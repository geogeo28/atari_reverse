"""THE DESK'S DISK UTILITIES — unit N (`src/desk/deskdisk.c`; band 6 wave 4, group G2, ruling R-W4-4): Format, the
disk copy and their helpers — their declared Alcyon frames and the unit's wave-4 list."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG

# ---- band 6 wave 4, group G2 (unit N) ----
P = "AES_ROM_DESK_"
UTIL_OPEN, UTIL_SHOW, UTIL_REDRAW, FAT_SWAP = P + "UTIL_OPEN", P + "UTIL_SHOW", P + "UTIL_REDRAW", P + "FAT_SWAP"
UTIL_BARS, UTIL_ERROR, FAT_MARK, COPY_TRACKS = P + "UTIL_BARS", P + "UTIL_ERROR", P + "FAT_MARK", P + "COPY_TRACKS"
FORMAT, COPY_DISK = P + "FORMAT", P + "COPY_DISK"
# `{routine: (the core's answer, its frame in push order)}` — None where the core answers nothing (its D0 a callee's
# leftover, read by no caller: the D0 table's)
SIGNATURES_WAVE_4 = {
    UTIL_OPEN: (None, ()),
    UTIL_SHOW: (None, (LONG, WORD, WORD, WORD)),
    UTIL_REDRAW: (None, ()),
    FAT_SWAP: (aes.WORD_ANSWER, (LONG,)),
    UTIL_BARS: (None, (LONG, LONG, WORD)),
    UTIL_ERROR: (None, (WORD, WORD)),
    FAT_MARK: (None, (WORD, WORD, LONG, LONG)),
    COPY_TRACKS: (aes.WORD_ANSWER, (WORD, LONG, LONG, WORD, WORD, WORD, WORD, WORD)),
    FORMAT: (aes.WORD_ANSWER, (LONG, LONG)),
    COPY_DISK: (aes.WORD_ANSWER, (LONG, LONG)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_4.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_N_WAVE_4 = tuple(SIGNATURES_WAVE_4)

# FORMAT AND THE COPY REACH GEMDOS (their Mallocs, Mfrees, Format's Dfree): on both shores of a case, unit C's recorder
# replaying the ROM's own run in place (`aes_deskdir`'s ENGINE, `in_place`, `replayed` — wave 2's one mechanism; Dfree
# and its DISKINFO, captured by `aes_deskdir.DFREE_FILLED`, are that recorder's since the fix pass), its twins bound in
# the row's child.
import aes_deskdir as _dd
import aes_event as _event

for _name in (FORMAT, COPY_DISK):
    _event.declare_child_doors(_name, _dd.ENGINE_CHILD_DOORS)
in_place = _dd.in_place

# ---- THE FLOPPY REPLAYED: the ROM's own run in place, call by call -----------------------------------------------------
# Format, the copy and copy_tracks reach the floppy through the AES's two doors — trp14 (`$fee488`: Flopfmt, Floprd,
# Flopwr, Protobt, the stub 11) and trp13 (`$fee478`: Getbpb, Rwabs) — whose traps reach the driver: on the ROM's
# machine slice H's formatter and drive B: (`aes_boot.Floppy`), on a row's shores NO DRIVER AT ALL. So on both shores
# of a case each call is answered by A REPLAY OF THE ROM'S OWN RUN IN PLACE (`floppy_in_place`) — a LABELLED STAGING,
# said in its id (FLOPPY_REPLAYED):
#   * on the ROM's shore three stubs in this group's window of the AES's staged area — at the `trap #14` vector, and at
#     the disk vectors `hdv_bpb` and `hdv_rw` the ROM's BIOS calls (unit J's way, `aes_desksupp`) — each answering D0
#     the next of the run's answers, kept as RUNS (a count and an answer: the copy's 240 XBIOS calls answer 0 alike),
#     its pointer stored back;
#   * on ours the C's XBIOS door `desk_disk_xbios_door` (`desk/deskdisk.h`) and the disk vectors' hook (trp13's twin
#     reaches it), bound in the row's child to the same answers and the same stores — AND EACH CALL HELD TO THE RUN'S:
#     its frame's words, and for Flopfmt the nine words of the skew table its second longword points at (the address
#     itself is a frame of the ROM's stack there, a host slot here); any other call, or one more, ENDS THE CHILD BY
#     NAME. `unheld`: a case's frame words no C has (Format's Flopwr filler, its -4(a6) never written: `deskdisk.c`'s
#     header) — named;
#   * the driver's RECORD each Getbpb of the run left (the disk it logged in: the formatted one, drive B:'s) LAID at the
#     arrival, on both shores — its BPB is what the C reads of the answer.
#   * AN Rwabs WRITE's BYTES (the fix pass, reviewer B's F1): the count x 512 bytes at its buffer, read off the run in
#     place at its trap, and the C's at its call held to them — refused by name where they differ (Format's root, its
#     label among it, and both FATs: one buffer reused, so the end-state compare alone would not see the root's).
#     UNHELD, named: what a Flopwr hands the disk (the boot sector, Protobt's effect — run by neither shore).
# WHAT THE DRIVER DOES TO MEMORY IS DONE ON NEITHER SHORE: no C of the unit reads a track's bytes back.
import ctypes
import os
import struct
import sys
from collections import namedtuple

import aes_boot
import aes_deskarrive as _da
import aes_deskbind as _db
import case
import gemdos_fs as _fs
import isr
import layouts
from address_hook import bind_pointer
from harness import addrs

FLOPPY_REPLAYED = "THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer"
FLOPPY = layouts.parse_constants((aes.INCLUDE / "desk" / "desksupp.h", aes.INCLUDE / "desk" / "deskdisk.h"),
                                 known={**vdi.CONSTANTS, **aes.CONSTANTS})
FLOPRD_FN, FLOPWR_FN = FLOPPY["XBIOS_FLOPRD_FN"], FLOPPY["XBIOS_FLOPWR_FN"]
FLOPFMT_FN, STUB_11_FN = FLOPPY["XBIOS_FLOPFMT_FN"], FLOPPY["XBIOS_STUB_11_FN"]
GETBPB_FN, RWABS_FN = addrs.BIOS_GETBPB_FN, addrs.BIOS_RWABS_FN
XBIOS_WORDS = {FLOPRD_FN: FLOPPY["XBIOS_FLOPRW_WORDS"], FLOPWR_FN: FLOPPY["XBIOS_FLOPRW_WORDS"],
               FLOPFMT_FN: FLOPPY["XBIOS_FLOPFMT_WORDS"], addrs.XBIOS_PROTOBT_FN: FLOPPY["XBIOS_PROTOBT_WORDS"],
               STUB_11_FN: FLOPPY["XBIOS_STUB_11_WORDS"]}
GETBPB_WORDS, RWABS_WORDS = 2, 7        # the function, the drive; the function, rwflag, buffer.l, count, record, drive
BIOS_WORDS = {GETBPB_FN: GETBPB_WORDS, RWABS_FN: RWABS_WORDS}
RWABS_FLAG_WORD, RWABS_BUFFER_WORD, RWABS_COUNT_WORD = 1, 2, 4      # ...the rwflag, the buffer's high word, the count
RWABS_WRITES = 1                        # rwflag's bit 0: a write
SECTOR_BYTES = 1 << FLOPPY["FLOPPY_SECTOR_SHIFT"]
SKEW_AT_WORD, SKEW_WORDS = 3, FLOPPY["FLOPPY_SECTORS"]   # Flopfmt's second longword (words 3, 4): the skew table's address
SKEW_ADDRESS = ((FLOPFMT_FN, SKEW_AT_WORD), (FLOPFMT_FN, SKEW_AT_WORD + 1))   # ...held by the table it points at, not itself
FLOPFMT_TRACK_WORD = SKEW_AT_WORD + 4   # ...then the device, the sectors, THE TRACK, THE SIDE
FLOPFMT_SIDE_WORD = FLOPFMT_TRACK_WORD + 1
RECORD_BYTES = aes_boot.FLOPPY_BPB_RECORD_BYTES
Door = namedtuple("Door", "trap back words")
TRAP_IN_A_DOOR = 6                      # a door's `trap` past its return's park (`$fee488` / `$fee478`: move.l (sp)+,<abs>)
XBIOS = Door(addrs.AES_ROM_TRP14 + TRAP_IN_A_DOOR, addrs.AES_ROM_TRP14 + TRAP_IN_A_DOOR + aes.WORD_BYTES, XBIOS_WORDS)
BIOS = Door(addrs.AES_ROM_TRP13 + TRAP_IN_A_DOOR, addrs.AES_ROM_TRP13 + TRAP_IN_A_DOOR + aes.WORD_BYTES, BIOS_WORDS)
DoorCall = namedtuple("DoorCall", "words pointed answer")
DoorCall.__doc__ = """One call through a door of a run: its frame's `words` (the function first); for Flopfmt the skew
table's words its second longword points at, for Getbpb the record its answer points at as the call left it, for an
Rwabs write the bytes it hands the disk (else ()); the long `answer`."""
BUS = aes.OS_BUS_ADDR_MASK
A6_LINKS = 64                           # frames walked up from a trap to find the routine's own (any desk nest is far fewer)


def _words(ram, at, count):
    return tuple(case.word_in(ram, at + nth * aes.WORD_BYTES) for nth in range(count))


def rwabs_written(ram, words):
    """What an Rwabs of `words` hands the disk: its count x 512 bytes at its buffer — b"" for a read."""
    if words[0] != RWABS_FN or not words[RWABS_FLAG_WORD] & RWABS_WRITES:
        return b""
    buffer = (words[RWABS_BUFFER_WORD] << 16 | words[RWABS_BUFFER_WORD + 1]) & BUS
    return bytes(ram[buffer:buffer + words[RWABS_COUNT_WORD] * SECTOR_BYTES])


def _inside(ram, a6, own):
    """Is the routine still running where the CPU stands (`ram`, its A6): its own frame `own` (the `link` at its entry,
    just under the return address) on the A6 chain?"""
    frame = a6 & BUS
    for _link in range(A6_LINKS):
        if frame == own:
            return True
        if not 0 < frame < aes_boot.RAM_BYTES:
            return False
        frame = case.long_in(ram, frame) & BUS
    return False


WATCHED, TRAPPED, ANSWERED = "unit N's floppy door", "trapped", "answered"


def _watches(own):
    """`{PC: (name, reader)}`: each door's trap and the instruction after it, read while the routine whose frame is
    `own` runs (else None) — the frame's words (and Flopfmt's skew table, an Rwabs write's bytes) at the trap, D0 (and
    the record a Getbpb answers) after it. (`own`, not the arrival: the readers are an argument of `aes_boot.continued`,
    read by value into its derivation's key.)"""
    def at_the_trap(door):
        def read(memory, sp):
            if not _inside(memory, aes_boot.registers_at_the_stop(("a6",))["a6"], own):
                return None
            function = case.word_in(memory, sp)
            if function not in door.words:
                raise aes_boot.Refused(f"the run calls function {function} through the door at {door.trap:#x}: no frame "
                                       f"of it is declared here")
            words = _words(memory, sp, door.words[function])
            if door is XBIOS and function == FLOPFMT_FN:
                return words, _words(memory, (words[SKEW_AT_WORD] << 16 | words[SKEW_AT_WORD + 1]) & BUS, SKEW_WORDS)
            return words, rwabs_written(memory, words) if door is BIOS else ()
        return read

    def after_it(door):
        def read(memory, _sp):
            registers = aes_boot.registers_at_the_stop(("a6", "d0"))
            if not _inside(memory, registers["a6"], own):
                return None
            answer = registers["d0"] & aes.LONG_MASK
            return answer, bytes(memory[answer & BUS:(answer & BUS) + RECORD_BYTES]) if door is BIOS else b""
        return read
    return {pc: (f"{WATCHED} {door.trap:#x} {which}", reader(door)) for door in (XBIOS, BIOS)
            for pc, which, reader in ((door.trap, TRAPPED, at_the_trap), (door.back, ANSWERED, after_it))}


def _calls_of(observed, door):
    """`door`'s `DoorCall`s off a run's `observed`, in order."""
    calls, trapped = [], None
    for name, read in observed:
        if read is None or not name.startswith(f"{WATCHED} {door.trap:#x}"):
            continue
        if name.endswith(TRAPPED):
            trapped = read
            continue
        (words, pointed), (answer, record) = trapped, read
        calls.append(DoorCall(words, record if door is BIOS and words[0] == GETBPB_FN and answer else pointed, answer))
    return tuple(calls)


Replayed = namedtuple("Replayed", "xbios bios")


def floppy_in_place(arrived, wakes=()):
    """THE ROM'S OWN RUN IN PLACE of the routine from `arrived` to its return, over the machine's device model, ONE RUN
    PER IDLE (at each the next of `wakes` taken in), each door's calls read while the routine runs (`aes_boot.continued`
    watched at the doors, `_watches`: what each read is in the `Boot`'s `observed`): a `Replayed`. (One run per idle,
    never a hop between calls: a hop mid-Format would remake the device model over a disk whose boot sector the
    formatter has not yet written, which the model refuses by name.)"""
    boot, stands_at, received, wakes, observed = arrived.boot, _da.entry_of(arrived.name), (), list(wakes), []
    watches = _watches(_db.stack_pointer(arrived.boot) - aes.LONG_BYTES)
    while True:
        try:
            ran = aes_boot.continued(boot, received, arrived.budget, arrived.returns_to, stands_at, watches)
        except aes_boot.Refused:
            ran = aes_boot.continued(boot, received, arrived.budget, None, stands_at, watches)
            assert wakes, f"{_da.label_of(arrived)}: the run idles with no wake left to take in"
            observed += ran.observed
            boot, stands_at, received = ran, None, wakes.pop(0)
            continue
        observed += ran.observed
        break
    assert not wakes, f"{_da.label_of(arrived)}: wakes left at the run's return"
    return Replayed(_calls_of(observed, XBIOS), _calls_of(observed, BIOS))


# ---- the ROM's shore: three stubs, each its runs of answers -----------------------------------------------------------
WINDOW_AT, WINDOW_BYTES = 0x7b640, 0x1C0
aes.SPAN.claim(WINDOW_AT, WINDOW_BYTES, "test/aes_deskdisk.py: group G2's floppy stubs (XBIOS, hdv_bpb, hdv_rw) and their runs")
RUN_BYTES = 2 * aes.LONG_BYTES          # a count of calls, then the answer they get
SPARE_ANSWER = -1 & aes.LONG_MASK       # a call past the run's: ERROR — the C that calls on is answered, and differs
SPARE_CALLS = 0xFFFF
MOVE_L_A0_PREDEC_SP, MOVEA_L_ABSOLUTE_A0, MOVE_L_4_A0_D0 = 0x2F08, 0x2079, 0x2028
SUBQ_L_1_A0, BNE_S, ADDQ_L_8_ABSOLUTE, MOVEA_L_SP_POSTINC_A0 = 0x5390, 0x6600, 0x50B9, 0x205F
RTE, RTS = 0x4E73, 0x4E75
ADDQ_BYTES = 6
STUB_ROOM = 0x20


class Stub(namedtuple("Stub", "vector at room returns")):
    """A stub at `at` (`room` bytes: its code, the runs' pointer, the runs) entered through the longword `vector`, left by
    `returns` (an exception's `rte`, a subroutine's `rts`): D0 the current run's answer, its count less one — at 0 the
    pointer on to the next run. Every register but D0 as found; the host twin (`answered`) is the same effect."""

    @property
    def pointer_at(self):
        return self.at + STUB_ROOM

    @property
    def runs(self):
        return (self.room - STUB_ROOM - aes.LONG_BYTES) // RUN_BYTES

    def code(self):
        pointer = struct.pack(">I", self.pointer_at)
        code = (struct.pack(">HH", MOVE_L_A0_PREDEC_SP, MOVEA_L_ABSOLUTE_A0) + pointer
                + struct.pack(">HHHH", MOVE_L_4_A0_D0, aes.LONG_BYTES, SUBQ_L_1_A0, BNE_S | ADDQ_BYTES)
                + struct.pack(">H", ADDQ_L_8_ABSOLUTE) + pointer + struct.pack(">HH", MOVEA_L_SP_POSTINC_A0, self.returns))
        assert len(code) <= STUB_ROOM
        return code

    def staged(self, answers):
        """The vector at the stub, the runs of `answers` (the spare run last), the pointer at the first."""
        runs = []
        for answer in answers:
            if runs and runs[-1][1] == answer:
                runs[-1][0] += 1
            else:
                runs.append([1, answer])
        runs.append([SPARE_CALLS, SPARE_ANSWER])
        assert len(runs) <= self.runs, f"{len(runs)} runs of answers: more than the stub at {self.at:#x} holds"
        laid = b"".join(struct.pack(">II", count, answer) for count, answer in runs)
        return {self.vector: struct.pack(">I", self.at), self.at: self.code(),
                self.pointer_at: struct.pack(">I", self.pointer_at + aes.LONG_BYTES) + laid}

    def answered(self, buf):
        """The stub's effect on the candidate's image: the run's answer, its count less one, the pointer moved on."""
        run = case.long_in(buf, self.pointer_at)
        count, answer = case.long_in(buf, run) - 1 & aes.LONG_MASK, case.long_in(buf, run + aes.LONG_BYTES)
        isr.poke(buf, run, struct.pack(">I", count))
        if not count:
            isr.poke(buf, self.pointer_at, struct.pack(">I", run + RUN_BYTES))
        return aes.signed(answer, bits=32)


XBIOS_STUB = Stub(addrs.VECTOR_TRAP_XBIOS, WINDOW_AT, 0xC0, RTE)
BPB_STUB = Stub(addrs.HDV_BPB, XBIOS_STUB.at + XBIOS_STUB.room, 0x60, RTS)
RW_STUB = Stub(addrs.HDV_RWABS, BPB_STUB.at + BPB_STUB.room, 0x60, RTS)
assert RW_STUB.at + RW_STUB.room <= WINDOW_AT + WINDOW_BYTES


def floppy_staged(replayed):
    """The ROM's shore's floppy, and the records the run's Getbpbs left — laid on both shores."""
    def answers(function):
        return [call.answer for call in replayed.bios if call.words[0] == function]
    records = {call.answer & BUS: call.pointed for call in replayed.bios if call.words[0] == GETBPB_FN and call.pointed}
    return case.merge_pokes(XBIOS_STUB.staged(call.answer for call in replayed.xbios), BPB_STUB.staged(answers(GETBPB_FN)),
                            RW_STUB.staged(answers(RWABS_FN)), records)


# ---- ours: the two hooks, in the row's child ------------------------------------------------------------------------
XBIOS_DOOR = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint16),
                              ctypes.c_uint16)
