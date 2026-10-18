# tests for the parts that don't need a webcam or windows.
# run from the windows_app folder:  python -m pytest tests

import os
import sys
from collections import namedtuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import gestures  # noqa: E402
import settings  # noqa: E402
from linefinder import find_line_in_gray, high_contrast, line_extent  # noqa: E402

P = namedtuple("P", "x y")

# fake upright right hand, palm facing the camera. palm size (wrist to middle base) = 0.2
MCP_X = {5: 0.45, 9: 0.50, 13: 0.55, 17: 0.60}


def make_hand(index=True, middle=False, ring=False, pinky=False, thumb="out"):
    pts = [P(0, 0)] * 21
    pts[0] = P(0.5, 0.8)  # wrist
    for base, up in ((5, index), (9, middle), (13, ring), (17, pinky)):
        x = MCP_X[base]
        pts[base] = P(x, 0.6)
        if up:  # straight up
            pts[base + 1], pts[base + 2], pts[base + 3] = P(x, 0.52), P(x, 0.48), P(x, 0.44)
        else:  # curled into the palm
            pts[base + 1], pts[base + 2], pts[base + 3] = P(x, 0.55), P(x, 0.58), P(x, 0.63)
    pts[1] = P(0.42, 0.75)
    if thumb == "out":
        pts[2], pts[3], pts[4] = P(0.38, 0.70), P(0.35, 0.65), P(0.33, 0.60)
    elif thumb == "up":
        pts[2], pts[3], pts[4] = P(0.40, 0.68), P(0.40, 0.58), P(0.40, 0.48)
    elif thumb == "tucked":
        pts[2], pts[3], pts[4] = P(0.44, 0.70), P(0.46, 0.67), P(0.47, 0.65)
    elif thumb == "pinch":
        pts[2], pts[3], pts[4] = P(0.42, 0.65), P(0.44, 0.52), P(0.45, 0.45)
    return pts


# ---------- poses ----------

def test_pointing_is_no_special_pose():
    h = make_hand(index=True, thumb="tucked")
    assert not gestures.open_palm_pose(h)
    assert not gestures.thumbs_up_pose(h)
    assert not gestures.two_finger_pose(h)


def test_two_fingers():
    assert gestures.two_finger_pose(make_hand(index=True, middle=True, thumb="tucked"))


def test_open_palm():
    h = make_hand(index=True, middle=True, ring=True, pinky=True, thumb="out")
    assert gestures.open_palm_pose(h)
    assert not gestures.two_finger_pose(h)
    assert not gestures.thumbs_up_pose(h)


def test_open_palm_with_thumb_tucked_still_counts():
    assert gestures.open_palm_pose(make_hand(index=True, middle=True, ring=True, pinky=True, thumb="tucked"))


def test_fist():
    assert gestures.fist_pose(make_hand(index=False, thumb="tucked"))
    assert gestures.fist_pose(make_hand(index=False, thumb="up"))  # thumbs up is a kind of fist
    assert not gestures.fist_pose(make_hand(index=True, thumb="tucked"))  # pointing is not


def test_thumb_rising_only_with_curled_fingers():
    assert gestures.thumb_rising(make_hand(index=False, thumb="up"))
    assert not gestures.thumb_rising(make_hand(index=True, thumb="up"))  # pointing with thumb up
    assert not gestures.thumb_rising(make_hand(index=True, thumb="pinch"))


def test_pose_names():
    assert gestures.pose_name(make_hand(index=True, thumb="tucked")) == "pointing"
    assert gestures.pose_name(make_hand(index=True, middle=True, ring=True, pinky=True)) == "open palm"
    assert gestures.pose_name(make_hand(index=False, thumb="up")) == "thumbs up"
    assert gestures.pose_name(make_hand(index=True, middle=True, thumb="tucked")) == "two fingers"
    assert gestures.pose_name(make_hand(thumb="pinch")) == "pinch"


def test_thumbs_up():
    h = make_hand(index=False, thumb="up")
    assert gestures.thumbs_up_pose(h)
    assert not gestures.open_palm_pose(h)
    assert not gestures.two_finger_pose(h)


def test_fist_without_thumb_is_not_thumbs_up():
    assert not gestures.thumbs_up_pose(make_hand(index=False, thumb="tucked"))


def test_pinch_ratio():
    assert gestures.pinch_ratio(make_hand(thumb="pinch")) < 0.25
    assert gestures.pinch_ratio(make_hand(thumb="out")) > 0.4


# ---------- scrolling ----------

