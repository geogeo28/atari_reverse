"""BOOT B6 HELD (`test/boot_late.py`, `src/boot/late/late.c`): the boot's interrupt-enabled late slice `[$fc0452, $fc047a)`
and the routines it ports with it (`$fc4a9e`, `$fc4be8`, `$fc053c`, `$fc0558`, `$fc0e56`) — the ROM's own against our C,
on the WARM and COLD machines (ruling D8, each A LABELLED STAGING), our side over a copy of the ROM window (rulings
"ROM-window overlay", "Own link rule").

THE WAITING ROUTINES ANSWERED AT THEIR ENTRIES on both shores (ruling D3, 2026-10-31; R-B4-2 for the clock) — the ACSI
probe and the clock's — each answer's value held here to the ROM's text that would leave it and to the capture (Hatari's
run of the ROM's own code) that holds it; each answer shown to write what it says and nothing else. THE FLOPPY RUN AS THE
ROM'S THROUGH THE KIT'S FDC/DMA MODEL (ruling D4, R-D4-1..3, 2026-11-01): hdv_init's drive probe and hdv_boot's Floprd
unanswered, their waits the ROM's own instruction-count loops; PSG port A and the chip carried from the ROM's runs
(R-D4-2); the model's ordered ledger and the chip it leaves held exactly; the drive arms (B: absent, no drive, A: empty)
each reached by the ROM's own count; Floprd's read of the blank disk the device model's. Held on every observable surface:
the stop, every register, the megabyte and the stores outside the BIOS stack's dead frames (the capture's own MASK
field), every ordered ledger, the FDC chip, the faults, the answers in order; each surface's negative here; each arm's
own cost pinned exactly; the price the table's (ruling D9). THE END SURFACE: the machine both shores reach at `$fc047a`
against the mid-boot capture under its own mask — apart in exactly D1, the same on both shores (D4's class gone); B4's
open carry (A3, A4, A6) closed here."""
import re
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs

import aes_boot
import boot
import boot_display
import boot_late as bl
import case
import layouts
import midboot_snapshot
import rom_data
from test_aes_devices import SYSVAR_NFLOPS

C = bl.CONSTANTS
BAR = 1.10
WORD_BYTES, LONG_BYTES = bl.WORD_BYTES, bl.LONG_BYTES
# THE ROM'S INSTRUCTIONS THE ANSWERS ARE READ OFF (each held to its text below).
# THE FLOPPY'S WAITS, read off the lower driver: `move.l #$40000,d7` (`#$60000`, the motor off), then `subq.l #1,d7 /
# beq timeout / btst #5,$fffa01 / bne` — instruction counts, no `_hz_200` (what lets the zero-time model serve them).
FLOPPY_WAIT_COUNT_LOAD, FLOPPY_SPIN_UP_COUNT_LOAD, FLOPPY_WAIT_POLL = 0xfc1dc0, 0xfc1dd4, 0xfc1de2
FLOPPY_WAIT_COUNT, FLOPPY_SPIN_UP_COUNT = 0x40000, 0x60000
ACSI_TIMED_OUT = 0xfc0642               # `$fc062a`'s `moveq #-1,d1`: `_hz_200` passed the count
ACSI_FAILED = 0xfc0606                  # `moveq #-1,d0`: the probe's failure
ACSI_FLAGS_SET = 0xfc060c               # `tst.b d0`: the flags it returns
ACSI_FLOCK_TAKEN, ACSI_FLOCK_FREED = 0xfc0592, 0xfc060e     # `st flock` / `sf flock`
CLOCK_PROBE_ABSENT = 0xfc4c3e           # the probe's `ori #1,ccr`: no RP5C15
RS232_TABLE_LOADED = 0xfc2522           # `$fc2408`'s `movea.l #<the RS232 handlers' table>,a3`
PRTBLK_END = 0xfc41a4                   # past Prtblk's own `rts` ($fc41a2): the text the overlay lies in ends
DISPLAY_BIN = bl.RECREATE / "build" / "bootdisplay" / "display.bin"
DISTINCT_LONG = 0x5a3c_c3a5            # a register pattern whose every byte differs from what an answer writes
ACSI_TARGETS = tuple(range(0, 0x100, C["ACSI_TARGET_STEP"]))    # `moveq #0,d7` .. the byte's wrap
FLOPPY_DRIVES = (0, 1)                  # hdv_init's loop: `cmpi.w #2,-2(a6)` ($fc0fb4) — drives A: and B:
SR_INTERRUPT_MASK = 0x0700
JMP_ABSOLUTE_LONG, JSR_ABSOLUTE_LONG = 0x4ef9, 0x4eb9


# ---- THE ROM'S TEXT: every constant the C is spelt in, read off the instruction that uses it ------------------------------
def _listing(span):
    return [text for _at, text in rom_data.instructions(*span)]


def test_the_slice_is_spelt_in_the_rom_s_own_operands():
    """`[$fc0452, $fc047a)` as the ROM's listing reads it, composed out of `boot/late.h` and the headers it names."""
    assert _listing(bl.SPAN) == [
        f"movew #{C['BOOT_SR_INTERRUPTS_OPEN']},%sr", f"moveq #{C['CARTRIDGE_HOOK_INTERRUPTS']},%d0",
        f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}", f"bsrw {bl.GEMDOS_BUFFERS[0]:#x}",
        f"movew {C['ROM_OS_HEADER'] + C['OS_HEADER_DOSDATE']:#x},{addrs.GEMDOS_DATE:#x}",
        f"bsrw {bl.CLOCK_DATE[0]:#x}", f"bsrw {bl.FLOPPY_BOOT[0]:#x}", f"bsrw {bl.ACSI_BOOT[0]:#x}",
        f"bsrw {bl.RESIDENT_SCAN[0]:#x}"]
    assert bl.SPAN == (C["ROM_DISPLAY_END"], C["ROM_LAUNCH"])


