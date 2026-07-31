"""Differential tests for Joust's startup chain (src/init.c).

Covered here: init_system @ 0x10080, init_video @ 0x104b2, init_game @ 0x105f0, _start @ 0x10000 as
far as its third call, title_screen @ 0x10aae, and its two palette helpers xbios_setpalette
@ 0x10c46 and cycle_palette @ 0x10c56. Of title_screen's four exits only one is an `rts`; what each
of the others is verified at, and why, is in the section that opens that battery.

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
import functools
import random
import struct
import threading

import ctypes
import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_collide import _wrote         # ...and the shared "what did the ORACLE actually store?"
from test_constants import _defines     # the shared `#define` scraper; see the pins at the end
# title_screen's Ctrl-C branches INTO poll_quit_key's quit tail, so its cases need that tail's own
# staging and checkpoint. Imported rather than restated: a second copy of the filesystem and system
# state would drift from the battery that verified the tail.
import test_input

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_START = 0x10000
ENTRY_INIT_SYSTEM = 0x10080
ENTRY_INIT_VIDEO = 0x104b2
ENTRY_INIT_GAME = 0x105f0
ENTRY_TITLE_SCREEN = 0x10aae
ENTRY_POLL_QUIT_KEY = 0x11c24      # verified in test_input.py; title_screen jumps into its MIDDLE

# ---- checkpoint PCs (harness `stop_pc`) ----
# _start's third `jsr`. Everything before it is init_system and init_game. title_screen after it IS
# reconstructed now; what keeps the checkpoint here is that entering it needs a glue refusal of its
# own (see the module comment in ../src/init.c and _start's row in ../STATUS.md).
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
A_DRAW_X = 0x10dec                 # ...its pen, then its GEMDOS file handle, then title_screen's
                                   # console-poll counter
A_DRAW_Y = 0x10dee                 # addrs.h — draw_x's neighbour, which nothing here may touch
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
A_IKBD_CMD_JOYREAD = 0x1145b       # input.h: the $16 title_screen and read_joysticks send
A_SND_LIST_SILENCE = 0x1150f       # sound.h: the Dosound list that silences the chip. Shares its
                                   # address with A_INIT_GLOBALS_TEMPLATE_END above — the list sits
                                   # exactly where init_game's template stops
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
UNWRITTEN_B, UNWRITTEN_W, UNWRITTEN_L = 0x5a, 0x5a5a, 0x5a5a5a5a
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
                    ("g_xbios_setpalette", ctypes.c_uint32),
                    ("g_title_screen", ctypes.c_uint32), ("g_title_ikbd_pass", ctypes.c_uint32)):
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


def _title(lib, buf):
    return lib.g_title_screen(buf)


# The glue's own probe is the FIRST layer against title_screen's uncapped IKBD spin; this is the
# second, and the README (../README.md, "A glue may refuse a call the original makes") makes it
# mandatory rather than optional. A candidate that entered the spin would hang this worker for ever
# and print nothing at all under `-n auto` — the one failure a differential cannot report — so every
# candidate-side entry goes through a deadline that turns it into an ordinary red assert. Modelled
# on test_input.py's `_pause_glue`, which carries the full rationale; kept local rather than shared
# because it names its own symbol, and a wrapper taking the symbol as an argument would be the only
# thing either file gained.
TITLE_GLUE_TIMEOUT_S = 5   # absurdly generous for a wait that leaves on its first read


def _title_ikbd(lib, buf):
    returned = []
    call = threading.Thread(target=lambda: returned.append(lib.g_title_ikbd_pass(buf)), daemon=True)
    call.start()
    call.join(TITLE_GLUE_TIMEOUT_S)

    assert returned, (f"g_title_ikbd_pass did not return within {TITLE_GLUE_TIMEOUT_S}s — the "
                      "uncapped IKBD wait was entered and never left")
    return returned[0]


# ------------------------------------------------------------------ shared staging helpers

@functools.lru_cache(maxsize=None)
def _noise(seed, length):
    """A seeded noise block. Memoised, and built in one `randbytes` call rather than per byte,
    because title_screen's two inputs are 32 KiB each and its fuzz would otherwise spend more time
    here than in the differential. Cached blocks are never mutated — `make_image` copies them."""
    return random.Random(seed).randbytes(length)


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
    """WHY _start's CHECKPOINT SITS WHERE IT DOES. title_screen's first instruction calls
    xbios_setpalette @ 0x10c46, and it calls cycle_palette @ 0x10c56 before it reads a key. All
    three are reconstructed now, each verified at its OWN entry; what still keeps _start's
    checkpoint short of the third `jsr` is that title_screen returns only for a key that chooses a
    game, so a forwarding g_start would need a refusal of its own (see ../src/init.c). Pinned on the
    two `bsr` targets so the claim tracks the binary rather than this comment.

    These were the last two of its SIX `bsr` callees to be ported; the other four — fill_screen
    @ 0x102e2, draw_string @ 0x10700 (three sites), snd_poll_done @ 0x10a8a and play_sound
    @ 0x10a56 — were already verified in their own layers. A SEVENTH transfer is not a call at all,
    and is what "all its callees are ported" would still not have covered: the Ctrl-C key is a
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


# ================================================================== title_screen @ 0x10aae
#
# The attract screen, and the one routine of the startup chain with FOUR exits, only one of which is
# an `rts`. What can be verified, and how, follows straight from the kit's console and IKBD models:
#
#   * '1' and '2' run to the `rts` at 0x10c44 and are diffed there, one console keystroke per run
#     (the model delivers exactly one — TRAP_MODEL.md Phase 1).
#   * CTRL-C leaves the routine altogether — a `beq.w` into poll_quit_key's quit tail, which ends in
#     GEMDOS Pterm — so it is diffed at that tail's own checkpoint, PAIRED with a never-returns
#     proof over the SAME staging.
#   * EVERYTHING ELSE (no key, or a key it does not act on) falls through the console poll into the
#     IKBD wait at 0x10bb8, which never ends on either side: the reply arrives on an interrupt the
#     oracle never runs, and the routine clears ikbd_packet on the way in so no poke survives. Those
#     runs are diffed at that wait, likewise paired with a never-returns proof.
#   * THE JOYSTICK START past that wait is reachable only by ROTATING the entry: the oracle is
#     started AT 0x10bb8 with a reply already staged, exactly as hiscore_joystick_input is.

TITLE_IKBD_WAIT_PC = 0x10bb8     # `tst.l ikbd_packet / beq.s *-6`, in TWO roles: the checkpoint the
                                 # attract pass stops at, and the entry the joystick pass is rotated
                                 # to (nothing else can get an oracle run past the wait)
