"use strict";

const PAGE_SIZE = 100;
const KNOWN_LABELS = { k: "Connu", n: "Connu (nouveau)", e: "Connu (existant)", r: "Corrigé" };
const STATUSES = {
  affected: "Affecté",
  potential: "Potentiellement affecté",
  fixed: "Corrigé",
  unknown: "Inconnu",
};
const UPGRADE_GROUPS = {
  gained: "Corrigés par la mise à niveau",
  introduced: "Nouveaux bugs connus",
  remaining: "Toujours présents",
};

const $ = (id) => document.getElementById(id);
const defaultFilters = () => ({
  query: "", version: "", from: "", model: "", category: "",
  hidden: new Set(["unknown"]), group: "gained",
});
const state = { view: "bugs", shown: PAGE_SIZE, hardware: "all", ...defaultFilters() };
let versions = [];
let models = [];
let categories = [];
let bugs = [];
let changes = [];
let lifecycles = [];
let recommended = { models: {} };
let annotations = {};
let versionAnnotations = {};
let optionsModel = "";
let checked = "";
let searchTimer;
const combos = {};

const escapeHtml = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const formatNumber = (n) => n.toLocaleString("fr-FR");
const formatDate = (iso) => iso.split("-").reverse().join("/");
const formatMonth = (month) => new Date(`${month}-01T12:00:00`).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });

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
      if (option.group && option.group !== group) {
        group = option.group;
        items.push(`<li class="combo-group" role="presentation">${escapeHtml(group)}</li>`);
      }
      const classes = index === this.active ? "combo-option active" : "combo-option";
      items.push(`<li id="${this.list.id}-${index}" class="${classes}" role="option" data-index="${index}" aria-selected="${option.value === this.current}">${escapeHtml(option.label)}</li>`);
    });
    this.list.innerHTML = items.join("") || '<li class="combo-empty">Aucun résultat</li>';
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
  return { id, category, description, workaround, cores, families, asics, events, fixes, notes, text };
}

function versionIndex(value) {
  return value === "" ? -1 : versions.findIndex((entry) => entry.v === value);
}

function compute() {
  const terms = searchTerms(state.query);
  const version = versionIndex(state.version);
  const from = versionIndex(state.from);
  const upgrade = state.view === "upgrade" && version >= 0 && from >= 0;
  const category = state.category === "" ? -1 : Number(state.category);
  const counts = {};
  const rows = [];

  if (state.view === "upgrade" && !upgrade) return { rows, counts };
  for (const bug of bugs) {
    if (category >= 0 && bug.category !== category) continue;
    if (!matchesTerms(bug, terms)) continue;
    const hardware = hardwareMatch(bug, state.model);
    if (!hardware) continue;

    const status = version >= 0 ? statusAt(bug, version, versions) : null;
    if (upgrade) {
      const group = upgradeGroup(bug, from, version, versions);
      if (!group) continue;
      counts[group] = (counts[group] || 0) + 1;
      if (group !== state.group) continue;
    } else if (status) {
      counts[status.key] = (counts[status.key] || 0) + 1;
      if (state.hidden.has(status.key)) continue;
    }
    rows.push({ bug, status, hardware });
  }
  if (state.model) rows.sort((a, b) => (a.hardware === "cited" ? 0 : 1) - (b.hardware === "cited" ? 0 : 1));
  return { rows, counts };
}

function highlight(text, terms) {
  const words = terms.filter((term) => !/^\d{5,7}$/.test(term)).map(escapeRegExp);
  const safe = escapeHtml(text);
  if (!words.length) return safe;
  return safe.replace(new RegExp(`(${words.map((w) => escapeHtml(w)).join("|")})`, "gi"), "<mark>$1</mark>");
}

function fixesLabel(bug) {
  const entries = [...bug.fixes.entries()].reverse().map(([, version]) => versions[version].v);
  return entries.length ? `Corrigé en ${entries.join(", ")}` : "Aucun correctif dans les notes";
}

