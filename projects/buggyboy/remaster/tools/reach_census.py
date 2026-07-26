"""reach_census.py — how far past the visible screen does a composed frame write?

THE MEASUREMENT BEHIND SCREEN_OVERDRAW. render/atari/game_main.c gives each draw buffer a scratch tail
because clipped roadside-object draws can write past the visible 32000 bytes. That tail used to be
0x20000, sized from a "~102 KB" guess. This driver is what replaced the guess with a number, and it is
how to re-derive it if a draw stage ever changes.

SLICE-1 RESULT (1 MB memory diet, 2026-07-25), over 5,240 composed frames — the composed-frame
differential's whole drive fixture set, legs 0-4 flat out plus the slalom / bonus / marker-decay / flag
capture / leg-time-out drives:

    the three fine-x object engines never left the visible screen at all   (deepest write 31,039)
    render_road's bottom-row cell reached 8 bytes past it, on 81 frames    (offsets 32,000..32,007)

Its companion tools/dispatch_sweep.py forces the dispatcher branch space a free drive may never reach
(view_flags x view_parity x p24_flag x bonus) over ~5,000 more runs and finds nothing deeper. So the
shipped tail is 0x1000 — a 512x margin over the measured reach — with SCREEN_TAIL_LIVE = 8 naming the
part of it a frame legitimately writes. Both numbers live in game_main.c; test/adapter.py reads them
from there, and equiv.py's per-frame tail canary is the standing regression guard on them.

HOW IT MEASURES. It drives the remaster's REAL per-frame composition (equiv._ComposedScene ->
rm_draw_frame, the same call the shell makes) over those fixtures, and per frame records

  * the CANARY high-water mark: the deepest byte written past the visible 32000, and the deepest byte
    written BEFORE the framebuffer base (engine-agnostic — catches every writer, not just blit.c);
  * the PROBE census (tools/reach_probe.c): per roadside-object blit, its destination window, and
    whether its whole destination lies below the visible screen (dispatch-cullable).

It widens the composed scene's tail to MEASURE_WINDOW and switches equiv's standing tail guard off for
the run — this driver MEASURES the number that guard enforces, so guarding it here would be circular.

With --cull it also runs with the below-screen draws SKIPPED, so the visible 32000 bytes can be
byte-compared against recreate's g_draw_frame (compare_leg_drive already does that comparison for us).

Usage:  python tools/reach_census.py [--cull] [--every N] [--thresh BYTES] [--short] [--out FILE.npz]
        (the instrumented build/libremaster_probe.so is compiled automatically)
"""
import argparse
import ctypes
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REMASTER = Path(__file__).resolve().parents[1]
PROBE_LIB = REMASTER / "build" / "libremaster_probe.so"
sys.path.insert(0, str(REMASTER / "test"))


def build_probe():
    """Compile the instrumented candidate .so: the Makefile's own host recipe plus -DRM_REACH_PROBE and
    tools/reach_probe.c, which is in tools/ precisely so no build's src wildcard can pick it up."""
    src = sorted(p for p in (REMASTER / "src").glob("*.c")
                 if not p.name.startswith("blitter"))          # STE-only sources; see the Makefile
    cmd = ["clang", "-std=c11", "-O2", "-fPIC", "-Wall", "-Wextra",
           f"-I{REMASTER / 'include'}", f"-I{REMASTER / 'render' / 'atari' / 'build'}",
           "-DRM_REACH_PROBE", "-shared", *map(str, src), str(REMASTER / "tools" / "reach_probe.c"),
           "-o", str(PROBE_LIB)]
    PROBE_LIB.parent.mkdir(exist_ok=True)
    subprocess.run(cmd, check=True)


build_probe()

import adapter                                                    # noqa: E402
adapter.LIBREMASTER = PROBE_LIB                                    # the instrumented candidate

# The composed scene's tail is widened past the shipped SCREEN_OVERDRAW so a regression deeper than the
# shipped tail is still MEASURABLE rather than clipped at it, and equiv's standing tail guard is switched
# off with it (SCREEN_TAIL_LIVE == the whole window leaves an empty guarded slice). Both must be set
# before equiv imports, which is when it derives its tail constants.
MEASURE_WINDOW = 0x20000
adapter.SCREEN_OVERDRAW = MEASURE_WINDOW
adapter.SCREEN_TAIL_LIVE = MEASURE_WINDOW

import equiv                                                      # noqa: E402

