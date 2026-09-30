"""`src/vdi/entry.S` — the Line-A exception, $a000 and the `trap #2` entry as the ROM spells them ($fc9f0c..$fc9ffb).

Two claims hold it. Its BYTES are the ROM's, every one but the references the `.S` measures to where it is linked:
$a000's two `lea`s of its own tables, and the opcode-table longwords of the primitives that ship as `.S` entries,
each relocated to the exact address that entry has in the blob. And it BEHAVES as the ROM, image and whole register
file, through Tier 3's transcription relation: the handler through a staged EXCEPTION CALLER that builds the frame
a real $Axxx does (`vdi_entry.exception_caller`), $a000 and the entry by `jsr`.

WHICH REGISTERS A CALLER CLEARS, measured: $a000 answers ITS OWN font and opcode tables in A1/A2 — the blob's, where
the ROM answers its own — so every row reaching it clears those two; a served primitive leaves A1 holding the
address the table gave it (the blob's entry, or the ROM's), so the pixel rows clear A1.
"""
import pytest

from harness import addrs, emu, make_image

import test_vdi_blit_engine as blit_engine
import test_vdi_raster_pixel as pixel
import vdi
import vdi_blit
import vdi_entry as entry
from opcodes import LINE_A

VDI_ROM_ENTRY_BYTES = 0x5E     # the entry's 94 bytes, through its `rts` (held below)
REGION = vdi.pinned_region(addrs.LINEA_ROM_DISPATCH, addrs.VDI_ROM_ENTRY + VDI_ROM_ENTRY_BYTES, "LINEA_ROM_DISPATCH",
                           ("LINEA_ROM_INIT", "VDI_ROM_ENTRY"))
_OWN = "an absolute address of the region's own table, which names entry.S's"
_SHIPPED = "a primitive that ships as a `.S` entry, which the table names"
INIT_LEAS = (addrs.LINEA_ROM_INIT + 0x0A, addrs.LINEA_ROM_INIT + 0x10)   # `lea <table>.l,a1` / `lea <table>.l,a2`
# The longwords that name a shipped entry: every primitive in a byte-pinned region. $a009 (v_show_c) and $a00f (the
# contour fill) ship as C and stay the ROM's own.
SHIPS_AS_C = (addrs.VDI_ROM_V_SHOW_C, addrs.LINEA_ROM_CONTOUR_FILL)
TABLE_SLOTS = range(vdi.LINEA_OPCODE_TABLE, vdi.LINEA_OPCODE_TABLE + (vdi.LINEA_OPCODE_LAST + 1) * vdi.LONG_BYTES,
                    vdi.LONG_BYTES)


def relocations():
    relocated = {at: vdi.Relocated(vdi.ABSOLUTE, REGION.anchor, f"$a000's `lea` of its table: {_OWN}") for at in INIT_LEAS}
    for slot in TABLE_SLOTS:
        target = vdi.rom_word(slot) << 16 | vdi.rom_word(slot + vdi.WORD_BYTES)
        if target not in SHIPS_AS_C:
            relocated[slot] = vdi.Relocated(vdi.ABSOLUTE, vdi.anchor_of(target), f"${target:x}: {_SHIPPED}")
    return relocated


def test_the_region_ends_where_the_entry_s_rts_does():
    assert vdi.rom_word(REGION.hi - vdi.WORD_BYTES) == int.from_bytes(entry.RTS, "big")
    assert vdi.rom_word(REGION.hi) != int.from_bytes(entry.RTS, "big")


def test_the_region_is_the_rom_s_words():
    vdi.assert_transcribed(REGION.anchor, REGION.lo, REGION.hi, entries=REGION.entries, relocated=relocations())


def test_the_primitives_that_ship_as_c_are_the_ones_no_region_holds():
    for slot in TABLE_SLOTS:
        target = vdi.rom_word(slot) << 16 | vdi.rom_word(slot + vdi.WORD_BYTES)
        held = any(region.lo <= target < region.hi for region in vdi.every_pinned_region())
        assert held == (target not in SHIPS_AS_C), f"${target:x}"


# ---- the behaviour ------------------------------------------------------------------------------------------------
INIT, PUT, GET, BITBLT = 0, 1, 2, 7
POINT, COLOUR = (37, 100), 0b1010
PIXEL_POKES = {PUT: pixel.point_pokes(*POINT, colour=COLOUR),
               GET: vdi.pixel_pokes({POINT: COLOUR}, onto=pixel.point_pokes(*POINT))}
