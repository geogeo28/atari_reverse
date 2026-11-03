"""THE FLOPPY'S LOWER DRIVER HELD (D4 P4a, `test/boot_floppy.py`): our probe `$fc173a` and the primitives it runs on,
against the ROM's own, each call B6 makes priced at its arrival (R-P4-3, the new tier-3 row kind), reached through the
6-byte `jmp` laid at the ROM's entry (R-P4-2). Held here: the names spelt in the ROM's own operands; the glue's settle the
ROM's bytes and its tail the ROM's exit but for the A5-relative operands; the product's place; the jump's bytes; the ROM's
run unchanged with our body laid; a run of ours that enters the ROM's ported text refused by name; every arrival held on
every surface (the polls counted, the `$a28` image, every register, the stack above the chain's floor) and priced under
the bar; and each surface changed alone named."""
import struct

import pytest

import harness
from harness import BASE_IMAGE

import boot
import boot_floppy as bf
import boot_late
import boot_launch
from harness import addrs, emu

BAR = 1.10
C = bf.CONSTANTS
ROM_PROBE_RETURN = 0xfc0f88             # hdv_init's `addal #14,sp` after its `jsr $fc173a`
ROM_FLOPRD_RETURN = 0xfc15b0            # hdv_boot's `addal #16,sp` after its `jsr $fc1782` (and every staged call's)
LEA_ABSOLUTE_LONG_A1 = 0x43f9
BSR_W, MOVEQ_MINUS_11, MOVEQ_MINUS_10, RTS, CMPI_L_D16_SP = 0x6100, 0x70f5, 0x70f6, 0x4e75, 0x0caf
ROM_ALERT = 0xfc1ebe                    # the single-drive alert, the glue's `floppy_single_drive_alert`
SPIN_UP_POLLS = C["FDC_WAIT_MOTOR_OFF"] - 1   # the motor-off count down, decremented before each poll
TYPE_ONE_POLLS = C["FDC_WAIT_MOTOR_ON"] - 1     # ...and the motor-on one
CHAIN_FLOOR = 0x74ff                    # the chain holds the BIOS stack byte for byte below it (`boot_chain`), spelt here
                                        # as a literal so a floor moved in the harness is seen (review RP4a's N2)
# THE COMMON ENTRY'S UNKNOWN-TRACK RECOVERY: `tst.w (a1)` at $fc1ca4, its `bpl.s` at $fc1ca8 past it to $fc1cca — the arm
# between, which hdv_boot's Floprd reaches on drive A: absent and B: present alone (ruling R-P4b-1).
ROM_RECORD_TRACK_TEST, ROM_RECOVERY = 0xfc1ca4, (0xfc1caa, 0xfc1cca)
RECOVERY_ROW = f"Floprd of the boot sector, {boot_late.A_ABSENT_B_PRESENT}, COLD"
ROM_RECOVERY_OWN_CYCLES = 132           # the ROM's cycles in the recovery's own text on that row (measured, review RP4b)
ALERT_ROW = "STAGED (R-P4-1): Floprd of drive B: on one drive (the single-drive alert)"
ALERT_HANDLER_CYCLES = 68               # `$fc07e8`'s `move.l etv_critic,-(sp) / rts`, the default's `moveq #-1,d0 / rts`
STAGED_DISK_OFFSET = (5 * 2 + 1) * 9 * 512   # track 5, side 1, sector 1 of an 80x2x9 `.ST`: where the 9-sector read starts
PORT_A_SIDE_0 = 0x01                    # port A bit 0: LOW selects side 1
WD1772_RESTORE_RATE = boot_late.WD1772_RESTORE  # (the commands as the ledger has them, the step rate or'd in)
WD1772_SEEK_RATE = boot_late.WD1772_SEEK
NAMES = tuple(bf.ARRIVALS)
WRITE_ROW = "STAGED (R-P4-1): Flopwr, track 3 side 0 sector 2"
BOOT_SECTOR_ROW = "STAGED (R-P4-1): Flopwr, the boot sector (the media marked CHANGED)"
WRITE_PROTECTED_ROW = "STAGED (R-P4-1): Flopwr, write-protected (no retry)"
FORMAT_ROW = "STAGED (R-P4-1): Flopfmt, track 5 side 0, interleave 1"
INTERLEAVE_2_ROW = "STAGED (R-P4-1): Flopfmt, track 6 side 1, interleave 2"
FORMAT_TIMEOUT_ROW = "STAGED (R-P4-1): Flopfmt, drive A: empty (the write track's timeout)"
FORMAT_WP_ROW = "STAGED (R-P4-1): Flopfmt, write-protected"
TWO_BYTE_VIRGIN_ROW = "STAGED (R-P4-1): Flopfmt, track 7 side 0, a virgin word of two bytes"
INTERLEAVE_10_ROW = "STAGED (R-P4-1): Flopfmt, interleave 10 over 9 sectors, write-protected"
TWO_SECTORS_ROW = "STAGED (R-P4-1): Flopwr, 2 sectors from track 3 sector 2"
TRACK_0_SIDE_1_ROW = "STAGED (R-P4-1): Flopwr, track 0 side 1 sector 1 (not the boot sector)"
TRACK_1_ROW = "STAGED (R-P4-1): Flopwr, track 1 side 0 sector 1 (not the boot sector)"
FLOPWR_EMPTY_ROW = "STAGED (R-P4-1): Flopwr, drive A: empty"
INTERLEAVE_2_WP_ROW = "STAGED (R-P4-1): Flopfmt, interleave 2, write-protected"
BAD_MAGIC_ROW = "STAGED (R-P4-1): Flopfmt, a bad magic (the ROM's stale error exit, kept)"
BAD_MAGIC_WARM_ROW = "STAGED (R-P4-1): Flopfmt, a bad magic, WARM (the ROM's stale error exit, kept)"
BAD_MAGIC_ROWS = (BAD_MAGIC_ROW, BAD_MAGIC_WARM_ROW)
PROBE_NAMES = tuple(name for name in NAMES if name.startswith("the probe"))
READ_NAMES = tuple(name for name in NAMES if name not in PROBE_NAMES)


def _rom_word(at):
    return struct.unpack_from(">H", BASE_IMAGE, at)[0]


def _rom_long(at):
    return struct.unpack_from(">I", BASE_IMAGE, at)[0]


