"""dispatch_sweep.py — the object dispatcher's write reach over its BRANCH space (the companion
measurement to tools/reach_census.py; together they are what sized game_main.c's SCREEN_OVERDRAW).

reach_census.py measures the reach the game's own play produces. The dispatcher's destination
arithmetic, though, is also keyed on inputs a free drive may never move: view_flags (0/2/4/6 — it
scales the per-object vertical offset and selects the view-transform records), view_parity, p24_flag
(the start-gate handler) and the bonus window. This forces each combination on every staged frame and
re-measures, so a branch the drives cannot reach is measured rather than assumed.

SLICE-1 RESULT (1 MB memory diet, 2026-07-25): ~5,000 forced-branch runs found nothing deeper than the
census did — the object dispatcher never wrote past the visible screen at all. See reach_census.py's
header for the combined number the shipped 0x1000 tail is sized from.

Run on recreate's OWN drive states (bench_frame.mid_race_state, legs 0-4 x warmup depth) with the
CANDIDATE dispatcher writing into an isolated canaried buffer (px = buffer, draw_buf = 0 — how
render/atari/game_main.c binds it).

Usage:  python tools/reach_census.py --short   # once, to build the instrumented .so
        python tools/dispatch_sweep.py [--step 20]
"""
import argparse
import ctypes
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REMASTER = Path(__file__).resolve().parents[1]
PROBE_LIB = REMASTER / "build" / "libremaster_probe.so"
sys.path.insert(0, str(REMASTER / "test"))

if not PROBE_LIB.exists():
    sys.exit(f"{PROBE_LIB} is missing — run `python tools/reach_census.py --short` once; it owns the "
             f"one recipe that compiles the -DRM_REACH_PROBE candidate .so")

import adapter                                                    # noqa: E402
adapter.LIBREMASTER = PROBE_LIB
import bench_frame                                                # noqa: E402
import equiv                                                      # noqa: E402

SCREEN_BYTES = adapter.SCREEN_BYTES
PAD = 0x8000
WINDOW = 0x20000
VIEW_FLAGS = (0, 2, 4, 6)
PARITY = (0, 2)
P24 = (0x30, 0x31)
BONUS = (0, 0x3c)
GROUND_OFF_MUL = 0xdd      # player.c §8: ground_view_off = obj_scan_off = view_flags * this
REC_FIELDS = 10
F_ENGINE, F_PASS, F_DSTOFF, F_ROWS, F_MIN, F_MAX, F_CULLABLE, F_CULLED, F_NEG, F_X = range(REC_FIELDS)


