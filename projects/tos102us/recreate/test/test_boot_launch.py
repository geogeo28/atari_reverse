"""BOOT B4 HELD (`test/boot_launch.py`, `src/boot/launch/`): the boot's last slice `[$fc047a, gem_entry)` and its AUTO
runner `$fc0c4a` (with the process `$fc0cae` it launches) — the ROM's own against OURS, THE .S THAT SHIPS (the ROM's
bytes, pinned where they are laid: ruling R-B4-1) AND ITS C TWIN, both from THE MID-BOOT MACHINE
(ruling D8, A LABELLED STAGING) with a disk in the drive, our side laid over the ROM window (rulings "ROM-window
overlay", "Own link rule"). Every observable surface held but what is named — each name proved here: the scratch by the
registers that differ, the dead classes by noise through the ROM's own continuation to gem_entry, the linked addresses
by their mapping alone; the launch's END SURFACE held to the pre-init capture of the same disk. Each surface's negative
is here; the price is the table's (ruling D9), our own cost pinned exactly below."""
import functools
import re
import struct
import subprocess

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_boot
import boot
import boot_floppy
import boot_launch as bl
import case
import midboot_snapshot
import preinit_snapshot
import rom_data
import transcription
from transcription import Laid, PC_RELATIVE, Relocated
from boot_snapshot import differing_fields

C = bl.CONSTANTS
HEAD = bl.layouts.parse_constants((bl.RECREATE / "include" / "boot" / "head.h",))
LONG_BYTES, WORD_BYTES = bl.LONG_BYTES, bl.WORD_BYTES
NOISE_SEEDS = (0, 1, 2)
LAUNCHES = tuple(name for name, each in bl.SLICES.items() if each.kind == bl.LAUNCH)
RUNNERS = tuple(name for name, each in bl.SLICES.items() if each.kind == bl.AUTO_RUNNER_KIND)
CAPTURED = tuple(name for name in LAUNCHES if bl.SLICES[name].disk in bl.CAPTURED)
WHICH = (bl.SHIPPED, bl.TWIN)
# THE SCRATCH, pinned literally (a name added to `NOT_HELD` would loosen the compare in silence).
SCRATCH = {bl.SHIPPED: {bl.LAUNCH: set(), bl.AUTO_RUNNER_KIND: set()},
           bl.TWIN: {bl.LAUNCH: set(), bl.AUTO_RUNNER_KIND: {"d1", "d7", "a0", "a1", "a2"}}}
# OUR OWN COST, PINNED EXACTLY: `(our instructions beyond the ROM's, our own cycles)`. THE .S's IS THE ROM'S (0 more, its
# own cycles equal); THE TWIN's — cycles are the only surface its glue's arms no row reaches have (the boot drive
# missing, `_cmdload`) and its copies' loop shapes.
OUR_OWN_COST = {
    bl.SHIPPED: {"boot launch B4, BLANK": (0, 1776), "boot launch B4, DESKTOP.INF": (0, 1776),
                 "boot launch B4, FILES": (0, 1776), "boot launch B4, ONE PROGRAM": (0, 2412),
                 "boot launch B4, PEXEC FAILS": (0, 2456), "boot AUTO runner B4, BLANK": (0, 870),
                 "boot AUTO runner B4, NO PROGRAM": (0, 870), "boot AUTO runner B4, ONE PROGRAM": (0, 1506),
                 "boot AUTO runner B4, PEXEC FAILS": (0, 1550)},
    bl.TWIN: {"boot launch B4, BLANK": (78, 2352), "boot launch B4, DESKTOP.INF": (78, 2352),
              "boot launch B4, FILES": (78, 2352), "boot launch B4, ONE PROGRAM": (99, 3104),
              "boot launch B4, PEXEC FAILS": (101, 3156), "boot AUTO runner B4, BLANK": (30, 1158),
              "boot AUTO runner B4, NO PROGRAM": (30, 1158), "boot AUTO runner B4, ONE PROGRAM": (51, 1910),
              "boot AUTO runner B4, PEXEC FAILS": (53, 1962)},
}
ONE_PROGRAM_ROWS = tuple(name for name, each in bl.SLICES.items() if each.disk == bl.ONE_PROGRAM)
# THE LOWER FLOPPY DRIVER'S CYCLES IN EACH ROW (D4 P5a): `(ours, the ROM's)` — our body and its jumps against the ROM's
# whole driver text, on either product of the launch (the driver is the same pieces beside both). Priced in no column of
# the row (ruling R-P5-4: the natural calls are no rows of their own; their cost shows in the chain rows), so PINNED here,
# exactly: two, three, five or four one-sector Floprds a row (the boot sector's log-in, the FAT, the root, a program).
FLOPRDS = {2: (24652, 24576), 3: (36978, 36864), 4: (49304, 49152), 5: (61630, 61440)}
FLOPRDS_OF = {"boot launch B4, BLANK": 2, "boot launch B4, DESKTOP.INF": 2, "boot launch B4, FILES": 3,
              "boot launch B4, ONE PROGRAM": 5, "boot launch B4, PEXEC FAILS": 4, "boot AUTO runner B4, BLANK": 2,
              "boot AUTO runner B4, NO PROGRAM": 3, "boot AUTO runner B4, ONE PROGRAM": 5,
              "boot AUTO runner B4, PEXEC FAILS": 4}
OUR_DRIVER = {name: FLOPRDS[count] for name, count in FLOPRDS_OF.items()}
FLOPRD_COMMANDS = (0x17, 0x80, 0x13)    # each one-sector Floprd's: seek-verify, read sector, the exit's seek
MOTOR_OFF_STATUS = (0xff8604, 0x04)    # the FDC status register read with the motor off (MR's chip)
MOTOR_ON_STATUS = (0xff8604, 0xa4)     # ...and with B6's carried chip: the motor on, spun up (and the track-0 bit)
OUR_FLOPRD_EXTRA_INSNS = 21             # ...and the instructions our driver's one-sector Floprd takes beyond the ROM's (measured)


@functools.cache
def the_rom_s(name):
    return bl.the_rom_s(bl.SLICES[name])


@functools.cache
def pair(name, which=bl.SHIPPED):
    return the_rom_s(name), bl.our_side(bl.SLICES[name], which=which)


# ---- THE ROM'S TEXT: every constant the C and the harness are spelt in, read off the instruction that uses it ------------
def texts(lo, hi):
    return [text for _at, text in rom_data.instructions(lo, hi) if text]


def operands(lo, hi):
    return {operand.value for operand in rom_data.text_operands(lo, hi)}


