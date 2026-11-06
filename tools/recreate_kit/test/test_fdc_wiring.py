"""Pin the FDC/DMA model's PYTHON SURFACE (TRAP_MODEL.md, "Phase 17") — `emu`'s arming, chip save/load, ledger and
refusals, and `harness.differential`'s refusal to run while it is armed — on the kit's miniature project
(`kit_smoke_project.bind()`, the binding `harness`/`emu` need at import).

The chip's semantics are test_fdc_model.py's, through a C probe; this suite is the layer above: that what a case
declares in Python reaches the oracle, and that what the oracle could not describe comes back as a refusal by name.
The routine it runs is the C probe's own minimal 68000 driver, read out of `fdc_model_probe.c` (one source).
"""
import re
import struct

from pathlib import Path

import pytest

from kit_smoke_project import bind

harness = bind()
emu = harness.emu

PROBE_SRC = Path(__file__).with_name("fdc_model_probe.c")
DRIVER_AT, BUFFER = 0x70000, 0x71000      # free image above the miniature project's program
BYTE_READ_AT = 0x72000
FLOOD_AT = 0x73000
CMD_READ, CMD_READ_MODE_COUNT = 0x80, 0x90
CMD_WRITE, CMD_WRITE_MODE_COUNT = 0xA0, 0x190
PORT_A_DRIVE_A_SIDE_0 = 0x05
WAIT_COUNT = 1000
GPIP, GPIP_DECLARED, GPIP_ASSERTED = 0xFFFA01, 0xFF, 0xDF
DMA_DATA, MOTOR = 0xFF8604, 0x80
SECTOR_BYTES = 512
FILL_SEED, FILL_STRIDE = 0x3B, 7
MOVE_B_ABSL_TO_D1, RTS = 0x1239, 0x4E75
MAX_INSNS = 100_000
# `move.w #$82,$ff8606 / loop: move.w $ff8604,d1 / subq.l #1,d0 / bne.s loop / rts` — d0 track-register reads, each its
# own READ entry (only polls merge). The count is the run's d0, so the cap is read from the .so (emu.FDC_LOG_MAX).
FLOOD = (0x33FC, 0x0082, 0x00FF, 0x8606, 0x3239, 0x00FF, 0x8604, 0x5380, 0x66F6, 0x4E75)
FLOOD_INSNS_PER_READ = 3


def _driver_words():
    """The probe's DRIVER[] table, parsed rather than copied (one source for the planted driver)."""
    table = re.search(r"static const uint16_t DRIVER\[\] = \{(.*?)\};", PROBE_SRC.read_text(), re.S).group(1)
    return [int(word, 16) for word in re.findall(r"0x[0-9a-f]{4}", table)]


def _image():
    image = harness.make_image()
    code = struct.pack(f">{len(_driver_words())}H", *_driver_words())
    image[DRIVER_AT:DRIVER_AT + len(code)] = code
    image[BYTE_READ_AT:BYTE_READ_AT + 8] = struct.pack(">HIH", MOVE_B_ABSL_TO_D1, DMA_DATA, RTS)
    image[FLOOD_AT:FLOOD_AT + 2 * len(FLOOD)] = struct.pack(f">{len(FLOOD)}H", *FLOOD)
    return image


def _disk():
    return bytearray((i * FILL_STRIDE + FILL_SEED) & 0xFF for i in range(emu.FDC_IMAGE_BYTES))


READ_SECTOR_1 = {"d0": CMD_READ, "d2": CMD_READ_MODE_COUNT, "d3": 1, "d4": PORT_A_DRIVE_A_SIDE_0, "d5": BUFFER,
                 "d6": 1, "d7": WAIT_COUNT}
WRITE_SECTOR_1 = {**READ_SECTOR_1, "d0": CMD_WRITE, "d2": CMD_WRITE_MODE_COUNT}


def _read_sector(registers=READ_SECTOR_1, **declared):
    final, writes, out = emu.run(_image(), DRIVER_AT, dict(registers), max_insns=MAX_INSNS,
                                 hw_seed={GPIP: GPIP_DECLARED}, **declared)
    return final, writes, out


