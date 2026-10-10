"""THE EVENT TAPE (`src/aes/aptape.c`: ap_trecd `$fe6766`, ap_tplay `$fe6610`) against the ROM — `test/aes_aptape.py`
has the machines: recordings the ROM's own ap_trecd made with real interrupts taken, and playbacks of them.

EVERY CASE SWITCHES (ap_trecd sleeps until the recorder stops, ap_tplay yields round each record), so every case is a
row that switches, held four ways:
  * THE PREMISE on the ROM's own run through its dispatcher: what it takes at which idle, who is entered, what it
    answers — and, for a recording, the records it leaves;
  * AT THE DISPATCHER (`aes_event.switches_where_the_rom_does`): the C's image where it first leaves — ap_trecd with
    the recorder armed and its first sleep queued, ap_tplay at its first yield, nothing stored yet;
  * TIER 1 THROUGH THE HOST'S SCHEDULER (`aes_switching.companion`): the C taken on to its return, the same idles and
    polls, every byte outside the run's own stack the ROM's;
  * ON BOTH BLOBS, AND IN THE TABLE: the real switch through our own dispatcher, its cycles pinned on both counts.

AND WHAT THE ROM DOES THAT A READER WOULD NOT EXPECT, each reproduced and held, never mended: a count of 0 (or below)
records all the same; a scale of 0 is the Alcyon runtime's divide by zero; a record's number is its LOW WORD, and a
number that is none of the four is a code address forker calls; A RECORDING PAST 32,767 BYTES (4,096 records and
more, which a count of 0 reaches) IS COUNTED BELOW 0 — ap_trecd answers a negative word and numbers NO record, the
buffer left holding the fork functions' addresses; a timer record's ticks are a LONG; and ap_trecd leaves in D0's
high word that of the last fork function's address it compared (`$00fe`), or of the cursor's distance where it
numbered none.
"""
import re

import pytest

from harness import addrs, make_image
from recreate_kit import rom_bench

import aes
import aes_aptape as tape
import aes_event
import aes_switch
import aes_switching as switching
import case
import test_aes_evfork_interrupted as between_instructions
import vdi

SHELL, SCREEN_MANAGER = tape.SHELL, tape.SCREEN_MANAGER
BENCH, SHIPPED = "bench", "bench_shipped"
Premise, Priced = switching.Premise, switching.Priced
ROWS, RECORDINGS = tape.EVERY_ROW, tape.RECORDINGS
ARGUMENT_CLASS_ROWS = tape.ARGUMENT_ROWS
HIGH_WORDS, A_ROUTINE_S_ADDRESS, AT_AN_ODD_ADDRESS, TICKS_A_LONG = ARGUMENT_CLASS_ROWS
ACROSS_A_WINDOW = tape.RECORDING_LABELS[tape.ONTO_AND_OFF_THE_BAR]
PLAYED, CURSOR_SHOWN, ONTO_THE_BAR = tape.PLAYED, tape.PLAYED_THE_CURSOR_SHOWN, tape.PLAYED_ONTO_THE_BAR
NO_MOUSE_RECORD, NONE_PLAYED = tape.NO_MOUSE_RECORD, tape.NONE_PLAYED


def _recording(name):
    return tape.RECORDING_LABELS[name]