def test_the_slices_are_spelt_in_the_rom_s_own_operands():
    """Each constant of `boot/launch.h` the slice uses, as the instruction that uses it reads in the ROM's listing — and
    the harness's own addresses: the launch's text from `tst.w _cmdload` to its `jmp`, the runner and its process."""
    launch = texts(*bl.LAUNCH_SPAN)
    runner = texts(*bl.AUTO_RUNNER_SPAN)
    for expected in (f"tstw 0x{C['SYSVAR_CMDLOAD']:x}", f"bsrw 0x{bl.AUTO_RUNNER:x}",
                     f"moveal #{C['BOOT_ENVIRONMENT']},%a1", f"cmpib #{C['ENVIRONMENT_DRIVE_MARK']},%a0@",
                     f"moveb 0x{C['SYSVAR_BOOTDEV']:x},%d0", f"addb #{C['DRIVE_LETTER_A']},%d0",
                     f"movew #{C['LAUNCH_PEXEC_JUST_GO']},%sp@-", f"movew #{addrs.GEMDOS_PEXEC_FN},%sp@-",
                     f"addaw #{C['PEXEC_FRAME_BYTES'] - C['LAUNCH_STRAY_WORD']},%sp",
                     f"movel 0x{HEAD['SYSVAR_EXEC_OS']:x},%a0@({addrs.BASEPAGE_TBASE})",
                     f"jmp 0x{C['ROM_RESET_ENTRY']:x}"):
        assert expected in launch, expected
    assert launch[-1] == f"jmp 0x{C['ROM_RESET_ENTRY']:x}" and bl.LAUNCH_SPAN[1] == C["ROM_ENVIRONMENT_TEMPLATE"]
    for expected in (f"movel %sp@+,0x{C['AUTO_RETURN']:x}", f"movel %a0,%a5@({C['AUTO_PATH']})",
                     f"movel %a1,%a5@({C['AUTO_PATTERN']})", f"movew #{C['LAUNCH_PEXEC_JUST_GO']},%sp@-",
                     f"movel #{bl.AUTO_PROCESS},%a0@({addrs.BASEPAGE_TBASE})", "movel %a3,%sp@-", f"movew #{addrs.GEMDOS_SUPER_FN},%sp@-",
                     f"lea %a5@({C['AUTO_PROCESS_BYTES']}),%sp", f"movel #{C['AUTO_PROCESS_BYTES']},%sp@-",
                     f"movew #{C['GEMDOS_MSHRINK_FN']},%sp@-", f"movew #{C['AUTO_SEARCH_ATTRIBUTES']},%sp@-",
                     f"pea 0x{C['AUTO_DTA']:x}", f"movew #{addrs.GEMDOS_FSETDTA_FN},%sp@-",
                     f"movew #{addrs.GEMDOS_FSFIRST_FN},%sp@-", f"movew #{addrs.GEMDOS_FSNEXT_FN},%sp@-",
                     f"lea 0x{C['AUTO_PROGRAM_NAME']:x},%a1", f"lea 0x{C['AUTO_DTA'] + bl.DTA_NAME:x},%a0",
                     f"lea 0x{HEAD['HEAD_BIOS_STACK_TOP']:x},%sp"):
        assert expected in runner, expected
    assert {C["ROM_AUTO_PATH"], C["ROM_AUTO_PATTERN"], C["ROM_EMPTY_STRING"]} <= operands(*bl.AUTO_RUNNER_SPAN)
    assert {C["ROM_ENVIRONMENT_TEMPLATE"], C["ROM_COMMAND_PRG"], C["ROM_EMPTY_STRING"], addrs.ROM_BASE} <= operands(*bl.LAUNCH_SPAN)
    assert texts(bl.SHELL_ARM_CALLS_THE_RUNNER, bl.SHELL_ARM_AUTO_RAN) == [f"bsrw 0x{bl.AUTO_RUNNER:x}"]
    assert runner[runner.index(f"movew #{addrs.GEMDOS_SUPER_FN},%sp@-") + 2] == "addqw #6,%sp"
    assert texts(bl.AUTO_SUPER_RETURN, bl.AUTO_SUPER_RETURN + WORD_BYTES) == ["addqw #6,%sp"]


def test_the_strings_are_where_the_slice_reads_them():
    """The ROM's strings, read in place (TABLE obligations): the environment's template — ONE drive mark, ended by its
    first byte with the top bit set — the `_cmdload` arm's program, the empty string, the AUTO search path and its
    pattern."""
    def text(at, end=b"\0"):
        return bytes(BASE_IMAGE[at:BASE_IMAGE.index(end, at) + len(end)])
    template = bytes(BASE_IMAGE[C["ROM_ENVIRONMENT_TEMPLATE"]:C["ROM_COMMAND_PRG"]])
    assert template == b"PATH=\0#:\\\0\0\xff" and template.count(bytes((C["ENVIRONMENT_DRIVE_MARK"],))) == 1
    assert [byte for byte in template if byte & 0x80] == [template[-1]]
    assert text(C["ROM_COMMAND_PRG"]) == b"COMMAND.PRG\0" and text(C["ROM_EMPTY_STRING"]) == b"\0"
    assert text(C["ROM_AUTO_PATH"]) == b"\\AUTO\\*.PRG\0" and text(C["ROM_AUTO_PATTERN"]) == b"*.PRG\0"


def test_the_glue_s_pexec_modes_are_gemdos_s():
    process = bl.layouts.parse_constants((bl.PROCESS_H,))
    assert (C["LAUNCH_PEXEC_LOAD_AND_GO"], C["LAUNCH_PEXEC_JUST_GO"]) == (process["PEXEC_LOAD_AND_GO"], process["PEXEC_JUST_GO"])


def test_the_floppy_driver_s_own_state_is_where_its_instructions_keep_it():
    lo, hi = bl.FLOPPY_LOWER_DRIVER_STATE
    driver = texts(0xfc1c48, 0xfc1c98)
    assert f"st 0x{lo:x}" in driver and "moveml %d3-%d7/%a3-%fp,0xa28" in driver
    assert texts(0xfc1746, 0xfc174c) == [f"lea 0x{hi - LONG_BYTES:x},%a1"]


# ---- THE .S: THE ROM'S OWN BYTES, PINNED WHERE THEY ARE LAID (ruling R-B4-1; the head's precedent, B1) ------------------
# The .S lays [$fc047a, $fc0d50) as the ROM lays it, the bytes between the launch and the runner FILLED (so both `bsr`s
# to the runner are the ROM's words). THREE REGIONS, pinned at their laid addresses: the launch, and the runner around
# THE ONE LONGWORD OURS — `move.l #<the process's text>,8(a0)`'s immediate, our linked entry (held below).
LAUNCH_LO, LAUNCH_HI = C["ROM_LAUNCH"], C["ROM_LAUNCH_END"]
RUNNER_LO, RUNNER_HI = C["ROM_AUTO_RUNNER"], C["ROM_AUTO_RUNNER_END"]
OURS_LONGWORD = 0xfc0c8c                 # the immediate of `move.l #$fc0cae,8(a0)` ($fc0c8a)


def _laid_at(rom):
    return C["LAUNCH_LAID_AT"] + rom - LAUNCH_LO


def _shipped():
    product = bl.product(bl.SHIPPED)
    return product.base, product.code


