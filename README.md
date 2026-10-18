# technica_reading_line

Point at text with your finger (via webcam) to highlight the line you're reading,
pinch to click, pinch-and-hold to zoom.

There are three versions:

- **`windows_app/`**: the Windows desktop app (newest). Works over any app on your screen.
- **`extension/`**: a Chrome extension (also works in Edge / Brave). Works on macOS, Windows and Linux.
- **`hand_cursor1.py`**: the original Windows-only desktop script.

## Windows app

Needs Windows 10 or 11 and **Python 3.9 to 3.12** (MediaPipe doesn't support newer Python yet).

### Setup (once)

Open a terminal in the `windows_app` folder:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```
venv\Scripts\activate
python reading_line.py
```

A preview window with your webcam shows up. Click on it once so it gets your key presses.

### Gestures

| Gesture | What it does |
| --- | --- |
| Point with index finger | moves the mouse |
| Quick pinch (thumb + index) | click |
| Pinch & hold, then hand up / down | zoom in / out (Windows Magnifier) |
| Hold index + middle finger up | highlight on / off |
| **Open palm**, then move it up / down | **scroll** (the further you move from where you started, the faster) |
| **Thumbs up**, hold for half a second | **read the line you were pointing at out loud** |
| **Hold the cursor still** (dwell mode on) | **click** without pinching |

### Keys (in the preview window)

| Key | What it does |
| --- | --- |
| `h` | highlight on / off |
| `r` | reading ruler on / off (dims the whole screen except your line) |
| `c` | next highlight colors (yellow, dark, blue tint, peach, white on blue) |
| `a` | auto-read on / off (reads each line after you stay on it for a moment) |
| `d` | dwell click on / off |
| `t` | read the current line now |
| `s` | stop speaking |
| `[` / `]` | ruler darker / lighter |
| `-` / `=` | voice slower / faster |
| `q` or `Esc` | quit |

Your choices are saved in `windows_app/settings.json`. That file also has every other setting
(smoothing, pinch sensitivity, dwell time, scroll speed...). Close the app before editing it.

### Tests

The gesture, dwell, scroll and line-finding logic has tests that don't need a webcam:

```
pip install pytest
python -m pytest tests
```

## Chrome extension

### Install

1. Open `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** and pick the `extension/` folder
4. Pin the extension, click its icon, then click **Start hand tracking**
5. The first time, a tab opens asking for the camera. Click **Allow camera**

Shortcut: `Alt+Shift+H` starts / stops tracking.

### Gestures

| Gesture | What it does |
| --- | --- |
| Point with index finger | moves the on-page cursor |
| Quick pinch (thumb + index) | click |
| Pinch & hold, then hand up / down | zoom in / out (up to 3×) |
| Hold index + middle finger up | turn line highlighting on / off |

### How it works

| File | Job |
| --- | --- |
| `offscreen.html/js` | hidden page that owns the webcam and runs MediaPipe Hand Landmarker (`lib/`, `models/`) |
| `background.js` | starts/stops the hidden page, forwards hand points to the tab you're looking at, does zoom with `chrome.tabs.setZoom` |
| `content.js` | runs in each page: cursor smoothing, pinch/click/zoom/two-finger logic (ported from the Python), line highlight, preview |
| `popup.*` | start/stop button and settings |
| `setup.*` | one-time camera permission page |

Differences from the Python version:

- The cursor is drawn inside the page instead of moving the real mouse. Extensions can't move the OS mouse.
- The line highlight comes from the page's own text layout instead of a screenshot, so it's exact,
  follows scrolling, and keeps working while zoomed.
- Zoom uses the browser's page zoom (not the Windows Magnifier) and keeps what you pointed at under your finger.
- It doesn't run on `chrome://` pages or the Chrome Web Store. Chrome blocks extensions there.

Settings (pinch thresholds, smoothing, etc.) are at the top of `extension/content.js`.

The MediaPipe files in `extension/lib/` come from `@mediapipe/tasks-vision@0.10.21`.

## Original script (Windows)

```
pip install opencv-python mediapipe numpy pyautogui
python hand_cursor1.py
```
