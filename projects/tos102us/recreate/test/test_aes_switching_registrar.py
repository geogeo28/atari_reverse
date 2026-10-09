"""THE REGISTRAR OF THE ROWS THAT SWITCH (`aes_switching.settled`), held WHERE NO BATTERY THAT REGISTERS ONE IS IMPORTED.

A row that switches is settled as its battery is IMPORTED — the ROM's scheduled run, then its replay through the watch
(`aes_switching.Switching`) — so a change that breaks the watch breaks the import, and a suite that cannot be
collected names no assertion (`test_aes_event_helpers.py` says the same of the door's helpers). These tests make the
derivation themselves, over rows spelt here from the door's own vocabulary: such a change fails HERE, by name.
"""
import re
import types

import pytest

from harness import addrs, make_image
from recreate_kit import rom_bench

import aes
import aes_event
import aes_evlib
import aes_switch
import aes_switching as switching
import case

SHELL, SCREEN_MANAGER = aes_switch.SHELL, aes_switch.SCREEN_MANAGER
RETURN_KEY_CODE = aes_event.RETURN_KEY << 8 | ord("\r")
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


# ---- A DELIVERY AT A POLL THAT IS NO IDLE, on the derivation and the ROM's own replay ---------------------------------------
# (Held HERE too, where no registering battery is imported: a watch that mislaid a poll's delivery would fail every
# battery that registers such a row AT ITS IMPORT — an error, which a strict sweep counts no kill.)
ONTO_THE_BAR, RETURN = aes_event.move_to(*aes_event.MENU_BAR_POINT), aes_event.key(aes_event.RETURN_KEY)
THE_POLL_AFTER_THE_MOVE = 1             # poll 0 is idle 0 (the move); forker wakes the screen manager; idle polls again
A_KEY_AT_A_POLL = switching.SwitchingRow(
    "a wait for a key; the mouse onto the bar; Return at the poll after it, the screen manager woken", aes_evlib.EV_BLOCK,
    aes_evlib.A_KEY_S_WAIT, aes_event.machine, {0: ONTO_THE_BAR}, at_polls={THE_POLL_AFTER_THE_MOVE: RETURN})


def _the_rom_s_replay(row, made, switches):
    """The ROM's own run of `row` over its settled machine, watched through `switches`: `(its watch, its D0)`."""
    watch = switching.the_rom_s(switches, switching._entry(row))
    _final, _writes, regs = rom_bench.watched_original(make_image(made.pokes), switching._entry(row), watch)
    rom_bench.vet_the_run_just_made("the ROM's replay of a wait whose key comes at a poll")
    watch.vet_ended("the ROM's replay")
    return watch, regs["d0"] & aes.WORD_MASK


def test_a_delivery_at_a_poll_is_settled_with_how_the_machine_stood_and_replayed_at_that_poll():
    """THE DERIVATION (`aes_switch.scheduled`, `aes_switching.settled`): the row's `Switches` carries the delivery
    by its poll's ordinal, with the polls the ROM's run makes — and, in what the delivery FOUND, the three words idle
    tests: nothing ready, the screen manager woken, nothing queued. The replay that lays it there is the run that
    took it (the screen manager entered once, Return answered), and the host's model answers the same."""
    made = switching.settled(A_KEY_AT_A_POLL)
    assert (made.switches.idles, made.switches.polls, made.entered) == (1, 4, (SCREEN_MANAGER, SHELL))
    (poll, (found, _wrote)), = made.switches.at_polls.items()
    stood = [int.from_bytes(found[at], "big") for at in (aes.AES_RLR, aes.AES_DRL, aes.AES_FORK_COUNT)]
    assert (poll, stood) == (THE_POLL_AFTER_THE_MOVE, [0, SCREEN_MANAGER, 0])
    watch, answer = _the_rom_s_replay(A_KEY_AT_A_POLL, made, made.switches)
    assert (watch.polls, watch.idles, watch.entered, answer) == (4, 1, [SCREEN_MANAGER, SHELL], RETURN_KEY_CODE)
    assert switching.companion(A_KEY_AT_A_POLL).answer & aes.WORD_MASK == RETURN_KEY_CODE


