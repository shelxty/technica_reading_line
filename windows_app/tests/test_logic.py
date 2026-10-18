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
from linefinder import BLACK, YELLOW, find_line_in_gray, high_contrast, line_extent  # noqa: E402

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
    assert gestures.pose_name(h) == "pointing"


def test_open_palm_scrolls_with_or_without_thumb():
    assert gestures.open_palm_pose(make_hand(index=True, middle=True, ring=True, pinky=True, thumb="out"))
    assert gestures.open_palm_pose(make_hand(index=True, middle=True, ring=True, pinky=True, thumb="tucked"))
    assert not gestures.thumbs_up_pose(make_hand(index=True, middle=True, ring=True, pinky=True))


def test_thumbs_up():
    h = make_hand(index=False, thumb="up")
    assert gestures.thumbs_up_pose(h)
    assert not gestures.open_palm_pose(h)
    assert gestures.pose_name(h) == "thumbs up"


def test_fist_without_thumb_is_not_thumbs_up():
    assert not gestures.thumbs_up_pose(make_hand(index=False, thumb="tucked"))


def test_thumb_rising_only_with_curled_fingers():
    assert gestures.thumb_rising(make_hand(index=False, thumb="up"))
    assert not gestures.thumb_rising(make_hand(index=True, thumb="up"))  # pointing with thumb up
    assert not gestures.thumb_rising(make_hand(index=True, thumb="pinch"))


def test_pinch():
    assert gestures.pinch_ratio(make_hand(thumb="pinch")) < 0.25
    assert gestures.pinch_ratio(make_hand(thumb="out")) > 0.4
    assert gestures.pose_name(make_hand(thumb="pinch")) == "pinch"


# ---------- scrolling ----------

def test_scroll_deadzone_direction_and_speed():
    assert gestures.scroll_velocity(0.02, 0.03, 60) == 0
    assert gestures.scroll_velocity(0.13, 0.03, 60) > 0  # hand up = scroll up
    assert gestures.scroll_velocity(-0.13, 0.03, 60) < 0
    assert gestures.scroll_velocity(0.2, 0.03, 60) > gestures.scroll_velocity(0.1, 0.03, 60)
    # a comfortable hand movement gives a few notches per second (each one gets sent as a full 120)
    assert 3 <= gestures.scroll_velocity(0.1, 0.03, 60) <= 6


def test_scroll_default_is_slower_and_capped():
    d = settings.DEFAULTS
    comfy = gestures.scroll_velocity(0.1, d["scroll_deadzone"], d["scroll_speed"], d["scroll_max"])
    assert 1 <= comfy <= 3  # a comfortable hand movement: 1-3 notches per second
    far = gestures.scroll_velocity(0.5, d["scroll_deadzone"], d["scroll_speed"], d["scroll_max"])
    assert far == d["scroll_max"]  # never faster than the cap
    assert gestures.scroll_velocity(-0.5, 0.03, 30, 6) == -6


# ---------- steady cursor ----------

def test_one_euro_removes_jitter_when_still():
    import random
    random.seed(1)
    f = gestures.OneEuro(0.5, 0.003)
    out = [f(500 + random.uniform(-8, 8), i / 30) for i in range(90)]  # finger "still" but noisy
    assert max(out[30:]) - min(out[30:]) < 6  # raw noise spans 16px


def test_one_euro_still_follows_real_movement():
    f = gestures.OneEuro(0.5, 0.003)
    for i in range(30):
        f(100, i / 30)
    x = 100
    for i in range(30, 60):  # move 1000px in one second
        x = f(100 + (i - 29) * 33.3, i / 30)
    assert x > 700  # caught up most of the way, no big lag


def test_index_extension_drops_when_curling():
    straight = gestures.index_extension(make_hand(index=True, thumb="tucked"))
    curled = gestures.index_extension(make_hand(index=False, thumb="up"))
    assert curled < settings.DEFAULTS["curl_ratio"] * straight


# ---------- zoom ----------

