"""The MFP TIMER C handler @ $fc30c4 — vector $114, two hundred times a second.

The most-executed routine in the ROM, and three routines in one: the 200 Hz tick count, the Dosound
driver's step, and the keyboard's auto-repeat countdowns, behind a divider that lets two of the three
run at 50 Hz.

WHAT EVERY CASE HERE DECLARES. The handler ends by clearing its own bit of the MFP's in-service
register — a READ-MODIFY-WRITE of $fffa11, spelt through `include/mfp.h`'s declared-map door — so
every case says what that register held (`io_seed`) and the byte stored is compared against it. A
case that touches the Dosound driver's mixer register declares the chip too (`psg_seed`), because
that register is read back before it is written and the six bits the list does not supply are
whatever the chip already had.

THE AUTO-REPEAT'S LAST ARM IS REACHABLE NOW, and it was not: `$fc2c42` is `kbd_queue_key`
(`src/bios/keyboard.c`), so the interval RELOAD and the INJECTION — the two instructions at the
bottom of the countdown — are a case rather than a halt. What that case needs beyond the countdown
is the keyboard's own state, which is why it stages the IKBD ring and `kbshift` where every other
case here leaves them alone.
"""
import ctypes
import struct

import pytest

import case
import isr
import iorec
from harness import BASE_IMAGE, addrs, _lib
from recreate_kit import os_map

_lib.isr_timer_c.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.isr_timer_c.restype = None

# ---- this battery's corner of the staging band ---------------------------------------------------
TIMER_STUB = isr.STUB_BAND + 0x00
DECOY_STUB = isr.STUB_BAND + 0x10
MARKS = isr.MARKS
SOUND_LIST = isr.STUB_BAND + 0x40
SOUND_LIST_BYTES = 0x40
assert SOUND_LIST + SOUND_LIST_BYTES <= isr.ISR_BAND + isr.ISR_BAND_BYTES

MARK = isr.MARK
# What the case declares the MFP's in-service register B held. Not 0, and not a byte with channel
# 5's own bit clear: the point of declaring it is that the SEVEN OTHER channels' flags survive the
# acknowledgement, and only a byte that has them set can show it.
ISRB_HELD = 0xFF
# The four states the divider's rotate cycles through on a real machine — $4444 is what the captured
# snapshot holds, and it is the ONE of the four whose rotate comes out negative, so the body runs on
# one tick in four and the other three only count and acknowledge.
DIVIDER_CYCLE = (0x4444, 0x8888, 0x1111, 0x2222)


def rotated_once(divider):
    """`rol.w` by one: the bit that leaves the top comes back in at the bottom."""
    return ((divider << 1) | (divider >> 15)) & 0xFFFF

WRITE, READ = os_map.OS_PSG_EVENT_WRITE, os_map.OS_PSG_EVENT_READ


marker_routine = isr.marker_routine


def quiet_pokes(overrides=None):
    """A tick with nothing to do: no sound list, no key held, and a divider that runs the body.

    `overrides` is a dict rather than keyword arguments because every key is an ADDRESS.
    """
    return {addrs.SYSVAR_TIMER_C_DIVIDER: struct.pack(">H", 0x4444),
            addrs.SOUND_LIST_POINTER: struct.pack(">I", 0),
            addrs.SYSVAR_KB_REPEAT_KEY: b"\x00",
            addrs.SYSVAR_ETV_TIMER: struct.pack(">I", TIMER_STUB),
            **(overrides or {})}


def _glue(lib, buf):
    lib.isr_timer_c(buf)


def run(pokes=None, *, routines=None, psg_seed=None, poison=True, isrb=ISRB_HELD):
    """One differential of the timer C handler over a declared MFP and a staged tick vector."""
    if routines is None:
        routines = {TIMER_STUB: marker_routine()}
    return isr.run(addrs.ISR_TIMER_C, _glue,
                   pokes=pokes if pokes is not None else quiet_pokes(),
                   routines=routines, poison=poison, psg_seed=psg_seed,
                   io_seed={addrs.MFP_ISRB: isrb})


