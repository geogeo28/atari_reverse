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
import functools
import os
from collections import namedtuple
import struct
import sys

import aes
import aes_boot
import aes_desk
import aes_deskapp as da
import aes_deskwin as w
import aes_event
import aes_fslib as fsl
import aes_gemdosif as gd
import aes_loader as ld
import aes_shell as sh
import aes_switch
import case
import gemdos
import gemdos_fs as fs
import isr
import vdi
from address_hook import bind_pointer
from harness import addrs

WORD, IMAGE = vdi.WORD_ARG, vdi.IMAGE_ARG
DRIVE_CHECK = "AES_ROM_DRIVE_CHECK"
aes.declare_alcyon(DRIVE_CHECK, None, (IMAGE, WORD))
UNIT_J = (DRIVE_CHECK,)
# ---- band 6 wave 2, group G3 (unit J) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_J (and its count) stays as it is
LONG = vdi.LONG_ARG
SIGNATURES_WAVE_2 = {
    "AES_ROM_DO_DIROPEN": (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD, LONG, LONG, LONG, LONG)),
    "AES_ROM_DO_DOPEN": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_DO_FOPEN": (aes.WORD_ANSWER, (LONG, WORD, WORD, LONG, LONG, LONG)),
    "AES_ROM_DESK_DO_FORMAT": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_CLOSE_WINDOW": (aes.WORD_ANSWER, (LONG,)),
    "AES_ROM_CLOSE_FOLDER": (aes.WORD_ANSWER, (LONG, WORD, LONG, LONG, LONG)),
    "AES_ROM_FUN_CLOSE": (aes.WORD_ANSWER, (LONG, WORD)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_J_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# FLIPPED at band 6 slice F3 (stage 2): the seven whole — none held.
UNIT_J_WAVE_2_HELD_AT_F3 = ()
# ---- end of group G3's wave-2 ----
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
STUBS_AT = da.GEMDOS.end                # (behind unit A's recorder, which ends at the band's $1D0)
MOVE_L_IMMEDIATE_D0, RTE, RTS = b"\x20\x3c", b"\x4e\x73", b"\x4e\x75"
STUB_BYTES = 8
assert da.GEMDOS.end <= STUBS_AT and STUBS_AT + 2 * STUB_BYTES <= da.BAND_AT + da.BAND_BYTES - 0x10


def floppy_staged(replay):
    """The ROM's shore's floppy: the sector laid at the buffer Malloc answers, the XBIOS's vector at Floprd's answer,
    `hdv_rw` at Rwabs's."""
    floprd_stub, rwabs_stub = STUBS_AT, STUBS_AT + STUB_BYTES
    return case.merge_pokes(
        {replay.malloc & da.BUS: replay.sector},
        {floprd_stub: MOVE_L_IMMEDIATE_D0 + struct.pack(">i", aes.signed(replay.floprd)) + RTE,
         rwabs_stub: MOVE_L_IMMEDIATE_D0 + struct.pack(">I", replay.rwabs & aes.LONG_MASK) + RTS,
         addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", floprd_stub), addrs.HDV_RWABS: struct.pack(">I", rwabs_stub)})


def staged(replay):
    """The ROM's shore's staging: the floppy (`floppy_staged`), and band 5's GEMDOS recorder scripted with Malloc's and
    Mfree's."""
    return case.merge_pokes(floppy_staged(replay), gd.GEMDOS.pokes((replay.malloc, replay.mfree)))


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


# ---- band 6 slice F2 (group G2): drive_check's ROW at an arrival — a row that switches with NO DOOR (measured: desk_wait's
# yields make no call of the event layer's door), over the arrival's machine (`aes_deskapp.switching_row`): the floppy
# replayed as Tier 1's, Malloc and Mfree answered by BAND 5's scripted trap (`aes_shell`, told Mfree at slice R8: the
# rows' convention), both said in the row's name. AES_BIOS_RETURN NAMED BY NATURE (`BIOS_DOOR_PARKED`): the C reaches
# trp13's `.S` through the shipped blob's glue, whose `jsr` parks THE GLUE'S return there where the ROM's door parks its
# caller's — F1's declared divergence (R9's kind, `test_the_bios_door_s_parked_return_is_named_by_trp13_alone`: no ROM
# instruction but trp13's own two reads it). Its three low bytes: the high byte is 0 on both shores, an address under
# 16 MB — equal, so compared, never named (each named byte must be one the ROM's run stores: the census,
# `aes_switching._its_own_by_nature`, which reads its write ledger since band 6 slice F3 stage 2's third fix pass).
BIOS_DOOR_PARKED = ((aes.AES_BIOS_RETURN + 1, aes.AES_BIOS_RETURN + aes.LONG_BYTES,
                     "AES_BIOS_RETURN: the shipped glue parks its own return, the ROM's door its caller's — read by trp13 alone"),)


def row_doors(replay, drive):
    """The row's child's doors: band 5's scripted trap's twins, and the floppy's two hooks (`bind_replay_in_a_child`)."""
    import aes_deskwin
    return (f"{aes_deskwin.SHELL_CHILD_DOORS}import aes_desksupp; aes_desksupp.bind_replay_in_a_child(lib, "
            f"{aes.signed(replay.floprd)}, {aes.signed(replay.rwabs, bits=32)}, {read_frame(replay, drive)!r}, "
            f"{change_frame(drive)!r}); ")


def register_row(arrived):
    """drive_check's case at `arrived`, REGISTERED as its row (above)."""
    replay, drive = in_place(arrived), arrived.arguments[0] - ord("A")
    return da.register_switching(arrived, door_user=False, answers=(replay.malloc, replay.mfree),
                                 layers=(floppy_staged(replay),), said=DRIVER_REPLAYED, doors=row_doors(replay, drive),
                                 also_dropped=BIOS_DOOR_PARKED)



# ==== BAND 6 WAVE 2 (group G3): GEMDOS AND THE FLOPPY REPLAYED UNDER THE WINDOWS' OPENERS AND CLOSERS ==================
# do_diropen reads a path (pn_active: Fsetdta, Fsfirst, Fsnext), do_dopen and do_fopen check a drive first
# (drive_check: Malloc, the boot sector's Floprd, the forced change's Rwabs, Mfree) and make it current (pro_chdir:
# Dsetdrv, Dsetpath) — under rows that switch. The host build has no GEMDOS of the floppy's, so A CASE OF ONE OF THEM
# RUNS BOTH SHORES OVER A REPLAY — A LABELLED STAGING, said in its id (REPLAYED):
#   * GEMDOS: `aes_fslib`'s replay (the ledger of every call, each answered from a script — D0, and for a search the
#     44 bytes the DTA holds after it), its handler laid in THIS GROUP'S OWN WINDOW (G3's: the fslib band's room is
#     160 bytes, and two more functions — pro_chdir's Dsetdrv and Dsetpath — make the handler 172), its DTA cell,
#     ledger and script fslib's own; the host twin the same over the C's image, bound in the row's child;
#   * THE SCRIPT IS THE ROM'S OWN RUN IN PLACE (`watched`: `aes_loader.run_on`, every `trap #1` of the AES's glue
#     watched — `__DOS`'s and dos_alloc's own — its answer and what GEMDOS stored, the DTA laid call by call);
#   * the floppy, where drive_check runs: drive_check's own replay (`in_place`, `floppy_staged`) at its arrival in
#     the same step, its two hooks bound in the child (`bind_replay_in_a_child`).
BUS = da.BUS
REPLAYED = "GEMDOS REPLAYED: the ROM's run in place's answers and DTAs"
REPLAYED_WITH_THE_FLOPPY = f"{REPLAYED}; {DRIVER_REPLAYED}"
DSETDRV, DSETPATH = addrs.GEMDOS_DSETDRV_FN, addrs.GEMDOS_DSETPATH_FN
REPLAY_ARGUMENT_BYTES = {**fsl.SESSION_ARGUMENT_BYTES, DSETDRV: aes.WORD_BYTES, DSETPATH: aes.LONG_BYTES}
REPLAY_HANDLER_AT = aes.SPAN.claim(0x7bf40, 0xC0, "test/aes_desksupp.py: group G3's GEMDOS replay handler (fslib's tables)")
assert len(fsl.replay_handler(REPLAY_ARGUMENT_BYTES)) <= 0xC0
sh.GEMDOS_LEDGERS.append(functools.partial(sh.GemdosLedger, REPLAY_HANDLER_AT, fsl.replay_handler(REPLAY_ARGUMENT_BYTES),
                                           fsl.LEDGER, REPLAY_ARGUMENT_BYTES, fsl.RECORDED_ARGUMENT_BYTES, fsl.DTA_CELL_AT))
WATCHED_INSNS = 6_000_000               # a window opened and drawn: do_dopen at A: File > Open runs ~2.1 M


@functools.cache
def watched(name, chain, nth=1, budget=WATCHED_INSNS):
    """THE ROM'S OWN RUN IN PLACE of the arrival, every GEMDOS call of the glue watched (`aes_loader.returned`): its
    `Ran` — and the DTA after each call, the arrival's DTA bytes with GEMDOS's stores laid call by call (`dtas`)."""
    arrived = w.arrival(name, chain, nth)
    stood = ld.stood_at(arrived.boot)
    return arrived, ld.returned(ld.arrival(name, stood), budget)


def gemdos_script(name, chain, nth=1):
    """THE SCRIPT (above): `((D0, the DTA's 44 bytes after a search, or none), ...)`, one per call of the run in place.
    The DTA is the one each Fsetdta names, followed from the arrival's bytes through every call's stores."""
    arrived, ran = watched(name, chain, nth)
    ram, dta, script = bytearray(arrived.boot.ram), None, []
    for call in ran.calls:
        for at, data in call.stored:
            ram[at:at + len(data)] = data
        if call.function == fsl.FSETDTA:
            dta = int.from_bytes(call.frame[:aes.LONG_BYTES], "big") & BUS
        searched = bytes(ram[dta:dta + fsl.DTA_BYTES]) if call.function in fsl.SEARCHES else fsl.NO_DTA
        script.append((call.answer, searched))
    return tuple(script)


def replay_pokes(script, handler_at=REPLAY_HANDLER_AT, argument_bytes=REPLAY_ARGUMENT_BYTES):
    """The trap vector at THIS GROUP'S handler, fslib's ledger empty, its DTA cell STALE, the script. `handler_at`,
    `argument_bytes`: another handler of fslib's tables, laid in its own span (band 6 W3a stage 3's, which tells two
    more functions' frames)."""
    assert len(script) <= fsl.REPLAY_CALLS, f"{len(script)} calls: more than the replay's band holds"
    entries = b"".join(struct.pack(">I", answer & aes.LONG_MASK) + filled for answer, filled in script)
    return {addrs.VECTOR_TRAP_GEMDOS: struct.pack(">I", handler_at),
            handler_at: fsl.replay_handler(argument_bytes), fsl.DTA_CELL_AT: struct.pack(">I", vdi.STALE_LONG),
            **fsl.LEDGER.staged(), **fsl.SCRIPT.staged(entries)}


def _replayed(function):
    """The handler's HOST TWIN for `function` (`aes_fslib._replayed`'s, over this group's functions)."""
    def handler(buf, arguments, _argument_bytes):
        entry, script = fsl.LEDGER.next(buf), fsl.SCRIPT.next(buf)
        frame = fsl.LEDGER.record(buf, entry, function, arguments, REPLAY_ARGUMENT_BYTES[function])
        if function == fsl.FSETDTA:
            isr.poke(buf, fsl.DTA_CELL_AT, frame[:aes.LONG_BYTES])
        if function in fsl.SEARCHES:
            isr.poke(buf, case.long_in(buf, fsl.DTA_CELL_AT) & BUS,
                     ctypes.string_at(ctypes.addressof(buf.contents) + script + aes.LONG_BYTES, fsl.DTA_BYTES))
        fsl.SCRIPT.step(buf, script)
        return case.long_in(buf, script)
    return handler


REPLAY_HANDLERS = {gemdos.rom_handler(function): _replayed(function) for function in REPLAY_ARGUMENT_BYTES}


def bind_gemdos_replay_in_a_child(lib):
    """IN THE ROW'S CHILD: the replay's host twins bound to GEMDOS's handlers (`aes_gemdosif.bind_handlers_in_a_child`);
    any other handler ENDS the child."""
    gd.bind_handlers_in_a_child(lib, REPLAY_HANDLERS, "the replay")


GEMDOS_REPLAY_DOORS = "import aes_desksupp; aes_desksupp.bind_gemdos_replay_in_a_child(lib); "


def floppy_replay(chain, nth=1):
    """drive_check's own replay at its `nth` arrival (from 1) of `chain`: a `Replay`, and the drive it reads."""
    arrived = da.arrival(DRIVE_CHECK, chain, nth - 1)
    return in_place(arrived), arrived.arguments[0] - ord("A")


def _replay_staged(each, floppy, script):
    """`(the replay's layers, its child's doors)` for the case: GEMDOS replayed — and the floppy where `floppy`."""
    layers = [replay_pokes(script or gemdos_script(each.name, each.chain, each.nth))]
    doors = GEMDOS_REPLAY_DOORS
    if floppy:
        replay, drive = floppy_replay(*floppy)
        layers.append(floppy_staged(replay))
        doors += (f"aes_desksupp.bind_replay_in_a_child(lib, {aes.signed(replay.floprd)}, {aes.signed(replay.rwabs, bits=32)}, "
                  f"{read_frame(replay, drive)!r}, {change_frame(drive)!r}); ")
    return layers, doors


def replayed_row(each, floppy=None, script=None):
    """THE CASE (an `aes_deskwin.Case`) of a routine of the group's that traps: its row that switches over the arrival's
    megabyte with GEMDOS replayed — and, `floppy` (drive_check's `(chain, nth)`), the floppy replayed too. `script`:
    a labelled staging's own script in place of the run in place's (said in the case's id)."""
    arrived = w.arrival_of(each)
    layers, doors = _replay_staged(each, floppy, script)
    pokes = case.merge_pokes(w.megabyte(arrived), *layers)
    the_row = w.row(w.label(each), each.name, arrived.arguments, pokes, vdi.ALCYON[each.name].restype is not None, each.budget)
    return the_row._replace(door=aes_switch.DoorUser(True, doors))


# ---- band 6 slice F3 (stage 2): A FLIPPED ROUTINE'S ROW ------------------------------------------------------------------------
# A case at an arrival of a flipped routine of the windows' openers and closers (units J, K), REGISTERED as its row that
# switches over `aes_deskwin`'s row machine (the arrival's megabyte whole but the harness's window,
# `aes_desk.arrival_s_machine`) — where its run traps, OVER THE SAME REPLAY its Tier 1 case runs (the orchestrator's
# ruling (c): the wave's own recorder — fslib's ledger and script, and drive_check's floppy where it runs, AES_BIOS_RETURN
# then named by nature as drive_check's own rows name it, `BIOS_DOOR_PARKED` — not band 5's 11-entry trap), said in the
# row's name; its wait ended by `at_idle`; a door user's door, else the replay's twins its companion's child doors; under
# `budget`, its case's own, where its run is past the default derivation margin (the user's ruling of 2026-10-21, "rows
# may declare budget": held both ways by every derivation of the row).
def registered_row(each, *, replayed, floppy=None, at_idle=None, door_user=False, x_flag_differs=False, budget=None):
    """THE CASE REGISTERED (above): the row."""
    arrived = w.arrival_of(each)
    pokes, label = aes_desk.arrival_s_machine(arrived.boot.ram), w.row_label(each)
    the_row = aes_event.woken_row(label, each.name, arrived.arguments, lambda: pokes, at_idle or {}, None, objects=True,
                                  answered=vdi.ALCYON[each.name].restype is not None, budget=budget)
    doors, parked = the_row.door.doors, ()
    if replayed:
        layers, doors = _replay_staged(each, floppy, None)
        staged = case.merge_pokes(pokes, *layers)
        said, parked = (REPLAYED_WITH_THE_FLOPPY, BIOS_DOOR_PARKED) if floppy else (REPLAYED, ())
        the_row = the_row._replace(label=f"{label}; {said}", machine=lambda: staged)
    door = aes_switch.DoorUser(True, doors) if door_user else None
    return aes_event.register_woken(the_row._replace(door=door, child_doors="" if door_user else doors,
                                                     x_flag_differs=x_flag_differs, also_dropped=parked))
