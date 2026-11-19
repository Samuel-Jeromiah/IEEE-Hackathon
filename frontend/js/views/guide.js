// Ask the guide: questions answered only from the bundled FEMA/MEMA/town documents, with the exact quote.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { errorBox, h } from "../ui.js";
import { notFoundBlock } from "./results.js";

const EXAMPLES = [
  "What counts as major damage for a flooded home?",
  "When should towns send damage reports to the county?",
  "Which FEMA category covers debris removal?",
  "Does FEMA pay for volunteers' pizza?",
];

const GUIDES = [
  ["FEMA Preliminary Damage Assessment Guide", "July 2025"],
  ["FEMA Preliminary Damage Assessment Pocket Guide", "July 2025"],
  ["MEMA Public Infrastructure Initial Damage Assessment: procedures", "Maine Emergency Management Agency"],
  ["MEMA Public Infrastructure IDA form and instructions", "Maine Emergency Management Agency"],
  ["MEMA Individuals & Households Initial Damage Assessment", "Maine Emergency Management Agency"],
  ["South Portland Emergency Operations Plan, Annex R: Recovery", "2023"],
];

function renderAnswer(answer) {
  if (!answer.found) {
    return h("div", { style: "margin-top:18px" }, notFoundBlock("Not in the guides",
      answer.answer || "I couldn't find that in the guides I have.",
      "StormLog only answers from the documents listed below, so it says so instead of guessing."));
  }
  const source = [answer.document, answer.page != null ? `p. ${answer.page}` : null,
    answer.match_score != null ? `quote verified · match ${Math.round(answer.match_score)}/100` : null]
    .filter(Boolean).join(" · ");
  return h("section", { class: "card answer-card", style: "margin-top:18px" },
    h("h2", { class: "eyebrow" }, "Answer"),
    h("p", { class: "answer-text" }, answer.answer || ""),
    answer.quote ? h("blockquote", { class: "quote" }, `“${answer.quote}”`) : null,
    source ? h("p", { class: "source-line" }, source) : null);
}

export function guideView(view) {
  const question = h("textarea", { id: "guide-q", class: "input", rows: 3,
    placeholder: "Ask about damage levels, deadlines, forms…" });
  const askBtn = h("button", { type: "submit", class: "btn btn-primary btn-lg" }, icon("book"), "Ask");
  const out = h("div", { "aria-live": "polite" });

  const form = h("form", { class: "card" },
    h("label", { class: "label", for: "guide-q" }, "Your question"),
    question,
    h("div", { class: "examples" }, EXAMPLES.map((ex) => h("button", {
      type: "button", class: "chip-button", onclick: () => { question.value = ex; form.requestSubmit(); },
    }, ex))),
    h("div", { style: "margin-top:14px" }, askBtn));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = question.value.trim();
    if (!q) {
      question.focus();
      return;
    }
    askBtn.disabled = true;
    out.replaceChildren(h("p", { class: "loading", style: "margin-top:18px" }, "Searching the guides"));
    try {
      out.replaceChildren(renderAnswer(await api.askGuide(q)));
    } catch (err) {
      out.replaceChildren(errorBox(err));
    } finally {
      askBtn.disabled = false;
    }
  });
  question.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit();
  });

  view.append(
    h("header", { class: "page-head" },
      h("p", { class: "kicker" }, "Ask the guide"),
      h("h1", {}, "What do the rules say?"),
      h("p", { class: "lede" }, "Answers come only from the guides on this laptop, with the exact quote and page. If it isn't in them, StormLog says so.")),
    form,
    out,
    h("section", { style: "margin-top:28px" },
      h("h2", { class: "section-rule" }, "Guides on this laptop"),
      h("ul", { class: "guide-list" }, GUIDES.map(([title, source]) => h("li", {},
        icon("file"), h("span", {}, h("strong", {}, title), h("br"), h("span", { class: "muted" }, source)))))));
}
