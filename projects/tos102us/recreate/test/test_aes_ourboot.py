"""THE OUR BOOT (band 5 wave 4, slice B): OUR BUILD BOOTS TO deskmain's ENTRY — held to the ROM's own boot, and priced.

The machine is `aes_boot.booted(..., laid=AT_GEM_ENTRY)`: A LABELLED STAGING (ruling W4-R1) — the blob laid at the
pre-init stop and the run entered at the blob's own gem_entry, NOT ONE LONGWORD MAPPED BY THE HARNESS — on the blank
disk and the DESKTOP.INF disk, both blobs; a disk with an accessory stays refused (ruling W4-R2). What it is held to is
`aes_ourboot.py`'s: both shores watched at the same checkpoints.

  1. THE MACHINE: it boots; "OURS BOOTED" IS CLAIMED TO deskmain's ENTRY AND NO FURTHER (ruling W4-R3) — WHO RAN, cut
     there: the ROM's GEM text 0 cycles, the Line-F handler's copy 0, ours > 0, the same whichever run was made before;
     the scan finds no entry held by value as the ROM's but gem_entry's three, which the BIOS stored; its refusals.
  2. THE CHECKPOINTS (ruling W4-R5): gem_entry's arms, gem_main's bring-up callee by callee, the reader's file arm at
     its real arrival, the shell's first pass — and, THROUGH THE SERVED DOOR ON THE OUR-BOOT MACHINE (ruling W4-R6: A
     LABELLED ARGUMENT CLASS, in the name of every test and row that uses it), gem_main's teardown, gem_entry's second
     pass, sh_cmd's four built-ins and the launch pass to dos_exec's entry: the megabyte at each, the order, the
     stores between two.
  3. THE CLASSES: the live ones named checkpoint by checkpoint, needed or refused; the dead ones proved dead by noise
     at every checkpoint; every code address mapped through the registry — each mapping needed, the three this slice
     activated among them — and `$8990..$8993`, a code address's half, by gem_entry's own offsets.
  4. THE TWO STACK GATES re-stated on the our-boot machine, bound and measured (rulings W4-R9, W4-R4).
  5. THE ROWS (ruling W4-R11): registered here, priced by `bench/tier3.py` on the shipped blob; held here on both
     blobs, with the bench blob's own figures (the C twins of every transcribed core in a real boot) REPORTED.

WHAT THIS BATTERY DOES NOT HOLD: anything past deskmain's entry on a machine of ours (the desk's depth under our
frames is not claimed); the `$2c` test's SKIP arm on a machine a boot makes — gem_entry is entered once, and its
loop's `bra` goes back past the test: held by the pin, and by a labelled craft here.
"""
import functools
import struct
import types

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3

import aes
import aes_boot
import aes_event
import aes_ourboot as ob
import aes_stack
import aes_switch
import case
import isr
import transcription
import test_aes_stack as pinned
from aes_boot import Refused

LONG_BYTES, WORD_BYTES, BUS = aes.LONG_BYTES, aes.WORD_BYTES, aes.OS_BUS_ADDR_MASK
BENCH, SHIPPED = pinned.BENCH, pinned.SHIPPED
every_blob = pytest.mark.parametrize("blob", isr.BLOBS)
BLANK, INF, INF_CHANGED = ob.THE_BLANK_DISK, ob.THE_INF_DISK, ob.THE_INF_DISK_CHANGED
DESKMAIN, GEM_MAIN = addrs.AES_ROM_DESKMAIN, addrs.AES_ROM_GEM_MAIN
READER_RETURNED, SH_CMD_RETURNED = ob.RETURNED.format(ob.THE_READER), ob.RETURNED.format(ob.SH_CMD)
FRAMES, MANAGER = (ob.PD0_FRAMES,), (ob.MANAGER_CONTEXT, ob.MANAGER_STACK)
A_WORD_OF_THE_AES_S_STATE = aes.header_constants("evasync.h")["AES_GL_BPEND"]       # compared at every checkpoint: in no class


def the_blob(blob):
    return isr.blob_named(blob)


# ---- THE ROWS (ruling W4-R11), REGISTERED: `bench/tier3.py` prices each on the shipped blob -----------------------------------
# A STRETCH between two checkpoints of a pass; `differs`: the LIVE classes the two machines differ in where it ends.
# EVERY CASE CARRIES THE MACHINE'S LABEL, and the served door's where its pass goes through it (`aes_ourboot.case_of`).
THE_FIRST_PASSES = {disk: ob.first_pass(disk) for disk in (BLANK, INF, INF_CHANGED)}
THE_TEARDOWN, THE_LAUNCH = ob.teardown_pass(), ob.launch_pass()
THE_BUILT_IN_PASSES = {built_in: ob.built_in_pass(built_in) for built_in in ob.THE_BUILT_INS}
TO_THE_DESK = "to deskmain's entry"
STRETCHES = (
    # gem_main: the stretch of a boot, and — deskmain served 0 — its teardown and the whole second pass
    ob.Stretch("AES_ROM_GEM_MAIN", f"the first pass {TO_THE_DESK}, the blank disk", THE_FIRST_PASSES[BLANK], ob.GEM_MAIN,
               ob.DESKMAIN_ENTERED, FRAMES + MANAGER, turns=1),
    ob.Stretch("AES_ROM_GEM_MAIN", f"the first pass {TO_THE_DESK}, a DESKTOP.INF on the disk", THE_FIRST_PASSES[INF], ob.GEM_MAIN,
               ob.DESKMAIN_ENTERED, FRAMES + MANAGER, turns=1),
    ob.Stretch("AES_ROM_GEM_MAIN", "the teardown, from the shell's return to its own", THE_TEARDOWN, "gsx_mfree",
               ob.GEM_MAIN_RETURNED, MANAGER),
    ob.Stretch("AES_ROM_GEM_MAIN", f"the second pass {TO_THE_DESK}", THE_TEARDOWN, ob.GEM_MAIN, ob.DESKMAIN_ENTERED, FRAMES + MANAGER,
               turns=1),
    # the `#E` reader: the boot's own call, over real GEMDOS in place
    ob.Stretch("AES_ROM_GEM_READ_INF", "the boot's own call: no DESKTOP.INF on the disk", THE_FIRST_PASSES[BLANK], ob.THE_READER,
               READER_RETURNED, FRAMES),
    ob.Stretch("AES_ROM_GEM_READ_INF", "the boot's own call: a DESKTOP.INF that asks the booted resolution", THE_FIRST_PASSES[INF],
               ob.THE_READER, READER_RETURNED, FRAMES),
    ob.Stretch("AES_ROM_GEM_READ_INF", "the boot's own call: a DESKTOP.INF that asks another resolution", THE_FIRST_PASSES[INF_CHANGED],
               ob.THE_READER, READER_RETURNED, FRAMES),
    # sh_main: its first pass, and its passes after a served deskmain
    ob.Stretch("AES_ROM_SH_MAIN", f"the first pass {TO_THE_DESK}", THE_FIRST_PASSES[BLANK], ob.SH_MAIN, ob.DESKMAIN_ENTERED,
               FRAMES + MANAGER),
    ob.Stretch("AES_ROM_SH_MAIN", "the desk quits: the shell's last pass, to gem_main's teardown", THE_TEARDOWN, ob.BEGAN, "gsx_mfree",
               FRAMES + MANAGER),
    ob.Stretch("AES_ROM_SH_MAIN", "a file shown, and back to deskmain's entry", THE_BUILT_IN_PASSES[ob.SHOW_FILE],
               ob.BEGAN, ob.DESKMAIN_ENTERED, FRAMES + MANAGER),
    ob.Stretch("AES_ROM_SH_MAIN", "a program the disk holds, to dos_exec's entry", THE_LAUNCH, ob.BEGAN, ob.DOS_EXEC_ENTERED,
               FRAMES + MANAGER),
    # sh_cmd: its five arms
    *(ob.Stretch("AES_ROM_SH_CMD", f"the tail's byte ${ob.THE_BUILT_INS[built_in][0]:x}: {built_in.partition('(')[2].rstrip(')')}",
                 THE_BUILT_IN_PASSES[built_in], ob.SH_CMD, SH_CMD_RETURNED, FRAMES + MANAGER) for built_in in ob.THE_BUILT_INS),
    ob.Stretch("AES_ROM_SH_CMD", "no built-in's byte: a program's tail", THE_LAUNCH, ob.SH_CMD, SH_CMD_RETURNED, FRAMES + MANAGER),
)
for _stretch in STRETCHES:
    ob.register(_stretch)
EVERY_STRETCH = pytest.mark.parametrize("stretch", STRETCHES, ids=ob.row_name)
THE_PASSES = {**{f"the first pass, {disk}": a_pass for disk, a_pass in THE_FIRST_PASSES.items()},
              "ARGUMENT CLASS (deskmain served 0): the teardown and the second pass": THE_TEARDOWN,
              "ARGUMENT CLASS (deskmain served 0): the teardown and the second pass, a DESKTOP.INF on the disk": ob.teardown_pass(INF),
              "ARGUMENT CLASS (deskmain served 1): the launch pass": THE_LAUNCH,
              **{f"ARGUMENT CLASS (deskmain served 1, the built-in served): {built_in}": a_pass
                 for built_in, a_pass in THE_BUILT_IN_PASSES.items()}}
every_pass = pytest.mark.parametrize("label", THE_PASSES)


# ---- (1) THE MACHINE ----------------------------------------------------------------------------------------------------------
THE_MACHINES = {"the blank disk": (aes_boot.our_desk_machine, aes_boot.desk_machine),
                "the DESKTOP.INF disk": (aes_boot.our_inf_machine, aes_boot.inf_machine)}
every_machine = pytest.mark.parametrize("disk", THE_MACHINES)
THE_ROM_ENTERS_DESKMAIN_AT = pinned.PD0_S[1] - pinned.THE_ROM_S_SP_IN_SH_MAIN - LONG_BYTES     # `$a364`


@every_blob
@every_machine
def test_labelled_staging_our_boot_reaches_deskmain_s_entry_and_its_first_idle_and_who_ran_is_ours(disk, blob):
    """THE OUR-BOOT MACHINE, BUILT (a LABELLED STAGING, ruling W4-R1): the blob laid at the pre-init stop and entered
    at its own gem_entry boots — and ARRIVES AT deskmain's ENTRY ON THE ROM'S OWN STACK POINTER. WHO RAN — "ours
    booted" claimed TO THE DESKTOP'S FIRST IDLE since band 6 W3b's flip (ruling W4-R3, extended by the orchestrator's
    O5): cycles in the blob, NOT ONE in the ROM's GEM text, NOT ONE in the Line-F handler's RAM copy, stopped at
    deskmain's entry AND run on to the first idle — the second the first's and more. It is no takeover: nothing was
    mapped — and the machine says what it is."""
    ours_boots, _the_rom_s = THE_MACHINES[disk]
    desk = aes_boot.deskmain_entry(aes_boot.ours_of(the_blob(blob)))       # ...where our door enters deskmain
    booted, at_the_desk = ours_boots(the_blob(blob)), ours_boots(the_blob(blob), until=desk)
    made = booted.our_boot
    assert made is not None and booted.takeover is None and booted.door is None and booted.ours == aes_boot.ours_of(the_blob(blob))
    instructions, cycles, sp = made.at_the_desk
    assert sp == THE_ROM_ENTERS_DESKMAIN_AT == 0xa364 and 0 < instructions < booted.boot.instructions and cycles > 0
    in_ours, in_the_rom_s_text, in_the_copy = made.ran
    assert in_ours > 0 and (in_the_rom_s_text, in_the_copy) == (0, 0)
    to_the_desk = at_the_desk.our_boot
    assert (to_the_desk.ours, to_the_desk.at_the_desk) == (made.ours, made.at_the_desk)
    assert to_the_desk.ran[1:] == (0, 0) and 0 < to_the_desk.ran[0] < in_ours, "to deskmain's entry, then on to the idle: ours alone"
    assert at_the_desk.idle is None and at_the_desk.registers["pc"] == desk
    assert (at_the_desk.boot.instructions, at_the_desk.registers["isp"]) == (instructions, sp)
    assert booted.idle == aes_boot.OURS, "the desk — ours since band 6 W3b — parks last, through OUR dispatcher"
    assert bytes(booted.ram[made.ours.base:made.ours.base + len(made.ours.image)]) == made.ours.image


