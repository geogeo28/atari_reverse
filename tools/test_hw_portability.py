#!/usr/bin/env python3
"""The pins for `tools/hw_portability.py` — its tier lattice, its tripwires, and its arithmetic.

WHY IT LIVES HERE, next to the tool, and not under any `projects/<name>/recreate/test/`: the tool
is game-agnostic, its tier rules encode `tools/recreate_kit`'s model rather than any one program's
behaviour, and a per-project suite would pin a shared tool from inside one game — the next game to
re-bootstrap would drag an unrelated failure along. It is deliberately NOT wired into any project's
`make test`, which builds an oracle `.so` this file never needs.

Run it standalone:

    pytest tools/test_hw_portability.py

THREE GROUPS, and the failure each exists to catch:

  * the LATTICE — the tier every access shape earns. The rule was re-derived against kit Phase 6
    (see `projects/wonderboy/recreate/PORTABILITY.md` §0g); before that it priced every PSG read as
    a hard reject, understating what the harness could verify by 20 functions on one real program.
    What matters most here is the T5 BOUNDARY: Phase 6 serves exactly one shape, and each case
    below is a shape it does NOT serve.
  * the TRIPWIRES — `check_shim_agreement()`, exercised by mutating throwaway copies of the kit.
    Every case is a drift that was measured to slip past an earlier version of the check.
  * the ARITHMETIC — one end-to-end reproduction against a committed scan, so a refactor of the
    call-graph closure cannot quietly move a published figure.
"""
import importlib.util
import pathlib
import shutil
import subprocess
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent
TOOL = TOOLS / "hw_portability.py"
KIT = TOOLS / "recreate_kit"

# The one committed scan in the workspace. BuggyBoy's and Joust's Ghidra DBs predate the
# reloc-parse fix (docs/ghidra-pipeline.md) and have no committed scan to pin against.
WONDERBOY_SCAN = REPO / "projects" / "wonderboy" / "out" / "hw_scan.tsv"
WONDERBOY_SUBSYSTEMS = REPO / "projects" / "wonderboy" / "recreate" / "subsystems.tsv"
COPYLOCK_EXCLUSION = (0xED8E, 0xF540, "Copylock ciphertext")


def load_tool():
    """Import hw_portability.py by path — it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("hw_portability", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hp = load_tool()


def access(addr, size, direction):
    """One synthetic Access with the scan's own field spellings, for a pure tier assertion."""
    return hp.Access(hp.UNATTRIBUTED_FN, 0, addr, str(size), direction, "ABS", "-", "-", "synthetic")


# --- the lattice ------------------------------------------------------------------------------
# (address, size, direction, expected tier, what the kit does with it). Sizes are the scan's:
# an int for a sized transfer, "?" where Ghidra could not size the operand.
LATTICE_CASES = [
    (0xFF8800, 1, "READ", "T_PSG_SEEDED_READ",
     "psg_read_back() serves it from the seeded register file and ledgers it"),
    (0xFFFF8800, 1, "READ", "T_PSG_SEEDED_READ",
     "the same port through the 68000's 24-bit bus alias, which BUS_ADDR_MASK folds"),
    (0xFF8802, 1, "READ", "T_HARD_REJECT",
     "the data port is write-only on the chip; the model refuses rather than invent a value"),
    (0xFF8804, 1, "READ", "T_HARD_REJECT",
     "a block mirror: the ST decodes the PSG incompletely, and only the canonical port reads back"),
    (0xFF8800, 2, "READ", "T_HARD_REJECT",
     "a WIDE read AT the read-back port takes in a neighbour the model cannot fabricate"),
    (0xFF8800, 4, "READ", "T_HARD_REJECT", "likewise at 32 bits"),
    (0xFF87FE, 4, "READ", "T_HARD_REJECT",
     "a long read straddling INTO the block from below — the case a start-address test misses"),
    (0xFF8800, 1, "WRITE", "T_PSG_WRITE", "the modeled select-latch write"),
    (0xFF8802, 1, "WRITE", "T_PSG_WRITE", "the modeled data-port write"),
    (0xFF8801, 1, "WRITE", "T_HARD_REJECT", "an odd alias, whose decoding the kit does not model"),
    (0xFF8800, 2, "WRITE", "T_HARD_REJECT", "a wide write over the port pair"),
    (0xFF8800, "?", "READ", "T_HARD_REJECT",
     "an operand Ghidra could not size is NOT assumed to be the modeled byte protocol"),
    (0xFFFA01, 1, "READ", "T_HW_READ",
     "MFP GPIP: served a real byte ONLY under audio capture, silently 0 for every differential"),
    (0xFF820A, 1, "READ", "T_HW_READ", "shifter sync: the same silent zero, BuggyBoy's tempo branch"),
    (0xFFFC00, 1, "READ", "T_HW_READ",
     "the IKBD status is the one non-zero answer, but a fabricated constant is still a read"),
    (0xFF8240, 2, "WRITE", "T_HW_WRITE", "a palette write: dropped, so the run completes blind"),
]