DISK_VECTOR_HOOK = "recreate_call_disk_vector"
CHILD_REPLAY_REFUSED = _event.CHILD_FLOPPY_REFUSED          # the child's exit status where the C's call is not the run's
_CHILD_TRAMPOLINES = []


def _refused(why):
    print(why, file=sys.stderr, flush=True)
    os._exit(CHILD_REPLAY_REFUSED)


def _held(made, want, unheld):
    """The words of a call that are held: those no `(function, word index)` of `unheld` names, the rest None."""
    return [None if (made[0], nth) in unheld else word for nth, word in enumerate(made)], \
           [None if (want[0], nth) in unheld else word for nth, word in enumerate(want)]


def bind_floppy_in_a_child(lib, xbios, bios, unheld=()):
    """IN THE ROW'S CHILD: the XBIOS door held to `xbios` (`((words, pointed), ...)`, the run's, in order) and the disk
    vectors' hook to `bios` (`((words, written), ...)`: an Rwabs write's bytes, `rwabs_written`), each answered as its
    stub answers — `unheld`: `(function, word index)` of frame words no C has; a write's bytes WRITTEN_UNHELD where a
    class says so. Any other call, one more, or a write of other bytes ENDS the child by name."""
    xbios, bios = list(xbios), list(bios)
    unheld = (*unheld, *SKEW_ADDRESS)

    def door(buf, frame, count):
        words = [frame[nth] for nth in range(count)]
        if not xbios:
            _refused(f"the C makes an XBIOS call more than the ROM's run: {words}")
        want, pointed = xbios.pop(0)
        made, held = _held(words, want, unheld)
        if made != held:
            _refused(f"the C's XBIOS call {words} is not the ROM's run's {list(want)}")
        if words[0] == FLOPFMT_FN:
            skew = (words[SKEW_AT_WORD] << 16 | words[SKEW_AT_WORD + 1]) & BUS
            if _words(buf, skew, SKEW_WORDS) != tuple(pointed):
                _refused(f"the C's Flopfmt skew table {_words(buf, skew, SKEW_WORDS)} is not the ROM's {pointed}")
        return XBIOS_STUB.answered(buf)

    def disk(buf, function, rwflag, buffer, count, record, device):
        words = [function, device] if function == GETBPB_FN else [function, rwflag, buffer >> 16, buffer & aes.WORD_MASK,
                                                                     count, record, device]
        if not bios:
            _refused(f"the C makes a BIOS call more than the ROM's run: {words}")
        want, want_written = bios.pop(0)
        if words != list(want):
            _refused(f"the C's BIOS call {words} is not the ROM's run's {list(want)}")
        written = rwabs_written(buf, words)
        if want_written is not WRITTEN_UNHELD and written != want_written:
            differs = next(nth for nth, (ours, rom) in enumerate(zip(written, want_written)) if ours != rom)
            _refused(f"the C's Rwabs write {words} hands the disk bytes that are not the ROM's run's: the first "
                     f"difference {differs} bytes into its buffer")
        return (BPB_STUB if function == GETBPB_FN else RW_STUB).answered(buf)
    for symbol, kind, effect in (("desk_disk_xbios_door", XBIOS_DOOR, door), (DISK_VECTOR_HOOK, _fs.DISK_CALL, disk)):
        trampoline = kind(effect)
        _CHILD_TRAMPOLINES.append(trampoline)
        bind_pointer(symbol, trampoline, lib)


WRITTEN_UNHELD = None                   # an Rwabs write's bytes a class does not hold at its call (said in its case)


def rwabs_written_by(call):
    """Whether the run's BIOS `call` is an Rwabs write."""
    return call.words[0] == RWABS_FN and bool(call.words[RWABS_FLAG_WORD] & RWABS_WRITES)


def floppy_door_source(replayed, unheld=()):
    """The child's source that binds both hooks over `replayed` (the row's `DoorUser`'s)."""
    xbios = tuple((call.words, call.pointed) for call in replayed.xbios)
    bios = tuple((call.words, call.pointed if call.words[0] == RWABS_FN else b"") for call in replayed.bios)
    return f"import aes_deskdisk; aes_deskdisk.bind_floppy_in_a_child(lib, {xbios!r}, {bios!r}, {tuple(unheld)!r}); "
# ---- end of group G2's wave-4 ----
