// Shared storm-mode pieces: labels, the damage placard, hazard banners, evidence chips, incident picker.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { currentIncidentId, setCurrentIncidentId } from "../state.js";
import { fmtRange, fmtTime, h, humanize, toast } from "../ui.js";

export const LEVELS = {
  affected: "Affected",
  minor: "Minor",
  major: "Major",
  destroyed: "Destroyed",
  needs_inspection: "Needs inspection",
};

// FEMA Public Assistance categories of work.
export const CATEGORIES = {
  A: "Debris removal",
  B: "Emergency protective measures",
  C: "Roads and bridges",
  D: "Water control facilities",
  E: "Buildings and equipment",
  F: "Utilities",
  G: "Parks, recreational and other facilities",
};

export const HAZARDS = {
  alarm_sounding: "Alarm sounding",
  downed_lines: "Downed power lines",
  gas_smell: "Gas smell reported",
  fire: "Fire",
  trapped_person: "Someone may be trapped",
  flooding: "Flooding",
  road_impassable: "Road closed",
  medical_need: "Medical need",
  other: "Hazard",
};

export const LOCATION_SOURCES = {
  photo_gps: "Location from photo GPS",
  voice_note: "Location from voice note",
  typed: "Location typed in",
  photo_text: "Location read from photo",
  unknown: "Location source unknown",
};

export const STATUSES = { draft: "Draft", needs_review: "Needs review", approved: "Approved" };

export const MAINE_COUNTIES = [
  "Androscoggin", "Aroostook", "Cumberland", "Franklin", "Hancock", "Kennebec", "Knox", "Lincoln",
  "Oxford", "Penobscot", "Piscataquis", "Sagadahoc", "Somerset", "Waldo", "Washington", "York",
];

export function statusPill(status) {
  return h("span", { class: "status", dataset: { status } }, STATUSES[status] || humanize(status));
}

export function placard(site) {
  if (site.kind === "public") {
    const cat = site.category;
    return h("div", { class: "placard", dataset: { level: cat ? "category" : "none" } },
      h("span", { class: "placard-label" }, "FEMA public assistance category"),
      h("span", { class: "placard-value" }, cat ? `Category ${cat}` : "Not set"),
      cat && h("span", { class: "placard-sub" }, CATEGORIES[cat]));
  }
  const level = site.level || "none";
  return h("div", { class: "placard", dataset: { level } },
    h("span", { class: "placard-label" }, "FEMA damage level"),
    h("span", { class: "placard-value" }, LEVELS[level] || "Not set"));
}

export function levelMini(site) {
  if (site.kind === "public") {
    return h("span", { class: "level-mini", dataset: { level: site.category ? "category" : "none" } },
      site.category ? `Cat. ${site.category}` : "No category");
  }
  const level = site.level || "none";
  return h("span", { class: "level-mini", dataset: { level } }, LEVELS[level] || "No level");
}

export function evidenceLabel(ev) {
  const loc = ev.locator || {};
  switch (ev.kind) {
    case "photo": return { iconName: "photo", text: "Photo" };
    case "voice": return { iconName: "mic", text: fmtRange(loc.t_start, loc.t_end) || "Voice note" };
    case "video_frame": return { iconName: "film", text: `Frame ${(loc.frame_idx ?? 0) + 1} · ${fmtTime(loc.t)}` };
    case "video_audio": return { iconName: "wave", text: `Audio ${fmtRange(loc.t_start, loc.t_end)}` };
    case "document": return { iconName: "file", text: loc.page != null ? `p. ${loc.page}` : "Document" };
    default: return { iconName: "file", text: humanize(ev.kind) };
  }
}

// Just the "where" part (time range, frame, page) for places that already show the evidence type.
export function evidenceWhere(ev) {
  const loc = ev.locator || {};
  switch (ev.kind) {
    case "voice":
    case "video_audio": return fmtRange(loc.t_start, loc.t_end);
    case "video_frame": return `Frame ${(loc.frame_idx ?? 0) + 1} · ${fmtTime(loc.t)}`;
    case "document": return loc.page != null ? `p. ${loc.page}` : "";
    default: return "";
  }
}

export function evidenceTitle(ev) {
  return {
    photo: "Photo",
    voice: "Voice note",
    video_frame: "Video frame",
    video_audio: "Sound in the video",
    document: "Document",
  }[ev.kind] || "Evidence";
}

export function evidenceChip(ev, onOpen) {
  const { iconName, text } = evidenceLabel(ev);
  return h("button", {
    type: "button", class: "chip", dataset: { verified: String(Boolean(ev.verified)) },
    "aria-label": `Open evidence: ${evidenceTitle(ev)} ${text}, ${ev.verified ? "verified" : "not verified"}`,
    onclick: () => onOpen(ev),
  }, icon(iconName, { size: 16 }), text,
  ev.verified ? h("span", { class: "chip-tick" }, icon("check", { size: 14 })) : null);
}

