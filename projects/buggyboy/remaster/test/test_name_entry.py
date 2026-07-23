"""test_name_entry.py — the high-score NAME-ENTRY tail (slice F) vs recreate.

update_highscore stops at the ranking checkpoint (test_flow_machine); when a leg-end score MADE the
table (results_mode == 0) the game runs an interactive initials screen, and when it MISSED (mode == 2)
a short game-over screen. This pins that tail:

  hiscore_countdown   one frame's "TIME nn" countdown tick        (differential vs g_hiscore_countdown)
  hiscore_charstep    one frame's initials selection              (differential vs g_hiscore_charstep)
  name-entry loop     the initials screen's sequencing + bookkeeping   (recording driver + directed)
  game-over tail      the missed-the-table redraw                 (recording driver)

The per-frame countdown/charstep are ORACLE-DIFFED (like init_playfield's nav/fire slices — the loop
that sequences them never returns under the oracle). The loop itself is a FlowOps driver: its SEQUENCING
(the prime/terminal draws, the per-frame draw/flash/show/poll order) is pinned STRUCTURALLY (a recording
log), and its own bookkeeping (the initials written into row+8, the confirm/backspace/timeout termination,
the rank cleared) directly. The name-entry jingle + the terminal sound/IKBD waits are off-image seams the
game ships without.
"""
import adapter
import equiv

FIRE = 0x80


# ---- per-frame countdown (g_hiscore_countdown) ----
def _cd_image(sub, timer):
    state = bytearray(equiv.bench_frame.IMAGE_SIZE)
    equiv._w16(state, adapter.A_countdown_sub, sub & 0xffff)
    equiv._w16(state, adapter.A_countdown_timer, timer & 0xffff)
    return state


def test_hiscore_countdown():
    """countdown_sub advance + 'TIME nn' render; timeout when the timer underflows. Sweeps the sub across
    the 0x11 tick boundary and the timer across its tens/units + underflow (a timeout off-by-one diverges
    either the return or the digits)."""
    lib = equiv._lib()
    for sub in (0, 1, 0x10, 0x11, 0x12, 0x20):
        for timer in (0, 1, 5, 9, 10, 11, 20, 30):
            bad, ret_c, ret_r = equiv.compare_hiscore_countdown(lib, _cd_image(sub, timer))
            assert not bad, f"sub={sub:#x} timer={timer}: {bad}"
            assert ret_c == ret_r, f"sub={sub:#x} timer={timer}: ret cand={ret_c} ref={ret_r}"


# ---- per-frame char select (g_hiscore_charstep) ----
# up=1, left=4 step the initial down; down=2, right=8 step it up; fire 0x80 does not move it.
CS_INPUTS = (0, 1, 4, 2, 8, 1 | 2, 0x80, 0x80 | 1)


def _cs_image(ch, dec, inc, dirs):
    state = bytearray(equiv.bench_frame.IMAGE_SIZE)
    state[equiv.CS_NAME_ADDR] = ch
    equiv._w16(state, adapter.A_leg_dec_delay, dec & 0xffff)
    equiv._w16(state, adapter.A_leg_inc_delay, inc & 0xffff)
    equiv._w16(state, adapter.A_input_state, dirs & 0xffff)
    return state


def test_hiscore_charstep():
    """Per-frame initials selection: up/left steps down (wraps 'A'->'`'), down/right steps up (wraps
    'a'->'A'), each gated by its auto-repeat delay. Sweeps the boundary chars + both delays + every
    direction (a wrong wrap bound or a dropped auto-repeat gate diverges)."""
    lib = equiv._lib()
    for ch in (0x41, 0x42, 0x5a, 0x5f, 0x60, 0x4d):    # 'A','B','Z','_','`', mid-range
        for dec in (0, 1):                             # 0 -> fires this frame, 1 -> not yet
            for inc in (0, 1):
                for dirs in CS_INPUTS:
                    bad = equiv.compare_hiscore_charstep(lib, _cs_image(ch, dec, inc, dirs))
                    assert not bad, f"ch={ch:#x} dec={dec} inc={inc} dirs={dirs:#x}: {bad}"


# ---- the name-entry loop (rm_flow_name_entry) ----
def _entry_image(leg=0, pos=1, timer=30, sub=0):
    state = bytearray(equiv.bench_frame.IMAGE_SIZE)
    equiv._w16(state, adapter.A_leg_index, leg)
    equiv._w16(state, adapter.A_hiscore_pos, pos)
    equiv._w16(state, adapter.A_results_mode, 0)       # made the table
    equiv._w16(state, adapter.A_countdown_timer, timer)
    equiv._w16(state, adapter.A_countdown_sub, sub)
    equiv._w16(state, adapter.A_input_state, 0)        # so the first fire is a fresh 0->1 edge
    return state


