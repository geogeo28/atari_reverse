"""The window library's MESSAGE SENDER — `src/aes/apmsg.c`, through the event door (`test/aes_event.py`).

    ap_sendmsg    msg[0] = type; msg[1] = rlr->p_pid (read AFTER the type's store); msg[2] = 0; msg[3..7] = the five
                  words; ap_rdwr(AQWRT, to, 16, msg) — D0 ap_rdwr's

THE MACHINES, each the ROM scheduler's own (`aes_event.machine`): PD0 running — woken by a key, its waits cancelled —
so a message to itself lands in its PIPE; the screen manager (PD1) running — woken by the mouse onto the menu bar —
while PD0 is still parked in the desk's evnt_multi waiting for a message: one sent to PD0 is handed straight to that
wait; and a pipe already holding one — sent before by the ROM's own ap_sendmsg.

The buffer is staged STALE (`case.SLACK_FILL`), so every word the C skipped differs.
"""
import struct

import aes
import aes_event
import aes_gsx as gsx
import case
import vdi
from case import merge_pokes
from harness import addrs, make_image

aes.declare_alcyon("AES_ROM_AP_SENDMSG", aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG) + (vdi.WORD_ARG,) * 7)
APMSG = aes.header_constants("apmsg.h")

THROUGH = gsx.THROUGH
SHELL, SCREEN_MANAGER = 0, 1           # the process ids: PD0 the desk, PD1 the screen manager
WM_REDRAW = 20                         # a message's type, as the window library sends it
WORDS = (3, -2, 0x7FFF, -0x8000, 0)
BUFFER = aes_event.MESSAGE_AT


def stale_buffer(at=BUFFER):
    return {at: bytes([case.SLACK_FILL]) * APMSG["AP_MSG_BYTES"]}


def running():
    return aes_event.machine(onto=stale_buffer())


def screen_manager_running():
    return aes_event.machine(aes_event.screen_manager_running, onto=stale_buffer())


def sendmsg(machine, to, type_=WM_REDRAW, buffer=BUFFER, words=WORDS, **kwargs):
    return aes_event.run_event("AES_ROM_AP_SENDMSG", (buffer, type_, to, *words), machine, **kwargs)


