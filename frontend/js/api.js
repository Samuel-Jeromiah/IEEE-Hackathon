// Client for the StormLog API (contract: contracts/schema.md, backend/schemas.py).
// Same-origin only: the web app is served by the API on the laptop, so no URLs leave the local network.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// crypto.randomUUID only exists in secure contexts; phones reach the laptop over plain HTTP.
export function uid() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const x = [...b].map((n) => n.toString(16).padStart(2, "0")).join("");
  return `${x.slice(0, 8)}-${x.slice(8, 12)}-${x.slice(12, 16)}-${x.slice(16, 20)}-${x.slice(20)}`;
}

async function request(method, path, { json, form } = {}) {
  const opts = { method, headers: {} };
  if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  } else if (form) {
    opts.body = form;
  }
  let resp;
  try {
    resp = await fetch(path, opts);
  } catch {
    throw new ApiError("Can't reach the StormLog laptop. Check that this device is on the same Wi-Fi.", 0);
  }
  if (!resp.ok) {
    let detail = "";
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || `The laptop answered with an error (${resp.status}).`, resp.status);
  }
  const type = resp.headers.get("content-type") || "";
  return type.includes("application/json") ? resp.json() : resp.text();
}

const enc = encodeURIComponent;

export const api = {
  health: () => request("GET", "/api/health"),
  info: () => request("GET", "/api/info"),
  analyze: (form) => request("POST", "/api/analyze", { form }),
  incidents: () => request("GET", "/api/incidents"),
  createIncident: (body) => request("POST", "/api/incidents", { json: body }),
  report: (incidentId) => request("GET", `/api/incidents/${enc(incidentId)}`),
  addSite: (incidentId, form) => request("POST", `/api/incidents/${enc(incidentId)}/sites`, { form }),
  patchSite: (siteId, body) => request("PATCH", `/api/sites/${enc(siteId)}`, { json: body }),
  askGuide: (question) => request("POST", "/api/guide/ask", { json: { question } }),
  analyzeIncident: (incidentId, prompt) =>
    request("POST", `/api/incidents/${enc(incidentId)}/analyze`, { json: { prompt } }),
  exportCsvUrl: (incidentId) => `/api/incidents/${enc(incidentId)}/export.csv`,
  reportHtmlUrl: (incidentId) => `/api/incidents/${enc(incidentId)}/report.html`,
};

// Progress events for one request (server-sent events). Optional by design: the POST
// response is the authoritative result, so a dropped stream never loses work.
// Returns a function that stops listening.
export function listen(requestId, onEvent) {
  if (!("EventSource" in window)) return () => {};
  const source = new EventSource(`/api/events/${enc(requestId)}`);
  source.onmessage = (msg) => {
    let ev;
    try {
      ev = JSON.parse(msg.data);
    } catch {
      return;
    }
    onEvent(ev);
    if (ev.type === "done" || ev.type === "error") source.close();
  };
  source.onerror = () => source.close(); // don't auto-reconnect; the POST result still arrives
  return () => source.close();
}
