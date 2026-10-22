"""THE TRAP DOOR, RUN (`src/aes/trapdoor.S`; its bytes are `test_aes_trapdoor.py`'s) — TIER 1 ON BOTH BLOBS, each case
an ARRIVAL of the ROM's own boot and a TRIP from it on each shore (`aes_trapdoor.py` says what those are).

  THE ROUND TRIP    an accessory's own AES call, from the handler's first instruction to the `rte`'s landing in the
                    program — the handler, aes_entry, the marshal, the opcode's routine, the dispatch (every other
                    process the dispatcher runs on the way), the way out: appl_init (an ALLOCATED accessory's, its UDA
                    above 64 KB: the first trap any boot makes), appl_find and appl_write (a STATIC process's, with
                    nobody else trapping on the way).
  SELECTOR 201      LABELLED: no program of any boot traps with it — a real arrival with D0's low word replaced. A
                    dispatch and nothing else: the marshal is not entered, on either shore.
  THE PTERM ARM     LABELLED the same way (selector 0): a CHECKPOINT where GEMDOS's own trap handler is entered — the
                    arm never comes back — the frame it pushed and the return address under it MAPPED.
  THE VDI ARM       the desk's first `trap #2` of a boot: on, through the vector GEM saved, to the BIOS's VDI door.
  THE WAY IN        the AES arm alone, to aes_entry's first instruction: the process's own stack taken, the frame
                    aes_entry is handed, the program's registers parked on its user stack.
  ub_trampoline     LABELLED: a staged call over the desk's machine, round a desk routine that returns at once.

WHAT EACH HOLDS: the register file and the megabyte where the trips end, outside the classes the case names (each
must differ: a class not needed is refused) — and WHO RAN, by the cycle profile: on our shore NOT ONE CYCLE in the
ROM's AES arm, its aes_entry, its marshal or its opcode switch wherever no other process traps on the way (and the
ROM's shore spends some there: the premise), and our own door entered.

THE DECLARED DIVERGENCE — D0'S HIGH WORD AT THE TRAP'S EXIT (ruling W3-R5; measured and explained here, reproduced
nowhere). The way out sets D0's LOW word (0) and reloads D1-A6; D0's high word nothing sets. ON THE ROM it is
the high word of THE LAST LONGWORD ALCYON'S CODE MOVED INTO D0 on the calling process's own path through the call —
and, where the opcode's arm moves none, THE PROGRAM'S OWN high word, still there from its `trap` (appl_init's arm is
inline word moves: 0 survives). Measured over the 30 exits of four accessory boots (the quiet, six-way, finding and
window pairs): 0 in 28; 1 in two — appl_find (fpdnm's answer, the PD it found: an allocated accessory's, above 64 KB)
and one wind_set (signal's `move.l a4,d0` at `$fe3fa2`: the PD of the process it woke, the same allocated one). OURS
IS GCC'S LAST LONGWORD: on the shipped blob 1 after appl_init of an allocated accessory (an address above 64 KB) and 0
after that wind_set — 5 of the 30 differ; on the bench blob the high half of an address of the calling process's own
stack, 1 for every call of an allocated accessory — 14 of the window and finding pairs' 26. THE VALUE IS IN NO REGISTER
AND NO BYTE OF THE MACHINE once the routine under the arm has returned: nothing in the `.S` or the thunk can
reproduce it, and reproducing Alcyon's leavings arm by arm is a second compiler. So each case DECLARES, per blob,
whether the high word differs — held both ways: declared and equal is refused, as undeclared and different is.
"""
import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu

import aes
import aes_boot
import aes_trapdoor as door
import case
import isr
import rom_data
import transcription

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = door.BUS
BENCH, SHIPPED = "the bench blob", "the shipped blob"
assert set(isr.BLOBS) == {BENCH, SHIPPED}
# What two builds' trips through one AES call differ in where the program has its registers back — each located from
# the machine's own pointers (`aes_trapdoor`), each REQUIRED to differ:
AN_AES_CALL_S_CLASSES = (door.the_blob_s_span, door.the_dispatcher_s_stack, door.its_saved_context, door.its_dead_stack)

TRAP_2 = 0x4e42                         # the instruction a program enters the door by
INT_OUT_POINTER = 3 * LONG_BYTES        # an AES parameter block: control, global, int_in, int_out, addr_in, addr_out
THE_USER_STACK_S_PARKED_REGISTERS = 14 * LONG_BYTES     # D1-D7, A0-A6 ($fe3ed2 movem.l d1-a6,-(a0))
AES_ENTRY_S_FRAME_BYTES = 3 * LONG_BYTES        # the handler's return address, two words, the parameter block
PTERM_FRAME = (addrs.GEMDOS_PTERM_FN, 0)        # what the Pterm arm pushes for `trap #1`: the function word, then the status
UB_S_RETURN_SITE = 0xFE3F56             # the instruction after ub_trampoline's `jsr`: the stack pointer taken back
# THE OPCODE SWITCH ROUND appl_init's ARM, as the ROM lays it: the head every opcode takes to the table's jump, the
# arm itself, and the tail every arm leaves by (the ladder's last instruction: `move.w d6,d0`, and the Line-F return).
APPL_INIT_OPCODE = 10
THE_SWITCH_S_HEAD = (addrs.AES_ROM_DISPATCH, 0xFE5DB2)
APPL_INIT_S_ARM = (0xFE5DB2, 0xFE5DF2)
THE_SWITCH_S_JUMP_AND_TAIL = (0xFE64BA, addrs.AES_ROM_MARSHAL)


def _appl_init():
    return door.accessory_trap(door.QUIET_PAIR, door.SECOND_ACCESSORY, 0)


def _appl_find():
    return door.accessory_trap(door.FINDING_PAIR, door.FIRST_ACCESSORY, 1)


