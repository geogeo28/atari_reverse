"""Differential tests for Joust's startup chain (src/init.c).

Covered here: init_system @ 0x10080, init_video @ 0x104b2, init_game @ 0x105f0, _start @ 0x10000 as
far as its third call, and title_screen's two palette helpers xbios_setpalette @ 0x10c46 and
cycle_palette @ 0x10c56. title_screen @ 0x10aae itself is NOT reconstructed; the reason is measured
by test_title_screen_no_key_path_stops_in_the_ikbd_wait.

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
from test_collide import _wrote         # ...and the shared "what did the ORACLE actually store?"
from test_constants import _defines     # the shared `#define` scraper; see the pins at the end

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_START = 0x10000
ENTRY_INIT_SYSTEM = 0x10080
ENTRY_INIT_VIDEO = 0x104b2
ENTRY_INIT_GAME = 0x105f0
ENTRY_TITLE_SCREEN = 0x10aae
ENTRY_POLL_QUIT_KEY = 0x11c24      # verified in test_input.py; title_screen jumps into its MIDDLE

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

# ---- title_screen's two palette helpers, the last of its callees to be ported (../STATUS.md) ----
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
A_IKBD_PACKET = 0x10e06            # input.h: what title_screen's no-key path clears and waits on
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
# g_xbios_setpalette RETURNS the table it hands the trap: the palette write is off-image, so that
# pointer is the only thing about it a test can compare (see src/init.c).
for _glue, _ret in (("g_start", None), ("g_init_system", None), ("g_init_video", None),
                    ("g_init_game", None), ("g_cycle_palette", None),
                    ("g_xbios_setpalette", ctypes.c_uint32)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P]
    _fn.restype = _ret


def _system(lib, buf):
    return lib.g_init_system(buf)


def _video(lib, buf):
    return lib.g_init_video(buf)


def _game(lib, buf):
    return lib.g_init_game(buf)


def _start(lib, buf):
    return lib.g_start(buf)


def _setpalette(lib, buf):
    return lib.g_xbios_setpalette(buf)


def _cycle(lib, buf):
    return lib.g_cycle_palette(buf)


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


def test_the_palette_routines_below_are_title_screens_own():
    """WHY THE CHECKPOINT SITS WHERE IT DOES, and what the next section covers. title_screen's first
    instruction calls xbios_setpalette @ 0x10c46, and it calls cycle_palette @ 0x10c56 before it
    reads a key. Both are reconstructed now — at their OWN entries, below — but title_screen is not,
    so the checkpoint still stops short of it (see
    test_title_screen_no_key_path_stops_in_the_ikbd_wait). Pinned on the two `bsr` targets so the
    claim tracks the binary rather than this comment.

    These were the last two of its SIX `bsr` callees to be ported; the other four — fill_screen
    @ 0x102e2, draw_string @ 0x10700 (three sites), snd_poll_done @ 0x10a8a and play_sound
    @ 0x10a56 — were already verified in their own layers. A SEVENTH transfer is not a call at all
    and is why "all its callees are ported" would still not mean "portable": the Ctrl-C key is a
    `beq.w` at 0x10bea into 0x11c56, the MIDDLE of poll_quit_key, which ends in Pterm and never
    comes back. See test_title_screen_ctrl_c_jumps_into_poll_quit_key.
    """
    for site, callee in ((0x10aae, ENTRY_XBIOS_SETPALETTE), (0x10b22, ENTRY_CYCLE_PALETTE)):
        opcode = struct.unpack_from(">H", harness.BASE_IMAGE, site)[0]
        displacement = struct.unpack_from(">h", harness.BASE_IMAGE, site + 2)[0]
        assert opcode == 0x6100, f"{site:#x} is not a bsr.w"
        assert site + 2 + displacement == callee
    assert harness.NAME_MAP.get(ENTRY_CYCLE_PALETTE) == "cycle_palette"
    assert harness.NAME_MAP.get(ENTRY_XBIOS_SETPALETTE) == "xbios_setpalette"


TITLE_IKBD_WAIT = 0x10bb8   # `tst.l ikbd_packet / beq.s *-6` — title_screen's no-key spin


def test_title_screen_no_key_path_stops_in_the_ikbd_wait():
    """Porting the two palette helpers did NOT unblock title_screen's no-key path, and this says
    WHERE it stops rather than only that it stops. Two halves, and the pair is the point:

      * a checkpoint run REACHES the wait head, so the 400-pass Bconstat poll ahead of it really
        does fall through to `clr.l ikbd_packet` + Ikbdws + the spin;
      * and an uncapped run never reaches `rts`, because the reply that would end that spin arrives
        by an IKBD INTERRUPT the oracle never runs (TRAP_MODEL.md's IKBD limit — read_joysticks'
        wall). Without the first half, a hang anywhere earlier would pass just as happily.

    Says nothing about the keyed branches, and they do not agree with each other: '1' and '2' reach
    the `rts` at 0x10c44 (ordinary unported work, one console keystroke per run), while Ctrl-C leaves
    title_screen altogether — see test_title_screen_ctrl_c_jumps_into_poll_quit_key.
    """
    pokes = {A_SCREEN_BASE: struct.pack(">I", SCREEN),
             # A sentinel in ikbd_packet, so "it is 0 at the wait" means the routine CLEARED it
             # rather than found it clear.
             A_IKBD_PACKET: struct.pack(">I", UNWRITTEN_L)}
    # emu.run RAISES "did not reach checkpoint" when the stop_pc is not hit, so returning at all is
    # the first half of the proof; the packet read is what says the clr.l ran on the way.
    image, _, _ = emu.run(harness.make_image(pokes), ENTRY_TITLE_SCREEN,
                          stop_pc=TITLE_IKBD_WAIT, max_insns=SPIN_CAP)
    assert struct.unpack_from(">I", image, A_IKBD_PACKET)[0] == 0, "ikbd_packet was not cleared"
    _never_returns(pokes, ENTRY_TITLE_SCREEN)


TITLE_CTRL_C_TEST = 0x10be6    # `cmp.b #$3,d0` — the quit key, tested before '1' and '2'
TITLE_CTRL_C_BRANCH = 0x10bea  # ...and the `beq.w` that leaves the routine
POLL_QUIT_KEY_QUIT_TAIL = 0x11c56   # inside poll_quit_key @ 0x11c24 (114 bytes), NOT its entry
CTRL_C_KEY = 3


def test_title_screen_ctrl_c_jumps_into_poll_quit_key():
    """The transfer that makes title_screen harder to port than its call graph suggests, and the
    reason "all six callees are ported" is not the same as "portable".

    Ctrl-C is not handled in title_screen at all: it is a `beq.w` into 0x11c56, the MIDDLE of
    poll_quit_key — past that routine's own entry and its Bconstat/Bconin, straight into the quit
    tail that silences the sound, writes HIGH.SCO and ends in Pterm. So it is neither a call nor a
    branch that returns: a reconstruction of title_screen would need a stop_pc checkpoint plus a
    never-returns pairing there, the way _start's third `jsr` is handled, and cannot simply call
    poll_quit_key. Pinned on the encoding so the claim tracks the binary.
    """
    assert _immediate(TITLE_CTRL_C_TEST, 2) == 0xb03c, f"{TITLE_CTRL_C_TEST:#x} is not `cmp.b #imm,d0`"
    assert _immediate(TITLE_CTRL_C_TEST + 2, 2) == CTRL_C_KEY
    assert _immediate(TITLE_CTRL_C_BRANCH, 2) == 0x6700, f"{TITLE_CTRL_C_BRANCH:#x} is not a beq.w"
    displacement = struct.unpack_from(">h", harness.BASE_IMAGE, TITLE_CTRL_C_BRANCH + 2)[0]
    assert TITLE_CTRL_C_BRANCH + 2 + displacement == POLL_QUIT_KEY_QUIT_TAIL
    assert harness.NAME_MAP.get(ENTRY_POLL_QUIT_KEY) == "poll_quit_key"
    assert ENTRY_POLL_QUIT_KEY < POLL_QUIT_KEY_QUIT_TAIL, \
        "the target must be INSIDE poll_quit_key, not its entry — that is the whole point"


# ============================== the title-screen palette @ 0x10c46 and 0x10c56

# The 16 words xbios_setpalette hands XBIOS Setpalette. The table's END is players_alive, which is
# what test_title_palette_is_sixteen_pens turns into a check rather than a comment.
A_TITLE_PALETTE = 0x10cd2
TITLE_PALETTE_PENS = 0x10
TITLE_PALETTE_HUE_PEN = 4                 # the one pen cycle_palette animates
A_TITLE_HUE = A_TITLE_PALETTE + 2 * TITLE_PALETTE_HUE_PEN
A_PALETTE_CYCLE_CTR = 0x10d52

# The counter's three component-select bits, what the counter is REPLACED by when they come up zero,
# and where each component sits in the palette word (all mirrors of src/init.c).
PALETTE_CYCLE_BLUE, PALETTE_CYCLE_GREEN, PALETTE_CYCLE_RED = 0x100, 0x200, 0x400
PALETTE_CYCLE_SELECT_MASK = 0x700
PALETTE_CYCLE_FIRST = 0x100
PALETTE_GREEN_SHIFT, PALETTE_RED_SHIFT = 4, 8
COUNTER_LOW_BYTE = 0xff    # the counter's low byte: the divider below the selector bits

# The trap's return address: reaching it means Setpalette has been serviced and its pushes are still
# at A7. `xbios_setpalette` is 16 bytes of nothing else — push, push, trap, unwind, rts.
AFTER_TITLE_SETPALETTE = 0x10c52


def test_xbios_setpalette_hands_the_title_palette():
    """The palette write is off-image (the kit models Setpalette as a no-op), so this routine has NO
    image effect whatever and the argument read-back is the entire verification — the same footing as
    init_video's Setpalette and flash_hiscore_color's Setcolor.

    Three things at once: the original really traps to Setpalette, it is handed title_palette as a
    RELOCATED longword (0xcd2 in the file, 0x10cd2 loaded), and the candidate returns that same
    pointer instead of some other table's. The `assert not diffs` below is STRUCTURALLY VACUOUS —
    the original's only writes are its two pushes, which sit inside the stack guard the diff drops,
    so no reconstruction can fail it. It stays because `differential` is also what returns `ret` and
    what vets a refused os_* call; the memory claim is made by the next test, not by this line.
    """
    diffs, info = differential(ENTRY_XBIOS_SETPALETTE, {"_pokes": {}}, _setpalette)
    assert not diffs, report(diffs)

    words = _trap_args({}, ENTRY_XBIOS_SETPALETTE, AFTER_TITLE_SETPALETTE, 3)
    assert words[2] == XBIOS_SETPALETTE, f"the original trapped to XBIOS fn {words[2]:#x}"
    assert _pushed_long(words, 0) == A_TITLE_PALETTE, "Setpalette was handed the wrong table"
    assert info["ret"] == _pushed_long(words, 0), (
        f"candidate returned {info['ret']:#x}, the original passed Setpalette "
        f"{_pushed_long(words, 0):#x} — the palette write itself is off-image, so nothing else can "
        f"catch this")


def test_xbios_setpalette_writes_no_image_byte():
    """...and this is the premise that lets the read-back above stand alone: the ORIGINAL writes no
    image byte, so there is nothing for a diff to compare and nothing for poison to poison. It is a
    fact about the shipped binary, measured rather than asserted in prose. The reconstruction is
    still held to it by `differential`'s image compare — do not read this test as that guard."""
    _, writes, _ = emu.run(harness.make_image(None), ENTRY_XBIOS_SETPALETTE)
    program_writes = sorted(addr for addr in writes if addr < emu.STACK_GUARD_LO)
    assert not program_writes, f"it wrote {len(program_writes)} byte(s), e.g. {program_writes[0]:#x}"


