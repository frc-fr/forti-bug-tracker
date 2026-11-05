"""Describe the change log for the "Quoi de neuf" page and the Atom feed."""
import html
from typing import Dict, List
from xml.etree import ElementTree

from .versions import version_key

ATOM = "http://www.w3.org/2005/Atom"
ID_PREFIX = "tag:github.com,2026:frc-fr/forti-bug-tracker"
FEED_SIZE = 50
PAGE_SIZE = 100
LISTED_BUGS = 50


def plural(count: int, singular: str, several: str) -> str:
    return f"{count} {singular if count == 1 else several}"


def title_of(change: dict, documents: Dict[str, dict]) -> str:
    version = change["version"]
    count = len(change["bugs"])
    if change["kind"] == "known_added":
        return f"FortiOS {version} : {plural(count, 'bug connu ajouté', 'bugs connus ajoutés')} aux notes"
    if change["kind"] == "fixed_added":
        return f"FortiOS {version} : {plural(count, 'correction ajoutée', 'corrections ajoutées')} aux notes"
    observations = documents.get(version, {}).get("observations", [])
    fixed = len({o["bug_id"] for o in observations if o["status"] == "resolved"})
    known = len({o["bug_id"] for o in observations if o["status"] != "resolved"})
    return (
        f"FortiOS {version} publiée : {plural(fixed, 'bug corrigé', 'bugs corrigés')}, "
        f"{plural(known, 'bug connu', 'bugs connus')}"
    )


def latest_changes(changes: List[dict], documents: Dict[str, dict], limit: int = PAGE_SIZE) -> List[dict]:
    ordered = sorted(
        changes,
        key=lambda c: (c["date"], version_key(c["version"]), c["kind"]),
        reverse=True,
    )
    return [{**change, "title": title_of(change, documents)} for change in ordered[:limit]]


def entry_link(change: dict, base_url: str) -> str:
    return f"{base_url}#version={change['version']}"


def entry_content(change: dict, descriptions: Dict[str, str], base_url: str) -> str:
    items = [
        f'<li><a href="{base_url}#query={bug}">{bug}</a> : {html.escape(descriptions.get(bug, ""))}</li>'
        for bug in change["bugs"][:LISTED_BUGS]
    ]
    hidden = len(change["bugs"]) - len(items)
    if hidden > 0:
        items.append(f"<li>et {hidden} autres</li>")
    return f"<ul>{''.join(items)}</ul>" if items else html.escape(change["title"])


def build_feed(changes: List[dict], descriptions: Dict[str, str], base_url: str) -> bytes:
    """Atom 1.0. `changes` come from latest_changes, the most recent first."""
    ElementTree.register_namespace("", ATOM)
    feed = ElementTree.Element(f"{{{ATOM}}}feed")

    def add(parent, tag, text=None, **attributes):
        element = ElementTree.SubElement(parent, f"{{{ATOM}}}{tag}", attributes)
        element.text = text
        return element

    add(feed, "title", "FortiOS Bug Tracker : quoi de neuf")
    add(feed, "subtitle", "Nouvelles versions FortiOS et bugs ajoutés aux Release Notes publiées")
    add(feed, "id", ID_PREFIX)
    add(feed, "link", href=base_url)
    add(feed, "link", rel="self", href=f"{base_url}feed.xml")
    add(feed, "updated", f"{changes[0]['date']}T00:00:00Z" if changes else "2026-01-01T00:00:00Z")
    add(add(feed, "author"), "name", "forti-bug-tracker")
    for change in changes[:FEED_SIZE]:
        entry = add(feed, "entry")
        add(entry, "title", change["title"])
        add(entry, "id", f"{ID_PREFIX}/{change['date']}/{change['version']}/{change['kind']}")
        add(entry, "link", href=entry_link(change, base_url))
        add(entry, "updated", f"{change['date']}T00:00:00Z")
        add(entry, "content", entry_content(change, descriptions, base_url), type="html")
    return ElementTree.tostring(feed, encoding="utf-8", xml_declaration=True)
