import re
from pathlib import Path

SITE = Path(__file__).parent.parent / "site"


def dictionary(language):
    source = (SITE / "i18n.js").read_text(encoding="utf-8")
    block = source.split(f"  {language}: {{\n", 1)[1].split("\n  },\n", 1)[0]
    return dict(re.findall(r'^    "([\w.]+)": "(.*)",$', block, re.M))


def test_both_languages_have_the_same_keys_and_placeholders():
    french, english = dictionary("fr"), dictionary("en")
    assert french.keys() == english.keys()
    for key, text in french.items():
        assert set(re.findall(r"\{\w+\}", text)) == set(re.findall(r"\{\w+\}", english[key])), key


def test_every_key_used_by_the_site_exists():
    known = dictionary("fr")
    page = (SITE / "index.html").read_text(encoding="utf-8")
    code = (SITE / "app.js").read_text(encoding="utf-8")
    used = re.findall(r'data-(?:text|html|placeholder|label)="([\w.]+)"', page) + re.findall(r'"([a-z]+\.[A-Za-z]+)"', code)
    assert [key for key in used if key not in known and not key.endswith(".js") and not key.endswith(".json")] == []
