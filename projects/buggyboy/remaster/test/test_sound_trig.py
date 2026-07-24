"""test_sound_trig.py — the slice-2 sound TRIGGER layer (src/sound_trig.c), differential vs recreate.

The trigger leaves (play_event_tune / handle_marker / stop_music / stop_music_chk) decide WHEN music
and effects start and stop. The leg / event / crash drives already compare them where the game itself
fires them (test_leg_drive / test_events / test_crash_fx now diff the SND_STATE + VBL enable + current
tune + the Dosound ledger). This suite pins the GUARD MATRIX the drives cannot reach — game-over, the
priority tune (cur_tune == 6 while music plays), handle_marker's cur_tune < 7 guard, stop_music_chk's
mzflag bail — directly against recreate's verified leaves (g_play_event_tune @0x11c7a / g_handle_marker
@0x11cb2 / g_stop_music @0x12ec4 / g_stop_music_chk @0x12ebc), plus the Dosound ledger's SENSITIVITY (a
wrong list id fails though the image is otherwise identical), mirroring recreate's own
test_dosound_ledger_sensitivity.

For each case we seed the two guard globals both sides (game_over @0x18c34, mzflag == SND_STATE+0x1e,
cur_tune @0x18cfa), build a candidate SoundDriver from the image, reset both Dosound ledgers, run the
oracle leaf (which mutates the image's SND_STATE / VBL vector / cur_tune / Dosound), run the candidate
leaf, and compare the candidate SoundDriver against the image's sound view + the two ledgers.
"""
import ctypes
from pathlib import Path

import adapter
import equiv                         # the shared sound-diff helpers (reset / streams / mismatch)
import harness                       # recreate's verified leaves (the oracle for this differential)
import pytest
from test_course_ring import _defines   # the tree's canonical #define parser (imported, not copied)

# sound.h's own #defines, parsed once — the source of truth for the mzflag offset + the Dosound list ids
# this file drives, so nothing here hand-copies a literal that could drift from the header.
_DEF_RE = r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)"
_SND_H = _defines(Path("include") / "sound.h", _DEF_RE)

A_game_over = adapter.A_game_over_flag                     # 0x18c34
A_mzflag = adapter.A_snd_state + _SND_H["SND_MUSIC_ON"]    # 0x1b07a
A_cur_tune = adapter.A_cur_tune_id                         # 0x18cfa

U8P = ctypes.POINTER(ctypes.c_uint8)
SDP = ctypes.POINTER(adapter.SoundDriver)

# The Dosound list offsets, from sound.h (the drive addresses them as SND_DOSOUND_BASE + offset).
LIST_COLLIDE = _SND_H["SND_DOSOUND_COLLIDE"]
LIST_CRASH = _SND_H["SND_DOSOUND_CRASH"]
LIST_IDLE = _SND_H["SND_DOSOUND_IDLE"]
LIST_BEEP = _SND_H["SND_DOSOUND_BEEP"]
LIST_GO = _SND_H["SND_DOSOUND_GO"]


def _bind():
    o = harness._lib
    for name in ("g_play_event_tune", "g_handle_marker", "g_stop_music", "g_stop_music_chk"):
        fn = getattr(o, name)
        fn.argtypes = [U8P, ctypes.c_uint32]
        fn.restype = None

    c = ctypes.CDLL(str(adapter.LIBREMASTER))
    for name in ("rm_play_event_tune", "rm_handle_marker"):
        getattr(c, name).argtypes = [SDP, ctypes.c_uint32, ctypes.c_bool]
        getattr(c, name).restype = None
    for name in ("rm_stop_music", "rm_stop_music_chk"):
        getattr(c, name).argtypes = [SDP, ctypes.c_uint16, ctypes.c_bool]
        getattr(c, name).restype = None
    c.rm_pause_silence.argtypes = [SDP]
    c.rm_pause_silence.restype = None
    c.rm_dosound_reset.restype = None
    c.rm_dosound_count.restype = ctypes.c_uint32
    c.rm_dosound_args.restype = ctypes.POINTER(ctypes.c_uint32)
    return o, c


_ORACLE, _CAND = _bind()


def _seed(image, game_over, mzflag, cur_tune):
    """Seed the two guard globals both sides (the image drives the oracle; the candidate SoundDriver is
    built from the same bytes below)."""
    image[A_game_over] = (game_over >> 8) & 0xff
    image[A_game_over + 1] = game_over & 0xff
    image[A_mzflag] = mzflag & 0xff
    image[A_cur_tune] = (cur_tune >> 8) & 0xff
    image[A_cur_tune + 1] = cur_tune & 0xff


