"""Differential tests for Joust's input layer (src/input.c).

Covered here: poll_quit_key @ 0x11c24 (with its pause loop @ 0x11d64), hiscore_key_input @ 0x144d4
and hiscore_joystick_input @ 0x14538. read_joysticks @ 0x11d9a is NOT reconstructed; the reason is
pinned by test_ikbd_wait_never_ends_from_the_routines_own_entry.

Every routine here is trap-bound, so the kit's TOS model
(../../../../tools/recreate_kit/TRAP_MODEL.md) sets what can be proved at all. Four of its limits
shape this whole file:

  * **One keystroke per run.** Bconstat/Bconin read harness-poked console state and Bconin CONSUMES
    it, so a run delivers at most one key. Every branch therefore gets its own fixed-input run, and
    poll_quit_key's pause — which waits for a SECOND key — can only be entered at its own head.
  * **Two exits never return.** GEMDOS Pterm is unmodeled (it ends the process; there is no
    post-state), and R/r jumps back into _start. Both are diffed at a checkpoint PC instead of at
    `rts`, and each is paired with a test that the run really does NOT reach `rts` — otherwise a
    `stop_pc` run that fell through to `rts` would stop at the sentinel and pass silently.
  * **Off-image traps.** Setscreen, two Ikbdws command strings, Kbdvbase, Super and Setpalette
    change no memory, so the image diff cannot see them at all. Their arguments are read back out of
    the oracle's own stack instead (`_pushed_words`), which is the only thing that can catch a wrong
    pointer or resolution.
  * **The IKBD reply never arrives.** Its interrogate command goes out through Ikbdws (no image
    effect) and the answer comes back on an interrupt the oracle never runs, so the two routines
    that wait for it spin forever — and they CLEAR the packet on entry, so a poked reply cannot
    survive to end the wait. hiscore_joystick_input is therefore entered at its wait loop with the
    reply staged, and read_joysticks is left unreconstructed.
"""
import ctypes
import random
import struct
import threading

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines     # the shared `#define` scraper; see the pin tests at the end
# The two sibling modules that already own what this file needs: test_score the stack-readback and
# mirror-pin helpers, test_os_traps the GEMDOS selector numbers the quit path traps through.
from test_score import _pin, _pushed_words, UNWRITTEN_W
from test_os_traps import GEMDOS_FCLOSE, GEMDOS_FOPEN, GEMDOS_FWRITE, GEMDOS_SUPER

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_POLL_QUIT_KEY = 0x11c24
ENTRY_PAUSE_LOOP = 0x11d64        # poll_quit_key's pause spin, entered directly (see the docstring)
ENTRY_HISCORE_KEY_INPUT = 0x144d4
ENTRY_HISCORE_JOYSTICK_INPUT = 0x14538
ENTRY_IKBD_WAIT = 0x1454e         # hiscore_joystick_input's IKBD wait loop, entered directly
ENTRY_READ_JOYSTICKS = 0x11d9a    # not reconstructed — see the IKBD section below

# ---- checkpoint PCs (harness `stop_pc`) ----
CHECKPOINT_BEFORE_PTERM = 0x11d4c  # stop here: the quit path's last image effect has run and
                                   # what follows is the `addq.w #4,a7` and GEMDOS Pterm's push+trap
PTERM_RETURN_PC = 0x11d56         # where the unmodeled Pterm trap would return, if it ever did
RESTART_ENTRY = 0x10006            # _start+6, where R/r jumps and never returns

# ---- the INPUT_* results src/input.c reports its exit with ----
INPUT_CONTINUE, INPUT_RESTART, INPUT_QUIT = 0, 1, 2

# ---- and what g_pause_until_key reports instead of hanging on an uncapped spin ----
PAUSE_LEFT_ON_KEY, PAUSE_NO_KEY = 0, 1

# ---- globals (mirrors of include/input.h, include/score.h and include/object.h) ----
A_SAVED_MOUSEVEC = 0x10d18
A_SAVED_JOYVEC = 0x10d1c
A_SAVED_REZ = 0x10d20
A_CONTERM_SAVE = 0x10d22
A_IKBD_CMD_RESET = 0x10d24
A_SAVED_PALETTE = 0x10d26
A_QUIT_FILE_HANDLE = 0x10dec       # draw_x, borrowed while HIGH.SCO is being written
A_SND_LIST_SILENCE = 0x1150f
A_IKBD_CMD_MOUSE_REL = 0x11d56
A_IKBD_CMD_JOYREAD = 0x1145b
A_FNAME_HIGHSCO = 0x102c8
A_HISCORE_DIRTY = 0x18388
A_HISCORE_NAME = 0x18396
A_SCREEN_BASE = 0x10dde
A_HISCORE_CURSOR = 0x10df4         # draw_shift, borrowed by the name-entry screen...
A_HISCORE_TOUCHED = 0x10df6        # ...draw_rows...
A_HISCORE_LETTER = 0x10df8         # ...and draw_dst_off
A_TEXT_PTR = 0x10e0a               # the text engine's block: ptr, shift, color, bg_color, flags
A_HISCORE_STICK = 0x10df0          # draw_src, borrowed to say whose joystick is entering the name
A_IKBD_PACKET = 0x10e06            # .l — where the IKBD interrupt handler leaves the reply
A_REPEAT_DELAY = 0x1415e
A_OBJECT_TABLE = 0x10f36           # player 1's slot
A_PLAYER2 = 0x10f84

# ---- TOS state the quit path restores ----
TOS_CONTERM = 0x484
KBDV_MOUSEVEC = 0x10
KBDV_JOYVEC = 0x18
OS_KBDVBASE = 0x500                # os.h: what XBIOS Kbdvbase returns

# ---- the keys poll_quit_key acts on ----
KEY_CTRL_C = 0x03
KEY_PAUSE_UPPER, KEY_PAUSE_LOWER = 0x50, 0x70
KEY_RESTART_UPPER, KEY_RESTART_LOWER = 0x52, 0x72
SPECIAL_KEYS = (KEY_CTRL_C, KEY_PAUSE_UPPER, KEY_PAUSE_LOWER, KEY_RESTART_UPPER, KEY_RESTART_LOWER)

# ---- the keys the name entry acts on ----
KEY_BACKSPACE, KEY_RETURN, KEY_SPACE = 0x08, 0x0d, 0x20
KEY_UPPER_A, KEY_UPPER_Z, KEY_LOWER_A = 0x41, 0x5a, 0x61
HISCORE_COLUMNS = 0x10

# ---- the joystick byte, and the auto-repeat it drives ----
JOY_FIRE, JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_DIRECTIONS = 0x80, 0x01, 0x02, 0x04, 0x08, 0x0f
REPEAT_DELAY_FIRST, REPEAT_DELAY_NEXT = 6, 2
IKBD_PACKET_JOYSTICK_1 = 1         # the reply is joystick 0's byte then joystick 1's
IKBD_PACKET_BUF = 0x60000          # scratch for the staged 2-byte reply, clear of SCREEN's band