REGIONS = (transcription.pinned_region(LAUNCH_LO, LAUNCH_HI, bl.ENTRY_SYMBOL, laid=Laid(_laid_at(LAUNCH_LO), _shipped)),
           transcription.pinned_region(RUNNER_LO, OURS_LONGWORD, bl.ENTRY_SYMBOL, laid=Laid(_laid_at(RUNNER_LO), _shipped)),
           transcription.pinned_region(OURS_LONGWORD + LONG_BYTES, RUNNER_HI, bl.ENTRY_SYMBOL,
                                       laid=Laid(_laid_at(OURS_LONGWORD + LONG_BYTES), _shipped)))
D16_PC_OPERAND = re.compile(r"%pc@\((0x[0-9a-f]+)\)")


def _in_the_spans(address):
    return LAUNCH_LO <= address < LAUNCH_HI or RUNNER_LO <= address < RUNNER_HI


def _references_leaving_the_spans():
    """`{extension word: (ROM target, the instruction)}`: every pc-relative operand of the two spans whose target lies
    outside both — DERIVED from the ROM's text; its displacement is the instruction's last word."""
    found = {}
    for lo, hi in ((LAUNCH_LO, LAUNCH_HI), (RUNNER_LO, RUNNER_HI)):
        decoded = rom_data.instructions(lo, hi)
        for (site, text), (after, _next) in zip(decoded, [*decoded[1:], (hi, None)]):
            for target in (int(each, 16) for each in D16_PC_OPERAND.findall(text or "")):
                if not _in_the_spans(target):
                    found[after - WORD_BYTES] = (target, text)
    return found


LEAVING = _references_leaving_the_spans()
RELOCATED = {at: Relocated(PC_RELATIVE, None, f"{text}: the ROM's ${target:x} in place", in_place=True)
             for at, (target, text) in LEAVING.items()}


def test_the_references_leaving_the_spans_are_the_rom_s_strings_alone():
    """DERIVED, then held to `boot/launch.h`: eleven operands, each one of the strings the slice reads in place."""
    targets = {target for target, _text in LEAVING.values()}
    assert len(LEAVING) == 11 and targets == {C["ROM_ENVIRONMENT_TEMPLATE"], C["ROM_COMMAND_PRG"],
                                              C["ROM_EMPTY_STRING"], C["ROM_AUTO_PATH"], C["ROM_AUTO_PATTERN"]}


