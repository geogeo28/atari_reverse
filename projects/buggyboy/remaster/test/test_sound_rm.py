"""test_sound_rm.py — the REFRESH sound driver's STATE side (src/sound.c), differential vs recreate.

The remaster owns the driver state in a native SoundState struct and reads the const tables + tune
note streams from a baked blob (render/atari/build/sound_data.h), instead of threading recreate's flat
image. This
suite pins the port against recreate's verified sound cores (`g_INITTUNE` / `g_INITFX` / `g_REFRESH`,
themselves byte-exact vs the 68000): for every valid tune id and fx id it seeds BOTH sides, then steps
REFRESH frame-by-frame, comparing on each frame

  * the PSG (reg, value) write stream — the driver's sole observable output (its YM2149 seam), and
  * the whole driver state — because the port deliberately keeps SoundState's byte layout identical to
    recreate's SND_STATE / SND_VOICE_CTRL regions, the state compares directly, catching any internal
    divergence that a given frame's stream happens not to surface.

Coverage: tunes 0..10 (all 11 records; ids 1-8 are the game's event/jingle tunes) and fx 0..9 (the 9
real records plus fx 9's bss-zero record, which INITFX(9) reads on the real machine) — INITTUNE/INITFX
alone, then REFRESH stepped SCENARIO_FRAMES per tune (loop-point + end-tune reached), the engine-EG
path (EGFLAG + engfreq sweep) alone and over music, TURNOFF/EGOFF mid-tune, and fx-over-music.

Two by-hand mutation sanity checks (each diverged the differential, as expected):
  1. Perturbed one SND_CONST byte in the tune-0 note stream (the generated sound_data.h byte at the
     offset for Ghidra 0x1b7d4 flipped) -> test_refresh_music tune=0 failed on a PSG-stream mismatch
     within a few frames. Reverted.
  2. Off-by-one in the port: changed rm_refresh's SND_TEMPO_RELOAD reload to 5 -> test_refresh_music
     diverged on every tune (tempo prescaler drifts, note stream advances a frame early). Reverted.
"""
import ctypes
import random
import sys
from pathlib import Path

import adapter
import harness                       # recreate's verified cores (the oracle for this differential)
from test_course_ring import _defines   # the tree's canonical #define parser (imported, not copied)

sys.path.insert(0, str(Path(adapter.REMASTER) / "render" / "atari"))
import gen_sound_fixture as gen      # noqa: E402  loader-only; pins the generator's window constants

# ---- single-source constants: sound.h (candidate layout) + recreate/src/sound.c (image bases) ----
# Parsed rather than hand-copied, so an offset fix in either source reaches this differential instead
# of leaving it arming the wrong byte on both sides (the CLAUDE.md cross-language one-source rule).
_DEF_RE = r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)"
_SND_H = _defines(Path("include") / "sound.h", _DEF_RE)
_REC = _defines(Path("src") / "sound.c", _DEF_RE, base=adapter.RECREATE)

SND_STATE = _REC["SND_STATE"]                     # 0x1b05c: the driver state block in the oracle image
SND_VOICE_CTRL = _REC["SND_VOICE_CTRL"]           # 0x1b64a: the three voice records in the oracle image
SND_STATE_BYTES = _SND_H["SND_STATE_BYTES"]
SND_VOICES = _SND_H["SND_VOICES"]
SND_VOICE_STRIDE = _SND_H["SND_VOICE_STRIDE"]
VC_ENV_FLG = _SND_H["SND_VC_ENV_FLG"]
A_egflag = SND_STATE + _SND_H["SND_EG_FLAG"]      # 0x1b07c
A_eg_p1 = SND_STATE + _SND_H["SND_EG_P1"]         # engfreq
A_eg_vol = SND_STATE + _SND_H["SND_EG_VOL"]
A_eg_phase = SND_STATE + _SND_H["SND_EG_PHASE"]
A_music_on = SND_STATE + _SND_H["SND_MUSIC_ON"]   # mzflag
A_fxflag = SND_STATE + _SND_H["SND_FX_FLAG"]
PSG_STAGING_BYTES = _SND_H["SND_ENV_SHAPE"] + 1   # staging bytes 0x00..SND_ENV_SHAPE the dump reads

