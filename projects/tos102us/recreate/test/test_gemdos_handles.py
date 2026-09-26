"""GEMDOS's HANDLE machinery — `src/gemdos/handles.c`, and what a handle really is.

    $fc52de  Fforce ($46)   move.l  p_run,(sp) / bsr $fc52f8
    $fc52f8                 cmp.w   #6,d5 / blt              ; the standard handle, 0..5
    $fc531c                 tst.w   d6 / bge                 ; a NEGATIVE handle is a DEVICE
    $fc5348                 move.l  (a0),d7 / bge            ; ...and so is a descriptor's own value
    $fc538a                 addq.w  #1,8(a1)                 ; only a FILE takes a reference
    $fc5216  Fdup ($45)     tst.l   4(a0,a1.l) / beq         ; the first descriptor nobody owns
    $fc56c6  Fclose ($3e)   subq.w  #1,8(a0) / bne           ; ...and the last holder lets it go
    $fc9924  the dispatcher  cmpi.w #129,-28(a6)             ; WHICH argument word holds the handle

THE ONE FACT THIS BATTERY EXISTS TO PIN is that a handle is three different things spelt as one
signed word, and every routine here branches on which: NEGATIVE is a character device, 0..5 is an
index into the running process's own `p_uft`, and 6 and up is an open file descriptor whose own
first longword is then a device or a file. Three kinds, two levels, and the sign decides at both.

WHAT IS PROVED AGAINST WHAT. `Fforce` and `Fdup` are ordinary leaves and are whole-function
differentials. `Fclose` is one here on its three DEVICE arms; its open-FILE arm closes through the
file system's own `$fc57ee` and needs a staged disk, so it is `test_gemdos_fs_close.py`'s. The dispatcher's
RESOLUTION is not a routine at all, so it is driven as a SLICE of `gemdos_dispatch_selector`
(`test/gemdos.py`), on the only three selectors whose descriptor has bit 7: `Fread`, `Fwrite` and
`Fseek`.
"""
import ctypes

import pytest

from harness import _lib, addrs, emu, make_image

import case
import gemdos
import gemdos_memory
import gemdos_process as process

for _name in ("gemdos_fforce", "gemdos_force_handle", "gemdos_fdup", "gemdos_fclose",
              "gemdos_dispatch_selector"):
    getattr(_lib, _name).restype = ctypes.c_uint32

P_RUN = gemdos.BASEPAGE

# A handle in the middle of the table and one at its end, so every claim below is made twice at
# addresses the arithmetic reaches differently.
A_FILE_HANDLE = 6
ANOTHER_FILE_HANDLE = 20
# ...and what a descriptor may NAME: a console device, and a longword standing in for whatever the
# file system puts there. Only its sign is read by anything in this file.
A_DEVICE = -1
ANOTHER_DEVICE = -3
A_FILE = 0x0001_2340

# Every standard handle the ROM's own bound admits, and the words just outside it.
STANDARD_HANDLES = (0, 1, 2, 3, 4, 5)
OUTSIDE_THE_BOUND = (-1, -2, 6, 7, 0x7FFF)

EIHNDL = addrs.GEMDOS_EIHNDL        # -37, as the whole D0 a `moveq` sign-extends into
ENHNDL = process.GEMDOS_ENHNDL      # ...and -35, the one answer in this group that is not it


def run_leaf(entry, glue, pokes):
    return process.run(entry, glue, pokes)


def no_store(info):
    """Nothing at all was written outside the run's own stack frame."""
    assert not gemdos_memory.stores(info), (
        f"the refused call still stored {sorted(hex(a) for a in gemdos_memory.stores(info))}")


# ================================================================================================
# Fforce ($46) and the body it shares with Pexec
# ================================================================================================

@pytest.mark.parametrize("standard", OUTSIDE_THE_BOUND)
def test_fforce_refuses_a_standard_handle_outside_the_six(standard):
    """`tst.w / bmi` then `cmp.w #6 / blt`: the bound is SIGNED and both ends of it are real. A word
    above 5 and a negative word are the same answer, and neither stores anything."""
    info = run_leaf(addrs.GEMDOS_FFORCE,
                    lambda lib, buf: lib.gemdos_fforce(buf, standard, A_DEVICE),
                    case.word_args(standard & 0xFFFF, A_DEVICE & 0xFFFF))
    assert info["regs"]["d0"] == EIHNDL
    no_store(info)


