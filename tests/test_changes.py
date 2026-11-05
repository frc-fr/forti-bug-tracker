import json
from xml.etree import ElementTree

from fortibugs.build import build_bugs, load_annotations, workflow_schedule
from fortibugs.extract import diff_version, read_changes, write_changes
from fortibugs.feed import ATOM, build_feed, latest_changes, titles_of


def observation(bug_id, status="known_new"):
    return {"bug_id": bug_id, "status": status, "category": "GUI", "description": f"Bug {bug_id}",
            "workaround": None, "page": 1}


def test_revision_reports_only_the_added_bugs():
    before = [observation("100000"), observation("200000", "resolved")]
    after = before + [observation("300000"), observation("400000", "resolved")]
    assert diff_version("7.6.7", before, after, "2026-11-05") == [
        {"date": "2026-11-05", "version": "7.6.7", "kind": "known_added", "bugs": ["300000"]},
        {"date": "2026-11-05", "version": "7.6.7", "kind": "fixed_added", "bugs": ["400000"]},
    ]


def test_same_bugs_with_new_wording_is_not_a_change():
    reworded = [dict(observation("100000"), description="Reworded")]
    assert diff_version("7.6.7", [observation("100000")], reworded, "2026-11-05") == []


def test_known_issue_turned_into_a_fix_is_reported():
    entries = diff_version("7.6.7", [observation("100000")], [observation("100000", "resolved")], "2026-11-05")
    assert [(e["kind"], e["bugs"]) for e in entries] == [("fixed_added", ["100000"])]


def test_change_log_round_trip(tmp_path):
    path = tmp_path / "changes.json"
    changes = [
        {"date": "2026-11-05", "version": "7.6.10", "kind": "version", "bugs": []},
        {"date": "2026-11-05", "version": "7.6.9", "kind": "version", "bugs": []},
    ]
    write_changes(path, changes)
    assert [c["version"] for c in read_changes(path)] == ["7.6.9", "7.6.10"]


def test_titles():
    documents = {"7.6.8": {"observations": [observation("1", "resolved"), observation("2"), observation("3")]}}
    change = {"date": "2026-10-22", "version": "7.6.8", "kind": "version", "bugs": []}
    assert titles_of(change, documents) == {"fr": "FortiOS 7.6.8 publiée : 1 bug corrigé, 2 bugs connus",
                                             "en": "FortiOS 7.6.8 released: 1 fixed bug, 2 known bugs"}
    change = {"date": "2026-10-23", "version": "7.6.8", "kind": "known_added", "bugs": ["2", "3"]}
    assert titles_of(change, documents)["en"] == "FortiOS 7.6.8: 2 known bugs added to the notes"


def test_feed_is_valid_atom_with_stable_ids():
    changes = latest_changes([
        {"date": "2026-10-22", "version": "7.6.8", "kind": "version", "bugs": []},
        {"date": "2026-10-30", "version": "7.6.8", "kind": "known_added", "bugs": ["100000"]},
    ], {"7.6.8": {"observations": []}})
    xml = build_feed(changes, {"100000": "Crash <b> & reboot"}, "https://example.org/")
    feed = ElementTree.fromstring(xml)
    ns = {"a": ATOM}
    assert feed.find("a:updated", ns).text == "2026-10-30T00:00:00Z"
    entries = feed.findall("a:entry", ns)
    assert len(entries) == 2
    assert entries[0].find("a:id", ns).text.endswith("/2026-10-30/7.6.8/known_added")
    content = entries[0].find("a:content", ns).text
    assert "Crash &lt;b&gt; &amp; reboot" in content
    assert "https://example.org/#query=100000" in content


def test_a_version_listing_a_bug_as_fixed_and_known_keeps_both_facts():
    documents = {"7.6.8": {"observations": [observation("100000", "resolved"), observation("100000", "known")]}}
    index = {"versions": [{"v": "7.6.8"}], "models": []}
    row = build_bugs(documents, index)["bugs"][0]
    assert sorted(event[1] for event in row[7]) == ["k", "r"]


def test_annotations_keep_known_bugs_only(tmp_path):
    path = tmp_path / "annotations.json"
    note = [{"label": "Note"}]
    path.write_text(json.dumps({"bugs": {"100000": note, "999999": note}, "versions": {"7.6.8": note, "9.9.9": note}}))
    index = {"versions": [{"v": "7.6.8"}]}
    assert load_annotations(path, {"bugs": [["100000"]]}, index) == {"bugs": {"100000": note}, "versions": {"7.6.8": note}}
    assert load_annotations(tmp_path / "missing.json", {"bugs": []}, index) == {"bugs": {}, "versions": {}}


def test_schedule_comes_from_the_workflow(tmp_path):
    path = tmp_path / "update.yml"
    path.write_text('on:\n  schedule:\n    - cron: "1 2 * * *"\n      timezone: "Europe/Paris"\n    - cron: "3 4 * * *"\n')
    assert workflow_schedule(path) == {"crons": ["1 2 * * *", "3 4 * * *"], "timezone": "Europe/Paris"}
    path.write_text('on:\n  schedule:\n    - cron: "1 2 * * *"\n')
    assert workflow_schedule(path)["timezone"] == "UTC"
    assert workflow_schedule(tmp_path / "missing.yml") is None
