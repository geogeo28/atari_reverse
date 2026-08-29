"""Differential tests for the status panel's blits (src/hud.c).

EVERY GRAPHIC THESE ROUTINES READ IS BSS, so every case stages the real file bytes from ../bin/disk
the way test_text.py stages the font. Against the zeroed bss each blit would write zeroes, a wrong
SOURCE address would read zeroes too, and the diff would stay empty — which is the same coverage
hole the font battery names.

The DESTINATIONS are the game's two framebuffers, and they are bss as well, so each case seeds BOTH
of them whole with noise. That does two jobs at once: it makes the blitted block visible, and it
makes a write one row or one byte outside the block a difference rather than a zero over a zero.
"""
import ctypes
import random
from pathlib import Path

import pytest

import abi
import harness
import loader
from abi import seed_spans
from harness import differential, hi_garbage, report

ENTRY_HUD_DRAW_LOGO_ANIM = 0x1452c
ENTRY_HUD_DRAW_POWERUP_ICON = 0x1459c
ENTRY_HUD_DRAW_WEAPON_ICON = 0x145da
ENTRY_DRAW_POWER_GAUGE = 0x137ca
ENTRY_DRAW_LIVES_ICONS = 0x134ca
ENTRY_DRAW_PLAYER_DIGIT_SHIFTED = 0x13568
ENTRY_DRAW_SCORE_PANEL = 0x136c8
ENTRY_STATUS_PANEL_BUILD_MASTER = 0x129aa
ENTRY_STATUS_PANEL_REDRAW_ALL = 0x135bc
ENTRY_PLAYER_INTRO_SCREEN = 0x13426
ENTRY_TITLE_SCREEN_DRAW = 0x12a28

# mirrors of include/hud.h
A_POWER_GAUGE_FRAMES = 0x607be
A_SMLOGOS_FRAMES = 0x6b46e
A_HUD_POWERUP_ICONS = 0x1931c
A_HUD_WEAPON_ICONS = 0x19330
A_POWERUP_CURSOR = 0x19905
A_POWERUP_ACTIVE_SLOT = 0x19906
A_PANEL_LOGO_FRAME = 0x1990e
A_POWER_GAUGE_DISPLAY = 0x198c3
A_SCREEN_BACK_BUFFER = 0x70300
A_SCREEN_FRONT_BUFFER = 0x78000
POWER_GAUGE_FRAMES = 4
POWER_GAUGE_ROWS = 8
POWER_GAUGE_ROW_BYTES = 32
POWERUP_ICON_ROWS = 26
POWERUP_ICON_ROW_BYTES = 16
WEAPON_ICON_ROWS = 18
WEAPON_ICON_ROW_BYTES = 8
ICON_TABLE_ENTRY_BYTES = 4

A_LIFE_ICONS = 0x6c8ae
A_ZYNAPS_LOGO = 0x6c8ee
A_HEWSON_LOGO = 0x6e0ee
A_SHOW_PREPARE_FOR_COMBAT = 0x19aac
A_MSG_PLAYER = 0x19933
A_PALETTE_FRONTEND = 0x195f8
LOGO_STRIPS = 3
LOGO_STRIP_BYTES = 0x800
HEWSON_LOGO_STRIPS = 2
HEWSON_STRIP_BYTES = 0x300
HISCORE_DIGITS_OFFSET = 0x7580
A_SCORE_PANEL_STRIP = 0x6c72e
A_PLAYER_PANEL_STRIP = 0x6c86e
A_HISCORE_PANEL_STRIP = 0x6c5ee
A_PANEL_MASTER = 0x41eae
A_LIVES = 0x1991a
A_CURRENT_PLAYER_INDEX = 0x1991b
A_PANEL_REDRAW_MASK = 0x19904
PANEL_REDRAW_LIVES_BIT = 4
LIVES_ICONS = 6
LIFE_ICON_ROWS = 8
LIFE_ICON_ROW_BYTES = 4
LIVES_FIRST_COLUMN = 0x20
LIVES_ROW_OFFSET = 0x6860
PLAYER_DIGIT_SHIFT = 4
PLAYER_DIGIT_GLYPH_BIAS = 1
PANEL_STRIP_ROWS = 8
PANEL_STRIP_ROW_BYTES = 40
PLAYER_STRIP_ROW_BYTES = 8
SCORE_STRIP_OFFSET = 0x5ed8
SCORE_DIGITS_OFFSET = 0x5e60
SCORE_RIGHTMOST_COLUMN = 0x26
PLAYER_STRIP_OFFSET = 0x7238
HISCORE_STRIP_OFFSET = 0x7598
PANEL_TOP_OFFSET = 0x5be0
PANEL_MASTER_LONGWORDS = 0x848

# mirrors of include/text.h
A_FONT_GLYPHS = 0x6be6e
GLYPH_BYTES = 0x28

# mirrors of include/score.h
A_PLAYER_SCORE_BCD = 0x195e0

# mirrors of include/highscore.h
A_HIGHSCORE_TABLE = 0x19d5a

# mirrors of include/irq.h
A_PALETTE_HW_SHADOW = 0x18fc4
A_MENU_PALETTE = 0x19f46
PALETTE_PENS = 16
PALETTE_BYTES = PALETTE_PENS * 2

# mirrors of include/video.h
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
SCREEN_BYTES = 32000
SCREEN_ROW_BYTES = 160

DISK = Path(__file__).resolve().parents[2] / "bin" / "disk"

# Where `_start` loads each file, from its own `lea` pairs: POWER.DAT at 0x1008e, SWEAP.DAT at
# 0x1025a, SSWEAP.DAT at 0x10270, SMLOGOS.DAT at 0x10286. The two icon banks have no C constant
# because no reconstructed routine names them — the game reaches them only through the pointer
# tables in the .PRG's own text — so `test_icon_tables_point_into_the_staged_banks` below pins these
# two addresses against those pointers rather than leaving them as the test's private guess.
A_SWEAP_ICONS = 0x6a8ee
A_SSWEAP_ICONS = 0x6b10e

STAGED_GRAPHICS = {
    A_POWER_GAUGE_FRAMES: "POWER.DAT",
    A_SMLOGOS_FRAMES: "SMLOGOS.DAT",
    A_SWEAP_ICONS: "SWEAP.DAT",
    A_SSWEAP_ICONS: "SSWEAP.DAT",
    A_LIFE_ICONS: "LIFEGRA.DAT",
    A_FONT_GLYPHS: "EXTCHARS.DAT",
    A_ZYNAPS_LOGO: "ZYNLOGO.DAT",
    A_HEWSON_LOGO: "HEWLOGO.DAT",
}

