"""Packer tests, including the one that actually matters: Python packs, the C depacker that
ships with the engine unpacks, and the bytes come back identical. A pure-Python round-trip
would only prove lz_pack agrees with lz_unpack, not that the engine can read the archive."""
import shutil
import struct
import subprocess

import numpy as np
import pytest

from stepix.pack import (MAX_MATCH, METHOD_LZSS, METHOD_STORED, MIN_MATCH, PAK_ALIGNMENT,
                         PAK_ENTRY_BYTES, PAK_HEADER_BYTES, PAK_MAGIC, WINDOW_SIZE, build_pak,
                         extract, lz_pack, lz_unpack, read_pak, read_pak_directory)

ASSETS_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent
C_SOURCES = ["depack.c", "depack_main.c"]
M68K_COMPILER = "m68k-elf-gcc"          # the target build; the host build proves nothing about -m68000
C_EXIT_BAD_STREAM = 3                   # EXIT_BAD_STREAM in depack_main.c

# Hand-built malformed streams, one per failure mode the depacker has to survive.
BAD_OFFSET_STREAM = bytes([0x00, 0x00, 0x00])           # first token is a match, offset 1, output empty
OVERSHOOT_STREAM = bytes([0x80, 0x41, 0xF0, 0x00])      # literal 'A', then an 18-byte run into 4 bytes of room
OVERSHOOT_RAW_LEN = 5
OVERSHOOT_EXPECTED = b"AAAAA"                           # the run clamped to raw_len, in both twins


def _corpus():
    rng = np.random.default_rng(0x5150)
    return {
        "ZEROS": bytes(4096),
        "REPEAT": b"ABCD" * 1000,
        "TEXT": b"the quick brown fox jumps over the lazy dog. " * 40,
        "RANDOM": rng.integers(0, 256, 3000, dtype=np.uint8).tobytes(),
        "MIXED": (b"xyz" * 100 + rng.integers(0, 4, 400, dtype=np.uint8).tobytes()) * 3,
        "ONEBYTE": b"Q",
        "EMPTY": b"",
        "RUN": bytes([0xAB]) * (MAX_MATCH * 5),         # exercises overlapping self-referential matches
    }


@pytest.mark.parametrize("name", sorted(_corpus()))
def test_python_round_trip(name):
    data = _corpus()[name]
    assert lz_unpack(lz_pack(data), len(data)) == data


