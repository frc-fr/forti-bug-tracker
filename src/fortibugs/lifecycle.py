"""Support dates of the FortiOS branches, from the endoflife.date API.

Read when the data is collected, never by the browser. This community source is not
Fortinet: a response that no longer parses must not erase the last valid dates.
"""
import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

API_URL = "https://endoflife.date/api/v1/products/fortios/"
PAGE_URL = "https://endoflife.date/fortios"
MINIMUM_BRANCHES = 5

BRANCH = re.compile(r"^\d+\.\d+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_lifecycle(payload: dict) -> dict:
    """Return the dates of each branch; raise if the response looks wrong."""
    branches = {}
    for release in payload["result"]["releases"]:
        name, engineering, support = release["name"], release["eoasFrom"], release["eolFrom"]
        if not BRANCH.match(name) or not DATE.match(str(engineering)) or not DATE.match(str(support)):
            raise ValueError(f"unexpected release: {release}")
        branches[name] = {"engineering": engineering, "support": support}
    if len(branches) < MINIMUM_BRANCHES:
        raise ValueError(f"only {len(branches)} branches in the lifecycle")
    return branches


def update_lifecycle(path: Path, client) -> None:
    """Refresh the dates; the Release Notes must not depend on this service."""
    try:
        response = client.request("GET", API_URL)
        response.raise_for_status()
        branches = parse_lifecycle(response.json())
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as error:
        log.error("support dates kept as they were: %s", error)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source": PAGE_URL, "branches": branches}, indent=2) + "\n")
