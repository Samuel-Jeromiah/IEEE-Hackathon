// Unified multimodal chat: ChatGPT-style thread; Manrope + blue tokens elsewhere.
import { api, listen, uid } from "../api.js";
import { icon } from "../icons.js";
import { navigate } from "../router.js";
import { errorBox, fmtBytes, h, progressPanel, toast } from "../ui.js";
import { renderCaseFile } from "./results.js";

const ACCEPT = "image/*,audio/*,video/*,.pdf,.docx,.txt,.md,.csv,text/csv";

const CODE_RE = /\b(write|generate|implement)\b[\s\S]{0,40}\b(code|function|script|tests?)\b|\bunit tests?\b|\bpytest\b|\best_cost\b/i;

const SUGGESTIONS = [
  { title: "Describe a photo", prompt: "What's in this photo?", icon: "photo" },
  { title: "Listen to audio", prompt: "Summarize the recording", icon: "mic" },
  { title: "Ask a document", prompt: "When is rent due?", icon: "file" },
  { title: "Watch a clip", prompt: "What happens in this clip?", icon: "film" },
];

export function fileKind(file) {
  const t = (file.type || "").toLowerCase();
  const n = (file.name || "").toLowerCase();
  if (t.startsWith("image/") || /\.(jpe?g|png|heic|heif|webp|gif|bmp)$/.test(n)) return "image";
  if (t.startsWith("audio/") || /\.(mp3|wav|m4a|ogg|opus|flac|aac)$/.test(n)) return "audio";
  if (t.startsWith("video/") || /\.(mp4|mov|webm|mkv|avi|m4v)$/.test(n)) return "video";
  if (t === "text/csv" || /\.csv$/.test(n)) return "code";
  if (/\.(pdf|docx|txt|md)$/.test(n) || t.includes("pdf") || t.includes("word")) return "document";
  return "document";
}

export function inferTaskHint(files, prompt) {
  const p = (prompt || "").trim();
  if (!files.length) {
    if (CODE_RE.test(p)) return "code";
    return null;
  }
  const kinds = [...new Set(files.map(fileKind))];
  if (kinds.length === 1) return kinds[0];
  return null;
}

function contextFromCase(cf) {
  if (!cf?.artifacts?.length) return cf?.answer || "";
  const parts = [];
  for (const a of cf.artifacts) {
    if (a.extracted_text) parts.push(a.extracted_text.slice(0, 6000));
    else if (a.transcript?.length) parts.push(a.transcript.map((s) => s.text).join(" "));
    else if (a.description) parts.push(a.description);
    else if (a.answer) parts.push(a.answer);
  }
  return parts.join("\n\n").slice(0, 12000);
}

function kindIcon(kind) {
  return ({ image: "photo", audio: "mic", video: "film", document: "file", code: "code" })[kind] || "file";
}

function avatar(who) {
  return h("div", { class: `chat-avatar chat-avatar-${who}`, "aria-hidden": "true" },
    icon(who === "assistant" ? "bolt" : "chat", { size: 16 }));
}

function autoSize(ta) {
  ta.style.height = "auto";
  ta.style.height = `${Math.min(200, Math.max(24, ta.scrollHeight))}px`;
}

