"""Differential tests for Joust's sound layer (src/sound.c).

Covered here: play_sound @ 0x10a56, snd_poll_done @ 0x10a8a and snd_tone_sweep @ 0x1096e.

This is the first battery whose functions live almost entirely OFF the memory image, so read
`tools/recreate_kit/TRAP_MODEL.md` alongside it. Two model surfaces carry everything:

  * XBIOS `Dosound(list)` — the model never dereferences the command list; it records the POINTER
    in an ordered ledger that `harness.differential()` compares against the candidate's. That is
    the only thing pinning play_sound's table indexing, so the cases below stage a table of
    distinct pointers and assert on `info["regs"]["dosound"]` directly rather than trusting that
    two identical images mean two identical sounds.
  * XBIOS `Giaccess` — a 16-byte YM2149 register file INSIDE the image (`harness.psg_regs`), so
    snd_poll_done's and snd_tone_sweep's register traffic is ordinary diffed memory.
"""
import ctypes
import random

import pytest

import abi
import emu
import harness
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin tests at the end
from test_score import _pin           # ...and the shared scrape-and-compare it feeds

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_SND_TONE_SWEEP = 0x1096e
ENTRY_PLAY_SOUND = 0x10a56
ENTRY_SND_POLL_DONE = 0x10a8a

# ---- globals (mirror of include/sound.h, which mirrors ../../names.txt) ----
A_SND_SWEEP_PITCH = 0x10d48
A_SND_SWEEP_VOLUME = 0x10d4a
A_SND_PRIORITY = 0x10d4c
A_SOUND_TABLE = 0x11774

SOUND_TABLE_STRIDE = 4         # lsl.l #2: the table holds longword command-list pointers
SOUND_TABLE_SLOTS = 16         # 0x11774..platform_table @ 0x117b4, i.e. 0x40 bytes of pointers
SND_PRIORITY_IDLE = 0x10       # what snd_poll_done releases the priority to