long_in_snapshot = isr.long_in_snapshot


def acknowledgement(isrb=ISRB_HELD):
    """What clearing channel 5's in-service bit looks like on the two off-image streams."""
    return ([(addrs.MFP_ISRB, 1, isrb)],
            [(addrs.MFP_ISRB, 1, isrb & ~(1 << addrs.MFP_ISRB_TIMER_C_BIT))])


# ---- the tick, the divider and the acknowledgement ------------------------------------------------

def test_the_vector_table_still_points_at_this_handler():
    assert isr.vector_in_snapshot(addrs.VECTOR_TIMER_C) == addrs.ISR_TIMER_C


@pytest.mark.parametrize("divider", DIVIDER_CYCLE)
def test_the_tick_is_counted_and_the_channel_acknowledged_on_both_paths(divider):
    """`_hz_200` is bumped before the divider is rotated and the MFP bit is cleared after the two
    paths meet, so a tick that does no work still does both. The four states of the real machine's
    divider are one cycle, and only one of them runs the body."""
    info = run(quiet_pokes({addrs.SYSVAR_TIMER_C_DIVIDER: struct.pack(">H", divider)}))
    reads, writes = acknowledgement()

    assert case.written(info, addrs.SYSVAR_HZ_200, 4) == long_in_snapshot(addrs.SYSVAR_HZ_200) + 1
    assert info["regs"]["io_events"] == reads
    assert info["regs"]["hw_writes"] == writes
    assert (MARKS in info["writes"]) == bool(rotated_once(divider) & 0x8000), \
        "the body ran on the wrong tick of the divider's cycle"


# Divider words that separate a ROTATE from everything it could be mistaken for: a shift (which
# loses the top bit rather than returning it), a counter, and a test of the value BEFORE the rotate.
# $8000 rotates to $0001 — positive — and $0001 to $0002; $4000 to $8000, the only one of these that
# runs the body; $ffff and $0000 are their own fixed points.
@pytest.mark.parametrize("divider", (0x0000, 0x0001, 0x4000, 0x8000, 0xFFFF, 0x0002, 0xC000))
def test_the_divider_is_rotated_by_one_and_the_body_runs_on_the_negative_result(divider):
    rotated = rotated_once(divider)
    info = run(quiet_pokes({addrs.SYSVAR_TIMER_C_DIVIDER: struct.pack(">H", divider)}))

    assert case.written(info, addrs.SYSVAR_TIMER_C_DIVIDER, 2) == rotated
    assert (MARKS in info["writes"]) == bool(rotated & 0x8000)


@pytest.mark.parametrize("isrb", (0xFF, 0x20, 0xDF, 0x00, 0xA5))
def test_the_acknowledgement_keeps_every_other_channel_s_in_service_bit(isrb):
    """The whole reason this goes through the declared map rather than `hw_bclr8`: the byte stored
    is a function of the byte the case says the register held, so a reconstruction that wrote a
    constant — or cleared the wrong bit — reds on the write ledger's VALUE."""
    reads, writes = acknowledgement(isrb)
    info = run(isrb=isrb)
    assert info["regs"]["io_events"] == reads
    assert info["regs"]["hw_writes"] == writes


# ---- the OS tick vector ---------------------------------------------------------------------------

def test_the_body_calls_etv_timer():
    assert run()["writes"][MARKS] == MARK


def test_the_tick_vector_called_is_the_one_etv_timer_names_and_not_another():
    info = run(routines={TIMER_STUB: marker_routine(0), DECOY_STUB: marker_routine(1)})
    assert info["writes"][MARKS] == MARK and MARKS + 1 not in info["writes"]


