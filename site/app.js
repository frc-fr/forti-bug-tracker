"use strict";

const PAGE_SIZE = 100;
const KNOWN_LABELS = { k: t("known.k"), n: t("known.n"), e: t("known.e"), r: t("status.fixed") };
const STATUSES = {
  affected: t("status.affected"),
  potential: t("status.potential"),
  fixed: t("status.fixed"),
  unknown: t("status.unknown"),
};
const SCOPES = {
  all: { label: t("scope.all"), tone: "all" },
  supported: { label: t("scope.supported"), tone: "fixed" },
  ended: { label: t("scope.ended"), tone: "unknown" },
};
// Riskiest first: what an upgrade brings or leaves matters more than what it fixes.
const UPGRADE_GROUPS = {
  all: { label: t("group.all"), tone: "all" },
  defaults: { label: t("group.defaults"), tone: "change" },
  introduced: { label: t("group.introduced"), tone: "affected" },
  remaining: { label: t("group.remaining"), tone: "potential" },
  gained: { label: t("group.gained"), tone: "fixed" },
  cli: { label: t("group.cli"), tone: "change" },
  gui: { label: t("group.gui"), tone: "change" },
  table: { label: t("group.table"), tone: "change" },
};
const CHANGE_GROUPS = ["defaults", "cli", "gui", "table"];

const $ = (id) => document.getElementById(id);
const defaultFilters = () => ({
  query: "", version: "", from: "", model: "", category: "",
  hidden: new Set(["unknown"]), group: "all", scope: "all",
});
const state = { view: "bugs", shown: PAGE_SIZE, hardware: "all", reading: false, ...defaultFilters() };
let versions = [];
let models = [];
let categories = [];
let bugs = [];
let changes = [];
let lifecycles = [];
let recommended = { models: {} };
let lifecycle = { source: null, branches: {} };
let annotations = {};
let versionAnnotations = {};
let optionsModel = "";
let notices = {};
let copiedTable = () => [];
let updated = "";
let schedule = null;
let searchTimer;
const combos = {};

const escapeHtml = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const formatNumber = (n) => n.toLocaleString(locale);
const formatDate = (iso) => iso.split("-").reverse().join("/");
const formatMonth = (month) => new Date(`${month}-01T12:00:00`).toLocaleDateString(locale, { month: "long", year: "numeric" });

/** Text field that filters a list of options as you type. */
class Combobox {
  constructor(root, onChange) {
    this.onChange = onChange;
    this.options = [];
    this.current = "";
    this.visible = [];
    this.active = -1;
    this.input = document.createElement("input");
    this.input.id = `${root.id}-input`;
    this.input.type = "text";
    this.input.autocomplete = "off";
    this.input.spellcheck = false;
    this.input.setAttribute("role", "combobox");
    this.input.setAttribute("aria-autocomplete", "list");
    this.input.setAttribute("aria-expanded", "false");
    this.input.setAttribute("aria-controls", `${root.id}-list`);
    this.list = document.createElement("ul");
    this.list.id = `${root.id}-list`;
    this.list.className = "combo-list";
    this.list.setAttribute("role", "listbox");
    this.list.hidden = true;
    root.append(this.input, this.list);

    this.input.addEventListener("focus", () => { this.open(""); this.input.select(); });
    this.input.addEventListener("click", () => {
      if (this.list.hidden) this.open("");
      // Deferred: a click on selected text collapses the selection after this event.
      setTimeout(() => {
        if (this.input.value === this.label()) this.input.select();
      });
    });
    this.input.addEventListener("input", () => this.open(this.input.value));
    this.input.addEventListener("blur", () => this.close());
    this.input.addEventListener("keydown", (event) => this.onKey(event));
    // mousedown, not click: the field must not lose focus before the choice is made.
    this.list.addEventListener("mousedown", (event) => {
      event.preventDefault();
      const option = event.target.closest("[data-index]");
      if (option) this.choose(this.visible[Number(option.dataset.index)]);
    });
  }

  setOptions(options) {
    this.options = options;
    this.value = this.current;
  }

  get value() {
    return this.current;
  }

  set value(value) {
    this.current = value;
    this.input.value = this.label();
  }

  label() {
    const option = this.options.find((entry) => entry.value === this.current);
    return option ? option.label : "";
  }

  open(text) {
    const terms = text.toLowerCase().split(/\s+/).filter(Boolean);
    this.visible = this.options.filter((option) => {
      const label = option.label.toLowerCase();
      return terms.every((term) => label.includes(term));
    });
    const selected = this.visible.findIndex((option) => option.value === this.current);
    this.active = terms.length ? 0 : Math.max(selected, 0);
    this.renderList();
    this.list.hidden = false;
    this.input.setAttribute("aria-expanded", "true");
    this.scrollToActive();
  }

  close() {
    this.list.hidden = true;
    this.input.setAttribute("aria-expanded", "false");
    this.input.removeAttribute("aria-activedescendant");
    this.value = this.current;
    // Still focused after Escape or a choice: typing must replace the label.
    if (document.activeElement === this.input) this.input.select();
  }