PSG_CAP = 64                         # max PSG writes captured per frame (driver emits <= 14)
SCENARIO_FRAMES = 300                # enough for every tune to reach its loop point / end-tune
TUNE_IDS = range(0, 11)              # all 11 tune records
FX_IDS = range(0, 10)               # 9 real fx records + fx 9's bss-zero record


# adapter owns the one ctypes mirror of the C SoundState; reuse it here rather than a second copy. Pin
# adapter's hand-copied geometry against this file's _defines-parsed sizes so a layout change in either
# source is caught (the CLAUDE.md one-source rule — the two must not drift silently).
SoundState = adapter.SoundState
_SS_FIELDS = dict(adapter.SoundState._fields_)
assert ctypes.sizeof(_SS_FIELDS["header"]) == SND_STATE_BYTES
assert ctypes.sizeof(_SS_FIELDS["voice"]) == SND_VOICES * SND_VOICE_STRIDE
assert ctypes.sizeof(adapter.SoundState) == SND_STATE_BYTES + SND_VOICES * SND_VOICE_STRIDE


U8P = ctypes.POINTER(ctypes.c_uint8)
SSP = ctypes.POINTER(SoundState)


def _bind():
    """Bind the recreate oracle + remaster candidate entry points once."""
    o = harness._lib
    for name, argc in (("g_TURNOFF", 0), ("g_EGOFF", 0), ("g_INITTUNE", 1), ("g_INITFX", 1)):
        fn = getattr(o, name)
        fn.argtypes = [U8P] + [ctypes.c_uint32] * argc
        fn.restype = None
    o.g_REFRESH.argtypes = [U8P, U8P, U8P, ctypes.c_uint32]
    o.g_REFRESH.restype = ctypes.c_uint32

    c = ctypes.CDLL(str(adapter.LIBREMASTER))
    for name in ("rm_sound_reset", "rm_turnoff", "rm_egoff"):
        getattr(c, name).argtypes = [SSP]
        getattr(c, name).restype = None
    for name in ("rm_inittune", "rm_initfx"):
        getattr(c, name).argtypes = [SSP, ctypes.c_uint32]
        getattr(c, name).restype = None
    c.rm_refresh.argtypes = [SSP, U8P, U8P, ctypes.c_int]
    c.rm_refresh.restype = ctypes.c_uint32
    return o, c


_ORACLE, _CAND = _bind()


# ---- one side each: a recreate flat image and a candidate SoundState, kept in lockstep ----

def _new_oracle():
    """Fresh recreate image (SND_STATE carries its power-on defaults) + a ctypes view over it."""
    img = harness.make_image()
    buf = (ctypes.c_uint8 * len(img)).from_buffer(img)
    return img, buf


def _new_cand():
    st = SoundState()
    _CAND.rm_sound_reset(ctypes.byref(st))
    return st


def _seed(img, st, addr, val):
    """Write one driver-state byte identically on both sides (oracle image + candidate header)."""
    img[addr] = val
    st.header[addr - SND_STATE] = val


def _seed_voice(img, st, v, off, val):
    """Write one voice-record byte identically on both sides."""
    img[SND_VOICE_CTRL + v * SND_VOICE_STRIDE + off] = val
    st.voice[v][off] = val


def _oracle_state(img):
    header = bytes(img[SND_STATE:SND_STATE + SND_STATE_BYTES])
    voices = [bytes(img[SND_VOICE_CTRL + v * SND_VOICE_STRIDE:
                        SND_VOICE_CTRL + (v + 1) * SND_VOICE_STRIDE]) for v in range(SND_VOICES)]
    return header, voices


def _cand_state(st):
    return bytes(st.header), [bytes(st.voice[v]) for v in range(SND_VOICES)]


