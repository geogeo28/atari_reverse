"""test_asm_blit.py — Musashi-executed differential: the hand-written m68k objshift2 core
(src/asm/objshift2.S, PERF30 A3) must be byte-for-byte identical to the C reference rm_blit_objshift2
(src/blit.c) on every fuzz case.

The host equivalence suite (test/test_blit_engines.py) proves the C reference matches recreate's verified
oracle, but it links C only and cannot execute m68k asm. This suite closes that gap: it runs each case
TWICE on the cross-compiled bench.elf under the cycle-accurate Musashi 68000 — once through the C entry
(bench_objsh2_run_c), once through the asm entry (bench_objsh2_run_asm) — and byte-compares the drawn
region. A one-byte divergence on any case fails the suite (mutation-proven, PERF30 A3 note).

Shape (F12): the harness is driven by an engine DESCRIPTOR (wrapper symbols, staged buffers, the param-
block packer, its case table) so phase 2's rm_blit_objshift asm core is a second descriptor + case
table, not a parallel harness class. The run wrappers unpack a param block (bench_main.c Objsh2Args):
emu.run_bench passes a single arg0, so the test pokes the args + noise buffers into the flat image, then
calls a zero-arg wrapper that reads the block and invokes one engine. dst/src are absolute addresses of
the bench's staged buffers (objsh2_dst / objsh2_src), started mid-buffer so the up-walk (0x2a rows * 160)
and the per-row source rewind stay in bounds.

The compare is bracketed (F5 canary): as well as the dst window it checks GUARD bytes on either side of
the window and the whole src buffer are IDENTICAL between the C and asm runs — a guard divergence is a
wild store past the window, a src divergence a store into the read-only source. And a positive control
(F4): the known base-drawing cases MUST change dst from the pre-blit noise, so a dead harness (broken
param block / renamed wrapper) that draws nothing fails loudly instead of false-greening C==asm.

Cases mirror test_blit_engines.py's objshift2 fuzz and widen it: all three width families (0/1/2 — the
direct host fuzz only pins width_idx 0, the others go through the dispatcher), every fine-x, the
LEFT/RIGHT clip-ladder columns + off-edge both sides + the base span, several row counts, PLUS a small
bit-15-set rows_m1 list (F1: the C draws (int16)rows_m1+1 <= 0 rows = nothing; the asm must match and not
run its 16-bit dbra away). 1740 cases, sharded across xdist workers by `chunk` like the other fuzz suites.

The shared helpers are imported, not copied (F7): _x_for from test_blit_engines (the C fuzz's x decoder)
and _syms/_load_flat/BENCH_ELF/BENCH_BIN from tools/bench.py (the flat-image loader).

Requires the m68k bench.elf (bash render/atari/bench_build.sh); make test builds it first. If it is
absent the suite FAILS with that hint rather than skipping — a silent skip would hide a broken asm.
"""
import struct
import sys
from pathlib import Path

import pytest

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE / "oracle"))       # emu (Musashi runner)
sys.path.insert(0, str(REMASTER / "tools"))        # bench: the flat-image loader (one source of truth, F7)

from bench import BENCH_ELF, BENCH_BIN, _syms, _load_flat   # noqa: E402
from test_blit_engines import _x_for                        # noqa: E402  the C fuzz's x decoder (F7)

BUILD_HINT = "bench.elf missing — build it: bash render/atari/bench_build.sh (make test builds it)"

FUZZ_CHUNKS = 8
DST_OFF = 0x2000               # start the cursors mid-buffer (bench_main.c OBJSH2_BUF_MID)
BUF_BYTES = 0x4000             # bench_main.c OBJSH2_BUF_BYTES (whole diff region)
GUARD = 0x40                   # canary bytes bracketing the dst window (F5): stores here = out-of-window

# The clip/edge/base column set (signed multiples of 8): far-left off-edge, the LEFT ladder rungs, the
# base span, the width ceilings, the RIGHT ladder, and off-right. A superset of test_blit_engines.py's
# objshift2 columns (adds 0x78), exercised across all three width families here.
COLUMNS = (-32, -24, -16, -8, 0x0, 0x40, 0x78, 0x80, 0x88, 0x90, 0x98, 0xa0)
ROWS_M1 = (0, 3, 0x2a)         # single row, a few rows, and the fixed-pass full 0x2a
WIDTH_IDX = (0, 1, 2)          # base ceiling 0x88 / 0x90 / 0x98
BASE_DRAW_COLS = (0x0, 0x40)   # columns that are BASE (on-screen, drawing) for every width family — F4

BASE_CASES = [(wi, fx, col, rows_m1)
              for wi in WIDTH_IDX
              for fx in range(16)
              for col in COLUMNS
              for rows_m1 in ROWS_M1]

# F1: bit-15-set rows_m1 — the C computes rows = (int16)rows_m1 + 1 and draws NOTHING when that is <= 0;
# the asm guards it with a `bmi` so its 16-bit dbra does not loop up to 65536 times. A dedicated small
# list over a left-clip / base / right-clip column and two fine-x (keep the total case count sane).
HIGH_ROW_COLS = (-8, 0x40, 0x90)
HIGH_ROWS_M1 = (0xffff, 0x8000)
HIGH_ROW_CASES = [(0, fx, col, rows_m1)
                  for fx in (0, 7)
                  for col in HIGH_ROW_COLS
                  for rows_m1 in HIGH_ROWS_M1]

