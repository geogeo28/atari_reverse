"""BOOT B5 HELD (`test/boot_display.py`, `src/boot/display/display.c`): the boot's display slice `[$fc03e0, $fc0452)` —
the ROM's own against our C, on the WARM and COLD machines (ruling D8, each A LABELLED STAGING), our side over a copy of
the ROM window (rulings "ROM-window overlay", "Own link rule").

Every arm — colour and mono, the resolution byte's four modes, the blitter ABSENT (the probe's bus error declared,
ruling D5) or PRESENT (its word declared) — held on every observable surface: the stop, every register (the mono arm's
A6 mapped back exactly), the megabyte (the hooks' return mapped back), the stores, every ordered ledger, the faults;
each surface's negative here; each arm's own cost pinned exactly; the price the table's (ruling D9). THE MONO ARM'S SYNC
WAIT has its poll ANSWERED on both shores (R-B5-1, `boot_display.answered_poll`): every answered value is held here to
the ROM's text that would leave it, and the reason it is answered — the kit's refusal — is pinned as measured."""
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs, emu

import boot
import boot_display as bd
import layouts
import rom_data

C = bd.CONSTANTS
LINEA = layouts.parse_constants((bd.RECREATE / "include" / "vdi" / "linea.h",))
ARMS = tuple(bd.SLICES.values())
BAR = 1.10
WORD_BYTES, LONG_BYTES = bd.WORD_BYTES, bd.LONG_BYTES
ABSOLUTE_IO_PAGE = 0xff000000           # objdump's spelling of an `abs.l` I/O address: the 32-bit sign-extended form
BLIT_MODE_PRESENT, BLIT_MODE_ABSENT = 2, 0      # the probe's answers ($fc0f38 `moveq #2,d0`; $fc0f1c `move.w #0,d0`)
PRTBLK_END = 0xfc41a4                   # past Prtblk's own `rts` ($fc41a2): the text the overlay lies in ends
COUNT_THE_POLL_WAITS_FOR = 1            # `moveq #1,d4` ($fc0e2a): what the first poll compares each read with
WAIT_HEAD_WRITES = ((addrs.MFP_TBCR, 0x10), (addrs.MFP_TBCR, 0x00), (addrs.MFP_TBDR, 0xf0), (addrs.MFP_TBCR, 0x08))
WAIT_TAIL_WRITE = (addrs.MFP_TBCR, 0x10)   # the timer reset again, past the poll
DISTINCT_LONG = 0x5a3c_c3a5            # a register pattern whose every byte differs from what the answer writes