function hardwareTags(bug, hardware) {
  const tags = [
    ...bug.cores,
    ...bug.families.map((family) => (family === "VM" ? "VM" : `Série ${family}`)),
  ].map((name) => `<span class="tag hw">${escapeHtml(name)}</span>`);
  bug.asics.forEach((asic) => tags.push(`<span class="tag" title="ASIC à vérifier pour votre modèle">${escapeHtml(asic)}</span>`));
  if (hardware === "generic") tags.push('<span class="tag">Générique</span>');
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
    return "<p>Non publiée par Fortinet. Ce bug n'a jamais figuré dans les Known issues : les notes indiquent seulement sa correction.</p>";
  }
  const lines = [...first].reverse().map(([branch, [version, status]]) => {
    const name = versions[version].v;
    const text = {
      n: `Identifié en ${name}, nouveau bug connu de cette version`,
      e: `Déjà présent en ${name}, identifié dans une version antérieure`,
      k: `Mentionné pour la première fois en ${name}`,
    }[status];
    return `<dt>${escapeHtml(branch)}</dt><dd>${escapeHtml(text)}</dd>`;
  });
  return `<dl class="history">${lines.join("")}</dl>
    <p class="note">Première mention dans les notes de chaque branche. Fortinet ne publie pas la version d'introduction : le bug peut être plus ancien.</p>`;
}

function renderHistory(bug) {
  const lines = [...bug.events].reverse().map(([version, status, page]) => {
    const entry = versions[version];
    const label = KNOWN_LABELS[status];
    const link = entry.pdf ? `<a href="${escapeHtml(entry.pdf)}#page=${page}" target="_blank" rel="noopener">note officielle, p. ${page}</a>` : "";
    return `<dt>${escapeHtml(entry.v)}</dt><dd>${label} · ${link}</dd>`;
  });
  return `<dl class="history">${lines.join("")}</dl>`;
}

function renderNotes(bug, terms) {
  return bug.notes.map((note) => `<h3>${escapeHtml(note.label)}</h3>
    <p>${highlight(note.text, terms)} <a href="${escapeHtml(note.url)}" target="_blank" rel="noopener">Article Fortinet</a></p>`).join("");
}

function renderBug({ bug, status, hardware }, terms) {
  const badge = status
    ? `<span class="badge ${status.key}">${STATUSES[status.key]}</span>${status.detail ? `<span>${escapeHtml(status.detail)}</span>` : ""}`
    : "";
  const workaround = bug.workaround
    ? `<h3>Contournement</h3><p>${highlight(bug.workaround, terms)}</p>`
    : "";
  return `<details class="bug" data-id="${bug.id}">
    <summary>
      <span class="bug-id">${bug.id}</span>
      <span class="bug-text">${highlight(bug.description, terms)}</span>
      <span class="bug-meta">${badge}<span>${escapeHtml(categories[bug.category])}</span><span>${escapeHtml(fixesLabel(bug))}</span>${bug.notes.map((note) => `<span class="badge fixed">${escapeHtml(note.label)}</span>`).join("")}${hardwareTags(bug, hardware)}</span>
    </summary>
    <div class="bug-detail">${renderNotes(bug, terms)}<h3>Apparition</h3>${renderAppearance(bug)}${workaround}<h3>Historique dans les notes</h3>${renderHistory(bug)}</div>
  </details>`;
}

function renderChips(counts) {
  const version = versionIndex(state.version);
  const chips = $("chips");
  if (state.view === "upgrade") {
    chips.innerHTML = Object.entries(UPGRADE_GROUPS).map(([key, label]) =>
      `<button type="button" class="chip" data-group="${key}" aria-pressed="${state.group === key}">${label} (${formatNumber(counts[key] || 0)})</button>`).join("");
  } else if (version >= 0) {
    chips.innerHTML = Object.entries(STATUSES).map(([key, label]) =>
      `<button type="button" class="chip" data-status="${key}" aria-pressed="${!state.hidden.has(key)}">${label} (${formatNumber(counts[key] || 0)})</button>`).join("");
  } else {
    chips.innerHTML = "";
  }
}

