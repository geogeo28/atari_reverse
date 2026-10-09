r"""THE MACHINES THE ROM'S OWN GEM START-UP MAKES — the pre-init machine, and what `gem_main` boots out of it
(`test_aes_boot.py`).

Every machine before this one was the post-boot snapshot (`tools/boot_snapshot.py`) or a state the ROM's routines were
driven to from it. Band 5's subject is what that snapshot lies AFTER — the AES's own init, the accessory loader, the
shell — so it needs two more, and both are made the same way the principle asks: a ROM run, never a poke.

  * THE PRE-INIT MACHINE (`preinit()`): Hatari stopped at `gem_entry`, before any instruction of GEM
    (`tools/preinit_snapshot.py`, `make preinit`) — RAM, registers, the shifter's palette and resolution.
  * A BOOTED MACHINE (`desk_machine()`, `accessory_machine()`): the ROM's OWN `gem_entry` run in the oracle FROM the
    pre-init machine — entered with the capture's whole register file, in user mode, on the capture's stacks — TO THE
    DESKTOP'S FIRST IDLE: the first arrival at the dispatcher's idle poll with no process ready, none woken and no
    fork queued (`aes_switch.waits_for_an_interrupt`'s three words). Every instruction between the two is the ROM's:
    GEMDOS, the BIOS, the XBIOS, the VDI, Line-A and Line-F are the image's own code, entered through the image's
    own vectors. NOT ONE BYTE OF THE MACHINE IS POKED — no vector, no stub, no staged record.

WHAT THE ORACLE MUST SERVE for that run, MEASURED (a boot that meets anything else is refused by name —
`rom_bench.vet_the_run_just_made`, and the device model's own refusals below):

  1. THE FLOPPY, AT THE DRIVER'S THREE ENTRIES. GEMDOS reaches a disk through `hdv_bpb`, `hdv_mediach` and `hdv_rw`,
     which on this machine name the ROM's floppy driver; below those entries is the FDC and its DMA — transactions,
     which `TRAP_MODEL.md` puts out of the model's reach. So the run is STOPPED at the three addresses the machine's
     own vectors hold and the call is answered there (`Floppy`): `Rwabs` copies sectors between the caller's buffer
     and a 720 KB image held OFF the machine, and `Mediach` says UNCHANGED — always.
     THE DISK SERVED IS THE DISK THE CAPTURE BOOTED WITH, and that is held, not assumed: the driver's own record for
     drive A: must hold the BPB of the image's boot sector AND ITS SERIAL, or the boot is refused. So GEMDOS's cache
     of the FAT and the root, the driver's record and its boot-sector buffer are the ones the REAL driver left
     before `gem_entry`; nothing is swapped in, and `Getbpb` — which the ROM would answer by reading the boot
     sector again and rewriting all of that — is never asked (a boot that asks is refused by name). The desk's
     machine boots from the capture made with the blank disk, the accessories' from the capture made with THEIR
     disk in the drive from power-on (`preinit_snapshot.accessory_path`); a mode is a word inside an accessory's own
     cluster, which nothing reads before `gem_entry` (`tools/accessory_disk.py`).
     WHY NOT A RAM DISK IN THE FREE WINDOW, as the file system's batteries stage one: `Pexec` hands a program the
     LARGEST free block and CLEARS it, and at the accessory loader's `Pexec(3)` that block is all of free memory —
     the staged disk and its stub routines with it (measured: the loader's first read after the clear ran off
     through the wiped window). `fs_pexec.pool` goes round that by re-cutting GEMDOS's pool with pokes; a device
     held off the machine needs none.
     WHAT THE MODEL DOES NOT DO: advance the driver's PRIVATE state (its drive-select and motor timers, the
     scratch its sector transfers leave). A boot asks the driver nothing but Mediach and Rwabs.
  2. THE BLITTER PROBE'S BUS ERROR. The desktop asks XBIOS `Blitmode(-1)`, whose probe (`$fc0f1a`) points the
     bus-error vector at its own tail and touches `$ffff8a00`: on an ST there is no blitter and the access FAULTS.
     The oracle's CPU takes no bus error, and the read is of an I/O byte no model serves — which refuses the run.
     So the run is stopped AT that one instruction and the exception is taken there as a 68000 takes it
     (`_bus_error`): the fourteen-byte group-0 frame pushed on the supervisor stack, the PC loaded from vector 2 as
     the machine holds it at that instant, no register but SP and PC touched. WHAT THAT BUYS IS THE MACHINE'S OWN
     PATH THROUGH THE PROBE — the instructions run, the stack the frame is pushed on — and NOT the probe's answer:
     this call discards it (measured: the booted machine is the same with D0 forced to "a blitter"). The frame is
     read back out of the machine where the probe's tail is entered (`Boot.bus_error_frame`); it is dead from
     there on, and the desk's later calls write over it.
  3. THE SHIFTER, by declaration (`io_seed`): the sixteen palette words (`vq_color` over every pen as the
     workstation opens) and the resolution byte (`Getrez`, twice), each AS THE CAPTURE READ IT OUT OF HATARI at the
     stop — the pre-init machine carries them for this.
  4. THE KEYBOARD ACIA'S STATUS, by the kit's own model (transmitter empty): seven polls, one before each of the
     seven bytes the mouse set-up sends the IKBD — `$08`, `$0b 1 1`, `$10`, `$07 0`: relative mouse, threshold 1/1,
     Y's origin at the top, button action 0 (`Boot.hardware_writes`; dropped, as every off-image store is).
  5. THE HORIZONTAL BLANK, THE ONE INTERRUPT THE RUN TAKES. `gem_main`'s `sti` drops the interrupt mask to 0, and
     on the machine a level-2 interrupt is then never more than a scan line away: the
     ROM's own handler (`$fc06c8`) raises the INTERRUPTED context's mask to 3 and the machine runs at 3 ever after —
     which is why every status word the AES saves on a real machine reads `$23xx`. So one horizontal blank is held
     PENDING for the whole run (`m68k_set_irq`), the CPU takes it through the image's own vector the moment the mask
     allows, the ROM's handler runs, and the next is made pending where that one was taken (MEASURED: every boot
     here takes exactly one, at `sti`'s own `rts`). A scan line's delay is not modelled: the interrupt arrives at
     the first instruction boundary the mask allows, which is one of the phases a machine has.
  NO OTHER INTERRUPT IS DELIVERED AND NONE IS NEEDED: nothing between `gem_entry` and the first idle waits on a
  clock. The booted machine's clocks are therefore the pre-init machine's — NO TIME HAS PASSED in it (on a machine
  the same instructions take about a second: some sixty vertical blanks, two hundred ticks).

HELD TO THE MACHINE, in the suite and beside it. In the suite: the desk's machine is the post-boot snapshot's own
boot — its vectors, its whole TPA, both processes' saved contexts, its screen (`test_aes_boot.py`). BESIDE IT, AND
NOT RUN BY THE SUITE: `python tools/preinit_snapshot.py --cross-check` boots the accessory disk in Hatari to the
desktop and prints, region by region, what the accessory machine and that real boot differ in outside the two
masks (fifteen seconds of emulation; the measured table is in the tool's own docstring).

THE TEST ACCESSORY (`test/acc/testacc.S`, built by `tools/accessory_disk.py` with the toolchain the measurement
programs are built with) is a real GEM accessory: `appl_init`, then an event wait for ever. What it does beside is a
WORD OF ITS TEXT, patched in the disk image (`QUIET`, or any of `FIND | WRITE | MULTI`): no rebuild, and the same
disk to the machine.

EVERYTHING HERE IS A KEPT DERIVATION (`derived.kept`): no line of the reconstruction runs. A derivation is keyed by
the pre-init machine's CONTENT (an argument, not a file of the tree: neither capture is in any tree key), so a
fresh capture is another question and the old answer is never served for it.
"""
import ctypes
import functools
import struct
from collections import namedtuple

