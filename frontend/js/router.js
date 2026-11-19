// Hash router. Each render gets a fresh container, so a slow view that finishes after
// the user has moved on writes into a detached element instead of the current screen.
import { errorBox } from "./ui.js";

const routes = [];

export function route(pattern, view) {
  const keys = [];
  const source = pattern.replace(/:(\w+)/g, (_, key) => {
    keys.push(key);
    return "([^/]+)";
  });
  routes.push({ re: new RegExp(`^${source}/?$`), keys, view });
}

export function navigate(path) {
  location.hash = `#${path}`;
}

export function start(outlet, { onRoute } = {}) {
  async function render() {
    const path = location.hash.slice(1) || "/";
    let match = null;
    let found = null;
    for (const r of routes) {
      match = path.match(r.re);
      if (match) {
        found = r;
        break;
      }
    }
    if (!found) {
      navigate("/");
      return;
    }
    const params = Object.fromEntries(found.keys.map((k, i) => [k, decodeURIComponent(match[i + 1])]));
    // A modal left open (e.g. evidence) must not follow the user to the next screen.
    for (const dlg of document.querySelectorAll("dialog[open]")) dlg.close();
    const view = document.createElement("div");
    view.className = "view";
    outlet.replaceChildren(view);
    window.scrollTo(0, 0);
    onRoute?.(path);
    try {
      await found.view(view, params);
    } catch (err) {
      view.append(errorBox(err, render));
    }
    outlet.focus({ preventScroll: true });
  }
  window.addEventListener("hashchange", render);
  render();
}