function renderNotices() {
  const notices = [];
  const selected = [versionIndex(state.version), state.view === "upgrade" ? versionIndex(state.from) : -1];
  for (const index of selected) {
    if (index >= 0 && versions[index].unavailable) {
      notices.push(`Les notes de la version ${versions[index].v} ne sont pas accessibles : ses corrections et ses bugs connus sont absents, les statuts de cette version sont incomplets.`);
    }
  }
  const version = selected[0];
  if (version >= 0 && state.model && !versions[version].unavailable) {
    const position = models.indexOf(state.model);
    if (!versions[version].models.includes(position)) {
      notices.push(`Le modèle ${state.model} n'apparaît pas dans la liste des modèles supportés par FortiOS ${versions[version].v}.`);
    }
  }
  if (state.view === "upgrade" && versionIndex(state.from) >= 0 && version >= 0 && versionIndex(state.from) >= version) {
    notices.push("La version cible doit être plus récente que la version actuelle.");
  }
  const articles = versionNotes(versionAnnotations, state.version, searchTerms(state.query), versions.map((entry) => entry.v)).map((note) =>
    `<p class="notice"><strong>FortiOS ${escapeHtml(note.version)} : ${escapeHtml(note.label)}.</strong> ${escapeHtml(note.text)} <a href="${escapeHtml(note.url)}" target="_blank" rel="noopener">Article Fortinet</a></p>`);
  $("notices").innerHTML = notices.map((text) => `<p class="notice">${escapeHtml(text)}</p>`).join("") + articles.join("");
}

function renderVersionInfo() {
  const entry = versions[versionIndex(state.version)];
  const parts = [];
  if (entry && !entry.unavailable) {
    parts.push(`FortiOS ${escapeHtml(entry.v)}`);
    if (entry.build) parts.push(`build ${escapeHtml(entry.build)}`);
    if (entry.released) parts.push(`publiée le ${formatDate(entry.released)}`);
    if (entry.revised) parts.push(`note révisée le ${formatDate(entry.revised)}`);
    if (entry.pdf) parts.push(`<a href="${escapeHtml(entry.pdf)}" target="_blank" rel="noopener">note officielle</a>`);
  }
  $("version-info").innerHTML = parts.join(" · ");
}

function renderRecommendation() {
  const entry = recommended.models[state.model];
  if (!entry) {
    $("recommendation").innerHTML = "";
    return;
  }
  const parts = [`Version recommandée par Fortinet pour ${escapeHtml(state.model)} : <strong>${escapeHtml(entry.release)}</strong>`];
  if (state.version !== entry.release) {
    const params = stateParams();
    params.set("version", entry.release);
    parts.push(`<a href="#${escapeHtml(params.toString())}">Voir cette version</a>`);
  }
  if (entry.ended) parts.push("support ingénierie terminé");
  parts.push(`<a href="${escapeHtml(recommended.source)}" target="_blank" rel="noopener">article Fortinet, état ${formatMonth(recommended.as_of)}</a>`);
  $("recommendation").innerHTML = parts.join(" · ");
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
  return `<p class="news-pdf">PDF révisé le ${formatDate(entry.revised)} · <a href="${escapeHtml(entry.pdf)}" target="_blank" rel="noopener">note officielle</a></p>`;
}

function renderHardware() {
  const terms = searchTerms($("hardware-query").value);
  const matching = lifecycles.filter(({ model }) => terms.every((term) => model.toLowerCase().includes(term)));
  const counts = {
    all: matching.length,
    current: matching.filter((entry) => entry.current).length,
    stopped: matching.filter((entry) => !entry.current).length,
  };
  const labels = { all: "Tous", current: "Dernière branche", stopped: "Plus dans la dernière branche" };
  $("chips").innerHTML = Object.entries(labels).map(([key, label]) =>
    `<button type="button" class="chip" data-hardware="${key}" aria-pressed="${state.hardware === key}">${label} (${formatNumber(counts[key])})</button>`).join("");

  const rows = matching
    .filter((entry) => state.hardware === "all" || entry.current === (state.hardware === "current"))
    .sort((a, b) => a.model.localeCompare(b.model, "fr", { numeric: true }))
    .map((entry) => {
      const badge = entry.current
        ? '<span class="badge fixed">Dernière branche</span>'
        : `<span class="badge potential">Arrêt après ${escapeHtml(entry.branch)}</span>`;
      const advice = recommended.models[entry.model];
      const support = !advice ? "—" : advice.ended
        ? '<span class="badge potential">Terminé</span>'
        : '<span class="badge fixed">En cours</span>';
      const release = advice
        ? `<a href="#${new URLSearchParams({ version: advice.release, model: entry.model })}">${escapeHtml(advice.release)}</a>`
        : "—";
      return `<tr><th scope="row"><a href="#model=${escapeHtml(entry.model)}">${escapeHtml(entry.model)}</a></th>
        <td>${escapeHtml(entry.first)}</td><td>${escapeHtml(entry.last)}</td><td>${badge}</td><td>${release}</td><td>${support}</td></tr>`;
    });
  $("results").innerHTML = rows.length
    ? `<table class="hardware-table"><thead><tr><th scope="col">Modèle</th><th scope="col">Première version</th><th scope="col">Dernière version</th><th scope="col">Statut FortiOS</th><th scope="col">Version recommandée</th><th scope="col">Support ingénierie</th></tr></thead><tbody>${rows.join("")}</tbody></table>`
    : "";
  $("count").textContent = rows.length ? "" : "Aucun modèle pour ces critères.";
  $("more").hidden = true;
  $("notices").innerHTML = "";
  $("version-info").innerHTML = "";
  $("recommendation").innerHTML = "";
  $("news-summary").innerHTML = "";
  writeHash();
}

