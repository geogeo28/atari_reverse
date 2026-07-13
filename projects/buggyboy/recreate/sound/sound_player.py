#!/usr/bin/env python3
"""Render BuggyBoy's music and sound effects to WAV files.

How it works: the game's sound driver is a 50 Hz VBL routine, ``REFRESH`` (@0x1b086), that
each frame walks a note/command stream and writes the YM2149 registers. We don't reimplement
it — we run the *original* driver in the Musashi oracle: seed a track with ``INITTUNE`` (or an
effect with ``INITFX``), then call ``REFRESH`` once per emulated frame, feeding the memory image
forward so the driver's state persists. The shim taps every PSG register write; ``ym2149.py``
turns that per-frame register stream into audio.

    python sound/sound_player.py                 # render all tunes + effects to out/sound/
    python sound/sound_player.py --loop-seconds 30   # cap long / non-terminating tracks at 30s
    python sound/sound_player.py --tunes 0,6 --fx 2

Effect ids feed INITFX; tune ids feed INITTUNE. Silent results (an id with no real data) are
skipped automatically.
"""
import argparse
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "oracle"))
from loader import load_image  # noqa: E402
import emu                      # noqa: E402
import ym2149                   # noqa: E402

PRG = HERE.parents[1] / "bin" / "BUGGYBOY.PRG"
OUT_DIR = HERE.parents[1] / "out" / "sound"

REFRESH = 0x1b086
INITTUNE = 0x1b59c
INITFX = 0x1b560

# The driver signals a sound's own end by clearing its active flag in the state block: mzflag
# for music (INITTUNE), fxflag for effects (INITFX). Some tracks instead end by freezing (the
# driver stops stepping) or, in principle, by looping. We detect all three by fingerprinting the
# driver's RAM each frame: it changes every frame while playing (the tempo counter at 0x1b080
# ticks), so a repeat of an earlier frame's state means a loop (period > 1) and a repeat of the
# previous frame means the driver has stopped (period 1 == ended). A sound that does none of
# these within LOOP_CAP_SECONDS is still evolving and is rendered up to the cap.
SND_STATE = 0x1b05c
MZFLAG = SND_STATE + 0x1e
FXFLAG = SND_STATE + 0x1f
DRIVER_RAM = (0x1b030, 0x1b700)   # covers the state block + the three voice-control records
LOOP_CAP_SECONDS = 120

DEFAULT_TUNES = range(0, 10)     # INITTUNE ids; silent ones are dropped
DEFAULT_FX = range(0, 9)         # INITFX ids 0-8 are the real effect table; 9+ read past it


def capture(starter, sound_id, flag_addr, max_frames, base_image):
    """Seed ``starter``(sound_id), then step REFRESH until the sound ends, loops, or hits the cap.

    Returns (snapshots, retriggers, end): ``snapshots`` are per-frame 16-register states trimmed
    to the sound's natural content (one loop's worth if it loops); ``retriggers`` flag frames that
    rewrote register 13 (a YM envelope retrigger); ``end`` is one of:
      ("flag", n)   — driver cleared its active flag after n frames (self-terminated),
      ("stop", n)   — driver froze after n frames (played out to a held/silent state),
      ("loop", n, p)— state revisited frame n-p; the tune loops with period p (n = start + p),
      ("open", n)   — still evolving at the n-frame cap.
    Returns None if the id hits an unmodeled path (no such sound).
    """
    lo, hi = DRIVER_RAM
    try:
        img, _, _ = emu.run(bytearray(base_image), starter, {"d0": sound_id})
    except RuntimeError:
        return None
    regs = [0] * 16
    snapshots, retriggers = [], []
    seen = {}                                          # driver-RAM state -> first frame index
    for f in range(max_frames):
        img, _, _ = emu.run(img, REFRESH, {})
        state = bytes(img[lo:hi])
        if state in seen:                              # this frame's state has occurred before
            period = f - seen[state]
            if period == 1:                            # unchanged from last frame: driver stopped
                return snapshots, retriggers, ("stop", f)
            return snapshots, retriggers, ("loop", f, period)
        seen[state] = f

        writes = emu.psg_writes()
        for reg, val in writes:
            if reg < 16:
                regs[reg] = val
        snapshots.append(list(regs))
        retriggers.append(any(reg == 13 for reg, _ in writes))
        if img[flag_addr] == 0:
            return snapshots, retriggers, ("flag", f + 1)
    return snapshots, retriggers, ("open", max_frames)


def write_wav(path, samples, rate):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def render_one(kind, starter, sound_id, flag_addr, max_frames, base_image):
    """Capture + render one sound to its natural length. Return (path, seconds, tag) or None."""
    captured = capture(starter, sound_id, flag_addr, max_frames, base_image)
    if captured is None:
        return None
    snapshots, retriggers, end = captured
    samples = ym2149.render(snapshots, retriggers)
    if np.abs(samples).max() < 1e-3:                   # normalised silence -> nothing to hear
        return None
    seconds = len(snapshots) / ym2149.FPS
    if end[0] == "loop":
        tag = f"loops, period {end[2] / ym2149.FPS:.2f}s"
    elif end[0] == "open":
        tag = "still evolving at cap"
    else:
        tag = ""                                       # "flag"/"stop": a plain finite one-shot
    path = OUT_DIR / f"{kind}_{sound_id:02d}.wav"
    write_wav(path, samples, ym2149.RATE)
    return path, seconds, tag


def parse_ids(spec, default):
    return default if spec is None else [int(x) for x in spec.split(",") if x != ""]


def main():
    ap = argparse.ArgumentParser(description="Render BuggyBoy YM2149 tunes/effects to WAV.")
    ap.add_argument("--loop-seconds", type=float, default=LOOP_CAP_SECONDS,
                    help="cap for a sound that neither self-terminates nor loops (default 120)")
    ap.add_argument("--tunes", help="comma-separated INITTUNE ids (default 0-9)")
    ap.add_argument("--fx", help="comma-separated INITFX ids (default 0-8)")
    args = ap.parse_args()

    max_frames = int(round(args.loop_seconds * ym2149.FPS))
    base = load_image(PRG)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [("tune", INITTUNE, MZFLAG, i) for i in parse_ids(args.tunes, DEFAULT_TUNES)]
    jobs += [("fx", INITFX, FXFLAG, i) for i in parse_ids(args.fx, DEFAULT_FX)]

    written = 0
    for kind, starter, flag_addr, sound_id in jobs:
        result = render_one(kind, starter, sound_id, flag_addr, max_frames, base)
        if result:
            path, seconds, tag = result
            suffix = f"  ({tag})" if tag else ""
            print(f"  {path.relative_to(OUT_DIR.parents[1])}  {seconds:.2f}s{suffix}")
            written += 1
        else:
            print(f"  {kind} {sound_id}: silent, skipped")
    print(f"\n{written} sound(s) written to {OUT_DIR}")


if __name__ == "__main__":
    main()