@pytest.mark.parametrize("astray, refused", (
    (lambda switches, delivery: switches._replace(at_polls={}), "idles once more than the ROM's own run did"),
    (lambda switches, delivery: switches._replace(at_polls={THE_POLL_AFTER_THE_MOVE + 1: delivery}), "which is this idle"),
    (lambda switches, delivery: switches._replace(at_polls={switches.polls: delivery}), r"named at poll \[4\] of a run that makes 4 poll"),
    (lambda switches, delivery: switches._replace(polls=switches.polls + 1), r"polled 4 time\(s\) where the ROM's own run polls 5"),
    (lambda switches, delivery: switches._replace(at_polls={THE_POLL_AFTER_THE_MOVE: (
        {**delivery[0], aes.AES_DRL: delivery[0][aes.AES_RLR]}, delivery[1])}), "where an interrupt is delivered at poll 1"),
), ids=("never laid", "laid a poll late", "named at a poll never made", "a poll more held", "found with nothing woken"))
def test_a_replay_that_takes_a_poll_s_delivery_otherwise_is_refused_by_name(astray, refused):
    """...AND EACH WAY A WATCH COULD MISTAKE IT IS REFUSED, on the ROM's own replay: the delivery never laid (the
    machine then idles where the ROM's run did not), laid a poll late (that poll is an idle: an idle's delivery has
    one spelling), named at a poll the run never makes (refused where the watch is made), the run held to a poll
    more than it makes, and the delivery handed over as found with NO process woken (checked against what idle
    tests before a byte is laid)."""
    made = switching.settled(A_KEY_AT_A_POLL)
    delivery, = made.switches.at_polls.values()
    with pytest.raises((switching.Refused, AssertionError), match=refused):
        _the_rom_s_replay(A_KEY_AT_A_POLL, made, astray(made.switches, delivery))


def test_the_host_s_model_counts_the_polls_of_both_dispatchers_and_lays_the_delivery_at_its_poll():
    """THE HOST'S SHORE (`aes_switch.Scheduling`: the poll hook at every poll of the C's idle, and the nested ROM run
    of a foreign process counted on in the same sequence): the C's run polls as often as the ROM's; held to a
    reference that takes nothing at the poll it idles once more and is refused by the idle hook's own words."""
    made = switching.settled(A_KEY_AT_A_POLL)
    reference = switching.scheduled(A_KEY_AT_A_POLL, made.pokes)

    def modelled(against):
        return aes_switch.modelled(switching._core(A_KEY_AT_A_POLL), A_KEY_AT_A_POLL.arguments, made.pokes, against, foreign=True)
    held = modelled(reference)
    assert (held.returncode, held.polls, held.idles) == (0, reference.polls, reference.idles), held.stderr
    never_handed = modelled(reference._replace(at_polls={}))
    assert never_handed.returncode != 0 and "idles once more than the ROM's own run did" in never_handed.stderr
    (poll, (found, wrote)), = reference.at_polls.items()
    nothing_woken = {**found, aes.AES_DRL: found[aes.AES_RLR]}
    astray = modelled(reference._replace(at_polls={poll: (nothing_woken, wrote)}))
    assert astray.returncode != 0 and f"where an interrupt is delivered at poll {poll} (the C scheduler's)" in astray.stderr


