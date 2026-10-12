"""GEMINIT'S C AT THE ROM'S OWN BOOT (`src/aes/geminit.c`) — the two stretches of gem_main's host twin that are a run
with an end, each held to THE ROM'S OWN RUN OF THE SAME BOOT, IN PLACE (`aes_loader`'s arrivals: the boot stopped where
the stretch begins, continued by the ROM to where it ends; the C over the megabyte the boot made, no byte poked):

  * gem_main'S FIRST STRETCH, `$fda062..$fda1ce` — from its entry to its call of `sti`: the long pointers, `trap #2`
    taken, the recorder off, the event blocks' free list, the scheduler's lists, the fork queue, the screen's lock,
    the three static processes laid out and PD0 made the running one. A RUN BETWEEN TWO ADDRESSES (D-3's kind: the ROM
    has no entry for it; the host's `aes_gem_main_lays_the_processes` is that stretch as a call). It makes no GEMDOS
    call and reaches no door.
  * THE INF READER AT ITS OWN ARRIVAL — gem_main's call of it (`$fda1f0`) on the blank disk's boot: the ROM's real
    GEMDOS in place (nine calls: no DESKTOP.INF on the disk, no C:), the C with GEMDOS REPLAYED from that run, the
    megabyte held at every call and at the return. The arm a boot reaches where the disk holds no file; the file arm's
    arrival is the INF capture's (`aes_boot.inf_preinit`), whose read `aes_loader`'s watch does not name — slice B's
    row, on the blobs.

EACH IS HELD TWICE, as the loader's cases are: as the boot made the machine, and again with EVERY BYTE THE ROM'S STRETCH
STORED WITHOUT CHANGING IT INVERTED — a labelled staging; the ROM's own run made again from that machine. It is what
makes the first stretch a test at all: gem_entry has just cleared THEGLO, so most of what gem_main then clears is 0
already, and a C that skipped those stores would leave the same megabyte.

WHAT THE TWO SHORES DIFFER IN BY NATURE, named per case and refused where never needed: the ROM's own frames (the
process's stack below the stack pointer the stretch began at), the Line-F mask word, and — the reader's — the host
slots of its C.
"""
import functools

import pytest

from harness import BASE_IMAGE, _lib, addrs

import aes
import aes_boot
import aes_geminit as gi
import aes_loader as ld
import aes_switch
import case
import gemdos
import rom_data

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
GEM_MAIN = addrs.AES_ROM_GEM_MAIN


# ---- gem_main's first stretch ------------------------------------------------------------------------------------------------
def _the_call_of(routine, lo, hi):
    """Where the ROM's code `[lo, hi)` Line-F-calls `routine`: ONE word."""
    (at,) = [at for at, text in rom_data.instructions(lo, hi)
             if text is None and aes.line_f_target(case.word_in(BASE_IMAGE, at)) == routine]
    return at


STI_CALL = _the_call_of(addrs.AES_ROM_STI, GEM_MAIN, addrs.AES_ROM_PINIT)
THE_LOOP_S_BRANCH = addrs.AES_ROM_GEM_GEMDOS_CALL - WORD_BYTES      # gem_entry's `bra` back, behind its `jsr` of gem_main
THE_STACK_BELOW = "the ROM's own frames: UDA0's stack below the stack pointer gem_main is entered on"
SILENT_STORES_INVERTED = "LABELLED STAGING: every byte the ROM's stretch stored without changing it, inverted"


@functools.cache
def entered():
    """The blank disk's boot stopped at gem_main's entry: a `Stood` — the megabyte gem_entry made, THEGLO just
    cleared, the stack pointer four bytes under UDA0's top."""
    return ld.stood_at(aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=GEM_MAIN))


