"""Pin the FDC/DMA TRANSACTION MODEL kit-side (TRAP_MODEL.md, "Phase 17"; include/fdc.h, src/fdc.c).

Ruling D4 (2026-11-01): R-D4-1 "Instant 'done', shared kit C" — a zero-time WD1772 + DMA, ARMED ONLY; R-D4-2 the chip
saveable and loadable whole; R-D4-3 an ordered transaction ledger, GPIP bit 5 the model's while armed, declarations on
the model's registers refused. Kit-wide, so pinned here rather than in the first project to need it.

`fdc_model_probe.c` drives it at two layers (its header says why): THE CHIP directly — every command the model serves,
every status bit, the DMA's address / count / status, each refusal, the ledger — and THE WIRING through the oracle,
running a minimal 68000 floppy driver of the probe's own: arming, GPIP's composition, the DMA's stores joining the
write-set, a timeout reached by the driver's own count-down, the carried chip, the conflicts, and UNARMED = the path
every $ff8604 access took before the model existed.

THE TABLE IS THE ASSERTION (test_io_model.py's convention): one row per case, each scalar exact, each ledger exact, the
argument in the row's comment. `probe_build.compile_probe` rebuilds the oracle's sources and src/fdc.c on every run, so
a reverted rule reddens here rather than hiding behind an up-to-date-looking liboracle.so.
"""
import ast
import re

from pathlib import Path

import pytest

from probe_build import compile_probe, run_probe

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("fdc_model_probe.c")
FDC_H = KIT / "include" / "fdc.h"
EMU_PY = KIT / "oracle" / "emu.py"

# ---- fdc.h's enums, read from the header rather than restated ---------------------------------------------------------
def _enum(first):
    """The names of the fdc.h enum whose first member is `first`, in order — their values 1, 2, ... (or 0, 1, ...)."""
    text = FDC_H.read_text()
    body = text[text.index(first):]
    body = body[:body.index("};")]
    return re.findall(r"^\s*(FDC_[A-Z_]+)\s*(?:=\s*\d+)?,", body, re.M)


EVENTS = {name: value for value, name in enumerate(_enum("FDC_EV_COMMAND = 1"), start=1)}
REFUSALS = {name: value for value, name in enumerate(_enum("FDC_REFUSE_NONE = 0"))}
COMMAND, DONE, HANG, FORCED, DMA_IN, DMA_OUT, READ, POLL, HDC = (
    EVENTS[f"FDC_EV_{kind}"] for kind in ("COMMAND", "DONE", "HANG", "FORCED", "DMA_IN", "DMA_OUT", "READ", "POLL",
                                          "HDC"))
NOT_REFUSED = 0
ACCESS, BAD_COMMAND, PORT_A_UNKNOWN, OFF_RAM, DIRECTION, UNREPRESENTABLE, HDC_READ, COUNT_READ, NO_COUNT, \
    GEOMETRY, SHORT_COUNT, TRACK_SECTORS, READ_ONLY, GPIP_WIDE = (REFUSALS[f"FDC_REFUSE_{why}"] for why in (
        "ACCESS", "COMMAND", "PORT_A_UNKNOWN", "DMA_OFF_RAM", "DIRECTION", "UNREPRESENTABLE", "HDC_READ",
        "COUNT_READ", "WRITE_NO_COUNT", "GEOMETRY", "TRACK_SHORT_COUNT", "TRACK_SECTORS", "READ_ONLY",
        "GPIP_WIDE"))

# ---- the registers and the bits, as fdc.h names them -------------------------------------------------------------------
DMA_DATA, DMA_MODE, ADDR_HI, ADDR_MID, ADDR_LO = 0xFF8604, 0xFF8606, 0xFF8609, 0xFF860B, 0xFF860D
READ_REG_SHIFT = 24
ACCESS_WIDTH_SHIFT = 24
BLOCK_LO = 0xFF8600
GPIP, GPIP_WORD = 0xFFFA01, 0xFFFA00
TRACK_REG, SECTOR_REG, DATA_REG = 1, 2, 3
BUSY, TR00, RNF, SPUN_UP, WPRT, MOTOR = 0x01, 0x04, 0x10, 0x20, 0x40, 0x80
DMA_OK, DMA_COUNT_NZ = 0x01, 0x02
INTRQ_BIT = 0x20
SECTOR_BYTES, TRACK_BYTES = 512, 6250

