"""STARTING A PROCESS — `Pexec` ($fc817a, GEMDOS $4b). `src/gemdos/process.c`.

    $fc817e  tst.w 8(a6) / cmpi.w #3 / cmpi.w #5      ; 0, 3, 4 and 5 — and they are not a range
    $fc81d2  jsr   $fc564a                            ; the dispatcher's record, saved at $7560
    $fc81e0  jsr   $fc4f38                            ; ...and one of Pexec's OWN armed at $7ef4
    $fc8242  cmpi.w #4,8(a6)                          ; MODE 4 has a basepage already
    $fc82ae  bsr   $fc886a                            ; the environment, cut and copied
    $fc82f6  bsr   $fc886a / cmpi.l #256              ; ...and the TPA, out of the LARGEST free block
    $fc84d0  bsr   $fc85ea                            ; the loader, for modes 0 and 3
    $fc85c8  jsr   $fc4fe8                            ; and modes 0 and 4 GO. Control does not return.

FOUR MODES AND TWO CASE SHAPES. `gemdos_pexec` itself is a whole-function differential on the arm
that returns before the record it arms — the refused mode — and everything past that record is
`gemdos_pexec_create` ($fc8242), entered as a SLICE, exactly as the dispatcher's own arms are
(`src/gemdos/dispatch.c` carries the argument; the record is the 68000 frame of the `jsr` that armed
it and a C core has no counterpart for it).

WHAT IS HERE IS MODES 4 AND 5, which is the whole of what `Pexec` does that is not the file system:
cut a TPA and an environment, fill a basepage, inherit the parent's handles and directories, copy the
command tail (mode 5) and build the child's initial stack and go (mode 4). Modes 0 and 3 LOAD a program
off the staged disk, and are `test_gemdos_process_pexec_load.py`'s.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import case
import gemdos
import gemdos_memory
import gemdos_process as process

for _name in ("gemdos_pexec", "gemdos_pexec_create", "gemdos_inherit_curdir"):
    getattr(_lib, _name).restype = ctypes.c_uint32
_lib.gemdos_inherit_curdir.restype = None

P_RUN = gemdos.BASEPAGE
A_FILE = 0x0001_2340
A_FILE_HANDLE = 6

AN_ENVIRONMENT = b"PATH=A:\\\0TOSTEST=1\0\0"          # 19 bytes: an ODD length, so the rounding shows
AN_EVEN_ENVIRONMENT = b"PATH=A:\0\0"                  # ...and 9, which rounds the other way
AN_EMPTY_ENVIRONMENT = b"\0\0"
A_COMMAND_TAIL = bytes([5]) + b"HELLO"

# Every word the two compares refuse, including both ends of the gap they leave.
REFUSED_MODES = (1, 2, 6, 7, 0xFFFF, 0x7FFF, 0x8000)

# What the oracle's own reset charges before any entry, which every cost here is net of — the same
# pair `test_gemdos_dispatch.py` nets its trampoline by.
RESET_INSNS, RESET_CYCLES = 1, 40


def pexec_pokes(mode, tail=A_COMMAND_TAIL, environment=AN_ENVIRONMENT, env_at=None, pokes=None):
    """A `Pexec` case: the slice trampoline, the two blocks the call points at, and its frame."""
    env_at = process.ENVIRONMENT_AT if env_at is None else env_at
    return {**gemdos.machine(), **process.slice_trampoline(),
            process.ENVIRONMENT_AT: environment,
            process.COMMAND_TAIL_AT: tail + b"\0",
            **process.pexec_args(mode, 0, process.COMMAND_TAIL_AT, env_at),
            **(pokes or {})}


# ================================================================================================
# The mode bound — the one arm of $fc817a a whole-function differential can reach
# ================================================================================================

@pytest.mark.parametrize("mode", REFUSED_MODES)
def test_a_mode_outside_the_four_is_einvfn(mode):
    """`tst.w / beq` then `cmpi.w #3 / blt` and `cmpi.w #5 / ble`: 0 is admitted on its own and 3..5
    as a range, so 1 and 2 are a GAP rather than the bottom of one. Both ends of it are driven, and
    so is every word above 5 including the two that straddle the sign.

    This is the only arm of `$fc817a` a differential reaches: everything past it has armed a
    termination record this reconstruction does not have.
    """
    pokes = pexec_pokes(mode)
    info = process.run(addrs.GEMDOS_PEXEC,
                       lambda lib, buf: lib.gemdos_pexec(buf, mode, 0, process.COMMAND_TAIL_AT,
                                                         process.ENVIRONMENT_AT),
                       pokes)
    assert info["regs"]["d0"] == addrs.GEMDOS_EINVFN
    assert not gemdos_memory.stores(info), "a refused mode still wrote something"


def test_pexec_saves_the_dispatcher_s_own_termination_record_before_it_arms_one():
    """A claim about the ORACLE, because the arming between it and the first reconstructed arm is
    the hole `test_gemdos_dispatch.py` measures: `Pexec` copies the twelve bytes at `$7ef4` to
    `$7560` so that its own error path can longjmp back OUT to the dispatcher's.

    Stopped at the `jsr $fc4f38` that arms the new one, so what the case reads at `$7560` is the
    copy and nothing else.
    """
    pokes = pexec_pokes(process.PEXEC_CREATE_BASEPAGE)
    final, writes, regs = emu.run(make_image(pokes), addrs.GEMDOS_PEXEC, {"a5": 0},
                                  stop_pc=0xFC81E0)
    assert regs["ninsns"] > 0
    saved = bytes(final[process.PEXEC_OUTER_JMPBUF:
                        process.PEXEC_OUTER_JMPBUF + process.JMPBUF_BYTES])
    assert saved == bytes(BASE_IMAGE[addrs.GEMDOS_TERMINATION_JMPBUF:
                                     addrs.GEMDOS_TERMINATION_JMPBUF + process.JMPBUF_BYTES])
    assert process.PEXEC_OUTER_JMPBUF in writes, "the record was not copied at all"


# A termination record no boot could have left, and a fill for the slot it is copied INTO. Both are
# staged, and that is the whole reason the case below is a case: the captured machine's `$7560`
# ALREADY holds a byte-for-byte copy of its `$7ef4` — the desktop's own last GEMDOS call left the
# pair that way — so a run that copied nothing at all reads exactly like one that copied correctly.
# (Measured: deleting the copy loop left this case green until these two pokes were added.)
A_STAGED_JMPBUF = bytes.fromhex("0001babe0002cafe00fc1234")
OUTER_JMPBUF_FILL = b"\xA5" * 12


def test_our_pexec_copies_that_record_too():
    """...and the CANDIDATE's half of it, which nothing had. The case above is the ORACLE stopped at
    the arming; this one runs our `gemdos_pexec` over the same staged machine and reads the same
    twelve bytes, because the two halves together are what "reproduced rather than omitted" means
    here — the copy is reconstructed (`src/gemdos/process.c`), only the ARMING is not.

    No oracle, for the arming's own reason: the ROM would arm a record two instructions later and a
    whole-function differential across it is the hole `test_gemdos_dispatch.py` measures.
    """
    pokes = {**pexec_pokes(process.PEXEC_CREATE_BASEPAGE),
             addrs.GEMDOS_TERMINATION_JMPBUF: A_STAGED_JMPBUF,
             process.PEXEC_OUTER_JMPBUF: OUTER_JMPBUF_FILL}
    _returned, image = gemdos.run_candidate_only(
        lambda lib, buf: lib.gemdos_pexec(buf, process.PEXEC_CREATE_BASEPAGE, 0,
                                          process.COMMAND_TAIL_AT, process.ENVIRONMENT_AT),
        pokes)
    assert bytes(image[process.PEXEC_OUTER_JMPBUF:
                       process.PEXEC_OUTER_JMPBUF + process.JMPBUF_BYTES]) == A_STAGED_JMPBUF


# ================================================================================================
# Mode 5 — create a basepage
# ================================================================================================

def create(mode=process.PEXEC_CREATE_BASEPAGE, **kwargs):
    pokes = pexec_pokes(mode, **kwargs)
    info = process.run(process.SLICE_TRAMPOLINE_AT,
                       lambda lib, buf: lib.gemdos_pexec_create(
                           buf, mode, 0, process.COMMAND_TAIL_AT,
                           kwargs.get("env_at", process.ENVIRONMENT_AT)),
                       pokes)
    return info, pokes


def test_mode_5_cuts_a_tpa_out_of_the_largest_free_block_and_answers_its_basepage():
    """TWO ALLOCATOR CALLS, and the pair is the point: the first asks `Malloc(-1)` how big the
    largest free block is and the second asks for exactly that, so the TPA is the whole of what was
    left. The basepage IS the block's first bytes, and `p_lowtpa`/`p_hitpa` are the block."""
    info, pokes = create()
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]

    block = [md for md in gemdos_memory.allocated_list(final) if md.start == basepage]
    assert block, "the basepage is not the start of an allocated block"
    assert case.long_in(final, basepage + addrs.BASEPAGE_LOWTPA) == basepage
    assert case.long_in(final, basepage + addrs.BASEPAGE_HITPA) == basepage + block[0].length
    assert not gemdos_memory.free_list(final), "the TPA was not the whole of the largest block"


