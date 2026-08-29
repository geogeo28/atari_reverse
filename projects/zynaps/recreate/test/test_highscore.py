"""Differential tests for the ROLE OF HONOUR screen (src/highscore.c).

The screen composes routines that already have batteries of their own — `screen_clear`,
`blit_graphic_block`, `draw_text_record`, `draw_bcd_number` and `screen_flip_buffers` — so what
these cases are for is the COMPOSITION: which buffer each piece goes into, that the logo's three
strips walk one source pointer rather than three, and that the five scores are drawn at the
routine's own row displacements and not at the rows the records carry.

WHAT THE DIFFERENTIAL CANNOT SEE HERE: `screen_flip_buffers` publishes the new front buffer to the
shifter at $ff8201/$ff8203, which is not an image address. The POINTER SWAP it makes is diffed;
the publish is not, and reaches only src/video.c's sink (include/video.h). STATUS.md carries that
residual, which is the video subsystem's rather than this one's.
"""
import ctypes
import random
from pathlib import Path

import pytest

import abi
import harness
from abi import seed_spans
from harness import differential, report

ENTRY_ROLE_OF_HONOUR_SCREEN = 0x13338
ENTRY_GAME_OVER_SCREEN = 0x12e66
ENTRY_HIGHSCORE_CHECK_AND_INSERT = 0x12eae
ENTRY_HIGHSCORE_ENTER_NAME = 0x12fd4
ENTRY_NAME_ENTRY_EDIT_STEP = 0x13058
ENTRY_NAME_ENTRY_REDRAW = 0x13196
# Checkpoints inside those four. The first three are the paragraph boundaries the composed routines
# are ALSO driven at, because a whole run cannot isolate what one paragraph does; the last three are
# the three addresses one edit step can leave through, which is how a case says which arm it drove.
STOP_GAME_OVER_SCREEN_PROLOGUE = 0x12e94      # the `bsr` into `highscore_check_and_insert`
STOP_HIGHSCORE_RATED = 0x12f0e                # both the shift and the no-shift arm converge here
STOP_HIGHSCORE_NOT_RATED = 0x12f5a            # ...and the `beq` at 0x12ed4 leaves for here
ENTRY_HIGHSCORE_RANK_AND_SHIFT = 0x12eb2
# `highscore_check_and_insert`'s own `rts`, and the ONLY way to stop the NOT RATED arm: 0x12fba pops
# one longword too many, so that `rts` returns two levels up and the routine has no reachable end of
# its own. test_the_not_rated_arm_pops_its_own_return_address is what states that.
STOP_CHECK_AND_INSERT_NOT_RATED = 0x12fc0
STOP_EDIT_STEP_REDRAW = 0x13196
# NOT A DISTINCT EXIT: 0x131c2 (the redraw block's last instruction) falls THROUGH into 0x131c4, so
# reaching this address does not by itself say the redraw was skipped. What says that is the compose
# page — a redraw writes the record and the block cursor into seeded noise. Kept as the KEEP arm's
# stop because it is where the original's three `bra`s go, not as the proof.
STOP_EDIT_STEP_KEEP = 0x131c4
STOP_EDIT_STEP_COMMIT = 0x1324a
# ...and where the REDRAW block itself ends, which is the same address by a different route:
# 0x131c2 restores D4 and falls through into it.
STOP_NAME_ENTRY_REDRAW = 0x131c4
# Where `game_over_screen`'s dead tail begins — the address the NOT RATED arm was meant to come back
# to. Named so the assertion below can say what the oracle's A0 is holding.
GAME_OVER_DEAD_TAIL = 0x12e98

# mirrors of include/highscore.h
A_HIGHSCORE_TABLE = 0x19d5a
HIGHSCORE_ENTRIES = 5
HIGHSCORE_ENTRY_BYTES = 0x16
HIGHSCORE_ENTRY_RECORD = 4
HIGHSCORE_DIGITS_COLUMN = 0xe
HIGHSCORE_FIRST_SCORE_OFFSET = 0x44c0
HIGHSCORE_SCORE_ROW_STEP = 0x780
HIGHSCORE_SHIFT_NAME_BYTES = 0xf
HIGHSCORE_NAME_OFFSET = 6
HIGHSCORE_NOT_RATED_COUNTER = HIGHSCORE_ENTRIES - 1
GAME_OVER_DIGIT_ROW_OFFSET = 0xa00
A_MSG_GAME_OVER_PLAYER = 0x199d9

# ...and of the game-over chain's own half of that header
A_MSG_NEW_HIGH_SCORE = 0x199ee
A_MSG_YOU_ARE_NOT_RATED = 0x19a24
SFX_NEW_HIGH_SCORE = 0x1e
SFX_YOU_ARE_NOT_RATED = 0x22
HIGHSCORE_RATED = 1
HIGHSCORE_NOT_RATED = 0
A_TEXT_PLEASE_ENTER_NAME = 0x19a0b
A_TEXT_OSK_ROW1 = 0x19ce6
A_TEXT_OSK_ROW2 = 0x19d05
A_TEXT_OSK_ROW3 = 0x19d24
A_NAME_ENTRY_RECORD = 0x19d48
NAME_ENTRY_FIRST_CHAR = 2
NAME_ENTRY_LAST_CHAR = 0x11
A_NAME_ENTRY_FROM_JOYSTICK = 0x19ce4
A_NAME_ENTRY_CURSOR_HIT = 0x19ce3
A_SCANCODE_TO_CHAR_TABLE = 0x19a39
NAME_ENTRY_SCANCODE_MAX = 0x72
SCANCODE_ESC = 0x01
SCANCODE_UNDO = 0x61
SCANCODE_BACKSPACE = 0x0e
SCANCODE_DELETE = 0x53
SCANCODE_RETURN = 0x1c
SCANCODE_ENTER = 0x72
A_JOYSTICK_STATE = 0x19681
JOYSTICK_UP = 0x01
JOYSTICK_DOWN = 0x02
JOYSTICK_LEFT = 0x04
JOYSTICK_RIGHT = 0x08
JOYSTICK_FIRE = 0x80
IKBD_CMD_JOYSTICK_INTERROGATE = 0x16
A_GUNSIGHT_SPRITE = 0x6a61e
GUNSIGHT_ROWS = 9
OSK_HOME_X = 0x50
OSK_HOME_Y = 0x41
OSK_CURSOR_STEP = 2
NAME_ENTRY_ROW_OFFSET = 0x3200
NAME_ENTRY_CURSOR_COLUMN_BIAS = 9
NAME_ENTRY_NAME_LONGS = 4
NAME_ENTRY_BLANK_FILL = 0x01010101
NAME_ENTRY_BLANK_TAIL = 0x01010100
NAME_ENTRY_STEP_SHIFT = 16
NAME_ENTRY_STEP_CURSOR_MASK = 0xffff
NAME_ENTRY_KEY_WAIT_PC = 0x13104
NAME_ENTRY_IDLE_VBL_WAIT_PC = 0x13118
NAME_ENTRY_VBL_WAIT_PC = 0x131d0
NAME_ENTRY_FIRE_RELEASE_WAIT_PC = 0x131ee
NAME_ENTRY_KEY_RELEASE_WAIT_PC = 0x131fa
NAME_ENTRY_COMMIT_WAIT_PC = 0x13264
NOT_RATED_FIRE_PRESS_WAIT_PC = 0x12f9a
NOT_RATED_FIRE_RELEASE_WAIT_PC = 0x12fb2

# The three arms `name_entry_edit_step` answers, in the header's own order, plus the address each
# one leaves the loop body at. `NAME_ENTRY_STEP_REFUSED` is not here: it is the kit's give-up and
# not an arm of the original, and a case that reached it would already have been thrown away.
STEP_REDRAW, STEP_KEEP, STEP_COMMIT = 0, 1, 2
STEP_STOP_PC = {STEP_REDRAW: STOP_EDIT_STEP_REDRAW,
                STEP_KEEP: STOP_EDIT_STEP_KEEP,
                STEP_COMMIT: STOP_EDIT_STEP_COMMIT}

# mirrors of include/enemy.h — the two bytes `st` and `sf` store
SCC_BYTE_TRUE = 0xff
SCC_BYTE_FALSE = 0x00

# mirrors of include/entity.h — the five gunsight fields the edit frame rewrites
ENTITY_STRIDE = 0x2c
ENTITY_X = 0x00
ENTITY_Y = 0x04
ENTITY_HEIGHT = 0x08
ENTITY_SPRITE = 0x0a
ENTITY_ALIVE = 0x0e

# mirrors of include/player.h, include/init.h, include/irq.h and include/text.h
A_ENTITY_TABLE = 0x17a8e
A_KEY_SCANCODE = 0x19685
A_VBL_WAIT_FLAG = 0x198a7
A_MENU_PALETTE = 0x19f46
CHAR_CLEAR_CELL = 1
CHAR_FILL_CELL = 2

# mirrors of include/input.h — the cursor the on-screen keyboard's hit test reads
A_OSK_CURSOR_X = 0x19d44
A_OSK_CURSOR_Y = 0x19d46

# mirrors of include/sound.h — where the two jingles' streams are found, and the header that makes
# the channel this file passes unobservable
A_TUNE_INDEX = 0x17058
A_TUNE_DATA = 0x171e8
SOUND_STREAM_CHANNEL_TAG = 0xfa

# mirrors of include/hud.h and include/video.h
A_PALETTE_FRONTEND = 0x195f8
A_BACKDROP_PAGE0 = 0x1a8ae
PLAYFIELD_BYTES = 0x5a00
SHIFTER_PALETTE_PAIRS = 8

# mirrors of include/score.h
A_PLAYER_SCORE_BCD = 0x195e0

# mirrors of include/hud.h (the digit the prologue prints after the record)
A_CURRENT_PLAYER_INDEX = 0x1991b
PLAYER_DIGIT_CHAR_ZERO = 0x31


# mirrors of include/hud.h
A_ZYNAPS_LOGO = 0x6c8ee
LOGO_STRIPS = 3
LOGO_STRIP_BYTES = 0x800

# mirrors of include/text.h
A_FONT_GLYPHS = 0x6be6e

# mirrors of include/video.h
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
SCREEN_BYTES = 32000
SCREEN_ROW_BYTES = 160

DISK = Path(__file__).resolve().parents[2] / "bin" / "disk"
# Read ONCE, as test_text.py's FONT_BYTES and test_hud.py's PANEL_IMAGE are: the font never changes
# and this file's poke builders run per case, the fuzz included.
FONT_BYTES = (DISK / "EXTCHARS.DAT").read_bytes()
ZYNAPS_LOGO_BYTES = (DISK / "ZYNLOGO.DAT").read_bytes()
SCREEN_BACK_BUFFER = abi.SCREEN_BACK
SCREEN_FRONT_BUFFER = abi.SCREEN_FRONT

