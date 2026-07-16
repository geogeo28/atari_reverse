"""Differential test for draw_object_list @ 0x1306e — the roadside-object display-list dispatcher.

Two nested loops walk the object list; each object's flag word (a3 stream) gates an optional SPECIAL
pass (record @ buf_a+0x21d0+d6) and a NORMAL pass keyed on the flag's low 6 bits (type -> record @
buf_a+0x8a0+type*0xd0+d6). Each record carries colour, a buf_c-relative src long, rows-1, a vertical
seed byte, the obj_type_jumptable index, and per-object x/dst offsets. The resolved handler is one of:
the objsprite engine (t1/t2/t4/w88), the t4+t1 stub, or the handler_lo blit families (0x98 / 0x90).

The test stages: buf_a (pointer @ 0x18c00) + per-type records, buf_c (pointer @ 0x18c08) + sprite-src
noise, the a5 list stream @ 0x16c06 and a3 flag stream @ 0x18ebc, the a4 x-offset word @ 0x18f26, the
draw buffer (a6), and the control words (view_flags/view_parity/bonus_timer/obj_scan_off). It drives one
object per run (the other 14 flagged type-0 = skipped) so each handler + jump-table index is isolated,
then a fuzz mixes them. color_pairs @ 0x15afa + obj_type_jumptable @ 0x13144 are real image data.
Whole-image diff vs the Musashi oracle (poisoned).
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1306e

# Fixed image-address streams the dispatcher reads.
A_LIST_BASE = 0x16c06        # a5 base (before += word@obj_scan_off)
A_FLAGS = 0x18ebc            # a3 base
A_XOFF_TBL = 0x18f26         # a4 base
A_OBJ_SCAN_OFF = 0x18c58
A_BUF_A_PTR, A_BUF_C_PTR = 0x18c00, 0x18c08
A_VIEW_FLAGS, A_VIEW_PARITY, A_BONUS_TIMER = 0x18c56, 0x18c60, 0x18d08
A_JUMPTABLE = 0x13144

# jump-table byte indices -> handler.
J_NOOP, J_T1, J_T2, J_W88, J_T4, J_STUB, J_LO1, J_LO2 = 0, 2, 4, 6, 8, 0xa, 0x18, 0x1a

# Staged scratch regions (clear of the program 0x10000..0x1bcf8 and of each other).
BUF_A = 0x60000              # buf_a records
BUF_C = 0x80000              # buf_c sprite-src base
SRC_OFF = 0x2000             # per-type record src long -> buf_c + this
BUFFER = 0x40000             # a6 draw buffer
BUF_LO = 0x30000             # staged buffer noise start (covers per-row rewinds above BUFFER)
BUF_SPAN = 0x20000
BUF_A_SPAN = 0x3000          # covers the 0x21d0 special record + the per-type records
SRC_SPAN = 0x8000            # sprite-src noise around BUF_C + SRC_OFF

OBJ_TYPE_BASE, OBJ_TYPE_STRIDE = 0x8a0, 0xd0
OBJ_SPECIAL_BASE = 0x21d0
N_OBJECTS = 15


def _w(v):
    return (v & 0xffff).to_bytes(2, "big")


def _l(v):
    return (v & 0xffffffff).to_bytes(4, "big")


def _type_record(jumpidx, colour, rows_m1, vseed, x_dst_off, x_off2, src_off, parity_off):
    """Build a per-type record covering data_base-relative fields. Returned as (rel_off -> bytes)
    pairs relative to type_base = buf_a + 0x8a0 + type*0xd0 (d6 == 0 for the single fuzzed row)."""
    fields = {
        -0x10: _w(colour),                 # colour (read before +d6)
        0x00: _l(src_off),                 # src long (+ buf_c)
        0x04: _w(rows_m1),                 # rows-1
        -0x0b: bytes([vseed & 0xff]),      # vertical seed byte
        0x06: _w(jumpidx),                 # obj_type_jumptable index
        0x08: _w(x_dst_off),               # a0 += this
        0x0a: _w(x_off2),                  # x += this
        0x0c: _w(parity_off),              # handler_lo src adj (parity 0)
        0x0e: _w(parity_off),              # handler_lo src adj (parity 2)
    }
    return fields


def _pokes(seed, obj_type, jumpidx, colour, rows_m1, x, view_flags, parity_flag, bonus,
           vseed, x_dst_off, x_off2, special=None):
    rng = random.Random(seed)
    p = {
        BUF_LO: bytes(rng.randrange(256) for _ in range(BUF_SPAN)),
        BUF_C + SRC_OFF - 0x100: bytes(rng.randrange(256) for _ in range(SRC_SPAN)),
        A_BUF_A_PTR: _l(BUF_A),
        A_BUF_C_PTR: _l(BUF_C),
        A_OBJ_SCAN_OFF: _w(0),                       # a5 stays at A_LIST_BASE
        A_VIEW_FLAGS: _w(view_flags),
        A_VIEW_PARITY: _w(parity_flag),
        A_BONUS_TIMER: _w(bonus),
        A_XOFF_TBL: _w(0),                           # shared x-offset word = 0
    }
    # a5 list stream: [dst_word, xoff_index, then 15 per-object x words].
    lst = bytearray()
    lst += _w(0)                                     # dst_word -> a0 = a6 + 0
    lst += _w(0)                                     # xoff index -> a4 = A_XOFF_TBL
    for i in range(N_OBJECTS):
        lst += _w(x if i == 0 else 0)
    p[A_LIST_BASE] = bytes(lst)
    # a3 flag stream: object 0 = obj_type (sign bit set if special), others type 0.
    flags = bytearray()
    for i in range(N_OBJECTS):
        if i == 0:
            f = obj_type | (0x8000 if special is not None else 0)
        else:
            f = 0
        flags += _w(f)
    p[A_FLAGS] = bytes(flags)
    # per-type record for obj_type (skip type 0, which never dispatches).
    if obj_type != 0:
        base = BUF_A + OBJ_TYPE_BASE + ((obj_type * OBJ_TYPE_STRIDE) & 0xffff)
        for rel, b in _type_record(jumpidx, colour, rows_m1, vseed, x_dst_off, x_off2,
                                   SRC_OFF, 0).items():
            p[base + rel] = b
    # special record (first pass), when requested: [src long, rows, jumpidx] @ 0x21d0.
    if special is not None:
        sj, srows = special
        p[BUF_A + OBJ_SPECIAL_BASE] = _l(SRC_OFF) + _w(srows) + _w(sj)
    return p


def _check(seed, obj_type, jumpidx, colour=5, rows_m1=3, x=0x40, view_flags=0, parity_flag=0,
           bonus=0, vseed=0, x_dst_off=0, x_off2=0, special=None):
    regs = {
        "a5": A_LIST_BASE, "a3": A_FLAGS, "a6": BUFFER, "d4": 0, "d6": 0, "d1": colour,
        "_pokes": _pokes(seed, obj_type, jumpidx, colour, rows_m1, x, view_flags, parity_flag,
                         bonus, vseed, x_dst_off, x_off2, special),
    }
    diffs, _ = differential(
        ENTRY, regs,
        lambda lib, buf: lib.g_draw_object_list(buf, A_LIST_BASE, A_FLAGS, BUFFER, 0, 0, colour),
        poison=True)
    assert not diffs, (f"type={obj_type} jump={jumpidx:#x} col={colour} rows={rows_m1 + 1} "
                       f"x={x:#x} view={view_flags} special={special}\n{report(diffs[:16])}")


harness._lib.g_draw_object_list.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
harness._lib.g_draw_object_list.restype = None


def test_skip_all():
    # Every object type 0 -> no dispatch at all -> no writes.
    _check(seed=1, obj_type=0, jumpidx=J_NOOP)


def test_noop():
    _check(seed=2, obj_type=3, jumpidx=J_NOOP)      # type nonzero but handler is a bare rts


def test_objsprite_handlers():
    for jump in (J_T1, J_T2, J_W88, J_T4):
        for x in (0x40, -8, 0x98):
            _check(seed=0x100 + jump * 8 + (x & 0xff), obj_type=5, jumpidx=jump, x=x, rows_m1=2)


def test_stub():
    for x in (0x40, 0, 0x20):
        _check(seed=0x200 + (x & 0xff), obj_type=7, jumpidx=J_STUB, x=x, rows_m1=1)


def test_handler_lo():
    for jump in (J_LO1, J_LO2):
        for parity in (0, 2):
            for x in (0x40, -8, -16, 0x90, 0x98):
                _check(seed=0x300 + jump * 16 + parity * 4 + (x & 0xff), obj_type=9, jumpidx=jump,
                       x=x, parity_flag=parity, colour=6, rows_m1=2)


def test_vertical_offset():
    # view_flags != 0 exercises the (vseed-rows)*view_flags>>4*width vertical a0 adjust.
    for vf in (2, 4, 6):
        for vseed in (0, 0x10, 0x80, 0xff):
            _check(seed=0x400 + vf * 256 + vseed, obj_type=4, jumpidx=J_T4, view_flags=vf,
                   vseed=vseed, rows_m1=2)


def test_x_and_dst_offsets():
    for x_dst_off in (0, 0x10, -0x10 & 0xffff):
        for x_off2 in (0, 8, -8 & 0xffff):
            _check(seed=0x500 + x_dst_off + x_off2, obj_type=6, jumpidx=J_LO1,
                   x_dst_off=x_dst_off, x_off2=x_off2)


def test_bonus_clamp():
    # bonus_timer != 0 and type < 6 -> type clamped to 6 (selects record 6, not the low type).
    for t in (1, 3, 5, 6, 8):
        _check(seed=0x600 + t, obj_type=t, jumpidx=J_T4, bonus=1)


def test_special_pass():
    # Flag word negative -> the SPECIAL pass fires (record @0x21d0) before the NORMAL pass.
    # Use a non-colour handler (t4) for the special pass so d1 threading is immaterial.
    for sj in (J_T4, J_T1, J_NOOP):
        _check(seed=0x700 + sj, obj_type=5, jumpidx=J_T2, special=(sj, 2))


# ---- multi-object / multi-row fuzz -----------------------------------------------------------
NORMAL_JUMPS = [J_NOOP, J_T1, J_T2, J_W88, J_T4, J_STUB, J_LO1, J_LO2]
D6_STEP = 0x10                   # d6 decrement per outer row


def _sx(w):
    return w - 0x10000 if w >= 0x8000 else w


def _pokes_multi(seed, objs, rows_outer, view_flags, parity_flag, bonus):
    """objs = per-object list of (type, jumpidx, colour, rows_m1, x, vseed, x_dst_off, x_off2) for the
    15 objects of EACH outer row (same list reused per row; d6 shifts the record read per row)."""
    rng = random.Random(seed)
    p = {
        BUF_LO: bytes(rng.randrange(256) for _ in range(BUF_SPAN)),
        BUF_C + SRC_OFF - 0x100: bytes(rng.randrange(256) for _ in range(SRC_SPAN)),
        A_BUF_A_PTR: _l(BUF_A),
        A_BUF_C_PTR: _l(BUF_C),
        A_OBJ_SCAN_OFF: _w(0),
        A_VIEW_FLAGS: _w(view_flags),
        A_VIEW_PARITY: _w(parity_flag),
        A_BONUS_TIMER: _w(bonus),
        A_XOFF_TBL: _w(0),
    }
    # a5 stream: rows_outer blocks of [dst_word, xoff_index, 15 x words].
    lst = bytearray()
    for _ in range(rows_outer):
        lst += _w(0) + _w(0)
        for (_t, _j, _c, _r, x, *_rest) in objs:
            lst += _w(x)
    p[A_LIST_BASE] = bytes(lst)
    # a3 stream: rows_outer blocks of 15 flag words + 1 trailing word (addq #2,a3 per row).
    flags = bytearray()
    for _ in range(rows_outer):
        for (t, *_rest) in objs:
            flags += _w(t)                           # low 6 bits = type; non-negative (no special)
        flags += _w(0)
    p[A_FLAGS] = bytes(flags)
    # per-type records, placed for every (type, d6) pair the run reads (d6 = -0x10*row).
    for row in range(rows_outer):
        d6 = (-D6_STEP * row) & 0xffff
        for (t, j, c, r, x, vseed, xd, xo) in objs:
            if t == 0:
                continue
            eff = 6 if (bonus and t < 6) else t
            type_base = (BUF_A + OBJ_TYPE_BASE + ((eff * OBJ_TYPE_STRIDE) & 0xffff)) & 0xffffffff
            p[type_base - 0x10] = _w(c)
            data_base = (type_base + _sx(d6)) & 0xffffffff
            for rel, b in {0x00: _l(SRC_OFF), 0x04: _w(r), -0x0b: bytes([vseed & 0xff]),
                           0x06: _w(j), 0x08: _w(xd), 0x0a: _w(xo),
                           0x0c: _w(0), 0x0e: _w(0)}.items():
                p[(data_base + rel) & 0xffffffff] = b
    return p


def test_fuzz():
    # The real caller (draw_game_objects tail) always passes d4=0, so the outer loop runs once. Fuzz
    # that case exhaustively: 15 objects/row, every handler, colours, rows, x regimes, view/parity/bonus.
    rng = random.Random(0x0B1EC7)
    for i in range(400):
        view_flags = rng.choice([0, 0, 2, 4, 6])
        parity = rng.choice([0, 2])
        bonus = rng.choice([0, 0, 1])
        objs = []
        for _ in range(N_OBJECTS):
            t = rng.choice([0, 0, 0, 1, 2, 5, 6, 9, 11])
            j = rng.choice(NORMAL_JUMPS)
            objs.append((t, j, rng.randrange(16), rng.randrange(0, 5),
                         rng.choice([0x40, -8 & 0xffff, -16 & 0xffff, 0x90, 0x98, 0x20]) & 0xffff,
                         rng.randrange(256), 0, 0))
        regs = {
            "a5": A_LIST_BASE, "a3": A_FLAGS, "a6": BUFFER, "d4": 0, "d6": 0, "d1": 0,
            "_pokes": _pokes_multi(i, objs, 1, view_flags, parity, bonus),
        }
        diffs, _ = differential(
            ENTRY, regs,
            lambda lib, buf: lib.g_draw_object_list(buf, A_LIST_BASE, A_FLAGS, BUFFER, 0, 0, 0),
            poison=True)
        assert not diffs, f"seed={i} view={view_flags} parity={parity} bonus={bonus}\n{report(diffs[:16])}"


def test_multirow():
    # d4>0 (multi outer row) never happens in the real game, but the reconstruction handles it: the
    # d6 record offset steps -0x10 per row. Exercise the d6-stepping path with clean, non-overlapping
    # records (1-2 active objects so per-type slots don't collide across rows) x view offsets.
    for rows_outer in (2, 3):
        for vf in (0, 2, 4, 6):
            objs = [(0,) * 8 for _ in range(N_OBJECTS)]
            objs[0] = (5, J_T4, 5, 2, 0x40, 0x80, 0, 0)
            objs[3] = (9, J_LO2, 6, 3, 0x90, 0x40, 0, 0)
            objs[8] = (2, J_T2, 4, 1, 0x98, 0x20, 0, 0)
            regs = {
                "a5": A_LIST_BASE, "a3": A_FLAGS, "a6": BUFFER,
                "d4": (rows_outer - 1) & 0xffff, "d6": 0, "d1": 0,
                "_pokes": _pokes_multi(0x900 + rows_outer * 8 + vf, objs, rows_outer, vf, 0, 0),
            }
            diffs, _ = differential(
                ENTRY, regs,
                lambda lib, buf: lib.g_draw_object_list(buf, A_LIST_BASE, A_FLAGS, BUFFER,
                                                        (rows_outer - 1) & 0xffff, 0, 0),
                poison=True)
            assert not diffs, f"rows_outer={rows_outer} view={vf}\n{report(diffs[:16])}"
