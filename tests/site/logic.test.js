// Run with: node --test tests/site/logic.test.js
const assert = require("node:assert");
const test = require("node:test");
const { versionChanges, officialUrl, branchSupport, supportedBranches, tableText, upgradeNotices, versionNotes, currentRecommendations, modelLifecycles, statusAt, hardwareMatch, searchTerms, matchesTerms, upgradeGroup } = require("../../site/logic.js");

const versions = [
  { v: "7.4.1", branch: "7.4" }, { v: "7.4.2", branch: "7.4" },
  { v: "7.6.0", branch: "7.6" }, { v: "7.6.1", branch: "7.6" }, { v: "7.6.2", branch: "7.6" }, { v: "7.6.3", branch: "7.6" },
];
const at = (events, index) => statusAt({ events }, index, versions).key;

test("known in the version: affected", () => {
  assert.equal(at([[3, "k", 1]], 3), "affected");
  assert.equal(at([[3, "e", 1]], 3), "affected");
});

test("fixed in or before the version of the branch", () => {
  assert.equal(at([[3, "r", 1]], 3), "fixed");
  assert.equal(at([[3, "r", 1]], 5), "fixed");
});

test("a known issue wins over a fix listed in the same version", () => {
  assert.equal(at([[3, "r", 1], [3, "k", 1]], 3), "affected");
});

test("a fix of the same version is kept for the next ones", () => {
  assert.equal(at([[3, "r", 1], [3, "k", 1]], 4), "fixed");
});

test("fixed later on the branch: potentially affected", () => {
  assert.equal(at([[4, "r", 1]], 2), "potential");
});

test("present later as an existing issue: potentially affected", () => {
  assert.equal(at([[4, "e", 1]], 2), "potential");
});

test("reported as new later: unknown, even if fixed afterwards", () => {
  assert.equal(at([[4, "n", 1]], 2), "unknown");
  assert.equal(at([[4, "n", 1], [5, "r", 1]], 2), "unknown");
  assert.equal(at([[4, "n", 1]], 4), "affected");
});

test("no mention on the branch: unknown, a fix elsewhere does not count", () => {
  assert.equal(at([[1, "r", 1]], 3), "unknown");
});

test("dropped from the notes without a fix: unknown", () => {
  const status = statusAt({ events: [[2, "k", 1]] }, 4, versions);
  assert.equal(status.key, "unknown");
  assert.deepEqual(status.detail, { id: "dropped", version: "7.6.0" });
});

test("the hardware filter is inclusive", () => {
  const generic = { cores: [], families: [] };
  assert.equal(hardwareMatch(generic, "FG-100F"), "generic");
  assert.equal(hardwareMatch({ cores: ["100F"], families: [] }, "FG-100F"), "cited");
  assert.equal(hardwareMatch({ cores: ["60F"], families: [] }, "FWF-60F-3G4G"), "cited");
  assert.equal(hardwareMatch({ cores: ["400F"], families: [] }, "FG-100F"), null);
  assert.equal(hardwareMatch({ cores: [], families: ["7000"] }, "FG-7121F"), "cited");
  assert.equal(hardwareMatch({ cores: [], families: ["VM"] }, "FG-VM64"), "cited");
  assert.equal(hardwareMatch({ cores: [], families: ["VM"] }, "FG-100F"), null);
  assert.equal(hardwareMatch(generic, ""), "all");
});

test("every search term must match, a number is a bug ID", () => {
  const bug = { id: "1306049", text: "ipsec phase2 rekey drops traffic" };
  assert.deepEqual(searchTerms("Rekey, Ipsec"), ["rekey", "ipsec"]);
  assert.ok(matchesTerms(bug, searchTerms("Rekey, Ipsec")));
  assert.ok(!matchesTerms(bug, searchTerms("Rekey, BGP")));
  assert.ok(matchesTerms(bug, searchTerms("1306049")));
  assert.ok(!matchesTerms(bug, searchTerms("130604")));
});

