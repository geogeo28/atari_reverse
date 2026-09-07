"""Differential tests for src/irq.c: the level-4 vertical blank, the MFP channel-6 IKBD/MIDI ACIA
handler and its two joystick continuations, and the TOS joystick callback the ACIA one displaced.

THREE THINGS ARE DIFFERENT ABOUT AN INTERRUPT, and every case here lives with all three.

(1) IT IS ENTERED BY THE 68000, NOT BY A CALLER. On the machine the exception sequence pushes SR and
PC and the routine leaves through `rte`. Every one of these four balances its own pushes before that
instruction, so the frame is read by the `rte` alone — which means a case can enter at the routine's
first instruction and STOP AT THE `rte` without ever fabricating a frame, and the oracle's A7 at the
checkpoint is the harness's own. That is what `STOP_*` below are, and `acia_ikbd_isr` needs four of
them because it has four `rte`s: one per arm, and the case's declared ACIA byte is what picks the
arm and therefore the checkpoint.

(2) ITS INPUT IS OFF-IMAGE. The byte the 6850 hands over is `hw_read8(OS_HW_ACIA_DATA)` on the
candidate side and a `move.b $fffffc02,d1` on the oracle's, and the model serves it only to a case
that DECLARES it (`hw_seed=`). The port is VOLATILE — a read pops the receive register — so one
declaration is one read, which is exactly what each of these routines makes.

(3) ITS OUTPUT IS PARTLY OFF-IMAGE TOO. Every path ends `bclr #6,$fffffa11`, which lands in the
ordered hardware WRITE ledger the harness compares rather than in the image; and `vbl_handler`'s
`jmp` chains to a TOS vector the model does not have, which is why its slice ends at the `jmp` and
the chain is a row in STATUS.md's "Unpinned on target".
"""
import random

import pytest

import abi
import conftest
import emu
import harness

# ---- the routines, and where each slice stops ---------------------------------------------------
ENTRY_VBL_HANDLER = 0x11636
# `jmp $1164e.l` @ 0x1164e — the chain into TOS's old $70 handler, whose operand `boot_init` fills.
# The model has no vector there, so this is the end of what a differential can say about the VBL.
STOP_VBL_CHAIN = 0x1164e

ENTRY_ACIA_IKBD_ISR = 0x14218
STOP_ACIA_ISR_JOY0_HEADER = 0x1423a   # `rte` after re-pointing $118 at acia_joy0_byte
STOP_ACIA_ISR_JOY1_HEADER = 0x14256   # ...and at acia_joy1_byte
STOP_ACIA_ISR_KEY_MAKE = 0x142bc      # `rte` after the eight `bset` rungs
STOP_ACIA_ISR_KEY_BREAK = 0x1430a     # ...and after the eight `bclr` ones

ENTRY_ACIA_JOY0_BYTE = 0x1430c
STOP_ACIA_JOY0_RTE = 0x1432e
ENTRY_ACIA_JOY1_BYTE = 0x14330
STOP_ACIA_JOY1_RTE = 0x14352

ENTRY_TOS_JOYVEC_HANDLER = 0x141fa    # ends `rts`: it is a CALLBACK, so its run stops there

# ---- mirrors of include/irq.h (MIRROR_HEADER below) and of the headers it reads -----------------
VECTOR_ACIA = 0x118
FN_ACIA_IKBD_ISR = 0x14218
FN_ACIA_JOY0_BYTE = 0x1430c
FN_ACIA_JOY1_BYTE = 0x14330
MFP_ISRB = 0xfffa11
MFP_ISRB_ACIA_BIT = 6
IKBD_JOY0_PACKET_HEADER = 0xfe
IKBD_JOY1_PACKET_HEADER = 0xff
A_key_watch_scancodes = 0x17782
KEY_WATCH_SCANCODES = 8
SCANCODE_BREAK_BIT = 7
IKBD_JOY_PACKET_JOY0 = 1
IKBD_JOY_PACKET_JOY1 = 2

