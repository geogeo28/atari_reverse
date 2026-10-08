"""THE INTERRUPTS' GLUE as the target build ships it (`src/aes/irq.S`): the AES's button, motion and tick routines —
what it hands the VDI as vectors — with drawrat and the bare `rts` between them, `$fed3be..$fed477`.

WHAT HOLDS IT.
  * ITS BYTES: the region is the ROM's but for SIX words, each a reference to code followed to what our build links
    in its place — three `jsr`s into C (b_click, forkq twice, b_delay: each to the Alcyon entry that takes the glue's
    pushed words into the C call) and the two fork functions it pushes by value (mchange, tchange: our own entries,
    as a queue entry's code is on target). On BOTH blobs.
  * ITS BEHAVIOUR, each glue entered AS THE ROM'S OWN INTERRUPT CODE ENTERS IT — the machine and the register file
    of an arrival of the VDI's mouse interrupt at the button's and the motion's glue, the tick's own entry — the
    ROM's glue and each blob's over that one machine with that one register file (`aes_switch.vet_the_glue`): the
    registers a glue owes its caller and the whole image equal, but the private stack (another build's frames) and a
    queued fork function's code (each shore's own address of the SAME function, held one by one).
  * ITS STACKS: our build's frames FIT the private stacks the ROM's fit in — 92 and 96 bytes — measured on every
    case: a store below a stack's bottom would land on the tick's own counters.
  * drawrat and justretf through Tier 3's transcription relation, as every `.S` row.

UNPRICED, AND WHY: the three glues have no Tier 3 row. A glue takes its arguments in REGISTERS, which the C relation
(`RomBench.measure`) does not hand, and it differs by nature in compared RAM, which the transcription relation does
not drop. What prices its work is priced where it is done: its instructions are the ROM's own, byte for byte, and
the C it calls has its rows (b_click, b_delay, forkq).
"""
import types

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench
from recreate_kit.rom_bench import RomBench

import aes
import aes_event
import aes_evasync
import aes_evinput
import aes_switch as switch
import case
import test_aes_gsx_transcription as frames
import test_aes_rom_data as rom_census
import transcription
from case import merge_pokes
from opcodes import RTS
from transcription import ABSOLUTE, Relocated

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
ENTRIES = transcription.SWITCH_ENTRIES
BUTTON_GLUE, MOTION_GLUE, TICK_GLUE = "AES_ROM_BUTTON_GLUE", "AES_ROM_MOTION_GLUE", "AES_ROM_TICK_GLUE"
DRAWRAT, JUSTRETF = "AES_ROM_DRAWRAT", "AES_ROM_JUSTRETF"
REGION = transcription.pinned_region(addrs.AES_ROM_BUTTON_GLUE, transcription.GLUE_REGION_END, BUTTON_GLUE,
                                     (MOTION_GLUE, DRAWRAT, JUSTRETF, TICK_GLUE))
# WHAT A WORD OF THE REGION THAT NAMES CODE STANDS FOR: the ROM routine it names, and the symbol our build links in
# its place — the Alcyon entry of the C (a `jsr`), or the fork function's own entry (pushed by value, for forkq).
STANDS_FOR = {
    addrs.AES_ROM_B_CLICK: ("aes_b_click_alcyon", "the button glue's `jsr b_click`: the Alcyon entry of our C"),
    addrs.AES_ROM_FORKQ: ("aes_forkq_alcyon", "the motion and the tick glue's `jsr forkq`"),
    addrs.AES_ROM_B_DELAY: ("aes_b_delay_alcyon", "the tick glue's `jsr b_delay`"),
    addrs.AES_ROM_MCHANGE: ("aes_mchange_fork", "the motion glue's `move.l #mchange`: the fork function forkq queues"),
    addrs.AES_ROM_TCHANGE: ("aes_tchange_fork", "the tick glue's `move.l #tchange`: the fork function forkq queues"),
}
WORDS_THAT_NAME_CODE = 6                # b_click, mchange, forkq, tchange, forkq again, b_delay


def _rom_long(at):
    return int.from_bytes(bytes(BASE_IMAGE[at:at + LONG_BYTES]), "big")


