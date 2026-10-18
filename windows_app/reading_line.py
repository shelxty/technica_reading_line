"""
Reading Line for Windows - the next version of hand_cursor1.py

setup (once), in this folder:
    pip install -r requirements.txt
run:
    python reading_line.py

gestures:
    point with index finger        -> moves the mouse
    quick pinch (thumb + index)    -> click
    pinch + hold, then up / down   -> zoom in / out (windows magnifier)
    index + middle finger up, hold -> highlight on / off
    open palm, then up / down      -> scroll (further from where you started = faster)
    thumbs up, hold                -> read the line you were pointing at out loud
    hold still (dwell mode on)     -> click, no pinch needed

keys (click on the preview window first so it gets the key presses):
    h  highlight on/off          r  reading ruler on/off      c  next highlight colors
    a  auto-read on/off          d  dwell click on/off        t  read current line now
    s  stop speaking             [ ]  ruler dimmer / brighter  - =  voice slower / faster
    q or esc  quit
"""

import ctypes
import os
import time
import urllib.request
from collections import deque

# make cursor coords match the real screen resolution on high-dpi monitors. has to happen first
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
import tkinter as tk
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from PIL import ImageGrab

import gestures
import settings as settings_file
from linefinder import COLOR_PRESETS, find_line_in_gray, high_contrast
from overlays import DwellRing, LineOverlay, RulerMask
from speech import Reader

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")


def model_path():
    # reuse the model in the repo root if it's there, otherwise download it next to this file
    for p in (os.path.join(HERE, "hand_landmarker.task"),
              os.path.join(HERE, os.pardir, "hand_landmarker.task")):
        if os.path.exists(p):
            return p
    p = os.path.join(HERE, "hand_landmarker.task")
    print("Downloading the model...")
    urllib.request.urlretrieve(MODEL_URL, p)
    return p


HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index finger
    (5, 9), (9, 10), (10, 11), (11, 12),  # middle finger
    (9, 13), (13, 14), (14, 15), (15, 16),  # ring finger
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),  # edge of the palm
]


def draw_landmarks(frame, hand):
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 255, 0), 2)
    for p in pts:
        cv2.circle(frame, p, 4, (0, 0, 255), -1)


S = settings_file.load()
settings_file.save(S)  # writes settings.json with every option the first time, so you can edit it
pyautogui.PAUSE = 0  # no 0.1s delay after every pyautogui action
SCREEN_W, SCREEN_H = pyautogui.size()


def to_screen(lm):
    nx = (lm.x - S.margin) / (1 - 2 * S.margin)
    ny = (lm.y - S.margin) / (1 - 2 * S.margin)
    nx = max(0, min(1, nx))
    ny = max(0, min(1, ny))
    return nx * SCREEN_W, ny * SCREEN_H


def clamp_to_screen(x, y):
    # keep 1px away from the edges so pyautogui's failsafe doesn't trigger
    return min(max(x, 1), SCREEN_W - 2), min(max(y, 1), SCREEN_H - 2)


# ---------- overlays ----------

root = tk.Tk()
root.withdraw()
line_ov = LineOverlay(root)
ruler = RulerMask(root, SCREEN_W, SCREEN_H, S.ruler_dim)
ring = DwellRing(root)
OVERLAYS = (line_ov, ruler, ring)
# on windows 10 (2004+) / 11 the overlays are invisible to screenshots, so we never have to hide them
CAPTURE_SAFE = all(o.excluded for o in OVERLAYS)
if not CAPTURE_SAFE:
    print("Older Windows: overlays will blink briefly when the line changes")

reader = Reader(S.ocr_lang, S.voice_rate)


def grab(box):
    if CAPTURE_SAFE:
        return ImageGrab.grab(bbox=box, all_screens=True)
    for o in OVERLAYS:
        o.suspend()
    root.update()
    time.sleep(0.03)
    try:
        return ImageGrab.grab(bbox=box, all_screens=True)
    finally:
        for o in OVERLAYS:
            o.resume()


