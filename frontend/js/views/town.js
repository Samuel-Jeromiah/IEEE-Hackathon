// Town report: the emergency director's view. Totals, threshold meter, site list, export, analysis.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { navigate } from "../router.js";
import { errorBox, fmtMoney, fmtNumber, h, progressPanel } from "../ui.js";
import { LEVELS, incidentPicker, levelMini, statusPill } from "./common.js";
import { renderCode } from "./results.js";
import { renderSite } from "./site.js";

const isWide = () => window.matchMedia("(min-width: 1024px)").matches;
const STATUS_ORDER = { needs_review: 0, draft: 1, approved: 2 };
const FILTERS = [
  ["all", "All"],
  ["hazards", "Hazards"],
  ["review", "Needs review"],
  ["approved", "Approved"],
];
const ANALYSIS_PRESETS = [
  "Total the damage by category and compare it to the county threshold.",
  "List every road that is closed.",
  "Which sites still need review?",
];

export async function townView(view) {
  view.append(h("header", { class: "page-head" },
    h("p", { class: "kicker" }, "Town report"),
    h("h1", {}, "Damage report"),
    h("p", { class: "lede" }, "Every site from the field, with totals for the county. Approve entries, enter costs, then export.")));
  const body = h("div");
  const picker = await incidentPicker({ onChange: () => load() });
  view.append(picker.el, body);

  async function load(keepSelected) {
    if (!picker.value) {
      body.replaceChildren(h("div", { class: "empty-state", style: "margin-top:18px" }, "Create an incident to start a report."));
      return;
    }
    body.replaceChildren(h("p", { class: "loading", style: "margin-top:18px" }, "Loading the report"));
    try {
      renderReport(body, await api.report(picker.value), load, keepSelected);
    } catch (err) {
      body.replaceChildren(errorBox(err, () => load()));
    }
  }
  await load();
}

function stat(label, value, detail, alert = false) {
  return h("div", { class: `stat${alert ? " alert" : ""}` },
    h("div", { class: "stat-label" }, label),
    h("div", { class: "stat-value" }, String(value)),
    detail ? h("div", { class: "stat-detail" }, detail) : null);
}

function thresholdMeter(t) {
  if (!t) {
    return h("section", { class: "card" }, h("h2", { class: "eyebrow" }, "County threshold"),
      h("p", { class: "muted" }, "Set the incident's county to compare public damage with FEMA's county threshold."));
  }
  const pct = Math.max(0, Number(t.percent_of_threshold) || 0);
  const met = pct >= 100;
  return h("section", { class: "card meter-card" },
    h("h2", { class: "eyebrow" }, `${t.county} County threshold · ${t.fiscal_year}`),
    h("p", { class: "meter-headline" }, met ? "Meets the county threshold" : `${pct.toFixed(1)}% of the county threshold`),
    h("div", { class: "meter", role: "img", "aria-label": `${pct.toFixed(1)} percent of the county threshold` },
      h("div", { class: `meter-fill${met ? " met" : ""}`, style: `width:${Math.min(100, pct)}%` })),
    h("div", { class: "meter-scale", "aria-hidden": "true" }, ["0%", "25%", "50%", "75%", "100%"].map((s) => h("span", {}, s))),
    h("p", { class: "source-line" },
      `${fmtMoney(t.public_damage_usd)} public damage of ${fmtMoney(t.threshold_usd)} needed`,
      ` (${fmtNumber(t.population)} residents × $${Number(t.per_capita_usd).toFixed(2)})`),
    h("p", { class: "source-line" }, `Source: ${t.source}`));
}

function analysisPanel(incidentId) {
  const prompt = h("textarea", { id: "analysis-prompt", class: "input", rows: 3,
    placeholder: "e.g. Total the damage by category" });
  const out = h("div", { style: "margin-top:14px" });
  const runBtn = h("button", { type: "button", class: "btn btn-dark" }, icon("code"), "Run analysis");
  runBtn.addEventListener("click", async () => {
    const text = prompt.value.trim();
    if (!text) {
      prompt.focus();
      return;
    }
    runBtn.disabled = true;
    const progress = progressPanel("Writing and running the analysis");
    out.replaceChildren(progress.el);
    try {
      const result = await api.analyzeIncident(incidentId, text);
      progress.done();
      out.replaceChildren(renderCode(result.code));
    } catch (err) {
      out.replaceChildren(errorBox(err));
    } finally {
      runBtn.disabled = false;
    }
  });
  return h("details", { class: "card more no-print" },
    h("summary", {}, icon("code"), " Analyze the report with code"),
    h("p", { class: "hint" }, "The code model writes a script, runs it on this incident's data on this laptop, and checks it with tests."),
    h("div", { class: "examples" }, ANALYSIS_PRESETS.map((p) => h("button", {
      type: "button", class: "chip-button", onclick: () => { prompt.value = p; prompt.focus(); },
    }, p))),
    h("label", { class: "label", for: "analysis-prompt", style: "margin-top:14px" }, "What should the code work out?"),
    prompt,
    h("div", { style: "margin-top:10px" }, runBtn),
    out);
}

