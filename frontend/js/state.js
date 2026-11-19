// Small client-side state: the current incident, and media this device uploaded.

const INCIDENT_KEY = "stormlog.incident";

export function currentIncidentId() {
  try {
    return localStorage.getItem(INCIDENT_KEY);
  } catch {
    return null; // storage can be blocked (private mode); the app still works
  }
}

export function setCurrentIncidentId(id) {
  try {
    localStorage.setItem(INCIDENT_KEY, id);
  } catch {
    /* ignore */
  }
}

// The API never sends uploads back, so evidence playback uses the files this browser
// still holds. Keyed by site id or request id; lives for the page session.
const media = new Map();

export function rememberMedia(key, files) {
  const urls = {};
  for (const [name, file] of Object.entries(files)) {
    if (file) urls[name] = URL.createObjectURL(file);
  }
  media.set(key, urls);
  return urls;
}

export function mediaFor(key) {
  return media.get(key) || {};
}
