"""THE CHAINED BOOT HELD (boot CH, `test/boot_chain.py`): our boot from the reset to `$fc047a` and on to gem_entry — the
head, B2, B3, B5, B6 and B4 of ours in sequence, the ROM's own code where nothing is ported — against the ROM's own boot
from the same machine, WARM and COLD on four of B5's arms, the blank disk (rulings R-CH-1 "Steered chain", D10
deferred, 2026-11-01; and every ruling each slice stands on).

Held here: THE STATIC LINK CHECK and the steering it reads (each with its negative); every boundary on every surface, the
carries exactly as named and dead by `$fc0452`; THE CHIP AND PORT-A CARRIES (R-D4-2: PSG port A from the head's store,
the FDC chip MR's until B6 runs the floppy through the kit's model) at every boundary, from each shore's own runs; the
ledgers the same as the slices' own (B6's answers and FDC ledger; B4's GEMDOS, floppy, clock and blanks); THE END SURFACES
(COLD) against both captures, apart in exactly the classes named (D1 at `$fc047a`; D1 and the launch's unread lower-driver
state at gem_entry);
THE HAND-OFF NO SLICE SEES — the traps and the blanks the ROM's later code takes enter OUR linked entries, counted, and
the +4 a call our `trap.S` costs proved; the device model through our linked XBIOS entry (I-1) and its refusals; the
price (ruling D9), each chain's own cycles pinned exactly."""
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs, make_image

import aes_boot
import boot
import boot_chain as bc
import boot_display
import boot_floppy
import boot_late
import boot_launch
import boot_sysvars
import staging

BAR = 1.10
LONG_BYTES = 4
FREE_RAM_SEARCHED = (0x20000, 0x30000)  # below the blob, outside every pre-init mask field: where a stray return is laid
A_LAUNCH_OFFSET = 0x40                  # an address inside the launch's text, ours and the ROM's by the same offset
NAMES = tuple(bc.SLICES)
COLD_CHAIN = bc.SLICES["boot chain, COLD"]
JMP_LONG_BYTES = 6
TRAPS_TAKEN = {bc.B6: 3, bc.B4: 3}      # GEMDOS's init and Dsetdrv / the launch's GEMDOS calls, through trap #13/#14
TRAP_S_EXTRA_A_CALL = bc.LEA_ABSOLUTE_LONG_CYCLES - bc.LEA_PC_RELATIVE_CYCLES
BLANKS_TAKEN, HBL_CYCLES = 2, 172       # the launch's two horizontal blanks (`aes_boot`'s model), each through the HBL entry


@pytest.fixture(scope="module", params=NAMES)
def pair(request):
    chain = bc.SLICES[request.param]
    return chain, bc.the_rom_s(chain), bc.ours(chain)


@pytest.fixture(scope="module")
def cold_pair():
    return bc.the_rom_s(COLD_CHAIN), bc.ours(COLD_CHAIN)


# ---- THE STATIC LINK CHECK AND THE STEERING (R-CH-1's (d)) ---------------------------------------------------------------
# EVERY `jmp.l` INTO THE ROM WINDOW EACH PRODUCT HOLDS, read off the code (objdump of each ELF; the blob's in its two
# boot entries) — typed here once, as the pin: B2's and B3's entries, the display's two paths and its sync-wait jump; and
# since D4 P4a our lower floppy driver's jumps laid at the ROM entries it ports (the probe; P4b Floprd, Flopver; P4c Flopwr,
# Flopfmt),
# each to its glue entry (R-P4-2).
EVERY_JMP_INTO_THE_ROM = {"head": {}, "blob": {0xfc03b6: 1, 0xfc03e0: 1}, "display": {0xfc0452: 2, 0xfc0e1a: 1},
                          "late": {0xfc047a: 1}, "launch": {0xfc0030: 1}, "floppy": {},
                          "floppy jump 0xfc173a": {0xfcc4b0: 1}, "floppy jump 0xfc1782": {0xfcc400: 1},
                          "floppy jump 0xfc1858": {0xfcc430: 1}, "floppy jump 0xfc1916": {0xfcc448: 1},
                          "floppy jump 0xfc1ae2": {0xfcc418: 1}}
NOT_A_SLICE_START = 0xfc0454            # inside B6's own span: an exit there is no slice's start
APPENDED_EXIT = 0xfc0460


def test_each_product_exits_to_the_rom_s_next_slice_start_and_the_steering_is_that():
    assert bc.EXPECTED_EXITS == EVERY_JMP_INTO_THE_ROM
    assert {name: bc.product_exits(name, bc.products()) for name in bc.EXPECTED_EXITS} == EVERY_JMP_INTO_THE_ROM
    assert bc.link_check() == []
    steering = bc.steering()
    assert set(steering) == {boot_head_end(), boot.HARDWARE_INIT_CALLED, boot.IKBD_RESET_DONE, boot.INTERRUPTS_OPENED,
                             boot.MIDBOOT}
    assert steering[boot.MIDBOOT] == boot_launch.product().base           # the .S lays the ROM's $fc047a first


def boot_head_end():
    return bc.boot_head.ours(boot.HEAD_ENDS)


def _relinked(name, old, new):
    laid = bc.products()
    base, code = laid[name]
    words = struct.pack(">HI", bc.JMP_ABSOLUTE_LONG, old)
    at = code.index(words)
    return {**laid, name: (base, code[:at] + struct.pack(">HI", bc.JMP_ABSOLUTE_LONG, new) + code[at + JMP_LONG_BYTES:])}