def stretch_classes(stood):
    sp = stood.registers["isp"]
    return ld.Classes({THE_STACK_BELOW: ((aes.AES_THEGLO + aes.UDA_STATE_BYTES, sp),),
                       ld.LINE_F_MASK: tuple((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW)})


def the_c_s_stretch(stood):
    """The megabyte the host's stretch leaves of `stood`'s: `aes_gem_main_lays_the_processes` over it, no hook bound
    (a door reached fails the run by name, as an unbound GEMDOS handler does)."""
    _answer, image = gemdos.run_candidate_only(lambda lib, buf: lib.aes_gem_main_lays_the_processes(buf), {0: stood.ram})
    assert not aes_switch.host_slots_held()
    return image[:ld.RAM_BYTES]


def held_to_the_rom_s(stood):
    """ONE PASS: the ROM's own run from `stood` to its call of sti, and the C's megabyte against the one it left —
    outside the two classes, each of which must have been needed. Answers the ROM's `Ran`."""
    ran = ld.run_on(stood, STI_CALL)
    assert not ran.calls, "the stretch makes no GEMDOS call"
    classes = stretch_classes(stood)
    ours = the_c_s_stretch(stood)
    differing = classes.differing(ran.stood.ram, ours)
    assert not differing, f"where the stretch ends the C's megabyte is not the ROM's — {ld._said(differing, ran.stood.ram, ours)}"
    classes.vet_each_was_needed("gem_main's first stretch")
    return ran


def silently_stored(stood, ran):
    """`stood` with every byte the ROM's stretch STORED AND LEFT AS IT FOUND IT inverted — outside the two classes."""
    assert ran.silent is not None, "the stretch's write ledger did not saturate"
    classes, ram = stretch_classes(stood), bytearray(stood.ram)
    inverted = [at for start, length in ran.silent for at in range(start, start + length) if classes.outside(at, 1)]
    for at in inverted:
        ram[at] ^= aes.BYTE_MASK
    return stood._replace(ram=bytes(ram)), inverted


def test_the_boot_enters_gem_main_where_gem_entry_s_jsr_leaves_it():
    """THE ARRIVAL: gem_entry's `jsr` ($fd9fbe) entered gem_main in supervisor state, four bytes under UDA0's top, its
    return address the `bra` back to the loop — and THEGLO is clear but for that one longword and UDA0's stack pointer."""
    stood = entered()
    registers, ram = stood.registers, stood.ram
    top = aes.AES_UDA1                  # UDA0's stack top is UDA1 itself (`aes/aes.h`)
    assert registers["pc"] == GEM_MAIN and registers["sr"] & aes_boot.SR_SUPERVISOR
    assert registers["isp"] == top - LONG_BYTES and case.long_in(ram, registers["isp"]) == THE_LOOP_S_BRANCH
    assert case.long_in(ram, aes.AES_THEGLO + aes.UDA_SUPER_SP) == top
    theglo = bytearray(ram[aes.AES_THEGLO:aes.AES_THEGLO + aes.AES_THEGLO_WORDS * WORD_BYTES])
    for at in (aes.UDA_SUPER_SP, registers["isp"] - aes.AES_THEGLO):
        theglo[at:at + LONG_BYTES] = bytes(LONG_BYTES)
    assert not any(theglo), "gem_entry's clear, and nothing stored since but the two"


def test_the_first_stretch_is_the_rom_s_as_the_boot_made_the_machine():
    ran = held_to_the_rom_s(entered())
    after = ran.stood
    assert after.registers["pc"] == STI_CALL
    # ...and what the ROM's stretch left, read off its own megabyte: PD0 running, alone and ready, its id 0 and the
    # count stepped; the free list's head the LAST event block; the three UDAs named by their PDs.
    ram = after.ram
    assert case.long_in(ram, aes.AES_RLR) == aes.AES_PD_TABLE and case.word_in(ram, aes.AES_STATIC_PIDS) == 1
    assert case.long_in(ram, aes.AES_EUL) == aes.AES_EVB_TABLE + (aes.AES_EVB_COUNT - 1) * aes.EVB_BYTES
    assert aes.list_of(ram, aes.AES_EUL, link=aes.EVB_NEXT, limit=aes.AES_EVB_COUNT) == [
        aes.AES_EVB_TABLE + nth * aes.EVB_BYTES for nth in reversed(range(aes.AES_EVB_COUNT))]
    assert [case.long_in(ram, aes.AES_PD_TABLE + nth * aes.PD_BYTES + aes.PD_UDA) for nth in range(aes.AES_PD_COUNT)] == [
        aes.AES_THEGLO, aes.AES_UDA1, aes.AES_UDA2]
    assert (case.long_in(ram, aes.AES_UDA1 + aes.UDA_SUPER_SP), case.long_in(ram, aes.AES_UDA2 + aes.UDA_SUPER_SP)) == (
        aes.AES_UDA1_STACK_TOP, aes.AES_UDA2_STACK_TOP)
    assert case.long_in(ram, addrs.VECTOR_TRAP_GEM) == addrs.GEM_TRAP2, "install_trap2 ran (the ROM's shore: the ROM's handler)"


def test_the_first_stretch_is_the_rom_s_with_its_silent_stores_made_to_show():
    """LABELLED STAGING (`SILENT_STORES_INVERTED`). The lists and counts the stretch clears were 0 when gem_main began,
    so those stores change nothing: here each such byte starts inverted, the ROM's own run is made again from that
    machine, and the C is held to it — a store the C skipped now differs."""
    stood = entered()
    staged, inverted = silently_stored(stood, ld.run_on(stood, STI_CALL))
    assert len(inverted) >= 40, f"only {len(inverted)} bytes were stored silently: the pass would hold little"
    silent = set(inverted)
    for cleared in (aes.AES_GL_RECD, aes.AES_RECORD_LEFT, aes.AES_DRL, aes.AES_NRL, aes.AES_ZOMBIE_LIST, aes.AES_FORK_COUNT,
                    aes.AES_FORK_TAIL, aes.AES_FORK_HEAD, aes.AES_FORKER_BUSY):
        assert cleared in silent, f"${cleared:x} is cleared by the stretch and was 0 already: it must be among the inverted"
    held_to_the_rom_s(staged)


def test_the_pass_sees_a_store_the_c_skipped(monkeypatch):
    """ITS RED: the C's megabyte with ONE of those silent clears undone — the not-ready list's head left as the
    inverted machine had it — parts from the ROM's, by address."""
    stood = entered()
    staged, _inverted = silently_stored(stood, ld.run_on(stood, STI_CALL))
    real = the_c_s_stretch

    def skipping_one_clear(machine):
        ram = bytearray(real(machine))
        ram[aes.AES_NRL:aes.AES_NRL + LONG_BYTES] = machine.ram[aes.AES_NRL:aes.AES_NRL + LONG_BYTES]
        return bytes(ram)
    monkeypatch.setattr(f"{__name__}.the_c_s_stretch", skipping_one_clear)
    with pytest.raises(AssertionError, match=f"{aes.AES_NRL:#x}"):
        held_to_the_rom_s(staged)


THE_SECOND_PASS = ("LABELLED ARGUMENT CLASS (ruling W4-R6): gem_main's SECOND entry — the ROM's own boot stopped at deskmain's entry, "
                   "deskmain answered 0 there by the served door (`aes_boot.served`), the ROM's teardown and gem_entry's loop run to it")


@functools.cache
def entered_again():
    """THE SECOND gem_main's ENTRY, a `Stood` (`THE_SECOND_PASS`): what no boot reaches — the machine a whole session
    left, THEGLO cleared again, the BSS's lists and `rlr` as the first pass's teardown left them."""
    at_deskmain = aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=addrs.AES_ROM_DESKMAIN)
    return ld.stood_at(aes_boot.served(at_deskmain, 0, until=GEM_MAIN))


