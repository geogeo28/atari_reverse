"""Differential tests for the roadside-object sprite draw-handler family @ 0x14620 / 0x1465c /
0x14664 (+ shared tail 0x14676) — disassembly-driven, verified vs the Musashi oracle.

Each entry is a register-glue routine that derives blit geometry from a per-object DESCRIPTOR record
(via A2) + view_flags / a parity flag, sets the per-row stride/mode word at A_blit_mode (0x18cb0),
and calls the already-verified leaf blit_objshift @ 0x14680. See BLIT_OBJSPRITE_SPEC.md.

The leaf reads real color_pairs image data (NOT staged) and sweeps A1 (src) / A0 (dst). We stage a
noise dst band wide enough for the derived sprite-top, a noise src arena mirroring an in-bounds
sprite stream, and the record bytes A2 points at; every register the chosen entry does not define is
poisoned (poison=True). Fields that would push A1/A0 outside the staged arenas are bounded, exactly
as test_blit_objshift bounds its stride — real records keep the pointers in bounds.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY_HI = 0x14620      # draw_obj_sprite_hi   (shared helper: mode-8 first blit + register rename)
ENTRY_DBL = 0x1465c     # draw_obj_handler_dbl (save colour, run 0x14620, restore colour, tail)
ENTRY_LO = 0x14664      # draw_obj_handler_lo  (dst from A6, src += per-parity word, tail)

# Named globals the code reads/writes (all inside the program's bss; already writable).
A_VIEW_FLAGS = 0x18c56
A_VIEW_PARITY = 0x18c60
A_BLIT_MODE = 0x18cb0

# Staged low-memory layout (clear of the program, which ends 0x1bcf8, and of the stack guard 0xff000).
DST_BASE = 0x60000      # a0/A6-relative dst base fed to the helper
DST_LO = 0x40000        # start of the staged dst noise region (covers the sprite-top reach below)
DST_SPAN = 0x30000      # covers DST_LO .. DST_BASE + column reach
SRC_BASE = 0x88000      # src sprite stream (a1); walks like blit_objshift's src
REC_BASE = 0x98000      # descriptor record base; the helper is passed rec+0xa

# Object stride / band width (= caller D2 = OBJD_WIDTH). suba.w #0xa0,a1 rewind + mulu height unit.
OBJD_WIDTH = 0xa0
# Leaf per-row a1 net advance is (8 - stride); the mode word is written by the code (8 or 0xa8), so
# for staging the src sweep we use the value the code will write, matching blit_objshift's model.
CELL_ADVANCE = 8
# A1 read-ahead per row: the leaf reads up to ~5 cells (0x28 bytes) forward of a1 each row.
ROW_READAHEAD = 0x28


def _sign16(v):
    v &= 0xffff
    return v - 0x10000 if v >= 0x8000 else v


def _src_band(rows_m1, mode_word):
    """Byte span [lo, hi) the leaf's a1 sweeps, given the mode word it will read per row (the stride).
    Mirrors test_blit_objshift._src_band so the staged noise covers every src read."""
    stride = _sign16(mode_word)
    rows = _sign16(rows_m1) + 1
    per_row = CELL_ADVANCE - stride
    a1 = SRC_BASE
    lo = hi = SRC_BASE
    for _ in range(max(rows, 1)):
        lo = min(lo, a1); hi = max(hi, a1 + ROW_READAHEAD)
        a1 += per_row
    lo = min(lo, a1); hi = max(hi, a1 + ROW_READAHEAD)
    return lo, hi


def _rec_bytes(rng, xoff, rows_view_bytes=None, src_off_pair=None):
    """Descriptor-record bytes. The helper is passed rec_cursor = rec+0xa (A2 on handler entry).
      rec+0x8   word  x screen offset re-read by move.w -(a2),d3  (0x14620)
      rec+0xc.. 4 bytes per-view rows-1 byte, indexed 4(a2,d7) with a2=rec+8  (0x14620)
      rec+0xc / rec+0xe  word per-parity src offset, 2(a2,d2) with a2=rec+0xa  (0x14664)
    The rows-1 table (0x14620) and the per-parity src-offset pair (0x14664) share rec+0xc but are
    read by different entries, never together — so exactly one is overlaid per record. Everything
    else is noise. Record spans rec .. rec+0x18."""
    rec = bytearray(rng.randrange(256) for _ in range(0x18))
    rec[0x8:0xa] = (xoff & 0xffff).to_bytes(2, "big")
    if rows_view_bytes is not None:                            # 0x14620 rows-1 table
        rec[0xc:0x10] = bytes(rows_view_bytes)
    if src_off_pair is not None:                               # 0x14664 per-parity src word pair
        rec[0xc:0xe] = (src_off_pair[0] & 0xffff).to_bytes(2, "big")
        rec[0xe:0x10] = (src_off_pair[1] & 0xffff).to_bytes(2, "big")
    return bytes(rec)


# ---- entry 0x14620 / 0x1465c: draw_obj_sprite_hi + draw_obj_handler_dbl ----

def _hi_pokes(seed, rows_seed, view, xoff, rows_byte):
    """Pokes for the mode-8 (0x14620) geometry. dst_top = DST_BASE - xoff + voff - width - height,
    height = width * rows_byte; the leaf then writes around dst_top + aligned_col. Stage a wide dst
    band so every write lands inside it, a src arena for the mode-8 sweep, view_flags, and the record.
    Both passes (0x1465c) share dst_top's band; the tail reuses the renamed a0/d0/d4."""
    rng = random.Random(seed)
    lo, hi = _src_band((rows_seed & 0xff00) | rows_byte, 0x8)   # mode-8 pass stride word = 8
    lo2, hi2 = _src_band((rows_seed & 0xff00) | rows_byte, 0xa8)  # tail pass stride word = 0xa8
    lo = min(lo, lo2); hi = max(hi, hi2)
    rows_view = [rng.randrange(0x20) for _ in range(4)]
    rows_view[view] = rows_byte
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_SPAN)),
        SRC_BASE - 0x2000: bytes(rng.randrange(256) for _ in range(0x2000)),  # room below SRC_BASE
        lo: bytes(rng.randrange(256) for _ in range(hi - lo)),
        REC_BASE: _rec_bytes(rng, xoff, rows_view_bytes=rows_view),
        A_VIEW_FLAGS: (view << 1).to_bytes(2, "big"),
    }