def test_the_calibration_word_is_pushed_in_front_of_the_tick_vector():
    """`move.w timr_ms,-(sp) / jsr (a0) / addq.w #2,sp` — TWO bytes of frame, so the stub finds the
    calibration at `4(sp)` and not the high half of a wider slot.

    THE ORACLE'S CLAIM ALONE, and deliberately not one of this battery's registered cases. Off
    target the candidate reaches the routine through a hook that is handed the word as a value, so
    nothing here says where on a stack it was; what holds the reconstruction to it is the TARGET
    build, whose `call_vector_word` is the ROM's own three instructions (`include/staged_call.h`).
    """
    calibration = 0x1234
    stub = (isr.store_frame_word(MARKS) + isr.RTS,
            lambda buf, argument: isr.poke(buf, MARKS, struct.pack(">H", argument)))
    info = run(quiet_pokes({addrs.SYSVAR_TIMR_MS: struct.pack(">H", calibration)}),
               routines={TIMER_STUB: stub})
    assert case.written(info, MARKS, 2) == calibration


# ---- the keyboard's auto-repeat ---------------------------------------------------------------------
A_SCANCODE = 0x1E                       # 'A' — any non-zero byte; the handler never decodes it here
REPEAT_ENABLED = 1 << addrs.CONTERM_REPEAT_BIT


# POISONING A COUNTDOWN FEEDS THE ROUTINE A DIFFERENT COUNT. The attribution pass re-runs both cores
# over an image whose oracle-written bytes are inverted, so a countdown that this tick left at N is
# re-entered at `N ^ $ff` — and a value that lands on 1 there runs the poisoned tick all the way into
# the auto-repeat INJECTION. That is an ordinary arm now rather than a halt, but it writes the IKBD
# ring, so the counts below are still chosen to keep the poisoned run out of it: a case that reaches
# the injection stages the ring for it, which is the one at the bottom of this section.
def repeat_pokes(delay, interval, key=A_SCANCODE, conterm=REPEAT_ENABLED | 1, overrides=None):
    return quiet_pokes({addrs.SYSVAR_CONTERM: bytes([conterm]),
                        addrs.SYSVAR_KB_REPEAT_KEY: bytes([key]),
                        addrs.SYSVAR_KB_REPEAT_DELAY: bytes([delay]),
                        addrs.SYSVAR_KB_REPEAT_LEFT: bytes([interval]),
                        **(overrides or {})})


@pytest.mark.parametrize("conterm", (0, 1, 0xFD, 0x80))
def test_repeating_switched_off_in_conterm_counts_nothing_down(conterm):
    """`btst #1,conterm` — bit 1 alone, so bit 0's key click and the six bits above are not part of
    the test. A reconstruction testing the whole byte passes 0 and fails $fd."""
    info = run(repeat_pokes(delay=1, interval=1, conterm=conterm))
    assert addrs.SYSVAR_KB_REPEAT_DELAY not in info["writes"]
    assert addrs.SYSVAR_KB_REPEAT_LEFT not in info["writes"]


def test_no_key_held_counts_nothing_down():
    info = run(repeat_pokes(delay=1, interval=1, key=0))
    assert addrs.SYSVAR_KB_REPEAT_DELAY not in info["writes"]
    assert addrs.SYSVAR_KB_REPEAT_LEFT not in info["writes"]


@pytest.mark.parametrize("delay", (2, 3, 0x19, 0xFF))
def test_a_key_still_inside_its_initial_delay_counts_only_that_down(delay):
    """The interval is 2 rather than 1 so that the poisoned re-run of the $ff case — which enters
    with a delay of 1 and therefore falls through into the interval — still has a tick to spend."""
    info = run(repeat_pokes(delay=delay, interval=2))
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_DELAY] == delay - 1
    assert addrs.SYSVAR_KB_REPEAT_LEFT not in info["writes"]


@pytest.mark.parametrize("interval", (2, 3, 0xFF))
def test_the_last_tick_of_the_delay_falls_straight_into_the_interval(interval):
    """`subq.b #1,$e80 / bne` — the delay reaching zero does NOT cost a tick of its own: the same
    entry goes on to decrement the interval. A reconstruction that returned after the delay hit zero
    is one tick slow on every held key."""
    info = run(repeat_pokes(delay=1, interval=interval))
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_DELAY] == 0
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_LEFT] == interval - 1


