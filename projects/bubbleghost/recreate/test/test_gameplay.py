"""Differential tests for the in-room simulation (src/gameplay.c).

WHAT IS HERE. `get_pixel` @ 0x13bea and `bubble_collision_probe` @ 0x13004 — the whole hazard
model; the five routines that walk the 58-word world block (`reset_world_state` @ 0x10f20,
`save_world_p1` @ 0x13ff4 / `p2` @ 0x14158, `restore_world_p1` @ 0x13d2c / `p2` @ 0x13e90);
`itoa_padded` @ 0x114ee; a SLICE of `ghost_blow` @ 0x129b4; and SEVEN slices of
`game_frame_update` @ 0x12322.

WHY `game_frame_update` IS SEVEN CASES AND NOT ONE. Two regions of it cannot be run here, and
neither limit is this reconstruction's (src/gameplay.c's header comment has the argument):
its front-end poll (`vq_mouse` @ 0x16a26 and `vq_key_s` @ 0x16a5e, plus the `Crawio` key read) is
the front-end subsystem's unported VDI binding, and its death sequence at 0x1273c draws the two
sprites through `src/blit.c`'s unported `vro_cpyfm` routines. So each slice is entered at its own
PC and diffed at the next one's, and the two gaps are STATUS.md residuals rather than code nobody
ran.

THE WORK BUFFER IS THE CASE'S OWN INPUT. `get_pixel` reads `screen_back`, which the game takes
from XBIOS `Logbase` — answered by the model with 0x8000, so the game's `Logbase - 0x7d00` would
land on the harness-poked input block (STATUS.md, "Model gaps"). Every case that reads a pixel
therefore pokes `screen_back` itself, into `test/abi.py`'s scratch map.

NO POISON PASS ON THE COLLISION PROBE. `probe_phase` is a read-modify-write counter AND the index
the eight probes are read at, so pre-inverting it steers the run somewhere else instead of catching
a coincidence (docs/agent-playbook.md §8). The routines that only WRITE — the world block's five,
`itoa_padded` — are run under poison.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import report

# ---- entry addresses (Ghidra == run-time; see README.md, "The image model") --------------------
ENTRY_RESET_WORLD_STATE = 0x10f20
ENTRY_ITOA_PADDED = 0x114ee
ENTRY_GHOST_BLOW = 0x129b4
STOP_GHOST_BLOW_BODY = 0x12ff8          # the `jsr hud_draw_counters` that ends the candle script
ENTRY_BUBBLE_COLLISION_PROBE = 0x13004
ENTRY_RESTORE_WORLD_P1 = 0x13d2c
ENTRY_RESTORE_WORLD_P2 = 0x13e90
ENTRY_GET_PIXEL = 0x13bea
ENTRY_SAVE_WORLD_P1 = 0x13ff4
ENTRY_SAVE_WORLD_P2 = 0x14158

# The seven slices of `game_frame_update` @ 0x12322, each entered inside the routine. A STOP is the
# first instruction NOT verified, so the slices tile the parts of the frame that can be run.
ENTRY_FRAME_ADVANCE_BUBBLE_FRAME = 0x12322
STOP_FRAME_ADVANCE_BUBBLE_FRAME = 0x1233a   # the `pea` that starts the vq_mouse call
ENTRY_FRAME_SCALE_MOUSE = 0x12434           # `cmpi.w #$23,-7674(a4)` — past the key poll
STOP_FRAME_SCALE_MOUSE = 0x124a4
ENTRY_FRAME_BLOW_OR_RECOVER = 0x124a4
STOP_FRAME_BLOW_OR_RECOVER = 0x1255c
ENTRY_FRAME_STEP_FACING = 0x1255c
STOP_FRAME_STEP_FACING = 0x125e6
ENTRY_FRAME_APPLY_FANS = 0x125e6
STOP_FRAME_APPLY_FANS = 0x126e2
ENTRY_FRAME_STEP_LIVE_BUBBLE = 0x126e2
STOP_FRAME_STEP_LIVE_BUBBLE = 0x1294a       # where every runnable path converges
ENTRY_FRAME_DRIFT_PULSE = 0x1294a
STOP_FRAME_DRIFT_PULSE = 0x129b0            # the `unlk a6`, which a mid-entry run must not reach

# The seven, in order, and the two regions between them that no slice covers — which is what
# `test_frame_slices_tile_game_frame_update` turns from prose into a pin.
FRAME_SLICES = (
    (ENTRY_FRAME_ADVANCE_BUBBLE_FRAME, STOP_FRAME_ADVANCE_BUBBLE_FRAME),
    (ENTRY_FRAME_SCALE_MOUSE, STOP_FRAME_SCALE_MOUSE),
    (ENTRY_FRAME_BLOW_OR_RECOVER, STOP_FRAME_BLOW_OR_RECOVER),
    (ENTRY_FRAME_STEP_FACING, STOP_FRAME_STEP_FACING),
    (ENTRY_FRAME_APPLY_FANS, STOP_FRAME_APPLY_FANS),
    (ENTRY_FRAME_STEP_LIVE_BUBBLE, STOP_FRAME_STEP_LIVE_BUBBLE),
    (ENTRY_FRAME_DRIFT_PULSE, STOP_FRAME_DRIFT_PULSE),
)
# `game_frame_update` ends where `ghost_blow` begins — the `unlk a6 / rts` at STOP_FRAME_DRIFT_PULSE
# is its last four bytes — so the routine's size needs no literal of its own.
FRAME_UPDATE_BYTES = ENTRY_GHOST_BLOW - ENTRY_FRAME_ADVANCE_BUBBLE_FRAME
# The ONE gap between two consecutive slices: the front-end poll, which is `src/frontend.c`'s
# `vq_mouse`/`vq_key_s` and the `Crawio(0xff)` key read (../STATUS.md, "Not reconstructed").
FRAME_FRONT_END_POLL = (STOP_FRAME_ADVANCE_BUBBLE_FRAME, ENTRY_FRAME_SCALE_MOUSE)
# ...and the region INSIDE slice 6 that no case reaches: the death sequence, which calls the three
# sprite routines. It is inside a slice rather than between two, so it is subtracted rather than
# skipped (`test_frame_step_live_bubble` never enters it — every case asserts the flag is 0).
FRAME_DEATH_SEQUENCE = (0x1273c, 0x1294a)
# What ../STATUS.md's `game_frame_update` row claims, and what the pin below re-derives.
FRAME_VERIFIED_BYTES = 902

# ---- mirrors of include/gameplay.h --------------------------------------------------------------
ROOM_COUNT = 36
ROOM_STRIDE = 120
ROOM_MAP_ROW_BYTES = 20
ROOM_MAP_CELL_BYTES = 2
ROOM_CANDLE_SFX = 0x74
OBJECT_SLOTS = 10
OBJECT_STRIDE = 14
OBJECT_ROOM_STRIDE = 140
OBJECT_TILE = 0
OBJECT_X = 6
OBJECT_Y = 8
OBJECT_FAN_TILE = 220
OBJECT_FAN_SLOT_A = 3
OBJECT_FAN_SLOT_B = 4
CANDLE_STRIDE = 12
CANDLE_FLAME_SLOT_A = 0
CANDLE_FLAME_SLOT_B = 2
CANDLE_TILE_A = 4
CANDLE_DEST_A = 6
CANDLE_TILE_B = 8
CANDLE_DEST_B = 10
PROBE_PHASES = 6
PROBE_PHASE_STRIDE = 0x20
PROBES = 8
PROBE_STRIDE = 4
PROBE_DX = 0
PROBE_DY = 2
WORLD_BLOCK_WORDS = 58
WORLD_BLOCK_CELL_BYTES = 2
GHOST_FACINGS = 8
GHOST_TILES_PER_FACING = 5
GHOST_BLOW_ANIM = 4
GHOST_IDLE_ANIM_LAST = 2
BREATH_MAX = 35
BREATH_REFILL_PER_FRAME = 3
KEY_SHIFT_NONE = 0
KEY_SHIFT_CTRL_ONLY = 4
BUBBLE_FIRST_FRAME = 4
BUBBLE_LAST_FRAME = 11
BLOW_RANGE = 50
BLOW_CONE_LIMIT = 40
BLOW_SPEED_ORTHOGONAL = 300
BLOW_SPEED_DIAGONAL = 250
CANDLE_DX_NEAR = 12
CANDLE_DX_FAR = 45
CANDLE_DY_MAX = 20
CANDLE_DY_MIN = 3
CANDLE_SCORE = 5000
DRIFT_SPEED_DECAY = 50
DRIFT_SPEED_FLOOR = 100
DRIFT_INTERVAL_MAX = 200
DRIFT_INTERVAL_DIVISOR = 10
DRIFT_VELOCITY_SCALE = 100
FAN_DX_MIN = 5
FAN_DX_MAX = 60
FAN_DY_LIMIT = 15
FAN_PUSH_PIXELS = 2
ENTRY_POINT_PIXELS = 32
PIXELS_PER_WORD = 16
PLANE_WORD_BYTES = 8
PIXEL_MSB = 15
ROOM_WIDE = 35
A_probe_table = 0x1f14a
A_object_table = 0x2069a
A_room_table = 0x21a4a
A_candle_table = 0x22b2a
A_deaths_in_room = 0x22f62
A_lives = 0x22fa8
A_hi_score = 0x22fac
A_score = 0x22fb0
A_btn_right_ready = 0x22fc2
A_btn_left_ready = 0x22fc4
A_x_impulse = 0x22fc6
A_blow_facing_plus1 = 0x22fc8
A_breath = 0x22fca
A_drift_speed = 0x22fcc
A_drift_pulse = 0x22fce
A_drift_interval = 0x22fd0
A_delta_y = 0x22fd2
A_delta_x = 0x22fd4
A_drift_dir_y = 0x22fd6
A_drift_dir_x = 0x22fd8
A_drift_vel_y = 0x22fda
A_drift_vel_x = 0x22fdc
A_probe_phase = 0x22fde
A_bubble_alive = 0x22fe0
A_ghost_anim = 0x22fe4
A_ghost_facing = 0x22fe6
A_bubble_frame = 0x22fe8
A_ghost_tile = 0x22fea
A_bubble_y = 0x22fec
A_bubble_x = 0x22fee
A_ghost_y = 0x22ff0
A_ghost_x = 0x22ff2
A_key_shift_state = 0x23116
A_mouse_y = 0x23118
A_mouse_x = 0x2311a
A_mouse_buttons = 0x2311c
A_room_number = 0x23120
A_sound_enabled = 0x2315e
A_p2_world_block = 0x231a6
A_p1_world_block = 0x2321a

# ---- mirrors of the neighbours' headers ---------------------------------------------------------
A_screen_back = 0x2314c                  # include/blit.h — the buffer `get_pixel` reads
SCREEN_ROW_BYTES = 160
SCREEN_BYTES = 32000
SCREEN_PLANES = 4
A_trap_saved_ret = 0x1e932               # include/clib.h — the trampoline's three slots
A_trap_saved_a2 = 0x1e936
A_trap_saved_a1 = 0x1e93a
A_fp_acc = 0x1ea9a
A_snd_def_fx = 0x201ca                   # include/sound.h
SND_DEF_BYTES = 0x70
A_snd_voice = 0x22daa                    # the three voice records the trigger API allocates from
SND_VOICE_BYTES = 0x8c
SND_VC_DURATION = 0x00                   # 200 Hz ticks left; 0 = idle
SND_VC_PRIORITY = 0x72                   # 0 = the voice is free, which is what gates the puff
TOS_VEC_TRAP9 = 0x00a4                   # the vector `psg_gate` @ 0x14940 dispatches through
SND_TRAP9_HANDLER_ENTRY = 0x14950

# ---- where a case stages the world --------------------------------------------------------------
# `get_pixel` reads `screen_back` with no bounds test at all, so the buffer is placed with a whole
# screen of seeded margin either side: the wrap case below deliberately reads BELOW it.
SCREEN_MARGIN = 0x9000       # wider than a screen: row 205's offset wraps to -32,736
SCREEN_BACK = abi.SCRATCH + SCREEN_MARGIN
SCREEN_TOP = SCREEN_BACK + SCREEN_BYTES
TEXT_BUFFER = SCREEN_TOP + SCREEN_MARGIN     # `itoa_padded`'s output, in memory the diff compares
TEXT_BUFFER_BYTES = 64
SCREEN_SPANS = ((abi.SCRATCH, SCREEN_TOP + SCREEN_MARGIN),)
# An all-colour-0 work buffer, which is what a room's empty cells really are (tile 50): under it no
# probe finds a hazard, so a case can drive the phase bookkeeping on its own.
BLANK_SCREEN_POKES = {A_screen_back: abi.long(SCREEN_BACK), SCREEN_BACK: bytes(SCREEN_BYTES)}

# The `trap #9` vector is zero in the post-init image — `install_sound_vectors` @ 0x148ea is what
# writes it — so any case that can reach `sound_play` has to stage it or the oracle jumps to
# address 0 (STATUS.md, "Model gaps").
TRAP9_VECTOR = {TOS_VEC_TRAP9: abi.long(SND_TRAP9_HANDLER_ENTRY)}

# ...and what the chip held on ENTRY, which is an input of the run like any other (TRAP_MODEL.md,
# Phase 6): `psg_gate` reads register 7 back to merge the mixer, and the model refuses to invent the
# bits nothing wrote. The whole file is declared rather than the registers one path happens to
# touch, so the seed is a statement about the chip and not about which branch a case takes.
PSG_ON_ENTRY = {register: (0x5a + register * 0x11) & 0xff for register in range(16)}

# The A1/A2 a slice that traps is entered with, and which its trampoline files. Distinctive rather
# than zero, so the three save slots are attributable (docs/agent-playbook.md §4).
CALLER_A1 = 0x0be511a1
CALLER_A2 = 0x0be511a2

CHUNKS = 8

_u8p = ctypes.POINTER(ctypes.c_uint8)
for _sym in ("g_bubble_collision_probe", "g_reset_world_state", "g_ghost_blow_body",
             "g_frame_advance_bubble_frame", "g_frame_scale_mouse_to_ghost",
             "g_frame_step_facing", "g_frame_apply_fans", "g_frame_drift_pulse"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None
harness._lib.g_get_pixel.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_get_pixel.restype = ctypes.c_uint32
harness._lib.g_save_world.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_save_world.restype = None
harness._lib.g_restore_world.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_restore_world.restype = None
harness._lib.g_itoa_padded.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_itoa_padded.restype = None
harness._lib.g_frame_blow_or_recover.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_frame_blow_or_recover.restype = None
harness._lib.g_frame_step_live_bubble.argtypes = [_u8p]
harness._lib.g_frame_step_live_bubble.restype = ctypes.c_uint32


# ================================================================================ staging helpers

def word_pokes(pairs):
    """One poke dict from `{address: signed word}`."""
    return {address: abi.word(value) for address, value in pairs.items()}


def screen_pokes(seed, extra=None):
    """Noise over the work buffer and its margins, then the pointer `get_pixel` reads it through."""
    return abi.merge_pokes(abi.seed_spans(seed, SCREEN_SPANS, guard=abi.GUARD_BYTES),
                           {A_screen_back: abi.long(SCREEN_BACK)}, extra or {},
                           allow_overlap=True)


def cell_planes(colours):
    """The four plane words of one 16-pixel cell, `colours[k]` being pixel k's index.

    Written from the ST's own interleaved layout rather than from `src/gameplay.c`: plane p's bit
    `15 - k` is bit p of pixel k's colour, and the four words sit one after the other.
    """
    planes = [0] * SCREEN_PLANES
    for pixel, colour in enumerate(colours):
        for plane in range(SCREEN_PLANES):
            if (colour >> plane) & 1:
                planes[plane] |= 1 << (PIXEL_MSB - pixel)
    return b"".join(abi.word(plane) for plane in planes)


# One differential, with the `a4` every function of this program is entered on. `abi.run_with_a4`
# IS that, so this is its name in this file and not a second copy of it: the two batteries that used
# to wrap it had byte-identical bodies.
_run = abi.run_with_a4


# ==================================================================================== get_pixel
#
# It writes nothing at all, so the image diff is vacuous here and the ANSWER is the whole test:
# every case below compares the candidate's return against the oracle's D0 low word, which is what
# the Alcyon ABI makes a `short` result.

def _get_pixel_case(x, y, pokes, name):
    diffs, info = _run(ENTRY_GET_PIXEL,
                       lambda lib, buf: lib.g_get_pixel(buf, x & 0xffffffff, y & 0xffffffff),
                       # `pokes` already CARRIES an overlap of its own (the case's row or cell
                       # content over `seed_spans`' noise, the later entry winning), so re-merging
                       # it byte-checked would refuse it. The arguments land at 4(A7), far from any
                       # of it — nothing this call adds overlaps anything.
                       abi.merge_pokes(pokes, abi.stack_args((2, x), (2, y)),
                                       allow_overlap=True))
    assert not diffs, f"{name} ({x}, {y})\n{report(diffs)}"
    assert info["ret"] & 0xffff == info["regs"]["d0"] & 0xffff, (
        f"{name} ({x}, {y}): candidate d0.w = {info['ret'] & 0xffff:#x}, "
        f"oracle d0.w = {info['regs']['d0'] & 0xffff:#x}")
    return info["ret"] & 0xffff


COLOUR_INDICES = 16


def _uniform_row(colour_of_cell):
    """A whole 320-pixel row, cell c filled with `colour_of_cell(c)` in every pixel."""
    return b"".join(cell_planes([colour_of_cell(cell)] * PIXELS_PER_WORD)
                    for cell in range(320 // PIXELS_PER_WORD))


@pytest.mark.parametrize("colour", range(COLOUR_INDICES))
def test_get_pixel_reads_every_colour_index(colour):
    """Cell c of one row is filled with colour c, and cell `colour` is probed. All sixteen indices,
    so a plane read in the wrong order or a missing plane disagrees on most of them."""
    row = 3
    pokes = screen_pokes(0x13be0,
                         {SCREEN_BACK + row * SCREEN_ROW_BYTES: _uniform_row(lambda cell: cell)})
    assert _get_pixel_case(colour * PIXELS_PER_WORD, row, pokes, "colour index") == colour


@pytest.mark.parametrize("pixel", range(PIXELS_PER_WORD))
def test_get_pixel_counts_bits_from_the_left(pixel):
    """One cell whose pixel k holds colour k: bit 15 is the LEFTMOST pixel, so a reconstruction
    counting from the other end reads the row backwards."""
    row, cell = 4, 2
    colours = list(range(PIXELS_PER_WORD))
    pokes = screen_pokes(0x13be1,
                         {SCREEN_BACK + row * SCREEN_ROW_BYTES + cell * PLANE_WORD_BYTES:
                          cell_planes(colours)})
    assert _get_pixel_case(cell * PIXELS_PER_WORD + pixel, row, pokes, "bit order") == pixel


@pytest.mark.parametrize("row", (0, 1, 79, 159, 191))
def test_get_pixel_row_and_cell_addressing(row):
    """The same colour ladder on several rows: a wrong row stride or a wrong cell stride reads a
    neighbour's noise instead."""
    pokes = screen_pokes(0x13be2 + row,
                         {SCREEN_BACK + row * SCREEN_ROW_BYTES:
                          _uniform_row(lambda cell: (cell * 7 + row) % COLOUR_INDICES)})
    for cell in (0, 5, 19):
        expected = (cell * 7 + row) % COLOUR_INDICES
        assert _get_pixel_case(cell * PIXELS_PER_WORD + 3, row, pokes, "addressing") == expected


