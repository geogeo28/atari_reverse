"""Differential test for init_playfield @ 0x12af6 (the leg-select / playfield-init loop).

The loop shows the leg-results screen, lets the player pick a leg with the joystick and start it
with fire, and idles into the attract demo (intermission) if left alone. It returns only when a leg
is started, so it is verified two ways (mirroring intermission's mid-entry treatment):

  * test_run — full run-to-rts from the real entry with fire staged (input_state = fire, input_prev
    clear). This exercises the prologue + one per-frame iteration (all through the verified draw
    callees) + the fire-start path + the 121-frame palette-flash "get ready" animation, diffing the
    whole image. The GEMDOS-console function-key menu is unreachable under the no-key model (Crawio
    -> 0), so control always takes the default redraw; see src/intermission.c.

  * test_nav — the joystick-navigation slice (0x2c00 tail): enter the oracle at 0x2c00 and diff at
    the idle-countdown dbf checkpoint (0x2c78). Fuzzes leg_index, the two auto-repeat delays, the
    direction bits and the input-change refill so every leg-step / clamp / delay branch is covered.
    Fire is never freshly pressed here (so control reaches the checkpoint rather than starting).
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12af6
NAV_ENTRY = 0x12c00        # joystick tail (after the default redraw)
NAV_STOP = 0x12c78         # move.w idle_countdown,d0 — just before the dbf

# --- globals (Ghidra addresses) ---
A_TIMEOUT_GATE = 0x18c3e
A_LEG_DEC_DELAY, A_LEG_INC_DELAY, A_IDLE = 0x18c62, 0x18c64, 0x18c66
A_LEG_INDEX, A_INPUT_STATE, A_INPUT_PREV = 0x18c38, 0x18c44, 0x18c42
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4
A_MEM_BASE, A_BUF_A, A_BUF_C = 0x18bfc, 0x18c00, 0x18c08

# --- memory map (non-overlapping, all below the stack guard) ---
SCREEN0, SCREEN1 = 0x20000, 0x30000        # physbase_tbl[0] / physbase_tbl[4]; each ~0x8000
SCREEN_SPAN = 0x8000
BUF_C, BUF_C_SPAN = 0x40000, 0x1a000       # dashboard build + result/num sprite sources
BUF_A = 0x60000                            # per-leg label/marker/digit records
MEM_BASE, MEM_SPAN = 0x70000, 0x2000       # raw per-leg dashboard block (mem_base + leg*0x500)

# buf_a record offsets (from the callee tests: leg_dash / leg_labels / leg_results)
MARKER_TBL = 0x7f8     # init_leg_dash seeds dash_marker from buf_a + this + leg*4
CLEAR_TBL = 0x7d0      # draw_leg_labels clear record (leg*8)
DIGITS_OFF = 0x884     # draw_leg_results digit string (leg*0xc)
LABEL_DESC_TBL = 0x8c0  # draw_leg_labels label descriptor (leg*0x10)

INPUT_FIRE = 0x80
SEL_REPEAT = 3         # auto-repeat delay reload (mirrors IP_SEL_REPEAT); benign for a fire-only frame
LEG_COUNT = 5          # legs 0..4

for _n in ("g_init_playfield", "g_init_playfield_nav"):
    getattr(harness._lib, _n).argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    getattr(harness._lib, _n).restype = None
harness._lib.g_init_playfield_fire.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_init_playfield_fire.restype = ctypes.c_int


def _bounded_marker(rng):
    """A dashboard progress-marker long {y: byte<=0xf0, bit: byte<=0xf, x: word<=0x400} — kept in
    range so probe_collision's neighbour walk stays inside the staged buf_c arena."""
    return bytes([rng.randint(0, 0xf0), rng.randint(0, 0xf)]) + rng.randint(0, 0x400).to_bytes(2, "big")


def _label_desc(rng):
    """A well-formed label descriptor: word dst offset, glyph byte-pairs (c1 != 0, c2), 0 terminator."""
    desc = rng.randint(0, 0x400).to_bytes(2, "big")
    for _ in range(rng.randint(1, 5)):
        desc += bytes([rng.randint(1, 255), rng.randint(0, 255)])
    return desc + b"\x00"


def _clear_rec(rng):
    """A clear record: word dst offset (bounded, sign-extended into buf_c) then two AND masks — kept
    in range so draw_leg_labels' clear writes stay inside the staged buf_c arena."""
    return (rng.randint(0, 0x400).to_bytes(2, "big")
            + rng.randint(0, 0xffff).to_bytes(2, "big")
            + rng.randint(0, 0xffff).to_bytes(2, "big"))