def test_the_basepage_is_cleared_from_its_TEXT_pointer_on_and_runs_past_its_own_end():
    """`clr.b` 256 times from `p_tbase` — which is +8, so the clear ends EIGHT BYTES PAST the
    basepage. Reproduced rather than tidied: the eight bytes past $ff are the first of the command
    tail's area, which the tail copy then writes over anyway.

    Driven over a TPA whose bytes were not already zero, which is what makes the clear visible.
    """
    dirt = bytes(range(0x40)) * 6
    info, pokes = create(pokes={gemdos_memory.SNAPSHOT_FREE_MD.start: dirt})
    staged, final = make_image(pokes), case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    overrun = basepage + addrs.BASEPAGE_COMMAND_TAIL * 2       # +$100, one byte past the basepage

    # The six segment longwords, which nothing writes after the clear — so they are the clear's own.
    assert not any(final[basepage + addrs.BASEPAGE_TBASE:basepage + addrs.BASEPAGE_DTA])
    # ...and both ends of the OVERRUN: eight bytes past $ff are cleared and the ninth is not.
    assert not any(final[overrun:overrun + addrs.BASEPAGE_TBASE])
    assert final[overrun + addrs.BASEPAGE_TBASE] == staged[overrun + addrs.BASEPAGE_TBASE] != 0, (
        "the clear ran further than the eight bytes past the basepage the ROM's own 256 reach")