# THE THREE PANEL STRIPS ARE NOT A FILE. `_start` stamps STATUS.PI1 into the screen at row 147 and
# then copies three rectangles of it back out (0x10564..0x105c4) — so their bytes are the panel
# image's, read at the very screen offset each strip is later stamped to. Deriving them here the
# same way keeps one source of truth: a strip staged from anywhere else would be this battery
# inventing panel graphics, and `test_the_strips_are_cut_from_the_panel_image` says so out loud.
PANEL_IMAGE = (DISK / "STATUS.PI1").read_bytes()


def _panel_strip(offset, rows, row_bytes):
    """The rectangle `_start` carves out of the stamped panel image at buffer offset `offset`."""
    start = offset - PANEL_TOP_OFFSET
    return b"".join(PANEL_IMAGE[start + row * SCREEN_ROW_BYTES:
                                start + row * SCREEN_ROW_BYTES + row_bytes]
                    for row in range(rows))


STAGED_STRIPS = {
    A_SCORE_PANEL_STRIP: (SCORE_STRIP_OFFSET, PANEL_STRIP_ROW_BYTES),
    A_PLAYER_PANEL_STRIP: (PLAYER_STRIP_OFFSET, PLAYER_STRIP_ROW_BYTES),
    A_HISCORE_PANEL_STRIP: (HISCORE_STRIP_OFFSET, PANEL_STRIP_ROW_BYTES),
}

harness._lib.g_hud_draw_logo_anim.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_hud_draw_logo_anim.restype = None
harness._lib.g_hud_draw_powerup_icon.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_hud_draw_powerup_icon.restype = None
harness._lib.g_hud_draw_weapon_icon.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_hud_draw_weapon_icon.restype = None
harness._lib.g_draw_power_gauge.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_power_gauge.restype = None
harness._lib.g_draw_lives_icons.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_lives_icons.restype = None
harness._lib.g_draw_player_digit_shifted.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                                     ctypes.c_uint32]
harness._lib.g_draw_player_digit_shifted.restype = None
harness._lib.g_draw_score_panel.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_score_panel.restype = None
harness._lib.g_status_panel_build_master.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_status_panel_build_master.restype = None
harness._lib.g_status_panel_redraw_all.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_status_panel_redraw_all.restype = None
harness._lib.g_player_intro_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_player_intro_screen.restype = None
harness._lib.g_title_screen_draw.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_title_screen_draw.restype = None

FUZZ_CHUNKS = 4


def _read_graphics():
    """Every graphic these routines read, at the address `_start` puts it at: the .DAT files it
    loads, and the three panel strips it carves out of STATUS.PI1."""
    pokes = {addr: (DISK / name).read_bytes() for addr, name in STAGED_GRAPHICS.items()}
    pokes.update({addr: _panel_strip(offset, PANEL_STRIP_ROWS, row_bytes)
                  for addr, (offset, row_bytes) in STAGED_STRIPS.items()})
    return pokes


# Read ONCE at import, not per case. `_panel_pokes` runs for every one of this battery's ~1,700
# differential cases and the bytes are immutable for the process's life; re-reading them there cost
# 13,464 file opens and 27 MB of I/O for 17 KB of distinct data. Callers `dict.update()` this into
# a fresh poke dict, so nothing aliases it.
GRAPHICS_POKES = _read_graphics()


def _panel_pokes(seed, extra=None, extra_spans=()):
    """Noise over both whole framebuffers, plus the real graphics and whatever a case adds.

    Guard bands either side, because most of what surrounds a framebuffer is bss: a candidate
    writing one row too far would put zeroes over zeroes and the diff would stay empty.
    """
    spans = [(A_SCREEN_BACK_BUFFER, A_SCREEN_BACK_BUFFER + SCREEN_BYTES),
             (A_SCREEN_FRONT_BUFFER, A_SCREEN_FRONT_BUFFER + SCREEN_BYTES), *extra_spans]
    pokes = seed_spans(seed, spans, guard=abi.GUARD_BYTES)
    pokes.update(GRAPHICS_POKES)
    pokes.update(extra or {})
    return pokes


def _sign_extend_byte(value):
    return value - 0x100 if value & 0x80 else value


def _icon_pointer(table, cursor):
    """The longword `movea.l (a2,d0.w),a2` loads for `cursor`, out of the image's own table.

    `ext.w` then `lsl.w #2` then a WORD index, so the arithmetic wraps in 16 bits and a cursor at or
    above 0x80 reads below the table — this mirrors that rather than assuming 4*cursor.
    """
    entry = (_sign_extend_byte(cursor) * ICON_TABLE_ENTRY_BYTES) & 0xffff
    delta = entry - 0x10000 if entry & 0x8000 else entry
    address = (table + delta) & 0xffffffff
    return int.from_bytes(bytes(harness.BASE_IMAGE[address:address + 4]), "big")


def _icon_cursors_in_the_loaded_program(table, rows, row_bytes):
    """Every cursor byte whose blit reads inside the LOADED PROGRAM, and only those.

    That set is far wider than the icons the bar shows — past the last entry the table runs into its
    neighbour and a negative cursor indexes back into the .PRG's text — but it is bounded at both
    ends, and both bounds are the harness's rather than the game's:

      * ABOVE the image there is nothing to read. The oracle would fault on unmapped memory and the
        candidate would read host heap, so the case would test the harness, not the routine.
      * BELOW `loader.LOAD_BASE` the image is not the program. The 68000 exception vectors live
        there and the oracle SYNTHESISES them — cursor 0x5c fetches a pointer of 0, and the vectors
        the oracle then served differ from the candidate's zeroed image byte for byte. That is a
        differential the routine has nothing to do with. The harness's poked input block at 0x600 is
        below the base for the same reason.

    STATUS.md records how many byte values each bound removes.
    """
    span = rows * row_bytes
    pointers = {cursor: _icon_pointer(table, cursor) for cursor in range(0x100)}
    return [cursor for cursor, pointer in pointers.items()
            if loader.LOAD_BASE <= pointer and pointer + span <= harness.OS_IMAGE_SIZE]


POWERUP_CURSORS = _icon_cursors_in_the_loaded_program(
    A_HUD_POWERUP_ICONS, POWERUP_ICON_ROWS, POWERUP_ICON_ROW_BYTES)
WEAPON_CURSORS = _icon_cursors_in_the_loaded_program(
    A_HUD_WEAPON_ICONS, WEAPON_ICON_ROWS, WEAPON_ICON_ROW_BYTES)


# =================================================================================================
# hud_draw_logo_anim @ 0x1452c
# =================================================================================================