TITLE_ATTRACT_HEAD = 0x10b22     # the attract loop's head: where a reply with no fire branches back
TITLE_AFTER_COPY = 0x10ad0       # the first `move.b #imm,text_color`: the picture is on the screen
                                 # and no text has been drawn over it yet
AFTER_TITLE_IKBDWS = 0x10bb6     # the joystick interrogate's stack cleanup

# title_screen's result codes (mirrors of include/init.h) and the glue-only refusal (src/init.c).
TITLE_STARTED, TITLE_QUIT, TITLE_IKBD_WAIT, TITLE_ATTRACT, TITLE_PASS_REFUSED = 0, 1, 2, 3, 4

TITLE_COLOR_PROMPT, TITLE_COLOR_HISCORE, TITLE_COLOR_CREDITS = 0xf, 2, 1
STR_TITLE_PROMPT, STR_TITLE_HISCORE, STR_TITLE_CREDITS = 0x183b3, 0x18381, 0x183d5
TITLE_POLL_PASSES = 400
TITLE_STARTING_LIVES = 4
SND_TITLE_TUNE = 0xe
TITLE_KEY_ONE_PLAYER, TITLE_KEY_TWO_PLAYER = 0x31, 0x32
KEY_CTRL_C = 3                     # input.h — poll_quit_key tests the same byte

TITLE_CTRL_C_TEST = 0x10be6        # `cmp.b #$3,d0` — the quit key, tested before '1' and '2'
TITLE_CTRL_C_BRANCH = 0x10bea      # ...and the `beq.w` that leaves the routine
POLL_QUIT_KEY_QUIT_TAIL = 0x11c56  # inside poll_quit_key @ 0x11c24 (114 bytes), NOT its entry

# The six pens the attract loop rotates, in the order the original moves them (../src/init.c).
TITLE_HUE_RING = (10, 9, 8, 3, 6, 4)

A_TEXT_COLOR = 0x10e0f             # draw.h
A_SND_PRIORITY = 0x10d4c           # sound.h
SND_PRIORITY_IDLE = 0x10
PSG_MIXER, PSG_MIXER_ALL_OFF = 7, 0x3f   # src/sound.c: all six tone+noise enables off = silence
A_SOUND_TABLE = 0x11774            # sound.h
OBJ_SCORE_LAST_DIGIT = 0x44        # score.h
OBJ_FLAGS = 0                      # joust.h

# Two staged joystick bytes, clear of the program (ends 0x2b7ae), of SCREEN and of the file table.
IKBD_PACKET_BUF = 0x60000
# ...and the two buffers that pin the wait's WIDTH, imported rather than respelled: the wait is ONE
# shared function (src/input.c), so its probe addresses have one definition, in test_input.py beside
# the constants of the layer that owns it. Each kills a different narrowing; see the comment there.
IKBD_PACKET_BUF_HIGH_ZERO = test_input.IKBD_PACKET_BUF_HIGH_ZERO
IKBD_PACKET_BUF_LSB_ONLY = test_input.IKBD_PACKET_BUF_LSB_ONLY
IKBD_PACKET_BYTES = 2              # input.h: what the glue's bound must leave readable
IKBD_FIRE = 0x80                   # the IKBD joystick byte's bit 7 — read here as its SIGN


# A cycled pen with NOTHING in its low 12 bits: cycle_palette returns early on one and leaves it
# wholly untouched, high nibble included (see its own battery below), so it is a sentinel that
# survives the colour cycle and lets the ring's permutation be read off on its own.
TITLE_HUE_COLOURLESS = 0xf000
TITLE_HUE_RED_3 = 0x0300     # ...and a hue the SHIPPED ring really circulates (red, level 3)


def _title_palette(seed, hue=TITLE_HUE_COLOURLESS):
    """16 DISTINCT pen words, with `hue` at the pen cycle_palette animates.

    The fifteen others carry the seed in their low 12 bits so no two pens are equal — which is what
    makes the ring's permutation readable — while `hue` decides whether the colour cycle does
    anything at all this run.
    """
    pens = [((seed + pen) * 0x111 + pen) & 0x0fff | 0x1000 for pen in range(TITLE_PALETTE_PENS)]
    pens[TITLE_PALETTE_HUE_PEN] = hue
    return b"".join(struct.pack(">H", pen) for pen in pens)


def _title_pokes(seed=1, key=None, console=None, counter=0, priority=None, mixer=None,
                 two_player=UNWRITTEN_B, picture=None, hue=TITLE_HUE_COLOURLESS, screen=SCREEN):
    """Everything title_screen reads, plus a sentinel wherever it must write.

    `key` stages one console keystroke through the model; `console` pokes the console longword RAW,
    which is the only way to build a low WORD real TOS cannot produce (see the width test below) —
    both fields together, so the console is never half-armed. `screen` defaults to SCREEN because
    the picture assertions read that span by name; the one case that moves it is what says the copy
    destination is READ from screen_base rather than being a constant this battery always agrees
    with (a wider sweep over the base belongs to init_game and init_video, which do the arithmetic).
    """
    pokes = {screen: _noise(seed, SCREEN_SPAN),
             A_SCREEN_BASE: struct.pack(">I", screen),
             # The title picture: the PRG's own data segment, which is where JOUST.MUR would have
             # landed. Staged as NOISE so a copy from the wrong address fails as a diff.
             A_LOAD_BUFFER: picture if picture is not None else _noise(seed + 1, SCREEN_BYTES),
             A_TITLE_PALETTE: _title_palette(seed, hue),
             A_PALETTE_CYCLE_CTR: struct.pack(">H", counter),
             A_IKBD_PACKET: struct.pack(">I", UNWRITTEN_L),
             A_PLAYERS_ALIVE: bytes([UNWRITTEN_B]),
             A_TWO_PLAYER_MODE: bytes([two_player]),
             A_DRAW_X: struct.pack(">H", UNWRITTEN_W),
             # draw_x's neighbour: the poll counter is a WORD store, so this must survive it.
             A_DRAW_Y: struct.pack(">H", UNWRITTEN_W),
             A_TEXT_COLOR: bytes([UNWRITTEN_B])}
    for player in (A_OBJECT_TABLE, A_PLAYER2):
        # FOUR bytes, not two. The one-player arm clears these flags with a `clr.w`, and the base
        # image is ALREADY ZERO in the two bytes above them — so a two-byte sentinel cannot tell
        # that word store from a longword one, and a reconstruction using the wrong width passes.
        # The extra two bytes are OBJ_X, which title_screen never touches.
        pokes[player + OBJ_FLAGS] = struct.pack(">I", UNWRITTEN_L)
        pokes[player + OBJ_SCORE_LAST_DIGIT] = bytes([UNWRITTEN_B])
        pokes[player + OBJ_LIVES] = bytes([UNWRITTEN_B])
    if priority is not None:
        pokes[A_SND_PRIORITY] = struct.pack(">H", priority)
    if mixer is not None:
        pokes.update(harness.psg_regs({PSG_MIXER: mixer}))
    if key is not None:
        pokes.update(harness.console_key(key))
    if console is not None:
        pokes[harness.OS_CON_PENDING] = struct.pack(">I", 1)
        pokes[harness.OS_CON_CHAR] = struct.pack(">I", console)
    return pokes


