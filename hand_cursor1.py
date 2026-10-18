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

import ctypes 
import tkinter as tk 
import numpy as np 
from PIL import Image, ImageGrab, ImageTk # imagegrab = screenshots, imagetk = show imgs in tkinter

ctypes.windll.shcore.SetProcessDpiAwareness(2) # this makes the cursor coords match the screen res on high-dpi monitors

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

# for the settings for highlighting + high contrast stuffs
REGION_W = 900 # width of screenshot strip 
SEARCH_H = 40 # how many pixels above or below to search for the line of text (Relative to fingerprint ofc)
SNAP = 12 # snap to text within this many pixels if the fingertip is in a gap between lines
INK_DIFF = 40 # how diff a pixel must be from the bg to count as text
PAD = 3 # extra pixels of padding around highlighted line 
BG_COLOR = (255, 255, 0) # new high contrast bg color (yellow)
FG_COLOR = (0, 0, 0) # new high contrast text color (black)

TWO_FINGER_HOLD = 0.8 


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


def finger_up(hand, tip, pip): 
    return hand[tip].y < hand[pip].y

def two_finger_pose(hand): # this is only for index + middle finger, not for index + ring or pinky or anything else ykykyk
    return (finger_up(hand, 8, 6) 
        and finger_up(hand, 12, 10)
        and not finger_up(hand, 16, 14)
        and not finger_up(hand, 20, 18))


def find_line(cx, cy): # line detection 
    x0 = max(0, int(cx - REGION_W // 2))
    x1 = min(SCREEN_W, int(cx + REGION_W // 2))
    y0 = max(0, int(cy - SEARCH_H))
    y1 = min(SCREEN_H, int(cy + SEARCH_H))

    shot = ImageGrab.grab(bbox = (x0, y0, x1, y1), all_screens = True)
    gray = np.array(shot.convert("L")).astype(np.int16) # convert to grayscale and int16 for diffing
    bg = np.median(gray) # get the median pixel value to use as the background color
    ink = np.abs(gray - bg) > INK_DIFF # this is a boolean array where True = text and False = background
    row_has_ink = ink.sum(axis = 1) >= 2
    ry = int(cy - y0)
    ry = min(max(ry, 0), len(row_has_ink) - 1) # keep it inside the strip's bounds 

    if not row_has_ink[ry]: 
        for d in range(1, SNAP + 1): # keep fingertip inside strip's bounds
            if ry - d >= 0 and row_has_ink[ry - d]: 
                ry -= d # search outward for nearest text row if fingertip is between text rows. then, if u find the text above, then yk you do what you gotta do!
                break 
            if ry + d < len(row_has_ink) and row_has_ink[ry + d]: # if u found text below!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                ry += d 
                break
        else: 
            return None # nothing to highlight if loop finished without finding any text nearby


    top = ry # start line at this row and grow upwards
    gap = 0 

    while top > 0 and gap <= 2: # grow up until 3+ empty rows in a row
        top -= 1
        gap = 0 if row_has_ink[top] else gap + 1 # if the row has text, reset gap to 0, otherwise increment gap

    top += gap # trim empty rows we stepped past
    bot = ry # grow downward the same way
    gap = 0 

    while bot < len(row_has_ink) - 1 and gap <= 2:
        bot += 1
        gap = 0 if row_has_ink[bot] else gap + 1
    bot -= gap # trim empty rows we stepped past
    cols = np.where(ink[top:bot + 1])[1] # get the x coords of all the text pixels in the line
    if len(cols) == 0: 
        return None # if there's no text in the line, return None
    left = max(0, x0 + int(cols.min()) - PAD) # line's left edge in screen coords
    right = min(SCREEN_W, x0 + int(cols.max()) + PAD) # line's right edge
    return left, max(0, y0 + top - PAD), right, min(SCREEN_H, y0 + bot + PAD) # top & bottom is apdded 

def high_contrast(box): # makes the black on yellow img of the highlighted line
    shot = ImageGrab.grab(bbox = box, all_screens = True) # screenshot of the line 
    gray = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2GRAY) # convert to grayscale
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU) # threshold to binary using Otsu's method; splits pixels into light/dark groups automatically
    if (mask > 0).mean() < 0.5: # txt = smaller group so make mask true for text
        text = mask > 0 
    else: 
        text = mask == 0 
    out = np.zeros((*gray.shape, 3), dtype = np.uint8) # blank rgb image the size of the line
    out[:] = BG_COLOR # fill with bg color
    out[text] = FG_COLOR # fill text pixels with fg color
    return out 

root = tk.Tk() # make tkinter window
root.overrideredirect(True) # remove title bar
root.attributes("-topmost", True) # keep window on top
root.withdraw() 
label = tk.Label(root, borderwidth = 0, padx = 0, pady = 0) # label to display the line img
label.pack() 
root.update()
hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) # get native window handle
style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) # get window style

ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80) # add click-through + no taskbar icon so that clicks can pass through to whats underneath OR ELSE YK OTHERWISE WE CANT DO ANYTHING WHILE ANYTHING'S HIGHLIGHTED

