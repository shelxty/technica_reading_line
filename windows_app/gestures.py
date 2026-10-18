# hand pose checks + small helpers. no windows stuff in here, so it can be tested anywhere.
# `hand` is the list of 21 mediapipe landmarks (each has .x and .y from 0 to 1)
#
# landmark numbers: 0 wrist, 4 thumb tip, 8 index tip, 12 middle tip, 16 ring tip, 20 pinky tip
# (the joint 2 below each tip is the "pip": 6, 10, 14, 18)

import math

FINGERS = ((8, 6), (12, 10), (16, 14), (20, 18))  # (tip, pip) for index, middle, ring, pinky


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def palm_size(hand):
    return dist(hand[0], hand[9])  # wrist to middle finger base


def pinch_ratio(hand):
    # thumb-index gap divided by palm size, so moving closer/further from the camera doesn't matter
    palm = palm_size(hand)
    return dist(hand[4], hand[8]) / palm if palm > 0 else 1.0


def finger_up(hand, tip, pip):
    return hand[tip].y < hand[pip].y


def finger_folded(hand, tip, pip):
    # works no matter which way the hand is turned: a curled finger's tip is closer to the wrist than its middle joint
    return dist(hand[tip], hand[0]) < dist(hand[pip], hand[0])


def open_palm_pose(hand):
    # all four fingers up = scroll mode (thumb can be anywhere)
    return all(finger_up(hand, tip, pip) for tip, pip in FINGERS)


def fist_pose(hand):
    return all(finger_folded(hand, tip, pip) for tip, pip in FINGERS)


def thumb_rising(hand):
    # fingers curled and the thumb starting to point up: on its way to a thumbs-up.
    # (after a real pinch the index finger opens up again, so this doesn't match)
    return fist_pose(hand) and hand[4].y < hand[3].y < hand[2].y


def pose_name(hand):
    # for the preview window, so you can see what the app thinks your hand is doing
    if pinch_ratio(hand) < 0.3:
        return "pinch"
    if open_palm_pose(hand):
        return "open palm"
    if thumbs_up_pose(hand):
        return "thumbs up"
    if fist_pose(hand):
        return "fist"
    if finger_up(hand, 8, 6):
        return "pointing"
    return "-"


def thumbs_up_pose(hand):
    # fist with the thumb pointing up = read this line aloud
    folded = all(finger_folded(hand, tip, pip) for tip, pip in FINGERS)
    thumb_up = (hand[4].y < hand[3].y < hand[2].y
                and hand[4].y < hand[5].y - 0.3 * palm_size(hand))
    return folded and thumb_up


def index_extension(hand):
    # how stretched out the index finger is (tip to knuckle, divided by palm size).
    # it drops as soon as you start curling the finger, e.g. on the way to a thumbs-up
    palm = palm_size(hand)
    return dist(hand[8], hand[5]) / palm if palm > 0 else 0.0


def scroll_velocity(offset, deadzone, speed, max_speed=None):
    # joystick-style: the further your palm is from where it started, the faster it scrolls.
    # offset > 0 = hand moved up = scroll up. returns mouse-wheel notches per second
    if abs(offset) <= deadzone:
        return 0.0
    v = (abs(offset) - deadzone) * speed
    if max_speed is not None:
        v = min(v, max_speed)
    return math.copysign(v, offset)


class OneEuro:
    """One Euro filter (Casiez et al. 2012): smooths a noisy value without making it laggy.
    when the value barely moves it smooths a lot (no jitter), when it moves fast it smooths
    a little (no lag). min_cutoff: lower = steadier when still. beta: higher = less lag when moving"""

    def __init__(self, min_cutoff=0.5, beta=0.003, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self.x = None
        self.dx = 0.0
        self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.x is None:
            self.x, self.t = x, t
            return x
        dt = max(t - self.t, 1e-3)
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * (x - self.x) / dt + (1 - a_d) * self.dx  # smoothed speed
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        a = self._alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        self.t = t
        return self.x


# the zoom steps chrome and edge use for ctrl + mouse wheel
BROWSER_ZOOM_LEVELS = [25, 33, 50, 67, 75, 80, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500]


def zoom_levels(lowest, highest):
    return [z for z in BROWSER_ZOOM_LEVELS if lowest <= z <= highest]
