r"""THE OUR-BOOT MACHINE BESIDE THE ROM'S OWN BOOT (band 5 wave 4, slice B: `test_aes_ourboot.py`, `bench/tier3.py`).

`aes_boot.booted(..., laid=AT_GEM_ENTRY)` makes the machine: A LABELLED STAGING (ruling W4-R1) — the blob laid at the
pre-init stop and the run entered at the blob's own gem_entry, no longword mapped by the harness. This module is what
says THAT MACHINE IS THE ROM'S, how far, and at what price:

  * A RUN WATCHED ON BOTH SHORES AT THE SAME CHECKPOINTS (`both_shores`): the ROM's own run from a machine and OUR
    build's from the same machine, each stopped at its first arrival at each `Checkpoint` — a ROM address on the
    ROM's shore; on ours the build's own entry for it (a symbol of the blob), the same offset inside gem_entry (the
    `.S` is byte-pinned: an instruction of ours lies where the ROM's does, from each one's entry), or the same ROM
    address (deskmain, a built-in of the desk's: the ROM's on both shores until band 6).
  * WHAT IS HELD AT EACH (`compared`, `vet_alike`): the megabyte, byte for byte — every code address of the relocation
    registry our run stored given the ROM's name first (never dropped) — outside THE CLASSES the two machines differ
    in by nature (`classes_at`: each located through the two machines' own pointers and stack pointers): THE LIVE
    ONES NAMED BY THE COMPARISON, each needed or the comparison refused; THE DEAD ONES PROVED DEAD BY NOISE at every
    checkpoint, on the ROM's own machine (`noise_proved`). The checkpoints arrived at IN THE SAME ORDER; and BETWEEN
    TWO OF THEM THE SAME BYTES STORED (`stores_differing`: each shore's write ledger over the stretch, outside the
    classes — a store one shore makes and the other does not is a difference even where both leave the same value,
    which is how a clear of a byte that is zero already is held).
  * WHO RAN (`who_ran`): a cycle profile differenced over the run — OUR shore NOT ONE CYCLE in the ROM's GEM text nor
    in the Line-F handler's RAM copy, the ROM's shore none in the blob. "OURS BOOTED" IS CLAIMED TO deskmain's ENTRY
    AND NO FURTHER (ruling W4-R3): every run here ends at an arrival at deskmain or before one.
  * THE ROADS NO MACHINE TAKES — gem_main's teardown, gem_entry's second pass, the shell's launch pass, sh_cmd's arms —
    ARE RUN THROUGH THE SERVED DOOR (`aes_boot.answered_at_its_entry`: ruling W4-R6's LABELLED ARGUMENT CLASS), ON THE
    OUR-BOOT MACHINE AND THE ROM'S FROM THE SAME STOP: deskmain answered a word at its entry on both; a built-in of
    the desk's answered where the run arrives at it (`Pass.serving`); the shell's buffers as THE ROM'S OWN shel_write
    leaves them, called over each stopped machine — the desk's own call, which is the ROM's on both shores.
  * A STRETCH IS PRICED (`Stretch`, `priced`: ruling W4-R11): the run between two checkpoints, each shore's own
    cycles in it — ours the blob's, the ROM's its AES text's and Line-F handler's — the turn of another process
    inside it cut out and priced by itself, the OS both run held equal. `bench/tier3.py` makes its rows of these.

WHAT A COMPARISON CANNOT HOLD, said once: PD0's LIVE FRAMES (the build's own, from the stack pointer to the stack's
top: sixty-two bytes at deskmain's entry) are vetted by what the caller DOES with an answer — the served passes —
never byte for byte; and nothing here runs past deskmain's entry (the desk's depth under our frames is not claimed).
"""
import functools
import re
from collections import namedtuple

from harness import BASE_IMAGE, addrs, bench_tier3, emu
from opcodes import JSR_ABSOLUTE_LONG

import preinit_snapshot

import aes
import aes_boot
import aes_event
import aes_objdraw
import aes_resource
import aes_stack
import aes_switch
import aes_switching
import case
import derived
import routines

RAM_BYTES = aes_boot.RAM_BYTES
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes.OS_BUS_ADDR_MASK
GEM_ENTRY, GEM_ENTRY_END = addrs.AES_ROM_GEM_ENTRY, addrs.AES_ROM_GEM_GEMDOS_CALL
DESKMAIN = addrs.AES_ROM_DESKMAIN


class Refused(AssertionError):
    """A run of the two shores is not the pair its declaration says: by name."""


# ---- THE CHECKPOINTS ---------------------------------------------------------------------------------------------------------
IN_GEM_ENTRY, THE_ROM_S_OWN = "at the ROM's own offset inside the build's gem_entry", "the ROM's own address on both shores"
Checkpoint = namedtuple("Checkpoint", "what rom ours")
Checkpoint.__doc__ = """One place both shores' runs are stopped at: `what` it is (its name in every table), the ROM's
address, and where OUR run stands for it — a symbol of the blob (the build's own entry), IN_GEM_ENTRY, or
THE_ROM_S_OWN."""
BRA_S = 0x60


def _jsr_in_gem_entry(target):
    """The address of gem_entry's `jsr <target>` — found in the ROM's own bytes, one."""
    found = [at for at in range(GEM_ENTRY, GEM_ENTRY_END - LONG_BYTES, WORD_BYTES)
             if bytes(BASE_IMAGE[at:at + WORD_BYTES]) == JSR_ABSOLUTE_LONG and case.long_in(BASE_IMAGE, at + WORD_BYTES) == target]
    assert len(found) == 1, f"gem_entry holds {len(found)} `jsr {target:#x}`: one is a checkpoint"
    return found[0]


RSC_INIT_CALLED_AT, THE_LOOP_S_TOP = _jsr_in_gem_entry(addrs.AES_ROM_ROM_RSC_INIT), _jsr_in_gem_entry(addrs.AES_ROM_SIZE_THEGLO)
GEM_MAIN_CALLED_AT = _jsr_in_gem_entry(addrs.AES_ROM_GEM_MAIN)
GEM_MAIN_RETURNS_TO = GEM_MAIN_CALLED_AT + WORD_BYTES + LONG_BYTES      # the loop's `bra` back
THEGLO_CLEARED_AT = aes_event.JUSTRETF_STORED_AT                        # the first of the three by-value stores: the clear is done
GEM_DISK_USABLE = aes.header_constants("gemstart.h")["GEM_DISK_USABLE"]    # the 1 gem_entry stores at `$8992`
assert BASE_IMAGE[GEM_MAIN_RETURNS_TO] == BRA_S and GEM_MAIN_RETURNS_TO + WORD_BYTES == GEM_ENTRY_END, "gem_entry ends in its `bra`"


def _entered(name, symbol=None):
    """The checkpoint at the ROM routine `addrs.<name>`'s entry: ours the build's own core of it (or `symbol`)."""
    return Checkpoint(aes_event.short_name(name), getattr(addrs, name), symbol or routines.core_symbol(name))


GEM_MAIN, THE_READER, SH_MAIN, SH_CMD = "gem_main", "the `#E` reader", "sh_main", "sh_cmd"
THE_COPY_MADE = "gem_entry: past the `$2c` test — the Line-F handler copied, the vector moved"
THE_LOOP = "gem_entry: the loop's top — the resources in, the usable-disk word stored"
THE_CLEAR = "gem_entry: THEGLO cleared"
THE_STACK_MOVED = "gem_entry: the three routines stored by value, the stack moved to UDA0"
GEM_MAIN_RETURNED = "gem_entry: gem_main has returned (the loop's `bra`)"
DESKMAIN_ENTERED, DOS_EXEC_ENTERED = "deskmain", "dos_exec"
IN_ITS_LOOP = (Checkpoint(THE_LOOP, THE_LOOP_S_TOP, IN_GEM_ENTRY), Checkpoint(THE_CLEAR, THEGLO_CLEARED_AT, IN_GEM_ENTRY),
               Checkpoint(THE_STACK_MOVED, GEM_MAIN_CALLED_AT, IN_GEM_ENTRY))
BROUGHT_UP = (
    Checkpoint(GEM_MAIN, addrs.AES_ROM_GEM_MAIN, "aes_rom_gem_main"),
    _entered("AES_ROM_CLI", "aes_rom_cli"), _entered("AES_ROM_INSTALL_TRAP2"), _entered("AES_ROM_STI", "aes_rom_sti"),
    _entered("AES_ROM_ICTLMGR"), Checkpoint(THE_READER, addrs.AES_ROM_GEM_READ_INF, "aes_gem_read_inf"),
    _entered("AES_ROM_LDACCS"), _entered("AES_ROM_SET_DEFDRV"), _entered("AES_ROM_GSX_INIT"), _entered("AES_ROM_TAKEERR"),
    _entered("AES_ROM_SH_TOGRAPHIC"), _entered("AES_ROM_GSX_TICK"), _entered("AES_ROM_EV_DCLICK"), _entered("AES_ROM_RS_FIXIT"),
    _entered("AES_ROM_WM_START"), _entered("AES_ROM_FS_START"), _entered("AES_ROM_DSPTCH"),
    Checkpoint(SH_MAIN, addrs.AES_ROM_SH_MAIN, "aes_sh_main"), _entered("AES_ROM_DESK_ALLOC"),
    Checkpoint(DESKMAIN_ENTERED, DESKMAIN, THE_ROM_S_OWN))
