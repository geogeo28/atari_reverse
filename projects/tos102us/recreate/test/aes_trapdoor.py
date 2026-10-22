r"""THE TRAP DOOR'S MACHINES AND RUNS (`src/aes/trapdoor.S`; `test_aes_trapdoor.py` pins its bytes,
`test_aes_trapdoor_rows.py` runs it) — band 5 wave 3, slice T.

WHAT A CASE OF THE DOOR IS. The door is entered by an exception and left by an `rte`: nothing of it is a call and its
return, and no frame somebody wrote is a state of it. A case is AN ARRIVAL and A TRIP:

  * AN ARRIVAL (`at_the_trap`): the ROM's own boot of a pre-init machine (`aes_boot`: every instruction the ROM's,
    the device model's five services) STOPPED AT THE HANDLER'S FIRST INSTRUCTION, at the n-th `trap #2` one named
    process makes with one selector — BY ADDRESS, and counted by who traps and with what, never by an instruction
    ordinal. The megabyte and the whole register file there: the program's frame {SR, PC} under the supervisor stack
    pointer, D0 the selector, D1 the parameter block.
  * A TRIP (`trip`): the machine run on FROM THE ARRIVAL to where the arm it takes leaves the door — the `rte`'s
    landing in the program (the AES arm: the whole call, every process the dispatcher runs on the way); the handler
    GEM found in the vector (the VDI arm); GEMDOS's own trap handler (the Pterm arm, which never comes back: a
    checkpoint). THE ROM'S SHORE runs on in place. OURS is the same machine with a blob laid in the harness's free
    window and THE CPU ENTERED AT THE BLOB'S HANDLER instead of the ROM's — one register of the file, the PC; the
    vector is not touched (nothing is bound before the flip, slice F), so every OTHER process's trap on the way is
    the ROM's on both shores.

WHAT IS HELD WHERE A TRIP ENDS (`held`): the whole register file (the program's own, where the trip lands in it) and
the megabyte, byte for byte, outside the CLASSES A CASE NAMES — each located from the machine's own pointers, each
REQUIRED TO DIFFER (a class a case passes without is refused) — with the door's own code addresses MAPPED, never
dropped (`mapped_back`). And WHO RAN (`Trip.cycles_in`): the cycle profile of the ROM's own spans of the door and of
the blob's.

LABELLED ARGUMENT CLASSES, the only states here no ROM run makes: selector 201 and selector 0, which no program of
any boot traps with — a real arrival's register file with D0's LOW WORD replaced, on both shores (`relabelled`).
"""
import functools
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu
from recreate_kit import rom_bench

import aes
import aes_boot
import case
import derived
import transcription

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
RAM_BYTES = addrs.ST_RAM_BYTES
BUS = aes.OS_BUS_ADDR_MASK
WORD_MASK = 0xffff
HIGH_WORD = 16                          # a longword's upper half, as a shift

# ---- the door, as the ROM lays it out and as a blob does -------------------------------------------------------------------
HANDLER, AES_ARM, PTERM_ARM = addrs.AES_ROM_TRAP2, addrs.GEM_TRAP2_AES_ARM, addrs.GEM_TRAP2_PTERM_ARM
WAY_OUT, WAY_OUT_RTE, UB_TRAMPOLINE = addrs.AES_ROM_TRAP2_EXIT, addrs.AES_ROM_TRAP2_RTE, addrs.AES_ROM_UB_TRAMPOLINE
REGION_LO, REGION_HI = HANDLER, addrs.AES_ROM_SIGNAL    # ub_trampoline's `rts` is the region's last word: signal follows
ENTRY, ENTRY_END = addrs.AES_ROM_ENTRY, addrs.AES_ROM_ENTRY_END
HANDLER_SYMBOL, WAY_OUT_SYMBOL, UB_SYMBOL, ENTRY_SYMBOL = "aes_rom_trap2", "aes_rom_trap2_exit", "aes_rom_ub_trampoline", "aes_rom_entry"
MARSHAL_THUNK = "aes_entry_to_aes_marshal"
USERDEF_THUNK = "ub_trampoline_to_aes_desk_userdef"     # band 6 slice F3 (N18): ub_trampoline's `jsr`, our C's thunk
SELECTOR_AES, SELECTOR_AES_ALT, SELECTOR_PTERM, SELECTOR_VDI = (
    addrs.GEM_SELECTOR_AES, addrs.GEM_SELECTOR_AES_ALT, addrs.GEM_SELECTOR_PTERM, addrs.GEM_SELECTOR_VDI)