# ---- THE ROM'S TEXT: every constant the C is spelt in, read off the instruction that uses it ------------------------------
def test_the_slice_is_spelt_in_the_rom_s_own_operands():
    """`[$fc03e0, $fc0452)` as the ROM's listing reads it, composed out of `boot/display.h`, `boot/head.h`,
    `boot/hwinit.h`, `boot/launch.h` and `addrs.h` — and the slice's end is `move #$2300,sr`."""
    resolution, gpip = ABSOLUTE_IO_PAGE | addrs.SHIFTER_RESOLUTION, ABSOLUTE_IO_PAGE | addrs.MFP_GPIP
    expected = [
        f"moveb {resolution:#x},%d0", f"andb #{addrs.GETREZ_MODE_MASK},%d0", f"cmpb #{C['SHIFTER_MODE_RESERVED']},%d0",
        "bnes 0xfc03f2", f"moveq #{addrs.SHIFTER_MODE_HIGH},%d0", f"moveb %d0,{addrs.SYSVAR_SSHIFTMD:#x}",
        f"moveb {gpip:#x},%d0", "bmis 0xfc0418", f"lea %pc@({bd.SYNC_WAIT_RETURNS:#x}),%fp", f"braw {C['ROM_SYNC_WAIT']:#x}",
        f"moveb #{addrs.SHIFTER_MODE_HIGH},{resolution:#x}", f"moveb #{addrs.SHIFTER_MODE_HIGH},{addrs.SYSVAR_SSHIFTMD:#x}",
        f"bsrw {C['ROM_BLITTER_PROBE']:#x}", f"jsr {C['ROM_LINEA_SET_VECTORS']:#x}", f"jsr {C['ROM_CONSOLE_REINIT']:#x}",
        f"cmpib #{addrs.SHIFTER_MODE_MEDIUM},{addrs.SYSVAR_SSHIFTMD:#x}", "bnes 0xfc043c",
        f"movew {ABSOLUTE_IO_PAGE | bd.PEN_15:#x},{ABSOLUTE_IO_PAGE | bd.PEN_3:#x}",
        f"movel #{bd.RESET_ENTRY},%a5@({addrs.SYSVAR_SWV_VEC})", f"movew #{C['VBLSEM_OPEN']},{addrs.SYSVAR_VBLSEM:#x}",
        "clrw %d0", f"bsrw {C['ROM_CARTRIDGE_HOOKS']:#x}",
    ]
    assert [text for _at, text in rom_data.instructions(*bd.SPAN)] == expected
    assert rom_data.instructions(bd.SPAN[1], bd.SPAN[1] + 4)[0][1] == "movew #8960,%sr"
    assert bd.SPAN == (C["ROM_BOOT_IKBD_RESET_DONE"], C["ROM_DISPLAY_END"]) and C["CARTRIDGE_HOOK_DISPLAY"] == 0
    assert (C["LOW_FOREGROUND_PEN"], C["MEDIUM_FOREGROUND_PEN"]) == (15, 3)


def _wait_text():
    return rom_data.instructions(C["ROM_SYNC_WAIT"], bd.SYNC_WAIT_END)


def test_the_answered_poll_is_the_wait_s_own_span_and_its_answer_what_the_text_leaves():
    """R-B5-1's PROVENANCE, off the ROM's text: the poll begins at the wait's first `move.b (a0),d0` and ends at the
    `move.b #$10,(a1)` past its `dbf`; the first loop exits when D0.b equals D4 (the `moveq #1,d4` above it), the second
    re-loads D4.b from the same register and leaves only when 616 more reads equal it — so D0.b and D4.b both hold the
    count, D3's low word the `dbf` run out (-1), and NOTHING ELSE the poll writes (A0, A1 and every store are the head's
    and the tail's, which run)."""
    text = dict(_wait_text())
    assert text[C["ROM_SYNC_WAIT"]] == f"lea {0xffff0000 | addrs.MFP_TBDR:#x},%a0"
    assert text[0xfc0e2a] == f"moveq #{COUNT_THE_POLL_WAITS_FOR},%d4"
    assert [text[at] for at in sorted(text) if bd.SYNC_POLL <= at < bd.SYNC_POLL_END] == [
        "moveb %a0@,%d0", "cmpb %d4,%d0", f"bnes {bd.SYNC_POLL:#x}", "moveb %a0@,%d4", "movew #615,%d3",
        "cmpb %a0@,%d4", "bnes 0xfc0e42", "dbf %d3,0xfc0e48"]
    assert (text[bd.SYNC_POLL_END], text[bd.SYNC_POLL_END + 4]) == ("moveb #16,%a1@", "jmp %fp@")
    assert bd.SYNC_WAIT_END == bd.SYNC_POLL_END + 6 and bd.DBF_RUN_OUT == 0xffff


