// run from extension_v2:  node --test tests
const test = require("node:test");
const assert = require("node:assert");
const G = require("../gestures.js");

// fake upright hand, palm facing the camera. palm size (wrist to middle base) = 0.2
const MCP_X = { 5: 0.45, 9: 0.5, 13: 0.55, 17: 0.6 };
function hand({ index = true, middle = false, ring = false, pinky = false, thumb = "tucked", x = 0, y = 0 } = {}) {
  const P = (px, py) => ({ x: px + x, y: py + y });
  const pts = Array.from({ length: 21 }, () => P(0, 0));
  pts[0] = P(0.5, 0.8);
  for (const [base, up] of [[5, index], [9, middle], [13, ring], [17, pinky]]) {
    const bx = MCP_X[base];
    pts[base] = P(bx, 0.6);
    const ys = up ? [0.52, 0.48, 0.44] : [0.55, 0.58, 0.63];
    ys.forEach((yy, i) => (pts[base + 1 + i] = P(bx, yy)));
  }
  pts[1] = P(0.42, 0.75);
  const thumbs = {
    out: [[0.38, 0.7], [0.35, 0.65], [0.33, 0.6]],
    up: [[0.4, 0.68], [0.4, 0.58], [0.4, 0.48]],
    tucked: [[0.44, 0.7], [0.46, 0.67], [0.47, 0.65]],
    pinch: [[0.42, 0.65], [0.44, 0.52], [0.45, 0.45]],
  }[thumb];
  thumbs.forEach(([px, py], i) => (pts[2 + i] = P(px, py)));
  return pts;
}

test("one finger = point, two fingers = highlight", () => {
  assert.equal(G.poseName(hand({ index: true })), "one");
  assert.equal(G.poseName(hand({ index: true, middle: true })), "two");
});

test("open palm, thumbs up, fist, pinch", () => {
  assert.equal(G.poseName(hand({ index: true, middle: true, ring: true, pinky: true, thumb: "out" })), "palm");
  assert.equal(G.poseName(hand({ index: false, thumb: "up" })), "thumbs");
  assert.equal(G.poseName(hand({ index: false, thumb: "tucked" })), "fist");
  assert.equal(G.poseName(hand({ thumb: "pinch" })), "pinch");
});

test("thumb rising only with curled fingers", () => {
  assert.ok(G.thumbRising(hand({ index: false, thumb: "up" })));
  assert.ok(!G.thumbRising(hand({ index: true, thumb: "up" })));
});

test("index extension drops when curling", () => {
  assert.ok(G.indexExtension(hand({ index: false })) < 0.75 * G.indexExtension(hand({ index: true })));
});

test("pose must hold for 3 frames before switching", () => {
  const s = new G.PoseStabilizer(3);
  assert.equal(s.update("one"), "none");
  assert.equal(s.update("one"), "none");
  assert.equal(s.update("one"), "one");
  assert.equal(s.update("two"), "one"); // one flicker frame doesn't switch
  assert.equal(s.update("one"), "one");
  s.update("two");
  s.update("two");
  assert.equal(s.update("two"), "two");
});

test("one euro filter: steady when still, keeps up when moving", () => {
  let seed = 1;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 2 - 1;
  const f = new G.OneEuro();
  const out = [];
  for (let i = 0; i < 90; i++) out.push(f.filter(500 + rand() * 8, i / 30));
  const tail = out.slice(30);
  assert.ok(Math.max(...tail) - Math.min(...tail) < 6);
  const g = new G.OneEuro();
  for (let i = 0; i < 30; i++) g.filter(100, i / 30);
  let x = 0;
  for (let i = 30; i < 60; i++) x = g.filter(100 + (i - 29) * 33.3, i / 30);
  assert.ok(x > 700);
});

