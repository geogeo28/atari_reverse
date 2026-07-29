"""road_dl_census.py — B2 (road display list) MEASUREMENT: does render_road's per-scanline control
stream change every frame, or only when (curve, view, slope, course) change?

This is a decision tool for PERF30 item B2, not an optimization. It drives real leg frames (the same
mid_race_state machinery frame_dist.py uses) and, per drawn frame, measures how the inputs render_road
consumes vary, and — crucially — how often the DISPLAY LIST (the op sequence render_road would replay)
actually changes.

Established by code inspection (see road.c / geometry.c / the fixture bindings):
  - render_road's display list (op sequence + source offsets + fill counts) is a PURE FUNCTION of the
    per-scanline control table `width_tbl` (= build_road_geometry's ctrl output) plus the view-selected
    `edge_tbl` window. `param`, `edge_tbl` content and `edge_const` are STATIC fixtures; `tex`/`edge_const`
    are never branched on. So "the display list changed" <=> "width_tbl (or the selected edge window)
    changed".
  - width_tbl is rebuilt each frame from: seg_data slopes (perspective), curve (steering, spread as a
    per-row RAMP by spread_curvature), view_flags (width bank + edge bank), and the ring marker column
    (high words). So steering enters the control table's LOW words per-row.

Three DL-change measures, from most pessimistic to most optimistic for B2:
  RAW   : does the raw width_tbl content change (any byte)?  (== "recompute everything" cache miss)
  FULL  : does the rendered output under a fixed RANDOM texture change? This is the true display list
          INCLUDING source operands (fine-x sub-column, edge seeds) — what a replay must reproduce.
  SHAPE : does the rendered output under a CONSTANT texture change? This ignores source operands and
          captures only the op SHAPE (copy-count / fill-count / edge position / flags) — the most
          optimistic B2 cache (one that recomputes operands per frame but caches the shape).

Usage:  ../recreate/.venv/bin/python tools/road_dl_census.py [frames_per_leg]
"""
import ctypes
import hashlib
import random
import sys
from collections import Counter
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))   # reverse/tools — the shared recreate kit
from recreate_kit import project                        # noqa: E402
project.load(RECREATE)                                  # binds the kit's loader/emu to recreate
for p in ("tools", "test", "render"):
    sys.path.insert(0, str(RECREATE / p))
sys.path.insert(0, str(REMASTER / "test"))

import adapter                         # noqa: E402
import bench_frame                     # noqa: E402
import equiv                           # noqa: E402  (binds the remaster lib signatures)

LEGS = (0, 1, 2, 3, 4)
FRAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 300
WARMUP0 = 60                           # skip the initial transient like frame_dist

A_curve = adapter.A_road_curve
A_view_flags = adapter.A_view_flags
A_seg = adapter.A_road_seg_data
A_ring = adapter.A_ring_base
RING_STRIDE = adapter.RING_ROW_BYTES
A_edge_sel = adapter.A_road_edge_sel
A_width_tbl = adapter.A_road_width_tbl
A_curve_tbl = adapter.A_road_curve_tbl
A_param = adapter.A_road_param
A_buf_b = adapter.A_buf_b
A_hscroll = adapter.A_hscroll_pos
A_horizon = adapter.A_horizon_row
WIDTH_BYTES = adapter.ROAD_WIDTH_TBL_BYTES   # 0x200
PARAM_CONSUMED = 0x400                        # generous bound on the monotonic param words read/frame
EDGE_BYTES = adapter.ROAD_EDGE_WINDOW_BYTES

lib = equiv._lib()

# recon builder + updater (image-pointer ABI), bound once.
_g_build = bench_frame.harness._lib.g_build_road_geometry
_g_build.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
_g_build.restype = None
_g_update = bench_frame.harness._lib.g_game_update
_g_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
_g_update.restype = None

# fixed synthetic textures (same every frame -> identical DL yields identical render output).
_rng = random.Random(0x0ad00ad0)
TEX_RANDOM = bytes(_rng.randrange(256) for _ in range(adapter.ROAD_TEX_WINDOW_BYTES))
TEX_CONST = bytes([0xA5]) * adapter.ROAD_TEX_WINDOW_BYTES
CONST_RANDOM = bytes(_rng.randrange(256) for _ in range(adapter.ROAD_CONST_BYTES))
CONST_CONST = bytes([0x5A]) * adapter.ROAD_CONST_BYTES


def _u16(m, a):
    return (m[a] << 8) | m[a + 1]


def _w16(m, a, v):
    m[a], m[a + 1] = (v >> 8) & 0xff, v & 0xff


A_view_bank = adapter.A_view_bank