line_box = None # screen rectangle; none means there's no hihglight currently 

def hide_overlay(): # hides highlight 
    global line_box 
    line_box = None # forget current line 
    root.withdraw() # hide window

def show_overlay(box): 
    global line_box
    img = Image.fromarray(high_contrast(box))
    photo = ImageTk.PhotoImage(img) # convert to tkinter image
    label.config(image = photo) # set the label to the new image
    label.image = photo # keep a reference to the image so it doesn't get garbage collected
    w, h = box[2] - box[0], box[3] - box[1] # width and height of the line
    root.geometry(f"{w}x{h}+{box[0]}+{box[1]}") # set the window size and position to match the line
    root.deiconify() # show the window
    root.attributes("-topmost", True) # keep it on top
    line_box = box

def update_highlight(cx, cy): 
    if line_box and line_box[0] <= cx <= line_box[2] and line_box[1] <= cy <= line_box[3]: 
        return # if the cursor is still inside the current highlight, do nothing
    hide_overlay() # hide so screenshot doesnt caputerue
    root.update() # make windows actually remove
    time.sleep(0.03) # this is how much time i slept this hackathon 

    box = find_line(cx, cy) # find line under fingertip
    if box: # if found a line
        show_overlay(box) # then highlight! so efficient



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

highlight_on = False # highlight changes to start off; turn it on with ur pose 
two_start = None 
two_fired = False

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
                    if highlight_on and zoom_level == 0: # highlight only if enabled and magnifier is off
                        update_highlight(sx, sy) # highlight line under smoothed fingertip
                    elif zoom_level > 0: # hide highlight while zoomed if screenshots dont match magnified view
                        hide_overlay() # 


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
                        hide_overlay() # remove highlight before screen is magnified
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

                if not pinching and two_finger_pose(hand):
                    if two_start is None: 
                        two_start = now 
                    elif not two_fired and (now - two_start) >= TWO_FINGER_HOLD: 
                        highlight_on = not highlight_on 
                        two_fired = True 
                        if not highlight_on: 
                            hide_overlay() 
                    if not two_fired: 
                        status = f"Hold... {int((now - two_start) / TWO_FINGER_HOLD * 100)}%"
                    else: 
                        status = "Highlight ON" if highlight_on else "Highlight OFF"
                else:
                    two_start = None 
                    two_fired = False
                    status = "No hand"


                root.update() # lets tkinter process events & redraw overlay each frame
                cv2.putText(frame, status + (" | HL on" if highlight_on else " | HL off "), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2) # display the status on the preview window in cyan, size 0.8
                cv2.imshow(WINDOW, frame) # show the webcam feed with the skeleton and status text

                key = cv2.waitKey(1) & 0xFF # process window events and get the key pressed
                if key in (ord('q'), 27): # if 'q' or ESC is pressed, exit the loop
                    break
                # if key == ord("h"): # toggling h toggles highlight feature; flip setting if turning it off and remove overlays and visible highlights
                #     highlight_on = not highlight_on 
                #     if not highlight_on: 
                #         hide_overlay()
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break # if u click the "X" on the window then it closes too (woah! really?? no idea!!)

finally:
    if zoom_level > 0: 
        pyautogui.hotkey("win", "esc") # if the magnifier is still open, close it
    cap.release() # free webcam !!!! ur free now!!!!!!
    cv2.destroyAllWindows() # close windows!!!!!!!!1

    try: # close overlay window on exit and destroy tkinter window
        root.destroy()
    except tk.TclError: # ignore errors if already gone 
        pass

    for _ in range(5): 
        cv2.waitKey(1) # wait a bit to make sure the window is closed before the script ends because errors errors errorcodezero (ref???)
                        







