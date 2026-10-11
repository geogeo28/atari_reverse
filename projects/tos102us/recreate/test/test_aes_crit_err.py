"""crit_err `$fe3cbe` (`src/aes/gemdosif.S`; its C twin in `gemdosif.c`): THE CRITICAL-ERROR HANDLER GEM INSTALLS — what
the BIOS's disk driver calls through etv_critic with `(error.w, drive.w)` when an access fails.

    crit_err(error, drive):
        spl7;  $8c42 = SP;  SP = $9446;  splx;  movem.l d3-d7/a3-a6,-(sp)        (a stack of its own, 2,048 bytes)
        row   = error == 0 ? 0 : (~error > 17 ? 0 : ~error)                      (SIGNED: a positive error's is < 0)
        alert = (error == 0 ? 0 : ~error) with its LOW BYTE := table[row]         ($fef790, eighteen bytes)
        D0 = eralert(alert, drive)
        D0 = D0.w == 0 ? (long)error : $10000                                      (the error stands, or RETRY)
        movem.l (sp)+,...;  SP = $8c42

IT SHIPS AS THE ROM'S INSTRUCTIONS AND HAS NO ROW OF THE TRANSCRIPTION RELATION: that relation compares everything and
drops nothing, and under crit_err the alert is eralert — Alcyon's code in the ROM, the build's C in a build: frames
of two compilers on crit_err's own stack, the Line-F handler's mask word, the registers a callee may keep. So it is
held here, four ways:

  * ITS OWN INSTRUCTIONS, EXACTLY (`served`): the ROM's routine and each blob's `.S` over one machine and one
    register file, WITH THE ALERT SERVED AT ITS ENTRY ON BOTH SHORES — a watch stops each run where eralert is
    entered (`$fe768c`; the `.S`'s thunk), reads the two words it was handed and the stack they lie on, and returns
    a scripted answer. Then nothing differs by nature but one longword: the return address the `jsr` pushed on
    crit_err's stack, a site of its own text — held to be exactly that site, on each shore. The whole image, the
    whole register file and THE CYCLES are equal. A LABELLED ARGUMENT CLASS: the driver's frame, staged.
  * THE WHOLE HANDLER THROUGH THE REAL ALERT (`through_the_alert`): the same pair of runs with nothing served, Return
    typed ahead — the alert drawn, run by fm_do and put back, on crit_err's stack — the answer, the registers
    crit_err keeps and the image, less what the two compilers' frames and the Line-F handler make differ, by name.
  * THE C TWIN (Tier 1): its table step against the ROM's own (the alert the ROM hands eralert, read at the served
    stop) over every class of error; and the twin whole, in a child — eralert's own door calls and image, and the
    answer crit_err makes of eralert's.
  * WHO ENTERS IT: etv_critic, which a build's retake and takeerr point at this entry
    (`test_aes_gemdosif_transcription.py`).

WHAT IS NOT HELD: A REAL ARRIVAL. No boot reaches crit_err (no floppy access comes after takeerr), and the device
model that would answer the driver's own call with a drive error is not built (band 5 wave 3, slice M / ruling W3-R7).
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, bench_tier3, emu, make_image
from recreate_kit import harness as kit_harness
from recreate_kit import rom_bench

import aes
import aes_event
import case
import test_aes_fmalert as alerts
import test_aes_gsx_transcription as frames
import transcription
import vdi
import vdi_helpers
from case import merge_pokes

CRIT_ERR, ERALERT = "AES_ROM_CRIT_ERR", alerts.ERALERT
aes.declare_alcyon(CRIT_ERR, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.WORD_ARG))
GEMDOSIF = aes.header_constants("gemdosif.h")
RETRY = aes.words_long(GEMDOSIF["CRIT_ERR_RETRY_HIGH_WORD"])            # 1 in D0's high word: $10000
ROWS, LAST_ROW = GEMDOSIF["CRIT_ERR_ALERT_ROWS"], GEMDOSIF["CRIT_ERR_LAST_ROW"]
SAVED_SP, STACK_LO, STACK_TOP = (GEMDOSIF[name] for name in ("AES_CRIT_ERR_SAVED_SP", "AES_CRIT_ERR_STACK",
                                                             "AES_CRIT_ERR_STACK_TOP"))
TABLE = addrs.AES_ROM_CRIT_ERR_ALERTS
S_ENTRY = transcription.transcription_symbol(CRIT_ERR)
THUNK = "gemdosif_to_aes_eralert"
ARGUMENT_CLASS = "ARGUMENT CLASS (the driver's frame staged: no access failed)"
WORD_MASK, LONG_MASK = aes.WORD_MASK, aes.LONG_MASK
# crit_err's own frame on its stack where eralert is entered: the nine registers, the error kept, eralert's two
# words and the `jsr`'s return address ($fe3cde movem; $fe3ce8; $fe3d04, $fe3d06; $fe3d08).
SAVED_REGISTERS = ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6")
FRAME_BYTES = len(SAVED_REGISTERS) * aes.LONG_BYTES + 3 * aes.WORD_BYTES + aes.LONG_BYTES
SP_AT_ERALERT = STACK_TOP - FRAME_BYTES
RETURN_SITE = 0xFE3D0E                  # the instruction after crit_err's `jsr eralert`
A_DRIVE = 1
# What lies between the run's stack top and the SP crit_err is entered with — and parks: the frame caller's one
# pushed longword (the driver's two words) and its `jsr`'s return address.
THE_CALLER_S_PUSHES = 2 * aes.LONG_BYTES
ALERT_INSNS = 600_000                   # an alert drawn, run and put back: past `emu.run`'s default (measured: 161,000)


# ---- the model of what the ROM does with an error, read off its instructions ----------------------------------------------
def signed_word(value):
    return aes.signed(value & WORD_MASK)


def row_of(error):
    """The table's row for `error` — which may be NEGATIVE (a positive error): below the table."""
    if signed_word(error) == 0:
        return 0
    indexed_by = signed_word(~error)
    return 0 if indexed_by > LAST_ROW else indexed_by