# ---- THE NAMES, SPELT IN THE ROM'S OWN OPERANDS ------------------------------------------------------------------------------
def test_the_probe_s_first_instruction_is_the_six_bytes_the_jump_replaces():
    assert _rom_word(bf.PROBE) == LEA_ABSOLUTE_LONG_A1 and _rom_long(bf.PROBE + 2) == C["FLOPPY_RECORD_A"]
    assert bf.STUB_BYTES == 6 and _rom_long(0xfc1748) == C["FLOPPY_RECORD_B"]


def test_the_driver_s_span_ends_past_its_last_rts():
    assert _rom_word(C["ROM_FLOPPY_LOWER_END"] - 2) == 0x4e75        # $fc1ef6's `rts`
    assert C["ROM_FLOPPY_FLOPRD"] == 0xfc1782 and _rom_word(C["ROM_FLOPPY_FLOPRD"]) == 0x6100      # Floprd's `bsr.w`


@pytest.mark.parametrize("at, value", [
    (0xfc1dc2, "FDC_WAIT_MOTOR_ON"), (0xfc1dd6, "FDC_WAIT_MOTOR_OFF"),          # `move.l #imm,d7`
])
def test_the_waits_are_the_rom_s_counts(at, value):
    assert _rom_long(at) == C[value]


def test_the_settle_and_the_force_s_delay_are_the_rom_s_counts():
    assert _rom_word(0xfc1eb0) == 0x3e3c and _rom_word(0xfc1eb2) == C["FDC_SETTLE_DBF"]
    assert _rom_word(0xfc1e06) == 0x3e3c and _rom_word(0xfc1e08) == C["FDC_FORCE_DBF"]


def test_the_save_area_is_the_common_entry_s():
    assert _rom_word(0xfc1c48) == 0x48f9 and _rom_long(0xfc1c4c) == C["FLOPPY_SAVE_AREA"]


def _symbol_code(name):
    product = bf.product()
    lo = product.symbols[name]
    hi = min(at for at in (*product.symbols.values(), product.base + len(product.code)) if at > lo)
    return product.code[lo - product.base:hi - product.base]


def test_the_glue_s_settle_is_the_rom_s_bytes():
    rom = bytes(BASE_IMAGE[0xfc1eac:0xfc1ebe])
    assert _symbol_code("floppy_settle").rstrip(b"\x4e\x71")[:len(rom)] == rom


def test_the_glue_s_tail_is_the_rom_s_exit_but_for_the_a5_operands():
    """`$fc1cf2..$fc1d28` (the stamp, the result popped, the restore, `flock`, `rts`), its two `d16(a5)` source operands
    spelt `abs.w` (A5 is the caller's in the glue: the same 8 cycles), after our push of the result (the ROM's at
    `$fc1cdc`, before its last seek, which the C makes)."""
    rom = bytearray(BASE_IMAGE[0xfc1cf2:0xfc1d28])
    for at, ours in ((0xfc1d00, 0x21b8), (0xfc1d10, 0x2178)):
        assert struct.unpack_from(">H", rom, at - 0xfc1cf2)[0] in (0x21ad, 0x216d)
        struct.pack_into(">H", rom, at - 0xfc1cf2, ours)
    assert _symbol_code("floppy_leave")[:2 + len(rom)] == bytes.fromhex("2f00") + bytes(rom)


# ---- THE PRODUCT AND ITS STAGING ---------------------------------------------------------------------------------------------
def test_the_body_lies_in_the_vdi_s_gdp_text_past_the_launch_twin_and_in_the_rom_s_fc_page():
    """Past the launch twin's laid span, inside `[$fcc400, $fcd400)` (R-P4c-1), and in $fc0000..$fcffff — the high byte a return into our
    body leaves in a dead frame is then the ROM's own `$fc` (R-P4-5's eleven bytes hold no more)."""
    product = bf.product()
    twin = boot_launch.product(boot_launch.TWIN)
    assert product.base == C["FLOPPY_LAID_AT"] >= twin.base + len(twin.code)
    assert product.base + len(product.code) <= C["FLOPPY_LAID_LIMIT"]
    assert product.base >> 16 == C["FLOPPY_LAID_LIMIT"] - 1 >> 16 == bf.PROBE >> 16


def test_the_jump_at_each_ported_entry_is_a_jmp_to_its_glue():
    for entry, symbol in bf.PORTED.items():
        assert bf.stub(entry) == struct.pack(">HI", bf.JMP_ABSOLUTE_LONG, bf.product().symbols[symbol])
        assert len(bf.stub(entry)) == bf.STUB_BYTES
    assert bf.NEVER_RUN == ((bf.PROBE + bf.STUB_BYTES, C["ROM_FLOPPY_FLOPRD"]),
                            (bf.FLOPRD + bf.STUB_BYTES, C["ROM_FLOPPY_FLOPWR"]),
                            (bf.FLOPWR + bf.STUB_BYTES, C["ROM_FLOPPY_FLOPFMT"]),
                            (bf.FLOPFMT + bf.STUB_BYTES, C["ROM_FLOPPY_FLOPVER"]),
                            (bf.FLOPVER + bf.STUB_BYTES, C["ROM_FLOPPY_VBL"]),
                            (C["ROM_FLOPPY_PRIMITIVES"], C["ROM_FLOPPY_LOWER_END"]))
    entries = (bf.PROBE, bf.FLOPRD, bf.FLOPWR, bf.FLOPFMT, bf.FLOPVER, C["ROM_FLOPPY_LOWER_END"])
    assert bf.ROM_TEXT_STILL_RUN == tuple((one + bf.STUB_BYTES, other) for one, other in zip(entries, entries[1:]))
    for entry in bf.PORTED:         # each jump replaces the ROM's first instructions: the probe's `lea`; the readers' and
        if entry == bf.PROBE:       # Flopwr's `bsr.w $fc1ebe / moveq #err,d0`; Flopfmt's first six bytes of its `cmpi.l`
            assert _rom_word(entry) == LEA_ABSOLUTE_LONG_A1
        elif entry == bf.FLOPFMT:   # ...(8 bytes: the jump splits it — no ROM branch reaches past $fc1916, the closed scan)
            assert _rom_word(entry) == CMPI_L_D16_SP and _rom_long(entry + 2) == C["FLOPFMT_MAGIC"]
        else:
            assert _rom_word(entry) == BSR_W and _rom_word(entry + 4) in (MOVEQ_MINUS_11, MOVEQ_MINUS_10)
            assert entry + 2 + struct.unpack_from(">h", BASE_IMAGE, entry + 2)[0] == ROM_ALERT


