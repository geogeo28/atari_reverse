"""test_asm_road.py — Musashi-executed differential: the hand-written m68k render_road band cores
(src/asm/road_band.S — PERF30 road-asm slices 1-3 port ALL of render_road's writers: band D, band B, then
bands C-near/C-far and band A) must be byte-for-byte identical to their C references (rr_band_?_c in
src/road.c) on every staged road frame.

The host equivalence suite (test/test_road.py) proves the C render_road matches recreate's verified
g_render_road, but it links C only and cannot execute m68k asm. This suite closes that gap per asm band:
it stages a real road frame, then runs the WHOLE road under Musashi with the band under test bound to its
C reference (every OTHER band on its shipping asm core) and byte-compares that against a single all-asm
baseline — so any framebuffer divergence isolates the band under test.

Why the whole road, not a band in isolation: `param` is a single monotonic cursor read across all seven
bands, so a band's entry state depends on how many param words the earlier bands consumed on THIS frame's
control stream — it cannot be constructed without running them. So each run is the full pipeline and only
the band under test differs. The BANDS descriptor names each band's (c/noop) wrappers, so one leg-sharded
harness covers all five cores (no copied class).

Staging (real frames, the flag census in PERF30's A4 note): each leg builds a mid-race image with real
game_update geometry, checkpointed at warmups 60/90/120 (they are prefixes of one simulation — one sim
per leg, not one per case). From each image the five road input buffers (width_tbl / param / edge window
/ edge_const / tex window) are extracted with adapter.road_input — the host road staging test_road.py
uses — across all 5 legs so band D sees splits, wide/solid centres, const strips, off-screen fills and
full-row fills. The buffers are poked into the bench's rr_diff_* staging buffers and the background into
the GUARD-bracketed rr_diff_fb; the buffer sizes are pinned against the bench ELF's own symbol spacing
(test_staging_matches_adapter), so a C-side resize without a matching poke cannot false-green.

Cross-checks per frame (ONE all-asm baseline shared across the checks — running each band's asm variant
separately would be the identical both-asm config):
  - C vs asm, per band: each band's C-isolation run (that band = C ref, every other band = shipping asm)
    must equal the all-asm baseline over the framebuffer window + GUARD bytes each side + the five
    read-only input buffers (a guard/input divergence is a wild asm store).
  - pipeline pin: bench_road_run_shipping (rm_render_road, the SHIPPING seven-band sequence) must equal
    bench_road_run_allasm (the DUPLICATED render_road_pipeline with every band asm), so the two hand-kept
    copies of the pipeline cannot drift.
  - positive control, per band: a no-op run for that band must draw a DIFFERENT framebuffer from its
    C-isolation run on at least one frame per leg, so a dead harness fails loudly instead of greening.

Requires the m68k bench.elf (bash render/atari/bench_build.sh); make test builds it first. If it is
absent the suite FAILS with that hint (bench.require_bench_elf) rather than skipping.
"""
import sys
from pathlib import Path

import pytest

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))   # reverse/tools — the shared recreate kit
from recreate_kit import project                        # noqa: E402
project.load(RECREATE)                                  # binds the kit's loader/emu to recreate
sys.path.insert(0, str(RECREATE / "tools"))        # bench_frame (mid-race staging internals)
sys.path.insert(0, str(REMASTER / "tools"))        # bench: the flat-image loader + shared helpers

import adapter                                      # noqa: E402  host road staging (same as test_road.py)
import bench_frame                                  # noqa: E402  the leg-simulation building blocks
from bench import BENCH_ELF, BENCH_BIN, _syms, _load_flat, require_bench_elf, noise_bytes  # noqa: E402

# All 5 legs; warmups are prefixes of one simulation (checkpointed). Legs are the shard axis (one worker
# per leg), so bench.elf is loaded once per worker and each leg's road is simulated once; all five cores run
# on the same staged frames.
LEGS = (0, 1, 2, 3, 4)
WARMUPS = (60, 90, 120)

# Per-band descriptor: the two bench wrappers that run the whole road with THIS band swapped to the C
# reference / a no-op (the other bands stay on their shipping-asm cores). The asm side is the SHARED
# all-asm baseline (every band asm) — running each band's asm variant separately would be the identical
# config, so ALL_ASM is run once per frame and each band's _c is compared against it. D = slice 1, B =
# slice 2, C-near/C-far + A = slice 3 (A/C-near/C-far isolated separately — distinct cores).
ALL_ASM = "bench_road_run_allasm"
BANDS = (
    {"name": "A",  "c": "bench_road_run_Ac",  "noop": "bench_road_run_noA"},
    {"name": "D",  "c": "bench_road_run_Dc",  "noop": "bench_road_run_noD"},
    {"name": "B",  "c": "bench_road_run_Bc",  "noop": "bench_road_run_noB"},
    {"name": "Cn", "c": "bench_road_run_Cnc", "noop": "bench_road_run_noCn"},
    {"name": "Cf", "c": "bench_road_run_Cfc", "noop": "bench_road_run_noCf"},
)