def alert_of(error, byte_at):
    """The word eralert is handed: `byte_at(row)` over the low byte of `~error` (of the error itself where it is 0)."""
    indexed_by = 0 if signed_word(error) == 0 else ~error & WORD_MASK
    return indexed_by & 0xFF00 | byte_at(row_of(error))


def rom_byte(row):
    return BASE_IMAGE[TABLE + row]


def answer_of(error, eralert_s):
    """crit_err's D0: the error sign-extended where eralert's WORD is 0, RETRY otherwise."""
    return RETRY if eralert_s & WORD_MASK else signed_word(error) & LONG_MASK


# ---- the two shores, entered alike ------------------------------------------------------------------------------------------
def staged(error, drive, machine):
    """`machine` with the driver's frame — `(error.w, drive.w)` over the return address — where the frame caller
    pushes it from, and that caller; the ROM's entry where the original's run finds its routine."""
    caller, pokes = frames.entered(CRIT_ERR, (error, drive), machine)
    return caller, transcription.transcription_pokes(CRIT_ERR, pokes, caller)


class Served:
    """THE ALERT SERVED AT ITS ENTRY: a watch stopped where eralert is entered (`at`) that notes the two words it was
    handed, the SP and the return address, and returns `answer` in D0 — eralert's `rts`, no instruction of it run."""

    def __init__(self, at, answer):
        self.first, self.answer, self.calls = frozenset({at}), answer, []

    def stopped(self, _pc, sp, memory):
        returns_to = case.long_in(memory, sp)
        self.calls.append((case.word_in(memory, sp + aes.LONG_BYTES), case.word_in(memory, sp + aes.LONG_BYTES + aes.WORD_BYTES),
                           sp, returns_to))
        emu.bench_door_return(self.answer, returns_to, sp + aes.LONG_BYTES)
        return self.first