@pytest.mark.parametrize("region", REGIONS, ids=lambda region: f"{region.lo:x}")
def test_the_s_is_the_rom_s_bytes_where_it_is_laid(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


def test_a_reference_left_out_is_seen():
    left_out = dict(RELOCATED)
    left_out.pop(min(left_out))
    with pytest.raises(AssertionError, match="against the ROM's"):
        transcription.assert_transcribed(REGIONS[0], relocated=left_out)


def test_the_one_longword_ours_is_our_linked_process_entry_and_the_rest_is_filled():
    """THE LONGWORD THE PINS LEAVE OUT holds our process entry where the ROM's holds `$fc0cae` (mapped back by the
    comparison); the bytes between the launch and the runner are the fill, and every symbol lies where the ROM has it."""
    product = bl.product(bl.SHIPPED)
    at = _laid_at(OURS_LONGWORD) - product.base
    assert case.long_in(BASE_IMAGE, OURS_LONGWORD) == bl.AUTO_PROCESS
    assert case.long_in(product.code, at) == product.symbols[bl.OUR_AUTO_PROCESS] == _laid_at(bl.AUTO_PROCESS)
    assert not any(product.code[_laid_at(LAUNCH_HI) - product.base:_laid_at(RUNNER_LO) - product.base])
    assert len(product.code) == RUNNER_HI - LAUNCH_LO
    for symbol, rom in ((bl.ENTRY_SYMBOL, LAUNCH_LO), (bl.OUR_RUNNER_CALL, bl.SHELL_ARM_CALLS_THE_RUNNER),
                        (bl.OUR_AUTO_RAN, bl.SHELL_ARM_AUTO_RAN), ("boot_auto_runner_entry", RUNNER_LO),
                        (bl.OUR_SUPER_RETURN, bl.AUTO_SUPER_RETURN)):
        assert product.symbols[symbol] == _laid_at(rom), symbol


def test_every_in_place_target_is_in_reach_of_a_word_displacement():
    """Why the .S is laid where it is: every target it reaches in place is within a signed 16-bit displacement."""
    for at, (target, _text) in LEAVING.items():
        assert -0x8000 <= target - _laid_at(at) < 0x8000


# ---- THE PRODUCT ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("which,laid_at", ((bl.SHIPPED, "LAUNCH_LAID_AT"), (bl.TWIN, "LAUNCH_TWIN_LAID_AT")))
def test_each_product_is_laid_in_the_rom_window_over_no_code_the_slice_runs(which, laid_at):
    product, laid = bl.product(which), bl.overlay(which=which)
    lo, hi = bl.our_span(laid)
    assert (lo, product.base) == (C[laid_at], C[laid_at]) and hi - lo == len(product.code)
    assert boot.ROM_WINDOW[0] <= lo < hi <= boot.ROM_WINDOW[1] and hi <= aes.AES_TEXT[0]
    for span in (*bl.THE_ROM_S_SPANS, bl.our_span(bl.overlay(which=next(each for each in WHICH if each != which)))):
        assert span[1] <= lo or hi <= span[0]


def test_the_c_names_none_of_the_registers_the_bios_frames():
    """THE FIXED REGISTERS (the Makefile's `-ffixed-*`): no instruction of the C names D3-D7 or A3-A6 — the BIOS frames
    exactly those in RAM on every disk call GEMDOS makes for its traps. (The glue's own A3/A4/A5 are the ROM's.)"""
    symbols = bl.product(bl.TWIN).symbols
    c_functions = sorted(at for name, at in symbols.items() if name in (
        "boot_auto_runner", "boot_auto_process", "boot_launch_sysbase", "boot_launch_gem", "environment_laid",
        "program_path_laid"))
    lo, hi = c_functions[0], bl.our_span(bl.overlay(which=bl.TWIN))[1]
    listing = subprocess.run(["m68k-elf-objdump", "-d", str(bl.product(bl.TWIN).elf), f"--start-address={lo}",
                              f"--stop-address={hi}"], capture_output=True, text=True, check=True).stdout
    named = [line for line in listing.splitlines() if any(f"%{reg}" in line for reg in (
        "d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6", "fp"))]
    assert "boot_launch_gem" in listing and not named, named


# ---- TIER 1: EVERY ROW, EVERY HELD SURFACE ----------------------------------------------------------------------------------
@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", tuple(bl.SLICES))
def test_ours_is_the_rom_s_on_every_held_surface(name, which):
    """Every held surface equal and the rest equal — through `priced_pair`, tier 3's own pricing (refused by name)."""
    the_rom_s, ours = pair(name, which)
    bl.priced_pair(bl.SLICES[name], the_rom_s, ours, which)


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", tuple(bl.SLICES))
def test_our_lower_driver_s_cycles_are_pinned_exactly_and_its_calls_are_the_one_sector_floprds(name, which):
    """D4 P5a: every row runs OUR lower floppy driver on our shore (the ROM's on its own) — its cycles pinned, and its
    calls, off the FDC model's ledger, each a one-sector Floprd (the commands `FLOPRD_COMMANDS`), as many as the pin says."""
    the_rom_s, ours = pair(name, which)
    assert (ours.driver, the_rom_s.driver) == OUR_DRIVER[name]
    commands = [entry[1] for entry in ours.fdc_events if entry[0] == "command"]
    assert commands == list(FLOPRD_COMMANDS) * FLOPRDS_OF[name]


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", tuple(bl.SLICES))
def test_our_own_cost_is_pinned_exactly(name, which):
    the_rom_s, ours = pair(name, which)
    beyond = ours.instructions - the_rom_s.instructions - OUR_FLOPRD_EXTRA_INSNS * FLOPRDS_OF[name]     # (D4 P5a: the driver's)
    assert (beyond, ours.own) == OUR_OWN_COST[which][name]


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", tuple(bl.SLICES))
def test_unmapped_the_megabyte_differs_at_our_linked_longwords_alone(name, which):
    """THE MAPPING'S NEGATIVE: without it, the only megabyte difference is the linked longwords, each holding ours (a
    copy on the process's stack a program's own stack lies over excepted: `bl.ON_THE_PROCESS_STACK`)."""
    the_rom_s, ours = pair(name, which)
    kind = bl.SLICES[name].kind
    links = bl.linked(kind, which)
    ram = bl._frame_pointer_held(the_rom_s, ours, [], which) if kind == bl.AUTO_RUNNER_KIND else ours.ram
    differing = {at for start, length in differing_fields(bl.masked(ram), bl.masked(the_rom_s.ram))
                 for at in range(start, start + length)}
    linked = {}
    for link, (where, value, _the_rom_s) in links.items():
        at = where(ours.ram)
        if link in bl.ON_THE_PROCESS_STACK and case.long_in(ours.ram, at) != value:
            assert bl.SLICES[name].disk == bl.ONE_PROGRAM, f"{link} is gone where no program ran"
            continue
        linked[at] = value
        assert case.long_in(ours.ram, at) == value
    assert differing and differing <= {at + offset for at in linked for offset in range(LONG_BYTES)}


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", RUNNERS)
def test_not_held_is_exactly_what_differs(name, which):
    """THE SCRATCH AT THE RUNNER'S RETURN is the registers that differ — over the arms, exactly `SCRATCH`."""
    the_rom_s, ours = pair(name, which)
    differing = {reg for reg in boot.REGISTER_NAMES if reg != "pc" and the_rom_s.registers[reg] != ours.registers[reg]}
    assert differing <= SCRATCH[which][bl.AUTO_RUNNER_KIND] == set(bl.NOT_HELD[which][bl.AUTO_RUNNER_KIND])


@pytest.mark.parametrize("which", WHICH)
def test_the_scratch_over_every_arm_is_every_name_of_it(which):
    union = set()
    for name in RUNNERS:
        the_rom_s, ours = pair(name, which)
        union |= {reg for reg in boot.REGISTER_NAMES if reg != "pc" and the_rom_s.registers[reg] != ours.registers[reg]}
    assert union == SCRATCH[which][bl.AUTO_RUNNER_KIND] and SCRATCH[which][bl.LAUNCH] == set(bl.NOT_HELD[which][bl.LAUNCH])


# ---- EACH SURFACE'S NEGATIVE ----------------------------------------------------------------------------------------------
NEGATIVE_LAUNCH, NEGATIVE_RUNNER = "boot launch B4, BLANK", "boot AUTO runner B4, PEXEC FAILS"


def _ram_changed(launch, at, value):
    ram = bytearray(launch.ram)
    ram[at] = value
    return launch._replace(ram=bytes(ram))


SURFACE_CHANGES = {
    "the stop": lambda launch: launch._replace(stop=launch.stop + WORD_BYTES),
    "the register d3": lambda launch: launch._replace(registers={**launch.registers, "d3": launch.registers["d3"] ^ 1}),
    "the register sr": lambda launch: launch._replace(registers={**launch.registers, "sr": launch.registers["sr"] ^ 1}),
    "the megabyte outside the pre-init mask": lambda launch: _ram_changed(launch, C["BOOT_ENVIRONMENT"],
                                                                         launch.ram[C["BOOT_ENVIRONMENT"]] ^ 1),
    "the addresses stored outside the mask": lambda launch: launch._replace(stored=launch.stored + ((0xe000, 1),)),
    "the fdc_events": lambda launch: launch._replace(fdc_events=launch.fdc_events[:-1]),
    "the fdc_chip": lambda launch: launch._replace(fdc_chip=launch.fdc_chip[:-1] + bytes((launch.fdc_chip[-1] ^ 1,))),
    "the port_a": lambda launch: launch._replace(port_a=launch.port_a ^ 1),
    "the blanks": lambda launch: launch._replace(blanks=launch.blanks + 1),
    "the gemdos": lambda launch: launch._replace(gemdos=launch.gemdos[:-1]),
    "the io_reads": lambda launch: launch._replace(io_reads=launch.io_reads + ((0xff8260, 1, 0),)),
    "the hardware_reads": lambda launch: launch._replace(hardware_reads=launch.hardware_reads + ((0xfffc00, 2),)),
    "the hardware_writes": lambda launch: launch._replace(hardware_writes=launch.hardware_writes + ((0xfffc02, 1, 0),)),
    "the clock": lambda launch: launch._replace(clock=launch.clock + 1),
}


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", (NEGATIVE_LAUNCH, NEGATIVE_RUNNER))
@pytest.mark.parametrize("surface", tuple(SURFACE_CHANGES))
def test_each_held_surface_changed_alone_is_named(name, surface, which):
    the_rom_s, ours = pair(name, which)
    kind = bl.SLICES[name].kind
    found = bl.differences(the_rom_s, SURFACE_CHANGES[surface](ours), kind, bl.linked(kind, which), which)
    assert len(found) == 1 and found[0].startswith(surface), found


def test_noise_inside_the_pre_init_mask_is_not_held_and_outside_it_is():
    the_rom_s, ours = pair(NEGATIVE_LAUNCH)
    inside = [(lo, lo + size) for lo, size, _why in preinit_snapshot.MASK]
    noisy_inside = ours._replace(ram=aes_boot.noise_over(ours.ram, inside, NOISE_SEEDS[0]))
    noisy_outside = ours._replace(ram=aes_boot.noise_over(ours.ram, [(0xe000, 0xe010)], NOISE_SEEDS[0]))
    links = bl.linked(bl.LAUNCH)
    assert bl.differences(the_rom_s, noisy_inside, bl.LAUNCH, links) == []
    assert bl.differences(the_rom_s, noisy_outside, bl.LAUNCH, links)[0].startswith("the megabyte")


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("deeper", (-1, 1))
def test_the_auto_frame_pointer_one_byte_off_is_named(deeper, which):
    the_rom_s, ours = pair(NEGATIVE_RUNNER, which)
    at = bl.frame_pointer_at(the_rom_s.ram)
    ram = bytearray(ours.ram)
    struct.pack_into(">I", ram, at, case.long_in(ours.ram, at) + deeper)
    found = bl.differences(the_rom_s, ours._replace(ram=bytes(ram)), bl.AUTO_RUNNER_KIND,
                           bl.linked(bl.AUTO_RUNNER_KIND, which), which)
    assert len(found) == 1 and found[0].startswith("the AUTO process's frame pointer")


def test_a_linked_longword_holding_neither_address_is_refused():
    the_rom_s, ours = pair(NEGATIVE_LAUNCH)
    with pytest.raises(AssertionError, match="neither ours"):
        bl.differences(the_rom_s, _ram_changed(ours, C["AUTO_RETURN"] + 1, 0x55), bl.LAUNCH, bl.linked(bl.LAUNCH))


# ---- WHO RAN ------------------------------------------------------------------------------------------------------------
JMP_ABSOLUTE_LONG = 0x4ef9


def test_ours_that_runs_the_rom_s_own_launch_is_refused_by_name():
    """THE FALSE GREEN: an overlay that jumps into the ROM's own launch would arrive at gem_entry with the ROM's own
    machine — refused, off the run's profile."""
    code = struct.pack(">HI", JMP_ABSOLUTE_LONG, boot.MIDBOOT) + bl.product().code[6:]
    with pytest.raises(AssertionError, match="executed"):
        bl.our_side(bl.SLICES[NEGATIVE_LAUNCH], code=code)


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("name", (NEGATIVE_LAUNCH, NEGATIVE_RUNNER, "boot launch B4, ONE PROGRAM"))
def test_the_rom_s_shore_is_the_same_run_with_and_without_the_overlay(name, which):
    """The spans each product is laid over — the launch's and our lower driver's body (its jumps lie over the ROM's own
    driver, whose text the ROM's shore runs) — are neither run nor read by the ROM's own slice: the same run, every
    surface."""
    the_slice = bl.SLICES[name]
    body = bl.our_pieces(which=which)[1]            # (the jumps lie over the ROM's own driver: its shore runs them)
    assert bl.the_rom_s(the_slice, laid=boot.overlays(bl.overlay(which=which), body)) == the_rom_s(name)


def test_ours_without_our_driver_laid_runs_the_rom_s_driver_and_is_refused_by_name():
    """THE FALSE GREEN OF THE DRIVER (D4 P5a): our launch with no driver of ours beside it runs the ROM's lower driver's
    ported text — measured equal on the ROM's instructions — and is refused off the profile (`never_run_on_ours`)."""
    the_slice = bl.SLICES[NEGATIVE_LAUNCH]
    laid = bl.overlay()
    machine = boot.entered_at(bl.start_of(the_slice), bl.our_entry(the_slice))
    _launch, elsewhere = bl.run(machine, bl.disk(the_slice.disk).image, bl.GEM_ENTRY, (bl.our_span(laid),), laid=laid)
    with pytest.raises(AssertionError, match="executed"):
        bl._vet_who_ran(machine.label, elsewhere, ran=(bl.our_span(laid),),
                        not_ran=bl.never_run_on_ours())


def test_a_run_with_the_printer_on_line_refuses_seeds_beside_its_port():
    """`aes_boot._Run` lays ONE declaration of the chips: the printer's port, or the seeds a B4 run hands it — the two
    together are refused by name, never one silently dropped (review RP5a's NIT 7)."""
    with pytest.raises(ValueError, match="printer"):
        aes_boot._Run(bytearray(BASE_IMAGE), bl.NO_ANSWER, 1, printer=True, seeds={"psg_seed": {addrs.PSG_PORT_A: 0}})


def test_the_carry_into_the_mid_boot_is_a_surface():
    """THE CARRY'S NEGATIVE (R-D4-2): the ROM's own launch from MR's power-on chip, not B6's, leaves another FDC ledger —
    its first status read finds the motor off (`$04`, not B6's `$a4`) — so the carry handed in is read, not a no-op. (The
    chip it leaves is the same: the first command spins the motor up.)"""
    the_slice = bl.SLICES[NEGATIVE_LAUNCH]
    carried = the_rom_s(NEGATIVE_LAUNCH)
    from_power_on, _elsewhere = bl.run(bl.start_of(the_slice), bl.disk(the_slice.disk).image, bl.GEM_ENTRY,
                                       bl.THE_ROM_S_SPANS, carry=bl.carry_at_the_mid_boot()._replace(chip=None))
    assert from_power_on.fdc_events[0] == ("read", *MOTOR_OFF_STATUS)
    assert carried.fdc_events[0] == ("read", *MOTOR_ON_STATUS)


# ---- THE DEVICE CLASS: DRIVE A: NEVER LOGGED IN -------------------------------------------------------------------------
def _memory(ram):
    memory = bytearray(BASE_IMAGE)
    memory[:bl.RAM_BYTES] = ram
    return memory


def test_drive_a_is_never_logged_in_at_the_mid_boot_stop():
    """THE PREMISE: at `$fc047a` the driver's record for drive A: is zero — GEMDOS has read nothing of the disk — and
    the blank disk's one trace is its boot sector in the disk buffer, which the first Getbpb lays again."""
    machine = boot.midboot_machine()
    memory = _memory(machine.ram)
    record = aes_boot.driver_record(memory)
    assert not any(memory[record:record + aes_boot.FLOPPY_BPB_RECORD_BYTES])
    assert machine.ram[aes_boot.driver_boot_sector(memory):][:512] == aes_boot.blank_disk()[:512]
    with pytest.raises(boot.Refused, match="another geometry"):
        aes_boot.Floppy(memory, aes_boot.blank_disk())
    bl.NeverLoggedIn(memory, bl.disk(bl.PEXEC_FAILS).image)


def test_a_record_that_holds_a_disk_is_vetted_as_the_parent_vets_it():
    memory = _memory(aes_boot.preinit().ram)
    bl.NeverLoggedIn(memory, aes_boot.blank_disk())
    with pytest.raises(boot.Refused):
        bl.NeverLoggedIn(memory, bl.disk(bl.PEXEC_FAILS).image)


@pytest.mark.parametrize("name", LAUNCHES)
def test_the_first_read_of_the_disk_is_the_log_in(name):
    """The first transfer the FDC model makes, on both shores, is the ROM's Getbpb's: the boot sector (track 0, side 0,
    sector 1) into the driver's boot-sector buffer — the disk logged in, since drive A: never was (R-B4-3)."""
    for launch in pair(name):
        transfers = [entry for entry in launch.fdc_events if entry[0] == "dma_in"]
        assert transfers[0] == ("dma_in", aes_boot.driver_boot_sector(_memory(bl.start_of(bl.SLICES[name]).ram)),
                                addrs.BOOT_SECTOR_BYTES)


# ---- THE END SURFACE: THE PRE-INIT CAPTURE -------------------------------------------------------------------------------
@pytest.mark.parametrize("name", CAPTURED)
def test_the_launch_reaches_the_pre_init_capture_of_its_disk(name):
    """THE END SURFACE (the survey's "by construction"): our launch's machine, its linked longwords mapped back, against
    Hatari's capture at gem_entry with the same disk in the drive from power-on — every register equal, and EVERY BYTE
    outside the pre-init mask (D4 P5a: the floppy through the FDC model, the lower driver's own state the capture's —
    until P5a 22-23 of its bytes were apart, the device model answering above that driver)."""
    the_rom_s, ours = pair(name)
    assert ours == pair(name)[1] and bl.differences(the_rom_s, pair(name, bl.TWIN)[1], bl.LAUNCH,
                                                   bl.linked(bl.LAUNCH, bl.TWIN), bl.TWIN) == []
    capture = bl.disk(bl.SLICES[name].disk).capture()
    registers, runs = bl.against_the_capture(ours, capture, bl.linked(bl.LAUNCH))
    assert (registers, runs) == bl.against_the_capture(the_rom_s, capture) == ((), ())


def test_the_end_surface_s_negative_a_byte_outside_the_driver_is_seen():
    _the_rom_s, ours = pair(NEGATIVE_LAUNCH)
    capture = bl.disk(bl.BLANK).capture()
    changed = _ram_changed(ours, C["BOOT_ENVIRONMENT"], ours.ram[C["BOOT_ENVIRONMENT"]] ^ 1)
    _registers, runs = bl.against_the_capture(changed, capture, bl.linked(bl.LAUNCH))
    assert (C["BOOT_ENVIRONMENT"], 1) in runs
    moved = ours._replace(registers={**ours.registers, "usp": ours.registers["usp"] ^ LONG_BYTES})
    assert bl.against_the_capture(moved, capture, bl.linked(bl.LAUNCH))[0] == ("usp",)


# ---- THE DEAD CLASSES AT THE RUNNER'S RETURN ------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", NOISE_SEEDS)
@pytest.mark.parametrize("name", RUNNERS)
def test_what_the_runner_s_row_does_not_hold_is_dead_by_gem_entry(name, seed):
    """THE ROM'S OWN RUN ON, from its machine at the runner's return, to gem_entry: noise in the scratch registers, the
    process's frame pointer and the two dead copies on its stack leaves the machine outside the mask, the registers and
    the instructions the same."""
    the_slice = bl.SLICES[name]
    start = bl.start_of(the_slice)
    machine, carry = bl.machine_of(the_rom_s(name), start), bl.carry_of(the_rom_s(name))
    plain = bl.continued(machine, the_slice.disk, carry)
    noisy = bl.continued(bl.noised(machine, bl.NOT_HELD[bl.TWIN][bl.AUTO_RUNNER_KIND], bl.dead_at_the_runner_s_return(machine),
                                   seed), the_slice.disk, carry)
    assert (noisy.instructions, noisy.registers) == (plain.instructions, plain.registers)
    assert bl.masked(noisy.ram) == bl.masked(plain.ram)


def test_noise_in_a_live_register_at_the_runner_s_return_is_seen():
    """NEGATIVE: A5 at the runner's return is the AUTO basepage the launch's Pexec(4) frame keeps — noise there reaches
    the pre-init machine."""
    the_slice = bl.SLICES[NEGATIVE_RUNNER]
    machine = bl.machine_of(the_rom_s(NEGATIVE_RUNNER), bl.start_of(the_slice))
    plain = bl.continued(machine, the_slice.disk)
    noisy = bl.continued(bl.noised(machine, ("a5",), ()), the_slice.disk)
    assert bl.masked(noisy.ram) != bl.masked(plain.ram)


# ---- THE MID-BOOT REGISTERS THAT REACH THE PRE-INIT MACHINE (B2's and B3's carried registers, measured at this end) -------
# GEMDOS keeps D0/A3-A6 of a process's last trap in its basepage (+$68..): the BIOS process's last is the runner's
# Pexec(4), so A3, A4 and A6 as the boot stands at `$fc047a` — the runner sets A5 and D0 itself — are bytes of the
# pre-init machine, outside its mask. D3 (B3's) is dead here.
BIOS_PROCESS_FRAME = {"a3": 0x6c, "a4": 0x70, "a6": 0x78}


@pytest.mark.parametrize("register", ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "a0", "a1", "a2", "a3", "a4",
                                      "a5", "a6"))
