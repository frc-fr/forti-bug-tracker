"""Turn the cached PDFs into data/extracted/<version>.json and log what changed."""
import json
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import report
from .collect import PAGE_URL, WEB_SUFFIX, load_manifest
from .parser import Document, parse_pdf
from .versions import branch_of, version_key
from .web_notes import parse_web_notes

log = logging.getLogger(__name__)


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def revision_date(entry: dict) -> Optional[str]:
    """Date of the last revision of a PDF, from its Last-Modified header."""
    stamp = entry.get("last_modified")
    return parsedate_to_datetime(stamp).strftime("%Y-%m-%d") if stamp else None


def write_version(path: Path, version: str, document, revised: Optional[str] = None) -> None:
    """One observation per line, so that a PDF revision gives a readable git diff."""
    head = {
        "version": version,
        "branch": branch_of(version),
        "build": document.build,
        "released": document.released,
        "revised": revised,
        "pages": document.pages,
        "models": document.models,
        "notices": document.notices,
        "changes": document.changes,
    }
    lines = ",\n".join(
        "  " + json.dumps(observation, ensure_ascii=False)
        for observation in document.observations
    )
    body = json.dumps(head, ensure_ascii=False)[:-1]
    path.write_text(f'{body}, "observations": [\n{lines}\n]}}\n', encoding="utf-8")


def bug_sets(observations: List[dict]) -> Tuple[Set[str], Set[str]]:
    """Return the fixed and the known bug IDs of a version."""
    fixed = {o["bug_id"] for o in observations if o["status"] == "resolved"}
    known = {o["bug_id"] for o in observations if o["status"] != "resolved"}
    return fixed, known


def diff_version(version: str, before: List[dict], after: List[dict], date: str) -> List[dict]:
    """Fortinet keeps editing published notes: report the bugs a revision added."""
    old_fixed, old_known = bug_sets(before)
    new_fixed, new_known = bug_sets(after)
    entries = []
    for kind, added in (("known_added", new_known - old_known), ("fixed_added", new_fixed - old_fixed)):
        if added:
            entries.append({"date": date, "version": version, "kind": kind, "bugs": sorted(added, key=int)})
    return entries