# ---- the name-entry screen's staging ----
# A scratch screen clear of the program (which ends 0x2b7ae), of abi's stub space and of the staged
# file table. The band is where draw_hiscore_entry (screen_base + 0x52b0) and draw_hiscore_cursor
# (+ 0x57b0) paint; it is filled with noise so an absent or spurious redraw shows as a diff.
SCREEN = 0x70000
SCREEN_SPAN = 0x8000
PAINTED_BAND_OFF, PAINTED_BAND_LEN = 0x5200, 0x700
TEXT_COLOR, TEXT_BG_COLOR, TEXT_FLAG_LARGE_FONT = 6, 0, 0x80
STAGED_LETTER = 0x5a               # what sits under the cursor before a key arrives

# ---- the XBIOS calls the quit path makes (the GEMDOS ones are imported above) ----
XBIOS_SETSCREEN, XBIOS_SETPALETTE, XBIOS_IKBDWS, XBIOS_KBDVBASE = 0x05, 0x06, 0x19, 0x22

HISCORE_RECORD_BYTES = 0x1a        # what Fwrite pushes out of hiscore_name
HIGHSCO_OPEN_MODE = 2              # GEMDOS Fopen mode 2 = read/write
HIGHSCO_NAME = "HIGH.SCO"

# A spin that never ends is capped rather than run to the harness default: these cases exist to show
# the oracle does NOT terminate, so the cap is the whole point and a small one keeps them cheap.
SPIN_CAP = 2_000

# The candidate has no such cap, so every call into its pause spin runs under a wall-clock deadline
# instead (see _pause_glue). Absurdly generous for a loop that leaves on its first pass, and only
# ever waited out by a candidate that is not leaving the loop at all.
PAUSE_GLUE_TIMEOUT_S = 5

FUZZ_CHUNKS = 4

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _ret in (("g_poll_quit_key", ctypes.c_uint32),
                    ("g_pause_until_key", ctypes.c_uint32),
                    ("g_hiscore_key_input", ctypes.c_uint32),
                    ("g_hiscore_joystick_input", ctypes.c_uint32)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P]
    _fn.restype = _ret


def _poll(lib, buf):
    return lib.g_poll_quit_key(buf)


# ------------------------------------------------------------------ shared staging helpers

# Distinctive values for the system state the quit path copies about, so a copy that never happened
# shows as a diff rather than as zero-matching-zero. The destinations are pre-filled with a sentinel
# for the same reason.
SAVED_MOUSEVEC, SAVED_JOYVEC = 0x0001A5A5, 0x0001C3C3
SAVED_REZ, SAVED_CONTERM = 0x0002, 0x0f
UNWRITTEN_B, UNWRITTEN_L = 0x5a, 0x5a5a5a5a          # UNWRITTEN_W is test_score's, imported above
STALE_HIGHSCO = b"\xa5" * HISCORE_RECORD_BYTES   # what the staged file holds before the run


def _system_state_pokes():
    """What init_system stashed away, plus a sentinel in every place restore_system must overwrite."""
    return {A_SAVED_MOUSEVEC: SAVED_MOUSEVEC.to_bytes(4, "big"),
            A_SAVED_JOYVEC: SAVED_JOYVEC.to_bytes(4, "big"),
            A_SAVED_REZ: SAVED_REZ.to_bytes(2, "big"),
            A_CONTERM_SAVE: bytes([SAVED_CONTERM]),
            TOS_CONTERM: bytes([UNWRITTEN_B]),
            OS_KBDVBASE + KBDV_MOUSEVEC: UNWRITTEN_L.to_bytes(4, "big"),
            OS_KBDVBASE + KBDV_JOYVEC: UNWRITTEN_L.to_bytes(4, "big")}


def _hiscore_record(seed):
    """26 bytes of printable noise standing in for the name+scores record Fwrite pushes out."""
    rng = random.Random(seed)
    return bytes(rng.randrange(0x20, 0x7f) for _ in range(HISCORE_RECORD_BYTES))


def _quit_pokes(dirty=1, seed=1):
    """Ctrl-C staged, plus everything the quit path reads: the system state, the dirty flag, the
    record to write, and a HIGH.SCO already on disk whose bytes the write must replace."""
    pokes = dict(harness.console_key(chr(KEY_CTRL_C)))
    pokes.update(_system_state_pokes())
    pokes[A_HISCORE_DIRTY] = bytes([dirty])
    pokes[A_HISCORE_NAME] = _hiscore_record(seed)
    pokes[A_QUIT_FILE_HANDLE] = UNWRITTEN_W.to_bytes(2, "big")
    file_pokes, _ = harness.stage_files([(HIGHSCO_NAME, STALE_HIGHSCO)])
    pokes.update(file_pokes)
    return pokes


def _oracle_final(pokes, entry=ENTRY_POLL_QUIT_KEY, **run_args):
    """The oracle's final image, for the few checks that must look at MODEL state.

    Not `info["writes"]`: the shim's write set logs the 68000's own stores only, and the trap model
    reaches the image directly (`os_bconin` clearing OS_CON_PENDING, `os_fwrite` filling the staged
    file), so none of that appears there. Those bytes ARE compared by the differential — they are
    ordinary image state — but a test that wants to read one has to read the image.
    """
    image, _, _ = emu.run(harness.make_image(pokes), entry, **run_args)
    return image


def _con_pending(image):
    return int.from_bytes(image[harness.OS_CON_PENDING:harness.OS_CON_PENDING + 4], "big")


def _stored(writes, addr, size=1):
    """What the ORIGINAL left at `addr`, out of the write set the differential already returned.

    Asserting from `info["writes"]` rather than re-running the oracle keeps the assertion about the
    very image the differential verified: a second run built from freshly staged pokes is only the
    same case as long as nobody changes how the case is staged. It also halves the oracle work,
    since every run copies the whole 1 MiB image. Raises if the run never wrote there, which is the
    useful answer for the tests below — they are all asserting that it did.
    """
    return int.from_bytes(bytes(writes[addr + step] for step in range(size)), "big")


