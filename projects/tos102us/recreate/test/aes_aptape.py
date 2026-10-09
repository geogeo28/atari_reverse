"""THE EVENT TAPE'S MACHINES AND ROWS — what `src/aes/aptape.c` (ap_trecd, ap_tplay) is proved over
(`test_aes_aptape.py`).

BOTH ROUTINES LEAVE BY THE DISPATCHER ON EVERY ARM: ap_trecd sleeps in ev_timer(100) until forker's recorder has
stopped, ap_tplay yields before its first record and after each. So neither has a case that returns without a
switch, and every case here is A ROW THAT SWITCHES (`aes_switching.SwitchingRow`): the call, and what the ROM's own
interrupt code delivers at which idle of the dispatcher.

EVERY MACHINE IS A ROM RUN'S:
  * A RECORDING is made by THE ROM'S OWN ap_trecd over a running desk (`aes_event.machine`), real interrupts taken at
    its dispatcher's idles — the mouse, the buttons, the keyboard, the ticks — recorded by the ROM's forker and
    numbered by the ROM's ap_trecd (`RECORDINGS`; `recorded`: the machine that run leaves, by its write ledger).
  * A PLAYBACK plays such a recording over the machine its recording left (`PLAYBACKS`).
  * THE ONE LABELLED CLASS (`ARGUMENT_CLASS`): a playback of records NO RECORDING HOLDS — a number above its low
    word, a routine's address for a number, a buffer at an odd address — laid over a recording's machine. ap_tplay
    reads whatever an application hands it; ap_trecd never writes such a record. Tier 1 only.

WHAT DIFFERS BY NATURE is the registrar's (`aes_switching.settled`): the Line-F mask word, the caller's saved
context, the dispatcher's stack, and spl7_save's SR save word under ap_trecd's own bracket and tchange's.
"""
import functools
import struct
from collections import namedtuple

from harness import make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evinput as evinput
import aes_evlib as evlib
import aes_switching
import case
import vdi
from case import merge_pokes

APTAPE = aes.header_constants("aptape.h")
AP_TRECD, AP_TPLAY = "AES_ROM_AP_TRECD", "AES_ROM_AP_TPLAY"
aes.declare_alcyon(AP_TRECD, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG))
aes.declare_alcyon(AP_TPLAY, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.WORD_ARG))
ROUTINES = (AP_TRECD, AP_TPLAY)

# ---- the buffer an application hands both: the input battery's band (`aes_evinput`) -----------------------------------
RECORD_AT, RECORD_BYTES = evinput.RECORD_AT, evinput.RECORD_BYTES
RECORD = struct.Struct(">II")           # a record: the fork function's number (its address while it records), its data
assert RECORD.size == aes.FORK_ENTRY_BYTES
MOST_RECORDS = RECORD_BYTES // RECORD.size
A_STALE_BYTE = 0xA5
STALE_RECORDS = {RECORD_AT: bytes([A_STALE_BYTE]) * RECORD_BYTES}     # a record not written shows
TIMER, BUTTON, MOUSE, KEY = (APTAPE[name] for name in ("TAPE_TIMER", "TAPE_BUTTON", "TAPE_MOUSE", "TAPE_KEY"))

# ---- what is delivered: the ROM's own interrupt code, at an idle of the dispatcher --------------------------------------
ticks = aes_event.ticks
POLL_TICKS = APTAPE["TRECD_POLL_MS"] // evasync.TICK_MS      # ap_trecd's sleep, in ticks: what wakes it to look again
A_TICK = ticks(1)                       # what wakes a delay of no tick at all (a short timer record played back)
AWAY, PRESS, A_CLICK, RETURN = evasync.AWAY, aes_event.press, evlib.A_CLICK, evasync.RETURN
CONTROL, BACKSLASH = aes_event.key(evinput.CONTROL_KEY), aes_event.key(evinput.BACKSLASH_KEY)
ONTO_THE_BAR, OFF_THE_BAR = evasync.ONTO_THE_BAR, evlib.OFF_THE_BAR
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD


@functools.cache
def desk_running():
    """PD0 running, the cursor hidden (`aes_event.machine`), the buffer stale."""
    return merge_pokes(aes_event.machine(), STALE_RECORDS)


@functools.cache
def desk_running_the_cursor_shown():
    """...and with the cursor SHOWN (`aes_event.shown_machine`): the VDI's own cursor routine then queues a point."""
    return merge_pokes(aes_event.shown_machine(), STALE_RECORDS)