CASES = BASE_CASES + HIGH_ROW_CASES


def _pack_objsh2(dst, src, x, rows_m1, width_idx):
    """Objsh2Args (bench_main.c): dst, dst_off, src, src_off (u32); x, rows_m1 (u16); width_idx (i32)."""
    return struct.pack(">IIIIHHi", dst, DST_OFF, src, DST_OFF,
                       x & 0xffff, rows_m1 & 0xffff, width_idx)


# Engine descriptor (F12). Phase 2 adds a second dict (its wrappers + buffers + packer + case table),
# not a parallel _Harness — the harness below is engine-agnostic.
OBJSHIFT2 = {
    "name":     "objshift2",
    "run_c":    "bench_objsh2_run_c",
    "run_asm":  "bench_objsh2_run_asm",
    "dst_sym":  "objsh2_dst",
    "src_sym":  "objsh2_src",
    "args_sym": "objsh2_args",
    "pack":     _pack_objsh2,
    "cases":    CASES,
}


class _Harness:
    """Loads bench.elf once per (worker, engine); runs one case through an engine wrapper via the param
    block, on a fresh copy of the image, and returns the whole memory for the caller to slice."""

    def __init__(self, desc):
        import emu
        self.emu = emu
        self.syms = _syms(BENCH_ELF)
        self.mem_t, self.sp, self.sentinel = _load_flat(BENCH_BIN, self.syms)
        self.dst = self.syms[desc["dst_sym"]]
        self.src = self.syms[desc["src_sym"]]
        self.args = self.syms[desc["args_sym"]]

    def run(self, wrapper, blk, noise_dst, noise_src):
        mem = bytearray(self.mem_t)
        mem[self.dst:self.dst + BUF_BYTES] = noise_dst
        mem[self.src:self.src + BUF_BYTES] = noise_src
        mem[self.args:self.args + len(blk)] = blk
        self.emu.run_bench(mem, self.syms[wrapper], arg0=0, sp=self.sp, sentinel=self.sentinel)
        return mem

    def compare_region(self, mem):
        """The slice the C and asm runs must agree on (F5): the dst window bracketed by GUARD bytes on
        each side + the whole src buffer. Any difference outside the window = a wild asm store."""
        return bytes(mem[self.dst - GUARD:self.dst + BUF_BYTES + GUARD]) + \
            bytes(mem[self.src:self.src + BUF_BYTES])

    def dst_window(self, mem):
        return bytes(mem[self.dst:self.dst + BUF_BYTES])


_HARNESSES = {}


def _harness(desc):
    if not (BENCH_ELF.exists() and BENCH_BIN.exists()):
        pytest.fail(BUILD_HINT)
    h = _HARNESSES.get(desc["name"])
    if h is None:
        h = _HARNESSES[desc["name"]] = _Harness(desc)
    return h


def _noise(seed, n):
    import random
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(n))


def _draws_zero_rows(rows_m1):
    """The C draws nothing when (int16)rows_m1 + 1 <= 0, i.e. when bit 15 of rows_m1 is set."""
    return bool(rows_m1 & 0x8000)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_objshift2_asm_matches_c(chunk, capsys):
    """Every objshift2 case, C entry vs asm entry, byte-exact over the bracketed dst window + src."""
    desc = OBJSHIFT2
    h = _harness(desc)
    bad = []
    dead = []
    for idx, (wi, fx, col, rows_m1) in enumerate(desc["cases"]):
        if idx % FUZZ_CHUNKS != chunk:
            continue
        # Same noise into dst+src for both runs; a distinct seed per case exercises real mask/pixel bits.
        nd = _noise(idx * 131 + 7, BUF_BYTES)
        ns = _noise(idx * 977 + 13, BUF_BYTES)
        x = _x_for(col, fx)
        blk = desc["pack"](h.dst, h.src, x, rows_m1, wi)
        cm = h.run(desc["run_c"], blk, nd, ns)
        am = h.run(desc["run_asm"], blk, nd, ns)
        wc, wa = h.compare_region(cm), h.compare_region(am)
        if wc != wa:
            diff = sum(1 for i in range(len(wc)) if wc[i] != wa[i])
            bad.append((wi, fx, col, rows_m1, diff))
        # F4 positive control: a base-drawing case MUST change dst from the noise baseline. If it didn't,
        # the harness is dead (broken param block / renamed wrapper) and C==asm would false-green.
        if col in BASE_DRAW_COLS and not _draws_zero_rows(rows_m1):
            if h.dst_window(cm) == nd:
                dead.append((wi, fx, col, rows_m1))
    with capsys.disabled():
        n = sum(1 for i in range(len(desc["cases"])) if i % FUZZ_CHUNKS == chunk)
        print(f"  objshift2 asm chunk {chunk}: {len(bad)} mismatches, {len(dead)} dead ({n} cases)")
    assert not dead, f"positive control: C drew nothing on a base case (dead harness?): {dead[:8]}"
    assert not bad, f"asm diverges from C reference: {bad[:8]}"
