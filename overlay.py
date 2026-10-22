# -*- coding: utf-8 -*-
"""
Oyun penceresine yapisik, seffaf, tiklama-gecirgen overlay.

Oyun 'Pencere' veya 'Pencereli Tam Ekran' modunda OLMALI.
Pencere basligi/sinifi notr tutulur, boylece anti-cheat pencere
taramalarinda dikkat cekmez.
"""
import ctypes
from ctypes import wintypes
import tkinter as tk

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

SUSPECT_TITLES = (
    "cheat engine", "cheatengine", "ce 7", "ce 6",
    "artmoney", "process hacker", "x64dbg", "ollydbg",
)


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def find_game_window(pid):
    """Process'e ait en buyuk gorunur pencereyi bulur."""
    result = {"hwnd": None, "area": 0}

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        wnd_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wnd_pid))
        if wnd_pid.value != pid:
            return True
        r = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return True
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > result["area"]:
            result["area"] = area
            result["hwnd"] = hwnd
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return result["hwnd"]


def client_rect_on_screen(hwnd):
    """Oyun istemci alani: (x, y, w, h) ekran koordinatinda."""
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def other_cheat_windows():
    """
    Zula Guard'i tetikledigi bilinen pencereleri arar.
    Ozellikle Cheat Engine acikken maca girilirse 5-10 sn sonra kick yenir.
    """
    found = []

    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        low = buf.value.lower()
        for s in SUSPECT_TITLES:
            if s in low:
                if buf.value not in found:
                    found.append(buf.value)
                break
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


class Overlay:
    def __init__(self, cfg):
        self.cfg = cfg
        set_dpi_aware()

        ov_cfg = cfg.get("overlay", {})
        self.root = tk.Tk(className=ov_cfg.get("window_class", "ZulaOverlay"))
        self.root.title(ov_cfg.get("window_title", "zula_wh"))
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg="black")
        self.root.geometry("400x300+0+0")

        try:
            self.root.attributes("-transparentcolor", "black")
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.root.update_idletasks()
        self.hwnd = self.root.winfo_id()
        self._make_click_through()

        self.width = 400
        self.height = 300
        self._last_geo = None

    def _make_click_through(self):
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)

    def track(self, game_hwnd):
        if not game_hwnd:
            return False
        rect = client_rect_on_screen(game_hwnd)
        if not rect:
            return False
        x, y, w, h = rect
        if w < 50 or h < 50:
            return False
        self.width, self.height = w, h
        geo = f"{w}x{h}+{x}+{y}"
        if geo != self._last_geo:
            self.root.geometry(geo)
            self._last_geo = geo
        return True

    # ---------------- cizim yardimcilari ---------------- #
    def begin(self):
        self.canvas.delete("all")

    def end(self):
        self.root.update()

    def box(self, x1, y1, x2, y2, color, width=2):
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=width)

    def corner_box(self, x1, y1, x2, y2, color, width=2, seg=0.22):
        w = x2 - x1
        h = y2 - y1
        sx = w * seg
        sy = h * seg
        for pts in (
            (x1, y1, x1 + sx, y1), (x1, y1, x1, y1 + sy),
            (x2, y1, x2 - sx, y1), (x2, y1, x2, y1 + sy),
            (x1, y2, x1 + sx, y2), (x1, y2, x1, y2 - sy),
            (x2, y2, x2 - sx, y2), (x2, y2, x2, y2 - sy),
        ):
            self.canvas.create_line(*pts, fill=color, width=width)

    def text(self, x, y, s, color, size=11, anchor="s", bold=True):
        self.canvas.create_text(
            x, y, text=s, fill=color, anchor=anchor,
            font=("Segoe UI", size, "bold" if bold else "normal"))

    def line(self, x1, y1, x2, y2, color, width=1):
        self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width)

    def rect_fill(self, x1, y1, x2, y2, color):
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, fill=color)

    def circle(self, x, y, r, color):
        self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                outline=color, fill=color)

    def destroy(self):
        try:
            self.root.destroy()
        except Exception:
            pass