def test_scroll_deadzone_and_direction():
    assert gestures.scroll_velocity(0.02, 0.03, 60) == 0
    assert gestures.scroll_velocity(0.13, 0.03, 60) > 0  # hand up = scroll up
    assert gestures.scroll_velocity(-0.13, 0.03, 60) < 0
    # further = faster
    assert gestures.scroll_velocity(0.2, 0.03, 60) > gestures.scroll_velocity(0.1, 0.03, 60)
    # a comfortable hand movement gives a few notches per second (each one gets sent as a full 120)
    assert 3 <= gestures.scroll_velocity(0.1, 0.03, 60) <= 6


# ---------- dwell ----------

def test_dwell_fires_once_then_needs_a_move():
    d = gestures.Dwell(radius=25, hold=1.5)
    assert d.update(100, 100, 0.0) == (0.0, False)
    p, fire = d.update(105, 102, 0.75)
    assert 0.4 < p < 0.6 and not fire
    assert d.update(103, 99, 1.6)[1] is True  # fires
    assert d.update(103, 99, 3.5)[1] is False  # still there, doesn't fire again
    d.update(300, 300, 4.0)  # move away
    assert d.update(300, 300, 5.6)[1] is True  # fires at the new spot


def test_dwell_resets_when_moving():
    d = gestures.Dwell(radius=25, hold=1.5)
    d.update(100, 100, 0.0)
    d.update(140, 100, 1.0)  # moved beyond radius, timer restarts
    assert d.update(140, 100, 2.0)[1] is False
    assert d.update(140, 100, 2.6)[1] is True


# ---------- line finder ----------

def render_text_strip():
    # three lines of black text on white, 30px apart, like a screenshot strip
    img = Image.new("L", (600, 120), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # older pillow
        font = ImageFont.load_default()
    for i, line in enumerate(["First line of text here", "Second line is in the middle", "Third line"]):
        draw.text((40, 10 + i * 35), line, fill=0, font=font)
    return np.array(img).astype(np.int16)


def ink_rows(gray, box):
    return gray[box[1]:box[3], box[0]:box[2]]


def test_finds_the_line_under_the_finger():
    gray = render_text_strip()
    box = find_line_in_gray(gray, 100, 55, pad=0)  # middle line
    assert box is not None
    left, top, right, bottom = box
    assert 40 <= top <= 55 <= bottom <= 75
    assert left >= 38 and right > 200
    # nothing from the line above or below got included
    assert (ink_rows(gray, box) < 128).any()
    assert bottom - top < 30


def test_snaps_to_nearby_line_from_a_gap():
    gray = render_text_strip()
    on_line = find_line_in_gray(gray, 100, 55, pad=0)
    gap_y = on_line[3] + 3  # just below the middle line
    assert find_line_in_gray(gray, 100, gap_y, pad=0) is not None


def render_two_columns():
    # a long line on the left, then a big gutter, then a second column - like a 2-column page
    img = Image.new("L", (1400, 60), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:
        font = ImageFont.load_default()
    left_text = "This is a long line of text in the left column that goes past nine hundred px wide ok"
    draw.text((20, 20), left_text, fill=0, font=font)
    left_end = int(20 + draw.textlength(left_text, font=font))
    draw.text((left_end + 120, 20), "right column", fill=0, font=font)
    return np.array(img).astype(np.int16), left_end


def test_line_extent_follows_the_whole_line_but_stops_at_the_gutter():
    gray, left_end = render_two_columns()
    box = find_line_in_gray(gray, 300, 30, pad=0)
    left, right = line_extent(gray, box[1], box[3], 300)
    assert left <= 22  # reached the start of the line
    assert left_end - 15 <= right <= left_end + 3  # reached the end of the line...
    assert right < left_end + 100  # ...but didn't jump the gutter into the right column


def test_line_extent_far_from_text_is_none():
    gray, _ = render_two_columns()
    box = find_line_in_gray(gray, 300, 30, pad=0)
    assert line_extent(gray, box[1], box[3], 1390) is None


def test_blank_area_returns_none():
    gray = np.full((80, 300), 255, dtype=np.int16)
    assert find_line_in_gray(gray, 150, 40) is None


def test_high_contrast_recolors_text():
    rgb = np.full((20, 50, 3), 255, dtype=np.uint8)
    rgb[5:15, 10:20] = 0  # "text"
    out = high_contrast(rgb, (255, 255, 0), (0, 0, 0))
    assert tuple(out[10, 15]) == (0, 0, 0)  # text -> black
    assert tuple(out[0, 0]) == (255, 255, 0)  # background -> yellow


# ---------- settings ----------

def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    s = settings.load()
    assert s.smooth == settings.DEFAULTS["smooth"]
    s.ruler_on = True
    s["dwell_time"] = 2.0
    settings.save(s)
    s2 = settings.load()
    assert s2.ruler_on is True and s2.dwell_time == 2.0
