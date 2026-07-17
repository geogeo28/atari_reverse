"""course_file.py — a mutable, patch-in-place editing model over COURSES.DAT.

Design principle: we never re-serialize the whole file from a parsed model (the
format is reverse-engineered and has quirks — e.g. a popcount-4 record whose 4th
payload byte overlaps the +6 marker word). Instead we keep the original bytes and
mutate only the specific fields the user edits, at their known offsets. That makes
an unedited round-trip byte-identical by construction, and keeps every edit auditable.

Editing surface (leg-scoped, indexed by play-order record k):
  - set_marker(leg, k, word)   roadside-object / event marker (+6 word)
  - set_control(leg, k, rows, decay)   rows held + marker-decay seed (+2)
  - set_mask(leg, k, mask)     15-bit select mask (+0 word)
  - set_payload_byte(leg, k, i, value)   one payload byte (+3+i)
  - set_scroll(leg, frame, band)   the 16-entry road-band scroll table
Higher-level helpers build on these (e.g. paint_marker_run for a continuous feature).

save() refuses to clobber without a backup (CLAUDE.md §8): it writes <path>.bak first.
"""
from __future__ import annotations

from pathlib import Path

import course_format as cf


class CourseFile:
    def __init__(self, data: bytes, path: Path | None = None):
        self.data = bytearray(data)
        self.path = path

    @classmethod
    def load(cls, path: str | Path) -> "CourseFile":
        p = Path(path)
        return cls(p.read_bytes(), p)

    # ---- record address helpers ----
    def _rec_off(self, leg: int, k: int) -> int:
        """File offset of leg's play-order record k (k=0 is the first pulled)."""
        off = cf.leg_stream_anchor(leg) - cf.RECORD_BYTES * (k + 1)
        if not (0 <= off <= len(self.data) - cf.RECORD_BYTES):
            raise IndexError(f"record {k} of leg {leg} is out of range (off 0x{off:x})")
        return off

    # ---- byte helpers ----
    def _wr16(self, off: int, value: int) -> None:
        self.data[off] = (value >> 8) & 0xFF
        self.data[off + 1] = value & 0xFF

    def records(self, leg: int, count: int = 256) -> list[cf.CourseRecord]:
        """A decoded read-only view of the leg (delegates to the shared decoder)."""
        return cf.decode_leg(bytes(self.data), leg, max_records=count)

    # ---- field edits ----
    def set_marker(self, leg: int, k: int, word: int) -> None:
        self._wr16(self._rec_off(leg, k) + 6, word & 0xFFFF)

    def set_mask(self, leg: int, k: int, mask: int) -> None:
        self._wr16(self._rec_off(leg, k), mask & 0xFFFF)

    def set_control(self, leg: int, k: int, rows: int, decay: int) -> None:
        """rows (1..31) held by this record; decay seed (-3..+4) -> control byte."""
        ctl = ((rows << 3) & 0xF8) | ((decay + 3) & 7)
        self.data[self._rec_off(leg, k) + 2] = ctl

    def set_payload_byte(self, leg: int, k: int, i: int, value: int) -> None:
        if not 0 <= i <= 4:
            raise ValueError("payload byte index 0..4")
        self.data[self._rec_off(leg, k) + 3 + i] = value & 0xFF

    def set_scroll(self, leg: int, frame: int, band: int) -> None:
        if not 0 <= frame < cf.SCROLL_TABLE_STRIDE:
            raise ValueError("scroll frame 0..15")
        self.data[cf.buf_a(leg * cf.SCROLL_TABLE_STRIDE) + frame] = band & 0xFF

    # ---- higher-level edit ----
    def paint_marker_run(self, leg: int, k0: int, length: int, word: int) -> None:
        """Place a continuous roadside feature: identical marker across `length` records."""
        for k in range(k0, k0 + length):
            self.set_marker(leg, k, word)

    # ---- dashboard track-map pixels (the per-leg course shape; plane1/w1) ----
    MAP_W = 128
    MAP_H = cf.DASH_ROWS

    def _map_w1_off(self, leg: int, x: int, y: int) -> tuple[int, int]:
        """(file offset of the w1 word, bit index) for track pixel (x,y)."""
        if not (0 <= x < self.MAP_W and 0 <= y < self.MAP_H):
            raise IndexError(f"map pixel ({x},{y}) out of range")
        off = leg * cf.DASH_LEG_STRIDE + y * cf.DASH_SRC_STRIDE + (x // 16) * 4 + 2
        return off, 15 - (x % 16)

    def get_map_pixel(self, leg: int, x: int, y: int) -> int:
        off, bit = self._map_w1_off(leg, x, y)
        return (cf.be16(bytes(self.data), off) >> bit) & 1

    def set_map_pixel(self, leg: int, x: int, y: int, on: bool) -> None:
        """Set/clear a track pixel (plane1/w1 only; scenery plane w0 is left untouched)."""
        off, bit = self._map_w1_off(leg, x, y)
        w1 = cf.be16(bytes(self.data), off)
        w1 = (w1 | (1 << bit)) if on else (w1 & ~(1 << bit))
        self._wr16(off, w1)

    def toggle_map_pixel(self, leg: int, x: int, y: int) -> int:
        on = not self.get_map_pixel(leg, x, y)
        self.set_map_pixel(leg, x, y, on)
        return int(on)

    # ---- persistence ----
    def save(self, path: str | Path | None = None) -> Path:
        dst = Path(path) if path is not None else self.path
        if dst is None:
            raise ValueError("no path to save to")
        if dst.exists():
            backup = dst.with_suffix(dst.suffix + ".bak")
            if not backup.exists():                 # keep the pristine original
                backup.write_bytes(dst.read_bytes())
        dst.write_bytes(bytes(self.data))
        return dst