def read_changes(path: Path) -> List[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def write_changes(path: Path, changes: List[dict]) -> None:
    changes = sorted(changes, key=lambda c: (c["date"], version_key(c["version"]), c["kind"]))
    lines = ",\n".join("  " + json.dumps(change, ensure_ascii=False) for change in changes)
    path.write_text(f"[\n{lines}\n]\n", encoding="utf-8")


def read_document(cache: Path, version: str, entry: dict) -> Optional[Document]:
    """The cached PDF of a version, or else its web notes; None when neither is cached."""
    pdf = cache / f"{version}.pdf"
    if pdf.exists():
        return parse_pdf(pdf, entry.get("pdf_url") or "")
    web = cache / f"{version}{WEB_SUFFIX}"
    if web.exists():
        return parse_web_notes(json.loads(web.read_text(encoding="utf-8")), PAGE_URL.format(version=version))
    return None


def cached_versions(cache: Path) -> List[str]:
    names = {pdf.stem for pdf in cache.glob("*.pdf")}
    names |= {web.name[:-len(WEB_SUFFIX)] for web in cache.glob(f"*{WEB_SUFFIX}")}
    return sorted(names, key=version_key)


def read_previous(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


def extract_all(manifest_path: Path, cache: Path, output: Path, changes_path: Path, report_path: Path,
                date: Optional[str] = None) -> List[str]:
    """Parse every cached document, write what is read and the processing report; return why the update stops.

    A version is published for what the code reads of it; what it does not read is in
    the report. A version that no longer parses, or loses most of its bugs, keeps its
    last reading. The update stops only when too few versions are read
    (report.PUBLISH_MINIMUM): the site then keeps its last version rather than an empty one.

    Without a change log the data is a baseline: published versions are recorded
    with their release date, as nothing tells which bugs were added when.
    """
    date = date or today()
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    previous = {d["key"]: d for d in report.load(report_path).get("documents", [])}
    baseline = not changes_path.exists()
    changes = read_changes(changes_path)
    entries: List[dict] = []
    groups: Dict[str, dict] = {}
    headings: Dict[str, Dict[str, bool]] = {}
    urls: Dict[str, str] = {}
    prose: List[dict] = []
    total = 0
    cached = set(cached_versions(cache))
    for version in sorted(set(manifest) | cached, key=version_key):
        entry = manifest.get(version, {})
        unavailable = bool(entry.get("unavailable"))
        if version not in cached and not unavailable:
            continue  # Not downloaded yet.
        total += 1
        target = output / f"{version}.json"
        old = read_previous(target)
        pdf = (cache / f"{version}.pdf").exists()
        url = entry["pdf_url"] if pdf and entry.get("pdf_url") else PAGE_URL.format(version=version)
        group = f"FortiOS {branch_of(version)}"
        findings: List[dict] = []
        document = None
        try:
            document = read_document(cache, version, entry)
        except Exception as error:  # A document that breaks the parser must not pass silently.
            findings.append(report.finding("not_understood", "parse_error", url, "", [], f"the parser stops: {error!r}"))
        if unavailable and document is not None and not pdf:
            findings.append(report.finding("left_out", "web_notes", url, "", [],
                                           "the PDF cannot be reached: the web version of the notes is read instead"))
        elif unavailable:
            findings.append(report.finding("unreachable", "http", entry.get("pdf_url") or url, "", [],
                                           "the PDF cannot be reached: its last reading stays"))
        ids = {"vendor": set(), "read": set(), "ruled": set(), "failed": set(), "unaccounted": set()}
        if document:
            findings += document.findings
            ids = document.accounting()
            places: Dict[Tuple[str, str], List[str]] = {}
            for bug in sorted(ids["unaccounted"], key=int):
                places.setdefault(document.listed[bug], []).append(bug)
            for (page, where), bugs in places.items():
                findings.append(report.finding("suspect", "unaccounted", page, where, bugs,
                                               "bug IDs the notes list that no rule of the code accounts for"))
            count = len(ids["read"])
            had = len({o["bug_id"] for o in old["observations"]}) if old else 0
            if had and not count:
                findings.append(report.finding("suspect", "lost_bugs", url, "", [], f"the notes had {had} bugs and have none now"))
            elif had and count < (1 - report.DROP_LIMIT) * had:
                findings.append(report.finding("suspect", "drop", url, "", [], f"{count} bugs read, {had} before"))
            headings[version] = document.headings
            if document.prose:
                prose.append({"key": version, "title": f"FortiOS {version}", "page": url, "count": len(document.prose),
                              "ids": sorted(document.prose, key=int)[:report.EXAMPLES]})
        urls[version] = url
        keep = document is None or any(f["rule"] in ("lost_bugs", "drop") for f in findings)
        if document and not keep:
            if old is None or baseline:
                released = document.released or (None if baseline else date)
                if released:
                    changes.append({"date": released, "version": version, "kind": "version", "bugs": []})
            else:
                changes.extend(diff_version(version, old["observations"], document.observations, date))
            write_version(target, version, document, revision_date(entry) if pdf else None)
            log.info("%s: %d observations, %d security entries left out", version, len(document.observations),
                     document.skipped_cve_rows)
        totals = groups.setdefault(group, {"name": group, "documents": 0, "vendor": 0, "read": 0, "ruled": 0, "failed": 0,
                                           "unaccounted": 0})
        totals["documents"] += 1
        for bucket in ("vendor", "read", "ruled", "failed", "unaccounted"):
            totals[bucket] += len(ids[bucket])
        if report.status_of(findings) != "read":
            kept = (old.get("revised") or "—") if keep and old else None
            entries.append(report.document(version, group, f"FortiOS {version}", url, findings, ids, previous.get(version), kept))
    for found in entries:
        if found["status"] in report.TO_FIX:
            log.warning("%s: %s %s", found["key"], found["status"], ", ".join(sorted({f["rule"] for f in found["findings"]})))
    order = sorted(groups.values(), key=lambda g: version_key(g["name"].split()[-1]), reverse=True)
    summary = report.build(report_path, entries, total, order, report.unused_sections(headings, urls), prose)
    publication = summary["publication"]
    if not publication["published"]:
        return [f"only {publication['read_share']:.0%} of the versions read, under {publication['minimum']:.0%}: "
                "the site keeps its last version"]
    write_changes(changes_path, changes)
    return []