# $ff is left out: the poisoned re-run would enter with an interval of 1 and reach the injection,
# which this case stages no ring for.
@pytest.mark.parametrize("interval", (2, 3, 0x1E, 0xFE))
def test_a_spent_delay_counts_the_interval_down_on_every_tick(interval):
    """`tst.b $e80 / beq` — a delay ALREADY at zero is not decremented (it would wrap to $ff and
    the key would stop repeating for 255 ticks); the interval is what counts."""
    info = run(repeat_pokes(delay=0, interval=interval))
    assert addrs.SYSVAR_KB_REPEAT_DELAY not in info["writes"]
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_LEFT] == interval - 1


@pytest.mark.parametrize("held", (A_SCANCODE, 0x10, 0x39))
def test_the_last_tick_of_the_interval_reloads_it_and_repeats_the_held_key(held):
    """THE ARM THIS BATTERY COULD NOT REACH. `move.b $e83,$e81 / move.b $e7f,d0 / lea $c76,a0 /
    bsr $fc2c42`: the interval is reloaded from `Kbrate`'s own byte and the HELD scancode goes into
    the IKBD's ring through the same routine a key the 6301 just sent uses.

    Three scancodes, because the injection is the only place this handler's held byte is read as
    anything but "non-zero" — a reconstruction that injected a constant, or the interval, passes on
    one of them.
    """
    ring = iorec.staged(addrs.IOREC_IKBD, 0, 0)
    info = run(repeat_pokes(delay=0, interval=1, key=held,
                            overrides={**ring, addrs.KBSHIFT: b"\x00"}))
    assert info["writes"][addrs.SYSVAR_KB_REPEAT_LEFT] == BASE_IMAGE[addrs.KBRATE_REPEAT]
    buffer = iorec.buffer_of(addrs.IOREC_IKBD)
    assert info["writes"][buffer + addrs.IOREC_KEY_BYTES + 1] == held
    assert case.written(info, addrs.IOREC_IKBD + addrs.IOREC_TAIL, 2) == addrs.IOREC_KEY_BYTES


# ---- the Dosound driver ------------------------------------------------------------------------------

def sound_pokes(commands, *, wait=0, ramp=0, at=SOUND_LIST):
    return quiet_pokes({addrs.SOUND_LIST_POINTER: struct.pack(">I", at),
                        addrs.SOUND_LIST_DELAY: bytes([wait]),
                        addrs.SOUND_RAMP_VALUE: bytes([ramp]),
                        SOUND_LIST: bytes(commands)})


def run_sound(pokes, **kwargs):
    """...and the run, WITHOUT the attribution pass — see the note below.

    Poisoning inverts every oracle-written byte, and one of them is the driver's own CURSOR: the
    poisoned re-run therefore enters with a pointer into the middle of nowhere and walks bytes that
    are all zero, which the list format reads as "write register 0" for ever. The run hits the
    oracle's instruction cap rather than proving anything.

    WHAT COVERS THE SAME GROUND. The attribution pass exists for a store whose value the byte
    already held, and every byte a list-running tick stores here CHANGES: the cursor moves off the
    address the case poked, the ramp accumulator is stepped by a non-zero step, and a pause's own
    count is asserted at three values that differ from the zero it is entered with. The single
    exception is the zero-tick pause, where the delay is stored 0 over 0 — and the STORE itself is
    what the three-value case above it attributes; that case is about the CURSOR.
    """
    return run(pokes, poison=False, **kwargs)


END_OF_LIST = (0xFF, 0x00)              # a wait command whose count is zero: the list stops here
PAUSE = 0xFF                            # ...and the same command with a count is an ordinary pause


def test_an_idle_driver_touches_nothing():
    """`move.l $e8a,d0 / beq` — a zero cursor is "no list", and the driver does not even look at its
    wait counter."""
    info = run()
    assert addrs.SOUND_LIST_DELAY not in info["writes"]
    assert info["regs"]["psg_events"] == []