# The handler's second instruction: a second stop inside it, so that a run watched at its first is watched there
# again whatever the stop before was (a door PC a run stands at is armed again only from another stop).
HANDLER_SECOND_INSTRUCTION = HANDLER + 2 * WORD_BYTES
# THE DOOR'S PARTS, each a span of the ROM's text and — by the same name — of a blob's (`our_door`): what a run's
# cycle profile is read over to say WHO RAN. The selector switch is every `trap #2`'s way in (the ROM's own VDI calls
# take it on both shores of any trip); the rest is the AES arm's alone.
SELECTOR_SWITCH, THE_PTERM_ARM, THE_AES_ARM, AES_ENTRY, BEHIND_IT = (
    "the selector switch and the VDI arm", "the Pterm arm", "the AES arm and the way out", "aes_entry",
    "the marshal and the opcode switch")
ROM_DOOR = {SELECTOR_SWITCH: (HANDLER, PTERM_ARM), THE_PTERM_ARM: (PTERM_ARM, AES_ARM), THE_AES_ARM: (AES_ARM, UB_TRAMPOLINE),
            AES_ENTRY: (ENTRY, ENTRY_END + WORD_BYTES),           # ...with its dead return word
            BEHIND_IT: (addrs.AES_ROM_DISPATCH, ENTRY)}
THE_THUNK = "the marshal's thunk"
AN_AES_CALL_S = (THE_AES_ARM, AES_ENTRY, BEHIND_IT)              # what one AES call runs of the door, past the switch
TRIP_INSNS = 2_000_000                  # a trip's budget: the longest measured, appl_init's through three processes, is 51,000


def text_spans(blob):
    """`{symbol: (start, end)}` of every text symbol `blob`'s table sizes."""
    return {symbol.name: (symbol.start, symbol.start + symbol.size)
            for symbol in transcription.symbol_table(str(blob.elf)) if symbol.kind in "Tt" and symbol.size is not None}


def in_the_region(blob, rom_address):
    """Where `blob` holds the ROM address `rom_address` of the door's region: the handler's entry plus the ROM's own
    distance (the byte pin holds the region laid out as the ROM's)."""
    assert REGION_LO <= rom_address < REGION_HI, f"{rom_address:#x} is no address of the door's region"
    return blob.entry(HANDLER_SYMBOL) + rom_address - REGION_LO


def our_door(blob):
    """`{part: (lo, hi)}`: the blob's own door under ROM_DOOR's names — its region's three parts, its aes_entry, the
    C behind it (the marshal and the opcode switch, as the symbol table sizes them) — and the marshal's thunk."""
    of = text_spans(blob)
    behind = (of["aes_marshal"], of["aes_dispatch"])
    return {**{part: (in_the_region(blob, lo), in_the_region(blob, hi))
               for part, (lo, hi) in ROM_DOOR.items() if REGION_LO <= lo < REGION_HI},
            AES_ENTRY: of[ENTRY_SYMBOL], THE_THUNK: of[MARSHAL_THUNK],
            BEHIND_IT: (min(lo for lo, _hi in behind), max(hi for _lo, hi in behind))}


def mapped_back(blob, value):
    """A CODE ADDRESS OF THE DOOR, MAPPED: the ROM's address for `value` where `value` lies in `blob`'s region or is
    its aes_entry's, else `value` — how a longword or a register our run leaves holding a site of its own door is
    compared EXACTLY with the ROM's (the registry's kind of mapping; never a drop)."""
    start = blob.entry(HANDLER_SYMBOL)
    if start <= value < start + REGION_HI - REGION_LO:
        return REGION_LO + value - start
    return ENTRY if value == blob.entry(ENTRY_SYMBOL) else value


# ---- A RUN OF A MACHINE FROM A WHOLE REGISTER FILE TO AN ADDRESS -------------------------------------------------------------
Stopped = namedtuple("Stopped", "ram registers disk instructions cycles streams profile")
Stopped.__doc__ = """Where a run stopped: the megabyte, the CPU's register file (`aes_boot.REGISTER_NAMES`), the disk as
the run left it, what it cost, the three off-image streams, and `profile` — `{(lo, hi): cycles}` for each span the
run was asked about."""