def test_which_mid_boot_registers_reach_the_pre_init_machine(register):
    machine = bl.start_of(bl.SLICES[NEGATIVE_LAUNCH])
    plain = bl.continued(machine, bl.BLANK)
    noisy = bl.continued(machine._replace(registers={**machine.registers,
                                                     register: machine.registers[register] ^ 0x00a5a5a4}), bl.BLANK)
    runs = differing_fields(bl.masked(noisy.ram), bl.masked(plain.ram))
    assert (noisy.instructions, noisy.registers) == (plain.instructions, plain.registers)
    bios_process = case.long_in(machine.ram, addrs.GEMDOS_P_RUN) & boot.BUS
    if register in BIOS_PROCESS_FRAME:
        at = bios_process + BIOS_PROCESS_FRAME[register]
        assert runs and all(at <= start and start + length <= at + LONG_BYTES for start, length in runs)
    else:
        assert runs == []


# ---- THE MASK'S RULE, CARRIED TO gem_entry (B0's, owed here) ---------------------------------------------------------------
def test_the_capture_s_masked_bytes_are_read_by_no_run_to_gem_entry():
    """From the mid-boot capture whose every masked byte is NOISE, the ROM's launch takes the same instructions to the
    same registers and the same machine outside the pre-init mask — the floppy through the FDC model since D4 P5a, its
    ledger the same too (B0's rule reached the first floppy call only)."""
    plain = bl.start_of(bl.SLICES[NEGATIVE_LAUNCH])
    spans = [(lo, lo + size) for lo, size, _why in midboot_snapshot.MASK]
    noisy = plain._replace(ram=aes_boot.noise_over(plain.ram, spans, NOISE_SEEDS[0]))
    one, other = bl.continued(plain, bl.BLANK), bl.continued(noisy, bl.BLANK)
    assert (one.instructions, one.registers, one.fdc_events) == (other.instructions, other.registers, other.fdc_events)
    assert bl.masked(one.ram) == bl.masked(other.ram)


