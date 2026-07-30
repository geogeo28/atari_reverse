"""Differential tests for Joust's startup chain (src/init.c).

Covered here: init_system @ 0x10080, init_video @ 0x104b2, init_game @ 0x105f0, and _start @ 0x10000
as far as its third call. title_screen @ 0x10aae is NOT reconstructed; the reason is pinned by
test_title_screen_is_blocked_on_two_unported_functions.

This is the most trap-dense code in the game, so the kit's TOS model
(../../../../tools/recreate_kit/TRAP_MODEL.md) sets what can be proved at all. Four of its limits
shape this whole file:

  * **XBIOS Getrez answers 0 for every run.** init_system's monochrome branch is therefore
    unreachable under the oracle, so no case executes it and nothing here verifies it. Its
    constants are pinned against the ORIGINAL'S INSTRUCTION ENCODINGS instead, which is all that is
    honestly available (the same technique test_sound.py uses for snd_tone_sweep's unobservable
    starting values).
  * **Setpalette / Setcolor / Setscreen / Ikbdws / Kbdvbase / Physbase change no memory.** A wrong
    argument to any of them is invisible to an image diff, so `_pushed_words` reads them back out of
    the oracle's own stack at a checkpoint placed on the trap's return address. It reads the final
    IMAGE rather than the write set, because a later push overwrites the same stack bytes and the
    write set records each address's FINAL value — which is a different trap's argument.
  * **A file the harness never staged rejects the whole run.** Every init_system case therefore
    stages HIGH.SCO; test_init_system_needs_high_sco_staged is what says so out loud.
  * **_start never returns.** It is diffed at a checkpoint PC, PAIRED with a proof that the run
    really does not reach `rts` — otherwise a checkpointed run that fell through would stop at the
    sentinel and pass silently.
"""
import random
import struct

import ctypes
import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines     # the shared `#define` scraper; see the pins at the end

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_START = 0x10000
ENTRY_INIT_SYSTEM = 0x10080
ENTRY_INIT_VIDEO = 0x104b2
ENTRY_INIT_GAME = 0x105f0
ENTRY_TITLE_SCREEN = 0x10aae

# ---- checkpoint PCs (harness `stop_pc`) ----
# _start's third `jsr`. Everything before it is init_system and init_game; title_screen and the
# per-frame loop after it are unreconstructed (see the module comment in ../src/init.c).
CHECKPOINT_START_AT_TITLE = 0x1000c
# The return address of each trap whose arguments the image cannot show. Reaching one of these means
# the trap has been serviced and A7 is back at the caller's pushes, which are still in memory.
AFTER_GETREZ = 0x10086
AFTER_FIRST_SETCOLOR = 0x10164
AFTER_PALETTE_LOOP = 0x10184      # ...and here the LAST Setcolor's pushes are still there
AFTER_SUPER = 0x1018c
AFTER_KBDVBASE = 0x101a8
AFTER_IKBDWS = 0x101da
AFTER_SETSCREEN = 0x101f0
AFTER_PHYSBASE = 0x101fc
AFTER_FOPEN = 0x10274
AFTER_FREAD = 0x10292
AFTER_FCLOSE = 0x102aa
AFTER_SETPALETTE = 0x104be        # init_video's
AFTER_RANDOM = 0x106ba            # init_game's

# ---- the two functions title_screen is blocked on (../STATUS.md) ----
ENTRY_XBIOS_SETPALETTE = 0x10c46
ENTRY_CYCLE_PALETTE = 0x10c56

# ---- globals (mirrors of include/init.h and the headers it includes) ----
A_SCREEN_BASE = 0x10dde
A_PLAYERS_ALIVE = 0x10cf2
A_PLATFORM_PRESENT = 0x10cfa
A_TWO_PLAYER_MODE = 0x10d11
A_GAME_OVER_FLAG = 0x10d12
A_SAVED_MOUSEVEC = 0x10d18
A_SAVED_JOYVEC = 0x10d1c
A_SAVED_REZ = 0x10d20
A_CONTERM_SAVE = 0x10d22
A_SAVED_PALETTE = 0x10d26
A_GROUND_ANIM_TIMER = 0x10d66
A_GROUND_ANIM = 0x10d68
A_PLAYFIELD_BOTTOM = 0x10d60
A_TROLL_STATE = 0x10dc4
A_DRAW_DST = 0x10de8               # init_system's palette write cursor
A_DRAW_X = 0x10dec                 # ...its pen, and then its GEMDOS file handle
A_SPAWN_TIMER = 0x10dfc
A_RNG_PTR = 0x10dfe
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36
A_PLAYER2 = 0x10f84
A_ENEMY_OBJECTS = 0x10fd2
A_EFFECT_TABLE = 0x1137a
A_PTERODACTYL_TABLE = 0x113ba
A_GAME_PALETTE = 0x1143a           # also A_pterodactyl_table_END
A_IKBD_CMD_JOYMODE = 0x1145a
A_INIT_PLAYERS_TEMPLATE = 0x1145c
A_INIT_GLOBALS_TEMPLATE = 0x114f8
A_INIT_GLOBALS_TEMPLATE_END = 0x1150f
A_GROUND_X0 = 0x117b8
A_GROUND_X1 = 0x117ba
A_SPAWN_POINTS = 0x11964
A_SPAWN_POINTS_END = 0x119b4
A_HISCORE_DIRTY = 0x18388
A_HISCORE_NAME = 0x18396
A_FNAME_HIGHSCO = 0x102c8
A_FNAME_MONO_ERR = 0x102be
A_IKBD_MOUSE_HANDLER = 0x102d2
A_IKBD_JOY_HANDLER = 0x102da
A_LOAD_BUFFER = 0x23aae

