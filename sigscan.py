# -*- coding: utf-8 -*-
"""
Offsetleri OTOMATIK bulur ve config.json'a yazar.

Kullanim:
    python sigscan.py            ikisini de ara
    python sigscan.py --entity   sadece entity_list
    python sigscan.py --matrix   sadece view_matrix
    python sigscan.py --dry      config'e yazma, sadece goster

Calisma mantigi: entity listesi head'i, icinde '.MDL' / 'MESH' string'ine
giden GECERLI bir pointer zinciri barindirir. Bu dogrulanabilir oldugu icin
tum adaylar taranip gercek zincir bulunur.
"""
import argparse
import array
import json
import os
import struct
import time

from memory import ZulaMemory, hx

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

IMAGE_SCN_MEM_WRITE = 0x80000000
PTR_MIN = 0x00010000
PTR_MAX = 0x7FFFFFFF

SCREEN_W = 1920
SCREEN_H = 1080


# ------------------------------------------------------------------ #
# PE / bolum okuma
# ------------------------------------------------------------------ #
def writable_sections(mem):
    hdr = mem.pm.read_bytes(mem.base, 0x1000)
    e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
    if hdr[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise RuntimeError("PE header okunamadi")
    coff = e_lfanew + 4
    num_sec = struct.unpack_from("<H", hdr, coff + 2)[0]
    opt_size = struct.unpack_from("<H", hdr, coff + 16)[0]
    sec_off = coff + 20 + opt_size

    out = []
    for i in range(num_sec):
        o = sec_off + i * 40
        name = hdr[o:o + 8].rstrip(b"\x00").decode("ascii", "ignore")
        vsize, va = struct.unpack_from("<II", hdr, o + 8)
        chars = struct.unpack_from("<I", hdr, o + 36)[0]
        if (chars & IMAGE_SCN_MEM_WRITE) and 0 < vsize < 32 * 1024 * 1024:
            out.append((name, va, vsize))
    return out


def load_sections(mem):
    secs = []
    for name, va, vsize in writable_sections(mem):
        try:
            buf = mem.pm.read_bytes(mem.base + va, vsize)
        except Exception:
            continue
        secs.append((name, mem.base + va, buf))
        print(f"  [*] bolum {name:<8} 0x{vsize:X} byte")
    return secs


# ------------------------------------------------------------------ #
# entity listesi arama
# ------------------------------------------------------------------ #
def score_head(mem, head_addr, max_walk=8):
    """
    head_addr bir dword tutuyor. Zinciri yuruyup kac gecerli
    model ismi buldugumuzu sayar.
    """
    try:
        node = mem.pm.read_uint(head_addr)
        if not (PTR_MIN < node < PTR_MAX):
            return 0
        score = 0
        for _ in range(max_walk):
            node = mem.pm.read_uint(node + 0x4)
            if not (PTR_MIN < node < PTR_MAX) or (node % 4):
                break
            sptr = mem.pm.read_uint(node + 0xC)
            if not (PTR_MIN < sptr < PTR_MAX):
                break
            raw = mem.pm.read_bytes(sptr, 32)
            z = raw.find(b"\x00")
            nm = raw[:z if z != -1 else 32].decode("ascii", "ignore").upper()
            if ".MDL" in nm or "MESH" in nm or "SPRITE" in nm or nm.endswith(".M"):
                score += 1
            else:
                break
        return score
    except Exception:
        return 0


def find_entity_list(mem):
    print("\n[*] entity_list araniyor (dogrulanmis tarama)...")
    best_score, best_off = 0, None
    tried = 0
    t0 = time.time()

    for _name, sec_addr, buf in load_sections(mem):
        n = len(buf) - (len(buf) % 4)
        arr = array.array("I")
        arr.frombytes(buf[:n])

        for i, v in enumerate(arr):
            if not (PTR_MIN < v < PTR_MAX) or (v % 4):
                continue
            tried += 1
            addr = sec_addr + i * 4
            sc = score_head(mem, addr)
            if sc > best_score:
                best_score = sc
                best_off = addr - mem.base
                print(f"  [+] acknex.dll+0x{best_off:X}   skor={sc}")
            if sc >= 6:
                print(f"  [=] {time.time() - t0:.1f}s, {tried} aday denendi")
                return best_off, best_score

    print(f"  [=] {time.time() - t0:.1f}s, {tried} aday denendi")
    return best_off, best_score


# ------------------------------------------------------------------ #
# view matrix arama
# ------------------------------------------------------------------ #
def project(m, p, w, h):
    x, y, z = p[0], p[2], p[1]
    cx = x * m[0] + y * m[4] + z * m[8] + m[12]
    cy = x * m[1] + y * m[5] + z * m[9] + m[13]
    cw = x * m[3] + y * m[7] + z * m[11] + m[15]
    if cw < 0.1:
        return None
    return (cx / cw + 1.0) * 0.5 * w, (1.0 - cy / cw) * 0.5 * h


def matrix_ok(m, samples, w, h):
    if abs(m[15]) < 1e-6 or abs(m[0]) < 1e-6 or abs(m[5]) < 1e-6:
        return False
    hits = 0
    for p in samples:
        r = project(m, p, w, h)
        if r is None:
            continue
        sx, sy = r
        if -2 * w <= sx <= 3 * w and -2 * h <= sy <= 3 * h:
            hits += 1
    return hits >= max(1, len(samples) - 1)


def sample_positions(mem, head_off):
    """Bulunan entity zincirinden ornek dunya pozisyonlari topla."""
    off_pos = hx(mem.cfg["offsets"]["entity_position"])
    samples = []
    try:
        node = mem.pm.read_uint(mem.base + head_off)
        for _ in range(64):
            node = mem.pm.read_uint(node + 0x4)
            if not node:
                break
            p = struct.unpack("<3f", mem.pm.read_bytes(node + off_pos, 12))
            if abs(p[0]) > 1.0 or abs(p[1]) > 1.0:
                samples.append(p)
            if len(samples) >= 4:
                break
    except Exception:
        pass
    return samples


def find_view_matrix(mem, samples):
    print("\n[*] view_matrix araniyor...")
    w, h = SCREEN_W, SCREEN_H
    t0 = time.time()
    checked = 0

    for _name, sec_addr, buf in load_sections(mem):
        n = len(buf) - (len(buf) % 4)
        arr = array.array("f")
        arr.frombytes(buf[:n])
        words = array.array("I")
        words.frombytes(buf[:n])

        for i in range(0, len(arr) - 16):
            if arr[i + 15] == 0.0:
                continue
            checked += 1

            # mod A: matris dogrudan bu adreste
            if matrix_ok(arr[i:i + 16], samples, w, h):
                off = (sec_addr + i * 4) - mem.base
                print(f"  [+] direct  acknex.dll+0x{off:X}  ({time.time() - t0:.1f}s)")
                return off, False

            # mod B: bu adreste matrise pointer var
            v = words[i]
            if PTR_MIN < v < PTR_MAX and v % 4 == 0:
                try:
                    m2 = struct.unpack("<16f", mem.pm.read_bytes(v, 64))
                except Exception:
                    continue
                if matrix_ok(m2, samples, w, h):
                    off = (sec_addr + i * 4) - mem.base
                    print(f"  [+] pointer acknex.dll+0x{off:X}  ({time.time() - t0:.1f}s)")
                    return off, True

    print(f"  [=] {time.time() - t0:.1f}s, {checked} aday denendi")
    return None, None


# ------------------------------------------------------------------ #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity", action="store_true")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    only_one = args.entity or args.matrix
    do_entity = args.entity or not only_one
    do_matrix = args.matrix or not only_one

    with open(CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    mem = ZulaMemory(cfg)
    mem.attach()
    print(f"[+] PID={mem.pid}  base=0x{mem.base:X}  yetki={mem.access_label}")

    changed = False

    if do_entity:
        off, sc = find_entity_list(mem)
        if off is not None and sc >= 2:
            cfg["offsets"]["entity_list"] = hex(off)
            changed = True
            print(f"[OK] entity_list = {hex(off)}  (skor {sc})")
        else:
            print("[!] entity_list bulunamadi - oyun bir macta mi?")

    if do_matrix:
        samples = []
        try:
            head_off = hx(cfg["offsets"]["entity_list"])
            samples = sample_positions(mem, head_off)
            print(f"  [*] {len(samples)} ornek pozisyon alindi")
        except Exception:
            pass

        if samples:
            off, is_ptr = find_view_matrix(mem, samples)
            if off is not None:
                cfg["offsets"]["view_matrix"] = hex(off)
                cfg["offsets"]["view_matrix_is_pointer"] = is_ptr
                changed = True
                print(f"[OK] view_matrix = {hex(off)}  (pointer={is_ptr})")
            else:
                print("[!] view_matrix bulunamadi")
        else:
            print("[!] ornek pozisyon yok, once entity_list gerekli")

    if changed and not args.dry:
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("\n[+] config.json guncellendi")
    else:
        print("\n[i] config.json'a yazilmadi")


if __name__ == "__main__":
    main()
    main()