@pytest.mark.parametrize("standard", STANDARD_HANDLES)
@pytest.mark.parametrize("device", (A_DEVICE, ANOTHER_DEVICE, -0x80))
def test_fforce_stores_a_device_as_the_byte_it_is(standard, device):
    """A NEGATIVE handle is a character device and there is nothing to look up: the low byte goes
    straight into `p_uft[standard]`. Driven at every one of the six slots, so the displacement is a
    claim, and at three devices including the most negative byte there is."""
    info = run_leaf(addrs.GEMDOS_FFORCE,
                    lambda lib, buf: lib.gemdos_fforce(buf, standard, device),
                    gemdos.standard_handles_poke([0] * addrs.BASEPAGE_STANDARD_HANDLES)
                    | case.word_args(standard, device & 0xFFFF))
    assert info["regs"]["d0"] == 0
    assert case.written(info, P_RUN + addrs.BASEPAGE_HANDLES + standard, 1) == (device & 0xFF)


@pytest.mark.parametrize("source", STANDARD_HANDLES)
def test_fforce_refuses_a_source_that_is_itself_a_standard_handle(source):
    """`cmp.w #6 / bge` on the handle being written: 0..5 is EIHNDL rather than an alias, which is
    what stops `Fforce(1, 0)` making stdout follow stdin."""
    info = run_leaf(addrs.GEMDOS_FFORCE,
                    lambda lib, buf: lib.gemdos_fforce(buf, 0, source),
                    case.word_args(0, source))
    assert info["regs"]["d0"] == EIHNDL
    no_store(info)


@pytest.mark.parametrize("handle", (A_FILE_HANDLE, ANOTHER_FILE_HANDLE))
def test_fforce_of_a_descriptor_that_names_a_device_stores_the_device_and_counts_nothing(handle):
    """THE ARM THAT MAKES THE DESCRIPTOR'S SIGN LOAD-BEARING. `Fdup(0)` on a console handle leaves a
    descriptor whose value is -1; forcing THAT back onto a standard handle stores -1 — not the
    handle — and takes no reference, because there is nothing to hold.

    The pair with the case below is the whole claim: same call, same arithmetic, two different
    stores decided by one `bge`.
    """
    pokes = process.descriptor_poke(handle, ANOTHER_DEVICE, P_RUN, references=4) \
        | gemdos.standard_handles_poke([0] * addrs.BASEPAGE_STANDARD_HANDLES) \
        | case.word_args(1, handle)
    info = run_leaf(addrs.GEMDOS_FFORCE, lambda lib, buf: lib.gemdos_fforce(buf, 1, handle), pokes)
    assert info["regs"]["d0"] == 0
    assert case.written(info, P_RUN + addrs.BASEPAGE_HANDLES + 1, 1) == (ANOTHER_DEVICE & 0xFF)
    final = process.descriptor(case.final_image(info, pokes), handle)
    assert final.references == 4, "a descriptor naming a device must not be counted"


@pytest.mark.parametrize("handle", (A_FILE_HANDLE, ANOTHER_FILE_HANDLE))
@pytest.mark.parametrize("references", (1, 7))
def test_fforce_of_a_descriptor_that_names_a_file_counts_the_new_holder(handle, references):
    """...and the other side of that `bge`: the HANDLE NUMBER is stored and the descriptor's
    reference count goes up by one, so a later `Fclose` of either holder does not release it."""
    pokes = process.descriptor_poke(handle, A_FILE, P_RUN, references=references) \
        | gemdos.standard_handles_poke([0] * addrs.BASEPAGE_STANDARD_HANDLES) \
        | case.word_args(2, handle)
    info = run_leaf(addrs.GEMDOS_FFORCE, lambda lib, buf: lib.gemdos_fforce(buf, 2, handle), pokes)
    assert info["regs"]["d0"] == 0
    assert case.written(info, P_RUN + addrs.BASEPAGE_HANDLES + 2, 1) == handle
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_REFCOUNT, 2) \
        == references + 1