test("comparing two versions", () => {
  assert.equal(upgradeGroup({ events: [[4, "r", 1]] }, 3, 4, versions), "gained");
  assert.equal(upgradeGroup({ events: [[4, "n", 1]] }, 3, 4, versions), "introduced");
  assert.equal(upgradeGroup({ events: [[3, "k", 1], [4, "e", 1]] }, 3, 4, versions), "remaining");
  assert.equal(upgradeGroup({ events: [[2, "r", 1]] }, 3, 4, versions), null);
});

test("model lifecycle from the supported lists", () => {
  const listed = [
    { v: "7.4.1", branch: "7.4", models: [0, 1] }, { v: "7.4.2", branch: "7.4", models: [0, 1] },
    { v: "7.4.3", branch: "7.4", models: [] },
    { v: "7.6.0", branch: "7.6", models: [1] },
  ];
  assert.deepEqual(modelLifecycles(["FG-60E", "FG-60F"], listed), [
    { model: "FG-60E", first: "7.4.1", last: "7.4.2", branch: "7.4", current: false },
    { model: "FG-60F", first: "7.4.1", last: "7.6.0", branch: "7.6", current: true },
  ]);
});

test("recommendations: only supported models, the most common release first", () => {
  const recommended = {
    a: { release: "7.4.13", ended: false },
    b: { release: "7.6.8", ended: false },
    c: { release: "7.6.8", ended: false },
    d: { release: "6.2.17", ended: true },
  };
  assert.deepStrictEqual(currentRecommendations(recommended), ["7.6.8", "7.4.13"]);
});

test("version notes: shown for the version or found by all the keywords", () => {
  const notes = { "7.6.8": [{ label: "GUI", text: "Fabric reset" }] };
  const order = ["7.4.9", "7.6.7", "7.6.8", "8.0.0"];
  assert.strictEqual(versionNotes(notes, "7.6.8", [], order).length, 1);
  assert.strictEqual(versionNotes(notes, "7.6.7", [], order).length, 0);
  assert.strictEqual(versionNotes(notes, "8.0.0", [], order).length, 0);
  assert.strictEqual(versionNotes(notes, "", ["fabric", "gui"], order)[0].version, "7.6.8");
  assert.strictEqual(versionNotes(notes, "", ["fabric", "ipsec"], order).length, 0);
});

test("version notes: a lasting change also shows on the later versions", () => {
  const notes = { "7.6.5": [{ label: "DH", text: "Default", and_later: true }] };
  const order = ["7.4.9", "7.6.4", "7.6.5", "7.6.8", "8.0.0"];
  assert.strictEqual(versionNotes(notes, "7.6.8", [], order).length, 1);
  assert.strictEqual(versionNotes(notes, "8.0.0", [], order).length, 1);
  assert.strictEqual(versionNotes(notes, "7.6.4", [], order).length, 0);
  assert.strictEqual(versionNotes(notes, "", [], order).length, 0);
});

test("upgrade notices: the target branch only, fresh when the current version lacks them", () => {
  const list = [{ v: "7.4.1", branch: "7.4" }, { v: "7.4.2", branch: "7.4" }, { v: "7.6.0", branch: "7.6" }, { v: "7.6.1", branch: "7.6" }];
  const notices = {
    "7.4.1": [["upgrade", "Common", 1]],
    "7.4.2": [["upgrade", "Skipped branch", 2]],
    "7.6.0": [["upgrade", "Common", 3], ["upgrade", "Only here", 4], ["table", null, 5]],
    "7.6.1": [["upgrade", "common", 6], ["table", null, 7]],
  };
  const items = upgradeNotices(notices, list, 0, 3);
  assert.deepStrictEqual(items.map(({ title, version, fresh }) => [title, version, fresh]), [
    ["common", "7.6.1", false], ["Only here", "7.6.0", true], [null, "7.6.0", true], [null, "7.6.1", true],
  ]);
  assert.deepStrictEqual(upgradeNotices(notices, list, 3, 0), []);
});

test("copied table: one line per row, cells free of tabs and line breaks", () => {
  assert.equal(tableText([["Bug", "Text"], ["1", "a\tb\nc"], ["2", null]]), "Bug\tText\n1\ta b c\n2\t");
});