def _appl_write():
    return door.accessory_trap(door.FINDING_PAIR, door.FIRST_ACCESSORY, 2)


def _selector_201():
    return door.relabelled(_appl_find(), door.SELECTOR_AES_ALT)


APPL_INIT, APPL_FIND, APPL_WRITE = 10, 13, 12       # the opcodes the three arrivals are held to carry
INIT, FIND, WRITE, ALT = ("appl_init, an allocated accessory's first trap", "appl_find, nobody else trapping",
                          "appl_write, nobody else trapping", "selector 201 (labelled): a dispatch alone")
# case -> (the arrival, the opcode its parameter block carries, the blobs on which D0's high word differs, whether
# another process traps on the way: the other accessory's first trap falls inside appl_init's)
ROUND_TRIPS = {
    INIT: (_appl_init, APPL_INIT, {BENCH, SHIPPED}, True),
    FIND: (_appl_find, APPL_FIND, {BENCH}, False),
    WRITE: (_appl_write, APPL_WRITE, set(), False),
    ALT: (_selector_201, APPL_FIND, set(), False),
}
PARAMETRIZED = [(name, blob) for name in ROUND_TRIPS for blob in isr.BLOBS]


def _opcode_of(arrival):
    """The opcode of the AES call an arrival carries: control[0] of the parameter block D1 names."""
    block = arrival.registers["d1"] & BUS
    return case.word_in(arrival.ram, case.long_in(arrival.ram, block) & BUS)


@pytest.fixture(scope="module")
def round_trip():
    """`(the ROM's trip, ours)` of a case on a blob, made once a module."""
    made = {}

    def of(name, blob_name):
        if (name, blob_name) not in made:
            blob, arrival = isr.blob_named(blob_name), ROUND_TRIPS[name][0]()
            landing, spans = door.program_frame(arrival)[1], door.profiled_spans(blob)
            made[(name, blob_name)] = (door.trip(arrival, landing, profiled=spans), door.trip(arrival, landing, blob, profiled=spans))
        return made[(name, blob_name)]
    return of


# ---- the arrivals ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_an_arrival_is_a_program_s_own_trap_at_the_handler_s_first_instruction(name):
    """THE PREMISE of every round trip, read off the arrival: the CPU stands at the ROM's handler in supervisor state,
    the frame under its stack pointer a USER program's — its PC inside the trapping accessory's own text, just past
    a `trap #2` — D0's low word the selector, D1 a parameter block whose opcode is the case's. THE UDA'S IN-AES WORD
    is 0, the process outside the AES — BUT AT A PROCESS'S FIRST TRAP, where it is still the 1 getpd set when the
    process was made (uda_insuper, `$fe3970`: a new process is marked inside before its program ever runs)."""
    make, opcode, _differs, _others = ROUND_TRIPS[name]
    arrival = make()
    status, landing = door.program_frame(arrival)
    assert arrival.registers["pc"] == door.HANDLER and not status & addrs.SR_SUPERVISOR
    basepage = case.long_in(arrival.ram, arrival.process + aes.PD_LDADDR) & BUS
    text = case.long_in(arrival.ram, basepage + addrs.BASEPAGE_TBASE) & BUS
    assert text <= landing - WORD_BYTES < text + case.long_in(arrival.ram, basepage + addrs.BASEPAGE_TLEN)
    assert case.word_in(arrival.ram, landing - WORD_BYTES) == TRAP_2, "the frame's PC is the instruction after a `trap #2`"
    assert arrival.registers["d0"] & door.WORD_MASK == (door.SELECTOR_AES_ALT if name == ALT else door.SELECTOR_AES)
    assert _opcode_of(arrival) == opcode
    marked = case.word_in(arrival.ram, door.uda_of(arrival.ram, arrival.process) + aes.UDA_IN_SUPER)
    assert marked == (aes.header_constants("pdpipe.h")["UDA_INSIDE_THE_AES"] if name == INIT else 0)


def test_the_two_processes_of_the_round_trips_are_an_allocated_one_above_64k_and_a_static_one():
    """...and WHICH processes: appl_init's is the accessory whose PD the loader ALLOCATED — its UDA above 64 KB, what
    brings a 1 into the high word of every address of its stack — the other two a static PD's, below."""
    allocated, static = _appl_init().process, _appl_find().process
    table = range(aes.AES_PD_TABLE, aes.AES_PD_TABLE + aes.AES_PD_COUNT * aes.PD_BYTES)
    assert allocated not in table and static in table
    assert door.uda_of(_appl_init().ram, allocated) >> door.HIGH_WORD == 1 and door.uda_of(_appl_find().ram, static) >> door.HIGH_WORD == 0


# ---- the round trip ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,blob_name", PARAMETRIZED)
def test_a_round_trip_lands_the_program_where_the_rom_s_does_with_the_rom_s_machine(name, blob_name, round_trip):
    """THE DIFFERENTIAL: where the `rte` lands, the WHOLE register file — the program's PC, its status register, both
    stack pointers, D1-A6, D0's low word and (where the case does not declare it) its high — and the megabyte outside
    the four classes: the answers in the program's own arrays, the process's UDA (its in-AES word, the stack stored
    for its next trap, the two stack pointers), every list and every other process."""
    the_rom_s, ours = round_trip(name, blob_name)
    declared = blob_name in ROUND_TRIPS[name][2]
    assert not door.differing(the_rom_s, ours, AN_AES_CALL_S_CLASSES, d0_high_differs=declared)