def _never_returns(pokes, entry):
    """Assert the original does not come back from `entry` on this input.

    The `stop_pc` runs elsewhere would pass just as happily on a routine that fell through to `rts`
    — osh_run stops at the sentinel or the checkpoint and reports success either way — so every
    checkpointed branch is paired with this.
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(pokes), entry, max_insns=SPIN_CAP)


# ------------------------------------------------------------------ poll_quit_key: the plain exits

def test_poll_quit_key_no_key_returns_at_once():
    """Bconstat says nothing is waiting, so the routine returns without reading the console.

    That it does not read is self-proving rather than asserted: Bconin with nothing pending is
    REFUSED by the model, so a run that reached it would be rejected as fabricated, not diffed.
    """
    diffs, info = differential(ENTRY_POLL_QUIT_KEY, {}, _poll, poison=True)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_CONTINUE


@pytest.mark.parametrize("key", (0x00, 0x01, 0x02, 0x04, 0x08, 0x0d, 0x20, 0x41, 0x51, 0x53,
                                 0x71, 0x73, 0x7f, 0x80, 0xff))
def test_poll_quit_key_ordinary_key_is_consumed_and_ignored(key):
    """Every key but the five it acts on falls through the 0x11d58 table and returns."""
    pokes = harness.console_key(chr(key))
    diffs, info = differential(ENTRY_POLL_QUIT_KEY, {"_pokes": pokes}, _poll, poison=True)
    assert not diffs, f"key={key:#04x}\n{report(diffs)}"
    assert info["ret"] == INPUT_CONTINUE


def test_poll_quit_key_reads_the_keystroke_out_of_the_console():
    """Bconin CONSUMES the pending key, which is image state — so a candidate that skipped the read
    would leave the console armed and diverge on every case above. Read once, here."""
    image = _oracle_final(harness.console_key("A"))
    assert _con_pending(image) == 0, "the keystroke is still pending: Bconin never ran"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_poll_quit_key_fuzz_every_ordinary_key(chunk):
    """All 256 ASCII bytes bar the five special ones, each with a random SCANCODE in the high word
    of Bconin's longword result — every test in the routine is a `cmp.b`, so that half is dead."""
    rng = random.Random(0x9017)
    cases = [(key, rng.randint(0, 0xffff)) for key in range(0x100) if key not in SPECIAL_KEYS]
    ran = 0
    for index, (key, scancode) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = harness.console_key(chr(key), scancode)
        diffs, info = differential(ENTRY_POLL_QUIT_KEY, {"_pokes": pokes}, _poll)
        assert not diffs, f"key={key:#04x} scancode={scancode:#06x}\n{report(diffs)}"
        assert info["ret"] == INPUT_CONTINUE
        ran += 1
    assert ran, "this shard ran no cases"


# ------------------------------------------------------------------ poll_quit_key: R/r restarts

@pytest.mark.parametrize("key", (KEY_RESTART_UPPER, KEY_RESTART_LOWER))
def test_poll_quit_key_restart_reaches_start(key):
    """R/r drops the caller's return address and jumps to _start+6. Diffed at that checkpoint."""
    pokes = harness.console_key(chr(key))
    diffs, info = differential(ENTRY_POLL_QUIT_KEY, {"_pokes": pokes}, _poll,
                               stop_pc=RESTART_ENTRY, poison=True)
    assert not diffs, f"key={key:#04x}\n{report(diffs)}"
    assert info["ret"] == INPUT_RESTART


@pytest.mark.parametrize("key", (KEY_RESTART_UPPER, KEY_RESTART_LOWER))
def test_poll_quit_key_restart_never_returns(key):
    """...and it really is the jump, not a fall-through to `rts`: without the checkpoint the run
    cannot finish. Nothing else distinguishes the two — the branch writes no memory at all."""
    _never_returns(harness.console_key(chr(key)), ENTRY_POLL_QUIT_KEY)


# ------------------------------------------------------------------ poll_quit_key: the pause loop

def _pause_glue(lib, buf):
    """Call g_pause_until_key under a wall-clock deadline, and return what it returned.

    EVERY candidate-side entry into the pause spin goes through here. The spin is uncapped in C —
    faithfully, the original has no cap either — so a candidate that failed to leave it would hang
    this worker for ever and print nothing at all under `-n auto`, which is the one failure a
    differential cannot report. The deadline turns that into an ordinary red assert naming the
    cause. CDLL releases the GIL, so the join really does expire; the abandoned thread is a daemon
    and cannot hold up the worker's exit, though it does keep one core spinning for the rest of the
    session — acceptable in a run that is already failing.
    """
    returned = []
    call = threading.Thread(target=lambda: returned.append(lib.g_pause_until_key(buf)), daemon=True)
    call.start()
    call.join(PAUSE_GLUE_TIMEOUT_S)

    assert returned, (f"g_pause_until_key did not return within {PAUSE_GLUE_TIMEOUT_S}s — the "
                      "uncapped pause spin was entered and never left")
    return returned[0]


@pytest.mark.parametrize("key", (KEY_PAUSE_UPPER, KEY_PAUSE_LOWER))
def test_pause_key_cannot_be_verified_through_poll_quit_key(key):
    """A MODEL LIMIT, pinned so it cannot change unnoticed: Bconin has just consumed the only
    keystroke a run can stage, so the pause loop never sees the second key that would end it and the
    oracle spins to its instruction cap. The loop is verified at its own entry below instead."""
    _never_returns(harness.console_key(chr(key)), ENTRY_POLL_QUIT_KEY)


@pytest.mark.parametrize("key,scancode", ((0x20, 0x39), (0x0d, 0x1c), (0x03, 0x2e), (0xff, 0xffff)))
def test_pause_loop_leaves_on_any_key_without_consuming_it(key, scancode):
    """Entered at the spin's head with a key already pending: the loop leaves on its first pass and
    does NOT read the key, so the keystroke is still armed afterwards — which the diff sees, because
    a candidate that called Bconin would have cleared OS_CON_PENDING."""
    pokes = harness.console_key(chr(key), scancode)
    diffs, info = differential(ENTRY_PAUSE_LOOP, {"_pokes": pokes}, _pause_glue, poison=True)
    assert not diffs, f"key={key:#04x}\n{report(diffs)}"
    assert info["ret"] == PAUSE_LEFT_ON_KEY, "the glue refused instead of running the loop"
    assert _con_pending(_oracle_final(pokes, ENTRY_PAUSE_LOOP)), "the pause loop ate the keystroke"


def test_pause_loop_spins_while_no_key_is_pending():
    """The other half of the same behaviour, and the reason the loop cannot be reached from
    poll_quit_key: with nothing staged it never leaves."""
    _never_returns({}, ENTRY_PAUSE_LOOP)


def test_pause_glue_refuses_a_call_that_would_never_return():
    """THE CANDIDATE'S HALF of the case above, which is why g_pause_until_key is not a bare
    forwarder. Only harness.differential's oracle-first ordering keeps the uncapped spin
    unreachable with nothing staged, and nothing pins that ordering — so the glue probes the
    console once and refuses, and this asserts the refusal is what comes back. Dropping the
    refusal makes _pause_glue's deadline expire, which is the whole point of running it there."""
    buf = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer(bytearray(harness.make_image()))
    assert _pause_glue(harness._lib, buf) == PAUSE_NO_KEY, \
        "the glue entered the loop with nothing pending"


# ------------------------------------------------------------------ poll_quit_key: Ctrl-C quits

def _quit_case(dirty, seed=1, poison=False):
    """Ctrl-C, run to the checkpoint one instruction short of GEMDOS Pterm."""
    pokes = _quit_pokes(dirty=dirty, seed=seed)
    diffs, info = differential(ENTRY_POLL_QUIT_KEY, {"_pokes": pokes}, _poll,
                               stop_pc=CHECKPOINT_BEFORE_PTERM, poison=poison)
    assert not diffs, f"hiscore_dirty={dirty:#04x}\n{report(diffs)}"
    assert info["ret"] == INPUT_QUIT
    assert info["regs"]["dosound"] == [A_SND_LIST_SILENCE], \
        "the quit path did not silence the YM2149 with the expected Dosound list"
    return info