def _row_off(leg, pos):
    return leg * adapter.HIGHSCORE_LEG_STRIDE + (pos - 1) * adapter.HIGHSCORE_ROW + adapter.HS_NAME_FIELD_OFF


# the prime and terminal both draw the screen twice under the results palette (draw, palette, show,
# draw, show) — the structural fingerprint every entry begins and ends with.
PRIME = ["draw_res_screen", "palette", "show", "draw_res_screen", "show"]


HOLD = 3   # the terminal-hold count the driver runs in these tests (drive_name_entry default)


def test_name_entry_full():
    """Alternating fire confirms three initials into the winning row (row+8..+10 = seed, +11 = 0), clears
    the rank, and returns CONTINUE. Also pins the sequencing: the prime + terminal double-draws, one
    (draw_res_screen, name_flash, show, poll) per frame, and the terminal HOLD + input-release wait."""
    lib = equiv._lib()
    poll = lambda i: FIRE if i % 2 == 0 else 0         # a fresh fire edge every other frame
    result, log, hs, fs = equiv.drive_name_entry(lib, _entry_image(leg=2, pos=3), poll)
    assert result == adapter.RM_FLOW_CONTINUE
    row = _row_off(2, 3)
    assert bytes(hs[row:row + 3]) == b"AAA", bytes(hs[row:row + 4])   # three confirmed initials
    assert hs[row + 3] == 0, "missing the terminating NUL"
    assert fs.hiscore_pos == 0, "the rank was not cleared"

    kinds = [r[0] for r in log]
    assert kinds[:5] == PRIME, kinds[:5]
    # terminal tail: the double-draw fade (PRIME), the HOLD, then the input-release wait.
    assert kinds.count("hold_frame") == HOLD, kinds.count("hold_frame")   # the finished table is held
    first_hold = kinds.index("hold_frame")
    assert kinds[first_hold - 5:first_hold] == PRIME, kinds[first_hold - 5:first_hold]
    last_hold = len(kinds) - 1 - kinds[::-1].index("hold_frame")
    assert kinds[last_hold + 1:] == ["poll"], kinds[last_hold + 1:]       # one release-wait poll (input cleared)
    # one flash per entry frame; the only extra poll is the terminal release wait.
    assert kinds.count("name_flash") == 5, kinds.count("name_flash")      # 3 confirms over 5 polled frames
    assert kinds.count("poll") == kinds.count("name_flash") + 1, kinds.count("poll")
    # the terminal draws carry the cleared rank (pos 0); the entry draws carried the live rank (pos 3).
    draw_args = [r[1] for r in log if r[0] == "draw_res_screen"]
    assert draw_args[-1] == (0, 0, 2) and draw_args[-2] == (0, 0, 2), draw_args[-2:]
    assert draw_args[0] == (0, 3, 2), draw_args[0]


def test_name_entry_timeout():
    """No fire: the countdown times out on the first frame (sub at the tick boundary, timer 0), ending
    entry with the initials untouched and the rank cleared — no per-frame draw beyond the prime/terminal."""
    lib = equiv._lib()
    result, log, hs, fs = equiv.drive_name_entry(lib, _entry_image(pos=1, timer=0, sub=0x11),
                                                 poll_of=lambda i: 0)
    assert result == adapter.RM_FLOW_CONTINUE
    row = _row_off(0, 1)
    assert hs[row] == 0x41, "the seeded initial was disturbed"
    assert fs.hiscore_pos == 0
    assert [r[0] for r in log].count("name_flash") == 0, "the loop drew a frame after timing out"


def test_name_entry_fire_edge():
    """Fire must be a FRESH 0->1 edge. HELD fire confirms only the FIRST initial, then the loop waits (no
    further edges) and ends on TIMEOUT — the third initial stays unconfirmed. A dropped edge check would
    confirm all three at once (mutation-caught)."""
    lib = equiv._lib()
    # Hold fire through entry (which times out ~frame 18), then release so the terminal input-release
    # wait (which spins while any bit is held) can return.
    result, log, hs, fs = equiv.drive_name_entry(lib, _entry_image(pos=1, timer=1, sub=0x11),
                                                 poll_of=lambda i: FIRE if i < 30 else 0)
    assert result == adapter.RM_FLOW_CONTINUE
    row = _row_off(0, 1)
    assert hs[row] == 0x41 and hs[row + 1] == 0x41, "the first initial was not confirmed"
    assert hs[row + 2] == 0, "a held fire confirmed the third initial (edge detection dropped)"
    assert fs.hiscore_pos == 0


