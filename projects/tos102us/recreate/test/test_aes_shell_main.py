"""sh_main `$feb0e6` (`src/aes/shell.c`): THE SHELL'S LOOP — what gem_main runs once GEM is up.

    sh_main():  ad_pfile = band[2].ob_spec;  sh_isgem = gl_shgem = sh_isdef = sh_doexec = sh_dodef = 1;
                do {
                    $c93c = 0;  if (sh_isdef) { sh_isgem = 1; $c93c = 1; }   sh_isdef = 1;
                    if (sh_isgem != gl_shgem) { gl_shgem = sh_isgem;  gl_shgem ? sh_tographic() : sh_toalpha(); }
                    if (gl_shgem) { wm_start(); ratinit(); }
                    if ($c890)          the cartridge's program (NOT RECONSTRUCTED: halts by name)
                    else if (sh_dodef)  { desk_alloc(); answer = deskmain(); gl_bpend = 0; desk_free();
                                          if (Getrez() != 2 && != 4) band[0].ob_spec = $1173;
                                          if (answer) sh_dodef = 0; else sh_doexec = 0; }
                    else if (sh_cmd())  sh_dodef = 1;
                    else { sh_draw(command, 0, 1);  sh_dodef = 1;
                           if (sh_find(command, sh_show)) { pd_nameit(rlr, sh_name(command)); dos_exec(command, 0, tail);
                                                            if (gl_shgem && DOS_ERR && DOS_AX < -32) fm_error(~DOS_AX - 30); }
                           else fm_error(2); }
                } while (sh_doexec);

EVERY RUN HERE RETURNS, SO EVERY RUN ENDS WITH A DESK PASS WHOSE DESKMAIN ANSWERS 0 — and a desk pass leaves by the
dispatcher (desk_free's yield, in the desk's rsrc_free binding): each case is A ROW THAT SWITCHES (`aes_switching`),
the C through its own scheduler held to the ROM's scheduled run with NOTHING dropped (`companion`).

WHAT IS ANSWERED, NOT RUN — each a LABELLED ARGUMENT CLASS, in every row's name:
  * DESKMAIN AND THE DESK'S BUILT-INS, at their entry on both shores (`aes_shmain`'s door): what each call was handed
    and found is the door's ledger; what a deskmain that asks for a launch LAYS before it returns is the four words
    the ROM's own shel_write stores (`aes_shmain.asked_words`), the two lines staged in the shell's buffers.
  * GEMDOS, by the recording, scripted trap: the desk's five Mallocs and eight Mfrees, sh_find's search, dos_exec's
    Pexec — NO PROGRAM IS RUN (a real Pexec loads over the blob: the standing limit), its answer is the script's.
  * GETREZ, by a staged trap (`aes_shmain.getrez_pokes`: the scheduler's harness declares no I/O byte).
THE MACHINE is the post-boot snapshot's, PD0 running — the desk up, its blocks standing: a desk pass allocates five
MORE and frees the running desk's own two and its resource (`test_aes_deskmem.py`'s argument class). sh_main's own
arrival — the boot's, over a THEGLO just cleared — is the our-boot slice's; no machine of today returns from deskmain.

NOT HERE: the blob (the door's `jsr`s are read in `test_aes_shell_door.py`; the rows are the our-boot slice's), the
cartridge's program beyond its halt, and a launch that runs a program.
"""
import functools
from collections import namedtuple

import pytest

from harness import BASE_IMAGE

import aes
import aes_event
import aes_gemdosif as gd
import aes_objdraw as od
import aes_shmain as sm
import aes_switch
import aes_switching as switching
import case
import test_aes_deskmem as deskmem
import test_aes_fmalert as alerts
import test_aes_fmlib as fmlib
import test_aes_gsxif as gsxif
import vdi
from case import merge_pokes

