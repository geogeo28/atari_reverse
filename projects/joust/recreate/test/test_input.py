"""Differential tests for Joust's input layer (src/input.c).

Covered here: poll_quit_key @ 0x11c24 (with its pause loop @ 0x11d64), hiscore_key_input @ 0x144d4,
hiscore_joystick_input @ 0x14538 and check_highscore @ 0x1437a (with its name-entry loop, entered at
its colour-cycle tail @ 0x14494). read_joysticks @ 0x11d9a shares this layer's IKBD wait and is
covered in test_player.py, beside the control_player calls that are its whole body; the limit both
routines meet is pinned here, for both entries, by
test_ikbd_wait_never_ends_from_the_routines_own_entry.

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
    survive to end the wait. Every routine that waits is therefore entered AT its wait loop with
    the reply staged. The prologue in front of it is a separate question per routine:
    read_joysticks' is checkpointed (test_player.py) and title_screen's is diffed inside its
    attract pass, while hiscore_joystick_input's 0x14538..0x1454d is not reconstructed at all.
"""
import collections
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
ENTRY_READ_JOYSTICKS = 0x11d9a    # reconstructed in test_player.py; only its wait is pinned here
ENTRY_CHECK_HIGHSCORE = 0x1437a
ENTRY_HISCORE_FLASH_TAIL = 0x14494  # check_highscore's colour-cycle tail, entered directly

# ---- checkpoint PCs (harness `stop_pc`) ----
CHECKPOINT_BEFORE_PTERM = 0x11d4c  # stop here: the quit path's last image effect has run and
                                   # what follows is the `addq.w #4,a7` and GEMDOS Pterm's push+trap
PTERM_RETURN_PC = 0x11d56         # where the unmodeled Pterm trap would return, if it ever did
RESTART_ENTRY = 0x10006            # _start+6, where R/r jumps and never returns
CHECKPOINT_ENTRY_LOOP = 0x1448e    # the head of check_highscore's name-entry loop: its whole setup
                                   # has run and the first `bsr` has not
CHECKPOINT_JOYSTICK_CALL = 0x14490  # ...one keyboard poll later, at the `bsr` no run comes back from

# ---- the INPUT_* results src/input.c reports its exit with ----
INPUT_CONTINUE, INPUT_RESTART, INPUT_QUIT = 0, 1, 2

# ---- ...and the CHECK_HIGHSCORE_* ones its high-score check reports ----
CHECK_HIGHSCORE_RETURNED, CHECK_HIGHSCORE_ENTERED, CHECK_HIGHSCORE_RESTART = 0, 1, 2

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
A_ENEMY_OBJECTS = 0x10fd2          # slot 2: where the tie-walk runs off the end of the two players
A_GAME_OVER_FLAG = 0x10d12
A_HISCORE_SCORE = 0x183a9          # the record holder's 7 digits, the tail of hiscore_name's record
A_TEXT_COLOR = 0x10e0f             # ...the rest of the text engine's block, past A_TEXT_PTR
A_TEXT_BG_COLOR = 0x10e10
A_TEXT_FLAGS = 0x10e11
A_HISCORE_FLASH = A_QUIT_FILE_HANDLE     # draw_x again: the pen-10 colour-cycle counter
A_HISCORE_FLASH_PASSES = 0x10dee   # draw_y's HIGH half: colour-cycle steps owed this loop pass
OBJ_SCORE_FIRST_DIGIT = 0x3e       # into an object record: its 7 ASCII score digits
STR_HISCORE_P1, STR_HISCORE_P2 = 0x18301, 0x18341   # the two "YOU HAVE HIGH SCORE PLAYER n" banners

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

# ---- the two reply-buffer addresses that make the SHARED wait's WIDTH observable ----
#
# src/input.c's wait_for_ikbd_packet spins on all four bytes of the ikbd_packet longword, and every
# battery that enters a wait needs the width pinned. An ordinary scratch buffer cannot do it: a
# pointer's non-zero bytes are the only ones a narrowed wait has to read, so a wait that ignored the
# bytes a given buffer leaves ZERO behaves identically on every case staged there. These two exist
# for nothing but that, and each kills a different narrowing — with the pointer non-zero ONLY in the
# byte named, a wait that skips that byte reads all-zero, never terminates, and the battery's
# wall-clock deadline turns it into an ordinary red:
#
#   * HIGH_ZERO: non-zero only in byte 2, so a wait reading `packet[0] | packet[1]` dies;
#   * LSB_ONLY:  non-zero only in byte 3, so a wait reading `packet[0] | packet[1] | packet[2]` dies.
#
# Byte 0 has no such buffer and can have none: every address inside a 0x100000-byte image has its
# most significant byte zero, so no legal pointer separates a wait that reads it from one that does
# not. That one byte is pinned against the ORIGINAL'S encoding instead.
#
# Both sit below the load base (0x10000) and above the kit's poked input block (0x600..0x61f), so
# they belong to no layer's staging. THEY LIVE HERE, not in the batteries, because the wait they
# probe is ONE function: test_init.py and test_player.py both import them rather than spelling the
# addresses twice (CLAUDE.md §5 — one canonical definition, never a copy per file).
IKBD_PACKET_BUF_HIGH_ZERO = 0x00c000
IKBD_PACKET_BUF_LSB_ONLY = 0x0000f0

# ---- the name-entry screen's staging ----
# A scratch screen clear of the program (which ends 0x2b7ae), of abi's stub space and of the staged
# file table. The band is where draw_hiscore_entry (screen_base + 0x52b0) and draw_hiscore_cursor
# (+ 0x57b0) paint; it is filled with noise so an absent or spurious redraw shows as a diff.
SCREEN = 0x70000
SCREEN_SPAN = 0x8000
PAINTED_BAND_OFF, PAINTED_BAND_LEN = 0x5200, 0x700
TEXT_COLOR, TEXT_BG_COLOR, TEXT_FLAG_LARGE_FONT, TEXT_FLAG_BACKGROUND = 6, 0, 0x80, 0x10
STAGED_LETTER = 0x5a               # what sits under the cursor before a key arrives

# ---- the XBIOS calls the quit path makes (the GEMDOS ones are imported above) ----
XBIOS_SETSCREEN, XBIOS_SETPALETTE, XBIOS_IKBDWS, XBIOS_KBDVBASE = 0x05, 0x06, 0x19, 0x22

HISCORE_RECORD_BYTES = 0x1a        # what Fwrite pushes out of hiscore_name
HIGHSCO_OPEN_MODE = 2              # GEMDOS Fopen mode 2 = read/write
HIGHSCO_NAME = "HIGH.SCO"