def test_gemdos_s_buffers_are_spelt_in_the_rom_s_own_operands():
    """`$fc4a9e`: four BCBs from BOOT_BCB_FIRST, two to a list, the first of each linked to the second, every one EMPTY,
    their sector buffers end to end from BOOT_SECTOR_BUFFER_FIRST; the lists' heads in _bufl; GEMDOS's init; Dsetdrv of
    the boot drive from the `link`'s one local; and the frame that is GEMDOS_BUFFERS_FRAME_BYTES with the `bsr`'s return."""
    fs = layouts.parse_constants((bl.RECREATE / "include" / "gemdos" / "fs.h",))
    bcbs = [C["BOOT_BCB_FIRST"] + each * fs["BCB_BYTES"] for each in range(2 * C["BOOT_BCBS_PER_LIST"])]
    buffers = [C["BOOT_SECTOR_BUFFER_FIRST"] + each * addrs.BOOT_SECTOR_BYTES for each in range(len(bcbs))]
    local = C["GEMDOS_BUFFERS_FRAME_BYTES"] - 2 * LONG_BYTES
    assert _listing(bl.GEMDOS_BUFFERS) == [
        f"linkw %fp,#-{local}",
        f"movel #{bcbs[1]},{bcbs[0] + fs['BCB_LINK']:#x}", f"movel #{bcbs[3]},{bcbs[2] + fs['BCB_LINK']:#x}",
        *[f"movew #-1,{bcb + fs['BCB_BUFDRV']:#x}" for bcb in bcbs],
        *[f"movel #{buffer},{bcb + fs['BCB_BUFR']:#x}" for bcb, buffer in zip(bcbs, buffers)],
        f"movel #{bcbs[0]},{addrs.SYSVAR_BUFL:#x}", f"movel #{bcbs[2]},{addrs.SYSVAR_BUFL + addrs.SYSVAR_BUFL_ENTRY_BYTES:#x}",
        f"jsr {C['ROM_GEMDOS_INIT']:#x}", f"movew {C['SYSVAR_BOOTDEV']:#x},%sp@", f"jsr {addrs.GEMDOS_DSETDRV:#x}",
        "unlk %fp", "rts"]
    assert fs["BCB_EMPTY"] == 0xffff


def test_the_clock_s_date_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.CLOCK_DATE) == [
        f"bsrs {addrs.BIOS_RTC_PROBE:#x}", "bcss 0xfc4c08", f"bsrs {C['ROM_RTC_READ']:#x}", "cmpl #-1,%d0",
        "beqs 0xfc4c08", f"movew %d0,{addrs.GEMDOS_TIME:#x}", "swap %d0", f"movew %d0,{addrs.GEMDOS_DATE:#x}",
        "moveq #0,%d0", "rts", "moveq #-1,%d0", "rts"]
    assert C["RTC_NO_STAMP"] == 0xffffffff


def test_the_floppy_s_boot_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.FLOPPY_BOOT) == [
        f"moveq #{C['CARTRIDGE_HOOK_FLOPPY_BOOT']},%d0", f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}",
        f"moveal {C['SYSVAR_HDV_BOOT']:#x},%a0", "jsr %a0@", "tstw %d0", "bnes 0xfc0556",
        f"lea {C['BOOT_DISK_BUFFER']:#x},%a0", "jsr %a0@", "rts"]


def test_the_acsi_s_boot_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.ACSI_BOOT) == [
        "moveq #0,%d7", f"bsrs {C['ROM_ACSI_READ_BOOT_SECTOR']:#x}", "bnes 0xfc057e",
        f"moveal {C['SYSVAR_DSKBUFP']:#x},%a0", f"movew #{addrs.BOOT_SECTOR_WORDS - 1},%d1", "moveq #0,%d0",
        "addw %a0@+,%d0", "dbf %d1,0xfc056a", f"cmpw #{addrs.BOOT_EXECUTABLE_SUM},%d0", "bnes 0xfc057e",
        f"moveal {C['SYSVAR_DSKBUFP']:#x},%a0", "jsr %a0@", f"addb #{C['ACSI_TARGET_STEP']},%d7", "bnes 0xfc055a", "rts"]


def test_the_reset_resident_scan_is_spelt_in_the_rom_s_own_operands():
    assert _listing(bl.RESIDENT_SCAN) == [
        f"moveal {addrs.SYSVAR_PHYSTOP:#x},%a0", f"subaw #{C['RESIDENT_PAGE_BYTES']},%a0",
        f"cmpal #{C['RESIDENT_SCAN_FLOOR']},%a0", "beqs 0xfc0e94", f"cmpil #{C['RESIDENT_MAGIC']},%a0@",
        "bnes 0xfc0e5c", f"cmpal %a0@({C['RESIDENT_SELF']}),%a0", "bnes 0xfc0e5c", "clrw %d0", "moveal %a0,%a1",
        f"movew #{addrs.BOOT_SECTOR_WORDS - 1},%d1", "addw %a1@+,%d0", "dbf %d1,0xfc0e7e", f"cmpw #{C['RESIDENT_SUM']},%d0",
        "bnes 0xfc0e5c", "movel %a0,%sp@-", f"jsr %a0@({C['RESIDENT_ENTRY']})", "moveal %sp@+,%a0", "bras 0xfc0e5c",
        "rts"]