def test_a_delivery_named_at_a_poll_the_run_never_makes_or_at_an_idle_is_refused_by_the_derivation():
    """THE ROM'S SHORE, WHERE A DELIVERY IS TAKEN (`aes_switch.scheduled`): a poll is named by its ordinal among the
    polls the run's dispatcher makes — one past the last is refused by name when the run has ended (nothing was
    delivered there), and one that IS an idle is refused where it is reached: an idle's delivery has one spelling."""
    made = switching.settled(A_KEY_AT_A_POLL)
    never_made = A_KEY_AT_A_POLL._replace(at_polls={**A_KEY_AT_A_POLL.at_polls, made.switches.polls: RETURN})
    with pytest.raises(AssertionError, match=r"made 4 polls: nothing was delivered at \[4\]"):
        switching.scheduled(never_made, made.pokes)
    with pytest.raises(AssertionError, match="a delivery is named at poll 0, which is idle 0 of the run"):
        switching.scheduled(A_KEY_AT_A_POLL._replace(at_polls={0: RETURN}), made.pokes)


# ---- THE QPB'S ADDRESS A PIPE WAIT LEAVES IN ITS EVB ------------------------------------------------------------------------
# evnt_mesag over an empty pipe, woken by the screen manager's own write (`aes_evlib.A_MESSAGE_WAITED_FOR`): the
# address of ap_rdwr's QPB is left in the freed EVB — a longword that differs on every shore.
A_MESSAGE_WAITED_FOR = aes_evlib.A_MESSAGE_WAITED_FOR
ITS_QPB = (aes_evlib.SHELL_PID, aes_event.MESSAGE_BYTES, aes_evlib.BUFFER_AT)


def test_a_qpb_s_address_left_in_an_evb_is_dropped_by_name_and_never_staged():
    """THE COMPOSITION (`aes_switching._qpbs_left`): the row's derivation finds the one EVB whose parameter the ROM's
    run stored with a stack address, keeps THE QPB IT NAMED WHILE ITS FRAME WAS LIVE, drops that longword at Tier 3
    under the QPB's own reason — and stages nothing there: the settled machine holds what the row's machine held."""
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    (at, qpb), = made.qpbs.items()
    assert qpb == ITS_QPB and at in switching.EVB_PARMS
    assert (at, at + aes.LONG_BYTES, aes_event.QPB_ADDRESS_WHY) in made.drops
    settled, unsettled = make_image(made.pokes), make_image(A_MESSAGE_WAITED_FOR.machine())
    assert bytes(settled[at:at + aes.LONG_BYTES]) == bytes(unsettled[at:at + aes.LONG_BYTES])
    assert switching.settled(WOKEN_BY_A_KEY).qpbs == {}, "...and a wait on no pipe leaves none"


def test_the_rom_s_qpb_is_read_while_its_frame_is_live_not_where_the_run_ends():
    """A ROM BEHAVIOUR THE DERIVATION STANDS ON, PINNED: ev_mesag's QPB is the arguments it pushed for ap_rdwr, and
    the trap frame of ev_mesag's own Line-F return lands on them — read where the run ENDS (as
    `aes_event.qpb_addresses_kept` reads it) its first two words are the high and low word of the address after
    ev_mesag's return word, no process and no count. The watch read it at the idle the process was parked at."""
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    the_rom_s = switching.scheduled(A_MESSAGE_WAITED_FOR, made.pokes)
    (at, live), = made.qpbs.items()
    frame = case.long_in(the_rom_s.memory, at) & aes_event.OS_BUS_ADDR_MASK
    where_it_ends = aes_event.QPB.unpack(bytes(the_rom_s.memory[frame:frame + aes_event.QPB.size]))
    pushed_by_the_return = (where_it_ends[0] & aes.WORD_MASK) << 8 * aes.WORD_BYTES | where_it_ends[1] & aes.WORD_MASK
    assert live == ITS_QPB and where_it_ends[:2] != live[:2]
    assert addrs.AES_ROM_EV_MESAG < pushed_by_the_return < addrs.AES_ROM_EV_TIMER