test("wave: three swings toggle, small wobble doesn't", () => {
  const w = new G.WaveDetector();
  let fired = false;
  const xs = [0.5, 0.58, 0.5, 0.42, 0.5, 0.58];
  xs.forEach((x, i) => (fired = w.add(i * 0.15, x) || fired));
  assert.ok(fired);
  const calm = new G.WaveDetector();
  let any = false;
  for (let i = 0; i < 30; i++) any = calm.add(i / 30, 0.5 + (i % 2 ? 0.01 : -0.01)) || any;
  assert.ok(!any);
});

test("stable target: reads what you rested on, not what you slid over", () => {
  const s = new G.StableTarget(0.35);
  for (let i = 0; i < 20; i++) s.update("A", "line A", i / 30);
  for (let i = 0; i < 6; i++) s.update("B", "line B", 20 / 30 + i / 30);
  assert.equal(s.stable, "line A");
});

test("drag scroll: page follows the palm, then glides and stops", () => {
  const d = new G.DragScroller();
  assert.equal(d.move(0.6, 0, 1000), 0);
  const px = d.move(0.55, 0, 1000); // hand up
  assert.ok(px > 0); // -> scroll down (the paper moves up)
  assert.ok(d.move(0.5, 0, 1000, true) < 0); // inverted
  assert.equal(d.move(0.5, 0.2, 1000), 0); // sideways (a wave) doesn't scroll
  const d2 = new G.DragScroller();
  d2.move(0.6, 0, 1000);
  d2.move(0.5, 0, 1000);
  let g = d2.glide();
  assert.ok(g > 0);
  for (let i = 0; i < 200; i++) g = d2.glide();
  assert.equal(g, 0);
});

test("zoom goes 50% to 300% with 100% in it", () => {
  assert.equal(G.ZOOM_LEVELS[0], 0.5);
  assert.equal(G.ZOOM_LEVELS.at(-1), 3);
  assert.ok(G.ZOOM_LEVELS.includes(1));
});

test("a fist with the thumb over the fingers is not a pinch (no accidental clicks)", () => {
  const f = hand({ index: false, thumb: "tucked" });
  assert.ok(G.pinchRatio(f) < 0.25); // thumb and index tips are close...
  assert.ok(!G.isPinch(f)); // ...but it's a fist
  assert.ok(G.isPinch(hand({ thumb: "pinch" })));
});

test("a half-bent finger keeps its state instead of flickering", () => {
  const f = new G.FingerState();
  const straight = hand({ index: true, middle: true });
  assert.deepEqual(f.update(straight), [true, true, false, false]);
  // middle finger half bent: ratio between the two thresholds, wobbling a little
  const half = (wobble) => {
    const h = hand({ index: true, middle: true });
    const wrist = h[0], pip = h[10];
    const target = G.dist(pip, wrist) * (1.1 + wobble); // tip-to-wrist distance for ratio 1.1 +- wobble
    const ux = (h[12].x - wrist.x), uy = (h[12].y - wrist.y), len = Math.hypot(ux, uy);
    h[12] = { x: wrist.x + (ux / len) * target, y: wrist.y + (uy / len) * target };
    return h;
  };
  for (const w of [0.03, -0.03, 0.02, -0.04, 0.03]) assert.equal(f.update(half(w))[1], true); // stays up
  f.update(hand({ index: true })); // clearly bent now
  for (const w of [0.03, -0.03, 0.02]) assert.equal(f.update(half(w))[1], false); // stays down
});

test("steady poses: one, two, palm, thumbs, fist", () => {
  const pose = (opts) => {
    const h = hand(opts);
    return G.poseFrom(h, new G.FingerState().update(h));
  };
  assert.equal(pose({ index: true }), "one");
  assert.equal(pose({ index: true, middle: true }), "two");
  assert.equal(pose({ index: true, middle: true, ring: true, pinky: true, thumb: "out" }), "palm");
  assert.equal(pose({ index: false, thumb: "up" }), "thumbs");
  assert.equal(pose({ index: false, thumb: "tucked" }), "fist");
  assert.equal(pose({ thumb: "pinch" }), "pinch");
});
