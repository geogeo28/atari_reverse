"""course_format.py — the on-disk layout of BuggyBoy's COURSES.DAT.

This is the *single source of truth* for the editor's view of the file. Every
constant here is transcribed from the verified C reconstruction and tagged with
the C symbol / source file it mirrors, so the two can be diffed by hand (and,
later, pinned equal by a test):

  - memory map ............ src/os.c  g_main   (mem_base / buf_a / buf_b offsets)
  - dashboard track map ... src/results.c  g_init_leg_dash
  - scroll table .......... src/road.c  g_set_screen_offset
  - object markers ........ src/gameplay.c  g_init_leg  (phase 10/11)
  - course-record stream .. src/game_update.c  game_update_course_advance

The whole file is loaded at `mem_base`; `buf_a = mem_base + 0x1900`. So a
buf_a-relative offset X is file offset (BUF_A_OFF + X).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- global memory map (src/os.c g_main) ----
BUF_A_OFF = 0x1900          # buf_a  = mem_base + 0x1900
BUF_B_OFF = 0xF660          # buf_b  = mem_base + 0xf660 (== COURSES.DAT size: file ends here)
LEG_COUNT = 5               # legs 0..4 (STATUS.md: "5 legs")

# ---- dashboard track-map bitmaps (src/results.c g_init_leg_dash) ----
DASH_LEG_STRIDE = 0x500     # per-leg raw block = DASH_ROWS * DASH_SRC_STRIDE
DASH_ROWS = 40
DASH_SRC_STRIDE = 0x20      # raw source bytes per row (8 groups x 4 bytes)
# The 5 bitmaps occupy file [0, LEG_COUNT*DASH_LEG_STRIDE) == [0, 0x1900) == up to buf_a.

# ---- per-leg course-record stream (src/game_update.c game_update_course_advance) ----
LEG_STRIDE = 0x2000         # GU_LEG_STRIDE: bytes per leg's course block
COURSE_STREAM = 0x5CE0      # GU_COURSE_STREAM: buf_a + leg*LEG_STRIDE + this = stream anchor
COURSE_MASK_BASE = 0x5D48   # GU_COURSE_MASK_BASE: per-course collision-flag longs
RECORD_BYTES = 8            # read_pos advances by 8 each pull
READ_POS_WRAP = 0x1FF8      # read_pos = (read_pos + 8) & this  (== LEG_STRIDE - 8)

# select-mask sub-run expansion codes (game_update: a control byte expands to a 2-word run)
ANIM_EXPAND = {0x0D: (0x0E, 0x0F), 0x10: (0x11, 0x12), 0x13: (0x14, 0x15), 0x16: (0x17, 0x18)}
SELECT_BITS = 15            # mask bits 0xe..0 drive the payload unpack

# ---- scroll table (src/road.c g_set_screen_offset) ----
SCROLL_TABLE_STRIDE = 0x10  # buf_a + leg*0x10: 16-byte per-leg road-band scroll frames
SCROLL_BAND_BYTES = 0x1900  # selected byte * this = buf_c road-scroll offset

# ---- object / palette selector + record table (src/gameplay.c g_init_leg phase 11) ----
OBJDISP_SEL_OFF = 0x50      # buf_a + this + leg*0x20: selector byte
OBJDISP_TBL_OFF = 0xF2      # buf_a + this + (selector<<4): the record source

# ---- roadside-object marker records (src/gameplay.c g_init_leg phase 10) ----
MARKER_SRC_BASE = 0x5CE0    # buf_a + this + leg*LEG_STRIDE (shares the stream anchor)
MARKER_RECORDS = 14
MARKER_SRC_STRIDE = 8


def be16(data: bytes, off: int) -> int:
    return (data[off] << 8) | data[off + 1]


def be32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "big")


def buf_a(off: int) -> int:
    """Translate a buf_a-relative offset to a COURSES.DAT file offset."""
    return BUF_A_OFF + off


def leg_stream_anchor(leg: int) -> int:
    """File offset of a leg's course-stream anchor (records are read *backward* from here)."""
    return buf_a(leg * LEG_STRIDE + COURSE_STREAM)


@dataclass
class CourseRecord:
    """One 8-byte course record, decoded the way game_update pulls it.

    The engine reads records backward from the leg anchor: pull k (1-based) sits
    at anchor - 8*k. `index` is k-1 (play order). The payload is the popcount of
    the low-15 select-mask bits, read forward from file_off+3 (mirrors the C).
    """
    index: int                 # 0-based play order
    file_off: int              # absolute COURSES.DAT offset of this record
    select_mask: int           # word @ +0
    control: int               # byte @ +2
    marker: int                # word @ +6
    payload: bytes = b""       # popcount(select_mask & 0x7fff) bytes from +3

    @property
    def row_count(self) -> int:
        """Scanline rows this record's geometry holds (control & 0xf8, stepped by 8)."""
        return (self.control & 0xF8) >> 3

    @property
    def decay_seed(self) -> int:
        """Marker-decay seed: (control & 7) - 3  (signed)."""
        return (self.control & 7) - 3

    @property
    def marker_is_event(self) -> bool:
        """Marker word with the sign bit set is a course event (checkpoint/collision/...)."""
        return bool(self.marker & 0x8000)

    def classify_marker(self) -> str:
        """Rough marker classification, mirroring game_update's mask tests."""
        m = self.marker
        if not (m & 0x8000):
            return "none"
        if (m & 0xF01E) == 0xF012:
            return "checkpoint?"      # &0x4f cleanup branch
        if (m & 0xF01E) == 0xF000:
            return "collision?"       # &0x6f cleanup branch
        if (m & 0x6000) == 0:
            return "score/msg?"       # &0x7f cleanup branch
        return "event"


def decode_leg(data: bytes, leg: int, max_records: int = 256) -> list[CourseRecord]:
    """Decode a leg's course-record stream (backward from the anchor) into records.

    Stops at max_records or when it walks below the leg block. This mirrors
    game_update's pull loop; it does not model the runtime row-count gating
    (that decides *when* the next record is pulled, not the record contents).
    """
    anchor = leg_stream_anchor(leg)
    low_bound = anchor - LEG_STRIDE           # backward window is one leg block
    records: list[CourseRecord] = []
    for k in range(1, max_records + 1):
        off = anchor - RECORD_BYTES * k
        if off < low_bound or off < 0:
            break
        mask = be16(data, off)
        control = data[off + 2]
        marker = be16(data, off + 6)
        # payload: one byte per set bit of the low-15 mask, forward from off+3
        nbytes = bin(mask & 0x7FFF).count("1")
        payload = bytes(data[off + 3: off + 3 + nbytes])
        records.append(CourseRecord(k - 1, off, mask, control, marker, payload))
    return records
