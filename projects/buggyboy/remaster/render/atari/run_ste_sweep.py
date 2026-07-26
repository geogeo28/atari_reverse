#!/usr/bin/env python3
"""run_ste_sweep.py — PERF30 C4: prove the STE colour/objshift2 blitter paths are byte-exact vs the CPU
engines across the whole case space (fine_x x width/base_cells x column/clip family x rows x colour).

Builds the GAME_STE_SWEEP variant and boots it on --machine ste --blitter. The PRG (src/blitter_sweep.c)
runs five sections — the objshift2 grid, the objshift pre-shift grid, the objshift HARDWARE-SKEW grid,
the skew route's sprite-key TABLE (hit / grow / y_count clip / full-table decline), and a BELOW-SCREEN
section that blits both shipping routes at and past the bottom edge and compares the overdraw tail too —
against their CPU references, and dumps a per-case mismatch grid to SCREEN.BIN: word0 = case count,
word1 = total mismatch, then one word per case (0 == byte-exact; clip cases the blitter declines are
logged 0 as the pinned CPU hybrid), then a SELF-DESCRIBING tail: the section layout, the drawn counts,
the count each section must reach, which sections ran, whether the boot bind placed the routes' tables at
all, and the cost bench. ALL case words zero == PASS.

A pass is not enough on its own: a section that declined every case would also report zero mismatches.
So the run additionally fails unless each section drew the number of cases the report itself says it
should — that non-vacuity gate is what makes the zero meaningful.

Usage:
    python render/atari/run_ste_sweep.py                 # the pin
    python render/atari/run_ste_sweep.py --mutate 1      # coverage check: a broken skew register MUST fail
    python render/atari/run_ste_sweep.py --mutate all    # every mutation in turn, aggregate verdict
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402

SWEEP_PRG = "BUGGYBST.PRG"
SCREEN_BYTES = run_hatari.SCREEN_BYTES
NWORDS = SCREEN_BYTES // 2

# Tail word indices, counted back from the end of the report — mirrors SWEEP_TAIL_* in blitter_sweep.c.
TAIL = {"handled2": 1, "handled_osh": 2, "handled_skew": 3,
        "n_cases2": 4, "n_cases_osh": 5, "expect_base": 6, "grids_run": 7,
        "bench_iters": 8, "bench_mat": 9, "bench_pass_syn": 10, "bench_pass_bin": 11,
        "bench_all_syn": 12, "bench_all_bin": 13, "bench_cpu": 14, "bench_declined": 15,
        "n_cases_tbl": 16, "cases_run_tbl": 17, "served_tbl": 18, "expect_tbl": 19,
        "n_cases_below": 20, "handled_below": 21, "tables_bound": 22}

# SWEEP_GRID_* in blitter_sweep.c: which sections the build actually ran.
GRID_OBJSHIFT2, GRID_OSH_PRESHIFT, GRID_OSH_SKEW, GRID_OSH_TABLE, GRID_BELOW = 1, 2, 4, 8, 16
GRIDS_ALL = GRID_OBJSHIFT2 | GRID_OSH_PRESHIFT | GRID_OSH_SKEW | GRID_OSH_TABLE | GRID_BELOW
# A mutate build sweeps only the two sections the skew route owns (blitter_sweep_super).
GRIDS_MUTATE = GRID_OSH_SKEW | GRID_OSH_TABLE
# 4 MB pinned, not RM_MEMSIZE's default: the sweep's own statics plus the two lookup tables the boot bind
# places in the free TPA are a REQUIREMENT of this measurement — a starved run would decline the tables
# and sweep nothing (which the report's tables_bound word then reports honestly, but is not a pin).
SWEEP_MEMSIZE = "4"

HZ200_CYCLES = 8_000_000 // 200                            # ST 68000 cycles per TOS _hz_200 tick

# The runner's MIRROR of blitter_sweep.c's grid dimensions. It is checked against word0 before anything
# is decoded, and nothing else is derived from it: the section offsets and the non-vacuity expectations
# come from the report's own layout words, so a C-side dimension change fails here loudly instead of
# silently re-attributing cases to the wrong section.
N_CASES_MIRROR, N_OSH_CASES_MIRROR = 3 * 16 * 12 * 3, 2 * 16 * 12 * 4
N_TBL_CASES_MIRROR = 128 + 8                               # OBJSH_SKEW_TABLE_ENTRIES + the 8 fixed cases
N_BELOW_CASES_MIRROR = 4 * 2 * (2 + 2)                     # under x fine_x x (objshift2 widths + base_cells)
# Decode hint for the fine_x diagnostic only (columns x (colour,rows,stride) tuples — the colour grid's
# two innermost loops). Not a gate: it only labels which fine_x values a mutation failed at.
OSH_INNER_PER_FINEX = 12 * 4

# The mutations (RM_SKEW_MUT_* in include/blitter.h) the --mutate knob can build, each with the section
# it MUST make fail. 1-5 break a calibrated register, so they fail the skew grid (and the table section
# with it, since the table blits through the same recipe); 6 breaks the table's grow rule alone, which
# no un-tabled grid can see — only the table section's taller-after-shorter case does.
MUTATIONS = {1: ("skew = fine_x + 1", "objshift skew"),
             2: ("FXSR forced on", "objshift skew"),
             3: ("endmask1 leading guard dropped", "objshift skew"),
             4: ("endmask3 trailing guard dropped", "objshift skew"),
             5: ("plane 3 `& ~mask` special dropped", "objshift skew"),
             6: ("table entry never grown to a taller sprite", "objshift table")}


def build(mutate):
    env = {**os.environ, "GAME_STE": "1", "GAME_STE_SWEEP": "1", "GAME_PRG": SWEEP_PRG,
           "GAME_STE_SKEW_MUTATE": str(mutate)}
    env.pop("GAME_STE_SELFTEST", None)
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def word(fb, i):
    return (fb[i * 2] << 8) | fb[i * 2 + 1]


def tail(fb, name):
    return word(fb, NWORDS - TAIL[name])


class Report:
    """The decoded SCREEN.BIN report: section layout, per-section failures, drawn counts, bench ticks."""

    def __init__(self, fb):
        self.fb = fb
        self.ncases = word(fb, 0)
        self.total = word(fb, 1)
        layout = N_CASES_MIRROR + 2 * N_OSH_CASES_MIRROR + N_TBL_CASES_MIRROR + N_BELOW_CASES_MIRROR
        if self.ncases != layout:
            die(f"report layout mismatch: word0={self.ncases}, this runner mirrors {layout} — "
                f"blitter_sweep.c's section dimensions moved and run_ste_sweep.py did not follow")
        self.n_cases2 = tail(fb, "n_cases2")
        self.n_osh = tail(fb, "n_cases_osh")
        self.n_tbl = tail(fb, "n_cases_tbl")
        self.n_below = tail(fb, "n_cases_below")
        if self.n_cases2 + 2 * self.n_osh + self.n_tbl + self.n_below != self.ncases:
            die(f"report tail disagrees with word0: {self.n_cases2} + 2*{self.n_osh} + {self.n_tbl} + "
                f"{self.n_below} != {self.ncases}")
        cases_run_tbl = tail(fb, "cases_run_tbl")
        if cases_run_tbl != self.n_tbl:
            die(f"the table section logged {cases_run_tbl} cases but its layout word says {self.n_tbl} — "
                f"sweep_table_section and N_TBL_CASES are out of step")
        self.expect_base = tail(fb, "expect_base")
        self.grids_run = tail(fb, "grids_run")
        # name, first case index, case count, grids_run bit, drawn count, expected drawn count
        self.grids = [("objshift2", 0, self.n_cases2, GRID_OBJSHIFT2, tail(fb, "handled2"), None),
                      ("objshift pre-shift", self.n_cases2, self.n_osh, GRID_OSH_PRESHIFT,
                       tail(fb, "handled_osh"), self.expect_base),
                      ("objshift skew", self.n_cases2 + self.n_osh, self.n_osh, GRID_OSH_SKEW,
                       tail(fb, "handled_skew"), self.expect_base),
                      ("objshift table", self.n_cases2 + 2 * self.n_osh, self.n_tbl, GRID_OSH_TABLE,
                       tail(fb, "served_tbl"), tail(fb, "expect_tbl")),
                      # No case here may be declined (the family predicates are horizontal-only), so the
                      # section's expectation is its whole case count — see sweep_below_screen_grid.
                      ("below-screen", self.n_cases2 + 2 * self.n_osh + self.n_tbl, self.n_below,
                       GRID_BELOW, tail(fb, "handled_below"), self.n_below)]

    def ran(self, bit):
        return bool(self.grids_run & bit)

    def failures(self, first, count):
        return [i for i in range(first, first + count) if word(self.fb, 2 + i) != 0]

    def section(self, name):
        return next(g for g in self.grids if g[0] == name)


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def check_non_vacuous(rep, expect_grids):
    """The gate that makes a zero mismatch mean something: every section this build was supposed to run
    must have run, and must have DRAWN the number of cases the report says it should.

    The two colour grids share one case space and one family predicate, so they must agree with each
    other AND with the count the C side enumerates from that predicate. A skew path that quietly
    declined everything (or a clip test that drifted) shows up here as 0 drawn against a non-zero
    expectation, even though every case word would still read 0. The table section carries its own
    expectation — every case but the two deliberate declines — for the same reason: a table that stopped
    serving anything would fall back to the CPU hybrid and still be byte-exact."""
    if rep.grids_run != expect_grids:
        die(f"grids_run={rep.grids_run:#x}, expected {expect_grids:#x} — the build ran a different set "
            f"of sections than this run asked for")
    if rep.expect_base <= 0:
        die(f"the colour case space contains {rep.expect_base} BASE cases — the grid is vacuous")
    for name, first, count, bit, drawn, expected in rep.grids:
        if not rep.ran(bit):
            stale = rep.failures(first, count)
            if stale:
                die(f"section '{name}' was not run but its case words are non-zero ({len(stale)} of them)")
            continue
        if expected is not None and drawn != expected:
            die(f"section '{name}' drew {drawn} cases, expected {expected} — it is not exercising the "
                f"path it claims to pin")
        if drawn <= 0:
            die(f"section '{name}' drew no cases at all — vacuous")


def print_bench(rep):
    iters = tail(rep.fb, "bench_iters")
    if not iters:
        return
    declined = tail(rep.fb, "bench_declined")
    if declined:
        die(f"{declined} timed bench call(s) were DECLINED by the skew path — the bench timed no-ops")
    rows = [("materialise (5 unshifted bitmaps)", "bench_mat"),
            ("blit passes only, synthetic fill (8 passes)", "bench_pass_syn"),
            ("blit passes only, game fill      (6 passes)", "bench_pass_bin"),
            ("materialise + passes, synthetic fill", "bench_all_syn"),
            ("materialise + passes, game fill", "bench_all_bin"),
            ("shipping CPU engine (RM_BLIT_OBJSHIFT)", "bench_cpu")]
    for label, key in rows:
        print(f"cost[base_cells=2 rows=32]  {label:44s} {tail(rep.fb, key) * HZ200_CYCLES // iters:7d} cyc")


def print_counts(rep):
    drawn = "  ".join(f"{name}={d}" + ("" if rep.ran(bit) else " (skipped)")
                      for name, _, _, bit, d, _ in rep.grids)
    print(f"cases: {rep.ncases} (objshift2 + objshift pre-shift + objshift skew + table + below-screen)   "
          f"blitter-drawn: {drawn}   expected BASE per colour grid: {rep.expect_base}"
          f"   total mismatch: {rep.total}")


def run_sweep(mutate):
    """Build (optionally mutated) and boot the sweep; return the decoded Report."""
    build(mutate)
    # 4800 cases x full-framebuffer memset/compare is a lot of emulated cycles — give it a generous
    # vblank budget + wall-clock so the sweep finishes and dumps (default 4000 vbls is far too short).
    fb = run_hatari.run(SWEEP_PRG, machine="ste", blitter=True, needs_data=True, memsize=SWEEP_MEMSIZE,
                        run_vbls=240000, timeout=900)[:SCREEN_BYTES]
    # Checked BEFORE the report is decoded: on a declined run every section is legitimately empty, so the
    # layout checks in Report would fire first and blame blitter_sweep.c for being out of step.
    if not tail(fb, "tables_bound"):
        # The legal-but-vacuous combo (GAME_FORCE_NO_BLITTER, a non-blitter machine, or a TPA with no room
        # for the tables): the boot bind placed nothing, every blitter path declines by design and NOTHING
        # was swept. Say so instead of decoding an all-zero grid as a pass.
        print("DECLINED: tables unplaced — the boot bind placed no blitter tables "
              "(GAME_FORCE_NO_BLITTER, no blitter, or no room in the TPA), so no section was swept and "
              "nothing is pinned")
        sys.exit(1)
    return Report(fb)


def fine_x_of(skew_case):
    return (skew_case // OSH_INNER_PER_FINEX) % 16


def mutation_verdict(rep, mutate, quiet=False):
    """A mutation is CAUGHT only if the section it is supposed to break actually failed. Returns True if
    caught. Each mutation names that section (MUTATIONS): a broken register shows up in the skew grid,
    while the table's grow rule is invisible to every un-tabled grid and can only show up in the table
    section. A mutate build sweeps ONLY those two sections; check_non_vacuous has already enforced that
    the other two were skipped and left no case words behind, and that both sections still drew every
    case they are supposed to."""
    note, target = MUTATIONS[mutate]
    _, first, count, _, _, _ = rep.section(target)
    bad = rep.failures(first, count)
    if not bad:
        if not quiet:
            print(f"MUTATION MISSED ({note}): the '{target}' section is vacuous for this break")
        return False
    if not quiet:
        print(f"MUTATION CAUGHT ({note}): {len(bad)} '{target}' case(s) mismatch — the sweep exercises it")
        if target == "objshift skew":
            hit = {fine_x_of(i - first) for i in bad}
            print(f"  fine_x values with NO failing skew case: {sorted(set(range(16)) - hit)}")
    return True


def run_mutation(mutate, quiet=False):
    """One mutation leg: build, run, verify the sections are still non-vacuous, return
    (caught, {section: n_failing})."""
    rep = run_sweep(mutate)
    check_non_vacuous(rep, GRIDS_MUTATE)          # a mutate build runs the skew grid + the table section
    if not quiet:
        print_counts(rep)
    failing = {name: len(rep.failures(first, count)) for name, first, count, bit, _, _ in rep.grids
               if rep.ran(bit)}
    return mutation_verdict(rep, mutate, quiet), failing


def run_all_mutations():
    results = {}
    for mutate in sorted(MUTATIONS):
        print(f"--- mutation {mutate}: {MUTATIONS[mutate][0]} ---")
        results[mutate] = run_mutation(mutate)
    print("\nmutation coverage:")
    for mutate, (caught, failing) in results.items():
        note, target = MUTATIONS[mutate]
        counts = "  ".join(f"{name}={n}" for name, n in failing.items())
        print(f"  {mutate}  {'CAUGHT' if caught else 'MISSED':6s}  in '{target}'   failing: {counts}"
              f"   {note}")
    missed = [m for m, (caught, _) in results.items() if not caught]
    if missed:
        print(f"MUTATION COVERAGE INCOMPLETE: mutation(s) {missed} not caught")
        return 1
    print(f"MUTATION COVERAGE COMPLETE: all {len(results)} mutations caught")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", default="0", choices=["0", *(str(m) for m in MUTATIONS), "all"],
                    help="deliberately break one thing the skew route depends on and expect the section "
                         "that covers it to FAIL; 'all' loops every mutation and reports an aggregate table")
    args = ap.parse_args()

    if args.mutate == "all":
        sys.exit(run_all_mutations())
    if args.mutate != "0":
        caught, _ = run_mutation(int(args.mutate))
        sys.exit(0 if caught else 1)

    rep = run_sweep(0)
    check_non_vacuous(rep, GRIDS_ALL)
    print_bench(rep)
    print_counts(rep)
    bad = [i for name, first, count, bit, _, _ in rep.grids for i in rep.failures(first, count)]
    if bad:
        print(f"DIFF: {len(bad)} case(s) mismatch (indices {bad[:20]}{'...' if len(bad) > 20 else ''})")
        sys.exit(1)
    print(f"MATCH: all three blitter paths, the skew sprite table and the below-screen destinations are "
          f"byte-exact (framebuffer + overdraw tail) over all {rep.ncases} swept cases")


if __name__ == "__main__":
    main()
