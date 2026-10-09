"""AN INTERRUPT TAKEN BETWEEN TWO INSTRUCTIONS of a routine the interrupts share state with — the surface no
differential has (`m68k_idioms.h`, "a word COUNTED IN MEMORY").

The fork queue's count, its tail and the click count are counted by the INTERRUPTS too: the VDI's motion glue queues
a move (forkq), its button glue counts a click (b_click), the tick counts the click delay down (b_delay). The ROM
counts each with ONE instruction on memory, so whatever instruction boundary an interrupt lands on, neither count is
lost. C that is the same function with no interrupt — all a Tier 1 or Tier 3 run makes — may be compiled to load /
change a register / store, and an interrupt inside that window is then overwritten by the store: forker's count lost an
interrupt's forkq so (the entry stranded in the ring, every later event served one event late).

WHAT RUNS HERE, on the ROM and on each of our two blobs: the routine from a ROM-made arrival, once per INSTRUCTION
BOUNDARY of its own body, the 68000 itself taking the ROM's own interrupt glue at that boundary — the instruction there
is replaced by a `jsr` to a trampoline for the one step (status register, scratch registers and the return to the
replaced instruction kept, as an exception keeps them), the watch stepping the routine an instruction at a time by the
successors its disassembly names.

THE RULE: the states our routine can be left in are the states the ROM's routine is left in at the boundaries of its
own — none more (a count lost) and none fewer (a window the ROM has, a word it reads again); and a state the ROM is left
in at ONE boundary alone is left by ours along one straight line of instructions (a word the ROM reads again just
before it uses it is not one ours read before a test and used after).

AND WHICH INSTRUCTION COUNTS (`test_a_shared_word_is_changed_by_the_kind_of_instruction_the_rom_changes_it_by`): the
sweep above cannot tell two spellings of a count apart where no interrupt of its cases lands between them, so each
routine is also stepped with NO interrupt, on the ROM and on both blobs, and every change its own instructions make
to a shared word is read off the instruction that made it — ONE instruction counting in memory (`addq.w #1,$c906`),
or a store (`clr.w`, `move.w`): ours make the ROM's changes, of the ROM's kinds, in the ROM's order. A count our
build made in a register and stored is a STORE where the ROM COUNTS: red on the instruction, whatever compiler
chose it and wherever an interrupt could land.

NOT HELD HERE: the interrupt MASK. A bench run is entered at IPL 7 and the glue is laid by the watch, not by the
CPU's priority logic — so a routine that masks (tchange's and adelay's spl7 bracket) is not swept: its bracket is
`test_aes_evwait.py`'s and the door's SR words'. Nor a boundary inside a callee: each callee is a case of its own.
"""
import functools
import re
import struct
import subprocess
from collections import namedtuple

import pytest

from harness import addrs, emu, make_image
from recreate_kit import asm_twin, rom_bench
from recreate_kit.rom_bench import RomBench

import aes
import aes_evinput as evinput
import case
import rom_data
import routines
import transcription
import vdi
from opcodes import JSR_ABSOLUTE_LONG

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES

# ---- the trampoline: the interrupt, taken as a subroutine that leaves the interrupted run what an exception leaves ----
MOVE_SR_PUSH = b"\x40\xe7"                      # move.w  sr,-(sp)
RETURN_TO_THE_REPLACED = b"\x5d\xaf\x00\x02"    # subq.l  #6,2(sp): the `jsr`'s return address, back onto the instruction
SAVE_SCRATCH = b"\x48\xe7\xe0\xe0"              # movem.l d0-d2/a0-a2,-(sp)
MOVE_W_IMMEDIATE_D0, MOVE_W_IMMEDIATE_D1 = b"\x30\x3c", b"\x32\x3c"
RESTORE_SCRATCH = b"\x4c\xdf\x07\x07"           # movem.l (sp)+,d0-d2/a0-a2
RTR = b"\x4e\x77"                               # the condition codes, then the PC
JSR_BYTES = len(JSR_ABSOLUTE_LONG) + LONG_BYTES
assert int.from_bytes(RETURN_TO_THE_REPLACED[:WORD_BYTES], "big") >> 9 & 7 == JSR_BYTES, "subq's count: the jsr's length"
TRAMPOLINE_AT = evinput.ARGUMENT_AT                  # the band's argument record: no case here hands one
RUN_INSNS = 100_000                             # one swept run: forker over two events is some 2,000

