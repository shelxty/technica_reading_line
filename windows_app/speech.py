# read aloud: turns a screenshot of a line into text (Windows' built-in OCR) and speaks it
# (Windows' built-in voice). runs on its own thread so the camera loop never waits on it

import asyncio
import queue
import threading

from PIL import Image


class Reader:
    def __init__(self, lang="en", rate=0):
        self.lang = lang
        self.rate = rate
        self.status = ""  # shown in the preview window if something is missing
        self.last_text = ""
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def read_image(self, img):
        # newest request wins: drop anything still waiting
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._q.put(img)

    def say(self, text):
        # short spoken announcement ("zoom 150 percent"). cuts off whatever was being said
        self._q.put(("say", text))

    def stop_speaking(self):
        self._q.put("stop")

    def set_rate(self, rate):
        self.rate = rate
        self._q.put("rate")

    def close(self):
        self._q.put(None)

    # ---------- worker thread ----------

    def _ocr(self, img, loop):
        # OCR struggles with small text, so scale short lines up first
        if img.height < 60:
            f = 60 / img.height
            img = img.resize((int(img.width * f), 60), Image.LANCZOS)
        try:
            import winocr
            result = loop.run_until_complete(winocr.recognize_pil(img, self.lang))
            return " ".join(result.text.split())
        except ImportError:
            pass
        try:
            import pytesseract
            return " ".join(pytesseract.image_to_string(img).split())
        except ImportError:
            self.status = "No OCR: pip install winocr"
            return ""

    def _run(self):
        voice = None
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Rate = self.rate
        except Exception as e:  # noqa: BLE001 - any failure just means no voice
            self.status = "No voice: pip install pywin32"
            print("text-to-speech unavailable:", e)

        SPEAK_ASYNC, PURGE = 1, 2  # don't block, and cut off whatever was being said
        loop = asyncio.new_event_loop()
        while True:
            item = self._q.get()
            if item is None:
                break
            if voice is None:
                continue
            if item == "stop":
                voice.Speak("", SPEAK_ASYNC | PURGE)
                continue
            if item == "rate":
                voice.Rate = self.rate
                continue
            if isinstance(item, tuple):
                voice.Speak(item[1], SPEAK_ASYNC | PURGE)
                continue
            try:
                text = self._ocr(item, loop)
            except Exception as e:  # noqa: BLE001
                self.status = "OCR failed"
                print("OCR failed:", e)
                continue
            self.last_text = text
            if text:
                self.status = ""
                voice.Speak(text, SPEAK_ASYNC | PURGE)
        loop.close()