harness._lib.g_role_of_honour_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_role_of_honour_screen.restype = None
harness._lib.g_game_over_screen_prologue.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_over_screen_prologue.restype = None
harness._lib.g_highscore_rank_and_shift.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_highscore_rank_and_shift.restype = ctypes.c_uint32
harness._lib.g_game_over_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_over_screen.restype = None
harness._lib.g_highscore_check_and_insert.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_highscore_check_and_insert.restype = ctypes.c_uint32
harness._lib.g_highscore_enter_name.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_highscore_enter_name.restype = None
harness._lib.g_name_entry_edit_step.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_name_entry_edit_step.restype = ctypes.c_uint32
harness._lib.g_name_entry_redraw.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_name_entry_redraw.restype = None


def _pokes(seed, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None, extra_spans=()):
    """Noise over both framebuffers, the real font and the real ZYNAPS logo, plus a case's own.

    Both graphics are bss — `_start` loads EXTCHARS.DAT and ZYNLOGO.DAT over them — so against a
    fresh image every glyph and every logo strip would blit zeroes and a wrong source address would
    be invisible. The guard bands are what turn a blit one row too far into a difference.

    `extra_spans` is what the game-over chain adds (`_chain_pokes` below): the seeding CONVENTION —
    which spans get a guard band, how the two screen pointers are encoded, where the font comes from
    — is one decision for the whole file, and two copies of it would let this battery's two halves
    diff the same screens under different rules.
    """
    spans = [(back, back + SCREEN_BYTES), (front, front + SCREEN_BYTES), *extra_spans]
    pokes = seed_spans(seed, spans, guard=abi.GUARD_BYTES)
    pokes[A_FONT_GLYPHS] = FONT_BYTES
    pokes[A_ZYNAPS_LOGO] = ZYNAPS_LOGO_BYTES
    pokes[A_SCREEN_BACK] = back.to_bytes(4, "big")
    pokes[A_SCREEN_FRONT] = front.to_bytes(4, "big")
    pokes.update(extra or {})
    return pokes


def _case(seed=0, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None, poison=False):
    pokes = _pokes(seed, back=back, front=front, extra=extra)
    diffs, _ = differential(
        ENTRY_ROLE_OF_HONOUR_SCREEN, {"_pokes": pokes},
        lambda lib, buf: lib.g_role_of_honour_screen(buf), poison=poison)
    assert not diffs, f"seed={seed} back={back:#x} front={front:#x}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (11, 12, 13))
def test_shipped_table(seed):
    """The screen as the game ships it: five names and five scores from the .PRG's own table."""
    _case(seed=seed)


def test_draws_into_the_back_buffer_whichever_it_is():
    """It takes the draw buffer from 0x1797e and flips at the end, so a candidate that hard-coded a
    buffer would agree only while the pointers happen to be the way `_start` left them."""
    _case(seed=21, back=SCREEN_FRONT_BUFFER, front=SCREEN_BACK_BUFFER)
    _case(seed=22, back=abi.SCRATCH, front=SCREEN_FRONT_BUFFER)


def _table_with(entries):
    """The five-entry table rebuilt from (score, column, row, name) tuples.

    EACH ROW IS PADDED WITH ITS OWN LETTER, not with spaces, and that is what pins the shift-down's
    fifteen-byte name copy END TO END. A shared filler makes neighbouring rows byte-identical from
    the fifth character on, so a shift that carried only the first seven bytes would move rows that
    already agreed there and the diff would see nothing — measured: with a common pad, dropping
    `HIGHSCORE_SHIFT_NAME_BYTES` from 15 to 7 leaves this file green.
    """
    blob = b""
    for index, (score, column, row, name) in enumerate(entries):
        name = name.ljust(HIGHSCORE_ENTRY_BYTES - HIGHSCORE_ENTRY_RECORD - 3,
                          bytes([ord("a") + index]))
        blob += score.to_bytes(4, "big") + bytes([column & 0xff, row & 0xff]) + name + b"\x00"
    assert len(blob) == HIGHSCORE_ENTRIES * HIGHSCORE_ENTRY_BYTES
    return {A_HIGHSCORE_TABLE: blob}


def test_the_score_rows_are_the_routines_own():
    """THE SCORES DO NOT FOLLOW THE RECORDS. Each score is drawn at a `lea` displacement of the
    routine's own — 17600 and four steps of 1920 — while each NAME is drawn at the row byte inside
    its record. The shipped table makes those the same five rows, so the only way to tell them apart
    is a table where they differ, which is what this case builds: the names move and the scores must
    not. A reconstruction that read the row from the record passes every other case here.
    """
    entries = [(0x00010000 * (i + 1), 0x10, 20 + i * 4, b"NAME%d" % i)
               for i in range(HIGHSCORE_ENTRIES)]
    _case(seed=31, extra=_table_with(entries))


def test_every_score_is_its_own_entry():
    """Five different scores at five different rows: a candidate that drew one entry's score five
    times, or walked the table with the wrong stride, differs on four rows out of five."""
    entries = [(0x12345678, 0x10, 110, b"AAA"), (0x00000000, 0x10, 122, b"BBB"),
               (0x99999999, 0x10, 134, b"CCC"), (0x00000001, 0x10, 146, b"DDD"),
               (0xffffffff, 0x10, 158, b"EEE")]
    _case(seed=41, extra=_table_with(entries))


def test_record_columns_are_the_records_own():
    """The name records carry their own column, and the routine passes each one through untouched —
    including a NEGATIVE one, which draw_text_record sign-extends to the left of the buffer."""
    entries = [(0x00000100 * (i + 1), column, 110 + i * 12, b"X")
               for i, column in enumerate((0, 1, 0x27, 0xff, 0x80))]
    _case(seed=51, extra=_table_with(entries))


def test_the_logo_strips_walk_one_source():
    """`blit_graphic_block` ADVANCES its source, and the routine loads it once for all three strips,
    so strip 1 starts where strip 0 stopped. Poking the logo's three strips to three distinguishable
    patterns is what separates that from three blits of strip 0."""
    logo = b"".join(bytes([0x11 * (strip + 1)]) * LOGO_STRIP_BYTES for strip in range(LOGO_STRIPS))
    _case(seed=61, extra={A_ZYNAPS_LOGO: logo})


# NO POISON PASS, and it is not an oversight: MEASURED, it crashes the candidate. The screen ends
# in `screen_flip_buffers`, which WRITES 0x1797e/0x17982 — so the attribution pass poisons the very
# pointer the routine reads its draw buffer from, and the re-run then draws at a canary address.
# That is the same shape as test_sound.py's two no-poison routines: an output the routine also
# steers on cannot be a canary. What the pass would have bought is bought instead by the pieces this
# screen is made of, every one of which has its own poison cases (test_text.py's draw_char /
# draw_bcd_number / draw_text_record, test_video.py's screen_clear / blit_graphic_block), plus
# `test_the_logo_strips_walk_one_source` and `test_every_score_is_its_own_entry` above, which fail
# on a candidate that writes the right bytes in the wrong places.



# ================================================================================================
# game_over_screen_prologue @ [0x12e66, 0x12e94)
# ================================================================================================

def _game_over_case(seed, player, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER):
    """The same staged screen the role-of-honour cases use, plus the player index it prints."""
    pokes = _pokes(seed, back=back, front=front, extra={A_CURRENT_PLAYER_INDEX: bytes([player])})
    diffs, _ = differential(ENTRY_GAME_OVER_SCREEN, {"_pokes": pokes},
                            lambda lib, buf: lib.g_game_over_screen_prologue(buf),
                            stop_pc=STOP_GAME_OVER_SCREEN_PROLOGUE)
    assert not diffs, (f"seed={seed} player={player:#04x} back={back:#x}\n{report(diffs)}")


@pytest.mark.parametrize("player", (0, 1, 2, 8))
def test_game_over_screen_prologue(player):
    """GAME OVER PLAYER n over a noise-seeded playfield.

    THE DIGIT'S COLUMN IS `draw_text_record`'s LEFTOVER, exactly as `player_intro_screen`'s is —
    nothing reloads D1 between the record and the character — so a candidate that named a column
    would put the number in the wrong place. The row is this screen's own 0xa00 and NOT hud.h's
    0x3200, which is the other thing these cases hold.

    The player index is swept over four values rather than the two the game produces, because it is
    added as a BYTE before `ext.w` and the sum indexes the font.
    """
    _game_over_case(seed=0x40 + player, player=player)


def test_game_over_screen_prologue_draws_into_the_back_buffer():
    """It reads 0x1797e for its buffer and does NOT flip afterwards, which is what separates it from
    the two front-end screens in src/hud.c. Swapping the pair and then pointing the back one at a
    third buffer is what makes both halves of that observable."""
    _game_over_case(seed=0x50, player=0, back=SCREEN_FRONT_BUFFER, front=SCREEN_BACK_BUFFER)
    _game_over_case(seed=0x51, player=1, back=abi.SCRATCH, front=SCREEN_FRONT_BUFFER)


# ================================================================================================
# highscore_rank_and_shift @ [0x12eb2, 0x12f0e) / [0x12eb2, 0x12f5a)
# ================================================================================================

# EVERY RANKING CASE POKES ITS OWN TABLE over the shipped one, and that is deliberate: the .PRG's
# five entries are close together and sorted, so they reach neither the equality boundary nor the
# signed compare. The shipped table is exercised by `role_of_honour_screen`'s cases above instead.


def _rank_case(score, table=None, rank=None, note="", poison=False):
    """Run the ranking slice for `score`, stopping at whichever arm `rank` says it takes.

    `rank` is the table row the score should take, or HIGHSCORE_ENTRIES for "did not rate"; the case
    asserts the reconstruction's answer against it AND against the oracle's own D6, so a candidate
    that shifted the right bytes for the wrong reason is still caught.
    """
    # NO SCREEN STAGING: this slice draws nothing, so the poke set is the table, the score, and a
    # guard entry PAST the five — which is what a shift one row too far would land on.
    pokes = {A_PLAYER_SCORE_BCD: score.to_bytes(4, "big"),
             A_HIGHSCORE_TABLE + HIGHSCORE_ENTRIES * HIGHSCORE_ENTRY_BYTES:
                 bytes([0xa5]) * HIGHSCORE_ENTRY_BYTES}
    if table is not None:
        pokes.update(table)          # `_table_with` answers a poke dict, not a blob
    not_rated = rank == HIGHSCORE_ENTRIES
    stop = STOP_HIGHSCORE_NOT_RATED if not_rated else STOP_HIGHSCORE_RATED
    diffs, info = differential(ENTRY_HIGHSCORE_RANK_AND_SHIFT, {"_pokes": pokes},
                              lambda lib, buf: lib.g_highscore_rank_and_shift(buf), stop_pc=stop,
                              poison=poison)
    assert not diffs, f"{note} score={score:#010x} rank={rank}\n{report(diffs)}"
    assert info["ret"] == rank, f"{note}: answered {info['ret']}, expected {rank}"
    if not not_rated:
        # D6 is the original's own answer, one BELOW the row (0x12f0e adds one to it).
        assert info["regs"]["d6"] & 0xffff == (rank - 1) & 0xffff, (
            f"{note}: the oracle ranked {info['regs']['d6'] & 0xffff}, not {rank - 1}")
    return info