def test_force_handle_writes_the_basepage_it_is_given_and_not_p_run():
    """$fc52f8 takes the basepage as its THIRD argument, which is the whole reason `Fforce` is four
    instructions and this is the body: `Pexec` calls it to fill a CHILD's handle table while `p_run`
    is still the parent's. A case that could not tell the two apart would not be about the argument.
    """
    child = process.stage_child()
    pokes = child.pokes | case.args(">HHI", 3, A_DEVICE & 0xFFFF, child.basepage)
    info = run_leaf(addrs.GEMDOS_FORCE_HANDLE,
                    lambda lib, buf: lib.gemdos_force_handle(buf, 3, A_DEVICE, child.basepage),
                    pokes)
    assert info["regs"]["d0"] == 0
    assert case.written(info, child.basepage + addrs.BASEPAGE_HANDLES + 3, 1) == (A_DEVICE & 0xFF)
    assert P_RUN + addrs.BASEPAGE_HANDLES + 3 not in info["writes"], (
        "the running process's own handle table was written")


# ================================================================================================
# Fdup ($45)
# ================================================================================================

@pytest.mark.parametrize("standard", OUTSIDE_THE_BOUND)
def test_fdup_refuses_a_standard_handle_outside_the_six(standard):
    info = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, standard),
                    case.word_arg(standard & 0xFFFF))
    assert info["regs"]["d0"] == EIHNDL
    no_store(info)


@pytest.mark.parametrize("taken", (0, 1, 3, 74))
def test_fdup_takes_the_first_descriptor_nobody_owns(taken):
    """The search is for a free OWNER longword, not a free value — which is the field `Fclose` and a
    process's release both zero. Driven with the first `taken` slots claimed, so the answer is
    `taken + 6` and the arithmetic that turns a slot into a handle is a claim at four values."""
    owned = {}
    for slot in range(taken):
        owned |= process.descriptor_poke(slot + addrs.GEMDOS_FIRST_FILE_HANDLE, A_FILE, P_RUN)
    pokes = owned | gemdos.standard_handles_poke([A_DEVICE]) | case.word_arg(0)
    info = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, 0), pokes)

    handle = taken + addrs.GEMDOS_FIRST_FILE_HANDLE
    assert info["regs"]["d0"] == handle
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_OWNER, 4) == P_RUN
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_VALUE, 4) \
        == (A_DEVICE & 0xFFFF_FFFF)
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_REFCOUNT, 2) == 1


def test_fdup_answers_enhndl_when_every_descriptor_is_owned():
    """The ONE error in this group that is not EIHNDL: -35, and the search has walked all 75."""
    pokes = process.full_table_poke(P_RUN) | gemdos.standard_handles_poke([A_DEVICE]) \
        | case.word_arg(0)
    info = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, 0), pokes)
    assert info["regs"]["d0"] == ENHNDL
    no_store(info)


def test_fdup_of_a_file_copies_the_value_and_starts_ITS_OWN_count_at_one():
    """A DUPLICATE AND NOT A REFERENCE, which is TOS 1.02's own defect reproduced rather than
    corrected: the new descriptor copies what the old one names but starts at one holder however
    many the old one had, so closing both halves closes the file twice."""
    source = ANOTHER_FILE_HANDLE
    pokes = process.descriptor_poke(source, A_FILE, P_RUN, references=5) \
        | gemdos.standard_handles_poke([source]) | case.word_arg(0)
    info = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, 0), pokes)

    assert info["regs"]["d0"] == addrs.GEMDOS_FIRST_FILE_HANDLE
    made = process.descriptor_at(addrs.GEMDOS_FIRST_FILE_HANDLE)
    assert case.written(info, made + process.HANDLE_VALUE, 4) == A_FILE
    assert case.written(info, made + process.HANDLE_REFCOUNT, 2) == 1
    assert process.descriptor_at(source) + process.HANDLE_REFCOUNT not in info["writes"], (
        "the source descriptor's count moved — this is a copy, not a reference")


def test_fdup_of_an_unused_slot_takes_the_device_arm_and_names_zero():
    """`ble`, not `blt`: a `p_uft` byte of 0 — an unused slot — takes the same arm a device does, and
    the new descriptor is left naming 0. The dispatcher's resolution answers EIHNDL for exactly that,
    which is the pair `test_a_handle_that_names_nothing_is_eihndl` below makes."""
    pokes = gemdos.standard_handles_poke([0, 0, 0, 0, 0, 0]) | case.word_arg(4)
    info = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, 4), pokes)
    made = process.descriptor_at(addrs.GEMDOS_FIRST_FILE_HANDLE)
    assert info["regs"]["d0"] == addrs.GEMDOS_FIRST_FILE_HANDLE
    assert case.written(info, made + process.HANDLE_VALUE, 4) == 0


# ================================================================================================
# Fclose ($3e)
# ================================================================================================

