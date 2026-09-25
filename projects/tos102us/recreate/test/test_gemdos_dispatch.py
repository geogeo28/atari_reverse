"""The GEMDOS DISPATCHER @ $fc94e4 — `src/gemdos/dispatch.c`, and what a `trap #1` becomes.

    $fc94e4  link    a6,#-54
    $fc94e8          clr.w   $68fa                   ; the call counter, cleared...
    $fc94ee          addq.w  #1,$68fa                ; ...and bumped, at the label a restart returns to
    $fc94fc          cmpi.w  #87,-34(a6) / ble       ; the bound, SIGNED and from above only
    $fc9504          moveq   #-32,d0                 ; ...EINVFN, having read no record at all
    $fc9510          jsr     $fc4f38                 ; arm the termination record at $7ef4
    $fc973e          muls.w  #6,d0 / add.l #$fd307a  ; the table: 88 SIX-byte records
    $fc9754          move.w  4(a0),-28(a6)           ; ...and the ARGUMENT DESCRIPTOR in each

WHAT THE DESCRIPTOR IS, which is the fact this battery exists to pin. Its low two bits are an
ARGUMENT-FRAME CLASS — 4, 8, 12 or 14 bytes of the caller's own words, copied onto the stack before
the `jsr` — and bit 7 marks a call whose argument is a HANDLE. For the character-device group
(selectors 1..11 and 16..19) the low seven bits of such a descriptor are a STANDARD HANDLE NUMBER,
0..3, and the dispatcher looks that handle up in the running process's own table at `p_run+$30`:

  * still a DEVICE (<= 0, which is what $ff/$fe/$fd are) — call the handler directly, after
    REWRITING the descriptor to 1 for the two console calls that take a string and 0 for the rest.
  * a FILE (> 0, i.e. `Fforce` has redirected it) — take the arm at `$fd328a`'s table instead, where
    `Cconin` becomes an `Fread` and `Cconws` a loop of `Fwrite`s.

THREE THINGS ARE PROVED THREE DIFFERENT WAYS here, because the dispatcher cannot be proved one way:

  1. The EINVFN arm is a WHOLE-FUNCTION differential at `$fc94e4`. It returns before the termination
     record is armed, so nothing about the record is in its way.
  2. The dispatch itself is a SLICE differential entered at `$fc973e` through the trampoline
     `gemdos.py` describes — because the record IS armed on every in-range call and it is the
     68000 frame of the `jsr` that armed it, which a C core has no counterpart for.
  3. The DESCRIPTOR SEMANTICS are claims about the ORACLE: run it to the handler's own first
     instruction and read the words it pushed off the stack. That is the only shape that reaches the
     classes whose handlers are not reconstructed yet — and it is the sharper claim anyway, because
     it names the bytes rather than the result they produced.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import case
import gemdos

for _name in ("gemdos_dispatch", "gemdos_dispatch_selector"):
    getattr(_lib, _name).restype = ctypes.c_uint32

# The handlers this wave can bind, keyed by the ROM address the table names — which is how the hook
# dispatches, so a case whose selector reaches anything else fails by naming it rather than by being
# answered with a fabricated 0 (`gemdos.bound_handlers`).
#
# Each takes `(buf, arguments, argument_bytes)` and returns the handler's D0, exactly as the 68000
# `jsr` would leave it. None of these six reads an argument, which is why none of them uses the two
# it is given: they are the descriptor-0 leaves, and the four bytes the dispatcher pushed in front of
# them are pushed for every call whether the handler wants them or not.
HANDLERS = {
    addrs.GEMDOS_SVERSION: lambda buf, args, width: _lib.gemdos_sversion(),
    addrs.GEMDOS_UNIMPLEMENTED: lambda buf, args, width: _lib.gemdos_unimplemented(),
    addrs.GEMDOS_FGETDTA: lambda buf, args, width: _lib.gemdos_fgetdta(buf),
    addrs.GEMDOS_DGETDRV: lambda buf, args, width: _lib.gemdos_dgetdrv(buf),
    addrs.GEMDOS_TGETDATE: lambda buf, args, width: _lib.gemdos_tgetdate(buf),
    addrs.GEMDOS_TGETTIME: lambda buf, args, width: _lib.gemdos_tgettime(buf),
}

# The six selectors those handlers answer, with what the ROM's own record says about each. Spelt as
# a table because every case below is "this selector, through the whole decision" and the thing that
# varies is the selector.
DISPATCHED = (
    ("Sversion", addrs.GEMDOS_SVERSION_FN),
    ("the undefined-selector stub", addrs.GEMDOS_UNDEFINED_FN),
    ("Fgetdta", addrs.GEMDOS_FGETDTA_FN),
    ("Dgetdrv", addrs.GEMDOS_DGETDRV_FN),
    ("Tgetdate", addrs.GEMDOS_TGETDATE_FN),
    ("Tgettime", addrs.GEMDOS_TGETTIME_FN),
)

PAST_THE_TABLE = addrs.GEMDOS_MAX_SELECTOR + 1
RESET_INSNS, RESET_CYCLES = 1, 40   # what the oracle charges before the entry runs
# How many of the 88 records name the stub — the ABI's undefined selectors, counted.
UNDEFINED_SELECTORS = 38
A_DTA = 0x0002_4680


def run_slice(selector, words=(), pokes=None):
    """One dispatch, entered at `$fc973e` through the trampoline, with THIS battery's handlers
    bound — `test/gemdos.py` owns the shape, because `test_gemdos_handles.py` drives the same slice
    and the two copies had drifted (see `gemdos.run_slice`)."""
    return gemdos.run_slice(selector, words, pokes, handlers=HANDLERS)


def run_to_handler(selector, words=(), pokes=None):
    """...and the same staging run on the ORACLE ALONE, stopped at the handler's own first
    instruction — which is where the argument frame the dispatcher built is on the stack."""
    staged = gemdos.slice_pokes(selector, words, pokes)
    return emu.run(make_image(staged), gemdos.TRAMPOLINE_AT, {"a5": 0},
                   stop_pc=gemdos.rom_handler(selector))




def rom_descriptor(selector):
    at = addrs.GEMDOS_FUNCTION_TABLE + selector * addrs.GEMDOS_RECORD_BYTES
    return case.word_in(BASE_IMAGE, at + addrs.GEMDOS_RECORD_DESCRIPTOR)


# ---- the table itself, as a fact about the ROM ----------------------------------------------------

def test_the_table_is_88_six_byte_records_and_40_of_them_are_the_stub():
    """The shape the dispatcher's `muls.w #6` and its `cmpi.w #87` describe, read back out of the
    ROM. The stub count is what says the selector map is the published ABI's: every selector the ABI
    leaves undefined names `$fc933e`, and no defined one does."""
    stubs = [selector for selector in range(addrs.GEMDOS_FUNCTION_COUNT)
             if gemdos.rom_handler(selector) == addrs.GEMDOS_UNIMPLEMENTED]
    assert addrs.GEMDOS_MAX_SELECTOR == addrs.GEMDOS_FUNCTION_COUNT - 1
    assert len(stubs) == UNDEFINED_SELECTORS
    assert addrs.GEMDOS_UNDEFINED_FN in stubs and addrs.GEMDOS_SVERSION_FN not in stubs
    # ...and `Super`, which is in the table and can never be reached through it: the trap entry
    # serves it inline and returns through `rte` (`src/gemdos/trap1.S`).
    assert gemdos.rom_handler(addrs.GEMDOS_SUPER_FN) == addrs.GEMDOS_UNIMPLEMENTED


@pytest.mark.parametrize("what,selector", DISPATCHED, ids=lambda arg: arg)
def test_each_dispatched_selector_reaches_its_own_handler(what, selector):
    """The index arithmetic, as the only thing that could put a call in the wrong record: the same
    staging with a different selector must reach a different routine."""
    assert gemdos.rom_handler(selector) in HANDLERS


# ---- 1. the bound, which is the whole of what a selector past the table gets ------------------------

@pytest.mark.parametrize("selector", (PAST_THE_TABLE, 0x60, 0x7FFF))
def test_a_selector_past_the_table_answers_einvfn(selector):
    """A WHOLE-FUNCTION differential, and the only arm of `$fc94e4` that is one: it returns before
    the termination record is armed, so there is nothing in the image but the call counter.

    EINVFN is the same -32 the undefined-selector stub answers, and the two are NOT the same event —
    this one reads no record and makes no call, and $0c has a whole dispatch before it.
    """
    with gemdos.bound_handlers({}):
        info = case.run(addrs.GEMDOS_DISPATCH, {"a5": 0, "_pokes": gemdos.dispatch_pokes(selector)},
                        gemdos.recording(lambda lib, buf: lib.gemdos_dispatch(buf,
                                                                              gemdos.ARGUMENTS_AT)))
    assert info["regs"]["d0"] == addrs.GEMDOS_EINVFN
    # A LIVE claim only because the glue opened a pass: outside one the hook refuses instead and
    # this list is empty whatever the candidate did.
    assert not gemdos.HANDLER_CALLS, "a selector past the table reached a handler"


def test_the_call_counter_is_cleared_and_then_bumped():
    """Two stores rather than one, and the difference is visible only in the ledger: the ROM clears
    $68fa on entry and increments it at a label the process-termination path branches BACK to, so a
    call that outlives a restart counts more than once."""
    with gemdos.bound_handlers({}):
        info = case.run(addrs.GEMDOS_DISPATCH,
                        {"a5": 0, "_pokes": gemdos.dispatch_pokes(PAST_THE_TABLE)},
                        gemdos.recording(lambda lib, buf: lib.gemdos_dispatch(buf,
                                                                              gemdos.ARGUMENTS_AT)))
    assert case.written(info, addrs.GEMDOS_CALL_DEPTH, 2) == 1


def test_the_bound_is_signed_so_a_negative_selector_passes_it():
    """`cmpi.w #87 / ble` bounds the selector from ABOVE ONLY, which is the same shape the BIOS
    dispatcher has. `Gemdos(-1)` passes, `muls.w #6` makes -6, and the record read is the six bytes
    BEFORE the table — which in this ROM is the tail of the VDI's data.

    Documented rather than dispatched: the handler those bytes spell is not a routine, so there is
    nothing for either side to call. What the case can say is that the ROM got past the bound, and
    it says it at the instruction that reads the record.
    """
    _final, _writes, regs = emu.run(make_image(gemdos.dispatch_pokes(0xFFFF)),
                                    addrs.GEMDOS_DISPATCH, {"a5": 0},
                                    stop_pc=addrs.GEMDOS_DISPATCH_SELECTOR)
    assert regs["ninsns"] > 0, "a negative selector was refused, so the bound is not the ROM's"


# ---- 2. the dispatch itself -------------------------------------------------------------------------

@pytest.mark.parametrize("what,selector", DISPATCHED, ids=lambda arg: arg)
def test_a_dispatched_call_answers_with_its_handlers_d0(what, selector):
    """The slice, over every selector this wave has a handler for: the same image on both sides, and
    the handler's own result as the dispatcher's.

    The ORACLE runs the ROM's handler; the CANDIDATE runs our reconstruction of it, through the hook
    `gemdos.bound_handlers` bound BY THE ADDRESS THE TABLE HOLDS. So this is also the second proof of
    each of those leaves: a reconstruction bound under the wrong address would never be called, and
    the refusal `bound_handlers` reports on its way out is what turns that into a failure, not a 0.
    """
    run_slice(selector, pokes=gemdos.dta_poke(A_DTA))
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [gemdos.rom_handler(selector)]


def test_the_descriptor_zero_leaves_take_the_four_byte_frame():
    """...and what "the same call" means for the argument frame: descriptor 0 is four bytes, which
    the dispatcher pushes whether the handler reads them or not."""
    info = run_slice(addrs.GEMDOS_SVERSION_FN, words=(0x1234, 0x5678))
    _handler, arguments, argument_bytes = gemdos.HANDLER_CALLS[0]
    assert arguments == gemdos.ARGUMENTS_AT + addrs.GEMDOS_ARGUMENT_WORD
    assert argument_bytes == addrs.GEMDOS_ARGUMENT_BYTES_0
    assert info["regs"]["d0"] == addrs.GEMDOS_VERSION


# ---- 3. the argument frame, class by class, measured off the ORACLE's own stack ----------------------

# The four classes, a selector that carries each, and the frame the ROM pushes for it. The widest is
# `Pexec`'s, which is a word and three longwords — 14 bytes, where a fourth longword would be 16.
ARGUMENT_CLASSES = (
    ("class 0 (Sversion)", addrs.GEMDOS_SVERSION_FN, addrs.GEMDOS_ARGUMENT_BYTES_0),
    ("class 1 (Fsetdta)", addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_ARGUMENT_BYTES_1),
    ("class 2 (Mshrink)", 0x4A, addrs.GEMDOS_ARGUMENT_BYTES_2),
    ("class 3 (Pexec)", addrs.GEMDOS_PEXEC_FN, addrs.GEMDOS_ARGUMENT_BYTES_3),
)
# Seven distinctive words, so that a frame one word too wide or too narrow names itself.
ARGUMENT_WORDS = (0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666, 0x7777)


@pytest.mark.parametrize("what,selector,argument_bytes", ARGUMENT_CLASSES, ids=lambda arg: arg)
def test_each_descriptor_class_copies_its_own_span_of_the_callers_words(what, selector,
                                                                        argument_bytes):
    """THE DESCRIPTOR'S LOW TWO BITS ARE A FRAME WIDTH, and this is where that is measured.

    Run the ORIGINAL to the handler's own first instruction and the words it copied are on the stack
    directly below the dispatcher's frame. Three of these four selectors have no reconstruction to
    call — `Mshrink` and `Pexec` are the memory manager's and the process group's — which is exactly
    why the claim is made about the oracle: the frame is the DISPATCHER's decision, and it can be
    read whether or not anything is ready to be called with it.
    """
    assert rom_descriptor(selector) & addrs.GEMDOS_DESC_ARGUMENT_MASK == \
        {4: 0, 8: 1, 12: 2, 14: 3}[argument_bytes]
    final, _writes, regs = run_to_handler(selector, words=ARGUMENT_WORDS)
    assert regs["ninsns"] > 0, "the run never reached the handler"
    pushed = gemdos.pushed_arguments(final, argument_bytes)
    assert pushed == list(ARGUMENT_WORDS[:argument_bytes // gemdos.WORD_BYTES]), (
        f"{what} pushed {[hex(value) for value in pushed]} — the frame is not the caller's first "
        f"{argument_bytes} bytes of words")


def test_the_candidate_copies_the_same_span_the_rom_does():
    """...and the other side of it: our C is told the same span the ROM pushed.

    The hook takes the argument ADDRESS and the WIDTH rather than the bytes, because off target
    there is no stack to push them onto — so the claim is that the span it names holds the same
    words the original's `move.w` chain copied.
    """
    run_slice(addrs.GEMDOS_SVERSION_FN, words=ARGUMENT_WORDS)
    _handler, arguments, argument_bytes = gemdos.HANDLER_CALLS[0]
    final, _writes, _regs = run_to_handler(addrs.GEMDOS_SVERSION_FN, words=ARGUMENT_WORDS)
    assert argument_bytes == addrs.GEMDOS_ARGUMENT_BYTES_0
    # The span our C was given, read out of the image the ORIGINAL ran over — which is where the
    # case staged the words, so this is the same bytes seen from the two sides.
    told = [int.from_bytes(bytes(final[at:at + gemdos.WORD_BYTES]), "big")
            for at in range(arguments, arguments + argument_bytes, gemdos.WORD_BYTES)]
    assert told == gemdos.pushed_arguments(final, argument_bytes)


def test_no_record_asks_for_an_argument_class_the_dispatcher_has_an_arm_for_all_of():
    """THE FOUR ARMS ARE FOUR COMPARES, and a class of 4 or more falls through all of them and
    returns 0 without calling anything ($fc9cb8).

    Nothing in this ROM reaches it: every one of the 88 records carries a class of 0..3, and the
    only other way to a record — a NEGATIVE selector, which the signed bound lets through — lands
    inside the character-device range, where the descriptor is REWRITTEN before the class is read.
    So the arm is transcribed and unreachable, and this is what says so rather than a comment.
    """
    classes = {rom_descriptor(selector) & addrs.GEMDOS_DESC_ARGUMENT_MASK
               for selector in range(addrs.GEMDOS_FUNCTION_COUNT)}
    assert classes <= set(range(addrs.GEMDOS_ARGUMENT_CLASSES))
    # ...and the negative half, in one fact: the character-device range's upper bound is NOT
    # negative, so every selector below zero is inside it — and inside it the descriptor is
    # rewritten to 0 or 1 before the class is read.
    assert addrs.GEMDOS_REDIRECT_LAST >= 0


# ---- the standard-handle redirection, which is what bit 7 of a descriptor is for ---------------------

# The character-device group and the standard handle each member consults. Read off the ROM's own
# records rather than listed: the descriptor IS the handle number, in its low seven bits.
DEVICE_SELECTORS = tuple(selector for selector in range(1, addrs.GEMDOS_REDIRECT_SECOND_LAST + 1)
                         if rom_descriptor(selector) & addrs.GEMDOS_DESC_HANDLE)


def test_the_character_device_group_is_the_selectors_with_a_handle_descriptor():
    """The two runs the dispatcher's four compares carve out — 1..11 and 16..19 — are exactly the
    selectors whose record carries a $80..$83 descriptor, with two exceptions in each direction that
    say what the compares are FOR.

    `Crawio` ($06) sits inside the range with a descriptor of 0, so the group is not "the range";
    `Fread` and `Fwrite` carry $82 and sit OUTSIDE it, so it is not "the descriptor" either. It is
    the intersection, and that is what makes the range compares load-bearing.
    """
    assert set(DEVICE_SELECTORS) <= set(range(addrs.GEMDOS_REDIRECT_FIRST,
                                              addrs.GEMDOS_REDIRECT_LAST + 1)) | \
        set(range(addrs.GEMDOS_REDIRECT_SECOND_FIRST, addrs.GEMDOS_REDIRECT_SECOND_LAST + 1))
    assert 0x06 not in DEVICE_SELECTORS, "Crawio's record does carry a handle descriptor after all"
    assert rom_descriptor(addrs.GEMDOS_FREAD_FN) & addrs.GEMDOS_DESC_HANDLE
    assert addrs.GEMDOS_FREAD_FN > addrs.GEMDOS_REDIRECT_SECOND_LAST


def test_the_standard_handles_a_fresh_process_has_are_the_three_devices():
    """...and what the descriptor's low bits index: `p_uft`, six bytes in the running basepage. The
    snapshot's desktop has the default set, which is what makes every case above take the "still a
    device" arm without saying so."""
    handles = [gemdos.BASEPAGE + addrs.BASEPAGE_HANDLES + index for index in range(4)]
    assert [int.from_bytes(bytes(BASE_IMAGE[at:at + 1]), "big", signed=True) for at in handles] == \
        [-1, -1, -2, -3], "the snapshot's standard handles are not stdin/stdout/stdaux/stdprn"