@pytest.mark.parametrize("name, old, new", [
    ("display", boot.INTERRUPTS_OPENED, boot.MIDBOOT),             # a path of B5 exiting past B6
    ("late", boot.MIDBOOT, boot.INTERRUPTS_OPENED),                # B6 exiting back to its own start
    ("blob", boot.HARDWARE_INIT_CALLED, boot.IKBD_RESET_DONE),     # B2 exiting past B3
])
def test_a_product_exiting_to_the_wrong_slice_start_is_named(name, old, new):
    """The product's exits named EXACTLY; and where the start it no longer exits to is a steering key, the map too."""
    laid = _relinked(name, old, new)
    expected = {**EVERY_JMP_INTO_THE_ROM[name], new: EVERY_JMP_INTO_THE_ROM[name].get(new, 0) + 1}
    expected[old] -= 1
    expected = {target: count for target, count in expected.items() if count}
    found = bc.link_check(laid=laid)
    assert found[0] == f"{name}: exits {bc._targets(expected)}, not {bc._targets(EVERY_JMP_INTO_THE_ROM[name])}"
    still_exited = any(old in bc.product_exits(product, laid) for product in EVERY_JMP_INTO_THE_ROM)
    assert [line.split(" {")[0] for line in found[1:]] == ([] if still_exited else ["the steering map"])


def test_an_exit_re_targeted_to_no_slice_start_is_named():
    """The display's sync-wait jump sent into the middle of B6: no slice start, and named (the reviewer's first edit)."""
    laid = _relinked("display", boot_display.SYNC_WAIT, NOT_A_SLICE_START)
    expected = {**EVERY_JMP_INTO_THE_ROM["display"], NOT_A_SLICE_START: 1}
    del expected[boot_display.SYNC_WAIT]
    assert bc.link_check(laid=laid) == [f"display: exits {bc._targets(expected)}, not "
                                        f"{bc._targets(EVERY_JMP_INTO_THE_ROM['display'])}"]


def test_an_exit_appended_is_named():
    """The late C with one more `jmp.l` into the ROM appended (the reviewer's second edit): named."""
    laid = bc.products()
    base, code = laid["late"]
    appended = {**laid, "late": (base, code + struct.pack(">HI", bc.JMP_ABSOLUTE_LONG, APPENDED_EXIT))}
    expected = {**EVERY_JMP_INTO_THE_ROM["late"], APPENDED_EXIT: 1}
    assert bc.link_check(laid=appended) == [f"late: exits {bc._targets(expected)}, not "
                                            f"{bc._targets(EVERY_JMP_INTO_THE_ROM['late'])}"]


def test_a_head_that_does_not_end_where_it_falls_through_is_named():
    laid = bc.products()
    base, code = laid["head"]
    assert any(line.startswith("head: ends") for line in bc.link_check(laid={**laid, "head": (base, code[:-2])}))


@pytest.mark.parametrize("arrival", (boot.HARDWARE_INIT_CALLED, boot.IKBD_RESET_DONE, boot.INTERRUPTS_OPENED, boot.MIDBOOT))
def test_a_steering_entry_off_by_two_is_named_and_does_not_hold(arrival):
    steering = {**bc.steering()}
    steering[arrival] += 2
    assert any(line.startswith("the steering map") for line in bc.link_check(steering_map=steering))
    try:
        steps = bc.ours.__wrapped__(COLD_CHAIN, tuple(steering.items()))
    except (boot.Refused, AssertionError):
        return
    rom = bc.the_rom_s(COLD_CHAIN)
    assert any(bc.differences(one, other, COLD_CHAIN) for one, other in zip(rom, steps))


def test_the_steering_refuses_a_machine_not_at_the_arrival(cold_pair):
    _rom, ours = cold_pair
    with pytest.raises(boot.Refused, match="not at 0xfc03e0 where it steers"):
        bc.steered(ours[bc.STEP_NAMES.index(bc.B2)].machine, boot.IKBD_RESET_DONE, bc.steering())


# ---- EVERY BOUNDARY HELD ---------------------------------------------------------------------------------------------------
def test_every_boundary_is_held_from_the_reset_to_gem_entry(pair):
    chain, rom, ours = pair
    assert [step.name for step in ours] == list(bc.STEP_NAMES)
    assert ours[-1].stop == rom[-1].stop == bc.END
    for one, other in zip(rom, ours):
        assert bc.differences(one, other, chain) == [], other.name


def test_the_carries_are_the_slices_named_scratch_and_all_dead_by_fc0452(pair):
    """B2's A3/A4 and scratch, B3's D2/A2 and scratch — EXACTLY those apart (the comparator's set equality), every one of
    them a name in its slice's NOT_HELD (or B2's A4, which B2 names as carried past B3), and NONE from `$fc0452` on: the
    ROM's routines B5 calls lay them on both shores."""
    chain, rom, ours = pair
    assert bc.CARRIED[bc.B2] <= set(boot_sysvars.NOT_HELD)
    assert bc.CARRIED[bc.B3] <= set(bc.boot_hwinit.NOT_HELD[bc.boot_hwinit.STRETCH_KIND]) | {"a4"}
    for name in (bc.B5, bc.B6, bc.B4):
        assert bc.CARRIED[name] == frozenset()
    at_b3 = bc.STEP_NAMES.index(bc.B3)
    assert {"a4", "d2", "a2"} <= {name for name in rom[at_b3].machine.registers
                                  if rom[at_b3].machine.registers[name] != bc.registers_held(ours[at_b3])[name]}


def test_the_rom_s_chain_is_the_same_without_the_blob_outside_its_span():
    span = (bc.blob().base, bc.blob().end)
    for with_it, without in zip(bc.the_rom_s(COLD_CHAIN), bc.the_rom_s(COLD_CHAIN, with_the_blob=False)):
        assert with_it.machine.registers == without.machine.registers and with_it.ledgers == without.ledgers
        assert bc._outside(with_it.machine.ram, span) == bc._outside(without.machine.ram, span)