# One descending five-entry table, shared by the three cases whose whole point is relative ordering
# — three separately-maintained copies of it would let "beats entry k" and "equals entry k" drift
# onto different boundaries. `DESCENDING_SCORES[row]` is entry `row`'s score.
DESCENDING_SCORES = tuple(0x1000 * (HIGHSCORE_ENTRIES - row) for row in range(HIGHSCORE_ENTRIES))
DESCENDING_TABLE = _table_with(tuple((DESCENDING_SCORES[row], 0x10, 110 + 12 * row,
                                      f"NAME{row}".encode())
                                     for row in range(HIGHSCORE_ENTRIES)))


@pytest.mark.parametrize("rank", range(HIGHSCORE_ENTRIES))
def test_the_score_ranks_at_every_row(rank):
    """A score that beats exactly the entries below `rank`, over a table of five distinct scores.

    Every row of the table is driven, which is what pins the BACKWARDS walk: a scan that started at
    entry 0 and walked down would agree only at the two ends. The shift is checked by the byte diff
    — entries below the rank move, the ones above do not — and the rank itself by the answer.
    """
    _rank_case(DESCENDING_SCORES[rank] + 1, table=DESCENDING_TABLE, rank=rank,
               note=f"row {rank}")


def test_a_score_below_the_last_entry_does_not_rate():
    """The one arm that leaves at 0x12f5a, and it writes NOTHING — no shift, no rank."""
    _rank_case(DESCENDING_SCORES[-1] - 1, table=DESCENDING_TABLE, rank=HIGHSCORE_ENTRIES,
               note="below the table")


def test_equalling_an_entry_does_not_beat_it():
    """`ble` — the compare is "score <= entry, stop", so an EQUAL score ranks BELOW the entry it
    matched. Equalling the last entry therefore does not rate at all, which is the boundary a `blt`
    would get wrong in exactly one place."""
    _rank_case(DESCENDING_SCORES[-1], table=DESCENDING_TABLE, rank=HIGHSCORE_ENTRIES,
               note="equals the last entry")
    _rank_case(DESCENDING_SCORES[2], table=DESCENDING_TABLE, rank=3, note="equals the middle entry")


def test_the_shift_leaves_each_row_its_own_column_and_row_bytes():
    """The shift carries the score and the fifteen name characters and NOTHING ELSE.

    Every entry is given a DIFFERENT column and row byte and a different terminator, none of which
    the original moves — so a candidate that shifted all 22 bytes writes four wrong pairs. This is
    the case that says the table's coordinates belong to the SCREEN ROW and not to the entry.
    """
    table = bytearray()
    for row in range(HIGHSCORE_ENTRIES):
        table += (0x9000 - 0x1000 * row).to_bytes(4, "big")
        table += bytes([0x10 + row, 110 + 12 * row])
        table += f"PLAYER{row}".encode().ljust(HIGHSCORE_SHIFT_NAME_BYTES, b"?")
        table += bytes([0xe0 + row])       # the terminator, distinct per row and never moved
    assert len(table) == HIGHSCORE_ENTRIES * HIGHSCORE_ENTRY_BYTES
    _rank_case(0x9001, table={A_HIGHSCORE_TABLE: bytes(table)}, rank=0, note="every row shifts")


def test_a_negative_entry_is_beaten_by_every_score():
    """`cmp.l` + `ble` is SIGNED, so a table score with bit 31 set reads as negative.

    BCD spells 0x80000000 as eight thousand million, a score the game cannot reach — but the
    instruction is signed and this is what says so. With the last entry negative, even a score of
    zero ranks, where an unsigned compare would refuse it.
    """
    table = _table_with(((0x00001000, 0x10, 110, b"A"), (0x00000900, 0x10, 122, b"B"),
                         (0x00000800, 0x10, 134, b"C"), (0x00000700, 0x10, 146, b"D"),
                         (0x80000000, 0x10, 158, b"E")))
    _rank_case(0, table=table, rank=4, note="negative last entry")


def test_rank_and_shift_attribution():
    """Poison the shift's own writes. This slice schedules nothing and draws nothing, so it is the
    one part of the chain that can take an attribution pass over its whole output — which is what
    holds every byte of the fifteen-character copy rather than the handful the names differ at."""
    _rank_case(DESCENDING_SCORES[0] + 1, table=DESCENDING_TABLE, rank=0, note="attribution",
               poison=True)


RANK_FUZZ_CHUNKS = 4
RANK_FUZZ_CASES = 60


def _expected_rank(score, scores):
    """The row the routine's own scan lands on, derived the way the instructions run it."""
    counter = HIGHSCORE_ENTRIES - 1
    while counter >= 0 and _signed(score) > _signed(scores[counter]):
        counter -= 1
    if counter == HIGHSCORE_NOT_RATED_COUNTER:
        return HIGHSCORE_ENTRIES
    return counter + 1


def _signed(value):
    return value - (1 << 32) if value & 0x80000000 else value


