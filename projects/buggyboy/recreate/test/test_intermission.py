"""Differential test for intermission_poll @ 0x12914 (an intermission-screen block blitter).

Despite the "poll" name it reads no input — it's a 9-entry, table-driven plain block copy from a
pre-rendered graphic in buf_c to the draw buffer (physbase_tbl[flip_idx] + 0x990). The 9-entry
control table is real image data (inline after the function); the test stages a buf_c source arena
+ dest region with noise and diffs the whole image. Fuzzed over both flip slots, poison-checked.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12914

BUF = 0x2000                   # draw buffer; dst = BUF + 0x990 + (signed) dst_off
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08

BUF_C = 0x40000                # buf_c base (clear of the program, dest region and stack staging)
# Source: buf_c + 0x32c80 + src_off (max 0x6ea0) + a rows*stride + width margin (recomputed per entry).
SRC_LO = BUF_C + 0x32c80
SRC_HI = BUF_C + 0x3b000
DST_LO, DST_HI = 0x1000, 0x6000            # covers BUF+0x990 +/- every (signed) dst_off + rows

harness._lib.g_intermission_poll.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_intermission_poll.restype = None


def _pokes(seed, flip):
    rng = random.Random(seed)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO)),
        SRC_LO: bytes(rng.randrange(256) for _ in range(SRC_HI - SRC_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
    }


def test_intermission_poll():
    for seed in range(25):
        for flip in (0, 4):
            regs = {"_pokes": _pokes(seed, flip)}
            diffs, _ = differential(ENTRY, regs,
                                    lambda l, b: l.g_intermission_poll(b), poison=True)
            assert not diffs, f"seed={seed} flip={flip}\n{report(diffs[:12])}"


# --- draw_intermission @ 0x129ba: the scrolling between-legs screen (hi-score/times/credits) ---
# Three sections (text rows, digit sprites, credits) all scroll by the signed offset at 0x18ca8.
# The layout tables (0x1858c/0x18622) and credit strings (0x180f4) are real image data; the test
# stages the string arenas (highscore_table, buf_a) + num sprites (buf_c) + screen with noise and
# fuzzes the scroll offset (and flip slot) to exercise the on-screen / clipped / off-top branches.
DI_ENTRY = 0x129ba
DI_NOISE_LO, DI_NOISE_HI = 0x2000, 0xc000      # screen band the sections draw into
A_BUF_A, A_SCROLL = 0x18c00, 0x18ca8
DI_BUF_C, DI_BUF_C_SPAN = 0x30000, 0x1c000     # num sprites (draw_num reads buf_c)
DI_BUF_A = 0x50000
A_HSCORE_LO, A_HSCORE_HI = 0x18266, 0x1858c    # section-1 strings; stop before the layout table

harness._lib.g_draw_intermission.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_intermission.restype = None


def _di_pokes(seed, scroll, flip):
    rng = random.Random(seed)
    return {
        DI_NOISE_LO: bytes(rng.randrange(256) for _ in range(DI_NOISE_HI - DI_NOISE_LO)),
        A_HSCORE_LO: bytes(rng.randrange(256) for _ in range(A_HSCORE_HI - A_HSCORE_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: DI_BUF_C.to_bytes(4, "big"),
        DI_BUF_C: bytes(rng.randrange(256) for _ in range(DI_BUF_C_SPAN)),
        A_BUF_A: DI_BUF_A.to_bytes(4, "big"),
        DI_BUF_A + 0x880: bytes(rng.randrange(256) for _ in range(0x60)),   # section-2 number strings
        A_SCROLL: (scroll & 0xffff).to_bytes(2, "big"),
    }


def test_draw_intermission():
    seed = 0
    for scroll in (0, 0x20, -0x20, 0x40, -0x40, 8, -8):    # on-screen / clipped / off-top branches
        for flip in (0, 4):
            regs = {"_pokes": _di_pokes(seed, scroll, flip)}
            diffs, _ = differential(DI_ENTRY, regs, lambda l, b: l.g_draw_intermission(b))
            assert not diffs, f"scroll={scroll} flip={flip}\n{report(diffs[:12])}"
            seed += 1


# --- fade_step @ 0x129a0: one intermission animation step -------------------------------------
# A prologue that repaints the backdrop (fill_screen colour 6), re-lays the static blocks
# (intermission_poll), stamps the fixed Elite Systems header (draw_text, const image string at
# 0x18002), then falls through into draw_intermission. The test stages the union of what
# intermission_poll (buf_c block source) and draw_intermission (hi-score/num strings, num sprites)
# read; the header string and layout tables are real image data. fill_screen repaints the whole
# buffer first, so the screen band needs no pre-noise.
FS_ENTRY = 0x129a0
FS_BUF_C = 0x40000                              # shared buf_c: num sprites (+0xbb80) + block src (+0x32c80)
FS_BUF_C_LO, FS_BUF_C_HI = FS_BUF_C + 0xb000, FS_BUF_C + 0x3b000
FS_BUF_A = 0x90000                              # clear of the buf_c arena above

harness._lib.g_fade_step.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_fade_step.restype = None


def _fs_pokes(seed, scroll, flip):
    rng = random.Random(seed)
    return {
        A_HSCORE_LO: bytes(rng.randrange(256) for _ in range(A_HSCORE_HI - A_HSCORE_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: FS_BUF_C.to_bytes(4, "big"),
        FS_BUF_C_LO: bytes(rng.randrange(256) for _ in range(FS_BUF_C_HI - FS_BUF_C_LO)),
        A_BUF_A: FS_BUF_A.to_bytes(4, "big"),
        FS_BUF_A + 0x880: bytes(rng.randrange(256) for _ in range(0x60)),
        A_SCROLL: (scroll & 0xffff).to_bytes(2, "big"),
    }


def test_fade_step():
    seed = 0
    for scroll in (0, 0x20, -0x20, 0x40, -0x40, 8, -8):
        for flip in (0, 4):
            regs = {"_pokes": _fs_pokes(seed, scroll, flip)}
            diffs, _ = differential(FS_ENTRY, regs, lambda l, b: l.g_fade_step(b))
            assert not diffs, f"scroll={scroll} flip={flip}\n{report(diffs[:12])}"
            seed += 1


# ============================================================================
# intermission @ 0x127a0 — the attract-mode / between-legs loop. It never returns except on a player
# abort, so it can't run to rts as a whole; instead each piece is diffed by entering the oracle at
# its PC (mid-function entry), mirroring the g_int_* phase-slice helpers.
#
#   * prologue + Phase A: run-to-rts from the real entry with an abort staged (the only path that
#     reaches rts from the top before an unbounded loop).
#   * Phase A branches: enter the loop head; the timer/scroll/dwell arithmetic + break-to-B.
#   * Phase B leg pick / Phase D dwell+carousel counters: cheap checkpoints (no heavy staging).
#
# Read-verified (documented in STATUS.md): the Phase-B game_update warm-up burst + draw_frame pair,
# and the Phase-C per-frame render pipeline (game_update + render_road + blit_road_scroll +
# draw_game_objects + draw_hud) with its 0x96-frame counter — every callee is verified on its own
# and the loop counters are transparent, but running the loops to a checkpoint would need the full
# game-state staging of ~50 game_update frames, which the harness sidesteps the same way it does for
# update_highscore's interactive name-entry tail.
# ============================================================================
INT_ENTRY = 0x127a0
INT_PHASEA = 0x127cc          # Phase-A loop head
INT_PHASEB = 0x127fe          # Phase-B entry (Phase-A break target)
INT_PHASEB_LEG = 0x12814      # after leg_index = leg_select
INT_PHASED_BODY = 0x128b0     # Phase-D loop head (counter slice)
INT_PHASED_DRAW = 0x128d8     # draw_leg_results call (checkpoint before the draw)
INT_TOP = 0x127a0             # Phase-D restart target

A_INT_TIMER, A_INT_FRAME, A_INT_SCROLL, A_INT_FRAME_HI = 0x18ca6, 0x18ca4, 0x18ca8, 0x18ca2
A_LEG_SELECT, A_LEG_INDEX = 0x18c36, 0x18c38
A_INPUT_STATE, A_INPUT_PREV = 0x18c44, 0x18c42

INT_SCREEN0, INT_SCREEN1 = 0x20000, 0x30000    # two draw buffers (flip alternates between them)
INT_BUF_C = 0x40000                             # block source (+0x32c80) + number sprites (+0xbb80)
INT_BUF_C_LO, INT_BUF_C_HI = INT_BUF_C + 0xb000, INT_BUF_C + 0x3b000
INT_BUF_A = 0x80000

# check_abort aborts when input_state's low byte is nonzero and differs from input_prev's low byte.
ABORT_POKES = {A_INPUT_STATE: b"\x00\x01", A_INPUT_PREV: b"\x00\x00"}

# g_int_stepA / g_int_stepD_counter return codes (mirror the #defines in src/intermission.c). The
# image diff can't see the return value, so the tests assert it directly to pin the control decision.
# NOTE: the Phase-A/D counter helpers read-modify-write their counter words, so the counter address
# is both input and output — the poison pass (which re-runs from an image whose oracle-written bytes
# are inverted) would corrupt that input and divert control flow, so poison is used only on the
# Phase-B leg pick (no PC-divergent branch). The counter tests aren't vacuous without it: each pokes
# an input distinct from the written output, so a missing write still shows in the diff.
INT_A_CONTINUE, INT_A_ABORT, INT_A_BREAK = 0, 1, 2
INT_D_DRAW, INT_D_ADVANCE, INT_D_RESTART = 0, 1, 2

for _n, _res in (("g_intermission", None), ("g_int_phaseB_leg", None),
                 ("g_int_stepA", ctypes.c_int), ("g_int_stepD_counter", ctypes.c_int)):
    getattr(harness._lib, _n).argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    getattr(harness._lib, _n).restype = _res


def _int_world(seed, flip):
    """Stage everything fade_step + draw_intermission read: hi-score strings, the buf_c graphic
    (block source + number sprites), the buf_a number strings, and both screen-buffer pointers.
    fill_screen repaints the whole draw buffer, so the screen band itself needs no pre-noise."""
    rng = random.Random(seed)
    return {
        A_HSCORE_LO: bytes(rng.randrange(256) for _ in range(A_HSCORE_HI - A_HSCORE_LO)),
        INT_BUF_C_LO: bytes(rng.randrange(256) for _ in range(INT_BUF_C_HI - INT_BUF_C_LO)),
        INT_BUF_A + 0x880: bytes(rng.randrange(256) for _ in range(0x60)),
        A_FLIP_IDX: (flip & 0xffff).to_bytes(2, "big"),
        A_PHYSBASE: INT_SCREEN0.to_bytes(4, "big") + INT_SCREEN1.to_bytes(4, "big"),
        A_BUF_C: INT_BUF_C.to_bytes(4, "big"),
        A_BUF_A: INT_BUF_A.to_bytes(4, "big"),
    }


def test_intermission_prologue_and_phaseA():
    """Run-to-rts from the real entry with an abort staged: the prologue (counter init + two
    fade_step backdrop frames + palette + flips) and one Phase-A frame (draw_intermission + flip),
    then check_abort fires and intermission returns. The whole image is diffed."""
    for seed, flip in ((0, 0), (1, 4)):
        pokes = _int_world(seed, flip)
        pokes.update(ABORT_POKES)
        diffs, _ = differential(INT_ENTRY, {"_pokes": pokes},
                                lambda l, b: l.g_intermission(b), max_insns=3_000_000,
                                hw_waiver=harness.HW_STUBBED_BY_OS_C)
        assert not diffs, f"seed={seed} flip={flip}\n{report(diffs[:16])}"


def _phaseA_pokes(timer, scroll, frame):
    p = _int_world(seed=7, flip=0)
    p.update(ABORT_POKES)
    p[A_INT_TIMER] = (timer & 0xffff).to_bytes(2, "big")
    p[A_INT_SCROLL] = (scroll & 0xffff).to_bytes(2, "big")
    p[A_INT_FRAME] = (frame & 0xffff).to_bytes(2, "big")
    return p


def test_phaseA_branches():
    """Enter the Phase-A loop head and run one frame to rts (abort staged). The staged counters
    drive each arithmetic branch: below-gate (no scroll change), in-gate (scroll advances), timer
    underflow (wrap to 0x5c), and scroll underflow (dwell counter ticks down, no break)."""
    cases = (
        (0x20, 0x30, 5),   # timer -> 0x1f, below the gate: no scroll change
        (0x50, 0x30, 5),   # timer -> 0x4f, in the gate: scroll -> 0x2f
        (0x00, 0x30, 5),   # timer underflow -> wrap to 0x5c (>= gate): scroll advances
        (0x50, 0x00, 5),   # scroll underflow -> scroll = 0, dwell 5 -> 4 (no break)
    )
    for timer, scroll, frame in cases:
        diffs, info = differential(INT_PHASEA, {"_pokes": _phaseA_pokes(timer, scroll, frame)},
                                   lambda l, b: l.g_int_stepA(b), max_insns=2_000_000,
                                   hw_waiver=harness.HW_STUBBED_BY_OS_C)
        assert not diffs, f"timer={timer:#x} scroll={scroll:#x} frame={frame}\n{report(diffs[:16])}"
        assert info["ret"] == INT_A_ABORT, f"timer={timer:#x}: ret={info['ret']} (expected abort)"


def test_phaseA_break_to_B():
    """Scroll underflow with the dwell counter at 0 breaks to Phase B *before* drawing; the oracle
    is checkpointed at the Phase-B entry PC and only the three counter words should have changed."""
    diffs, info = differential(INT_PHASEA, {"_pokes": _phaseA_pokes(0x50, 0x00, 0x00)},
                               lambda l, b: l.g_int_stepA(b), stop_pc=INT_PHASEB)
    assert not diffs, f"break-to-B\n{report(diffs[:16])}"
    assert info["ret"] == INT_A_BREAK, f"ret={info['ret']} (expected break)"


def test_phaseB_leg_select():
    """Phase-B leg pick: leg_select advances (wraps at 5) and is copied into leg_index. Checkpoint
    right after the copy (before the init/warm-up tail); no staging needed. Poison-checked so the
    sel=5 wrap (both words -> 0) still verifies the writes rather than matching base-0 by luck."""
    for sel in range(6):
        p = {A_LEG_SELECT: (sel & 0xffff).to_bytes(2, "big")}
        diffs, _ = differential(INT_PHASEB, {"_pokes": p}, lambda l, b: l.g_int_phaseB_leg(b),
                                stop_pc=INT_PHASEB_LEG, poison=True)
        assert not diffs, f"leg_select={sel}\n{report(diffs[:16])}"


def test_phaseD_dwell():
    """Phase-D counter with the per-leg dwell not yet elapsed: just tick it. Checkpoint before the
    draw_leg_results call."""
    for hi in (0, 1, 0x18):                        # hi + 1 < INT_D_DWELL (0x1a) -> no advance
        p = {A_INT_FRAME_HI: hi.to_bytes(2, "big")}
        diffs, info = differential(INT_PHASED_BODY, {"_pokes": p},
                                   lambda l, b: l.g_int_stepD_counter(b), stop_pc=INT_PHASED_DRAW)
        assert not diffs, f"hi={hi:#x}\n{report(diffs[:16])}"
        assert info["ret"] == INT_D_DRAW, f"hi={hi:#x}: ret={info['ret']} (expected draw)"


def test_phaseD_restart():
    """Dwell elapsed with every leg already shown: reset the counter + leg_index and restart at the
    top. Checkpointed at the restart target PC."""
    p = {A_INT_FRAME_HI: (0x19).to_bytes(2, "big"), A_LEG_INDEX: (4).to_bytes(2, "big")}
    diffs, info = differential(INT_PHASED_BODY, {"_pokes": p},
                               lambda l, b: l.g_int_stepD_counter(b), stop_pc=INT_TOP)
    assert not diffs, f"restart\n{report(diffs[:16])}"
    assert info["ret"] == INT_D_RESTART, f"ret={info['ret']} (expected restart)"


def test_phaseD_advance():
    """Dwell elapsed with legs remaining: advance leg_index and rebuild that leg's dashboard
    (init_leg_dash). init_leg_dash reads mem_base/buf_a/buf_c, so stage those (as test_leg_dash
    does). Checkpoint before the draw_leg_results call."""
    rng = random.Random(0x0D)
    mem_base, buf_c, buf_a = 0x50000, 0x60000, 0x90000
    A_MEM_BASE = 0x18bfc
    p = {
        A_INT_FRAME_HI: (0x19).to_bytes(2, "big"),
        A_LEG_INDEX: (2).to_bytes(2, "big"),                # -> 3 (< 5): advance, not restart
        mem_base: bytes(rng.randrange(256) for _ in range(0x2000)),
        buf_c: bytes(rng.randrange(256) for _ in range(0x14000)),
        buf_a + 0x7f8: bytes(rng.randrange(256) for _ in range(0x40)),
        A_MEM_BASE: mem_base.to_bytes(4, "big"),
        A_BUF_A: buf_a.to_bytes(4, "big"),
        A_BUF_C: buf_c.to_bytes(4, "big"),
    }
    diffs, info = differential(INT_PHASED_BODY, {"_pokes": p},
                               lambda l, b: l.g_int_stepD_counter(b), stop_pc=INT_PHASED_DRAW)
    assert not diffs, f"advance\n{report(diffs[:16])}"
    assert info["ret"] == INT_D_ADVANCE, f"ret={info['ret']} (expected advance)"