# ---- EACH SURFACE's NEGATIVE, AND EACH MAPPING's ------------------------------------------------------------------------------
def _changed_ram(step, at, value):
    ram = bytearray(step.machine.ram)
    ram[at] = value
    return step._replace(machine=step.machine._replace(ram=bytes(ram)))


def test_each_held_surface_changed_alone_is_named(cold_pair):
    rom, ours = cold_pair
    last = ours[-1]
    registers = {**last.machine.registers, "d3": last.machine.registers["d3"] ^ 1}
    changed = {
        "stop": last._replace(stop=boot.MIDBOOT),
        "registers": last._replace(machine=last.machine._replace(registers=registers)),
        "ram": _changed_ram(last, addrs.GEMDOS_DATE, last.machine.ram[addrs.GEMDOS_DATE] ^ 1),
        "stored": last._replace(stored=(*last.stored, (boot_late.STACK_RESIDUE[0] - 2, 1))),
        "gemdos": last._replace(ledgers={**last.ledgers, "gemdos": last.ledgers["gemdos"][:-1]}),
        "answers": ours[bc.STEP_NAMES.index(bc.B6)]._replace(answers=()),
        "fdc_events": _b6(ours)._replace(ledgers={**_b6(ours).ledgers, "fdc_events": _b6(ours).ledgers["fdc_events"][:-1]}),
        "fdc_chip": _b6(ours)._replace(ledgers={**_b6(ours).ledgers, "fdc_chip": bytes(len(_b6(ours).ledgers["fdc_chip"]))}),
        "carry": last._replace(carry=last.carry._replace(port_a=last.carry.port_a ^ 1)),
    }
    for surface, step in changed.items():
        index = bc.STEP_NAMES.index(step.name)
        found = bc.differences(rom[index], step, COLD_CHAIN)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


def _b6(steps):
    return steps[bc.STEP_NAMES.index(bc.B6)]


def test_a_carry_that_would_survive_is_named(cold_pair):
    """The carries are held as an exact SET: a register left apart at `$fc0452` — a carry that did not die — is named."""
    rom, ours = cold_pair
    at_b5 = bc.STEP_NAMES.index(bc.B5)
    step = ours[at_b5]
    kept = step._replace(machine=step.machine._replace(registers={**step.machine.registers, "a4": 0}))
    assert any(line.startswith("registers apart ['a4']") for line in bc.differences(rom[at_b5], kept, COLD_CHAIN))


def test_each_linked_vector_is_mapped_back_and_unmapped_is_seen(cold_pair, monkeypatch):
    rom, ours = cold_pair
    for vector in bc.LINKED:
        monkeypatch.setattr(bc, "LINKED", {each: link for each, link in bc.LINKED.items() if each != vector})
        found = bc.differences(rom[-1], ours[-1], COLD_CHAIN)
        firsts = {f"ram, first at {vector + offset:#x}" for offset in range(4)}
        assert any(line in firsts for line in found), (hex(vector), found)
        monkeypatch.undo()


def test_the_returns_into_our_code_are_mapped_inside_the_pre_init_mask_alone(cold_pair, monkeypatch):
    """THE RETURNS MAPPED, EXACTLY: without our dispatcher's, GEMDOS's dead frames hold our `jsr (a0)` return; a launch
    return of ours laid OUTSIDE the mask is not mapped (seen)."""
    rom, ours = cold_pair
    monkeypatch.setattr(bc, "our_returns", lambda: {})
    assert any(line.startswith("ram") for line in bc.differences(rom[-1], ours[-1], COLD_CHAIN))
    monkeypatch.undo()
    outside = next(at for at in range(FREE_RAM_SEARCHED[0], FREE_RAM_SEARCHED[1], LONG_BYTES) if not any(
        base <= at < base + size for base, size, _name in bc.preinit_snapshot.MASK))
    ram, rom_ram = bytearray(ours[-1].machine.ram), bytearray(rom[-1].machine.ram)
    struct.pack_into(">I", ram, outside, boot_launch.product().base + A_LAUNCH_OFFSET)
    struct.pack_into(">I", rom_ram, outside, boot_launch.LAUNCH_SPAN[0] + A_LAUNCH_OFFSET)
    mine = ours[-1]._replace(machine=ours[-1].machine._replace(ram=bytes(ram)))
    theirs = rom[-1]._replace(machine=rom[-1].machine._replace(ram=bytes(rom_ram)))
    found = bc.differences(theirs, mine, COLD_CHAIN)
    assert len(found) == 1 and found[0].startswith("ram, first at") and outside <= int(found[0].split()[-1], 16) < outside + 4


def test_the_returns_mapped_are_our_dispatcher_s_and_the_launch_s_by_offset():
    (ours, rom), = bc.our_returns().items()
    assert rom == 0xfc0830 and struct.unpack_from(">H", BASE_IMAGE, rom - 2)[0] == bc.JSR_INDIRECT_A0
    assert bc._launch_rom_address(boot_launch.product().base) == boot.MIDBOOT
    assert bc._launch_rom_address(boot_launch.product().base - 2) is None