import derived
from harness import BASE_IMAGE, addrs, emu
from recreate_kit import rom_bench

import accessory_disk
import preinit_snapshot
import st_build

import aes
import aes_switch
import case
import fs_pexec

RAM_BYTES = addrs.ST_RAM_BYTES
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes.OS_BUS_ADDR_MASK
LONG_MASK = aes.LONG_MASK

# ---- THE CPU, WHERE A RUN STANDS STOPPED ------------------------------------------------------------------------------
# The kit's door can set D0, PC and SP at a stop and wrecks the scratch registers as a C call does
# (`emu.bench_door_return`): right for a callback, wrong for both things done here — entering a machine with its WHOLE
# register file and its status register, and taking an exception that touches no data register. Musashi's own
# accessors are exported by the oracle's library and are what the kit's door is written with; they are read here,
# the kit's files untouched. (Named for the orchestrator: `emu` could offer this pair.)
M68K_REGISTER = {**{f"d{n}": n for n in range(8)}, **{f"a{n}": 8 + n for n in range(8)},
                 "pc": 16, "sr": 17, "usp": 19, "isp": 20}          # m68k.h's `m68k_register_t`
_CPU = emu._LIB
_CPU.m68k_set_reg.argtypes, _CPU.m68k_set_reg.restype = (ctypes.c_int, ctypes.c_uint), None
_CPU.m68k_get_reg.argtypes, _CPU.m68k_get_reg.restype = (ctypes.c_void_p, ctypes.c_int), ctypes.c_uint
_CPU.m68k_set_irq.argtypes, _CPU.m68k_set_irq.restype = (ctypes.c_uint,), None
HBL_LEVEL, NO_INTERRUPT = 2, 0          # the horizontal blank's priority; the line let go
REGISTER_NAMES = preinit_snapshot.REGISTER_NAMES
SR_SUPERVISOR = preinit_snapshot.SR_SUPERVISOR
SR_TRACE = 0x8000


