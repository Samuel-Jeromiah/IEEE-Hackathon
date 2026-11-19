// Report damage: the volunteer's phone flow. Photo, voice note, optional video, location, send.
import { api, listen, uid } from "../api.js";
import { icon } from "../icons.js";
import { navigate } from "../router.js";
import { rememberMedia } from "../state.js";
import { errorBox, filePicker, h, progressPanel, toast } from "../ui.js";
import { incidentPicker } from "./common.js";

function step(number, title, { optional = false } = {}, ...content) {
  return h("section", { class: "card step" },
    h("span", { class: "step-num", "aria-hidden": "true" }, String(number)),
    h("h2", {}, title, optional ? h("span", { class: "optional" }, "Optional") : null),
    ...content);
}

export async function reportView(view) {
  view.append(h("header", { class: "page-head" },
    h("p", { class: "kicker" }, "Field report"),
    h("h1", {}, "Report damage"),
    h("p", { class: "lede" }, "Add what you have. A photo or a voice note is enough. More evidence makes a better entry.")));

  const incident = await incidentPicker({ hideLabel: true });
  const photo = filePicker({
    label: "Photo", accept: "image/*", capture: "environment", takeLabel: "Take photo", chooseLabel: "Choose photo",
    iconName: "camera", kind: "image", hint: "Show the whole damaged area. Include the house number or a road sign if you can.",
  });
  const voice = filePicker({
    label: "Voice note", accept: "audio/*", capture: "user", takeLabel: "Record", chooseLabel: "Choose recording",
    iconName: "mic", kind: "audio",
    hint: "Say the address, what you see, and anything dangerous (wires down, gas smell, someone inside).",
  });
  const video = filePicker({
    label: "Video", accept: "video/*", capture: "environment", takeLabel: "Record video", chooseLabel: "Choose video",
    iconName: "film", kind: "video", hint: "Under a minute. Keep the camera steady and narrate if you can.",
  });
  const location = h("input", {
    id: "report-location", class: "input", type: "text", autocomplete: "street-address", placeholder: "e.g. 14 Water Street",
  });
  const sendBtn = h("button", { type: "submit", class: "btn btn-primary btn-xl btn-block" }, icon("arrowRight"), "Send report");
  const status = h("div");

  const form = h("form", { class: "report-form", novalidate: true },
    step(1, "Incident", {}, incident.el),
    step(2, "Photo", {}, photo.el),
    step(3, "Voice note", {}, voice.el),
    step(4, "Video", { optional: true }, video.el),
    step(5, "Location", {},
      h("label", { class: "label", for: "report-location" }, "Address or landmark"),
      location,
      h("p", { class: "hint" }, "Or just say it in your voice note. StormLog picks it up.")),
    h("div", { class: "sticky-send" }, sendBtn),
    status);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!incident.value) return toast("Pick or create an incident first.", "error");
    if (!photo.file && !voice.file && !video.file) return toast("Add a photo, a voice note or a video.", "error");

    sendBtn.disabled = true;
    const rid = uid();
    const progress = progressPanel("Building the site entry");
    status.replaceChildren(progress.el);
    progress.el.scrollIntoView({ behavior: "smooth", block: "center" });
    const stop = listen(rid, progress.update);

    const fd = new FormData();
    if (photo.file) fd.append("photo", photo.file);
    if (voice.file) fd.append("voice", voice.file);
    if (video.file) fd.append("video", video.file);
    if (location.value.trim()) fd.append("location_text", location.value.trim());
    fd.append("request_id", rid);
    try {
      const site = await api.addSite(incident.value, fd);
      progress.done();
      rememberMedia(site.id, { photo: photo.file, voice: voice.file, video: video.file });
      toast("Site entry drafted.", "ok");
      navigate(`/incident/${site.incident_id}/site/${site.id}`);
    } catch (err) {
      status.replaceChildren(errorBox(err));
      sendBtn.disabled = false;
    } finally {
      stop();
    }
  });

  view.append(form);
}