class _Met(Exception):
    """A watched arrival is the one asked for: the run stands stopped there."""


def _run(memory, served, registers, *, until=None, observing=None, profiled=()):
    """`aes_boot`'s own run (the device model's five services, one horizontal blank pending) of `memory` from the
    register file `registers` — `served` the machine it continues (its `disk`, its shifter bytes) — to its first
    arrival at `until`, or to where a reader of `observing` raises `_Met`. An idle met first is REFUSED BY NAME, as a
    boot's `until` is. `profiled`: the spans whose cycles are tallied."""
    floppy = aes_boot.Floppy(memory, served.disk)
    run = aes_boot._Run(memory, floppy, TRIP_INSNS if until else aes_boot.BOOT_INSNS, until=until, observing=observing)
    emu.prof_reset()
    emu.prof_enable(bool(profiled))
    try:
        try:
            run.to_an_idle(registers, aes_boot.io_seed_of(served))
        except _Met:
            pass
        else:
            if until is None:
                raise aes_boot.Refused("the run reached an idle and the arrival it was watched for was never met")
        result, left = run.result, aes_boot.registers_at_the_stop(aes_boot.REGISTER_NAMES)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
        profile = {span: emu.prof_cycles(*span) for span in profiled}
    finally:
        emu.prof_enable(False)
        aes_boot._CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("a run to the trap door, or through it")
    return Stopped(bytes(memory[:RAM_BYTES]), left, bytes(floppy.disk), result["ninsns"], result["cycles"], streams, profile)


def _image_of(ram):
    memory = bytearray(BASE_IMAGE)      # ...for the ROM in it: the megabyte below is the machine's
    memory[:RAM_BYTES] = ram
    return memory


def running_process(memory):
    """`(pd, name)` of the process a machine runs (AES_RLR's head)."""
    pd = case.long_in(memory, aes.AES_RLR) & BUS
    return pd, bytes(memory[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES])


# ---- AN ARRIVAL ---------------------------------------------------------------------------------------------------------------
Arrival = namedtuple("Arrival", "ram registers disk io process")
Arrival.__doc__ = """The ROM's boot stopped at the handler's first instruction, one process's n-th trap with one
selector: the megabyte, the register file (the PC is the ROM's handler), the disk and the shifter bytes a run
continued from it is served, and the PD of the `process` that trapped."""
DESK_NAME = b" " * aes.PD_NAME_BYTES    # the desk's PD carries no name before its own appl_init names it


def padded(name):
    return name.encode().ljust(aes.PD_NAME_BYTES)


Booting = namedtuple("Booting", "disk io")       # what a boot's run is served: the disk in the drive, the shifter's bytes


@derived.kept
def at_the_trap(machine, disk, name, nth=0, selector=SELECTOR_AES):
    """THE ARRIVAL (the module's docstring): the ROM's boot of the pre-init `machine` over `disk`, stopped at the
    handler's first instruction where the process named `name` (a PD's eight bytes) traps for the `nth` time with
    D0.w = `selector`. REFUSED BY NAME where the boot idles first."""
    memory, met = _image_of(machine.ram), []

    def at_the_handler(stopped, _sp):
        selected = aes_boot.registers_at_the_stop(("d0",))["d0"] & WORD_MASK
        if selected == selector and running_process(stopped)[1] == name:
            met.append(None)
            if len(met) > nth:
                raise _Met
    watched = {HANDLER: ("the handler", at_the_handler), HANDLER_SECOND_INSTRUCTION: ("its second instruction", lambda *_: None)}
    try:
        stopped = _run(memory, Booting(disk, machine.io), machine.registers, observing=watched)
    except aes_boot.Refused as idled:
        raise aes_boot.Refused(f"the boot idled after {len(met)} trap(s) of {name!r} with selector {selector:#x}: no "
                               f"{nth}-th to arrive at") from idled
    assert stopped.registers["pc"] == HANDLER and stopped.registers["sr"] & addrs.SR_SUPERVISOR
    return Arrival(stopped.ram, stopped.registers, stopped.disk, machine.io, running_process(memory)[0])


def program_frame(arrival):
    """`(status word, PC)` of the frame the exception pushed for the program: what the way out's `rte` pops."""
    return struct.unpack_from(">HI", arrival.ram, arrival.registers["isp"] & BUS)


