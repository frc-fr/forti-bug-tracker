"""Fortinet's recommended FortiOS release per model, from its community article.

The article is reviewed quarterly and only its product table is kept. A page that
no longer parses must not erase the last valid table: the site shows its date.
"""
import html
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

log = logging.getLogger(__name__)

ARTICLE_URL = "https://community.fortinet.com/fortigate-3/recommended-release-for-fortios-116639"
MINIMUM_ROWS = 50

AS_OF = re.compile(r"latest as of ([A-Z][a-z]+ \d{4})")
TABLE = re.compile(r"Product Details.*?</table>", re.S)
ROW = re.compile(r"<tr.*?</tr>", re.S)
CELL = re.compile(r"<td.*?</td>", re.S)
RELEASE = re.compile(r"^\d+\.\d+\.\d+$")

PRODUCT = re.compile(r"^(FortiGateRugged|FortiGate|FortiWiFi)-(.+)$", re.I)
PREFIXES = {"fortigaterugged": "FGR", "fortigate": "FG", "fortiwifi": "FWF"}
ANY_VARIANT = re.compile(r"\s*(and variants|-\s*all versions)\s*$", re.I)
SERIES = re.compile(r"^([67])000([EF])$")
# The article and the Release Notes do not spell these models the same way.
ALIASES = {"FG-280D": "FG-280D-POE", "FG-400E-BYPASS": "FG-400E-BP"}


def cell_text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def parse_article(page: str) -> dict:
    """Return the date and the rows of the article; raise if it looks wrong."""
    as_of = AS_OF.search(page)
    table = TABLE.search(page)
    if not as_of or not table:
        raise ValueError("recommended release table not found")

    entries = []
    segment = None
    for row in ROW.findall(table.group(0)):
        cells = [cell_text(cell) for cell in CELL.findall(row)]
        if len(cells) != 4:
            continue
        segment = cells[0] or segment
        product, release, ended = cells[1:]
        if not RELEASE.match(release) or ended not in ("Y", "N"):
            raise ValueError(f"unexpected row: {cells}")
        entries.append({"segment": segment, "product": product, "release": release,
                        "engineering_support_ended": ended == "Y"})
    if len(entries) < MINIMUM_ROWS:
        raise ValueError(f"only {len(entries)} rows in the recommended release table")
    return {"as_of": datetime.strptime(as_of.group(1), "%B %Y").strftime("%Y-%m"), "entries": entries}


def update_recommended(path: Path, client) -> None:
    """Refresh the table; the Release Notes must not depend on this page."""
    try:
        response = client.request("GET", ARTICLE_URL)
        response.raise_for_status()
        content = parse_article(response.text)
    except (RuntimeError, ValueError, OSError) as error:
        log.error("recommended releases kept as they were: %s", error)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source": ARTICLE_URL, **content}, indent=2) + "\n")


def product_patterns(product: str) -> List[str]:
    """Regular expressions of the model names covered by a row of the article."""
    match = PRODUCT.match(product)
    if not match:
        return []
    prefix = PREFIXES[match.group(1).lower()]
    names = ANY_VARIANT.sub("", match.group(2))
    suffix = "(-.+)?" if ANY_VARIANT.search(match.group(2)) else ""
    patterns = []
    for name in re.split(r"\s*/\s*", names):
        series = SERIES.match(name)
        if series:
            patterns.append(rf"{prefix}-{series.group(1)}\d{{3}}{series.group(2)}")
        else:
            model = f"{prefix}-{name.upper()}"
            patterns.append(re.escape(ALIASES.get(model, model)) + suffix)
    return patterns


def resolve_models(entries: Iterable[dict], models: Iterable[str]) -> Tuple[Dict[str, dict], List[str]]:
    """Map our model names to their row; also return the rows matching no model."""
    models = list(models)
    resolved: Dict[str, dict] = {}
    unmatched = []
    for entry in entries:
        found = [model for pattern in product_patterns(entry["product"]) for model in models
                 if re.fullmatch(pattern, model)]
        if not found:
            unmatched.append(entry["product"])
        for model in found:
            resolved[model] = entry
    return resolved, unmatched