@pytest.mark.parametrize("chunk", range(RANK_FUZZ_CHUNKS))
def test_rank_and_shift_fuzz(chunk):
    """Random tables and random scores, including unsorted tables and negative entries.

    AN UNSORTED TABLE IS A REAL INPUT to this half of the routine — nothing here re-sorts, and the
    scan stops at the first entry it does not beat — so the fuzz does not sort what it generates.
    """
    rng = random.Random(0x12eb2 + chunk)
    for _ in range(RANK_FUZZ_CASES // RANK_FUZZ_CHUNKS):
        scores = tuple(rng.choice((rng.randrange(0x10000), rng.getrandbits(32)))
                       for _ in range(HIGHSCORE_ENTRIES))
        table = _table_with(tuple((scores[row], rng.randrange(0x100), rng.randrange(0x100),
                                   bytes(rng.randrange(0x41, 0x5b) for _ in range(4)))
                                  for row in range(HIGHSCORE_ENTRIES)))
        score = rng.choice((rng.randrange(0x10000), rng.getrandbits(32),
                            scores[rng.randrange(HIGHSCORE_ENTRIES)]))
        _rank_case(score, table=table, rank=_expected_rank(score, scores), note="fuzz")


# ================================================================================================
# The game-over chain: game_over_screen @ 0x12e66 -> highscore_check_and_insert @ 0x12eae ->
# highscore_enter_name @ 0x12fd4
#
# EVERY CASE BELOW DECLARES A SCHEDULE, A SET OF WAIT SITES, OR BOTH, and that is the whole reason
# this half of the file exists: the chain busy-waits on four bytes nothing in it writes — the VBL
# flag, the IKBD scancode, and the joystick byte for a press and again for its release — so before
# the kit's scheduled-write model (TRAP_MODEL.md, Phase 8) none of these routines could be RUN, let
# alone verified. A schedule is the case's claim about what the interrupt handlers store and when,
# stated explicitly and given to both sides from one list; the kit compares the oracle's arrivals at
# each wait against the candidate's polls, site by site, so a port whose loop turned a different
# number of times fails even though the agent made both images agree.
#
# WHAT STAYS UNPINNED, and it is a bound of the model rather than of these cases: `OS_SCHED_MAX` is
# eight stores and `OS_SCHED_SITE_MAX` four sites per run, so one run can spell two characters and
# then commit — not fifteen. The fifteen-character cap is driven at the edit step instead, where a
# case can start the cursor wherever it likes. STATUS.md's "## Coverage limits" carries both.
# ================================================================================================

# What one gunsight blit can read out of its preshift bank, DERIVED from src/sprite.c rather than
# guessed: the phase offset is `(x & 0xf) * rows * SPRITE_COLLIDE_ROW_HALF_WORDS`, and x is forced
# even, so at 9 rows it maxes at 14 * 45 = 630; the rows themselves are 10 bytes each and a top clip
# only moves them, so 9 * 10 = 90 more. 720 bytes, rounded up here to a round number. `make guarded`
# is NOT what says so — it sees only accesses that leave the image, and this whole span is inside
# it — so over-seeding costs nothing and under-seeding would have to be caught by this arithmetic.
GUNSIGHT_SPRITE_BYTES = 0x400
# The characters between the name record's coordinates and its terminator — the same fifteen the
# shift-down carries, counted here from the two cursor bounds instead of restated.
NAME_ENTRY_CHARS = NAME_ENTRY_LAST_CHAR - NAME_ENTRY_FIRST_CHAR
# Three scancodes whose table entries are letters, read back off the image by
# `test_the_scancode_table_answers_letters` rather than assumed here.
SCANCODE_A, SCANCODE_B, SCANCODE_C = 0x1e, 0x30, 0x2e
# One of the thirty drawn keys, in the coordinates `onscreen_keyboard_hit_test` reads the cursor in:
# the top row's first key, which is 'A'. The arithmetic is that routine's own, inverted — see
# test_input.py's `_key_position`, which is where the grid is pinned.
OSK_KEY_A_X, OSK_KEY_A_Y = 0x68, 0x80
# A run long enough to blit the compose page onto the playfield several times over: one such blit is
# 5760 `move.l`s and the loop makes one a frame, so the default 200,000 does not cover a name.
CHAIN_MAX_INSNS = 2_000_000


def _store(pc, nth, addr, value, width=1):
    """One scheduled store, in the shape `harness.differential` takes."""
    return {"pc": pc, "nth": nth, "addr": addr, "width": width, "value": value}


def _chain_pokes(seed, score, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None):
    """Everything the chain draws into, reads from, or waits on — as noise with guard bands.

    `_pokes`' two spans plus four of this chain's own, because it composes into the FRONT END'S PAGE
    (`A_BACKDROP_PAGE0`) and blits that onto the playfield, draws the gunsight out of a preshift bank
    in bss, rewrites entity record 0 every frame, and copies the front end's palette into the shadow
    the menu VBL uploads. All four of those are bss and would be zeroes, where a blit of zeroes over
    zeroes is invisible.

    The four wait bytes are poked to a settled state — no key down, no fire, the VBL flag clear —
    so that every wait a case does NOT schedule falls through in one poll, and the polls a case DOES
    schedule are the only ones its arrival counts have to account for.

    TWO OF THE GUARD BANDS REACH INTO THE .PRG'S OWN DATA, which is checked rather than assumed:
    `A_MENU_PALETTE` is the first bss address, so its band below covers `attract_bar_pattern`'s tail
    and `boss_hitpoints` (0x19f28..0x19f45), and `A_ENTITY_TABLE`'s covers the tail of
    `actor_spawn_template` (0x17a62..). Neither region is read anywhere in `[0x12e66, 0x1326e)` —
    they belong to the attract bars, the boss and the spawner — and the band is applied identically
    to both sides, so noising them costs nothing and buys the thing a guard band is for: a palette
    copy or a record write that runs one longword short or one long.
    """
    pokes = _pokes(seed, back=back, front=front, extra_spans=(
        (A_BACKDROP_PAGE0, A_BACKDROP_PAGE0 + PLAYFIELD_BYTES),
        (A_GUNSIGHT_SPRITE, A_GUNSIGHT_SPRITE + GUNSIGHT_SPRITE_BYTES),
        (A_ENTITY_TABLE, A_ENTITY_TABLE + ENTITY_STRIDE),
        (A_MENU_PALETTE, A_MENU_PALETTE + SHIFTER_PALETTE_PAIRS * 4)))
    pokes[A_PLAYER_SCORE_BCD] = score.to_bytes(4, "big")
    pokes[A_CURRENT_PLAYER_INDEX] = b"\x00"
    pokes[A_JOYSTICK_STATE] = b"\x00"
    pokes[A_KEY_SCANCODE] = b"\x00"
    pokes[A_VBL_WAIT_FLAG] = b"\x00"
    # These two are adjacent and neither may be guarded: the byte above them is another
    # subsystem's, and the name record three bytes on runs straight into the high-score table.
    pokes[A_NAME_ENTRY_CURSOR_HIT] = bytes([0, SCC_BYTE_FALSE])
    pokes.update(extra or {})
    return pokes


def test_the_scancode_table_answers_letters():
    """The three scancodes the cases below type, read out of the image rather than assumed.

    Also the two bytes that make the SIGN extension observable: a scancode of 0x80 indexes 128 bytes
    BEFORE the table, which lands on the terminator of the message above it and answers a printable
    space — so a reconstruction that zero-extended would read a different byte and store a different
    character. 0x0c is an ordinary unprintable key, negative, so the two are not conflated.
    """
    table = harness.BASE_IMAGE
    assert (table[A_SCANCODE_TO_CHAR_TABLE + SCANCODE_A],
            table[A_SCANCODE_TO_CHAR_TABLE + SCANCODE_B],
            table[A_SCANCODE_TO_CHAR_TABLE + SCANCODE_C]) == (ord("A"), ord("B"), ord("C"))
    assert table[A_SCANCODE_TO_CHAR_TABLE - 0x80] == ord(" ")
    assert table[A_SCANCODE_TO_CHAR_TABLE + 0x0c] == 0xff


# ------------------------------------------------------------------------------------------------
# name_entry_edit_step @ [0x13058, 0x13196) / [0x13058, 0x131c4) / [0x13058, 0x1324a)
#
# One pass of the loop's body, entered where the original enters it. This is the slice that can put
# the cursor anywhere and hand the step any scancode, which is what makes the dispatch's arms and
# the fifteen-character cap reachable at all — a whole run cannot spell fifteen characters.
# ------------------------------------------------------------------------------------------------

def _record_with(characters):
    """The name record as a poke: its shipped column and row, then `characters`, then the 0."""
    body = bytes(characters).ljust(NAME_ENTRY_CHARS, bytes([CHAR_CLEAR_CELL]))
    assert len(body) == NAME_ENTRY_CHARS
    return {A_NAME_ENTRY_RECORD: bytes(harness.BASE_IMAGE[A_NAME_ENTRY_RECORD:
                                                          A_NAME_ENTRY_RECORD
                                                          + NAME_ENTRY_FIRST_CHAR]) + body + b"\x00"}


def _edit_step_case(cursor, step, moved, key=None, joystick=0, from_joystick=SCC_BYTE_FALSE,
                    cursor_xy=(OSK_HOME_X, OSK_HOME_Y), record=None, idle_frames=0,
                    fire_arrives_at=None, scratch_d4=0, seed=0x70, poison=False, note=""):
    """One edit step: `cursor` in, `step` and `moved` expected out.

    `key` is the scancode the ACIA handler leaves, scheduled at the step's own poll; passing None
    means the step must produce its own, which only the joystick arm can do. `idle_frames` is how
    many frames go by with no key at all before it arrives — each one shows the page and waits for
    the next VBL, which is the loop's SECOND wait site. `fire_arrives_at` is the idle frame whose
    VBL brings a joystick packet with FIRE down, which is how the joystick arm is driven without
    scheduling a scancode: the routine has to produce that itself.
    """
    arrival = idle_frames + 1
    schedule = [_store(NAME_ENTRY_IDLE_VBL_WAIT_PC, frame + 1, A_VBL_WAIT_FLAG, 0)
                for frame in range(idle_frames)]
    if fire_arrives_at is not None:
        schedule.append(_store(NAME_ENTRY_IDLE_VBL_WAIT_PC, fire_arrives_at, A_JOYSTICK_STATE,
                               JOYSTICK_FIRE))
    if key is not None:
        schedule.append(_store(NAME_ENTRY_KEY_WAIT_PC, arrival, A_KEY_SCANCODE, key))
    sites = [NAME_ENTRY_KEY_WAIT_PC, NAME_ENTRY_IDLE_VBL_WAIT_PC]
    extra = {A_OSK_CURSOR_X: (cursor_xy[0] << 16 | cursor_xy[1]).to_bytes(4, "big"),
             A_JOYSTICK_STATE: bytes([joystick]),
             A_NAME_ENTRY_CURSOR_HIT: bytes([0, from_joystick])}
    extra.update(record or {})
    pokes = _chain_pokes(seed, score=0, extra=extra)
    # THE CANDIDATE IS HANDED THE WHOLE REGISTER, not the low word, so that a reconstruction which
    # treated the cursor as a longword diverges here instead of being handed a clean value.
    d4 = (scratch_d4 << 16) | cursor
    regs = {"d4": d4, "a5": A_NAME_ENTRY_RECORD, "_pokes": pokes}
    diffs, info = differential(
        ENTRY_NAME_ENTRY_EDIT_STEP, regs,
        lambda lib, buf: lib.g_name_entry_edit_step(buf, d4),
        stop_pc=STEP_STOP_PC[step], schedule=schedule, wait_sites=sites,
        max_insns=CHAIN_MAX_INSNS, poison=poison)
    assert not diffs, f"{note} cursor={cursor} key={key}\n{report(diffs)}"
    assert info["ret"] == (step << NAME_ENTRY_STEP_SHIFT) | moved, (
        f"{note}: the candidate answered {info['ret']:#x}, not step {step} cursor {moved}")
    assert info["regs"]["d4"] & 0xffff == moved, (
        f"{note}: the oracle left D4 = {info['regs']['d4'] & 0xffff}, not {moved}")
    return info


@pytest.mark.parametrize("key", (SCANCODE_A, SCANCODE_B, SCANCODE_C))
def test_a_typed_letter_lands_at_the_cursor(key):
    """A letter goes into the record at the cursor's own index and the cursor steps one on.

    The record's index is the ORIGINAL'S `(0,a5,d4.w)`, so it carries the record's column and row
    bytes with it: a reconstruction that indexed from the first CHARACTER instead would write two
    bytes early and overwrite the coordinates.
    """
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=key, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR + 1, note="a letter")


def test_a_letter_is_stored_at_every_index_the_record_has():
    """Every slot of the name, so the block cursor's column and the record index move together."""
    for cursor in range(NAME_ENTRY_FIRST_CHAR, NAME_ENTRY_LAST_CHAR):
        _edit_step_case(cursor=cursor, key=SCANCODE_A, step=STEP_REDRAW, moved=cursor + 1,
                        seed=0x200 + cursor, note=f"index {cursor}")


def test_the_fifteenth_character_is_the_last():
    """`cmp.w #$11,d4` + `beq` — at the terminator's slot a letter is dropped and nothing is drawn.

    The two sides of that boundary are what the case drives: at NAME_ENTRY_LAST_CHAR - 1 the letter
    lands and the cursor reaches the cap, and AT the cap the step keeps the screen instead. A
    reconstruction whose cap was one out passes one of these and not the other.
    """
    _edit_step_case(cursor=NAME_ENTRY_LAST_CHAR - 1, key=SCANCODE_A, step=STEP_REDRAW,
                    moved=NAME_ENTRY_LAST_CHAR, note="the last free slot")
    _edit_step_case(cursor=NAME_ENTRY_LAST_CHAR, key=SCANCODE_A, step=STEP_KEEP,
                    moved=NAME_ENTRY_LAST_CHAR, note="the record is full")


@pytest.mark.parametrize("key", (SCANCODE_ESC, SCANCODE_UNDO))
def test_esc_and_undo_blank_the_whole_name(key):
    """Both clear every character back to CHAR_CLEAR_CELL and put the cursor back at the start —
    over a record with real characters in it, which is the only way the blanking is visible.

    WITH AN ATTRIBUTION PASS, because the sixteen bytes are the routine's whole output here and the
    record's terminator is already 0 in the shipped image: without poison, a candidate that wrote
    the three `#$1010101` longwords and skipped `NAME_ENTRY_BLANK_TAIL`'s low byte would match. The
    pass is legal on this arm — the only byte the schedule stores is the scancode, which nothing on
    this path writes.
    """
    _edit_step_case(cursor=NAME_ENTRY_LAST_CHAR, key=key, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR, record=_record_with(b"HOWIEHOWIEHOWIE"),
                    poison=True, note="clear the name")


@pytest.mark.parametrize("key", (SCANCODE_BACKSPACE, SCANCODE_DELETE))
def test_backspace_erases_one_character_and_stops_at_the_start(key):
    """The erase is a CHAR_CLEAR_CELL written back into the record, not a shortening of it — the
    record is always fifteen characters long — and `cmp.w #$2,d4` refuses to go below the first."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR + 3, key=key, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR + 2, record=_record_with(b"ABC"),
                    note="erase one")
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=key, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR, record=_record_with(b""),
                    note="nothing to erase")


@pytest.mark.parametrize("key", (SCANCODE_RETURN, SCANCODE_ENTER))
def test_return_and_enter_leave_for_the_commit(key):
    """Both leave at 0x1324a with the cursor untouched — the copy itself is past this slice."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR + 2, key=key, step=STEP_COMMIT,
                    moved=NAME_ENTRY_FIRST_CHAR + 2, record=_record_with(b"AB"), note="commit")


