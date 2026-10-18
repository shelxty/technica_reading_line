// runs inside the hidden offscreen document.
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

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.target !== "offscreen") return;
  if (msg.type === "start") start();
  if (msg.type === "stop") stop();
});

start();