def _title_case(expect, stop_pc=0, poison=False, **staging):
    """One title_screen run: oracle from 0x10aae, candidate through g_title_screen."""
    pokes = _title_pokes(**staging)
    diffs, info = differential(ENTRY_TITLE_SCREEN, {"_pokes": pokes}, _title,
                               stop_pc=stop_pc, poison=poison)
    assert not diffs, f"{staging}\n{report(diffs)}"
    assert info["ret"] == expect, f"title_screen reported {info['ret']}, expected {expect}"
    return pokes, info


# ------------------------------------------------------------------ the two keys that start a game

@pytest.mark.parametrize("key,two_player", ((chr(TITLE_KEY_ONE_PLAYER), False),
                                            (chr(TITLE_KEY_TWO_PLAYER), True)))
def test_title_screen_key_starts_the_chosen_game(key, two_player):
    """The only two inputs that reach the `rts` at 0x10c44, so the only two runs the differential
    can diff whole: the picture, the three text lines, the colour cycle, the palette ring, the sound
    poll and the player records, all in one compare.

    Both arms fall into the SAME tail at 0x10c32, which is why player 1 is armed identically by
    each; only the two-player arm touches player 2's record, and only the one-player arm clears
    player 2's flags WORD.
    """
    _, info = _title_case(TITLE_STARTED, key=key, poison=True)
    writes = info["writes"]

    # Read off the ORACLE'S WRITE SET rather than its final image: "the original stored this" is a
    # stronger claim than "this byte ended up here", and the untouched cases below become "the
    # original never stored there at all", which a final-image read cannot distinguish from a store
    # that happened to write the sentinel back.
    assert _wrote(info, A_PLAYERS_ALIVE) == (2 if two_player else 1)
    assert _wrote(info, A_TWO_PLAYER_MODE) == (1 if two_player else 0)
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SCORE_LAST_DIGIT) == ord("0")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_LIVES) == TITLE_STARTING_LIVES
    if two_player:
        assert _wrote(info, A_PLAYER2 + OBJ_SCORE_LAST_DIGIT) == ord("0")
        assert _wrote(info, A_PLAYER2 + OBJ_LIVES) == TITLE_STARTING_LIVES
        assert A_PLAYER2 + OBJ_FLAGS not in writes, \
            "the two-player arm must NOT clear player 2's flags"
    else:
        assert _wrote(info, A_PLAYER2 + OBJ_FLAGS, 2) == 0
        assert A_PLAYER2 + OBJ_SCORE_LAST_DIGIT not in writes, \
            "the one-player arm must leave player 2's score alone"
        assert A_PLAYER2 + OBJ_LIVES not in writes


def test_title_screen_counts_its_console_polls_in_a_word():
    """The poll counter is `move.w #$190` + `subq.w #1` + `bne`. A key on the FIRST poll leaves it
    at 400 untouched, which is the only run that can show the value at all (every run that spends
    it ends at 0), and draw_y's sentinel one word up is what pins the store's WIDTH.

    The `bne` is a zero test, not a sign test — unobservable from 400, so it is pinned against the
    original's encoding rather than claimed from a case."""
    pokes, _ = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER))
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN)
    assert struct.unpack_from(">H", image, A_DRAW_X)[0] == TITLE_POLL_PASSES
    assert struct.unpack_from(">H", image, A_DRAW_Y)[0] == UNWRITTEN_W, \
        "the poll counter was stored wider than a word"

    assert _immediate(0x10b82, 2) == TITLE_POLL_PASSES, "move.w #$190,draw_x @ 0x10b80"
    assert _immediate(0x10b9a, 2) == 0x5379, "0x10b9a is not `subq.w #1,abs.l`"
    assert _immediate(0x10ba0, 2) == 0x66e6, "0x10ba0 is not the `bne.s` back to the poll head"


# ------------------------------------------------------------------ what it paints

def test_title_screen_paints_the_picture_over_the_fill():
    """Checkpointed one instruction past the copy loop, before any text is drawn over it.

    Three claims in one: the source is load_buffer (staged as noise, so a copy from anywhere else
    diverges), the copy is exactly SCREEN_BYTES long — its `cmpa.l` bound is EXCLUSIVE — and the
    eight bytes fill_screen paints PAST the framebuffer (src/fill.c) survive it.
    """
    pokes = _title_pokes()
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=TITLE_AFTER_COPY)
    picture = pokes[A_LOAD_BUFFER]
    assert image[SCREEN:SCREEN + SCREEN_BYTES] == picture
    assert image[SCREEN + SCREEN_BYTES:SCREEN + SCREEN_BYTES + 8] == bytes(8), \
        "fill_screen's eight extra bytes are not what the copy stops short of"
    assert image[SCREEN + SCREEN_BYTES + 8:SCREEN + SCREEN_SPAN] == \
        pokes[SCREEN][SCREEN_BYTES + 8:], "the run painted past fill_screen's own end"


def test_title_screen_paints_the_placeholder_picture_the_prg_carries():
    """THE ONE CASE THAT RUNS ON THE REAL ARTWORK. Every other case pokes noise over load_buffer,
    which is the stronger input for catching a wrong source address but says nothing about the
    shipped bytes. This says the routine really paints the picture JOUST.PRG carries — which is what
    the Gamex release shows, since its JOUST.MUR loader is branched over (../README.md)."""
    shipped = bytes(harness.BASE_IMAGE[A_LOAD_BUFFER:A_LOAD_BUFFER + SCREEN_BYTES])
    assert len(set(shipped)) > 1, "load_buffer holds a blank framebuffer, not a picture"
    pokes, _ = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER), picture=shipped)
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=TITLE_AFTER_COPY)
    assert image[SCREEN:SCREEN + SCREEN_BYTES] == shipped


SCREEN_SECOND = 0x88000   # a second base, clear of SCREEN (0x70000 + 0x8000) and of the file table