# ---- WHAT EACH ROW IS, read off the ROM's own run of it (`aes_switching.Premise`): the idles it takes a delivery at,
# the idles it makes, the process that makes the call, EVERY PROCESS ITS DISPATCHER ENTERS IN ORDER — one entry a
# sleep woken (ap_trecd), one a yield and one more a timer record waited out (ap_tplay) — and the word it answers
# (ap_trecd: the records made; ap_tplay sets no D0).
ONCE, TWICE, THRICE = (SHELL,), (SHELL,) * 2, (SHELL,) * 3
PREMISES = {
    _recording(tape.FULL): Premise((0,), 1, SHELL, ONCE, 4),
    _recording(tape.MERGED): Premise((0, 1, 2), 3, SHELL, THRICE, 2),
    _recording(tape.A_KEY): Premise((0, 1), 2, SHELL, ONCE, 1),
    _recording(tape.ENDED_EARLY): Premise((0, 1, 2), 3, SHELL, ONCE, 3),
    _recording(tape.NOTHING): Premise((0, 1), 2, SHELL, ONCE, 0),
    _recording(tape.UNASKED): Premise((0, 1, 2), 3, SHELL, TWICE, 4),
    _recording(tape.UNASKED_BELOW_ZERO): Premise((0, 1, 2), 3, SHELL, TWICE, 3),
    _recording(tape.CURSOR_SHOWN): Premise((0,), 1, SHELL, ONCE, 4),
    ACROSS_A_WINDOW: Premise((0, 1, 2), 3, SHELL, (SCREEN_MANAGER, SCREEN_MANAGER, SHELL), 3),
    _recording(tape.A_WHOLE_CLICK): Premise((0,), 1, SHELL, ONCE, 5),
    # four records: the first yield, a yield a move, the wait woken, its yield, the press's yield
    PLAYED: Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    tape.PLAYED_SLOWLY: Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    NONE_PLAYED: Premise((), 0, SHELL, ONCE, None),
    NO_MOUSE_RECORD: Premise((0,), 1, SHELL, (SHELL,) * 4, None),
    tape.A_KEY_PLAYED: Premise((), 0, SHELL, TWICE, None),
    tape.SHIFT_KEYS_PLAYED: Premise((), 0, SHELL, (SHELL,) * 4, None),
    CURSOR_SHOWN: Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    # the move onto the bar is run by forker under the SECOND yield, which comes back to the desk (ready before the
    # manager was woken); the THIRD yield enters the screen manager
    ONTO_THE_BAR: Premise((), 0, SHELL, (SHELL, SHELL, SCREEN_MANAGER, SHELL, SHELL), None),
    tape.NONE_PLAYED_BELOW_ZERO: Premise((), 0, SHELL, ONCE, None),
    "two of four records played: the moves alone": Premise((), 0, SHELL, THRICE, None),
    "a whole click played": Premise((0,), 1, SHELL, (SHELL,) * 7, None),
    "four records played at a third: the wait is eight ticks": Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    tape.PLAYED_BACKWARDS: Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    HIGH_WORDS: Premise((0,), 1, SHELL, (SHELL,) * 6, None),
    A_ROUTINE_S_ADDRESS: Premise((), 0, SHELL, TWICE, None),
    AT_AN_ODD_ADDRESS: Premise((), 0, SHELL, THRICE, None),
    # one timer record: the first yield, the wait of 100 ms woken by ap_trecd's own poll of ticks, its yield
    TICKS_A_LONG: Premise((0,), 1, SHELL, THRICE, None),
}
# The rows a blob runs: the priced ones — and, unregistered (the second differential alone), the count and the scale
# below 0 (signed words, each: a build that read one unsigned shows nowhere else on target) and the two of the
# labelled class whose records are no code address.
ON_BOTH_BLOBS = (*tape.PRICED, tape.NONE_PLAYED_BELOW_ZERO, tape.PLAYED_BACKWARDS, HIGH_WORDS, AT_AN_ODD_ADDRESS)
# THE WHOLE RUN'S CYCLES, the ROM's and ours net of the entry both share, by blob — the second differential's own
# measurement (`aes_switching.measured_on`) — for every priced row and the two of the labelled class a blob runs
# (unregistered: the second differential alone). A row that moves says why: a frame, a path, the dispatcher itself.
# AND WHAT THE TABLE PRICES (`aes_switching.Priced`; `tier3.measure`, the shipped blob): each shore's OWN cycles; THE
# CALLER'S OWN, net of the calls of rebound entries, and how many it closes — ev_timer's ev_block, once a sleep and
# once a timer record (a playback of no timer record calls none: one count); and the row's foreign windows.
NO_WINDOW = switching.NO_WINDOW
THE_MANAGER_S_TURN = (1, 65624, 52100)  # the screen manager's own run with the mouse on its bar: the ROM's, on both shores
# @PINS-BEGIN (measured: scratch `pins.py`)
WHOLE_RUN = {
    'two moves, the ticks and a press recorded: the buffer full':
        {BENCH: (47218, 40418), SHIPPED: (47218, 39678)},
    'ticks recorded over three sleeps, merged into one record; then a press':
        {BENCH: (100142, 83114), SHIPPED: (100142, 82458)},
    "one record, a key's":
        {BENCH: (46782, 39054), SHIPPED: (46782, 38896)},
    'ended by Control-backslash before the buffer is full':
        {BENCH: (67926, 58824), SHIPPED: (67926, 58506)},
    'a count of 0, ended at once: nothing recorded':
        {BENCH: (45914, 38054), SHIPPED: (45914, 38078)},
    'a count of 0, events before it is ended: all recorded':
        {BENCH: (91628, 77904), SHIPPED: (91628, 77188)},
    'four records played: two moves, a wait, a press':
        {BENCH: (127008, 112164), SHIPPED: (127008, 113724)},
    'four records played slowly: the wait is twenty-five ticks':
        {BENCH: (127198, 112368), SHIPPED: (127198, 113914)},
    'none of four records played: a count of 0':
        {BENCH: (12180, 10844), SHIPPED: (12180, 10964)},
    'a wait and a press played: no mouse record':
        {BENCH: (71054, 61100), SHIPPED: (71054, 61780)},
    'a key played':
        {BENCH: (26936, 23178), SHIPPED: (26936, 23420)},
    'two moves and the shift keys played':
        {BENCH: (83320, 75278), SHIPPED: (83320, 76402)},
    "four records played, the cursor shown: the VDI's cursor routine queues each point":
        {BENCH: (127192, 112348), SHIPPED: (127192, 113908)},
    'the mouse played onto the menu bar and off it: the screen manager entered from a yield':
        {BENCH: (167922, 155392), SHIPPED: (167922, 156652)},
    'none played: a count below 0':
        {BENCH: (12180, 10844), SHIPPED: (12180, 10964)},
    'four records played at a negative scale: the wait is no tick':
        {BENCH: (127064, 112192), SHIPPED: (127064, 113780)},
    'ARGUMENT CLASS (records no recording holds): four numbers with a high word, played as their low words':
        {BENCH: (118520, 103224), SHIPPED: (118520, 104674)},
    'ARGUMENT CLASS (records no recording holds): two records at an odd address':
        {BENCH: (68138, 62078), SHIPPED: (68138, 63082)},
}
PRICED = {
    'two moves, the ticks and a press recorded: the buffer full':
        Priced((20758, 29658), (1778, 3566), 1, (0, 0, 0)),   # 0.70 / 0.50
    'ticks recorded over three sleeps, merged into one record; then a press':
        Priced((39438, 59570), (3158, 5306), 3, (0, 0, 0)),   # 0.66 / 0.60
    "one record, a key's":
        Priced((16462, 25476), (1506, 2850), 1, (0, 0, 0)),   # 0.65 / 0.53
    'ended by Control-backslash before the buffer is full':
        Priced((24598, 35822), (1690, 3326), 1, (0, 0, 0)),   # 0.69 / 0.51
    'a count of 0, ended at once: nothing recorded':
        Priced((15752, 24608), (1350, 2612), 1, (0, 0, 0)),   # 0.64 / 0.52
    'a count of 0, events before it is ended: all recorded':
        Priced((35942, 52762), (2560, 4674), 2, (0, 0, 0)),   # 0.68 / 0.55
    'four records played: two moves, a wait, a press':
        Priced((41656, 58612), (30468, 41570), 2, (0, 0, 0)),   # 0.71 / 0.73
    'four records played slowly: the wait is twenty-five ticks':
        Priced((41846, 58802), (30660, 41762), 2, (0, 0, 0)),   # 0.71 / 0.73
    'none of four records played: a count of 0':
        Priced((3926, 5418), None, None, (0, 0, 0)),   # 0.72
    'a wait and a press played: no mouse record':
        Priced((26178, 37244), (14990, 20202), 2, (0, 0, 0)),   # 0.70 / 0.74
    'a key played':
        Priced((9344, 13412), None, None, (0, 0, 0)),   # 0.70
    'two moves and the shift keys played':
        Priced((25160, 34510), None, None, (0, 0, 0)),   # 0.73
    "four records played, the cursor shown: the VDI's cursor routine queues each point":
        Priced((41656, 58612), (30468, 41570), 2, (0, 0, 0)),   # 0.71 / 0.73
    'the mouse played onto the menu bar and off it: the screen manager entered from a yield':
        Priced((32158, 46136), None, None, (1, 65624, 52100)),   # 0.70
}
# @PINS-END
WINDOWS = {label: priced.windows for label, priced in PRICED.items() if priced.windows != NO_WINDOW}


