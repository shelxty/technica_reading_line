// the step-by-step tutorial: one gesture at a time. content.js (the gesture engine, running on this page
// too) tells us what you did, and the step celebrates when it sees the gesture it's teaching

const $ = (s) => document.querySelector(s);
const panels = [...document.querySelectorAll(".panel")];
const navButtons = [...document.querySelectorAll(".stepper button")];
const live = $("#live");
const backBtn = $("#back");
const nextBtn = $("#next");
const LAST = panels.length - 1; // the "all done" panel
const GESTURES = LAST - 1; // steps 1..7 are gestures
const learned = new Set();
let current = 0;

function show(index, { focus = true } = {}) {
  current = Math.max(0, Math.min(LAST, index));
  panels.forEach((p, i) => (p.hidden = i !== current));
  navButtons.forEach((b, i) => {
    if (i === current) b.setAttribute("aria-current", "step");
    else b.removeAttribute("aria-current");
  });
  const panel = panels[current];
  const title = panel.querySelector("h2").textContent;
  $("#step-count").textContent = `Step ${current + 1} of ${panels.length}`;
  backBtn.disabled = current === 0;
  updateNext();
  live.textContent = `Step ${current + 1} of ${panels.length}: ${title}`;
  if (focus) panel.querySelector("h2").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

function updateNext() {
  if (current === LAST) {
    nextBtn.textContent = "Start reading the web →";
    return;
  }
  const done = current === 0 ? cameraOn : learned.has(current);
  nextBtn.textContent = done ? "Next →" : "Skip this step →";
}

function markStep(index, how = "done") {
  if (index < 1 || index > GESTURES || learned.has(index)) return;
  learned.add(index);
  const btn = navButtons[index];
  btn.classList.add("done");
  btn.querySelector(".state").textContent = how === "skipped" ? "Skipped" : "Done ✓";
  const bar = document.querySelector(".progress");
  bar.setAttribute("aria-valuenow", String(learned.size));
  bar.setAttribute("aria-valuetext", `${learned.size} of ${GESTURES} gestures learned`);
  bar.querySelector(".bar").style.width = `${(learned.size / GESTURES) * 100}%`;
  if (how === "done") {
    const panel = panels[index];
    panel.classList.add("success");
    panel.querySelector(".feedback").textContent = "✓ You did it! Press Next when you're ready.";
    if (index === current) live.textContent = "You did it! Press Next when you're ready.";
  }
  updateNext();
}

backBtn.addEventListener("click", () => show(current - 1));
nextBtn.addEventListener("click", () => {
  if (current === LAST) return window.close();
  if (current >= 1 && !learned.has(current)) markStep(current, "skipped");
  if (current === 0 && !cameraOn) navButtons[0].querySelector(".state").textContent = "Skipped";
  show(current + 1);
});
navButtons.forEach((b) => b.addEventListener("click", () => show(Number(b.dataset.go))));

// gestures, as reported by the engine. only the step you're on counts, so the steps go in order
let slept = false;
window.addEventListener("readingline", (e) => {
  const event = e.detail.event;
  if (event === "sleep") slept = true;
  if (event === "wake" && !slept) return; // a full pause + resume
  const panel = panels[current];
  if (panel.dataset.event === event) markStep(current);
});

$("#demo-button").addEventListener("click", () => {
  $("#demo-result").textContent = "✓ Clicked!";
  if (panels[current].dataset.event === "demo-click") markStep(current);
  setTimeout(() => ($("#demo-result").textContent = ""), 2500);
});
document.querySelector(".demo-link").addEventListener("click", (e) => e.preventDefault());

// ---------- camera ----------

const allow = $("#allow");
const msg = $("#camera-msg");
let cameraOn = false;

function cameraReady() {
  cameraOn = true;
  allow.disabled = true;
  allow.textContent = "✓ Camera is on";
  msg.textContent = "The camera is on. Raise your hand, then press Next.";
  panels[0].classList.add("success");
  navButtons[0].classList.add("done");
  navButtons[0].querySelector(".state").textContent = "Done ✓";
  updateNext();
}

allow.addEventListener("click", async () => {
  msg.textContent = "Waiting for the camera…";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop()); // we only needed the permission
    await chrome.runtime.sendMessage({ target: "background", type: "start" });
    cameraReady();
  } catch (e) {
    msg.textContent = e.name === "NotAllowedError"
      ? "The camera was blocked. Click the camera icon in the address bar, choose Allow, then try again."
      : `The camera couldn't start (${e.message}).`;
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.running && changes.running.newValue) cameraReady();
});
chrome.storage.session.get({ running: false }).then(({ running }) => running && cameraReady());

show(0, { focus: false });