# ---- check_highscore's own constants (mirrors of src/input.c) ----
HISCORE_SCORE_DIGITS = 7           # what the copy walks, and what the comparisons MEANT to
HISCORE_DIRTY_SET = 0x20
HISCORE_ENTRY_COLOR = 6
HISCORE_FLASH_PASSES = 1
HISCORE_FLASH_DELAY_SPINS = 0x3e80
HISCORE_RECORD_PAD = A_HISCORE_SCORE - A_HISCORE_NAME   # the name plus the string's control bytes

# A spin that never ends is capped rather than run to the harness default: these cases exist to show
# the oracle does NOT terminate, so the cap is the whole point and a small one keeps them cheap.
SPIN_CAP = 2_000

# check_highscore's loop is the exception: reaching it costs ~35,400 instructions and one blocked
# pass ~32,000 more, so a small cap would prove only that the run is slow. This one is chosen large
# enough that a run which was going to come back would have done so several times over.
HISCORE_ENTRY_SPIN_CAP = 200_000

# The candidate has no such cap, so every call into its pause spin runs under a wall-clock deadline
# instead (see _pause_glue). Absurdly generous for a loop that leaves on its first pass, and only
# ever waited out by a candidate that is not leaving the loop at all.
PAUSE_GLUE_TIMEOUT_S = 5

FUZZ_CHUNKS = 4

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _ret in (("g_poll_quit_key", ctypes.c_uint32),
                    ("g_pause_until_key", ctypes.c_uint32),
                    ("g_hiscore_key_input", ctypes.c_uint32),
                    ("g_hiscore_joystick_input", ctypes.c_uint32),
                    ("g_check_highscore", ctypes.c_uint32),
                    ("g_hiscore_entry_pass", ctypes.c_uint32)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P]
    _fn.restype = _ret

# The kit's refused-os_*-call recorder (include/os.h), called directly by the pin below.
harness._lib.os_refused.argtypes = [ctypes.c_int32]
harness._lib.os_refused.restype = ctypes.c_int32


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


def _program_writes(writes):
    """The addresses the run wrote OUTSIDE the oracle's own machine stack — `bsr` return addresses
    and trap arguments land in the band the differential drops (emu.STACK_GUARD_LO), so a test
    asserting on the exact set of program writes has to drop them too.

    Named for the program rather than the image because test_wave.py's `_image_writes` is a
    different helper (it takes `info` and returns a dict), and one name for two shapes is how a
    caller ends up passing the wrong thing and silently asserting on `info`'s own keys."""
    return {addr for addr in writes if addr < emu.STACK_GUARD_LO}


def _never_returns(pokes, entry, cap=SPIN_CAP):
    """Assert the original does not come back from `entry` on this input.

    The `stop_pc` runs elsewhere would pass just as happily on a routine that fell through to `rts`
    — osh_run stops at the sentinel or the checkpoint and reports success either way — so every
    checkpointed branch is paired with this.

    `cap` MUST leave room for everything the checkpointed run does before it blocks, or the pair
    degenerates into "this routine is slower than `cap`" (see HISCORE_ENTRY_SPIN_CAP).
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(pokes), entry, max_insns=cap)


# ------------------------------------------------------------------ poll_quit_key: the plain exits

def test_poll_quit_key_no_key_returns_at_once():
    """Bconstat says nothing is waiting, so the routine returns without reading the console.

    That it does not read is self-proving rather than asserted: Bconin with nothing pending is
    REFUSED by the model, so a run that reached it would be rejected as fabricated, not diffed.
    """
    diffs, info = differential(ENTRY_POLL_QUIT_KEY, {}, _poll, poison=True)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_CONTINUE


def test_a_candidate_side_refusal_fails_the_case():
    """WHAT MAKES THE TEST ABOVE MEAN ANYTHING — and the module comment's closed asymmetry.

    A refused os_* call used to reject the ORACLE's run only, so a candidate that dropped
    poll_console_key's Bconstat gate called Bconin with nothing pending, got 0, touched nothing, and
    left every case green. The kit now tallies the candidate's refusals too. Deleting the real gate
    is how that was measured; this pins the wiring — reset, tally, raise — permanently, without
    mutating the reconstruction: the glue itself refuses one call, exactly as os.h's helpers do.
    """
    def refusing_glue(lib, buf):
        lib.os_refused(0)                       # os.h's answer when a helper cannot be served
        return _poll(lib, buf)

    with pytest.raises(AssertionError, match="REFUSES to serve"):
        differential(ENTRY_POLL_QUIT_KEY, {}, refusing_glue)


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
    beforehand, so the spin never ends whatever is staged. That is why BOTH routines are verified
    from their wait loop instead, with the prologue in front of it checkpointed on its own
    (read_joysticks' half of that is in test_player.py).
    """
    _never_returns(_joystick_pokes(JOY_UP), entry)


# ================================================================== check_highscore @ 0x1437a
#
# Three exits, verified three ways.
#
#   * NOT GAME OVER, and A SCORE THAT DID NOT BEAT THE RECORD, both `rts` — ordinary differential
#     cases, and between them the whole of the two score comparisons.
#   * A NEW RECORD, which never returns: the routine drops its caller's return address
#     (`addq.w #4,a7`) and falls into a loop with no exit instruction. The setup is diffed at
#     CHECKPOINT_ENTRY_LOOP, PAIRED with a `_never_returns` proof — without which a run that fell
#     through to `rts` would stop at the sentinel and pass just as happily.
#   * THE LOOP ITSELF, which no run entered at 0x1437a can even complete one pass of: the joystick
#     reader blocks in its IKBD wait (see the section above) on the first pass, whatever is staged.
#     It is verified entered at the colour-cycle tail (0x14494) instead, running round the branch at
#     0x144ae and through the keyboard poll, and stopped at the joystick call it never comes back
#     from. That is also why g_check_highscore refuses the loop rather than forwarding into it.
#
# The two comparisons carry the ORIGINAL'S COUNTER-DESTRUCTION BUG, and `_walk_scores` below is an
# independent model of it: every case states how far the walk went as well as who won, so a
# reconstruction that stopped after seven bytes fails on where the answer came from, not just on
# the answer.

WALK_MODEL_LIMIT = 4_000    # a walk this long is a runaway, not a case: fail rather than hang


def _signed(byte):
    return byte - 0x100 if byte > 0x7f else byte


def _walk_scores(image, left, right):
    """(verdict, bytes walked) for the original's score comparison — an INDEPENDENT model.

    `move.b #$7,d0` sets a seven-character count and `move.b (a0)+,d0` overwrites it with the
    character on the spot, so the only thing `subq.b #1,d0 / bne` can end the loop on is a character
    equal to 1. Two strings that agree therefore walk PAST both records. Both `cmp.b` operands are
    signed; the verdict is +1 for `left`, -1 for `right`, and 0 for the character-of-1 stop, which
    the two call sites resolve in OPPOSITE directions.
    """
    for step in range(WALK_MODEL_LIMIT):
        character, against = _signed(image[left + step]), _signed(image[right + step])
        if character > against:
            return 1, step + 1
        if character < against:
            return -1, step + 1
        if character == 1:
            return 0, step + 1
    raise AssertionError(f"the walk from {left:#x}/{right:#x} ran past {WALK_MODEL_LIMIT} bytes")