UNWRITTEN_W = 0x5a5a           # parked in an output word so a candidate that skips it differs
PSG_NOISE_BYTE = 0xa5          # staged into a register to prove the routine does or does not touch it

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs in (("g_play_sound", 1), ("g_snd_poll_done", 0), ("g_snd_tone_sweep", 0)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = None


def _sign_ext16(value):
    """A staged word as the 68000's signed word operations read it. The assert is what keeps a
    wider fuzz honest: 0x18000 is not a word, and silently returning it would make a case's
    EXPECTATION disagree with the oracle while looking like a reconstruction bug."""
    assert 0 <= value <= 0xffff, f"{value:#x} is not a word"
    return value - 0x10000 if value & 0x8000 else value


# ---------------------------------------------------------------------------
# play_sound @ 0x10a56
# ---------------------------------------------------------------------------
#
# The word argument arrives at 4(a7), but the routine's FIRST instruction is
# `movem.l #$fffe,-(a7)` — 60 bytes of saved registers. Entering through abi.stack_call_pokes,
# which parks A7 at 0x400fc, would drop that save area into ordinary diffed memory, where the
# pure-C candidate has nothing to match it with. The stub below pushes the argument from the
# oracle's own A7 instead, so every stack byte stays inside the guard band the differential
# already excludes and the comparison elsewhere stays byte-for-byte.

def _word_arg_stub(routine, arg):
    """move.w #arg,-(a7) ; jsr routine ; addq.l #2,a7 ; rts — poked identically into both images."""
    return (b"\x3f\x3c" + (arg & 0xffff).to_bytes(2, "big")
            + b"\x4e\xb9" + routine.to_bytes(4, "big")
            + b"\x54\x8f"
            + b"\x4e\x75")


def _sound_table(first_list=0x60000, stride=0x10):
    """A sound_table of DISTINCT command-list pointers, so the ledger identifies which entry was
    played. Real lists are byte strings the model never reads; only the pointer is ever compared."""
    return b"".join((first_list + slot * stride).to_bytes(4, "big")
                    for slot in range(SOUND_TABLE_SLOTS))


def _play_pokes(index, priority, table):
    pokes = {abi.STUB: _word_arg_stub(ENTRY_PLAY_SOUND, index),
             A_SND_PRIORITY: (priority & 0xffff).to_bytes(2, "big")}
    if table is not None:
        pokes[A_SOUND_TABLE] = table
    return pokes


def _expected_list(pokes, index):
    """The longword play_sound must hand Dosound: sound_table indexed by the SIGN-EXTENDED low word
    of index * 4. Read out of the staged image, so a case reaching outside the table is covered
    too."""
    entry = (A_SOUND_TABLE + _sign_ext16(index * SOUND_TABLE_STRIDE & 0xffff)) & 0xffffffff
    image = harness.make_image(pokes)
    return int.from_bytes(image[entry:entry + 4], "big")


def _play_case(index, priority, table=None, poison=False):
    """Run play_sound(index) with snd_priority staged, and check BOTH halves of its contract: the
    image (snd_priority) through the diff, and the off-image Dosound call through the ledger."""
    pokes = _play_pokes(index, priority, table)
    plays = _sign_ext16(index) <= _sign_ext16(priority)
    diffs, info = differential(abi.STUB, {"_pokes": pokes},
                               lambda lib, buf: lib.g_play_sound(buf, index), poison=poison)
    assert not diffs, f"index={index:#x} priority={priority:#x}\n{report(diffs)}"
    expected = [_expected_list(pokes, index)] if plays else []
    assert info["regs"]["dosound"] == expected, (
        f"index={index:#x} priority={priority:#x}: Dosound ledger is "
        f"{[hex(x) for x in info['regs']['dosound']]}, expected {[hex(x) for x in expected]}")
    return info


# Every ordering of a small index against a small priority, plus the boundary itself: `bgt` drops
# the call only when the request is STRICTLY greater, so index == priority still plays.
@pytest.mark.parametrize("priority", (0, 1, 2, 3, 4, 0x10, 0x7f, 0x100))
@pytest.mark.parametrize("index", (0, 1, 2, 3, 4, 0x10))
def test_play_sound_priority_gate(index, priority):
    _play_case(index, priority, table=_sound_table())


# `cmp.w` + `bgt` compares the two WORDS, signed — the `clr.l d0` ahead of it buys nothing, since
# the high half is never compared. So an index of 0x8000 is -32768 to the gate and outranks
# everything, and a priority of 0x8000 admits nothing but itself and lower.
@pytest.mark.parametrize("priority", (0, 0x10, 0x7ffe, 0x7fff, 0x8000, 0x8001, 0xfff0, 0xffff))
@pytest.mark.parametrize("index", (0, 0x10, 0x7fff, 0x8000, 0xfff0, 0xffff))
def test_play_sound_priority_compare_is_a_signed_word(index, priority):
    _play_case(index, priority, table=_sound_table())


# The scaled index reaches the table through `move.l (0,a0,d0.w)` — the LOW WORD of d0, sign
# extended, so only the bottom 14 bits of the index pick an entry and bit 13 decides the direction.
# 0x2000 * 4 is 0x8000, which indexes 0x8000 bytes BELOW sound_table; 0x4000 * 4 is 0x10000, whose
# low word is 0, so it reads the SAME entry index 0 does. The priority is staged wide open so each
# of these actually reaches the table read.
_WRAPPING_INDICES = (0x1fff, 0x2000, 0x2001, 0x3fff, 0x4000, 0x4001, 0x7fff, 0x8000, 0xbfff,
                     0xc000, 0xfffe, 0xffff)


@pytest.mark.parametrize("index", _WRAPPING_INDICES)
def test_play_sound_table_index_is_a_sign_extended_word(index):
    _play_case(index, 0x7fff, table=_sound_table())


def test_play_sound_index_0x4000_reads_the_same_entry_as_index_0():
    """The wrap made explicit: two indices 0x4000 apart hand Dosound the same command list, and
    differ only in the priority they leave behind."""
    table = _sound_table()
    assert (_play_case(0, 0x7fff, table=table)["regs"]["dosound"]
            == _play_case(0x4000, 0x7fff, table=table)["regs"]["dosound"])


def test_play_sound_uses_the_games_own_table():
    """Without a staged table the entries are the shipped binary's own list pointers — the case the
    game actually runs, and the one a mis-scaled index would still have to match."""
    for index in range(SOUND_TABLE_SLOTS):
        _play_case(index, 0x7fff)


def test_play_sound_write_is_attributed():
    """poison=True re-runs both cores on an image where snd_priority holds the INVERSE of what the
    oracle left, catching a candidate that never wrote it. That only bites when the sound still
    plays on the poisoned image, i.e. when index <= ~index — which holds for every negative index
    and no positive one, so these are the cases worth poisoning."""
    for index in (0x8000, 0xc000, 0xfff0, 0xffff):
        _play_case(index, 0x7fff, table=_sound_table(), poison=True)


PLAY_FUZZ_CHUNKS = 2


def _play_fuzz_cases():
    rng = random.Random(0x10A56)                 # seeded ONCE — every chunk replays this stream
    for i in range(300):
        yield (i, rng.randint(0, 0xffff), rng.randint(0, 0xffff))


@pytest.mark.parametrize("chunk", range(PLAY_FUZZ_CHUNKS))
def test_play_sound_fuzz(chunk):
    table = _sound_table()
    for i, index, priority in _play_fuzz_cases():
        if i % PLAY_FUZZ_CHUNKS != chunk:
            continue
        _play_case(index, priority, table=table)


# ---------------------------------------------------------------------------
# snd_poll_done @ 0x10a8a
# ---------------------------------------------------------------------------

PSG_MIXER = 7                  # YM2149 register 7: the six tone + noise enables, ACTIVE LOW
PSG_MIXER_ALL_OFF = 0x3f       # all six set = every generator silenced = the effect has finished


def _poll_case(mixer, priority, poison=False, other_regs=()):
    """Run snd_poll_done with register 7 staged. The staged value is the whole input — nothing else
    steers it — so the sweep below over all 256 bytes is the complete input space."""
    regfile = {PSG_MIXER: mixer}
    regfile.update(other_regs)
    pokes = {A_SND_PRIORITY: (priority & 0xffff).to_bytes(2, "big"), **harness.psg_regs(regfile)}
    diffs, _ = differential(ENTRY_SND_POLL_DONE, {"_pokes": pokes},
                            lambda lib, buf: lib.g_snd_poll_done(buf), poison=poison)
    assert not diffs, f"mixer={mixer:#04x} priority={priority:#x}\n{report(diffs)}"


@pytest.mark.parametrize("mixer", range(0x100))
def test_snd_poll_done_over_every_mixer_byte(mixer):
    """`andi.b #$3f` then `cmpi.b #$3f`: the two bits ABOVE the six enables are masked off, so
    0x3f/0x7f/0xbf/0xff all release the priority and every other byte leaves it alone."""
    _poll_case(mixer, priority=3)


@pytest.mark.parametrize("priority", (0, 1, 3, 0x10, 0x7fff, 0x8000, 0xffff))
def test_snd_poll_done_release_overwrites_any_priority(priority):
    """The release is an unconditional `move.w #$10` — it does not compare against what is playing,
    so even a priority that already outranks idle is overwritten."""
    _poll_case(PSG_MIXER_ALL_OFF, priority, poison=True)
    _poll_case(PSG_MIXER_ALL_OFF - 1, priority, poison=True)


def test_snd_poll_done_reads_register_7_and_no_other():
    """A read leaves the register file alone, and only register 7 is consulted: the same mixer with
    every other register set to noise must behave identically."""
    noise = {reg: PSG_NOISE_BYTE for reg in range(harness.OS_PSG_NREGS) if reg != PSG_MIXER}
    for mixer in (0, PSG_MIXER_ALL_OFF, 0xff):
        _poll_case(mixer, priority=3, other_regs=noise)


# ---------------------------------------------------------------------------
# snd_tone_sweep @ 0x1096e
# ---------------------------------------------------------------------------
#
# 2064 passes of 8 Giaccess traps, and the only inputs are the staged register file and the two
# counters it immediately overwrites — so the differential's whole reach here is the final register
# file plus the two counters' residue. The loops' START values are outside that reach and are
# pinned statically further down; three smaller gaps have no pin at all and are named here rather
# than left to be discovered:
#   * the ORDER of a pass's eight accesses. The kit models Giaccess as a register FILE, not an
#     ordered write ledger (TRAP_MODEL.md, Phase 3), and the seven writes go to seven distinct
#     registers, so permuting them is invisible. The order below does match 0x10990..0x10a3a.
#   * where the channel-C mute sits. It writes a register nothing else touches, so hoisting it
#     into the loop would also be invisible.
#   * the bottom two bits of the `or.l #$3f` mask, which the `bclr` pair immediately clears again.
#     They are pinned only by PSG_MIXER_ALL_OFF being shared with snd_poll_done, where all six
#     bits are load-bearing.

PSG_TONE_A_FINE, PSG_TONE_A_COARSE = 0, 1
PSG_TONE_B_FINE, PSG_TONE_B_COARSE = 2, 3
PSG_VOLUME_A, PSG_VOLUME_B, PSG_VOLUME_C = 8, 9, 0xa
SWEEP_TONE_B_COARSE = 0x0c     # channel B's fixed coarse period

SWEEP_MIXER_KEPT = 0xc0        # the two bits above the enables: `or.l`/`bclr` never touch them
SWEEP_MIXER_TONES_ON = 0x3c    # all six enables set, then tone A and B cleared back on
SWEEP_PITCH_END = 0xfffe       # `subq.w #2` past 0: the value the `bge` finally rejects
SWEEP_VOLUME_END = 0xffff      # `subq.w #1` past 0, likewise


def _sweep_pokes(regfile):
    """Both counters are staged with a sentinel: they are pure outputs, so a candidate that failed
    to write one would leave the sentinel and differ."""
    return {A_SND_SWEEP_PITCH: UNWRITTEN_W.to_bytes(2, "big"),
            A_SND_SWEEP_VOLUME: UNWRITTEN_W.to_bytes(2, "big"),
            **harness.psg_regs(regfile)}


def _sweep_case(regfile, poison=False):
    """Diff the sweep, then hand back the ORACLE's final image — what the claims below are stated
    against. `differential` does not expose the final image, so this costs a second oracle run
    (~45 ms); the alternative is asserting only that the two sides agree, which would leave the
    original's actual register traffic nowhere written down."""
    pokes = _sweep_pokes(regfile)
    diffs, _ = differential(ENTRY_SND_TONE_SWEEP, {"_pokes": pokes},
                            lambda lib, buf: lib.g_snd_tone_sweep(buf), poison=poison)
    assert not diffs, f"regfile={regfile}\n{report(diffs)}"
    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_SND_TONE_SWEEP)
    return final