# ---- record layout (mirrors of the headers init.h includes) ----
OBJ_SCORE_PTR = 0x36
OBJ_LIVES = 0x4c                   # score.h; varied by the init_video fuzz
OBJ_RECORD = A_PLAYER2 - A_OBJECT_TABLE
MSG_RECORD, MSG_KIND = 0xc, 0
PT_RECORD, PT_FLAGS = 0x20, 0
EFF_RECORD, EFF_TIMER = 0x10, 0
SPAWN_RECORD, SPAWN_IN_USE = 0x14, 0

# ---- TOS state ----
TOS_CONTERM = 0x484
OS_KBDVBASE = 0x500                # os.h: what XBIOS Kbdvbase returns
KBDVBASE_MOUSEVEC, KBDVBASE_JOYVEC = 0x10, 0x18
OS_SCREEN_BASE = 0x8000            # os.h: what XBIOS Physbase returns

# ---- the trap selectors this chain issues ----
GEMDOS_SUPER, GEMDOS_FOPEN, GEMDOS_FCLOSE, GEMDOS_FREAD = 0x20, 0x3d, 0x3e, 0x3f
XBIOS_PHYSBASE, XBIOS_GETREZ, XBIOS_SETSCREEN = 0x02, 0x04, 0x05
XBIOS_SETPALETTE, XBIOS_SETCOLOR, XBIOS_RANDOM = 0x06, 0x07, 0x11
XBIOS_IKBDWS, XBIOS_KBDVBASE = 0x19, 0x22

GEMDOS_OPEN_MODE_RW = 2            # what Fopen's mode word is here; the model ignores it
SETSCREEN_KEEP = 0xffff            # Setscreen(-1, -1, rez): leave both screen pointers alone
SETCOLOR_QUERY = 0xffff            # Setcolor(pen, -1): read the pen back without changing it
IKBDWS_ONE_BYTE = 0                # Ikbdws' length word is count - 1
PALETTE_PENS = 0x10
HISCORE_FILE_BYTES = 0x1a
HISCORE_LOADED_MARK = 0x20
SCREEN_BYTES = 0x7d00
HIGHSCO_NAME = "HIGH.SCO"

# ---- init_video's score bar ----
HUD_BAR_OFF = 0x6ae0
HUD_BAR_COLUMN = 0x80
HUD_BAR_PASSES = 4
HUD_BAR_PLANES01, HUD_BAR_PLANES23 = 0x0000ffff, 0xffffffff
SCREEN_ROW_BYTES = 0xa0

# ---- staging ----
# A scratch screen clear of the program (which ends 0x2b7ae), of abi's stub space and of the staged
# file table; filled with noise so a missing write shows as a diff rather than as zero over zero.
SCREEN = 0x70000
SCREEN_SPAN = 0x8000
UNWRITTEN_B, UNWRITTEN_L = 0x5a, 0x5a5a5a5a
STAGED_MOUSEVEC, STAGED_JOYVEC = 0x0001a5a5, 0x0001c3c3

# init_game clears the first field of every record across four tables that happen to be contiguous
# (messages, objects, effects, pterodactyls), so one noise poke covers all of them; the spawn pads
# and the globals template's destination get their own.
NOISE_TABLES = ((A_MESSAGE_TABLE, A_GAME_PALETTE - A_MESSAGE_TABLE),
                (A_SPAWN_POINTS, A_SPAWN_POINTS_END - A_SPAWN_POINTS),
                (A_PLAYERS_ALIVE, A_INIT_GLOBALS_TEMPLATE_END - A_INIT_GLOBALS_TEMPLATE))

# A run that spins for ever is capped rather than run to the harness default. It must still be large
# enough that a run which DID return would have finished — _start's title screen alone copies a
# whole framebuffer — or "did not reach rts" would prove nothing.
SPIN_CAP = 1_000_000

FUZZ_CHUNKS = 2

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue in ("g_start", "g_init_system", "g_init_video", "g_init_game"):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P]
    _fn.restype = None


def _system(lib, buf):
    return lib.g_init_system(buf)


def _video(lib, buf):
    return lib.g_init_video(buf)


def _game(lib, buf):
    return lib.g_init_game(buf)


def _start(lib, buf):
    return lib.g_start(buf)


# ------------------------------------------------------------------ shared staging helpers

def _noise(seed, length):
    return bytes(random.Random(seed).randrange(0x100) for _ in range(length))


