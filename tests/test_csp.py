import re
from pathlib import Path

import pytest

SITE = Path(__file__).parent.parent / "site"
PAGES = sorted(SITE.glob("*.html"))


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_every_page_declares_the_policy_before_any_script(page):
    source = page.read_text(encoding="utf-8")
    policy = source.index('http-equiv="Content-Security-Policy"')
    assert policy < source.index("<script")
    assert "default-src 'none'" in source


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_nothing_inline_would_be_blocked(page):
    source = page.read_text(encoding="utf-8")
    assert re.findall(r"<script(?![^>]*\bsrc=)", source) == []
    assert "<style" not in source
    assert re.findall(r"\s(?:style|on[a-z]+)=", source) == []


def test_the_scripts_build_no_inline_style_or_handler():
    source = (SITE / "app.js").read_text(encoding="utf-8") + (SITE / "i18n.js").read_text(encoding="utf-8")
    assert re.findall(r"\sstyle=|\son(?:click|error|load)=", source) == []
