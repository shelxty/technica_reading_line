// hand pose checks + small helpers. no browser stuff in here, so it can be tested with node.
// `hand` = the 21 mediapipe points, each {x, y} from 0 to 1 (x already mirrored)
//
// point numbers: 0 wrist, 4 thumb tip, 8 index tip, 12 middle tip, 16 ring tip, 20 pinky tip
// (the joint 2 below each tip is the "pip": 6, 10, 14, 18)

(() => {
  const FINGERS = [[8, 6], [12, 10], [16, 14], [20, 18]]; // [tip, pip] for index, middle, ring, pinky

  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const palmSize = (hand) => dist(hand[0], hand[9]); // wrist to middle finger base

  // thumb-index gap divided by palm size, so moving closer/further from the camera doesn't matter
  const pinchRatio = (hand) => {
    const palm = palmSize(hand);
    return palm > 0 ? dist(hand[4], hand[8]) / palm : 1;
  };

  // a real pinch: thumb and index tips touch out in front of the hand. a fist also brings them close,
  // but there the index tip is curled into the palm - that must not count as a pinch (or it would click)
  const isPinch = (hand, enter = 0.25) => {
    const palm = palmSize(hand);
    return pinchRatio(hand) < enter && palm > 0 && dist(hand[8], hand[9]) / palm > 0.4;
  };

  const fingerUp = (hand, tip, pip) => hand[tip].y < hand[pip].y;
  // works whichever way the hand is turned: a curled finger's tip is closer to the wrist than its middle joint
  const fingerFolded = (hand, tip, pip) => dist(hand[tip], hand[0]) < dist(hand[pip], hand[0]);

  const ups = (hand) => FINGERS.map(([tip, pip]) => fingerUp(hand, tip, pip));

  const onePoint = (hand) => {
    const [i, m, r, p] = ups(hand);
    return i && !m && !r && !p;
  };
  const twoPoint = (hand) => {
    const [i, m, r, p] = ups(hand);
    return i && m && !r && !p;
  };
  const openPalm = (hand) => ups(hand).every(Boolean);
  const fist = (hand) => FINGERS.every(([tip, pip]) => fingerFolded(hand, tip, pip));
  const thumbsUp = (hand) =>
    fist(hand) &&
    hand[4].y < hand[3].y && hand[3].y < hand[2].y &&
    hand[4].y < hand[5].y - 0.3 * palmSize(hand);
  // fingers curled and the thumb starting to point up: on its way to a thumbs-up
  const thumbRising = (hand) => fist(hand) && hand[4].y < hand[3].y && hand[3].y < hand[2].y;

  // how stretched out the index finger is. drops as soon as you start curling it
  const indexExtension = (hand) => {
    const palm = palmSize(hand);
    return palm > 0 ? dist(hand[8], hand[5]) / palm : 0;
  };

  // how straight a finger is, whichever way the hand is turned: tip-to-wrist divided by
  // middle-joint-to-wrist. about 1.3 when straight, under 1 when curled
  const fingerRatio = (hand, tip, pip) => {
    const d = dist(hand[pip], hand[0]);
    return d > 0 ? dist(hand[tip], hand[0]) / d : 1;
  };

  // up / down for each finger, with two thresholds: a finger has to straighten clearly to count as up
  // and bend clearly to count as down. a half-bent finger keeps its last state instead of flickering
  class FingerState {
    constructor({ up = 1.15, down = 1.05 } = {}) {
      this.upAt = up;
      this.downAt = down;
      this.reset();
    }
    reset() {
      this.state = [false, false, false, false];
    }
    update(hand) {
      this.state = FINGERS.map(([tip, pip], i) => {
        const r = fingerRatio(hand, tip, pip);
        if (r >= this.upAt) return true;
        if (r <= this.downAt) return false;
        return this.state[i];
      });
      return this.state;
    }
  }

  // the pose from the steady finger states (used by the app; poseName below is the one-frame version)
  function poseFrom(hand, [i, m, r, p], pinchEnter = 0.25) {
    if (isPinch(hand, pinchEnter)) return "pinch";
    if (i && m && r && p) return "palm";
    if (!i && !m && !r && !p && thumbsUp(hand)) return "thumbs";
    if (i && m && !r && !p) return "two";
    if (i && !m && !r && !p) return "one";
    if (!i && !m && !r && !p) return "fist";
    return "none";
  }

  // what the hand is doing, in one word
  function poseName(hand, pinchEnter = 0.25) {
    if (isPinch(hand, pinchEnter)) return "pinch";
    if (openPalm(hand)) return "palm";
    if (thumbsUp(hand)) return "thumbs";
    if (twoPoint(hand)) return "two";
    if (onePoint(hand)) return "one";
    if (fist(hand)) return "fist";
    return "none";
  }

  // a pose has to show up for a few frames in a row before we believe it, so a finger that flickers
  // up for one frame doesn't switch modes
  class PoseStabilizer {
    constructor(frames = 4) {
      this.frames = frames;
      this.reset();
    }
    reset() {
      this.pose = "none";
      this.candidate = null;
      this.count = 0;
    }
    update(raw) {
      if (raw === this.pose) {
        this.candidate = null;
        this.count = 0;
      } else if (raw === this.candidate) {
        if (++this.count >= this.frames) {
          this.pose = raw;
          this.candidate = null;
          this.count = 0;
        }
      } else {
        this.candidate = raw;
        this.count = 1;
      }
      return this.pose;
    }
  }

  // One Euro filter (Casiez et al. 2012): smooths a noisy value without making it laggy.
  // barely moving = lots of smoothing (no jitter), moving fast = little smoothing (no lag)
  class OneEuro {
    constructor(minCutoff = 0.6, beta = 0.004, dCutoff = 1.0) {
      Object.assign(this, { minCutoff, beta, dCutoff });
      this.reset();
    }
    reset() {
      this.x = null;
      this.dx = 0;
      this.t = null;
    }
    static alpha(cutoff, dt) {
      const tau = 1 / (2 * Math.PI * cutoff);
      return 1 / (1 + tau / dt);
    }
    filter(x, t) {
      if (this.x === null) {
        this.x = x;
        this.t = t;
        return x;
      }
      const dt = Math.max(t - this.t, 1e-3);
      const ad = OneEuro.alpha(this.dCutoff, dt);
      this.dx = ad * ((x - this.x) / dt) + (1 - ad) * this.dx;
      const a = OneEuro.alpha(this.minCutoff + this.beta * Math.abs(this.dx), dt);
      this.x = a * x + (1 - a) * this.x;
      this.t = t;
      return this.x;
    }
  }

  // wave = the open hand swinging left-right a few times (from hand_cursor1.py)
  class WaveDetector {
    constructor({ window = 2, amp = 0.05, swings = 3, cooldown = 1.5 } = {}) {
      Object.assign(this, { window, amp, swings, cooldown });
      this.samples = [];
      this.lastWave = -Infinity;
    }
    // t in seconds, x = hand position (0..1). returns true once when a wave is completed
    add(t, x) {
      this.samples.push([t, x]);
      while (this.samples.length && this.samples[0][0] < t - this.window) this.samples.shift();
      if (t - this.lastWave < this.cooldown || this.samples.length < 2) return false;
      let last = this.samples[0][1];
      let dir = 0;
      let swings = 0;
      for (const [, sx] of this.samples) {
        if (dir !== 1 && sx - last > this.amp) {
          dir = 1;
          swings++;
          last = sx;
        } else if (dir !== -1 && last - sx > this.amp) {
          dir = -1;
          swings++;
          last = sx;
        } else if ((dir === 1 && sx > last) || (dir === -1 && sx < last)) {
          last = sx; // keep following the swing to its furthest point
        }
      }
      if (swings >= this.swings) {
        this.lastWave = t;
        this.samples = [];
        return true;
      }
      return false;
    }
    clear() {
      this.samples = [];
    }
  }

  // remembers the last thing (line / link) the highlight rested on for at least `hold` seconds,
  // so a thumbs-up reads what you meant, not whatever the fingertip slid over while curling
  class StableTarget {
    constructor(hold = 0.35) {
      this.hold = hold;
      this.reset();
    }
    reset() {
      this.current = null;
      this.since = 0;
      this.stable = null;
      this.stableAt = 0;
    }
    update(key, value, t) {
      if (key !== (this.current && this.current.key)) {
        this.current = key ? { key, value } : null;
        this.since = t;
      }
      if (this.current && t - this.since >= this.hold) {
        this.stable = this.current.value;
        this.stableAt = t;
      }
    }
  }

  // drag scrolling: the page follows the palm like a sheet of paper, then glides a little
  class DragScroller {
    constructor({ gain = 2.2, deadzone = 0.003, friction = 0.9 } = {}) {
      Object.assign(this, { gain, deadzone, friction });
      this.reset();
    }
    reset() {
      this.lastY = null;
      this.velocity = 0; // px per frame, for the glide afterwards
    }
    // y = palm height (0..1), dx = sideways movement this frame. returns px to scroll this frame
    move(y, dx, viewportH, invert = false) {
      if (this.lastY === null) {
        this.lastY = y;
        return 0;
      }
      const dy = y - this.lastY;
      this.lastY = y;
      // ignore jitter, and sideways swings (that's a wave, not a scroll)
      if (Math.abs(dy) < this.deadzone || Math.abs(dx) > 2 * Math.abs(dy)) {
        this.velocity *= this.friction;
        return 0;
      }
      // hand moves up -> the paper moves up -> you see what's further down
      const px = -dy * this.gain * viewportH * (invert ? -1 : 1);
      this.velocity = 0.6 * this.velocity + 0.4 * px;
      return px;
    }
    // called every frame after the palm is gone: returns the glide distance (0 when stopped)
    glide() {
      this.lastY = null;
      this.velocity *= this.friction;
      if (Math.abs(this.velocity) < 0.5) this.velocity = 0;
      return this.velocity;
    }
  }

  // chrome's own zoom steps, limited to 50% - 300%
  const ZOOM_LEVELS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];

  const api = {
    dist, palmSize, pinchRatio, isPinch, fingerRatio, FingerState, poseFrom, fingerUp, fingerFolded, onePoint, twoPoint, openPalm, fist,
    thumbsUp, thumbRising, indexExtension, poseName, PoseStabilizer, OneEuro, WaveDetector,
    StableTarget, DragScroller, ZOOM_LEVELS,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.RLGestures = api;
})();
