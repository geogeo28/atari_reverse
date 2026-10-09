"""THE OPCODE SWITCH AND THE COPY ROUND IT (`src/aes/gemsuper.c`: aes_dispatch `$fe5d9c`, aes_marshal `$fe64e6`) against
the ROM — `test/aes_gemsuper.py` has the calls: each an arm's routine's own registered row LIFTED into the call of the
switch that makes it.

WHAT IS HELD:
  * THE SHAPE, read off the ROM: one routine, its table of 116 longwords naming 69 arms, every arm reached by a
    case here (`test_every_arm_of_the_rom_s_table_has_a_call`);
  * EVERY ARM AT THE SWITCH — Tier 1 over the whole image and the answer words, by the arm's style — and the same
    calls AT THE MARSHAL, the copies in and back round them;
  * THE WAKES: the arms whose routine waits, taken through the dispatcher — the premise on the ROM's run, the C AT
    DSPTCH, Tier 1 through the host's scheduler, both blobs and the table's price on both counts (a door user's on
    the door users' own three tests, `test_tier3.py`); and calls held at the dispatcher alone, a wake's call with
    words of its own (a timer above 65,535 ticks is woken by no case);
  * EVERY WORD AN ARM READS TAKES TWO VALUES across the arm's cases
    (`test_every_word_an_arm_reads_takes_two_values_across_its_cases`), so no arm passes by pushing a constant;
  * THE COUNTS (`src/aes/gemsuper.c`): a copy past its array INSIDE the frame is the ROM's own, reproduced, the
    three largest on both blobs. PAST THE FRAME the two copies in are the ROM's return through the program's own
    words — shown on the ROM, refused by name in C before a byte moves — and the copy back, which only reads, is
    reproduced: the words are each build's own, modelled off target, vetted on each blob.

AND WHAT THE ROM DOES THAT A READER WOULD NOT EXPECT, each reproduced and held, never mended: graf_mkstate answers -1
(gr_mkstate's loop counter); thirty-two arms answer 1 whatever their routine did (scrp_read and fsel_input among
them); int_out words an arm does not write are handed back as the supervisor stack held them; evnt_multi without a
timer hands ev_multi a local it never set.
"""
import re
import struct
import subprocess

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
from recreate_kit import asm_twin

import abi
import aes
import aes_event
import aes_fslib as fsl
import aes_gemsuper as g
import aes_shell as sh
import aes_switch
import aes_switching as switching
import case
import test_aes_aptape          # noqa: F401  (the batteries whose registered rows the calls are lifted from, each
import test_aes_door as door    #               imported BEFORE this module registers its own)
import test_aes_evfork_interrupted as between_instructions
import test_aes_evlib           # noqa: F401
import test_aes_evmulti         # noqa: F401
import test_aes_fmalert         # noqa: F401
import test_aes_fmdo            # noqa: F401
import test_aes_fmlib           # noqa: F401
import test_aes_fs_input as selector
import test_aes_fs_input_rows   # noqa: F401
import test_aes_grdrag          # noqa: F401
import test_aes_grlib           # noqa: F401
import test_aes_grwait          # noqa: F401
import test_aes_gsx             # noqa: F401
import test_aes_gsxif           # noqa: F401
import test_aes_mnlib           # noqa: F401
import test_aes_ob_draw         # noqa: F401
import test_aes_ob_edit         # noqa: F401
import test_aes_objects_edit    # noqa: F401
import test_aes_objects_find    # noqa: F401
import test_aes_oblib           # noqa: F401
import test_aes_pdpipe          # noqa: F401
import test_aes_resource        # noqa: F401
import test_aes_resource_dos    # noqa: F401
import test_aes_resource_load   # noqa: F401
import test_aes_shell_buf       # noqa: F401
import test_aes_shell_find      # noqa: F401
import test_aes_wm_update       # noqa: F401
import test_aes_wmlib           # noqa: F401
import transcription
from case import merge_pokes

DISPATCH, MARSHAL = g.DISPATCH, g.MARSHAL
GEMSUPER = g.GEMSUPER
WORD, LONG = aes.WORD_BYTES, aes.LONG_BYTES
SHELL = aes.SHELL_PD
RETURNING = g.returning()
WOKEN, WOKEN_AT_THE_MARSHAL = g.woken(), g.woken_at_the_marshal()
SWITCHING = {**WOKEN, **WOKEN_AT_THE_MARSHAL}
REGISTERED, REGISTERED_SWITCHING = g.register()
# ...and the calls held at the dispatcher alone (`aes_gemsuper.HELD_AT_THE_DISPATCHER`): no rows, by nature.
HELD = g.held_at_the_dispatcher()


# ---- THE SHAPE: one routine, a table, 69 arms ---------------------------------------------------------------------------------
ARMS_OF_THE_TABLE = {opcode: door.arm_of(opcode) for opcode in range(addrs.AES_OPCODE_FIRST, addrs.AES_OPCODE_LAST + 1)}
DEFAULT_ARM = addrs.AES_ROM_DEFAULT_ARM
OPCODES_WITH_AN_ARM = sorted(opcode for opcode, arm in ARMS_OF_THE_TABLE.items() if arm != DEFAULT_ARM)
LINE_F_RETURN = 0xF031                  # the switch's one exit: `move.w d6,d0`, then the masked return (D6, D7)
THE_SWITCH_S_BYTES = 1866               # `$fe5d9c..$fe64e5`: the inventory's span of it
TABLE_ENTRIES = addrs.AES_OPCODE_LAST - addrs.AES_OPCODE_FIRST + 1      # 116 longwords
ARMS_WITH_A_ROUTINE, GAPS_OF_THE_TABLE = 68, 48     # the inventory's count: 68 arms and the default, 69 "functions"
ANSWER_KEPT = 0x3C00                    # `move.w d0,d6`: an arm that keeps what its routine answered
D6_LOADED = (0x3C28, 0x3C39, 0x7CFF)    # ...or loads D6 itself: appl_init (`move.w 28(a0),d6`), graf_handle, the default


def test_the_switch_is_one_routine_from_its_link_to_its_one_masked_return():
    """`$fe5d9c..$fe64e5`, 1,866 bytes: ONE Alcyon routine — a `link`, the head, 69 arms, the ladder of pops the arms
    leave by, and ONE Line-F return ($fe64e4), the only one before the marshal's `link`. The inventory's 69 "functions"
    are the arms: every table entry lies INSIDE that span."""
    exits = [at for at in range(addrs.AES_ROM_DISPATCH, addrs.AES_ROM_MARSHAL, WORD)
             if case.word_in(BASE_IMAGE, at) == LINE_F_RETURN]
    assert exits == [addrs.AES_ROM_MARSHAL - WORD] and addrs.AES_ROM_MARSHAL - addrs.AES_ROM_DISPATCH == THE_SWITCH_S_BYTES
    assert all(addrs.AES_ROM_DISPATCH < arm < door.LADDER for arm in ARMS_OF_THE_TABLE.values())
    assert len(set(ARMS_OF_THE_TABLE.values())) == ARMS_WITH_A_ROUTINE + 1 and len(OPCODES_WITH_AN_ARM) == ARMS_WITH_A_ROUTINE
    assert len(ARMS_OF_THE_TABLE) == TABLE_ENTRIES == ARMS_WITH_A_ROUTINE + GAPS_OF_THE_TABLE


def _opcodes_called():
    calls = [lift.call for lift in RETURNING.values()]
    calls += [g.call_of(name).call for name in (*g.WOKEN, *g.THROUGH_INTERRUPTS, *(each.label for each in g.APPL_EXITS))]
    return {aes.signed(call.opcode) & aes.WORD_MASK for call in calls}


def test_every_arm_of_the_rom_s_table_has_a_call():
    """EVERY ARM IS REACHED THROUGH THE SWITCH: the opcodes of this battery's calls are every opcode the ROM's table
    gives an arm of its own — and the default arm's are a gap, both ends of the range and both ends of a word."""
    called = _opcodes_called()
    assert sorted(called & set(OPCODES_WITH_AN_ARM)) == OPCODES_WITH_AN_ARM
    no_such = set(g.NO_SUCH_CALLS.values())
    assert no_such <= called and not no_such & set(OPCODES_WITH_AN_ARM)
    assert {addrs.AES_OPCODE_FIRST - 1, addrs.AES_OPCODE_LAST + 1, 0, 0xFFFF, 0x7FFF, 0x8000} <= no_such
    assert all(ARMS_OF_THE_TABLE.get(opcode, DEFAULT_ARM) == DEFAULT_ARM for opcode in no_such)


# ---- EVERY WORD AN ARM READS TAKES TWO VALUES ---------------------------------------------------------------------------------
# An arm handed ONE value of a word by every case is not held to reading it: `in(7)` replaced by the constant passes
# every differential. So, for every arm of the table, over EVERY call this battery makes of it at the switch — the
# calls that return, the wakes, the calls taken through interrupts and the calls held at the dispatcher — each word
# of int_in and each longword of addr_in takes at least two values. WHICH WORDS AN ARM READS is the arm table's own
# statement (`aes_gemsuper.ARMS`: the words a lifted call hands; a word the ROM's arm never reads is `Unread` there,
# and the ROM is asked below that it reads none of them).
def _every_call_at_the_switch():
    calls = [(label, lift.call) for label, lift in RETURNING.items()]
    calls += [(name, g.call_of(name).call) for name in (*g.WOKEN, *g.THROUGH_INTERRUPTS, *(each.label for each in g.APPL_EXITS))]
    calls += [(each.label, g.made_again(each.label).call) for each in (*g.WOKEN_AGAIN, *g.HELD_AT_THE_DISPATCHER)]
    return calls