def _system_pokes(seed=1, conterm=0xff, hiscore=None):
    """Everything init_system reads, plus a sentinel everywhere it must write.

    HIGH.SCO is always staged: os_fopen refuses a name the harness never declared, and a refused
    call rejects the oracle's whole run (see test_init_system_needs_high_sco_staged).
    """
    pokes = {A_SAVED_PALETTE: _noise(seed, 2 * PALETTE_PENS),
             # A sentinel one word past the palette: the loop must stop after PALETTE_PENS pens.
             A_SAVED_PALETTE + 2 * PALETTE_PENS: bytes([UNWRITTEN_B, UNWRITTEN_B]),
             TOS_CONTERM: bytes([conterm]),
             OS_KBDVBASE + KBDVBASE_MOUSEVEC: struct.pack(">I", STAGED_MOUSEVEC),
             OS_KBDVBASE + KBDVBASE_JOYVEC: struct.pack(">I", STAGED_JOYVEC)}
    for addr, width in ((A_SCREEN_BASE, 4), (A_SAVED_REZ, 2), (A_CONTERM_SAVE, 1),
                        (A_SAVED_MOUSEVEC, 4), (A_SAVED_JOYVEC, 4), (A_DRAW_X, 2), (A_DRAW_DST, 4),
                        (A_HISCORE_NAME, HISCORE_FILE_BYTES), (A_HISCORE_DIRTY, 1),
                        (A_TWO_PLAYER_MODE, 1)):
        pokes[addr] = bytes([UNWRITTEN_B]) * width
    record = hiscore if hiscore is not None else _noise(seed + 1, HISCORE_FILE_BYTES)
    file_pokes, _ = harness.stage_files([(HIGHSCO_NAME, record)])
    pokes.update(file_pokes)
    return pokes


def _game_pokes(seed=1, screen=SCREEN, random_value=0x123456):
    """Noise over every table init_game clears, plus its two inputs (screen_base and XBIOS Random)."""
    pokes = {addr: _noise(seed + index, length)
             for index, (addr, length) in enumerate(NOISE_TABLES)}
    pokes[A_SCREEN_BASE] = struct.pack(">I", screen)
    pokes[harness.OS_RANDOM_VALUE] = struct.pack(">I", random_value)
    return pokes


def _after_init_game(seed=1, screen=SCREEN, lives=None):
    """The image init_game leaves behind — which is what init_video runs on inside _start.

    Built here from the templates rather than by running init_game, so init_video's battery does not
    rest on the routine it sits next to: a wrong template address fails as a diff, not as a silent
    agreement between two copies of the same mistake.
    """
    base = harness.BASE_IMAGE
    players = bytearray(base[A_INIT_PLAYERS_TEMPLATE:A_INIT_GLOBALS_TEMPLATE])
    for index, slot in enumerate((0, OBJ_RECORD)):
        field = slot + OBJ_SCORE_PTR
        struct.pack_into(">I", players, field,
                         struct.unpack_from(">I", players, field)[0] + screen)
        if lives is not None:
            players[slot + OBJ_LIVES] = lives[index]
    return {screen: _noise(seed, SCREEN_SPAN),
            A_OBJECT_TABLE: bytes(players),
            A_PLAYERS_ALIVE: bytes(base[A_INIT_GLOBALS_TEMPLATE:A_INIT_GLOBALS_TEMPLATE_END]),
            A_SCREEN_BASE: struct.pack(">I", screen)}


def _oracle_final(pokes, entry, **run_args):
    """The oracle's final image, for the checks that must look at MODEL state or at the stack.

    Not `info["writes"]`: that maps each written address to its FINAL value, so a stack slot pushed
    twice reports only the second push — which is a different trap's argument — and the trap model
    reaches the image directly (os_fread filling hiscore_name), never through the write set.
    """
    image, _, _ = emu.run(harness.make_image(pokes), entry, **run_args)
    return image


def _pushed_words(image, count):
    """The `count` words still on the oracle's stack, outermost (highest address) first."""
    return [struct.unpack_from(">H", image, emu.STACK_TOP - 2 * (index + 1))[0]
            for index in range(count)]


def _pushed_long(words, index):
    """The longword pushed at `index`: its LOW word is the outermost of the pair."""
    return (words[index + 1] << 16) | words[index]


def _trap_args(pokes, entry, stop_pc, count):
    """The `count` words the original had pushed when the trap at `stop_pc` returned."""
    return _pushed_words(_oracle_final(pokes, entry, stop_pc=stop_pc), count)