@pytest.mark.parametrize("machine", boot_late.MACHINES)
def test_the_rom_s_run_is_the_same_with_our_body_laid(machine):
    body = bf.pieces()[0]
    plain, with_it = boot_late.the_rom_s(machine), boot_late.the_rom_s(machine, laid=body)
    assert with_it.slice.machine == plain.slice.machine and with_it.slice.stored == plain.slice.stored
    assert (with_it.slice.instructions, with_it.slice.cycles) == (plain.slice.instructions, plain.slice.cycles)
    assert all(getattr(with_it.slice, ledger) == getattr(plain.slice, ledger) for ledger in boot_late.LEDGERS)


def test_overlapping_overlays_are_refused():
    body = bf.pieces()[0]
    with pytest.raises(boot.Refused, match="two overlays overlap"):
        boot.overlays(body, boot.overlaid(body.at + 2, b"\x4e\x71\x4e\x71"))


@pytest.mark.parametrize("span", bf.NEVER_RUN, ids=lambda span: f"{span[0]:#x}")
def test_a_call_of_ours_that_runs_the_rom_s_driver_text_is_refused_by_name(span):
    """Our glue entry made a `jmp` into each span of the ROM's text ours must never run: refused by name. The probe's entry
    jumps to the span's first `rts` (back to hdv_init at once) or, in the probe's own text, which holds none, to its first
    word; Flopwr's text (no `rts` either) is entered from Flopwr's own glue on a writable staged row, at its first word."""
    product = bf.product()
    if span[0] == bf.FLOPWR + bf.STUB_BYTES:
        name, symbol, target = WRITE_ROW, bf.PORTED[bf.FLOPWR], span[0]
    else:
        name, symbol = NAMES[0], bf.PORTED[bf.PROBE]
        target = next((word for word in range(span[0], span[1], 2) if _rom_word(word) == RTS), span[0])
    at = product.symbols[symbol] - product.base
    code = product.code[:at] + struct.pack(">HI", bf.JMP_ABSOLUTE_LONG, target) + product.code[at + 6:]
    with pytest.raises(boot.Refused, match=rf"executed the ROM's driver text .*\[{span[0]:#x}, {span[1]:#x}\)"):
        bf.ours(name, code=code)


# ---- THE ARRIVALS --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arm", boot_late.DRIVE_ARMS)
def test_b6_calls_the_probe_twice_from_hdv_init_drive_a_then_b_then_floprd_from_hdv_boot(arm):
    """...and hdv_boot's Floprd of the boot sector, but with no drive at all (`_nflops` 0: it calls nothing)."""
    calls = bf.b6_calls(boot.COLD, arm)
    floprd = [] if arm == boot_late.A_ABSENT else [ROM_FLOPRD_RETURN]
    assert [arrival.returns_to for arrival, _ in calls] == [ROM_PROBE_RETURN] * 2 + floprd
    assert [struct.unpack_from(">H", arrival.machine.ram, arrival.machine.registers["isp"] + 12)[0]
            for arrival, _ in calls[:2]] == [0, 1]


@pytest.fixture(scope="module", params=NAMES)
def a_call(request):
    name = request.param
    return name, bf.the_rom_s(name), bf.ours(name)


def test_ours_is_the_rom_s_on_every_held_surface(a_call):
    name, rom, mine = a_call
    assert bf.differences(name, rom, mine) == []
    assert mine.slice.stop == rom.slice.stop == bf.arrival_of(name).returns_to


def test_our_call_spends_every_cycle_in_our_driver_but_the_handler_both_run_and_is_under_the_bar(a_call):
    """Each shore's own: ours every cycle in our jump and body, the ROM's in its driver — the rest, the critical-error
    handler the single-drive alert calls (the one row that reaches it), equal on both."""
    name, rom, mine = a_call
    rest = mine.slice.cycles - mine.own
    assert rest == rom.slice.cycles - rom.own == (ALERT_HANDLER_CYCLES if name == ALERT_ROW else 0)
    assert mine.own / rom.own <= BAR