@every_blob
@every_machine
def test_labelled_staging_our_boot_makes_the_calls_of_the_disk_the_rom_s_boot_makes(disk, blob):
    """...and it is THE SAME BOOT to the device: every call of the floppy driver, in order, with the same arguments
    and answers as the ROM's own boot of that disk; one horizontal blank taken; the disk left as it was."""
    ours_boots, the_rom_boots = THE_MACHINES[disk]
    ours, the_rom_s = ours_boots(the_blob(blob)).boot, the_rom_boots().boot
    assert ours.floppy == the_rom_s.floppy and len(ours.floppy) > 0
    assert (ours.blanks, ours.disk, ours.io) == (the_rom_s.blanks, the_rom_s.disk, the_rom_s.io)
    assert ours.hardware_writes == the_rom_s.hardware_writes, "the same bytes to the IKBD, the same off-image stores"


@every_blob
@every_machine
def test_labelled_staging_on_the_our_boot_machine_no_entry_is_held_by_value_as_the_rom_s(disk, blob):
    """THE SCAN, PASSED WITH NOTHING MAPPED BY THE HARNESS: at its first idle the our-boot machine holds NO routine of
    the registry by value as the ROM's in a live longword — `$88`, `$404`, the three gem_entry stores, the VDI's
    three vectors and the screen manager's entry each hold the blob's own, stored by our own run — but gem_entry's
    own address, in the three places THE BIOS stored it (exec_os, the AES's basepage, the launch's frame): by no row
    of ours, so not mapped on either shore."""
    held = aes_boot.vet_no_entry_is_held_as_the_rom_s(THE_MACHINES[disk][0](the_blob(blob)))
    live = [each for each in held if not each.dead]
    assert {each.where for each in live} == {aes_boot.THE_BIOS_S} and {each.routine for each in live} == {addrs.AES_ROM_GEM_ENTRY}
    assert len(live) == 3 and min(each.slot for each in live) == aes_boot.preinit_snapshot.EXEC_OS


def test_labelled_staging_who_ran_is_one_number_whatever_ran_before_it():
    """WHO RAN IS DETERMINISTIC — a difference over one run, never a tally of the process: the same boot made cold three
    times round two other profiled runs gives the same three figures, and so do a pass's two shores made twice."""
    blob, capture, disk = the_blob(SHIPPED), aes_boot.preinit(), aes_boot.blank_disk()
    ours = aes_boot.ours_of(blob)
    desk = aes_boot.deskmain_entry(ours)

    def made():
        return aes_boot.booted.derive(capture, disk, until=desk, ours=ours, laid=aes_boot.AT_GEM_ENTRY).our_boot.ran
    first = made()
    aes_boot.booted.derive(aes_boot.inf_preinit(), aes_boot.inf_disk_of(), until=desk, ours=ours, laid=aes_boot.AT_GEM_ENTRY)
    second = made()
    again = ob.who_ran(ob.Both(ob.watched(THE_TEARDOWN), ob.watched(THE_TEARDOWN, blob), blob, THE_TEARDOWN))
    assert first == second == made() and first[0] > 0 and first[1:] == (0, 0)
    the_rom_s_run = ob.watched(THE_TEARDOWN)
    assert again == ob.who_ran(ob.Both(the_rom_s_run, ob.watched(THE_TEARDOWN, blob), blob, THE_TEARDOWN))
    # ITS RED: the ROM's own run handed over AS OURS (a labelled craft) — cycles in the ROM's GEM text, none in a blob.
    with pytest.raises(ob.Refused, match=r"WHO RAN: our run spent [1-9]\d* cycles IN THE ROM'S OWN GEM TEXT .* and 0 in the blob"):
        ob.who_ran(ob.Both(the_rom_s_run, the_rom_s_run, blob, THE_TEARDOWN))


TRAP_7 = aes_boot.TRAP_7_WORD
A_JUMP_TO_THE_ROM_S_GEM_ENTRY = aes_switch.JMP_ABSOLUTE_LONG + struct.pack(">I", addrs.AES_ROM_GEM_ENTRY)


def _crafted(blob, words):
    """A LABELLED CRAFT, for a refusal: `blob`'s `Ours` with `words` laid over its gem_entry's first instructions."""
    ours = aes_boot.ours_of(the_blob(blob))
    at = ours.start - ours.base
    image = bytearray(ours.image)
    image[at:at + len(words)] = words
    return ours._replace(image=bytes(image))


A_JUMP_TO_THE_ROM_S_DESKMAIN = aes_switch.JMP_ABSOLUTE_LONG + struct.pack(">I", addrs.AES_ROM_DESKMAIN)


@every_blob
def test_labelled_staging_an_our_boot_whose_desk_is_the_rom_s_after_all_is_refused_at_its_first_idle(blob):
    """O5's NEGATIVE PAST deskmain's ENTRY (band 6 W3b's flip, review RW3F's B3): "ours booted" now reaches the desk's
    FIRST IDLE, so a build whose deskmain is the ROM's after all — A LABELLED CRAFT: the door's thunk
    (`linef_to_aes_deskmain`, where sh_main's desk door enters) made a jump to the ROM's deskmain — boots the blank disk
    to its first idle exactly as ours to deskmain's entry, and WHO RAN, counted up to where the run ended, refuses it:
    cycles in the ROM's GEM text and in the Line-F handler's RAM copy, every one of them past deskmain's entry."""
    ours = aes_boot.ours_of(the_blob(blob))
    at = aes_boot.deskmain_entry(ours) - ours.base
    assert at != DESKMAIN - ours.base, "the door enters deskmain at its thunk (the flip)"
    image = bytearray(ours.image)
    image[at:at + len(A_JUMP_TO_THE_ROM_S_DESKMAIN)] = A_JUMP_TO_THE_ROM_S_DESKMAIN
    with pytest.raises(Refused, match=r"NOT AN OUR BOOT — WHO RAN up to where the run ended \([^)]*\): \d+ cycles in the blob, [1-9]\d* IN THE "
                                      r"ROM'S OWN GEM TEXT \[0x[0-9a-f]+, 0x[0-9a-f]+\) and [1-9]\d* in the Line-F handler's RAM copy"):
        aes_boot.booted.derive(aes_boot.preinit(), aes_boot.blank_disk(), laid=aes_boot.AT_GEM_ENTRY, ours=ours._replace(image=bytes(image)))


@every_blob
def test_labelled_staging_what_the_our_boot_refuses_each_by_name(blob):
    """THE LAY'S REFUSALS, beside the premises' own (`test_aes_boot_w4.py`: no blob, a door, a window not free, a disk
    with an accessory): a blob that links no gem_entry; A BUILD WHOSE START-UP IS THE ROM'S AFTER ALL (a labelled
    craft: the blob's gem_entry made a jump to the ROM's — the machine boots, and WHO RAN refuses it: cycles in the
    ROM's GEM text); and A HALT OF THE BUILD (a labelled craft: `trap #7` where gem_entry begins), stopped at the
    BIOS's exception handler and said — never run on into the bombs."""
    capture, disk, ours = aes_boot.preinit(), aes_boot.blank_disk(), aes_boot.ours_of(the_blob(blob))
    lay = functools.partial(aes_boot.booted.derive, capture, disk, laid=aes_boot.AT_GEM_ENTRY)
    with pytest.raises(Refused, match="the blob links no `aes_rom_gem_entry`"):
        lay(ours=ours._replace(start=None))
    # (BOTH SPANS THE BOOT'S WHO-RAN WATCHES ARE IN THE REFUSAL, EACH WITH CYCLES: the ROM's boot runs its text AND makes
    # its Line-F calls through the handler's RAM copy — a who-ran that stopped watching the copy would say 0 of it here)
    the_rom_s_after_all = _crafted(blob, A_JUMP_TO_THE_ROM_S_GEM_ENTRY)
    with pytest.raises(Refused, match=r"NOT AN OUR BOOT — WHO RAN up to where the run ended \([^)]*\): \d+ cycles in the blob, [1-9]\d* IN THE ROM'S OWN GEM "
                                      r"TEXT \[0x[0-9a-f]+, 0x[0-9a-f]+\) and [1-9]\d* in the Line-F handler's RAM copy"):
        lay(ours=the_rom_s_after_all, until=DESKMAIN)
    with pytest.raises(Refused, match=r"THE BUILD'S OWN HALT, `trap #7` at .* \(blob \+ "):
        lay(ours=_crafted(blob, struct.pack(">H", TRAP_7)))
    assert case.long_in(capture.ram, aes_boot.VECTOR_TRAP_7) & BUS == aes_boot.THE_BIOS_S_EXCEPTION_HANDLER
    # ...and THE SAME HALT IN A RUN WATCHED AT ITS CHECKPOINTS (`aes_ourboot`: the passes' engine watches for it too).
    a_pass = THE_FIRST_PASSES[BLANK]
    memory, registers, _disk, io, laid = ob.began_at(a_pass, the_blob(blob))
    memory[laid.start:laid.start + WORD_BYTES] = struct.pack(">H", TRAP_7)
    with pytest.raises(Refused, match=r"THE BUILD'S OWN HALT, `trap #7` at .* \(blob \+ "):
        ob.watched_over(memory, registers, disk, io, laid, ob.places_of(a_pass.checkpoints, the_blob(blob)), ob.until_of(a_pass, the_blob(blob)),
                    ob.our_tally(the_blob(blob)))
    # ...and THE ROM'S START-UP AFTER ALL, IN A PASS (the same craft, watched: `who_ran` refuses the pass it ends).
    memory, registers, _disk, io, laid = ob.began_at(a_pass, the_blob(blob))
    memory[laid.start:laid.start + len(A_JUMP_TO_THE_ROM_S_GEM_ENTRY)] = A_JUMP_TO_THE_ROM_S_GEM_ENTRY
    ran = ob.watched_over(memory, registers, disk, io, the_rom_s_after_all, {}, addrs.AES_ROM_DESKMAIN, ob.our_tally(the_blob(blob)))
    both = ob.both_shores(a_pass, the_blob(blob))
    with pytest.raises(ob.Refused, match=r"WHO RAN: our run spent [1-9]\d* cycles IN THE ROM'S OWN GEM TEXT"):
        ob.who_ran(both._replace(ours=ran))
    # ...and THE ROM'S SELECTOR SWITCH ALONE (the `$88` handler's first instructions, in neither of the AES's own spans:
    # a span of its own in a pass's who-ran) — A LABELLED CRAFT OF THE TALLY: that same run's, which really went
    # through the ROM's switch, with its cycles in the AES's own spans made zero. Refused for the switch's cycles.
    through_the_switch = ran.ended.tally[ob.IN_THE_ROM_S_SELECTOR]
    assert through_the_switch > 0 and both.ours.ended.tally[ob.IN_THE_ROM_S_SELECTOR] == 0 < both.ours.ended.tally[ob.IN_OUR_SELECTOR]
    the_switch_alone = tuple(0 if which == ob.IN_THE_ROM_S_AES else spent for which, spent in enumerate(ran.ended.tally))
    with pytest.raises(ob.Refused, match=rf"WHO RAN: our run spent {through_the_switch} cycles IN THE ROM'S OWN GEM TEXT"):
        ob.who_ran(both._replace(ours=ran._replace(ended=ran.ended._replace(tally=the_switch_alone))))
    # ...and A BOOT THAT STORED OVER ITS OWN BLOB (the vet where the run ends, handed a labelled crafted ledger — the
    # premises refuse every disk that would do it — and a megabyte whose blob is no longer the blob's bytes).
    memory = bytearray(BASE_IMAGE)
    memory[:aes_boot.RAM_BYTES] = capture.ram
    booting = aes_boot.BootingOurs(memory, ours)
    booting.begun()
    ended = (1, 1, {"pc": 0, "isp": 0})
    with pytest.raises(Refused, match=rf"THE OUR-BOOT STORED OVER ITS OWN BLOB: 2 byte\(s\) of its span .* from {ours.base + 4:#x} on"):
        booting.made(memory, ended, {ours.base + 4, ours.base + 5, ours.base - 1, ours.end})
    memory[ours.base + 8] ^= 0xff
    with pytest.raises(Refused, match="THE OUR-BOOT STORED OVER ITS OWN BLOB: its span holds other bytes than the blob's"):
        booting.made(memory, ended, set())