# THE BOOT'S FIRST PASS, from the pre-init stop to deskmain's entry: gem_entry's arms, then gem_main's callees in the
# ROM's order and the shell's first pass.
THE_FIRST_PASS = (Checkpoint(THE_COPY_MADE, RSC_INIT_CALLED_AT, IN_GEM_ENTRY), *IN_ITS_LOOP, *BROUGHT_UP)
# ...and what follows A DESKMAIN THAT ANSWERS 0 (served): the shell's last steps, gem_main's teardown callee by callee,
# its return into gem_entry's loop — and THE SECOND PASS, a whole bring-up again, to deskmain's second entry. (A
# routine both parts call is a checkpoint at its FIRST arrival of the run: gsx_tick's is the teardown's, the first
# dsptch the yield of the shell's desk_free.)
TAKEN_DOWN = (_entered("AES_ROM_DESK_FREE"), _entered("AES_ROM_GSX_MFREE"), _entered("AES_ROM_GIVEERR"), _entered("AES_ROM_RS_FREE"),
              _entered("AES_ROM_FREE_ACCS"), _entered("AES_ROM_GSX_WSCLOSE"), _entered("AES_ROM_GSX_ESCAPES"),
              _entered("AES_ROM_RESTORE_TRAP2"), Checkpoint(GEM_MAIN_RETURNED, GEM_MAIN_RETURNS_TO, IN_GEM_ENTRY))
THE_TEARDOWN_AND_THE_SECOND_PASS = (*TAKEN_DOWN, *IN_ITS_LOOP, *BROUGHT_UP)
# ...and A DESKMAIN THAT ANSWERS 1 (served, after the ROM's own shel_write): the shell's next pass — the screen set up
# afresh (wm_start, THEN ratinit: the order is the order of two checkpoints), then a built-in of the desk's through
# sh_cmd and back to the desk, or a program found and dos_exec ENTERED (where the run ends: RUNS A PROGRAM, and a real
# launch loads over the blob).
THE_NEXT_PASS_BEGINS = (_entered("AES_ROM_DESK_FREE"), _entered("AES_ROM_WM_START"), _entered("AES_ROM_RATINIT"),
                        Checkpoint(SH_CMD, addrs.AES_ROM_SH_CMD, "aes_sh_cmd"))
A_BUILT_IN_PASS = (*THE_NEXT_PASS_BEGINS, _entered("AES_ROM_DESK_ALLOC"), Checkpoint(DESKMAIN_ENTERED, DESKMAIN, THE_ROM_S_OWN))
THE_LAUNCH_PASS = (*THE_NEXT_PASS_BEGINS, _entered("AES_ROM_SH_FIND"), _entered("AES_ROM_PD_NAMEIT"),
                   Checkpoint(DOS_EXEC_ENTERED, addrs.AES_ROM_DOS_EXEC, "aes_rom_dos_exec"))
# A ROUTINE WHOSE RETURN IS A CHECKPOINT TOO (a stretch priced from its entry to its return): the stop is made where
# its entry is arrived at — the address its caller's call left at the stack pointer.
RETURNED = "{}: returned"
ENTERED_AND_RETURNED = (THE_READER, SH_CMD)
A_SWITCH = "the dispatcher enters a process (switchto's `rte`)"
BEGAN = "where the run began"           # a run's first `Stop`: the machine it was entered over, nothing spent yet


def our_address(checkpoint, blob):
    """Where OUR run stands for `checkpoint` on `blob` (a `RomBench`)."""
    if checkpoint.ours == THE_ROM_S_OWN:
        return checkpoint.rom
    if checkpoint.ours == IN_GEM_ENTRY:
        return blob.entry(aes_boot.GEM_ENTRY_SYMBOL) + checkpoint.rom - GEM_ENTRY
    return blob.entry(checkpoint.ours)


# ---- ONE WATCHED RUN ---------------------------------------------------------------------------------------------------------
Stop = namedtuple("Stop", "what sp registers instructions cycles written tally ram running")
Stop.__doc__ = """One arrival of a watched run: `what` (a checkpoint's name, `RETURNED` of one, A_SWITCH); the
supervisor stack pointer and the register file there; the run's `instructions` and `cycles` so far; how many stores
its ledger held (`written`); the caller's `tally` there, as differences from the run's start; the megabyte (`ram`:
kept at a checkpoint's FIRST arrival, None at any other stop); and the process `running` (the PD `rlr` names — at
A_SWITCH the one being entered)."""
Watched = namedtuple("Watched", "stops ledger ended served")
Watched.__doc__ = """One shore's run (`watched_over`): every `Stop` in order; its write `ledger` (each address stored, in
order); the `Stop` it `ended` at; and the routines `served` in place on the way (`aes_boot.Served` each)."""
A_PASS_INSNS = aes_boot.BOOT_INSNS
PROFILE_HELD_BY_A_WATCHED_RUN = "a run of the two shores watched at its checkpoints (`aes_ourboot.watched_over`)"


class _Watching:
    """The observers of one watched run (`aes_boot._Run`'s `observing`): each checkpoint's arrival kept as a `Stop`,
    a routine of `returns` given a stop at its return address as its entry is arrived at, and a routine of `serving`
    ANSWERED WHERE THE RUN STANDS AT ITS ENTRY (the served door's own act, in place)."""

    def __init__(self, memory, places, tally, returns, serving, ours, crafted=()):
        self._memory, self._tally, self._returns, self._serving, self._ours = memory, tally, returns, dict(serving), ours
        self._crafted = dict(crafted)
        self.stops, self.served, self._began, self._seen = [], [], None, set()
        self.observing = {address: (what, self._arrived(what)) for address, what in places.items()}
        if ours is not None:            # ...a halt of the build is SAID, never run on into the bombs
            self.observing.update(aes_boot.watched_for_the_build_s_halt(memory, ours))
        self._due = {}                  # `{a return address: (the routine's name, the stack pointer it returns with)}`

    def begun(self, registers):
        """The profile is on and the run about to be entered with `registers`: its first `Stop` (the CPU itself still
        holds the last run's: the file it will be given is the one kept)."""
        self._began = self._tally()
        sp = registers["isp"] if registers["sr"] & aes_boot.SR_SUPERVISOR else registers["usp"]
        self.stops.append(self._stop(BEGAN, sp, True)._replace(registers=dict(registers), instructions=0, cycles=0, written=0))

    def _stop(self, what, sp, keep):
        cost = aes_event.run_cost()
        tally = tuple(now - then for now, then in zip(self._tally(), self._began))
        return Stop(what, sp, aes_boot._registers_now(), cost["insns"], cost["cycles"], aes_boot._CPU.osh_num_writes(), tally,
                    bytes(self._memory[:RAM_BYTES]) if keep else None, case.long_in(self._memory, aes.AES_RLR) & BUS)

    def _arrived(self, what):
        def read(memory, sp):
            first = what not in self._seen
            self._seen.add(what)
            self.stops.append(self._stop(what, sp, first and what != A_SWITCH))
            if what in self._returns and first:
                back = case.long_in(memory, sp) & BUS
                self._due[back] = (what, sp + LONG_BYTES)
                self.observing.setdefault(back, (RETURNED.format(what), self._returned(back)))
            if what in self._serving:
                self.served.append(aes_boot.served_where_it_stands(memory, sp, self._serving[what], self._ours))
            for at, data in self._crafted.get(what, ()) if first else ():      # A LABELLED CRAFT: after the stop is kept
                memory[at:at + len(data)] = data
        return read

    def _returned(self, back):
        def read(_memory, sp):
            what, expected = self._due.get(back, (None, None))
            if sp == expected:          # ...the return itself: another arrival at that address is not it
                del self._due[back]
                self.stops.append(self._stop(RETURNED.format(what), sp, True))
        return read


