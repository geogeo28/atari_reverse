"""Demonstrate the Zynaps secrets on the ORIGINAL binary, in Hatari, headlessly.

Every experiment here boots the real game (the faithful `.stx` by default), drives it to level 1
through `boot_shots.py`'s own two anchors -- the PRG appearing in RAM and the PREPARE-FOR-COMBAT
gate being crossed -- and then does ONE thing and photographs the consequence. Nothing is claimed
that a capture or a memory dump does not show.

    python3 projects/zynaps/tools/secrets_demo.py probe            # what the level does unattended
    python3 projects/zynaps/tools/secrets_demo.py pause            # the SPACE pause
    python3 projects/zynaps/tools/secrets_demo.py invuln-off       # control: the ship dies
    python3 projects/zynaps/tools/secrets_demo.py invuln-on        # the 0x19912 flag poked to 1
    python3 projects/zynaps/tools/secrets_demo.py patroller-off    # control: the shipped handler
    python3 projects/zynaps/tools/secrets_demo.py patroller-on     # the dead 0x148ca handler
    python3 projects/zynaps/tools/secrets_demo.py all              # every demonstration, ~25 min

`--mode gemdos` swaps the floppy for `bin/disk/` as drive C:, which reaches the level in a fraction
of the time; it runs the same PRG off the same data files and is used for iteration, while the
reported runs are on the `.stx`.
"""
import argparse
import json
import struct
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

import boot_shots as boot
from hatari_headless import HeadlessSession, log_faults, same_picture

OUT = PROJECT / "out" / "secrets"

# --- the game's own addresses, as TEXT offsets (a sweep address minus its nominal 0x10000 base) ---
# Every one is read out of out/prg_dis.txt or names.txt; none is guessed.
PALETTE_SWAP_COUNTDOWN = 0x9683  # the pause loop rewrites both of these to 8 on every pass
PALETTE_ROTATE_COUNTDOWN = 0x9684
LIVES = 0x991A
SHIP_INVULNERABLE = 0x9912       # read by three `tst.b`, written by nothing in the image
DEATH_EVENT_FLAGS = 0x98C4       # bit 0 set beside every player explosion
LEVEL_SECTION = 0x9895
ACTOR_MOVE_TABLE = 0x9380        # 0x2e longs, dispatched on record byte +0x11
# The span the four bytes above fall in, so one dump is one SNAPSHOT of them: bytes fetched in
# separate debugger calls are seconds of emulated time apart and a row of them could straddle a death.
PLAYER_STATE_FIRST, PLAYER_STATE_LAST = LEVEL_SECTION, LIVES
# The eleven records `enemies_move_all` walks, and the three fields this demo reads out of one.
ACTOR_ARRAY = 0x7B96
ACTOR_SLOTS = 11
ACTOR_RECORD_BYTES = 0x2C
ACTOR_X = 0x00
ACTOR_ALIVE = 0x0E
ACTOR_TYPE = 0x11

PAUSE_COUNTDOWN_WHILE_PAUSED = 8   # what the pause loop writes to both countdowns on every pass
BLANK_COLOUR_COUNT = boot.BLANK_COLOUR_COUNT   # a capture with this many colours is of nothing

# The dead sine patroller and the live handler whose table slot it would replace. Both are stored in
# the table as ALREADY-RELOCATED absolute addresses, so a poke has to add the load base.
DEAD_PATROLLER = 0x48CA
# WHICH type the dead handler was written for is not recoverable -- no table entry survives -- so the
# demonstration borrows a slot instead. Type 0x16 is the one `spawn_formation` puts on screen
# continuously in every section (an earlier run measured type 0x0e, the opcode-0x0b trio, appearing in
# none of 120 samples), and its shipped handler is the script VM, so a run that patrols instead of
# following its script is unmistakable.
DEMO_TYPE = 0x16

SETTLE_SECONDS = 4.0             # after the gate, before anything is touched: let the level scroll
MOTION_SECONDS = 1.5             # long enough that a running level is a different picture
FROZEN_SECONDS = 2.5             # ...and long enough that a frozen one is still the same picture
PROBE_SECONDS = 90.0
PROBE_INTERVAL = 5.0
# Comfortably past the ~22 s the `probe` run measured an unattended ship taking to lose three lives.
INVULN_WATCH_SECONDS = 70.0
# Each sample is one 484-byte dump through the debugger, so the interval is what the FIFO can keep up
# with rather than a frame rate; 120 of them span several waves crossing the screen.
PATROLLER_SAMPLES = 120
PATROLLER_INTERVAL = 0.5
PATROLLER_SHOT_EVERY = 20