def test_every_row_and_pass_of_the_our_boot_says_what_it_is_made_of():
    """THE LABELS (rulings W4-R1, W4-R6): every registered row's case begins with the machine's label; every row of a
    pass through the served door says so, and no other does; and nothing here names a disk with an accessory."""
    assert ob.STRETCHES and set(ob.STRETCHES) == {ob.row_name(stretch) for stretch in STRETCHES}
    for stretch in STRETCHES:
        said = ob.case_of(stretch)
        assert said.startswith(ob.ON_THE_OUR_BOOT_MACHINE) and "LABELLED STAGING" in said
        assert ("ARGUMENT CLASS (deskmain served" in said) == (stretch.a_pass.answer is not None)
        assert ("a built-in too" in said) == bool(stretch.a_pass.serving)
    assert set(ob.DISKS) == {BLANK, INF, INF_CHANGED} and "LABELLED STAGING" in aes_boot.OUR_BOOT


@every_blob
def test_the_built_ins_are_served_where_the_desk_door_enters_them_read_off_the_build(blob):
    """THE SERVED DOOR AT OUR ENTRIES (band 6 slice F4's prep, ruling O2): each built-in's checkpoint stands on our
    shore where the blob's desk door `jsr`s it — the ROM's routine while it is the ROM's, the table's thunk once it is
    flipped, read off the build and never named — and the served door answers a flipped one at that thunk: no entry
    of ours to answer at while all four are the ROM's, and none on the ROM's shore."""
    ours, door = the_blob(blob), transcription.desk_door_bindings(the_blob(blob).elf)
    for built_in, a_pass in THE_BUILT_IN_PASSES.items():
        checkpoint, = [each for each in a_pass.checkpoints if each.what == built_in]
        assert checkpoint.ours == ob.AT_THE_DESK_DOOR and ob.our_address(checkpoint, ours) == door[checkpoint.rom]
    assert ob.served_door_of(ours) == {entry: rom for rom, entry in door.items() if entry != rom}
    assert ob.served_door_of(None) == {}


# ---- (2) THE CHECKPOINTS: both shores, the megabyte at each, the order, the stores between two ---------------------------------
# THE LIVE CLASSES, CHECKPOINT BY CHECKPOINT — a rule read off what the machine is, the same on both blobs:
#   * PD0's LIVE FRAMES wherever the two shores stand BELOW PD0's stack's top — everywhere but gem_entry's own
#     checkpoints (its first stack, and the loop's `movea.l a6,sp`: the stack empty);
#   * THE SCREEN MANAGER'S CONTEXT AND STACK from its first turn (the first dispatch: at the shell's entry) until THEGLO
#     is cleared again (gem_entry's loop, on a second pass).
IN_GEM_ENTRY_ITSELF = (ob.THE_COPY_MADE, ob.THE_LOOP, ob.THE_CLEAR, ob.THE_STACK_MOVED, ob.GEM_MAIN_RETURNED)


def live_at(a_pass, names):
    """`{checkpoint: the live classes named there}` over a pass's checkpoints in the order the run makes them."""
    managed, live = a_pass.answer is not None, {}
    for what in names:
        managed = (managed or what == ob.SH_MAIN) and what != ob.THE_CLEAR
        frames = what not in IN_GEM_ENTRY_ITSELF and not (what == ob.BEGAN and a_pass.answer is None)
        live[what] = (FRAMES if frames else ()) + (MANAGER if managed else ())
    return live


# THE ONE STORE THE ROM MAKES AND A BUILD'S COMPILER ELIDES: the reader's `clr.w $890a` (`$fda532`), reached only where
# the word was read zero the instruction before — GCC keeps no store of a value it has just tested. The megabyte is
# the same; the ledger is not, and says so here by name (any other store one shore makes alone is a difference).
THE_ROM_ALONE_STORES = {(f"the first pass, {INF}", READER_RETURNED): (aes.AES_GL_RSCHANGE, aes.AES_GL_RSCHANGE + 1)}
# HOW MANY CHECKPOINTS EACH KIND OF PASS ARRIVES AT (first arrivals): its own, where it began, and the return of the
# reader or of sh_cmd — none silently dropped. ONE IS NOT ARRIVED AT AGAIN on a second pass, on either shore: rs_fixit
# (the AES's resource was fixed on the first: gem_main's once-only gate, `$9c40`).
ARRIVED_AT = {"first": len(ob.THE_FIRST_PASS) + 2, "teardown": len(ob.THE_TEARDOWN_AND_THE_SECOND_PASS) + 2 - 1,
              "launch": len(ob.THE_LAUNCH_PASS) + 2, "built-in": len(ob.A_BUILT_IN_PASS) + 1 + 2}


def _kind(label):
    return "first" if label.startswith("the first") else "teardown" if "teardown" in label else "launch" if "launch" in label else "built-in"


@every_blob
@every_pass
def test_labelled_staging_both_shores_arrive_at_every_checkpoint_in_one_order_with_the_rom_s_machine_and_stores(label, blob):
    """EVERY CHECKPOINT OF A PASS, ON BOTH SHORES (the our-boot machine: A LABELLED STAGING; a pass after deskmain: THE
    SERVED DOOR, A LABELLED ARGUMENT CLASS — both in this test's ids): the two runs arrive at the same checkpoints IN
    THE SAME ORDER (each of the pass's, and the returns of the reader and of sh_cmd); AT EACH, OUR MEGABYTE IS THE
    ROM'S — every code address mapped back, nothing differing outside the classes, the LIVE classes that differ
    exactly the ones the rule names there; BETWEEN TWO, THE SAME BYTES STORED on both shores outside the classes (a
    silent store counts: the ledgers are compared, not the values) but the one named above; and WHO RAN to where the
    pass ends — at deskmain, or before it — is ours alone."""
    a_pass = THE_PASSES[label]
    both = ob.both_shores(a_pass, the_blob(blob))
    in_ours, in_the_rom_s, the_rom_s_own = ob.who_ran(both)
    assert in_ours > 0 and in_the_rom_s == 0 and the_rom_s_own > 0
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    assert list(the_rom_s) == list(ours) and len(ours) == ARRIVED_AT[_kind(label)], list(ours)
    assert both.ours.ended.what == a_pass.until and both.ours.ended.sp == both.the_rom_s.ended.sp, "one stack pointer where the pass ends"
    in_gem_entry = both.ours.ended.tally[ob.IN_GEM_ENTRY_ITSELF]        # ...its own instructions: the pin's bytes, run — the ROM's cycles
    assert in_gem_entry == both.the_rom_s.ended.tally[ob.IN_GEM_ENTRY_ITSELF] and bool(in_gem_entry) == (_kind(label) in ("first", "teardown"))
    assert [served.routine for served in both.ours.served] == [routine for routine, _answer in a_pass.serving] == [
        served.routine for served in both.the_rom_s.served]
    live, before = live_at(a_pass, list(ours)), None
    for what in ours:
        who = f"{label}, at {what} ({blob})"
        ob.vet_alike(who, the_rom_s[what], ours[what], both.blob, live[what])
        classes = ob.classes_at(the_rom_s[what], ours[what], (both.blob.base, both.blob.end))
        left_out = [span for spans in classes.values() for span in spans]
        only_the_rom_s, only_ours = ob.stores_differing(both, before, what, left_out)
        assert tuple(only_the_rom_s) == THE_ROM_ALONE_STORES.get((label, what), ()) and not only_ours, (
            f"{who}: since {before} the ROM's run alone stored at {[f'{at:#x}' for at in only_the_rom_s[:8]]} and ours "
            f"alone at {[f'{at:#x}' for at in only_ours[:8]]}")
        before = what


def test_labelled_staging_a_class_named_and_not_needed_and_a_difference_outside_the_classes_are_both_refused():
    """THE COMPARISON'S OWN REDS, on the shipped blob: at deskmain's entry named WITHOUT a live class the machines
    differ in, or — at gem_entry's loop's top, where they differ in none — WITH one (PD0's frames: the stack is not
    taken yet), it is refused by name; and A STORE THAT IS NO CLASS'S — one byte of the AES's own state changed on
    our shore's megabyte (a labelled craft) — is a difference outside the classes, shown with both shores' bytes."""
    both = ob.both_shores(THE_FIRST_PASSES[BLANK], the_blob(SHIPPED))
    every_rom_s, every_ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    the_rom_s, ours = every_rom_s[ob.DESKMAIN_ENTERED], every_ours[ob.DESKMAIN_ENTERED]
    ob.vet_alike("as it is", the_rom_s, ours, both.blob, FRAMES + MANAGER)
    with pytest.raises(ob.Refused, match="a class named and not needed, or needed and not named"):
        ob.vet_alike("one short", the_rom_s, ours, both.blob, FRAMES)
    ob.vet_alike("as it is, in gem_entry", every_rom_s[ob.THE_LOOP], every_ours[ob.THE_LOOP], both.blob, ())
    with pytest.raises(ob.Refused, match="a class named and not needed, or needed and not named"):
        ob.vet_alike("one too many", every_rom_s[ob.THE_LOOP], every_ours[ob.THE_LOOP], both.blob, FRAMES)
    changed = bytearray(ours.ram)
    changed[A_WORD_OF_THE_AES_S_STATE + 1] ^= 1
    with pytest.raises(ob.Refused, match=rf"OUR MACHINE IS NOT THE ROM'S outside the classes — 1 byte\(s\) in 1 run\(s\)"
                                         rf".*{A_WORD_OF_THE_AES_S_STATE + 1:#x}"):
        ob.vet_alike("a store of no class", the_rom_s, ours._replace(ram=bytes(changed)), both.blob, FRAMES + MANAGER)