@pytest.mark.parametrize("machine", bd.MACHINES)
def test_the_answer_writes_d0_d4_and_d3_alone_from_the_machine_the_rom_s_head_leaves(machine):
    """The ROM's own head run to the poll lays D4 = 1 (`moveq`); the answer copies its low byte to D0, sets D3.w and the
    PC, and touches nothing else — D0's and D3's upper bits kept."""
    arm = bd.Arm(machine, addrs.SHIFTER_MODE_LOW, bd.MONO, bd.ABSENT)
    head = boot.run(bd.labelled(arm), {bd.SYNC_POLL}, **bd.declared(arm))
    # D0 and D3 as the head leaves them, but for a pattern in each: the answer's bytes are seen to be WRITTEN.
    before = {**head.machine.registers, "d0": head.machine.registers["d0"] ^ DISTINCT_LONG, "d3": DISTINCT_LONG}
    after = bd.answered_poll(head.machine._replace(registers=before)).registers
    assert before["d4"] == COUNT_THE_POLL_WAITS_FOR
    assert after == {**before, "pc": bd.SYNC_POLL_END,
                     "d0": before["d0"] & ~0xff | COUNT_THE_POLL_WAITS_FOR, "d3": before["d3"] & ~0xffff | 0xffff}
    with pytest.raises(AssertionError, match="the poll is answered at"):
        bd.answered_poll(bd.labelled(arm))


@pytest.mark.parametrize("machine", bd.MACHINES)
def test_a5_is_zero_where_the_slice_begins(machine):
    """The ROM stores swv_vec through `$46e(a5)`; ours through an image base of 0 — the same store only while A5 = 0."""
    assert bd.start_of(machine).registers["a5"] == 0


# ---- THE PRODUCT AND ITS STAGING ------------------------------------------------------------------------------------------
def test_the_product_lies_at_its_laid_address_clear_of_b4_s_overlay():
    product = bd.product()
    launch = layouts.parse_constants((bd.RECREATE / "include" / "boot" / "launch.h",))["LAUNCH_LAID_AT"]
    launch_bytes = (bd.RECREATE / "build" / "bootlaunch" / "launch.bin").stat().st_size
    assert product.base == C["DISPLAY_LAID_AT"] and product.symbols[bd.ENTRY_SYMBOL] == product.base
    assert launch + launch_bytes <= product.base and product.base + len(product.code) <= PRTBLK_END


def test_our_code_jumps_on_from_every_path_and_links_the_sync_wait_once():
    """The hooks' return our mapping reads is one of the C's `jmp $fc0452` (GCC lays one per palette path); the sync
    wait's link is the one `lea 1f(pc),a6` before its one `jmp`."""
    tails = bd.jumps_to(bd.SPAN[1])
    assert len(tails) == 2
    assert bd.our_sync_wait_return() > bd.product().base


@pytest.mark.parametrize("arm", (*ARMS[:4], *[arm for arm in ARMS if arm.monitor == bd.MONO][:2]),
                         ids=lambda arm: bd.name_of(arm))
def test_the_rom_s_run_is_the_same_with_and_without_the_overlay(arm):
    plain, with_it = bd.the_rom_s(arm), bd.the_rom_s(arm, laid=bd.overlay())
    assert (with_it.slice.stop, with_it.slice.instructions, with_it.slice.cycles, with_it.own) == (
        plain.slice.stop, plain.slice.instructions, plain.slice.cycles, plain.own)
    assert with_it.slice.machine == plain.slice.machine and with_it.slice.stored == plain.slice.stored
    assert all(getattr(with_it.slice, ledger) == getattr(plain.slice, ledger) for ledger in bd.LEDGERS)


def test_a_run_of_ours_that_runs_the_rom_s_slice_is_refused_by_name():
    """THE FALSE GREEN: code laid as ours that jumps into the ROM's own slice would be held equal on its instructions."""
    jump_in = struct.pack(">HI", bd.JMP_ABSOLUTE_LONG, bd.SPAN[0])
    with pytest.raises(boot.Refused, match=r"the run executed \[0xfc03e0, 0xfc0452\)"):
        bd.our_side(ARMS[0], code=jump_in)