Interrupt = namedtuple("Interrupt", "glue d0 d1")
A_MOVE = Interrupt(addrs.AES_ROM_MOTION_GLUE, 100, 50)          # the VDI's motion vector: forkq(mchange, x, y)
THE_LEFT_BUTTON = Interrupt(addrs.AES_ROM_BUTTON_GLUE, 1, 0)    # the VDI's button vector: b_click(buttons)
A_TICK = Interrupt(addrs.AES_ROM_TICK_GLUE, 0, 0)


def trampoline(interrupt):
    code = (MOVE_SR_PUSH + RETURN_TO_THE_REPLACED + SAVE_SCRATCH
            + MOVE_W_IMMEDIATE_D0 + struct.pack(">H", interrupt.d0) + MOVE_W_IMMEDIATE_D1 + struct.pack(">H", interrupt.d1)
            + JSR_ABSOLUTE_LONG + struct.pack(">I", interrupt.glue) + RESTORE_SCRATCH + RTR)
    assert len(code) <= evinput.ARGUMENT_BYTES
    return code


# ---- a routine's body: each instruction and where control can go from it ---------------------------------------------
_BRANCH = re.compile(r"(?:b(?:ra|hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)[swl]?|db\w+)$")
_LEAVES = re.compile(r"(?:rts|rte|rtr|jmp)$")
_TARGET = re.compile(r"(?:0x)?([0-9a-f]+)(?: <[^>]*>)?$")
_LISTED = re.compile(r"^\s*([0-9a-f]+):\t(?:[0-9a-f]{4} )+\s*\t(.*)$", re.MULTILINE)
ROM_BODY_SCANNED = 0x800                        # further than any routine runs: the opcode switch's 1,866 bytes


Shore = namedtuple("Shore", "entry reach begin text")       # a routine on one shore: `text` its instructions by PC


def _successors(listed):
    """`{pc: the PCs of the body control can reach next}` from `[(pc, length, text)]`: the instruction after, and a
    branch's target; none for the one that leaves. A call comes back to the instruction after it."""
    body = {pc for pc, _length, _text in listed}
    reach = {}
    for pc, length, text in listed:
        mnemonic, _, operands = text.partition(" ")
        after = set() if _LEAVES.match(mnemonic) or mnemonic == "bras" or mnemonic == "braw" else {pc + length}
        if _BRANCH.match(mnemonic):
            after.add(int(_TARGET.search(operands.strip())[1], 16))
        reach[pc] = frozenset(after & body)
        assert pc not in reach[pc], f"an instruction at {pc:#x} that branches to itself cannot be stepped"
    return reach


A_CALL = "call"                                 # a Line-F call word, as a body lists it: the ROM's `jsr`


@functools.cache
def rom_body(entry):
    """The ROM routine at `entry`, to its one exit (Alcyon's: a Line-F return, or an `rts`): `[(pc, length, text)]`."""
    image, listed = rom_data.linef_dis.Path(rom_data.ROM_IMAGE).read_bytes(), []
    for pc, length, text in rom_data.linef_dis.sweep(entry, entry + ROM_BODY_SCANNED):
        text = text or rom_data.linef_dis.line_f_text(image, pc, {})
        ends = text.startswith("LF_RET") or text == "rts"
        listed.append((pc, length, "rts" if ends else A_CALL if text.startswith("LF_CALL") else text))
        if ends:
            return listed
    raise AssertionError(f"no exit of the routine at {entry:#x} within {ROM_BODY_SCANNED:#x} bytes")