def test_every_priced_row_is_registered_and_pinned():
    """The registry holds the priced rows (`aes_aptape.register`), each with its premise and both its pins; every
    other row has its premise, and is Tier 1's alone."""
    assert set(tape.REGISTERED) <= set(aes_event.SWITCHING_ROWS)
    assert {row.label for row in tape.REGISTERED.values()} == tape.PRICED.keys() == PRICED.keys()
    assert PREMISES.keys() == ROWS.keys() and WHOLE_RUN.keys() == set(ON_BOTH_BLOBS)
    assert not ARGUMENT_CLASS_ROWS.keys() & tape.PRICED.keys(), "the labelled class is in no registry"
    assert WINDOWS == {ONTO_THE_BAR: THE_MANAGER_S_TURN}, "one priced row has another process's turn in it"


# ---- THE MACHINES: a recording is the ROM's own, and holds what its name says --------------------------------------------------
# WHAT THE ROM LEAVES ABOVE ap_trecd's ANSWER, recorded and not compared with ours: the routine sets D0 as a WORD
# (`$fe6816 move.w d6,d0`) over whatever the register held — the last record's code as its loop loaded it to compare
# (`$fe67fc move.l -4(a6),d0`: a fork function's address, `$00fe....`), or, where it numbered none, the cursor's
# distance (`$fe67ae..$fe67b4`: 0 above a word, under 65,536 bytes). OUR ap_trecd answers a `uint16_t`: the ABI says
# nothing of the register above it, the bench compares the two bytes its signature declares (`tier3.CALL`'s `returns`)
# and the callers (the AES's arm of opcode 15: band 5) read `d0.w` — so the high word is no part of the answer.
D0_S_HIGH_WORD_AFTER_A_RECORD_NUMBERED = aes.high_word(addrs.AES_ROM_MCHANGE)
assert {aes.high_word(getattr(addrs, routine)) for routine in ("AES_ROM_TCHANGE", "AES_ROM_BCHANGE", "AES_ROM_KCHANGE")} == {
    D0_S_HIGH_WORD_AFTER_A_RECORD_NUMBERED}, "every fork function's address has one high word"


def _buffer(memory, records):
    return bytes(memory[tape.RECORD_AT:tape.RECORD_AT + records * tape.RECORD.size])


@pytest.mark.parametrize("name", RECORDINGS)
def test_the_rom_s_own_recording_holds_what_its_name_says(name):
    """THE ROM'S ap_trecd, the events taken at its dispatcher's idles: it answers the records its forker made, the
    buffer holds each as a NUMBER and its data — no fork function's address left — the bytes past them untouched,
    and the recorder is disarmed (its flag, its count, its cursor all 0)."""
    made, row = RECORDINGS[name], tape.RECORDING_ROWS[name]
    the_rom_s = switching.scheduled(row, switching.settled(row).pokes)
    assert the_rom_s.ended == aes_switch.RETURNED and the_rom_s.d0 & aes.WORD_MASK == len(made.records)
    assert aes.high_word(the_rom_s.d0) == (D0_S_HIGH_WORD_AFTER_A_RECORD_NUMBERED if made.records else 0)
    assert _buffer(the_rom_s.memory, tape.MOST_RECORDS) == (
        tape._records(*made.records) + bytes([tape.A_STALE_BYTE]) * (tape.RECORD_BYTES - len(made.records) * tape.RECORD.size))
    assert [case.word_in(the_rom_s.memory, aes.AES_GL_RECD), case.word_in(the_rom_s.memory, aes.AES_RECORD_LEFT),
            case.long_in(the_rom_s.memory, aes.AES_RECORD_CURSOR)] == [0, 0, 0]