def _run(oracle_call, cand_call, game_over=0, mzflag=0, cur_tune=0):
    """Seed the guards, snapshot the candidate driver, run both leaves, and return the sound mismatches
    (name, cand, ref) + the two Dosound ledgers, via the shared equiv helpers (one comparator, one reset,
    one stream reader — not a second inline copy)."""
    image = harness.make_image()
    _seed(image, game_over, mzflag, cur_tune)
    snd = adapter.sound_driver(image)                 # copies the seeded SND_STATE / vbl / cur_tune
    equiv._sound_reset(_CAND)                          # fresh ledgers both sides (recreate global + candidate)
    buf = (ctypes.c_uint8 * len(image)).from_buffer(image)
    oracle_call(buf)
    cand_call(snd, bool(game_over))
    out = equiv._driver_sound_mismatches(snd, image)  # SND_STATE header + voices + vbl + cur_tune
    return out, equiv._dosound_streams(_CAND)          # (candidate, reference) ordered streams


# ---- play_event_tune: the priority / game-over guard matrix ----

@pytest.mark.parametrize("tune", [0, 1, 2, 3, 4, 5, 6, 8, 9, 0xa])
@pytest.mark.parametrize("game_over,mzflag,cur_tune", [
    (0, 0, 0),      # open guard -> INITTUNE lands + vbl running + cur_tune = tune
    (0, 0xff, 0),   # music playing, cur_tune != 6 -> still runs (mzflag doesn't block play_event_tune)
    (0, 0xff, 6),   # PRIORITY: cur_tune == 6 && music -> vbl set, then bails (no INITTUNE, cur_tune stays 6)
    (0, 0, 6),      # cur_tune == 6 but no music -> runs
    (1, 0, 0),      # game-over -> the whole leaf is a no-op
])
def test_play_event_tune(tune, game_over, mzflag, cur_tune):
    out, (c_led, o_led) = _run(
        lambda b: _ORACLE.g_play_event_tune(b, tune),
        lambda s, go: _CAND.rm_play_event_tune(s, tune, go),
        game_over=game_over, mzflag=mzflag, cur_tune=cur_tune)
    assert not out, f"play_event_tune tune={tune} go={game_over} mz={mzflag} cur={cur_tune}: {out}"
    assert c_led == o_led, f"play_event_tune ledger {c_led} != {o_led}"   # (never Dosounds)


# ---- handle_marker: the cur_tune < 7 / game-over guard matrix ----

@pytest.mark.parametrize("fx", [0, 1, 3, 5, 6, 8])
@pytest.mark.parametrize("game_over,mzflag,cur_tune", [
    (0, 0, 0),      # open -> TURNOFF + INITFX
    (0, 0xff, 3),   # cur_tune < 7 && music -> guarded, no-op
    (0, 0xff, 7),   # cur_tune >= 7 bypasses the music guard -> runs
    (0, 0, 3),      # cur_tune < 7 but no music -> runs
    (1, 0, 0),      # game-over -> no-op
])
def test_handle_marker(fx, game_over, mzflag, cur_tune):
    out, (c_led, o_led) = _run(
        lambda b: _ORACLE.g_handle_marker(b, fx),
        lambda s, go: _CAND.rm_handle_marker(s, fx, go),
        game_over=game_over, mzflag=mzflag, cur_tune=cur_tune)
    assert not out, f"handle_marker fx={fx} go={game_over} mz={mzflag} cur={cur_tune}: {out}"
    assert c_led == o_led


# ---- stop_music / stop_music_chk: the mzflag / game-over guard + the Dosound ledger ----

@pytest.mark.parametrize("lst", [LIST_COLLIDE, LIST_CRASH, LIST_IDLE, LIST_BEEP, LIST_GO])
@pytest.mark.parametrize("game_over,mzflag", [(0, 0), (0, 0xff), (1, 0)])
def test_stop_music(lst, game_over, mzflag):
    out, (c_led, o_led) = _run(
        lambda b: _ORACLE.g_stop_music(b, adapter.SND_DOSOUND_BASE + lst),
        lambda s, go: _CAND.rm_stop_music(s, lst, go),
        game_over=game_over, mzflag=mzflag)
    assert not out, f"stop_music list={lst:#x} go={game_over} mz={mzflag}: {out}"
    assert c_led == o_led, f"stop_music ledger {c_led} != {o_led}"


@pytest.mark.parametrize("lst", [LIST_IDLE, LIST_CRASH])
@pytest.mark.parametrize("game_over,mzflag", [(0, 0), (0, 0xff), (1, 0)])
def test_stop_music_chk(lst, game_over, mzflag):
    out, (c_led, o_led) = _run(
        lambda b: _ORACLE.g_stop_music_chk(b, adapter.SND_DOSOUND_BASE + lst),
        lambda s, go: _CAND.rm_stop_music_chk(s, lst, go),
        game_over=game_over, mzflag=mzflag)
    assert not out, f"stop_music_chk list={lst:#x} go={game_over} mz={mzflag}: {out}"
    assert c_led == o_led