def test_labelled_craft_where_the_two_shores_stand_and_how_a_run_ends_are_refused_each_by_name(monkeypatch):
    """THE REFUSALS OF THE CLASSES' OWN GEOMETRY AND OF A WATCHED RUN, EACH WITH ITS RED — LABELLED CRAFTS, every one:
    two real stops of the shipped blob's first pass with ONE STACK POINTER MOVED (never a machine a run made), a
    megabyte with `savptr` moved, a stretch's stops cut short, the kit's ledger said full.
      * one shore on gem_entry's first stack and the other not (the loop's top, ours moved to PD0's top);
      * the two shores not both on PD0's stack (deskmain's entry, ours moved above its top);
      * a checkpoint taken on the dispatcher's stack (its frames are live there: no class of a process applies);
      * TWO CLASSES THAT OVERLAP (the BIOS's register-save pointer laid at GEMDOS's stack's top: its frame's class
        then lies inside GEMDOS's own) — a byte left out twice is one a comparison no longer places;
      * a stretch that ENDS INSIDE ANOTHER PROCESS'S TURN (gem_main's stretch cut at the screen manager's entry);
      * A SATURATED WRITE LEDGER (the kit's answer replaced): what a run stored between two checkpoints is not known."""
    both = ob.both_shores(THE_FIRST_PASSES[BLANK], the_blob(SHIPPED))
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    span = (both.blob.base, both.blob.end)
    (_first_lo, first_top), (_pd0_lo, pd0_top) = pinned.THE_FIRST_STACK_S, pinned.PD0_S
    dispatcher_lo, dispatcher_top = aes_event.DISPATCHER_STACK
    in_the_loop, at_the_desk = (the_rom_s[ob.THE_LOOP], ours[ob.THE_LOOP]), (the_rom_s[ob.DESKMAIN_ENTERED], ours[ob.DESKMAIN_ENTERED])
    assert in_the_loop[0].sp == in_the_loop[1].sp == first_top and not dispatcher_lo <= pd0_top + LONG_BYTES <= dispatcher_top
    with pytest.raises(ob.Refused, match="one shore stands on gem_entry's first stack and the other does not"):
        ob.classes_at(in_the_loop[0], in_the_loop[1]._replace(sp=pd0_top), span)
    with pytest.raises(ob.Refused, match=rf"the two shores stand at SP {at_the_desk[0].sp:#x} and {pd0_top + LONG_BYTES:#x}: not both on PD0's stack"):
        ob.classes_at(at_the_desk[0], at_the_desk[1]._replace(sp=pd0_top + LONG_BYTES), span)
    with pytest.raises(ob.Refused, match="a checkpoint taken ON THE DISPATCHER'S STACK"):
        ob.classes_at(at_the_desk[0], at_the_desk[1]._replace(sp=dispatcher_lo + LONG_BYTES), span)
    moved = bytearray(at_the_desk[0].ram)
    moved[addrs.SYSVAR_SAVPTR:addrs.SYSVAR_SAVPTR + LONG_BYTES] = struct.pack(">I", aes_boot.preinit_snapshot.GEMDOS_STACK_TOP)
    with pytest.raises(ob.Refused, match="two classes of one comparison overlap at deskmain"):
        ob.compared(at_the_desk[0]._replace(ram=bytes(moved)), at_the_desk[1], both.blob)
    stops = ob.between(both.the_rom_s, ob.GEM_MAIN, ob.DESKMAIN_ENTERED)
    own = ob.THE_START_UP_S_PROCESS
    entered = next(index for index, stop in enumerate(stops) if stop.what == ob.A_SWITCH and stop.running != own)
    assert len(ob.turns_in(stops, own)) == 1
    with pytest.raises(ob.Refused, match="the stretch ends inside another process's turn"):
        ob.turns_in(stops[:entered + 1], own)
    monkeypatch.setattr(ob.emu, "bench_writes", lambda _memory: ((), True))
    to_the_copy = ob.Pass("a labelled craft: the kit's ledger said full", BLANK, ob.THE_FIRST_PASS[:1], ob.THE_COPY_MADE)
    with pytest.raises(ob.Refused, match="the watched run's write ledger saturated"):
        ob.watched(to_the_copy)


# A WATCHED RUN'S PROFILE IS ITS OWN FROM ITS FIRST TALLY (band 6 slice F4's prep, review RF4P's F1): the tallies' module
# (`bench/tier3.py`), imported cold, derives kept answers, and one SAMPLED to be made again (`derived._sampled`) is a
# profiled step of its own (`aes_desk.stepped`: vetted free, reset, on — and OFF). Inside a watched run's first tally
# that left the ROM's shore 0 cycles in its own text — red on whichever worker's salt sampled one first.
TO_THE_COPY = ob.Pass("a labelled craft: the boot's first pass to the Line-F handler's copy", BLANK, ob.THE_FIRST_PASS[:1],
                      ob.THE_COPY_MADE)
A_KEPT_ANSWER_MADE_AGAIN = "a kept answer made again, a labelled craft"   # (no regex metacharacter: matched below)


def _a_kept_answer_made_again():
    """A LABELLED CRAFT: what a sampled kept answer made again does to the profile — `aes_desk.stepped`'s own frame."""
    aes_event.vet_the_profile_is_free(A_KEPT_ANSWER_MADE_AGAIN)
    ob.emu.prof_reset()
    ob.emu.prof_enable(True)
    ob.emu.prof_enable(False)


def test_labelled_craft_a_watched_run_imports_the_tallies_module_before_its_profile_is_on():
    """THE TALLIES' MODULE COLD: its first `bench_tier3()` of the process makes a kept answer again (the craft) — the
    watched run asks it before its profile is on, so the ROM's shore still tallies its own text."""
    tier3, cold = bench_tier3(), [True]

    def imported_cold():
        if cold:
            cold.clear()
            _a_kept_answer_made_again()
        return tier3
    # (not the `monkeypatch` fixture: it switches the kept answers off — the tallies' module would derive cold — and no
    # derivation is patched here)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(ob, "bench_tier3", imported_cold)
        the_rom_s_own = ob.watched(TO_THE_COPY).ended.tally[0]
    assert not cold and the_rom_s_own > 0, f"the ROM's shore tallied {the_rom_s_own} cycles in its own text"


def test_labelled_craft_a_profiled_run_a_watched_run_s_tally_asks_for_is_refused_by_name():
    """A PROFILED RUN INSIDE A WATCHED ONE, asked by its tally — its very first reading too — is refused by name: the
    run's profile is held from that reading on (`aes_event.profile_held`)."""
    def a_tally_that_makes_one():
        _a_kept_answer_made_again()
        return ob.the_rom_s_tally()
    memory, registers, disk, io, _ours = ob.began_at(TO_THE_COPY, None)
    with pytest.raises(AssertionError, match=f"A PROFILED RUN INSIDE ANOTHER: {A_KEPT_ANSWER_MADE_AGAIN}"):
        ob.watched_over(memory, registers, disk, io, None, ob.places_of(TO_THE_COPY.checkpoints, None), ob.until_of(TO_THE_COPY, None),
                        a_tally_that_makes_one)


# ---- gem_entry's ARMS (ruling W4-R5) ----------------------------------------------------------------------------------------------
LINE_F_VECTOR = addrs.VECTOR_LINE_F


@every_blob
def test_labelled_staging_gem_entry_s_arms_are_the_rom_s_at_each_checkpoint(blob):
    """gem_entry's OWN ARMS, on the our-boot machine, each at its checkpoint (the megabyte there is the ROM's: the
    test above) — said here in what each one is. THE `$2c` TEST, taken: the BIOS's vector had a non-zero high byte,
    so a block was Malloc'ed, OUR hundred bytes copied into it — the ROM's own but its `movea.l #<table>` OURS (band 6's
    binding: `$cc24` our table) — and the vector pointed at the copy. THE CLEAR: THEGLO zero from its first word to the
    count size_theglo answered. THE THREE STORES: `$947a`, `$947e` and `$8c32` hold THE BLOB'S OWN justretf, tick
    glue and trampoline where the ROM's machine holds the ROM's. THE STACK MOVE: UDA0's saved SP and the CPU's are
    PD0's top. And its OWN INSTRUCTIONS' CYCLES are the ROM's to the cycle (the pin's bytes, run)."""
    both = ob.both_shores(THE_FIRST_PASSES[BLANK], the_blob(blob))
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    copy = case.long_in(ours[ob.THE_COPY_MADE].ram, LINE_F_VECTOR)
    assert case.long_in(aes_boot.preinit().ram, LINE_F_VECTOR) >> 24 and not copy >> 24 and copy == case.long_in(the_rom_s[ob.THE_COPY_MADE].ram, LINE_F_VECTOR)
    handler, operand = addrs.AES_ROM_LINEF_HANDLER, aes.LINEF_TABLE_OPERAND
    copied, theirs = ours[ob.THE_COPY_MADE].ram[copy:copy + aes.LINEF_COPY_BYTES], bytes(BASE_IMAGE[handler:handler + aes.LINEF_COPY_BYTES])
    assert copied[:operand] == theirs[:operand] and copied[operand + LONG_BYTES:] == theirs[operand + LONG_BYTES:]
    assert case.long_in(copied, operand) == both.blob.entry("aes_linef_table"), "the copy's table is not the blob's own: the binding"
    assert (copy, copy + aes.LINEF_COPY_BYTES) == aes_boot.LINE_F_COPY, "the span who-ran profiles is where this machine's copy lies"
    cleared = ours[ob.THE_CLEAR]
    words = cleared.registers["a0"] - aes.AES_THEGLO
    assert words > 0 and not any(cleared.ram[aes.AES_THEGLO:cleared.registers["a0"]]) and cleared.registers["a0"] == the_rom_s[ob.THE_CLEAR].registers["a0"]
    moved = ours[ob.THE_STACK_MOVED]
    for declared in aes_event.STORED_BY_GEM_ENTRY:
        (rom, symbol), = declared.symbols.items()
        assert case.long_in(moved.ram, declared.slots[0]) == both.blob.entry(symbol) != rom
        assert case.long_in(the_rom_s[ob.THE_STACK_MOVED].ram, declared.slots[0]) == rom
        assert case.long_in(ours[ob.THE_CLEAR].ram, declared.slots[0]) == 0, "stored after the clear, by the three `lea`s"
    assert moved.sp == pinned.PD0_S[1] == case.long_in(moved.ram, aes.AES_THEGLO + aes.UDA_SUPER_SP) == the_rom_s[ob.THE_STACK_MOVED].sp
    assert both.ours.ended.tally[ob.IN_GEM_ENTRY_ITSELF] == both.the_rom_s.ended.tally[ob.IN_GEM_ENTRY_ITSELF] > 0


@every_blob
def test_labelled_staging_labelled_craft_the_skip_arm_of_the_vector_test_is_the_rom_s(blob):
    """THE `$2c` TEST'S SKIP ARM HAS NO MACHINE — gem_entry is entered ONCE, and its loop's `bra` goes back to
    `$fd9f72`, past the test: no second pass reaches it (the design took it for the second pass's; read, and held by
    the served teardown's checkpoints, which never arrive there). So A LABELLED CRAFT: the pre-init machine with the
    Line-F vector's high byte made zero (the address kept), both shores entered — and at the next checkpoint both
    stand with NO block taken and the vector as it was: the megabyte the ROM's, the pool untouched."""
    capture, disk = aes_boot.preinit(), aes_boot.blank_disk()
    crafted = bytearray(capture.ram)
    crafted[LINE_F_VECTOR] = 0
    a_pass = ob.Pass("a labelled craft: the vector's high byte zero", BLANK, ob.THE_FIRST_PASS[:1], ob.THE_COPY_MADE)
    runs = {}
    for shore in (None, the_blob(blob)):
        memory, registers, _disk, io, ours = ob.began_at(a_pass, shore)
        memory[:aes_boot.RAM_BYTES] = crafted
        if ours is not None:
            memory[ours.base:ours.base + len(ours.image)] = ours.image
        tally = ob.the_rom_s_tally if shore is None else ob.our_tally(shore)
        runs[shore is None] = ob.watched_over(memory, registers, disk, io, ours, ob.places_of(a_pass.checkpoints, shore), ob.until_of(a_pass, shore), tally)
    the_rom_s, ours = runs[True].ended, runs[False].ended
    ob.vet_alike(f"the skip arm ({blob})", the_rom_s, ours, the_blob(blob), ())
    assert case.long_in(ours.ram, LINE_F_VECTOR) == case.long_in(crafted, LINE_F_VECTOR) and not case.long_in(ours.ram, LINE_F_VECTOR) >> 24
    taken = ob.checkpoints_of(ob.both_shores(THE_FIRST_PASSES[BLANK], the_blob(blob)).ours)[ob.THE_COPY_MADE]
    assert ours.instructions < taken.instructions, "no Malloc, no copy: fewer instructions than the arm a boot takes"
    assert ours.instructions == the_rom_s.instructions and ours.cycles == the_rom_s.cycles, "the pin's bytes, run: one cost"