  choose(option) {
    const changed = option.value !== this.current;
    this.current = option.value;
    this.close();
    if (changed) this.onChange(option.value);
  }

  onKey(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (this.list.hidden) {
        this.open("");
      } else if (this.visible.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        this.active = (this.active + step + this.visible.length) % this.visible.length;
        this.renderList();
        this.scrollToActive();
      }
    } else if (event.key === "Enter" && !this.list.hidden) {
      event.preventDefault();
      if (this.visible[this.active]) this.choose(this.visible[this.active]);
    } else if (event.key === "Escape") {
      this.close();
    }
  }

  renderList() {
    let group = null;
    const items = [];
    this.visible.forEach((option, index) => {
      const tone = option.tone ? ` ${option.tone}` : "";
      if (option.group && option.group !== group) {
        group = option.group;
        items.push(`<li class="combo-group${tone}" role="presentation">${escapeHtml(group)}</li>`);
      }
      const classes = `combo-option${tone}${index === this.active ? " active" : ""}`;
      items.push(`<li id="${this.list.id}-${index}" class="${classes}" role="option" data-index="${index}" aria-selected="${option.value === this.current}">${escapeHtml(option.label)}</li>`);
    });
    this.list.innerHTML = items.join("") || `<li class="combo-empty">${t("filter.noResult")}</li>`;
  }

  scrollToActive() {
    const option = this.list.querySelector(".active");
    if (!option) return;
    option.scrollIntoView({ block: "nearest" });
    this.input.setAttribute("aria-activedescendant", option.id);
  }
}

function hydrate(row) {
  const [id, category, description, workaround, cores, families, asics, events] = row;
  const fixes = new Map();
  for (const [version, status] of events) {
    const branch = versions[version].branch;
    if (status === "r" && !fixes.has(branch)) fixes.set(branch, version);
  }
  const notes = annotations[id] || [];
  const added = notes.map((note) => `${note.label} ${note.text}`).join(" ");
  const text = `${description} ${workaround || ""} ${added}`.toLowerCase();
  const supported = supportedBranches(events, versions);
  return { id, category, description, workaround, cores, families, asics, events, fixes, notes, text, supported };
}

/** The branch filter only makes sense on a search across all the versions. */
function scopeApplies() {
  return state.view === "bugs" && !state.version && Object.keys(lifecycle.branches).length > 0;
}

function versionIndex(value) {
  return value === "" ? -1 : versions.findIndex((entry) => entry.v === value);
}

function compute() {
  const terms = searchTerms(state.query);
  const version = versionIndex(state.version);
  const from = versionIndex(state.from);
  const upgrade = state.view === "upgrade" && version >= 0 && from >= 0;
  const scoped = scopeApplies();
  const category = state.category === "" ? -1 : Number(state.category);
  const counts = {};
  const rows = [];

  if (state.view === "upgrade" && !upgrade) return { rows, counts };
  const found = upgrade ? versionChanges(versions, from, version) : [];
  const changed = new Set(found.map((change) => change.id));
  if (category < 0) {
    for (const change of found) {
      if (!terms.every((term) => change.text.toLowerCase().includes(term) || term === change.id)) continue;
      counts[change.chapter] = (counts[change.chapter] || 0) + 1;
      counts.all = (counts.all || 0) + 1;
      if (state.group === "all" || state.group === change.chapter) rows.push({ change, group: change.chapter });
    }
  }
  for (const bug of bugs) {
    if (category >= 0 && bug.category !== category) continue;
    if (changed.has(bug.id)) continue;
    if (!matchesTerms(bug, terms)) continue;
    const hardware = hardwareMatch(bug, state.model);
    if (!hardware) continue;

    if (scoped) {
      const scope = bug.supported.length ? "supported" : "ended";
      counts[scope] = (counts[scope] || 0) + 1;
      counts.all = (counts.all || 0) + 1;
      if (state.scope !== "all" && scope !== state.scope) continue;
    }
    const status = version >= 0 ? statusAt(bug, version, versions) : null;
    if (upgrade) {
      const group = upgradeGroup(bug, from, version, versions);
      if (!group) continue;
      counts[group] = (counts[group] || 0) + 1;
      counts.all = (counts.all || 0) + 1;
      if (state.group !== "all" && group !== state.group) continue;
      rows.push({ bug, status, hardware, group });
      continue;
    } else if (status) {
      counts[status.key] = (counts[status.key] || 0) + 1;
      if (state.hidden.has(status.key)) continue;
    }
    rows.push({ bug, status, hardware });
  }
  const risk = Object.keys(UPGRADE_GROUPS);
  const cited = (row) => (row.hardware === "cited" ? 0 : 1);
  const ended = (row) => (scoped && !row.bug.supported.length ? 1 : 0);
  rows.sort((a, b) => risk.indexOf(a.group) - risk.indexOf(b.group) || (state.model ? cited(a) - cited(b) : 0) || ended(a) - ended(b));
  return { rows, counts };
}

function officialLink(entry, page, label) {
  return `<a href="${escapeHtml(officialUrl(entry, page))}" target="_blank" rel="noopener">${label}</a>`;
}