def test_noise_outside_the_capture_s_mask_is_seen_at_gem_entry():
    plain = bl.start_of(bl.SLICES[NEGATIVE_LAUNCH])
    noisy = plain._replace(ram=aes_boot.noise_over(plain.ram, [(boot.RAM_BYTES - 16, boot.RAM_BYTES)], NOISE_SEEDS[0]))
    assert bl.masked(bl.continued(plain, bl.BLANK).ram) != bl.masked(bl.continued(noisy, bl.BLANK).ram)


# ---- DRIVE A:'S WRITE-PROTECT LATCH AND SEEN BYTE, HELD BY BOTH CAPTURE MASKS (D4 P5a R-P5a-2, P5b R-P5b-1) ---------------
# The ROM's Getbpb, which B4 runs since P5a, reads the latch (`$fc1156`); its Mediach, which every AES boot runs since P5b,
# reads the seen byte (`$fc11aa`). The floppy's vertical-blank service's other words, `$9f9` and `[$9fb,$a08)`, stay
# masked — EXACTLY those (`preinit_snapshot.FLOPPY_VBL_WORDS_MASKED`, both masks' one source).
DRIVE_A_LATCH = preinit_snapshot.DRIVE_A_WRITE_PROTECT_LATCH
DRIVE_A_SEEN = preinit_snapshot.DRIVE_A_WRITE_PROTECT_SEEN
FLOPPY_VBL_WORDS_END = preinit_snapshot.FLOPPY_VBL_WORDS_END
HELD_IN_THE_FIELD = (DRIVE_A_LATCH, DRIVE_A_SEEN)
MEDIACH_READS_THE_SEEN_BYTE = 0xfc11a4  # `movea.l #<the seen bytes>,a0`, then `tst.b 0(a0,d7.w)`: drive A: added
LATCH_SET, LATCH_CLEAR = 0xff, 0x00     # a latch as the service leaves a protected drive's, and an unprotected one's


