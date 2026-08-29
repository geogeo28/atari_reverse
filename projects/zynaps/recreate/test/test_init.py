"""Differential tests for the boot prologue and the level-section flow (src/init.c).

EVERY CASE HERE IS A CHECKPOINT RUN, and it has to be: `_start` never returns and neither does the
section chain it ends in — there is not an `rts` between 0x10000 and the frame loop at 0x10f4e. So a
case names an entry PC and a stop PC and the differential diffs the image THERE
(`docs/agent-playbook.md` §5), and each of the seven slices below states in its own docstring which
address range that proves. What lies between the ranges is in STATUS.md, not papered over.

THE FILES ARE THE DISK'S OWN, AND WHICH ONES IS THE GAME'S CHOICE. The section flow patches a
variant letter or digit into a filename in the text segment and then opens whatever the string now
says, so this file works out each section's file list from the binary's own sixteen-byte tables
rather than from a list a test author typed — a wrong table index would then stage the wrong file
and the open would be refused rather than quietly passing.
"""
import ctypes
import functools
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

# The seven slices, as (entry, stop). Each is pinned by name in ENTRY_PROLOGUES at the bottom.
ENTRY_BOOT_ENTER_SUPERVISOR = 0x10000
STOP_BOOT_ENTER_SUPERVISOR = 0x10010          # the Line-A opcode, which the oracle cannot execute
ENTRY_BOOT_SAVE_VBL_VECTOR = 0x10012
STOP_BOOT_SAVE_VBL_VECTOR = 0x1001c           # the first `ikbd_send_cmd`, which busy-waits
ENTRY_BOOT_LOAD_TITLE_ASSETS = 0x1002c
STOP_BOOT_LOAD_TITLE_ASSETS = 0x101ba         # where the NINTH staged file would be opened
ENTRY_SECTION_ADVANCE = 0x10814
ENTRY_SECTION_RELOAD_NEEDED = 0x1083a
STOP_SECTION_RELOAD = 0x1085a                 # the reload arm, at its first unported `bsr`
STOP_SECTION_NO_RELOAD = 0x10b6e              # the other arm's `beq` target
ENTRY_SECTION_RELOAD_INTRO_SCREENS = 0x1085a
ENTRY_SECTION_LOAD_ASSETS = 0x10862
STOP_SECTION_LOAD_ASSETS = 0x10b6e
ENTRY_SECTION_RESTART_PROLOGUE = 0x10b6e
ENTRY_SECTION_START_PREFILL = 0x10c4e
STOP_SECTION_START_PREFILL = 0x10d96
# The prologue runs straight on into the prefill, so its stop IS that slice's entry.
STOP_SECTION_RESTART_PROLOGUE = ENTRY_SECTION_START_PREFILL
# Not a slice of this subsystem — src/scroll.c's, and pinned there. This battery enters it to
# produce the unpacked map its prefill cases run on, exactly as test_scroll.py does.
ENTRY_MAP_RLE_DECOMPRESS = 0x15920

# ---- mirrors of include/init.h ----
A_VECTOR_VBL = 0x70
A_VECTOR_TIMER_B = 0x120
A_VBL_ISR = 0x10776
A_TIMER_B_ISR = 0x10782
A_SAVED_TOS_VBL_VECTOR = 0x195d0
SHIFTER_MODE_RESOLUTION_MASK = 0xfc
A_LEVEL_SECTION = 0x19895
A_LEVEL_SECTION_LOADED = 0x19913
A_SHOW_PREPARE_FOR_COMBAT = 0x19aac
A_ASTEROID_SECTION_FLAG = 0x198fd
A_MOTHERSHIP_INDEX = 0x1987c
A_SECTION_GROUND_TARGET_FLAG = 0x19897
A_PALETTE_ASTEROID = 0x19638
A_KEY_SCANCODE = 0x19685
A_MOTHERSHIP_PENDING = 0x198af
SECTION_RESTART_SHIP_X = 0x40
SECTION_RESTART_SHADOW_X = 0x50
SECTION_RESTART_SHIP_Y = 0x64
SECTION_RESTART_SHIP_ROWS = 0x14
SECTION_RESTART_KILL_SLOTS = 18
SECTION_RESTART_ASTEROID_RECORDS = 18
SQUADRON_MARKS = 6
SECTION_RESTART_LAUNCH_STOCK = 2
# --- mirrors of include/sprite.h and include/weapon.h, which own the other two figures ---
SHIP_SPRITE_GAP = 1600
PLAYER_SHOT_SLOTS = 6
# --- mirrors of the headers the prologue borrows its resets from ---
A_ENTITY_GUNSIGHT = 0x17dd2          # include/weapon.h
A_DEATH_EVENT_FLAGS = 0x198c4        # include/weapon.h
A_MISSILE_LAUNCH_COUNTER = 0x198b5   # include/weapon.h
A_BOMB_LAUNCH_COUNTER = 0x198b6      # include/weapon.h
A_ASTEROID_RECORDS = 0x17e2a         # include/enemy.h
A_SQUADRON_KILL_COUNTERS = 0x198bb   # include/enemy.h
A_EXPLOSION_GROUP_ACTIVE_BITS = 0x19670  # include/enemy.h
A_SCROLL_FROZEN = 0x198b1            # include/enemy.h
A_PLAYER_RECORD = 0x17d7a            # include/enemy.h
A_MOTHERSHIP_READY = 0x198b0         # include/mothership.h
A_ENTITY_TABLE = 0x17a8e             # include/player.h
A_SHIP_RECORD_SHADOW = 0x17da6       # include/player.h
ENTITY_STRIDE = 0x2c                 # include/entity.h
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT = 0x00, 0x04, 0x08
ENTITY_SPRITE, ENTITY_ALIVE, ENTITY_TYPE = 0x0a, 0x0e, 0x11
ENTITY_SLOTS = 20
A_PALETTE_NEXT = 0x19f66
A_PALETTE_PER_SECTION_TABLE = 0x18fe4
SECTION_COUNT = 0x10
SECTION_TYPE_ASTEROID = 0x71
SECTION_PALETTE_BYTES = 0x20
A_ALIEN_VARIANT_TABLE = 0x197fc
A_ALIEN2_VARIANT_TABLE = 0x1980c
A_MOTHERSHIP_VARIANT_TABLE = 0x1981c
A_MISSILE_VARIANT_TABLE = 0x197eb
A_SECTION_TYPE_TABLE = 0x1984c
A_ZYN_VARIANT_TABLE = 0x1985c
A_SECTION_PALETTE_INDEX_TABLE = 0x1986c
A_GROUND_TARGET_BY_PALETTE_TABLE = 0x19898
A_SECTION_RESTART_TABLE = 0x19e84
A_SCROLL_POS = 0x195cc
A_MAP_OFFSET = 0x1823e
A_MAP_PTR = 0x18242
A_MAP_PAGE = 0x198a5
A_MAP_PAGE_PTR = 0x17986
A_MAP_PAGE_TABLE = 0x1798a
A_MAP_COLUMN = 0x198a6
MAP_PAGES = 8
SECTION_PREFILL_COLUMNS = 0xa0
A_FILENAME_ALIEN_DAT = 0x196b0
A_FILENAME_MOTHER_DAT = 0x196e8
A_FILENAME_MISSILE_DAT = 0x1970d
A_FILENAME_LEV_MAP = 0x197d9
A_FILENAME_ZYN_DAT = 0x197e2
BOOT_POWER_GAUGE_DST = 0x607be
BOOT_SHIP_SOURCE = 0x577fe
FILENAME_ALIEN_VARIANT = 5
FILENAME_MOTHER_VARIANT = 6
FILENAME_MISSILE_VARIANT = 7
FILENAME_LEV_VARIANT = 3
FILENAME_ZYN_VARIANT = 3