def _logo_case(frame_byte, seed=0, poison=False):
    pokes = _panel_pokes(seed, {A_PANEL_LOGO_FRAME: bytes([frame_byte])})
    diffs, _ = differential(
        ENTRY_HUD_DRAW_LOGO_ANIM, {"_pokes": pokes},
        lambda lib, buf: lib.g_hud_draw_logo_anim(buf), poison=poison)
    assert not diffs, f"frame_byte={frame_byte:#x}\n{report(diffs)}"


@pytest.mark.parametrize("frame_byte", (0, 1, 2, 3, 0x7f, 0x80, 0xfe, 0xff))
def test_logo_anim_toggles_then_masks(frame_byte):
    """The byte is EOR'd with 1 and then read back, so the frame drawn is the new one — and it is
    re-masked with `and.b #$1` afterwards, which is the only thing bounding a byte nothing else
    clamps. Both halves are driven here: 0 and 1 are the values the game holds, and the six others
    are what a stray write would leave, where dropping either the toggle or the mask diverges."""
    _logo_case(frame_byte, seed=frame_byte)


def test_logo_anim_frame_byte_is_written_back():
    """The toggled byte is an OUTPUT as well as an input, and it is in the diffed image."""
    _logo_case(0, seed=5)
    _logo_case(1, seed=5)


@pytest.mark.parametrize("frame_byte", (0, 1))
def test_logo_anim_attribution(frame_byte):
    """Poison every byte the blit writes. The source is five 8-byte COLUMNS 0x100 apart rather than
    one 40-byte run, so a candidate that read the row straight through would leave four fifths of
    each row canary."""
    _logo_case(frame_byte, seed=17, poison=True)


# =================================================================================================
# hud_draw_powerup_icon @ 0x1459c
# =================================================================================================

def _powerup_case(cursor, seed=0, poison=False):
    pokes = _panel_pokes(seed, {A_POWERUP_CURSOR: bytes([cursor])})
    diffs, _ = differential(
        ENTRY_HUD_DRAW_POWERUP_ICON, {"_pokes": pokes},
        lambda lib, buf: lib.g_hud_draw_powerup_icon(buf), poison=poison)
    assert not diffs, f"cursor={cursor:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_powerup_icon_every_reachable_cursor(chunk):
    """Every cursor byte whose pointer stays in the loaded program, sharded four ways.

    That set is much wider than the five icons the bar shows: past the fifth entry the table runs
    straight into the weapon table beside it, and a negative cursor indexes back into the .PRG's
    text. Both are what `ext.w` + `lsl.w #2` do, and both are driven rather than avoided.
    """
    for cursor in POWERUP_CURSORS[chunk::FUZZ_CHUNKS]:
        _powerup_case(cursor, seed=cursor)


@pytest.mark.parametrize("cursor", (0, 4))
def test_powerup_icon_attribution(cursor):
    """Poison all 26 rows in both buffers: a candidate drawing 25 stays canary on the last."""
    _powerup_case(cursor, seed=23, poison=True)


# =================================================================================================
# hud_draw_weapon_icon @ 0x145da
# =================================================================================================

def _weapon_case(cell, slot, seed=0, poison=False):
    pokes = _panel_pokes(seed, {A_POWERUP_ACTIVE_SLOT: bytes([slot])})
    diffs, _ = differential(
        ENTRY_HUD_DRAW_WEAPON_ICON, {"d0": cell, "_pokes": pokes},
        lambda lib, buf: lib.g_hud_draw_weapon_icon(buf, cell), poison=poison)
    assert not diffs, f"cell={cell:#x} slot={slot:#x}\n{report(diffs)}"


# TWO cell values, not three: the cell is a `tst.b`, so 1 and 0xff take the same arm and write
# byte-identical output for every slot. That the test is of the low BYTE — that 0xff is a right cell
# and 0xffffff00 is a left one — is `test_weapon_icon_cell_is_a_byte_test` below, which needs one
# case rather than 209.
@pytest.mark.parametrize("cell", (0, 1))
@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_weapon_icon_every_reachable_slot(chunk, cell):
    """Both cells, over every slot byte whose pointer stays in the loaded program.

    The two cells are 16 bytes apart — 32 pixels — and the glyph is only 8 bytes wide, so a
    candidate that put the right-hand cell at the wrong offset would leave the left one intact and
    still differ. The shipped table holds six pointers and the two longwords after it are
    instructions, so the reachable set stops well short of 256.
    """
    for slot in WEAPON_CURSORS[chunk::FUZZ_CHUNKS]:
        _weapon_case(cell, slot, seed=slot + cell)


def test_weapon_icon_cell_is_a_byte_test():
    """`tst.b d0` — only the low byte chooses the cell, so junk above it must not move the glyph,
    and a low byte of 0 must pick the left cell however loud the rest of D0 is."""
    rng = random.Random(ENTRY_HUD_DRAW_WEAPON_ICON)
    for cell in (0, 1, 0xff):
        _weapon_case(hi_garbage(rng, cell), 0, seed=cell)
    _weapon_case(0xffffff00, 0, seed=3)


@pytest.mark.parametrize("cell", (0, 1))
def test_weapon_icon_attribution(cell):
    """Poison all 18 rows in both buffers."""
    _weapon_case(cell, 1, seed=31, poison=True)


def test_icon_tables_point_into_the_staged_banks():
    """The five power-up icons and the six weapon glyphs land inside the files this battery stages.

    THIS IS WHAT PINS `A_SWEAP_ICONS` AND `A_SSWEAP_ICONS`, which no C constant carries: the
    differential cannot see a wrong staging address, because both sides read the same image. The
    game's own pointer table can — a bank staged anywhere else would leave every shipped pointer
    outside the bytes that were staged.
    """
    for table, count, base, name in ((A_HUD_POWERUP_ICONS, 5, A_SWEAP_ICONS, "SWEAP.DAT"),
                                     (A_HUD_WEAPON_ICONS, 6, A_SSWEAP_ICONS, "SSWEAP.DAT")):
        end = base + len(GRAPHICS_POKES[base])
        for index in range(count):
            pointer = _icon_pointer(table, index)
            assert base <= pointer < end, (
                f"{name} icon {index} points at {pointer:#x}, outside the staged "
                f"[{base:#x}, {end:#x})")


# =================================================================================================
# draw_power_gauge @ 0x137ca
# =================================================================================================

# `ext.w` + `mulu.w #$100` on a byte at or above 0x80 puts the frame 0xff00xx bytes past the table,
# far outside the image, so the negative half of the byte cannot be a case — the oracle would read
# unmapped memory. The positive half is complete: 0..3 select a frame and 4..0x7f all clamp.
POWER_GAUGE_MAX_LEVEL = 0x7f


