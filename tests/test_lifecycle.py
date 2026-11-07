import json

from fortibugs.build import build_lifecycle
from fortibugs.lifecycle import MINIMUM_BRANCHES, PAGE_URL, parse_lifecycle, update_lifecycle


def payload(count=MINIMUM_BRANCHES, **changes):
    releases = [{"name": f"7.{index}", "eoasFrom": "2027-05-11", "eolFrom": "2028-11-11", **changes}
                for index in range(count)]
    return {"result": {"releases": releases}}


class Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self.content


class FakeClient:
    def __init__(self, content):
        self.content = content

    def request(self, method, url):
        return Response(self.content)


def test_parse_keeps_the_dates_of_each_branch():
    branches = parse_lifecycle(payload())
    assert branches["7.0"] == {"engineering": "2027-05-11", "support": "2028-11-11"}


def test_update_writes_the_dates(tmp_path):
    path = tmp_path / "lifecycle.json"
    update_lifecycle(path, FakeClient(payload()))
    content = json.loads(path.read_text())
    assert content["source"] == PAGE_URL
    assert len(content["branches"]) == MINIMUM_BRANCHES


def test_a_wrong_response_keeps_the_last_dates(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text("kept")
    for content in (payload(count=2), payload(eolFrom=True), {"result": {}}, None):
        update_lifecycle(path, FakeClient(content))
    assert path.read_text() == "kept"


def test_build_without_the_file_has_no_dates(tmp_path):
    assert build_lifecycle(tmp_path / "missing.json") == {"source": None, "branches": {}}