# Poison is deliberately NOT set here: attribution does not vary with the staged mixer byte, and
# test_snd_tone_sweep_writes_exactly_eight_registers already runs the pass over ALL twelve bytes
# the sweep writes. Ten more of them would triple this test's cost and prove nothing further.
@pytest.mark.parametrize("mixer", (0x00, 0x03, 0x3c, 0x3f, 0x40, 0x80, 0xc0, 0xff, 0x55, 0xaa))
def test_snd_tone_sweep_mixer_read_modify_write(mixer):
    """The mixer is the one register the sweep READS back, and it re-reads it every pass. `or.l #$3f`
    then `bclr #0` / `bclr #1` silences all six generators and re-enables tones A and B, leaving the
    two bits above them exactly as staged — so what the sweep leaves behind still carries them."""
    final = _sweep_case({PSG_MIXER: mixer})
    assert final[harness.OS_PSG_REGS + PSG_MIXER] == (mixer & SWEEP_MIXER_KEPT) | SWEEP_MIXER_TONES_ON


def test_snd_tone_sweep_writes_exactly_eight_registers():
    """Which registers the sweep touches, stated rather than assumed: with the whole file staged to
    noise, the eight it drives come out at their final values and the other eight keep the noise."""
    final = _sweep_case({reg: PSG_NOISE_BYTE for reg in range(harness.OS_PSG_NREGS)}, poison=True)
    regfile = final[harness.OS_PSG_REGS:harness.OS_PSG_REGS + harness.OS_PSG_NREGS]

    written = {PSG_TONE_A_FINE: 0, PSG_TONE_A_COARSE: 0, PSG_TONE_B_FINE: 0,
               PSG_TONE_B_COARSE: SWEEP_TONE_B_COARSE,
               PSG_MIXER: (PSG_NOISE_BYTE & SWEEP_MIXER_KEPT) | SWEEP_MIXER_TONES_ON,
               PSG_VOLUME_A: 0, PSG_VOLUME_B: 0, PSG_VOLUME_C: 0}
    for reg in range(harness.OS_PSG_NREGS):
        assert regfile[reg] == written.get(reg, PSG_NOISE_BYTE), f"YM2149 register {reg}"