def _check_hi(entry, seed, x, color, rows_seed, voff, view, xoff, rows_byte):
    pokes = _hi_pokes(seed, rows_seed, view, xoff, rows_byte)
    rec_cursor = REC_BASE + 0xa
    regs = {
        "d0": x & 0xffff, "d1": color & 0xffff, "d2": OBJD_WIDTH,
        "d4": rows_seed & 0xffff, "d7": voff & 0xffff,
        "a0": DST_BASE, "a1": SRC_BASE, "a2": rec_cursor,
        "_pokes": pokes,
    }
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: _call_hi(lib, buf, entry, x, color, rows_seed, voff, rec_cursor),
        poison=True)
    assert not diffs, (f"entry={entry:#x} x={x:#x} col={color} rows_seed={rows_seed:#x} "
                       f"voff={voff:#x} view={view} xoff={xoff:#x} rows_byte={rows_byte}\n"
                       f"{report(diffs[:16])}")


def _call_hi(lib, buf, entry, x, color, rows_seed, voff, rec_cursor):
    args = (buf, x & 0xffff, color & 0xffff, OBJD_WIDTH, rows_seed & 0xffff, voff & 0xffff,
            DST_BASE, SRC_BASE, rec_cursor)
    if entry == ENTRY_HI:
        lib.g_draw_obj_sprite_hi(*args)
    else:
        lib.g_draw_obj_handler_dbl(*args)


