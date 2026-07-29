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
    python sound/sound_player.py --synth sid --tunes 3   # C64 SID transcode -> *_sid.wav
    python sound/sound_player.py --c64 --tunes 3         # C64-flavored SID (PWM+filter+ADSR) -> *_c64.wav
    python sound/sound_player.py --c64-sustain 6 --tunes 3 --fx ""  # A/B a flavor -> tune_03_c64s06.wav

Effect ids feed INITFX; tune ids feed INITTUNE. Silent results (an id with no real data) are
skipped automatically.
"""
import argparse
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "tools"))   # reverse/tools — the shared recreate kit
from recreate_kit import project  # noqa: E402
project.load(HERE.parent)         # recreate/ — binds the kit's loader/emu to this game
from loader import load_image  # noqa: E402
import emu                      # noqa: E402
import ym2149                   # noqa: E402
import sid                      # noqa: E402  # C64 SID transcode of the same YM stream

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


def render_one(kind, starter, sound_id, flag_addr, max_frames, base_image, synth, c64=False,
               c64_sustain=None):
    """Capture + render one sound to its natural length. Return (path, seconds, tag) or None.

    ``synth`` is the renderer module (``ym2149`` or ``sid``); both expose ``render`` and ``RATE``.
    ``c64`` (SID only) engages the C64-native flavor and tags the file ``_c64`` instead of ``_sid``;
    an explicit ``c64_sustain`` (0..15) overrides the ADSR sustain and tags the file ``_c64s<N>``.
    """
    captured = capture(starter, sound_id, flag_addr, max_frames, base_image)
    if captured is None:
        return None
    snapshots, retriggers, end = captured
    kwargs = {"c64": True} if c64 else {}
    if c64 and c64_sustain is not None:
        kwargs["c64_sustain"] = c64_sustain
    samples = synth.render(snapshots, retriggers, **kwargs)
    if np.abs(samples).max() < 1e-3:                   # normalised silence -> nothing to hear
        return None
    seconds = len(snapshots) / ym2149.FPS
    if end[0] == "loop":
        tag = f"loops, period {end[2] / ym2149.FPS:.2f}s"
    elif end[0] == "open":
        tag = "still evolving at cap"
    else:
        tag = ""                                       # "flag"/"stop": a plain finite one-shot
    if c64:                                            # keep sustain-flavor renders side by side
        suffix = "_c64" if c64_sustain is None else f"_c64s{c64_sustain:02d}"
    else:
        suffix = "_sid" if synth is sid else ""
    path = OUT_DIR / f"{kind}_{sound_id:02d}{suffix}.wav"
    write_wav(path, samples, synth.RATE)
    return path, seconds, tag


def parse_ids(spec, default):
    return default if spec is None else [int(x) for x in spec.split(",") if x != ""]


def main():
    ap = argparse.ArgumentParser(description="Render BuggyBoy YM2149 tunes/effects to WAV.")
    ap.add_argument("--loop-seconds", type=float, default=LOOP_CAP_SECONDS,
                    help="cap for a sound that neither self-terminates nor loops (default 120)")
    ap.add_argument("--tunes", help="comma-separated INITTUNE ids (default 0-9)")
    ap.add_argument("--fx", help="comma-separated INITFX ids (default 0-8)")
    ap.add_argument("--synth", choices=("ym", "sid"), default="ym",
                    help="chip to render on: ym = Atari ST YM2149 (default), sid = C64 SID transcode")
    ap.add_argument("--c64", action="store_true",
                    help="SID only: engage the C64-native flavor (PWM + resonant filter + ADSR "
                         "pluck) instead of the clinical transcode; implies --synth sid, tags *_c64.wav")
    ap.add_argument("--c64-sustain", type=int, default=None, metavar="0-15",
                    help="C64 ADSR sustain level (0-15, default 6); implies --c64. Higher holds the "
                         "note body fuller, lower is more percussive. Tags *_c64s<N>.wav for A/B-ing")
    args = ap.parse_args()

    if args.c64_sustain is not None:
        if not 0 <= args.c64_sustain <= 15:
            ap.error("--c64-sustain must be in 0..15")
        args.c64 = True                          # a sustain override only means anything in C64 mode
    if args.c64:
        args.synth = "sid"                       # the C64 flavor is a SID rendering mode
    synth = sid if args.synth == "sid" else ym2149
    max_frames = int(round(args.loop_seconds * ym2149.FPS))
    base = load_image(PRG)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [("tune", INITTUNE, MZFLAG, i) for i in parse_ids(args.tunes, DEFAULT_TUNES)]
    jobs += [("fx", INITFX, FXFLAG, i) for i in parse_ids(args.fx, DEFAULT_FX)]

    written = 0
    for kind, starter, flag_addr, sound_id in jobs:
        result = render_one(kind, starter, sound_id, flag_addr, max_frames, base, synth,
                            args.c64, args.c64_sustain)
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