@pytest.mark.parametrize("name,blob_name", PARAMETRIZED)
def test_the_program_gets_back_every_register_but_d0_and_its_own_frame(name, blob_name, round_trip):
    """WHAT THE DIFFERENTIAL COMPARED, read off each shore against the ARRIVAL: D1-D7 and A1-A6 as the program had
    them, its user stack pointer, the supervisor stack pointer the exception left once its frame is popped, the
    frame's own status word and PC — and D0's low word 0. A0 IS NOT GIVEN BACK (a ROM behaviour, the ROM's bytes):
    the handler takes the user stack pointer INTO A0 before it parks the registers, so what it parks and reloads
    for A0 is that pointer — and the reload's own `(a0)+` leaves A0 the pointer as it stood at the trap. The process
    is outside the AES again, and the stack its UDA keeps for its next trap is the one it kept for this."""
    arrival = ROUND_TRIPS[name][0]()
    status, landing = door.program_frame(arrival)
    uda = door.uda_of(arrival.ram, arrival.process)
    for made in round_trip(name, blob_name):
        left = made.stopped.registers
        kept = [register for register in aes_boot.REGISTER_NAMES if register not in ("d0", "a0", "pc", "sr", "isp")]
        assert {register: left[register] for register in kept} == {register: arrival.registers[register] for register in kept}
        assert left["a0"] == arrival.registers["usp"] != arrival.registers["a0"]
        assert (left["pc"], left["sr"]) == (landing, status)
        assert left["isp"] == arrival.registers["isp"] + aes_boot.FRAME_BYTES and left["d0"] & door.WORD_MASK == 0
        assert case.word_in(made.stopped.ram, uda + aes.UDA_IN_SUPER) == 0
        assert case.long_in(made.stopped.ram, uda + aes.UDA_SUPER_SP) == case.long_in(arrival.ram, uda + aes.UDA_SUPER_SP)


@pytest.mark.parametrize("name,blob_name", PARAMETRIZED)
def test_who_ran_a_round_trip(name, blob_name, round_trip):
    """WHO RAN, by the cycle profile of both trips (`aes_trapdoor.vet_who_ran`). THE ROM'S SHORE: cycles in the ROM's
    AES arm and aes_entry — the premise — and none in the blob. OURS: our AES arm, way out and aes_entry entered;
    and, on every trip no other process traps inside, NOT ONE CYCLE in the ROM's AES arm, aes_entry, marshal or
    opcode switch. Where another process does trap on the way (appl_init: the other accessory's own first trap, the
    ROM's on both shores — the vector is not bound) our shore's cycles there are fewer than the ROM's by at least
    the arm's own."""
    door.vet_who_ran(*round_trip(name, blob_name), others_trap=ROUND_TRIPS[name][3])


def test_every_round_trip_asks_who_ran(round_trip, monkeypatch):
    """THE GUARD IS ASKED (a guard is silent on honest numbers whether it is called or not): the test above hands
    `vet_who_ran` the case's own two trips, and says another process traps inside appl_init's alone."""
    asked = []
    monkeypatch.setattr(door, "vet_who_ran", lambda *trips, others_trap: asked.append((trips, others_trap)))
    for name, blob_name in PARAMETRIZED:
        test_who_ran_a_round_trip(name, blob_name, round_trip)
    assert asked == [(round_trip(name, blob_name), name == INIT) for name, blob_name in PARAMETRIZED]


def _with_no_cycle_in(made, spans):
    return made._replace(stopped=made.stopped._replace(profile={**made.stopped.profile, **{span: 0 for span in spans}}))


@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_who_ran_refuses_a_trip_of_ours_that_ran_the_rom_s_door_or_never_its_own(blob_name, round_trip):
    """THE GUARD'S OWN REDS, on real trips: THE ROM'S OWN TRIP handed in as ours (what a trip entered at the ROM's
    handler is: every cycle of the call in the ROM's door) is refused by its cycles there; our trip with the profile
    of our aes_entry zeroed is refused as never entered; the ROM's with its arm's zeroed as no premise; and the trip
    another process traps inside (appl_init's) is refused where it is asked for not one cycle — and where its
    cycles in the ROM's door are the whole of the ROM's shore's."""
    blob = isr.blob_named(blob_name)
    the_rom_s, ours = round_trip(WRITE, blob_name)
    with pytest.raises(AssertionError, match="our trip never entered our own door's part"):
        door.vet_who_ran(the_rom_s, the_rom_s._replace(blob=blob))
    entered_and_in_the_rom_s = ours._replace(stopped=ours.stopped._replace(profile={**the_rom_s.stopped.profile, **{
        span: ours.stopped.profile[span] for span in door.our_door(blob).values()}}))
    with pytest.raises(AssertionError, match="cycles in the ROM's door"):
        door.vet_who_ran(the_rom_s, entered_and_in_the_rom_s)
    with pytest.raises(AssertionError, match="never entered our own door's part `aes_entry`"):
        door.vet_who_ran(the_rom_s, _with_no_cycle_in(ours, (door.our_door(blob)[door.AES_ENTRY],)))
    with pytest.raises(AssertionError, match="the arrival does not take it"):
        door.vet_who_ran(_with_no_cycle_in(the_rom_s, (door.ROM_DOOR[door.THE_AES_ARM], door.ROM_DOOR[door.AES_ENTRY])), ours)
    others_inside = round_trip(INIT, blob_name)
    with pytest.raises(AssertionError, match="cycles in the ROM's door"):
        door.vet_who_ran(*others_inside)
    whole = others_inside[1]._replace(stopped=others_inside[1].stopped._replace(profile={**others_inside[1].stopped.profile, **{
        span: others_inside[0].stopped.profile[span] for span in door.ROM_DOOR.values()}}))
    with pytest.raises(AssertionError, match="accounts for at most"):
        door.vet_who_ran(others_inside[0], whole, others_trap=True)


