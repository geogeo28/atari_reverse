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
ENTRY_SECTION_LOAD_ASSETS = 0x10862
STOP_SECTION_LOAD_ASSETS = 0x10b6e
# The `cmp.b #$71,d0` at 0x109de has set the flags and the `beq` at 0x109e2 has not run yet, so
# BOTH arms reach here — which is what lets the four asteroid sections verify the shared prefix
# even though the arm beyond it is unported.
STOP_SECTION_LOAD_ASSETS_PREFIX = 0x109e2
ENTRY_SECTION_START_PREFILL = 0x10c4e
STOP_SECTION_START_PREFILL = 0x10d96
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
def test_section_load_assets_prefix_of_an_asteroid_section(section):
    """The four asteroid sections' SHARED PREFIX, up to the branch that leaves this reconstruction.

    Everything before 0x109e2 is common to both arms — the two alien banks, the boss sprite, the
    missile frames — and it is driven by the same nine tables, so leaving it untested would leave a
    quarter of the sections' table lookups unexercised. The case stops at the `beq` itself, which
    both arms reach, and asserts that the reconstruction reports the arm it cannot follow rather
    than falling into the map path (which would clear `asteroid_section_flag` where the original
    sets it, and mislead `section_start_prefill` into rendering a backdrop that does not exist).
    """
    pokes = _stage(_section_files(section))
    pokes[A_LEVEL_SECTION] = bytes([section])
    info = _slice_case(ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS_PREFIX, pokes,
                       lambda lib, buf: lib.g_section_load_assets(buf), f"asteroid section={section}",
                       max_insns=SECTION_LOAD_MAX_INSNS)
    assert info["ret"] == 0, f"section {section} is an asteroid section but the map arm ran"


def test_section_load_assets_covers_both_ground_targets():
    """The two arms of `tst.b $19897` are both reached by the shipped sections.

    The ground-target graphic is chosen by a flag that is itself a table byte, so which arm a
    section takes is the level designer's and not this battery's; this is where the claim that both
    are exercised is held against the tables rather than assumed.
    """
    chosen = {_section_files(section)[-1] for section in MAP_SECTIONS}
    assert chosen == {"gndtarg1.dat", "rocket.dat"}, chosen


ASTEROID_SECTION_COUNT = 4       # measured: the section-type table's four 'q' entries


def test_asteroid_sections_are_the_unported_arm():
    """Four of the sixteen sections branch at 0x109e2 into `asteroids_load_and_build` (0x156ac).

    That routine is not reconstructed, so the arm is read-verified and no case above drives it.
    Pinned here so the count cannot drift silently: if a table changed and every section became a
    map section, MAP_SECTIONS would silently claim coverage it never had.
    """
    assert len(ASTEROID_SECTIONS) == ASTEROID_SECTION_COUNT
    assert len(MAP_SECTIONS) == SECTION_COUNT - ASTEROID_SECTION_COUNT


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
    "ENTRY_SECTION_START_PREFILL": "2a3900018242babc0004",
}