# ---- THE ANSWERS: each entry, each value, held to the ROM's text and to the capture --------------------------------------
def _at(at):
    return rom_data.instructions(at, at + WORD_BYTES)[0][1]


def test_the_floppy_s_waits_count_instructions_and_never_read_the_clock():
    """WHY NO TIME SOURCE (ruling D4): the lower driver's wait loads its count, then polls GPIP bit 5 — no `_hz_200`."""
    assert _at(FLOPPY_WAIT_COUNT_LOAD) == f"movel #{FLOPPY_WAIT_COUNT},%d7"
    assert _at(FLOPPY_SPIN_UP_COUNT_LOAD) == f"movel #{FLOPPY_SPIN_UP_COUNT},%d7"
    assert _at(FLOPPY_WAIT_POLL) == "btst #5,0xfffffa01"
    assert not [text for _at_, text in rom_data.instructions(FLOPPY_WAIT_COUNT_LOAD, FLOPPY_WAIT_POLL + 10)
                if f"{addrs.SYSVAR_HZ_200:#x}" in text]


def test_the_drive_probe_is_hdv_init_s_and_the_model_counts_both_drives_as_the_capture_did():
    """hdv_init calls the probe for each drive, the drive at 12(sp), and stores its D0 in the drive's status word: the
    capture's ROM run stored 0 for BOTH drives — and so does the ROM's run through the model on the capture's drives."""
    assert _at(bl.DRIVE_PROBE_CALL) == f"jsr {bl.DRIVE_PROBE:#x}"
    assert _at(bl.DRIVE_PROBE + 6) == f"tstw %sp@({bl.DRIVE_PROBE_DEVICE_AT})"
    status = case.long_in(BASE_IMAGE, bl.DRIVE_STATUS_LOAD + WORD_BYTES)
    assert _at(bl.DRIVE_STATUS_LOAD) == f"addal #{status},%a0"
    capture, ran = boot.midboot_machine(), bl.the_rom_s(boot.COLD).slice.machine
    for machine in (capture, ran):
        assert [case.word_in(machine.ram, status + drive * WORD_BYTES) for drive in FLOPPY_DRIVES] == [0, 0]
        assert case.word_in(machine.ram, SYSVAR_NFLOPS) == len(FLOPPY_DRIVES)


def test_floprd_is_the_machine_s_own_xbios_entry_and_hdv_boot_calls_it():
    assert _at(bl.FLOPRD_CALL) == f"jsr {bl.FLOPRD_ENTRY:#x}"
    machine = bl.start_of(boot.COLD)
    memory = bytearray(BASE_IMAGE)
    memory[:bl.RAM_BYTES] = machine.ram
    assert aes_boot._xbios_entry(memory, aes_boot.XBIOS_FLOPRD) == bl.FLOPRD_ENTRY


def test_the_acsi_s_no_device_is_what_the_rom_s_probe_leaves_and_what_the_capture_holds():
    """D3 "no device": the probe `lea`s A6 and A5 first; its first command byte unacknowledged, `$fc062a` ends with
    `moveq #-1,d1`, `$fc0606` `moveq #-1,d0`, then `tst.b d0` and `sf flock`. The capture — Hatari's run of the ROM's own
    probe, eight times, the reset-resident scan after it touching none of the four — holds exactly these."""
    assert _at(bl.ACSI_PROBE) == f"lea {bl.ACSI_A6:#x},%fp" and _at(bl.ACSI_PROBE + 6) == f"lea {bl.ACSI_A5:#x},%a5"
    assert _at(ACSI_TIMED_OUT) == "moveq #-1,%d1" and _at(ACSI_FAILED) == "moveq #-1,%d0" and _at(ACSI_FLAGS_SET) == "tstb %d0"
    assert _at(ACSI_FLOCK_TAKEN) == f"st {addrs.SYSVAR_FLOCK:#x}" and _at(ACSI_FLOCK_FREED) == f"sf {addrs.SYSVAR_FLOCK:#x}"
    assert _at(bl.ACSI_WAIT_ADD) == f"addl {addrs.SYSVAR_HZ_200:#x},%d1"
    capture = boot.midboot_machine()
    assert {name: capture.registers[name] for name in bl.ACSI_NO_DEVICE} == bl.ACSI_NO_DEVICE
    assert capture.ram[addrs.SYSVAR_FLOCK] == 0


def _standing_at(machine, entry, **registers):
    """`machine` standing at `entry` as a caller's `jsr` leaves it: a return address pushed under the stack pointer."""
    ram = bytearray(machine.ram)
    sp = machine.registers["isp"] - LONG_BYTES
    struct.pack_into(">I", ram, sp, bl.SPAN[1])
    return machine._replace(ram=bytes(ram), registers={**machine.registers, "pc": entry, "isp": sp, **registers})


