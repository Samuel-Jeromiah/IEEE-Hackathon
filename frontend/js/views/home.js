// Home: the field kit. One big action, two secondary ones, and the five general tools.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { currentIncidentId } from "../state.js";
import { h } from "../ui.js";
import { caseTagParts } from "./common.js";
import { TOOLS, toolTile } from "./tools.js";

export function homeView(view) {
  const caseTag = h("p", { class: "case-tag reveal", style: "animation-delay:.14s" },
    h("span", { class: "loading" }, "Loading incident"));
  const phoneCard = h("aside", { class: "card phone-card reveal", style: "animation-delay:.3s" },
    h("h2", { class: "eyebrow" }, "Open on a phone"), h("p", { class: "loading" }, "Finding this laptop's address"));

  view.append(
    h("section", { class: "hero" },
      h("p", { class: "kicker reveal" }, "Initial damage assessment · runs offline"),
      h("h1", { class: "hero-title reveal", style: "animation-delay:.05s" },
        "Document storm damage. ", h("span", {}, "No internet needed.")),
      h("p", { class: "hero-sub reveal", style: "animation-delay:.1s" },
        "Photos, voice notes and video become a draft damage report. Every line links to its evidence."),
      caseTag),
    h("div", { class: "home-grid" },
      h("div", {},
        h("a", { class: "slab reveal", href: "#/report", style: "animation-delay:.16s" },
          h("span", { class: "slab-icons" }, icon("camera", { size: 30 }), icon("mic", { size: 30 })),
          h("span", { class: "slab-title" }, "Report damage"),
          h("span", { class: "slab-sub" }, "Photo · voice note · video"),
          icon("arrowRight", { size: 30 })),
        h("div", { class: "duo reveal", style: "animation-delay:.2s" },
          h("a", { class: "btn btn-ghost btn-lg", href: "#/town" }, icon("clipboard"), "Town report"),
          h("a", { class: "btn btn-ghost btn-lg", href: "#/guide" }, icon("book"), "Ask the guide")),
        h("h2", { class: "section-rule" }, "General tools"),
        h("div", { class: "tiles" }, TOOLS.map(toolTile))),
      phoneCard));

  api.incidents()
    .then((incidents) => {
      const id = currentIncidentId();
      const inc = incidents.find((i) => i.id === id) || incidents[0];
      caseTag.replaceChildren(...(inc ? caseTagParts(inc) : ["No incident yet: start one from the town report"]));
    })
    .catch(() => caseTag.replaceChildren("Incident list unavailable"));

  api.info()
    .then((info) => {
      phoneCard.replaceChildren(
        h("h2", { class: "eyebrow" }, "Open on a phone"),
        info.qr_png_b64
          ? h("img", { src: `data:image/png;base64,${info.qr_png_b64}`, alt: `QR code for ${info.lan_url}`, width: 240, height: 240 })
          : null,
        h("span", { class: "mono" }, info.lan_url),
        h("p", { class: "hint" }, "Phones on the same Wi-Fi can scan this. No internet connection is needed."));
    })
    .catch(() => phoneCard.replaceChildren(
      h("h2", { class: "eyebrow" }, "Open on a phone"), h("p", { class: "hint" }, "Couldn't read this laptop's address.")));
}
