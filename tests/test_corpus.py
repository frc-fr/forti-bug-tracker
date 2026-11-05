"""Checks on the real PDFs, when FORTIBUGS_CACHE points to the downloaded corpus."""
import os
from pathlib import Path

import pytest

from fortibugs.parser import parse_pdf

CACHE = os.environ.get("FORTIBUGS_CACHE")
PDFS = sorted(Path(CACHE).glob("*.pdf")) if CACHE else []

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not PDFS, reason="FORTIBUGS_CACHE not set"),
]


@pytest.mark.parametrize("pdf", PDFS, ids=lambda pdf: pdf.stem)
def test_release_notes(pdf):
    result = parse_pdf(pdf)
    assert result.warnings == []
    assert result.models
    assert all(o["description"] for o in result.observations)
    assert not any("CVE-" in o["description"] for o in result.observations)