function renderNews() {
  const advised = currentRecommendations(recommended.models);
  $("news-summary").innerHTML = latestCard("Dernière version publiée", "released")
    + latestCard("Dernier PDF mis à jour", "revised")
    + (advised.length ? newsCard("Recommandée par Fortinet", formatMonth(recommended.as_of), advised) : "");
  const byId = new Map(bugs.map((bug) => [bug.id, bug]));
  const entries = changes.map((change) => {
    const items = change.bugs.slice(0, 20).map((id) => {
      const bug = byId.get(id);
      return `<li><a href="#query=${id}">${id}</a> ${bug ? escapeHtml(bug.description) : ""}</li>`;
    });
    const hidden = change.bugs.length - items.length;
    if (hidden > 0) items.push(`<li class="muted">et ${formatNumber(hidden)} autres</li>`);
    return `<article class="news">
      <time datetime="${change.date}">${formatDate(change.date)}</time>
      <h2><a href="#version=${escapeHtml(change.version)}">${escapeHtml(change.title)}</a></h2>
      ${pdfLine(change.version)}
      ${items.length ? `<ul>${items.join("")}</ul>` : ""}
    </article>`;
  });
  $("results").innerHTML = entries.join("");
  $("count").textContent = "";
  $("more").hidden = true;
  $("chips").innerHTML = "";
  $("notices").innerHTML = "";
  $("version-info").innerHTML = "";
  $("recommendation").innerHTML = "";
  writeHash();
}

function render() {
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

  const waiting = state.view === "upgrade" && (!state.from || !state.version);
  $("count").textContent = waiting
    ? "Choisissez la version actuelle et la version cible."
    : rows.length ? `${formatNumber(rows.length)} bug${rows.length > 1 ? "s" : ""}` : "Aucun bug pour ces critères.";
  $("results").innerHTML = rows.slice(0, state.shown).map((row) => renderBug(row, terms)).join("");
  $("more").hidden = rows.length <= state.shown;
  writeHash();
}

function stateParams() {
  const params = new URLSearchParams();
  if (state.view !== "bugs") params.set("view", state.view);
  for (const key of ["query", "version", "from", "model", "category"]) {
    if (state[key]) params.set(key, state[key]);
  }
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
  $("version-label").textContent = upgrade ? "Version cible" : "Version FortiOS";
  $("view-help").textContent = {
    bugs: "Trouve un bug par numéro ou mots-clés, et son statut sur votre version et votre matériel.",
    upgrade: "Indique ce que change le passage d'une version à une autre : bugs corrigés, nouveaux bugs connus et bugs toujours présents.",
    news: "Les nouvelles versions, et les bugs que Fortinet ajoute après coup aux notes déjà publiées.",
    hardware: "Pour chaque modèle, la première et la dernière version FortiOS qui le supportent, et la version recommandée par Fortinet.",
  }[state.view];
  if (state.model !== optionsModel) {
    optionsModel = state.model;
    combos.version.setOptions(versionOptions("Toutes les versions"));
    combos.from.setOptions(versionOptions("Choisir"));
  }
  for (const key of ["version", "from", "model", "category"]) combos[key].value = state[key];
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent = theme === "dark" ? "Passer en blanc" : "Passer en noir";
}