function renderReport(body, report, reload, keepSelected) {
  const inc = report.incident;
  const homes = report.sites.filter((s) => s.kind === "home");
  const publicTotal = Object.values(report.totals_by_category_usd).reduce((a, b) => a + b, 0);
  let filter = "all";
  let selectedId = keepSelected || null;

  const listHolder = h("div");
  const detail = h("aside", { class: "town-detail", "aria-label": "Selected site" });

  const matches = (s) => ({
    all: true,
    hazards: s.hazards.length > 0,
    review: s.status !== "approved",
    approved: s.status === "approved",
  })[filter];

  function row(site) {
    return h("button", {
      type: "button", class: "site-row", "aria-current": site.id === selectedId ? "true" : null,
      onclick: () => select(site),
    },
    site.hazards.length ? icon("alert", { label: "Has hazards" }) : icon(site.kind === "public" ? "flag" : "pin"),
    h("span", { class: "site-row-title" }, site.location?.text || "Location not given"),
    levelMini(site),
    h("span", { class: "site-row-sub" },
      `${site.kind === "public" ? "Public" : "Home"} · ${site.evidence.length} evidence · `, statusPill(site.status)));
  }

  function renderList() {
    const sites = report.sites.filter(matches).sort((a, b) =>
      (b.hazards.length > 0) - (a.hazards.length > 0) || STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
    listHolder.replaceChildren(sites.length
      ? h("div", { class: "site-list" }, sites.map(row))
      : h("div", { class: "empty-state", style: "margin-top:12px" },
        report.sites.length ? "No sites match this filter." : "No sites yet. Volunteers' reports appear here."));
    for (const el of listHolder.querySelectorAll(".site-row .icon[role='img']")) el.classList.add("hz");
  }

  function select(site) {
    if (!isWide()) {
      navigate(`/incident/${inc.id}/site/${site.id}`);
      return;
    }
    selectedId = site.id;
    renderList();
    renderSite(detail, site, { onSaved: (updated) => reload(updated.id) });
  }

  const segmented = h("div", { class: "segmented no-print", role: "group", "aria-label": "Filter sites" },
    FILTERS.map(([value, label]) => h("button", {
      type: "button", "aria-pressed": String(value === filter),
      onclick: (e) => {
        filter = value;
        for (const b of segmented.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b === e.currentTarget));
        renderList();
      },
    }, label)));

  body.replaceChildren(
    h("div", { class: "stats", style: "margin-top:20px" },
      stat("Sites", report.sites.length, `${homes.length} homes · ${report.sites.length - homes.length} public`),
      stat("Homes by level", homes.length, Object.entries(report.totals_by_level)
        .map(([level, n]) => h("span", { class: "level-mini", dataset: { level } }, `${n} ${LEVELS[level] || level}`))),
      stat("Public damage", fmtMoney(publicTotal), Object.entries(report.totals_by_category_usd)
        .map(([cat, usd]) => h("span", { class: "level-mini", dataset: { level: "category" } }, `${cat} · ${fmtMoney(usd)}`))),
      stat("Open hazards", report.hazards_open, report.hazards_open ? "Check these first" : "None open", report.hazards_open > 0)),
    h("div", { style: "margin-top:16px" }, thresholdMeter(report.threshold)),
    h("div", { class: "actions no-print", style: "margin-top:16px" },
      h("a", { class: "btn btn-ghost", href: api.exportCsvUrl(inc.id), download: `${inc.id}.csv` }, icon("download"), "Export CSV"),
      h("a", { class: "btn btn-ghost", href: api.reportHtmlUrl(inc.id), target: "_blank", rel: "noopener" },
        icon("printer"), "Printable report")),
    h("div", { style: "margin-top:16px" }, analysisPanel(inc.id)),
    h("div", { class: "town-panes" },
      h("section", {}, h("div", { class: "row", style: "justify-content:space-between" },
        h("h2", { style: "margin:0" }, "Sites"), segmented), listHolder),
      detail));

  renderList();
  const keep = keepSelected && report.sites.find((s) => s.id === keepSelected);
  if (isWide()) {
    if (keep) select(keep);
    else detail.replaceChildren(h("div", { class: "empty-state" }, "Select a site to see its evidence."));
  }
}