@pytest.mark.parametrize("wait", (1, 2, 0xFF))
def test_a_driver_inside_a_pause_only_counts_it_down(wait):
    info = run(sound_pokes((0, 1) + END_OF_LIST, wait=wait))
    assert info["writes"][addrs.SOUND_LIST_DELAY] == wait - 1
    assert info["regs"]["psg_events"] == []
    assert addrs.SOUND_LIST_POINTER not in info["writes"], "the cursor moved during a pause"


# Register/value pairs a list can carry. Register 7 is left out — it is the read-modify-write below
# — and so is anything above 15, which the chip's four-bit select latch cannot name and which BOTH
# sides refuse rather than mask down (`psg.h`).
@pytest.mark.parametrize("reg,value", ((0, 0xFF), (1, 0x0F), (8, 0x10), (13, 0x0E), (15, 0xAA)))
def test_a_register_byte_writes_that_register_and_the_driver_runs_on(reg, value):
    info = run_sound(sound_pokes((reg, value) + END_OF_LIST))
    assert info["regs"]["psg_events"] == [(WRITE, reg, value)]


def test_every_register_pair_before_the_next_command_is_written_in_order():
    """The driver does not stop at one: it runs bytes until a COMMAND ends the tick, so a list can
    program the whole chip in a single interrupt."""
    pairs = ((0, 0x11), (1, 0x02), (8, 0x0F), (2, 0x33))
    info = run_sound(sound_pokes(sum(pairs, ()) + END_OF_LIST))
    assert info["regs"]["psg_events"] == [(WRITE, reg, value) for reg, value in pairs]


# What the mixer's read-modify-write keeps and what it replaces: the chip's two I/O-direction bits
# survive and the six tone/noise enables come from the list.
@pytest.mark.parametrize("held,supplied", ((0xC0, 0x3F), (0x40, 0x00), (0x00, 0x3F), (0xFF, 0x00),
                                           (0x80, 0x15), (0x7F, 0xFF)))
def test_the_mixer_register_keeps_the_chip_s_two_port_direction_bits(held, supplied):
    """`move.b $ff8800,d0 / andi.b #$c0,d0 / or.b d1,d0` over `andi.b #$3f,d1` — the one register the
    driver reads before it writes, so what the chip already held is an INPUT of the run."""
    info = run_sound(sound_pokes((addrs.PSG_MIXER_REGISTER, supplied) + END_OF_LIST),
               psg_seed={addrs.PSG_MIXER_REGISTER: held})
    merged = (held & addrs.PSG_MIXER_PORT_MASK) | (supplied & addrs.PSG_MIXER_CHANNEL_MASK)
    assert info["regs"]["psg_events"] == [(READ, addrs.PSG_MIXER_REGISTER, held),
                                          (WRITE, addrs.PSG_MIXER_REGISTER, merged)]


@pytest.mark.parametrize("value", (0x00, 0x42, 0xFF))
def test_command_80_loads_the_ramp_accumulator_and_runs_on(value):
    info = run_sound(sound_pokes((addrs.DOSOUND_LOAD_TEMP, value) + END_OF_LIST))
    assert info["writes"][addrs.SOUND_RAMP_VALUE] == value
    assert info["regs"]["psg_events"] == []


# `$81 <reg> <step> <end>`: the accumulator is stepped, written to the register, and the whole
# command is re-read next tick until the accumulator equals the end value.
@pytest.mark.parametrize("start,step,end", ((0x10, 0x01, 0x11), (0x10, 0xFF, 0x0F), (0x00, 0x80, 0x80),
                                            (0xFF, 0x01, 0x00)))
def test_command_81_that_reaches_its_end_steps_once_and_moves_on(start, step, end):
    info = run_sound(sound_pokes((addrs.DOSOUND_RAMP, 8, step, end) + END_OF_LIST, ramp=start))
    assert info["writes"][addrs.SOUND_RAMP_VALUE] == end
    assert info["regs"]["psg_events"] == [(WRITE, 8, end)]
    assert case.written(info, addrs.SOUND_LIST_POINTER, 4) == SOUND_LIST + 4


