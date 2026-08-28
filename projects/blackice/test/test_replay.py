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
# The goldens are the SHIPPING width, and say so rather than inheriting it.
DETAIL = CONST["DETAIL_DEFAULT"]


def run_host(tmp_path, seed=None, png="none", level=LEVEL):
    tmp_path.mkdir(parents=True, exist_ok=True)
    hashes = tmp_path / "hashes.txt"
    command = [str(blackice.HOST_BIN), "--level", str(level), "--script", str(SCRIPT),
               "--frames", str(FRAMES), "--detail", str(DETAIL), "--out", str(tmp_path),
               "--png", png, "--hashes", str(hashes)]
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


def test_the_rng_is_the_design_lcg(lib):
    """DESIGN 4.3 names the generator exactly: a 32-bit LCG with Numerical
    Recipes' constants, handing out the HIGH half of the state because an LCG's
    low bits have a short period (bit 0 alternates).  Both halves of that claim
    are pinned here - the recurrence, and which half is published."""
    import ctypes

    rng = blackice.Rng()
    lib.rng_seed.argtypes = [ctypes.POINTER(blackice.Rng), ctypes.c_uint32]
    lib.rng_next.argtypes = [ctypes.POINTER(blackice.Rng)]
    lib.rng_next.restype = ctypes.c_uint16
    lib.rng_below.argtypes = [ctypes.POINTER(blackice.Rng), ctypes.c_uint16]
    lib.rng_below.restype = ctypes.c_uint16

    mask = 0xffffffff
    state = 12345
    lib.rng_seed(ctypes.byref(rng), state)
    assert rng.state == state, "a seed must be taken as given: every state is legal"
    for _ in range(1000):
        state = (state * CONST["RNG_MULTIPLIER"] + CONST["RNG_INCREMENT"]) & mask
        assert lib.rng_next(ctypes.byref(rng)) == state >> 16
        assert rng.state == state

    # The low bit of an LCG state alternates; the published half must not.
    lib.rng_seed(ctypes.byref(rng), 1)
    draws = [lib.rng_next(ctypes.byref(rng)) for _ in range(2000)]
    assert len(set(draws)) > 1900, "the published half is not mixing"

    lib.rng_seed(ctypes.byref(rng), 12345)
    assert all(lib.rng_below(ctypes.byref(rng), 6) < 6 for _ in range(500))


def test_the_walk_actually_opens_the_door(lib):
    """A golden test that only says 'the bytes are the same' can go green on a
    frozen picture.  This one asserts the walk does what it was written to do."""
    import ctypes

    level = blackice.parse_level(lib, LEVEL.read_text())
    state = blackice.new_state(lib, level)
    # One parser, shared with the host through its own token table.
    script = blackice.parse_script(SCRIPT.read_text())

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


def test_the_host_refuses_a_broken_script(lib, tmp_path):
    """A misspelled token used to be worth zero: the run silently became a
    different run and still passed.  Both halves of a script line are checked."""
    import subprocess

    for body, why in [("10 forwrad\n", "misspelled token"),
                      ("ten forward\n", "non-numeric repeat"),
                      ("0 forward\n", "zero repeat")]:
        script = tmp_path / "bad.txt"
        script.write_text(body)
        result = subprocess.run(
            [str(blackice.HOST_BIN), "--level", str(LEVEL), "--script", str(script),
             "--frames", "1", "--out", str(tmp_path), "--png", "none"],
            capture_output=True)
        assert result.returncode != 0, "the host accepted a script with a %s" % why


def test_the_suite_and_the_host_read_a_script_the_same_way(lib):
    """blackice.parse_script reads the host's own token table, so the two can
    disagree only if that table is not what the host compiles."""
    tokens = blackice.script_tokens()

    assert tokens["forward"] == CONST["INPUT_FORWARD"]
    assert tokens["throttle"] == CONST["INPUT_THROTTLE_NEXT"]
    assert "use" not in tokens, "DESIGN 6 has no use key"
    for name, bit in tokens.items():
        assert bin(bit).count("1") == 1, "%s is not a single input bit" % name

    script = blackice.parse_script(SCRIPT.read_text())
    assert len(script) == 100
    assert script[0] == CONST["INPUT_FORWARD"]