@pytest.mark.parametrize("handle", (-1, -3, -0x8000))
def test_fclose_of_a_device_handle_does_nothing_at_all(handle):
    """`tst.w / bge`: a negative handle names a device, there is nothing to close, and D0 is 0 —
    which is `clr.l`, so the caller's high half goes too."""
    info = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, handle),
                    case.word_arg(handle & 0xFFFF))
    assert info["regs"]["d0"] == 0
    no_store(info)


@pytest.mark.parametrize("standard", STANDARD_HANDLES)
def test_fclose_of_a_standard_handle_naming_a_device_clears_the_slot(standard):
    """The slot is cleared BEFORE the ROM knows what was in it (`clr.b` then `tst.w`), and a slot
    that held a device is the whole of the work. Zero is what an unused slot holds, so this is also
    what makes a closed standard handle indistinguishable from one never opened."""
    pokes = gemdos.standard_handles_poke([ANOTHER_DEVICE] * addrs.BASEPAGE_STANDARD_HANDLES) \
        | case.word_arg(standard)
    info = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, standard), pokes)
    assert info["regs"]["d0"] == 0
    assert case.written(info, P_RUN + addrs.BASEPAGE_HANDLES + standard, 1) == 0
    assert len(gemdos_memory.stores(info)) == 1, "one byte, and the descriptors left alone"


@pytest.mark.parametrize("handle", (A_FILE_HANDLE, ANOTHER_FILE_HANDLE))
@pytest.mark.parametrize("references", (2, 9))
def test_fclose_of_a_shared_descriptor_only_drops_the_count(handle, references):
    """A descriptor naming a device with more than one holder: the count goes down and NOTHING else
    moves — the value and the owner stay, so the slot is still not `Fdup`'s to take."""
    pokes = process.descriptor_poke(handle, A_DEVICE, P_RUN, references=references) \
        | case.word_arg(handle)
    info = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, handle), pokes)
    assert info["regs"]["d0"] == 0
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_REFCOUNT, 2) \
        == references - 1
    assert len(gemdos_memory.stores(info)) == 2, "the count, and only the count"


@pytest.mark.parametrize("handle", (A_FILE_HANDLE, ANOTHER_FILE_HANDLE))
def test_fclose_of_the_last_holder_gives_the_descriptor_back(handle):
    """...and the last one: the count reaches zero and the value and the OWNER are cleared, which is
    exactly what puts the slot back in `Fdup`'s search."""
    pokes = process.descriptor_poke(handle, A_DEVICE, P_RUN, references=1) | case.word_arg(handle)
    info = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, handle), pokes)
    at = process.descriptor_at(handle)
    assert info["regs"]["d0"] == 0
    assert case.written(info, at + process.HANDLE_REFCOUNT, 2) == 0
    assert case.written(info, at + process.HANDLE_VALUE, 4) == 0
    assert case.written(info, at + process.HANDLE_OWNER, 4) == 0



@pytest.mark.parametrize("handle", (A_FILE_HANDLE, ANOTHER_FILE_HANDLE))
def test_fclose_of_a_descriptor_that_names_nothing_is_eihndl(handle):
    """THE ARM BOTH `bge`s FALL INTO, and it has two outcomes rather than one. A descriptor whose
    value is not negative is looked up ONE MORE TIME ($fc51c0) and branched on: 0 is a handle that
    names nothing and answers EIHNDL with NOTHING stored, and only a positive value is the open
    FILE whose close ($fc57ee) `test_gemdos_fs_close.py` drives over a staged disk.

    The state is one `Fdup` really makes. `Fdup(4)` on the captured machine — whose `p_uft[4]` is 0,
    an unused slot — takes the `ble` arm and leaves the new descriptor naming 0; closing it is this.
    """
    pokes = process.descriptor_poke(handle, 0, P_RUN) | case.word_arg(handle)
    info = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, handle), pokes)
    assert info["regs"]["d0"] == EIHNDL
    no_store(info)


def test_fdup_of_an_unused_slot_makes_a_descriptor_fclose_answers_eihndl_for():
    """...and the pair, end to end: `Fdup` of a standard handle holding 0, then `Fclose` of what it
    answered. Two runs rather than one claim, because it is the SECOND that reaches the lookup."""
    standard, pokes = 4, gemdos.standard_handles_poke([0] * addrs.BASEPAGE_STANDARD_HANDLES)
    duplicated = run_leaf(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, standard),
                          pokes | case.word_arg(standard))
    handle = duplicated["regs"]["d0"]
    assert handle == A_FILE_HANDLE, "the first free descriptor is the one `Fclose` is asked for"

    closed = run_leaf(addrs.GEMDOS_FCLOSE, lambda lib, buf: lib.gemdos_fclose(buf, handle),
                      process.descriptor_poke(handle, 0, P_RUN) | case.word_arg(handle))
    assert closed["regs"]["d0"] == EIHNDL


