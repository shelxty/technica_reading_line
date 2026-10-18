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

SCROLL_GAIN = 8000 # scrolls + closing/waving; this converts hand movement per frame into a scroll amount 
# ^ 120 = one mouse-wheel notch, so higher value means faster scrolling
SCROLL_DEADZONE = 0.004 # ignore vertical movement smaller than this frame so that not everything triggers scrolling
WAVE_WINDOW = 1.5 # how many seconds of hand movement history that is examined when ur looking for a wave
WAVE_AMP = 0.07 # this is how far the hand must swing (denoted as a fraction of the screen width) in a direction to count as a swing 
WAVE_SWINGS = 4 # num of swings to count as a wave. one swing is right to left, or left to right. thus, this is two "full waves" ifykwim
WAKE_COOLDOWN = 1.5 # waving should turn on/off a sleep mode, which has a cooldown of 1.5 seconds 



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

def four_finger_pose(hand): 
    return (finger_up(hand, 8, 6) 
        and finger_up(hand, 12, 10)
        and finger_up(hand, 16, 14)
        and finger_up(hand, 20, 18))
        # see how this four finger pose differs from the two finger pose by using "and" and not "and not"? woahhh that's the difference isnt it so cool ikr ur so cool, reader <3   

def is_wave(samples): 
    if len(samples) < 2: # if not enough data, no wave
        return False # balanced, as all things should be 
    xs = [x for _, x in samples] # keep only horizontal positions
    last = xs[0]
    direction = 0 # 0 = unknown, 1 = moving right, -1 = moving left
    swings = 0 # the number of swings only counts completd direction changes

    for x in xs[1:]:
        if direction != 1 and x - last > WAVE_AMP: # moved right by WAVE_AMP from last extreme
            direction = 1 # heading right 
            swings += 1
            last = x  # reset extreme to here
        elif direction != -1 and last - x > WAVE_AMP: 
            direction = -1 # heading left aaaaaaaaaaaaaaaaaaaaaaaa
            swings += 1 
            last = x 
        elif (direction == 1 and x > last) or (direction == -1 and x < last): # still traveling in same direction 
            last = x # then extend the extreme slightly so that the small wobbles dont count in the tracking alksd;jfa;sldfja;lsdfkj
    return swings >= WAVE_SWINGS # if there were enough alternating swings, a wave happened!!!!!!!! woah!!!!!!!!!!!!
# reminds me of all the times i could barely wave to someone because of my social anxiety making me think no one was waving to me when they were.... oh well! we improve 


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
hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2) # get native window handle
style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) # get window style

ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80) # add click-through + no taskbar icon so that clicks can pass through to whats underneath OR ELSE YK OTHERWISE WE CANT DO ANYTHING WHILE ANYTHING'S HIGHLIGHTED
ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x2) 

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

scroll_prev_y = None # palm height on the previous frame; if this is set to None, it means that we're not actively scrolling
scroll_prev_x = None # i implore you to guess what this could possibly mean
wave_samples = deque() # recent (time, x) palm positions that are used to detect a wave 

asleep = False 
last_toggle = 0.0 # time of last sleep. this is zero because i've never slept in my life!


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
            hands_found = result.hand_landmarks 
            if asleep: 
                now_s = time.time() # current time
                if hands_found: 
                    h0 = hands_found[0] # if hands found, look at its 21 landmarks
                    draw_landmarks(frame, h0) # keep drawing skeleton so that it's evident the program is still tracking everything
                    if four_finger_pose(h0): # when asleep, nothing works except for waving again to reactivate everything
                        wave_samples.append((now_s, h0[9].x)) # record palm x position w/ timestamp 
                        while wave_samples and now_s - wave_samples[0][0] > WAVE_WINDOW: 
                            wave_samples.popleft() # removeo ldest sample
                        if is_wave(wave_samples) and now_s - last_toggle > WAKE_COOLDOWN:
                            asleep = False # omg. ur awake. you've been in a coma for the last 20 years. please, please, let me start from the beginning now...
                            last_toggle = now_s 
                            wave_samples.clear() # discrd wave so no re-triggering
                    else: 
                        wave_samples.clear() # wave must happen in the open hand pose 
                else: 
                    wave_samples.clear() # and discrad any partial wave
                hands_found = []

            # if result.hand_landmarks: # only act if hand = detected 
            if hands_found:
                hand = result.hand_landmarks[0]
                draw_landmarks(frame, hand) #self-explanatory
                now = time.time() # what is the time.time now??
                ratio = pinch_ratio(hand) # how closed ur hand is. how pinchy ur doing yes
                four_pose = four_finger_pose(hand) 

                if not pinching and not four_pose: # if ur not pinching AS WELL AS not actively scrolling, this controls cursor movement 
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
                    # status = "No hand"

                if not pinching and four_pose: # if ur hand is open and it's not mid pinch
                    hide_overlay()
                    px, py = hand[9].x, hand[9].y # the middle finger knuckle is a steady palm position
                    status = "Four fingers: scroll" # print this
                    if scroll_prev_y is not None: # when u have a previous frame to compare to... then 
                        d = scroll_prev_y - py # positive = hand moved up 
                        dx = px - scroll_prev_x # horizontal movement
                        if abs(d) > SCROLL_DEADZONE and abs(d) > abs(dx): # when there's more vertical movement than horizontal movement (we cant have waving scroll stuff LOL)
                            pyautogui.scroll(int(d * SCROLL_GAIN))
                            status = "Scroll up" if d > 0 else "Scroll down"
                    scroll_prev_y = py # remember frame's height 
                    scroll_prev_x = px # and also remember frame's horizontal position for next time
                    wave_samples.append((now, px))

                    while wave_samples and now - wave_samples[0][0] > WAVE_WINDOW: # drop samples older than the window 
                        wave_samples.popleft()
                    if is_wave(wave_samples): 
                        # status = "Wave: closing" # leave main loop
                        # break 
                        if is_wave(wave_samples) and now - last_toggle > WAKE_COOLDOWN: 
                            asleep = True 
                            last_toggle = now # start cooldown of 1.5s
                            wave_samples.clear() 
                            scroll_prev_y = None # cancel any scroll that's in progress
                            scroll_prev_x = None 
                            two_start = None 
                            two_fired = False 
                            hide_overlay() 
                            status = "Sleeping"
                else: 
                    scroll_prev_y = None 
                    scroll_prev_x = None 
                    wave_samples.clear() 



            else: 
                # status = "No hand"
                status = "Sleeping (wave to wake)" if asleep else "No hand"
                two_start = None 
                two_fired = False 

                scroll_prev_y = None 
                scroll_prev_x = None 
                wave_samples.clear() 


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
                        







