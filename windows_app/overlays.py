# the see-through windows drawn on top of everything:
#   LineOverlay - the recolored (high contrast) line
#   RulerMask   - dims the whole screen except the current line (4 dark panels around it)
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


class _Overlay:
    # tk only creates the real (outer) window the first time it's shown, and can rebuild it later.
    # so we show each overlay once off-screen at startup, and re-check the click-through style every
    # time it's shown. otherwise the style lands on the wrong window and the overlay blocks your clicks

    def __init__(self, root, tk_layered=False, alpha=255):
        self.tk_layered = tk_layered  # True if tk handles transparency (-transparentcolor)
        self.alpha = alpha  # 0..255, how see-through the window is (only when tk_layered is False)
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)  # no title bar
        self.win.attributes("-topmost", True)
        self.win.geometry("1x1+-32000+-32000")  # off-screen while we set it up
        self.win.deiconify()
        self.win.update()
        self._affinity_hwnd = None
        self.excluded = False
        self.visible = False

    def _finish_setup(self):
        # call at the end of the subclass __init__, after its tk attributes are set
        self.win.update()
        self._apply_style()
        self.win.withdraw()

    def _apply_style(self):
        """click-through, no taskbar icon, never takes focus, hidden from screenshots"""
        hwnd = user32.GetAncestor(self.win.winfo_id(), 2)  # the real outer window
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        wanted = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if style & wanted != wanted:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | wanted)
        if not self.tk_layered:
            # a layered window with no alpha set is invisible, so always set it
            user32.SetLayeredWindowAttributes(hwnd, 0, self.alpha, LWA_ALPHA)
        if hwnd != self._affinity_hwnd:
            # screenshots skip this window, so we can grab the text under it without hiding it
            self.excluded = bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
            self._affinity_hwnd = hwnd

    def _show(self):
        if not self.visible:
            self.win.deiconify()
            self.visible = True
        self.win.attributes("-topmost", True)
        self._apply_style()

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
            self._apply_style()


class LineOverlay(_Overlay):
    def __init__(self, root):
        super().__init__(root)
        self.label = tk.Label(self.win, borderwidth=0, padx=0, pady=0)
        self.label.pack()
        self._finish_setup()

    def show(self, rgb, box):
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.config(image=photo)
        self.label.image = photo  # keep a reference so it isn't garbage collected
        w, h = box[2] - box[0], box[3] - box[1]
        self.win.geometry(f"{w}x{h}+{box[0]}+{box[1]}")
        self._show()


class _DimPanel(_Overlay):
    def __init__(self, root, alpha):
        super().__init__(root, alpha=alpha)
        self.win.configure(bg="black")
        self._finish_setup()

    def place(self, x, y, w, h):
        if w <= 0 or h <= 0:
            self.hide()
            return
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self._show()


class RulerMask:
    # 4 see-through black panels (above, below, left, right of the line) instead of one window with a
    # hole cut out - same simple trick as the highlight overlay, so it works on every windows version

    def __init__(self, root, screen_w, screen_h, dim):
        self.w, self.h = screen_w, screen_h
        self.panels = [_DimPanel(root, self._alpha(dim)) for _ in range(4)]
        self.excluded = all(p.excluded for p in self.panels)
        self.visible = False

    @staticmethod
    def _alpha(dim):
        return int(max(0.0, min(1.0, dim)) * 255)

    def set_dim(self, dim):
        for p in self.panels:
            p.alpha = self._alpha(dim)
            if p.visible:
                p._apply_style()

    def show(self, box):
        l, t, r, b = (int(v) for v in box)
        top, bottom, left, right = self.panels
        top.place(0, 0, self.w, t)
        bottom.place(0, b, self.w, self.h - b)
        left.place(0, t, l, b - t)
        right.place(r, t, self.w - r, b - t)
        self.visible = True
        self.excluded = all(p.excluded for p in self.panels)

    def hide(self):
        for p in self.panels:
            p.hide()
        self.visible = False

    def suspend(self):
        for p in self.panels:
            p.suspend()

    def resume(self):
        for p in self.panels:
            p.resume()


class DwellRing(_Overlay):
    SIZE = 56

    def __init__(self, root):
        super().__init__(root, tk_layered=True)
        s = self.SIZE
        self.canvas = tk.Canvas(self.win, width=s, height=s, bg=KEY, highlightthickness=0, borderwidth=0)
        self.canvas.pack()
        self.canvas.create_oval(6, 6, s - 6, s - 6, outline="#ffffff", width=6)  # track
        self.arc = self.canvas.create_arc(6, 6, s - 6, s - 6, start=90, extent=0,
                                          style="arc", outline="#ff8c00", width=6)
        self.win.attributes("-transparentcolor", KEY)
        self._finish_setup()

    def show(self, x, y, progress):
        self.canvas.itemconfig(self.arc, extent=-359.9 * min(progress, 1.0))  # clockwise from the top
        s = self.SIZE
        self.win.geometry(f"{s}x{s}+{int(x - s / 2)}+{int(y - s / 2)}")
        self._show()
