"""Differential tests for the shared object-sprite blit engine @ 0x131f6..0x13df8 — a single
parameterized fine-x-shifted 4-plane masked-transparency sprite blitter with ~18 alternate entry
points (disassembly-driven, verified vs the Musashi oracle). See OBJ_BLIT_ENGINE_SPEC.md.

It is the SIBLING of blit_objshift2: same STRADDLE / LEFT-EDGE / RIGHT-EDGE cell shell and the same
a0=col0 / a2=a0+8=col1 pairing, but the transparency SHOW mask is built from FOUR source words
(~(w0|w1|w2|~w3)) and pixels are copied plain-shifted (no color_pairs / no colour AND). The mask seed
is moveq #$ff = 0x000000FF (high word 0x0000). Per row all pointers net -160 bytes (one scanline up).

Staging mirrors test_blit_objshift / test_blit_objshift2: a noise dst band wide enough for the
column reach across every fuzzed row, a noise src arena mirroring an in-bounds sprite stream, and —
for the entries that read game state — view_flags, the per-view record on the caller's a2, and the
A_obj_view_xform table (real image data; NOT staged). Every register the chosen entry does not define
is poisoned (poison=True). Fields that would push a0/a1 outside the staged arenas are bounded, exactly
as the sibling tests bound their stride — real records/x keep the pointers in bounds.

Fuzz spans every fine-x (0..15), every width family (0x80/0x88/0x90/0x98), every dispatch branch
(LEFT ladder rungs / BASE / WIDE ladder rungs / fully-clipped both ends) and several row counts, so
every reachable body and all three cell kinds are exercised, for each entry-point shape.
"""
import ctypes
import random

import harness
from harness import differential, report

# Entry-point Ghidra addresses (jump-table object-type handlers into the shared body).
ENTRY_T4 = 0x131f6      # bare width-0x80 prologue
ENTRY_T2 = 0x1352c      # bare width-0x90 prologue
ENTRY_T1 = 0x13642      # bare width-0x98 prologue
ENTRY_W88 = 0x133b6     # width-0x88 prologue join (reached only via t39/t34/t3)
ENTRY_T53 = 0x13204     # ALT ENTRY into width-0x80 (skips fine-x calc)
ENTRY_T34 = 0x133ac     # a6-relative -> width 0x88
ENTRY_T33 = 0x1350c     # a6-relative -> width 0x90
ENTRY_T32 = 0x13622     # a6-relative -> width 0x98
ENTRY_T39 = 0x133a6     # view-transform (bsr 0x145fc) -> width 0x88
ENTRY_T38 = 0x13506     # view-transform -> width 0x90
ENTRY_T37 = 0x1361c     # view-transform -> width 0x98
ENTRY_T42 = 0x13512     # scan-table x-build -> width 0x90
ENTRY_T41 = 0x13628     # scan-table x-build -> width 0x98
ENTRY_T3 = 0x133b2      # bsr 0x14620 then fall into width 0x88
ENTRY_T49 = 0x13528     # bsr 0x14620 then fall into width 0x90
ENTRY_T16 = 0x1363e     # bsr 0x14620 then fall into width 0x98

# Named globals the wrappers read (all inside the program's bss / const image; already present).
A_VIEW_FLAGS = 0x18c56
A_OBJ_SCAN_OFF = 0x18c58
A_VIEW_XFORM = 0x1722a       # real image data (const table); left real, not staged

# Staged low-memory layout (clear of the program, which ends 0x1bcf8, and of the stack guard 0xff000).
DST_BASE = 0x60000           # dst scanline base; a0 = dst + aligned_col, then rewinds up per row
DST_LO = 0x50000             # start of the staged dst noise region (covers rewinds above DST_BASE)
DST_SPAN = 0x20000           # covers DST_LO .. DST_BASE + column reach across all fuzzed rows
SRC_BASE = 0x88000           # src sprite stream (a1); walks up 160 bytes per row
REC_BASE = 0x98000           # per-view / a6-relative record the wrappers read via a2/a6

ROW_UP = 0xa0                # per-row net pointer delta magnitude (one 160-byte scanline up)
ROW_READAHEAD = 0x30         # a1/a0 read-ahead per row: up to ~6 cells (0x30 bytes) forward
LADDER_SKIP = 0x20           # extra one-time a0/a1 advance the LEFT ladder can apply (<= 3 cells)

WIDTHS = {ENTRY_T4: 0x80, ENTRY_T2: 0x90, ENTRY_T1: 0x98, ENTRY_W88: 0x88}
FINE_X_ALL = range(16)


