"""Parser tests on synthetic PDFs: Fortinet's own files are not redistributed here."""
import fitz
import pytest

from fortibugs.parser import chapter_notices, clean_category, clean_description, find_in_pages, first_sentence, join_lines, parse_pdf

ID_X, TEXT_X = 62, 137


class Notes:
    """Builds a minimal Release Notes PDF with the layout of the real ones."""

    def __init__(self):
        self.doc = fitz.open()
        self.toc = []
        self.page = None
        self.y = 0

    def new_page(self):
        self.page = self.doc.new_page(width=612, height=792)
        self.y = 80

    def write(self, x, text, font="helv", size=9.5, y=None):
        self.page.insert_text((x, self.y if y is None else y), text, fontname=font, fontsize=size)

    def chapter(self, title, new_page=True):
        if new_page:
            self.new_page()
        else:
            self.y += 40
        self.toc.append([1, title, self.doc.page_count])
        self.write(35, title, "hebo", 27)
        self.y += 40

    def heading(self, title):
        self.write(35, title, "hebo", 18)
        self.y += 30

    def header(self, second="Description"):
        self.write(ID_X, "Bug ID", "hebo", 10)
        self.write(TEXT_X, second, "hebo", 10)
        self.y += 20

    def row(self, bug_id, *lines):
        self.write(ID_X, bug_id)
        for line in lines:
            self.write(TEXT_X, line)
            self.y += 13
        self.y += 6

    def save(self, path):
        self.doc.set_toc(self.toc)
        self.doc.save(path)
        return parse_pdf(path)


@pytest.fixture
def notes():
    return Notes()