def test_title_palette_is_sixteen_pens():
    """The table xbios_setpalette hands over runs from title_palette up to players_alive — 16 words,
    which is the ST's whole hardware palette. Nothing reads the bound, so this pins the ADDRESSES
    against each other rather than an instruction."""
    assert A_TITLE_PALETTE + 2 * TITLE_PALETTE_PENS == A_PLAYERS_ALIVE
    assert TITLE_PALETTE_PENS == PALETTE_PENS, "the same 16 pens init_system reads back"


def _cycle_pokes(counter, colour, seed=0):
    """The WHOLE palette table under noise, plus the counter and a sentinel past it.

    The whole table rather than the animated pen alone: a step that wrote the neighbouring pen would
    otherwise land on the base image's own palette word, where it might pass unnoticed. The sentinel
    past the counter is what pins `addq.w` (and the reset store) to a WORD — a longword either way
    would carry into it.
    """
    table = bytearray(_noise(seed, 2 * TITLE_PALETTE_PENS))
    struct.pack_into(">H", table, 2 * TITLE_PALETTE_HUE_PEN, colour)
    return {A_TITLE_PALETTE: bytes(table),
            A_PALETTE_CYCLE_CTR: struct.pack(">H", counter),
            A_PALETTE_CYCLE_CTR + 2: bytes([UNWRITTEN_B, UNWRITTEN_B])}