A_vbl_tick = 0x17720          # include/irq.h
A_joy0_state = 0x1777e
A_joy1_state = 0x1777f
A_key_bits = 0x17780
A_key_last_scancode = 0x17781
A_sound_module = 0x58944      # include/globals.h
SND_MUSIC_ACTIVE = 0x1e       # include/sound.h — the driver's only "a tune is playing" signal
SND_CHANNEL_A = 0x568         # include/sound.h — three channel structures, back to back
SND_CHANNELS = 3              # include/sound.h
SND_CHANNEL_STRIDE = 24       # include/sound.h
SCC_TRUE = 0xff               # include/common.h — what a 68000 `Scc` writes, one byte of ones
SND_ENTRY_MUSIC_START = 1256  # include/sound.h
SHIFTER_SYNC_50HZ = 1 << 1    # include/sound.h

# The shifter's sync byte, `os.h`'s OS_HW_SHIFTER_SYNC on the C side. `sound_vbl_tick` branches on
# bit 1 of it (50 Hz vs 60 Hz), so a case that reaches the module has to declare the machine.
HW_SHIFTER_SYNC = 0xff820a
HW_ACIA_DATA = 0xfffc02
BOTH_MACHINES = (SHIFTER_SYNC_50HZ, 0)

# The four `bclr #6,$fffffa11` sites, one per path that reaches an `rte`: the two joystick headers,
# the make ladder's tail and the break ladder's.
ACIA_END_OF_INTERRUPT_SITES = (0x14230, 0x1424c, 0x142b4, 0x14302)
BCLR_IMM_ABS_LONG = 0x08b9    # `bclr #<data>,xxx.l` — the instruction word all four share
# The 68000 aliases $fffffa11 onto the 24-bit bus address the kit's `hw_bclr8` takes.
OS_HW_BUS_MASK = 0xffffff

VBL_TICK_BYTES = 4
FUZZ_CHUNKS = 4

# The tune `music_start` is given to put the module into a state where `vbl_handler`'s call has a
# whole frame of music to do. Any of the five would serve; 1 is the in-game theme.
STAGED_TUNE = 1
# The three-byte IKBD joystick report `tos_joyvec_handler` is handed, parked in the test's scratch.
JOY_PACKET = abi.SCRATCH
JOY_PACKET_BYTES = 3


abi.declare_glue("g_vbl_handler", "g_acia_ikbd_isr", "g_acia_joy0_byte", "g_acia_joy1_byte")
abi.declare_glue("g_tos_joyvec_handler", args=1)


# =================================================================================================
# vbl_handler @ 0x11636 — SLICE [0x11636, 0x1164e)
# =================================================================================================


def _vbl_case(pokes, sync, note):
    abi.run_case(ENTRY_VBL_HANDLER, lambda lib, buf: lib.g_vbl_handler(buf), pokes=pokes,
                 stop_pc=STOP_VBL_CHAIN, hw_seed={HW_SHIFTER_SYNC: sync}, note=note)


@pytest.mark.parametrize("sync", BOTH_MACHINES)
@pytest.mark.parametrize("tick", (0, 1, 2, 0x7fffffff, 0xfffffffe, 0xffffffff))
def test_the_vbl_counts_a_frame_and_ticks_the_sound_module(tick, sync):
    """The counter's increment at both machine speeds, including the LONGWORD WRAP.

    `addq.l #1` on 0xffffffff gives 0, not a 33rd bit, and nothing in the handler guards it — so the
    frame pacer would see the counter go backwards once every 2^32 vertical blanks. The wrap is what
    separates a 32-bit increment from a 16-bit one, and 0x7fffffff separates it from a signed
    saturation; neither is reachable in a real session and both are cheap to state.

    The module's tick runs on every one of these, which is what makes the PSG ledger the second
    surface here: a reconstruction that bumped the counter and skipped `jsr 38(a0)` leaves the same
    image and an empty register stream.
    """
    _vbl_case({A_vbl_tick: tick.to_bytes(VBL_TICK_BYTES, "big")}, sync, f"tick={tick:#x}")