def test_the_first_stretch_is_the_rom_s_at_gem_main_s_second_entry_deskmain_served_where_rlr_still_names_the_shell():
    """LABELLED (`THE_SECOND_PASS`: deskmain SERVED — the desk never ran). The boot enters gem_main with `rlr` 0 and
    every list empty; the second pass of gem_entry's loop enters it on the same stack pointer with `rlr` STILL THE
    SHELL'S PD (slice M's finding: the loop's clear of THEGLO does not reach the word) and whatever the session left
    in the BSS. The ROM's stretch stores `rlr` before it reads it and clears what it clears; the C is held to the
    ROM's own run FROM THAT ENTRY: a read of the stale pointer, or the NOT-READY LIST's clear skipped, parts the
    megabytes. (The delay list's and the screen lock's clears do NOT show here — both are clean at a served second
    entry: the first-entry test with every silent store inverted is what holds those two.)"""
    first, again = entered(), entered_again()
    assert again.registers["pc"] == GEM_MAIN and again.registers["isp"] == first.registers["isp"]
    assert (case.long_in(first.ram, aes.AES_RLR), case.long_in(again.ram, aes.AES_RLR)) == (0, aes.SHELL_PD)
    assert (case.word_in(again.ram, aes.AES_STATIC_PIDS), case.long_in(again.ram, aes.AES_NRL) != 0) == (2, True), (
        "the premise: the second entry is not the first's machine — the count the first pass left, a list not empty")
    ran = held_to_the_rom_s(again)
    assert case.long_in(ran.stood.ram, aes.AES_RLR) == aes.SHELL_PD and case.word_in(ran.stood.ram, aes.AES_STATIC_PIDS) == 1


def test_the_host_stretch_is_gem_main_s_own_beginning():
    """The stretch's entry is the first of gem_main's three (`geminit.c`): the library exports both, and the stretch
    ends where the ROM's next Line-F word calls sti — the interrupts are let in by the stretch AFTER it."""
    assert hasattr(_lib, "aes_gem_main") and hasattr(_lib, "aes_gem_main_lays_the_processes")
    assert GEM_MAIN < STI_CALL < addrs.AES_ROM_PINIT
    before = [aes.line_f_target(case.word_in(BASE_IMAGE, at)) for at, text in rom_data.instructions(GEM_MAIN, STI_CALL)
              if text is None]
    assert before == [addrs.AES_ROM_INI_DLONGS, addrs.AES_ROM_CLI, addrs.AES_ROM_INSTALL_TRAP2, addrs.AES_ROM_PINIT]