def _register(name):
    return _CPU.m68k_get_reg(None, M68K_REGISTER[name])


def _set_register(name, value):
    _CPU.m68k_set_reg(M68K_REGISTER[name], value & LONG_MASK)


def _enter(registers):
    """The stopped CPU given the whole register file of `registers`. THE STATUS REGISTER FIRST: it says which stack
    pointer A7 is, and each of the two is then set by its own name."""
    _set_register("sr", registers["sr"])
    for name in REGISTER_NAMES:
        if name != "sr":
            _set_register(name, registers[name])


def _registers_now():
    return {name: _register(name) for name in REGISTER_NAMES}


# ---- THE ROM ADDRESSES OF THE DEVICE MODEL ------------------------------------------------------------------------------
# Held to the ROM's own bytes by `test_aes_boot.py` (the instruction at each, the constant it carries).
GEM_ENTRY = addrs.AES_ROM_GEM_ENTRY
IDLE_LOOP, IDLE_POLLED = addrs.AES_ROM_IDLE_LOOP, addrs.AES_ROM_IDLE_POLLED
BLITTER_PROBE = 0xfc0f1a                # XBIOS Blitmode's probe: vector 2 pointed at its own tail, the touch, `moveq #2`
BLITTER_PROBE_TOUCH = 0xfc0f34          # `tst.w $8a00(a0)`, A0 = 0: the access that faults where there is no blitter
BLITTER_PROBE_TOUCH_WORDS = (0x4a68, 0x8a00)
BLITTER_PROBE_FAULTED = 0xfc0f3a        # ...and where the probe points the vector: its own tail, D0 still 0
BLITTER_REGISTERS = 0xffff8a00          # the address the access drives, as the 68000 forms it (A0 + a signed d16)
FLOPPY_GETBPB_RECORD_LOAD = 0xfc0fea    # the driver's `adda.l #<its BPB records>,a5`, the drive number * 32 in A5
FLOPPY_BPB_RECORD_BYTES = 32            # ($fc0fe4 `asl.w #5`)
ADDA_L_IMMEDIATE_A5 = 0xdbfc
VECTOR_BUS_ERROR = 0x008
DRIVE_A = 0
FIRST_ACCESSORY_BASEPAGE = 0x9724       # long: where sndcli parks the FIRST accessory's basepage ($fe435a)
SNDCLI, SNDCLI_END = 0xfe42e8, 0xfe4394
GEM_MAIN_EVB_COUNT_AT = 0xfda0ce        # gem_main's `cmp.w #15,d7`: the EVBs it links at start-up
ACCESSORY_EVB_COUNT_AT = 0xfe455c       # the accessory allocator's `cmp.w #5,d7`: the EVBs each allocated PD brings
CMP_W_IMMEDIATE_D7 = 0xbe7c
ACCESSORY_SLOTS = 6                     # `$c6b2[]`'s longwords: the loader takes six accessories at most
ACCESSORY_BLOCK_ASKED_AT = 0xfe44dc     # the allocator's `move.l #2226,(sp)` before dos_alloc
MOVE_L_IMMEDIATE_TO_STACK = 0x2ebc
ACCESSORY_BLOCK_BYTES = 2226            # an allocated accessory's PD, UDA, CDA and five EVBs
ACCESSORY_UDA_BYTES = 1866              # ...its UDA: from the PD's end to the CDA ($fe4508 `lea 2050(a3)`)
BASEPAGE_BYTES = 0x100

# ---- THE BUS ERROR A 68000 TAKES --------------------------------------------------------------------------------------
# Group 0: (special status, access address, instruction register, SR, PC), fourteen bytes, pushed on the supervisor
# stack. The status word's low five bits are R/W, I/N and the function code; its upper eleven are, on a 68000, the
# instruction register's (the manual leaves them undefined) — Hatari's own choice for them is not consulted, and the
# probe reads none of the frame: it reloads SP from A2. The PC stacked is the instruction's own advanced past its
# extension word (the 68000 has prefetched it when the data access faults).
_BUS_ERROR_FRAME = struct.Struct(">HIHHI")
BUS_ERROR_FRAME_BYTES = _BUS_ERROR_FRAME.size
STATUS_READ, STATUS_SUPERVISOR_DATA = 0x10, 0x5
STATUS_FROM_THE_INSTRUCTION = 0xffe0


class Refused(RuntimeError):
    """The boot met something the device model does not serve: said by name, never answered by a guess."""