# The six, WHERE THE ROM HAS THEM: every operand of the region that holds one of those routines' addresses.
RELOCATED = {at: Relocated(ABSOLUTE, None, STANDS_FOR[_rom_long(at)][1], thunk=STANDS_FOR[_rom_long(at)][0])
             for at in range(REGION.lo, REGION.hi - LONG_BYTES + 1, WORD_BYTES) if _rom_long(at) in STANDS_FOR}
assert len(RELOCATED) == WORDS_THAT_NAME_CODE
# The three Alcyon entries under the glue's `jsr`s, in the source's order: each one's shape and the C it enters.
THUNKS = {"aes_b_click_alcyon": (switch.ONE_WORD_THUNK, "aes_b_click"),
          "aes_b_delay_alcyon": (switch.ONE_WORD_THUNK, "aes_b_delay"),
          "aes_forkq_alcyon": (switch.TWO_LONGS_THUNK, "aes_forkq")}
GLUE_ENTRIES = ("aes_rom_button_glue", "aes_rom_motion_glue", "aes_rom_drawrat", "aes_rom_justretf", "aes_rom_tick_glue")
BLOBS = switch.BLOBS


@pytest.fixture(scope="module", params=BLOBS.values(), ids=BLOBS)
def blob(request):
    return RomBench(request.param)


# ---- the bytes ----------------------------------------------------------------------------------------------------------
def test_the_region_is_the_rom_s_bytes_but_for_the_six_words_that_name_code():
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_the_region_is_the_same_bytes_on_both_blobs(blob):
    """...and on the shipped configuration's blob: every byte the ROM's but the six operands, each the address that
    blob links the named symbol at."""
    start = blob.entry("aes_rom_button_glue")
    ours = bytearray(blob.blob[start - blob.base:start - blob.base + REGION.hi - REGION.lo])
    theirs = bytearray(BASE_IMAGE[REGION.lo:REGION.hi])
    for at, relocation in RELOCATED.items():
        operand = slice(at - REGION.lo, at - REGION.lo + LONG_BYTES)
        assert bytes(ours[operand]) == blob.entry(relocation.thunk).to_bytes(LONG_BYTES, "big"), relocation.why
        ours[operand] = theirs[operand]
    assert ours == theirs


def test_the_table_s_exits_are_the_symbols_the_relocations_name():
    """Each glue's EXITS (`transcription.SWITCH_ENTRIES`) are the symbols its own relocations name — and what the
    ROM's words named there was the ROM's routine each stands for: the C's ROM twin, or the fork function."""
    for entry in GLUE_ENTRIES:
        row = ENTRIES[entry]
        inside = {relocation.thunk for at, relocation in RELOCATED.items() if row.rom <= at < row.rom + row.bytes}
        assert inside == row.exits, f"{entry}: its relocations name {sorted(inside)}, the table {sorted(row.exits)}"
    for rom, (symbol, _why) in STANDS_FOR.items():
        if rom in switch.FORK_ENTRY_SYMBOLS:
            assert switch.FORK_ENTRY_SYMBOLS[rom] == symbol, "a fork function pushed by value: the entry a queue entry holds"


def test_the_source_holds_its_entries_its_thunks_and_nothing_else(blob):
    """WHAT THE BYTE PIN DOES NOT REACH, held: `irq.S`'s symbols — the five routines, the three Alcyon entries — lie
    END TO END in each blob, nothing after the last but the assembler's fill; and each entry is its shape into the C
    its name says: b_click's and b_delay's one word SIGN-EXTENDED into its slot, forkq's code then its data."""
    switch.vet_laid_end_to_end(blob, (*GLUE_ENTRIES, *THUNKS))
    for thunk, (shape, body) in THUNKS.items():
        switch.vet_a_thunk(blob, thunk, shape, body)
    assert set(THUNKS) == {symbol for symbol, _why in STANDS_FOR.values()} - set(switch.FORK_ENTRY_SYMBOLS.values())


def test_the_region_is_the_five_routines_end_to_end():
    at = REGION.lo
    for entry in GLUE_ENTRIES:
        assert ENTRIES[entry].rom == at, f"{entry} begins at {ENTRIES[entry].rom:#x}, the routine before it ends at {at:#x}"
        at += ENTRIES[entry].bytes
    assert at == REGION.hi and bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS


# ---- the three glues, entered as the ROM's own interrupt code enters them ---------------------------------------------------
A_TIMER_MS = 100
TICKS_BEFORE_IT_RUNS_OUT = A_TIMER_MS // aes_evasync.TICK_MS - 1


def _after(machine, *interrupts):
    """`machine` (pokes) with `interrupts` taken over it in place, in order (`aes_event.press`, `ticks(n)`, ...)."""
    image = make_image(machine)
    for interrupt in interrupts:
        interrupt(image)
    return aes_event.as_pokes(image, upto=addrs.ST_RAM_BYTES)


def _waiting_for_a_timer():
    """The desk parked in an evnt_multi for A_TIMER_MS (the ROM's own call, to the dispatcher's loop) and every tick
    but the last taken: the next one runs the delay out."""
    frame, pokes = aes_evasync.ev_multi_frame(aes.EV_MU_TIMER, timer=A_TIMER_MS)
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes))
    return _after(parked, aes_event.ticks(TICKS_BEFORE_IT_RUNS_OUT))


def _a_press_counting():
    """The snapshot with the left button's packet taken and no tick yet: the desk waits for a double click, so the
    press opened a click count."""
    return _after({}, lambda image: aes_event.taken_in_place(image, aes_event.packets(aes_event.LEFT_DOWN_PACKET)))


def _arriving(packet, machine):
    return lambda: switch.glue_arrival(aes_event.mouse_packet(*packet), machine())


def _ticking(machine):
    return lambda: switch.GlueArrival(switch.TICK_GLUE, {}, machine())


def _count_left_one():
    """...and every tick of that count but the last: the next one runs the click out and queues the button change."""
    image = make_image(_a_press_counting())
    while aes.read_field(image, "AES", "GL_CLICK_TICKS") > 1:
        aes_event.tick(image)
    return aes_event.as_pokes(image, upto=addrs.ST_RAM_BYTES)


A_MOVE = switch.A_MOUSE_PACKET
CASES = {
    "the button glue: a press, the desk waiting for a double click": (
        _arriving((aes_event.LEFT_DOWN_PACKET,), dict), switch.BUTTON_GLUE, switch.EVERY_REGISTER),
    "the button glue: a press, a process running": (
        _arriving((aes_event.LEFT_DOWN_PACKET,), aes_event.machine), switch.BUTTON_GLUE, switch.EVERY_REGISTER),
    "the button glue: the release of a button held, queued at once": (
        _arriving((aes_event.NO_BUTTON_PACKET,), aes_event.pressed), switch.BUTTON_GLUE, switch.EVERY_REGISTER),
    "the motion glue: a move": (_arriving(A_MOVE, dict), switch.MOTION_GLUE, switch.EVERY_REGISTER),
    "the motion glue: a move, a process running": (
        _arriving(A_MOVE, aes_event.machine), switch.MOTION_GLUE, switch.EVERY_REGISTER),
    "the tick glue: nothing counted": (_ticking(dict), switch.TICK_GLUE, switch.KEPT_BY_ANY_CALLEE),
    "the tick glue: a click count counted down": (_ticking(_a_press_counting), switch.TICK_GLUE, switch.KEPT_BY_ANY_CALLEE),
    "the tick glue: the click count run out, the change queued": (
        _ticking(_count_left_one), switch.TICK_GLUE, switch.KEPT_BY_ANY_CALLEE),
    "the tick glue: a delay counted down": (
        _ticking(lambda: _after(_waiting_for_a_timer_from_the_start(), aes_event.ticks(1))), switch.TICK_GLUE,
        switch.KEPT_BY_ANY_CALLEE),
    "the tick glue: the delay run out, tchange queued": (_ticking(_waiting_for_a_timer), switch.TICK_GLUE,
                                                         switch.KEPT_BY_ANY_CALLEE),
}
QUEUES_A_FORK = {"the button glue: the release of a button held, queued at once": addrs.AES_ROM_BCHANGE,
                 "the motion glue: a move": addrs.AES_ROM_MCHANGE,
                 "the motion glue: a move, a process running": addrs.AES_ROM_MCHANGE,
                 "the tick glue: the click count run out, the change queued": addrs.AES_ROM_BCHANGE,
                 "the tick glue: the delay run out, tchange queued": addrs.AES_ROM_TCHANGE}