# ---- the reader at its own arrival -------------------------------------------------------------------------------------------
# The host slots the reader's C claims (`include/host_slot.h`): GEMDOS's trap words, and its own pair — claimed on
# the `#E` arm alone, which this arrival does not reach. Registered with the loader's table of them by role: the
# arrivals' classes are located through it (`aes_loader.classes_of`).
ld.HOST_SLOT_ROLES.setdefault(gi.READ_INF, ("GEMDOS_WORDS", "AES_READ_INF_PAIR"))
READER_CLASSES = (ld.ROM_FRAMES, ld.HOST_FRAMES, ld.LINE_F_MASK)
MALLOC, MFREE, DGETDRV, DSETDRV, DSETPATH, FOPEN = gi.MALLOC, gi.MFREE, gi.DGETDRV, gi.DSETDRV, gi.DSETPATH, gi.FOPEN


@functools.cache
def reader_arrival():
    """gem_main's call of the reader on the blank disk's boot: an `Arrival` — no argument, the frame gem_main pushed."""
    return ld.boot_arrival(gi.READ_INF, aes_boot.preinit(), aes_boot.blank_disk())


def test_the_reader_s_arrival_is_gem_main_s_call_of_it():
    arrived = reader_arrival()
    assert arrived.arguments == () and ld.return_site(arrived) == _the_call_of(
        addrs.AES_ROM_GEM_READ_INF, GEM_MAIN, addrs.AES_ROM_PINIT) + WORD_BYTES
    ram = arrived.stood.ram
    assert (case.word_in(ram, gi.RSCHANGE), case.word_in(ram, gi.RESTYPE)) == (0, 1), "gem_entry's two words, as the reader finds them"
    assert not any(ram[aes.AES_SHELL_GEM_BUFFER:aes.AES_SHELL_GEM_BUFFER + gi.INF_BUFFER_BYTES]), "the shell's buffer: clear"


def test_the_usable_disk_word_the_reader_finds_is_a_return_address_s_low_word():
    """A BEHAVIOUR OF THE ROM, read off its own boot (`aes_geminit.THE_ROM_S_USABLE_WORD`): the word gem_entry set to 1
    lies in its own first stack, and what the reader tests is the low word of the return address gem_entry's `jsr` of
    size_theglo pushed over it — `$9f78`, with `$00fd` under it. Non-zero, so the disk is read; never the 1."""
    ram = reader_arrival().stood.ram
    assert case.long_in(ram, gi.DISK_USABLE - WORD_BYTES) == gi.SIZE_THEGLO_RETURNS_TO
    assert case.word_in(ram, gi.DISK_USABLE) == gi.THE_ROM_S_USABLE_WORD == 0x9F78 != gi.GEMSTART["GEM_DISK_USABLE"]
    first_stack_top = aes.header_constants("aes.h")["AES_SR_DISPATCH"]
    assert gi.DISK_USABLE + WORD_BYTES == first_stack_top, "the word is the first stack's top two bytes"


def test_the_reader_is_the_rom_s_at_its_arrival_on_a_disk_with_no_inf():
    """HELD TWICE (`aes_loader.held_twice`): the C makes the ROM's nine GEMDOS calls over the ROM's megabyte at each,
    answers its 0 and leaves its megabyte — and again from the machine with the ROM's silent stores inverted."""
    ran, ours = ld.held_twice(reader_arrival(), *READER_CLASSES)
    assert ld.answered(ran) == gi.GEMINIT["INF_NOT_READ"] == ours.answer
    assert [call.function for call in ran.calls] == [MALLOC, DGETDRV, DSETDRV, DGETDRV, DSETPATH, FOPEN, DGETDRV, DSETDRV, MFREE]
    opened = ran.calls[5]
    assert aes.signed(opened.answer, bits=32) < 0, "the blank disk holds no DESKTOP.INF"


def test_at_its_arrival_the_reader_leaves_the_rom_s_default_in_the_shell_s_buffer():
    """WHAT THE BOOT'S OWN READER DID: the shell's GEM buffer holds the ROM's INF — the bytes the post-boot snapshot
    still holds there — the device words as gem_entry laid them, and the drive map without a C:."""
    arrived = reader_arrival()
    ran = ld.returned(arrived)
    after = ran.stood.ram
    default_bytes = gi.default_inf_bytes(after)
    snapshot = bytes(BASE_IMAGE[aes.AES_SHELL_GEM_BUFFER:aes.AES_SHELL_GEM_BUFFER + default_bytes])
    assert after[aes.AES_SHELL_GEM_BUFFER:aes.AES_SHELL_GEM_BUFFER + default_bytes] == snapshot and b"#E " in snapshot
    assert (case.word_in(after, gi.RSCHANGE), case.word_in(after, gi.RESTYPE)) == (0, 1), "no line was acted on"
    assert not ran.calls[7].answer & aes.header_constants("deskleaf.h")["DRIVE_C_BIT"], "the second isdrive: no C:"
