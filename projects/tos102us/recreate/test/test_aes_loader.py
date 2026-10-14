r"""THE ACCESSORY LOADER (`src/aes/loader.c`): sndcli `$fe42e8`, ldaccs `$fe4394`, free_accs `$fe4476` and cre_aproc
`$fe44d4` — each held to the ROM AT ITS ARRIVAL in the ROM's own boot, GEMDOS replayed from the ROM's own run
(`aes_loader.py` says how, and why not through the kit's differential).

    sndcli(name, count):  strcpy(name, the shell's line); handle = dos_open(the shell's buffer, 0)  -> failed: 0
                          count != 0: cre_aproc()                                                    -> refused: 0
                          pgmld(handle, the shell's line, &basepage); dos_close(handle)              -> -1: 0
                          count == 0 ? $9724 = basepage : $9bc4[$c682] = basepage
                          pstart(gotopgm, name, basepage); 1
    ldaccs():             $c682 = 0; cartridge accessories; no drive, or $8992 clear: done
                          drive = dos_gdrv(); dta = dos_alloc(50); dos_sdta(dta); C: in the drive map: dos_sdrv(C:)
                          dos_chdir("\"); dos_sfirst("\*.ACC") — not found: dos_sdrv(drive)
                          dos_chdir("\"); found = dos_sfirst("\*.ACC")
                          six passes at most, six started at most, while found:
                              sndcli(dta + 30, started) -> started++;  found = dos_snext()
                          dos_free(dta)
    free_accs():          $9724: dos_free(its environment), dos_free(it)
                          each of $c682: dos_free($9bc4[i]'s environment), dos_free($9bc4[i]), dos_free($c6b2[i])
    cre_aproc():          block = dos_alloc(2226) -> 0: 0;  $c6b2[$c682] = block; pinit(block, block + 2050)
                          its UDA block + 184, the stack pointer it saves that + 1862; five EVBs from block + 2086
                          pushed on the free list; 1

THE MACHINES. The accessory capture's boot (two test accessories on the disk: the first runs in the spare static PD,
the second in an allocated one) reaches sndcli twice, cre_aproc once and ldaccs once; the desk capture's reaches
ldaccs over a disk with no accessory; the seven-accessory capture's, ldaccs over one file more than it takes and
sndcli's third call (the allocated count 1). A BROKEN ACCESSORY IS A PATCH OF ITS OWN CLUSTER ON THE DISK — the program
header's magic, or its BSS length — which nothing reads before `gem_entry`, so the disk is still the disk the capture
booted with: the second's magic wrong (the load fails after its descriptor was allocated: BEHAVIOUR (b)), the first's
(the count stays 0), and the first's BSS so long that under 2,226 bytes are left (Malloc refuses the second's
descriptor: BEHAVIOUR (a) — the file never closed).

WHAT NO BOOT REACHES, AND HOW IT IS HELD INSTEAD (each a labelled ARGUMENT CLASS):
  * free_accs — called only when gem_main returns (a resolution change), which no machine here does. Run over the
    BOOTED machines at their idle through the kit's differential, GEMDOS's `Mfree` scripted with the answers the
    ROM's own GEMDOS gives for those blocks: the ledger names each block and each return site parked.
  * sndcli's first arm (the open fails): no disk makes a file a search finds and an open misses. Run over the
    snapshot through `aes_shell`'s scripted trap.
  * ldaccs's cartridge arm: no machine has a cartridge (ruling W3-R6); the C halts by name there, in a child.
NOT REACHED AT ALL, said: ldaccs with a drive C: in the map (the device model holds A: alone), Malloc refusing the
DTA, the loop ended by SIX STARTED before six passes (an accessory started before the first pass: a cartridge's).
"""
import functools
import struct
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench

import accessory_disk
import aes
import aes_boot
import aes_event
import aes_fslib as fsl
import aes_gemctrl as gc
import aes_gemdosif as gd
import aes_loader as ld
import aes_pdpipe as pp
import aes_shell as sh
import case
import fs_pexec
import gemdos
import routines
import transcription
import vdi
from case import merge_pokes

SNDCLI, LDACCS, FREE_ACCS, CRE_APROC = ld.SNDCLI, ld.LDACCS, ld.FREE_ACCS, ld.CRE_APROC
LOADER = ld.LOADER
SHELL_LINE = aes.header_constants("geminit.h")["AES_SHELL_LINE"]
FIRST_BASEPAGE, BASEPAGES = LOADER["AES_FIRST_ACC_BASEPAGE"], LOADER["AES_ACC_BASEPAGES"]
PDS, COUNT, STATIC_COUNT = aes.AES_ACCESSORY_PDS, aes.AES_ACCESSORY_COUNT, aes.AES_STATIC_PIDS
BLOCK_BYTES, EVBS, EVB_COUNT = LOADER["ACC_BLOCK_BYTES"], LOADER["ACC_EVBS"], LOADER["ACC_EVB_COUNT"]
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
DGETDRV, DSETDRV, MALLOC, MFREE, FSETDTA, DSETPATH, FSFIRST, FSNEXT, FOPEN, FCLOSE, PEXEC, MSHRINK = (
    addrs.GEMDOS_DGETDRV_FN, addrs.GEMDOS_DSETDRV_FN, addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN,
    addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_DSETPATH_FN, addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FSNEXT_FN,
    addrs.GEMDOS_FOPEN_FN, addrs.GEMDOS_FCLOSE_FN, addrs.GEMDOS_PEXEC_FN, addrs.GEMDOS_MSHRINK_FN)
_GEMDOS_HEADERS = fs_pexec.LOADER_HEADER.parent
_ERRORS = {**fs_pexec.PEXEC_LOAD, **{name: value for header in ("memory.h", "fs.h", "process.h")
                                     for name, value in fs_pexec.addrs.parse(_GEMDOS_HEADERS / header).items()}}
# GEMDOS's answers, as its own headers spell them (unsigned longs there): -66, -40, -39, -36, -33, -49
EPLFMT, EIMBA, ENSMEM, EACCDN, EFILNF, ENMFIL = (aes.signed(_ERRORS[f"GEMDOS_{name}"], 8 * LONG_BYTES)
                                                 for name in ("EPLFMT", "EIMBA", "ENSMEM", "EACCDN", "EFILNF", "ENMFIL"))
PEXEC_LOAD = 3                          # Pexec's mode: load, do not start
GEMDOS_OK = 0
DTA_NAME = addrs.parse(aes.INCLUDE / "gemdos" / "fs.h")["DTA_NAME"]
DRIVE_C_BIT = aes.header_constants("deskleaf.h")["DRIVE_C_BIT"]
SPARE_STATIC_PD = aes.AES_PD_TABLE + 2 * aes.PD_BYTES          # the third static PD: the first accessory's
ALL_THREE = (ld.ROM_FRAMES, ld.HOST_FRAMES, ld.LINE_F_MASK)
NO_MASK = (ld.ROM_FRAMES, ld.HOST_FRAMES)
STATIC_COUNT_STEERS, ACCESSORY_COUNT_STEERS, STACK_STEERS = (ld.STEERS_THE_STATIC_COUNT, ld.STEERS_THE_ACCESSORY_COUNT,
                                                             pp.STEERS_THE_STACK)


# ---- the disks: the capture's own, and a broken accessory's ----------------------------------------------------------------
PRG_MAGIC, PRG_MAGIC_AT, PRG_BSS_AT = fs_pexec.PRG_MAGIC, 0, 10             # a program header's magic word, and its BSS length
NOT_THE_MAGIC = 0x601b
LEFT_UNDER_A_DESCRIPTOR = 1000          # bytes of free memory left behind the first accessory: under cre_aproc's 2,226
CAPTURE_S, SECOND_NO_PROGRAM, FIRST_NO_PROGRAM, NO_ROOM = (
    "the capture's own disk", "the second accessory is no program", "the first accessory is no program",
    "the first accessory leaves no room")
# ...and THE SEVEN-ACCESSORY CAPTURE's (`aes_boot.seven_accessory_preinit`): one more file than the loader takes.
SEVEN, SEVEN_FIRST_NO_PROGRAM = "the seven-accessory capture's own disk", "seven accessories, the first no program"
SEVEN_QUIET = (aes_boot.QUIET,) * len(aes_boot.SEVEN_ACCESSORY_NAMES)


def _patched(index, at, packed, of=None):
    """The capture's disk (or the disk `of`) with `packed` laid at `at` of its `index`-th accessory's FILE — inside
    its program header, so inside its own cluster."""
    disk, start = bytearray(_disk(of or CAPTURE_S)), accessory_disk.file_at(index)
    assert at + len(packed) <= aes_boot.PRG_HEADER_BYTES and case.word_in(disk, start + PRG_MAGIC_AT) == PRG_MAGIC
    disk[start + at:start + at + len(packed)] = packed
    return bytes(disk)


def _kept(ram, basepage):
    """What pgmld shrinks a program's block to: its basepage and its three lengths."""
    return aes_boot.BASEPAGE_BYTES + sum(case.long_in(ram, basepage + at) for at in (
        addrs.BASEPAGE_TLEN, addrs.BASEPAGE_DLEN, addrs.BASEPAGE_BLEN))


@functools.cache
def _disk(which):
    if which == CAPTURE_S:
        return aes_boot.accessory_disk_of(aes_boot.QUIET, aes_boot.QUIET)
    if which == SEVEN:
        return aes_boot.seven_accessory_disk_of(*SEVEN_QUIET)
    if which == SEVEN_FIRST_NO_PROGRAM:
        return _patched(0, PRG_MAGIC_AT, struct.pack(">H", NOT_THE_MAGIC), of=SEVEN)
    if which in (SECOND_NO_PROGRAM, FIRST_NO_PROGRAM):
        return _patched(which == SECOND_NO_PROGRAM, PRG_MAGIC_AT, struct.pack(">H", NOT_THE_MAGIC))
    assert which == NO_ROOM
    # ...a BSS that ends LEFT_UNDER_A_DESCRIPTOR bytes below the top of the block the ROM's own Pexec gave the first
    # accessory: read off the ROM's run over the capture's disk, never typed.
    ram = _returned(FIRST).stood.ram
    basepage = case.long_in(ram, FIRST_BASEPAGE)
    top, bss = case.long_in(ram, basepage + addrs.BASEPAGE_HITPA), case.long_in(ram, basepage + addrs.BASEPAGE_BLEN)
    return _patched(0, PRG_BSS_AT, struct.pack(">I", bss + top - (basepage + _kept(ram, basepage)) - LEFT_UNDER_A_DESCRIPTOR))


# ---- the cases: an arrival, the classes its two shores differ in, the words that steer its second pass ----------------------
Case = namedtuple("Case", "arrival classes steers twice", defaults=((), True))
Case.__doc__ = """One case: how its `arrival` is made, the `classes` its two megabytes differ in, the reasons that
steer its second pass — and whether it has one (`twice`: False for the one run whose write ledger saturates)."""


def _first_sndcli(disk):
    return ld.boot_arrival(SNDCLI, aes_boot.accessory_preinit(), _disk(disk))


def _second_sndcli(disk):
    return ld.next_arrival(SNDCLI, _first_sndcli(disk))


def _ldaccs(disk):
    return ld.boot_arrival(LDACCS, aes_boot.accessory_preinit(), _disk(disk))


def _first_sndcli_of_seven():
    return ld.boot_arrival(SNDCLI, aes_boot.seven_accessory_preinit(), _disk(SEVEN))


def _ldaccs_of_seven(disk):
    return ld.boot_arrival(LDACCS, aes_boot.seven_accessory_preinit(), _disk(disk))


def _with_the_count_pushed(arrived, count):
    """sndcli's arrival with the count word of the frame its caller pushed staged at `count`."""
    return ld.staged(arrived, {arrived.stood.registers["isp"] + COUNT_IN_SNDCLI_S_FRAME: struct.pack(">h", count)})