# ---- THE RECORDINGS: the ROM's own appl_trecord, the events delivered at its dispatcher's idles ---------------------------
# `machine` (a zero-argument builder), `count` (ap_trecd's second argument), `at_idle` (`{idle: interrupt(s)}`), and
# `records`: what the ROM's run leaves in the buffer — its answer is how many (held: `test_aes_aptape.py`).
Recording = namedtuple("Recording", "machine count at_idle records")
FULL, MERGED, A_KEY, ENDED_EARLY = "full", "merged", "a key", "ended early"
NOTHING, UNASKED, UNASKED_BELOW_ZERO = "nothing", "unasked", "unasked, below zero"
CURSOR_SHOWN, ONTO_AND_OFF_THE_BAR, A_WHOLE_CLICK = "the cursor shown", "onto and off the bar", "a whole click"
ONE_CLICK = 1                           # a button record's low word: the clicks counted
KBSHIFT_CONTROL = 0x04                  # a key record's low word, the shift keys: Control down (Kbshift's bit 2)


def _moved(start, to):
    """THE MOUSE RECORDS OF A MOVE from `start` to `to`: one A PACKET, where that packet leaves the mouse — a packet
    moves it `aes_event.MOUSE_STEP` at most each way (`aes_event.moving_to`)."""
    records = []
    while start != to:
        start = tuple(at + max(-aes_event.MOUSE_STEP, min(aes_event.MOUSE_STEP, goal - at)) for at, goal in zip(start, to))
        records.append((MOUSE, aes.words_long(*start)))
    return tuple(records)


def _where_the_mouse_is(machine):
    """Where the VDI's mouse interrupt has the cursor over `machine` (pokes): GCURX, GCURY."""
    image = make_image(machine)
    return case.word_in(image, vdi.LINEA_GCURX), case.word_in(image, vdi.LINEA_GCURY)