# ---- A TEXT CELL HIGHER THAN IT IS WIDE: A LABELLED CRAFT, for the band's widths ---------------------------------------------------
# gem_main sizes the launch band's three first objects by the cell's WIDTH and its root, its bar and its text by the
# cell's HEIGHT (`$fda304..$fda38c`). EVERY MACHINE A BOOT MAKES HERE IS THE COLOUR SCREEN'S: its cell is 8 x 8, so a
# build that took the height for the width would leave the same megabyte (the first review's A6 survived the first
# pass's checkpoints for that, and no capture boots the monochrome screen: a resolution pair that asks it leaves the
# device model). So A LABELLED CRAFT, ON BOTH SHORES: where each run arrives at fs_start — the last callee before the
# band is sized — the cell's height is made TWICE its width (the word `gl_hchar`), and both run on to the first
# dispatch and the shell's entry: the megabyte the ROM's at each, the stores the ROM's.
THE_CELL_S_WIDTH, THE_CELL_S_HEIGHT = aes.AES_GL_WCHAR, aes.AES_GL_HCHAR
A_HIGHER_CELL = 16


def _with_a_higher_cell(disk=BLANK):
    crafted = (("fs_start", ((THE_CELL_S_HEIGHT, struct.pack(">H", A_HIGHER_CELL)),)),)
    until = next(index for index, checkpoint in enumerate(ob.THE_FIRST_PASS) if checkpoint.what == ob.SH_MAIN)
    return ob.Pass(f"A LABELLED CRAFT (the text cell made {A_HIGHER_CELL} high where fs_start is entered): the first pass to the "
                   f"shell's entry, {disk}", disk, ob.THE_FIRST_PASS[:until + 1], ob.SH_MAIN, crafted=crafted)


@every_blob
def test_labelled_staging_labelled_craft_the_band_is_sized_by_a_cell_higher_than_wide_as_the_rom_sizes_it(blob):
    """THE BAND'S SIZES OVER A CELL THAT IS NOT SQUARE (the craft above, on both shores): the machine a boot makes has
    a cell as wide as it is high — said first, off both shores' megabytes: that is why the plain checkpoints cannot
    tell the two apart —; with the height made twice the width at fs_start's entry, both shores arrive at the first
    dsptch and at the shell's entry with THE ROM'S MEGABYTE and THE ROM'S STORES, and the band's objects hold a width
    of cells across by the cell's WIDTH and heights of the cell's HEIGHT."""
    a_pass = _with_a_higher_cell()
    both = ob.both_shores(a_pass, the_blob(blob))
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    assert list(the_rom_s) == list(ours) and ob.who_ran(both)[1] == 0
    made = ours["fs_start"].ram
    assert case.word_in(made, THE_CELL_S_WIDTH) == case.word_in(made, THE_CELL_S_HEIGHT) == A_HIGHER_CELL // 2, "the boot's own cell: square"
    live, before = live_at(a_pass, list(ours)), None
    for what in ours:
        ob.vet_alike(f"a higher cell, at {what} ({blob})", the_rom_s[what], ours[what], both.blob, live[what])
        classes = ob.classes_at(the_rom_s[what], ours[what], (both.blob.base, both.blob.end))
        assert ob.stores_differing(both, before, what, [span for spans in classes.values() for span in spans]) == ([], []), what
        before = what
    sized = ours["dsptch"].ram
    band, columns = case.long_in(sized, aes.AES_AD_STDESK) & BUS, case.word_in(sized, aes.AES_GL_NCOLS)
    assert case.word_in(sized, THE_CELL_S_HEIGHT) == A_HIGHER_CELL and columns > 0
    assert case.word_in(sized, band + aes.OB_WIDTH) == columns * (A_HIGHER_CELL // 2), "cells across by the cell's WIDTH"
    assert case.word_in(sized, band + aes.OB_HEIGHT) % A_HIGHER_CELL == 0, "...and its root as high as cells down by the cell's HEIGHT"


# ---- (3) THE CLASSES: the dead ones proved dead; every code address mapped, each mapping needed ----------------------------------
NOISE_SEEDS = (1, 0x5eed)
A_SERVED_ROUTINE_HAS_NO_RUN_BEHIND_IT = tuple(ob.THE_BUILT_INS)     # a pair that begins where a routine is answered
NOISE_REACHES = {"d2", "sr"}            # the condition codes parked with a mask come back in SR — and in D2, where the
#                                         Line-F handler keeps the caller's status word: flags and a scratch register
NOISE_REACHES_ON_OURS = {"sr"}          # ...and OUR build runs no Line-F handler: the flags alone
NOISED_PASSES = {label: a_pass for label, a_pass in THE_PASSES.items() if INF_CHANGED not in label and "$fc" not in label and "$fb" not in label}


@every_blob
@pytest.mark.parametrize("label", NOISED_PASSES)
def test_labelled_staging_every_dead_class_is_dead_at_every_checkpoint_the_rom_s_own_run_over_noise(label, blob):
    """THE DEAD CLASSES ARE DEAD — proved AT EVERY CHECKPOINT of a pass, on THE ROM'S OWN MACHINE: the spans the
    comparison there leaves out for a dead class (as the two shores' stack pointers place them) filled with noise, the
    ROM's code run on from that stop to the next checkpoint — where it arrives with THE SAME MACHINE outside those
    spans and the classes there, and the same registers but the flags and D2 (the parked condition codes ARE read
    back into the status register: they are the flags of an instruction long gone, and decide nothing). Two seeds."""
    _every_pair_proved_over_noise(label, blob, on_ours=False)


def _every_pair_proved_over_noise(label, blob, on_ours):
    """EVERY pair of consecutive checkpoints of the pass but those that begin where a routine is ANSWERED, counted."""
    both = ob.both_shores(THE_PASSES[label], the_blob(blob))
    names = list(ob.checkpoints_of(both.the_rom_s))
    assert names == list(ob.checkpoints_of(both.ours))
    pairs = [(since, until) for since, until in zip(names, names[1:]) if since not in A_SERVED_ROUTINE_HAS_NO_RUN_BEHIND_IT]
    assert len(pairs) == len(names) - 1 - len(THE_PASSES[label].serving), "one pair a checkpoint, less the one a served routine begins"
    for since, until in pairs:
        for seed in NOISE_SEEDS:
            differing, registers, noised = ob.noise_proved(both, since, until, seed, on_ours=on_ours)
            assert not differing and set(registers) <= (NOISE_REACHES_ON_OURS if on_ours else NOISE_REACHES) and noised > 0, (
                f"{label} ({blob}, {'OUR' if on_ours else 'the ROM' + chr(39) + 's'} shore): noise in the dead classes at {since} reaches "
                f"{until} — the machine differs at {[(f'{at:#x}', length) for at, length in differing[:6]]}, the registers {registers}")


@every_blob
@pytest.mark.parametrize("label", NOISED_PASSES)
def test_labelled_staging_every_dead_class_is_dead_at_every_checkpoint_our_own_run_over_noise(label, blob):
    """...AND DEAD FOR OUR BUILD TOO — the ROM's shore cannot say that OUR code never reads those bytes. THE SAME PROOF
    ON OUR SHORE, at every checkpoint of the pass, both blobs, two seeds: the dead classes noised, OUR build run on
    from its own stop to the next checkpoint, and compared with its own plain run there UNDER THE STRICTER LEAVE-OUT
    — the dead classes and the blob alone; the LIVE classes (PD0's frames, the screen manager's context and stack)
    are COMPARED: one build's frames are the same bytes on two runs of it. A C change that came to read residue —
    an uninitialised local, a register saved before it is set — reddens here."""
    _every_pair_proved_over_noise(label, blob, on_ours=True)


def test_labelled_staging_noise_in_a_live_longword_is_found_where_the_run_arrives():
    """THE NOISE PROOF'S OWN RED: the same run of the ROM's — from the reader's entry to its return, on the DESKTOP.INF
    machine — with ONE LIVE LONGWORD OF THE AES'S STATE noised beside the dead classes (the keyboard's owner, which
    nothing in that stretch stores) arrives with exactly those four bytes differing; without it, with none."""
    both = ob.both_shores(THE_FIRST_PASSES[INF], the_blob(SHIPPED))
    owner = aes.header_constants("wmupdate.h")["AES_GL_KOWNER"]
    for on_ours in (False, True):       # ...on either shore
        assert ob.noise_proved(both, ob.THE_READER, READER_RETURNED, 1, on_ours=on_ours)[:2] == ((), [])
        differing, _registers, _noised = ob.noise_proved(both, ob.THE_READER, READER_RETURNED, 1, also=((owner, owner + LONG_BYTES),),
                                                         on_ours=on_ours)
        assert differing == ((owner, LONG_BYTES),)


# WHAT IS MAPPED AT deskmain's ENTRY, AND NEEDED THERE — each declaration of the registry whose slots hold a blob
# address where our boot arrives (un-mapped, the two machines differ in exactly its slots), and the one longword that
# is no declaration: the first stack's top, a code address of gem_entry's.
GEM_ENTRY_S_THREE = tuple(declared.what for declared in aes_event.STORED_BY_GEM_ENTRY)
NEEDED_AT_THE_DESK = {aes_event.GLUE_CODES.what, aes_event.SCREEN_MANAGER_ENTRY.what, aes_event.GEM_TRAP_VECTOR.what,
                      aes_event.CRITICAL_ERROR_VECTOR.what, *GEM_ENTRY_S_THREE,
                      aes_event.LINEF_TABLE_SLOT.what}     # (band 6's binding: our gem_entry's copy stored our table)


@every_blob
def test_labelled_staging_each_mapping_is_needed_where_our_boot_arrives_and_gem_entry_s_three_are_proved_by_its_own_run(blob):
    """A MAPPING NOBODY WOULD MISS IS NOT A MAPPING: at deskmain's entry on the our-boot machine, EACH declaration of
    the registry left unmapped in turn makes the two machines differ — in its own slots and nowhere else — and so
    does the first stack's top longword (`$8990`, the return address of gem_entry's `jsr` of size_theglo: mapped
    through gem_entry's own offsets). THE THREE THIS SLICE ACTIVATED are among them, stored by OUR gem_entry in this
    same run (the registry's `MAPPING_PROVED_BY`: the rows of gem_main's stretches end here). A declaration whose
    slots hold nothing of ours yet there (the fork queue's, a program's first-entry frame) is needed by no one —
    and un-mapping it changes nothing."""
    both = ob.both_shores(THE_FIRST_PASSES[BLANK], the_blob(blob))
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s)[ob.DESKMAIN_ENTERED], ob.checkpoints_of(both.ours)[ob.DESKMAIN_ENTERED]
    assert not ob.compared(the_rom_s, ours, both.blob).differing
    needed = set()
    for relocation in ob.relocations_of(both.blob):
        differing = ob.compared(the_rom_s, ours, both.blob, without=(relocation.what,)).differing
        slots = set(aes_event.slots_over(relocation, ours.ram))
        assert all(at - at % 2 in slots or at - at % 2 - 2 in slots for at, _length in differing), relocation.what
        if differing:
            needed.add(relocation.what)
    assert needed == NEEDED_AT_THE_DESK
    proved_here = (*GEM_ENTRY_S_THREE, aes_event.LINEF_TABLE_SLOT.what)
    assert {what: aes_event.MAPPING_PROVED_BY[what] for what in proved_here} == dict.fromkeys(proved_here, ("aes_rom_gem_main",))
    assert all(row.symbol == "aes_rom_gem_main" for row in bench_tier3().ROWS if row.address == GEM_MAIN) and not aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3
    top = ob.THE_FIRST_STACK_S_TOP_LONGWORD
    assert [at for at, _length in ob.compared(the_rom_s, ours, both.blob, without=(top,)).differing] == [top + 1]


