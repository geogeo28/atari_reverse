"""Pin the STRAY-WRITE GUARD over the band the differential drops (`harness._stray_stack_writes`).

`diff_spans()` drops `[STACK_GUARD_LO, STACK_BAND_HI)` because the oracle uses it as a real machine
stack and the C reconstruction has no analogue for one. That is sound only while the oracle uses it
PURELY as a stack, so `differential` reports every write inside it the run's own frame does not
explain — otherwise the drop would silently hide program output, which is the one thing a cutoff
must never do quietly.

ABOVE THE SENTINEL RETURN SLOT SITS THE CALLER'S ARGUMENT AREA, and it belongs to the CALLEE rather
than to the case: an Alcyon/DRI C routine writes its own arguments back into it (`move.l d0,8(a6)`,
the write-to-`(sp)` first-argument idiom every ROM and game in this workspace is full of), so the
function under test stores bytes there that no case poked. Reporting those as masked output made 103
of bubbleghost's cases red.

THE BAND ENDS AT THE TOP OF THAT AREA (`emu.STACK_BAND_HI`), so "a write above the area" is not this
guard's business at all — it is the byte diff's. That is the sharper of the two surfaces: such a
write reds with the address AND both sides' values rather than with a bare address. Both halves are
pinned below, and the second is what says the exemption did not give the guard away.

Everything is driven END TO END through a real `differential`, on a routine planted in the smoke
project's own image, rather than by calling the predicate with a synthetic write set: the guard is
only worth anything if `differential` still calls it, and the write has to reach the oracle through
the write ledger the guard actually reads.
"""
import re
import struct

from pathlib import Path

import pytest

from kit_smoke_project import bind

harness = bind()
emu = harness.emu

# Where the planted routine goes: in-image, clear of the smoke `.PRG`'s text and of the three
# scratch addresses its own routines use (0x30000..0x30040), and far below the stack band.
PLANTED_AT = 0x40000
STORED_BYTE = 0x5A

# The first argument slot, spelled as every project's `test/abi.py` spells it.
FIRST_ARG = emu.STACK_TOP + harness.SENTINEL_SLOT_BYTES
# ...and the first address ABOVE the caller's frame area, which no such frame reaches.
ABOVE_ARGS = FIRST_ARG + harness.STACK_ARGS_BYTES

_MOVE_B_IMM_ABSL = 0x13FC
_RTS = 0x4E75


def _store_routine(addr):
    """`move.b #STORED_BYTE,addr.l` / `rts`, as a poke that plants it at PLANTED_AT."""
    code = struct.pack(">HHI", _MOVE_B_IMM_ABSL, STORED_BYTE, addr) + struct.pack(">H", _RTS)
    return {PLANTED_AT: code}


def _run(addr):
    """Differential the planted store against a candidate that writes nothing.

    The store lands in the DROPPED band, so the byte comparison cannot see it either way — which is
    exactly the situation the guard exists for, and why a candidate that does nothing is the right
    counterpart rather than a defect in the case.
    """
    return harness.differential(PLANTED_AT, {"_pokes": _store_routine(addr)},
                                lambda lib, buf: lib.g_hw_untouched(buf))


PROJECTS = Path(__file__).resolve().parents[3] / "projects"
# How a case stages a called function's arguments: `abi.stack_args((2, handle), (4, buffer), …)`,
# one `(width_in_bytes, value)` per argument — plus bubbleghost's `("slot", n)` form, which is a
# longword pointer into its out-parameter table.
_STACK_ARGS_CALL = re.compile(r"stack_args\(")
_ARG_WIDTH = re.compile(r'\(\s*(?:(2|4)|"slot")\s*,')
_SLOT_WIDTH_BYTES = 4