@pytest.mark.parametrize("addr,size,direction,tier_name,why",
                         LATTICE_CASES,
                         ids=[f"{a:#x}-{s}-{d}" for a, s, d, _, _ in LATTICE_CASES])
def test_access_earns_its_tier(addr, size, direction, tier_name, why):
    assert access(addr, size, direction).tier == getattr(hp, tier_name), why


def test_a_psg_read_is_never_counted_as_false_green():
    """Neither shape can fabricate a branch: a served read is a DECLARED input, a refused one never
    completes the run. The false-green count is the report's most consequential number."""
    for addr, size, direction in ((0xFF8800, 1, "READ"), (0xFF8802, 1, "READ")):
        steering = hp.Access(hp.UNATTRIBUTED_FN, 0, addr, str(size), direction, "ABS",
                             hp.STEER_VERDICT, "-", "synthetic")
        assert not steering.steers


def test_a_steering_non_psg_read_is_counted():
    """The positive control for the test above — otherwise it would pass on a broken `steers`."""
    steering = hp.Access(hp.UNATTRIBUTED_FN, 0, 0xFFFA01, "1", "READ", "ABS",
                         hp.STEER_VERDICT, "-", "synthetic")
    assert steering.steers


def test_tier_names_and_order_agree():
    """The lattice is compared with `<` and `max()` throughout, so its ORDER is load-bearing, and
    `tier_num()` reads the numbers out of these strings for the report's prose."""
    assert hp.TIER_NAMES == ["T0 CLEAN", "T1 PSG_WRITE_ONLY", "T2 PSG_SEEDED_READ",
                             "T3 HW_WRITE_ONLY", "T4 HW_READ", "T5 HARD_REJECT", "T6 UNMEASURABLE"]
    assert hp.T_CLEAN < hp.T_PSG_WRITE < hp.T_PSG_SEEDED_READ < hp.T_HW_WRITE
    assert hp.T_HW_WRITE < hp.T_HW_READ < hp.T_HARD_REJECT < hp.T_UNMEASURABLE
    assert hp.tier_num(hp.T_PSG_SEEDED_READ) == "T2"


def test_a_seeded_read_is_runnable_and_a_rejected_one_is_not():
    """`runnable` is defined as `tier < T_HARD_REJECT` in two places; this pins which side of that
    line the new tier falls on, which is the whole point of inserting it below the hardware tiers."""
    assert hp.T_PSG_SEEDED_READ < hp.T_HARD_REJECT
    assert not hp.T_HARD_REJECT < hp.T_HARD_REJECT


# --- the tripwires ----------------------------------------------------------------------------

@pytest.fixture
def kit_copy(tmp_path, monkeypatch):
    """A throwaway kit whose files the test may mutate, with the tool re-pointed at it.

    The tool resolves its pinned paths at import time, so each path is monkeypatched individually —
    including the tuple `PINNED_CONSTANTS` and the `SHIM_C` the behavioural check uses, which is
    also what keeps that check from silently drifting onto os.h if the tuple is ever reordered.
    """
    root = tmp_path / "recreate_kit"
    (root / "oracle").mkdir(parents=True)
    (root / "include").mkdir(parents=True)
    shim_c, os_h = root / "oracle" / "shim.c", root / "include" / "os.h"
    shutil.copy(KIT / "oracle" / "shim.c", shim_c)
    shutil.copy(KIT / "include" / "os.h", os_h)
    monkeypatch.setattr(hp, "KIT", root)
    monkeypatch.setattr(hp, "SHIM_C", shim_c)
    monkeypatch.setattr(hp, "OS_H", os_h)
    monkeypatch.setattr(hp, "PINNED_CONSTANTS",
                        tuple((shim_c if path.name == "shim.c" else os_h, pins)
                              for path, pins in hp.PINNED_CONSTANTS))
    return root