def _sign16(v):
    v &= 0xffff
    return v - 0x10000 if v >= 0x8000 else v


def _x_for(col, fine_x):
    """x that decodes to aligned column `col` (a signed multiple of 8) with nibble `fine_x`.
    aligned_col = ((int16)x >> 1) & 0xfff8 reads x bits >= 4; fine_x = x & 0xf reads bits 0..3."""
    return ((col << 1) | (fine_x & 0xf)) & 0xffff


def _band(base, rows_m1):
    """Byte span [lo, hi) a pointer that starts at `base` and nets -160 bytes/row sweeps over the
    run, plus the one-time LEFT-ladder skip and the per-row read-ahead. Generous by design."""
    rows = _sign16(rows_m1) + 1
    lo = base - LADDER_SKIP
    hi = base + ROW_READAHEAD + LADDER_SKIP
    for r in range(max(rows, 1)):
        p = base - ROW_UP * r
        lo = min(lo, p - LADDER_SKIP)
        hi = max(hi, p + ROW_READAHEAD)
    return lo, hi


def _noise_pokes(seed, rows_m1, extra=None):
    """A noise dst band + a noise src band covering the sweep; plus any extra pokes."""
    rng = random.Random(seed)
    slo, shi = _band(SRC_BASE, rows_m1)
    pokes = {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_SPAN)),
        slo: bytes(rng.randrange(256) for _ in range(shi - slo)),
    }
    for a, b in (extra or {}).items():
        pokes[a] = b
    return pokes


# ---- bare / alt-entry cases (D0 x, D4 rows-1, A0 dst, A1 src) ----

def _check_bare(entry, gfn, seed, x, rows_m1):
    regs = {"d0": x & 0xffff, "d4": rows_m1 & 0xffff, "a0": DST_BASE, "a1": SRC_BASE,
            "_pokes": _noise_pokes(seed, rows_m1)}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: gfn(lib)(buf, x & 0xffff, rows_m1 & 0xffff, DST_BASE, SRC_BASE),
        poison=True)
    assert not diffs, f"entry={entry:#x} x={x:#x} rows={rows_m1 + 1}\n{report(diffs[:16])}"


def _all_cols(width):
    """Every dispatch column for a width: LEFT ladder rungs, a BASE sweep, WIDE ladder rungs, and
    fully-clipped both ends (multiples of 8, signed)."""
    cols = [-8, -16, -24, -32, -40]                     # LEFT rungs + fully off-left
    cols += list(range(0, width, 8))                    # BASE
    cols += [width, width + 8, width + 0x10, width + 0x18, width + 0x20]  # WIDE rungs + off-right
    return cols


def test_bare_widths_every_fine_x():
    gfns = {ENTRY_T4: lambda lib: lib.g_objsprite_t4, ENTRY_T2: lambda lib: lib.g_objsprite_t2,
            ENTRY_T1: lambda lib: lib.g_objsprite_t1, ENTRY_W88: lambda lib: lib.g_objsprite_w88}
    for entry, width in WIDTHS.items():
        for fine_x in FINE_X_ALL:
            for col in _all_cols(width):
                _check_bare(entry, gfns[entry], seed=(entry & 0xffff) + fine_x * 0x200 + (col & 0xff),
                            x=_x_for(col, fine_x), rows_m1=3)