@every_blob
def test_labelled_staging_the_usable_disk_longword_is_a_code_address_s_half_mapped_and_never_dropped(blob):
    """`$8990..$8993` — THE CLASS OF ITS OWN. The usable-disk word the reader tests is the low half of a longword of
    gem_entry's FIRST STACK: at the loop's top it holds THE HIGH WORD of rom_rsc_init's return address over the 1
    gem_entry stored; from the `jsr` of size_theglo on, that call's WHOLE return address — the blob's own on our
    shore (`$9f78` in the ROM: its low word non-zero on both blobs), the ROM's by gem_entry's own offsets once mapped.
    Compared exactly at every checkpoint; in no class; the reader READS it — the DESKTOP.INF machine reads its file."""
    both = ob.both_shores(THE_FIRST_PASSES[INF], the_blob(blob))
    the_rom_s, ours = ob.checkpoints_of(both.the_rom_s), ob.checkpoints_of(both.ours)
    top, start = ob.THE_FIRST_STACK_S_TOP_LONGWORD, both.blob.entry(aes_boot.GEM_ENTRY_SYMBOL)
    returns_to = ob.THE_LOOP_S_TOP + WORD_BYTES + LONG_BYTES
    assert case.long_in(the_rom_s[ob.THE_LOOP].ram, top) == ob.RSC_INIT_RETURNS_TO >> ob.HIGH_WORD << ob.HIGH_WORD | ob.GEM_DISK_USABLE
    ours_returns_to = start + ob.RSC_INIT_RETURNS_TO - ob.GEM_ENTRY
    assert case.long_in(ours[ob.THE_LOOP].ram, top) == ours_returns_to >> ob.HIGH_WORD << ob.HIGH_WORD | ob.GEM_DISK_USABLE
    for what in list(ours)[list(ours).index(ob.THE_CLEAR):]:
        assert case.long_in(the_rom_s[what].ram, top) == returns_to == 0xfd9f78
        assert case.long_in(ours[what].ram, top) == start + returns_to - ob.GEM_ENTRY and case.word_in(ours[what].ram, top + WORD_BYTES)
        spans = [span for spans in ob.classes_at(the_rom_s[what], ours[what], (both.blob.base, both.blob.end)).values() for span in spans]
        assert not any(lo < top + LONG_BYTES and top < hi for lo, hi in spans), f"at {what} a class covers the longword"
    assert both.ours.ended.registers["pc"] == aes_boot.deskmain_entry(aes_boot.ours_of(both.blob)), "...and the boot that read its DESKTOP.INF arrived"


# ---- (4) THE TWO STACK GATES, ON THE OUR-BOOT MACHINE: bound and measured (rulings W4-R9, W4-R4) ---------------------------------
THE_SHELL_IS_ENTERED_AT = pinned.PD0_S[1] - pinned.THE_BUILD_ENTERS_SH_MAIN            # `$a392`
THE_MARGINS = {ob.DESKMAIN_ENTERED: 26, ob.DOS_EXEC_ENTERED: 22, **dict.fromkeys(ob.THE_BUILT_INS, 20)}
# (the two file built-ins are handed one longword — `$a356` less its return address —, the two disk ones two)
THE_ROM_ENTERS = {ob.DESKMAIN_ENTERED: 0xa364, ob.DOS_EXEC_ENTERED: 0xa35e, ob.SHOW_FILE: 0xa352, ob.PRINT_FILE: 0xa352,
                  ob.FORMAT: 0xa34e, ob.COPY_DISK: 0xa34e}


# EACH CALL OUT OF THE SHELL, and the pass whose run arrives at it: deskmain on the boot's own first pass; through the
# served door dos_exec (the launch pass) and each of the desk's four built-ins.
THE_CALLS_OUT_OF_THE_SHELL = {ob.DESKMAIN_ENTERED: THE_FIRST_PASSES[BLANK], ob.DOS_EXEC_ENTERED: THE_LAUNCH, **THE_BUILT_IN_PASSES}


@every_blob
@pytest.mark.parametrize("disk", (BLANK, INF))
def test_labelled_staging_the_first_stack_gate_holds_on_the_our_boot_machine_bound_and_measured(disk, blob):
    """THE FIRST-STACK GATE (ruling W4-R9) ON THE OUR-BOOT MACHINE, both disks: gem_entry's first stack is 134 bytes;
    the build's reading bounds what it takes at 88 and ITS OWN BOOT TAKES 88 — the bound, to the byte, 46 spare —
    where the ROM's own boot of the same disk takes 84. (No interrupt lands there on the oracle's boots; one that
    does on a machine pushes under whichever is deeper: the finding stands, uncharged — STATUS, AWAITING 21.)"""
    both = ob.both_shores(THE_FIRST_PASSES[disk], the_blob(blob))
    bound, _chain = aes_stack.first_stack_bound(both.blob)
    assert ob.first_stack_used(both.ours) == bound == pinned.THE_FIRST_STACK_BOUND == 88
    assert pinned.THE_FIRST_STACK_S_SPAN - bound == pinned.THE_FIRST_STACK_GATE_S_MARGIN == 46 and pinned.THE_FIRST_STACK_S_SPAN == 134
    assert ob.first_stack_used(both.the_rom_s) == pinned.THE_ROM_S_FIRST_STACK_USE == 84


@every_blob
def test_labelled_staging_the_rom_depth_rule_holds_at_every_door_deskmain_served_bound_and_measured(blob):
    """THE ROM-DEPTH RULE (ruling W4-R4) ON THE OUR-BOOT MACHINE, AT EVERY CALL OUT OF THE SHELL — deskmain on the
    boot's own first pass; through the served door (AN ARGUMENT CLASS) dos_exec and each of the desk's four
    built-ins: THE CALLEE IS ENTERED ON THE ROM'S OWN STACK POINTER (`$a364`, `$a35e`, `$a352` / `$a34e`), and THE DOOR'S MARGIN
    — the stack pointer our frames stood at, which the door keeps in D3 for the call, above the lowest its vet lets
    them stand — IS THE BOUND'S: 26 / 22 / 20. The shell itself is entered at `$a392` where the ROM's is at `$a382`."""
    the_build = the_blob(blob)
    passes = THE_CALLS_OUT_OF_THE_SHELL
    bound = {(call.function, call.floor - call.ours): pinned.PD0_S[1] - call.floor for call in aes_stack.desk_door_calls(the_build)}
    assert sorted(margin for _function, margin in bound) == sorted(set(THE_MARGINS.values()))
    for callee, a_pass in passes.items():
        both = ob.both_shores(a_pass, the_build)
        the_rom_s, ours = ob.checkpoints_of(both.the_rom_s)[callee], ob.checkpoints_of(both.ours)[callee]
        assert ours.sp == the_rom_s.sp == THE_ROM_ENTERS[callee], callee
        function = "aes_sh_main" if callee in (ob.DESKMAIN_ENTERED, ob.DOS_EXEC_ENTERED) else "aes_sh_cmd"
        assert ob.kept_at_the_door(ours) - bound[function, THE_MARGINS[callee]] == THE_MARGINS[callee], callee
    first = ob.both_shores(THE_FIRST_PASSES[BLANK], the_build)
    entered = [ob.checkpoints_of(run)[ob.SH_MAIN].sp for run in (first.ours, first.the_rom_s)]
    assert entered == [THE_SHELL_IS_ENTERED_AT, pinned.PD0_S[1] - pinned.THE_ROM_ENTERS_SH_MAIN] == [0xa392, 0xa382]


# ---- THE ARGUMENTS HANDED THROUGH THE DESK DOOR: what each callee will read, compared exactly on its own -------------------------
_SHELL = aes.header_constants("shell.h")
THE_TAIL_S_TEXT, LOAD_AND_GO = _SHELL["AES_SH_TAIL_TEXT"], _SHELL["SH_PEXEC_LOAD_AND_GO"]
THE_COMMAND, THE_TAIL = aes.CONSTANTS["AES_SHELL_BUFFER"], aes.CONSTANTS["AES_SHELL_TAIL"]      # each a longword: where the text lies
# WHAT THE ROM'S CALLER LAYS FOR EACH, lowest first (`struct` formats): nothing for deskmain; dos_exec the command, the
# mode word and the tail; a file built-in the tail's text; a disk built-in the tail's text and the command.
HANDED_AS = {ob.DESKMAIN_ENTERED: ">", ob.DOS_EXEC_ENTERED: ">IhI", ob.SHOW_FILE: ">I", ob.PRINT_FILE: ">I", ob.FORMAT: ">II", ob.COPY_DISK: ">II"}


def _the_rom_hands(callee, ram):
    """The arguments the ROM's own instructions hand `callee` over the machine `ram` (the shell's two pointers read there)."""
    command, tail = case.long_in(ram, THE_COMMAND), case.long_in(ram, THE_TAIL)
    return {ob.DESKMAIN_ENTERED: (), ob.DOS_EXEC_ENTERED: (command, LOAD_AND_GO, tail), ob.SHOW_FILE: (THE_TAIL_S_TEXT,),
            ob.PRINT_FILE: (THE_TAIL_S_TEXT,), ob.FORMAT: (THE_TAIL_S_TEXT, command), ob.COPY_DISK: (THE_TAIL_S_TEXT, command)}[callee]