# ---- THE LEDGERS ARE THE SLICES' OWN ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("machine", boot_late.MACHINES)
def test_the_answers_and_the_launch_s_ledgers_are_the_slices_own(machine):
    late = boot_late.our_side(machine)
    launch = boot_launch.our_side(boot_launch.SliceOf(boot_launch.LAUNCH, boot_launch.BLANK))
    for name, chain in bc.SLICES.items():
        if chain.machine != machine:
            continue
        steps = bc.ours(chain)
        b6, b4 = steps[bc.STEP_NAMES.index(bc.B6)], steps[-1]
        assert b6.answers == late.answers, name
        # the FDC ledger the slice's, each poll served THIS chain's GPIP byte (B5's arm: the mono socket's bit 7 low)
        served = boot_display.GPIP_OF[chain.arm.monitor] & ~boot_late.GPIP_INTRQ
        expected = tuple(("poll", served, entry[2]) if entry[0] == "poll" else entry for entry in late.slice.fdc_events)
        assert (b6.ledgers["fdc_events"], b6.ledgers["fdc_chip"]) == (expected, late.slice.fdc_chip), name
        expected = tuple(("poll", served, entry[2]) if entry[0] == "poll" else entry for entry in launch.fdc_events)
        assert (b4.ledgers["gemdos"], b4.ledgers["fdc_events"], b4.ledgers["clock"], b4.ledgers["blanks"]) == (
            launch.gemdos, expected, launch.clock, launch.blanks), name


def test_the_mono_arm_s_poll_is_answered_in_the_chain():
    for name, chain in bc.SLICES.items():
        b5 = bc.ours(chain)[bc.STEP_NAMES.index(bc.B5)]
        poll = (("the sync wait's poll",),) if chain.arm.monitor == boot_display.MONO else ()
        assert b5.answers == (*poll, ("the cartridge's hooks", 0)), name     # the hooks' arrival watched (d0 = 0)


# ---- THE END SURFACES (COLD) ------------------------------------------------------------------------------------------------
def test_at_fc047a_both_shores_are_the_mid_boot_capture_but_d1(cold_pair):
    """B6's own END class, chained: D1 alone (D6, memctrl, its two copies) — D4's lower-driver bytes gone (R-D4-3)."""
    rom, ours = cold_pair
    capture = boot.midboot_machine()
    at_b6 = bc.STEP_NAMES.index(bc.B6)
    theirs = bc.against_the_midboot(rom[at_b6], capture, ours_side=False)
    mine = bc.against_the_midboot(ours[at_b6], capture, ours_side=True)
    assert theirs == mine == (set(boot_late.END_REGISTERS_OWED), set(boot_late.END_APART))


def test_at_gem_entry_both_shores_are_the_pre_init_capture_but_its_own_named_set(cold_pair):
    """D1 (memctrl, `$424`) ALONE — every register equal. Until D4 P5a the lower floppy driver's own state was apart too (B4
    answered the floppy at the upper driver's entries); since P5a B4 runs it through the FDC model and the set is empty."""
    rom, ours = cold_pair
    capture = boot_launch.disk(boot_launch.BLANK).capture()
    theirs = bc.against_the_preinit(rom[-1], capture, ours_side=False)
    mine = bc.against_the_preinit(ours[-1], capture, ours_side=True)
    assert theirs == mine == (set(), {*bc.END_PREINIT_MEMCTRL})
    assert bc.END_PREINIT_LOWER_DRIVER == ()


# ---- THE HAND-OFF NO SLICE SEES -------------------------------------------------------------------------------------------
def test_the_rom_s_later_code_enters_our_linked_entries_and_trap_s_costs_four_a_call(pair):
    """The traps GEMDOS makes in B6 and the launch makes in B4 go through OUR `trap.S` (B2's linked $b4/$b8) — counted on
    its `lea`s — and never through the ROM's dispatcher; the launch's blanks through OUR HBL entry. THE +12 A STEP,
    PROVED: our `trap.S` minus the ROM's dispatcher is 4 cycles a call (`lea abs.l` 12 against `lea d16(pc)` 8), and the
    HBL entry, the ROM's bytes, costs the ROM's exactly."""
    _chain, rom, ours = pair
    for one, other in zip(rom, ours):
        calls = TRAPS_TAKEN.get(other.name, 0)
        assert bc.trap_calls(other, True) == bc.trap_calls(one, False) == calls, other.name
        assert other.spent["the ROM's dispatcher"] == other.spent["the ROM's HBL"] == 0
        assert other.spent["our trap.S"] - one.spent["the ROM's dispatcher"] == TRAP_S_EXTRA_A_CALL * calls
        hbl = HBL_CYCLES if other.name == bc.B4 else 0
        assert other.spent["our HBL"] == one.spent["the ROM's HBL"] == hbl
    assert ours[-1].ledgers["blanks"] == BLANKS_TAKEN


def test_our_linked_entries_stand_in_their_vectors_at_every_boundary_from_b2_on(pair):
    """THE SEVEN LINKED VECTORS HOLD OUR ENTRIES on our side from `$fc03b6` (B2's five) and `$fc03e0` (B3's two) to
    gem_entry — those no chain enters (the VBL, timer C, the ACIA, Line-A, the XBIOS trap) as much as those it does —
    and the ROM's own handlers on the ROM's side: a vector left the ROM's on ours is red here, entered or not."""
    _chain, rom, ours = pair
    symbols = bc.blob().symbols
    for one, other in zip(rom, ours):
        stored = {vector: link for vector, link in bc.LINKED.items()
                  if other.name != bc.HEAD and (other.name != bc.B2 or vector in boot_sysvars.LINKED)}
        for vector, (symbol, rom_address) in stored.items():
            assert struct.unpack_from(">I", other.machine.ram, vector)[0] == symbols[symbol], (other.name, hex(vector))
            assert struct.unpack_from(">I", one.machine.ram, vector)[0] == rom_address, (other.name, hex(vector))