def _gauge_case(level, back=A_SCREEN_BACK_BUFFER, front=A_SCREEN_FRONT_BUFFER, seed=0,
                poison=False):
    pokes = _panel_pokes(seed, {A_POWER_GAUGE_DISPLAY: bytes([level]),
                                A_SCREEN_BACK: back.to_bytes(4, "big"),
                                A_SCREEN_FRONT: front.to_bytes(4, "big")})
    diffs, _ = differential(
        ENTRY_DRAW_POWER_GAUGE, {"_pokes": pokes},
        lambda lib, buf: lib.g_draw_power_gauge(buf), poison=poison)
    assert not diffs, f"level={level:#x} back={back:#x} front={front:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_power_gauge_every_level_the_byte_can_hold(chunk):
    """0 through 0x7f, sharded four ways — the whole half of the byte whose frame is in the image.

    The clamp is the point: it is a SIGNED compare against 4 and it WRITES THE LEVEL BACK, so 4 and
    everything above it is both drawn as frame 3 and stored as 3, and that store is in the diff.
    """
    for level in range(chunk, POWER_GAUGE_MAX_LEVEL + 1, FUZZ_CHUNKS):
        _gauge_case(level, seed=level)


def test_power_gauge_reads_the_buffer_pointers():
    """The one panel routine that takes its destinations from 0x1797e/0x17982 rather than carrying
    them as literals — so the two buffers are swapped here, and drawn into a third that is neither.
    A candidate holding the addresses as constants would agree on the first case alone."""
    _gauge_case(1, back=A_SCREEN_FRONT_BUFFER, front=A_SCREEN_BACK_BUFFER, seed=41)
    _gauge_case(2, back=A_SCREEN_BACK_BUFFER + SCREEN_BYTES, front=A_SCREEN_FRONT_BUFFER, seed=42)


@pytest.mark.parametrize("level", (0, 3))
def test_power_gauge_attribution(level):
    """Poison all 8 rows in both buffers.

    ONLY THE NON-CLAMPING LEVELS CAN TAKE THIS PASS, and `make guarded` is what said so. The canary
    is the final value inverted; a level of 4 or more is CLAMPED and so written back as 3, and the
    poisoned byte is then 0xfc — negative, which puts the frame 0xff00xx bytes outside the image.
    `make test` passed that case green because there was no image there to differ. Levels 0..3 are
    not written back at all, so they are not poisoned and the pass is sound for them.
    """
    _gauge_case(level, seed=53, poison=True)


# =================================================================================================
# draw_lives_icons @ 0x134ca
# =================================================================================================

def _lives_case(lives, mask=0xff, seed=0, poison=False):
    pokes = _panel_pokes(seed, {A_LIVES: bytes([lives]), A_PANEL_REDRAW_MASK: bytes([mask])})
    diffs, _ = differential(
        ENTRY_DRAW_LIVES_ICONS, {"_pokes": pokes},
        lambda lib, buf: lib.g_draw_lives_icons(buf), poison=poison)
    assert not diffs, f"lives={lives:#x} mask={mask:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_lives_every_count(chunk):
    """All 256 values the lives byte can hold, sharded four ways.

    Exhaustive because the full/empty choice is a SIGNED BYTE compare of `lives - 1` against the
    slot's 1-based number, and every fork of it is a single value: 0 lives underflows to -1 and
    leaves every slot empty, 1 life still leaves them all empty (the ship in play is not a spare),
    7 fills all six, and 0x80 through 0xff are negative and empty again.
    """
    for lives in range(chunk, 0x100, FUZZ_CHUNKS):
        _lives_case(lives, seed=lives)


@pytest.mark.parametrize("mask", (0x00, 0x10, 0xff, 0xef, 0xa5))
def test_lives_clears_only_its_own_panel_bit(mask):
    """`bclr #4` — the other seven bits must come back untouched, which a candidate STORING zero
    instead of clearing one bit would not manage."""
    _lives_case(4, mask=mask, seed=mask)


@pytest.mark.parametrize("lives", (0, 2, 4, 7))
def test_lives_attribution(lives):
    """Poison every byte the six slots write in both buffers, plus the panel mask. A candidate
    drawing five icons, or writing only one buffer, stays canary on what it skipped."""
    _lives_case(lives, seed=61, poison=True)


# =================================================================================================
# draw_player_digit_shifted @ 0x13568
# =================================================================================================

# The two cells the game draws into (`lea $7f238` and `lea $77538`, the panel's PLAYER strip in each
# buffer), plus one that is neither — the destination is A0 and the routine cares about nothing
# else. All three are EVEN: the routine reads and writes WORDS, and a 68000 faults on an odd one.
PLAYER_DIGIT_CELLS = (A_SCREEN_FRONT_BUFFER + PLAYER_STRIP_OFFSET,
                      A_SCREEN_BACK_BUFFER + PLAYER_STRIP_OFFSET,
                      A_SCREEN_FRONT_BUFFER + PLAYER_STRIP_OFFSET + 2)


def _player_digit_case(player, cell, seed=0, poison=False):
    pokes = _panel_pokes(seed, {A_CURRENT_PLAYER_INDEX: bytes([player])})
    diffs, _ = differential(
        ENTRY_DRAW_PLAYER_DIGIT_SHIFTED, {"a0": cell, "_pokes": pokes},
        lambda lib, buf: lib.g_draw_player_digit_shifted(buf, cell), poison=poison)
    assert not diffs, f"player={player:#x} cell={cell:#x}\n{report(diffs)}"


def _player_indices_in_the_image():
    """Every player index whose glyph is inside the image, and only those.

    The glyph number is `player + 1` added as a BYTE, then `ext.w`, then `mulu.w #$28` — and the
    multiply is UNSIGNED, so a glyph number with bit 7 set scales 0xff80..0xffff rather than -128..-1
    and lands about 2.6 MB past the font. `make guarded` is what found that: `make test` passed those
    indices green because neither side had an image there to differ.

    So the reachable set is `player + 1 <= 0x7f` — 0..0x7e, plus 0xff, whose byte add wraps to glyph
    0. The game writes 0 and 1. STATUS.md records the 128 indices this leaves undriven (0x7f..0xfe).
    """
    largest_positive_glyph = 0x7f     # the last number `ext.w` leaves with bit 15 clear
    return [player for player in range(0x100)
            if ((player + 1) & 0xff) <= largest_positive_glyph]