FIRST, SECOND, ITS_DESCRIPTOR = "sndcli, the first accessory", "sndcli, the second accessory", "cre_aproc, the second accessory's"
TWO_ACCESSORIES, NO_ACCESSORY = "ldaccs, two accessories", "ldaccs, a disk with no accessory"
SECOND_FAILS_TO_LOAD = "sndcli, (b): the second accessory's load fails with its descriptor allocated"
LDACCS_SECOND_FAILS, LDACCS_FIRST_FAILS = "ldaccs, (b): the second is no program", "ldaccs, the first is no program"
DESCRIPTOR_REFUSED = "sndcli, (a): Malloc refuses the second accessory's descriptor"
# THE SEVEN-ACCESSORY CAPTURE's two: the loader's whole run over one file more than it takes — SIX LOADS, whose stores
# saturate the kit's write ledger, so this one case is held ONCE (and held to be the one that cannot be held twice) —
# and the same disk with its first accessory no program: six passes that start nothing, held twice.
SIX_OF_SEVEN = "ldaccs, seven accessories on the disk: six loaded"
SIX_PASSES_NONE_STARTED = "ldaccs, seven accessories, the first no program: six passes"
# ...THE ALLOCATED COUNT AT 1 — where an index by 0 and an index by the count part — IS A BOOT'S OWN STATE since the
# seven-accessory capture: its THIRD call of sndcli arrives with `$c682` = 1 (the first accessory is not counted) and
# loads as any other, its ledger whole — held twice, no word staged. (Until wave 3's review this was the two-accessory
# boot's second call with the count staged at 1: a state a ROM run makes is taken from the ROM run.)
# ...AND TWO ARGUMENT CLASSES, each labelled, each THE ROM'S OWN RUN, IN PLACE, FROM A BOOT'S ARRIVAL WITH ONE WORD STAGED:
#   * ldaccs hands sndcli a count from 0 up, and sndcli tests it against 0 alone — the same call, THE COUNT ITS CALLER
#     PUSHED STAGED AT -1 (a descriptor is allocated: nonzero is all it asks);
#   * the usable-disk word is 1 on every machine (gem_entry's) — ldaccs's arrival over the blank disk, THE WORD STAGED 0.
THIRD_OF_SEVEN = "sndcli, the third accessory of seven: the allocated count 1"
SECOND_WITH_COUNT_MINUS_1 = "ARGUMENT CLASS (the count pushed staged at -1): sndcli, the second accessory"
NO_USABLE_DISK = "ARGUMENT CLASS (the usable-disk word staged 0): ldaccs"
COUNT_IN_SNDCLI_S_FRAME = 2 * LONG_BYTES            # past the return address and the name's pointer
LDACCS_DESCRIPTOR_REFUSED = "ldaccs, (a): no room for the second accessory's descriptor"
CASES = {
    FIRST: Case(lambda: _first_sndcli(CAPTURE_S), ALL_THREE, (STATIC_COUNT_STEERS, STACK_STEERS)),
    SECOND: Case(lambda: _second_sndcli(CAPTURE_S), ALL_THREE, (ACCESSORY_COUNT_STEERS,)),
    ITS_DESCRIPTOR: Case(lambda: ld.next_arrival(CRE_APROC, _second_sndcli(CAPTURE_S)), ALL_THREE),
    TWO_ACCESSORIES: Case(lambda: _ldaccs(CAPTURE_S), ALL_THREE, (STATIC_COUNT_STEERS, STACK_STEERS)),
    NO_ACCESSORY: Case(lambda: ld.boot_arrival(LDACCS, aes_boot.preinit(), aes_boot.blank_disk()), ALL_THREE),
    SECOND_FAILS_TO_LOAD: Case(lambda: _second_sndcli(SECOND_NO_PROGRAM), ALL_THREE),
    LDACCS_SECOND_FAILS: Case(lambda: _ldaccs(SECOND_NO_PROGRAM), ALL_THREE, (STATIC_COUNT_STEERS, STACK_STEERS)),
    LDACCS_FIRST_FAILS: Case(lambda: _ldaccs(FIRST_NO_PROGRAM), ALL_THREE),
    DESCRIPTOR_REFUSED: Case(lambda: _second_sndcli(NO_ROOM), NO_MASK),
    THIRD_OF_SEVEN: Case(lambda: ld.next_arrival(SNDCLI, ld.next_arrival(SNDCLI, _first_sndcli_of_seven())), ALL_THREE,
                         (ACCESSORY_COUNT_STEERS,)),
    SECOND_WITH_COUNT_MINUS_1: Case(lambda: _with_the_count_pushed(_second_sndcli(CAPTURE_S), -1), ALL_THREE,
                                    (ACCESSORY_COUNT_STEERS,)),
    SIX_OF_SEVEN: Case(lambda: _ldaccs_of_seven(SEVEN), ALL_THREE, twice=False),
    SIX_PASSES_NONE_STARTED: Case(lambda: _ldaccs_of_seven(SEVEN_FIRST_NO_PROGRAM), ALL_THREE),
    NO_USABLE_DISK: Case(lambda: ld.staged(ld.boot_arrival(LDACCS, aes_boot.preinit(), aes_boot.blank_disk()),
                                           {LOADER["AES_DISK_USABLE"]: struct.pack(">h", 0)}), ALL_THREE),
    LDACCS_DESCRIPTOR_REFUSED: Case(lambda: _ldaccs(NO_ROOM), ALL_THREE, (STATIC_COUNT_STEERS, STACK_STEERS)),
}
STEERED = [(label, reason) for label, each in CASES.items() for reason in each.steers]
HELD_TWICE = [label for label, each in CASES.items() if each.twice]
HELD_ONCE = [label for label, each in CASES.items() if not each.twice]


@functools.cache
def _arrived(label):
    return CASES[label].arrival()


def _returned(label):
    return ld.returned(_arrived(label))


def _call(function, *fields):
    """A GEMDOS call as a watched run keeps one — `(function, its frame's bytes)` — for fields ('w', value) / ('l', value)."""
    return function, b"".join(struct.pack(">H" if kind == "w" else ">I", value & (aes.WORD_MASK if kind == "w" else aes.LONG_MASK))
                              for kind, value in fields)


def _calls(ran):
    return [(call.function, call.frame) for call in ran.calls]


def _functions(ran):
    return [call.function for call in ran.calls]


def _answers(ran):
    return [aes.signed(call.answer, bits=32) for call in ran.calls]


def _text(ram, at):
    return bytes(ram[at:ram.index(b"\0", at)])


def _process(ram, pd):
    """A PD as pstart leaves one: `(its name, its id, the basepage it was loaded as, where it begins)` — the last the
    PC of psetup's frame on the stack its UDA names."""
    _ldaddr_at, pc_at = aes_boot.entry_slots(ram, pd)
    assert case.word_in(ram, pc_at - WORD_BYTES) == aes_boot.SR_SUPERVISOR, "psetup's frame: a supervisor status word"
    return (bytes(ram[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES]), case.word_in(ram, pd + aes.PD_PID),
            case.long_in(ram, pd + aes.PD_LDADDR), case.long_in(ram, pc_at))


def _woken(ram):
    return aes.list_of(ram, aes.AES_DRL, limit=aes_boot.EVB_CAP)


def test_held_twice_makes_its_second_pass_over_the_machine_with_the_silent_stores_inverted(monkeypatch):
    """THE SECOND PASS IS MADE, AND OVER ANOTHER MACHINE (wave 3's review, B-F7: `held_twice` with its second `held`
    handed the FIRST machine again passed all 124 — and that pass is the only thing that sees a store the C skipped
    where the value is already there, ldaccs's count cleared at 0). `held` is watched, not replaced: called twice,
    the second time over the arrival `silently_stored` makes — a megabyte that differs from the boot's, in bytes the
    ROM's first run stored without changing."""
    each, arrived = CASES[TWO_ACCESSORIES], _arrived(TWO_ACCESSORIES)
    passes, held = [], ld.held

    def watched(over, *named, **kwargs):
        passes.append(over)
        return held(over, *named, **kwargs)
    monkeypatch.setattr(ld, "held", watched)
    rom, _ours = ld.held_twice(arrived, *each.classes, steers=each.steers)
    assert len(passes) == 2 and passes[0] is arrived
    inverted = ld.silently_stored(arrived, rom, each.steers)
    assert passes[1].stood.ram == inverted.stood.ram != arrived.stood.ram
    differing = [at for at in range(len(arrived.stood.ram)) if arrived.stood.ram[at] != inverted.stood.ram[at]]
    silent = {at for start, size in rom.silent for at in range(start, start + size)}
    assert differing and set(differing) <= silent, "the second machine differs from the boot's in silent stores alone"
    assert COUNT in differing, "ldaccs's `clr.w $c682` over a count already 0 is one of them: the store the first pass cannot see"


# ---- EVERY CASE, HELD TWICE ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label", HELD_TWICE)
def test_the_c_is_the_rom_s_from_the_arrival_to_the_return_twice(label):
    """THE DIFFERENTIAL: the C over the arrival's megabyte makes the ROM's GEMDOS calls over the ROM's megabyte at
    each, answers what the ROM answers and leaves the ROM's megabyte, outside the classes the case names (each
    needed) — as the boot made the arrival, and again with every byte the ROM's routine stored without changing it
    inverted."""
    each = CASES[label]
    rom, ours = ld.held_twice(_arrived(label), *each.classes, steers=each.steers)
    assert ours.calls == len(rom.calls) > 0


@pytest.mark.parametrize("label", HELD_ONCE)
def test_the_c_is_the_rom_s_from_the_arrival_to_the_return__once_where_no_second_pass_can_be_made(label):
    """...AND THE ONE RUN THAT LOADS SIX PROGRAMS, held ONCE — the same differential, the arrival as the boot made it —
    because its second pass CANNOT BE MADE, and that is held too: the kit's write ledger saturated (each `Pexec`
    clears the largest free block), so what the routine stored without changing it is not known. (A case named
    here whose ledger did not saturate fails: it owes its second pass.)"""
    each, arrived = CASES[label], _arrived(label)
    assert not each.steers
    rom, ours = ld.held(arrived, *each.classes)
    assert ours.calls == len(rom.calls) > 0 and rom.silent is None
    with pytest.raises(ld.Refused, match="saturated the kit's write ledger"):
        ld.silently_stored(arrived, rom)


@pytest.mark.parametrize("label", HELD_TWICE)
def test_the_second_pass_s_machine_is_another_machine(label):
    """...and that second pass is not the first again: the arrival differs in at least one byte, in none the case's
    reasons name and in none no C stores."""
    each, arrived = CASES[label], _arrived(label)
    second = ld.silently_stored(arrived, _returned(label), each.steers)
    inverted = [at for at in range(ld.RAM_BYTES) if second.stood.ram[at] != arrived.stood.ram[at]]
    kept = [*ld.no_c_stores(arrived.stood), *(span for reason in each.steers for span in reason.spans)]
    assert inverted and not [at for at in inverted if any(lo <= at < hi for lo, hi in kept)]
    assert all(second.stood.ram[at] == arrived.stood.ram[at] ^ aes.BYTE_MASK for at in inverted)


@pytest.mark.parametrize("label, reason", STEERED, ids=[f"{label}: {reason.spans[0][0]:#x}" for label, reason in STEERED])
def test_each_steering_reason_of_a_case_is_needed(label, reason):
    """A WORD LEFT AS IT IS IN THE SECOND PASS IS ONE THAT STEERS — asked of the ROM alone: with that reason's words
    inverted too, its own run from the second pass's machine is refused or goes elsewhere."""
    assert ld.steers_the_rom(_arrived(label), reason, CASES[label].steers)