@pytest.mark.parametrize("dirty", (0x01, 0x80, 0xff))
def test_poll_quit_key_ctrl_c_writes_the_high_score(dirty):
    """A pending high score is opened, written and closed on the way out. Any non-zero flag byte
    counts — the original tests it with `tst.b`."""
    _quit_case(dirty, seed=dirty, poison=True)


def _staged_highsco(image):
    return bytes(image[harness.OS_FS_STAGING:harness.OS_FS_STAGING + HISCORE_RECORD_BYTES])


def test_poll_quit_key_ctrl_c_clean_skips_the_file_entirely():
    """hiscore_dirty == 0: no Fopen, no Fwrite — the staged file is left exactly as it was."""
    _quit_case(0, poison=True)
    pokes = _quit_pokes(dirty=0)
    assert _staged_highsco(_oracle_final(pokes, stop_pc=CHECKPOINT_BEFORE_PTERM)) == STALE_HIGHSCO


def test_poll_quit_key_ctrl_c_record_really_reaches_the_staged_file():
    """The bytes that land in HIGH.SCO are hiscore_name's 26, replacing what the file held.

    The differential already pins the two cores against each other; this pins them against the
    binary — that the record written is the one at hiscore_name, at its own length.
    """
    pokes = _quit_pokes(dirty=1, seed=7)
    assert _staged_highsco(_oracle_final(pokes, stop_pc=CHECKPOINT_BEFORE_PTERM)) \
        == _hiscore_record(7)


def test_poll_quit_key_ctrl_c_ends_in_an_unmodeled_pterm():
    """WHY the checkpoint above exists. Run one instruction further — past the trap — and the model
    rejects the whole run: Pterm ends the process, so there is no post-state to diff and no result
    to serve. The quit path has no `rts` to stop at either."""
    pokes = _quit_pokes()
    with pytest.raises(RuntimeError, match="unmodeled OS behaviour"):
        emu.run(harness.make_image(pokes), ENTRY_POLL_QUIT_KEY, stop_pc=PTERM_RETURN_PC)


def test_poll_quit_key_ctrl_c_restores_the_system_state():
    """conterm and the two KBDVBASE vectors are the only three memory effects of the hand-back."""
    writes = _quit_case(1)["writes"]
    assert _stored(writes, TOS_CONTERM) == SAVED_CONTERM
    assert _stored(writes, OS_KBDVBASE + KBDV_MOUSEVEC, 4) == SAVED_MOUSEVEC
    assert _stored(writes, OS_KBDVBASE + KBDV_JOYVEC, 4) == SAVED_JOYVEC


# ------------------------------------------------------------------ the quit path's trap arguments
#
# Setscreen, the two Ikbdws strings, Kbdvbase, Super and Setpalette change no memory, so the whole
# differential is blind to them: a wrong resolution or a wrong command-string pointer would pass. The
# oracle's write set does hold the words the original pushed for each `trap`, though — nothing else
# writes there — so each call is checkpointed just past its stack cleanup and its arguments read
# back. Outermost (highest address) word first, i.e. the LAST argument pushed comes last.

def _quit_trap_args(checkpoint, count):
    _, writes, _ = emu.run(harness.make_image(_quit_pokes()), ENTRY_POLL_QUIT_KEY,
                           stop_pc=checkpoint)
    return _pushed_words(writes, count)


QUIT_TRAP_CALLS = (
    # (checkpoint just past the call's stack cleanup, the words it pushed, what it is)
    (0x11c80, (HIGHSCO_OPEN_MODE, A_FNAME_HIGHSCO & 0xffff, A_FNAME_HIGHSCO >> 16, GEMDOS_FOPEN),
     "Fopen(HIGH.SCO, read/write)"),
    (0x11cbe, (A_HISCORE_NAME & 0xffff, A_HISCORE_NAME >> 16, HISCORE_RECORD_BYTES, 0,
               harness.OS_FS_FIRST_HANDLE, GEMDOS_FWRITE), "Fwrite(handle, 26, hiscore_name)"),
    (0x11ccc, (harness.OS_FS_FIRST_HANDLE, GEMDOS_FCLOSE), "Fclose(handle)"),
    (0x11cf2, (SAVED_REZ, 0xffff, 0xffff, 0xffff, 0xffff, XBIOS_SETSCREEN),
     "Setscreen(-1, -1, saved_rez)"),
    (0x11d04, (A_IKBD_CMD_MOUSE_REL & 0xffff, A_IKBD_CMD_MOUSE_REL >> 16, 0, XBIOS_IKBDWS),
     "Ikbdws(0, ikbd_cmd_mouse_rel)"),
    (0x11d16, (A_IKBD_CMD_RESET & 0xffff, A_IKBD_CMD_RESET >> 16, 1, XBIOS_IKBDWS),
     "Ikbdws(1, ikbd_cmd_reset)"),
    (0x11d20, (0, 0, XBIOS_KBDVBASE), "Kbdvbase()"),
    (0x11d3e, (0, 0, GEMDOS_SUPER), "Super(0)"),
    (0x11d4c, (A_SAVED_PALETTE & 0xffff, A_SAVED_PALETTE >> 16, XBIOS_SETPALETTE),
     "Setpalette(saved_palette)"),
)


@pytest.mark.parametrize("checkpoint,expected,label", QUIT_TRAP_CALLS,
                         ids=[call[2] for call in QUIT_TRAP_CALLS])
def test_quit_path_trap_arguments(checkpoint, expected, label):
    got = _quit_trap_args(checkpoint, len(expected))
    assert tuple(got) == tuple(expected), f"{label}: pushed {[hex(w) for w in got]}"


def test_ikbd_command_strings_are_the_bytes_the_image_carries():
    """The Ikbdws pointers are addresses; these are the commands they point AT.

    ikbd_cmd_mouse_rel is the interesting one: it sits in the two dead bytes right after
    poll_quit_key's Pterm trap, so a linear disassembly renders it as an instruction
    (`move.b d0,d2`) rather than as the IKBD command byte it is. ikbd_cmd_joyread is the command
    the two unreconstructible IKBD waits send — the only thing in this file that pins it, since no
    run can execute the Ikbdws that would push it.
    """
    image = bytes(harness.BASE_IMAGE)
    assert image[A_IKBD_CMD_JOYREAD] == 0x16, "not the IKBD 'interrogate joysticks' command"
    assert image[A_IKBD_CMD_MOUSE_REL] == 0x14, "not the IKBD 'relative mouse reporting' command"
    assert image[A_IKBD_CMD_RESET:A_IKBD_CMD_RESET + 2] == b"\x80\x01", "not the IKBD reset command"
    assert image[A_FNAME_HIGHSCO:A_FNAME_HIGHSCO + 9] == b"HIGH.SCO\x00"


