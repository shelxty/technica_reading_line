# finds the clickable thing (link, button, tab...) under the cursor, using Windows UI Automation -
# the same accessibility info screen readers use. browsers (chrome, edge), file explorer, office and
# most windows apps provide it. that way the highlight can wrap just that link / button / tab
# instead of the whole line of text

import os
from collections import namedtuple

# box = (left, top, right, bottom) on screen, kind = "link", "button"..., name = its label
Component = namedtuple("Component", "box kind name")

# UI Automation control type -> what we call it
KINDS = {
    "HyperlinkControl": "link",
    "ButtonControl": "button",
    "SplitButtonControl": "button",
    "TabItemControl": "tab",
    "MenuItemControl": "menu item",
    "CheckBoxControl": "checkbox",
    "RadioButtonControl": "radio button",
    "ComboBoxControl": "dropdown",
    "EditControl": "text field",
    "TreeItemControl": "tree item",
    "SliderControl": "slider",
    "SpinnerControl": "spinner",
}

try:
    import uiautomation as auto
except ImportError:  # not installed, or not on windows: we just highlight lines
    auto = None


def available():
    return auto is not None


def is_component_box(box, x, y, screen_w, screen_h):
    """is this a sensible thing to highlight? (not tiny, actually under the cursor, and not
    something huge like a whole card or a big text area - those get line-by-line highlighting)"""
    left, top, right, bottom = box
    if right - left < 4 or bottom - top < 4:
        return False
    if not (left <= x <= right and top <= y <= bottom):
        return False
    return (right - left) * (bottom - top) <= 0.15 * screen_w * screen_h


def component_at(x, y, screen_w, screen_h, levels=4):
    """the link / button / tab... under (x, y), or None if it's plain text (or anything else)"""
    if auto is None:
        return None
    try:
        control = auto.ControlFromPoint(int(x), int(y))
        if control is not None and getattr(control, "ProcessId", None) == os.getpid():
            return None  # that's our own highlight window, not the app underneath
        # the thing right under the cursor is often the text *inside* a link or button, so look a few
        # levels up for the link / button itself
        for _ in range(levels):
            if control is None:
                return None
            kind = KINDS.get(control.ControlTypeName)
            if kind:
                r = control.BoundingRectangle
                box = (r.left, r.top, r.right, r.bottom)
                if not is_component_box(box, x, y, screen_w, screen_h):
                    return None
                return Component(box, kind, " ".join((control.Name or "").split()))
            control = control.GetParentControl()
    except Exception:  # noqa: BLE001 - apps can vanish or refuse mid-lookup; just fall back to lines
        return None
    return None