def the_rom_s(caller, pokes, watch=None, budget=ALERT_INSNS):
    """The ROM's crit_err over `pokes`: `(image, registers)` — a bench run of the original, entered as `emu.run`
    enters it, under `transcription.DIRTY`."""
    image = bytearray(make_image(pokes))
    if watch is None:
        final, _writes, regs = emu.run(image, caller.at, dict(transcription.DIRTY), max_insns=budget)
        return final, regs
    _image, _writes, regs = rom_bench.watched_original(image, caller.at, watch, dict(transcription.DIRTY))
    rom_bench.vet_the_run_just_made("the ROM's crit_err, its alert served")
    return image, regs


def ours(blob, caller, pokes, watch=None):
    """The blob's `.S` over the same `pokes`, entered at the same caller with the same register file: the kit's own
    run, nothing mapped and nothing compared."""
    seed = [transcription.DIRTY[name] for name in emu.REPORTED_REGS]
    return rom_bench.RomBench._call(blob, bytearray(make_image(pokes)), S_ENTRY, args=(blob.entry(S_ENTRY),),
                                    entry_at=caller.at, seed_regs=seed, watch=watch)


def differing(the_rom_s_image, our_image, blob, dropped=()):
    """Every compared address at which the two images differ: the kit's spans (the image less the run's stack band),
    less the blob's own span and the windows `dropped` names."""
    spans = []
    for lo, hi in kit_harness.diff_spans():
        spans += [(lo, min(hi, blob.base)), (max(lo, blob.end), hi)] if lo < blob.end and blob.base < hi else [(lo, hi)]
    return kit_harness.differing_addresses(
        memoryview(bytes(the_rom_s_image)), memoryview(bytes(our_image)), [(lo, hi) for lo, hi in spans if lo < hi],
        lambda address: any(lo <= address < hi for lo, hi, _why in dropped))


def registers(regs):
    return {name: regs[name] for name in emu.REPORTED_REGS}


# ---- 1. ITS OWN INSTRUCTIONS, EXACTLY: the alert served on both shores -------------------------------------------------------
# EVERY CLASS OF ERROR the instructions tell apart: the eighteen the table has a row for (-1 .. -18); none (0); past
# the last row with a clear high byte (-19, -256); the high byte kept (-257, -300, the least word); and — apart,
# below — the positive ones.
MAPPED = tuple(range(-1, -ROWS - 1, -1))
NEGATIVE_ERRORS = (*MAPPED, 0, -19, -256, -257, -300, -0x8000)
POSITIVE_ERRORS = (1, 2, 0x7FFF)
# How far below its table a build certainly still reads ITS OWN text: this file's pinned region ($fe3c3e..$fe3db3)
# lies right under it. Further down is whatever the link put there — or, on the smaller blob, the machine's RAM.
SMALLEST_TEXT_BELOW_THE_TABLE = addrs.AES_ROM_LMUL - addrs.AES_ROM_GEM_DOS_TRAP
# What the served alert answers: its first button (the error stands), another, and two longs whose WORD decides.
ERALERT_ANSWERS = {"the first button": 0, "another": 1, "a long whose word is 0": 0x7FFF_0000, "a negative word": 0xFFFF}
THE_RETURN_SITE = (SP_AT_ERALERT, SP_AT_ERALERT + aes.LONG_BYTES,
                   "the return address crit_err's `jsr eralert` pushed on its own stack: a site of its own text")


def served(blob, error, drive, answer):
    """One case on both shores, the alert served: `((the ROM's image, registers, watch), (ours...))`."""
    caller, pokes = staged(error, drive, alerts.running())
    the_rom_s_watch, our_watch = Served(addrs.AES_ROM_ERALERT, answer), Served(blob.entry(THUNK), answer)
    rom_image, rom_regs = the_rom_s(caller, pokes, the_rom_s_watch)
    our_run = ours(blob, caller, pokes, our_watch)
    return (rom_image, rom_regs, the_rom_s_watch), (our_run.image, {**our_run.regs, "ninsns": our_run.insns,
                                                                    "cycles": our_run.cycles}, our_watch)