@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_selector_200_enters_the_marshal_and_selector_201_does_not(blob_name, round_trip):
    """THE ONE BRANCH OF aes_entry, held on both shores by the profile: over ONE arrival, selector 200 runs the
    marshal and the opcode switch (ours: the thunk, and the C behind it) and selector 201 runs NEITHER — on the ROM
    (the premise: the labelled class takes the arm it is labelled for) and on ours. And the program's answer array is
    written by 200 and left as it was by 201."""
    our_door = door.our_door(isr.blob_named(blob_name))
    marshalled, bare = round_trip(FIND, blob_name), round_trip(ALT, blob_name)
    assert door.cycles_in(marshalled[0], door.ROM_DOOR, door.BEHIND_IT) and not door.cycles_in(bare[0], door.ROM_DOOR, door.BEHIND_IT)
    assert door.cycles_in(marshalled[1], our_door, door.THE_THUNK) and door.cycles_in(marshalled[1], our_door, door.BEHIND_IT)
    assert not door.cycles_in(bare[1], our_door, door.THE_THUNK) and not door.cycles_in(bare[1], our_door, door.BEHIND_IT)
    arrival = _appl_find()
    block = arrival.registers["d1"] & BUS
    int_out = case.long_in(arrival.ram, block + INT_OUT_POINTER) & BUS
    for the_rom_s, ours in (marshalled, bare):
        assert case.word_in(the_rom_s.stopped.ram, int_out) == case.word_in(ours.stopped.ram, int_out)
    assert case.word_in(marshalled[0].stopped.ram, int_out) != case.word_in(arrival.ram, int_out), "appl_find answered"
    assert case.word_in(bare[0].stopped.ram, int_out) == case.word_in(arrival.ram, int_out), "selector 201 answers nothing"


@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_the_door_s_own_instructions_cost_one_call_what_they_cost_another(blob_name, round_trip):
    """THE DOOR'S OWN PATH IS ONE PATH: our AES arm, way out, aes_entry and thunk spend, to the cycle, the same on
    every selector-200 trip whatever the opcode and the process — and selector 201 the same less the marshal's call.
    (No price: the door's row is the flip's. A pad anywhere in the door moves every one of these alike — it is the
    byte pin that sees a pad; this holds that no trip takes another way through.)"""
    our_door = door.our_door(isr.blob_named(blob_name))

    def own(name):
        return tuple(door.cycles_in(round_trip(name, blob_name)[1], our_door, part)
                     for part in (door.THE_AES_ARM, door.AES_ENTRY, door.THE_THUNK))
    assert own(INIT) == own(FIND) == own(WRITE)
    arm, entry, thunk = own(ALT)
    assert (arm, thunk) == (own(FIND)[0], 0) and 0 < entry < own(FIND)[1]


# ---- THE DOOR'S PRICE: ONE ROUND TRIP, ITS OWN CYCLES ON EACH SHORE (the narrow door flip, band 5 wave 3) --------------------
# The door is entered by an exception and left by an `rte`: no call and return exists, and the table's row is a call.
# So ITS PRICE IS HELD HERE, BY ITS OWN BATTERY, PER SELECTOR, at a program's own trap: the cycles each shore spends in
# THE DOOR'S OWN INSTRUCTIONS on one round trip — the AES arm and the way out (the pinned region: the same bytes),
# aes_entry (the stream) and, on ours, the marshal's thunk — the marshal, the opcode switch and the routine under them
# being their own rows'. THE ROM'S COUNT LEAVES OUT ITS LINE-F HANDLER: aes_entry reaches the marshal, dsptch and the
# way out through three Line-F calls (two for selector 201) where ours `jsr`s — cycles the table's convention counts
# for the ROM on every other row and that the profile here cannot tell from the marshal's own — so THE RATIO PINNED IS
# AN UPPER BOUND, and it is under the bar as it stands. (INSIDE A PRICED ROW the same instructions are in an
# accessory's turn, `aes_accessory_turns_pinned`: there the Line-F handler is counted, as the convention has it.)
DOOR_S_OWN = (door.THE_AES_ARM, door.AES_ENTRY)
THE_DOOR_S_PRICE = {door.SELECTOR_AES: (856, 814), door.SELECTOR_AES_ALT: (730, 758)}       # (ours, the ROM's): 1.05, 0.96
PRICED_AT = {INIT: door.SELECTOR_AES, FIND: door.SELECTOR_AES, WRITE: door.SELECTOR_AES, ALT: door.SELECTOR_AES_ALT}
NOBODY_ELSE_TRAPS = (FIND, WRITE, ALT)  # (appl_init's trip holds another process's whole trap: the ROM's on both shores)


@pytest.mark.parametrize("name", NOBODY_ELSE_TRAPS)
@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_the_door_s_own_round_trip_is_priced_per_selector_and_under_the_bar(name, blob_name, round_trip):
    """ONE ROUND TRIP'S OWN CYCLES, each shore's door alone, PINNED per selector on both blobs (the door is the same
    bytes in both) — and at or under the bar with the ROM's Line-F passes left out of its count."""
    the_rom_s, ours = round_trip(name, blob_name)
    our_door = door.our_door(isr.blob_named(blob_name))
    priced = (door.cycles_in(ours, our_door, *DOOR_S_OWN, door.THE_THUNK), door.cycles_in(the_rom_s, door.ROM_DOOR, *DOOR_S_OWN))
    assert priced == THE_DOOR_S_PRICE[PRICED_AT[name]], f"{name}: the door's own cycles (ours, the ROM's) moved: say why"
    assert priced[0] / priced[1] <= bench_tier3().TIER3_FUNCTION_BAR
    assert not door.cycles_in(the_rom_s, our_door, *DOOR_S_OWN, door.THE_THUNK), "the ROM's trip ran no cycle of our door"