def _words_of_one_value():
    """`{(opcode, array, index): the one value}` over every arm's calls — the `Unread` words left out."""
    single = {}
    for opcode in OPCODES_WITH_AN_ARM:
        calls = [call for _label, call in _every_call_at_the_switch() if call.opcode == opcode]
        for array in ("int_in", "addr_in"):
            for index in range(max(len(getattr(call, array)) for call in calls)):
                values = {getattr(call, array)[index] for call in calls if index < len(getattr(call, array))}
                if len(values) < 2 and not all(isinstance(value, g.Unread) for value in values):
                    single[opcode, array, index] = values
    return single


# THE WORDS NO CASE GIVES A SECOND VALUE, each BY NAME WITH ITS REASON — asserted, so one that gains a second value
# leaves the list and one that loses its second value is refused:
ONE_VALUE_BY_NATURE = {
}


def test_every_word_an_arm_reads_takes_two_values_across_its_cases():
    single = _words_of_one_value()
    assert set(single) == set(ONE_VALUE_BY_NATURE), (
        "an arm is handed ONE value of a word it reads by every case (a switch that pushed the constant would pass): "
        + "; ".join(f"opcode {opcode} {array}[{index}] = {sorted(values)}" for (opcode, array, index), values in sorted(
            single.items()) if (opcode, array, index) not in ONE_VALUE_BY_NATURE)
        + f" — or no longer single: {sorted(set(ONE_VALUE_BY_NATURE) - set(single))}")


def _calls_with_an_unread_word():
    return [(label, lift) for label, lift in RETURNING.items() if any(isinstance(word, g.Unread) for word in lift.call.int_in)]


def test_a_word_marked_unread_is_one_the_rom_s_arm_never_reads():
    """THE ARM TABLE'S CLAIM, ASKED OF THE ROM: a call's `Unread` word (objc_change's int_in[1], graf_watchbox's
    int_in[0]) handed as another value leaves the ROM's whole run as it was — the image but for that word, and D0."""
    marked = _calls_with_an_unread_word()
    assert {lift.call.opcode for _label, lift in marked} == {addrs.AES_ROM_OB_CHANGE_OPCODE, addrs.AES_ROM_GR_WATCHBOX_OPCODE}
    for label, lift in marked:
        unread = [index for index, word in enumerate(lift.call.int_in) if isinstance(word, g.Unread)]
        other = lift._replace(call=g.with_words({index: 0 for index in unread})(lift.call))
        runs = []
        for each in (lift, other):
            arguments, pokes = g.staged(each)
            final, _writes, registers = emu.run(make_image(aes.staged(DISPATCH, arguments, pokes)), addrs.AES_ROM_DISPATCH)
            for index in unread:
                final[g.INT_IN_AT + index * WORD:g.INT_IN_AT + (index + 1) * WORD] = bytes(WORD)
            runs.append((bytes(final), registers["d0"]))
        assert runs[0] == runs[1], label


def test_the_header_s_own_opcodes_and_layouts_are_the_rom_s():
    """What the C switches on and copies by, held to the ROM beside the calls that use them: the six opcodes
    `addrs.h` pairs with no routine are the table's entries for their arms (the calls here take theirs off the
    table, `aes_gemsuper.ARMS_OF_NO_ONE_ROUTINE`); the parameter block is six longwords in the order the marshal's
    instructions index it; and the frame is the ROM's `link`, less Alcyon's argument slot."""
    for name, opcode in zip(g.ARMS_OF_NO_ONE_ROUTINE, (g.APPL_INIT, g.APPL_READ, g.APPL_EXIT, g.MENU_TEXT, g.GRAF_HANDLE,
                                                      g.GRAF_MOUSE)):
        assert GEMSUPER[f"AES_{name}_OPCODE"] == opcode and ARMS_OF_THE_TABLE[opcode] == g.ARMS_OF_NO_ONE_ROUTINE[name], name
    assert [GEMSUPER[f"AESPB_{name}"] for name in ("CONTROL", "GLOBAL", "INT_IN", "INT_OUT", "ADDR_IN", "ADDR_OUT")] == list(
        range(0, g.PARAMETER_BLOCK.size, LONG))
    link_displacement = aes.signed(case.word_in(BASE_IMAGE, addrs.AES_ROM_MARSHAL + WORD))
    assert -link_displacement - LONG == GEMSUPER["MARSHAL_FRAME_BYTES"] == GEMSUPER["MARSHAL_CONTROL"] + 4 * WORD
    waits = aes.header_constants("evwait.h")       # ap_rdwr's code IS the wait's kind: the door's two names of them
    assert (g.EVDOOR["AP_RDWR_READ"], g.EVDOOR["AP_RDWR_WRITE"]) == (waits["IASYNC_READ"], waits["IASYNC_WRITE"])


def _keeps_its_routine_s_answer(opcode):
    """Does the ROM's arm of `opcode` store D6 — its routine's D0, or a word of its own?"""
    lo, hi = door.arm_span(opcode)
    words = [case.word_in(BASE_IMAGE, at) for at in range(lo, hi, WORD)]
    return ANSWER_KEPT in words or any(word in words for word in D6_LOADED)


ANSWER_DONE = [opcode for opcode in OPCODES_WITH_AN_ARM if not _keeps_its_routine_s_answer(opcode)]
ARMS_THAT_ANSWER_1 = 32
# ...among them the arms whose ROUTINE answers something a program might expect back, and does not get:
ANSWERS_DROPPED = (g.APPL_READ, addrs.AES_ROM_AP_RDWR_OPCODE, addrs.AES_ROM_SC_READ_OPCODE, addrs.AES_ROM_SC_WRITE_OPCODE,
                   addrs.AES_ROM_FS_INPUT_OPCODE, addrs.AES_ROM_WM_OPEN_OPCODE, addrs.AES_ROM_WM_GET_OPCODE,
                   addrs.AES_ROM_WM_SET_OPCODE)


def test_thirty_two_arms_answer_1_whatever_their_routine_did():
    """A ROM BEHAVIOUR, KEPT: the switch starts with D6 = 1 (`$fe5da8`) and an arm with no `move.w d0,d6` answers
    that — appl_read and appl_write (ap_rdwr's answer dropped), menu_bar, objc_draw, scrp_read and scrp_write (whose
    routines answer whether the copy was made), fsel_input, wind_open, wind_close, wind_get, wind_set ... READ OFF
    THE ROM'S ARMS, and each such arm's calls here answer 1."""
    assert len(ANSWER_DONE) == ARMS_THAT_ANSWER_1 and set(ANSWERS_DROPPED) <= set(ANSWER_DONE)
    assert g.GEMSUPER["AES_GRAF_MOUSE_OPCODE"] in ANSWER_DONE and addrs.AES_ROM_GR_MKSTATE_OPCODE not in ANSWER_DONE



# ---- THE SWITCH'S HEAD ON TARGET: the ROM's own shape, a bounds check and one indexed jump ----------------------------------------
# `-fno-jump-tables` is the build's (atari/target.mk: no absolute address in read-only data for a .PRG's relocation
# table to carry); `aes_dispatch` alone is compiled with a table (`src/aes/gemsuper.c`: COMPILED_AS_A_JUMP_TABLE) —
# measured against the compare tree the flag gives: appl_init 714 cycles to the ROM's 632 (1.13), with the table 608
# (0.96) — the table's own line, `make bench`. What makes that sound is held here, on the build's own instructions
# and its own relocations.
RANGE_CHECKED = re.compile(rf"cmpi?w #{TABLE_ENTRIES - 1},%d\d")
THE_TABLE_IS_GONE = (
    "aes_dispatch has no jump indexed through the PC on this blob: the switch was built as A COMPARE TREE — the "
    "per-function `optimize(\"jump-tables\")` (`src/aes/gemsuper.c`, COMPILED_AS_A_JUMP_TABLE) no longer overrides the "
    "build's `-fno-jump-tables` (a compiler that ignores the attribute, a flag that outranks it). What it costs: an "
    "opcode at the tree's bottom pays seven compares for one indexed jump — appl_init 714 cycles to the ROM's 632, "
    "1.13 of them: OVER the bar, where the table's 608 is 0.96")
ABOVE_THE_RANGE = re.compile(r"bhi[sw]? ")
INDEXED_JUMP = re.compile(r"jmp %pc@\(")
A_COMPARE = re.compile(r"cmp")


def test_the_switch_is_a_bounds_check_and_one_indexed_jump_on_both_blobs(blob):
    """`$fe64ba sub.w #10` / `$fe64be cmp.w #115` / `bhi` / the table / `jmp (a0)`: our switch's head has ONE compare
    — the opcode less 10 against 115, unsigned — before a jump indexed through the PC, and no other before it."""
    body = [text for _pc, _length, text in between_instructions.blob_body(blob, "aes_dispatch")]
    jump = next((at for at, text in enumerate(body) if INDEXED_JUMP.match(text)), None)
    assert jump is not None, THE_TABLE_IS_GONE
    head = body[:jump]
    assert [text for text in head if A_COMPARE.match(text)] == [text for text in head if RANGE_CHECKED.match(text)]
    assert len([text for text in head if RANGE_CHECKED.match(text)]) == 1
    checked = next(at for at, text in enumerate(head) if RANGE_CHECKED.match(text))
    assert ABOVE_THE_RANGE.match(head[checked + 1]), head[checked + 1]
    assert any(text.startswith(("addiw #-10,", "subiw #10,", "subqw #10,", "addqw #-10,")) for text in head[:checked]), head