def test_title_screen_paints_where_screen_base_points():
    """The destination is READ from screen_base, not assumed.

    Every other case in this file stages the same base, so a reconstruction that had the address
    baked in would agree with all of them — this is the one that moves it. It also proves the eight
    bytes fill_screen paints past the framebuffer follow the base rather than staying put.
    """
    pokes = _title_pokes(screen=SCREEN_SECOND)
    diffs, info = differential(ENTRY_TITLE_SCREEN, {"_pokes": pokes}, _title,
                               stop_pc=TITLE_IKBD_WAIT_PC)
    assert not diffs, report(diffs)
    assert info["ret"] == TITLE_IKBD_WAIT

    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=TITLE_AFTER_COPY)
    assert image[SCREEN_SECOND:SCREEN_SECOND + SCREEN_BYTES] == pokes[A_LOAD_BUFFER]
    assert image[SCREEN:SCREEN + SCREEN_SPAN] == harness.BASE_IMAGE[SCREEN:SCREEN + SCREEN_SPAN], \
        "the run painted at the base every OTHER case stages"


def test_title_screen_draws_three_lines_each_in_its_own_colour():
    """The three `draw_string` calls and the colour each is preceded by. The PAIRING is held by the
    differential — a swapped colour repaints the glyphs differently — but the colour byte itself is
    overwritten twice, so only the last survives to be read back; the pairing is therefore ALSO
    pinned against the original's own immediates.

    The middle line is not a fixed string: HIGH.SCO's record lies inside it (init.h), which is how
    the title screen shows the saved high score.
    """
    pokes, _ = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER))
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN)
    assert image[A_TEXT_COLOR] == TITLE_COLOR_CREDITS, "the last line's colour is what survives"

    for colour_at, colour, string_at, string in (
            (0x10ad3, TITLE_COLOR_PROMPT, 0x10ada, STR_TITLE_PROMPT),
            (0x10ae9, TITLE_COLOR_HISCORE, 0x10af0, STR_TITLE_HISCORE),
            (0x10aff, TITLE_COLOR_CREDITS, 0x10b06, STR_TITLE_CREDITS)):
        assert _immediate(colour_at, 1) == colour, f"text_color immediate @ {colour_at:#x}"
        assert _immediate(string_at, 4) == string, f"draw_string's argument @ {string_at:#x}"
    assert A_HISCORE_NAME == STR_TITLE_HISCORE + _defines("include/init.h")[
        "STR_TITLE_HISCORE_RECORD_OFF"], "the HIGH SCORE line no longer contains hiscore_name"


def test_title_screen_hands_setpalette_the_title_palette():
    """The palette write is off-image, so a wrong table would be invisible to the diff. Read the
    trap's own pushes back out of the oracle's stack at the FIRST of title_screen's two calls.

    The outermost longword is the `bsr`'s own return address, which is the extra thing this says
    over xbios_setpalette's battery: the call came from title_screen's very first instruction."""
    words = _trap_args(_title_pokes(), ENTRY_TITLE_SCREEN, AFTER_TITLE_SETPALETTE, 5)
    assert _pushed_long(words, 0) == ENTRY_TITLE_SCREEN + 4, "not title_screen's `bsr` at 0x10aae"
    assert _pushed_long(words, 2) == A_TITLE_PALETTE
    assert words[4] == XBIOS_SETPALETTE


def test_title_screen_asks_the_ikbd_for_both_joysticks():
    """XBIOS Ikbdws has no image effect either: the command string's address and its length word
    (count - 1, so one byte) come back off the oracle's stack instead."""
    words = _trap_args(_title_pokes(), ENTRY_TITLE_SCREEN, AFTER_TITLE_IKBDWS, 4)
    assert _pushed_long(words, 0) == A_IKBD_CMD_JOYREAD
    assert words[2] == IKBDWS_ONE_BYTE
    assert words[3] == XBIOS_IKBDWS


# ------------------------------------------------------------------ the palette ring

def _ring_pen(image, pen):
    return struct.unpack_from(">H", image, A_TITLE_PALETTE + 2 * pen)[0]


def test_title_screen_rotates_six_palette_pens_one_place():
    """The ring at 0x10b26..0x10b5e, read off a table of sixteen DISTINCT words.

    Each of the six pens takes its successor's colour and the last takes the first's, so the six
    walk one place round a closed cycle; the other ten must be untouched, which is what says the ring
    is those six pens and no others. The cycled pen is staged colourless (see `_title_palette`) so
    that cycle_palette contributes nothing here — the composition of the two is the next test.

    ONE PASS PER RUN IS ALL THERE IS: the loop is only re-entered through the IKBD wait, which no
    run leaves, so no case can rotate the ring twice.
    """
    pokes, _ = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER))
    before = harness.make_image(pokes)
    after = _oracle_final(pokes, ENTRY_TITLE_SCREEN)

    for index, pen in enumerate(TITLE_HUE_RING):
        source = TITLE_HUE_RING[(index + 1) % len(TITLE_HUE_RING)]
        assert _ring_pen(after, pen) == _ring_pen(before, source), \
            f"pen {pen} did not take pen {source}'s colour"
    for pen in range(TITLE_PALETTE_PENS):
        if pen in TITLE_HUE_RING:
            continue
        assert _ring_pen(after, pen) == _ring_pen(before, pen), f"pen {pen} is not in the ring"


def test_title_screen_rotates_the_hue_the_cycle_has_just_moved():
    """...and the ORDER of the two steps IS held by the differential, unlike most of this
    reconstruction's transcribed orders: cycle_palette rewrites pen 4, which is IN the ring, so the
    value that lands in pen 6 one instruction later is the cycle's OUTPUT and not the pen's old
    colour. Swapping the two statements changes pen 6 and pen 4 both.

    The counter is staged one short of a carry into the selector, so the selector comes up blue and
    a red level 3 — a level the shipped ring really does circulate — is moved into blue.
    """
    pokes, _ = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER),
                           hue=TITLE_HUE_RED_3, counter=PALETTE_CYCLE_FIRST - 1)
    before, after = harness.make_image(pokes), _oracle_final(pokes, ENTRY_TITLE_SCREEN)

    assert _ring_pen(after, 6) == 0x0003, "pen 6 did not take the cycle's freshly moved hue"
    assert _ring_pen(after, TITLE_PALETTE_HUE_PEN) == _ring_pen(before, TITLE_HUE_RING[0])
    assert struct.unpack_from(">H", after, A_PALETTE_CYCLE_CTR)[0] == PALETTE_CYCLE_FIRST


# ------------------------------------------------------------------ the attract tune

def _dosound(info):
    return info["regs"]["dosound"]


def _sound_list(index):
    return struct.unpack_from(">I", harness.BASE_IMAGE, A_SOUND_TABLE + 4 * index)[0]