def test_bare_row_counts():
    for entry, width in WIDTHS.items():
        gfn = {ENTRY_T4: "g_objsprite_t4", ENTRY_T2: "g_objsprite_t2",
               ENTRY_T1: "g_objsprite_t1", ENTRY_W88: "g_objsprite_w88"}[entry]
        for rows_m1 in (0, 1, 5, 0x1f):
            _check_bare(entry, (lambda g: (lambda lib: getattr(lib, g)))(gfn),
                        seed=0x1000 + (entry & 0xff) + rows_m1,
                        x=_x_for(width // 2 & ~7, 5), rows_m1=rows_m1)


def test_bare_fuzz():
    gfns = {ENTRY_T4: lambda lib: lib.g_objsprite_t4, ENTRY_T2: lambda lib: lib.g_objsprite_t2,
            ENTRY_T1: lambda lib: lib.g_objsprite_t1, ENTRY_W88: lambda lib: lib.g_objsprite_w88}
    rng = random.Random(0xB177)
    for i in range(3000):
        entry = rng.choice(list(WIDTHS))
        width = WIDTHS[entry]
        fine_x = rng.randrange(16)
        col = rng.choice([
            rng.randrange(-40, -8) & ~7,                # clipped left
            rng.choice([-8, -16, -24]),                 # LEFT ladder rungs
            rng.randrange(0, width) & ~7,               # base
            rng.choice([width, width + 8, width + 0x10, width + 0x18]),  # WIDE rungs
            rng.randrange(width + 0x20, width + 0x80) & ~7,              # clipped right
        ])
        rows_m1 = rng.randrange(0, 20)
        _check_bare(entry, gfns[entry], seed=i, x=_x_for(col, fine_x), rows_m1=rows_m1)


# ---- alt entry 0x13204 (t53): caller pre-sets d0=aligned_col, d6=shl, d7=shr ----
# The alt entry starts at `adda.w d0,a0`; the FIRST dispatch branch `bmi <LEFT>` (0x13206) reads the
# N flag from the CALLER's last op on d0 — `adda.w` sets no flags. Real callers reach 0x13204 having
# just masked/tested d0 (so N = sign(aligned_col)); the differential harness cannot set the CCR, so
# the oracle's dispatch here is driven by an uncontrolled flag and is NOT reproducible in isolation
# (it even diverges between the normal and poison emu runs). So t53 cannot be soundly diffed vs the
# oracle on its own. Instead we pin it as a candidate-consistency check: g_objsprite_t53 (fed the
# pre-decoded aligned_col/shl/shr) must produce byte-identical output to g_objsprite_t4 fed the x
# that decodes to the same (aligned_col, fine_x) — because the alt entry is exactly the width-0x80
# prologue with the fine-x/asr/andi computation hoisted into the caller. g_objsprite_t4's own output
# is fully oracle-verified (test_bare_widths_every_fine_x), so this transitively verifies t53's body.

def test_alt_entry_t53_matches_t4():
    import harness
    from harness import make_image, _lib
    for fine_x in FINE_X_ALL:
        shl, shr = 16 - fine_x, fine_x
        for col in _all_cols(0x80):
            pokes = _noise_pokes(0x2000 + fine_x * 0x200 + (col & 0xff), 3)
            x = _x_for(col, fine_x)
            out = {}
            for tag, call in (
                ("t4", lambda buf: _lib.g_objsprite_t4(buf, x & 0xffff, 3, DST_BASE, SRC_BASE)),
                ("t53", lambda buf: _lib.g_objsprite_t53(buf, col & 0xffff, shl, shr, 3, DST_BASE, SRC_BASE)),
            ):
                img = make_image(dict(pokes))
                buf = (ctypes.c_uint8 * len(img)).from_buffer(bytearray(img))
                call(buf)
                out[tag] = bytes(buf)
            assert out["t4"] == out["t53"], f"t53 != t4 for col={col:#x} fine_x={fine_x}"


# ---- a6-relative wrappers (a0 = a6 + sign_ext16(word@--a2)) then a width prologue ----

def _check_a6(entry, gname, width, seed, x, rows_m1, rec_word):
    rec_cursor = REC_BASE + 0x10          # a2; the wrapper reads word@(a2-2)
    a6 = DST_BASE                         # a0 = a6 + rec_word
    rec = {rec_cursor - 2: (rec_word & 0xffff).to_bytes(2, "big")}
    regs = {"d0": x & 0xffff, "d4": rows_m1 & 0xffff, "a6": a6, "a2": rec_cursor, "a1": SRC_BASE,
            "_pokes": _noise_pokes(seed, rows_m1, rec)}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, gname)(buf, x & 0xffff, rows_m1 & 0xffff, a6, rec_cursor, SRC_BASE),
        poison=True)
    assert not diffs, (f"entry={entry:#x} x={x:#x} rows={rows_m1 + 1} rec_word={rec_word:#x}\n"
                       f"{report(diffs[:16])}")


def test_a6_wrappers():
    cases = [(ENTRY_T34, "g_objsprite_t34", 0x88), (ENTRY_T33, "g_objsprite_t33", 0x90),
             (ENTRY_T32, "g_objsprite_t32", 0x98)]
    for entry, gname, width in cases:
        for fine_x in (0, 7, 15):
            for col in _all_cols(width):
                for rec_word in (0, 0x20, -0x20 & 0xffff):
                    _check_a6(entry, gname, width,
                              seed=(entry & 0xffff) + fine_x * 0x100 + (col & 0xff) + rec_word,
                              x=_x_for(col, fine_x), rows_m1=2, rec_word=rec_word)