def _check(lib, buf):
    return lib.g_check_highscore(buf)


def _entry_pass(lib, buf):
    return lib.g_hiscore_entry_pass(buf)


def _score_pokes(p1, p2, hiscore, game_over=1, extra=None):
    """A finished game with three seven-digit score strings staged.

    The record's digits go in as part of the whole 26-byte HIGH.SCO record, its name half filled
    with a sentinel — so a reconstruction reading the record's score from anywhere but
    A_HISCORE_SCORE would compare against 0x5a bytes and diverge.
    """
    for string in (p1, p2, hiscore):
        assert len(string) == HISCORE_SCORE_DIGITS, f"{string!r} is not a score string"
    pokes = {A_SCREEN_BASE: struct.pack(">I", SCREEN),
             A_GAME_OVER_FLAG: bytes([game_over]),
             A_HISCORE_STICK: struct.pack(">I", UNWRITTEN_L),
             A_OBJECT_TABLE + OBJ_SCORE_FIRST_DIGIT: p1,
             A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT: p2,
             A_HISCORE_NAME: bytes([UNWRITTEN_B]) * HISCORE_RECORD_PAD + hiscore}
    pokes.update(extra or {})
    return pokes


# What the model says the routine will do with a staged case: who leads and over how many bytes,
# then whether that leader beats the record and over how many. Both comparisons come off ONE build
# of the very image the case will run, so there is a single place a case's staging is interpreted.
_Model = collections.namedtuple("_Model", "leader leader_walk beats record_walk")


def _model(pokes):
    image = harness.make_image(pokes)
    verdict, leader_walk = _walk_scores(image, A_OBJECT_TABLE + OBJ_SCORE_FIRST_DIGIT,
                                        A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT)
    leader = A_PLAYER2 if verdict < 0 else A_OBJECT_TABLE
    beats, record_walk = _walk_scores(image, leader + OBJ_SCORE_FIRST_DIGIT, A_HISCORE_SCORE)
    return _Model(leader, leader_walk, beats > 0, record_walk)


def _return_case(pokes, expected_leader, poison=True):
    """One of the two paths that really do `rts`. `expected_leader` is None when the run should not
    even reach the comparison (not game over), and the object slot draw_src must name otherwise."""
    diffs, info = differential(ENTRY_CHECK_HIGHSCORE, {"_pokes": pokes}, _check, poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] == CHECK_HIGHSCORE_RETURNED
    if expected_leader is None:
        assert not _program_writes(info["writes"]), "a run that is not game over wrote something"
    else:
        assert _program_writes(info["writes"]) == set(range(A_HISCORE_STICK, A_HISCORE_STICK + 4)), \
            "the returning path wrote something other than draw_src"
        assert _stored(info["writes"], A_HISCORE_STICK, 4) == expected_leader
    return info


# ---- the two returning exits ----

UNBEATABLE = b"\x7f" * HISCORE_SCORE_DIGITS   # signed-maximum bytes: no score can compare greater
# ...and a record every ASCII score beats. Every digit of it differs from the scores staged against
# it below, so a copy one byte short of seven shows up in the PLAIN diff — with a record sharing the
# winner's trailing '0's, only the poison pass could tell (measured with a mutation).
BEATABLE = b"\x01" + b"2" * (HISCORE_SCORE_DIGITS - 1)


def test_check_highscore_returns_at_once_when_the_game_is_not_over():
    """`tst.b game_over_flag` is the first instruction, and a clear byte returns before the routine
    has read a single score — staged here with a record-beating score, so what stops it is the flag
    and nothing else."""
    _return_case(_score_pokes(b"9999990", b"0000000", BEATABLE, game_over=0), None)


@pytest.mark.parametrize("game_over", (1, 2, 0x80, 0xff))
def test_check_highscore_runs_on_any_non_zero_game_over_flag(game_over):
    """`tst.b`, not a compare against 1."""
    _return_case(_score_pokes(b"1000000", b"0000000", UNBEATABLE, game_over=game_over),
                 A_OBJECT_TABLE)


@pytest.mark.parametrize("position", range(HISCORE_SCORE_DIGITS))
@pytest.mark.parametrize("winner", (A_OBJECT_TABLE, A_PLAYER2))
def test_check_highscore_picks_the_higher_score(position, winner):
    """The leader is decided digit by digit, most significant first — the first position at which
    the two strings differ settles it, at every one of the seven."""
    high = b"0" * position + b"1" + b"0" * (HISCORE_SCORE_DIGITS - position - 1)
    low = b"0" * HISCORE_SCORE_DIGITS
    p1, p2 = (high, low) if winner == A_OBJECT_TABLE else (low, high)
    pokes = _score_pokes(p1, p2, UNBEATABLE)
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (winner, position + 1)
    _return_case(pokes, winner)


def test_the_player_comparison_is_signed():
    """`bgt`/`blt` after `cmp.b` are SIGNED. 0x80 is the most negative byte, so it LOSES to 0x7f —
    an unsigned reading of the same two bytes would hand the win to the other player."""
    pokes = _score_pokes(b"\x80" + b"0" * 6, b"\x7f" + b"0" * 6, UNBEATABLE)
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (A_PLAYER2, 1)
    _return_case(pokes, A_PLAYER2)


@pytest.mark.parametrize("position", range(HISCORE_SCORE_DIGITS))
def test_a_score_below_the_record_returns_without_touching_anything_else(position):
    """The second comparison's `blt` arm: the leader's score is smaller at `position`, so the
    routine returns having written only draw_src."""
    record = b"9" * (position + 1) + b"0" * (HISCORE_SCORE_DIGITS - position - 1)
    score = b"9" * position + b"1" + b"0" * (HISCORE_SCORE_DIGITS - position - 1)
    pokes = _score_pokes(score, b"0" * HISCORE_SCORE_DIGITS, record)
    model = _model(pokes)
    assert (model.beats, model.record_walk) == (False, position + 1)
    _return_case(pokes, A_OBJECT_TABLE)


def test_the_record_comparison_is_signed():
    """The same signedness on the second comparison — and the one place it changes the EXIT rather
    than the answer: read unsigned, 0x80 would beat 0x7f and the run would never return at all.

    The 0x80 sits in the SECOND digit because 0x80 is the smallest signed byte there is, so a
    leading one could never make player 1 the leader in the first place.
    """
    pokes = _score_pokes(b"9\x80" + b"0" * 5, b"0\x80" + b"0" * 5, b"9\x7f" + b"0" * 5)
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (A_OBJECT_TABLE, 1)
    assert (model.beats, model.record_walk) == (False, 2)
    _return_case(pokes, A_OBJECT_TABLE)


# ---- the counter-destruction bug ----