def test_title_screen_silences_the_chip_behind_the_picture():
    """The Dosound the painting ends with — the same silence list the quit path uses."""
    _, info = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER), priority=0)
    assert _dosound(info) == [A_SND_LIST_SILENCE]


@pytest.mark.parametrize("priority,mixer,plays", (
    (0, PSG_MIXER_ALL_OFF, True),                 # snd_poll_done releases the priority, so it plays
    (SND_PRIORITY_IDLE, 0, True),                 # ...and an ALREADY idle priority plays it too
    (0, PSG_MIXER_ALL_OFF ^ 1, False),            # one enable still on: the chip is busy
    (SND_PRIORITY_IDLE - 1, 0, False)))           # ...as is a priority one short of idle
def test_title_screen_restarts_the_tune_only_while_the_chip_is_idle(priority, mixer, plays):
    """The gate re-reads snd_priority after snd_poll_done rather than looking at what it did, so
    both routes to idle admit the tune and both routes away from it hold it off. Asserted on the
    kit's Dosound ledger, since play_sound's whole effect past snd_priority is off-image."""
    _, info = _title_case(TITLE_STARTED, key=chr(TITLE_KEY_ONE_PLAYER),
                          priority=priority, mixer=mixer)
    expected = [A_SND_LIST_SILENCE] + ([_sound_list(SND_TITLE_TUNE)] if plays else [])
    assert _dosound(info) == expected
    assert _immediate(0x10b6c, 2) == 0x0c79, "0x10b6c is not `cmpi.w #imm,abs.l`"
    assert _immediate(0x10b6e, 2) == SND_PRIORITY_IDLE
    assert _immediate(0x10b78, 2) == SND_TITLE_TUNE, "play_sound's index @ 0x10b76"


# ------------------------------------------------------------------ the paths that never return

def test_title_screen_no_key_path_stops_in_the_ikbd_wait():
    """THE ONE PATH THAT CANNOT BE VERIFIED TO AN `rts`, diffed as far as it goes. Two halves, and
    the pair is the point:

      * the checkpoint run REACHES the wait head, so the 400-pass Bconstat poll ahead of it really
        does fall through to `clr.l ikbd_packet` + Ikbdws + the spin — and the whole run up to there
        is diffed, so everything the attract pass writes is verified even though its exit is not;
      * and an uncapped run never reaches `rts`, because the reply that would end that spin arrives
        by an IKBD INTERRUPT the oracle never runs (TRAP_MODEL.md's IKBD limit — read_joysticks'
        wall). Without the first half, a hang anywhere earlier would pass just as happily.

    ikbd_packet is staged with a sentinel, so "0 at the wait" means the routine CLEARED it rather
    than found it clear; draw_x at 0 is the 400 passes having really been spent.
    """
    pokes, _ = _title_case(TITLE_IKBD_WAIT, stop_pc=TITLE_IKBD_WAIT_PC, poison=True)
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=TITLE_IKBD_WAIT_PC)
    assert struct.unpack_from(">I", image, A_IKBD_PACKET)[0] == 0, "ikbd_packet was not cleared"
    assert struct.unpack_from(">H", image, A_DRAW_X)[0] == 0, "the poll counter was not spent"
    _never_returns(pokes, ENTRY_TITLE_SCREEN)


@pytest.mark.parametrize("key,console", (("X", None), ("\r", None), (None, 0x0131), (None, 0x0132)))
def test_title_screen_ignores_a_key_it_does_not_act_on(key, console):
    """A key that is neither Ctrl-C nor '1' nor '2' is CONSUMED and then ignored: the poll goes
    round again — without spending a pass on it — and the run ends in the IKBD wait like a run with
    no key at all. players_alive and two_player_mode keep their sentinels, which is what says the
    key decided nothing.

    The last two cases are CONSTRUCTED, and say so: 0x0131/0x0132 put '1'/'2' in the low BYTE of the
    console longword and something else in the byte above, which real TOS never does (Bconin returns
    scancode << 16 | ascii). They are the only input that can separate the `cmp.w`s at 0x10bee and
    0x10bf4 from the `cmp.b` at 0x10be6 one instruction earlier — read as bytes, both would start a
    game.
    """
    pokes, _ = _title_case(TITLE_IKBD_WAIT, stop_pc=TITLE_IKBD_WAIT_PC, key=key, console=console)
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=TITLE_IKBD_WAIT_PC)
    assert struct.unpack_from(">I", image, harness.OS_CON_PENDING)[0] == 0, "the key was not read"
    assert image[A_PLAYERS_ALIVE] == UNWRITTEN_B
    assert image[A_TWO_PLAYER_MODE] == UNWRITTEN_B
    _never_returns(pokes, ENTRY_TITLE_SCREEN)


def test_title_screen_ctrl_c_jumps_into_poll_quit_key():
    """WHY Ctrl-C IS NOT A CALL, pinned on the encoding so the claim tracks the binary.

    It is a `beq.w` into 0x11c56, the MIDDLE of poll_quit_key — past that routine's own entry and
    its Bconstat/Bconin, straight into the quit tail that silences the sound, writes HIGH.SCO and
    ends in Pterm. So a reconstruction cannot call poll_quit_key: what it reaches is the shared tail
    src/input.c exports as `quit_to_desktop`, and the exit is reported as TITLE_QUIT (below).
    """
    assert _immediate(TITLE_CTRL_C_TEST, 2) == 0xb03c, f"{TITLE_CTRL_C_TEST:#x} is not `cmp.b #imm,d0`"
    assert _immediate(TITLE_CTRL_C_TEST + 2, 2) == KEY_CTRL_C
    assert _immediate(TITLE_CTRL_C_BRANCH, 2) == 0x6700, f"{TITLE_CTRL_C_BRANCH:#x} is not a beq.w"
    displacement = struct.unpack_from(">h", harness.BASE_IMAGE, TITLE_CTRL_C_BRANCH + 2)[0]
    assert TITLE_CTRL_C_BRANCH + 2 + displacement == POLL_QUIT_KEY_QUIT_TAIL
    assert harness.NAME_MAP.get(ENTRY_POLL_QUIT_KEY) == "poll_quit_key"
    assert ENTRY_POLL_QUIT_KEY < POLL_QUIT_KEY_QUIT_TAIL, \
        "the target must be INSIDE poll_quit_key, not its entry — that is the whole point"


def _ctrl_c_pokes(console=None, **staging):
    """The Ctrl-C staging: title_screen's own inputs plus everything the quit tail reads.

    Built on test_input's `_quit_pokes` so the two batteries stage the same filesystem and system
    state — a second copy would drift from the one that verified that tail. `_quit_pokes` stages the
    plain Ctrl-C keystroke itself; `console` replaces it with a raw longword afterwards.
    """
    pokes = _title_pokes(**staging)
    pokes.update(test_input._quit_pokes())
    if console is not None:
        pokes[harness.OS_CON_CHAR] = struct.pack(">I", console)
    return pokes


