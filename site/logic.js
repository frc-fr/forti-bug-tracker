"use strict";
// What the site concludes from the notes, kept apart from the page so it can be tested.

/** Status of a bug on one version, from what the notes of its branch say. */
function statusAt(bug, index, versions) {
  const branch = versions[index].branch;
  const own = bug.events.filter(([v]) => versions[v].branch === branch);
  if (own.some(([v, status]) => v === index && status !== "r")) return { key: "affected" };

  const fixed = own.find(([v, status]) => status === "r" && v <= index);
  if (fixed) return { key: "fixed", detail: { id: "fixedSince", version: versions[fixed[0]].v } };

  // Reported as new later on: nothing suggests that this older version has it.
  if (own.length && own[0][1] === "n" && own[0][0] > index) {
    return { key: "unknown", detail: { id: "reportedNew", version: versions[own[0][0]].v } };
  }

  const fixedLater = own.find(([v, status]) => status === "r" && v > index);
  if (fixedLater) return { key: "potential", detail: { id: "fixedIn", version: versions[fixedLater[0]].v } };

  const knownLater = own.find(([v]) => v > index);
  if (knownLater) return { key: "potential", detail: { id: "knownIn", version: versions[knownLater[0]].v } };

  if (own.length) {
    const last = own[own.length - 1][0];
    return { key: "unknown", detail: { id: "dropped", version: versions[last].v } };
  }
  return { key: "unknown", detail: { id: "noMention" } };
}

function modelFamily(core) {
  if (core.startsWith("VM")) return "VM";
  const series = core.match(/^([67])\d{3}/);
  return series ? `${series[1]}000` : null;
}

/** Inclusive filter: "cited" for the selected hardware, "generic" when none is named. */
function hardwareMatch(bug, model) {
  if (!model) return "all";
  if (!bug.cores.length && !bug.families.length) return "generic";
  const core = model.split("-")[1];
  if (bug.cores.includes(core) || bug.families.includes(modelFamily(core))) return "cited";
  return null;
}

function searchTerms(query) {
  return query.toLowerCase().split(/[\s,;]+/).filter(Boolean);
}

function matchesTerms(bug, terms) {
  return terms.every((term) => (/^\d{5,7}$/.test(term) ? bug.id === term : bug.text.includes(term)));
}

function upgradeGroup(bug, from, to, versions) {
  const before = statusAt(bug, from, versions).key;
  const after = statusAt(bug, to, versions).key;
  if (after === "fixed" && before !== "fixed") return "gained";
  if (after === "affected") return before === "affected" ? "remaining" : "introduced";
  return null;
}

/** First and last version listing each model, and whether the newest branch still does. */
function modelLifecycles(models, versions) {
  const listed = versions.filter((entry) => entry.models.length);
  const newest = listed[listed.length - 1].branch;
  return models.map((model, position) => {
    const having = listed.filter((entry) => entry.models.includes(position));
    const last = having[having.length - 1];
    return { model, first: having[0].v, last: last.v, branch: last.branch, current: last.branch === newest };
  });
}

/** Releases recommended for the models still under engineering support, the most common first. */
function currentRecommendations(recommended) {
  const counts = new Map();
  for (const { release, ended } of Object.values(recommended)) {
    if (!ended) counts.set(release, (counts.get(release) || 0) + 1);
  }
  return [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a));
}

/** Notes of a version, also reached by keywords since they belong to no bug. */
function versionNotes(annotations, version, terms, order) {
  const position = order.indexOf(version);
  return Object.entries(annotations).flatMap(([name, notes]) => notes
    .filter((note) => {
      const text = `${note.label} ${note.text}`.toLowerCase();
      return name === version
        || (note.and_later && position >= order.indexOf(name))
        || (terms.length > 0 && terms.every((term) => text.includes(term)));
    })
    .map((note) => ({ ...note, version: name })));
}

/** Notices of the target branch up to the target, "fresh" when the current version lacks them. */
function upgradeNotices(notices, versions, from, to) {
  if (from >= to) return [];
  const known = new Set((notices[versions[from].v] || []).map(([, title]) => title && title.toLowerCase()));
  const found = new Map();
  versions.slice(from + 1, to + 1).filter((entry) => entry.branch === versions[to].branch).forEach((entry) => {
    for (const [chapter, title, reference] of notices[entry.v] || []) {
      const key = title ? `${chapter}|${title.toLowerCase()}` : `${chapter}@${entry.v}`;
      found.set(key, { chapter, title, reference, version: entry.v, fresh: !title || !known.has(title.toLowerCase()) });
    }
  });
  return [...found.values()];
}

/** Tab-separated text, which spreadsheets and mail clients paste as a table. */
function tableText(rows) {
  return rows.map((row) => row.map((cell) => String(cell ?? "").replace(/\s+/g, " ").trim()).join("\t")).join("\n");
}

if (typeof module !== "undefined") {
  module.exports = { tableText, upgradeNotices, versionNotes, currentRecommendations, modelLifecycles, statusAt, modelFamily, hardwareMatch, searchTerms, matchesTerms, upgradeGroup };
}