const branches = { "7.2": { engineering: "2025-03-31", support: "2026-09-30" }, "7.6": { engineering: "2028-07-25", support: "2030-01-25" } };

test("a branch is supported up to its last day", () => {
  assert.equal(branchSupport("7.2", branches, "2026-09-30").supported, true);
  assert.equal(branchSupport("7.2", branches, "2026-10-01").supported, false);
});

test("a branch older than every listed one is out of support", () => {
  assert.equal(branchSupport("5.6", branches, "2026-11-07").supported, false);
});

test("a branch newer than the listed ones is supported, without date", () => {
  const support = branchSupport("8.2", branches, "2026-11-07");
  assert.equal(support.supported, true);
  assert.equal(support.support, undefined);
});

test("the numbers of a branch compare as numbers", () => {
  assert.equal(branchSupport("7.10", branches, "2026-11-07").supported, true);
});

test("a bug lists its supported branches, newest first", () => {
  const dated = [
    { branch: "7.2", support: { supported: false } },
    { branch: "7.4", support: { supported: true } },
    { branch: "7.6", support: { supported: true } },
  ];
  assert.deepEqual(supportedBranches([[0, "r", 1], [1, "k", 1], [2, "k", 1], [2, "r", 1]], dated), ["7.6", "7.4"]);
  assert.deepEqual(supportedBranches([[0, "r", 1]], dated), []);
});

test("an official link opens the page of the PDF holding the fact", () => {
  const entry = { pdf: "https://example.test/notes.pdf", page: "https://example.test/notes" };
  assert.equal(officialUrl(entry, 5), "https://example.test/notes.pdf#page=5");
  assert.equal(officialUrl(entry, undefined), "https://example.test/notes.pdf");
  assert.equal(officialUrl({ ...entry, pdf: null }, 5), "https://example.test/notes");
  assert.equal(officialUrl({ ...entry, pdf: null }, "/document/chapter"), "https://docs.fortinet.com/document/chapter");
});

test("only the changes the current version does not have are listed", () => {
  const notes = [
    { v: "7.4.1", branch: "7.4", changes: [["defaults", "100", "Old", 5]] },
    { v: "7.4.2", branch: "7.4", changes: [["defaults", "100", "Old", 5], ["defaults", "200", "New", 6]] },
    { v: "7.4.3", branch: "7.4", changes: [["defaults", "100", "Old", 5], ["defaults", "200", "New", 6]] },
  ];
  assert.deepEqual(versionChanges(notes, 0, 2).map(({ id, entry }) => [id, entry.v]), [["200", "7.4.2"]]);
  assert.deepEqual(versionChanges(notes, 2, 0), []);
});

test("a change reworded under the same number is listed again", () => {
  const notes = [
    { v: "7.6.5", branch: "7.6", changes: [["defaults", "300", "No longer adjusted", 5]] },
    { v: "7.6.8", branch: "7.6", changes: [["defaults", "300", "Adjusted again", 5]] },
  ];
  assert.deepEqual(versionChanges(notes, 0, 1).map(({ text }) => text), ["Adjusted again"]);
});

test("a change of another branch is not on the way to the target", () => {
  const notes = [
    { v: "7.4.1", branch: "7.4", changes: [] },
    { v: "7.4.2", branch: "7.4", changes: [["defaults", "100", "Other branch", 5]] },
    { v: "7.6.0", branch: "7.6", changes: [["defaults", "200", "Target branch", 6]] },
  ];
  assert.deepEqual(versionChanges(notes, 0, 2).map(({ id }) => id), ["200"]);
});

test("the same number in two chapters gives two changes", () => {
  const notes = [
    { v: "7.4.1", branch: "7.4", changes: [] },
    { v: "7.4.2", branch: "7.4", changes: [["cli", "100", "Command", 5], ["gui", "100", "Page", 6]] },
  ];
  assert.deepEqual(versionChanges(notes, 0, 1).map(({ chapter }) => chapter), ["cli", "gui"]);
});