# ---- mirrors of include/scroll.h and include/video.h ----
A_TILE_SET_BASE = 0x4b3be
A_MAP_UNPACKED = 0x478ae
MAP_ROWS = 18
MAP_COLUMNS = 400
MAP_COLUMN_BYTES = 0x24
SCROLL_PHASES = 20
SCROLL_PHASE_STEP = 8
A_SCROLL_PREFILL_HIDE_SCREEN = 0x19ac1
A_SCROLL_COL_WORKSPACE = 0x19fae
SCROLL_COLUMN_PASSES = 72
SCROLL_COLUMN_CELL_LONGS = 8
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
SCREEN_ROW_BYTES = 160
PLAYFIELD_BYTES = 0x5a00

# The two hard-coded framebuffer addresses `_start` fixes. They already have a home in test/abi.py,
# which the scratch map is laid out around, so the mirrors below take THEM as the Python side rather
# than restating the numbers — which makes the MIRRORS entries a pin between abi.py and src/init.c.
BOOT_SCREEN_BACK = abi.SCREEN_BACK
BOOT_SCREEN_FRONT = abi.SCREEN_FRONT

MAP_UNPACKED_BYTES = MAP_COLUMNS * MAP_COLUMN_BYTES
WORKSPACE_BYTES = SCROLL_COLUMN_PASSES * SCROLL_COLUMN_CELL_LONGS * 4
DISK = harness.PRG.parent / "disk"

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_boot_enter_supervisor.argtypes = [_u8p]
harness._lib.g_boot_enter_supervisor.restype = ctypes.c_uint32
harness._lib.g_section_reload_needed.argtypes = [_u8p]
harness._lib.g_section_reload_needed.restype = ctypes.c_uint32
harness._lib.init_shifter_mode_mask_written.argtypes = []
harness._lib.init_shifter_mode_mask_written.restype = ctypes.c_uint8
harness._lib.init_shifter_mode_writes.argtypes = []
harness._lib.init_shifter_mode_writes.restype = ctypes.c_uint32
harness._lib.init_palette_uploads.argtypes = []
harness._lib.init_palette_uploads.restype = ctypes.c_uint32
harness._lib.g_section_load_assets.argtypes = [_u8p]
harness._lib.g_section_load_assets.restype = ctypes.c_uint32
for _sym in ("g_boot_save_vbl_vector", "g_boot_load_title_assets", "g_section_advance",
             "g_section_reload_intro_screens", "g_section_restart_prologue",
             "g_section_start_prefill"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None


def _table_byte(table, section):
    """One per-section table byte, read out of the loaded image."""
    return harness.BASE_IMAGE[table + section]


def _section_files(section):
    """The files this section's own tables name, in the order the flow opens them.

    Derived from the binary rather than transcribed: the flow patches each variant character into
    the filename and opens the patched string, so this is the same lookup the code does — and an
    index this test got wrong would stage a file the routine never opens, whose own open would then
    be refused by the trap model instead of passing quietly.
    """
    names = [f"alien{chr(_table_byte(A_ALIEN_VARIANT_TABLE, section))}.dat",
             f"alien{chr(_table_byte(A_ALIEN2_VARIANT_TABLE, section))}.dat",
             f"mother{chr(_table_byte(A_MOTHERSHIP_VARIANT_TABLE, section))}.dat",
             f"missile{chr(_table_byte(A_MISSILE_VARIANT_TABLE, section))}.dat"]
    kind = chr(_table_byte(A_SECTION_TYPE_TABLE, section))
    if ord(kind) == SECTION_TYPE_ASTEROID:
        return names + ["bigast.dat"]
    names.append(f"lev{kind}.map")
    names.append(f"zyn{chr(_table_byte(A_ZYN_VARIANT_TABLE, section))}.dat")
    palette_index = _table_byte(A_SECTION_PALETTE_INDEX_TABLE, section)
    names.append("gndtarg1.dat"
                 if _table_byte(A_GROUND_TARGET_BY_PALETTE_TABLE, palette_index) else "rocket.dat")
    return names


def _is_asteroid_section(section):
    return _table_byte(A_SECTION_TYPE_TABLE, section) == SECTION_TYPE_ASTEROID


MAP_SECTIONS = tuple(s for s in range(SECTION_COUNT) if not _is_asteroid_section(s))
ASTEROID_SECTIONS = tuple(s for s in range(SECTION_COUNT) if _is_asteroid_section(s))


def _stage(names):
    """Stage the named disk files, which is what lets the routine's Fopen/Fread/Fclose be served."""
    pokes, _handles = harness.stage_files([(n, (DISK / n.upper()).read_bytes()) for n in names])
    return pokes


def _slice_case(entry, stop, pokes, glue, label, poison=False, max_insns=200_000):
    diffs, info = differential(entry, {"_pokes": pokes}, glue, stop_pc=stop, poison=poison,
                               max_insns=max_insns)
    assert not diffs, f"{label} [{entry:#x}, {stop:#x})\n{report(diffs)}"
    return info


# ============================================================ boot_enter_supervisor @ 0x10000

def test_boot_enter_supervisor():
    """GEMDOS Super(0), and then the program takes the old supervisor stack as its own.

    THE SLICE WRITES NO IMAGE BYTE — the three pushes are stack and the trap is served from the
    model — so the empty diff is not the assertion here; the token in D0 is, and it is compared
    against the ORACLE's own D0. What no image differential can reach is that A7 then becomes that
    token: `emu.REPORTED_REGS` does not carry A7, and the reconstruction has no machine stack of its
    own. STATUS.md records that residual rather than this case pretending to hold it.
    """
    info = _slice_case(ENTRY_BOOT_ENTER_SUPERVISOR, STOP_BOOT_ENTER_SUPERVISOR, {},
                       lambda lib, buf: lib.g_boot_enter_supervisor(buf), "super")
    assert info["ret"] == info["regs"]["d0"], (
        f"Super(0) token cand={info['ret']:#x} oracle={info['regs']['d0']:#x}")
    assert info["ret"] == harness.OS_SUPER_TOKEN


# ============================================================ boot_save_vbl_vector @ 0x10012

@pytest.mark.parametrize("vector", (0x00fc1234, 0, 0xffffffff))
def test_boot_save_vbl_vector(vector):
    """`move.l $70.l,$195d0.l`, over three values of the vector TOS left there.

    Both addresses are inside the image, so this is the one part of the boot prologue that is
    ordinary diffable memory. The destination is seeded with a value that is neither of them, which
    is what makes a candidate that copied nothing differ (both addresses are otherwise zero in the
    loaded image, and zero over zero differs nowhere).
    """
    pokes = {A_VECTOR_VBL: vector.to_bytes(4, "big"), A_SAVED_TOS_VBL_VECTOR: b"\x5a\xa5\x5a\xa5"}
    _slice_case(ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR, pokes,
                lambda lib, buf: lib.g_boot_save_vbl_vector(buf), f"vbl={vector:#x}")


def test_boot_save_vbl_vector_attribution():
    """Poison: a candidate that wrote nothing stays canary at the destination."""
    pokes = {A_VECTOR_VBL: (0x00fc1234).to_bytes(4, "big")}
    _slice_case(ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR, pokes,
                lambda lib, buf: lib.g_boot_save_vbl_vector(buf), "poison", poison=True)


# ========================================================= boot_load_title_assets @ 0x1002c

# The eight files `_start` reads before the slice's end, in the order it reads them. Unlike the
# section flow's, these filenames are constants in the table and are never patched — so the list is
# read off the `lea`s in the disassembly and the assertion below is what ties it to them.
BOOT_FILES = ("zynpic.pic", "power.dat", "myship.dat", "status.pi1", "bullet.dat", "explode.dat",
              "gemgraf.dat", "spinners.dat")
BOOT_MAX_INSNS = 4_000_000


def test_boot_files_are_the_names_the_table_holds():
    """Each name in BOOT_FILES is the nul-terminated string at the address `_start` passes.

    Cheap, and it is what stops the list above from drifting into a list of files that happen to be
    on the disk: a `lea` this battery misread would stage a file the slice never opens.
    """
    for address, name in ((0x19692, "zynpic.pic"), (0x1969d, "power.dat"), (0x196bb, "myship.dat"),
                          (0x196c6, "status.pi1"), (0x196d1, "bullet.dat"),
                          (0x196dc, "explode.dat"), (0x196f4, "gemgraf.dat"),
                          (0x19700, "spinners.dat")):
        end = harness.BASE_IMAGE.index(0, address)
        assert bytes(harness.BASE_IMAGE[address:end]).decode("ascii") == name


def test_boot_load_title_assets():
    """The longest stretch of `_start` the harness can run end to end: 0x1002c to 0x101ba.

    Eight files read straight off the disk into the addresses the game gives them, the two
    framebuffer pointers fixed at their hard-coded values, the game's own VBL and Timer B vectors
    installed over TOS's, the title tune started, the picture published, its palette uploaded, seven
    ship frames de-interleaved and one four-frame preshift bank built. Every one of those is a leaf
    another battery already verified; what THIS case proves is the composition — the order and the
    addresses — over the whole image at once.

    THE LEDGER ASSERTIONS BELOW RIDE ON THE SAME RUN, deliberately: they read the candidate sink the
    differential has just filled, so they need no second 4-million-instruction run and no second seam
    into the candidate's image. They cover the two effects the image cannot —

      * `andi.b #$fc,$ff8260` selects low resolution at an address far above the image. RESIDUAL, and
        a bigger one than the palette's and the screen base's: it is a read-modify-write and the READ
        half has no modelled answer on either side, so what the sink holds is the mask and the fact
        that the write happened, never the byte that came back. On target that byte decides the other
        six bits of the mode register (`docs/on-target-execution.md`).
      * `set_palette_title` writes NO image byte at all — its whole effect is sixteen colour
        registers, recorded in src/video.c's own sink, which nothing here can read. Without the
        upload count, deleting that call from the slice would leave this case green.
    """
    _slice_case(ENTRY_BOOT_LOAD_TITLE_ASSETS, STOP_BOOT_LOAD_TITLE_ASSETS, _stage(BOOT_FILES),
                lambda lib, buf: lib.g_boot_load_title_assets(buf), "boot assets",
                max_insns=BOOT_MAX_INSNS)
    assert harness._lib.init_shifter_mode_mask_written() == SHIFTER_MODE_RESOLUTION_MASK
    assert harness._lib.init_shifter_mode_writes() == 1
    assert harness._lib.init_palette_uploads() == 1


# ================================================================ section_advance @ 0x10814

@pytest.mark.parametrize("section", tuple(range(SECTION_COUNT)) + (0xff,))
def test_section_advance(section):
    """Every section number, plus 0xff.

    The wrap is a `cmpi.b #$10` against the INCREMENTED byte, so 15 wraps to 0 and 0xff — which the
    flow never produces, but which the byte can hold — increments to 0 and is left there rather than
    wrapping again. The map cursor is reset to the level's first column whichever way it goes, and
    it is seeded elsewhere so a candidate that skipped the reset differs.
    """
    pokes = {A_LEVEL_SECTION: bytes([section]), A_MAP_PTR: b"\x00\x0d\xea\xdc"}
    _slice_case(ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED, pokes,
                lambda lib, buf: lib.g_section_advance(buf), f"section={section:#x}")


def test_section_advance_attribution():
    """Poison: the map cursor reset and the section byte are both attributable."""
    _slice_case(ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED, {A_LEVEL_SECTION: b"\x07"},
                lambda lib, buf: lib.g_section_advance(buf), "poison", poison=True)


# =========================================================== section_reload_needed @ 0x1083a

@pytest.mark.parametrize("loaded,section,reload_needed",
                         ((0, 0, False), (3, 3, False), (0xff, 0xff, False),
                          (0, 1, True), (3, 4, True), (0xff, 0, True)))
def test_section_reload_needed(loaded, section, reload_needed):
    """The gate's two arms, which END AT DIFFERENT ADDRESSES — so each is its own checkpoint.

    Equal, the flow branches straight to the section start and this slice writes nothing at all;
    different, it records the section as loaded and clears the PREPARE FOR COMBAT banner. Both
    destination bytes are seeded to values neither arm produces, so the no-write arm is a real
    assertion rather than an empty one.
    """
    pokes = {A_LEVEL_SECTION: bytes([section]), A_LEVEL_SECTION_LOADED: bytes([loaded]),
             A_SHOW_PREPARE_FOR_COMBAT: b"\x5a"}
    stop = STOP_SECTION_RELOAD if reload_needed else STOP_SECTION_NO_RELOAD
    info = _slice_case(ENTRY_SECTION_RELOAD_NEEDED, stop, pokes,
                       lambda lib, buf: lib.g_section_reload_needed(buf),
                       f"loaded={loaded:#x} section={section:#x}")
    assert bool(info["ret"]) == reload_needed


# ============================================================ section_load_assets @ 0x10862

SECTION_LOAD_MAX_INSNS = 20_000_000


@pytest.mark.parametrize("section", MAP_SECTIONS)
def test_section_load_assets(section):
    """Every non-asteroid section, over the files its own tables name.

    THE FILENAMES ARE PATCHED IN THE TEXT SEGMENT and the diff covers them, so this case holds the
    nine table lookups as well as the loads they steer: a wrong index writes a different letter into
    `alien_.dat` and the open is then refused by the trap model rather than passing. Downstream of
    the loads it also composes the map unpacker, four preshift builders, five block copies and the
    per-section palette row — every one of them verified elsewhere, with the ORDER and the addresses
    proved here.
    """
    pokes = _stage(_section_files(section))
    pokes[A_LEVEL_SECTION] = bytes([section])
    info = _slice_case(ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS, pokes,
                       lambda lib, buf: lib.g_section_load_assets(buf), f"section={section}",
                       max_insns=SECTION_LOAD_MAX_INSNS)
    assert info["ret"] == 1, f"section {section} is a map section but the map arm did not run"


@pytest.mark.parametrize("section", ASTEROID_SECTIONS)
def test_section_load_assets_of_an_asteroid_section(section):
    """Each of the four asteroid sections in full, over BIGAST.DAT and its own four other files.

    This case covers the prefix as well as the arm. An earlier revision stopped the oracle at the
    `beq` itself (0x109e2) so the shared prefix could be verified while the arm was unported; that
    checkpoint is gone with the arm's landing, because the candidate has no prefix to stop at.

    The arm is short and every one of its effects is in the diff: the six sprite banks built and
    preshifted into `A_backdrop_page0` (46 KB of them), the flag the map arm CLEARS and this one
    SETS, and the fixed 32-byte palette row it takes instead of a per-section one. It also proves
    the arm SKIPS the map: the tile-set buffer holds BIGAST.DAT's bytes and nothing else, where the
    map arm would have overwritten them with a level file twice over.
    """
    pokes = _stage(_section_files(section))
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes[A_ASTEROID_SECTION_FLAG] = b"\x5a"      # neither arm's answer, so the store is visible
    # ...and a palette row unlike anything in the per-section table, which is what makes the SOURCE
    # ADDRESS observable — see test_the_asteroid_palette_row_is_only_pinned_by_a_poke below.
    pokes[A_PALETTE_ASTEROID] = ASTEROID_PALETTE_PROBE
    info = _slice_case(ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS, pokes,
                       lambda lib, buf: lib.g_section_load_assets(buf), f"asteroid section={section}",
                       max_insns=SECTION_LOAD_MAX_INSNS)
    assert info["ret"] == 0, f"section {section} is an asteroid section but the map arm ran"


# A colour row no shipped table holds. The shifter ignores the top nibble of each pen and the game
# never writes one, so the probe stays inside the 0x0777 range a real palette uses — it is a palette
# the level designer did not choose, not a nonsense value.
ASTEROID_PALETTE_PROBE = bytes.fromhex(
    "0111022203330444055506660777011302240335044604570560067107120123")


def test_the_asteroid_palette_row_is_only_pinned_by_a_poke():
    """THE SHIPPED 0x19638 ROW IS BYTE-IDENTICAL TO ROW 0 OF THE TABLE AT 0x18fe4. Measured.

    So on the shipped image a candidate that took the asteroid palette from the per-section table's
    first row would copy exactly the same 32 bytes, and no case over the game's own data could tell
    the two sources apart — a mutation swapping them survived the whole suite until the case above
    started poking `ASTEROID_PALETTE_PROBE` over 0x19638. The poke is real program data given to
    BOTH sides, not a fabricated record; this assertion is what stops it looking arbitrary, and it
    fails loudly if a future image ever makes the two rows differ on their own.
    """
    shipped = bytes(harness.BASE_IMAGE[A_PALETTE_ASTEROID:
                                       A_PALETTE_ASTEROID + SECTION_PALETTE_BYTES])
    row_zero = bytes(harness.BASE_IMAGE[A_PALETTE_PER_SECTION_TABLE:
                                        A_PALETTE_PER_SECTION_TABLE + SECTION_PALETTE_BYTES])
    assert shipped == row_zero, (
        "0x19638 and the per-section table's row 0 no longer agree — the poke in "
        "test_section_load_assets_of_an_asteroid_section is no longer the only thing pinning the "
        "asteroid arm's palette source, and this note can be simplified")
    assert ASTEROID_PALETTE_PROBE != shipped
    assert len(ASTEROID_PALETTE_PROBE) == SECTION_PALETTE_BYTES


def test_the_asteroid_palette_row_is_not_one_of_the_per_section_rows():
    """The asteroid arm's `movem.l $19638` reads a row OUTSIDE the sixteen-row table at 0x18fe4.

    Without this the two arms' palette work would look like one lookup with a different index, and a
    candidate that reached the asteroid row by indexing the table would pass every case above.
    """
    assert not (A_PALETTE_PER_SECTION_TABLE <= A_PALETTE_ASTEROID
                < A_PALETTE_PER_SECTION_TABLE + SECTION_COUNT * SECTION_PALETTE_BYTES)


def test_section_load_assets_covers_both_ground_targets():
    """The two arms of `tst.b $19897` are both reached by the shipped sections.

    The ground-target graphic is chosen by a flag that is itself a table byte, so which arm a
    section takes is the level designer's and not this battery's; this is where the claim that both
    are exercised is held against the tables rather than assumed.
    """
    chosen = {_section_files(section)[-1] for section in MAP_SECTIONS}
    assert chosen == {"gndtarg1.dat", "rocket.dat"}, chosen


ASTEROID_SECTION_COUNT = 4       # measured: the section-type table's four 'q' entries


def test_both_arms_are_driven_and_every_section_is_one_or_the_other():
    """Four of the sixteen sections branch at 0x109e2, and BOTH arms now have cases above.

    This used to say the asteroid arm was unported. It is not: `test_section_load_assets_of_an_
    asteroid_section` drives all four. What the count still buys is that neither list can quietly
    empty — if a table changed and every section became a map section, MAP_SECTIONS would claim
    coverage of an arm nothing exercised.
    """
    assert len(ASTEROID_SECTIONS) == ASTEROID_SECTION_COUNT
    assert len(MAP_SECTIONS) == SECTION_COUNT - ASTEROID_SECTION_COUNT
    assert ASTEROID_SECTIONS and MAP_SECTIONS


# ================================================ section_reload_intro_screens @ 0x1085a
# ...and section_restart_prologue @ 0x10b6e.
#
# BOTH SLICES CALL TWO WHOLE FRONT-END SCREENS (`player_intro_screen` @ 0x13426 and
# `status_panel_redraw_all` @ 0x135bc), so they need every graphic those two read staged at the
# address `_start` loads it to. test_hud.py already derives that set from the .PRG and the disk —
# the eight .DAT files and the three panel strips CUT OUT OF STATUS.PI1 rather than staged from
# anywhere else — and rebuilding it here would be a second source of truth for panel graphics.
# It is imported instead, which is also what test_constants.py does to every battery.
#
# NEITHER SLICE TAKES A POISON PASS, for test_hud.py's own two reasons: `player_intro_screen` ends
# in `screen_flip_buffers`, which writes the very longwords it read its draw buffer from, and
# `draw_power_gauge` inside the panel repaint writes a clamped level back and then indexes a frame
# table with it. Both are recorded there; nothing is added here.
import test_hud                                                          # noqa: E402

# The four names this battery borrows from it, checked at import so a rename over there fails HERE
# with a sentence instead of an AttributeError inside an unrelated case. Three are underscore-
# private, which is exactly why nothing in test_hud would otherwise signal the dependency.
for _borrowed in ("_panel_pokes", "_buffer_pokes", "A_SCREEN_BACK_BUFFER", "A_SCREEN_FRONT_BUFFER"):
    assert hasattr(test_hud, _borrowed), (
        f"test_init.py's two front-end slices reuse test_hud.{_borrowed} for its panel staging; "
        f"that name is gone, so either restore it or give this battery its own staging")

RESET_SEED = 0x5a               # neither arm's answer for any byte the prologue clears or sets


def _front_end_pokes(seed, extra=None):
    """test_hud.py's panel staging plus the two buffer pointers, which its cases pass separately."""
    return test_hud._panel_pokes(seed, {
        **test_hud._buffer_pokes(test_hud.A_SCREEN_BACK_BUFFER, test_hud.A_SCREEN_FRONT_BUFFER),
        **(extra or {})})


def test_section_reload_intro_screens():
    """Two `bsr`s: the PLAYER n screen, then the whole status panel.

    THE ORDER IS *NOT* THE ASSERTION, and saying so is the point of this docstring. Swapping the two
    calls was mutation-tested and SURVIVED: `status_panel_redraw_all` writes every panel piece to
    BOTH framebuffers, and `player_intro_screen`'s `playfield_clear` touches only rows 0..143 while
    the panel starts at row 147 — so the `screen_flip_buffers` between them exchanges two pointers
    whose buffers end up holding the same bytes either way. STATUS.md's mutation ledger carries the
    argument and names the surface that WOULD catch it (a rendered-pixel or on-target one).

    What this case does assert is that both calls happen, over the real graphics, at the addresses
    `_start` gives them — a slice that dropped one of them differs on tens of thousands of bytes.
    """
    _slice_case(ENTRY_SECTION_RELOAD_INTRO_SCREENS, ENTRY_SECTION_LOAD_ASSETS,
                _front_end_pokes(seed=0x1085a & 0xff),
                lambda lib, buf: lib.g_section_reload_intro_screens(buf), "reload intro")


def _restart_pokes(seed, alive, extra=None):
    """The prologue's whole input set: a live-or-dead entity table, live asteroid records, and every
    byte it clears or sets seeded to a value it does not produce.

    `alive` seeds BOTH record arrays' alive bytes and the six shot slots' type bytes, so a sweep one
    record short leaves a set byte standing where the original cleared it. The banner byte is seeded
    to neither 0 nor 1 for the same reason.
    """
    table = bytearray()
    for index in range(ENTITY_SLOTS):
        record = bytearray(random.Random(0x10b6e + seed + index).randbytes(ENTITY_STRIDE))
        record[ENTITY_ALIVE] = alive
        record[ENTITY_TYPE] = alive
        table += record
    asteroids = bytearray()
    for index in range(SECTION_RESTART_ASTEROID_RECORDS):
        record = bytearray(random.Random(0x17e2a + seed + index).randbytes(ENTITY_STRIDE))
        record[ENTITY_ALIVE] = alive
        asteroids += record
    # ...and one record past the ASTEROID array, at 0x18142, which nothing else in this poke set
    # touches: that is what pins its count of eighteen. The entity array gets NO such guard, because
    # the record after its twentieth IS `A_asteroid_records` — its own count is pinned instead by
    # the ship's shadow at slot 18 (`test_the_restart_prologue_leaves_the_ship_shadow_alive`), which
    # is the only slot an overrun of one could touch observably.
    asteroids += random.Random(0x2001 + seed).randbytes(ENTITY_STRIDE)

    pokes = {
        A_ENTITY_TABLE: bytes(table),
        A_ASTEROID_RECORDS: bytes(asteroids),
        A_SHOW_PREPARE_FOR_COMBAT: bytes([RESET_SEED]),
        A_DEATH_EVENT_FLAGS: bytes([RESET_SEED]),
        A_MISSILE_LAUNCH_COUNTER: bytes([RESET_SEED, RESET_SEED]),   # ...and the bomb counter beside it
        A_SQUADRON_KILL_COUNTERS: bytes([RESET_SEED] * (SQUADRON_MARKS + 1)),  # +1: a guard byte
        A_KEY_SCANCODE: bytes([RESET_SEED]),
        A_EXPLOSION_GROUP_ACTIVE_BITS: bytes([RESET_SEED]),
        A_SCROLL_FROZEN: bytes([RESET_SEED]),
        A_MOTHERSHIP_READY: bytes([RESET_SEED]),
        A_MOTHERSHIP_PENDING: bytes([RESET_SEED]),
    }
    pokes.update(extra or {})
    return _front_end_pokes(seed, pokes)


@pytest.mark.parametrize("alive", (0x00, 0x01, 0x80, 0xff))
def test_section_restart_prologue(alive):
    """0xd0 bytes of resets reaching five subsystems, plus the two front-end screens.

    The alive byte is swept because every clear is a `clr.b` on a byte whose entry value the sweeps
    must not depend on — and 0x00 going in is the case that would hide a missing clear, which is why
    it is driven beside three non-zero ones rather than instead of them.
    """
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=alive, alive=alive),
                lambda lib, buf: lib.g_section_restart_prologue(buf), f"alive={alive:#04x}")