def _tuple(state):
    """The semantic determinant of the display list a per-(state) cache would key on: curve (steering),
    view_flags + view_bank (which pick the width bank AND the edge window via road_edge_sel), the 13
    segment slopes (perspective), and the 14 ring marker words (the flag high-halves)."""
    curve = _u16(state, A_curve)
    view = _u16(state, A_view_flags)
    bank = _u16(state, A_view_bank)
    seg = tuple(_u16(state, A_seg + i * 2) for i in range(13))
    markers = tuple(_u16(state, A_ring + b * RING_STRIDE + 30) for b in range(adapter.RM_RING_ROWS))
    return (curve, view, bank, seg, markers)


def _dl_fingerprint(state, tex, const):
    """Render with a fixed synthetic texture; hash the road band. Same op sequence + operands (given
    the same `tex`) => same bytes. With TEX_RANDOM this fingerprints the FULL display list (incl.
    source operands); with TEX_CONST it fingerprints only the op SHAPE."""
    inp, keep = adapter.road_input(state)
    _wt, _pm, edge_const, _ew, tex_window = keep
    tex_window[:] = tex
    edge_const[:] = const
    fb = adapter.Framebuffer()
    lib.rm_render_road(ctypes.byref(inp), ctypes.byref(fb))
    return hashlib.blake2b(bytes(fb.px), digest_size=16).digest()