def session_for(mode, rom, work):
    log = OUT / f"{mode}_secrets.log"
    return HeadlessSession(boot.hatari_arguments(mode, rom, gui=False), log_path=log,
                           fifo_path=OUT / f"{mode}_secrets.fifo", work_dir=work), log


def drive_to_level(session):
    """Boot, cross the front end and the fire gate, and return the load base. Both anchors are
    `boot_shots.py`'s: a RAM search for the PRG's own TEXT, then the gate's own breakpoint."""
    base = boot.wait_for_load(session)
    marker = boot.arm_fire_gate(session, base)
    loaded_at = time.monotonic()
    for at, _, action in boot.TIMELINE:
        if action == boot.AWAIT_GATE:
            boot.await_gate(session, marker)
            return base
        session.wait(max(0.0, loaded_at + at - time.monotonic()))
        session.require_alive(f"driving the front end at +{at:.0f}s")
        if action is not None:
            session.key(action)
    return base


def bytes_at(session, base, first, last):
    """One dump of `first`..`last` inclusive, as a dict keyed by offset.

    ONE ROUND TRIP, NOT ONE PER BYTE: the machine keeps running between debugger calls, so bytes
    fetched separately are not a snapshot and a "row" of them could straddle a death."""
    span = last - first + 1
    blob = session.savebin("span.bin", base + first, span)
    return {first + i: blob[i] for i in range(span)}


def shot(session, tag):
    """Photograph the frame through `boot_shots.capture_frame`, which RETAKES A BLANK ONE.

    That retry is not a nicety here: the pause verdict is "these two captures are the same picture",
    and two photographs of a blanked screen satisfy it whatever the frame loop is doing."""
    return boot.capture_frame(session, OUT / f"{tag}.png")


def colours(path):
    """How many distinct colours a capture holds. One means it is a photograph of nothing."""
    return boot.distinct_colours(path)


def poke_long(session, address, value):
    session.poke(address, *struct.pack(">I", value))


# --- the experiments -----------------------------------------------------------------------------

def experiment_probe(session, base):
    """No poke at all: sample the state an unattended ship reaches, so the demos below can be aimed."""
    session.wait(SETTLE_SECONDS)
    rows = []
    deadline = time.monotonic() + PROBE_SECONDS
    while time.monotonic() < deadline:
        at = time.monotonic()
        state = bytes_at(session, base, PLAYER_STATE_FIRST, PLAYER_STATE_LAST)
        rows.append((round(at - session.started, 1),
                     state[LIVES], state[LEVEL_SECTION],
                     state[DEATH_EVENT_FLAGS], state[SHIP_INVULNERABLE]))
        print("   t=%6.1fs lives=%d section=%02x death_flags=%02x invuln=%02x" % rows[-1])
        session.wait(PROBE_INTERVAL)
    shot(session, "probe_end")
    return {"rows": rows}


def _pause_cycle(session, base, round_number):
    """One press-pause-press cycle, photographed. Returns the round's own findings."""
    tag = f"pause_r{round_number}"
    moving_a = shot(session, f"{tag}_1_moving_a")
    session.wait(MOTION_SECONDS)
    moving_b = shot(session, f"{tag}_2_moving_b")

    session.key(boot.KEY_SPACE)
    session.wait(1.0)
    frozen_a = shot(session, f"{tag}_3_frozen_a")
    paused = bytes_at(session, base, PALETTE_SWAP_COUNTDOWN, PALETTE_ROTATE_COUNTDOWN)
    countdowns = (paused[PALETTE_SWAP_COUNTDOWN], paused[PALETTE_ROTATE_COUNTDOWN])
    session.wait(FROZEN_SECONDS)
    frozen_b = shot(session, f"{tag}_4_frozen_b")

    session.key(boot.KEY_SPACE)
    session.wait(1.0)
    resumed_a = shot(session, f"{tag}_5_resumed_a")
    session.wait(MOTION_SECONDS)
    resumed_b = shot(session, f"{tag}_6_resumed_b")

    return {"round": round_number,
            "moved_before": not same_picture(moving_a, moving_b),
            "frozen_while_paused": same_picture(frozen_a, frozen_b),
            # WITHOUT THIS THE FROZEN VERDICT IS UNFALSIFIABLE: two photographs of a blanked screen
            # are the same picture too, so the pair has to be shown to hold a real frame.
            "frozen_pair_colours": (colours(frozen_a), colours(frozen_b)),
            "countdowns_while_paused": countdowns,
            "countdowns_hold_the_pause_value": countdowns == (PAUSE_COUNTDOWN_WHILE_PAUSED,) * 2,
            "moved_after": not same_picture(resumed_a, resumed_b)}