def relabelled(arrival, selector):
    """A LABELLED ARGUMENT CLASS: `arrival` with D0's LOW WORD `selector` — a trap no program of any boot makes.
    The machine is the arrival's, every byte; one word of one register is not."""
    registers = dict(arrival.registers)
    registers["d0"] = registers["d0"] & ~WORD_MASK & aes.LONG_MASK | selector
    return arrival._replace(registers=registers)


# ---- A TRIP -------------------------------------------------------------------------------------------------------------------
Trip = namedtuple("Trip", "stopped blob arrival ours")
Trip.__doc__ = """One shore's run from an arrival to where its arm leaves the door: where it `stopped`, the `blob`
whose handler it was entered at (None: the ROM's shore), the `arrival`, and `ours` (the blob as laid, or None)."""


def _vet_our_blob_stands(memory, ours):
    """The blob laid for a trip is still its own bytes where the trip ends: nothing of the machine stored over it."""
    if bytes(memory[ours.base:ours.base + len(ours.image)]) != ours.image:
        raise aes_boot.Refused(f"the trip stored over the blob laid at [{ours.base:#x}, {ours.base + len(ours.image):#x})")


def trip(arrival, until, blob=None, profiled=()):
    """THE TRIP (the module's docstring) from `arrival` to the first arrival at `until`: the ROM's shore, or — `blob`
    a `RomBench` — ours: the blob laid where the machine holds nothing (refused otherwise) and the CPU entered at ITS
    handler's first instruction."""
    memory, registers, ours = _image_of(arrival.ram), dict(arrival.registers), None
    if blob is not None:
        ours = aes_boot.ours_of(blob)
        aes_boot._vet_clear_where_the_blob_goes(memory, ours)
        memory[ours.base:ours.base + len(ours.image)] = ours.image
        registers["pc"] = blob.entry(HANDLER_SYMBOL)
    stopped = _run(memory, arrival, registers, until=until, profiled=profiled)
    if ours is not None:
        _vet_our_blob_stands(memory, ours)
    return Trip(stopped, blob, arrival, ours)


def profiled_spans(blob):
    """The spans a trip is profiled over on either shore: every part of the ROM's door and of `blob`'s."""
    return (*ROM_DOOR.values(), *our_door(blob).values())


def cycles_in(made, door_of, *parts):
    """The cycles the trip `made` spent in `parts` of a door (`ROM_DOOR`, or a blob's `our_door`)."""
    return sum(made.stopped.profile[door_of[part]] for part in parts)


def vet_who_ran(the_rom_s, ours, others_trap=False):
    """WHO RAN two profiled trips of one arrival, by their cycles (refused by name otherwise). THE ROM'S SHORE spent
    cycles in the ROM's AES arm and aes_entry — the premise: the arrival takes that arm — and none in the blob's door.
    OURS entered its own AES arm and its own aes_entry, and spent NOT ONE CYCLE in the ROM's AES arm, aes_entry,
    marshal or opcode switch — unless `others_trap`: another process's own trap falls inside the trip (the ROM's on
    both shores: the vector is not bound), and then fewer than the ROM's shore by at least the arm's own."""
    our_door_s = our_door(ours.blob)
    in_the_rom_s_arm = cycles_in(the_rom_s, ROM_DOOR, THE_AES_ARM, AES_ENTRY)
    assert in_the_rom_s_arm, "the ROM's trip spent no cycle in the ROM's AES arm: the arrival does not take it"
    assert not sum(the_rom_s.stopped.profile[span] for span in our_door_s.values()), "the ROM's trip ran the blob's door"
    for part in (THE_AES_ARM, AES_ENTRY):
        assert cycles_in(ours, our_door_s, part), f"our trip never entered our own door's part `{part}`"
    in_the_rom_s = cycles_in(ours, ROM_DOOR, *AN_AES_CALL_S)
    if not others_trap:
        assert in_the_rom_s == 0, f"our trip spent {in_the_rom_s} cycles in the ROM's door"
        return
    most = cycles_in(the_rom_s, ROM_DOOR, *AN_AES_CALL_S) - in_the_rom_s_arm
    assert 0 < in_the_rom_s <= most, (
        f"our trip spent {in_the_rom_s} cycles in the ROM's door where another process's trap accounts for at most {most}")