def test_a_qpb_address_no_stop_saw_live_is_refused_by_name():
    """...AND WHERE THE WATCH SAW NOTHING, NOTHING IS SETTLED: handed a watch that saw no QPB (a wait queued and
    freed between two stops of the dispatcher would leave one), the derivation refuses by name."""
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    the_rom_s = switching.scheduled(A_MESSAGE_WAITED_FOR, made.pokes)
    stored = dict.fromkeys(range(min(made.qpbs), min(made.qpbs) + aes.LONG_BYTES), 0)
    blind = types.SimpleNamespace(qpbs_seen={}, qpbs_parked={})
    with pytest.raises(AssertionError, match="that no stop of its dispatcher saw live"):
        switching._qpbs_left("a row", the_rom_s.memory, stored, blind)
    in_a_live_frame = {at: (A_FRAME_S_ADDRESS, A_FRAME_S_ADDRESS) for at in made.qpbs}
    seeing = types.SimpleNamespace(qpbs_seen=made.qpbs, qpbs_parked=in_a_live_frame)
    assert switching._qpbs_left("a row", the_rom_s.memory, stored, seeing) == made.qpbs


def test_a_companion_vets_the_qpb_before_it_leaves_its_address_out(monkeypatch):
    """TIER 1 OF SUCH A ROW (`aes_switching.companion`): the C's own longword must be its process's QPB slot naming
    the ROM's QPB — vetted, and only then left out of the compare. Held to a QPB of one byte more, the companion is
    refused by name; and with the vet's answer thrown away the compare itself reds on that longword (its low word:
    the two shores' frames lie in one 64 KB)."""
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    assert switching.companion(A_MESSAGE_WAITED_FOR).answer is not None
    (at, (process, count, buffer)), = made.qpbs.items()
    monkeypatch.setattr(switching, "settled", lambda row: made._replace(qpbs={at: (process, count + 1, buffer)}))
    with pytest.raises(AssertionError, match=r"the QPB the parked wait names .* is not the ROM's"):
        switching.companion(A_MESSAGE_WAITED_FOR)
    monkeypatch.setattr(switching, "settled", lambda row: made)
    monkeypatch.setattr(switching, "_vetted_qpbs", lambda row, settled, image: frozenset())
    with pytest.raises(AssertionError, match=f"bytes differ from the ROM's run: {at + aes.WORD_BYTES:#x}"):
        switching.companion(A_MESSAGE_WAITED_FOR)


A_FRAME_S_ADDRESS = case.STACK_BAND.start + 0x100      # anywhere in the run's own stack band
THE_STACK_POINTER_THERE = A_FRAME_S_ADDRESS - 0x20      # ...the frame live: the process's stack pointer below it


