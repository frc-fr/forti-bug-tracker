"""Read the web version of the Release Notes, for a version whose PDF cannot be reached."""
import html
import re
from typing import Dict, List

from .parser import MODEL, Document, Row, chapter_notices, to_observations

CHAPTERS = {
    "known": "known-issues",
    "resolved": "resolved-issues",
    "intro": "introduction-and-supported-models",
    "changes": "change-log",
}

HEADING_OR_ROW = re.compile(r'<h([23]) id="[^"]*">(.*?)</h\1>|<tr[^>]*>(.*?)</tr>', re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
BUG_ID = re.compile(r"\b\d{5,8}\b")
TOC_TOKEN = re.compile(r'<ul class="toc__children"|</ul>|<a class="toc__link" href="([^"]+)">(.*?)</a>', re.S)


def text_of(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def chapter_urls(page: str, version: str) -> Dict[str, str]:
    """Find the chapters in the navigation of a version page; their numbers are not stable."""
    urls = {}
    for name, slug in CHAPTERS.items():
        match = re.search(rf'href="(/document/fortigate/{re.escape(version)}/fortios-release-notes/\d+/{slug})"', page)
        if match:
            urls[name] = match.group(1)
    return urls


def parse_rows(page: str, known: bool) -> List[Row]:
    """Resolved issues are grouped by h2; known issues by status in h2 and category in h3."""
    rows = []
    status = "resolved"
    category = None
    for match in HEADING_OR_ROW.finditer(page):
        level, heading, row = match.groups()
        if heading is not None:
            title = text_of(heading)
            if known and level == "2":
                status = "known_new" if title.lower().startswith("new") else "known_existing"
                category = None
            else:
                category = title
            continue
        cells = CELL.findall(row)
        if len(cells) == 2 and BUG_ID.search(text_of(cells[0])):
            rows.append(Row(BUG_ID.findall(text_of(cells[0])), None, status, category, [text_of(cells[1])]))
    return rows


def parse_models(page: str) -> List[str]:
    start = page.find('id="supported-models"')
    text = text_of(page[start:]) if start >= 0 else ""
    return sorted(set(MODEL.findall(text)))


def parse_toc(page: str) -> List[tuple]:
    """The navigation as (level, title, path), like the bookmarks of a PDF."""
    start = page.find('class="toc__')
    toc = []
    level = 1
    for match in TOC_TOKEN.finditer(page, max(start, 0)):
        path, title = match.groups()
        if path:
            toc.append((level, text_of(title), path))
        elif match.group(0) == "</ul>":
            level -= 1
            if level < 1:
                break
        else:
            level += 1
    return toc


def parse_web_notes(pages: Dict[str, str]) -> Document:
    """Build the same document as a PDF; raise when the pages do not look as expected."""
    warnings: List[str] = []
    rows = parse_rows(pages["resolved"], False) + parse_rows(pages["known"], True)
    observations, skipped = to_observations(rows, warnings)
    models = parse_models(pages["intro"])
    if not observations or not models or warnings:
        raise ValueError(f"unexpected web notes: {len(observations)} bugs, {len(models)} models, {warnings}")
    build = re.search(r"\bbuild\s*(\d{3,4})\b", text_of(pages["intro"]))
    released = re.search(r"(\d{4}-\d{2}-\d{2})\s+Initial", text_of(pages["changes"]))
    return Document(build.group(1) if build else None, released.group(1) if released else None,
                    models, observations, skipped, [], chapter_notices(parse_toc(pages["intro"])))