RELOCATIONS_OF = re.compile(r"RELOCATION RECORDS FOR \[([^\]]+)\]:\n(.*?)(?:\n\n|\Z)", re.S)
A_RELOCATION = re.compile(r"^[0-9a-f]{8}\s+(R_68K_\w+)\s+(\S+)", re.M)
THE_SWITCH_S_TEXT = ".text.aes_dispatch"


def test_the_switch_s_table_names_no_absolute_address():
    """THE REASON `-fno-jump-tables` EXISTS DOES NOT REACH THIS TABLE: every relocation IN the switch's own text is a
    CALL of another function by its name — none names a place in that text (a table of absolute addresses would be
    longwords relocated against the function's own section, as the marshal's call of the switch is) — and the
    object has no read-only data at all.

    WHAT IT READS IS THE SHIPPED BLOB'S OBJECT — the build that carries `-ffunction-sections`, so the switch's text
    is a section of its own. OWED the day `gemsuper.c` joins the `atari/` ROM link: the same reading of THAT link's
    object, whose flags are its own."""
    built = transcription.SHIPPED_ELF.parent / "obj" / "src_aes_gemsuper_c.o"
    listed = subprocess.run(["m68k-elf-objdump", "-r", "-h", str(built)], capture_output=True, text=True, check=True).stdout
    by_section = {section: A_RELOCATION.findall(records) for section, records in RELOCATIONS_OF.findall(listed)}
    in_the_switch = by_section[THE_SWITCH_S_TEXT]
    # ...at least one call an arm with a routine (most arms call one; the inline ones none, the multi-call ones more)
    assert len(in_the_switch) >= ARMS_WITH_A_ROUTINE - len(g.ARMS_OF_NO_ONE_ROUTINE), len(in_the_switch)
    assert all(kind == "R_68K_32" and not target.startswith(".") for kind, target in in_the_switch), (
        sorted({(kind, target) for kind, target in in_the_switch if kind != "R_68K_32" or target.startswith(".")}))
    assert (THE_SWITCH_S_TEXT in {target.split("+")[0] for _kind, target in by_section[".text.aes_marshal"]}
            and ".rodata" not in listed), "the premise: a reference to the switch's text WOULD be listed against its section"


# ---- EVERY ARM, AT THE SWITCH AND AT THE MARSHAL ----------------------------------------------------------------------------------
def _held(lift, result, entry):
    """What every returning call is held to beside the differential: the answer where the arm keeps the ROM's 1."""
    answer = result.answer() if entry == DISPATCH else g.int_out(result.final, 1)[0]
    if lift.call.opcode in ANSWER_DONE:
        assert answer == g.DONE, f"{lift.source}: answers {answer}"
    return answer


@pytest.mark.parametrize("label", RETURNING)
def test_a_call_at_the_switch_is_the_rom_s(label):
    """TIER 1 OF EVERY ARM, entered at `$fe5d9c` over the arrays of a real call: the whole image, the answer words in
    int_out among it (stale before the call), and D0."""
    lift = RETURNING[label]
    _held(lift, g.run(lift), DISPATCH)


@pytest.mark.parametrize("label", RETURNING)
def test_a_call_at_the_marshal_is_the_rom_s(label):
    """...and the same call through `$fe64e6`: the program's control, int_in and addr_in copied in, the switch, its
    answer and int_out copied back — the marshal answers nothing, and the program's int_out[0] is the switch's answer.
    addr_out is written for rsrc_gaddr alone, with the address rs_gaddr parked."""
    lift = RETURNING[label]
    result = g.run(lift, MARSHAL)
    _held(lift, result, MARSHAL)
    parked = case.long_in(result.final, aes.header_constants("objects.h")["AES_RS_ADDROUT"])
    expected = parked if lift.call.opcode == addrs.AES_ROM_RS_GADDR_OPCODE else g.STALE_LONG
    assert case.long_in(result.final, g.ADDR_OUT_AT) == expected


@pytest.mark.parametrize("source", g.THROUGH_INTERRUPTS)
def test_a_door_user_s_call_taken_through_interrupts_is_the_rom_s(source):
    """A DOOR USER'S ARM with its routine's own interrupts delivered at the same door calls: the arm adds none, so
    the row's ordinals are the switch's."""
    lift = g.lifted(source)
    assert g.through_interrupts(lift).returned


# ---- fsel_input: A WHOLE SELECTOR, in one call ----------------------------------------------------------------------------------
@pytest.mark.parametrize("label", ("Return in the ring", "a name and Return in the ring"))
def test_fsel_input_s_whole_selector_through_the_switch(label):
    """THE ARM OVER A SELECTOR THAT RUNS TO ITS END (the lifted row is the one that is refused its memory, and reads
    none of its arguments): the keys typed before the call, REAL GEMDOS on both shores over the staged disk, the
    VDI's cores and the event door bound (`aes_fslib.run_session`'s arrangement, the C first in a fork) — the path
    and the selection out of addr_in, each handed back, the button into int_out[1], and the answer 1 whatever
    fs_input's was."""
    path, codes, budget, (button, path_back, selection_back) = selector.REAL[label]
    machine = merge_pokes(selector._typed_ahead(path, *codes), fsl.STALE_ANSWERS, fsl.STALE_SLOTS)
    call = g.Call(addrs.AES_ROM_FS_INPUT_OPCODE, (), (fsl.PATH_AT, fsl.FILE_AT), 2)
    arguments, pokes = g.at_the_switch(call, machine)
    aes_event.begin_a_door_run(sh.REAL_WINDOWS)
    result = aes_event.capped_run(DISPATCH, budget, {}, lambda **limits: aes.run_function(
        DISPATCH, arguments, pokes, hook=fsl.session_doors([], []), dropped_windows=sh.REAL_WINDOWS, poison=False,
        first=aes_event.forked_inside_its_pass(DISPATCH, arguments), **limits))
    assert result.answer() == g.DONE and g.int_out(result.final, 2)[1] == button
    assert (selector.text_at(result.final, fsl.PATH_AT), selector.text_at(result.final, fsl.FILE_AT)) == (path_back, selection_back)


# ---- WHAT THE ARMS ANSWER --------------------------------------------------------------------------------------------------------
def test_graf_mkstate_answers_minus_one():
    """A ROM BEHAVIOUR, KEPT: graf_mkstate's arm keeps D0 as gr_mkstate leaves it (`$fe62fe move.w d0,d6`), and
    gr_mkstate — hand 68000, answering through its four pointers — leaves there its `dbf` counter run out
    (`$fe8770 moveq #3,d0` .. `$fe877a dbf d0`): $ffff. The program's int_out[0] is -1."""
    lift = RETURNING["opcode 79, as aes_gr_mkstate, four answers"]
    assert g.run(lift).answer() == GEMSUPER["GRAF_MKSTATE_ANSWER"] == -1
    assert g.int_out(g.run(lift, MARSHAL).final, 1) == [-1]


def test_appl_init_fills_the_program_s_global():
    """appl_init: the AES's version and its one application, the caller's id, the screen's planes, THEGLO's address
    and the desk's two drive words — global[3..9] left as the program had them."""
    result = g.run(RETURNING["appl_init"])
    filled = struct.unpack(">15H", result.after(g.GLOBAL_AT, 30))
    running = case.long_in(result.final, aes.AES_RLR)
    pid = case.word_in(result.final, running + aes.PD_PID)
    assert filled[:3] == (GEMSUPER["AES_VERSION"], 1, pid) and result.answer() == pid
    assert filled[3:10] == (g.STALE,) * 7
    assert filled[10] == case.word_in(result.final, aes.header_constants("gsx.h")["AES_GL_NPLANES"])
    assert aes.words_long(filled[11], filled[12]) == aes.AES_THEGLO
    assert filled[13:] == (case.word_in(result.final, GEMSUPER["AES_GL_BVDISK"]),
                           case.word_in(result.final, GEMSUPER["AES_GL_BVHARD"]))


def test_graf_handle_answers_the_cell_and_the_box():
    result = g.run(RETURNING["graf_handle"])
    handle = case.word_in(result.final, aes.header_constants("gsx.h")["AES_GL_HANDLE"])
    wbox = case.word_in(result.final, aes.header_constants("gsxif.h")["AES_GL_WBOX"])
    assert g.int_out(result.final, 6) == [aes.signed(g.STALE), case.word_in(result.final, aes.AES_GL_WCHAR),
                                          case.word_in(result.final, aes.AES_GL_HCHAR), wbox,
                                          case.word_in(result.final, aes.AES_GL_HBOX), aes.signed(g.STALE)]
    assert result.answer() == handle


