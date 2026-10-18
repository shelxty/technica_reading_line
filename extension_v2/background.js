// service worker: starts / stops the camera page, forwards hand points to the tab you're looking at,
// zooms, reads out loud (chrome's text-to-speech, which tells us each word as it's spoken),
// and handles the keyboard shortcuts

const OFFSCREEN_URL = "offscreen.html";
const ZOOM_LEVELS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3]; // 50% - 300%
const EXTENSION_ORIGIN = `chrome-extension://${chrome.runtime.id}/`;

let activeTab = { id: null, url: "" };
const injected = new Set();

// let the content scripts read / write the "sleeping" flag
chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_AND_UNTRUSTED_CONTEXTS" }).catch(() => {});

// ---------- camera page ----------

async function hasOffscreen() {
  return (await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] })).length > 0;
}

async function startTracking() {
  if (await hasOffscreen()) {
    chrome.runtime.sendMessage({ target: "offscreen", type: "start" }).catch(() => {});
    return;
  }
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ["USER_MEDIA", "AUDIO_PLAYBACK"],
    justification: "Reads the webcam to follow your hand, and plays short sound cues.",
  });
}

async function stopTracking() {
  if (await hasOffscreen()) await chrome.offscreen.closeDocument().catch(() => {});
  chrome.tts.stop();
  await chrome.storage.session.set({ running: false, sleeping: false });
  updateBadge();
  for (const tab of await chrome.tabs.query({})) chrome.tabs.sendMessage(tab.id, { type: "stopped" }).catch(() => {});
  chrome.runtime.sendMessage({ type: "stopped" }).catch(() => {}); // extension pages (tutorial)
}

async function toggleTracking() {
  const { running } = await chrome.storage.session.get("running");
  return running ? stopTracking() : startTracking();
}

async function updateBadge() {
  const { running, sleeping } = await chrome.storage.session.get(["running", "sleeping"]);
  chrome.action.setBadgeText({ text: running ? (sleeping ? "Zz" : "ON") : "" });
  chrome.action.setBadgeBackgroundColor({ color: sleeping ? "#475569" : "#15803d" });
  chrome.action.setTitle({ title: running ? (sleeping ? "Reading Line: sleeping" : "Reading Line: on") : "Reading Line: off" });
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && (changes.running || changes.sleeping)) updateBadge();
});

function openTutorial() {
  chrome.tabs.create({ url: chrome.runtime.getURL("tutorial.html") });
}

// ---------- which tab gets the hand points ----------

async function currentTab() {
  if (activeTab.id !== null) return activeTab;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  activeTab = tab ? { id: tab.id, url: tab.url || "" } : { id: null, url: "" };
  return activeTab;
}

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  if (activeTab.id !== null && activeTab.id !== tabId) chrome.tabs.sendMessage(activeTab.id, { type: "inactive" }).catch(() => {});
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  activeTab = { id: tabId, url: (tab && tab.url) || "" };
});
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  const [tab] = await chrome.tabs.query({ active: true, windowId });
  if (tab) activeTab = { id: tab.id, url: tab.url || "" };
});
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "loading") injected.delete(tabId);
  if (tabId === activeTab.id && tab.url) activeTab.url = tab.url;
});
chrome.tabs.onRemoved.addListener((tabId) => {
  injected.delete(tabId);
  if (tabId === activeTab.id) activeTab = { id: null, url: "" };
});

async function forwardFrame(hand) {
  const tab = await currentTab();
  // the tutorial (an extension page) hears the camera page directly
  if (tab.id === null || tab.url.startsWith(EXTENSION_ORIGIN)) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "frame", via: "bg", hand });
  } catch {
    // tabs opened before the extension was installed don't have the content script yet
    if (injected.has(tab.id)) return;
    injected.add(tab.id);
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["gestures.js", "content.js"] }).catch(() => {});
  }
}

// ---------- zoom ----------