@pytest.mark.parametrize("key", (NAME_ENTRY_SCANCODE_MAX + 1, 0x7f))
def test_a_scancode_above_the_table_keeps_the_screen(key):
    """`cmp.b #$72` + `bgt` is a SIGNED byte compare, so only 0x73..0x7f are above the bound — and
    both of those index bytes that are perfectly printable, which is what makes the bound and the
    table's own answer separable. Neither reaches the record."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=key, step=STEP_KEEP,
                    moved=NAME_ENTRY_FIRST_CHAR, note=f"scancode {key:#04x}")


def test_a_scancode_with_bit_7_set_reads_below_the_table():
    """...and is NOT above the bound, because the compare is signed: 0x80 sign-extends to -128 and
    the lookup lands 128 bytes before the table, on the terminator of the message above it. That
    byte is a space, so the key TYPES — which is the arm a zero-extending reconstruction misses."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=0x80, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR + 1, note="scancode 0x80")


def test_an_unprintable_key_keeps_the_screen():
    """A table entry with bit 7 set (`bmi`) means "not a character" and nothing is stored."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=0x0c, step=STEP_KEEP,
                    moved=NAME_ENTRY_FIRST_CHAR, note="an unprintable key")


def test_d4_carries_its_high_word_through_the_step():
    """The cursor is a WORD in D4 and every instruction that moves or tests it is a word
    instruction, so the caller's high half comes back untouched — and, more to the point, cannot
    reach the record index. BOTH SIDES ARE GIVEN THE JUNK: a reconstruction that carried the cursor
    as a longword would index the record at `record + 0xbeef0002` and differ in the bytes, not just
    in a register the candidate never saw."""
    info = _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, step=STEP_REDRAW,
                           moved=NAME_ENTRY_FIRST_CHAR + 1, scratch_d4=0xbeef,
                           note="hi garbage in D4")
    assert info["regs"]["d4"] >> 16 == 0xbeef


@pytest.mark.parametrize("cursor,moved", ((0, 1), (1, 2), (0x12, 0x13), (0xffff, 0)))
def test_the_cursor_is_a_SIGNED_word_outside_the_loop_s_own_bounds(cursor, moved):
    """`(0,a5,d4.w)` SIGN-extends and `add.w` wraps, and only an entry from outside says so.

    The loop's own two guards keep D4 in [2, 0x11], so nothing inside it can tell a signed index
    from an unsigned one — but this entry point exists to be entered with any cursor, and each of
    these four lands somewhere a wrong reading would not: 0 and 1 write the record's own column and
    row bytes, 0x12 writes PAST the record into the high-score table's first byte (`beq` guards the
    cap, so only exactly 0x11 is refused), and 0xffff writes one byte BELOW the record while
    `add.w #$9` wraps its column back to 8 and `add.w #$1` wraps the cursor to 0. A zero-extending
    reconstruction writes 0x8000 bytes away instead, and an `unsigned` one answers 0x10000.
    """
    _edit_step_case(cursor=cursor, key=SCANCODE_A, step=STEP_REDRAW, moved=moved,
                    seed=0x1900 + cursor, note=f"cursor {cursor:#06x}")


def test_a_frame_without_fire_clears_the_joystick_flag_it_finds_set():
    """`sf $19ce4` runs on EVERY frame, before the fire test, and only a frame that starts with the
    flag already set can see it.

    The flag is what `name_entry_wait_for_release` forks on, so a reconstruction that only ever SET
    it would send the next pass of the loop into the fire-release wait instead of the scancode one —
    a different wait at a different site, which the arrival counts would then disagree about. Every
    other case here starts with the byte at 0, where the clear writes zero over zero.
    """
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, joystick=0,
                    from_joystick=SCC_BYTE_TRUE, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR + 1, seed=0x74, note="a stale joystick flag")


# ------------------------------------------------------------------------------------------------
# name_entry_redraw @ [0x13196, 0x131c4)
# ------------------------------------------------------------------------------------------------

def _redraw_case(cursor, record=None, scratch_d4=0, seed=0x2000, poison=False, note=""):
    """The REDRAW block for one cursor. No schedule and no waits — it draws and returns."""
    pokes = _chain_pokes(seed, score=0, extra=dict(record or {}))
    d4 = (scratch_d4 << 16) | cursor
    diffs, _ = differential(
        ENTRY_NAME_ENTRY_REDRAW, {"d4": d4, "a5": A_NAME_ENTRY_RECORD, "_pokes": pokes},
        lambda lib, buf: lib.g_name_entry_redraw(buf, d4),
        stop_pc=STOP_NAME_ENTRY_REDRAW, max_insns=CHAIN_MAX_INSNS, poison=poison)
    assert not diffs, f"{note} cursor={cursor:#06x}\n{report(diffs)}"


@pytest.mark.parametrize("cursor", tuple(range(NAME_ENTRY_FIRST_CHAR, NAME_ENTRY_LAST_CHAR + 1)))
def test_the_block_cursor_is_drawn_at_every_slot_and_hidden_at_the_cap(cursor):
    """Sixteen cursors: fifteen draw the block one column further along, and the sixteenth — exactly
    NAME_ENTRY_LAST_CHAR — draws none, which is the `bge` this block is here for."""
    _redraw_case(cursor, record=_record_with(b"ZY"), seed=0x2000 + cursor, note="every slot")


@pytest.mark.parametrize("cursor", (0, 1, 0x12, 0x40, 0x7fff, 0x8000, 0xffff))
def test_the_block_cursor_s_compare_is_SIGNED(cursor):
    """`cmp.w #$11,d4` + `bge` — so a NEGATIVE cursor is below the cap and the block IS drawn.

    That is the whole reason this block has an entry of its own: inside the loop D4 never leaves
    [2, 0x11], where a signed and an unsigned compare agree, and a reconstruction that made it
    unsigned passes every other case in this file. Here 0x8000 and 0xffff are negative and draw
    (their columns wrap back into the row with `add.w #$9`), while 0x12..0x7fff are above the cap
    and draw nothing — the two arms an unsigned reading gets exactly backwards at the top.
    """
    _redraw_case(cursor, record=_record_with(b"ZY"), seed=0x3000 + (cursor & 0xff),
                 note="signed compare")


def test_redraw_attribution():
    """Poison the block's own writes: no schedule here, so the pass is unconditional."""
    _redraw_case(NAME_ENTRY_FIRST_CHAR + 4, record=_record_with(b"ZYNAPS"), poison=True,
                 note="attribution")


def test_fire_on_a_key_types_it_without_the_acia():
    """THE JOYSTICK ARM: fire over a drawn key produces the scancode the routine then reads back.

    NO SCANCODE IS SCHEDULED. What the packet brings is FIRE, one frame in — so the byte the step
    dispatches on is the one the routine wrote itself, out of `onscreen_keyboard_hit_test` at the
    cursor's own position, and the whole chain from a screen coordinate to a character in the record
    is what the case holds. It also pins the `st` that marks this frame's key as the joystick's,
    which is what picks the release wait the NEXT pass of the loop makes.
    """
    info = _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=None, joystick=0, idle_frames=1,
                           fire_arrives_at=1, cursor_xy=(OSK_KEY_A_X, OSK_KEY_A_Y),
                           step=STEP_REDRAW, moved=NAME_ENTRY_FIRST_CHAR + 1, note="fire on 'A'")
    assert _wrote(info["writes"], A_NAME_ENTRY_FROM_JOYSTICK, what="the `st`") == bytes([SCC_BYTE_TRUE])
    assert _wrote(info["writes"], A_NAME_ENTRY_RECORD + NAME_ENTRY_FIRST_CHAR,
                  what="the insert") == b"A"


def test_fire_off_the_grid_produces_no_key_and_the_frame_goes_round():
    """Fire where there is no key answers 0, which is the same as no key at all: the page is shown,
    the loop waits for the next VBL, and the frame runs again. That second wait is the loop's other
    site — a run that took the first one twice instead would be counted at the wrong wait."""
    info = _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, joystick=JOYSTICK_FIRE,
                           idle_frames=1, step=STEP_REDRAW, moved=NAME_ENTRY_FIRST_CHAR + 1,
                           note="fire off the grid")
    assert _wrote(info["writes"], A_NAME_ENTRY_FROM_JOYSTICK, what="the `st`") == bytes([SCC_BYTE_TRUE])


@pytest.mark.parametrize("idle_frames", (1, 2, 3))
def test_a_frame_with_no_key_waits_and_draws_again(idle_frames):
    """Frames go by until a scancode arrives, and each one flips and waits. The arrival counts are
    what hold the loop: the kit compares the oracle's arrivals at each site against the candidate's
    polls, so a reconstruction that drew once and spun on the byte fails even though the bytes
    agree."""
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, idle_frames=idle_frames,
                    step=STEP_REDRAW, moved=NAME_ENTRY_FIRST_CHAR + 1, seed=0x300 + idle_frames,
                    note=f"{idle_frames} idle frames")


@pytest.mark.parametrize("direction,axis,delta", (
    (JOYSTICK_UP, A_OSK_CURSOR_Y, -OSK_CURSOR_STEP),
    (JOYSTICK_DOWN, A_OSK_CURSOR_Y, +OSK_CURSOR_STEP),
    (JOYSTICK_LEFT, A_OSK_CURSOR_X, -OSK_CURSOR_STEP),
    (JOYSTICK_RIGHT, A_OSK_CURSOR_X, +OSK_CURSOR_STEP)))
def test_each_direction_moves_the_cursor_two_pixels(direction, axis, delta):
    """One bit at a time, so a reconstruction that swapped two of the four is caught on both."""
    info = _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, joystick=direction,
                           step=STEP_REDRAW, moved=NAME_ENTRY_FIRST_CHAR + 1,
                           note=f"direction {direction:#04x}")
    moved_to = (OSK_HOME_X if axis == A_OSK_CURSOR_X else OSK_HOME_Y) + delta
    assert int.from_bytes(_wrote(info["writes"], axis, 2, "the cursor step"), "big") == moved_to