# ---- the backspace arm ('`' delete: p-1 shift, HOLD placeholder, chars_left++) ----
INC = 0x02   # down/right: dial the initial up
DEC = 0x01   # up/left: dial the initial down


def test_name_entry_backspace():
    """The delete arm: confirm the first initial, dial the SECOND down to the '`' sentinel and fire on it
    to back up (shift '`' into the previous slot, leave '_', restore chars_left), then re-confirm. The
    winning row is seeded to 0x60 ('`') so a single dial reaches a real letter. After the sequence the row
    holds two clean 'A's — a delete that failed to move the pointer back (p -= 1 dropped) leaves the '`'
    and '_' placeholders (0x60/0x5f) instead (mutation-caught)."""
    lib = equiv._lib()
    script = {0: INC, 1: FIRE, 2: DEC, 3: FIRE, 4: INC, 5: FIRE}   # dial-up, confirm, dial-to-`, delete, dial-up, confirm
    poll = lambda i: script.get(i, 0)                              # then idle -> the countdown times out
    result, log, hs, fs = equiv.drive_name_entry(lib, _entry_image(pos=1, timer=1, sub=0x10),
                                                 poll, seed_char=0x60)
    assert result == adapter.RM_FLOW_CONTINUE
    row = _row_off(0, 1)
    assert hs[row] == 0x41 and hs[row + 1] == 0x41, bytes(hs[row:row + 2])   # delete-then-reconfirm -> 'A','A'
    assert fs.hiscore_pos == 0
    assert [r[0] for r in log].count("hold_frame") == HOLD             # reached the terminal hold


# ---- the missed-the-table tail (rm_flow_game_over_tail) ----
def test_game_over_tail():
    """The missed path redraws the results screen twice under the results palette (mode 2, no rank)."""
    lib = equiv._lib()
    img = bytearray(equiv.bench_frame.IMAGE_SIZE)
    equiv._w16(img, adapter.A_results_mode, 2)
    equiv._w16(img, adapter.A_hiscore_pos, 0)
    equiv._w16(img, adapter.A_leg_index, 1)
    result, log = equiv.drive_game_over_tail(lib, img)
    assert result == adapter.RM_FLOW_CONTINUE
    assert [r[0] for r in log] == PRIME, [r[0] for r in log]
    for r in log:
        if r[0] == "draw_res_screen":
            assert r[1] == (2, 0, 1), r[1]         # missed mode, no rank, leg 1
    assert [r[1] for r in log if r[0] == "palette"] == [(adapter.RM_FLOW_PAL_RESULTS,)]


# ---- the made/missed dispatch (rm_flow_score_tail) ----
def _tail_image(mode, leg=0, pos=1):
    img = bytearray(equiv.bench_frame.IMAGE_SIZE)
    equiv._w16(img, adapter.A_results_mode, mode)
    equiv._w16(img, adapter.A_hiscore_pos, pos)
    equiv._w16(img, adapter.A_leg_index, leg)
    equiv._w16(img, adapter.A_input_state, 0)
    return img


def test_score_tail_made_routes_to_name_entry():
    """results_mode == 0 dispatches to the interactive name entry. Seeded to time out on the first frame,
    so the only proof it entered name entry (not the game-over redraw) is the terminal HOLD it runs."""
    lib = equiv._lib()
    img = _tail_image(0, leg=0, pos=1)
    equiv._w16(img, adapter.A_countdown_timer, 0)
    equiv._w16(img, adapter.A_countdown_sub, 0x11)          # times out on frame 0
    result, log, hs, fs = equiv.drive_score_tail(lib, img)
    assert result == adapter.RM_FLOW_CONTINUE
    assert [r[0] for r in log].count("hold_frame") == HOLD, "made path did not run the name-entry hold"
    assert fs.hiscore_pos == 0


def test_score_tail_missed_routes_to_game_over():
    """results_mode == 2 dispatches to the game-over redraw: exactly the double-draw fade, NO name-entry
    hold. An inverted dispatch would run name entry here (a hold_frame would appear) — mutation-caught."""
    lib = equiv._lib()
    result, log, hs, fs = equiv.drive_score_tail(lib, _tail_image(2, leg=1, pos=0))
    assert result == adapter.RM_FLOW_CONTINUE
    kinds = [r[0] for r in log]
    assert kinds == PRIME, kinds
    assert "hold_frame" not in kinds, "missed path ran the name-entry hold (dispatch inverted)"
