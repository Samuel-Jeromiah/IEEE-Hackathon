// Stroke icons (24x24), built with DOM calls so no markup strings are injected.
const NS = "http://www.w3.org/2000/svg";
const P = (d, extra = {}) => ["path", { d, ...extra }];

const ICONS = {
  camera: [P("M3 8h3.2l2-3h7.6l2 3H21v11H3z"), ["circle", { cx: 12, cy: 13, r: 3.6 }]],
  mic: [["rect", { x: 9, y: 3, width: 6, height: 11, rx: 3 }], P("M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6")],
  film: [["rect", { x: 3, y: 5, width: 18, height: 14, rx: 2 }], P("M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4")],
  photo: [["rect", { x: 3, y: 4, width: 18, height: 16, rx: 2 }], ["circle", { cx: 9, cy: 10, r: 2 }], P("M21 16l-5-5-9 9")],
  file: [P("M6 3h8l4 4v14H6z"), P("M14 3v4h4M9 12h6M9 16h6")],
  code: [P("M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14")],
  clipboard: [["rect", { x: 5, y: 4, width: 14, height: 17, rx: 2 }], P("M9 4V3h6v1M9 10h6M9 14h6M9 18h3")],
  book: [P("M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"), P("M4 20.5V5.5M8 7h8")],
  grid: [["rect", { x: 4, y: 4, width: 7, height: 7, rx: 1 }], ["rect", { x: 13, y: 4, width: 7, height: 7, rx: 1 }],
    ["rect", { x: 4, y: 13, width: 7, height: 7, rx: 1 }], ["rect", { x: 13, y: 13, width: 7, height: 7, rx: 1 }]],
  pin: [P("M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z"), ["circle", { cx: 12, cy: 9, r: 2.5 }]],
  alert: [P("M12 3 22 20H2z"), P("M12 10v4.5M12 17.5h.01")],
  check: [P("M4 12.5l5 5L20 6.5")],
  x: [P("M6 6l12 12M18 6 6 18")],
  play: [P("M7 4.5v15l12-7.5z", { fill: "currentColor" })],
  wave: [P("M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2")],
  arrowRight: [P("M5 12h14M13 6l6 6-6 6")],
  arrowLeft: [P("M19 12H5M11 6l-6 6 6 6")],
  download: [P("M12 4v11M7 10l5 5 5-5M5 20h14")],
  printer: [P("M7 8V3h10v5M7 17H4v-7h16v7h-3"), ["rect", { x: 7, y: 14, width: 10, height: 7 }]],
  pencil: [P("M4 20h4L19.5 8.5a2.1 2.1 0 0 0-4-4L4 16z")],
  phone: [["rect", { x: 7, y: 2.5, width: 10, height: 19, rx: 2 }], P("M11 18.5h2")],
  upload: [P("M12 16V5M7 10l5-5 5 5M5 20h14")],
  copy: [["rect", { x: 8, y: 8, width: 12, height: 12, rx: 2 }], P("M4 16V4h12")],
  plus: [P("M12 5v14M5 12h14")],
  flag: [P("M5 21V4h11l-1.5 4L16 12H5")],
  bolt: [P("M13 2 4 14h7l-1 8 9-12h-7z")],
  chat: [P("M4 5h16v11H8l-4 4z")],
};

export function icon(name, { size = 24, label } = {}) {
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({
    viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round",
  })) svg.setAttribute(k, v);
  svg.classList.add("icon");
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
  }
  for (const [tag, attrs] of ICONS[name] || []) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.append(el);
  }
  return svg;
}