P1_PAST_DIGITS = A_OBJECT_TABLE + OBJ_SCORE_FIRST_DIGIT + HISCORE_SCORE_DIGITS
P2_PAST_DIGITS = A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT + HISCORE_SCORE_DIGITS
RECORD_PAST_DIGITS = A_HISCORE_SCORE + HISCORE_SCORE_DIGITS


@pytest.mark.parametrize("winner", (A_OBJECT_TABLE, A_PLAYER2))
def test_equal_scores_walk_past_the_seven_digits(winner):
    """THE BUG. With both players on the same seven digits the walk does not stop — it carries on
    into the byte AFTER each record's digits, and that byte picks the winner.

    A reconstruction that honoured the `move.b #$7,d0` count would tie here and fall through to
    player 1 in both directions, so the player-2 case is the one that fails it.
    """
    high, low = b"\x40", b"\x20"
    p1_past, p2_past = (high, low) if winner == A_OBJECT_TABLE else (low, high)
    pokes = _score_pokes(b"1234560", b"1234560", UNBEATABLE,
                         extra={P1_PAST_DIGITS: p1_past, P2_PAST_DIGITS: p2_past})
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (winner, HISCORE_SCORE_DIGITS + 1), \
        "the walk stopped at the digits"
    _return_case(pokes, winner)


def test_a_character_of_one_ends_the_player_walk_at_player_1():
    """The only thing that CAN end the walk on equal strings: `subq.b #1` on a character of 1 sets
    Z, and the `bne` then drops into player 1's store. Staged with the byte past the digits
    favouring player 2, so a walk that did not stop would give the opposite answer."""
    score = b"12\x014560"
    pokes = _score_pokes(score, score, UNBEATABLE,
                         extra={P1_PAST_DIGITS: b"\x20", P2_PAST_DIGITS: b"\x40"})
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (A_OBJECT_TABLE, 3), "the 0x01 did not stop the walk"
    _return_case(pokes, A_OBJECT_TABLE)


def test_a_score_equal_to_the_record_walks_past_it_and_returns():
    """The same walk on the second comparison, resolved the other way: the byte past the record's
    digits is the smaller, so this is NOT a new record and the routine returns."""
    pokes = _score_pokes(b"1234560", b"0000000", b"1234560",
                         extra={P1_PAST_DIGITS: b"\x20", RECORD_PAST_DIGITS: b"\x40"})
    model = _model(pokes)
    assert (model.beats, model.record_walk) == (False, HISCORE_SCORE_DIGITS + 1)
    _return_case(pokes, A_OBJECT_TABLE)


def test_a_character_of_one_ends_the_record_walk_as_NOT_a_new_record():
    """...and the character-of-1 stop resolves the OPPOSITE way here: `bne` falls through to the
    `rts` at 0x143de. The byte past the digits would have made this a new record, so a
    reconstruction that missed the stop would never return instead of returning."""
    score = b"12\x014560"
    pokes = _score_pokes(score, b"\x00" * HISCORE_SCORE_DIGITS, score,
                         extra={P1_PAST_DIGITS: b"\x40", RECORD_PAST_DIGITS: b"\x20"})
    model = _model(pokes)
    assert (model.beats, model.record_walk) == (False, 3)
    _return_case(pokes, A_OBJECT_TABLE)


def test_how_far_the_walk_really_goes_on_the_shipped_object_table():
    """THE MEASUREMENT src/input.c's comment quotes, pinned rather than asserted in prose.

    With the two players on identical digits and nothing else staged, the walk runs 79 bytes: past
    player 1's record and into player 2's, so what settles it is PLAYER 2's own score digits
    (which the case staged) against enemy slot 2's (which it did not).
    """
    pokes = _score_pokes(b"1000000", b"1000000", UNBEATABLE)
    model = _model(pokes)
    assert (model.leader, model.leader_walk) == (A_OBJECT_TABLE, 79)

    # BOTH ends, or the claim is only half asserted: the walk that started on the two players'
    # digits ends comparing player 2's own against enemy slot 2's, a whole record further on.
    last = model.leader_walk - 1
    assert A_OBJECT_TABLE + OBJ_SCORE_FIRST_DIGIT + last == A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT, \
        "the walk no longer lands on player 2's digits"
    assert A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT + last == A_ENEMY_OBJECTS + OBJ_SCORE_FIRST_DIGIT, \
        "the walk no longer lands on enemy slot 2's digits"
    _return_case(pokes, model.leader)


# ---- the new-record path: the entry screen, at a checkpoint ----

def _entry_screen_pokes(p1, p2, hiscore, seed=0, extra=None):
    """The staging both the checkpointed case and its `_never_returns` pair use — so the pair
    really is the same case. Every destination the setup writes carries a sentinel first, and the
    whole framebuffer is noise, so an absent fill or an absent redraw shows as a diff."""
    rng = random.Random(seed)
    pokes = _score_pokes(p1, p2, hiscore)
    pokes.update({A_HISCORE_DIRTY: bytes([UNWRITTEN_B]),
                  A_TEXT_PTR: struct.pack(">IBBBB", UNWRITTEN_L, UNWRITTEN_B,
                                          UNWRITTEN_B, UNWRITTEN_B, 0),
                  A_REPEAT_DELAY: bytes([UNWRITTEN_B]),
                  A_HISCORE_CURSOR: struct.pack(">H", UNWRITTEN_W),
                  A_HISCORE_TOUCHED: struct.pack(">H", UNWRITTEN_W),
                  A_HISCORE_LETTER: struct.pack(">H", UNWRITTEN_W),
                  SCREEN: rng.randbytes(SCREEN_SPAN)})
    pokes.update(extra or {})
    return pokes


def _entry_screen_case(pokes, expected_leader, poison=False):
    """Diff the new-record path at the head of the loop it never leaves, and check what it left."""
    diffs, info = differential(ENTRY_CHECK_HIGHSCORE, {"_pokes": pokes}, _check,
                               stop_pc=CHECKPOINT_ENTRY_LOOP, poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] == CHECK_HIGHSCORE_ENTERED
    assert _stored(info["writes"], A_HISCORE_STICK, 4) == expected_leader
    assert info["regs"]["dosound"] == [A_SND_LIST_SILENCE], \
        "the entry screen did not silence the YM2149 with the expected Dosound list"
    return info