# ---- view-transform wrappers (helper 0x145fc then a width prologue) ----
# Helper: a3 = 0x1722a + sign_ext16(word@--a2) + view_flags*2; a1 -= word[0]; a0 = a6 + (word[1]&0xE0);
# rows -= (word[1]&0x1f). The A_obj_view_xform table is REAL image data — left real, not staged. To
# steer the record to a controlled entry we set the a2 word so the record lands on a chosen offset,
# and read whatever the real table holds there. We only need the pointers to stay in the arenas, so
# we pick a small a2 word (record near table start) and cap rows; the real word[0]/word[1] then drive
# a1/a0/rows deterministically and identically on both cores.

def _check_xform(entry, gname, width, seed, x, rows_seed, view, a2_word):
    rec_cursor = REC_BASE + 0x10          # a2; the helper reads word@(a2-2)
    a6 = DST_BASE                         # a0 = a6 + (word[1] & 0xE0), stays in the dst band
    rec = {rec_cursor - 2: (a2_word & 0xffff).to_bytes(2, "big"),
           A_VIEW_FLAGS: (view << 1).to_bytes(2, "big")}
    regs = {"d0": x & 0xffff, "d4": rows_seed & 0xffff, "a6": a6, "a1": SRC_BASE, "a2": rec_cursor,
            "_pokes": _noise_pokes(seed, rows_seed + 0x40, rec)}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, gname)(buf, x & 0xffff, rows_seed & 0xffff, a6, SRC_BASE, rec_cursor),
        poison=True)
    assert not diffs, (f"entry={entry:#x} x={x:#x} rows_seed={rows_seed} view={view} "
                       f"a2_word={a2_word:#x}\n{report(diffs[:16])}")


def test_view_transform_wrappers():
    cases = [(ENTRY_T39, "g_objsprite_t39", 0x88), (ENTRY_T38, "g_objsprite_t38", 0x90),
             (ENTRY_T37, "g_objsprite_t37", 0x98)]
    for entry, gname, width in cases:
        for view in range(4):
            for fine_x in (0, 8, 15):
                # small a2 words keep the record near the table start (in-image); rows seeded high so
                # the (word[1]&0x1f) clip cannot underflow into a huge count.
                for a2_word in (0, 2, 4, 6):
                    _check_xform(entry, gname, width,
                                 seed=(entry & 0xffff) + view * 0x100 + fine_x * 0x10 + a2_word,
                                 x=_x_for(width // 2 & ~7, fine_x), rows_seed=0x30, view=view,
                                 a2_word=a2_word)


# ---- scan-table x-build wrappers (a0 = a6 + word@(a2)+ ; x rebuilt from a4/a5/scan_off) ----

def _check_scan(entry, gname, width, seed, rows_m1, a0_word, a4_word, a5_word, scan_off, x_col):
    """Stage a2/a4/a5 so a0 lands in the dst band and the rebuilt x hits aligned column `x_col`.
    x = word@(a5 + sign_ext16(-scan_off)) + word@a4 + word@(a2+2). We put the whole desired x into
    word@a4 and zero the others, choosing scan_off = 0 so a5's index is 0."""
    a6 = DST_BASE
    rec_cursor = REC_BASE + 0x10          # a2 (post-incremented once for a0, then read again for x)
    a4 = REC_BASE + 0x40
    a5 = REC_BASE + 0x80
    want_x = _x_for(x_col, seed & 0xf)
    pokes = {
        rec_cursor: (a0_word & 0xffff).to_bytes(2, "big"),            # word@a2 -> a0 offset (post-inc)
        rec_cursor + 2: (0).to_bytes(2, "big"),                       # word@(a2+2) -> x term 3
        a4: (want_x & 0xffff).to_bytes(2, "big"),                     # word@a4 -> x term 2 (carries x)
        a5: (a5_word & 0xffff).to_bytes(2, "big"),                    # word@(a5 + -scan_off) -> x term 1
        A_OBJ_SCAN_OFF: (scan_off & 0xffff).to_bytes(2, "big"),
    }
    regs = {"d4": rows_m1 & 0xffff, "a6": a6, "a2": rec_cursor, "a4": a4, "a5": a5, "a1": SRC_BASE,
            "_pokes": _noise_pokes(seed, rows_m1, pokes)}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, gname)(buf, rows_m1 & 0xffff, a6, rec_cursor, a4, a5, SRC_BASE),
        poison=True)
    assert not diffs, (f"entry={entry:#x} rows={rows_m1 + 1} a0_word={a0_word:#x} x_col={x_col:#x} "
                       f"scan_off={scan_off:#x}\n{report(diffs[:16])}")