WHERE_THE_SNAPSHOT_S_MOUSE_IS = _where_the_mouse_is(aes_event.machine())
# The snapshot's mouse moved AWAY arrives as two packets: two mouse records.
THE_MOVE_AWAY = _moved(WHERE_THE_SNAPSHOT_S_MOUSE_IS, evasync.OUTSIDE)
THE_PRESS = (BUTTON, aes.words_long(aes_event.LEFT_BUTTON, ONE_CLICK))      # the left button down, one click
THE_RELEASE = (BUTTON, aes.words_long(0, ONE_CLICK))
RETURN_TYPED = (KEY, aes.words_long(evinput.RETURN_KEY_CODE))
CONTROL_HELD = (KEY, aes.words_long(0, KBSHIFT_CONTROL))                    # no key, the shift keys changed
THE_MOVE_ONTO_THE_BAR = _moved(WHERE_THE_SNAPSHOT_S_MOUSE_IS, aes_event.MENU_BAR_POINT)
THE_MOVE_OFF_THE_BAR = _moved(aes_event.MENU_BAR_POINT, aes_event.A_POINT_ON_THE_DESKTOP)
assert (len(THE_MOVE_AWAY), len(THE_MOVE_ONTO_THE_BAR), len(THE_MOVE_OFF_THE_BAR)) == (2, 1, 2)
RECORDINGS = {
    # the buffer FULL: the recorder stops itself, and ap_trecd finds it stopped when its sleep runs out
    FULL: Recording(desk_running, 4, {0: (AWAY, PRESS, ticks(POLL_TICKS))},
                    (*THE_MOVE_AWAY, (TIMER, POLL_TICKS), THE_PRESS)),
    # a tick recorded just after a tick is ADDED to it (forker's merge arm), over three sleeps of ap_trecd's loop
    MERGED: Recording(desk_running, 2, {0: ticks(POLL_TICKS), 1: ticks(POLL_TICKS), 2: (PRESS, ticks(POLL_TICKS))},
                      ((TIMER, 3 * POLL_TICKS), THE_PRESS)),
    # one record, a key's (the poll that takes it is the idle's own; the ticks then wake ap_trecd)
    A_KEY: Recording(desk_running, 1, {0: RETURN, 1: ticks(POLL_TICKS)}, (RETURN_TYPED,)),
    # Control-\ ends a recording that is not full, and is not recorded — the Control key going down is
    ENDED_EARLY: Recording(desk_running, 4, {0: (AWAY, CONTROL), 1: BACKSLASH, 2: ticks(POLL_TICKS)},
                           (*THE_MOVE_AWAY, CONTROL_HELD)),
    # a count of 0, ended at once (the poll takes Control and the key together): nothing recorded, 0 answered
    NOTHING: Recording(desk_running, 0, {0: (CONTROL, BACKSLASH), 1: ticks(POLL_TICKS)}, ()),
    # A COUNT OF 0 DOES NOT RECORD NOTHING (a ROM behaviour, kept): forker counts the records left DOWN PAST 0 and
    # goes on while the count is not 0 — everything is recorded, into a buffer the caller said holds no record
    UNASKED: Recording(desk_running, 0, {0: (AWAY, PRESS, ticks(POLL_TICKS)), 1: (CONTROL, BACKSLASH), 2: ticks(POLL_TICKS)},
                       (*THE_MOVE_AWAY, (TIMER, POLL_TICKS), THE_PRESS)),
    # ...and so does a count below 0
    UNASKED_BELOW_ZERO: Recording(desk_running, -1, {0: (AWAY, ticks(POLL_TICKS)), 1: (CONTROL, BACKSLASH), 2: ticks(POLL_TICKS)},
                                  (*THE_MOVE_AWAY, (TIMER, POLL_TICKS))),
    CURSOR_SHOWN: Recording(desk_running_the_cursor_shown, 4, {0: (AWAY, PRESS, ticks(POLL_TICKS))},
                            (*THE_MOVE_AWAY, (TIMER, POLL_TICKS), THE_PRESS)),
    # the mouse onto the menu bar and off it again: THE SCREEN MANAGER runs twice while the recorder is armed
    ONTO_AND_OFF_THE_BAR: Recording(desk_running, 3, {0: ONTO_THE_BAR, 1: OFF_THE_BAR, 2: ticks(POLL_TICKS)},
                                    (*THE_MOVE_ONTO_THE_BAR, *THE_MOVE_OFF_THE_BAR)),
    A_WHOLE_CLICK: Recording(desk_running, 5, {0: (AWAY, A_CLICK, ticks(POLL_TICKS))},
                             (*THE_MOVE_AWAY, (TIMER, POLL_TICKS), THE_PRESS, THE_RELEASE)),
}
assert all(len(recording.records) <= MOST_RECORDS for recording in RECORDINGS.values())


def recording_row(name):
    """The recording `name` as a row that switches: the ROM's — or our — ap_trecd, its events at the idles."""
    made = RECORDINGS[name]
    return aes_switching.SwitchingRow(RECORDING_LABELS[name], AP_TRECD, (RECORD_AT, made.count), made.machine, made.at_idle)


def recorded(name):
    """THE MACHINE THE ROM'S OWN RECORDING `name` LEAVES (`aes_switching.left_by`: every byte its run or an interrupt
    stored): the records in the buffer, numbered; the mouse, the buttons and the keyboard where the events left them."""
    made = RECORDINGS[name]
    return aes_switching.left_by(AP_TRECD, (RECORD_AT, made.count), made.machine(), made.at_idle)


RECORDING_LABELS = {
    FULL: "two moves, the ticks and a press recorded: the buffer full",
    MERGED: "ticks recorded over three sleeps, merged into one record; then a press",
    A_KEY: "one record, a key's",
    ENDED_EARLY: "ended by Control-backslash before the buffer is full",
    NOTHING: "a count of 0, ended at once: nothing recorded",
    UNASKED: "a count of 0, events before it is ended: all recorded",
    UNASKED_BELOW_ZERO: "a count below 0: recorded all the same",
    CURSOR_SHOWN: "two moves, the ticks and a press recorded, the cursor shown",
    ONTO_AND_OFF_THE_BAR: "the mouse onto the menu bar and off it: the screen manager's turns inside the recording",
    A_WHOLE_CLICK: "two moves, the ticks, a press and its release recorded",
}
assert RECORDING_LABELS.keys() == RECORDINGS.keys()

