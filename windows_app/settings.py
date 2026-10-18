# all the tunable settings live here. they're saved to settings.json next to this file,
# so you can change them (close the app first) and they're remembered next time.
# every timing below can be made longer if you need more time for a gesture

import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULTS = {
    # cursor
    "margin": 0.15,  # ignore the outer 15% of the camera frame so you can reach the screen edges
    "steady": 0.5,  # cursor steadiness when your finger is still. lower = steadier (try 0.3 - 1.5)
    "responsive": 0.003,  # how quickly the cursor catches up when you move. higher = less lag
    "still_px": 3,  # ignore wobbles smaller than this many pixels
    "curl_ratio": 0.75,  # index finger bent to below this much of its full length = curling: freeze cursor
    "lookback_s": 0.25,  # when a pinch / curl starts, jump back to where the cursor was this long ago

    # pinch = click, pinch + hold + move = zoom
    "pinch_enter": 0.25,  # pinch "closed" when thumb-index gap is below this fraction of palm size
    "pinch_exit": 0.4,
    "click_confirm": 0.25,  # wait this long before clicking, so a thumbs-up can cancel it
    "hold_time": 0.4,  # hold a pinch this long to zoom instead of click
    "zoom_step": 0.06,  # how far to move your hand (fraction of camera height) per zoom step
    "zoom_min": 50,  # percent
    "zoom_max": 300,

    # highlight (black text on yellow)
    "highlight": True,
    "region_w": 900,  # width of the area around the finger used to find which line it's on
    "search_h": 40,  # px above/below the fingertip to search for text
    "snap": 12,  # snap to text within this many px if the fingertip is between lines
    "ink_diff": 40,  # how different a pixel must be from the background to count as text
    "pad": 3,  # extra px of padding around the highlighted line
    "word_gap": 1.5,  # a gap wider than this many line-heights = end of the line (column edge)

    # thumbs up = read aloud
    "read_hold": 0.5,  # seconds to hold a thumbs-up before it reads
    "rest_time": 0.4,  # a line counts as "the one you're reading" after your finger rests on it this long
    "voice_rate": 0,  # -10 (slow) .. 10 (fast)
    "ocr_lang": "en",
    "announce": True,  # say changes out loud too ("zoom 150 percent", "paused"...)

    # open palm = scroll
    "palm_enter": 0.25,  # hold an open palm this long to start scrolling
    "scroll_deadzone": 0.03,  # how far (fraction of camera height) to move before scrolling starts
    "scroll_speed": 30,  # mouse-wheel notches per second per unit of hand movement. lower = slower
    "scroll_max": 6,  # fastest scroll, in mouse-wheel notches per second

    # preview window
    "text_scale": 0.7,  # size of the text in the preview window
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
