"""Differential tests for the RAW blitters (src/blit.c).

WHAT IS HERE. The ten routines that move pixels with `move.l (a3)+,(a2)+` and nothing else:
`clear_physical_screen` @ 0x10efe, `present_score_strip` @ 0x131f0, `present_hud_row` @ 0x13224,
`stage_to_work` @ 0x13258, `present_room` @ 0x13286, `draw_tile_bank_screen` @ 0x1369a,
`draw_hud_row_tiles` @ 0x13712, `objects_animate_and_draw` @ 0x1376e, and three SLICES —
`build_sprite_bank` @ 0x132ec's raw prefix, one tile of `draw_room_to_stage` @ 0x13a08, and the
whole slide loop of `room_wipe_in` @ 0x13b1e. What is NOT here is the game's other drawing family,
which goes through `vro_cpyfm`; STATUS.md records those as residuals.

THE TWO POINTERS ARE THE CASE'S OWN INPUTS, NOT THE MODEL'S. `init_gem_and_screens` @ 0x10118 takes
them from XBIOS `Logbase`, which the kit answers with `OS_SCREEN_BASE` = 0x8000 — so the game's
`Logbase - 0x7d00` work buffer would land at 0x300, on top of the harness-poked input block, and a
32,000-byte frame write would silently eat any staged keystroke (STATUS.md, "Model gaps"). So every
case below POKES `screen_phys`/`screen_back` itself, at addresses that keep the real machine's own
relationship (the two screens adjacent, `screen_back` one screen below `screen_phys`) inside
`test/abi.py`'s scratch map.

THE SIX GHOST.DAT BANKS ARE STAGED WHERE THE GAME'S OWN MALLOCS PUT THEM — six 30,720-byte blocks
from `OS_HEAP_BASE`, which is what `load_level_pictures` @ 0x1396c's `c_malloc(0x7800) x 6` really
produces under the model. Each battery runs them BOTH ways: seeded with noise, so that a copy one
row too long has something to differ against, and filled with the real `../bin/GHOST.DAT`, so that
the tile geometry is checked against the bytes the game actually draws.
"""
import ctypes
import pathlib
import random

import pytest

import abi
import emu
import harness
from harness import report

REC = pathlib.Path(__file__).resolve().parents[1]

# ---- entry addresses (Ghidra == run-time; see README.md, "The image model") --------------------
ENTRY_CLEAR_PHYSICAL_SCREEN = 0x10efe
ENTRY_PRESENT_SCORE_STRIP = 0x131f0
ENTRY_PRESENT_HUD_ROW = 0x13224
ENTRY_STAGE_TO_WORK = 0x13258
ENTRY_PRESENT_ROOM = 0x13286
ENTRY_BUILD_SPRITE_BANK = 0x132ec
ENTRY_DRAW_TILE_BANK_SCREEN = 0x1369a
ENTRY_DRAW_HUD_ROW_TILES = 0x13712
ENTRY_OBJECTS_ANIMATE_AND_DRAW = 0x1376e
# The three mid-entry slices, each entered INSIDE its routine and stopped before the part the TOS
# model refuses (docs/agent-playbook.md §5). The stop PC is the first instruction NOT verified.
ENTRY_DRAW_ROOM_TILE_TO_STAGE = 0x13a38     # just past the loop's `vq_mouse`
STOP_DRAW_ROOM_TILE_TO_STAGE = 0x13afa      # ...to just before `addq.w #1,-2(a6)`
ENTRY_ROOM_WIPE_IN_SLIDE = 0x13b62          # `clr.w d7`, past the three `sound_release_voice`s
STOP_ROOM_WIPE_IN_SLIDE = 0x13bda           # ...to the `sound_release_voice(0)` that ends the wipe
ENTRY_ROOM_WIPE_IN_STEP = 0x13b66           # one slide step, entered with D7 = the step number
STOP_ROOM_WIPE_IN_STEP = 0x13bd4            # ...to its `cmpi.w #$28,d7`
STOP_BUILD_SPRITE_BANK_PREPARE = 0x13330    # `clr.w -4(a6)`: the head of the `vro_cpyfm` grab loop

# ---- mirrors of include/blit.h -----------------------------------------------------------------
SCREEN_ROW_BYTES = 160
SCREEN_BYTES = 32000
CLEARED_SCREEN_BYTES = 30720
TILE_PIXELS = 32
TILE_ROW_BYTES = 16
TILE_BYTES = 512
TILE_ROW_SCREEN_BYTES = 0x1400
TILES_PER_BANK = 60
DAT_BANKS = 7
ROOM_TILE_COLS = 10
ROOM_TILE_ROWS = 5
BANK_TILE_ROWS = 6
ROOM_BYTES = 0x6400
SCORE_STRIP_OFFSET = 0x6540
SCORE_STRIP_BYTES = 4096
HUD_TILE_BANK = 5
HUD_FIRST_TILE_IN_BANK = 50
WIPE_STEPS = 40
WIPE_STEP_BYTES = 640
OBJECT_SLOTS = 10
OBJECT_STRIDE = 14
OBJECT_ROOM_STRIDE = 140
OBJECT_TILE = 0
OBJECT_COUNTDOWN = 2
OBJECT_RELOAD = 4
OBJECT_X = 6
OBJECT_Y = 8
OBJECT_FRAME = 10
OBJECT_FRAME_COUNT = 12
ROOM_STRIDE = 120
ROOM_MAP_ROW_BYTES = 20
ROOM_MAP_CELL_BYTES = 2
MFDB_PLANES = 12
A_SCREEN_PHYS = 0x23148
A_SCREEN_BACK = 0x2314c
A_DAT_BANK = 0x2312a
A_BANK_INDEX = 0x2311e
A_MFDB_SRC = 0x23100
A_MFDB_DST = 0x230ec
A_ROOM_NUMBER = 0x23120
A_OBJECT_TABLE = 0x2069a
A_ROOM_TABLE = 0x21a4a

ROOM_COUNT = 36                  # `../notes/gameplay.md` §4: the castle is a 6 x 6 grid

# ---- where a case stages the world -------------------------------------------------------------
# The screens keep the machine's own relationship — `screen_back = screen_phys - SCREEN_BYTES` —
# and the staging area `draw_room_to_stage` composes into sits one room below that again, so the
# three are contiguous and start exactly at the scratch map's base.
STAGE = abi.SCRATCH
SCREEN_BACK = STAGE + ROOM_BYTES
SCREEN_PHYS = SCREEN_BACK + SCREEN_BYTES
SCREEN_TOP = SCREEN_PHYS + SCREEN_BYTES