def watched_over(memory, registers, disk, io, ours, places, until, tally, returns=(), serving=None, crafted=(), budget=A_PASS_INSNS):
    """ONE SHORE'S RUN over the sixteen megabytes `memory`, entered with `registers`, `disk` in the drive: observed at
    each address of `places` (`{address: what}`), ended at its first arrival at `until`. `ours`: the blob the
    machine holds (an `aes_boot.Ours`), None on the ROM's shore. `tally`: what is read at every stop (a tuple of
    running totals: differenced from the run's start). `serving`: `{what: the word}` — each such routine answered
    where the run stands at its entry. `crafted`: `((what, ((address, bytes), ...)), ...)` — A LABELLED CRAFT, bytes
    laid where the run first arrives at that checkpoint (its `Stop` kept first: the machine as the run made it). A
    `Watched`. THE PROFILE IS ON FOR THE RUN (the caller's tally reads it), never reset: refused by name inside
    another profiled measurement."""
    watching = _Watching(memory, {address: what for address, what in places.items() if address != until}, tally,
                         returns, serving or {}, ours, crafted)
    run = aes_boot._Run(memory, aes_boot.Floppy(memory, disk), budget, until=until, ours=ours, observing=watching.observing)
    run._observing = watching.observing     # ...the SAME dict: a return's stop is added while the run is in flight
    aes_event.vet_the_profile_is_free("a watched run of the two shores")
    emu.prof_enable(True)
    try:
        watching.begun(registers)
        with aes_event.profile_held(PROFILE_HELD_BY_A_WATCHED_RUN):
            run.to_an_idle(registers, aes_boot._io_seed(io))
        ended = watching._stop(places.get(until, f"{until:#x}"), emu.bench_door_sp(), True)
        ledger = tuple(aes_boot._CPU.osh_write_addrs()[:aes_boot._CPU.osh_num_writes()])
        _writes, truncated = emu.bench_writes(memory)
        if truncated:
            raise Refused("the watched run's write ledger saturated: what it stored between two checkpoints is not known")
    finally:
        emu.prof_enable(False)
        aes_boot._CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    aes_boot.rom_bench.vet_the_run_just_made("a watched run of the two shores")
    return Watched(tuple(watching.stops) + (ended,), ledger, ended, tuple(watching.served))


# ---- A PASS: where both shores' runs begin, what they are watched at, where they end -------------------------------------------
THE_BLANK_DISK, THE_INF_DISK, THE_INF_DISK_CHANGED = "the blank disk", "the DESKTOP.INF disk", "the DESKTOP.INF disk asking another resolution"
DISKS = {THE_BLANK_DISK: lambda: (aes_boot.preinit(), aes_boot.blank_disk()),
         THE_INF_DISK: lambda: (aes_boot.inf_preinit(), aes_boot.inf_disk_of()),
         THE_INF_DISK_CHANGED: lambda: (aes_boot.inf_preinit(), aes_boot.inf_disk_of(resolution=aes_boot.RESOLUTION_CHANGED))}
Pass = namedtuple("Pass", "what disk checkpoints until answer calls serving crafted", defaults=(None, (), (), ()))
Pass.__doc__ = """One run of both shores: `what` it is; the `disk` (a key of DISKS); the `checkpoints` it is watched at
and the one it ends at (`until`: its name). FROM THE PRE-INIT STOP where `answer` is None — the boot's own first
pass —, else FROM deskmain's ENTRY THROUGH THE SERVED DOOR (a labelled argument class): deskmain answered `answer`
after `calls` (`aes_boot.answered_at_its_entry`'s: the ROM's routines called over each stopped machine), and each
routine of `serving` (`((its checkpoint's name, the word), ...)`) answered where the run arrives at it. `crafted`:
A LABELLED CRAFT (`((a checkpoint's name, ((address, bytes), ...)), ...)`) — bytes laid ON BOTH SHORES where each
run first arrives at that checkpoint: a state no boot here makes (a text cell higher than it is wide), said in the
pass's own name."""
SHOW_FILE, PRINT_FILE, FORMAT, COPY_DISK = (aes_boot.SERVED_ROUTINES[getattr(addrs, name)][0] for name in (
    "AES_ROM_DESK_SHOW_FILE", "AES_ROM_DESK_PRINT_FILE", "AES_ROM_DESK_FORMAT", "AES_ROM_DESK_COPY_DISK"))
THE_BUILT_INS = {SHOW_FILE: (0xfe, addrs.AES_ROM_DESK_SHOW_FILE), PRINT_FILE: (0xfd, addrs.AES_ROM_DESK_PRINT_FILE),
                 FORMAT: (0xfc, addrs.AES_ROM_DESK_FORMAT), COPY_DISK: (0xfb, addrs.AES_ROM_DESK_COPY_DISK)}
A_FILE_OF_THE_DISK = aes_boot.accessory_disk.INF_NAME.encode()      # the DESKTOP.INF itself: what a launch finds on that disk
SH_WRITE, STRING_ROOM = "AES_ROM_SH_WRITE", 0x80


def shel_write(command, tail):
    """THE ROM'S OWN shel_write(1, 1, 0, command, tail) as the served door calls it over a stopped machine (`calls`):
    the two strings staged in the call's image alone — the shell's buffers are then what a real call leaves."""
    pokes = case.merge_pokes(aes_objdraw.string_pokes(command, at=aes_resource.BUFFER_AT, room=STRING_ROOM),
                             aes_objdraw.string_pokes(tail, at=aes_resource.SECOND_BUFFER_AT, room=STRING_ROOM))
    return SH_WRITE, (1, 1, 0, aes_resource.BUFFER_AT, aes_resource.SECOND_BUFFER_AT), tuple(sorted(pokes.items()))


def first_pass(disk):
    return Pass(f"the boot's first pass, {disk}", disk, THE_FIRST_PASS, DESKMAIN_ENTERED)


def teardown_pass(disk=THE_BLANK_DISK):
    return Pass(f"deskmain answers 0: the teardown and the second pass, {disk}", disk, THE_TEARDOWN_AND_THE_SECOND_PASS,
                DESKMAIN_ENTERED, 0)


def built_in_pass(built_in, disk=THE_INF_DISK):
    """deskmain answers 1 with the shell's tail a built-in's byte and a name: sh_cmd's arm, the built-in served."""
    byte, entry = THE_BUILT_INS[built_in]
    checkpoints = (*THE_NEXT_PASS_BEGINS, Checkpoint(built_in, entry, THE_ROM_S_OWN), *A_BUILT_IN_PASS[len(THE_NEXT_PASS_BEGINS):])
    return Pass(f"deskmain answers 1 for {built_in}, {disk}", disk, checkpoints, DESKMAIN_ENTERED, 1,
                (shel_write(A_FILE_OF_THE_DISK, bytes((byte,)) + A_FILE_OF_THE_DISK),), ((built_in, 0),))


def launch_pass(disk=THE_INF_DISK):
    """deskmain answers 1 with a command the disk holds and no tail: sh_cmd answers 0, the file is found, dos_exec entered."""
    return Pass(f"deskmain answers 1 for a program the disk holds, {disk}", disk, THE_LAUNCH_PASS, DOS_EXEC_ENTERED, 1,
                (shel_write(A_FILE_OF_THE_DISK, b""),))


def the_rom_s_tally():
    tier3 = bench_tier3()
    return (tier3._cycles_in(tier3.AES_OWN_SPANS), tier3._cycles_in((tier3.LINE_F_HANDLER_COPY,)), 0, 0,
            emu.prof_cycles(*tier3.GEM_SELECTOR_SWITCH), 0, emu.prof_cycles(GEM_ENTRY, GEM_ENTRY_END))


def our_tally(blob):
    tier3 = bench_tier3()
    glue, selector = tier3.glue_of(blob), tier3.our_selector_switch(blob)

    start = blob.entry(aes_boot.GEM_ENTRY_SYMBOL)

    def tally():
        in_glue = tier3._cycles_in(glue)    # (the thunks lie inside the blob: its own cycles are net of them)
        return (tier3._cycles_in(tier3.AES_OWN_SPANS), tier3._cycles_in((tier3.LINE_F_HANDLER_COPY,)), tier3.our_cycles(blob) - in_glue,
                in_glue, emu.prof_cycles(*tier3.GEM_SELECTOR_SWITCH), emu.prof_cycles(*selector) if selector else 0,
                emu.prof_cycles(start, start + GEM_ENTRY_END - GEM_ENTRY))
    return tally


# What a `Stop.tally` holds, in order: the cycles in the ROM's AES-own spans (its text less the selector switch, and
# the Line-F handler's RAM copy), in that copy alone, in OUR build's own code (the blob less its selector switch and
# its thunks), in its thunks, in the ROM's selector switch and in ours — and in gem_entry's own body, each shore's.
IN_THE_ROM_S_AES, IN_THE_LINE_F_COPY, IN_OURS, IN_OUR_GLUE, IN_THE_ROM_S_SELECTOR, IN_OUR_SELECTOR, IN_GEM_ENTRY_ITSELF = range(7)


def places_of(checkpoints, blob):
    """`{address: what}` of a run's stops on one shore (`blob` None: the ROM's) — its checkpoints and the
    dispatcher's entry of a process: the ROM's switchto on both shores (the desk's process switches through the
    ROM's), and on ours the build's own."""
    places = {(checkpoint.rom if blob is None else our_address(checkpoint, blob)): checkpoint.what for checkpoint in checkpoints}
    assert len(places) == len(checkpoints), "two checkpoints of one run stand at one address"
    places[addrs.AES_ROM_SWITCHTO_RTE] = A_SWITCH
    if blob is not None:
        places[aes_switching.our_dispatcher(blob).rte] = A_SWITCH
    return places


def until_of(a_pass, blob):
    checkpoint, = [each for each in a_pass.checkpoints if each.what == a_pass.until]
    return checkpoint.rom if blob is None else our_address(checkpoint, blob)