def _ctrl_c_case(console=None, **staging):
    """One Ctrl-C run, stopped at poll_quit_key's own pre-Pterm checkpoint — the counterpart of
    `_title_case` for the one key that leaves title_screen altogether. The checkpoint belongs to
    test_input, so naming it in one place is what stops the fuzz below drifting off it."""
    pokes = _ctrl_c_pokes(console=console, **staging)
    diffs, info = differential(ENTRY_TITLE_SCREEN, {"_pokes": pokes}, _title,
                               stop_pc=test_input.CHECKPOINT_BEFORE_PTERM)
    assert not diffs, f"{staging}\n{report(diffs)}"
    assert info["ret"] == TITLE_QUIT
    return pokes, info


@pytest.mark.parametrize("console", (None, 0x0103))
def test_title_screen_ctrl_c_quits_to_the_desktop(console):
    """The Ctrl-C run, diffed at poll_quit_key's own pre-Pterm checkpoint and PAIRED with a proof
    the same staging never reaches an `rts`.

    Everything on both sides of the branch is in the compare: title_screen's picture and palette
    work, then the quit tail's Dosound silence, the HIGH.SCO write-back and the restored system
    state (that tail's own battery is test_input's; this says title_screen really lands in it).

    The second case is CONSTRUCTED — 0x0103 is Ctrl-C in the low byte with a byte above it that real
    TOS never sets — and is the other half of the width test: the `cmp.b` at 0x10be6 acts on it
    where the two `cmp.w`s one instruction later would not.
    """
    pokes, info = _ctrl_c_case(console=console)
    assert _dosound(info) == [A_SND_LIST_SILENCE, A_SND_LIST_SILENCE], \
        "the title's own silence, then the quit path's"

    # The cap is argued, not picked: the checkpointed run above is the longest thing this input can
    # do before Pterm, so a cap several times its cost says "never returns", not "slower than".
    # Read off the run the differential already made — `info["regs"]` is that run's out-regs.
    assert info["regs"]["ninsns"] * 4 < SPIN_CAP, "SPIN_CAP no longer leaves room for the quit path"
    _never_returns(pokes, ENTRY_TITLE_SCREEN)


def test_title_screen_ctrl_c_really_writes_the_high_score():
    """...and the bytes that reach HIGH.SCO are hiscore_name's, which is what says the branch landed
    in the quit tail proper rather than merely somewhere past the `beq.w`."""
    pokes = _ctrl_c_pokes()
    image = _oracle_final(pokes, ENTRY_TITLE_SCREEN, stop_pc=test_input.CHECKPOINT_BEFORE_PTERM)
    assert test_input._staged_highsco(image) == pokes[A_HISCORE_NAME]


# ------------------------------------------------------------------ the joystick, past the wait

def _ikbd_pokes(joystick0, joystick1, two_player, buffer=IKBD_PACKET_BUF):
    """The rotated entry's staging: a reply already in ikbd_packet, and the mode it acts on."""
    pokes = _title_pokes(two_player=two_player)
    pokes[A_IKBD_PACKET] = struct.pack(">I", buffer)
    pokes[buffer] = bytes([joystick0, joystick1])
    return pokes


def _ikbd_case(joystick0, joystick1, two_player, expect, stop_pc=0, poison=False,
               buffer=IKBD_PACKET_BUF):
    pokes = _ikbd_pokes(joystick0, joystick1, two_player, buffer)
    diffs, info = differential(TITLE_IKBD_WAIT_PC, {"_pokes": pokes}, _title_ikbd,
                               stop_pc=stop_pc, poison=poison)
    assert not diffs, f"joysticks {joystick0:#04x}/{joystick1:#04x}\n{report(diffs)}"
    assert info["ret"] == expect
    return pokes, info


# ZIPPED, not stacked: the fire test reads only the two joystick bytes and the mode test only
# two_player_mode, so the axes are independent and a cross product would buy twelve duplicate runs.
# All four fire shapes and all four mode bytes still appear, and the fuzz below crosses them anyway.
@pytest.mark.parametrize("joystick0,joystick1,two_player",
                         ((IKBD_FIRE, 0, 0), (0, IKBD_FIRE, 1),
                          (IKBD_FIRE, IKBD_FIRE, 0x80), (0x8f, 0x0f, 0xff)))
def test_title_screen_joystick_fire_starts_the_game(joystick0, joystick1, two_player):
    """VERIFIED FROM 0x10bb8 — entered at the IKBD wait with the reply already staged, the same
    rotation hiscore_joystick_input is verified through, and for the same reason: the wait's own
    prologue clears ikbd_packet, so no poked reply survives a run that starts before it.

    From the wait on this is an ordinary run to the `rts`. Either stick's fire button starts the
    game — the two bytes are OR-ed and only the SIGN of that byte is read — and the mode comes from
    whatever two_player_mode already held, tested with `tst.b`, so any non-zero byte means two.
    """
    _, info = _ikbd_case(joystick0, joystick1, two_player, TITLE_STARTED, poison=True)
    assert _wrote(info, A_PLAYERS_ALIVE) == (2 if two_player else 1)
    assert _wrote(info, A_TWO_PLAYER_MODE) == (1 if two_player else 0)
    assert _wrote(info, A_OBJECT_TABLE + OBJ_LIVES) == TITLE_STARTING_LIVES


@pytest.mark.parametrize("joystick0,joystick1", ((0, 0), (0x7f, 0x7f), (0x0f, 0x40)))
def test_title_screen_joystick_without_fire_goes_round_the_attract_loop(joystick0, joystick1):
    """No fire: the `bpl.w` branches back to the attract head at 0x10b22 having written NOTHING, and
    from there the run is the no-key one again — so it never returns, which is the pair this
    checkpoint needs."""
    pokes, info = _ikbd_case(joystick0, joystick1, 0, TITLE_ATTRACT, stop_pc=TITLE_ATTRACT_HEAD)
    assert not [addr for addr in info["writes"] if addr < emu.STACK_GUARD_LO], \
        "the ORIGINAL wrote to the image on the no-fire path"
    _never_returns(pokes, TITLE_IKBD_WAIT_PC)


@pytest.mark.parametrize("buffer", (IKBD_PACKET_BUF_HIGH_ZERO, IKBD_PACKET_BUF_LSB_ONLY))
@pytest.mark.parametrize("joystick0,joystick1,expect,stop_pc",
                         ((IKBD_FIRE, 0, TITLE_STARTED, 0),
                          (0, 0, TITLE_ATTRACT, TITLE_ATTRACT_HEAD)))
