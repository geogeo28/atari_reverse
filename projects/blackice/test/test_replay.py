"""Determinism and the golden frames.

A fixed timestep plus a seeded RNG plus a recorded input script is the whole
test strategy for this engine: if the same script produces the same state hash
and the same pixels twice, every stage between them is pinned at once.
"""
import hashlib
import pathlib
import subprocess

import pytest

import blackice
from blackice import CONST

GOLDEN = blackice.ROOT / "test" / "golden"
LEVEL = blackice.ROOT / "levels" / "level1.txt"
SCRIPT = blackice.ROOT / "test" / "scripts" / "walk.txt"
FRAMES = 100


def run_host(tmp_path, seed=None, png="none", level=LEVEL):
    tmp_path.mkdir(parents=True, exist_ok=True)
    hashes = tmp_path / "hashes.txt"
    command = [str(blackice.HOST_BIN), "--level", str(level), "--script", str(SCRIPT),
               "--frames", str(FRAMES), "--out", str(tmp_path), "--png", png,
               "--hashes", str(hashes)]
    if seed is not None:
        command += ["--seed", str(seed)]
    subprocess.run(command, check=True)
    return hashes.read_text()


def test_the_same_script_replays_identically(lib, tmp_path):
    first = run_host(tmp_path / "a")
    second = run_host(tmp_path / "b")
    assert first == second
    assert len(first.splitlines()) == FRAMES


def test_a_different_seed_gives_a_different_state(lib, tmp_path):
    """The seed is threaded into the hashed state, so a run started with a
    different one can never be mistaken for the same run."""
    default = run_host(tmp_path / "a")
    other = run_host(tmp_path / "b", seed=1234)
    assert default != other


def test_the_walk_matches_the_golden_state_and_screen_hashes(lib, tmp_path):
    produced = run_host(tmp_path / "run").splitlines()
    expected = (GOLDEN / "walk_hashes.txt").read_text().splitlines()
    assert len(produced) == len(expected)
    for frame, (got, want) in enumerate(zip(produced, expected)):
        assert got == want, "frame %d diverged: %r != %r" % (frame, got, want)


def test_every_golden_png_is_reproduced_byte_for_byte(lib, tmp_path):
    out = tmp_path / "frames"
    run_host(out, png="all")
    expected = {}
    for line in (GOLDEN / "walk_png_sha256.txt").read_text().splitlines():
        frame, digest = line.split()
        expected[int(frame)] = digest

    for frame, digest in expected.items():
        data = (out / ("frame%04d.png" % frame)).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, "frame %d differs" % frame


@pytest.mark.parametrize("frame", [0, 20, 40, 60, 99])
def test_the_committed_sample_frames_are_the_ones_that_were_hashed(frame):
    """The five PNGs kept in the repo for eyeballing must be the same files the
    hash list describes, or the pictures and the contract drift apart."""
    committed = (GOLDEN / ("frame%04d.png" % frame)).read_bytes()
    digests = dict(line.split() for line in
                   (GOLDEN / "walk_png_sha256.txt").read_text().splitlines())
    assert hashlib.sha256(committed).hexdigest() == digests[str(frame)]


def test_the_rng_is_a_full_period_generator(lib):
    """A 16-bit xorshift with a broken triple degenerates into a short cycle,
    which would quietly stop being random long before anyone noticed."""
    import ctypes

    rng = blackice.Rng()
    lib.rng_seed.argtypes = [ctypes.POINTER(blackice.Rng), ctypes.c_uint16]
    lib.rng_next.argtypes = [ctypes.POINTER(blackice.Rng)]
    lib.rng_next.restype = ctypes.c_uint16
    lib.rng_below.argtypes = [ctypes.POINTER(blackice.Rng), ctypes.c_uint16]
    lib.rng_below.restype = ctypes.c_uint16

    lib.rng_seed(ctypes.byref(rng), 1)
    seen = set()
    for _ in range(65535):
        seen.add(lib.rng_next(ctypes.byref(rng)))
    assert len(seen) == 65535, "period is %d, not the full 65535" % len(seen)
    assert 0 not in seen

    lib.rng_seed(ctypes.byref(rng), 0)
    assert rng.state == CONST["RNG_DEFAULT_SEED"], "zero must not be accepted as a seed"

    lib.rng_seed(ctypes.byref(rng), 12345)
    assert all(lib.rng_below(ctypes.byref(rng), 6) < 6 for _ in range(500))


def test_the_walk_actually_opens_the_door(lib):
    """A golden test that only says 'the bytes are the same' can go green on a
    frozen picture.  This one asserts the walk does what it was written to do."""
    import ctypes

    level = blackice.parse_level(lib, LEVEL.read_text())
    state = blackice.new_state(lib, level)
    tokens = {"forward": CONST["INPUT_FORWARD"], "back": CONST["INPUT_BACK"],
              "turn_left": CONST["INPUT_TURN_LEFT"], "turn_right": CONST["INPUT_TURN_RIGHT"],
              "-": 0}
    script = []
    for line in SCRIPT.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        value = 0
        for token in parts[1:]:
            value |= tokens[token]
        script += [value] * int(parts[0])

    opened = set()
    for tick in range(FRAMES):
        lib.game_step(ctypes.byref(state), script[tick] if tick < len(script) else 0)
        for i in range(state.door_count):
            if state.doors[i].state != CONST["DOOR_STATE_CLOSED"]:
                opened.add(state.doors[i].cell)

    assert opened, "the scripted walk never opened a door"
    start = (level.start_cell_x, level.start_cell_y)
    moved = (state.player.x >> 8, state.player.y >> 8) != start
    assert moved, "the scripted walk never went anywhere"