async function stepZoom(tabId, dir) {
  const current = await chrome.tabs.getZoom(tabId);
  let i = ZOOM_LEVELS.reduce((best, z, k) => (Math.abs(z - current) < Math.abs(ZOOM_LEVELS[best] - current) ? k : best), 0);
  const next = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, i + dir));
  if (next === i) return { zoom: ZOOM_LEVELS[i], changed: false };
  await chrome.tabs.setZoom(tabId, ZOOM_LEVELS[next]);
  return { zoom: ZOOM_LEVELS[next], changed: true };
}

// ---------- read aloud ----------

let voiceName;
async function pickVoice() {
  // a voice on this computer that reports words as it speaks them (for the word-by-word highlight)
  if (voiceName !== undefined) return voiceName;
  const voices = await chrome.tts.getVoices();
  const lang = (navigator.language || "en").slice(0, 2);
  const good = voices.filter((v) => !v.remote && (v.eventTypes || []).includes("word"));
  const pick = good.find((v) => (v.lang || "").startsWith(lang)) || good[0];
  voiceName = pick ? pick.voiceName : null;
  return voiceName;
}

let speakingPort = null;
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "tts") return;
  port.onMessage.addListener(async (msg) => {
    if (msg.type === "stop") {
      chrome.tts.stop();
      return;
    }
    if (msg.type === "hello") {
      // tell the page whether this voice reports each word (then a whole paragraph can be one smooth voice)
      const voice = await pickVoice();
      try {
        port.postMessage({ type: "caps", wordEvents: !!voice });
      } catch {
        // the page went away
      }
      return;
    }
    if (msg.type !== "speak") return;
    speakingPort = port;
    const voice = await pickVoice();
    chrome.tts.speak(msg.text, {
      rate: msg.rate || 1,
      enqueue: false,
      ...(voice ? { voiceName: voice } : {}),
      onEvent: (e) => {
        try {
          port.postMessage({ id: msg.id, type: e.type, charIndex: e.charIndex, length: e.length });
        } catch {
          // the page went away
        }
      },
    });
  });
  port.onDisconnect.addListener(() => {
    if (speakingPort === port) {
      chrome.tts.stop();
      speakingPort = null;
    }
  });
});

// ---------- messages ----------

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.target !== "background") return;
  switch (msg.type) {
    case "frame":
      forwardFrame(msg.hand);
      break;
    case "tracking-started":
      chrome.storage.session.set({ running: true, cameraError: "" });
      break;
    case "camera-error":
      stopTracking();
      chrome.storage.session.set({ cameraError: msg.name });
      if (msg.name === "NotAllowedError") openTutorial(); // the tutorial asks for the camera
      break;
    case "start":
      startTracking().then(() => sendResponse({ ok: true }));
      return true;
    case "stop":
      stopTracking().then(() => sendResponse({ ok: true }));
      return true;
    case "open-tutorial":
      openTutorial();
      break;
    case "zoom":
      if (!sender.tab) break;
      stepZoom(sender.tab.id, msg.dir).then(sendResponse).catch(() => sendResponse({ zoom: null }));
      return true;
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-tracking") toggleTracking();
  if (command === "toggle-sleep") {
    const { sleeping } = await chrome.storage.session.get("sleeping");
    chrome.storage.session.set({ sleeping: !sleeping });
  }
  if (command === "read-here") {
    const tab = await currentTab();
    if (tab.id === null) return;
    if (tab.url.startsWith(EXTENSION_ORIGIN)) chrome.runtime.sendMessage({ type: "read-here" }).catch(() => {});
    else chrome.tabs.sendMessage(tab.id, { type: "read-here" }).catch(() => {});
  }
});

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === "install") openTutorial();
});

// the service worker can restart at any time: resync the badge with reality
(async () => {
  if (!(await hasOffscreen())) await chrome.storage.session.set({ running: false });
  updateBadge();
})();