@pytest.fixture(autouse=True)
def disarmed_after():
    """The model is process-global oracle state: every case leaves it disarmed, as it found it."""
    yield
    emu.fdc_disarm()


def test_an_armed_read_lands_in_the_image_joins_the_writes_and_is_ledgered():
    disk = _disk()
    emu.fdc_arm(emu.FdcDrive(disk))
    final, writes, out = _read_sector()
    assert final[BUFFER:BUFFER + SECTOR_BYTES] == disk[:SECTOR_BYTES]
    assert all(addr in writes for addr in range(BUFFER, BUFFER + SECTOR_BYTES))
    assert out["d1"] & 0xFFFF == MOTOR
    assert emu.fdc_events() == [("command", CMD_READ, 0), ("dma_in", BUFFER, SECTOR_BYTES), ("done", MOTOR, 0),
                                ("poll", GPIP_ASSERTED, 1), ("read", DMA_DATA, MOTOR)]


def test_the_chip_a_run_left_is_saved_and_declared_whole():
    """R-D4-2: `fdc_state()` is the chip the run LEFT; declared, it is the chip the next run STARTS from — and a run
    that touches no register leaves it exactly as declared."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    _read_sector()
    left = emu.fdc_state()
    assert left != emu.fdc_power_on_state()
    emu.fdc_declare(left)
    image = harness.make_image()
    image[DRIVER_AT:DRIVER_AT + 2] = struct.pack(">H", RTS)
    emu.run(image, DRIVER_AT, max_insns=MAX_INSNS)
    assert emu.fdc_state() == left
    emu.fdc_arm(emu.FdcDrive(_disk()))            # re-arming declares MR's chip again — and drops the one left
    assert emu.fdc_state() == emu.fdc_power_on_state()
    emu.run(image, DRIVER_AT, max_insns=MAX_INSNS)
    assert emu.fdc_state() == emu.fdc_power_on_state()


def test_every_run_starts_from_the_declared_chip_not_the_last_one():
    """The declaration is re-installed per run, as every seed is: after a read moved the chip, a run that touches no
    register leaves exactly the DECLARED chip — never the one the read left."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    emu.fdc_declare(emu.fdc_power_on_state())
    _read_sector()
    assert emu.fdc_state() != emu.fdc_power_on_state()
    image = harness.make_image()
    image[DRIVER_AT:DRIVER_AT + 2] = struct.pack(">H", RTS)
    emu.run(image, DRIVER_AT, max_insns=MAX_INSNS)
    assert emu.fdc_state() == emu.fdc_power_on_state()

def test_another_geometry_is_refused_by_name_and_leaves_the_model_disarmed():
    with pytest.raises(ValueError, match="80 tracks x 2 sides x 9 sectors"):
        emu.fdc_arm(emu.FdcDrive(bytearray(emu.FDC_IMAGE_BYTES - SECTOR_BYTES)))
    assert not emu.fdc_armed()


def test_a_model_refusal_sinks_the_run_by_name():
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(RuntimeError, match="bus error on the ST"):
        emu.run(_image(), BYTE_READ_AT, max_insns=MAX_INSNS)


def test_a_declaration_on_a_register_the_armed_model_owns_sinks_the_run():
    """R-D4-3: an io_seed on $ff8604 would be bypassed by the armed model — refused, never silently ignored."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(RuntimeError, match="the ARMED FDC model owns, the first at 0xff8604"):
        _read_sector(io_seed={DMA_DATA: 0})


def test_unarmed_the_register_is_todays_unmodeled_read():
    """R-D4-1, ARMED ONLY: disarmed, a $ff8604 read is the counted unmodeled 0 it always was, and the FDC ledger is
    empty."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    emu.fdc_disarm()
    _final, _writes, out = emu.run(_image(), BYTE_READ_AT, max_insns=MAX_INSNS)
    assert out["d1"] & 0xFF == 0
    assert out["io_unmodeled_reads"] == 1
    assert emu.fdc_events() == []