function versionOptions(placeholder) {
  const advice = recommended.models[state.model];
  const options = [...versions].reverse().map((entry) => {
    const suffix = entry.unavailable ? " (notes indisponibles)" : entry.build ? ` (build ${entry.build})` : "";
    const mark = advice && advice.release === entry.v ? " · recommandée" : "";
    return { value: entry.v, label: `${entry.v}${suffix}${mark}`, group: `FortiOS ${entry.branch}` };
  });
  return [{ value: "", label: placeholder }, ...options];
}

function modelLabel(model) {
  const lifecycle = lifecycles.find((entry) => entry.model === model);
  return lifecycle.current ? model : `${model} (jusqu'à ${lifecycle.branch})`;
}

function modelOptions() {
  const families = [["FG", "FortiGate"], ["FWF", "FortiWiFi"], ["FGR", "FortiGate Rugged"], ["FFW", "FortiFirewall"], ["FOS", "FortiOS VM"]];
  const options = families.flatMap(([prefix, group]) => models
    .filter((model) => model.startsWith(`${prefix}-`))
    .sort((a, b) => a.localeCompare(b, "fr", { numeric: true }))
    .map((model) => ({ value: model, label: modelLabel(model), group })));
  return [{ value: "", label: "Tous les matériels" }, ...options];
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
  $("tab-bugs").addEventListener("click", () => update({ view: "bugs" }));
  $("tab-upgrade").addEventListener("click", () => update({ view: "upgrade" }));
  $("tab-news").addEventListener("click", () => update({ view: "news" }));
  $("tab-hardware").addEventListener("click", () => update({ view: "hardware" }));
  $("hardware-query").addEventListener("input", () => render());
  $("more").addEventListener("click", () => {
    state.shown += PAGE_SIZE;
    render();
  });
  $("chips").addEventListener("click", (event) => {
    const chip = event.target.closest("button");
    if (!chip) return;
    if (chip.dataset.hardware) {
      update({ hardware: chip.dataset.hardware });
    } else if (chip.dataset.group) {
      update({ group: chip.dataset.group });
    } else {
      const key = chip.dataset.status;
      if (state.hidden.has(key)) state.hidden.delete(key); else state.hidden.add(key);
      update({});
    }
  });
  window.addEventListener("hashchange", () => {
    readHash();
    $("query").value = state.query;
    update({});
  });
}

async function start() {
  const [index, data, news] = await Promise.all(
    ["data/index.json", "data/bugs.json", "data/changes.json"].map((url) => fetch(url).then((response) => {
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return response.json();
    })),
  );
  versions = index.versions;
  models = index.models;
  categories = data.categories;
  changes = news;
  checked = index.checked;
  recommended = index.recommended;
  annotations = data.annotations.bugs;
  versionAnnotations = data.annotations.versions;
  bugs = data.bugs.map(hydrate);
  lifecycles = modelLifecycles(models, versions);

  for (const key of ["version", "from", "model", "category"]) {
    combos[key] = new Combobox($(key), (value) => update({ [key]: value }));
  }
  combos.version.setOptions(versionOptions("Toutes les versions"));
  combos.from.setOptions(versionOptions("Choisir"));
  combos.model.setOptions(modelOptions());
  combos.category.setOptions([
    { value: "", label: "Toutes les catégories" },
    ...categories.map((name, index) => ({ value: String(index), label: name })),
  ]);

  if (recommended.as_of) {
    $("recommended-note").innerHTML = `La version recommandée et la fin du support ingénierie viennent de l'<a href="${escapeHtml(recommended.source)}" target="_blank" rel="noopener">article Fortinet</a> (état ${formatMonth(recommended.as_of)}), revu chaque trimestre. Un tiret signale un modèle absent de cet article, ou que les notes de la version recommandée ne listent pas.`;
  }
  const latest = [...versions].reverse().find((entry) => !entry.unavailable);
  $("scope").textContent = `Bugs et correctifs de toutes les versions FortiOS, de ${versions[0].branch} à ${latest.branch}`;
  $("stats").textContent = `${formatNumber(bugs.length)} bugs · ${formatNumber(versions.length)} versions · dernière version ${latest.v} · données vérifiées le ${formatDate(checked)}`;
  readHash();
  $("query").value = state.query;
  bindEvents();
  update({});
}

applyTheme(document.documentElement.dataset.theme);
start().catch((error) => {
  $("stats").textContent = "Impossible de charger les données.";
  console.error(error);
});
