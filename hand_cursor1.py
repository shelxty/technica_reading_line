import time # timestamps 
import math 
import urllib.request # for downloading the model
import os 
from collections import deque 

import cv2 # this is openCV
import pyautogui # for controlling the mouse

import mediapipe as mp 
from mediapipe.tasks import python as mp_python 
from mediapipe.tasks.python import vision

# section 1 ish idk how to format this properly
# downloading the model
MODEL_PATH = "hand_landmarker.task"
URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
       "hand_landmarker/float16/1/hand_landmarker.task")

if not os.path.exists(MODEL_PATH):
    print("Downloading the model...")
    urllib.request.urlretrieve(URL, MODEL_PATH)
    print("Model downloaded.")


# these are the settings that are tunable 
MARGIN = 0.15 # this ignores the outer 15% of the camera frame so u only get the 15-85%, which allows u to reach the edges
SMOOTH = 0.8 # cursor smoothing. higher = steadier but laggier, and lower = more jittery
PINCH_ENTER = 0.25 # pinch is counted as "closed" when thumb-index gap is below this fraction of palm size 
PINCH_EXIT = 0.4 # opposite of above yk
HOLD_TIME = 0.4 # time to hold for zooming instead of clicking
ZOOM_STEP = 0.06 
MAX_ZOOM = 5 
LOOKBACK = 6 # use cursor position from this many frames ago

pyautogui.PAUSE = 0 # usually pyautogui has a 0.1s delay after every action but this eliminates that
SCREEN_W, SCREEN_H = pyautogui.size() # get the screen res in pixels

# a new part!
# the hand skeleton (woah scary)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), # thumb
    (0, 5), (5, 6), (6, 7), (7, 8), # index finger
    (5, 9), (9, 10), (10, 11), (11, 12), # middle finger
    (9, 13), (13, 14), (14, 15), (15, 16), # ring finger
    (13, 17), (17, 18), (18, 19), (19, 20), # pinky
    (0, 17), # edge of the palm
]

def draw_landmarks(frame, hand): # draws skeleton on preview img
    h, w = frame.shape[:2] 
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand] # converts normalized (0-1) coords to pixel coords
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 255, 0), 2) # this draws a green line for every connected pair of fingers
    for p in pts: 
        cv2.circle(frame, p, 4, (0, 0, 255), -1) # red dot for every finger joint


# helper funcs 
def to_screen(lm): 
    nx = (lm.x - MARGIN) / (1 - 2 * MARGIN) # this is the normalized x coord of the finger, ignoring the outer 15% of the camera frame
    ny = (lm.y - MARGIN) / (1 - 2 * MARGIN) # same for y
    nx = max(0, min(1, nx)) # clamp to [0, 1]
    ny = max(0, min(1, ny)) 
    return nx * SCREEN_W, ny * SCREEN_H # convert to screen coords in pixels

def pinch_ratio(hand): 
    gap = math.hypot(hand[4].x - hand[8].x, 
                     hand[4].y - hand[8].y) # distance between thumb tip and index tip using x and y diffs
    palm_size = math.hypot(hand[0].x - hand[9].x, 
                            hand[0].y - hand[9].y) # distance between wrist and middle finger base
    return gap / palm_size if palm_size > 0 else 1.0 # divide by palm size means that moving further or closer to the screen doesn't matter 


# landmarker stuf
options = vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH), # this is the model we downloaded
    running_mode = vision.RunningMode.VIDEO, # tracks hands across frames
    num_hands = 1, # only track one hand
    min_hand_detection_confidence = 0.5, # how confident the model has to be to detect a hand
    min_hand_presence_confidence = 0.5, # how confident the model has to be to say that a hand is present
    min_tracking_confidence = 0.5, # how confident the model has to be to track a hand
)

# state variables 
sx, sy = SCREEN_W / 2, SCREEN_H / 2 # cursor position
history = deque(maxlen = LOOKBACK) # stores the last few cursor positions for smoothing
pinching = False # state to store if a pinch is currently being held 
pinch_start = 0.0 # time when last pinch started
zoom_mode = False 
anchor_y = 0.0 
zoom_level = 0 
frozen = (sx sy) # cursor position when zooming started
status = "Move your hand"

cap = cv2.VideoCapture(0) # open the webcam
start = time.time() # timestamp for FPS calculation for MediaPipe's timestamps
WINDOW = "Hand_Cursor" # name of the window that will show the webcam feed (preview window)

try: 
    with vision.HandLandmarker.create_from_options(options) as landmarker: # create + auto-close model 
        while True: 
            ret, frame = cap.read() # grab frame from webcam
            if not ret:  
                break # if there's no frame, there must be a camera problem, so we break
            frame = cv2.flip(frame, 1) # mirror img so that moving rihgt moves the cursor right too
            