def _bus_error(memory, access):
    """THE STOPPED CPU TAKES A BUS ERROR at the data access of the instruction it stands at: the frame pushed, SP
    lowered, the trace bit cleared, the PC loaded from the vector the machine holds. Answers the frame's bytes by
    address (the harness's store: the CPU would have made it)."""
    status, pc, sp = _register("sr"), _register("pc"), _register("a7")
    if not status & SR_SUPERVISOR:
        raise Refused(f"a bus error at {pc:#x} taken in user mode: the model pushes on the stack the CPU stands on")
    opcode, extension = case.word_in(memory, pc), WORD_BYTES
    frame = _BUS_ERROR_FRAME.pack(opcode & STATUS_FROM_THE_INSTRUCTION | STATUS_READ | STATUS_SUPERVISOR_DATA,
                                  access & LONG_MASK, opcode, status, pc + WORD_BYTES + extension)
    sp -= BUS_ERROR_FRAME_BYTES
    memory[sp:sp + BUS_ERROR_FRAME_BYTES] = frame
    _set_register("a7", sp)
    _set_register("sr", status & ~SR_TRACE)
    _set_register("pc", case.long_in(memory, VECTOR_BUS_ERROR) & BUS)
    return {sp: frame}


# ---- THE FLOPPY, AT THE DRIVER'S THREE ENTRIES ---------------------------------------------------------------------------
# Each call as the BIOS dispatcher's `jsr` leaves it: the return address at (sp), the function's arguments above it.
GETBPB, MEDIACH, RWABS = "Getbpb", "Mediach", "Rwabs"
DEVICE_AT = 4                           # Getbpb's and Mediach's one argument
RWABS_FLAG_AT, RWABS_BUFFER_AT, RWABS_COUNT_AT, RWABS_RECORD_AT, RWABS_DEVICE_AT = 4, 6, 10, 12, 14
RWABS_WRITE = 1
# The nine words of a BPB, from a boot sector (little-endian, `st_build`'s offsets): what the ROM's Getbpb computed
# when it logged the disk in, and what its record for the drive must hold for the disk served to be that disk.
BOOT_SECTOR_BPB = struct.Struct("<HBHBHHBHH")       # bytes/sector, sectors/cluster, reserved, FATs, root entries,
BPB_WORDS = struct.Struct(">9H")                    # sectors, media, sectors/FAT, sectors/track
FAT12_FLAGS = 0
FLOPPY_RECORD_SERIAL = 28               # the driver's record: the boot sector's three serial bytes ($fc1130)
FLOPPY_BOOT_SECTOR_BUFFER_LOAD = 0xfc112a           # ...copied out of its boot-sector buffer: `adda.l #<buffer>,a1`
ADDA_L_IMMEDIATE_A1 = 0xd3fc

Call = namedtuple("Call", "function arguments answer")