# ---- THE PLAYBACKS: appl_tplay of a recording over the machine its recording left ------------------------------------------
# `recording`, `count` (None: every record of it), `scale`, `at_idle`: what wakes each timer record's wait.
Playback = namedtuple("Playback", "recording count scale at_idle staged", defaults=(None,))
AS_RECORDED = APTAPE["TPLAY_SCALE_UNIT"]    # a scale of 100: a tick played as 100 ms / 100 — 1 ms, under a tick's own 20
SLOWLY = 1                              # a scale of 1: a recorded tick is 100 ms, five ticks
TICKS_A_TICK_SLOWLY = APTAPE["TPLAY_SCALE_UNIT"] // evasync.TICK_MS
A_THIRD = 3                             # a scale that does not divide: 5 ticks are 166 ms and a remainder — eight ticks
BACKWARDS = -AS_RECORDED                # a negative scale: the wait is -5 ms, which is no tick either
PLAYED, PLAYED_SLOWLY, NONE_PLAYED = ("four records played: two moves, a wait, a press",
                                      "four records played slowly: the wait is twenty-five ticks",
                                      "none of four records played: a count of 0")
NO_MOUSE_RECORD, A_KEY_PLAYED, SHIFT_KEYS_PLAYED = ("a wait and a press played: no mouse record", "a key played",
                                                    "two moves and the shift keys played")
PLAYED_THE_CURSOR_SHOWN = "four records played, the cursor shown: the VDI's cursor routine queues each point"
PLAYED_ONTO_THE_BAR = "the mouse played onto the menu bar and off it: the screen manager entered from a yield"
NONE_PLAYED_BELOW_ZERO = "none played: a count below 0"
PLAYED_BACKWARDS = "four records played at a negative scale: the wait is no tick"
PLAYBACKS = {
    PLAYED: Playback(FULL, None, AS_RECORDED, {0: A_TICK}),
    PLAYED_SLOWLY: Playback(FULL, None, SLOWLY, {0: ticks(POLL_TICKS * TICKS_A_TICK_SLOWLY)}),
    NONE_PLAYED: Playback(FULL, 0, AS_RECORDED, {}),
    NO_MOUSE_RECORD: Playback(MERGED, None, AS_RECORDED, {0: A_TICK}),
    A_KEY_PLAYED: Playback(A_KEY, None, AS_RECORDED, {}),
    SHIFT_KEYS_PLAYED: Playback(ENDED_EARLY, None, AS_RECORDED, {}),
    PLAYED_THE_CURSOR_SHOWN: Playback(CURSOR_SHOWN, None, AS_RECORDED, {0: A_TICK}),
    PLAYED_ONTO_THE_BAR: Playback(ONTO_AND_OFF_THE_BAR, None, AS_RECORDED, {}),
    # ...and those no registry holds: each another count or another scale of a priced one
    NONE_PLAYED_BELOW_ZERO: Playback(FULL, -1, AS_RECORDED, {}),
    "two of four records played: the moves alone": Playback(FULL, 2, AS_RECORDED, {}),
    "a whole click played": Playback(A_WHOLE_CLICK, None, AS_RECORDED, {0: A_TICK}),
    "four records played at a third: the wait is eight ticks": Playback(FULL, None, A_THIRD, {0: ticks(8)}),
    PLAYED_BACKWARDS: Playback(FULL, None, BACKWARDS, {0: A_TICK}),
}
PRICED_PLAYBACKS = (PLAYED, PLAYED_SLOWLY, NONE_PLAYED, NO_MOUSE_RECORD, A_KEY_PLAYED, SHIFT_KEYS_PLAYED,
                    PLAYED_THE_CURSOR_SHOWN, PLAYED_ONTO_THE_BAR)
# A SCALE OF 0 IS THE ALCYON RUNTIME'S OWN DIVIDE BY ZERO (ldiv, `divs.w`): the 68000 takes vector 5 — an `rte` on this
# machine — and the ROM's playback goes on with whatever the divide left. ldiv's C core refuses that divide by name
# (`src/aes/strings.c`: not reconstructed), so this playback is no row: `test_aes_aptape.py` holds the refusal.
PLAYED_AT_NO_SCALE = Playback(FULL, None, 0, {0: A_TICK})

# ---- THE LABELLED CLASS: records no recording holds ---------------------------------------------------------------------------
ARGUMENT_CLASS = "ARGUMENT CLASS (records no recording holds)"
A_HIGH_WORD = 0x0005                    # ...of a record's number: ap_tplay's switch reads the low word alone
A_PLAYED_POINT = evinput.A_PLAYED_POINT
ODD = 1                                 # the buffer moved to an odd address: ap_tplay copies a record a byte at a time