@pytest.mark.parametrize("entry", sorted(bl.ANSWERED), ids=hex)
def test_each_answer_writes_what_it_says_and_nothing_else(entry):
    """Each answer from a machine whose every scratch register holds a pattern: the registers it names written, the
    flags it names, the PC the return, the stack one longword up — every other register and byte as they were."""
    machine = bl.start_of(boot.COLD)
    before = _standing_at(machine, entry, **{name: DISTINCT_LONG for name in ("d0", "d1", "a5", "a6")},
                          d7=0x40, sr=machine.registers["sr"] | 0x1f)
    after, asked, laid = bl.answered(before)
    registers = {**before.registers, "pc": bl.SPAN[1], "isp": before.registers["isp"] + LONG_BYTES}
    ram = bytearray(before.ram)
    if entry == bl.ACSI_PROBE:    # read off the ROM's text: the two `lea`s, the two `moveq #-1`, `tst.b` over -1
        a6, a5 = (_operand_of_lea(at) for at in (bl.ACSI_PROBE, bl.ACSI_PROBE + 6))
        registers.update(d0=_moveq_minus_one(ACSI_FAILED), d1=_moveq_minus_one(ACSI_TIMED_OUT), a5=a5, a6=a6)
        registers["sr"] = before.registers["sr"] & ~0x1f | 0x08      # X (the wait's `add.l`, no carry) Z V C clear, N set
        ram[addrs.SYSVAR_FLOCK] = 0
        assert asked == ("the ACSI probe", 0x40) and laid == ((addrs.SYSVAR_FLOCK, 1),)
    else:                           # the probe's absent arm: `ori #1,ccr` — the carry
        assert _at(CLOCK_PROBE_ABSENT) == "orib #1,%ccr"
        registers["sr"] = before.registers["sr"] | 0x01
        assert asked == ("the clock's probe",)
    assert after.registers == registers and after.ram == bytes(ram)


def _operand_of_lea(at):
    return int(re.fullmatch(r"lea (0x[0-9a-f]+),%(?:fp|a5)", _at(at)).group(1), 16)


def _moveq_minus_one(at):
    assert _at(at).startswith("moveq #-1,")
    return 0xffffffff


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_the_rom_s_floprd_through_the_model_reads_what_the_device_model_served(machine):
    """THE FLOPRD CROSS-CHECK (R-D4-3): from the one machine standing at Floprd's entry, `aes_boot.Floppy`'s answer (the
    one B6 retired) and the ROM's own Floprd run through the FDC model to its return: the same call (the boot sector of
    the blank disk to `_dskbufp`), the same bytes at every run the device model lays, the same D0."""
    check, model, returned = bl.floprd_cross_check(machine)
    assert check.asked.arguments == (C["BOOT_DISK_BUFFER"], 0, 1, 0, 0, 1)
    assert check.laid == ((C["BOOT_DISK_BUFFER"], addrs.BOOT_SECTOR_BYTES),)
    assert returned.registers["d0"] == check.model_d0 == check.served_d0 == FLOPRD_OK     # D0 off the ROM's run itself
    assert model == check.served
    assert check.served[C["BOOT_DISK_BUFFER"]] == bl.the_disk()[:addrs.BOOT_SECTOR_BYTES]


FLOPRD_OK = 0
FLOPRD_SEEK_ERROR = 0xfffffffa          # -6: the `$a26` Floprd's seek-verify ($fc1d7a) loads, extended at its exit


def test_the_cross_check_s_d0_is_the_rom_s_own_not_the_device_model_s():
    """THE D0 HALF, PINNED APART FROM THE ANSWER IT IS CHECKED AGAINST: drive A: empty, the ROM's Floprd times out in its
    seek-verify and returns the seek error, while the device model (which holds the disk) would have answered 0 — so a
    `model_d0` that were the device model's would be named here."""
    check, _model, returned = bl.floprd_cross_check(boot.COLD, bl.A_EMPTY)
    assert returned.registers["d0"] == check.model_d0 == FLOPRD_SEEK_ERROR
    assert check.served_d0 == FLOPRD_OK and check.model_d0 != check.served_d0


def test_the_boot_sector_lands_through_the_dma_as_a_store():
    """The DMA's 512 bytes are STORES of the run (the kit joins them to the write-set), at `_dskbufp`."""
    shore = bl.the_rom_s(boot.COLD)
    sector = bytes(shore.slice.machine.ram[C["BOOT_DISK_BUFFER"]:C["BOOT_DISK_BUFFER"] + addrs.BOOT_SECTOR_BYTES])
    assert sector == bl.the_disk()[:addrs.BOOT_SECTOR_BYTES]
    assert ("dma_in", C["BOOT_DISK_BUFFER"], addrs.BOOT_SECTOR_BYTES) in shore.slice.fdc_events
    assert any(start <= C["BOOT_DISK_BUFFER"] and C["BOOT_DISK_BUFFER"] + addrs.BOOT_SECTOR_BYTES <= start + length
               for start, length in shore.slice.stored)


def test_an_entry_no_answer_names_is_refused():
    with pytest.raises(boot.Refused, match="no answered entry"):
        bl.answered(bl.start_of(boot.COLD))


# ---- THE PRODUCT AND ITS STAGING ------------------------------------------------------------------------------------------
def test_the_product_lies_at_its_laid_address_clear_of_b5_s_overlay():
    display = layouts.parse_constants((bl.INCLUDE_BOOT / "display.h",))["DISPLAY_LAID_AT"]
    product = bl.product()
    assert product.base == C["LATE_LAID_AT"] and product.symbols[bl.ENTRY_SYMBOL] == product.base
    assert display + DISPLAY_BIN.stat().st_size <= product.base and product.base + len(product.code) <= PRTBLK_END


BOOT_SOURCES = bl.RECREATE / "src" / "boot"
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_STRING_MACRO = re.compile(r'^#define\s+(\w+)\s+((?:"[^"]*"\s*,?\s*)+)$', re.MULTILINE)
_ASM_EXIT = re.compile(r"__asm__\b(?:(?!__asm__).)*?\);\s*__builtin_unreachable\(\);", re.DOTALL)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CLOBBER_SECTION = 3    # `template : outputs : inputs : clobbers [: labels]`