def blob_body(blob, symbol):
    """`symbol`'s instructions in the build at `blob.elf`, as objdump lists the function: `[(pc, length, text)]`."""
    listing = subprocess.run(["m68k-elf-objdump", "-d", f"--disassemble={symbol}", str(blob.elf)], capture_output=True,
                             text=True, check=True).stdout
    found = [(int(pc, 16), text.strip()) for pc, text in _LISTED.findall(listing)]
    assert found and found[0][0] == blob.entry(symbol), f"objdump lists no {symbol} in {blob.elf}"
    ends = [pc for pc, _text in found[1:]] + [found[-1][0] + WORD_BYTES]
    return [(pc, end - pc, text) for (pc, text), end in zip(found, ends)]


def _shore(entry, listed, begin):
    return Shore(entry, _successors(listed), begin, {pc: text for pc, _length, text in listed})


# ---- the two shores' runs, entered as their rows enter them -----------------------------------------------------------
def _the_rom_s(name, arguments, machine):
    pokes = aes.staged(name, vdi.as_signed(name, arguments), machine)
    entry = getattr(addrs, name)

    def begin(door):
        memory = make_image(pokes)
        return memory, rom_bench.original_entered(memory, entry, door, max_insns=RUN_INSNS)
    return _shore(entry, rom_body(entry), begin)


def _ours(blob, name, arguments, machine):
    symbol, c_arguments = routines.core_symbol(name), (0, *arguments)      # the image's base first: 0 on target
    entry = blob.entry(symbol)

    def begin(door):
        memory = make_image(machine)
        memory[blob.base:blob.base + len(blob.blob)] = blob.blob
        sp = emu.STACK_TOP - rom_bench._stack_args_overflow(c_arguments)
        asm_twin.stage_stack_args(memory, sp, c_arguments[1:])
        emu.install_chip_seeds()
        seed = [asm_twin.CALLEE_SAVED_SEEDS.get(register, 0) for register in emu.REPORTED_REGS]
        return memory, emu.run_bench(memory, entry, c_arguments[0], sp, emu.SENTINEL, max_insns=RUN_INSNS, door=door,
                                     seed_regs=seed)
    return _shore(entry, blob_body(blob, symbol), begin)


Run = namedtuple("Run", "memory boundaries d0")


def interrupted_at(shore, boundary, interrupt, at_each_boundary=None):
    """The run of `shore` (`_the_rom_s` / `_ours`) with `interrupt` taken at its `boundary`-th instruction boundary
    (None: never): its memory at its return, the boundaries it stepped (each the PC of the instruction after it),
    its D0. `at_each_boundary(pc, memory)`: called at every boundary of the routine's own, before the instruction at
    `pc` runs."""
    entry, reach, begin = shore.entry, shore.reach, shore.begin
    memory, result = begin({entry})
    stepped, replaced, code = [], None, trampoline(interrupt)
    try:
        while result["status"] == emu.BENCH_DOOR:
            pc = emu.bench_door_pc()
            if pc != TRAMPOLINE_AT and at_each_boundary:
                at_each_boundary(pc, memory)
            if pc == TRAMPOLINE_AT:                 # the `jsr` has been made: the instruction is put back before the
                at, held = replaced                 # glue runs — it may call this very routine (forkq's does)
                memory[at:at + JSR_BYTES] = held
                emu.bench_door_arm(None)
            elif len(stepped) == boundary:
                replaced = (pc, bytes(memory[pc:pc + JSR_BYTES]))
                memory[pc:pc + JSR_BYTES] = JSR_ABSOLUTE_LONG + struct.pack(">I", TRAMPOLINE_AT)
                memory[TRAMPOLINE_AT:TRAMPOLINE_AT + len(code)] = code
                emu.bench_door_arm({TRAMPOLINE_AT})
                stepped.append(pc)
            else:
                stepped.append(pc)
                emu.bench_door_arm(reach[pc] or None)
            result = emu.bench_resume(entry, max_insns=RUN_INSNS)
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"the interrupted run of {entry:#x}")
    return Run(memory, tuple(stepped), result["d0"])