def test_fcreate_fallback_is_unreachable_under_the_model():
    """A MODEL LIMIT, pinned: poll_quit_key falls back to Fcreate when Fopen fails, and no input can
    make that happen. os_fcreate is os_fopen plus a truncation, so both succeed for a name the
    harness staged and both are REFUSED (raising the run) for one it did not — there is no image in
    which Fopen returns -1 and Fcreate then returns a handle. The fallback is reproduced in
    src/input.c unverified; see ../STATUS.md.
    """
    pokes = dict(harness.console_key(chr(KEY_CTRL_C)))
    pokes.update(_system_state_pokes())
    pokes[A_HISCORE_DIRTY] = b"\x01"                       # ...and HIGH.SCO deliberately NOT staged
    with pytest.raises(RuntimeError, match="unmodeled OS behaviour"):
        emu.run(harness.make_image(pokes), ENTRY_POLL_QUIT_KEY, stop_pc=CHECKPOINT_BEFORE_PTERM)


# ------------------------------------------------------------------ hiscore_key_input @ 0x144d4

def _key_entry(lib, buf):
    return lib.g_hiscore_key_input(buf)


def _entry_pokes(cursor, key=None, letter=STAGED_LETTER, touched=0, scancode=0, seed=0):
    """The name-entry screen as check_highscore leaves it, plus one staged keystroke.

    The screen is noise over the whole band the two drawing routines paint in, so a redraw that
    should not have happened — or one that did not — shows as a diff rather than as zero on zero.
    """
    rng = random.Random(seed)
    pokes = {A_SCREEN_BASE: struct.pack(">I", SCREEN),
             A_HISCORE_CURSOR: struct.pack(">H", cursor),
             A_HISCORE_TOUCHED: struct.pack(">H", touched),
             # draw_string is handed the ADDRESS of the letter, so the byte after it terminates.
             A_HISCORE_LETTER: bytes([letter, 0]),
             A_TEXT_PTR: struct.pack(">IBBBB", UNWRITTEN_L, UNWRITTEN_B,
                                     TEXT_COLOR, TEXT_BG_COLOR, TEXT_FLAG_LARGE_FONT),
             SCREEN + PAINTED_BAND_OFF: rng.randbytes(PAINTED_BAND_LEN)}
    if key is not None:
        pokes.update(harness.console_key(chr(key), scancode))
    return pokes


def _key_case(cursor, key, expected=INPUT_CONTINUE, poison=True, **staging):
    pokes = _entry_pokes(cursor, key=key, seed=(cursor + key) & 0xff, **staging)
    diffs, info = differential(ENTRY_HISCORE_KEY_INPUT, {"_pokes": pokes}, _key_entry, poison=poison)
    assert not diffs, f"cursor={cursor:#x} key={key:#04x}\n{report(diffs)}"
    assert info["ret"] == expected
    return info


def _painted(writes):
    """Did the original paint anything on screen? The drawing routines store through the 68000, so
    those writes ARE in the write set (unlike the trap model's own — see _oracle_final)."""
    return any(SCREEN <= addr < SCREEN + SCREEN_SPAN for addr in writes)


def test_hiscore_key_input_no_key_returns_at_once():
    diffs, info = differential(ENTRY_HISCORE_KEY_INPUT, {"_pokes": _entry_pokes(3)},
                               _key_entry, poison=True)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_CONTINUE
    assert not _painted(info["writes"]), "it painted the screen without a keystroke"


@pytest.mark.parametrize("cursor", (1, 2, 8, 15, 0x8000, 0xffff))
def test_hiscore_key_input_backspace_steps_left(cursor):
    """Backspace decrements the cursor and redraws it — unless `bge` says otherwise, and `bge` after
    a `subq` tests N == V. 0x8000 is where that bites: 0x8000 - 1 = 0x7fff OVERFLOWS, so it compares
    as negative and the cursor is CLAMPED, where reading the stored 0x7fff as signed would redraw."""
    _key_case(cursor, KEY_BACKSPACE)


def test_hiscore_key_input_backspace_at_column_zero_clamps_and_does_not_redraw():
    """Column 0 is the one case that stores 0xffff and then clamps it back — and, because the
    redraw hangs off the same signed test, the one that leaves the screen untouched."""
    info = _key_case(0, KEY_BACKSPACE)
    assert not _painted(info["writes"]), "column 0 still redrew the cursor"
    assert _stored(info["writes"], A_HISCORE_CURSOR, 2) == 0


def test_hiscore_key_input_return_before_any_input_is_ignored():
    """RETURN with draw_rows still 0: the entry has not been touched, so it just returns."""
    _key_case(4, KEY_RETURN)


@pytest.mark.parametrize("touched", (1, 0x8000, 0xffff))
def test_hiscore_key_input_return_finishes_the_entry(touched):
    """...and once it has, RETURN drops the caller's return address and jumps back into _start. Any
    non-zero draw_rows counts (the original tests it with `tst.w`), and the jump really is a jump:
    the `rts` is unreachable, which nothing but the failed run below would show — no memory effect
    distinguishes the two branches."""
    pokes = _entry_pokes(4, key=KEY_RETURN, touched=touched)
    _never_returns(pokes, ENTRY_HISCORE_KEY_INPUT)
    diffs, info = differential(ENTRY_HISCORE_KEY_INPUT, {"_pokes": pokes}, _key_entry,
                               stop_pc=RESTART_ENTRY)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_RESTART


@pytest.mark.parametrize("key", tuple(range(KEY_UPPER_A, KEY_UPPER_Z + 1)) + (KEY_SPACE,))
def test_hiscore_key_input_accepts_upper_case_and_space(key):
    """Every accepted key is stored under the cursor, drawn, and the cursor stepped on."""
    _key_case(5, key)


@pytest.mark.parametrize("key", tuple(range(KEY_LOWER_A, KEY_LOWER_A + 26)))
def test_hiscore_key_input_folds_lower_case(key):
    """a-z lose 0x20 and are then accepted as the upper-case letter."""
    _key_case(6, key)


def test_hiscore_key_input_stores_the_folded_letter():
    """The byte that reaches draw_dst_off is the FOLDED one, not what was typed."""
    info = _key_case(2, KEY_LOWER_A + 25)                     # 'z'
    assert _stored(info["writes"], A_HISCORE_LETTER) == KEY_UPPER_Z


@pytest.mark.parametrize("key", (0x00, 0x01, 0x07, 0x09, 0x1f, 0x21, 0x30, 0x39, 0x40, 0x5b, 0x60,
                                 0x7b, 0x7f, 0x80, 0x9a, 0xc1, 0xda, 0xe1, 0xff))
def test_hiscore_key_input_rejects_everything_else(key):
    """The two range tests are SIGNED byte compares over a value the fold has already changed:
    0x9a folds to 0x7a and fails the upper end, while 0xda/0xe1 fold to 0xba/0xc1 — negative — and
    fail the LOWER one. An unsigned reading of either test would accept a different set."""
    assert not _painted(_key_case(7, key)["writes"]), f"key {key:#04x} was accepted"