def message_of(result, at=BUFFER):
    return [aes.signed(word) for word in result.words(at, APMSG["AP_MSG_BYTES"] // aes.WORD_BYTES)]


def queued(result, pd=aes.SHELL_PD):
    return result.field("PD", "QUEUE_INDEX", pd)


def one_queued():
    """PD0 running, one message already in its pipe: the ROM's own ap_sendmsg run first."""
    state = running()
    delta, _final, _regs = aes_event.derived(addrs.AES_ROM_AP_SENDMSG,
                                             aes.staged("AES_ROM_AP_SENDMSG", (BUFFER, WM_REDRAW, SHELL, *WORDS), state))
    return merge_pokes(state, delta)


# ---- the cases -----------------------------------------------------------------------------------------------------
def test_ap_sendmsg_returns_through_the_door_in_a_child():
    """FIRST, in a child process: a message the event layer can take is served and the core returns. A door call the
    nested run refuses halts the core (`aes/evdoor.h`), which in-process would end the run rather than fail one case —
    here it fails this one, before any in-process case can halt."""
    returncode, stderr, _image = aes_event.refusal("AES_ROM_AP_SENDMSG", running(), (BUFFER, WM_REDRAW, SHELL, *WORDS))
    assert returncode == 0, stderr


def test_to_pd0_parked_the_message_is_handed_to_its_wait():
    """Sent by the screen manager, running: PD0 waits for a message in the desk's evnt_multi, and ap_rdwr hands this
    one straight to that EVB's buffer — PD0's pipe left empty — the wait satisfied waking PD0 (onto the woken list,
    for the dispatcher's next pass). The sender is PD1."""
    result = sendmsg(screen_manager_running(), SHELL)
    assert message_of(result) == [WM_REDRAW, SCREEN_MANAGER, 0, *WORDS]
    assert queued(result) == 0
    assert aes.list_of(result.final, aes.AES_DRL) == [aes.SHELL_PD]


def test_to_pd0_running_the_message_lands_in_its_pipe():
    result = sendmsg(running(), SHELL)
    assert queued(result) == APMSG["AP_MSG_BYTES"]
    assert message_of(result, aes.SHELL_PD + aes.PD_QUEUE) == [WM_REDRAW, SHELL, 0, *WORDS]


def test_to_the_screen_manager():
    result = sendmsg(running(), SCREEN_MANAGER, type_=-1, words=(0,) * 5)
    assert message_of(result)[:2] == [-1, SHELL]


def test_a_second_message_behind_the_first():
    first = make_image(one_queued())
    pipe = aes.SHELL_PD + aes.PD_QUEUE
    result = sendmsg(one_queued(), SHELL, words=(1, 2, 3, 4, 5))
    assert queued(result) == 2 * APMSG["AP_MSG_BYTES"]
    assert result.after(pipe, APMSG["AP_MSG_BYTES"]) == bytes(first[pipe:pipe + APMSG["AP_MSG_BYTES"]]), "the first is kept"
    assert message_of(result, pipe + APMSG["AP_MSG_BYTES"]) == [WM_REDRAW, SHELL, 0, 1, 2, 3, 4, 5]


def test_the_sender_is_read_after_the_type_is_stored():
    """THE ORDER, as an overlap: the buffer laid over PD0's own process id, so the type's store IS the id the next
    instruction reads — the sender comes out as the type. The words after it rewrite PD0's event fields with what they
    hold, so the machine is otherwise unmoved."""
    at = aes.SHELL_PD + aes.PD_PID
    words = struct.unpack(">5h", bytes(make_image()[at + APMSG["AP_MSG_WORDS"]:at + APMSG["AP_MSG_BYTES"]]))
    result = sendmsg(running(), SCREEN_MANAGER, type_=SCREEN_MANAGER, buffer=at, words=words)
    assert message_of(result, at)[:2] == [SCREEN_MANAGER, SCREEN_MANAGER]


def test_the_running_pd_is_reached_through_the_24_bit_bus():
    """The sender is read through `rlr`, a longword the 68000's bus drops the top byte of: staged with one, the ROM — and
    every routine of the event layer after it — reaches PD0 all the same."""
    tagged = merge_pokes(running(), aes.field_pokes("AES", RLR=aes.SHELL_PD | aes.BUS_TAG))
    result = sendmsg(tagged, SHELL)
    assert message_of(result) == [WM_REDRAW, SHELL, 0, *WORDS]


def test_a_redraw_for_the_same_window_is_merged_into_the_one_queued():
    """The event layer's own arm (both shores run it): a second WM_REDRAW for the window already queued is not
    appended — the pipe still holds one message."""
    result = sendmsg(one_queued(), SHELL)
    assert queued(result) == APMSG["AP_MSG_BYTES"]


def test_the_buffer_is_put_on_the_bus():
    result = sendmsg(running(), SHELL, buffer=BUFFER | aes.BUS_TAG)
    assert message_of(result) == [WM_REDRAW, SHELL, 0, *WORDS]


@THROUGH
def test_ap_sendmsg_through_its_callers_word(through_line_f):
    result = sendmsg(running(), SHELL, through_line_f=through_line_f)
    assert queued(result) == APMSG["AP_MSG_BYTES"]


def test_an_odd_buffer_is_refused_by_name():
    """The 68000's address error on the first `move.w` — which the oracle's Musashi completes — refused by the host in a
    child process (the door bound there too)."""
    returncode, stderr, _image = aes_event.refusal(
        "AES_ROM_AP_SENDMSG", running(), (BUFFER + 1, WM_REDRAW, SHELL, *WORDS))
    assert returncode != 0 and "address error" in stderr, stderr


# ---- the registry ----------------------------------------------------------------------------------------------------
ROWS = {
    "from the screen manager to PD0 parked: handed to its wait": (screen_manager_running, SHELL),
    "to PD0 running: into its pipe": (running, SHELL),
    "a second behind the first": (one_queued, SHELL),
}
for _label, (_machine, _to) in ROWS.items():
    aes_event.register(_label, "AES_ROM_AP_SENDMSG", (BUFFER, WM_REDRAW, _to, *WORDS), _machine())