# ---- sndcli ---------------------------------------------------------------------------------------------------------------------
def _loaded(ran, at):
    """The four calls of a load that succeeds, from `ran`'s call `at` on, and the basepage Pexec answered."""
    handle, basepage = ran.calls[0].answer, ran.calls[at].answer
    return [_call(PEXEC, ("w", PEXEC_LOAD), ("l", SHELL_LINE), ("l", addrs.AES_PGMLD_EMPTY_TAIL), ("l", 0)),
            _call(MSHRINK, ("w", 0), ("l", basepage), ("l", _kept(ran.stood.ram, basepage))),
            _call(FCLOSE, ("w", handle))], basepage


def test_the_first_accessory_is_loaded_into_the_spare_static_pd():
    """THE BOOT'S OWN FIRST CALL, count 0: the name copied to the shell's line and the file opened BY THE SHELL'S
    BUFFER POINTER; no descriptor allocated; the program loaded and shrunk; the file closed; the basepage kept in
    AES_FIRST_ACC_BASEPAGE — the table of the others untouched — and the third static PD made its process: named,
    numbered 2, loaded as that basepage, to begin at gotopgm, woken. 1 answered."""
    arrived, ran = _arrived(FIRST), _returned(FIRST)
    name, count = arrived.arguments
    before, ram = arrived.stood.ram, ran.stood.ram
    assert count == 0 and case.long_in(before, aes.AES_SHELL_BUFFER) == SHELL_LINE
    load, basepage = _loaded(ran, 1)
    assert _calls(ran) == [_call(FOPEN, ("l", SHELL_LINE), ("w", LOADER["SNDCLI_OPEN_MODE"])), *load]
    assert ld.answered(ran) == LOADER["SNDCLI_STARTED"] and _text(ram, SHELL_LINE) == _text(before, name) == b"TESTACC1.ACC"
    assert (case.long_in(ram, FIRST_BASEPAGE), case.long_in(ram, BASEPAGES)) == (basepage, 0)
    assert _process(ram, SPARE_STATIC_PD) == (b"TESTACC1", 2, basepage, addrs.AES_ROM_GOTOPGM)
    assert (case.word_in(ram, STATIC_COUNT), case.word_in(ram, COUNT)) == (aes.AES_PD_COUNT, 0)
    assert _woken(ram) == [SPARE_STATIC_PD, *_woken(before)]


def test_the_second_accessory_is_loaded_into_a_descriptor_of_its_own():
    """THE BOOT'S SECOND CALL, count 1: a descriptor allocated BETWEEN the open and the load, kept in
    AES_ACCESSORY_PDS at the count; the basepage kept in AES_ACC_BASEPAGES at the same count — the first's word
    untouched — and getpd hands that block out as process 3, stepping the count."""
    arrived, ran = _arrived(SECOND), _returned(SECOND)
    name, count = arrived.arguments
    before, ram = arrived.stood.ram, ran.stood.ram
    block = ran.calls[1].answer
    load, basepage = _loaded(ran, 2)
    assert count == 1 and case.word_in(before, COUNT) == 0
    assert _calls(ran) == [_call(FOPEN, ("l", SHELL_LINE), ("w", 0)), _call(MALLOC, ("l", BLOCK_BYTES)), *load]
    assert ld.answered(ran) == 1 and _text(ram, SHELL_LINE) == _text(before, name) == b"TESTACC2.ACC"
    assert (case.long_in(ram, PDS), case.long_in(ram, BASEPAGES), case.word_in(ram, COUNT)) == (block, basepage, 1)
    assert case.long_in(ram, FIRST_BASEPAGE) == case.long_in(before, FIRST_BASEPAGE) != basepage
    assert _process(ram, block) == (b"TESTACC2", aes.AES_PD_COUNT, basepage, addrs.AES_ROM_GOTOPGM)
    assert _woken(ram) == [block, *_woken(before)]


def test_both_tables_are_indexed_by_the_allocated_count():
    """THE SEVEN-ACCESSORY BOOT'S THIRD ARRIVAL, a state the ROM's own run made: the count pushed is 2, the allocated
    count 1. The descriptor's block and the basepage are kept in the SECOND entries of their tables — the first, the
    second accessory's, left as they were — and getpd hands out that block as process 4, the count 2."""
    arrived, ran = _arrived(THIRD_OF_SEVEN), _returned(THIRD_OF_SEVEN)
    before, ram = arrived.stood.ram, ran.stood.ram
    assert (arrived.arguments[1], case.word_in(before, COUNT)) == (2, 1), "no word staged: the boot's own third call"
    block, basepage = ran.calls[1].answer, ran.calls[2].answer
    assert (case.long_in(ram, PDS + LONG_BYTES), case.long_in(ram, BASEPAGES + LONG_BYTES)) == (block, basepage)
    firsts = (case.long_in(before, PDS), case.long_in(before, BASEPAGES))
    assert (case.long_in(ram, PDS), case.long_in(ram, BASEPAGES)) == firsts and 0 not in firsts and block not in firsts
    third = aes_boot.SEVEN_ACCESSORY_NAMES[2].partition(".")[0].encode()
    assert case.word_in(ram, COUNT) == 2 and _process(ram, block)[:2] == (third, aes.AES_PD_COUNT + 1)


def test_any_nonzero_count_takes_a_descriptor():
    """ARGUMENT CLASS (the count pushed staged at -1, above): the count is tested against 0 alone ($fe4318 `tst.w`)
    — a negative one allocates a descriptor and keeps the basepage in the others' table, as 1 does."""
    arrived, ran = _arrived(SECOND_WITH_COUNT_MINUS_1), _returned(SECOND_WITH_COUNT_MINUS_1)
    assert arrived.arguments[1] == -1 and _functions(ran) == [FOPEN, MALLOC, PEXEC, MSHRINK, FCLOSE]
    assert case.long_in(ran.stood.ram, BASEPAGES) == ran.calls[2].answer and ld.answered(ran) == 1


def test_a_load_that_fails_leaves_the_descriptor_s_block_allocated_and_stored__behaviour_b():
    """A ROM BEHAVIOUR, PINNED AS IT IS (b): the second accessory is no program (its header's magic) — Pexec answers
    EPLFMT AFTER cre_aproc allocated; the file is closed; 0 answered — and the block is NOT freed (no Mfree is made)
    and stays in AES_ACCESSORY_PDS[0], the count still 0: the next accessory's block is stored over it. No process
    is made, no basepage kept."""
    arrived, ran = _arrived(SECOND_FAILS_TO_LOAD), _returned(SECOND_FAILS_TO_LOAD)
    before, ram = arrived.stood.ram, ran.stood.ram
    handle, block = ran.calls[0].answer, ran.calls[1].answer
    assert _functions(ran) == [FOPEN, MALLOC, PEXEC, FCLOSE] and _calls(ran)[3] == _call(FCLOSE, ("w", handle))
    assert aes.signed(ran.calls[2].answer, bits=32) == EPLFMT and ld.answered(ran) == LOADER["SNDCLI_NOT_STARTED"]
    assert block and (case.long_in(ram, PDS), case.word_in(ram, COUNT), case.long_in(ram, BASEPAGES)) == (block, 0, 0)
    assert _woken(ram) == _woken(before) and case.word_in(ram, STATIC_COUNT) == case.word_in(before, STATIC_COUNT)


def test_a_refused_descriptor_returns_without_closing_the_file__behaviour_a():
    """A ROM BEHAVIOUR, PINNED AS IT IS (a): under 2,226 bytes are free behind the first accessory (its BSS) — Malloc
    answers 0, and sndcli answers 0 WITH THE FILE STILL OPEN: its two calls are the open and the Malloc, and no
    Fclose follows. dos_alloc's failure is the glue's verdict word; nothing is stored in either table."""
    arrived, ran = _arrived(DESCRIPTOR_REFUSED), _returned(DESCRIPTOR_REFUSED)
    before, ram = arrived.stood.ram, ran.stood.ram
    assert _calls(ran) == [_call(FOPEN, ("l", SHELL_LINE), ("w", 0)), _call(MALLOC, ("l", BLOCK_BYTES))]
    assert _answers(ran)[0] >= addrs.GEMDOS_FIRST_FILE_HANDLE and _answers(ran)[1] == 0
    assert ld.answered(ran) == 0 and case.word_in(ram, aes.AES_DOS_ERR) == 1
    assert (case.long_in(ram, PDS), case.long_in(ram, BASEPAGES)) == (case.long_in(before, PDS), case.long_in(before, BASEPAGES))


# ...AND THE ARM NO DISK REACHES: the open fails. ARGUMENT CLASS — the snapshot's machine, a staged name, GEMDOS
# scripted (`aes_shell`'s recording trap, which tells Fopen and Malloc apart): nothing but the open is made.
NAME_AT = aes.BLOCKS_AT
A_NAME = "NOSUCH.ACC"


ELSEWHERE_AT = NAME_AT + 0x40           # ...and a second buffer, which the shell's buffer pointer is staged at


def _sndcli_scripted(count, answers, pokes):
    """sndcli over the snapshot with GEMDOS scripted — EVERY RUN OF ITS C FIRST IN A FORK (`aes_event`'s guard): a C that
    went on past the failed open would run off the script's end, which in process is the worker's death."""
    arguments = (NAME_AT, count)
    return sh.run_scripted(SNDCLI, arguments, answers, merge_pokes(pokes), first=aes_event.forked_inside_its_pass(SNDCLI, arguments))


@pytest.mark.parametrize("count", (0, 1, -1), ids=("the first accessory", "a later one", "a negative count"))
@pytest.mark.parametrize("error", (EFILNF, EACCDN), ids=("EFILNF", "EACCDN"))
def test_an_open_that_fails_ends_sndcli_at_once(error, count):
    """ARGUMENT CLASS (above). The name copied, Fopen of the shell's buffer over mode 0 — refused: 0 answered, the
    glue's verdict set, and neither a descriptor nor a load asked for, whatever the count."""
    assert sh.SHELL_BUFFER == SHELL_LINE
    result = _sndcli_scripted(count, [error], sh.text(NAME_AT, A_NAME, 0x40))
    assert sh.calls(result.final) == [(FOPEN, sh.frame(("l", SHELL_LINE), ("w", 0)))]
    assert result.answer() == 0 and result.field("AES", "DOS_ERR") == 1
    assert _text(result.final, SHELL_LINE) == A_NAME.encode()


def test_the_file_is_opened_by_the_shell_s_buffer_pointer_not_by_the_line_the_name_went_to():
    """ARGUMENT CLASS (the pointer staged at another buffer: every machine's names the shell's line). The name is
    copied to the LINE, an immediate; the open reads the POINTER ($fe4302 `move.l $c79e,-(sp)`) — whatever it names."""
    pokes = merge_pokes(sh.text(NAME_AT, A_NAME, 0x40), {aes.AES_SHELL_BUFFER: struct.pack(">I", ELSEWHERE_AT)})
    result = _sndcli_scripted(0, [EFILNF], pokes)
    assert sh.calls(result.final) == [(FOPEN, sh.frame(("l", ELSEWHERE_AT), ("w", 0)))]
    assert _text(result.final, SHELL_LINE) == A_NAME.encode()