def bpb_of(boot_sector):
    """The BPB the ROM's Getbpb makes of a floppy's boot sector: recsiz, clsiz, clsizb, rdlen, fsiz, fatrec (the
    SECOND FAT's first record: TOS's convention), datrec, numcl, bflags."""
    (sector_bytes, cluster_sectors, reserved, _fats, root_entries, sectors, _media, fat_sectors,
     _track_sectors) = BOOT_SECTOR_BPB.unpack_from(boot_sector, st_build.BPB_AT)
    root_sectors = root_entries * st_build.DIR_ENTRY_BYTES // sector_bytes
    second_fat = reserved + fat_sectors
    data = second_fat + fat_sectors + root_sectors
    return BPB_WORDS.pack(sector_bytes, cluster_sectors, cluster_sectors * sector_bytes, root_sectors, fat_sectors,
                          second_fat, data, (sectors - data) // cluster_sectors, FAT12_FLAGS)


def _operand_of(memory, at, opcode, what):
    """The longword operand of the ROM instruction at `at`, which must be `opcode`."""
    found, operand = struct.unpack_from(">HI", memory, at)
    if found != opcode:
        raise Refused(f"the ROM's Getbpb does not load {what} at {at:#x}")
    return operand


def driver_record(memory):
    """Where the ROM's Getbpb keeps drive A:'s record — read out of its own instruction."""
    records = _operand_of(memory, FLOPPY_GETBPB_RECORD_LOAD, ADDA_L_IMMEDIATE_A5, "its records")
    return records + DRIVE_A * FLOPPY_BPB_RECORD_BYTES


def driver_boot_sector(memory):
    """...and the buffer it reads a boot sector into."""
    return _operand_of(memory, FLOPPY_BOOT_SECTOR_BUFFER_LOAD, ADDA_L_IMMEDIATE_A1, "its boot-sector buffer")


class Floppy:
    """Drive A: as the entries of the machine's own driver answer for it (the module's docstring): `disk` a 720 KB
    image held off the machine — THE DISK THE MACHINE BOOTED WITH, or the model is refused: the driver's record
    must hold its BPB and its serial. `calls`: every call made, in order."""

    def __init__(self, memory, disk):
        self._memory, self.disk, self.calls = memory, bytearray(disk), []
        vectors = {GETBPB: addrs.HDV_BPB, MEDIACH: addrs.HDV_MEDIACH, RWABS: addrs.HDV_RWABS}
        self.entries = {case.long_in(memory, vector) & BUS: function for function, vector in vectors.items()}
        outside = [f"{function} at {entry:#x}" for entry, function in self.entries.items() if entry < emu.ROM_BASE]
        if len(self.entries) != len(vectors) or outside:
            raise Refused(f"this machine's disk vectors do not name three routines of the ROM ({outside}): the model "
                          f"stands in for the ROM's floppy driver and for no other")
        self.record = driver_record(memory)
        self._vet_it_is_the_disk_the_machine_logged_in()

    def _vet_it_is_the_disk_the_machine_logged_in(self):
        held = bytes(self._memory[self.record:self.record + BPB_WORDS.size])
        serial_at = self.record + FLOPPY_RECORD_SERIAL
        serial = bytes(self._memory[serial_at:serial_at + st_build.BOOT_SERIAL_BYTES])
        if held != bpb_of(self.disk):
            raise Refused(f"the disk's boot sector says another geometry ({bpb_of(self.disk).hex()}) than the "
                          f"driver's record for drive A: holds ({held.hex()})")
        if serial != accessory_disk.serial_of(self.disk):
            raise Refused(f"the disk's serial ({accessory_disk.serial_of(self.disk).hex()}) is not the one the driver "
                          f"logged in ({serial.hex()}): this machine booted with another disk — GEMDOS's cache is that "
                          f"disk's, and the model swaps none in")

    def _word(self, at):
        return case.word_in(self._memory, at)

    def _drive_a(self, function, device):
        if device != DRIVE_A:
            raise Refused(f"{function} of drive {device}: the model holds drive A: alone")

    def served(self, entry, sp):
        """The call the run stands at the entry of, answered: `(D0, the return address)`."""
        answer = getattr(self, f"_{self.entries[entry].lower()}")(sp)
        return answer, case.long_in(self._memory, sp) & BUS

    def _getbpb(self, sp):
        raise Refused(f"Getbpb of drive {self._word(sp + DEVICE_AT)}: the ROM's would read the boot sector again and "
                      f"rewrite its record, its serial and its buffer, which the model does not do — and no boot "
                      f"over the disk the machine logged in asks")

    def _mediach(self, sp):
        self._drive_a(MEDIACH, self._word(sp + DEVICE_AT))
        self.calls.append(Call(MEDIACH, (DRIVE_A,), addrs.MEDIACH_UNCHANGED))
        return addrs.MEDIACH_UNCHANGED

    def _rwabs(self, sp):
        flag, count, record = (self._word(sp + at) for at in (RWABS_FLAG_AT, RWABS_COUNT_AT, RWABS_RECORD_AT))
        buffer = case.long_in(self._memory, sp + RWABS_BUFFER_AT) & BUS
        self._drive_a(RWABS, self._word(sp + RWABS_DEVICE_AT))
        at, size = record * st_build.SECTOR_BYTES, count * st_build.SECTOR_BYTES
        if at + size > len(self.disk) or buffer + size > RAM_BYTES:
            raise Refused(f"Rwabs of {count} sector(s) at record {record} to {buffer:#x} leaves the disk or the RAM")
        if flag & RWABS_WRITE:
            self.disk[at:at + size] = self._memory[buffer:buffer + size]
        else:
            self._memory[buffer:buffer + size] = self.disk[at:at + size]
        self.calls.append(Call(RWABS, (flag, buffer, count, record, DRIVE_A), 0))
        return 0


def _return_from_the_driver(answer, to, sp):
    """The driver's `rts`, its answer in D0. Every other register is left as the caller had it: what the ROM's
    driver would leave in its scratch registers is the driver's, which did not run."""
    _set_register("d0", answer)
    _set_register("pc", to)
    _set_register("a7", sp + LONG_BYTES)


# ---- THE BOOT -------------------------------------------------------------------------------------------------------------
# Where the bench door's two entry stores go (the sentinel, an argument): OFF THE MACHINE — past its RAM, below the
# I/O page and the ROM, where the oracle drops a store as the bus does. The run's stacks are the capture's.
OFF_THE_MACHINE = 0x200000
BOOT_INSNS = 4_000_000                  # measured: 718,522 with two quiet accessories, 592,893 with none
Boot = namedtuple("Boot", "ram registers disk instructions cycles polls blanks floppy io_reads hardware_reads "
                          "hardware_writes stored bus_error_frame writes_truncated")
Boot.__doc__ = """One boot of the ROM from a pre-init machine to the first idle: the megabyte of `ram` it left and the
CPU's `registers` there (REGISTER_NAMES; the PC is idle's poll), the `disk` as it left it, its cost, how many times
idle polled on the way (`polls`, the last the idle), how many horizontal blanks it took (`blanks`), every `floppy`
call (`Call`), the declared I/O reads `(address, width, value)`, the kit's modelled reads `(address, value)`, the
off-image stores `(address, width, value)`, the RAM it
`stored` to as `(start, length)` runs (the kit's write ledger and the harness's own stores: the sectors read, the bus
error's frame), `bus_error_frame` (`{address: bytes}`: the fourteen bytes at the supervisor stack pointer, READ OUT
OF THE MACHINE as the probe's tail is entered) and whether the ledger saturated."""


def io_seed_of(machine):
    """The declared I/O map of a pre-init machine: each byte of the shifter the capture read out of Hatari."""
    return {preinit_snapshot.IO_AT + offset: byte for offset, byte in enumerate(machine.io)}


def _runs(addresses):
    """Sorted addresses as `(start, length)` runs."""
    runs = []
    for at in addresses:
        if runs and at == runs[-1][0] + runs[-1][1]:
            runs[-1][1] += 1
        else:
            runs.append([at, 1])
    return tuple((start, length) for start, length in runs)


def _vet_the_probe(memory):
    words = struct.unpack_from(">2H", memory, BLITTER_PROBE_TOUCH)
    if words != BLITTER_PROBE_TOUCH_WORDS or case.long_in(memory, VECTOR_BUS_ERROR) & BUS != BLITTER_PROBE_FAULTED:
        raise Refused(f"the run stands at {BLITTER_PROBE_TOUCH:#x} and it is not the blitter probe's touch with the "
                      f"bus-error vector at its tail: no other access of this machine is known to fault")
    if _register("a0"):
        raise Refused("the blitter probe's touch with A0 not 0: it would not reach the blitter's registers")


def _the_frame_the_handler_is_entered_over(memory):
    """The CPU stands at the probe's tail, the exception taken: the fourteen bytes at ITS stack pointer, read out of
    the machine — what the 68000 pushed, wherever the model put it."""
    pc, sp = _register("pc"), _register("a7")
    if pc != BLITTER_PROBE_FAULTED:
        raise Refused(f"the bus error entered {pc:#x}, not the probe's tail")
    return {sp: bytes(memory[sp:sp + BUS_ERROR_FRAME_BYTES])}


def _run_to_the_first_idle(memory, machine, floppy, budget):
    """The run itself: the door at the pre-init PC (so it stops before one instruction), the capture's register file
    laid and a horizontal blank made pending, then each stop served — a driver entry, the probe's touch, the blank's
    handler entered, idle's poll — to the idle. Answers the last segment's result, what the harness stored into the
    machine on the way (`{address: bytes}`), the bus error's frame as the machine holds it where the probe's tail is
    entered, the polls made and the blanks taken."""
    hbl = case.long_in(memory, addrs.VECTOR_HBL) & BUS
    stops = frozenset(floppy.entries) | {BLITTER_PROBE_TOUCH, IDLE_LOOP, IDLE_POLLED, hbl}
    laid, pushed, frame, polls, blanks = {}, {}, {}, 0, 0
    emu.install_chip_seeds()
    result = emu.run_bench(memory, machine.registers["pc"], 0, OFF_THE_MACHINE, emu.SENTINEL, max_insns=budget,
                           door={machine.registers["pc"]}, seed_regs=None, io_seed=io_seed_of(machine))
    assert result["status"] == emu.BENCH_DOOR and not result["ninsns"], "the boot ran before its registers were laid"
    _enter(machine.registers)
    _CPU.m68k_set_irq(HBL_LEVEL)
    while True:
        emu.bench_door_arm(stops - {_register("pc")})
        left = budget - result["ninsns"]
        if left <= 0:
            raise Refused(f"the boot did not reach an idle within {budget} instructions")
        result = emu.bench_resume(GEM_ENTRY, max_insns=left)
        if result["status"] != emu.BENCH_DOOR:
            raise Refused(f"the boot left the machine: it ended with status {result['status']} at "
                          f"{emu.bench_resume_pc():#x}")
        pc, sp = emu.bench_door_pc(), emu.bench_door_sp()
        if pc in floppy.entries:
            before = len(floppy.calls)
            answer, to = floppy.served(pc, sp)
            _return_from_the_driver(answer, to, sp)
            call, = floppy.calls[before:]
            if call.function == RWABS and not call.arguments[0] & RWABS_WRITE:
                _flag, buffer, count, _record, _device = call.arguments
                laid[buffer] = bytes(memory[buffer:buffer + count * st_build.SECTOR_BYTES])
        elif pc == hbl:
            blanks += 1                 # ...taken: the CPU let the line go, and the next one is pending from here
            _CPU.m68k_set_irq(HBL_LEVEL)
        elif pc == BLITTER_PROBE_TOUCH:
            _vet_the_probe(memory)
            pushed = _bus_error(memory, BLITTER_REGISTERS)
            frame = _the_frame_the_handler_is_entered_over(memory)
        elif pc == IDLE_LOOP:
            polls += 1
            if aes_switch.waits_for_an_interrupt(memory):
                return result, {**laid, **pushed}, frame, polls, blanks


@derived.kept
def booted(machine, disk, budget=BOOT_INSNS):
    """THE ROM'S OWN BOOT (the module's docstring) from the pre-init `machine` (`preinit_snapshot.PreInit`) with
    `disk` — the one it booted with — in drive A:, to the first idle: a `Boot`."""
    memory = bytearray(BASE_IMAGE)                  # ...for the ROM in it: the megabyte below is the pre-init machine's
    memory[:RAM_BYTES] = machine.ram
    floppy = Floppy(memory, disk)
    try:
        result, laid, frame, polls, blanks = _run_to_the_first_idle(memory, machine, floppy, budget)
        registers = _registers_now()
        writes, truncated = emu.bench_writes(memory)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
    finally:
        _CPU.m68k_set_irq(NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("the ROM's boot from the pre-init machine")
    stored = set(at for at in writes if at < RAM_BYTES)
    for at, data in laid.items():
        stored.update(range(at, at + len(data)))
    return Boot(bytes(memory[:RAM_BYTES]), registers, bytes(floppy.disk), result["ninsns"], result["cycles"], polls, blanks,
                tuple(floppy.calls), *streams, _runs(sorted(stored)), frame, truncated)


# ---- THE TEST ACCESSORY (`tools/accessory_disk.py` builds it and its disk) ---------------------------------------------------
PRG_HEADER_BYTES = fs_pexec.PRG_HEADER_BYTES
PRG_TEXT_BYTES_AT = 2                   # the header's four lengths: TEXT, DATA, BSS, symbols
NOT_CALLED = 0xfffe                     # what testacc.S's `res_find` and `res_write` hold until the call is made
QUIET, FIND, WRITE, MULTI = accessory_disk.QUIET, accessory_disk.FIND, accessory_disk.WRITE, accessory_disk.MULTI
ACCESSORY_NAMES = accessory_disk.NAMES
RESULT_WORDS = ("res_id", "res_find", "res_write", "res_events", "res_wakes")
_built = derived.kept(accessory_disk.build)         # the three texts are the question: none is a file of the tree's key


@functools.cache
def accessory():
    """The test accessory, built (once per source text: kept; once per process: read): an `accessory_disk.Accessory`."""
    return _built(accessory_disk.SOURCE.read_text(), accessory_disk.LINK.read_text(), accessory_disk.WRAPPER.read_text())


def lengths_of(file):
    """A GEMDOS program's `(TEXT, DATA, BSS, symbols)` lengths, off its header."""
    return struct.unpack_from(">4I", file, PRG_TEXT_BYTES_AT)


def fixups_of(file):
    """The offsets, from TEXT, of the longwords a GEMDOS program's relocation table names."""
    text, data, _bss, symbols = lengths_of(file)
    at = PRG_HEADER_BYTES + text + data + symbols
    first, = struct.unpack_from(">I", file, at)
    if not first:
        return ()
    offsets = [first]
    cursor = first
    for step in file[at + LONG_BYTES:]:
        if step == fs_pexec.PRG_END:
            break
        cursor += fs_pexec.PRG_SKIP_DISTANCE if step == fs_pexec.PRG_SKIP else step
        if step != fs_pexec.PRG_SKIP:
            offsets.append(cursor)
    return tuple(offsets)


@functools.cache
def accessory_disk_of(*modes):
    """The disk with one test accessory per mode (`accessory_disk.disk_of`): one disk to the machine whatever the
    modes — its boot sector, FATs and root are the capture's."""
    return accessory_disk.disk_of(accessory(), modes)


# ---- A MACHINE, AND WHAT IT IS READ BY -------------------------------------------------------------------------------------
Process = namedtuple("Process", "pd name pid waiting evwait uda cda basepage events")
Process.__doc__ = """One process of a machine, read off its PD: its address, name, id, whether it waits and for which
event bits, its UDA, CDA and basepage (0 for a process no program was loaded for), and the EVBs on its list."""
EVB_CAP = 64                            # more EVBs on one list than any machine here supplies: a list that does not end


class Machine:
    """A machine a `Boot` left: its megabyte (`ram`), the CPU's `registers` at the idle, the `boot` it came by — and
    its processes, read through its OWN pointers (never an address a capture decides).

    HOW A ROW RUNS OVER IT: `pokes` is the machine as the pokes every battery stages a case from (`{0: ram}` —
    `harness.make_image(machine.pokes)`, `case.merge_pokes(machine.pokes, <the case's own>)`, the `machine` argument
    of `aes.staged` and of the scheduler's driver); `image()` the sixteen megabytes, the ROM in place."""

    def __init__(self, boot):
        self.boot, self.ram, self.registers = boot, boot.ram, boot.registers
        self.pokes = {0: boot.ram}

    def image(self):
        memory = bytearray(BASE_IMAGE)
        memory[:RAM_BYTES] = self.ram
        return memory

    def long(self, at):
        return case.long_in(self.ram, at)

    def word(self, at):
        return case.word_in(self.ram, at)

    def process(self, pd):
        events = aes.list_of(self.ram, pd + aes.PD_EVLIST, link=aes.EVB_NEXT, limit=EVB_CAP)
        return Process(pd, bytes(self.ram[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES]),
                       self.word(pd + aes.PD_PID), self.word(pd + aes.PD_STAT) == aes.PD_STAT_WAITING,
                       self.word(pd + aes.PD_EVWAIT), self.long(pd + aes.PD_UDA) & BUS, self.long(pd + aes.PD_CDA) & BUS,
                       self.long(pd + aes.PD_LDADDR) & BUS, tuple(events))

    def static_processes(self):
        """The three PDs of the AES's own table, used or not."""
        return tuple(self.process(aes.AES_PD_TABLE + index * aes.PD_BYTES) for index in range(aes.AES_PD_COUNT))

    def allocated_accessories(self):
        """The accessories whose PD the loader ALLOCATED (`$c6b2[]`, `$c682` of them): every one but the first."""
        count = self.word(aes.AES_ACCESSORY_COUNT)
        return tuple(self.process(self.long(aes.AES_ACCESSORY_PDS + index * LONG_BYTES) & BUS)
                     for index in range(count))

    def static_uda_bytes(self):
        """How long each static process's UDA is: to the next one's, the last to the PD table (they are laid end to
        end, the table after them — `gem_entry`'s and `gem_main`'s own arithmetic)."""
        starts = [process.uda for process in self.static_processes()] + [aes.AES_PD_TABLE]
        return tuple(after - at for at, after in zip(starts, starts[1:]))

    def waiting(self):
        """The processes on the not-ready list, in its order."""
        return tuple(self.process(pd) for pd in aes.list_of(self.ram, aes.AES_NRL, limit=EVB_CAP))

    def named(self, name):
        """The process of that name (blank-padded to a PD's eight), among those that wait."""
        padded = name.encode().ljust(aes.PD_NAME_BYTES)
        found, = [process for process in self.waiting() if process.name == padded]
        return found

    def free_events(self):
        """The free EVBs, in the list's order."""
        return tuple(aes.list_of(self.ram, aes.AES_EUL, link=aes.EVB_NEXT, limit=EVB_CAP))

    def accessory_word(self, process, symbol):
        """A word of a test accessory's own memory — `symbol` of its build — off the TEXT base its basepage names."""
        text = self.long(process.basepage + addrs.BASEPAGE_TBASE)
        return self.word(text + accessory().symbols[symbol])

    def results(self, process):
        """What a test accessory's process kept of the AES's answers: `{RESULT_WORDS: word}`."""
        return {name: self.accessory_word(process, name) for name in RESULT_WORDS}


@functools.cache
def preinit():
    """The pre-init machine of this tree (`build/preinit.bin`; `make preinit`): booted with the blank disk."""
    return preinit_snapshot.load()


@functools.cache
def accessory_preinit():
    """...and the one booted with the accessories' disk in the drive (`build/preinit_acc.bin`; `make preinit-acc`)."""
    return preinit_snapshot.load(preinit_snapshot.accessory_path())


@functools.cache
def blank_disk():
    return accessory_disk.disk_with()


def desk_machine(machine=None):
    """THE DESK'S MACHINE: the ROM booted from the pre-init `machine` (this tree's by default) over the blank disk it
    was captured with — the post-boot snapshot's own boot, stopped at its FIRST idle instead of nine hundred
    vertical blanks on. The snapshot's family, without the time."""
    return Machine(booted(machine or preinit(), blank_disk()))


def accessory_machine(first=QUIET, second=QUIET, machine=None):
    """THE ACCESSORY MACHINE: the ROM booted from the ACCESSORY pre-init `machine` (this tree's by default) over the
    disk it was captured with, each accessory in its mode (`first`, `second`) — both loaded by the ROM's own loader,
    started, and waiting with the desk and the screen manager at the first idle."""
    return Machine(booted(machine or accessory_preinit(), accessory_disk_of(first, second)))