def began_at(a_pass, blob):
    """WHERE ONE SHORE'S RUN OF `a_pass` BEGINS: `(the sixteen megabytes, the register file, the disk, the shifter's
    bytes, the blob the machine holds)` — the pre-init machine (the blob laid and the PC at its gem_entry, on ours:
    `aes_boot`'s own lay, its premises vetted), or deskmain's entry of that shore's boot, ANSWERED (the served door)."""
    machine, disk = DISKS[a_pass.disk]()
    ours = aes_boot.ours_of(blob) if blob is not None else None
    if a_pass.answer is None:
        memory = bytearray(BASE_IMAGE)
        memory[:RAM_BYTES] = machine.ram
        if ours is None:
            return memory, machine.registers, disk, machine.io, None
        aes_boot.vet_an_our_boot_is_asked_right(machine, disk, ours)
        return memory, aes_boot.BootingOurs(memory, ours).entered(machine.registers), disk, machine.io, ours
    laid = dict(ours=ours, laid=aes_boot.AT_GEM_ENTRY) if ours is not None else {}
    at_the_desk = aes_boot.booted(machine, disk, until=DESKMAIN, **laid)
    bench_tier3()                       # ...the registry: a routine called over the machine is framed by its own battery
    _name, _at, memory, _called, registers = aes_boot.answered_at_its_entry(at_the_desk, a_pass.answer, a_pass.calls)
    return memory, registers, at_the_desk.disk, at_the_desk.io, ours


def watched(a_pass, blob=None):
    """ONE SHORE'S RUN OF `a_pass` — the ROM's (`blob` None) or `blob`'s (a `RomBench`) — a `Watched`."""
    memory, registers, disk, io, ours = began_at(a_pass, blob)
    tally = the_rom_s_tally if blob is None else our_tally(blob)
    return watched_over(memory, registers, disk, io, ours, places_of(a_pass.checkpoints, blob), until_of(a_pass, blob), tally,
                    returns=ENTERED_AND_RETURNED, serving=dict(a_pass.serving), crafted=a_pass.crafted)


# ---- THE CLASSES TWO SHORES' MACHINES DIFFER IN AT A CHECKPOINT, BY NATURE ----------------------------------------------------
# Each LOCATED THROUGH THE MACHINES' OWN POINTERS AND THE TWO STACK POINTERS AT THE STOP — never an address a capture
# or a blob's layout decides. TWO KINDS, held two ways (`vet_alike`):
#   * THE LIVE ONES (`LIVE_CLASSES`) — bytes the machine WILL READ, each build's own by nature: PD0's live frames, and
#     the screen manager's saved context and stack once it has had its first turn. NAMED BY EVERY COMPARISON THAT
#     NEEDS ONE, AND REFUSED WHERE NAMED AND NOT NEEDED (a class that excuses nothing would be one nobody misses the
#     day it excuses a real store): a row names them, a checkpoint's table names them. What vets their content is
#     what the machine DOES with it — the run on to the next checkpoint, and for PD0's frames the served passes.
#   * THE DEAD ONES (`DEAD_CLASSES`) — residue of code that ran, WRITTEN BEFORE IT IS READ AGAIN: stacks below a
#     stack pointer or left for good, save areas laid at every entry. Whether two builds' residue happens to differ
#     in one at a given stop is an accident of their frames, so they are not named stop by stop: EACH IS PROVED DEAD
#     BY NOISE, AT EVERY CHECKPOINT, ON THE ROM'S OWN MACHINE (`noise_proved`: the spans a comparison there leaves
#     out filled with noise, the ROM run on to the next checkpoint — the same machine there outside them).
THE_BLOB = aes_boot.THE_BLOB
FIRST_STACK_RESIDUE = ("gem_entry's first stack under its top longword: the residue of each build's own frames there — read by "
                       "nothing again (the stack is left for good at the loop's foot; an interrupt taken on it pushes over it)")
GEMDOS_S_STACK = "GEMDOS's own stack, to its top: every `trap #1` reloads it — the last caller's registers and return sites"
THE_BIOS_S_STACK = ("the BIOS's own stack, which gem_entry's Super leaves for good: the frame of that trap, a return site inside "
                    "each build's gem_entry")
TRAP_SAVE = aes_boot.TRAP_SAVE_FRAME
BASEPAGE_SAVE = ("the AES's basepage's register save area: D0, A3-A6 and the frame pointer of whoever made the last `trap #1`, "
                 "laid at every trap's entry before they are read")
CONDITION_CODES = ("the condition codes in the three SR save words (their low bytes): the flags of whichever build's last "
                   "instruction before the mask was parked")
DISPATCHER_STACK = "the dispatcher's own stack, dead while a process runs: the frames of the build whose dispatcher last ran"
PD0_CONTEXT = "PD0's saved context in its UDA, stale while it runs: the registers of the build that last called dsptch"
PD0_DEAD = "PD0's stack below the lower of the two stack pointers: dead frames of each build's own start-up"
PD0_FRAMES = ("PD0's LIVE FRAMES, from the lower of the two stack pointers to the stack's top: each build's own — gem_entry's "
              "return, gem_main's and the shell's (VETTED BY WHAT THE CALLER DOES WITH AN ANSWER: the served passes)")
MANAGER_CONTEXT, MANAGER_STACK = aes_boot.SAVED_CONTEXT, aes_boot.MANAGER_STACK
LINE_F_MASK = aes_boot.LINE_F_MASK
XBIOS_RETURN_SITE = ("the XBIOS door's parked return site: the address trp14 was last reached with, laid at every call before it "
                     "is read — its caller's own site in the ROM (and in the C twin, which is handed it), the generated thunk's "
                     "where a build's C reaches the `.S` through glue")
DEAD_CLASSES = (FIRST_STACK_RESIDUE, GEMDOS_S_STACK, THE_BIOS_S_STACK, TRAP_SAVE, BASEPAGE_SAVE, CONDITION_CODES, DISPATCHER_STACK,
                PD0_CONTEXT, PD0_DEAD, LINE_F_MASK, XBIOS_RETURN_SITE)
LIVE_CLASSES = (PD0_FRAMES, MANAGER_CONTEXT, MANAGER_STACK)
CCR_BYTE = 1                            # of a status word: its low byte, the condition codes
UDA0, UDA1 = aes.AES_THEGLO, aes.AES_UDA1


def _context_of(uda):
    (lo, hi, _why), = aes_switch.uda_context_drop(uda)
    return ((lo, hi),)


