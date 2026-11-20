// StormLog web app entry point: routes, navigation state, and the model-status pill.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { route, start } from "./router.js";
import { chatView, toolsRedirectView } from "./views/chat.js";
import { guideView } from "./views/guide.js";
import { homeView } from "./views/home.js";
import { reportView } from "./views/report.js";
import { siteView } from "./views/site.js";
import { townView } from "./views/town.js";

route("/", homeView);
route("/report", reportView);
route("/incident/:incidentId/site/:siteId", siteView);
route("/town", townView);
route("/guide", guideView);
route("/chat", chatView);
route("/tools", toolsRedirectView);
route("/tools/:kind", toolsRedirectView);

for (const slot of document.querySelectorAll("[data-icon]")) slot.append(icon(slot.dataset.icon, { size: 22 }));

function markNav(path) {
  const section = path.startsWith("/incident")
    ? "/town"
    : path.startsWith("/tools") || path.startsWith("/chat")
      ? "/chat"
      : path;
  for (const link of document.querySelectorAll("[data-nav]")) {
    if (link.dataset.nav === section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

const pill = document.getElementById("health-pill");
const PILL_TEXT = { ok: "Local models ready", stub: "Stub data", warn: "Models starting", down: "Laptop unreachable" };

async function refreshHealth() {
  let state;
  try {
    const health = await api.health();
    state = health.mode === "stub" ? "stub" : health.status === "ok" ? "ok" : "warn";
    pill.title = `Mode: ${health.mode}${health.profile ? ` · profile ${health.profile}` : ""}`;
  } catch {
    state = "down";
    pill.title = "The web app can't reach the StormLog laptop";
  }
  pill.dataset.state = state;
  pill.textContent = PILL_TEXT[state];
}

start(document.getElementById("view"), { onRoute: markNav });
refreshHealth();
setInterval(refreshHealth, 15000);
