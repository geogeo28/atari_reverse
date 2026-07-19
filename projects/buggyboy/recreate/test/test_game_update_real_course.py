"""Differential test: game_update over the REAL leg-N course data, frame by frame.

The synthetic section-12 fuzz (test_game_update._check_course) uses random buf_a, so it never runs
the actual COURSES.DAT record sequence. This stages the real course (render_screen._prepared_image
+ oracle init_leg, so both sides start byte-identical), forces a section-12 advance each frame, and
diffs g_game_update against the Musashi oracle (0x1110e) over the whole image, frame by frame.

It regression-guards three real reconstruction bugs the random fuzz missed (fixed 2026-07):
  - section-H horizon dispatch passed d5=0 (should be horizon_row / +2) -> event_type/obj_active
    never cleared, course/palette state drifted;
  - section-G spin/fx select read obj-0x1c/-0x1b instead of obj-2/-1 -> wrong spin fx;
  - fx_block_2e did a byte store where the original's last write is a word (move.w 0x003e).

NOT covered: the mode-4 Setpalette-target fix from the same pass is OFF-IMAGE (g_xbios_setpalette
has no image effect in the harness), so no whole-image diff can see it — it was found by a Hatari
memory-snapshot diff. See recreate/README.md "Harness gaps" for the proposed off-image ledger.

Parametrized by (leg, chunk): the recon advance is fast (.so); the oracle checks shard by frame
range across xdist workers.
"""
import ctypes
import sys
from pathlib import Path

import pytest

import harness
import emu

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))
import render_screen as R                                             # noqa: E402

INIT_LEG = 0x104b8                     # oracle init_leg (both sides start identical)
GAME_UPDATE = 0x1110e                  # oracle game_update entry
A_LEG_INDEX = 0x18c38
# per-frame state that forces a section-12 course advance (view_flags wrap, max rpm, no input)
A_VIEW_FLAGS, A_ENGINE_RPM, A_SCROLL_PHASE, A_INPUT_STATE = 0x18c56, 0x18c4c, 0x18c4e, 0x18c44
N_FRAMES = 120                         # covers the frames the three bugs surfaced at (14/60/93)
CHUNKS = 4
MAX_INSNS = 4_000_000

harness._lib.g_game_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_game_update.restype = None


def _w16(m, a, v):
    m[a] = (v >> 8) & 0xff
    m[a + 1] = v & 0xff


def _force_advance(m):
    _w16(m, A_VIEW_FLAGS, 0x10)
    _w16(m, A_ENGINE_RPM, 0xf)
    _w16(m, A_SCROLL_PHASE, 0xe)
    _w16(m, A_INPUT_STATE, 0)


@pytest.mark.parametrize("leg", range(5))
@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_game_update_real_course(leg, chunk):
    img, _ = R._prepared_image({A_LEG_INDEX: leg.to_bytes(2, "big")})
    post_init, _, _ = emu.run(bytearray(img), INIT_LEG, {}, max_insns=MAX_INSNS)
    state = bytearray(post_init)
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(state)
    lo, hi = chunk * N_FRAMES // CHUNKS, (chunk + 1) * N_FRAMES // CHUNKS
    guard = emu.STACK_GUARD_LO
    for f in range(hi):                # advance the recon to the chunk end; oracle-check only [lo,hi)
        _force_advance(state)
        if lo <= f < hi:
            pre = bytes(state)
            o_post, _, _ = emu.run(bytearray(pre), GAME_UPDATE, {}, max_insns=MAX_INSNS)
            harness._lib.g_game_update(buf)                       # state <- recon(pre), in place
            if bytes(state)[:guard] != o_post[:guard]:           # fast path: whole-image compare
                a = next(i for i in range(guard) if state[i] != o_post[i])
                diffs = sum(1 for i in range(guard) if state[i] != o_post[i])
                raise AssertionError(
                    f"leg {leg} frame {f}: {diffs} byte(s) differ from the oracle; first at "
                    f"{harness.label(a)} @ {hex(a)} (recon={state[a]:#04x} oracle={o_post[a]:#04x})")
        else:
            harness._lib.g_game_update(buf)                      # fast recon-only advance
