// DOM helpers and shared components. Server text is always inserted as text nodes, never as HTML.
import { icon } from "./icons.js";

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style") el.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

// ----------------------------------------------------------------- formatting
export function fmtTime(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "";
  const t = Math.max(0, Math.round(Number(seconds)));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

export function fmtRange(start, end) {
  if (start == null) return "";
  return end != null && Math.round(end) !== Math.round(start) ? `${fmtTime(start)}–${fmtTime(end)}` : fmtTime(start);
}

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const fmtMoney = (n) => (n == null ? "—" : money.format(n));
export const fmtNumber = (n) => (n == null ? "—" : new Intl.NumberFormat("en-US").format(n));

export function fmtDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export const humanize = (s) => String(s ?? "").replace(/_/g, " ");

// ----------------------------------------------------------------- feedback
let toastTimer;
export function toast(message, kind = "info") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.dataset.kind = kind;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3600);
}

export function errorBox(err, retry) {
  return h("div", { class: "notice notice-error", role: "alert" },
    icon("alert"),
    h("div", {},
      h("strong", {}, "Something went wrong"),
      h("p", {}, err?.message || String(err)),
      retry && h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: retry, style: "margin-top:10px" },
        "Try again")));
}

// navigator.clipboard needs a secure context; fall back to execCommand over plain HTTP.
export async function copyText(text) {
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  const ta = h("textarea", { readonly: true, style: "position:fixed;left:-9999px;opacity:0" });
  ta.value = text;
  document.body.append(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

// Progress panel driven by server-sent events: stage text, striped bar, streamed answer text.
export function progressPanel(title = "Working on it") {
  const bar = h("div", { class: "progress-bar indeterminate" });
  const stage = h("p", { class: "progress-stage" }, "Sending…");
  const stream = h("p", { class: "progress-stream", hidden: true });
  const slow = h("p", { class: "progress-slow", hidden: true },
    "This is taking longer than usual. Everything runs on this laptop, not the cloud, so it's still working.");
  const el = h("section", { class: "card progress", "aria-live": "polite", "aria-busy": "true" },
    h("h2", { class: "eyebrow" }, title), h("div", { class: "progress-track" }, bar), stage, stream, slow);
  const timer = setTimeout(() => { slow.hidden = false; }, 45000);
  return {
    el,
    update(ev) {
      if (ev.type === "progress") {
        if (ev.message) stage.textContent = ev.message;
        if (typeof ev.pct === "number") {
          bar.classList.remove("indeterminate");
          bar.style.width = `${Math.max(6, Math.min(100, ev.pct))}%`;
        }
      } else if (ev.type === "delta" && ev.delta) {
        stream.hidden = false;
        stream.textContent += ev.delta; // chunks are raw text; concatenate as received
      } else if (ev.type === "error" && ev.message) {
        stage.textContent = ev.message;
      }
    },
    done() {
      clearTimeout(timer);
      el.setAttribute("aria-busy", "false");
      bar.classList.remove("indeterminate");
      bar.style.width = "100%";
    },
  };
}

// File picker with a camera/recorder button (phones) and a chooser, plus a preview.
export function filePicker({ label, accept, capture, takeLabel, chooseLabel, iconName, kind, hint }) {
  let file = null;
  let url = null;
  const take = capture ? h("input", { type: "file", accept, capture, class: "visually-hidden", tabindex: "-1" }) : null;
  const choose = h("input", { type: "file", accept, class: "visually-hidden", tabindex: "-1" });
  const preview = h("div", { class: "picker-preview", hidden: true });

  function set(next) {
    if (url) URL.revokeObjectURL(url);
    file = next || null;
    url = file ? URL.createObjectURL(file) : null;
    preview.replaceChildren();
    preview.hidden = !file;
    if (!file) return;
    let media = null;
    if (kind === "image") media = h("img", { src: url, alt: `Selected ${label.toLowerCase()}` });
    else if (kind === "audio") media = h("audio", { src: url, controls: true });
    else if (kind === "video") media = h("video", { src: url, controls: true, playsinline: true });
    preview.append(media || "", h("div", { class: "picker-meta" },
      h("span", { class: "mono" }, `${file.name} · ${fmtBytes(file.size)}`),
      h("button", {
        type: "button", class: "btn btn-ghost btn-sm",
        onclick: () => { if (take) take.value = ""; choose.value = ""; set(null); },
      }, icon("x"), "Remove")));
  }
  take?.addEventListener("change", () => set(take.files[0]));
  choose.addEventListener("change", () => set(choose.files[0]));

  const el = h("div", { class: "picker" },
    h("div", { class: "picker-buttons" },
      take && h("button", { type: "button", class: "btn btn-dark touch-only", onclick: () => take.click() },
        icon(iconName), takeLabel),
      h("button", { type: "button", class: "btn btn-ghost", onclick: () => choose.click() }, icon("upload"), chooseLabel)),
    hint && h("p", { class: "hint" }, hint),
    take, choose, preview);
  return {
    el,
    get file() { return file; },
    get url() { return url; },
    clear: () => set(null),
  };
}

// Modal dialog (the <dialog> element works over plain HTTP).
export function showDialog(...content) {
  const closeBtn = h("button", { type: "button", class: "btn btn-ghost btn-sm dialog-close" }, icon("x"), "Close");
  const dlg = h("dialog", { class: "dialog" }, h("div", { class: "dialog-body" }, closeBtn, ...content));
  closeBtn.addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => {
    dlg.querySelectorAll("audio, video").forEach((m) => m.pause());
    dlg.remove();
  });
  document.body.append(dlg);
  dlg.showModal();
  return dlg;
}

// Audio/video element that jumps to a moment once metadata is loaded.
export function seekableMedia(kind, src, startAt) {
  const el = h(kind, { src, controls: true, playsinline: kind === "video" ? true : null, preload: "metadata" });
  if (startAt != null) {
    el.addEventListener("loadedmetadata", () => {
      el.currentTime = Math.max(0, startAt - 0.3);
    }, { once: true });
  }
  return el;
}

export function seekTo(mediaEl, seconds) {
  if (!mediaEl) return;
  mediaEl.currentTime = Math.max(0, seconds);
  mediaEl.play?.().catch(() => {});
  mediaEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
