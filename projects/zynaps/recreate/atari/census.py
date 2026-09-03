"""Census: walk the oracle playing the real game and report how loaded each frame's entity table is.

Saves the busiest image seen so far as it goes, so a run that ends in a frame the schedule cannot
complete (a death, a section boundary) still leaves its heaviest frame behind.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The kit binding, the actor-slot range and the liveness test all come from bench_tier — its own
# import is what puts tools/ and test/ on the path, so this must precede every name below it.
# ONE SPELLING OF THE ENTITY TABLE for the two halves of one instrument: the census decides which
# frame is busiest and the bench prices it, and a disagreement about ENTITY_ALIVE would make the
# second measure a frame the first did not choose. Both read the records through `test_frame`,
# whose MIRRORS pin every one of them against its header.
from bench_tier import ACTOR_FIRST_SLOT, ACTOR_LAST_SLOT, live_slots  # noqa: E402
import test_frame as F                                              # noqa: E402

# The quiet frame is the heavy one's CONTROL, so it must be the same game rather than the same
# screen: taken only once the section has scrolled past its opening, where nothing has spawned yet
# for reasons that are about the clock rather than about the world.
LIGHT_WARMUP_FRAMES = 10


def census(image):
    """[(slot, type)] for every live entity — `bench_tier.live_slots` with each slot's type."""
    return [(slot, image[F.entity_record(slot) + F.ENTITY_TYPE])
            for slot in live_slots(image)]


USAGE = ("usage: python3 atari/census.py <section> <frames> <joystick-seed> <busiest.img> "
         "[quietest.img]")


def main():
    if len(sys.argv) < 5:
        raise SystemExit(USAGE)
    section = int(sys.argv[1])
    frames = int(sys.argv[2])
    seed = int(sys.argv[3])
    out = Path(sys.argv[4])
    light_out = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    image = F._stage_section(section)
    rng = F.world_rng(seed)
    best = (-1, 0)
    quietest = None
    for n in range(frames):
        image[F.A_JOYSTICK_STATE] = rng.choice(F.JOYSTICK_BYTES)
        try:
            image = F.advance_one_frame(image)
        except RuntimeError as exc:
            print(f"frame {n + 1}: the oracle could not complete the frame — {exc}", flush=True)
            break
        live = census(image)
        actors = [s for s, _ in live if ACTOR_FIRST_SLOT <= s <= ACTOR_LAST_SLOT]
        print(f"frame {n + 1:4d}  live={len(live):2d}  actors={len(actors):2d}  "
              f"types={sorted(t for _, t in live)}", flush=True)
        rank = (len(actors), len(live))
        if light_out is not None and n + 1 >= LIGHT_WARMUP_FRAMES \
                and (quietest is None or rank < quietest):
            quietest = rank
            light_out.write_bytes(bytes(image))
        if rank > best:
            best = rank
            out.write_bytes(bytes(image))
            print(f"   ...saved as the busiest so far -> {out.name}", flush=True)
    print(f"\nBUSIEST: {best[0]} live actor slots, {best[1]} live entities -> {out}")
    if quietest is not None:
        print(f"QUIETEST (from frame {LIGHT_WARMUP_FRAMES} on): {quietest[0]} live actor slots, "
              f"{quietest[1]} live entities -> {light_out}")


if __name__ == "__main__":
    main()
