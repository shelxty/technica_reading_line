// the tutorial: asks for the camera, then ticks off each gesture as you do it

const $ = (s) => document.querySelector(s);
const steps = [...document.querySelectorAll(".step")];
const live = $("#live");
const NAMES = { point: "Point", highlight: "Highlight", read: "Read out loud", click: "Click", zoom: "Zoom", scroll: "Scroll", wake: "Pause and resume" };

function markDone(step, how = "done") {
  if (step.classList.contains("done")) return;
  step.classList.add("done", "just-done");
  setTimeout(() => step.classList.remove("just-done"), 400);
  step.querySelector(".done-text").textContent = how === "skipped" ? "Skipped" : "Done ✓";
  const done = steps.filter((s) => s.classList.contains("done")).length;
  const bar = $("#progress");
  bar.setAttribute("aria-valuenow", String(done));
  bar.setAttribute("aria-valuetext", `${done} of ${steps.length} gestures learned`);
  bar.querySelector(".bar").style.width = `${(done / steps.length) * 100}%`;
  $("#progress-text").textContent = `${done} of ${steps.length}`;
  live.textContent = how === "skipped" ? `${NAMES[step.dataset.event]} skipped.` : `Nice! ${NAMES[step.dataset.event]} done.`;
  if (done === steps.length) {
    const end = $("#all-done");
    end.hidden = false;
    end.focus({ preventScroll: true });
    live.textContent = "You've learned all the gestures. You're all set!";
  }
}

steps.forEach((step) => step.querySelector(".skip-step").addEventListener("click", () => markDone(step, "skipped")));

// content.js (the gesture engine, also running on this page) tells us what you did
let slept = false;
window.addEventListener("readingline", (e) => {
  const event = e.detail.event;
  if (event === "sleep") slept = true;
  if (event === "wake" && !slept) return; // has to be a full pause + resume
  const step = steps.find((s) => s.dataset.event === event);
  if (step) markDone(step);
});

$("#demo-button").addEventListener("click", () => {
  $("#demo-result").textContent = "✓ Clicked!";
  setTimeout(() => ($("#demo-result").textContent = ""), 2500);
});
$("#demo-link").addEventListener("click", (e) => {
  e.preventDefault();
  $("#steps").scrollIntoView({ block: "start" });
});

// ---------- camera ----------

const allow = $("#allow");
const msg = $("#camera-msg");

function cameraReady() {
  allow.disabled = true;
  allow.textContent = "✓ Camera is on";
}

async function checkRunning() {
  const { running } = await chrome.storage.session.get({ running: false });
  if (running) cameraReady();
}

allow.addEventListener("click", async () => {
  msg.textContent = "Waiting for the camera…";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop()); // we only needed the permission
    await chrome.runtime.sendMessage({ target: "background", type: "start" });
    msg.textContent = "The camera is on. Show your hand and try the gestures below.";
    cameraReady();
  } catch (e) {
    msg.textContent = e.name === "NotAllowedError"
      ? "The camera was blocked. Click the camera icon in the address bar, choose Allow, then try again."
      : `The camera couldn't start (${e.message}).`;
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.running) {
    if (changes.running.newValue) cameraReady();
    else {
      allow.disabled = false;
      allow.textContent = "Allow camera and start";
    }
  }
});
checkRunning();