def _state_mismatches(img, st):
    o_hdr, o_voices = _oracle_state(img)
    c_hdr, c_voices = _cand_state(st)
    out = []
    for off in range(SND_STATE_BYTES):
        if o_hdr[off] != c_hdr[off]:
            out.append((f"header[{off:#04x}]", c_hdr[off], o_hdr[off]))
    for v in range(SND_VOICES):
        for off in range(SND_VOICE_STRIDE):
            if o_voices[v][off] != c_voices[v][off]:
                out.append((f"voice[{v}][{off:#04x}]", c_voices[v][off], o_voices[v][off]))
    return out


def _refresh_both(buf, st):
    """One REFRESH frame each side; return (oracle_psg, cand_psg) as [(reg, val), ...]."""
    o_reg, o_val = (ctypes.c_uint8 * PSG_CAP)(), (ctypes.c_uint8 * PSG_CAP)()
    on = _ORACLE.g_REFRESH(buf, o_reg, o_val, PSG_CAP)
    c_reg, c_val = (ctypes.c_uint8 * PSG_CAP)(), (ctypes.c_uint8 * PSG_CAP)()
    cn = _CAND.rm_refresh(ctypes.byref(st), c_reg, c_val, PSG_CAP)
    # The shell sizes its VBL PSG buffer to SND_PSG_WRITES_MAX (sound.h); a frame that emitted more would
    # overrun it. Pin both sides against the header constant so a driver change that adds a write is caught.
    assert on <= _SND_H["SND_PSG_WRITES_MAX"] and cn <= _SND_H["SND_PSG_WRITES_MAX"], (on, cn)
    o_psg = [(o_reg[i], o_val[i]) for i in range(on)]
    c_psg = [(c_reg[i], c_val[i]) for i in range(cn)]
    return o_psg, c_psg


def _assert_ok(mismatches, label):
    assert not mismatches, f"{label} diverged from recreate: " + "; ".join(
        f"{n}: candidate {c:#x} != recreate {r:#x}" for n, c, r in mismatches[:8])


def _step_and_compare(img, buf, st, frames, tag):
    """Step `frames` REFRESH frames on both sides, asserting the PSG stream + whole state match each."""
    for f in range(frames):
        o_psg, c_psg = _refresh_both(buf, st)
        assert o_psg == c_psg, f"{tag} frame {f} PSG\n oracle={o_psg}\n cand  ={c_psg}"
        _assert_ok(_state_mismatches(img, st), f"{tag} frame {f} state")


# ---- cross-language source-of-truth pin: sound.h offsets ↔ the real image addresses ----
# SND_CONST is baked as image[SND_STATE:SND_CONST_END]; every *_OFF in sound.h must therefore equal
# (its documented Ghidra address − SND_STATE), and the Dosound offsets (base − SND_DOSOUND_BASE). This
# pins the C header (the SND_CONST index base) to the image the generator bakes from — if either the
# header or the generator drifts, the baked blob would be read at the wrong offset. The generator's own
# window constants (SND_STATE / SND_CONST_END / SND_DOSOUND_BASE) are pinned to the same addresses too.

_GHIDRA_ADDR = {                     # sound.h *_OFF constant -> documented Ghidra address (recreate/sound.c)
    "SND_PITCH_TABLE_OFF": 0x1b2be, "SND_ENV_TABLE_OFF": 0x1b440, "SND_PERIOD_TABLE_OFF": 0x1b446,
    "SND_TUNE_TAB_B_OFF": 0x1b5f3, "SND_TUNE_TAB_W_OFF": 0x1b5f4, "SND_MOD_TABLE_OFF": 0x1b77f,
    "SND_FX_TABLE_OFF": 0x1bc56,
}
SND_DOSOUND_BASE = 0x18b78
_DOSOUND_ADDR = {                    # sound.h SND_DOSOUND_* constant -> documented list address
    "SND_DOSOUND_COLLIDE": 0x18b78, "SND_DOSOUND_CRASH": 0x18b92, "SND_DOSOUND_IDLE": 0x18ba2,
    "SND_DOSOUND_BEEP": 0x18bba, "SND_DOSOUND_GO": 0x18bca,
}


