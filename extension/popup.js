const toggleBtn = document.getElementById("toggle");
const statusEl = document.getElementById("status");
const checkboxes = ["highlightOn", "showPreview"].map((id) => document.getElementById(id));

function render(running) {
  toggleBtn.textContent = running ? "Stop hand tracking" : "Start hand tracking";
  toggleBtn.classList.toggle("stop", running);
  statusEl.textContent = running ? "Tracking your hand" : "Camera off";
  statusEl.classList.toggle("on", running);
}

async function cameraGranted() {
  try {
    return (await navigator.permissions.query({ name: "camera" })).state === "granted";
  } catch {
    return false;
  }
}

toggleBtn.addEventListener("click", async () => {
  const { running } = await chrome.storage.session.get("running");
  if (running) {
    await chrome.runtime.sendMessage({ target: "background", type: "stop" });
    return;
  }
  // the popup can't show the camera prompt, so ask from a normal tab the first time
  if (!(await cameraGranted())) {
    chrome.tabs.create({ url: chrome.runtime.getURL("setup.html") });
    window.close();
    return;
  }
  statusEl.textContent = "Starting camera…";
  await chrome.runtime.sendMessage({ target: "background", type: "start" });
});

chrome.storage.session.get("running", ({ running }) => render(!!running));
chrome.storage.local.get({ highlightOn: false, showPreview: true }, (s) => {
  for (const box of checkboxes) box.checked = s[box.id];
});

for (const box of checkboxes) {
  box.addEventListener("change", () => chrome.storage.local.set({ [box.id]: box.checked }));
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.running) render(!!changes.running.newValue);
  if (area === "local") {
    for (const box of checkboxes) if (changes[box.id]) box.checked = changes[box.id].newValue;
  }
});
