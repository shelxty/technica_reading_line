# the highlight: a borderless, click-through window that sits exactly on top of the line you're
# pointing at and shows it as black text on yellow.
# this is the same trick as the original hand_cursor1.py: the tk window itself is the overlay

import ctypes
import tkinter as tk

from PIL import Image, ImageTk

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20  # clicks pass through to whatever is underneath
WS_EX_TOOLWINDOW = 0x80  # no taskbar icon
LWA_ALPHA = 0x2


class HighlightOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Reading Line highlight")
        self.root.overrideredirect(True)  # no title bar
        self.root.attributes("-topmost", True)
        self.root.withdraw()
        self.label = tk.Label(self.root, borderwidth=0, padx=0, pady=0)
        self.label.pack()
        self.root.update()
        hwnd = user32.GetAncestor(self.root.winfo_id(), 2)  # native window handle
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        self.visible = False

    def show(self, rgb, box):
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.label.config(image=photo)
        self.label.image = photo  # keep a reference so it isn't garbage collected
        w, h = box[2] - box[0], box[3] - box[1]
        self.root.geometry(f"{w}x{h}+{box[0]}+{box[1]}")
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.visible = True

    def hide(self):
        if self.visible:
            self.root.withdraw()
            self.root.update()  # make windows actually remove it
            self.visible = False

    def update(self):
        self.root.update()

    def destroy(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
