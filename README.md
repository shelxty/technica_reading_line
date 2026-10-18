# Wavi: Highlighted Accessibility

Point at text with your finger (via webcam) to highlight the line you're reading,
pinch to click, pinch-and-hold to zoom.

There are four versions:

- **`extension_v2/`** (**Wavy**): the newest Chrome extension: point, highlight, read aloud word by word, palm scroll,
  pinch to click and zoom, wave to pause, a first-run tutorial, and Section 508 / WCAG 2.0 AA accessibility.
  See [extension_v2/README.md](extension_v2/README.md).
- **`windows_app/`**: the Windows desktop app (newest). Works over any app on your screen.
- **`extension/`**: a Chrome extension (also works in Edge / Brave). Works on macOS, Windows and Linux.
- **`hand_cursor1.py`**: the original Windows-only desktop script.


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

Links, buttons and tabs are found through Windows' accessibility info (UI Automation, the same thing
screen readers use). If you set the app up before this was added, run `pip install -r requirements.txt` again.

A preview window with your webcam shows up. Click on it once so it gets your key presses.
You can resize it to make its text bigger.

### Gestures

| Gesture | What it does |
| --- | --- |
| Point with your index finger | moves the mouse. The line of text under it is highlighted black on yellow. On a link, button, tab, menu item, checkbox or text field, just that element is highlighted |
| Thumbs up, hold for half a second | reads the line (or link / button / tab) your finger last rested on, out loud. It stays highlighted until it's finished. Links and buttons are read by their name and type, like a screen reader: "Contact us, link" |
| Open palm (four fingers up), then move it up / down | scroll. The faster you move, the further you scroll |
| Quick pinch (in under 0.4 seconds) (thumb + index) | click |
| Pinch and hold, then move your hand up / down | zoom in / out, from 50% to 300% |

Zoom uses the Chrome zoom function.


### Keys (in the preview window)

| Key | What it does |
| --- | --- |
| `Space` | pause / resume hand control (get your mouse back without quitting) |
| `h` | highlight on / off |
| `t` | read the current line |
| `s` | stop reading |
| `-` / `=` | voice slower / faster |
| `q` or `Esc` | quit |

The preview shows what the app is doing, the zoom level, and **`Hand:`**, the gesture it thinks you're
making. If a gesture doesn't work, check that first.

Settings are saved in `windows_app/settings.json`. Close the app before editing it. The useful ones:

| Setting | What it does |
| --- | --- |
| `steady` | cursor steadiness when your finger is still. Lower = steadier (try 0.3 to 1.5) |
| `responsive` | how fast the cursor catches up when you move. Higher = less lag |
| `still_px` | wobbles smaller than this many pixels are ignored |
| `scroll_speed` / `scroll_max` | how fast scrolling speeds up, and its top speed (wheel notches per second) |
| `components` | `false` = always highlight whole lines, even on links and buttons |
| `say_kind` | `false` = read just a link's / button's name, without "link" / "button" |
| `rest_time` | how long your finger has to rest on a line before thumbs-up reads that line (seconds) |
| `curl_ratio` | how much the index finger has to bend before the cursor holds still (for thumbs-up) |
| `read_hold`, `hold_time`, `palm_enter`, `click_confirm` | how long each gesture has to be held |

Also: pinch sensitivity, zoom range, preview text size.


### Tests

The gesture, scroll, zoom, line-finding and color contrast logic has tests that don't need a webcam:

```
pip install pytest
python -m pytest tests
```

## Chrome extension

### Install

1. Download this repository as a `.zip` file.
2. Extract the folder.
3. Open `chrome://extensions`
4. Turn on **Developer mode** (top right)
5. Click **Load unpacked** and pick the extracted `extension/` folder
6. Pin the extension, click its icon, then click **Start hand tracking**
7. The first time, a tab opens asking for the camera. Click **Allow camera**

Shortcut: `Alt+Shift+H` starts / stops tracking.


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
