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
# Two SLICES of routines the kit cannot run whole (STATUS.md): each is `[entry, stop)`, and the
# ranking one has two stops because its two arms leave at different addresses.
ENTRY_GAME_OVER_SCREEN_PROLOGUE = 0x12e66
STOP_GAME_OVER_SCREEN_PROLOGUE = 0x12e94      # the `bsr` into `highscore_check_and_insert`
ENTRY_HIGHSCORE_RANK_AND_SHIFT = 0x12eb2
STOP_HIGHSCORE_RATED = 0x12f0e                # both the shift and the no-shift arm converge here
STOP_HIGHSCORE_NOT_RATED = 0x12f5a            # ...and the `beq` at 0x12ed4 leaves for here

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
SCREEN_BACK_BUFFER = abi.SCREEN_BACK
SCREEN_FRONT_BUFFER = abi.SCREEN_FRONT

harness._lib.g_role_of_honour_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_role_of_honour_screen.restype = None
harness._lib.g_game_over_screen_prologue.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_over_screen_prologue.restype = None
harness._lib.g_highscore_rank_and_shift.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_highscore_rank_and_shift.restype = ctypes.c_uint32


def _pokes(seed, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None):
    """Noise over both framebuffers, the real font and the real ZYNAPS logo, plus a case's own.

    Both graphics are bss — `_start` loads EXTCHARS.DAT and ZYNLOGO.DAT over them — so against a
    fresh image every glyph and every logo strip would blit zeroes and a wrong source address would
    be invisible. The guard bands are what turn a blit one row too far into a difference.
    """
    spans = [(back, back + SCREEN_BYTES), (front, front + SCREEN_BYTES)]
    pokes = seed_spans(seed, spans, guard=abi.GUARD_BYTES)
    pokes[A_FONT_GLYPHS] = (DISK / "EXTCHARS.DAT").read_bytes()
    pokes[A_ZYNAPS_LOGO] = (DISK / "ZYNLOGO.DAT").read_bytes()
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
    """The five-entry table rebuilt from (score, column, row, name) tuples."""
    blob = b""
    for score, column, row, name in entries:
        name = name.ljust(HIGHSCORE_ENTRY_BYTES - HIGHSCORE_ENTRY_RECORD - 3, b" ")
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
    diffs, _ = differential(ENTRY_GAME_OVER_SCREEN_PROLOGUE, {"_pokes": pokes},
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


def _rank_case(score, table=None, rank=None, note=""):
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
                              lambda lib, buf: lib.g_highscore_rank_and_shift(buf), stop_pc=stop)
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
)
ENTRY_PROLOGUES = {
    # Ten bytes is not enough here: `title_screen_draw` @ 0x12a28 opens with the SAME
    # `lea $6c8ee,a6 / movea.l $1797e,a0` and the two separate only at byte 16.
    "ENTRY_ROLE_OF_HONOUR_SCREEN": "4df90006c8ee20790001797e2f086100f626",
    "ENTRY_GAME_OVER_SCREEN_PROLOGUE": "61002b1420790001797e",
    "ENTRY_HIGHSCORE_RANK_AND_SHIFT": "2239000195e041f900019db2",
}