def experiment_pause(session, base):
    """SPACE in the level. Two rounds, because a claim reproduced once is not reproduced."""
    session.wait(SETTLE_SECONDS)
    return {"rounds": [_pause_cycle(session, base, n) for n in (1, 2)]}


def _invulnerability(session, base, flag):
    """Poke the flag (or not) and then leave the ship completely alone.

    NOTHING ELSE IS TOUCHED. The `probe` run measured what an unattended ship does on level 1 --
    three lives gone in about twenty-two seconds -- so the game's own enemies are the experiment and
    the flag is the only variable. Sampling the lives byte is the surface; the captures show it."""
    # POKED AT THE GATE, not after a settle: an earlier run that waited four seconds first found a
    # death already in flight -- the life is deducted when the explosion animation reaches frame 13,
    # not when the ship is hit -- so it lost one life before the flag could take effect.
    tag = "invuln_on" if flag else "invuln_off"
    if flag:
        session.poke(base + SHIP_INVULNERABLE, 1)
    session.wait(SETTLE_SECONDS)
    rows = []
    shot(session, f"{tag}_1_start")
    deadline = time.monotonic() + INVULN_WATCH_SECONDS
    while time.monotonic() < deadline:
        state = bytes_at(session, base, PLAYER_STATE_FIRST, PLAYER_STATE_LAST)
        rows.append((round(time.monotonic() - session.started, 1),
                     state[LIVES], state[DEATH_EVENT_FLAGS], state[SHIP_INVULNERABLE]))
        print("   t=%6.1fs lives=%d death_flags=%02x invuln=%02x" % rows[-1])
        session.wait(PROBE_INTERVAL)
    shot(session, f"{tag}_2_end")
    return {"flag": flag, "lives_first": rows[0][1], "lives_last": rows[-1][1],
            "death_flags_last": rows[-1][2], "invuln_byte": rows[-1][3], "rows": rows}


def experiment_invuln_off(session, base):
    return _invulnerability(session, base, flag=False)


def experiment_invuln_on(session, base):
    return _invulnerability(session, base, flag=True)


def live_actors(session, base):
    """(slot, type, x) for every live record in the eleven `enemies_move_all` walks.

    A screenshot cannot tell a sprite moving left from one moving right, so the x series is the
    demonstration and the captures are only corroboration."""
    array = session.savebin("actors.bin", base + ACTOR_ARRAY, ACTOR_SLOTS * ACTOR_RECORD_BYTES)
    live = []
    for slot in range(ACTOR_SLOTS):
        record = array[slot * ACTOR_RECORD_BYTES:(slot + 1) * ACTOR_RECORD_BYTES]
        if record[ACTOR_ALIVE]:
            live.append((slot, record[ACTOR_TYPE], struct.unpack(">H", record[ACTOR_X:ACTOR_X + 2])[0]))
    return live


def _patroller(session, base, dead_handler):
    """Point the wave trio's move slot at the dead 0x148ca handler, or leave it alone.

    BOTH RUNS POKE THE INVULNERABILITY FLAG, which is not the variable under test: an unattended
    ship loses its three lives in about 22 s (see `probe`), and each death restarts the section, so
    without it neither run stays in one section long enough for a wave to cross the screen. The
    single variable is the table slot."""
    tag = "patroller_on" if dead_handler else "patroller_off"
    session.poke(base + SHIP_INVULNERABLE, 1)
    slot = base + ACTOR_MOVE_TABLE + DEMO_TYPE * 4
    session.wait(SETTLE_SECONDS)
    before = struct.unpack(">I", session.savebin("slot.bin", slot, 4))[0]
    if dead_handler:
        poke_long(session, slot, base + DEAD_PATROLLER)
    after = struct.unpack(">I", session.savebin("slot2.bin", slot, 4))[0]

    tracks = []
    for step in range(PATROLLER_SAMPLES):
        live = live_actors(session, base)
        tracks.append(live)
        print(f"   step {step:3d}: " +
              (", ".join(f"s{s}/t{kind:02x}/x{x}" for s, kind, x in live) or "none live"))
        if step % PATROLLER_SHOT_EVERY == 0:
            shot(session, f"{tag}_{step:03d}")
        session.wait(PATROLLER_INTERVAL)
    return {"slot_before": hex(before), "slot_after": hex(after),
            "demo_type": DEMO_TYPE,
            "sample_interval_seconds": PATROLLER_INTERVAL,
            "demo_type_seen": any(kind == DEMO_TYPE for sample in tracks for _, kind, _ in sample),
            # The raw samples only: `tools/patroller_tracks.py` cuts them into one series per actor,
            # which is the unit that means anything. A derived copy here could only drift from them.
            "tracks": tracks}


