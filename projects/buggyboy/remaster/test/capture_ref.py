"""capture_ref.py — golden framebuffers from the verified recreate/ cores.

This is the REFERENCE side of the remaster equivalence harness (see ../README.md "The contract").
It drives recreate/build/libbuggyboy.so — the cores proven byte-for-byte against the Musashi oracle
— through the in-race render pipeline and captures the 32000-byte framebuffer each frame. Those
frames are the ground truth the remaster candidate must reproduce pixel-for-pixel.

Determinism: we stage a real mid-race image exactly as recreate/tools/bench_frame.py does (real
COURSES.DAT, oracle init_leg, then N warmup game_update frames each forcing a section-12 advance),
then for each captured frame run the render pipeline into a fixed screen buffer and read it back.
Same leg + same warmup in -> identical bytes out.

Usage (standalone sanity check — proves capture is deterministic):
    python test/capture_ref.py [leg] [frames]
"""
import ctypes
import hashlib
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]        # remaster/
RECREATE = REMASTER.parent / "recreate"               # sibling verified reconstruction
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))   # reverse/tools — the shared recreate kit
from recreate_kit import project                        # noqa: E402
project.load(RECREATE)                                  # binds the kit's loader/emu to recreate
sys.path.insert(0, str(RECREATE / "test"))
sys.path.insert(0, str(RECREATE / "render"))
sys.path.insert(0, str(RECREATE / "tools"))

import harness                                         # noqa: E402  loads recreate's libbuggyboy.so
import render_screen as R                              # noqa: E402  buffer layout + SCREEN_BASE
import bench_frame                                     # noqa: E402  realistic mid-race staging

SCREEN_BASE = R.SCREEN_BASE                            # physbase_tbl[0]: where the pipeline draws
SCREEN_BYTES = R.ROW_STRIDE * R.H                      # 160 * 200 = 32000

# The in-race per-frame render pipeline, in draw order. Each recon g_* wrapper takes only the image
# pointer and reads the draw buffer from physbase_tbl[flip_idx] (set by bench_frame's staging).
RENDER_PIPELINE = ("g_render_road", "g_blit_road_scroll", "g_draw_game_objects", "g_draw_hud")


def _bind(name):
    fn = getattr(harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    return fn


def _render_into(state):
    """Run the render pipeline over `state` (a mid-race image bytearray) and return the 32000-byte
    framebuffer drawn at SCREEN_BASE."""
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    for name in RENDER_PIPELINE:
        _bind(name)(buf)
    return bytes(state[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES])


def capture_frames(leg=0, frames=1, warmup=60):
    """Capture `frames` consecutive rendered framebuffers starting from a mid-race state on `leg`.
    Between frames we advance one game_update (as bench_frame does) so the road/objects/HUD move."""
    state = bench_frame.mid_race_state(leg, warmup)
    step = _bind("g_game_update")
    buf = (ctypes.c_uint8 * bench_frame.IMAGE_SIZE).from_buffer(state)
    out = []
    for _ in range(frames):
        out.append(_render_into(state))
        bench_frame._force_advance(state)
        step(buf)
    return out


if __name__ == "__main__":
    leg = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    frames = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    a = capture_frames(leg, frames)
    b = capture_frames(leg, frames)                    # re-run: must be byte-identical (determinism)
    for i, (fa, fb) in enumerate(zip(a, b)):
        tag = "ok " if fa == fb else "DIFF"
        print(f"  frame {i}: {tag} {hashlib.sha256(fa).hexdigest()[:16]}  ({len(fa)} bytes)")
    print("deterministic" if a == b else "NON-DETERMINISTIC — capture is not reproducible")
