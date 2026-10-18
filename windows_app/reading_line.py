"""
Reading Line for Windows - the next version of hand_cursor1.py

setup (once), in this folder:
    pip install -r requirements.txt
run:
    python reading_line.py

gestures:
    point with your index finger       -> moves the mouse, and the line of text under it is highlighted
    thumbs up, hold half a second      -> reads the highlighted line out loud
    open palm, then move up / down     -> scroll (the further you move, the faster)
    quick pinch (thumb + index)        -> click
    pinch + hold, then move up / down  -> zoom in / out, 50% to 300% (same as ctrl + mouse wheel)

keys (click on the preview window first so it gets the key presses):
    space  pause / resume hand control      h  highlight on / off
    t      read the current line            s  stop reading
    -  =   voice slower / faster            q or esc  quit
"""

import ctypes
import math
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
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from PIL import ImageGrab

import gestures
import settings as settings_file
from linefinder import BLACK, YELLOW, find_line_in_gray, high_contrast, line_extent
from overlays import HighlightOverlay
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


overlay = HighlightOverlay()
reader = Reader(S.ocr_lang, S.voice_rate)


def announce(text):
    # spoken feedback, so you don't have to look at the preview window to know what happened
    if S.announce:
        reader.say(text)


# ---------- highlight ----------

line_box = None  # screen rectangle of the line under the finger; None = no text there
overlay_box = None  # the line the highlight is currently drawn on
read_box = None  # the line being read aloud (highlight stays locked on it until the voice is done)
stable = gestures.StableLine(S.rest_time)


def grab(box):
    return ImageGrab.grab(bbox=box, all_screens=True)