@pytest.mark.parametrize("size", [0, 1, 2, MIN_MATCH, MIN_MATCH - 1, MAX_MATCH, MAX_MATCH + 1, WINDOW_SIZE, WINDOW_SIZE + 1])
def test_round_trip_at_the_format_boundaries(size):
    """Sizes either side of every field limit: min/max match and the 12-bit window."""
    data = bytes(range(256)) * (size // 256 + 1)
    data = data[:size]
    assert lz_unpack(lz_pack(data), len(data)) == data


@pytest.mark.parametrize("seed", range(12))
def test_round_trip_on_fuzzed_data(seed):
    rng = np.random.default_rng(seed)
    alphabet = int(rng.integers(1, 256))
    data = rng.integers(0, alphabet, int(rng.integers(0, 5000)), dtype=np.uint8).tobytes()
    assert lz_unpack(lz_pack(data), len(data)) == data


def test_repetitive_data_compresses_hard():
    data = _corpus()["ZEROS"]
    assert len(lz_pack(data)) < len(data) // 4


def test_incompressible_data_is_stored_in_the_archive():
    blob = build_pak({"RANDOM": _corpus()["RANDOM"]})
    entry = read_pak_directory(blob)[0]
    assert entry.method == METHOD_STORED
    assert entry.packed_len == entry.raw_len


def test_truncated_stream_is_rejected():
    packed = lz_pack(_corpus()["TEXT"])
    with pytest.raises(ValueError):
        lz_unpack(packed[:5], len(_corpus()["TEXT"]))


def test_match_reaching_before_the_output_start_is_rejected():
    """A hand-built stream whose first token is a match: the depacker must not read behind dst."""
    stream = bytes([0x00]) + struct.pack(">H", (0 << 12) | 0)
    with pytest.raises(ValueError):
        lz_unpack(stream, MIN_MATCH)


# ---- archive ------------------------------------------------------------------------
def test_pak_header_and_directory_layout():
    corpus = _corpus()
    blob = build_pak(corpus)
    magic, version, count = struct.unpack_from(">4sHH", blob, 0)
    assert magic == PAK_MAGIC and version == 1 and count == len(corpus)
    assert PAK_HEADER_BYTES == 8 and PAK_ENTRY_BYTES == 24

    for position, name in enumerate(corpus):
        fields = struct.unpack_from(">8sIIIHH", blob, PAK_HEADER_BYTES + position * PAK_ENTRY_BYTES)
        assert fields[0].rstrip(b"\0").decode() == name
        assert fields[5] == 0                                   # reserved word stays zero


def test_pak_round_trip():
    corpus = _corpus()
    assert read_pak(build_pak(corpus)) == corpus


def test_pak_round_trip_uncompressed():
    corpus = _corpus()
    blob = build_pak(corpus, compress=False)
    assert all(entry.method == METHOD_STORED for entry in read_pak_directory(blob))
    assert read_pak(blob) == corpus


def test_every_payload_is_word_aligned():
    """The 68000 reads these blobs with word and long moves; an odd offset is a bus error."""
    blob = build_pak(_corpus())
    for entry in read_pak_directory(blob):
        assert entry.offset % PAK_ALIGNMENT == 0, entry.name


def test_entries_stay_inside_the_archive():
    blob = build_pak(_corpus())
    for entry in read_pak_directory(blob):
        assert entry.offset + entry.packed_len <= len(blob)


def test_ratio_is_reported_per_entry():
    blob = build_pak({"ZEROS": _corpus()["ZEROS"]})
    entry = read_pak_directory(blob)[0]
    assert 0.0 < entry.ratio < 0.5 and entry.method == METHOD_LZSS


def test_long_name_rejected():
    with pytest.raises(ValueError):
        build_pak({"TOOLONGNAME": b"x"})


def test_unknown_method_rejected():
    blob = bytearray(build_pak({"ZEROS": _corpus()["ZEROS"]}))
    entry = read_pak_directory(bytes(blob))[0]
    struct.pack_into(">H", blob, PAK_HEADER_BYTES + 20, 99)
    with pytest.raises(ValueError):
        extract(bytes(blob), read_pak_directory(bytes(blob))[0])
    assert entry.method == METHOD_LZSS


def test_bad_magic_rejected():
    with pytest.raises(ValueError):
        read_pak_directory(b"NOPE" + build_pak({"A": b"x"})[4:])


# ---- the C depacker -----------------------------------------------------------------
@pytest.fixture(scope="module")
def c_depacker(tmp_path_factory):
    """Compile depack.c natively.

    A missing compiler FAILS rather than skips: these are the only tests that prove the engine
    can read what Python packs, and a skip takes them all away while the run still exits 0.
    """
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.fail("no C compiler (cc, gcc or clang) on PATH: the C depacker cross-check cannot run")
    binary = tmp_path_factory.mktemp("cdepack") / "depack_main"
    subprocess.run([compiler, "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(binary)]
                   + [str(ASSETS_DIR / source) for source in C_SOURCES], check=True)
    return binary


def _run_c_depack(binary, tmp_path, packed: bytes, raw_len: int) -> tuple[int, bytes]:
    """Run the C depacker and return (exit status, output bytes); no output file means b''."""
    packed_path = tmp_path / "in.lz"
    out_path = tmp_path / "out.bin"
    packed_path.write_bytes(packed)
    result = subprocess.run([str(binary), str(packed_path), str(raw_len), str(out_path)], capture_output=True)
    return result.returncode, out_path.read_bytes() if out_path.exists() else b""


def _c_depack(binary, tmp_path, packed: bytes, raw_len: int) -> bytes:
    status, data = _run_c_depack(binary, tmp_path, packed, raw_len)
    assert status == 0, f"depack_main exited {status}"
    return data


@pytest.mark.parametrize("name", sorted(_corpus()))
def test_c_depacker_matches_python(c_depacker, tmp_path, name):
    data = _corpus()[name]
    assert _c_depack(c_depacker, tmp_path, lz_pack(data), len(data)) == data


@pytest.mark.parametrize("seed", range(8))
def test_c_depacker_on_fuzzed_data(c_depacker, tmp_path, seed):
    rng = np.random.default_rng(1000 + seed)
    data = rng.integers(0, int(rng.integers(2, 256)), int(rng.integers(1, 4000)), dtype=np.uint8).tobytes()
    assert _c_depack(c_depacker, tmp_path, lz_pack(data), len(data)) == data


def test_c_depacker_on_real_generated_assets(c_depacker, tmp_path):
    """The demo's own textures and screen -- real data, not just synthetic corpora."""
    from stepix.demo_assets import build_demo_assets
    from stepix.planar import screen_to_planar
    from stepix.texture import pack_textures

    assets = build_demo_assets()
    for data in (pack_textures(assets.textures, assets.shade_table), screen_to_planar(assets.backdrop)):
        assert _c_depack(c_depacker, tmp_path, lz_pack(data), len(data)) == data


# ---- the C depacker on malformed streams --------------------------------------------
def test_both_twins_reject_a_match_reaching_before_the_output(c_depacker, tmp_path):
    """The C used to read behind dst here; Python always raised. Both must refuse."""
    status, _ = _run_c_depack(c_depacker, tmp_path, BAD_OFFSET_STREAM, MIN_MATCH)
    assert status == C_EXIT_BAD_STREAM
    with pytest.raises(ValueError):
        lz_unpack(BAD_OFFSET_STREAM, MIN_MATCH)


def test_both_twins_clamp_a_match_that_overshoots_raw_len(c_depacker, tmp_path):
    """The C used to write 13 bytes past dst+raw_len here; Python clamped. Both must clamp."""
    status, data = _run_c_depack(c_depacker, tmp_path, OVERSHOOT_STREAM, OVERSHOOT_RAW_LEN)
    assert status == 0
    assert data == OVERSHOOT_EXPECTED == lz_unpack(OVERSHOOT_STREAM, OVERSHOOT_RAW_LEN)


def test_both_twins_reject_a_truncated_stream(c_depacker, tmp_path):
    """The C now knows packed_len, so it stops instead of reading past the end of the buffer."""
    data = _corpus()["TEXT"]
    truncated = lz_pack(data)[:5]
    status, _ = _run_c_depack(c_depacker, tmp_path, truncated, len(data))
    assert status == C_EXIT_BAD_STREAM
    with pytest.raises(ValueError):
        lz_unpack(truncated, len(data))


def test_depack_c_builds_for_the_68000(tmp_path):
    """depack.c is the one file that ships to the target: a host-only build proves nothing."""
    compiler = shutil.which(M68K_COMPILER)
    if compiler is None:
        pytest.skip(f"{M68K_COMPILER} not on PATH: the target build of depack.c was NOT checked")
    subprocess.run([compiler, "-m68000", "-Os", "-Wall", "-Wextra", "-Werror", "-c",
                    str(ASSETS_DIR / "depack.c"), "-o", str(tmp_path / "depack.o")], check=True)
    assert (tmp_path / "depack.o").is_file()


# ---- resource names ------------------------------------------------------------------
def test_names_that_collide_once_upper_cased_are_rejected():
    """{'font', 'FONT'} wrote two entries called FONT: read_pak kept the last, the engine
    would have found the first."""
    with pytest.raises(ValueError, match="collides"):
        build_pak({"font": b"one", "FONT": b"two"})


def test_names_are_folded_to_the_on_disk_form():
    assert read_pak_directory(build_pak({"font": b"data"}))[0].name == "FONT"


def test_read_pak_inverts_build_pak_for_upper_case_names():
    """The round-trip invariant the demo build relies on, stated as its own test."""
    corpus = _corpus()
    assert all(name == name.upper() for name in corpus)
    assert read_pak(build_pak(corpus)) == corpus