def test_hiscore_key_input_cursor_stops_at_the_last_column():
    """A letter typed in the last column advances the cursor past the end, which clamps it back —
    and, on that path only, does NOT redraw the cursor bar."""
    info = _key_case(HISCORE_COLUMNS - 1, KEY_UPPER_A)
    assert _stored(info["writes"], A_HISCORE_CURSOR, 2) == HISCORE_COLUMNS - 1


def test_hiscore_key_input_cursor_clamp_is_unsigned():
    """0xffff + 1 wraps to 0, which the UNSIGNED clamp lets through — so the cursor is redrawn at
    column 0 rather than pinned at the last column. A signed compare would take the other branch."""
    info = _key_case(0xffff, KEY_UPPER_A)
    assert _stored(info["writes"], A_HISCORE_CURSOR, 2) == 0
    assert _painted(info["writes"]), "a wrapped cursor should still redraw the bar"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_hiscore_key_input_fuzz(chunk):
    """All 256 key bytes across the columns a name entry reaches, each with a random scancode in
    Bconin's high word. draw_rows is left 0 throughout, so RETURN simply returns and every case has
    an `rts` to diff at."""
    rng = random.Random(0x44d4)
    cases = [(key, rng.randrange(HISCORE_COLUMNS), rng.randint(0, 0xffff), rng.randint(0, 0xff))
             for key in range(0x100)]
    ran = 0
    for index, (key, cursor, scancode, letter) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _entry_pokes(cursor, key=key, letter=letter, scancode=scancode, seed=index)
        diffs, info = differential(ENTRY_HISCORE_KEY_INPUT, {"_pokes": pokes}, _key_entry)
        assert not diffs, (f"key={key:#04x} cursor={cursor} letter={letter:#04x} "
                           f"scancode={scancode:#06x}\n{report(diffs)}")
        assert info["ret"] == INPUT_CONTINUE
        ran += 1
    assert ran, "this shard ran no cases"


# ------------------------------------------------------------------ hiscore_joystick_input @ 0x14538
#
# ENTERED AT THE IKBD WAIT LOOP (0x1454e), not at 0x14538 — the one place in this layer where the
# oracle is started inside a routine. The three instructions before the loop clear ikbd_packet and
# send XBIOS Ikbdws the "interrogate joysticks" command; the reply then arrives on an IKBD interrupt
# the oracle never runs, and Ikbdws itself has no image effect, so the spin cannot end. Staging the
# reply and entering AT the loop is what TRAP_MODEL.md's governing rule prescribes — the packet
# becomes an ordinary poked input both cores read — and it leaves exactly the clear, the Ikbdws and
# the blocking behaviour unverified. test_ikbd_wait_never_ends_from_the_routines_own_entry below
# pins that limit rather than leaving it as a claim.

def _joystick(lib, buf):
    return lib.g_hiscore_joystick_input(buf)


def _joystick_pokes(stick, other_stick=0, owner=A_PLAYER2, delay=0, cursor=4,
                    letter=STAGED_LETTER, touched=0, seed=0):
    """The entry screen plus an IKBD reply packet staged where the wait loop expects to find it.

    `stick` is the byte for the joystick the entering player owns and `other_stick` the one it must
    NOT read — distinct, so picking the wrong half of the packet shows.
    """
    pokes = _entry_pokes(cursor, letter=letter, touched=touched, seed=seed)
    joystick_0, joystick_1 = (stick, other_stick) if owner == A_PLAYER2 else (other_stick, stick)
    pokes[A_IKBD_PACKET] = struct.pack(">I", IKBD_PACKET_BUF)
    pokes[IKBD_PACKET_BUF] = bytes([joystick_0, joystick_1])
    pokes[A_HISCORE_STICK] = struct.pack(">I", owner)
    pokes[A_REPEAT_DELAY] = bytes([delay])
    return pokes


def _joystick_case(stick, expected=INPUT_CONTINUE, poison=True, **staging):
    pokes = _joystick_pokes(stick, **staging)
    diffs, info = differential(ENTRY_IKBD_WAIT, {"_pokes": pokes}, _joystick, poison=poison)
    assert not diffs, f"stick={stick:#04x} {staging}\n{report(diffs)}"
    assert info["ret"] == expected
    return info


@pytest.mark.parametrize("owner", (A_PLAYER2, A_OBJECT_TABLE, A_PLAYER2 + 1, A_PLAYER2 - 1,
                                  A_PLAYER2 | 0xffff0000, 0))
def test_hiscore_joystick_input_reads_the_entering_players_stick(owner):
    """Player 2 reads the packet's first byte, anyone else the second — a FULL `cmpi.l`, so a
    pointer one byte either side of player 2's slot already counts as somebody else, and so does one
    that differs only ABOVE the low word. The two bytes move opposite directions, so reading the
    wrong one steps the letter the wrong way."""
    _joystick_case(JOY_UP, other_stick=JOY_DOWN, owner=owner, seed=owner & 0xff)


@pytest.mark.parametrize("touched", (0, 1))
def test_hiscore_joystick_input_fire_finishes_the_entry(touched):
    """Fire ends the entry — but only once the stick has been moved at least once, and that flag is
    set AFTER the fire test, so fire on the very first poll is ignored."""
    if not touched:
        _joystick_case(JOY_FIRE, touched=0)
        return
    pokes = _joystick_pokes(JOY_FIRE, touched=1)
    _never_returns(pokes, ENTRY_IKBD_WAIT)
    diffs, info = differential(ENTRY_IKBD_WAIT, {"_pokes": pokes}, _joystick, stop_pc=RESTART_ENTRY)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_RESTART


@pytest.mark.parametrize("stick", (0x00, 0x10, 0x20, 0x40, 0x70))
def test_hiscore_joystick_input_centred_resets_the_repeat(stick):
    """No direction bit set: the auto-repeat counter is cleared so the next push acts at once, and
    nothing else happens. The high bits above the fire bit are ignored by `and.b #$f`."""
    info = _joystick_case(stick, delay=5)
    assert _stored(info["writes"], A_REPEAT_DELAY) == 0
    assert not _painted(info["writes"]), "a centred stick still redrew"


@pytest.mark.parametrize("delay", (2, 3, 6, 7, 0x7f))
def test_hiscore_joystick_input_repeat_counts_down_without_acting(delay):
    """A counter still positive after the decrement means the held direction is between repeats."""
    info = _joystick_case(JOY_UP, delay=delay)
    assert not _painted(info["writes"]), f"delay {delay} acted early"


@pytest.mark.parametrize("delay,reloaded", ((1, REPEAT_DELAY_NEXT),      # hit exactly 0 -> repeat
                                            (0, REPEAT_DELAY_FIRST),     # first frame of a push
                                            (0xff, REPEAT_DELAY_FIRST),
                                            (0x80, REPEAT_DELAY_FIRST),  # subq OVERFLOWS: `blt`
                                            (0x81, REPEAT_DELAY_FIRST)))
