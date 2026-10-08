"""THE REGISTRAR OF THE ROWS THAT SWITCH (`aes_switching.settled`), held WHERE NO BATTERY THAT REGISTERS ONE IS IMPORTED.

A row that switches is settled as its battery is IMPORTED — the ROM's scheduled run, then its replay through the watch
(`aes_switching.Switching`) — so a change that breaks the watch breaks the import, and a suite that cannot be
collected names no assertion (`test_aes_event_helpers.py` says the same of the door's helpers). These tests make the
derivation themselves, over rows spelt here from the door's own vocabulary: such a change fails HERE, by name.
"""
import pytest

import aes
import aes_event
import aes_evlib
import aes_switch
import aes_switching as switching

SHELL, SCREEN_MANAGER = aes_switch.SHELL, aes_switch.SCREEN_MANAGER
A_KEY_S_WAIT = (aes.header_constants("evwait.h")["IASYNC_KEYBOARD"], 0)
RETURN = aes_event.key(aes_event.RETURN_KEY)
ONTO_THE_BAR = aes_event.move_to(*aes_event.MENU_BAR_POINT)
WOKEN_BY_A_KEY = switching.SwitchingRow("a wait for a key; Return at the first idle", aes_evlib.EV_BLOCK, A_KEY_S_WAIT,
                                        aes_event.machine, {0: RETURN})
THROUGH_THE_SCREEN_MANAGER = switching.SwitchingRow(
    "a wait for a key; the mouse onto the bar, the screen manager's turn, then Return", aes_evlib.EV_BLOCK, A_KEY_S_WAIT,
    aes_event.machine, {0: ONTO_THE_BAR, 1: RETURN})
# (the row, the idles its ROM run makes, the processes its dispatcher enters)
ROWS = {row.label: (row, idles, entered) for row, idles, entered in (
    (WOKEN_BY_A_KEY, 1, (SHELL,)), (THROUGH_THE_SCREEN_MANAGER, 2, (SCREEN_MANAGER, SHELL)))}


@pytest.mark.parametrize("label", ROWS)
def test_a_row_is_settled_from_the_rom_s_own_runs(label):
    """THE DERIVATION, made here: the scheduled run says what is delivered at which idle and who is entered; its
    replay through the watch is that same run (held), ends as the row says, and its ledger cuts the drops — every
    byte of each staged at the value the run leaves. (WHICH kinds a row drops is the one census's:
    `test_aes_event.BY_NATURE_CENSUS`, the rows that switch.)"""
    row, idles, entered = ROWS[label]
    made = switching.settled(row)
    assert (made.switches.idles, made.switches.process, made.entered) == (idles, SHELL, entered)
    assert sorted(made.switches.at_idles) == sorted(row.at_idle) and not made.switches.at_calls
    staged = switching.scheduled(row, made.pokes)
    assert all(bytes(staged.started[lo:hi]) == bytes(staged.memory[lo:hi]) for lo, hi, _why in made.drops), (
        "the settled machine holds, in every dropped window, what the ROM's run leaves there")


def test_a_replay_that_is_not_the_run_that_took_the_deliveries_is_refused(monkeypatch):
    """THE REPLAY IS HELD TO THE RUN IT REPLAYS: handed a delivery that writes ANOTHER byte than the interrupt wrote
    (the key's code in the keyboard's ring, changed — where nothing checks what it lands on), the replay answers
    another key in another machine, and the derivation refuses it by name: nothing is settled from it."""
    switches_of = switching.switches_of

    def another_key(reference):
        switches = switches_of(reference)
        found, wrote = switches.at_idles[0]
        longest = max(wrote, key=lambda at: len(wrote[at]))
        return switches._replace(at_idles={0: (found, {**wrote, longest: wrote[longest][:-1] + bytes([wrote[longest][-1] ^ 1])})})
    monkeypatch.setattr(switching, "switches_of", another_key)
    with pytest.raises(AssertionError, match="the replay that lays the deliveries is not the run that took them"):
        switching.settled(WOKEN_BY_A_KEY)