def _a_watch_at_staged_idles():
    """`(a watch, its memory, idle_with)` over STAGED STOPS (no run makes them): the machine idling, the first EVB's
    parameter set to `parameter` and `qpb` laid at A_FRAME_S_ADDRESS by each `idle_with(parameter, qpb)`."""
    watch = switching.the_rom_s(aes_event.Switches({}, 4, SHELL))
    memory, at = make_image(aes_event.machine()), switching.EVB_PARMS[0]
    for head in (aes.AES_RLR, aes.AES_DRL):
        memory[head:head + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    parked_at = aes_event.uda_of(SHELL, memory) + aes.UDA_SUPER_SP
    memory[parked_at:parked_at + aes.LONG_BYTES] = THE_STACK_POINTER_THERE.to_bytes(aes.LONG_BYTES, "big")

    def idle_with(parameter, qpb):
        memory[at:at + aes.LONG_BYTES] = parameter.to_bytes(aes.LONG_BYTES, "big")
        memory[A_FRAME_S_ADDRESS:A_FRAME_S_ADDRESS + aes_event.QPB.size] = aes_event.QPB.pack(*qpb)
        watch._polled.clear()
        watch.stopped(switching.ROM_POLL, 0, memory)
    return watch, memory, idle_with


def test_the_watch_reads_a_qpb_the_first_time_its_address_is_seen_and_not_again():
    """`Switching.qpbs_seen`, over staged stops (no run makes them): an EVB's parameter naming eight bytes of the
    run's stack is read at an idle — with where it lay and the parked process's stack pointer; the same address seen
    again — the EVB freed, the frame gone, other bytes there — is NOT read again; a new address is. A parameter
    outside the stack band is nobody's frame."""
    watch, memory, idle_with = _a_watch_at_staged_idles()
    at = switching.EVB_PARMS[0]
    idle_with(aes_evlib.BUFFER_AT, ITS_QPB)
    assert watch.qpbs_seen == {}
    idle_with(A_FRAME_S_ADDRESS, ITS_QPB)
    assert watch.qpbs_seen == {at: ITS_QPB} and watch.qpbs_parked == {at: (A_FRAME_S_ADDRESS, THE_STACK_POINTER_THERE)}
    idle_with(A_FRAME_S_ADDRESS, (0, 0, 0))
    assert watch.qpbs_seen == {at: ITS_QPB}, "the address was seen: what lies there now is not the QPB"


def test_a_wait_still_queued_is_read_again_where_its_qpb_s_address_was_seen_before():
    """...BUT A WAIT THAT IS QUEUED NAMES A LIVE QPB, whatever was read at that address before: the same EVB taken
    for a second wait whose QPB lies where the first one's did (a routine that waits twice out of one frame) is read
    AGAIN — the first QPB kept for it would vet the second wait against another process, count or buffer."""
    watch, memory, idle_with = _a_watch_at_staged_idles()
    at, evb = switching.EVB_PARMS[0], switching.EVB_PARMS[0] - aes.EVB_PARM
    idle_with(A_FRAME_S_ADDRESS, ITS_QPB)
    another = (ITS_QPB[0], ITS_QPB[1], ITS_QPB[2] + aes_event.MESSAGE_BYTES)
    readers = SHELL + aes.PD_QUEUE_READERS                  # A STAGED LIST: the EVB queued to read the desk's pipe
    memory[readers:readers + aes.LONG_BYTES] = evb.to_bytes(aes.LONG_BYTES, "big")
    memory[evb + aes.EVB_LINK:evb + aes.EVB_LINK + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    assert evb in aes_event.waiting_on_a_pipe(memory)
    idle_with(A_FRAME_S_ADDRESS, another)
    assert watch.qpbs_seen == {at: another}


def test_a_qpb_parked_in_a_frame_its_process_no_longer_has_is_refused_by_name(blob, monkeypatch):
    """THE PLACE, NOT ONLY THE BYTES (`aes_switching.vet_the_qpbs_lay_in_live_frames`, asked of the ROM's replay and
    of every blob's run): on each blob our parked wait's QPB lies in a frame the desk still has — at or above the
    stack pointer savestate kept. RED, twice: a watch that saw the QPB BELOW that pointer (a twin that queued the
    address of a popped frame: the right eight bytes until the next call) is refused by name; and so is our real run
    held to a process that stood parked ABOVE where its QPB lies."""
    _measured, watch, _foreign = switching.measured_on(blob, A_MESSAGE_WAITED_FOR)
    (at, (lay_at, parked_at)), = watch.qpbs_parked.items()
    assert parked_at <= lay_at < case.STACK_BAND.stop and at in switching.settled(A_MESSAGE_WAITED_FOR).qpbs
    dead = types.SimpleNamespace(qpbs_seen=watch.qpbs_seen, qpbs_parked={at: (parked_at - aes.LONG_BYTES, parked_at)})
    with pytest.raises(AssertionError, match="BELOW its process's stack pointer .* a dead frame's address"):
        switching.vet_our_qpbs("a twin", switching.settled(A_MESSAGE_WAITED_FOR).qpbs, dead)
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    monkeypatch.setattr(switching, "settled", lambda row: made)     # the ROM's derivation as it stands: OUR run is the one held
    monkeypatch.setattr(switching.Switching, "_parked_at", lambda self, memory: lay_at + aes.LONG_BYTES)
    with pytest.raises(AssertionError, match=rf"^{re.escape(switching.row_name(A_MESSAGE_WAITED_FOR))}: the QPB .* a dead frame's address"):
        switching.measured_on(blob, A_MESSAGE_WAITED_FOR)


THE_MANAGER_S_WRITE = switching.SwitchingRow("the screen manager's write to the desk's full pipe; freed by the desk's read",
                                             aes_evlib.AP_RDWR, aes_evlib.THE_BLOCKED_WRITE,
                                             aes_evlib.the_manager_writing_to_a_full_pipe, {})


def test_a_wait_served_with_no_idle_is_seen_where_its_process_is_resumed():
    """THE OTHER PLACE A QPB IS SEEN LIVE: the screen manager's blocked write is freed by the desk's read with the
    machine never idle — no idle to read the QPB at — and its process is resumed inside mwait, the frame still
    there. The derivation keeps the QPB the write was handed, read at that resume; the row's process is the screen
    manager, read off the machine."""
    made = switching.settled(THE_MANAGER_S_WRITE)
    assert (made.switches.idles, made.switches.process, made.entered[-1]) == (0, SCREEN_MANAGER, SCREEN_MANAGER)
    _code, process, count, buffer = aes_evlib.THE_BLOCKED_WRITE
    assert list(made.qpbs.values()) == [(process, count, buffer)]
    assert switching.companion(THE_MANAGER_S_WRITE).answer is not None


def test_a_companion_holds_the_qpb_to_the_slot_of_its_own_entry_s_role(monkeypatch):
    """...AND WHOSE SLOT: a row entered at an entry that parks a QPB (ap_rdwr) is held to THAT entry's own role
    (`aes_event.our_qpb_slots`) — the same eight bytes at another routine's slot are another routine's frame. With
    the two roles' slots exchanged (the slot ap_rdwr's twin really uses is then ev_multi's), the companion refuses
    by name; a vet that took any role's slot would pass it."""
    roles = aes_event.QPB_SLOT_OF_AN_ENTRY
    (first, its), (second, the_other_s) = roles.items()
    monkeypatch.setattr(aes_event, "QPB_SLOT_OF_AN_ENTRY", {first: the_other_s, second: its})
    with pytest.raises(AssertionError, match="is no QPB slot of the running process under .* role"):
        switching.companion(THE_MANAGER_S_WRITE)


def test_the_machine_a_run_leaves_holds_every_byte_it_stored_not_only_what_differs_from_the_snapshot():
    """`aes_switching.left_by` IS BY THE LEDGER: the desk's wait for a key across the screen manager's turn stores
    bytes with the very value the snapshot holds (a list relinked as it was, a word counted up and down), and each
    is in the machine it leaves — laid over ANOTHER capture of the boot, they are still the run's. (A machine kept
    as "what differs from the snapshot" lost them: the lock's row over it never returned in the snapshot-noise
    sweep.) Nothing of the run's own stack is in it."""
    machine, wake = aes_event.machine(), {0: ONTO_THE_BAR, 1: RETURN}
    left = switching.left_by(aes_evlib.EV_BLOCK, A_KEY_S_WAIT, machine, wake)
    row = switching.SwitchingRow("", aes_evlib.EV_BLOCK, A_KEY_S_WAIT, lambda: machine, wake)
    _reference, _watch, final, writes = switching._replayed(row, switching._staged(row))
    before = make_image(switching._staged(row))
    as_they_were = [at for at in writes if at not in case.STACK_BAND and final[at] == before[at]]
    after = make_image(left)
    assert as_they_were and all(any(start <= at < start + len(data) for start, data in left.items()) for at in as_they_were[:64])
    assert bytes(after[:case.STACK_BAND.start]) == bytes(final[:case.STACK_BAND.start])
    assert not [at for at in left if at in case.STACK_BAND]
