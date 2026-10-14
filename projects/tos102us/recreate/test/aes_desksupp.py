"""UNIT J, drive_check, AT ITS ARRIVALS — band 6 wave 1b, group G2 (`src/desk/desksupp.c`, `test_desk_supp.py`).
HELD AT TIER 1, NOTHING BOUND.

drive_check reads a floppy's boot sector (XBIOS Floprd) and forces its media change (BIOS Rwabs through the disk
vector), between two Mallocs' worth of GEMDOS and the yields of desk_wait. A case is A ROW THAT SWITCHES over the
arrival's megabyte with THE ROM'S FLOPPY DRIVER REPLAYED on both shores — a LABELLED STAGING said in every id
(`DRIVER_REPLAYED`):
  * the sector Floprd read IN THE ROM'S OWN RUN IN PLACE is LAID where it reads it (the Malloc'ed buffer), and the
    read answers what that run's answered: on the ROM's shore the XBIOS's vector at a stub (`move.l #answer,d0 / rte`),
    on ours `desk_floprd_door` bound in the row's child;
  * the forced change answers what the run's did: the ROM's `hdv_rw` at a stub (`move.l #answer,d0 / rts`), ours the
    disk vectors' hook bound in the child;
  * GEMDOS's Malloc and Mfree are band 5's recording trap, scripted with the run's answers (`SCRIPTED`);
  * Drvmap is the machine's own BIOS on the ROM's shore, its C core (`bios_drvmap`) on ours.
"""
import ctypes
import os
from collections import namedtuple
import struct
import sys

import aes
import aes_boot
import aes_deskapp as da
import aes_gemdosif as gd
import aes_switch
import case
import gemdos_fs as fs
import vdi
from address_hook import bind_pointer
from harness import addrs

WORD, IMAGE = vdi.WORD_ARG, vdi.IMAGE_ARG
DRIVE_CHECK = "AES_ROM_DRIVE_CHECK"
aes.declare_alcyon(DRIVE_CHECK, None, (IMAGE, WORD))
UNIT_J = (DRIVE_CHECK,)
DRIVER_REPLAYED = "THE ROM'S FLOPPY DRIVER REPLAYED: its sector laid, its two answers staged"

# ---- the ROM's own run in place: where each of its calls returns ------------------------------------------------------------
FLOPRD_BACK, RWABS_BACK = 0xfe1b62, 0xfe1bb2       # the words after the two door calls (`desk/desksupp.h`'s sites)
SECTOR_BYTES = 512
Replay = namedtuple("Replay", "malloc floprd sector rwabs mfree returned")


def in_place(arrived):
    """THE ROM'S OWN RUN IN PLACE of drive_check from its arrival, on A FLOPPY'S READ THAT SUCCEEDS AT ONCE: Malloc's
    answer (at GEMDOS's handler, then where its exception returns), Floprd's answer and the sector it read into the
    buffer, Rwabs's answer, Mfree's, and the `Boot` at its own return. Refused by name where a read is retried."""
    entry, sp = da.entry_of(DRIVE_CHECK), da.stack_pointer(arrived.boot)
    handler = case.long_in(arrived.boot.ram, addrs.VECTOR_TRAP_GEMDOS) & da.BUS

    def gemdos_answer(boot, stands_at):
        boot = aes_boot.continued(boot, (), arrived.budget, handler, stands_at)
        assert da.stack_pointer(boot) < sp, "the trap is drive_check's own"
        back = case.long_in(boot.ram, da.stack_pointer(boot) + aes.WORD_BYTES) & da.BUS
        return aes_boot.continued(boot, (), arrived.budget, back, handler), back

    alloc, at = gemdos_answer(arrived.boot, entry)
    read = aes_boot.continued(alloc, (), arrived.budget, FLOPRD_BACK, at)
    buffer = alloc.registers["d0"] & da.BUS
    answer = read.registers["d0"] & aes.WORD_MASK
    if answer not in (0, aes.WORD_MASK & -14):
        raise aes_boot.Refused(f"{da.label_of(arrived)}: Floprd answered {answer:#x}: eralert's retry, no arm a case replays")
    forced = aes_boot.continued(read, (), arrived.budget, RWABS_BACK, FLOPRD_BACK)
    freed, at = gemdos_answer(forced, RWABS_BACK)
    back = aes_boot.continued(freed, (), arrived.budget, arrived.returns_to, at)
    assert da.stack_pointer(back) == sp + aes.LONG_BYTES
    return Replay(alloc.registers["d0"], answer, bytes(read.ram[buffer:buffer + SECTOR_BYTES]), forced.registers["d0"],
                  freed.registers["d0"], back)