def test_the_door_s_price_is_the_same_trip_whoever_else_traps_inside_it(round_trip):
    """...and appl_init's trip, through three processes, spends in OUR door what every selector-200 trip does (the
    other process's trap inside it is the ROM's on both shores of a trip: the vector is not bound there)."""
    for blob_name in isr.BLOBS:
        _its, ours = round_trip(INIT, blob_name)
        our_door = door.our_door(isr.blob_named(blob_name))
        assert door.cycles_in(ours, our_door, *DOOR_S_OWN, door.THE_THUNK) == THE_DOOR_S_PRICE[door.SELECTOR_AES][0]


# ---- THE CENSUS OF THE DOOR AND THE LOADER AT TIER 3: a ratio, or one of three reasons, by name -----------------------------
# Every routine of band 5 wave 3 says how it is held at Tier 3: PRICED (rows of the table; or a ratio its own battery
# pins, said so), or one of THREE REASONS it has no second column:
NEVER_RETURNS = "NEVER RETURNS: a checkpoint — the machine where it leaves, no second column"
RUNS_A_PROGRAM = "RUNS A PROGRAM: priced over a scripted Pexec alone; a real launch loads over the harness's blob"
NO_MACHINE = "NO MACHINE: no oracle machine reaches it"
IN_THE_TABLE, BY_ITS_BATTERY = "rows of the table", "a ratio its own battery pins"
THE_CENSUS = {
    "AES_ROM_TRAP2": (BY_ITS_BATTERY, "the AES arm's round trip per selector (above); inside every accessory's turn"),
    "the trap's VDI arm": (BY_ITS_BATTERY, "the selector switch, the ROM's own bytes: cut out of both own counts and held equal "
                                           "on every row behind the door (`tier3.vet_who_ran_the_door`)"),
    "the trap's Pterm arm": (NEVER_RETURNS, "ends at GEMDOS's own trap handler, Pterm(0) pushed"),
    "AES_ROM_TRAP2_EXIT": (BY_ITS_BATTERY, "the way out: in the round trip"),
    "AES_ROM_ENTRY": (BY_ITS_BATTERY, "the stream: in the round trip"),
    "AES_ROM_UB_TRAMPOLINE": (NO_MACHINE, "a desk window with icons drawn (band 6's `$fde844` under it); held at Tier 1 "
                                          "over a staged call"),
    "AES_ROM_GOTOPGM": (NEVER_RETURNS, "enters the program: held where every door machine's boot enters each accessory"),
    "AES_ROM_CRIT_ERR": (BY_ITS_BATTERY, "held to the ROM's cycle count with eralert served (`test_aes_crit_err.py`; ruling G-2)"),
    "AES_ROM_DOS_EXEC": (RUNS_A_PROGRAM, "five `.S` rows over the scripted Pexec"),
    "AES_ROM_SNDCLI": (IN_THE_TABLE, "four rows, GEMDOS replayed"),
    "AES_ROM_LDACCS": (IN_THE_TABLE, "two rows, GEMDOS replayed"),
    "AES_ROM_CRE_APROC": (IN_THE_TABLE, "one row"),
    "AES_ROM_FREE_ACCS": (IN_THE_TABLE, "one row, Mfree scripted"),
    "the cartridge's loader ($fed554, $fed5c2)": (NO_MACHINE, "the oracle serves no cartridge (ruling W3-R6)"),
}


def test_the_census_says_how_each_routine_of_the_door_and_the_loader_is_held_at_tier_3():
    """EACH ENTRY IS WHAT IT SAYS: a routine named IN THE TABLE has priced rows there (and as many as it says the
    loader's battery registers); one with a REASON has none; the door's own entries are all here."""
    tier3 = bench_tier3()
    reasons = {NEVER_RETURNS, RUNS_A_PROGRAM, NO_MACHINE}
    assert {how for how, _what in THE_CENSUS.values()} == reasons | {IN_THE_TABLE, BY_ITS_BATTERY}
    assert {entry.upper() for entry in transcription.TRAPDOOR_ENTRIES} <= set(THE_CENSUS)
    for name, (how, _what) in THE_CENSUS.items():
        if not hasattr(addrs, name):
            continue
        rows = [row for row in tier3.ROWS if tier3.rom_address(row) == getattr(addrs, name)]
        if how == IN_THE_TABLE:
            assert rows, f"{name}: said priced in the table, and no row is"
        elif name != "AES_ROM_DOS_EXEC":
            assert not rows, f"{name}: has a row in the table now: say so in the census"
    assert [row for row in tier3.ROWS if tier3.rom_address(row) == addrs.AES_ROM_DOS_EXEC], "dos_exec's scripted rows"


