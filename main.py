# -*- coding: utf-8 -*-
"""
Zula external wallhack - ana dongu.

Yonetici olarak calistir. Oyun 'Pencere / Pencereli Tam Ekran' modunda olmali.
"""
import ctypes
import json
import os
import time

import overlay as ovl
import render
from aimbot import AimState, key_down
from aimbot import run as aim_run
from memory import ZulaMemory, hx

user32 = ctypes.windll.user32
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

VK_F1, VK_F2, VK_F3, VK_F4, VK_F5 = 0x70, 0x71, 0x72, 0x73, 0x74
VK_F6, VK_F7, VK_F8, VK_END = 0x75, 0x76, 0x77, 0x23

AIM_KEYS = [(18, "ALT"), (17, "CTRL"), (16, "SHIFT"), (2, "RMB"), (1, "LMB")]

_NAME_CACHE = {}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class KeyState:
    def __init__(self):
        self.prev = {}

    def pressed(self, vk):
        cur = key_down(vk)
        was = self.prev.get(vk, False)
        self.prev[vk] = cur
        return cur and not was


def classify(handle, cfg):
    f = cfg["filter"]
    for m in f["team_a_models"]:
        if m in handle:
            return "a"
    for m in f["team_b_models"]:
        if m in handle:
            return "b"
    return None


def build_entities(mem, cfg):
    off_handle = hx(cfg["offsets"]["entity_handle"])
    off_pos = hx(cfg["offsets"]["entity_position"])
    off_ang = hx(cfg["offsets"]["entity_angles"])
    off_health = hx(cfg["offsets"]["health"], None)
    off_armor = hx(cfg["offsets"]["armor"], None)
    off_alive = hx(cfg["entity"]["alive_offset"])

    alive_mode = cfg["entity"].get("alive_mode", "auto")
    draw_dead = cfg["entity"].get("draw_dead", False)
    max_d = float(cfg["entity"]["max_distance"])

    f = cfg["filter"]
    local = None
    local_pos = None
    players = []

    for ent in mem.iter_entities():
        handle = _NAME_CACHE.get(ent)
        if handle is None:
            h_ptr = mem.u32(ent + off_handle)
            if not h_ptr:
                continue
            handle = mem.cstr(h_ptr, 32)
            if not handle:
                continue
            _NAME_CACHE[ent] = handle

        is_local = f["local_marker"] in handle and f["mesh_marker"] in handle
        is_player = (f["player_marker"] in handle
                     and f["mesh_marker"] in handle and not is_local)
        if not (is_local or is_player):
            continue

        pos = mem.vec3(ent + off_pos)
        if not pos:
            continue
        if abs(pos[0]) < 0.01 and abs(pos[1]) < 0.01 and abs(pos[2]) < 0.01:
            continue

        if not draw_dead:
            if alive_mode == "uc_chain":
                n1 = mem.u32(ent + 0x4) or 0
                n2 = (mem.u32(n1 + 0x4) or 0) if n1 else 0
                if not n2 or mem.i32(n2 + 0x34) != 67109120:
                    continue
            elif alive_mode == "offset":
                av = mem.f32(ent + off_alive)
                if av is None or av < float(cfg["entity"]["alive_min"]):
                    continue

        angles = mem.vec3(ent + off_ang) or (0.0, 0.0, 0.0)

        info = {
            "addr": ent,
            "handle": handle,
            "pos": pos,
            "yaw": angles[0],
            "pitch": angles[1],
            "local": is_local,
            "team": "local" if is_local else (classify(handle, cfg) or "enemy"),
            "health": mem.f32(ent + off_health) if off_health else None,
            "armor": mem.f32(ent + off_armor) if off_armor else None,
            "screen": None,
            "aim_screen": None,
            "dist": 0.0,
            "name": handle.replace("_MESH.MD", "").replace("_MESH.M", "")
                         .replace("CHAR_", "").replace("FPS_", "")
                         .replace("_", " ").strip(),
        }

        if is_local:
            local = info
            local_pos = pos
        else:
            players.append(info)

    if local_pos is not None:
        for p in players:
            p["dist"] = render.dist3(p["pos"], local_pos)
        players = [p for p in players if p["dist"] <= max_d]

    return local, players