@pytest.fixture(scope="session")
def music_playing_pokes(post_load_image):
    """The module with a tune RUNNING, staged by the module's own `music_start`, as pokes.

    Without it every VBL case reaches a driver with nothing to play, and the tick's music half —
    the sequencer, the tempo divider, the whole reason the handler calls into the module at all —
    is skipped on both sides. The staging is the ORIGINAL's own routine run under the oracle, not a
    transcription of what it leaves; `test_the_staged_module_really_has_a_tune_running` is what says
    it did something.
    """
    entry = A_sound_module + SND_ENTRY_MUSIC_START
    pokes = abi.call_sequence_with_d0_pokes([(entry, STAGED_TUNE)])
    image = bytearray(post_load_image)
    for address, data in pokes.items():
        image[address:address + len(data)] = data
    final, _writes, _regs = emu.run(image, abi.STUB, hw_seed={HW_SHIFTER_SYNC: SHIFTER_SYNC_50HZ})
    return conftest.byte_run_pokes(post_load_image, bytearray(final))


def test_the_staged_module_really_has_a_tune_running(post_load_image, music_playing_pokes):
    """A staging that quietly did nothing would make the case below a duplicate of the idle one.

    It asserts on the MODULE'S OWN SIGNALS rather than on how many bytes moved: `music_active` is
    the one flag the driver exposes for "a tune is playing", and all three channel structures have
    to have been armed. A byte count was the first shape of this check and it was passing on
    HARNESS SCAFFOLDING — the sum ran over every poke above the module's base, which includes the
    stub at `abi.STUB` (measured 2026-09-07: 22 real bytes against a threshold of 32).
    """
    image = bytearray(post_load_image)
    for address, data in music_playing_pokes.items():
        image[address:address + len(data)] = data

    assert image[A_sound_module + SND_MUSIC_ACTIVE] == SCC_TRUE, (
        "the module's `music_active` flag is clear after `music_start`, so the staging did not "
        "start a tune and the VBL case below runs on an idle driver")
    for channel in range(SND_CHANNELS):
        at = A_sound_module + SND_CHANNEL_A + channel * SND_CHANNEL_STRIDE
        assert image[at:at + SND_CHANNEL_STRIDE] != post_load_image[at:at + SND_CHANNEL_STRIDE], (
            f"channel {channel}'s structure is untouched; `music_start` arms all three")


@pytest.mark.parametrize("sync", BOTH_MACHINES)
def test_the_vbl_ticks_a_running_tune(music_playing_pokes, sync):
    """The same handler over a driver that has a whole frame of music to do.

    This is the case that says the `jsr 38(a0)` is the REAL module entry and not merely a call that
    happened: on an idle driver the tick's music half returns almost at once, and here it steps the
    tempo divider, the sequencer and three channels, all of which land in the image and in the PSG
    register stream the harness compares.
    """
    pokes = dict(music_playing_pokes)
    pokes[A_vbl_tick] = (2).to_bytes(VBL_TICK_BYTES, "big")
    _vbl_case(pokes, sync, f"tune {STAGED_TUNE}, sync={sync:#x}")


def test_the_vbl_chain_operand_is_where_the_slice_stops():
    """`STOP_VBL_CHAIN` is the `jmp` whose OPERAND `boot_init` overwrites — not an arbitrary PC.

    The operand longword lives at `conftest.A_vbl_chain_vector`, immediately after the instruction,
    and the image ships it pointing at the `jmp` itself (a self-loop) until the boot chain fills it
    from the old $70. Both facts are read off the loaded image here, so a slice that stopped one
    instruction early — before the `movem.l` restore — would be a checkpoint this test does not
    describe.
    """
    assert conftest.A_vbl_chain_vector == STOP_VBL_CHAIN + 2, (
        "the chain's operand does not follow the `jmp` this slice stops at")
    shipped = int.from_bytes(bytes(harness.BASE_IMAGE[conftest.A_vbl_chain_vector:
                                                      conftest.A_vbl_chain_vector + 4]), "big")
    assert shipped == STOP_VBL_CHAIN, (
        f"the shipped chain operand is {shipped:#x}, not the self-loop {STOP_VBL_CHAIN:#x}")