SH_MAIN, SHELL, FM = sm.SH_MAIN, sm.SHELL, alerts.FM
ARGUMENT_CLASS = "ARGUMENT CLASS (deskmain answered at its entry, GEMDOS scripted, Getrez staged)"
SHELL_BUFFER, SHELL_PD = od.SHELL_BUFFER, aes.SHELL_PD
BAND = od.trees()["desktop band"]
ROOT_SPEC_AT = BAND + aes.OB_SPEC
COLOUR_SPEC = SHELL["SH_BAND_COLOUR_SPEC"]
NO_ARGUMENT = sm.NO_ARGUMENT
MALLOC, MFREE, FSETDTA, FSFIRST, PEXEC = sm.MALLOC, sm.MFREE, sm.FSETDTA, sm.FSFIRST, sm.PEXEC
BLOCKS, SIZES = deskmem.BLOCKS, deskmem.SIZES
GEMDOS_OK = 0
EFILNF, ENSMEM = -33, -39
A_PROGRAM = b"A:\\MEG.PRG"
A_PROGRAM_S_TAIL = b" LETTER.DOC"
PD_NAME_AT = SHELL_PD + aes.PD_NAME
PENDING_CLICKS = 5                      # what a deskmain lays in gl_bpend: sh_main clears it after EVERY return

# ---- one pass's GEMDOS, as the script answers it -------------------------------------------------------------------------------
DESK_PASS = (*BLOCKS, *([GEMDOS_OK] * 8))        # desk_alloc's five blocks, desk_free's eight frees
FOUND = (GEMDOS_OK, GEMDOS_OK)                   # sh_find: Fsetdta, then Fsfirst finds the file as given
# ...or finds it nowhere: the three searches of its walk over this machine's environment (as given, at the root, down
# PATH's one element — `test_aes_shell_find.py` has the walk) each refused. EXACTLY three: the script's next answers
# are the next desk pass's blocks.
SEARCHES_OF_THE_WALK = 3
NOT_FOUND_ANYWHERE = (GEMDOS_OK, *([EFILNF] * SEARCHES_OF_THE_WALK))


def launch(pexec):
    return (*FOUND, pexec)


