// WCAG 2.0 AA (what Section 508 requires): text needs at least 4.5:1 contrast with its background.
// this checks every text / background pair the extension draws
const test = require("node:test");
const assert = require("node:assert");

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const ratio = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const PAIRS = {
  // page highlight
  "line highlight (black on yellow)": ["#000000", "#ffff00"],
  "word being read (black on orange)": ["#000000", "#ff8c00"],
  "highlight tag": ["#111111", "#ffde00"],
  "reading tag": ["#052e13", "#22c55e"],
  // cursor badges: white text on each mode color
  ...Object.fromEntries(
    Object.entries({ point: "#1d4ed8", highlight: "#b45309", scroll: "#0f766e", pinch: "#c2410c", zoom: "#6d28d9", read: "#15803d", sleep: "#475569" })
      .map(([k, c]) => [`badge: ${k}`, ["#ffffff", c]])
  ),
  // hand preview panel (dark)
  "panel status": ["#fef9c3", "#0f172a"],
  "panel chip label": ["#cbd5e1", "#1e293b"],
  "panel hint": ["#e2e8f0", "#0f172a"],
  // popup + tutorial, light
  "text": ["#0f172a", "#ffffff"],
  "muted text": ["#475569", "#ffffff"],
  "muted text on card": ["#475569", "#f1f5f9"],
  "primary button": ["#ffffff", "#1d4ed8"],
  "stop button": ["#ffffff", "#b91c1c"],
  "error": ["#991b1b", "#fef2f2"],
  "done step": ["#166534", "#dcfce7"],
  "link": ["#1d4ed8", "#ffffff"],
  // popup + tutorial, dark
  "dark text": ["#f1f5f9", "#0b1120"],
  "dark muted": ["#cbd5e1", "#162033"],
  "dark primary button": ["#0b1120", "#3b82f6"],
  "dark stop button": ["#0b1120", "#f87171"],
  "dark error": ["#fecaca", "#3b1212"],
  "dark done step": ["#bbf7d0", "#14532d"],
  "dark link": ["#3b82f6", "#131c2e"],
};

for (const [name, [fg, bg]] of Object.entries(PAIRS)) {
  test(`${name}: ${ratio(fg, bg).toFixed(1)}:1`, () => assert.ok(ratio(fg, bg) >= 4.5, `${fg} on ${bg}`));
}