# ---- THE DECLARED DIVERGENCE: D0's high word ----------------------------------------------------------------------------------
def test_on_the_rom_d0_s_high_word_is_the_program_s_own_where_the_arm_moves_no_longword_into_d0(round_trip):
    """WHAT THE ROM LEAVES, held on the real calls. appl_init's arm is inline word moves (no call, and no instruction
    of its path through the switch moves a longword into D0 — read off the ROM below), so the program's own high
    word comes back: 0, what it trapped with. appl_find's answer is fpdnm's — the PD found, a longword — whose high
    word comes back: the allocated accessory's PD lies above 64 KB, so 1 — WHICH THE PROGRAM THEN TRAPS WITH AGAIN
    (it loads the selector as a word): appl_write's arrival holds that 1, and appl_write's own routine moves a
    longword into D0 and hands back 0. And THE SAME ARRIVAL TAKEN WITH SELECTOR 201 (labelled) — no arm at all —
    hands the 1 back, on the ROM and on both blobs: where nothing is moved, both builds keep the program's own."""
    assert case.long_in(BASE_IMAGE, addrs.AES_OPCODE_TABLE + (APPL_INIT_OPCODE - addrs.AES_OPCODE_FIRST) * LONG_BYTES) == APPL_INIT_S_ARM[0]
    on_its_path = [text for span in (THE_SWITCH_S_HEAD, APPL_INIT_S_ARM, THE_SWITCH_S_JUMP_AND_TAIL)
                   for _at, text in rom_data.instructions(*span)]
    calls = [text for text in on_its_path[:-1] if text is None or text.split()[0] in ("jsr", "bsr")]
    into_d0 = [text for text in on_its_path[:-1] if text and text.endswith(",%d0")]
    assert not calls and into_d0 and all(text.split()[0].endswith("w") for text in into_d0), (
        f"appl_init's path through the switch calls something or moves a longword into D0: {calls} {into_d0}")
    for name, trapped_with, handed_back in ((INIT, 0, 0), (FIND, 0, 1), (WRITE, 1, 0)):
        the_rom_s, _ours = round_trip(name, BENCH)
        assert ROUND_TRIPS[name][0]().registers["d0"] >> door.HIGH_WORD == trapped_with
        assert the_rom_s.stopped.registers["d0"] >> door.HIGH_WORD == handed_back
    bare = door.relabelled(_appl_write(), door.SELECTOR_AES_ALT)
    landing = door.program_frame(bare)[1]
    for made in (door.trip(bare, landing), *(door.trip(bare, landing, isr.blob_named(blob_name)) for blob_name in isr.BLOBS)):
        assert made.stopped.registers["d0"] == 1 << door.HIGH_WORD, "the high word it trapped with, the low word 0"
    found = _appl_find()
    answered = round_trip(FIND, BENCH)[0].stopped.ram
    int_out = case.long_in(found.ram, (found.registers["d1"] & BUS) + INT_OUT_POINTER) & BUS
    the_found = next(pd for pd in _every_pd(answered) if case.word_in(answered, pd + aes.PD_PID) == case.word_in(answered, int_out))
    assert the_found >> door.HIGH_WORD == 1, "appl_find found the allocated accessory: the PD whose high word D0 carries out"


def _every_pd(ram):
    static = [aes.AES_PD_TABLE + index * aes.PD_BYTES for index in range(aes.AES_PD_COUNT)]
    return static + [case.long_in(ram, aes.AES_ACCESSORY_PDS + index * LONG_BYTES) & BUS
                     for index in range(case.word_in(ram, aes.AES_ACCESSORY_COUNT))]


def test_the_declarations_are_what_the_two_blobs_leave(round_trip):
    """...AND OURS, per blob — the table `ROUND_TRIPS` declares, said in numbers: the bench blob leaves the high half
    of an address of the calling process's own stack (1 for the allocated accessory's every call, 0 for a static
    process's — so appl_find, where the ROM leaves 1, differs); the shipped blob 1 after the allocated accessory's
    appl_init and, after appl_find, the PD's own high word as the ROM does."""
    high = {(name, blob_name): tuple(made.stopped.registers["d0"] >> door.HIGH_WORD for made in round_trip(name, blob_name))
            for name, blob_name in PARAMETRIZED}
    assert high == {(INIT, BENCH): (0, 1), (INIT, SHIPPED): (0, 1), (FIND, BENCH): (1, 0), (FIND, SHIPPED): (1, 1),
                    (WRITE, BENCH): (0, 0), (WRITE, SHIPPED): (0, 0), (ALT, BENCH): (0, 0), (ALT, SHIPPED): (0, 0)}
    assert {key for key, (its, ours) in high.items() if its != ours} == {
        (name, blob_name) for name, (_make, _opcode, differs, _others) in ROUND_TRIPS.items() for blob_name in differs}


def test_a_declaration_not_needed_and_a_difference_not_declared_are_both_refused(round_trip):
    """THE HOLD'S OWN REDS: appl_write's trip with D0's high word DECLARED to differ (it is 0 on both shores) and
    appl_init's with it NOT declared are each a finding, by name."""
    not_needed = door.differing(*round_trip(WRITE, SHIPPED), AN_AES_CALL_S_CLASSES, d0_high_differs=True)
    assert len(not_needed) == 1 and door.D0_S_HIGH_WORD in not_needed[0]
    undeclared = door.differing(*round_trip(INIT, SHIPPED), AN_AES_CALL_S_CLASSES)
    assert undeclared == ["d0: the ROM's 0x0, ours 0x10000"]


# ---- the differential's own reds -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("left_out", AN_AES_CALL_S_CLASSES[1:], ids=lambda located: located.__name__)
def test_each_class_of_a_round_trip_is_needed(left_out, round_trip):
    """A round trip compared WITHOUT one of its classes is red in that class's bytes, on each blob — so none is a
    class the trips pass without (and one named where nothing differs is refused: below)."""
    for blob_name in isr.BLOBS:
        without = tuple(located for located in AN_AES_CALL_S_CLASSES if located is not left_out)
        found = door.differing(*round_trip(WRITE, blob_name), without)
        covered = set(left_out(*round_trip(WRITE, blob_name)))
        assert len(found) == 1 and "differ outside the classes named" in found[0]
        assert int(found[0].split("from ")[1].split(":")[0], 16) in covered


def test_a_class_nothing_differs_in_is_refused(round_trip):
    """THE VDI ARM'S TRIP differs in nothing but the blob: naming an AES call's classes for it is refused, each."""
    arrival = door.desk_s_first_vdi_trap()
    blob = isr.blob_named(SHIPPED)
    vdi_door = case.long_in(arrival.ram, addrs.SYSVAR_VDI_ENTRY) & BUS
    found = door.differing(door.trip(arrival, vdi_door), door.trip(arrival, vdi_door, blob), AN_AES_CALL_S_CLASSES)
    assert len(found) == len(AN_AES_CALL_S_CLASSES) - 1 and all("not needed" in finding for finding in found)