PLAYER_DIGIT_INDICES = _player_indices_in_the_image()


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_player_digit_every_index(chunk):
    """Every player index whose glyph stays in the image, sharded four ways.

    The byte add is the point: 0xff wraps to glyph 0 rather than reaching glyph 0x100, and 0x7e —
    the last index here — reaches glyph 0x7f, which is 79 glyphs past the font's 48 and reads the
    bss behind it. Both are what the instructions do and both are driven.
    """
    for player in PLAYER_DIGIT_INDICES[chunk::FUZZ_CHUNKS]:
        _player_digit_case(player, PLAYER_DIGIT_CELLS[0], seed=player)


@pytest.mark.parametrize("cell", PLAYER_DIGIT_CELLS)
def test_player_digit_every_cell(cell):
    """Both of the game's cells and one that is neither — A0 is the whole of the destination."""
    for player in (0, 1):
        _player_digit_case(player, cell, seed=cell + player)


def test_player_digit_shift_leaves_the_background():
    """THE MASK WORD STARTS AT 0xffff, not at 0: the glyph's AND byte goes into its low half and the
    rotate carries four ones into the top nibble, so the four pixels the glyph does not cover keep
    the background. Over a NOISY cell a candidate that started the mask from `clr.w` would clear
    them instead, and the noise is what makes that a difference."""
    for seed in (71, 72, 73):
        _player_digit_case(0, PLAYER_DIGIT_CELLS[0], seed=seed)


@pytest.mark.parametrize("player", (0, 1))
def test_player_digit_attribution(player):
    """Poison all eight rows times four planes."""
    _player_digit_case(player, PLAYER_DIGIT_CELLS[0], seed=83, poison=True)


# =================================================================================================
# draw_score_panel @ 0x136c8
# =================================================================================================

# The two buffers the game passes in A6, and a third that is neither.
SCORE_PANEL_BUFFERS = (A_SCREEN_BACK_BUFFER, A_SCREEN_FRONT_BUFFER, abi.SCRATCH)


def _score_panel_case(buffer, score=None, seed=0, poison=False):
    extra = {} if score is None else {A_PLAYER_SCORE_BCD: score.to_bytes(4, "big")}
    spans = () if buffer in (A_SCREEN_BACK_BUFFER, A_SCREEN_FRONT_BUFFER) \
        else ((buffer, buffer + SCREEN_BYTES),)
    pokes = _panel_pokes(seed, extra, extra_spans=spans)
    diffs, _ = differential(
        ENTRY_DRAW_SCORE_PANEL, {"a6": buffer, "_pokes": pokes},
        lambda lib, buf: lib.g_draw_score_panel(buf, buffer), poison=poison)
    assert not diffs, f"buffer={buffer:#x} score={score}\n{report(diffs)}"


@pytest.mark.parametrize("buffer", SCORE_PANEL_BUFFERS)
def test_score_panel_every_buffer(buffer):
    """A6 is the whole of the destination — both framebuffers and one that is neither."""
    _score_panel_case(buffer, seed=buffer & 0xff)


@pytest.mark.parametrize("score", (0x00000000, 0x00000001, 0x12345678, 0x99999999, 0xffffffff))
def test_score_panel_draws_the_score(score):
    """The strip and then the eight digits, which the routine reaches by FALLING THROUGH into
    draw_bcd_number rather than calling it — so the digits are part of this routine's diff."""
    _score_panel_case(A_SCREEN_BACK_BUFFER, score=score, seed=score & 0xff)


def test_score_panel_attribution():
    """Poison the strip's eight rows and all eight digit cells at once."""
    _score_panel_case(A_SCREEN_FRONT_BUFFER, score=0x24681357, seed=97, poison=True)


# =================================================================================================
# status_panel_build_master @ 0x129aa
# =================================================================================================

PANEL_MASTER_BYTES = PANEL_MASTER_LONGWORDS * 4


def _build_master_case(seed=0, poison=False):
    pokes = _panel_pokes(seed,
                         extra_spans=((A_PANEL_MASTER, A_PANEL_MASTER + PANEL_MASTER_BYTES),))
    diffs, _ = differential(
        ENTRY_STATUS_PANEL_BUILD_MASTER, {"_pokes": pokes},
        lambda lib, buf: lib.g_status_panel_build_master(buf), poison=poison)
    assert not diffs, f"seed={seed}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (101, 102, 103))
def test_build_master_stamps_then_snapshots(seed):
    """Three strips into the front buffer and then 53 rows of it copied to the master.

    THE SNAPSHOT MUST SEE THE STAMPS: the master is taken from row 147 downwards and all three
    strips land inside that band, so a candidate that snapshotted first, or stamped into the wrong
    buffer, differs in the master as well as on screen. The master's own bytes are seeded with noise
    and a guard band, because it is bss and a short copy would otherwise leave zeroes where the
    oracle also left zeroes.
    """
    _build_master_case(seed=seed)


def test_build_master_attribution():
    """Poison all 8480 master bytes and the three stamped strips."""
    _build_master_case(seed=104, poison=True)


def test_the_strips_are_cut_from_the_panel_image():
    """`_start` carves each strip out of the panel image at the screen offset the strip is later
    stamped back to, so a strip and the panel row under it are THE SAME BYTES.

    That is what makes staging them from STATUS.PI1 evidence rather than assertion, and it is why
    the panel image's own length is checked here: it must be exactly the master snapshot's, or the
    rectangles cut below would come from somewhere the panel does not cover.
    """
    assert len(PANEL_IMAGE) == PANEL_MASTER_BYTES, (
        f"STATUS.PI1 is {len(PANEL_IMAGE)} bytes but the master snapshot is {PANEL_MASTER_BYTES}")
    for addr, (offset, row_bytes) in STAGED_STRIPS.items():
        start = offset - PANEL_TOP_OFFSET
        last = start + (PANEL_STRIP_ROWS - 1) * SCREEN_ROW_BYTES + row_bytes
        assert 0 <= start and last <= len(PANEL_IMAGE), (
            f"the strip at {addr:#x} is cut from [{start}, {last}), outside the panel image")
        assert len(_panel_strip(offset, PANEL_STRIP_ROWS, row_bytes)) == PANEL_STRIP_ROWS * row_bytes