@pytest.mark.parametrize("x", (-1, -2, -15, -16, -17, -32))
def test_get_pixel_negative_x(x):
    """`divs.w #$10` truncates TOWARD ZERO, so a negative x lands on the cell to its right and the
    bit index runs past 15 into the plane word's zero-extended high half. A reconstruction that
    floor-divided, or that masked the bit index to four bits, answers differently."""
    _get_pixel_case(x, 3, screen_pokes(0x13be8), "negative x")


@pytest.mark.parametrize("y", (200, 205, 300, -1))
def test_get_pixel_row_offset_wraps_in_a_signed_word(y):
    """`muls.w #$a0` then `ext.l` throws the product's high word away, so row 205 reads 32,736
    bytes BELOW the buffer rather than 32,800 above it. The buffer is staged a margin up so that
    the wrapped address still lands on seeded noise."""
    _get_pixel_case(7, y, screen_pokes(0x13be9), "row wrap")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_get_pixel_fuzz(chunk):
    """Random probes over noise. Chunk-SEEDED: each shard draws its own (abi.shard's docstring)."""
    rng = random.Random(0x13bea + chunk)
    pokes = screen_pokes(0x13bf0 + chunk)
    for _ in range(12):
        _get_pixel_case(rng.randrange(-64, 384), rng.randrange(-8, 208), pokes, "fuzz")


# ======================================================================= bubble_collision_probe

def probe_offsets(image, phase):
    """The eight (dx, dy) pairs of `probe_table[phase]`, read out of the loaded image.

    Read rather than transcribed: the table is `init_globals`' output and the point of the cases
    below is the ADDRESSING, not the numbers.
    """
    base = A_probe_table + phase * PROBE_PHASE_STRIDE
    return [(int.from_bytes(image[base + i * PROBE_STRIDE + PROBE_DX:][:2], "big", signed=True),
             int.from_bytes(image[base + i * PROBE_STRIDE + PROBE_DY:][:2], "big", signed=True))
            for i in range(PROBES)]


def _probe_case(pokes, name, **kwargs):
    diffs, _info = _run(ENTRY_BUBBLE_COLLISION_PROBE,
                        lambda lib, buf: lib.g_bubble_collision_probe(buf), pokes, **kwargs)
    assert not diffs, f"{name}\n{report(diffs)}"


@pytest.mark.parametrize("phase", (0, 1, 2, 3, 4, 5, 6, -1, 0x7fff))
def test_probe_phase_steps_before_it_is_used(phase):
    """The phase is incremented FIRST and the wrap tests the value the frame arrived with, so the
    phases actually probed run 1, 2, 3, 4, 5, 0 — and a phase outside 0..5 keeps counting up
    instead of being clamped. Over an all-zero screen, so nothing pops and the write is the test."""
    pokes = abi.merge_pokes(
        BLANK_SCREEN_POKES,
        word_pokes({A_probe_phase: phase, A_bubble_x: 40, A_bubble_y: 40,
                    A_bubble_alive: 1, A_bubble_frame: 7}))
    _probe_case(pokes, f"phase {phase}")


@pytest.mark.parametrize("probe", range(PROBES))
def test_probe_pops_the_bubble_on_a_non_zero_pixel(probe, post_init_image):
    """One non-background pixel under exactly one of the eight rim offsets. Driven probe by probe,
    so a reconstruction that read the pairs at the wrong stride — or that stopped after the first
    — is wrong on all but one of the eight."""
    phase, bubble_x, bubble_y = 1, 48, 32
    dx, dy = probe_offsets(post_init_image, phase)[probe]
    x, y = bubble_x + dx, bubble_y + dy
    cell = x // PIXELS_PER_WORD
    colours = [0] * PIXELS_PER_WORD
    colours[x % PIXELS_PER_WORD] = 9
    pokes = abi.merge_pokes(
        BLANK_SCREEN_POKES,
        {SCREEN_BACK + y * SCREEN_ROW_BYTES + cell * PLANE_WORD_BYTES: cell_planes(colours)},
        word_pokes({A_probe_phase: phase - 1, A_bubble_x: bubble_x, A_bubble_y: bubble_y,
                    A_bubble_alive: 1, A_bubble_frame: 7}),
        allow_overlap=True)
    _probe_case(pokes, f"probe {probe}")