def test_the_restart_prologue_leaves_the_ship_shadow_alive():
    """The one record the sweep does NOT kill, and it is not the last one.

    `move.w #$11,d0` + dbf covers slots 0..17; the `clr.b $17de0` after it is the GUNSIGHT's alive
    byte at slot 19, so slot 18 — the ship's shadow — keeps whatever it had. A candidate that read
    the count as nineteen, or the stray clear as "one more slot", agrees with the original on every
    other byte and differs on exactly this one. The arithmetic is asserted here as well as driven,
    because the address 0x17de0 appears in the original as a bare literal.
    """
    assert A_ENTITY_GUNSIGHT + ENTITY_ALIVE == 0x17de0
    assert A_SHIP_RECORD_SHADOW == A_ENTITY_TABLE + 18 * ENTITY_STRIDE
    assert A_ENTITY_GUNSIGHT == A_ENTITY_TABLE + 19 * ENTITY_STRIDE
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=7, alive=0xff),
                lambda lib, buf: lib.g_section_restart_prologue(buf), "shadow survives")


def test_the_restart_prologue_rewrites_the_ship_pair_last():
    """The pair's positions, sprites and heights, over records seeded to none of them.

    The two sprite longwords are ONE FRAME APART (names.txt's 0x640 stride on 0x111f4), which is
    what this holds against them being two unrelated literals — and the height pair is written from
    a SECOND `lea` of the same record after the position pair, so a candidate that folded the two
    blocks into one still has to put the same bytes at the same four offsets.
    """
    seeded = bytes([RESET_SEED]) * ENTITY_STRIDE
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=9, alive=1,
                               extra={A_PLAYER_RECORD: seeded + seeded}),
                lambda lib, buf: lib.g_section_restart_prologue(buf), "ship pair")


