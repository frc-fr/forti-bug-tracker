"""Discover the Release Notes PDFs and keep sources/manifest.json up to date.

docs.fortinet.com is only read one page per version, without query strings and
with the Crawl-delay of its robots.txt. Known versions are then tracked with a
HEAD on the S3 object: Fortinet regenerates the PDFs in place, so the ETag is
what tells us a document changed.
"""
import hashlib
import json
import logging
import re
import time
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests

from .versions import branch_of, version_key
from .web_notes import CHAPTERS, chapter_urls

log = logging.getLogger(__name__)

DOCS_URL = "https://docs.fortinet.com"
PAGE_URL = DOCS_URL + "/document/fortigate/{version}/fortios-release-notes"
USER_AGENT = "forti-bug-tracker/0.1 (+https://github.com/frc-fr/forti-bug-tracker)"
CRAWL_DELAY = 2.0
SEED_VERSION = "7.6.4"
# Fortinet revises old versions of a live branch, and only those: the age of a
# version says nothing, the last revision seen in its branch does.
ACTIVE_DAYS = 90
WEB_SUFFIX = ".web.json"

VERSION_LINK = re.compile(r"/document/fortigate/(\d+\.\d+\.\d+)/fortios-release-notes")
PDF_LINK = re.compile(r"https://fortinetweb\.s3\.amazonaws\.com/[^\"'\s<>]+?\.pdf")


class Client:
    """HTTP client that spaces out requests and retries transient failures."""

    def __init__(self, delay: float = CRAWL_DELAY, retries: int = 4):
        self.delay = delay
        self.retries = retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0

    def request(self, method: str, url: str) -> requests.Response:
        for attempt in range(self.retries):
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                response = self.session.request(method, url, timeout=60)
            except requests.RequestException as error:
                log.warning("%s %s failed: %s", method, url, error)
            else:
                if response.status_code not in (429, 500, 502, 503, 504):
                    return response
                log.warning("%s %s returned %s", method, url, response.status_code)
            time.sleep(self.delay * 2 ** (attempt + 1))
        raise RuntimeError(f"{method} {url}: giving up after {self.retries} attempts")


def load_manifest(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    return {entry["version"]: entry for entry in json.loads(path.read_text())["versions"]}


def save_manifest(path: Path, manifest: Dict[str, dict]) -> None:
    entries = [manifest[version] for version in sorted(manifest, key=version_key)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"versions": entries}, indent=2) + "\n")


def find_pdf_url(html: str, version: str) -> Optional[str]:
    """Pick the Release Notes PDF of a version page, which may link other PDFs."""
    links = list(dict.fromkeys(PDF_LINK.findall(html)))
    named = [link for link in links if version in link.rsplit("/", 1)[-1]]
    return (named or links or [None])[0]


def list_versions(client: Client, seed: str) -> List[str]:
    response = client.request("GET", PAGE_URL.format(version=seed))
    response.raise_for_status()
    return sorted(set(VERSION_LINK.findall(response.text)), key=version_key)


def discover_pdf(client: Client, version: str) -> Optional[str]:
    response = client.request("GET", PAGE_URL.format(version=version))
    if response.status_code != 200:
        log.warning("%s: page returned %s", version, response.status_code)
        return None
    return find_pdf_url(response.text, version)


def object_state(client: Client, url: str) -> Optional[dict]:
    response = client.request("HEAD", url)
    if response.status_code != 200:
        return None
    return {
        "etag": response.headers.get("ETag", "").strip('"'),
        "last_modified": response.headers.get("Last-Modified"),
        "size": int(response.headers.get("Content-Length", 0)),
    }


def active_branches(manifest: Dict[str, dict], today: date) -> Set[str]:
    """Branches with a PDF revised lately; a dormant one wakes up with its next revision."""
    cutoff = today - timedelta(days=ACTIVE_DAYS)
    return {
        entry["branch"] for entry in manifest.values()
        if entry.get("last_modified") and parsedate_to_datetime(entry["last_modified"]).date() >= cutoff
    }


def update_manifest(path: Path, client: Client, check_all: bool = True) -> Dict[str, dict]:
    """Add new versions and refresh the state of the known ones.

    New versions are always found. Without check_all, the known PDFs of dormant
    branches are left out. The manifest is saved after every new version so that
    an interrupted crawl resumes where it stopped.
    """
    manifest = load_manifest(path)
    active = active_branches(manifest, date.today())
    seed = max(manifest, key=version_key) if manifest else SEED_VERSION
    versions = sorted(set(list_versions(client, seed)) | set(manifest), key=version_key)
    log.info("%d versions listed, %d already known", len(versions), len(manifest))

    for version in versions:
        entry = manifest.get(version)
        if entry and not check_all and entry["branch"] not in active:
            continue
        state = object_state(client, entry["pdf_url"]) if entry else None
        if state is None:
            # New version, or the known URL is gone: the page has the current one.
            url = discover_pdf(client, version)
            state = object_state(client, url) if url else None
            entry = entry or {"version": version, "branch": branch_of(version)}
            manifest[version] = entry
            entry["pdf_url"] = url
            if state is None:
                # Recorded rather than skipped: the site has to show the gap.
                log.error("%s: no reachable PDF", version)
                entry["unavailable"] = True
                save_manifest(path, manifest)
                continue
        if entry.get("etag") != state["etag"]:
            log.info("%s: new revision %s", version, state["last_modified"])
        entry.update(state)
        entry.pop("unavailable", None)
        save_manifest(path, manifest)
    return manifest


def download_web_notes(manifest: Dict[str, dict], cache: Path, client: Client) -> None:
    """Keep the web chapters of the versions without PDF; a failure keeps the last copy."""
    cache.mkdir(parents=True, exist_ok=True)
    for version, entry in manifest.items():
        if not entry.get("unavailable"):
            continue
        response = client.request("GET", PAGE_URL.format(version=version))
        urls = chapter_urls(response.text, version) if response.status_code == 200 else {}
        if not all(name in urls for name in CHAPTERS):
            log.error("%s: web chapters not found", version)
            continue
        pages = {name: client.request("GET", DOCS_URL + url) for name, url in urls.items()}
        if any(page.status_code != 200 for page in pages.values()):
            log.error("%s: web chapters not reachable", version)
            continue
        target = cache / f"{version}{WEB_SUFFIX}"
        target.write_text(json.dumps({name: page.text for name, page in pages.items()}), encoding="utf-8")
        log.info("%s: web notes saved", version)


def download_pdfs(manifest: Dict[str, dict], cache: Path, client: Client) -> List[str]:
    """Fetch the PDFs missing from the cache; return the versions downloaded."""
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for version in sorted(manifest, key=version_key):
        entry = manifest[version]
        if entry.get("unavailable"):
            continue
        target = cache / f"{version}.pdf"
        stamp = cache / f"{version}.etag"
        if target.exists() and stamp.exists() and stamp.read_text() == entry["etag"]:
            entry.setdefault("sha256", hashlib.sha256(target.read_bytes()).hexdigest())
            continue
        response = client.request("GET", entry["pdf_url"])
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise RuntimeError(f"{version}: {entry['pdf_url']} is not a PDF")
        target.write_bytes(response.content)
        stamp.write_text(entry["etag"])
        entry["sha256"] = hashlib.sha256(response.content).hexdigest()
        downloaded.append(version)
        log.info("%s: downloaded %d bytes", version, len(response.content))
    return downloaded