@pytest.mark.parametrize("entry", (DISPATCH, MARSHAL))
def test_graf_handle_over_metrics_each_its_own(entry):
    """THE LABELLED CLASS (`aes_gemsuper.ARGUMENT_CLASS_METRICS`): on the captured machine a cell is as wide as it
    is high and the handle is the 1 every arm of no answer gives — staged each its own, graf_handle's five words
    are told apart: the answer is the HANDLE, and the four sizes go back in the ROM's order."""
    assert g.ARGUMENT_CLASS_METRICS.startswith("ARGUMENT CLASS")
    result = g.run(RETURNING["graf_handle"], entry, onto=g.TELLING_METRICS)
    assert g.int_out(result.final, 5)[1:] == [6, 9, 13, 17]
    assert (result.answer() if entry == DISPATCH else g.int_out(result.final, 1)[0]) == 3


def test_menu_text_s_item_is_an_unsigned_index():
    """A ROM BEHAVIOUR, KEPT — THE LABELLED CLASS (`aes_gemsuper.ARGUMENT_CLASS_FAR_ITEM`): `$fe6008 mulu.w #24`.
    Item $8000 is the object 786,432 bytes ABOVE the tree, not 786,432 below it: its ob_spec, staged there, is
    where the caller's string is copied."""
    assert g.ARGUMENT_CLASS_FAR_ITEM.startswith("ARGUMENT CLASS")
    lift = RETURNING["menu_text: an item's text replaced"]
    far = lift._replace(call=lift.call._replace(int_in=(g.A_FAR_ITEM,)))
    result = g.run(far, onto=g.far_item(lift.call.addr_in[0]))
    assert result.after(g.AN_ITEM_S_TEXT_AT, len(g.A_TEXT)) == g.A_TEXT


def test_menu_text_copies_the_caller_s_string_over_the_item_s_own():
    lift = RETURNING["menu_text: an item's text replaced"]
    result = g.run(lift)
    tree, text = lift.call.addr_in
    item, = lift.call.int_in
    spec = case.long_in(result.final, (tree & g.BUS) + item * aes.OB_BYTES + aes.OB_SPEC)
    assert result.after(spec & g.BUS, len(g.A_TEXT)) == g.A_TEXT and text == g.TEXT_AT


def test_objc_find_searches_from_the_object_it_is_handed():
    """A file line's point is found from the root and NOT from the scroll bar, which does not hold it: the arm's
    first word is where the search starts (the row from the slider's track finds what the root's search finds)."""
    from_the_root = g.run(RETURNING["opcode 43, as aes_ob_find, a file line, two levels"]).answer()
    from_the_scroll_bar = g.run(RETURNING["objc_find: a file line's point, searched from the scroll bar: not found"]).answer()
    assert from_the_root > 0 and from_the_scroll_bar == aes.OB_NIL


def test_evnt_dclick_sets_the_rate_it_is_handed():
    assert g.run(RETURNING["evnt_dclick: another rate set"]).answer() == g.ANOTHER_RATE != 0


@pytest.mark.parametrize("label", [f"no such call: {name}" for name in g.NO_SUCH_CALLS])
def test_an_opcode_with_no_arm_shows_the_alert_and_answers_minus_one(label):
    """THE DEFAULT ARM, from both ends: below 10 (the `sub.w #10` wraps, `bhi` is unsigned), above 125, a gap of the
    table — the alert "Bad Function #" (the differential's whole image: the screen put back) and -1."""
    assert g.run(RETURNING[label]).answer() == GEMSUPER["AES_ANSWER_NO_SUCH_CALL"]


# ---- THE WAKES: the arms whose routine waits -----------------------------------------------------------------------------------------
def _source_of(row):
    """The registered row of the arm's routine a row that switches is lifted from, or made again over — or None
    (appl_exit's)."""
    name = row.label.removeprefix("marshalled: ")
    if any(name == each.label for each in g.WOKEN_AGAIN):
        return aes_event.SWITCHING_ROWS[g.wake_made_again(name)]
    source = name.split(", as ", 1)[1] if ", as " in name else None
    return aes_event.SWITCHING_ROWS.get(source)


@pytest.mark.parametrize("label", SWITCHING)
def test_an_arm_adds_no_wait_to_its_routine_s_wake(label):
    """THE PREMISE, DERIVED: the ROM's run of the call through its own dispatcher returns in the process that made
    it, having idled as often, polled as often and entered the same processes in the same order as its routine's
    own row — the arm adds no wait and no switch — and the row carries that run's deliveries. appl_exit has no such
    row: its one yield (all_run's) comes back to the caller with nothing delivered."""
    row, made = SWITCHING[label], switching.settled(SWITCHING[label])
    the_rom_s = switching.scheduled(row, made.pokes)
    assert the_rom_s.ended == aes_switch.RETURNED and made.switches == switching.rederived(row), label
    at_its_end = the_rom_s.memory
    assert aes.list_of(at_its_end, aes.AES_RLR)[0] == made.switches.process and at_its_end[aes.AES_INDISP] == 0
    source = _source_of(row)
    if source is None:
        assert (the_rom_s.idles, tuple(the_rom_s.entered), dict(the_rom_s.delivered)) == (0, (SHELL,), {}), label
        return
    assert (the_rom_s.idles, the_rom_s.polls, tuple(the_rom_s.entered)) == (
        source.switches.idles, source.switches.polls, tuple(source.entered)), label
    assert sorted(the_rom_s.delivered) == sorted(source.switches.at_idles)


# appl_exit's one switch is all_run's BARE YIELD with nobody else ready: the ROM's own dispatcher comes straight back
# to the caller, so a run of the ROM that is not stopped at dsptch RETURNS — there is no "ends at the dispatcher"
# half to hold the C's refusal to. What it stored before the yield is held where the model runs it on: a door
# user's image at EVERY dispatch (`aes_switching.companion`, below).
COMES_STRAIGHT_BACK = tuple(label for label in SWITCHING if "appl_exit" in label)
ENDS_AT_THE_DISPATCHER = tuple(label for label in SWITCHING if label not in COMES_STRAIGHT_BACK)


def test_appl_exit_s_yield_comes_straight_back_on_the_rom():
    """THE PREMISE of leaving appl_exit out of the next test: taken through nothing, the ROM's own run of it returns
    — its dispatcher entered once, by all_run's yield, and the caller the only process ready."""
    assert len(COMES_STRAIGHT_BACK) == len(g.APPL_EXITS) + 1
    for label in COMES_STRAIGHT_BACK:
        row = SWITCHING[label]
        _calls, _delivered, _memory, returned = aes_event.rom_interrupted(row.name, row.arguments, row.machine(), {})
        assert returned is not None, label


def _held_at_its_first_switch(row):
    """The C of `row` AT DSPTCH against the ROM's there, by the arm's style; how the ROM's own run switches."""
    if not row.door:
        how = aes_event.rom_at_dsptch(row.name, row.arguments, row.machine()).switches
        aes_event.switches_where_the_rom_does(row.name, row.arguments, row.machine(), switches=how)
        return how
    how = aes_event.BLOCKS if row.at_calls else aes_event.rom_at_dsptch(row.name, row.arguments, row.machine()).switches
    held = aes_event.interrupted(row.name, row.arguments, row.machine(), row.at_calls or {}, objects=row.door.objects,
                                 switches=how, budget=row.budget)
    assert not held.returned
    return how


@pytest.mark.parametrize("label", ENDS_AT_THE_DISPATCHER)
def test_a_call_s_first_switch_is_held_at_the_dispatcher(label):
    """WHERE THE C FIRST LEAVES — a block or a yield, as the ROM's own run says at dsptch — its whole image the
    ROM's there: what the arm and its routine stored before the switch (a door user's through
    `aes_event.blocked_then_woken`'s first half, the frames its door calls were handed among it)."""
    _held_at_its_first_switch(SWITCHING[label])


@pytest.mark.parametrize("label", HELD)
def test_a_wake_s_call_with_words_of_its_own_is_held_at_the_dispatcher(label):
    """...and the calls that are held THERE ALONE (`aes_gemsuper.HELD_AT_THE_DISPATCHER`): a wake's call made again
    with other words — a time whose HIGH word is not zero (the wait's count is in the image compared: the timer's
    two words made one long, low word first), a top byte on a buffer, another process's pipe — each BLOCKS where
    the ROM's does, over the image the ROM's holds there."""
    assert _held_at_its_first_switch(HELD[label]) == aes_event.BLOCKS


A_LONG_TIMER_S_HIGH_WORD = {"evnt_timer: a time above 65,535 ticks": 1,
                            "evnt_multi: a timer above 65,535 ticks": GEMSUPER["EVNT_MULTI_TIME_HIGH"]}


@pytest.mark.parametrize("label", A_LONG_TIMER_S_HIGH_WORD)
def test_a_long_time_s_high_word_is_in_the_wait_the_rom_queues(label):
    """THE PREMISE of holding a timer at the dispatcher: the ROM's own image at dsptch differs between the call
    with a time above 65,535 ticks and the same call with the time's high word zero — the high word reaches the
    wait the image is compared over."""
    row, lift = HELD[label], g.made_again(label)
    assert lift.call.int_in[A_LONG_TIMER_S_HIGH_WORD[label]] == g.A_LONG_TIME[1] != 0
    low_alone = lift._replace(call=g.with_words({A_LONG_TIMER_S_HIGH_WORD[label]: 0})(lift.call))
    the_long_s = aes_event.rom_at_dsptch(row.name, row.arguments, row.machine())
    the_low_s = aes_event.rom_at_dsptch(row.name, *g.staged(low_alone))
    assert the_long_s.switches == the_low_s.switches == aes_event.BLOCKS and the_long_s.memory != the_low_s.memory