# The six GHOST.DAT buffers, plus the GHOST.PRE one at index 6, laid out in the Malloc arena
# `project.toml` places — which is the region the game's own `c_malloc(0x7800) x 6` really hands
# back. The arena is unused by these cases: nothing here traps, so no served Malloc can collide.
#
# THE GAP BETWEEN BANKS IS LOAD-BEARING, and it is the one thing here that is not simply what the
# machine does. `tile_source` computes `dat_bank[n / 60] + (n % 60) * 512`, and 60 tiles of 512
# bytes is exactly DAT_BANK_BYTES — so with the banks packed end to end that expression collapses
# to `dat_bank[0] + n * 512` for EVERY n, and the `divs.w #$3c` split becomes unobservable.
# Measured: with contiguous banks a reconstruction splitting at 59 tiles per bank passed all 244
# cases. The gap makes the two disagree, and the game's own allocator leaves one anyway (each
# `c_malloc` block carries a header).
DAT_BANK_BYTES = 0x7800
DAT_BANKS_FROM_FILE = 6
BANK_BASE = emu.OS_HEAP_BASE
# ...and the gap is IRREGULAR, which is the second half of the same argument. A fixed stride is
# still affine — `BANK_BASE + index * STRIDE` — so a reconstruction that computed a bank's address
# arithmetically instead of loading `dat_bank[index]` out of the image matches every case anyway.
# Random, ordered, non-overlapping offsets make the pointer LOAD the only way to be right. The seed
# is fixed, so the layout is the same every run and a failure is reproducible.
BANK_TOP = 0x88000               # the banks end below WRAP_BAND, which ends below abi.STUB
BANK_ADDRESSES = tuple(sorted(
    BANK_BASE + 2 * offset for offset in random.Random(0x8a11c).sample(
        range((BANK_TOP - BANK_BASE - DAT_BANKS * DAT_BANK_BYTES) // 2), DAT_BANKS)))
BANK_ADDRESSES = tuple(address + index * DAT_BANK_BYTES
                       for index, address in enumerate(BANK_ADDRESSES))

# A band clear of every staged region, for the two cases whose destination is deliberately computed
# by a WRAPPED offset and so lands nowhere the rest of the battery seeds (see the `ext.l` tests).
WRAP_BAND = (0x88000, 0x8c000)

# The Alcyon frame a mid-entry slice is entered on. `emu.run` forces A7 to `emu.STACK_TOP` and every
# entry below is past its routine's own `link a6,#-n`, so A6 sits one longword down — where a `jsr`
# made from A7 = STACK_TOP would have left it. The frame's locals are inside the stack-guard band
# the differential drops, so they are inputs and scratch rather than compared output.
FRAME_A6 = emu.STACK_TOP - 4
FRAME_TILE_ROW = FRAME_A6 - 4    # the routine's -4(a6)
FRAME_TILE_COL = FRAME_A6 - 2    # ...and its -2(a6)

GHOST_DAT = (REC.parent / "bin" / "GHOST.DAT").read_bytes()

_u8p = ctypes.POINTER(ctypes.c_uint8)
for _sym in ("g_clear_physical_screen", "g_present_room", "g_present_hud_row",
             "g_present_score_strip", "g_stage_to_work", "g_draw_tile_bank_screen",
             "g_draw_hud_row_tiles", "g_objects_animate_and_draw",
             "g_build_sprite_bank_prepare", "g_room_wipe_in_slide"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None
harness._lib.g_draw_room_tile_to_stage.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_draw_room_tile_to_stage.restype = None
harness._lib.g_room_wipe_in_step.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_room_wipe_in_step.restype = None


# ================================================================================ staging helpers

def _bank(index):
    return BANK_ADDRESSES[index]


# The pointers every routine here reads out of the game's own globals.
POINTER_POKES = {
    A_SCREEN_PHYS: abi.long(SCREEN_PHYS),
    A_SCREEN_BACK: abi.long(SCREEN_BACK),
    A_DAT_BANK: b"".join(abi.long(_bank(i)) for i in range(DAT_BANKS)),
}

SCREEN_SPANS = ((STAGE, SCREEN_TOP),)
BANK_SPANS = tuple((_bank(i), _bank(i) + DAT_BANK_BYTES) for i in range(DAT_BANKS))
# The object table `objects_animate_and_draw` steps through. Seeding it replaces the game's own,
# which is why the battery that uses it also runs the shipped shape. The ROOM table is never seeded
# wholesale: a random word there is a tile index over the whole 16-bit range, and the wild source
# address that produces is what `make guarded` faults on (see the `ext.l` cases).
OBJECT_TABLE_SPAN = (A_OBJECT_TABLE, A_OBJECT_TABLE + ROOM_COUNT * OBJECT_ROOM_STRIDE)


def _pokes(seed, spans, extra=None):
    """Noise over every span the run touches, then the pointers the routines read.

    THE OVERLAP IS DELIBERATE HERE, which is why this is the one `abi.merge_pokes` call in the
    project that allows one. The noise covers whole regions — the screens, the seven banks — and the
    stagings that follow deliberately land INSIDE them: `POINTER_POKES` writes the globals a routine
    reads its addresses out of, and `extra` (the real GHOST.DAT, an object record, a map cell) is
    the case's own content. `make_image` applies a poke dict in insertion order, so the LATER poke
    wins: noise first, then the pointers, then `extra` — the case's own bytes over everything.
    """
    return abi.merge_pokes(abi.seed_spans(seed, spans, guard=abi.GUARD_BYTES),
                           POINTER_POKES, extra or {}, allow_overlap=True)


def _real_dat_poke():
    """The real GHOST.DAT over banks 0..5 — the exact 60-tile buffers `load_level_pictures` reads.

    The file's last 32 bytes are the palette, not a seventh bank, so bank 6 (GHOST.PRE) keeps
    whatever noise the case seeded it with.
    """
    return {_bank(i): GHOST_DAT[i * DAT_BANK_BYTES:(i + 1) * DAT_BANK_BYTES]
            for i in range(DAT_BANKS_FROM_FILE)}


def _run(entry, glue, pokes, regs=None, **kwargs):
    """One differential, with the `a4` every function of this program is entered on."""
    return abi.run_with_a4(entry, glue, pokes=pokes, regs=regs, **kwargs)


# ============================================================== the four whole-region screen copies
#
# Each is one `dbf` loop and nothing else, so what a case has to get wrong for the diff to notice is
# the span: the offset it starts at and the number of longwords it moves.

_REGION_COPIES = {
    "present_room": (ENTRY_PRESENT_ROOM, "g_present_room"),
    "present_hud_row": (ENTRY_PRESENT_HUD_ROW, "g_present_hud_row"),
    "present_score_strip": (ENTRY_PRESENT_SCORE_STRIP, "g_present_score_strip"),
    "stage_to_work": (ENTRY_STAGE_TO_WORK, "g_stage_to_work"),
    "clear_physical_screen": (ENTRY_CLEAR_PHYSICAL_SCREEN, "g_clear_physical_screen"),
}


def _region_case(name, seed, extra=None, poison=False):
    entry, symbol = _REGION_COPIES[name]
    pokes = _pokes(seed, SCREEN_SPANS, extra)
    diffs, _ = _run(entry, lambda lib, buf: getattr(lib, symbol)(buf), pokes, poison=poison)
    assert not diffs, f"{name} seed={seed:#x}\n{report(diffs)}"


@pytest.mark.parametrize("name", sorted(_REGION_COPIES))
@pytest.mark.parametrize("seed", (1, 2, 3))
def test_region_copy(name, seed):
    """Noise over both screens and the staging area: a span one row long or short differs."""
    _region_case(name, seed)


@pytest.mark.parametrize("name", sorted(_REGION_COPIES))
def test_region_copy_attribution(name):
    """The poison pass: every byte the oracle wrote is pre-inverted, so a candidate that "matched"
    by leaving a region that already held the right bytes now differs (§4)."""
    _region_case(name, seed=0x1f0, poison=True)


@pytest.mark.parametrize("name", sorted(_REGION_COPIES))
@pytest.mark.parametrize("delta", (4, SCREEN_ROW_BYTES, -4, -SCREEN_ROW_BYTES))
def test_region_copy_overlapping_screens(name, delta):
    """The two screens overlapping by one longword or one scanline, either way round.

    THIS is what pins the ascending `move.l (a3)+,(a2)+` order. Nothing the game does aliases the
    two screens — `init_gem_and_screens` always puts them a screen apart — but the routines read
    both from globals, so the overlap is a legal input and the smear it produces is the only
    observable difference between copying up and copying down.
    """
    _region_case(name, seed=0x5c0 + delta, extra={A_SCREEN_PHYS: abi.long(SCREEN_BACK + delta)})


# ================================================================================== the tile draws

@pytest.mark.parametrize("bank_index", range(DAT_BANKS))
def test_draw_tile_bank_screen_noise(bank_index):
    """A 10 x 6 grid of 32x32 cells, over noise: a wrong stride shows in every cell but the first."""
    pokes = _pokes(0x3690 + bank_index, SCREEN_SPANS + BANK_SPANS,
                   {A_BANK_INDEX: abi.word(bank_index)})
    diffs, _ = _run(ENTRY_DRAW_TILE_BANK_SCREEN,
                    lambda lib, buf: lib.g_draw_tile_bank_screen(buf), pokes)
    assert not diffs, f"bank {bank_index}\n{report(diffs)}"


@pytest.mark.parametrize("bank_index", range(DAT_BANKS_FROM_FILE))
def test_draw_tile_bank_screen_real_ghost_dat(bank_index):
    """...and over the real file, which is what `build_sprite_bank` grabs its sprites back out of."""
    extra = dict(_real_dat_poke())
    extra[A_BANK_INDEX] = abi.word(bank_index)
    pokes = _pokes(0x369a, SCREEN_SPANS + BANK_SPANS, extra)
    diffs, _ = _run(ENTRY_DRAW_TILE_BANK_SCREEN,
                    lambda lib, buf: lib.g_draw_tile_bank_screen(buf), pokes)
    assert not diffs, f"bank {bank_index}\n{report(diffs)}"


def test_draw_tile_bank_screen_attribution():
    _pokes_ = _pokes(0x3691, SCREEN_SPANS + BANK_SPANS, {A_BANK_INDEX: abi.word(0)})
    diffs, _ = _run(ENTRY_DRAW_TILE_BANK_SCREEN,
                    lambda lib, buf: lib.g_draw_tile_bank_screen(buf), _pokes_, poison=True)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("seed", (1, 2))
def test_draw_hud_row_tiles_noise(seed):
    """Ten tiles from bank 5, read through the absolute `&dat_bank[5]` rather than `bank_index`."""
    pokes = _pokes(0x3712 + seed, SCREEN_SPANS + BANK_SPANS)
    diffs, _ = _run(ENTRY_DRAW_HUD_ROW_TILES,
                    lambda lib, buf: lib.g_draw_hud_row_tiles(buf), pokes, poison=(seed == 1))
    assert not diffs, report(diffs)


def test_draw_hud_row_tiles_real_ghost_dat():
    """The shipped HUD strip: GHOST.DAT tiles 350..359, bank 5's last ten."""
    pokes = _pokes(0x3713, SCREEN_SPANS + BANK_SPANS, _real_dat_poke())
    diffs, _ = _run(ENTRY_DRAW_HUD_ROW_TILES,
                    lambda lib, buf: lib.g_draw_hud_row_tiles(buf), pokes)
    assert not diffs, report(diffs)


def test_the_hud_strip_really_is_the_last_ten_tiles_of_bank_5():
    """`draw_hud_row_tiles`' `add.l #$6400` is 50 tiles into the bank, NOT the 0x6400 that is the
    room's byte size — the two numbers are equal by coincidence and are separate constants in
    include/blit.h. This is the arithmetic that says which one the routine means."""
    assert HUD_FIRST_TILE_IN_BANK * TILE_BYTES == 0x6400
    assert HUD_TILE_BANK * TILES_PER_BANK + HUD_FIRST_TILE_IN_BANK == 350


# ========================================================== objects_animate_and_draw @ 0x1376e

def _objects_case(seed, room, spans, extra=None, poison=False):
    pokes = _pokes(seed, spans, {**(extra or {}), A_ROOM_NUMBER: abi.word(room)})
    diffs, _ = _run(ENTRY_OBJECTS_ANIMATE_AND_DRAW,
                    lambda lib, buf: lib.g_objects_animate_and_draw(buf), pokes, poison=poison)
    assert not diffs, f"room {room} seed={seed:#x}\n{report(diffs)}"


@pytest.mark.parametrize("room", range(ROOM_COUNT))
def test_objects_animate_and_draw_shipped_rooms(room):
    """THE GAME'S OWN OBJECT TABLE, one room at a time, over the real GHOST.DAT.

    The table is left exactly as `init_globals` wrote it, so what runs is the animation phase the
    shipped data starts each slot at — room 22's ten candles at 0,1,1,2,2,3,3,4,4, the fans' 8-frame
    cycles, and the `-1` empty slots that must be skipped rather than drawn.
    """
    _objects_case(0x1376e, room, SCREEN_SPANS + BANK_SPANS, _real_dat_poke())


@pytest.mark.parametrize("room", (0, 3, 22, 35))
def test_objects_animate_and_draw_shipped_rooms_over_noise(room):
    """The same rooms with the banks noisy, so a wrong source offset has something to differ."""
    _objects_case(0x376e + room, room, SCREEN_SPANS + BANK_SPANS)


OBJECT_FUZZ_CASES = 96
OBJECT_FUZZ_CHUNKS = 4


def _object_fuzz_cases():
    """Random object records for one room, in the ranges the shipped table stays inside.

    Seeded ONCE so every chunk replays the same stream and the shards partition it exactly.
    `tile` stays below the six banks' 360 tiles and `frame` small, so the source stays inside the
    staged buffers; `x`/`y` stay on the tile grid, so the destination stays on the screen. Both
    bounds are the shipped data's, and the out-of-range behaviour they leave unexercised is the
    `ext.l` wrap the two dedicated cases below pin instead.
    """
    rng = random.Random(ENTRY_OBJECTS_ANIMATE_AND_DRAW)
    cases = []
    for _ in range(OBJECT_FUZZ_CASES):
        room = rng.randrange(ROOM_COUNT)
        slots = []
        for _slot in range(OBJECT_SLOTS):
            slots.append({
                OBJECT_TILE: -1 if rng.random() < 0.3 else rng.randrange(DAT_BANKS_FROM_FILE * TILES_PER_BANK),
                OBJECT_COUNTDOWN: rng.randrange(0, 4),
                OBJECT_RELOAD: rng.randrange(0, 4),
                OBJECT_X: rng.randrange(ROOM_TILE_COLS),
                OBJECT_Y: rng.randrange(ROOM_TILE_ROWS),
                OBJECT_FRAME: rng.randrange(0, 8),
                OBJECT_FRAME_COUNT: rng.randrange(1, 9),
            })
        cases.append((room, slots))
    return cases


_OBJECT_FUZZ = _object_fuzz_cases()


@pytest.mark.parametrize("chunk", range(OBJECT_FUZZ_CHUNKS))
def test_objects_animate_and_draw_fuzz(chunk):
    for i, (room, slots) in enumerate(_OBJECT_FUZZ):
        if i % OBJECT_FUZZ_CHUNKS != chunk:
            continue
        extra = {}
        base = A_OBJECT_TABLE + room * OBJECT_ROOM_STRIDE
        for slot, fields in enumerate(slots):
            for offset, value in fields.items():
                extra[base + slot * OBJECT_STRIDE + offset] = abi.word(value)
        _objects_case(0x4000 + i, room, SCREEN_SPANS + BANK_SPANS + (OBJECT_TABLE_SPAN,), extra)


def test_objects_animate_and_draw_countdown_reaches_zero_and_reloads():
    """The one branch the shipped tables reach rarely and the whole animation turns on: a slot whose
    countdown is ALREADY 0 reloads and steps its frame; every other slot only decrements.

    Slot k is given countdown k, so exactly slot 0 fires this frame — and the frame wrap is armed on
    it as well (`frame == count - 1`), so the case covers the reload, the step and the wrap at once.
    """
    room = 1
    extra = {}
    base = A_OBJECT_TABLE + room * OBJECT_ROOM_STRIDE
    for slot in range(OBJECT_SLOTS):
        fields = {OBJECT_TILE: slot * TILES_PER_BANK // 2, OBJECT_COUNTDOWN: slot,
                  OBJECT_RELOAD: 3, OBJECT_X: slot % ROOM_TILE_COLS,
                  OBJECT_Y: slot % ROOM_TILE_ROWS, OBJECT_FRAME: 2, OBJECT_FRAME_COUNT: 3}
        for offset, value in fields.items():
            extra[base + slot * OBJECT_STRIDE + offset] = abi.word(value)
    _objects_case(0x4100, room, SCREEN_SPANS + BANK_SPANS + (OBJECT_TABLE_SPAN,), extra)


def test_objects_animate_and_draw_word_edge_branches():
    """The two tests whose instructions are wider than the shipped data ever exercises.

    The slot test is `cmpi.w #$0,(a0) / blt`, so ANY negative tile is an empty slot and not only
    the -1 the tables hold; the countdown test is `cmpi.w #$0,d0 / bne`, so a NEGATIVE countdown
    fires the animation where the `bgt` a reader might write instead would skip it. Both are
    synthetic — the countdown is only ever reloaded from a non-negative field and only ever
    decremented from a non-zero one, so nothing in play reaches either — but both are what the
    routine's own instructions say, and a reconstruction narrower than them passed everything else
    in this battery (measured).
    """
    room = 2
    extra = {}
    base = A_OBJECT_TABLE + room * OBJECT_ROOM_STRIDE
    for slot in range(OBJECT_SLOTS):
        fields = {OBJECT_TILE: -2 - slot if slot < 3 else 60 + slot * 7,
                  OBJECT_COUNTDOWN: -1 - slot if slot >= 3 else 0,
                  OBJECT_RELOAD: 2, OBJECT_X: slot % ROOM_TILE_COLS,
                  OBJECT_Y: slot % ROOM_TILE_ROWS, OBJECT_FRAME: 1, OBJECT_FRAME_COUNT: 4}
        for offset, value in fields.items():
            extra[base + slot * OBJECT_STRIDE + offset] = abi.word(value)
    _objects_case(0x4200, room, SCREEN_SPANS + BANK_SPANS + (OBJECT_TABLE_SPAN,), extra)


# ================================================ build_sprite_bank @ 0x132ec — the raw prefix

def test_build_sprite_bank_prepare():
    """[0x132ec, 0x13330): bank 0 painted over the work buffer, and a 32x32 cell described to the
    VDI in both MFDBs. The 60 `c_malloc` + `vro_cpyfm` grabs that follow are the residual.

    It is also the one case that runs `draw_tile_bank_screen` from its real caller rather than at
    its own entry, so the composition is checked as well as the leaf.
    """
    pokes = _pokes(0x132ec, SCREEN_SPANS + BANK_SPANS, _real_dat_poke())
    diffs, _ = _run(ENTRY_BUILD_SPRITE_BANK,
                    lambda lib, buf: lib.g_build_sprite_bank_prepare(buf), pokes,
                    stop_pc=STOP_BUILD_SPRITE_BANK_PREPARE)
    assert not diffs, report(diffs)


def test_build_sprite_bank_prepare_over_noise():
    """The same, with both MFDBs and `bank_index` pre-filled with noise, so a field the prefix
    forgets to write differs instead of already holding zero."""
    mfdb_bytes = MFDB_PLANES + 2        # `planes` is the last field, so this is the whole record
    mfdb_noise = ((A_MFDB_DST, A_MFDB_DST + mfdb_bytes), (A_MFDB_SRC, A_MFDB_SRC + mfdb_bytes),
                  (A_BANK_INDEX, A_BANK_INDEX + 2))
    pokes = _pokes(0x132ed, SCREEN_SPANS + BANK_SPANS + mfdb_noise)
    diffs, _ = _run(ENTRY_BUILD_SPRITE_BANK,
                    lambda lib, buf: lib.g_build_sprite_bank_prepare(buf), pokes,
                    stop_pc=STOP_BUILD_SPRITE_BANK_PREPARE)
    assert not diffs, report(diffs)


# ==================================== draw_room_to_stage @ 0x13a08 — one tile of its 5 x 10 loop

def _room_tile_case(seed, room, tile_row, tile_col, spans, extra=None, poison=False):
    frame = {FRAME_TILE_ROW: abi.word(tile_row), FRAME_TILE_COL: abi.word(tile_col),
             A_ROOM_NUMBER: abi.word(room)}
    pokes = _pokes(seed, spans, {**(extra or {}), **frame})
    diffs, _ = _run(ENTRY_DRAW_ROOM_TILE_TO_STAGE,
                    lambda lib, buf: lib.g_draw_room_tile_to_stage(buf, tile_row & 0xffff,
                                                                   tile_col & 0xffff),
                    pokes, regs={"a6": FRAME_A6},
                    stop_pc=STOP_DRAW_ROOM_TILE_TO_STAGE, poison=poison)
    assert not diffs, f"room {room} cell ({tile_row},{tile_col}) seed={seed:#x}\n{report(diffs)}"


@pytest.mark.parametrize("tile_row", range(ROOM_TILE_ROWS))
@pytest.mark.parametrize("tile_col", range(ROOM_TILE_COLS))
def test_draw_room_tile_every_cell(tile_row, tile_col):
    """All fifty cells of a shipped room map, over the real GHOST.DAT — the whole of what
    `draw_room_to_stage`'s loop does, one iteration at a time."""
    _room_tile_case(0x13a08, room=1, tile_row=tile_row, tile_col=tile_col,
                    spans=SCREEN_SPANS + BANK_SPANS, extra=_real_dat_poke())


@pytest.mark.parametrize("room", range(ROOM_COUNT))
def test_draw_room_tile_every_room(room):
    """One cell from every room's map, so every shipped tile index the map holds is at least
    reachable — including the tiles above bank 0 that exercise the `divs.w #$3c` split."""
    _room_tile_case(0x3a08 + room, room, tile_row=room % ROOM_TILE_ROWS,
                    tile_col=room % ROOM_TILE_COLS,
                    spans=SCREEN_SPANS + BANK_SPANS, extra=_real_dat_poke())


ROOM_TILE_FUZZ_CASES = 80
ROOM_TILE_FUZZ_CHUNKS = 4


def _room_tile_fuzz_cases():
    """Random maps and cells. Seeded once; every chunk replays the stream (§7)."""
    rng = random.Random(ENTRY_DRAW_ROOM_TILE_TO_STAGE)
    return [(rng.randrange(ROOM_COUNT), rng.randrange(ROOM_TILE_ROWS), rng.randrange(ROOM_TILE_COLS))
            for _ in range(ROOM_TILE_FUZZ_CASES)]


_ROOM_TILE_FUZZ = _room_tile_fuzz_cases()


@pytest.mark.parametrize("chunk", range(ROOM_TILE_FUZZ_CHUNKS))
def test_draw_room_tile_fuzz(chunk):
    """A noisy room table, so the tile index is any word — which drives the bank split, the
    in-bank offset and therefore the source address over its whole range.

    The map cell is masked to the six real banks' tile range by seeding only the low byte of each
    word: a tile above 359 would index `dat_bank[6]` and beyond, off the staged buffers.
    """
    for i, (room, tile_row, tile_col) in enumerate(_ROOM_TILE_FUZZ):
        if i % ROOM_TILE_FUZZ_CHUNKS != chunk:
            continue
        rng = random.Random(0x5000 + i)
        cell = (A_ROOM_TABLE + room * ROOM_STRIDE + tile_row * ROOM_MAP_ROW_BYTES
                + tile_col * ROOM_MAP_CELL_BYTES)
        tile = rng.randrange(DAT_BANKS_FROM_FILE * TILES_PER_BANK)
        _room_tile_case(0x5000 + i, room, tile_row, tile_col,
                        spans=SCREEN_SPANS + BANK_SPANS, extra={cell: abi.word(tile)})


def test_draw_room_tile_attribution():
    _room_tile_case(0x13a09, room=1, tile_row=2, tile_col=3,
                    spans=SCREEN_SPANS + BANK_SPANS, extra=_real_dat_poke(), poison=True)


# The two shapes of the `muls.w #k / ext.l` truncation every screen offset in this file is built
# with. A tile row of 13 makes the 32-bit product 0x10400, whose low word is 0x0400 — the
# destination lands 1,024 bytes into the staging area instead of 66,560 past it. A tile row of 7
# makes it 0x8c00, whose low word is NEGATIVE, so the destination lands BELOW the staging area
# entirely. A reconstruction that multiplied in 32 bits writes neither place.
@pytest.mark.parametrize("tile_row,tile_col", ((13, 0), (7, 3)))
def test_draw_room_tile_offset_wraps_in_a_signed_word(tile_row, tile_col):
    """The map cell is poked with a REAL tile rather than seeded, and that is not tidiness.

    A row past the map reads its cell from wherever the record layout puts it, and a seeded word
    there is a tile index over the whole 16-bit range — which makes `dat_bank[tile / 60]` a garbage
    pointer and the source address wild. The oracle bounds such an address to the image and reads
    zero; a reconstruction indexing `image + address` walks off the buffer, which is invisible under
    `make test` and is exactly what `make guarded` faulted on when this case seeded the table. The
    shipped maps hold tiles 0..359, so 359 is the strongest in-range value: bank 5, entry 59.
    """
    cell = (A_ROOM_TABLE + ROOM_STRIDE + tile_row * ROOM_MAP_ROW_BYTES
            + tile_col * ROOM_MAP_CELL_BYTES)
    _room_tile_case(0xe47 + tile_row, room=1, tile_row=tile_row, tile_col=tile_col,
                    spans=SCREEN_SPANS + BANK_SPANS + (WRAP_BAND,),
                    extra={cell: abi.word(DAT_BANKS_FROM_FILE * TILES_PER_BANK - 1)})


# ============================================ room_wipe_in @ 0x13b1e — the 40-step slide loop

@pytest.mark.parametrize("step", range(WIPE_STEPS))
def test_room_wipe_in_step(step):
    """One slide step, entered with D7 = the step number: the descending 25,600-byte move onto its
    own span four scanlines down, then the top `640 * (step + 1)` bytes presented."""
    pokes = _pokes(0x13b66 + step, SCREEN_SPANS)
    diffs, _ = _run(ENTRY_ROOM_WIPE_IN_STEP,
                    lambda lib, buf: lib.g_room_wipe_in_step(buf, step), pokes,
                    regs={"d7": step}, stop_pc=STOP_ROOM_WIPE_IN_STEP)
    assert not diffs, f"step {step}\n{report(diffs)}"


# ---- the step whose presented-longword count does NOT fit a word --------------------------------
# `move.l #$a0,d0 / move.w d7,d1 / addq.w #1,d1 / mulu.w d1,d0 / subq.w #1,d0 / dbf d0`: the product
# is 32 bits but the decrement and the `dbf` are WORD-sized, so the pass count is the product's low
# word. The game's own loop only ever reaches step 39 (160 x 40 = 6,400, far inside a word), but the
# slice is entered with D7 as an input — exactly like `sound_voice_priority`'s out-of-range index —
# so these are legal inputs that separate the two arithmetics.
WIPE_WORD_BOUNDARY_STEP = 409        # 160 x 410 = 0x10040: 64 longs presented, not 65,600
WIPE_WORD_BOUNDARY_LONGS = 64

# ...and the other end: step -1 makes `addq.w #1,d1` zero, so `mulu` gives 0, `subq.w #1` gives
# 0xffff and the `dbf` runs the full 65,536 times. That does not fit the scratch map the rest of
# this battery stages in — 262,144 bytes from `screen_back` would run past the model's staged-file
# table — so the case re-stages the two screens LOW, inside the same free window, keeping the
# machine's own `screen_back = screen_phys - SCREEN_BYTES` relationship.
WIPE_MAX_STEP = 0xffff
WIPE_MAX_STEP_LONGS = 0x10000
WIDE_SCREEN_PHYS = 0x70000
WIDE_SCREEN_BACK = WIDE_SCREEN_PHYS - SCREEN_BYTES
WIDE_STAGE = WIDE_SCREEN_BACK - ROOM_BYTES
# The descending move reads one WIPE_STEP_BYTES below the staging area at this step, and the ascend
# writes WIPE_MAX_STEP_LONGS longwords from screen_phys — so that is the whole span to seed.
WIDE_SPAN = (WIDE_STAGE - WIPE_STEP_BYTES, WIDE_SCREEN_PHYS + WIPE_MAX_STEP_LONGS * 4)
# 65,536 x 2 instructions for the present, plus 6,400 x 4 for the descending move: ~157,000. The cap
# is loose enough not to be a tuning knob and tight enough that a runaway is still caught.
WIPE_MAX_STEP_MAX_INSNS = 400_000

WIPE_SLIDE_MAX_INSNS = 2_000_000     # measured ~1.29M: 40 x 6,400 descending longs + 131,200 up


def test_room_wipe_in_step_counts_the_presented_longs_in_a_word():
    """Step 409, where the 32-bit product first passes 0x10000 and its low word does not.

    A reconstruction that computed `160 * (step + 1)` in 32 bits presents 65,600 longwords here
    instead of 64 — a quarter of a megabyte over everything above the screen — so this is the case
    that separates the `dbf`'s word counter from the `mulu`'s longword product.
    """
    pokes = _pokes(0x13b66 + WIPE_WORD_BOUNDARY_STEP, SCREEN_SPANS)
    diffs, _ = _run(ENTRY_ROOM_WIPE_IN_STEP,
                    lambda lib, buf: lib.g_room_wipe_in_step(buf, WIPE_WORD_BOUNDARY_STEP), pokes,
                    regs={"d7": WIPE_WORD_BOUNDARY_STEP}, stop_pc=STOP_ROOM_WIPE_IN_STEP)
    assert not diffs, report(diffs)


def test_room_wipe_in_step_at_the_word_boundary_presents_the_whole_counter():
    """Step -1: the word product is 0, so `subq.w #1` leaves 0xffff and the `dbf` runs 65,536 times.

    The far end of the same arithmetic, and the one input on which a 32-bit reconstruction presents
    NOTHING where the original presents 256 KiB. It runs on its own low staging (see WIDE_SCREEN_*)
    because that quarter-megabyte does not fit above `abi.SCRATCH`.
    """
    screens = {A_SCREEN_PHYS: abi.long(WIDE_SCREEN_PHYS), A_SCREEN_BACK: abi.long(WIDE_SCREEN_BACK)}
    pokes = _pokes(0x13b65, (WIDE_SPAN,), screens)
    diffs, _ = _run(ENTRY_ROOM_WIPE_IN_STEP,
                    lambda lib, buf: lib.g_room_wipe_in_step(buf, WIPE_MAX_STEP), pokes,
                    regs={"d7": WIPE_MAX_STEP}, stop_pc=STOP_ROOM_WIPE_IN_STEP,
                    max_insns=WIPE_MAX_STEP_MAX_INSNS)
    assert not diffs, report(diffs)


def test_room_wipe_in_slide():
    """The whole loop [0x13b62, 0x13bda), which is the only thing that pins the STEPS together —
    each step reads what the one before it wrote, so a wrong step size compounds rather than
    cancelling."""
    pokes = _pokes(0x13b62, SCREEN_SPANS)
    diffs, _ = _run(ENTRY_ROOM_WIPE_IN_SLIDE,
                    lambda lib, buf: lib.g_room_wipe_in_slide(buf), pokes,
                    stop_pc=STOP_ROOM_WIPE_IN_SLIDE, max_insns=WIPE_SLIDE_MAX_INSNS)
    assert not diffs, report(diffs)


def test_room_wipe_in_slide_over_a_real_room():
    """...with the staging area holding what `draw_room_to_stage` would really have composed there:
    room 1's map, drawn cell by cell from the real GHOST.DAT before the slide runs.

    The composition is run under the ORACLE, not through the candidate: staging the wipe's input
    with the code under test would make the case circular. So the bytes the slide moves here are
    the ones the original's own tile blitter put there.
    """
    image = harness.make_image(_pokes(0x13b63, SCREEN_SPANS, _real_dat_poke()))
    for tile_row in range(ROOM_TILE_ROWS):
        for tile_col in range(ROOM_TILE_COLS):
            image[FRAME_TILE_ROW:FRAME_TILE_ROW + 2] = abi.word(tile_row)
            image[FRAME_TILE_COL:FRAME_TILE_COL + 2] = abi.word(tile_col)
            image, _writes, _regs = emu.run(image, ENTRY_DRAW_ROOM_TILE_TO_STAGE,
                                            {"a4": abi.A4_BASE, "a6": FRAME_A6},
                                            stop_pc=STOP_DRAW_ROOM_TILE_TO_STAGE)
    composed = {STAGE: bytes(image[STAGE:SCREEN_BACK])}
    pokes = _pokes(0x13b63, SCREEN_SPANS, {**_real_dat_poke(), **composed})
    diffs, _ = _run(ENTRY_ROOM_WIPE_IN_SLIDE,
                    lambda lib, buf: lib.g_room_wipe_in_slide(buf), pokes,
                    stop_pc=STOP_ROOM_WIPE_IN_SLIDE, max_insns=WIPE_SLIDE_MAX_INSNS)
    assert not diffs, report(diffs)


# ======================================================================== the staging's own pins

SCREEN_TOTAL_ROWS = 200          # 320x200 low resolution
PICTURE_ROWS = 192               # what a full-screen picture covers, and all `clear` clears


def test_the_screen_and_tile_geometry_agree():
    """The constants src/blit.c computes every offset from, checked against each other.

    Not a differential — the arithmetic below is what makes the numbers a MODEL of the screen
    rather than ten literals read off ten instructions. A `#define` mistyped in include/blit.h
    fails here by name before any case has to explain a smeared image.
    """
    assert SCREEN_BYTES == SCREEN_TOTAL_ROWS * SCREEN_ROW_BYTES
    assert CLEARED_SCREEN_BYTES == PICTURE_ROWS * SCREEN_ROW_BYTES
    assert TILE_BYTES == TILE_PIXELS * TILE_ROW_BYTES
    assert TILE_ROW_SCREEN_BYTES == TILE_PIXELS * SCREEN_ROW_BYTES
    assert ROOM_BYTES == ROOM_TILE_ROWS * TILE_ROW_SCREEN_BYTES
    assert BANK_TILE_ROWS * ROOM_TILE_COLS == TILES_PER_BANK, "the bank screen is one whole bank"
    assert WIPE_STEPS * WIPE_STEP_BYTES == ROOM_BYTES, "the slide arrives exactly one room down"
    # The counters' band lies inside the HUD tile row, which is why `present_score_strip` is a
    # cheaper `present_hud_row` and not a different picture.
    assert ROOM_BYTES < SCORE_STRIP_OFFSET
    assert SCORE_STRIP_OFFSET + SCORE_STRIP_BYTES <= ROOM_BYTES + TILE_ROW_SCREEN_BYTES


def test_the_wide_wipe_staging_stays_inside_the_free_window():
    """The 65,536-longword present writes 256 KiB, which only fits below the scratch map.

    Its window is [BG_PROGRAM_END, OS_FS_TABLE) — above the program's last byte, below the model's
    staged-file table — and the descending move reaches one wipe step below the staging area, so
    both ends are checked rather than the destination alone.
    """
    from test_image_model import BG_PROGRAM_END

    assert WIDE_SCREEN_BACK == WIDE_SCREEN_PHYS - SCREEN_BYTES, "the machine's own relationship"
    assert WIDE_STAGE == WIDE_SCREEN_BACK - ROOM_BYTES
    assert WIDE_SPAN[0] >= BG_PROGRAM_END, "the descending move reaches into the program"
    assert WIDE_SPAN[1] == WIDE_SCREEN_PHYS + WIPE_MAX_STEP_LONGS * 4
    assert WIDE_SPAN[1] <= harness.OS_FS_TABLE, "the present runs into the staged-file table"
    assert (WIPE_STEP_BYTES // 4) * ((WIPE_WORD_BOUNDARY_STEP + 1) & 0xffff) & 0xffff \
        == WIPE_WORD_BOUNDARY_LONGS, "step 409's low word is not the 64 longs the case expects"


def test_the_staged_screens_fit_the_scratch_map():
    """Everything this battery pokes lies inside `test/abi.py`'s declared span, so no case reaches
    the staged-file table above it or the Malloc arena below."""
    assert abi.SCRATCH <= STAGE
    assert SCREEN_TOP <= abi.SCRATCH + abi.SCRATCH_BYTES
    assert SCREEN_BACK == SCREEN_PHYS - SCREEN_BYTES, "the machine's own screen relationship"
    assert STAGE == SCREEN_BACK - ROOM_BYTES


def test_the_staged_banks_are_separated_and_inside_the_arena():
    """The seven buffers sit in the arena `project.toml` places, clear of the program below and of
    the scratch map above — SEPARATED, which is what makes the bank split observable at all, and at
    IRREGULAR distances, which is what makes the pointer load observable."""
    top = _bank(DAT_BANKS - 1) + DAT_BANK_BYTES
    assert _bank(0) >= emu.OS_HEAP_BASE, "the staged banks start below the model's Malloc arena"
    gaps = [_bank(i + 1) - (_bank(i) + DAT_BANK_BYTES) for i in range(DAT_BANKS - 1)]
    assert all(gap > 0 for gap in gaps), (
        "packed banks make dat_bank[n / 60] + (n % 60) * 512 equal dat_bank[0] + n * 512, and the "
        f"divs.w #$3c split stops being observable — gaps {gaps}")
    assert len(set(gaps)) > 1, (
        "a CONSTANT gap is still an affine layout: a candidate computing bank n's address as "
        f"base + n * stride would match every case without ever loading dat_bank[n] — gaps {gaps}")
    assert all(address % 2 == 0 for address in BANK_ADDRESSES), "a `move.l` source must be even"
    assert top <= BANK_TOP <= WRAP_BAND[0], "the staged banks reach the wrapped-offset band"
    assert WRAP_BAND[1] <= abi.STUB
    assert len(GHOST_DAT) >= DAT_BANKS_FROM_FILE * DAT_BANK_BYTES


def test_the_mid_entry_frame_is_stack_scratch():
    """A slice's locals must land where the differential drops them AND where its stray-write check
    still calls them stack — otherwise the frame spills would read as program output."""
    for address in (FRAME_TILE_ROW, FRAME_TILE_COL):
        assert emu.STACK_GUARD_LO <= address < emu.STACK_TOP
        assert address >= emu.STACK_TOP - emu.STACK_SCRATCH


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("SCREEN_ROW_BYTES", "include/blit.h", "SCREEN_ROW_BYTES"),
    ("SCREEN_BYTES", "include/blit.h", "SCREEN_BYTES"),
    ("CLEARED_SCREEN_BYTES", "include/blit.h", "CLEARED_SCREEN_BYTES"),
    ("TILE_PIXELS", "include/blit.h", "TILE_PIXELS"),
    ("TILE_ROW_BYTES", "include/blit.h", "TILE_ROW_BYTES"),
    ("TILE_BYTES", "include/blit.h", "TILE_BYTES"),
    ("TILE_ROW_SCREEN_BYTES", "include/blit.h", "TILE_ROW_SCREEN_BYTES"),
    ("TILES_PER_BANK", "include/blit.h", "TILES_PER_BANK"),
    ("DAT_BANKS", "include/blit.h", "DAT_BANKS"),
    ("ROOM_TILE_COLS", "include/blit.h", "ROOM_TILE_COLS"),
    ("ROOM_TILE_ROWS", "include/blit.h", "ROOM_TILE_ROWS"),
    ("BANK_TILE_ROWS", "include/blit.h", "BANK_TILE_ROWS"),
    ("ROOM_BYTES", "include/blit.h", "ROOM_BYTES"),
    ("SCORE_STRIP_OFFSET", "include/blit.h", "SCORE_STRIP_OFFSET"),
    ("SCORE_STRIP_BYTES", "include/blit.h", "SCORE_STRIP_BYTES"),
    ("HUD_TILE_BANK", "include/blit.h", "HUD_TILE_BANK"),
    ("HUD_FIRST_TILE_IN_BANK", "include/blit.h", "HUD_FIRST_TILE_IN_BANK"),
    ("WIPE_STEPS", "include/blit.h", "WIPE_STEPS"),
    ("WIPE_STEP_BYTES", "include/blit.h", "WIPE_STEP_BYTES"),
    ("OBJECT_SLOTS", "include/blit.h", "OBJECT_SLOTS"),
    ("OBJECT_STRIDE", "include/blit.h", "OBJECT_STRIDE"),
    ("OBJECT_ROOM_STRIDE", "include/blit.h", "OBJECT_ROOM_STRIDE"),
    ("OBJECT_TILE", "include/blit.h", "OBJECT_TILE"),
    ("OBJECT_COUNTDOWN", "include/blit.h", "OBJECT_COUNTDOWN"),
    ("OBJECT_RELOAD", "include/blit.h", "OBJECT_RELOAD"),
    ("OBJECT_X", "include/blit.h", "OBJECT_X"),
    ("OBJECT_Y", "include/blit.h", "OBJECT_Y"),
    ("OBJECT_FRAME", "include/blit.h", "OBJECT_FRAME"),
    ("OBJECT_FRAME_COUNT", "include/blit.h", "OBJECT_FRAME_COUNT"),
    ("ROOM_STRIDE", "include/blit.h", "ROOM_STRIDE"),
    ("ROOM_MAP_ROW_BYTES", "include/blit.h", "ROOM_MAP_ROW_BYTES"),
    ("ROOM_MAP_CELL_BYTES", "include/blit.h", "ROOM_MAP_CELL_BYTES"),
    ("MFDB_PLANES", "include/blit.h", "MFDB_PLANES"),
    ("A_SCREEN_PHYS", "include/blit.h", "A_screen_phys"),
    ("A_SCREEN_BACK", "include/blit.h", "A_screen_back"),
    ("A_DAT_BANK", "include/blit.h", "A_dat_bank"),
    ("A_BANK_INDEX", "include/blit.h", "A_bank_index"),
    ("A_MFDB_SRC", "include/blit.h", "A_mfdb_src"),
    ("A_MFDB_DST", "include/blit.h", "A_mfdb_dst"),
    ("A_ROOM_NUMBER", "include/blit.h", "A_room_number"),
    ("A_OBJECT_TABLE", "include/blit.h", "A_object_table"),
    ("A_ROOM_TABLE", "include/blit.h", "A_room_table"),
)

# TWENTY BYTES, not the usual eight or ten. Five of the routines here open with the identical
# `link a6,#$0 / movem.l #$0030,-(a7) / move.l -7630(a4),d0` and separate only at the `add.l #$…`
# that names the band they copy — so a shorter prologue would let `present_hud_row` stand for
# `present_score_strip`, and a mistyped entry would run the wrong routine and still come back clean.
ENTRY_PROLOGUES = {
    "ENTRY_CLEAR_PHYSICAL_SCREEN": "4e5600002f0b202ce22e26404280303c1dff26fc",
    "ENTRY_PRESENT_SCORE_STRIP": "4e56000048e70030202ce232d0bc000065402640",
    "ENTRY_PRESENT_HUD_ROW": "4e56000048e70030202ce232d0bc000064002640",
    "ENTRY_STAGE_TO_WORK": "4e56000048e70030202ce23290bc000064002640",
    "ENTRY_PRESENT_ROOM": "4e56000048e70030202ce2322640202ce22e2440",
    "ENTRY_BUILD_SPRITE_BANK": "4e56fff4426ce2044eba03a4397c0020e1ea397c",
    "ENTRY_DRAW_TILE_BANK_SCREEN": "4e56fffc48e70030302ce204e58041ece210d0c0",
    "ENTRY_DRAW_HUD_ROW_TILES": "4e56fffe48e70030202ce224d0bc000064002640",
    "ENTRY_OBJECTS_ANIMATE_AND_DRAW": "4e56fff048e70030426efffe600001de302efffe",
    "ENTRY_DRAW_ROOM_TILE_TO_STAGE": "302efffc322ce206c3fc007841eccb30d288c1fc",
    "ENTRY_ROOM_WIPE_IN_SLIDE": "4247606e202ce232d0bc000063fc323c0280c3c7",
    "ENTRY_ROOM_WIPE_IN_STEP": "202ce232d0bc000063fc323c0280c3c748c1d081",
}