def test_opposite_directions_are_applied_in_turn_and_not_exclusively():
    """All four bits set at once: each is a separate `btst` applied where it is found, so the pairs
    cancel and the cursor ends where it started.

    WHAT THIS CATCHES is a reconstruction that made the pairs EXCLUSIVE — an `else if` chain, or a
    `switch` on the low nibble — which would move the cursor once and land two pixels away. WHAT IT
    CANNOT CATCH is one that nets the two into a single signed step per axis: that writes a
    different number of times to the same address with the same final value, and no memory surface
    separates them (an attribution pass does not either — the oracle writes the poisoned value
    straight back). Recorded as an equivalent reconstruction in STATUS.md rather than claimed.
    """
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A,
                    joystick=JOYSTICK_UP | JOYSTICK_DOWN | JOYSTICK_LEFT | JOYSTICK_RIGHT,
                    step=STEP_REDRAW, moved=NAME_ENTRY_FIRST_CHAR + 1, note="all four directions")


def test_edit_step_attribution():
    """Poison the step's own writes, on the TYPED arm — and only that arm can take the pass.

    `differential` refuses attribution over a byte the run's schedule also stores, because the agent
    overwrites the canary on both sides. Here the one scheduled byte is the scancode, and on the
    typed arm the routine does not write it (only a joystick pick does), so nothing clashes. The
    joystick arm cannot be poisoned: its packet arrives at the VBL wait, whose flag the routine
    writes itself.
    """
    _edit_step_case(cursor=NAME_ENTRY_FIRST_CHAR, key=SCANCODE_A, step=STEP_REDRAW,
                    moved=NAME_ENTRY_FIRST_CHAR + 1, poison=True, note="attribution")


EDIT_STEP_FUZZ_CHUNKS = 4
EDIT_STEP_CURSORS = (NAME_ENTRY_FIRST_CHAR, NAME_ENTRY_FIRST_CHAR + 1,
                     NAME_ENTRY_LAST_CHAR - 1, NAME_ENTRY_LAST_CHAR)


def _signed8(byte):
    return byte - 0x100 if byte & 0x80 else byte


def _expected_step(key, cursor):
    """The arm and the cursor the dispatch produces, derived the way the instructions run it."""
    if key in (SCANCODE_ESC, SCANCODE_UNDO):
        return STEP_REDRAW, NAME_ENTRY_FIRST_CHAR
    if key in (SCANCODE_BACKSPACE, SCANCODE_DELETE):
        return STEP_REDRAW, cursor - 1 if cursor != NAME_ENTRY_FIRST_CHAR else cursor
    if key in (SCANCODE_RETURN, SCANCODE_ENTER):
        return STEP_COMMIT, cursor
    if _signed8(key) > NAME_ENTRY_SCANCODE_MAX:
        return STEP_KEEP, cursor
    character = harness.BASE_IMAGE[A_SCANCODE_TO_CHAR_TABLE + _signed8(key)]
    if _signed8(character) < 0 or cursor == NAME_ENTRY_LAST_CHAR:
        return STEP_KEEP, cursor
    return STEP_REDRAW, cursor + 1


def _edit_step_fuzz_cases():
    """Every scancode paired with a cursor drawn ONCE, so the pairing does not move with the shard
    count. Choosing it by `key % EDIT_STEP_FUZZ_CHUNKS` would make which scancodes ever meet the
    fifteen-character cap an artefact of how many workers the file happens to shard into."""
    rng = random.Random(ENTRY_NAME_ENTRY_EDIT_STEP)   # seeded once; each chunk replays it
    for key in range(1, 0x100):
        yield key, rng.choice(EDIT_STEP_CURSORS)


@pytest.mark.parametrize("chunk", range(EDIT_STEP_FUZZ_CHUNKS))
def test_edit_step_fuzz(chunk):
    """Every scancode a byte can hold except 0, each at one of the four cursor positions that
    matter, against a record with characters already in it.

    Exhaustive rather than random because the dispatch forks EIGHT ways over one byte and three of
    the boundaries are single values; 0 is the one byte excluded, because it is what the loop spins
    ON and a schedule that stored it would never end.
    """
    record = _record_with(b"ZYNAPS")
    for case, (key, cursor) in enumerate(_edit_step_fuzz_cases()):
        if case % EDIT_STEP_FUZZ_CHUNKS != chunk:
            continue
        step, moved = _expected_step(key, cursor)
        _edit_step_case(cursor=cursor, key=key, step=step, moved=moved, record=record,
                        seed=0x1000 + key, note="fuzz")


# ------------------------------------------------------------------------------------------------
# highscore_enter_name @ 0x12fd4, whole
# ------------------------------------------------------------------------------------------------

# The four sites a typed name reaches. The commit's is declared even by a run that does not reach
# it: sites are what the counts are kept under, and an undeclared poll is a refusal.
TYPED_NAME_SITES = (NAME_ENTRY_VBL_WAIT_PC, NAME_ENTRY_KEY_RELEASE_WAIT_PC,
                    NAME_ENTRY_KEY_WAIT_PC, NAME_ENTRY_COMMIT_WAIT_PC)


def _typed_name_schedule(scancodes):
    """The stores that spell `scancodes` on the real keyboard, one key per pass of the loop.

    Each pass needs the VBL handler's clear before the loop will look at the keyboard, and the ACIA
    handler's scancode at the poll the loop spins on. Every pass but the first also needs the
    PREVIOUS key's release, because the loop waits for the scancode byte to go back to zero before
    it accepts another — which is the thing that makes a held key type once.

    Three passes is 2 + 3 + 3 = 8 stores, exactly `OS_SCHED_MAX`, so a run spells two characters and
    commits. STATUS.md's "## Coverage limits" carries that ceiling and what covers the rest.
    """
    stores = []
    for arrival, scancode in enumerate(scancodes, start=1):
        stores.append(_store(NAME_ENTRY_VBL_WAIT_PC, arrival, A_VBL_WAIT_FLAG, 0))
        if arrival > 1:
            stores.append(_store(NAME_ENTRY_KEY_RELEASE_WAIT_PC, arrival, A_KEY_SCANCODE, 0))
        stores.append(_store(NAME_ENTRY_KEY_WAIT_PC, arrival, A_KEY_SCANCODE, scancode))
    return stores


def _wrote(writes, addr, length=1, what=""):
    """`length` bytes the ORACLE stored at `addr`, or a named failure if it stored none.

    `info["writes"]` holds only addresses the run wrote, so a plain index raises `KeyError` on
    exactly the interesting failure — a store the case's schedule never got the run as far as. These
    assertions are ABOUT THE ORIGINAL, the way test_input.py's read-stream ones are: `assert not
    diffs` has already made the two images equal, so what they add is a statement of what the run
    was supposed to produce, which is what makes a mis-driven case fail as a mis-driven case.
    """
    missing = [at for at in range(length) if addr + at not in writes]
    assert not missing, (
        f"{what or 'the run'} never stored {'byte' if length == 1 else 'bytes'} "
        f"{', '.join(f'{addr + at:#x}' for at in missing)} — it did not get that far")
    return bytes(writes[addr + at] for at in range(length))


def _committed_name(writes, slot):
    """The sixteen bytes the run left in `slot`'s name area, out of the oracle's write set."""
    return _wrote(writes, slot + HIGHSCORE_NAME_OFFSET, NAME_ENTRY_CHARS + 1, "the commit")


def _typed_name_case(entry, glue, scancodes, slot, score, regs=None, seed=0x90, note=""):
    """Run `entry` while the keyboard spells `scancodes`, the last of which must commit."""
    pokes = _chain_pokes(seed, score=score)
    run_regs = dict(regs or {})
    run_regs["_pokes"] = pokes
    diffs, info = differential(entry, run_regs, glue, schedule=_typed_name_schedule(scancodes),
                               wait_sites=list(TYPED_NAME_SITES), max_insns=CHAIN_MAX_INSNS)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def test_enter_name_spells_a_name_and_commits_it():
    """PLEASE ENTER YOUR NAME, two letters typed, and RETURN — end to end, to the routine's `rts`.

    The name that lands in the slot is what this case is for: the record's fifteen characters and
    its terminator, copied to the slot's own name offset so that the entry's column and row bytes
    survive, exactly as they survive the shift-down that freed the slot. The SCORE goes in first,
    before a single character is typed, which a reconstruction that wrote it at the commit would
    get wrong only here.
    """
    slot = A_HIGHSCORE_TABLE + 2 * HIGHSCORE_ENTRY_BYTES
    info = _typed_name_case(ENTRY_HIGHSCORE_ENTER_NAME,
                            lambda lib, buf: lib.g_highscore_enter_name(buf, slot),
                            (SCANCODE_A, SCANCODE_B, SCANCODE_RETURN), slot=slot,
                            score=0x00123456, regs={"a0": slot}, note="AB then RETURN")
    assert _committed_name(info["writes"], slot) == (
        b"AB" + bytes([CHAR_CLEAR_CELL]) * (NAME_ENTRY_CHARS - 2) + b"\x00")
    assert _wrote(info["writes"], slot, 4, "the score") == (0x00123456).to_bytes(4, "big")


def test_enter_name_starts_the_cursor_at_the_keyboard_and_blanks_the_record():
    """The opening: the cursor is put at OSK_HOME, which is OFF the grid — the player has to move
    onto a key — and the record is blanked whatever it held, so a previous player's name cannot
    survive into this one's entry."""
    slot = A_HIGHSCORE_TABLE
    info = _typed_name_case(ENTRY_HIGHSCORE_ENTER_NAME,
                            lambda lib, buf: lib.g_highscore_enter_name(buf, slot),
                            (SCANCODE_RETURN,), slot=slot, score=0, regs={"a0": slot},
                            seed=0x91, note="commit at once")
    assert _wrote(info["writes"], A_OSK_CURSOR_X, 2, "the cursor home") == OSK_HOME_X.to_bytes(2, "big")
    assert _wrote(info["writes"], A_OSK_CURSOR_Y, 2, "the cursor home") == OSK_HOME_Y.to_bytes(2, "big")
    assert _committed_name(info["writes"], slot) == (
        bytes([CHAR_CLEAR_CELL]) * NAME_ENTRY_CHARS + b"\x00")


def test_enter_name_writes_the_score_into_the_slot_it_was_handed():
    """A0 IS AN ARGUMENT: three different slots, each getting the score and the name, so a
    reconstruction that hard-coded the table's first entry differs on two of the three."""
    for row in range(1, 4):
        slot = A_HIGHSCORE_TABLE + row * HIGHSCORE_ENTRY_BYTES
        info = _typed_name_case(ENTRY_HIGHSCORE_ENTER_NAME,
                                lambda lib, buf, slot=slot: lib.g_highscore_enter_name(buf, slot),
                                (SCANCODE_C, SCANCODE_RETURN), slot=slot, score=0x00009900,
                                regs={"a0": slot}, seed=0xa0 + row, note=f"slot {row}")
        assert _committed_name(info["writes"], slot)[:1] == b"C"


