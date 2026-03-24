import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageGrab
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions
from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
import urllib.request
from collections import deque
import datetime

os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

# ─── RANGLAR ──────────────────────────────────────────
BG      = "#050810"
PANEL   = "#0a0f1e"
BORDER  = "#1a2540"
ACCENT  = "#00f5c4"
ACCENT2 = "#ff4d6d"
ACCENT3 = "#6c63ff"
DIM     = "#3a4a6a"
TEXT    = "#c8d8f0"
VOL_C   = "#ffaa00"
SHOT_C  = "#00ccff"

# ─── EKRAN O'LCHAMLARI ────────────────────────────────
def get_monitors():
    try:
        out = subprocess.check_output(
            "xrandr | grep ' connected' | awk '{print $1}'",
            shell=True).decode().strip().split('\n')
        monitors = []
        for mon in out:
            res = subprocess.check_output(
                f"xrandr | grep -A1 '{mon} connected' | grep -o '[0-9]*x[0-9]*+[0-9]*+[0-9]*' | head -1",
                shell=True).decode().strip()
            if res:
                parts = res.replace('x', '+').split('+')
                if len(parts) == 4:
                    monitors.append({'name': mon, 'w': int(parts[0]),
                                     'h': int(parts[1]), 'x': int(parts[2]), 'y': int(parts[3])})
        if monitors: return monitors
    except: pass
    try:
        out = subprocess.check_output("xrandr | grep '*' | awk '{print $1}'",
                                       shell=True).decode().strip().split('\n')[0]
        w, h = out.split('x')
        return [{'name': 'default', 'w': int(w), 'h': int(h), 'x': 0, 'y': 0}]
    except:
        return [{'name': 'default', 'w': 1920, 'h': 1080, 'x': 0, 'y': 0}]

MONITORS = get_monitors()
TOTAL_W = max(m['x'] + m['w'] for m in MONITORS)
TOTAL_H = max(m['y'] + m['h'] for m in MONITORS)