@every_blob
def test_labelled_staging_argument_class_each_callee_out_of_the_shell_is_handed_the_rom_s_arguments(blob):
    """THE ARGUMENTS HANDED THROUGH THE DESK DOOR, ON THE OUR-BOOT MACHINE (A LABELLED STAGING; dos_exec's and the
    built-ins' passes through the served door: AN ARGUMENT CLASS) — at each callee's entry both shores stand on ONE
    stack pointer, and THE BYTES THE CALLEE WILL READ above its return address are THE ROM'S, compared exactly and
    by themselves (the megabyte's compare leaves them out with the rest of PD0's live frames): nothing for deskmain;
    dos_exec the command, the load-and-go mode word and the tail; a file built-in the tail's text; a disk built-in
    the tail's text THEN the command. ITS RED (a labelled craft): Format's two longwords exchanged on our megabyte."""
    for callee, a_pass in THE_CALLS_OUT_OF_THE_SHELL.items():
        both = ob.both_shores(a_pass, the_blob(blob))
        the_rom_s, ours = ob.checkpoints_of(both.the_rom_s)[callee], ob.checkpoints_of(both.ours)[callee]
        handed = ob.vet_handed_alike(f"{callee} ({blob})", callee, the_rom_s, ours)
        assert len(handed) == struct.calcsize(HANDED_AS[callee]) and struct.unpack(HANDED_AS[callee], handed) == _the_rom_hands(callee, ours.ram)
        fields = struct.unpack(HANDED_AS[callee], handed)
        assert len(set(fields)) == len(fields), f"{callee}: two of its arguments are one value — exchanged, they would be the same bytes"
    at, exchanged = ours.sp + LONG_BYTES, bytearray(ours.ram)       # (the last of them: the disk copy's)
    exchanged[at:at + 2 * LONG_BYTES] = ours.ram[at + LONG_BYTES:at + 2 * LONG_BYTES] + ours.ram[at:at + LONG_BYTES]
    with pytest.raises(ob.Refused, match=rf"IS HANDED OTHER ARGUMENTS THAN THE ROM'S — at SP {ours.sp:#x}"):
        ob.vet_handed_alike("a labelled craft", callee, the_rom_s, ours._replace(ram=bytes(exchanged)))
    with pytest.raises(ob.Refused, match="its arguments cannot be compared address for address"):
        ob.vet_handed_alike("a labelled craft", callee, the_rom_s, ours._replace(sp=ours.sp + LONG_BYTES))


# ---- (5) THE ROWS: each stretch the ROM's on both blobs; the census; the figures a convention does not show ----------------------
BAR = 1.10
ONE_INSTRUCTION_S_CYCLES = 4         # a `nop`'s: the least a run can differ by
FIGURE = ob.A_FIGURE                 # a ratio AS THE TABLE PRINTS IT: every figure below is pinned to those digits, exactly


def key_of(stretch):
    return stretch.routine, stretch.what


def _with_thunks(price):
    return (price.own[0] + price.glue) / price.own[1]


def _net_of_line_f(price):
    return (price.own[0] + price.glue) / (price.own[1] - price.line_f)


def _turns_printed(price):
    """Each turn of another process inside a stretch as `(with its thunks, net of the ROM's Line-F handler)`, printed."""
    return [(FIGURE.format((ours + glue) / the_rom_s), FIGURE.format((ours + glue) / (the_rom_s - line_f)))
            for ours, the_rom_s, glue, _shared, line_f in price.turns]


# ON THE SHIPPED BLOB, WHAT THE TABLE'S CONVENTION DOES NOT SHOW (ruling W4-R11 prints both; F-10, AWAITING 20): each
# row's ratio NET OF THE ROM'S LINE-F HANDLER — ours and its thunks against the ROM's own cycles less the cycles of the
# RAM copy its every internal call goes through — THE LINE THE TABLE PRINTS UNDER EVERY STRETCH. Every stretch's line is
# held to its measured price below (its integers and its printed digits); THE ONES OVER 1.00 ON THE PRINTED DIGITS are
# pinned here, REPORTED, never accepted: every one of these rows is at or under 0.99 by the table's convention.
NET_OF_LINE_F_OVER_1_00 = {     # `{(the routine, the case): the figure the table prints}`
    ("AES_ROM_GEM_MAIN", "the teardown, from the shell's return to its own"): "1.15",
    ("AES_ROM_SH_MAIN", "the desk quits: the shell's last pass, to gem_main's teardown"): "1.27",
    ("AES_ROM_SH_CMD", "the tail's byte $fe: a file shown"): "1.06",
    ("AES_ROM_SH_CMD", "the tail's byte $fd: a file printed"): "1.27",
    ("AES_ROM_SH_CMD", "the tail's byte $fc: Format"): "1.28",
    ("AES_ROM_SH_CMD", "the tail's byte $fb: the disk copy"): "1.28"}
OVER_THE_BAR_NET_OF_LINE_F = {key: figure for key, figure in NET_OF_LINE_F_OVER_1_00.items() if float(figure) > BAR}
# ...and THE SCREEN MANAGER'S FIRST TURN inside gem_main's three stretches that hold one, `(with its thunks, net of the
# handler)` on each blob: under the bar by the convention, OVER IT NET — reported with the rows.
THE_TURN_INSIDE = {SHIPPED: ("0.67", "1.11"), BENCH: ("0.72", "1.21")}
# THE BENCH BLOB'S OWN FIGURES, REPORTED (AWAITING 15: a twin's number, never what ships): on it a boot runs the C TWIN
# of every transcribed core — the byte and string loops, the rectangle atoms, the vector takes — where the shipped
# blob runs the ROM's own instructions. ONE PAIR A STRETCH, `(its ratio with thunks, net of the ROM's Line-F handler)`,
# in the registry's order — each held to its own stretch, exactly (a figure of one pass is never another's).
ON_THE_BENCH_BLOB = dict(zip(map(key_of, STRETCHES), (
    ("1.13", "1.41"), ("1.11", "1.40"), ("0.61", "1.12"), ("1.75", "1.85"),             # gem_main: two first passes, the teardown, the second pass
    ("1.99", "2.02"), ("1.90", "1.95"), ("1.90", "1.95"),                               # the `#E` reader
    ("2.00", "2.03"), ("0.77", "1.25"), ("1.82", "1.88"), ("0.82", "1.02"),             # sh_main: first, last, a built-in and back, a launch
    ("0.52", "1.06"), ("0.98", "1.34"), ("0.95", "1.31"), ("0.95", "1.31"), ("0.45", "0.75"))))     # sh_cmd: $fe, $fd, $fc, $fb, none
assert len(ON_THE_BENCH_BLOB) == len(STRETCHES) == 16 and set(NET_OF_LINE_F_OVER_1_00) <= set(ON_THE_BENCH_BLOB)


@EVERY_STRETCH
def test_labelled_staging_each_stretch_is_the_rom_s_and_under_the_bar_as_it_ships(stretch):
    """A ROW'S OWN DIFFERENTIAL AND ITS PRICE, on the shipped blob (what `bench/tier3.py` prints): both shores arrive at
    its two checkpoints; who ran; the megabyte where it ends the ROM's outside the dead classes and the live ones it
    names; THE OS BOTH RUN ONE NUMBER, inside and outside the screen manager's turn — and its own cycles against the
    ROM's AES text and Line-F handler AT OR UNDER THE BAR, thunks counted, the turn inside it under it by itself."""
    price = ob.priced(stretch, the_blob(SHIPPED))
    assert 0 < price.own[0] and _with_thunks(price) <= BAR, f"{ob.row_name(stretch)}: {price.own} + {price.glue} in thunks"
    assert all((ours + glue) / the_rom_s <= BAR for ours, the_rom_s, glue, _shared, _line_f in price.turns)
    assert price.deepest[0] == price.deepest[1] or stretch.until in (READER_RETURNED, SH_CMD_RETURNED, "gsx_mfree"), (
        "where a stretch ends at a call out of the build, both shores stand at one stack pointer")
    assert price.in_the_rom_s == 0, "what the table's general who-ran guard is handed for the row: measured, and nothing"
    # THE LINE THE TABLE PRINTS UNDER THE ROW IS THIS STRETCH'S MEASURED PRICE — its four integers and its printed digits
    # (and the turn's inside it): the figure that carries the numbers over the bar is read from the table, never beside it.
    net, line = FIGURE.format(_net_of_line_f(price)), ob.stretch_lines_of(ob.THE_TABLE.read_text())[ob.row_name(stretch)]
    assert (line.ours, line.the_rom_s, line.glue, line.line_f, line.net) == (*price.own, price.glue, price.line_f, net), (
        f"{ob.row_name(stretch)}: the table's line net of the ROM's Line-F handler says {line}; the stretch measures "
        f"{price.own} + {price.glue} in thunks, {price.line_f} the handler's: {net}")
    assert _turns_printed(price) == [THE_TURN_INSIDE[SHIPPED]] * stretch.turns == [(turn.with_thunks, turn.net) for turn in line.turns]
    assert (float(net) > 1.00) == (key_of(stretch) in NET_OF_LINE_F_OVER_1_00) and NET_OF_LINE_F_OVER_1_00.get(key_of(stretch), net) == net, (
        f"{ob.row_name(stretch)}: {net} net of the ROM's Line-F handler, and {NET_OF_LINE_F_OVER_1_00.get(key_of(stretch))} pinned — REPORT IT")


@every_blob
def test_labelled_staging_labelled_craft_a_stretch_whose_os_cycles_differ_on_the_two_shores_is_refused(blob, monkeypatch):
    """THE OS BOTH RUN IS HELD TO ONE NUMBER, AND THE HOLD HAS A RED (a labelled craft: our shore's run of the first
    pass as it was measured, but for ONE INSTRUCTION'S CYCLES more where gem_main's stretch ends — cycles that are
    neither the blob's nor the ROM's GEM text's: the OS's): the row is refused by name, never priced."""
    stretch = next(each for each in STRETCHES if each.a_pass == THE_FIRST_PASSES[BLANK])
    both = ob.both_shores(stretch.a_pass, the_blob(blob))
    last = ob.between(both.ours, stretch.since, stretch.until)[-1]
    stops = tuple(stop._replace(cycles=stop.cycles + ONE_INSTRUCTION_S_CYCLES) if stop is last else stop for stop in both.ours.stops)
    monkeypatch.setattr(ob, "both_shores", lambda a_pass, _blob: both._replace(ours=both.ours._replace(stops=stops)))
    with pytest.raises(ob.Refused, match="THE OS BOTH RUN is not one number"):
        ob.priced(stretch, the_blob(blob))
    # ...and WHO RAN IS ASKED AT THE ROW (a labelled craft: the ROM's own run of the pass handed over AS OURS) — a stretch
    # of a run that spent its cycles in the ROM's GEM text is refused for that, before anything of it is priced.
    monkeypatch.setattr(ob, "both_shores", lambda a_pass, _blob: both._replace(ours=both.the_rom_s))
    with pytest.raises(ob.Refused, match=r"WHO RAN: our run spent [1-9]\d* cycles IN THE ROM'S OWN GEM TEXT .* and 0 in the blob"):
        ob.priced(stretch, the_blob(blob))
    # ...and A PIN OF THE TURNS INSIDE IT that the run does not make is refused too (the table's lines are counted by it).
    monkeypatch.undo()
    with pytest.raises(ob.Refused, match=r"1 turn\(s\) of another process on the ROM's shore, 1 on ours, 0 pinned"):
        ob.priced(stretch._replace(turns=0), the_blob(blob))


@EVERY_STRETCH
def test_labelled_staging_each_stretch_is_the_rom_s_on_the_bench_blob_too_its_twins_figures_reported(stretch):
    """...AND ON THE BENCH BLOB, where every transcribed core's C TWIN runs in its place: the same differential, held —
    and its price REPORTED, not gated (a twin's number: what ships is the row above). Over the bar there: gem_main's
    stretches, the reader's and the shell's passes that reach the resource's and the band's loops."""
    price = ob.priced(stretch, the_blob(BENCH))
    measured = FIGURE.format(_with_thunks(price)), FIGURE.format(_net_of_line_f(price))
    assert measured == ON_THE_BENCH_BLOB[key_of(stretch)], (
        f"{ob.row_name(stretch)} on the bench blob: {measured} (with thunks, net of the ROM's Line-F handler) where "
        f"{ON_THE_BENCH_BLOB[key_of(stretch)]} is reported")
    assert _turns_printed(price) == [THE_TURN_INSIDE[BENCH]] * stretch.turns


