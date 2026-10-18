// Reading Line v2 - runs in every web page (and in the tutorial page).
// gets the 21 hand points for every camera frame and turns them into:
//   ☝️ one finger      -> cursor
//   ✌️ two fingers     -> cursor + highlight what's under it (a line of text, or just the link / button)
//   👍 thumbs up       -> read the highlighted line out loud, word by word
//   🖐️ open palm       -> drag the page up / down like paper
//   🤏 pinch           -> click.  pinch + hold, then up / down -> zoom 50% - 300%
//   👋 wave            -> sleep / wake (so you can talk with your hands)

(() => {
  if (window.__readingLineV2) return;
  window.__readingLineV2 = true;

  const G = globalThis.RLGestures;
  const IS_EXTENSION_PAGE = location.protocol === "chrome-extension:";

  // tuning (the user-facing ones are in the popup)
  const T = {
    margin: 0.15, // ignore the outer 15% of the camera picture so you can reach the screen edges
    pinchEnter: 0.25,
    pinchExit: 0.4,
    holdToZoom: 0.45, // hold a pinch this long to zoom instead of click
    zoomStep: 0.06, // hand movement (fraction of camera height) per zoom step
    clickConfirm: 0.2, // wait this long before clicking, so a thumbs-up can cancel it
    lookback: 0.25, // when a pinch / curl starts, use where the cursor was this long ago
    curlRatio: 0.75, // index finger bent below this much of its length = it's curling: hold the cursor
    readHold: 0.4, // hold a thumbs-up this long to read
    stillPx: 2, // ignore wobbles smaller than this
    keepHighlight: 3, // after leaving ✌️, the highlight stays this many seconds (time to do 👍)
    restTime: 0.35, // the highlight has to rest on something this long to count as "the line you meant"
    snap: 12, // look this far above / below the finger for text if it's between lines
    pad: 3,
    noFrameTimeout: 1200,
  };

  const DEFAULTS = {
    soundOn: true,
    wordByWord: true,
    sayKind: true,
    showPreview: true,
    voiceRate: 1,
    cursorSize: 1,
    invertScroll: false,
    readParagraph: true, // after the line, keep reading the rest of the paragraph
    holdScale: 1, // 1 = normal, 1.5 = relaxed, 2 = extra relaxed: every "hold" takes this much longer
  };
  const S = { ...DEFAULTS };
  const hold = (name) => T[name] * (S.holdScale || 1);
  const safe = (fn) => {
    try {
      return fn();
    } catch {
      return undefined; // the extension was reloaded under us
    }
  };
  safe(() => chrome.storage.local.get(DEFAULTS, (s) => {
    Object.assign(S, s);
    applySettings();
  }));
  safe(() => chrome.storage.session.get({ sleeping: false }, (s) => setSleeping(!!s.sleeping, false)));
  safe(() => chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local") {
      for (const k in changes) if (k in DEFAULTS) S[k] = changes[k].newValue;
      applySettings();
    }
    if (area === "session" && changes.sleeping) setSleeping(!!changes.sleeping.newValue, false);
  }));

  // tutorial page listens to these to tick off each gesture
  const emit = (event) => window.dispatchEvent(new CustomEvent("readingline", { detail: { event } }));
  const sound = (name) => {
    if (S.soundOn) safe(() => chrome.runtime.sendMessage({ target: "offscreen", type: "sound", name }).catch(() => {}));
  };

  // ---------------------------------------------------------------- on-page UI (shadow DOM)

  const MODES = {
    // every color has at least 4.5:1 contrast with the white badge text (WCAG AA, checked in tests)
    point: { color: "#1d4ed8", label: "☝️ Point" },
    highlight: { color: "#b45309", label: "✌️ Highlight" },
    scroll: { color: "#0f766e", label: "🖐️ Scroll" },
    pinch: { color: "#c2410c", label: "🤏 Pinch" },
    zoom: { color: "#6d28d9", label: "🔍 Zoom" },
    thumbs: { color: "#15803d", label: "👍 Hold to read" },
    read: { color: "#15803d", label: "🔊 Reading" },
    sleep: { color: "#475569", label: "💤 Sleeping · wave to wake" },
  };
  const CHIPS = [
    ["point", "☝️", "Point"],
    ["highlight", "✌️", "Highlight"],
    ["read", "👍", "Read"],
    ["scroll", "🖐️", "Scroll"],
    ["pinch", "🤏", "Click"],
    ["zoom", "🔍", "Zoom"],
  ];

  const ui = (() => {
    const host = document.createElement("div");
    host.setAttribute("aria-hidden", "true"); // decorative; the popup / status text carry the meaning
    host.style.cssText = "all:initial;position:fixed;inset:0;pointer-events:none;z-index:2147483647;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        :host { --mode: #1d4ed8; --size: 1; }
        * { box-sizing: border-box; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
        .cursor { position: fixed; left: 0; top: 0; display: none; will-change: transform; }
        .arrow { width: calc(26px * var(--size)); height: calc(26px * var(--size));
          filter: drop-shadow(0 0 6px var(--mode)) drop-shadow(0 1px 1px rgba(0,0,0,.5)); transition: filter .2s; }
        .ring { position: absolute; left: calc(-14px * var(--size)); top: calc(-14px * var(--size));
          width: calc(28px * var(--size)); height: calc(28px * var(--size)); }
        .ring circle { fill: none; stroke: var(--mode); stroke-width: 3; stroke-linecap: round;
          transform: rotate(-90deg); transform-origin: 50% 50%; }
        .badge { position: absolute; left: calc(24px * var(--size)); top: calc(22px * var(--size));
          white-space: nowrap; padding: 5px 11px; border-radius: 999px; font-size: 13px; font-weight: 650;
          color: #fff; background: var(--mode); box-shadow: 0 4px 14px rgba(0,0,0,.25);
          opacity: 0; transform: translateY(4px) scale(.96); transition: opacity .18s, transform .18s, background .2s; }
        .badge.show { opacity: 1; transform: none; }
        .ripple { position: fixed; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%;
          border: 3px solid #c2410c; opacity: 0; }
        .ripple.go { animation: ripple .45s ease-out; }
        @keyframes ripple { from { opacity: .9; transform: scale(.3); } to { opacity: 0; transform: scale(1.6); } }
        .hl { position: fixed; display: none; border-radius: 5px;
          box-shadow: 0 0 0 3px #ffde00, 0 0 0 4.5px rgba(0,0,0,.55), 0 6px 18px rgba(0,0,0,.18);
          transition: left .08s, top .08s, width .08s, height .08s; }
        .hl.component { box-shadow: 0 0 0 4px #ffde00, 0 0 0 5.5px rgba(0,0,0,.6), 0 6px 18px rgba(0,0,0,.2); }
        .hl.reading { box-shadow: 0 0 0 3px #22c55e, 0 0 0 4.5px rgba(0,0,0,.55), 0 6px 18px rgba(0,0,0,.18); }
        .hl .tag { position: absolute; left: -4px; top: -27px; padding: 2px 8px; border-radius: 6px 6px 6px 0;
          font-size: 12px; font-weight: 700; color: #111; background: #ffde00; white-space: nowrap; }
        .hl.reading .tag { background: #22c55e; color: #052e13; }
        .hud { position: fixed; right: 16px; bottom: 16px; width: 248px; display: none; padding: 12px;
          border-radius: 18px; color: #f8fafc; background: rgba(15, 23, 42, .9);
          box-shadow: 0 12px 40px rgba(0,0,0,.35), inset 0 0 0 1px rgba(255,255,255,.08);
          backdrop-filter: blur(10px); }
        .top { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
        .dot { width: 10px; height: 10px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 10px #22c55e; }
        .hud.sleep .dot { background: #94a3b8; box-shadow: none; }
        .pill { margin-left: auto; padding: 2px 8px; border-radius: 999px; font-size: 11px; background: rgba(34,197,94,.18); color: #86efac; }
        .hud.sleep .pill { background: rgba(148,163,184,.2); color: #e2e8f0; }
        canvas { display: block; width: 224px; height: 132px; border-radius: 12px; background: rgba(255,255,255,.04); }
        .chips { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; margin-top: 8px; }
        .chip { display: flex; flex-direction: column; align-items: center; gap: 1px; padding: 5px 0; border-radius: 10px;
          font-size: 16px; background: rgba(255,255,255,.06); transition: all .15s; }
        .chip span { font-size: 10px; font-weight: 600; color: #cbd5e1; }
        .chip.on { opacity: 1; background: var(--mode); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.3); }
        .chip.on span { color: #fff; }
        .status { margin-top: 8px; min-height: 18px; font-size: 13px; font-weight: 600; color: #fef9c3; }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
      </style>
      <div class="hl"><div class="tag"></div></div>
      <div class="ripple"></div>
      <div class="cursor">
        <svg class="ring" viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" stroke-dasharray="75.4" stroke-dashoffset="75.4"/></svg>
        <svg class="arrow" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8.2 16.4 L11.6 24 L15 22.5 L11.7 15 L19 15 Z"
          fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>
        <div class="badge"></div>
      </div>
      <div class="hud">
        <div class="top"><div class="dot"></div>Reading Line<div class="pill">Active</div></div>
        <canvas width="448" height="264"></canvas>
        <div class="chips">${CHIPS.map(([k, e, l]) => `<div class="chip" data-k="${k}">${e}<span>${l}</span></div>`).join("")}</div>
        <div class="status"></div>
      </div>`;
    const $ = (s) => root.querySelector(s);
    return {
      host,
      cursor: $(".cursor"),
      ring: $(".ring circle"),
      badge: $(".badge"),
      ripple: $(".ripple"),
      hl: $(".hl"),
      tag: $(".hl .tag"),
      hud: $(".hud"),
      pill: $(".pill"),
      canvas: $("canvas"),
      chips: [...root.querySelectorAll(".chip")],
      status: $(".status"),
    };
  })();

  // ::highlight() only works from a stylesheet in the page itself.
  // black on yellow (19.6:1 contrast) for the line, black on orange (9:1) for the word being read
  const pageStyle = document.createElement("style");
  pageStyle.textContent = `
    ::highlight(rl-line) { background-color: #ffff00; color: #000; }
    ::highlight(rl-word) { background-color: #ff8c00; color: #000; }`;

  let visible = false;
  function attachUI() {
    if (!ui.host.isConnected) document.documentElement.appendChild(ui.host);
    if (!pageStyle.isConnected) (document.head || document.documentElement).appendChild(pageStyle);
  }
  function showUI() {
    attachUI();
    if (visible) return;
    visible = true;
    ui.cursor.style.display = "block";
    ui.hud.style.display = S.showPreview ? "block" : "none";
  }
  function hideUI() {
    visible = false;
    ui.cursor.style.display = "none";
    ui.hud.style.display = "none";
    clearHighlight();
  }
  function applySettings() {
    ui.host.style.setProperty("--size", String(S.cursorSize));
    ui.hud.style.display = S.showPreview && visible ? "block" : "none";
  }

  let mode = "point";
  let badgeTimer = 0;
  function setMode(next, label) {
    const m = MODES[next];
    ui.host.style.setProperty("--mode", m.color);
    const text = label || m.label;
    if (ui.badge.textContent !== text) ui.badge.textContent = text;
    if (next !== mode) {
      ui.badge.classList.add("show");
      clearTimeout(badgeTimer);
      // the plain pointer only flashes its badge; every other mode keeps it on while it lasts
      if (next === "point") badgeTimer = setTimeout(() => ui.badge.classList.remove("show"), 900);
      if (next !== "point" && next !== "pinch") emitModeOnce(next);
      mode = next;
    } else if (next !== "point") {
      ui.badge.classList.add("show");
    }
    ui.chips.forEach((c) => c.classList.toggle("on", c.dataset.k === (next === "thumbs" ? "read" : next)));
  }
  const emitted = new Set();
  function emitModeOnce(m) {
    // highlight / scroll / zoom... -> tell the tutorial (only once per mode change)
    if (m === "highlight" || m === "scroll") emit(m);
    emitted.add(m);
  }

  function moveCursor(x, y) {
    ui.cursor.style.transform = `translate(${x}px, ${y}px)`;
  }
  function setRing(progress) {
    ui.ring.style.strokeDashoffset = String(75.4 * (1 - Math.max(0, Math.min(1, progress))));
  }
  function ripple(x, y) {
    ui.ripple.style.left = `${x}px`;
    ui.ripple.style.top = `${y}px`;
    ui.ripple.classList.remove("go");
    void ui.ripple.offsetWidth; // restart the animation
    ui.ripple.classList.add("go");
  }
  let lastStatus = "";
  function setStatus(text) {
    if (text !== lastStatus) ui.status.textContent = lastStatus = text;
  }

  const HAND_LINES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11],
    [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
  function drawHud(hand) {
    if (!S.showPreview) return;
    const c = ui.canvas;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    if (!hand) {
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "600 26px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Show your hand to the camera", c.width / 2, c.height / 2);
      return;
    }
    const pts = hand.map((p) => [p.x * c.width, p.y * c.height]);
    ctx.lineCap = "round";
    ctx.lineWidth = 5;
    ctx.strokeStyle = MODES[mode].color;
    for (const [a, b] of HAND_LINES) {
      ctx.beginPath();
      ctx.moveTo(...pts[a]);
      ctx.lineTo(...pts[b]);
      ctx.stroke();
    }
    ctx.fillStyle = "#fff";
    for (const [x, y] of pts) {
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // ---------------------------------------------------------------- what's under the cursor

  const COMPONENTS = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary", "[contenteditable=true]",
    "[role=button]", "[role=link]", "[role=tab]", "[role=menuitem]", "[role=checkbox]", "[role=radio]",
    "[role=switch]", "[role=option]", "[role=treeitem]", "[role=slider]", "[role=combobox]",
  ].join(",");

  function kindOf(el) {
    const role = el.getAttribute("role");
    if (role) return { menuitem: "menu item", treeitem: "tree item", combobox: "dropdown" }[role] || role;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "select") return "dropdown";
    if (tag === "textarea" || el.isContentEditable) return "text field";
    if (tag === "summary") return "button";
    if (tag === "input") {
      const type = (el.type || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(type)) return "button";
      if (type === "checkbox" || type === "radio") return type === "radio" ? "radio button" : "checkbox";
      if (type === "range") return "slider";
      return "text field";
    }
    return "button";
  }

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  function nameOf(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) return clean(aria);
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const text = by.split(/\s+/).map((id) => document.getElementById(id)?.innerText).join(" ");
      if (clean(text)) return clean(text);
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT") {
      const label = el.labels && el.labels[0] ? el.labels[0].innerText : "";
      const value = el.type === "button" || el.type === "submit" ? el.value : "";
      return clean(label || value || el.placeholder || el.title || el.name);
    }
    const text = clean(el.innerText);
    if (text) return text.slice(0, 160);
    const img = el.querySelector("img[alt]");
    return clean(img ? img.alt : el.title);
  }

  function componentAt(x, y) {
    const hit = document.elementFromPoint(x, y);
    if (!hit) return null;
    const el = hit.closest(COMPONENTS);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return null;
    // something huge (a whole card that's one link) -> highlight line by line instead
    if (r.width * r.height > 0.15 * innerWidth * innerHeight) return null;
    return { key: el, kind: kindOf(el), el, name: nameOf(el) };
  }

  // --- lines of text: ask the page where its text is (exact, follows scrolling, works when zoomed) ---
  const measure = document.createRange();
  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      const p = document.caretPositionFromPoint(x, y);
      return p && { node: p.offsetNode, offset: p.offset };
    }
    const r = document.caretRangeFromPoint && document.caretRangeFromPoint(x, y);
    return r && { node: r.startContainer, offset: r.startOffset };
  }
  function charRect(node, i) {
    if (i < 0 || i >= node.length) return null;
    measure.setStart(node, i);
    measure.setEnd(node, i + 1);
    for (const r of measure.getClientRects()) if (r.width > 0 && r.height > 0) return r;
    return null;
  }
  const sameLine = (a, b) => Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5 * Math.min(a.height, b.height);
  function hitChar(x, y) {
    const c = caretAt(x, y);
    if (!c || !c.node || c.node.nodeType !== Node.TEXT_NODE) return null;
    for (const i of [c.offset, c.offset - 1]) {
      const r = charRect(c.node, i);
      if (r && x >= r.left - 2 && x <= r.right + 2 && y >= r.top && y <= r.bottom) return { node: c.node, index: i, rect: r };
    }
    return null;
  }
  function blockOf(node) {
    let el = node.parentElement;
    while (el && el !== document.body && getComputedStyle(el).display.startsWith("inline")) el = el.parentElement;
    return el || document.body;
  }
  // grow from the character under the finger to the whole visual line, left and right
  function expandLine(hit) {
    const walker = document.createTreeWalker(blockOf(hit.node), NodeFilter.SHOW_TEXT);
    let start = { node: hit.node, index: hit.index };
    let end = { node: hit.node, index: hit.index };
    const LIMIT = 3000;
    back: for (let node = hit.node, i = hit.index - 1, n = 0; node && n < LIMIT;) {
      for (; i >= 0; i--, n++) {
        const r = charRect(node, i);
        if (!r) continue;
        if (!sameLine(r, hit.rect)) break back;
        start = { node, index: i };
      }
      walker.currentNode = node;
      node = walker.previousNode();
      i = node ? node.length - 1 : -1;
    }
    fwd: for (let node = hit.node, i = hit.index + 1, n = 0; node && n < LIMIT;) {
      for (; i < node.length; i++, n++) {
        const r = charRect(node, i);
        if (!r) continue;
        if (!sameLine(r, hit.rect)) break fwd;
        end = { node, index: i };
      }
      walker.currentNode = node;
      node = walker.nextNode();
      i = 0;
    }
    const range = document.createRange();
    range.setStart(start.node, start.index);
    range.setEnd(end.node, end.index + 1);
    return range;
  }
  function lineAt(x, y) {
    for (let d = 0; d <= T.snap; d += 2) {
      const hit = hitChar(x, y - d) || (d && hitChar(x, y + d));
      if (hit) {
        const range = expandLine(hit);
        const r = range.getBoundingClientRect();
        return { key: `line:${Math.round(r.top + scrollY)}:${Math.round(r.left + scrollX)}`, kind: "line", range };
      }
    }
    return null;
  }

  const rectOf = (t) => (t.el ? t.el.getBoundingClientRect() : t.range.getBoundingClientRect());
  const inside = (r, x, y) => r && x >= r.left - T.pad && x <= r.right + T.pad && y >= r.top - T.pad && y <= r.bottom + T.pad;

  // ---------------------------------------------------------------- highlight

  let target = null; // what's highlighted: {key, kind, range?, el?, name?}
  let lastCheck = 0;
  const hasHighlights = () => window.CSS && CSS.highlights && typeof Highlight !== "undefined";

  function paintTarget(t, reading = false) {
    const r = rectOf(t);
    Object.assign(ui.hl.style, {
      display: "block",
      left: `${r.left - T.pad}px`,
      top: `${r.top - T.pad}px`,
      width: `${r.width + 2 * T.pad}px`,
      height: `${r.height + 2 * T.pad}px`,
    });
    ui.hl.classList.toggle("component", t.kind !== "line");
    ui.hl.classList.toggle("reading", reading);
    ui.tag.textContent = reading ? "🔊 Reading · 👍 to stop" : t.kind === "line" ? "✌️ Line" : `✌️ ${t.kind[0].toUpperCase()}${t.kind.slice(1)}`;
    ui.tag.style.top = r.top < 34 ? `${r.height + 2 * T.pad + 4}px` : "-27px"; // keep the tag on screen
    if (hasHighlights()) {
      let range = t.range;
      if (!range && t.el && t.el.textContent.trim() && !/^(INPUT|TEXTAREA|SELECT)$/.test(t.el.tagName)) {
        range = document.createRange();
        range.selectNodeContents(t.el);
      }
      if (range) CSS.highlights.set("rl-line", new Highlight(range));
      else CSS.highlights.delete("rl-line");
    }
  }

  function clearHighlight() {
    target = null;
    ui.hl.style.display = "none";
    if (hasHighlights()) {
      CSS.highlights.delete("rl-line");
      CSS.highlights.delete("rl-word");
    }
  }

  function updateHighlight(x, y, t) {
    const onIt = target && inside(rectOf(target), x, y);
    // on a line, keep checking every so often whether you moved onto a link inside it
    if (onIt && !(target.kind === "line" && t - lastCheck > 0.1)) return;
    lastCheck = t;
    const next = componentAt(x, y) || (onIt && target.kind === "line" ? target : lineAt(x, y));
    if (!next) {
      if (!onIt) clearHighlight();
      return;
    }
    if (!target || next.key !== target.key) {
      target = next;
      paintTarget(target);
      emit("highlight");
    }
  }

  // the highlighted text moves when you scroll, so move the frame with it
  const repaint = () => {
    if (reading) paintTarget(reading.target, true);
    else if (target) paintTarget(target);
  };
  addEventListener("scroll", repaint, { capture: true, passive: true });
  addEventListener("resize", repaint, { passive: true });

  // ---------------------------------------------------------------- read aloud (word by word)

  // reading = { id, lines: [line targets], spans: [{start, end}] per line, text, map, index, target, oneVoice }
  let reading = null;
  let readId = 0;
  let resumeAt = null; // the line reading was stopped on
  let resumeUntil = 0;
  let port = null;
  let wordEvents = false; // does this computer's voice tell us each word? (asked once)

  function ttsPort() {
    if (port) return port;
    port = chrome.runtime.connect({ name: "tts" });
    port.onMessage.addListener(onTtsEvent);
    port.onDisconnect.addListener(() => (port = null));
    port.postMessage({ type: "hello" }); // background answers with what the voice can do
    return port;
  }
  safe(() => ttsPort());

  // the line's text with spaces tidied up, plus where each character lives in the page,
  // so the word being spoken can be highlighted
  function textWithMap(range) {
    const map = [];
    let text = "";
    const root = range.commonAncestorContainer.nodeType === Node.TEXT_NODE
      ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!range.intersectsNode(node)) continue;
      const from = node === range.startContainer ? range.startOffset : 0;
      const to = node === range.endContainer ? range.endOffset : node.length;
      for (let i = from; i < to; i++) {
        const ch = node.data[i];
        if (/\s/.test(ch)) {
          if (text && !text.endsWith(" ")) {
            text += " ";
            map.push([node, i]);
          }
        } else {
          text += ch;
          map.push([node, i]);
        }
      }
    }
    if (text.endsWith(" ")) {
      text = text.slice(0, -1);
      map.pop();
    }
    return { text, map };
  }

  const lineTarget = (range) => {
    const r = range.getBoundingClientRect();
    return { key: `line:${Math.round(r.top + scrollY)}:${Math.round(r.left + scrollX)}`, kind: "line", range };
  };

  // the visual line right after `range`, in the same paragraph (null at the end of the paragraph)
  function nextLineAfter(range) {
    let node = range.endContainer;
    let i = range.endOffset;
    if (node.nodeType !== Node.TEXT_NODE) return null;
    const last = charRect(node, i - 1);
    const walker = document.createTreeWalker(blockOf(node), NodeFilter.SHOW_TEXT);
    walker.currentNode = node;
    for (let n = 0; node && n < 5000;) {
      for (; i < node.length; i++, n++) {
        if (/\s/.test(node.data[i])) continue;
        const r = charRect(node, i);
        if (r && (!last || !sameLine(r, last))) return lineTarget(expandLine({ node, index: i, rect: r }));
      }
      node = walker.nextNode();
      i = 0;
    }
    return null;
  }

  // this line and every line after it, to the end of the paragraph
  function paragraphFrom(t) {
    const lines = [t];
    while (S.readParagraph && lines.length < 200) {
      const next = nextLineAfter(lines[lines.length - 1].range);
      if (!next) break;
      lines.push(next);
    }
    return lines;
  }

  // scroll so the line being read stays comfortably in view
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  function keepInView(t) {
    const r = rectOf(t);
    if (r.bottom < innerHeight - 90 && r.top > 60) return;
    let el = (t.range ? t.range.startContainer.parentElement : t.el) || document.body;
    while (el && el !== document.body) {
      const oy = getComputedStyle(el).overflowY;
      if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 4) break;
      el = el.parentElement;
    }
    const scroller = !el || el === document.body ? document.scrollingElement || document.documentElement : el;
    scroller.scrollBy({ top: r.top - innerHeight * 0.35, behavior: reduceMotion.matches ? "auto" : "smooth" });
  }

  function speak(text) {
    safe(() => ttsPort().postMessage({ type: "speak", id: reading.id, text, rate: S.voiceRate }));
  }

  function showLine(index) {
    reading.index = index;
    reading.target = reading.lines[index];
    target = reading.target;
    paintTarget(reading.target, true);
    keepInView(reading.target);
  }

  function startReading(t) {
    stopReading(false);
    if (t.kind !== "line") {
      // a link / button / tab: read its name (and what it is, like a screen reader does)
      const text = t.name ? (S.sayKind ? `${t.name}, ${t.kind}` : t.name) : "";
      if (!text) return setStatus("Nothing to read here");
      reading = { id: ++readId, lines: [t], spans: [{ start: 0, end: text.length }], text, map: null, index: 0, target: t, oneVoice: true };
      paintTarget(t, true);
      speak(text);
    } else {
      const lines = paragraphFrom(t);
      const parts = lines.map((line) => textWithMap(line.range));
      let text = "";
      const map = [];
      const spans = [];
      parts.forEach((part) => {
        if (text) {
          text += " ";
          map.push(null); // the space joining two lines
        }
        spans.push({ start: text.length, end: text.length + part.text.length });
        text += part.text;
        map.push(...part.map);
      });
      if (!text.trim()) return setStatus("Nothing to read here");
      // one smooth voice for the whole paragraph if the voice reports words (so we can follow along);
      // otherwise read it one line at a time
      const oneVoice = wordEvents || lines.length === 1;
      reading = { id: ++readId, lines, parts, spans, text, map, index: 0, target: t, oneVoice };
      showLine(0);
      speak(oneVoice ? text : parts[0].text);
    }
    const more = reading.lines.length > 1 ? ` · ${reading.lines.length} lines` : "";
    setStatus(`🔊 Reading${more} · 👍, Esc or wave to stop`);
    sound("read");
    emit("read");
  }

  // stop reading. the line you were on stays highlighted, so 👍 continues from there
  function stopReading(tell = true) {
    if (!reading) return;
    const at = reading.target;
    reading = null;
    if (hasHighlights()) CSS.highlights.delete("rl-word");
    if (tell) safe(() => port && port.postMessage({ type: "stop" }));
    target = at;
    paintTarget(at);
    // keep the line you stopped on highlighted for a while, so 👍 can pick up from there
    resumeAt = at;
    resumeUntil = now() + 10 * (S.holdScale || 1);
    highlightUntil = resumeUntil;
    if (tell) setStatus("Stopped · 👍 to continue from this line");
  }

  function highlightWord(charIndex, length) {
    if (!S.wordByWord || !reading.map || !hasHighlights()) return;
    let end = length ? charIndex + length : reading.text.indexOf(" ", charIndex);
    if (end < 0 || end > reading.text.length) end = reading.text.length;
    const a = reading.map[charIndex];
    const b = reading.map[end - 1];
    if (!a || !b) return;
    const r = document.createRange();
    r.setStart(a[0], a[1]);
    r.setEnd(b[0], b[1] + 1);
    CSS.highlights.set("rl-word", new Highlight(r));
  }

  function onTtsEvent(e) {
    if (e.type === "caps") {
      wordEvents = !!e.wordEvents;
      return;
    }
    if (!reading || e.id !== reading.id) return;
    if (e.type === "word") {
      if (reading.oneVoice) {
        // which line is this word on? move the highlight (and scroll) when the voice reaches the next line
        const at = reading.spans.findIndex((sp) => e.charIndex < sp.end + 1);
        if (at >= 0 && at !== reading.index) showLine(at);
        highlightWord(e.charIndex, e.length);
      } else {
        highlightWord(reading.spans[reading.index].start + e.charIndex, e.length);
      }
    } else if (e.type === "end" && !reading.oneVoice && reading.index < reading.lines.length - 1) {
      // reading line by line: on to the next one
      showLine(reading.index + 1);
      if (hasHighlights()) CSS.highlights.delete("rl-word");
      speak(reading.parts[reading.index].text);
    } else if (["end", "interrupted", "cancelled", "error"].includes(e.type)) {
      const finished = e.type === "end";
      stopReading(false);
      setStatus(e.type === "error" ? "Couldn't read that out loud" : finished ? "Done reading" : "Stopped · 👍 to continue");
    }
  }

  // Esc stops reading (only while reading, so it never gets in the page's way otherwise)
  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && reading) stopReading();
  }, true);

  // ---------------------------------------------------------------- click / scroll / zoom

  function clickAt(x, y) {
    const el = document.elementFromPoint(x, y);
    if (!el) return;
    const base = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, view: window, button: 0 };
    el.dispatchEvent(new PointerEvent("pointerdown", { ...base, pointerType: "mouse", isPrimary: true, buttons: 1 }));
    el.dispatchEvent(new MouseEvent("mousedown", { ...base, buttons: 1 }));
    const focusable = el.closest("a[href], button, input, textarea, select, summary, [tabindex], [contenteditable=true]");
    if (focusable) focusable.focus({ preventScroll: true });
    el.dispatchEvent(new PointerEvent("pointerup", { ...base, pointerType: "mouse", isPrimary: true }));
    el.dispatchEvent(new MouseEvent("mouseup", base));
    el.dispatchEvent(new MouseEvent("click", base));
    ripple(x, y);
    sound("click");
    emit("click");
  }

  // scroll whatever is scrollable under the cursor (an inner panel, or the page)
  function scrollerAt(x, y) {
    for (let el = document.elementFromPoint(x, y); el && el !== document.documentElement; el = el.parentElement) {
      const oy = getComputedStyle(el).overflowY;
      if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight + 4) return el;
    }
    return document.scrollingElement || document.documentElement;
  }

  let zoomBusy = false;
  async function zoom(dir, x, y) {
    if (zoomBusy) return;
    zoomBusy = true;
    // keep whatever is under the finger under the finger
    const el = document.elementFromPoint(x, y);
    const before = el && el.getBoundingClientRect();
    const fx = before && before.width ? (x - before.left) / before.width : 0;
    const fy = before && before.height ? (y - before.top) / before.height : 0;
    const vx = x / innerWidth;
    const vy = y / innerHeight;
    let res = null;
    try {
      res = await chrome.runtime.sendMessage({ target: "background", type: "zoom", dir });
    } catch {
      res = null;
    }
    zoomBusy = false;
    if (!res || res.zoom == null) return;
    const pct = Math.round(res.zoom * 100);
    zoomLabel = res.changed ? `🔍 ${pct}%` : `🔍 ${pct}% (${dir > 0 ? "max" : "min"})`;
    if (res.changed) {
      sound(dir > 0 ? "zoomIn" : "zoomOut");
      emit("zoom");
      if (el) {
        await new Promise((r) => setTimeout(r, 90));
        const after = el.getBoundingClientRect();
        scrollBy(after.left + fx * after.width - vx * innerWidth, after.top + fy * after.height - vy * innerHeight);
      }
    }
  }

  // ---------------------------------------------------------------- sleep (wave)

  let sleeping = false;
  function setSleeping(value, announce = true) {
    if (value === sleeping) return;
    sleeping = value;
    ui.hud.classList.toggle("sleep", sleeping);
    ui.pill.textContent = sleeping ? "Sleeping" : "Active";
    if (sleeping) {
      stopReading();
      clearHighlight();
    }
    if (announce) {
      safe(() => chrome.storage.session.set({ sleeping }));
      sound(sleeping ? "sleep" : "wake");
      emit(sleeping ? "sleep" : "wake");
    }
  }

  // ---------------------------------------------------------------- the gesture engine

  const now = () => performance.now() / 1000;
  const fingers = new G.FingerState(); // up / down per finger, without flicker
  const stab = new G.PoseStabilizer(4); // a mode has to show for 4 frames (~0.13 s) before it switches
  const fx = new G.OneEuro();
  const fy = new G.OneEuro();
  const wave = new G.WaveDetector();
  const stable = new G.StableTarget(T.restTime);
  const drag = new G.DragScroller();
  let cx = innerWidth / 2;
  let cy = innerHeight / 2;
  let history = []; // [t, x, y]
  let extRef = 0;
  let curlFrozen = false;
  let pinching = false;
  let pinchStart = 0;
  let zoomMode = false;
  let anchorY = 0;
  let frozen = [cx, cy];
  let pendingClick = null;
  let pinchBlocked = false;
  let thumbStart = null;
  let thumbFired = false;
  let thumbTarget = null;
  let lastTwo = -Infinity;
  let highlightUntil = 0;
  let lastPalmX = null;
  let lastPalmT = -Infinity;
  let zoomLabel = "";
  let lastFrame = 0;

  function toView(p) {
    const nx = Math.max(0, Math.min(1, (p.x - T.margin) / (1 - 2 * T.margin)));
    const ny = Math.max(0, Math.min(1, (p.y - T.margin) / (1 - 2 * T.margin)));
    return [nx * innerWidth, ny * innerHeight];
  }
  function pointBefore(t, seconds) {
    for (let i = history.length - 1; i >= 0; i--) if (history[i][0] <= t - seconds) return [history[i][1], history[i][2]];
    return history.length ? [history[0][1], history[0][2]] : [cx, cy];
  }

  let pinchFrames = 0; // a pinch has to show for 2 frames in a row before it starts

  function resetHand() {
    fingers.reset();
    pinchFrames = 0;
    stab.reset();
    fx.reset();
    fy.reset();
    drag.reset();
    extRef = 0;
    curlFrozen = false;
    pinching = false;
    zoomMode = false;
    pendingClick = null;
    thumbStart = null;
    thumbFired = false;
    history = [];
    setRing(0);
  }

  function onFrame(hand) {
    lastFrame = performance.now();
    showUI();
    const t = now();

    if (!hand) {
      resetHand();
      ui.cursor.style.opacity = "0.35";
      setStatus(sleeping ? "💤 Sleeping · wave to wake" : "Show your hand to the camera");
      drawHud(null);
      const g = drag.glide();
      if (g) scrollerAt(cx, cy).scrollBy(0, g);
      return;
    }
    ui.cursor.style.opacity = "1";
    const raw = G.poseFrom(hand, fingers.update(hand), T.pinchEnter);
    const pose = stab.update(raw);

    // 👋 wave (open hand swinging sideways) -> sleep / wake
    if (raw === "palm") lastPalmT = t;
    else if (t - lastPalmT > 0.4) wave.clear();
    if (raw === "palm" && wave.add(t, hand[9].x)) {
      setSleeping(!sleeping);
      drag.reset();
    }
    if (sleeping) {
      setMode("sleep");
      setStatus("💤 Sleeping · wave to wake");
      setRing(0);
      drawHud(hand);
      return;
    }

    // index finger curling (on the way to 👍 / a fist)? hold the cursor where you were pointing
    const ext = G.indexExtension(hand);
    if (!curlFrozen) extRef = Math.max(ext, extRef * 0.995);
    if (!curlFrozen && !pinching && ext < T.curlRatio * extRef) {
      curlFrozen = true;
      [cx, cy] = pointBefore(t, T.lookback);
      moveCursor(cx, cy);
    } else if (curlFrozen && ext >= (T.curlRatio + 0.1) * extRef) {
      curlFrozen = false;
      fx.reset();
      fy.reset();
      fx.filter(cx, t);
      fy.filter(cy, t);
    }

    // ☝️ / ✌️ move the cursor
    if (!pinching && !curlFrozen && (raw === "one" || raw === "two" || raw === "none")) {
      const [tx, ty] = toView(hand[8]);
      const nx = fx.filter(tx, t);
      const ny = fy.filter(ty, t);
      if (Math.hypot(nx - cx, ny - cy) >= T.stillPx) [cx, cy] = [nx, ny];
      history.push([t, cx, cy]);
      if (history.length > 90) history.shift();
      moveCursor(cx, cy);
    }

    // 🖐️ open palm -> drag the page like paper (and glide a bit after)
    if (raw === "palm" && !pinching) {
      const dx = lastPalmX === null ? 0 : hand[9].x - lastPalmX;
      const px = drag.move(hand[9].y, dx, innerHeight, S.invertScroll);
      if (px) scrollerAt(cx, cy).scrollBy(0, px);
      lastPalmX = hand[9].x;
    } else {
      lastPalmX = null;
      const g = drag.glide();
      if (g) scrollerAt(cx, cy).scrollBy(0, g);
    }

    // 🤏 pinch = click, pinch + hold + up/down = zoom
    const thumbGoingUp = G.thumbsUp(hand) || G.thumbRising(hand);
    if (pinchBlocked && G.fingerUp(hand, 8, 6) && !thumbGoingUp) pinchBlocked = false;
    if (pendingClick && thumbGoingUp) pendingClick = null; // it was a 👍, not a click
    else if (pendingClick && t - pendingClick.t >= hold("clickConfirm")) {
      clickAt(...pendingClick.at);
      pendingClick = null;
    }
    if (pinching && !zoomMode && G.thumbsUp(hand)) {
      pinching = false;
      pinchBlocked = true;
      setRing(0);
    }
    const ratio = G.pinchRatio(hand);
    pinchFrames = G.isPinch(hand, T.pinchEnter) ? pinchFrames + 1 : 0;
    if (!pinching && !pinchBlocked && raw !== "palm" && pinchFrames >= 2) {
      pinching = true;
      pinchStart = t;
      zoomMode = false;
      frozen = curlFrozen ? [cx, cy] : pointBefore(t, T.lookback); // closing the fingers drags the tip
      [cx, cy] = frozen;
      moveCursor(cx, cy);
    } else if (pinching && !zoomMode && t - pinchStart > hold("holdToZoom")) {
      zoomMode = true;
      anchorY = hand[8].y;
      zoomLabel = "🔍 Move up / down";
      sound("mode");
    }
    if (pinching && zoomMode) {
      const dy = anchorY - hand[8].y;
      if (Math.abs(dy) > T.zoomStep && !zoomBusy) {
        anchorY = hand[8].y;
        zoom(dy > 0 ? 1 : -1, cx, cy);
      }
    }
    if (pinching && ratio > T.pinchExit) {
      pinching = false;
      if (!zoomMode) pendingClick = { at: frozen, t };
      history = [];
    }
    setRing(pinching && !zoomMode ? (t - pinchStart) / hold("holdToZoom") : 0);

    // ✌️ highlight (only while not reading - then the highlight stays on what's being read)
    if (!reading) {
      if (pose === "two" && !pinching) {
        updateHighlight(cx, cy, t);
        lastTwo = t;
        highlightUntil = t + hold("keepHighlight");
        if (target) stable.update(target.key, target, t);
      } else if (pose === "one" && !pinching) {
        if (target && t - lastTwo > 0.3) clearHighlight();
      } else if (target && t > highlightUntil) {
        clearHighlight();
      }
    }

    // 👍 thumbs up -> read what's highlighted (thumbs up again while reading = stop)
    if (pose === "thumbs") {
      if (thumbStart === null) {
        thumbStart = t;
        const resume = resumeAt && t < resumeUntil && target === resumeAt ? resumeAt : null;
        const recent = stable.stable && t - stable.stableAt < 4 ? stable.stable : null;
        thumbTarget = resume || recent || target;
        if (thumbTarget && !reading) {
          target = thumbTarget;
          paintTarget(target);
        }
        highlightUntil = t + hold("keepHighlight") + hold("readHold");
      } else if (!thumbFired && t - thumbStart >= hold("readHold")) {
        thumbFired = true;
        if (reading) stopReading();
        else if (thumbTarget) startReading(thumbTarget);
        else setStatus("✌️ Highlight a line first, then 👍");
      }
    } else {
      thumbStart = null;
      thumbFired = false;
    }

    // what the cursor badge / HUD should say
    let m = "point";
    let label;
    if (reading) m = "read";
    else if (pinching && zoomMode) [m, label] = ["zoom", zoomLabel];
    else if (pinching) m = "pinch";
    else if (raw === "palm") m = "scroll";
    else if (pose === "thumbs") m = "thumbs";
    else if (pose === "two") m = "highlight";
    setMode(m, label);
    if (!reading) {
      setStatus({
        point: "☝️ Pointing · ✌️ two fingers to highlight",
        highlight: target ? `✌️ ${target.kind === "line" ? "Line" : target.kind} highlighted · 👍 to read` : "✌️ Move onto some text",
        scroll: "🖐️ Move your palm up / down",
        pinch: "🤏 Let go to click · hold to zoom",
        zoom: "🔍 Move up to zoom in, down to zoom out",
        thumbs: thumbTarget ? "👍 Keep holding to read…" : "✌️ Highlight a line first, then 👍",
      }[m] || "");
    }
    if (m === "point" && !emitted.has("point")) {
      emit("point");
      emitted.add("point");
    }
    drawHud(hand);
  }

  setInterval(() => {
    if (visible && performance.now() - lastFrame > T.noFrameTimeout) {
      hideUI();
      resetHand();
    }
  }, 500);

  // keyboard way to read (Alt+Shift+R): whatever is highlighted, or the line / link under the mouse
  let mouse = null;
  addEventListener("mousemove", (e) => (mouse = [e.clientX, e.clientY]), { passive: true });
  function readHere() {
    if (reading) return stopReading();
    const at = mouse || [cx, cy];
    const t = target || componentAt(...at) || lineAt(...at);
    if (t) {
      attachUI(); // just the highlight - no hand cursor needed when using the keyboard
      startReading(t);
    }
  }

  safe(() => chrome.runtime.onMessage.addListener((msg) => {
    // normal pages get frames forwarded from the background script; extension pages (the tutorial)
    // hear them straight from the camera page
    const fromCamera = msg.target === "background" && msg.type === "frame";
    if (msg.type === "frame" && (IS_EXTENSION_PAGE ? fromCamera && document.visibilityState === "visible" : msg.via === "bg")) {
      onFrame(msg.hand);
    }
    if (msg.type === "stopped" || msg.type === "inactive") {
      stopReading();
      hideUI();
      resetHand();
    }
    if (msg.type === "stop-reading") stopReading();
    if (msg.type === "read-here") readHere();
  }));
})();