def _never_returns(pokes, entry):
    """Assert the original does not come back from `entry` on this input.

    The `stop_pc` run elsewhere would pass just as happily on a routine that fell through to `rts` —
    osh_run stops at the sentinel or the checkpoint and reports success either way — so every
    checkpointed branch is paired with this.
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(pokes), entry, max_insns=SPIN_CAP)


# ================================================================== init_game @ 0x105f0

def _game_case(poison=True, **kwargs):
    pokes = _game_pokes(**kwargs)
    diffs, info = differential(ENTRY_INIT_GAME, {"_pokes": pokes}, _game, poison=poison)
    assert not diffs, f"{kwargs}\n{report(diffs)}"
    return pokes, info


def test_init_game_resets_one_games_worth_of_state():
    _game_case()


@pytest.mark.parametrize("screen", (0, OS_SCREEN_BASE, SCREEN, 0x7fffc, 0xfff80000))
def test_init_game_relocates_every_pointer_by_screen_base(screen):
    """screen_base is folded into both score rows and into playfield_bottom, all as FULL longwords —
    so a base that wraps 32 bits (the last case) must wrap the same way."""
    pokes, _ = _game_case(screen=screen)
    image = _oracle_final(pokes, ENTRY_INIT_GAME)
    template = harness.BASE_IMAGE
    for slot, player in ((0, A_OBJECT_TABLE), (OBJ_RECORD, A_PLAYER2)):
        offset = struct.unpack_from(">I", template,
                                    A_INIT_PLAYERS_TEMPLATE + slot + OBJ_SCORE_PTR)[0]
        assert struct.unpack_from(">I", image, player + OBJ_SCORE_PTR)[0] == \
            (offset + screen) & 0xffffffff
    assert struct.unpack_from(">I", image, A_PLAYFIELD_BOTTOM)[0] == \
        (screen + SCREEN_BYTES) & 0xffffffff


@pytest.mark.parametrize("random_value", (0, 1, 2, 0xfe, 0xff, 0x100, 0x1ff, 0xfffffe, 0xffffff,
                                          0xff00ff, 0x5555aa))
def test_init_game_seeds_the_rng_cursor_with_an_even_offset(random_value):
    """`andi.l #$fe` on the WHOLE longword: only bits 1..7 of XBIOS Random survive, so the cursor
    starts at most 254 bytes into the image and always on an even address."""
    pokes, _ = _game_case(random_value=random_value)
    image = _oracle_final(pokes, ENTRY_INIT_GAME)
    load_base = _defines("include/addrs.h")["IMAGE_LOAD_BASE"]
    seed_mask = _defines("src/init.c")["RNG_SEED_MASK"]
    assert struct.unpack_from(">I", image, A_RNG_PTR)[0] == load_base + (random_value & seed_mask)


def test_init_game_clears_exactly_the_first_field_of_every_slot():
    """The four table sweeps: each clears one field per record and leaves the noise either side of
    it, which is what pins both the stride and the exclusive bound."""
    pokes, _ = _game_case()
    before, after = harness.make_image(pokes), _oracle_final(pokes, ENTRY_INIT_GAME)
    for table, end, stride, field, width in (
            (A_SPAWN_POINTS, A_SPAWN_POINTS_END, SPAWN_RECORD, SPAWN_IN_USE, 1),
            (A_MESSAGE_TABLE, A_OBJECT_TABLE, MSG_RECORD, MSG_KIND, 1),
            (A_PTERODACTYL_TABLE, A_GAME_PALETTE, PT_RECORD, PT_FLAGS, 2),
            (A_EFFECT_TABLE, A_PTERODACTYL_TABLE, EFF_RECORD, EFF_TIMER, 4)):
        slots = 0
        for slot in range(table, end, stride):
            assert after[slot + field:slot + field + width] == bytes(width), \
                f"slot {slot:#x} of the table at {table:#x} was not cleared"
            tail = slice(slot + field + width, slot + stride)
            assert after[tail] == before[tail], \
                f"slot {slot:#x} of the table at {table:#x} lost bytes past its first field"
            slots += 1
        assert slots == (end - table) // stride

    assert after[A_ENEMY_OBJECTS:A_EFFECT_TABLE] == bytes(A_EFFECT_TABLE - A_ENEMY_OBJECTS), \
        "the 12 non-player object slots are cleared wholesale, players excepted"
    assert after[A_OBJECT_TABLE:A_ENEMY_OBJECTS] != bytes(A_ENEMY_OBJECTS - A_OBJECT_TABLE), \
        "...and the two player records the templates just filled are NOT part of that sweep"


def test_init_game_copies_both_templates_out_of_the_program():
    pokes, _ = _game_case()
    image = _oracle_final(pokes, ENTRY_INIT_GAME)
    base = harness.BASE_IMAGE
    globals_span = A_INIT_GLOBALS_TEMPLATE_END - A_INIT_GLOBALS_TEMPLATE
    assert image[A_PLAYERS_ALIVE:A_PLAYERS_ALIVE + globals_span] == \
        base[A_INIT_GLOBALS_TEMPLATE:A_INIT_GLOBALS_TEMPLATE_END]
    assert image[A_PLATFORM_PRESENT:A_PLATFORM_PRESENT + 8] == bytes([1] * 8), \
        "the globals template is what puts all eight platforms back"
    # The players' records, bar the two score pointers the relocation above rewrites.
    for slot in (0, OBJ_RECORD):
        record = bytearray(base[A_INIT_PLAYERS_TEMPLATE + slot:
                                A_INIT_PLAYERS_TEMPLATE + slot + OBJ_RECORD])
        copied = bytearray(image[A_OBJECT_TABLE + slot:A_OBJECT_TABLE + slot + OBJ_RECORD])
        record[OBJ_SCORE_PTR:OBJ_SCORE_PTR + 4] = copied[OBJ_SCORE_PTR:OBJ_SCORE_PTR + 4]
        assert copied == record


def test_init_game_sets_the_scalar_state():
    pokes, _ = _game_case()
    image = _oracle_final(pokes, ENTRY_INIT_GAME)
    init_c = _defines("src/init.c")
    assert struct.unpack_from(">H", image, A_SPAWN_TIMER)[0] == init_c["SPAWN_TIMER_INIT"]
    assert image[A_GROUND_ANIM_TIMER] == init_c["GROUND_ANIM_TIMER_INIT"]
    assert struct.unpack_from(">H", image, A_GROUND_X1)[0] == init_c["GROUND_X1_INIT"]
    assert struct.unpack_from(">H", image, A_GROUND_X0)[0] == 0
    assert struct.unpack_from(">H", image, A_GROUND_ANIM)[0] == 0
    assert struct.unpack_from(">H", image, A_TROLL_STATE)[0] == 0
    assert image[A_GAME_OVER_FLAG] == 0


def test_init_game_asks_xbios_random_for_its_seed():
    """XBIOS Random takes no argument, so only the selector says the call happened at all."""
    words = _trap_args(_game_pokes(), ENTRY_INIT_GAME, AFTER_RANDOM, 1)
    assert words[0] == XBIOS_RANDOM


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_init_game_fuzz(chunk):
    """Noise seeds x screen bases x Random values, so no case can pass by writing zero over zero."""
    rng = random.Random(0x105f0)
    cases = [(seed, screen, rng.getrandbits(24))
             for seed in range(12)
             for screen in (0, SCREEN, OS_SCREEN_BASE, 0xffff0000)]
    ran = 0
    for index, (seed, screen, random_value) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _game_pokes(seed=seed, screen=screen, random_value=random_value)
        diffs, _ = differential(ENTRY_INIT_GAME, {"_pokes": pokes}, _game)
        assert not diffs, f"seed={seed} screen={screen:#x} random={random_value:#x}\n{report(diffs)}"
        ran += 1
    assert ran, "this shard ran no cases"


# ================================================================== init_video @ 0x104b2

def _video_case(poison=True, **kwargs):
    pokes = _after_init_game(**kwargs)
    diffs, info = differential(ENTRY_INIT_VIDEO, {"_pokes": pokes}, _video, poison=poison)
    assert not diffs, f"{kwargs}\n{report(diffs)}"
    return pokes, info


def test_init_video_paints_the_first_frame():
    _video_case()


@pytest.mark.parametrize("screen", (0x60000, SCREEN, 0x78000))
def test_init_video_draws_from_screen_base(screen):
    _video_case(screen=screen)


@pytest.mark.parametrize("lives", ((0, 0), (1, 6), (3, 3), (0x7f, 0x80), (0xff, 0xfe)))
def test_init_video_draws_whatever_life_count_the_template_left(lives):
    """draw_lives_p1/p2 read the count as a SIGNED byte, so the high half of this range draws an
    empty row — reproduced, and the case exists so the two calls are not merely present."""
    _video_case(lives=lives)


def test_init_video_paints_the_score_bar():
    """Two four-cell blocks, three rows tall. Checked against an independent model of the six
    offsets, so a bar drawn at the wrong stride fails here as well as in the diff."""
    pokes, _ = _video_case(poison=False)
    image = _oracle_final(pokes, ENTRY_INIT_VIDEO)
    for pass_index in range(HUD_BAR_PASSES):
        cell = SCREEN + HUD_BAR_OFF + 8 * pass_index
        for row in range(3):
            for column in (0, HUD_BAR_COLUMN):
                at = cell + row * SCREEN_ROW_BYTES + column
                assert struct.unpack_from(">I", image, at)[0] == HUD_BAR_PLANES01
                assert struct.unpack_from(">I", image, at + 4)[0] == HUD_BAR_PLANES23


def test_init_video_hands_setpalette_the_game_palette():
    """The palette write is off-image, so this read-back is the only thing that can catch it."""
    words = _trap_args(_after_init_game(), ENTRY_INIT_VIDEO, AFTER_SETPALETTE, 3)
    assert words[2] == XBIOS_SETPALETTE
    assert _pushed_long(words, 0) == A_GAME_PALETTE, "Setpalette was handed the wrong table"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_init_video_fuzz(chunk):
    """Screen noise x screen base x both players' life counts."""
    rng = random.Random(0x104b2)
    cases = [(seed, screen, (rng.randrange(0x100), rng.randrange(0x100)))
             for seed in range(6)
             for screen in (0x60000, SCREEN)]
    ran = 0
    for index, (seed, screen, lives) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _after_init_game(seed=seed, screen=screen, lives=lives)
        diffs, _ = differential(ENTRY_INIT_VIDEO, {"_pokes": pokes}, _video)
        assert not diffs, f"seed={seed} screen={screen:#x} lives={lives}\n{report(diffs)}"
        ran += 1
    assert ran, "this shard ran no cases"