# The mixer's read-modify-write is `write_one_register`'s and NOT the ramp's: the ROM's $81 arm
# selects the register and writes the accumulator straight to the data port, whatever register it
# names. The chip is seeded with its port-direction bits set, so a reconstruction that routed the
# ramp through the same helper as a plain register byte would READ $ff8800 first and store the
# merged byte — two events where this is one, and a different value in it.
@pytest.mark.parametrize("start,step,end", ((0x10, 0x01, 0x11), (0x10, 0x01, 0x20)))
def test_a_ramp_on_the_mixer_register_writes_it_outright(start, step, end):
    held = 0xC0
    info = run_sound(sound_pokes((addrs.DOSOUND_RAMP, addrs.PSG_MIXER_REGISTER, step, end)
                                 + END_OF_LIST, ramp=start),
                     psg_seed={addrs.PSG_MIXER_REGISTER: held})
    stepped = (start + step) & 0xFF
    assert info["regs"]["psg_events"] == [(WRITE, addrs.PSG_MIXER_REGISTER, stepped)]


@pytest.mark.parametrize("start,step,end", ((0x10, 0x01, 0x20), (0x00, 0x02, 0xFF), (0x80, 0xFE, 0x00)))
def test_command_81_that_has_not_reached_its_end_winds_the_cursor_back_over_itself(start, step, end):
    """`subq.w #4,a0` — the WHOLE command, so the next tick reads the same four bytes and steps
    again. A reconstruction that wound back by three would re-read the operands as a command."""
    info = run_sound(sound_pokes((addrs.DOSOUND_RAMP, 8, step, end) + END_OF_LIST, ramp=start))
    stepped = (start + step) & 0xFF
    assert info["writes"][addrs.SOUND_RAMP_VALUE] == stepped
    assert info["regs"]["psg_events"] == [(WRITE, 8, stepped)]
    assert case.written(info, addrs.SOUND_LIST_POINTER, 4) == SOUND_LIST


# Every command byte from $82 up is a pause, and so is $ff — which the ROM reaches by a different
# branch (`addq.b #1,d0 / bpl`) than the rest. Both arms are one behaviour and both are tested.
#
# TWO CLAIMS, SEVEN PAIRS rather than the cross product of them: that each of the five command bytes
# is a pause, and that the tick count is stored as it stands at 1, 2 and $ff. Every pair below is
# the first appearance of a command or of a count; a full 5x3 would run eight more cases that repeat
# a claim two others already make.
@pytest.mark.parametrize("command,ticks", ((0x82, 1), (0x83, 1), (0xC0, 1), (0xFE, 1), (0xFF, 1),
                                           (0x82, 2), (0x82, 0xFF)))
def test_a_pause_command_sets_the_wait_and_leaves_the_cursor_past_it(command, ticks):
    info = run_sound(sound_pokes((command, ticks) + END_OF_LIST))
    assert info["writes"][addrs.SOUND_LIST_DELAY] == ticks
    assert case.written(info, addrs.SOUND_LIST_POINTER, 4) == SOUND_LIST + 2


@pytest.mark.parametrize("command", (0x82, 0xFF))
def test_a_pause_of_zero_ticks_ends_the_list(command):
    """`movea.w #0,a0` — the cursor stored is ZERO, which is what the next tick reads as "nothing is
    playing". A reconstruction that only stored the wait would restart the list from its end."""
    info = run_sound(sound_pokes((command, 0)))
    assert info["writes"][addrs.SOUND_LIST_DELAY] == 0
    assert case.written(info, addrs.SOUND_LIST_POINTER, 4) == 0


def test_the_list_is_read_from_wherever_the_cursor_points():
    """...and not from a base the reconstruction remembers: the same list staged further along."""
    elsewhere = SOUND_LIST + 0x10
    info = run_sound(sound_pokes((0, 0x11) + END_OF_LIST,
                           at=elsewhere)
               | {elsewhere: bytes((3, 0x22) + END_OF_LIST)})
    assert info["regs"]["psg_events"] == [(WRITE, 3, 0x22)]