def test_the_default_dta_and_the_environment_pointer_are_filled_after_the_clear():
    """Both are inside the span the clear just ran over, so the order is load-bearing: `p_dta` is
    the command-tail area at +$80 and `p_env` the block the environment was copied into."""
    info, pokes = create()
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    environment = case.long_in(final, basepage + addrs.BASEPAGE_ENV)

    assert case.long_in(final, basepage + addrs.BASEPAGE_DTA) \
        == basepage + addrs.BASEPAGE_COMMAND_TAIL
    assert [md for md in gemdos_memory.allocated_list(final) if md.start == environment], (
        "p_env does not name an allocated block")


@pytest.mark.parametrize("what,environment", (
    ("an odd length, which rounds up", AN_ENVIRONMENT),
    ("an even one, which does not", AN_EVEN_ENVIRONMENT),
    ("the empty environment, which is two NULs", AN_EMPTY_ENVIRONMENT),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_the_environment_is_measured_to_its_double_nul_and_copied_whole(what, environment):
    """The length walk counts every byte up to and including the pair of NULs that ends the block,
    then rounds UP TO A WORD (`btst #0` on the counter's low byte). What is copied is that many
    bytes, so an odd environment's copy runs one byte past its own end.

    Three lengths, because the rounding is the only thing that distinguishes them.
    """
    info, pokes = create(environment=environment)
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    at = case.long_in(final, basepage + addrs.BASEPAGE_ENV)
    length = len(environment) + (len(environment) & 1)

    assert bytes(final[at:at + len(environment)]) == environment
    block = [md for md in gemdos_memory.allocated_list(final) if md.start == at]
    assert block and block[0].length == length, (
        f"the environment block is {block[0].length if block else None:#x} bytes, not {length:#x}")


def test_an_environment_pointer_of_zero_takes_the_parent_s_own():
    """`tst.l 18(a6) / bne`: a null environment argument means "inherit", and what is inherited is
    `p_run`'s `p_env` — the pointer, which is then measured and copied like any other."""
    parent_environment = case.long_in(BASE_IMAGE, P_RUN + addrs.BASEPAGE_ENV)
    info, pokes = create(env_at=0)
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    at = case.long_in(final, basepage + addrs.BASEPAGE_ENV)

    assert at != parent_environment, "the child was given the parent's block rather than a copy"
    assert bytes(final[at:at + 2]) == bytes(BASE_IMAGE[parent_environment:parent_environment + 2])


@pytest.mark.parametrize("what,tail", (
    ("a short one", A_COMMAND_TAIL),
    ("an empty one", b""),
    ("exactly the maximum", bytes([process.PEXEC_COMMAND_TAIL_MAX - 1])
     + b"X" * (process.PEXEC_COMMAND_TAIL_MAX - 1)),
    ("one byte more than the maximum", bytes([process.PEXEC_COMMAND_TAIL_MAX])
     + b"X" * process.PEXEC_COMMAND_TAIL_MAX),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_the_command_tail_is_copied_up_to_125_bytes_and_terminated(what, tail):
    """`cmpi.w #125 / bge` OR the first NUL, whichever comes first, and then a NUL of its own. The
    first byte copied is the tail's LENGTH byte — an Atari command tail is a Pascal string and the
    loop does not know it, which is why a 125-byte tail loses its last character."""
    info, pokes = create(tail=tail)
    final = case.final_image(info, pokes)
    at = info["regs"]["d0"] + addrs.BASEPAGE_COMMAND_TAIL
    kept = tail[:process.PEXEC_COMMAND_TAIL_MAX]

    assert bytes(final[at:at + len(kept)]) == kept
    assert final[at + len(kept)] == 0, "the copied tail was not NUL-terminated"


@pytest.mark.parametrize("handles", ((-1, -1, -2, -3, 0, 0), (-3, -2, -1, 0, 0, -1)))
def test_the_parent_s_DEVICE_handles_are_copied_as_the_bytes_they_are(handles):
    """A handle that is not strictly positive has nothing to take a reference on, so it is copied
    straight — which is every handle a fresh process has."""
    info, pokes = create(pokes=gemdos.standard_handles_poke(handles))
    final = case.final_image(info, pokes)
    at = info["regs"]["d0"] + addrs.BASEPAGE_HANDLES
    assert list(final[at:at + addrs.BASEPAGE_STANDARD_HANDLES]) == [h & 0xFF for h in handles]


def test_a_parent_handle_that_names_a_file_is_FORCED_into_the_child_and_counted():
    """...and the other arm: a handle above 0 goes through `Fforce`'s own body ($fc52f8), so the
    open-file descriptor's reference count counts the child too. Without that, the parent's `Fclose`
    would close a file the child still holds."""
    handles = (-1, -1, -2, -3, A_FILE_HANDLE, 0)
    info, pokes = create(pokes={**gemdos.standard_handles_poke(handles),
                                **process.descriptor_poke(A_FILE_HANDLE, A_FILE, P_RUN)})
    final = case.final_image(info, pokes)
    at = info["regs"]["d0"] + addrs.BASEPAGE_HANDLES

    assert final[at + 4] == A_FILE_HANDLE
    assert process.descriptor(final, A_FILE_HANDLE).references == 2


def test_every_one_of_the_sixteen_directories_is_inherited_zero_or_not():
    """`$fc51de` for all sixteen entries, unconditionally — so the count of directory node 0 goes up
    by however many EMPTY slots the parent has, which on the captured machine is fifteen. That is
    the ROM's own shape and the release routine's third loop is its mirror image: THAT one skips a
    zero, so a process started by `Pexec` gives back fifteen references it was never charged for.
    """
    curdir = tuple(BASE_IMAGE[P_RUN + addrs.BASEPAGE_CURDIR + index]
                   for index in range(addrs.BASEPAGE_CURDIR_ENTRIES))
    info, pokes = create()
    final = case.final_image(info, pokes)
    at = info["regs"]["d0"] + addrs.BASEPAGE_CURDIR

    assert list(final[at:at + addrs.BASEPAGE_CURDIR_ENTRIES]) == list(curdir)
    for node in set(curdir):
        assert process.directory_refcount(final, node) \
            == (process.directory_refcount(BASE_IMAGE, node) + curdir.count(node)) & 0xFF


def test_the_current_drive_is_inherited_and_the_load_drive_is_not():
    """One byte copied ($fc846a) and its neighbour left in the clear's zeroes, which is what says
    the copy is `p_curdrv` and not `p_lddrv`."""
    info, pokes = create(pokes=gemdos.current_drive_poke(3))
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    assert final[basepage + addrs.BASEPAGE_CURDRV] == 3
    assert final[basepage + addrs.BASEPAGE_LDDRV] == 0


def test_mode_5_charges_both_blocks_to_the_CALLER():
    """A basepage the caller is going to be handed back belongs to the caller: `m_own` on both the
    environment and the TPA is `p_run`, so a `Pterm` of the PARENT releases them. Only a mode that
    RUNS the child charges them to the child ($fc8342, whose `mode == 4` half is dead code)."""
    info, pokes = create()
    final = case.final_image(info, pokes)
    basepage = info["regs"]["d0"]
    environment = case.long_in(final, basepage + addrs.BASEPAGE_ENV)

    for start in (basepage, environment):
        block = [md for md in gemdos_memory.allocated_list(final) if md.start == start]
        assert block and block[0].owner == P_RUN, f"the block at {start:#x} is charged elsewhere"


def test_no_descriptor_for_the_environment_is_ensmem():
    """The first of the two ways `Pexec` runs out. `gemdos_md_alloc` answers 0 when the RECORD POOL
    is spent — TOS 1.02's "out of memory descriptors" — and `Pexec` reports -39 over RAM that is
    plainly free, having stored nothing."""
    spent = gemdos_memory.stage(gemdos_memory.fill(), arena_words_left=0)
    info, pokes = create(pokes=spent.pokes)
    assert info["regs"]["d0"] == process.GEMDOS_ENSMEM


def test_a_largest_free_block_smaller_than_a_basepage_is_ensmem_and_gives_the_environment_back():
    """The second, and the one with an unwind: the TPA is refused BEFORE it is cut (`cmpi.l #256`),
    and the environment block already cut is inserted back into the free list — so the pool comes
    out of the refusal with the same number of free bytes it went in with."""
    tiny = process.BASEPAGE_BYTES - 2
    staged = gemdos_memory.stage(gemdos_memory.fill(
        (gemdos_memory.USED, gemdos_memory.SNAPSHOT_FREE_MD.length - tiny)))
    info, pokes = create(pokes=staged.pokes)
    final = case.final_image(info, pokes)

    assert info["regs"]["d0"] == process.GEMDOS_ENSMEM
    assert sum(md.length for md in gemdos_memory.free_list(final)) == tiny, (
        "the environment block was not given back")


# ================================================================================================
# Mode 4 — run a basepage somebody else filled
# ================================================================================================

def run_mode_4(basepage, pokes=None):
    """Mode 4's checkpoint, and it makes NO claim about D0 — which is the honest width here rather
    than a gap. The ROM loads its result at `$fc85ce`, one instruction PAST the `jsr` into the
    epilogue, so a mode-4 call never reaches it: what is in D0 at the checkpoint is the stack
    pointer the build left there, and a case that compared it would be comparing scratch."""
    staged = {**gemdos.machine(), **process.slice_trampoline(),
              **process.pexec_args(process.PEXEC_JUST_GO, 0, basepage, 0), **(pokes or {})}

    def go(lib, buf):
        lib.gemdos_pexec_create(buf, process.PEXEC_JUST_GO, 0, basepage, 0)

    return process.run(process.SLICE_TRAMPOLINE_AT, go, staged,
                       stop_pc=process.PEXEC_EPILOGUE_CALL, routines={},
                       io_seed=process.A_BATTERY_CLOCK, width=case.NO_RESULT), staged


A_TEXT_BASE = 0x1E400
A_DATA_BASE = 0x1E800
A_BSS_BASE = 0x1EC00


def a_loaded_child():
    """A basepage a loader has already filled: the TPA, the three segment bases, and nothing else.
    Mode 4's whole input, which is why it is the one mode that takes a basepage ARGUMENT.

    `p_run` is left as the SNAPSHOT has it — the desktop's own process — because mode 4's caller is
    the parent and the staged basepage is the child it is about to run. `stage_child` makes the
    child the running process, which is what the TERMINATORS need and the opposite of this.
    """
    child = process.stage_child()
    child = child._replace(pokes={key: value for key, value in child.pokes.items()
                                  if key != addrs.GEMDOS_P_RUN})
    filled = bytearray(make_image(child.pokes)[child.basepage:
                                               child.basepage + addrs.BASEPAGE_COMMAND_TAIL])
    struct.pack_into(">I", filled, addrs.BASEPAGE_TBASE, A_TEXT_BASE)
    struct.pack_into(">I", filled, addrs.BASEPAGE_DBASE, A_DATA_BASE)
    struct.pack_into(">I", filled, addrs.BASEPAGE_BBASE, A_BSS_BASE)
    return child._replace(pokes={**child.pokes, child.basepage: bytes(filled)})


def test_mode_4_makes_the_caller_the_parent_and_the_child_the_running_process():
    """It creates nothing: `$fc8248` branches past the whole of the basepage work, so the only
    memory mode 4 writes is the child's own — `p_parent`, the stack, and `p_run`."""
    child = a_loaded_child()
    info, pokes = run_mode_4(child.basepage, child.pokes)

    assert case.written(info, child.basepage + addrs.BASEPAGE_PARENT, 4) == P_RUN
    assert case.written(info, addrs.GEMDOS_P_RUN, 4) == child.basepage


def test_mode_4_builds_the_child_s_initial_stack_under_its_own_p_hitpa():
    """Thirteen longwords and a word, built DOWNWARDS from the top of the TPA: the basepage, a zero,
    ten more zeros, the entry point, a zero WORD, and the return address at `$755a`. That is what a
    program entered by `Pexec` finds, and `4(sp)` on entry is the first of the eleven zeros."""
    child = a_loaded_child()
    info, pokes = run_mode_4(child.basepage, child.pokes)
    final = case.final_image(info, pokes)
    top = child.basepage + child.tpa

    assert case.long_in(final, top - 4) == child.basepage
    assert all(case.long_in(final, top - 8 - 4 * step) == 0
               for step in range(process.PEXEC_STACK_ZERO_LONGS + 1))
    entry_at = process.child_entry_at(top)
    assert case.long_in(final, entry_at) == A_TEXT_BASE
    assert case.word_in(final, entry_at - 2) == 0
    assert case.long_in(final, entry_at - 6) == process.PEXEC_RETURN_ADDRESS


def test_mode_4_seeds_the_child_s_saved_registers_with_its_own_segment_bases():
    """The four save slots the trap entry's epilogue restores from: A6 and the frame pointer are the
    stack just built, A5 is `p_dbase` and A4 is `p_bbase` — which is the register contract every
    Atari `.PRG` of the period was linked against."""
    child = a_loaded_child()
    info, pokes = run_mode_4(child.basepage, child.pokes)
    final = case.final_image(info, pokes)
    stack = case.long_in(final, child.basepage + addrs.BASEPAGE_SAVED_FRAME)

    assert case.long_in(final, child.basepage + addrs.BASEPAGE_SAVED_A6) == stack
    assert case.long_in(final, child.basepage + addrs.BASEPAGE_SAVED_A5) == A_DATA_BASE
    assert case.long_in(final, child.basepage + addrs.BASEPAGE_SAVED_A4) == A_BSS_BASE


def test_mode_4_touches_no_allocator_at_all():
    """The claim that separates it from mode 5 on the same slice: not one descriptor moves, no list
    head is written, and the record arena's cursor is where it was."""
    child = a_loaded_child()
    info, pokes = run_mode_4(child.basepage, child.pokes)
    final = case.final_image(info, pokes)

    assert gemdos_memory.arena_used_words(final) == gemdos_memory.arena_used_words(
        make_image(child.pokes))
    assert [md.at for md in gemdos_memory.free_list(final)] \
        == [md.at for md in gemdos_memory.free_list(make_image(child.pokes))]


# ================================================================================================
# $fc51de — one inherited directory
# ================================================================================================

@pytest.mark.parametrize("entry", (0, 7, addrs.BASEPAGE_CURDIR_ENTRIES - 1))
@pytest.mark.parametrize("node", (0, 1, 2, 0x7F))
def test_inherit_curdir_stores_the_byte_and_bumps_the_node_s_count(entry, node):
    """Two stores and the second one is what makes the first safe: the child's `p_curdir[entry]`
    gets the byte, and the shared count for that node goes up so the parent's own release cannot
    take the directory away while the child still names it.

    Driven at both ends of the sixteen slots, and at a node the captured machine does not use — the
    count is a byte and `addq.b` on 0 is 1 whatever the table held.
    """
    child = process.stage_child()
    pokes = {**child.pokes, **case.args(">HHI", entry, node, child.basepage)}
    info = process.run(addrs.GEMDOS_INHERIT_CURDIR,
                       lambda lib, buf: lib.gemdos_inherit_curdir(buf, entry, node,
                                                                  child.basepage),
                       pokes, width=case.NO_RESULT)

    assert case.written(info, child.basepage + addrs.BASEPAGE_CURDIR + entry, 1) == node
    assert case.written(info, addrs.GEMDOS_CURDIR_REFCOUNTS + node, 1) \
        == (BASE_IMAGE[addrs.GEMDOS_CURDIR_REFCOUNTS + node] + 1) & 0xFF


def test_the_slice_trampoline_costs_what_its_rows_are_net_of():
    """`link a6,#-48` and `jmp <long>.l`, measured rather than read off the 68000's tables — the two
    instructions the ORIGINAL's column is charged for and the candidate never runs."""
    _final, _writes, regs = emu.run(make_image(process.slice_trampoline()),
                                    process.SLICE_TRAMPOLINE_AT, {"a5": 0},
                                    stop_pc=addrs.GEMDOS_PEXEC_CREATE)
    assert (regs["ninsns"] - RESET_INSNS, regs["cycles"] - RESET_CYCLES) \
        == process.SLICE_ENTRY_COST


# ---- the registry --------------------------------------------------------------------------------

def _register_all():
    pokes = pexec_pokes(process.PEXEC_CREATE_BASEPAGE)
    child = a_loaded_child()

    gemdos.register("gemdos_pexec, a refused mode", addrs.GEMDOS_PEXEC, {"a5": 0},
                    pexec_pokes(1))
    gemdos.register("gemdos_pexec_create, mode 5", process.SLICE_TRAMPOLINE_AT, {"a5": 0}, pokes)
    gemdos.register("gemdos_inherit_curdir", addrs.GEMDOS_INHERIT_CURDIR, {"a5": 0},
                    {**child.pokes, **case.args(">HHI", 2, 1, child.basepage)})


_register_all()