@pytest.mark.parametrize("leader", (A_OBJECT_TABLE, A_PLAYER2))
def test_check_highscore_puts_up_the_entry_screen(leader):
    """A new record: silence the chip, mark the record dirty, take the leader's seven digits, clear
    the screen, draw that player's banner, blank the name, set the entry's text state and paint the
    cursor. Both banners are covered by the two arms — the strings differ, so a wrong one shows as
    a screenful of diffs rather than as a missing assertion."""
    score, other = b"9000000", b"1000000"
    p1, p2 = (score, other) if leader == A_OBJECT_TABLE else (other, score)
    pokes = _entry_screen_pokes(p1, p2, BEATABLE, seed=leader)
    info = _entry_screen_case(pokes, leader)

    writes = info["writes"]
    assert _stored(writes, A_HISCORE_DIRTY) == HISCORE_DIRTY_SET
    assert bytes(writes[A_HISCORE_SCORE + n] for n in range(HISCORE_SCORE_DIGITS)) == score
    assert bytes(writes[A_HISCORE_NAME + n] for n in range(HISCORE_COLUMNS)) == \
        bytes([KEY_SPACE]) * HISCORE_COLUMNS
    assert _stored(writes, A_TEXT_COLOR) == HISCORE_ENTRY_COLOR
    assert _stored(writes, A_TEXT_BG_COLOR) == 0
    assert _stored(writes, A_TEXT_FLAGS) & TEXT_FLAG_BACKGROUND
    assert _stored(writes, A_REPEAT_DELAY) == 0
    assert _stored(writes, A_HISCORE_TOUCHED, 2) == 0
    assert _stored(writes, A_HISCORE_CURSOR, 2) == 0
    assert _stored(writes, A_HISCORE_LETTER, 2) == KEY_SPACE << 8
    assert _painted(writes), "the entry screen painted nothing"


@pytest.mark.parametrize("leader", (A_OBJECT_TABLE, A_PLAYER2))
def test_check_highscore_entry_screen_never_returns(leader):
    """The pair CHECKPOINT_ENTRY_LOOP needs, over the same staging: `stop_pc` reports success at the
    sentinel too, so without this a run that quietly fell through to `rts` would look identical."""
    score, other = b"9000000", b"1000000"
    p1, p2 = (score, other) if leader == A_OBJECT_TABLE else (other, score)
    _never_returns(_entry_screen_pokes(p1, p2, BEATABLE, seed=leader), ENTRY_CHECK_HIGHSCORE,
                   cap=HISCORE_ENTRY_SPIN_CAP)


def test_the_entry_screen_copies_exactly_seven_score_bytes():
    """The copy at 0x1440a is the one loop of the three whose counter SURVIVES (`move.b (a0)+,(a1)+`
    leaves d0 alone), so it really does move seven bytes — and it starts at the record's digits, not
    at the end of the name: the three bytes between are left untouched."""
    info = _entry_screen_case(_entry_screen_pokes(b"9000000", b"1000000", BEATABLE), A_OBJECT_TABLE)
    touched = {addr for addr in info["writes"]
               if A_HISCORE_NAME <= addr < A_HISCORE_NAME + HISCORE_RECORD_BYTES}
    assert touched == set(range(A_HISCORE_NAME, A_HISCORE_NAME + HISCORE_COLUMNS)) \
        | set(range(A_HISCORE_SCORE, RECORD_PAST_DIGITS))


def test_check_highscore_entry_screen_poison():
    """The attribution pass, on one shape rather than all of them: it re-runs BOTH cores on an image
    whose 32,000-odd oracle-written bytes are inverted, which is expensive and — since the record's
    own digits are among them — also a different comparison. Still a valid case (the poisoned record
    is smaller, so it is still beaten), and it is what catches a byte the candidate never writes."""
    _entry_screen_case(_entry_screen_pokes(b"9000000", b"1000000", BEATABLE), A_OBJECT_TABLE,
                       poison=True)


# ---- the entry loop, one pass at a time ----

def _flash_pass_pokes(counter=0, key=None, cursor=4, seed=0):
    """The entry screen as the setup really leaves it, plus the colour-cycle counter under test.

    text_flags carries the BACKGROUND bit as well as the large font, because that is what
    show_hiscore_entry_screen sets (`bset #4,text_flags` at 0x1445a) — `_entry_pokes` alone stages
    only the font, which would drive the redraw down a branch the real screen never reaches.

    ikbd_packet is staged HERE rather than by the one case that reads it, so the checkpointed pass
    and the `_never_returns` twin that pairs with it run on identical input — which is what that
    helper's docstring asks for. It changes nothing about the checkpointed run (which stops before
    the joystick reader) and is what lets the blocking case assert the reader cleared it.
    """
    pokes = _entry_pokes(cursor, key=key, seed=seed)
    pokes[A_TEXT_FLAGS] = bytes([TEXT_FLAG_LARGE_FONT | TEXT_FLAG_BACKGROUND])
    pokes[A_IKBD_PACKET] = struct.pack(">I", IKBD_PACKET_BUF)
    pokes[A_HISCORE_FLASH] = struct.pack(">H", counter)
    pokes[A_HISCORE_FLASH_PASSES] = bytes([UNWRITTEN_B])
    return pokes


@pytest.mark.parametrize("counter", (0, 1, 6, 7, 0x7fff, 0xffff))
def test_hiscore_entry_pass_cycles_the_colour_and_polls_the_keyboard(counter):
    """One pass of the loop, entered at the colour-cycle tail: set the pass count, spin the delay,
    step flash_hiscore_color ONCE, fall out of the `subq.b`/`bne`, branch back to the loop head and
    poll the keyboard. With nothing staged at the console that poll returns at once, so the only
    memory this pass touches is the two-byte counter and the pass count itself."""
    pokes = _flash_pass_pokes(counter)
    diffs, info = differential(ENTRY_HISCORE_FLASH_TAIL, {"_pokes": pokes}, _entry_pass,
                               stop_pc=CHECKPOINT_JOYSTICK_CALL, poison=True)
    assert not diffs, f"counter={counter:#x}\n{report(diffs)}"
    assert info["ret"] == INPUT_CONTINUE
    # +1, not +HISCORE_FLASH_PASSES: this is flash_hiscore_color's own `addq.w #1` (src/score.c),
    # a different constant that happens to share the value.
    assert _stored(info["writes"], A_HISCORE_FLASH, 2) == (counter + 1) & 0xffff
    assert _program_writes(info["writes"]) == {A_HISCORE_FLASH, A_HISCORE_FLASH + 1,
                                             A_HISCORE_FLASH_PASSES}
    assert _stored(info["writes"], A_HISCORE_FLASH_PASSES) == 0, \
        "the pass count did not count down to zero"


def test_hiscore_entry_pass_reaches_the_keyboard_reader():
    """...and the poll it ends with is the real hiscore_key_input: with 'A' staged the pass also
    types a letter, steps the cursor and repaints — which is the only thing separating a loop that
    calls the reader from one that merely returns.

    NO `_never_returns` TWIN, and it does not need one: the pair exists to rule out a checkpointed
    run that quietly fell through to `rts`, and a run that had done that could not have painted the
    letter this case asserts on. The blocking case below carries the proof for this entry point.
    """
    pokes = _flash_pass_pokes(counter=3, key=KEY_UPPER_A, seed=0x448e)
    diffs, info = differential(ENTRY_HISCORE_FLASH_TAIL, {"_pokes": pokes}, _entry_pass,
                               stop_pc=CHECKPOINT_JOYSTICK_CALL)
    assert not diffs, report(diffs)
    assert info["ret"] == INPUT_CONTINUE
    assert _stored(info["writes"], A_HISCORE_LETTER) == KEY_UPPER_A
    assert _painted(info["writes"]), "the keyboard poll drew nothing"