# ---- the probe's own constants (fdc_model_probe.c), the other half of each claim ---------------------------------------
GPIP_DECLARED = 0xFF
GPIP_ASSERTED = GPIP_DECLARED & ~INTRQ_BIT
DRIVE_A, DRIVE_B, NO_DRIVE = 0, 1, 0xFF
SIDE_0, SIDE_1 = 0, 1
DMA_BUFFER, DMA_WRAP_BUFFER, TRACK_BUFFER, RAM_BYTES = 0x4000, 0xFE00, 0x6000, 0x10000
CMD_RESTORE, CMD_SEEK, CMD_SEEK_VERIFY, CMD_STEP = 0x00, 0x10, 0x14, 0x20
CMD_READ, CMD_READ_MULTI, CMD_WRITE, CMD_READ_ADDRESS = 0x80, 0x90, 0xA0, 0xC0
CMD_FORCE, CMD_FORCE_INDEX, CMD_READ_TRACK, CMD_WRITE_TRACK = 0xD0, 0xD4, 0xE0, 0xF0
FORMAT_TRACK, READ_TRACK, READ_SECTOR = 3, 5, 7
SEEK_CLAMP_DATA, HEAD_STOP = 200, 85
FORMAT_COUNT = 31
SECTORS_STARTED = -(-TRACK_BYTES // SECTOR_BYTES)   # what one Write Track takes off the count: 13
TIMEOUT_POLLS = 99                     # TIMEOUT_COUNT 100: the 100th `subq` reaches 0 before its poll
PSG_PORT_A = 14
GPIP_SLOT_BIT = 1                      # os.h's OS_HW_SLOT_MFP_GPIP (0), as a mask
FDC_LOG_MAX = 4096
REGISTERS_TRACK, REGISTERS_SECTOR, REGISTERS_DATA = 0x2A, 0x07, 0x99
DRIVER_HW_WRITES = 11                  # 3 address bytes, 3 mode words, the count, 2 mode words, the sector, the command
ACSI_FIRST_BYTE, ACSI_MODE = 0x08, 0x88
SHORT_TRACK_COUNT = 12                 # 12 x 512 = 6,144: less than a revolution
EIGHT_SECTORS_FOUND = 0x1FE            # bits 1..8: the found-mask of a track missing sector 9
BLOCK_ADDR_MID_WORD, BLOCK_ADDR_HI_WORD = 0xFF860C, 0xFF8608
OFF_RAM_TRACK = (RAM_BYTES - TRACK_BYTES // 2) & ~1    # the probe asks an odd address; bit 0 is not wired
OFF_RAM_SECTOR = RAM_BYTES - SECTOR_BYTES // 2
GPIP_SLOT_STALE = 1                    # Phase 7's stale mask, slot 0


def _access(address, width):
    """An access refusal's detail: the width in the top byte, the address below."""
    return width << ACCESS_WIDTH_SHIFT | address


def _tsn(track, side, sector):
    return track << 16 | side << 8 | sector


def _sel(drive, side=SIDE_0):
    return drive << 8 | side


def _model(**claims):
    """One chip-layer case's whole scalar claim, the quiet state as defaults (test_io_model.py's `_scalars`)."""
    base = dict(intrq=0, busy=0, track=0, sector=1, head_a=0, count=0, addr=0, stored=0, refused=NOT_REFUSED,
                refused_at=0, dropped=0)
    base.update(claims)
    base["gpip"] = GPIP_ASSERTED if base["intrq"] else GPIP_DECLARED
    return base


def _with_status(scalars, status, intrq_after_read=0):
    return {**scalars, "status": status, "intrq_after_read": intrq_after_read}


def _oracle(**claims):
    base = dict(d0=0, d1=0, refused=NOT_REFUSED, refused_at=0, conflicts=0, conflict_first=0, hw_unseeded=0,
                hw_stale=0, hw_nlog=0, io_unmodeled=0, io_unmodeled_first=0, stored_in_buffer=0, hw_writes=0)
    base.update(claims)
    return base


TYPE1_DONE = MOTOR | SPUN_UP
SEEK_ERROR = TYPE1_DONE | RNF
READ_LEDGER = [(COMMAND, CMD_READ, _sel(DRIVE_A)), (DMA_IN, DMA_BUFFER, SECTOR_BYTES), (DONE, MOTOR, 0)]

EXPECTED = {
    # MR: a 1 in the sector register, the DMA's error clear; the status a read sees is TYPE I and LIVE — drive A
    # selected, its head at 0: TR00, and nothing else (the motor has never turned).
    "model_power_on": dict(scalars={**_with_status(_model(), TR00), "dma_status": DMA_OK}, ledger=[]),
    # Restore with a drive: the head to 0, TR 0, INTRQ (GPIP bit 5 LOW) — and the read clears INTRQ.
    "model_restore": dict(scalars=_with_status(_model(intrq=1), TYPE1_DONE | TR00),
                          ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0)]),
    # NO DRIVE, the motor already on (R-D4-1, Hatari, datasheet): 255 steps with no TR00 — the SEEK ERROR, TR 0, and
    # TR00 off in the live status, the line having no drive behind it.
    "model_restore_absent_motor_on": dict(scalars=_with_status(_model(intrq=1), SEEK_ERROR),
                                          ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_B)), (DONE, SEEK_ERROR, 0)]),
    # ...the motor OFF: the spin-up counts index pulses no drive sends — HANG, busy, no INTRQ; a TR write and a
    # second command are ignored while busy (neither reaches TR nor the ledger).
    "model_restore_absent_motor_off": dict(scalars=_with_status(_model(busy=1), MOTOR | BUSY),
                                           ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_B)), (HANG, CMD_RESTORE, 0)]),
    # ...ended the only way it can be: a force-interrupt ($D0: no INTRQ), busy cleared, the motor line kept.
    "model_restore_absent_forced": dict(
        scalars=_with_status(_model(), MOTOR),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_B)), (HANG, CMD_RESTORE, 0),
                (READ, DMA_DATA, MOTOR | BUSY), (FORCED, CMD_FORCE, 0)]),
    # Neither select line low: no drive at all — the same seek error, the ledger naming no drive.
    "model_no_drive_selected": dict(scalars=_with_status(_model(intrq=1), SEEK_ERROR),
                                    ledger=[(COMMAND, CMD_RESTORE, _sel(NO_DRIVE)), (DONE, SEEK_ERROR, 0)]),
    # A drive with NO DISK: no index pulse, so the spin-up hangs (R-D4-1)...
    "model_empty_spin_up": dict(scalars=_model(busy=1),
                                ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (HANG, CMD_RESTORE, 0)]),
    # ...once the motor is on a restore needs none (it steps to TR00), and the empty bay reads WRITE-PROTECTED...
    "model_empty_restore": dict(
        scalars=_with_status(_model(intrq=1), TYPE1_DONE | WPRT | TR00),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (HANG, CMD_RESTORE, 0), (FORCED, CMD_FORCE, 0),
                (COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0)]),
    # ...but a VERIFY searches for an ID field, which counts revolutions: it hangs.
    "model_empty_verify": dict(
        scalars=_model(busy=1),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (HANG, CMD_RESTORE, 0), (FORCED, CMD_FORCE, 0),
                (COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0),
                (READ, DMA_DATA, TYPE1_DONE | WPRT | TR00), (COMMAND, CMD_SEEK_VERIFY, _sel(DRIVE_A)),
                (HANG, CMD_SEEK_VERIFY, 0)]),
    # Seek: the head moves by DR - TR, TR := DR; off track 0, so no TR00.
    "model_seek": dict(scalars=_with_status(_model(intrq=1, track=READ_TRACK, head_a=READ_TRACK), TYPE1_DONE),
                       ledger=[(COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0)]),
    # ...with VERIFY on the track it reached: the ID field's track (the physical one) matches TR.
    "model_seek_verify": dict(
        scalars=_with_status(_model(intrq=1, track=READ_TRACK, head_a=READ_TRACK), TYPE1_DONE),
        ledger=[(COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0), (READ, DMA_DATA, TYPE1_DONE),
                (COMMAND, CMD_SEEK_VERIFY, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0)]),
    # ...and with TR disagreeing with the head: no ID field holds TR — the seek error.
    "model_seek_verify_mismatch": dict(
        scalars=_with_status(_model(intrq=1, track=READ_TRACK - 2, head_a=READ_TRACK), SEEK_ERROR),
        ledger=[(COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0), (READ, DMA_DATA, TYPE1_DONE),
                (COMMAND, CMD_SEEK_VERIFY, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0), (READ, DMA_DATA, TYPE1_DONE),
                (COMMAND, CMD_SEEK_VERIFY, _sel(DRIVE_A)), (DONE, SEEK_ERROR, 0)]),
    # A seek past the medium: the head stops at its mechanical stop, TR takes the value, the verify finds nothing.
    "model_seek_clamped": dict(
        scalars=_with_status(_model(intrq=1, track=SEEK_CLAMP_DATA, head_a=HEAD_STOP), SEEK_ERROR),
        ledger=[(COMMAND, CMD_SEEK_VERIFY, _sel(DRIVE_A)), (DONE, SEEK_ERROR, 0)]),
    # A sector READ through the DMA, side 1: the disk's bytes at the address, every one a store; the address +512, the
    # count -1. The DMA status: OK, the count not zero, the residue of the last FDC byte ($80, the command) above.
    "model_read_sector": dict(
        scalars={**_with_status(_model(intrq=1, track=READ_TRACK, sector=READ_SECTOR, head_a=READ_TRACK, count=1,
                                       addr=DMA_BUFFER + SECTOR_BYTES, stored=SECTOR_BYTES), MOTOR),
                 "same_bytes": 1, "dma_status": CMD_READ | DMA_COUNT_NZ | DMA_OK,
                 "dma_status_after_status": MOTOR | DMA_COUNT_NZ | DMA_OK},
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A, SIDE_1)), (DMA_IN, DMA_BUFFER, SECTOR_BYTES), (DONE, MOTOR, 0)]),
    # Sector 10 on a 9-sector track: RECORD NOT FOUND, no transfer, the count kept.
    "model_read_rnf": dict(scalars=_with_status(_model(intrq=1, sector=10, count=1, addr=DMA_BUFFER), MOTOR | RNF),
                           ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A)), (DONE, MOTOR | RNF, 0)]),
    # A read with a zero count: the DMA's error bit (Hatari, STF) — and the direction toggle clears it.
    "model_read_zero_count": dict(
        scalars={**_model(intrq=1, addr=DMA_BUFFER), "dma_status": CMD_READ,
                 "dma_status_after_toggle": CMD_READ | DMA_OK},
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A)), (DONE, MOTOR, 0)]),
    # The address is one 24-bit counter: a sector at $fe00 carries it into $010000, read back byte by byte.
    "model_read_address_wraps": dict(
        scalars={**_model(intrq=1, addr=DMA_WRAP_BUFFER + SECTOR_BYTES, stored=SECTOR_BYTES), "hi": 1, "mid": 0,
                 "lo": 0},
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A)), (DMA_IN, DMA_WRAP_BUFFER, SECTOR_BYTES), (DONE, MOTOR, 0),
                (READ, ADDR_HI, 1), (READ, ADDR_MID, 0), (READ, ADDR_LO, 0)]),
    # Bit 0 of the low address byte is not wired: an odd address is the even one below it.
    "model_read_odd_address": dict(
        scalars=_model(intrq=1, addr=DMA_BUFFER + SECTOR_BYTES, stored=SECTOR_BYTES),
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A)), (DMA_IN, DMA_BUFFER, SECTOR_BYTES), (DONE, MOTOR, 0)]),
    # REFUSED, and never completed: a read against the DMA's direction, and one that would leave the RAM.
    "model_read_wrong_direction": dict(
        scalars=_model(count=1, addr=DMA_BUFFER, refused=DIRECTION, refused_at=CMD_READ),
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A))]),
    "model_read_off_ram": dict(
        scalars=_model(count=1, addr=RAM_BYTES - SECTOR_BYTES // 2, refused=OFF_RAM,
                       refused_at=RAM_BYTES - SECTOR_BYTES // 2),
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A))]),
    # A sector WRITE: the RAM's bytes onto the image at (0, 0, 4); the DMA's sends are not stores.
    "model_write_sector": dict(
        scalars={**_with_status(_model(intrq=1, sector=4, addr=DMA_BUFFER + SECTOR_BYTES), MOTOR), "written": 1},
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A)), (DMA_OUT, DMA_BUFFER, SECTOR_BYTES), (DONE, MOTOR, 0)]),
    # ...write-protected: WPRT before any transfer, the disk untouched.
    "model_write_protected": dict(
        scalars={**_with_status(_model(intrq=1, sector=4, count=1, addr=DMA_BUFFER), MOTOR | WPRT),
                 "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A)), (DONE, MOTOR | WPRT, 0)]),
    # REFUSED: a write with no count (no data to send), and one against the direction.
    "model_write_no_count": dict(
        scalars={**_model(sector=4, addr=DMA_BUFFER, refused=NO_COUNT, refused_at=CMD_WRITE), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A))]),
    "model_write_wrong_direction": dict(
        scalars=_model(sector=4, count=1, addr=DMA_BUFFER, refused=DIRECTION, refused_at=CMD_WRITE),
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A))]),
    # WRITE TRACK in the ROM drivers' layout: one revolution (6,250 bytes) consumed, the count down by the sectors
    # started (13 of 31), the nine sectors decoded back onto the image; side 1 of the track untouched.
    "model_write_track": dict(
        scalars={**_with_status(_model(intrq=1, track=FORMAT_TRACK, head_a=FORMAT_TRACK,
                                       count=FORMAT_COUNT - SECTORS_STARTED,
                                       addr=TRACK_BUFFER + TRACK_BYTES), MOTOR),
                 "formatted": 1, "side_1_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A)), (DMA_OUT, TRACK_BUFFER, TRACK_BYTES), (DONE, MOTOR, 0)]),
    # REFUSED BEFORE THE DMA MOVES (so RAM, image, address and count stay put): an ID naming another track (detail:
    # track << 16 | side << 8 | sector), and data holding $F5 (which the chip writes as a mark, not data).
    "model_write_track_other_track": dict(
        scalars={**_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=FORMAT_COUNT, addr=TRACK_BUFFER,
                          refused=UNREPRESENTABLE, refused_at=_tsn(FORMAT_TRACK + 4, SIDE_0, 1)), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0), (COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    "model_write_track_special_data": dict(
        scalars={**_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=FORMAT_COUNT, addr=TRACK_BUFFER,
                          refused=UNREPRESENTABLE, refused_at=_tsn(FORMAT_TRACK, SIDE_0, 1)), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0), (COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    "model_write_track_protected": dict(
        scalars={**_model(intrq=1, count=FORMAT_COUNT, addr=TRACK_BUFFER), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A)), (DONE, MOTOR | WPRT, 0)]),
    # The commands no modelled driver issues: REFUSED, by name, never invented.
    **{f"model_{name}": dict(scalars=_model(refused=BAD_COMMAND, refused_at=command),
                             ledger=[(COMMAND, command, _sel(DRIVE_A))])
       for name, command in (("step", CMD_STEP), ("read_multi", CMD_READ_MULTI), ("read_address", CMD_READ_ADDRESS),
                             ("read_track", CMD_READ_TRACK))},
    # A byte (or long) access to the two word registers: the ST's bus error, refused.
    "model_byte_read": dict(scalars=_model(refused=ACCESS, refused_at=_access(DMA_DATA, 1)), ledger=[]),
    "model_byte_write": dict(scalars=_model(refused=ACCESS, refused_at=_access(DMA_MODE, 1)), ledger=[]),
    "model_long_read": dict(scalars=_model(refused=ACCESS, refused_at=_access(DMA_DATA, 4)), ledger=[]),
    # The sector count is write-only; an HDC register read needs an ACSI device nobody modelled.
    "model_count_read": dict(scalars=_model(refused=COUNT_READ, refused_at=DMA_DATA), ledger=[(READ, DMA_DATA, 0)]),
    "model_hdc_read": dict(scalars=_model(refused=HDC_READ, refused_at=DMA_DATA), ledger=[(READ, DMA_DATA, 0)]),
    # A command with port A never known: no drive or side can be selected — refused, naming the PSG register.
    "model_port_a_unknown": dict(scalars=_model(refused=PORT_A_UNKNOWN, refused_at=PSG_PORT_A), ledger=[]),
    # move.l to $ff8604: the data word first (here an HDC byte, which no device answers), then the mode word.
    "model_hdc_long_write": dict(scalars={**_model(), "mode": 0x8A},
                                 ledger=[(HDC, ACSI_FIRST_BYTE, ACSI_MODE)]),
    "model_fdc_long_write": dict(scalars={"data": 0x12, "mode": 0x80}, ledger=[]),
    # TR, SR and DR read back; each READ entry names its register in the top byte; the DMA status carries the last
    # FDC byte's residue in bits 3-15.
    "model_registers": dict(
        scalars={**_model(track=REGISTERS_TRACK, sector=REGISTERS_SECTOR), "data": REGISTERS_DATA,
                 "dma_status": (REGISTERS_DATA & 0xF8) | DMA_OK},
        ledger=[(READ, TRACK_REG << READ_REG_SHIFT | DMA_DATA, REGISTERS_TRACK),
                (READ, SECTOR_REG << READ_REG_SHIFT | DMA_DATA, REGISTERS_SECTOR),
                (READ, DATA_REG << READ_REG_SHIFT | DMA_DATA, REGISTERS_DATA),
                (READ, DMA_MODE, (REGISTERS_DATA & 0xF8) | DMA_OK)]),
    # A force-interrupt WITH a condition asserts INTRQ at once.
    "model_force_with_condition": dict(scalars=_model(intrq=1), ledger=[(FORCED, CMD_FORCE_INDEX, 0)]),
    # POLLS COUNTED, NOT LISTED (R-D4-3): three identical polls are one entry of three; a change of answer is a new
    # entry; the declared bits come through untouched.
    "model_polls": dict(scalars=_model(intrq=1, track=1, head_a=1),
                        ledger=[(POLL, GPIP_DECLARED, 3), (COMMAND, CMD_SEEK, _sel(DRIVE_A)), (DONE, TYPE1_DONE, 0),
                                (POLL, GPIP_ASSERTED, 1), (POLL, 0, 1)]),
    # The ledger's cap: one past it is DROPPED and counted, never silently.
    "model_ledger_overflow": dict(scalars={"nlog": FDC_LOG_MAX, "dropped": 1}, ledger=None),
    # R-D4-1: 80x2x9 alone — a byte short, a byte long, no image, a third drive: refused; an empty bay and the disk
    # itself accepted.
    "model_geometry": dict(scalars={"short": GEOMETRY, "long": GEOMETRY, "no_image": GEOMETRY,
                                    "third_drive": GEOMETRY, "empty_bay": NOT_REFUSED, "the_disk": NOT_REFUSED},
                           ledger=[]),
    # UNARMED = TODAY (R-D4-1): a $ff8604 read is the unmodeled 0, counted; a write lands in the Phase-10 ledger; the
    # FDC ledger is empty — before any arming, and after an arm and a disarm.
    **{f"oracle_{when}_read": dict(scalars=_oracle(io_unmodeled=1, io_unmodeled_first=DMA_DATA), ledger=[])
       for when in ("unarmed", "disarmed")},
    **{f"oracle_{when}_write": dict(scalars={**_oracle(hw_writes=1), "first_hw_write": DMA_MODE}, ledger=[])
       for when in ("unarmed", "disarmed")},
    # ARMED, the probe's driver reads a sector: the bytes land, all 512 join the write-set, the one poll is served the
    # declared byte with bit 5 low, Phase 7's own ledger sees no poll, and every register store is in Phase 10's.
    "oracle_read": dict(scalars={**_oracle(d0=CMD_READ, d1=MOTOR, stored_in_buffer=SECTOR_BYTES,
                                           hw_writes=DRIVER_HW_WRITES), "same_bytes": 1},
                        ledger=[*READ_LEDGER, (POLL, GPIP_ASSERTED, 1), (READ, DMA_DATA, MOTOR)]),
    # A drive missing, the motor off: the driver's own count-down runs out (99 polls, ONE entry), its force-interrupt
    # ends the hang, the status reads motor-on and nothing else.
    "oracle_absent_timeout": dict(
        scalars=_oracle(d0=0xFFFFFFFF, d1=MOTOR, hw_writes=DRIVER_HW_WRITES + 1),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (HANG, CMD_RESTORE, 0), (POLL, GPIP_DECLARED, TIMEOUT_POLLS),
                (FORCED, CMD_FORCE, 0), (READ, DMA_DATA, MOTOR)]),
    # R-D4-2: the chip that run LEFT (the motor on), declared for the next: the restore now ends in the seek error at
    # once — and the declaration is re-installed per run, so the second run says the same.
    **{f"oracle_absent_carried_{when}": dict(
        scalars=_oracle(d1=SEEK_ERROR, hw_writes=DRIVER_HW_WRITES),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (DONE, SEEK_ERROR, 0), (POLL, GPIP_ASSERTED, 1),
                (READ, DMA_DATA, SEEK_ERROR)]) for when in ("motor_on", "again")},
    # A drive with no disk: the same timeout road; its status after the force is type I, live: TR00 and WPRT.
    "oracle_empty_timeout": dict(
        scalars=_oracle(d0=0xFFFFFFFF, d1=MOTOR | WPRT | TR00, hw_writes=DRIVER_HW_WRITES + 1),
        ledger=[(COMMAND, CMD_RESTORE, _sel(DRIVE_A)), (HANG, CMD_RESTORE, 0), (POLL, GPIP_DECLARED, TIMEOUT_POLLS),
                (FORCED, CMD_FORCE, 0), (READ, DMA_DATA, MOTOR | WPRT | TR00)]),
    # GPIP's other bits UNDECLARED: Phase 7's refusal mask names the slot, the model still owns bit 5.
    "oracle_gpip_undeclared": dict(
        scalars=_oracle(d0=CMD_READ, d1=MOTOR, hw_unseeded=GPIP_SLOT_BIT, stored_in_buffer=SECTOR_BYTES,
                        hw_writes=DRIVER_HW_WRITES),
        ledger=[*READ_LEDGER, (POLL, 0, 1), (READ, DMA_DATA, MOTOR)]),
    # A declaration on a register the armed model owns: a CONFLICT, counted with its address — never bypassed silently.
    "oracle_conflict": dict(
        scalars=_oracle(d0=CMD_READ, d1=MOTOR, conflicts=1, conflict_first=DMA_DATA, stored_in_buffer=SECTOR_BYTES,
                        hw_writes=DRIVER_HW_WRITES),
        ledger=[*READ_LEDGER, (POLL, GPIP_ASSERTED, 1), (READ, DMA_DATA, MOTOR)]),
    # `move.b $ff8604,d1` armed: the bus error, refused.
    "oracle_byte_access": dict(scalars=_oracle(refused=ACCESS, refused_at=_access(DMA_DATA, 1)), ledger=[]),

    # ---- the fix pass (review RP2) -----------------------------------------------------------------------------------
    # EVERY Write Track a .ST cannot hold is REFUSED BY NAME, before the DMA moves — never a silent $80 (R1): a count
    # short of a revolution (the chip would write on with lost data, which the model does not invent)...
    "model_write_track_short_count": dict(
        scalars={**_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=SHORT_TRACK_COUNT, addr=TRACK_BUFFER,
                          refused=SHORT_COUNT, refused_at=SHORT_TRACK_COUNT), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    # ...fewer than nine sectors (the detail: the mask of those found)...
    "model_write_track_eight_sectors": dict(
        scalars={**_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=FORMAT_COUNT, addr=TRACK_BUFFER,
                          refused=TRACK_SECTORS, refused_at=EIGHT_SECTORS_FOUND), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    # ...an ID repeated (a tenth naming sector 1 again), an ID for the other side, an ID with no data field of its own
    # before the next ID (the fifth: sector 5)...
    **{f"model_write_track_{name}": dict(
        scalars={**_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=FORMAT_COUNT, addr=TRACK_BUFFER,
                          refused=UNREPRESENTABLE, refused_at=detail), "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))])
       for name, detail in (("duplicate_id", _tsn(FORMAT_TRACK, SIDE_0, 1)), ("other_side", _tsn(FORMAT_TRACK, SIDE_1, 1)),
                            ("id_without_data", _tsn(FORMAT_TRACK, SIDE_0, 5)))},
    # ...and a revolution that would leave the RAM.
    "model_write_track_off_ram": dict(
        scalars=_model(track=FORMAT_TRACK, head_a=FORMAT_TRACK, count=FORMAT_COUNT, addr=OFF_RAM_TRACK,
                       refused=OFF_RAM, refused_at=OFF_RAM_TRACK),
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    # A sector write that would read past the RAM: refused, the disk untouched.
    "model_write_off_ram": dict(
        scalars={**_model(sector=4, count=1, addr=OFF_RAM_SECTOR, refused=OFF_RAM, refused_at=OFF_RAM_SECTOR),
                 "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A))]),
    # An image lent READ-ONLY (R4): reads are served; a write sector or a write track is refused by name.
    "model_read_only_read": dict(
        scalars={**_model(intrq=1, addr=DMA_BUFFER + SECTOR_BYTES, stored=SECTOR_BYTES), "same_bytes": 1},
        ledger=READ_LEDGER),
    "model_read_only_write": dict(
        scalars={**_model(sector=4, count=1, addr=DMA_BUFFER, refused=READ_ONLY, refused_at=CMD_WRITE),
                 "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE, _sel(DRIVE_A))]),
    "model_read_only_track": dict(
        scalars={**_model(count=FORMAT_COUNT, addr=TRACK_BUFFER, refused=READ_ONLY, refused_at=CMD_WRITE_TRACK),
                 "disk_untouched": 1},
        ledger=[(COMMAND, CMD_WRITE_TRACK, _sel(DRIVE_A))]),
    # A force after a TYPE II command: the status reverts to type I — the live TR00 of the selected head.
    "model_force_after_read": dict(
        scalars=_with_status(_model(addr=DMA_BUFFER + SECTOR_BYTES, stored=SECTOR_BYTES), MOTOR | TR00),
        ledger=[*READ_LEDGER, (FORCED, CMD_FORCE, 0)]),
    # The rest of the DMA block (R2): no register the model serves there — refused by name, never passed through. A
    # word store at $ff860c is, on a 68000, a store to the address's LOW byte; the model does not claim that decode.
    **{name: dict(scalars=_model(refused=ACCESS, refused_at=_access(address, width)), ledger=[])
       for name, address, width in (("model_word_write_address_byte", BLOCK_ADDR_MID_WORD, 2),
                                    ("model_byte_write_data_low", DMA_DATA + 1, 1),
                                    ("model_word_read_address_hi_word", BLOCK_ADDR_HI_WORD, 2),
                                    ("model_byte_read_block_start", BLOCK_LO, 1),
                                    ("model_long_write_mode", DMA_MODE, 4))},
    # Ownership: an access touching any byte of [$ff8600, $ff8610) is the model's (straddling the start included);
    # a WIDE access over GPIP is the refusal's, a byte one the model's composition.
    "model_block_ownership": dict(scalars={"below": 0, "straddle": 1, "last": 1, "above": 0, "gpip_word": 1,
                                           "gpip_byte": 0}, ledger=[]),
    # THROUGH THE ORACLE (R3): the move.l hook (the ACSI idiom) reaches the model — the HDC byte, then the mode...
    "oracle_long_write": dict(scalars=_oracle(hw_writes=2), ledger=[(HDC, ACSI_FIRST_BYTE, ACSI_MODE)]),
    # ...Phase 7's STALE rule holds for the declared half of GPIP: stored, then read back...
    "oracle_gpip_stale": dict(scalars=_oracle(hw_stale=GPIP_SLOT_STALE, hw_writes=1), ledger=[(POLL, GPIP_DECLARED, 1)]),
    # ...a SEQUENCE on GPIP while armed is a conflict, named...
    "oracle_gpip_sequence_conflict": dict(
        scalars=_oracle(conflicts=1, conflict_first=GPIP, hw_stale=GPIP_SLOT_STALE, hw_writes=1),
        ledger=[(POLL, GPIP_DECLARED, 1)]),
    # ...a WORD read over GPIP is refused (R2) — never served a 0 that reads as INTRQ asserted...
    "oracle_gpip_word_read": dict(scalars=_oracle(refused=GPIP_WIDE, refused_at=_access(GPIP_WORD, 2)), ledger=[]),
    # ...a word into the address bytes is refused through the oracle too (and still ledgered by Phase 10)...
    "oracle_word_into_address_bytes": dict(
        scalars=_oracle(refused=ACCESS, refused_at=_access(BLOCK_ADDR_MID_WORD, 2), hw_writes=1), ledger=[]),
    # ...and a disarm FORGETS the bays: re-armed with none declared, drive A is absent — the read hangs and the
    # driver's own count-down times out, where a remembered bay would have read the image lent before.
    "oracle_rearm_forgets_bays": dict(
        scalars=_oracle(d0=0xFFFFFFFF, d1=MOTOR, hw_writes=DRIVER_HW_WRITES + 1),
        ledger=[(COMMAND, CMD_READ, _sel(DRIVE_A)), (HANG, CMD_READ, 0), (POLL, GPIP_DECLARED, TIMEOUT_POLLS),
                (FORCED, CMD_FORCE, 0), (READ, DMA_DATA, MOTOR)]),
}


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Build and run the probe once; return {case: {"scalars", "ledger", "file"}}."""
    return run_probe(compile_probe(PROBE_SRC, tmp_path_factory.mktemp("fdc_model")))


def test_the_probe_reports_every_case(probe):
    """Guard the fixture: a probe that stopped printing would make every row below pass vacuously."""
    assert set(probe) == set(EXPECTED)


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_scalars(probe, case):
    """Every scalar exact. A case with a ledger row prints its length as `nlog`, which `test_ledger` holds through
    the ledger itself; only the overflow case, whose ledger is too long to list, claims `nlog` as a scalar."""
    reported = dict(probe[case]["scalars"])
    if EXPECTED[case]["ledger"] is not None:
        assert reported.pop("nlog", 0) == len(EXPECTED[case]["ledger"])
    assert reported == EXPECTED[case]["scalars"]


@pytest.mark.parametrize("case", sorted(case for case, row in EXPECTED.items() if row["ledger"] is not None))
def test_ledger(probe, case):
    assert probe[case]["ledger"] == EXPECTED[case]["ledger"]


def test_the_probe_driver_is_its_own_not_a_roms():
    """The kit is project-agnostic: its probe's driver is planted from the probe's own table — no ROM, no
    project path, no image a project ships."""
    source = PROBE_SRC.read_text()
    assert "static const uint16_t DRIVER[]" in source
    assert "TOS" not in source and "projects/" not in source


def _emu_dict(name):
    tree = ast.parse(EMU_PY.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"emu.py has no {name}")


def test_emu_names_fdc_h_s_ledger_kinds_and_refusals():
    """emu.py's FDC_EVENTS / FDC_REFUSALS mirror enums the .so does not export: held to fdc.h's text, so a reordered
    or grown enum reddens here instead of mislabelling a ledger entry or a refusal."""
    events = _emu_dict("FDC_EVENTS")
    assert {value: name.lower() for name, value in
            ((name[len("FDC_EV_"):], value) for name, value in EVENTS.items())} == events
    refusals = _emu_dict("FDC_REFUSALS")
    assert set(refusals) == {value for name, value in REFUSALS.items() if value}
    geometry = re.search(r"^FDC_REFUSE_GEOMETRY = (\d+)", EMU_PY.read_text(), re.M)
    assert geometry and int(geometry.group(1)) == GEOMETRY
