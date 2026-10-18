""" 

before running, in the terminal, run

pip install opencv-python mediapipe numpy pyautogui

and then, you can just run 
python hand_cursor1.py

in the terminal again obv 

"""

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
frozen = (sx, sy) # cursor position when zooming started
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
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # convert to RGB for MediaPipe
            # ^ this is because opencv uses bgr but mediapipe uses rgb 
            mp_image = mp.Image(image_format = mp.ImageFormat.SRGB, data=rgb) # convert to mediapipe image format

            ts = int((time.time() - start) * 1000) # timestamp in milliseconds
            result = landmarker.detect_for_video(mp_image, ts) # run the model on the frame

            if result.hand_landmarks: # only act if hand = detected 
                hand = result.hand_landmarks[0]
                draw_landmarks(frame, hand) #self-explanatory
                now = time.time() # what is the time.time now??
                ratio = pinch_ratio(hand) # how closed ur hand is. how pinchy ur doing yes

                if not pinching: # if ur not pinching, this controls cursor movement 
                    tx, ty = to_screen(hand[8]) # get the screen coords of the index finger tip
                    sx = sx * SMOOTH + tx * (1 - SMOOTH) 
                    sy = sy * SMOOTH + ty * (1 - SMOOTH) 
                    history.append((sx, sy)) # add the new cursor position to the history for smoothing
                    pyautogui.moveTo(
                        min(max(sx, 1), SCREEN_W - 2), # keep 1 px away from the edges to prevent failsafe from activating
                        min(max(sy, 1), SCREEN_H - 2)
                    )
                    status = "Pointing"

                if not pinching and ratio < PINCH_ENTER: # if ur pinch just started!
                    pinching = True 
                    pinch_start = now # note the time it began
                    zoom_mode = False 
                    # closing ur fingers = fingertip drifts, so you need to use the position from a few frames before to make it accurate

                    frozen = history[0] if history else (sx, sy)

                    pyautogui.moveTo(
                        min(max(frozen[0], 1), SCREEN_W - 2),
                        min(max(frozen[1], 1), SCREEN_H - 2)) # snap mouse back

                    status = "Pinch..."

                elif pinching and not zoom_mode and (now - pinch_start) > HOLD_TIME: # if ur pinch has been held for long enough, enter zoom mode
                    zoom_mode = True 
                    anchor_y = hand[8].y # the y coord of the index finger tip when zooming started
                    status = "Zoom: hand up - in, down = out"

                if pinching and zoom_mode: 
                    dy = anchor_y - hand[8].y # how far the finger has moved up or down since zooming started
                    if dy > ZOOM_STEP and zoom_level < MAX_ZOOM: # if the finger has moved up enough, zoom in
                        pyautogui.hotkey("win", "=")
                        zoom_level += 1
                        anchor_y = hand[8].y # reset reference so each step = new movement
                    elif dy < -ZOOM_STEP and zoom_level > 0: 
                        if zoom_level == 1: 
                            pyautogui.hotkey("win", "esc") # step goes back to normal size so we close the magnifier entirely
                        else: 
                            pyautogui.hotkey("win", "-") # otherwise, just zoom out by one step 
                        zoom_level -= 1
                        anchor_y = hand[8].y # reset reference so each step = new movement

                if pinching and ratio > PINCH_EXIT: # this is for when the pinch is released 
                    pinching = False 
                    if not zoom_mode: 
                        pyautogui.click() # if it was released before the hold time, it was a quick pinch which counts as a click instead
                        status = "CLICK"
                    else: 
                        status = "Zoom set" # zoom gesture ended so there's no click
                    history.clear() 
                else: 
                    status = "No hand"

                cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2) # display the status on the preview window in cyan, size 0.8
                cv2.imshow(WINDOW, frame) # show the webcam feed with the skeleton and status text

                key = cv2.waitKey(1) & 0xFF # process window events and get the key pressed
                if key in (ord('q'), 27): # if 'q' or ESC is pressed, exit the loop
                    break
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break # if u click the "X" on the window then it closes too (woah! really?? no idea!!)

finally:
    if zoom_level > 0: 
        pyautogui.hotkey("win", "esc") # if the magnifier is still open, close it
    cap.release() # free webcam !!!! ur free now!!!!!!
    cv2.destroyAllWindows() # close windows!!!!!!!!1
    for _ in range(5): 
        cv2.waitKey(1) # wait a bit to make sure the window is closed before the script ends because errors errors errorcodezero (ref???)
                        