def main(step):
    lib = equiv._lib()
    u8p = ctypes.POINTER(ctypes.c_uint8)
    lib.rm_reach_frame_begin.argtypes = [u8p, ctypes.c_int, ctypes.c_int32]
    lib.rm_reach_recs.restype = ctypes.POINTER(ctypes.c_int32)
    for fn in (lib.rm_reach_count, lib.rm_reach_neg_total, lib.rm_reach_neg_skipped):
        fn.restype = ctypes.c_int32
    skipped = 0                          # blits the probe SKIPPED past its bias — see reach_probe.c

    buf = bytearray(PAD + SCREEN_BYTES + WINDOW)
    view = np.frombuffer(memoryview(buf), dtype=np.uint8)
    pat = np.random.default_rng(7).integers(0, 256, size=len(buf), dtype=np.uint8)
    fb = adapter.Framebuffer.from_buffer(buf, PAD)
    px = ctypes.cast(ctypes.addressof(fb), u8p)

    combo_max = defaultdict(lambda: -1 << 40)
    combo_min = defaultdict(lambda: 1 << 40)
    natural = defaultdict(int)
    overall = [-1 << 40, 1 << 40, 0, 0, 0]      # max, min, blits, cullable, neg
    runs = 0

    for leg in range(5):
        for w in range(0, 601, step):
            image = bench_frame.mid_race_state(leg, w)
            natural[("view_flags", equiv._r16(image, adapter.A_view_flags))] += 1
            natural[("view_parity", equiv._r16(image, adapter.A_view_parity))] += 1
            natural[("bonus", equiv._r16(image, adapter.A_bonus_timer) != 0)] += 1
            natural[("p24", image[adapter.A_p24_flag])] += 1
            img = bytearray(image)
            cbuf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(img)
            _count, slots = equiv._objlist_passes(img)
            for vf in VIEW_FLAGS:
                for par in PARITY:
                    for p24 in P24:
                        for bon in BONUS:
                            ctx = equiv._objlist_ctx(lib, cbuf, 0)
                            ctx.px = px
                            ctx.view_flags = vf
                            # ground_view_off == obj_scan_off == view_flags * 0xdd (gameplay.c §8):
                            # the two are ONE derived value, so forcing view_flags without it builds a
                            # state the game never produces.
                            ctx.obj_scan_off = ctypes.c_int16(vf * GROUND_OFF_MUL).value
                            ctx.view_parity = par
                            ctx.p24_flag = p24
                            ctx.bonus_timer = bon
                            view[:] = pat
                            lib.rm_reach_frame_begin(px, 0, SCREEN_BYTES)
                            for p in slots:
                                if p is None:
                                    continue
                                lo, fo, outer, rec, col = p
                                lib.rm_draw_object_list(ctypes.byref(ctx), cbuf, lo, cbuf, fo,
                                                        outer, rec, col)
                            d = np.flatnonzero(view != pat)
                            n = int(lib.rm_reach_count())
                            if n:
                                rec_arr = np.ctypeslib.as_array(
                                    lib.rm_reach_recs(), shape=(n * REC_FIELDS,)
                                ).reshape(n, REC_FIELDS).astype(np.int64)
                                overall[2] += n
                                overall[3] += int(rec_arr[:, F_CULLABLE].sum())
                                # RM_REACH_NEG_* is a code, not a flag (reach_probe.c): any nonzero one
                                # is a blit whose first destination cursor started below the buffer.
                                overall[4] += int((rec_arr[:, F_NEG] != 0).sum())
                            key = (vf, par, p24, bon)
                            if d.size:
                                hi, lo_off = int(d[-1]) - PAD, int(d[0]) - PAD
                                combo_max[key] = max(combo_max[key], hi)
                                combo_min[key] = min(combo_min[key], lo_off)
                                overall[0] = max(overall[0], hi)
                                overall[1] = min(overall[1], lo_off)
                            skipped += int(lib.rm_reach_neg_skipped())
                            runs += 1
            del cbuf
        print(f"  leg {leg}: runs={runs} max_off={overall[0]} min_off={overall[1]}", flush=True)

    print(f"\ndispatcher runs: {runs}  (5 legs x warmup 0..600 step {step} x "
          f"{len(VIEW_FLAGS)}x{len(PARITY)}x{len(P24)}x{len(BONUS)} forced branches)")
    print(f"blits: {overall[2]}   flagged cullable (top row at/below {SCREEN_BYTES}): {overall[3]}"
          f"   negative first-cursor: {overall[4]}   SKIPPED past the probe bias: {skipped} "
          f"(nonzero = this run under-measured)")
    print(f"write window over ALL runs: [{overall[1]}, {overall[0]}]  -> "
          f"past-screen {max(0, overall[0] + 1 - SCREEN_BYTES)} bytes, "
          f"before-screen {max(0, -overall[1])} bytes")
    print("\nper forced (view_flags, parity, p24, bonus):")
    for k in sorted(combo_max):
        print(f"  {k}: [{combo_min[k]}, {combo_max[k]}]  past-screen "
              f"{max(0, combo_max[k] + 1 - SCREEN_BYTES)}")
    print("\nNATURAL values seen across the staged frames:")
    for k in sorted(natural, key=lambda t: (t[0], str(t[1]))):
        print(f"  {k[0]}={k[1]!r}: {natural[k]} frames")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=20)
    main(ap.parse_args().step)