def machine(door, gemdos_, mode=sm.MODES["low"], onto=None):
    """PD0 RUNNING over the snapshot (the scheduler's own machine), the door staged with its script, GEMDOS scripted,
    Getrez answering `mode`; the command line and the tail a launch would be asked with in the shell's buffers, the
    root's colour and the band's text pointer STALE so a store shows."""
    return merge_pokes(aes_event.machine(), gd.STALE_DOS, sm.GEMDOS.pokes(gemdos_), sm.door_pokes(door), sm.getrez_pokes(mode),
                       od.string_pokes(A_PROGRAM, at=SHELL_BUFFER, room=aes.AES_SHELL_LINE_BYTES),
                       {sm.TAIL: sm.tail(len(A_PROGRAM_S_TAIL), A_PROGRAM_S_TAIL).ljust(aes.AES_SHELL_LINE_BYTES, b"\0")},
                       {ROOT_SPEC_AT: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big")},
                       aes.field_pokes("AES", AD_PFILE=vdi.STALE_LONG), onto)


def asks(gem=1, bpend=PENDING_CLICKS):
    """A deskmain that ASKS FOR WHAT THE SHELL'S BUFFERS HOLD: its answer 1, and what it lays first — the four words
    the ROM's own shel_write(1, gem, ...) stores, and clicks left pending."""
    return 1, {**sm.asked_words(gem), sm.BPEND: bpend}


QUITS = (0, {sm.BPEND: PENDING_CLICKS})          # a deskmain that ends the shell, clicks left pending
# `at_idle`: the interrupts the run takes where the machine IDLES — an alert waiting for its answer (a key typed ahead
# is taken by the keyboard's poll at the desk pass's yield, long before any alert waits for one).
Pass = namedtuple("Pass", "door gemdos mode onto at_idle objects budget", defaults=(sm.MODES["low"], None, None, False, None))
RETURN_AT_THE_ALERT = {0: aes_event.key(aes_event.RETURN_KEY)}
# A row whose alert is drawn, run and put back is past the scheduler's default budget: its own, from its measured run
# (320,837 instructions the longest; `aes_event`'s margin is five).
ALERT_ROW_INSNS = 1_700_000
BUILT_IN_TAIL = {sm.TAIL: sm.tail(SHELL["SH_CMD_FORMAT"], b"A:").ljust(aes.AES_SHELL_LINE_BYTES, b"\0")}

THE_DESK_QUITS = "the desk quits at once"
IN_MONOCHROME = "the desk quits, the screen monochrome"
IN_MEDIUM = "the desk quits, medium resolution"
A_BUILT_IN = "the desk asks for a built-in (Format), then quits"
A_GEM_PROGRAM = "the desk asks for a GEM program, which ends well; then quits"
AN_EXIT_CODE = "a GEM program ends with an exit code of 1: no alert"
AT_THE_BOUND = "a GEM program's launch answers -32: no alert"
NOT_LOADED = "a GEM program's launch answers -33 (file not found): fm_error(2), Return"
NO_MEMORY = "a GEM program's launch answers -39 (no memory): fm_error(8), Return"
NOT_FOUND = "the command is found nowhere: fm_error(2), Return"
A_TEXT_PROGRAM = "the desk asks for a program that is not GEM's, whose launch answers -33: the screen switched both ways, no alert"
# A THIRD CLASS: THE DESK'S ANSWER IS TESTED AS A WORD FOR ZERO (`$feb216 tst.w / beq`), not for a positive number — a
# deskmain answering -1 (no desk of the ROM's does) asks for what the buffers hold exactly as one answering 1.
A_NEGATIVE_ANSWER = "the desk answers -1 (a class of its own: no desk does), taken as a request: a GEM program run; then quits"
# TWO MORE CLASSES, each for a word sh_main reads or stores that the rows above cannot tell from its neighbour:
#   * AS A BOOT'S BSS HAS THEM: the four flags and gl_shgem CLEAR where sh_main is entered — gem_main's own arrival
#     finds them so (the capture holds what sh_main's first pass left). Every one of sh_main's five opening stores shows.
#   * A SEARCH WHOSE ANSWER'S WORD IS NEGATIVE AND WHOSE LONG IS NOT ($0000ffd0: no GEMDOS answers it): the glue's
#     word is then below the bound with its verdict CLEAR, and the launch ends well — no alert: the verdict is what
#     sh_main asks first. With GEMDOS's real answers the word a good launch leaves is the search's 0.
FLAGS_CLEAR_AT_ENTRY = "the desk quits at once, the shell's flags clear at its entry (a boot's BSS)"
A_WORD_BELOW_THE_BOUND_AND_NO_ERROR = "a GEM program ends well with the glue's word left at -48 by its search: no alert"
A_SEARCH_S_ANSWER_NO_GEMDOS_GIVES = 0x0000_FFD0
CLEAR_FLAGS = {at: bytes(aes.WORD_BYTES) for at in (*sm.FLAGS, aes.AES_GL_SHGEM)}
PASSES = {
    THE_DESK_QUITS: Pass((QUITS,), DESK_PASS),
    IN_MONOCHROME: Pass((QUITS,), DESK_PASS, sm.MODES["high"]),
    IN_MEDIUM: Pass((QUITS,), DESK_PASS, sm.MODES["medium"]),
    A_BUILT_IN: Pass((asks(), 0, QUITS), (*DESK_PASS, *DESK_PASS), onto=BUILT_IN_TAIL, objects=True),
    A_GEM_PROGRAM: Pass((asks(), QUITS), (*DESK_PASS, *launch(GEMDOS_OK), *DESK_PASS), objects=True),
    AN_EXIT_CODE: Pass((asks(), QUITS), (*DESK_PASS, *launch(1), *DESK_PASS), objects=True),
    AT_THE_BOUND: Pass((asks(), QUITS), (*DESK_PASS, *launch(-32), *DESK_PASS), objects=True),
    NOT_LOADED: Pass((asks(), QUITS), (*DESK_PASS, *launch(EFILNF), *DESK_PASS), at_idle=RETURN_AT_THE_ALERT, objects=True, budget=ALERT_ROW_INSNS),
    NO_MEMORY: Pass((asks(), QUITS), (*DESK_PASS, *launch(ENSMEM), *DESK_PASS), at_idle=RETURN_AT_THE_ALERT, objects=True, budget=ALERT_ROW_INSNS),
    NOT_FOUND: Pass((asks(), QUITS), (*DESK_PASS, *NOT_FOUND_ANYWHERE, *DESK_PASS), at_idle=RETURN_AT_THE_ALERT, objects=True, budget=ALERT_ROW_INSNS),
    FLAGS_CLEAR_AT_ENTRY: Pass((QUITS,), DESK_PASS, onto=CLEAR_FLAGS),
    A_WORD_BELOW_THE_BOUND_AND_NO_ERROR: Pass(
        (asks(), QUITS), (*DESK_PASS, GEMDOS_OK, A_SEARCH_S_ANSWER_NO_GEMDOS_GIVES, GEMDOS_OK, *DESK_PASS), objects=True),
    A_NEGATIVE_ANSWER: Pass(((-1, asks()[1]), QUITS), (*DESK_PASS, *launch(GEMDOS_OK), *DESK_PASS), objects=True),
    A_TEXT_PROGRAM: Pass((asks(gem=0), QUITS), (*DESK_PASS, GEMDOS_OK, *launch(EFILNF), gsxif.SNAPSHOT_BUFFER_AT, *DESK_PASS),
                         objects=True),
}


@functools.cache
def staged(label):
    a_pass = PASSES[label]
    return machine(a_pass.door, a_pass.gemdos, a_pass.mode, a_pass.onto)


def row(label):
    a_pass = PASSES[label]
    door = aes_switch.DoorUser(objects=a_pass.objects, doors=sm.child_doors(a_pass.mode))
    return switching.SwitchingRow(f"{ARGUMENT_CLASS}: {label}", SH_MAIN, (), functools.partial(staged, label),
                                  a_pass.at_idle or {}, answered=False, door=door, budget=a_pass.budget)


@functools.cache
def ran(label):
    """The row's companion: the C through its own scheduler, the ROM's scheduled run, nothing dropped — its image."""
    return switching.companion(row(label))


def words(image, *fields):
    return tuple(case.word_in(image, at) for at in fields)


def door_calls(label):
    return sm.calls(ran(label).image)


def gemdos_calls(label):
    return [function for function, _frame in sm.gemdos_calls(ran(label).image)]


# One label's cases back to back on one worker: its companion is made once per process (`conftest.py`).
pytestmark = pytest.mark.collected_with(by=lambda parameters: parameters.get("label"))
EVERY = pytest.mark.parametrize("label", PASSES)


# ---- the premises -------------------------------------------------------------------------------------------------------------
def test_the_snapshot_is_a_desk_running_with_a_click_pending():
    """THE ROM-RUN STATE every row starts over: the capture's four flags as sh_main's first pass left them, gl_shgem
    set, and gl_bpend NOT zero — so that its clearing shows without a word of ours."""
    assert words(BASE_IMAGE, *sm.FLAGS, aes.AES_GL_SHGEM) == (1, 1, 1, 1, 1)
    assert case.word_in(BASE_IMAGE, sm.BPEND) != 0
    assert case.long_in(BASE_IMAGE, aes.AES_AD_PFILE) == case.long_in(BASE_IMAGE, BAND + SHELL["SH_BAND_TEXT_SPEC"]), (
        "ad_pfile is the band's text object's ob_spec — its TEDINFO, whose first longword is te_ptext")


def test_deskmain_and_sh_main_are_each_called_from_one_site():
    """deskmain by sh_main alone ($feb1dc), sh_main by gem_main alone ($fda398): Line-F words, read off the ROM."""
    (sites,) = aes.line_f_call_sites("AES_ROM_DESKMAIN").values()
    assert sites == (0xFEB1DC,)
    (sites,) = aes.line_f_call_sites(SH_MAIN).values()
    assert sites == (0xFDA398,)


def test_what_a_desk_that_asks_lays_is_what_the_rom_s_shel_write_stores():
    """sh_doexec 1, sh_isgem as asked, sh_dodef and sh_isdef CLEARED — read off the ROM's own run of shel_write."""
    assert sm.asked_words(1) == dict(zip(sm.FLAGS, (1, 1, 0, 0)))
    assert sm.asked_words(0) == dict(zip(sm.FLAGS, (1, 0, 0, 0)))


# ---- every row: the C through its own scheduler is the ROM's run ---------------------------------------------------------------
@EVERY
def test_sh_main_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1, nothing dropped: the same idles and polls, every door call of the event layer handed the same frame,
    every byte outside the run's own stack the ROM's — the desk door's ledger and the GEMDOS ledger among them. And
    HOW IT ENDS, whatever came between: nothing asked any more, the desk next, the screen GEM's, no click pending."""
    made = ran(label)
    assert made.entered and set(made.entered) <= {SHELL_PD, aes.SCREEN_MANAGER_PD}
    assert words(made.image, aes.AES_SH_DOEXEC, aes.AES_SH_DODEF, aes.AES_SH_ISDEF, aes.AES_GL_SHGEM, sm.BPEND) == (0, 1, 1, 1, 0)
    assert case.long_in(made.image, aes.AES_AD_PFILE) == case.long_in(BASE_IMAGE, BAND + SHELL["SH_BAND_TEXT_SPEC"])
    assert door_calls(label)[-1].routine == sm.DESKMAIN and len(door_calls(label)) == len(PASSES[label].door)


# ---- the desk pass ----------------------------------------------------------------------------------------------------------------
def test_the_first_pass_is_the_desk_s__its_memory_taken_before_it_and_freed_after():
    """One call through the door — deskmain, handed nothing, entered with sh_dodef and gl_shgem set — between
    desk_alloc's five Mallocs and desk_free's eight Mfrees; and its answer 0 ends the shell."""
    (call,) = door_calls(THE_DESK_QUITS)
    assert (call.routine, call.first, call.second, call.dodef, call.shgem) == (sm.DESKMAIN, NO_ARGUMENT, NO_ARGUMENT, 1, 1)
    assert gemdos_calls(THE_DESK_QUITS) == [MALLOC] * 5 + [MFREE] * 8
    assert [frame[:4] for _function, frame in sm.gemdos_calls(ran(THE_DESK_QUITS).image)[:5]] == [
        size.to_bytes(4, "big") for size in SIZES]


# An alert's own wait is a multi-click wait: abutton counts it into gl_bpend and evremove takes a count back only
# while more than one stands (`aes/evasync.h`) — so a pass that showed an alert leaves the 1 the capture itself holds.
AN_ALERT_S_WAIT_LEFT = 1


@EVERY
def test_the_pending_clicks_are_cleared_after_every_deskmain(label):
    """BEHAVIOUR (e). Each deskmain here LAYS a count of pending clicks before it returns: whatever is called through
    the door next finds gl_bpend cleared of it — 0, or the one wait an alert shown since then left; never the count
    laid — the first deskmain finds the capture's own, and the run ends with 0."""
    made = door_calls(label)
    assert made[0].bpend == case.word_in(BASE_IMAGE, sm.BPEND)
    left_since = AN_ALERT_S_WAIT_LEFT if PASSES[label].at_idle else 0
    assert [call.bpend for call in made[1:]] == [0] * (len(made) - 2) + [left_since] * (len(made) > 1)
    assert PENDING_CLICKS not in (0, AN_ALERT_S_WAIT_LEFT, AN_ALERT_S_WAIT_LEFT + PENDING_CLICKS)
    assert case.word_in(ran(label).image, sm.BPEND) == 0


@pytest.mark.parametrize("label, coloured", ((THE_DESK_QUITS, True), (IN_MEDIUM, True), (IN_MONOCHROME, False)),
                         ids=("low", "medium", "high"))
def test_the_band_s_root_is_made_the_colour_desktop_s_unless_the_screen_is_monochrome(label, coloured):
    """Getrez 0 and 1: the root's ob_spec := $1173. Getrez 2: left as it was."""
    spec = case.long_in(ran(label).image, ROOT_SPEC_AT)
    assert spec == (COLOUR_SPEC if coloured else vdi.STALE_LONG)


# ---- the desk asks for something ----------------------------------------------------------------------------------------------------
def test_a_built_in_runs_between_two_desk_passes():
    """deskmain answers 1 with a tail whose first byte is Format's: sh_cmd runs it — entered with sh_dodef CLEAR, the
    tail's text and the command line its frame — sh_dodef is set again, and the desk runs once more. No search, no
    Pexec: GEMDOS sees two desk passes and nothing between."""
    first, built_in, last = door_calls(A_BUILT_IN)
    assert (first.routine, first.dodef) == (sm.DESKMAIN, 1)
    assert (built_in.routine, built_in.first, built_in.second, built_in.dodef) == (sm.FORMAT, sm.TAIL_TEXT, SHELL_BUFFER, 0)
    assert (last.routine, last.dodef) == (sm.DESKMAIN, 1)
    assert gemdos_calls(A_BUILT_IN) == ([MALLOC] * 5 + [MFREE] * 8) * 2


def pexec_frames(label):
    return [frame for function, frame in sm.gemdos_calls(ran(label).image) if function == PEXEC]


@pytest.mark.parametrize("label", (A_GEM_PROGRAM, AN_EXIT_CODE, AT_THE_BOUND, NOT_LOADED, NO_MEMORY))
def test_a_program_is_looked_for_named_and_run_between_two_desk_passes(label):
    """deskmain answers 1 and the tail is a program's: sh_find's search (Fsetdta, Fsfirst), the shell's PD named after
    the command's name part, and ONE Pexec — load and go, the command line, the tail, the caller's environment —
    between the two desk passes."""
    assert gemdos_calls(label) == [MALLOC] * 5 + [MFREE] * 8 + [FSETDTA, FSFIRST, PEXEC] + [MALLOC] * 5 + [MFREE] * 8
    assert pexec_frames(label) == [sm.GEMDOS.call(PEXEC, ("w", SHELL["SH_PEXEC_LOAD_AND_GO"]), ("l", SHELL_BUFFER),
                                                  ("l", sm.TAIL), ("l", 0))[1]]
    assert bytes(ran(label).image[PD_NAME_AT:PD_NAME_AT + aes.PD_NAME_BYTES]) == b"MEG     "
    assert [call.routine for call in door_calls(label)] == [sm.DESKMAIN, sm.DESKMAIN]


def alert_shown(label):
    """The alert tree's first message line as the run left it — the capture's own where no alert was built."""
    Final = namedtuple("Final", "final")
    return fmlib.line_of(Final(ran(label).image), fmlib.FIRST_LINE)


SNAPSHOT_LINE = fmlib.line_of(namedtuple("Final", "final")(BASE_IMAGE), fmlib.FIRST_LINE)


def first_line_of(string):
    lines, _buttons = fmlib.sections(alerts.aes_string(string))
    return lines[0]


@pytest.mark.parametrize("label", (A_GEM_PROGRAM, AN_EXIT_CODE, AT_THE_BOUND, A_TEXT_PROGRAM, A_WORD_BELOW_THE_BOUND_AND_NO_ERROR))
def test_a_launch_that_leaves_no_error_below_the_bound_or_is_not_gem_s_shows_no_alert(label):
    """BEHAVIOUR (d), the arms that show nothing: Pexec answered 0; a WORD at or above -32 — a program's exit code
    of 1, and -32 itself, each an "error" by dos_exec's verdict (`aes/gemdosif.h`) —; -33 while the screen is NOT
    GEM's; and a word below the bound with the verdict clear. No alert was built: the tree's line is the capture's."""
    assert alert_shown(label) == SNAPSHOT_LINE


def test_the_glue_s_verdict_is_asked_before_its_word():
    """ARGUMENT CLASS (the search answered `$0000ffd0`, which no GEMDOS answers: its LONG is no error, its WORD is
    -48). The premise, read off the run: the command was found all the same (sh_find asks the verdict), the launch
    was made — and what it left the glue's word at is below the bound."""
    assert gemdos_calls(A_WORD_BELOW_THE_BOUND_AND_NO_ERROR) == [MALLOC] * 5 + [MFREE] * 8 + [FSETDTA, FSFIRST, PEXEC] + [MALLOC] * 5 + [MFREE] * 8
    assert aes.signed(A_SEARCH_S_ANSWER_NO_GEMDOS_GIVES & 0xFFFF) == -48 < SHELL["SH_LAUNCH_ERRORS_BELOW"]


def test_sh_main_sets_its_five_flags_whatever_it_is_entered_with():
    """ARGUMENT CLASS (the four flags and gl_shgem staged CLEAR, as a boot's BSS has them at gem_main's own call).
    The run is the capture's own first pass all the same: the desk at once, entered with sh_dodef and gl_shgem SET —
    and no screen switch on the way (gl_shgem is set with sh_isgem, not copied from it): GEMDOS sees the desk pass
    alone."""
    (call,) = door_calls(FLAGS_CLEAR_AT_ENTRY)
    assert (call.routine, call.dodef, call.shgem) == (sm.DESKMAIN, 1, 1)
    assert gemdos_calls(FLAGS_CLEAR_AT_ENTRY) == [MALLOC] * 5 + [MFREE] * 8


@pytest.mark.parametrize("label, string", ((NOT_LOADED, "FM_ERROR_NOT_FOUND"), (NO_MEMORY, "FM_ERROR_NO_MEMORY"),
                                           (NOT_FOUND, "FM_ERROR_NOT_FOUND")), ids=("-33", "-39", "not found"))
def test_an_error_is_shown_by_fm_error_under_its_ms_dos_number(label, string):
    """BEHAVIOUR (d), the arms that show: a launch's word below -32 while the screen is GEM's is fm_error(~word - 30)
    — -33 is 2, "can't find the folder or file"; -39 is 8, "not enough memory": two words, two alerts — and a command
    sh_find finds nowhere is fm_error(2) with no Pexec at all. Return answers the alert."""
    assert alert_shown(label) == first_line_of(FM[string]) != SNAPSHOT_LINE
    assert first_line_of(FM["FM_ERROR_NOT_FOUND"]) != first_line_of(FM["FM_ERROR_NO_MEMORY"])
    assert len(pexec_frames(label)) == (0 if label == NOT_FOUND else 1)


def test_a_command_found_nowhere_is_searched_for_down_its_whole_walk_and_never_run():
    assert gemdos_calls(NOT_FOUND) == ([MALLOC] * 5 + [MFREE] * 8 + [FSETDTA] + [FSFIRST] * SEARCHES_OF_THE_WALK
                                       + [MALLOC] * 5 + [MFREE] * 8)
    assert bytes(ran(NOT_FOUND).image[PD_NAME_AT:PD_NAME_AT + aes.PD_NAME_BYTES]) == bytes(BASE_IMAGE[PD_NAME_AT:PD_NAME_AT + 8])


def test_a_program_that_is_not_gem_s_gets_the_screen_in_text_and_gem_takes_it_back():
    """THE TWO FLAGS. The desk asks with sh_isgem 0: sh_main copies it into gl_shgem and hands the screen over
    (sh_toalpha: the save buffer freed — one Mfree more), runs the program, and on the next pass — sh_isdef set
    again, so sh_isgem — takes it back (sh_tographic: the buffer allocated again) before the desk: the second
    deskmain is entered with gl_shgem 1."""
    first, last = door_calls(A_TEXT_PROGRAM)
    assert (first.shgem, last.shgem) == (1, 1)
    assert gemdos_calls(A_TEXT_PROGRAM) == ([MALLOC] * 5 + [MFREE] * 8 + [MFREE] + [FSETDTA, FSFIRST, PEXEC] + [MALLOC]
                                            + [MALLOC] * 5 + [MFREE] * 8)
    assert words(ran(A_TEXT_PROGRAM).image, aes.AES_SH_ISGEM, aes.AES_GL_SHGEM, sm.ISDEF_SEEN) == (1, 1, 1)


def test_the_word_of_sh_isdef_is_what_the_last_pass_found():
    """`$c93c`, stored and read by nothing: 1 where the pass found sh_isdef set — every pass after a deskmain that
    asked nothing of the screen, and the first."""
    assert case.word_in(ran(THE_DESK_QUITS).image, sm.ISDEF_SEEN) == 1
    assert case.word_in(ran(A_GEM_PROGRAM).image, sm.ISDEF_SEEN) == 1


# ---- the cartridge's program: NOT RECONSTRUCTED --------------------------------------------------------------------------------------
def test_the_cartridge_s_program_halts_by_name_where_the_rom_would_call_it():
    """RULING W4-R12. With the desk's request for a cartridge's program staged ($c890: ARGUMENT CLASS — no machine
    here has a cartridge), the C makes the two acts before the call — the tail's length byte from its text, the band
    (not drawn: the desk is next) — and HALTS BY NAME at cart_exec, in a child: no door call, no GEMDOS call."""
    text = b"CART.PRG"
    pokes = merge_pokes(machine((), ()), {sm.CART_LAUNCH: b"\0\1", sm.TAIL: bytes([vdi.FILL]) + text + b"\0"})
    returncode, stderr, image = aes_event.refusal(SH_MAIN, pokes, (), bind=aes_event.child_binding(before=sm.CHILD_DOORS))
    assert returncode != 0 and "cart_exec" in stderr and "not reconstructed" in stderr, stderr
    assert image[sm.TAIL] == len(text) and sm.calls(image) == [] and sm.gemdos_calls(image) == []
    assert case.word_in(image, sm.CART_LAUNCH) == 1, "the request is still standing: the arm did not finish"