# ================================================================== init_system @ 0x10080

def _system_case(poison=True, **kwargs):
    pokes = _system_pokes(**kwargs)
    diffs, info = differential(ENTRY_INIT_SYSTEM, {"_pokes": pokes}, _system, poison=poison)
    assert not diffs, f"{kwargs}\n{report(diffs)}"
    return pokes, info


def test_init_system_takes_the_machine_over():
    _system_case()


def test_init_system_needs_high_sco_staged():
    """WHY EVERY CASE ABOVE STAGES THE FILE. os_fopen refuses a name the harness never declared, and
    a refusal rejects the ORACLE's whole run — so an unstaged run is not a green case with a missing
    high score, it is no case at all. The candidate's own half of the same asymmetry is caught by
    harness.differential's refusal tally (TRAP_MODEL.md)."""
    unstaged = {key: value for key, value in _system_pokes().items() if key < harness.OS_FS_TABLE}
    with pytest.raises(RuntimeError, match="unmodeled OS behaviour"):
        emu.run(harness.make_image(unstaged), ENTRY_INIT_SYSTEM)


@pytest.mark.parametrize("conterm", (0x00, 0x01, 0x07, 0x08, 0x0f, 0xf8, 0xff, 0x5a))
def test_init_system_saves_conterm_whole_and_masks_the_low_three_flags(conterm):
    """`andi.b #$f8` on the TOS variable, after the whole byte has been stashed for the quit path."""
    pokes, _ = _system_case(conterm=conterm)
    image = _oracle_final(pokes, ENTRY_INIT_SYSTEM)
    assert image[A_CONTERM_SAVE] == conterm
    assert image[TOS_CONTERM] == conterm & _defines("include/init.h")["CONTERM_KEEP"]


