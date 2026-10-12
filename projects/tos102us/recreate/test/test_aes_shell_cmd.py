"""sh_cmd `$feb2fc` (`src/aes/shell.c`): the command tail's first byte run as one of the desk's four built-ins.

    sh_cmd():  switch (tail[0]) {                                  the tail's text is at $c42f, the command at *$c79e
                 case $fe: show(text);                                                              break;
                 case $fd: strcpy("PRINTING  ", command); strcat(text, command);
                           sh_draw(command, 0, 1); print(text);                                     break;
                 case $fc: sh_draw(command, 0, 1); format(text, command);                           break;
                 case $fb: sh_draw(command, 0, 1); copy(text, command);                             break;
                 default:  return 0;
               }
               return 1;

THE FOUR ROUTINES ARE BAND 6's (`aes/deskdoor.h`) and ARE ANSWERED AT THEIR ENTRY ON BOTH SHORES, a LABELLED ARGUMENT
CLASS in every case here (`aes_shmain`: the ROM's Line-F call through a staged copy of its call table, ours through
the door's hook) — what each is handed is read off the door's ledger. No case runs a Format.

WHAT REACHES IT: sh_main alone (`$feb22e`), on a pass the desk left a command for — which no boot makes (band 5 wave
4's design, 2.4: NO MACHINE). Here it is run over (a) the snapshot's own state, the desk the one running (sh_dodef
set: sh_draw draws nothing), with a tail staged — an ARGUMENT CLASS — and (b) THE MACHINE THE ROM'S OWN shel_write
LEAVES (`aes_shmain.asked`), sh_dodef cleared as sh_main has it where it calls sh_cmd: the band drawn.

NOT HERE: the blob. On target the door is a `jsr` of the ROM's routine over PD0's stack (`test_aes_shell_door.py` reads
the instructions); its rows are the our-boot slice's.
"""
import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_objdraw as od
import aes_shmain as sm
import case
import test_aes_ob_draw as ob_draw
import vdi
from case import merge_pokes
from test_aes_gsx import screen_changed

SH_CMD = sm.SH_CMD
SHELL = sm.SHELL
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
SHELL_BUFFER = od.SHELL_BUFFER
NO_ARGUMENT = sm.NO_ARGUMENT
TEXT = b"A:\\LETTER.DOC"
PRINTING = b"PRINTING  "
# Each built-in: its command byte, the routine, and the frame the ROM's sh_cmd hands it.
BUILT_INS = {
    "show a file ($fe)": (SHELL["SH_CMD_SHOW"], sm.SHOW_FILE, (sm.TAIL_TEXT, NO_ARGUMENT)),
    "print a file ($fd)": (SHELL["SH_CMD_PRINT"], sm.PRINT_FILE, (sm.TAIL_TEXT, NO_ARGUMENT)),
    "format a disk ($fc)": (SHELL["SH_CMD_FORMAT"], sm.FORMAT, (sm.TAIL_TEXT, SHELL_BUFFER)),
    "copy a disk ($fb)": (SHELL["SH_CMD_COPY"], sm.COPY_DISK, (sm.TAIL_TEXT, SHELL_BUFFER)),
}
DRAWS_THE_BAND = ("print a file ($fd)", "format a disk ($fc)", "copy a disk ($fb)")
A_COMMAND = b"A:\\DESK.CMD"
STALE_BUFFER = od.string_pokes(A_COMMAND, at=SHELL_BUFFER, room=aes.AES_SHELL_LINE_BYTES)
ANSWER = 0x0BAD_0001                    # what the routine answers: sh_cmd reads none of it


def tail_pokes(command_byte, text=TEXT):
    return {sm.TAIL: sm.tail(command_byte, text).ljust(aes.AES_SHELL_LINE_BYTES, bytes([vdi.FILL]))}


def desk_running(command_byte, answers=(ANSWER,), text=TEXT):
    """(a) The snapshot's own state — the desk running, sh_dodef set — the door staged, the tail's bytes staged."""
    return aes.leaf_machine(onto=merge_pokes(sm.door_pokes(answers), STALE_BUFFER, tail_pokes(command_byte, text)))


def cmd(machine, hook=sm.door_hook, **kwargs):
    return aes.run_function(SH_CMD, (), machine, hook=hook, **{"poison": False, **kwargs})


# ---- the premises ---------------------------------------------------------------------------------------------------------
def test_the_band_is_dead_ram_of_the_snapshot():
    assert not any(BASE_IMAGE[sm.BAND_AT:sm.BAND_AT + sm.BAND_BYTES])


