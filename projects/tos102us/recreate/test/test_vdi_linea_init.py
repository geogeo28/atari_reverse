"""Line-A $a000 ($fc9f34) — the primitive doors' worked example: `src/vdi/linea.c`.

    lea $299a,a0 / move.l a0,d0 / lea $fc9f8a,a1 / lea $fc9f4a,a2 / rts

It reads nothing and answers in FOUR registers, which is what makes it the example of
`vdi.declare_primitive`'s several-register answer: each of D0/A0/A1/A2 is compared on both shores.
It is run twice — by `jsr`, as the VDI enters primitives, and THROUGH the Line-A exception, as a
program does. The first is priced: Tier 3's column compares D0 (the core returns it and writes all four
through its pointer), Tier 1 here compares all four. The second is not — it is entered at a stub.
"""
import re
from pathlib import Path

import pytest

from harness import addrs

import vdi

NAME = "LINEA_ROM_INIT"
OPCODE = 0
RESULTS = ("d0", "a0", "a1", "a2")
vdi.declare_primitive(NAME, results=RESULTS)
# What the registers hold on entry, distinct from every answer, so an answer left unwritten shows.
ENTRY = {register: 0xDEC0_DE00 + index for index, register in enumerate(RESULTS)}
VDI_H = Path(__file__).resolve().parents[1] / "include" / "vdi" / "vdi.h"
LINEA_INIT_ENUM = re.compile(r"enum \{ (LINEA_INIT_\w+(?:, LINEA_INIT_\w+)*) \};")


def test_the_c_twin_s_answers_are_declared_in_this_battery_s_order():
    """`vdi/vdi.h`'s LINEA_INIT_* index the C twin's answers, and the AES's `$a000` bridge (`aes/gsx.h`) takes
    LINEA_INIT_A0 out of them; RESULTS here is the order of its own. Held equal: D0 and A0 both answer LINEA_BASE, so
    a swap of the two is invisible to any run."""
    declared = LINEA_INIT_ENUM.search(VDI_H.read_text())
    assert declared, f"vdi.h's LINEA_INIT_* enum is no longer one line matching {LINEA_INIT_ENUM.pattern!r}"
    names = [name.removeprefix("LINEA_INIT_").lower() for name in declared.group(1).split(", ")]
    assert names == [*RESULTS, "answers"]


def test_by_jsr_answers_the_block_and_both_tables():
    result = vdi.run_primitive(NAME, ENTRY, {})
    regs = result.info["regs"]
    assert (regs["d0"], regs["a0"]) == (vdi.LINEA_BASE, vdi.LINEA_BASE)
    assert (regs["a1"], regs["a2"]) == (vdi.LINEA_FONT_TABLE, vdi.LINEA_OPCODE_TABLE)


@pytest.mark.parametrize("scratch", (0, 0xFFFF_FFFF))
def test_through_the_exception_the_answer_survives_the_handler(scratch):
    """`$fc9f0c` restores D3-D7/A3-A5 only, so the four answers reach the program — and the staged
    `rts` after the opcode word is reached, which is the handler adding 2 to the stacked PC."""
    registers = {**ENTRY, "d3": scratch, "a3": scratch}
    result = vdi.run_through_exception(NAME, OPCODE, registers, {})
    regs = result.info["regs"]
    assert (regs["d3"], regs["a3"]) == (scratch, scratch)
    assert regs["a2"] == vdi.LINEA_OPCODE_TABLE


vdi.register("linea_init, by jsr", addrs.LINEA_ROM_INIT, {}, regs=ENTRY)
vdi.register("linea_init, through the exception", vdi.STUB_AT, vdi.exception_stub_pokes(OPCODE),
             regs=ENTRY, priced=False)