def _records(*records):
    return b"".join(RECORD.pack(number, data) for number, data in records)


ABOVE_THE_LOW_WORD = _records((aes.words_long(A_HIGH_WORD, MOUSE), aes.words_long(*A_PLAYED_POINT)),
                              (aes.words_long(A_HIGH_WORD, BUTTON), THE_PRESS[1]),
                              (aes.words_long(A_HIGH_WORD, KEY), RETURN_TYPED[1]),
                              (aes.words_long(A_HIGH_WORD, TIMER), 0))
# A number that is none of the four is QUEUED AS IT IS, and forker calls it: here the address of the ROM's own
# routine that draws nothing (its low word, $d424, is no number) — handed its data, it returns.
A_ROUTINE_FOR_A_NUMBER = _records((aes_event.addrs.AES_ROM_JUSTRETF, aes.words_long(*A_PLAYED_POINT)))
# A TIMER RECORD'S TICKS ARE A LONG ($fe6662 `move.l -8(a6),-(sp)` into lmul): 32,768 of them — one past a signed
# word (a staged record) — at the largest scale a word holds wait 32,768 * 100 / 32,767 = 100 ms, ap_trecd's own
# poll. Read as a word they are -32,768: a wait of -100 ms.
TICKS_PAST_A_SIGNED_WORD, THE_LARGEST_SCALE = 0x8000, 0x7FFF
ARGUMENT_PLAYBACKS = {
    f"{ARGUMENT_CLASS}: four numbers with a high word, played as their low words":
        Playback(FULL, 4, AS_RECORDED, {0: A_TICK}, {RECORD_AT: ABOVE_THE_LOW_WORD}),
    f"{ARGUMENT_CLASS}: a routine's address for a number, queued as it is":
        Playback(FULL, 1, AS_RECORDED, {}, {RECORD_AT: A_ROUTINE_FOR_A_NUMBER}),
    f"{ARGUMENT_CLASS}: two records at an odd address":
        Playback(FULL, 2, AS_RECORDED, {}, {RECORD_AT: bytes([A_STALE_BYTE]) + _records(*THE_MOVE_AWAY)}),
    f"{ARGUMENT_CLASS}: a timer record of 32,768 ticks played at a scale of 32,767: the ticks are a long":
        Playback(FULL, 1, THE_LARGEST_SCALE, {0: ticks(POLL_TICKS)}, {RECORD_AT: _records((TIMER, TICKS_PAST_A_SIGNED_WORD))}),
}
AT_AN_ODD_ADDRESS = f"{ARGUMENT_CLASS}: two records at an odd address"


def playback_row(label, play=None):
    """The playback `label` (of `PLAYBACKS` or `ARGUMENT_PLAYBACKS`, or `play` itself) as a row that switches.
    ap_tplay sets no D0."""
    play = play or {**PLAYBACKS, **ARGUMENT_PLAYBACKS}[label]
    count = len(RECORDINGS[play.recording].records) if play.count is None else play.count
    at = RECORD_AT + (ODD if label == AT_AN_ODD_ADDRESS else 0)

    def machine():
        return merge_pokes(recorded(play.recording), play.staged)
    return aes_switching.SwitchingRow(label, AP_TPLAY, (at, count, play.scale), machine, play.at_idle, answered=False)


# ---- THE ROWS -------------------------------------------------------------------------------------------------------------------
# PRICED: registered rows that switch (`aes_switching.register_row`: Tier 1 their companion, both blobs, the table).
# The rest are Tier 1's alone, each for its reason:
#   * another count or scale of a priced row, a recording that is only a playback's machine — nothing new to price;
#   * A RECORDING WITH ANOTHER PROCESS'S TURN INSIDE IT (ONTO_AND_OFF_THE_BAR): the events delivered inside the foreign
#     window are run — and RECORDED — by the ROM's forker on both shores (the window is the ROM's code), so on a blob
#     the buffer holds the ROM's fork-function addresses where our ap_trecd looks for our own, and numbers them 0.
#     The registry relocates a recording where a run begins and ends and where a delivery is laid, not where a
#     window closes (`test_aes_aptape.py` holds the refusal);
#   * the labelled class.
PRICED_RECORDINGS = (FULL, MERGED, A_KEY, ENDED_EARLY, NOTHING, UNASKED)
RECORDING_ROWS = {name: recording_row(name) for name in RECORDINGS}
PLAYBACK_ROWS = {label: playback_row(label) for label in PLAYBACKS}
ARGUMENT_ROWS = {label: playback_row(label) for label in ARGUMENT_PLAYBACKS}
EVERY_ROW = {row.label: row for row in (*RECORDING_ROWS.values(), *PLAYBACK_ROWS.values(), *ARGUMENT_ROWS.values())}
assert len(EVERY_ROW) == len(RECORDINGS) + len(PLAYBACKS) + len(ARGUMENT_PLAYBACKS), "two rows of one label"
PRICED = {row.label: row for row in (*(RECORDING_ROWS[name] for name in PRICED_RECORDINGS),
                                     *(PLAYBACK_ROWS[label] for label in PRICED_PLAYBACKS))}