def test_a_chain_of_ours_that_runs_another_slice_s_ported_code_is_refused(cold_pair):
    """THE UNION VET (R2): the late step of ours with cycles in B5's ported span — its own vet alone would pass it."""
    _rom, ours = cold_pair
    at_b6 = bc.STEP_NAMES.index(bc.B6)
    step = ours[at_b6]
    assert bc.rom_own(step._replace(spent={**step.spent, "the ROM's B5": 40})) == 0
    leaked = step._replace(spent={**step.spent, "the ROM's B5": 40})
    with pytest.raises(boot.Refused, match="ran the ROM's ported code {\"the ROM's B5\": 40}"):
        bc._vet_who_ran("a case", (*ours[:at_b6], leaked, *ours[at_b6 + 1:]))


def test_a_chain_of_ours_that_enters_a_linked_entry_no_chain_takes_is_refused(cold_pair):
    _rom, ours = cold_pair
    step = ours[-1]
    leaked = step._replace(spent={**step.spent, "our other linked entries": 44})
    with pytest.raises(boot.Refused, match="entered a linked entry no chain takes"):
        bc._vet_who_ran("a case", (*ours[:-1], leaked))


def test_the_union_of_the_ported_spans_is_every_slice_s(cold_pair):
    """Every span the boot ports is in the union, and ours spends none of it in any step (the vet ran: measured 0)."""
    _rom, ours = cold_pair
    assert set(bc.PORTED_UNION) == {name for name in bc.spans() if name.startswith("the ROM's")} - {
        "the ROM's window", "the ROM's trap leas", "the ROM's lower driver", "the ROM's lower driver ours still runs"}
    assert all(step.spent[name] == 0 for step in ours for name in bc.PORTED_UNION)


# ---- THE BIOS STACK'S DEAD FRAMES, TIGHTENED (R3: the chain's comparison alone) ----------------------------------------------
def _ram_apart(rom_step, our_step, lo, hi):
    mine = bc.ram_held(our_step)
    return {at for at in range(lo, hi) if rom_step.machine.ram[at] != mine[at]}


def test_the_frames_apart_are_measured_from_74ff_at_fc047a_and_exactly_twenty_three_bytes_at_gem_entry(pair):
    """At gem_entry: the BIOS stack's eleven (R-P4-5) and GEMDOS's stack's twelve (R-P5a-1) — and nothing else of the
    megabyte (`differences`' own compare holds the rest)."""
    _chain, rom, ours = pair
    lo, hi = boot_late.STACK_RESIDUE
    at_b6 = bc.STEP_NAMES.index(bc.B6)
    assert min(_ram_apart(rom[at_b6], ours[at_b6], lo, hi)) == bc.FRAMES_APART_FROM
    assert _ram_apart(rom[-1], ours[-1], lo, hi) == bc.B3_FRAMES_LEFT | bc.OUR_DRIVER_S_DEAD_FRAMES
    assert _ram_apart(rom[-1], ours[-1], *GEMDOS_STACK_DEAD_FRAMES) == bc.GEMDOS_STACK_DRIVER_FRAMES
    assert _ram_apart(rom[-1], ours[-1], 0, boot.RAM_BYTES) == bc.APART_AT_THE_END
    mine = bc.ram_held(ours[-1])
    assert {at: (rom[-1].machine.ram[at], mine[at]) for at in bc.APART_AT_THE_END} == bc.VALUES_AT_THE_END


def _a_third_value(pair_of_values):
    return next(value for value in range(0x100) if value not in pair_of_values)


@pytest.mark.parametrize("at", sorted(bc.APART_AT_THE_END))
def test_a_byte_of_the_twenty_three_apart_with_a_third_value_is_seen(cold_pair, at):
    """THE VALUES' NEGATIVE (review RP5a's REQ-1): ours holding neither shore's byte there — still apart, so a position set
    would pass it — is named."""
    rom, ours = cold_pair
    step = _changed_ram(ours[-1], at, _a_third_value(bc.VALUES_AT_THE_END[at]))
    assert bc.differences(rom[-1], step, COLD_CHAIN) == [f"ram, first at {at:#x}"]


def test_a_byte_of_the_rom_s_frames_moved_is_seen(cold_pair):
    """...and the ROM's side of a byte moved (the low byte of its return into its own driver, `$fc1df0`) is named too."""
    rom, ours = cold_pair
    at = 0x14b7
    moved = _changed_ram(rom[-1], at, _a_third_value(bc.VALUES_AT_THE_END[at]))
    assert bc.differences(moved, ours[-1], COLD_CHAIN) == [f"ram, first at {at:#x}"]


@pytest.mark.parametrize("step_name", (bc.B6, bc.B4))
def test_a_stray_store_in_the_bios_stack_s_dead_frames_is_seen(cold_pair, step_name):
    """A byte of ours apart below `$74ff` at `$fc047a`, or anywhere outside the eleven at gem_entry, is named (the reviewer's
    S11: a stray `wr16 $7480` in the late C survived the zeroed field)."""
    rom, ours = cold_pair
    index = bc.STEP_NAMES.index(step_name)
    stray = bc.FRAMES_APART_FROM - 0x7f
    step = _changed_ram(ours[index], stray, ours[index].machine.ram[stray] ^ 0xff)
    assert bc.differences(rom[index], step, COLD_CHAIN) == [f"ram, first at {stray:#x}"]


@pytest.mark.parametrize("at", (min(bc.B3_FRAMES_LEFT), min(bc.OUR_DRIVER_S_DEAD_FRAMES), max(bc.OUR_DRIVER_S_DEAD_FRAMES),
                                min(bc.GEMDOS_STACK_DRIVER_FRAMES), max(bc.GEMDOS_STACK_DRIVER_FRAMES)))
