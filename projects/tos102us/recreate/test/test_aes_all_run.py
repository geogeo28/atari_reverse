"""all_run `$fda03e` (`src/aes/geminit.c`) against the ROM: one yield, then the screen's lock taken and given back.

    all_run():  for (i = 0; i < 1; i++) dsptch();  wm_update(TRUE);  wm_update(FALSE);

IT LEAVES BY THE DISPATCHER ON EVERY ARM (the yield comes first), so every case is A ROW THAT SWITCHES, and it is a
DOOR USER (wm_update's tak_flag, ev_block and unsync): `aes_event.woken_row`, held four ways —
  * THE PREMISE on the ROM's own run through its dispatcher: who is entered, at which idle what is taken;
  * AT THE DISPATCHER: the C's image where it first leaves — at the yield, nothing stored yet;
  * TIER 1 THROUGH THE HOST'S SCHEDULER (`aes_switching.companion`), the door bound: every byte outside the run's own
    stack the ROM's, every frame the door is handed;
  * ON BOTH BLOBS, AND IN THE TABLE: the real switch through our own dispatcher, on two counts.

THE MACHINES ARE ROM RUNS' — a process running as the ROM's own scheduler left it (`aes_event.machine`), the lock as
the ROM's own wm_update or the screen manager's own menu left it. WHO CALLS IT: the AES's appl_exit arm (`$fe5e6a`)
and the desk's binding of it (`$fddea0`), each after an ap_rdwr — a running application's call, which these
machines are — and gem_main once the desk has returned (`$fda396`).
WHAT IT IS FOR shows in the second machine: with the screen manager's menu down — the manager holds the lock —
all_run's own BEG_UPDATE WAITS until the menu is let go; only then does the caller go on.
"""
import pytest

from harness import addrs

import aes
import aes_event
import aes_evlib as evlib
import aes_switching as switching
import test_aes_wm_update as wm_update
import vdi

ALL_RUN = "AES_ROM_ALL_RUN"
aes.declare_alcyon(ALL_RUN, None, (vdi.IMAGE_ARG,))
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
BENCH, SHIPPED = "bench", "bench_shipped"
Premise, Priced = switching.Premise, switching.Priced
NO_WINDOW = switching.NO_WINDOW
TAK_FLAG, EV_BLOCK, UNSYNC = addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_EV_BLOCK, addrs.AES_ROM_UNSYNC

ALONE = "the desk alone ready: a yield back to it, the lock taken and given back"
LOCK_HELD_ALREADY = "the lock the caller's own already: taken a second time, one level given back"
BEHIND_THE_MENU = "the screen manager's menu holds the lock: the caller waits until the menu is let go"


def _row(label, machine, at_idle=None):
    return aes_event.woken_row(label, ALL_RUN, (), machine, at_idle or {}, answered=False)


ROWS = {
    ALONE: _row(ALONE, aes_event.machine),
    LOCK_HELD_ALREADY: _row(LOCK_HELD_ALREADY, wm_update.locked),
    BEHIND_THE_MENU: _row(BEHIND_THE_MENU, evlib.the_manager_s_menu_holds_the_lock, evlib.THE_MENU_LET_GO),
}
# What the ROM's own run of each IS: the idles it takes a delivery at, the idles it makes, who calls, every process
# its dispatcher enters — the yield comes back to the desk; behind the menu the desk's wait then lets the screen
# manager run three times (the mouse off its bar, the press, the release) before the lock is handed over — and no
# answer: all_run sets no D0.
PREMISES = {
    ALONE: Premise((), 0, SHELL, (SHELL,), None),
    LOCK_HELD_ALREADY: Premise((), 0, SHELL, (SHELL,), None),
    BEHIND_THE_MENU: Premise((0, 1), 2, SHELL, (SHELL, SCREEN_MANAGER, SCREEN_MANAGER, SCREEN_MANAGER, SHELL), None),
}
# ...and the door calls its process makes, in order: the lock asked for, waited for where another holds it, released.
DOOR_CALLS = {
    ALONE: (TAK_FLAG, UNSYNC),
    LOCK_HELD_ALREADY: (TAK_FLAG, UNSYNC),
    BEHIND_THE_MENU: (TAK_FLAG, EV_BLOCK, UNSYNC),
}
REGISTERED = {switching.row_name(row): row for row in map(aes_event.register_woken, ROWS.values())}