def rewrite(path, old, new):
    text = path.read_text()
    assert old in text, f"the fixture's own premise is stale: {old!r} is not in {path.name}"
    path.write_text(text.replace(old, new))


def test_an_unmutated_kit_passes(kit_copy):
    """The control. Without it every tripwire case below could pass on a check that always exits."""
    hp.check_shim_agreement()


def test_a_renamed_constant_fails(kit_copy):
    """Kit Phase 6, replayed: it moved OS_PSG_PORT_SELECT out of shim.c, and the pin — still naming
    shim.c — refused every run until repaired. That refusal is the behaviour, not the bug."""
    rewrite(kit_copy / "include" / "os.h", "#define OS_PSG_PORT_SELECT", "#define YM_PORT_SELECT")
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "OS_PSG_PORT_SELECT" in str(exit_info.value)


def test_a_changed_constant_value_fails(kit_copy):
    rewrite(kit_copy / "include" / "os.h", "0xff8802u", "0xff8806u")
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "0xff8806" in str(exit_info.value)


def test_a_changed_block_end_fails(kit_copy):
    """PSG_BLOCK_END decides which accesses are tested against the PSG protocol at all."""
    rewrite(kit_copy / "oracle" / "shim.c", "#define PSG_BLOCK_END 0xff8900",
            "#define PSG_BLOCK_END 0xff8880")
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "PSG_BLOCK_END" in str(exit_info.value)


@pytest.mark.parametrize("rewritten", ["(0xff8802u)", "0xff8802u | PSG_SOME_FLAG", "(PSG_BASE + 2)"])
def test_a_value_that_is_no_longer_a_bare_literal_fails(kit_copy, rewritten):
    """A value group anchored only at its START silently reads `0xff8802` out of
    `0xff8802u | PSG_SOME_FLAG` and pins a constant the kit does not have — the trailing-junk case
    is the one that discriminates, since a leading paren already fails to match. All three shapes
    must end the pin loudly rather than half-read it."""
    rewrite(kit_copy / "include" / "os.h", "0xff8802u", rewritten)
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "bare literal" in str(exit_info.value)


def test_a_renamed_seeded_read_fails(kit_copy):
    """The T2 tier's whole basis. This is the over-count direction of drift — the tool would go on
    calling those reads runnable while the oracle had gone back to refusing them."""
    rewrite(kit_copy / "oracle" / "shim.c", "psg_read_back", "psg_readback_v2")
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "psg_read_back" in str(exit_info.value)


def test_a_seeded_read_named_only_in_a_comment_fails(kit_copy):
    """A bare `"psg_read_back" in text` check was MEASURED to pass on exactly this shim: the
    function renamed, the old name surviving in the comment above it. The pin matches a definition
    for that reason, so a comment can never stand in for the code."""
    shim_c = kit_copy / "oracle" / "shim.c"
    rewrite(shim_c, "static unsigned int psg_read_back(void)",
            "/* replaces psg_read_back() */\nstatic unsigned int psg_read_back_removed(void)")
    assert "psg_read_back" in shim_c.read_text(), "the mutation must keep the substring present"
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "psg_read_back" in str(exit_info.value)


def test_the_behavioural_pin_follows_shim_c_not_the_tuple_order(kit_copy, monkeypatch):
    """The tool's own repair instruction tells a future reader to MOVE an entry in
    PINNED_CONSTANTS. If the behavioural check reached its file positionally it would then be
    reading os.h for a function that lives in shim.c — and pass forever. Reversing the tuple must
    change nothing."""
    monkeypatch.setattr(hp, "PINNED_CONSTANTS", tuple(reversed(hp.PINNED_CONSTANTS)))
    hp.check_shim_agreement()
    rewrite(kit_copy / "oracle" / "shim.c", "static unsigned int psg_read_back(void)",
            "static unsigned int psg_readback_v2(void)")
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert "psg_read_back" in str(exit_info.value)


@pytest.mark.parametrize("missing", ["oracle/shim.c", "include/os.h"])
def test_a_present_kit_missing_a_pinned_file_fails(kit_copy, missing):
    """Measured hole: skipping per-file let a deleted os.h leave both OS_PSG_* constants unpinned,
    and a deleted shim.c leave three constants AND the behavioural pin unchecked — exit 0 either
    way, still pricing T2. A present kit missing a pinned file is drift, not absence."""
    (kit_copy / missing).unlink()
    with pytest.raises(SystemExit) as exit_info:
        hp.check_shim_agreement()
    assert missing.split("/")[-1] in str(exit_info.value)