def find_line(cx, cy):
    y0 = max(0, int(cy - S.search_h))
    y1 = min(SCREEN_H, int(cy + S.search_h))
    if y1 - y0 < 2:
        return None
    # one screenshot strip across the whole screen width
    full = np.array(grab((0, y0, SCREEN_W, y1)).convert("L")).astype(np.int16)

    # 1) which rows is the line on? only look near the finger, so text in other columns doesn't confuse it
    x0 = max(0, int(cx - S.region_w // 2))
    x1 = min(SCREEN_W, int(cx + S.region_w // 2))
    box = find_line_in_gray(full[:, x0:x1], cx - x0, cy - y0, S.snap, S.ink_diff, S.pad)
    if box is None:
        return None
    top, bottom = box[1], box[3]

    # 2) how far left/right does it go? follow the text until a big gap (column edge), so the whole
    #    line gets highlighted and read, not just the part near your finger
    extent = line_extent(full, top, bottom, cx, S.ink_diff, S.word_gap)
    if extent is None:
        left, right = x0 + box[0], x0 + box[2]
    else:
        left, right = max(0, extent[0] - S.pad), min(SCREEN_W, extent[1] + S.pad)
    return left, y0 + top, right, y0 + bottom


def inside(box, x, y):
    return box is not None and box[0] <= x <= box[2] and box[1] <= y <= box[3]


def show_box(box):
    """highlights `box` (black on yellow). returns the plain screenshot of that line"""
    global overlay_box
    if overlay.visible:
        overlay.hide()  # hide so the screenshot doesn't capture it
        time.sleep(0.03)
    img = grab(box)
    overlay.show(high_contrast(np.array(img.convert("RGB")), YELLOW, BLACK), box)
    overlay_box = box
    return img


def update_line(cx, cy, now):
    """finds the line under the finger, highlights it (if highlight is on) and remembers
    which line you've rested on (for read aloud)"""
    global line_box
    if not inside(line_box, cx, cy):
        if overlay.visible:
            hide_highlight()  # hide so the screenshot doesn't capture it
            time.sleep(0.03)
        line_box = find_line(cx, cy)
    stable.update(line_box, now)
    if line_box and S.highlight:
        if overlay_box != line_box:
            show_box(line_box)
    elif overlay.visible:
        hide_highlight()


def hide_highlight():
    global overlay_box
    overlay.hide()
    overlay_box = None


def forget_line():
    global line_box
    line_box = None
    hide_highlight()


def content_moved():
    # after scrolling / zooming the text is somewhere else, so forget every remembered line
    global read_box
    forget_line()
    stable.reset()
    read_box = None


def read_box_aloud(box):
    """highlights the line and reads it. the highlight stays on it until the voice is done"""
    global read_box
    if box is None:
        announce("No text here")
        return "No text here"
    read_box = box
    reader.read_image(show_box(box))
    return "Reading aloud"


def line_to_read(x, y):
    # the line you rested on, if there is one; otherwise whatever is under (x, y)
    if stable.stable is not None:
        return stable.stable
    if inside(line_box, x, y):
        return line_box
    hide_highlight()
    time.sleep(0.03)
    return find_line(x, y)


# ---------- zoom (ctrl + mouse wheel, like ctrl + / ctrl - in browsers, Word, PDF readers...) ----------

ZOOM_LEVELS = gestures.zoom_levels(S.zoom_min, S.zoom_max)
ZOOM_START = ZOOM_LEVELS.index(100) if 100 in ZOOM_LEVELS else 0
zoom_index = ZOOM_START


def zoom_by(direction):
    """direction +1 = zoom in, -1 = zoom out. returns False at the 50% / 300% limits"""
    global zoom_index
    new = zoom_index + direction
    if not 0 <= new < len(ZOOM_LEVELS):
        return False
    pyautogui.keyDown("ctrl")
    try:
        pyautogui.scroll(120 * direction)  # one mouse-wheel notch = one zoom step
    finally:
        pyautogui.keyUp("ctrl")
    zoom_index = new
    content_moved()
    return True


# ---------- preview window ----------

WINDOW = "Reading Line"
WHITE_BGR, YELLOW_BGR, ORANGE_BGR = (255, 255, 255), (0, 255, 255), (0, 165, 255)
HELP = ["space pause   h highlight   t read   s stop reading",
        "- = voice speed   q quit"]


def draw_text_block(frame, lines, top):
    # text always sits on a solid black box, so it has high contrast no matter what the webcam shows
    # (white on black 21:1, yellow 19.6:1, orange 10.6:1 - WCAG AA needs 4.5:1)
    scale = S.text_scale
    line_h = int(32 * scale / 0.7)
    height = line_h * len(lines) + 10
    y0 = top if top >= 0 else frame.shape[0] - height
    cv2.rectangle(frame, (0, y0), (frame.shape[1], y0 + height), (0, 0, 0), -1)
    for i, (text, color) in enumerate(lines):
        cv2.putText(frame, text, (10, y0 + (i + 1) * line_h), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2,
                    cv2.LINE_AA)


# ---------- main loop ----------

options = vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=model_path()),
    running_mode=vision.RunningMode.VIDEO,  # tracks hands across frames
    num_hands=1,  # either hand works, one at a time
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)

sx, sy = SCREEN_W / 2, SCREEN_H / 2  # smoothed cursor position
history = deque(maxlen=90)  # (time, x, y) of the cursor over the last ~3 seconds
filter_x = gestures.OneEuro(S.steady, S.responsive)  # removes the jitter from the fingertip
filter_y = gestures.OneEuro(S.steady, S.responsive)
ext_ref = 0.0  # how long the index finger looks when it's straight (slowly adapts)
curl_frozen = False  # True while the index finger is curling: cursor stays put


def point_before(now, seconds):
    """where the cursor was `seconds` ago. used when a pinch or curl starts, because bending the
    finger drags the fingertip (and the cursor) away from what you were pointing at"""
    for t, x, y in reversed(history):
        if t <= now - seconds:
            return x, y
    return (history[0][1], history[0][2]) if history else (sx, sy)

paused = False
status = "Move your hand"

pinching = False
pinch_start = 0.0
zoom_mode = False
anchor_y = 0.0
frozen = (sx, sy)
pending_click = None  # (point, time) of a pinch click waiting to happen
pinch_blocked = False  # after a thumbs-up, no pinching until the index finger is up again

palm_start = None
palm_lost = None
scrolling = False
scroll_anchor = 0.0
scroll_acc = 0.0  # leftover fraction of a mouse-wheel notch

thumb_start = None
thumb_fired = False
thumb_point = (sx, sy)
thumb_box = None

cap = cv2.VideoCapture(0)
cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)  # resizable, so you can make the text bigger
start = time.time()
last_t = start
last_ts = -1

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
                pose_info = f"Hand: {gestures.pose_name(hand)}"
            else:
                hand = None
                pose_info = "Hand: not seen"
                filter_x.reset()
                filter_y.reset()
                ext_ref = 0.0
                curl_frozen = False

            if paused:
                status = "PAUSED - press space to resume"
            elif hand is None:
                status = "No hand"
                thumb_start = None
                thumb_fired = False
                scrolling = False
                palm_start = None
                pending_click = None
            else:
                palm = not pinching and gestures.open_palm_pose(hand)
                thumbs = not pinching and gestures.thumbs_up_pose(hand)

                # --- open palm = scroll ---
                if palm:
                    palm_lost = None
                    if palm_start is None:
                        palm_start = now
                    if not scrolling and now - palm_start >= S.palm_enter:
                        scrolling = True
                        scroll_anchor = hand[9].y  # middle of the palm is the steadiest point
                        scroll_acc = 0.0
                        content_moved()
                elif scrolling:
                    if palm_lost is None:
                        palm_lost = now
                    if now - palm_lost > 0.2:  # short grace period so scrolling doesn't stutter
                        scrolling = False
                        palm_start = None
                        history.clear()
                else:
                    palm_start = None

                if scrolling:
                    v = gestures.scroll_velocity(scroll_anchor - hand[9].y, S.scroll_deadzone, S.scroll_speed,
                                                 S.scroll_max)
                    scroll_acc += v * dt
                    notches = int(scroll_acc)
                    if notches:
                        # always whole notches (120 each): lots of windows apps ignore anything smaller
                        pyautogui.scroll(notches * 120)
                        scroll_acc -= notches
                    status = "Scrolling" + (" up" if v > 0 else " down" if v < 0 else ": move palm up or down")

                # --- index finger curling (on the way to a thumbs-up or fist)? freeze the cursor ---
                # the fingertip slides down while it bends, which used to drag the cursor and the
                # highlight onto the lines below. so as soon as it starts bending, snap back to where
                # you were pointing just before, and stay there until the finger straightens again
                ext = gestures.index_extension(hand)
                if not curl_frozen:
                    ext_ref = max(ext, ext_ref * 0.995)  # slowly adapts if you change how you point
                if not curl_frozen and not pinching and ext < S.curl_ratio * ext_ref:
                    curl_frozen = True
                    sx, sy = point_before(now, S.lookback_s)
                    pyautogui.moveTo(*clamp_to_screen(sx, sy))
                elif curl_frozen and ext >= (S.curl_ratio + 0.1) * ext_ref:
                    curl_frozen = False
                    filter_x.reset()  # carry on smoothly from where the cursor is now
                    filter_y.reset()
                    filter_x(sx, now)
                    filter_y(sy, now)
                if curl_frozen and not (pinching or scrolling or thumbs):
                    status = "Holding position (finger bent)"

                # --- pointing: move the cursor + highlight the line under it ---
                if not (pinching or scrolling or palm or thumbs or curl_frozen):
                    tx, ty = to_screen(hand[8])  # index fingertip
                    nx, ny = filter_x(tx, now), filter_y(ty, now)
                    if math.hypot(nx - sx, ny - sy) >= S.still_px:  # ignore tiny wobbles
                        sx, sy = nx, ny
                    history.append((now, sx, sy))
                    pyautogui.moveTo(*clamp_to_screen(sx, sy))
                    status = "Pointing"
                    if not reader.busy:
                        update_line(sx, sy, now)

                # --- pinch = click, pinch + hold + move = zoom ---
                # making a thumbs-up drags the index finger past the thumb, which looks like a pinch.
                # so a pinch that turns into a thumbs-up is cancelled, and every click waits
                # click_confirm seconds in case the thumb is on its way up
                thumb_going_up = gestures.thumbs_up_pose(hand) or gestures.thumb_rising(hand)
                if pinch_blocked and gestures.finger_up(hand, 8, 6) and not thumb_going_up:
                    pinch_blocked = False

                if pending_click and thumb_going_up:
                    pending_click = None
                elif pending_click and now - pending_click[1] >= S.click_confirm:
                    pyautogui.click(*clamp_to_screen(*pending_click[0]))
                    pending_click = None
                    status = "Click"

                if pinching and not zoom_mode and gestures.thumbs_up_pose(hand):
                    pinching = False
                    pinch_blocked = True
                    history.clear()

                if not pinching and not pinch_blocked and not scrolling and ratio < S.pinch_enter:
                    pinching = True
                    pinch_start = now
                    zoom_mode = False
                    # closing your fingers makes the fingertip drift, so use the position from a few frames ago
                    frozen = (sx, sy) if curl_frozen else point_before(now, S.lookback_s)
                    pyautogui.moveTo(*clamp_to_screen(*frozen))
                    status = "Pinch"
                elif pinching and not zoom_mode and now - pinch_start > S.hold_time:
                    zoom_mode = True
                    anchor_y = hand[8].y
                    status = f"Zoom {ZOOM_LEVELS[zoom_index]}%: move hand up to zoom in, down to zoom out"

                if pinching and zoom_mode:
                    dy = anchor_y - hand[8].y
                    if abs(dy) > S.zoom_step:
                        anchor_y = hand[8].y  # each step needs a new movement
                        direction = 1 if dy > 0 else -1
                        if zoom_by(direction):
                            status = f"Zoom {ZOOM_LEVELS[zoom_index]}%"
                            announce(f"Zoom {ZOOM_LEVELS[zoom_index]} percent")
                        else:
                            limit = "maximum" if direction > 0 else "minimum"
                            status = f"Zoom {ZOOM_LEVELS[zoom_index]}% ({limit})"
                            announce(f"{limit} zoom")

                if pinching and ratio > S.pinch_exit:
                    pinching = False
                    if not zoom_mode:
                        pending_click = (frozen, now)  # quick pinch = click (in a moment, see above)
                    history.clear()

                # --- thumbs up = read the line aloud ---
                if thumbs and not scrolling:
                    if thumb_start is None:
                        thumb_start = now
                        # making the thumbs-up moved your fingertip, so read the line you rested on before
                        thumb_point = (sx, sy) if curl_frozen else point_before(now, S.lookback_s)
                        thumb_box = line_to_read(*thumb_point)
                        if thumb_box and not reader.busy:
                            show_box(thumb_box)  # shows which line is about to be read
                    elif not thumb_fired and now - thumb_start >= S.read_hold:
                        thumb_fired = True
                        status = read_box_aloud(thumb_box)
                    if not thumb_fired:
                        status = f"Thumbs up: reading in {max(0.0, S.read_hold - (now - thumb_start)):.1f}s"
                else:
                    thumb_start = None
                    thumb_fired = False

            # done reading? let the highlight follow your finger again
            if read_box is not None and not reader.busy:
                read_box = None
                forget_line()
            if read_box is not None and not paused:
                status = "Reading aloud" + (f": {reader.last_text[:40]}..." if reader.last_text else "")

            overlay.update()  # let tkinter redraw the highlight

            # preview window
            mode = (f"Highlight {'on' if S.highlight else 'off'}   Zoom {ZOOM_LEVELS[zoom_index]}%   "
                    f"{pose_info}")
            top_lines = [(status, YELLOW_BGR), (mode, WHITE_BGR)]
            if reader.status:
                top_lines.append((reader.status, ORANGE_BGR))
            draw_text_block(frame, top_lines, 0)
            draw_text_block(frame, [(line, WHITE_BGR) for line in HELP], -1)
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord(" "):
                paused = not paused
                pinching = scrolling = False
                pending_click = None
                content_moved()
                announce("Paused" if paused else "Resumed")
            elif key == ord("h"):
                S.highlight = not S.highlight
                settings_file.save(S)
                forget_line()
                announce(f"Highlight {'on' if S.highlight else 'off'}")
            elif key == ord("t"):
                status = read_box_aloud(line_box if inside(line_box, sx, sy) else line_to_read(sx, sy))
            elif key == ord("s"):
                reader.stop_speaking()
            elif key in (ord("-"), ord("=")):
                S.voice_rate = min(10, max(-10, S.voice_rate + (1 if key == ord("=") else -1)))
                reader.set_rate(S.voice_rate)
                settings_file.save(S)
                announce(f"Voice speed {S.voice_rate}")

            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break  # closed with the X button

finally:
    # put the zoom back where it started
    while zoom_index != ZOOM_START:
        if not zoom_by(1 if zoom_index < ZOOM_START else -1):
            break
    pyautogui.keyUp("ctrl")
    reader.close()
    cap.release()
    cv2.destroyAllWindows()
    overlay.destroy()
    for _ in range(5):
        cv2.waitKey(1)