# ---- cre_aproc ------------------------------------------------------------------------------------------------------------------
def test_cre_aproc_lays_a_descriptor_out_in_one_block_and_pushes_its_five_event_blocks():
    """THE BOOT'S ONE CALL: Malloc of 2,226 bytes; the block kept in AES_ACCESSORY_PDS at the count, WHICH IS NOT
    STEPPED; the PD at its start given its CDA (pinit: its pipe, a blank name), its UDA behind it, that UDA's saved
    stack pointer the top of its empty stack; and the five event blocks at its end pushed on the free list one by
    one — so the list begins with the LAST of them. 1 answered."""
    arrived, ran = _arrived(ITS_DESCRIPTOR), _returned(ITS_DESCRIPTOR)
    before, ram = arrived.stood.ram, ran.stood.ram
    block, = _answers(ran)
    assert _calls(ran) == [_call(MALLOC, ("l", BLOCK_BYTES))] and ld.answered(ran) == LOADER["ACC_MADE"]
    count = case.word_in(before, COUNT)
    assert case.long_in(ram, PDS + count * LONG_BYTES) == block and case.word_in(ram, COUNT) == count
    uda = block + aes.PD_BYTES
    assert (case.long_in(ram, block + aes.PD_UDA), case.long_in(ram, block + aes.PD_CDA)) == (uda, block + LOADER["ACC_CDA"])
    assert case.long_in(ram, uda + aes.UDA_SUPER_SP) == uda + LOADER["ACC_STACK_TOP"]
    assert bytes(ram[block + aes.PD_NAME:block + aes.PD_NAME + aes.PD_NAME_BYTES]) == b" " * aes.PD_NAME_BYTES
    events = [block + EVBS + index * aes.EVB_BYTES for index in range(EVB_COUNT)]
    free_before = aes.list_of(before, aes.AES_EUL, link=aes.EVB_NEXT, limit=aes_boot.EVB_CAP)
    assert aes.list_of(ram, aes.AES_EUL, link=aes.EVB_NEXT, limit=aes_boot.EVB_CAP) == [*reversed(events), *free_before]
    assert events[-1] + aes.EVB_BYTES == block + BLOCK_BYTES


# ---- ldaccs ---------------------------------------------------------------------------------------------------------------------
def _search(ran, drive_set_back):
    """ldaccs's calls up to its second search's answer, as `ran` made them: the drive map asked (Dgetdrv, then
    Dsetdrv of its answer), the drive, the DTA allocated and set, the map again, the look at C:'s root — the drive
    set back where it found nothing — and the search that is kept."""
    drive, dta = ran.calls[0].answer, ran.calls[3].answer
    back = [_call(DSETDRV, ("w", ran.calls[2].answer))] if drive_set_back else []
    return [_call(DGETDRV), _call(DSETDRV, ("w", drive)), _call(DGETDRV), _call(MALLOC, ("l", LOADER["LDACCS_DTA_BYTES"])),
            _call(FSETDTA, ("l", dta)), _call(DGETDRV), _call(DSETDRV, ("w", ran.calls[5].answer)),
            _call(DSETPATH, ("l", LOADER["AES_ACC_ROOT_OF_C"])), _call(FSFIRST, ("l", LOADER["AES_ACC_PATTERN_OF_C"]), ("w", 0)),
            *back, _call(DSETPATH, ("l", LOADER["AES_ACC_ROOT"])), _call(FSFIRST, ("l", LOADER["AES_ACC_PATTERN"]), ("w", 0))], dta


def test_ldaccs_loads_both_accessories_of_the_disk():
    """THE BOOT'S OWN CALL, WHOLE: the count cleared; the search (no drive C: in the map, so no Dsetdrv before it;
    found at the first look, so none after); then each file found handed sndcli — the first with count 0, the second
    with 1 — a search for the next after each, and the DTA freed once Fsnext finds no more. Both processes stand
    woken, the second ahead of the first."""
    arrived, ran = _arrived(TWO_ACCESSORIES), _returned(TWO_ACCESSORIES)
    before, ram = arrived.stood.ram, ran.stood.ram
    search, dta = _search(ran, drive_set_back=False)
    assert _calls(ran)[:len(search)] == search and not ran.calls[1].answer & DRIVE_C_BIT
    assert _functions(ran)[len(search):] == [FOPEN, PEXEC, MSHRINK, FCLOSE, FSNEXT,
                                             FOPEN, MALLOC, PEXEC, MSHRINK, FCLOSE, FSNEXT, MFREE]
    assert _calls(ran)[-1] == _call(MFREE, ("l", dta)) and _answers(ran)[-2] == ENMFIL
    block = case.long_in(ram, PDS)
    assert case.word_in(ram, COUNT) == 1 and _woken(ram) == [block, SPARE_STATIC_PD, *_woken(before)]
    assert _process(ram, SPARE_STATIC_PD)[0] == b"TESTACC1" and _process(ram, block)[0] == b"TESTACC2"
    assert _text(ram, dta + DTA_NAME) == b"TESTACC2.ACC", "the names are read where a search leaves them in the DTA"


def test_ldaccs_over_a_disk_with_no_accessory_sets_the_drive_back_and_loads_nothing():
    """THE DESK'S BOOT'S CALL: the look at C:'s root finds nothing — the drive it began on is set again — the kept
    search finds nothing either: no file opened, no process made, the DTA freed."""
    arrived, ran = _arrived(NO_ACCESSORY), _returned(NO_ACCESSORY)
    before, ram = arrived.stood.ram, ran.stood.ram
    search, dta = _search(ran, drive_set_back=True)
    assert _calls(ran) == [*search, _call(MFREE, ("l", dta))]
    assert [_answers(ran)[at] for at in (8, 11)] == [EFILNF, EFILNF]
    assert case.word_in(ram, COUNT) == 0 and _woken(ram) == _woken(before)
    assert case.word_in(ram, STATIC_COUNT) == case.word_in(before, STATIC_COUNT) == aes.AES_PD_COUNT - 1



def test_ldaccs_loads_nothing_from_a_disk_the_usable_disk_word_rules_out():
    """ARGUMENT CLASS (the word staged 0, above): the drive map is asked — isdrive's two calls — and ldaccs returns:
    no DTA, no search. The count is cleared all the same."""
    ran = _returned(NO_USABLE_DISK)
    assert _functions(ran) == [DGETDRV, DSETDRV] and ran.calls[1].answer & aes.WORD_MASK
    assert case.word_in(ran.stood.ram, COUNT) == 0


def test_ldaccs_goes_on_past_an_accessory_whose_load_fails__behaviour_b():
    """(b), WHOLE: the second accessory's load fails with its descriptor allocated — ldaccs searches on, frees the
    DTA and returns with one accessory started, THE DEAD BLOCK STILL IN AES_ACCESSORY_PDS[0] and the count 0 (so
    free_accs would never free it)."""
    ran = _returned(LDACCS_SECOND_FAILS)
    ram = ran.stood.ram
    assert _functions(ran)[11:] == [FOPEN, PEXEC, MSHRINK, FCLOSE, FSNEXT, FOPEN, MALLOC, PEXEC, FCLOSE, FSNEXT, MFREE]
    block, = [call.answer for call in ran.calls if call.function == MALLOC and call.frame == _call(MALLOC, ("l", BLOCK_BYTES))[1]]
    assert (case.long_in(ram, PDS), case.word_in(ram, COUNT)) == (block, 0) and case.long_in(ram, FIRST_BASEPAGE)
    assert _woken(ram)[0] == SPARE_STATIC_PD


def test_a_first_accessory_that_is_no_program_leaves_the_second_the_first_s_place__and_gemdos_refuses_it():
    """THE COUNT IS OF ACCESSORIES STARTED: the first file's load fails (EPLFMT), so the second is handed sndcli with
    count 0 again — no descriptor is allocated for it. AND A BEHAVIOUR OF THE ROM'S GEMDOS, as its own run shows it:
    after a Pexec that failed on a bad header, the next Pexec(3) answers ENSMEM — nothing is loaded from this disk."""
    ran = _returned(LDACCS_FIRST_FAILS)
    ram = ran.stood.ram
    assert _functions(ran)[11:] == [FOPEN, PEXEC, FCLOSE, FSNEXT, FOPEN, PEXEC, FCLOSE, FSNEXT, MFREE]
    assert [answer for call, answer in zip(ran.calls, _answers(ran)) if call.function == PEXEC] == [EPLFMT, ENSMEM]
    assert (case.long_in(ram, FIRST_BASEPAGE), case.long_in(ram, PDS), case.word_in(ram, COUNT)) == (0, 0, 0)


def test_ldaccs_never_closes_the_file_of_an_accessory_whose_descriptor_was_refused__behaviour_a():
    """(a), WHOLE: two files opened, ONE closed — the second's handle is left open when ldaccs returns."""
    ran = _returned(LDACCS_DESCRIPTOR_REFUSED)
    assert _functions(ran)[11:] == [FOPEN, PEXEC, MSHRINK, FCLOSE, FSNEXT, FOPEN, MALLOC, FSNEXT, MFREE]
    opened = [call.answer for call in ran.calls if call.function == FOPEN]
    closed = [case.word_in(call.frame, 0) for call in ran.calls if call.function == FCLOSE]
    assert len(opened) == 2 and closed == opened[:1]


A_LOAD, A_LOAD_INTO_A_DESCRIPTOR = [FOPEN, PEXEC, MSHRINK, FCLOSE, FSNEXT], [FOPEN, MALLOC, PEXEC, MSHRINK, FCLOSE, FSNEXT]
LOADS_MOST = LOADER["ACC_SLOTS"]


def test_ldaccs_takes_six_accessories_of_seven_and_never_opens_the_seventh():
    """THE SEVEN-ACCESSORY BOOT'S OWN CALL, WHOLE: six files loaded — the first into the spare static PD, FIVE into
    descriptors of their own, each kept with its basepage AT THE COUNT IT WAS ALLOCATED AT (0..4: the tables indexed
    for real) — and the loop ends WITH A SEVENTH FILE FOUND (the sixth Fsnext answers 0) and not opened. The count is
    5; the six stand woken, the last made first."""
    arrived, ran = _arrived(SIX_OF_SEVEN), _returned(SIX_OF_SEVEN)
    before, ram = arrived.stood.ram, ran.stood.ram
    search, dta = _search(ran, drive_set_back=False)
    assert _functions(ran)[len(search):] == [*A_LOAD, *A_LOAD_INTO_A_DESCRIPTOR * (LOADS_MOST - 1), MFREE]
    assert _answers(ran)[-2] == GEMDOS_OK and _text(ram, dta + DTA_NAME) == b"TESTACC7.ACC", "the seventh: found, never opened"
    blocks = [call.answer for call in ran.calls if _call(call.function, ("l", BLOCK_BYTES)) == (MALLOC, call.frame)]
    basepages = [call.answer for call in ran.calls if call.function == PEXEC]
    assert len(set(blocks)) == LOADS_MOST - 1 and len(set(basepages)) == LOADS_MOST
    assert [case.long_in(ram, PDS + index * LONG_BYTES) for index in range(LOADS_MOST - 1)] == blocks
    assert [case.long_in(ram, BASEPAGES + index * LONG_BYTES) for index in range(LOADS_MOST - 1)] == basepages[1:]
    assert (case.long_in(ram, FIRST_BASEPAGE), case.word_in(ram, COUNT)) == (basepages[0], LOADS_MOST - 1)
    made = [SPARE_STATIC_PD, *blocks]
    assert _woken(ram) == [*reversed(made), *_woken(before)]
    assert [_process(ram, pd)[:3] for pd in made] == [(f"TESTACC{nth + 1}".encode(), 2 + nth, basepages[nth]) for nth in range(LOADS_MOST)]


def test_ldaccs_makes_six_passes_and_no_more_though_none_started():
    """THE PASS BOUND BY ITSELF: the seven-accessory disk with its first accessory no program — nothing loads (GEMDOS
    refuses every load after the first's bad header: ENSMEM, as on the pair's disk) — and ldaccs opens SIX files, the
    count started still 0, and leaves the seventh, found, unopened. (The other bound — six STARTED — ends the loop
    alone only where an accessory was started before the first pass: a cartridge's, which no machine has.)"""
    ran = _returned(SIX_PASSES_NONE_STARTED)
    assert _functions(ran)[11:] == [*[FOPEN, PEXEC, FCLOSE, FSNEXT] * LOADS_MOST, MFREE]
    assert [answer for call, answer in zip(ran.calls, _answers(ran)) if call.function == PEXEC] == [EPLFMT, *[ENSMEM] * (LOADS_MOST - 1)]
    assert _answers(ran)[-2] == GEMDOS_OK and case.word_in(ran.stood.ram, COUNT) == 0 == case.long_in(ran.stood.ram, FIRST_BASEPAGE)