def test_a_differential_refuses_to_run_while_the_model_is_armed():
    """The candidate has no device wired (R-D4-1), so an armed differential would compare a floppy against none."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(AssertionError, match="FDC/DMA model is ARMED"):
        harness.differential(DRIVER_AT, {}, None)


def test_a_read_only_image_is_read_and_a_write_to_it_is_refused_by_name():
    """R4: a `bytes` image is lent READ-ONLY (P3 boots aes_boot's blank disk this way): the model reads a private
    copy; a write sector is refused, naming the read-only image — never written, never invented."""
    disk = bytes(_disk())
    emu.fdc_arm(emu.FdcDrive(disk))
    final, _writes, _out = _read_sector()
    assert final[BUFFER:BUFFER + SECTOR_BYTES] == disk[:SECTOR_BYTES]
    with pytest.raises(RuntimeError, match="lent read-only"):
        _read_sector(WRITE_SECTOR_1)


@pytest.mark.parametrize("bay", [emu.FdcDrive([0] * 4), emu.FdcDrive(bytearray(16)), "drive A"])
def test_a_refused_declaration_leaves_the_model_disarmed(bay):
    """R4: every input is checked before anything is armed, and a refusal leaves the model DISARMED — even one armed
    by the case before (no previous bay outlives it)."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(ValueError, match="drive A"):
        emu.fdc_arm(bay)
    assert not emu.fdc_armed()


def test_the_chip_cannot_be_read_or_declared_while_disarmed():
    """N1/N2: disarmed there is no chip to carry — `fdc_state` and `fdc_declare` refuse rather than hand back the
    last armed run's chip, or take a declaration arming would discard."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    _read_sector()
    left = emu.fdc_state()
    emu.fdc_disarm()
    with pytest.raises(RuntimeError, match="DISARMED"):
        emu.fdc_state()
    with pytest.raises(RuntimeError, match="DISARMED"):
        emu.fdc_declare(left)


def test_the_chip_a_refused_run_left_is_not_carried():
    """A refused run's chip describes nothing (a refusal may come after the DMA advanced): `fdc_state` refuses it."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(RuntimeError):
        emu.run(_image(), BYTE_READ_AT, max_insns=MAX_INSNS)
    with pytest.raises(RuntimeError, match="REFUSED"):
        emu.fdc_state()


def test_a_model_refusal_sinks_a_bench_run_by_name():
    """The README's second refusal surface: a bench segment (`run_bench`) is sunk as `emu.run` is."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    try:
        with pytest.raises(RuntimeError, match="bus error on the ST"):
            emu.run_bench(_image(), BYTE_READ_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL)
    finally:
        emu.bench_abort()


def _flood(reads):
    """The flood's run of `reads` track-register reads, armed."""
    return emu.run(_image(), FLOOD_AT, {"d0": reads}, max_insns=FLOOD_INSNS_PER_READ * reads + MAX_INSNS)


def test_a_ledger_overflow_sinks_the_run_by_name():
    """Never silent: one register read past the ledger's cap is dropped, counted, and the run is refused naming it."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(RuntimeError, match=rf"overflowed the ledger — 1 past FDC_LOG_MAX \({emu.FDC_LOG_MAX}\) were DROPPED"):
        _flood(emu.FDC_LOG_MAX + 1)


def test_a_run_of_exactly_the_cap_after_an_overflow_is_read_back_whole():
    """At the cap the ledger is complete, and `fdc_events()` hands back every entry, the last a `read`. The run follows
    an overflowed one, so the dropped count is reset per run too: a run that dropped nothing is not refused."""
    emu.fdc_arm(emu.FdcDrive(_disk()))
    with pytest.raises(RuntimeError, match="overflowed the ledger"):
        _flood(emu.FDC_LOG_MAX + 1)
    _flood(emu.FDC_LOG_MAX)
    events = emu.fdc_events()
    assert emu.fdc_causes() == [] and len(events) == emu.FDC_LOG_MAX and events[-1][0] == "read"
