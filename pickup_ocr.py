"""
Pickup reader: spots the small "143 ВТОРСЫРЬЁ" notifications Warframe shows
near the bottom-centre of the screen when you pick something up, and turns
them into (resource, amount) events for the tracker.

How it works (read-only, never touches the game process):
  1. Every ~0.6 s take a screenshot of a small strip of the screen where
     those notifications appear (Pillow's ImageGrab - plain screen capture,
     the same thing any screenshot tool does).
  2. Run Tesseract OCR on it (an external program the user installs, with
     the Russian language data shipped in the `tessdata` folder).
  3. Parse "<number> <name>" lines, ignore OCR glitches by requiring the
     same reading in two consecutive frames, and work out how much is NEW
     (the notification lingers for a few seconds and can grow when several
     pickups merge, so we count only the increase).

This is the same capture + OCR technique community tools such as WFInfo use.
The pure logic (parsing / de-duplication) lives in plain functions and
classes so it can be tested without a screen or Tesseract.
"""

import difflib
import io
import os
import re
import shutil
import subprocess
import sys
import threading
import time

# Fraction of the screen to read: (left, top, right, bottom). Chosen from a
# real 1920x1080 screenshot where the stack sat at x~850-1040, y~930-1010.
DEFAULT_REGION = (0.42, 0.78, 0.60, 0.945)
CAPTURE_INTERVAL = 0.6      # seconds between screenshots
ACTIVE_TTL = 3.0            # a notification not seen for this long is "gone"
UPSCALE = 3
WHITE_THRESHOLD = 200       # notification text is near-white

IGNORE = "__ignore__"
MAX_SINGLE_PICKUP = 5000   # larger readings are treated as OCR misreads
MAX_CREDITS_PICKUP = 200000  # credits legitimately come in much bigger chunks

# Names known from real screenshots (normalized, see normalize_name()).
# Anything else is learned from the player the first time it is seen.
DEFAULT_NAME_MAP = {
    "ВТОРСЫРЬЕ": "Salvage",
    "ГЕКСЕНОН": "Hexenon",
    "КРЕДИТЫ": "Credits",
    "ЭНЕРГИЯ": IGNORE,
}

_LATIN_TO_CYR = {
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К",
    "M": "М", "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
}
_LINE_RE = re.compile(r"(?<!\d)(\d{1,6})\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё' ]{3,30})")


def normalize_name(text):
    """Upper-case, unify Latin look-alikes with Cyrillic, drop everything
    except letters. Makes OCR noise like 'BTOPCbIPbE' comparable."""
    text = text.upper().replace("Ё", "Е")
    text = "".join(_LATIN_TO_CYR.get(ch, ch) for ch in text)
    return "".join(ch for ch in text if ch.isalpha())


def match_name(norm, known, cutoff=0.78):
    """Best fuzzy match of `norm` among `known` normalized names, or None."""
    if norm in known:
        return norm
    best, best_ratio = None, cutoff
    for cand in known:
        ratio = difflib.SequenceMatcher(None, norm, cand).ratio()
        if ratio >= best_ratio:
            best, best_ratio = cand, ratio
    return best


def parse_popup_text(text):
    """OCR text -> list of (display_name, normalized_name, amount)."""
    found = []
    for line in text.splitlines():
        m = _LINE_RE.search(line)
        if not m:
            continue
        amount = int(m.group(1))
        display = m.group(2).strip()
        norm = normalize_name(display)
        if len(norm) < 4 or amount <= 0:
            continue
        found.append((display, norm, amount))
    return found


class PickupTracker:
    """Turns noisy per-frame readings into 'how much is new' credits.

    process(items, now) takes [(key, amount), ...] read from one frame and
    returns [(key, credited_amount), ...].

    Rules:
      * A reading only counts once the same (key, amount) shows up in two
        consecutive frames (filters one-off OCR misreads like 348 -> 848).
      * First time a key is seen (or after it vanished for ACTIVE_TTL):
        credit the full amount - a fresh notification.
      * Same key, higher amount while still visible: credit the increase
        (the game merged another pickup into the same notification).
      * Same amount: already counted, nothing.
      * Lower amount: a new notification replaced the old one: credit it.
    """

    def __init__(self, ttl=ACTIVE_TTL):
        self.ttl = ttl
        self._prev_items = set()
        self._active = {}   # key -> (amount, last_seen)

    def process(self, items, now):
        current = set(items)
        confirmed = current & self._prev_items
        self._prev_items = current

        # Forget notifications that have been gone for a while.
        for key in [k for k, (_, seen) in self._active.items() if now - seen > self.ttl]:
            del self._active[key]

        # If one key has several confirmed readings, use the largest.
        best = {}
        for key, amount in confirmed:
            if amount > best.get(key, 0):
                best[key] = amount

        credits = []
        for key, amount in best.items():
            prev = self._active.get(key)
            if prev is None:
                credits.append((key, amount))
            else:
                prev_amount = prev[0]
                if amount > prev_amount:
                    credits.append((key, amount - prev_amount))
                elif amount < prev_amount:
                    credits.append((key, amount))
            self._active[key] = (amount, now)
        return credits