function highlight(text, terms) {
  const words = terms.filter((term) => !/^\d{5,7}$/.test(term)).map(escapeRegExp);
  const safe = escapeHtml(text);
  if (!words.length) return safe;
  return safe.replace(new RegExp(`(${words.map((w) => escapeHtml(w)).join("|")})`, "gi"), "<mark>$1</mark>");
}

function fixesLabel(bug) {
  const entries = [...bug.fixes.entries()].reverse().map(([, version]) => versions[version].v);
  return entries.length ? t("bug.fixedIn", { versions: entries.join(", ") }) : t("bug.noFix");
}

function hardwareTags(bug, hardware) {
  const tags = [
    ...bug.cores,
    ...bug.families.map((family) => (family === "VM" ? "VM" : t("bug.series", { family }))),
  ].map((name) => `<span class="tag hw">${escapeHtml(name)}</span>`);
  bug.asics.forEach((asic) => tags.push(`<span class="tag" title="${t("bug.asic")}">${escapeHtml(asic)}</span>`));
  if (hardware === "generic") tags.push(`<span class="tag">${t("bug.generic")}</span>`);
  return tags.join("");
}

/** First mention of a bug per branch: Fortinet does not publish where it was introduced. */
function renderAppearance(bug) {
  const first = new Map();
  for (const [version, status] of bug.events) {
    const branch = versions[version].branch;
    if (status !== "r" && !first.has(branch)) first.set(branch, [version, status]);
  }
  if (!first.size) {
    return `<p>${t("bug.neverKnown")}</p>`;
  }
  const lines = [...first].reverse().map(([branch, [version, status]]) => {
    const key = { n: "bug.firstNew", e: "bug.firstExisting", k: "bug.firstKnown" }[status];
    const text = t(key, { version: versions[version].v });
    return `<dt>${escapeHtml(branch)}</dt><dd>${escapeHtml(text)}</dd>`;
  });
  return `<dl class="history">${lines.join("")}</dl>
    <p class="note">${t("bug.appearanceNote")}</p>`;
}

function renderHistory(bug) {
  const lines = [...bug.events].reverse().map(([version, status, page]) => {
    const entry = versions[version];
    const label = KNOWN_LABELS[status];
    const link = officialLink(entry, page, t(entry.pdf ? "bug.officialPage" : "version.official", { page }));
    return `<dt>${escapeHtml(entry.v)}</dt><dd>${label}, ${link}</dd>`;
  });
  return `<dl class="history">${lines.join("")}</dl>`;
}

function renderNotes(bug, terms) {
  return bug.notes.map((note) => `<h3>${escapeHtml(note.label)}</h3>
    <p>${highlight(note.text, terms)} <a href="${escapeHtml(note.url)}" target="_blank" rel="noopener">${t("bug.article")}</a></p>`).join("");
}

function statusDetail(detail) {
  return detail ? `<span>${escapeHtml(t(`detail.${detail.id}`, detail))}</span>` : "";
}

function supportTag(bug) {
  if (!scopeApplies()) return "";
  return bug.supported.length
    ? `<span class="tag supported">${t("bug.supported", { branches: escapeHtml(bug.supported.join(", ")) })}</span>`
    : `<span class="tag">${t("scope.ended")}</span>`;
}

/** A change has a summary and a link: only a note from an article gives it something to unfold. */
function renderChange({ chapter, id, text, page, entry }, terms) {
  const notes = annotations[id] || [];
  const link = officialLink(entry, page, typeof page === "number" ? t("change.page", { version: escapeHtml(entry.v), page }) : escapeHtml(entry.v));
  const head = `<span class="bug-id">${id}</span>
    <span class="bug-text">${highlight(text, terms)}</span>
    <span class="bug-meta"><span class="badge change">${t(`change.${chapter}`)}</span>${link}${notes.map((note) => `<span class="badge potential">${escapeHtml(note.label)}</span>`).join("")}</span>`;
  return notes.length
    ? `<details class="bug"><summary>${head}</summary><div class="bug-detail">${renderNotes({ notes }, terms)}</div></details>`
    : `<div class="bug"><div class="bug-row">${head}</div></div>`;
}

function renderBug({ bug, status, hardware, group, change }, terms) {
  if (change) return renderChange(change, terms);
  const badge = group
    ? `<span class="badge ${UPGRADE_GROUPS[group].tone}">${UPGRADE_GROUPS[group].label}</span>`
    : status
      ? `<span class="badge ${status.key}">${STATUSES[status.key]}</span>${statusDetail(status.detail)}`
      : "";
  const workaround = bug.workaround
    ? `<h3>${t("bug.workaround")}</h3><p>${highlight(bug.workaround, terms)}</p>`
    : "";
  return `<details class="bug" data-id="${bug.id}">
    <summary>
      <span class="bug-id">${bug.id}</span>
      <span class="bug-text">${highlight(bug.description, terms)}</span>
      <span class="bug-meta">${badge}<span>${escapeHtml(categories[bug.category])}</span><span>${escapeHtml(fixesLabel(bug))}</span>${bug.notes.map((note) => `<span class="badge fixed">${escapeHtml(note.label)}</span>`).join("")}${supportTag(bug)}${hardwareTags(bug, hardware)}</span>
    </summary>
    <div class="bug-detail">${renderNotes(bug, terms)}<h3>${t("bug.appearance")}</h3>${renderAppearance(bug)}${workaround}<h3>${t("bug.history")}</h3>${renderHistory(bug)}</div>
  </details>`;
}