def test_no_kit_at_all_still_classifies(tmp_path, monkeypatch):
    """The one case that must NOT fail: a checkout without the kit cannot contradict anything, and
    the tool is useful there. This is the boundary the per-file rule above must not overrun."""
    monkeypatch.setattr(hp, "KIT", tmp_path / "absent")
    hp.check_shim_agreement()


# --- the arithmetic ---------------------------------------------------------------------------

@pytest.mark.skipif(not WONDERBOY_SCAN.exists(), reason="no committed hw_scan.tsv to pin against")
def test_the_committed_scan_reproduces_its_published_figures():
    """The end-to-end regression: one real scan, the closure, the published totals.

    The tier LATTICE moved in §0g and these numbers moved with it — deliberately, and accounted for
    function by function there. What this case pins is that nothing moves them AGAIN by accident: a
    refactor of the fixed-point closure or of the exclusion handling would otherwise shift a
    published figure with no diff to show for it.
    """
    scan = hp.parse_scan(WONDERBOY_SCAN, set())
    excluded = hp.apply_exclusions(scan, [COPYLOCK_EXCLUSION])
    direct_tier, direct_steers = hp.direct_tiers(scan, excluded)
    tier, steers = hp.close_over_call_graph(scan, direct_tier, direct_steers)

    runnable = [a for a in scan.funcs if tier[a] < hp.T_HARD_REJECT]
    at_risk = [a for a in scan.funcs if steers[a]]
    assert len(scan.funcs) == 256
    assert sum(f.size for f in scan.funcs.values()) == 25786
    assert (len(runnable), sum(scan.funcs[a].size for a in runnable)) == (242, 24318)
    assert (len(at_risk), sum(scan.funcs[a].size for a in at_risk)) == (28, 3348)
    # No function hard-rejects on its own access any more: Phase 6 removed the last PSG read wall.
    assert not [a for a in scan.funcs if direct_tier[a] == hp.T_HARD_REJECT]


@pytest.mark.skipif(not WONDERBOY_SCAN.exists(), reason="no committed hw_scan.tsv to pin against")
def test_the_realised_model_equals_the_capability_it_was_priced_at():
    """`--model psg:read` prices the HYPOTHETICAL "harness gains a PSG read model" (PORTABILITY.md
    §6, its largest predicted lever). Phase 6 built it, so the default run must now reach the same
    place the flag used to — and the flag must buy nothing further on top."""
    def runnable_totals(modeled):
        scan = hp.parse_scan(WONDERBOY_SCAN, modeled)
        excluded = hp.apply_exclusions(scan, [COPYLOCK_EXCLUSION])
        direct_tier, direct_steers = hp.direct_tiers(scan, excluded)
        tier, _ = hp.close_over_call_graph(scan, direct_tier, direct_steers)
        keys = [a for a in scan.funcs if tier[a] < hp.T_HARD_REJECT]
        return len(keys), sum(scan.funcs[a].size for a in keys)

    assert runnable_totals(set()) == runnable_totals({("psg", "read")})


@pytest.mark.skipif(not WONDERBOY_SCAN.exists(), reason="no committed hw_scan.tsv to pin against")
def test_the_tool_runs_end_to_end_as_a_script():
    """Everything above imports the module; this is the only case that proves `main()` — argument
    parsing, the report sections, the exit status — still works as the documented command."""
    argv = [sys.executable, str(TOOL), str(WONDERBOY_SCAN),
            "--exclude", "0x%x:0x%x:%s" % COPYLOCK_EXCLUSION, "--root", "0x4a0", "--root", "0x400"]
    if WONDERBOY_SUBSYSTEMS.exists():
        argv += ["--subsystems", str(WONDERBOY_SUBSYSTEMS)]
    done = subprocess.run(argv, capture_output=True, text=True, check=True)
    assert "242/256 functions, 24318/25786 bytes = 94.3 %" in done.stdout
    assert "| T2 PSG_SEEDED_READ |" in done.stdout


def test_an_empty_scan_is_refused(tmp_path):
    """A failed Ghidra run leaves a header-only TSV, which would otherwise print a report of zeroes
    and exit 0 — "nothing measured" reading as "everything clean"."""
    empty = tmp_path / "hw_scan.tsv"
    empty.write_text("# hw scan\nP\tprogram\tNONE.PRG\n")
    done = subprocess.run([sys.executable, str(TOOL), str(empty)], capture_output=True, text=True)
    assert done.returncode != 0
    assert "no F records" in done.stderr
