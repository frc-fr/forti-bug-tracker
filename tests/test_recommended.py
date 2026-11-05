import json

import pytest

from fortibugs.build import build_recommended
from fortibugs.recommended import MINIMUM_ROWS, parse_article, product_patterns, resolve_models, update_recommended


def article(rows):
    cells = "".join(
        f"<tr><td><p>{segment}</p></td><td><p>{product}</p></td><td><p>{release}</p></td><td><p>{ended}</p></td></tr>"
        for segment, product, release, ended in rows
    )
    return (
        "<p>The recommendations stated below are the latest as of October 2026, and are reviewed.</p>"
        "<table><tr><td></td><td><p>Product Details</p></td><td>Recommended Release</td>"
        f"<td>End of Engineering Support Passed (Y/N)</td></tr>{cells}</table>"
        "<p>Is 7.6.6 still recommended?</p>"
    )


def filler(count=MINIMUM_ROWS):
    return [("\xa0", f"FortiGate-{index}F", "7.6.8", "N") for index in range(100, 100 + count)]


class Page:
    def __init__(self, text, status=200):
        self.text = text
        self.status = status

    def raise_for_status(self):
        if self.status != 200:
            raise OSError(self.status)


class FakeClient:
    def __init__(self, response):
        self.response = response

    def request(self, method, url):
        return self.response


def test_parse_keeps_the_rows_and_carries_the_segment():
    content = parse_article(article([("Low End", "FortiGate-30E", "6.2.17", "Y"), *filler()]))
    assert content["as_of"] == "2026-10"
    assert content["entries"][0] == {"segment": "Low End", "product": "FortiGate-30E", "release": "6.2.17",
                                     "engineering_support_ended": True}
    assert content["entries"][1]["segment"] == "Low End"
    assert content["entries"][1]["engineering_support_ended"] is False


@pytest.mark.parametrize("page", [
    "<p>Nothing here</p>",
    article(filler(MINIMUM_ROWS - 1)),
    article([("", "FortiGate-30E", "see notes", "Y"), *filler()]),
])
def test_parse_refuses_a_page_that_looks_wrong(page):
    with pytest.raises(ValueError):
        parse_article(page)


@pytest.mark.parametrize("response", [Page("<p>Changed layout</p>"), Page("", 403)])
def test_failed_update_keeps_the_last_table(tmp_path, response):
    path = tmp_path / "recommended.json"
    path.write_text("previous")
    update_recommended(path, FakeClient(response))
    assert path.read_text() == "previous"


def test_update_writes_the_table(tmp_path):
    path = tmp_path / "recommended.json"
    update_recommended(path, FakeClient(Page(article(filler()))))
    assert len(json.loads(path.read_text())["entries"]) == MINIMUM_ROWS


@pytest.mark.parametrize("product, expected", [
    ("FortiGate-60F", ["FG-60F"]),
    ("FortiWifi-60E", ["FWF-60E"]),
    ("FortiGateRugged-60F-3G4G", ["FGR-60F-3G4G"]),
    ("FortiGate-200G/201G", ["FG-200G", "FG-201G"]),
    ("FortiGate-50G/51G and variants", ["FG-50G", "FG-50G-5G", "FG-51G-SFP-POE"]),
    ("FortiGate-6000F / 7000E / 7000F", ["FG-6300F", "FG-7030E", "FG-7121F"]),
    ("FortiGate-VM64 -all versions", ["FG-VM64", "FG-VM64-KVM"]),
    ("FortiGate-280D", ["FG-280D-POE"]),
    ("FortiGate-400E-BYPASS", ["FG-400E-BP"]),
])
def test_rows_reach_our_model_names(product, expected):
    models = ["FG-60F", "FG-60F-POE", "FWF-60E", "FGR-60F-3G4G", "FG-200G", "FG-201G", "FG-50G", "FG-50G-5G",
              "FG-51G-SFP-POE", "FWF-50G", "FG-6300F", "FG-7030E", "FG-7121F", "FG-3000F", "FG-VM64", "FG-VM64-KVM",
              "FOS-VM64", "FG-280D-POE", "FG-400E-BP"]
    resolved, unmatched = resolve_models([{"product": product}], models)
    assert sorted(resolved) == sorted(expected)
    assert not unmatched


def test_a_row_without_model_is_reported():
    assert resolve_models([{"product": "FortiGate-9999Z"}], ["FG-60F"])[1] == ["FortiGate-9999Z"]
    assert product_patterns("FortiSwitch-124F") == []


def test_build_drops_a_model_the_notes_of_that_release_do_not_list(tmp_path):
    path = tmp_path / "recommended.json"
    path.write_text(json.dumps({"as_of": "2026-10", "source": "https://example.test", "entries": [
        {"product": "FortiGate-VM64 -all versions", "release": "7.6.8", "engineering_support_ended": False},
    ]}))
    index = {"models": ["FG-VM64", "FG-VM64-NPU"], "versions": [{"v": "5.6.14", "models": [1]}, {"v": "7.6.8", "models": [0]}]}
    assert build_recommended(path, index)["models"] == {"FG-VM64": {"release": "7.6.8", "ended": False}}


def test_build_without_the_file_has_no_recommendation(tmp_path):
    assert build_recommended(tmp_path / "missing.json", {"models": [], "versions": []})["models"] == {}