def _waiting_for_a_timer_from_the_start():
    frame, pokes = aes_evasync.ev_multi_frame(aes.EV_MU_TIMER, timer=A_TIMER_MS)
    return aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes))


@pytest.mark.parametrize("name", CASES)
def test_the_glue_behaves_as_the_rom_s_on_both_blobs(name, blob):
    arrive, glue, kept = CASES[name]
    arrival = arrive()
    assert arrival.glue is glue, f"the interrupt arrived at {arrival.glue.symbol}"
    the_rom_s, _ours = switch.vet_the_glue(blob, arrival, kept)
    before = aes_event.fork_queue(make_image(arrival.machine))
    newly = [code for code, _data in aes_event.fork_queue(the_rom_s.memory)[len(before):]]
    assert newly == ([QUEUES_A_FORK[name]] if name in QUEUES_A_FORK else []), (
        f"the case's premise — what the ROM's glue queues: {[f'{code:#x}' for code in newly]}")


@pytest.mark.parametrize("name", CASES)
def test_both_shores_run_on_the_glue_s_private_stack(name, blob):
    """THE DEPTH, measured: each shore's run goes down its glue's private stack and no other. That OURS FITS is not
    this test's (a depth read off stores inside the stack cannot exceed it): `vet_the_glue_s_runs` refuses a store
    below the bottom — its own RED below — and the static reading holds the deepest path of the build."""
    arrive, glue, kept = CASES[name]
    the_rom_s, ours = switch.vet_the_glue(blob, arrive(), kept)
    assert switch.deepest_on(the_rom_s, glue.stack) > 0 and switch.deepest_on(ours, glue.stack) > 0


# What each glue's deepest path takes of its private stack, read off the build (`aes_switch.StackReading`): the
# button's 78 of 92 bytes (its register save, the pushed word, the Alcyon entry, b_click, forkq), the motion's 60,
# the tick's 58 of 96.
GLUE_STACK_USE = {"aes_rom_button_glue": 78, "aes_rom_motion_glue": 60, "aes_rom_tick_glue": 58}


@pytest.mark.parametrize("glue", (switch.BUTTON_GLUE, switch.MOTION_GLUE, switch.TICK_GLUE), ids=lambda glue: glue.symbol)
def test_a_glue_s_deepest_path_is_read_off_the_build_and_is_the_one_its_cases_run(glue, blob):
    """THE DERIVED CHECK of a private stack: the deepest any path of the blob's listing takes it — the glue's own
    pushes, its Alcyon entry, the C under it — FITS, on a path no case runs as on the others; and it is EXACTLY how
    deep the cases above go, so they do reach the worst one."""
    lo, hi = glue.stack
    read = switch.StackReading(blob.elf).of(glue.symbol)
    assert read.deepest <= hi - lo, f"{' -> '.join(read.path)} takes {read.deepest} bytes of a {hi - lo}-byte stack"
    measured = max(switch.deepest_on(switch.glue_on(blob, arrive()), glue.stack)
                   for arrive, entered, _kept in CASES.values() if entered is glue)
    assert measured == read.deepest == GLUE_STACK_USE[glue.symbol], (
        f"{glue.symbol}: the listing's deepest path takes {read.deepest} bytes, the cases reach {measured}")


# ---- THE VET'S OWN REDS: each refusal of `vet_the_glue_s_runs`, over a real pair of runs with ONE thing of ours forged ------
A_QUEUEING_CASE = "the motion glue: a move"
A_CALLEE_SAVED_REGISTER = "d3"


def _the_pair(blob):
    arrival = CASES[A_QUEUEING_CASE][0]()
    return arrival.glue, switch.glue_on_the_rom(arrival), switch.glue_on(blob, arrival)


def test_a_glue_that_stored_below_its_private_stack_is_refused(blob):
    """A store of ours just under the stack's bottom, where the ROM's run stores nothing: our frames did not fit."""
    glue, the_rom_s, ours = _the_pair(blob)
    below = glue.stack[0] - WORD_BYTES
    assert below not in the_rom_s.wrote, "the premise: the ROM's run stores nothing there"
    with pytest.raises(AssertionError, match="stored BELOW its private stack's bottom"):
        switch.vet_the_glue_s_runs(blob, glue, the_rom_s, ours._replace(wrote=ours.wrote | {below}))
    switch.vet_the_glue_s_runs(blob, glue, the_rom_s, ours)