# ---- EVERY COLOUR ARM, EVERY HELD SURFACE ---------------------------------------------------------------------------------
@pytest.fixture(scope="module", params=ARMS, ids=lambda arm: bd.name_of(arm))
def a_pair(request):
    arm = request.param
    return arm, bd.the_rom_s(arm), bd.our_side(arm)


def test_ours_is_the_rom_s_on_every_held_surface(a_pair):
    arm, the_rom_s, ours = a_pair
    assert bd.differences(the_rom_s.slice, ours.slice, arm) == []
    assert ours.slice.stop == bd.SPAN[1]
    assert bd.mapped_registers(ours.slice.machine.registers) == the_rom_s.slice.machine.registers


def test_a6_is_apart_on_the_mono_arm_alone_each_shore_s_link(a_pair):
    """R-B5-1 / RB5's I5: on the mono arm A6 reaches $fc0452 as each shore's own link — the ROM's `$fc0408`, ours past
    our `jmp $fc0e1a` — mapped back by that one value; on the colour arms it is equal unmapped."""
    arm, the_rom_s, ours = a_pair
    theirs, mine = the_rom_s.slice.machine.registers["a6"], ours.slice.machine.registers["a6"]
    if arm.monitor == bd.MONO:
        assert (theirs, mine) == (bd.SYNC_WAIT_RETURNS, bd.our_sync_wait_return())
    else:
        assert theirs == mine != bd.our_sync_wait_return()


def test_the_hooks_return_is_the_one_byte_run_apart_and_maps_back(a_pair):
    """Unmapped, the megabytes differ in the stack longword under the entry's stack pointer alone: the ROM's holds
    `$fc0452`, ours one of our `jmp $fc0452`."""
    arm, the_rom_s, ours = a_pair
    lo, hi = bd.hooks_return_slot(arm)
    differing = {at for at, (one, other) in enumerate(zip(the_rom_s.slice.machine.ram, ours.slice.machine.ram)) if one != other}
    assert differing and differing <= set(range(lo, hi))
    assert struct.unpack_from(">I", the_rom_s.slice.machine.ram, lo)[0] == bd.SPAN[1]
    assert struct.unpack_from(">I", ours.slice.machine.ram, lo)[0] in bd.jumps_to(bd.SPAN[1])


def test_the_arm_s_display_state_is_laid(a_pair):
    """What the slice is FOR, on both shores: sshiftmd the mode (3 read as 2), the Line-A's vectors filled for the
    probe's answer, swv_vec the reset, vblsem open; ST medium's pen 3 written with pen 15's colour, alone."""
    arm, the_rom_s, ours = a_pair
    ram = ours.slice.machine.ram
    mono = arm.monitor == bd.MONO
    mode = addrs.SHIFTER_MODE_HIGH if mono or arm.resolution == C["SHIFTER_MODE_RESERVED"] else arm.resolution
    blit_mode = BLIT_MODE_PRESENT if arm.blitter == bd.PRESENT else BLIT_MODE_ABSENT
    assert ram[addrs.SYSVAR_SSHIFTMD] == mode
    assert struct.unpack_from(">H", ram, LINEA["LINEA_BLIT_MODE"])[0] == blit_mode
    assert struct.unpack_from(">I", ram, addrs.SYSVAR_SWV_VEC)[0] == bd.RESET_ENTRY
    assert struct.unpack_from(">H", ram, addrs.SYSVAR_VBLSEM)[0] == C["VBLSEM_OPEN"]
    pen_3 = [(bd.PEN_3, 2, int.from_bytes(bytes(bd.PEN_15_COLOUR), "big"))]
    writes = [tuple(write) for write in ours.slice.hardware_writes]
    if mono:        # the wait's head and tail, then the switch to ST high; no palette fix (sshiftmd is high)
        expected = [(at, 1, value) for at, value in (*WAIT_HEAD_WRITES, WAIT_TAIL_WRITE)]
        expected.append((addrs.SHIFTER_RESOLUTION, 1, addrs.SHIFTER_MODE_HIGH))
    else:
        expected = pen_3 if arm.resolution == addrs.SHIFTER_MODE_MEDIUM else []
    assert writes == expected
    assert len(ours.slice.faults) == (arm.blitter == bd.ABSENT)
    assert [tuple(read)[0] for read in ours.slice.hardware_reads] == [addrs.MFP_GPIP]