def _cycle_case(counter, colour, seed=0, poison=True):
    """One differential step, returning the oracle's info so a caller can name what it expects.

    WHAT THE TWO HALVES PROVE, since they are not the same thing. `differential` (image diff, plus
    poison) is what holds the RECONSTRUCTION to the original. The `_wrote` reads below are on the
    ORACLE's write set, so they state what the ORIGINAL does — which is what stops a battery passing
    vacuously with both sides writing nothing, and is the only way to tell a written-but-identical
    word from an untouched one. They do not constrain the candidate: a reconstruction that wrote the
    pen back unchanged on the early-return path would still be image-equivalent, and green.
    """
    pokes = _cycle_pokes(counter, colour, seed)
    diffs, info = differential(ENTRY_CYCLE_PALETTE, {"_pokes": pokes}, _cycle, poison=poison)
    assert not diffs, f"counter={counter:#x} colour={colour:#x}\n{report(diffs)}"
    return info


def _cycle_step(counter, colour, expected_colour, expected_counter, seed=0, poison=True):
    """...and assert both of them. `expected_colour` None means the ORIGINAL wrote no pen at all."""
    info = _cycle_case(counter, colour, seed=seed, poison=poison)
    where = f"counter={counter:#x} colour={colour:#x}"
    assert _wrote(info, A_TITLE_HUE, 2) == expected_colour, f"{where}: wrong pen value"
    assert _wrote(info, A_PALETTE_CYCLE_CTR, 2) == expected_counter, f"{where}: wrong counter"