# ---- what an interrupt and the routine share: the state the rule is about ---------------------------------------------
SHARED_WORDS = (aes.AES_FORK_HEAD, aes.AES_FORK_TAIL, aes.AES_FORK_COUNT, aes.AES_GL_CLICK_TICKS, evinput.EVI["AES_GL_BCLICK"],
                evinput.EVI["AES_GL_BTRUE"], evinput.EVI["AES_GL_BDESIRED"])
FORK_FUNCTION_ENTRIES = {"aes_kchange_fork": addrs.AES_ROM_KCHANGE, "aes_bchange_fork": addrs.AES_ROM_BCHANGE,
                         "aes_mchange_fork": addrs.AES_ROM_MCHANGE, "aes_tchange_fork": addrs.AES_ROM_TCHANGE}


def state(memory, codes):
    """The shared words, the posted byte and the whole ring — a queued code read as the ROM's address of the fork
    function (`codes`: our build queues the function's own entry, `aes/evfork.h`)."""
    ring = [case.long_in(memory, at) for at in range(aes.AES_FORK_QUEUE, aes.AES_FORK_QUEUE
                                                      + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES, LONG_BYTES)]
    return (tuple(case.word_in(memory, at) for at in SHARED_WORDS) + (memory[aes.AES_FORK_POSTED],)
            + tuple(codes.get(value, value) for value in ring[aes.FORK_CODE // LONG_BYTES::2])
            + tuple(ring[aes.FORK_DATA // LONG_BYTES::2]))


def states(shore, interrupt, codes=None):
    """`{state: the boundaries that leave it}` of `shore` with `interrupt` taken at each boundary of its own body."""
    left, stepped = {}, interrupted_at(shore, None, interrupt).boundaries
    _vet_every_instruction_was_stepped(shore, stepped)
    for boundary in range(len(stepped)):
        left.setdefault(state(interrupted_at(shore, boundary, interrupt).memory, codes or {}), []).append(boundary)
    return left


def _executed(shore):
    """The instructions of `shore`'s own body its unwatched run executes, as the oracle's profile tallies them."""
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        shore.begin(None)
    finally:
        emu.bench_abort()
        emu.prof_enable(False)
    return {pc for pc in shore.reach if emu.prof_cycles(pc, pc + WORD_BYTES)}


def _vet_every_instruction_was_stepped(shore, stepped):
    lost = _executed(shore) ^ set(stepped)
    assert not lost, (
        f"the watch of {shore.entry:#x} did not step the instructions the run executed (at {sorted(map(hex, lost))}): a "
        f"successor its listing does not name — the boundaries after it would go unswept, and nothing would say so")


# ---- the cases ----------------------------------------------------------------------------------------------------------
# `states`: how many states the ROM's own routine is left in — what makes the case one (1: the ROM's routine is left the
# same wherever the interrupt lands, which is the whole claim of an instruction on memory).
Case = namedtuple("Case", "routine arrival interrupt states")
PRESS_RELEASE_MOVE = "a press and its release, then a move ends the count"
CASES = {
    # forker has counted the one entry out and not yet tested the count again: the move queued there is served by
    # this run, at every boundary but the last few (after the loop's last test: left queued, the count 1).
    "forker, a move": Case(evinput.FORKER, lambda: evinput.at("the shift key alone", evinput.FORKER, 1), A_MOVE, 2),
    # chkkbd's forkq of a key, a move queued inside it: THE ROM'S OWN RACE (the tail read at $fe4b2c, counted at
    # $fe4b44 — both entries land in one slot, the tail two on and a stale slot counted). Ours is that race, no other.
    "forkq, a move": Case(evinput.FORKQ, lambda: evinput.at("a key wakes the desk", evinput.FORKQ), A_MOVE, 3),
    # mchange's b_delay of the whole count, the button pressed AGAIN inside it: b_click's `addq.w #3` on the count.
    # The ROM reads the buttons AGAIN ($fe4ff6) for the second entry it queues, after comparing them ($fe4fea): a
    # press between the two queues that press (`word_read_again`).
    "b_delay, the button again": Case(evinput.B_DELAY, lambda: evinput.at(PRESS_RELEASE_MOVE, evinput.B_DELAY), THE_LEFT_BUTTON, 5),
    "b_delay, a tick": Case(evinput.B_DELAY, lambda: evinput.at(PRESS_RELEASE_MOVE, evinput.B_DELAY), A_TICK, 2),
    # ...and mchange itself: it tests the count, compares the mouse with the slop, and reads the count AGAIN for
    # b_delay ($fe5376, $fe53be) — the button again between the two is counted off with the rest.
    "mchange, the button again": Case(evinput.MCHANGE, lambda: evinput.at(PRESS_RELEASE_MOVE, evinput.MCHANGE), THE_LEFT_BUTTON, 3),
    # b_click runs in the button's interrupt alone, and a tick cannot nest in it on an ST (both are the MFP's, level
    # 6): the case holds the idiom at b_click's two counts, as a machine's it would be no case.
    "b_click, a tick": Case(evinput.B_CLICK, lambda: evinput.at("a double click wakes the desk", evinput.B_CLICK, 2), A_TICK, 1),
}
BLOBS = {"the bench blob": None, "the shipped blob": transcription.SHIPPED_ELF.parent}


@functools.cache
def blob_in(directory):
    return RomBench(directory)


@functools.cache
def the_rom_s_states(name):
    routine, arrival, interrupt, _rom_only = CASES[name]
    arrival = arrival()
    return states(_the_rom_s(routine, arrival.arguments, arrival.machine), interrupt)


@pytest.mark.parametrize("name", CASES)
def test_the_rom_s_routine_is_left_in_the_states_the_case_declares(name):
    """...and stepping alone, the interrupt never taken, changes nothing — while TAKEN it leaves, at some boundary
    at least, a state the run without it does not: a case whose interrupt changed no word of the state would be
    swept green by a routine that lost it (ONE declared state, as b_click's under a tick, is the ROM's claim that
    the boundary does not matter — it must still not be the untaken run's)."""
    routine, arrival, interrupt, declared = CASES[name]
    arrival = arrival()
    shore = _the_rom_s(routine, arrival.arguments, arrival.machine)
    assert len(the_rom_s_states(name)) == declared
    plain = interrupted_at(shore, None, interrupt)
    untaken = interrupted_at(shore, len(plain.boundaries), interrupt)            # a boundary the run never reaches
    assert state(plain.memory, {}) == state(untaken.memory, {})
    assert the_interrupt_shows(the_rom_s_states(name), state(plain.memory, {})), (
        "the interrupt, taken, changes nothing the state holds")


def the_interrupt_shows(left, untaken):
    """Does an interrupt taken at SOME boundary leave a state (`left`: `states`' answer) other than `untaken`, the
    state of the run that never took it?"""
    return set(left) != {untaken}


def test_a_case_whose_interrupt_changes_nothing_of_the_state_would_be_no_case():
    """The premise the cases are held to, on its own: one state at every boundary is a case (the ROM's claim that
    the boundary does not matter) only if it is NOT the untaken run's."""
    assert the_interrupt_shows({"taken": [0, 1, 2]}, "untaken")
    assert the_interrupt_shows({"untaken": [0], "taken": [1, 2]}, "untaken")
    assert not the_interrupt_shows({"untaken": [0, 1, 2]}, "untaken")


@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
@pytest.mark.parametrize("name", CASES)
def test_an_interrupt_between_any_two_instructions_leaves_a_state_the_rom_s_routine_leaves(name, directory):
    routine, arrival, interrupt, _declared = CASES[name]
    arrival, blob = arrival(), blob_in(directory)
    codes = {blob.entry(symbol): rom_address for symbol, rom_address in FORK_FUNCTION_ENTRIES.items()}
    shore = _ours(blob, routine, arrival.arguments, arrival.machine)
    ours = states(shore, interrupt, codes)
    the_rom_s = the_rom_s_states(name)
    lost = {left: boundaries for left, boundaries in ours.items() if left not in the_rom_s}
    assert not lost, (
        f"{name}: an interrupt at boundaries {sorted(sum(lost.values(), []))} of our {evinput.short(routine)} leaves a state "
        f"the ROM's routine is left in at none of its own — a count changed in a register and stored over the interrupt's")
    never = the_rom_s.keys() - ours.keys()
    assert not never, (
        f"{name}: the ROM's routine is left in {len(never)} states ours never is (at its boundaries "
        f"{sorted(sum((the_rom_s[left] for left in never), []))}) — a word the ROM reads again, read once")
    widened = [left for left, boundaries in the_rom_s.items()
               if len(boundaries) == 1 and not _one_straight_line(shore, ours[left], interrupt)]
    assert not widened, (
        f"{name}: a state the ROM's routine is left in at ONE boundary alone — a window of one instruction — is left by "
        f"ours at {[ours[left] for left in widened]}, across a branch: a word read before the test, used after it")


def _one_straight_line(shore, boundaries, interrupt):
    """Whether `boundaries` of `shore`'s run are consecutive with no conditional branch between two of them: the
    instructions of one window — a value read, moved, pushed — and nothing decided inside it."""
    stepped = interrupted_at(shore, None, interrupt).boundaries
    return (boundaries == list(range(boundaries[0], boundaries[-1] + 1))
            and all(len(shore.reach[stepped[boundary]]) == 1 for boundary in boundaries[:-1]))


# ---- which instruction changes a shared word: one that COUNTS IN MEMORY, or a store -----------------------------------
COUNTED, STORED = "counted in memory by one instruction", "stored"
_COUNTS_A_WORD = re.compile(r"(?:addq|subq|add|sub)w$")
_A_REGISTER = re.compile(r"%(?:[ad][0-7]|sp|fp)$")
_CALLS = re.compile(rf"(?:{A_CALL}|jsr|bsr[swl]?)$")


def kind_of_change(text):
    """How the instruction `text` changes the memory word it changes: COUNTED — an add or a subtract whose destination
    is memory — or STORED; None for a call (the change is its callee's, a case of its own)."""
    mnemonic, _, operands = text.partition(" ")
    if _CALLS.match(mnemonic):
        return None
    counted = _COUNTS_A_WORD.match(mnemonic) and not _A_REGISTER.search(operands.rpartition(",")[2].strip())
    return COUNTED if counted else STORED


def changes_of_the_shared_words(shore):
    """`[(shared word, kind of change)]`, in order: every change `shore`'s own instructions make to a SHARED_WORDS word
    in its plain run — each read off the one instruction between the two boundaries the word differs at."""
    seen = []
    plain = interrupted_at(shore, None, A_TICK, lambda pc, memory: seen.append(
        (pc, [case.word_in(memory, at) for at in SHARED_WORDS])))
    _vet_every_instruction_was_stepped(shore, plain.boundaries)
    after_each = [words for _pc, words in seen[1:]] + [[case.word_in(plain.memory, at) for at in SHARED_WORDS]]
    made = []
    for (pc, before), after in zip(seen, after_each):
        kind = kind_of_change(shore.text[pc])
        made += [(at, kind) for at, was, now in zip(SHARED_WORDS, before, after) if was != now and kind]
    return made


@pytest.mark.parametrize("text, kind", (
    ("addqw #1,0xc906", COUNTED), ("subqw #1,%a5@", COUNTED), ("subw %d1,%a0@(0,%d0:l)", COUNTED),
    ("addqw #3,%a1@", COUNTED), ("addqw #1,%d0", STORED), ("subqw #1,%a2", STORED), ("movew %d0,0xc906", STORED),
    ("clrw 0xc6b0", STORED), ("addql #1,0x948e", STORED), ("jsr 0xfe4b1a", None), ("bsrw 30510 <aes_forkq>", None),
    (A_CALL, None)))
def test_an_instruction_counts_in_memory_or_stores(text, kind):
    """The reading of one instruction, on both listings' spellings: a WORD added to or subtracted from in MEMORY
    counts; into a register it counts nothing an interrupt shares (what stores the register after does)."""
    assert kind_of_change(text) == kind


# The words each routine's OWN instructions count in memory, by the ROM's own run of its case — what
# `m68k_idioms.h`'s `add_word_in_memory` / `sub_word_in_memory` are for, site by site (`src/aes/evfork.c`,
# `src/aes/evinput.c`).
COUNTED_BY = {
    evinput.FORKER: {aes.AES_FORK_COUNT, aes.AES_FORK_HEAD},
    evinput.FORKQ: {aes.AES_FORK_TAIL, aes.AES_FORK_COUNT},
    evinput.B_DELAY: {aes.AES_GL_CLICK_TICKS},
    evinput.B_CLICK: {evinput.EVI["AES_GL_BCLICK"], aes.AES_GL_CLICK_TICKS},
    evinput.MCHANGE: set(),                  # its count is b_delay's to count off; it reads it twice (`word_read_again`)
}


def _arrival_of(routine):
    """A case's arrival for `routine` — the first of CASES that names it."""
    return next(case_.arrival for case_ in CASES.values() if case_.routine == routine)()


@pytest.mark.parametrize("routine", COUNTED_BY, ids=evinput.short)
def test_the_rom_counts_in_memory_the_words_the_idiom_is_for(routine):
    """The premise, off the ROM: each word COUNTED_BY names for the routine is counted by one instruction of its
    own in this case's run — and no other shared word is."""
    arrival = _arrival_of(routine)
    made = changes_of_the_shared_words(_the_rom_s(routine, arrival.arguments, arrival.machine))
    assert {at for at, kind in made if kind == COUNTED} == COUNTED_BY[routine], made


@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
@pytest.mark.parametrize("routine", COUNTED_BY, ids=evinput.short)
def test_a_shared_word_is_changed_by_the_kind_of_instruction_the_rom_changes_it_by(routine, directory):
    """THE STATIC PIN of `add_word_in_memory` / `sub_word_in_memory`, on both blobs: the changes our routine's own
    instructions make to the words an interrupt shares are the ROM's — the same words, in the same order, each by an
    instruction of the same kind. C that counts one in a register and stores it changes it by a STORE where the ROM
    COUNTS IN MEMORY: red here whatever the interrupted sweep's cases can tell apart (forkq's count and b_click's
    click count were memory-direct by the compiler's own choice before the idiom — nothing held them)."""
    arrival, blob = _arrival_of(routine), blob_in(directory)
    ours = changes_of_the_shared_words(_ours(blob, routine, arrival.arguments, arrival.machine))
    the_rom_s = changes_of_the_shared_words(_the_rom_s(routine, arrival.arguments, arrival.machine))
    assert ours == the_rom_s, (
        f"our {evinput.short(routine)} changes the words an interrupt shares as {ours}, the ROM's as {the_rom_s}")


def test_the_trampoline_returns_to_the_instruction_it_replaced_with_its_registers_and_flags():
    """THE MECHANISM, on a routine none of whose words is the interrupts': downorup answers the same D0 with a move's
    interrupt taken at each of its boundaries (the condition codes its branches test, its registers and its frame
    all kept) — and the move is queued each time."""
    arrival = evinput.at("a press wakes the desk", evinput.DOWNORUP)
    shore = _the_rom_s(evinput.DOWNORUP, arrival.arguments, arrival.machine)
    plain = interrupted_at(shore, None, A_MOVE)
    assert len(plain.boundaries) > 10
    for boundary in range(len(plain.boundaries)):
        taken = interrupted_at(shore, boundary, A_MOVE)
        assert taken.d0 & aes.WORD_MASK == plain.d0 & aes.WORD_MASK, f"the answer with the interrupt at boundary {boundary}"
        assert (len(evinput.fork_queue(taken.memory)), evinput.fork_queue(taken.memory)[-1]) == (
            len(evinput.fork_queue(plain.memory)) + 1, (addrs.AES_ROM_MCHANGE, aes.words_long(A_MOVE.d0, A_MOVE.d1))), boundary