def test_one_of_the_twenty_three_bytes_made_equal_is_seen(cold_pair, at):
    rom, ours = cold_pair
    step = _changed_ram(ours[-1], at, rom[-1].machine.ram[at])
    assert bc.differences(rom[-1], step, COLD_CHAIN) == [f"ram, first at {at:#x}"]


def test_our_driver_s_dead_frames_lie_in_b6_s_last_probe_s_frame_span_where_the_rom_s_run_stores_too(cold_pair):
    """R-P4-5 "Widen exact set 3→11": the eight bytes our lower driver leaves apart at gem_entry lie in the frames of B6's
    LAST probe (drive B:'s) — from 20 bytes under its entry SP (the ROM's depth, ours the same) to that SP — and the ROM's
    own B6 run stores every one of them (so they are frames, not state)."""
    rom, _ours = cold_pair
    last_probe, _called = boot_floppy.b6_calls(boot.COLD)[1]      # drive B:'s (Floprd's own frames lie above it)
    entry_sp = last_probe.machine.registers["isp"]
    assert bc.B6_LAST_PROBE_FRAMES == (entry_sp - boot_floppy.ROM_PROBE_FRAME_BYTES, entry_sp)
    lo, hi = bc.B6_LAST_PROBE_FRAMES
    assert all(lo <= at < hi for at in bc.OUR_DRIVER_S_DEAD_FRAMES)
    stored = {at for start, length in rom[bc.STEP_NAMES.index(bc.B6)].stored for at in range(start, start + length)}
    assert bc.OUR_DRIVER_S_DEAD_FRAMES <= stored
    assert bc.APART_AT_THE_END == bc.B3_FRAMES_LEFT | bc.OUR_DRIVER_S_DEAD_FRAMES | bc.GEMDOS_STACK_DRIVER_FRAMES
    assert len(bc.APART_AT_THE_END) == 23


# GEMDOS's own stack's dead frames: the pre-init MASK's field (`preinit_snapshot.MASK`, "dead frames of GEMDOS's own stack")
GEMDOS_STACK_DEAD_FRAMES = (bc.preinit_snapshot.GEMDOS_STACK_FLOOR, bc.preinit_snapshot.GEMDOS_STACK_TOP)
OURS_ALONE_STORES = frozenset({0x14a9, 0x14aa})     # the two of the twelve inside our deeper store: the ROM's B4 stores neither


def test_our_driver_s_gemdos_stack_frames_lie_in_its_masked_field_where_the_rom_s_b4_stores_too(cold_pair):
    """R-P5a-1 "Widen to 23, named": the twelve bytes our lower driver leaves apart on GEMDOS's stack at gem_entry lie in
    the pre-init mask's field of GEMDOS's dead frames; the ROM's own B4 run stores every one of them but the two inside the
    four bytes ours stores deeper (`OUR_DRIVER_S_DEEPER_STORE`, stored by ours alone) — frames, not state."""
    rom, ours = cold_pair
    field = next((base, base + size) for base, size, why in bc.preinit_snapshot.MASK if "GEMDOS's own stack" in why)
    assert field == GEMDOS_STACK_DEAD_FRAMES
    lo, hi = field
    assert all(lo <= at < hi for at in bc.GEMDOS_STACK_DRIVER_FRAMES | bc.OUR_DRIVER_S_DEEPER_STORE)
    floor, top = bc.B4_LAST_FLOPRD_FRAMES
    assert min(bc.OUR_DRIVER_S_DEEPER_STORE) == floor and max(bc.GEMDOS_STACK_DRIVER_FRAMES) < top

    def stored(step):
        return {at for start, length in step.stored for at in range(start, start + length)}
    assert bc.GEMDOS_STACK_DRIVER_FRAMES - bc.OUR_DRIVER_S_DEEPER_STORE <= stored(rom[-1])      # the ROM's frames
    assert bc.GEMDOS_STACK_DRIVER_FRAMES & bc.OUR_DRIVER_S_DEEPER_STORE == OURS_ALONE_STORES     # ...ours alone stores these
    assert stored(ours[-1]) - stored(rom[-1]) == bc.OUR_DRIVER_S_DEEPER_STORE == bc.STORED_APART[bc.B4]
    assert not stored(rom[-1]) - stored(ours[-1])


def _without(runs, addresses):
    """`runs` (address, length) with the contiguous `addresses` cut out of them, every other byte kept."""
    lo, hi = min(addresses), max(addresses) + 1
    kept = []
    for start, length in runs:
        end = start + length
        kept += [(start, length)] if end <= lo or start >= hi else []
        kept += [(start, lo - start)] if start < lo < end else []
        kept += [(hi, end - hi)] if start < hi < end else []
    return tuple(kept)


@pytest.mark.parametrize("change", ("the deeper store gone", "one more store", "a store the ROM's alone"))
def test_the_deeper_store_is_named_exactly(cold_pair, change):
    """R-P5a-1's negative of the stored set: the four bytes ours stores deeper missing (and nothing else: the ROM's
    direction stays equal, so only the deeper-store check can name it — review RP5a's REQ-2), one more of ours, or one of
    the ROM's ours does not make — each named."""
    rom, ours = cold_pair
    one, other = rom[-1], ours[-1]
    if change == "the deeper store gone":
        other = other._replace(stored=_without(other.stored, bc.OUR_DRIVER_S_DEEPER_STORE))
    elif change == "one more store":
        other = other._replace(stored=(*other.stored, (min(bc.OUR_DRIVER_S_DEEPER_STORE) - 1, 1)))
    else:
        one = one._replace(stored=(*one.stored, (0xe000, 1)))
    assert bc.differences(one, other, COLD_CHAIN) == ["stored: the addresses stored outside the residue differ"]