def test_our_own_cost_is_pinned_exactly(a_pair):
    """COST IS THE ONLY SURFACE of the C's shape — a second store of sshiftmd (what GCC makes without the barrier) or a
    re-made image base would hold every other surface — so each arm's own instructions and cycles are pinned."""
    arm, _the_rom_s, ours = a_pair
    assert ours.own == OUR_OWN_CYCLES[arm.monitor][arm.resolution]


# Each arm's own cycles: the blitter's two answers run one path of ours (the probe's fault is the ROM's), so 8 costs.
OUR_OWN_CYCLES = {
    bd.COLOUR: {addrs.SHIFTER_MODE_LOW: 292, addrs.SHIFTER_MODE_MEDIUM: 322, addrs.SHIFTER_MODE_HIGH: 292,
                C["SHIFTER_MODE_RESERVED"]: 294},
    bd.MONO: {addrs.SHIFTER_MODE_LOW: 352, addrs.SHIFTER_MODE_MEDIUM: 352, addrs.SHIFTER_MODE_HIGH: 352,
              C["SHIFTER_MODE_RESERVED"]: 354},
}


# ---- EACH SURFACE'S NEGATIVE ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def low_pair():
    arm = ARMS[0]
    return arm, bd.the_rom_s(arm).slice, bd.our_side(arm).slice


def _ram_changed(slice_, at, value):
    ram = bytearray(slice_.machine.ram)
    ram[at] = value
    return slice_._replace(machine=slice_.machine._replace(ram=bytes(ram)))


def _registers_changed(slice_, **changes):
    return slice_._replace(machine=slice_.machine._replace(registers={**slice_.machine.registers, **changes}))


def test_each_held_surface_changed_alone_is_named(low_pair):
    arm, the_rom_s, ours = low_pair
    changed = {
        "stop": ours._replace(stop=bd.SPAN[0]),
        "registers": _registers_changed(ours, d2=ours.machine.registers["d2"] ^ 1),
        "ram": _ram_changed(ours, addrs.SYSVAR_SSHIFTMD, ours.machine.ram[addrs.SYSVAR_SSHIFTMD] ^ 1),
        "stored": ours._replace(stored=(*ours.stored, (addrs.SYSVAR_SSHIFTMD - 1, 1))),
        **{ledger: ours._replace(**{ledger: (*getattr(ours, ledger), ("a staged entry",))}) for ledger in bd.LEDGERS},
    }
    assert set(changed) == set(bd.SURFACES)
    for surface, slice_ in changed.items():
        found = bd.differences(the_rom_s, slice_, arm)
        assert len(found) == 1 and found[0].startswith(surface), (surface, found)


@pytest.mark.parametrize("register", ["d0", "d1", "a0", "a1", "a6", "sr"])
def test_every_register_is_held(low_pair, register):
    arm, the_rom_s, ours = low_pair
    found = bd.differences(the_rom_s, _registers_changed(ours, **{register: ours.machine.registers[register] ^ 1}), arm)
    assert len(found) == 1 and found[0].startswith("registers")


def test_the_hooks_return_maps_back_from_our_jump_alone(low_pair):
    """Any other longword in the slot is seen: a return into our code anywhere but a `jmp $fc0452`, or the ROM's own."""
    arm, the_rom_s, ours = low_pair
    lo, _hi = bd.hooks_return_slot(arm)
    for held in (bd.product().base, bd.SPAN[1] + WORD_BYTES):
        ram = bytearray(ours.machine.ram)
        struct.pack_into(">I", ram, lo, held)
        found = bd.differences(the_rom_s, ours._replace(machine=ours.machine._replace(ram=bytes(ram))), arm)
        assert len(found) == 1 and found[0].startswith(f"ram, first at {lo:#x}"[:12]), (hex(held), found)
    assert bd.mapped_back(the_rom_s.machine.ram, arm) == the_rom_s.machine.ram