function tile(data, key, label, tone, count, pressed) {
  return `<button type="button" class="summary-card ${tone}" data-${data}="${key}" aria-pressed="${pressed}"><strong>${formatNumber(count || 0)}</strong><span>${label}</span></button>`;
}

function renderChips(counts) {
  const version = versionIndex(state.version);
  if (state.view === "upgrade") {
    const compared = version >= 0 && versionIndex(state.from) >= 0;
    $("chips").innerHTML = compared
      ? Object.entries(UPGRADE_GROUPS)
        // No count on notes whose chapter cannot be read: zero would claim there is no change.
        .filter(([key]) => !CHANGE_GROUPS.includes(key) || counts[key] || state.group === key)
        // The order of the tiles helps finding one; the list keeps the riskiest first.
        .sort(([a, { label: first }], [b, { label: second }]) => (b === "all") - (a === "all") || first.localeCompare(second, locale))
        .map(([key, { label, tone }]) => tile("group", key, label, tone, counts[key], state.group === key)).join("")
      : "";
  } else if (scopeApplies()) {
    $("chips").innerHTML = Object.entries(SCOPES).map(([key, { label, tone }]) => tile("scope", key, label, tone, counts[key], state.scope === key)).join("");
  } else if (version >= 0) {
    $("chips").innerHTML = Object.entries(STATUSES).map(([key, label]) => tile("status", key, label, key, counts[key], !state.hidden.has(key))).join("");
  } else {
    $("chips").innerHTML = "";
  }
}

function renderNotices() {
  const notices = [];
  const selected = [versionIndex(state.version), state.view === "upgrade" ? versionIndex(state.from) : -1];
  for (const index of selected) {
    if (index >= 0 && versions[index].unavailable) {
      notices.push(t("notice.unavailable", { version: versions[index].v }));
    }
  }
  for (const index of selected) {
    if (index >= 0 && versions[index].web) notices.push(t("notice.web", { version: versions[index].v }));
  }
  const version = selected[0];
  if (version >= 0 && state.model && !versions[version].unavailable) {
    const position = models.indexOf(state.model);
    if (!versions[version].models.includes(position)) {
      notices.push(t("notice.notListed", { model: state.model, version: versions[version].v }));
    }
  }
  if (state.view === "upgrade" && versionIndex(state.from) >= 0 && version >= 0 && versionIndex(state.from) >= version) {
    notices.push(t("notice.order"));
  }
  const articles = versionNotes(versionAnnotations, state.version, searchTerms(state.query), versions.map((entry) => entry.v)).map((note) =>
    `<details class="notice"><summary>${escapeHtml(t("notice.article", note))}</summary><p>${escapeHtml(note.text)} <a href="${escapeHtml(note.url)}" target="_blank" rel="noopener">${t("bug.article")}</a></p></details>`);
  $("notices").innerHTML = notices.map((text) => `<p class="notice">${escapeHtml(text)}</p>`).join("") + articles.join("");
}

function supportBadge(support) {
  if (!Object.keys(lifecycle.branches).length) return "";
  if (!support.support && support.supported) return "";
  const date = support.support && formatDate(support.support);
  const [tone, text] = !support.support ? ["unknown", t("support.ended")]
    : support.supported ? ["fixed", t("support.until", { date })] : ["unknown", t("support.endedOn", { date })];
  return `<a class="badge ${tone}" href="${escapeHtml(lifecycle.source)}" target="_blank" rel="noopener">${text}</a>`;
}

/** Shortcuts to the latest version of each supported branch. */
function renderSupport() {
  const latest = new Map(versions.filter((entry) => !entry.unavailable).map((entry) => [entry.branch, entry]));
  const branches = [...latest.values()].filter((entry) => entry.support.supported).reverse();
  const shown = ["bugs", "upgrade"].includes(state.view) && Object.keys(lifecycle.branches).length > 0;
  $("support").hidden = !shown;
  if (!shown) return;
  const links = branches.map((entry) => {
    const params = stateParams();
    params.set("version", entry.v);
    const date = entry.support.support ? `<small>${t("support.date", { date: formatDate(entry.support.support) })}</small>` : "";
    const current = entry.v === state.version ? ' aria-current="true"' : "";
    return `<a class="support-branch" href="#${escapeHtml(params.toString())}"${current}><strong>${escapeHtml(entry.v)}</strong>${date}</a>`;
  });
  $("support").innerHTML = `<h2>${t("support.title")}</h2><div class="support-list">${links.join("")}</div>
    <p class="muted">${t("support.note", { url: escapeHtml(lifecycle.source) })}</p>`;
}