export function hazardBanner(hazard, chips = []) {
  const lifeSafety = hazard.severity === "life_safety";
  return h("div", { class: "hazard", role: lifeSafety ? "alert" : null, dataset: { severity: hazard.severity } },
    icon("alert", { size: 30 }),
    h("p", { class: "hazard-title" }, HAZARDS[hazard.type] || "Hazard"),
    h("div", { class: "hazard-body" },
      h("p", {}, hazard.message),
      chips.length ? h("div", { class: "chips" }, chips) : null,
      lifeSafety ? h("a", { class: "btn btn-danger btn-sm", href: "tel:911", style: "margin-top:12px" }, "Call 911") : null));
}

export function caseTagParts(inc) {
  return [
    h("b", {}, "Incident"),
    inc.name,
    inc.town ? `· ${inc.town}` : null,
    inc.county ? `· ${inc.county} Co.` : null,
    inc.started ? `· ${inc.started}` : null,
  ];
}

export const incidentName = (inc) => [inc.name, inc.town].filter(Boolean).join(" · ");

function newIncidentForm(onCreated) {
  const today = new Date().toISOString().slice(0, 10);
  const name = h("input", { id: "ni-name", class: "input", required: true, placeholder: "e.g. November windstorm" });
  const town = h("input", { id: "ni-town", class: "input", placeholder: "e.g. Rockland" });
  const county = h("select", { id: "ni-county", class: "input" },
    h("option", { value: "" }, "Choose a county"), MAINE_COUNTIES.map((c) => h("option", { value: c }, c)));
  const started = h("input", { id: "ni-started", class: "input", type: "date", value: today });
  const submit = h("button", { type: "submit", class: "btn btn-primary" }, icon("plus"), "Create incident");
  const form = h("form", { class: "form-grid" },
    h("div", {}, h("label", { class: "label", for: "ni-name" }, "Name"), name),
    h("div", { class: "form-grid two" },
      h("div", {}, h("label", { class: "label", for: "ni-town" }, "Town"), town),
      h("div", {}, h("label", { class: "label", for: "ni-county" }, "County"), county)),
    h("div", {}, h("label", { class: "label", for: "ni-started" }, "Storm started"), started),
    h("div", {}, submit));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!name.value.trim()) {
      name.focus();
      return;
    }
    submit.disabled = true;
    try {
      const inc = await api.createIncident({
        name: name.value.trim(),
        town: town.value.trim() || null,
        county: county.value || null,
        started: started.value || null,
      });
      form.reset();
      onCreated(inc);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

// Incident <select> plus an inline "new incident" form. Remembers the choice on this device.
// hideLabel keeps the label for screen readers when a visible heading already names the field.
export async function incidentPicker({ onChange, hideLabel = false } = {}) {
  const incidents = await api.incidents();
  let current = currentIncidentId();
  if (!incidents.some((i) => i.id === current)) current = incidents[0]?.id || null;
  if (current) setCurrentIncidentId(current);

  const select = h("select", { id: "incident-select", class: "input" });
  const fill = () => {
    select.replaceChildren(...(incidents.length
      ? incidents.map((i) => h("option", { value: i.id, selected: i.id === current }, incidentName(i)))
      : [h("option", { value: "" }, "No incidents yet: create one")]));
  };
  fill();
  select.addEventListener("change", () => {
    current = select.value || null;
    if (current) setCurrentIncidentId(current);
    onChange?.(current);
  });

  const formWrap = h("div", { class: "card", hidden: true, style: "margin-top:12px" });
  formWrap.append(newIncidentForm((inc) => {
    incidents.push(inc);
    current = inc.id;
    setCurrentIncidentId(current);
    fill();
    formWrap.hidden = true;
    toast(`Created “${inc.name}”.`, "ok");
    onChange?.(current);
  }));
  const toggle = h("button", {
    type: "button", class: "btn btn-ghost",
    onclick: () => {
      formWrap.hidden = !formWrap.hidden;
      if (!formWrap.hidden) formWrap.querySelector("input")?.focus();
    },
  }, icon("plus"), "New incident");

  const el = h("div", { class: "incident-picker" },
    h("label", { class: hideLabel ? "label visually-hidden" : "label", for: "incident-select" }, "Incident"),
    h("div", { class: "row" }, h("div", { style: "flex:1 1 240px" }, select), toggle),
    formWrap);
  return { el, get value() { return current; } };
}
