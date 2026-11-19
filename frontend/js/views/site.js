// Site card: hazards first, then the damage placard, facts with evidence chips, evidence list, actions.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { mediaFor } from "../state.js";
import { fmtDateTime, fmtMoney, h, humanize, seekableMedia, showDialog, toast } from "../ui.js";
import {
  CATEGORIES, LEVELS, LOCATION_SOURCES, evidenceChip, evidenceLabel, evidenceTitle, evidenceWhere, hazardBanner, placard,
  statusPill,
} from "./common.js";

export async function siteView(view, { incidentId, siteId }) {
  view.append(h("a", { class: "back", href: "#/town" }, icon("arrowLeft"), "Town report"));
  const holder = h("div");
  view.append(holder);
  const report = await api.report(incidentId);
  const site = report.sites.find((s) => s.id === siteId);
  if (!site) throw new Error("That site isn't part of this incident.");
  renderSite(holder, site);
}

// Renders (and re-renders after edits) a site into a container. Used by the site page and the town report.
export function renderSite(container, site, { onSaved } = {}) {
  const rerender = (updated) => {
    renderSite(container, updated, { onSaved });
    onSaved?.(updated);
  };
  container.replaceChildren(siteCard(site, rerender));
}

const formatValue = (v) => (typeof v === "boolean" ? (v ? "Yes" : "No") : typeof v === "string" ? humanize(v) : v);

function fact(label, value, chips, needsReview) {
  const empty = value == null || value === "";
  return h("div", { class: "fact" },
    h("dt", {}, label),
    h("dd", {},
      h("span", { class: `fact-value${empty ? " empty" : ""}` }, empty ? "Not known yet" : String(value)),
      chips.length || needsReview
        ? h("div", { class: "chips" }, chips,
          needsReview ? h("span", { class: "needs-review" }, icon("flag", { size: 14 }), "Needs review") : null)
        : null));
}

function openEvidence(site, ev) {
  const local = mediaFor(site.id);
  const loc = ev.locator || {};
  const parts = [h("h2", {}, evidenceTitle(ev))];
  if (ev.kind === "photo") {
    const src = local.photo || ev.media_url;
    parts.push(src ? h("img", { src, alt: "Photo used as evidence" }) : h("p", { class: "hint" }, "Photo not available on this device."));
  } else if (ev.kind === "voice") {
    parts.push(local.voice
      ? seekableMedia("audio", local.voice, loc.t_start)
      : h("p", { class: "hint" }, "The recording stays on the phone that sent it. The quote below was checked against its transcript."));
  } else if (ev.kind === "video_frame" || ev.kind === "video_audio") {
    const t = loc.t ?? loc.t_start;
    if (local.video) parts.push(seekableMedia("video", local.video, t));
    else if (ev.media_url) parts.push(h("img", { src: ev.media_url, alt: "Video frame used as evidence" }));
    else parts.push(h("p", { class: "hint" }, "The video stays on the phone that sent it."));
  }
  if (ev.quote) parts.push(h("blockquote", { class: "quote" }, `“${ev.quote}”`));
  parts.push(h("p", { class: "source-line" }, evidenceLabel(ev).text, " · ",
    ev.verified
      ? h("span", { class: "verified" }, `Verified${ev.match_score != null ? ` · match ${Math.round(ev.match_score)}/100` : ""}`)
      : "Not verified"));
  showDialog(...parts);
}

function editForm(site, save, cancel) {
  const location = h("input", { id: "edit-location", class: "input", value: site.location?.text || "" });
  const rows = [h("div", {}, h("label", { class: "label", for: "edit-location" }, "Location"), location)];
  let level = null;
  let category = null;
  let cost = null;
  if (site.kind === "home") {
    level = h("select", { id: "edit-level", class: "input" },
      Object.entries(LEVELS).map(([v, label]) => h("option", { value: v, selected: v === site.level }, label)));
    rows.push(h("div", {}, h("label", { class: "label", for: "edit-level" }, "Damage level"), level,
      h("p", { class: "hint" }, "Rules set this from the evidence. Change it only if you inspected the site.")));
  } else {
    category = h("select", { id: "edit-category", class: "input" },
      Object.entries(CATEGORIES).map(([v, label]) => h("option", { value: v, selected: v === site.category }, `${v} · ${label}`)));
    cost = h("input", { id: "edit-cost", class: "input", type: "number", min: "0", step: "100", inputmode: "numeric",
      value: site.est_cost ?? "" });
    rows.push(
      h("div", {}, h("label", { class: "label", for: "edit-category" }, "FEMA category"), category),
      h("div", {}, h("label", { class: "label", for: "edit-cost" }, "Estimated cost (USD)"), cost));
  }
  const fieldInputs = Object.entries(site.fields).map(([name, f]) => {
    const input = h("input", { id: `edit-f-${name}`, class: "input", value: f.value ?? "" });
    rows.push(h("div", {}, h("label", { class: "label", for: `edit-f-${name}` }, humanize(name)), input));
    return [name, f, input];
  });
  const form = h("form", { class: "card form-grid" }, h("h2", { class: "eyebrow" }, "Edit site"), ...rows,
    h("div", { class: "actions" },
      h("button", { type: "submit", class: "btn btn-primary" }, icon("check"), "Save"),
      h("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel")));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const patch = {};
    if (location.value.trim() !== (site.location?.text || "")) patch.location_text = location.value.trim();
    if (level && level.value !== site.level) patch.level = level.value;
    if (category && category.value !== site.category) patch.category = category.value;
    if (cost && cost.value !== "" && Number(cost.value) !== site.est_cost) patch.est_cost = Number(cost.value);
    const fields = {};
    for (const [name, f, input] of fieldInputs) {
      if (input.value !== String(f.value ?? "")) fields[name] = input.value || null;
    }
    if (Object.keys(fields).length) patch.fields = fields;
    if (!Object.keys(patch).length) return cancel();
    save(patch, "Changes saved");
  });
  return form;
}

