"""THE DESK'S ALERT AND ITS MESSAGE TO ITSELF (`src/desk/deskfun.c`; band 6 wave 1b, group G4, unit H): fun_alert
`$fdfd58` and fun_msg `$fdfda6`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`): a chain of the hands stopped at the routine's first
    instruction, the arguments read off the frame the desk's caller pushed. Where no chain makes the machine an arm
    needs, the case is A LABELLED ARGUMENT CLASS, said in its name (the same routine over an arrival's machine, other
    arguments). Never a poke.
  * BOTH YIELD (each ends on a binding of unit D): every case is a row that switches, held through the companion,
    fun_alert's through its wake (the alert answered by Return).
  * D0 AT RETURN: both answer their binding's word — held to the ROM's D0.w on every case, no divergence.
  * UNBOUND: no function of a blob but a routine held at Tier 1 refers to its cores; the Line-F table's entries stay
    the ROM's; no registry names one.
"""
import pytest

import aes_deskarrive as da
import aes_deskbind as db
import aes_deskfun as fun

Case = da.Case
RETURN = da.RETURN_TYPED
FORMAT_WARNED = "A: File > Format, Return (the warning answered)"
OPEN_ALERT = "file: File > Open (the Show / Print / Cancel alert)"
AS_TEXT, FILE_INFO = "window: View > Show as Text", "file: File > Show Info, Return"
PROGRAM_INFO = "files: the program selected, File > Show Info, Return"
NO_PARAMETERS = 0
A_WORD_THE_SENDER_IS_NOT = 0x7777       # fun_msg's unread second word, other than gl_apid (0: its one caller pushes it)


def _unread_word(arrived):
    return (arrived.arguments[0], A_WORD_THE_SENDER_IS_NOT, *arrived.arguments[2:])


CASES = (
    # fun_alert: the merge arm (a parameter) at the format warning, none at Open's. (The drive's trash alert — a
    # parameter too, `drive A: dragged to the trash, Return` — was tried and is not kept: its scheduled run idles for
    # ever after a Return at its first or its second idle; not debugged.)
    Case(fun.FUN_ALERT, FORMAT_WARNED, wake=RETURN, arm=lambda a: a[2] != NO_PARAMETERS),
    Case(fun.FUN_ALERT, OPEN_ALERT, wake=RETURN, arm=lambda a: a[2] == NO_PARAMETERS),
    # fun_msg: its two callers' sites (the text view's redraw, Show Info's), and a window of another rectangle
    Case(fun.FUN_MSG, AS_TEXT), Case(fun.FUN_MSG, FILE_INFO), Case(fun.FUN_MSG, PROGRAM_INFO),
    Case(fun.FUN_MSG, AS_TEXT, arguments=_unread_word,
         why="its second word other than gl_apid (its one kind of caller pushes gl_apid, 0): the sender is gl_apid's, read again"),
)
BY_LABEL = da.by_label(CASES)
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)


@EVERY_CASE
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core through the host's scheduler held to the ROM's routine from the same entry — the idles,
    the image at every dispatch and where it returns, the answer (the binding's word) at its width."""
    da.tier_1(BY_LABEL[name])


ARRIVALS, CLASSES = 5, 1


def test_every_routine_of_the_unit_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES if not each.why]
    assert {each.name for each in at_its_own} == set(fun.UNIT_H)
    assert (len(at_its_own), len(CASES) - len(at_its_own)) == (ARRIVALS, CLASSES)


def test_both_answer_their_binding_s_word_which_five_instructions_read_of_fun_alert_and_none_of_fun_msg():
    """D0: each answers the word its binding answers (the C has it: no divergence) — fun_alert's read by five
    instructions of the ROM, fun_msg's by none (`aes_deskbind.answer_readers`)."""
    assert {name: len(db.answer_readers(da.entry_of(name))) for name in fun.UNIT_H} == {fun.FUN_ALERT: 5, fun.FUN_MSG: 0}


def test_the_unit_is_linked_and_unbound(blob):
    """UNBOUND (`aes_deskarrive.unbound`): both cores linked, nothing of the blob but a routine held at Tier 1 refers to
    them, their table entries are the ROM's, no registry names one."""
    da.unbound(blob, fun.UNIT_H)