SCREEN_BASE = adapter.SCREEN_BASE
SCREEN_BYTES = adapter.SCREEN_BYTES
TAIL0 = SCREEN_BASE + SCREEN_BYTES
ROW = 160

ACCEL, BRAKE, LEFT, RIGHT = 0x01, 0x02, 0x04, 0x08
ENGINES = ("objsprite", "objshift", "objshift2")
REC_FIELDS = 10           # int32s per RmReachRec (tools/reach_probe.c)
(F_ENGINE, F_PASS, F_DSTOFF, F_ROWS, F_MIN, F_MAX, F_CULLABLE, F_CULLED,
 F_NEG, F_X) = range(REC_FIELDS)


def drive_set(full=True):
    """(name, leg, inputs, image_tweak) — the composed-frame differential's fixtures (test_composed_
    frame.py), which between them cover legs 0-4 flat out (crashes fire on every leg), slalom crash
    drives, the 5-flag bonus window, an armed marker decay, a flag capture, and a leg-end time-out."""
    n = 600 if full else 120
    out = []
    for leg in range(5):
        out.append((f"flat_out.leg{leg}", leg, [ACCEL] * n, None))
    for leg in (2, 4):
        out.append((f"slalom.leg{leg}", leg,
                    [ACCEL | (LEFT if (f // 50) % 2 else RIGHT) for f in range(n)], None))
    for leg in (0, 2):
        out.append((f"bonus.leg{leg}", leg, [ACCEL] * min(n, 90),
                    lambda img: equiv._w16(img, adapter.A_bonus_timer, 0x3c)))
    for leg in (0, 2):
        def decay(img):
            equiv._w16(img, adapter.A_marker_decay, 1)
            equiv._w16(img, adapter.A_marker_decay + 2, 0x10)
            equiv._w16(img, adapter.A_marker_decay + 4, 0x1a0)
        out.append((f"decay.leg{leg}", leg, [ACCEL] * min(n, 90), decay))
    out.append(("flag_capture.leg2", 2, [ACCEL] * min(n, 400), None))
    for leg in (0, 1):
        out.append((f"timeout.leg{leg}", leg, [0] * min(n, 140),
                    lambda img: equiv._w16(img, adapter.A_time_left, 6)))
    return out


class Census:
    """Wraps _ComposedScene.draw: canary-fill, run the real composition, scan + harvest the probe."""

    def __init__(self, lib, cull, thresh):
        self.lib = lib
        self.cull = cull
        self.thresh = thresh
        self.rows = []            # one per composed frame
        self.engine_max = np.full(len(ENGINES), np.iinfo(np.int64).min, dtype=np.int64)
        self.pass_max = {}
        self.deep_examples = []
        self.neg_examples = []
        self.tail_hits = []
        self.view_flags_hist = {}
        self.view_flags_min = {}
        rng = np.random.default_rng(20260726)
        # ONE canary for the tail: equiv._ComposedScene.draw refills the tail from equiv._TAIL_CANARY
        # before every composition, so this driver replaces that pattern with a random one (uniform bytes
        # would hide a draw that wrote the same byte) rather than fighting it with a second fill.
        self.canary_tail = rng.integers(0, 256, size=MEASURE_WINDOW, dtype=np.uint8)
        equiv._TAIL_CANARY = self.canary_tail.tobytes()
        self.canary_head = rng.integers(0, 256, size=SCREEN_BASE, dtype=np.uint8)
        self._bind()

    def _bind(self):
        lib = self.lib
        u8p = ctypes.POINTER(ctypes.c_uint8)
        lib.rm_reach_frame_begin.argtypes = [u8p, ctypes.c_int, ctypes.c_int32]
        lib.rm_reach_frame_begin.restype = None
        for fn in (lib.rm_reach_count, lib.rm_reach_overflow, lib.rm_reach_rec_bytes,
                   lib.rm_reach_neg_total, lib.rm_reach_neg_skipped):
            fn.argtypes, fn.restype = [], ctypes.c_int32
        lib.rm_reach_recs.argtypes = []
        lib.rm_reach_recs.restype = ctypes.POINTER(ctypes.c_int32)
        assert lib.rm_reach_rec_bytes() == 4 * REC_FIELDS, "RmReachRec layout moved"

    def install(self, scene, tag):
        """Attach to one _ComposedScene (per drive) — its _fb_buf is the surface we measure."""
        self.scene = scene
        self.tag = tag
        self.frame = 0
        buf = np.frombuffer(memoryview(scene._fb_buf), dtype=np.uint8)
        assert buf.flags.writeable and buf.size == TAIL0 + MEASURE_WINDOW, "unexpected _fb_buf layout"
        self.buf = buf

    def draw(self, orig, scene, state):
        self.buf[:SCREEN_BASE] = self.canary_head          # the tail is refilled by equiv's own draw
        px = ctypes.cast(ctypes.addressof(scene.fb), ctypes.POINTER(ctypes.c_uint8))
        self.lib.rm_reach_frame_begin(px, 1 if self.cull else 0, self.thresh)
        out = orig(scene, state)
        self._harvest()
        self.frame += 1
        return out

    def _attribute(self):
        """Re-run each NON-object stage alone on a fresh canary, with the scene's own post-draw
        structs, to name the writer of a past-the-screen byte the object probe does not account for."""
        sc, lib, buf = self.scene, self.lib, self.buf
        out = []
        for tag, call in (("render_road", lambda: lib.rm_render_road(ctypes.byref(sc.road),
                                                                     ctypes.byref(sc.fb))),
                          ("road_scroll", lambda: lib.rm_blit_road_scroll(ctypes.byref(sc.scroll),
                                                                          sc.shifted,
                                                                          ctypes.byref(sc.fb))),
                          ("draw_hud", lambda: lib.rm_draw_hud(ctypes.byref(sc.hud),
                                                               ctypes.byref(sc.hud_assets),
                                                               ctypes.byref(sc.fb))),
                          ("ground", lambda: lib.rm_draw_ground(ctypes.byref(sc.ground),
                                                                ctypes.byref(sc.ground_assets),
                                                                ctypes.byref(sc.fb)))):
            buf[TAIL0:] = self.canary_tail
            call()
            d = np.flatnonzero(buf[TAIL0:] != self.canary_tail)
            if d.size:
                out.append((tag, int(d[-1]) + 1))
        return out

    def _harvest(self):
        buf = self.buf
        d = np.flatnonzero(buf[TAIL0:] != self.canary_tail)
        tail_reach = int(d[-1]) + 1 if d.size else 0            # bytes written past offset 32000
        dh = np.flatnonzero(buf[:SCREEN_BASE] != self.canary_head)
        head_reach = SCREEN_BASE - int(dh[0]) if dh.size else 0  # bytes written before offset 0

        n = int(self.lib.rm_reach_count())
        if n:
            flat = np.ctypeslib.as_array(self.lib.rm_reach_recs(), shape=(n * REC_FIELDS,))
            rec = flat.reshape(n, REC_FIELDS).astype(np.int64)
        else:
            rec = np.zeros((0, REC_FIELDS), dtype=np.int64)
        drew = rec[rec[:, F_MAX] > np.iinfo(np.int32).min] if n else rec
        pmax = int(drew[:, F_MAX].max()) if drew.size else -1
        pmin = int(drew[:, F_MIN].min()) if drew.size else 0
        keep = drew[drew[:, F_CULLABLE] == 0] if drew.size else drew
        kmax = int(keep[:, F_MAX].max()) if keep.size else -1
        for e in range(len(ENGINES)):
            sel = drew[drew[:, F_ENGINE] == e] if drew.size else drew
            if sel.size:
                self.engine_max[e] = max(self.engine_max[e], int(sel[:, F_MAX].max()))
        if drew.size:
            for p in np.unique(drew[:, F_PASS]):
                sel = drew[drew[:, F_PASS] == p]
                self.pass_max[int(p)] = max(self.pass_max.get(int(p), -1), int(sel[:, F_MAX].max()))

        vf = int(self.scene.objlist.view_flags)
        self.view_flags_hist[vf] = self.view_flags_hist.get(vf, 0) + 1
        self.view_flags_min[vf] = min(self.view_flags_min.get(vf, 1 << 40), pmin)
        # RM_REACH_NEG_* is a code, not a flag: any nonzero one is a blit whose first cursor started
        # below the buffer (3 = deeper than the probe's bias, so the draw was SKIPPED — see reach_probe.c).
        neg = int((rec[:, F_NEG] != 0).sum()) if n else 0
        self.rows.append((self.tag, self.frame, tail_reach, head_reach, n,
                          int(rec[:, F_CULLABLE].sum()) if n else 0,
                          int(rec[:, F_CULLED].sum()) if n else 0,
                          pmax, pmin, kmax, int(self.lib.rm_reach_overflow()), neg,
                          int(self.lib.rm_reach_neg_skipped())))
        if neg and len(self.neg_examples) < 25:
            self.neg_examples.append((self.tag, self.frame, rec[rec[:, F_NEG] != 0].tolist()))
        if tail_reach > 0 and len(self.tail_hits) < 12:
            self.tail_hits.append((self.tag, self.frame, tail_reach,
                                   (d + SCREEN_BYTES).tolist()[:16], self._attribute()))
        if tail_reach > 0 and len(self.deep_examples) < 40 and tail_reach > 40000:
            worst = drew[np.argsort(drew[:, F_MAX])[-3:]] if drew.size else drew
            self.deep_examples.append((self.tag, self.frame, tail_reach, worst.tolist()))


def run(cull, thresh, every, full, out_path):
    lib = equiv._lib()
    census = Census(lib, cull, thresh)
    orig_draw = equiv._ComposedScene.draw

    def draw(scene, state):
        return census.draw(orig_draw, scene, state)
    equiv._ComposedScene.draw = draw

    def sampler(frame, is_event):
        return is_event or frame % every == 0

    total_composed = total_diffs = 0
    t0 = time.time()
    for name, leg, inputs, tweak in drive_set(full):
        image = equiv.leg_start_background(leg)
        if tweak is not None:
            tweak(image)
        # install() needs the scene, which compare_leg_drive builds internally — hook _ComposedScene
        # construction for this drive.
        orig_init = equiv._ComposedScene.__init__

        def init(scene, *a, _name=name, **k):
            orig_init(scene, *a, **k)
            census.install(scene, _name)
        equiv._ComposedScene.__init__ = init
        try:
            mism, stats = equiv.compare_leg_drive(lib, image, inputs, compose=sampler)
        finally:
            equiv._ComposedScene.__init__ = orig_init
        comp = [m for m in mism if isinstance(m[1], str) and m[1].startswith("composed_fb")]
        total_composed += stats["composed_checked"]
        total_diffs += stats["composed_diffs"]
        print(f"  {name:22s} composed={stats['composed_checked']:5d} diffs={stats['composed_diffs']:4d} "
              f"crashes={stats['armed']:3d} wraps={stats['wraps']:4d} leg_over={stats['leg_over']}"
              f"  [{time.time() - t0:6.1f}s]", flush=True)
        if comp:
            print(f"      first: {comp[0]}", flush=True)

    equiv._ComposedScene.draw = orig_draw
    arr = np.array([r[1:] for r in census.rows], dtype=np.int64)
    tags = np.array([r[0] for r in census.rows])
    np.savez(out_path, rows=arr, tags=tags,
             engine_max=census.engine_max, cull=int(cull), thresh=thresh,
             composed=total_composed, diffs=total_diffs,
             pass_max=np.array(sorted(census.pass_max.items()), dtype=np.int64))
    print(f"\ncull={cull} thresh={thresh}: composed frames={total_composed} composed_diffs={total_diffs}")
    print(f"engine max_off: " + ", ".join(f"{ENGINES[i]}={int(v)}" for i, v in enumerate(census.engine_max)))
    print(f"pass max_off:   {sorted(census.pass_max.items())}")
    print(f"deepest write past the visible screen (whole composed frame): {int(arr[:, 1].max())} bytes "
          f"on {int((arr[:, 1] > 0).sum())} of {len(arr)} frames")
    print(f"saved -> {out_path}")
    for ex in census.deep_examples[:5]:
        print(f"  deep {ex[0]} f{ex[1]} tail_reach={ex[2]} worst_recs={ex[3]}")
    for h in census.tail_hits[:8]:
        print(f"  tail-hit {h[0]} f{h[1]} reach={h[2]} offsets={h[3]} attributed={h[4]}")
    print(f"natural view_flags: " + ", ".join(
        f"{k}:{v} frames (min_off {census.view_flags_min[k]})" for k, v in sorted(census.view_flags_hist.items())))
    print(f"negative-offset blits: {int(arr[:, 10].sum())} on {int((arr[:, 10] > 0).sum())} frames; "
          f"SKIPPED past the probe bias: {int(arr[:, 11].max())} (nonzero = the run under-measured)")
    for ex in census.neg_examples[:6]:
        print(f"  neg {ex[0]} f{ex[1]} recs={ex[2]}")
    return census


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cull", action="store_true")
    ap.add_argument("--thresh", type=int, default=SCREEN_BYTES + ROW)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--short", action="store_true")
    ap.add_argument("--out", default="census.npz")
    a = ap.parse_args()
    run(a.cull, a.thresh, a.every, not a.short, a.out)