def _world(seed, leg):
    """Stage the union of what every reachable callee reads (init_leg_dash, draw_leg_results,
    draw_panel5, draw_leg_labels, probe_collision) plus the leg-select globals with fire staged."""
    rng = random.Random(seed)
    pokes = {
        # buffer bases + pointers
        A_MEM_BASE: MEM_BASE.to_bytes(4, "big"),
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_PHYSBASE: SCREEN0.to_bytes(4, "big") + SCREEN1.to_bytes(4, "big"),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        # source arenas (noise; fills/blits overwrite what they own)
        MEM_BASE: bytes(rng.randrange(256) for _ in range(MEM_SPAN)),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        SCREEN0: bytes(rng.randrange(256) for _ in range(SCREEN_SPAN)),
        SCREEN1: bytes(rng.randrange(256) for _ in range(SCREEN_SPAN)),
        BUF_A + 0x7d0: bytes(rng.randrange(256) for _ in range(0x130)),   # 0x7d0..0x900 records region
        # bounded per-leg records overlaid on the noise
        BUF_A + MARKER_TBL + leg * 4: _bounded_marker(rng),
        BUF_A + CLEAR_TBL + leg * 8: _clear_rec(rng),
        BUF_A + DIGITS_OFF + leg * 0xc: bytes([1, 2, 3, 0]),
        BUF_A + LABEL_DESC_TBL + leg * 0x10: _label_desc(rng),
        # leg-select state: pick this leg, press fire (no direction) -> start on the first frame
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        A_INPUT_STATE: INPUT_FIRE.to_bytes(2, "big"),
        A_INPUT_PREV: (0).to_bytes(2, "big"),
        A_LEG_DEC_DELAY: SEL_REPEAT.to_bytes(2, "big"),
        A_LEG_INC_DELAY: SEL_REPEAT.to_bytes(2, "big"),
        A_TIMEOUT_GATE: (0).to_bytes(2, "big"),
    }
    return pokes


def test_run():
    """Full run-to-rts: prologue + one per-frame iteration + fire-start + palette-flash animation."""
    for i, leg in enumerate((0, 2, 4)):
        regs = {"_pokes": _world(seed=i, leg=leg)}
        diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_init_playfield(b), max_insns=8_000_000)
        assert not diffs, f"leg={leg}\n{report(diffs[:16])}"


# --- navigation slice ---------------------------------------------------------------------------
# Direction bits: up 1, down 2, left 4, right 8 (fire 0x80 deliberately never set here).
NAV_DIRS = (0, 1, 2, 4, 8, 1 | 8, 2 | 4)         # none / each direction / conflicting combos
NAV_DELAYS = (0, 1)                               # 0 -> expires (steps), 1 -> not yet


def _nav_pokes(leg, dec_delay, inc_delay, dirs, prev):
    return {
        A_LEG_INDEX: (leg & 0xffff).to_bytes(2, "big"),
        A_LEG_DEC_DELAY: (dec_delay & 0xffff).to_bytes(2, "big"),
        A_LEG_INC_DELAY: (inc_delay & 0xffff).to_bytes(2, "big"),
        A_INPUT_STATE: (dirs & 0xffff).to_bytes(2, "big"),
        A_INPUT_PREV: (prev & 0xffff).to_bytes(2, "big"),
        A_IDLE: (0x100).to_bytes(2, "big"),        # distinct from the refill value so a refill shows
    }


def test_nav():
    for leg in range(LEG_COUNT):
        for dec_delay in NAV_DELAYS:
            for inc_delay in NAV_DELAYS:
                for dirs in NAV_DIRS:
                    for prev in (dirs, dirs ^ 1):    # equal (no refill) and differing (refill)
                        pokes = _nav_pokes(leg, dec_delay, inc_delay, dirs, prev)
                        diffs, _ = differential(NAV_ENTRY, {"_pokes": pokes},
                                                lambda l, b: l.g_init_playfield_nav(b),
                                                stop_pc=NAV_STOP)
                        assert not diffs, (f"leg={leg} dec={dec_delay} inc={inc_delay} "
                                           f"dirs={dirs:#x} prev={prev:#x}\n{report(diffs[:12])}")


# --- fire edge ----------------------------------------------------------------------------------
# The fire check (0x2c6c) reads the previous/current input snapshots from d0/d7 and branches: a
# *fresh* fire press (prev bit7 clear, cur bit7 set) starts the leg (jumps to 0x2c96); a held fire,
# a released fire, or no fire falls through to the idle-countdown dbf (0x2c78). Enter the oracle at
# the check with the two snapshots in d0/d7 (and mirrored in memory for the candidate), then diff at
# whichever branch target the decision selects — the PC reached proves the oracle's branch and the
# glue's return proves the candidate agrees. No memory is written between 0x2c6c and either target.
FIRE_ENTRY = 0x12c6c
FIRE_START_PC = 0x12c96    # fresh press -> start the selected leg
FIRE_WAIT_PC = 0x12c78     # otherwise -> idle-countdown dbf

FIRE_CASES = (
    # (input_prev, input_state, expect_start, stop_pc)
    (0x00, INPUT_FIRE, 1, FIRE_START_PC),          # fresh press -> start
    (INPUT_FIRE, INPUT_FIRE, 0, FIRE_WAIT_PC),     # held (already down) -> keep waiting
    (INPUT_FIRE, 0x00, 0, FIRE_WAIT_PC),           # released -> keep waiting
    (0x00, 0x00, 0, FIRE_WAIT_PC),                 # no fire -> keep waiting
    (0x00, INPUT_FIRE | 4, 1, FIRE_START_PC),      # fresh press with a direction also held -> start
)


def test_fire_edge():
    for prev, state, expect, stop in FIRE_CASES:
        regs = {"d0": prev, "d7": state,
                "_pokes": {A_INPUT_PREV: prev.to_bytes(2, "big"), A_INPUT_STATE: state.to_bytes(2, "big")}}
        diffs, info = differential(FIRE_ENTRY, regs, lambda l, b: l.g_init_playfield_fire(b), stop_pc=stop)
        assert not diffs, f"prev={prev:#x} state={state:#x}\n{report(diffs[:8])}"
        assert info["ret"] == expect, f"prev={prev:#x} state={state:#x}: ret={info['ret']} (expected {expect})"