@pytest.mark.parametrize("at", sorted(set(range(*bc.B4_LAST_FLOPRD_FRAMES)) - bc.GEMDOS_STACK_DRIVER_FRAMES)[:3])
def test_a_further_byte_of_our_driver_s_gemdos_stack_frames_moving_is_seen(cold_pair, at):
    """R-P5a-1's negative: a byte of the same frames outside the twelve, made apart, still reds — the set is exact."""
    rom, ours = cold_pair
    step = _changed_ram(ours[-1], at, rom[-1].machine.ram[at] ^ 0xff)
    assert bc.differences(rom[-1], step, COLD_CHAIN) == [f"ram, first at {at:#x}"]


def test_every_chain_hands_b4_the_carry_b4_s_battery_starts_from():
    """R-D4-2 at `$fc047a`: the ROM's own B6 leaves ONE carry (port A, the chip) on all eight chains — the one B4's own battery
    is handed from the mid-boot capture (`boot_launch.carry_at_the_mid_boot`)."""
    assert {bc.the_rom_s(chain)[bc.STEP_NAMES.index(bc.B6)].carry for chain in bc.SLICES.values()} == {
        boot_launch.carry_at_the_mid_boot()}


@pytest.mark.parametrize("at", sorted(set(range(*bc.B6_LAST_PROBE_FRAMES)) - bc.OUR_DRIVER_S_DEAD_FRAMES)[:3])
def test_a_further_byte_of_the_last_probe_s_frames_moving_is_seen(cold_pair, at):
    """R-P4-5's negative: a byte of the same frames outside the eight, made apart, still reds — the set is exact."""
    rom, ours = cold_pair
    step = _changed_ram(ours[-1], at, rom[-1].machine.ram[at] ^ 0xff)
    assert bc.differences(rom[-1], step, COLD_CHAIN) == [f"ram, first at {at:#x}"]


def test_a_chain_of_ours_that_runs_the_rom_s_dispatcher_is_refused(cold_pair):
    """A vector left the ROM's: our step would run the ROM's dispatcher — refused by name (the who-ran vet)."""
    _rom, ours = cold_pair
    step = ours[-1]
    leaked = step._replace(spent={**step.spent, "the ROM's dispatcher": 464})
    with pytest.raises(boot.Refused, match="ran 464 cycles of the ROM's own code it ports"):
        bc._vet_who_ran("a case", (*ours[:-1], leaked))


# ---- I-1: THE FLOPPY MODEL THROUGH OUR LINKED XBIOS ENTRY ---------------------------------------------------------------------
def _with_xbios(handler, laid=True):
    capture = aes_boot.preinit()
    memory = make_image({0: capture.ram, addrs.VECTOR_TRAP_XBIOS: struct.pack(">I", handler)})
    if laid:
        the_blob = bc.blob()
        memory[the_blob.base:the_blob.base + len(the_blob.blob)] = the_blob.blob
    return memory


def test_the_floppy_model_reads_the_rom_s_table_through_our_linked_xbios_entry():
    ours = aes_boot.Floppy(_with_xbios(bc.blob().symbols[aes_boot.OUR_XBIOS_ENTRY]), aes_boot.blank_disk())
    the_rom_s = aes_boot.Floppy(_with_xbios(addrs.XBIOS_TRAP14), aes_boot.blank_disk())
    assert ours.entries == the_rom_s.entries


@pytest.mark.parametrize("what", ("our BIOS entry", "a copy of our XBIOS entry elsewhere", "our XBIOS entry not laid",
                                  "our XBIOS entry naming another table"))
def test_a_foreign_xbios_vector_is_still_refused(what):
    symbols = bc.blob().symbols
    if what == "our BIOS entry":
        memory = _with_xbios(symbols["bios_trap13"])
    elif what == "our XBIOS entry not laid":
        memory = _with_xbios(symbols[aes_boot.OUR_XBIOS_ENTRY], laid=False)
    elif what == "our XBIOS entry naming another table":     # its `lea`'s operand the BIOS's table: the operand check
        at = symbols[aes_boot.OUR_XBIOS_ENTRY]
        memory = _with_xbios(at)
        struct.pack_into(">I", memory, at + 2, addrs.BIOS_FUNCTION_TABLE)
    else:
        memory = _with_xbios(staging.SCRATCH)
        at = symbols[aes_boot.OUR_XBIOS_ENTRY]
        memory[staging.SCRATCH:staging.SCRATCH + JMP_LONG_BYTES] = memory[at:at + JMP_LONG_BYTES]
    with pytest.raises(aes_boot.Refused, match="does not name the ROM's dispatcher"):
        aes_boot.Floppy(memory, aes_boot.blank_disk())


# ---- ITS PRICE (ruling D9): the table's rows --------------------------------------------------------------------------------
# Each chain's OWN cycles, pinned EXACTLY: (ours, the ROM's) — its only surface is cost. Ours +16 in every chain since the
# floppy ran through the FDC model (ruling D4): B6's two `lea`s that call hdv_boot at the ROM's depth. Since D4 P4a (R-P4-3)
# B6 runs OUR lower floppy driver: since P4b its probes AND hdv_boot's Floprd — ours +30,780 over D4's (the driver's three
# calls, in place), the ROM's +31,152 (its own three: its whole driver, none of it run by ours, `bc.replaced_calls`). Since D4
# P5a (R-P5-1) B4 runs our lower driver too — its two Floprds (the log-in's boot sector, the root): ours +24,652, the ROM's
# +24,576 (its whole driver, `bc.replaced_calls`), in every chain.
OWN = {
    "boot chain, WARM": (2593640, 2619620),
    "boot chain, COLD": (5511716, 5537696),
    "boot chain, WARM, mono, ST low, blitter ABSENT": (2593700, 2619676),
    "boot chain, WARM, colour, ST low, blitter PRESENT": (2593640, 2619620),
    "boot chain, WARM, colour, ST medium, blitter ABSENT": (2593670, 2619646),
    "boot chain, COLD, mono, ST low, blitter ABSENT": (5511776, 5537752),
    "boot chain, COLD, colour, ST low, blitter PRESENT": (5511716, 5537696),
    "boot chain, COLD, colour, ST medium, blitter ABSENT": (5511746, 5537722),
}