def test_header_offsets_match_image_addresses():
    for name, addr in _GHIDRA_ADDR.items():
        assert _SND_H[name] == addr - SND_STATE, f"{name} {_SND_H[name]:#x} != {addr:#x} - SND_STATE"
    for name, addr in _DOSOUND_ADDR.items():
        assert _SND_H[name] == addr - SND_DOSOUND_BASE, f"{name} {_SND_H[name]:#x} != {addr:#x} - dosound base"
    # The baked window must cover fx record 9 (INITFX(9)'s bss-zero record) — the largest const index.
    fx9_end = _SND_H["SND_FX_TABLE_OFF"] + (FX_IDS[-1] + 1) * _SND_H["SND_FX_RECORD"]
    assert gen.SND_STATE == SND_STATE
    assert gen.SND_CONST_END - gen.SND_STATE >= fx9_end, "SND_CONST window too small for fx 9"
    assert gen.SND_DOSOUND_BASE == SND_DOSOUND_BASE


def test_dosound_lists_terminate_inside_the_baked_window():
    """Every baked Dosound list reaches its end marker (an opcode >= 0x82 with a zero operand — these
    lists all end `ff 00`) before the baked window ends, so no list is truncated by the bake. (The
    pair could in principle appear as data mid-list; the guard is against window truncation.)"""
    img = harness.BASE_IMAGE
    for name, addr in _DOSOUND_ADDR.items():
        blob = bytes(img[addr:gen.SND_DOSOUND_END])
        assert b"\xff\x00" in blob, f"{name} has no Dosound terminator before the baked window end"


def test_image_tables_live_where_the_offsets_claim():
    """The documented table addresses hold real (nonzero) program data, and fx record 9 is bss zeros
    past the image end — the assumption the generator bakes and INITFX(9) reads."""
    img = harness.BASE_IMAGE
    for name, addr in _GHIDRA_ADDR.items():
        assert any(img[addr:addr + 0x10]), f"{name} @ {addr:#x} is unexpectedly all-zero"
    fx9 = _GHIDRA_ADDR["SND_FX_TABLE_OFF"] + FX_IDS[-1] * _SND_H["SND_FX_RECORD"]
    assert not any(img[fx9:fx9 + _SND_H["SND_FX_RECORD"]]), "fx record 9 is not bss-zero as assumed"


# ---- INITTUNE / INITFX in isolation ----

def test_inittune_all():
    """Seed each tune id both sides; the seeded music header + three voice records must match."""
    for tune in TUNE_IDS:
        img, buf = _new_oracle()
        _ORACLE.g_INITTUNE(buf, tune)
        st = _new_cand()
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _assert_ok(_state_mismatches(img, st), f"inittune tune={tune}")


def test_initfx_all():
    """Seed each fx id both sides; the loaded effect-voice record must match (incl. fx 9's zeros)."""
    for fx in FX_IDS:
        img, buf = _new_oracle()
        _ORACLE.g_INITFX(buf, fx)
        st = _new_cand()
        _CAND.rm_initfx(ctypes.byref(st), fx)
        _assert_ok(_state_mismatches(img, st), f"initfx fx={fx}")


# ---- REFRESH: the VBL orchestrator, per frame ----

def test_refresh_music():
    """Every tune, INITTUNE-seeded, stepped far enough to walk the tempo prescaler, the note stream
    (loop-point + end-tune), and the per-frame DSP."""
    for tune in TUNE_IDS:
        img, buf = _new_oracle()
        _ORACLE.g_INITTUNE(buf, tune)
        st = _new_cand()
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _assert_ok(_state_mismatches(img, st), f"tune={tune} seed")
        _step_and_compare(img, buf, st, SCENARIO_FRAMES, f"tune={tune}")


def test_refresh_fx():
    """Every fx, INITFX-seeded and armed, stepped through the frequency sweep, noise gate, and the
    effect switching itself off when its duration counter elapses."""
    for fx in FX_IDS:
        img, buf = _new_oracle()
        st = _new_cand()
        _ORACLE.g_INITFX(buf, fx)
        _CAND.rm_initfx(ctypes.byref(st), fx)
        _seed(img, st, A_fxflag, 0xff)             # arm the effect (INITFX leaves it set already)
        _step_and_compare(img, buf, st, 60, f"fx={fx}")