def test_the_caller_s_registers_are_saved_at_a28_and_given_back(a_call):
    """The 36 bytes at `$a28` are the caller's D3-D7 / A3-A6, on both shores; and each comes back — but on Flopfmt's bad
    magic, which saves nothing and restores the STALE image (the ROM bug kept: its own test)."""
    name, rom, mine = a_call
    if name in BAD_MAGIC_ROWS:
        return
    arrival = bf.arrival_of(name)
    saved = b"".join(struct.pack(">I", arrival.machine.registers[r]) for r in
                     ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6"))
    at = C["FLOPPY_SAVE_AREA"]
    for shore in (rom, mine):
        assert shore.slice.machine.ram[at:at + len(saved)] == saved
        assert all(shore.slice.machine.registers[r] == arrival.machine.registers[r]
                   for r in ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6"))


@pytest.mark.parametrize("name", PROBE_NAMES)
def test_the_probe_s_d1_and_d2_keep_the_caller_s_upper_bytes_a0_and_a1_are_the_rom_s(name):
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    arrival = bf.arrival_of(name)
    for shore in (rom, mine):
        registers = shore.slice.machine.registers
        for register in ("d1", "d2"):
            assert registers[register] >> 8 == arrival.machine.registers[register] >> 8
        assert registers["a0"] == C["FLOPPY_LAST_ACCESS"]
        drive = struct.unpack_from(">H", arrival.machine.ram, arrival.machine.registers["isp"] + 12)[0]
        assert registers["a1"] == (C["FLOPPY_RECORD_B"] if drive else C["FLOPPY_RECORD_A"])


@pytest.mark.parametrize("name", PROBE_NAMES)
def test_the_probe_s_frames_lie_at_the_rom_s_depth_above_the_chain_s_floor(name):
    """THE STACK BOUND (decision 10, the orchestrator's: the C made to fit): nothing of ours stored under the call's SP
    deeper than the ROM's own 20 bytes — the chain's floor `$74ff` well clear."""
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    sp = bf.arrival_of(name).machine.registers["isp"]
    floor = bf.frames(sp)[0]

    def below(shore):
        return {at for start, length in shore.slice.stored for at in range(start, start + length) if floor <= at < sp}
    assert min(below(mine)) >= min(below(rom)) >= sp - bf.ROM_TIMEOUT_FRAME_BYTES
    if not any(event[0] == "poll" and event[2] > 1 for event in rom.slice.fdc_events):     # no wait timed out
        assert min(below(rom)) == min(below(mine)) == sp - bf.ROM_PROBE_FRAME_BYTES


@pytest.mark.parametrize("name", [name for name in NAMES if "drive A:," in name and boot_late.A_ABSENT in name])
def test_the_spin_up_timeout_counts_the_rom_s_polls(name):
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    for shore in (rom, mine):
        polls = [event for event in shore.slice.fdc_events if event[0] == "poll" and event[2] > 1]
        assert [event[2] for event in polls] == [SPIN_UP_POLLS]


# ---- EACH SURFACE CHANGED ALONE IS NAMED ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cold_call():
    name = NAMES[0]
    return name, bf.the_rom_s(name), bf.ours(name)


def _with_ram(shore, at, value):
    ram = bytearray(shore.slice.machine.ram)
    ram[at] = value
    return shore._replace(slice=shore.slice._replace(machine=shore.slice.machine._replace(ram=bytes(ram))))


def _with_registers(shore, **registers):
    machine = shore.slice.machine
    return shore._replace(slice=shore.slice._replace(machine=machine._replace(registers={**machine.registers, **registers})))


@pytest.mark.parametrize("surface", ("save area", "d1", "x flag", "stop", "below the floor", "stored", "fdc_events",
                                     "psg_events", "hardware_writes", "fdc_chip"))
def test_each_held_surface_changed_alone_is_named(cold_call, surface):
    name, rom, mine = cold_call
    sp = bf.arrival_of(name).machine.registers["isp"]
    if surface == "save area":
        changed, said = _with_ram(mine, 0xa37, mine.slice.machine.ram[0xa37] ^ 1), "ram, first at 0xa37"
    elif surface == "d1":
        changed, said = _with_registers(mine, d1=mine.slice.machine.registers["d1"] ^ 1), "registers"
    elif surface == "x flag":
        changed, said = _with_registers(mine, sr=mine.slice.machine.registers["sr"] ^ 0x10), "registers"
    elif surface == "stop":
        changed, said = mine._replace(slice=mine.slice._replace(stop=0)), "stop"
    elif surface == "below the floor":
        floor = CHAIN_FLOOR - 1
        changed, said = _with_ram(mine, floor, mine.slice.machine.ram[floor] ^ 1), f"ram, first at {floor:#x}"
    elif surface == "stored":
        changed = mine._replace(slice=mine.slice._replace(stored=(*mine.slice.stored, (0x20000, 1))))
        said = "stored"
    elif surface == "fdc_chip":
        changed, said = mine._replace(slice=mine.slice._replace(fdc_chip=b"")), "fdc_chip"
    else:
        ledger = getattr(mine.slice, surface)
        changed = mine._replace(slice=mine.slice._replace(**{surface: ledger[:-1]}))
        said = surface
    found = bf.differences(name, rom, changed)
    assert len(found) == 1 and found[0].startswith(said)


def test_the_call_s_own_frames_alone_are_not_held(cold_call):
    name, rom, mine = cold_call
    sp = bf.arrival_of(name).machine.registers["isp"]
    assert bf.differences(name, rom, _with_ram(mine, sp - 1, mine.slice.machine.ram[sp - 1] ^ 1)) == []


# ---- ITS PRICE (R-P4-3: the new row kind) --------------------------------------------------------------------------------------
# Each call's OWN cycles, pinned EXACTLY: (ours, the ROM's) — since P4b hdv_boot's Floprd and the staged calls (R-P4-1)
# too. Both drives' probes on COLD's four drive arms and WARM's capture
# drives; the two timeouts (the spin-up of no drive / of an empty drive A:) cost the ROM's own count down on both shores.
OWN = {
    "the probe of drive A:, the capture's drives, COLD": (9262, 9456),
    "the probe of drive B:, the capture's drives, COLD": (9272, 9488),
    'the probe of drive A:, drive B: absent, COLD': (9262, 9456),
    'the probe of drive B:, drive B: absent, COLD': (15708, 16114),
    'the probe of drive A:, no drive at all, COLD': (18104590, 18105004),
    'the probe of drive B:, no drive at all, COLD': (15682, 16088),
    'the probe of drive A:, drive A: empty, COLD': (18104546, 18104898),
    'the probe of drive B:, drive A: empty, COLD': (15708, 16114),
    'the probe of drive A:, drive A: absent, B: present, COLD': (18104590, 18105004),
    'the probe of drive B:, drive A: absent, B: present, COLD': (9246, 9462),
    "the probe of drive A:, the capture's drives, WARM": (9262, 9456),
    "the probe of drive B:, the capture's drives, WARM": (9272, 9488),
    "Floprd of the boot sector, the capture's drives, COLD": (12366, 12328),
    'Floprd of the boot sector, drive B: absent, COLD': (12444, 12406),
    'Floprd of the boot sector, drive A: empty, COLD': (48271342, 48272102),
    'Floprd of the boot sector, drive A: absent, B: present, COLD': (36214820, 36215726),
    "Floprd of the boot sector, the capture's drives, WARM": (12366, 12328),
    'STAGED (R-P4-1): Floprd, 9 sectors from track 5 side 1 sector 1': (37342, 36632),
    'STAGED (R-P4-1): Floprd, track 79 side 1 sector 9': (12366, 12328),
    'STAGED (R-P4-1): Floprd, sector 10 (record not found, the recalibrate)': (39286, 39640),
    'STAGED (R-P4-1): Floprd, sector 0 (record not found)': (39286, 39640),
    'STAGED (R-P4-1): Floprd, track 80 (the seek-verify fails)': (32960, 33544),
    "STAGED (R-P4-1): Floprd of drive B:, empty (the seek-verify's timeouts)": (48271268, 48272030),
    'STAGED (R-P4-1): Floprd of drive B: on one drive (the single-drive alert)': (12530, 12490),
    'STAGED (R-P4-1): Flopver, track 0 side 0, 9 sectors': (46432, 45754),
    'STAGED (R-P4-1): Flopver, sectors 8 to 10 (one listed)': (39518, 39452),
    'STAGED (R-P4-1): Flopver, sectors 10 and 11 (both listed)': (52664, 52760),
    'STAGED (R-P4-1): Flopver, track 5 side 1, 2 sectors': (18348, 18300),
    'STAGED (R-P4-1): Flopver of drive B:, empty (the seek-verify fails)': (12069812, 12070034),
    'STAGED (R-P4-1): Flopwr, track 3 side 0 sector 2': (13390, 13340),
    'STAGED (R-P4-1): Flopwr, the boot sector (the media marked CHANGED)': (13416, 13426),
    'STAGED (R-P4-1): Flopwr, sector 10 (record not found)': (42046, 42204),
    'STAGED (R-P4-1): Flopwr, write-protected (no retry)': (13270, 13284),
    'STAGED (R-P4-1): Flopwr, drive A: empty': (72412470, 72413712),
    'STAGED (R-P4-1): Flopwr, 2 sectors from track 3 sector 2': (17496, 17340),
    'STAGED (R-P4-1): Flopwr, track 0 side 1 sector 1 (not the boot sector)': (13390, 13340),
    'STAGED (R-P4-1): Flopwr, track 1 side 0 sector 1 (not the boot sector)': (13390, 13340),
    'STAGED (R-P4-1): Flopfmt, track 5 side 0, interleave 1': (195460, 191622),
    'STAGED (R-P4-1): Flopfmt, track 6 side 1, interleave 2': (195524, 191654),
    'STAGED (R-P4-1): Flopfmt, write-protected': (159112, 156162),
    'STAGED (R-P4-1): Flopfmt, interleave 2, write-protected': (159176, 156194),
    'STAGED (R-P4-1): Flopfmt, track 7 side 0, a virgin word of two bytes': (195460, 191622),
    'STAGED (R-P4-1): Flopfmt, interleave 10 over 9 sectors, write-protected': (172928, 169348),
    "STAGED (R-P4-1): Flopfmt, drive A: empty (the write track's timeout)": (12218618, 12215812),
    "STAGED (R-P4-1): Flopfmt, a bad magic (the ROM's stale error exit, kept)": (4088, 4092),
    "STAGED (R-P4-1): Flopfmt, a bad magic, WARM (the ROM's stale error exit, kept)": (4088, 4092),
}


def test_every_call_is_priced_and_pinned():
    assert list(OWN) == list(NAMES)
    for name in NAMES:
        assert bf.priced(name).own == OWN[name], name


def test_the_table_prices_every_call_on_each_shore_s_whole_call_under_the_bar():
    """R-P4-3's new row kind in the table: one row a call, its costs the call's, the verdict ok."""
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_floppy_call(row)]
    assert [row.registered for row in rows] == list(bf.ARRIVALS) == list(OWN)
    bench = tier3.RomBench()
    for row in rows:
        priced, measured = bf.priced(row.registered), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio <= BAR
        assert tier3.verdict(row, measured, 0, None) == "ok"


# ---- THE FLOOR, INDEPENDENT OF THE HARNESS (review RP4a's N2) --------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_the_arrival_rows_hold_the_bios_stack_from_the_chain_s_floor(name):
    sp = bf.arrival_of(name).machine.registers["isp"]
    assert bf.frames(sp) == (CHAIN_FLOOR, sp)


# ---- THE RECOVERY ARM: A HALT IN P4a, AND NO P4a CALL REACHES IT (review RP4a's R1) ------------------------------------------
def test_the_recovery_arm_is_the_rom_s_text_past_its_bpl():
    assert _rom_word(ROM_RECORD_TRACK_TEST) == 0x4a69 and _rom_word(ROM_RECORD_TRACK_TEST + 2) == 0
    branch = BASE_IMAGE[ROM_RECORD_TRACK_TEST + 4:ROM_RECORD_TRACK_TEST + 6]
    assert branch[0] == 0x6a and ROM_RECORD_TRACK_TEST + 6 + branch[1] == ROM_RECOVERY[1] == ROM_RECOVERY[0] + 0x20


def _rom_s_recovery_cycles(name):
    arrival = bf.arrival_of(name)          # (made before the profile opens)
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        bf._call(arrival)
        return emu.prof_cycles(*ROM_RECOVERY)
    finally:
        emu.prof_enable(False)


@pytest.mark.parametrize("name", NAMES)
def test_one_call_alone_reaches_the_recovery_hdv_boot_s_floprd_with_drive_a_absent(name):
    """THE RECOVERY'S ONE ARM (ruling R-P4b-1): of every call held, the ROM's own run spends cycles in the recovery's text
    on hdv_boot's Floprd with drive A: absent and B: present alone — the probe clears the record's track before its common
    entry reads it, and every other Floprd / Flopver asks after a drive whose probe left its track known."""
    assert _rom_s_recovery_cycles(name) == (ROM_RECOVERY_OWN_CYCLES if name == RECOVERY_ROW else 0)


def test_the_recovery_is_held_on_its_row_the_track_unknown_still_and_the_seek_error():
    """On its row both shores take the recovery — A:'s restore on no drive, the seek to 10, the restore again — leave A:'s
    record UNKNOWN (`$ff00`) and return the seek-verify's -6; every surface held (`differences`, the row's own test)."""
    for shore in (bf.the_rom_s(RECOVERY_ROW), bf.ours(RECOVERY_ROW)):
        ram = shore.slice.machine.ram
        assert struct.unpack_from(">H", ram, C["FLOPPY_RECORD_A"])[0] == C["FLOPPY_UNKNOWN_TRACK"]
        assert shore.slice.machine.registers["d0"] == C["FLOPPY_SEEK_ERROR"] & 0xffffffff
        commands = [event[1] for event in shore.slice.fdc_events if event[0] == "command"]
        assert commands[:3] == [WD1772_RESTORE_RATE, WD1772_SEEK_RATE, WD1772_RESTORE_RATE]


# ---- P4b: THE READ SIDE ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", READ_NAMES)
def test_the_reader_s_frames_lie_above_the_chain_s_floor(name):
    """Floprd's and Flopver's frames — ours and the ROM's — all above the floor the chain holds: each call's deepest store
    in the BIOS stack under its entry SP (the floor's side included, so a deeper store reds; `differences` holds the
    bytes)."""
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    sp = bf.arrival_of(name).machine.registers["isp"]

    def deepest(shore):         # over the whole BIOS stack under the call's SP, the floor's side of it too
        return min(at for start, length in shore.slice.stored for at in range(start, start + length)
                   if boot_late.STACK_RESIDUE[0] <= at < sp)
    assert deepest(mine) >= CHAIN_FLOOR and deepest(rom) >= CHAIN_FLOOR


def test_a_staged_call_lays_its_arguments_where_floprd_s_stand_and_enters_its_entry():
    """R-P4-1: B6's machine at its Floprd arrival, the arguments laid past the return, the PC the entry named; the return
    hdv_boot's; each shore's disk its own writable copy (`Arrival.writable`)."""
    for name, staged in bf.STAGED.items():
        arrival = bf.arrival_of(f"STAGED (R-P4-1): {name}")
        floprd, _ = bf.b6_calls(staged.boot, staged.drive_arm)[bf.B6_FLOPRD_INDEX]
        sp = arrival.machine.registers["isp"]
        assert sp == floprd.machine.registers["isp"] and arrival.returns_to == ROM_FLOPRD_RETURN
        if isinstance(staged, bf.StagedFormat):
            layout = bf.FORMAT_ARGUMENTS
            magic = C["FLOPFMT_MAGIC"] if staged.magic is None else staged.magic
            laid = (bf.STAGED_BUFFER, 0, staged.drive, staged.spt, staged.track, staged.side, staged.interleave, magic,
                    staged.virgin)
        else:
            layout = bf.STAGED_ARGUMENTS
            laid = (bf.STAGED_BUFFER, 0, staged.drive, staged.sector, staged.track, staged.side, staged.count)
        assert struct.unpack_from(layout, arrival.machine.ram, sp + 4) == laid
        assert arrival.machine.registers["pc"] == staged.entry and arrival.writable
        assert arrival.protected == staged.protected
        assert arrival.machine.registers == {**floprd.machine.registers, "pc": staged.entry}   # the arrival's own
        outside = struct.calcsize(layout) + 4
        assert arrival.machine.ram[:sp + 4] + arrival.machine.ram[sp + outside:] == (
            floprd.machine.ram[:sp + 4] + floprd.machine.ram[sp + outside:])
        assert bf.STAGED_LABEL in arrival.machine.label


def test_the_nine_sector_read_lands_the_disk_s_track_5_side_1_at_a_buffer_whose_high_byte_is_not_0():
    """THE DMA ADDRESS's HIGH BYTE (P4a's open `dma_hi_from_top_byte`, pinned): the buffer $30000's high byte 3 written to
    $ff8609 on both shores, the nine sectors landing there; side 1's select bit in port A (P4a's open `side_ignored`)."""
    name = "STAGED (R-P4-1): Floprd, 9 sectors from track 5 side 1 sector 1"
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    disk = bytes(boot_late.the_disk())
    for shore in (rom, mine):
        writes = shore.slice.hardware_writes
        assert (C["FDC_DMA_ADDRESS_HI"], 1, bf.STAGED_BUFFER >> 16) in writes
        ram = shore.slice.machine.ram
        assert ram[bf.STAGED_BUFFER:bf.STAGED_BUFFER + 9 * 512] == disk[STAGED_DISK_OFFSET:STAGED_DISK_OFFSET + 9 * 512]
        port_a = [value for kind, register, value in shore.slice.psg_events
                  if kind == emu.os_map.OS_PSG_EVENT_WRITE and register == addrs.PSG_PORT_A]
        assert port_a and all(value & PORT_A_SIDE_0 == 0 for value in port_a)        # side 1: the bit LOW
        assert shore.images[0] == disk                                                  # a read writes nothing


def test_the_single_drive_alert_asks_the_handler_remembers_the_letter_and_rewrites_the_caller_s_drive():
    name = ALERT_ROW
    arrival = bf.arrival_of(name)
    sp = arrival.machine.registers["isp"]
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        ram = shore.slice.machine.ram
        assert struct.unpack_from(">H", ram, C["FLOPPY_SINGLE_DRIVE_LETTER"])[0] == 1
        assert struct.unpack_from(">H", ram, C["FLOPPY_WP_SEEN"])[0] == 0xffff
        assert struct.unpack_from(">H", ram, sp + 4 + bf.CONSTANTS["FLOPPY_ARG_DRIVE"])[0] == 0
        assert shore.slice.machine.registers["a1"] == C["FLOPPY_RECORD_A"]


@pytest.mark.parametrize("name, d0, d1", [
    ("STAGED (R-P4-1): Floprd, sector 10 (record not found, the recalibrate)", -8, -8),
    ("STAGED (R-P4-1): Floprd, track 80 (the seek-verify fails)", -6, None),
    ("STAGED (R-P4-1): Floprd of drive B:, empty (the seek-verify's timeouts)", -6, None),
    ("STAGED (R-P4-1): Flopver of drive B:, empty (the seek-verify fails)", -6, None),
])
def test_each_error_arm_returns_the_rom_s_error_and_d1_the_decode_s(name, d0, d1):
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        registers = shore.slice.machine.registers
        assert registers["d0"] == d0 & 0xffffffff
        if d1 is not None:
            assert registers["d1"] == d1 & 0xffffffff


def test_the_recalibrate_runs_on_the_second_last_retry():
    """Record not found: seek-verify, read; seek-verify, read; then the recalibrate — restore, seek 5, seek-verify — and
    the last seek-verify and read; on both shores (the FDC ledger's commands, in order)."""
    name = "STAGED (R-P4-1): Floprd, sector 10 (record not found, the recalibrate)"
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        commands = [event[1] for event in shore.slice.fdc_events if event[0] == "command"]
        assert commands == [0x17, 0x80, 0x17, 0x80, 0x03, 0x13, 0x17, 0x17, 0x80, 0x13]


def test_flopver_lists_the_sector_it_cannot_read_and_returns_0():
    name = "STAGED (R-P4-1): Flopver, sectors 8 to 10 (one listed)"
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        ram = shore.slice.machine.ram
        assert struct.unpack_from(">HH", ram, bf.STAGED_BUFFER) == (10, 0)
        assert shore.slice.machine.registers["d0"] == 0
        assert shore.slice.machine.registers["a2"] == bf.STAGED_BUFFER + 2       # A2: the list's cursor, handed back


@pytest.mark.parametrize("name", [name for name in READ_NAMES if ("timeouts" in name or "drive A: empty" in name)
                                  and ("Floprd" in name or "Flopver" in name)])
def test_the_seek_verify_s_timeouts_count_the_rom_s_polls(name):
    """An empty drive: each seek-verify hangs (no index pulse), the type-I count down's 262,143 polls, on both shores."""
    polls = [[event[2] for event in shore.slice.fdc_events if event[0] == "poll" and event[2] > 1]
             for shore in (bf.the_rom_s(name), bf.ours(name))]
    assert polls[0] == polls[1] == [TYPE_ONE_POLLS] * 4


def test_flopwr_s_empty_drive_recalibrates_at_once_counting_the_rom_s_polls():
    """Flopwr's failed seek-verify recalibrates AT ONCE ($fc1906): six type-I hangs of 262,143 polls, on both shores."""
    polls = [[event[2] for event in shore.slice.fdc_events if event[0] == "poll" and event[2] > 1]
             for shore in (bf.the_rom_s(FLOPWR_EMPTY_ROW), bf.ours(FLOPWR_EMPTY_ROW))]
    assert polls[0] == polls[1] == [TYPE_ONE_POLLS] * 6


def test_the_staged_disk_changed_alone_is_named():
    name = "STAGED (R-P4-1): Floprd, track 79 side 1 sector 9"
    rom, mine = bf.the_rom_s(name), bf.ours(name)
    changed = mine._replace(images=(bytes(len(mine.images[0])), *mine.images[1:]))
    assert bf.differences(name, rom, changed) == ["images: the disks the two shores left differ"]


@pytest.mark.parametrize("name", [*READ_NAMES])
def test_every_reader_but_one_asks_after_a_known_track(name):
    """WHY ONE ROW ALONE REACHES THE RECOVERY: at every Floprd / Flopver arrival the record of the drive the request
    reaches — drive A: wherever the single-drive alert rewrites it (a one-drive machine) — holds a known track, but at
    hdv_boot's Floprd with drive A: absent and B: present (R-P4b-1), where A:'s failed probe left it `$ff00`."""
    arrival = bf.arrival_of(name)
    ram, sp = arrival.machine.ram, arrival.machine.registers["isp"]
    drive = struct.unpack_from(">H", ram, sp + 4 + bf.CONSTANTS["FLOPPY_ARG_DRIVE"])[0]
    if struct.unpack_from(">H", ram, C["SYSVAR_NFLOPS"])[0] == 1:
        drive = 0
    record = C["FLOPPY_RECORD_B"] if drive else C["FLOPPY_RECORD_A"]
    assert (struct.unpack_from(">h", ram, record)[0] < 0) == (name == RECOVERY_ROW)


def test_flopver_resets_its_retries_per_sector_both_sectors_listed():
    """REVIEW RP4b's R2, pinned on real disk data: sectors 10 and 11 of a 9-sector track both fail — the SECOND gets its
    own three reads and the recalibrate again (its retries reset per sector), and both are listed."""
    name = "STAGED (R-P4-1): Flopver, sectors 10 and 11 (both listed)"
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        assert struct.unpack_from(">HHH", shore.slice.machine.ram, bf.STAGED_BUFFER) == (10, 11, 0)
        commands = [event[1] for event in shore.slice.fdc_events if event[0] == "command"]
        assert commands.count(boot_late.WD1772_READ_SECTOR) == 6 and commands.count(boot_late.WD1772_RESTORE) == 2


# ---- P4c: THE WRITE SIDE ------------------------------------------------------------------------------------------------------
SECTOR_BYTES = C["FLOPPY_SECTOR_BYTES"]
TRACK_BYTES = 6250        # one DD track's raw length (250 kbit/s at 300 rpm): every ID field the builder lays starts in it
SECTORS_A_TRACK, SIDES = 9, 2               # the 80x2x9 `.ST` every disk of the project is (R-D4-1)


def _disk_offset(track, side, sector):
    return ((track * SIDES + side) * SECTORS_A_TRACK + sector - 1) * SECTOR_BYTES


def _commands(shore):
    return [event[1] for event in shore.slice.fdc_events if event[0] == "command"]


@pytest.mark.parametrize("name, sectors", [(WRITE_ROW, 1), (TWO_SECTORS_ROW, 2)])
def test_flopwr_writes_each_sector_from_the_next_512_bytes_of_the_buffer(name, sectors):
    """One Write Sector per sector, each sending the buffer's next 512 bytes — the 2-sector row through the loop's
    continuation ($fc18de..$fc18fc: the next sector's register and DMA address set, the retries reset) — and the disk
    left holding the buffer there, on both shores. (B6's buffer and the blank disk's track 3 are both zeros, so the image
    alone cannot tell which sectors were written: the DMA's trail and the chip's sector register — the differential's
    `fdc_chip` — do.)"""
    expected = []
    for n in range(sectors):
        expected += [("command", C["WD1772_WRITE_SECTOR"], 0), ("dma_out", bf.STAGED_BUFFER + n * SECTOR_BYTES, SECTOR_BYTES)]
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        events = [event for event in shore.slice.fdc_events if event[0] == "dma_out"
                  or event[:2] == ("command", C["WD1772_WRITE_SECTOR"])]
        assert events == expected
        at, size = _disk_offset(3, 0, 2), sectors * SECTOR_BYTES
        ram = shore.slice.machine.ram
        assert shore.images[0][at:at + size] == ram[bf.STAGED_BUFFER:bf.STAGED_BUFFER + size]


@pytest.mark.parametrize("name, changed", [(BOOT_SECTOR_ROW, True), (WRITE_ROW, False), (TRACK_0_SIDE_1_ROW, False),
                                           (TRACK_1_ROW, False)])
def test_flopwr_marks_the_media_changed_on_the_boot_sector_alone(name, changed):
    """`$fc1862`: sector 1 of track 0 side 0 alone — each of the sector, the track and the side decisive."""
    before = bf.arrival_of(name).machine.ram[C["FLOPPY_MEDIA_MODE"]]
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        mode = shore.slice.machine.ram[C["FLOPPY_MEDIA_MODE"]]
        assert mode == (C["FLOPPY_MEDIA_CHANGED"] if changed else before) and before != C["FLOPPY_MEDIA_CHANGED"]


def test_a_write_protected_disk_is_the_decode_s_minus_13_at_once_no_retry():
    """THE DECODE's WRITE-PROTECT ARM (P4b's unpinned item, PINNED): one Write Sector, the status's bit 6, D0 and D1 -13,
    the disk untouched — on both shores."""
    for shore in (bf.the_rom_s(WRITE_PROTECTED_ROW), bf.ours(WRITE_PROTECTED_ROW)):
        registers = shore.slice.machine.registers
        assert registers["d0"] == registers["d1"] == C["FLOPPY_WRITE_PROTECTED"] & 0xffffffff
        assert _commands(shore).count(C["WD1772_WRITE_SECTOR"]) == 1
        assert shore.images[0] == bytes(boot_late.the_disk())


def _sector_ids(ram):
    """The sector numbers of the ID fields the builder laid in the buffer, in track order."""
    track, ids, at = ram[bf.STAGED_BUFFER:bf.STAGED_BUFFER + TRACK_BYTES], [], 0
    while (at := track.find(bytes([C["TRACK_MARK_PREFIX"]] * 3 + [C["TRACK_ID_MARK"]]), at)) >= 0:
        ids.append(track[at + 6])
        at += 4
    return ids


@pytest.mark.parametrize("name, order", [(FORMAT_WP_ROW, [1, 2, 3, 4, 5, 6, 7, 8, 9]),
                                         (INTERLEAVE_2_WP_ROW, [1, 3, 5, 7, 9, 2, 4, 6, 8]),
                                         (INTERLEAVE_10_ROW, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])])
