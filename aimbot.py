# -*- coding: utf-8 -*-
"""
Dis aimbot + humanize katmani.

Fare hareketi SendInput ile yapilir; oyunun kendi hassasiyetinden etkilenir.
Humanize katmani, sabit bolenli ustel bozunma desenini kirar:
  - hedef degisiminde tepki gecikmesi
  - olu bolge (yakin hedefte mikro hareket yok)
  - her karede degisen smooth degeri
  - ara sira asma (overshoot)
  - kucuk rastgele jitter
"""
import ctypes
import math
import random

user32 = ctypes.windll.user32
MOUSEEVENTF_MOVE = 0x0001
PUL = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


class AimState:
    def __init__(self):
        self.last_target = None
        self.reaction_left = 0


def move_mouse_relative(dx, dy):
    if dx == 0 and dy == 0:
        return
    inp = INPUT()
    inp.type = 0  # INPUT_MOUSE
    inp.u.mi.dx = int(dx)
    inp.u.mi.dy = int(dy)
    inp.u.mi.dwFlags = MOUSEEVENTF_MOVE
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def pick_target(cfg, players, cx, cy):
    a = cfg["aimbot"]
    fov_px = float(a["fov"]) * (cx / 100.0)
    best = None
    best_d = 1e9
    for p in players:
        if p["local"]:
            continue
        if a.get("only_enemy", True) and p["team"] != "enemy":
            continue
        if p["screen"] is None:
            continue
        d = math.hypot(p["screen"][0] - cx, p["screen"][1] - cy)
        if d > fov_px:
            continue
        if d < best_d:
            best_d = d
            best = p
    return best


def run(cfg, players, width, height, state):
    a = cfg["aimbot"]
    if not a.get("enabled", False):
        state.last_target = None
        return None

    cx, cy = width / 2.0, height / 2.0
    target = pick_target(cfg, players, cx, cy)

    if target is None or target["aim_screen"] is None:
        state.last_target = None
        state.reaction_left = 0
        return target

    h = a.get("humanize", {})
    human = h.get("enabled", True)

    if human:
        if state.last_target is not target:
            state.reaction_left = int(h.get("reaction_frames", 6))
            state.last_target = target
        if state.reaction_left > 0:
            state.reaction_left -= 1
            return target

    dx = target["aim_screen"][0] - cx
    dy = target["aim_screen"][1] - cy

    if human:
        dz = float(h.get("deadzone", 1.2))
        if abs(dx) < dz and abs(dy) < dz:
            return target
        j = float(h.get("smooth_jitter", 0.35))
        smooth = max(1.0, float(a["smooth"]) * (1.0 + random.uniform(-j, j)))
        if random.random() < float(h.get("overshoot_chance", 0.08)):
            smooth = max(1.0, smooth * (1.0 - float(h.get("overshoot", 0.15))))
    else:
        smooth = max(1.0, float(a["smooth"]))

    mx = dx / smooth
    my = dy / smooth

    limit = float(a["max_step"])
    mx = max(-limit, min(limit, mx))
    my = max(-limit, min(limit, my))

    if human:
        jp = float(h.get("jitter_px", 0.7))
        mx += random.uniform(-jp, jp)
        my += random.uniform(-jp, jp)

    if key_down(int(a["key_vk"])):
        move_mouse_relative(round(mx), round(my))

    return target