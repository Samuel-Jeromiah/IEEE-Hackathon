// The five general tools (the hackathon checklist): photo, audio, document, video, code.
import { api, listen, uid } from "../api.js";
import { icon } from "../icons.js";
import { navigate } from "../router.js";
import { errorBox, filePicker, h, progressPanel, toast } from "../ui.js";
import { renderCaseFile } from "./results.js";

export const TOOLS = [
  {
    kind: "image", title: "Photo", icon: "photo", blurb: "Describe it, then ask about it",
    accept: "image/*", capture: "environment", take: "Take photo", choose: "Choose photo", needsFile: true,
    question: "Ask about the photo (optional)", examples: ["What is in this photo?", "Read any text you can see."],
  },
  {
    kind: "audio", title: "Audio", icon: "mic", blurb: "Transcript, questions and sounds",
    accept: "audio/*", capture: "user", take: "Record", choose: "Choose audio", needsFile: true,
    question: "Ask about the recording (optional)", examples: ["What sounds can you hear?", "Summarize what was said."],
  },
  {
    kind: "document", title: "Document", icon: "file", blurb: "Answers with the exact quote",
    accept: ".pdf,.docx,.txt,.md,image/*", choose: "Choose document", allowText: true,
    question: "Your question", examples: ["When is rent due?", "Who signed this letter?", "Is pizza allowed?"],
  },
  {
    kind: "video", title: "Video", icon: "film", blurb: "What happens, and when",
    accept: "video/*", capture: "environment", take: "Record video", choose: "Choose video", needsFile: true,
    question: "Ask about the video (optional)", examples: ["What happens in this clip?", "Is anyone in danger?"],
  },
  {
    kind: "code", title: "Code", icon: "code", blurb: "Written, run and tested",
    accept: ".csv,text/csv", choose: "Add a CSV (optional)", promptRequired: true,
    question: "What should the code do?",
    examples: ["Write a function that checks whether a number is prime, with tests.",
      "Total the est_cost column by category."],
  },
];

export function toolTile(tool, index = 0) {
  return h("a", { class: "tile reveal", href: `#/tools/${tool.kind}`, style: `animation-delay:${0.2 + index * 0.05}s` },
    icon(tool.icon, { size: 30 }), h("span", { class: "tile-title" }, tool.title), h("span", { class: "tile-blurb" }, tool.blurb));
}

export function toolsHomeView(view) {
  view.append(
    h("header", { class: "page-head" },
      h("p", { class: "kicker" }, "General tools · local models"),
      h("h1", {}, "Ask about anything"),
      h("p", { class: "lede" }, "Photos, recordings, documents, videos and code requests, answered on this laptop. Answers point to their evidence, or say when they can't tell.")),
    h("div", { class: "tiles" }, TOOLS.map(toolTile)));
}

export function toolView(view, { kind }) {
  const tool = TOOLS.find((t) => t.kind === kind);
  if (!tool) {
    navigate("/tools");
    return;
  }
  const picker = filePicker({
    label: tool.title, accept: tool.accept, capture: tool.capture, takeLabel: tool.take, chooseLabel: tool.choose,
    iconName: tool.icon, kind: tool.kind,
  });
  const pasted = tool.allowText
    ? h("textarea", { id: "tool-text", class: "input", rows: 6, placeholder: "…or paste the document text here" })
    : null;
  const question = tool.promptRequired
    ? h("textarea", { id: "tool-q", class: "input", rows: 3, required: true })
    : h("input", { id: "tool-q", class: "input", type: "text", autocomplete: "off" });
  const runBtn = h("button", { type: "submit", class: "btn btn-primary btn-lg" }, icon("arrowRight"), "Run");
  const out = h("div");

  const form = h("form", { class: "card stack", novalidate: true },
    h("div", {}, h("p", { class: "label" }, tool.kind === "code" ? "Data file" : tool.title), picker.el),
    pasted ? h("div", {}, h("label", { class: "label", for: "tool-text" }, "Or paste text"), pasted) : null,
    h("div", {},
      h("label", { class: "label", for: "tool-q" }, tool.question),
      question,
      h("div", { class: "examples" }, tool.examples.map((ex) => h("button", {
        type: "button", class: "chip-button", onclick: () => { question.value = ex; question.focus(); },
      }, ex)))),
    h("div", {}, runBtn));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = pasted?.value.trim() || "";
    const prompt = question.value.trim();
    if (tool.needsFile && !picker.file) return toast(`Add a ${tool.title.toLowerCase()} first.`, "error");
    if (tool.allowText && !picker.file && !text) return toast("Choose a document or paste its text.", "error");
    if (tool.promptRequired && !prompt) {
      question.focus();
      return toast("Describe what the code should do.", "error");
    }
    runBtn.disabled = true;
    const rid = uid();
    const progress = progressPanel(`Working on your ${tool.title.toLowerCase()}`);
    out.replaceChildren(progress.el);
    progress.el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    const stop = listen(rid, progress.update);
    const fd = new FormData();
    if (picker.file) fd.append("files", picker.file);
    if (text) fd.append("text", text);
    if (prompt) fd.append("prompt", prompt);
    fd.append("task_hint", tool.kind);
    fd.append("request_id", rid);
    try {
      const casefile = await api.analyze(fd);
      progress.done();
      out.replaceChildren(renderCaseFile(casefile, { fileUrl: picker.url }));
    } catch (err) {
      out.replaceChildren(errorBox(err));
    } finally {
      stop();
      runBtn.disabled = false;
    }
  });

  view.append(
    h("a", { class: "back", href: "#/tools" }, icon("arrowLeft"), "All tools"),
    h("header", { class: "page-head tool-head" },
      h("span", { class: "tool-icon" }, icon(tool.icon, { size: 30 })),
      h("div", {}, h("p", { class: "kicker" }, "General tool"), h("h1", { style: "margin:0" }, tool.title))),
    form, out);
}