# ---- rm_pause_silence: the Help-key pause silence (main @0x10100:293-300) ----
# There is no recreate g_* leaf for this (the Help pause is main-level code, not a decompiled export), so
# it is unit-pinned: seed every field it touches ACTIVE, silence, and check the cleared state.

def test_pause_silence():
    """rm_pause_silence silences the driver for a Help pause: mzflag + the music byte, the effect flag and
    the envelope generator all cleared, but the VBL pump left RUNNING (pointed at REFRESH) so it plays
    silence rather than being parked — unlike rm_stop_music, which parks the vector."""
    snd = adapter.sound_driver(harness.make_image())
    snd.state.header[_SND_H["SND_MUSIC_ON"]] = 0xff      # mzflag: music master enable
    snd.state.header[_SND_H["SND_MUSIC_BYTE"]] = 0xff    # music-playing byte (TURNOFF/EGOFF clear it)
    snd.state.header[_SND_H["SND_FX_FLAG"]] = 0xff       # effect active
    snd.state.header[_SND_H["SND_EG_FLAG"]] = 0xff       # envelope generator active
    snd.vbl_enable = adapter.RM_VBL_PARKED               # start PARKED to prove it is set RUNNING
    _CAND.rm_pause_silence(ctypes.byref(snd))
    assert snd.state.header[_SND_H["SND_MUSIC_ON"]] == 0, "mzflag not cleared"
    assert snd.state.header[_SND_H["SND_MUSIC_BYTE"]] == 0, "music byte not cleared"
    assert snd.state.header[_SND_H["SND_FX_FLAG"]] == 0, "fxflag not cleared"
    assert snd.state.header[_SND_H["SND_EG_FLAG"]] == 0, "EG flag not cleared"
    assert snd.vbl_enable == adapter.RM_VBL_RUNNING, "VBL pump parked, not left RUNNING"


def test_pause_silence_lock_balanced():
    """The multi-store publish is bracketed atomically (like rm_stop_music) so the 50 Hz VBL pump never
    refreshes a half-silenced record: exactly one balanced RM_SOUND_LOCK / RM_SOUND_UNLOCK pair. (On the
    host build the locks are no-ops, so balance is pinned structurally in the source.)"""
    src = (Path("src") / "sound_trig.c").read_text()
    start = src.index("void rm_pause_silence(")
    body = src[start:src.index("\n}", start)]            # the body has no nested braces
    assert body.count("RM_SOUND_LOCK()") == 1 and body.count("RM_SOUND_UNLOCK()") == 1, body


# ---- cross-language source-of-truth pins for the hand-copied slice-2 constants ----
# _DEF_RE / _SND_H are parsed at the top of this file (the mzflag offset + Dosound ids use them).
_EVENTS_C = _defines(Path("src") / "events.c", _DEF_RE)
_FLOW_C = _defines(Path("src") / "flow.c", _DEF_RE)
_REC_SND = _defines(Path("src") / "sound.c", _DEF_RE, base=adapter.RECREATE)
_REC_ADDRS = _defines(Path("include") / "addrs.h", _DEF_RE, base=adapter.RECREATE)
_REC_EVT = _defines(Path("src") / "events.c", _DEF_RE, base=adapter.RECREATE)
_REC_GU = _defines(Path("src") / "game_update.c", _DEF_RE, base=adapter.RECREATE)
_REC_HS = _defines(Path("src") / "highscore.c", _DEF_RE, base=adapter.RECREATE)
_SND_TRIG_C = _defines(Path("src") / "sound_trig.c", _DEF_RE)
_REC_OS = _defines(Path("src") / "os.c", _DEF_RE, base=adapter.RECREATE)