# (counter before the step, the colour word written, the counter written). The staged pen holds
# blue = 3 throughout, so the expected colour says exactly which components the selector lit.
_SELECTOR_STEPS = (
    (0x0000, 0x003, 0x0100),   # counter 1: no select bit at all -> RESET, and blue from there
    (0x00ff, 0x003, 0x0100),   # ...then every selector in turn, from the counter just below it
    (0x01ff, 0x030, 0x0200),
    (0x02ff, 0x033, 0x0300),
    (0x03ff, 0x300, 0x0400),
    (0x04ff, 0x303, 0x0500),
    (0x05ff, 0x330, 0x0600),
    (0x06ff, 0x333, 0x0700),
    (0x07ff, 0x003, 0x0100),   # past the top selector, the counter is REPLACED rather than masked
)


@pytest.mark.parametrize("counter,expected_colour,expected_counter", _SELECTOR_STEPS)
def test_cycle_palette_selector_places_the_hue(counter, expected_colour, expected_counter):
    """All eight values of the three select bits, each stated as the colour word it produces rather
    than recomputed — so the shifts (blue none, green 4, red 8) are pinned by value.

    The first and last rows are the reset: with bits 8-10 zero the routine does not merely treat the
    selection as "blue", it stores PALETTE_CYCLE_FIRST over the whole counter word.
    """
    _cycle_step(counter, 0x003, expected_colour, expected_counter)