# ---- the ROM's shore: two stubs in the group's band ---------------------------------------------------------------------------
STUBS_AT = da.BAND_AT + 0x1C0
MOVE_L_IMMEDIATE_D0, RTE, RTS = b"\x20\x3c", b"\x4e\x73", b"\x4e\x75"
STUB_BYTES = 8
assert da.GEMDOS.end <= STUBS_AT and STUBS_AT + 2 * STUB_BYTES <= da.BAND_AT + da.BAND_BYTES - 0x10


def staged(replay):
    """The ROM's shore's staging: the sector laid at the buffer Malloc answers, the XBIOS's vector at Floprd's answer,
    `hdv_rw` at Rwabs's, and band 5's GEMDOS recorder scripted with Malloc's and Mfree's."""
    floprd_stub, rwabs_stub = STUBS_AT, STUBS_AT + STUB_BYTES
    return case.merge_pokes(
        {replay.malloc & da.BUS: replay.sector},
        {floprd_stub: MOVE_L_IMMEDIATE_D0 + struct.pack(">i", aes.signed(replay.floprd)) + RTE,
         rwabs_stub: MOVE_L_IMMEDIATE_D0 + struct.pack(">I", replay.rwabs & aes.LONG_MASK) + RTS,
         addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", floprd_stub), addrs.HDV_RWABS: struct.pack(">I", rwabs_stub)},
        gd.GEMDOS.pokes((replay.malloc, replay.mfree)))


# ---- ours: the child's two hooks --------------------------------------------------------------------------------------------
FLOPRD_DOOR = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint16,
                               ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16)
DISK_VECTOR_HOOK = "recreate_call_disk_vector"   # `gemdos/fs.h`'s, as `gemdos_fs.DISK_HOOK` binds it in-process
CHILD_REPLAY_REFUSED = 8                # the child's exit status where a call no replay serves is made
_CHILD_TRAMPOLINES = []


def bind_replay_in_a_child(lib, floprd, rwabs, read_frame, change_frame):
    """IN THE ROW'S CHILD: `desk_floprd_door` answering `floprd` (the sector is laid already) and the disk vectors'
    hook answering Rwabs `rwabs` — EACH CALL'S FRAME HELD to the ROM's (`read_frame`: buffer, device, sector, track,
    side, count; `change_frame`: Rwabs's rwflag, buffer, count, record, device); any other call or frame ENDS the
    child by name."""
    def refused(why):
        print(why, file=sys.stderr, flush=True)
        os._exit(CHILD_REPLAY_REFUSED)

    def read(_buf, *frame):
        if tuple(frame) != tuple(read_frame):
            refused(f"drive_check's C read the floppy over {frame}, not the ROM's {read_frame}")
        return floprd

    def disk(_buf, function, *frame):
        if function != addrs.BIOS_RWABS_FN or tuple(frame) != tuple(change_frame):
            refused(f"drive_check's C asked the disk vectors for {function} {frame}, not Rwabs {change_frame}")
        return rwabs
    for symbol, kind, effect in (("desk_floprd_door", FLOPRD_DOOR, read), (DISK_VECTOR_HOOK, fs.DISK_CALL, disk)):
        trampoline = kind(effect)
        _CHILD_TRAMPOLINES.append(trampoline)
        bind_pointer(symbol, trampoline, lib)


# THE FRAMES THE ROM'S drive_check PUSHES (read off its body, `$fe1b40..$fe1bb0`): Floprd(buffer, 0, drive, 1, 0, 0, 1)
# and Rwabs(0, NULL, 2, 0, drive).
def read_frame(replay, drive):
    return (replay.malloc & aes.LONG_MASK, drive, 1, 0, 0, 1)


def change_frame(drive):
    return (0, 0, 2, 0, drive)


def row_of(arrived, replay, label=None, laid=()):
    """THE CASE: the row that switches over the arrival's megabyte, the driver replayed (above) — and `laid`, a
    labelled staging's layers, over it."""
    drive = arrived.arguments[0] - ord("A")
    source = (f"{gd.CHILD_DOORS}import aes_desksupp; aes_desksupp.bind_replay_in_a_child(lib, {aes.signed(replay.floprd)}, "
              f"{aes.signed(replay.rwabs, bits=32)}, {read_frame(replay, drive)!r}, {change_frame(drive)!r}); ")
    row = da.row_of(arrived, layers=(staged(replay), *laid), label=label)
    return row._replace(door=aes_switch.DoorUser(True, source))
