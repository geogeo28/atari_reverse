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

  1. THE FLOPPY, AT THE DRIVER'S ENTRIES. GEMDOS reaches a disk through `hdv_bpb`, `hdv_mediach` and `hdv_rw`,
     which on this machine name the ROM's floppy driver; below those entries is the FDC and its DMA — transactions,
     which `TRAP_MODEL.md` puts out of the model's reach. So the run is STOPPED at the three addresses the machine's
     own vectors hold and the call is answered there (`Floppy`): `Rwabs` copies sectors between the caller's buffer
     and a 720 KB image held OFF the machine, and `Mediach` says UNCHANGED.
     A FOURTH ENTRY AND ONE BYTE OF THE DRIVER'S STATE (band 5 wave 4: what a drive's window needs — nothing of a
     boot arrives at either). The desk, before it opens a drive, reads the boot sector FOR ITSELF by XBIOS `Floprd`
     — under the three vectors, at the driver's own routine, served there too — and then FORCES A MEDIA CHANGE:
     `Rwabs` of NO BUFFER, whose count the ROM's driver stores as the drive's mode. The model stores that byte where
     the driver keeps it (read out of its instruction), answers `Mediach` CHANGED while it says so, and serves the
     `Getbpb` GEMDOS then asks — the one Getbpb served: of the disk the machine logged in, after a forced change —
     which ends it.
     THE DISK SERVED IS THE DISK THE CAPTURE BOOTED WITH, and that is held, not assumed: the driver's own record for
     drive A: must hold the BPB of the image's boot sector, ITS GEOMETRY AND ITS SERIAL, or the boot is refused. So
     GEMDOS's cache of the FAT and the root, the driver's record and its boot-sector buffer are the ones the REAL
     driver left before `gem_entry`; nothing is swapped in, and `Getbpb` — which the ROM answers by reading the
     boot sector again and rewriting all of that: the same bytes, for that disk — is asked by no boot (band 6 wave
     4's devices, below, are where a run asks it of another disk: one the formatter rewrote, drive B:'s). The desk's
     machine boots from the capture made with the blank disk, the accessories' from the capture made with THEIR
     disk in the drive from power-on (`preinit_snapshot.accessory_path`); a mode is a word inside an accessory's own
     cluster, which nothing reads before `gem_entry` (`tools/accessory_disk.py`).
     WHY NOT A RAM DISK IN THE FREE WINDOW, as the file system's batteries stage one: `Pexec` hands a program the
     LARGEST free block and CLEARS it, and at the accessory loader's `Pexec(3)` that block is all of free memory —
     the staged disk and its stub routines with it (measured: the loader's first read after the clear ran off
     through the wiped window). `fs_pexec.pool` goes round that by re-cutting GEMDOS's pool with pokes; a device
     held off the machine needs none.
     WHAT THE MODEL DOES NOT DO: advance the driver's PRIVATE state (its drive-select and motor timers, its
     write-protect latches and last-access times, the scratch its sector transfers leave) — the media-change mode
     apart, which is the desk's to drive. A boot asks the driver nothing but Mediach and Rwabs.
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
A MACHINE WHOSE TRAP DOOR IS OURS TOO (band 5 wave 3: `ours_of(blob, door=)`, `desk_machine(ours=, door=)`) is that
boot with the same ONE takeover, made where the dispatcher first passes (the boot's first switchto `rte`), handed A
DOOR: the registry's pending declarations mapped beside the screen manager's entry — the GEM trap's vector, and the
first-entry frame of every loaded program, WALKED FROM THE MACHINE. Every accessory is then entered through our
gotopgm, traps into our handler and parks through our dispatcher; the desk stays the ROM's. WHO RAN is a cycle
profile (the ROM's door text: zero cycles from the lay on), the classes are per process, and a door the ROM took
back is refused by name. THE DOOR IS A PARAMETER, each part answered by the blob's own entry, found by symbol
(`src/aes/trapdoor.S`, `switch.S`, `gemdosif.S`, `gemstart.S`'s three, `irq.S`'s glues): Tier 3 hands
`aes_event.THE_DOOR` (the accessory machines' rows since the narrow door flip, the desk's own machine's since the
full flip — `aes_ctlmgr.our_machine`): the trap door's three AND, since the full flip, what the ROM's gem_entry and
gem_main stored by value before the takeover's stop — justretf's slot, the tick glue's two, the desk's trampoline
slot, the VDI's button and motion vectors — so that the scan finds, at a door machine's idle, no live longword
holding by value the ROM's copy of a routine the registry declares (`vet_no_entry_is_held_as_the_rom_s`: seventeen
routines, not every ROM routine — the section "THE SCAN" below). The prototype door the takeover was first proved with
(`test/acc/protodoor.S`) is retired: the shipped door gave the same machines.
THE THIRD CAPTURE (`seven_accessory_preinit`, `make preinit-acc7`): seven accessories in the drive, one more than
the loader takes — `seven_accessory_machine`. Its boot saturates the kit's write ledger, so no takeover is made of it
(refused by name); and a boot that stores at `$0..$7` — the ROM's shadow: a bus error on the machine — is refused.
A BOOTED MACHINE IS CONTINUED (`Machine.continued`) by what it receives at its idle — IKBD bytes through the ROM's
ACIA handler, the system timer's ticks through Timer C's — and its own run to the next idle, of whichever
dispatcher: how both shores' screen managers are held to DO the same when woken.
BAND 5 WAVE 4, THE ROM'S SIDE (`test_aes_boot_w4.py`): THE FOURTH CAPTURE (`inf_preinit`, `make preinit-inf`: the
blank disk plus the ROM's own default DESKTOP.INF — `inf_machine`, its `#E` line's pairs patched in the image);
`continued` AS FAR AS A DRIVE'S WINDOW (the device model above; the desk's user-block trampoline's arrivals
watched: `trampoline_stops`); THE SERVED DOOR (`served`: deskmain and the shell's built-ins answered AT THEIR ENTRY,
a labelled argument class — the one door here through which a routine is not run); THE OUR-BOOT MACHINE'S PREMISES
vetted against the ROM's own run (`vet_ours_can_be_laid_at_gem_entry`); and THE SCAN (`entries_held_by_value`,
`vet_no_entry_is_held_as_the_rom_s`): no longword holding, by value, the ROM's copy of a routine the registry declares.
THE OUR-BOOT MACHINE (band 5 wave 4, slice B; ruling W4-R1 — A LABELLED STAGING, said in the name of every row and
test that uses it): `booted(..., ours=, laid=AT_GEM_ENTRY)`, `our_desk_machine`, `our_inf_machine` — the pre-init
machine with THE BLOB LAID WHERE THE RUN STANDS BEFORE ITS FIRST INSTRUCTION and the run ENTERED AT THE BLOB'S OWN
gem_entry with the capture's whole register file. NOT ONE LONGWORD OF THE MACHINE IS MAPPED BY THE HARNESS: `$88`,
`$404`, the three routines gem_entry stores by value, the VDI's three vectors and the screen manager's entry are each
stored by OUR OWN RUN. "OURS BOOTED" IS CLAIMED TO deskmain's ENTRY AND NO FURTHER (ruling W4-R3: from there the desk —
the ROM's — calls the ROM's AES through the ROM's Line-F table on both shores): WHO RAN is cut there (`OurBoot.ran`: a
cycle profile — the ROM's GEM text and the Line-F handler's copy ZERO cycles, or the boot is refused by name), and
what the machine differs from the ROM-booted one in, checkpoint by checkpoint, is `aes_ourboot.py`'s.

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
import contextlib
import ctypes
import functools
import hashlib
import operator
import random
import struct
from collections import namedtuple
from pathlib import Path

import derived
from harness import BASE_IMAGE, addrs, emu, make_image
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
import staging
import test_bios_bconout as bconout
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


def registers_at_the_stop(names):
    """The registers `names` of the CPU where a bench run stands stopped (a watch's `stopped`: the kit's loop hands a
    watch the PC, A7 and the memory, and the oracle's CPU holds the rest): `{name: value}`."""
    return {name: _register(name) for name in names}


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
FIRST_ACCESSORY_BASEPAGE = 0x9724       # long: where sndcli parks the FIRST accessory's basepage ($fe4358)
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


# ---- THE FLOPPY, AT THE DRIVER'S ENTRIES -----------------------------------------------------------------------------------
# Each call as the BIOS dispatcher's `jsr` leaves it: the return address at (sp), the function's arguments above it.
GETBPB, MEDIACH, RWABS, FLOPRD = "Getbpb", "Mediach", "Rwabs", "Floprd"
DEVICE_AT = 4                           # Getbpb's and Mediach's one argument
RWABS_FLAG_AT, RWABS_BUFFER_AT, RWABS_COUNT_AT, RWABS_RECORD_AT, RWABS_DEVICE_AT = 4, 6, 10, 12, 14
RWABS_WRITE = 1
# THE FOURTH ENTRY (band 5 wave 4, ruling W4-R8: what a drive's window needs): XBIOS Floprd, which the desk asks FOR
# ITSELF before it opens a drive ($fe1b46: the boot sector read into a block of its own, `eralert` on an error) —
# under the three vectors, straight to the driver's own routine, whose FDC transactions are out of the model's reach
# as the others' are. Its entry is read out of the XBIOS dispatcher's table as the machine's own trap vector names
# it (`_xbios_entry`); its frame is the dispatcher's `jsr`'s: (buffer, a filler long, device, sector, track, side, count).
XBIOS_FLOPRD = 8
LEA_PC_RELATIVE_A0 = 0x41fa             # the dispatcher's first instruction: `lea <its table>(pc),a0`
TABLE_ENTRY_INDIRECT = 0x80000000       # of a dispatcher's table entry: the routine is the longword it names (a RAM vector)
FLOPRD_BUFFER_AT, FLOPRD_DEVICE_AT, FLOPRD_SECTOR_AT, FLOPRD_TRACK_AT, FLOPRD_SIDE_AT, FLOPRD_COUNT_AT = 4, 12, 14, 16, 18, 20
# ...and THE DRIVE'S MEDIA-CHANGE MODE, the one byte of the driver's own state the desk DRIVES: after that read it
# calls `Rwabs(0, NULL, 2, 0, drive)` ($fe1bb0) — a NULL buffer is no transfer: the ROM's Rwabs stores the COUNT as
# the drive's mode ($fc12e2) and answers 0 — so that GEMDOS's next Mediach answers CHANGED and its Getbpb logs the
# disk in again. Where the modes lie is read out of that instruction.
FLOPPY_MODE_LOAD = 0xfc12e6             # Rwabs's `movea.l #<the modes>,a1`, the drive number then added
MOVEA_L_IMMEDIATE_A1 = 0x227c
MEDIA_UNCHANGED, MEDIA_CHANGED = addrs.MEDIACH_UNCHANGED, addrs.MEDIACH_CHANGED
# The nine words of a BPB, from a boot sector (little-endian, `st_build`'s offsets): what the ROM's Getbpb computed
# when it logged the disk in, and what its record for the drive must hold for the disk served to be that disk.
BOOT_SECTOR_BPB = struct.Struct("<HBHBHHBHH")       # bytes/sector, sectors/cluster, reserved, FATs, root entries,
BPB_WORDS = struct.Struct(">9H")                    # sectors, media, sectors/FAT, sectors/track
FAT12_FLAGS = 0
FLOPPY_RECORD_SERIAL = 28               # the driver's record: the boot sector's three serial bytes ($fc1130)
# ...and the five words Getbpb lays between the two ($fc10de..$fc111a): tracks, sides, sectors a cylinder, sectors a
# track, hidden sectors — off the boot sector's geometry words (sectors a track, sides, hidden), after its BPB's.
BOOT_SECTOR_GEOMETRY = struct.Struct("<3H")
BOOT_SECTOR_GEOMETRY_AT = st_build.BPB_AT + 13
RECORD_GEOMETRY = struct.Struct(">5H")
FLOPPY_RECORD_GEOMETRY = 18
FLOPPY_BOOT_SECTOR_BUFFER_LOAD = 0xfc112a           # ...copied out of its boot-sector buffer: `adda.l #<buffer>,a1`
ADDA_L_IMMEDIATE_A1 = 0xd3fc
# ...and of a record, the words its Getbpb lays (`$fc1070..$fc111a`, `$fc1130`): the BPB's first EIGHT — its ninth,
# the flags, it leaves as it was — then the geometry and the serial.
FLOPPY_RECORD_FLAGS = 16

# ---- THE DEVICES OF BAND 6 WAVE 4 (ruling W6-R9: DECLARED AT THE DRIVER'S ENTRIES, NOT POKED) ---------------------------------
# Each answers what no hardware here does, and says so: the CLASS it answers in is named in every `Boot` whose run it
# answered (`Boot.devices`), never silently.
#   * THE FORMATTER: XBIOS Flopfmt and Flopwr, two more entries of the ROM's floppy driver served where Floprd is (the
#     desk's File > Format and its disk copy ask them FOR THEMSELVES, under the three vectors). What they reach below
#     those entries — the PSG's register 14 (the drive's select, `$fc1e60`) and the MFP's `$fffa01` (the FDC's done
#     line, `$fc1a92`) — is the FDC's transaction, which no declaration serves: they are answered at the entry, as
#     Floprd is, and nothing of the two is read.
#   * DRIVE B: — THE ROM'S OWN TWO-DRIVE PATH. The capture's machine counts TWO floppies (`_nflops`, read in place:
#     the driver's one-drive swap, `$fc1ebe`, is not taken) and its drive B: was never LOGGED IN (its record all
#     zeros — the boot did touch drive 1: its access time `$9fc + 4` is stamped on every capture); a machine made with a
#     disk in it (`with_a_disk_in_drive_b`) answers Getbpb, Floprd and Flopwr of drive 1 off a second image.
#   * THE PRINTER — ON A MACHINE MADE WITH ONE (`with_a_printer_on_line`, `Boot.printer`; every other machine's
#     GPIP is declared by nothing, and a run that reads it is refused by the kit, by name). The BIOS's printer driver
#     (`$fc2090`) runs as the ROM's — its five-second hold-off, its BUSY poll — over the MFP's GPIP DECLARED with
#     BUSY clear (a printer on line). What it reaches past that poll, the PSG transaction that hands the port one byte
#     (port B made an output, the byte on it, the strobe pulsed low twice and high once: `$fc20cc..$fc20f4`), is
#     answered at its first instruction as the FDC's are at the driver's entries: the byte kept in the run's ledger
#     (`Boot.printed`), the driver's own answer (sent) handed back — and EVERY GPIP read of the run must be such a
#     poll, one a byte, or the run is refused by name (`devices_answered`: the RS232 handshake, the monitor detect
#     and the FDC's done line read the same byte). WHY NOT THE PSG DECLARED TOO, MEASURED: fourteen accesses of the
#     chip a byte (the reviewer's run of the ROM's own transaction) — the DESKTOP.INF's print overflows the kit's PSG
#     ledger (4,096 events) and the run is refused by name. What the skipped transaction leaves unlike the ROM's: D1
#     and D2 (`$ffffff8f`, `$20` there; the model leaves them as entered — scratch to the trap's caller).
THE_FORMATTER = "W6-R9 THE FORMATTER: XBIOS Flopfmt / Flopwr answered at the driver's entries (no FDC here)"
DRIVE_B = "W6-R9 DRIVE B: a second disk, in the drive the capture's machine never logged in"
THE_PRINTER = "W6-R9 THE PRINTER: a printer on line at the parallel port (no printer here)"
FLOPWR, FLOPFMT = "Flopwr", "Flopfmt"
# THE PARALLEL PORT'S BUSY LINE, as a machine with a printer on line is served it: the GPIP with every line high but
# BUSY (`test_bios_bconout.py`'s declaration of a ready printer: one for the tree). A run that never polls it reads none.
THE_PRINTER_S_PORT = {"hw_seed": {addrs.MFP_GPIP: bconout.GPIP_READY}}
PRINTER_SEND = 0xfc20cc                 # `move.w sr,d3`: the transaction's first instruction, BUSY seen clear
PRINTER_CHARACTER_AT = 6                # Bconout's character, as the driver reads it (`$fc20e4`: `move.w 6(sp),d0`)
XBIOS_FLOPWR, XBIOS_FLOPFMT = 9, 10
DRIVE_B_DEVICE = DRIVE_A + 1
# Flopfmt's frame as the dispatcher's `jsr` leaves it (`$fc1930..$fc1942`, the shared prologue `$fc1c48`): the
# buffer, the skew table, the device, sectors a track, the track, the side, the interleave, the magic, the virgin word.
(FLOPFMT_BUFFER_AT, FLOPFMT_SKEW_AT, FLOPFMT_DEVICE_AT, FLOPFMT_SECTORS_AT, FLOPFMT_TRACK_AT, FLOPFMT_SIDE_AT,
 FLOPFMT_INTERLEAVE_AT, FLOPFMT_MAGIC_AT, FLOPFMT_VIRGIN_AT) = 4, 8, 12, 14, 16, 18, 20, 22, 26
FLOPFMT_MAGIC = 0x87654321              # `$fc1916`'s `cmpi.l`: any other is an error before the FDC is touched
FLOPFMT_MAGIC_CHECK_AT = 0xfc1916
# THE TRACK THE ROM'S FLOPFMT LAYS IN THE CALLER'S BUFFER before it writes it (`$fc198c`; held to the ROM's own run of
# that code by the battery): each run a byte repeated, a sector's ID and data fields between.
TRACK_GAP_BYTE, TRACK_SYNC_ZERO, TRACK_SYNC_MARK = 0x4e, 0x00, 0xf5
TRACK_LEAD_IN, TRACK_SYNC_ZEROS, TRACK_SYNC_MARKS, TRACK_ID_GAP, TRACK_SECTOR_GAP, TRACK_LEAD_OUT = 60, 12, 3, 22, 40, 1401
ID_ADDRESS_MARK, DATA_ADDRESS_MARK, CRC_WRITE = 0xfe, 0xfb, 0xf7
SECTOR_SIZE_CODE = 2                    # 512 bytes
# ...and what its verify (`$fc1afe`) then leaves there: each sector read into the buffer's SECOND 512 bytes, and the
# list of the sectors that failed at its head, ended by a zero word — for a track that verified, the zero alone.
VERIFY_READS_AT = st_build.SECTOR_BYTES
BAD_SECTORS_END = bytes(WORD_BYTES)
# A FLOPWR OF THE BOOT SECTOR (sector 1 of track 0, side 0) MARKS THE DRIVE CHANGED, as Flopfmt marks it before it
# formats (`$fc1862..$fc1874`, `$fc194a`: `moveq #2,d0; bsr` the mode store `$fc1ef6`).
FLOPWR_MARKS_THE_BOOT_SECTOR_AT, FLOPFMT_MARKS_THE_DRIVE_AT, THE_MODE_STORE = 0xfc1862, 0xfc1948, 0xfc1ef6
# THE ROM'S RWABS ASKS NO MEDIA CHANGE OF A CALL WHOSE FLAG IS 2 OR MORE (`$fc12f8`: `cmpi.w #2,8(a6); bge`) — the
# format's own writes of the FAT and the root (flag 3) while the drive is held CHANGED; OF ANY OTHER, a drive held
# CHANGED answers E_CHNG and transfers nothing (`$fc11e4`'s Mediach is 2: `$fc1316`), the mode left as it is — GEMDOS's
# first read after the format, which then logs the disk in again.
RWABS_NO_MEDIA_CHECK = 2
RWABS_NO_MEDIA_CHECK_AT = 0xfc12f8
# ...and maps a record to (track, side, sector) through the drive's RECORD (`$fc1394..$fc13b6`): its sectors a
# cylinder and a track — the disk's own geometry, which a single-sided disk lays on the medium's first side.
FLOPPY_RECORD_CYLINDER_SECTORS, FLOPPY_RECORD_TRACK_SECTORS = 22, 24
# ...and VERIFIES EACH WRITE where `_fverify` is set (`$fc1426`: `tst.w $444`; every capture's is): Flopver
# (`$fc1ae2`) of the sectors just written into the driver's own buffer (`$fc143c`: `move.l #$16da,-(sp)`), which
# leaves what Flopfmt's verify leaves in its buffer (`VERIFY_READS_AT`, `BAD_SECTORS_END`): each sector read into the
# buffer's second 512 bytes — the transfer's last record there at the end — and the bad-sector list's end, the zero
# word, at its head (`$fc1714` reads it: none, so no -16).
SYSVAR_FVERIFY = 0x444
RWABS_VERIFY_AT, RWABS_VERIFY_BUFFER = 0xfc1426, 0x16da

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