function renderVersionInfo() {
  const entry = versions[versionIndex(state.version)];
  const parts = [];
  if (entry && !entry.unavailable) {
    parts.push(`FortiOS ${escapeHtml(entry.v)}`);
    if (entry.build) parts.push(officialLink(entry, entry.pages.build, `build ${escapeHtml(entry.build)}`));
    if (entry.released) parts.push(officialLink(entry, entry.pages.changes, t("version.released", { date: formatDate(entry.released) })));
    if (entry.revised) parts.push(officialLink(entry, entry.pages.changes, t("version.revised", { date: formatDate(entry.revised) })));
    const support = supportBadge(entry.support);
    if (support) parts.push(support);
    parts.push(officialLink(entry, entry.pages.changes, t("version.official")));
  }
  $("version-info").innerHTML = parts.map((part) => `<span>${part}</span>`).join("");
}

function noticeItem(notice) {
  const entry = versions.find((candidate) => candidate.v === notice.version);
  const url = typeof notice.reference === "number" && entry.pdf
    ? `${entry.pdf}#page=${notice.reference}`
    : typeof notice.reference === "string" ? `https://docs.fortinet.com${notice.reference}` : entry.page;
  const label = notice.title || `FortiOS ${notice.version}`;
  const version = notice.title ? ` <span class="muted">${escapeHtml(notice.version)}</span>` : "";
  return `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>${version}</li>`;
}

function renderUpgradeNotices() {
  const from = versionIndex(state.from);
  const to = versionIndex(state.version);
  const items = (state.view === "upgrade" && from >= 0 && to >= 0 ? upgradeNotices(notices, versions, from, to) : [])
    // A chapter read line by line is in the list; one without bug numbers can only be linked.
    .filter((item) => !versions[versionIndex(item.version)].changes.some(([chapter]) => chapter === item.chapter));
  if (!items.length) {
    $("upgrade-notices").innerHTML = "";
    return;
  }
  const fresh = items.filter((item) => item.fresh);
  const chapters = ["upgrade", "special", "defaults", "cli", "gui", "table"].map((chapter) => {
    const list = fresh.filter((item) => item.chapter === chapter);
    return list.length ? `<section><h3>${t(`chapter.${chapter}`)}</h3><ul>${list.map(noticeItem).join("")}</ul></section>` : "";
  }).join("");
  const others = items.filter((item) => !item.fresh);
  const repeated = others.length
    ? `<details><summary>${t("reading.repeated", { count: others.length, version: escapeHtml(state.from) })}</summary><ul>${others.map(noticeItem).join("")}</ul></details>`
    : "";
  $("upgrade-notices").innerHTML = `<details class="reading"${state.reading ? " open" : ""}><summary>${t("reading.title", { count: fresh.length })}</summary>
    <p class="muted">${t("reading.help", { branch: escapeHtml(versions[to].branch) })}</p><div class="reading-chapters">${chapters}</div>${repeated}</details>`;
}

function renderRecommendation() {
  const entry = recommended.models[state.model];
  if (!entry) {
    $("recommendation").innerHTML = "";
    return;
  }
  const parts = [t("advice.main", { model: escapeHtml(state.model), release: escapeHtml(entry.release) })];
  if (state.version !== entry.release) {
    const params = stateParams();
    params.set("version", entry.release);
    parts.push(`<a href="#${escapeHtml(params.toString())}">${t("advice.view")}</a>`);
  }
  if (entry.ended) parts.push(t("advice.ended"));
  parts.push(`<a href="${escapeHtml(recommended.source)}" target="_blank" rel="noopener">${t("advice.source", { month: formatMonth(recommended.as_of) })}</a>`);
  $("recommendation").innerHTML = parts.map((part) => `<span>${part}</span>`).join("");
}

/** Versions holding the most recent value of a date field, newest version first. */
function latestBy(field) {
  const dated = versions.filter((entry) => entry[field]);
  const date = dated.reduce((latest, entry) => (entry[field] > latest ? entry[field] : latest), "");
  return { date, entries: dated.filter((entry) => entry[field] === date).reverse() };
}

function newsCard(title, date, releases) {
  const links = releases.map((release) => `<a href="#version=${escapeHtml(release)}">${escapeHtml(release)}</a>`);
  return `<section class="news-card"><h2>${title}</h2><strong>${date}</strong><p>FortiOS ${links.join(", ")}</p></section>`;
}

function latestCard(title, field) {
  const { date, entries } = latestBy(field);
  return newsCard(title, formatDate(date), entries.map((entry) => entry.v));
}

function pdfLine(version) {
  const entry = versions.find((candidate) => candidate.v === version);
  if (!entry || !entry.pdf || !entry.revised) return "";
  return `<p class="news-pdf version-info"><span>${t("news.revised", { date: formatDate(entry.revised) })}</span> ${officialLink(entry, entry.pages.changes, t("version.official"))}</p>`;
}

function bugTable(rows) {
  const header = ["copy.bug", "copy.status", "copy.category", "copy.description", "copy.workaround", "copy.fix"].map((key) => t(key));
  return [header, ...rows.map(({ bug, status, group, change }) => (change ? [
    change.id, UPGRADE_GROUPS[group].label, "", change.text, "", "",
  ] : [
    bug.id,
    group ? UPGRADE_GROUPS[group].label : status ? STATUSES[status.key] : "",
    categories[bug.category],
    bug.description,
    bug.workaround,
    fixesLabel(bug),
  ]))];
}

