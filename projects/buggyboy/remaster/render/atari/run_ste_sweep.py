#!/usr/bin/env python3
"""run_ste_sweep.py — PERF30 C4: prove the STE colour/objshift2 blitter paths are byte-exact vs the CPU
engines across the whole case space (fine_x x width/base_cells x column/clip family x rows x colour).

Builds the GAME_STE_SWEEP variant and boots it on --machine ste --blitter. The PRG (src/blitter_sweep.c)
runs three grids — objshift2 pre-shift, objshift pre-shift, and the objshift HARDWARE-SKEW path
(src/blitter_skew.c) — against their CPU references and dumps a per-case mismatch grid to SCREEN.BIN:
word0 = case count, word1 = total mismatch, then one word per case (0 == byte-exact; clip cases the
blitter declines are logged 0 as the pinned CPU hybrid), then a SELF-DESCRIBING tail: the grid layout,
the BASE-handled counts, the BASE count each colour grid must reach, which grids ran, and the slice-1
cost bench. ALL case words zero == PASS.

A pass is not enough on its own: a grid that declined every case would also report zero mismatches. So
the run additionally fails unless each grid handled the number of BASE cases the report itself says it
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
        "bench_all_syn": 12, "bench_all_bin": 13, "bench_cpu": 14, "bench_declined": 15}

# SWEEP_GRID_* in blitter_sweep.c: which grids the build actually ran.
GRID_OBJSHIFT2, GRID_OSH_PRESHIFT, GRID_OSH_SKEW = 1, 2, 4
GRIDS_ALL = GRID_OBJSHIFT2 | GRID_OSH_PRESHIFT | GRID_OSH_SKEW

HZ200_CYCLES = 8_000_000 // 200                            # ST 68000 cycles per TOS _hz_200 tick

# The runner's MIRROR of blitter_sweep.c's grid dimensions. It is checked against word0 before anything
# is decoded, and nothing else is derived from it: the grid offsets and the non-vacuity expectation come
# from the report's own layout words, so a C-side dimension change fails here loudly instead of silently
# re-attributing cases to the wrong grid.
N_CASES_MIRROR, N_OSH_CASES_MIRROR = 3 * 16 * 12 * 3, 2 * 16 * 12 * 4
# Decode hint for the fine_x diagnostic only (columns x (colour,rows,stride) tuples — the colour grid's
# two innermost loops). Not a gate: it only labels which fine_x values a mutation failed at.
OSH_INNER_PER_FINEX = 12 * 4

# The mutations (RM_SKEW_MUT_* in include/blitter.h) the --mutate knob can build.
MUTATIONS = {1: "skew = fine_x + 1", 2: "FXSR forced on", 3: "endmask1 leading guard dropped",
             4: "endmask3 trailing guard dropped", 5: "plane 3 `& ~mask` special dropped"}


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
    """The decoded SCREEN.BIN report: grid layout, per-grid failures, handled counts, bench ticks."""

    def __init__(self, fb):
        self.fb = fb
        self.ncases = word(fb, 0)
        self.total = word(fb, 1)
        layout = N_CASES_MIRROR + 2 * N_OSH_CASES_MIRROR
        if self.ncases != layout:
            die(f"report layout mismatch: word0={self.ncases}, this runner mirrors {layout} — "
                f"blitter_sweep.c's grid dimensions moved and run_ste_sweep.py did not follow")
        self.n_cases2 = tail(fb, "n_cases2")
        self.n_osh = tail(fb, "n_cases_osh")
        if self.n_cases2 + 2 * self.n_osh != self.ncases:
            die(f"report tail disagrees with word0: {self.n_cases2} + 2*{self.n_osh} != {self.ncases}")
        self.expect_base = tail(fb, "expect_base")
        self.grids_run = tail(fb, "grids_run")
        # name, first case index, case count, grids_run bit, handled count, expected handled count
        self.grids = [("objshift2", 0, self.n_cases2, GRID_OBJSHIFT2, tail(fb, "handled2"), None),
                      ("objshift pre-shift", self.n_cases2, self.n_osh, GRID_OSH_PRESHIFT,
                       tail(fb, "handled_osh"), self.expect_base),
                      ("objshift skew", self.n_cases2 + self.n_osh, self.n_osh, GRID_OSH_SKEW,
                       tail(fb, "handled_skew"), self.expect_base)]

    def ran(self, bit):
        return bool(self.grids_run & bit)

    def failures(self, first, count):
        return [i for i in range(first, first + count) if word(self.fb, 2 + i) != 0]


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def check_non_vacuous(rep, expect_grids):
    """The gate that makes a zero mismatch mean something: every grid this build was supposed to run
    must have run, and must have DRAWN the BASE cases the report says the case space contains.

    The two colour grids share one case space and one family predicate, so they must agree with each
    other AND with the count the C side enumerates from that predicate. A skew path that quietly
    declined everything (or a clip test that drifted) shows up here as 0 handled against a non-zero
    expectation, even though every case word would still read 0."""
    if rep.grids_run != expect_grids:
        die(f"grids_run={rep.grids_run:#x}, expected {expect_grids:#x} — the build ran a different set "
            f"of grids than this run asked for")
    if rep.expect_base <= 0:
        die(f"the colour case space contains {rep.expect_base} BASE cases — the grid is vacuous")
    for name, first, count, bit, handled, expected in rep.grids:
        if not rep.ran(bit):
            stale = rep.failures(first, count)
            if stale:
                die(f"grid '{name}' was not run but its case words are non-zero ({len(stale)} of them)")
            continue
        if expected is not None and handled != expected:
            die(f"grid '{name}' handled {handled} BASE cases, expected {expected} — the grid is not "
                f"exercising the path it claims to pin")
        if handled <= 0:
            die(f"grid '{name}' handled no cases at all — vacuous")


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
    handled = "  ".join(f"{name}={h}" + ("" if rep.ran(bit) else " (skipped)")
                        for name, _, _, bit, h, _ in rep.grids)
    print(f"cases: {rep.ncases} (objshift2 + objshift pre-shift + objshift skew)   BASE blitter-drawn: "
          f"{handled}   expected BASE per colour grid: {rep.expect_base}"
          f"   total mismatch: {rep.total}")


def run_sweep(mutate):
    """Build (optionally mutated) and boot the sweep; return the decoded Report."""
    build(mutate)
    # 4800 cases x full-framebuffer memset/compare is a lot of emulated cycles — give it a generous
    # vblank budget + wall-clock so the sweep finishes and dumps (default 4000 vbls is far too short).
    fb = run_hatari.run(SWEEP_PRG, machine="ste", blitter=True, needs_data=True,
                        run_vbls=240000, timeout=900)[:SCREEN_BYTES]
    return Report(fb)


def fine_x_of(skew_case):
    return (skew_case // OSH_INNER_PER_FINEX) % 16


def mutation_verdict(rep, mutate, quiet=False):
    """A mutation is CAUGHT only if the skew grid failed AND nothing else did. Returns True if caught.

    A mutate build sweeps the skew grid ALONE (the mutation touches nothing the other two drive), so
    'nothing else failed' is checked as 'the other grids were skipped and left no case words behind' —
    check_non_vacuous already enforced both, and that the skew grid still drew every BASE case."""
    note = MUTATIONS[mutate]
    skew = next(g for g in rep.grids if g[3] == GRID_OSH_SKEW)
    bad = rep.failures(skew[1], skew[2])
    if not bad:
        if not quiet:
            print(f"MUTATION MISSED ({note}): the sweep is vacuous for this register")
        return False
    if not quiet:
        hit = {fine_x_of(i - skew[1]) for i in bad}
        print(f"MUTATION CAUGHT ({note}): {len(bad)} skew case(s) mismatch — the sweep exercises the path")
        print(f"  fine_x values with NO failing skew case: {sorted(set(range(16)) - hit)}")
    return True


def run_mutation(mutate, quiet=False):
    """One mutation leg: build, run, verify the grid is still non-vacuous, return (caught, n_failing)."""
    rep = run_sweep(mutate)
    check_non_vacuous(rep, GRID_OSH_SKEW)                  # the mutate build runs the skew grid alone
    if not quiet:
        print_counts(rep)
    skew = next(g for g in rep.grids if g[3] == GRID_OSH_SKEW)
    return mutation_verdict(rep, mutate, quiet), len(rep.failures(skew[1], skew[2]))


def run_all_mutations():
    results = {}
    for mutate in sorted(MUTATIONS):
        print(f"--- mutation {mutate}: {MUTATIONS[mutate]} ---")
        results[mutate] = run_mutation(mutate)
    print("\nmutation coverage:")
    for mutate, (caught, nbad) in results.items():
        print(f"  {mutate}  {'CAUGHT' if caught else 'MISSED':6s}  {nbad:4d} failing skew case(s)   "
              f"{MUTATIONS[mutate]}")
    missed = [m for m, (caught, _) in results.items() if not caught]
    if missed:
        print(f"MUTATION COVERAGE INCOMPLETE: mutation(s) {missed} not caught")
        return 1
    print(f"MUTATION COVERAGE COMPLETE: all {len(results)} mutations caught by the skew grid")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", default="0", choices=["0", *(str(m) for m in MUTATIONS), "all"],
                    help="build a deliberately broken skew register and expect the sweep to FAIL; "
                         "'all' loops every mutation and reports an aggregate table")
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
    print(f"MATCH: all three blitter paths are byte-exact over all {rep.ncases} swept cases")


if __name__ == "__main__":
    main()
