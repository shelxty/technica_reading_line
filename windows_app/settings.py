# all the tunable settings live here. they're saved to settings.json next to this file,
# so whatever you change with the keyboard shortcuts is remembered next time

import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULTS = {
    # cursor + pinch (same as hand_cursor1.py)
    "margin": 0.15,  # ignore the outer 15% of the camera frame so you can reach the edges
    "smooth": 0.8,  # cursor smoothing. higher = steadier but laggier
    "pinch_enter": 0.25,  # pinch "closed" when thumb-index gap is below this fraction of palm size
    "pinch_exit": 0.4,
    "hold_time": 0.4,  # hold a pinch this long to zoom instead of click
    "zoom_step": 0.06,
    "max_zoom": 5,
    "lookback": 6,  # use cursor position from this many frames ago when a pinch starts
    "two_finger_hold": 0.8,

    # line detection
    "region_w": 900,  # width of screenshot strip
    "search_h": 40,  # px above/below the fingertip to search for text
    "snap": 12,  # snap to text within this many px if the fingertip is between lines
    "ink_diff": 40,  # how different a pixel must be from the background to count as text
    "pad": 3,  # extra px of padding around the highlighted line

    # highlight look (index into linefinder.COLOR_PRESETS)
    "color_preset": 0,
    "highlight_on": False,

    # reading ruler: dims the whole screen except the line you're on
    "ruler_on": False,
    "ruler_dim": 0.6,  # 0 = no dimming, 1 = black

    # read aloud
    "auto_read": False,  # read each new line automatically after you stay on it
    "auto_read_delay": 0.8,  # seconds on a line before auto-read kicks in
    "read_hold": 0.5,  # seconds to hold thumbs-up before it reads
    "voice_rate": 0,  # -10 (slow) .. 10 (fast)
    "ocr_lang": "en",

    # dwell click: hold the cursor still to click (no pinch needed)
    "dwell_on": False,
    "dwell_time": 1.5,
    "dwell_radius": 25,  # px the cursor can wobble and still count as "still"

    # open-palm scrolling
    "palm_enter": 0.25,  # hold an open palm this long to start scrolling
    "scroll_deadzone": 0.03,  # how far (fraction of camera height) to move before scrolling starts
    "scroll_speed": 6000,  # scroll speed per unit of hand movement (120 = one mouse-wheel notch)
}


class Settings(dict):
    # dict that also lets you write s.smooth instead of s["smooth"]
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def load():
    s = Settings(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                saved = json.load(f)
            s.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            print("settings.json is broken, using defaults")
    return s


def save(s):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(dict(s), f, indent=2)
