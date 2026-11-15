"""Extract the bug tables of a FortiOS Release Notes PDF.

The PDFs have a real text layer and bookmarks, so no OCR is involved: sections
come from the bookmarks and rows from the position of the text, anchored on the
"Bug ID" / "Description" table headers because the layout moved over the years.
Anything that does not fit is reported rather than dropped.

Every bug ID of a bug chapter ends in one bucket of the processing report: read, left
out by a known rule ("ruled"), or not understood ("failed"). The IDs are also read from
the plain text of the chapter, without the geometry: one found in none of the buckets
is a silent path of the code, and the report calls the note suspect.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import fitz

from .report import accounting, finding

BUG_ID = re.compile(r"\b\d{5,7}\b")
# A stray dash may follow the IDs: "300372 -".
ID_CELL = re.compile(r"^\s*\d{5,7}(\s*,?\s*\d{5,7})*\s*[,-]?\s*$")
# An ID the vendor printed broken, "205025 0" for a seven-digit ID: never guessed, left out by rule.
MALFORMED_ID = re.compile(r"^\s*(\d{5,7})\s+\d{1,2}\s*$")
BULLET_ID = re.compile(r"\((\d{5,7})\)")
CVE_REFERENCE = re.compile(r"[\s(,;]*\bCVE-\d{4}-\d{4,}\b[)]?", re.I)
VULNERABILITY_NOTICE = re.compile(r"no longer vulnerable|following CVE", re.I)
WORKAROUND = re.compile(r"\bWorkaround\s*:\s*", re.I)
MODEL = re.compile(r"\b(?:FG|FGT|FGR|FWF|FFW|FGVM|FOS|FS)-?[0-9V][0-9A-Za-z]*(?:-[0-9A-Za-z]+)*")
NOTICE_CHAPTERS = [
    (r"upgrade information$", "upgrade"),
    (r"special notices$", "special"),
    (r"changes in (default behavior|default values|cli defaults)$", "defaults"),
    (r"changes in cli$", "cli"),
    (r"changes in gui behavior$", "gui"),
    (r"changes in table ?size$", "table"),
]
OTHER_CHAPTERS = re.compile(
    r"change log|product integration|resolved issues|known issues|limitations|introduction|built-in|"
    r"new feature|table of contents|image checksum|firmware image checksums|appendix|supported models|upgrading to",
    re.I,
)
# Bug IDs cited in the text of the other chapters: "(bug ID 1234567)", "bug 570575".
CITED_ID = re.compile(r"\bbug(?:\s+ID)?\s*[:#]?\s*(\d{5,7})\b", re.I)
# The lines of a "Bug ID" table outside the bug chapters.
TABLE_ID = re.compile(r"(?m)^\s*(\d{5,7})\s*,?\s*$")
# Chapters whose IDs are not bugs (enhancements), or are read as changes of behavior.
NOT_PROSE = re.compile(r"new feature|^changes in", re.I)
# The frame of the PDF, not its content: never reported as a section left unread.
FRAME = re.compile(r"^table of contents$", re.I)
TABLE_CAPTION = re.compile(r"^Table \d+:\s*(?:Resolved |Known )?(.*?)(?: issues?)?(?: \(continued\))?$", re.I)
SYMBOL_FONTS = ("dingbat", "wingding", "symbol")

SAME_LINE = 2.5  # points: cells of one visual line can differ slightly in height
TOP_MARGIN, BOTTOM_MARGIN = 0.06, 0.93
CHAPTER_MIN_SIZE = 14  # chapter titles of old notes are large but not bold


@dataclass
class Line:
    x: float
    y: float
    text: str
    size: float
    bold: bool


@dataclass
class Row:
    ids: List[str]
    page: int
    status: str
    category: Optional[str]
    text: List[str] = field(default_factory=list)
    open_cell: bool = False  # the ID cell ended with a comma: more IDs follow


@dataclass
class Section:
    title: str
    first_page: int
    last_page: int
    next_title: Optional[str]
    status: str
    category: Optional[str] = None


MAX_SUMMARY = 220
CHANGE_CHAPTERS = ("defaults", "cli", "gui", "table")
VULNERABILITY_ID = re.compile(r"\b(CVE|CWE)\b")
CHAPTER_FURNITURE = re.compile(
    r"^(FortiOS .*Release Notes|Release Notes|Fortinet( Technologies)?,? Inc\.?,?|Changes in .{0,30}|Bug ID|Description|\d{1,3}|)$"
)


def as_text(found: dict) -> str:
    return f"{found['page']}: {found['count']} bugs under {found['where']!r}: {found['detail']}"


@dataclass
class Document:
    build: Optional[str]
    released: Optional[str]
    models: List[str]
    observations: List[dict]
    # What is not read, and why: a known rule ("left_out"), or a layout to adapt the code to.
    findings: List[dict]
    notices: List[list] = field(default_factory=list)
    pages: Dict[str, int] = field(default_factory=dict)
    changes: List[list] = field(default_factory=list)
    # Bug ID: (page, place) where the note lists it.
    listed: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    # Each chapter or section title, and whether the site reads something under it.
    headings: Dict[str, bool] = field(default_factory=dict)
    # Bug IDs cited in the text of the other chapters.
    prose: Set[str] = field(default_factory=set)

    @property
    def warnings(self) -> List[str]:
        """What the code cannot read: it has to be adapted."""
        return [as_text(f) for f in self.findings if f["kind"] == "not_understood"]

    @property
    def skipped_cve_rows(self) -> int:
        """The security fixes left out."""
        return sum(f["count"] for f in self.findings if f["rule"] == "security")

    def accounting(self) -> Dict[str, Set[str]]:
        """Each bug ID the note lists, in one bucket: read, ruled out, failed, or unaccounted."""
        return accounting(set(self.listed), {o["bug_id"] for o in self.observations}, self.findings)


def page_lines(page: fitz.Page) -> List[List[Line]]:
    """Return the body of a page as visual lines, each sorted left to right."""
    height = page.rect.height
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for raw in block.get("lines", []):
            spans = [s for s in raw["spans"] if s["text"].strip()]
            spans = [s for s in spans if not any(f in s["font"].lower() for f in SYMBOL_FONTS)]
            if not spans:
                continue
            x, y = raw["bbox"][:2]
            if y < height * TOP_MARGIN or y > height * BOTTOM_MARGIN:
                continue
            lines.append(Line(
                x=x, y=y,
                text="".join(s["text"] for s in spans).replace("\xa0", " ").strip(),
                size=max(s["size"] for s in spans),
                bold=any("bold" in s["font"].lower() or s["flags"] & 16 for s in spans),
            ))
    lines.sort(key=lambda line: line.y)
    grouped: List[List[Line]] = []
    for line in lines:
        if grouped and line.y - grouped[-1][0].y < SAME_LINE:
            grouped[-1].append(line)
        else:
            grouped.append([line])
    return [sorted(group, key=lambda line: line.x) for group in grouped]


def find_sections(doc: fitz.Document) -> List[Section]:
    tops = [entry for entry in doc.get_toc() if entry[0] == 1]
    sections = []
    for index, (_, title, page) in enumerate(tops):
        following = tops[index + 1] if index + 1 < len(tops) else None
        last_page = following[2] if following else len(doc)
        next_title = following[1] if following else None
        name = title.strip().lower()
        if name.startswith("resolved"):
            sections.append(Section(title, page, last_page, next_title, "resolved"))
        elif name.startswith("known"):
            sections.append(Section(title, page, last_page, next_title, "known"))
        elif re.match(r"built-in (av|ips) engine", name):
            category = "AV Engine" if " av " in name else "IPS Engine"
            sections.append(Section(title, page, last_page, next_title, "resolved", category))
    return sections


def normalize_title(text: str) -> str:
    return re.sub(r"\W+", "", text).lower()


def clean_category(text: str) -> str:
    """Old notes caption their tables: "Table 19: Resolved system issues (continued)"."""
    match = TABLE_CAPTION.match(text)
    if not match:
        return text
    name = match.group(1).strip()
    return name[:1].upper() + name[1:]


def header_columns(group: List[Line]) -> Optional[Tuple[float, float, str]]:
    """Return (id column x, text column x, text column name) for a table header."""
    if len(group) < 2 or normalize_title(group[0].text) != "bugid":
        return None
    return group[0].x, group[1].x, group[1].text


def after_title(groups: List[List[Line]], title: str) -> List[List[Line]]:
    """Drop what precedes a chapter title, as it may belong to the previous chapter."""
    wanted = normalize_title(title)
    for index, group in enumerate(groups):
        if normalize_title(group[0].text) == wanted:
            return groups[index + 1:]
    return groups


def link(url: str, page: Optional[int]) -> str:
    """The exact page of the PDF, as the site links it."""
    return f"{url}#page={page}" if page else url


def place(section_title: str, category: Optional[str]) -> str:
    return " / ".join(part for part in (section_title, category) if part)


def parse_section(doc: fitz.Document, section: Section, findings: List[dict], url: str) -> Tuple[List[Row], List[Row]]:
    """The rows of a bug chapter, and those of its security tables, which the site leaves out."""
    rows: List[Row] = []
    security: List[Row] = []
    status = section.status
    category = section.category
    columns: Optional[Tuple[float, float]] = None
    cve_table = False
    row: Optional[Row] = None
    stop = normalize_title(section.next_title or "\0")

    for number in range(section.first_page, section.last_page + 1):
        groups = page_lines(doc[number - 1])
        if number == section.first_page:
            groups = after_title(groups, section.title)
        for group in groups:
            first = group[0]
            header = header_columns(group)
            if header:
                columns = header[:2]
                cve_table = "cve" in header[2].lower() or cve_table
                if not cve_table and normalize_title(header[2]) != "description":
                    findings.append(finding("not_understood", "unknown_column", link(url, number),
                                            place(section.title, category), [], f"a table column named {header[2]!r}"))
                row = None
                continue

            in_table_text = columns is not None and first.x >= columns[1] - 2
            if len(group) == 1 and not in_table_text and (first.bold or first.size >= CHAPTER_MIN_SIZE):
                title = normalize_title(first.text)
                if title == stop:
                    return rows, security
                # The chapter title is repeated on top of its pages: tables go on.
                if title == normalize_title(section.title):
                    continue
                row, columns = None, None
                if title == "newknownissues":
                    status, category = "known_new", section.category
                elif title == "existingknownissues":
                    status, category = "known_existing", section.category
                elif "vulnerabilit" in title:
                    cve_table = True
                    if section.category is None:
                        category = clean_category(first.text)
                elif section.category is None:
                    cve_table = False
                    category = clean_category(first.text)
                continue

            if columns is None:
                continue
            left = [line for line in group if line.x < columns[1] - 2]
            right = [line for line in group if line.x >= columns[1] - 2]
            cell = " ".join(line.text for line in left)
            if left and ID_CELL.match(cell):
                ids = BUG_ID.findall(cell)
                # IDs stacked in one cell share the description of the first line.
                if row is not None and (row.open_cell or not right):
                    row.ids.extend(ids)
                else:
                    row = Row(ids, number, status, category)
                    (security if cve_table else rows).append(row)
                row.open_cell = cell.rstrip().endswith(",")
            elif left:
                # An ID cell with more than IDs: a form the parser does not read. The end of a
                # reference, "(duplicate of" + "378521)", lists no bug.
                broken = MALFORMED_ID.match(cell)
                found = re.match(r"\s*(\d{5,7})(?=\s|,|$)", cell)
                if broken:
                    findings.append(finding("left_out", "malformed_id", link(url, number), place(section.title, category),
                                            [broken.group(1)], f"an ID printed broken by the vendor, not guessed: {cell.strip()!r}"))
                elif found:
                    findings.append(finding("not_understood", "id_cell", link(url, number), place(section.title, category),
                                            [found.group(1)], f"an ID cell that holds more than IDs: {cell[:60]!r}"))
                row = None
                continue
            if row is not None and right:
                row.text.extend(line.text for line in right)
    return rows, security


def parse_bullets(doc: fitz.Document, section: Section) -> List[Row]:
    """Early 5.x notes list issues as bullets ending with "(id)", without tables."""
    rows: List[Row] = []
    for number in range(section.first_page, section.last_page + 1):
        text = doc[number - 1].get_text()
        for item in re.split(r"\n\s*•\s*", text)[1:]:
            match = BULLET_ID.search(item)
            if match:
                description = " ".join(item[:match.start()].split())
                rows.append(Row([match.group(1)], number, section.status, None, [description]))
    return rows


def join_lines(lines: List[str]) -> str:
    """Join wrapped lines; a line broken after a hyphen is one word: "rate-" + "limit"."""
    text = ""
    for line in lines:
        glued = text.endswith("-") and len(text) > 1 and text[-2] != " "
        text += line if glued or not text else f" {line}"
    return text


def clean_description(text: str) -> Tuple[str, Optional[str]]:
    """Split the workaround out and remove CVE references from a description."""
    text = CVE_REFERENCE.sub("", " ".join(text.split())).strip()
    parts = WORKAROUND.split(text, maxsplit=1)
    workaround = parts[1].strip() if len(parts) > 1 else None
    return parts[0].strip(), workaround or None


def to_observations(rows: List[Row], findings: List[dict], url: str, chapter: str = "") -> List[dict]:
    """The observations of the rows; a security fix, or a row without text, goes to the findings."""
    observations = []
    for row in rows:
        raw = join_lines(row.text)
        if VULNERABILITY_NOTICE.search(raw):
            findings.append(finding("left_out", "security", link(url, row.page), place(chapter, row.category), row.ids,
                                    "a vulnerability fix in a bug list"))
            continue
        description, workaround = clean_description(raw)
        if not description:
            findings.append(finding("not_understood", "no_description", link(url, row.page), place(chapter, row.category),
                                    row.ids, "a bug ID without description: the table layout is not read"))
        for bug_id in row.ids:
            observations.append({
                "bug_id": bug_id,
                "status": row.status,
                "category": row.category,
                "description": description,
                "workaround": workaround,
                "page": row.page,
            })
    return observations


def extract_models(doc: fitz.Document) -> List[str]:
    toc = doc.get_toc()
    for index, (level, title, page) in enumerate(toc):
        if title.strip().lower() != "supported models":
            continue
        # The list goes on under sub-headings: "FortiGate", "FortiWiFi", "6000 and 7000"...
        following = next(
            (entry for entry in toc[index + 1:]
             if entry[0] <= level and not re.search(r"supported models|^forti|6000|7000", entry[1].strip(), re.I)),
            None,
        )
        last = following[2] if following else page
        text = "\n".join(doc[number - 1].get_text() for number in range(page, last + 1))
        # Names are cut at their hyphens by line wraps: "FG-" + "200D", "FG-200D-" + "POE".
        text = re.sub(r"(?<=-)\s+", "", text)
        first = MODEL.search(text)
        if not first:
            return []
        # From the first model on: the introduction lists the chapter titles before it.
        text = text[first.start():]
        if following:
            text = re.split(title_pattern(following[1]), text)[0]
        return sorted(set(MODEL.findall(text)))
    return []


def find_in_pages(doc: fitz.Document, pattern: str, limit: int) -> Tuple[Optional[str], Optional[int]]:
    """First match in the opening pages, with its page number as a PDF link expects it."""
    for number in range(min(limit, len(doc))):
        match = re.search(pattern, doc[number].get_text())
        if match:
            return match.group(1), number + 1
    return None, None


def change_log_page(doc: fitz.Document) -> Optional[int]:
    """The chapter holding the release and revision dates, whatever their format."""
    return next((page for _, title, page in doc.get_toc() if title.strip().lower() == "change log"), None)


def chapter_notices(toc: List[tuple]) -> List[list]:
    """List the [chapter, title, reference] worth reading before an upgrade.

    A chapter without sections keeps a None title: its content is specific to the
    version. A top-level entry that is no known chapter is a misplaced section.
    """
    notices = []
    current = None
    for level, title, reference in toc:
        name = " ".join(title.split())
        code = next((code for pattern, code in NOTICE_CHAPTERS if re.match(pattern, name, re.I)), None)
        if level == 1 and code:
            current = code
            notices.append([code, None, reference])
        elif level == 1 and OTHER_CHAPTERS.match(name):
            current = None
        elif current and level <= 2:
            notices.append([current, name, reference])
    titled = {notice[0] for notice in notices if notice[1]}
    return [notice for notice in notices if notice[1] or notice[0] not in titled]


def full_title(doc: fitz.Document, title: str, page: int) -> str:
    """Bookmarks cut long titles: the heading on the page has the rest."""
    prefix = title[:-3].strip()
    for block in doc[page - 1].get_text("dict")["blocks"]:
        spans = [span["text"] for line in block.get("lines", []) for span in line["spans"]]
        text = " ".join(" ".join(spans).split())
        if text.startswith(prefix):
            return text
    return f"{prefix}…"


def extract_notices(doc: fitz.Document) -> List[list]:
    notices = chapter_notices(doc.get_toc())
    for notice in notices:
        if notice[1] and notice[1].endswith("..."):
            notice[1] = full_title(doc, notice[1], notice[2])
    return notices


def first_sentence(text: str) -> str:
    """The summary of a change: its full text can run over a page."""
    text = re.sub(r"^[l•]\s+", "", " ".join(text.split()))
    sentence = re.split(r"(?<=[.!?])\s+(?=[A-Z]|config\b)", text)[0]
    if len(sentence) <= MAX_SUMMARY:
        return sentence
    return sentence[:MAX_SUMMARY].rsplit(" ", 1)[0] + "…"


def chapter_rows(doc: fitz.Document, chapter: str, notices: List[list]) -> List[list]:
    """List the [chapter, bug ID, summary, page] of a table of changes."""
    start = next((notice[2] for notice in notices if notice[0] == chapter), None)
    if not isinstance(start, int):
        return []
    following = [page for level, _, page in doc.get_toc() if level == 1 and page > start]
    rows: List[list] = []
    for number in range(start, min(following or [start + 1])):
        for line in doc[number - 1].get_text().splitlines():
            text = line.strip()
            if re.fullmatch(r"\d{6,7}", text):
                rows.append([text, "", number])
            elif rows and not CHAPTER_FURNITURE.match(text):
                rows[-1][1] += f" {text}"
    summaries = [[chapter, bug, first_sentence(text), page] for bug, text, page in rows]
    return [row for row in summaries if not VULNERABILITY_ID.search(row[2])]


def extract_changes(doc: fitz.Document, notices: List[list]) -> List[list]:
    return [row for chapter in CHANGE_CHAPTERS for row in chapter_rows(doc, chapter, notices)]


def title_pattern(title: str) -> str:
    return r"(?m)^\s*" + r"\s+".join(map(re.escape, title.split())) + r"\s*$"


def listed_ids(doc: fitz.Document, section: Section) -> Dict[str, int]:
    """IDs of a section found without the geometry, with their page: the cross-check of the parser."""
    found: Dict[str, int] = {}
    started = False
    for number in range(section.first_page, section.last_page + 1):
        text = doc[number - 1].get_text()
        if not started:
            start = re.search(title_pattern(section.title), text)
            if start:
                text, started = text[start.end():], True
            elif number == section.first_page:
                started = True
        if section.next_title and number == section.last_page:
            # The last page is shared when the next chapter starts on it.
            text = re.split(title_pattern(section.next_title), text)[0]
        text = re.sub(r"Beta Forum:\s*\d+", "", text)
        for bug in re.findall(r"(?m)^\s*(\d{5,7})\s*,?\s*(?:$|[A-Za-z])", text):
            found.setdefault(bug, number)
    return found


def chapter_headings(toc: List[tuple], sections: List[Section]) -> Dict[str, bool]:
    """Each chapter and section title, and whether the site reads something under it.

    Read: the bug chapters and their sections, the chapters of notices and their
    sections, the change log (dates) and the supported models.
    """
    bugs = {section.title for section in sections}
    notices = {notice[1] for notice in chapter_notices(toc) if notice[1]}
    headings: Dict[str, bool] = {}
    whole = False
    for level, title, _ in toc:
        name = " ".join(title.split())
        if level > 2 or FRAME.match(name):
            continue
        if level == 1:
            notice = any(re.match(pattern, name, re.I) for pattern, _ in NOTICE_CHAPTERS)
            whole = title in bugs or notice
            used = whole or bool(re.match(r"change log$|introduction", name, re.I))
        else:
            used = whole or bool(re.search(r"supported models", name, re.I))
        headings[name] = headings.get(name, False) or used or name in notices
    return headings


def cited_ids(doc: fitz.Document, sections: List[Section]) -> Set[str]:
    """Bug IDs cited in the other chapters: special notices, limitations, change log..."""
    toc = [(title, page) for level, title, page in doc.get_toc() if level == 1]
    bug_pages = {n for s in sections for n in range(s.first_page, s.last_page + 1)}
    found: Set[str] = set()
    for number in range(1, len(doc) + 1):
        chapter = next((title for title, page in reversed(toc) if page <= number), "")
        if number in bug_pages or NOT_PROSE.search(chapter.strip()):
            continue
        text = doc[number - 1].get_text()
        found.update(CITED_ID.findall(text))
        if re.search(r"(?m)^\s*Bug ID\s*$", text):
            found.update(TABLE_ID.findall(text))
    return found


def parse_pdf(path: Path, url: str = "") -> Document:
    """Read a PDF; `url` is where Fortinet publishes it, for the exact pages of the report."""
    doc = fitz.open(path)
    findings: List[dict] = []
    sections = find_sections(doc)
    for status, name in (("resolved", "Resolved issues"), ("known", "Known issues")):
        if not any(s.status == status for s in sections):
            findings.append(finding("not_understood", "section_missing", url, "", [],
                                    f"no {name} chapter among the bookmarks"))

    observations: List[dict] = []
    listed: Dict[str, Tuple[str, str]] = {}
    for section in sections:
        rows, security = parse_section(doc, section, findings, url)
        if not rows and section.category is None:
            rows = parse_bullets(doc, section)
        observations.extend(to_observations(rows, findings, url, section.title))
        for row in security:
            findings.append(finding("left_out", "security", link(url, row.page), place(section.title, row.category),
                                    row.ids, "a list of vulnerability fixes"))
        for row in rows + security:
            for bug in row.ids:
                listed.setdefault(bug, (link(url, row.page), place(section.title, row.category)))
        # A line of a description may start with a number: only the ID cell of a row lists a bug.
        described = {found.group(1) for row in rows + security for line in row.text
                     for found in [re.match(r"\s*(\d{5,7})\b", line)] if found}
        for bug, number in listed_ids(doc, section).items():
            if bug not in listed and bug not in described:
                listed[bug] = (link(url, number), section.title)

    build, build_page = find_in_pages(doc, r"\bbuild\s*(\d{3,4})\b", 12)
    notices = extract_notices(doc)
    released, released_page = find_in_pages(doc, r"(\d{4}-\d{2}-\d{2})\s+Initial", 10)
    changes = extract_changes(doc, notices)
    return Document(
        build=build,
        released=released,
        models=extract_models(doc),
        observations=observations,
        findings=findings,
        notices=notices,
        changes=changes,
        pages={"build": build_page, "changes": change_log_page(doc) or released_page},
        listed=listed,
        headings=chapter_headings(doc.get_toc(), sections),
        prose=cited_ids(doc, sections) - set(listed) - {row[1] for row in changes},
    )
