// runs inside the hidden offscreen document: owns the webcam, runs the hand model, plays sound cues.
// this is the browser version of the "landmarker stuf" + webcam loop from hand_cursor1.py:
// grab webcam frames -> run mediapipe -> send the 21 hand points to the background script,
// which forwards them to whatever tab you're looking at

import { FilesetResolver, HandLandmarker } from "./lib/vision_bundle.mjs";

const send = (msg) => chrome.runtime.sendMessage({ target: "background", ...msg }).catch(() => {});

let stream = null;
let landmarker = null;
let running = false;

async function createLandmarker() {
  const vision = await FilesetResolver.forVisionTasks(chrome.runtime.getURL("lib/wasm"));
  const opts = (delegate) => ({
    baseOptions: {
      modelAssetPath: chrome.runtime.getURL("models/hand_landmarker.task"),
      delegate,
    },
    runningMode: "VIDEO", // tracks hands across frames
    numHands: 1, // only track one hand
    minHandDetectionConfidence: 0.5,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
  try {
    return await HandLandmarker.createFromOptions(vision, opts("GPU"));
  } catch (e) {
    console.warn("GPU delegate failed, falling back to CPU", e);
    return await HandLandmarker.createFromOptions(vision, opts("CPU"));
  }
}

function report(result) {
  const hand = result.landmarks && result.landmarks[0];
  // mirror x so moving your hand right moves the cursor right (same as cv2.flip(frame, 1))
  const points = hand ? hand.map((p) => ({ x: 1 - p.x, y: p.y })) : null;
  send({ type: "frame", hand: points });
}

// preferred path: read frames straight from the camera track.
// this is driven by the camera itself, so chrome can't throttle it the way it throttles
// timers in hidden pages
async function loopTrackProcessor(track) {
  const reader = new MediaStreamTrackProcessor({ track }).readable.getReader();
  while (running) {
    const { value: frame, done } = await reader.read();
    if (done || !frame) break;
    try {
      const bitmap = await createImageBitmap(frame);
      report(landmarker.detectForVideo(bitmap, performance.now()));
      bitmap.close();
    } finally {
      frame.close();
    }
  }
  reader.cancel().catch(() => {});
}

// fallback for browsers without MediaStreamTrackProcessor
async function loopVideo() {
  const video = document.getElementById("cam");
  video.srcObject = stream;
  await video.play();
  let lastTime = -1;
  const tick = () => {
    if (!running) return;
    if (video.currentTime !== lastTime) {
      lastTime = video.currentTime;
      report(landmarker.detectForVideo(video, performance.now()));
    }
    setTimeout(tick, 15);
  };
  tick();
}

async function start() {
  if (running) return;
  running = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: "user" },
      audio: false,
    });
  } catch (e) {
    running = false;
    send({ type: "camera-error", name: e.name, message: e.message });
    return;
  }
  try {
    landmarker = landmarker || (await createLandmarker());
  } catch (e) {
    running = false;
    stop();
    send({ type: "model-error", message: String(e) });
    return;
  }
  send({ type: "tracking-started" });

  const [track] = stream.getVideoTracks();
  if (typeof MediaStreamTrackProcessor !== "undefined") {
    loopTrackProcessor(track).catch((e) => console.error(e));
  } else {
    loopVideo().catch((e) => console.error(e));
  }
}

function stop() {
  running = false;
  if (stream) stream.getTracks().forEach((t) => t.stop()); // free webcam !!!! ur free now!!!!!!
  stream = null;
}

// ---------- sound cues (made on the fly, no audio files) ----------

let audio = null;
function tone(freq, start, length, { type = "sine", volume = 0.12, slideTo = null } = {}) {
  audio = audio || new AudioContext();
  const t0 = audio.currentTime + start;
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + length);
  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + length);
  osc.connect(gain).connect(audio.destination);
  osc.start(t0);
  osc.stop(t0 + length + 0.02);
}

const SOUNDS = {
  click: () => tone(1400, 0, 0.05, { type: "triangle", volume: 0.15 }),
  mode: () => { tone(660, 0, 0.08); tone(880, 0.07, 0.1); },
  zoomIn: () => tone(500, 0, 0.12, { slideTo: 900 }),
  zoomOut: () => tone(900, 0, 0.12, { slideTo: 500 }),
  read: () => { tone(784, 0, 0.12, { volume: 0.08 }); tone(1047, 0.1, 0.18, { volume: 0.08 }); },
  sleep: () => { tone(660, 0, 0.15); tone(440, 0.14, 0.25); },
  wake: () => { tone(440, 0, 0.15); tone(660, 0.14, 0.25); },
};

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.target !== "offscreen") return;
  if (msg.type === "start") start();
  if (msg.type === "stop") stop();
  if (msg.type === "sound" && SOUNDS[msg.name]) SOUNDS[msg.name]();
});

start();