def test_the_entry_loop_blocks_in_the_joystick_readers_ikbd_wait():
    """WHY THE LOOP IS VERIFIED A PASS AT A TIME. The second `bsr` of every pass enters
    hiscore_joystick_input at its own head, which clears ikbd_packet and waits for a reply an IKBD
    interrupt delivers — so the pass never finishes, whatever the harness stages.

    Oracle-only, deliberately: the reconstruction starts at the wait loop and has no prologue to
    clear the packet, so there is no candidate side to diff. The positive half (the run really does
    get that far, and really does clear the packet) is what stops this being a hang anywhere else.
    """
    pokes = _flash_pass_pokes()
    image, writes, _ = emu.run(harness.make_image(pokes), ENTRY_HISCORE_FLASH_TAIL,
                               stop_pc=ENTRY_IKBD_WAIT)
    assert set(range(A_IKBD_PACKET, A_IKBD_PACKET + 4)) <= set(writes), \
        "the joystick reader's prologue did not clear ikbd_packet"
    assert int.from_bytes(bytes(image[A_IKBD_PACKET:A_IKBD_PACKET + 4]), "big") == 0
    _never_returns(pokes, ENTRY_HISCORE_FLASH_TAIL, cap=HISCORE_ENTRY_SPIN_CAP)


# ---- fuzz ----

_WALK_BYTES = (b"0123456789" + bytes((0x00, 0x01, 0x20, 0x2f, 0x3a, 0x7f, 0x80, 0x81, 0xff)))


def _fuzz_score(rng):
    return bytes(rng.choice(_WALK_BYTES) for _ in range(HISCORE_SCORE_DIGITS))


def _walk_fuzz_cases():
    """Random score pairs, a fifth of them deliberately IDENTICAL so the walk runs off the end of
    the records — the corpus is generated whole and sharded afterwards, so every shard sees the
    same cases whatever order they are scheduled in."""
    rng = random.Random(0x1437a)
    cases = []
    for _ in range(120):
        p1 = _fuzz_score(rng)
        cases.append((p1, p1 if rng.randrange(5) == 0 else _fuzz_score(rng)))
    return cases


def test_the_walk_fuzz_corpus_reaches_all_three_verdicts():
    """The corpus has to exercise what it claims to: both winners, the character-of-1 stop, and at
    least one walk that runs PAST the seven digits. Without this a corpus that quietly stopped
    covering the bug would still shard cleanly and pass."""
    outcomes = set()
    longest = 0
    for p1, p2 in _walk_fuzz_cases():
        pokes = _score_pokes(p1, p2, UNBEATABLE)
        image = harness.make_image(pokes)
        verdict, walked = _walk_scores(image, A_OBJECT_TABLE + OBJ_SCORE_FIRST_DIGIT,
                                       A_PLAYER2 + OBJ_SCORE_FIRST_DIGIT)
        outcomes.add(verdict)
        longest = max(longest, walked)
    assert outcomes == {-1, 0, 1}, f"the corpus reaches only {sorted(outcomes)}"
    assert longest > HISCORE_SCORE_DIGITS, "no case walks past the seven digits"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_check_highscore_walk_fuzz(chunk):
    """The player comparison over the whole corpus, against an unbeatable record so every case has
    an `rts` to diff at — and every case checked against the model, so a pass cannot be vacuous."""
    ran = 0
    for index, (p1, p2) in enumerate(_walk_fuzz_cases()):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _score_pokes(p1, p2, UNBEATABLE)
        _return_case(pokes, _model(pokes).leader, poison=False)
        ran += 1
    assert ran, "this shard ran no cases"


def _record_fuzz_cases():
    """Score/record pairs for the SECOND comparison, a third of them equal for the seven digits."""
    rng = random.Random(0x143d2)
    cases = []
    for _ in range(24):
        score = _fuzz_score(rng)
        cases.append((score, score if rng.randrange(3) == 0 else _fuzz_score(rng)))
    return cases


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_check_highscore_record_fuzz(chunk):
    """The record comparison, with the model deciding BOTH which player leads and which exit the
    case takes: a beaten record is diffed at the entry loop and paired with its own `never returns`,
    everything else at `rts`. Player 2 is left on the shipped zeros, so the leader is usually player
    1 — but a fuzzed score can lose to them, and the model says which."""
    ran, beaten = 0, 0
    for index, (score, record) in enumerate(_record_fuzz_cases()):
        if index % FUZZ_CHUNKS != chunk:
            continue
        pokes = _entry_screen_pokes(score, b"\x00" * HISCORE_SCORE_DIGITS, record, seed=index)
        model = _model(pokes)
        if model.beats:
            _entry_screen_case(pokes, model.leader)
            _never_returns(pokes, ENTRY_CHECK_HIGHSCORE, cap=HISCORE_ENTRY_SPIN_CAP)
            beaten += 1
        else:
            _return_case(pokes, model.leader, poison=False)
        ran += 1
    assert ran, "this shard ran no cases"
    assert beaten, "this shard never reached the entry screen"


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
                       (ENTRY_READ_JOYSTICKS, "read_joysticks"),
                       (ENTRY_CHECK_HIGHSCORE, "check_highscore")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"
    assert _defines("include/input.h")["RESTART_ENTRY"] == RESTART_ENTRY
    for checkpoint, _, label in QUIT_TRAP_CALLS:
        assert ENTRY_POLL_QUIT_KEY < checkpoint < CHECKPOINT_BEFORE_PTERM + 2, \
            f"{label}'s checkpoint is outside poll_quit_key"
    assert CHECKPOINT_BEFORE_PTERM < ENTRY_PAUSE_LOOP < ENTRY_HISCORE_KEY_INPUT, \
        "the pause loop is not in poll_quit_key's tail, past the Pterm the quit path ends at"
    assert ENTRY_HISCORE_JOYSTICK_INPUT < ENTRY_IKBD_WAIT, \
        "the IKBD wait loop is not inside hiscore_joystick_input"
    assert ENTRY_CHECK_HIGHSCORE < CHECKPOINT_ENTRY_LOOP < CHECKPOINT_JOYSTICK_CALL \
        < ENTRY_HISCORE_FLASH_TAIL < A_FLASH_HISCORE_COLOR, \
        "check_highscore's entry loop is not inside check_highscore"