def classes_at(the_rom_s, ours, blob_span):
    """THE CLASSES (above) over two shores' `Stop`s at one checkpoint, `{class: ((lo, hi), ...)}`: every one that CAN
    differ where the two stack pointers stand — `compared` counts each, and a comparison names the ones it needs."""
    (first_lo, first_top), (pd0_lo, pd0_top) = (aes_stack.gem_entry_s_stacks()[which] for which in (aes_stack.THE_FIRST_STACK, aes_stack.PD0_S_STACK))
    lower, saved = min(the_rom_s.sp, ours.sp), case.long_in(the_rom_s.ram, addrs.SYSVAR_SAVPTR) & BUS
    basepage = case.long_in(the_rom_s.ram, addrs.GEMDOS_P_RUN) & BUS
    dispatcher_lo, dispatcher_top = aes_event.DISPATCHER_STACK
    for stop in (the_rom_s, ours):
        if dispatcher_lo <= stop.sp <= dispatcher_top:
            raise Refused(f"a checkpoint taken ON THE DISPATCHER'S STACK (SP {stop.sp:#x} at {stop.what}): its frames are live there")
    classes = {
        THE_BLOB: (blob_span,),
        GEMDOS_S_STACK: ((preinit_snapshot.GEMDOS_STACK_FLOOR, preinit_snapshot.GEMDOS_STACK_TOP),),
        THE_BIOS_S_STACK: ((preinit_snapshot.BIOS_STACK_TOP - preinit_snapshot.STACK_DEAD_BYTES, preinit_snapshot.BIOS_STACK_TOP),),
        TRAP_SAVE: ((saved - addrs.TRAP_SAVE_FRAME_BYTES, saved),),
        BASEPAGE_SAVE: ((basepage + addrs.BASEPAGE_SAVED_D0, basepage + addrs.BASEPAGE_SAVED_FRAME + LONG_BYTES),),
        CONDITION_CODES: tuple((word + CCR_BYTE, word + WORD_BYTES) for word in sorted(aes_event.SR_DROPS)),
        DISPATCHER_STACK: ((dispatcher_lo, dispatcher_top),),
        PD0_CONTEXT: _context_of(UDA0), MANAGER_CONTEXT: _context_of(UDA1),
        MANAGER_STACK: ((UDA1 + aes.UDA_STATE_BYTES, aes.AES_UDA1_STACK_TOP),),
        LINE_F_MASK: tuple((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW),
        XBIOS_RETURN_SITE: ((aes.AES_XBIOS_RETURN, aes.AES_XBIOS_RETURN + LONG_BYTES),)}
    if first_lo <= lower <= first_top:      # ...both still on gem_entry's first stack (its own arms' checkpoints)
        if not (first_lo <= the_rom_s.sp <= first_top and first_lo <= ours.sp <= first_top):
            raise Refused(f"at {ours.what} one shore stands on gem_entry's first stack and the other does not")
        # (EVERY checkpoint of gem_entry's stands at this stack's TOP on both shores: frames of its own between a lower
        # stack pointer and the top would be no class — compared exactly, and a difference there said)
        classes[FIRST_STACK_RESIDUE] = ((first_lo, min(lower, first_top - LONG_BYTES)),)
    elif the_rom_s.what == BEGAN and the_rom_s.sp == ours.sp and not the_rom_s.registers["sr"] & aes_boot.SR_SUPERVISOR:
        pass                                # ...the pre-init stop itself, in user state: gem_entry has taken no stack yet
    else:
        if not pd0_lo <= lower <= pd0_top or not pd0_lo <= max(the_rom_s.sp, ours.sp) <= pd0_top:
            raise Refused(f"at {ours.what} the two shores stand at SP {the_rom_s.sp:#x} and {ours.sp:#x}: not both on PD0's stack")
        classes.update({FIRST_STACK_RESIDUE: ((first_lo, first_top - LONG_BYTES),), PD0_DEAD: ((pd0_lo, lower),),
                        PD0_FRAMES: ((lower, pd0_top),)})
    return classes


# ---- A CODE ADDRESS IS MAPPED, NEVER DROPPED --------------------------------------------------------------------------------
# THE REGISTRY'S (`tier3.code_relocations`): `$88`, `$404`, the screen manager's entry, the VDI's three vectors and the
# contrl longwords a vex hands — and, ACTIVATED BY THIS SLICE because gem_entry's own run stores them, justretf's slot
# `$947a`, the tick glue's (`$947e`, the VDI's tick vector) and the desk's trampoline slot `$8c32`.
# AND ONE LONGWORD THAT IS NO SLOT OF THE REGISTRY, because no instruction stores it BY VALUE: THE TOP LONGWORD OF
# gem_entry's FIRST STACK, `$8990` — A CODE ADDRESS'S HALF, A CLASS OF ITS OWN, AND NEVER CALLED DEAD. Its low word is
# THE USABLE-DISK WORD the `#E` reader and ldaccs test (`$8992`: non-zero is all they ask; `test_aes_gemstart.py`
# holds each blob's layout to that), and what it holds is a RETURN ADDRESS a `jsr` of gem_entry's pushed there:
#   * WHOLE, once the first pass's `jsr` of size_theglo has run (nothing on that pass pushes over it again);
#   * ITS HIGH WORD ALONE between gem_entry's `move.w #1,$8992` and that `jsr` (one checkpoint: the loop's top) — the
#     high word of rom_rsc_init's return address, over the 1.
# It is given the ROM's name THROUGH gem_entry's OWN OFFSETS — the `.S` is byte-pinned, so an instruction of the
# build's gem_entry lies as far from its entry as the ROM's from `$fd9eca` — and compared exactly.
THE_FIRST_STACK_S_TOP_LONGWORD = aes_stack.gem_entry_s_stacks()[aes_stack.THE_FIRST_STACK][1] - LONG_BYTES
THE_SYMBOL = aes_boot.GEM_ENTRY_SYMBOL  # the run the registry is read for: the build's own start-up
RSC_INIT_RETURNS_TO = RSC_INIT_CALLED_AT + WORD_BYTES + LONG_BYTES
HIGH_WORD = 16
assert THE_FIRST_STACK_S_TOP_LONGWORD + WORD_BYTES == aes.header_constants("loader.h")["AES_DISK_USABLE"], "the usable-disk word is its low word"


def relocations_of(blob):
    """The registry's relocations for a run of the start-up on `blob`, each with a mapping this build links."""
    tier3 = bench_tier3()
    return tuple(each for each in tier3.code_relocations(blob.elf, THE_SYMBOL) if each.mapping)


def mapped_back(ram, blob, without=()):
    """OUR shore's megabyte `ram` WITH EVERY CODE ADDRESS GIVEN THE ROM'S NAME (above): a bytearray. `without`: the
    declarations LEFT UNMAPPED (their `what` — a test's, to show each mapping is needed; `THE_FIRST_STACK_S_TOP_LONGWORD`
    for the one that is no declaration)."""
    tier3, mapped = bench_tier3(), bytearray(ram)
    tier3.mapped_back(mapped, [each for each in relocations_of(blob) if each.what not in without])
    if THE_FIRST_STACK_S_TOP_LONGWORD not in without:
        held, start = case.long_in(mapped, THE_FIRST_STACK_S_TOP_LONGWORD), blob.entry(aes_boot.GEM_ENTRY_SYMBOL)
        ours_returns_to = start + RSC_INIT_RETURNS_TO - GEM_ENTRY
        if start <= held < start + GEM_ENTRY_END - GEM_ENTRY:
            named = held - start + GEM_ENTRY
        elif held == (ours_returns_to >> HIGH_WORD << HIGH_WORD | GEM_DISK_USABLE):
            named = RSC_INIT_RETURNS_TO >> HIGH_WORD << HIGH_WORD | GEM_DISK_USABLE
        else:
            named = held                # ...anything else is no code address of gem_entry's: compared as it stands
        mapped[THE_FIRST_STACK_S_TOP_LONGWORD:THE_FIRST_STACK_S_TOP_LONGWORD + LONG_BYTES] = named.to_bytes(LONG_BYTES, "big")
    return mapped


Compared = namedtuple("Compared", "differing within")
Compared.__doc__ = """Two shores' machines at one checkpoint: `differing` — the `(address, length)` runs they differ at
OUTSIDE every class of `classes_at` — and `within`: `{class: how many bytes differ in it}`, the zeroes left out."""


def compared(the_rom_s, ours, blob, without=()):
    """THE COMPARISON at one checkpoint: `the_rom_s` and `ours` (two `Stop`s with their megabytes), our code addresses
    mapped back, every class counted and left out. A `Compared`."""
    theirs, mine = the_rom_s.ram, mapped_back(ours.ram, blob, without)
    within, classes = {}, classes_at(the_rom_s, ours, (blob.base, blob.end))
    every = sorted(span for spans in classes.values() for span in spans if span[0] < span[1])
    if any(hi > lo_after for (_lo, hi), (lo_after, _hi) in zip(every, every[1:])):
        raise Refused(f"two classes of one comparison overlap at {the_rom_s.what}: {[(hex(lo), hex(hi)) for lo, hi in every]}")
    for name, spans in classes.items():
        differing = sum(left != right for lo, hi in spans for left, right in zip(theirs[lo:hi], mine[lo:hi]))
        if differing:
            within[name] = differing
        for lo, hi in spans:
            mine[lo:hi] = theirs[lo:hi]
    return Compared(tuple(aes_boot.differing_runs(theirs, bytes(mine))), within)


def vet_alike(who, the_rom_s, ours, blob, live):
    """`compared`, HELD: nothing differs outside the classes, and THE LIVE CLASSES THAT DIFFER ARE EXACTLY `live` — one
    named and not needed excuses a store for nothing, one needed and not named is a difference nobody declared. (The
    dead ones are held by their noise proof: above.) A `Compared`."""
    found = compared(the_rom_s, ours, blob)
    if found.differing:
        shown = [(f"{at:#x}", the_rom_s.ram[at:at + min(length, 8)].hex(), bytes(mapped_back(ours.ram, blob)[at:at + min(length, 8)]).hex())
                 for at, length in found.differing[:aes_event.COMPARED_DIFFERENCES_SHOWN]]
        raise Refused(f"{who}: OUR MACHINE IS NOT THE ROM'S outside the classes — {sum(length for _at, length in found.differing)} "
                      f"byte(s) in {len(found.differing)} run(s), the first (address, the ROM's, ours): {shown}")
    needed = sorted(name for name in found.within if name in LIVE_CLASSES)
    if needed != sorted(live):
        raise Refused(f"{who}: of the LIVE classes the two machines differ in {needed} and the comparison names "
                      f"{sorted(live)} — a class named and not needed, or needed and not named")
    return found


# ---- BOTH SHORES, HELD ---------------------------------------------------------------------------------------------------------
Both = namedtuple("Both", "the_rom_s ours blob a_pass")
Both.__doc__ = """One pass on both shores (`both_shores`): the two `Watched`, the blob ours was, and the `Pass`."""


@functools.lru_cache(maxsize=4)
def _both(a_pass, elf):
    blob = next(aes_stack.blob_of(shore) for shore in aes_stack.BLOBS if str(aes_stack.blob_of(shore).elf) == elf)
    return Both(watched(a_pass), watched(a_pass, blob), blob, a_pass)


def both_shores(a_pass, blob):
    """`a_pass` RUN ON BOTH SHORES — the ROM's own and `blob`'s — once a process (the megabytes are not kept on disk)."""
    return _both(a_pass, str(blob.elf))


def checkpoints_of(run):
    """`{what: its Stop}` — each checkpoint's FIRST arrival (the one whose megabyte was kept), in the run's order."""
    return {stop.what: stop for stop in run.stops if stop.ram is not None}


def who_ran(both):
    """WHO RAN, to where the pass ended: `(our run's cycles in the blob, its cycles in the ROM's GEM text and Line-F
    copy, the ROM's run's cycles in its own AES spans)` — the middle one zero, or the pass is refused."""
    ours, the_rom_s = both.ours.ended.tally, both.the_rom_s.ended.tally
    in_ours = ours[IN_OURS] + ours[IN_OUR_GLUE] + ours[IN_OUR_SELECTOR]
    in_the_rom_s = ours[IN_THE_ROM_S_AES] + ours[IN_THE_ROM_S_SELECTOR]
    if in_the_rom_s or not in_ours or not the_rom_s[IN_THE_ROM_S_AES]:
        raise Refused(f"WHO RAN: our run spent {in_the_rom_s} cycles IN THE ROM'S OWN GEM TEXT (its Line-F handler's copy "
                      f"among it: {ours[IN_THE_LINE_F_COPY]}) and {in_ours} in the blob; the ROM's {the_rom_s[IN_THE_ROM_S_AES]} "
                      f"in its own")
    return in_ours, in_the_rom_s, the_rom_s[IN_THE_ROM_S_AES]


def stores_differing(both, since, until, left_out):
    """THE BYTES ONE SHORE STORED AND THE OTHER DID NOT between the checkpoints `since` and `until` (their names; None:
    from the run's start), outside the spans `left_out`: `(the ROM's run's alone, ours alone)` as sorted addresses.
    Each shore's own write ledger — a store of the value a byte holds already is a store."""
    def stored(run):
        marks = {stop.what: stop.written for stop in run.stops if stop.ram is not None}
        return {at for at in run.ledger[marks[since] if since else 0:marks[until]]
                if at < RAM_BYTES and not any(lo <= at < hi for lo, hi in left_out)}
    the_rom_s, ours = stored(both.the_rom_s), stored(both.ours)
    return sorted(the_rom_s - ours), sorted(ours - the_rom_s)


# ---- A STRETCH, PRICED (ruling W4-R11) ---------------------------------------------------------------------------------------
Stretch = namedtuple("Stretch", "routine what a_pass since until differs turns", defaults=(0,))
Stretch.__doc__ = """One priced row: the `routine` it is a row of (an `addrs` name), `what` the case is, the `Pass` it
is a stretch of, the two checkpoints it runs between (`since`, `until`: names), `differs` — THE LIVE CLASSES the
two shores' machines differ in where the stretch ends, each needed (`vet_alike`) — and `turns`: HOW MANY TURNS OF
ANOTHER PROCESS (the screen manager's) lie inside it, PINNED — each is a line of the table under the row, and the
count of those lines is held against the registry (`test_aes_switching.py`)."""
Priced = namedtuple("Priced", "costs own glue line_f turns shared deepest in_the_rom_s")
Priced.__doc__ = """A stretch's price (`priced`): `costs` — `((the ROM's instructions, cycles), (ours))` between its
two checkpoints; `own` — `(ours, the ROM's)` cycles of each shore's own AES code in it, the turns of another process
cut out; our thunks' cycles (`glue`); the ROM's own cycles that are its Line-F handler's (`line_f`); `turns` —
`((ours, the ROM's, glue, shared, the ROM's Line-F), ...)`, each turn of another process inside the stretch; `shared`
— the OS both run outside the turns, one number; `deepest`, the stack pointers at the stretch's end (the ROM's,
ours); and `in_the_rom_s` — OUR run's cycles in the ROM's own AES spans and selector switch OVER THE STRETCH, measured:
what the table's general who-ran guard is handed for the row (`tier3.vet_our_run_kept_out_of_the_aes`)."""


# EVERY STRETCH HERE IS THE START-UP'S OWN PROCESS'S — PD0, the shell's: gem_entry, gem_main and sh_main run as it
# (`rlr` names nothing before gem_main's first stretch has made it the running process: read, it would say 0).
THE_START_UP_S_PROCESS = aes.SHELL_PD


def between(run, since, until):
    """The `Stop`s of `run` from the first arrival at `since` to the one at `until` (both included)."""
    names = [stop.what for stop in run.stops]
    if since not in names or until not in names[names.index(since):]:
        raise Refused(f"the run does not go from {since} to {until}: it arrived at {[name for name in names if name != A_SWITCH]}")
    first = names.index(since)
    return run.stops[first:names.index(until, first) + 1]


def _spent(before, after):
    return (after.instructions - before.instructions, after.cycles - before.cycles,
            tuple(now - then for now, then in zip(after.tally, before.tally)))


def turns_in(stops, own):
    """The turns of ANOTHER PROCESS inside a stretch: `[(instructions, cycles, tally)]` — each from the dispatcher's
    entry of a process that is not `own` to its next entry of `own`."""
    turns, began = [], None
    for stop in stops:
        if stop.what != A_SWITCH:
            continue
        if stop.running != own and began is None:
            began = stop
        elif stop.running == own and began is not None:
            turns.append(_spent(began, stop))
            began = None
    if began is not None:
        raise Refused(f"the stretch ends inside another process's turn (entered at instruction {began.instructions})")
    return turns


def priced(stretch, blob):
    """THE PRICE OF `stretch` ON `blob` (above), its differential first: both shores arrive at its two checkpoints,
    WHO RAN, the megabyte where it ends is the ROM's outside the classes it names (each needed), and the OS both
    run costs the same cycles on both shores, turn by turn. A `Priced`."""
    both = both_shores(stretch.a_pass, blob)
    who = f"{stretch.routine}, {stretch.what} ({aes_stack.shore_of(blob)})"
    who_ran(both)
    rom_stops, our_stops = (between(run, stretch.since, stretch.until) for run in (both.the_rom_s, both.ours))
    vet_alike(who, rom_stops[-1], our_stops[-1], blob, stretch.differs)
    process = THE_START_UP_S_PROCESS
    (rom_insns, rom_cycles, rom), (our_insns, our_cycles, ours) = _spent(rom_stops[0], rom_stops[-1]), _spent(our_stops[0], our_stops[-1])
    rom_turns, our_turns = turns_in(rom_stops, process), turns_in(our_stops, process)
    if not len(rom_turns) == len(our_turns) == stretch.turns:
        raise Refused(f"{who}: {len(rom_turns)} turn(s) of another process on the ROM's shore, {len(our_turns)} on ours, "
                      f"{stretch.turns} pinned")
    turns = []
    for (_rom_n, rom_whole, its), (_our_n, our_whole, mine) in zip(rom_turns, our_turns):
        shared = (rom_whole - its[IN_THE_ROM_S_AES], our_whole - mine[IN_OURS] - mine[IN_OUR_GLUE])
        if shared[0] != shared[1]:
            raise Refused(f"{who}: inside a turn of another process the OS both run costs {shared[0]} cycles on the ROM's shore and {shared[1]} on ours")
        turns.append((mine[IN_OURS], its[IN_THE_ROM_S_AES], mine[IN_OUR_GLUE], shared[0], its[IN_THE_LINE_F_COPY]))
    own = (ours[IN_OURS] - sum(turn[0] for turn in turns), rom[IN_THE_ROM_S_AES] - sum(turn[1] for turn in turns))
    glue = ours[IN_OUR_GLUE] - sum(turn[2] for turn in turns)
    line_f = rom[IN_THE_LINE_F_COPY] - sum(turn[4] for turn in turns)
    in_the_turns = (sum(turn[1] + turn[3] for turn in turns), sum(turn[0] + turn[2] + turn[3] for turn in turns))
    shared = (rom_cycles - own[1] - in_the_turns[0], our_cycles - own[0] - glue - in_the_turns[1])
    if shared[0] != shared[1] or rom[IN_THE_ROM_S_SELECTOR] != ours[IN_OUR_SELECTOR]:
        raise Refused(f"{who}: THE OS BOTH RUN is not one number — {shared[0]} cycles on the ROM's shore, {shared[1]} on ours "
                      f"(the selector switch: the ROM's {rom[IN_THE_ROM_S_SELECTOR]}, ours {ours[IN_OUR_SELECTOR]}): the two runs "
                      f"did not make the same calls of the OS")
    return Priced(((rom_insns, rom_cycles), (our_insns, our_cycles)), own, glue, line_f, tuple(turns), shared[0],
                  (rom_stops[-1].sp, our_stops[-1].sp), ours[IN_THE_ROM_S_AES] + ours[IN_THE_ROM_S_SELECTOR])


# ---- THE ROWS (`bench/tier3.py` reads `STRETCHES`; a battery registers them) -------------------------------------------------------
# `{the registered name: its Stretch}`. A row's function is the routine's own label; its case begins with THE LABEL of
# the machine it is made of (ruling W4-R1), and with THE ARGUMENT CLASS where its pass goes through the served door
# (ruling W4-R6). Its symbol is the entry of the build the routine is: gem_main's target entry, the three C cores.
STRETCHES = {}
SYMBOL_OF = {"AES_ROM_GEM_MAIN": "aes_rom_gem_main", "AES_ROM_GEM_READ_INF": "aes_gem_read_inf", "AES_ROM_SH_MAIN": "aes_sh_main",
             "AES_ROM_SH_CMD": "aes_sh_cmd"}
ON_THE_OUR_BOOT_MACHINE = "LABELLED STAGING (our boot)"
SERVED_AS = "ARGUMENT CLASS (deskmain served {})"


def case_of(stretch):
    """The row's case: the machine's label, the served door's where the pass goes through it, then what it is."""
    a_pass = stretch.a_pass
    if a_pass.answer is None:
        return f"{ON_THE_OUR_BOOT_MACHINE}: {stretch.what}"
    served = SERVED_AS.format(f"{a_pass.answer}, a built-in too" if a_pass.serving else a_pass.answer)
    return f"{ON_THE_OUR_BOOT_MACHINE}, {served}: {stretch.what}"


def function_of(stretch):
    """...and its function: the routine's own Tier 3 label, with its ROM address."""
    return f"{routines.role(stretch.routine)} (${getattr(addrs, stretch.routine):x})"


def row_name(stretch):
    return f"{SYMBOL_OF[stretch.routine]}, {case_of(stretch)}"


def register(stretch):
    """ONE PRICED ROW, registered. THE CAPTURE ITS PASS BOOTS FROM IS READ HERE, as the registry is imported — so that
    `test/test_makefile.py` sees every capture a row is made from among the Makefile's REGISTRY_READS. Nothing is run."""
    assert set(stretch.differs) <= set(LIVE_CLASSES) and row_name(stretch) not in STRETCHES, row_name(stretch)
    DISKS[stretch.a_pass.disk]()
    STRETCHES[row_name(stretch)] = stretch
    return stretch


# ---- THE DEAD CLASSES, PROVED DEAD BY NOISE (on the ROM's own machine, and on OURS) -----------------------------------------------
def noise_proved(both, since, until, seed, also=(), on_ours=False):
    """ONE SHORE'S OWN RUN FROM THE CHECKPOINT `since` TO `until` (the next one), MADE AGAIN OVER NOISE: every byte of the
    DEAD classes the comparison at `since` leaves out — located from the two shores' stops there — replaced by noise
    that differs from it, that shore's code run on from its own stop's register file. THE ROM'S (the default): what
    says the classes are residue the ROM never reads. OURS (`on_ours`): what says OUR BUILD never reads them either
    — a C change that came to read residue would redden here and nowhere on the ROM's shore. Answers `(the (address,
    length) runs the machine it arrives with differs at from that shore's plain run's; the registers that differ;
    how many bytes were noised)` — the first two empty, or a class called dead is read before it is written.
    LEFT OUT WHERE THE RUN ARRIVES: the noised spans and, on the ROM's shore, every class at `until`; ON OURS THE
    STRICTER LEAVE-OUT — the dead classes there and the blob alone, THE LIVE CLASSES COMPARED (one build's own frames
    are the same bytes on two runs of it). `also`: spans noised BESIDE the dead classes and NOT left out where the
    run arrives (the proof's own red: noise in a live byte is found)."""
    shore = both.blob if on_ours else None
    the_rom_s, ours = checkpoints_of(both.the_rom_s), checkpoints_of(both.ours)
    plain = ours if on_ours else the_rom_s
    began, arrives = plain[since], plain[until]
    span = (both.blob.base, both.blob.end)
    dead = [each for name, spans in classes_at(the_rom_s[since], ours[since], span).items() if name in DEAD_CLASSES for each in spans]
    _machine, disk = DISKS[both.a_pass.disk]()
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = aes_boot.noise_over(began.ram, [*dead, *also], seed)
    address = next(address for address, what in places_with_returns(both, shore).items() if what == until)
    tally = our_tally(shore) if on_ours else the_rom_s_tally
    run = watched_over(memory, began.registers, disk, _machine.io, aes_boot.ours_of(shore) if on_ours else None, {address: until},
                       address, tally)
    left_out = [*dead, *(each for name, spans in classes_at(the_rom_s[until], ours[until], span).items()
                         if not on_ours or name in DEAD_CLASSES or name == THE_BLOB for each in spans)]
    theirs, mine = bytearray(arrives.ram), bytearray(run.ended.ram)
    for lo, hi in left_out:
        mine[lo:hi] = theirs[lo:hi]
    registers = sorted(name for name in arrives.registers if arrives.registers[name] != run.ended.registers[name])
    return tuple(aes_boot.differing_runs(bytes(theirs), bytes(mine))), registers, sum(hi - lo for lo, hi in dead)


def places_with_returns(both, blob):
    """`places_of` of the pass on one shore, with the return site of each routine of ENTERED_AND_RETURNED as the run
    found it (the address its entry's stop read at the stack pointer)."""
    run = both.the_rom_s if blob is None else both.ours
    places = places_of(both.a_pass.checkpoints, blob)
    for stop in run.stops:
        if stop.ram is not None and stop.what in ENTERED_AND_RETURNED:
            places[case.long_in(stop.ram, stop.sp) & BUS] = RETURNED.format(stop.what)
    return places


# ---- THE TWO STACK GATES, ON THE OUR-BOOT MACHINE (rulings W4-R9, W4-R4): measured off the watched runs ------------------------
def first_stack_used(run):
    """The bytes of gem_entry's first stack one shore's first pass used: its top less the lowest address its ledger
    stored on it, up to where the stack is left (the checkpoint THE_STACK_MOVED)."""
    bottom, top = aes_stack.gem_entry_s_stacks()[aes_stack.THE_FIRST_STACK]
    left_at = checkpoints_of(run)[THE_STACK_MOVED].written
    return top - min(at for at in run.ledger[:left_at] if bottom <= at < top)


def kept_at_the_door(stop):
    """THE STACK POINTER OUR BUILD STOOD AT BEFORE THE DESK DOOR STOOD IT AT THE ROM'S, read where the callee is
    entered: the door keeps it in D3 for the call (`include/aes/deskdoor.h`) — what the door's own vet compared."""
    return stop.registers["d3"]


# ---- THE ARGUMENTS HANDED THROUGH THE DESK DOOR: what the callee will read, compared exactly --------------------------------------
# At a callee's entry out of the shell BOTH SHORES STAND ON ONE STACK POINTER (the ROM-depth rule, above), so THE
# FRAME THE CALLEE WILL READ — from above its return address to the top of the slot the ROM's own call sequence stores
# its last argument in — lies at the same addresses on both, and IS COMPARED EXACTLY: a comparison of its own, far
# narrower than `PD0_FRAMES` (which leaves every live frame of PD0's out, these bytes among them — so that a build
# handing a callee its arguments in the wrong order arrived at every megabyte checkpoint unseen). The return address
# under it is each shore's own (the ROM's Line-F site, a place in the blob) and is no argument. EVERY ARGUMENT HERE IS
# DATA — a buffer of the shell's, a mode word — and is compared as it stands; a code address among them would be the
# blob's on our shore and DIFFER, said by name, never passed. WHERE THE FRAME ENDS: the stack pointer the ROM's caller
# stands at before the call's frame is laid (sh_main's, or sh_cmd's for a built-in: read off the ROM's own frames by
# the stack battery) plus THE SLOT its call sequence stores in AT that stack pointer (`include/aes/deskdoor.h`:
# Alcyon's scratch longword, the last argument's; deskmain's bare call has none) — `{the callee: that slot's bytes}`.
_DOOR = aes.header_constants("deskdoor.h")
THE_SLOT_OF = {DESKMAIN_ENTERED: _DOOR["DESK_DOOR_NO_SLOT"], DOS_EXEC_ENTERED: _DOOR["DESK_DOOR_SCRATCH_SLOT"],
               **dict.fromkeys(THE_BUILT_INS, _DOOR["DESK_DOOR_SCRATCH_SLOT"])}


def handed_through_the_door(callee, the_rom_s, ours):
    """THE ARGUMENT BYTES `callee` WILL READ, on each shore (two `Stop`s at its entry): `(the ROM's, ours)`. Refused
    where the two shores do not stand on one stack pointer there — the frames would not be the same addresses."""
    if the_rom_s.sp != ours.sp:
        raise Refused(f"{callee} is entered at SP {the_rom_s.sp:#x} on the ROM's shore and {ours.sp:#x} on ours: its arguments "
                      f"cannot be compared address for address")
    in_sh_main, in_sh_cmd = sorted(aes_stack.the_rom_s_sp_at_the_door())      # bytes under PD0's top
    stands = aes_stack.gem_entry_s_stacks()[aes_stack.PD0_S_STACK][1] - (in_sh_cmd if callee in THE_BUILT_INS else in_sh_main)
    lo, hi = ours.sp + LONG_BYTES, stands + THE_SLOT_OF[callee]
    return the_rom_s.ram[lo:hi], ours.ram[lo:hi]


def vet_handed_alike(who, callee, the_rom_s, ours):
    """`handed_through_the_door`, HELD: the callee is handed THE ROM'S ARGUMENTS, byte for byte. Answers them."""
    theirs, mine = handed_through_the_door(callee, the_rom_s, ours)
    if theirs != mine:
        raise Refused(f"{who}: {callee} IS HANDED OTHER ARGUMENTS THAN THE ROM'S — at SP {ours.sp:#x}, above the return "
                      f"address, the ROM's caller laid {theirs.hex(' ', WORD_BYTES)} and ours {mine.hex(' ', WORD_BYTES)}")
    return theirs


# ---- THE CENSUS OF WAVE 4's SIX ROUTINES AT TIER 3 (ruling W4-R11): rows of the table, or one of three reasons ---------------------
IN_THE_TABLE, BY_ITS_CHECKPOINTS = "rows of the table", "held at its checkpoints, both shores, both blobs"
NEVER_RETURNS = "NEVER RETURNS"
RUNS_A_PROGRAM = "RUNS A PROGRAM"
NO_MACHINE = "NO MACHINE"
THE_CENSUS = {
    "AES_ROM_GEM_ENTRY": (NEVER_RETURNS, "the program's entry: a loop with no way out. Held at its checkpoints (the `$2c` test, the "
                                         "clear, the three stores, the stack move; the second pass through the served door); its "
                                         "own instructions' cycles are the ROM's by the pin, and held equal by the battery"),
    "AES_ROM_GEM_GEMDOS_CALL": (IN_THE_TABLE, "six `.S` rows over the recorded trap (an argument class: every caller is band 6's)"),
    "AES_ROM_GEM_MAIN": (IN_THE_TABLE, "stretches to deskmain's entry on two disks; the teardown and the second pass through the served door"),
    "AES_ROM_GEM_READ_INF": (IN_THE_TABLE, "the boot's own call over real GEMDOS, in place: no file, a file, a file that asks another resolution"),
    "AES_ROM_SH_MAIN": (IN_THE_TABLE, "the first pass to deskmain's entry; the passes after a served deskmain"),
    "AES_ROM_SH_CMD": (IN_THE_TABLE, "its five arms after a served deskmain, the built-in served where it is entered"),
}
# ...and WHAT OF THEM HAS NO SECOND COLUMN, by its reason — what a row's notes and STATUS say in these words:
WITHOUT_A_SECOND_COLUMN = {
    "gem_main, whole": (NEVER_RETURNS, "in a boot: its return is the desk's Quit, a hand's — the teardown is run through the served door"),
    "sh_main's launch, past dos_exec's entry": (RUNS_A_PROGRAM, "a real Pexec(0) loads over the blob (THE STANDING LIMIT)"),
    "sh_main's cartridge arm, the cartridge's loader": (NO_MACHINE, "the oracle serves no cartridge (ruling W4-R12): the arm halts by name"),
    "the desk's depth under our frames, past deskmain": (NO_MACHINE, "not claimed: from deskmain's entry the desk calls the ROM's AES (ruling W4-R3)"),
}


# ---- WHAT THE TABLE PRINTS OF A STRETCH, READ BACK (the fix pass: the line net of the ROM's Line-F handler is held) ---------------
# `bench/tier3.py` prints, under each stretch, its whole run's line (its own cycles, the ROM's, its thunks') and its
# ratio NET OF THE ROM'S LINE-F HANDLER — the one place the figures over the bar that the slice REPORTS are printed.
# Read here, each line held to its own integers; `test_aes_ourboot.py` holds each to the stretch's measured price,
# `test_status.py` holds STATUS's quotes to the printed digits.
THE_TABLE = derived.RECREATE / "build" / "bench" / "tier3.txt"
A_FIGURE = "{:.2f}"                     # a ratio as the table prints one
_A_ROW_RE = re.compile(r"^\S.*?\s\$(?P<addr>f[c-e][0-9a-f]+)\s+(?P<case>.+?)\s+\d+/\d+\s+\d+/\d+\s+(?P<ratio>\d+\.\d\d)\s")
_ITS_WHOLE_RUN_RE = re.compile(
    r"^\s+whole run: \d\.\d\d — own (?P<ours>\d+) cycles against the ROM's (?P<the_rom_s>\d+) in the AES's text and Line-F handler; "
    r"the OS both run \d+ against \d+(?:, and (?P<glue>\d+) in thunks: (?P<with_thunks>\d\.\d\d) with them)?$")
_ITS_NET_RE = re.compile(
    r"^\s+net of the ROM's Line-F handler \((?P<line_f>\d+) of its (?P<the_rom_s>\d+), (?P<share>\d+)%\): (?P<net>\d\.\d\d) — printed, "
    r"part of no rule")
_A_TURN_INSIDE_RE = re.compile(r"^\s+screen manager's turn: ours (?P<ours>\d+) / ROM (?P<the_rom_s>\d+) = ")
_A_TURN_S_THUNKS_RE = re.compile(r", and (?P<glue>\d+) in thunks: (?P<with_thunks>\d\.\d\d) with them")
_A_TURN_S_LINE_F_RE = re.compile(r"the ROM's Line-F handler alone is (?P<line_f>\d+) of its (?P<the_rom_s>\d+) \(\d+%\): net of it (?P<net>\d\.\d\d)")
StretchLine = namedtuple("StretchLine", "ours the_rom_s glue line_f with_thunks net turns")
StretchLine.__doc__ = """What the table prints of one stretch: its own cycles and the ROM's, its thunks', the ROM's Line-F
handler's — integers — and, AS PRINTED, its ratio with its thunks and the one net of the handler; `turns`: each turn of
another process under the row, a `TurnInside`."""
TurnInside = namedtuple("TurnInside", "ours the_rom_s glue line_f with_thunks net")


def _printed(ours, glue, the_rom_s, line_f):
    """`(with its thunks, net of the ROM's Line-F handler)` as the table prints the two ratios of those integers."""
    return A_FIGURE.format((ours + glue) / the_rom_s), A_FIGURE.format((ours + glue) / (the_rom_s - line_f))


def _a_turn_inside(line):
    """The `TurnInside` a turn's line under a stretch prints — held to its own integers; None for any other line."""
    head = _A_TURN_INSIDE_RE.match(line)
    if not head:
        return None
    thunks, share = _A_TURN_S_THUNKS_RE.search(line), _A_TURN_S_LINE_F_RE.search(line)
    if not share:
        raise Refused(f"a turn inside a stretch that prints no Line-F share: {line.strip()[:160]}")
    ours, the_rom_s, glue, line_f = int(head["ours"]), int(head["the_rom_s"]), int(thunks["glue"]) if thunks else 0, int(share["line_f"])
    with_thunks, net = _printed(ours, glue, the_rom_s, line_f)
    if (int(share["the_rom_s"]), share["net"]) != (the_rom_s, net) or (thunks and thunks["with_thunks"] != with_thunks):
        raise Refused(f"the table prints a turn's figures its own integers do not make ({with_thunks}, {net}): {line.strip()[:200]}")
    return TurnInside(ours, the_rom_s, glue, line_f, with_thunks, net)


def _a_stretch_s_line(row, under):
    """The `StretchLine` of the row `row` with the indented lines `under` it — ONE whole-run line and ONE line net of
    the Line-F handler, held to their own integers to the printed digits (the share, both ratios)."""
    whole = [found for found in map(_ITS_WHOLE_RUN_RE.match, under) if found]
    net = [found for found in map(_ITS_NET_RE.match, under) if found]
    if not len(whole) == len(net) == 1:
        raise Refused(f"a stretch's row with {len(whole)} whole-run line(s) and {len(net)} net of the Line-F handler: {row[:160]}")
    (whole,), (net,) = whole, net
    ours, the_rom_s, glue, line_f = int(whole["ours"]), int(whole["the_rom_s"]), int(whole["glue"] or 0), int(net["line_f"])
    said = (int(net["the_rom_s"]), net["share"], whole["with_thunks"] or _A_ROW_RE.match(row)["ratio"], net["net"])
    held = (the_rom_s, f"{line_f / the_rom_s:.0%}".rstrip("%"), *_printed(ours, glue, the_rom_s, line_f))
    if said != held:
        raise Refused(f"the table prints a stretch's figures its own integers do not make ({said} for {held}): {row[:120]} / {net[0].strip()}")
    return StretchLine(ours, the_rom_s, glue, line_f, said[2], said[3], tuple(turn for turn in map(_a_turn_inside, under) if turn))


def stretch_lines_of(table):
    """`{a registered stretch's name: its StretchLine}` off the table's text `table`, IN THE TABLE'S ORDER — every
    stretch of the registry found once, and no line net of the Line-F handler under any other row: else refused."""
    names = {(getattr(addrs, stretch.routine), case_of(stretch)): name for name, stretch in STRETCHES.items()}
    lines, found = table.splitlines(), {}
    for at, line in enumerate(lines):
        row = _A_ROW_RE.match(line)
        name = names.get((int(row["addr"], 16), row["case"].strip())) if row else None
        if name is None:
            continue
        if name in found:
            raise Refused(f"the table holds the stretch {name!r} twice")
        under = next((index for index, after in enumerate(lines[at + 1:]) if not after.startswith(" ")), len(lines) - at - 1)
        found[name] = _a_stretch_s_line(line, lines[at + 1:at + 1 + under])
    said = sum(bool(_ITS_NET_RE.match(line)) for line in lines)
    if set(found) != set(STRETCHES) or said != len(found):
        raise Refused(f"the table holds {len(found)} of the {len(STRETCHES)} registered stretches, and {said} line(s) net of the Line-F handler")
    return found