def _clobbers(statement, macros):
    """The clobber section of one `__asm__ (...)` statement, its string macros expanded."""
    sections = _STRING_LITERAL.sub(lambda literal: literal[0].replace(":", ""), statement).split(":")   # a template's labels
    clobbers = sections[_CLOBBER_SECTION] if len(sections) > _CLOBBER_SECTION else ""
    return re.sub(r"\b\w+\b", lambda name: macros.get(name[0], name[0]), clobbers)


def test_every_asm_that_leaves_for_good_clobbers_memory():
    """A `jmp` out of the boot's C leaves the function for good (`__builtin_unreachable()` follows it: a noreturn function
    that falls off its end is an error under -Werror), so GCC may sink or drop any store before it unless the asm says it
    reads memory. Owed by review RCH on late.c's exit to `$fc047a`; display.c's exit is the second site held."""
    exits = {}
    for source in sorted(BOOT_SOURCES.rglob("*.c")):
        text = _BLOCK_COMMENT.sub("", source.read_text())
        macros = dict(_STRING_MACRO.findall(text))
        for statement in _ASM_EXIT.findall(text):
            exits.setdefault(source.relative_to(BOOT_SOURCES).as_posix(), []).append('"memory"' in _clobbers(statement, macros))
    assert exits == {"late/late.c": [True], "display/display.c": [True]}


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_the_rom_s_run_is_the_same_with_and_without_the_overlay(machine):
    plain, with_it = bl.the_rom_s(machine), bl.the_rom_s(machine, laid=bl.overlay())
    assert (with_it.slice.stop, with_it.slice.instructions, with_it.slice.cycles, with_it.own, with_it.answers) == (
        plain.slice.stop, plain.slice.instructions, plain.slice.cycles, plain.own, plain.answers)
    assert with_it.slice.machine == plain.slice.machine and with_it.slice.stored == plain.slice.stored
    assert all(getattr(with_it.slice, ledger) == getattr(plain.slice, ledger) for ledger in bl.LEDGERS)


@pytest.mark.parametrize("span", bl.THE_ROM_S_SPANS, ids=lambda span: f"{span[0]:#x}")
def test_a_run_of_ours_that_runs_the_rom_s_code_is_refused_by_name(span):
    """THE FALSE GREEN: code laid as ours that jumps into the ROM's own slice — or any routine this slice ports — would
    be held equal on the ROM's instructions."""
    if span == bl.SPAN:
        jump_in = struct.pack(">HI", JMP_ABSOLUTE_LONG, span[0])
    else:       # a routine the slice ports, called as ours would call it, then on to the slice's end
        jump_in = struct.pack(">HIHI", JSR_ABSOLUTE_LONG, span[0], JMP_ABSOLUTE_LONG, bl.SPAN[1])
    with pytest.raises(boot.Refused, match=rf"the run executed \[{span[0]:#x}, {span[1]:#x}\)"):
        bl.our_side(boot.COLD, code=jump_in)


# ---- EVERY ARM, EVERY HELD SURFACE ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module", params=bl.MACHINES)
def a_pair(request):
    machine = request.param
    return machine, bl.the_rom_s(machine), bl.our_side(machine)


def test_ours_is_the_rom_s_on_every_held_surface(a_pair):
    _machine, the_rom_s, ours = a_pair
    assert bl.differences(the_rom_s, ours) == []
    assert ours.slice.stop == bl.SPAN[1] and ours.slice.machine.registers == the_rom_s.slice.machine.registers


def test_the_answers_are_asked_in_the_rom_s_order(a_pair):
    """The hooks with 1; GEMDOS's init; Dsetdrv of drive 0 (`_bootdev`); the clock once; the hooks with 3; the ACSI for
    each of its eight targets in order — on both shores. The drive probe and Floprd are ANSWERED NO MORE (R-D4-3)."""
    _machine, the_rom_s, ours = a_pair
    assert ours.answers == the_rom_s.answers
    hooks = "the cartridge's hooks"
    assert list(ours.answers) == [
        (hooks, C["CARTRIDGE_HOOK_INTERRUPTS"]), ("GEMDOS's init",), ("Dsetdrv", 0), ("the clock's probe",),
        (hooks, C["CARTRIDGE_HOOK_FLOPPY_BOOT"]), *[("the ACSI probe", target) for target in ACSI_TARGETS]]


def test_the_slice_s_state_is_laid(a_pair):
    """What the slice is FOR, on both shores: the interrupts open (mask 3), the two buffer lists, the DOS date the OS
    header's, the drives counted and mounted (both, through the model), the boot sector read, flock free, A0 the scan's
    floor."""
    _machine, _the_rom_s, ours = a_pair
    ram, registers = ours.slice.machine.ram, ours.slice.machine.registers
    assert registers["sr"] & SR_INTERRUPT_MASK == C["BOOT_SR_INTERRUPTS_OPEN"] & SR_INTERRUPT_MASK
    fs = layouts.parse_constants((bl.RECREATE / "include" / "gemdos" / "fs.h",))
    first, third = C["BOOT_BCB_FIRST"], C["BOOT_BCB_FIRST"] + 2 * fs["BCB_BYTES"]
    assert [case.long_in(ram, addrs.SYSVAR_BUFL + list_ * addrs.SYSVAR_BUFL_ENTRY_BYTES) for list_ in (0, 1)] == [first, third]
    assert case.word_in(ram, addrs.GEMDOS_DATE) == case.word_in(BASE_IMAGE, C["ROM_OS_HEADER"] + C["OS_HEADER_DOSDATE"])
    assert case.long_in(ram, addrs.SYSVAR_DRVBITS) & 0b11 == 0b11
    assert ram[addrs.SYSVAR_FLOCK] == 0 and registers["a0"] == C["RESIDENT_SCAN_FLOOR"] and registers["d7"] == 0