def test_ldaccs_halts_by_name_where_a_cartridge_answers__in_a_child():
    """ARGUMENT CLASS (the cartridge's magic staged at its port: no machine has one). The cartridge's own accessories
    are loaded by `$fed554`, which is not reconstructed: the C refuses by name there rather than go on to the disk
    as if the port were empty."""
    cart = aes.header_constants("cart.h")
    staged = {cart["CART_BASE"]: struct.pack(">I", cart["CART_APPLICATION_MAGIC"])}
    returncode, stderr, _image = aes_event.refusal(LDACCS, staged, (), bind=None, read_back=False)
    assert returncode != 0 and "ldaccs: an application cartridge answers" in stderr, stderr


# ---- free_accs: no boot calls it ------------------------------------------------------------------------------------------------
# ARGUMENT CLASS, labelled: THE BOOTED MACHINES AT THEIR IDLE (every block the ROM's own loader left), free_accs entered
# over them through the kit's differential, GEMDOS scripted — the ledger keeps each Mfree and what was parked at it.
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
FREE_RETURN_SITES = (addrs.AES_FREE_ACCS_FIRST_ENV_RETURN, addrs.AES_FREE_ACCS_FIRST_RETURN, addrs.AES_FREE_ACCS_ENV_RETURN,
                     addrs.AES_FREE_ACCS_BASEPAGE_RETURN, addrs.AES_FREE_ACCS_PD_RETURN)


SEVEN_AT_ITS_IDLE = "seven"             # `_at_its_idle`'s third machine: six loaded, `$c682` = 5 — both tables indexed 0..4 FOR REAL


@functools.cache
def _at_its_idle(accessories):
    if accessories == SEVEN_AT_ITS_IDLE:
        return gc._as_pokes(aes_boot.seven_accessory_machine(*SEVEN_QUIET).ram, "the seven-accessory machine, at its idle")
    machine = aes_boot.accessory_machine() if accessories else aes_boot.desk_machine()
    return gc._as_pokes(machine.ram, f"the {'accessory' if accessories else 'desk'} machine, at its idle")


def _freed(image):
    """What free_accs frees over `image`, in its order, each with the return site its call parks: the first
    accessory's environment and basepage (where its word is not 0, a LONG), then each allocated accessory's
    environment, basepage and descriptor (while the index is below the count, a SIGNED word)."""
    first_env, first, env, basepage, descriptor = FREE_RETURN_SITES

    def of(at, env_site, site):
        return [(case.long_in(image, at + addrs.BASEPAGE_ENV), env_site), (at, site)]
    held = case.long_in(image, FIRST_BASEPAGE)
    freed = of(held, first_env, first) if held else []
    for index in range(max(aes.signed(case.word_in(image, COUNT)), 0)):
        freed += [*of(case.long_in(image, BASEPAGES + index * LONG_BYTES), env, basepage),
                  (case.long_in(image, PDS + index * LONG_BYTES), descriptor)]
    return freed


def _blocks(image):
    return [block for block, _site in _freed(image)]


def _the_rom_s_own_answers(pokes):
    """What the ROM's OWN GEMDOS answers each Mfree free_accs makes over the machine `pokes`, each call over the
    memory the one before it left (a real `trap #1` a call: `aes_fslib.gemdos_call`)."""
    memory, answers = make_image(pokes), []
    for block in _blocks(memory):
        answer, memory = fsl.gemdos_call(memory, MFREE, *gemdos.long_words(block))
        answers.append(answer)
    return answers


def _free_accs(accessories, answers=None, pokes=None, **kwargs):
    machine = merge_pokes(_at_its_idle(accessories), gd.STALE_DOS, pokes)
    answers = _the_rom_s_own_answers(machine) if answers is None else answers
    staged = merge_pokes(machine, gd.scripted_pokes(answers))
    # (every run of the C first in a fork: a loop that ran on past the count would run off the script's end)
    return aes.run_function(FREE_ACCS, (), staged, hook=gd.scripted_hook, poison=False,
                            first=aes_event.forked_inside_its_pass(FREE_ACCS, ()), **kwargs), make_image(machine)


@THROUGH
def test_free_accs_frees_every_block_the_loader_left_and_clears_nothing(through_line_f):
    """ARGUMENT CLASS (above), the accessory machine: five Mfrees — the first accessory's environment and basepage,
    the second's environment, basepage and descriptor — each answered as the ROM's own GEMDOS answers it (freed),
    each parking its own return site; and neither the count nor a pointer is cleared."""
    result, before = _free_accs(True, through_line_f=through_line_f)
    blocks = _blocks(before)
    assert len(blocks) == 5 == len(set(blocks)) and _the_rom_s_own_answers(_at_its_idle(True)) == [GEMDOS_OK] * 5
    assert gd.calls(result.final) == [gd.call(MFREE, ("l", block)) for block in blocks]
    assert [site for site, _trap in gd.sites_parked_at(result.final)] == list(FREE_RETURN_SITES)
    assert _blocks(result.final) == blocks and result.field("AES", "DOS_ERR") == 0


def test_free_accs_over_a_machine_with_no_accessory_frees_nothing():
    """ARGUMENT CLASS, the desk's machine: no first basepage, a count of 0 — not one call."""
    result, before = _free_accs(False)
    assert not _blocks(before) and gd.calls(result.final) == []


LOW_BASEPAGE = aes.AES_THEGLO           # a "basepage" below 64 KB: the HIGH word of its address is 0, and it is one
STAGINGS = {    # what is staged over the accessory machine, and how many blocks are then freed
    "the first basepage's word 0: the allocated one's three": ({FIRST_BASEPAGE: bytes(LONG_BYTES)}, 3),
    "the first basepage below 64 KB, its word tested as a LONG: all five": ({FIRST_BASEPAGE: struct.pack(">I", LOW_BASEPAGE)}, 5),
    "the count 0: the first's two": ({COUNT: struct.pack(">h", 0)}, 2),
    "the count negative, a signed compare: the first's two": ({COUNT: struct.pack(">h", -1)}, 2),
}


@pytest.mark.parametrize("staging", STAGINGS)
def test_free_accs_reads_the_first_basepage_and_the_count_as_they_stand(staging):
    """ARGUMENT CLASS (the accessory machine with one word staged): the blocks freed and the sites parked are what
    the two words say, read as the ROM reads them."""
    pokes, how_many = STAGINGS[staging]
    freed = _freed(make_image(merge_pokes(_at_its_idle(True), pokes)))
    result, _before = _free_accs(True, [GEMDOS_OK] * len(freed), pokes)
    assert len(freed) == how_many
    assert gd.calls(result.final) == [gd.call(MFREE, ("l", block)) for block, _site in freed]
    assert [site for site, _trap in gd.sites_parked_at(result.final)] == [site for _block, site in freed]


ALLOCATED_OF_SEVEN = aes_boot.ACCESSORY_SLOTS - 1      # six loaded: the first in the spare static PD, five allocated


@pytest.mark.parametrize("refused", (False, True), ids=("the ROM's own GEMDOS's answers", "every Mfree refused"))
def test_free_accs_walks_both_tables_by_the_index_and_goes_on_past_a_refusal(refused):
    """ARGUMENT CLASS in the call (no boot calls free_accs) AND IN ONE WORD — THE TABLES ARE A ROM RUN'S: the
    seven-accessory machine at its idle, `$c682` = 5, five real blocks in `$c6b2[0..4]` and five real basepages in
    `$9bc4[0..4]`, no record staged (until wave 3's review: a count of 2 over the two-accessory machine with a
    fabricated second entry). THE ONE WORD: the first basepage's, staged 0 — the whole walk is seventeen Mfrees and
    the recorder's ledger holds sixteen (`aes_gemdosif.GEMDOS`), so the first accessory's two (held on the
    two-accessory machine, above) are left out. Fifteen Mfrees — each index's three from BOTH tables — in the ROM's
    order, each block distinct, whatever GEMDOS answers: its own answers (freed), or every one refused."""
    the_first_s_left_out = {FIRST_BASEPAGE: bytes(LONG_BYTES)}
    machine = make_image(_at_its_idle(SEVEN_AT_ITS_IDLE))
    assert case.word_in(machine, COUNT) == ALLOCATED_OF_SEVEN and case.long_in(machine, FIRST_BASEPAGE)
    how_many = 3 * ALLOCATED_OF_SEVEN
    assert how_many + 2 > gd.GEMDOS.ledger.entries >= how_many, "the staging is needed: the whole walk does not fit the ledger"
    rom_s = _the_rom_s_own_answers(merge_pokes(_at_its_idle(SEVEN_AT_ITS_IDLE), the_first_s_left_out))
    result, before = _free_accs(SEVEN_AT_ITS_IDLE, [EIMBA] * how_many if refused else rom_s, the_first_s_left_out)
    blocks = _blocks(before)
    assert len(blocks) == how_many == len(set(blocks)) and 0 not in blocks
    for index in range(ALLOCATED_OF_SEVEN):
        assert blocks[3 * index + 1:3 * index + 3] == [case.long_in(before, BASEPAGES + index * LONG_BYTES),
                                                       case.long_in(before, PDS + index * LONG_BYTES)]
    assert gd.calls(result.final) == [gd.call(MFREE, ("l", block)) for block in blocks]
    if refused:
        assert result.field("AES", "DOS_ERR") == 1 and result.field("AES", "DOS_AX") == EIMBA & aes.WORD_MASK
    else:
        assert rom_s == [GEMDOS_OK] * how_many and result.field("AES", "DOS_ERR") == 0
    assert _blocks(result.final) == blocks, "neither the count nor a pointer is cleared"


# ---- the ROM's own constants, read off its bytes --------------------------------------------------------------------------------
RETURN_SITES = {    # each site the C parks, and the door whose Line-F call the ROM makes just before it
    "AES_SNDCLI_CLOSE_RETURN": "AES_ROM_DOS_CLOSE", "AES_LDACCS_GDRV_RETURN": "AES_ROM_DOS_GDRV",
    "AES_LDACCS_SDTA_RETURN": "AES_ROM_DOS_SDTA", "AES_LDACCS_SDRV_C_RETURN": "AES_ROM_DOS_SDRV",
    "AES_LDACCS_CHDIR_OF_C_RETURN": "AES_ROM_DOS_CHDIR", "AES_LDACCS_SDRV_BACK_RETURN": "AES_ROM_DOS_SDRV",
    "AES_LDACCS_CHDIR_RETURN": "AES_ROM_DOS_CHDIR", "AES_LDACCS_FREE_RETURN": "AES_ROM_DOS_FREE",
    "AES_FREE_ACCS_FIRST_ENV_RETURN": "AES_ROM_DOS_FREE", "AES_FREE_ACCS_FIRST_RETURN": "AES_ROM_DOS_FREE",
    "AES_FREE_ACCS_ENV_RETURN": "AES_ROM_DOS_FREE", "AES_FREE_ACCS_BASEPAGE_RETURN": "AES_ROM_DOS_FREE",
    "AES_FREE_ACCS_PD_RETURN": "AES_ROM_DOS_FREE",
}
ROUTINE_SPANS = {"SNDCLI": (addrs.AES_ROM_SNDCLI, addrs.AES_ROM_LDACCS), "LDACCS": (addrs.AES_ROM_LDACCS, addrs.AES_ROM_FREE_ACCS),
                 "FREE_ACCS": (addrs.AES_ROM_FREE_ACCS, addrs.AES_ROM_CRE_APROC)}


