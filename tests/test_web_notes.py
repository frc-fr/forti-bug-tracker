import json

import pytest

from fortibugs.extract import extract_all
from fortibugs.web_notes import chapter_urls, parse_changes, parse_toc, parse_web_notes

HEAD = "<tr><th><p>Bug ID</p></th><th><p>Description</p></th></tr>"


def row(bug, text):
    return f"<tr><td><p>{bug}</p></td><td><p>{text}</p></td></tr>"


PAGES = {
    "resolved": '<h2>Products</h2><h2 id="gui">GUI</h2><table>' + HEAD + row("100001", "Fixed &amp; done.") + "</table>"
                '<h2 id="cve">Common Vulnerabilities and Exposures</h2><table>'
                + row("100002", "FortiOS is no longer vulnerable to the following CVE References: CVE-2026-0001")
                + "</table>",
    "known": '<h2 id="new">New known issues</h2><h3 id="ha">HA</h3><table>' + row("100003", "New bug.") + "</table>"
             '<h2 id="existing">Existing known issues</h2><h3 id="vm">VM</h3><table>'
             + row("100004", "<p>Old bug.</p><p>Workaround: reboot.</p>") + "</table>",
    "intro": '<p>FortiOS 7.4.7 build 2731.</p><h2 id="supported-models">Supported models</h2><p>FG-40F, FWF-40F</p>',
    "changes": "<table><tr><td>2025-02-03</td><td>Initial release.</td></tr></table>",
}


def test_web_notes_give_the_same_document_as_a_pdf():
    document = parse_web_notes(PAGES)
    assert (document.build, document.released, document.models) == ("2731", "2025-02-03", ["FG-40F", "FWF-40F"])
    assert document.skipped_cve_rows == 1
    assert [(o["bug_id"], o["status"], o["category"]) for o in document.observations] == [
        ("100001", "resolved", "GUI"), ("100003", "known_new", "HA"), ("100004", "known_existing", "VM")]
    assert document.observations[0]["description"] == "Fixed & done."
    assert document.observations[2]["workaround"] == "reboot."
    assert not any("CVE" in o["description"] for o in document.observations)


def test_a_changed_layout_is_refused():
    with pytest.raises(ValueError):
        parse_web_notes({**PAGES, "resolved": "<p>New layout</p>", "known": "<p>New layout</p>"})


def test_chapters_come_from_the_navigation():
    page = ('<a href="/document/fortigate/7.4.7/fortios-release-notes/236526/known-issues">x</a>'
            '<a href="/document/fortigate/7.4.6/fortios-release-notes/1/resolved-issues">y</a>')
    assert chapter_urls(page, "7.4.7") == {"known": "/document/fortigate/7.4.7/fortios-release-notes/236526/known-issues"}


def test_a_broken_page_keeps_the_last_data(tmp_path):
    cache, output, log = tmp_path / "cache", tmp_path / "out", tmp_path / "changes.json"
    cache.mkdir()
    output.mkdir()
    log.write_text("[]")
    (output / "7.4.7.json").write_text("previous")
    (cache / "7.4.7.web.json").write_text(json.dumps({**PAGES, "resolved": "", "known": ""}))
    assert extract_all(cache, output, log) == {}
    assert (output / "7.4.7.json").read_text() == "previous"


def test_the_navigation_reads_like_bookmarks():
    link = '<a class="toc__link" href="/{0}">{0}</a>'
    page = ('<nav class="toc__tree"><ul>' + link.format("Special notices") + '<ul class="toc__children" hidden>'
            + link.format("One") + "</ul>" + link.format("Resolved issues") + "</ul></nav>")
    assert parse_toc(page)[:2] == [(1, "Special notices", "/Special notices"), (2, "One", "/One")]


def test_a_change_table_gives_the_same_rows_as_a_pdf():
    page = "<table><tr><td>1104085</td><td>Increase the limit. It was lower.</td></tr><tr><td>Bug ID</td><td>Description</td></tr></table>"
    changes = parse_changes({"table": page}, [["table", None, "/document/table"]])
    assert changes == [["table", "1104085", "Increase the limit.", "/document/table"]]
