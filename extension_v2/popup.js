const DEFAULTS = {
  soundOn: true,
  readParagraph: true,
  wordByWord: true,
  sayKind: true,
  showPreview: true,
  invertScroll: false,
  voiceRate: 1,
  cursorSize: 1,
  holdScale: 1,
};

const $ = (s) => document.querySelector(s);
const toggleBtn = $("#toggle");
const stateEl = $("#state");
const errorEl = $("#error");

const ERRORS = {
  NotAllowedError: "Camera access was blocked. Open the tutorial to allow it.",
  NotFoundError: "No camera was found. Plug one in and try again.",
  NotReadableError: "The camera is being used by another app. Close it and try again.",
};

function render({ running, sleeping, cameraError }) {
  document.body.classList.toggle("on", !!running && !sleeping);
  document.body.classList.toggle("sleeping", !!running && !!sleeping);
  stateEl.textContent = running
    ? sleeping
      ? "Gestures are paused. Wave to resume."
      : "Hand tracking is on"
    : "Hand tracking is off";
  toggleBtn.textContent = running ? "Stop hand tracking" : "Start hand tracking";
  errorEl.hidden = !cameraError;
  errorEl.textContent = cameraError ? ERRORS[cameraError] || "The camera couldn't start." : "";
}

async function refresh() {
  render(await chrome.storage.session.get({ running: false, sleeping: false, cameraError: "" }));
}

async function cameraGranted() {
  try {
    return (await navigator.permissions.query({ name: "camera" })).state === "granted";
  } catch {
    return false;
  }
}

toggleBtn.addEventListener("click", async () => {
  const { running } = await chrome.storage.session.get({ running: false });
  if (running) {
    await chrome.runtime.sendMessage({ target: "background", type: "stop" });
    return;
  }
  // the popup can't show the camera prompt, so the first time the tutorial asks for it
  if (!(await cameraGranted())) {
    chrome.runtime.sendMessage({ target: "background", type: "open-tutorial" });
    window.close();
    return;
  }
  stateEl.textContent = "Starting the camera…";
  await chrome.runtime.sendMessage({ target: "background", type: "start" });
});

$("#tutorial").addEventListener("click", () => {
  chrome.runtime.sendMessage({ target: "background", type: "open-tutorial" });
  window.close();
});
$("#shortcuts").addEventListener("click", () => chrome.tabs.create({ url: "chrome://extensions/shortcuts" }));

// ---------- settings ----------

const outputs = {
  voiceRate: (v) => `${Number(v).toFixed(1)}×`,
  cursorSize: (v) => `${Number(v).toFixed(2).replace(/0$/, "")}×`,
};

function showSettings(s) {
  document.querySelectorAll(".switch").forEach((el) => el.setAttribute("aria-checked", String(!!s[el.dataset.key])));
  document.querySelectorAll("input[type=range], select").forEach((el) => {
    el.value = String(s[el.dataset.key]);
    const out = document.getElementById(`${el.id}Out`);
    if (out) {
      out.textContent = outputs[el.dataset.key](el.value);
      el.setAttribute("aria-valuetext", out.textContent);
    }
  });
}

document.querySelectorAll(".switch").forEach((el) =>
  el.addEventListener("click", () => {
    const on = el.getAttribute("aria-checked") !== "true";
    el.setAttribute("aria-checked", String(on));
    chrome.storage.local.set({ [el.dataset.key]: on });
  })
);
document.querySelectorAll("input[type=range], select").forEach((el) =>
  el.addEventListener("input", () => {
    const value = Number(el.value);
    const out = document.getElementById(`${el.id}Out`);
    if (out) {
      out.textContent = outputs[el.dataset.key](value);
      el.setAttribute("aria-valuetext", out.textContent);
    }
    chrome.storage.local.set({ [el.dataset.key]: value });
  })
);

chrome.storage.local.get(DEFAULTS, showSettings);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session") refresh();
});
refresh();