# ----------------------------------------------------------------------
# Tesseract + screen capture (Windows only at runtime)
# ----------------------------------------------------------------------

def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tesseract():
    # A portable copy next to the program wins: Tesseract-OCR\\tesseract.exe
    local = os.path.join(_app_dir(), "Tesseract-OCR", "tesseract.exe")
    if os.path.exists(local):
        return local
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        cand = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
        if os.path.exists(cand):
            return cand
    return None


def find_tessdata():
    """Folder holding rus.traineddata. Checked in this order:
      1. a `tessdata` folder next to the program (lets the player override),
      2. the copy bundled inside the .exe (PyInstaller unpacks it to
         sys._MEIPASS), so a friend only needs the exe + Tesseract,
      3. Tesseract's own tessdata, if Russian was installed with it."""
    candidates = [os.path.join(_app_dir(), "tessdata")]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.append(os.path.join(bundled, "tessdata"))
    exe = find_tesseract()
    if exe:
        candidates.append(os.path.join(os.path.dirname(exe), "tessdata"))
    for folder in candidates:
        if os.path.exists(os.path.join(folder, "rus.traineddata")):
            return folder
    return None


def check_ready():
    """Returns (ok, message_key). message_key is an English UI string."""
    if find_tesseract() is None:
        return False, "Tesseract not found - see README"
    if find_tessdata() is None:
        return False, "Russian OCR data missing (tessdata folder)"
    return True, "OCR ready"


def _screen_size():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return None


def preprocess(image):
    """Keep only near-white pixels as black text on white, enlarged."""
    gray = image.convert("L").point(lambda v: 0 if v > WHITE_THRESHOLD else 255)
    return gray.resize((gray.width * UPSCALE, gray.height * UPSCALE))


def run_ocr(image, tesseract_exe, tessdata_dir):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    cmd = [tesseract_exe, "stdin", "stdout", "--tessdata-dir", tessdata_dir,
           "-l", "rus+eng", "--psm", "6"]
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    proc = subprocess.run(cmd, input=buf.getvalue(), capture_output=True,
                          creationflags=flags, timeout=15)
    return proc.stdout.decode("utf-8", errors="ignore")


class PickupWatcher:
    """Background thread: capture -> OCR -> parse -> de-duplicate.

    on_pickup(display_name, norm_name, amount) is called (from the
    background thread) for every newly-credited pickup, using the display
    text of the first reading of that name. Name -> resource mapping is the
    caller's job.
    """

    def __init__(self, on_pickup, on_status=None, region=DEFAULT_REGION,
                 debug=False, known_names=None):
        self.on_pickup = on_pickup
        self.on_status = on_status or (lambda msg: None)
        self.region = region
        self.debug = debug
        self.known = set(known_names or [])
        self._tracker = PickupTracker()
        self._stop = threading.Event()
        self._thread = None
        self._debug_path = os.path.join(_app_dir(), "pickup_debug.log")
        self._crop_path = os.path.join(_app_dir(), "pickup_last_crop.png")
        self._display = {}

    def add_known_name(self, norm):
        self.known.add(norm)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _log(self, line):
        if not self.debug:
            return
        try:
            if os.path.exists(self._debug_path) and os.path.getsize(self._debug_path) > 2_000_000:
                os.replace(self._debug_path, self._debug_path + ".old")
            with open(self._debug_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except OSError:
            pass

    def _run(self):
        ok, msg = check_ready()
        self.on_status(msg)
        self._log(f"check_ready ok={ok} msg={msg!r} tesseract={find_tesseract()!r} tessdata={find_tessdata()!r}")
        if not ok:
            return
        try:
            from PIL import ImageGrab
        except ImportError:
            self.on_status("Pillow missing - run: pip install Pillow")
            return
        exe, tessdata = find_tesseract(), find_tessdata()
        size = _screen_size()
        if size is None:
            self.on_status("Screen capture only works on Windows")
            return
        w, h = size
        l, t, r, b = self.region
        bbox = (int(l * w), int(t * h), int(r * w), int(b * h))
        self._log(f"start screen={w}x{h} bbox={bbox}")

        while not self._stop.is_set():
            started = time.time()
            try:
                shot = ImageGrab.grab(bbox=bbox)
                if self.debug:
                    try:
                        shot.save(self._crop_path)
                    except OSError:
                        pass
                text = run_ocr(preprocess(shot), exe, tessdata)
                parsed = parse_popup_text(text)

                items = []
                for display, norm, amount in parsed:
                    key = match_name(norm, self.known | set(self._display)) or norm
                    self._display.setdefault(key, display)
                    items.append((key, amount))
                credits = self._tracker.process(items, time.time())
                self._log(f"raw={text.strip()!r} items={items} credits={credits}")
                for key, amount in credits:
                    self.on_pickup(self._display.get(key, key), key, amount)
            except Exception as exc:   # never let the thread die silently
                self._log(f"error: {exc!r}")
            wait = CAPTURE_INTERVAL - (time.time() - started)
            if wait > 0:
                self._stop.wait(wait)
