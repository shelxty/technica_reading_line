# the see-through windows drawn on top of everything:
#   LineOverlay - the recolored (high contrast) line
#   RulerMask   - dims the whole screen except a hole over the current line
#   DwellRing   - progress ring around the cursor for dwell click
# all of them are click-through so you can still use whatever is underneath

import ctypes
import tkinter as tk

from PIL import Image, ImageTk

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20  # clicks pass through
WS_EX_TOOLWINDOW = 0x80  # no taskbar icon
WS_EX_NOACTIVATE = 0x08000000  # never steals focus
LWA_ALPHA = 0x2
WDA_EXCLUDEFROMCAPTURE = 0x11  # windows 10 2004+: screenshots don't see this window

KEY = "#ff00fe"  # pixels of this exact color are fully see-through


def _make_click_through(win, set_alpha):
    """turns a tk window into a click-through overlay. returns True if it's also hidden from screenshots,
    which means we can screenshot the text under it without hiding it first (no flicker)"""
    win.update_idletasks()
    hwnd = user32.GetAncestor(win.winfo_id(), 2)  # native window handle
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                          style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    if set_alpha:
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)  # a layered window with no alpha is invisible
    return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


class _Overlay:
    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)  # no title bar
        self.win.attributes("-topmost", True)
        self.win.withdraw()
        self.visible = False
        self.excluded = False

    def _show(self):
        if not self.visible:
            self.win.deiconify()
            self.visible = True
        self.win.attributes("-topmost", True)

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False

    # used to take screenshots when the window can't be hidden from capture (older windows)
    def suspend(self):
        if self.visible:
            self.win.withdraw()

    def resume(self):
        if self.visible:
            self.win.deiconify()
            self.win.attributes("-topmost", True)


class LineOverlay(_Overlay):
    def __init__(self, root):
        super().__init__(root)
        self.label = tk.Label(self.win, borderwidth=0, padx=0, pady=0)
        self.label.pack()
        self.excluded = _make_click_through(self.win, set_alpha=True)

    def show(self, rgb, box):
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.config(image=photo)
        self.label.image = photo  # keep a reference so it isn't garbage collected
        w, h = box[2] - box[0], box[3] - box[1]
        self.win.geometry(f"{w}x{h}+{box[0]}+{box[1]}")
        self._show()


class RulerMask(_Overlay):
    def __init__(self, root, screen_w, screen_h, dim):
        super().__init__(root)
        self.win.geometry(f"{screen_w}x{screen_h}+0+0")
        self.canvas = tk.Canvas(self.win, width=screen_w, height=screen_h, bg="black",
                                highlightthickness=0, borderwidth=0)
        self.canvas.pack()
        self.hole = self.canvas.create_rectangle(0, 0, 0, 0, fill=KEY, outline="")
        # tk sets up the transparency first, then we add click-through on top
        self.win.attributes("-alpha", dim)
        self.win.attributes("-transparentcolor", KEY)
        self.excluded = _make_click_through(self.win, set_alpha=False)

    def set_dim(self, dim):
        self.win.attributes("-alpha", dim)

    def show(self, box):
        self.canvas.coords(self.hole, *box)
        self._show()


class DwellRing(_Overlay):
    SIZE = 56

    def __init__(self, root):
        super().__init__(root)
        s = self.SIZE
        self.canvas = tk.Canvas(self.win, width=s, height=s, bg=KEY, highlightthickness=0, borderwidth=0)
        self.canvas.pack()
        self.canvas.create_oval(6, 6, s - 6, s - 6, outline="#ffffff", width=6)  # track
        self.arc = self.canvas.create_arc(6, 6, s - 6, s - 6, start=90, extent=0,
                                          style="arc", outline="#ff8c00", width=6)
        self.win.attributes("-transparentcolor", KEY)
        self.excluded = _make_click_through(self.win, set_alpha=False)

    def show(self, x, y, progress):
        self.canvas.itemconfig(self.arc, extent=-359.9 * min(progress, 1.0))  # clockwise from the top
        s = self.SIZE
        self.win.geometry(f"{s}x{s}+{int(x - s / 2)}+{int(y - s / 2)}")
        self._show()