def test_a_driver_that_was_paused_resumes_where_it_stopped():
    """The pair that says the wait counter and the cursor are one mechanism: a tick that finds the
    counter at 1 spends it, and the next tick runs the byte the cursor is already on."""
    spent = run_sound(sound_pokes((5, 0x99) + END_OF_LIST, wait=1))
    assert spent["regs"]["psg_events"] == []
    resumed = run_sound(sound_pokes((5, 0x99) + END_OF_LIST, wait=0))
    assert resumed["regs"]["psg_events"] == [(WRITE, 5, 0x99)]


# ---- what the handler gives back ---------------------------------------------------------------------

def test_the_handler_gives_every_register_back():
    isr.assert_registers_survived(run())


def test_the_divided_away_tick_gives_them_back_too():
    """...and it never saved them: three instructions and a `bclr`."""
    isr.assert_registers_survived(run(quiet_pokes({addrs.SYSVAR_TIMER_C_DIVIDER: b"\x11\x11"})))




# ---- the cases this battery REGISTERS -----------------------------------------------------------
# Two, because the divider makes two routines out of one: the tick that only counts and
# acknowledges, and the tick that runs the driver, the auto-repeat and the OS vector. A 200 Hz
# handler's cost is three quarters the first and one quarter the second.
IO_QUIET = {addrs.MFP_ISRB: ISRB_HELD}

# A serviced tick with something in every part of it: a sound list that writes two registers and
# then pauses, a key inside its initial delay, and the tick vector.
SERVICED_TICK = sound_pokes((0, 0x11, addrs.PSG_MIXER_REGISTER, 0x3F, PAUSE, 2)) | {
    addrs.SYSVAR_CONTERM: bytes([REPEAT_ENABLED | 1]),
    addrs.SYSVAR_KB_REPEAT_KEY: bytes([A_SCANCODE]),
    addrs.SYSVAR_KB_REPEAT_DELAY: bytes([4]),
    addrs.SYSVAR_KB_REPEAT_LEFT: bytes([4])}

REGISTERED = (
    {"name": "isr_timer_c, a divided-away tick", "entry": addrs.ISR_TIMER_C,
     "pokes": quiet_pokes({addrs.SYSVAR_TIMER_C_DIVIDER: b"\x11\x11"}), "io_seed": IO_QUIET},
    {"name": "isr_timer_c, a serviced tick", "entry": addrs.ISR_TIMER_C,
     "pokes": SERVICED_TICK, "io_seed": IO_QUIET,
     "psg_seed": {addrs.PSG_MIXER_REGISTER: 0xC0},
     "routines": {TIMER_STUB: marker_routine()}},
)
VERIFIED_CASES = tuple(isr.registered(spec) for spec in REGISTERED)
# ...and the same two as WHOLE-HANDLER cases: `src/bios/isr.S` — the tick count, the divider and the
# `bclr` acknowledgement included — held to the image, the WHOLE register file and the chip
# (`isr.transcribed`). Both frames are already in the band the diff drops, so the specs are the
# registered ones unchanged.
TRANSCRIBED = REGISTERED
TRANSCRIPTION_CASES = tuple(isr.transcribed(spec) for spec in TRANSCRIBED)


@pytest.mark.parametrize("spec", REGISTERED, ids=lambda spec: spec["name"])
def test_every_registered_case_is_one_this_battery_proves(spec):
    """The row and the differential are the SAME spec (`isr.registered` / `isr.run_spec`).

    Without the attribution pass, for `run_sound`'s reason: the serviced tick stores the driver's
    cursor, and a poisoned cursor walks zeroed memory as an endless run of register writes.
    """
    isr.run_spec(spec, _glue, poison=False)


def test_the_stub_at_the_vector_is_the_rom_s_own_bytes():
    """`src/bios/isr.S`'s timer C stub against the ROM's own words. The acknowledgement is in there:
    one `bclr` on $fffa11 where the C core spells a declared read and a ledgered store, which is the
    difference the Tier 3 row measures and this says is a difference in CYCLES alone."""
    isr.assert_the_stub_is_the_rom_s_bytes("ISR_TIMER_C")