# =================================================================================================
# acia_ikbd_isr @ 0x14218 and its two continuations
# =================================================================================================
#
# THE SCANCODE PICKS THE CHECKPOINT. The handler has four `rte`s and a case can name only one
# `stop_pc`, so the arm the declared byte takes is what the case has to stop at — which is also the
# cleanest statement of what each byte means.


def _isr_stop_pc(received):
    """The `rte` the handler reaches for `received`, which is the arm that byte selects."""
    if received == IKBD_JOY0_PACKET_HEADER:
        return STOP_ACIA_ISR_JOY0_HEADER
    if received == IKBD_JOY1_PACKET_HEADER:
        return STOP_ACIA_ISR_JOY1_HEADER
    return (STOP_ACIA_ISR_KEY_BREAK if received & (1 << SCANCODE_BREAK_BIT)
            else STOP_ACIA_ISR_KEY_MAKE)


def _isr_case(received, pokes=None, note=""):
    abi.run_case(ENTRY_ACIA_IKBD_ISR, lambda lib, buf: lib.g_acia_ikbd_isr(buf), pokes=pokes,
                 stop_pc=_isr_stop_pc(received), hw_seed={HW_ACIA_DATA: received},
                 note=f"received={received:#04x} {note}")


@pytest.mark.parametrize("header,expected", ((IKBD_JOY0_PACKET_HEADER, FN_ACIA_JOY0_BYTE),
                                             (IKBD_JOY1_PACKET_HEADER, FN_ACIA_JOY1_BYTE)))
def test_a_joystick_header_re_points_the_vector_at_its_continuation(header, expected):
    """The two-state machine: the header byte moves $118 and the handler does nothing else.

    Neither arm touches `key_last_scancode`, which is what separates a header from a key — and the
    post-load image holds a zero there, so a reconstruction that stored the header would differ. The
    vector really is the state: `test_the_vector_the_isr_installs_is_the_routine_named_here` pins
    that the address written is the continuation's entry rather than a number.
    """
    _isr_case(header, {A_key_last_scancode: b"\x00"}, note=f"-> {expected:#x}")


def test_the_vector_the_isr_installs_is_the_routine_named_here():
    """The two immediate operands the handler writes into $118, read out of the loaded image.

    A `move.l #$n,$118` whose n drifted would still pass every case above — both sides would write
    whatever the original writes — so the addresses `include/irq.h` names are pinned against the
    instruction rather than against the differential.
    """
    for site, expected in ((0x14228, FN_ACIA_JOY0_BYTE), (0x14244, FN_ACIA_JOY1_BYTE)):
        operand = int.from_bytes(bytes(harness.BASE_IMAGE[site:site + 4]), "big")
        assert operand == expected, (
            f"the `move.l #...,$118` at {site - 2:#x} names {operand:#x}, not {expected:#x}")


def test_the_end_of_interrupt_names_channel_six_at_every_rte_path():
    """The BIT the `bclr` clears is pinned by nothing the differential compares, so read it.

    `hw_bclr8` ledgers the byte the ORACLE's read-modify-write produces from the model's fabricated
    zero — `0 & ~(1 << bit)` — which is 0 for EVERY bit, so the write ledger holds
    (0xfffa11, width 1, value 0) whatever bit number the reconstruction names. `MFP_ISRB_ACIA_BIT`
    mutated to 0 therefore survives the whole battery (measured 2026-09-07). What IS checkable is
    the original's own instruction: `bclr #6,$fffffa11` encodes as 0x08b9, an immediate word and an
    absolute long, at each of the four paths that reach an `rte`.

    THE CHAIN IS TWO LINKS AND BOTH ARE NEEDED: this pins the PYTHON constant against the original's
    bytes, and `test_constants.py`'s `MIRRORS` check pins the C `#define` against that same Python
    constant. Either alone leaves one end free to drift.
    """
    for site in ACIA_END_OF_INTERRUPT_SITES:
        opcode = int.from_bytes(bytes(harness.BASE_IMAGE[site:site + 2]), "big")
        bit = int.from_bytes(bytes(harness.BASE_IMAGE[site + 2:site + 4]), "big")
        address = int.from_bytes(bytes(harness.BASE_IMAGE[site + 4:site + 8]), "big")
        assert opcode == BCLR_IMM_ABS_LONG, f"{site:#x} is not a `bclr #n,xxx.l`"
        assert bit == MFP_ISRB_ACIA_BIT, f"{site:#x} clears bit {bit}, not {MFP_ISRB_ACIA_BIT}"
        assert address & OS_HW_BUS_MASK == MFP_ISRB, (
            f"{site:#x} names {address:#x}, not the MFP's in-service register B")