def test_hiscore_joystick_input_repeat_reloads_and_acts(delay, reloaded):
    """Reaching zero reloads the SHORT delay and acting from a negative counter reloads the long
    one. 0x80 is the case that separates the 68000's `blt` (N != V) from a signed test of the stored
    byte: 0x80 - 1 = 0x7f, which as a byte looks positive but overflowed, so it takes `blt`."""
    info = _joystick_case(JOY_UP, delay=delay)
    assert _stored(info["writes"], A_REPEAT_DELAY) == reloaded
    assert _painted(info["writes"]), f"delay {delay:#04x} should have acted"


@pytest.mark.parametrize("letter,stepped", ((KEY_UPPER_A, KEY_UPPER_A + 1),
                                            (KEY_UPPER_Z, KEY_SPACE),      # off the letters...
                                            (KEY_SPACE, KEY_UPPER_A),      # ...and off the space
                                            (0x00, 0x01), (0xff, 0x00)))
def test_hiscore_joystick_input_up_steps_the_letter(letter, stepped):
    """Up walks ' ' -> 'A' -> ... -> 'Z' -> ' '. The second wrap test re-reads the byte, which is
    what turns a step off ' ' (0x21) into 'A' in the same frame."""
    info = _joystick_case(JOY_UP, delay=0, letter=letter, seed=letter)
    assert _stored(info["writes"], A_HISCORE_LETTER) == stepped


@pytest.mark.parametrize("letter,stepped", ((KEY_UPPER_Z, KEY_UPPER_Z - 1),
                                            (KEY_UPPER_A, KEY_SPACE),
                                            (KEY_SPACE, KEY_UPPER_Z),
                                            (0x00, 0xff), (0x21, 0x20)))
def test_hiscore_joystick_input_down_steps_the_letter(letter, stepped):
    """...and down walks it back the other way, through the same two wraps."""
    info = _joystick_case(JOY_DOWN, delay=0, letter=letter, seed=letter)
    assert _stored(info["writes"], A_HISCORE_LETTER) == stepped


@pytest.mark.parametrize("cursor", (0, 1, 8, HISCORE_COLUMNS - 1, 0x8000, 0xffff))
def test_hiscore_joystick_input_left_and_right_move_the_cursor(cursor):
    """Left and right enter the same two shared tails backspace and an accepted letter use, so the
    clamps at both ends — and the `bge` overflow at 0x8000 — are the same ones."""
    _joystick_case(JOY_LEFT, cursor=cursor, seed=cursor & 0xff)
    _joystick_case(JOY_RIGHT, cursor=cursor, seed=cursor & 0xff)


def test_hiscore_joystick_input_direction_priority():
    """All four directions at once: the tests run up, down, left, right and the first wins."""
    info = _joystick_case(JOY_DIRECTIONS, delay=0, letter=KEY_UPPER_A)
    assert _stored(info["writes"], A_HISCORE_LETTER) == KEY_UPPER_A + 1


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_hiscore_joystick_input_fuzz(chunk):
    """Every stick byte against random counters, letters, cursors and stick owners. draw_rows is
    left 0, so fire simply returns and every case has an `rts` to diff at."""
    rng = random.Random(0x4538)
    cases = [(stick, rng.randint(0, 0xff), rng.randint(0, 0xff), rng.randrange(HISCORE_COLUMNS),
              rng.choice((A_PLAYER2, A_OBJECT_TABLE)))
             for stick in range(0x100)]
    ran = 0
    for index, (stick, delay, letter, cursor, owner) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _joystick_pokes(stick, other_stick=(~stick) & 0xff, owner=owner, delay=delay,
                                cursor=cursor, letter=letter, seed=index)
        diffs, info = differential(ENTRY_IKBD_WAIT, {"_pokes": pokes}, _joystick)
        assert not diffs, (f"stick={stick:#04x} delay={delay:#04x} letter={letter:#04x} "
                           f"cursor={cursor} owner={owner:#x}\n{report(diffs)}")
        assert info["ret"] == INPUT_CONTINUE
        ran += 1
    assert ran, "this shard ran no cases"


@pytest.mark.parametrize("entry,label", ((ENTRY_HISCORE_JOYSTICK_INPUT, "hiscore_joystick_input"),
                                         (ENTRY_READ_JOYSTICKS, "read_joysticks")))
def test_ikbd_wait_never_ends_from_the_routines_own_entry(entry, label):
    """THE MODEL LIMIT THIS LAYER IS BOUNDED BY, pinned for both routines that hit it.

    Each clears ikbd_packet, sends the IKBD its interrogate command with XBIOS Ikbdws — which the
    model swallows, no image effect — and then spins until an interrupt handler fills the packet in.
    The oracle runs no interrupts, and the routine's own `clr.l` wipes anything the harness poked
    beforehand, so the spin never ends whatever is staged. That is why hiscore_joystick_input is
    verified from its wait loop instead, and why read_joysticks is not reconstructed at all.
    """
    _never_returns(_joystick_pokes(JOY_UP), entry)


# ------------------------------------------------------------------ mirrored-constant pins
#
# Mandatory, not bookkeeping: a drifted address here would be INVISIBLE to the differential. The
# test would stage its inputs at a dead address, both cores would read the game's own static data at
# the real one, agree, and the suite would go green having proved nothing.