# =================================================================================================
# The three composers. Each is made of routines that already have batteries of their own, so these
# cases are about the COMPOSITION: which buffer each piece goes into, what order they run in, and
# the state bytes the composer sets between them.
#
# NONE OF THEM TAKES A POISON PASS, and each refusal is measured rather than assumed:
#
#   * `player_intro_screen` and `title_screen_draw` end in `screen_flip_buffers`, which WRITES the
#     two buffer pointers — so the pass would poison the very longword the routine reads its draw
#     buffer from, and the re-run draws at a canary address. Measured: a bus error in the candidate.
#   * `status_panel_redraw_all` does not flip, but `draw_power_gauge` inside it WRITES the clamped
#     level back to A_POWER_GAUGE_DISPLAY and then indexes the frame table with it. The canary is
#     the final value inverted, and every value that byte can end on is 0..3 — so the canary is
#     always 0xfc..0xff, NEGATIVE, and the frame lands 0xff00xx bytes outside the image.
#
# What the pass would have bought is bought by the pieces: draw_char, draw_bcd_number,
# draw_text_record, screen_clear, blit_graphic_block, playfield_clear and all eight leaves above
# have their own poison cases, and the ordering cases below fail on a candidate that writes the
# right bytes in the wrong place or the wrong order.
# =================================================================================================

def _buffer_pokes(back, front):
    return {A_SCREEN_BACK: back.to_bytes(4, "big"), A_SCREEN_FRONT: front.to_bytes(4, "big")}


# =================================================================================================
# status_panel_redraw_all @ 0x135bc
# =================================================================================================

def _redraw_all_case(seed=0, back=A_SCREEN_BACK_BUFFER, front=A_SCREEN_FRONT_BUFFER, extra=None):
    spans = [(buffer, buffer + SCREEN_BYTES) for buffer in (back, front)
             if buffer not in (A_SCREEN_BACK_BUFFER, A_SCREEN_FRONT_BUFFER)]
    pokes = _panel_pokes(seed, {**_buffer_pokes(back, front), **(extra or {})}, extra_spans=spans)
    diffs, _ = differential(
        ENTRY_STATUS_PANEL_REDRAW_ALL, {"_pokes": pokes},
        lambda lib, buf: lib.g_status_panel_redraw_all(buf))
    assert not diffs, f"seed={seed} back={back:#x} front={front:#x}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (111, 112))
def test_redraw_all_shipped_state(seed):
    """The whole panel from the state the .PRG boots with."""
    _redraw_all_case(seed=seed)


def test_redraw_all_moves_only_the_half_that_reads_the_pointers():
    """A THIRD BUFFER, which is the only case that separates the two halves.

    The score panel and the hi-score strip take their destination from 0x1797e/0x17982; the PLAYER
    strip, its shifted digit, and the logo / power-up / weapon / lives blits all carry absolute RAM
    (`lea $7f238.l,a0` @ 0x135ca and `lea $77538.l,a0` @ 0x135f2 for the player strip alone). So
    pointing a pointer at somewhere that is neither framebuffer must move exactly the first group.

    SWAPPING THE PAIR CANNOT SHOW THAT — it is symmetric across the two literals, so a candidate
    that ran the whole routine off the pointers writes the same two addresses in the other order and
    the diff stays empty. This case caught exactly that defect in `redraw_player_strip`.
    """
    _redraw_all_case(seed=113, back=A_SCREEN_FRONT_BUFFER, front=A_SCREEN_BACK_BUFFER)
    _redraw_all_case(seed=114, back=abi.SCRATCH, front=A_SCREEN_FRONT_BUFFER)
    _redraw_all_case(seed=115, back=A_SCREEN_BACK_BUFFER, front=abi.SCRATCH)


@pytest.mark.parametrize("level,lives,player,logo,cursor", (
    (0, 3, 0, 0, 0),
    (3, 6, 1, 1, 4),
    (9, 0, 1, 0, 2),
    (2, 0xff, 0xff, 1, 1),
))
def test_redraw_all_every_piece_reads_its_own_state(level, lives, player, logo, cursor):
    """One case per piece of state the panel shows, all moved at once: the gauge level (including
    one that clamps), the lives count (including 0 and a negative byte), the player index, the logo
    animation frame and the power-up cursor."""
    _redraw_all_case(seed=level + lives, extra={
        A_POWER_GAUGE_DISPLAY: bytes([level]), A_LIVES: bytes([lives]),
        A_CURRENT_PLAYER_INDEX: bytes([player]), A_PANEL_LOGO_FRAME: bytes([logo]),
        A_POWERUP_CURSOR: bytes([cursor])})


@pytest.mark.parametrize("score,hiscore", ((0x00000000, 0x00100000),
                                           (0x12345678, 0x99999999),
                                           (0x00000001, 0x00000000)))
def test_redraw_all_draws_both_numbers(score, hiscore):
    """The score comes from A_PLAYER_SCORE_BCD and the hi-score from the FIRST ENTRY of the
    high-score table, at two different columns and two different rows in both buffers."""
    _redraw_all_case(seed=score & 0xff, extra={
        A_PLAYER_SCORE_BCD: score.to_bytes(4, "big"),
        A_HIGHSCORE_TABLE: hiscore.to_bytes(4, "big")})


@pytest.mark.parametrize("slot", (0, 1, 2, 5))
def test_redraw_all_overwrites_the_weapon_slot(slot):
    """The routine SETS A_POWERUP_ACTIVE_SLOT itself — 0 before the right-hand glyph and 1 before
    the left — so whatever it held on entry cannot reach either blit, and the byte comes back at 1.
    Both writes are in the diff."""
    _redraw_all_case(seed=slot + 120, extra={A_POWERUP_ACTIVE_SLOT: bytes([slot])})


# =================================================================================================
# player_intro_screen @ 0x13426
# =================================================================================================

def _intro_case(seed=0, back=A_SCREEN_BACK_BUFFER, front=A_SCREEN_FRONT_BUFFER, extra=None):
    pokes = _panel_pokes(seed, {**_buffer_pokes(back, front), **(extra or {})})
    diffs, _ = differential(
        ENTRY_PLAYER_INTRO_SCREEN, {"_pokes": pokes},
        lambda lib, buf: lib.g_player_intro_screen(buf))
    assert not diffs, f"seed={seed} back={back:#x}\n{report(diffs)}"


@pytest.mark.parametrize("prepare", (0, 1, 0xff))
def test_intro_prepare_for_combat_flag(prepare):
    """The second line is drawn only when the flag byte is nonzero (`tst.b` + `beq`), so all three
    of these fork the same way the game's own 0/1 does."""
    _intro_case(seed=prepare + 130, extra={A_SHOW_PREPARE_FOR_COMBAT: bytes([prepare])})


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_intro_every_player_index(chunk):
    """All 256 player indices, sharded four ways.

    THE DIGIT'S COLUMN IS draw_text_record's LEFTOVER D1 — nothing reloads it, so the number lands
    immediately after "PLAYER". The character is `index + 0x31` added as a BYTE, so 0xcf and above
    wrap into the control characters draw_char forks on (0x01 clears a cell, 0x02 fills it, 0x20
    draws nothing at all), and 0x7f..0xce reach it as codes above the font's 48 glyphs.
    """
    for player in range(chunk, 0x100, FUZZ_CHUNKS):
        _intro_case(seed=player, extra={A_CURRENT_PLAYER_INDEX: bytes([player])})