def test_python_constants_match_the_c():
    """Every value this slice hand-copies is pinned to its one source of truth (CLAUDE.md §5)."""
    # adapter's sound layout / addresses vs the C header + recreate's image bases.
    assert adapter.SND_STATE_BYTES == _SND_H["SND_STATE_BYTES"]
    assert adapter.SND_VOICES == _SND_H["SND_VOICES"]
    assert adapter.SND_VOICE_STRIDE == _SND_H["SND_VOICE_STRIDE"]
    assert adapter.SND_DOSOUND_BASE == _SND_H["SND_DOSOUND_BASE"]
    assert adapter.A_snd_state == _REC_SND["SND_STATE"]
    assert adapter.A_snd_voice_ctrl == _REC_SND["SND_VOICE_CTRL"]
    assert adapter.A_vbl_sound_vec == _REC_ADDRS["A_vbl_sound_vec"]
    assert adapter.A_refresh == _REC_ADDRS["A_refresh"]
    assert adapter.A_cur_tune_id == _REC_ADDRS["A_cur_tune_id"]
    # the Dosound list offsets (this file + sound.h) == the recreate list addresses minus the base.
    for name, off in (("A_dosound_collide", LIST_COLLIDE), ("A_dosound_crash", LIST_CRASH),
                      ("A_dosound_idle", LIST_IDLE), ("A_dosound_beep", LIST_BEEP),
                      ("A_dosound_go", LIST_GO)):
        assert off == _REC_ADDRS[name] - adapter.SND_DOSOUND_BASE, name
    # the guard ids vs recreate's events.c.
    assert _SND_H["SND_TUNE_PRIORITY"] == _REC_EVT["TUNE_PRIORITY"]
    assert _SND_H["SND_MARKER_TUNE_MIN"] == _REC_EVT["MARKER_TUNE_MIN"]
    # the wired tune ids vs recreate's own #defines (events.c / game_update.c / highscore.c).
    assert _EVENTS_C["RM_TUNE_FLAG_BONUS"] == _REC_EVT["FLAG_TUNE_BONUS"]
    assert _EVENTS_C["RM_TUNE_FLAG_NORMAL"] == _REC_EVT["FLAG_TUNE_NORMAL"]
    assert _EVENTS_C["RM_TUNE_SCORE_MSG"] == _REC_GU["GU_SCORE_TUNE"]
    assert _EVENTS_C["RM_TUNE_CKPT_COUNTER"] == _REC_GU["GU_CKPT_TUNE"]
    assert _EVENTS_C["RM_TUNE_EVT_A"] == _REC_GU["GU_EVT_TUNE_A"]
    assert _EVENTS_C["RM_TUNE_CKPT_PASS"] == _REC_GU["GU_TUNE_CKPT_PASS"]
    assert _EVENTS_C["RM_TUNE_LEG_END"] == _REC_GU["GU_TUNE_LEG_END"]
    assert _EVENTS_C["RM_TUNE_COLL_MARK"] == _REC_GU["GU_TUNE_COLL_MARK"]
    assert _FLOW_C["RM_TUNE_GAME_OVER"] == _REC_HS["TUNE_GAME_OVER"]
    assert _FLOW_C["RM_TUNE_RANK1"] == _REC_HS["TUNE_RANK1"]
    assert _FLOW_C["RM_TUNE_OTHER"] == _REC_HS["TUNE_OTHER"]
    # RM_TUNE_GET_READY has no recreate #define (ip_start_leg passes the literal 0 to g_play_event_tune);
    # pin it against that single call site's argument (intermission.c @0x2c96). Prefer the pin over prose.
    import re
    _int_c = (adapter.RECREATE / "src" / "intermission.c").read_text()
    _gets = re.findall(r"g_play_event_tune\(image,\s*(\d+)\)", _int_c)
    assert len(_gets) == 1, f"expected one g_play_event_tune call in intermission.c, got {_gets}"
    assert _FLOW_C["RM_TUNE_GET_READY"] == int(_gets[0])
    # The two Dosound ledgers are fixed-size; pin the remaster cap == the recreate cap == the value the
    # drive harness compares against (equiv.DOSOUND_LEDGER_CAP), so a stream can't silently truncate on
    # one side only (fix: the drive fails loudly at the cap instead of comparing blind).
    assert _SND_TRIG_C["RM_DOSOUND_LOG_MAX"] == _REC_OS["MAX_DOSOUND_LOG"] == equiv.DOSOUND_LEDGER_CAP


def test_dosound_ledger_sensitivity():
    """A candidate Dosound with the WRONG list fails the ledger diff though the SND_STATE is byte-identical
    (mirrors recreate's test_dosound_ledger_sensitivity). The oracle stops with the beep list; the
    candidate is given the 'go' list — same image effect, divergent ledger."""
    out, (c_led, o_led) = _run(
        lambda b: _ORACLE.g_stop_music(b, adapter.SND_DOSOUND_BASE + LIST_BEEP),
        lambda s, go: _CAND.rm_stop_music(s, LIST_GO, go))
    assert not out, f"the SND_STATE should be identical (only the Dosound A0 differs): {out}"
    assert c_led != o_led, "wrong Dosound list must diverge the ledger"
    assert o_led == [adapter.SND_DOSOUND_BASE + LIST_BEEP]
    assert c_led == [adapter.SND_DOSOUND_BASE + LIST_GO]