# ================================================================================================
# The dispatcher's own resolution ($fc9924), as a slice
# ================================================================================================

# The only three selectors whose descriptor has bit 7 set once the character-device group has had
# its own rewritten — read out of the ROM's table rather than written down.
FREAD, FWRITE, FSEEK = addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FWRITE_FN, addrs.GEMDOS_FSEEK_FN


def test_exactly_three_selectors_reach_the_resolution_arm():
    """Everything else with bit 7 set is a character-device call, whose descriptor the dispatcher
    has rewritten to 0 or 1 by the time the `btst #7` runs. So the arm's whole input set is these
    three, and one of them — `Fseek` — is the $81 that puts its handle in the third word."""
    handled = [selector for selector in range(addrs.GEMDOS_FUNCTION_COUNT)
               if gemdos.rom_descriptor(selector) & addrs.GEMDOS_DESC_HANDLE
               and not (1 <= selector <= addrs.GEMDOS_REDIRECT_LAST)
               and not (addrs.GEMDOS_REDIRECT_SECOND_FIRST <= selector
                        <= addrs.GEMDOS_REDIRECT_SECOND_LAST)]
    assert handled == [FREAD, FWRITE, FSEEK]
    assert gemdos.rom_descriptor(FSEEK) == addrs.GEMDOS_DESC_HANDLE_AT_THIRD_WORD
    assert gemdos.rom_descriptor(FREAD) == gemdos.rom_descriptor(FWRITE) != \
        addrs.GEMDOS_DESC_HANDLE_AT_THIRD_WORD