def held_exactly(blob, error, drive, answer):
    """THE RELATION: one call of eralert on each shore, the same two words on the same stack; the image equal but
    for the one return site, which is each shore's own; the WHOLE register file; the instructions and the cycles."""
    (rom_image, rom_regs, rom_watch), (our_image, our_regs, our_watch) = served(blob, error, drive, answer)
    (rom_alert, rom_drive, rom_sp, rom_site), = rom_watch.calls
    (our_alert, our_drive, our_sp, our_site), = our_watch.calls
    assert (our_alert, our_drive, our_sp) == (rom_alert, rom_drive, rom_sp) and rom_sp == SP_AT_ERALERT
    assert rom_site == RETURN_SITE and our_site == blob.entry(S_ENTRY) + RETURN_SITE - addrs.AES_ROM_CRIT_ERR
    assert differing(rom_image, our_image, blob, (THE_RETURN_SITE,)) == []
    assert registers(our_regs) == registers(rom_regs)
    assert (our_regs["ninsns"], our_regs["cycles"]) == (rom_regs["ninsns"], rom_regs["cycles"]), "the same instructions"
    return rom_alert, rom_image, rom_regs


@pytest.mark.parametrize("answered", ERALERT_ANSWERS)
@pytest.mark.parametrize("error", NEGATIVE_ERRORS)
def test_the_transcription_is_the_rom_s_handler_with_the_alert_served(error, answered, blob):
    """...and WHAT BOTH DO is what the instructions say: the alert the table's row gives, laid over the low byte of
    `~error`; the drive handed on; D0 = D1 the error or RETRY by the answer's word; D3-D7/A3-A6 as found; the
    caller's SP parked and come back to."""
    answer = ERALERT_ANSWERS[answered]
    alert, image, regs = held_exactly(blob, error, A_DRIVE, answer)
    assert alert == alert_of(error, rom_byte)
    assert regs["d0"] == regs["d1"] == answer_of(error, answer)
    assert all(regs[name] == transcription.DIRTY[name] for name in SAVED_REGISTERS)
    assert case.long_in(image, SAVED_SP) == emu.STACK_TOP - THE_CALLER_S_PUSHES


@pytest.mark.parametrize("drive", (0, 1, 15, 0x1234, -1), ids=("A:", "B:", "P:", "a word with a high byte", "-1"))
def test_the_drive_s_word_is_handed_on_as_it_came(drive, blob):
    held_exactly(blob, -1, drive, 0)
    caller, pokes = staged(-1, drive, alerts.running())
    watch = Served(addrs.AES_ROM_ERALERT, 0)
    the_rom_s(caller, pokes, watch)
    assert watch.calls[0][1] == drive & WORD_MASK


def test_the_registers_it_keeps_are_saved_on_its_own_stack_in_movem_s_order(blob):
    """`movem.l d3-d7/a3-a6,-(sp)` from the stack's top: read off both shores' stacks where the run ends (dead, and
    compared: the image is equal) — D3 lowest, A6 highest."""
    _alert, image, _regs = held_exactly(blob, -1, A_DRIVE, 0)
    saved = struct.unpack(f">{len(SAVED_REGISTERS)}I", bytes(image[STACK_TOP - len(SAVED_REGISTERS) * aes.LONG_BYTES:STACK_TOP]))
    assert saved == tuple(transcription.DIRTY[name] for name in SAVED_REGISTERS)
    kept_error = STACK_TOP - len(SAVED_REGISTERS) * aes.LONG_BYTES - aes.WORD_BYTES
    assert case.word_in(image, kept_error) == -1 & WORD_MASK, "the error, kept under them for the answer"


def test_the_table_is_what_the_names_say():
    """The eighteen rows, read off the ROM: every one an alert eralert has (0..6), and what the classes above rest on —
    row 0 is the alert of no error and of an error past the table."""
    table = bytes(BASE_IMAGE[TABLE:TABLE + ROWS])
    assert len(table) == ROWS == LAST_ROW + 1 and set(table) <= set(range(alerts.ERALERT_ERRORS))
    assert [alert_of(error, rom_byte) for error in (0, -19, -256)] == 3 * [table[0]]
    assert alert_of(-257, rom_byte) == 0x0100 | table[0], "the high byte of ~error is kept: eralert is handed $01xx"