@pytest.mark.parametrize("site", RETURN_SITES)
def test_each_return_site_the_c_parks_is_behind_the_rom_s_own_line_f_call_of_that_door(site):
    at, door = getattr(addrs, site), getattr(addrs, RETURN_SITES[site])
    lo, hi = next(span for routine, span in ROUTINE_SPANS.items() if site.startswith(f"AES_{routine}_"))
    assert lo < at < hi and aes.line_f_target(case.word_in(BASE_IMAGE, at - WORD_BYTES)) == door


def test_every_line_f_call_of_a_parking_door_in_the_loader_has_its_site():
    """...and none is missing: every Line-F call in the three routines of a door that parks its caller's return."""
    parking = {getattr(addrs, door) for door in set(RETURN_SITES.values())}
    found = {at + WORD_BYTES for lo, hi in ROUTINE_SPANS.values() for at in range(lo, hi, WORD_BYTES)
             if aes.line_f_target(case.word_in(BASE_IMAGE, at)) in parking}
    assert found == {getattr(addrs, site) for site in RETURN_SITES}


ROM_OPERANDS = {    # the instruction, its bytes' layout, what it carries
    "the descriptor block asked of Malloc": (0xfe44dc, ">HI", (0x2ebc, LOADER["ACC_BLOCK_BYTES"])),
    "its UDA": (0xfe4500, ">Hh", (0x41eb, LOADER["ACC_UDA"])),
    "its CDA": (0xfe4508, ">Hh", (0x41eb, LOADER["ACC_CDA"])),
    "its event blocks": (0xfe4510, ">Hh", (0x49eb, LOADER["ACC_EVBS"])),
    "the top of its stack": (0xfe4528, ">HI", (0xd0bc, LOADER["ACC_STACK_TOP"])),
    "how many event blocks": (0xfe455c, ">Hh", (0xbe7c, LOADER["ACC_EVB_COUNT"])),
    "an event block's size": (0xfe453e, ">Hh", (0xc3fc, aes.EVB_BYTES)),
    "the DTA asked of Malloc": (0xfe43ca, ">HI", (0x2ebc, LOADER["LDACCS_DTA_BYTES"])),
    "a name's place in the DTA": (0xfe442c, ">HIh", (0x06ae, DTA_NAME, -18)),
    "the passes": (0xfe445a, ">Hh", (0xbe7c, LOADER["ACC_SLOTS"])),
    "the started": (0xfe4460, ">Hhh", (0x0c6e, LOADER["ACC_SLOTS"], -4)),
    "the first basepage's word": (0xfe4358, ">HhI", (0x23ee, -6, FIRST_BASEPAGE)),
    "the others' table": (0xfe436c, ">HI", (0xd1fc, BASEPAGES)),
    "the descriptors' table": (0xfe44f6, ">HI", (0xd1fc, PDS)),
    "the usable-disk word": (0xfe43ba, ">HI", (0x4a79, LOADER["AES_DISK_USABLE"])),
    "gotopgm, pushed for pstart": (0xfe437c, ">HI", (0x2f3c, addrs.AES_ROM_GOTOPGM)),
    "the shell's line, pgmld's name": (0xfe4336, ">HI", (0x2f3c, SHELL_LINE)),
    "the shell's buffer, dos_open's name": (0xfe4302, ">HI", (0x2f39, aes.AES_SHELL_BUFFER)),
}


@pytest.mark.parametrize("what", ROM_OPERANDS)
def test_a_constant_of_the_loader_is_the_rom_s_own_operand(what):
    at, layout, expected = ROM_OPERANDS[what]
    assert struct.unpack_from(layout, BASE_IMAGE, at) == expected


def test_the_loader_s_strings_are_the_rom_s():
    for root, pattern in (("AES_ACC_ROOT_OF_C", "AES_ACC_PATTERN_OF_C"), ("AES_ACC_ROOT", "AES_ACC_PATTERN")):
        assert _text(BASE_IMAGE, LOADER[root]) == b"\\" and _text(BASE_IMAGE, LOADER[pattern]) == b"\\*.ACC"
    assert LOADER["AES_ACC_PATTERN_OF_C"] == LOADER["AES_ACC_ROOT_OF_C"] + 2 and LOADER["AES_ACC_PATTERN"] == LOADER["AES_ACC_ROOT"] + 2


def test_the_glue_traps_from_two_places_and_the_block_is_what_the_boot_s_reader_says():
    assert ld.GLUE_TRAP_RETURNS == (0xfe3bce, 0xfe3c46)
    assert BLOCK_BYTES == aes_boot.ACCESSORY_BLOCK_BYTES and LOADER["ACC_SLOTS"] == aes_boot.ACCESSORY_SLOTS
    assert FIRST_BASEPAGE == aes_boot.FIRST_ACCESSORY_BASEPAGE and (addrs.AES_ROM_SNDCLI, addrs.AES_ROM_LDACCS) == (
        aes_boot.SNDCLI, aes_boot.SNDCLI_END)


# ---- THE HARNESS, HELD ON ITSELF: each thing it must refuse, refused by name ---------------------------------------------------
def _held(ran, classes=ALL_THREE, label=SECOND):
    return ld.held(_arrived(label), *classes, ran=ran)


def _with_call(ran, nth, **changed):
    calls = list(ran.calls)
    calls[nth] = calls[nth]._replace(**changed)
    return ran._replace(calls=tuple(calls))


def test_a_c_call_over_another_frame_than_the_rom_s_is_refused():
    ran = _returned(SECOND)
    wrong = _with_call(ran, 1, frame=struct.pack(">I", BLOCK_BYTES + 2))
    with pytest.raises(ld.Refused, match=r"GEMDOS call 1 of the C is 0x48 over 000008b2, the ROM's 0x48 over 000008b4"):
        _held(wrong)


def test_a_c_call_of_another_function_than_the_rom_s_is_refused():
    ran = _returned(SECOND)
    with pytest.raises(ld.Refused, match=r"GEMDOS call 4 of the C is 0x3e over .*, the ROM's 0x49 over"):
        _held(_with_call(ran, 4, function=MFREE, frame=bytes(LONG_BYTES)))


def test_a_c_that_makes_a_call_more_than_the_rom_is_refused():
    ran = _returned(SECOND)
    with pytest.raises(ld.Refused, match="the C makes a GEMDOS call more than the ROM's 4 — function 0x3e"):
        _held(ran._replace(calls=ran.calls[:4]))


def test_a_c_that_makes_a_call_fewer_than_the_rom_is_refused():
    """...the ROM's run given one call more at its end, which the C never makes."""
    ran = _returned(DESCRIPTOR_REFUSED)
    more = ran._replace(calls=(*ran.calls, ld.Call(FCLOSE, struct.pack(">H", 6), (), 0, ())))
    with pytest.raises(ld.Refused, match="the C made 2 GEMDOS calls, the ROM's run 3"):
        _held(more, NO_MASK, DESCRIPTOR_REFUSED)


def test_a_store_the_c_has_not_made_where_it_traps_is_refused_at_that_call():
    """THE MEGABYTE AT EVERY CALL: a byte the ROM's routine is said to have changed before its Pexec — one the C
    does not store — is refused AT that call, by its address, though GEMDOS's own stores are laid over both."""
    ran = _returned(SECOND)
    spare = aes.AES_GL_DACNT
    assert not _arrived(SECOND).stood.ram[spare]
    wrong = _with_call(ran, 2, own=(*ran.calls[2].own, (spare, b"\x5a")))
    with pytest.raises(ld.Refused, match=rf"where it makes GEMDOS call 2 \(0x4b\) the C's megabyte is not the ROM's — {spare:#x}\+1"):
        _held(wrong)


def test_a_megabyte_that_differs_where_the_routine_returns_is_refused():
    ran = _returned(SECOND)
    ram = bytearray(ran.stood.ram)
    ram[FIRST_BASEPAGE] ^= 0x40
    with pytest.raises(ld.Refused, match=rf"where it returns the C's megabyte is not the ROM's — {FIRST_BASEPAGE:#x}\+1"):
        _held(ran._replace(stood=ran.stood._replace(ram=bytes(ram))))


def test_an_answer_that_is_not_the_rom_s_is_refused():
    ran = _returned(SECOND)
    registers = {**ran.stood.registers, "d0": 0}
    with pytest.raises(ld.Refused, match="the C answers 0x1, the ROM 0x0"):
        _held(ran._replace(stood=ran.stood._replace(registers=registers)))


def test_a_class_named_and_not_needed_is_refused():
    """The case that returns before any masked return of its own changed the mask word names that class for nothing."""
    with pytest.raises(ld.Refused, match=r"the two shores never differ in \['the Line-F mask word'\]"):
        _held(_returned(DESCRIPTOR_REFUSED), ALL_THREE, DESCRIPTOR_REFUSED)


@pytest.mark.parametrize("left_out", ALL_THREE)
def test_each_class_of_a_case_is_needed_or_the_megabytes_differ(left_out):
    """...and the other way: with any one of its three left unnamed the case is refused where the megabytes differ."""
    with pytest.raises(ld.Refused, match="the C's megabyte is not the ROM's"):
        _held(_returned(SECOND), tuple(each for each in ALL_THREE if each != left_out))


def test_a_class_no_case_may_name_is_refused():
    with pytest.raises(ld.Refused, match="no class a case of the loader may name"):
        ld.classes_of(_arrived(SECOND), "the dispatcher's stack")


class _NoCpu:
    """The watch's `trap #1` stop asked of a frame by hand: it is refused before the CPU or the ledger is read."""

    def __init__(self, status, back, function):
        self.memory = bytearray(BASE_IMAGE)
        self.sp = 0x7000
        self.memory[self.sp:self.sp + 8] = struct.pack(">HIH", status, back, function)

    def entered(self):
        watch = ld._GemdosWatched(self.memory)
        watch._entered(self.memory, self.sp)


@pytest.mark.parametrize("status, back, function, said", (
    (0x2300, 0xfe3a18, FOPEN, "a `trap #1` from 0xfe3a16"),
    (0x0300, ld.GLUE_TRAP_RETURNS[1], FOPEN, r"a `trap #1` from 0xfe3c44 \(status 0x0300\)"),
    (0x2300, ld.GLUE_TRAP_RETURNS[1], addrs.GEMDOS_FREAD_FN, "calls GEMDOS function 0x3f, whose frame this module does not name"),
), ids=("from outside the glue", "from user state", "a function it does not read"))
def test_the_watch_refuses_a_trap_it_cannot_read(status, back, function, said):
    with pytest.raises(ld.Refused, match=said):
        _NoCpu(status, back, function).entered()


def test_the_watch_refuses_a_return_with_no_entry_seen():
    """A stop missed (the run re-arms a stop at the next one) is not a call silently lost."""
    watch = ld._GemdosWatched(bytearray(BASE_IMAGE))
    with pytest.raises(ld.Refused, match="no `trap #1` was seen entered"):
        watch._returned(bytearray(BASE_IMAGE), 0)


def test_an_arrival_is_refused_off_a_machine_that_stands_elsewhere():
    stood = _arrived(SECOND).stood
    with pytest.raises(ld.Refused, match="not at AES_ROM_LDACCS's entry"):
        ld.arrival(LDACCS, stood)


def test_a_run_entered_at_the_address_it_is_to_stop_at_is_refused():
    stood = _arrived(SECOND).stood
    with pytest.raises(ld.Refused, match="a run entered at 0xfe42e8 to stop at 0xfe42e8"):
        ld.run_on.derive(stood, addrs.AES_ROM_SNDCLI)