def _watched_scancodes():
    """The eight scancodes the ladder compares against, read out of the LOADED IMAGE.

    Out of the image and not out of a list here, so a case cannot go stale against a table that
    moved: the table is initialised data and nothing at run time writes it.
    """
    at = A_key_watch_scancodes
    return list(bytes(harness.BASE_IMAGE[at:at + KEY_WATCH_SCANCODES]))


def test_the_watch_table_lists_one_scancode_twice():
    """0x00 appears at bit 3 AND bit 7, which is why a received 0x00 is not a no-op.

    The ladder is unrolled with no early exit, so both bits move together — the one place the
    "every rung always runs" shape is observable from the game's OWN data rather than from a poked
    table. `test_every_watched_scancode_moves_its_bit` drives it.
    """
    table = _watched_scancodes()
    assert table.count(0x00) == 2, f"the shipped watch table is {table}, with no repeated entry"


@pytest.mark.parametrize("bit", range(KEY_WATCH_SCANCODES))
@pytest.mark.parametrize("entry_bits", (0x00, 0xff, 0x5a))
def test_every_watched_scancode_moves_its_bit(bit, entry_bits):
    """Each of the eight, pressed and released, over three entry states of `key_bits`.

    The entry states matter because the rungs are `bset`/`bclr` and not a store: a reconstruction
    that assigned the whole byte would agree with every case entered at 0x00 and differ at 0xff.
    """
    scancode = _watched_scancodes()[bit]
    for received in (scancode, scancode | (1 << SCANCODE_BREAK_BIT)):
        _isr_case(received, {A_key_bits: bytes([entry_bits])}, note=f"bit {bit}")


@pytest.mark.parametrize("received", (0x00, 0x01, 0x0f, 0x7d, 0x7f, 0x80, 0x81, 0xfd))
def test_the_raw_scancode_byte_is_kept_whatever_the_ladder_does(received):
    """`key_last_scancode` takes the byte whatever it is; `key_bits` moves only on a match.

    THE POOL IS DELIBERATELY MIXED. 0x01, 0x0f, 0x7d, 0x81 and 0xfd match nothing in the table, so
    `key_bits` must come out untouched; 0x00 and its break form 0x80 match the table's DOUBLED entry
    and move bits 3 and 7 together. Both shapes have to leave the same raw byte behind, which is
    what this case is about.

    0x7f and 0x81 are the interesting ends: 0x7f is the largest MAKE code, and its break form 0xff
    is the joystick-1 header — so a release of scancodes 0x7e and 0x7f can never reach this arm at
    all, and the two rungs that would answer them are unreachable by construction rather than by the
    table's contents.
    """
    _isr_case(received, {A_key_bits: b"\xa5", A_key_last_scancode: b"\x5a"})


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_the_isr_over_every_byte_the_acia_can_hand_it(chunk):
    """ALL 256 received bytes, each against a random `key_bits` and scancode, sharded by `chunk`.

    EXHAUSTIVE AND NOT SAMPLED, because the input is one byte wide: the handler's whole decision is
    a three-way branch on it and then eight unrolled comparisons against a table read out of the
    image, so 256 cases is the entire domain and a fuzz over it was leaving roughly a third of the
    codes undriven on any given run. The two headers are in the sweep for the same reason they were
    in the fuzz — the arm a byte takes is the routine's first decision, and each byte's `stop_pc` is
    the `rte` that arm reaches.

    The ENTRY STATE is still random, and deliberately: the rungs are `bset`/`bclr` and not a store,
    so what a byte does depends on the byte already in `key_bits`, and the cases above drive the
    three states that separate an assignment from a bit operation.
    """
    rng = random.Random(0xac1a + chunk)
    for received in range(chunk, 0x100, FUZZ_CHUNKS):
        _isr_case(received, {A_key_bits: bytes([rng.randrange(0x100)]),
                             A_key_last_scancode: bytes([rng.randrange(0x100)])},
                  note="the exhaustive byte sweep")