SCREEN_BYTES = adapter.SCREEN_BYTES
GUARD = 0x40                        # bench_main.c RR_DIFF_GUARD: canary bytes bracketing the framebuffer
EDGE_PAD = adapter.ROAD_EDGE_PAD    # rr_diff_edge window: road.edge_tbl = base + this
TEX_PAD_LO = adapter.ROAD_TEX_PAD_LO  # rr_diff_tex window: road.tex = base + this


def _leg_frames(leg):
    """The leg's mid-race image at each warmup in WARMUPS, from ONE simulation (warmups are prefixes).
    Replicates bench_frame.mid_race_state's init + `warmup` forced game_update loop, snapshotting along
    the way. The differential compares C vs asm on whatever is staged, so if these internals ever drift
    from mid_race_state the frames are still valid road frames — it cannot false-green, only re-pick."""
    import ctypes
    bf = bench_frame
    img, _ = bf.R._prepared_image({bf.A_LEG_INDEX: leg.to_bytes(2, "big")})
    post_init, _, _ = bf.emu.run(bytearray(img), bf.INIT_LEG, {}, max_insns=bf.MAX_INSNS)
    state = bytearray(post_init)
    buf = (ctypes.c_uint8 * bf.IMAGE_SIZE).from_buffer(state)
    bf.harness._lib.g_game_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    bf.harness._lib.g_game_update.restype = None
    want = set(WARMUPS)
    frames = {}
    for f in range(1, max(WARMUPS) + 1):
        bf._force_advance(state)
        bf.harness._lib.g_game_update(buf)
        if f in want:
            frames[f] = bytes(state)
    return frames


class _Harness:
    """Loads bench.elf once per worker; stages one road frame into a fresh image copy and runs one
    whole-road wrapper, returning the memory for the caller to slice."""

    def __init__(self):
        import emu
        self.emu = emu
        self.syms = _syms(BENCH_ELF)
        self.mem_t, self.sp, self.sentinel = _load_flat(BENCH_BIN, self.syms)
        self.width = self.syms["rr_diff_width"]
        self.param = self.syms["rr_diff_param"]
        self.edge = self.syms["rr_diff_edge"]
        self.const = self.syms["rr_diff_const"]
        self.tex = self.syms["rr_diff_tex"]
        self.fbx = self.syms["rr_diff_fb"]          # struct start: [GUARD lo | Framebuffer | GUARD hi]
        self.fb = self.fbx + GUARD

    def stage(self, image):
        """Extract the five road input buffers from a mid-race `image` (adapter.road_input, as test_road)
        and poke them + a GUARD-bracketed background into a fresh bench image copy. Returns (mem, sizes)."""
        _inp, keep = adapter.road_input(image)
        width_tbl, param, edge_const, edge_window, tex_window = (bytes(b) for b in keep)
        background = bytes(image[adapter.SCREEN_BASE:adapter.SCREEN_BASE + SCREEN_BYTES])

        mem = bytearray(self.mem_t)
        for at, data in ((self.width, width_tbl), (self.param, param), (self.edge, edge_window),
                         (self.const, edge_const), (self.tex, tex_window)):
            mem[at:at + len(data)] = data
        mem[self.fbx:self.fbx + GUARD] = noise_bytes(1, GUARD)
        mem[self.fb:self.fb + SCREEN_BYTES] = background
        mem[self.fb + SCREEN_BYTES:self.fb + SCREEN_BYTES + GUARD] = noise_bytes(2, GUARD)
        return mem, (width_tbl, param, edge_window, edge_const, tex_window)

    def run(self, mem, wrapper):
        m = bytearray(mem)
        self.emu.run_bench(m, self.syms[wrapper], arg0=0, sp=self.sp, sentinel=self.sentinel)
        return m

    def compare_region(self, mem, sizes):
        """The slice the runs must agree on: the framebuffer window bracketed by GUARD bytes on each side,
        plus the five read-only input buffers (a divergence there is a wild store)."""
        w, p, e, c, t = sizes
        return (bytes(mem[self.fbx:self.fb + SCREEN_BYTES + GUARD])
                + bytes(mem[self.width:self.width + len(w)])
                + bytes(mem[self.param:self.param + len(p)])
                + bytes(mem[self.edge:self.edge + len(e)])
                + bytes(mem[self.const:self.const + len(c)])
                + bytes(mem[self.tex:self.tex + len(t)]))

    def fb_window(self, mem):
        return bytes(mem[self.fb:self.fb + SCREEN_BYTES])