def test_a_glue_that_gave_a_register_back_changed_is_refused(blob):
    glue, the_rom_s, ours = _the_pair(blob)
    changed = {**ours.registers, A_CALLEE_SAVED_REGISTER: ours.registers[A_CALLEE_SAVED_REGISTER] + 1}
    with pytest.raises(AssertionError, match=f"registers .*{A_CALLEE_SAVED_REGISTER}"):
        switch.vet_the_glue_s_runs(blob, glue, the_rom_s, ours._replace(registers=changed))


@pytest.mark.parametrize("queued", ["the ROM's own address of the function", "our entry of another fork function"])
def test_a_glue_that_queued_another_code_than_its_own_entry_of_the_function_is_refused(blob, queued):
    """THE VET OF A QUEUED CODE is by the function it names: neither the ROM's address (a relocation left out) nor
    our entry of ANOTHER fork function passes for "some code"."""
    glue, the_rom_s, ours = _the_pair(blob)
    slot, = [at for at in aes_event.FORK_CODE_SLOTS if at in the_rom_s.wrote]
    assert case.long_in(the_rom_s.memory, slot) == addrs.AES_ROM_MCHANGE == QUEUES_A_FORK[A_QUEUEING_CASE]
    assert case.long_in(ours.memory, slot) == blob.entry(switch.FORK_ENTRY_SYMBOLS[addrs.AES_ROM_MCHANGE])
    forged = {"the ROM's own address of the function": addrs.AES_ROM_MCHANGE,
              "our entry of another fork function": blob.entry(switch.FORK_ENTRY_SYMBOLS[addrs.AES_ROM_BCHANGE])}[queued]
    memory = bytearray(ours.memory)
    memory[slot:slot + LONG_BYTES] = forged.to_bytes(LONG_BYTES, "big")
    with pytest.raises(AssertionError, match="not its own entry of that function"):
        switch.vet_the_glue_s_runs(blob, glue, the_rom_s, ours._replace(memory=memory))


def test_the_differential_sees_the_register_file_an_arrival_hands(blob):
    """...and the differential sees what it is for: an arrival handed with another register file than the ROM's
    interrupt left reds on the image (the motion glue queues the point it is handed) — the registers apart, which
    the glue gives back as it found them and so differ first."""
    arrival = CASES[A_QUEUEING_CASE][0]()
    moved = arrival._replace(registers={**arrival.registers, "d0": arrival.registers["d0"] + 1})
    the_rom_s, ours = switch.glue_on_the_rom(arrival), switch.glue_on(blob, moved)
    with pytest.raises(AssertionError, match="memory differs"):
        switch.vet_the_glue_s_runs(blob, arrival.glue, the_rom_s, ours, kept=())


# ---- THE GLUE IS INSTALLED BY OUR OWN CODE ---------------------------------------------------------------------------------
# gsx_setmb_aes hands the VDI the button and the motion glue BY ADDRESS (`gsxif.c`; gsx_init and gsx_graphic install
# through it): the ROM's own off target — the image the ROM's byte for byte — and THIS BUILD'S on target. So a build
# that ships runs its own glue under the VDI's mouse interrupt, and with it everything the glue's pins and
# differentials above hold: b_click, forkq, the fork function queued, the counts made in memory.
# FOUR SURFACES: no word of either blob names the ROM's glue or switch; each installer's run on a blob leaves the two
# vectors at the blob's own entries; the VDI's own interrupt code, run over the machine that run left, reaches OUR glue
# and spends no cycle in the AES's ROM text; and Tier 3 compares those code addresses EXACTLY — the blob's entry for
# the ROM's routine it stands for (`bench/tier3.py`), nothing dropped — where the kit's own bench sees them differ.
INSTALLERS = (("aes_gsx_setmb_aes", "over the defaults"), ("aes_gsx_graphic", "back into graphics"),
              ("aes_gsx_init", "the AES's start-up"))
