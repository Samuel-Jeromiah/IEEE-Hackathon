// Renders a CaseFile from POST /api/analyze: one block per artifact, by kind.
import { icon } from "../icons.js";
import { copyText, fmtRange, fmtTime, h, seekTo, toast } from "../ui.js";

const answerBlock = (text) => h("div", { class: "result-answer" }, h("p", {}, text));
const section = (title, ...content) => h("section", {}, h("h3", { class: "eyebrow" }, title), ...content);

export function renderCaseFile(cf, { fileUrl } = {}) {
  const wrap = h("div", { class: "result" });
  if (cf.policy?.action === "declined") {
    wrap.append(h("div", { class: "notice" }, icon("alert"),
      h("div", {}, h("p", {}, cf.policy.message || cf.answer || "I can't help with that."))));
    return wrap;
  }
  if (cf.status !== "ok" || cf.degraded?.length) {
    wrap.append(h("div", { class: "notice notice-warn" }, icon("alert"),
      h("div", {},
        h("strong", {}, cf.status === "failed" ? "This didn't work" : "Partial result"),
        (cf.degraded || []).map((d) => h("p", {}, d)))));
  }
  const abstained = cf.policy?.action === "abstained";
  for (const artifact of cf.artifacts) wrap.append(renderArtifact(artifact, fileUrl, abstained));
  return wrap;
}

function renderArtifact(a, fileUrl, abstained = false) {
  const failed = a.status === "failed"
    ? h("div", { class: "notice notice-error" }, icon("alert"), h("div", {}, h("strong", {}, "Couldn't process this file"),
      h("p", {}, a.error || "Unknown error")))
    : null;
  // Documents have their own not-found block; elsewhere an abstention replaces the answer.
  const cantTell = abstained && a.answer && !["document", "code"].includes(a.kind)
    ? notFoundBlock("Can't tell", a.answer, "StormLog says so instead of guessing.")
    : null;
  const shown = cantTell ? { ...a, answer: null } : a;
  const body = {
    image: imageResult, audio: audioResult, document: documentResult, video: videoResult, code: codeResult,
  }[a.kind]?.(shown, fileUrl) || (cantTell ? null : textResult(shown));
  return h("div", { class: "stack" }, failed, cantTell, body);
}

function textResult(a) {
  return answerBlock(a.answer || "No answer.");
}

function imageResult(a, url) {
  return h("div", { class: "stack" },
    url ? h("div", { class: "media-frame" }, h("img", { src: url, alt: a.description || "Your photo" })) : null,
    a.answer ? answerBlock(a.answer) : null,
    a.description ? section("What's in the photo", h("p", {}, a.description)) : null,
    a.extracted_text ? section("Text in the photo", h("div", { class: "output" }, h("pre", {}, a.extracted_text))) : null);
}

function timeline(segments, player) {
  return h("ol", { class: "timeline" }, segments.map((s) => h("li", {},
    h("button", { type: "button", disabled: !player, onclick: () => seekTo(player, s.t_start) },
      h("span", { class: "t" }, fmtRange(s.t_start, s.t_end)), h("span", {}, s.text)))));
}

function soundsList(sounds, player) {
  return h("div", { class: "sounds" }, sounds.map((s) => {
    const pct = Math.round((s.score || 0) * 100);
    return h("button", { type: "button", class: "sound", disabled: !player, onclick: () => seekTo(player, s.t_start) },
      h("span", { class: "t" }, fmtRange(s.t_start, s.t_end)),
      h("span", {}, h("span", { class: "sound-label" }, s.label),
        h("span", { class: "sound-bar", "aria-hidden": "true" }, h("span", { style: `width:${pct}%` }))),
      h("span", { class: "score" }, `${pct}%`));
  }));
}

function audioResult(a, url) {
  const player = url ? h("audio", { src: url, controls: true, preload: "metadata" }) : null;
  return h("div", { class: "stack" },
    player,
    a.answer ? answerBlock(a.answer) : null,
    a.transcript?.length ? section("Transcript", timeline(a.transcript, player)) : null,
    a.sounds?.length ? section("Sounds", soundsList(a.sounds, player)) : null);
}