def main():
    cfg = load_config()
    mem = ZulaMemory(cfg)

    print("[*] Zula.exe bekleniyor...")
    while not mem.is_alive():
        try:
            mem.attach()
            _NAME_CACHE.clear()
            print(f"[+] Baglandi. PID={mem.pid}  base=0x{mem.base:X}  "
                  f"yetki={mem.access_label}")
        except Exception:
            time.sleep(1.0)

    ov = ovl.Overlay(cfg)
    ks = KeyState()
    aim_state = AimState()
    aim_key_index = 0
    frame_counter = 0
    ce_windows = []
    frame_time = 1.0 / float(cfg["loop"]["fps"])

    print("[+] Hazir.")
    print("    F1 ESP | F2 Radar | F3 Aimbot | F4 Nisam tusu | F5 Snapline")
    print("    F6 Reload | F7 Oluleri ciz | F8 Status | END Cikis")

    try:
        while True:
            t0 = time.perf_counter()
            frame_counter += 1

            if not mem.is_alive():
                print("[!] Process kapandi, yeniden baglaniliyor...")
                time.sleep(1.0)
                try:
                    mem.attach()
                    _NAME_CACHE.clear()
                except Exception:
                    continue

            # ------------------ hotkeyler ------------------ #
            if ks.pressed(VK_F1):
                cfg["esp"]["enabled"] = not cfg["esp"]["enabled"]
            if ks.pressed(VK_F2):
                cfg["radar"]["enabled"] = not cfg["radar"]["enabled"]
            if ks.pressed(VK_F3):
                cfg["aimbot"]["enabled"] = not cfg["aimbot"]["enabled"]
            if ks.pressed(VK_F4):
                aim_key_index = (aim_key_index + 1) % len(AIM_KEYS)
                cfg["aimbot"]["key_vk"] = AIM_KEYS[aim_key_index][0]
            if ks.pressed(VK_F5):
                cfg["esp"]["snapline"] = not cfg["esp"]["snapline"]
            if ks.pressed(VK_F6):
                try:
                    fresh = load_config()
                    cfg.update(fresh)
                    _NAME_CACHE.clear()
                    print("[+] config.json yeniden yuklendi")
                except Exception as e:
                    print(f"[!] config hatasi: {e}")
            if ks.pressed(VK_F7):
                cfg["entity"]["draw_dead"] = not cfg["entity"]["draw_dead"]
            if ks.pressed(VK_F8):
                cfg["loop"]["print_status"] = not cfg["loop"]["print_status"]
            if ks.pressed(VK_END):
                break

            mem.begin_frame()

            # ------------------ pencere ------------------ #
            game_hwnd = ovl.find_game_window(mem.pid)
            if not ov.track(game_hwnd):
                ov.begin()
                ov.text(12, 12, "Oyun penceresi bulunamadi", "#FF3B30", anchor="nw")
                ov.end()
                time.sleep(frame_time)
                continue

            width, height = ov.width, ov.height

            # ------------------ matrix ------------------ #
            m = mem.view_matrix()
            if m is None:
                ov.begin()
                if cfg["loop"]["print_status"]:
                    render.draw_status(ov, cfg, [
                        "view matrix NULL -> view_matrix offseti yanlis",
                        "cozum: python sigscan.py",
                    ])
                ov.end()
                time.sleep(frame_time)
                continue

            # ------------------ entity ------------------ #
            local, players = build_entities(mem, cfg)

            for p in players:
                p["screen"] = render.world_to_screen(m, p["pos"], width, height)
                aim_z = p["pos"][2] + (28.0 if cfg["aimbot"]["aim_head"] else 12.0)
                p["aim_screen"] = render.world_to_screen(
                    m, (p["pos"][0], p["pos"][1], aim_z), width, height)

            # ------------------ cizim ------------------ #
            ov.begin()
            if cfg["esp"]["enabled"]:
                for p in players:
                    render.draw_player(ov, cfg, m, p, width, height)
            if cfg["radar"]["enabled"]:
                render.draw_radar(ov, cfg, local, players, width, height)

            if cfg["loop"]["print_status"]:
                if frame_counter % 30 == 0:
                    ce_windows = ovl.other_cheat_windows()

                lines = [
                    f"ESP:{'ACIK' if cfg['esp']['enabled'] else 'KAPALI'}  "
                    f"Radar:{'ACIK' if cfg['radar']['enabled'] else 'KAPALI'}  "
                    f"Aimbot:{'ACIK' if cfg['aimbot']['enabled'] else 'KAPALI'} "
                    f"({AIM_KEYS[aim_key_index][1]})",
                    f"Oyuncu: {len(players)}   "
                    f"Local: {'var' if local else 'yok'}   "
                    f"Yetki: {mem.access_label}",
                ]
                if ce_windows:
                    lines.append("UYARI: " + ", ".join(ce_windows[:2])
                                 + " acik -> kick riski")
                render.draw_status(ov, cfg, lines)

            # ------------------ aimbot ------------------ #
            if cfg["aimbot"]["enabled"]:
                aim_run(cfg, players, width, height, aim_state)

            ov.end()

            dt = time.perf_counter() - t0
            if dt < frame_time:
                time.sleep(frame_time - dt)

    except KeyboardInterrupt:
        pass
    finally:
        ov.destroy()
        mem.detach()
        print("[*] Kapatildi.")


if __name__ == "__main__":
    main()