# (the staged pen, the hue it yields once every selector bit is set). All three components are lit
# by counter 0x6ff -> 0x700, so the expected word repeats the hue in all three nibbles.
# Only the rows a single component cannot state: one component at a time is swept exhaustively by
# test_cycle_palette_moves_every_hue_level below.
_HUE_SOURCES = (
    (0x123, 0x333),   # all three lit: BLUE wins
    (0x120, 0x222),   # blue empty: green wins
    (0x100, 0x111),   # blue and green empty: red wins
    (0xf001, 0x111),  # bits 12-15 are not a component and are DROPPED by the rebuild
    (0xffff, 0xfff),
)


@pytest.mark.parametrize("colour,expected", _HUE_SOURCES)
def test_cycle_palette_takes_the_first_non_zero_component(colour, expected):
    """`move.w dN,d3 / bne` three times over, in blue, green, red order — the priority, and the fact
    that a rotation reads ONE component and writes up to three."""
    _cycle_step(0x06ff, colour, expected, PALETTE_CYCLE_SELECT_MASK)


@pytest.mark.parametrize("level", range(1, 0x10))
def test_cycle_palette_moves_every_hue_level(level):
    """Every level a 4-bit component can hold, out of each of the three positions and into all
    three. Exhaustive on the level, which is what pins the masks as nibbles: a mask one bit too wide
    would take a neighbour's bit into the hue at some level here.

    Level 0 is not a level but the early return, and is covered — poisoned — by
    test_cycle_palette_leaves_a_colourless_pen_alone.
    """
    for source_shift in (0, PALETTE_GREEN_SHIFT, PALETTE_RED_SHIFT):
        _cycle_step(0x06ff, level << source_shift, (level << 8) | (level << 4) | level,
                    PALETTE_CYCLE_SELECT_MASK, seed=level, poison=False)


@pytest.mark.parametrize("colour", (0x0000, 0xf000, 0x8000, 0x1000))
def test_cycle_palette_leaves_a_colourless_pen_alone(colour):
    """A pen with nothing in its low 12 bits has no hue to move, and the routine returns without
    touching it — so its high nibble SURVIVES, where any rotation would have dropped it. The counter
    has already been bumped by then, which is the write that keeps the case from being a no-op."""
    _cycle_step(0x06ff, colour, None, PALETTE_CYCLE_SELECT_MASK)


# (counter before the step, counter after it, the colour it lands on). Every wrap the word can take.
_COUNTER_WRAPS = (
    (0xffff, PALETTE_CYCLE_FIRST, 0x003),   # WORD wrap to 0: no select bits, so the reset fires
    (0x7fff, PALETTE_CYCLE_FIRST, 0x003),   # 0x8000 — bit 15 is not a selector either
    (0xf7ff, PALETTE_CYCLE_FIRST, 0x003),   # 0xf800: the reset REPLACES the word, high bits and all
    (0x0800, PALETTE_CYCLE_FIRST, 0x003),   # 0x0801 — nor is bit 11
    (0x00fe, PALETTE_CYCLE_FIRST, 0x003),   # 0x00ff: below every selector
    (0x08ff, 0x0900, 0x003),                # ...but WITH a selector the high bits survive the step
    (0xf6ff, 0xf700, 0x333),
)


@pytest.mark.parametrize("counter,expected_counter,expected_colour", _COUNTER_WRAPS)
def test_cycle_palette_counter_wraps_within_the_word(counter, expected_counter, expected_colour):
    """`addq.w #1` is WORD wide (the sentinel poked past the counter is what says so), and the reset
    STORES PALETTE_CYCLE_FIRST rather than OR-ing it in — 0xf800 becomes 0x0100, not 0xf900."""
    _cycle_step(counter, 0x003, expected_colour, expected_counter)


def _cycle_fuzz_cases():
    rng = random.Random(0x10c56)          # seeded ONCE — every chunk replays this stream
    for index in range(400):
        # Half the counters drawn from the whole word, and half with the low byte SATURATED so the
        # step carries into the selector — leaving the selector itself random, which is what makes
        # every carry (including 0x700 -> reset) reachable. Masking the selector off instead would
        # pin all 200 of those cases to one selector and hit the reset never.
        counter = rng.randrange(0x10000)
        if index % 2:
            counter |= COUNTER_LOW_BYTE
        yield index, counter, rng.randrange(0x10000)


