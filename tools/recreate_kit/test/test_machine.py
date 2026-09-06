"""Pin `include/machine.h`'s LONGWORD extend helpers against the oracle's own 68000.

`long_add_extend` / `long_sub_extend` model the X bit `add.l` / `sub.l` leave — the bit `addx`,
`subx` and `roxl` fold back in. It is not memory, so a project's byte differential cannot see it
directly: a wrong carry model shows up only where the flag changes a stored result, and the helper
itself is otherwise unpinned. `machine_probe.c` materialises the CPU's X into a reported register and
prints it beside the helper's answer, so the two are compared rather than one restating the other.

Built from the oracle's own sources by `probe_build.compile_probe`, for its reasons: `shim.c` is
recompiled on every run, and a checkout with nothing built skips rather than fails.
"""
import re
import subprocess

from pathlib import Path

import pytest

from probe_build import compile_probe

PROBE_SRC = Path(__file__).with_name("machine_probe.c")

# (left, right, X after `add.l`, X after `sub.l`), mirroring machine_probe.c's OPERANDS case for
# case — the operands are compared too, so a table edited on one side only fails by name. The
# expected bits are stated here rather than derived: `add` carries when the 32-bit sum wraps, `sub`
# borrows when the minuend is below the subtrahend, and neither has anything to do with signed
# overflow (case 7 is exactly that distinction).
CASES = (
    (0x00000000, 0x00000000, 0, 0),
    (0x00000000, 0x00000001, 0, 1),   # 0 - 1 borrows
    (0x00000001, 0x00000000, 0, 0),
    (0x00000001, 0xffffffff, 1, 1),   # the sum wraps to 0; and 1 is below 0xffffffff
    (0xffffffff, 0x00000001, 1, 0),   # the same sum, the other way round; no borrow
    (0xffffffff, 0xffffffff, 1, 0),   # equal operands never borrow
    (0x80000000, 0x80000000, 1, 0),   # the two sign bits carry out
    (0x7fffffff, 0x00000001, 0, 0),   # signed OVERFLOW, and no carry at all
    (0x12345678, 0xedcba988, 1, 1),   # wraps to exactly 0
)

EXPECTED = {}
for _index, (_left, _right, _add, _sub) in enumerate(CASES):
    EXPECTED[("add", _index)] = (_left, _right, _add)
    EXPECTED[("sub", _index)] = (_left, _right, _sub)


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Build and run the probe once; return {(op, index): (left, right, helper, cpu)}."""
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("machine"))
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {(op, int(index)): (int(left), int(right), int(helper), int(cpu))
            for op, index, left, right, helper, cpu
            in re.findall(r"^(add|sub) (\d+) (\d+) (\d+) (\d+) (\d+)$", out, re.M)}


def test_the_probe_reports_every_case(results):
    """Guard the fixture: a probe that stopped printing would make every assertion below vacuous."""
    assert set(results) == set(EXPECTED), (
        f"probe cases and expectations disagree — only in probe: "
        f"{sorted(set(results) - set(EXPECTED))}, only in EXPECTED: "
        f"{sorted(set(EXPECTED) - set(results))}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_helper_and_the_cpu_agree_on_the_extend_bit(results, case):
    left, right, helper, cpu = results[case]
    want_left, want_right, want_bit = EXPECTED[case]
    assert (left, right) == (want_left, want_right), (
        f"{case[0]} case {case[1]}: the probe ran ({left:#x}, {right:#x}) but this file expects "
        f"({want_left:#x}, {want_right:#x}) — the two operand tables have drifted apart")
    assert helper == cpu, (
        f"{case[0]} case {case[1]} ({left:#x}, {right:#x}): machine.h's long_{case[0]}_extend says "
        f"{helper}, the oracle's 68000 leaves X = {cpu}")
    assert helper == want_bit, (
        f"{case[0]} case {case[1]} ({left:#x}, {right:#x}): both sides say {helper}, but the extend "
        f"bit that pair leaves is {want_bit}")