@pytest.mark.parametrize("entry_vector", (0, FN_ACIA_IKBD_ISR, 0xdeadbeef))
@pytest.mark.parametrize("received,entry,stop,state", (
    (0x00, ENTRY_ACIA_JOY0_BYTE, STOP_ACIA_JOY0_RTE, A_joy0_state),
    (0x8f, ENTRY_ACIA_JOY0_BYTE, STOP_ACIA_JOY0_RTE, A_joy0_state),
    (0xff, ENTRY_ACIA_JOY0_BYTE, STOP_ACIA_JOY0_RTE, A_joy0_state),
    (0x00, ENTRY_ACIA_JOY1_BYTE, STOP_ACIA_JOY1_RTE, A_joy1_state),
    (0x8f, ENTRY_ACIA_JOY1_BYTE, STOP_ACIA_JOY1_RTE, A_joy1_state),
    (0xff, ENTRY_ACIA_JOY1_BYTE, STOP_ACIA_JOY1_RTE, A_joy1_state),
))
def test_a_continuation_stores_its_stick_and_hands_the_vector_back(received, entry, stop, state,
                                                                   entry_vector):
    """The second byte of a joystick report: store it, acknowledge the MFP, restore $118.

    0xff is a legitimate stick byte here and NOT a header — the continuation does not decode, it
    stores — which is the whole reason the two-state machine exists. The `entry_vector` sweep is
    what makes "restore" mean something: entered with $118 already holding the handler's own
    address, a reconstruction that never wrote it back would be indistinguishable.
    """
    glue = (lambda lib, buf: lib.g_acia_joy0_byte(buf)) if state == A_joy0_state \
        else (lambda lib, buf: lib.g_acia_joy1_byte(buf))
    abi.run_case(entry, glue, pokes={VECTOR_ACIA: entry_vector.to_bytes(4, "big"), state: b"\x5a"},
                 stop_pc=stop, hw_seed={HW_ACIA_DATA: received},
                 note=f"received={received:#04x} at {entry:#x}")


# =================================================================================================
# tos_joyvec_handler @ 0x141fa — dead on the machine, and an ordinary callback here
# =================================================================================================


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_tos_joyvec_copies_the_packets_two_state_bytes(chunk):
    """Bytes 1 and 2 of TOS's three-byte report into the two stick states, sharded.

    Byte 0 is the report's own header and the callback ignores it, so the packets here carry a
    random one: a reconstruction that read the packet one byte early would take it and differ.
    """
    rng = random.Random(0x30ec + chunk)
    for _ in range(16):
        packet = bytes(rng.randrange(0x100) for _ in range(JOY_PACKET_BYTES))
        pokes = {JOY_PACKET: packet,
                 A_joy0_state: bytes([rng.randrange(0x100), rng.randrange(0x100)])}
        abi.run_case(ENTRY_TOS_JOYVEC_HANDLER,
                     lambda lib, buf: lib.g_tos_joyvec_handler(buf, JOY_PACKET),
                     pokes=pokes, regs={"a0": JOY_PACKET}, note=f"packet={packet.hex()}")


def test_tos_joyvec_attribution():
    """Poison the two state bytes: a candidate that wrote neither would stay canary."""
    abi.run_case(ENTRY_TOS_JOYVEC_HANDLER,
                 lambda lib, buf: lib.g_tos_joyvec_handler(buf, JOY_PACKET),
                 pokes={JOY_PACKET: bytes([0x00, 0x0f, 0xf0])}, regs={"a0": JOY_PACKET},
                 poison=True)


