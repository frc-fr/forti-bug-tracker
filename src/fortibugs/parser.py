"""Extract the bug tables of a FortiOS Release Notes PDF.

The PDFs have a real text layer and bookmarks, so no OCR is involved: sections
come from the bookmarks and rows from the position of the text, anchored on the
"Bug ID" / "Description" table headers because the layout moved over the years.
Anything that does not fit is reported in `warnings` rather than dropped.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

BUG_ID = re.compile(r"\b\d{5,7}\b")
ID_CELL = re.compile(r"^\s*\d{5,7}(\s*,?\s*\d{5,7})*\s*,?\s*$")
BULLET_ID = re.compile(r"\((\d{5,7})\)")
CVE_REFERENCE = re.compile(r"[\s(,;]*\bCVE-\d{4}-\d{4,}\b[)]?", re.I)
VULNERABILITY_NOTICE = re.compile(r"no longer vulnerable|following CVE", re.I)
WORKAROUND = re.compile(r"\bWorkaround\s*:\s*", re.I)
MODEL = re.compile(r"\b(?:FG|FGT|FGR|FWF|FFW|FGVM|FOS|FS)-?[0-9V][0-9A-Za-z]*(?:-[0-9A-Za-z]+)*")
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


@dataclass
class Document:
    build: Optional[str]
    released: Optional[str]
    models: List[str]
    observations: List[dict]
    skipped_cve_rows: int
    warnings: List[str]


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


def parse_section(doc: fitz.Document, section: Section, warnings: List[str]) -> Tuple[List[Row], int]:
    rows: List[Row] = []
    skipped = 0
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
                    warnings.append(f"p{number}: unknown column {header[2]!r}")
                row = None
                continue

            in_table_text = columns is not None and first.x >= columns[1] - 2
            if len(group) == 1 and not in_table_text and (first.bold or first.size >= CHAPTER_MIN_SIZE):
                title = normalize_title(first.text)
                if title == stop:
                    return rows, skipped
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
                    if cve_table:
                        skipped += 1
                    row = Row(ids, number, status, category)
                    if not cve_table:
                        rows.append(row)
                row.open_cell = cell.rstrip().endswith(",")
            elif left:
                row = None
                continue
            if row is not None and right:
                row.text.extend(line.text for line in right)
    return rows, skipped


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


def to_observations(rows: List[Row], warnings: List[str]) -> Tuple[List[dict], int]:
    observations = []
    skipped = 0
    for row in rows:
        raw = join_lines(row.text)
        if VULNERABILITY_NOTICE.search(raw):
            skipped += 1
            continue
        description, workaround = clean_description(raw)
        if not description:
            warnings.append(f"p{row.page}: bug {row.ids[0]} has no description")
        for bug_id in row.ids:
            observations.append({
                "bug_id": bug_id,
                "status": row.status,
                "category": row.category,
                "description": description,
                "workaround": workaround,
                "page": row.page,
            })
    return observations, skipped


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


def extract_build(doc: fitz.Document) -> Optional[str]:
    for number in range(min(12, len(doc))):
        match = re.search(r"\bbuild\s*(\d{3,4})\b", doc[number].get_text())
        if match:
            return match.group(1)
    return None


def extract_release_date(doc: fitz.Document) -> Optional[str]:
    for number in range(min(10, len(doc))):
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s+Initial", doc[number].get_text())
        if match:
            return match.group(1)
    return None


def title_pattern(title: str) -> str:
    return r"(?m)^\s*" + r"\s+".join(map(re.escape, title.split())) + r"\s*$"


def expected_ids(doc: fitz.Document, section: Section) -> set:
    """IDs of a section found without the geometry: the cross-check of the parser."""
    text = "\n".join(
        doc[number - 1].get_text()
        for number in range(section.first_page, section.last_page + 1)
    )
    start = re.search(title_pattern(section.title), text)
    if start:
        text = text[start.end():]
    if section.next_title:
        # The last page is shared when the next chapter starts on it.
        text = re.split(title_pattern(section.next_title), text)[0]
    text = re.sub(r"Beta Forum:\s*\d+", "", text)
    return set(re.findall(r"(?m)^\s*(\d{5,7})\s*,?\s*(?:$|[A-Za-z])", text))


def parse_pdf(path: Path) -> Document:
    doc = fitz.open(path)
    warnings: List[str] = []
    sections = find_sections(doc)
    if not any(s.status == "resolved" for s in sections):
        warnings.append("no Resolved issues section")
    if not any(s.status == "known" for s in sections):
        warnings.append("no Known issues section")

    observations: List[dict] = []
    skipped = 0
    seen: Dict[str, bool] = {}
    for section in sections:
        rows, section_skipped = parse_section(doc, section, warnings)
        if not rows and section.category is None:
            rows = parse_bullets(doc, section)
        section_observations, notices = to_observations(rows, warnings)
        skipped += section_skipped + notices
        observations.extend(section_observations)
        seen.update((o["bug_id"], True) for o in section_observations)
        if not section_skipped and not notices:
            missing = sorted(expected_ids(doc, section) - set(seen))
            if missing:
                warnings.append(f"{section.title}: {len(missing)} IDs not parsed: {missing[:5]}")

    return Document(
        build=extract_build(doc),
        released=extract_release_date(doc),
        models=extract_models(doc),
        observations=observations,
        skipped_cve_rows=skipped,
        warnings=warnings,
    )
