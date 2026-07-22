"""profile.py — cycle-per-PC profile of a remaster bench wrapper on the 68000 (Musashi).

Runs one (or more) of bench_main.c's bench_* entry points with the oracle's cycle histogram enabled
(emu.prof_*), then maps the per-PC cycle tallies back to functions via the ELF symbol table — the
"where do the cycles actually go" view the flat per-stage bench (tools/bench.py) cannot give.

Usage (from remaster/, after bench_build.sh):
    python tools/profile.py bench_objlist_fixed [bench_...]      # per-function breakdown
    python tools/profile.py --lines 8 bench_objlist_fixed        # + the 8 hottest PCs, annotated

The staging is bench.py's own (staged_mem + preps_for), so a profile always breaks down exactly the
run the corresponding bench row measured.
"""
import argparse
import subprocess
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
for p in ("oracle", "tools", "test", "render"):
    sys.path.insert(0, str(RECREATE / p))

import emu                                          # noqa: E402  Musashi cycle-accurate runner
import bench_frame                                  # noqa: E402  CPU_HZ

sys.path.insert(0, str(REMASTER / "tools"))
from bench import BENCH_ELF, staged_mem, preps_for   # noqa: E402

CPU_HZ = bench_frame.CPU_HZ


def _func_ranges(syms, limit):
    """[(start, end, name)] for every symbol, end = next symbol's start (the last one runs to
    `limit`, the end of the profiled PC window)."""
    entries = sorted((addr, name) for name, addr in syms.items())
    return [(addr, entries[i + 1][0] if i + 1 < len(entries) else limit, name)
            for i, (addr, name) in enumerate(entries)]


def profile(entry_labels, show_lines=0):
    syms, mem_t, sp, sentinel = staged_mem()

    for label in entry_labels:
        mem = bytearray(mem_t)
        # preps (staging + any table builds) run un-profiled, exactly as bench.py runs them
        for prep in preps_for(label):
            emu.run_bench(mem, syms[prep], arg0=0, sp=sp, sentinel=sentinel)

        emu.prof_reset()
        emu.prof_enable(True)
        r = emu.run_bench(mem, syms[label], arg0=0, sp=sp, sentinel=sentinel)
        emu.prof_enable(False)
        data = emu.prof_data()

        per_func = {}
        hot_pcs = {}
        for start, end, name in _func_ranges(syms, limit=len(data) * 2):
            cyc = sum(data[start // 2:end // 2])
            if not cyc:
                continue
            per_func[name] = cyc
            if show_lines:
                pcs = [(data[i], i * 2) for i in range(start // 2, min(end // 2, len(data)))]
                hot_pcs[name] = sorted(pcs, reverse=True)[:show_lines]

        total = r["cycles"]
        print(f"\n{label}: {total} cycles = {1000 * total / CPU_HZ:.2f} ms "
              f"({r['ninsns']} insns)")
        for name, cyc in sorted(per_func.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<32}{cyc:>10}  {1000 * cyc / CPU_HZ:>7.2f} ms  {100 * cyc / total:>5.1f}%")
            for cyc_pc, pc in hot_pcs.get(name, ()):
                if cyc_pc:
                    print(f"      pc {pc:#07x}  {cyc_pc:>9} cyc   {_disasm_line(pc)}")


_DISASM = {}


def _disasm_line(pc):
    """The objdump line at `pc` (cached one-shot disassembly of the whole ELF)."""
    if not _DISASM:
        out = subprocess.check_output(["m68k-elf-objdump", "-d", str(BENCH_ELF)], text=True)
        for line in out.splitlines():
            parts = line.split(":", 1)
            try:
                _DISASM[int(parts[0].strip(), 16)] = parts[1].strip()
            except (ValueError, IndexError):
                continue
    return _DISASM.get(pc, "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entries", nargs="+", help="bench_* symbol(s) from bench_main.c")
    ap.add_argument("--lines", type=int, default=0, metavar="N",
                    help="also print the N hottest PCs per function, objdump-annotated")
    args = ap.parse_args()
    profile(args.entries, show_lines=args.lines)


if __name__ == "__main__":
    main()