# What `harness.STACK_ARGS_BYTES` IS, and the one bound with no spelling to derive: a case entering a
# routine mid-body declares a synthetic frame base above STACK_TOP so that A6 and A7 stand where the
# routine's own `link` would have left them, and the routine then writes its locals there. MEASURED
# — every project's suite run with the exemption removed — at 24 bytes past the sentinel slot, by
# bubbleghost's `link a6,#$ffe4` slice (`test_draw_room_to_stage_cell`), whose deeper locals at
# +28/+30 that case STAGES and which are therefore exempt already. The deepest write nothing stages
# is +24..+27, and that is this number.
DEEPEST_SYNTHETIC_FRAME_LOCAL = 24


def _widest_staged_argument_list():
    """The widest argument list any case in this workspace stages, in bytes, or None.

    Parsed rather than restated, because ``STACK_ARGS_BYTES`` is a MEASUREMENT of the projects and a
    number nobody re-derives is a number that silently stops being true — the next case to push a
    wider list would have its callee's write-back reported as masked output, with a message pointing
    at the stack band rather than at this constant.

    THE REGEX READS LITERAL WIDTHS ONLY (``(2, x)``, ``(4, x)``, ``("slot", x)``); a case that spelt
    a width as a name or an expression contributes 0 rather than its real size. That is a deliberate
    floor rather than an oversight — every `stack_args` call in the workspace spells the width as a
    literal, which is what the helper takes one for — and the bound it produces is only ever used to
    say the exempt area is WIDE ENOUGH. The case that would slip past it is a non-literal width
    summing past 24, and the surface that reds for that is the project's own suite.

    Returns None where the projects are not present, which is the kit's own bare-checkout state.
    """
    if not PROJECTS.is_dir():
        return None
    widest = 0
    for path in PROJECTS.rglob("*.py"):
        source = path.read_text(errors="ignore")
        for call in _STACK_ARGS_CALL.finditer(source):
            depth, end = 1, call.end()
            while depth and end < len(source):
                depth += (source[end] == "(") - (source[end] == ")")
                end += 1
            body = source[call.end():end - 1]
            widest = max(widest, sum(int(w) if w else _SLOT_WIDTH_BYTES
                                     for w in _ARG_WIDTH.findall(body)))
    return widest or None


def test_the_frame_area_covers_the_widest_list_the_workspace_stages():
    """One of the constant's two bounds, re-derived rather than trusted.

    A callee cannot write above the argument list its caller pushed, so the widest list any case
    stages is a hard lower bound on the exempt area — and it is a MEASUREMENT of the projects, which
    a number nobody re-derives silently stops matching. The next case to push a wider list would
    have its callee's write-back reported as masked output, with a message pointing at the stack
    band rather than at this constant.

    The area is deliberately WIDER than this bound, and the surplus is the constant's OTHER evidence:
    a case entering a routine mid-body declares a synthetic frame base above STACK_TOP, and the
    routine's own locals are written there. That shape has no parsable spelling to derive — a frame
    base is an ordinary `emu.STACK_TOP + n` in a project's own test module — so it is recorded in
    `harness.STACK_ARGS_BYTES`'s comment with the measurement that produced it, and pinned by the
    end-to-end cases below rather than here.
    """
    widest = _widest_staged_argument_list()
    if widest is None:
        pytest.skip("no projects/ in this checkout, so the widest argument list cannot be measured")
    assert harness.STACK_ARGS_BYTES >= widest, (
        f"a case now stages {widest} bytes of arguments but the exempt area is only "
        f"{harness.STACK_ARGS_BYTES} — its callee's write-back into the top of its own frame will "
        f"be reported as output masked by the stack-band cutoff")


