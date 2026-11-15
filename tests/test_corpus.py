"""Checks on the real PDFs of .cache/pdfs, or of FORTIBUGS_CACHE when set."""
import json
import os
import re
from pathlib import Path

import pytest

from fortibugs.parser import parse_pdf

CACHE = Path(os.environ.get("FORTIBUGS_CACHE", ".cache/pdfs"))
PDFS = sorted(CACHE.glob("*.pdf"))

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not PDFS, reason="no downloaded PDF"),
]


@pytest.mark.parametrize("pdf", PDFS, ids=lambda pdf: pdf.stem)
def test_release_notes(pdf):
    result = parse_pdf(pdf)
    assert result.warnings == []
    assert result.models
    assert all(o["description"] for o in result.observations)
    assert not any("CVE-" in o["description"] for o in result.observations)


def test_words_keep_their_spaces():
    # A text engine upgrade once glued words together without any other symptom.
    pdf = next((pdf for pdf in PDFS if pdf.stem == "7.6.4"), None)
    if pdf is None:
        pytest.skip("7.6.4 not in the corpus")
    descriptions = {o["bug_id"]: o["description"] for o in parse_pdf(pdf).observations}
    assert "HW log(ps) rate" in descriptions["1143144"]


def test_no_change_summary_names_a_vulnerability():
    for path in Path("data/extracted").glob("*.json"):
        for _, bug, text, _ in json.loads(path.read_text(encoding="utf-8")).get("changes", []):
            assert not re.search(r"\bCVE|\bCWE", text), bug