@pytest.mark.parametrize("label", SWITCHING)
def test_a_call_taken_on_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1 OF A WAKE (`aes_switching.companion`, nothing dropped): the C through the host's scheduler — the arm,
    its routine, the wait, the wake — the same idles and polls, the answer, every byte outside the run's own stack."""
    row = SWITCHING[label]
    ran = switching.companion(row)
    if row.name == DISPATCH and g.call_of(_name_of(label)).call.opcode in ANSWER_DONE:
        assert ran.answer & aes.WORD_MASK == g.DONE


def _name_of(label):
    name = label.removeprefix("marshalled: ")
    return name.split(", as ", 1)[1] if ", as " in name else name



# ---- THE WAKES ON BOTH BLOBS, AND IN THE TABLE ------------------------------------------------------------------------------------
BENCH, SHIPPED = "bench", "bench_shipped"      # a blob's directory: what `aes_switching.vet_on_a_blob` reads a pin by
Priced, NO_WINDOW = switching.Priced, switching.NO_WINDOW
# THE WHOLE RUN'S CYCLES of each row that switches — the ROM's and ours, net of the entry both share, by blob (the
# second differential's own measurement, `aes_switching.measured_on`) — and WHAT THE TABLE PRICES
# (`aes_switching.Priced`): each shore's own cycles; the caller's own, net of the calls of rebound entries, and how
# many it closes; the foreign windows. A row that moves says why: the arm, its routine, the dispatcher itself.
# @PINS-BEGIN (measured: scratch `pins.py`, then `pins_emit.py`)
WHOLE_RUN = {
    "opcode 11, as aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)":
        {BENCH: (1176770, 1170538), SHIPPED: (1176770, 1170272)},
    'opcode 24, as aes_ev_timer, a time of five ticks, blocked; run out by them':
        {BENCH: (31684, 26510), SHIPPED: (31684, 26412)},
    'opcode 71, as aes_gr_dragbox, held at the mouse; moved, then released':
        {BENCH: (276684, 257452), SHIPPED: (276684, 255062)},
    'opcode 25, as aes_ev_multi, blocked and woken — a release wakes: the button up, which is down':
        {BENCH: (45202, 38104), SHIPPED: (45202, 37916)},
    'marshalled: appl_exit: no accessory, the pipe empty':
        {BENCH: (16326, 13504), SHIPPED: (16326, 13450)},
    'opcode 14, as aes_ap_tplay, none of four records played: a count of 0':
        {BENCH: (12834, 11320), SHIPPED: (12834, 11440)},
    'opcode 25, as aes_ev_multi, blocked and woken — a key wakes: a key, none queued':
        {BENCH: (44006, 37716), SHIPPED: (44006, 37526)},
    'opcode 75, as aes_gr_watchbox, blocked three times: the mouse in, out again, then the rise: 0':
        {BENCH: (258096, 221742), SHIPPED: (258096, 218758)},
    'opcode 25, as aes_ev_multi, blocked and woken — leaving wakes: two rectangles':
        {BENCH: (62842, 53604), SHIPPED: (62842, 52480)},
    'opcode 14, as aes_ap_tplay, a wait and a press played: no mouse record':
        {BENCH: (71708, 61912), SHIPPED: (71708, 62592)},
    'opcode 25, as aes_ev_multi, blocked and woken — the ticks wake: a message and a timer':
        {BENCH: (48806, 41108), SHIPPED: (48806, 40574)},
    'opcode 76, as aes_gr_slidebox, the elevator held; dragged down, then released':
        {BENCH: (275602, 253434), SHIPPED: (275602, 250890)},
    'opcode 25, as aes_ev_multi, blocked and woken — entering wakes: the second rectangle alone':
        {BENCH: (52738, 46286), SHIPPED: (52738, 45950)},
    "opcode 15, as aes_ap_trecd, one record, a key's":
        {BENCH: (47416, 39606), SHIPPED: (47416, 39448)},
    'opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe':
        {BENCH: (1188090, 1181176), SHIPPED: (1188090, 1181032)},
    "opcode 107, as aes_wm_update, the lock handed to the screen manager, which waits for it: a yield inside unsync's call":
        {BENCH: (15166, 12250), SHIPPED: (15166, 12372)},
    'appl_exit: no accessory, the pipe empty':
        {BENCH: (15056, 12108), SHIPPED: (15056, 12228)},
    'opcode 20, as aes_ev_keybd, no key queued, blocked; woken by Return':
        {BENCH: (32590, 26952), SHIPPED: (32590, 26640)},
    'opcode 50, as aes_fm_do, nothing typed: the first wait blocked; woken by Return':
        {BENCH: (177068, 151206), SHIPPED: (177068, 141320)},
    'opcode 15, as aes_ap_trecd, a count of 0, ended at once: nothing recorded':
        {BENCH: (46548, 38622), SHIPPED: (46548, 38646)},
    'appl_exit: a message left in the pipe, read away':
        {BENCH: (24076, 18654), SHIPPED: (24076, 17834)},
    'opcode 21, as aes_ev_button, a press waited for, blocked; woken by it':
        {BENCH: (34840, 28168), SHIPPED: (34840, 27858)},
    'opcode 52, as aes_fm_alert, no button the default: Return taken, the next wait blocked; the second button clicked while it waits':
        {BENCH: (1493598, 1414124), SHIPPED: (1493598, 1406676)},
    'opcode 21, as aes_ev_button, a double click waited for, blocked; woken by the two presses':
        {BENCH: (34904, 28258), SHIPPED: (34904, 27948)},
    "appl_exit: two accessories told to close, the caller's own message read away":
        {BENCH: (44546, 32860), SHIPPED: (44546, 30160)},
    'opcode 22, as aes_ev_mouse, the mouse in the rectangle it is to leave, blocked; woken by its leaving':
        {BENCH: (41330, 35488), SHIPPED: (41330, 35030)},
    'opcode 56, as aes_fm_button, the button held down, OK not under the mouse: the watch blocked; woken by the rise':
        {BENCH: (123504, 104008), SHIPPED: (123504, 102570)},
    'opcode 25, as aes_ev_multi, blocked and woken — the ticks wake: a timer':
        {BENCH: (43044, 37124), SHIPPED: (43044, 37148)},
    'marshalled: opcode 20, as aes_ev_keybd, no key queued, blocked; woken by Return':
        {BENCH: (33860, 28348), SHIPPED: (33860, 27862)},
    "opcode 23, as aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)":
        {BENCH: (1177110, 1170644), SHIPPED: (1177110, 1170380)},
    'opcode 70, as aes_gr_rubbox, the corner at the mouse; stretched, then released':
        {BENCH: (297884, 278708), SHIPPED: (297884, 276180)},
    'opcode 25, as aes_ev_multi, blocked and woken — a double click wakes: a double click':
        {BENCH: (46274, 38900), SHIPPED: (46274, 38712)},
    'marshalled: opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe':
        {BENCH: (1190616, 1184576), SHIPPED: (1190616, 1183482)},
    'appl_tplay: at half speed, a top byte on its records':
        {BENCH: (71830, 62116), SHIPPED: (71830, 62782)},
}
PRICED = {
    "opcode 11, as aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)":
        Priced((14224, 21466), (428, 668), 1, (1, 1139762, 278034)),   # 0.66 / 0.64
    'opcode 24, as aes_ev_timer, a time of five ticks, blocked; run out by them':
        Priced((12144, 18160), (1056, 1518), 1, (0, 0, 0)),   # 0.67 / 0.70
    'opcode 71, as aes_gr_dragbox, held at the mouse; moved, then released':
        Priced((72308, 100982), (30710, 39158), 4, (0, 0, 0)),   # 0.72 / 0.78
    'opcode 25, as aes_ev_multi, blocked and woken — a release wakes: the button up, which is down':
        Priced((16702, 24916), (622, 996), 1, (0, 0, 0)),   # 0.67 / 0.62
    'marshalled: appl_exit: no accessory, the pipe empty':
        Priced((6196, 9564), (5762, 8814), 2, (0, 0, 0)),   # 0.65 / 0.65
    'opcode 14, as aes_ap_tplay, none of four records played: a count of 0':
        Priced((4402, 6072), None, None, (0, 0, 0)),   # 0.72
    'opcode 25, as aes_ev_multi, blocked and woken — a key wakes: a key, none queued':
        Priced((15292, 22700), (622, 996), 1, (0, 0, 0)),   # 0.67 / 0.62
    'opcode 75, as aes_gr_watchbox, blocked three times: the mouse in, out again, then the rise: 0':
        Priced((90684, 135282), (23876, 36888), 4, (0, 0, 0)),   # 0.67 / 0.65
    'opcode 25, as aes_ev_multi, blocked and woken — leaving wakes: two rectangles':
        Priced((26730, 38520), (622, 996), 1, (0, 0, 0)),   # 0.69 / 0.62
    'opcode 14, as aes_ap_tplay, a wait and a press played: no mouse record':
        Priced((26990, 37898), (15634, 20856), 2, (0, 0, 0)),   # 0.71 / 0.75
    'opcode 25, as aes_ev_multi, blocked and woken — the ticks wake: a message and a timer':
        Priced((19168, 28520), (646, 1060), 1, (0, 0, 0)),   # 0.67 / 0.61
    'opcode 76, as aes_gr_slidebox, the elevator held; dragged down, then released':
        Priced((75240, 107204), (33642, 45380), 4, (0, 0, 0)),   # 0.70 / 0.74
    'opcode 25, as aes_ev_multi, blocked and woken — entering wakes: the second rectangle alone':
        Priced((20408, 28416), (622, 996), 1, (0, 0, 0)),   # 0.72 / 0.62
    "opcode 15, as aes_ap_trecd, one record, a key's":
        Priced((17014, 26110), (1858, 3484), 1, (0, 0, 0)),   # 0.65 / 0.53
    'opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe':
        Priced((17946, 26024), (622, 996), 1, (1, 1139762, 278034)),   # 0.69 / 0.62
    "opcode 107, as aes_wm_update, the lock handed to the screen manager, which waits for it: a yield inside unsync's call":
        Priced((5334, 8404), (510, 1052), 1, (0, 0, 0)),   # 0.63 / 0.48
    'appl_exit: no accessory, the pipe empty':
        Priced((5190, 8294), (4756, 7544), 2, (0, 0, 0)),   # 0.63 / 0.63
    'opcode 20, as aes_ev_keybd, no key queued, blocked; woken by Return':
        Priced((11444, 18046), (398, 900), 1, (0, 0, 0)),   # 0.63 / 0.44
    'opcode 50, as aes_fm_do, nothing typed: the first wait blocked; woken by Return':
        Priced((76780, 116356), (55946, 83182), 5, (0, 0, 0)),   # 0.66 / 0.67
    'opcode 15, as aes_ap_trecd, a count of 0, ended at once: nothing recorded':
        Priced((16320, 25242), (1702, 3246), 1, (0, 0, 0)),   # 0.65 / 0.52
    'appl_exit: a message left in the pipe, read away':
        Priced((10588, 17314), (4882, 7784), 3, (0, 0, 0)),   # 0.61 / 0.63
    'opcode 21, as aes_ev_button, a press waited for, blocked; woken by it':
        Priced((13682, 21316), (414, 674), 1, (0, 0, 0)),   # 0.64 / 0.61
    'opcode 52, as aes_fm_alert, no button the default: Return taken, the next wait blocked; the second button clicked while it waits':
        Priced((189876, 295286), (136762, 213046), 10, (0, 0, 0)),   # 0.64 / 0.64
    'opcode 21, as aes_ev_button, a double click waited for, blocked; woken by the two presses':
        Priced((13772, 21380), (414, 674), 1, (0, 0, 0)),   # 0.64 / 0.61
    "appl_exit: two accessories told to close, the caller's own message read away":
        Priced((22498, 37784), (6130, 9780), 5, (0, 0, 0)),   # 0.60 / 0.63
    'opcode 22, as aes_ev_mouse, the mouse in the rectangle it is to leave, blocked; woken by its leaving':
        Priced((16526, 23770), (758, 1584), 1, (0, 0, 0)),   # 0.70 / 0.48
    'opcode 56, as aes_fm_button, the button held down, OK not under the mouse: the watch blocked; woken by the rise':
        Priced((43624, 66878), (15854, 24188), 3, (0, 0, 0)),   # 0.65 / 0.66
    'opcode 25, as aes_ev_multi, blocked and woken — the ticks wake: a timer':
        Priced((15842, 22758), (646, 1060), 1, (0, 0, 0)),   # 0.70 / 0.61
    'marshalled: opcode 20, as aes_ev_keybd, no key queued, blocked; woken by Return':
        Priced((12450, 19316), (1404, 2170), 1, (0, 0, 0)),   # 0.64 / 0.65
    "opcode 23, as aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)":
        Priced((14332, 21806), (536, 1008), 1, (1, 1139762, 278034)),   # 0.66 / 0.53
    'opcode 70, as aes_gr_rubbox, the corner at the mouse; stretched, then released':
        Priced((71898, 100378), (30300, 38554), 4, (0, 0, 0)),   # 0.72 / 0.79
    'opcode 25, as aes_ev_multi, blocked and woken — a double click wakes: a double click':
        Priced((17498, 25988), (622, 996), 1, (0, 0, 0)),   # 0.67 / 0.62
    'marshalled: opcode 25, as aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe':
        Priced((19964, 28550), (2640, 3522), 1, (1, 1139762, 278034)),   # 0.70 / 0.75
    'appl_tplay: at half speed, a top byte on its records':
        Priced((27180, 38020), (15826, 20980), 2, (0, 0, 0)),   # 0.71 / 0.75
}
# @PINS-END