# ------------------------------------------------------------------------------------------------
# highscore_check_and_insert @ 0x12eae, and game_over_screen @ 0x12e66
# ------------------------------------------------------------------------------------------------

# A score above the shipped table's best and one below its worst — the two arms, off the .PRG's own
# five entries rather than off a table these cases invent, since the composition is what is under
# test here and the ranking has its own battery above.
SCORE_BEATS_THE_TABLE = 0x00990000
SCORE_MISSES_THE_TABLE = 0x00000001


def _not_rated_schedule(press_arrival=1, release_arrival=1):
    """Fire pressed at the `press_arrival`th look and released at the `release_arrival`th.

    Two separate waits on ONE byte, at two PCs — which is exactly the shape the kit keys a wait by
    the PC for: a single per-run counter could not tell the press loop's polls from the release
    loop's, and a port that dropped one of the two would balance against the other.
    """
    return [_store(NOT_RATED_FIRE_PRESS_WAIT_PC, press_arrival, A_JOYSTICK_STATE, JOYSTICK_FIRE),
            _store(NOT_RATED_FIRE_RELEASE_WAIT_PC, release_arrival, A_JOYSTICK_STATE, 0)]


NOT_RATED_SITES = (NOT_RATED_FIRE_PRESS_WAIT_PC, NOT_RATED_FIRE_RELEASE_WAIT_PC)


def _not_rated_case(entry, glue, stop_pc=0, press_arrival=1, release_arrival=1, joystick=0,
                    seed=0xb0, note=""):
    pokes = _chain_pokes(seed, score=SCORE_MISSES_THE_TABLE,
                         extra={A_JOYSTICK_STATE: bytes([joystick])})
    diffs, info = differential(entry, {"_pokes": pokes}, glue, stop_pc=stop_pc,
                               schedule=_not_rated_schedule(press_arrival, release_arrival),
                               wait_sites=list(NOT_RATED_SITES), max_insns=CHAIN_MAX_INSNS)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def test_a_score_that_misses_the_table_gets_the_not_rated_screen():
    """YOU ARE NOT RATED, and the routine answers 0.

    It draws into `screen_back` and NOT into the compose page the rated arm uses — the message goes
    on top of the GAME OVER already there and the flip shows it — which is the one thing a
    reconstruction that used one buffer for both screens gets wrong. It also clears the joystick
    byte first, so a fire that was already down when the screen appeared cannot satisfy the wait.
    """
    info = _not_rated_case(ENTRY_HIGHSCORE_CHECK_AND_INSERT,
                           lambda lib, buf: lib.g_highscore_check_and_insert(buf),
                           stop_pc=STOP_CHECK_AND_INSERT_NOT_RATED, note="not rated")
    assert info["ret"] == HIGHSCORE_NOT_RATED
    assert info["regs"]["d0"] & 0xff == HIGHSCORE_NOT_RATED


def test_the_not_rated_arm_pops_its_own_return_address():
    """THE FINDING THAT MAKES `game_over_screen`'S TAIL DEAD, stated as the oracle's own A0.

    0x12fba is a `movea.l (a7)+,a0` copied from the rated arm, whose matching push at 0x12f20 this
    arm never makes — so at the routine's `rts` A0 holds the caller's return address and A7 has
    already stepped past it. Entered here at 0x12eae, that address is the harness's own sentinel,
    which is what the assertion reads. The consequence is that the `bne` at 0x12e98 and the palette
    restore behind it never run on this arm; the rated arm reaches them and branches over them; so
    the reconstruction of `game_over_screen` ends at the call.
    """
    info = _not_rated_case(ENTRY_HIGHSCORE_CHECK_AND_INSERT,
                           lambda lib, buf: lib.g_highscore_check_and_insert(buf),
                           stop_pc=STOP_CHECK_AND_INSERT_NOT_RATED, seed=0xb1, note="the pop")
    assert info["regs"]["a0"] == harness.emu.SENTINEL, (
        f"A0 came back {info['regs']['a0']:#x}, not the return address the harness pushed — the "
        f"extra pop this row is about is not happening")


def test_the_not_rated_screen_clears_the_joystick_byte_before_it_waits():
    """`clr.b $19681` is what makes the wait a NEW press rather than one already in progress.

    The byte is poked with fire down and the packet that really presses it is put at the SECOND look
    — so with the clear the first look sees nothing and the wait goes round again, and without it
    the first look is already satisfied and the case's second store never comes due, which sinks the
    run. That is the only shape that separates the two: the byte ends the same either way.
    """
    _not_rated_case(ENTRY_HIGHSCORE_CHECK_AND_INSERT,
                    lambda lib, buf: lib.g_highscore_check_and_insert(buf),
                    stop_pc=STOP_CHECK_AND_INSERT_NOT_RATED, joystick=0xff, press_arrival=2,
                    seed=0xb8, note="fire already down")


def test_both_jingles_name_their_own_voice():
    """WHY THE CHANNEL `sound_start` IS HANDED CANNOT BE OBSERVED, read off the game's own data.

    Both calls pass D0, and D0 is whatever the palette `movem.l d0-d7` left in it — the first
    longword of the front-end palette, two instructions earlier. `sound_start` uses that only when
    the effect's stream carries no 0xfa channel header (include/sound.h), and both of these streams
    open with one. So the byte is dead for these two callers, a reconstruction that passed 0 behaves
    identically, and no case here can tell them apart. This is what says so — and it fails the day
    either stream changes, which is when the argument would need re-making.
    """
    for number in (SFX_NEW_HIGH_SCORE, SFX_YOU_ARE_NOT_RATED):
        offset = int.from_bytes(bytes(harness.BASE_IMAGE[A_TUNE_INDEX + number * 2:][:2]), "little")
        stream = A_TUNE_DATA + (offset - 0x10000 if offset & 0x8000 else offset)
        assert harness.BASE_IMAGE[stream] == SOUND_STREAM_CHANNEL_TAG, (
            f"sfx {number:#04x}'s stream at {stream:#x} no longer opens with a channel header, so "
            f"the D0 the two call sites pass has stopped being unobservable")


@pytest.mark.parametrize("press_arrival,release_arrival", ((1, 1), (3, 1), (1, 4), (2, 2)))
def test_the_not_rated_screen_waits_for_a_press_and_then_a_release(press_arrival, release_arrival):
    """Both waits go round as many times as the case says, and each round sends the interrogate
    command again — so the arrival counts, not the final byte, are what hold the two loops."""
    _not_rated_case(ENTRY_HIGHSCORE_CHECK_AND_INSERT,
                    lambda lib, buf: lib.g_highscore_check_and_insert(buf),
                    stop_pc=STOP_CHECK_AND_INSERT_NOT_RATED, press_arrival=press_arrival,
                    release_arrival=release_arrival, seed=0x400 + 8 * press_arrival + release_arrival,
                    note=f"press {press_arrival} release {release_arrival}")


def test_game_over_screen_not_rated_end_to_end():
    """The whole chain on the arm that does not rate, to `rts` — the ONLY entry that reaches one on
    this arm, because `highscore_check_and_insert`'s own `rts` returns one level too far.

    A0 says so from here too: what comes back is the address of the `bne` that would have run the
    palette restore, which is the return address this arm popped instead of returning to.
    """
    info = _not_rated_case(ENTRY_GAME_OVER_SCREEN, lambda lib, buf: lib.g_game_over_screen(buf),
                           seed=0xc0, note="game over, not rated")
    assert info["regs"]["a0"] == GAME_OVER_DEAD_TAIL


def test_game_over_screen_rated_end_to_end():
    """...and on the arm that does: GAME OVER PLAYER, the ranking and its shift-down, NEW HIGH
    SCORE into the compose page, the name typed, and the PSG silenced on the way out.

    The two screens of this arm are drawn into DIFFERENT buffers, one paragraph apart, and the name
    lands in table row 0 because the score beats every entry — so the shift-down has moved all five
    rows down before a character is typed, which is what the committed bytes are checked against.
    """
    slot = A_HIGHSCORE_TABLE
    info = _typed_name_case(ENTRY_GAME_OVER_SCREEN,
                            lambda lib, buf: lib.g_game_over_screen(buf),
                            (SCANCODE_A, SCANCODE_C, SCANCODE_RETURN), slot=slot,
                            score=SCORE_BEATS_THE_TABLE, seed=0xc1, note="game over, rated")
    assert _committed_name(info["writes"], slot) == (
        b"AC" + bytes([CHAR_CLEAR_CELL]) * (NAME_ENTRY_CHARS - 2) + b"\x00")


def test_check_and_insert_rated_answers_one():
    """The rated arm reaches its own `rts` (nothing has been popped that should not have been) and
    answers 1, which is the value the dead `bne` above it would have branched on."""
    slot = A_HIGHSCORE_TABLE
    info = _typed_name_case(ENTRY_HIGHSCORE_CHECK_AND_INSERT,
                            lambda lib, buf: lib.g_highscore_check_and_insert(buf),
                            (SCANCODE_B, SCANCODE_RETURN), slot=slot,
                            score=SCORE_BEATS_THE_TABLE, seed=0xc2, note="rated")
    assert info["ret"] == HIGHSCORE_RATED
    assert info["regs"]["d0"] & 0xff == HIGHSCORE_RATED