def test_rows_categories_and_wrapped_descriptions(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("IPsec VPN")
    notes.header()
    notes.row("1203158", "Tunnel flaps during rekey")
    notes.row("1214345", "High memory usage when multiple", "VDOMs are configured.")
    result = notes.save(tmp_path / "n.pdf")
    assert [(o["bug_id"], o["status"], o["category"], o["description"]) for o in result.observations] == [
        ("1203158", "resolved", "IPsec VPN", "Tunnel flaps during rekey"),
        ("1214345", "resolved", "IPsec VPN", "High memory usage when multiple VDOMs are configured."),
    ]
    assert result.warnings == ["no Known issues section"]


def test_stacked_ids_share_their_description(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("Routing")
    notes.header()
    notes.write(ID_X, "1075607,")
    notes.write(TEXT_X, "BGP flaps after failover")
    notes.y += 13
    notes.write(ID_X, "1075911")
    notes.y += 19
    result = notes.save(tmp_path / "n.pdf")
    assert [(o["bug_id"], o["description"]) for o in result.observations] == [
        ("1075607", "BGP flaps after failover"),
        ("1075911", "BGP flaps after failover"),
    ]


def test_row_continues_on_next_page_under_repeated_title(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header()
    notes.row("1203158", "First part")
    notes.new_page()
    notes.write(35, "Resolved issues", "hebo", 27)
    notes.y += 40
    notes.header()
    notes.row("1214345", "Second bug")
    result = notes.save(tmp_path / "n.pdf")
    assert [o["category"] for o in result.observations] == ["GUI", "GUI"]


def test_known_issues_on_a_shared_page_are_not_resolved(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header()
    notes.row("1203158", "Fixed bug")
    notes.chapter("Known issues", new_page=False)
    notes.heading("New known issues")
    notes.heading("HA")
    notes.header()
    notes.row("1214345", "Open bug")
    result = notes.save(tmp_path / "n.pdf")
    assert [(o["bug_id"], o["status"], o["category"]) for o in result.observations] == [
        ("1203158", "resolved", "GUI"),
        ("1214345", "known_new", "HA"),
    ]


def test_chapter_starts_at_its_title_on_a_shared_page(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header()
    notes.row("1203158", "Fixed bug")
    notes.chapter("Known issues", new_page=False)
    notes.heading("HA")
    notes.header()
    notes.row("1214345", "Open bug")
    result = notes.save(tmp_path / "n.pdf")
    statuses = {o["bug_id"]: o["status"] for o in result.observations}
    assert statuses == {"1203158": "resolved", "1214345": "known"}
    assert len(result.observations) == 2


def test_cve_tables_are_dropped(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header()
    notes.row("1203158", "Fixed bug")
    notes.heading("Common Vulnerabilities and Exposures")
    notes.header("CVE references")
    notes.row("1227177", "FortiOS 7.6.7 is no longer vulnerable to the following CVE Reference:")
    result = notes.save(tmp_path / "n.pdf")
    assert [o["bug_id"] for o in result.observations] == ["1203158"]
    assert result.skipped_cve_rows == 1


def test_unknown_table_column_is_reported(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header("Severity")
    notes.row("1203158", "Fixed bug")
    assert any("unknown column" in w for w in notes.save(tmp_path / "n.pdf").warnings)


def test_id_outside_a_table_is_reported(notes, tmp_path):
    notes.chapter("Resolved issues")
    notes.heading("GUI")
    notes.header()
    notes.row("1203158", "Fixed bug")
    notes.heading("Other")
    notes.write(ID_X, "1214345 is listed without a table header")
    assert any("not parsed" in w for w in notes.save(tmp_path / "n.pdf").warnings)


def test_workaround_and_cve_cleaning():
    assert clean_description("Blank page. Workaround: clear the cache") == ("Blank page.", "clear the cache")
    assert clean_description("Crash in sslvpnd (CVE-2023-27997).") == ("Crash in sslvpnd.", None)


def test_lines_broken_after_a_hyphen_are_glued():
    assert join_lines(["set admin-http-rate-", "limit-max-requests 0"]) == "set admin-http-rate-limit-max-requests 0"
    assert join_lines(["first line -", "second line"]) == "first line - second line"
    assert join_lines(["first line", "second line"]) == "first line second line"


def test_table_captions():
    assert clean_category("Table 19: Resolved system issues (continued)") == "System"
    assert clean_category("IPsec VPN") == "IPsec VPN"


def test_supported_models_with_wrapped_names_and_sub_headings(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 70), "Special Notices")
    page.insert_text((60, 100), "Supported models")
    page.insert_text((60, 130), "FortiGate")
    page.insert_text((60, 150), "FG-100D, FG- 200D, FG-200D-")
    page.insert_text((60, 165), "POE, FG-300D")
    page.insert_text((60, 190), "FortiWiFi")
    page.insert_text((60, 210), "FWF-60F")
    page.insert_text((60, 240), "Special Notices")
    page.insert_text((60, 260), "FG-999D is not in the list")
    doc.set_toc([
        [1, "Introduction", 1], [2, "Supported models", 1], [2, "FortiGate", 1], [2, "FortiWiFi", 1],
        [1, "Special Notices", 1],
    ])
    doc.save(tmp_path / "n.pdf")
    assert parse_pdf(tmp_path / "n.pdf").models == ["FG-100D", "FG-200D", "FG-200D-POE", "FG-300D", "FWF-60F"]


def test_notices_keep_sections_and_version_specific_chapters():
    toc = [
        (1, "Change Log", 1),
        (1, "Upgrade information", 2),
        (2, "Downgrading", 3),
        (3, "Too deep", 3),
        (1, "A misplaced section", 4),
        (1, "Changes in table size", 5),
        (1, "Resolved issues", 6),
        (2, "Firewall", 6),
    ]
    assert chapter_notices(toc) == [
        ["upgrade", "Downgrading", 3], ["upgrade", "A misplaced section", 4], ["table", None, 5]]


class FakePage:
    def __init__(self, text):
        self.text = text

    def get_text(self):
        return self.text


def test_a_fact_keeps_the_page_a_pdf_link_expects():
    pages = [FakePage("Contents"), FakePage("2026-10-22 Initial release."), FakePage("build 1778")]
    assert find_in_pages(pages, r"(\d{4}-\d{2}-\d{2})\s+Initial", 10) == ("2026-10-22", 2)
    assert find_in_pages(pages, r"\bbuild\s*(\d{3,4})\b", 2) == (None, None)


def test_a_change_is_summed_up_by_its_first_sentence():
    assert first_sentence("l Inline IPS is now disabled. It was enabled.") == "Inline IPS is now disabled."
    assert first_sentence("Change the default. config system interface") == "Change the default."
    assert first_sentence("Use e.g. this value") == "Use e.g. this value"
    assert first_sentence("word " * 100).endswith("…")