def test_refresh_music_eg():
    """Music + envelope generator in the same frames, so the EG's channel-A override of the music
    DSP's period is exercised (they are otherwise tested apart)."""
    for tune in (0, 6):
        img, buf = _new_oracle()
        st = _new_cand()
        _ORACLE.g_INITTUNE(buf, tune)
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _seed(img, st, A_egflag, 0xff)              # arm the EG alongside music
        _step_and_compare(img, buf, st, 120, f"tune+eg={tune}")


def test_refresh_eg():
    """The engine-EG path alone: EGFLAG on, music/fx off, swept engfreq + random EG params. Covers the
    EG period synthesis and its channel-A override across a full phase sweep."""
    for s in range(60):
        rng = random.Random(31000 + s)
        img, buf = _new_oracle()
        st = _new_cand()
        _seed(img, st, A_egflag, 0xff)
        _seed(img, st, A_music_on, 0x00)
        _seed(img, st, A_fxflag, 0x00)
        _seed(img, st, A_eg_p1, rng.randrange(256))
        _seed(img, st, A_eg_vol, rng.randrange(256))
        _seed(img, st, A_eg_phase, rng.randrange(256))
        for b in range(PSG_STAGING_BYTES):             # random PSG staging: exercise the dump + mixer
            _seed(img, st, SND_STATE + b, rng.randrange(256))
        for v in range(SND_VOICES):
            _seed_voice(img, st, v, VC_ENV_FLG, rng.randrange(256))
        _step_and_compare(img, buf, st, 40, f"eg seed={s}")   # 40 frames sweeps EG_PHASE fully


def test_turnoff_midtune():
    """TURNOFF mid-tune: seed + step a tune, TURNOFF both sides, keep stepping. The stopped music must
    stay silent and identical (mzflag + music byte/word cleared)."""
    for tune in (1, 6):
        img, buf = _new_oracle()
        _ORACLE.g_INITTUNE(buf, tune)
        st = _new_cand()
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _step_and_compare(img, buf, st, 30, f"turnoff-pre tune={tune}")
        _ORACLE.g_TURNOFF(buf)
        _CAND.rm_turnoff(ctypes.byref(st))
        _assert_ok(_state_mismatches(img, st), f"turnoff tune={tune}")
        _step_and_compare(img, buf, st, 20, f"turnoff-post tune={tune}")


def test_egoff_midtune():
    """EGOFF mid-run: arm the EG over a tune, EGOFF both sides, keep stepping. EGOFF clears EGFLAG and
    the music byte, so the EG override stops and the music byte reads 0 thereafter."""
    for tune in (0, 8):
        img, buf = _new_oracle()
        st = _new_cand()
        _ORACLE.g_INITTUNE(buf, tune)
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _seed(img, st, A_egflag, 0xff)
        _step_and_compare(img, buf, st, 20, f"egoff-pre tune={tune}")
        _ORACLE.g_EGOFF(buf)
        _CAND.rm_egoff(ctypes.byref(st))
        _assert_ok(_state_mismatches(img, st), f"egoff tune={tune}")
        _step_and_compare(img, buf, st, 20, f"egoff-post tune={tune}")


def test_fx_over_music():
    """An effect running on top of music: both the music DSP (voices A/B) and the FX block (channel C)
    mutate the same frame, so their shared PSG staging + R6 interplay is exercised together."""
    for tune, fx in ((6, 0), (8, 5)):
        img, buf = _new_oracle()
        st = _new_cand()
        _ORACLE.g_INITTUNE(buf, tune)
        _ORACLE.g_INITFX(buf, fx)
        _CAND.rm_inittune(ctypes.byref(st), tune)
        _CAND.rm_initfx(ctypes.byref(st), fx)
        _seed(img, st, A_fxflag, 0xff)
        _step_and_compare(img, buf, st, 60, f"fx-over-music tune={tune} fx={fx}")