def test_probe_phase_offset_wraps_in_a_signed_word():
    """`muls.w #$20` then `adda.w` reduces the phase offset to a WORD, so phase 1024 reads the
    table 32,768 bytes BELOW itself rather than above.

    The game's own phase never leaves 0..5, so nothing in its data reaches this — the case builds
    it: eight probe pairs are poked at the word-truncated address and one non-background pixel is
    placed under the first of them, while the 32-bit address is left holding zeroes. A
    reconstruction that added the offset in 32 bits reads eight (0, 0) probes at the bubble's own
    corner instead and pops nothing. Measured — the 32-bit form passed all 368 other cases.
    """
    phase, bubble_x, bubble_y = 1024, 48, 32
    wrapped_table = A_probe_table + (phase * PROBE_PHASE_STRIDE & 0xffff) - 0x10000
    probe_dx, probe_dy = 21, 9
    x, y = bubble_x + probe_dx, bubble_y + probe_dy
    colours = [0] * PIXELS_PER_WORD
    colours[x % PIXELS_PER_WORD] = 5
    pokes = abi.merge_pokes(
        BLANK_SCREEN_POKES,
        {SCREEN_BACK + y * SCREEN_ROW_BYTES + (x // PIXELS_PER_WORD) * PLANE_WORD_BYTES:
         cell_planes(colours)},
        {wrapped_table: (abi.word(probe_dx) + abi.word(probe_dy)) * PROBES},
        word_pokes({A_probe_phase: phase - 1, A_bubble_x: bubble_x, A_bubble_y: bubble_y,
                    A_bubble_alive: 1, A_bubble_frame: 7}),
        allow_overlap=True)
    _probe_case(pokes, "phase offset wrap")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_probe_fuzz(chunk):
    """Random bubble positions and phases over a noisy screen — where almost every probe hits, so
    what this pins is WHICH probe hits first and the phase bookkeeping around it."""
    rng = random.Random(0x13004 + chunk)
    for _ in range(12):
        pokes = screen_pokes(
            0x13010 + chunk * 100 + rng.randrange(64),
            word_pokes({A_probe_phase: rng.randrange(-2, 9),
                        A_bubble_x: rng.randrange(-16, 300),
                        A_bubble_y: rng.randrange(-16, 140),
                        A_bubble_alive: rng.choice((0, 1)),
                        A_bubble_frame: rng.randrange(0, 13)}))
        _probe_case(pokes, f"fuzz chunk {chunk}")


# ================================================================== the 58-word world block
#
# `reset_world_state` and the four save/restore routines all walk ONE list of 58 table cells, so
# what these cases pin is the LIST — its addresses, its order, and the fact that the block is
# filled backwards. The three tables are contiguous in the bss (object, then room, then candle), so
# noise over all of them is one span, and both players' blocks are another.

WORLD_TABLE_SPAN = (A_object_table, A_candle_table + ROOM_COUNT * CANDLE_STRIDE)
WORLD_BLOCK_SPAN = (A_p2_world_block,
                    A_p1_world_block + WORLD_BLOCK_WORDS * WORLD_BLOCK_CELL_BYTES)
WORLD_SPANS = (WORLD_TABLE_SPAN, WORLD_BLOCK_SPAN)

_WORLD_ROUTINES = {
    "reset_world_state": (ENTRY_RESET_WORLD_STATE,
                          lambda lib, buf: lib.g_reset_world_state(buf)),
    "save_world_p1": (ENTRY_SAVE_WORLD_P1,
                      lambda lib, buf: lib.g_save_world(buf, A_p1_world_block)),
    "save_world_p2": (ENTRY_SAVE_WORLD_P2,
                      lambda lib, buf: lib.g_save_world(buf, A_p2_world_block)),
    "restore_world_p1": (ENTRY_RESTORE_WORLD_P1,
                         lambda lib, buf: lib.g_restore_world(buf, A_p1_world_block)),
    "restore_world_p2": (ENTRY_RESTORE_WORLD_P2,
                         lambda lib, buf: lib.g_restore_world(buf, A_p2_world_block)),
}


def _world_case(name, seed, poison=False):
    entry, glue = _WORLD_ROUTINES[name]
    pokes = abi.seed_spans(seed, WORLD_SPANS, guard=abi.GUARD_BYTES)
    diffs, _info = _run(entry, glue, pokes, poison=poison)
    assert not diffs, f"{name} seed={seed:#x}\n{report(diffs)}"


@pytest.mark.parametrize("name", sorted(_WORLD_ROUTINES))
@pytest.mark.parametrize("seed", (1, 2, 3))
def test_world_block_routine(name, seed):
    """Noise over the three tables and both blocks: a cell at the wrong address, or a block word at
    the wrong end, moves a byte the diff sees."""
    _world_case(name, 0x10f20 + seed)


@pytest.mark.parametrize("name", sorted(_WORLD_ROUTINES))
def test_world_block_routine_attribution(name):
    """The poison pass: every byte the oracle wrote is pre-inverted, so a candidate that "matched"
    by leaving a cell that already held the right word now differs (docs/agent-playbook.md §4)."""
    _world_case(name, 0x10f30, poison=True)


def test_world_block_is_filled_backwards(post_init_image):
    """The blocks are written in DESCENDING address order, so entry 0 of the list is the block's
    LAST word. Save into a block whose 58 words are all distinct, then restore into tables that are
    all distinct, and the two directions have to agree — a reconstruction that filled the block
    forwards passes neither."""
    numbered = b"".join(abi.word(0x100 + index) for index in range(WORLD_BLOCK_WORDS))
    pokes = abi.merge_pokes(
        abi.seed_spans(0x10f40, WORLD_SPANS, guard=abi.GUARD_BYTES),
        {A_p1_world_block: numbered, A_p2_world_block: numbered},
        allow_overlap=True)
    for name in ("save_world_p1", "restore_world_p1", "save_world_p2", "restore_world_p2"):
        entry, glue = _WORLD_ROUTINES[name]
        diffs, _info = _run(entry, glue, pokes)
        assert not diffs, f"{name}\n{report(diffs)}"


# ============================================================================= itoa_padded
#
# The buffer is a caller stack local in the game — inside the band the differential drops — so the
# cases put it in the scratch map instead, where every byte it writes is compared.

ITOA_SPAN = ((TEXT_BUFFER, TEXT_BUFFER + TEXT_BUFFER_BYTES),)


def _itoa_case(value, width, seed, poison=False):
    pokes = abi.merge_pokes(abi.seed_spans(seed, ITOA_SPAN, guard=abi.GUARD_BYTES),
                            abi.stack_args((4, value), (4, TEXT_BUFFER), (2, width)))
    diffs, _info = _run(ENTRY_ITOA_PADDED,
                        lambda lib, buf: lib.g_itoa_padded(buf, value & 0xffffffff, TEXT_BUFFER,
                                                           width & 0xffff),
                        pokes, poison=poison)
    assert not diffs, f"itoa_padded({value}, w={width})\n{report(diffs)}"


@pytest.mark.parametrize("value", (0, 1, 9, 10, 99, 100, 12345, 999999, 1000000, 0x7fffffff))
@pytest.mark.parametrize("width", (1, 6))
def test_itoa_padded(value, width):
    """The HUD's four counters, at every digit count they reach and past it. A field WIDER than the
    number is zero-padded; a number wider than the field is not truncated."""
    _itoa_case(value, width, 0x114ee + width)


@pytest.mark.parametrize("value", (-1, -12345, -0x80000000))
def test_itoa_padded_negative(value):
    """`c_ldiv` is SIGNED, so a negative value yields negative remainders and the routine writes
    `'0' + remainder` — characters below '0'. It has no minus-sign path at all; the HUD never hands
    it a negative because `hud_draw_counters` clamps `lives` first."""
    _itoa_case(value, 6, 0x114f0)


@pytest.mark.parametrize("width", (0, 2, 8))
def test_itoa_padded_width_edges(width):
    """A width of 0 pads nothing and a width past the digit count pads to it; the terminator lands
    after the padding either way, which is what the reversal then re-measures."""
    _itoa_case(42, width, 0x114f2 + width)


def test_itoa_padded_attribution():
    """Poison: the buffer is noise the oracle overwrote, so a candidate that wrote nothing at all
    would have matched on a zeroed buffer and cannot here."""
    _itoa_case(90210, 6, 0x114f8, poison=True)


# ============================================================================= ghost_blow
#
# THE SLICE IS `[0x129b4, 0x12ff8)`: everything but the two redraws the candle script ends with
# (`hud_draw_counters` @ 0x113d2, which is VDI-bound, and `present_score_strip` @ 0x131f0). The
# score award itself IS inside the slice.

# The ghost sits well inside the room so that a blow window either side of it stays on screen.
GHOST_HOME_X, GHOST_HOME_Y = 100, 60

# `blow_facing_plus1` is `(ghost_tile + 1) / 5`, and a blowing ghost's tile is `facing*5 + 4` — so
# during a blow the index really is the facing plus one, which is what the switch keys on.
def blowing_tile(facing):
    return facing * GHOST_TILES_PER_FACING + GHOST_BLOW_ANIM


# One (dx, dy) per facing that lands inside its cone, chosen so the diagonal weighted sums are 0.
BLOW_HITS = {
    0: (-20, 0),      # left
    1: (-8, 16),      # down-left:  4*dx + 2*dy = 0
    2: (0, 20),       # down
    3: (15, 10),      # down-right: 2*dx - 3*dy = 0
    4: (20, 0),       # right
    5: (10, -15),     # up-right:   3*dx + 2*dy = 0
    6: (0, -20),      # up
    7: (-20, -10),    # up-left:    2*dx - 4*dy = 0
}


def live_voice_pokes(voice, priority=1):
    """`snd_voice[voice]` as a LIVE, low-priority record — what a "the voice is busy" case needs.

    Both fields matter and each closes a different hole. `sound_voice_priority` reads
    `SND_VC_PRIORITY`, and non-zero there is what makes `ghost_blow` skip the puff and
    `frame_blow_or_recover` release it; `sound_release_voice` reads `SND_VC_DURATION` and returns
    at once when it is 0. The priority is deliberately BELOW the puff's own (`BLOW_SFX_PRIORITY`,
    5) — with a higher one `sound_play` refuses the trigger by itself and a reconstruction that
    dropped the gate entirely is still byte-identical. Measured, twice: this staging began as one
    word at field 0 and a candidate with no gate at all passed all 374 cases.
    """
    return {A_snd_voice + voice * SND_VOICE_BYTES + SND_VC_DURATION: 40,
            A_snd_voice + voice * SND_VOICE_BYTES + SND_VC_PRIORITY: priority}


BLOW_VOICE = 1                   # `move.w #$1,-(a7)` @ 0x129b8 — src/gameplay.c's BLOW_VOICE


def blow_pokes(facing, delta_x, delta_y, extra=None, room=1, voice_busy=False):
    """The world a blow case is run in: a ghost, a bubble at an offset from it, and no candle.

    `candle_table[room][0]` is set to -1 unless a case overrides it, because the candle script runs
    whether or not the bubble was blown and its two redraws are outside the slice.
    """
    state = {
        A_room_number: room,
        A_ghost_x: GHOST_HOME_X, A_ghost_y: GHOST_HOME_Y,
        A_bubble_x: GHOST_HOME_X + delta_x, A_bubble_y: GHOST_HOME_Y + delta_y,
        A_ghost_tile: blowing_tile(facing),
        A_sound_enabled: 1,
        A_drift_dir_x: 0, A_drift_dir_y: 0,
        # NOT ZERO, and that is what makes the orthogonal arms observable: an orthogonal blow
        # leaves the velocity on the axis it does not move along ALONE, and against a zero it would
        # be indistinguishable from one that wrote `0 * speed` there. Measured — a reconstruction
        # that armed both axes passed all 360 cases until these two stopped being 0.
        A_drift_vel_x: 0x1234, A_drift_vel_y: 0x5678,
        # ...and so are the pulse schedule's two, for the same reason: `arm_drift` clears both, and
        # against a staged 0 that is indistinguishable from not writing them at all. Measured — a
        # reconstruction that dropped the two clears passed the whole battery until these moved.
        A_drift_speed: 0, A_drift_pulse: 0x0111, A_drift_interval: 0x0222,
        A_delta_x: 0, A_delta_y: 0, A_blow_facing_plus1: 0,
        A_candle_table + room * CANDLE_STRIDE + CANDLE_FLAME_SLOT_A: -1,
    }
    if voice_busy:
        state.update(live_voice_pokes(BLOW_VOICE))
    return abi.merge_pokes(word_pokes(state), TRAP9_VECTOR, extra or {}, allow_overlap=True)


def _blow_case(pokes, name):
    diffs, _info = _run(ENTRY_GHOST_BLOW, lambda lib, buf: lib.g_ghost_blow_body(buf), pokes,
                        stop_pc=STOP_GHOST_BLOW_BODY, psg_seed=PSG_ON_ENTRY)
    assert not diffs, f"{name}\n{report(diffs)}"


@pytest.mark.parametrize("facing", range(GHOST_FACINGS))
def test_ghost_blow_arms_every_facing(facing):
    """Each of the eight directions, with the bubble inside its cone: the drift direction, the
    velocity along each axis the direction moves on, and the fresh pulse schedule."""
    delta_x, delta_y = BLOW_HITS[facing]
    _blow_case(blow_pokes(facing, delta_x, delta_y), f"facing {facing}")


@pytest.mark.parametrize("facing", range(GHOST_FACINGS))
def test_ghost_blow_misses_the_opposite_side(facing):
    """The same offsets against the OPPOSITE facing, which no cone admits — so nothing is armed and
    only `delta_x`/`delta_y`/`blow_facing_plus1` move."""
    delta_x, delta_y = BLOW_HITS[facing]
    opposite = (facing + GHOST_FACINGS // 2) % GHOST_FACINGS
    _blow_case(blow_pokes(opposite, delta_x, delta_y), f"facing {opposite} missing")


# The facing whose own test a pure-x or pure-y offset of that sign satisfies, so that passing the
# range gate actually ARMS something and the gate is observable. Without this the extreme rows below
# clear the gate and then fall through every direction test, and a wrong gate looks identical.
GATE_FACING = {("x", 1): 4, ("x", -1): 0, ("y", 1): 2, ("y", -1): 6}


@pytest.mark.parametrize("delta", (BLOW_RANGE - 1, BLOW_RANGE, BLOW_RANGE + 1,
                                   -BLOW_RANGE + 1, -BLOW_RANGE, -BLOW_RANGE - 1, -0x8000))
@pytest.mark.parametrize("axis", ("x", "y"))
def test_ghost_blow_range_gate(delta, axis):
    """`|dx| < 50` and `|dy| < 50`, both computed with `neg.w` — and `neg.w` of the most negative
    word is ITSELF, so -32768 passes a gate that -32767 fails. A reconstruction using a total
    `abs()` rejects it. Each row faces the direction that offset would blow in, so that clearing
    the gate has a visible consequence."""
    delta_x, delta_y = (delta, 0) if axis == "x" else (0, delta)
    facing = GATE_FACING[(axis, 1 if delta > 0 else -1)]
    pokes = blow_pokes(facing, 0, 0, extra=word_pokes({
        A_bubble_x: (GHOST_HOME_X + delta_x) & 0xffff,
        A_bubble_y: (GHOST_HOME_Y + delta_y) & 0xffff}))
    _blow_case(pokes, f"range gate {axis}={delta}")


@pytest.mark.parametrize("facing,delta_x,delta_y", (
    # down-right, 2dx - 3dy: 38 admitted / 40 refused, then -38 admitted / -40 refused
    (3, 28, 6), (3, 29, 6), (3, 11, 20), (3, 10, 20),
    # down-left, 4dx + 2dy: -38 admitted / -40 refused, then +38 admitted / +40 refused
    (1, -9, -1), (1, -10, 1), (1, -6, 31), (1, -6, 32),
    # up-right, 3dx + 2dy: 38 admitted / 41 refused, then -38 admitted / -40 refused
    (5, 18, -8), (5, 19, -8), (5, 6, -28), (5, 6, -29),
    # up-left, 2dx - 4dy: 36 admitted / 40 refused, then -38 admitted / -40 refused
    (7, -6, -12), (7, -6, -13), (7, -31, -6), (7, -32, -6),
))
def test_ghost_blow_cone_boundaries(facing, delta_x, delta_y):
    """The four diagonal cones at the `bge #$28` / `ble #$ffd8` boundaries, BOTH bounds of each.

    The weights differ between the pairs (4/3/3/4) and the sums are WORD arithmetic, so each row is
    one side of one comparison. Measured: with only the down-right and down-left rows, deleting the
    cone test from the up-right and up-left arms passed the whole battery — a cone nobody drives to
    its limit is a cone nobody has tested."""
    _blow_case(blow_pokes(facing, delta_x, delta_y), f"cone {facing} ({delta_x}, {delta_y})")


@pytest.mark.parametrize("voice_busy", (False, True))
def test_ghost_blow_triggers_the_puff_only_on_an_idle_voice(voice_busy):
    """`sound_voice_priority(1) == 0` gates the puff, so holding the blow does not restart it. The
    PSG ledger and the voice record are what tell the two apart — `sound_play` writes both."""
    _blow_case(blow_pokes(4, *BLOW_HITS[4], voice_busy=voice_busy), f"voice busy={voice_busy}")


# The ten rooms whose `candle_table` record is not -1 (../notes/gameplay.md §4).
CANDLE_ROOMS = (3, 4, 5, 8, 9, 13, 14, 16, 19, 25)


def _word_in(image, address):
    """One SIGNED word out of a run's image — `abi.read_word`, under this battery's own name,
    because every word it reads back is a game word and -1 is not 0xffff here."""
    return abi.read_word(image, address, signed=True)


def flame_pixel_position(image, room):
    """Where `room`'s lit-flame object stands, in PIXELS, read out of the room's own data.

    The candle window is measured from the ghost to THIS point, so every candle case places the
    ghost relative to it rather than to a hard-coded tile.
    """
    slot = _word_in(image, A_candle_table + room * CANDLE_STRIDE + CANDLE_FLAME_SLOT_A)
    record = A_object_table + room * OBJECT_ROOM_STRIDE + slot * OBJECT_STRIDE
    return (_word_in(image, record + OBJECT_X) * ENTRY_POINT_PIXELS,
            _word_in(image, record + OBJECT_Y) * ENTRY_POINT_PIXELS)


@pytest.mark.parametrize("room", CANDLE_ROOMS)
def test_ghost_blow_extinguishes_a_candle(room, post_init_image):
    """The one scripted interaction in the game, over every room that ships with a candle.

    The ghost is placed from the room's OWN data — the lit-flame object's tile position, read out
    of the post-init image — so what the case asserts is the whole script: the window, the four
    object tiles, the two tile-map cells patched at the cells those objects occupied, the record
    retired, and the 5,000 points. The bubble is parked out of blowing range so that the only thing
    moving is the candle.
    """
    flame_x, flame_y = flame_pixel_position(post_init_image, room)
    # Centres of the two windows: delta_x in (-45, -12) and delta_y in (3, 20), both exclusive.
    ghost_x = flame_x + (CANDLE_DX_NEAR + CANDLE_DX_FAR) // 2
    ghost_y = flame_y - (CANDLE_DY_MAX + CANDLE_DY_MIN) // 2

    pokes = abi.merge_pokes(word_pokes({
        A_room_number: room,
        A_ghost_x: ghost_x, A_ghost_y: ghost_y,
        A_bubble_x: ghost_x + 200, A_bubble_y: ghost_y,   # far out of blowing range
        A_ghost_tile: blowing_tile(0),                    # facing left, the only facing that blows
        A_sound_enabled: 1,
        A_blow_facing_plus1: 0, A_delta_x: 0, A_delta_y: 0,
    }), {A_score: abi.long(1234), A_hi_score: abi.long(500000)}, TRAP9_VECTOR)
    _blow_case(pokes, f"candle in room {room}")


@pytest.mark.parametrize("delta_x,delta_y", (
    (-CANDLE_DX_NEAR, 10), (-CANDLE_DX_NEAR - 1, 10),
    (-CANDLE_DX_FAR, 10), (-CANDLE_DX_FAR + 1, 10),
    (-30, CANDLE_DY_MAX), (-30, CANDLE_DY_MAX - 1),
    (-30, CANDLE_DY_MIN), (-30, CANDLE_DY_MIN + 1),
))
def test_ghost_blow_candle_window_boundaries(delta_x, delta_y, post_init_image):
    """Each of the four `bge`/`ble` bounds of the candle window, from both sides. `delta_x` and
    `delta_y` here are the CANDLE's offset from the ghost, which is the opposite sign convention
    from the bubble's — the routine measures `candle - ghost` with the same two scratch globals."""
    room = 3
    flame_x, flame_y = flame_pixel_position(post_init_image, room)

    pokes = abi.merge_pokes(word_pokes({
        A_room_number: room,
        A_ghost_x: flame_x - delta_x, A_ghost_y: flame_y - delta_y,
        A_bubble_x: flame_x + 200, A_bubble_y: flame_y,
        A_ghost_tile: blowing_tile(0),
        A_sound_enabled: 1,
    }), {A_score: abi.long(0), A_hi_score: abi.long(0)}, TRAP9_VECTOR)
    _blow_case(pokes, f"candle window ({delta_x}, {delta_y})")


@pytest.mark.parametrize("facing", (1, 4, 7))
def test_ghost_blow_candle_needs_the_left_facing(facing, post_init_image):
    """Only `blow_facing_plus1 == 1` — the ghost facing left — extinguishes anything, however well
    placed the candle is."""
    room = 3
    flame_x, flame_y = flame_pixel_position(post_init_image, room)

    pokes = abi.merge_pokes(word_pokes({
        A_room_number: room,
        A_ghost_x: flame_x + 28, A_ghost_y: flame_y - 11,
        A_bubble_x: flame_x + 228, A_bubble_y: flame_y,
        A_ghost_tile: blowing_tile(facing),
        A_sound_enabled: 1,
    }), {A_score: abi.long(0), A_hi_score: abi.long(0)}, TRAP9_VECTOR)
    _blow_case(pokes, f"candle with facing {facing}")


def test_ghost_blow_candle_patch_can_move_the_room_number(post_init_image):
    """The FIRST map patch stores into `A_room_number`, and everything after it uses the new room.

    `room_table[room].map[y][x]`'s column offset is `adda.w`-truncated, so a tile column of 2923 in
    room 0 puts `map[0][2923]` at exactly `A_room_number` (0x21a4a + 5846 = 0x23120). The original
    re-reads `-7674(a4)` before each of its twenty-eight table accesses, so the second patch and the
    record retire then work on room 2 — the tile the first patch just wrote — while a reconstruction
    that read the room once keeps using room 0. Nothing in the shipped data reaches this; the case
    builds it, and it is the only thing that separates the two programs.
    """
    room, flame_a, flame_b = 0, 0, 1
    tile_a, tile_b = 2, 7                      # tile_a becomes the new room number
    column_onto_room_number = (A_room_number - A_room_table) // ROOM_MAP_CELL_BYTES
    candle = A_candle_table + room * CANDLE_STRIDE
    moved = A_candle_table + tile_a * CANDLE_STRIDE

    def slot_field(room_index, slot, field):
        return A_object_table + room_index * OBJECT_ROOM_STRIDE + slot * OBJECT_STRIDE + field

    pokes = abi.merge_pokes(word_pokes({
        A_room_number: room,
        candle + CANDLE_FLAME_SLOT_A: flame_a, candle + CANDLE_FLAME_SLOT_B: flame_b,
        candle + CANDLE_TILE_A: tile_a, candle + CANDLE_DEST_A: 2,
        candle + CANDLE_TILE_B: tile_b, candle + CANDLE_DEST_B: 3,
        # ...and the record the run lands on once the room has moved.
        moved + CANDLE_FLAME_SLOT_A: 4, moved + CANDLE_FLAME_SLOT_B: 1,
        slot_field(tile_a, 1, OBJECT_X): 3, slot_field(tile_a, 1, OBJECT_Y): 1,
        # The flame object sits at the column whose map cell IS `A_room_number`.
        slot_field(room, flame_a, OBJECT_X): column_onto_room_number,
        slot_field(room, flame_a, OBJECT_Y): 0,
        slot_field(room, flame_b, OBJECT_X): 1, slot_field(room, flame_b, OBJECT_Y): 1,
        A_room_table + ROOM_CANDLE_SFX: -1,    # room 0's sfx: no sound, so this is about addressing
        # The ghost, inside the candle window: delta_x = -30, delta_y = 10.
        A_ghost_x: ((column_onto_room_number * ENTRY_POINT_PIXELS) & 0xffff) + 30,
        A_ghost_y: -10,
        A_ghost_tile: blowing_tile(0),
        A_bubble_x: 300, A_bubble_y: 300,      # far out of blowing range
        A_sound_enabled: 1,
    }), {A_score: abi.long(0), A_hi_score: abi.long(0)}, TRAP9_VECTOR)
    _blow_case(pokes, "candle patch moves the room number")


def _wrapped(value):
    """`value` reduced the way an `adda.w` reduces it: its low word, read signed."""
    low = value & 0xffff
    return low - 0x10000 if low >= 0x8000 else low


@pytest.mark.parametrize("room", (469, 235))
def test_ghost_blow_candle_room_offset_is_added_in_32_bits(room):
    """`ghost_blow` reaches an object record with `muls.w #$8c` + `add.l a0,d1` — the room offset in
    FULL 32 bits — while the SLOT offset goes through an `adda.w`. The fan test at 0x125e6 does the
    opposite, and the two only disagree once `room * 140` overflows a signed word, which the game's
    own 0..35 never does.

    So this case plants the candle's flame object where the 32-BIT address points (in the arena,
    which is otherwise all zeroes) and leaves the word-truncated address holding the real object
    table. A reconstruction that truncated measures a different `delta_x`/`delta_y` and extinguishes
    nothing. Measured — the truncated form passed all 363 other cases.
    """
    flame_slot, tile_x, tile_y = 4, 5, 3
    candle_record = A_candle_table + _wrapped(room * CANDLE_STRIDE)
    object_record = (A_object_table + (room * OBJECT_ROOM_STRIDE)
                     + _wrapped(flame_slot * OBJECT_STRIDE))
    pokes = abi.merge_pokes(word_pokes({
        A_room_number: room,
        candle_record + CANDLE_FLAME_SLOT_A: flame_slot,
        candle_record + CANDLE_FLAME_SLOT_B: 5,
        candle_record + CANDLE_TILE_A: 100, candle_record + CANDLE_DEST_A: 6,
        candle_record + CANDLE_TILE_B: 101, candle_record + CANDLE_DEST_B: 7,
        # ...and no ambient sound, so the case is about the addressing and not about `sound_play`.
        A_room_table + ROOM_CANDLE_SFX + _wrapped(room * ROOM_STRIDE): -1,
        object_record + OBJECT_X: tile_x, object_record + OBJECT_Y: tile_y,
        A_ghost_x: tile_x * ENTRY_POINT_PIXELS + (CANDLE_DX_NEAR + CANDLE_DX_FAR) // 2,
        A_ghost_y: tile_y * ENTRY_POINT_PIXELS - (CANDLE_DY_MAX + CANDLE_DY_MIN) // 2,
        A_bubble_x: 300, A_bubble_y: 300,
        A_ghost_tile: blowing_tile(0),
        A_sound_enabled: 1,
    }), {A_score: abi.long(0), A_hi_score: abi.long(0)}, TRAP9_VECTOR)
    _blow_case(pokes, f"candle room offset {room}")


# ================================================================ game_frame_update, slice by slice

def _slice_case(entry, stop, glue, pokes, name, regs=None, **kwargs):
    diffs, info = _run(entry, glue, pokes, regs=regs, stop_pc=stop, **kwargs)
    assert not diffs, f"{name}\n{report(diffs)}"
    return info


@pytest.mark.parametrize("frame", (0, 1, 3, 4, 10, 11, 12, 13, -1, 0x7fff))
def test_frame_advance_bubble_frame(frame):
    """The nine bubble frames wrap 12 -> 4, and the test is on the value the frame ARRIVED with —
    so 12 is written and only then replaced, and a frame outside the range keeps counting."""
    _slice_case(ENTRY_FRAME_ADVANCE_BUBBLE_FRAME, STOP_FRAME_ADVANCE_BUBBLE_FRAME,
                lambda lib, buf: lib.g_frame_advance_bubble_frame(buf),
                word_pokes({A_bubble_frame: frame}), f"bubble frame {frame}")


@pytest.mark.parametrize("room", (0, 1, ROOM_WIDE))
@pytest.mark.parametrize("mouse", ((0, 0), (1, 1), (159, 99), (319, 199), (-1, -1), (500, 400)))
def test_frame_scale_mouse_to_ghost(room, mouse):
    """The mouse divided down onto the room area by the Alcyon software float package: 1.115 (room
    35: 1.684) horizontally and 1.577 vertically, TRUNCATED rather than rounded. The eight-byte
    accumulator is image state, so a wrong divisor or a wrong opcode diverges there first."""
    mouse_x, mouse_y = mouse
    _slice_case(ENTRY_FRAME_SCALE_MOUSE, STOP_FRAME_SCALE_MOUSE,
                lambda lib, buf: lib.g_frame_scale_mouse_to_ghost(buf),
                # ghost_x/ghost_y are staged NON-ZERO: with a mouse of (0, 0) the answer is 0 too,
                # so against a zeroed pair the whole slice could be deleted and those rows passed.
                word_pokes({A_room_number: room, A_mouse_x: mouse_x, A_mouse_y: mouse_y,
                            A_ghost_x: 0x3c3c, A_ghost_y: 0x5a5a}),
                f"room {room} mouse {mouse}")


def blow_slice_pokes(shift, breath, facing=4, anim=0, room=1, bubble_offset=(200, 0),
                     voice_busy=False):
    """The world `frame_blow_or_recover` is entered in: no candle in the room (its script ends in
    two calls outside this slice) and the bubble parked out of blowing range unless a case moves
    it."""
    delta_x, delta_y = bubble_offset
    state = {
        A_key_shift_state: shift, A_breath: breath,
        A_ghost_facing: facing, A_ghost_anim: anim, A_ghost_tile: 0,
        A_room_number: room, A_sound_enabled: 1,
        A_ghost_x: GHOST_HOME_X, A_ghost_y: GHOST_HOME_Y,
        A_bubble_x: GHOST_HOME_X + delta_x, A_bubble_y: GHOST_HOME_Y + delta_y,
        A_drift_dir_x: 0, A_drift_dir_y: 0,
        A_drift_vel_x: 0x1234, A_drift_vel_y: 0x5678,   # see `blow_pokes` — not zero, on purpose
        A_drift_speed: 0, A_drift_pulse: 0x0111, A_drift_interval: 0x0222,
        A_candle_table + room * CANDLE_STRIDE + CANDLE_FLAME_SLOT_A: -1,
    }
    if voice_busy:
        # Both arms of this slice release the puff when voice 1 is live, and with the post-init
        # priority of 0 neither `sound_release_voice` call ever fired. Measured — replacing both
        # with a no-op passed the whole battery until this knob existed.
        state.update(live_voice_pokes(BLOW_VOICE))
    return abi.merge_pokes(word_pokes(state), TRAP9_VECTOR,
                           {A_trap_saved_a1: abi.long(0), A_trap_saved_a2: abi.long(0),
                            A_trap_saved_ret: abi.long(0)})


def _blow_slice_case(pokes, name):
    return _slice_case(ENTRY_FRAME_BLOW_OR_RECOVER, STOP_FRAME_BLOW_OR_RECOVER,
                       lambda lib, buf: lib.g_frame_blow_or_recover(buf, CALLER_A1, CALLER_A2),
                       pokes, name, regs={"a1": CALLER_A1, "a2": CALLER_A2},
                       psg_seed=PSG_ON_ENTRY)


@pytest.mark.parametrize("voice_busy", (False, True))
@pytest.mark.parametrize("shift", (KEY_SHIFT_NONE, 1, 2, 3, KEY_SHIFT_CTRL_ONLY, 5, 8, 0x10))
def test_frame_blow_or_recover_shift_gate(shift, voice_busy):
    """Blowing is on while the shift mask is NEITHER 0 nor 4 — any modifier except Ctrl alone. The
    two branches leave different `ghost_anim`, `breath` and trampoline slots behind.

    `voice_busy` is what reaches the two `sound_release_voice` calls: with the post-init priority of
    0 neither ever fires, and replacing both with a no-op passed the whole battery."""
    _blow_slice_case(blow_slice_pokes(shift, breath=20, voice_busy=voice_busy),
                     f"shift {shift} voice busy={voice_busy}")


@pytest.mark.parametrize("voice_busy", (False, True))
@pytest.mark.parametrize("breath", (-1, 0, 1, 2, 20, BREATH_MAX, BREATH_MAX + 1, 0x7fff))
def test_frame_blow_or_recover_breath(breath, voice_busy):
    """The gauge, from both sides: blowing drains one and the frame it goes NEGATIVE releases the
    puff, pins the gauge at empty and issues the pink `Setcolor` — whose only reproducible effect
    is the trampoline's three save slots. Idle refills three at a time, capped at 35."""
    _blow_slice_case(blow_slice_pokes(2, breath, voice_busy=voice_busy),
                     f"blow breath {breath} voice busy={voice_busy}")
    _blow_slice_case(blow_slice_pokes(KEY_SHIFT_NONE, breath, voice_busy=voice_busy),
                     f"idle breath {breath} voice busy={voice_busy}")


@pytest.mark.parametrize("anim", (0, 1, 2, 3, 4, -1))
def test_frame_blow_or_recover_idle_animation(anim):
    """The idle walk cycle steps 0, 1, 2, 3 and wraps on the value it arrived with — so 3 is
    written and only then replaced by 0."""
    _blow_slice_case(blow_slice_pokes(KEY_SHIFT_NONE, breath=10, anim=anim), f"idle anim {anim}")


@pytest.mark.parametrize("facing", range(GHOST_FACINGS))
def test_frame_blow_or_recover_blows(facing):
    """A blowing frame with the bubble inside the facing's cone: the slice pins `ghost_anim = 4`
    and `ghost_tile = facing*5 + 4` BEFORE `ghost_blow` reads the tile back as its facing index."""
    _blow_slice_case(blow_slice_pokes(1, breath=20, facing=facing,
                                      bubble_offset=BLOW_HITS[facing]),
                     f"blow facing {facing}")


@pytest.mark.parametrize("buttons", (0, 1, 2, 3, -1))
@pytest.mark.parametrize("latches", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_frame_step_facing(buttons, latches):
    """One step per press: the facing moves on the frame the button is seen down with its latch
    armed, and the latch re-arms on the first frame that button is not the one reported."""
    left, right = latches
    pokes = abi.merge_pokes(word_pokes({A_mouse_buttons: buttons, A_ghost_facing: 3,
                                        A_ghost_anim: 2, A_ghost_tile: 0}),
                            {A_btn_left_ready: bytes([left]),
                             A_btn_right_ready: bytes([right])})
    _slice_case(ENTRY_FRAME_STEP_FACING, STOP_FRAME_STEP_FACING,
                lambda lib, buf: lib.g_frame_step_facing(buf), pokes,
                f"buttons {buttons} latches {latches}")


@pytest.mark.parametrize("facing", (0, 1, 6, 7))
@pytest.mark.parametrize("buttons", (1, 2))
def test_frame_step_facing_wraps(facing, buttons):
    """The wrap at both ends and the step JUST INSIDE each of them: 7 + 1 -> 0 but 6 + 1 stays 7,
    and 0 - 1 -> 7 but 1 - 1 stays 0. Both tests are made AFTER the store, so the out-of-range value
    is written and only then replaced — and the two rows either side are what separate `> 7` from
    `>= 7` (measured: without them a wrap one step early passes)."""
    pokes = abi.merge_pokes(word_pokes({A_mouse_buttons: buttons, A_ghost_facing: facing,
                                        A_ghost_anim: 1, A_ghost_tile: 0}),
                            {A_btn_left_ready: b"\x01", A_btn_right_ready: b"\x01"})
    _slice_case(ENTRY_FRAME_STEP_FACING, STOP_FRAME_STEP_FACING,
                lambda lib, buf: lib.g_frame_step_facing(buf), pokes,
                f"wrap facing {facing} buttons {buttons}")


def fan_pokes(room, slot, fan_tile_x, fan_tile_y, bubble_x, bubble_y, tile=OBJECT_FAN_TILE):
    """A room with one fan in `slot` and an empty slot in the other one."""
    other = OBJECT_FAN_SLOT_B if slot == OBJECT_FAN_SLOT_A else OBJECT_FAN_SLOT_A
    record = A_object_table + room * OBJECT_ROOM_STRIDE + slot * OBJECT_STRIDE
    other_record = A_object_table + room * OBJECT_ROOM_STRIDE + other * OBJECT_STRIDE
    return word_pokes({
        A_room_number: room,
        record + OBJECT_TILE: tile,
        record + OBJECT_X: fan_tile_x, record + OBJECT_Y: fan_tile_y,
        other_record + OBJECT_TILE: -1,
        A_bubble_x: bubble_x, A_bubble_y: bubble_y,
        A_drift_dir_x: 0, A_drift_vel_x: 0, A_x_impulse: 0,
        A_delta_x: 0, A_delta_y: 0,
    })


def _fan_case(pokes, name):
    _slice_case(ENTRY_FRAME_APPLY_FANS, STOP_FRAME_APPLY_FANS,
                lambda lib, buf: lib.g_frame_apply_fans(buf), pokes, name)


@pytest.mark.parametrize("slot", (OBJECT_FAN_SLOT_A, OBJECT_FAN_SLOT_B))
@pytest.mark.parametrize("delta_x,delta_y", (
    (FAN_DX_MIN, 0), (FAN_DX_MIN + 1, 0), (FAN_DX_MAX, 0), (FAN_DX_MAX - 1, 0),
    (30, -FAN_DY_LIMIT), (30, -FAN_DY_LIMIT + 1), (30, FAN_DY_LIMIT), (30, FAN_DY_LIMIT - 1),
    (30, 0),
))
def test_frame_apply_fans_window(slot, delta_x, delta_y):
    """The push region, at each of its four bounds from both sides: 5 < dx < 60 and -15 < dy < 15,
    measured from the BUBBLE to the fan. `delta_x`/`delta_y` are written whether or not the fan
    reaches, so a room with a fan leaves different scratch behind than one without."""
    fan_tile_x, fan_tile_y = 6, 3
    _fan_case(fan_pokes(7, slot, fan_tile_x, fan_tile_y,
                        fan_tile_x * ENTRY_POINT_PIXELS - delta_x,
                        fan_tile_y * ENTRY_POINT_PIXELS - delta_y),
              f"fan slot {slot} delta ({delta_x}, {delta_y})")


@pytest.mark.parametrize("tile", (OBJECT_FAN_TILE - 1, OBJECT_FAN_TILE + 1, -1, 0))
def test_frame_apply_fans_only_tile_220(tile):
    """Only tile 220 is a fan, and only in slots 3 and 4 — every other object is just pixels the
    collision probe reads. A non-fan slot writes NEITHER scratch global."""
    _fan_case(fan_pokes(7, OBJECT_FAN_SLOT_A, 6, 3, 6 * ENTRY_POINT_PIXELS - 30,
                        3 * ENTRY_POINT_PIXELS, tile=tile),
              f"tile {tile}")


def test_frame_apply_fans_second_slot_overwrites_the_scratch():
    """Both slots run, in order, and each writes the two scratch globals — so a room with a fan in
    BOTH slots leaves slot 4's measurement behind, not slot 3's."""
    room = 7
    base = A_object_table + room * OBJECT_ROOM_STRIDE
    pokes = word_pokes({
        A_room_number: room,
        base + OBJECT_FAN_SLOT_A * OBJECT_STRIDE + OBJECT_TILE: OBJECT_FAN_TILE,
        base + OBJECT_FAN_SLOT_A * OBJECT_STRIDE + OBJECT_X: 6,
        base + OBJECT_FAN_SLOT_A * OBJECT_STRIDE + OBJECT_Y: 3,
        base + OBJECT_FAN_SLOT_B * OBJECT_STRIDE + OBJECT_TILE: OBJECT_FAN_TILE,
        base + OBJECT_FAN_SLOT_B * OBJECT_STRIDE + OBJECT_X: 2,
        base + OBJECT_FAN_SLOT_B * OBJECT_STRIDE + OBJECT_Y: 1,
        A_bubble_x: 6 * ENTRY_POINT_PIXELS - 30, A_bubble_y: 3 * ENTRY_POINT_PIXELS,
        A_drift_dir_x: 0, A_drift_vel_x: 0, A_x_impulse: 0, A_delta_x: 0, A_delta_y: 0,
    })
    _fan_case(pokes, "both fan slots")


@pytest.mark.parametrize("room", (5, 8, 26, 29))
def test_frame_apply_fans_shipped_rooms(room):
    """The four rooms that really carry a fan, over the table `init_globals` built — with the
    bubble parked where the push region is, from the room's own data."""
    pokes = word_pokes({A_room_number: room, A_bubble_x: 100, A_bubble_y: 60,
                        A_drift_dir_x: 0, A_drift_vel_x: 0, A_x_impulse: 0,
                        A_delta_x: 0, A_delta_y: 0})
    _fan_case(pokes, f"shipped room {room}")


def truncated_object_field(room, slot, field):
    """Where the FAN test really looks: the room offset through an `adda.w`, i.e. its low word.

    Every object access inside `ghost_blow` adds the room offset in full 32 bits (`add.l a0,d1`);
    the fan test reaches a FIXED slot, so the compiler folded the slot into the `lea` and added the
    room offset with an `adda.w` instead. The two differ only once `room * 140` overflows a signed
    word, which the game's own 0..35 never does — so this is arithmetic that has to be pinned
    deliberately or not at all.
    """
    offset = (room * OBJECT_ROOM_STRIDE) & 0xffff
    return A_object_table + slot * OBJECT_STRIDE + field + (offset - 0x10000 if offset >= 0x8000
                                                            else offset)


@pytest.mark.parametrize("room", (235, 469, -1))
def test_frame_apply_fans_room_offset_wraps_in_a_signed_word(room):
    """A fan planted where the WORD-truncated room offset points, and nowhere else.

    Room 469's offset wraps to +124, which lands the lookup back inside the object table; room
    235's wraps negative into TEXT. A reconstruction that added the room offset in 32 bits reads
    the (zero) arena instead and finds no fan at all, so the two disagree on every byte the fan
    would have written. Measured — the 32-bit form passed all 360 other cases.
    """
    slot, fan_tile_x, fan_tile_y = OBJECT_FAN_SLOT_A, 6, 3
    other = OBJECT_FAN_SLOT_B
    pokes = word_pokes({
        A_room_number: room,
        truncated_object_field(room, slot, OBJECT_TILE): OBJECT_FAN_TILE,
        truncated_object_field(room, slot, OBJECT_X): fan_tile_x,
        truncated_object_field(room, slot, OBJECT_Y): fan_tile_y,
        truncated_object_field(room, other, OBJECT_TILE): -1,
        A_bubble_x: fan_tile_x * ENTRY_POINT_PIXELS - 30,
        A_bubble_y: fan_tile_y * ENTRY_POINT_PIXELS,
        A_drift_dir_x: 0, A_drift_vel_x: 0, A_x_impulse: 0, A_delta_x: 0, A_delta_y: 0,
    })
    _fan_case(pokes, f"fan room wrap {room}")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_frame_apply_fans_fuzz(chunk):
    """Random fan placements and bubble positions across the room. Chunk-SEEDED."""
    rng = random.Random(0x125e6 + chunk)
    for _ in range(10):
        _fan_case(fan_pokes(rng.randrange(ROOM_COUNT), rng.choice((3, 4)),
                            rng.randrange(0, 10), rng.randrange(0, 5),
                            rng.randrange(-32, 320), rng.randrange(-32, 160),
                            tile=rng.choice((OBJECT_FAN_TILE, OBJECT_FAN_TILE, -1, 50))),
                  f"fan fuzz chunk {chunk}")


# ---- slice 6: the bubble's own step -------------------------------------------------------------
# The DEAD-and-animating branch (`bubble_alive == 0` with `bubble_frame > 3`) is the death
# sequence, which draws through the VDI and never reaches this slice's stop PC — so no case below
# arms it, and STATUS.md carries it as a residual.

def bubble_step_pokes(alive, frame, vel_x=0, vel_y=0, impulse=0, blank_screen=True, seed=0x126e2):
    state = {
        A_bubble_alive: alive, A_bubble_frame: frame,
        A_bubble_x: 120, A_bubble_y: 64,
        A_drift_vel_x: vel_x, A_drift_vel_y: vel_y, A_x_impulse: impulse,
        A_probe_phase: 0, A_sound_enabled: 1,
    }
    screen = (BLANK_SCREEN_POKES if blank_screen else
              abi.merge_pokes(abi.seed_spans(seed, SCREEN_SPANS, guard=abi.GUARD_BYTES),
                              {A_screen_back: abi.long(SCREEN_BACK)}, allow_overlap=True))
    return abi.merge_pokes(word_pokes(state), screen, TRAP9_VECTOR, allow_overlap=True)


def _bubble_step_case(pokes, name):
    """One slice-6 differential, and the candidate's flag checked against 0.

    The flag says "the routine has entered the death sequence", which no case can run — so every
    case here must answer 0, and the assertion is a self-consistency check rather than a comparison
    with the oracle (the original computes no such value; STATUS.md residual 4). It is what stops
    the reconstruction from reporting a death that did not happen.
    """
    info = _slice_case(ENTRY_FRAME_STEP_LIVE_BUBBLE, STOP_FRAME_STEP_LIVE_BUBBLE,
                       lambda lib, buf: lib.g_frame_step_live_bubble(buf), pokes, name,
                       psg_seed=PSG_ON_ENTRY)
    assert info["ret"] & 0xffff == 0, (
        f"{name}: the slice answered {info['ret'] & 0xffff:#x}, i.e. it claims the run entered the "
        f"death sequence — but the run reached the stop PC, so it did not")
    return info


@pytest.mark.parametrize("vel_x,vel_y,impulse", (
    (0, 0, 0), (300, 0, 0), (-300, 0, 0), (0, 250, 0), (0, -250, 0),
    (99, 99, 0), (-99, -99, 0), (100, -100, 0), (-1, 0, -FAN_PUSH_PIXELS),
    (250, -250, -FAN_PUSH_PIXELS), (0x7fff, 0x7fff, 0),
))
def test_frame_step_live_bubble_integrates(vel_x, vel_y, impulse):
    """A live bubble over a blank screen: the velocity is in hundredths of a pixel and truncates
    toward zero (`divs.w #$64`), and the fan's impulse is added in whole pixels on x only."""
    _bubble_step_case(bubble_step_pokes(1, 7, vel_x, vel_y, impulse),
                      f"integrate ({vel_x}, {vel_y}, {impulse})")


def test_frame_step_live_bubble_pops_and_plays_the_sound():
    """A live bubble over a NOISY screen: the probe finds a non-zero pixel, clears the frame, and
    the pop sound goes out on voice 2 — which the PSG ledger and the voice record are what see."""
    _bubble_step_case(bubble_step_pokes(1, 7, blank_screen=False), "pop")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_frame_step_live_bubble_fuzz(chunk):
    """Random velocities over a noisy screen, so both arms — pop and integrate — come up."""
    rng = random.Random(0x126f0 + chunk)
    for _ in range(8):
        _bubble_step_case(
            bubble_step_pokes(1, rng.randrange(1, 13),
                              rng.randrange(-32768, 32768), rng.randrange(-32768, 32768),
                              rng.choice((0, -FAN_PUSH_PIXELS)),
                              blank_screen=rng.choice((True, False)),
                              seed=0x12700 + chunk * 64 + rng.randrange(32)),
            f"bubble fuzz chunk {chunk}")


@pytest.mark.parametrize("frame", (0, 1, 2, 3, -1))
def test_frame_step_dead_bubble_below_the_death_frame(frame):
    """A dead bubble still on an early animation frame falls straight through to the drift pulse —
    the one dead path that does not enter the death sequence."""
    _bubble_step_case(bubble_step_pokes(0, frame), f"dead frame {frame}")


# ---- slice 7: the drift pulse -------------------------------------------------------------------

def _drift_case(pulse, dir_x, dir_y, speed, interval, name):
    pokes = word_pokes({A_drift_pulse: pulse, A_drift_dir_x: dir_x, A_drift_dir_y: dir_y,
                        A_drift_speed: speed, A_drift_interval: interval,
                        A_drift_vel_x: 0x1234, A_drift_vel_y: 0x5678,
                        A_x_impulse: -FAN_PUSH_PIXELS})
    _slice_case(ENTRY_FRAME_DRIFT_PULSE, STOP_FRAME_DRIFT_PULSE,
                lambda lib, buf: lib.g_frame_drift_pulse(buf), pokes, name)


@pytest.mark.parametrize("pulse", (0, 1, 2, 20, -1, 0x7fff))
def test_frame_drift_pulse_counter(pulse):
    """The counter is tested on the value the frame ARRIVED with, so it is decremented every frame
    and fires on the frame it was already 0 — which is what makes the gap `interval / 10` frames
    and not one more."""
    _drift_case(pulse, -1, 1, 300, 0, f"pulse {pulse}")


@pytest.mark.parametrize("speed", (300, 250, 200, 150, DRIFT_SPEED_FLOOR + DRIFT_SPEED_DECAY,
                                   DRIFT_SPEED_FLOOR, DRIFT_SPEED_FLOOR - 1, 0, -0x7fff))
def test_frame_drift_pulse_speed_decay(speed):
    """50 per pulse down to a floor of 100 — the 3, 2.5, 2, 1.5, 1 pixel steps a blow gives."""
    _drift_case(0, 1, -1, speed, 0, f"speed {speed}")


@pytest.mark.parametrize("interval", (0, 9, 10, 11, 199, DRIFT_INTERVAL_MAX,
                                      DRIFT_INTERVAL_MAX + 1, -1))
def test_frame_drift_pulse_interval_growth(interval):
    """The gap grows by one per pulse to a cap of 200, and the counter reloads from `interval / 10`
    — a `divs.w`, so the reload is 0 for the first ten pulses."""
    _drift_case(0, -1, 0, 200, interval, f"interval {interval}")


@pytest.mark.parametrize("dir_x,dir_y", ((0, 0), (1, 0), (0, 1), (-1, -1), (1, -1), (2, -3)))
def test_frame_drift_pulse_velocity(dir_x, dir_y):
    """The velocity a pulse re-arms is `direction * speed` in WORD arithmetic, on BOTH axes —
    unlike the blow, which leaves the axis it does not move on alone."""
    _drift_case(0, dir_x, dir_y, 300, 50, f"dir ({dir_x}, {dir_y})")


# ================================================================================================
# The pins `test/test_constants.py` collects: every constant this battery restates, against its one
# home in the C, and every entry address against the original's own bytes.
# ================================================================================================

MIRRORS = (
    ("ROOM_COUNT", "include/gameplay.h", "ROOM_COUNT"),
    ("ROOM_STRIDE", "include/gameplay.h", "ROOM_STRIDE"),
    ("ROOM_MAP_ROW_BYTES", "include/gameplay.h", "ROOM_MAP_ROW_BYTES"),
    ("ROOM_MAP_CELL_BYTES", "include/gameplay.h", "ROOM_MAP_CELL_BYTES"),
    ("ROOM_CANDLE_SFX", "include/gameplay.h", "ROOM_CANDLE_SFX"),
    ("OBJECT_SLOTS", "include/gameplay.h", "OBJECT_SLOTS"),
    ("OBJECT_STRIDE", "include/gameplay.h", "OBJECT_STRIDE"),
    ("OBJECT_ROOM_STRIDE", "include/gameplay.h", "OBJECT_ROOM_STRIDE"),
    ("OBJECT_TILE", "include/gameplay.h", "OBJECT_TILE"),
    ("OBJECT_X", "include/gameplay.h", "OBJECT_X"),
    ("OBJECT_Y", "include/gameplay.h", "OBJECT_Y"),
    ("OBJECT_FAN_TILE", "include/gameplay.h", "OBJECT_FAN_TILE"),
    ("OBJECT_FAN_SLOT_A", "include/gameplay.h", "OBJECT_FAN_SLOT_A"),
    ("OBJECT_FAN_SLOT_B", "include/gameplay.h", "OBJECT_FAN_SLOT_B"),
    ("CANDLE_STRIDE", "include/gameplay.h", "CANDLE_STRIDE"),
    ("CANDLE_FLAME_SLOT_A", "include/gameplay.h", "CANDLE_FLAME_SLOT_A"),
    ("CANDLE_FLAME_SLOT_B", "include/gameplay.h", "CANDLE_FLAME_SLOT_B"),
    ("CANDLE_TILE_A", "include/gameplay.h", "CANDLE_TILE_A"),
    ("CANDLE_DEST_A", "include/gameplay.h", "CANDLE_DEST_A"),
    ("CANDLE_TILE_B", "include/gameplay.h", "CANDLE_TILE_B"),
    ("CANDLE_DEST_B", "include/gameplay.h", "CANDLE_DEST_B"),
    ("PROBE_PHASES", "include/gameplay.h", "PROBE_PHASES"),
    ("PROBE_PHASE_STRIDE", "include/gameplay.h", "PROBE_PHASE_STRIDE"),
    ("PROBES", "include/gameplay.h", "PROBES"),
    ("PROBE_STRIDE", "include/gameplay.h", "PROBE_STRIDE"),
    ("PROBE_DX", "include/gameplay.h", "PROBE_DX"),
    ("PROBE_DY", "include/gameplay.h", "PROBE_DY"),
    ("WORLD_BLOCK_WORDS", "include/gameplay.h", "WORLD_BLOCK_WORDS"),
    ("WORLD_BLOCK_CELL_BYTES", "include/gameplay.h", "WORLD_BLOCK_CELL_BYTES"),
    ("GHOST_FACINGS", "include/gameplay.h", "GHOST_FACINGS"),
    ("GHOST_TILES_PER_FACING", "include/gameplay.h", "GHOST_TILES_PER_FACING"),
    ("GHOST_BLOW_ANIM", "include/gameplay.h", "GHOST_BLOW_ANIM"),
    ("GHOST_IDLE_ANIM_LAST", "include/gameplay.h", "GHOST_IDLE_ANIM_LAST"),
    ("BREATH_MAX", "include/gameplay.h", "BREATH_MAX"),
    ("BREATH_REFILL_PER_FRAME", "include/gameplay.h", "BREATH_REFILL_PER_FRAME"),
    ("KEY_SHIFT_NONE", "include/gameplay.h", "KEY_SHIFT_NONE"),
    ("KEY_SHIFT_CTRL_ONLY", "include/gameplay.h", "KEY_SHIFT_CTRL_ONLY"),
    ("BUBBLE_FIRST_FRAME", "include/gameplay.h", "BUBBLE_FIRST_FRAME"),
    ("BUBBLE_LAST_FRAME", "include/gameplay.h", "BUBBLE_LAST_FRAME"),
    ("BLOW_RANGE", "include/gameplay.h", "BLOW_RANGE"),
    ("BLOW_CONE_LIMIT", "include/gameplay.h", "BLOW_CONE_LIMIT"),
    ("BLOW_SPEED_ORTHOGONAL", "include/gameplay.h", "BLOW_SPEED_ORTHOGONAL"),
    ("BLOW_SPEED_DIAGONAL", "include/gameplay.h", "BLOW_SPEED_DIAGONAL"),
    ("CANDLE_DX_NEAR", "include/gameplay.h", "CANDLE_DX_NEAR"),
    ("CANDLE_DX_FAR", "include/gameplay.h", "CANDLE_DX_FAR"),
    ("CANDLE_DY_MAX", "include/gameplay.h", "CANDLE_DY_MAX"),
    ("CANDLE_DY_MIN", "include/gameplay.h", "CANDLE_DY_MIN"),
    ("CANDLE_SCORE", "include/gameplay.h", "CANDLE_SCORE"),
    ("DRIFT_SPEED_DECAY", "include/gameplay.h", "DRIFT_SPEED_DECAY"),
    ("DRIFT_SPEED_FLOOR", "include/gameplay.h", "DRIFT_SPEED_FLOOR"),
    ("DRIFT_INTERVAL_MAX", "include/gameplay.h", "DRIFT_INTERVAL_MAX"),
    ("DRIFT_INTERVAL_DIVISOR", "include/gameplay.h", "DRIFT_INTERVAL_DIVISOR"),
    ("DRIFT_VELOCITY_SCALE", "include/gameplay.h", "DRIFT_VELOCITY_SCALE"),
    ("FAN_DX_MIN", "include/gameplay.h", "FAN_DX_MIN"),
    ("FAN_DX_MAX", "include/gameplay.h", "FAN_DX_MAX"),
    ("FAN_DY_LIMIT", "include/gameplay.h", "FAN_DY_LIMIT"),
    ("FAN_PUSH_PIXELS", "include/gameplay.h", "FAN_PUSH_PIXELS"),
    ("ENTRY_POINT_PIXELS", "include/gameplay.h", "ENTRY_POINT_PIXELS"),
    ("PIXELS_PER_WORD", "include/gameplay.h", "PIXELS_PER_WORD"),
    ("PLANE_WORD_BYTES", "include/gameplay.h", "PLANE_WORD_BYTES"),
    ("PIXEL_MSB", "include/gameplay.h", "PIXEL_MSB"),
    ("ROOM_WIDE", "include/gameplay.h", "ROOM_WIDE"),
    ("A_probe_table", "include/gameplay.h", "A_probe_table"),
    ("A_object_table", "include/gameplay.h", "A_object_table"),
    ("A_room_table", "include/gameplay.h", "A_room_table"),
    ("A_candle_table", "include/gameplay.h", "A_candle_table"),
    ("A_deaths_in_room", "include/gameplay.h", "A_deaths_in_room"),
    ("A_lives", "include/gameplay.h", "A_lives"),
    ("A_hi_score", "include/gameplay.h", "A_hi_score"),
    ("A_score", "include/gameplay.h", "A_score"),
    ("A_btn_right_ready", "include/gameplay.h", "A_btn_right_ready"),
    ("A_btn_left_ready", "include/gameplay.h", "A_btn_left_ready"),
    ("A_x_impulse", "include/gameplay.h", "A_x_impulse"),
    ("A_blow_facing_plus1", "include/gameplay.h", "A_blow_facing_plus1"),
    ("A_breath", "include/gameplay.h", "A_breath"),
    ("A_drift_speed", "include/gameplay.h", "A_drift_speed"),
    ("A_drift_pulse", "include/gameplay.h", "A_drift_pulse"),
    ("A_drift_interval", "include/gameplay.h", "A_drift_interval"),
    ("A_delta_y", "include/gameplay.h", "A_delta_y"),
    ("A_delta_x", "include/gameplay.h", "A_delta_x"),
    ("A_drift_dir_y", "include/gameplay.h", "A_drift_dir_y"),
    ("A_drift_dir_x", "include/gameplay.h", "A_drift_dir_x"),
    ("A_drift_vel_y", "include/gameplay.h", "A_drift_vel_y"),
    ("A_drift_vel_x", "include/gameplay.h", "A_drift_vel_x"),
    ("A_probe_phase", "include/gameplay.h", "A_probe_phase"),
    ("A_bubble_alive", "include/gameplay.h", "A_bubble_alive"),
    ("A_ghost_anim", "include/gameplay.h", "A_ghost_anim"),
    ("A_ghost_facing", "include/gameplay.h", "A_ghost_facing"),
    ("A_bubble_frame", "include/gameplay.h", "A_bubble_frame"),
    ("A_ghost_tile", "include/gameplay.h", "A_ghost_tile"),
    ("A_bubble_y", "include/gameplay.h", "A_bubble_y"),
    ("A_bubble_x", "include/gameplay.h", "A_bubble_x"),
    ("A_ghost_y", "include/gameplay.h", "A_ghost_y"),
    ("A_ghost_x", "include/gameplay.h", "A_ghost_x"),
    ("A_room_number", "include/gameplay.h", "A_room_number"),
    ("A_sound_enabled", "include/gameplay.h", "A_sound_enabled"),
    ("A_p2_world_block", "include/gameplay.h", "A_p2_world_block"),
    ("A_p1_world_block", "include/gameplay.h", "A_p1_world_block"),
    # ...and the neighbours' headers this battery reads through rather than restates.
    ("A_key_shift_state", "include/frontend.h", "A_key_shift_state"),
    ("A_mouse_y", "include/frontend.h", "A_mouse_y"),
    ("A_mouse_x", "include/frontend.h", "A_mouse_x"),
    ("A_mouse_buttons", "include/frontend.h", "A_mouse_buttons"),
    ("A_screen_back", "include/blit.h", "A_screen_back"),
    ("SCREEN_ROW_BYTES", "include/blit.h", "SCREEN_ROW_BYTES"),
    ("SCREEN_BYTES", "include/blit.h", "SCREEN_BYTES"),
    ("SCREEN_PLANES", "include/blit.h", "SCREEN_PLANES"),
    ("A_trap_saved_ret", "include/clib.h", "A_trap_saved_ret"),
    ("A_trap_saved_a2", "include/clib.h", "A_trap_saved_a2"),
    ("A_trap_saved_a1", "include/clib.h", "A_trap_saved_a1"),
    ("A_fp_acc", "include/clib.h", "A_fp_acc"),
    ("A_snd_def_fx", "include/sound.h", "A_snd_def_fx"),
    ("SND_DEF_BYTES", "include/sound.h", "SND_DEF_BYTES"),
    ("A_snd_voice", "include/sound.h", "A_snd_voice"),
    ("SND_VOICE_BYTES", "include/sound.h", "SND_VOICE_BYTES"),
    ("SND_VC_DURATION", "include/sound.h", "SND_VC_DURATION"),
    ("SND_VC_PRIORITY", "include/sound.h", "SND_VC_PRIORITY"),
    ("TOS_VEC_TRAP9", "include/sound.h", "TOS_VEC_TRAP9"),
    ("SND_TRAP9_HANDLER_ENTRY", "include/sound.h", "SND_TRAP9_HANDLER_ENTRY"),
)

# ONE CONSTANT THIS BATTERY RESTATES AND CANNOT PIN: `CANDLE_NONE` (-1). `test_constants.py`'s
# scraper reads an unsigned literal or a single-bit shift, so a parenthesised negative is invisible
# to it — which is why every BOUND the header carries is spelt as a magnitude and negated where it
# is used (`CANDLE_DX_NEAR`, `FAN_DY_LIMIT`, `FAN_PUSH_PIXELS`). The battery does not restate
# `CANDLE_NONE`; it writes -1 at the sites that stage "this room has no candle", where the literal
# is the sentinel itself and naming it would say nothing more.

def test_frame_slices_tile_game_frame_update():
    """The seven slices TILE `game_frame_update`, with one declared gap — and the "902 of 1682
    bytes" in ../STATUS.md is re-derived here rather than believed.

    A slice's `stop_pc` is the first instruction it does NOT verify, so consecutive slices must meet
    exactly: a GAP would be a region no case runs and nobody notices, and an OVERLAP would mean two
    slices claim the same bytes and the ledger's byte count double-counts them. Only two regions are
    exempt and both are named in ../STATUS.md: the front-end poll between slices 1 and 2, and the
    death sequence inside slice 6.
    """
    for index, (entry, stop) in enumerate(FRAME_SLICES):
        assert entry < stop, f"slice {index} is empty or backwards: [{entry:#x}, {stop:#x})"
    for index, ((_entry, stop), (next_entry, _next_stop)) in enumerate(zip(FRAME_SLICES,
                                                                          FRAME_SLICES[1:])):
        if (stop, next_entry) == FRAME_FRONT_END_POLL:
            continue
        assert stop == next_entry, (
            f"slice {index} stops at {stop:#x} and slice {index + 1} starts at {next_entry:#x} — "
            f"the {'gap' if stop < next_entry else 'overlap'} between them is unaccounted for; the "
            f"only declared gap is the front-end poll "
            f"[{FRAME_FRONT_END_POLL[0]:#x}, {FRAME_FRONT_END_POLL[1]:#x})")

    assert FRAME_SLICES[0][0] == ENTRY_FRAME_ADVANCE_BUBBLE_FRAME
    death_start, death_end = FRAME_DEATH_SEQUENCE
    covering = [(entry, stop) for entry, stop in FRAME_SLICES if entry <= death_start < stop]
    assert len(covering) == 1 and death_end <= covering[0][1], (
        f"the death sequence [{death_start:#x}, {death_end:#x}) is not inside exactly one slice")

    verified = sum(stop - entry for entry, stop in FRAME_SLICES) - (death_end - death_start)
    assert verified == FRAME_VERIFIED_BYTES, (
        f"the seven slices cover {verified} bytes of `game_frame_update`, not the "
        f"{FRAME_VERIFIED_BYTES} ../STATUS.md's row states")
    assert FRAME_UPDATE_BYTES == 1682, (
        f"`game_frame_update` is {FRAME_UPDATE_BYTES} bytes, not the 1682 ../STATUS.md's row states")


# TWELVE BYTES. Four routines here open with the identical `link a6,#$0 / move.w -n(a4),-m(a4)` and
# separate only at the displacements — `save_world_p1` and `save_world_p2` differ in their fifth
# word — and five slices are entered mid-body where there is no `link` to tell them apart at all.
ENTRY_PROLOGUES = {
    "ENTRY_RESET_WORLD_STATE": "4e560000303c00043940dc34",
    "ENTRY_ITOA_PADDED": "4e56fffa426efffe202e0008",
    "ENTRY_GHOST_BLOW": "4e56fffc3f3c00014eba1ba0",
    "ENTRY_BUBBLE_COLLISION_PROBE": "4e560000302ce0c4526ce0c4",
    "ENTRY_RESTORE_WORLD_P1": "4e560000396ce372dc34396c",
    "ENTRY_RESTORE_WORLD_P2": "4e560000396ce2fedc34396c",
    "ENTRY_GET_PIXEL": "4e56fff448e70310302e0008",
    "ENTRY_SAVE_WORLD_P1": "4e560000396cdc34e372396c",
    "ENTRY_SAVE_WORLD_P2": "4e560000396cdc34e2fe396c",
    "ENTRY_FRAME_ADVANCE_BUBBLE_FRAME": "4e560000302ce0ce526ce0ce",
    "ENTRY_FRAME_SCALE_MOUSE": "0c6c0023e2066624302ce200",
    "ENTRY_FRAME_BLOW_OR_RECOVER": "302ce1fc67620c6c0004e1fc",
    "ENTRY_FRAME_STEP_FACING": "0c6c0001e2026626102ce0aa",
    "ENTRY_FRAME_APPLY_FANS": "302ce206c1fc008c41ecb7aa",
    "ENTRY_FRAME_STEP_LIVE_BUBBLE": "302ce0c667544eba091a0c6c",
    "ENTRY_FRAME_DRIFT_PULSE": "426ce0c2426ce0c0426ce0ac",
}

# ...and the CHECKPOINTS. A `stop_pc` is as able to name the wrong instruction as an entry is — one
# early diffs a slice before its last store and comes back clean — so `test_constants.py` requires a
# row here for every module-level `STOP_*`.
#
# SIX OF THESE REPEAT AN `ENTRY_*` ROW ABOVE, and that is the point rather than a duplication: the
# seven frame slices TILE the routine, so each one's stop IS the next one's entry
# (`test_frame_slices_tile_game_frame_update` asserts it). The pins are per NAME, so each still fails
# under the name of the constant that moved.
STOP_PROLOGUES = {
    "STOP_GHOST_BLOW_BODY": "4ebae3d84eba01f24e5e4e75",
    "STOP_FRAME_ADVANCE_BUBBLE_FRAME": "486ce1fe486ce200486ce202",
    "STOP_FRAME_SCALE_MOUSE": "302ce1fc67620c6c0004e1fc",
    "STOP_FRAME_BLOW_OR_RECOVER": "0c6c0001e2026626102ce0aa",
    "STOP_FRAME_STEP_FACING": "302ce206c1fc008c41ecb7aa",
    "STOP_FRAME_APPLY_FANS": "302ce0c667544eba091a0c6c",
    "STOP_FRAME_STEP_LIVE_BUBBLE": "426ce0c2426ce0c0426ce0ac",
    "STOP_FRAME_DRIFT_PULSE": "4e5e4e754e56fffc3f3c0001",
}