INSTALLER_S_FILE = "gsxif.c"
# The ROM's sites that name an entry of the switch's kind BY VALUE and whose routine is NOT reconstructed yet (census
# (b), `test_aes_rom_data.CODE_IMMEDIATES`): gem_main's two (the bare `rts` into AES_DRWADDR, the tick glue into the
# longword it later hands vex_timv), the two `pea gotopgm` of the accessory loader and the shell's launch, and
# ap_tplay's two (the bare `rts` handed to the VDI). Each must name OUR entry the day its routine is C.
def _entry_named(value):
    """The entry of the switch's kind whose ROM bytes hold the address `value`, or None."""
    return next((name for name, row in ENTRIES.items() if row.rom <= value < row.rom + row.bytes), None)


# ...READ OFF THE CENSUS ITSELF (`test_aes_rom_data.CODE_IMMEDIATES`: the site, the routine named, the file whose C owes
# it once ported): the sites that name an entry of the switch's kind — owed by nobody yet, or installed by `gsxif.c`.
_NAMING_AN_ENTRY = {site: (_entry_named(immediate.value), immediate.owed_by)
                    for site, immediate in rom_census.CODE_IMMEDIATES.items() if _entry_named(immediate.value)}
OWED_BY_ROUTINES_NOT_RECONSTRUCTED = {site: entry for site, (entry, owed_by) in _NAMING_AN_ENTRY.items() if owed_by is None}
INSTALLED_BY = {site: entry for site, (entry, owed_by) in _NAMING_AN_ENTRY.items() if owed_by == INSTALLER_S_FILE}
INSTALLER_S_SITES, SITES_OWED = 2, 6
assert (len(INSTALLED_BY), len(OWED_BY_ROUTINES_NOT_RECONSTRUCTED)) == (INSTALLER_S_SITES, SITES_OWED)
assert set(INSTALLED_BY.values()) == set(switch.GLUE_ENTRY_SYMBOLS.values())


def _rom_addresses_named_in(blob):
    """`{address in blob: the entry named}`: every even-aligned longword of `blob` that holds an address inside the
    ROM bytes of an entry of the switch's kind."""
    return {blob.base + at: _entry_named(int.from_bytes(blob.blob[at:at + LONG_BYTES], "big"))
            for at in range(0, len(blob.blob) - LONG_BYTES + 1, WORD_BYTES)
            if _entry_named(int.from_bytes(blob.blob[at:at + LONG_BYTES], "big"))}


def test_no_word_of_either_blob_names_the_rom_s_glue_or_switch(blob):
    """THE BUILD NAMES ITS OWN: nothing a blob links holds the ROM address of the glue, of drawrat or justretf, or of
    any routine of the switch — a routine of ours that handed one on would send the machine into the ROM's (or, in a
    ROM that no longer has it there, into whatever is)."""
    named = _rom_addresses_named_in(blob)
    assert not named, f"the blob names ROM entries of the switch's kind: { {hex(at): name for at, name in named.items()} }"