def test_a_run_that_does_not_return_to_its_caller_s_frame_is_refused():
    """`returned` holds the stack pointer where the run ends: an arrival whose stack pointer is said one frame off."""
    arrived = _arrived(ITS_DESCRIPTOR)
    registers = dict(arrived.stood.registers)
    ran = ld.returned(arrived)
    there = {**ran.stood.registers, "isp": ran.stood.registers["isp"] + LONG_BYTES}
    assert there["isp"] != registers["isp"] + LONG_BYTES
    with pytest.raises(ld.Refused, match="not AES_ROM_CRE_APROC's return to its caller"):
        ld._vet_it_returned(arrived, ran._replace(stood=ran.stood._replace(registers=there)))


# ---- THE BLOB ROWS (band 5 wave 3, slice F: the narrow door flip) ---------------------------------------------------------------
# Each routine PRICED, as a kit call over its arrival with GEMDOS REPLAYED from the ROM's own run of that arrival
# (`aes_loader.replayed_megabyte`: what is a labelled staging there, and why). The arrivals are the accessory capture's
# and the desk capture's (the registry's import reads those two captures and no third); the seven-accessory boot's
# cases stay Tier 1. WHAT A BLOB RUN STORES THAT THE ROM'S DOES NOT — both MAPPED by the relocation registry, nothing
# dropped:
#   * THE FIRST-ENTRY FRAME psetup lays for the program (sndcli hands pstart gotopgm): the build's own
#     `aes_rom_gotopgm` — `aes_event.PROGRAM_ENTRY`, whose slots are WALKED FROM THE MACHINE. sndcli's rows are what
#     proves that entry a mapping (`aes_event.MAPPING_PROVED_BY`);
#   * pgmld's COMMAND TAIL in the replayed trap's ledger, on the shipped blob (the `.S` hands its own zero word):
#     `aes_event.TEXT_SITES`. (On the bench blob the C twin of pgmld hands a zero word of its own, as its own rows
#     say — the table prices these rows on the shipped blob, `through`.)
ROWS_AT_ARRIVALS = (FIRST, SECOND, ITS_DESCRIPTOR, TWO_ACCESSORIES, NO_ACCESSORY, DESCRIPTOR_REFUSED, SECOND_FAILS_TO_LOAD)
# THE ROWS WHOSE DTA IS LAID AT EACH SEARCH, not first (`aes_loader.DtaFilledAtItsSearches`): the one run whose searches
# leave it more than one value — a name found, then the next.
DTA_AT_ITS_SEARCHES = (TWO_ACCESSORIES,)
# free_accs IS CALLED BY NO BOOT (gem_main never returns here), so its row is no arrival's and replays no run of the
# ROM's: an ARGUMENT CLASS, said in its name — the accessory capture's machine AT ITS FIRST IDLE (`aes_boot`), the
# glue's verdict words stale, each Mfree answered what the ROM's own GEMDOS answers THAT block's Mfree over that
# machine, asked call by call outside any run of free_accs (`_the_rom_s_own_answers`); nothing GEMDOS stores is laid.
# (Its name is kept under the table's widest case: a longer one would re-align every line of `build/bench/tier3.txt`.)
FREE_ACCS_ROW = ("ARGUMENT CLASS (no boot calls it): both accessories' blocks freed at the accessory machine's idle, "
                 "each Mfree answered as GEMDOS does")


def _row_label(label):
    """A case's label as its row's: its routine's name dropped (the row is named by its core), the staging said."""
    staging = f"{ld.REPLAYED}, {ld.AT_ITS_SEARCHES}" if label in DTA_AT_ITS_SEARCHES else ld.REPLAYED
    return f"{label.split(', ', 1)[1]} ({staging})"


@functools.cache
def _replayed(label, at_its_searches=None):
    """`label`'s machine as a blob row runs over it (pokes) — `at_its_searches`: as the row says, unless handed."""
    arrived, ran = _arrived(label), _returned(label)
    at_its_searches = label in DTA_AT_ITS_SEARCHES if at_its_searches is None else at_its_searches
    megabyte = gc._as_pokes(ld.replayed_megabyte(arrived, ran, at_its_searches), f"{label}: its arrival, GEMDOS's stores laid")
    return merge_pokes(megabyte, ld.replayed_trap(arrived, ran, at_its_searches))


# (THE EVENT LAYER'S REGISTRAR: sndcli's pstart runs psetup's mask bracket, whose SR save word no host C stores —
# settled as every such row's is, `aes_event.settled`: staged at the value the ROM's run leaves, dropped by name.)
BLOB_ROWS = {label: aes_event.register_row(_row_label(label), _arrived(label).routine, _arrived(label).arguments, _replayed(label),
                                           hook=functools.partial(ld.replayed_hook, label in DTA_AT_ITS_SEARCHES))
             for label in ROWS_AT_ARRIVALS}


def _free_accs_machine():
    machine = merge_pokes(_at_its_idle(True), gd.STALE_DOS)
    return merge_pokes(machine, gd.scripted_pokes(_the_rom_s_own_answers(machine)))


BLOB_ROWS[FREE_ACCS_ROW] = aes.register(FREE_ACCS_ROW, FREE_ACCS, (), _free_accs_machine(), hook=gd.scripted_hook)


def _table_row(label):
    """The registered blob row of the case `label`, as the table reads it."""
    tier3 = bench_tier3()
    name = FREE_ACCS if label == FREE_ACCS_ROW else _arrived(label).routine
    return tier3.row_named((routines.core_symbol(name), label if label == FREE_ACCS_ROW else _row_label(label)))


def _measured(label):
    tier3 = bench_tier3()
    return tier3.measure(_table_row(label), tier3.RomBench())


@pytest.mark.parametrize("label", (*ROWS_AT_ARRIVALS, FREE_ACCS_ROW))
def test_a_blob_row_of_the_loader_is_held_by_tier_3_and_under_the_bar(label):
    """EACH ROW THROUGH THE TABLE'S OWN MEASURE (the shipped blob for a row that reaches pgmld's `.S`): the second
    differential whole — the megabyte, the answer, the replayed trap's ledger call for call — nothing dropped but
    the Line-F mask word every C row drops, and the ratio at or under the bar."""
    tier3 = bench_tier3()
    row = _table_row(label)
    by_nature = {why for _lo, _hi, why in (*aes.LINE_F_MASK_WINDOW, *aes_event.sr_drops())}
    assert {why for _lo, _hi, why in row.dropped} <= by_nature, "the words every such row settles, and nothing of the loader's own"
    assert _measured(label).ratio <= tier3.TIER3_FUNCTION_BAR


# ---- EACH REPLAYED ROW IS THE ROM'S OWN RUN OF ITS ARRIVAL (`aes_loader.vet_the_replay_is_the_run_in_place`) ----------------
# The classes each row's two megabytes — the ROM's routine as a kit call over the row's machine, and the ROM's in-place
# run — differ in, named per row and refused where unneeded. Every row: the in-place frames, the trap, the harness's
# stack. psetup's SR save word where the run reaches pstart; the glue's words a run never stores (cre_aproc's Malloc
# is dos_alloc's own trap, which parks nothing and keeps no verdict; sndcli (a) stops behind its open).
EVERY_REPLAY_S = (ld.ROM_FRAMES, ld.THE_REPLAYED_TRAP, ld.THE_HARNESS_STACK)
PSETUP_S_STATUS = ld.parked_status(aes.AES_SR_PSETUP)
REPLAY_CLASSES = {
    FIRST: (*EVERY_REPLAY_S, PSETUP_S_STATUS),
    SECOND: (*EVERY_REPLAY_S, PSETUP_S_STATUS),
    ITS_DESCRIPTOR: (*EVERY_REPLAY_S, *(ld.staged_stale(field) for field in sh.DOS_FIELDS)),
    TWO_ACCESSORIES: (*EVERY_REPLAY_S, PSETUP_S_STATUS),
    NO_ACCESSORY: EVERY_REPLAY_S,
    DESCRIPTOR_REFUSED: (*EVERY_REPLAY_S, ld.staged_stale("DOS_RETURN")),
    SECOND_FAILS_TO_LOAD: EVERY_REPLAY_S,
}
assert set(REPLAY_CLASSES) == set(ROWS_AT_ARRIVALS)


def _the_rom_s_shore(pokes, label):
    """The ROM's routine of `label` as the kit calls it over the row machine `pokes`: `(the memory it left, D0)`."""
    arrived = _arrived(label)
    staged = aes.staged(arrived.routine, vdi.as_signed(arrived.routine, arrived.arguments), pokes)
    final, _writes, registers = emu.run(make_image(staged), getattr(addrs, arrived.routine))
    return final, registers["d0"]


def _vet_the_replay(label, pokes, classes=None, at_its_searches=None):
    final, answer = _the_rom_s_shore(pokes, label)
    ld.vet_the_replay_is_the_run_in_place(
        label, _arrived(label), _returned(label), final, answer, *(REPLAY_CLASSES[label] if classes is None else classes),
        at_its_searches=label in DTA_AT_ITS_SEARCHES if at_its_searches is None else at_its_searches)


@pytest.mark.parametrize("label", ROWS_AT_ARRIVALS)
def test_a_replayed_row_s_rom_shore_is_the_rom_s_own_run_of_the_arrival_in_place(label):
    """THE HOLD OF THE STAGING (the fix pass of the narrow door flip, B-F1): the row's own registered machine, the
    ROM's routine called over it as Tier 3 calls it — its GEMDOS ledger the in-place run's calls frame for frame, its
    answer that run's, its megabyte that run's outside the row's classes, each needed."""
    row = _table_row(label)
    final, _writes, registers = emu.run(make_image(row.pokes), row.entry)
    ld.vet_the_replay_is_the_run_in_place(label, _arrived(label), _returned(label), final, registers["d0"],
                                          *REPLAY_CLASSES[label], at_its_searches=label in DTA_AT_ITS_SEARCHES)


@pytest.mark.parametrize("label", ROWS_AT_ARRIVALS)
def test_a_class_of_the_replay_s_hold_left_out_or_added_unneeded_is_refused(label):
    """EACH CLASS IS NEEDED AND NO OTHER IS: a row's hold with one of its classes left out differs by the megabyte,
    and with one it does not name added is refused as naming a class not needed."""
    pokes = _replayed(label)
    for left_out in REPLAY_CLASSES[label]:
        with pytest.raises(ld.Refused, match="megabyte is not the ROM's run's in place"):
            _vet_the_replay(label, pokes, [each for each in REPLAY_CLASSES[label] if each is not left_out])
    unneeded = next(each for each in (PSETUP_S_STATUS, ld.staged_stale("DOS_AX")) if each not in REPLAY_CLASSES[label])
    with pytest.raises(ld.Refused, match="a class named and not needed"):
        _vet_the_replay(label, pokes, (*REPLAY_CLASSES[label], unneeded))


def _with_the_script(label, answers):
    """`label`'s row machine with the replayed trap's script holding `answers` in the run's own answers' place."""
    recorder = ld.recorder_of(label in DTA_AT_ITS_SEARCHES)
    script = b"".join(struct.pack(">I", answer & aes.LONG_MASK) for answer in answers)
    return merge_pokes(_replayed(label), recorder.script.staged(script))


def _the_run_s_answers(label):
    return [call.answer for call in _returned(label).calls]


MAKES_SEVERAL_CALLS = tuple(label for label in ROWS_AT_ARRIVALS if label != ITS_DESCRIPTOR)      # cre_aproc makes one


@pytest.mark.parametrize("label", MAKES_SEVERAL_CALLS)
def test_a_replay_with_two_answers_swapped_is_not_the_rom_s_run(label):
    """THE RED, a script that is not the run's (reviewer B's B1 — which passed every row while both shores were
    compared with each other alone): the first two answers swapped — a later call's frame is then not the in-place
    run's (the handle closed, the block shrunk, the drive set), or a call is missing."""
    answers = _the_run_s_answers(label)
    assert answers[0] != answers[1]
    with pytest.raises(ld.Refused, match="the first to differ is call"):
        _vet_the_replay(label, _with_the_script(label, [answers[1], answers[0], *answers[2:]]))