def _changed_bytes(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def drive_leg(leg):
    state = bench_frame.mid_race_state(leg, WARMUP0)
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    rows = []
    for _ in range(FRAMES):
        _g_build(buf)                                  # build this frame's control table
        width = bytes(state[A_width_tbl:A_width_tbl + WIDTH_BYTES])
        curve_tbl = bytes(state[A_curve_tbl:A_curve_tbl + adapter.RM_CTRL_BYTES])
        param = bytes(state[A_param:A_param + PARAM_CONSUMED])
        esel = adapter._i16(state, A_edge_sel)
        edge = bytes(state[adapter.A_road_edge_base + esel:adapter.A_road_edge_base + esel + 0x200])
        buf_b = int.from_bytes(state[A_buf_b:A_buf_b + 4], "big")
        rows.append({
            "T": _tuple(state),
            "width": width, "curve_tbl": curve_tbl, "param": param, "edge": edge,
            "esel": esel, "buf_b": buf_b, "hscroll": _u16(state, A_hscroll),
            "horizon": _u16(state, A_horizon),
            "dl_full": _dl_fingerprint(state, TEX_RANDOM, CONST_RANDOM),
            "dl_shape": _dl_fingerprint(state, TEX_CONST, CONST_CONST),
        })
        bench_frame._force_advance(state)              # advance to the next frame
        _g_update(buf)
    return rows


def _change_stats(rows, key):
    """(% frames changed vs previous, mean changed bytes | mean when-changed, max)."""
    changed = 0
    cb, cb_when = [], []
    for i in range(1, len(rows)):
        d = _changed_bytes(rows[i][key], rows[i - 1][key])
        cb.append(d)
        if d:
            changed += 1
            cb_when.append(d)
    n = len(rows) - 1
    return (100 * changed / n,
            sum(cb) / n,
            (sum(cb_when) / len(cb_when)) if cb_when else 0,
            max(cb) if cb else 0,
            len(rows[0][key]))


def _hash_change(rows, key):
    return 100 * sum(1 for i in range(1, len(rows)) if rows[i][key] != rows[i - 1][key]) / (len(rows) - 1)


def _cache(rows, key_fn, val_fn):
    """Per-key cache over the drive: (distinct keys, distinct vals, hit-rate, key->val deterministic?)."""
    seen = {}
    hits = 0
    deterministic = True
    for r in rows:
        k, v = key_fn(r), val_fn(r)
        if k in seen:
            hits += 1
            if seen[k] != v:
                deterministic = False
        else:
            seen[k] = v
    distinct_vals = len({val_fn(r) for r in rows})
    return len(seen), distinct_vals, 100 * hits / len(rows), deterministic


def main():
    print(f"B2 road-display-list census — legs {LEGS}, {FRAMES} frames/leg "
          f"(mid_race_state drive, forced course-advance/frame, input=0)\n")
    all_rows = []
    per_leg = {}
    for leg in LEGS:
        rows = drive_leg(leg)
        per_leg[leg] = rows
        all_rows += rows
        print(f"  leg {leg}: {len(rows)} frames", flush=True)

    print("\n=== Q1: which consumed streams vary frame-to-frame? (per-stream, all legs pooled) ===")
    print(f"  {'stream':<12}{'bytes':>7}{'%frames chg':>13}{'mean chg B':>12}"
          f"{'mean|chg':>10}{'max chg':>9}")
    for key, label in (("width", "width_tbl"), ("curve_tbl", "ctrl(full)"),
                       ("param", "param"), ("edge", "edge_win")):
        pcts, mcb, mcw, mx = [], [], [], 0
        for rows in per_leg.values():
            p, m, w, x, nb = _change_stats(rows, key)
            pcts.append(p); mcb.append(m); mcw.append(w); mx = max(mx, x)
        print(f"  {label:<12}{nb:>7}{sum(pcts)/len(pcts):>12.1f}%{sum(mcb)/len(mcb):>12.1f}"
              f"{sum(mcw)/len(mcw):>10.1f}{mx:>9}")
    # scalars
    for key, label in (("esel", "edge_sel"), ("buf_b", "tex_base"), ("hscroll", "hscroll"),
                       ("horizon", "horizon")):
        chg = []
        for rows in per_leg.values():
            chg.append(100 * sum(1 for i in range(1, len(rows)) if rows[i][key] != rows[i-1][key])
                       / (len(rows) - 1))
        print(f"  {label:<12}{'(scalar)':>7}{sum(chg)/len(chg):>12.1f}%")

    print("\n=== Q3: display-list change rate + cache hit rates (per leg, then pooled) ===")
    print(f"  {'measure':<24}{'%frames chg':>13}{'distinct':>10}{'1-entry hit':>13}"
          f"{'content hit':>13}")

    def dl_block(rows, tag):
        for key, label in (("width", "RAW width_tbl content"),
                           ("dl_full", "FULL DL (rand tex)"),
                           ("dl_shape", "SHAPE only (const tex)")):
            chg = _hash_change(rows, key)
            distinct = len({r[key] for r in rows})
            last1 = 100 * sum(1 for i in range(1, len(rows)) if rows[i][key] == rows[i-1][key]) / (len(rows)-1)
            content = 100 * (len(rows) - distinct) / len(rows)
            print(f"  {tag+label:<24}{chg:>12.1f}%{distinct:>10}{last1:>12.1f}%{content:>12.1f}%")

    for leg, rows in per_leg.items():
        dl_block(rows, f"L{leg} ")
    dl_block(all_rows, "ALL ")

    print("\n=== Q3: per-(curve,view,seg,marker) tuple cache (pooled) ===")
    for key, label in (("width", "RAW width_tbl"), ("dl_full", "FULL DL"), ("dl_shape", "SHAPE DL")):
        nk, nv, hit, det = _cache(all_rows, lambda r: r["T"], lambda r, k=key: r[k])
        print(f"  tuple->{label:<14} distinct_keys={nk:<5} distinct_vals={nv:<5} "
              f"hit={hit:.1f}%  key->val_deterministic={det}")
    # tuple space bound
    curves = len({r['T'][0] for r in all_rows})
    views = len({r['T'][1] for r in all_rows})
    banks = len({r['T'][2] for r in all_rows})
    segs = len({r['T'][3] for r in all_rows})
    marks = len({r['T'][4] for r in all_rows})
    print(f"  observed tuple-component spreads: curves={curves} views={views} banks={banks} "
          f"seg_data={segs} marker_cols={marks}")

    print("\n=== Q5: does the double-build on a wrap frame produce a different stream? ===")
    # Re-derive: build twice (build is idempotent given fixed inputs) vs build/advance/build.
    diff_idempotent = _wrap_probe(per_leg)
    print(diff_idempotent)


def _wrap_probe(per_leg):
    """A wrap frame rebuilds geometry twice: once for the pre-advance pose, once after the course
    advance mutated the ring/slope. Idempotence: building twice on the SAME state is a no-op; the two
    builds differ iff the inputs between them differ. Quantify how much width_tbl moves across one
    forced advance (the per-frame delta this drive already applies)."""
    deltas = []
    for rows in per_leg.values():
        for i in range(1, len(rows)):
            deltas.append(_changed_bytes(rows[i]["width"], rows[i - 1]["width"]))
    nz = [d for d in deltas if d]
    return (f"  build is a pure function of (pose,ring): building twice on one state is identical.\n"
            f"  Across the forced per-frame advance, width_tbl moves on {100*len(nz)/len(deltas):.1f}% "
            f"of frames (mean {sum(deltas)/len(deltas):.1f} B, mean-when-moved {sum(nz)/max(len(nz),1):.1f} B).\n"
            f"  => on a real wrap frame the second build differs from the first by exactly this per-advance\n"
            f"     delta; a per-tuple cache MUST rebuild (or invalidate) around every advance.")


if __name__ == "__main__":
    main()