function siteCard(site, rerender) {
  const byId = new Map(site.evidence.map((e) => [e.id, e]));
  const open = (ev) => openEvidence(site, ev);
  const chipsFor = (ids = []) => ids.map((id) => byId.get(id)).filter(Boolean).map((ev) => evidenceChip(ev, open));

  async function save(patch, message) {
    try {
      const updated = await api.patchSite(site.id, patch);
      toast(message, "ok");
      rerender(updated);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const facts = [
    ...Object.entries(site.fields).map(([name, f]) => fact(humanize(name), f.value, chipsFor(f.evidence_ids), f.needs_review)),
    ...site.observations.map((o) => fact(humanize(o.name), formatValue(o.value), chipsFor(o.evidence_ids), false)),
  ];

  const editHolder = h("div", { hidden: true });
  const toggleEdit = () => {
    if (editHolder.hidden) {
      editHolder.replaceChildren(editForm(site, save, () => { editHolder.hidden = true; }));
      editHolder.hidden = false;
      editHolder.querySelector("input")?.focus();
    } else {
      editHolder.hidden = true;
    }
  };

  return h("article", { class: "site" },
    site.hazards.map((hz) => hazardBanner(hz, chipsFor(hz.evidence_ids))),
    h("header", { class: "site-head" },
      h("p", { class: "kicker" }, site.kind === "public" ? "Public infrastructure" : "Home"),
      h("h1", {}, site.location?.text || "Location not given"),
      h("div", { class: "site-meta" },
        h("span", {}, LOCATION_SOURCES[site.location?.source] || LOCATION_SOURCES.unknown),
        h("span", {}, fmtDateTime(site.created_at)),
        statusPill(site.status))),
    h("section", { class: "card" },
      placard(site),
      site.level_reason ? h("p", { class: "reason" }, h("strong", {}, "Why: "), site.level_reason) : null,
      site.kind === "public"
        ? h("p", { class: "reason" }, h("strong", {}, "Estimated cost: "),
          site.est_cost != null ? fmtMoney(site.est_cost) : "not entered yet. A person enters costs; the model never estimates them.")
        : null),
    facts.length ? h("section", { class: "card" }, h("h2", { class: "eyebrow" }, "What the evidence shows"), h("dl", { class: "facts" }, facts)) : null,
    h("section", { class: "card" },
      h("h2", { class: "eyebrow" }, `Evidence (${site.evidence.length})`),
      h("div", { class: "evidence-list" }, site.evidence.map((ev) => {
        const where = evidenceWhere(ev);
        return h("div", { class: "evidence-item" },
          icon(evidenceLabel(ev).iconName),
          h("div", {},
            h("div", {}, h("strong", {}, evidenceTitle(ev)), where ? h("span", { class: "source-line" }, ` · ${where}`) : null),
            h("div", { class: "source-line" }, ev.verified
              ? h("span", { class: "verified" }, `Verified${ev.match_score != null ? ` · match ${Math.round(ev.match_score)}/100` : ""}`)
              : "Not verified"),
            ev.quote ? h("blockquote", { class: "quote" }, `“${ev.quote}”`) : null,
            h("div", { style: "margin-top:8px" },
              h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => open(ev) },
                icon("play", { size: 16 }), "Open"))));
      }))),
    h("div", { class: "actions no-print" },
      site.status !== "approved"
        ? h("button", { type: "button", class: "btn btn-ok", onclick: () => save({ status: "approved" }, "Site approved") },
          icon("check"), "Approve")
        : h("button", { type: "button", class: "btn btn-ghost", onclick: () => save({ status: "needs_review" }, "Reopened for review") },
          icon("flag"), "Reopen for review"),
      h("button", { type: "button", class: "btn btn-ghost", onclick: toggleEdit }, icon("pencil"), "Edit")),
    editHolder);
}