def test_no_interrupt_is_delivered_and_only_the_floppy_is_touched(a_pair):
    """The slice opens the interrupts and none arrives (D3); every other device it reaches is answered at an entry. ITS
    HARDWARE IS THE FLOPPY'S ALONE, on both shores: every store in the DMA block, the PSG's port A alone, no declared or
    modelled read (GPIP's polls are the FDC model's own ledger's) — and that ledger's polls are GPIP's declared byte with
    bit 5 LOW: the zero-time chip's INTRQ at the first poll, every wait; no command hangs."""
    machine, the_rom_s, ours = a_pair
    asserted = boot_display.GPIP_OF[bl.DISPLAY_ARM[machine].monitor] & ~bl.GPIP_INTRQ    # B5's arm's declaration
    for shore in (the_rom_s, ours):
        slice_ = shore.slice
        assert slice_.hardware_writes
        assert all(bl.DMA_BLOCK[0] <= at < bl.DMA_BLOCK[1] for at, _width, _value in slice_.hardware_writes)
        assert {register for _kind, register, _value in slice_.psg_events} == {addrs.PSG_PORT_A}
        assert not slice_.io_reads and not slice_.hardware_reads and not slice_.faults
        polls = [entry for entry in slice_.fdc_events if entry[0] == "poll"]
        assert polls and all(entry[1:] == (asserted, 1) for entry in polls)
        assert not [entry for entry in slice_.fdc_events if entry[0] in ("hang", "forced")]



def test_the_stores_apart_lie_in_the_bios_stack_s_dead_frames_alone(a_pair):
    """Unmapped, the megabytes differ in THE RESIDUE alone (the capture's own MASK field: the BIOS stack under its top),
    and nothing is stored below it — the frames apart are each shore's own depths. The residue
    is dead at `$fc047a`: B4's `test_the_capture_s_masked_bytes_are_read_by_no_run_to_gem_entry`."""
    _machine, the_rom_s, ours = a_pair
    lo, hi = bl.STACK_RESIDUE
    differing = [at for at, (one, other) in enumerate(zip(the_rom_s.slice.machine.ram, ours.slice.machine.ram)) if one != other]
    assert differing and lo <= min(differing) and max(differing) < hi
    below = range(lo - (hi - lo), lo)
    for shore in (the_rom_s, ours):
        assert not [start for start, length in shore.slice.stored if start < below.stop and below.start < start + length]


def test_our_own_cost_is_pinned_exactly(a_pair):
    """COST IS THE ONLY SURFACE of the C's shape where every other surface holds (the scan's loop, the BCBs' stores), so
    each arm's own cycles are pinned."""
    _machine, the_rom_s, ours = a_pair
    assert (ours.own, the_rom_s.own) == OWN_CYCLES


# ours, the ROM's: the same on WARM and COLD (the slice reads nothing they differ in). Ours 115,906 before the floppy ran
# through the FDC model: +16, the two `lea`s that call hdv_boot at the ROM's depth (`FLOPPY_BOOT_FRAME_BYTES`).
OWN_CYCLES = (115_922, 136_546)


# ---- THE END SURFACE: the mid-boot capture ---------------------------------------------------------------------------------
def test_the_end_surface_is_the_capture_but_d1():
    """COLD — the capture is a power-on's boot — reaches `$fc047a` on both shores equal to the capture outside its MASK
    but for D1 ALONE (the cold arm's memctrl on the flat megabyte: D6, memctrl, D6's copy where the BIOS framed it, and
    D6's low byte in the lower floppy driver's save area) — the same on both shores, pinned exactly. D4's class (the lower
    driver's state in [$9f6, $a54) and its scratch D2 / A1) is GONE: the driver runs through the FDC model (R-D4-3)."""
    capture = boot.midboot_machine()
    rom, ours = bl.against_the_capture(bl.the_rom_s(boot.COLD), capture), bl.against_the_capture(bl.our_side(boot.COLD), capture)
    assert rom == ours == (set(bl.END_REGISTERS_OWED), set(bl.END_APART))
    assert set(bl.END_REGISTERS_OWED) == {"d6"}
    assert [at for at in bl.END_APART if bl.LOWER_DRIVER_STATE[0] <= at < bl.LOWER_DRIVER_STATE[1]] == [
        bl.LOWER_DRIVER_SAVED_D6_LOW]


def test_the_memctrl_copies_are_the_cold_arm_s_own():
    """D1 named, not assumed: the capture's ST holds memctrl $05, the oracle's flat megabyte sizes $08 — in memctrl and in
    D6's low byte where the BIOS framed D6 below savptr (the register save area: D3 at $90c, a longword each), and where
    the lower floppy driver's `movem.l d3-d7/a3-a6,$a28` keeps it ($a34: D6's low byte at $a37)."""
    capture = boot.midboot_machine()
    ours = bl.our_side(boot.COLD).slice.machine
    memctrl, framed = bl.MEMCTRL_COPIES
    assert (capture.ram[memctrl], ours.ram[memctrl]) == (capture.registers["d6"], ours.registers["d6"]) == (0x05, 0x08)
    assert (capture.ram[framed], ours.ram[framed]) == (0x05, 0x08)
    saved = bl.LOWER_DRIVER_SAVED_D6_LOW
    assert (capture.ram[saved], ours.ram[saved]) == (0x05, 0x08)
    assert _at(LOWER_DRIVER_SAVE) == "moveml %d3-%d7/%a3-%fp,0xa28" and saved == 0xa28 + 3 * LONG_BYTES + 3