def driver_mode(memory):
    """...and the byte the driver keeps drive A:'s media-change mode in — read out of Rwabs's own instruction."""
    return _operand_of(memory, FLOPPY_MODE_LOAD, MOVEA_L_IMMEDIATE_A1, "its media-change modes") + DRIVE_A


def geometry_of(boot_sector):
    """A floppy's `(sectors, sectors a track, sides, hidden sectors)`, off its boot sector."""
    sectors = BOOT_SECTOR_BPB.unpack_from(boot_sector, st_build.BPB_AT)[5]
    return (sectors, *BOOT_SECTOR_GEOMETRY.unpack_from(boot_sector, BOOT_SECTOR_GEOMETRY_AT))


def record_geometry_of(boot_sector):
    """The five words the ROM's Getbpb lays after a drive's BPB ($fc10de..$fc111a), of a floppy's boot sector:
    tracks, sides, sectors a cylinder, sectors a track, hidden sectors."""
    sectors, track_sectors, sides, hidden = geometry_of(boot_sector)
    cylinder_sectors = track_sectors * sides
    return RECORD_GEOMETRY.pack(sectors // cylinder_sectors, sides, cylinder_sectors, track_sectors, hidden)


def _xbios_entry(memory, function):
    """The routine the machine's own XBIOS dispatcher enters for `function`: its table found through the trap's
    vector and the handler's first instruction (`lea <table>(pc),a0`: a word, how many functions, then a longword
    each) — REFUSED BY NAME where the vector names no such handler or the entry is not a routine of the ROM."""
    handler = case.long_in(memory, addrs.VECTOR_TRAP_XBIOS) & BUS
    opcode, displacement = struct.unpack_from(">Hh", memory, handler)
    table = handler + WORD_BYTES + displacement
    if opcode != LEA_PC_RELATIVE_A0 or handler < emu.ROM_BASE or case.word_in(memory, table) <= function:
        raise Refused(f"this machine's XBIOS vector ({handler:#x}) does not name the ROM's dispatcher with a table of "
                      f"more than {function} functions: the model stands in for the ROM's floppy driver and no other")
    entry = case.long_in(memory, table + WORD_BYTES + function * LONG_BYTES)
    if entry & TABLE_ENTRY_INDIRECT or entry < emu.ROM_BASE:
        raise Refused(f"XBIOS function {function} of this machine is not a routine of the ROM ({entry:#x})")
    return entry


def virgin_sector(virgin):
    """A formatted sector's 512 bytes: the virgin word over (`$fc1a10`: `move.b` its two bytes, 256 times)."""
    return virgin.to_bytes(WORD_BYTES, "big") * (st_build.SECTOR_BYTES // WORD_BYTES)


def track_laid(track, side, order, virgin):
    """THE TRACK THE ROM'S FLOPFMT LAYS IN ITS BUFFER (`$fc198c`) for `track` of `side`, its sectors numbered in
    `order` (the skew table's), each data field the `virgin` word over: the lead-in, then per sector its ID field
    (sync, the mark, track, side, sector, the size code, the CRC's write byte) and its data field, then the lead-out."""
    def run(byte, count):
        return bytes((byte,)) * count

    sync = run(TRACK_SYNC_ZERO, TRACK_SYNC_ZEROS) + run(TRACK_SYNC_MARK, TRACK_SYNC_MARKS)
    data = virgin_sector(virgin)
    sectors = (sync + bytes((ID_ADDRESS_MARK, track & aes.BYTE_MASK, side & aes.BYTE_MASK, sector, SECTOR_SIZE_CODE, CRC_WRITE))
               + run(TRACK_GAP_BYTE, TRACK_ID_GAP) + sync + bytes((DATA_ADDRESS_MARK,)) + data + bytes((CRC_WRITE,))
               + run(TRACK_GAP_BYTE, TRACK_SECTOR_GAP) for sector in order)
    return run(TRACK_GAP_BYTE, TRACK_LEAD_IN) + b"".join(sectors) + run(TRACK_GAP_BYTE, TRACK_LEAD_OUT)


def record_spans(disk):
    """`((offset, bytes), ...)` THE ROM'S GETBPB WRITES INTO A DRIVE'S RECORD of a floppy's boot sector: the BPB's
    first eight words, then the geometry and the serial (the flags word between is the driver's, untouched)."""
    return ((0, bpb_of(disk)[:FLOPPY_RECORD_FLAGS]),
            (FLOPPY_RECORD_GEOMETRY, record_geometry_of(disk) + accessory_disk.serial_of(disk)))


class Floppy:
    """Drive A: as the entries of the machine's own driver answer for it (the module's docstring): `disk` a 720 KB
    image held off the machine — THE DISK THE MACHINE BOOTED WITH, or the model is refused: the driver's record
    must hold its BPB, its geometry and its serial. `calls`: every call made, in order. AND WAVE 4's DEVICES (above,
    W6-R9): the formatter's two entries (`formatter`), and `drive_b` — a second image in drive B:, or None (no image:
    the drive as the capture left it, never logged in) — each class of answer a run was given kept in `labelled`."""

    def __init__(self, memory, disk, drive_b=None):
        self._memory, self.disk, self.calls, self._laid = memory, bytearray(disk), [], []
        self.drive_b, self.labelled = None if drive_b is None else bytearray(drive_b), set()
        vectors = {GETBPB: addrs.HDV_BPB, MEDIACH: addrs.HDV_MEDIACH, RWABS: addrs.HDV_RWABS}
        self.entries = {case.long_in(memory, vector) & BUS: function for function, vector in vectors.items()}
        self.entries[_xbios_entry(memory, XBIOS_FLOPRD)] = FLOPRD
        outside = [f"{function} at {entry:#x}" for entry, function in self.entries.items() if entry < emu.ROM_BASE]
        if len(self.entries) != len(vectors) + 1 or outside:
            raise Refused(f"this machine's three disk vectors and its XBIOS Floprd do not name four routines of the ROM "
                          f"({outside}): the model stands in for the ROM's floppy driver and for no other")
        self.formatter = {_xbios_entry(memory, XBIOS_FLOPWR): FLOPWR, _xbios_entry(memory, XBIOS_FLOPFMT): FLOPFMT}
        self.record, self._mode_at = driver_record(memory), driver_mode(memory)
        self._vet_it_is_the_disk_the_machine_logged_in()
        if self.drive_b is not None:
            self._vet_drive_b_holds_its_own_disk()

    def held_in_b(self):
        """The image in drive B: as the run leaves it — None where the drive is empty."""
        return None if self.drive_b is None else bytes(self.drive_b)

    @property
    def served_at(self):
        """`{entry: function}` of every routine of the driver the model answers: the four, and the formatter's two."""
        return {**self.entries, **self.formatter}

    def _record_of(self, device):
        return self.record + (device - DRIVE_A) * FLOPPY_BPB_RECORD_BYTES

    def _mode_of(self, device):
        return self._mode_at + device - DRIVE_A

    def _vet_drive_b_holds_its_own_disk(self):
        """DRIVE B:'s RECORD IS ITS DISK'S — or none (never logged in: the capture's), or one the driver holds CHANGED
        (a boot sector written since: its next Getbpb logs the disk in again) — or the model is refused by name."""
        record = self._record_of(DRIVE_B_DEVICE)
        held = bytes(self._memory[record:record + FLOPPY_RECORD_SERIAL + st_build.BOOT_SERIAL_BYTES])
        if not any(held) or self._memory[self._mode_of(DRIVE_B_DEVICE)] == MEDIA_CHANGED:
            return
        if any(held[at:at + len(data)] != data for at, data in record_spans(self.drive_b)):
            raise Refused(f"drive B:'s record ({held.hex()}) is not the disk in it: the model swaps none in")

    def _vet_it_is_the_disk_the_machine_logged_in(self):
        held = bytes(self._memory[self.record:self.record + BPB_WORDS.size])
        geometry_at, serial_at = self.record + FLOPPY_RECORD_GEOMETRY, self.record + FLOPPY_RECORD_SERIAL
        geometry = bytes(self._memory[geometry_at:geometry_at + RECORD_GEOMETRY.size])
        serial = bytes(self._memory[serial_at:serial_at + st_build.BOOT_SERIAL_BYTES])
        if held != bpb_of(self.disk) or geometry != record_geometry_of(self.disk):
            raise Refused(f"the disk's boot sector says another geometry ({bpb_of(self.disk).hex()} "
                          f"{record_geometry_of(self.disk).hex()}) than the driver's record for drive A: holds "
                          f"({held.hex()} {geometry.hex()})")
        if serial != accessory_disk.serial_of(self.disk):
            raise Refused(f"the disk's serial ({accessory_disk.serial_of(self.disk).hex()}) is not the one the driver "
                          f"logged in ({serial.hex()}): this machine booted with another disk — GEMDOS's cache is that "
                          f"disk's, and the model swaps none in")

    def _word(self, at):
        return case.word_in(self._memory, at)

    def _drive_a(self, function, device):
        if device != DRIVE_A:
            raise Refused(f"{function} of drive {device}: the model holds drive A: alone")

    def _disk_of(self, function, device):
        """The image in drive `device`: A:'s, or B:'s where the machine was made with one there (labelled) — refused by
        name for any other drive, and for B: where it holds none."""
        if device == DRIVE_B_DEVICE and self.drive_b is not None:
            self.labelled.add(DRIVE_B)
            return self.drive_b
        self._drive_a(function, device)
        return self.disk

    def _lay(self, at, data):
        """The harness's own store into the machine, in the driver's place: made, and kept for the run's ledger."""
        self._memory[at:at + len(data)] = data
        self._laid.append((at, bytes(data)))

    def laid_by_the_last_call(self):
        """What the call just served stored into the machine, `((address, bytes), ...)` — handed over once."""
        laid, self._laid = tuple(self._laid), []
        return laid

    def changed(self):
        """Does the driver's own mode byte say the disk CHANGED (the desk's forced change, until the next Getbpb)?"""
        return self._memory[self._mode_at] == MEDIA_CHANGED

    def served(self, entry, sp):
        """The call the run stands at the entry of, answered: `(D0, the return address)`."""
        answer = getattr(self, f"_{self.served_at[entry].lower()}")(sp)
        return answer, case.long_in(self._memory, sp) & BUS

    def _getbpb(self, sp):
        """THE ROM'S GETBPB OF THE DISK IN THE DRIVE: it reads the boot sector into its buffer again, rewrites the
        drive's record off it (`record_spans`) and ends any change. For the disk the machine logged in the record's
        bytes are the ones it holds and are not laid again — the desk's forced change of A:, GEMDOS's Mediach answered
        so, and the disk copy's own Getbpb of its source; a disk the formatter rewrote, or drive B:'s first, is logged
        in. (It leaves the mode MAYBE where the drive's write-protect latch is set — a byte of the capture's mask this
        model does not read: UNCHANGED is stored, and a latched drive's next transfer would compare the serial and
        find the same disk.)"""
        device = self._word(sp + DEVICE_AT)
        disk, record = self._disk_of(GETBPB, device), self._record_of(device)
        for at, data in record_spans(disk):
            if bytes(self._memory[record + at:record + at + len(data)]) != data:
                self._lay(record + at, data)
        self._lay(driver_boot_sector(self._memory), disk[:st_build.SECTOR_BYTES])
        self._lay(self._mode_of(device), bytes((MEDIA_UNCHANGED,)))
        self.calls.append(Call(GETBPB, (device,), record))
        return record

    def _mediach(self, sp):
        """UNCHANGED — but CHANGED while the driver's mode byte says so, as the ROM's answers it first ($fc119a)."""
        self._drive_a(MEDIACH, self._word(sp + DEVICE_AT))
        answer = MEDIA_CHANGED if self.changed() else MEDIA_UNCHANGED
        self.calls.append(Call(MEDIACH, (DRIVE_A,), answer))
        return answer

    def _medium_at(self, track, side, sector):
        """Where (track, side, sector) lies in an image: the medium's own order — 80 tracks of two sides of nine."""
        return ((track * st_build.HEADS + side) * st_build.SECTORS_PER_TRACK + sector - 1) * st_build.SECTOR_BYTES

    def _records_at(self, record, count):
        """Where Rwabs's `count` records from `record` lie on drive A:'s medium, as the ROM's maps them: through the
        drive's RECORD — its sectors a cylinder and a track (`$fc1394..$fc13b6`)."""
        cylinder = self._word(self.record + FLOPPY_RECORD_CYLINDER_SECTORS)
        track_sectors = self._word(self.record + FLOPPY_RECORD_TRACK_SECTORS)
        at = []
        for each in range(record, record + count):
            track, in_the_cylinder = divmod(each, cylinder)
            side, sector = divmod(in_the_cylinder, track_sectors)
            at.append(self._medium_at(track, side, sector + 1))
        return at

    def _lay_the_verify(self, last_record):
        """What the ROM's Rwabs's verify of a write leaves in the driver's buffer (`RWABS_VERIFY_BUFFER`): the last
        record read back at its second 512 bytes, the bad-sector list's end at its head."""
        self._lay(RWABS_VERIFY_BUFFER + VERIFY_READS_AT, last_record)
        self._lay(RWABS_VERIFY_BUFFER, BAD_SECTORS_END)

    def _rwabs(self, sp):
        flag, count, record = (self._word(sp + at) for at in (RWABS_FLAG_AT, RWABS_COUNT_AT, RWABS_RECORD_AT))
        buffer = case.long_in(self._memory, sp + RWABS_BUFFER_AT) & BUS
        self._drive_a(RWABS, self._word(sp + RWABS_DEVICE_AT))
        if not buffer:
            return self._mode_set(flag, count, record)
        if self.changed() and flag < RWABS_NO_MEDIA_CHECK:
            self.calls.append(Call(RWABS, (flag, buffer, count, record, DRIVE_A), addrs.E_CHNG_LONG))
            return addrs.E_CHNG_LONG
        sector_bytes, size = st_build.SECTOR_BYTES, count * st_build.SECTOR_BYTES
        at = self._records_at(record, count)
        if any(each + sector_bytes > len(self.disk) for each in at) or buffer + size > RAM_BYTES:
            raise Refused(f"Rwabs of {count} sector(s) at record {record} to {buffer:#x} leaves the disk or the RAM")
        if flag & RWABS_WRITE:
            for nth, each in enumerate(at):
                self.disk[each:each + sector_bytes] = self._memory[buffer + nth * sector_bytes:buffer + (nth + 1) * sector_bytes]
            if at and self._word(SYSVAR_FVERIFY):
                self._lay_the_verify(self.disk[at[-1]:at[-1] + sector_bytes])
        else:
            self._lay(buffer, b"".join(self.disk[each:each + sector_bytes] for each in at))
        self.calls.append(Call(RWABS, (flag, buffer, count, record, DRIVE_A), 0))
        return 0

    def _mode_set(self, flag, mode, record):
        """Rwabs OF NO BUFFER: no transfer — the count is the drive's new media-change mode, stored where the
        driver keeps it. THE FORCED CHANGE ALONE is served (the desk's, before it opens a drive)."""
        if mode != MEDIA_CHANGED:
            raise Refused(f"Rwabs of no buffer with the count {mode}: the ROM's stores it as the drive's media-change "
                          f"mode, and the model serves the forced change ({MEDIA_CHANGED}) alone")
        self._lay(self._mode_at, bytes((mode,)))
        self.calls.append(Call(RWABS, (flag, 0, mode, record, DRIVE_A), 0))
        return 0

    def _sectors_asked(self, function, sp):
        """Floprd's and Flopwr's one frame, read and vetted: `(buffer, device, sector, track, side, count, the
        image, where on it)` — REFUSED BY NAME off the track (a sector past the ninth), off the medium, past the RAM."""
        buffer = case.long_in(self._memory, sp + FLOPRD_BUFFER_AT) & BUS
        device, sector, track, side, count = (self._word(sp + at) for at in (
            FLOPRD_DEVICE_AT, FLOPRD_SECTOR_AT, FLOPRD_TRACK_AT, FLOPRD_SIDE_AT, FLOPRD_COUNT_AT))
        disk = self._disk_of(function, device)
        size = count * st_build.SECTOR_BYTES
        on_the_track = 1 <= sector and 1 <= count and sector - 1 + count <= st_build.SECTORS_PER_TRACK
        if (not on_the_track or side >= st_build.HEADS or track >= st_build.TRACKS or not buffer
                or buffer + size > RAM_BYTES):
            raise Refused(f"{function} of {count} sector(s) from sector {sector} of track {track}, side {side}, to "
                          f"{buffer:#x} leaves the track, the disk or the RAM")
        return buffer, device, sector, track, side, count, disk, self._medium_at(track, side, sector)

    def _floprd(self, sp):
        """XBIOS Floprd: `count` sectors of one track's one side, copied to the caller's buffer. (The ROM's own
        prologue — which disk a single drive holds, the drive's lock and select — is the driver's private state.)"""
        buffer, device, sector, track, side, count, disk, at = self._sectors_asked(FLOPRD, sp)
        self._lay(buffer, disk[at:at + count * st_build.SECTOR_BYTES])
        self.calls.append(Call(FLOPRD, (buffer, device, sector, track, side, count), 0))
        return 0

    def _flopwr(self, sp):
        """XBIOS Flopwr (THE FORMATTER's): `count` sectors of the caller's buffer written to one track's one side —
        and a write that begins at the boot sector marks the drive CHANGED, as the ROM's does before its FDC is
        touched."""
        buffer, device, sector, track, side, count, disk, at = self._sectors_asked(FLOPWR, sp)
        disk[at:at + count * st_build.SECTOR_BYTES] = self._memory[buffer:buffer + count * st_build.SECTOR_BYTES]
        if (sector - 1) | track | side == 0:
            self._lay(self._mode_of(device), bytes((MEDIA_CHANGED,)))
        self.labelled.add(THE_FORMATTER)
        self.calls.append(Call(FLOPWR, (buffer, device, sector, track, side, count), 0))
        return 0

    def _flopfmt(self, sp):
        """XBIOS Flopfmt (THE FORMATTER's): one side of one track formatted in the skew table's order, its sectors
        the virgin word over — the drive marked CHANGED first, as the ROM's marks it — and the caller's buffer left
        as the ROM's leaves it: the track it laid (`track_laid`), then its verify's — the sectors read back one by
        one into the second 512 bytes (the last one's there), the bad-sector list at the head (none: the zero alone).
        REFUSED BY NAME: another magic, an interleave (the desk hands the skew table, -1), another track than the
        medium's nine sectors, a skew table that is not those nine, a track past the medium, a buffer past the RAM."""
        memory = self._memory
        buffer, skew = (case.long_in(memory, sp + at) & BUS for at in (FLOPFMT_BUFFER_AT, FLOPFMT_SKEW_AT))
        device, sectors, track, side, interleave, virgin = (self._word(sp + at) for at in (
            FLOPFMT_DEVICE_AT, FLOPFMT_SECTORS_AT, FLOPFMT_TRACK_AT, FLOPFMT_SIDE_AT, FLOPFMT_INTERLEAVE_AT,
            FLOPFMT_VIRGIN_AT))
        magic = case.long_in(memory, sp + FLOPFMT_MAGIC_AT)
        disk = self._disk_of(FLOPFMT, device)
        order = [self._word(skew + nth * WORD_BYTES) for nth in range(sectors)]
        laid = bytearray(track_laid(track, side, order, virgin))
        if (magic != FLOPFMT_MAGIC or aes.signed(interleave) >= 0 or sectors != st_build.SECTORS_PER_TRACK
                or sorted(order) != list(range(1, sectors + 1)) or track >= st_build.TRACKS or side >= st_build.HEADS
                or buffer + len(laid) > RAM_BYTES):
            raise Refused(f"Flopfmt of track {track}, side {side} ({sectors} sectors {order}, interleave "
                          f"{aes.signed(interleave)}, magic {magic:#x}) into {buffer:#x}: the model formats the desk's "
                          f"track alone — nine sectors in a skew table's order, on the medium, the buffer in the RAM")
        self._lay(self._mode_of(device), bytes((MEDIA_CHANGED,)))
        data = virgin_sector(virgin)
        for sector in order:
            at = self._medium_at(track, side, sector)
            disk[at:at + st_build.SECTOR_BYTES] = data
        laid[VERIFY_READS_AT:VERIFY_READS_AT + st_build.SECTOR_BYTES] = data
        laid[:len(BAD_SECTORS_END)] = BAD_SECTORS_END
        self._lay(buffer, laid)
        self.labelled.add(THE_FORMATTER)
        self.calls.append(Call(FLOPFMT, (buffer, device, track, side), 0))
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
ONE_INSTRUCTION = 1                     # the segment a run leaves a stop by (`_Run._stepped_off`)
THE_ROM_S, OURS = "the ROM's", "ours"     # whose code a PC is, and whose dispatcher an idle is (`whose`)
Boot = namedtuple("Boot", "ram registers disk instructions cycles polls blanks floppy io_reads hardware_reads "
                          "hardware_writes stored bus_error_frame writes_truncated io idle takeover observed served "
                          "our_boot drive_b devices printed printer",
                  defaults=(None, THE_ROM_S, None, (), (), None, None, (), b"", False))
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
manager is ours, or None; `observed`: of a CONTINUED run (`continued`), the calls it was watched to make; `served`: THE
LABEL of a machine made through the served door (`served`: a `Served` for each routine answered at its entry, in
order) — empty for every machine a run of the ROM's own code alone made; `our_boot`: the `OurBoot` of a machine OUR
gem_entry booted (`laid=AT_GEM_ENTRY`: a labelled staging), or None. WAVE 4's DEVICES (W6-R9): `drive_b`, the image
in drive B: as the run left it (None: no image there — every capture's, whose drive B: was never logged in); `devices`, the CLASSES of answer the run
was given that no hardware here gives (`THE_FORMATTER`, `DRIVE_B`, `THE_PRINTER`), sorted; `printed`, the bytes it
handed the printer, in order (`PRINTER_SEND`); `printer`, whether the machine has a printer on line
(`with_a_printer_on_line`: its runs are served the GPIP and the port's transaction; False for every capture's)."""


def devices_answered(floppy, hardware_reads, printed):
    """The classes of answer the run was given that no hardware here gives: the floppy's (`Floppy.labelled`), and
    THE_PRINTER where it handed the printer a byte — REFUSED BY NAME unless every read of the MFP's GPIP was the
    printer driver's BUSY poll before a byte it handed (one a byte, BUSY seen clear): the ROM reads that byte elsewhere
    too (the RS232 handshake, the monitor detect, the FDC's done line), which the printer's declaration does not serve."""
    polls = sum(1 for at, _value in hardware_reads if at == addrs.MFP_GPIP)
    if polls != len(printed):
        raise Refused(f"the run read the MFP's GPIP ({addrs.MFP_GPIP:#x}) {polls} time(s) and handed the printer "
                      f"{len(printed)} byte(s): a GPIP read that is no BUSY poll of the printer's is served by no device here")
    return tuple(sorted(floppy.labelled | ({THE_PRINTER} if printed else set())))


def surfaced(floppy, hardware_reads, printed):
    """WHAT A RUN'S DEVICES LEFT, as a `Boot` carries it — `{"drive_b", "devices", "printed"}`, `devices_answered`'s
    refusal with it: EVERY run of this module's surfaces it, a continuation's, a served run's AND A BOOT'S (band 6
    slice H, owed since wave 4's: a boot's `Boot` took the defaults, and a GPIP read no device serves went unvetted)."""
    return {"drive_b": floppy.held_in_b(), "devices": devices_answered(floppy, hardware_reads, printed), "printed": bytes(printed)}


def blob_of(boot):
    """THE BLOB `boot`'s MACHINE HOLDS (an `Ours`): a takeover's, an our-boot's — None for a machine the ROM booted."""
    if boot.takeover is not None:
        return boot.takeover.ours
    return boot.our_boot.ours if boot.our_boot is not None else None


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


# ---- THE TAKEOVER: A BOOT WHOSE SCREEN MANAGER — AND, HANDED A DOOR, WHOSE TRAP DOOR — IS OURS ------------------------------
# THE ROM BOOTS, AND FROM THE FIRST PROCESS IT EVER ENTERS ON, OUR CODE STANDS IN THE ROM'S PLACE (band 5 wave 2: ctlmgr
# in C; wave 3, ruling W3-R2: the stop moved to where a loaded program can still be taken). ictlmgr hands pstart
# ctlmgr's address twice, and the machine keeps it in two longwords (`entry_slots`): the PD's p_ldaddr, and the PC of
# the frame psetup pushed on the new process's own stack — the frame switchto's `rte` pops when the dispatcher first
# enters it. THE TAKEOVER IS MADE AT THE BOOT'S FIRST switchto `rte` — a stop BY ADDRESS, never by a count: the
# dispatcher's first pass, which RESUMES THE BOOT'S OWN PROCESS (PD0, gem_main's: the one process that is not entered
# there) or enters the first process it ever runs, the screen manager's frame — and every loaded program's — still
# unpopped on its stack — and is two things, neither a poke of the CPU:
#   * THE BLOB IS LAID where every Tier 3 row lays it (`Ours`: its link address, in the harness's free window);
#   * THE REGISTRY'S MAPPING IS APPLIED (`aes_event.SCREEN_MANAGER_ENTRY`): each of the two slots, which holds the
#     ROM's ctlmgr, is given the blob's own entry — found BY SYMBOL in the blob's ELF. The ROM's `rte` then pops OUR
#     entry: no register is set, and the PC is the one the machine's own instruction loads.
# That the mapping is what OUR ictlmgr + pstart store is ictlmgr's own returning row (the flip's, at the arrival
# `booted(until=<ictlmgr>)`): so the takeover is a build's ictlmgr having run, and no stage of ours.
# WHY THERE AND NOT EARLIER: on the accessory boot `Pexec(3)` hands the loader the largest free block — the free
# window — and CLEARS it before any process first runs (measured: every byte of the blob's span stored before the
# stop, none after). `laid=FROM_THE_START` is that boot, kept as the RED it is.
# WHY THERE AND NOT LATER (wave 2's stop, the screen manager's own first entry — `AT_THE_SCREEN_MANAGER_S_ENTRY`, kept
# so that the two are held to make ONE MACHINE): on an accessory boot both accessories are entered, take their first
# `trap #2` and park INSIDE THE ROM'S aes_entry before the screen manager first runs — a process the ROM's gotopgm
# entered and the ROM's trap handler parked is the ROM's for as long as it lives.
# THE DOOR (`Ours.door`, of `ours_of(blob, door=)`; none by default): the registry's declarations (`aes_event.THE_DOOR`,
# or some of them) a takeover applies beside the screen manager's entry, each the same kind of mapping and nothing
# else —
#   * a LONGWORD OF THE MACHINE'S OWN (`aes_event.THE_MACHINE_S_VECTORS`: `$88`, `$404` — and, since the full flip,
#     justretf's slot, the tick glue's kept longword and the VDI's tick vector, its button and motion vectors, the
#     desk's trampoline slot): the longword must hold the ROM's routine (one the ROM has not stored yet, or has given
#     back, is refused by name) and is given the blob's;
#   * A LOADED PROGRAM'S FIRST-ENTRY FRAME (`aes_event.PROGRAM_ENTRY`): WALKED FROM THE MACHINE — every process whose
#     UDA's stack pointer names a frame holding the ROM's gotopgm, vetted never entered — and given the blob's.
# VETTED AT THE STOP, each refused by name (`_vet_the_boot_s_first_entry`, `_vet_never_entered`, `_vetted_slots`,
# `_vet_clear_where_the_blob_goes`): the process the `rte` enters, unless it is the boot's own resumed, is entered on
# the stack its own UDA names, every register switchto loaded out of its never-saved UDA zero; the screen manager is SCRENMGR, its frame the only thing
# on its stack (every byte below is zero, as gem_main's BSS left it), and so is each program's mapped; the screen
# manager's two slots are the registry's and hold the ROM's ctlmgr; nothing lies where the blob goes.
# VETTED WHERE THE BOOT ENDS (`_TakingOver.made`): the `rte` entered our entry on the stack's top; NOT ONE STORE of
# the rest of the boot landed in the blob's span (the write ledger from the lay on, and the sectors the harness laid),
# and its bytes are the blob's; p_ldaddr holds our entry; the screen manager stands PARKED IN OUR TEXT (`whose`) —
# and, of a door: EVERY PROGRAM MAPPED WAS ENTERED THROUGH OUR gotopgm, on its stack's top, and stands parked in our
# text; each vector STILL HOLDS OURS (the ROM's retake stores its own back at every sh_tographic: a door the ROM took
# back is refused by name, never silently lost); and WHO RAN — A CYCLE PROFILE, never a count of stops: from the lay
# on THE ROM'S TEXT OF EACH PART RAN ZERO CYCLES (`aes_event.ROM_TEXT_OF`), and our entry of each ran.
# WHERE A BOOT ENDS: at the first idle of WHICHEVER dispatcher — the ROM's (`IDLE_LOOP`) or the blob's own (its
# keyboard poll called from its idle: `Ours.poll`, `Ours.idle`). A process parks through the dispatcher of the build
# it runs: the desk through the ROM's, the screen manager — and, behind a door, every accessory — through ours; so
# the boot's last park decides, and `Boot.idle` says which.
ENTRY_SYMBOL = aes_event.SCREEN_MANAGER_ENTRY_SYMBOL
GEM_ENTRY_SYMBOL = "aes_rom_gem_entry"  # `src/aes/gemstart.S`: the build's own gem_entry, where an our-boot machine is entered
ROM_ENTRY = aes_event.SCREEN_MANAGER_ROM_ENTRY
OUR_POLL, OUR_IDLE = "aes_chkkbd", "aes_idle"       # the blob's dispatcher: its poll, and the idle that calls it
SCREEN_MANAGER_NAME = b"SCRENMGR"
FRAME_PC = aes_event.EXCEPTION_FRAME_PC              # an exception frame: the status word, then the PC
FRAME_BYTES = WORD_BYTES + LONG_BYTES
AT_THE_FIRST_ENTRY, FROM_THE_START = "at the boot's first switchto `rte`", "before the boot's first instruction"
AT_THE_SCREEN_MANAGER_S_ENTRY = "at the screen manager's first entry"       # wave 2's stop: kept, to be held equal
AT_GEM_ENTRY = "at gem_entry, before the boot's first instruction, the run entered at the blob's own"    # the our-boot machine's
# The handlers ctlmgr calls, each by its ROM entry and its frame there (two words): what a continued run is watched
# to call (`continued`) — on the blob at the entry of each one's C core (`routines.core_symbol`), a longword an
# argument, after the image pointer.
HANDLER_NAMES = ("AES_ROM_HCTL_BUTTON", "AES_ROM_HCTL_RECT")
HANDLER_WORDS = 2                       # (mx, my)

Ours = namedtuple("Ours", "base end image entry poll idle handlers rom door start", defaults=((), (), None))
Ours.__doc__ = """A blob AS A TAKEOVER READS IT (`ours_of`), by content — what a kept boot is keyed by: where it is
linked (`base`) and ends (`end`: its allocated span), its bytes (`image`), its `entry` (ENTRY_SYMBOL), its
dispatcher's `poll` and the `(start, end)` of the `idle` that calls it, `handlers`: `((the ROM's handler, its C
core's entry), ...)` — `rom`: `((address, bytes), ...)`, THE ROM DATA A LABELLED STAGING MAPS FOR THIS BLOB
(`restaged`: the VDI's opcode tables naming the blob's own handlers), laid over the ROM in every continuation —
and `door`: THE TRAP DOOR A TAKEOVER MAPS BESIDE THE SCREEN MANAGER'S ENTRY, a `DoorPart` each (none: the screen
manager alone is ours); `start`: the blob's own gem_entry (GEM_ENTRY_SYMBOL: where an our-boot machine is entered),
None for a build that links none."""
DoorPart = namedtuple("DoorPart", "what mapping")
DoorPart.__doc__ = """One declaration of the registry as a blob answers it: `what` (its `RelocatedCode.what`) and
`mapping` — `((the ROM's routine, the blob's own entry), ...)`, each entry found by symbol."""
Program = namedtuple("Program", "pd name stack slot")
Program.__doc__ = """A loaded program a door takeover took: its `pd`, its `name`, its `stack` span `(lo, top)` as the
stop found it (the end of its UDA's state block; the end of psetup's frame) and the `slot` its first-entry frame's
PC lay in."""
DoorTaken = namedtuple("DoorTaken", "vectors programs ran")
DoorTaken.__doc__ = """What a door takeover did: `vectors` — `{slot: (the ROM's handler found, ours laid)}`;
`programs` — a `Program` for each first-entry frame mapped; and `ran`, WHO RAN from the lay on, `{what: (cycles at
our entries' first instructions, cycles in the ROM's text of it)}` — the second zero, or the boot is refused."""
Takeover = namedtuple("Takeover", "ours process stack instructions slots cleared stored_after found laid door",
                      defaults=(None,))
Takeover.__doc__ = """What one boot's takeover did and found: `ours`; THE SCREEN MANAGER'S PD (`process`); its `stack`
span `(lo, top)` as the stop found it — from the end of the UDA's state block to the end of psetup's frame; how many
`instructions` the boot had run at the stop (a capture's own number: for a reader, never a stop); `slots` — `{slot:
(the ROM's entry found, ours laid)}`; `cleared`: how many stores the boot had made into the blob's span BEFORE the blob
was laid; `stored_after`: the addresses of the span stored at AFTER (none, or the boot is refused); `found`: `(the
digest of the megabyte as the stop found it, the registers there)`; `laid`: when the blob was; and `door`: the
`DoorTaken` of a takeover handed a door, else None."""


def _function_of(placed, symbol, blob, why):
    found = placed.get(symbol)
    if found is None or found.kind not in "Tt" or not blob.base <= found.start < blob.base + len(blob.blob):
        raise Refused(f"the blob {blob.elf} has no entry `{symbol}`: {why}")
    return found


def _door_of(placed, blob, door):
    """The declarations `door` (`(what, ((the ROM's routine, our symbol), ...))` each) as `blob` answers them: a
    `DoorPart` each — REFUSED BY NAME where the blob links no entry for a routine one of them names (a build before
    that routine was ported)."""
    return tuple(DoorPart(what, tuple((rom, _function_of(placed, symbol, blob, f"{what} cannot be mapped to this build").start)
                                      for rom, symbol in symbols)) for what, symbols in door)


@functools.cache
def _ours_at(elf, base, end, image, door=()):
    blob = namedtuple("Blob", "elf base blob")(elf, base, image)
    placed = {symbol.name: symbol for symbol in transcription.symbol_table(elf)}
    entry = _function_of(placed, ENTRY_SYMBOL, blob, "nothing of this build can be entered in the ROM's ctlmgr's place")
    poll = _function_of(placed, OUR_POLL, blob, "its dispatcher's idle has no poll to stop a boot at")
    idle = _function_of(placed, OUR_IDLE, blob, "its dispatcher has no idle to end a boot in")
    if idle.size is None:
        raise Refused(f"the blob {elf} does not size `{OUR_IDLE}`: a poll made from it cannot be told from ev_multi's")
    handlers = tuple((getattr(addrs, name), placed[routines.core_symbol(name)].start) for name in HANDLER_NAMES
                     if routines.core_symbol(name) in placed)
    start = placed.get(GEM_ENTRY_SYMBOL)
    return Ours(base, max(end, base + len(image)), image, entry.start, poll.start, (idle.start, idle.start + idle.size),
                handlers, door=_door_of(placed, blob, door), start=start.start if start is not None else None)


def ours_of(blob, door=()):
    """`blob` (a `RomBench`: the bench blob's or the shipped one's) AS A TAKEOVER READS IT: an `Ours` — its entry
    FOUND BY SYMBOL in its ELF, and REFUSED BY NAME where the blob has none. `door`: THE DOOR IS OURS TOO — the
    registry's declarations the takeover maps beside the screen manager's entry (`aes_event.THE_DOOR`'s seven since the
    full flip — the trap door's three, `GEM_TRAP_VECTOR`, `PROGRAM_ENTRY`, `CRITICAL_ERROR_VECTOR`; gem_entry's three
    by-value stores; the two glues — or some of them: a test's own door), each entry found by symbol or the blob
    refused."""
    declared = tuple((part.what, tuple(sorted(part.symbols.items()))) for part in door)
    return _ours_at(str(blob.elf), blob.base, blob.end, bytes(blob.blob), declared)


GOTOPGM_SYMBOL = aes_event.PROGRAM_ENTRY.symbols[addrs.AES_ROM_GOTOPGM]


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


def _vet_never_entered(memory, pd):
    """THE PROCESS `pd` HAS NEVER BEEN ENTERED — psetup's frame, at the stack pointer its UDA names, is the only thing
    on its stack (every byte below it zero), and resumes in supervisor state untraced — or it is refused by name:
    answers its stack span `(lo, top)`, the top the frame's end."""
    name, uda = _name_of(memory, pd), case.long_in(memory, pd + aes.PD_UDA) & BUS
    sp = case.long_in(memory, uda + aes.UDA_SUPER_SP) & BUS
    lo, status = uda + aes.UDA_STATE_BYTES, case.word_in(memory, sp)
    used = len(bytes(memory[lo:sp]).rstrip(b"\0"))
    if used:
        raise Refused(f"NOT THE FIRST ENTRY OF {name!r} (the PD at {pd:#x}): its stack holds something below the "
                      f"frame popped, up to {lo + used - 1:#x} — code has run on it")
    if not status & SR_SUPERVISOR or status & SR_TRACE:
        raise Refused(f"the frame switchto pops for {name!r} (the PD at {pd:#x}) holds the status word {status:#x}")
    return lo, sp + FRAME_BYTES


def _vet_the_boot_s_first_entry(memory, pd, sp, registers):
    """THE STOP IS A PROCESS'S FIRST ENTRY (above) — `memory` and the CPU's `registers` at switchto's `rte`, `pd` the
    process it enters, `sp` its stack pointer — or the boot is refused by name: entered on the stack its UDA names,
    never entered before (`_vet_never_entered`), every register switchto loaded out of its never-saved UDA zero.
    Answers the process's stack span `(lo, top)`."""
    name, uda = _name_of(memory, pd), case.long_in(memory, pd + aes.PD_UDA) & BUS
    if sp != case.long_in(memory, uda + aes.UDA_SUPER_SP) & BUS:
        raise Refused(f"{name!r} (the PD at {pd:#x}) is entered at SP {sp:#x}, not on the stack its UDA names")
    stack = _vet_never_entered(memory, pd)
    loaded = {name: registers[name] for name in (*preinit_snapshot.DATA_REGISTERS, *preinit_snapshot.ADDRESS_REGISTERS)
              if registers[name]}
    if loaded:
        raise Refused(f"NOT THE FIRST ENTRY OF {name!r} (the PD at {pd:#x}): switchto loaded {loaded} out of its UDA, "
                      f"which nothing has saved a context in yet")
    return stack


def _vet_the_screen_manager(memory, pd):
    """The process whose entry is mapped is SCRENMGR, never entered: its stack span `(lo, top)`."""
    name = _name_of(memory, pd)
    if name != SCREEN_MANAGER_NAME:
        raise Refused(f"the ROM's ctlmgr is the entry of the process {name!r} at {pd:#x}: not SCRENMGR")
    return _vet_never_entered(memory, pd)


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


def _declared(what):
    """The registry's declaration named `what` (`aes_event.RelocatedCode`)."""
    found, = [each for each in vars(aes_event).values() if isinstance(each, aes_event.RelocatedCode) and each.what == what]
    return found


def door_slots(memory, part):
    """WHERE THE MACHINE `memory` KEEPS what the door part `part` maps: `((pd or None, slot), ...)` — the vector's
    own longword (`aes_event.THE_MACHINE_S_VECTORS`: a declaration's other slots are a recorder's ledger's, no
    machine's), and, for one WALKED FROM THE MACHINE (`aes_event.SLOTS_WALKED_FROM_THE_MACHINE`: a loaded program's
    first-entry frame), each process's. A part that names neither is refused."""
    walked = aes_event.SLOTS_WALKED_FROM_THE_MACHINE.get(part.what)
    vectors = tuple((None, slot) for slot in aes_event.THE_MACHINE_S_VECTORS.get(part.what, ()))
    if not walked and not vectors:
        raise Refused(f"{part.what} names neither a vector of the machine nor a walk of it: nothing of a door to map")
    return (*vectors, *(walked(memory) if walked else ()))


def vet_the_door_stands(memory, ours, when):
    """EVERY VECTOR OF THE DOOR STILL HOLDS OURS over `memory` — or the machine is refused by name. The ROM puts its
    own handlers back (retake, `$fe3c84`: `move.l #$fe3ea6,$88` and crit_err through Setexc, at every sh_tographic;
    restore_trap2 and giveerr): a machine continued through one is the ROM's door again while it is called ours."""
    for part in ours.door:
        entries = dict(part.mapping)
        for pd, slot in door_slots(memory, part):
            held = case.long_in(memory, slot)
            if pd is None and held not in entries.values():
                raise Refused(
                    f"THE DOOR IS NO LONGER OURS {when}: {part.what} holds {held:#x}"
                    + (" — THE ROM'S OWN HANDLER, PUT BACK (retake, restore_trap2, giveerr)" if held in entries else "")
                    + f", not the blob's {[f'{entry:#x}' for entry in entries.values()]}")


def _cycles_at(entries):
    """The cycles the profile tallied at the first instruction of each of `entries`: it ran, or it did not."""
    return sum(emu.prof_cycles(entry, entry + WORD_BYTES) for entry in entries)


def _cycles_in(spans):
    return sum(emu.prof_cycles(lo, hi) for lo, hi in spans)


class _TakingOver:
    """ONE BOOT'S TAKEOVER (above), made where the run stops for it: `armed` the stops it asks for as it stands —
    switchto's `rte` until the takeover is made there, then each entry of ours a mapped frame is to pop (the next
    instruction of its `rte`: held to be where it lands — the screen manager's, and behind a door our gotopgm, once
    per program), then nothing."""

    def __init__(self, memory, ours, laid):
        self._memory, self.ours, self._laid = memory, ours, laid
        self.armed, self.taken, self.entered = frozenset({addrs.AES_ROM_SWITCHTO_RTE}), None, False
        self._mark, self._laid_by_the_harness = None, []
        self._programs_to_enter, self._tallied_at_the_lay = {}, {}
        if ours.door and laid != AT_THE_FIRST_ENTRY:
            raise Refused(f"a door is taken {AT_THE_FIRST_ENTRY} and nowhere else: laid {laid}, a program the ROM's "
                          f"gotopgm entered before the stop is the ROM's for as long as it lives")
        if laid == FROM_THE_START:      # the RED's (above): before the run's ledger begins
            memory[ours.base:ours.base + len(ours.image)] = ours.image
            self._mark = 0

    @property
    def profiled(self):
        """Is this boot's who-ran read off the cycle profile (a door's)?"""
        return bool(self.ours.door)

    def stopped(self, pc, sp, instructions):
        if self.taken is None:
            if self._laid != AT_THE_SCREEN_MANAGER_S_ENTRY or case.long_in(self._memory, sp + FRAME_PC) & BUS == ROM_ENTRY:
                self._take_over(sp, instructions)
        elif pc == self.ours.entry:
            self._entered(sp)
        else:
            self._program_entered(pc, sp)

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
        registers, resumed = _registers_now(), case.long_in(memory, aes.AES_RLR) & BUS
        if resumed != aes.SHELL_PD:     # ...the boot's own process — PD0, gem_main's — is RESUMED there, never entered
            _vet_the_boot_s_first_entry(memory, resumed, sp, registers)
        manager = aes.SCREEN_MANAGER_PD
        slots = _vetted_slots(memory, manager)
        stack = _vet_the_screen_manager(memory, manager)
        found = (hashlib.sha256(memory[:RAM_BYTES]).digest(), registers)
        if self._laid == FROM_THE_START:
            cleared = 0
            self._vet_not_stored_over()
        else:
            cleared = len(self._stored_in_the_span(0))
            _vet_clear_where_the_blob_goes(memory, ours)
            memory[ours.base:ours.base + len(ours.image)] = ours.image
            self._mark = _CPU.osh_num_writes()
        mapped = _mapped(memory, slots, {ROM_ENTRY: ours.entry})
        door = self._door_mapped() if ours.door else None
        self.taken = Takeover(ours, manager, stack, instructions, mapped, cleared, (), found, self._laid, door)
        self.armed = frozenset({ours.entry, *self._programs_to_enter})

    def _door_mapped(self):
        """THE DOOR'S MAPPING APPLIED where the boot stands (above), and the profile's tallies kept as the lay found
        them: a `DoorTaken`, its `ran` still to be read where the boot ends."""
        memory, vectors, programs = self._memory, {}, []
        for part in self.ours.door:
            mapping = dict(part.mapping)
            for pd, slot in door_slots(memory, part):
                held = case.long_in(memory, slot)
                if pd is None and held not in mapping:
                    raise Refused(f"{part.what} holds {held:#x} at the stop, not the ROM's "
                                  f"{[f'{rom:#x}' for rom in mapping]}: nothing of the registry's to map there — the "
                                  f"ROM has not installed its handler yet, or has given the vector back")
                if held not in mapping:
                    continue            # a process parked, or one no program was started in: no first-entry frame
                if pd is None:
                    vectors.update(_mapped(memory, (slot,), mapping))
                else:
                    programs.append(Program(pd, _name_of(memory, pd), _vet_never_entered(memory, pd), slot))
                    _mapped(memory, (slot,), mapping)
                    self._programs_to_enter.setdefault(mapping[held], []).append(pd)
            self._tallied_at_the_lay[part.what] = self._tallies_of(part)
        self._vet_no_program_left_the_rom_s(memory)
        return DoorTaken(vectors, tuple(programs), {})

    def _vet_no_program_left_the_rom_s(self, memory):
        """A PARTIAL DOOR IS REFUSED BY NAME: the GEM trap's vector mapped while a loaded program's first-entry frame
        still holds THE ROM'S gotopgm. Such a boot passes every other vet — who-ran is read per DECLARED part, and
        the ROM's gotopgm is no part of a door of the vector alone — while the ROM enters every accessory: a machine
        called "behind our door" whose programs the ROM started (wave 3's review, C-F8)."""
        mapped = {part.what for part in self.ours.door}
        if aes_event.GEM_TRAP_VECTOR.what not in mapped or aes_event.PROGRAM_ENTRY.what in mapped:
            # (a door of the programs alone is refused where the boot ends: parked in the ROM's text; and a door that
            # DECLARES the programs and maps one short — a frame not walked — is the who-ran's to refuse: gotopgm is its part)
            return
        left = [pd for pd, slot in aes_event.first_entry_frames(memory) if case.long_in(memory, slot) & BUS == addrs.AES_ROM_GOTOPGM]
        if left:
            raise Refused(f"A PARTIAL DOOR: {aes_event.GEM_TRAP_VECTOR.what} is mapped and the first-entry frame of "
                          f"{sorted(_name_of(memory, pd) for pd in left)} still holds the ROM's gotopgm "
                          f"({addrs.AES_ROM_GOTOPGM:#x}) — the door maps {sorted(mapped)} and not "
                          f"{aes_event.PROGRAM_ENTRY.what!r}: every loaded program is entered through ours, or none is")

    @staticmethod
    def _tallies_of(part):
        """`(cycles at our entries of `part`, cycles in the ROM's text of it)` as the profile stands."""
        return _cycles_at(entry for _rom, entry in part.mapping), _cycles_in(aes_event.ROM_TEXT_OF[part.what])

    def _entered(self, sp):
        if sp != self.taken.stack[1]:
            raise Refused(f"our entry is entered at SP {sp:#x}, not on the top of the screen manager's stack")
        self.entered, self.armed = True, self.armed - {self.ours.entry}

    def _program_entered(self, pc, sp):
        """Our gotopgm (`pc`) is entered: by switchto's `rte` popping a frame the door mapped, for the process running."""
        pd = case.long_in(self._memory, aes.AES_RLR) & BUS
        tops = {program.pd: program.stack[1] for program in self.taken.door.programs}
        if pd not in self._programs_to_enter[pc]:
            raise Refused(f"our entry at {pc:#x} is entered for the process at {pd:#x} ({_name_of(self._memory, pd)!r}), "
                          f"whose first-entry frame the door did not map — or mapped, and it is entered twice")
        if sp != tops[pd]:
            raise Refused(f"our entry at {pc:#x} is entered at SP {sp:#x}, not on the top of the stack of "
                          f"{_name_of(self._memory, pd)!r} ({tops[pd]:#x})")
        self._programs_to_enter[pc].remove(pd)
        if not self._programs_to_enter[pc]:
            self.armed -= {pc}

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
        if not self.entered and at_an_idle:
            raise Refused(f"the `rte` at the screen manager's first entry did not enter `{ENTRY_SYMBOL}` "
                          f"({self.ours.entry:#x}): the frame's PC was not mapped")
        if not self.entered:            # ...stopped before its idle — at either stop the takeover can be laid at
            self._vet_still_to_be_entered(memory)
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
        return taken._replace(door=self._door_made(memory, taken.door, at_an_idle)) if taken.door else taken

    def _vet_still_to_be_entered(self, memory):
        """A BOOT STOPPED BEFORE THE SCREEN MANAGER'S FIRST ENTRY (an `until` between the takeover's stop — the boot's
        first switchto `rte`, which resumes PD0 — and that entry) is a takeover machine only while the screen manager
        HAS STILL TO BE ENTERED, AND THROUGH OURS: nobody runs it, and the frame switchto will pop for it holds our
        entry. Anything else is the ROM's ctlmgr entered by a frame left unmapped — a machine called ours standing in
        the ROM's text — and is refused by name (wave 2 refused it by the stop; no profile watches a takeover with no
        door)."""
        pd, running = self.taken.process, case.long_in(memory, aes.AES_RLR) & BUS
        resumed_at = parked_pc(memory, pd)
        if running == pd or resumed_at != self.ours.entry:
            raise Refused(f"THE SCREEN MANAGER WAS NOT ENTERED THROUGH `{ENTRY_SYMBOL}` ({self.ours.entry:#x}) where the "
                          f"boot was stopped: " + ("it is the process running, and " if running == pd else "")
                          + f"its first-entry frame holds {resumed_at:#x}"
                          + (" — THE ROM'S ctlmgr: the frame's PC was not mapped" if resumed_at == ROM_ENTRY else "")
                          + ". A takeover machine never stands in the ROM's text of a routine it claims")

    def _door_made(self, memory, door, at_an_idle):
        """...AND ITS DOOR (above): the vectors still ours, who ran, every program entered through ours and parked
        in our text — the `DoorTaken`, its `ran` read."""
        vet_the_door_stands(memory, self.ours, "where the boot ends")
        ran = {}
        for part in self.ours.door:
            (ours_then, rom_s_then), (ours_now, rom_s_now) = self._tallied_at_the_lay[part.what], self._tallies_of(part)
            ran[part.what] = (ours_now - ours_then, rom_s_now - rom_s_then)
            if ran[part.what][1]:
                spans = [f"[{lo:#x}, {hi:#x})" for lo, hi in aes_event.ROM_TEXT_OF[part.what]]
                raise Refused(f"THE ROM'S OWN CODE RAN BEHIND A DOOR CALLED OURS: {ran[part.what][1]} cycles in "
                              f"{', '.join(spans)} after the takeover — {part.what} was mapped and the ROM's routine "
                              f"still reached (a process the ROM entered before the stop, a Line-F call, a vector "
                              f"left the ROM's)")
        left = {_name_of(memory, pd) for pds in self._programs_to_enter.values() for pd in pds}
        if at_an_idle and left:
            raise Refused(f"the boot reached its idle and {sorted(left)} was never entered through our gotopgm")
        for program in door.programs if at_an_idle else ():
            if whose(parked_pc(memory, program.pd), self.ours) != OURS:
                raise Refused(f"{program.name!r} stands parked at {parked_pc(memory, program.pd):#x}, in the ROM's "
                              f"text: behind a door that is ours it parks through our dispatcher")
        if at_an_idle and not ran.get(aes_event.GEM_TRAP_VECTOR.what, (True,))[0]:
            raise Refused("the boot reached its idle and our `trap #2` handler never ran: the vector mapped, and not "
                          "one GEM call of the rest of the boot arrived at ours")
        return door._replace(ran=ran)


# ---- ONE RUN OF A MACHINE TO AN IDLE: a boot's, or a booted machine's continued -------------------------------------------------
class _Run:
    """The run itself, from a whole register file to AN IDLE — the first arrival at a dispatcher's idle poll with
    nothing ready, nothing woken and no fork queued: the ROM's dispatcher's, or the blob's own (`ours`: after a
    takeover, or of a machine continued) — or to its FIRST ARRIVAL AT `until` where one is named, an idle refused
    if it comes first. Each stop is served: a driver entry, the probe's touch, the blank's handler entered, a poll,
    the takeover's (`taking`), a call watched (`observing`: `{PC: (name, a reader of the frame at that stop)}`).
    AFTER IT: `result` (the last segment's), what the harness stored into the machine (`laid`, `pushed`), the bus
    error's `frame`, the `polls` made, the `blanks` taken, whose `idle` it ended at, and what it `observed`.

    EVERY ARRIVAL AT A STOP IS A STOP. The door stops BEFORE the instruction at a stop's PC, so the run leaves a stop
    by ONE INSTRUCTION with that PC alone disarmed (`_stepped_off`) and every stop — that one too — is armed again
    for the rest: two arrivals at one PC with no other stop between are two stops. (Until band 5 wave 3 the PC stayed
    disarmed to the NEXT stop, and such a pair counted once: 102 arrivals at the trap handler where 366 happened. A
    zero was honest then; a count was not.)"""

    def __init__(self, memory, floppy, budget, *, until=None, taking=None, ours=None, observing=None, printer=False):
        self._memory, self._floppy, self._budget, self._until = memory, floppy, budget, until
        self._taking, self._ours, self._observing = taking, ours, dict(observing or {})
        self._printer = printer         # a printer on line (`Boot.printer`): its port declared, its transaction a stop
        self._hbl = case.long_in(memory, addrs.VECTOR_HBL) & BUS
        self._back = None               # where a poll of ours returns: the poll's entry is a stop again from there
        self.laid, self.pushed, self.frame, self.polls, self.blanks = {}, {}, {}, 0, 0
        self.idle, self.observed, self.result, self.printed = None, [], None, bytearray()

    def _our_dispatcher(self):
        """The blob whose idle is a stop as the run stands: a continued machine's, or a takeover's once made."""
        if self._taking is not None:
            return self._taking.ours if self._taking.entered else None
        return self._ours

    def _stops(self):
        stops = {*self._floppy.served_at, BLITTER_PROBE_TOUCH, IDLE_LOOP, IDLE_POLLED, self._hbl, *self._observing}
        stops |= {PRINTER_SEND} if self._printer else set()
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
        emu.install_chip_seeds(**(THE_PRINTER_S_PORT if self._printer else {}))
        result = emu.run_bench(memory, entered["pc"], 0, OFF_THE_MACHINE, emu.SENTINEL, max_insns=budget,
                               door={entered["pc"]}, seed_regs=None, io_seed=io_seed)
        assert result["status"] == emu.BENCH_DOOR and not result["ninsns"], "the run began before its registers were laid"
        _enter(entered)
        _CPU.m68k_set_irq(HBL_LEVEL)
        ours = self._our_dispatcher()
        if ours is not None and entered["pc"] == ours.poll:
            self._back = case.long_in(memory, _register("a7")) & BUS      # entered AT a poll of ours (a machine continued)
        while True:
            self._stepped_off(self._stops())
            left = budget - _CPU.osh_num_insns()
            if left <= 0:
                raise Refused(f"the run did not reach an idle within {budget} instructions")
            result = self._resumed(left)
            if result["status"] != emu.BENCH_DOOR:
                raise Refused(f"the run left the machine: it ended with status {result['status']} at "
                              f"{emu.bench_resume_pc():#x}")
            self.result = result
            if self._stopped(emu.bench_door_pc(), emu.bench_door_sp()):
                return result

    @staticmethod
    def _stepped_off(stops):
        """The run, standing BEFORE the instruction at one of `stops`, taken ONE INSTRUCTION on with that PC alone
        disarmed — then every stop armed (the class's note). Where it stands at none of them (a driver's call
        answered, the bus error taken: the PC moved) nothing is run."""
        at = _register("pc")
        if at in stops:
            emu.bench_door_arm(stops - {at})
            _CPU.osh_bench_resume(ONE_INSTRUCTION, (ctypes.c_uint32 * len(emu.REPORTED_REGS))())
            # THE RUN'S FIRST RESUMED SEGMENT RUNS NO INSTRUCTION (measured: the oracle counts one and the PC and A7
            # stand where the registers were laid). A run ENTERED AT A STOP — a machine continued from its idle's
            # poll — would stand there still, be stopped at once, and have its entry counted as an arrival: so that
            # one segment is taken again. (Slice L's finding; `test_a_run_entered_at_a_stop_does_not_count_its_entry`.)
            if _CPU.osh_num_insns() == ONE_INSTRUCTION and _register("pc") == at:
                _CPU.osh_bench_resume(ONE_INSTRUCTION, (ctypes.c_uint32 * len(emu.REPORTED_REGS))())
        emu.bench_door_arm(stops)

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
        if pc in self._floppy.served_at:
            self._serve_the_driver(pc, sp)
        elif pc == self._hbl:
            self.blanks += 1            # ...taken: the CPU let the line go, and the next one is pending from here
            _CPU.m68k_set_irq(HBL_LEVEL)
        elif pc == PRINTER_SEND:
            self.printed.append(case.word_in(memory, sp + PRINTER_CHARACTER_AT) & aes.BYTE_MASK)
            _return_from_the_driver(addrs.PRINTER_SENT, case.long_in(memory, sp) & BUS, sp)
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
        answer, to = self._floppy.served(pc, sp)
        _return_from_the_driver(answer, to, sp)
        for at, data in self._floppy.laid_by_the_last_call():      # the sectors read; the driver's own bytes (Getbpb, a mode)
            self.laid[at] = data
            if self._taking is not None:
                self._taking.harness_laid(at, len(data))

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


ROM_SHADOW_BYTES = 8                    # `$0..$7`: on an ST the ROM's first two longwords, read there — and no RAM


def _vet_nothing_stored_under_the_rom_s_shadow(before, memory, writes, what):
    """NO STORE AT `$0..$7` — or the run is refused by name. On the machine those eight bytes are the ROM's (the reset
    vectors, shadowed) and A WRITE THERE IS A BUS ERROR; the oracle's megabyte takes the store and runs on, into a
    machine no ST reaches. (How the ROM gets there, MEASURED: six accessories each in a six-way wait ask 42 EVBs of
    the 40 the machine supplies; get_evb, `$fe4002`, answers 0 for an empty free list, and the desk's wait is built
    at address 0 all the same.) Held two ways: the run's write ledger (`writes`; it saturates on a boot that loads many programs) and the eight bytes
    themselves, `before` the run and after."""
    if any(at < ROM_SHADOW_BYTES for at in writes) or bytes(memory[:ROM_SHADOW_BYTES]) != bytes(before[:ROM_SHADOW_BYTES]):
        raise Refused(f"{what} STORED AT $0..$7 (they held {bytes(before[:ROM_SHADOW_BYTES]).hex()}, they hold "
                      f"{bytes(memory[:ROM_SHADOW_BYTES]).hex()}): on the machine that is a BUS ERROR — the ROM's "
                      f"shadow, not RAM — and this model takes none there. (The ROM's get_evb answers 0 where the "
                      f"free EVB list is empty: more waits asked than the machine supplies EVBs build one at address 0)")


def _io_seed(io):
    """The declared I/O map of a pre-init machine's shifter bytes."""
    return {preinit_snapshot.IO_AT + offset: byte for offset, byte in enumerate(io)}


PROFILE_HELD_BY_A_DOOR_BOOT = "a door boot's own run (`aes_boot.booted`)"

# ---- THE OUR-BOOT MACHINE'S PREMISES (band 5 wave 4, ruling W4-R1), VETTED AGAINST THE ROM'S OWN RUN ---------------------------
# `booted(preinit, disk, ours=, laid=AT_GEM_ENTRY)` is the pre-init machine with the blob laid where the run stands
# BEFORE ITS FIRST INSTRUCTION and entered at the blob's own gem_entry — no longword mapped by the harness. What makes
# that A MACHINE AND NOT A POKE OVER ONE is three facts about the ROM's side, each refused by name where it fails
# (`vet_ours_can_be_laid_at_gem_entry`), none of them a fact about our code:
#   * THE ENTRY: the capture stands at `gem_entry` as the machine's own `exec_os` names it, IN USER MODE — a program's
#     entry, the registers the launch left;
#   * THE WINDOW IS ZERO AT THE STOP: every span the harness will use — the blob's, the kit's staging band and its
#     stack band (`harness_window`) — holds nothing;
#   * THE ROM'S OWN BOOT OF THE SAME MACHINE AND DISK STORES NOTHING THERE, to its first idle (its whole ledger, the
#     sectors the harness laid among it; a saturated ledger is refused). So nothing the boot does between `gem_entry`
#     and the desk depends on, or lands in, the bytes the blob takes — ON THIS DISK. A disk with an accessory fails
#     it by 196,608 + 4,096 + 3,868 bytes and more: the loader's `Pexec(3)` clears the largest free block, the window
#     with it, and OUR loader's first Pexec would erase the code that called it (ruling W4-R2: such machines stay
#     door takeovers; putting the blob back after the clear is refused, never done).
STAGING_BAND, STACK_BAND = "the kit's staging band", "the kit's stack band"


def harness_window(ours):
    """THE SPANS OF THE MACHINE THE HARNESS USES for a blob `ours` (anything with `base` and `end`), `{what: (lo, hi)}`:
    the blob's own, the staging band `project.toml` declares and the oracle's stack band."""
    return {THE_BLOB: (ours.base, ours.end), STAGING_BAND: (staging.SCRATCH, staging.SCRATCH + staging.SCRATCH_BYTES),
            STACK_BAND: (emu.STACK_GUARD_LO, emu.STACK_BAND_HI)}


def _stored_within(stored, lo, hi):
    """How many bytes of `[lo, hi)` the `(start, length)` runs `stored` cover."""
    return sum(max(0, min(hi, start + length) - max(lo, start)) for start, length in stored)


def vet_ours_can_be_laid_at_gem_entry(machine, disk, ours):
    """THE THREE PREMISES (above) of the our-boot machine over the pre-init `machine` and `disk`, for the blob `ours`
    — each REFUSED BY NAME: answers the window, `{what: (lo, hi)}`. THE ROM'S OWN BOOT is the kept one."""
    registers, named = machine.registers, case.long_in(machine.ram, preinit_snapshot.EXEC_OS) & BUS
    if not registers["pc"] == named == GEM_ENTRY:
        raise Refused(f"the machine stands at {registers['pc']:#x} and its exec_os names {named:#x}: not gem_entry "
                      f"({GEM_ENTRY:#x}) — a blob is laid {AT_GEM_ENTRY} and nowhere else")
    if registers["sr"] & SR_SUPERVISOR:
        raise Refused(f"the machine stands at gem_entry in supervisor mode (SR {registers['sr']:#06x}): gem_entry is "
                      f"entered as a program, and ours would load its first stack over a state no launch leaves")
    window = harness_window(ours)
    for what, (lo, hi) in window.items():
        held = bytes(machine.ram[lo:hi]).lstrip(b"\0")
        if held:
            raise Refused(f"THE WINDOW IS NOT ZERO AT THE STOP: {what} [{lo:#x}, {hi:#x}) holds something from "
                          f"{hi - len(held):#x} — the pre-init machine is not free where the harness goes")
    rom_s = booted(machine, disk)
    if rom_s.writes_truncated:
        raise Refused("the ROM's own boot of this machine and disk saturated its write ledger: what it stores in the "
                      "window is not known, and no blob is laid on a guess")
    for what, (lo, hi) in window.items():
        stored = _stored_within(rom_s.stored, lo, hi)
        if stored:
            raise Refused(f"THE ROM'S OWN BOOT OF THIS DISK STORES AT {stored} BYTE(S) OF {what} [{lo:#x}, {hi:#x}) before "
                          f"its first idle: `Pexec` hands a program the largest free block and clears it — over a disk "
                          f"with an accessory our own loader's first Pexec would erase the code that called it. Such "
                          f"a machine stays a door takeover {AT_THE_FIRST_ENTRY} (ruling W4-R2); the blob is never "
                          f"put back after a clear")
    return window


# ---- THE OUR-BOOT MACHINE ITSELF (band 5 wave 4, slice B): THE BLOB LAID AT gem_entry AND ENTERED AT ITS OWN ----------------
# WHAT THE HARNESS DOES, and it is two things: the blob's bytes laid in the window the premises hold free, and the
# capture's register file entered WITH THE PC AT THE BLOB'S gem_entry instead of the ROM's — the one word of the CPU
# that says whose start-up runs. Every other register, both stack pointers and the megabyte are the capture's. No
# longword of the machine is given a blob address by the harness: what holds one where the run ends was stored by
# our own instructions (`aes_ourboot.py` holds each to the registry's declaration of it).
# WHAT `exec_os` AND THE AES's BASEPAGE STILL NAME is the ROM's gem_entry — stored by the BIOS, read by nothing after
# the launch, NOT MAPPED on either shore (the scan's `THE_BIOS_S`).
# WHO RAN, CUT AT deskmain's ENTRY (`OurBoot.ran`, ruling W4-R3): the cycle profile's tallies as the run arrives at
# `$fe272e` (or where it ends, for a boot stopped earlier) less what they were as it began — NOT ONE CYCLE in the
# ROM's GEM text (`aes.AES_TEXT`) nor in the Line-F handler's RAM copy, or the boot is REFUSED BY NAME; the blob's own
# count is what "ours" means. From deskmain on the ROM's spans are live BY DECLARATION (the desk is the ROM's, and
# calls the ROM's AES through the ROM's table): nothing is claimed of them, in those words.
# REFUSED BY NAME beside the premises: a blob that links no gem_entry; a door (nothing is mapped); A HALT OF THE BUILD
# (`trap #7`: the desk door's vet, a routine not reconstructed — the run is stopped where the BIOS's handler for it
# is entered, and said: never run on into the bombs); a store of the boot's into the blob's span.
# Every vector the BIOS has given no handler holds ONE routine's address under the vector's own number in the high
# byte (a 68000 drives 24 address lines; the handler reads the byte back off the PC to say which bombs to draw). The
# oracle's PC keeps all 32 bits: the stop is armed at the longword AS THE VECTOR HOLDS IT.
THE_BIOS_S_EXCEPTION_HANDLER = 0xfc0b50
VECTOR_TRAP_7 = 0x9c                    # `trap #7`: the build's halt (`recreate_not_reconstructed`, the desk door's vet)
TRAP_7_WORD, TRAP_INSTRUCTION_BYTES = 0x4e47, WORD_BYTES
OUR_BOOT = "OUR BOOT — A LABELLED STAGING (ruling W4-R1): the blob laid at gem_entry, the run entered at its own"
PROFILE_HELD_BY_AN_OUR_BOOT = "an our-boot's own run (`aes_boot.booted`, laid at gem_entry)"
OurBoot = namedtuple("OurBoot", "ours at_the_desk ran")
OurBoot.__doc__ = """What makes a `Boot` an OUR-BOOT machine's (above): the blob (`ours`, an `Ours`); `at_the_desk` —
`(instructions, cycles, the supervisor stack pointer)` as the run FIRST arrived at deskmain's entry, None for a boot
stopped before it; and `ran`, WHO RAN UP TO THERE (to where the boot ended, for one stopped earlier): `(cycles in the
blob, cycles in the ROM's GEM text, cycles in the Line-F handler's RAM copy)` — the last two zero, or no such `Boot`
exists."""
LINE_F_COPY = (aes.AES_LINEF_COPY, aes.AES_LINEF_COPY + aes.LINEF_COPY_BYTES)


def vet_an_our_boot_is_asked_right(machine, disk, ours):
    """`booted(..., laid=AT_GEM_ENTRY)`'s question, vetted before anything is laid: a blob, one that links its own
    gem_entry, handed no door — and the three premises (`vet_ours_can_be_laid_at_gem_entry`), each its own refusal."""
    if ours is None:
        raise Refused(f"nothing is laid {AT_GEM_ENTRY} without a blob: `ours` names none")
    if ours.door:
        raise Refused(f"a blob laid {AT_GEM_ENTRY} is handed NO DOOR: the harness maps no longword of the our-boot "
                      f"machine — each vector and entry is stored by our own run (ruling W4-R1)")
    if ours.start is None:
        raise Refused(f"the blob links no `{GEM_ENTRY_SYMBOL}`: an our-boot machine is entered at the build's own "
                      f"gem_entry and nowhere else")
    vet_ours_can_be_laid_at_gem_entry(machine, disk, ours)


def watched_for_the_build_s_halt(memory, ours):
    """THE STOP A RUN OF A MACHINE WHOSE BLOB IS `ours` IS WATCHED AT FOR THE BUILD'S HALT (`_Run`'s `observing`):
    `{where the machine's `trap #7` vector leads: (what, its reader)}` — the reader REFUSES BY NAME, with the address
    of the `trap #7` in the blob read off the frame the BIOS's handler is entered over. Refused where the vector is
    no longer the BIOS's own (a halt would not be seen where it is watched for)."""
    halts_at = case.long_in(memory, VECTOR_TRAP_7)
    if halts_at & BUS != THE_BIOS_S_EXCEPTION_HANDLER:
        raise Refused(f"this machine's `trap #7` vector holds {halts_at:#x}, not the BIOS's own handler "
                      f"({THE_BIOS_S_EXCEPTION_HANDLER:#x}): a halt of the build would not be seen where it is watched for")

    def halted(memory, sp):
        status, pc = case.word_in(memory, sp), case.long_in(memory, sp + FRAME_PC) & BUS
        halt = pc - TRAP_INSTRUCTION_BYTES
        in_the_blob = ours.base <= halt < ours.base + len(ours.image)
        raise Refused(
            f"THE RUN TOOK A `trap #7` THE MACHINE DOES NOT HANDLE, from {pc:#x} (status {status:#06x}, SP {sp:#x})"
            + (f" — THE BUILD'S OWN HALT, `trap #7` at {halt:#x} (blob + {halt - ours.base:#x}): the desk door's vet (a "
               f"build whose frames run deeper than the ROM's at a call out of the shell, or a call off PD0's stack) "
               f"or a routine not reconstructed" if in_the_blob and case.word_in(memory, halt) == TRAP_7_WORD else ""))
    return {halts_at: ("the build's halt: `trap #7`, taken", halted)}


class BootingOurs:
    """ONE OUR-BOOT (above), from the lay to its `OurBoot`: the blob laid as it is made; `watched`, the stops the
    run is observed at (deskmain's entry, the BIOS's exception handler); `begun()` once the profile is on; `made()`
    where the run ended."""

    def __init__(self, memory, ours):
        self._memory, self.ours = memory, ours
        _vet_clear_where_the_blob_goes(memory, ours)
        memory[ours.base:ours.base + len(ours.image)] = ours.image
        self._began, self._at_the_desk, self._ran = None, None, None
        self.watched = {addrs.AES_ROM_DESKMAIN: ("deskmain's entry", self._arrived_at_the_desk),
                        **watched_for_the_build_s_halt(memory, ours)}

    def entered(self, registers):
        """The capture's register file, entered at the blob's own gem_entry."""
        return {**registers, "pc": self.ours.start}

    def _tallies(self):
        ours = self.ours
        return (emu.prof_cycles(ours.base, ours.base + len(ours.image)), emu.prof_cycles(*aes.AES_TEXT),
                emu.prof_cycles(*LINE_F_COPY))

    def begun(self):
        """The profile is on and the run about to begin: the tallies it starts from (never reset: differences)."""
        self._began = self._tallies()

    def _ran_so_far(self):
        return tuple(now - then for now, then in zip(self._tallies(), self._began))

    def _arrived_at_the_desk(self, _memory, sp):
        if self._at_the_desk is None:   # ...its FIRST arrival: the claim's cut (a second pass's is the served door's)
            cost = aes_event.run_cost()
            self._at_the_desk, self._ran = (cost["insns"], cost["cycles"], sp), self._ran_so_far()

    def made(self, memory, ended, stored):
        """THE OUR-BOOT, VETTED WHERE THE RUN ENDED (above): its `OurBoot`. `ended`: `(instructions, cycles, the
        registers)` there; `stored`: every address the run and the harness stored at."""
        ours = self.ours
        reached = sorted(at for at in stored if ours.base <= at < ours.end)
        if reached or bytes(memory[ours.base:ours.base + len(ours.image)]) != ours.image:
            raise Refused(
                f"THE OUR-BOOT STORED OVER ITS OWN BLOB: "
                + (f"{len(reached)} byte(s) of its span [{ours.base:#x}, {ours.end:#x}) from {reached[0]:#x} on" if reached
                   else "its span holds other bytes than the blob's, by no store the ledgers name")
                + " — the blob lies in memory GEMDOS believes free: a Malloc or a Pexec of the boot's was handed it (a "
                  "disk with an accessory: ruling W4-R2), and the run went on over code that was no longer there")
        instructions, cycles, registers = ended
        if self._at_the_desk is None and registers["pc"] & BUS == addrs.AES_ROM_DESKMAIN:
            self._at_the_desk, self._ran = (instructions, cycles, registers["isp"]), self._ran_so_far()   # ...ended there (`until`)
        ran = self._ran if self._ran is not None else self._ran_so_far()
        ours, the_rom_s, the_copy = ran
        if the_rom_s or the_copy or not ours:
            raise Refused(
                f"NOT AN OUR BOOT — WHO RAN up to {'deskmain' + chr(39) + 's entry' if self._at_the_desk else 'where the boot was stopped'}: "
                f"{ours} cycles in the blob, {the_rom_s} IN THE ROM'S OWN GEM TEXT [{aes.AES_TEXT[0]:#x}, "
                f"{aes.AES_TEXT[1]:#x}) and {the_copy} in the Line-F handler's RAM copy — a routine of the build that "
                f"is still the ROM's (a `jsr` into its text, a vector or a code address by value left the ROM's, a "
                f"Line-F call), or a blob that never ran")
        return OurBoot(self.ours, self._at_the_desk, ran)


@derived.kept
def booted(machine, disk, budget=BOOT_INSNS, until=None, ours=None, laid=AT_THE_FIRST_ENTRY):
    """THE ROM'S OWN BOOT (the module's docstring) from the pre-init `machine` (`preinit_snapshot.PreInit`) with
    `disk` — the one it booted with — in drive A:, to the first idle: a `Boot`. `until`: STOPPED EARLIER, at the
    boot's first arrival at that address — a routine's entry, the machine and the registers as its caller left
    them (the `Boot`'s PC is then `until`, its A7 the caller's stack pointer over the return address and the frame).
    `ours` (an `Ours`: `ours_of(blob)`): THE SCREEN MANAGER IS OURS — the takeover (above) made at its first entry,
    the `Boot`'s `takeover` what it did; `until` may then name an address of the blob. KEPT BY CONTENT: the pre-init
    machine's, the disk's and the blob's — a rebuilt blob is another question. `laid`: when the blob is (the RED's;
    `AT_GEM_ENTRY`: THE OUR-BOOT MACHINE, ruling W4-R1's LABELLED STAGING — its premises vetted against the ROM's own
    run, the blob laid before the run's first instruction and the run entered at the blob's own gem_entry; no
    takeover, no door: the `Boot`'s `our_boot` says what it is and who ran to deskmain's entry)."""
    ours_boots = laid == AT_GEM_ENTRY
    if ours_boots:
        vet_an_our_boot_is_asked_right(machine, disk, ours)
    memory = bytearray(BASE_IMAGE)                  # ...for the ROM in it: the megabyte below is the pre-init machine's
    memory[:RAM_BYTES] = machine.ram
    floppy = Floppy(memory, disk)
    booting = BootingOurs(memory, ours) if ours_boots else None
    taking = _TakingOver(memory, ours, laid) if ours is not None and not ours_boots else None
    run = (_Run(memory, floppy, budget, until=until, ours=ours, observing=booting.watched) if ours_boots
           else _Run(memory, floppy, budget, until=until, taking=taking))
    profiled = ours_boots or (taking is not None and taking.profiled)
    if profiled:
        aes_event.vet_the_profile_is_free("an our-boot" if ours_boots else "a door boot")      # ...refused by name, before
    # ...AND HELD FOR ITS OWN RUN, as every profiled run of Tier 3's is: a second door boot begun inside this one
    # (a derivation asked cold by a stop's watcher) would switch the profile off under it.
    held_by = PROFILE_HELD_BY_AN_OUR_BOOT if ours_boots else PROFILE_HELD_BY_A_DOOR_BOOT
    holding = aes_event.profile_held(held_by) if profiled else contextlib.nullcontext()
    entered = booting.entered(machine.registers) if ours_boots else machine.registers
    try:
        # A DOOR'S WHO-RAN — AND AN OUR-BOOT'S — IS READ OFF THE CYCLE PROFILE (`_TakingOver.made`,
        # `BootingOurs.made`), on for this run alone: its tallies are read as DIFFERENCES, nothing reset — but the
        # profile is one switch of the oracle's, so such a boot is never derived inside another measurement's
        # profiled run (it would be left off for the rest of it).
        if profiled:
            emu.prof_enable(True)
        if ours_boots:
            booting.begun()
        with holding:
            result = run.to_an_idle(entered, io_seed_of(machine))
        registers = _registers_now()
        writes, truncated = emu.bench_writes(memory)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
        _vet_nothing_stored_under_the_rom_s_shadow(machine.ram, memory, writes, "THE BOOT")
        if ours is not None and truncated:
            raise Refused("the boot's write ledger saturated: what it stored over the blob's span is not known")
        takeover = taking.made(memory, run.idle is not None) if taking is not None else None
        our_boot = None
        if ours_boots:
            harness_s = {at for start, data in run.laid.items() for at in range(start, start + len(data))}
            our_boot = booting.made(memory, (result["ninsns"], result["cycles"], registers), {*writes, *harness_s})
    finally:
        if profiled:
            emu.prof_enable(False)
        _CPU.m68k_set_irq(NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made("the ROM's boot from the pre-init machine")
    return Boot(bytes(memory[:RAM_BYTES]), registers, bytes(floppy.disk), result["ninsns"], result["cycles"], run.polls,
                run.blanks, tuple(floppy.calls), *streams, run.stored(writes), run.frame, truncated, machine.io, run.idle,
                takeover, our_boot=our_boot, **surfaced(floppy, streams[1], run.printed))


# ---- THE TEST ACCESSORY (`tools/accessory_disk.py` builds it and its disk) ---------------------------------------------------
PRG_HEADER_BYTES = fs_pexec.PRG_HEADER_BYTES
PRG_TEXT_BYTES_AT = 2                   # the header's four lengths: TEXT, DATA, BSS, symbols
NOT_CALLED = 0xfffe                     # what testacc.S's `res_find` and `res_write` hold until the call is made
QUIET, FIND, WRITE, MULTI = accessory_disk.QUIET, accessory_disk.FIND, accessory_disk.WRITE, accessory_disk.MULTI
REGISTER, HIDE, with_a_window = accessory_disk.REGISTER, accessory_disk.HIDE, accessory_disk.with_a_window
ACCESSORY_NAMES, SEVEN_ACCESSORY_NAMES = accessory_disk.NAMES, accessory_disk.SEVEN_NAMES
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


@functools.cache
def seven_accessory_disk_of(*modes):
    """...and THE SEVEN-ACCESSORY DISK, each of its seven in its mode: the disk `seven_accessory_preinit` booted with."""
    assert len(modes) == len(SEVEN_ACCESSORY_NAMES), f"seven accessories, {len(modes)} modes"
    return accessory_disk.disk_of(accessory(), modes, SEVEN_ACCESSORY_NAMES)


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
        self.takeover, self.idle, self.observed, self.served = boot.takeover, boot.idle, boot.observed, boot.served
        self.our_boot = boot.our_boot   # of a machine OUR gem_entry booted (a labelled staging): its `OurBoot`
        self.ours = blob_of(boot)       # the blob of a machine whose screen manager is ours (a takeover's, an our-boot's)
        self.door = boot.takeover.door if boot.takeover else None      # ...and what a door takeover did, behind a door

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


# THE CAPTURES THIS PROCESS HAS READ, in the order it first asked for each. `test/test_makefile.py` reads it as the
# registry's import ends: a capture that import reads must be among the Makefile's REGISTRY_READS, or `make bench`
# dies in an empty tree — which no suite can see, since a suite only ever runs in a tree that was built.
CAPTURES_READ = []


def _capture(path):
    CAPTURES_READ.append(path)
    return preinit_snapshot.load(path)


@functools.cache
def preinit():
    """The pre-init machine of this tree (`build/preinit.bin`; `make preinit`): booted with the blank disk."""
    return _capture(preinit_snapshot.preinit_path())


@functools.cache
def accessory_preinit():
    """...and the one booted with the accessories' disk in the drive (`build/preinit_acc.bin`; `make preinit-acc`)."""
    return _capture(preinit_snapshot.accessory_path())


@functools.cache
def seven_accessory_preinit():
    """...and the one booted with SEVEN accessories in the drive (`build/preinit_acc7.bin`; `make preinit-acc7`)."""
    return _capture(preinit_snapshot.seven_accessory_path())


@functools.cache
def blank_disk():
    return accessory_disk.disk_with()


def _taken_over_by(blob, door=()):
    """`booted`'s arguments that make the screen manager `blob`'s (None: the ROM's own) — and its trap door, of `door`."""
    return {} if blob is None else {"ours": ours_of(blob, door)}


def desk_machine(machine=None, ours=None, door=()):
    """THE DESK'S MACHINE: the ROM booted from the pre-init `machine` (this tree's by default) over the blank disk it
    was captured with — the post-boot snapshot's own boot, stopped at its FIRST idle instead of nine hundred
    vertical blanks on. The snapshot's family, without the time. `ours` (a `RomBench`: `isr.blob_named`): THE SCREEN
    MANAGER IS THAT BLOB'S (the takeover) — and, of a `door` (`ours_of`'s), ITS TRAP DOOR."""
    return Machine(booted(machine or preinit(), blank_disk(), **_taken_over_by(ours, door)))


def accessory_machine(first=QUIET, second=QUIET, machine=None, ours=None, door=()):
    """THE ACCESSORY MACHINE: the ROM booted from the ACCESSORY pre-init `machine` (this tree's by default) over the
    disk it was captured with, each accessory in its mode (`first`, `second`) — both loaded by the ROM's own loader,
    started, and waiting with the desk and the screen manager at the first idle. `ours`, `door`: as `desk_machine`'s."""
    return Machine(booted(machine or accessory_preinit(), accessory_disk_of(first, second), **_taken_over_by(ours, door)))


def seven_accessory_machine(*modes, machine=None, ours=None, door=()):
    """THE SEVEN-ACCESSORY MACHINE (band 5 wave 3): the ROM booted from the SEVEN-accessory pre-init `machine` over the
    disk it was captured with, each of the seven in its mode (all quiet by default) — ONE MORE `.ACC` THAN THE LOADER
    TAKES: six are loaded and started (the spare static PD and five allocated ones), the seventh is never opened.
    `ours`, `door`: as `desk_machine`'s."""
    modes = modes or (QUIET,) * len(SEVEN_ACCESSORY_NAMES)
    return Machine(booted(machine or seven_accessory_preinit(), seven_accessory_disk_of(*modes), **_taken_over_by(ours, door)))


# ---- THE DESKTOP.INF MACHINE (band 5 wave 4, ruling W4-R7): the fourth capture ------------------------------------------------
VIEW_AS_ICONS, VIEW_AS_TEXT = accessory_disk.VIEW_AS_ICONS, accessory_disk.VIEW_AS_TEXT
RESOLUTION_AS_BOOTED, RESOLUTION_CHANGED = accessory_disk.RESOLUTION_AS_BOOTED, accessory_disk.RESOLUTION_CHANGED


@functools.cache
def inf_preinit():
    """...and the one booted with THE DESKTOP.INF DISK in the drive (`build/preinit_inf.bin`; `make preinit-inf`)."""
    return _capture(preinit_snapshot.inf_path())


@functools.cache
def default_inf():
    """The ROM's own default DESKTOP.INF text, cut out of the ROM this process holds (`accessory_disk.default_inf`)."""
    return accessory_disk.default_inf(bytes(BASE_IMAGE[emu.ROM_BASE:emu.ROM_END]))


@functools.cache
def inf_disk_of(view=VIEW_AS_ICONS, resolution=RESOLUTION_AS_BOOTED):
    """THE DESKTOP.INF DISK, its `#E` line's two pairs as asked (`accessory_disk.inf_disk_of`): one disk to the
    machine whatever they are — the disk `inf_preinit` booted with. A resolution no boot survives is refused by name."""
    return accessory_disk.inf_disk_of(default_inf(), view, resolution)


def inf_machine(view=VIEW_AS_ICONS, resolution=RESOLUTION_AS_BOOTED, machine=None, ours=None, door=()):
    """THE DESKTOP.INF MACHINE: the ROM booted from the DESKTOP.INF pre-init `machine` (this tree's by default) over
    the disk it was captured with, its `#E` line asking `view` and `resolution` — the reader's FILE arm, its parse
    and app_reschange run in place; no accessory. `VIEW_AS_TEXT`: a drive's window on it holds its items as
    G_USERDEF objects (`continued`: the trampoline's arrivals). `ours`, `door`: as `desk_machine`'s."""
    return Machine(booted(machine or inf_preinit(), inf_disk_of(view, resolution), **_taken_over_by(ours, door)))


# THE CARTRIDGE'S LINE A DRIVE (band 6 slice F3's fix pass; the user's ruling 2026-10-21: "price via INF class") — A
# LABELLED CLASS OF DISK: the DESKTOP.INF disk, the default text's cartridge line retyped a drive's
# (`accessory_disk.with_the_cartridge_line_a_drive`: one byte of the file, the serial and the layout unchanged). A
# ROM-run state, never a poke: the ROM's own boot reads the file and keeps a drive icon lettered 'c'.
THE_CARTRIDGE_A_DRIVE = ("F3 THE CARTRIDGE'S LINE A DRIVE: the DESKTOP.INF disk, its `#C 01 06 00 FF c CARTRIDGE` line retyped "
                         "`#M` (one byte of the file): a drive icon lettered 'c'")


@functools.cache
def cartridge_drive_disk():
    """THE DESKTOP.INF DISK OF THE CLASS ABOVE: one disk to the machine `inf_preinit` logged in, as every `#E` pair's is."""
    return accessory_disk.with_the_cartridge_line_a_drive(inf_disk_of(), default_inf())


def with_a_disk_in_drive_b(machine, disk):
    """`machine` — booted, or continued, with drive B: empty — WITH `disk` IN DRIVE B: (band 6 wave 4, W6-R9: the
    `DRIVE_B` class). Drive B: was never LOGGED IN — the driver's record for it is all zeros — so a disk there is one
    no BPB of the machine's describes. IT IS NOT MEASURED THE SAME MACHINE TO THE BYTE: the boot did touch drive 1 (its
    access time `$9fc + 4` is stamped on every capture), and no capture was made with a disk in drive B: — hence the
    label. REFUSED BY NAME for a machine whose drive B: holds one already, or was logged in."""
    record = driver_record(machine.image()) + DRIVE_B_DEVICE * FLOPPY_BPB_RECORD_BYTES
    if machine.boot.drive_b is not None or any(machine.ram[record:record + FLOPPY_BPB_RECORD_BYTES]):
        raise Refused("a disk is put in drive B: of a machine whose drive B: holds one already, or was logged in")
    return Machine(machine.boot._replace(drive_b=bytes(disk)))


def with_a_printer_on_line(machine):
    """`machine` WITH A PRINTER ON LINE AT ITS PARALLEL PORT (band 6 wave 4, W6-R9: the `THE_PRINTER` class): every
    run continued from it is served the GPIP with BUSY clear and the port's transaction (`PRINTER_SEND`). Nothing of
    the megabyte changes — no run before it read the port. REFUSED BY NAME for a machine that has one already."""
    if machine.boot.printer:
        raise Refused("a printer is put on line at a machine that has one already")
    return Machine(machine.boot._replace(printer=True))


# ---- BEGIN band 6 wave 0, slice H: THE FILES MACHINE (ruling W6-R10) — the fifth capture ---------------------------------------
@functools.cache
def files_preinit():
    """...and the one booted with THE FILES DISK in the drive (`build/preinit_files.bin`; `make preinit-files`)."""
    return _capture(accessory_disk.files_capture_path())


@functools.cache
def files_disk_of(view=VIEW_AS_ICONS):
    """THE FILES DISK (`accessory_disk.files_disk_of`): the ROM's default DESKTOP.INF, a text longer than the viewer's
    page, a program (the test accessory's file) and the folder AUTO with a file in it — one disk to the machine
    whatever the `view` pair: the disk `files_preinit` booted with."""
    return accessory_disk.files_disk_of(default_inf(), accessory().file, view)


def files_machine(view=VIEW_AS_ICONS, machine=None):
    """THE FILES MACHINE: the ROM booted from the FILES pre-init `machine` (this tree's by default) over the disk it
    was captured with — a desk with no accessory, whose drive holds what the desk's own acts need (`test/aes_desk.py`)."""
    return Machine(booted(machine or files_preinit(), files_disk_of(view)))
# ---- END band 6 wave 0, slice H -----------------------------------------------------------------------------------------------


# ---- THE OUR-BOOT MACHINES (band 5 wave 4, slice B; ruling W4-R1: A LABELLED STAGING) ----------------------------------------
def our_desk_machine(blob, until=None, machine=None):
    """THE DESK'S MACHINE, BOOTED BY OUR OWN gem_entry (`booted(..., laid=AT_GEM_ENTRY)`: A LABELLED STAGING — the blob
    `blob` (a `RomBench`) laid at the pre-init stop of the blank disk's capture and the run entered at its own
    gem_entry) — to its first idle, or stopped at its first arrival at `until`. "OURS BOOTED" IS CLAIMED TO
    deskmain's ENTRY AND NO FURTHER (`Machine.our_boot`: who ran, cut there)."""
    return Machine(booted(machine or preinit(), blank_disk(), until=until, ours=ours_of(blob), laid=AT_GEM_ENTRY))


def our_inf_machine(blob, view=VIEW_AS_ICONS, resolution=RESOLUTION_AS_BOOTED, until=None, machine=None):
    """...and THE DESKTOP.INF MACHINE, booted the same way over the disk its capture was made with: OUR reader's file
    arm, its `#E` parse and app_reschange run in place. NO DISK WITH AN ACCESSORY HAS ONE (ruling W4-R2: refused by
    name — our own loader's first Pexec would clear the blob)."""
    return Machine(booted(machine or inf_preinit(), inf_disk_of(view, resolution), until=until, ours=ours_of(blob),
                          laid=AT_GEM_ENTRY))


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
TICKS = "the system timer ticks"        # ...and TIME PASSING at the idle (band 6 wave 4): that many ticks, each through
                                        # Timer C's handler as a click's are — the printer's five-second hold-off waited out
LEFT_DOWN, NO_BUTTON = aes_event.LEFT_DOWN_PACKET, aes_event.NO_BUTTON_PACKET


def mouse_to(x, y):
    """RECEIVED: relative mouse packets toward (`x`, `y`), the buttons as they are held, until the cursor is there."""
    return MOUSE_TO, x, y


def ikbd(*packet):
    """RECEIVED: these bytes from the IKBD — a relative mouse packet is its header, dx and dy."""
    return IKBD_BYTES, bytes(byte & aes.BYTE_MASK for byte in packet)


def ticked(count):
    """RECEIVED: `count` ticks of the system timer — time passing at the idle, a 200th of a second each."""
    return TICKS, count


MFP_LEVEL = 6                           # the 68901's interrupt priority: the ACIAs' line and Timer C both
SR_IPL_SHIFT = 8                        # the status register's interrupt mask, bits 8-10 (`addrs.SR_IPL_MASK`)
OPEN_TO_INTERRUPTS = addrs.SR_IPL_MASK | SR_SUPERVISOR      # of a status word: what says who may interrupt it


class _Receiving:
    """WHAT A MACHINE AT ITS IDLE — OR STOPPED AT A NAMED STOP (`continued`'s `at`) — RECEIVES, taken over `memory` IN
    PLACE (above), each interrupt the ROM's own handler entered from the machine's own vector (`aes_switch`'s staged
    entry: the exception frame, then the handler) and its stores laid in. `status`: the status register the machine
    stands with there — AN INTERRUPT IS REFUSED BY
    NAME where its mask does not let that level in: a machine whose dispatcher left the mask at 6 or 7 hears no
    keyboard and no timer, and a model that ran the handler all the same would hide a dead machine. `stored`: every
    address the handlers stored at (the harness's own stack band apart)."""

    def __init__(self, memory, status):
        self._memory, self._status, self.stored = memory, status, set()

    def _interrupted(self, vector, what, **seeds):
        masked = (self._status & addrs.SR_IPL_MASK) >> SR_IPL_SHIFT
        if masked >= MFP_LEVEL:
            raise Refused(f"the machine stands where it receives (its idle, or the named stop it is continued at) with "
                          f"the interrupt mask at {masked}: {what} — an MFP interrupt, level {MFP_LEVEL} — is never "
                          f"taken. On iron this machine is dead")
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

    def _tick(self):
        self._interrupted(addrs.VECTOR_TIMER_C, "the system timer's tick", psg_seed=aes_switch.QUIET_PSG)

    def _ticked_until_the_click_resolves(self):
        for _tick in range(MOST_CLICK_TICKS):
            if not case.word_in(self._memory, aes.AES_GL_CLICK_TICKS):
                return
            self._tick()
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
            elif kind == TICKS:
                for _tick in range(*what):
                    self._tick()
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


TRAMPOLINE = "ub_trampoline"


def _parmblk_handed_the_trampoline(memory, sp):
    """`(the object, the USERBLK's parameter)` of the PARMBLK ub_trampoline is handed: the longword above its return
    address names it, on whichever shore — the desk's own draw code is its caller on both."""
    block = case.long_in(memory, sp + LONG_BYTES) & BUS
    return case.word_in(memory, block + aes.PARM_OBJECT), case.long_in(memory, block + aes.PARM_PARM)


def trampoline_stops(ours=None):
    """`{PC: (TRAMPOLINE, the reader of its frame there)}`: THE DESK'S USER-BLOCK TRAMPOLINE'S ENTRY (band 5 wave 4) —
    the ROM's, and, on a machine whose door maps the trampoline's slot (`aes_event.USERBLK_TRAMPOLINE_SLOT`: no door
    does before wave 4's activation), the blob's own. What a continued run is watched to ARRIVE at: a G_USERDEF
    object of a desk window drawn (a drive's window in the text view)."""
    stops = {aes_event.USERBLK_TRAMPOLINE: (TRAMPOLINE, _parmblk_handed_the_trampoline)}
    for part in (ours.door if ours is not None else ()):
        if part.what == aes_event.USERBLK_TRAMPOLINE_SLOT.what:
            stops.update({entry: (TRAMPOLINE, _parmblk_handed_the_trampoline) for _rom, entry in part.mapping})
    return stops


# ---- BEGIN band 6 wave 0, slice H: A RECEPTION AT A NAMED STOP (ruling W6-R10; the design's 3.3) --------------------------------
# A RUN THAT WAITS FOR A HAND WITHOUT IDLING has no idle to be continued from: the desk's file viewer polls the console
# through GEMDOS until a key comes, and the AES's rubber box (gr_stilldn under gr_rubwind) asks ev_multi with the
# button held and is always ready — `continued` refuses both by name (the dispatcher spins). What a hand does there is
# what it does at an idle, delivered WHILE THE LOOP TURNS: so a continuation may END AT A NAMED STOP (`until`: the
# run's first arrival at that address — a loop's own instruction, named by its caller and held to the ROM's bytes by
# its battery; an idle that comes first is refused by name) and a boot that STANDS AT ONE may be continued FROM IT
# (`at`: the address it stands at, said by the caller — a boot that stands elsewhere, or at an idle, is refused by
# name). The reception is taken as every other is — the ROM's own handlers, from the machine's own vectors, the
# interrupt refused where the mask the stop stands at would not let it in — between two instructions of the loop,
# which is one of the phases a machine has. Nothing of the AES's or the desk's state is touched.
def _vet_stands_where_it_is_continued_from(boot, at):
    """`boot` stands AT ITS IDLE (`at` None) or STOPPED AT THE NAMED STOP `at` — or the continuation is refused by name."""
    pc = boot.registers["pc"] & BUS
    if at is None and boot.idle is None:
        raise Refused("a boot stopped before its first idle is continued by nothing: it stands at no idle")
    if at is not None and (boot.idle is not None or pc != at):
        raise Refused(f"A RECEPTION AT A NAMED STOP is taken where the machine STANDS STOPPED THERE: this one stands at "
                      f"{pc:#x}" + (f", the idle of {boot.idle} dispatcher" if boot.idle is not None else "")
                      + f" — not at {at:#x}")

# ---- END band 6 wave 0, slice H -----------------------------------------------------------------------------------------------


def continued(boot, received, budget=CONTINUED_INSNS, until=None, at=None, watches=None):
    """`_continue`, KEPT — ITS REFUSAL TOO (`_continued_or_its_refusal`): raises `Refused` with the reason the run
    was refused for when it was made."""
    answer = _continued_or_its_refusal(boot, received, budget, until, at, watches)
    if isinstance(answer, KeptRefusal):
        raise Refused(answer.reason)
    return answer


# A REFUSAL IS AN ANSWER OF THE ARGUMENTS as much as a machine is: every `Refused` of a continuation is decided by the
# machine, the reception, the budget and the stops. The callers that PROBE with one (`aes_deskdir.in_place`: the hop
# to the next trap, to a named stop, to the return — most of them refused) asked the ROM for the same refusals in
# every process, and a run refused at its budget is CONTINUED_INSNS instructions (measured, gate-speed pass
# 2026-10-15: 35 refused runs, 127 s, made again in each desk_show_file case). So the refusal is kept, its reason with
# it; any other exception keeps nothing, as before.
KeptRefusal = namedtuple("KeptRefusal", "reason")


@derived.kept
def _continued_or_its_refusal(boot, received, budget, until, at, watches):
    try:
        return _continue(boot, received, budget, until, at, watches)
    except Refused as refused:
        return KeptRefusal(str(refused))


def _continue(boot, received, budget=CONTINUED_INSNS, until=None, at=None, watches=None):
    """`boot` — a machine at its idle — CONTINUED (above): what it `received` taken through the ROM's interrupt
    handlers, then the run to its next idle. `until`, `at` (band 6 wave 0): A NAMED STOP the run ENDS AT instead of an
    idle, and the one the boot STANDS AT instead of an idle (`_vet_stands_where_it_is_continued_from`'s section).
    `watches` (band 6 wave 4): `{PC: (a name, the reader of the frame there)}` the run is watched at BESIDE the
    handlers — an ARGUMENT, so a derivation's key holds it (`aes_deskdisk`'s floppy doors: a run watched there is
    another question than one that is not).
    A `Boot` again: the megabyte and the registers THERE, that run's own
    cost, polls, stores and streams, whose `idle` it ended at, and `observed` — `(the handler, (mx, my))` for each
    call of a screen manager's handler (`handler_stops`), in order, whichever shore's ctlmgr made it, and
    `(TRAMPOLINE, (the object, its USERBLK's parameter))` for each arrival at the desk's user-block trampoline
    (`trampoline_stops`). THE DEVICE MODEL IS THE BOOT'S (`Floppy`: the driver's four entries, the forced change).
    REFUSED BY NAME: a reception the idle's interrupt mask would never let in (`_Receiving`); and, on a machine whose
    screen manager is ours, A CONTINUATION THAT REACHES THE BLOB (`_vet_the_blob_was_not_reached`: the blob lies in
    memory GEMDOS believes free — a row's chain may not Malloc or Pexec its way into it)."""
    _vet_stands_where_it_is_continued_from(boot, at)
    ours = blob_of(boot)
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = boot.ram
    for rom_at, data in (ours.rom if ours is not None else ()):  # the ROM data a staging mapped for the blob (`restaged`)
        memory[rom_at:rom_at + len(data)] = data
    receiving = _Receiving(memory, boot.registers["sr"]).all_of(received)
    floppy = Floppy(memory, boot.disk, boot.drive_b)
    run = _Run(memory, floppy, budget, until=until, ours=ours,
               observing={**handler_stops(ours), **trampoline_stops(ours), **(watches or {})}, printer=boot.printer)
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
    _vet_nothing_stored_under_the_rom_s_shadow(boot.ram, memory, writes, "THE CONTINUATION")
    if ours is not None:
        harness_s = {at for start, data in run.laid.items() for at in range(start, start + len(data))}
        _vet_the_blob_was_not_reached(memory, ours, {*writes, *receiving.stored, *harness_s})
        vet_the_door_stands(memory, ours, "where the continuation ends")
    return boot._replace(ram=bytes(memory[:RAM_BYTES]), registers=registers, disk=bytes(floppy.disk),
                         instructions=result["ninsns"], cycles=result["cycles"], polls=run.polls, blanks=run.blanks,
                         floppy=tuple(floppy.calls), io_reads=streams[0], hardware_reads=streams[1],
                         hardware_writes=streams[2], stored=run.stored(writes), bus_error_frame=run.frame,
                         writes_truncated=truncated, idle=run.idle, observed=tuple(run.observed),
                         **surfaced(floppy, streams[1], run.printed))


continued.derive = _continue            # the run made here and now, never kept (`kept`'s own attribute, as it was)


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
# BEHIND A DOOR (band 5 wave 3) THE SAME CLASSES ARE PER PROCESS — every program the door took runs our event layer as
# the screen manager does, and parks through our dispatcher — and ONE MORE, the parked buffer's address:
#   * each program's SAVED CONTEXT and its STACK (as the screen manager's: `uda_context_drop`; the span the stop
#     found, from its UDA's state block to psetup's frame's end);
#   * A WAIT'S PARAMETER THAT IS AN ADDRESS IN THE WAITER'S OWN STACK: an EVB on a program's list whose parameter
#     longword names a place INSIDE THAT PROGRAM'S STACK ON BOTH MACHINES (a message wait keeps its buffer's QPB, a
#     local of the waiting routine — two builds' frames, two addresses). Named only where both machines hold such an
#     address there: an EVB whose parameter differs otherwise is a difference. AND ONLY WHERE THE TWO ADDRESSES
#     DIFFER (the door diet, wave 3: the build's frames above a message wait's QPB now sum to what the ROM's do, and
#     the two machines hold THE SAME address there — a class that excused nothing would be one nobody needs).
#   * the VECTORS are code addresses: MAPPED back (`mapped_back`), never dropped.
PROGRAM_CONTEXT, PROGRAM_STACK = "{}'s saved context in its UDA", "{}'s stack: dead below its parked stack pointer, live frames above"
PARKED_ADDRESS = "{}'s wait at {:#x}: its parameter, an address in its own stack"
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
    for program in (taken.door.programs if taken.door else ()):
        classes.update(_of_a_program(rom, ours, program))
    (mask_lo, mask_hi, _mask_why), = aes.LINE_F_MASK_WINDOW
    return classes, {LINE_F_MASK: (mask_lo, mask_hi), TRAP_SAVE_FRAME: trap_save_frame(ours)}


def _of_a_program(rom, ours, program):
    """The classes of ONE PROGRAM a door took (above), `{class: (lo, hi)}`, through the machines' own pointers."""
    name, (lo, top) = program.name.decode().strip(), program.stack
    uda = ours.long(program.pd + aes.PD_UDA) & BUS
    if rom.process(program.pd)._replace(events=()) != ours.process(program.pd)._replace(events=()):
        raise Refused(f"the two machines' {name} are not one process: {rom.process(program.pd)} and {ours.process(program.pd)}")
    (context_lo, context_hi, _why), = aes_switch.uda_context_drop(uda)
    classes = {PROGRAM_CONTEXT.format(name): (context_lo, context_hi), PROGRAM_STACK.format(name): (lo, top)}
    for evb in ours.process(program.pd).events:
        slot = evb + aes.EVB_PARM
        if all(lo <= each.long(slot) & BUS < top for each in (rom, ours)) and rom.long(slot) != ours.long(slot):
            classes[PARKED_ADDRESS.format(name, evb)] = (slot, slot + LONG_BYTES)
    return classes


def differing_runs(one, other):
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
    the screen manager's entry, where a slot holds it; the longwords its door mapped) — what a takeover machine is
    compared as. OF A MACHINE AS ITS TAKEOVER LEFT IT: where a continuation behind THE DOOR has run OUR glue, code
    addresses have TRAVELLED out of those longwords (our fork functions into the fork queue, the trampoline into the
    desk's USERBLKs) — such a machine is compared through the registry itself (`tier3.mapped_back`:
    `test_aes_boot_w4.py`), and compared here it differs there by name."""
    ram = bytearray(machine.ram)
    if machine.ours is not None:
        _mapped(ram, aes_event.SCREEN_MANAGER_ENTRY.slots, {machine.ours.entry: ROM_ENTRY})
    for slot, (rom, entry) in (machine.door.vectors.items() if machine.door else ()):     # ...and a door's vectors
        _mapped(ram, (slot,), {entry: rom})
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
    return Compared(differing_runs(theirs, bytes(mine)), within)


def noised(machine, spans, seed):
    """`machine` with every byte of `spans` (`(lo, hi)` each) replaced by NOISE that differs from it: the machine a
    dead span is proved dead on — its continuation is the plain machine's."""
    return Machine(machine.boot._replace(ram=noise_over(machine.ram, spans, seed)))


def noise_over(ram, spans, seed):
    """The megabyte `ram` with every byte of `spans` replaced by noise that differs from it: bytes."""
    generator, noisy = random.Random(seed), bytearray(ram)
    for lo, hi in spans:
        for at in range(lo, hi):
            noisy[at] ^= generator.randrange(1, 256)
    return bytes(noisy)


def restaged(machine, memory, rom=()):
    """`machine` WITH THE MEGABYTE OF `memory` — A LABELLED STAGING, its author's to justify (a routine laid under a
    trap, a tree's object changed) — and, on a machine whose screen manager is ours, ITS BLOB AS `memory` HOLDS IT: the
    `Ours` it carries is given those bytes, so a staging that patches the blob's own text (the build's VDI linked
    under `trap #2`) is the blob a continuation then holds untouched (`_vet_the_blob_was_not_reached`). The entry,
    the poll, the idle and the handlers stay where the ELF placed them: a staging that moves code is not this.
    `rom`: the ROM DATA the staging mapped, DECLARED by its author as `(address, length)` each — a machine keeps its
    megabyte, not its ROM: what `memory` holds there is carried with the blob and laid again in every continuation.
    Refused on a machine whose screen manager is the ROM's: its ROM is the ROM."""
    assert not rom or machine.ours is not None, "ROM data is mapped for a blob: this machine's screen manager is the ROM's"
    boot = machine.boot._replace(ram=bytes(memory[:RAM_BYTES]))
    if machine.ours is not None:
        ours = machine.ours
        mapped = tuple((at, bytes(memory[at:at + length])) for at, length in rom)
        staged = ours._replace(image=bytes(memory[ours.base:ours.base + len(ours.image)]), rom=mapped)
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


# ---- THE SERVED DOOR (band 5 wave 4, ruling W4-R6): A ROUTINE ANSWERED AT ITS ENTRY — A LABELLED ARGUMENT CLASS -----------------
# THE ONE DOOR OF THIS HARNESS THROUGH WHICH A ROUTINE IS NOT RUN. deskmain returns on no machine made here (its return
# is a hand's: Quit, a program opened) and the shell's four built-ins are entered only for a request of the desk's —
# so gem_main's teardown, gem_entry's second pass, the shell's launch pass and sh_cmd's arms have NO MACHINE. What
# stands in is this: a boot STOPPED AT THE ROUTINE'S ENTRY (`booted(..., until=)`: the machine and the registers as
# its caller left them) and CONTINUED AS IF THE ROUTINE HAD RETURNED A WORD — the return address popped, D0's low word
# the answer; nothing else of the CPU or the machine is touched, because the routine did not run (D0's high word,
# Alcyon's scratch registers and the Line-F handler's mask word are as the caller left them: a real return would
# have left the routine's own there).
# IT IS A STAGING, AND LABELLED: the `Boot` it answers carries a `Served` for each routine answered (`Boot.served`,
# `Machine.served`) through every continuation, and a row made of such a machine says so in its name. It proves what
# THE CALLER does with an answer — on both shores, from the same stop — and nothing about the routine served.
# BEFORE THE ANSWER, `calls`: ROM routines CALLED over the stopped machine as a battery calls one (`aes.staged`: the
# frame and whatever the call's own `staging` pokes hold, in the call's image alone) and THEIR STORES laid in — how the
# shell's buffers come to hold what a real shel_write leaves, never a poke. WHOSE ROUTINE, on a machine whose blob is
# ours: THE ROM'S, on an OUR-BOOT machine — the call stands in for the desk's own, and the desk calls the AES through
# the ROM's Line-F table on both shores (ruling W4-R3): the same routine, the same stores, on either machine. Refused
# on a TAKEOVER machine, where nothing has said which it would be.
# REFUSED BY NAME (`served`): a boot that stands at no routine the door serves (an idle, another `until`); one that
# stands there in user mode; a caller that is not the shell — the return address is neither the ROM's own site of
# that call nor inside the machine's blob; an answer that is no word; a SECOND arrival at any routine the door serves
# before `until` (it would run the ROM's routine under a label that says it was served: serve it again, from a boot
# stopped there); the first idle before `until`; and whatever a continuation is refused for.
# `{the routine: (its name, the shell's ONE Line-F call word of it)}` — each held to the ROM's own bytes (the battery).
SERVED_ROUTINES = {
    addrs.AES_ROM_DESKMAIN: ("deskmain", 0xfeb1dc),
    addrs.AES_ROM_DESK_SHOW_FILE: ("the shell's built-in $fe (a file shown)", 0xfeb322),
    addrs.AES_ROM_DESK_PRINT_FILE: ("the shell's built-in $fd (a file printed)", 0xfeb356),
    addrs.AES_ROM_DESK_FORMAT: ("the shell's built-in $fc (Format)", 0xfeb372),
    addrs.AES_ROM_DESK_COPY_DISK: ("the shell's built-in $fb (the disk copy)", 0xfeb390)}
Served = namedtuple("Served", "routine at answer calls")
Served.__doc__ = """One routine answered at its entry: its name, its entry (`at`), the word answered, and the names of
the ROM routines called over the stopped machine before the answer."""


def _vet_stands_at_a_served_entry(boot):
    """`boot` stands STOPPED AT THE ENTRY OF A ROUTINE THE DOOR SERVES, called by the shell — or it is refused by name:
    answers `(the routine's name, its entry, the return address)`."""
    at, sp = boot.registers["pc"] & BUS, boot.registers["isp"]
    if boot.idle is not None or at not in SERVED_ROUTINES:
        raise Refused(f"THE SERVED DOOR ANSWERS A ROUTINE AT ITS ENTRY: this boot stands at {at:#x}"
                      + (f", the idle of {boot.idle} dispatcher" if boot.idle is not None else "")
                      + f" — at none of {[f'{each:#x}' for each in SERVED_ROUTINES]} (`booted(..., until=)`)")
    name, call = SERVED_ROUTINES[at]
    if not boot.registers["sr"] & SR_SUPERVISOR:
        raise Refused(f"{name} is entered in user mode: the shell runs it on its own supervisor stack, and the "
                      f"answer would pop a return address off another")
    back = case.long_in(boot.ram, sp) & BUS
    _vet_the_shell_called(name, call, back, blob_of(boot))
    return name, at, back


def _vet_the_shell_called(name, call, back, ours):
    """The routine `name` would return to `back`: the ROM's own site of that call (the word after its Line-F call
    word at `call`) or, on a machine whose blob is `ours`, a place in the blob — else refused by name."""
    if back != call + WORD_BYTES and not (ours is not None and whose(back, ours) == OURS):
        raise Refused(f"{name} was not called by the shell: it would return to {back:#x}, neither the ROM's own site "
                      f"({call:#x}, a Line-F call word) nor a place in this machine's blob")


def served_where_it_stands(memory, sp, answer, ours):
    """THE SERVED DOOR'S ACT, IN PLACE: a run in flight stands STOPPED AT THE ENTRY of a routine of `SERVED_ROUTINES`
    (a watch's stop: `memory`, the stack pointer `sp`; `ours` the blob the machine holds, or None) — vetted as a
    stopped boot is (supervisor state, called by the shell, a word answered), then the return address popped and D0's
    low word the `answer`, on the CPU where it stands; nothing else is touched. Answers its `Served` (no calls: a
    routine cannot be called over a machine whose run is in flight). What a run watched on both shores serves a
    built-in of the desk's by, mid-stretch (`aes_ourboot.Pass.serving`)."""
    at = _register("pc") & BUS
    if at not in SERVED_ROUTINES:
        raise Refused(f"THE SERVED DOOR ANSWERS A ROUTINE AT ITS ENTRY: the run stands at {at:#x} — at none of "
                      f"{[f'{each:#x}' for each in SERVED_ROUTINES]}")
    name, call = SERVED_ROUTINES[at]
    if not _register("sr") & SR_SUPERVISOR:
        raise Refused(f"{name} is entered in user mode: the shell runs it on its own supervisor stack, and the "
                      f"answer would pop a return address off another")
    if not -0x8000 <= answer <= aes.WORD_MASK:
        raise Refused(f"{name} answers a word: {answer:#x} is none")
    back = case.long_in(memory, sp) & BUS
    _vet_the_shell_called(name, call, back, ours)
    _set_register("d0", _register("d0") & ~aes.WORD_MASK & LONG_MASK | answer & aes.WORD_MASK)
    _set_register("pc", back)
    _set_register("a7", sp + LONG_BYTES)
    return Served(name, at, answer & aes.WORD_MASK, ())


def _called_over(memory, name, arguments, pokes):
    """THE ROM'S OWN ROUTINE `name` CALLED OVER `memory` in place, as a battery calls one: its frame of `arguments`
    and the call's own staging (`pokes`) in the call's image alone, ITS STORES LAID IN. Answers what it stored."""
    staged = aes.staged(name, arguments, case.merge_pokes({0: bytes(memory[:RAM_BYTES])}, dict(pokes)))
    _final, writes, registers = emu.run(make_image(staged), getattr(addrs, name))
    rom_bench.vet_the_run_just_made(f"{name}, called over a stopped machine before a served answer")
    if registers.get("writes_truncated"):
        raise Refused(f"{name}'s run overflowed the write ledger: what it stored is not known")
    stored = case.written_by(writes)
    for at, data in stored.items():
        memory[at:at + len(data)] = data
    return stored


def _refusing_a_second_arrival(name, until):
    def refused(_memory, _sp):
        raise Refused(f"THE RUN ARRIVED AT {name} AGAIN before "
                      + (f"{until:#x}" if until else "an idle")
                      + ": the ROM's own routine would run under a label that says it was served — stop there "
                        "(`until`) and serve it again")
    return refused


def answered_at_its_entry(boot, answer, calls=()):
    """THE SERVED DOOR'S ONE ACT (above), without the run that follows it: `boot` — stopped at the entry of a routine
    of `SERVED_ROUTINES` — vetted, `calls` made over its machine, and the routine ANSWERED the word `answer`:
    `(the routine's name, its entry, the sixteen megabytes the run goes on over, what the calls stored `{address:
    bytes}`, the register file it goes on with)`. Each refusal is by name (above). What `served` makes its run from,
    and what a measurement that watches such a run on both shores makes its own from (`aes_ourboot.py`)."""
    name, at, back = _vet_stands_at_a_served_entry(boot)
    if not -0x8000 <= answer <= aes.WORD_MASK:
        raise Refused(f"{name} answers a word: {answer:#x} is none")
    ours = blob_of(boot)
    if calls and boot.takeover is not None:
        raise Refused(f"a routine called over a TAKEOVER machine, before {name} is answered: whose routine — the ROM's "
                      f"or the blob's — nothing has said there, and this door calls the ROM's (on an our-boot machine "
                      f"it stands in for the desk's own call, which is the ROM's on both shores: ruling W4-R3)")
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = boot.ram
    for rom_at, data in (ours.rom if ours is not None else ()):
        memory[rom_at:rom_at + len(data)] = data
    called = {}
    for routine, arguments, pokes in calls:
        called.update(_called_over(memory, routine, arguments, pokes))
    answered = {**boot.registers, "pc": back, "isp": boot.registers["isp"] + LONG_BYTES,
                "d0": boot.registers["d0"] & ~aes.WORD_MASK & LONG_MASK | answer & aes.WORD_MASK}
    return name, at, memory, called, answered


@derived.kept
def served(boot, answer, until=None, calls=(), budget=BOOT_INSNS):
    """THE SERVED DOOR (above): `boot` — stopped at the entry of a routine of `SERVED_ROUTINES` — continued as if that
    routine had answered the word `answer`, to its first arrival at `until` (None: to the first idle). `calls`:
    `((an addrs name, its arguments, its staging pokes), ...)`, the ROM's routines called over the stopped machine
    first. A `Boot`: the megabyte and the registers THERE, that run's own cost and streams, and `served` — THE LABEL,
    one `Served` longer. Each refusal is by name (above)."""
    name, at, memory, called, answered = answered_at_its_entry(boot, answer, calls)
    ours = blob_of(boot)
    floppy = Floppy(memory, boot.disk, boot.drive_b)
    again = {entry: (each, _refusing_a_second_arrival(each, until)) for entry, (each, _call) in SERVED_ROUTINES.items()
             if entry != until}
    run = _Run(memory, floppy, budget, until=until, ours=ours,
               observing={**handler_stops(ours), **trampoline_stops(ours), **again}, printer=boot.printer)
    try:
        result = run.to_an_idle(answered, _io_seed(boot.io))
        registers = _registers_now()
        writes, truncated = emu.bench_writes(memory)
        streams = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
    finally:
        _CPU.m68k_set_irq(NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"a boot's run on from {name}, served at its entry")
    if truncated:
        raise Refused("the served run's write ledger saturated: what it stored is not known")
    _vet_nothing_stored_under_the_rom_s_shadow(boot.ram, memory, writes, "THE SERVED RUN")
    run.laid.update(called)
    if ours is not None:
        harness_s = {each for start, data in run.laid.items() for each in range(start, start + len(data))}
        _vet_the_blob_was_not_reached(memory, ours, {*writes, *harness_s})
        vet_the_door_stands(memory, ours, "where the served run ends")
    label = Served(name, at, answer & aes.WORD_MASK, tuple(routine for routine, _arguments, _pokes in calls))
    return boot._replace(ram=bytes(memory[:RAM_BYTES]), registers=registers, disk=bytes(floppy.disk),
                         instructions=result["ninsns"], cycles=result["cycles"], polls=run.polls, blanks=run.blanks,
                         floppy=tuple(floppy.calls), io_reads=streams[0], hardware_reads=streams[1],
                         hardware_writes=streams[2], stored=run.stored(writes), bus_error_frame=run.frame,
                         writes_truncated=truncated, idle=run.idle, observed=tuple(run.observed),
                         served=(*boot.served, label), **surfaced(floppy, streams[1], run.printed))


# ---- THE SCAN: NO LONGWORD HOLDS, BY VALUE, THE ROM'S COPY OF A ROUTINE THE REGISTRY DECLARES (band 5 wave 4; the design's §3.4) ----
# WHAT A DOOR MUST MAP is decided by the machine, not by a list someone keeps: every longword of the megabyte that holds
# THE ROM'S ADDRESS OF A ROUTINE THE REGISTRY DECLARES (`aes_event`'s `RelocatedCode`s, mapped or pending — the routines
# the ROM stores BY VALUE and a build stores as its own; and `gem_entry`) is found by a scan (`entries_held_by_value`)
# and said to lie in one of four places, each through the machine's own pointers:
#   * A SLOT OF THE REGISTRY (`IN_A_SLOT`): a declared longword or one a walk finds (`aes_event.slots_over`) — on a
#     machine called ours, an entry the door left the ROM's: THE FINDING;
#   * `gem_entry` (`THE_BIOS_S`): `exec_os`, the AES basepage's text base, the launch's frames — stored by the BIOS,
#     by no row of ours, and so NOT MAPPED on either shore (the policy's own rule, ruling W4-R1);
#   * A DEAD SPAN (`dead_by_nature`): a process's stack below its parked stack pointer, the dispatcher's below the
#     idle's, the BIOS's last register-save frame, the interrupt glues' own stacks, a fork-queue entry outside the
#     queue's live run — residue of code that ran, which nothing reads before it writes;
#   * ELSEWHERE (`UNACCOUNTED`): a live longword no declaration knows — a slot the registry is missing.
# The blob's own span is not scanned (it is code: a ROM address in it is a constant of the build, held by the census).
# THE VET (`vet_no_entry_is_held_as_the_rom_s`): a machine called ours with a finding or an unaccounted holder is
# REFUSED BY NAME, every one listed. BEHIND THE DOOR (the full flip) IT PASSES at every door machine's idle and where a
# continuation ends; behind the trap door's three alone — wave 3's narrow door — it refuses, naming the six longwords
# the full flip's four parts map (`test_aes_boot_w4.py` pins both, so a holder added or mapped moves a test).
# WHAT THE SCAN IS NOT (band 5 wave 4, slice F's fix pass — the second review's finding 1):
#   * IT IS A LIST OF SEVENTEEN VALUES (`routines_by_value`: the sixteen routines the registry's declarations name, and
#     gem_entry), NOT THE BUILD'S SYMBOL SET: a ROM routine the registry does not declare passes it wherever it lies —
#     in a live longword nobody declared, and IN A LONGWORD OF THE DOOR ITSELF. What refuses a wrong value in a door
#     longword is `vet_the_door_stands` (anything there but the blob's own entry). On every door machine the reviewer's
#     wider scan found twelve live longwords holding OTHER ROM routines, none of which a door can map (the Line-F
#     table's first nine entries in gem_entry's RAM copy; aes_dsptch as a saved register; dos_alloc twice; a resume PC
#     of the desk — `test_aes_boot_w4.py` names them): the scan over every named entry is an option put to the user.
#   * IT COMPARES THE WHOLE LONGWORD: a routine's address under a non-zero top byte is another value to it.
#   * IT IS RUN AT AN IDLE AND WHERE A CONTINUATION ENDS, NOWHERE ELSE. At deskmain's entry a door machine still holds
#     the ROM's tick glue in the AES's contrl (`aes.AES_GSX_CONTRL_PTR`: the ROM's gsx_tick's hand-in from before the
#     takeover's stop, a slot of the registry a value TRAVELS through — no longword of the machine's own, so no door
#     maps it) and the scan refuses there, for that one longword; gone by the first idle.
IN_A_SLOT, UNACCOUNTED = "a slot of the registry: {}", "no slot of the registry and no dead span"
THE_BIOS_S = "gem_entry's address, stored by the BIOS: not mapped"
DEAD_PROCESS_STACK, DEAD_FORK_ENTRY = "{}'s stack below its parked stack pointer", "a fork-queue entry outside the queue's live run"
# ...and THE INTERRUPT GLUES' OWN STACKS (`aes/evdisp.h`: each glue parks the interrupted stack pointer and runs on a
# stack of the AES's own, from its top down — the button and motion glue's above the tick's words, the tick glue's
# above that): dead between interrupts. MEASURED: the VDI's mouse handler enters the button glue with ITS ADDRESS IN
# A1, and the glue's `movem.l d0-d2/a0-a2,-(sp)` leaves that longword on its stack after every button packet.
GLUE_STACK, TICK_STACK = "the button and motion glues' own stack, dead between interrupts", "the tick glue's own stack, dead between ticks"
_GLUE = aes.header_constants("evdisp.h")
GLUE_STACKS = {GLUE_STACK: (aes.AES_TIMER_COUNTDOWN + LONG_BYTES, _GLUE["AES_GLUE_STACK_TOP"]),
               TICK_STACK: (_GLUE["AES_GLUE_STACK_TOP"], _GLUE["AES_TICK_STACK_TOP"])}
Held = namedtuple("Held", "slot routine symbol where dead")
Held.__doc__ = """One longword of a machine that holds a ROM routine's address: its `slot`, the `routine` (the ROM's
address), the build's `symbol` for it (None: gem_entry), `where` it lies (above) and whether that is `dead`."""


def routines_by_value():
    """`{the ROM's routine: the build's symbol for it}` over every declaration of the registry, mapped or pending —
    and gem_entry (None: nothing of a build is mapped for it)."""
    declared = {rom: symbol for each in vars(aes_event).values() if isinstance(each, aes_event.RelocatedCode)
                for rom, symbol in each.symbols.items()}
    return {**declared, GEM_ENTRY: None}


def dead_by_nature(machine):
    """THE DEAD SPANS OF `machine` AT ITS IDLE (above), `{what: (lo, hi)}`, each through the machine's own pointers:
    every process's stack below its parked stack pointer, the dispatcher's dead frames, the BIOS's last register-save
    frame, the interrupt glues' own stacks, and each fork-queue entry outside the queue's live run."""
    ram, spans = machine.ram, {DEAD_DISPATCHER_FRAMES: (aes_event.DISPATCHER_STACK[0], machine.registers["isp"]),
                               TRAP_SAVE_FRAME: trap_save_frame(machine), **GLUE_STACKS}
    for pd, slot in aes_event.first_entry_frames(ram):
        uda = case.long_in(ram, pd + aes.PD_UDA) & BUS
        spans[DEAD_PROCESS_STACK.format(_name_of(ram, pd).decode().strip() or f"the PD at {pd:#x}")] = (
            uda + aes.UDA_STATE_BYTES, slot - FRAME_PC)
    head, count = machine.word(aes.AES_FORK_HEAD), machine.word(aes.AES_FORK_COUNT)
    live = {(head + nth) % aes.AES_FORK_ENTRIES for nth in range(count)}
    for index in range(aes.AES_FORK_ENTRIES):
        if index not in live:
            entry = aes.AES_FORK_QUEUE + index * aes.FORK_ENTRY_BYTES
            spans[f"{DEAD_FORK_ENTRY} ({index})"] = (entry, entry + aes.FORK_ENTRY_BYTES)
    return spans


def _slots_declared(ram):
    """`{slot: the declarations that name it}` over the machine `ram`: every declaration's longwords — declared,
    walked, and the machine's own vector."""
    declared = {}
    for each in vars(aes_event).values():
        if isinstance(each, aes_event.RelocatedCode):
            for slot in (*aes_event.slots_over(each, ram), *aes_event.THE_MACHINE_S_VECTORS.get(each.what, ())):
                declared.setdefault(slot, []).append(each)
    return declared


def _where(slot, routine, declared, dead):
    """`(where, is it dead)` of one holder: a dead span first (a stale fork entry is a slot too, and dead); then the
    declaration that names the slot — the one that names the routine too, where several share a longword."""
    for what, (lo, hi) in dead.items():
        if lo <= slot < hi:
            return what, True
    if routine == GEM_ENTRY:
        return THE_BIOS_S, False
    naming = sorted(declared.get(slot, ()), key=lambda each: routine not in each.symbols)
    return (IN_A_SLOT.format(naming[0].what), False) if naming else (UNACCOUNTED, False)


def entries_held_by_value(machine):
    """THE SCAN (above) over `machine` at its idle: a `Held` for every longword at an even address, outside the
    machine's blob, that holds the ROM's address of a routine of `routines_by_value` — in address order."""
    ram, routines, dead = machine.ram, routines_by_value(), dead_by_nature(machine)
    slots = _slots_declared(ram)
    blob = (machine.ours.base, machine.ours.end) if machine.ours is not None else (0, 0)
    held = []
    for slot in range(0, RAM_BYTES - LONG_BYTES + WORD_BYTES, WORD_BYTES):
        value = case.long_in(ram, slot)
        if value in routines and not blob[0] <= slot < blob[1]:
            held.append(Held(slot, value, routines[value], *_where(slot, value, slots, dead)))
    return tuple(held)


def vet_no_entry_is_held_as_the_rom_s(machine):
    """THE VET (above): `machine`, called ours, holds NO ENTRY OF THE REGISTRY BY VALUE AS THE ROM'S in a live
    longword — gem_entry's, the BIOS's, apart — or it is refused by name, every holder listed. Answers the scan."""
    if machine.ours is None:
        raise Refused("a machine the ROM booted holds every entry as the ROM's: the scan vets a machine CALLED OURS")
    held = entries_held_by_value(machine)
    left = [each for each in held if not each.dead and each.where != THE_BIOS_S]
    if left:
        named = "; ".join(f"${each.slot:x} holds {each.routine:#x} (`{each.symbol}`): {each.where}" for each in left)
        raise Refused(f"A ROUTINE THE REGISTRY DECLARES IS HELD BY VALUE AS THE ROM'S on a machine called ours — {len(left)} "
                      f"longword(s): {named}. The door maps what it declares; these it left the ROM's")
    return held
