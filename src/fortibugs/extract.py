"""Turn the cached PDFs into data/extracted/<version>.json and log what changed."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .parser import parse_pdf
from .versions import branch_of, version_key

log = logging.getLogger(__name__)


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_version(path: Path, version: str, document) -> None:
    """One observation per line, so that a PDF revision gives a readable git diff."""
    head = {
        "version": version,
        "branch": branch_of(version),
        "build": document.build,
        "released": document.released,
        "models": document.models,
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


def extract_all(cache: Path, output: Path, changes_path: Path, date: Optional[str] = None) -> Dict[str, List[str]]:
    """Parse every cached PDF and return the warnings per version.

    Without a change log the data is a baseline: published versions are recorded
    with their release date, as nothing tells which bugs were added when.
    """
    date = date or today()
    output.mkdir(parents=True, exist_ok=True)
    baseline = not changes_path.exists()
    changes = read_changes(changes_path)
    pdfs = sorted(cache.glob("*.pdf"), key=lambda pdf: version_key(pdf.stem))
    problems = {}
    for pdf in pdfs:
        version = pdf.stem
        document = parse_pdf(pdf)
        target = output / f"{version}.json"
        previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
        if previous is None or baseline:
            released = document.released or (None if baseline else date)
            if released:
                changes.append({"date": released, "version": version, "kind": "version", "bugs": []})
        else:
            changes.extend(diff_version(version, previous["observations"], document.observations, date))
        write_version(target, version, document)
        log.info("%s: %d observations", version, len(document.observations))
        if document.warnings:
            problems[version] = document.warnings
    # A failed extraction must not leave a log describing data that is not published.
    if not problems:
        write_changes(changes_path, changes)
    return problems
