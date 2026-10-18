# finds the line of text under the fingertip in a screenshot, and makes the recolored
# (high contrast) version of it. same logic as find_line() / high_contrast() in hand_cursor1.py,
# just split out so it can be tested without a screen

import cv2
import numpy as np

YELLOW = (255, 255, 0)
BLACK = (0, 0, 0)  # black on yellow = 19.6:1 contrast, well above the 4.5:1 that WCAG AA asks for


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


def line_extent(gray, top, bottom, x, ink_diff=40, word_gap=1.5):
    """gray = a full-screen-width strip, [top, bottom) = the rows of one line, x = fingertip.
    walks left and right from the text nearest the fingertip, and stops at the first gap wider than
    word_gap line-heights (a column edge, sidebar, etc). returns (left, right) or None"""
    rows = gray[top:bottom]
    if rows.size == 0:
        return None
    ink = np.abs(rows - np.median(rows)) > ink_diff
    col_has_ink = ink.any(axis=0)
    w = len(col_has_ink)
    max_gap = max(8, int(word_gap * (bottom - top)))

    cols = np.where(col_has_ink)[0]
    if len(cols) == 0:
        return None
    start = int(cols[np.argmin(np.abs(cols - x))])  # text column closest to the finger
    if abs(start - x) > max_gap:
        return None

    left, gap = start, 0
    for c in range(start - 1, -1, -1):
        if col_has_ink[c]:
            left, gap = c, 0
        else:
            gap += 1
            if gap > max_gap:
                break
    right, gap = start, 0
    for c in range(start + 1, w):
        if col_has_ink[c]:
            right, gap = c, 0
        else:
            gap += 1
            if gap > max_gap:
                break
    return left, right + 1


def high_contrast(rgb, bg_color, fg_color):
    """rgb = HxWx3 screenshot of one line. returns the same line redrawn as text color on bg color.
    keeps the soft (anti-aliased) edges of the letters, so the text looks as smooth as the original
    instead of jagged - the same look as the browser extension's highlight"""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    bg = np.median(gray)  # most of a line is background
    dist = np.abs(gray - bg)  # works for dark-on-light and light-on-dark (dark mode) text
    strongest = dist.max()
    out = np.empty((*gray.shape, 3), dtype=np.float32)
    if strongest < 40:  # no text in there
        out[:] = bg_color
        return out.astype(np.uint8)
    ink = np.clip(dist / (0.85 * strongest), 0, 1)[..., None]  # 0 = background, 1 = solid letter
    out[:] = np.array(bg_color, np.float32) * (1 - ink) + np.array(fg_color, np.float32) * ink
    return np.round(out).astype(np.uint8)


# the frame around the highlight, same as the extension: 3px yellow ring + 1px dark outline, rounded corners
RING = 3
OUTLINE = 1
RADIUS = 3
BORDER = RING + OUTLINE  # how far the frame sticks out around the line


def render_highlight(region, inner, bg_color=(255, 255, 0), fg_color=(0, 0, 0)):
    """region = HxWx3 screenshot of the line plus BORDER px around it, inner = (x0, y0, x1, y1) of the
    line inside that screenshot. returns what the highlight window shows: the line as black text on
    yellow, a yellow ring around it, and a thin see-through dark outline (60% black over the page)"""
    from PIL import Image, ImageDraw

    page = Image.fromarray(region).convert("RGB")
    w, h = page.size
    x0, y0, x1, y1 = inner
    out = page.copy()

    # dark outline: the page darkened to 40%, like rgba(0, 0, 0, .6) in the extension
    outline = Image.new("L", (w, h), 0)
    ImageDraw.Draw(outline).rounded_rectangle(
        (x0 - BORDER, y0 - BORDER, x1 - 1 + BORDER, y1 - 1 + BORDER), radius=RADIUS + BORDER, fill=255)
    out.paste(Image.eval(page, lambda v: int(v * 0.4)), mask=outline)

    # yellow ring
    ImageDraw.Draw(out).rounded_rectangle(
        (x0 - RING, y0 - RING, x1 - 1 + RING, y1 - 1 + RING), radius=RADIUS + RING, fill=bg_color)

    # the line itself, recolored
    text = Image.fromarray(high_contrast(region[y0:y1, x0:x1], bg_color, fg_color))
    corners = Image.new("L", text.size, 0)
    ImageDraw.Draw(corners).rounded_rectangle((0, 0, text.size[0] - 1, text.size[1] - 1), radius=RADIUS, fill=255)
    out.paste(text, (x0, y0), corners)
    return np.array(out)