# ---- A RECORDING PAST 32,767 BYTES: Tier 1 alone ---------------------------------------------------------------------------------
# ap_trecd counts the records made as the cursor's distance CUT TO A WORD and divided SIGNED (`$fe67b6 move.w d0,d6 /
# ext.l d6 / divs.w #8,d6`), and numbers them under a signed compare (`$fe6812 cmp.w d6,d5 / blt`). A count of 0 records
# until Control-backslash (above), so a recording runs past 4,095 records by ROM-run means alone: the mouse moved a
# packet at a time — a mouse record each — over as many idles as it takes. THE BUFFER is free RAM of the snapshot (the
# staged window is 24 KB: too small), held clear where the row is made.
# WHY TIER 1 ALONE: one ROM run of it is some ten seconds; a blob's pair, the table's and the sweeps' replays would
# each pay that again for a row whose price is the short recordings' — the loop it would add is the one that numbers
# NO record.
LONG_RECORD_AT = 0x50000
PACKETS_AN_IDLE = 30                    # under the fork queue's 32 entries (AES_FORK_ENTRIES), which forker empties at each idle
IDLES_OF_PACKETS = 137                  # the fewest idles of thirty that pass 4,095 records
A_LONG_RECORDING_S_RECORDS = IDLES_OF_PACKETS * PACKETS_AN_IDLE
A_LONG_RECORDING_S_BYTES = A_LONG_RECORDING_S_RECORDS * RECORD.size
MOST_BYTES_A_SIGNED_WORD_COUNTS = 0x7FFF
assert MOST_BYTES_A_SIGNED_WORD_COUNTS < A_LONG_RECORDING_S_BYTES < MOST_BYTES_A_SIGNED_WORD_COUNTS + PACKETS_AN_IDLE * RECORD.size
A_LONG_RECORDING = "a count of 0 over 4,110 packets: past 32,767 bytes the records are counted below 0, and none is numbered"
A_LONG_RECORDING_S_BUDGET = 8_000_000   # declared from its measured run of 1,452,102 instructions (A CASE'S OWN BUDGET)
TO_AND_FRO = ((1, 0), (-1, 0)) * (PACKETS_AN_IDLE // 2)


def _to_and_fro(image):
    """Thirty packets, the mouse a pixel right and back: thirty mouse records and the mouse where it was."""
    return aes_event.taken_in_place(image, aes_event.moving_by(*TO_AND_FRO))


def a_long_recording_row():
    """THE ROM'S OWN appl_trecord(buffer, 0) over the running desk, 4,110 packets taken at 137 idles, then
    Control-backslash, then the ticks that wake it: a row that switches (Tier 1's alone)."""
    image = make_image(desk_running())
    assert not any(image[LONG_RECORD_AT:LONG_RECORD_AT + A_LONG_RECORDING_S_BYTES + RECORD.size]), "the buffer is free RAM"
    at_idle = {**dict.fromkeys(range(IDLES_OF_PACKETS), _to_and_fro),
               IDLES_OF_PACKETS: (CONTROL, BACKSLASH), IDLES_OF_PACKETS + 1: ticks(POLL_TICKS)}
    return aes_switching.SwitchingRow(A_LONG_RECORDING, AP_TRECD, (LONG_RECORD_AT, 0), desk_running, at_idle,
                                      budget=A_LONG_RECORDING_S_BUDGET)


def register():
    """The priced rows REGISTERED (`aes_switching.register_row`): `{the row's name in the registry: the row}`."""
    return {aes_switching.row_name(row): row for row in map(aes_switching.register_row, PRICED.values())}


REGISTERED = register()
