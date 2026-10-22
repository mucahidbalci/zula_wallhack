# -*- coding: utf-8 -*-
"""
Offset avlama yardimcisi. Oyun acik ve bir MAC ICINDE calistir.
Can / zirh gibi oyun ici degerleri bulmak icin Cheat Engine ile kullan.
"""
import json
import os
import struct
import time

from memory import ZulaMemory, hx

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def main():
    with open(CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    mem = ZulaMemory(cfg)
    mem.attach()
    print(f"[+] PID={mem.pid}   base=0x{mem.base:X}   yetki={mem.access_label}\n")

    off_handle = hx(cfg["offsets"]["entity_handle"])
    off_pos = hx(cfg["offsets"]["entity_position"])
    off_ang = hx(cfg["offsets"]["entity_angles"])

    dumped = set()

    try:
        while True:
            mem.begin_frame()
            head = mem.entity_head()
            m = mem.view_matrix()

            print("=" * 78)
            print(f"entity_head = 0x{head:X}   "
                  f"(acknex.dll + {cfg['offsets']['entity_list']})")
            print(f"view matrix = {'OK' if m else 'NULL'}   "
                  f"(acknex.dll + {cfg['offsets']['view_matrix']})")
            print("-" * 78)

            if head == 0:
                print(">>> entity_list offseti YANLIS. 'python sigscan.py' calistir.")
                time.sleep(2.0)
                continue

            count = 0
            for ent in mem.iter_entities():
                hptr = mem.u32(ent + off_handle)
                if not hptr:
                    continue
                name = mem.cstr(hptr, 40)
                if not name or ("CHAR_" not in name and "FPS_" not in name):
                    continue

                pos = mem.vec3(ent + off_pos)
                ang = mem.vec3(ent + off_ang)
                print(f"\nent = 0x{ent:X}   name = '{name}'")
                print(f"  pos @ +0x{off_pos:X} = "
                      f"{tuple(round(v, 2) for v in pos) if pos else None}")
                print(f"  ang @ +0x{off_ang:X} = "
                      f"{tuple(round(v, 2) for v in ang) if ang else None}")

                if ent not in dumped:
                    dumped.add(ent)
                    print("  --- ilk 0x200 byte (int | float) ---")
                    for row in range(0, 0x200, 0x10):
                        try:
                            b = mem.pm.read_bytes(ent + row, 16)
                        except Exception:
                            break
                        ints = [int.from_bytes(b[i:i + 4], "little")
                                for i in range(0, 16, 4)]
                        flts = [round(struct.unpack("<f", b[i:i + 4])[0], 2)
                                for i in range(0, 16, 4)]
                        print(f"   +0x{row:03X}  "
                              + " ".join(f"{v:>10d}" for v in ints)
                              + " | "
                              + " ".join(f"{v:>8.2f}" for v in flts))
                count += 1

            print(f"\n[toplam {count} oyuncu entity]")
            time.sleep(2.0)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()