def test_cycle_palette_fuzz_carries_into_every_selector():
    """What the low-byte saturation above is FOR, asserted instead of assumed.

    The property is NOT "all eight selectors occur" — 400 uniform draws give that on their own, so
    an assertion phrased that way passes with the saturation deleted and guards nothing (measured).
    What saturation buys is the CARRY: a step from a counter whose low byte is already full is the
    only way the selector changes at all, and only ~1 in 256 uniform counters lands there. So this
    asserts the eight selectors reached BY A CARRYING STEP, which collapses to almost nothing the
    moment `|= COUNTER_LOW_BYTE` goes away.

    Checked over the WHOLE stream rather than inside a shard, since each shard sees only half of it,
    and it needs no oracle run: the generator is seeded once and is pure.
    """
    carried = {(counter + 1) & PALETTE_CYCLE_SELECT_MASK
               for _, counter, _ in _cycle_fuzz_cases()
               if counter & COUNTER_LOW_BYTE == COUNTER_LOW_BYTE}
    expected = {bits << 8 for bits in range(8)}
    assert carried == expected, \
        f"no carrying step reaches selector(s) {sorted(expected - carried)} — is the low-byte " \
        f"saturation in _cycle_fuzz_cases still there?"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_cycle_palette_fuzz(chunk):
    """Random counters x random pen values x a fresh noise table per case. Shares this module's
    FUZZ_CHUNKS rather than naming its own: the whole battery is well under a second, so the sharding
    is for the recipe's sake, not the critical path."""
    ran = 0
    for index, counter, colour in _cycle_fuzz_cases():
        if index % FUZZ_CHUNKS != chunk:
            continue
        _cycle_case(counter, colour, seed=index, poison=False)
        ran += 1
    assert ran, "this shard ran no cases"


def test_cycle_palette_attribution():
    """Poison over the source components the batteries above do NOT reach.

    Poisoning is MEASURED SAFE for this routine — its two outputs do steer the next step, but the
    poisoned image is run through BOTH cores, so an inverted counter is simply a different and
    equally valid case, not a divergence — which is why `_cycle_case` defaults to it and the three
    hand-written batteries above carry it on every row. Those rows all stage a BLUE source, though,
    and the exhaustive green/red sweep runs unpoisoned for cost; these four close that gap.
    """
    for counter, colour in ((0x03ff, 0x0f0),   # green source, into red alone
                            (0x05ff, 0xf00),   # red source, into blue+red
                            (0xffff, 0x0a0),   # green source through the counter's word wrap
                            (0x0000, 0x000)):  # ...and the early return, through the reset
        _cycle_case(counter, colour, poison=True)


# ================================================================== mirror pins
#
# This module restates addresses that belong to ../../names.txt and constants that belong to the C.
# Python can import neither, so CLAUDE.md's rule applies: pin every copy equal to its source.

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_START, "_start"), (ENTRY_INIT_SYSTEM, "init_system"),
                       (ENTRY_INIT_VIDEO, "init_video"), (ENTRY_INIT_GAME, "init_game"),
                       (ENTRY_TITLE_SCREEN, "title_screen"),
                       (ENTRY_XBIOS_SETPALETTE, "xbios_setpalette"),
                       (ENTRY_CYCLE_PALETTE, "cycle_palette")):
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
                             ("A_title_palette", A_TITLE_PALETTE),
                             ("A_palette_cycle_ctr", A_PALETTE_CYCLE_CTR),
                             ("A_init_players_template", A_INIT_PLAYERS_TEMPLATE),
                             ("A_init_globals_template", A_INIT_GLOBALS_TEMPLATE),
                             ("A_init_globals_template_END", A_INIT_GLOBALS_TEMPLATE_END),
                             ("KBDVBASE_MOUSEVEC", KBDVBASE_MOUSEVEC),
                             ("KBDVBASE_JOYVEC", KBDVBASE_JOYVEC),
                             ("HISCORE_FILE_BYTES", HISCORE_FILE_BYTES),
                             ("SCREEN_BYTES", SCREEN_BYTES)):
        assert init_h[c_name] == mirrored, f"{c_name} differs from this module's mirror"

    # Two globals this module mirrors that belong to OTHER layers' headers. players_alive became
    # load-bearing when test_title_palette_is_sixteen_pens made it the palette table's bound.
    for c_name, header, mirrored in (("A_players_alive", "include/score.h", A_PLAYERS_ALIVE),
                                     ("A_ikbd_packet", "include/input.h", A_IKBD_PACKET)):
        assert _defines(header)[c_name] == mirrored, f"{c_name} differs from this module's mirror"


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