WINDOWS = {label: priced.windows for label, priced in PRICED.items() if priced.windows != NO_WINDOW}
# The one foreign window these rows have: the screen manager's menu chain, which writes the message a blocked read
# waits for — the ROM's own run of the other process, on both shores.
THE_MENU_CHAIN_S_TURN = (1, 1139762, 278034)
# WHO HOLDS WHICH. A DOOR USER'S wake (`SwitchingRow.door`) is held on both blobs and in the table by the door users'
# own three tests (`test_tier3.py`, which pins every door user that switches under its registered name: the two
# tables below are this battery's rows, handed there). The EVENT LAYER'S OWN arms' wakes are held here.
A_DOOR_USER_S = tuple(label for label, row in SWITCHING.items() if row.door)
THE_LAYER_S_OWN = tuple(label for label, row in SWITCHING.items() if not row.door)
DOOR_USERS_PRICED = {switching.row_name(SWITCHING[label]): tuple(PRICED[label]) for label in A_DOOR_USER_S}
DOOR_USERS_WHOLE_RUN = {switching.row_name(SWITCHING[label]): WHOLE_RUN[label] for label in A_DOOR_USER_S}


def test_every_row_that_switches_is_registered_and_pinned():
    assert REGISTERED_SWITCHING.keys() == SWITCHING.keys() == WHOLE_RUN.keys() == PRICED.keys()
    assert len(set(REGISTERED)) == len(REGISTERED) and all(case.registered_case(name) for name in REGISTERED)
    assert {switching.row_name(row) for row in SWITCHING.values()} <= set(aes_event.SWITCHING_ROWS)
    assert set(WINDOWS.values()) == {THE_MENU_CHAIN_S_TURN} and all("write" in label for label in WINDOWS)
    assert A_DOOR_USER_S and THE_LAYER_S_OWN and all(g.style_of(g.call_of(_name_of(label)).call.opcode) == g.LAYER
                                                     for label in THE_LAYER_S_OWN)


def _premise(row):
    """What the ROM's own run of `row` IS (`aes_switching.Premise`), read off that run: what a blob's run is held to."""
    made = switching.settled(row)
    the_rom_s = switching.scheduled(row, made.pokes)
    answer = the_rom_s.d0 & aes.WORD_MASK if row.answered else None
    return switching.Premise(tuple(sorted(the_rom_s.delivered)), the_rom_s.idles, made.switches.process,
                             tuple(the_rom_s.entered), answer, tuple(sorted(the_rom_s.at_polls)))


@pytest.mark.parametrize("label", THE_LAYER_S_OWN)
def test_a_wake_really_switches_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH (`aes_switching.vet_on_a_blob`): our switch, its arm and the arm's
    routine through OUR dsptch, disp, savestate and switchto, and back into GCC's frame — the marshal's copies live
    in it across the wait. The image the ROM's but for the row's drops; the idles, the polls and the processes
    entered the ROM's own run's; the whole run's cycles pinned; another process's turn the ROM's, to the cycle."""
    row = SWITCHING[label]
    switching.vet_the_premise(row, _premise(row))
    switching.vet_on_a_blob(blob, row, _premise(row), WINDOWS.get(label, NO_WINDOW), WHOLE_RUN[label])


@pytest.mark.parametrize("label", THE_LAYER_S_OWN)
def test_the_table_prices_a_wake_on_both_counts(label):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's own cycles on each shore and — where
    the run calls a rebound entry — the caller's own, both pinned, both under the bar."""
    switching.vet_the_table_s_price(SWITCHING[label], PRICED[label])


# ---- THE COUNTS -------------------------------------------------------------------------------------------------------------------
COUNTED = {each.label: each for each in g.COUNTS}


@pytest.mark.parametrize("label", COUNTED)
def test_a_count_past_its_array_inside_the_frame_is_the_rom_s_own(label):
    """TIER 1 OF THE MARSHAL'S COPIES where the control's counts are not its arrays': the whole image, the program's
    arrays among it — a word copied past int_in's sixteen IS the opcode, the counts, and the C's frame is the ROM's."""
    lift, counts = g.counted(label)
    g.run(lift, MARSHAL, counts)


def _counted(label):
    lift, counts = g.counted(label)
    return lift, g.run(lift, MARSHAL, counts)


THE_MODEL_ABOVE_OUR_FRAME = range(g.OUR_FRAME_AT + g.FRAME_BYTES, g.OUR_FRAME_AT + aes.HOST_SLOTS["HOST_SLOT_AES_MARSHAL_FRAME_BYTES"])
A_CALLER_S_OWN = bytes(range(0xA0, 0xA0 + len(THE_MODEL_ABOVE_OUR_FRAME)))     # sixteen bytes, each its own