# ---------- line detection + highlight + ruler ----------

line_box = None  # screen rectangle of the line under the finger; None = no line
line_since = 0.0  # when we landed on this line (for auto-read)
auto_read_done = True


def find_line(cx, cy):
    x0 = max(0, int(cx - S.region_w // 2))
    x1 = min(SCREEN_W, int(cx + S.region_w // 2))
    y0 = max(0, int(cy - S.search_h))
    y1 = min(SCREEN_H, int(cy + S.search_h))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    gray = np.array(grab((x0, y0, x1, y1)).convert("L")).astype(np.int16)
    box = find_line_in_gray(gray, cx - x0, cy - y0, S.snap, S.ink_diff, S.pad)
    if box is None:
        return None
    return x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]


def show_line_visuals():
    if line_box is None:
        line_ov.hide()
        return
    if S.highlight_on:
        _, bg, fg = COLOR_PRESETS[S.color_preset % len(COLOR_PRESETS)]
        line_ov.show(high_contrast(np.array(grab(line_box).convert("RGB")), bg, fg), line_box)
    else:
        line_ov.hide()
    if S.ruler_on:
        ruler.show(line_box)


def forget_line():
    global line_box
    line_box = None
    line_ov.hide()


def update_line(cx, cy, now):
    global line_box, line_since, auto_read_done
    b = line_box
    if b and b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
        return  # still on the same line, nothing to do
    box = find_line(cx, cy)
    if box is None:
        line_box = None
        line_ov.hide()  # the ruler keeps showing the last line so it doesn't blink between lines
        return
    line_box = box
    line_since = now
    auto_read_done = False
    show_line_visuals()


def read_line_at(x, y):
    b = line_box
    box = b if (b and b[0] <= x <= b[2] and b[1] <= y <= b[3]) else find_line(x, y)
    if box is None:
        return "No text here"
    reader.read_image(grab(box))
    return "Reading aloud"


# ---------- settings shortcuts ----------

def toggle(name, label):
    S[name] = not S[name]
    settings_file.save(S)
    apply_settings()
    return f"{label} {'ON' if S[name] else 'OFF'}"


def apply_settings():
    if not S.highlight_on:
        line_ov.hide()
    if not S.ruler_on:
        ruler.hide()
    if not S.dwell_on:
        ring.hide()
        dwell.reset()
    forget_line()  # makes the next frame find + redraw the line with the new settings


def lines_wanted():
    return S.highlight_on or S.ruler_on or S.auto_read


# ---------- hand landmarker ----------

options = vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=model_path()),
    running_mode=vision.RunningMode.VIDEO,  # tracks hands across frames
    num_hands=1,  # either hand works, but only one at a time
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)

# state
sx, sy = SCREEN_W / 2, SCREEN_H / 2  # smoothed cursor position
history = deque(maxlen=S.lookback)
pinching = False
pinch_start = 0.0
zoom_mode = False
anchor_y = 0.0
zoom_level = 0
frozen = (sx, sy)
status = "Move your hand"

two_start = None
two_fired = False

palm_start = None  # open palm first seen
palm_lost = None  # open palm last lost (short grace period so scrolling doesn't stutter)
scrolling = False
scroll_anchor = 0.0
scroll_acc = 0.0  # leftover fraction of a scroll step

thumb_start = None
thumb_fired = False
thumb_point = (sx, sy)

dwell = gestures.Dwell(S.dwell_radius, S.dwell_time)

cap = cv2.VideoCapture(0)
start = time.time()
last_t = start
last_ts = -1
WINDOW = "Reading Line"
HELP = "h hl  r ruler  c colors  a auto-read  d dwell  t read  s stop  q quit"

try:
    with vision.HandLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame = cap.read()
            if not ret:
                break  # camera problem
            frame = cv2.flip(frame, 1)  # mirror so moving right moves the cursor right
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # opencv is bgr, mediapipe wants rgb
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = max(int((time.time() - start) * 1000), last_ts + 1)  # must always increase
            last_ts = ts
            result = landmarker.detect_for_video(mp_image, ts)

            now = time.time()
            dt = min(now - last_t, 0.1)
            last_t = now

            if result.hand_landmarks:
                hand = result.hand_landmarks[0]
                draw_landmarks(frame, hand)
                ratio = gestures.pinch_ratio(hand)
                palm = not pinching and gestures.open_palm_pose(hand)
                thumbs = not pinching and gestures.thumbs_up_pose(hand)
                two = not pinching and gestures.two_finger_pose(hand)

                # --- open palm = scroll ---
                if palm:
                    palm_lost = None
                    if palm_start is None:
                        palm_start = now
                    if not scrolling and now - palm_start >= S.palm_enter:
                        scrolling = True
                        scroll_anchor = hand[9].y  # middle of the palm is the steadiest point
                        scroll_acc = 0.0
                        forget_line()
                        ruler.hide()  # the page is about to move under it
                elif scrolling:
                    if palm_lost is None:
                        palm_lost = now
                    if now - palm_lost > 0.2:
                        scrolling = False
                        palm_start = None
                        history.clear()
                else:
                    palm_start = None

                if scrolling:
                    v = gestures.scroll_velocity(scroll_anchor - hand[9].y, S.scroll_deadzone, S.scroll_speed)
                    scroll_acc += v * dt
                    step = int(scroll_acc)
                    if step:
                        pyautogui.scroll(step)  # windows wheel units, 120 = one notch
                        scroll_acc -= step
                    status = "Scrolling" + (" up" if v > 0 else " down" if v < 0 else " (move palm up/down)")

                # --- pointing: move the cursor ---
                if not (pinching or scrolling or palm or thumbs):
                    tx, ty = to_screen(hand[8])  # index fingertip
                    sx = sx * S.smooth + tx * (1 - S.smooth)
                    sy = sy * S.smooth + ty * (1 - S.smooth)
                    history.append((sx, sy))
                    pyautogui.moveTo(*clamp_to_screen(sx, sy))
                    status = "Pointing"

                    if lines_wanted() and zoom_level == 0:
                        update_line(sx, sy, now)
                    elif zoom_level > 0:
                        # screenshots don't match the magnified view, so hide everything while zoomed
                        forget_line()
                        ruler.hide()

                    if S.dwell_on and not two:
                        progress, fire = dwell.update(sx, sy, now)
                        if fire:
                            ring.hide()
                            pyautogui.click()
                            status = "DWELL CLICK"
                        elif progress > 0.1:
                            ring.show(sx, sy, progress)
                        else:
                            ring.hide()
                    else:
                        dwell.reset()
                        ring.hide()
                else:
                    dwell.reset()
                    ring.hide()

                # --- pinch = click, pinch + hold = zoom (same as before) ---
                if not pinching and not scrolling and ratio < S.pinch_enter:
                    pinching = True
                    pinch_start = now
                    zoom_mode = False
                    # closing your fingers makes the fingertip drift, so use the position from a few frames ago
                    frozen = history[0] if history else (sx, sy)
                    pyautogui.moveTo(*clamp_to_screen(*frozen))
                    status = "Pinch..."
                elif pinching and not zoom_mode and now - pinch_start > S.hold_time:
                    zoom_mode = True
                    anchor_y = hand[8].y
                    status = "Zoom: hand up = in, down = out"

                if pinching and zoom_mode:
                    dy = anchor_y - hand[8].y
                    if dy > S.zoom_step and zoom_level < S.max_zoom:
                        forget_line()
                        ruler.hide()
                        pyautogui.hotkey("win", "=")
                        zoom_level += 1
                        anchor_y = hand[8].y
                    elif dy < -S.zoom_step and zoom_level > 0:
                        pyautogui.hotkey("win", "esc" if zoom_level == 1 else "-")
                        zoom_level -= 1
                        anchor_y = hand[8].y

                if pinching and ratio > S.pinch_exit:
                    pinching = False
                    if not zoom_mode:
                        pyautogui.click()  # quick pinch = click
                        status = "CLICK"
                    else:
                        status = "Zoom set"
                    history.clear()

                # --- index + middle up = highlight on/off ---
                if two and not scrolling:
                    if two_start is None:
                        two_start = now
                    elif not two_fired and now - two_start >= S.two_finger_hold:
                        two_fired = True
                        toggle("highlight_on", "Highlight")
                    if not two_fired:
                        status = f"Hold... {int((now - two_start) / S.two_finger_hold * 100)}%"
                    else:
                        status = "Highlight ON" if S.highlight_on else "Highlight OFF"
                else:
                    two_start = None
                    two_fired = False

                # --- thumbs up = read the line aloud ---
                if thumbs and not scrolling:
                    if thumb_start is None:
                        thumb_start = now
                        # curling the index finger drags the cursor down, so use where it was a few frames ago
                        thumb_point = history[0] if history else (sx, sy)
                    elif not thumb_fired and now - thumb_start >= S.read_hold:
                        thumb_fired = True
                        status = read_line_at(*thumb_point)
                    if not thumb_fired:
                        status = f"Read... {int((now - thumb_start) / S.read_hold * 100)}%"
                else:
                    thumb_start = None
                    thumb_fired = False

                # --- auto-read: read a line once you've stayed on it for a moment ---
                if (S.auto_read and line_box and not auto_read_done and not scrolling and not pinching
                        and now - line_since >= S.auto_read_delay):
                    auto_read_done = True
                    reader.read_image(grab(line_box))
            else:
                status = "No hand"
                two_start = None
                two_fired = False
                thumb_start = None
                thumb_fired = False
                scrolling = False
                palm_start = None
                dwell.reset()
                ring.hide()

            root.update()  # let tkinter redraw the overlays

            # preview window
            preset = COLOR_PRESETS[S.color_preset % len(COLOR_PRESETS)][0]
            flags = (f"HL {'on' if S.highlight_on else 'off'} | Ruler {'on' if S.ruler_on else 'off'} | "
                     f"Auto-read {'on' if S.auto_read else 'off'} | Dwell {'on' if S.dwell_on else 'off'} | {preset}")
            cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, flags, (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            if reader.status:
                cv2.putText(frame, reader.status, (10, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.putText(frame, HELP, (10, frame.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("h"):
                status = toggle("highlight_on", "Highlight")
            elif key == ord("r"):
                status = toggle("ruler_on", "Ruler")
            elif key == ord("a"):
                status = toggle("auto_read", "Auto-read")
            elif key == ord("d"):
                status = toggle("dwell_on", "Dwell click")
            elif key == ord("c"):
                S.color_preset = (S.color_preset + 1) % len(COLOR_PRESETS)
                settings_file.save(S)
                apply_settings()
            elif key == ord("t"):
                status = read_line_at(sx, sy)
            elif key == ord("s"):
                reader.stop_speaking()
            elif key in (ord("["), ord("]")):
                S.ruler_dim = round(min(0.9, max(0.1, S.ruler_dim + (0.1 if key == ord("[") else -0.1))), 1)
                ruler.set_dim(S.ruler_dim)
                settings_file.save(S)
            elif key in (ord("-"), ord("=")):
                S.voice_rate = min(10, max(-10, S.voice_rate + (1 if key == ord("=") else -1)))
                reader.set_rate(S.voice_rate)
                settings_file.save(S)

            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break  # closed with the X button

finally:
    if zoom_level > 0:
        pyautogui.hotkey("win", "esc")  # close the magnifier
    reader.close()
    cap.release()
    cv2.destroyAllWindows()
    try:
        root.destroy()
    except tk.TclError:
        pass
    for _ in range(5):
        cv2.waitKey(1)