def test_the_scan_finds_a_rom_address_a_blob_names(blob):
    """THE SCAN'S OWN RED: the same blob with the ROM's button glue's address laid over four of its bytes, at an even
    offset — found, by the entry it names; laid at an odd one — no instruction's operand lies there — not."""
    planted = addrs.AES_ROM_BUTTON_GLUE.to_bytes(LONG_BYTES, "big")
    at = WORD_BYTES * (len(blob.blob) // LONG_BYTES)

    def with_it_at(offset):
        return types.SimpleNamespace(base=blob.base, blob=bytes(blob.blob[:offset]) + planted + bytes(blob.blob[offset + LONG_BYTES:]))
    assert _rom_addresses_named_in(with_it_at(at)) == {blob.base + at: "aes_rom_button_glue"}
    assert not _rom_addresses_named_in(with_it_at(at + 1))


def test_every_rom_site_that_names_the_glue_by_value_is_installed_or_owed():
    """THE LIST, held to the census of the ROM's own immediates: every instruction of the AES that names an entry of
    the switch's kind as a VALUE is either gsx_setmb_aes's (installed above) or one of a routine not reconstructed
    yet, by address — a new site, or one ported and not re-pointed, is neither."""
    import test_aes_rom_data as census
    named = {site: _entry_named(row.value) for site, row in census.CODE_IMMEDIATES.items() if _entry_named(row.value)}
    assert named == {**OWED_BY_ROUTINES_NOT_RECONSTRUCTED, **INSTALLED_BY}
    for site in INSTALLED_BY:
        assert census.CODE_IMMEDIATES[site].owed_by == "gsxif.c"
    for site in OWED_BY_ROUTINES_NOT_RECONSTRUCTED:
        assert census.CODE_IMMEDIATES[site].owed_by is None, f"${site:x}: ported — it must name our entry, and leave this list"


def _installer_row(key):
    return bench_tier3().row_named(key)


def _our_run_of(bench, row):
    """`row`'s routine run on `bench`'s blob over the row's machine: the image it left."""
    return bench._call(make_image(row.pokes), row.symbol, row.args, io_seed=row.io_seed).image


@pytest.mark.parametrize("key", INSTALLERS, ids=lambda key: key[0])
def test_each_installer_hands_the_vdi_this_build_s_own_glue(key, blob):
    """ON TARGET the two vectors hold the BLOB'S entries — the button glue in USER_BUT, the motion glue in USER_MOT
    (and in the AES's contrl[7..8], the last routine handed in) — on the kit's own bench, where nothing is relocated;
    the ROM's run of the same row leaves the ROM's two (the row's premise)."""
    row = _installer_row(key)
    final, _writes, _regs = emu.run(make_image(row.pokes), row.entry, dict(row.regs or {}), io_seed=row.io_seed)
    assert (case.long_in(final, switch.USER_BUT), case.long_in(final, switch.USER_MOT)) == (
        addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE), "the premise: the ROM's run installs the ROM's glue"
    ours = _our_run_of(blob, row)
    button, motion = blob.entry(switch.BUTTON_GLUE.symbol), blob.entry(switch.MOTION_GLUE.symbol)
    assert case.long_in(ours, switch.USER_BUT) == button, "USER_BUT: this build's button glue"
    assert case.long_in(ours, switch.USER_MOT) == motion, "USER_MOT: this build's motion glue"
    assert case.long_in(ours, aes.AES_GSX_CONTRL_PTR) == motion, "contrl[7..8]: the motion glue, handed in last"


@pytest.mark.parametrize("key", INSTALLERS, ids=lambda key: key[0])
def test_tier_3_compares_the_installed_glue_exactly_and_drops_nothing_for_it(key, blob):
    """THE RELOCATION: Tier 3's own bench hands back our image with each blob entry in a glue slot given the ROM
    address it stands for — so the row's compare is exact, with NO drop over the slots; and it maps nothing else (a
    slot the kit's bench left at the ROM's own value, or at any other, is as our run left it)."""
    row = _installer_row(key)
    assert not [lo for lo, hi, _why in row.dropped for slot in switch.GLUE_CODE_SLOTS if lo < slot + LONG_BYTES and slot < hi]
    unrelocated = _our_run_of(blob, row)
    relocated = _our_run_of(bench_tier3().RomBench(blob.elf.parent), row)
    back = {blob.entry(symbol): rom for rom, symbol in switch.GLUE_ENTRY_SYMBOLS.items()}
    for slot in switch.GLUE_CODE_SLOTS:
        found = case.long_in(unrelocated, slot)
        assert case.long_in(relocated, slot) == back.get(found, found), f"{slot:#x}: {found:#x} relocated otherwise"
    assert (case.long_in(relocated, switch.USER_BUT), case.long_in(relocated, switch.USER_MOT)) == (
        addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE)
    bench_tier3().measure(row, bench_tier3().RomBench(blob.elf.parent))


def _the_vdi_s_interrupt_over(memory, interrupt):
    """The ROM's own VDI mouse interrupt (`aes_event.mouse_packet`) run over `memory` IN PLACE, profiled: the cycles
    it spent in the AES's ROM text."""
    for at, data in interrupt.inputs.items():
        memory[at:at + len(data)] = data
    emu.install_chip_seeds()
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        result = emu.run_bench(memory, interrupt.entry, 0, emu.STACK_TOP, emu.SENTINEL, max_insns=switch.GLUE_INSNS,
                               seed_regs=rom_bench.entry_registers(interrupt.regs))
    finally:
        emu.prof_enable(False)
        emu.bench_abort()
    assert result["status"] != emu.BENCH_DOOR, "the interrupt did not end"
    return emu.prof_cycles(*aes.AES_TEXT)


INSTALLED_PATH_PACKETS = {"a move": (A_MOVE, "aes_rom_motion_glue", addrs.AES_ROM_MCHANGE),
                          "a press": ((aes_event.LEFT_DOWN_PACKET,), "aes_rom_button_glue", None)}


@pytest.mark.parametrize("packet", INSTALLED_PATH_PACKETS)
def test_the_vdi_s_interrupt_runs_this_build_s_glue_once_our_code_installed_it(packet, blob):
    """THE SHIPPED PATH, END TO END: over the machine OUR gsx_init left on the blob, the ROM's own VDI mouse interrupt
    calls through the two vectors into THIS BUILD — our glue, its Alcyon entry, our C — and spends NOT ONE CYCLE in the
    AES's ROM text; a move queues OUR entry of mchange. THE PREMISE beside it: over the same blob in a machine the
    ROM's gsx_init made, the same interrupt runs the ROM's glue."""
    header, glue, queues = INSTALLED_PATH_PACKETS[packet]
    row = _installer_row(("aes_gsx_init", "the AES's start-up"))
    ours = bytearray(_our_run_of(blob, row))
    before = aes_event.fork_queue(ours)
    lo = blob.entry(glue)
    in_the_rom = _the_vdi_s_interrupt_over(ours, aes_event.mouse_packet(*header))
    in_our_glue = emu.prof_cycles(lo, lo + ENTRIES[glue].bytes)
    assert in_our_glue > 0, f"the interrupt never entered {glue} of the blob"
    assert in_the_rom == 0, f"with our glue installed the interrupt still spent {in_the_rom} cycles in the AES's ROM text"
    if queues:
        (code, _data), = aes_event.fork_queue(ours)[len(before):]
        assert code == blob.entry(switch.FORK_ENTRY_SYMBOLS[queues])
    the_rom_s, _writes, _regs = emu.run(make_image(row.pokes), row.entry, dict(row.regs or {}), io_seed=row.io_seed)
    rom_made = bytearray(the_rom_s)
    rom_made[blob.base:blob.base + len(blob.blob)] = blob.blob
    assert _the_vdi_s_interrupt_over(rom_made, aes_event.mouse_packet(*header)) > 0, "the premise: the ROM's glue runs"
    assert emu.prof_cycles(lo, lo + ENTRIES[glue].bytes) == 0


# ---- drawrat and justretf: Tier 3's transcription relation ---------------------------------------------------------------
A_POINT = (100, 50)
A_MOVE_PLAYED = "the desk plays a move back"


def _played():
    arrival = aes_evinput.at(A_MOVE_PLAYED, aes_evinput.DRAWRAT)
    return arrival.arguments, arrival.machine


# drawrat's frame is two words — one longword its frame caller pushes; justretf takes nothing, and the plain caller.
ROWS = {
    (DRAWRAT, "no cursor routine saved: the bare `rts`"): lambda: frames.entered(DRAWRAT, A_POINT, aes_event.machine()),
    (DRAWRAT, "a recording played back: the VDI's own cursor routine"): lambda: frames.entered(DRAWRAT, *_played()),
    (JUSTRETF, "the routine that draws nothing"): lambda: (transcription.PLAIN_CALLER, aes_event.machine()),
}


@pytest.mark.parametrize("name,shape", sorted(ROWS), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    caller, pokes = ROWS[(name, shape)]()
    transcription.run_transcription(name, pokes, caller=caller)


def test_the_played_machine_s_cursor_routine_is_the_vdi_s_own():
    """The second row's premise: while the ROM's own appl_tplay plays a mouse record, the routine drawrat calls is the
    VDI's default cursor routine — not the bare `rts` the snapshot holds."""
    _arguments, machine = _played()
    assert aes.read_field(make_image(machine), "AES", "DRWADDR") == addrs.VDI_ROM_DEFAULT_USER_CUR
    assert aes.read_field(BASE_IMAGE, "AES", "DRWADDR") == addrs.AES_ROM_JUSTRETF


for (_name, _shape), _made in sorted(ROWS.items()):
    _caller, _pokes = _made()
    transcription.register_transcription(_name, _shape, _pokes, caller=_caller)