def test_intro_draws_into_the_back_buffer_whichever_it_is():
    """`playfield_clear` and the blits all follow 0x1797e, and the flip at the end swaps the pair."""
    _intro_case(seed=141, back=A_SCREEN_FRONT_BUFFER, front=A_SCREEN_BACK_BUFFER)
    _intro_case(seed=142, back=abi.SCRATCH, front=A_SCREEN_FRONT_BUFFER)


@pytest.mark.parametrize("column,row,text", (
    (0x10, 0x50, b"PLAYER"),   # the shipped record, spelt out
    (0x10, 0x50, b""),         # ...empty, where the digit lands ON the record's own column
    (0x10, 0x50, b"A"),        # ...one character
    (0x00, 0x50, b"PLAYERPLAYERPLAYER"),   # a long run, from column 0
    (0x20, 0x50, b"PLAYER"),   # the same length starting elsewhere
    (0xff, 0x50, b"PLAYER"),   # a NEGATIVE start column, sign-extended
    (0x10, 0x20, b"PLAYER"),   # a different row: the digit's row is the routine's own, not this
))
def test_intro_digit_follows_the_records_leftover_column(column, row, text):
    """THE DIGIT'S COLUMN IS `draw_text_record`'s SECOND OUTPUT — D1, one past the last character it
    drew — and nothing reloads it, so the number lands wherever the string ran out.

    That output has NO OTHER PIN IN THE SUITE: `g_draw_text_record` passes NULL for it and
    test_text.py's stub dumps only A6, so a reconstruction that handed back the record's STARTING
    column, or the column before the last increment, or nothing at all on the empty-record path,
    passes every one of that battery's twelve shipped records and seven synthetic edges. These seven
    record shapes are what stands between it and an untested output: they vary the length (0, 1, 6
    and 18 characters), both ends of the start column's SIGN, and the row — which must not move the
    digit, because the digit's row is this routine's own `lea 12800(a0),a0`.

    The record is poked over the shipped msg_player, so A6 still points where the `lea` at 0x1346c
    puts it and only its contents change.
    """
    record = bytes([column & 0xff, row & 0xff]) + text + b"\x00"
    _intro_case(seed=column + row + len(text), extra={A_MSG_PLAYER: record})


def test_intro_installs_the_frontend_palette():
    """The last thing it does is copy 32 bytes from A_PALETTE_FRONTEND into irq.h's A_MENU_PALETTE,
    which is the shadow the menu VBL uploads. Poking the source to noise is what makes the copy
    visible: the destination is the first byte of bss and is otherwise zero on both sides."""
    rng = random.Random(ENTRY_PLAYER_INTRO_SCREEN)
    _intro_case(seed=151, extra={A_PALETTE_FRONTEND: rng.randbytes(PALETTE_BYTES)})


def test_intro_blanks_the_raster_pen_zero():
    """`clr.w $18fc4` — the raster split's first colour word, and only that word: the fifteen pens
    after it must survive, which noise over the whole shadow is what shows."""
    rng = random.Random(ENTRY_PLAYER_INTRO_SCREEN + 1)
    _intro_case(seed=152, extra={A_PALETTE_HW_SHADOW: rng.randbytes(PALETTE_BYTES)})


# =================================================================================================
# title_screen_draw @ 0x12a28
# =================================================================================================

def _title_case(seed=0, back=A_SCREEN_BACK_BUFFER, front=A_SCREEN_FRONT_BUFFER, extra=None):
    pokes = _panel_pokes(seed, {**_buffer_pokes(back, front), **(extra or {})})
    diffs, _ = differential(
        ENTRY_TITLE_SCREEN_DRAW, {"_pokes": pokes},
        lambda lib, buf: lib.g_title_screen_draw(buf))
    assert not diffs, f"seed={seed} back={back:#x}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (161, 162))
def test_title_screen(seed):
    """The screen as the game ships it: two logos and five records over a cleared frame."""
    _title_case(seed=seed)


def test_title_draws_into_the_back_buffer_whichever_it_is():
    _title_case(seed=163, back=A_SCREEN_FRONT_BUFFER, front=A_SCREEN_BACK_BUFFER)
    _title_case(seed=164, back=abi.SCRATCH, front=A_SCREEN_FRONT_BUFFER)