export function chatView(view) {
  let attachments = [];
  let lastContext = "";
  let busy = false;

  const thread = h("div", { class: "chat-thread", role: "log", "aria-live": "polite" });
  const attachStrip = h("div", { class: "chat-attach-strip", hidden: true });
  const input = h("textarea", {
    class: "chat-input",
    rows: 1,
    placeholder: "Message StormLog…",
    autocomplete: "off",
  });
  const fileInput = h("input", {
    type: "file", class: "visually-hidden", tabindex: "-1", accept: ACCEPT, multiple: true,
  });
  const sendBtn = h("button", {
    type: "submit", class: "chat-send", disabled: true, "aria-label": "Send message",
  }, icon("arrowRight", { size: 18 }));
  const attachBtn = h("button", {
    type: "button", class: "chat-icon-btn", "aria-label": "Attach files",
    onclick: () => fileInput.click(),
  }, icon("plus", { size: 20 }));

  function syncSend() {
    sendBtn.disabled = busy || (!input.value.trim() && !attachments.length);
  }

  function renderAttachStrip() {
    attachStrip.hidden = attachments.length === 0;
    attachStrip.replaceChildren(...attachments.map((a, i) => h("div", { class: "chat-chip" },
      icon(kindIcon(a.kind), { size: 14 }),
      h("span", { class: "chat-chip-name" }, a.file.name),
      h("span", { class: "mono" }, fmtBytes(a.file.size)),
      h("button", {
        type: "button", class: "chat-chip-x", "aria-label": `Remove ${a.file.name}`,
        onclick: () => {
          URL.revokeObjectURL(a.url);
          attachments.splice(i, 1);
          renderAttachStrip();
          syncSend();
        },
      }, icon("x", { size: 14 })))));
  }

  function addFiles(list) {
    for (const file of list) {
      if (attachments.some((a) => a.file.name === file.name && a.file.size === file.size)) continue;
      attachments.push({ file, url: URL.createObjectURL(file), kind: fileKind(file) });
    }
    renderAttachStrip();
    syncSend();
  }

  fileInput.addEventListener("change", () => {
    if (fileInput.files?.length) addFiles([...fileInput.files]);
    fileInput.value = "";
  });
  input.addEventListener("input", () => { autoSize(input); syncSend(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  function showEmpty() {
    thread.replaceChildren(
      h("div", { class: "chat-empty" },
        h("div", { class: "chat-empty-mark" }, icon("bolt", { size: 28 })),
        h("h1", { class: "chat-empty-title" }, "How can I help?"),
        h("p", { class: "chat-empty-sub" },
          "Upload a photo, recording, video, or document — or just ask. Runs offline on this laptop."),
        h("div", { class: "chat-suggestions" },
          ...SUGGESTIONS.map((s) => h("button", {
            type: "button", class: "chat-suggestion",
            onclick: () => { input.value = s.prompt; autoSize(input); input.focus(); syncSend(); },
          },
            h("span", { class: "chat-suggestion-icon" }, icon(s.icon, { size: 18 })),
            h("span", { class: "chat-suggestion-title" }, s.title),
            h("span", { class: "chat-suggestion-prompt" }, s.prompt))))));
  }
  showEmpty();

  function appendUserTurn(text, files) {
    const empty = thread.querySelector(".chat-empty");
    if (empty) empty.remove();
    const previews = files.map((a) => {
      if (a.kind === "image") return h("img", { class: "chat-thumb", src: a.url, alt: a.file.name });
      if (a.kind === "video") return h("video", { class: "chat-thumb", src: a.url, muted: true });
      return h("span", { class: "chat-file-pill" }, icon(kindIcon(a.kind), { size: 14 }), a.file.name);
    });
    thread.append(
      h("div", { class: "chat-row chat-row-user" },
        h("div", { class: "chat-row-body" },
          files.length ? h("div", { class: "chat-user-media" }, ...previews) : null,
          text ? h("div", { class: "chat-bubble chat-bubble-user" }, text) : null),
        avatar("user")));
    thread.scrollTop = thread.scrollHeight;
  }

  function appendAssistantSlot() {
    const body = h("div", { class: "chat-row-body" });
    const slot = h("div", { class: "chat-row chat-row-assistant" }, avatar("assistant"), body);
    thread.append(slot);
    thread.scrollTop = thread.scrollHeight;
    return body;
  }

  const form = h("form", { class: "chat-composer", novalidate: true },
    attachStrip,
    h("div", { class: "chat-composer-shell" },
      attachBtn, fileInput, input, sendBtn),
    h("p", { class: "chat-footnote" }, "StormLog can make mistakes. Check evidence quotes and timestamps."));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const prompt = input.value.trim();
    const files = [...attachments];
    if (!prompt && !files.length) return toast("Type a message or attach a file.", "error");

    busy = true;
    syncSend();
    appendUserTurn(prompt, files);
    input.value = "";
    autoSize(input);
    attachments = [];
    renderAttachStrip();

    const slot = appendAssistantSlot();
    const rid = uid();
    const progress = progressPanel("Thinking…");
    slot.replaceChildren(progress.el);
    const stop = listen(rid, progress.update);

    const hint = inferTaskHint(files.map((a) => a.file), prompt);
    const fd = new FormData();
    for (const a of files) fd.append("files", a.file);
    if (prompt) fd.append("prompt", prompt);
    if (!files.length && lastContext) fd.append("text", lastContext);
    if (hint) fd.append("task_hint", hint);
    fd.append("request_id", rid);

    try {
      const casefile = await api.analyze(fd);
      progress.done();
      lastContext = contextFromCase(casefile) || lastContext;
      const primaryUrl = files[0]?.url || null;
      slot.replaceChildren(
        h("div", { class: "chat-assistant-card" }, renderCaseFile(casefile, { fileUrl: primaryUrl })));
    } catch (err) {
      slot.replaceChildren(errorBox(err));
    } finally {
      stop();
      busy = false;
      syncSend();
      thread.scrollTop = thread.scrollHeight;
      input.focus();
    }
  });

  view.addEventListener("dragover", (e) => { e.preventDefault(); view.classList.add("chat-drop"); });
  view.addEventListener("dragleave", () => view.classList.remove("chat-drop"));
  view.addEventListener("drop", (e) => {
    e.preventDefault();
    view.classList.remove("chat-drop");
    if (e.dataTransfer?.files?.length) addFiles([...e.dataTransfer.files]);
  });

  document.body.classList.add("chat-mode");
  view.classList.add("chat-page");
  view.append(thread, form);
  input.focus();
  autoSize(input);

  const obs = new MutationObserver(() => {
    if (!document.body.contains(view)) {
      document.body.classList.remove("chat-mode");
      obs.disconnect();
    }
  });
  obs.observe(document.body, { childList: true, subtree: true });
}

export function toolsRedirectView() {
  navigate("/chat");
}