# ---- A POSITIVE ERROR READS BELOW THE TABLE: the ROM's own bytes there, and — a NAMED DIVERGENCE — ours ----------------------
@pytest.mark.parametrize("error", POSITIVE_ERRORS)
def test_a_positive_error_indexes_below_the_table_on_both_shores__each_its_own_bytes(error, blob):
    """THE ROM'S BEHAVIOUR (never fixed): `~error` is negative, passes the SIGNED `ble`, and the row is read BELOW the
    table — in the ROM the bytes of whatever precedes `$fef790` (another table's longwords; for a large error, AES
    text). THE `.S` DOES THE SAME THING OVER ITS OWN LAYOUT: the table is laid behind this file's text, so the byte
    it reads is one of the build's own code. EVERYTHING ELSE IS EQUAL — the stack, the registers, the cycles — and the
    one word that differs is held to be exactly that byte on each shore. No caller hands a positive error: the BIOS's
    are negative, and the desk's one call (`$fee378`) is behind a `bge`."""
    (rom_image, rom_regs, rom_watch), (our_image, our_regs, our_watch) = served(blob, error, A_DRIVE, 0)
    row = row_of(error)
    assert row < 0
    our_table = blob.entry(transcription.transcription_symbol("AES_ROM_CRIT_ERR_ALERTS"))
    assert rom_watch.calls[0][0] == alert_of(error, rom_byte)
    assert our_watch.calls[0][0] == alert_of(error, lambda below: our_image[our_table + below])
    if -row <= SMALLEST_TEXT_BELOW_THE_TABLE:
        assert blob.base <= our_table + row < our_table, "the byte ours reads is the build's own code"
    the_alert_handed = (SP_AT_ERALERT + aes.LONG_BYTES, SP_AT_ERALERT + aes.LONG_BYTES + aes.WORD_BYTES,
                        "the alert's word on crit_err's stack: its low byte read below each shore's own table")
    assert differing(rom_image, our_image, blob, (THE_RETURN_SITE, the_alert_handed)) == []
    assert registers(our_regs) == registers(rom_regs) and our_regs["cycles"] == rom_regs["cycles"]


# ---- 2. THE WHOLE HANDLER THROUGH THE REAL ALERT ---------------------------------------------------------------------------
# Return typed ahead answers the alert's DEFAULT button: the first for the alert of error -17 (the error stands), the
# second — Retry — for every other row's (`alerts.eralert_level`).
THROUGH_THE_ALERT = {"the alert's first button the default: the error stands": -17,
                     "Retry the default": -1,
                     "Retry the default, the alert naming its drive": -2,
                     "no error at all: the table's row 0": 0}
BY_NATURE = (
    (STACK_LO, SP_AT_ERALERT + aes.LONG_BYTES, "crit_err's own stack under its frame: eralert's frames — Alcyon's in the "
                                               "ROM, GCC's in a build — and the return site above them"),
    *aes.LINE_F_MASK_WINDOW,
)
# The registers the GCC ABI lets eralert's C keep or leave as it likes, and Alcyon's code leaves its own way.
ERALERT_S_OWN = ("d2", "a0", "a1", "a2")


def before_the_alert(error):
    """The driver's frame for `error` on A_DRIVE over the alert's machine, Return typed ahead: `(caller, pokes)`."""
    return staged(error, A_DRIVE, merge_pokes(alerts.answered(alerts.RETURN), aes_event.savptr_in_the_band()))


def through_the_alert(blob, error):
    caller, pokes = before_the_alert(error)
    return the_rom_s(caller, pokes), ours(blob, caller, pokes)