def test_snd_tone_sweep_counters_end_below_zero():
    """Both loops are `subq.w` + `bge` — SIGNED, and testing the counter AFTER the step — so each
    runs one pass more than its start suggests and leaves the first value the branch rejected.
    That residue is what pins the step: a `subq.w #1` on the pitch would leave 0xffff, not 0xfffe."""
    final = _sweep_case({PSG_MIXER: 0})
    assert int.from_bytes(final[A_SND_SWEEP_PITCH:A_SND_SWEEP_PITCH + 2], "big") == SWEEP_PITCH_END
    assert int.from_bytes(final[A_SND_SWEEP_VOLUME:A_SND_SWEEP_VOLUME + 2], "big") == SWEEP_VOLUME_END


# The two loop START values, and WHICH mechanism covers how much of each. Every pass rewrites the
# same eight registers, so only the LAST pass survives into the final image — but "last pass" is not
# the same for every start, so the differential's reach is partial rather than nil:
#
#   * SWEEP_PITCH_START — its PARITY and SIGN are differentially visible. `subq.w #2` walks an even
#     start down to a 0xfffe residue and an odd one to 0xffff, and the last TONE_A/B_FINE the sweep
#     writes is 0 for the even start and 1 for the odd. Measured: 0x100 -> 0x101 fails 12 cases
#     above. What is beyond the differential is the MAGNITUDE among non-negative EVEN starts —
#     0x100 -> 0x200 walks to the same 0xfffe through the same final registers, so it leaves a
#     byte-identical image and only the encoding pin below catches it.
#   * SWEEP_VOLUME_START — genuinely unobservable. Every start ends its loop at 0 and then 0xffff
#     with the same final volume written, so 0x0f -> 0x20 is byte-identical; the pin is its ONLY
#     catcher.
#
# So the pin below is NOT redundant with the differential, and deleting it in a tidy-up would drop
# the sole check on the pitch magnitude and on the volume start entirely. It reads the shipped
# binary's own instruction encodings — the only other source of truth there is.
I_SET_VOLUME, I_SET_PITCH = 0x10980, 0x10988     # move.w #imm,<abs>.l
I_STEP_PITCH, I_STEP_VOLUME = 0x10a40, 0x10a4a   # subq.w #n,<abs>.l
MOVE_W_IMM_TO_ABS_L = 0x33fc
SUBQ_W_ABS_L = 0x5179                            # bit 8 = subtract; count in bits 11..9 (0 means 8)