def test_the_differential_sees_a_register_and_a_byte(round_trip):
    """...and it sees what it is for: one register of our trip's file changed is a finding by name — and so is ONE
    BYTE JUST OUTSIDE EACH CLASS, which is what holds the classes to their bounds: the process's in-AES word (under
    its saved registers), its saved A6 (the longword after them), the first byte AT the stack pointer its UDA keeps
    (the dead stack ends under it), and the bytes on either side of the dispatcher's stack."""
    the_rom_s, ours = round_trip(WRITE, SHIPPED)
    nudged = ours._replace(stopped=ours.stopped._replace(registers={**ours.stopped.registers, "a3": ours.stopped.registers["a3"] + 2}))
    assert [finding.split(":")[0] for finding in door.differing(the_rom_s, nudged, AN_AES_CALL_S_CLASSES)] == ["a3"]
    uda = door.uda_of(ours.stopped.ram, ours.arrival.process)
    dispatcher_s = door.the_dispatcher_s_stack(the_rom_s, ours)
    just_outside = (uda + aes.UDA_REGS - 1, uda + aes.UDA_A6, case.long_in(ours.stopped.ram, uda + aes.UDA_SUPER_SP) & BUS,
                    dispatcher_s.start - 1, dispatcher_s.stop)
    for at in just_outside:
        marked = bytearray(ours.stopped.ram)
        marked[at] ^= 1
        found = door.differing(the_rom_s, ours._replace(stopped=ours.stopped._replace(ram=bytes(marked))), AN_AES_CALL_S_CLASSES)
        assert len(found) == 1 and f"from {at:#x}" in found[0], f"a byte changed at {at:#x}, just outside a class: {found}"


def test_a_trip_that_idles_before_it_arrives_is_refused():
    """A TRIP ASKED TO AN ADDRESS THE MACHINE NEVER REACHES ends at the boot's idle and is refused by name (the
    quiet pair's second AES call is a wait for ever: its `rte` never lands)."""
    waiting = door.accessory_trap(door.QUIET_PAIR, door.SECOND_ACCESSORY, 1)
    with pytest.raises(aes_boot.Refused, match="reached its first idle and never arrived"):
        door.trip(waiting, door.program_frame(waiting)[1])


def test_an_arrival_no_boot_makes_is_refused():
    with pytest.raises(aes_boot.Refused, match="no 9-th to arrive at"):
        door.accessory_trap(door.QUIET_PAIR, door.SECOND_ACCESSORY, 9)


