"""Turn a patroller run's samples into one x series PER ACTOR, and score each for a turn.

`secrets_demo.py patroller-{on,off}` records every live actor at each sample, so reducing a sample to
one number mixes actors that spawned and despawned at different moments. The unit that means anything
is a maximal run of consecutive samples in which ONE SLOT holds a live record of the demo type --
that is one actor's flight, and its x series is what the move handler produced.

The dead handler 0x148ca turns at x <= 0xc8; the shipped one for that slot is the script VM, which
mostly does not. So the statistic is how many tracks turn, and the two runs are read together.

    python3 projects/zynaps/tools/patroller_tracks.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out" / "secrets"
RUNS = ("patroller-off", "patroller-on")
# The handler steps x by 2 a frame and the machine runs at 50 Hz, so one sample of travel is
# `2 * 50 * interval` px; a rise smaller than that is sampling noise or a record replaced in its
# slot, not a turn. The interval comes out of the record rather than being restated here.
PIXELS_PER_SECOND = 2 * 50
MIN_SAMPLES = 4          # fewer than this is not a flight, it is the tail of one
TRACKS_SHOWN = 8


def tracks_for(samples, demo_type):
    """[(slot, [x, ...]), ...] -- one entry per maximal single-slot run of `demo_type`."""
    open_runs, done = {}, []
    for sample in samples:
        live = {slot: x for slot, kind, x in sample if kind == demo_type}
        for slot in list(open_runs):
            if slot not in live:
                done.append((slot, open_runs.pop(slot)))
        for slot, x in live.items():
            open_runs.setdefault(slot, []).append(x)
    return done + sorted(open_runs.items())


def turned(xs, margin):
    """True if the series falls to a floor and then climbs back well past it."""
    floor = min(xs)
    after = xs[xs.index(floor):]
    return len(after) > 1 and max(after) - floor > margin


def report(tag):
    result = json.loads((OUT / f"result_{tag}.json").read_text())["result"]
    margin = PIXELS_PER_SECOND * result["sample_interval_seconds"]
    tracks = [(slot, xs) for slot, xs in tracks_for(result["tracks"], result["demo_type"])
              if len(xs) >= MIN_SAMPLES]
    turns = sum(1 for _, xs in tracks if turned(xs, margin))
    print(f"== {tag}: move-table slot {result['slot_before']} -> {result['slot_after']}, "
          f"type {result['demo_type']:#04x}, turn margin {margin:.0f} px")
    print(f"   {len(tracks)} tracks of {MIN_SAMPLES}+ samples, {turns} of them turn")
    for slot, xs in tracks[:TRACKS_SHOWN]:
        print(f"   slot {slot:2d}: " + " ".join(str(x) for x in xs) +
              ("   <- turns" if turned(xs, margin) else ""))


def main():
    for tag in RUNS:
        report(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