def test_entry_and_checkpoint_addresses_match_names_txt_and_the_c():
    """Every address the oracle is entered at is the one names.txt gives that function, and every
    checkpoint lies inside the routine it belongs to."""
    for addr, name in ((ENTRY_POLL_QUIT_KEY, "poll_quit_key"),
                       (ENTRY_HISCORE_KEY_INPUT, "hiscore_key_input"),
                       (ENTRY_HISCORE_JOYSTICK_INPUT, "hiscore_joystick_input"),
                       (ENTRY_READ_JOYSTICKS, "read_joysticks")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"
    assert _defines("include/input.h")["RESTART_ENTRY"] == RESTART_ENTRY
    for checkpoint, _, label in QUIT_TRAP_CALLS:
        assert ENTRY_POLL_QUIT_KEY < checkpoint < CHECKPOINT_BEFORE_PTERM + 2, \
            f"{label}'s checkpoint is outside poll_quit_key"
    assert CHECKPOINT_BEFORE_PTERM < ENTRY_PAUSE_LOOP < ENTRY_HISCORE_KEY_INPUT, \
        "the pause loop is not in poll_quit_key's tail, past the Pterm the quit path ends at"
    assert ENTRY_HISCORE_JOYSTICK_INPUT < ENTRY_IKBD_WAIT, \
        "the IKBD wait loop is not inside hiscore_joystick_input"


def test_mirrored_constants_match_input_h():
    _pin(_defines("include/input.h"), "input.h", {
        "A_saved_mousevec": A_SAVED_MOUSEVEC, "A_saved_joyvec": A_SAVED_JOYVEC,
        "A_saved_rez": A_SAVED_REZ, "A_conterm_save": A_CONTERM_SAVE,
        "A_ikbd_cmd_reset": A_IKBD_CMD_RESET, "A_saved_palette": A_SAVED_PALETTE,
        "A_snd_list_silence": A_SND_LIST_SILENCE,
        "A_ikbd_cmd_mouse_rel": A_IKBD_CMD_MOUSE_REL,
        "A_fname_highsco": A_FNAME_HIGHSCO, "A_hiscore_dirty": A_HISCORE_DIRTY,
        "A_ikbd_packet": A_IKBD_PACKET, "A_repeat_delay": A_REPEAT_DELAY,
        "A_ikbd_cmd_joyread": A_IKBD_CMD_JOYREAD,
        "INPUT_CONTINUE": INPUT_CONTINUE, "INPUT_RESTART": INPUT_RESTART, "INPUT_QUIT": INPUT_QUIT,
    })
    # Three of the addresses this file stages through are ALIASES in the C (of the sprite-draw
    # scratch the entry screen borrows, and of draw_x), so `_defines` never sees them: pin the
    # addresses they alias instead, exactly as test_score.py does.
    _pin(_defines("include/object.h"), "object.h", {"A_draw_x": A_QUIT_FILE_HANDLE})
    _pin(_defines("include/addrs.h"), "addrs.h", {
        "A_screen_base": A_SCREEN_BASE, "A_object_table": A_OBJECT_TABLE,
        "A_draw_shift": A_HISCORE_CURSOR, "A_draw_rows": A_HISCORE_TOUCHED,
        "A_draw_src": A_HISCORE_STICK,
    })
    _pin(_defines("include/draw.h"), "draw.h", {
        "A_draw_dst_off": A_HISCORE_LETTER, "A_text_ptr": A_TEXT_PTR,
        "A_player2": A_PLAYER2, "TEXT_FLAG_LARGE_FONT": TEXT_FLAG_LARGE_FONT,
    })
    _pin(_defines("include/score.h"), "score.h", {"A_hiscore_name": A_HISCORE_NAME})


def test_mirrored_constants_match_input_c_and_the_kit():
    _pin(_defines("src/input.c"), "input.c", {
        "HISCORE_RECORD_BYTES": HISCORE_RECORD_BYTES, "HIGHSCO_OPEN_MODE": HIGHSCO_OPEN_MODE,
        "TOS_CONTERM": TOS_CONTERM, "KBDV_MOUSEVEC": KBDV_MOUSEVEC, "KBDV_JOYVEC": KBDV_JOYVEC,
        "KEY_CTRL_C": KEY_CTRL_C,
        "KEY_PAUSE_UPPER": KEY_PAUSE_UPPER, "KEY_PAUSE_LOWER": KEY_PAUSE_LOWER,
        "KEY_RESTART_UPPER": KEY_RESTART_UPPER, "KEY_RESTART_LOWER": KEY_RESTART_LOWER,
        "KEY_BACKSPACE": KEY_BACKSPACE, "KEY_RETURN": KEY_RETURN, "KEY_SPACE": KEY_SPACE,
        "KEY_UPPER_A": KEY_UPPER_A, "KEY_UPPER_Z": KEY_UPPER_Z, "KEY_LOWER_A": KEY_LOWER_A,
        "HISCORE_COLUMNS": HISCORE_COLUMNS,
        "JOY_FIRE": JOY_FIRE, "JOY_UP": JOY_UP, "JOY_DOWN": JOY_DOWN, "JOY_LEFT": JOY_LEFT,
        "JOY_RIGHT": JOY_RIGHT, "JOY_DIRECTIONS": JOY_DIRECTIONS,
        "IKBD_JOYSTICK_1": IKBD_PACKET_JOYSTICK_1,
        "REPEAT_DELAY_FIRST": REPEAT_DELAY_FIRST, "REPEAT_DELAY_NEXT": REPEAT_DELAY_NEXT,
        # The four wrap thresholds are what make the alphabet ' ' + 'A'..'Z' rather than a plain
        # byte counter, and the differential is the only thing that could otherwise catch them.
        "LETTER_PAST_Z": KEY_UPPER_Z + 1, "LETTER_PAST_SPACE": KEY_SPACE + 1,
        "LETTER_BEFORE_A": KEY_UPPER_A - 1, "LETTER_BEFORE_SPACE": KEY_SPACE - 1,
        "PAUSE_LEFT_ON_KEY": PAUSE_LEFT_ON_KEY, "PAUSE_NO_KEY": PAUSE_NO_KEY,
    })
    _pin(_defines("../../../tools/recreate_kit/include/os.h"), "os.h", {
        "OS_KBDVBASE": OS_KBDVBASE, "OS_BIOS_DEV_CON": 2,
    })
    # The text engine's five fields are staged as ONE `>IBBBB` poke, which only reaches the right
    # bytes while they are consecutive in this order.
    draw_h = _defines("include/draw.h")
    assert [draw_h[name] - A_TEXT_PTR for name in ("A_text_shift", "A_text_color",
                                                   "A_text_bg_color", "A_text_flags")] == \
        [4, 5, 6, 7], "the text-engine globals are no longer the block _entry_pokes packs"


def test_painted_band_covers_what_the_entry_screen_draws():
    """The noise band must really span both painted rows, or an absent redraw would land on zeros
    and `_painted` would be reading an empty region."""
    score_c = _defines("src/score.c")
    for name in ("HISCORE_ENTRY_OFF", "HISCORE_UNDERLINE_OFF"):
        assert PAINTED_BAND_OFF <= score_c[name] < PAINTED_BAND_OFF + PAINTED_BAND_LEN, \
            f"score.c's {name} is outside the noise band this file stages"
    assert score_c["HISCORE_UNDERLINE_OFF"] < SCREEN_SPAN, "SCREEN_SPAN misses the painted rows"


def test_global_names_match_names_txt():
    """...and every one of those addresses is the global names.txt says it is."""
    for addr, name in ((A_SAVED_MOUSEVEC, "saved_mousevec"), (A_SAVED_JOYVEC, "saved_joyvec"),
                       (A_CONTERM_SAVE, "conterm_save"), (A_QUIT_FILE_HANDLE, "draw_x"),
                       (A_FNAME_HIGHSCO, "fname_highsco"), (A_HISCORE_DIRTY, "hiscore_dirty"),
                       (A_HISCORE_NAME, "hiscore_name"), (A_SCREEN_BASE, "screen_base"),
                       (A_HISCORE_CURSOR, "draw_shift"), (A_HISCORE_TOUCHED, "draw_rows"),
                       (A_HISCORE_LETTER, "draw_dst_off"), (A_TEXT_PTR, "text_ptr"),
                       (A_HISCORE_STICK, "draw_src"), (A_IKBD_PACKET, "ikbd_packet"),
                       (A_IKBD_CMD_JOYREAD, "ikbd_cmd_joyread"),
                       (A_OBJECT_TABLE, "object_table"), (A_PLAYER2, "player2")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"