def test_init_system_hooks_the_ikbd_vectors_and_keeps_the_old_ones():
    pokes, _ = _system_case()
    image = _oracle_final(pokes, ENTRY_INIT_SYSTEM)
    assert struct.unpack_from(">I", image, A_SAVED_MOUSEVEC)[0] == STAGED_MOUSEVEC
    assert struct.unpack_from(">I", image, A_SAVED_JOYVEC)[0] == STAGED_JOYVEC
    assert struct.unpack_from(">I", image, OS_KBDVBASE + KBDVBASE_MOUSEVEC)[0] == \
        A_IKBD_MOUSE_HANDLER
    assert struct.unpack_from(">I", image, OS_KBDVBASE + KBDVBASE_JOYVEC)[0] == A_IKBD_JOY_HANDLER


def test_init_system_reads_back_all_sixteen_pens_and_stops():
    """The pen and the write cursor both live in memory and are re-read every pass. The model has no
    palette, so every answer is 0 — but the sentinel past the sixteenth word is what proves the loop
    stops where `cmpi.w #$10` says, and the final cursor is what proves it stepped a word at a time.
    """
    pokes, _ = _system_case()
    image = _oracle_final(pokes, ENTRY_INIT_SYSTEM)
    assert image[A_SAVED_PALETTE:A_SAVED_PALETTE + 2 * PALETTE_PENS] == bytes(2 * PALETTE_PENS)
    assert image[A_SAVED_PALETTE + 2 * PALETTE_PENS] == UNWRITTEN_B, "the loop ran past pen 15"
    assert struct.unpack_from(">I", image, A_DRAW_DST)[0] == A_SAVED_PALETTE + 2 * PALETTE_PENS
    assert struct.unpack_from(">H", image, A_DRAW_X)[0] != PALETTE_PENS, \
        "the pen word is reused as HIGH.SCO's file handle after the loop"


def test_init_system_loads_the_high_score():
    record = bytes(range(0x41, 0x41 + HISCORE_FILE_BYTES))
    pokes, _ = _system_case(hiscore=record)
    image = _oracle_final(pokes, ENTRY_INIT_SYSTEM)
    assert image[A_HISCORE_NAME:A_HISCORE_NAME + HISCORE_FILE_BYTES] == record
    assert image[A_HISCORE_DIRTY] == HISCORE_LOADED_MARK, (
        "a successful load leaves hiscore_dirty non-zero, which save_hiscore (src/input.c) tests "
        "with `tst.b` — so every Ctrl-C after a normal boot rewrites HIGH.SCO. Original behaviour")
    assert image[A_TWO_PLAYER_MODE] == 0
    assert struct.unpack_from(">I", image, A_SCREEN_BASE)[0] == OS_SCREEN_BASE, \
        "screen_base comes from XBIOS Physbase"
    assert struct.unpack_from(">H", image, A_SAVED_REZ)[0] == 0, \
        "the resolution Getrez reported, stashed for the Setscreen on the way out"


@pytest.mark.parametrize("stop_pc,expected", (
    (AFTER_GETREZ, (XBIOS_GETREZ,)),
    (AFTER_FIRST_SETCOLOR, (SETCOLOR_QUERY, 0, XBIOS_SETCOLOR)),
    (AFTER_PALETTE_LOOP, (SETCOLOR_QUERY, PALETTE_PENS - 1, XBIOS_SETCOLOR)),
    (AFTER_SUPER, (0, 0, GEMDOS_SUPER)),
    (AFTER_KBDVBASE, (0, 0, XBIOS_KBDVBASE)),
    (AFTER_SETSCREEN, (0, SETSCREEN_KEEP, SETSCREEN_KEEP, SETSCREEN_KEEP, SETSCREEN_KEEP,
                       XBIOS_SETSCREEN)),
    (AFTER_PHYSBASE, (XBIOS_PHYSBASE,)),
    (AFTER_FCLOSE, (harness.OS_FS_FIRST_HANDLE, GEMDOS_FCLOSE)),
))
def test_init_system_trap_arguments(stop_pc, expected):
    """Six of these traps change no memory at all, so their arguments are invisible to the diff.
    Read them back off the oracle's stack at the trap's own return address instead — including the
    LAST pen of the palette loop, whose pushes are still there when the loop falls out."""
    assert tuple(_trap_args(_system_pokes(), ENTRY_INIT_SYSTEM, stop_pc, len(expected))) == expected


def test_init_system_puts_the_ikbd_into_joystick_interrogation_mode():
    """One byte ($15) through XBIOS Ikbdws, whose length word is count - 1. It is what makes the $16
    interrogations title_screen and read_joysticks send later answerable — and it is off-image."""
    words = _trap_args(_system_pokes(), ENTRY_INIT_SYSTEM, AFTER_IKBDWS, 4)
    assert words[3] == XBIOS_IKBDWS
    assert words[2] == IKBDWS_ONE_BYTE
    assert _pushed_long(words, 0) == A_IKBD_CMD_JOYMODE