function extractedText(a) {
  return a.extracted_text
    ? h("details", { class: "more" }, h("summary", {}, "Text StormLog read from the document"), h("pre", {}, a.extracted_text))
    : null;
}

export function notFoundBlock(title, message, why) {
  return h("div", { class: "not-found" },
    h("p", { class: "not-found-title" }, title), h("p", {}, message), why ? h("p", { class: "hint" }, why) : null);
}

function documentResult(a) {
  const qa = a.doc_qa;
  if (qa && !qa.found) {
    return h("div", { class: "stack" },
      notFoundBlock("Not in the document", a.answer || "I couldn't find that in the document.",
        "StormLog only answers when it can quote the document, so it says so instead of guessing."),
      extractedText(a));
  }
  const source = [qa?.page != null ? `Page ${qa.page}` : null,
    qa?.match_score != null ? `quote verified · match ${Math.round(qa.match_score)}/100` : null].filter(Boolean).join(" · ");
  return h("div", { class: "stack" },
    a.answer ? answerBlock(a.answer) : null,
    qa?.quote ? h("section", { class: "card" }, h("h3", { class: "eyebrow" }, "From the document"),
      h("blockquote", { class: "quote" }, `“${qa.quote}”`), source ? h("p", { class: "source-line" }, source) : null) : null,
    extractedText(a));
}

function videoResult(a, url) {
  const player = url ? h("video", { src: url, controls: true, playsinline: true, preload: "metadata" }) : null;
  const frames = (a.frames || []).map((f) => h("button", { type: "button", class: "frame", disabled: !player, onclick: () => seekTo(player, f.t) },
    f.thumb_b64
      ? h("img", { src: `data:image/jpeg;base64,${f.thumb_b64}`, alt: f.caption || `Frame at ${fmtTime(f.t)}` })
      : h("span", { class: "frame-placeholder" }, icon("film")),
    h("span", { class: "t" }, `Frame ${f.idx + 1} · ${fmtTime(f.t)}`),
    f.caption ? h("span", { class: "frame-caption" }, f.caption) : null));
  return h("div", { class: "stack" },
    player ? h("div", { class: "media-frame" }, player) : null,
    a.answer ? answerBlock(a.answer) : null,
    a.description ? section("What happens", h("p", {}, a.description)) : null,
    frames.length ? section("Frames", h("div", { class: "frames" }, frames)) : null,
    a.transcript?.length ? section("Speech", timeline(a.transcript, player)) : null,
    a.sounds?.length ? section("Sounds", soundsList(a.sounds, player)) : null);
}

export function renderCode(code, answer) {
  const copyBtn = h("button", {
    type: "button", class: "btn",
    onclick: async () => toast((await copyText(code.source)) ? "Code copied" : "Couldn't copy", "ok"),
  }, icon("copy", { size: 18 }), "Copy");
  return h("div", { class: "stack" },
    answer ? answerBlock(answer) : null,
    h("div", { class: "row" },
      h("span", { class: `badge ${code.tests_passed ? "pass" : "fail"}` },
        icon(code.tests_passed ? "check" : "x", { size: 16 }), code.tests_passed ? "Tests passed" : "Tests failed"),
      h("span", { class: "source-line" }, `${code.attempts} attempt${code.attempts === 1 ? "" : "s"}`)),
    h("div", { class: "codeblock" }, h("pre", {}, h("code", {}, code.source)), copyBtn),
    code.stdout ? h("div", { class: "output" }, h("h3", { class: "eyebrow" }, "Output"), h("pre", {}, code.stdout)) : null,
    code.stderr ? h("div", { class: "output" }, h("h3", { class: "eyebrow" }, "Errors"), h("pre", {}, code.stderr)) : null);
}

function codeResult(a) {
  return a.code ? renderCode(a.code, a.answer) : textResult(a);
}
