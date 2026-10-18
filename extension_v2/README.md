# Reading Line v2: read the web with your hands

A Chrome extension (also Edge and Brave) that follows your hand with your webcam.

| Gesture | What it does |
| --- | --- |
| ☝️ One finger | moves the cursor |
| ✌️ Two fingers | highlights the line under the cursor, black on yellow. On a link, button, tab, checkbox or text field, just that element is highlighted |
| 👍 Thumbs up (hold) | reads from the highlighted line to the end of the paragraph, out loud. The highlight moves line by line, each word lights up orange, and the page scrolls along |
| 🖐️ Open palm, up / down | scrolls. The page follows your palm like a sheet of paper and glides a little when you stop |
| 🤏 Quick pinch | clicks |
| 🤏 Pinch and hold, then up / down | zooms the page in / out, from 50% to 300% |
| 👋 Wave | pauses all gestures (so you can talk with your hands). Wave again to resume |

### Stopping the reading

Any of these stop it. The line you stopped on stays highlighted for 10 seconds, so 👍 continues from there:

- 👍 thumbs up again
- `Esc`, or `Alt` + `Shift` + `R`
- 👋 wave (this also pauses all gestures)

If your computer's voice reports each word (most built-in voices do), the paragraph is read in one smooth
voice. Otherwise it's read one line at a time. Turn "Keep reading to the end of the paragraph" off in the popup
to read just one line.

## Install

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and choose this `extension_v2` folder.
3. The tutorial opens. Click **Allow camera and start**, then try each gesture. The cards tick themselves off.
4. Later, click the extension's icon to start / stop it and change settings.

If you also have the first version (`extension/`) loaded, turn it off so they don't both use the camera.

## On every page

- **Cursor:** an arrow with a colored badge that says what it's doing ("✌️ Highlight", "🔍 150%", "💤 Sleeping"...).
  A ring around it fills while you pinch-and-hold, showing when a click will become a zoom.
- **Hand panel** (bottom right): your hand's skeleton, the six gestures with the active one lit up, and a
  hint for what to do next. You can hide it in the settings.

## Keyboard

| Keys | What it does |
| --- | --- |
| `Alt` + `Shift` + `H` | start / stop hand tracking |
| `Alt` + `Shift` + `R` | read from the highlighted line, or the line / link under the mouse (again to stop) |
| `Esc` | stop reading |
| `Alt` + `Shift` + `S` | pause / resume gestures |

You can change these at `chrome://extensions/shortcuts`.

## Settings (in the popup)

Keep reading to the end of the paragraph · sound cues · word-by-word highlight · saying "link" / "button" after a name · hand panel · reverse scroll ·
reading speed · cursor size · **gesture timing** (normal, relaxed 1.5×, extra relaxed 2×: more time for every hold).

## Accessibility: Section 508 / WCAG 2.0 AA

Section 508 uses WCAG 2.0 level AA, and ADA compliance is usually measured against the same standard. Here's how each criterion that applies is met:

| WCAG criterion | How it's met |
| --- | --- |
| 1.1.1 Non-text content | Icons and emoji are marked decorative (`aria-hidden`) next to a text label. The hand panel is decorative; its meaning is also in text |
| 1.3.1 Info and relationships | Real headings, lists, `<label>`s, `<output>`s, a `<dl>` for shortcuts, `role="switch"` with `aria-checked`, `role="progressbar"` with values |
| 1.4.1 Use of color | Every state is also shown in words: switches say "(on)" / "(off)", steps say "Done ✓", the badge names the mode |
| 1.4.3 Contrast (minimum) | Every text / background pair is at least 4.5:1, in light and dark mode. `tests/contrast.test.js` checks all 29 pairs (highlight 19.6:1, word 9:1, the lowest is 4.6:1) |
| 1.4.4 Resize text | Popup and tutorial use relative layout and work at 200% browser zoom. The cursor size is adjustable |
| 2.1.1 Keyboard | Everything in the popup and tutorial works with Tab / Space / Enter. Reading, sleep and start / stop have shortcuts |
| 2.1.2 No keyboard trap | Nothing traps focus. Every tutorial step has a **Skip** button |
| 2.2.1 Timing adjustable | "Gesture timing" makes every hold 1.5× or 2× longer |
| 2.2.2 Pause, stop, hide | Speech stops with 👍, `Esc` or `Alt+Shift+R`, and can be continued. Waving or `Alt+Shift+S` pauses everything. The hand panel can be hidden |
| 2.3.1 Three flashes | Nothing flashes. Animations turn off with the system "reduce motion" setting |
| 2.4.1 Bypass blocks | The tutorial has a "Skip to the gestures" link |
| 2.4.3 / 2.4.7 Focus order / visible | Logical source order. A 3px focus outline on everything |
| 3.1.1 Language of page | `lang="en"` on every page |
| 3.3.1 / 3.3.3 Error identification / suggestion | Camera problems are shown in an alert with what to do ("Click the camera icon in the address bar…") |
| 4.1.2 Name, role, value | All controls are native buttons / inputs or have a role, a name and their state |
| 4.1.3 Status messages (2.1) | Tracking state, tutorial progress and the demo button result are live regions |

**Checked with axe-core 4.10** (rules for WCAG 2.0 / 2.1 A and AA, and Section 508): 0 violations on the
popup (24 checks passed) and on the tutorial (26 passed). axe can't measure contrast on gradient backgrounds,
which is why the contrast test above exists.

This is a self-assessment. Formal 508 conformance (a VPAT / ACR) needs a review by an accessibility
specialist, including testing with screen readers such as NVDA, JAWS and VoiceOver.

## How it works

| File | Job |
| --- | --- |
| `offscreen.html/js` | hidden page: owns the webcam, runs MediaPipe Hand Landmarker (`lib/`, `models/`), plays the sound cues |
| `background.js` | starts / stops the hidden page, forwards hand points to the tab you're on, zooms, reads out loud with `chrome.tts` (which reports each word), keyboard shortcuts |
| `gestures.js` | pose detection, steadying the cursor (One Euro filter), wave, drag scroll. No browser code, so it's unit tested |
| `content.js` | runs in each page: the gesture rules, cursor, highlight, word-by-word reading, the hand panel |
| `popup.*`, `tutorial.*` | the settings popup and the first-run tutorial |

Pages Chrome doesn't let extensions touch (`chrome://`, the Chrome Web Store) can't be controlled.

## Tests

```
node --test tests/*.test.js
```

42 tests: every pose, steady finger states (no flicker), the cursor filter, wave, drag scroll, zoom range, a fist not counting as a pinch, and color contrast.
