import json
from datetime import date

from fortibugs import collect


def entry(version, branch, modified):
    return {"version": version, "branch": branch, "pdf_url": f"https://example.test/{version}.pdf",
            "etag": "old", "last_modified": modified}


MANIFEST = [
    entry("7.0.1", "7.0", "Tue, 21 Jul 2026 10:00:00 GMT"),
    entry("7.6.0", "7.6", "Mon, 26 Oct 2026 10:00:00 GMT"),
    entry("7.6.1", "7.6", "Mon, 05 Jan 2026 10:00:00 GMT"),
]


def run(tmp_path, monkeypatch, check_all):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"versions": MANIFEST}))
    checked = []

    class Today(date):
        @classmethod
        def today(cls):
            return date(2026, 11, 5)

    def state(client, url):
        checked.append(url.rsplit("/", 1)[-1][:-4])
        return {"etag": "new", "last_modified": "Thu, 05 Nov 2026 10:00:00 GMT", "size": 1}

    monkeypatch.setattr(collect, "date", Today)
    monkeypatch.setattr(collect, "list_versions", lambda client, seed: ["7.0.1", "7.0.2", "7.6.0", "7.6.1"])
    monkeypatch.setattr(collect, "discover_pdf", lambda client, version: f"https://example.test/{version}.pdf")
    monkeypatch.setattr(collect, "object_state", state)
    collect.update_manifest(path, None, check_all=check_all)
    return checked


def test_a_branch_is_active_as_a_whole():
    manifest = {item["version"]: item for item in MANIFEST}
    assert collect.active_branches(manifest, date(2026, 11, 5)) == {"7.6"}
    assert collect.active_branches(manifest, date(2026, 8, 1)) == {"7.0", "7.6"}


def test_routine_run_skips_dormant_branches_but_finds_new_versions(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, False) == ["7.0.2", "7.6.0", "7.6.1"]


def test_full_run_checks_everything(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, True) == ["7.0.1", "7.0.2", "7.6.0", "7.6.1"]
