// runs in every web page. gets the 21 hand points for each camera frame and does the
// same gesture logic as the main loop in hand_cursor1.py, but inside the page:
//   - index finger moves an on-page cursor
//   - quick pinch = click
//   - pinch + hold, then move hand up/down = zoom in/out
//   - hold index + middle finger up = toggle line highlighting
// instead of screenshotting the screen to find the line of text, we ask the page itself
// where the text is, so the highlight is exact and follows scrolling

(() => {
  if (window.__readingLineLoaded) return;
  window.__readingLineLoaded = true;

  // these are the settings that are tunable (same meaning as the python version)
  const MARGIN = 0.15; // ignore the outer 15% of the camera frame so you can reach the edges
  const SMOOTH = 0.8; // cursor smoothing. higher = steadier but laggier
  const PINCH_ENTER = 0.25; // pinch "closed" when thumb-index gap is below this fraction of palm size
  const PINCH_EXIT = 0.4;
  const HOLD_TIME = 0.4; // seconds to hold a pinch for zooming instead of clicking
  const ZOOM_STEP = 0.06; // how far (fraction of camera height) to move per zoom step
  const LOOKBACK = 6; // use cursor position from this many frames ago when a pinch starts
  const TWO_FINGER_HOLD = 0.8;
  const SNAP = 12; // snap to text within this many px if the fingertip is between lines
  const PAD = 3; // extra px around the highlighted line
  const NO_FRAME_TIMEOUT = 1000; // ms without frames before we hide the cursor
  const HIGHLIGHT_NAME = "reading-line";

  const HAND_CONNECTIONS = [
    [0, 1], [1, 2], [2, 3], [3, 4], // thumb
    [0, 5], [5, 6], [6, 7], [7, 8], // index finger
    [5, 9], [9, 10], [10, 11], [11, 12], // middle finger
    [9, 13], [13, 14], [14, 15], [15, 16], // ring finger
    [13, 17], [17, 18], [18, 19], [19, 20], // pinky
    [0, 17], // edge of the palm
  ];

  // ---------- settings (shared with the popup) ----------

  const settings = { highlightOn: false, showPreview: true };
  const safe = (fn) => {
    try { return fn(); } catch { return undefined; } // extension was reloaded under us
  };
  safe(() => chrome.storage.local.get(settings, (s) => Object.assign(settings, s)));
  safe(() => chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    for (const k in changes) settings[k] = changes[k].newValue;
    if (!settings.highlightOn) clearHighlight();
    ui.preview.style.display = settings.showPreview && visible ? "block" : "none";
  }));

  // ---------- on-page UI (cursor, line box, preview) in a shadow root ----------

  const ui = (() => {
    const host = document.createElement("div");
    host.style.cssText =
      "all: initial; position: fixed; inset: 0; pointer-events: none; z-index: 2147483647;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        .cursor { position: fixed; left: 0; top: 0; width: 18px; height: 18px; margin: -9px 0 0 -9px;
          border-radius: 50%; background: rgba(30,144,255,.55); border: 2px solid #fff;
          box-shadow: 0 0 0 1px rgba(0,0,0,.4); display: none; transition: background .1s; }
        .cursor.pinch { background: rgba(255,140,0,.8); }
        .cursor.zoom { background: rgba(160,32,240,.8); }
        .cursor.click { animation: pulse .3s ease-out; }
        @keyframes pulse { from { box-shadow: 0 0 0 0 rgba(255,140,0,.9); } to { box-shadow: 0 0 0 18px rgba(255,140,0,0); } }
        .line { position: fixed; display: none; border-radius: 3px;
          box-shadow: 0 0 0 3px #ffff00, 0 0 0 4px rgba(0,0,0,.6); }
        .preview { position: fixed; right: 12px; bottom: 12px; display: none;
          background: rgba(20,20,20,.85); border-radius: 8px; overflow: hidden; }
        canvas { display: block; }
      </style>
      <div class="line"></div>
      <div class="cursor"></div>
      <div class="preview"><canvas width="200" height="150"></canvas></div>`;
    return {
      host,
      cursor: root.querySelector(".cursor"),
      line: root.querySelector(".line"),
      preview: root.querySelector(".preview"),
      canvas: root.querySelector("canvas"),
    };
  })();

  // ::highlight() only works from a stylesheet in the page itself.
  // black text on yellow = the same high contrast look as the python overlay
  const style = document.createElement("style");
  style.textContent = `::highlight(${HIGHLIGHT_NAME}) { background-color: #ffff00; color: #000000; }`;

  let visible = false;
  function showUI() {
    if (!ui.host.isConnected) document.documentElement.appendChild(ui.host);
    if (!style.isConnected) (document.head || document.documentElement).appendChild(style);
    if (visible) return;
    visible = true;
    ui.cursor.style.display = "block";
    ui.preview.style.display = settings.showPreview ? "block" : "none";
  }
  function hideUI() {
    visible = false;
    ui.cursor.style.display = "none";
    ui.preview.style.display = "none";
    clearHighlight();
  }

  function moveCursor(x, y) {
    ui.cursor.style.transform = `translate(${x}px, ${y}px)`;
  }
  function setCursorMode(mode) {
    ui.cursor.classList.toggle("pinch", mode === "pinch");
    ui.cursor.classList.toggle("zoom", mode === "zoom");
  }

  function drawPreview(hand, status) {
    if (!settings.showPreview) return;
    const c = ui.canvas;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    if (hand) {
      const pts = hand.map((p) => [p.x * c.width, p.y * c.height]);
      ctx.strokeStyle = "#00ff00"; // green bones
      ctx.lineWidth = 2;
      for (const [a, b] of HAND_CONNECTIONS) {
        ctx.beginPath();
        ctx.moveTo(...pts[a]);
        ctx.lineTo(...pts[b]);
        ctx.stroke();
      }
      ctx.fillStyle = "#ff3030"; // red joints
      for (const [x, y] of pts) {
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.font = "bold 12px system-ui, sans-serif";
    ctx.fillStyle = "#00ffff";
    ctx.fillText(`${status} | HL ${settings.highlightOn ? "on" : "off"}`, 8, 18);
  }

  // ---------- helpers (same math as python) ----------

  function toView(lm) {
    let nx = (lm.x - MARGIN) / (1 - 2 * MARGIN);
    let ny = (lm.y - MARGIN) / (1 - 2 * MARGIN);
    nx = Math.max(0, Math.min(1, nx));
    ny = Math.max(0, Math.min(1, ny));
    return [nx * window.innerWidth, ny * window.innerHeight];
  }

  function pinchRatio(hand) {
    const gap = Math.hypot(hand[4].x - hand[8].x, hand[4].y - hand[8].y);
    const palm = Math.hypot(hand[0].x - hand[9].x, hand[0].y - hand[9].y);
    return palm > 0 ? gap / palm : 1;
  }

  const fingerUp = (hand, tip, pip) => hand[tip].y < hand[pip].y;
  const twoFingerPose = (hand) =>
    fingerUp(hand, 8, 6) && fingerUp(hand, 12, 10) &&
    !fingerUp(hand, 16, 14) && !fingerUp(hand, 20, 18);

  // ---------- line detection ----------

  const measure = document.createRange();

  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      const p = document.caretPositionFromPoint(x, y);
      return p && { node: p.offsetNode, offset: p.offset };
    }
    const r = document.caretRangeFromPoint && document.caretRangeFromPoint(x, y);
    return r && { node: r.startContainer, offset: r.startOffset };
  }

  // on-screen box of one character, or null if it isn't drawn (collapsed space, hidden, ...)
  function charRect(node, i) {
    if (i < 0 || i >= node.length) return null;
    measure.setStart(node, i);
    measure.setEnd(node, i + 1);
    for (const r of measure.getClientRects()) if (r.width > 0 && r.height > 0) return r;
    return null;
  }

  function sameLine(a, b) {
    const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return overlap > 0.5 * Math.min(a.height, b.height);
  }

  // which character is actually under (x, y)? null if the point isn't on text
  function hitChar(x, y) {
    const caret = caretAt(x, y);
    if (!caret || !caret.node || caret.node.nodeType !== Node.TEXT_NODE) return null;
    if (ui.host.contains(caret.node)) return null;
    for (const i of [caret.offset, caret.offset - 1]) {
      const r = charRect(caret.node, i);
      if (r && x >= r.left - 2 && x <= r.right + 2 && y >= r.top && y <= r.bottom) {
        return { node: caret.node, index: i, rect: r };
      }
    }
    return null;
  }

  function blockOf(node) {
    let el = node.parentElement;
    while (el && el !== document.body && getComputedStyle(el).display.startsWith("inline")) {
      el = el.parentElement;
    }
    return el || document.body;
  }

  // grow from the character under the finger to the whole visual line (left and right),
  // like the grow-up/grow-down loops in find_line() but sideways through the text
  function expandLine(hit) {
    const block = blockOf(hit.node);
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const box = { left: hit.rect.left, right: hit.rect.right, top: hit.rect.top, bottom: hit.rect.bottom };
    const grow = (r) => {
      box.left = Math.min(box.left, r.left);
      box.right = Math.max(box.right, r.right);
      box.top = Math.min(box.top, r.top);
      box.bottom = Math.max(box.bottom, r.bottom);
    };
    const LIMIT = 3000;

    // walk backwards
    let start = { node: hit.node, index: hit.index };
    walk: for (let node = hit.node, i = hit.index - 1, n = 0; node && n < LIMIT; ) {
      for (; i >= 0; i--, n++) {
        const r = charRect(node, i);
        if (!r) continue;
        if (!sameLine(r, hit.rect)) break walk;
        start = { node, index: i };
        grow(r);
      }
      walker.currentNode = node;
      node = walker.previousNode();
      i = node ? node.length - 1 : -1;
    }

    // walk forwards
    let end = { node: hit.node, index: hit.index };
    walk: for (let node = hit.node, i = hit.index + 1, n = 0; node && n < LIMIT; ) {
      for (; i < node.length; i++, n++) {
        const r = charRect(node, i);
        if (!r) continue;
        if (!sameLine(r, hit.rect)) break walk;
        end = { node, index: i };
        grow(r);
      }
      walker.currentNode = node;
      node = walker.nextNode();
      i = 0;
    }

    const range = document.createRange();
    range.setStart(start.node, start.index);
    range.setEnd(end.node, end.index + 1);
    return { range, box };
  }

  function findLine(x, y) {
    // if the fingertip is in a gap between lines, search outward for the nearest text
    for (let d = 0; d <= SNAP; d += 2) {
      const hit = hitChar(x, y - d) || (d && hitChar(x, y + d));
      if (hit) return expandLine(hit);
    }
    return null;
  }

  // ---------- highlight ----------

  let line = null; // { range, box } of the highlighted line; null = nothing highlighted

  function paintLine() {
    const b = line.box;
    Object.assign(ui.line.style, {
      display: "block",
      left: `${b.left - PAD}px`,
      top: `${b.top - PAD}px`,
      width: `${b.right - b.left + 2 * PAD}px`,
      height: `${b.bottom - b.top + 2 * PAD}px`,
    });
  }

  function clearHighlight() {
    line = null;
    ui.line.style.display = "none";
    if (window.CSS && CSS.highlights) CSS.highlights.delete(HIGHLIGHT_NAME);
  }

  function inBox(b, x, y) {
    return b.left - PAD <= x && x <= b.right + PAD && b.top - PAD <= y && y <= b.bottom + PAD;
  }

  function updateHighlight(x, y) {
    if (line && inBox(line.box, x, y)) return; // still on the same line, do nothing
    const found = findLine(x, y);
    if (!found) return clearHighlight();
    line = found;
    if (window.CSS && CSS.highlights) {
      CSS.highlights.set(HIGHLIGHT_NAME, new Highlight(line.range));
    }
    paintLine();
  }

  // the highlighted text moves when you scroll, so move the box with it
  function refreshLineBox() {
    if (!line) return;
    const r = line.range.getBoundingClientRect();
    line.box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    paintLine();
  }
  window.addEventListener("scroll", refreshLineBox, { capture: true, passive: true });
  window.addEventListener("resize", refreshLineBox, { passive: true });

  // ---------- click ----------

  function clickAt(x, y) {
    const el = document.elementFromPoint(x, y);
    if (!el) return;
    const base = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, view: window, button: 0 };
    el.dispatchEvent(new PointerEvent("pointerdown", { ...base, pointerType: "mouse", isPrimary: true, buttons: 1 }));
    el.dispatchEvent(new MouseEvent("mousedown", { ...base, buttons: 1 }));
    const focusable = el.closest("a[href], button, input, textarea, select, [tabindex], [contenteditable='true']");
    if (focusable) focusable.focus({ preventScroll: true });
    el.dispatchEvent(new PointerEvent("pointerup", { ...base, pointerType: "mouse", isPrimary: true }));
    el.dispatchEvent(new MouseEvent("mouseup", base));
    el.dispatchEvent(new MouseEvent("click", base));

    ui.cursor.classList.remove("click");
    void ui.cursor.offsetWidth; // restart the pulse animation
    ui.cursor.classList.add("click");
  }

  // ---------- zoom ----------

  // zoom the page, then scroll so whatever was under your finger stays under your finger
  // (the windows magnifier zooms around the cursor, this is the closest thing for a web page)
  async function zoom(dir, x, y) {
    const el = document.elementFromPoint(x, y);
    const before = el && el.getBoundingClientRect();
    const fx = before && before.width ? (x - before.left) / before.width : 0;
    const fy = before && before.height ? (y - before.top) / before.height : 0;
    const vx = x / window.innerWidth;
    const vy = y / window.innerHeight;

    let res = null;
    try {
      res = await chrome.runtime.sendMessage({ target: "background", type: "zoom", dir });
    } catch {
      return null;
    }
    if (!res || res.level === null) return null;

    if (el) {
      await new Promise((r) => setTimeout(r, 80)); // let the page relayout at the new zoom
      const after = el.getBoundingClientRect();
      window.scrollBy(
        after.left + fx * after.width - vx * window.innerWidth,
        after.top + fy * after.height - vy * window.innerHeight
      );
    }
    clearHighlight();
    return res.level;
  }

  // ---------- gesture state machine (the main loop from python) ----------

  let sx = window.innerWidth / 2;
  let sy = window.innerHeight / 2;
  let history = [];
  let pinching = false;
  let pinchStart = 0;
  let zoomMode = false;
  let zoomBusy = false;
  let anchorY = 0;
  let frozen = [sx, sy];
  let status = "Move your hand";
  let twoStart = null;
  let twoFired = false;
  let lastFrame = 0;

  function resetState() {
    history = [];
    pinching = false;
    zoomMode = false;
    twoStart = null;
    twoFired = false;
    setCursorMode("point");
  }

  function onFrame(hand) {
    lastFrame = performance.now();
    showUI();

    if (!hand) {
      status = "No hand";
      twoStart = null;
      twoFired = false;
      ui.cursor.style.opacity = "0.3";
      drawPreview(null, status);
      return;
    }
    ui.cursor.style.opacity = "1";

    const now = performance.now() / 1000;
    const ratio = pinchRatio(hand);

    if (!pinching) {
      const [tx, ty] = toView(hand[8]); // index fingertip
      sx = sx * SMOOTH + tx * (1 - SMOOTH);
      sy = sy * SMOOTH + ty * (1 - SMOOTH);
      history.push([sx, sy]);
      if (history.length > LOOKBACK) history.shift();
      moveCursor(sx, sy);
      status = "Pointing";
      if (settings.highlightOn) updateHighlight(sx, sy);
    }

    if (!pinching && ratio < PINCH_ENTER) {
      // pinch just started. closing your fingers makes the fingertip drift,
      // so use the position from a few frames back
      pinching = true;
      pinchStart = now;
      zoomMode = false;
      frozen = history.length ? history[0] : [sx, sy];
      moveCursor(...frozen);
      setCursorMode("pinch");
      status = "Pinch...";
    } else if (pinching && !zoomMode && now - pinchStart > HOLD_TIME) {
      zoomMode = true;
      anchorY = hand[8].y;
      setCursorMode("zoom");
      status = "Zoom: hand up = in, down = out";
    }

    if (pinching && zoomMode && !zoomBusy) {
      const dy = anchorY - hand[8].y;
      if (Math.abs(dy) > ZOOM_STEP) {
        zoomBusy = true;
        anchorY = hand[8].y; // reset reference so each step = new movement
        zoom(dy > 0 ? 1 : -1, ...frozen).then((level) => {
          zoomBusy = false;
          if (level !== null) status = `Zoom level ${level}`;
        });
      }
    }

    if (pinching && ratio > PINCH_EXIT) {
      pinching = false;
      setCursorMode("point");
      if (!zoomMode) {
        clickAt(...frozen); // quick pinch = click
        status = "CLICK";
      } else {
        status = "Zoom set";
      }
      history = [];
    }

    if (!pinching && twoFingerPose(hand)) {
      if (twoStart === null) {
        twoStart = now;
      } else if (!twoFired && now - twoStart >= TWO_FINGER_HOLD) {
        settings.highlightOn = !settings.highlightOn;
        twoFired = true;
        if (!settings.highlightOn) clearHighlight();
        safe(() => chrome.storage.local.set({ highlightOn: settings.highlightOn }));
      }
      status = twoFired
        ? `Highlight ${settings.highlightOn ? "ON" : "OFF"}`
        : `Hold... ${Math.round(((now - twoStart) / TWO_FINGER_HOLD) * 100)}%`;
    } else {
      twoStart = null;
      twoFired = false;
    }

    drawPreview(hand, status);
  }

  setInterval(() => {
    if (visible && performance.now() - lastFrame > NO_FRAME_TIMEOUT) {
      hideUI();
      resetState();
    }
  }, 500);

  safe(() => chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "frame") onFrame(msg.hand);
    if (msg.type === "stopped" || msg.type === "inactive") {
      hideUI();
      resetState();
    }
  }));
})();