function hardwareTable(entries) {
  const header = ["model", "first", "last", "status", "release", "support"].map((key) => t(`hardware.${key}`));
  return [header, ...entries.map((entry) => {
    const advice = recommended.models[entry.model];
    return [
      entry.model, entry.first, entry.last,
      entry.current ? t("hardware.current") : t("hardware.stoppedAfter", { branch: entry.branch }),
      advice ? advice.release : "",
      advice ? t(advice.ended ? "hardware.ended" : "hardware.ongoing") : "",
    ];
  })];
}

/** The Clipboard API needs HTTPS: a local preview over HTTP falls back on the old command. */
async function copyText(text) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const field = document.createElement("textarea");
  field.value = text;
  document.body.append(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

function renderHardware() {
  const terms = searchTerms($("hardware-query").value);
  const matching = lifecycles.filter(({ model }) => terms.every((term) => model.toLowerCase().includes(term)));
  const counts = {
    all: matching.length,
    current: matching.filter((entry) => entry.current).length,
    stopped: matching.filter((entry) => !entry.current).length,
  };
  const labels = {
    all: [t("hardware.all"), "all"],
    current: [t("hardware.current"), "fixed"],
    stopped: [t("hardware.stopped"), "potential"],
  };
  $("chips").innerHTML = Object.entries(labels)
    .map(([key, [label, tone]]) => tile("hardware", key, label, tone, counts[key], state.hardware === key)).join("");

  const listed = matching
    .filter((entry) => state.hardware === "all" || entry.current === (state.hardware === "current"))
    .sort((a, b) => a.model.localeCompare(b.model, "fr", { numeric: true }));
  copiedTable = () => hardwareTable(listed);
  $("copy").hidden = !listed.length;
  $("copy").textContent = t("list.copy");
  const rows = listed
    .map((entry) => {
      const badge = entry.current
        ? `<span class="badge fixed">${t("hardware.current")}</span>`
        : `<span class="badge potential">${t("hardware.stoppedAfter", { branch: escapeHtml(entry.branch) })}</span>`;
      const advice = recommended.models[entry.model];
      const support = !advice ? "—" : advice.ended
        ? `<span class="badge potential">${t("hardware.ended")}</span>`
        : `<span class="badge fixed">${t("hardware.ongoing")}</span>`;
      const release = advice
        ? `<a href="#${new URLSearchParams({ version: advice.release, model: entry.model })}">${escapeHtml(advice.release)}</a>`
        : "—";
      return `<tr><th scope="row"><a href="#model=${escapeHtml(entry.model)}">${escapeHtml(entry.model)}</a></th>
        <td>${escapeHtml(entry.first)}</td><td>${escapeHtml(entry.last)}</td><td>${badge}</td><td>${release}</td><td>${support}</td></tr>`;
    });
  $("results").innerHTML = rows.length
    ? `<table class="hardware-table"><thead><tr>${["model", "first", "last", "status", "release", "support"].map((key) => `<th scope="col">${t(`hardware.${key}`)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`
    : "";
  $("count").textContent = rows.length ? "" : t("hardware.none");
  $("more").hidden = true;
  $("notices").innerHTML = "";
  $("version-info").innerHTML = "";
  $("recommendation").innerHTML = "";
  $("upgrade-notices").innerHTML = "";
  $("news-summary").innerHTML = "";
  writeHash();
}

function renderNews() {
  const advised = currentRecommendations(recommended.models);
  $("news-summary").innerHTML = latestCard(t("news.latestRelease"), "released")
    + latestCard(t("news.latestPdf"), "revised")
    + (advised.length ? newsCard(t("news.recommended"), formatMonth(recommended.as_of), advised) : "");
  const byId = new Map(bugs.map((bug) => [bug.id, bug]));
  const entries = changes.map((change) => {
    const items = change.bugs.slice(0, 20).map((id) => {
      const bug = byId.get(id);
      return `<li><a href="#query=${id}">${id}</a> ${bug ? escapeHtml(bug.description) : ""}</li>`;
    });
    const hidden = change.bugs.length - items.length;
    if (hidden > 0) items.push(`<li class="muted">${t("news.more", { count: formatNumber(hidden) })}</li>`);
    return `<article class="news">
      <time datetime="${change.date}">${formatDate(change.date)}</time>
      <h2><a href="#version=${escapeHtml(change.version)}">${escapeHtml(change.titles[language])}</a></h2>
      ${pdfLine(change.version)}
      ${items.length ? `<ul>${items.join("")}</ul>` : ""}
    </article>`;
  });
  $("results").innerHTML = entries.join("");
  $("count").textContent = "";
  $("more").hidden = true;
  $("copy").hidden = true;
  $("chips").innerHTML = "";
  $("notices").innerHTML = "";
  $("version-info").innerHTML = "";
  $("recommendation").innerHTML = "";
  $("upgrade-notices").innerHTML = "";
  writeHash();
}

function render() {
  renderSupport();
  if (state.view === "news") {
    renderNews();
    return;
  }
  if (state.view === "hardware") {
    renderHardware();
    return;
  }
  $("news-summary").innerHTML = "";
  const { rows, counts } = compute();
  const terms = searchTerms(state.query);
  renderChips(counts);
  renderNotices();
  renderVersionInfo();
  renderRecommendation();
  renderUpgradeNotices();

  const waiting = state.view === "upgrade" && (!state.from || !state.version);
  $("count").textContent = waiting
    ? t("count.choose")
    : state.view === "upgrade" && CHANGE_GROUPS.includes(state.group) ? t("count.changes", { label: UPGRADE_GROUPS[state.group].label, count: formatNumber(rows.length) })
      : rows.length > state.shown ? t("count.partial", { count: formatNumber(rows.length), shown: formatNumber(state.shown) })
      : rows.length > 1 ? t("count.many", { count: formatNumber(rows.length) }) : t(rows.length ? "count.one" : "count.none");
  $("results").innerHTML = rows.slice(0, state.shown).map((row) => renderBug(row, terms)).join("");
  $("more").hidden = rows.length <= state.shown;
  $("more").textContent = t("list.more", { count: formatNumber(rows.length - state.shown) });
  copiedTable = () => bugTable(rows);
  $("copy").hidden = !rows.length;
  $("copy").textContent = t("list.copy");
  writeHash();
}

function stateParams(shown = language) {
  const params = new URLSearchParams();
  if (shown === "en") params.set("lang", "en");
  if (state.view !== "bugs") params.set("view", state.view);
  for (const key of ["query", "version", "from", "model", "category"]) {
    if (state[key]) params.set(key, state[key]);
  }
  if (state.scope !== "all") params.set("scope", state.scope);
  return params;
}

function writeHash() {
  history.replaceState(null, "", `#${stateParams()}`);
}

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  state.view = ["upgrade", "news", "hardware"].includes(params.get("view")) ? params.get("view") : "bugs";
  for (const key of ["query", "version", "from", "model", "category"]) {
    state[key] = params.get(key) || "";
  }
  state.scope = ["supported", "ended"].includes(params.get("scope")) ? params.get("scope") : "all";
}

function syncControls() {
  const upgrade = state.view === "upgrade";
  const news = state.view === "news";
  $("tab-bugs").setAttribute("aria-pressed", String(state.view === "bugs"));
  $("tab-upgrade").setAttribute("aria-pressed", String(upgrade));
  const hardware = state.view === "hardware";
  $("tab-news").setAttribute("aria-pressed", String(news));
  $("tab-hardware").setAttribute("aria-pressed", String(hardware));
  $("filters").hidden = news || hardware;
  $("legend").hidden = news || hardware;
  $("hardware-tools").hidden = !hardware;
  $("subscribe").hidden = !news;
  $("field-from").hidden = !upgrade;
  $("version-label").textContent = t(upgrade ? "filter.target" : "filter.version");
  $("view-help").textContent = t(`help.${state.view}`);
  if (state.model !== optionsModel) {
    optionsModel = state.model;
    combos.version.setOptions(versionOptions(t("filter.allVersions")));
    combos.from.setOptions(versionOptions(t("filter.choose")));
  }
  for (const key of ["version", "from", "model", "category"]) combos[key].value = state[key];
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent = t(theme === "dark" ? "theme.light" : "theme.dark");
}

function branchLabel({ branch, support }) {
  if (!Object.keys(lifecycle.branches).length) return `FortiOS ${branch}`;
  if (!support.supported) return t("option.branchEnded", { branch });
  return support.support ? t("option.branchUntil", { branch, date: formatDate(support.support) }) : `FortiOS ${branch}`;
}

function versionOptions(placeholder) {
  const advice = recommended.models[state.model];
  const options = [...versions].reverse().map((entry) => {
    const suffix = entry.unavailable ? t("option.unavailable") : entry.build ? ` (build ${entry.build})` : "";
    const mark = advice && advice.release === entry.v ? t("option.recommended") : "";
    return { value: entry.v, label: `${entry.v}${suffix}${mark}`, group: branchLabel(entry), tone: entry.support.supported ? "" : "ended" };
  });
  return [{ value: "", label: placeholder }, ...options];
}

function modelLabel(model) {
  const lifecycle = lifecycles.find((entry) => entry.model === model);
  return lifecycle.current ? model : t("option.until", { model, branch: lifecycle.branch });
}

function modelOptions() {
  const families = [["FG", "FortiGate"], ["FWF", "FortiWiFi"], ["FGR", "FortiGate Rugged"], ["FFW", "FortiFirewall"], ["FOS", "FortiOS VM"]];
  const options = families.flatMap(([prefix, group]) => models
    .filter((model) => model.startsWith(`${prefix}-`))
    .sort((a, b) => a.localeCompare(b, "fr", { numeric: true }))
    .map((model) => ({ value: model, label: modelLabel(model), group })));
  return [{ value: "", label: t("filter.allModels") }, ...options];
}

function update(changes) {
  clearTimeout(searchTimer);
  // The field is the reference: a filter can change while a search is debounced.
  Object.assign(state, { query: $("query").value }, changes, { shown: PAGE_SIZE });
  syncControls();
  render();
}

function bindEvents() {
  $("query").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => update({}), 150);
  });
  $("theme").addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("theme", theme);
    applyTheme(theme);
  });
  $("reset").addEventListener("click", () => {
    $("query").value = "";
    update(defaultFilters());
  });
  $("language").addEventListener("click", () => {
    const next = language === "fr" ? "en" : "fr";
    localStorage.setItem("language", next);
    history.replaceState(null, "", `#${stateParams(next)}`);
    location.reload();
  });
  $("tab-bugs").addEventListener("click", () => update({ view: "bugs" }));
  $("tab-upgrade").addEventListener("click", () => update({ view: "upgrade" }));
  $("tab-news").addEventListener("click", () => update({ view: "news" }));
  $("tab-hardware").addEventListener("click", () => update({ view: "hardware" }));
  $("hardware-query").addEventListener("input", () => render());
  $("more").addEventListener("click", () => {
    state.shown = Infinity;
    render();
  });
  $("chips").addEventListener("click", (event) => {
    const chip = event.target.closest("button");
    if (!chip) return;
    if (chip.dataset.hardware) {
      update({ hardware: chip.dataset.hardware });
    } else if (chip.dataset.scope) {
      update({ scope: chip.dataset.scope });
    } else if (chip.dataset.group) {
      update({ group: chip.dataset.group });
    } else {
      const key = chip.dataset.status;
      if (state.hidden.has(key)) state.hidden.delete(key); else state.hidden.add(key);
      update({});
    }
  });
  // toggle does not bubble, and a new render must not fold what the reader opened.
  $("upgrade-notices").addEventListener("toggle", (event) => {
    if (event.target.classList.contains("reading")) state.reading = event.target.open;
  }, true);
  $("copy").addEventListener("click", async () => {
    const table = copiedTable();
    await copyText(tableText(table));
    $("copy").textContent = t("list.copied", { count: formatNumber(table.length - 1) });
  });
  $("to-top").addEventListener("click", () => window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
  window.addEventListener("scroll", () => {
    $("to-top").hidden = window.scrollY < 500;
  }, { passive: true });
  // Selecting text in a bug must not fold or unfold it.
  $("results").addEventListener("click", (event) => {
    if (event.target.closest("summary") && !getSelection().isCollapsed) event.preventDefault();
  });
  window.addEventListener("hashchange", () => {
    readHash();
    $("query").value = state.query;
    update({});
  });
}

