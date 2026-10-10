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

A MACHINE WHOSE SCREEN MANAGER IS OURS (band 5 wave 2: `booted(..., ours=)`, `desk_machine(ours=blob)`,
`accessory_machine(..., ours=blob)`) is the same boot WITH ONE TAKEOVER: at the screen manager's first entry — the
ROM's switchto about to `rte` into the ROM's ctlmgr — the blob is laid and the two longwords the machine keeps that
entry in are mapped to the blob's own (`aes_event.SCREEN_MANAGER_ENTRY`: the relocation registry's entry; the
section "THE TAKEOVER" below says what is vetted there and where the boot ends). The ROM's boot runs on: its desk,
its loader and its accessories, with OUR ctlmgr the process they wake and are woken by. What such a machine differs
from the ROM-booted one in is FOUR CLASSES of bytes, each found through the machine's own pointers (`by_nature`,
`compared`).
A BOOTED MACHINE IS CONTINUED (`Machine.continued`) by what it receives at its idle — IKBD bytes through the ROM's
ACIA handler, the system timer's ticks through Timer C's — and its own run to the next idle, of whichever
dispatcher: how both shores' screen managers are held to DO the same when woken.

EVERYTHING HERE IS A KEPT DERIVATION (`derived.kept`). A ROM boot runs no line of the reconstruction. TWO KEPT
ANSWERS HERE DO RUN THE CANDIDATE — A NAMED EXCEPTION to `derived.py`'s rule that a derivation runs none (the
orchestrator's ruling, band 5 wave 2): `booted(..., ours=)`, a takeover boot, and `continued` of a takeover machine
both run THE BLOB. Each is sound BY ITS KEY: a derivation is keyed by the pre-init machine's CONTENT (an argument,
not a file of the tree: neither capture is in any tree key) AND BY THE BLOB'S — `Ours`, an argument too: the blob's
bytes and every address read off its ELF (for `continued`, inside the `Boot` it is handed) — so a fresh capture or
a rebuilt blob is another question and the old answer is never served for it; and an edited source is another TREE
besides (`derived.tree_key`). Neither answer runs the host library, so a process whose candidate library is not the
project's own (where `derived` keeps nothing) loses nothing by it.
"""
import ctypes
import functools
import hashlib
import operator
import random
import struct
from collections import namedtuple

import derived
from harness import BASE_IMAGE, addrs, emu
from recreate_kit import rom_bench

import accessory_disk
import preinit_snapshot
import st_build

import aes
import aes_event
import aes_switch
import case
import fs_pexec
import routines
import transcription

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
THE_ROM_S, OURS = "the ROM's", "ours"     # whose code a PC is, and whose dispatcher an idle is (`whose`)
Boot = namedtuple("Boot", "ram registers disk instructions cycles polls blanks floppy io_reads hardware_reads "
                          "hardware_writes stored bus_error_frame writes_truncated io idle takeover observed",
                  defaults=(None, THE_ROM_S, None, ()))
Boot.__doc__ = """One boot of the ROM from a pre-init machine to the first idle: the megabyte of `ram` it left and the
CPU's `registers` there (REGISTER_NAMES; the PC is idle's poll), the `disk` as it left it, its cost, how many times
idle polled on the way (`polls`, the last the idle), how many horizontal blanks it took (`blanks`), every `floppy`
call (`Call`), the declared I/O reads `(address, width, value)`, the kit's modelled reads `(address, value)`, the
off-image stores `(address, width, value)`, the RAM it
`stored` to as `(start, length)` runs (the kit's write ledger and the harness's own stores: the sectors read, the bus
error's frame), `bus_error_frame` (`{address: bytes}`: the fourteen bytes at the supervisor stack pointer, READ OUT
OF THE MACHINE as the probe's tail is entered) and whether the ledger saturated. `io`: the shifter bytes the pre-init
machine carried (what a run continued from this one is served). `idle`: WHOSE DISPATCHER the idle it ended at is
(THE_ROM_S, OURS — None for a boot stopped earlier, at `until`); `takeover`: the `Takeover` of a boot whose screen
manager is ours, or None; `observed`: of a CONTINUED run (`continued`), the calls it was watched to make."""


def io_seed_of(machine):
    """The declared I/O map of a pre-init machine: each byte of the shifter the capture read out of Hatari."""
    return _io_seed(machine.io)


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


# ---- THE TAKEOVER: A BOOT WHOSE SCREEN MANAGER IS OURS (band 5 wave 2: ctlmgr in C) -------------------------------------------
# THE ROM BOOTS, AND AT THE SCREEN MANAGER'S FIRST ENTRY OUR ctlmgr IS ENTERED IN THE ROM'S PLACE. ictlmgr hands pstart
# ctlmgr's address twice, and the machine keeps it in two longwords (`entry_slots`): the PD's p_ldaddr, and the PC of
# the frame psetup pushed on the new process's own stack — the frame switchto's `rte` pops when the dispatcher first
# enters it. THE TAKEOVER IS MADE AT THAT `rte`, the frame still under SP — a stop BY ADDRESS, never by a count —
# and is two things, neither a poke of the CPU:
#   * THE BLOB IS LAID where every Tier 3 row lays it (`Ours`: its link address, in the harness's free window);
#   * THE REGISTRY'S MAPPING IS APPLIED (`aes_event.SCREEN_MANAGER_ENTRY`): each of the two slots, which holds the
#     ROM's ctlmgr, is given the blob's own entry — found BY SYMBOL in the blob's ELF. The ROM's `rte` then pops OUR
#     entry: no register is set, and the PC is the one the machine's own instruction loads.
# That the mapping is what OUR ictlmgr + pstart store is ictlmgr's own returning row (the flip's, at the arrival
# `booted(until=<ictlmgr>)`): so the takeover is a build's ictlmgr having run, and no stage of ours.
# WHY THERE AND NOT EARLIER: on the accessory boot `Pexec(3)` hands the loader the largest free block — the free
# window — and CLEARS it before the screen manager first runs (measured: every byte of the blob's span stored
# before the stop, none after). `laid=FROM_THE_START` is that boot, kept as the RED it is.
# VETTED AT THE STOP, each refused by name (`_vet_the_first_entry`, `_vetted_slots`, `_vet_clear_where_the_blob_goes`):
# the process being entered is SCRENMGR, on the stack its own UDA names, the frame the only thing on it (every byte
# of its stack below is zero, as gem_main's BSS left it) and every register switchto loaded out of its never-saved
# UDA zero; the two slots are the registry's and hold the ROM's ctlmgr; nothing lies where the blob goes.
# VETTED WHERE THE BOOT ENDS (`_TakingOver.made`): the `rte` entered our entry on the stack's top; NOT ONE STORE of
# the rest of the boot landed in the blob's span (the write ledger from the lay on, and the sectors the harness laid),
# and its bytes are the blob's; p_ldaddr holds our entry; and the screen manager stands PARKED IN OUR TEXT (`whose`).
# WHERE A BOOT ENDS: at the first idle of WHICHEVER dispatcher — the ROM's (`IDLE_LOOP`) or the blob's own (its
# keyboard poll called from its idle: `Ours.poll`, `Ours.idle`). A process parks through the dispatcher of the build
# it runs: the desk and the accessories through the ROM's, the screen manager through ours — so the boot's last
# park decides, and `Boot.idle` says which (measured: the desk parks last in every boot here — the ROM's idle).
ENTRY_SYMBOL = aes_event.SCREEN_MANAGER_ENTRY_SYMBOL
ROM_ENTRY = aes_event.SCREEN_MANAGER_ROM_ENTRY
OUR_POLL, OUR_IDLE = "aes_chkkbd", "aes_idle"       # the blob's dispatcher: its poll, and the idle that calls it
SCREEN_MANAGER_NAME = b"SCRENMGR"
FRAME_PC = aes_event.EXCEPTION_FRAME_PC              # an exception frame: the status word, then the PC
FRAME_BYTES = WORD_BYTES + LONG_BYTES
AT_THE_FIRST_ENTRY, FROM_THE_START = "at the screen manager's first entry", "before the boot's first instruction"
# The handlers ctlmgr calls, each by its ROM entry and its frame there (two words): what a continued run is watched
# to call (`continued`) — on the blob at the entry of each one's C core (`routines.core_symbol`), a longword an
# argument, after the image pointer.
HANDLER_NAMES = ("AES_ROM_HCTL_BUTTON", "AES_ROM_HCTL_RECT")
HANDLER_WORDS = 2                       # (mx, my)

Ours = namedtuple("Ours", "base end image entry poll idle handlers")
Ours.__doc__ = """A blob AS A TAKEOVER READS IT (`ours_of`), by content — what a kept boot is keyed by: where it is
linked (`base`) and ends (`end`: its allocated span), its bytes (`image`), its `entry` (ENTRY_SYMBOL), its
dispatcher's `poll` and the `(start, end)` of the `idle` that calls it, and `handlers`: `((the ROM's handler, its C
core's entry), ...)`."""
Takeover = namedtuple("Takeover", "ours process stack instructions slots cleared stored_after found laid")
Takeover.__doc__ = """What one boot's takeover did and found: `ours`; the PD entered (`process`); its `stack` span
`(lo, top)` as the stop found it — from the end of the UDA's state block to the end of psetup's frame; how many
`instructions` the boot had run there (a capture's own number: for a reader, never a stop); `slots` — `{slot: (the
ROM's entry found, ours laid)}`; `cleared`: how many stores the boot had made into the blob's span BEFORE the blob was
laid; `stored_after`: the addresses of the span stored at AFTER (none, or the boot is refused); `found`: `(the
digest of the megabyte as the stop found it, the registers there)`; and `laid`: when the blob was."""


def _function_of(placed, symbol, blob, why):
    found = placed.get(symbol)
    if found is None or found.kind not in "Tt" or not blob.base <= found.start < blob.base + len(blob.blob):
        raise Refused(f"the blob {blob.elf} has no entry `{symbol}`: {why}")
    return found


@functools.cache
def _ours_at(elf, base, end, image):
    blob = namedtuple("Blob", "elf base blob")(elf, base, image)
    placed = {symbol.name: symbol for symbol in transcription.symbol_table(elf)}
    entry = _function_of(placed, ENTRY_SYMBOL, blob, "nothing of this build can be entered in the ROM's ctlmgr's place")
    poll = _function_of(placed, OUR_POLL, blob, "its dispatcher's idle has no poll to stop a boot at")
    idle = _function_of(placed, OUR_IDLE, blob, "its dispatcher has no idle to end a boot in")
    if idle.size is None:
        raise Refused(f"the blob {elf} does not size `{OUR_IDLE}`: a poll made from it cannot be told from ev_multi's")
    handlers = tuple((getattr(addrs, name), placed[routines.core_symbol(name)].start) for name in HANDLER_NAMES
                     if routines.core_symbol(name) in placed)
    return Ours(base, max(end, base + len(image)), image, entry.start, poll.start, (idle.start, idle.start + idle.size),
                handlers)


def ours_of(blob):
    """`blob` (a `RomBench`: the bench blob's or the shipped one's) AS A TAKEOVER READS IT: an `Ours` — its entry
    FOUND BY SYMBOL in its ELF, and REFUSED BY NAME where the blob has none."""
    return _ours_at(str(blob.elf), blob.base, blob.end, bytes(blob.blob))


def whose(pc, ours=None):
    """WHOSE CODE A PROCESS IS RESUMED IN — the PC switchto's `rte` pops — on a machine whose blob is `ours` (None:
    a machine the ROM booted): OURS inside the blob, THE_ROM_S inside the AES's own ROM text; anything else is
    refused by name (a PC in RAM that is no blob's, in the BIOS, in the desktop's text)."""
    pc &= BUS
    if ours is not None and ours.base <= pc < ours.base + len(ours.image):
        return OURS
    if aes.AES_TEXT[0] <= pc < aes.AES_TEXT[1]:
        return THE_ROM_S
    blob = f"the blob [{ours.base:#x}, {ours.base + len(ours.image):#x})" if ours is not None else "no blob (the ROM's boot)"
    raise Refused(f"a process resumed at {pc:#x}: neither in {blob} nor in the AES's ROM text "
                  f"[{aes.AES_TEXT[0]:#x}, {aes.AES_TEXT[1]:#x})")


def entry_slots(memory, pd):
    """THE TWO LONGWORDS THE MACHINE KEEPS A PROCESS'S ENTRY IN, for a process pstart has set up and nothing has
    entered yet — read through the machine's own pointers: its PD's p_ldaddr (pstart `$fe5892`), and the PC of the
    frame psetup pushed on the stack its UDA names (`$fe3994`: the status word, then the PC — the stack's top - 4)."""
    uda = case.long_in(memory, pd + aes.PD_UDA) & BUS
    return pd + aes.PD_LDADDR, (case.long_in(memory, uda + aes.UDA_SUPER_SP) & BUS) + FRAME_PC


def parked_pc(memory, pd):
    """Where the process `pd`, parked, is RESUMED: the PC of the frame at the stack pointer its UDA keeps."""
    uda = case.long_in(memory, pd + aes.PD_UDA) & BUS
    return case.long_in(memory, (case.long_in(memory, uda + aes.UDA_SUPER_SP) & BUS) + FRAME_PC) & BUS


def _name_of(memory, pd):
    return bytes(memory[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES])


def _vetted_slots(memory, pd):
    """`entry_slots` of the process switchto is about to enter — HELD to be the registry's two, each holding the
    ROM's ctlmgr: a mapping applied anywhere else is another process's, and is refused."""
    slots, registry = entry_slots(memory, pd), aes_event.SCREEN_MANAGER_ENTRY.slots
    if sorted(slots) != sorted(registry):
        raise Refused(f"the entry of the process at {pd:#x} lies at {[f'{slot:#x}' for slot in slots]}, and the "
                      f"registry's slots of {aes_event.SCREEN_MANAGER_ENTRY.what} are "
                      f"{[f'{slot:#x}' for slot in registry]}: the mapping would be applied to ANOTHER PROCESS")
    for slot in slots:
        held = case.long_in(memory, slot)
        if held != ROM_ENTRY:
            raise Refused(f"the slot at {slot:#x} of the process at {pd:#x} holds {held:#x}, not the ROM's ctlmgr "
                          f"({ROM_ENTRY:#x}): nothing of the registry's to map there — not the screen manager's entry")
    return slots


def _vet_the_first_entry(memory, pd, sp, registers):
    """THE STOP IS THE SCREEN MANAGER'S FIRST ENTRY (above) — `memory` and the CPU's `registers` at switchto's `rte`,
    `pd` the process it enters, `sp` its stack pointer — or the boot is refused by name: answers the process's
    stack span `(lo, top)`."""
    name, uda = _name_of(memory, pd), case.long_in(memory, pd + aes.PD_UDA) & BUS
    if name != SCREEN_MANAGER_NAME:
        raise Refused(f"switchto's `rte` pops the ROM's ctlmgr for the process {name!r} at {pd:#x}: not SCRENMGR")
    if sp != case.long_in(memory, uda + aes.UDA_SUPER_SP) & BUS:
        raise Refused(f"the screen manager is entered at SP {sp:#x}, not on the stack its UDA names")
    lo, status = uda + aes.UDA_STATE_BYTES, case.word_in(memory, sp)
    used = len(bytes(memory[lo:sp]).rstrip(b"\0"))
    if used:
        raise Refused(f"NOT THE SCREEN MANAGER'S FIRST ENTRY: its stack holds something below the frame popped, "
                      f"up to {lo + used - 1:#x} — the ROM's ctlmgr has run on it")
    if not status & SR_SUPERVISOR or status & SR_TRACE:
        raise Refused(f"the frame switchto pops for the screen manager holds the status word {status:#x}")
    loaded = {name: registers[name] for name in (*preinit_snapshot.DATA_REGISTERS, *preinit_snapshot.ADDRESS_REGISTERS)
              if registers[name]}
    if loaded:
        raise Refused(f"NOT THE SCREEN MANAGER'S FIRST ENTRY: switchto loaded {loaded} out of its UDA, which nothing "
                      f"has saved a context in yet")
    return lo, sp + FRAME_BYTES


def _vet_clear_where_the_blob_goes(memory, ours):
    held = bytes(memory[ours.base:ours.end]).lstrip(b"\0")
    if held:
        raise Refused(f"the machine holds something where the blob goes, from {ours.end - len(held):#x}: the harness's "
                      f"free window is not free at the screen manager's first entry")


def _mapped(memory, slots, mapping):
    """The longwords `slots` of `memory` mapped IN PLACE by `mapping`, as Tier 3 maps a registry's
    (`tier3.map_code_slots`): `{slot: (what it held, what it holds)}` for each one mapped."""
    done = {}
    for slot in slots:
        held = case.long_in(memory, slot)
        if held in mapping:
            memory[slot:slot + LONG_BYTES] = struct.pack(">I", mapping[held])
            done[slot] = (held, mapping[held])
    return done


class _TakingOver:
    """ONE BOOT'S TAKEOVER (above), made where the run stops for it: `armed` the stops it asks for as it stands —
    switchto's `rte` until the screen manager's first entry is found there, then our entry (the next instruction:
    held to be where the `rte` lands), then nothing."""

    def __init__(self, memory, ours, laid):
        self._memory, self.ours, self._laid = memory, ours, laid
        self.armed, self.taken, self.entered = frozenset({addrs.AES_ROM_SWITCHTO_RTE}), None, False
        self._mark, self._laid_by_the_harness = None, []
        if laid == FROM_THE_START:      # the RED's (above): before the run's ledger begins
            memory[ours.base:ours.base + len(ours.image)] = ours.image
            self._mark = 0

    def stopped(self, pc, sp, instructions):
        if pc == self.ours.entry:
            self._entered(sp)
        elif case.long_in(self._memory, sp + FRAME_PC) & BUS == ROM_ENTRY:
            self._take_over(sp, instructions)

    def _stored_in_the_span(self, since, until=None):
        """The addresses of the blob's span the run's write ledger names from its entry `since` on."""
        ledger, count = _CPU.osh_write_addrs(), _CPU.osh_num_writes() if until is None else until
        base, end = self.ours.base, self.ours.end
        return sorted({at for at in ledger[since:count] if base <= at < end})

    def harness_laid(self, at, size):
        """The harness itself stored `size` bytes at `at` (a sector read): the ledger does not name them."""
        if self._mark is not None:
            self._laid_by_the_harness += [each for each in range(at, at + size) if self.ours.base <= each < self.ours.end]

    def _take_over(self, sp, instructions):
        memory, ours = self._memory, self.ours
        pd = case.long_in(memory, aes.AES_RLR) & BUS
        slots = _vetted_slots(memory, pd)
        registers = _registers_now()
        stack = _vet_the_first_entry(memory, pd, sp, registers)
        found = (hashlib.sha256(memory[:RAM_BYTES]).digest(), registers)
        if self._laid == AT_THE_FIRST_ENTRY:
            cleared = len(self._stored_in_the_span(0))
            _vet_clear_where_the_blob_goes(memory, ours)
            memory[ours.base:ours.base + len(ours.image)] = ours.image
            self._mark = _CPU.osh_num_writes()
        else:
            cleared = 0
            self._vet_not_stored_over()
        mapped = _mapped(memory, slots, {ROM_ENTRY: ours.entry})
        self.taken = Takeover(ours, pd, stack, instructions, mapped, cleared, (), found, self._laid)
        self.armed = frozenset({ours.entry})

    def _entered(self, sp):
        if sp != self.taken.stack[1]:
            raise Refused(f"our entry is entered at SP {sp:#x}, not on the top of the screen manager's stack")
        self.entered, self.armed = True, frozenset()

    def _stored_over(self):
        """The addresses of the blob's span stored at since the blob was laid: by the run (its ledger) and by the
        harness (the sectors it laid)."""
        return sorted({*self._stored_in_the_span(self._mark), *self._laid_by_the_harness})

    def _vet_not_stored_over(self):
        ours, stored = self.ours, self._stored_over()
        if stored:
            raise Refused(f"THE BOOT STORED OVER THE BLOB, laid {self._laid}: {len(stored)} byte(s) of its span "
                          f"[{ours.base:#x}, {ours.end:#x}) from {stored[0]:#x} on — `Pexec` hands a program the largest "
                          f"free block and clears it, and the accessory loader's is the harness's free window")
        if bytes(self._memory[ours.base:ours.base + len(ours.image)]) != ours.image:
            raise Refused(f"the blob laid {self._laid} is no longer the blob's bytes, and the ledger names no store there")

    def made(self, memory, at_an_idle):
        """THE TAKEOVER, VETTED WHERE THE RUN ENDED (above): its `Takeover`."""
        if self.taken is None:
            raise Refused(f"the boot ended and switchto's `rte` never popped the ROM's ctlmgr ({ROM_ENTRY:#x}): the "
                          f"screen manager's first entry was not met — nothing was taken over")
        if not self.entered:
            raise Refused(f"the `rte` at the screen manager's first entry did not enter `{ENTRY_SYMBOL}` "
                          f"({self.ours.entry:#x}): the frame's PC was not mapped")
        self._vet_not_stored_over()
        taken = self.taken._replace(stored_after=tuple(self._stored_over()))
        pd = taken.process
        held = case.long_in(memory, pd + aes.PD_LDADDR)
        if held != self.ours.entry:
            raise Refused(f"the screen manager's p_ldaddr holds {held:#x}"
                          + (" — the ROM's ctlmgr: LEFT UNMAPPED" if held == ROM_ENTRY else "")
                          + f", not `{ENTRY_SYMBOL}` ({self.ours.entry:#x}) as our ictlmgr + pstart store it")
        if at_an_idle and whose(parked_pc(memory, pd), self.ours) != OURS:
            raise Refused(f"the screen manager stands parked at {parked_pc(memory, pd):#x}, in the ROM's text: this "
                          f"machine's screen manager is not ours")
        return taken


# ---- ONE RUN OF A MACHINE TO AN IDLE: a boot's, or a booted machine's continued -------------------------------------------------
class _Run:
    """The run itself, from a whole register file to AN IDLE — the first arrival at a dispatcher's idle poll with
    nothing ready, nothing woken and no fork queued: the ROM's dispatcher's, or the blob's own (`ours`: after a
    takeover, or of a machine continued) — or to its FIRST ARRIVAL AT `until` where one is named, an idle refused
    if it comes first. Each stop is served: a driver entry, the probe's touch, the blank's handler entered, a poll,
    the takeover's (`taking`), a call watched (`observing`: `{PC: (name, a reader of the frame at that stop)}`).
    AFTER IT: `result` (the last segment's), what the harness stored into the machine (`laid`, `pushed`), the bus
    error's `frame`, the `polls` made, the `blanks` taken, whose `idle` it ended at, and what it `observed`."""

    def __init__(self, memory, floppy, budget, *, until=None, taking=None, ours=None, observing=None):
        self._memory, self._floppy, self._budget, self._until = memory, floppy, budget, until
        self._taking, self._ours, self._observing = taking, ours, dict(observing or {})
        self._hbl = case.long_in(memory, addrs.VECTOR_HBL) & BUS
        self._back = None               # where a poll of ours returns: the poll's entry is a stop again from there
        self.laid, self.pushed, self.frame, self.polls, self.blanks = {}, {}, {}, 0, 0
        self.idle, self.observed, self.result = None, [], None

    def _our_dispatcher(self):
        """The blob whose idle is a stop as the run stands: a continued machine's, or a takeover's once made."""
        if self._taking is not None:
            return self._taking.ours if self._taking.entered else None
        return self._ours

    def _stops(self):
        stops = {*self._floppy.entries, BLITTER_PROBE_TOUCH, IDLE_LOOP, IDLE_POLLED, self._hbl, *self._observing}
        stops |= {self._until} if self._until else set()
        stops |= self._taking.armed if self._taking is not None else set()
        ours = self._our_dispatcher()
        stops |= {ours.poll} if ours is not None else set()
        stops |= {self._back} if self._back is not None else set()
        return stops

    def to_an_idle(self, entered, io_seed):
        """Entered with the register file `entered` — the door at its PC, so the run stops before one instruction —
        and a horizontal blank pending; then each stop, to the idle."""
        budget, memory = self._budget, self._memory
        emu.install_chip_seeds()
        result = emu.run_bench(memory, entered["pc"], 0, OFF_THE_MACHINE, emu.SENTINEL, max_insns=budget,
                               door={entered["pc"]}, seed_regs=None, io_seed=io_seed)
        assert result["status"] == emu.BENCH_DOOR and not result["ninsns"], "the run began before its registers were laid"
        _enter(entered)
        _CPU.m68k_set_irq(HBL_LEVEL)
        ours = self._our_dispatcher()
        if ours is not None and entered["pc"] == ours.poll:
            self._back = case.long_in(memory, _register("a7")) & BUS      # entered AT a poll of ours (a machine continued)
        while True:
            emu.bench_door_arm(self._stops() - {_register("pc")})
            left = budget - result["ninsns"]
            if left <= 0:
                raise Refused(f"the run did not reach an idle within {budget} instructions")
            result = self._resumed(left)
            if result["status"] != emu.BENCH_DOOR:
                raise Refused(f"the run left the machine: it ended with status {result['status']} at "
                              f"{emu.bench_resume_pc():#x}")
            self.result = result
            if self._stopped(emu.bench_door_pc(), emu.bench_door_sp()):
                return result

    def _resumed(self, left):
        """The run continued to its next stop — or REFUSED BY NAME where `left` instructions do not reach one: a
        machine that never idles (a process that yields with nothing to wait for spins the dispatcher for ever — the
        screen manager with the button held down)."""
        try:
            return emu.bench_resume(GEM_ENTRY, max_insns=left)
        except RuntimeError as spun:
            if "did not return to the sentinel" not in str(spun):
                raise
            raise Refused(f"the run did not reach an idle within {self._budget} instructions: it stands at "
                          f"{emu.bench_resume_pc():#x} and the machine never waits for an interrupt") from spun

    def _stopped(self, pc, sp):
        """One stop served: True where the run ends there."""
        memory, ours = self._memory, self._our_dispatcher()
        if pc in self._floppy.entries:
            self._serve_the_driver(pc, sp)
        elif pc == self._hbl:
            self.blanks += 1            # ...taken: the CPU let the line go, and the next one is pending from here
            _CPU.m68k_set_irq(HBL_LEVEL)
        elif pc == BLITTER_PROBE_TOUCH:
            _vet_the_probe(memory)
            self.pushed = _bus_error(memory, BLITTER_REGISTERS)
            self.frame = _the_frame_the_handler_is_entered_over(memory)
        elif pc == self._until:
            return True
        elif pc == IDLE_LOOP:
            return self._polled(THE_ROM_S)
        elif self._taking is not None and pc in self._taking.armed:
            self._taking.stopped(pc, sp, self.result["ninsns"])
        elif ours is not None and pc == ours.poll:
            self._back = case.long_in(memory, sp) & BUS
            if ours.idle[0] <= self._back < ours.idle[1]:      # ...or a poll of the event layer's own (ev_multi's)
                return self._polled(OURS)
        elif pc == self._back:
            self._back = None
        elif pc in self._observing:
            name, read = self._observing[pc]
            self.observed.append((name, read(memory, sp)))
        return False

    def _serve_the_driver(self, pc, sp):
        floppy, memory = self._floppy, self._memory
        before = len(floppy.calls)
        answer, to = floppy.served(pc, sp)
        _return_from_the_driver(answer, to, sp)
        call, = floppy.calls[before:]
        if call.function == RWABS and not call.arguments[0] & RWABS_WRITE:
            _flag, buffer, count, _record, _device = call.arguments
            self.laid[buffer] = bytes(memory[buffer:buffer + count * st_build.SECTOR_BYTES])
            if self._taking is not None:
                self._taking.harness_laid(buffer, count * st_build.SECTOR_BYTES)

    def _polled(self, whose_idle):
        self.polls += 1
        if not aes_switch.waits_for_an_interrupt(self._memory):
            return False
        if self._until:
            raise Refused(f"the boot reached its first idle and never arrived at {self._until:#x}")
        self.idle = whose_idle
        return True

    def stored(self, writes):
        """The RAM the run stored to, as runs: its ledger's addresses and the harness's own stores."""
        stored = set(at for at in writes if at < RAM_BYTES)
        for at, data in {**self.laid, **self.pushed}.items():
            stored.update(range(at, at + len(data)))
        return _runs(sorted(stored))


def _io_seed(io):
    """The declared I/O map of a pre-init machine's shifter bytes."""
    return {preinit_snapshot.IO_AT + offset: byte for offset, byte in enumerate(io)}


@derived.kept
def booted(machine, disk, budget=BOOT_INSNS, until=None, ours=None, laid=AT_THE_FIRST_ENTRY):
    """THE ROM'S OWN BOOT (the module's docstring) from the pre-init `machine` (`preinit_snapshot.PreInit`) with
    `disk` — the one it booted with — in drive A:, to the first idle: a `Boot`. `until`: STOPPED EARLIER, at the
    boot's first arrival at that address — a routine's entry, the machine and the registers as its caller left
    them (the `Boot`'s PC is then `until`, its A7 the caller's stack pointer over the return address and the frame).
    `ours` (an `Ours`: `ours_of(blob)`): THE SCREEN MANAGER IS OURS — the takeover (above) made at its first entry,
    the `Boot`'s `takeover` what it did; `until` may then name an address of the blob. KEPT BY CONTENT: the pre-init
    machine's, the disk's and the blob's — a rebuilt blob is another question. `laid`: when the blob is (the RED's)."""
    memory = bytearray(BASE_IMAGE)                  # ...for the ROM in it: the megabyte below is the pre-init machine's
    memory[:RAM_BYTES] = machine.ram
    floppy = Floppy(memory, disk)
    taking = _TakingOver(memory, ours, laid) if ours is not None else None
    run = _Run(memory, floppy, budget, until=until, taking=taking)
    try:
        result = run.to_an_idle(machine.registers, io_seed_of(machine))
        registers = _registers_now()
        writes, truncated = emu.bench_writes(memory)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
        if taking is not None and truncated:
            raise Refused("the boot's write ledger saturated: what it stored over the blob's span is not known")
        takeover = taking.made(memory, run.idle is not None) if taking is not None else None
    finally:
        _CPU.m68k_set_irq(NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("the ROM's boot from the pre-init machine")
    return Boot(bytes(memory[:RAM_BYTES]), registers, bytes(floppy.disk), result["ninsns"], result["cycles"], run.polls,
                run.blanks, tuple(floppy.calls), *streams, run.stored(writes), run.frame, truncated, machine.io, run.idle,
                takeover)


# ---- THE TEST ACCESSORY (`tools/accessory_disk.py` builds it and its disk) ---------------------------------------------------
PRG_HEADER_BYTES = fs_pexec.PRG_HEADER_BYTES
PRG_TEXT_BYTES_AT = 2                   # the header's four lengths: TEXT, DATA, BSS, symbols
NOT_CALLED = 0xfffe                     # what testacc.S's `res_find` and `res_write` hold until the call is made
QUIET, FIND, WRITE, MULTI = accessory_disk.QUIET, accessory_disk.FIND, accessory_disk.WRITE, accessory_disk.MULTI
REGISTER, HIDE, with_a_window = accessory_disk.REGISTER, accessory_disk.HIDE, accessory_disk.with_a_window
ACCESSORY_NAMES = accessory_disk.NAMES
RESULT_WORDS = ("res_id", "res_find", "res_write", "res_events", "res_wakes", "res_menu", "res_window", "res_opened")
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
        self.takeover, self.idle, self.observed = boot.takeover, boot.idle, boot.observed
        self.ours = boot.takeover.ours if boot.takeover else None      # the blob of a machine whose screen manager is ours

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

    def screen_manager(self):
        """The screen manager's process, BY ITS NAME."""
        return self.named(SCREEN_MANAGER_NAME.decode())

    def whose(self, pc):
        """Whose code `pc` — a PC a switchto's `rte` resumes a process of this machine at — is (`whose`)."""
        return whose(pc, self.ours)

    def resumed_in(self, process):
        """...and whose the waiting `process` (a `Process`) will be resumed in: OURS, or THE_ROM_S."""
        return self.whose(parked_pc(self.ram, process.pd))

    def continued(self, *received, budget=None):
        """THIS MACHINE, AT ITS IDLE, RECEIVES — each of `received` through the ROM's own interrupt handlers
        (`mouse_to`, `ikbd`, `CLICK_TICKS`) — AND RUNS ON TO ITS NEXT IDLE (`continued`): the `Machine`
        there, `observed` the handlers its screen manager was watched to call. A TAKEOVER MACHINE CANNOT BE
        CONTINUED THROUGH AN ALLOCATION THAT REACHES THE BLOB (refused by name: `_vet_the_blob_was_not_reached`)."""
        return Machine(continued(self.boot, received, *((budget,) if budget else ())))

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


def _taken_over_by(blob):
    """`booted`'s arguments that make the screen manager `blob`'s (None: the ROM's own)."""
    return {} if blob is None else {"ours": ours_of(blob)}


def desk_machine(machine=None, ours=None):
    """THE DESK'S MACHINE: the ROM booted from the pre-init `machine` (this tree's by default) over the blank disk it
    was captured with — the post-boot snapshot's own boot, stopped at its FIRST idle instead of nine hundred
    vertical blanks on. The snapshot's family, without the time. `ours` (a `RomBench`: `isr.blob_named`): THE SCREEN
    MANAGER IS THAT BLOB'S (the takeover)."""
    return Machine(booted(machine or preinit(), blank_disk(), **_taken_over_by(ours)))


def accessory_machine(first=QUIET, second=QUIET, machine=None, ours=None):
    """THE ACCESSORY MACHINE: the ROM booted from the ACCESSORY pre-init `machine` (this tree's by default) over the
    disk it was captured with, each accessory in its mode (`first`, `second`) — both loaded by the ROM's own loader,
    started, and waiting with the desk and the screen manager at the first idle. `ours`: as `desk_machine`'s."""
    return Machine(booted(machine or accessory_preinit(), accessory_disk_of(first, second), **_taken_over_by(ours)))


# ---- A BOOTED MACHINE, CONTINUED: what it receives at its idle, and the run to its next -------------------------------------
# WHAT A MACHINE RECEIVES is what a user's hand sends it, AS THE HARDWARE DELIVERS IT: bytes of the IKBD, each taken
# through the ROM's own ACIA handler entered from the machine's own vector (`_Receiving`, as `aes_switch` enters one: the
# handler's run over the machine as it stands, an exception frame under it; its three bytes make a packet the BIOS
# hands the VDI's mouse interrupt, which calls the AES's two glues) — and the system timer's ticks, through the ROM's
# Timer C handler from ITS vector, as many as run an open click count out. Each run's stores are laid into the
# machine; its own stack is the harness's (on iron its frames land below the interrupted SP: dead bytes of the
# dispatcher's stack, which no machine here is compared in).
# THEN THE MACHINE RUNS ON FROM ITS IDLE — the CPU entered with the whole register file the idle was met with, at the
# poll it stood at (the ROM's dispatcher's or the blob's) — to the next idle of either. Nothing is staged: what woke
# is what the interrupts' own code queued.
CONTINUED_INSNS = 1_500_000             # one wake's run to the next idle (measured: a menu dropped is some 80,000)
MOUSE_TO, IKBD_BYTES, CLICK_TICKS = "the mouse moved to", "the IKBD sends", ("ticks until the click's count has run out",)
MOST_CLICK_TICKS = 256                  # a click's count is a few serviced ticks: a wait past this resolves nothing
LEFT_DOWN, NO_BUTTON = aes_event.LEFT_DOWN_PACKET, aes_event.NO_BUTTON_PACKET


def mouse_to(x, y):
    """RECEIVED: relative mouse packets toward (`x`, `y`), the buttons as they are held, until the cursor is there."""
    return MOUSE_TO, x, y


def ikbd(*packet):
    """RECEIVED: these bytes from the IKBD — a relative mouse packet is its header, dx and dy."""
    return IKBD_BYTES, bytes(byte & aes.BYTE_MASK for byte in packet)


MFP_LEVEL = 6                           # the 68901's interrupt priority: the ACIAs' line and Timer C both
SR_IPL_SHIFT = 8                        # the status register's interrupt mask, bits 8-10 (`addrs.SR_IPL_MASK`)
OPEN_TO_INTERRUPTS = addrs.SR_IPL_MASK | SR_SUPERVISOR      # of a status word: what says who may interrupt it


class _Receiving:
    """WHAT A MACHINE AT ITS IDLE RECEIVES, taken over `memory` IN PLACE (above), each interrupt the ROM's own
    handler entered from the machine's own vector (`aes_switch`'s staged entry: the exception frame, then the
    handler) and its stores laid in. `status`: the status register the idle stands at — AN INTERRUPT IS REFUSED BY
    NAME where its mask does not let that level in: a machine whose dispatcher left the mask at 6 or 7 hears no
    keyboard and no timer, and a model that ran the handler all the same would hide a dead machine. `stored`: every
    address the handlers stored at (the harness's own stack band apart)."""

    def __init__(self, memory, status):
        self._memory, self._status, self.stored = memory, status, set()

    def _interrupted(self, vector, what, **seeds):
        masked = (self._status & addrs.SR_IPL_MASK) >> SR_IPL_SHIFT
        if masked >= MFP_LEVEL:
            raise Refused(f"the machine stands at its idle with the interrupt mask at {masked}: {what} — an MFP "
                          f"interrupt, level {MFP_LEVEL} — is never taken. On iron this machine is dead")
        entry = case.long_in(self._memory, vector) & BUS
        stub = aes_switch.PUSH_RETURN_AND_SR + aes_switch.JMP_ABSOLUTE_LONG + struct.pack(">I", entry) + aes_switch.RTS
        staged = bytearray(self._memory)
        staged[aes_switch.INTERRUPT_STUB_AT:aes_switch.INTERRUPT_STUB_AT + len(stub)] = stub
        _final, writes, _regs = emu.run(staged, aes_switch.INTERRUPT_STUB_AT, {}, **seeds)
        for at, data in case.written_by(writes).items():
            self._memory[at:at + len(data)] = data
            self.stored.update(range(at, at + len(data)))

    def _through_the_acia(self, data):
        for byte in data:
            self._interrupted(addrs.VECTOR_ACIA, f"the IKBD's byte {byte:#04x}",
                              io_seed={**aes_switch.ACIA_SEEDS, addrs.IKBD_ACIA_DATA: byte})

    def _moved_to(self, x, y):
        memory = self._memory
        while aes_event._cursor(memory) != (x, y):
            cursor = aes_event._cursor(memory)
            dx, dy = (max(-aes_event.MOUSE_STEP, min(aes_event.MOUSE_STEP, to - at)) for to, at in zip((x, y), cursor))
            header = aes_event.MOUSE_PACKET_HEADER | aes_event._packet_buttons(memory)
            self._through_the_acia(bytes((header, dx & aes.BYTE_MASK, dy & aes.BYTE_MASK)))
            if aes_event._cursor(memory) == cursor:
                raise Refused(f"the mouse cannot be moved to ({x}, {y}): a packet of ({dx}, {dy}) left the cursor at {cursor}")

    def _ticked_until_the_click_resolves(self):
        for _tick in range(MOST_CLICK_TICKS):
            if not case.word_in(self._memory, aes.AES_GL_CLICK_TICKS):
                return
            self._interrupted(addrs.VECTOR_TIMER_C, "the system timer's tick", psg_seed=aes_switch.QUIET_PSG)
        raise Refused(f"{MOST_CLICK_TICKS} ticks of the system timer did not run the click's count out")

    def all_of(self, received):
        """Each of `received`, in turn."""
        for kind, *what in received:
            if kind == MOUSE_TO:
                self._moved_to(*what)
            elif kind == IKBD_BYTES:
                self._through_the_acia(*what)
            elif (kind, *what) == CLICK_TICKS:
                self._ticked_until_the_click_resolves()
            else:
                raise Refused(f"a machine cannot receive {(kind, *what)}")
        return self


def _vet_the_blob_was_not_reached(memory, ours, stored):
    """A CONTINUED TAKEOVER MACHINE STILL HOLDS ITS BLOB, UNTOUCHED — or the continuation is refused by name.
    THE STANDING LIMIT of every machine here whose screen manager is ours: the blob lies where the harness lays it,
    in memory GEMDOS BELIEVES FREE (its free list was cut before the blob existed, and nothing tells it). A chain in
    which the desk or an accessory Mallocs or Pexecs far enough is HANDED THOSE BYTES — and would run on over our
    code. So `stored` — every address the run's ledger, the interrupt handlers and the harness's own sector reads
    name — must miss the blob's span, and its bytes must be the blob's."""
    reached = sorted(at for at in stored if ours.base <= at < ours.end)
    if reached or bytes(memory[ours.base:ours.base + len(ours.image)]) != ours.image:
        raise Refused(
            f"A TAKEOVER MACHINE CANNOT BE CONTINUED THROUGH AN ALLOCATION THAT REACHES THE BLOB: the continuation "
            + (f"stored {len(reached)} byte(s) of its span [{ours.base:#x}, {ours.end:#x}) from {reached[0]:#x} on"
               if reached else "left its span holding other bytes than the blob's, by no store the ledgers name")
            + " — the blob lies in memory GEMDOS believes free, and a Malloc or a Pexec of the desk's or an accessory's "
              "is handed it")


def _handler_frame_of_the_rom(memory, sp):
    """The two words the ROM's ctlmgr pushed for a handler: above the return address."""
    return struct.unpack_from(f">{HANDLER_WORDS}h", memory, sp + LONG_BYTES)


def _handler_frame_of_ours(memory, sp):
    """...and the two GCC's caller left its C core: a longword each, after the return address and the image."""
    return tuple(aes.signed(case.long_in(memory, sp + (2 + nth) * LONG_BYTES) & aes.WORD_MASK) for nth in range(HANDLER_WORDS))


def handler_stops(ours=None):
    """`{PC: (the handler's name, the reader of its frame there)}`: the ROM's handlers' entries and, on a machine
    whose screen manager is `ours`, their C cores' in the blob."""
    stops = {getattr(addrs, name): (aes_event.short_name(name), _handler_frame_of_the_rom) for name in HANDLER_NAMES}
    for rom, core in (ours.handlers if ours is not None else ()):
        stops[core] = (stops[rom][0], _handler_frame_of_ours)
    return stops


@derived.kept
def continued(boot, received, budget=CONTINUED_INSNS):
    """`boot` — a machine at its idle — CONTINUED (above): what it `received` taken through the ROM's interrupt
    handlers, then the run to its next idle. A `Boot` again: the megabyte and the registers THERE, that run's own
    cost, polls, stores and streams, whose `idle` it ended at, and `observed` — `(the handler, (mx, my))` for each
    call of a screen manager's handler (`handler_stops`), in order, whichever shore's ctlmgr made it.
    REFUSED BY NAME: a reception the idle's interrupt mask would never let in (`_Receiving`); and, on a machine whose
    screen manager is ours, A CONTINUATION THAT REACHES THE BLOB (`_vet_the_blob_was_not_reached`: the blob lies in
    memory GEMDOS believes free — a row's chain may not Malloc or Pexec its way into it)."""
    if boot.idle is None:
        raise Refused("a boot stopped before its first idle is continued by nothing: it stands at no idle")
    ours = boot.takeover.ours if boot.takeover else None
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = boot.ram
    receiving = _Receiving(memory, boot.registers["sr"]).all_of(received)
    floppy = Floppy(memory, boot.disk)
    run = _Run(memory, floppy, budget, ours=ours, observing=handler_stops(ours))
    try:
        result = run.to_an_idle(boot.registers, _io_seed(boot.io))
        registers = _registers_now()
        writes, truncated = emu.bench_writes(memory)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
    finally:
        _CPU.m68k_set_irq(NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("a booted machine's run from its idle to the next")
    if truncated:
        raise Refused("the continued run's write ledger saturated: what it stored is not known")
    if ours is not None:
        harness_s = {at for start, data in run.laid.items() for at in range(start, start + len(data))}
        _vet_the_blob_was_not_reached(memory, ours, {*writes, *receiving.stored, *harness_s})
    return boot._replace(ram=bytes(memory[:RAM_BYTES]), registers=registers, disk=bytes(floppy.disk),
                         instructions=result["ninsns"], cycles=result["cycles"], polls=run.polls, blanks=run.blanks,
                         floppy=tuple(floppy.calls), io_reads=streams[0], hardware_reads=streams[1],
                         hardware_writes=streams[2], stored=run.stored(writes), bus_error_frame=run.frame,
                         writes_truncated=truncated, idle=run.idle, observed=tuple(run.observed))


# ---- A MACHINE WHOSE SCREEN MANAGER IS OURS, BESIDE THE ONE THE ROM BOOTED: what the two differ in, BY NATURE ---------------
# FOUR CLASSES, and nothing else in the megabyte (`compared`; `test_aes_boot.py` holds it on every machine, both
# blobs) — each LOCATED FROM THE MACHINES' OWN POINTERS, never by an address:
#   * THE DISPATCHER'S DEAD FRAMES: its stack below the stack pointer the idle stands at. A switch runs on that
#     stack and leaves it dead; the frames there are those of the build whose dispatcher last ran — ours, when the
#     screen manager parks. DROPPED, and proved dead by noise (`noised`: the machine's continuation is unchanged).
#   * THE SCREEN MANAGER'S SAVED CONTEXT in its UDA (`aes_switch.uda_context_drop`: savestate's registers and the
#     two stack pointers): the CPU state of the code that called dsptch — ours. DROPPED; vetted by RESUMING it.
#   * THE SCREEN MANAGER'S STACK, `[the end of its UDA's state block, the top psetup's frame ended at)`: below the
#     parked stack pointer DEAD (noise-proved), from it up the LIVE frames of whichever ctlmgr runs there. DROPPED;
#     the live frames vetted by what the screen manager DOES when woken (`continued`, on both shores).
#   * ITS p_ldaddr: a code address — MAPPED through the registry (`aes_event.SCREEN_MANAGER_ENTRY`), and equal
#     after it. Never dropped.
# and the blob's own span, which the ROM's machine holds empty.
# TWO MORE WHERE THE TWO IDLES ARE NOT ONE DISPATCHER'S — a machine continued until its screen manager parks LAST
# stands in OUR idle where the ROM's stands in the ROM's — each `by_nature`'s to name, PER COMPARISON, and REFUSED
# where the two machines do not differ in it (`compared`):
#   * the WHOLE dispatcher's stack (the live frames of two builds' idles) — in place of its dead frames;
#   * THE LINE-F MASK WORD (`aes.LINE_F_MASK_WINDOW`: rewritten by every masked return of the ROM's code, by no C);
#   * THE BIOS'S LAST REGISTER-SAVE FRAME (`trap_save_frame`: the frame under `savptr` — dead once the trap has
#     returned — in which the idle's own keyboard poll, a BIOS trap, saved the registers and the return of the
#     build that polled).
DEAD_DISPATCHER_FRAMES = "the dispatcher's dead frames: its stack below the stack pointer the idle stands at"
DISPATCHER_STACK = "the dispatcher's whole stack: the two machines idle in two builds' dispatchers"
SAVED_CONTEXT = "the screen manager's saved context in its UDA"
MANAGER_STACK = "the screen manager's stack: dead below its parked stack pointer, its ctlmgr's live frames above"
THE_BLOB = "the blob's own span"
LINE_F_MASK, TRAP_SAVE_FRAME = "the Line-F mask word", "the BIOS's last register-save frame, dead under savptr"
Compared = namedtuple("Compared", "differing within")
Compared.__doc__ = """Two machines compared: `differing` — the `(address, length)` runs they differ at OUTSIDE every
class (none, for a takeover machine beside its ROM-booted one) — and `within`: `{class: how many bytes differ in
it}`, the measured table."""
COMPARED_BLOCK_BYTES = 0x1000


def trap_save_frame(machine):
    """`(lo, hi)` of the BIOS's register-save frame last used on `machine`: the one under `savptr`."""
    top = machine.long(addrs.SYSVAR_SAVPTR) & BUS
    return top - addrs.TRAP_SAVE_FRAME_BYTES, top


def by_nature(rom, ours):
    """THE CLASSES (above) the takeover machine `ours` differs from the ROM-booted `rom` in, `{class: (lo, hi)}` —
    the two machines at the idle the same receptions brought each to — and the classes a comparison of them may
    name beside (`{class: (lo, hi)}`: needed only where the two idles are two dispatchers')."""
    if ours.takeover is None or rom.takeover is not None:
        raise Refused("a comparison is of the machine THE ROM BOOTED and, second, of one whose screen manager is ours: "
                      f"the first {'is' if rom.takeover else 'is not'} a takeover machine, the second "
                      f"{'is' if ours.takeover else 'is not'}")
    manager, taken = ours.screen_manager(), ours.takeover
    if rom.screen_manager()._replace(events=(), basepage=0) != manager._replace(events=(), basepage=0):
        raise Refused(f"the two machines' screen managers are not one process: {rom.screen_manager()} and {manager}")
    (context_lo, context_hi, _why), = aes_switch.uda_context_drop(manager.uda)
    bottom, top = aes_event.DISPATCHER_STACK
    one_dispatcher = rom.idle == ours.idle
    dead_below = max(rom.registers["isp"], ours.registers["isp"])
    classes = {DEAD_DISPATCHER_FRAMES if one_dispatcher else DISPATCHER_STACK: (bottom, dead_below if one_dispatcher else top),
               SAVED_CONTEXT: (context_lo, context_hi), MANAGER_STACK: taken.stack,
               THE_BLOB: (taken.ours.base, taken.ours.end)}
    (mask_lo, mask_hi, _mask_why), = aes.LINE_F_MASK_WINDOW
    return classes, {LINE_F_MASK: (mask_lo, mask_hi), TRAP_SAVE_FRAME: trap_save_frame(ours)}


def _differing_runs(one, other):
    """Every maximal `(address, length)` run two megabytes differ at."""
    runs = []
    for block in range(0, len(one), COMPARED_BLOCK_BYTES):
        if one[block:block + COMPARED_BLOCK_BYTES] == other[block:block + COMPARED_BLOCK_BYTES]:
            continue
        for at in range(block, min(block + COMPARED_BLOCK_BYTES, len(one))):
            if one[at] != other[at]:
                if runs and runs[-1][0] + runs[-1][1] == at:
                    runs[-1][1] += 1
                else:
                    runs.append([at, 1])
    return [tuple(run) for run in runs]


def mapped_back(machine):
    """`machine`'s megabyte with every code address of the registry's slots given THE ROM'S NAME (ours -> the ROM's:
    the screen manager's entry, where a slot holds it) — what a takeover machine is compared as."""
    ram = bytearray(machine.ram)
    if machine.ours is not None:
        _mapped(ram, aes_event.SCREEN_MANAGER_ENTRY.slots, {machine.ours.entry: ROM_ENTRY})
    return bytes(ram)


def compared(rom, ours, also=()):
    """THE STRUCTURAL COMPARISON: the takeover machine `ours` beside the ROM-booted `rom` (each at the idle the same
    receptions brought it to), its code addresses mapped back (`mapped_back`), every class of `by_nature` left out —
    and each class `also` names beside (LINE_F_MASK, TRAP_SAVE_FRAME), REFUSED BY NAME where the two machines do not
    differ in it: a `Compared`."""
    classes, nameable = by_nature(rom, ours)
    unknown = [name for name in also if name not in nameable]
    if unknown:
        raise Refused(f"no class a comparison may name beside: {unknown}")
    classes.update({name: nameable[name] for name in also})
    spans = sorted(classes.values())
    if any(hi > lo_after for (_lo, hi), (lo_after, _hi) in zip(spans, spans[1:])):
        raise Refused(f"two classes of one comparison overlap: {[(hex(lo), hex(hi)) for lo, hi in spans]}")
    theirs, mine, within = rom.ram, bytearray(mapped_back(ours)), {}
    for name, (lo, hi) in classes.items():      # ...each class counted, then left out: given the ROM's bytes
        within[name] = sum(map(operator.ne, theirs[lo:hi], mine[lo:hi]))
        mine[lo:hi] = theirs[lo:hi]
    unneeded = [name for name in also if not within[name]]
    if unneeded:
        raise Refused(f"the two machines do not differ in {unneeded}: a class named beside and not needed")
    return Compared(_differing_runs(theirs, bytes(mine)), within)


def noised(machine, spans, seed):
    """`machine` with every byte of `spans` (`(lo, hi)` each) replaced by NOISE that differs from it: the machine a
    dead span is proved dead on — its continuation is the plain machine's."""
    generator, ram = random.Random(seed), bytearray(machine.ram)
    for lo, hi in spans:
        for at in range(lo, hi):
            ram[at] ^= generator.randrange(1, 256)
    return Machine(machine.boot._replace(ram=bytes(ram)))


def restaged(machine, memory):
    """`machine` WITH THE MEGABYTE OF `memory` — A LABELLED STAGING, its author's to justify (a routine laid under a
    trap, a tree's object changed) — and, on a machine whose screen manager is ours, ITS BLOB AS `memory` HOLDS IT: the
    `Ours` it carries is given those bytes, so a staging that patches the blob's own text (the build's VDI linked
    under `trap #2`) is the blob a continuation then holds untouched (`_vet_the_blob_was_not_reached`). The entry,
    the poll, the idle and the handlers stay where the ELF placed them: a staging that moves code is not this."""
    boot = machine.boot._replace(ram=bytes(memory[:RAM_BYTES]))
    if machine.ours is not None:
        ours = machine.ours
        staged = ours._replace(image=bytes(memory[ours.base:ours.base + len(ours.image)]))
        boot = boot._replace(takeover=boot.takeover._replace(ours=staged))
    return Machine(boot)


def dead_spans(machine):
    """THE SPANS OF `machine`, AT ITS IDLE, NO CODE WILL READ BEFORE IT WRITES — `{what: (lo, hi)}`: the dispatcher's
    stack below the idle's stack pointer, the screen manager's stack below its parked stack pointer, and the BIOS's
    register-save frame under `savptr`."""
    manager = machine.screen_manager()
    parked = machine.long(manager.uda + aes.UDA_SUPER_SP) & BUS
    return {DEAD_DISPATCHER_FRAMES: (aes_event.DISPATCHER_STACK[0], machine.registers["isp"]),
            MANAGER_STACK: (manager.uda + aes.UDA_STATE_BYTES, parked),
            TRAP_SAVE_FRAME: trap_save_frame(machine)}