def experiment_patroller_off(session, base):
    return _patroller(session, base, dead_handler=False)


def experiment_patroller_on(session, base):
    return _patroller(session, base, dead_handler=True)


EXPERIMENTS = {
    "probe": experiment_probe,
    "pause": experiment_pause,
    "invuln-off": experiment_invuln_off,
    "invuln-on": experiment_invuln_on,
    "patroller-off": experiment_patroller_off,
    "patroller-on": experiment_patroller_on,
}

# WHAT EACH RUN HAD TO SHOW, so the EXIT STATUS is a surface and not just "Hatari did not crash".
# Without these the whole battery exits 0 with `"frozen_while_paused": false` buried in a JSON file
# nobody re-reads -- which is exactly how the wrong SPACE claim survived for a year.
# `probe` has no verdict on purpose: it measures the level to aim the others and asserts nothing.
VERDICTS = {
    "pause": lambda r: all(c["moved_before"] and c["frozen_while_paused"]
                           and c["countdowns_hold_the_pause_value"]
                           and min(c["frozen_pair_colours"]) > BLANK_COLOUR_COUNT
                           and c["moved_after"] for c in r["rounds"]),
    # The control has to actually kill the ship, or the cheat run proves nothing by comparison.
    "invuln-off": lambda r: r["lives_last"] < r["lives_first"],
    "invuln-on": lambda r: r["lives_last"] == r["lives_first"] and not r["death_flags_last"],
    # Both patroller runs need the demo type on screen at all; the turn counts are read back by
    # patroller_tracks.py, which the README quotes.
    "patroller-off": lambda r: r["demo_type_seen"] and r["slot_after"] == r["slot_before"],
    "patroller-on": lambda r: r["demo_type_seen"] and r["slot_after"] != r["slot_before"],
}

ALL = "all"
# Each demonstration is a whole boot, so `all` costs about twenty-five minutes. `probe` is left out:
# it aims the others rather than demonstrating anything, and `invuln-off` measures the same thing.
ALL_ORDER = ["pause", "invuln-off", "invuln-on", "patroller-off", "patroller-on"]


def run_experiment(name, mode, rom, tos):
    """One boot, one experiment, one `result_<name>.json`. True if the run is evidence."""
    with tempfile.TemporaryDirectory() as work:
        session, log = session_for(mode, rom, work)
        try:
            base = drive_to_level(session)
            print(f"-- {name}: loaded at base {base:#x}")
            result = EXPERIMENTS[name](session, base)
        finally:
            status = session.close()

    faults = log_faults(log)
    # The run's own numbers, beside its captures: stdout scrolls away, and a claim in the README has
    # to point at something on disk.
    verdict = VERDICTS[name](result) if name in VERDICTS else None
    record = OUT / f"result_{name}.json"
    record.write_text(json.dumps({"experiment": name, "mode": mode, "tos": tos,
                                  "base": base, "verdict": verdict, "result": result}, indent=2))
    print(f"-- verdict: {verdict}   (written to {record})")
    print(f"-- hatari exit {status}, {len(faults)} fault line(s)")
    for line in faults:
        print(f"   FAULT: {line}")
    return status == 0 and not faults and verdict is not False


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", choices=sorted(EXPERIMENTS) + [ALL])
    parser.add_argument("--mode", default="stx", choices=boot.BOOT_MODES)
    parser.add_argument("--tos", default=boot.DEFAULT_TOS)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rom, version = boot.resolve_tos(None, args.tos)
    boot.refuse_unsupported(args.mode, version)
    # One at a time even for `all`: every run drives the same command FIFO, so two cannot overlap.
    wanted = ALL_ORDER if args.experiment == ALL else [args.experiment]
    good = [run_experiment(name, args.mode, rom, args.tos) for name in wanted]
    return 0 if all(good) else 1


if __name__ == "__main__":
    raise SystemExit(main())