def test_the_census_says_how_each_of_the_six_routines_is_held_at_tier_3():
    """THE CENSUS (ruling W4-R11): gem_entry NEVER RETURNS — no row, its checkpoints; each of the other five has rows
    of the table at its own address, and the registered stretches are exactly theirs. What has no second column says
    which of the three reasons."""
    tier3 = bench_tier3()
    assert set(ob.THE_CENSUS) == {"AES_ROM_GEM_ENTRY", "AES_ROM_GEM_GEMDOS_CALL", "AES_ROM_GEM_MAIN", "AES_ROM_GEM_READ_INF",
                                  "AES_ROM_SH_MAIN", "AES_ROM_SH_CMD"}
    for name, (how, _what) in ob.THE_CENSUS.items():
        rows = [row for row in tier3.ROWS if tier3.rom_address(row) == getattr(addrs, name)]
        assert bool(rows) == (how == ob.IN_THE_TABLE), f"{name}: {how}, and {len(rows)} row(s) of the table"
        assert how in (ob.IN_THE_TABLE, ob.NEVER_RETURNS)
    stretches = [row for row in tier3.ROWS if tier3.is_a_stretch(row)]
    assert {row.registered for row in stretches} == set(ob.STRETCHES) and len(stretches) == len(STRETCHES) == 16
    assert {tier3.rom_address(row) for row in stretches} == {getattr(addrs, name) for name in ob.SYMBOL_OF}
    assert all(tier3.goes_through_the_os(row) and not row.transcription and not row.dropped for row in stretches)
    assert len([row for row in tier3.ROWS if tier3.rom_address(row) == addrs.AES_ROM_GEM_GEMDOS_CALL and row.transcription]) == 6
    assert {reason for reason, _why in ob.WITHOUT_A_SECOND_COLUMN.values()} == {ob.NEVER_RETURNS, ob.RUNS_A_PROGRAM, ob.NO_MACHINE}
    assert max(len(row.case) for row in stretches) <= 136, "a case longer than the table's widest moves every line of it"
    assert set(ON_THE_BENCH_BLOB) == {key_of(stretch) for stretch in STRETCHES} and len(OVER_THE_BAR_NET_OF_LINE_F) == 5
    assert sum(float(with_thunks) > BAR for with_thunks, _net in ON_THE_BENCH_BLOB.values()) == 8, "the eight STATUS reports (AWAITING 22, B-2)"


# ---- THE SERVED DOOR ITSELF, ON AN OUR-BOOT MACHINE (`aes_boot.served`: slice M's door, its caller now the blob's) ---------------
@every_blob
def test_labelled_staging_argument_class_deskmain_served_the_shell_in_the_blob_is_its_caller(blob):
    """SLICE M's DOOR, ON A MACHINE OF OURS: the our-boot stopped at deskmain's entry stands there CALLED BY THE BLOB'S
    OWN SHELL (the return address is a place in the blob — the door's arm for it had no machine before), and deskmain
    answered 0 runs OUR teardown and OUR gem_entry's loop to the second entry of OUR gem_main: on the stack pointer of
    the first, `$88` and `$404` given back to the VDI's and the BIOS's own, the label carried. THE ROM's shel_write
    may be CALLED over an our-boot machine first (the desk's own call is the ROM's on both shores: ruling W4-R3)."""
    the_build = the_blob(blob)
    at_the_desk = aes_boot.our_desk_machine(the_build, until=aes_boot.deskmain_entry(aes_boot.ours_of(the_build))).boot
    back = case.long_in(at_the_desk.ram, at_the_desk.registers["isp"]) & BUS
    assert the_build.base <= back < the_build.end and aes_boot.whose(back, aes_boot.blob_of(at_the_desk)) == aes_boot.OURS
    entered = aes_boot.our_desk_machine(the_build, until=the_build.entry("aes_rom_gem_main")).boot
    again = aes_boot.served(at_the_desk, 0, until=the_build.entry("aes_rom_gem_main"))
    assert again.served == (aes_boot.Served("deskmain", DESKMAIN, 0, ()),) and again.our_boot == at_the_desk.our_boot
    assert again.registers["isp"] == entered.registers["isp"] == pinned.PD0_S[1] - LONG_BYTES
    the_rom_s = aes_boot.served(aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=DESKMAIN), 0, until=GEM_MAIN)
    for vector in (addrs.VECTOR_TRAP_GEM, aes_event.ETV_CRITIC):
        assert case.long_in(again.ram, vector) == case.long_in(the_rom_s.ram, vector) and not the_build.base <= case.long_in(again.ram, vector) < the_build.end
    asked = aes_boot.served(at_the_desk, 1, until=the_build.entry("aes_sh_cmd"), calls=(ob.shel_write(ob.A_FILE_OF_THE_DISK, b""),))
    assert asked.served[0].calls == (ob.SH_WRITE,) and asked.registers["pc"] == the_build.entry("aes_sh_cmd")


# ---- THE CLAIM'S CUT: the our-boot machine at its first idle (ruling W4-R10's measure; band 6 W3b's O5 makes it the claim) ---------
# SINCE BAND 6 W3b's FLIP THE DESK IS OURS TO ITS FIRST IDLE (deskmain's C, `test_desk_w3b.py`): who ran is ours alone there
# (the test above), and the two machines are apart nowhere outside the classes of PD0's own stack and context (our
# deskmain's frames and saved registers, GCC's, over each build's residue), the desk's wait's parameter and the screen
# manager's saved context and stack — RE-DERIVED AT THE FLIP AND PINNED, per blob and disk (`AT_THE_FIRST_IDLE`).
@every_blob
@every_machine
def test_labelled_staging_the_machine_at_its_first_idle_differs_in_the_classes_alone(disk, blob):
    """THE OUR-BOOT MACHINE RUN ON TO THE DESKTOP'S FIRST IDLE, beside the ROM-booted one (ruling W4-R10's measure,
    the claim's cut since band 6 W3b's O5): ours idles in OUR dispatcher (our deskmain parked in its evnt_multi), the
    ROM's in its own; with every code address mapped back the two megabytes differ ONLY in the classes — and of those,
    beside the dead ones, in PD0's stack (whole: the desk's live frames over each build's), the desk's wait's parameter
    (its QPB in each build's frame) and the screen manager's saved context and stack: AS MANY BYTES AS PINNED."""
    ours_boots, the_rom_boots = THE_MACHINES[disk]
    ours, the_rom_s = ours_boots(the_blob(blob)), the_rom_boots()
    assert (ours.idle, the_rom_s.idle) == (aes_boot.OURS, aes_boot.THE_ROM_S)

    def as_a_stop(machine):         # ...placed at PD0's stack's bottom: its whole stack is then one class, the live frames
        return ob.Stop("the first idle", pinned.PD0_S[0], machine.registers, machine.boot.instructions, machine.boot.cycles, 0, (),
                       machine.ram, aes.SHELL_PD)
    found = ob.compared(as_a_stop(the_rom_s), as_a_stop(ours), the_blob(blob))
    assert found.differing == (), [(f"{at:#x}", length) for at, length in found.differing[:8]]
    assert {name for name in found.within if name in ob.LIVE_CLASSES} == {ob.PD0_FRAMES, ob.MANAGER_CONTEXT, ob.MANAGER_STACK, ob.PD0_PARKED}
    # HOW MANY BYTES, all told, by class — each blob's own layout's: the frames a compiler lays, our deskmain's among them
    # since band 6 W3b (863 on the shipped blob and 734 on the bench one before it, on both disks, a bound then; 343 /
    # 326 before band 6's binding). PINNED at the flip (O5: the classes re-derived).
    within = {name: count for name, count in found.within.items() if name != ob.THE_BLOB}
    assert within == AT_THE_FIRST_IDLE[blob], within


# `{blob: {class: the bytes the two machines differ in there}}` at the first idle, on both disks alike (measured, W3b's flip)
AT_THE_FIRST_IDLE = {
    "the bench blob": {ob.GEMDOS_S_STACK: 17, ob.THE_BIOS_S_STACK: 3, ob.TRAP_SAVE: 8, ob.BASEPAGE_SAVE: 11, ob.CONDITION_CODES: 1,
                       ob.DISPATCHER_STACK: 140, ob.PD0_CONTEXT: 27, ob.MANAGER_CONTEXT: 18, ob.MANAGER_STACK: 156,
                       ob.LINE_F_MASK: 2, ob.FIRST_STACK_RESIDUE: 44, ob.PD0_FRAMES: 572, ob.PD0_PARKED: 1},
    "the shipped blob": {ob.GEMDOS_S_STACK: 17, ob.THE_BIOS_S_STACK: 3, ob.TRAP_SAVE: 8, ob.BASEPAGE_SAVE: 11,
                         ob.DISPATCHER_STACK: 143, ob.PD0_CONTEXT: 28, ob.MANAGER_CONTEXT: 18, ob.MANAGER_STACK: 164,
                         ob.LINE_F_MASK: 2, ob.FIRST_STACK_RESIDUE: 52, ob.PD0_FRAMES: 572, ob.PD0_PARKED: 1},
}   # (1,000 / 1,019 bytes all told; 734 / 863 before the flip, when the ROM's desk ran over our AES. The shipped blob's
    # PD0_FRAMES 571 -> 569 at boot B2, LAYOUT, measured: `src/boot/` links before `src/desk/`, so the desk moved +$168;
    # three return addresses in PD0's frames went $04ff7e -> $0500e6 and their middle byte now equals the ROM's $00 there
    # (at $a1a4, $a1e2, $a210: -3), and one word went $000c -> $0174 and now differs at $a26e (+1) — net -2. At boot B3,
    # LAYOUT again, measured against a pre-B3 build of both blobs: `src/boot/hwinit.c` links before the desk. The shipped
    # blob's desk moved +$294: the same three return addresses went $0500e6 -> $05037a, their middle byte $03 against the
    # ROM's $00 again (+3: 569 -> 572); the bench blob's +$268: a code address in PD0's saved context went $04a002 ->
    # $04a26a, its byte at $9c90 now the ROM's $a2 (-1: PD0_CONTEXT 28 -> 27))


def test_a_wait_s_parameter_is_the_parked_class_only_where_both_shores_name_pd0_s_stack():
    """`ob.PD0_PARKED` (band 6's binding) IS A CLASS OF BOTH SHORES (the fix pass, reviewer A's mutant R7): an EVB's
    parameter naming a place in PD0's stack on ONE shore alone is no class — compared exactly, and the difference said —
    and one naming it on both is. Two stops laid by hand over the base image, at PD0's stack, one EVB's parameter set."""
    pd0_lo, pd0_top = aes_stack.gem_entry_s_stacks()[aes_stack.PD0_S_STACK]
    slot, blob_span = aes_event.EVBS[0] + aes.EVB_PARM, (aes.OS_BUS_ADDR_MASK - 1, aes.OS_BUS_ADDR_MASK)
    inside, outside = pd0_top - 2 * aes.LONG_BYTES, pd0_lo - aes.LONG_BYTES

    def stop(parameter):
        ram = bytearray(BASE_IMAGE[:addrs.ST_RAM_BYTES])
        ram[slot:slot + aes.LONG_BYTES] = struct.pack(">I", parameter)
        return types.SimpleNamespace(what="a checkpoint", sp=(pd0_lo + pd0_top) // 2, registers={}, ram=bytes(ram))
    assert (slot, slot + aes.LONG_BYTES) in ob.classes_at(stop(inside), stop(inside), blob_span)[ob.PD0_PARKED]
    for one_shore in ((stop(inside), stop(outside)), (stop(outside), stop(inside))):
        assert (slot, slot + aes.LONG_BYTES) not in ob.classes_at(*one_shore, blob_span).get(ob.PD0_PARKED, ())