LOWER_DRIVER_SAVE = 0xfc1c48            # the lower driver's common entry: `movem.l d3-d7/a3-a6,$a28`


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_b4_s_open_carry_closes_a3_a4_a6_are_the_capture_s(machine):
    """B4's OPEN CARRY: A3, A4 and A6 at `$fc047a` reach the pre-init machine (the BIOS process's basepage). On both shores,
    from the ROM's machine at `$fc0452`, they are the capture's: A6 the ACSI probe's answer (its `lea $ffff8606,a6`), A3
    the RS232 table B3's ROM init leaves ($fc2522 `movea.l #$fc25a0,a3` — which B3's C does NOT leave: owed there), A4
    what the ROM's routines before $fc0452 leave."""
    capture = boot.midboot_machine()
    for shore in (bl.the_rom_s(machine), bl.our_side(machine)):
        held = shore.slice.machine.registers
        assert {name: held[name] for name in ("a3", "a4", "a6")} == {name: capture.registers[name] for name in ("a3", "a4", "a6")}
    assert _at(RS232_TABLE_LOADED) == f"moveal #{C['ROM_RS232_HANDLER_TABLE']},%a3" and capture.registers["a3"] == C["ROM_RS232_HANDLER_TABLE"]


def test_the_warm_machine_is_no_power_on_s_and_differs_where_its_ram_was_the_desk_s():
    """WHY THE END SURFACE IS COLD's: WARM keeps the RAM the head's clears do not reach — the post-boot snapshot's
    (a desk's) above $10000 and the shell's environment at $840 — where the capture's power-on holds zeros."""
    capture = boot.midboot_machine()
    _registers, differing = bl.against_the_capture(bl.our_side(boot.WARM), capture)
    assert any(at >= 0x10000 for at in differing) and any(0x840 <= at < 0x850 for at in differing)


# ---- EACH SURFACE'S NEGATIVE ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cold_pair():
    return bl.the_rom_s(boot.COLD), bl.our_side(boot.COLD)


def _with_slice(shore, **changes):
    return shore._replace(slice=shore.slice._replace(**changes))


def _ram_changed(shore, at, value):
    ram = bytearray(shore.slice.machine.ram)
    ram[at] = value
    return _with_slice(shore, machine=shore.slice.machine._replace(ram=bytes(ram)))


def _registers_changed(shore, **changes):
    return _with_slice(shore, machine=shore.slice.machine._replace(registers={**shore.slice.machine.registers, **changes}))


def test_each_held_surface_changed_alone_is_named(cold_pair):
    the_rom_s, ours = cold_pair
    changed = {
        "stop": _with_slice(ours, stop=bl.SPAN[0]),
        "registers": _registers_changed(ours, d2=ours.slice.machine.registers["d2"] ^ 1),
        "ram": _ram_changed(ours, addrs.GEMDOS_DATE, ours.slice.machine.ram[addrs.GEMDOS_DATE] ^ 1),
        "stored": _with_slice(ours, stored=(*ours.slice.stored, (bl.STACK_RESIDUE[0] - 2, 1))),
        **{ledger: _with_slice(ours, **{ledger: (*getattr(ours.slice, ledger), ("a staged entry",))}) for ledger in bl.LEDGERS},
        "fdc_chip": _with_slice(ours, fdc_chip=bytes(len(ours.slice.fdc_chip))),
        "answers": ours._replace(answers=ours.answers[:-1]),
    }
    assert set(changed) == {*bl.SURFACES, "answers"}
    for surface, shore in changed.items():
        found = bl.differences(the_rom_s, shore)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


@pytest.mark.parametrize("register", boot.REGISTER_NAMES)
def test_every_register_is_held(cold_pair, register):
    the_rom_s, ours = cold_pair
    found = bl.differences(the_rom_s, _registers_changed(ours, **{register: ours.slice.machine.registers[register] ^ 1}))
    assert len(found) == 1 and found[0].startswith("registers")


def test_the_residue_alone_is_not_held(cold_pair):
    """A byte just above and just below the residue is seen; one inside it is not."""
    the_rom_s, ours = cold_pair
    lo, hi = bl.STACK_RESIDUE
    for at, seen in ((lo - 1, True), (lo, False), (hi - 1, False), (hi, True)):
        found = bl.differences(the_rom_s, _ram_changed(ours, at, ours.slice.machine.ram[at] ^ 0xff))
        assert bool(found) == seen, (hex(at), found)


# ---- ITS PRICE (ruling D9): the table's rows ------------------------------------------------------------------------------
def test_the_table_prices_both_machines_on_each_shore_s_own_cycles_under_the_bar():
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_late_slice(row)]
    assert [row.registered for row in rows] == list(bl.SLICES)
    bench = tier3.RomBench()
    for row in rows:
        machine = bl.SLICES[row.registered]
        assert (row.entry, row.symbol) == (bl.SPAN[0], bl.ENTRY_SYMBOL)
        priced, measured = bl.priced(machine), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


class _OursOwnReadShort:
    emu = bl.emu

    def __getattr__(self, name):
        return getattr(self.emu, name)

    def prof_cycles(self, lo, hi):
        return self.emu.prof_cycles(lo, hi) - (4 if lo == bl.product().base else 0)