# =================================================================================================
# the addresses and constants this battery names
# =================================================================================================

MIRROR_HEADER = "include/irq.h"
MIRRORS = (
    "VECTOR_ACIA", "FN_ACIA_IKBD_ISR", "FN_ACIA_JOY0_BYTE", "FN_ACIA_JOY1_BYTE",
    "MFP_ISRB", "MFP_ISRB_ACIA_BIT",
    "IKBD_JOY0_PACKET_HEADER", "IKBD_JOY1_PACKET_HEADER",
    "A_key_watch_scancodes", "KEY_WATCH_SCANCODES", "SCANCODE_BREAK_BIT",
    "IKBD_JOY_PACKET_JOY0", "IKBD_JOY_PACKET_JOY1",
    "A_vbl_tick",
    "A_joy0_state", "A_joy1_state", "A_key_bits", "A_key_last_scancode",
    ("A_sound_module", "include/globals.h", "A_sound_module"),
    ("SND_MUSIC_ACTIVE", "include/sound.h", "SND_MUSIC_ACTIVE"),
    ("SND_CHANNEL_A", "include/sound.h", "SND_CHANNEL_A"),
    ("SND_CHANNELS", "include/sound.h", "SND_CHANNELS"),
    ("SND_CHANNEL_STRIDE", "include/sound.h", "SND_CHANNEL_STRIDE"),
    ("SCC_TRUE", "include/common.h", "SCC_TRUE"),
    ("SND_ENTRY_MUSIC_START", "include/sound.h", "SND_ENTRY_MUSIC_START"),
    ("SHIFTER_SYNC_50HZ", "include/sound.h", "SHIFTER_SYNC_50HZ"),
)

# Eight bytes or more each, so a prologue names one routine rather than a family: the two
# continuations differ only in the address of their third instruction, and the four `rte`s need the
# instruction AFTER them to be separable at all.
ENTRY_PROLOGUES = {
    # movem.l #$fffe,-(a7) / addq.l #1,$17720
    "ENTRY_VBL_HANDLER": "48e7fffe52b900017720",
    # move.l d1,-(a7) / move.b $fffffc02,d1 / cmpi.b #$fe,d1
    "ENTRY_ACIA_IKBD_ISR": "2f011239fffffc020c0100fe",
    # move.l d1,-(a7) / move.b $fffffc02,d1 / move.b d1,$1777e
    "ENTRY_ACIA_JOY0_BYTE": "2f011239fffffc0213c10001777e",
    # ...and $1777f, which is the only byte between the two routines
    "ENTRY_ACIA_JOY1_BYTE": "2f011239fffffc0213c10001777f",
    # movem.l #$00c0,-(a7) / lea $1777e(pc),a1 -- the address it loads and never uses
    "ENTRY_TOS_JOYVEC_HANDLER": "48e700c043fa357e",
}

STOP_PROLOGUES = {
    # jmp $1164e.l -- the chain, with the shipped self-loop still in its operand
    "STOP_VBL_CHAIN": "4ef90001164e",
    # rte, then the `cmpi.b #$ff,d1` of the arm it branched over
    "STOP_ACIA_ISR_JOY0_HEADER": "4e730c0100ff6616",
    # rte, then the key path's `movem.l #$80c0,-(a7)`
    "STOP_ACIA_ISR_JOY1_HEADER": "4e7348e780c041f9",
    # rte, then the first rung of the BREAK ladder
    "STOP_ACIA_ISR_KEY_MAKE": "4e73b21866020191",
    # rte, then acia_joy0_byte's own prologue
    "STOP_ACIA_ISR_KEY_BREAK": "4e732f011239fffffc02",
    "STOP_ACIA_JOY0_RTE": "4e732f011239fffffc02",
    # rte, then read_player_input's `tst.w $1770e`
    "STOP_ACIA_JOY1_RTE": "4e734a790001770e670a",
}