# ========================================================= section_start_prefill @ 0x10c4e

PREFILL_MAX_INSNS = 20_000_000


@functools.lru_cache(maxsize=None)
def _unpacked_map(level):
    """The map the game gets, produced by the ORIGINAL'S OWN unpacker (as test_scroll.py does).

    Cached because every prefill case wants the same level, and each miss is a full oracle run of
    `map_rle_decompress` plus a 39 KB read off the disk.
    """
    image = harness.make_image({A_TILE_SET_BASE: (DISK / level).read_bytes()})
    final, _writes, _regs = emu.run(image, ENTRY_MAP_RLE_DECOMPRESS, {})
    return bytes(final[A_MAP_UNPACKED:A_MAP_UNPACKED + MAP_UNPACKED_BYTES])


def _prefill_pokes(section, map_ptr, page, column, asteroid, seed):
    """All eight pages, the framebuffer and the column workspace seeded, then the real map and tile
    set poked over regions no seed covers.

    THE WORKSPACE IS AN OUTPUT TOO — the tile decoder fills it and the emitter drains it — and it
    abuts page 0 (`A_scroll_col_workspace` + its length is `A_backdrop_page0`), so its upper guard
    band and that page's span overlap. `abi.seed_spans` merges them rather than letting the later
    poke silently win, which is the whole reason the seeding goes through it.

    THE LAST PAGE HAS NO UPPER GUARD BAND, and it cannot: page 7 ends at exactly `A_map_unpacked`,
    so the map poked in below wins those sixteen bytes. The map's own bytes are a distinguishable
    non-zero neighbour, so an over-run past page 7 still differs — but it differs against real data
    rather than against a seed, and the assertion below is what stops that adjacency changing
    silently.
    """
    assert PREFILL_PAGES[-1] + PLAYFIELD_BYTES == A_MAP_UNPACKED, (
        "the last page no longer abuts the unpacked map — re-check this case's guard bands")
    pokes = abi.seed_spans(seed, tuple((base, base + PLAYFIELD_BYTES) for base in PREFILL_PAGES)
                           + ((abi.SCREEN_BACK, abi.SCREEN_BACK + PLAYFIELD_BYTES),
                              (A_SCROLL_COL_WORKSPACE, A_SCROLL_COL_WORKSPACE + WORKSPACE_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[A_MAP_UNPACKED] = _unpacked_map("LEV1.MAP")
    pokes[A_TILE_SET_BASE] = (DISK / "ZYN1.DAT").read_bytes()
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    pokes[A_MAP_PTR] = map_ptr.to_bytes(4, "big")
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes[A_MAP_PAGE] = bytes([page])
    pokes[A_MAP_COLUMN] = bytes([column])
    pokes[A_ASTEROID_SECTION_FLAG] = bytes([asteroid])
    return pokes


# The eight off-screen pages `map_page_table` names, read out of the image so a table that moved
# fails here rather than leaving eight seeded spans pointing at nothing.
PREFILL_PAGES = tuple(
    int.from_bytes(bytes(harness.BASE_IMAGE[A_MAP_PAGE_TABLE + 4 * page:
                                            A_MAP_PAGE_TABLE + 4 * page + 4]), "big")
    for page in range(MAP_PAGES))


@pytest.mark.parametrize("section", (0, 1, 7, 15))
def test_section_start_prefill_every_restart_entry(section):
    """The restart search at four sections, then 160 columns of backdrop pre-rendered.

    The search walks the word table BACKWARDS from the section's own eight-byte slot, so the section
    number decides where it starts and the map cursor decides where it stops — and the three globals
    it publishes (`map_ptr`, `map_offset`, `scroll_pos`) are all diffed. The pre-fill then drives
    160 columns through `scroll_emit_tile_column` and `scroll_emit_column_shift2` into all eight
    pages, which is the composition test for the whole scroller: every page is seeded over a full
    playfield, so a candidate that filled the wrong page, or stopped a column short, differs.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(section, A_MAP_UNPACKED, 0, 0, 0, seed=0x100 + section),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"section={section}",
                max_insns=PREFILL_MAX_INSNS)


# The rewind cases, as (map cursor, does the pre-render run?). THE PRE-RENDER IS OFF FOR THREE OF
# THEM, and that is a measurement rather than a shortcut: the rewind is decided BEFORE the pre-fill
# loop and the asteroid guard returns straight after the search publishes its three globals, so an
# asteroid run tests exactly the arithmetic these cases are about at a thousandth of the cost (~1 ms
# against ~500 ms). Two are kept full so that "the pre-fill starts from the REWOUND cursor" — which
# no other case covers, since every other one starts below the floor — still has a witness.
REWIND_CASES = ((A_MAP_UNPACKED, True),
                (A_MAP_UNPACKED + 20 * MAP_COLUMN_BYTES, False),
                (0x47b7e, True),
                (0x47b7e + 0x2d0, False),
                (A_MAP_UNPACKED + 300 * MAP_COLUMN_BYTES, False))


@pytest.mark.parametrize("map_ptr,prerender", REWIND_CASES)
def test_section_start_prefill_rewinds_past_the_floor(map_ptr, prerender):
    """The `cmp.l #$47b7e` / `sub.l #$2d0` rewind, at and either side of its edge.

    A cursor at or past the floor is pulled back twenty columns before the restart search runs, so
    the two cases at 0x47b7e and 0x47b7e + 0x2d0 are what say the comparison is `>=` and that the
    subtraction is twenty columns and not some other distance.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(4, map_ptr, 0, 0, 0 if prerender else 1, seed=map_ptr),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"map_ptr={map_ptr:#x}",
                max_insns=PREFILL_MAX_INSNS)


@pytest.mark.parametrize("page,column", ((0, 0), (1, 0), (7, 3), (7, SCROLL_PHASES - 1)))
def test_section_start_prefill_starts_mid_ring(page, column):
    """The pre-fill picks up wherever the page and column counters already are.

    Page 0 is the one that decodes a fresh tile column and advances the map; pages 1..7 re-emit the
    same workspace two pixels further along. Starting at page 7 and at the last column phase is what
    exercises both wraps — the page counter's at eight and the column's at twenty.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(0, A_MAP_UNPACKED, page, column, 0, seed=0x200 + page * 32 + column),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"page={page} column={column}",
                max_insns=PREFILL_MAX_INSNS)


def test_section_start_prefill_asteroid_section_renders_nothing():
    """`tst.b $198fd` before the loop: an asteroid section has no backdrop, so the search publishes
    its three globals and the routine returns without touching a page. The eight seeded pages coming
    back untouched is the assertion."""
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(1, A_MAP_UNPACKED, 0, 0, 1, seed=0x300),
                lambda lib, buf: lib.g_section_start_prefill(buf), "asteroid",
                max_insns=PREFILL_MAX_INSNS)


def test_section_start_prefill_publishes_the_search_result():
    """The three globals the restart search publishes, read back out of the ORACLE's final image.

    NO POISON PASS, and it is measured rather than an omission: `map_ptr` is both an input to the
    search and its output, and `map_page` / `map_column` are both the pre-fill's cursors and its
    results, so an attribution run poisons the routine's own control flow and the oracle diverges
    (`docs/agent-playbook.md` §8). This case is what stands in its place — the two derived longwords
    are checked against the cursor the search settled on, so a candidate that published the cursor
    and left the other two alone fails here even though both are otherwise diffed against a
    destination that happens to hold the right bytes.
    """
    pokes = _prefill_pokes(4, A_MAP_UNPACKED + 300 * MAP_COLUMN_BYTES, 0, 0, 1, seed=0x400)
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_SECTION_START_PREFILL, {},
                                    stop_pc=STOP_SECTION_START_PREFILL,
                                    max_insns=PREFILL_MAX_INSNS)
    cursor = int.from_bytes(bytes(final[A_MAP_PTR:A_MAP_PTR + 4]), "big")
    offset = int.from_bytes(bytes(final[A_MAP_OFFSET:A_MAP_OFFSET + 4]), "big")
    scroll_pos = int.from_bytes(bytes(final[A_SCROLL_POS:A_SCROLL_POS + 4]), "big")
    assert offset == cursor - A_MAP_UNPACKED, "map_offset is not the cursor's offset into the map"
    assert scroll_pos == (offset // MAP_COLUMN_BYTES) * SCROLL_PHASE_STEP, (
        "scroll_pos is not the column index times one cell's bytes")


# ============================================================ the slices, and the gaps between them

# Every slice's range, and every GAP between them with the reason it is a gap. The seven slices are
# checkpoint runs and STATUS.md explains each gap in prose; this table is the same claim in a form a
# test can walk, so a slice cannot be silently narrowed and a gap cannot silently grow.
SLICES = (
    (ENTRY_BOOT_ENTER_SUPERVISOR, STOP_BOOT_ENTER_SUPERVISOR),
    (ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR),
    (ENTRY_BOOT_LOAD_TITLE_ASSETS, STOP_BOOT_LOAD_TITLE_ASSETS),
    (ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED),
    (ENTRY_SECTION_RELOAD_NEEDED, STOP_SECTION_RELOAD),
    (ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS),
    (ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL),
)
GAPS = (
    (0x10010, 0x10012, "the Line-A opcode, which the oracle takes as an exception"),
    (0x1001c, 0x1002c, "the two ikbd_send_cmd calls, which spin on the unmodelled ACIA at $fffc00"),
    (0x101ba, 0x10814, "the rest of _start: more than the model's eight staged-file slots"),
    (0x1085a, 0x10862, "player_intro_screen and status_panel_redraw_all, neither ported"),
    (0x10b6e, 0x10c4e, "the same two, plus resets of globals five other subsystems own"),
)

# The two bytes the "modelled as a no-op" claim rests on, and the two `bsr`s the ACIA gap is made of.
LINE_A_HIDE_MOUSE = bytes.fromhex("a00a")
IKBD_SEND_CMD_CALLS = bytes.fromhex("103c00126100442210 3c00156100441a".replace(" ", ""))


def test_the_slices_and_their_gaps_tile_the_flow():
    """The seven ranges and the five gaps cover [0x10000, 0x10d96) exactly, in order, with no hole.

    A wrong STOP mostly fails loudly on its own (a divergent diff, or `max_insns`), so the exposure
    this closes is the TILING: nothing else says the ranges plus the declared gaps account for every
    byte between the entry and the last checkpoint. A slice narrowed by an edit, or a gap that grew
    because a stop moved, shows up here with the address rather than only in STATUS.md's prose.
    """
    spans = sorted(SLICES + tuple((lo, hi) for lo, hi, _why in GAPS))
    at = ENTRY_BOOT_ENTER_SUPERVISOR
    for lo, hi in spans:
        assert lo == at, f"the flow is not covered at {at:#x}: the next span starts at {lo:#x}"
        assert lo < hi, f"span [{lo:#x}, {hi:#x}) is empty or backwards"
        at = hi
    assert at == STOP_SECTION_START_PREFILL


def test_the_line_a_gap_really_is_the_line_a_opcode():
    """The Line-A is modelled as a no-op, and nothing but these two bytes says it is one.

    `ENTRY_PROLOGUES` below pins what each slice STANDS ON; this pins what the gaps stand on. If
    0x10010 held some other instruction the seven slices would all still pass and the no-op model
    would be wrong with no witness at all.
    """
    at = 0x10010
    assert bytes(harness.BASE_IMAGE[at:at + len(LINE_A_HIDE_MOUSE)]) == LINE_A_HIDE_MOUSE


def test_the_acia_gap_really_is_the_two_ikbd_sends():
    """...and the same for the other gap the harness cannot run: `move.b #$12,d0 / bsr ikbd_send_cmd`
    twice over, with 0x15 the second time. Sixteen bytes, so a gap that grew to swallow a real
    instruction fails here."""
    at = 0x1001c
    assert bytes(harness.BASE_IMAGE[at:at + len(IKBD_SEND_CMD_CALLS)]) == IKBD_SEND_CMD_CALLS


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_VECTOR_VBL", "include/init.h", "A_vector_vbl"),
    ("A_VECTOR_TIMER_B", "include/init.h", "A_vector_timer_b"),
    ("A_VBL_ISR", "include/init.h", "A_vbl_isr"),
    ("A_TIMER_B_ISR", "include/init.h", "A_timer_b_isr"),
    ("A_SAVED_TOS_VBL_VECTOR", "include/init.h", "A_saved_tos_vbl_vector"),
    ("SHIFTER_MODE_RESOLUTION_MASK", "include/init.h", "SHIFTER_MODE_RESOLUTION_MASK"),
    ("A_LEVEL_SECTION", "include/init.h", "A_level_section"),
    ("A_LEVEL_SECTION_LOADED", "include/init.h", "A_level_section_loaded"),
    ("A_SHOW_PREPARE_FOR_COMBAT", "include/hud.h", "A_show_prepare_for_combat"),
    ("A_ASTEROID_SECTION_FLAG", "include/init.h", "A_asteroid_section_flag"),
    ("A_MOTHERSHIP_INDEX", "include/init.h", "A_mothership_index"),
    ("A_SECTION_GROUND_TARGET_FLAG", "include/init.h", "A_section_ground_target_flag"),
    ("A_PALETTE_ASTEROID", "include/init.h", "A_palette_asteroid"),
    ("A_KEY_SCANCODE", "include/init.h", "A_key_scancode"),
    ("A_MOTHERSHIP_PENDING", "include/init.h", "A_mothership_pending"),
    ("SECTION_RESTART_SHIP_X", "include/init.h", "SECTION_RESTART_SHIP_X"),
    ("SECTION_RESTART_SHADOW_X", "include/init.h", "SECTION_RESTART_SHADOW_X"),
    ("SECTION_RESTART_SHIP_Y", "include/init.h", "SECTION_RESTART_SHIP_Y"),
    ("SECTION_RESTART_SHIP_ROWS", "include/init.h", "SECTION_RESTART_SHIP_ROWS"),
    ("SECTION_RESTART_KILL_SLOTS", "include/init.h", "SECTION_RESTART_KILL_SLOTS"),
    ("SECTION_RESTART_ASTEROID_RECORDS", "include/init.h",
     "SECTION_RESTART_ASTEROID_RECORDS"),
    ("SQUADRON_MARKS", "include/init.h", "SQUADRON_MARKS"),
    ("SECTION_RESTART_LAUNCH_STOCK", "include/init.h", "SECTION_RESTART_LAUNCH_STOCK"),
    ("SHIP_SPRITE_GAP", "include/sprite.h", "SHIP_SPRITE_GAP"),
    ("PLAYER_SHOT_SLOTS", "include/weapon.h", "PLAYER_SHOT_SLOTS"),
    ("A_ENTITY_GUNSIGHT", "include/weapon.h", "A_entity_gunsight"),
    ("A_DEATH_EVENT_FLAGS", "include/weapon.h", "A_death_event_flags"),
    ("A_MISSILE_LAUNCH_COUNTER", "include/weapon.h", "A_missile_launch_counter"),
    ("A_BOMB_LAUNCH_COUNTER", "include/weapon.h", "A_bomb_launch_counter"),
    ("A_ASTEROID_RECORDS", "include/enemy.h", "A_asteroid_records"),
    ("A_SQUADRON_KILL_COUNTERS", "include/enemy.h", "A_squadron_kill_counters"),
    ("A_EXPLOSION_GROUP_ACTIVE_BITS", "include/enemy.h", "A_explosion_group_active_bits"),
    ("A_SCROLL_FROZEN", "include/enemy.h", "A_scroll_frozen"),
    ("A_PLAYER_RECORD", "include/enemy.h", "A_player_record"),
    ("A_MOTHERSHIP_READY", "include/mothership.h", "A_mothership_ready"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_SHIP_RECORD_SHADOW", "include/player.h", "A_ship_record_shadow"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("A_PALETTE_NEXT", "include/init.h", "A_palette_next"),
    ("A_PALETTE_PER_SECTION_TABLE", "include/init.h", "A_palette_per_section_table"),
    ("SECTION_COUNT", "include/init.h", "SECTION_COUNT"),
    ("SECTION_TYPE_ASTEROID", "include/init.h", "SECTION_TYPE_ASTEROID"),
    ("SECTION_PALETTE_BYTES", "include/init.h", "SECTION_PALETTE_BYTES"),
    ("A_ALIEN_VARIANT_TABLE", "include/init.h", "A_alien_variant_table"),
    ("A_ALIEN2_VARIANT_TABLE", "include/init.h", "A_alien2_variant_table"),
    ("A_MOTHERSHIP_VARIANT_TABLE", "include/init.h", "A_mothership_variant_table"),
    ("A_MISSILE_VARIANT_TABLE", "include/init.h", "A_missile_variant_table"),
    ("A_SECTION_TYPE_TABLE", "include/init.h", "A_section_type_table"),
    ("A_ZYN_VARIANT_TABLE", "include/init.h", "A_zyn_variant_table"),
    ("A_SECTION_PALETTE_INDEX_TABLE", "include/init.h", "A_section_palette_index_table"),
    ("A_GROUND_TARGET_BY_PALETTE_TABLE", "include/init.h", "A_ground_target_by_palette_table"),
    ("A_SECTION_RESTART_TABLE", "include/init.h", "A_section_restart_table"),
    ("A_SCROLL_POS", "include/init.h", "A_scroll_pos"),
    ("A_MAP_OFFSET", "include/init.h", "A_map_offset"),
    ("A_MAP_PTR", "include/init.h", "A_map_ptr"),
    ("A_MAP_PAGE", "include/init.h", "A_map_page"),
    ("A_MAP_PAGE_PTR", "include/init.h", "A_map_page_ptr"),
    ("A_MAP_PAGE_TABLE", "include/init.h", "A_map_page_table"),
    ("A_MAP_COLUMN", "include/init.h", "A_map_column"),
    ("MAP_PAGES", "include/init.h", "MAP_PAGES"),
    ("SECTION_PREFILL_COLUMNS", "include/init.h", "SECTION_PREFILL_COLUMNS"),
    ("A_FILENAME_ALIEN_DAT", "include/init.h", "A_filename_alien_dat"),
    ("A_FILENAME_MOTHER_DAT", "include/init.h", "A_filename_mother_dat"),
    ("A_FILENAME_MISSILE_DAT", "include/init.h", "A_filename_missile_dat"),
    ("A_FILENAME_LEV_MAP", "include/init.h", "A_filename_lev_map"),
    ("A_FILENAME_ZYN_DAT", "include/init.h", "A_filename_zyn_dat"),
    ("FILENAME_ALIEN_VARIANT", "include/init.h", "FILENAME_ALIEN_VARIANT"),
    ("FILENAME_MOTHER_VARIANT", "include/init.h", "FILENAME_MOTHER_VARIANT"),
    ("FILENAME_MISSILE_VARIANT", "include/init.h", "FILENAME_MISSILE_VARIANT"),
    ("FILENAME_LEV_VARIANT", "include/init.h", "FILENAME_LEV_VARIANT"),
    ("FILENAME_ZYN_VARIANT", "include/init.h", "FILENAME_ZYN_VARIANT"),
    ("A_TILE_SET_BASE", "include/scroll.h", "A_tile_set_base"),
    ("A_MAP_UNPACKED", "include/scroll.h", "A_map_unpacked"),
    ("MAP_ROWS", "include/scroll.h", "MAP_ROWS"),
    ("MAP_COLUMNS", "include/scroll.h", "MAP_COLUMNS"),
    ("MAP_COLUMN_BYTES", "include/scroll.h", "MAP_COLUMN_BYTES"),
    ("SCROLL_PHASES", "include/scroll.h", "SCROLL_PHASES"),
    ("SCROLL_PHASE_STEP", "include/scroll.h", "SCROLL_PHASE_STEP"),
    ("A_SCROLL_PREFILL_HIDE_SCREEN", "include/scroll.h", "A_scroll_prefill_hide_screen"),
    ("A_SCROLL_COL_WORKSPACE", "include/scroll.h", "A_scroll_col_workspace"),
    ("SCROLL_COLUMN_PASSES", "include/scroll.h", "SCROLL_COLUMN_PASSES"),
    ("SCROLL_COLUMN_CELL_LONGS", "include/scroll.h", "SCROLL_COLUMN_CELL_LONGS"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("PLAYFIELD_BYTES", "include/video.h", "PLAYFIELD_BYTES"),
    ("BOOT_SCREEN_BACK", "src/init.c", "BOOT_SCREEN_BACK"),
    ("BOOT_SCREEN_FRONT", "src/init.c", "BOOT_SCREEN_FRONT"),
    ("BOOT_POWER_GAUGE_DST", "src/init.c", "BOOT_POWER_GAUGE_DST"),
    ("BOOT_SHIP_SOURCE", "src/init.c", "BOOT_SHIP_SOURCE"),
)
# Every entry here is a MID-ROUTINE address except the first — `_start` is the only one of the seven
# ../../names.txt gives an `fn` line — so the prologue is the ten bytes the slice's own first
# instructions occupy rather than a function's opening. That is what makes the pin worth having: a
# slice boundary mistyped by two bytes would enter mid-instruction and the oracle would decode
# rubbish, and this is the check that says which bytes each entry stands on.
ENTRY_PROLOGUES = {
    "ENTRY_BOOT_ENTER_SUPERVISOR": "42a73f3c00204e41dffc",
    "ENTRY_BOOT_SAVE_VBL_VECTOR": "23f900000070000195d0",
    "ENTRY_BOOT_LOAD_TITLE_ASSETS": "23fc000703000001797e",
    "ENTRY_SECTION_ADVANCE": "23fc000478ae00018242",
    "ENTRY_SECTION_RELOAD_NEEDED": "103900019913b0390001",
    "ENTRY_SECTION_LOAD_ASSETS": "103900019895488041f9",
    "ENTRY_SECTION_RELOAD_INTRO_SCREENS": "61002bca61002d5c103900019895",
    "ENTRY_SECTION_RESTART_PROLOGUE": "13fc000100019aac610028ae",
    "ENTRY_SECTION_START_PREFILL": "2a3900018242babc0004",
}