@pytest.mark.parametrize("label", THROUGH_THE_ALERT)
def test_the_handler_shows_the_alert_and_answers_as_the_rom_s(label, blob):
    """BOTH SHORES RUN THE ALERT FOR REAL — the blob's through the thunk into `aes_eralert`, on crit_err's own stack:
    the answer in D0 and D1; every register crit_err keeps; the caller's SP come back to; and THE IMAGE — the alert's
    tree, the screen put back, the keyboard's ring, the event layer's globals — equal outside what the two compilers'
    frames and the ROM's Line-F handler make differ, each by name."""
    error = THROUGH_THE_ALERT[label]
    (rom_image, rom_regs), our_run = through_the_alert(blob, error)
    first_button_default = alerts.eralert_level(alert_of(error, rom_byte)) == 1
    assert rom_regs["d0"] == rom_regs["d1"] == answer_of(error, 0 if first_button_default else 1)
    # ...our image with the code addresses of the build given the ROM's names, as Tier 3 gives them (the relocation
    # registry: the alert's Return is a fork our interrupt code queued — a fork function's address in the queue).
    tier3 = bench_tier3()
    our_image = tier3._mapped_back(bytearray(our_run.image), tier3.code_relocations(blob.elf, S_ENTRY))
    assert differing(rom_image, our_image, blob, BY_NATURE) == []
    compared = [name for name in emu.REPORTED_REGS if name not in ERALERT_S_OWN]
    assert {name: our_run.regs[name] for name in compared} == {name: rom_regs[name] for name in compared}
    assert all(rom_regs[name] == transcription.DIRTY[name] for name in SAVED_REGISTERS)


def lowest_store_on_its_stack(writes):
    return min(at for at in writes if STACK_LO <= at < STACK_TOP)


def test_the_alert_runs_inside_crit_err_s_stack_on_both_shores_with_room_for_more_than_it_uses(blob):
    """A MEASURED DEPTH, NOT A BOUND (a bound is the stack reading's to give): the lowest byte each shore stores on
    the 2,048-byte stack while the alert of error -1 runs. The ROM's Alcyon frames reach 716 bytes down, a build's
    840 to 850 (2026-10-11; the numbers are the compiler's and the layout's, so what is asserted is the margin: each
    shore leaves more of the stack unused than it uses)."""
    caller, pokes = before_the_alert(-1)
    _final, writes, _regs = emu.run(make_image(pokes), caller.at, dict(transcription.DIRTY), max_insns=ALERT_INSNS)
    ours_stored, _truncated = emu.bench_writes(ours(blob, caller, pokes).image)
    for stored in (writes, ours_stored):
        used = STACK_TOP - lowest_store_on_its_stack(stored)
        assert FRAME_BYTES < used < (STACK_TOP - STACK_LO) // 2, f"{used} bytes of crit_err's stack used"


# ---- 3. THE C TWIN -----------------------------------------------------------------------------------------------------------
_lib.aes_crit_err_alert.restype = ctypes.c_int16
_lib.aes_crit_err_alert.argtypes = (ctypes.c_void_p, ctypes.c_int16)


def the_rom_s_alert(error):
    """The word the ROM's crit_err hands eralert for `error`: read where eralert is entered, the alert served."""
    caller, pokes = staged(error, 0, alerts.running())
    watch = Served(addrs.AES_ROM_ERALERT, 0)
    the_rom_s(caller, pokes, watch)
    return watch.calls[0][0]


TWIN_S_ERRORS = (*NEGATIVE_ERRORS, *POSITIVE_ERRORS, 17, 18, 0x0100, 0x00FF, -0x7FFF)


@pytest.mark.parametrize("error", TWIN_S_ERRORS)
def test_the_twin_s_table_step_is_the_rom_s(error):
    """TIER 1, the table: the C's alert for `error` against the word the ROM's own crit_err hands eralert — every
    class, the positive ones too (the host reads the ROM's bytes below the table, in place)."""
    image = kit_harness.candidate_image(make_image({}))
    assert _lib.aes_crit_err_alert(image, error) & WORD_MASK == the_rom_s_alert(error) == alert_of(error, rom_byte)


NOT_HELD_BY_THE_ROM_S_RUN = aes_event.HeldElsewhere(
    "the twin's door calls are eralert's own, made with the alert and the drive this test holds: eralert's battery "
    "holds them to the ROM's (`test_aes_fmalert.py`); the ROM's crit_err makes them from another stack")


def in_a_child(name, values):
    """The C core `name` over the alert's machine, Return typed ahead, in a child: `(its answer, the image it left)`."""
    returncode, stderr, image = aes_event.door_child(name, values, alerts.answered(alerts.RETURN), objects=True,
                                                     answered=True, door_calls=NOT_HELD_BY_THE_ROM_S_RUN)
    assert returncode == 0, stderr
    return vdi_helpers.answer_in(stderr), image