# The four call targets and the two immediates that carry check_highscore's whole shape, none of
# which any single differential case can separate from a neighbouring instruction. Pinned against
# the ORIGINAL'S OWN ENCODING, the way test_player.py pins its checkpoints: a `bsr` displacement,
# a relocated string pointer, or the delay count drifting fails here rather than quietly diffing
# somewhere else. Each entry is (address, width, expected).
BSR = 0x6100      # `bsr`: the low byte is the short displacement, or 0 for the .w form below
MOVE_L_IMM_PUSH, CMPI_L_ABS, MOVE_B_IMM_ABS, MOVE_W_IMM_D0 = 0x2f3c, 0x0cb9, 0x13fc, 0x303c
ADDQ_W_4_A7 = 0x584f

# The four routines check_highscore reaches by `bsr`, and where it calls each from. draw_string and
# fill_screen are `jsr`s with the callee spelled out, so they need no displacement arithmetic.
A_DRAW_HISCORE_CURSOR, A_FLASH_HISCORE_COLOR = 0x14658, 0x144b0
CALL_DRAW_HISCORE_CURSOR = 0x1448a     # `bsr.w`, the last instruction of the entry-screen setup
CALL_HISCORE_KEY_INPUT = 0x1448e       # `bsr.s`, the loop head (== CHECKPOINT_ENTRY_LOOP)
CALL_FLASH_HISCORE_COLOR = 0x144a4     # `bsr.s`, inside the colour-cycle tail
BSR_CALLS = ((CALL_DRAW_HISCORE_CURSOR, A_DRAW_HISCORE_CURSOR),
             (CALL_HISCORE_KEY_INPUT, ENTRY_HISCORE_KEY_INPUT),
             (CHECKPOINT_JOYSTICK_CALL, ENTRY_HISCORE_JOYSTICK_INPUT),
             (CALL_FLASH_HISCORE_COLOR, A_FLASH_HISCORE_COLOR))

# ...and the immediates, each named for the instruction it belongs to rather than left as bare hex.
DROP_RETURN_ADDRESS = 0x143e0          # `addq.w #4,a7` — why the new-record path never returns
BANNER_PLAYER_TEST = 0x1441e           # `cmpi.l #object_table,draw_src`
BANNER_P1_PUSH, BANNER_P2_PUSH = 0x1442a, 0x1443a     # `move.l #str_hiscore_pN,-(a7)`
FLASH_DELAY_LOAD = 0x1449c             # `move.w #$3e80,d0`, the spin the differential cannot see


def _image_word(addr):
    return int.from_bytes(bytes(harness.BASE_IMAGE[addr:addr + 2]), "big")


def _image_long(addr):
    return int.from_bytes(bytes(harness.BASE_IMAGE[addr:addr + 4]), "big")


def _bsr_target(addr):
    """Where the `bsr` at `addr` goes: a short displacement in the opcode's low byte, or — when
    that byte is 0 — the extension word that follows. BOTH are SIGNED: read unsigned, a backward
    `bsr` (or a short displacement of 0x80 and up) would resolve thousands of bytes away, and a pin
    that exists to catch a call drifting would be the thing doing the drifting."""
    opcode = _image_word(addr)
    assert opcode & 0xff00 == BSR, f"{addr:#x} is not a bsr ({opcode:#06x})"
    short = opcode & 0xff
    displacement = struct.unpack(">b", bytes([short]))[0] if short \
        else struct.unpack(">h", bytes(harness.BASE_IMAGE[addr + 2:addr + 4]))[0]
    return addr + 2 + displacement


@pytest.mark.parametrize("site,callee", BSR_CALLS)
def test_check_highscore_calls_the_routines_it_claims_to(site, callee):
    """A `bsr` displacement is not something a single differential case can separate from a
    neighbouring instruction, so it is pinned against the ORIGINAL'S OWN ENCODING — the way
    test_player.py pins its checkpoints."""
    assert _bsr_target(site) == callee
    assert harness.NAME_MAP.get(callee), f"names.txt has no function at {callee:#x}"


def test_check_highscores_immediates_are_the_instructions_they_claim_to_be():
    """The banner selection, its two string pointers, the pass count and the delay. The last is the
    ONE constant of this routine the differential cannot see at all — a register-only spin with no
    memory effect — so this encoding is the whole of its evidence."""
    assert (_image_word(BANNER_PLAYER_TEST), _image_long(BANNER_PLAYER_TEST + 2),
            _image_long(BANNER_PLAYER_TEST + 6)) \
        == (CMPI_L_ABS, A_OBJECT_TABLE, A_HISCORE_STICK), "the banner's player test moved"
    assert (_image_word(BANNER_P1_PUSH), _image_long(BANNER_P1_PUSH + 2)) \
        == (MOVE_L_IMM_PUSH, STR_HISCORE_P1)
    assert (_image_word(BANNER_P2_PUSH), _image_long(BANNER_P2_PUSH + 2)) \
        == (MOVE_L_IMM_PUSH, STR_HISCORE_P2)

    assert (_image_word(ENTRY_HISCORE_FLASH_TAIL), _image_long(ENTRY_HISCORE_FLASH_TAIL + 4)) \
        == (MOVE_B_IMM_ABS, A_HISCORE_FLASH_PASSES)
    assert _image_word(ENTRY_HISCORE_FLASH_TAIL + 2) == HISCORE_FLASH_PASSES
    assert (_image_word(FLASH_DELAY_LOAD), _image_word(FLASH_DELAY_LOAD + 2)) \
        == (MOVE_W_IMM_D0, HISCORE_FLASH_DELAY_SPINS)

    # The instruction that makes the new-record path never return. It is a STACK write, which the
    # diff drops, so no differential case can see it either; the C reports it as
    # CHECK_HIGHSCORE_ENTERED / CHECK_HIGHSCORE_RESTART, and this is that claim's only pin.
    assert _image_word(DROP_RETURN_ADDRESS) == ADDQ_W_4_A7, \
        "the caller's return address is no longer dropped"


def test_the_high_score_record_is_one_block():
    """A_hiscore_score is the tail of the same 26 bytes HIGH.SCO carries and save_hiscore writes
    back, not an address of its own — so the name, the padding and the digits must still add up."""
    assert A_HISCORE_NAME + HISCORE_RECORD_PAD == A_HISCORE_SCORE
    assert HISCORE_RECORD_PAD + HISCORE_SCORE_DIGITS == HISCORE_RECORD_BYTES
    assert HISCORE_RECORD_PAD > HISCORE_COLUMNS, "the name would run into the score digits"