def test_init_system_opens_and_reads_high_sco_by_name():
    open_words = _trap_args(_system_pokes(), ENTRY_INIT_SYSTEM, AFTER_FOPEN, 4)
    assert open_words[3] == GEMDOS_FOPEN
    assert _pushed_long(open_words, 1) == A_FNAME_HIGHSCO
    assert open_words[0] == GEMDOS_OPEN_MODE_RW

    read_words = _trap_args(_system_pokes(), ENTRY_INIT_SYSTEM, AFTER_FREAD, 6)
    assert read_words[5] == GEMDOS_FREAD
    assert read_words[4] == harness.OS_FS_FIRST_HANDLE, "Fread is handed the handle still in D0"
    assert _pushed_long(read_words, 2) == HISCORE_FILE_BYTES
    assert _pushed_long(read_words, 0) == A_HISCORE_NAME


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_init_system_fuzz(chunk):
    """Palette noise x conterm x high-score record."""
    cases = [(seed, conterm) for seed in range(12) for conterm in (0x00, 0x5a, 0xff)]
    ran = 0
    for index, (seed, conterm) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _system_pokes(seed=seed, conterm=conterm)
        diffs, _ = differential(ENTRY_INIT_SYSTEM, {"_pokes": pokes}, _system)
        assert not diffs, f"seed={seed} conterm={conterm:#04x}\n{report(diffs)}"
        ran += 1
    assert ran, "this shard ran no cases"


# ---------------------------------------- the monochrome branch: UNREACHABLE, hence unverified

def test_getrez_answers_low_resolution_so_the_mono_branch_is_dead():
    """The whole reason nothing below is verified: the model has one resolution, and the routine
    stores Getrez' answer where the differential can see it. `cmpi.b #$2` therefore never matches,
    so the reconstruction's fixed TOS_REZ_LOW is a checked fact rather than a hidden mirror."""
    init_c = _defines("src/init.c")
    image = _oracle_final(_system_pokes(), ENTRY_INIT_SYSTEM)
    assert struct.unpack_from(">H", image, A_SAVED_REZ)[0] == init_c["TOS_REZ_LOW"]
    assert init_c["TOS_REZ_LOW"] != init_c["TOS_REZ_MONO"]


def _immediate(addr, width):
    """The operand the ORIGINAL encodes at `addr`, straight out of the relocated image."""
    return int.from_bytes(harness.BASE_IMAGE[addr:addr + width], "big")


def test_mono_branch_constants_match_the_original_encoding():
    """No run reaches the monochrome splash, so the differential proves nothing about it. Pin its
    constants against the instruction operands instead — the only evidence there is."""
    init_c, init_h = _defines("src/init.c"), _defines("include/init.h")
    assert _immediate(0x1008b, 1) == init_c["TOS_REZ_MONO"], "cmpi.b #$2,d0 @ 0x10088"
    assert _immediate(0x10096, 4) == init_h["A_fname_mono_err"], "move.l #MONO.ERR,-(a7) @ 0x10094"
    assert _immediate(0x100ae, 4) == init_h["A_load_buffer"], "Fread's buffer @ 0x100ac"
    assert _immediate(0x100b4, 4) == init_c["MONO_SPLASH_BYTES"], "Fread's count @ 0x100b2"
    assert _immediate(0x100e2, 4) == init_h["A_load_buffer"], "movea.l #buffer,a0 @ 0x100e0"
    assert _immediate(0x100ee, 2) == init_c["MONO_SPLASH_DST_OFF"], "adda.w #$1f54,a1 @ 0x100ec"
    assert _immediate(0x100f5, 1) == init_c["MONO_SPLASH_LONGS"], "move.b #$a,d0 @ 0x100f2"
    assert _immediate(0x100fe, 2) == init_c["MONO_SCREEN_ROW_BYTES"], "adda.w #$50,a1 @ 0x100fc"
    assert _immediate(0x10102, 4) == init_h["A_load_buffer"] + init_c["MONO_SPLASH_BYTES"], \
        "the copy's exclusive bound, cmpa.l @ 0x10100"
    assert _immediate(0x10133, 1) == init_c["MONO_ACK_KEY"], "cmp.b #$d,d0 @ 0x10130"


def test_the_two_dead_blocks_of_init_system_are_unreachable():
    """0x10206 (load the music off raw floppy, else halt) and 0x10226 (open JOUST.MUR) are branched
    OVER by the Gamex release, which is why neither is reconstructed. Pinned on the two `bra.s`
    displacements, so a rebuilt names.txt or a different dump cannot quietly reintroduce them."""
    for branch, over in ((0x10204, 0x10224), (0x10224, 0x10264)):
        opcode, displacement = harness.BASE_IMAGE[branch], harness.BASE_IMAGE[branch + 1]
        assert opcode == 0x60, f"{branch:#x} is not a bra.s"
        assert branch + 2 + displacement == over, f"{branch:#x} no longer jumps to {over:#x}"


# ================================================================== _start @ 0x10000