function localizedNotes(annotations) {
  return Object.fromEntries(Object.entries(annotations).map(([key, notes]) =>
    [key, notes.map((note) => ({ ...note, label: note.label[language], text: note.text[language] }))]));
}

async function start() {
  const [index, data, news, chapters] = await Promise.all(
    ["data/index.json", "data/bugs.json", "data/changes.json", "data/notices.json"].map((url) => fetch(url).then((response) => {
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return response.json();
    })),
  );
  lifecycle = index.lifecycle;
  const today = new Date().toISOString().slice(0, 10);
  versions = index.versions.map((entry) => ({ ...entry, support: branchSupport(entry.branch, lifecycle.branches, today) }));
  models = index.models;
  categories = data.categories;
  changes = news;
  notices = chapters;
  updated = index.updated;
  schedule = index.schedule;
  recommended = index.recommended;
  annotations = localizedNotes(data.annotations.bugs);
  versionAnnotations = localizedNotes(data.annotations.versions);
  bugs = data.bugs.map(hydrate);
  lifecycles = modelLifecycles(models, versions);

  for (const key of ["version", "from", "model", "category"]) {
    combos[key] = new Combobox($(key), (value) => update({ [key]: value }));
  }
  combos.version.setOptions(versionOptions(t("filter.allVersions")));
  combos.from.setOptions(versionOptions(t("filter.choose")));
  combos.model.setOptions(modelOptions());
  combos.category.setOptions([
    { value: "", label: t("filter.allCategories") },
    ...categories.map((name, index) => ({ value: String(index), label: name })),
  ]);

  if (recommended.as_of) {
    $("recommended-note").innerHTML = t("hardware.recommended", { url: escapeHtml(recommended.source), month: formatMonth(recommended.as_of) });
  }
  const latest = [...versions].reverse().find((entry) => !entry.unavailable);
  $("scope").textContent = t("page.scopeRange", { first: versions[0].branch, last: latest.branch });
  $("stats").textContent = t("page.stats", { bugs: formatNumber(bugs.length), versions: formatNumber(versions.length), latest: latest.v });
  const moment = new Date(updated);
  $("updated").textContent = t("page.updated", {
    date: moment.toLocaleDateString(locale),
    time: moment.toLocaleTimeString(locale, { timeStyle: "short" }),
  });
  if (schedule) $("schedule").textContent = t("page.schedule", { crons: schedule.crons.join(t("page.and")), zone: schedule.timezone });
  readHash();
  $("query").value = state.query;
  bindEvents();
  update({});
}

applyTheme(document.documentElement.dataset.theme);
start().catch((error) => {
  $("stats").textContent = t("page.failed");
  console.error(error);
});