# ─── SICHQONCHA (xdotool) ─────────────────────────────
def move_cursor(x, y):
    x = max(0, min(int(x), TOTAL_W - 1))
    y = max(0, min(int(y), TOTAL_H - 1))
    subprocess.Popen(["xdotool", "mousemove", str(x), str(y)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_left_click():
    subprocess.Popen(["xdotool", "click", "1"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_right_click():
    subprocess.Popen(["xdotool", "click", "3"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_double_click():
    subprocess.Popen(["xdotool", "click", "--repeat", "2", "--delay", "80", "1"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_scroll_up(n=2):
    subprocess.Popen(["xdotool", "click", "--repeat", str(n), "4"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_scroll_down(n=2):
    subprocess.Popen(["xdotool", "click", "--repeat", str(n), "5"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_mouse_down():
    subprocess.Popen(["xdotool", "mousedown", "1"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_mouse_up():
    subprocess.Popen(["xdotool", "mouseup", "1"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def do_key(key):
    subprocess.Popen(["xdotool", "key", key],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ─── OVOZ BALANDLIGI (pactl / amixer) ─────────────────
def set_system_volume(percent):
    """Linux: pactl orqali ovoz balandligini o'zgartirish"""
    percent = max(0, min(100, int(percent)))
    try:
        subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        try:
            subprocess.Popen(["amixer", "-q", "set", "Master", f"{percent}%"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

def get_system_volume():
    """Joriy ovoz balandligini olish"""
    try:
        out = subprocess.check_output(
            "pactl get-sink-volume @DEFAULT_SINK@ | grep -o '[0-9]*%' | head -1",
            shell=True).decode().strip().rstrip('%')
        return int(out)
    except:
        return 50

def volume_up(step=5):
    subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def volume_down(step=5):
    subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ─── SCREENSHOT ───────────────────────────────────────
SHOT_DIR = os.path.expanduser("~/Pictures/NozimAI")
os.makedirs(SHOT_DIR, exist_ok=True)

def take_screenshot(root_widget=None):
    """Ekran skrinshotini olish va saqlash"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SHOT_DIR, f"nozim_ai_{ts}.png")
    try:
        # scrot yoki import (ImageMagick)
        result = subprocess.run(["scrot", path],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            subprocess.run(["import", "-window", "root", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        try:
            img = ImageGrab.grab()
            img.save(path)
        except:
            return None, None
    return path, ts

# ─── MODEL ────────────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
if not os.path.exists(MODEL_PATH):
    print("Model yuklanmoqda...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        MODEL_PATH)
    print("Model yuklandi!")

THUMB, INDEX, MIDDLE, RING, PINKY = 4, 8, 12, 16, 20
CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),(0,17)
]

DEFAULT_SETTINGS = {
    'smooth':       0.25,
    'thresh':       0.55,
    'scroll_speed': 2,
    'vol_step':     5,      # Ovoz o'zgartirish qadami
    'monitor_idx':  0,
    'cam_idx':      0,
    'show_skeleton':True,
    'show_fps':     True,
    'vol_gesture':  True,   # Ovoz gestini yoqish/o'chirish
    'shot_dir':     SHOT_DIR,
}


class NozimAI:
    def __init__(self, root):
        self.root = root
        self.root.title("NOZIM AI — v5.0")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.settings = DEFAULT_SETTINGS.copy()
        self.cur_x = self.cur_y = 0.0
        self.running = False
        self._pending_frame = None

        # Gesture states
        self.pinch_ti = self.pinch_tm = self.pinch_tr = False
        self.drag_active = False
        self.last_click_time = 0
        self.scroll_ref_y = None
        self.scroll_cooldown = 0
        self.kb_gesture_cd = 0
        self.vol_gesture_cd = 0
        self.shot_gesture_cd = 0
        self.vol_ref_y = None

        # Volume
        self.current_vol = get_system_volume()

        # Screenshots list
        self.screenshots = []

        # FPS
        self.fps_buf = deque(maxlen=30)
        self.prev_time = time.time()

        self._build_ui()
        self._clock_tick()
        self._preview_tick()

    # ══════════════════════════════════════════════════
    #  UI QURISH
    # ══════════════════════════════════════════════════
    def _build_ui(self):
        # CHAP PANEL
        self.left = tk.Frame(self.root, bg=BG, width=310)
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)

        # Header
        hdr = tk.Frame(self.left, bg=BG)
        hdr.pack(fill="x", padx=12, pady=(16,4))
        tk.Label(hdr, text="NOZIM AI",
                 font=("Courier New", 22, "bold"), bg=BG, fg=ACCENT).pack()
        tk.Label(hdr, text="GESTURE CONTROL  v5.0",
                 font=("Courier New", 7), bg=BG, fg=DIM).pack()

        # Status bar
        sb = tk.Frame(self.left, bg=PANEL,
                      highlightbackground=BORDER, highlightthickness=1)
        sb.pack(fill="x", padx=12, pady=6)
        r1 = tk.Frame(sb, bg=PANEL)
        r1.pack(fill="x", padx=10, pady=(6,2))
        self.cam_dot = tk.Canvas(r1, width=10, height=10,
                                  bg=PANEL, highlightthickness=0)
        self.cam_dot.create_oval(1,1,9,9, fill=DIM, outline="", tags="dot")
        self.cam_dot.pack(side="left", padx=(0,5))
        self.cam_lbl = tk.Label(r1, text="KAMERA OFF",
                                 font=("Courier New", 9), bg=PANEL, fg=DIM)
        self.cam_lbl.pack(side="left")
        self.fps_lbl = tk.Label(r1, text="",
                                 font=("Courier New", 9), bg=PANEL, fg=DIM)
        self.fps_lbl.pack(side="right")
        r2 = tk.Frame(sb, bg=PANEL)
        r2.pack(fill="x", padx=10, pady=(0,6))
        self.mon_lbl = tk.Label(r2, text=f"Monitor: {MONITORS[0]['name']}",
                                 font=("Courier New", 8), bg=PANEL, fg=DIM)
        self.mon_lbl.pack(side="left")
        self.clock_lbl = tk.Label(r2, text="00:00:00",
                                   font=("Courier New", 8), bg=PANEL, fg=DIM)
        self.clock_lbl.pack(side="right")

        # Tugmalar
        bp = tk.Frame(self.left, bg=PANEL,
                      highlightbackground=BORDER, highlightthickness=1)
        bp.pack(fill="x", padx=12, pady=4)
        inn = tk.Frame(bp, bg=PANEL)
        inn.pack(padx=12, pady=10, fill="x")

        self._btn(inn, "🚀  START",       "#003d30", ACCENT,  self.start_engine).pack(fill="x", pady=2)
        self._btn(inn, "⏹  STOP",        "#200a0e", ACCENT2, self.stop_engine).pack(fill="x", pady=2)
        self._btn(inn, "📸  SCREENSHOT",  "#001a22", SHOT_C,  self.manual_screenshot).pack(fill="x", pady=2)
        self._btn(inn, "⚙   SOZLAMA",    "#0a0f2a", ACCENT3, self.open_settings).pack(fill="x", pady=2)
        self._btn(inn, "⏻  CHIQISH",     "#200a0e", ACCENT2, self._on_close).pack(fill="x", pady=2)

        # ── OVOZ BOSHQARUVI ──
        tk.Frame(inn, bg=BORDER, height=1).pack(fill="x", pady=8)
        tk.Label(inn, text="🔊 OVOZ BALANDLIGI:",
                 font=("Courier New", 8, "bold"), bg=PANEL, fg=VOL_C).pack(anchor="w")
        vol_f = tk.Frame(inn, bg=PANEL)
        vol_f.pack(fill="x", pady=4)
        self.vol_var = tk.IntVar(value=self.current_vol)
        self.vol_scale = tk.Scale(vol_f, from_=0, to=100, orient="horizontal",
                                   variable=self.vol_var, command=self._on_vol_change,
                                   bg=PANEL, fg=VOL_C, troughcolor=BORDER,
                                   activebackground=VOL_C, highlightthickness=0,
                                   sliderlength=15, width=8, showvalue=False)
        self.vol_scale.pack(side="left", fill="x", expand=True)
        self.vol_pct_lbl = tk.Label(vol_f, text=f"{self.current_vol}%",
                                     font=("Courier New", 9, "bold"),
                                     bg=PANEL, fg=VOL_C, width=5)
        self.vol_pct_lbl.pack(side="right")

        # Vol buttons
        vbf = tk.Frame(inn, bg=PANEL)
        vbf.pack(fill="x", pady=2)
        self._mini_btn(vbf, "🔉 -5", VOL_C, lambda: self._adjust_vol(-5)).pack(side="left", fill="x", expand=True, padx=(0,2))
        self._mini_btn(vbf, "🔊 +5", VOL_C, lambda: self._adjust_vol(+5)).pack(side="right", fill="x", expand=True, padx=(2,0))

        # ── GEST QO'LLANMA ──
        tk.Frame(inn, bg=BORDER, height=1).pack(fill="x", pady=8)
        tk.Label(inn, text="BOSHQARUV:",
                 font=("Courier New", 8, "bold"), bg=PANEL, fg=TEXT).pack(anchor="w")

        guides = [
            (ACCENT,   "KICHIK BARMOG'",     "Kursor"),
            (ACCENT,   "BOSH + KO'RSATKICH", "Chap klik"),
            (ACCENT,   "2x BOSH + KO'RS.",   "2x klik"),
            (ACCENT2,  "BOSH + O'RTA",        "O'ng klik"),
            (ACCENT3,  "KO'RS. + O'RTA",      "Scroll"),
            ("#aa66ff", "BOSH + UZUQ",         "Drag & Drop"),
            (VOL_C,    "BOSH + JIMJILOQ",     "Ovoz +/−"),
            (SHOT_C,   "✌ IKKITA BARMOG'",   "Screenshot"),
            ("#ffaa00", "BARCHA 5",             "Reset"),
            ("#00aaff", "MUSHTLASH",            "Alt+Tab"),
        ]
        for color, k, v in guides:
            r = tk.Frame(inn, bg=PANEL)
            r.pack(fill="x", pady=1)
            tk.Label(r, text="●", font=("Courier New", 7), bg=PANEL, fg=color).pack(side="left", padx=(0,3))
            tk.Label(r, text=k, font=("Courier New", 7, "bold"), bg=PANEL, fg=TEXT).pack(side="left")
            tk.Label(r, text=f" → {v}", font=("Courier New", 7), bg=PANEL, fg=DIM).pack(side="left")

        # Status
        tk.Frame(inn, bg=BORDER, height=1).pack(fill="x", pady=6)
        self.status_lbl = tk.Label(inn, text="● TAYYOR",
                                    font=("Courier New", 10, "bold"), bg=PANEL, fg=DIM)
        self.status_lbl.pack(anchor="w")

        # Log
        self.log = tk.Text(inn, height=4, bg="#040810", fg=ACCENT,
                           font=("Courier New", 8), relief="flat",
                           state="disabled", highlightbackground=BORDER, highlightthickness=1)
        self.log.pack(fill="x", pady=(6,0))
        self._log("Tayyor. START bosing.")

        # Screenshot directory info
        tk.Label(self.left, text=f"📁 {SHOT_DIR}",
                 font=("Courier New", 6), bg=BG, fg=DIM, wraplength=280).pack(pady=(4,2))
        mon_info = " | ".join([f"{m['name']}:{m['w']}x{m['h']}" for m in MONITORS])
        tk.Label(self.left, text=mon_info,
                 font=("Courier New", 6), bg=BG, fg=DIM).pack(pady=(0,8))

        # O'NG: kamera
        right = tk.Frame(self.root, bg="#000000")
        right.pack(side="right", fill="both", expand=True)
        self.preview = tk.Label(right, bg="#000000",
                                 text="📷\n\nKamera ko'rinishi\nSTART bosing",
                                 fg="#1a2a1a", font=("Courier New", 13))
        self.preview.pack(fill="both", expand=True)

        self.root.geometry("1080x640")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"1080x640+{(sw-1080)//2}+{(sh-640)//2}")

    def _btn(self, parent, label, bg, fg, cmd):
        f = tk.Frame(parent, bg=bg, highlightbackground=fg,
                     highlightthickness=1, cursor="hand2")
        lbl = tk.Label(f, text=label, font=("Courier New", 10, "bold"),
                       bg=bg, fg=fg, pady=8, cursor="hand2")
        lbl.pack(expand=True)
        oe = lambda e: (f.config(bg=fg), lbl.config(bg=fg, fg=bg))
        ol = lambda e: (f.config(bg=bg), lbl.config(bg=bg, fg=fg))
        for w in (f, lbl):
            w.bind("<Enter>", oe); w.bind("<Leave>", ol)
            w.bind("<Button-1>", lambda e: cmd())
        return f

    def _mini_btn(self, parent, label, fg, cmd):
        f = tk.Frame(parent, bg=PANEL, highlightbackground=fg,
                     highlightthickness=1, cursor="hand2")
        lbl = tk.Label(f, text=label, font=("Courier New", 8, "bold"),
                       bg=PANEL, fg=fg, pady=3, cursor="hand2")
        lbl.pack(expand=True)
        for w in (f, lbl):
            w.bind("<Button-1>", lambda e: cmd())
        return f

    def _on_vol_change(self, v):
        vol = int(float(v))
        self.vol_pct_lbl.configure(text=f"{vol}%")
        set_system_volume(vol)
        self.current_vol = vol

    def _adjust_vol(self, delta):
        new_vol = max(0, min(100, self.current_vol + delta))
        self.vol_var.set(new_vol)
        self.vol_pct_lbl.configure(text=f"{new_vol}%")
        set_system_volume(new_vol)
        self.current_vol = new_vol
        self._log(f"Ovoz: {new_vol}%")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text, color=ACCENT):
        self.status_lbl.configure(text=f"● {text}", fg=color)

    def _clock_tick(self):
        self.clock_lbl.configure(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._clock_tick)

    def _preview_tick(self):
        if self._pending_frame is not None:
            f = self._pending_frame
            self._pending_frame = None
            pw = self.preview.winfo_width()
            ph = self.preview.winfo_height()
            if pw > 10 and ph > 10:
                h, w = f.shape[:2]
                scale = min(pw/w, ph/h)
                nw, nh = int(w*scale), int(h*scale)
                rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb, (nw, nh))
                pil = Image.fromarray(resized)
                tk_img = ImageTk.PhotoImage(pil)
                self.preview.configure(image=tk_img, text="")
                self.preview.image = tk_img
        self.root.after(33, self._preview_tick)

    def _set_cam(self, on):
        c = ACCENT if on else DIM
        self.cam_dot.itemconfig("dot", fill=c)
        self.cam_lbl.configure(fg=c, text="KAMERA ON" if on else "KAMERA OFF")

    def _on_close(self):
        self.running = False
        if self.drag_active: do_mouse_up()
        self.root.quit()

    def manual_screenshot(self):
        """Tugma bosilganda skrinshot olish"""
        path, ts = take_screenshot()
        if path:
            self._log(f"📸 Screenshot: {ts}")
            self._set_status("SCREENSHOT OLINDI", SHOT_C)
        else:
            self._log("Screenshot xatosi!")

    # ══════════════════════════════════════════════════
    #  SOZLAMALAR
    # ══════════════════════════════════════════════════
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("SOZLAMALAR")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.geometry("400x580")
        sx = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        sy = self.root.winfo_y() + (self.root.winfo_height() - 580) // 2
        win.geometry(f"400x580+{sx}+{sy}")

        tk.Label(win, text="⚙  SOZLAMALAR",
                 font=("Courier New", 14, "bold"), bg=PANEL, fg=ACCENT3).pack(pady=16)

        frm = tk.Frame(win, bg=PANEL)
        frm.pack(fill="x", padx=24)

        def slider_row(parent, label, key, from_, to, resolution=0.01):
            r = tk.Frame(parent, bg=PANEL)
            r.pack(fill="x", pady=6)
            tk.Label(r, text=label, font=("Courier New", 9),
                     bg=PANEL, fg=TEXT, width=22, anchor="w").pack(side="left")
            var = tk.DoubleVar(value=self.settings[key])
            val_lbl = tk.Label(r, text=f"{self.settings[key]:.1f}",
                                font=("Courier New", 9), bg=PANEL, fg=ACCENT, width=5)
            val_lbl.pack(side="right")
            def on_change(v):
                self.settings[key] = float(v)
                val_lbl.configure(text=f"{float(v):.1f}")
            sl = tk.Scale(r, from_=from_, to=to, resolution=resolution,
                          orient="horizontal", variable=var, command=on_change,
                          bg=PANEL, fg=TEXT, troughcolor=BORDER,
                          activebackground=ACCENT3, highlightthickness=0,
                          sliderlength=15, width=8)
            sl.pack(side="right", padx=4)
            return var

        slider_row(frm, "Silliqlik (smooth)",   "smooth",       0.05, 1.0)
        slider_row(frm, "Klik sezgirligi",       "thresh",       0.3,  0.9)
        slider_row(frm, "Scroll tezligi",        "scroll_speed", 1,    5, 1)
        slider_row(frm, "Ovoz qadam (%)",        "vol_step",     1,    20, 1)

        # Monitor tanlash
        tk.Frame(frm, bg=BORDER, height=1).pack(fill="x", pady=10)
        tk.Label(frm, text="Aktiv monitor:",
                 font=("Courier New", 9), bg=PANEL, fg=TEXT).pack(anchor="w")
        mon_var = tk.IntVar(value=self.settings['monitor_idx'])
        for i, m in enumerate(MONITORS):
            tk.Radiobutton(frm,
                text=f"{m['name']}  ({m['w']}x{m['h']} @ +{m['x']},+{m['y']})",
                variable=mon_var, value=i,
                font=("Courier New", 8), bg=PANEL, fg=TEXT,
                selectcolor=BORDER, activebackground=PANEL,
                activeforeground=ACCENT).pack(anchor="w", pady=2)

        # Togglelar
        tk.Frame(frm, bg=BORDER, height=1).pack(fill="x", pady=10)

        def toggle_row(parent, label, key):
            r = tk.Frame(parent, bg=PANEL)
            r.pack(fill="x", pady=4)
            tk.Label(r, text=label, font=("Courier New", 9),
                     bg=PANEL, fg=TEXT).pack(side="left")
            var = tk.BooleanVar(value=self.settings[key])
            tk.Checkbutton(r, variable=var, bg=PANEL, fg=ACCENT,
                            selectcolor=BORDER, activebackground=PANEL,
                            command=lambda: self.settings.update({key: var.get()})).pack(side="right")
            return var

        toggle_row(frm, "Skelet ko'rsatish",     "show_skeleton")
        toggle_row(frm, "FPS ko'rsatish",         "show_fps")
        toggle_row(frm, "Ovoz gest (bosh+jimj.)", "vol_gesture")

        # Kamera indeksi
        tk.Frame(frm, bg=BORDER, height=1).pack(fill="x", pady=8)
        cam_r = tk.Frame(frm, bg=PANEL)
        cam_r.pack(fill="x")
        tk.Label(cam_r, text="Kamera indeksi (0/1/2):",
                 font=("Courier New", 9), bg=PANEL, fg=TEXT).pack(side="left")
        cam_var = tk.IntVar(value=self.settings['cam_idx'])
        for i in range(3):
            tk.Radiobutton(cam_r, text=str(i), variable=cam_var, value=i,
                           font=("Courier New", 9), bg=PANEL, fg=TEXT,
                           selectcolor=BORDER, activebackground=PANEL,
                           activeforeground=ACCENT).pack(side="left", padx=4)

        # Saqlash
        def save():
            self.settings['monitor_idx'] = mon_var.get()
            self.settings['cam_idx']     = cam_var.get()
            m = MONITORS[self.settings['monitor_idx']]
            self.mon_lbl.configure(text=f"Monitor: {m['name']}")
            self._log("Sozlamalar saqlandi")
            win.destroy()

        save_f = tk.Frame(win, bg=ACCENT3, highlightbackground=ACCENT3,
                          highlightthickness=1, cursor="hand2")
        save_f.pack(padx=24, pady=16, fill="x")
        save_lbl = tk.Label(save_f, text="💾  SAQLASH",
                             font=("Courier New", 11, "bold"),
                             bg=ACCENT3, fg=PANEL, pady=10, cursor="hand2")
        save_lbl.pack(expand=True)
        for w in (save_f, save_lbl):
            w.bind("<Button-1>", lambda e: save())

    # ══════════════════════════════════════════════════
    #  ENGINE
    # ══════════════════════════════════════════════════
    def start_engine(self):
        if self.running:
            self._log("Allaqachon ishlamoqda!")
            return
        self.running = True
        self._set_cam(True)
        self._set_status("ISHLAMOQDA", ACCENT)
        self._log("Kamera ishga tushdi...")
        threading.Thread(target=self._camera_loop, daemon=True).start()

    def stop_engine(self):
        if self.drag_active:
            do_mouse_up()
            self.drag_active = False
        self.running = False
        self._set_cam(False)
        self._set_status("TO'XTATILDI", ACCENT2)
        self._log("To'xtatildi.")
        self.preview.configure(image="", text="📷\n\nKamera ko'rinishi\nSTART bosing")
        self.fps_lbl.configure(text="")

    # ══════════════════════════════════════════════════
    #  KAMERA LOOP
    # ══════════════════════════════════════════════════
    def _camera_loop(self):
        options = HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=VisionTaskRunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.3,
            min_hand_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )

        cam_idx = self.settings['cam_idx']
        cap = cv2.VideoCapture(cam_idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        if not cap.isOpened():
            self.root.after(0, lambda: self._log("XATO: Kamera ochilmadi!"))
            return

        self.root.after(0, lambda: self._log("Qo'lingizni ko'rsating..."))

        with HandLandmarker.create_from_options(options) as detector:
            while self.running:
                ret, frame = cap.read()
                if not ret: break

                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]

                # FPS
                now = time.time()
                dt = now - self.prev_time + 1e-9
                self.fps_buf.append(1.0 / dt)
                self.prev_time = now
                fps = int(np.mean(self.fps_buf))

                if self.settings['show_fps']:
                    self.root.after(0, lambda f=fps:
                        self.fps_lbl.configure(text=f"{f} FPS"))

                mon = MONITORS[self.settings['monitor_idx']]
                mon_x, mon_y = mon['x'], mon['y']
                mon_w, mon_h = mon['w'], mon['h']

                rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = detector.detect(mp_img)

                action_text  = ""
                action_color = (0, 245, 196)

                if result.hand_landmarks:
                    lms = result.hand_landmarks[0]
                    pts = [(int(lm.x * w), int(lm.y * h)) for lm in lms]

                    if self.settings['show_skeleton']:
                        for a, b in CONNECTIONS:
                            cv2.line(frame, pts[a], pts[b], (15, 60, 45), 2)
                        for i, pt in enumerate(pts):
                            r = 6 if i in (THUMB,INDEX,MIDDLE,RING,PINKY) else 3
                            cv2.circle(frame, pt, r, (0, 200, 140), -1)

                    t       = pts[THUMB]
                    ix, iy  = pts[INDEX]
                    mx, my  = pts[MIDDLE]
                    rx, ry  = pts[RING]
                    px, py  = pts[PINKY]

                    # Kursor: kichik barmog'
                    fx = np.interp(px, (40, w-40), (mon_x, mon_x + mon_w))
                    fy = np.interp(py, (40, h-40), (mon_y, mon_y + mon_h))
                    s  = self.settings['smooth'] * 3
                    self.cur_x += (fx - self.cur_x) * s
                    self.cur_y += (fy - self.cur_y) * s
                    move_cursor(self.cur_x, self.cur_y)
                    cv2.circle(frame, (px, py), 15, (0, 255, 200), 2)
                    cv2.circle(frame, (px, py), 3,  (0, 255, 200), -1)

                    palm   = np.hypot(pts[0][0]-pts[17][0], pts[0][1]-pts[17][1]) + 1e-6
                    THRESH = self.settings['thresh']

                    d_ti = np.hypot(ix-t[0], iy-t[1]) / palm
                    d_tm = np.hypot(mx-t[0], my-t[1]) / palm
                    d_tr = np.hypot(rx-t[0], ry-t[1]) / palm
                    d_tp = np.hypot(px-t[0], py-t[1]) / palm  # thumb-pinky (ovoz)
                    d_im = np.hypot(mx-ix,   my-iy)   / palm

                    tips_y  = [pts[4][1],pts[8][1],pts[12][1],pts[16][1],pts[20][1]]
                    bases_y = [pts[2][1],pts[5][1],pts[9][1], pts[13][1],pts[17][1]]
                    open_count  = sum(1 for i in range(5) if tips_y[i] < bases_y[i])
                    closed_count = 5 - open_count

                    # ✌ SCREENSHOT GESTI: faqat ko'rsatkich + o'rta ochiq
                    index_up  = pts[8][1]  < pts[5][1]
                    middle_up = pts[12][1] < pts[9][1]
                    ring_down  = pts[16][1] >= pts[13][1]
                    pinky_down = pts[20][1] >= pts[17][1]
                    if index_up and middle_up and ring_down and pinky_down and d_ti > THRESH:
                        if now > self.shot_gesture_cd:
                            path, ts = take_screenshot()
                            if path:
                                self.shot_gesture_cd = now + 2.0
                                action_text  = "📸 SCREENSHOT!"
                                action_color = (0, 200, 255)
                                self.root.after(0, lambda t=ts: self._log(f"📸 Screenshot: {t}"))
                                self.root.after(0, lambda: self._set_status("SCREENSHOT", SHOT_C))
                        cv2.circle(frame, (ix,iy), 18, (0,200,255), 2)
                        cv2.circle(frame, (mx,my), 18, (0,200,255), 2)
                        self._pending_frame = frame.copy()
                        continue

                    # ── MUSHTLASH ──
                    if closed_count == 5:
                        t_now = time.time()
                        if t_now > self.kb_gesture_cd:
                            do_key("alt+Tab")
                            self.kb_gesture_cd = t_now + 1.5
                            action_text  = "⌨ ALT+TAB"
                            action_color = (0, 170, 255)
                            self.root.after(0, lambda: self._log("Alt+Tab"))
                            self.root.after(0, lambda: self._set_status("ALT+TAB", "#00aaff"))

                    # ── BARCHA 5 OCHIQ: RESET ──
                    elif open_count == 5:
                        if self.drag_active:
                            do_mouse_up()
                            self.drag_active = False
                        self.pinch_ti = self.pinch_tm = self.pinch_tr = False
                        self.scroll_ref_y = None
                        self.vol_ref_y = None
                        action_text  = "✋ RESET"
                        action_color = (255, 200, 0)
                        self.root.after(0, lambda: self._set_status("RESET", "#ffaa00"))

                    else:
                        # ── OVOZ: bosh + jimjiloq ──
                        if self.settings['vol_gesture'] and d_tp < THRESH:
                            if self.vol_ref_y is None:
                                self.vol_ref_y = py
                            else:
                                dy = self.vol_ref_y - py
                                if abs(dy) > 8 and now > self.vol_gesture_cd:
                                    step = int(self.settings['vol_step'])
                                    if dy > 0:
                                        volume_up(step)
                                        self.current_vol = min(100, self.current_vol + step)
                                        action_text  = f"🔊 OVOZ + ({self.current_vol}%)"
                                    else:
                                        volume_down(step)
                                        self.current_vol = max(0, self.current_vol - step)
                                        action_text  = f"🔉 OVOZ − ({self.current_vol}%)"
                                    action_color = (255, 170, 0)
                                    self.vol_ref_y = py
                                    self.vol_gesture_cd = now + 0.4
                                    vol_now = self.current_vol
                                    self.root.after(0, lambda v=vol_now: (
                                        self._set_status(f"OVOZ: {v}%", VOL_C),
                                        self.vol_var.set(v),
                                        self.vol_pct_lbl.configure(text=f"{v}%")
                                    ))
                            cv2.circle(frame, (px,py), 18, (255,170,0), 2)
                            cv2.circle(frame, t,       18, (255,170,0), 2)
                            self._pending_frame = frame.copy()
                            continue
                        else:
                            self.vol_ref_y = None

                        pairs  = {"ti": d_ti, "tm": d_tm, "tr": d_tr, "im": d_im}
                        best   = min(pairs, key=pairs.get)
                        best_d = pairs[best]

                        # Chap klik
                        if best == "ti" and best_d < THRESH:
                            if not self.pinch_ti:
                                self.pinch_ti = True
                                t_now = time.time()
                                if t_now - self.last_click_time < 0.35:
                                    do_double_click()
                                    action_text  = "⚡ 2x KLIK!"
                                    action_color = (255, 255, 0)
                                    self.root.after(0, lambda: self._log("2x klik!"))
                                    self.root.after(0, lambda: self._set_status("2x KLIK", "#ffff00"))
                                else:
                                    do_left_click()
                                    action_text  = "👆 CHAP KLIK"
                                    action_color = (0, 255, 120)
                                    self.root.after(0, lambda: self._log("Chap klik"))
                                    self.root.after(0, lambda: self._set_status("CHAP KLIK", ACCENT))
                                self.last_click_time = t_now
                            cv2.circle(frame, (ix,iy), 20, (0,255,120), 2)
                            cv2.circle(frame, t,       20, (0,255,120), 2)
                        elif best != "ti":
                            self.pinch_ti = False

                        # O'ng klik
                        if best == "tm" and best_d < THRESH:
                            if not self.pinch_tm:
                                self.pinch_tm = True
                                do_right_click()
                                action_text  = "👆 O'NG KLIK"
                                action_color = (255, 80, 80)
                                self.root.after(0, lambda: self._log("O'ng klik"))
                                self.root.after(0, lambda: self._set_status("O'NG KLIK", ACCENT2))
                            cv2.circle(frame, (mx,my), 20, (255,80,80), 2)
                            cv2.circle(frame, t,       20, (255,80,80), 2)
                        elif best != "tm":
                            self.pinch_tm = False

                        # Drag
                        if best == "tr" and best_d < THRESH:
                            if not self.drag_active:
                                self.drag_active = True
                                do_mouse_down()
                                action_text  = "✊ DRAG BOSHLANDI"
                                action_color = (170, 100, 255)
                                self.root.after(0, lambda: self._log("Drag boshlandi"))
                                self.root.after(0, lambda: self._set_status("DRAG", ACCENT3))
                            else:
                                action_text  = "✊ DRAG..."
                                action_color = (170, 100, 255)
                            cv2.circle(frame, (rx,ry), 20, (170,100,255), 2)
                            cv2.circle(frame, t,       20, (170,100,255), 2)
                        elif best != "tr" and self.drag_active:
                            do_mouse_up()
                            self.drag_active = False
                            action_text  = "✊ TASHLAB YUBORILDI"
                            action_color = (170, 100, 255)
                            self.root.after(0, lambda: self._log("Drag tugadi"))
                            self.root.after(0, lambda: self._set_status("ISHLAMOQDA", ACCENT))

                        # Scroll
                        if best == "im" and best_d < THRESH:
                            self.pinch_ti = self.pinch_tm = self.pinch_tr = False
                            if self.scroll_ref_y is None:
                                self.scroll_ref_y = iy
                            else:
                                dy    = self.scroll_ref_y - iy
                                spd   = int(self.settings['scroll_speed'])
                                if abs(dy) > 10 and now > self.scroll_cooldown:
                                    if dy > 0:
                                        do_scroll_up(spd)
                                        action_text = "↑ SCROLL UP"
                                    else:
                                        do_scroll_down(spd)
                                        action_text = "↓ SCROLL DOWN"
                                    action_color       = (100, 200, 255)
                                    self.scroll_ref_y  = iy
                                    self.scroll_cooldown = now + 0.12
                                    self.root.after(0, lambda t=action_text:
                                        self._set_status(t, ACCENT3))
                            cv2.circle(frame, (ix,iy), 16, (100,200,255), 2)
                            cv2.circle(frame, (mx,my), 16, (100,200,255), 2)
                        else:
                            self.scroll_ref_y = None

                    cv2.putText(frame, "QO'L ANIQLANDI", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,245,196), 2)
                    if action_text:
                        cv2.putText(frame, action_text, (10, h-30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, action_color, 2)

                else:
                    if self.drag_active:
                        do_mouse_up()
                        self.drag_active = False
                    self.pinch_ti = self.pinch_tm = self.pinch_tr = False
                    self.scroll_ref_y = None
                    self.vol_ref_y = None
                    cv2.putText(frame, "Qo'lingizni ko'rsating...", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (60,60,60), 2)
                    self.root.after(0, lambda: self._set_status("QO'L YO'Q", DIM))

                if self.settings['show_fps']:
                    cv2.putText(frame, f"{fps} FPS", (w-75, 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40,40,40), 1)

                cv2.putText(frame, f"Monitor: {mon['name']} ({mon_w}x{mon_h})",
                            (10, h-12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (40,40,40), 1)

                self._pending_frame = frame.copy()

        cap.release()
        self.root.after(0, self.stop_engine)


if __name__ == "__main__":
    root = tk.Tk()
    NozimAI(root)
    root.mainloop()