def test_title_screen_waits_on_the_whole_packet_longword(joystick0, joystick1, expect, stop_pc,
                                                         buffer):
    """THE WAIT IS A `tst.l`, pinned by STAGING rather than by an encoding read.

    Every other case in this file puts the reply buffer at IKBD_PACKET_BUF, whose pointer's second
    byte is 0x06 — so a wait that read only the first two bytes of ikbd_packet would see a non-zero
    word and behave identically on all of them. That made the width look like an inherent limit of
    the harness; it was a property of the chosen address.

    ONE PROBE BUFFER IS NOT ENOUGH EITHER, and that was the second half of the same mistake: a
    pointer whose high word is zero kills a wait reading `packet[0] | packet[1]`, but its own LOW
    byte is zero too, so a wait reading `packet[0] | packet[1] | packet[2]` survives it. The second
    buffer's pointer is non-zero ONLY in that last byte. With both, a wait narrowed at EITHER end
    never terminates and `_title_ikbd`'s deadline turns that into an ordinary red (measured, both).

    THREE of the pointer's four bytes are pinned this way. The fourth — byte 0, the most significant
    — cannot be: every address inside a 0x100000-byte image has it zero, so no legal pointer can
    make it matter. That one byte is what test_the_ikbd_wait_tests_the_whole_longword still covers
    against the original's own encoding.
    """
    _ikbd_case(joystick0, joystick1, 0, expect, stop_pc=stop_pc, buffer=buffer)


# What the glue refuses: an empty packet (the spin would never end) and a pointer the routine may
# not dereference — 0x100000 is the first address past the image, and UNWRITTEN_L is _title_pokes'
# OWN default, which is why an _ikbd_pokes that forgot its override must not sail through.
UNREADABLE_PACKETS = (0, harness.OS_IMAGE_SIZE, harness.OS_IMAGE_SIZE - 1, UNWRITTEN_L, 0xffffffff)


@pytest.mark.parametrize("packet", UNREADABLE_PACKETS)
def test_title_ikbd_glue_refuses_a_wait_it_could_not_leave(packet):
    """THE CANDIDATE'S HALF of the wait, and why g_title_ikbd_pass is not a bare forwarder.

    Two refusals, and they fail differently. With ikbd_packet EMPTY the reconstruction's spin never
    ends and would hang the pytest worker with no output at all; only harness.differential's
    oracle-first ordering keeps that unreachable, and nothing pins that ordering. With a pointer
    OUTSIDE THE IMAGE the spin ends at once and the two cores then disagree about what it points at
    — the oracle's memory callbacks answer 0 for any address past its size, while the candidate
    would index host memory past the end of the buffer, which is undefined behaviour that either
    fabricates a diff or kills the worker. Neither reading is the original's, so the glue refuses.

    OS_IMAGE_SIZE - 1 is the boundary case: the last byte is in the image, but the packet's SECOND
    byte is not, so it must be refused too.
    """
    buf = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer(
        bytearray(harness.make_image({A_IKBD_PACKET: struct.pack(">I", packet)})))
    assert _title_ikbd(harness._lib, buf) == TITLE_PASS_REFUSED, \
        f"the glue entered the wait with ikbd_packet = {packet:#x}"


def test_the_ikbd_wait_tests_the_whole_longword():
    """The ONE byte of the wait no staged pointer can reach, against the original's own encoding.

    The other three are pinned by staging (test_title_screen_waits_on_the_whole_packet_longword);
    byte 0 is not reachable at all, because every address inside a 0x100000-byte image has it zero,
    so a wait ignoring it agrees with `tst.l` on every legal pointer. That is an equivalent mutant
    under the model rather than a coverage hole — but the ORIGINAL still spells a longword test, and
    this is what says so, the same technique test_cycle_palettes_component_shifts_are_logical uses.
    """
    assert _immediate(TITLE_IKBD_WAIT_PC, 2) == 0x4ab9, "0x10bb8 is not `tst.l abs.l`"
    assert _immediate(TITLE_IKBD_WAIT_PC + 2, 4) == A_IKBD_PACKET
    assert _immediate(TITLE_IKBD_WAIT_PC + 6, 2) == 0x67f8, "the `beq.s` back to the wait head"


def test_title_ikbd_glue_accepts_the_last_readable_packet():
    """...and the pair the refusals need: the byte BELOW the boundary is accepted, so the guard is
    a bound and not a blanket. Both packet bytes are inside the image, both are zero, so the run is
    the ordinary no-fire one and reports TITLE_ATTRACT."""
    packet = harness.OS_IMAGE_SIZE - IKBD_PACKET_BYTES
    buf = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer(
        bytearray(harness.make_image({A_IKBD_PACKET: struct.pack(">I", packet)})))
    assert _title_ikbd(harness._lib, buf) == TITLE_ATTRACT


# ------------------------------------------------------------------ fuzz

TITLE_KEY_CHUNKS = 8


def _title_key_cases():
    """Every ASCII byte the console can deliver, each with its own palette, picture and chip state.

    Classified by what the key does, because that decides where the run can be stopped: '1'/'2'
    reach the `rts`, Ctrl-C the quit tail's checkpoint, and everything else the IKBD wait.

    The cycled pen is drawn from a set that is HALF colourless, so half the corpus runs the colour
    cycle's early return and half runs it for real and feeds its output into the ring. The three
    coloured values are the levels the shipped ring can circulate (see cycle_palette's row in
    ../STATUS.md); without them every case would take the early return and the composed pass would
    never be fuzzed.
    """
    hues = (TITLE_HUE_COLOURLESS, TITLE_HUE_COLOURLESS, 0x0300, 0x0020, 0x0004, 0x0200)
    rng = random.Random(ENTRY_TITLE_SCREEN)
    for key in range(0x100):
        yield (key, rng.randrange(1, 1 << 16), rng.choice((0, PSG_MIXER_ALL_OFF)),
               rng.randrange(2), rng.choice(hues))