def test_start_calls_init_system_then_init_game():
    """Diffed at the third `jsr`. WHAT THIS PROVES: _start does nothing of its own before those two
    calls and makes them in that order, on the state init_system itself leaves behind (screen_base
    is XBIOS Physbase', not a poked one). WHAT IT DOES NOT: anything about title_screen, init_video
    or the per-frame loop — the checkpoint is placed before the first of them."""
    pokes = _system_pokes()
    diffs, _ = differential(ENTRY_START, {"_pokes": pokes}, _start,
                            stop_pc=CHECKPOINT_START_AT_TITLE, poison=True)
    assert not diffs, report(diffs)

    image = _oracle_final(pokes, ENTRY_START, stop_pc=CHECKPOINT_START_AT_TITLE)
    assert struct.unpack_from(">I", image, A_SCREEN_BASE)[0] == OS_SCREEN_BASE, "init_system ran"
    assert struct.unpack_from(">I", image, A_PLAYFIELD_BOTTOM)[0] == OS_SCREEN_BASE + SCREEN_BYTES, \
        "init_game ran, and after init_system: it relocated against Physbase' answer"


def test_start_never_returns():
    """...and the checkpoint above is a checkpoint, not a fall-through: the per-frame loop is
    endless, so without one the run cannot finish. The cap is large enough that a run which DID
    return would have got there — title_screen alone copies a whole framebuffer."""
    _never_returns(_system_pokes(), ENTRY_START)


def test_title_screen_is_blocked_on_two_unported_functions():
    """WHY THE CHECKPOINT SITS WHERE IT DOES. title_screen's first instruction calls
    xbios_setpalette @ 0x10c46, and it calls cycle_palette @ 0x10c56 before it reads a key; the
    second writes memory, so no reconstruction of title_screen can be diffed past it. Pinned on the
    two `bsr` targets so the claim tracks the binary rather than this comment."""
    for site, callee in ((0x10aae, ENTRY_XBIOS_SETPALETTE), (0x10b22, ENTRY_CYCLE_PALETTE)):
        opcode = struct.unpack_from(">H", harness.BASE_IMAGE, site)[0]
        displacement = struct.unpack_from(">h", harness.BASE_IMAGE, site + 2)[0]
        assert opcode == 0x6100, f"{site:#x} is not a bsr.w"
        assert site + 2 + displacement == callee
    assert harness.NAME_MAP.get(ENTRY_CYCLE_PALETTE) == "cycle_palette"
    assert harness.NAME_MAP.get(ENTRY_XBIOS_SETPALETTE) == "xbios_setpalette"


# ================================================================== mirror pins
#
# This module restates addresses that belong to ../../names.txt and constants that belong to the C.
# Python can import neither, so CLAUDE.md's rule applies: pin every copy equal to its source.

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_START, "_start"), (ENTRY_INIT_SYSTEM, "init_system"),
                       (ENTRY_INIT_VIDEO, "init_video"), (ENTRY_INIT_GAME, "init_game"),
                       (ENTRY_TITLE_SCREEN, "title_screen")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_global_addresses_match_the_c():
    init_h = _defines("include/init.h")
    for c_name, mirrored in (("A_tos_conterm", TOS_CONTERM),
                             ("A_ikbd_mouse_handler", A_IKBD_MOUSE_HANDLER),
                             ("A_ikbd_joy_handler", A_IKBD_JOY_HANDLER),
                             ("A_ikbd_cmd_joymode", A_IKBD_CMD_JOYMODE),
                             ("A_fname_mono_err", A_FNAME_MONO_ERR),
                             ("A_load_buffer", A_LOAD_BUFFER),
                             ("A_game_palette", A_GAME_PALETTE),
                             ("A_init_players_template", A_INIT_PLAYERS_TEMPLATE),
                             ("A_init_globals_template", A_INIT_GLOBALS_TEMPLATE),
                             ("A_init_globals_template_END", A_INIT_GLOBALS_TEMPLATE_END),
                             ("KBDVBASE_MOUSEVEC", KBDVBASE_MOUSEVEC),
                             ("KBDVBASE_JOYVEC", KBDVBASE_JOYVEC),
                             ("HISCORE_FILE_BYTES", HISCORE_FILE_BYTES),
                             ("SCREEN_BYTES", SCREEN_BYTES)):
        assert init_h[c_name] == mirrored, f"{c_name} differs from this module's mirror"


def test_hud_bar_constants_match_the_c():
    init_c = _defines("src/init.c")
    assert init_c["HUD_BAR_OFF"] == HUD_BAR_OFF
    assert init_c["HUD_BAR_COLUMN"] == HUD_BAR_COLUMN
    assert init_c["HUD_BAR_PASSES"] == HUD_BAR_PASSES
    assert init_c["HUD_BAR_PLANES01"] == HUD_BAR_PLANES01
    assert init_c["HUD_BAR_PLANES23"] == HUD_BAR_PLANES23, \
        "moveq #$ff SIGN-EXTENDS: the second longword is all ones, not the byte it reads as"
    assert _defines("include/joust.h")["SCREEN_ROW_BYTES"] == SCREEN_ROW_BYTES


def test_startup_constants_match_the_c():
    init_c = _defines("src/init.c")
    assert init_c["PALETTE_PENS"] == PALETTE_PENS
    assert init_c["TOS_SETCOLOR_QUERY"] == SETCOLOR_QUERY
    assert init_c["HISCORE_LOADED_MARK"] == HISCORE_LOADED_MARK
