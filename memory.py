# -*- coding: utf-8 -*-
"""
Zula / Acknex A8 bellek okuma katmani.

UYARI 1: Zula 32-bit process. Tum pointer'lar 4 byte -> read_uint kullan,
         read_longlong DEGIL.
UYARI 2: Anti-cheat ObRegisterCallbacks ile yetki kirpabilir. Bu yuzden
         PROCESS_ALL_ACCESS yerine once en az yetkiyle acmayi deniyoruz.
         Sadece okuma yaptigimiz icin VM_READ yeterli, yazma yok.
"""
import ctypes
import struct

import pymem
import pymem.pattern
import pymem.process

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Sirayla denenecek yetki maskeleri. Az yetki = daha az suphe + daha az red.
ACCESS_CANDIDATES = [
    (0x1F0FFF, "PROCESS_ALL_ACCESS"),
    (0x0410,   "VM_READ|QUERY_INFORMATION"),
    (0x1010,   "VM_READ|QUERY_LIMITED"),
    (0x0010,   "VM_READ (son care)"),
]


def hx(v, default=0):
    """'0x3DC' gibi config stringlerini int'e cevirir."""
    if v is None:
        return default
    if isinstance(v, int):
        return v
    return int(str(v), 16)


class ZulaMemory:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pm = None
        self.base = 0
        self.pid = 0
        self.access_label = "?"
        self.module_name = cfg["module_name"]
        self._cache = {}

    # ------------------------------------------------------------------ #
    # baglanti
    # ------------------------------------------------------------------ #
    def find_pid(self):
        entry = pymem.process.process_from_name(self.cfg["process_name"])
        if entry is None:
            raise RuntimeError(f"{self.cfg['process_name']} bulunamadi")
        return entry.th32ProcessID

    def _open_minimal(self, pid):
        for mask, label in ACCESS_CANDIDATES:
            h = _k32.OpenProcess(mask, False, pid)
            if h:
                return h, label
        raise RuntimeError(f"OpenProcess basarisiz (err={ctypes.get_last_error()})")

    def attach(self):
        self.detach()
        pid = self.find_pid()
        handle, label = self._open_minimal(pid)

        pm = pymem.Pymem()          # handle'i kendimiz verecegiz
        pm.process_id = pid
        pm.process_handle = handle

        mod = pymem.process.module_from_name(handle, self.module_name)
        if mod is None:
            raise RuntimeError(f"{self.module_name} modulu bulunamadi")

        self.pm = pm
        self.pid = pid
        self.access_label = label
        self.base = mod.lpBaseOfDll
        return self.base

    def detach(self):
        try:
            if self.pm is not None and self.pm.process_handle:
                _k32.CloseHandle(self.pm.process_handle)
        except Exception:
            pass
        self.pm = None

    def is_alive(self):
        try:
            if self.pm is None:
                return False
            return pymem.process.module_from_name(
                self.pm.process_handle, self.module_name) is not None
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # kare basi cache
    # ------------------------------------------------------------------ #
    def begin_frame(self):
        self._cache.clear()

    def _c(self, key, reader, addr):
        if key in self._cache:
            return self._cache[key]
        try:
            v = reader(addr)
        except Exception:
            v = None
        self._cache[key] = v
        return v

    # ------------------------------------------------------------------ #
    # temel okumalar
    # ------------------------------------------------------------------ #
    def u8(self, addr):
        return self._c(("u8", addr), self.pm.read_uchar, addr)

    def i32(self, addr):
        return self._c(("i32", addr), self.pm.read_int, addr)

    def u32(self, addr):
        return self._c(("u32", addr), self.pm.read_uint, addr)

    def f32(self, addr):
        return self._c(("f32", addr), self.pm.read_float, addr)

    def vec3(self, addr):
        if ("v3", addr) in self._cache:
            return self._cache[("v3", addr)]
        try:
            v = struct.unpack("<3f", self.pm.read_bytes(addr, 12))
        except Exception:
            v = None
        self._cache[("v3", addr)] = v
        return v

    def matrix16(self, addr):
        if ("m16", addr) in self._cache:
            return self._cache[("m16", addr)]
        try:
            v = struct.unpack("<16f", self.pm.read_bytes(addr, 64))
        except Exception:
            v = None
        self._cache[("m16", addr)] = v
        return v

    def cstr(self, addr, maxlen=64):
        if not addr:
            return ""
        try:
            raw = self.pm.read_bytes(addr, maxlen)
        except Exception:
            return ""
        z = raw.find(b"\x00")
        if z != -1:
            raw = raw[:z]
        return raw.decode("ascii", errors="ignore")

    # ------------------------------------------------------------------ #
    # entity listesi:  head = *(acknex.dll + entity_list)
    #                  node = *(node + entity_next)
    # ------------------------------------------------------------------ #
    def entity_head(self):
        off = hx(self.cfg["offsets"]["entity_list"])
        return self.u32(self.base + off) or 0

    def iter_entities(self):
        off_next = hx(self.cfg["offsets"]["entity_next"], 0x4)
        node = self.entity_head()
        limit = int(self.cfg["entity"]["max_iterations"])
        for _ in range(limit):
            if not node:
                return
            node = self.u32(node + off_next) or 0
            if not node:
                return
            yield node

    # ------------------------------------------------------------------ #
    # view matrix
    # ------------------------------------------------------------------ #
    def view_matrix(self):
        addr = self.base + hx(self.cfg["offsets"]["view_matrix"])
        if self.cfg["offsets"].get("view_matrix_is_pointer", True):
            addr = self.u32(addr) or 0
        if not addr:
            return None
        m = self.matrix16(addr)
        if not m or abs(m[15]) < 1e-6:
            return None
        return m

    # ------------------------------------------------------------------ #
    # AOB tarama (pymem desenleri regex'tir, '.' joker karakterdir)
    # ------------------------------------------------------------------ #
    def scan(self, pattern: bytes):
        try:
            return pymem.pattern.pattern_scan_module(
                self.pm.process_handle, self.module_name, pattern)
        except Exception:
            return None