def test_mirrored_constants_match_input_h():
    _pin(_defines("include/input.h"), "input.h", {
        "A_saved_mousevec": A_SAVED_MOUSEVEC, "A_saved_joyvec": A_SAVED_JOYVEC,
        "A_saved_rez": A_SAVED_REZ, "A_conterm_save": A_CONTERM_SAVE,
        "A_ikbd_cmd_reset": A_IKBD_CMD_RESET, "A_saved_palette": A_SAVED_PALETTE,
        "A_ikbd_cmd_mouse_rel": A_IKBD_CMD_MOUSE_REL,
        "A_fname_highsco": A_FNAME_HIGHSCO, "A_hiscore_dirty": A_HISCORE_DIRTY,
        "A_ikbd_packet": A_IKBD_PACKET, "A_repeat_delay": A_REPEAT_DELAY,
        "A_ikbd_cmd_joyread": A_IKBD_CMD_JOYREAD,
        "IKBD_JOYSTICK_1": IKBD_PACKET_JOYSTICK_1,
        "A_hiscore_score": A_HISCORE_SCORE,
        "STR_HISCORE_P1": STR_HISCORE_P1, "STR_HISCORE_P2": STR_HISCORE_P2,
        "INPUT_CONTINUE": INPUT_CONTINUE, "INPUT_RESTART": INPUT_RESTART, "INPUT_QUIT": INPUT_QUIT,
        "CHECK_HIGHSCORE_RETURNED": CHECK_HIGHSCORE_RETURNED,
        "CHECK_HIGHSCORE_ENTERED": CHECK_HIGHSCORE_ENTERED,
        "CHECK_HIGHSCORE_RESTART": CHECK_HIGHSCORE_RESTART,
    })
    # Five of the addresses this file stages through are ALIASES in the C (of the sprite-draw
    # scratch the entry screen and the quit path borrow: draw_x, draw_shift, draw_rows, draw_src,
    # draw_y), so `_defines` never sees them: pin the addresses they alias instead, exactly as
    # test_score.py does.
    _pin(_defines("include/object.h"), "object.h", {"A_draw_x": A_QUIT_FILE_HANDLE})
    _pin(_defines("include/addrs.h"), "addrs.h", {
        "A_screen_base": A_SCREEN_BASE, "A_object_table": A_OBJECT_TABLE,
        "A_enemy_objects": A_ENEMY_OBJECTS,
        "A_draw_shift": A_HISCORE_CURSOR, "A_draw_rows": A_HISCORE_TOUCHED,
        "A_draw_src": A_HISCORE_STICK, "A_draw_y": A_HISCORE_FLASH_PASSES,
    })
    _pin(_defines("include/draw.h"), "draw.h", {
        "A_draw_dst_off": A_HISCORE_LETTER, "A_text_ptr": A_TEXT_PTR,
        "A_player2": A_PLAYER2, "TEXT_FLAG_LARGE_FONT": TEXT_FLAG_LARGE_FONT,
        "A_text_color": A_TEXT_COLOR, "A_text_bg_color": A_TEXT_BG_COLOR,
        "A_text_flags": A_TEXT_FLAGS, "TEXT_FLAG_BACKGROUND": TEXT_FLAG_BACKGROUND,
    })
    _pin(_defines("include/score.h"), "score.h", {
        "A_hiscore_name": A_HISCORE_NAME, "A_game_over_flag": A_GAME_OVER_FLAG,
        "OBJ_SCORE_FIRST_DIGIT": OBJ_SCORE_FIRST_DIGIT,
    })
    # Two constants the input layer reads but no longer owns, because title_screen (src/init.c)
    # became a second reader of each: the quit key it tests to reach the same quit tail, and the
    # Dosound list it silences the chip with.
    _pin(_defines("include/input.h"), "input.h", {"KEY_CTRL_C": KEY_CTRL_C})
    _pin(_defines("include/sound.h"), "sound.h", {"A_snd_list_silence": A_SND_LIST_SILENCE})


def test_mirrored_constants_match_input_c_and_the_kit():
    _pin(_defines("src/input.c"), "input.c", {
        "HISCORE_RECORD_BYTES": HISCORE_RECORD_BYTES, "HIGHSCO_OPEN_MODE": HIGHSCO_OPEN_MODE,
        "TOS_CONTERM": TOS_CONTERM, "KBDV_MOUSEVEC": KBDV_MOUSEVEC, "KBDV_JOYVEC": KBDV_JOYVEC,
        "KEY_PAUSE_UPPER": KEY_PAUSE_UPPER, "KEY_PAUSE_LOWER": KEY_PAUSE_LOWER,
        "KEY_RESTART_UPPER": KEY_RESTART_UPPER, "KEY_RESTART_LOWER": KEY_RESTART_LOWER,
        "KEY_BACKSPACE": KEY_BACKSPACE, "KEY_RETURN": KEY_RETURN, "KEY_SPACE": KEY_SPACE,
        "KEY_UPPER_A": KEY_UPPER_A, "KEY_UPPER_Z": KEY_UPPER_Z, "KEY_LOWER_A": KEY_LOWER_A,
        "HISCORE_COLUMNS": HISCORE_COLUMNS,
        "JOY_FIRE": JOY_FIRE, "JOY_UP": JOY_UP, "JOY_DOWN": JOY_DOWN, "JOY_LEFT": JOY_LEFT,
        "JOY_RIGHT": JOY_RIGHT, "JOY_DIRECTIONS": JOY_DIRECTIONS,
        "REPEAT_DELAY_FIRST": REPEAT_DELAY_FIRST, "REPEAT_DELAY_NEXT": REPEAT_DELAY_NEXT,
        # The four wrap thresholds are what make the alphabet ' ' + 'A'..'Z' rather than a plain
        # byte counter, and the differential is the only thing that could otherwise catch them.
        "LETTER_PAST_Z": KEY_UPPER_Z + 1, "LETTER_PAST_SPACE": KEY_SPACE + 1,
        "LETTER_BEFORE_A": KEY_UPPER_A - 1, "LETTER_BEFORE_SPACE": KEY_SPACE - 1,
        "PAUSE_LEFT_ON_KEY": PAUSE_LEFT_ON_KEY, "PAUSE_NO_KEY": PAUSE_NO_KEY,
        "HISCORE_SCORE_DIGITS": HISCORE_SCORE_DIGITS, "HISCORE_DIRTY_SET": HISCORE_DIRTY_SET,
        "HISCORE_ENTRY_COLOR": HISCORE_ENTRY_COLOR, "HISCORE_FLASH_PASSES": HISCORE_FLASH_PASSES,
        "HISCORE_FLASH_DELAY_SPINS": HISCORE_FLASH_DELAY_SPINS,
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
                       (A_OBJECT_TABLE, "object_table"), (A_PLAYER2, "player2"),
                       (A_ENEMY_OBJECTS, "enemy_objects"),
                       (A_GAME_OVER_FLAG, "game_over_flag"), (A_HISCORE_SCORE, "hiscore_score"),
                       (A_HISCORE_FLASH_PASSES, "draw_y"), (A_TEXT_COLOR, "text_color"),
                       (A_TEXT_BG_COLOR, "text_bg_color"), (A_TEXT_FLAGS, "text_flags"),
                       (STR_HISCORE_P1, "str_hiscore_p1"), (STR_HISCORE_P2, "str_hiscore_p2")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"
