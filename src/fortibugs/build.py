"""Generate the static site: copy site/ and cross the extracted data into dist/data."""
import json
import logging
import shutil
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional

from .collect import PAGE_URL, load_manifest
from .extract import read_changes, today
from .feed import build_feed, latest_changes
from .normalize import canonical_model, hardware_tags, model_core, normalize_category
from .recommended import resolve_models
from .versions import branch_of, version_key

log = logging.getLogger(__name__)

STATUS_CODES = {"resolved": "r", "known": "k", "known_new": "n", "known_existing": "e"}


def load_extracted(directory: Path) -> Dict[str, dict]:
    documents = {}
    for path in directory.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        documents[document["version"]] = document
    return documents


def revision_date(entry: dict) -> Optional[str]:
    """Date of the last revision of a PDF, from its Last-Modified header."""
    stamp = entry.get("last_modified")
    return parsedate_to_datetime(stamp).strftime("%Y-%m-%d") if stamp else None


def build_index(documents: Dict[str, dict], manifest: Dict[str, dict]) -> dict:
    versions = sorted(set(documents) | set(manifest), key=version_key)
    models: Dict[str, List[str]] = {}
    for version in versions:
        names = documents.get(version, {}).get("models", [])
        models[version] = sorted({m for m in map(canonical_model, names) if m})
    all_models = sorted({model for names in models.values() for model in names})
    positions = {model: index for index, model in enumerate(all_models)}
    return {
        "checked": today(),
        "models": all_models,
        "versions": [
            {
                "v": version,
                "branch": branch_of(version),
                "build": documents.get(version, {}).get("build"),
                "released": documents.get(version, {}).get("released"),
                "revised": revision_date(manifest.get(version, {})),
                "pdf": manifest.get(version, {}).get("pdf_url"),
                "page": PAGE_URL.format(version=version),
                "unavailable": version not in documents,
                "models": [positions[model] for model in models[version]],
            }
            for version in versions
        ],
    }


def build_recommended(path: Path, index: dict) -> dict:
    """Recommendation per model, kept only where the notes of that release list the model."""
    if not path.exists():
        return {"as_of": None, "source": None, "models": {}}
    article = json.loads(path.read_text(encoding="utf-8"))
    resolved, unmatched = resolve_models(article["entries"], index["models"])
    for product in unmatched:
        log.warning("recommended release: no model for %s", product)
    listed = {entry["v"]: {index["models"][position] for position in entry["models"]}
              for entry in index["versions"]}
    return {
        "as_of": article["as_of"],
        "source": article["source"],
        "models": {
            model: {"release": entry["release"], "ended": entry["engineering_support_ended"]}
            for model, entry in resolved.items()
            if model in listed.get(entry["release"], ())
        },
    }


def known_annotations(annotations: Dict[str, List[dict]], known: set) -> Dict[str, List[dict]]:
    for key in set(annotations) - known:
        log.warning("annotation for an unknown bug or version: %s", key)
    return {key: notes for key, notes in annotations.items() if key in known}


def load_annotations(path: Path, bugs: dict, index: dict) -> dict:
    """Facts added by hand from Fortinet articles, which the Release Notes do not carry.

    An article without bug number is attached to a version, never to a guessed bug.
    """
    if not path.exists():
        return {"bugs": {}, "versions": {}}
    annotations = json.loads(path.read_text(encoding="utf-8"))
    return {
        "bugs": known_annotations(annotations["bugs"], {row[0] for row in bugs["bugs"]}),
        "versions": known_annotations(annotations["versions"], {entry["v"] for entry in index["versions"]}),
    }


def build_bugs(documents: Dict[str, dict], index: dict) -> dict:
    """Merge the observations per bug; the wording of the latest version wins."""
    positions = {entry["v"]: i for i, entry in enumerate(index["versions"])}
    cores = {model_core(model) for model in index["models"]}
    bugs: Dict[str, dict] = {}
    for version in sorted(documents, key=version_key):
        for observation in documents[version]["observations"]:
            bug = bugs.setdefault(observation["bug_id"], {"events": {}})
            bug["category"] = normalize_category(observation["category"])
            bug["description"] = observation["description"]
            bug["workaround"] = observation["workaround"] or bug.get("workaround")
            code = STATUS_CODES[observation["status"]]
            # A version can list a bug as both fixed and known: both facts are kept.
            bug["events"].setdefault((version, code == "r"), [positions[version], code, observation["page"]])

    categories = sorted({bug["category"] for bug in bugs.values()})
    category_positions = {name: index for index, name in enumerate(categories)}
    rows = []
    for bug_id, bug in sorted(bugs.items(), key=lambda item: -int(item[0])):
        models, families, asics = hardware_tags(bug["description"], bug["category"], cores)
        rows.append([
            bug_id,
            category_positions[bug["category"]],
            bug["description"],
            bug["workaround"],
            models,
            families,
            asics,
            sorted(bug["events"].values()),
        ])
    return {"categories": categories, "bugs": rows}


def build_site(
    extracted: Path, manifest_path: Path, changes_path: Path, recommended_path: Path,
    annotations_path: Path, sources: Path, dist: Path, base_url: str,
) -> dict:
    documents = load_extracted(extracted)
    manifest = load_manifest(manifest_path)
    index = build_index(documents, manifest)
    index["recommended"] = build_recommended(recommended_path, index)
    bugs = build_bugs(documents, index)
    bugs["annotations"] = load_annotations(annotations_path, bugs, index)
    changes = latest_changes(read_changes(changes_path), documents)
    descriptions = {row[0]: row[2] for row in bugs["bugs"]}

    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(sources, dist)
    (dist / "data").mkdir()
    for name, content in (("index.json", index), ("bugs.json", bugs), ("changes.json", changes)):
        (dist / "data" / name).write_text(
            json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    (dist / "feed.xml").write_bytes(build_feed(changes, descriptions, base_url))

    tagged = Counter(
        "model" if row[4] else "family" if row[5] else "asic" if row[6] else "generic"
        for row in bugs["bugs"]
    )
    return {
        "versions": len(index["versions"]),
        "models": len(index["models"]),
        "recommended": len(index["recommended"]["models"]),
        "categories": len(bugs["categories"]),
        "bugs": len(bugs["bugs"]),
        "tags": dict(tagged),
    }
