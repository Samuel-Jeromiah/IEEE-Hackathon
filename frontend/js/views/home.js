// Home: report entry points and chat.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { currentIncidentId } from "../state.js";
import { h } from "../ui.js";
import { caseTagParts } from "./common.js";

export function homeView(view) {
  const caseTag = h("p", { class: "case-tag" },
    h("span", { class: "loading" }, "Loading incident"));
  const phoneCard = h("aside", { class: "card phone-card" },
    h("h2", { class: "eyebrow" }, "Phone access"), h("p", { class: "loading" }, "Finding address"));

  view.append(
    h("section", { class: "hero" },
      h("h1", { class: "hero-title" }, "Storm damage reports"),
      h("p", { class: "hero-sub" }, "Upload photos, voice notes, or video. Fields link back to evidence."),
      caseTag),
    h("div", { class: "home-grid" },
      h("div", {},
        h("a", { class: "slab", href: "#/report" },
          h("span", { class: "slab-icons" }, icon("camera", { size: 22 }), icon("mic", { size: 22 })),
          h("span", { class: "slab-title" }, "Report damage"),
          h("span", { class: "slab-sub" }, "Photo, voice, or video"),
          icon("arrowRight", { size: 20 })),
        h("div", { class: "duo" },
          h("a", { class: "btn btn-ghost btn-lg", href: "#/town" }, icon("clipboard"), "Town report"),
          h("a", { class: "btn btn-ghost btn-lg", href: "#/guide" }, icon("book"), "Guide")),
        h("a", { class: "slab slab-chat", href: "#/chat" },
          h("span", { class: "slab-icons" }, icon("chat", { size: 22 })),
          h("span", { class: "slab-title" }, "Chat"),
          h("span", { class: "slab-sub" }, "Ask about files or text"),
          icon("arrowRight", { size: 20 }))),
      phoneCard));

  api.incidents()
    .then((incidents) => {
      const id = currentIncidentId();
      const inc = incidents.find((i) => i.id === id) || incidents[0];
      caseTag.replaceChildren(...(inc ? caseTagParts(inc) : ["No incident yet — start one from Town report"]));
    })
    .catch(() => caseTag.replaceChildren("Incident list unavailable"));

  api.info()
    .then((info) => {
      phoneCard.replaceChildren(
        h("h2", { class: "eyebrow" }, "Phone access"),
        info.qr_png_b64
          ? h("img", { src: `data:image/png;base64,${info.qr_png_b64}`, alt: `QR code for ${info.lan_url}`, width: 240, height: 240 })
          : null,
        h("span", { class: "mono" }, info.lan_url),
        h("p", { class: "hint" }, "Same Wi-Fi only."));
    })
    .catch(() => phoneCard.replaceChildren(
      h("h2", { class: "eyebrow" }, "Phone access"), h("p", { class: "hint" }, "Couldn't read this laptop's address.")));
}