# ---- THE MONO ARM: why its poll is answered (R-B5-1), the refusal measured ------------------------------------------------
@pytest.fixture(scope="module")
def mono_pair():
    arm = next(arm for arm in ARMS if arm.monitor == bd.MONO)
    return arm, bd.the_rom_s(arm).slice, bd.our_side(arm).slice


def test_a6_maps_back_from_our_link_alone(mono_pair):
    """Any other A6 is seen: the ROM's own link left in ours unmapped (the value ours never holds), or ours one word off."""
    arm, the_rom_s, ours = mono_pair
    for held in (bd.our_sync_wait_return() + WORD_BYTES, bd.SYNC_WAIT_RETURNS + WORD_BYTES):
        found = bd.differences(the_rom_s, _registers_changed(ours, a6=held), arm)
        assert len(found) == 1 and found[0].startswith("registers"), (hex(held), found)


TIMER_B_DATA = addrs.MFP_TBDR


def test_the_mono_arm_through_the_sync_wait_is_refused_by_the_kit_for_want_of_a_counter():
    """WHY THE MONO ARM STOPS AT THE WAIT (a ruling owed): the wait stores timer B's data register and reads it back as a
    running counter. Declared as a LIST, the reads after the run's own store are STALE (refused by name); declared
    WRITE-THROUGH, every read is the 240 stored and the wait never ends."""
    machine = bd.labelled(bd.Arm(boot.WARM, addrs.SHIFTER_MODE_LOW, bd.MONO, bd.ABSENT))
    mono = {addrs.MFP_GPIP: bd.GPIP_OF[bd.MONO]}
    with pytest.raises(boot.Refused, match=rf"read I/O byte\(s\) THIS run stored to.*first at {TIMER_B_DATA:#x}"):
        boot.run(machine, {bd.SPAN[1]}, io_seed={addrs.SHIFTER_RESOLUTION: 0, TIMER_B_DATA: [1] * 200}, hw_seed=mono,
                 faults=(bd.aes_boot.THE_BLITTER_PROBE,))
    with pytest.raises(boot.NeverArrived) as spun:
        boot.run(machine, {bd.SPAN[1]}, io_seed={addrs.SHIFTER_RESOLUTION: 0, TIMER_B_DATA: emu.write_through(1)},
                 hw_seed=mono, faults=(bd.aes_boot.THE_BLITTER_PROBE,), budget=50_000)
    assert bd.SYNC_POLL <= spun.value.standing < bd.SYNC_POLL_END


# ---- ITS PRICE (ruling D9): the table's rows ------------------------------------------------------------------------------
def test_the_table_prices_every_arm_on_each_shore_s_own_cycles_under_the_bar():
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_display_slice(row)]
    assert [row.registered for row in rows] == list(bd.SLICES)
    bench = tier3.RomBench()
    for row in rows:
        arm = bd.SLICES[row.registered]
        assert (row.entry, row.symbol) == (bd.SPAN[0], bd.ENTRY_SYMBOL)
        priced, measured = bd.priced(arm), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


class _OursOwnReadShort:
    def __getattr__(self, name):
        return getattr(emu, name)

    @staticmethod
    def prof_cycles(lo, hi):
        return emu.prof_cycles(lo, hi) - (4 if lo == bd.product().base else 0)


def test_the_rest_beside_each_shore_s_own_is_held_equal_in_the_price(monkeypatch):
    monkeypatch.setattr(bd, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="beside its own, ours spent"):
        bd.priced(ARMS[0])