def test_the_staged_table_is_the_rom_s_but_for_the_five_door_entries():
    """Every other Line-F call of a run goes where the ROM's goes: the copy differs from `$fee900..` in the five
    longwords alone, each now a stub's address — and the handler's copy names the table by one operand."""
    staged, the_rom_s = sm._staged_table(), bytes(BASE_IMAGE[sm.LINEF_TABLE:sm.LINEF_TABLE + sm.LINEF_TABLE_BYTES])
    differ = {at for at in range(0, len(staged), aes.LONG_BYTES) if staged[at:at + 4] != the_rom_s[at:at + 4]}
    assert differ == {sm._slot(routine) for routine in sm.FRAME_LONGS} and len(differ) == 5
    assert case.long_in(BASE_IMAGE, sm.TABLE_OPERAND_AT) == sm.LINEF_TABLE


def test_who_calls_the_four_built_ins_and_sh_cmd():
    """THE CALL SITES, read off the ROM: each built-in is Line-F-called from sh_cmd's own text and nowhere else in
    GEM's; sh_cmd from sh_main alone."""
    for routine, name in ((sm.SHOW_FILE, "AES_ROM_DESK_SHOW_FILE"), (sm.PRINT_FILE, "AES_ROM_DESK_PRINT_FILE"),
                          (sm.FORMAT, "AES_ROM_DESK_FORMAT"), (sm.COPY_DISK, "AES_ROM_DESK_COPY_DISK")):
        (sites,) = aes.line_f_call_sites(name).values()
        assert len(sites) == 1 and addrs.AES_ROM_SH_CMD < sites[0] < addrs.AES_ROM_SH_CMD + 196, hex(routine)
    (sites,) = aes.line_f_call_sites(SH_CMD).values()
    assert len(sites) == 1 and addrs.AES_ROM_SH_MAIN < sites[0] < addrs.AES_ROM_SH_CMD


# ---- (a) the desk running: nothing drawn --------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("built_in", BUILT_INS)
def test_argument_class_a_built_in_is_called_once_over_the_frame_the_rom_hands_it_and_sh_cmd_answers_1(built_in, through_line_f):
    """ARGUMENT CLASS (a tail staged while the desk runs; the routine answered at its entry). ONE call through the
    door: the routine the byte names, the tail's TEXT its first longword, the command line's pointer behind it for
    the two disk routines — and 1, whatever the routine answered."""
    byte, routine, frame = BUILT_INS[built_in]
    result = cmd(desk_running(byte), through_line_f=through_line_f)
    assert result.answer() == SHELL["SH_CMD_RAN"] == 1
    (call,) = sm.calls(result.final)
    assert (call.routine, call.first, call.second) == (routine, *frame)


@pytest.mark.parametrize("built_in", BUILT_INS)
def test_argument_class_what_the_built_in_answers_is_not_sh_cmd_s_answer(built_in):
    byte, _routine, _frame = BUILT_INS[built_in]
    assert cmd(desk_running(byte, answers=(0,))).answer() == 1


def test_argument_class_print_heads_the_command_line_with_the_rom_s_text_and_the_file_s_name():
    """`$fd`: the command line := "PRINTING  " (the ROM's own string, `$fef47e`), then the tail's text — before the
    routine is called. The others leave the command line as it was."""
    result = cmd(desk_running(SHELL["SH_CMD_PRINT"]))
    assert bytes(BASE_IMAGE[addrs.AES_SH_PRINTING_TEXT:addrs.AES_SH_PRINTING_TEXT + len(PRINTING) + 1]) == PRINTING + b"\0"
    assert result.after(SHELL_BUFFER, len(PRINTING) + len(TEXT) + 1) == PRINTING + TEXT + b"\0"
    for built_in in ("show a file ($fe)", "format a disk ($fc)", "copy a disk ($fb)"):
        assert cmd(desk_running(BUILT_INS[built_in][0])).after(SHELL_BUFFER, len(A_COMMAND) + 1) == A_COMMAND + b"\0"


NO_BUILT_IN = (0, 1, len(TEXT), 0x7F, 0x80, SHELL["SH_CMD_COPY"] - 1, 0xFF)


@THROUGH
@pytest.mark.parametrize("byte", NO_BUILT_IN, ids=[f"${byte:02x}" for byte in NO_BUILT_IN])
def test_argument_class_any_other_byte_is_a_program_s_tail__0_and_nothing_stored(byte, through_line_f):
    """A program's tail begins with its length: every byte but the four answers 0, calls nothing and stores nothing —
    the bytes either side of the four ($fa, $ff) among them."""
    result = cmd(desk_running(byte, answers=()), through_line_f=through_line_f)
    assert result.answer() == SHELL["SH_CMD_NONE"] == 0
    assert sm.calls(result.final) == [] and aes.stored_nothing(result)