def test_palette_cycle_constants_match_the_c():
    """The whole colour cycle's constants live in src/init.c; the batteries above spell every one of
    them out as a literal expected value, so a drift on either side would weaken them silently
    rather than fail."""
    init_c = _defines("src/init.c")
    assert (init_c["PALETTE_BLUE_MASK"], init_c["PALETTE_GREEN_MASK"], init_c["PALETTE_RED_MASK"]) \
        == (0x00f, 0x0f0, 0xf00)
    assert (init_c["PALETTE_GREEN_SHIFT"], init_c["PALETTE_RED_SHIFT"]) \
        == (PALETTE_GREEN_SHIFT, PALETTE_RED_SHIFT)
    assert (init_c["PALETTE_CYCLE_BLUE"], init_c["PALETTE_CYCLE_GREEN"], init_c["PALETTE_CYCLE_RED"]) \
        == (PALETTE_CYCLE_BLUE, PALETTE_CYCLE_GREEN, PALETTE_CYCLE_RED)
    assert init_c["PALETTE_CYCLE_SELECT_MASK"] == PALETTE_CYCLE_SELECT_MASK
    assert init_c["PALETTE_CYCLE_FIRST"] == PALETTE_CYCLE_FIRST
    assert init_c["TITLE_PALETTE_HUE_PEN"] == TITLE_PALETTE_HUE_PEN


def test_the_palette_cycle_constants_that_must_agree_do():
    """Two couplings the C spells as separate literals — because each is an instruction operand —
    and which nothing else can see: the mirror pins above compare each name to its own copy, never
    to the other name. `test_no_value_has_two_spellings` is blind here too, since neither is an
    address and only the select BITS are in flag-bit form."""
    assert PALETTE_CYCLE_SELECT_MASK == PALETTE_CYCLE_BLUE | PALETTE_CYCLE_GREEN | PALETTE_CYCLE_RED, \
        "`andi.w #$700` must keep exactly the three select bits"
    assert PALETTE_CYCLE_FIRST == PALETTE_CYCLE_BLUE, \
        "the reset restarts the cycle at blue, and cycle_palette's rebuild depends on it"


# 68000 register-shift encoding: 1110 ccc d ss i tt rrr — bits 4-3 are the type, 00 arithmetic,
# 01 logical.
SHIFT_TYPE_MASK, SHIFT_TYPE_LOGICAL = 0x0018, 0x0008


def test_cycle_palettes_component_shifts_are_logical():
    """The one thing about cycle_palette the differential CANNOT see. Both component extractions
    mask BEFORE they shift (`andi.w #$f0` / `andi.w #$f00`), so bit 15 is already clear and `asr.w`
    would answer identically for every input — no staged pen can separate them. The reconstruction's
    unsigned `>>` is therefore pinned against the ORIGINAL'S INSTRUCTION ENCODING instead, the same
    technique test_mono_branch_constants_match_the_original_encoding uses."""
    for addr, what in ((0x10c88, "lsr.w #4,d1 — green"), (0x10c94, "lsr.w #8,d2 — red")):
        opcode = _immediate(addr, 2)
        assert opcode & SHIFT_TYPE_MASK == SHIFT_TYPE_LOGICAL, \
            f"{what} @ {addr:#x} encodes as {opcode:#06x}, which is not a LOGICAL shift"