# @PINS-BEGIN (measured: scratch `b5/H/pins.py`)
WHOLE_RUN = {
    'the desk alone ready: a yield back to it, the lock taken and given back':
        {BENCH: (14024, 11462), SHIPPED: (14024, 11582)},
    "the lock the caller's own already: taken a second time, one level given back":
        {BENCH: (13952, 11384), SHIPPED: (13952, 11504)},
    "the screen manager's menu holds the lock: the caller waits until the menu is let go":
        {BENCH: (391348, 382922), SHIPPED: (391348, 382812)},
}
PRICED = {
    'the desk alone ready: a yield back to it, the lock taken and given back':
        Priced((4544, 7262), (4110, 6512), 2, (0, 0, 0)),   # 0.63 / 0.63
    "the lock the caller's own already: taken a second time, one level given back":
        Priced((4466, 7190), (4110, 6512), 2, (0, 0, 0)),   # 0.62 / 0.63
    "the screen manager's menu holds the lock: the caller waits until the menu is let go":
        Priced((19298, 28946), (4206, 6708), 3, (1, 338080, 124096)),   # 0.67 / 0.63
}
# @PINS-END
WINDOWS = {label: priced.windows for label, priced in PRICED.items() if priced.windows != NO_WINDOW}
# ...and as `test_tier3`'s census of the door users that switch reads them (its own two tables' shape, by the
# registry's name): every row here is one — its run arrives at tak_flag and unsync.
DOOR_USERS_PRICED = {switching.row_name(ROWS[label]): tuple(PRICED[label]) for label in ROWS}
DOOR_USERS_WHOLE_RUN = {switching.row_name(ROWS[label]): WHOLE_RUN[label] for label in ROWS}


def spb_of(image):
    """The screen's lock in `image`: how deep it is held, and by whom."""
    return wm_update.spb_of(image)


def test_every_row_is_registered_and_pinned():
    assert set(REGISTERED) <= set(aes_event.SWITCHING_ROWS)
    assert PREMISES.keys() == ROWS.keys() == DOOR_CALLS.keys() == WHOLE_RUN.keys() == PRICED.keys()
    assert set(WINDOWS) == {BEHIND_THE_MENU}, "one row has another process's turns in it"


@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_of_a_row_is_what_its_name_says(label):
    """THE PREMISE (`aes_switching.vet_the_premise`), and the door calls the ROM's own run makes, in order."""
    the_rom_s = switching.vet_the_premise(ROWS[label], PREMISES[label])
    assert tuple(call.routine for call in the_rom_s.calls) == DOOR_CALLS[label]


@pytest.mark.parametrize("label", ROWS)
def test_the_first_thing_all_run_does_is_yield(label):
    """AT THE DISPATCHER (`aes_event.switches_where_the_rom_does`): the C reaches its first switch as a YIELD — its
    process still ready — with the whole image the ROM's own at dsptch: nothing stored, the lock not yet asked for."""
    row = ROWS[label]
    held = aes_event.switches_where_the_rom_does(row.name, row.arguments, row.machine(), switches=aes_event.YIELDS)
    assert spb_of(held.image) == spb_of(aes_event.make_image(row.machine())), "the lock untouched before the yield"


@pytest.mark.parametrize("label", ROWS)
def test_a_row_taken_on_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1 (`aes_switching.companion`, nothing dropped, the door bound in the same child): the C through its own
    scheduler makes the ROM's door calls, each handed the ROM's frame, enters the processes the ROM's run enters,
    and leaves the ROM's image."""
    ran = switching.companion(ROWS[label])
    assert tuple(call.routine for call in ran.calls) == DOOR_CALLS[label]
    assert ran.entered == tuple(PREMISES[label].entered)


def test_the_lock_is_left_as_it_was_found_alone_and_one_level_down_never_lower():
    """What the two calls of wm_update leave of the lock: free where it was free (count 0, no owner); the caller's
    own still, one level deep, where the caller held it; and FREE behind the menu — the screen manager handed it
    over as its menu went, and the caller gave it back."""
    left = {label: spb_of(switching.companion(ROWS[label]).image) for label in ROWS}
    assert left[ALONE] == (0, 0) and left[BEHIND_THE_MENU] == (0, 0), left
    assert left[LOCK_HELD_ALREADY] == (1, SHELL), left


def test_behind_the_menu_the_caller_really_waits_for_the_lock():
    """THE PREMISE OF THE WAIT: with the menu still down — nothing delivered — all_run does not return: its
    BEG_UPDATE finds the lock the screen manager's and the machine idles, every process waiting."""
    import aes_switch
    row = ROWS[BEHIND_THE_MENU]._replace(at_idle={})
    the_rom_s = switching.scheduled(row, switching._staged(row))
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (aes_switch.IDLES, 1, (SHELL,))
    assert spb_of(the_rom_s.memory)[1] == SCREEN_MANAGER


# ---- ON BOTH BLOBS, AND IN THE TABLE -------------------------------------------------------------------------------------
@pytest.mark.parametrize("label", ROWS)
def test_a_row_really_switches_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH (`aes_switching.vet_on_a_blob`): our all_run yields through OUR
    dsptch and disp and comes back into GCC's frame; behind the menu it sleeps in our mwait across the screen
    manager's three turns — the ROM's own code on both shores, to the cycle — and is woken by our switchto."""
    switching.vet_on_a_blob(blob, ROWS[label], PREMISES[label], WINDOWS.get(label, NO_WINDOW), WHOLE_RUN[label])


@pytest.mark.parametrize("label", ROWS)
def test_the_table_prices_a_row_on_both_counts(label):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's own cycles and the caller's own, net
    of the three door calls, both pinned and both under the bar."""
    switching.vet_the_table_s_price(ROWS[label], PRICED[label])
