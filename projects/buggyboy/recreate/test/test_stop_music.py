"""Differential tests for stop_music @ 0x12ec4 and stop_music_chk @ 0x12ebc.

Both silence the sound driver unless a game-over is latched: TURNOFF the music state, clear the
effect flag / current tune, park vbl_sound_vec at the local rts (0x12ef4), then issue XBIOS
Dosound (hardware-only, no image effect). stop_music_chk additionally bails when music is playing
(MZFLAG != 0). The tests stage the affected globals with noise and diff the whole image across the
guard combinations; the Dosound trap validates the shim's XBIOS 0x20 handling.
"""
import ctypes
import random

import harness
from harness import differential, report

STOP_MUSIC = 0x12ec4
STOP_MUSIC_CHK = 0x12ebc

A_GAME_OVER = 0x18c34          # word guard
A_VBL_SOUND_VEC = 0x18c0c      # long -> parked at 0x12ef4
A_CUR_TUNE_ID = 0x18cfa        # word -> 0
A_MZFLAG = 0x1b07a             # byte (TURNOFF clears; chk reads it as a guard)
A_FXFLAG = 0x1b07b             # byte -> 0
SND_MUSIC_BYTE = 0x1b063       # SND_STATE + 0x07 -> 0
SND_MUSIC_WORD = 0x1b064       # SND_STATE + 0x08 -> 0 (word)

for name in ("g_stop_music", "g_stop_music_chk"):
    fn = getattr(harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]  # (image, dosound list_off)
    fn.restype = None


def _pokes(game_over, mzflag, seed):
    rng = random.Random(seed)
    nz = lambda n: bytes(rng.randrange(1, 256) for _ in range(n))
    return {
        A_GAME_OVER: game_over.to_bytes(2, "big"),
        A_MZFLAG: bytes([mzflag]),
        A_FXFLAG: nz(1),
        A_CUR_TUNE_ID: nz(2),
        A_VBL_SOUND_VEC: nz(4),
        SND_MUSIC_BYTE: nz(1),
        SND_MUSIC_WORD: nz(2),
    }


def _check(entry, glue, game_over, mzflag, seed, label):
    regs = {"_pokes": _pokes(game_over, mzflag, seed)}
    diffs, _ = differential(entry, regs, glue, poison=True)
    assert not diffs, f"{label} game_over={game_over} mzflag={mzflag} seed={seed}\n{report(diffs[:12])}"


def test_stop_music():
    glue = lambda l, b: l.g_stop_music(b, 0)   # list_off irrelevant: Dosound is off-image (no-op here)
    for seed in range(12):
        _check(STOP_MUSIC, glue, game_over=0, mzflag=seed & 0xff, seed=seed, label="stop_music/active")
    for seed in range(4):
        _check(STOP_MUSIC, glue, game_over=1 + seed, mzflag=0x11, seed=seed, label="stop_music/game_over")


def test_stop_music_chk():
    glue = lambda l, b: l.g_stop_music_chk(b, 0)
    for seed in range(12):
        _check(STOP_MUSIC_CHK, glue, game_over=0, mzflag=0, seed=seed, label="chk/run")
    for seed in range(6):
        _check(STOP_MUSIC_CHK, glue, game_over=0, mzflag=1 + seed, seed=seed, label="chk/music-playing")
    for seed in range(4):
        _check(STOP_MUSIC_CHK, glue, game_over=1, mzflag=0, seed=seed, label="chk/game_over")


# --- main race-start Dosound (0x10222) + the ledger's sensitivity (improvement #2) ----------------
# main loads A0 = A_dosound_beep then calls stop_music (0x10222), which Dosounds the leg-start
# countdown beeps. main isn't run end-to-end, so enter at the a0-load (0x1021c) and stop just after
# stop_music returns. The image diff can't see the off-image Dosound(A0); the side-effect ledger does,
# so this both covers the 0x10222 call site and verifies its A0 is A_dosound_beep.
MAIN_BEEP_ENTRY, MAIN_BEEP_STOP = 0x1021c, 0x10226
A_DOSOUND_BEEP, A_DOSOUND_GO = 0x18bba, 0x18bca


def test_main_racestart_dosound():
    regs = {"_pokes": {A_GAME_OVER: b"\x00\x00", A_MZFLAG: b"\x00"}}
    diffs, _ = differential(MAIN_BEEP_ENTRY, regs,
                            lambda l, b: l.g_stop_music(b, A_DOSOUND_BEEP), stop_pc=MAIN_BEEP_STOP)
    assert not diffs, report(diffs[:12])


def test_dosound_ledger_sensitivity():
    """A candidate Dosound with the wrong list fails the ledger though the image is byte-identical."""
    import pytest
    with pytest.raises(AssertionError, match="Dosound ledger mismatch"):
        differential(MAIN_BEEP_ENTRY, {"_pokes": {A_GAME_OVER: b"\x00\x00"}},
                     lambda l, b: l.g_stop_music(b, A_DOSOUND_GO), stop_pc=MAIN_BEEP_STOP)