def test_a_count_of_0_does_not_record_nothing():
    """A ROM BEHAVIOUR, KEPT: appl_trecord(buffer, 0) — and a count below 0 — records EVERY event until Control-\\ is
    typed, into a buffer its caller said holds no record. forker counts the records left down from the count and
    goes on while the result is not 0 (`$fe4ca4 subq.w #1` / `$fe4caa move.w $9728,$c79a`): from 0 that is -1, and
    the recorder runs for 65,536 records. Only a recording ended before its first event records nothing."""
    assert RECORDINGS[tape.UNASKED].count == RECORDINGS[tape.NOTHING].count == 0 > RECORDINGS[tape.UNASKED_BELOW_ZERO].count
    assert PREMISES[_recording(tape.UNASKED)].answer == len(RECORDINGS[tape.UNASKED].records) == 4
    assert PREMISES[_recording(tape.UNASKED_BELOW_ZERO)].answer == len(RECORDINGS[tape.UNASKED_BELOW_ZERO].records) == 3
    assert PREMISES[_recording(tape.NOTHING)].answer == len(RECORDINGS[tape.NOTHING].records) == 0


def test_a_recording_past_32767_bytes_is_counted_below_zero_and_numbered_nowhere():
    """A ROM BEHAVIOUR, KEPT (`$fe67b6 move.w d0,d6 / ext.l d6 / divs.w #8,d6`, `$fe6812 cmp.w d6,d5 / blt`): the
    ROM's own appl_trecord(buffer, 0) with 4,110 packets taken at 137 of its dispatcher's idles, ended by
    Control-backslash. The cursor has gone 32,880 bytes; cut to a word that is -32,656, and ap_trecd answers -4,082
    (`$f00e`) — and its numbering loop, `blt` over a negative count, numbers NO record: the buffer holds every
    record's FORK FUNCTION'S ADDRESS, as forker copied it. TIER 1 (`aes_switching.companion`: the C's answer the
    ROM's, every byte outside the run's own stack the ROM's — so what is read off the C's image below is the ROM's
    run's): a build that counted the distance unsigned, or did not cut it to a word, answers 4,110 and numbers them
    all. No blob runs it (`aes_aptape`: ten seconds a ROM run)."""
    row = tape.a_long_recording_row()
    ran = switching.companion(row)
    made, cut = tape.A_LONG_RECORDING_S_RECORDS, aes.signed(tape.A_LONG_RECORDING_S_BYTES)
    assert (ran.delivered.idles, ran.entered) == (tape.IDLES_OF_PACKETS + 2, ONCE)
    assert cut < 0 and aes.signed(ran.answer) == -(-cut // tape.RECORD.size) == -4082, hex(ran.answer)
    x, y = tape.WHERE_THE_SNAPSHOT_S_MOUSE_IS
    to_and_fro = [(addrs.AES_ROM_MCHANGE, aes.words_long(x + dx, y)) for dx in (1, 0)] * (made // 2)
    recorded = bytes(ran.image[tape.LONG_RECORD_AT:tape.LONG_RECORD_AT + (made + 1) * tape.RECORD.size])
    assert recorded == tape._records(*to_and_fro) + bytes(tape.RECORD.size), "every record a fork function's address still; none past them"
    assert [case.word_in(ran.image, aes.AES_GL_RECD), case.word_in(ran.image, aes.AES_RECORD_LEFT),
            case.long_in(ran.image, aes.AES_RECORD_CURSOR)] == [0, 0, 0]


@pytest.mark.parametrize("name", (tape.FULL, tape.NOTHING))
def test_a_recording_nothing_wakes_sleeps_for_ever(name):
    """THE PREMISE OF THE LOOP: with nothing delivered ap_trecd never returns — the machine idles, every process
    waiting, the recorder armed (a full buffer and an ended recording are each an interrupt's doing)."""
    row = tape.RECORDING_ROWS[name]._replace(at_idle={})
    the_rom_s = switching.scheduled(row, switching._staged(row))
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (aes_switch.IDLES, 1, ())
    assert case.word_in(the_rom_s.memory, aes.AES_GL_RECD) == 1


def test_a_played_timer_record_nothing_wakes_blocks_after_the_moves():
    """...and ap_tplay's wait is a real one: with no tick delivered the playback stops in the timer record, the
    desk entered three times before it (the first yield, a yield a move)."""
    row = ROWS[PLAYED]._replace(at_idle={})
    the_rom_s = switching.scheduled(row, switching._staged(row))
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (aes_switch.IDLES, 1, THRICE)


# ---- THE PREMISE, AT THE DISPATCHER, AND TIER 1 ---------------------------------------------------------------------------------
@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_of_a_row_is_what_its_name_says(label):
    """THE PREMISE (`aes_switching.vet_the_premise`): the ROM's run through its own dispatcher over the row's settled
    machine returns to the process that made the call, each interrupt taken at the idle the row names, the
    dispatcher entering exactly the processes named, in order — and the row carries that run's deliveries."""
    switching.vet_the_premise(ROWS[label], PREMISES[label])


@pytest.mark.parametrize("label", ROWS)
def test_a_row_s_first_switch_is_held_at_the_dispatcher(label):
    """WHERE THE C FIRST LEAVES, its image the ROM's own at dsptch: ap_trecd BLOCKS in its first sleep with the
    recorder armed over the buffer — the flag, the count as handed (0 and -1 too), the cursor — and a delay of five
    ticks queued; ap_tplay YIELDS before it has stored anything (the playing flag and the mouse's place are written
    after the first yield, not before)."""
    row = ROWS[label]
    how = aes_event.BLOCKS if row.name == tape.AP_TRECD else aes_event.YIELDS
    held = aes_event.switches_where_the_rom_does(row.name, row.arguments, row.machine(), switches=how)
    if row.name == tape.AP_TPLAY:
        return
    records, count = row.arguments
    assert [case.word_in(held.image, aes.AES_GL_RECD), case.word_in(held.image, aes.AES_RECORD_LEFT),
            case.long_in(held.image, aes.AES_RECORD_CURSOR)] == [1, count & aes.WORD_MASK, records]


@pytest.mark.parametrize("label", ROWS)
def test_a_row_taken_on_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1 (`aes_switching.companion`, nothing dropped): the C through its own scheduler — every yield and every
    wake a return of `aes_dsptch`, forker and the fork functions in C under it — makes the idles and the polls of
    the ROM's run and leaves the ROM's image: the buffer, the recorder's three words, the fork queue run dry, the
    VDI's two routines put back, the mouse where the last record put it."""
    ran = switching.companion(ROWS[label])
    assert ran.entered == tuple(PREMISES[label].entered)
    if ROWS[label].name == tape.AP_TRECD:
        assert ran.answer & aes.WORD_MASK == PREMISES[label].answer


# ---- WHAT A PLAYBACK LEAVES, held on the ROM's run (the companion holds the C to the same image) -------------------------------
def _played(label):
    """`(the machine the playback began over, the memory the ROM's run of it leaves)`."""
    row = ROWS[label]
    made = switching.settled(row)
    return make_image(made.pokes), switching.scheduled(row, made.pokes).memory


@pytest.mark.parametrize("label", (PLAYED, CURSOR_SHOWN, ONTO_THE_BAR, HIGH_WORDS))
def test_a_playback_with_a_mouse_record_takes_the_vdi_s_routines_and_gives_them_back(label):
    """A MOUSE RECORD's playback displaces the VDI's cursor and motion routines (vex_curv, vex_motv) and puts both
    back: where the ROM's run ends the two vectors are what they were, the AES keeps what it displaced — the VDI's
    own default_user_cur where drawrat calls it, the motion routine in ap_tplay's own longword — contrl[9..10]
    holds the last thing displaced, THE ROUTINE THAT DRAWS NOTHING, and the playing flag is down again."""
    before, after = _played(label)
    cursor, motion = vdi.field("LINEA", "USER_CUR").at, vdi.field("LINEA", "USER_MOT").at
    assert (case.long_in(after, cursor), case.long_in(after, motion)) == (case.long_in(before, cursor), case.long_in(before, motion))
    assert case.long_in(after, aes.header_constants("gsxif.h")["AES_DRWADDR"]) == case.long_in(before, cursor) == addrs.VDI_ROM_DEFAULT_USER_CUR
    assert case.long_in(after, tape.APTAPE["AES_PLAY_OLD_MOTION"]) == case.long_in(before, motion)
    assert case.long_in(after, aes.AES_GSX_CONTRL_PTR2) == addrs.AES_ROM_JUSTRETF
    assert case.word_in(after, aes.header_constants("evfork.h")["AES_GL_PLAY"]) == 0


@pytest.mark.parametrize("label", (NO_MOUSE_RECORD, NONE_PLAYED, tape.A_KEY_PLAYED))
def test_a_playback_with_no_mouse_record_leaves_the_vdi_s_routines_alone(label):
    """...and a playback that meets no mouse record makes neither exchange: the AES's two save longwords and
    contrl[9..10] are as the machine had them."""
    before, after = _played(label)
    for kept in (aes.header_constants("gsxif.h")["AES_DRWADDR"], tape.APTAPE["AES_PLAY_OLD_MOTION"], aes.AES_GSX_CONTRL_PTR2):
        assert case.long_in(after, kept) == case.long_in(before, kept)


def test_a_playback_notes_where_the_mouse_was_after_its_first_yield():
    """gl_mx / gl_my (`AES_PLAY_FROM_X`, `_Y`: read by nothing in this ROM) hold the mouse's place as the playback
    FOUND it — where the recording left it — not where the last record put it."""
    before, after = _played(PLAYED)
    xrat, yrat = aes.header_constants("gsx.h")["AES_XRAT"], aes.header_constants("gsx.h")["AES_YRAT"]
    found = (case.word_in(before, xrat), case.word_in(before, yrat))
    assert (case.word_in(after, tape.APTAPE["AES_PLAY_FROM_X"]), case.word_in(after, tape.APTAPE["AES_PLAY_FROM_Y"])) == found
    assert found == (tape.THE_MOVE_AWAY[-1][1] >> aes.HIGH_WORD_SHIFT, tape.THE_MOVE_AWAY[-1][1] & aes.WORD_MASK)


# ---- `$fcff0a`, THE VDI'S OWN CURSOR ROUTINE, UNDER A REAL PLAYBACK ------------------------------------------------------------
def _calls_of_the_cursor_routine(row, pokes):
    """Each time the ROM's run of `row` over `pokes` ENTERS the VDI's default_user_cur: `(the longword $947a holds,
    the cursor's hide count)` there — a watched replay of the scheduled run (`aes_switching.the_rom_s`, an observed
    stop)."""
    reference = switching.scheduled(row, pokes)
    drwaddr, hide_count, seen = aes.header_constants("gsxif.h")["AES_DRWADDR"], vdi.field("LINEA", "M_HID_CT").at, []
    watch = switching.the_rom_s(switching.switches_of(reference), switching._entry(row), observing={
        addrs.VDI_ROM_DEFAULT_USER_CUR: lambda memory: seen.append((case.long_in(memory, drwaddr), case.word_in(memory, hide_count)))})
    rom_bench.watched_original(make_image(pokes), switching._entry(row), watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {row.label}")
    watch.vet_ended(row.label)
    return seen


def _with_the_trap_save_where_the_snapshot_has_it(pokes):
    """`pokes` (a settled row's: `savptr` moved into the stack band, as every priced row's) with the BIOS trap's
    save area back where the snapshot keeps it — in compared RAM."""
    moved = aes_event.savptr_in_the_band()
    kept = {at: data for at, data in pokes.items() if at not in moved}
    return case.merge_pokes(kept, {addrs.SYSVAR_SAVPTR: aes_event.SNAPSHOT_SAVPTR.to_bytes(aes.LONG_BYTES, "big")})


@pytest.mark.parametrize("label, shown", ((CURSOR_SHOWN, True), (PLAYED, False)))
def test_a_played_move_draws_through_the_vdi_s_own_cursor_routine(label, shown):
    """WHAT `$947a` HOLDS WHILE A RECORDING PLAYS IS THE VDI'S default_user_cur (`$fcff0a`), put there by ap_tplay's
    own vex_curv — no case stages it: the ROM's run enters it once a mouse record (mchange's drawrat), each time
    through `$947a`. With the cursor SHOWN (a hide count of 0) it takes its storing arm — the played point queued
    for the VBL (CUR_X, CUR_Y, the moved flag); hidden, it stores nothing. The C reaches the candidate's own
    default_user_cur on the register hook, under the scheduler's model: the companion holds the queue equal."""
    row = ROWS[label]
    entered = _calls_of_the_cursor_routine(row, switching.settled(row).pokes)
    assert [through for through, _hidden in entered] == [addrs.VDI_ROM_DEFAULT_USER_CUR] * len(tape.THE_MOVE_AWAY)
    assert all((hidden == 0) == shown for _through, hidden in entered), entered
    before, after = _played(label)
    point = tape.THE_MOVE_AWAY[-1][1]
    queue = [vdi.field("LINEA", name).at for name in ("CUR_X", "CUR_Y")]
    queued = [case.word_in(after, at) for at in queue]
    assert (queued == [point >> aes.HIGH_WORD_SHIFT, point & aes.WORD_MASK]) == shown
    assert shown or queued == [case.word_in(before, at) for at in queue], "hidden, the routine stores nothing"


@pytest.mark.parametrize("label", (CURSOR_SHOWN, tape.A_KEY_PLAYED))
def test_the_trap_frame_under_a_playback_is_the_keyboard_poll_s_own(label):
    """THE TRAP-FRAME HALF OF `$fcff0a`'s BINDING (FLIP 3's debt: reachable only under ap_tplay). With the BIOS
    trap's save area where the snapshot keeps it (compared RAM, not the stack band a priced row moves it to), a
    playback's C through the scheduler differs from the ROM's run IN THE TRAP'S SAVED REGISTERS ALONE — the
    caller's, by nature (`aes_event.TRAP_SAVE_DROP`) — and in NO byte of its frame's PC and SR
    (`TRAP_FRAME_BYTES`): the ROM's run stores them, and stores what the machine held — the dispatcher's keyboard
    poll is the last trap of every such run, and the locator's sample under a played move (vsm_locator) parks the
    same site. So a playback needs no drop of the frame, and none is made for it: a drop there would hide a C that
    wrote the frame."""
    row = ROWS[label]
    pokes = _with_the_trap_save_where_the_snapshot_has_it(switching.settled(row).pokes)
    reference = switching.scheduled(row, pokes)
    ran = aes_switch.modelled(switching._core(row), vdi.as_signed(row.name, row.arguments), pokes, reference,
                              answered=False, foreign=False)
    assert reference.ended == aes_switch.RETURNED and ran.returncode == 0, ran.stderr
    differ = aes_event.differing(ran.image, reference.memory, frozenset(case.STACK_BAND))
    saved = frozenset(at for lo, hi, _why in aes_event.TRAP_SAVE_DROP for at in range(lo, hi))
    assert differ and set(differ) <= saved, [f"{at:#x}" for at in sorted(set(differ) - saved)]
    frame = sorted(aes_event.TRAP_FRAME_BYTES)
    started = make_image(pokes)
    assert bytes(reference.memory[at] for at in frame) == bytes(started[at] for at in frame) == bytes(ran.image[at] for at in frame)


# ---- ON BOTH BLOBS, AND IN THE TABLE ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label", ON_BOTH_BLOBS)
def test_a_row_really_switches_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH (`aes_switching.vet_on_a_blob`): our ap_trecd sleeps in OUR mwait
    and is woken by our switchto; our ap_tplay yields through OUR dsptch and disp, forker running the fork function
    it has just queued — ours, by its own entry's address — and comes back into GCC's frame, the record's cursor and
    count still in its registers. The image the ROM's but for the row's drops, the idles, the polls, the processes
    entered, the whole run's cycles pinned; the screen manager's turn the ROM's own on both shores, to the cycle."""
    switching.vet_on_a_blob(blob, ROWS[label], PREMISES[label], WINDOWS.get(label, NO_WINDOW), WHOLE_RUN[label])


@pytest.mark.parametrize("label", PRICED)
def test_the_table_prices_a_row_on_both_counts(label):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's own cycles on each shore and — where
    the run calls a rebound entry (ev_timer's ev_block) — the caller's own, both pinned, both under the bar."""
    switching.vet_the_table_s_price(ROWS[label], PRICED[label])


# ---- THE TARGET TEXT: ap_trecd's mask bracket, which no run of a bench can see ---------------------------------------------------
# A bench run is entered at IPL 7 and takes no interrupt the watch does not lay, and the SR save word is stored by
# tchange's bracket under every sleep too: a build of ap_trecd that armed the recorder UNMASKED leaves every image
# and every ledger as they are. So the bracket is read off the build's own instructions.
SR_PARKED = re.compile(rf"move\.?w %sr,(0x)?{aes.AES_SR_SPL:x}\b")
MASK_RAISED = re.compile(r"ori\.?w #(1792|0x700),%sr")
SR_PUT_BACK = re.compile(rf"move\.?w (0x)?{aes.AES_SR_SPL:x}\b.*,%sr")
A_CALL = re.compile(r"(jsr|bsr)")
# The recorder's three words in the order each of the ROM's two brackets stores them: the flag, the count, the cursor.
THE_RECORDER_S_WORDS = (aes.AES_GL_RECD, aes.AES_RECORD_LEFT, aes.AES_RECORD_CURSOR)


AN_ADDRESS_LOADED = re.compile(r"movea?l #(\d+),%([ad]\d)$")


def _stores_to_the_recorder_s_words(body):
    """`[(where, word)]`: every STORE to one of the recorder's three words in `body` (a blob's instructions), as GCC
    spells a store at an address off the image's base — the address loaded (`movel #51098,%d0`), and the NEXT
    instruction a move or a clr whose destination is through it (`…,%a2@(0,%d0:l)`). A load of one through it (the
    cursor read: `movel %a2@(0,%d0:l),%d1`) is none."""
    stores = []
    for at, (text, used) in enumerate(zip(body, body[1:])):
        loaded = AN_ADDRESS_LOADED.match(text)
        if loaded and int(loaded.group(1)) in THE_RECORDER_S_WORDS:
            if used.startswith(("move", "clr")) and used.endswith(f"(0,%{loaded.group(2)}:l)"):
                stores.append((at + 1, int(loaded.group(1))))
    return stores


def test_ap_trecd_arms_and_disarms_the_recorder_with_the_interrupts_masked(blob):
    """`$fe6776` / `$fe678c`, `$fe67a0` / `$fe67c4`: forker's recorder reads its three words between two
    instructions of any process, so the ROM writes them under spl7 — armed, and disarmed with the cursor read. OUR
    build's ap_trecd has exactly those two brackets (the SR parked in spl7's word and the mask raised by the next
    instruction; put back from the same word); every instruction that names the recorder's count or its cursor
    lies inside one; EVERY STORE to one of the recorder's three words — the FLAG among them: armed before the mask
    is raised, the recorder could run with its count and its cursor not yet set — lies inside one, and each bracket
    stores the three IN THE ROM'S ORDER (`$fe6778` the flag, `$fe6780` the count, `$fe6786` the cursor; `$fe67a2`,
    `$fe67a8`, `$fe67be`); and its one call — the sleep — lies between the two, UNMASKED (a sleep under the mask
    would never be woken)."""
    body = [text for _pc, _length, text in between_instructions.blob_body(blob, "aes_ap_trecd")]
    parked, raised, put_back = ([at for at, text in enumerate(body) if shape.search(text)]
                                for shape in (SR_PARKED, MASK_RAISED, SR_PUT_BACK))
    assert len(parked) == len(put_back) == 2 and raised == [at + 1 for at in parked], (parked, raised, put_back)
    (armed, _disarmed), (armed_until, disarmed_until) = parked, put_back
    assert armed < armed_until < parked[1] < disarmed_until
    brackets = (range(parked[0], put_back[0]), range(parked[1], put_back[1]))
    naming = [at for at, text in enumerate(body)
              if any(f"#{word}" in text or f"{word:#x}" in text for word in (aes.AES_RECORD_LEFT, aes.AES_RECORD_CURSOR))]
    assert len(naming) >= 2 * len(brackets) and all(any(at in bracket for bracket in brackets) for at in naming), naming
    stores = _stores_to_the_recorder_s_words(body)
    assert all(any(at in bracket for bracket in brackets) for at, _word in stores), stores
    assert [[word for at, word in stores if at in bracket] for bracket in brackets] == [list(THE_RECORDER_S_WORDS)] * 2, stores
    calls = [at for at, text in enumerate(body) if A_CALL.match(text)]
    assert len(calls) >= 1 and all(armed_until < at < parked[1] for at in calls), calls


EXCHANGE = re.compile(rf"pea (0x)?({addrs.VDI_ROM_VEX_CURV_OPCODE:x}|{addrs.VDI_ROM_VEX_MOTV_OPCODE:x})\b")
CURSOR_THEN_MOTION = (addrs.VDI_ROM_VEX_CURV_OPCODE, addrs.VDI_ROM_VEX_MOTV_OPCODE)


def test_ap_tplay_exchanges_the_cursor_routine_before_the_motion_routine(blob):
    """`$fe66a4` (127) before `$fe66c2` (126), and `$fe6740` before `$fe6756`: the ROM displaces — and puts back — the
    VDI's CURSOR routine first, then its MOTION routine. The order shows in no image a run is compared at: both are
    exchanged before the next yield and both put back before the return, so it is seen only by an interrupt taken
    between the two (the mouse moving with one routine displaced and the other not) and in contrl's leftovers until
    the next VDI call. Held on the build's own instructions: the four opcodes ap_tplay hands gsx_ncode, in the
    order its text spells them — the taking, then the giving back."""
    body = [text for _pc, _length, text in between_instructions.blob_body(blob, "aes_ap_tplay")]
    handed = [int(found.group(2), 16) for found in map(EXCHANGE.match, body) if found]
    assert handed == [*CURSOR_THEN_MOTION, *CURSOR_THEN_MOTION], handed


# ---- WHAT NO BLOB RUNS, AND WHAT NO HOST FORK RUNS — each refused by name -----------------------------------------------------------
def test_a_recording_across_another_process_s_turn_is_refused_on_a_blob(blob):
    """THE MIXTURE'S OWN LIMIT, held so that it is not met by surprise: a recording with the screen manager's turn
    INSIDE it is the ROM's on the host (Tier 1 above) and RED on a blob in exactly the records made inside the
    foreign window — the ROM's forker ran those events and its recorder copied the ROM's fork-function addresses,
    which our ap_trecd, comparing with our own entries, numbers 0 (a timer's) where the ROM's numbers them 2 (a
    mouse's). No relocation maps a recording where a window closes; the row is registered nowhere."""
    row = ROWS[ACROSS_A_WINDOW]
    assert SCREEN_MANAGER in PREMISES[ACROSS_A_WINDOW].entered and ACROSS_A_WINDOW not in tape.PRICED
    with pytest.raises(AssertionError, match="left different memory than the original") as refused:
        switching.measured_on(blob, row)
    low_bytes = [tape.RECORD_AT + nth * tape.RECORD.size + aes.LONG_BYTES - 1 for nth in (1, 2)]
    assert all(f"{at:#x} (0x{tape.MOUSE:02x} -> 0x{tape.TIMER:02x})" in str(refused.value) for at in low_bytes), refused.value
    assert "2 byte(s)" in str(refused.value)


def test_a_routine_s_address_played_for_a_number_is_the_rom_s_code_on_a_blob(blob):
    """A NUMBER THAT IS NONE OF THE FOUR IS QUEUED AS IT IS: the labelled case hands the ROM's own justretf for one,
    forker calls it and it returns (Tier 1 above: the C queues the same longword). On a blob that is 16 cycles of
    the AES's ROM inside our run — a code address in an application's data, which nothing relocates — and the
    general guard refuses it by name."""
    with pytest.raises(AssertionError, match="OUR run spent 16 cycles at the PCs of the AES's own ROM"):
        switching.measured_on(blob, ROWS[A_ROUTINE_S_ADDRESS])


def test_a_scale_of_0_is_the_runtime_s_divide_by_zero_which_the_c_refuses_by_name():
    """A ROM BEHAVIOUR, NOT RECONSTRUCTED: appl_tplay at a scale of 0 divides a timer record's milliseconds by zero
    in the Alcyon runtime (ldiv's `divs.w`): the 68000 takes vector 5 — an `rte` on this machine — and the ROM's
    playback carries on and returns. ldiv's C core halts at that divide by name (`src/aes/strings.c`), so the C's
    playback does too: refused, never answered with a quotient of our own making."""
    row = tape.playback_row("four records played at a scale of 0", tape.PLAYED_AT_NO_SCALE)
    made = switching.settled(row)
    reference = switching.scheduled(row, made.pokes)
    assert reference.ended == aes_switch.RETURNED and reference.entered == PREMISES[PLAYED].entered
    ran = aes_switch.modelled(switching._core(row), vdi.as_signed(row.name, row.arguments), made.pokes, reference,
                              answered=False, foreign=False)
    assert ran.returncode != 0 and "not reconstructed: divs.w by zero" in ran.stderr, ran.stderr