@pytest.mark.parametrize("selector,argument_bytes", (
    (0x01, addrs.GEMDOS_ARGUMENT_BYTES_0),      # Cconin — nothing to pass
    (0x02, addrs.GEMDOS_ARGUMENT_BYTES_0),      # Cconout — the character, in the four bytes
    (0x09, addrs.GEMDOS_ARGUMENT_BYTES_1),      # Cconws — a POINTER, so the descriptor becomes 1
    (0x0A, addrs.GEMDOS_ARGUMENT_BYTES_1),      # Cconrs — ...and so does this one's
    (0x10, addrs.GEMDOS_ARGUMENT_BYTES_0),      # Cconos
))
def test_an_unredirected_device_call_has_its_descriptor_rewritten(selector, argument_bytes):
    """THE REWRITE, which is the half of the redirection that runs on every ordinary machine.

    A $80..$83 descriptor says nothing about the argument frame, so once the standard handle turns
    out to be a device after all the dispatcher REPLACES it: 1 for the two console calls that take a
    string, 0 for everything else. The frame the handler is entered with is what says which happened,
    and it is measured here off the oracle's stack — these five handlers are the character-device
    group's and are not reconstructed yet.
    """
    assert rom_descriptor(selector) & addrs.GEMDOS_DESC_HANDLE
    final, _writes, regs = run_to_handler(selector, words=ARGUMENT_WORDS)
    assert regs["ninsns"] > 0, "the run never reached the handler, so it took the redirected arm"
    assert gemdos.pushed_arguments(final, argument_bytes) == \
        list(ARGUMENT_WORDS[:argument_bytes // gemdos.WORD_BYTES])


@pytest.mark.parametrize("selector,arm", (
    (0x01, 0xFC97B6),       # Cconin  -> read one byte through Fread
    (0x02, 0xFC97DC),       # Cconout -> write it through Fwrite
    (0x09, 0xFC97FA),       # Cconws  -> a loop of Fwrites
    (0x0A, 0xFC982C),       # Cconrs  -> the line editor, which also Fseeks
    (0x0B, 0xFC98DC),       # Cconis  -> a constant: a file is always ready
))
def test_a_redirected_standard_handle_takes_the_table_arm_instead(selector, arm):
    """...and the other half: point the process's standard handle at a FILE and the handler is not
    called at all. `$fd328a`'s 19 longwords, indexed by selector - 1, are what runs instead.

    NOT RECONSTRUCTED — every arm is an `Fread`, an `Fwrite` or an `Fseek` and the file system is
    not written — so the claim is made as a slice: the run is required to arrive at the arm.
    """
    handle = 6       # the first real file handle; anything > 0 takes this arm
    staged = gemdos.slice_pokes(selector, words=ARGUMENT_WORDS,
                                pokes=gemdos.standard_handles_poke([handle, handle, handle,
                                                                    handle]))
    _final, _writes, regs = emu.run(make_image(staged), gemdos.TRAMPOLINE_AT, {"a5": 0},
                                    stop_pc=arm)
    assert regs["ninsns"] > 0


def test_the_slice_trampoline_costs_what_its_rows_are_net_of():
    """Every Tier 3 row for the dispatcher's slice is entered at the trampoline on the ORIGINAL's
    side and by a C call on ours, so the trampoline's three instructions sit in one column alone and
    `rom_bench.Measurement` takes them off it. A row netted by the wrong constant is a row about
    nothing, so the constant is measured here rather than declared."""
    insns, cycles = gemdos.SLICE_ENTRY_COST
    _final, _writes, regs = emu.run(make_image(gemdos.slice_pokes(addrs.GEMDOS_SVERSION_FN)),
                                    gemdos.TRAMPOLINE_AT, {"a5": 0},
                                    stop_pc=addrs.GEMDOS_DISPATCH_SELECTOR)
    assert (regs["ninsns"] - RESET_INSNS, regs["cycles"] - RESET_CYCLES) == (insns, cycles)


# ---- the termination record, which this reconstruction does NOT write ---------------------------------

def test_the_termination_record_is_the_callers_own_frame():
    """WHAT `src/gemdos/dispatch.c` OMITS, measured rather than described.

    Between the bound and the dispatch the ROM calls `$fc4f38` with `$7ef4`, and what that writes is
    three longwords of the 68000 frame the call was made from: the dispatcher's own frame pointer,
    the stack slot its argument sits in, and the address to resume at. `Pterm` comes back to them.

    A C core has no counterpart for any of the three — its frame is the host's or GCC's, and the
    resume address is an instruction inside the ROM — so the record is not reconstructed, and this
    is the case that says exactly how big the hole is: twelve bytes, at one address, all three of
    them derived from a stack this reconstruction does not have.
    """
    staged = gemdos.dispatch_pokes(addrs.GEMDOS_SVERSION_FN)
    _final, writes, _regs = emu.run(make_image(staged), addrs.GEMDOS_DISPATCH, {"a5": 0})
    record = [int.from_bytes(bytes(writes[addrs.GEMDOS_TERMINATION_JMPBUF + 4 * word + byte]
                                   for byte in range(4)), "big") for word in range(3)]
    assert record[0] == gemdos.DISPATCHER_FRAME_AT, "the first longword is not the dispatcher's A6"
    assert record[1] == gemdos.DISPATCHER_SP, "the second is not the dispatcher's own stack pointer"
    assert addrs.GEMDOS_DISPATCH < record[2] < addrs.GEMDOS_DISPATCH_SELECTOR, (
        "the third is not a resume address inside the dispatcher")


def test_the_slice_the_battery_enters_is_past_that_record():
    """...and the consequence, which is why cases 2 above are slices: a run entered at `$fc973e`
    writes NOTHING at `$7ef4`, so the omission is not in the way of anything this file proves."""
    staged = gemdos.slice_pokes(addrs.GEMDOS_SVERSION_FN)
    _final, writes, _regs = emu.run(make_image(staged), gemdos.TRAMPOLINE_AT, {"a5": 0})
    assert addrs.GEMDOS_TERMINATION_JMPBUF not in writes


# ---- the mask -------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", (1, 2, 3))
def test_no_gemdos_case_depends_on_a_byte_the_capture_does_not_reproduce(seed):
    """THE MASK, for the wave's TRANSCRIPTION rows — `test_boot_snapshot.py`'s claim, made here over
    the rows its own sweep cannot reach.

    Two captures of the same boot disagree over 1,929 bytes. A case that read one of them would be
    verified against one particular boot, and GEMDOS reads more of the live machine than the BIOS
    leaves do: the running process's basepage, the process tables, the date and time words. Running
    the ORIGINAL over the snapshot and over a snapshot whose masked regions hold noise, and
    requiring the two indistinguishable, is what answers it.

    `gemdos.CASES` is NOT swept here: those rows are spliced into `VERIFIED_CASES`, where the
    orchestrator makes exactly this claim about every one of them. What it cannot see is a
    transcription row, whose relation is the second differential rather than `harness.differential`
    — `test_bios_trap.py` sweeps its own for the same reason.
    """
    import test_boot_snapshot as snapshot
    import test_gemdos_trap1                                       # noqa: F401  (registers its rows)

    scrambled = snapshot._scrambled_base(seed)
    shapes = [(name, caller, regs, pokes, None, None, ())
              for name, _symbol, caller, regs, pokes, _cost in gemdos.TRANSCRIPTIONS]
    for shape in shapes:
        assert snapshot._oracle_outputs(scrambled, shape) == \
            snapshot._oracle_outputs(snapshot.BASE_IMAGE, shape), (
                f"{shape[0]} behaves differently over a snapshot whose masked regions hold noise, "
                f"so it reads a byte two captures of the same boot disagree about")


# ---- the registry -------------------------------------------------------------------------------------

def _register_all():
    for what, selector in DISPATCHED:
        gemdos.register(f"gemdos_dispatch_selector, {what}", gemdos.TRAMPOLINE_AT, {"a5": 0},
                        gemdos.slice_pokes(selector, pokes=gemdos.dta_poke(A_DTA)))
    gemdos.register("gemdos_dispatch, a selector past the table", addrs.GEMDOS_DISPATCH,
                    {"a5": 0}, gemdos.dispatch_pokes(PAST_THE_TABLE))


_register_all()
