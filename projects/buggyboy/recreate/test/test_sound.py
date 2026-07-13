"""Differential tests for the sound driver's per-frame leaves.

Register contract is taken from REFRESH (@0x1b086): A3 = SND_STATE (0x1b05c), and the voice
updaters are called with A0 pointing at a voice-control record (0x1b64a, stride 0x18); D0's high
byte is a live-in index scratch. We seed the record, the two touched SND_STATE bytes, and a
well-formed note stream, then diff the whole image against the oracle.

The note stream is built from tokens so it always terminates at a note (or a note-like command)
inside the seeded buffer — never walking off into live driver bytes. Command 0x85 (loop) resets
the stream pointer, so it is tested with a controlled loop target; command 0x88 (end tune)
rewrites the return address to re-enter REFRESH and cannot be verified run-to-rts, so it is
excluded (see STATUS.md).
"""
import ctypes
import random

import harness
from harness import differential, report

U8P = ctypes.POINTER(ctypes.c_uint8)
for name, argc in [("g_EGOFF", 0), ("g_snd_voice_b", 1), ("g_snd_voice_a", 1)]:
    fn = getattr(harness._lib, name)
    fn.argtypes = [U8P] + [ctypes.c_uint32] * argc
    fn.restype = None
for name in ("g_snd_cmd_handler", "g_snd_stub"):
    fn = getattr(harness._lib, name)
    fn.argtypes = [U8P, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    fn.restype = ctypes.c_uint32

SND_STATE = 0x1b05c
REC = 0x1b64a                    # voice-0 control record
STREAM = 0x1b800                 # scratch note-stream buffer (offset 0x7a4 from SND_STATE)
VOICE_A = 0x1b2e8                # entry alias: A0 += 0x18, then the snd_voice_b body
VOICE_B = 0x1b2ec
CMD_H = 0x1b3be                  # snd_cmd_handler
STUB = 0x1b3ba                   # entry alias: A0 += 0x18, then the snd_cmd_handler body
MOD_TAB = 0x1b77f                # A1: modulation-table base
OUT = 0x1b063                    # A2: PSG volume-output cursor

A_egflag = SND_STATE + 0x20      # 0x1b07c
A_music_byte = SND_STATE + 0x07  # 0x1b063

# Record span written by the updater, plus the two SND_STATE bytes it can touch.
REC_SPAN = 0x30
VC_STREAM = 0x02                 # word: stream offset relative to SND_STATE
VC_TIMER = 0x0a                  # note-duration countdown

# Stream tokens: (opcode, extra_param_bytes). Excludes 0x85 (loop) and 0x88 (end tune).
SAFE_CMDS = {0x81: 0, 0x82: 2, 0x83: 0, 0x84: 0, 0x86: 2, 0x87: 0, 0x89: 1, 0x8a: 0, 0x8b: 1, 0x8c: 0}


def test_egoff():
    pokes = {A_egflag: b"\xff", A_music_byte: b"\xaa"}
    diffs, _ = differential(0x1b252, {"_pokes": pokes}, lambda lib, buf: lib.g_EGOFF(buf))
    assert not diffs, report(diffs[:12])


def _voice_case(entry, glue_name, timer, flags, stream_bytes, seed=0):
    """Seed the body record at REC + the stream, then diff one voice-step call.

    Both entries drive the body on REC: snd_voice_b takes A0 = REC, snd_voice_a takes A0 = REC -
    0x18 (it adds one stride back). Seeding is therefore always at REC for both.
    """
    rng = random.Random(seed)
    a0 = REC if entry == VOICE_B else REC - 0x18
    rec = bytearray(rng.randrange(256) for _ in range(REC_SPAN))
    rec[0x00] = flags
    rec[VC_TIMER] = timer
    rec[VC_STREAM:VC_STREAM + 2] = ((STREAM - SND_STATE) & 0xffff).to_bytes(2, "big")
    pokes = {
        REC: bytes(rec),
        STREAM: bytes(stream_bytes),
        SND_STATE + 0x27: bytes([rng.randrange(256), rng.randrange(256)]),  # 0x27, 0x28
    }
    glue = getattr(harness._lib, glue_name)
    diffs, _ = differential(entry, {"a0": a0, "a3": SND_STATE, "_pokes": pokes},
                            lambda lib, buf: glue(buf, a0))
    assert not diffs, f"{glue_name} timer={timer} flags={flags:#x}\n{report(diffs[:12])}"


def _rand_stream(rng, n_tokens):
    """A well-formed token sequence ending in a note (< 0x80)."""
    out = []
    for _ in range(n_tokens):
        kind = rng.random()
        if kind < 0.4:                                  # pitch / param set
            out.append(rng.randrange(0xb0, 0x100))
        else:                                           # a safe command + its params
            op = rng.choice(list(SAFE_CMDS))
            out.append(op)
            out += [rng.randrange(256) for _ in range(SAFE_CMDS[op])]
    out.append(rng.randrange(0x80))                     # terminating note
    return out


def test_voice_glide():
    # Timer still running (>1 after decrement): only glide steps the note. Cover both glide bits.
    for seed in range(60):
        rng = random.Random(1000 + seed)
        flags = rng.randrange(256)
        entry, glue = (VOICE_B, "g_snd_voice_b") if seed % 2 else (VOICE_A, "g_snd_voice_a")
        _voice_case(entry, glue, timer=rng.randrange(2, 256), flags=flags,
                    stream_bytes=[], seed=seed)


def test_voice_stream():
    # Timer expires (=1): read the stream. Fuzz well-formed token streams through both entries.
    for seed in range(200):
        rng = random.Random(seed)
        stream = _rand_stream(rng, rng.randrange(1, 8))
        entry, glue = (VOICE_B, "g_snd_voice_b") if seed % 2 else (VOICE_A, "g_snd_voice_a")
        _voice_case(entry, glue, timer=1, flags=rng.randrange(256), stream_bytes=stream, seed=seed)


def test_voice_cmd80():
    # Command 0x80 finalises like a note without the note setup.
    for seed in range(20):
        rng = random.Random(500 + seed)
        stream = _rand_stream(rng, rng.randrange(0, 4))[:-1] + [0x80]
        _voice_case(VOICE_B, "g_snd_voice_b", timer=1, flags=rng.randrange(256),
                    stream_bytes=stream, seed=500 + seed)


def test_voice_loop_cmd():
    # Command 0x85 jumps to loop_table[idx], where loop_table = SND_STATE + word[SND_STATE +
    # loop_off] and idx = rec[0x01] (byte, +2 each hit); a zero entry restarts the loop at idx 0.
    # Lay a small table whose entries point at terminating notes, and cover both the direct index
    # and the wrap-to-0 branch.
    TABLE = STREAM - SND_STATE + 0x40    # loop-point table (words), relative to SND_STATE
    NOTE0 = STREAM - SND_STATE + 0x60    # loop target for entry 0
    for seed, start_idx in enumerate([0, 4]):   # idx 0 direct; idx 4 -> entry 0 -> wrap to 0
        rng = random.Random(700 + seed)
        rec = bytearray(rng.randrange(256) for _ in range(REC_SPAN))
        rec[0x00] = rng.randrange(256)
        rec[0x01] = start_idx
        rec[VC_TIMER] = 1
        rec[VC_STREAM:VC_STREAM + 2] = ((STREAM - SND_STATE) & 0xffff).to_bytes(2, "big")
        rec[0x04:0x06] = (TABLE & 0xffff).to_bytes(2, "big")
        table = bytearray(8)                     # 4 word entries
        table[0:2] = (NOTE0 & 0xffff).to_bytes(2, "big")   # entry 0 -> a note
        table[4:6] = (0).to_bytes(2, "big")                # entry 4 (idx 4) == 0 -> restart
        pokes = {
            REC: bytes(rec),
            STREAM: bytes([0x85]),
            SND_STATE + TABLE: bytes(table),
            SND_STATE + NOTE0: bytes([rng.randrange(0x80)]),
            SND_STATE + 0x27: bytes([rng.randrange(256), rng.randrange(256)]),
        }
        diffs, _ = differential(VOICE_B, {"a0": REC, "a3": SND_STATE, "_pokes": pokes},
                                lambda lib, buf: lib.g_snd_voice_b(buf, REC))
        assert not diffs, f"loop start_idx={start_idx}\n{report(diffs[:12])}"


def test_cmd_handler():
    # Per-frame voice DSP. Fuzz the record (covers the envelope / vibrato / portamento / control-bit
    # branches), diff the whole image, and check the returned tone period matches the oracle's D1.
    for seed in range(400):
        rng = random.Random(9000 + seed)
        rec = bytearray(rng.randrange(256) for _ in range(REC_SPAN))
        entry, glue = (CMD_H, "g_snd_cmd_handler") if seed % 2 else (STUB, "g_snd_stub")
        a0 = REC if entry == CMD_H else REC - 0x18
        pokes = {REC: bytes(rec)}
        g = getattr(harness._lib, glue)
        diffs, info = differential(entry, {"a0": a0, "a1": MOD_TAB, "a2": OUT, "a3": SND_STATE,
                                           "_pokes": pokes},
                                   lambda lib, buf: g(buf, a0, MOD_TAB, OUT))
        assert not diffs, f"{glue} seed={seed}\n{report(diffs[:12])}"
        assert info["ret"] & 0xffff == info["regs"]["d1"] & 0xffff, \
            f"{glue} seed={seed}: period ret={info['ret']:#x} oracle D1={info['regs']['d1']:#x}"


def test_cmd_handler_portamento():
    # The pitch-glide branch (FLAGS bit3 set) is rarely hit by the random fuzz above, so force it:
    # both the per-note delay (PORTA_LEN != 0 -> just decrement) and the glide step (PORTA_LEN == 0
    # -> accumulate a signed step into GLIDE_ACC and slide the period).
    VC_PORTA_STEP, VC_PORTA_LEN, VC_GLIDE_ACC = 0x06, 0x07, 0x08
    n = 0
    for porta_len in (0, 1, 3):
        for step in (0x01, 0x7f, 0x80, 0xff):        # signed porta step (ext.w)
            for acc in (0x0000, 0x00ff, 0x7fff, 0xfff0):
                rng = random.Random(4242 + n)
                n += 1
                rec = bytearray(rng.randrange(256) for _ in range(REC_SPAN))
                rec[0x00] = (rec[0x00] | 0x08) & 0xef   # FLAGS: bit3 (porta) on, bit4 (vibrato) off
                rec[VC_PORTA_STEP] = step
                rec[VC_PORTA_LEN] = porta_len
                rec[VC_GLIDE_ACC:VC_GLIDE_ACC + 2] = acc.to_bytes(2, "big")
                pokes = {REC: bytes(rec)}
                diffs, info = differential(CMD_H, {"a0": REC, "a1": MOD_TAB, "a2": OUT,
                                                   "a3": SND_STATE, "_pokes": pokes},
                                           lambda lib, buf: lib.g_snd_cmd_handler(buf, REC, MOD_TAB, OUT))
                assert not diffs, f"porta len={porta_len} step={step:#x} acc={acc:#x}\n{report(diffs[:12])}"
                assert info["ret"] & 0xffff == info["regs"]["d1"] & 0xffff, \
                    f"porta len={porta_len} step={step:#x} acc={acc:#x}: ret={info['ret']:#x} D1={info['regs']['d1']:#x}"