# ---- the way in ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("blob_name", isr.BLOBS)
@pytest.mark.parametrize("name", (INIT, FIND))
def test_the_way_in_hands_aes_entry_the_rom_s_frame_on_the_process_s_own_stack(name, blob_name):
    """THE AES ARM ALONE, to aes_entry's first instruction — both shores from the arrival, the megabyte equal outside
    the blob with ONE longword mapped (the handler's return address, a site of each build's own region) and nothing
    dropped. READ OFF OURS: the CPU on the stack the process's UDA named, twelve bytes pushed — the return address,
    the selector, a zero word, the parameter block; the UDA marked inside the AES, the trap's own stack pointer and
    the user's parked in it; D1-A6 parked on the user stack, fourteen longwords under where it stood (A0's slot the
    user stack pointer itself, which the handler had just taken into A0); A6 the UDA."""
    arrival, blob = ROUND_TRIPS[name][0](), isr.blob_named(blob_name)
    the_rom_s, ours = door.trip(arrival, door.ENTRY), door.trip(arrival, blob.entry(door.ENTRY_SYMBOL), blob)
    uda = door.uda_of(arrival.ram, arrival.process)
    stack = case.long_in(arrival.ram, uda + aes.UDA_SUPER_SP) & BUS
    handed = stack - AES_ENTRY_S_FRAME_BYTES
    assert not door.differing(the_rom_s, ours, (door.the_blob_s_span,), mapped=(handed,))
    left, ram = ours.stopped.registers, ours.stopped.ram
    assert left["isp"] == handed and left["a6"] == uda
    assert case.long_in(ram, handed) == door.in_the_region(blob, door.WAY_OUT)
    assert (case.word_in(ram, handed + 4), case.word_in(ram, handed + 6), case.long_in(ram, handed + 8)) == (
        door.SELECTOR_AES, 0, arrival.registers["d1"])
    assert case.word_in(ram, uda + aes.UDA_IN_SUPER) == 1
    assert case.long_in(ram, uda + aes.UDA_TRAP_SSP) == arrival.registers["isp"]
    parked = arrival.registers["usp"] - THE_USER_STACK_S_PARKED_REGISTERS
    assert case.long_in(ram, uda + aes.UDA_USER_SP) == left["usp"] == parked
    saved = [case.long_in(ram, parked + index * LONG_BYTES) for index in range(THE_USER_STACK_S_PARKED_REGISTERS // LONG_BYTES)]
    program_s = {**arrival.registers, "a0": arrival.registers["usp"]}       # A0's slot: the user stack pointer (above)
    assert saved == [program_s[register] for register in (*(f"d{n}" for n in range(1, 8)), *(f"a{n}" for n in range(7)))]


# ---- the Pterm arm and the VDI arm ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_the_pterm_arm_reaches_gemdos_with_pterm_0_pushed_and_never_comes_back(blob_name):
    """THE PTERM ARM — a CHECKPOINT, and LABELLED (selector 0 on a real arrival): where GEMDOS's own trap handler is
    entered (the address the machine's vector $84 holds) both shores stand with one register file and one megabyte
    outside the blob, ONE longword mapped: the PC of the frame `trap #1` pushed, the instruction after the trap — a
    site of each build's region, never returned to. Under that frame: `$4c`, 0 — Pterm(0) — and under those the
    program's own frame, untouched. Not one cycle of ours in the ROM's handler."""
    arrival, blob = door.relabelled(_appl_find(), door.SELECTOR_PTERM), isr.blob_named(blob_name)
    gemdos, spans = case.long_in(arrival.ram, addrs.VECTOR_TRAP_GEMDOS) & BUS, door.profiled_spans(blob)
    the_rom_s, ours = door.trip(arrival, gemdos, profiled=spans), door.trip(arrival, gemdos, blob, profiled=spans)
    frame = ours.stopped.registers["isp"]
    assert not door.differing(the_rom_s, ours, (door.the_blob_s_span,), mapped=(frame + aes_boot.FRAME_PC,))
    assert frame == arrival.registers["isp"] - 2 * WORD_BYTES - aes_boot.FRAME_BYTES
    assert case.long_in(the_rom_s.stopped.ram, frame + aes_boot.FRAME_PC) == door.AES_ARM, "the instruction after the ROM's `trap #1`"
    pushed = frame + aes_boot.FRAME_BYTES
    assert (case.word_in(ours.stopped.ram, pushed), case.word_in(ours.stopped.ram, pushed + WORD_BYTES)) == PTERM_FRAME
    our_door = door.our_door(blob)
    assert door.cycles_in(the_rom_s, door.ROM_DOOR, door.SELECTOR_SWITCH) and door.cycles_in(the_rom_s, door.ROM_DOOR, door.THE_PTERM_ARM)
    assert door.cycles_in(ours, our_door, door.SELECTOR_SWITCH) and door.cycles_in(ours, our_door, door.THE_PTERM_ARM)
    assert not sum(ours.stopped.profile[span] for span in door.ROM_DOOR.values())
    assert not door.cycles_in(ours, our_door, door.THE_AES_ARM), "the trap never came back into the arm behind it"


@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_the_vdi_arm_goes_on_to_the_handler_gem_found_with_nothing_changed(blob_name):
    """THE VDI ARM, at a real arrival (the desk's first `trap #2` of the boot: D0 = $73): where the run reaches the
    handler GEM found in the vector and kept (SYSVAR_VDI_ENTRY: the BIOS's VDI door) both shores stand with THE
    ARRIVAL'S OWN register file but the PC — the caller's frame still under the stack pointer — and one megabyte
    outside the blob, nothing mapped, nothing dropped. Not one cycle of ours in the ROM's handler."""
    arrival, blob = door.desk_s_first_vdi_trap(), isr.blob_named(blob_name)
    vdi_door, spans = case.long_in(arrival.ram, addrs.SYSVAR_VDI_ENTRY) & BUS, door.profiled_spans(blob)
    assert vdi_door == addrs.GEM_TRAP2_VDI_DOOR and arrival.registers["d0"] & door.WORD_MASK == door.SELECTOR_VDI
    the_rom_s, ours = door.trip(arrival, vdi_door, profiled=spans), door.trip(arrival, vdi_door, blob, profiled=spans)
    assert not door.differing(the_rom_s, ours, (door.the_blob_s_span,))
    assert {**ours.stopped.registers, "sr": None} == {**arrival.registers, "pc": vdi_door, "sr": None}, (
        "every register the arrival's but the PC — and the condition codes, the selector's three compares'")
    our_door = door.our_door(blob)
    assert door.cycles_in(the_rom_s, door.ROM_DOOR, door.SELECTOR_SWITCH) == door.cycles_in(ours, our_door, door.SELECTOR_SWITCH) > 0
    assert not sum(ours.stopped.profile[span] for span in door.ROM_DOOR.values())


# ---- ub_trampoline --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("blob_name", isr.BLOBS)
def test_ub_trampoline_calls_the_desk_s_draw_code_on_the_desk_s_own_stack_and_comes_back(blob_name):
    """ub_trampoline — LABELLED (a staged call over the desk's booted machine; the desk's draw code MADE to return
    at its first instruction: `aes_trapdoor.through_ub_trampoline`). AT THE CALL each shore stands in ITS draw code
    — the ROM's `$fde844`; on a blob, since band 6 slice F3 (N18), the thunk into our C, the trampoline's operand
    relocated — on THE STACK THE DESK'S START-UP ALLOCATED (the machine's own AES_USERDEF_STACK: its top less the PARMBLK
    and the return address), the PARMBLK handed, the caller's stack pointer parked — one megabyte outside the blob
    but the return address, a site of each build's region, mapped. WHERE IT RETURNS: the caller's stack pointer
    back, D0 the draw code's answer, every other register as the callee left it, the megabyte equal the same way."""
    machine, blob = aes_boot.desk_machine(), isr.blob_named(blob_name)
    registers = dict(transcription.DIRTY)
    the_rom_s, ours = door.through_ub_trampoline(machine.ram, registers), door.through_ub_trampoline(machine.ram, registers, blob)
    top = machine.long(aes.AES_USERDEF_STACK) & BUS
    assert top and the_rom_s.sp_at_the_call == ours.sp_at_the_call == top - 2 * LONG_BYTES
    assert case.long_in(ours.at_the_call, top - LONG_BYTES) == door.A_PARMBLK
    assert case.long_in(ours.at_the_call, aes.AES_USERDEF_SP_SAVE) == emu.STACK_TOP
    assert the_rom_s.registers_at_the_call == ours.registers_at_the_call
    its_return, our_return = (case.long_in(shore.at_the_call, top - 2 * LONG_BYTES) for shore in (the_rom_s, ours))
    assert door.mapped_back(blob, our_return) == its_return == UB_S_RETURN_SITE
    its_ours = aes_boot.ours_of(blob)
    outside = [at for at in range(door.RAM_BYTES) if not its_ours.base <= at < its_ours.end
               and not top - 2 * LONG_BYTES <= at < top - LONG_BYTES]
    for its, mine in ((the_rom_s.at_the_call, ours.at_the_call), (the_rom_s.returned, ours.returned)):
        assert all(its[at] == mine[at] for at in outside)
    assert the_rom_s.d0 == ours.d0 == door.A_DRAW_ANSWER and the_rom_s.registers == ours.registers