def test_the_rest_beside_each_shore_s_own_is_held_equal_in_the_price(monkeypatch):
    monkeypatch.setattr(bl, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="beside its own, ours spent"):
        bl.priced(boot.COLD)


# ---- THE CARRIES (R-D4-2) AND THE DRIVE ARMS (R-D4-3), from the ROM's own runs ---------------------------------------------
PORT_A_AFTER_B3 = 0x27                  # the head's `$07` through B3's own RMWs: DTR, RTS cleared, the strobe set


@pytest.mark.parametrize("machine", bl.MACHINES)
def test_port_a_at_the_slice_s_start_is_carried_from_the_rom_s_own_stores(machine):
    """PSG port A at `$fc0452` is the ROM's chained boot's (the head's store through B3's RMWs) — not B3's battery seed,
    which declares another byte — and D2 at `$fc047a` (port A before the driver's last select) is then the capture's."""
    import boot_hwinit
    assert bl.port_a_at_start(machine) == PORT_A_AFTER_B3
    assert boot_hwinit.PSG_SEED[addrs.PSG_PORT_A] != PORT_A_AFTER_B3
    assert bl.the_rom_s(machine).slice.machine.registers["d2"] == boot.midboot_machine().registers["d2"]


def test_the_chip_and_port_a_are_carried_leg_to_leg():
    """Every leg is a run: the chip a leg leaves is the chip the next starts from (R-D4-2) — the joined ledger in the
    ROM's own order across the legs, and the chip the shores leave equal (and not MR's)."""
    rom, ours = bl.the_rom_s(boot.COLD), bl.our_side(boot.COLD)
    assert rom.slice.fdc_chip == ours.slice.fdc_chip != bl.emu.fdc_power_on_state()
    commands = [entry for entry in rom.slice.fdc_events if entry[0] == "command"]
    # A: restore, the exit's seek; B: restore, seek; hdv_boot's Floprd: seek-verify, read, the exit's seek — in order
    assert [entry[1] for entry in commands] == [bl.WD1772_RESTORE, bl.WD1772_SEEK, bl.WD1772_RESTORE, bl.WD1772_SEEK,
                                                bl.WD1772_SEEK_VERIFY, bl.WD1772_READ_SECTOR, bl.WD1772_SEEK]
    assert [entry[2] >> bl.FDC_DRIVE_SHIFT for entry in commands] == [0, 0, 1, 1, 0, 0, 0]


# THE ARMS, each from the ROM's runs on both shores, held equal, each with its ledger: the drives the ROM counts, and the
# timeouts the ROM's own count-down reaches (`(command, polls)` per hang); their instructions pinned (the ROM's shore).
ARMS = {bl.B_ABSENT: dict(nflops=1, timeouts=(), instructions=17_008),
        bl.A_ABSENT: dict(nflops=0, timeouts=((bl.WD1772_RESTORE, FLOPPY_SPIN_UP_COUNT - 1),), instructions=1_587_388),
        bl.A_EMPTY: dict(nflops=1, timeouts=((bl.WD1772_RESTORE, FLOPPY_SPIN_UP_COUNT - 1),
                                             *[(bl.WD1772_SEEK_VERIFY, FLOPPY_WAIT_COUNT - 1)] * 4),
                         instructions=5_785_168)}


@pytest.fixture(scope="module", params=sorted(ARMS))
def arm_pair(request):
    return request.param, bl.the_rom_s(boot.COLD, drive_arm=request.param), bl.our_side(boot.COLD, drive_arm=request.param)


def test_each_drive_arm_is_held_equal_and_reached_by_the_rom_s_own_count(arm_pair):
    arm, rom, ours = arm_pair
    expected = ARMS[arm]
    assert bl.differences(rom, ours) == []
    assert case.word_in(rom.slice.machine.ram, SYSVAR_NFLOPS) == expected["nflops"]
    events = rom.slice.fdc_events
    hangs = [entry[1] for entry in events if entry[0] == "hang"]
    long_polls = [entry[2] for entry in events if entry[0] == "poll" and entry[2] > 1]
    assert len(hangs) == len(long_polls) == len(expected["timeouts"])          # (the zip below cannot truncate)
    assert list(zip(hangs, long_polls)) == list(expected["timeouts"])
    assert len([entry for entry in events if entry[0] == "forced"]) == len(expected["timeouts"])
    assert rom.slice.instructions == expected["instructions"]


def test_drive_b_absent_s_restore_ends_in_the_seek_error():
    """The motor on (A:'s probe turned it on), B:'s restore steps 255 times with no TR00: the seek error, twice (the
    probe's retry after its seek to 10), and the probe fails."""
    events = bl.the_rom_s(boot.COLD, drive_arm=bl.B_ABSENT).slice.fdc_events
    drive_b = 1 << bl.FDC_DRIVE_SHIFT
    b_restores = [index for index, entry in enumerate(events)
                  if entry[0] == "command" and entry[1:] == (bl.WD1772_RESTORE, drive_b)]
    assert [events[index + 1] for index in b_restores] == [("done", bl.WD1772_SEEK_ERROR, 0)] * 2


def test_a_drive_arm_on_one_shore_alone_is_named():
    """THE FDC LEDGER IS A SURFACE: the ROM's on the capture's drives, ours with B: absent — its transactions named (and the
    megabyte: one drive counted). The chip alone is the each-surface negative's (both arms leave drive A:'s seek last)."""
    found = bl.differences(bl.the_rom_s(boot.COLD), bl.our_side(boot.COLD, drive_arm=bl.B_ABSENT))
    assert any(item.startswith("fdc_events") for item in found) and any(item.startswith("ram") for item in found)