def test_title_hewson_logo_continues_the_zynaps_source():
    """ONE SOURCE POINTER DRAWS BOTH LOGOS. `blit_graphic_block` advances A6, the routine loads it
    once, and the three 64-row ZYNAPS strips exhaust ZYNLOGO.DAT exactly — so the two 24-row strips
    that follow read HEWLOGO.DAT, which `_start` loads at the next address up. Poking the two files
    to distinguishable patterns is what separates that from a second `lea`."""
    _title_case(seed=165, extra={
        A_ZYNAPS_LOGO: bytes([0x5a]) * (LOGO_STRIPS * LOGO_STRIP_BYTES),
        A_HEWSON_LOGO: bytes([0xa5]) * (HEWSON_LOGO_STRIPS * HEWSON_STRIP_BYTES)})


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_POWER_GAUGE_FRAMES", "include/hud.h", "A_power_gauge_frames"),
    ("A_SMLOGOS_FRAMES", "include/hud.h", "A_smlogos_frames"),
    ("A_HUD_POWERUP_ICONS", "include/hud.h", "A_hud_powerup_icons"),
    ("A_HUD_WEAPON_ICONS", "include/hud.h", "A_hud_weapon_icons"),
    ("A_POWERUP_CURSOR", "include/hud.h", "A_powerup_cursor"),
    ("A_POWERUP_ACTIVE_SLOT", "include/hud.h", "A_powerup_active_slot"),
    ("A_PANEL_LOGO_FRAME", "include/hud.h", "A_panel_logo_frame"),
    ("A_POWER_GAUGE_DISPLAY", "include/hud.h", "A_power_gauge_display"),
    ("A_SCREEN_BACK_BUFFER", "include/hud.h", "A_screen_back_buffer"),
    ("A_SCREEN_FRONT_BUFFER", "include/hud.h", "A_screen_front_buffer"),
    ("POWER_GAUGE_FRAMES", "include/hud.h", "POWER_GAUGE_FRAMES"),
    ("POWER_GAUGE_ROWS", "include/hud.h", "POWER_GAUGE_ROWS"),
    ("POWER_GAUGE_ROW_BYTES", "include/hud.h", "POWER_GAUGE_ROW_BYTES"),
    ("POWERUP_ICON_ROWS", "include/hud.h", "POWERUP_ICON_ROWS"),
    ("POWERUP_ICON_ROW_BYTES", "include/hud.h", "POWERUP_ICON_ROW_BYTES"),
    ("WEAPON_ICON_ROWS", "include/hud.h", "WEAPON_ICON_ROWS"),
    ("WEAPON_ICON_ROW_BYTES", "include/hud.h", "WEAPON_ICON_ROW_BYTES"),
    ("ICON_TABLE_ENTRY_BYTES", "include/hud.h", "ICON_TABLE_ENTRY_BYTES"),
    ("A_LIFE_ICONS", "include/hud.h", "A_life_icons"),
    ("A_SCORE_PANEL_STRIP", "include/hud.h", "A_score_panel_strip"),
    ("A_PLAYER_PANEL_STRIP", "include/hud.h", "A_player_panel_strip"),
    ("A_HISCORE_PANEL_STRIP", "include/hud.h", "A_hiscore_panel_strip"),
    ("A_PANEL_MASTER", "include/hud.h", "A_panel_master"),
    ("A_LIVES", "include/hud.h", "A_lives"),
    ("A_CURRENT_PLAYER_INDEX", "include/hud.h", "A_current_player_index"),
    ("A_PANEL_REDRAW_MASK", "include/hud.h", "A_panel_redraw_mask"),
    ("PANEL_REDRAW_LIVES_BIT", "include/hud.h", "PANEL_REDRAW_LIVES_BIT"),
    ("LIVES_ICONS", "include/hud.h", "LIVES_ICONS"),
    ("LIFE_ICON_ROWS", "include/hud.h", "LIFE_ICON_ROWS"),
    ("LIFE_ICON_ROW_BYTES", "include/hud.h", "LIFE_ICON_ROW_BYTES"),
    ("LIVES_FIRST_COLUMN", "include/hud.h", "LIVES_FIRST_COLUMN"),
    ("LIVES_ROW_OFFSET", "include/hud.h", "LIVES_ROW_OFFSET"),
    ("PLAYER_DIGIT_SHIFT", "include/hud.h", "PLAYER_DIGIT_SHIFT"),
    ("PLAYER_DIGIT_GLYPH_BIAS", "include/hud.h", "PLAYER_DIGIT_GLYPH_BIAS"),
    ("PANEL_STRIP_ROWS", "include/hud.h", "PANEL_STRIP_ROWS"),
    ("PANEL_STRIP_ROW_BYTES", "include/hud.h", "PANEL_STRIP_ROW_BYTES"),
    ("PLAYER_STRIP_ROW_BYTES", "include/hud.h", "PLAYER_STRIP_ROW_BYTES"),
    ("SCORE_STRIP_OFFSET", "include/hud.h", "SCORE_STRIP_OFFSET"),
    ("SCORE_DIGITS_OFFSET", "include/hud.h", "SCORE_DIGITS_OFFSET"),
    ("SCORE_RIGHTMOST_COLUMN", "include/hud.h", "SCORE_RIGHTMOST_COLUMN"),
    ("PLAYER_STRIP_OFFSET", "include/hud.h", "PLAYER_STRIP_OFFSET"),
    ("HISCORE_STRIP_OFFSET", "include/hud.h", "HISCORE_STRIP_OFFSET"),
    ("PANEL_TOP_OFFSET", "include/hud.h", "PANEL_TOP_OFFSET"),
    ("PANEL_MASTER_LONGWORDS", "include/hud.h", "PANEL_MASTER_LONGWORDS"),
    ("A_FONT_GLYPHS", "include/text.h", "A_font_glyphs"),
    ("GLYPH_BYTES", "include/text.h", "GLYPH_BYTES"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("A_HIGHSCORE_TABLE", "include/highscore.h", "A_highscore_table"),
    ("A_PALETTE_HW_SHADOW", "include/irq.h", "A_palette_hw_shadow"),
    ("A_MENU_PALETTE", "include/irq.h", "A_menu_palette"),
    ("PALETTE_PENS", "include/video.h", "PALETTE_PENS"),
    ("A_ZYNAPS_LOGO", "include/hud.h", "A_zynaps_logo"),
    ("A_HEWSON_LOGO", "include/hud.h", "A_hewson_logo"),
    ("A_SHOW_PREPARE_FOR_COMBAT", "include/hud.h", "A_show_prepare_for_combat"),
    ("A_MSG_PLAYER", "include/text.h", "A_msg_player"),
    ("A_PALETTE_FRONTEND", "include/hud.h", "A_palette_frontend"),
    ("LOGO_STRIPS", "include/hud.h", "LOGO_STRIPS"),
    ("LOGO_STRIP_BYTES", "include/hud.h", "LOGO_STRIP_BYTES"),
    ("HEWSON_LOGO_STRIPS", "include/hud.h", "HEWSON_LOGO_STRIPS"),
    ("HEWSON_STRIP_BYTES", "include/hud.h", "HEWSON_STRIP_BYTES"),
    ("HISCORE_DIGITS_OFFSET", "include/hud.h", "HISCORE_DIGITS_OFFSET"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
)
ENTRY_PROLOGUES = {
    "ENTRY_STATUS_PANEL_REDRAW_ALL": "6100020c2c7900017982",
    "ENTRY_PLAYER_INTRO_SCREEN": "61003726610025504279",
    # Ten bytes is not enough here: `role_of_honour_screen` @ 0x13338 opens with the SAME
    # `lea $6c8ee,a6 / movea.l $1797e,a0` and the two separate only at byte 16.
    "ENTRY_TITLE_SCREEN_DRAW": "4df90006c8ee20790001797e2f086100ff36",
    "ENTRY_DRAW_LIVES_ICONS": "323c002041f90007e860",
    "ENTRY_DRAW_PLAYER_DIGIT_SHIFTED": "10390001991b52004880",
    "ENTRY_DRAW_SCORE_PANEL": "49f90006c72e264e47eb",
    "ENTRY_STATUS_PANEL_BUILD_MASTER": "49f90006c72e267c0007",
    "ENTRY_HUD_DRAW_LOGO_ANIM": "0a3900010001990e41f9",
    "ENTRY_HUD_DRAW_POWERUP_ICON": "41f9000761c043f90007",
    "ENTRY_HUD_DRAW_WEAPON_ICON": "41f90007606043f90007",
    "ENTRY_DRAW_POWER_GAUGE": "41f9000607be10390001",
}