# ---- WHAT TWO TRIPS DIFFER IN, BY NATURE --------------------------------------------------------------------------------------
# Each class is a function of the two trips' machines answering the byte addresses it covers — read off the machine's
# own pointers, never an address a capture or a layout decides.
def uda_of(ram, pd):
    return case.long_in(ram, pd + aes.PD_UDA) & BUS


def the_blob_s_span(_rom, ours):
    """The blob's own span: its text and data as laid, and the storage it allocates behind them."""
    return range(ours.ours.base, ours.ours.end)


def its_dead_stack(rom, _ours):
    """The trapping process's UDA stack BELOW the stack pointer the way out stored for its next trap: two builds'
    frames, dead on both shores once the call is over."""
    uda = uda_of(rom.stopped.ram, rom.arrival.process)
    return range(uda + aes.UDA_STATE_BYTES, case.long_in(rom.stopped.ram, uda + aes.UDA_SUPER_SP) & BUS)


def its_saved_context(rom, _ours):
    """The trapping process's saved registers in its UDA (D0..A5): what the dispatcher parked at its last switch —
    aes_entry's dsptch, where the ROM's context holds the Line-F handler's A0, D1 and D2 and Alcyon's leavings, and
    ours a `jsr`'s and GCC's. Dead once the call is over: the way out reloads D1-A6 from the user stack."""
    uda = uda_of(rom.stopped.ram, rom.arrival.process)
    return range(uda + aes.UDA_REGS, uda + aes.UDA_A6)


def the_dispatcher_s_stack(_rom, _ours):
    """The dispatcher's own stack: dead between two switches, and two builds' frames below its top."""
    return range(aes.header_constants("evdisp.h")["AES_DISPATCHER_STACK_BOTTOM"], aes.AES_DISPATCHER_STACK_TOP)


D0_S_HIGH_WORD = "D0's high word at the trap's exit"


def differing(rom, ours, classes=(), d0_high_differs=False, mapped=()):
    """WHAT THE TWO TRIPS DIFFER IN where they end, outside `classes`: a list of findings, empty where they agree —
    each register by name (D0's HIGH WORD apart where the case declares `d0_high_differs`: THE DECLARED DIVERGENCE,
    `D0_S_HIGH_WORD`), the megabyte by its first differing addresses, the off-image streams. `mapped`: the longwords
    of the megabyte that hold A SITE OF THE DOOR on each shore, compared exactly through `mapped_back` — each must
    NEED the mapping. A class named and not needed (no byte of it differs), a mapping not needed, or the declaration
    where D0 is equal, is a finding too."""
    found, blob = [], ours.blob
    our_ram = bytearray(ours.stopped.ram)
    for slot in mapped:
        held = case.long_in(our_ram, slot)
        if mapped_back(blob, held) == held:
            found.append(f"the longword at {slot:#x} is declared to hold a site of the door and holds {held:#x}: nothing to map")
        our_ram[slot:slot + LONG_BYTES] = struct.pack(">I", mapped_back(blob, held))
    for name in aes_boot.REGISTER_NAMES:
        its, mine = rom.stopped.registers[name], mapped_back(blob, ours.stopped.registers[name])
        if name == "d0" and d0_high_differs:
            if its >> HIGH_WORD == mine >> HIGH_WORD:
                found.append(f"{D0_S_HIGH_WORD} is declared to differ and is {its >> HIGH_WORD:#x} on both shores")
            its, mine = its & WORD_MASK, mine & WORD_MASK
        if its != mine:
            found.append(f"{name}: the ROM's {its:#x}, ours {mine:#x}")
    left_out = set()
    for located in classes:
        covered = set(located(rom, ours))
        if located is not the_blob_s_span and not any(rom.stopped.ram[at] != our_ram[at] for at in covered):
            found.append(f"the class `{located.__name__}` is named and no byte of it differs: not needed")
        left_out |= covered
    apart = [at for at in range(RAM_BYTES) if rom.stopped.ram[at] != our_ram[at] and at not in left_out]
    if apart:
        found.append(f"{len(apart)} byte(s) of the megabyte differ outside the classes named, from {apart[0]:#x}: "
                     f"{[hex(at) for at in apart[:16]]}")
    for what, its, mine in zip(("declared I/O reads", "modelled hardware reads", "off-image stores"),
                               rom.stopped.streams, ours.stopped.streams):
        if its != mine:
            found.append(f"the {what} differ: the ROM's run made {len(its)}, ours {len(mine)}")
    return found