def test_the_four_bytes_are_the_only_built_ins():
    assert sorted(byte for byte, _routine, _frame in BUILT_INS.values()) == [0xFB, 0xFC, 0xFD, 0xFE]
    assert SHELL["SH_CMD_COPY"] - 1 in NO_BUILT_IN and 0xFF in NO_BUILT_IN


def test_argument_class_the_frame_s_first_longword_is_the_tail_s_text_by_address():
    """THE TAIL'S TEXT IS NAMED BY ADDRESS (`movea.l #$c42f,a5`), not through the tail's pointer: with AES_SHELL_TAIL
    staged elsewhere (ARGUMENT CLASS: ini_dlongs' pointer moved) the routine is handed `$c42f` all the same — and
    the command line THROUGH its pointer."""
    elsewhere = sm.BAND_AT + sm.BAND_BYTES - 0x100
    moved = merge_pokes(desk_running(SHELL["SH_CMD_FORMAT"]),
                        aes.field_pokes("AES", SHELL_TAIL=elsewhere, SHELL_BUFFER=elsewhere + 0x80))
    (call,) = sm.calls(cmd(moved).final)
    assert (call.first, call.second) == (sm.TAIL_TEXT, elsewhere + 0x80)


# ---- (b) as sh_main calls it: the machine the ROM's own shel_write leaves, the band drawn ------------------------------------------
DRAW_DOORS = aes.doors(ob_draw.doors(), sm.door_hook)


def asked_for(command_byte, command=A_COMMAND):
    return merge_pokes(sm.asked(command, sm.tail(command_byte, TEXT)), sm.door_pokes((ANSWER,)))


def drawn(machine, **kwargs):
    return cmd(machine, hook=DRAW_DOORS, max_insns=ob_draw.OB_DRAW_INSNS, **{**od.PTSIN_READ_FIRST, **kwargs})


def test_asked_is_what_the_rom_s_own_shel_write_leaves():
    """THE ROM-RUN STATE: the command in the shell's buffer, the tail — its first byte the command — in the shell's
    tail, sh_dodef and sh_isdef cleared, sh_doexec set."""
    image = make_image(asked_for(SHELL["SH_CMD_FORMAT"]))
    assert bytes(image[SHELL_BUFFER:SHELL_BUFFER + len(A_COMMAND) + 1]) == A_COMMAND + b"\0"
    assert bytes(image[sm.TAIL:sm.TAIL + 1 + len(TEXT) + 1]) == bytes([0xFC]) + TEXT + b"\0"
    assert [case.word_in(image, flag) for flag in sm.FLAGS] == [1, 1, 0, 0]


@pytest.mark.parametrize("built_in", DRAWS_THE_BAND)
def test_argument_class_the_band_is_drawn_with_the_command_line_before_the_built_in_is_called(built_in):
    """ARGUMENT CLASS (a launch asked by the ROM's shel_write; the routine answered at its entry). sh_dodef clear and
    gl_shgem set, as the door's ledger found them: the band drawn — the screen changed, the band's text pointed at the
    command line — then the one call."""
    byte, routine, frame = BUILT_INS[built_in]
    result = drawn(asked_for(byte))
    (call,) = sm.calls(result.final)
    assert (call.routine, call.first, call.second, call.dodef, call.shgem) == (routine, *frame, 0, 1)
    assert result.answer() == 1 and screen_changed(result)
    assert result.long(case.long_in(BASE_IMAGE, aes.AES_AD_PFILE)) == SHELL_BUFFER


def test_argument_class_show_draws_nothing_even_where_a_band_would_be_drawn():
    """`$fe` calls its routine and nothing else: over the same machine the screen is left as it was."""
    result = drawn(asked_for(SHELL["SH_CMD_SHOW"]))
    assert result.answer() == 1 and not screen_changed(result)
    (call,) = sm.calls(result.final)
    assert (call.routine, call.first) == (sm.SHOW_FILE, sm.TAIL_TEXT)


def test_argument_class_print_draws_the_band_with_the_line_it_has_just_made():
    """THE ORDER: the line is made BEFORE the band is drawn — another line, another screen."""
    screens = []
    for text in (b"A.DOC", b"B.DOC"):
        machine = merge_pokes(sm.asked(A_COMMAND, sm.tail(SHELL["SH_CMD_PRINT"], text)), sm.door_pokes((ANSWER,)))
        result = drawn(machine)
        assert result.after(SHELL_BUFFER, len(PRINTING) + len(text) + 1) == PRINTING + text + b"\0"
        screens.append(vdi.screen_of(result.final))
    assert screens[0] != screens[1]