def test_the_table_prices_every_chain_on_each_shore_s_own_cycles_under_the_bar():
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_chain(row)]
    assert [row.registered for row in rows] == list(bc.SLICES) == list(OWN)
    bench = tier3.RomBench()
    for row in rows:
        priced, measured = bc.priced(bc.SLICES[row.registered]), tier3.measure(row, bench)
        assert priced.own == OWN[row.registered], (row.registered, priced.own)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


@pytest.mark.parametrize("name", ("boot chain, WARM", "boot chain, COLD"))
def test_the_chain_s_own_cycles_are_pinned_without_the_table(name):
    """THE PRICE IN PLACE (D4 P4a): our lower driver's calls in B6 leave the ROM's rest through `bc.replaced_calls` — held
    here as well as in the table's test, whose import is the derivations' (so a mutation sweep that deselects it still
    reaches the subtraction)."""
    assert bc.priced(bc.SLICES[name]).own == OWN[name]


def test_the_rest_beside_each_shore_s_own_is_held_equal_step_by_step(monkeypatch):
    real = bc.our_own
    monkeypatch.setattr(bc, "our_own", lambda step: real(step) - (4 if step.name == bc.B5 else 0))
    with pytest.raises(AssertionError, match="in B5, beside its own, ours spent"):
        bc.priced(COLD_CHAIN)


# ---- THE CARRIES (R-D4-2), every boundary, from each shore's own runs ----------------------------------------------------------
PORT_A_AT = {bc.HEAD: 0x07, bc.B2: 0x07, bc.B3: 0x27, bc.B5: 0x27, bc.B6: 0x25, bc.B4: 0x24}


def test_port_a_and_the_chip_are_carried_at_every_boundary(pair):
    """PSG port A: the head's store `$07`, through B3's own RMWs (DTR, RTS low, the strobe high: `$27`), and B6's last
    select (drive A:, side 0: `$25`), and B4's last (`$24`: side 1, the root's sector, D4 P5a) — on both shores. THE CHIP:
    MR's (None) until B6 runs the floppy, then the chip B6 left, then the chip B4 left (through the FDC model since P5a)."""
    _chain, rom, ours = pair
    for steps in (rom, ours):
        assert {step.name: step.carry.port_a for step in steps} == PORT_A_AT
        assert [step.carry.chip for step in steps[:bc.STEP_NAMES.index(bc.B6)]] == [None] * bc.STEP_NAMES.index(bc.B6)
        assert _b6(steps).carry.chip == _b6(steps).ledgers["fdc_chip"] is not None
        assert steps[-1].carry.chip == steps[-1].ledgers["fdc_chip"] not in (None, _b6(steps).carry.chip)


def test_no_step_but_b6_and_b4_touches_the_fdc(pair):
    """WHY THE CHIP AT `$fc0452` IS MR's: the head, B2, B3 and B5 reach no register of the DMA block — no store, no declared
    read, no modelled read — on either shore; and none but B6 and B4 (since D4 P5a) arms the model."""
    _chain, rom, ours = pair
    for steps in (rom, ours):
        for step in steps:
            if step.name in bc.FLOPPY_STEPS:
                continue
            ledgers = step.ledgers
            addresses = [entry[0] for name in ("hardware_writes", "io_reads", "hardware_reads") for entry in ledgers[name]]
            assert not [at for at in addresses if boot_late.DMA_BLOCK[0] <= at < boot_late.DMA_BLOCK[1]], step.name
            assert not ledgers.get("fdc_events") and ledgers.get("fdc_chip") is None, step.name


def test_b3_in_the_chain_reads_the_carried_port_a_not_its_battery_s_seed(cold_pair):
    """R-D4-2: inside the chain B3's first read-modify-write of port A reads the head's `$07` — its battery's seed stays
    its battery's (`boot_hwinit.PSG_SEED`)."""
    rom, ours = cold_pair
    for steps in (rom, ours):
        b3 = steps[bc.STEP_NAMES.index(bc.B3)]
        first_read = next(entry for entry in b3.ledgers["psg_events"] if entry[1] == addrs.PSG_PORT_A)
        assert first_read[2] == PORT_A_AT[bc.HEAD]


def test_the_text_under_our_floppy_body_runs_on_no_step_but_our_b6_and_b4(pair):
    """THE SPAN OUR LOWER DRIVER'S BODY IS LAID OVER IS FREE (D4 P4b, widened by R-P4c-1: the VDI's GDP text,
    `[$fcc400, $fcd400)`): the ROM's
    own boot spends no cycle there in any step, and ours none but in B6 and B4 (since D4 P5a), where our driver lies there."""
    _chain, rom, ours = pair
    assert all(step.spent["our floppy"] == 0 for step in rom)
    assert all(step.spent["our floppy"] == 0 for step in ours if step.name not in bc.FLOPPY_STEPS)
    assert all(ours[bc.STEP_NAMES.index(name)].spent["our floppy"] > 0 for name in bc.FLOPPY_STEPS)
