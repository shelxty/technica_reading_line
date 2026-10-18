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


def two_finger_pose(hand):
    # index + middle up, ring + pinky down
    return (finger_up(hand, 8, 6) and finger_up(hand, 12, 10)
            and not finger_up(hand, 16, 14) and not finger_up(hand, 20, 18))


def open_palm_pose(hand):
    # all four fingers up and the thumb sticking out = scroll mode
    fingers = all(finger_up(hand, tip, pip) for tip, pip in FINGERS)
    thumb_out = dist(hand[4], hand[5]) > 0.5 * palm_size(hand)
    return fingers and thumb_out


def thumbs_up_pose(hand):
    # fist with the thumb pointing up = read this line aloud
    folded = all(finger_folded(hand, tip, pip) for tip, pip in FINGERS)
    thumb_up = (hand[4].y < hand[3].y < hand[2].y
                and hand[4].y < hand[5].y - 0.3 * palm_size(hand))
    return folded and thumb_up


def scroll_velocity(offset, deadzone, speed):
    # joystick-style: the further your palm is from where it started, the faster it scrolls.
    # offset > 0 = hand moved up = scroll up. returns wheel units per second
    if abs(offset) <= deadzone:
        return 0.0
    return math.copysign((abs(offset) - deadzone) * speed, offset)


class Dwell:
    # "hold still to click". update() every frame with the cursor position;
    # it returns (progress 0..1, fire). after it fires you have to move away before it can fire again

    def __init__(self, radius, hold):
        self.radius = radius
        self.hold = hold
        self.reset()

    def reset(self):
        self.anchor = None
        self.start = 0.0
        self.armed = True

    def update(self, x, y, now):
        if self.anchor is None or math.hypot(x - self.anchor[0], y - self.anchor[1]) > self.radius:
            self.anchor = (x, y)
            self.start = now
            self.armed = True
            return 0.0, False
        if not self.armed:
            return 0.0, False
        progress = (now - self.start) / self.hold
        if progress >= 1:
            self.armed = False
            return 1.0, True
        return progress, False