def names_its_drive(alert):
    return bool(alerts.eralert_entry("AES_ERALERT_LEVELS", alert) & alerts.FM["ERALERT_NAMES_DRIVE"])


@pytest.mark.parametrize("label", THROUGH_THE_ALERT)
def test_the_twin_is_eralert_over_the_table_s_alert_and_answers_the_rom_s_answer(label):
    """TIER 1, the twin whole, BY COMPOSITION — the door's own differential cannot hold it (it compares the image at
    every door call, and the ROM's frames there lie on crit_err's stack, the host's in its slots). So: the twin, in a
    child, leaves THE VERY IMAGE the C eralert leaves for the alert the table gives and the drive it was handed
    (eralert's own battery holds that C to the ROM) — an image the drive shows in, where the alert names it — and its
    answer is the ROM's own crit_err's D0 for the same error."""
    error = THROUGH_THE_ALERT[label]
    alert = alert_of(error, rom_byte)
    twin_s, twin_image = in_a_child(CRIT_ERR, (error, A_DRIVE))
    eralert_s, eralert_image = in_a_child(ERALERT, (alert, A_DRIVE))
    assert bytes(twin_image) == bytes(eralert_image), "the twin stores nothing of its own"
    if names_its_drive(alert):
        _answer, on_another_drive = in_a_child(ERALERT, (alert, A_DRIVE + 1))
        assert bytes(on_another_drive) != bytes(eralert_image), "the drive handed on is in the alert shown"
    _rom_image, rom_regs = the_rom_s(*before_the_alert(error))
    assert twin_s & LONG_MASK == answer_of(error, eralert_s) == rom_regs["d0"]


def test_the_alerts_run_for_real_include_one_that_names_its_drive_and_both_default_buttons():
    """WHAT THE CASES ABOVE REST ON, read off the ROM's two tables: an alert whose text names the drive (so the
    drive's word is seen), one whose first button is the default (the error stands) and one whose second is."""
    run = [alert_of(error, rom_byte) for error in THROUGH_THE_ALERT.values()]
    assert any(map(names_its_drive, run)) and {alerts.eralert_level(alert) for alert in run} == {1, 2}


# ---- 4. WHO ELSE ENTERS IT -----------------------------------------------------------------------------------------------
THE_DESK_S_CALL = 0xFEE378              # the one Line-F call of crit_err in the GEM text: a desk utility's (band 6)
ITS_TEST, ITS_BRANCH_ROUND_THE_CALL = 0xFEE36E, 0xFEE372
TST_W_8_A6, BGE_S = 0x4A6E_0008, 0x6C


def test_its_one_line_f_caller_is_the_desk_s_and_hands_it_a_negative_error_alone():
    """BESIDE THE VECTOR, ONE CALL: the desk's at `$fee378` — reached only where the word it hands on is negative
    (`tst.w 8(a6)` / `bge` round the call), as the BIOS's driver calls etv_critic only for a negative answer. So no
    caller hands crit_err a positive error. BAND 6's: the day that routine is C its call of `aes_crit_err` reaches the
    `.S` through a generated thunk, and the pair is `transcription.C_CALLERS_OF_TRANSCRIBED_CORES`'s — none yet."""
    assert [at for sites in aes.line_f_call_sites(CRIT_ERR).values() for at in sites] == [THE_DESK_S_CALL]
    assert case.long_in(BASE_IMAGE, ITS_TEST) == TST_W_8_A6 and BASE_IMAGE[ITS_BRANCH_ROUND_THE_CALL] == BGE_S
    branches_to = ITS_BRANCH_ROUND_THE_CALL + aes.WORD_BYTES + BASE_IMAGE[ITS_BRANCH_ROUND_THE_CALL + 1]
    assert ITS_BRANCH_ROUND_THE_CALL < THE_DESK_S_CALL < branches_to
    assert not [caller for caller, core in transcription.C_CALLERS_OF_TRANSCRIBED_CORES if core == "aes_crit_err"]