def test_scan_table_wrappers():
    cases = [(ENTRY_T42, "g_objsprite_t42", 0x90), (ENTRY_T41, "g_objsprite_t41", 0x98)]
    for entry, gname, width in cases:
        for x_col in _all_cols(width):
            _check_scan(entry, gname, width, seed=(entry & 0xffff) + (x_col & 0xff),
                        rows_m1=2, a0_word=0, a4_word=0, a5_word=0, scan_off=0, x_col=x_col)


# ---- bsr draw_obj_sprite_hi (0x14620, verified) then fall into a width prologue ----
# Compose: the helper draws a mode-8 pass (its own geometry from a record + view_flags), renames
# D3->D0 / D5->D4 / A0=sprite-top / A1-=band, and this engine draws a second pass on those. Stage as
# test_blit_objsprite stages draw_obj_sprite_hi: a wide dst band, a src arena, the rec+0xc rows table,
# and view_flags; bound rows_byte / xoff so both passes stay in the arenas.

DBL_DST_LO = 0x40000
DBL_DST_SPAN = 0x40000
OBJD_WIDTH = 0xa0


def _hi_pokes(seed, rows_byte, view, xoff):
    rng = random.Random(seed)
    rows_view = [rng.randrange(0x10) for _ in range(4)]
    rows_view[view] = rows_byte
    rec = bytearray(rng.randrange(256) for _ in range(0x18))
    rec[0x8:0xa] = (xoff & 0xffff).to_bytes(2, "big")
    rec[0xc:0x10] = bytes(rows_view)
    # src arena: the helper's mode-8 pass reads from SRC_BASE, the fall-in pass from SRC_BASE-0xa0.
    return {
        DBL_DST_LO: bytes(rng.randrange(256) for _ in range(DBL_DST_SPAN)),
        SRC_BASE - 0x4000: bytes(rng.randrange(256) for _ in range(0x8000)),
        REC_BASE: bytes(rec),
        A_VIEW_FLAGS: (view << 1).to_bytes(2, "big"),
    }


def _check_hi(entry, gname, width, seed, x, colour, rows_byte, voff, view, xoff):
    dst = DBL_DST_LO + 0x20000            # centre of the dst band (a0 base fed to the helper)
    rec_cursor = REC_BASE + 0xa
    regs = {"d0": x & 0xffff, "d1": colour & 0xffff, "d2": OBJD_WIDTH, "d4": rows_byte & 0xffff,
            "d7": voff & 0xffff, "a0": dst, "a1": SRC_BASE, "a2": rec_cursor,
            "_pokes": _hi_pokes(seed, rows_byte, view, xoff)}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, gname)(buf, x & 0xffff, colour & 0xffff, OBJD_WIDTH,
                                             rows_byte & 0xffff, voff & 0xffff, dst, SRC_BASE, rec_cursor),
        poison=True)
    assert not diffs, (f"entry={entry:#x} x={x:#x} col={colour} rows_byte={rows_byte} view={view} "
                       f"xoff={xoff:#x}\n{report(diffs[:16])}")


def test_bsr_hi_wrappers():
    cases = [(ENTRY_T3, "g_objsprite_t3", 0x88), (ENTRY_T49, "g_objsprite_t49", 0x90),
             (ENTRY_T16, "g_objsprite_t16", 0x98)]
    for entry, gname, width in cases:
        for view in range(4):
            for fine_x in (0, 7, 15):
                _check_hi(entry, gname, width, seed=(entry & 0xffff) + view * 0x100 + fine_x,
                          x=_x_for(width // 2 & ~7, fine_x), colour=5, rows_byte=2,
                          voff=OBJD_WIDTH * 2, view=view, xoff=0x30)


# ctypes signatures.
_P = ctypes.POINTER(ctypes.c_uint8)
for _g, _n in [("g_objsprite_t4", 4), ("g_objsprite_t2", 4), ("g_objsprite_t1", 4),
               ("g_objsprite_w88", 4), ("g_objsprite_t53", 6),
               ("g_objsprite_t34", 5), ("g_objsprite_t33", 5), ("g_objsprite_t32", 5),
               ("g_objsprite_t39", 5), ("g_objsprite_t38", 5), ("g_objsprite_t37", 5),
               ("g_objsprite_t42", 6), ("g_objsprite_t41", 6),
               ("g_objsprite_t3", 8), ("g_objsprite_t49", 8), ("g_objsprite_t16", 8)]:
    getattr(harness._lib, _g).argtypes = [_P] + [ctypes.c_uint32] * _n
    getattr(harness._lib, _g).restype = None