def masked_bytes(mask):
    return {at for lo, size, _why in mask for at in range(lo, lo + size)}


def with_drive_a_latched(ram, at=DRIVE_A_LATCH):
    latched = bytearray(ram)
    latched[at] = LATCH_SET
    return bytes(latched)


def every_capture():
    import accessory_disk
    return (midboot_snapshot.load(), *(preinit_snapshot.load(path()) for path in (
        preinit_snapshot.preinit_path, preinit_snapshot.accessory_path, preinit_snapshot.seven_accessory_path,
        preinit_snapshot.inf_path, accessory_disk.files_capture_path)))


def test_drive_a_s_write_protect_latch_is_the_byte_getbpb_reads_and_the_field_beside_it_is_the_service_s_words():
    """The latch is read out of Getbpb's own instruction (`$fc114a movea.l #<the latches>,a1`, drive A: added) and is the
    driver header's `FLOPPY_WP_LATCH`; the service's words end where the driver's request begins (`FLOPPY_DRIVE`) — the
    tools' two constants pinned to the C's spelling (one source of truth across the language boundary)."""
    assert aes_boot.driver_latches(BASE_IMAGE)[0] == DRIVE_A_LATCH == boot_floppy.CONSTANTS["FLOPPY_WP_LATCH"]
    assert FLOPPY_VBL_WORDS_END == boot_floppy.CONSTANTS["FLOPPY_DRIVE"]


def test_drive_a_s_seen_byte_is_the_byte_mediach_reads():
    """(R-P5b-1) The seen byte is read out of Mediach's own instruction (`$fc11a4 movea.l #<the seen bytes>,a0`, then
    `tst.b 0(a0,d7.w)`, drive A: added) and is the driver header's `FLOPPY_WP_SEEN`."""
    assert texts(MEDIACH_READS_THE_SEEN_BYTE, MEDIACH_READS_THE_SEEN_BYTE + 10) == [
        f"moveal #{DRIVE_A_SEEN},%a0", "tstb %a0@(0,%d7:w)"]
    assert DRIVE_A_SEEN == boot_floppy.CONSTANTS["FLOPPY_WP_SEEN"]


@pytest.mark.parametrize("mask", (preinit_snapshot.MASK, midboot_snapshot.MASK), ids=("pre-init", "mid-boot"))
def test_each_mask_holds_drive_a_s_latch_and_seen_byte_and_masks_exactly_the_service_s_other_words(mask):
    """BOTH DIRECTIONS (review RP5a's REQ-3, R-P5b-1): from the latch to one byte past the service's words, the mask covers
    EXACTLY `$9f9` and `[$9fb, $a08)` — the latch and the seen byte held, and neither a word of the service left unmasked
    nor the driver's request (`$a08`) masked."""
    around = set(range(DRIVE_A_LATCH, FLOPPY_VBL_WORDS_END + 1))
    assert masked_bytes(mask) & around == {DRIVE_A_LATCH + 1, *range(DRIVE_A_SEEN + 1, FLOPPY_VBL_WORDS_END)}


@pytest.mark.parametrize("at", HELD_IN_THE_FIELD, ids=("the latch", "the seen byte"))
def test_every_capture_holds_drive_a_s_latch_and_seen_byte_clear(at):
    """WHAT IS HELD: drive A: holds an unprotected disk from power-on, so the mid-boot capture and all five pre-init
    captures leave its latch and its seen byte clear. (Drive B:'s latch `$9f9` and seen byte `$9fb` are phase: `$ff` in
    some captures, `$00` in others — the service's poll of an empty bay — and stay masked.)"""
    assert [capture.ram[at] for capture in every_capture()] == [LATCH_CLEAR] * 6


@pytest.mark.parametrize("at", HELD_IN_THE_FIELD, ids=("the latch", "the seen byte"))
def test_a_capture_with_drive_a_s_latch_or_seen_byte_apart_is_caught_by_both_masks(at):
    """THE NEGATIVE: a capture whose drive-A: latch, or seen byte, differs is a disagreement `--twice` says, on both
    captures' masks."""
    mid = midboot_snapshot.load()
    assert midboot_snapshot.disagreements(mid, mid._replace(ram=with_drive_a_latched(mid.ram, at))) == (
        "the RAM outside the mask",)
    pre = preinit_snapshot.load()
    assert preinit_snapshot.masked(pre.ram) != preinit_snapshot.masked(with_drive_a_latched(pre.ram, at))


def test_the_launch_reads_drive_a_s_latch():
    """WHY IT IS HELD: from the mid-boot capture with drive A:'s latch set, the ROM's launch takes Getbpb's other arm
    (the latch copied, the drive's mode MAYBE) — other instructions, another machine outside the pre-init mask."""
    plain = bl.start_of(bl.SLICES[NEGATIVE_LAUNCH])
    one = bl.continued(plain, bl.BLANK)
    latched = bl.continued(plain._replace(ram=with_drive_a_latched(plain.ram)), bl.BLANK)
    assert latched.instructions != one.instructions and bl.masked(latched.ram) != bl.masked(one.ram)


# ---- THE CLOCK, ANSWERED AT ITS PROBE'S ENTRY (ruling R-B4-2) ---------------------------------------------------------------
@pytest.mark.parametrize("name", tuple(bl.SLICES))
def test_the_clock_is_asked_where_a_program_runs_and_nowhere_else(name):
    """ONCE where a program loads and runs (its Pexec(0)'s resync, `$fc5092`), on both shores; never elsewhere."""
    the_rom_s, ours = pair(name)
    assert the_rom_s.clock == ours.clock == pair(name, bl.TWIN)[1].clock == (bl.SLICES[name].disk == bl.ONE_PROGRAM)