def _opcode(addr):
    return int.from_bytes(harness.BASE_IMAGE[addr:addr + 2], "big")


def test_sweep_start_values_match_the_original_instructions():
    """`move.w #imm,<abs>.l` is opcode | imm.w | addr.l. Both the immediate and the address are
    checked, so a slip that pinned the wrong instruction fails rather than passing on a coincidence
    (the addresses are the RELOCATED ones the loaded image holds, not the listing's raw words)."""
    source = _defines("src/sound.c")
    for addr, counter, constant in ((I_SET_VOLUME, A_SND_SWEEP_VOLUME, "SWEEP_VOLUME_START"),
                                    (I_SET_PITCH, A_SND_SWEEP_PITCH, "SWEEP_PITCH_START")):
        assert _opcode(addr) == MOVE_W_IMM_TO_ABS_L, f"{addr:#x} is not `move.w #imm,<abs>.l`"
        assert int.from_bytes(harness.BASE_IMAGE[addr + 4:addr + 8], "big") == counter, \
            f"the `move.w` at {addr:#x} does not target {counter:#x}"
        assert source[constant] == _opcode(addr + 2), \
            f"{constant} is {source[constant]:#x}; the original loads {_opcode(addr + 2):#x}"


def test_sweep_steps_match_the_original_instructions():
    """The steps ARE visible to the differential (through the counters' residue); pinning them here
    as well costs two lines and keeps all four counter instructions documented in one place."""
    step = _defines("src/sound.c")["SWEEP_PITCH_STEP"]
    for addr, counter, count in ((I_STEP_PITCH, A_SND_SWEEP_PITCH, step),
                                 (I_STEP_VOLUME, A_SND_SWEEP_VOLUME, 1)):
        assert _opcode(addr) == SUBQ_W_ABS_L | (count << 9), f"{addr:#x} is not `subq.w #{count}`"
        assert int.from_bytes(harness.BASE_IMAGE[addr + 2:addr + 6], "big") == counter, \
            f"the `subq.w` at {addr:#x} does not target {counter:#x}"