def test_flopfmt_builds_the_track_in_the_interleave_s_order(name, order):
    """The ID fields the builder laid, in track order — read on the write-protected rows, where no verify reads the
    sectors back over the buffer. Both loops test at the bottom ($fc1a3a, $fc1a44): an interleave above the sectors a
    track still builds each pass's first sector — sector 10 of a 9-sector track."""
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        assert _sector_ids(shore.slice.machine.ram) == order


@pytest.mark.parametrize("name", (FORMAT_ROW, INTERLEAVE_2_ROW, TWO_BYTE_VIRGIN_ROW))
def test_flopfmt_leaves_the_virgin_track_on_the_disk_verified(name):
    staged = bf.STAGED[name.split(": ", 1)[1]]
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        at = _disk_offset(staged.track, staged.side, 1)
        assert shore.images[0][at:at + SECTORS_A_TRACK * SECTOR_BYTES] == staged.virgin.to_bytes(2, "big") * (
            SECTORS_A_TRACK * SECTOR_BYTES // 2)
        assert shore.slice.machine.registers["a2"] == bf.STAGED_BUFFER          # the verify's list, empty
        assert shore.slice.machine.ram[C["FLOPPY_MEDIA_MODE"]] == C["FLOPPY_MEDIA_CHANGED"]


def test_the_fill_hands_d1_back_holding_its_last_minus_1():
    """THE FILL's D1 RESIDUE (R-P4c-2's idiom): where the write track times out, nothing decodes after the fills — D1's low
    word is the last `dbf`'s -1, its high word the caller's, on both shores; and the write track's poll-first count."""
    arrival = bf.arrival_of(FORMAT_TIMEOUT_ROW)
    for shore in (bf.the_rom_s(FORMAT_TIMEOUT_ROW), bf.ours(FORMAT_TIMEOUT_ROW)):
        d1 = shore.slice.machine.registers["d1"]
        assert d1 & 0xffff == 0xffff and d1 >> 16 == arrival.machine.registers["d1"] >> 16
        assert shore.slice.machine.registers["d0"] == 0xffffffff
        polls = [event[2] for event in shore.slice.fdc_events if event[0] == "poll" and event[2] > 1]
        assert polls == [C["FDC_WAIT_MOTOR_ON"]]


@pytest.mark.parametrize("name", BAD_MAGIC_ROWS)
def test_the_bad_magic_exit_runs_on_the_caller_s_registers_the_rom_bug_kept(name):
    """THE BAD-MAGIC ROM BUG (the user, 2026-11-02: kept): no common entry — the exit stores its mode words through the
    caller's A6 (hdv_boot's frame word, `$754e`: the last, `$80`), writes the caller's A1's word (drive B:'s record, track
    0) to the FDC under the chip's last mode — a STRAY RESTORE — returns the stale `$a26`, marks the stale drive's media
    maybe changed, stamps the stale drive's last access with `_hz_200` read through the caller's A5, and gives back the
    registers of the STALE `$a28` image, on both shores — at COLD's arrival and WARM's (where `_hz_200` is not 0)."""
    arrival = bf.arrival_of(name)
    before = arrival.machine
    a6, a1 = before.registers["a6"], before.registers["a1"]
    stale_drive = struct.unpack_from(">H", before.ram, C["FLOPPY_DRIVE"])[0]
    stale_error = struct.unpack_from(">h", before.ram, C["FLOPPY_ERROR"])[0]
    save = struct.unpack_from(">9I", before.ram, C["FLOPPY_SAVE_AREA"])
    tick = struct.unpack_from(">I", before.ram, before.registers["a5"] + addrs.SYSVAR_HZ_200)[0]
    assert tick or name == BAD_MAGIC_ROW                # (WARM's tick is not 0: a read through any other base shows)
    for shore in (bf.the_rom_s(name), bf.ours(name)):
        machine = shore.slice.machine
        assert struct.unpack_from(">H", machine.ram, a6)[0] == C["FDC_MODE_STATUS"]
        assert _commands(shore)[:2] == [WD1772_RESTORE_RATE & ~3 | struct.unpack_from(">H", before.ram, a1)[0],
                                        WD1772_SEEK_RATE]
        assert machine.registers["d0"] == stale_error & 0xffffffff
        assert machine.ram[C["FLOPPY_MEDIA_MODE"] + stale_drive] == C["FLOPPY_MEDIA_MAYBE"]
        assert struct.unpack_from(">I", machine.ram, C["FLOPPY_LAST_ACCESS"] + 4 * stale_drive)[0] == tick
        restored = tuple(machine.registers[name] for name in ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6"))
        assert restored == save