# $a007 is the served primitive that leaves A6 changed (`adda.w #76,a6`, $fd05fc) — the register the handler's
# `movem` does not keep, so the row the handler's contract in `vdi/transcribed.h` is measured over.
BITBLT_POKES = vdi_blit.canvas(blit_engine.BITBLT_ROWS["one pixel"])
BITBLT_REGS = {"a6": vdi_blit.BLOCK_AT}
# (number, pokes, registers, what the caller clears), one per shape the handler has.
HANDLER_CASES = (("$a000", INIT, {}, {}, ("a1", "a2")),
                 ("$a001", PUT, PIXEL_POKES[PUT], {}, ("a1",)),
                 ("$a002", GET, PIXEL_POKES[GET], {}, ("a1",)),
                 ("$a007, one pixel", BITBLT, BITBLT_POKES, BITBLT_REGS, ("a1",)),
                 ("$a010, unserved", 0x10, {}, {}, ()),
                 ("$afff, unserved", vdi.LINEA_OPCODE_MASK, {}, {}, ()))


@pytest.mark.parametrize("label,number,pokes,regs,cleared", HANDLER_CASES, ids=[case[0] for case in HANDLER_CASES])
def test_the_handler_behaves_as_the_rom(label, number, pokes, regs, cleared):
    vdi.run_transcription("LINEA_ROM_DISPATCH", pokes, regs, caller=entry.exception_caller(LINE_A | number, cleared))


def test_a000_by_jsr_behaves_as_the_rom():
    vdi.run_transcription("LINEA_ROM_INIT", {}, caller=POOL.caller_for("LINEA_ROM_INIT"))


# The entry's shapes: no points, one, the cap, a count past it only unsigned, and one whose doubled word wraps to 0.
ENTRY_COUNTS = (0, 1, entry.PAST_THE_CAP, 0x4000, 0x8000)


@pytest.mark.parametrize("points", ENTRY_COUNTS)
def test_the_entry_behaves_as_the_rom(points):
    vdi.run_transcription("VDI_ROM_ENTRY", entry_pokes(points), ENTRY_REGS)


def test_the_entry_keeps_every_register_but_d0_s_low_word():
    """What makes the relation above more than both sides agreeing: the ROM hands the caller D1-A6 back, and D0's high
    half as the NOP's path left it — the file the case entered with."""
    registers = {**vdi.DIRTY, **ENTRY_REGS}
    pokes = vdi.transcription_pokes("VDI_ROM_ENTRY", entry_pokes(1))
    _final, _writes, left = emu.run(make_image(pokes), vdi.PLAIN_CALLER.at, registers)
    assert {name: left[name] for name in emu.REPORTED_REGS if name != "d0"} == \
        {name: value for name, value in registers.items() if name != "d0"}
    assert left["d0"] == registers["d0"] & ~0xFFFF, "D0.w is VDI_RESULT, cleared; its high half the caller's"


def entry_pokes(points):
    source = vdi.SCREEN.base if points > 1 else vdi.PTSIN_AT
    return entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, points, source=source)


ENTRY_REGS = {"d0": entry.VDI_SELECTOR, "d1": vdi.PARAMETER_BLOCK_AT}
# $a000's `jsr` callers, one POOL_STRIDE apart in the band's room for them, past the exception callers'.
POOL_STRIDE = 0x10
POOL = vdi.CallerPool(entry.JSR_CALLERS_AT, entry.JSR_CALLERS_END, POOL_STRIDE, {"LINEA_ROM_INIT": ("a1", "a2")})

# ---- the rows Tier 3 prices ----------------------------------------------------------------------------------------
for _label, _number, _pokes, _regs, _cleared in HANDLER_CASES:
    vdi.register_transcription("LINEA_ROM_DISPATCH", _label, _pokes, _regs,
                               caller=entry.exception_caller(LINE_A | _number, _cleared))
POOL.register_transcription("LINEA_ROM_INIT", "by jsr", {})
for _points in (0, 1, entry.PAST_THE_CAP):
    vdi.register_transcription("VDI_ROM_ENTRY", f"{_points} point(s)", entry_pokes(_points), ENTRY_REGS)