@pytest.mark.parametrize("selector", (FREAD, FWRITE))
@pytest.mark.parametrize("what,handle,pokes", (
    ("a descriptor that names nothing", A_FILE_HANDLE,
     process.descriptor_poke(A_FILE_HANDLE, 0, P_RUN)),
    ("a standard handle that names nothing", 4, gemdos.standard_handles_poke([0] * 6)),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_a_handle_that_names_nothing_is_eihndl(selector, what, handle, pokes):
    """`tst.l / beq` on the RESOLVED longword, which is the one place a handle is refused after the
    walk rather than before it. Both ways of reaching a zero: a descriptor holding one, and a
    standard handle whose `p_uft` byte is the 0 an unused slot holds.

    The call is refused before any handler is reached, which is what `bound_handlers({})` makes a
    claim rather than an accident.
    """
    info = gemdos.run_slice(selector, (handle, 0, 0, 0, 0, 0), pokes)
    assert info["regs"]["d0"] == EIHNDL
    assert not gemdos.HANDLER_CALLS, "a refused handle still reached a handler"


def test_fseek_takes_its_handle_from_the_THIRD_word():
    """$81 is `Fseek`, whose first argument is a longword offset — so its handle is the third word
    and not the first. Staged with a PERFECTLY GOOD handle in the first word and a dead one in the
    third: a reconstruction reading the wrong word would resolve the good one and never answer."""
    pokes = process.descriptor_poke(A_FILE_HANDLE, A_FILE, P_RUN) \
        | process.descriptor_poke(ANOTHER_FILE_HANDLE, 0, P_RUN)
    info = gemdos.run_slice(FSEEK, (0, A_FILE_HANDLE, ANOTHER_FILE_HANDLE, 0, 0, 0), pokes)
    assert info["regs"]["d0"] == EIHNDL
    assert not gemdos.HANDLER_CALLS


@pytest.mark.parametrize("what,handle,pokes,reaches", (
    ("a descriptor naming a device", A_FILE_HANDLE,
     process.descriptor_poke(A_FILE_HANDLE, A_DEVICE, P_RUN), 0xFC99BC),
    ("a standard handle naming a device", 0,
     gemdos.standard_handles_poke([A_DEVICE] * 6), 0xFC99BC),
    ("a descriptor naming a file", A_FILE_HANDLE,
     process.descriptor_poke(A_FILE_HANDLE, A_FILE, P_RUN), 0xFC9AC6),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_where_a_resolved_handle_sends_the_ORIGINAL(what, handle, pokes, reaches):
    """A claim about the ORACLE, because neither arm is a differential this wave can make: a DEVICE
    routes into the console leaves under an `Fread` that does not exist, and a FILE falls through to
    the ordinary dispatch and the file system's own handler.

    What the case can say is WHICH of the two the walk reached, and it says it at the instruction —
    `$fc99bc` is the device routing and `$fc9ac6` the ordinary dispatch. That is what makes the
    reconstruction's halt (`src/gemdos/dispatch.c`) a halt on the right arm.
    """
    staged = gemdos.slice_pokes(FREAD, (handle, 0, 0, 0, 0, 0), pokes)
    _final, _writes, regs = emu.run(make_image(staged), gemdos.TRAMPOLINE_AT,
                                    {"a5": 0}, stop_pc=reaches)
    assert regs["ninsns"] > 0, f"the ORIGINAL never reached {reaches:#x}"


A_HANDLER_RESULT = 0x0BAD_F00D          # what the bound stand-in answers, and nothing else does


def test_a_handle_that_names_a_file_falls_through_to_the_ordinary_dispatch():
    """THE THIRD OUTCOME, on the CANDIDATE's side: a resolved longword that is neither 0 nor
    negative is the file system's own pointer, and the dispatcher does nothing about it — it falls
    through to the ordinary dispatch and calls the handler with the frame the descriptor asks for
    (`bge $fc9ac6`).

    NO ORACLE, and this is the one case in the file that has none. The ROM's own `Fread` handler
    would run on the other shore and it is the file system's, so there is no second column to
    compare — the ORIGINAL's half of this claim is the case above, which stops it at `$fc9ac6`. What
    is pinned here is that our dispatcher reaches the call at all, with the right handler and the
    right frame: a reconstruction that answered EIHNDL for every non-negative resolution would pass
    every other case in this section.
    """
    handler = gemdos.rom_handler(FREAD)
    pokes = gemdos.slice_pokes(FREAD, (A_FILE_HANDLE, 0, 0, 0, 0, 0),
                               process.descriptor_poke(A_FILE_HANDLE, A_FILE, P_RUN))
    returned, _image = gemdos.run_candidate_only(
        lambda lib, buf: lib.gemdos_dispatch_selector(buf, gemdos.ARGUMENTS_AT), pokes,
        handlers={handler: lambda buf, args, width: A_HANDLER_RESULT})

    assert gemdos.HANDLER_CALLS == [(handler, gemdos.ARGUMENTS_AT + addrs.GEMDOS_ARGUMENT_WORD,
                                     addrs.GEMDOS_ARGUMENT_BYTES_2)], (
        "the resolved FILE did not reach the handler with `Fread`'s own argument frame")
    assert returned == A_HANDLER_RESULT, "the dispatcher did not answer what the handler left"


# ---- the registry ----------------------------------------------------------------------------------
# One row per routine, built from the same constructors the cases above drive. The dispatcher's
# RESOLUTION has no row of its own: it is an arm of `gemdos_dispatch_selector`, which
# `test_gemdos_dispatch.py` already prices, and the slice case below would be a second row for one
# routine.

def _register_all():
    gemdos.register("gemdos_fforce, a device", addrs.GEMDOS_FFORCE, {"a5": 0},
                    gemdos.standard_handles_poke([0] * addrs.BASEPAGE_STANDARD_HANDLES)
                    | case.word_args(1, A_DEVICE & 0xFFFF))
    gemdos.register("gemdos_force_handle, into another basepage", addrs.GEMDOS_FORCE_HANDLE,
                    {"a5": 0}, _force_handle_pokes())
    gemdos.register("gemdos_fdup, the first free descriptor", addrs.GEMDOS_FDUP, {"a5": 0},
                    gemdos.standard_handles_poke([A_DEVICE]) | case.word_arg(0))
    gemdos.register("gemdos_fclose, the last holder of a descriptor", addrs.GEMDOS_FCLOSE,
                    {"a5": 0},
                    process.descriptor_poke(A_FILE_HANDLE, A_DEVICE, P_RUN, references=1)
                    | case.word_arg(A_FILE_HANDLE))


def _force_handle_pokes():
    child = process.stage_child()
    return {**child.pokes, **case.args(">HHI", 3, A_DEVICE & 0xFFFF, child.basepage)}


_register_all()