@pytest.mark.parametrize("rank", range(HIGHSCORE_ENTRIES))
def test_the_name_goes_into_the_row_the_ranking_chose(rank):
    """A score that beats exactly the entries below `rank`, all the way through to the name landing
    in that row of the table — which is what joins the ranking half to the entry half. The shipped
    table's five scores are what the score is derived from, so the case cannot rank itself."""
    shipped = [int.from_bytes(bytes(harness.BASE_IMAGE[A_HIGHSCORE_TABLE
                                                       + row * HIGHSCORE_ENTRY_BYTES:][:4]), "big")
               for row in range(HIGHSCORE_ENTRIES)]
    slot = A_HIGHSCORE_TABLE + rank * HIGHSCORE_ENTRY_BYTES
    info = _typed_name_case(ENTRY_GAME_OVER_SCREEN,
                            lambda lib, buf: lib.g_game_over_screen(buf),
                            (SCANCODE_C, SCANCODE_RETURN), slot=slot, score=shipped[rank] + 1,
                            seed=0xd0 + rank, note=f"rank {rank}")
    assert _committed_name(info["writes"], slot)[:1] == b"C"


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_HIGHSCORE_TABLE", "include/highscore.h", "A_highscore_table"),
    ("HIGHSCORE_ENTRIES", "include/highscore.h", "HIGHSCORE_ENTRIES"),
    ("HIGHSCORE_ENTRY_BYTES", "include/highscore.h", "HIGHSCORE_ENTRY_BYTES"),
    ("HIGHSCORE_ENTRY_RECORD", "include/highscore.h", "HIGHSCORE_ENTRY_RECORD"),
    ("HIGHSCORE_DIGITS_COLUMN", "include/highscore.h", "HIGHSCORE_DIGITS_COLUMN"),
    ("HIGHSCORE_FIRST_SCORE_OFFSET", "include/highscore.h", "HIGHSCORE_FIRST_SCORE_OFFSET"),
    ("HIGHSCORE_SCORE_ROW_STEP", "include/highscore.h", "HIGHSCORE_SCORE_ROW_STEP"),
    ("HIGHSCORE_SHIFT_NAME_BYTES", "include/highscore.h", "HIGHSCORE_SHIFT_NAME_BYTES"),
    ("HIGHSCORE_NAME_OFFSET", "include/highscore.h", "HIGHSCORE_NAME_OFFSET"),
    ("GAME_OVER_DIGIT_ROW_OFFSET", "include/highscore.h", "GAME_OVER_DIGIT_ROW_OFFSET"),
    ("A_MSG_GAME_OVER_PLAYER", "include/highscore.h", "A_msg_game_over_player"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("A_CURRENT_PLAYER_INDEX", "include/hud.h", "A_current_player_index"),
    ("PLAYER_DIGIT_CHAR_ZERO", "include/hud.h", "PLAYER_DIGIT_CHAR_ZERO"),
    ("A_ZYNAPS_LOGO", "include/hud.h", "A_zynaps_logo"),
    ("LOGO_STRIPS", "include/hud.h", "LOGO_STRIPS"),
    ("LOGO_STRIP_BYTES", "include/hud.h", "LOGO_STRIP_BYTES"),
    ("A_FONT_GLYPHS", "include/text.h", "A_font_glyphs"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("A_MSG_NEW_HIGH_SCORE", "include/highscore.h", "A_msg_new_high_score"),
    ("A_MSG_YOU_ARE_NOT_RATED", "include/highscore.h", "A_msg_you_are_not_rated"),
    ("SFX_NEW_HIGH_SCORE", "include/highscore.h", "SFX_NEW_HIGH_SCORE"),
    ("SFX_YOU_ARE_NOT_RATED", "include/highscore.h", "SFX_YOU_ARE_NOT_RATED"),
    ("HIGHSCORE_RATED", "include/highscore.h", "HIGHSCORE_RATED"),
    ("HIGHSCORE_NOT_RATED", "include/highscore.h", "HIGHSCORE_NOT_RATED"),
    ("A_TEXT_PLEASE_ENTER_NAME", "include/highscore.h", "A_text_please_enter_name"),
    ("A_TEXT_OSK_ROW1", "include/highscore.h", "A_text_osk_row1"),
    ("A_TEXT_OSK_ROW2", "include/highscore.h", "A_text_osk_row2"),
    ("A_TEXT_OSK_ROW3", "include/highscore.h", "A_text_osk_row3"),
    ("A_NAME_ENTRY_RECORD", "include/highscore.h", "A_name_entry_record"),
    ("NAME_ENTRY_FIRST_CHAR", "include/highscore.h", "NAME_ENTRY_FIRST_CHAR"),
    ("NAME_ENTRY_LAST_CHAR", "include/highscore.h", "NAME_ENTRY_LAST_CHAR"),
    ("A_NAME_ENTRY_FROM_JOYSTICK", "include/highscore.h", "A_name_entry_from_joystick"),
    ("A_NAME_ENTRY_CURSOR_HIT", "include/highscore.h", "A_name_entry_cursor_hit"),
    ("A_SCANCODE_TO_CHAR_TABLE", "include/highscore.h", "A_scancode_to_char_table"),
    ("NAME_ENTRY_SCANCODE_MAX", "include/highscore.h", "NAME_ENTRY_SCANCODE_MAX"),
    ("SCANCODE_ESC", "include/highscore.h", "SCANCODE_ESC"),
    ("SCANCODE_UNDO", "include/highscore.h", "SCANCODE_UNDO"),
    ("SCANCODE_BACKSPACE", "include/highscore.h", "SCANCODE_BACKSPACE"),
    ("SCANCODE_DELETE", "include/highscore.h", "SCANCODE_DELETE"),
    ("SCANCODE_RETURN", "include/highscore.h", "SCANCODE_RETURN"),
    ("SCANCODE_ENTER", "include/highscore.h", "SCANCODE_ENTER"),
    ("A_JOYSTICK_STATE", "include/highscore.h", "A_joystick_state"),
    ("JOYSTICK_UP", "include/highscore.h", "JOYSTICK_UP"),
    ("JOYSTICK_DOWN", "include/highscore.h", "JOYSTICK_DOWN"),
    ("JOYSTICK_LEFT", "include/highscore.h", "JOYSTICK_LEFT"),
    ("JOYSTICK_RIGHT", "include/highscore.h", "JOYSTICK_RIGHT"),
    ("JOYSTICK_FIRE", "include/highscore.h", "JOYSTICK_FIRE"),
    ("IKBD_CMD_JOYSTICK_INTERROGATE", "include/highscore.h", "IKBD_CMD_JOYSTICK_INTERROGATE"),
    ("A_GUNSIGHT_SPRITE", "include/highscore.h", "A_gunsight_sprite"),
    ("GUNSIGHT_ROWS", "include/highscore.h", "GUNSIGHT_ROWS"),
    ("OSK_HOME_X", "include/highscore.h", "OSK_HOME_X"),
    ("OSK_HOME_Y", "include/highscore.h", "OSK_HOME_Y"),
    ("OSK_CURSOR_STEP", "include/highscore.h", "OSK_CURSOR_STEP"),
    ("NAME_ENTRY_ROW_OFFSET", "include/highscore.h", "NAME_ENTRY_ROW_OFFSET"),
    ("NAME_ENTRY_CURSOR_COLUMN_BIAS", "include/highscore.h", "NAME_ENTRY_CURSOR_COLUMN_BIAS"),
    ("NAME_ENTRY_NAME_LONGS", "include/highscore.h", "NAME_ENTRY_NAME_LONGS"),
    ("NAME_ENTRY_BLANK_FILL", "include/highscore.h", "NAME_ENTRY_BLANK_FILL"),
    ("NAME_ENTRY_BLANK_TAIL", "include/highscore.h", "NAME_ENTRY_BLANK_TAIL"),
    ("NAME_ENTRY_STEP_SHIFT", "include/highscore.h", "NAME_ENTRY_STEP_SHIFT"),
    ("NAME_ENTRY_STEP_CURSOR_MASK", "include/highscore.h", "NAME_ENTRY_STEP_CURSOR_MASK"),
    ("NAME_ENTRY_KEY_WAIT_PC", "include/highscore.h", "NAME_ENTRY_KEY_WAIT_PC"),
    ("NAME_ENTRY_IDLE_VBL_WAIT_PC", "include/highscore.h", "NAME_ENTRY_IDLE_VBL_WAIT_PC"),
    ("NAME_ENTRY_VBL_WAIT_PC", "include/highscore.h", "NAME_ENTRY_VBL_WAIT_PC"),
    ("NAME_ENTRY_FIRE_RELEASE_WAIT_PC", "include/highscore.h", "NAME_ENTRY_FIRE_RELEASE_WAIT_PC"),
    ("NAME_ENTRY_KEY_RELEASE_WAIT_PC", "include/highscore.h", "NAME_ENTRY_KEY_RELEASE_WAIT_PC"),
    ("NAME_ENTRY_COMMIT_WAIT_PC", "include/highscore.h", "NAME_ENTRY_COMMIT_WAIT_PC"),
    ("NOT_RATED_FIRE_PRESS_WAIT_PC", "include/highscore.h", "NOT_RATED_FIRE_PRESS_WAIT_PC"),
    ("NOT_RATED_FIRE_RELEASE_WAIT_PC", "include/highscore.h", "NOT_RATED_FIRE_RELEASE_WAIT_PC"),
    ("SCC_BYTE_TRUE", "include/enemy.h", "SCC_BYTE_TRUE"),
    ("SCC_BYTE_FALSE", "include/enemy.h", "SCC_BYTE_FALSE"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_KEY_SCANCODE", "include/init.h", "A_key_scancode"),
    ("A_VBL_WAIT_FLAG", "include/irq.h", "A_vbl_wait_flag"),
    ("A_MENU_PALETTE", "include/irq.h", "A_menu_palette"),
    ("CHAR_CLEAR_CELL", "include/text.h", "CHAR_CLEAR_CELL"),
    ("CHAR_FILL_CELL", "include/text.h", "CHAR_FILL_CELL"),
    ("A_OSK_CURSOR_X", "include/input.h", "A_osk_cursor_x"),
    ("A_OSK_CURSOR_Y", "include/input.h", "A_osk_cursor_y"),
    ("A_TUNE_INDEX", "include/sound.h", "A_tune_index"),
    ("A_TUNE_DATA", "include/sound.h", "A_tune_data"),
    ("SOUND_STREAM_CHANNEL_TAG", "include/sound.h", "SOUND_STREAM_CHANNEL_TAG"),
    ("A_PALETTE_FRONTEND", "include/hud.h", "A_palette_frontend"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
    ("PLAYFIELD_BYTES", "include/video.h", "PLAYFIELD_BYTES"),
    ("SHIFTER_PALETTE_PAIRS", "include/video.h", "SHIFTER_PALETTE_PAIRS"),
)
ENTRY_PROLOGUES = {
    # Ten bytes is not enough here: `title_screen_draw` @ 0x12a28 opens with the SAME
    # `lea $6c8ee,a6 / movea.l $1797e,a0` and the two separate only at byte 16.
    "ENTRY_ROLE_OF_HONOUR_SCREEN": "4df90006c8ee20790001797e2f086100f626",
    "ENTRY_GAME_OVER_SCREEN": "61002b1420790001797e",
    "ENTRY_HIGHSCORE_RANK_AND_SHIFT": "2239000195e041f900019db2",
    "ENTRY_HIGHSCORE_CHECK_AND_INSERT": "610001122239000195e0",
    "ENTRY_HIGHSCORE_ENTER_NAME": "2f08207c0001a8ae4df9",
    "ENTRY_NAME_ENTRY_EDIT_STEP": "45f900017a8e35790001",
    "ENTRY_NAME_ENTRY_REDRAW": "207c0001a8ae2c4d2f04",
}