# ---- THE MACHINES THIS BATTERY ARRIVES ON --------------------------------------------------------------------------------------
QUIET_PAIR = (aes_boot.QUIET, aes_boot.QUIET)
FINDING_PAIR = (aes_boot.FIND | aes_boot.WRITE, aes_boot.QUIET)
FIRST_ACCESSORY, SECOND_ACCESSORY = (padded(name) for name in aes_boot.ACCESSORY_NAMES[:2])


@functools.cache
def accessory_trap(modes, name, nth=0):
    """The `nth` AES trap of the accessory `name` on the accessory boot whose two accessories run in `modes`."""
    return at_the_trap(aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(*modes), name, nth)


@functools.cache
def desk_s_first_vdi_trap():
    """The desk boot's first `trap #2`: the desk's own, for the VDI."""
    return at_the_trap(aes_boot.preinit(), aes_boot.blank_disk(), DESK_NAME, 0, SELECTOR_VDI)


# ---- ub_trampoline: A LABELLED ARGUMENT CLASS, and the desk's draw code not run ------------------------------------------------
# No boot reaches it (a desk window with icons draws through it: a hand's double-click), and what it calls is the
# desk's own draw code, band 6's — the ROM's `$fde844` on the ROM's shore, and on a blob (since band 6 slice F3, N18)
# the thunk into our C, `USERDEF_THUNK`: each shore's run is stopped at ITS callee's first instruction (the
# door), so neither callee runs. So its case is a CALL STAGED over a machine the ROM booted — the desk's, whose
# start-up allocated the 1 KB stack the trampoline moves to (AES_USERDEF_STACK holds its real top) — entered with a
# whole register file, and held at TWO PLACES: where it enters the desk's routine (the stack it stands on, the
# PARMBLK handed, the caller's stack pointer parked), and where it returns to its caller once that routine has
# returned — which it is MADE to do at its own first instruction (the oracle's callback return: D0 an answer, the
# return address popped), the same on both shores.
UbCall = namedtuple("UbCall", "at_the_call registers_at_the_call sp_at_the_call returned registers d0")
UbCall.__doc__ = """ub_trampoline run round a desk routine that returns at once: the megabyte and the registers
`at_the_call` of the desk's routine and the stack pointer there; the megabyte where the trampoline `returned`, the
registers it left and D0."""
UB_INSNS = 64                           # the trampoline is seven instructions
A_PARMBLK, A_DRAW_ANSWER = 0x0001_2340, 0x0000_5a5a     # an address and a draw code's answer, no machine's own


def through_ub_trampoline(ram, registers, blob=None):
    """ub_trampoline(A_PARMBLK) over the megabyte `ram`, entered with `registers` (`emu.REPORTED_REGS`) on the
    harness's stack — the ROM's, or `blob`'s (the blob laid): a `UbCall`."""
    memory, entry, callee = _image_of(ram), UB_TRAMPOLINE, addrs.AES_ROM_DESK_USERDEF
    if blob is not None:
        ours = aes_boot.ours_of(blob)
        aes_boot._vet_clear_where_the_blob_goes(memory, ours)
        memory[ours.base:ours.base + len(ours.image)] = ours.image
        entry, callee = blob.entry(UB_SYMBOL), blob.entry(USERDEF_THUNK)
    emu.install_chip_seeds()
    result = emu.run_bench(memory, entry, A_PARMBLK, emu.STACK_TOP, emu.SENTINEL, max_insns=UB_INSNS,
                           door=frozenset({callee}), seed_regs=rom_bench.entry_registers(registers))
    try:
        assert (result["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, callee), (
            "ub_trampoline never entered the desk's draw code")
        sp = emu.bench_door_sp()
        at_the_call, registers_there = bytes(memory[:RAM_BYTES]), aes_boot.registers_at_the_stop(emu.REPORTED_REGS)
        emu.bench_door_return(A_DRAW_ANSWER, case.long_in(memory, sp), sp + LONG_BYTES)
        emu.bench_door_arm(None)
        result = emu.bench_resume(entry, max_insns=UB_INSNS)
        assert result["status"] == emu.BENCH_SENTINEL, "ub_trampoline did not return to its caller"
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("ub_trampoline round a desk routine that returns at once")
    return UbCall(at_the_call, registers_there, sp, bytes(memory[:RAM_BYTES]), result["regs"], result["d0"])