@pytest.mark.parametrize("label", COUNTED)
def test_no_copy_inside_the_frame_stores_past_it(label):
    """WHAT THE HOST'S DIFFERENTIAL CANNOT SEE, ASKED OF THE C ITSELF: the stack band is dropped on both shores, so a
    copy one word too long — into the words above the frame, a caller's — would pass every case above. The C in a
    fork, its image read back: the sixteen bytes above its frame are as they were staged, on every count. (On
    target those bytes are GCC's saved A6 and return address: the three largest of these counts are rows, so both
    blobs run them and come back.)"""
    lift, counts = g.counted(label)
    arguments, pokes = g.staged(lift, MARSHAL, counts)
    pokes = merge_pokes(pokes, {THE_MODEL_ABOVE_OUR_FRAME.start: A_CALLER_S_OWN})
    forked = aes_event.core_in_a_fork(MARSHAL, arguments, pokes, read_back=True,
                                      hook=aes_event.door_hook(True, g.walked()) if g.style(lift) == g.DOOR else None)
    assert forked.returncode == 0, forked.stderr
    assert bytes(forked.image[at] for at in THE_MODEL_ABOVE_OUR_FRAME) == A_CALLER_S_OWN


def test_the_three_largest_counts_inside_the_frame_are_rows():
    assert {f"aes_marshal, marshalled: {label}" for label in g.PRICED_COUNTS} <= set(REGISTERED)
    assert [g.counted(label)[1] for label in g.PRICED_COUNTS] == [(g.INT_IN_ROOM, 1, 0), (0, 1, g.ADDR_IN_ROOM // 2),
                                                                  (16, g.INT_OUT_ROOM, 0)]


def test_the_seventeenth_word_of_int_in_is_the_opcode():
    """A ROM BEHAVIOUR, KEPT: the control says graf_handle with 17 words of int_in; the seventeenth lands on the
    copied control's first word, and the switch is called with IT — graf_mkstate, whose -1 and four answers come
    back."""
    _lift, result = _counted(g.SEVENTEENTH_IS_THE_OPCODE)
    answers = g.int_out(result.final, 5)
    assert answers[0] == GEMSUPER["GRAF_MKSTATE_ANSWER"] and g.STALE not in [word & aes.WORD_MASK for word in answers]


def test_the_nineteenth_word_of_int_in_is_int_out_s_count():
    """...and the nineteenth is how many answer words go back: the control asked for ONE, five came."""
    _lift, result = _counted(g.NINETEENTH_IS_INT_OUT_S_COUNT)
    answers = [word & aes.WORD_MASK for word in g.int_out(result.final, 6)]
    assert g.STALE not in answers[:5] and answers[5] == g.STALE


def test_the_twentieth_word_of_int_in_is_addr_in_s_count():
    """...and the twentieth how many longwords of addr_in are copied — read AFTER int_in's copy: the control said
    none, and scrp_read (the seventeenth word's opcode) is handed the program's buffer."""
    _lift, result = _counted(g.TWENTIETH_IS_ADDR_IN_S_COUNT)
    scrap = aes.header_constants("aes.h")["AES_SCRAP_PATH"]
    copied = result.after(g.TEXT_AT, g.TEXT_ROOM)
    assert copied != g.STALE_TEXT[g.TEXT_AT] and copied.split(b"\0")[0] == result.after(scrap, g.TEXT_ROOM).split(b"\0")[0]


def test_a_third_longword_of_addr_in_lands_in_the_answer_words():
    """addr_in's array is two longwords: a third is copied over int_out[0..1] — the first then the switch's answer,
    the second handed back as it came."""
    _lift, result = _counted(g.THIRD_LONG_IN_THE_ANSWERS)
    assert g.int_out(result.final, 2)[1] & aes.WORD_MASK == g.TWO_TELLING_LONGS[1] & aes.WORD_MASK


def test_a_fourteenth_longword_of_addr_in_is_the_opcode():
    """...and the fourteenth reaches the copied control: its low word is the opcode — the control said appl_find."""
    _lift, result = _counted(g.FOURTEENTH_LONG_IS_THE_OPCODE)
    assert g.int_out(result.final, 1) == [GEMSUPER["GRAF_MKSTATE_ANSWER"]]


def test_a_fifteenth_longword_of_addr_in_is_int_out_s_count():
    """...and the fifteenth — the last the frame has room for — the copied counts: the control asked ONE answer
    word back, the fifteenth longword's low word says five, and graf_mkstate's five come."""
    _lift, result = _counted(g.FIFTEENTH_LONG_IS_INT_OUT_S_COUNT)
    answers = [word & aes.WORD_MASK for word in g.int_out(result.final, 6)]
    assert g.STALE not in answers[:5] and answers[5] == g.STALE and aes.signed(answers[0]) == GEMSUPER["GRAF_MKSTATE_ANSWER"]


def test_addr_out_is_written_by_the_copied_opcode_not_the_program_s():
    """`$fe658c cmpi.w #112,-8(a6)`: the marshal stores rsrc_gaddr's address through addr_out where THE COPIED
    opcode is 112 — read again after the copies. A control that says rsrc_gaddr with a seventeenth word of int_in
    is graf_handle's call by then, and addr_out is left as the program had it."""
    _lift, result = _counted(g.ADDR_OUT_BY_THE_COPIED_OPCODE)
    assert case.long_in(result.final, g.ADDR_OUT_AT) == g.STALE_LONG
    assert g.int_out(result.final, 1) == [case.word_in(result.final, aes.header_constants("gsx.h")["AES_GL_HANDLE"])]


def test_twenty_seven_words_of_int_out_hand_the_program_its_int_in_and_control_back():
    """int_out's array is seven words: asked for 27, the copy back runs on through the copied int_in and the copied
    control — the frame's top."""
    lift, result = _counted(g.INT_IN_COMES_BACK)
    back = [word & aes.WORD_MASK for word in g.int_out(result.final, 28)]
    control = struct.unpack(">4H", g.control_of(lift.call, (16, 27, 0))[:8])
    assert tuple(back[7:23]) == g.SIXTEEN_WORDS and tuple(back[23:27]) == control and back[27] == g.STALE


def test_no_word_of_int_out_asked_back_leaves_the_program_s_alone():
    _lift, result = _counted(g.NOTHING_ASKED_BACK)
    assert [word & aes.WORD_MASK for word in g.int_out(result.final, 2)] == [g.STALE, g.STALE]


def test_addr_in_s_count_is_doubled_in_a_word():
    """`$fe6528 lsl.w #1`: a count of $8001 copies ONE longword (appl_find finds the name it was handed), and $8000
    none at all — the arm then reads the frame's own unset longword, and finds nobody of that name."""
    _lift, one = _counted(g.A_COUNT_DOUBLED_IN_A_WORD)
    _lift, none = _counted(g.A_COUNT_DOUBLED_TO_NOTHING)
    pd_name_missing = aes.header_constants("pdpipe.h")["AP_FIND_NONE"]
    assert g.int_out(one.final, 1) != [pd_name_missing] and g.int_out(none.final, 1) == [pd_name_missing]


OUR_COPIED_CONTROL = range(g.OUR_FRAME_AT + GEMSUPER["MARSHAL_CONTROL"], g.OUR_FRAME_AT + g.FRAME_BYTES)
OUR_FRAME = range(g.OUR_FRAME_AT, g.OUR_FRAME_AT + g.FRAME_BYTES)


@pytest.mark.parametrize("label", g.PAST_THE_FRAME)
def test_a_copy_past_the_frame_is_refused_by_name_before_a_byte_of_it_moves(label):
    """PAST THE FRAME a copy IN would store over the saved A6 and the return address the ROM then returns through: no
    C has that frame, and the marshal halts by name (`recreate_not_reconstructed`: `trap #7` on target) BEFORE THE
    COPY — read back from the fork's image, nothing has moved but the copied control (on target a count of 65,535
    words would have copied 128 KB over the stack first). The copy BACK past the host slot's model is refused off
    target alone, after the switch has run: nothing outside the frame has moved, the program's int_out least of all."""
    call, counts, words = g.PAST_THE_FRAME[label]
    arguments, pokes = g.at_the_marshal(call, g.call_of(g.THE_DESK_RUNNING).machine(), counts)
    forked = aes_event.core_in_a_fork(MARSHAL, arguments, pokes, read_back=True)
    assert forked.returncode != 0 and f"not reconstructed: aes_marshal: {words}" in forked.stderr, forked.stderr
    before = make_image(pokes)
    moved = [at for at in range(len(before)) if before[at] != forked.image[at]]
    may_move = OUR_FRAME if "OFF TARGET" in words else OUR_COPIED_CONTROL
    assert moved and set(moved) <= set(may_move), [hex(at) for at in moved if at not in may_move][:8]


# ---- int_out PAST THE FRAME: reproduced, the words each build's own ------------------------------------------------------------
READ_PAST = {each.label: each for each in g.READ_PAST_THE_FRAME}
SAVED_A6_WORD = g.INT_OUT_ROOM           # the first word of int_out past the frame's twenty-seven


def _longs_back(image, count):
    """The longwords the program's int_out holds past the frame's twenty-seven words, of `count` words copied back."""
    back = [word & aes.WORD_MASK for word in g.int_out(image, count)]
    return [aes.words_long(*back[at:at + 2]) for at in range(g.INT_OUT_ROOM, count - 1, 2)]


@pytest.mark.parametrize("label", READ_PAST)
def test_int_out_past_the_frame_is_copied_back_as_the_rom_s_is(label):
    """TIER 1 OF THE COPY BACK PAST THE FRAME — THE LABELLED ARGUMENT CLASS (`aes_gemsuper.ARGUMENT_CLASS_CALLER`: the
    host slot's model of a caller's words, staged as the ROM's own frame has them on this case): the ROM hands the
    program the A6 it was entered with, its return address and its argument — the parameter block's address — and
    RETURNS, and so does the C, the whole image the ROM's."""
    assert g.ARGUMENT_CLASS_CALLER.startswith("ARGUMENT CLASS")
    lift, counts = g.counted(label)
    result = g.run(lift, MARSHAL, counts, onto=g.a_caller_s_words(*g.staged(lift, MARSHAL, counts)))
    words_back = counts[1]
    back = [word & aes.WORD_MASK for word in g.int_out(result.final, words_back + 1)]
    assert back[words_back] == g.STALE and back[SAVED_A6_WORD] == aes.high_word(g.A_CASE_S_A6)
    if words_back == g.HOST_INT_OUT_ROOM:
        assert _longs_back(result.final, words_back)[:3] == [g.A_CASE_S_A6, emu.SENTINEL, g.BLOCK_AT]


# What the door users' census (`test_tier3.py`) reads of those two rows' drops: `{the kind: {the core: its rows}}`.
PAST_THE_FRAME_CENSUS = {
    g.THE_SAVED_A6_S.split(":")[0]: {"aes_marshal": 2},        # both rows reach the saved A6
    g.THE_ARGUMENTS_.split(":")[0]: {"aes_marshal": 1},        # the longer one the words of the arguments
}


def test_the_two_rows_that_read_past_the_frame_are_priced_with_their_drops():
    tier3 = bench_tier3()
    for label, drops in g.PAST_THE_FRAME_DROPS.items():
        row = tier3.row_named(("aes_marshal", f"marshalled: {label}"))
        assert set(drops) <= set(row.dropped), label


@pytest.mark.parametrize("label", g.PAST_THE_FRAME_DROPS)
def test_on_a_blob_the_words_past_the_frame_are_our_build_s_own(label, blob):
    """WHAT THE DROPS EXCUSE, VETTED ON EACH BLOB (the row's own second differential compares every other byte): past
    the frame's twenty-seven words our build hands the program ITS caller's A6 (the bench's seed), ITS return
    address (the bench's sentinel: compared, not dropped — the ROM's run returns to the same), the image pointer
    GCC's frame has before the argument, and then the parameter block's address — where the ROM's frame has the
    block's address straight after the return address."""
    row = bench_tier3().row_named(("aes_marshal", f"marshalled: {label}"))
    ours = blob._call(make_image(row.pokes), row.symbol, row.args).image
    words_back = READ_PAST[label].counts[1]
    back = [word & aes.WORD_MASK for word in g.int_out(ours, words_back + 1)]
    our_caller_s_a6 = asm_twin.CALLEE_SAVED_SEEDS["a6"]
    assert back[words_back] == g.STALE and back[SAVED_A6_WORD] == aes.high_word(our_caller_s_a6)
    if words_back == g.HOST_INT_OUT_ROOM:
        the_image_pointer = row.args[0]
        assert _longs_back(ours, words_back) == [our_caller_s_a6, emu.SENTINEL, the_image_pointer, g.BLOCK_AT]
        assert the_image_pointer == 0 and row.args[1] == g.BLOCK_AT


A_FRAME_POINTER = 0x00070ACE            # what the program's int_in[20..21] make the ROM's A6
A_PLACE_TO_RETURN_TO = addrs.AES_ROM_JUSTRETF      # ...and its int_in[22..23] the address the ROM returns to


def test_the_rom_returns_through_the_program_s_own_words_past_twenty_two():
    """THE OVERRUN, SHOWN ON THE ROM (what the C refuses above): 24 words of int_in. Words 21-22 land on the marshal's
    saved A6 and words 23-24 on its return address — and the ROM's marshal, its switch run and its answer copied
    back, `unlk`s into the first and RETURNS TO THE SECOND: an address of the program's choosing, in supervisor
    mode."""
    words = (*g.SIXTEEN_WORDS, g.GRAF_HANDLE, 24, 5, 0, aes.high_word(A_FRAME_POINTER), A_FRAME_POINTER & aes.WORD_MASK,
             aes.high_word(A_PLACE_TO_RETURN_TO), A_PLACE_TO_RETURN_TO & aes.WORD_MASK)
    arguments, pokes = g.at_the_marshal(g.Call(g.GRAF_HANDLE, words), g.call_of(g.THE_DESK_RUNNING).machine(), (24, 5, 0))
    image = make_image(aes.staged(MARSHAL, arguments, pokes))
    final, _writes, registers = emu.run(image, addrs.AES_ROM_MARSHAL, stop_pc=A_PLACE_TO_RETURN_TO)
    assert registers["checkpoint"], "the ROM's marshal did not return to the address int_in[22..23] name"
    assert registers["a6"] == A_FRAME_POINTER
    assert g.int_out(final, 5)[1:] == [case.word_in(final, at) for at in (
        aes.AES_GL_WCHAR, aes.AES_GL_HCHAR, aes.header_constants("gsxif.h")["AES_GL_WBOX"], aes.AES_GL_HBOX)]


def test_the_rom_hands_back_its_saved_a6_and_return_address_past_twenty_seven():
    """...and 31 words of int_out, read back on the ROM: after the copied control come the A6 the marshal was entered
    with and the address it returns to — the supervisor stack's own, handed to the program."""
    arguments, pokes = g.at_the_marshal(g.Call(g.GRAF_HANDLE), g.call_of(g.THE_DESK_RUNNING).machine(), (0, 31, 0))
    image = make_image(aes.staged(MARSHAL, arguments, pokes))
    final, _writes, registers = emu.run(image, addrs.AES_ROM_MARSHAL, {"a6": A_FRAME_POINTER})
    back = [word & aes.WORD_MASK for word in g.int_out(final, 32)]
    assert back[27:31] == [aes.high_word(A_FRAME_POINTER), A_FRAME_POINTER & aes.WORD_MASK,
                           aes.high_word(emu.SENTINEL), emu.SENTINEL & aes.WORD_MASK] and back[31] == g.STALE


# ---- WHAT AN ARM DOES NOT SET -------------------------------------------------------------------------------------------------------
STALE_ANSWERS = (0x0BAD, 0x0CAB, 0x0DAD)
WF_TOP_S = "opcode 104, as aes_wm_get, WF_TOP"


def test_answer_words_an_arm_does_not_write_come_back_as_the_stack_held_them():
    """A ROM BEHAVIOUR, KEPT — THE LABELLED ARGUMENT CLASS (`aes_gemsuper.ARGUMENT_CLASS`: the frame's stale words are
    staged, on both shores): wind_get(WF_TOP) writes ONE answer word, the binding asks five back, and the marshal's
    int_out is never cleared — the program's int_out[2..4] are whatever the supervisor stack held under the call.
    WHAT THIS IS NOT: coverage of the stale values themselves. No ROM run made them; the case stages three words to
    show that the marshal copies back what it finds — which words a real call finds there is its history's."""
    assert g.ARGUMENT_CLASS.startswith("ARGUMENT CLASS")
    lift = RETURNING[WF_TOP_S]
    stale = g.stack_left(GEMSUPER["MARSHAL_INT_OUT"] + 2 * WORD, g.words(*STALE_ANSWERS))
    result = g.run(lift, MARSHAL, onto=stale)
    assert lift.call.int_out == 5 and tuple(word & aes.WORD_MASK for word in g.int_out(result.final, 5)[2:]) == STALE_ANSWERS


AN_UNSET_TIMER = 0x0BADF00D
NO_TIMER_S = f"opcode {addrs.AES_ROM_EV_MULTI_OPCODE}, as {g.THE_NO_TIMER_S}"


def test_evnt_multi_without_a_timer_hands_ev_multi_a_local_the_rom_never_set():
    """A ROM BEHAVIOUR, NOT REPRODUCED AND HARMLESS: the arm builds ev_multi's timer in -4(a6) only where the flags
    ask for one (`$fe5ec6 btst #5` / `beq`) and pushes that local either way — unset, whatever the stack held. ev_multi
    reads it under MU_TIMER alone. Shown on the ROM (the local staged, the frame it hands ev_multi read back); the C
    hands EVNT_MULTI_NO_TIMER, which is what the ROM's hands over a stack never used — every other case of the arm."""
    lift = RETURNING[NO_TIMER_S]
    arguments, pokes = g.staged(lift)
    assert not lift.call.int_in[0] & aes.EV_MU_TIMER
    the_switch_s_local = abi.FIRST_ARG - LONG - LONG - LONG      # the return address, the saved A6, then -4(a6)
    handed = aes_event.rom_handed(DISPATCH, arguments, merge_pokes(pokes, {the_switch_s_local: g.longs(AN_UNSET_TIMER)}))
    clean = aes_event.rom_handed(DISPATCH, arguments, pokes)
    timer_at = 3                        # ev_multi's frame: flags, two rectangles, the timer
    assert [call.arguments[timer_at] for call in handed] == [AN_UNSET_TIMER]
    assert [call.arguments[timer_at] for call in clean] == [GEMSUPER["EVNT_MULTI_NO_TIMER"]]