@pytest.mark.parametrize("chunk", range(TITLE_KEY_CHUNKS))
def test_title_screen_key_fuzz(chunk):
    """256 keys x a fresh noise picture, palette table, counter, mixer, mode and cycled pen."""
    ran, cycled = 0, 0
    for key, counter, mixer, two_player, hue in _title_key_cases():
        if key % TITLE_KEY_CHUNKS != chunk:      # one case per byte, so the key IS the shard index
            continue
        cycled += hue != TITLE_HUE_COLOURLESS
        staging = dict(seed=key, counter=counter, mixer=mixer, two_player=two_player, hue=hue)
        if key == KEY_CTRL_C:
            _ctrl_c_case(**staging)
        elif key in (TITLE_KEY_ONE_PLAYER, TITLE_KEY_TWO_PLAYER):
            _title_case(TITLE_STARTED, key=chr(key), **staging)
        else:
            _title_case(TITLE_IKBD_WAIT, stop_pc=TITLE_IKBD_WAIT_PC, key=chr(key), **staging)
        ran += 1
    assert ran, "this shard ran no cases"
    assert 0 < cycled < ran, "this shard no longer covers both arms of the colour cycle"


def _joystick_cases():
    rng = random.Random(TITLE_IKBD_WAIT_PC)
    return [(rng.randrange(0x100), rng.randrange(0x100), rng.randrange(0x100))
            for _ in range(120)]


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_title_screen_joystick_fuzz(chunk):
    """Random reply bytes x random two_player_mode bytes, each classified by the OR of the two
    joystick bytes so a corpus that stopped covering one arm fails instead of sharding cleanly."""
    fired = 0
    ran = 0
    for index, (joystick0, joystick1, two_player) in enumerate(_joystick_cases()):
        if index % FUZZ_CHUNKS != chunk:
            continue
        fire = (joystick0 | joystick1) & IKBD_FIRE
        fired += bool(fire)
        _ikbd_case(joystick0, joystick1, two_player,
                   TITLE_STARTED if fire else TITLE_ATTRACT,
                   stop_pc=0 if fire else TITLE_ATTRACT_HEAD)
        ran += 1
    assert ran, "this shard ran no cases"
    assert 0 < fired < ran, "this shard no longer covers both arms of the fire test"


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


def test_title_screen_constants_match_the_c():
    """Everything the title-screen battery restates, against the file that owns it.

    TITLE_HUE_RING is deliberately NOT pinned: it is a C array, which `_defines` cannot read, and it
    does not need to be — the Python tuple is an INDEPENDENT model of the permutation, checked
    against the ORACLE's image, while the C array is checked against the same oracle by the diff. A
    drift on either side fails as a case rather than as a pin.
    """
    init_c, init_h = _defines("src/init.c"), _defines("include/init.h")
    for name, mirrored in (("TITLE_COLOR_PROMPT", TITLE_COLOR_PROMPT),
                           ("TITLE_COLOR_HISCORE", TITLE_COLOR_HISCORE),
                           ("TITLE_COLOR_CREDITS", TITLE_COLOR_CREDITS),
                           ("TITLE_POLL_PASSES", TITLE_POLL_PASSES),
                           ("TITLE_STARTING_LIVES", TITLE_STARTING_LIVES),
                           ("SND_TITLE_TUNE", SND_TITLE_TUNE),
                           ("TITLE_KEY_ONE_PLAYER", TITLE_KEY_ONE_PLAYER),
                           ("TITLE_KEY_TWO_PLAYER", TITLE_KEY_TWO_PLAYER),
                           ("TITLE_HUE_RING_PENS", len(TITLE_HUE_RING)),
                           ("TITLE_PASS_REFUSED", TITLE_PASS_REFUSED)):
        assert init_c[name] == mirrored, f"{name} differs from src/init.c"
    for name, mirrored in (("STR_TITLE_PROMPT", STR_TITLE_PROMPT),
                           ("STR_TITLE_HISCORE", STR_TITLE_HISCORE),
                           ("STR_TITLE_CREDITS", STR_TITLE_CREDITS),
                           ("TITLE_STARTED", TITLE_STARTED), ("TITLE_QUIT", TITLE_QUIT),
                           ("TITLE_IKBD_WAIT", TITLE_IKBD_WAIT),
                           ("TITLE_ATTRACT", TITLE_ATTRACT)):
        assert init_h[name] == mirrored, f"{name} differs from include/init.h"

    # ...and the four other layers' constants this battery reaches into.
    for header, names in (("include/input.h", (("KEY_CTRL_C", KEY_CTRL_C),
                                               ("A_ikbd_cmd_joyread", A_IKBD_CMD_JOYREAD),
                                               ("IKBD_PACKET_BYTES", IKBD_PACKET_BYTES))),
                          ("include/sound.h", (("A_snd_priority", A_SND_PRIORITY),
                                               ("SND_PRIORITY_IDLE", SND_PRIORITY_IDLE),
                                               ("A_snd_list_silence", A_SND_LIST_SILENCE),
                                               ("A_sound_table", A_SOUND_TABLE))),
                          ("include/draw.h", (("A_text_color", A_TEXT_COLOR),)),
                          ("include/score.h", (("OBJ_SCORE_LAST_DIGIT", OBJ_SCORE_LAST_DIGIT),)),
                          ("include/joust.h", (("OBJ_FLAGS", OBJ_FLAGS),)),
                          ("include/addrs.h", (("A_draw_y", A_DRAW_Y),))):
        defines = _defines(header)
        for name, mirrored in names:
            assert defines[name] == mirrored, f"{name} differs from {header}"

    for name, mirrored in (("PSG_MIXER", PSG_MIXER), ("PSG_MIXER_ALL_OFF", PSG_MIXER_ALL_OFF)):
        assert _defines("src/sound.c")[name] == mirrored, f"{name} differs from src/sound.c"

    # g_title_ikbd_pass returns values from BOTH spaces — init.h's four outcomes and src/init.c's
    # glue-only refusal — and the two pins above scrape one file each, so only this sees a
    # collision. Without it, a later TITLE_* added to init.h as "the next free number" would make
    # the refusal indistinguishable from a real outcome with every existing test still green.
    outcomes = {name: init_h[name]
                for name in ("TITLE_STARTED", "TITLE_QUIT", "TITLE_IKBD_WAIT", "TITLE_ATTRACT")}
    assert init_c["TITLE_PASS_REFUSED"] not in outcomes.values(), \
        f"TITLE_PASS_REFUSED collides with one of {outcomes}"


def test_title_screen_resumes_the_poll_without_spending_a_pass():
    """An unrecognised key branches back to the POLL HEAD at 0x10b88, not to the `subq.w` at
    0x10b9a — so it costs the attract pass nothing. Both runs end at the same IKBD wait with the
    counter at 0, so the differential cannot tell the two apart; only the encoding can."""
    displacement = struct.unpack_from(">b", harness.BASE_IMAGE, 0x10bf9)[0]
    assert _immediate(0x10bf8, 1) == 0x66, "0x10bf8 is not a `bne.s`"
    assert 0x10bf8 + 2 + displacement == 0x10b88, "the unrecognised key no longer resumes the poll"


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