def test_the_clock_s_probe_is_where_both_callers_call_it_and_answers_as_its_absent_arm():
    """The entry answered is the probe both callers `bsr` to, and the answer its absent arm's: `ori #1,ccr` / `rts`."""
    assert texts(0xfc5092, 0xfc5096) == [f"bsrw 0x{bl.CLOCK_PROBE:x}"]
    assert texts(0xfc4c44, 0xfc4c46) == [f"bsrs 0x{bl.CLOCK_PROBE:x}"]
    assert texts(0xfc4c3e, 0xfc4c44) == [f"orib #{bl.SR_CARRY},%ccr", "rts"]


def test_the_capture_machine_has_no_clock():
    """THE ANSWER'S PROVENANCE: the capture's machine is a plain ST (`--machine st`), which has no RP5C15."""
    import boot_snapshot
    arguments = boot_snapshot.MACHINE_ARGUMENTS
    assert arguments[arguments.index("--machine") + 1] == "st"


@pytest.mark.parametrize("name", ONE_PROGRAM_ROWS)
def test_a_clock_answered_present_takes_another_road(name):
    """THE ANSWER'S NEGATIVE: carry clear — a clock there — and the ROM takes the present arm (its digits read, GEMDOS's
    time and date laid from them): another machine. The answer is a surface the row holds, not a no-op."""
    the_slice = bl.SLICES[name]
    present, _elsewhere = bl.run(bl.start_of(the_slice), bl.disk(the_slice.disk).image, bl.stop_of(the_slice, False),
                                 bl.THE_ROM_S_SPANS, clock_carry=False)
    assert present.clock == 2 and bl.masked(present.ram) != bl.masked(the_rom_s(name).ram)     # (the read probes again)


# ---- TWO PIECES ON A CASE'S OWN INPUTS --------------------------------------------------------------------------------------
@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize("bootdev,letter", ((0x0000, "A"), (0x0001, "A"), (0x0100, "B"), (0x0201, "C")))
def test_the_environment_s_letter_is_made_from_bootdev_s_high_byte(bootdev, letter, which):
    """THE ROM'S BUG, KEPT: `move.b $446,d0` reads the word's FIRST byte — drive 1 is still 'A', 256 is 'B'. Ours lays
    the same twelve bytes and stores nothing else outside the stack."""
    (the_rom_s, rom_stored), (ours, our_stored) = bl.environment_of(bootdev, which)
    assert ours == the_rom_s == b"PATH=\0" + letter.encode() + b":\\\0\0\xff" and our_stored == rom_stored


@pytest.mark.parametrize("which,scratch", ((bl.SHIPPED, []), (bl.TWIN, ["d1", "a0", "a1"])))
def test_without_its_drive_the_runner_launches_nothing(which, scratch):
    """THE DRIVE MISSING (`_drvbits` without `_bootdev`'s bit): the runner lays its path and returns at once — no
    GEMDOS call on either shore, every register (but the scratch) and the megabyte the same."""
    the_rom_s, ours = bl.runner_without_its_drive(which)
    assert the_rom_s.gemdos == ours.gemdos == () and the_rom_s.fdc_events == ours.fdc_events == ()
    assert [reg for reg in boot.REGISTER_NAMES if reg != "pc" and the_rom_s.registers[reg] != ours.registers[reg]] == scratch
    ram = bl.mapped_back(ours.ram, {name: link for name, link in bl.linked(bl.LAUNCH, which).items()
                                    if name == "the runner's return"})
    assert bl.masked(ram) == bl.masked(the_rom_s.ram)


# ---- THE GEMDOS LEDGER'S ARGUMENT WIDTHS, READ OFF THE ROM (review RB4's R1) ----------------------------------------------
PUSH_BYTES = {"movel": LONG_BYTES, "pea": LONG_BYTES, "clrl": LONG_BYTES, "movew": WORD_BYTES, "clrw": WORD_BYTES}


def _pushed_before(listing, index):
    """The bytes the instructions right before `listing[index]` push (`-(sp)`), walking back to the first that pushes
    nothing."""
    pushed = 0
    for _at, text in reversed(listing[:index]):
        mnemonic = (text or "").split(" ")[0]
        if mnemonic not in PUSH_BYTES or not (mnemonic == "pea" or text.endswith("%sp@-")):
            break
        pushed += PUSH_BYTES[mnemonic]
    return pushed


def _frames_the_runner_pushes():
    """`{GEMDOS function: its frame, the function word among it}` as the ROM's runner and process push them: each `trap
    #1`'s pushes walked back from it; Fsfirst's and Fsnext's, whose words are pushed before Fsetdta's, as the ROM counts
    them itself (`moveq #8,d7` / `moveq #2,d7`, dropped by `adda.w d7,sp`)."""
    listing = rom_data.instructions(*bl.AUTO_RUNNER_SPAN)
    frames = {}
    for index, (_at, text) in enumerate(listing):
        if text == "trap #1" and _pushed_before(listing, index):
            function = int(listing[index - 1][1].split("#")[1].split(",")[0])
            frames[function] = _pushed_before(listing, index)
    counts = [int(text.split("#")[1].split(",")[0]) for _at, text in listing if text and text.endswith(",%d7")]
    frames[addrs.GEMDOS_FSFIRST_FN], frames[addrs.GEMDOS_FSNEXT_FN] = counts
    return frames


def test_each_gemdos_argument_width_is_the_rom_s_own_frame_less_its_function_word():
    """THE LEDGER CANNOT BE NARROWED IN SILENCE: every width `GEMDOS_ARGUMENT_BYTES` compares is the frame the ROM's own
    code pushes for that call, less the function word — Pexec 14, Mshrink 10, Fsfirst 6, Fsnext 0, Fsetdta 4, Super 4 —
    and Pterm0's, the AUTO program's own `clr.w -(sp)`, 0."""
    frames = _frames_the_runner_pushes()
    assert frames[addrs.GEMDOS_PEXEC_FN] == C["PEXEC_FRAME_BYTES"]
    expected = {function: frame - WORD_BYTES for function, frame in frames.items()}
    program = [line.split("|")[0].split() for line in bl.AUTO_PROGRAM_SOURCE.read_text().splitlines()
               if line.startswith("    ") and line.split("|")[0].strip() and not line.strip().startswith(".")]
    assert program == [["clr.w", "-(%sp)"], ["trap", "#1"]]
    expected[addrs.GEM_SELECTOR_PTERM] = WORD_BYTES - WORD_BYTES
    assert expected == bl.GEMDOS_ARGUMENT_BYTES == {
        addrs.GEMDOS_PEXEC_FN: 14, C["GEMDOS_MSHRINK_FN"]: 10, addrs.GEMDOS_FSFIRST_FN: 6, addrs.GEMDOS_FSNEXT_FN: 0,
        addrs.GEMDOS_FSETDTA_FN: 4, addrs.GEMDOS_SUPER_FN: 4, addrs.GEM_SELECTOR_PTERM: 0}