# ---- entry 0x14664: draw_obj_handler_lo ----

def _lo_pokes(seed, rows_m1, parity_flag, src_off_pair):
    rng = random.Random(seed)
    parity = 2 & parity_flag
    src_off = _sign16(src_off_pair[parity // 2])
    lo, hi = _src_band(rows_m1, 0xa8)          # tail pass stride word = 0xa8
    lo += src_off; hi += src_off               # A1 starts at SRC_BASE + this per-parity offset
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_SPAN)),
        min(lo, SRC_BASE): bytes(rng.randrange(256)
                                 for _ in range(max(hi, SRC_BASE + ROW_READAHEAD) - min(lo, SRC_BASE))),
        REC_BASE: _rec_bytes(rng, 0, src_off_pair=src_off_pair),
        A_VIEW_PARITY: (parity_flag & 0xffff).to_bytes(2, "big"),
    }


def _check_lo(seed, x, color, rows_m1, parity_flag, src_off_pair):
    rec_cursor = REC_BASE + 0xa
    a6_base = DST_BASE - 0x3ac0             # so a0 = a6 + 0x3ac0 = DST_BASE (centre of the dst band)
    regs = {
        "d0": x & 0xffff, "d1": color & 0xffff, "d4": rows_m1 & 0xffff,
        "a1": SRC_BASE, "a2": rec_cursor, "a6": a6_base,
        "_pokes": _lo_pokes(seed, rows_m1, parity_flag, src_off_pair),
    }
    diffs, _ = differential(
        ENTRY_LO, regs,
        lambda lib, buf: lib.g_draw_obj_handler_lo(buf, x & 0xffff, color & 0xffff, rows_m1 & 0xffff,
                                                   SRC_BASE, rec_cursor, a6_base),
        poison=True)
    assert not diffs, (f"x={x:#x} col={color} rows_m1={rows_m1} parity={parity_flag:#x} "
                       f"src_off={src_off_pair}\n{report(diffs[:16])}")


# ctypes signatures.
harness._lib.g_draw_obj_sprite_hi.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 8
harness._lib.g_draw_obj_sprite_hi.restype = None
harness._lib.g_draw_obj_handler_dbl.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 8
harness._lib.g_draw_obj_handler_dbl.restype = None
harness._lib.g_draw_obj_handler_lo.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
harness._lib.g_draw_obj_handler_lo.restype = None


def test_hi_views():
    # 0x14620: every view selector (0..3) picks a different rows byte at rec+0xc+view.
    for view in range(4):
        _check_hi(ENTRY_HI, seed=view, x=0x84, color=5, rows_seed=3, voff=OBJD_WIDTH * 2,
                  view=view, xoff=0x40, rows_byte=2)


def test_hi_xoff_sign():
    # rec+8 x offset is signed (suba.w d3,a0); exercise both signs (dst_top stays in the band).
    for xoff in (0x0, 0x20, 0x60, -0x20 & 0xffff, -0x60 & 0xffff):
        _check_hi(ENTRY_HI, seed=0x100 + (xoff & 0xffff), x=0x60, color=8, rows_seed=4,
                  voff=OBJD_WIDTH, view=1, xoff=xoff, rows_byte=3)


def test_hi_rows_byte():
    # rows_byte drives the mulu height (a0 sprite-top offset) and the leaf's rows-1.
    for rows_byte in (0, 1, 2, 5, 0x10):
        _check_hi(ENTRY_HI, seed=0x200 + rows_byte, x=0x50, color=11, rows_seed=rows_byte,
                  voff=OBJD_WIDTH * 3, view=2, xoff=0x30, rows_byte=rows_byte)


