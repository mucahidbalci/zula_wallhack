# -*- coding: utf-8 -*-
"""
Dunya -> ekran donusumu, ESP ve radar cizimi.

Zula Z-up motor (x, y yatay / z yukari). D3D row-vector matrisi kullanilir.
Gorunurluk (raycast) kontrolu YOK -> duvar arkasindaki dusman da cizilir.
"""
import math

COLORS = {
    "enemy": "#FF3B30",
    "team": "#30D158",
    "local": "#64D2FF",
    "radar_bg": "#0A0A0A",
    "radar_border": "#8E8E93",
    "radar_enemy": "#FF3B30",
    "radar_team": "#30D158",
    "radar_local": "#64D2FF",
}


def world_to_screen(m, pos_engine, width, height):
    """pos_engine (x, y, z) z-up -> ekran (sx, sy) veya None."""
    if m is None or pos_engine is None:
        return None
    x, y, z = pos_engine[0], pos_engine[2], pos_engine[1]

    clip_x = x * m[0] + y * m[4] + z * m[8] + m[12]
    clip_y = x * m[1] + y * m[5] + z * m[9] + m[13]
    clip_w = x * m[3] + y * m[7] + z * m[11] + m[15]

    if clip_w < 0.1:
        return None

    ndc_x = clip_x / clip_w
    ndc_y = clip_y / clip_w

    return (ndc_x + 1.0) * 0.5 * width, (1.0 - ndc_y) * 0.5 * height


def dist3(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def draw_player(ov, cfg, m, ent, width, height):
    esp = cfg["esp"]
    pos = ent["pos"]

    head = world_to_screen(m, (pos[0], pos[1], pos[2] + float(esp["head_offset"])),
                           width, height)
    feet = world_to_screen(m, (pos[0], pos[1], pos[2] + float(esp["feet_offset"])),
                           width, height)
    if not head or not feet:
        return

    box_h = feet[1] - head[1]
    if box_h <= 2 or box_h > height * 3:
        return
    box_w = box_h / float(esp["box_width_divisor"])

    x1 = head[0] - box_w / 2.0
    x2 = head[0] + box_w / 2.0
    y1 = head[1]
    y2 = feet[1]

    if x2 < 0 or x1 > width or y2 < 0 or y1 > height:   # ekran disi culling
        return

    color = COLORS["enemy"] if ent["team"] == "enemy" else COLORS["team"]
    if ent["local"]:
        color = COLORS["local"]

    if esp.get("box", True):
        if esp.get("corner_box", False):
            ov.corner_box(x1, y1, x2, y2, color)
        else:
            ov.box(x1, y1, x2, y2, color)

    if esp.get("snapline", False):
        ov.line(width / 2, height, head[0], y2, color, 1)

    label_y = y1 - 4
    if esp.get("name", True):
        ov.text(head[0], label_y, ent["name"], color, size=int(esp["font_size"]))
        label_y -= 14

    if esp.get("distance", True):
        meters = ent["dist"] * float(cfg["units"]["unit_to_meter"])
        ov.text(head[0], label_y, f"{meters:.0f}m", color,
                size=int(esp["font_size"]) - 1)
        label_y -= 13

    if esp.get("health_bar", True) and ent.get("health") is not None:
        hp = max(0, min(100, int(ent["health"])))
        bar_x = x1 - 6
        ov.rect_fill(bar_x, y2, bar_x + 3, y1, "#3A3A3C")
        filled = (y2 - y1) * (hp / 100.0)
        bar_color = "#30D158" if hp > 50 else ("#FFD60A" if hp > 25 else "#FF3B30")
        ov.rect_fill(bar_x, y2 - filled, bar_x + 3, y2, bar_color)
        ov.text(bar_x - 2, y2, str(hp), "#FFFFFF", size=9, anchor="e")

    if esp.get("armor_text", False) and ent.get("armor") is not None:
        ov.text(x2 + 4, y2, f"AP {int(ent['armor'])}", "#64D2FF", size=9, anchor="w")


def draw_radar(ov, cfg, local, players, width, height):
    r_cfg = cfg["radar"]
    size = int(r_cfg["size"])
    margin = int(r_cfg["margin"])
    cx = width - margin - size // 2
    cy = height - margin - size // 2
    r = size // 2

    ov.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=COLORS["radar_border"], fill=COLORS["radar_bg"])
    ov.line(cx, cy - r, cx, cy + r, "#2C2C2E", 1)
    ov.line(cx - r, cy, cx + r, cy, "#2C2C2E", 1)

    if local is None:
        return

    yaw = math.radians(local["yaw"])
    s = math.sin(yaw)
    c = math.cos(yaw)
    scale = float(r_cfg["scale"])
    rng = float(r_cfg["range"])

    for p in players:
        dx = p["pos"][0] - local["pos"][0]
        dy = p["pos"][1] - local["pos"][1]
        if math.hypot(dx, dy) > rng:
            continue
        rx = (dx * s - dy * c) * scale
        ry = -(dx * c + dy * s) * scale
        if r_cfg.get("flip_x"):
            rx = -rx
        if r_cfg.get("flip_y"):
            ry = -ry
        px = cx + rx
        py = cy + ry
        if not (cx - r <= px <= cx + r and cy - r <= py <= cy + r):
            continue
        color = COLORS["radar_enemy"] if p["team"] == "enemy" else COLORS["radar_team"]
        ov.circle(px, py, 3, color)

    ov.circle(cx, cy, 3, COLORS["radar_local"])


def draw_status(ov, cfg, lines):
    y = 12
    for line in lines:
        ov.text(12, y, line, "#FFFFFF", size=11, anchor="nw", bold=False)
        y += 16