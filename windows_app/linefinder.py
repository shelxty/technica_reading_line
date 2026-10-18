# finds the line of text under the fingertip in a screenshot, and makes the recolored
# (high contrast) version of it. same logic as find_line() / high_contrast() in hand_cursor1.py,
# just split out so it can be tested without a screen

import cv2
import numpy as np

# (name, background RGB, text RGB)
COLOR_PRESETS = [
    ("Yellow", (255, 255, 0), (0, 0, 0)),  # the original black on yellow
    ("Dark", (0, 0, 0), (255, 255, 0)),  # yellow on black, easier on the eyes at night
    ("Blue tint", (200, 225, 255), (0, 0, 0)),  # soft tints some people with dyslexia prefer
    ("Peach", (255, 218, 185), (0, 0, 0)),
    ("White on blue", (0, 40, 120), (255, 255, 255)),
]


def find_line_in_gray(gray, rx, ry, snap=12, ink_diff=40, pad=3):
    """gray = 2D int array (a strip of the screen), (rx, ry) = fingertip inside it.
    returns (left, top, right, bottom) of the text line in strip coords, or None"""
    h, w = gray.shape
    bg = np.median(gray)  # most common-ish color = background
    ink = np.abs(gray - bg) > ink_diff  # True = text pixel
    row_has_ink = ink.sum(axis=1) >= 2
    ry = min(max(int(ry), 0), h - 1)

    if not row_has_ink[ry]:
        # fingertip is between lines, look up and down for the nearest text
        for d in range(1, snap + 1):
            if ry - d >= 0 and row_has_ink[ry - d]:
                ry -= d
                break
            if ry + d < h and row_has_ink[ry + d]:
                ry += d
                break
        else:
            return None

    # grow up and down until 3+ empty rows in a row
    top, gap = ry, 0
    while top > 0 and gap <= 2:
        top -= 1
        gap = 0 if row_has_ink[top] else gap + 1
    top += gap
    bot, gap = ry, 0
    while bot < h - 1 and gap <= 2:
        bot += 1
        gap = 0 if row_has_ink[bot] else gap + 1
    bot -= gap

    cols = np.where(ink[top:bot + 1])[1]
    if len(cols) == 0:
        return None
    return (max(0, int(cols.min()) - pad), max(0, top - pad),
            min(w, int(cols.max()) + 1 + pad), min(h, bot + 1 + pad))


def high_contrast(rgb, bg_color, fg_color):
    """rgb = HxWx3 screenshot of one line. returns the same line redrawn as text color on bg color"""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)  # split light/dark automatically
    text = mask > 0 if (mask > 0).mean() < 0.5 else mask == 0  # text = the smaller group
    out = np.empty((*gray.shape, 3), dtype=np.uint8)
    out[:] = bg_color
    out[text] = fg_color
    return out