def test_zoom_goes_from_50_to_300_percent():
    levels = gestures.zoom_levels(50, 300)
    assert levels[0] == 50 and levels[-1] == 300
    assert 100 in levels
    assert levels == sorted(levels)


# ---------- line finder ----------

def load_font():
    try:
        return ImageFont.load_default(size=18)
    except TypeError:  # older pillow
        return ImageFont.load_default()


def render_text_strip():
    # three lines of black text on white, 35px apart, like a screenshot strip
    img = Image.new("L", (600, 120), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(["First line of text here", "Second line is in the middle", "Third line"]):
        draw.text((40, 10 + i * 35), line, fill=0, font=load_font())
    return np.array(img).astype(np.int16)


def render_two_columns():
    # a long line on the left, then a big gutter, then a second column - like a 2-column page
    img = Image.new("L", (1400, 60), 255)
    draw = ImageDraw.Draw(img)
    font = load_font()
    left_text = "This is a long line of text in the left column that goes past nine hundred px wide ok"
    draw.text((20, 20), left_text, fill=0, font=font)
    left_end = int(20 + draw.textlength(left_text, font=font))
    draw.text((left_end + 120, 20), "right column", fill=0, font=font)
    return np.array(img).astype(np.int16), left_end


def test_finds_the_line_under_the_finger():
    gray = render_text_strip()
    box = find_line_in_gray(gray, 100, 55, pad=0)  # middle line
    assert box is not None
    left, top, right, bottom = box
    assert 40 <= top <= 55 <= bottom <= 75
    assert left >= 38 and right > 200
    assert bottom - top < 30  # nothing from the line above or below got included


def test_snaps_to_nearby_line_from_a_gap():
    gray = render_text_strip()
    on_line = find_line_in_gray(gray, 100, 55, pad=0)
    assert find_line_in_gray(gray, 100, on_line[3] + 3, pad=0) is not None


def test_blank_area_returns_none():
    gray = np.full((80, 300), 255, dtype=np.int16)
    assert find_line_in_gray(gray, 150, 40) is None


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


def test_high_contrast_recolors_text():
    rgb = np.full((20, 50, 3), 255, dtype=np.uint8)
    rgb[5:15, 10:20] = 0  # "text"
    out = high_contrast(rgb, YELLOW, BLACK)
    assert tuple(out[10, 15]) == BLACK
    assert tuple(out[0, 0]) == YELLOW


def test_high_contrast_keeps_smooth_letter_edges():
    rgb = np.full((20, 50, 3), 255, dtype=np.uint8)
    rgb[5:15, 10:20] = 0  # solid letter
    rgb[5:15, 20] = 128  # soft (anti-aliased) edge
    out = high_contrast(rgb, YELLOW, BLACK)
    edge = out[10, 20]
    assert 0 < edge[0] < 255 and edge[2] == 0  # in between black and yellow, not snapped to either


def test_high_contrast_dark_mode_text():
    rgb = np.full((20, 50, 3), 30, dtype=np.uint8)  # dark background
    rgb[5:15, 10:20] = 220  # light text
    out = high_contrast(rgb, YELLOW, BLACK)
    assert tuple(out[10, 15]) == BLACK and tuple(out[0, 0]) == YELLOW


def test_highlight_frame_looks_like_the_extension():
    from linefinder import BORDER, RING, render_highlight
    h, w = 30, 120
    region = np.full((h + 2 * BORDER, w + 2 * BORDER, 3), 255, dtype=np.uint8)  # white page
    region[BORDER + 10:BORDER + 20, BORDER + 20:BORDER + 40] = 0  # some text
    out = render_highlight(region, (BORDER, BORDER, BORDER + w, BORDER + h))
    mid_y = BORDER + h // 2
    assert tuple(out[mid_y, BORDER + 25]) == BLACK  # text -> black
    assert tuple(out[mid_y, BORDER + 80]) == YELLOW  # line background -> yellow
    assert tuple(out[mid_y, BORDER - RING]) == YELLOW  # 3px yellow ring
    assert tuple(out[mid_y, 0]) == (102, 102, 102)  # outline = page darkened by 60%
    assert tuple(out[0, 0]) == (255, 255, 255)  # rounded corner: page shows through


# ---------- contrast (WCAG 2.0 AA / Section 508: at least 4.5:1 for text) ----------

def contrast(rgb1, rgb2):
    def luminance(rgb):
        def channel(c):
            c /= 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (channel(c) for c in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(rgb1), luminance(rgb2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_highlight_contrast():
    assert contrast(BLACK, YELLOW) >= 4.5


def test_preview_text_contrast():
    # the preview text colors (white, yellow, orange) on their black text box
    for color in [(255, 255, 255), (255, 255, 0), (255, 165, 0)]:
        assert contrast(color, (0, 0, 0)) >= 4.5, color


# ---------- settings ----------

def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    s = settings.load()
    assert s.highlight is True  # highlight is on by default
    s.highlight = False
    s["read_hold"] = 1.0
    settings.save(s)
    s2 = settings.load()
    assert s2.highlight is False and s2.read_hold == 1.0


def test_old_settings_are_dropped(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"ruler_on": true, "scroll_notches": 60, "steady": 0.8}')
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(path))
    s = settings.load()
    assert "ruler_on" not in s and "scroll_notches" not in s  # old settings are ignored
    assert s.scroll_speed == settings.DEFAULTS["scroll_speed"]  # so the new slower default applies
    assert s.steady == 0.8  # current settings are kept


# ---------- which line gets read ----------

LINE_A = (0, 100, 800, 120)
LINE_B = (0, 125, 800, 145)


def test_reads_the_line_you_rested_on_not_the_one_you_passed():
    st = gestures.StableLine(hold=0.4)
    for i in range(20):  # rest on line A for 0.66 s
        st.update(LINE_A, i / 30)
    t = 20 / 30
    for i in range(6):  # making the thumbs-up drags the finger across line B for 0.2 s
        st.update(LINE_B, t + i / 30)
    assert st.stable == LINE_A


def test_resting_on_a_new_line_switches_to_it():
    st = gestures.StableLine(hold=0.4)
    st.update(LINE_A, 0.0)
    st.update(LINE_A, 0.5)
    st.update(LINE_B, 0.6)
    st.update(LINE_B, 1.1)
    assert st.stable == LINE_B


def test_stable_line_forgotten_after_reset():
    st = gestures.StableLine(hold=0.4)
    st.update(LINE_A, 0.0)
    st.update(LINE_A, 0.5)
    st.reset()
    assert st.stable is None


# ---------- read aloud keeps "busy" until the voice is done ----------

import time  # noqa: E402

import speech  # noqa: E402


class FakeVoice:
    def __init__(self, talk_time):
        self.talk_time = talk_time
        self.spoken = []
        self.started = 0.0
        self.Rate = 0

    def Speak(self, text, flags):  # noqa: N802 - SAPI's name
        self.spoken.append(text)
        self.started = time.time()

    def WaitUntilDone(self, ms):  # noqa: N802
        return time.time() - self.started >= self.talk_time


def make_reader(talk_time=0.6, text="hello world"):
    class TestReader(speech.Reader):
        def _make_voice(self):
            self.fake = FakeVoice(talk_time)
            return self.fake

        def _ocr(self, img, loop):
            return text

    r = TestReader()
    time.sleep(0.05)
    return r


def wait_until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_busy_while_reading_then_free():
    r = make_reader(talk_time=0.6)
    r.read_image(Image.new("RGB", (10, 10)))
    assert r.busy
    time.sleep(0.4)
    assert r.busy  # still talking
    assert wait_until(lambda: not r.busy)
    assert r.fake.spoken == ["hello world"]
    r.close()


def test_stop_frees_immediately():
    r = make_reader(talk_time=5)
    r.read_image(Image.new("RGB", (10, 10)))
    assert wait_until(lambda: r.fake.spoken)
    r.stop_speaking()
    assert not r.busy
    r.close()


def test_no_text_found_is_not_busy():
    r = make_reader(text="")
    r.read_image(Image.new("RGB", (10, 10)))
    assert wait_until(lambda: not r.busy)
    r.close()