_HARNESS = None


def _harness():
    require_bench_elf()
    global _HARNESS
    if _HARNESS is None:
        _HARNESS = _Harness()
    return _HARNESS


def _gap_after(addrs, addr):
    """Bytes from `addr` to the next symbol above it — the space the buffer at `addr` may safely occupy."""
    higher = [a for a in addrs if a > addr]
    return (min(higher) - addr) if higher else float("inf")


def test_staging_matches_adapter():
    """Pin the C/Python staging contract against the bench ELF itself: each rr_diff_* buffer must have at
    least its poked length of room before the next symbol, and the framebuffer struct must fit its
    GUARD-bracketed window — so a C-side resize can't false-green a differential that keeps poking the old
    length. (Only the elf-existence guard + nm are needed; no full harness.)"""
    require_bench_elf()
    syms = _syms(BENCH_ELF)
    addrs = sorted(set(syms.values()))
    # The poked lengths equal adapter.road_input's extraction sizes (one source of truth); assert each
    # fits before the next symbol in the ELF.
    for name, poke_len in (("rr_diff_width", adapter.ROAD_WIDTH_TBL_BYTES),
                           ("rr_diff_param", adapter.ROAD_PARAM_BYTES),
                           ("rr_diff_edge",  adapter.ROAD_EDGE_WINDOW_BYTES),
                           ("rr_diff_const", adapter.ROAD_CONST_BYTES),
                           ("rr_diff_tex",   adapter.ROAD_TEX_WINDOW_BYTES)):
        assert poke_len <= _gap_after(addrs, syms[name]), f"{name}: poke {poke_len} overruns the ELF slot"
    # The GUARD-bracketed framebuffer struct ([GUARD | Framebuffer | GUARD]) must fit its slot; this pins
    # RR_DIFF_GUARD == GUARD (a C-side guard change shrinks/grows the slot the poke assumes).
    assert 2 * GUARD + SCREEN_BYTES <= _gap_after(addrs, syms["rr_diff_fb"]), "rr_diff_fb slot too small"
    assert adapter.ROAD_EDGE_WINDOW_BYTES == 2 * EDGE_PAD and EDGE_PAD == 0x400
    assert TEX_PAD_LO == 0x4000


@pytest.mark.parametrize("leg", LEGS)
def test_bands_asm_match_c(leg, capsys):
    """Every staged road frame for one leg, for each asm band (A, D, B, C-near, C-far): whole road with that
    band = C ref vs the all-asm baseline, byte-exact over the bracketed framebuffer + read-only inputs; plus
    the shipping-pipeline pin and the no-op positive control. All bands run on the SAME staged frames (one
    simulation per leg)."""
    h = _harness()
    frames = _leg_frames(leg)
    bad, pipe_bad, drew = [], [], {b["name"]: 0 for b in BANDS}
    for warmup in WARMUPS:
        mem, sizes = h.stage(frames[warmup])
        # ONE all-asm baseline (every band asm through render_road_pipeline) — reused as every band's asm
        # side (running each band's asm variant would be this identical config).
        wa = h.compare_region(h.run(mem, ALL_ASM), sizes)
        # Pipeline pin (once): the shipping road (rm_render_road, direct body) must match the all-asm
        # pipeline byte-for-byte — proves the two hand-kept copies of the seven-band sequence did not drift.
        if h.compare_region(h.run(mem, "bench_road_run_shipping"), sizes) != wa:
            pipe_bad.append((leg, warmup))
        for b in BANDS:
            cm = h.run(mem, b["c"])          # this band = C ref, the other band = shipping asm
            wc = h.compare_region(cm, sizes)
            if wc != wa:
                bad.append((leg, warmup, b["name"], sum(1 for a, x in zip(wc, wa) if a != x)))
            # Positive control per band: only until we have seen it paint (a few real frames are entirely
            # col<0 / SKIP blank — A4 census — so it is per-leg aggregate, not per-frame).
            if drew[b["name"]] == 0:
                if h.fb_window(cm) != h.fb_window(h.run(mem, b["noop"])):
                    drew[b["name"]] += 1
    with capsys.disabled():
        drew_str = " ".join(f"{n}={'y' if d else 'N'}" for n, d in drew.items())
        print(f"  road band asm leg {leg}: {len(bad)} mismatches, {len(pipe_bad)} pipeline drift, "
              f"drew[{drew_str}] ({len(WARMUPS)} frames x {len(BANDS)} bands)")
    missing = [n for n, d in drew.items() if not d]
    assert not missing, f"positive control: band(s) {missing} drew nothing on any warmup of leg {leg}"
    assert not pipe_bad, f"shipping road diverges from the all-asm pipeline: {pipe_bad}"
    assert not bad, f"band asm diverges from C reference: {bad}"
