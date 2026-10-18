// service worker: starts/stops the camera page, forwards hand points to the active tab,
// and does the zooming (the browser version of win+= / win+- / win+esc)

const OFFSCREEN_URL = "offscreen.html";
const ZOOM_STEPS = [1, 1.25, 1.5, 2, 2.5, 3]; // zoom_level 0..5 (MAX_ZOOM = 5)

let activeTabId = null;
const injectedTabs = new Set(); // tabs we've already tried to inject the content script into
const baseZoom = new Map(); // tabId -> zoom the page had before we started zooming it

// ---------- offscreen (camera) document ----------

async function hasOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  return contexts.length > 0;
}

async function startTracking() {
  if (await hasOffscreen()) {
    chrome.runtime.sendMessage({ target: "offscreen", type: "start" }).catch(() => {});
    return;
  }
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ["USER_MEDIA"],
    justification: "Reads the webcam to track your hand for gesture control.",
  });
}

async function stopTracking() {
  if (await hasOffscreen()) {
    chrome.runtime.sendMessage({ target: "offscreen", type: "stop" }).catch(() => {});
    await chrome.offscreen.closeDocument().catch(() => {});
  }
  await setRunning(false);
  // tell every tab to clear its cursor/highlight
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) chrome.tabs.sendMessage(tab.id, { type: "stopped" }).catch(() => {});
  // put zoom back the way it was (like closing the magnifier on exit)
  for (const [tabId, zoom] of baseZoom) chrome.tabs.setZoom(tabId, zoom).catch(() => {});
  baseZoom.clear();
  zoomLevels.clear();
}

async function setRunning(running) {
  await chrome.storage.session.set({ running });
  chrome.action.setBadgeText({ text: running ? "ON" : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#1a7f37" });
}

async function toggleTracking() {
  const { running } = await chrome.storage.session.get("running");
  if (running) return stopTracking();
  return startTracking();
}

// the camera permission prompt can't show in the popup or the hidden page, so if the
// camera was refused (or never asked) we open a normal tab that asks for it
function openSetup() {
  chrome.tabs.create({ url: chrome.runtime.getURL("setup.html") });
}

// ---------- which tab gets the hand points ----------

async function getActiveTabId() {
  if (activeTabId !== null) return activeTabId;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  activeTabId = tab ? tab.id : null;
  return activeTabId;
}

chrome.tabs.onActivated.addListener(({ tabId }) => {
  if (activeTabId !== null && activeTabId !== tabId) {
    chrome.tabs.sendMessage(activeTabId, { type: "inactive" }).catch(() => {});
  }
  activeTabId = tabId;
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  const [tab] = await chrome.tabs.query({ active: true, windowId });
  if (tab) activeTabId = tab.id;
});

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "loading") injectedTabs.delete(tabId);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  injectedTabs.delete(tabId);
  baseZoom.delete(tabId);
  zoomLevels.delete(tabId);
  if (tabId === activeTabId) activeTabId = null;
});

async function forwardFrame(hand) {
  const tabId = await getActiveTabId();
  if (tabId === null) return;
  try {
    await chrome.tabs.sendMessage(tabId, { type: "frame", hand });
  } catch {
    // tabs that were open before the extension was installed don't have the content script yet
    if (injectedTabs.has(tabId)) return;
    injectedTabs.add(tabId);
    chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }).catch(() => {});
  }
}

// ---------- zoom ----------

const zoomLevels = new Map(); // tabId -> current step in ZOOM_STEPS

// dir = +1 (zoom in) or -1 (zoom out). returns the new level, or null if nothing changed
async function stepZoom(tabId, dir) {
  const level = zoomLevels.get(tabId) || 0;
  const next = Math.max(0, Math.min(ZOOM_STEPS.length - 1, level + dir));
  if (next === level) return null;
  if (!baseZoom.has(tabId)) baseZoom.set(tabId, await chrome.tabs.getZoom(tabId));
  await chrome.tabs.setZoom(tabId, baseZoom.get(tabId) * ZOOM_STEPS[next]);
  zoomLevels.set(tabId, next);
  if (next === 0) baseZoom.delete(tabId); // back to normal size, like closing the magnifier
  return next;
}

// ---------- messages ----------

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.target !== "background") return;

  switch (msg.type) {
    case "frame":
      forwardFrame(msg.hand);
      break;
    case "tracking-started":
      setRunning(true);
      break;
    case "camera-error":
      console.warn("camera error", msg.name, msg.message);
      stopTracking();
      if (msg.name === "NotAllowedError") openSetup();
      break;
    case "model-error":
      console.error("model error", msg.message);
      stopTracking();
      break;
    case "start":
      startTracking().then(() => sendResponse({ ok: true }));
      return true;
    case "stop":
      stopTracking().then(() => sendResponse({ ok: true }));
      return true;
    case "toggle":
      toggleTracking().then(() => sendResponse({ ok: true }));
      return true;
    case "zoom":
      if (!sender.tab) break;
      stepZoom(sender.tab.id, msg.dir)
        .then((level) => sendResponse({ level }))
        .catch((e) => sendResponse({ level: null, error: String(e) }));
      return true;
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-tracking") toggleTracking();
});

// service worker restarts forget everything, so resync the badge with reality
(async () => setRunning(await hasOffscreen()))();