NOT_GEMDOS_S = 0x40                     # a bit no answer of these runs' last call has: an answer GEMDOS did not give


@pytest.mark.parametrize("label", ROWS_AT_ARRIVALS)
def test_a_replay_whose_last_answer_is_not_gemdos_s_is_not_the_rom_s_run(label):
    """...and the LAST answer wrong (B2): the one no later call's frame can show — seen in the megabyte, where the
    glue keeps GEMDOS's answer (`DOS_AX`), or the routine what it made of it."""
    answers = _the_run_s_answers(label)
    with pytest.raises(ld.Refused, match="megabyte is not the ROM's run's in place|GEMDOS calls|answers"):
        _vet_the_replay(label, _with_the_script(label, [*answers[:-1], answers[-1] ^ NOT_GEMDOS_S]))


ANSWERS_A_WORD = tuple(label for label in ROWS_AT_ARRIVALS if vdi.ALCYON[_arrived(label).routine].restype is not None)


@pytest.mark.parametrize("label", ANSWERS_A_WORD)
def test_a_replay_that_answers_another_word_than_the_run_in_place_is_refused(label):
    """...AND THE ANSWER IS THE RUN'S (sndcli's 1 or 0, cre_aproc's): the row's own run handed to the hold with
    another word in D0 is refused by the answer — and ldaccs, which answers nothing, is asked for none."""
    assert len(ANSWERS_A_WORD) == 5 and LDACCS not in {_arrived(each).routine for each in ANSWERS_A_WORD}
    final, answer = _the_rom_s_shore(_replayed(label), label)
    with pytest.raises(ld.Refused, match="the replayed run answers"):
        ld.vet_the_replay_is_the_run_in_place(label, _arrived(label), _returned(label), final, answer ^ 1, *REPLAY_CLASSES[label])


def _without_the_stores_of(label, nth):
    """`label`'s row machine with what GEMDOS stored in call `nth` of the ROM's run NOT LAID."""
    arrived, ran = _arrived(label), _returned(label)
    kept = ran._replace(calls=tuple(call._replace(stored=()) if index == nth else call for index, call in enumerate(ran.calls)))
    megabyte = gc._as_pokes(ld.replayed_megabyte(arrived, kept), f"{label}: GEMDOS's stores laid but call {nth}'s")
    return merge_pokes(megabyte, ld.replayed_trap(arrived, ran))


STORES_IN_ITS_FIRST_CALL = (FIRST, SECOND, ITS_DESCRIPTOR, DESCRIPTOR_REFUSED, SECOND_FAILS_TO_LOAD)


@pytest.mark.parametrize("label", STORES_IN_ITS_FIRST_CALL)
def test_a_replay_with_one_call_s_stores_not_laid_is_not_the_rom_s_run(label):
    """...and A STORE OF GEMDOS'S NOT LAID (B3: the first call's — an open's file record, a Malloc's descriptor):
    the megabyte where the run returns is not the in-place run's. (ldaccs's first call is Dgetdrv, which stores
    nothing outside the process's own stack: no row of it is asked.)"""
    assert ld.replayed_megabyte(_arrived(label), _returned(label)) != ld.replayed_megabyte(
        _arrived(label), _returned(label)._replace(calls=_returned(label).calls[1:]))
    with pytest.raises(ld.Refused, match="megabyte is not the ROM's run's in place"):
        _vet_the_replay(label, _without_the_stores_of(label, 0), at_its_searches=False)


def test_ldaccs_s_first_call_stores_nothing_a_replay_lays():
    """...which is held, not said: laid or not, Dgetdrv's stores leave the two ldaccs rows' megabytes as they are."""
    for label in (TWO_ACCESSORIES, NO_ACCESSORY):
        arrived, ran = _arrived(label), _returned(label)
        assert ran.calls[0].function == DGETDRV
        assert ld.replayed_megabyte(arrived, ran) == ld.replayed_megabyte(arrived, ran._replace(calls=ran.calls[1:]))


def test_the_dta_laid_first_loads_the_last_accessory_twice_and_is_refused():
    """WHY ONE ROW'S DTA IS LAID AT ITS SEARCHES (B-F1 (b)): laid first — as every other store of GEMDOS's is — the
    DTA holds what the LAST search left, ldaccs hands sndcli the second accessory's name at both passes, and the
    first PD is named for the second file. The hold refuses that machine by the megabyte: one byte of the PD's
    name. Laid at its searches, the row is the ROM's run (the hold's own test above)."""
    arrived, ran = _arrived(TWO_ACCESSORIES), _returned(TWO_ACCESSORIES)
    lo, hi = ld.its_dta(ran)
    names = [fill[DTA_NAME:fill.index(b"\0", DTA_NAME)] for fill in ld.dta_at_each_search(arrived, ran)]
    assert names[-3:-1] == [f"{name}.ACC".encode() for name in aes_boot.ACCESSORY_NAMES], "two names found, one after the other"
    assert names[-1] == names[-2], "...and the search that finds no more leaves the last"
    laid_first = _replayed(TWO_ACCESSORIES, at_its_searches=False)
    final, _answer = _the_rom_s_shore(laid_first, TWO_ACCESSORIES)
    first_pd_s, second_pd_s = (bytes(final[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES])
                               for pd in (SPARE_STATIC_PD, case.long_in(final, PDS)))
    assert first_pd_s == second_pd_s, "both processes named for the last file found"
    with pytest.raises(ld.Refused, match="megabyte is not the ROM's run's in place") as refused:
        _vet_the_replay(TWO_ACCESSORIES, laid_first, at_its_searches=False)
    the_digit = SPARE_STATIC_PD + aes.PD_NAME + len(aes_boot.ACCESSORY_NAMES[0]) - 1
    assert f"{the_digit:#x}+1: the ROM's {ord('1'):x}, ours {ord('2'):x}" in str(refused.value), "the first PD's name: TESTACC2 for TESTACC1"
    staged = make_image(_replayed(TWO_ACCESSORIES))
    assert case.long_in(staged, ld.DTA_FILLED.dta_cell) == lo
    assert bytes(staged[lo:hi]) == arrived.stood.ram[lo:hi], "the DTA as the arrival holds it until its first search: laid at its calls ALONE"


@pytest.mark.parametrize("label", [label for label in ROWS_AT_ARRIVALS if label not in DTA_AT_ITS_SEARCHES])
def test_a_row_that_names_the_dta_at_its_searches_and_does_not_need_it_is_refused(label):
    """...AND NO OTHER ROW NAMES IT: a run with no Fsetdta has no DTA to lay, and one whose searches all fail leaves
    it one value — laid first it is the ROM's."""
    with pytest.raises(ld.Refused, match="no one DTA to lay at its searches|leave the DTA one value"):
        _replayed(label, at_its_searches=True)


def test_the_rows_that_reach_pgmld_are_priced_as_shipped_and_ldaccs_reaches_it_through_sndcli():
    """sndcli's and ldaccs's rows are `through` rows (the shipped blob: pgmld is its `.S` there, behind the generated
    thunk), and `aes_event.TEXT_SITE_CALLERS_CALLERS` is the build's own call graph: ldaccs reaches sndcli, the one
    declared caller of pgmld."""
    tier3 = bench_tier3()
    graph = transcription.call_graph(tier3.BUILT_ELF)
    reaching = transcription.callers_closure(graph, set(aes_event.TEXT_SITE_CALLERS)) - set(aes_event.TEXT_SITE_CALLERS)
    assert set(aes_event.TEXT_SITE_CALLERS_CALLERS) == {name for name in reaching if name in ("aes_ldaccs", "aes_cre_aproc", "aes_free_accs")}
    assert set(aes_event.TEXT_SITE_CALLERS_CALLERS) == {"aes_ldaccs"}
    for label in (FIRST, TWO_ACCESSORIES):
        assert tier3.ships_through_a_call(_table_row(label))
    assert not tier3.ships_through_a_call(_table_row(FREE_ACCS_ROW))


# ---- THE FIRST-ENTRY FRAME sndcli LAYS IS THE BUILD'S OWN gotopgm: mapped, never dropped (`aes_event.PROGRAM_ENTRY`) ----
SNDCLI_ROWS = (FIRST, SECOND)


@pytest.fixture
def program_entry_unmapped(monkeypatch):
    """The registry with `PROGRAM_ENTRY` naming no entry of any build — for the test's length."""
    tier3 = bench_tier3()
    door = tuple(each._replace(symbols={}) if each is aes_event.PROGRAM_ENTRY else each for each in aes_event.THE_TRAP_DOOR)
    monkeypatch.setattr(aes_event, "THE_TRAP_DOOR", door)
    tier3.door_relocation.cache_clear()
    yield
    monkeypatch.undo()
    tier3.door_relocation.cache_clear()


@pytest.mark.parametrize("label", SNDCLI_ROWS)
def test_the_frame_sndcli_lays_holds_the_rom_s_gotopgm_on_the_rom_s_shore_and_its_slot_is_walked(label):
    """WHAT THE MAPPING STANDS ON, on the ROM's shore: where the ROM's own run of the arrival returns, the process
    just started is parked on psetup's frame, whose PC — the slot `aes_event.first_entry_frames` walks to — holds the
    ROM's gotopgm; no static tuple names it (the second accessory's is a Malloc's)."""
    before, left = _arrived(label).stood.ram, _returned(label).stood.ram

    def holding_gotopgm(ram):
        return {slot for _pd, slot in aes_event.first_entry_frames(ram) if case.long_in(ram, slot) == addrs.AES_ROM_GOTOPGM}
    laid = holding_gotopgm(left) - holding_gotopgm(before)
    assert len(laid) == 1 and aes_event.PROGRAM_ENTRY.slots == (), "sndcli's own run lays one frame, and its slot is walked"
    assert len(holding_gotopgm(left)) == 1 + SNDCLI_ROWS.index(label), "the first accessory's is still unpopped at the second's"


@pytest.mark.parametrize("label", SNDCLI_ROWS)
def test_a_first_entry_frame_left_unmapped_is_refused(label, program_entry_unmapped):
    """THE RED of the mapping: with gotopgm's entry taken out of the registry sndcli's row differs from the ROM's in
    the frame's PC — the build's own `aes_rom_gotopgm` where the ROM laid `$fe38b0`. The relation drops nothing."""
    with pytest.raises(AssertionError, match="left different memory than the original"):
        _measured(label)


@pytest.mark.parametrize("label", SNDCLI_ROWS)
def test_a_build_that_laid_the_rom_s_gotopgm_is_refused_by_name(label, monkeypatch):
    """...AND THE OTHER WAY: a sndcli that handed pstart the ROM's gotopgm would leave `$fe38b0` in the frame — equal
    to the ROM's memory, so the compare alone would pass it. The registry's vet refuses it by name (THAT frame of
    the arrival's machine did not hold it: our code stored the ROM's) — AT THE SECOND ACCESSORY TOO, whose machine
    comes with the first's frame still unpopped and holding the ROM's gotopgm: what came with a machine excuses the
    slot it stood in and no other (`tier3.what_came_with`; the fix pass, A-4 — per relocation, this row passed)."""
    made = rom_bench.RomBench._call

    def laying_the_rom_s(self, image, symbol, *args, **kwargs):
        ours = made(self, image, symbol, *args, **kwargs)
        for _pd, slot in aes_event.first_entry_frames(ours.image):
            if self.base <= case.long_in(ours.image, slot) < self.end:
                ours.image[slot:slot + LONG_BYTES] = addrs.AES_ROM_GOTOPGM.to_bytes(LONG_BYTES, "big")
        return ours
    monkeypatch.setattr(rom_bench.RomBench, "_call", laying_the_rom_s)
    with pytest.raises(AssertionError, match=rf"THE ROM'S OWN address {addrs.AES_ROM_GOTOPGM:#x} in a loaded program's first-entry frame"):
        _measured(label)