def test_hi_rows_seed_high_byte():
    # move.b writes only D4's low byte; the high byte survives from rows_seed and the leaf reads
    # (int16)D4 as rows-1. A nonzero high byte therefore means thousands of sprite rows, which no
    # real record (word@rec+4 is a small rows count) ever produces and which would sweep A0/A1 far
    # outside any staged arena (and past max_insns). So the high-byte carry is faithfully modeled
    # (set_low_byte in the C) but cannot be image-verified in isolation; with a zero high byte the
    # carry is a no-op. We pin the zero-high-byte behaviour here across the low-byte range.
    for rows_byte in (0, 1, 2, 0x1f):
        _check_hi(ENTRY_HI, seed=0x280 + rows_byte, x=0x48, color=6, rows_seed=rows_byte,
                  voff=OBJD_WIDTH, view=0, xoff=0x20, rows_byte=rows_byte)


def test_hi_fine_x():
    # fine-x nibble in D0 selects the leaf's sub-pixel shift; sweep it (aligned col kept in BASE).
    for fine_x in range(16):
        x = (0x40 << 1) | fine_x
        _check_hi(ENTRY_HI, seed=0x300 + fine_x, x=x, color=fine_x & 0xf, rows_seed=2,
                  voff=OBJD_WIDTH, view=0, xoff=0x40, rows_byte=1)


def test_dbl_basic():
    # 0x1465c: colour-preserving double draw — mode 8 pass then mode 0xa8 tail reusing the rename.
    for view in range(4):
        _check_hi(ENTRY_DBL, seed=0x400 + view, x=0x84, color=7, rows_seed=3, voff=OBJD_WIDTH * 2,
                  view=view, xoff=0x40, rows_byte=2)


def test_lo_parity():
    # 0x14664: view_parity low bit selects the src word at rec+0xc (0) or rec+0xe (2).
    for flag in (0, 1, 2, 3):
        _check_lo(seed=0x500 + flag, x=0x50, color=9, rows_m1=2, parity_flag=flag,
                  src_off_pair=(0x40, -0x40 & 0xffff))


def test_lo_rows_and_x():
    for rows_m1 in (0, 1, 4, 0xf):
        for fine_x in (0, 7, 15):
            x = (0x40 << 1) | fine_x
            _check_lo(seed=0x600 + rows_m1 * 16 + fine_x, x=x, color=rows_m1 & 0xf, rows_m1=rows_m1,
                      parity_flag=0, src_off_pair=(0x20, 0x20))


def test_hi_fuzz():
    rng = random.Random(0xB0B)
    for i in range(600):
        entry = rng.choice([ENTRY_HI, ENTRY_DBL])
        view = rng.randrange(4)
        fine_x = rng.randrange(16)
        # aligned col kept in the leaf's BASE range so the sprite-top lands inside the dst band.
        col = rng.randrange(0, 0x98) & ~7
        x = (col << 1) | fine_x
        color = rng.randrange(16)
        rows_byte = rng.randrange(0, 0x14)                 # bounded so height*width stays in band
        rows_seed = rows_byte                              # high byte 0 (realistic; see high_byte test)
        voff = OBJD_WIDTH * rng.randrange(0, 4)
        xoff = rng.randrange(-0x60, 0x61) & 0xffff         # bounded x offset (stays in band)
        _check_hi(entry, seed=i, x=x, color=color, rows_seed=rows_seed, voff=voff, view=view,
                  xoff=xoff, rows_byte=rows_byte)


def test_lo_fuzz():
    rng = random.Random(0xC0C)
    for i in range(400):
        fine_x = rng.randrange(16)
        col = rng.randrange(0, 0x98) & ~7
        x = (col << 1) | fine_x
        color = rng.randrange(16)
        rows_m1 = rng.randrange(0, 0x14)
        flag = rng.randrange(4)
        # Per-parity src offsets bounded so a1 stays inside the staged src arena.
        pair = (rng.randint(-0x80, 0x80) & 0xffff, rng.randint(-0x80, 0x80) & 0xffff)
        _check_lo(seed=i, x=x, color=color, rows_m1=rows_m1, parity_flag=flag, src_off_pair=pair)