# ---------------------------------------------------------------------------
# Mirrored-constant pins. A drifted address is INVISIBLE to the differential: the staged input
# lands in dead memory, both cores agree on the game's own static data, and the case goes green
# proving nothing. Same arrangement as test_object.py's, using test_constants' scraper.
# ---------------------------------------------------------------------------

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_SND_TONE_SWEEP, "snd_tone_sweep"),
                       (ENTRY_PLAY_SOUND, "play_sound"),
                       (ENTRY_SND_POLL_DONE, "snd_poll_done")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_constants_match_the_c():
    """Every constant this file restates equals the one src/sound.c compiles against."""
    _pin(_defines("include/sound.h"), "sound.h", {
        "A_snd_sweep_pitch": A_SND_SWEEP_PITCH, "A_snd_sweep_volume": A_SND_SWEEP_VOLUME,
        "A_snd_priority": A_SND_PRIORITY, "A_sound_table": A_SOUND_TABLE,
        "SND_PRIORITY_IDLE": SND_PRIORITY_IDLE,
    })
    _pin(_defines("src/sound.c"), "sound.c", {
        "SOUND_TABLE_STRIDE": SOUND_TABLE_STRIDE,
        "PSG_MIXER": PSG_MIXER, "PSG_MIXER_ALL_OFF": PSG_MIXER_ALL_OFF,
        "PSG_TONE_A_FINE": PSG_TONE_A_FINE, "PSG_TONE_A_COARSE": PSG_TONE_A_COARSE,
        "PSG_TONE_B_FINE": PSG_TONE_B_FINE, "PSG_TONE_B_COARSE": PSG_TONE_B_COARSE,
        "PSG_VOLUME_A": PSG_VOLUME_A, "PSG_VOLUME_B": PSG_VOLUME_B, "PSG_VOLUME_C": PSG_VOLUME_C,
        "SWEEP_TONE_B_COARSE": SWEEP_TONE_B_COARSE,
    })


def test_sound_table_spans_the_slots_the_tests_stage():
    """_sound_table() writes SOUND_TABLE_SLOTS longwords over the image — one past the end would
    silently rewrite platform_table, which is the next global names.txt lists."""
    a_platform_table = _defines("include/object.h")["A_platform_table"]
    assert A_SOUND_TABLE + SOUND_TABLE_SLOTS * SOUND_TABLE_STRIDE == a_platform_table
    assert harness.NAME_MAP.get(a_platform_table) == "platform_table"