def test_the_exempt_area_is_exactly_the_deepest_unstaged_frame_write():
    """The constant's other bound, and it is an EQUALITY because the band now ends here.

    Too SMALL and a synthetic frame's own locals read as masked output (the battery that reddens for
    real is projects/bubbleghost's `test_draw_room_to_stage_cell`). Too LARGE and bytes of real
    compared image are dropped from the diff instead — which is what used to cost every .PRG project
    the last 228 bytes of its image, invisibly, because a byte nothing compares reds nowhere. So the
    measurement IS the value, in both directions, and moving it is a case's evidence to bring.
    """
    assert harness.STACK_ARGS_BYTES == DEEPEST_SYNTHETIC_FRAME_LOCAL, (
        f"the exempt area is {harness.STACK_ARGS_BYTES} bytes where the deepest write no case "
        f"stages reaches {DEEPEST_SYNTHETIC_FRAME_LOCAL}. Below that, a callee's own frame locals "
        f"red as masked output; above it, that many bytes of compared image are dropped from every "
        f"diff in the workspace with nothing to report the loss")


def test_the_band_is_wide_enough_for_this_suite_to_mean_anything():
    """The frame area must be INSIDE the dropped band, or the exemption case below is measuring the
    ordinary byte diff instead of the guard — and the first address ABOVE it must be outside, which
    is what hands a write there to the diff."""
    assert not harness.in_diff(FIRST_ARG), "the argument area is no longer inside the dropped band"
    assert not harness.in_diff(ABOVE_ARGS - 1), "the frame area's last byte is no longer dropped"
    assert harness.in_diff(ABOVE_ARGS), (
        f"{ABOVE_ARGS:#x} is still inside the dropped band, so a write there would be hidden from "
        f"the byte diff — the band no longer closes at the top of the frame area")


# Deep inside the dropped band and far below any frame this run could push: `STACK_SCRATCH` is the
# only part below STACK_TOP a call may legitimately use, so a write below that is program output the
# drop would hide — which is the guard's whole subject.
DEEP_IN_THE_BAND = emu.STACK_GUARD_LO + 8


def test_a_write_deep_in_the_dropped_band_is_reported_by_the_guard():
    """The guard's own direction, which the byte diff cannot cover: this address IS dropped.

    Everything above the frame area is compared image now, so the cases below are about the diff.
    This one is what says the remaining band — the scratch a frame never reaches — is still watched:
    the store lands where no comparison can see it, and only `_stray_stack_writes` reports it.
    """
    assert not harness.in_diff(DEEP_IN_THE_BAND), (
        "this address is compared, so the case would red on the byte diff rather than on the guard")
    with pytest.raises(AssertionError, match="reserved stack band"):
        _run(DEEP_IN_THE_BAND)


def test_a_callee_writing_its_own_frame_area_is_not_reported():
    """The exemption, which is what a callee's write-back needs.

    The store goes to the first argument slot, which the case did NOT poke — the poke plants the
    routine, nothing else — so the staged-address exemption cannot be what lets this through. Only
    the argument area's own exemption can.
    """
    diffs, _info = _run(FIRST_ARG)
    assert diffs == [], "the store reached a compared byte, so this case is not about the guard"


@pytest.mark.parametrize("offset", (0, 1, 0x40))
def test_a_write_above_the_frame_area_shows_in_the_byte_diff(offset):
    """...and the half the exemption must not give away.

    No caller's frame reaches above the argument list it pushed, so a store there is ordinary
    program output — and it lands in COMPARED image, where the candidate (which stores nothing)
    differs from the oracle byte for byte. Driven at the area's first byte and just past it as well
    as well clear of it, because an off-by-one in the bound is exactly the mutation that would drop
    the first byte of real output instead.
    """
    where = ABOVE_ARGS + offset
    diffs, _info = _run(where)
    assert diffs == [(where, STORED_BYTE, 0)], (
        f"the store at {where:#x} did not come back as a byte difference, so the dropped band still "
        f"covers it")


def test_the_last_byte_of_the_frame_area_is_still_exempt():
    """The other side of the same bound: an area one byte short would report the last byte a caller
    with the widest argument list really staged, or — since the band closes here too — compare it."""
    diffs, _info = _run(ABOVE_ARGS - 1)
    assert diffs == []
