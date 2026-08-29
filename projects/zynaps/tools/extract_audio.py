#!/usr/bin/env python3
"""Dump Zynaps' (Atari ST, Hewson 1988) music and sound effects.

Usage:
  python3 projects/zynaps/tools/extract_audio.py [OUT_DIR]

OUT_DIR defaults to `projects/zynaps/out/audio` (gitignored). Reads only the game's own binary
under `projects/zynaps/bin/` (ZYNAPS17.PRG, through the kit's PRG loader) and writes, for each of
the 45 sound numbers the driver's index table holds:

  snd_NN.ym       one YM2149 register file per 50 Hz frame, uncompressed interleaved YM6 — the same
                  container `projects/wonderboy/tools/extract_audio.py` writes
  snd_NN.wav      the same frames rendered to 44100 Hz 16-bit mono
  manifest.tsv    per number: kind, voices used, frames, seconds, how the capture ended, the loop
                  it proved, how many frames are audible, and where the GAME starts that number

`manifest.tsv` is written LAST and only after every check below has passed, so its presence is what
marks the directory complete: a run that fails leaves the .ym/.wav files it got to and no manifest.

THIS IS AN ORACLE-DRIVEN CAPTURE, NOT A STATIC PARSE. `../recreate/src/sound.c` reconstructs the
whole replayer and `../recreate/test/test_sound.py` verifies it against the original — but rather
than re-run the reconstruction, this tool runs the ORIGINAL 68000 code under the kit's Musashi
oracle (`tools/recreate_kit`) and records what it writes to the chip:

  sound_reset_psg  once  -> silence: voices stopped, volumes zeroed, mixer muted, 14 registers out
  sound_start      once, with d1 = the sound number and d0 = SOUND_START_FALLBACK_CHANNEL
  sound_tick       once per emulated 50 Hz frame -> one frame of PSG traffic

Each tick's `(reg, value)` writes are folded into a running shadow of the chip's 16 registers, and
the shadow is snapshotted after every tick. That snapshot IS a YM frame. `sound_tick` flushes LAST
frame's shadow before computing this frame's, so the snapshot after tick N is what the chip really
held while frame N was on the raster.

WHY THE AUDIO-CAPTURE MODE, when this driver never reads the chip back. `emu.audio_capturing()`
exists for the two things a replayer needs that a differential must refuse (TRAP_MODEL.md): a
`$ff8800` read-back, and the 50 Hz colour-ST tempo bits. Zynaps needs NEITHER — it keeps its own
14-byte register shadow in the text segment and pushes it blind, and its tick rate is the VBL
rather than a byte it reads. The mode is used anyway because it is the sanctioned scope for a
capture that spans runs, and `_vetted_psg_writes` asserts the thing that makes it a non-event here:
not one read is served across the whole sweep, so nothing in these dumps is the shim's invention.

EVERY NUMBER IS CAPTURED FROM A FRESH IMAGE (`harness.make_image()`), because the driver's state —
the register shadow, the three voice records, the noise block and the round-robin toggle at
`sound_voice_toggle` — all live in the TEXT segment and nothing but a reload restores them.
`check_capture_is_reproducible` re-captures after the sweep to prove nothing leaked.

WHERE EACH CAPTURE STOPS. Four rules, and the manifest says which one ended each number:

  self-ended     every voice's `VOICE_ENABLE` byte is 0 — command 0xe1 ran on each of them.
  exact loop     the driver's whole mutable state repeated, which proves the output repeats forever
                 from that frame. The capture stops at the repeat, so the file is the lead-in plus
                 one full period.
  musical loop   the state repeated in everything but the NOISE BLOCK'S COUNTER PAIR
                 (`sound_noise_block` +0/+1). That pair is this driver's answer to Wonder Boy's
                 song-speed accumulator: `sound_noise_modulate` steps it on every single tick,
                 whether or not any voice wants noise. Against the record the binary ships — cursor
                 0, so both limit bytes read 0 from the zeroed vector page — the first byte fires
                 only when it wraps (256 ticks) and the second only when IT wraps (65,536 ticks),
                 which is well past any cap worth running. It is rewound only by `note_on`
                 consuming a pending 0xe4, which is exactly why the tunes that use 0xe4 DO reach an
                 exact loop and the rest cannot. The rule is a FALLBACK, never a competitor: the
                 capture runs the exact detector all the way to the cap first and only then looks
                 at the musical one, so an exact loop is never traded away for a weaker musical
                 one. A musical capture is truncated to lead-in + the loop played through TWICE.
  capped         none of the above inside SOUND_FRAME_CAP frames.

WHAT THE RENDERER MODELS. `write_wav` renders through BuggyBoy's
`projects/buggyboy/recreate/sound/ym2149.py`, imported rather than reimplemented: three square
tones from the 12-bit periods, the chip's 17-bit noise LFSR, the mixer's active-low gates, the
4-bit ~3 dB/step volume DAC and the eight envelope shapes. Two Zynaps facts it must be handed
correctly:

  * `sound_tick` writes registers 10..0 and STOPS — registers 11..13 are the envelope period and
    shape, and pushing 13 would retrigger the envelope every frame (names.txt, 0x16b94). So the
    only reg-13 write in a whole capture is `sound_reset_psg`'s, before frame 1, and `retriggers`
    is all-false: the envelope generator reads as long completed, which is what the chip does.
  * the driver adds a biased delta to its volume byte WITHOUT masking, so a volume register
    genuinely reaches values above 0x0f and bit 4 — "use the envelope" — really does get set. On
    hardware those channel-frames are silent, because the envelope finished before frame 1; the
    renderer models exactly that, and `audible_frames` counts them as silent for the same reason.

It renders each file peak-NORMALISED (that is `ym2149.render`'s contract), so a .wav's loudness is
not comparable with another's. Every "is this silent?" claim here is therefore made on the REGISTER
STREAM instead, where it is a fact about the chip rather than about a gain stage.

Addresses come from two sources of truth and are spelt as a literal in neither: entry points are
looked up by name in `../names.txt` (`entry_of`), and every table address and record offset is
scraped out of `../recreate/include/sound.h` — the same header the differential batteries mirror,
so a rename or a move fails here loudly instead of dumping from a stale address. The YM2149's own
register numbers and bit fields are the chip's, not the game's, and are named here.
"""

import os
import struct
import sys
import wave
from collections import namedtuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
RECREATE_DIR = os.path.join(PROJECT_DIR, "recreate")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "audio")
# The YM2149 software synth is BuggyBoy's, and it is imported rather than copied: it is the one
# renderer this workspace has, docs/sound.md documents it as such, and a second copy here would be
# a second set of DAC and envelope approximations to keep in step.
BUGGYBOY_SYNTH_DIR = os.path.join(REPO_ROOT, "projects", "buggyboy", "recreate", "sound")

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
from recreate_kit import project                    # noqa: E402  (needs the path above)

project.load(RECREATE_DIR)                          # binds the kit to this game's project.toml
sys.path.insert(0, os.path.join(RECREATE_DIR, "test"))   # harness.py, abi.py, test_constants.py
sys.path.insert(0, BUGGYBOY_SYNTH_DIR)
try:
    from recreate_kit import os_map                 # noqa: E402  (must follow project.load)
    import emu                                      # noqa: E402
    import loader                                   # noqa: E402  (bound by project.load)
    import prg_dis                                  # noqa: E402  (tools/prg_dis.py: header parser)
    import harness                                  # noqa: E402  (recreate/test/harness.py shim)
    import abi                                      # noqa: E402  (recreate/test/abi.py stubs)
    import test_constants                           # noqa: E402  (its header scraper; see below)
    import ym2149                                   # noqa: E402  (BuggyBoy's YM2149 synth)
    import numpy                                    # noqa: E402  (ym2149's own dependency)
except (OSError, RuntimeError) as error:
    # OSError is the ctypes.CDLL behind the oracle or the candidate; RuntimeError is the kit's own
    # stale-.so check, whose message already names the symbol and the rebuild that restores it.
    raise SystemExit("this tool drives the kit's Musashi oracle and the project's own library, and "
                     "one of them is not built or is out of date (%s):\n"
                     "  make -C projects/zynaps/recreate" % error)
except ImportError as error:
    raise SystemExit("a module this tool reuses is missing (%s). It needs numpy — run it with the "
                     "atari_reverse conda env's python, or projects/zynaps/recreate/.venv/bin/python"
                     % error)

# ---- the driver's constants, from the header the differential batteries mirror ------------------
# `test_constants._defines` is this project's ONE reader of a C header (test/test_constants.py),
# and it is reused deliberately: a second `#define` regex here would be exactly the drift that
# module exists to diagnose. It is private only in the sense that nothing else needed it yet.

SOUND_H = test_constants._defines("include/sound.h")

A_TUNE_INDEX = SOUND_H["A_tune_index"]                 # the little-endian offset words
A_TUNE_DATA = SOUND_H["A_tune_data"]                   # ...relative to this
A_MOD_TABLE_DATA = SOUND_H["A_mod_table_data"]         # ...and what the index table butts up against
A_PSG_REG_SHADOW = SOUND_H["A_psg_reg_shadow"]         # the driver's 14-byte copy of the chip
A_SOUND_NOISE_BLOCK = SOUND_H["A_sound_noise_block"]   # the noise sweep's modulation record
A_SOUND_VOICE1 = SOUND_H["A_sound_voice1"]
A_NOTE_PERIOD_TBL = SOUND_H["A_note_period_tbl"]       # where the mutable block ends (read-only)
VOICE_STRIDE = SOUND_H["VOICE_STRIDE"]
VOICE_ENABLE = SOUND_H["VOICE_ENABLE"]                 # 0 = this voice has stopped
VOICE_MOD_COUNTERS = SOUND_H["VOICE_MOD_COUNTERS"]     # the modulation machine's counter pair
PSG_SHADOW_REGS = SOUND_H["PSG_SHADOW_REGS"]           # 14: what sound_reset_psg pushes
PSG_TICK_FLUSH_REGS = SOUND_H["PSG_TICK_FLUSH_REGS"]   # 11: what sound_tick pushes, 10..0
PSG_REG_MIXER = SOUND_H["PSG_REG_MIXER"]
PSG_REG_VOLUME_A = SOUND_H["PSG_REG_VOLUME_A"]
SOUND_STREAM_CHANNEL_TAG = SOUND_H["SOUND_STREAM_CHANNEL_TAG"]   # the `fa <chan>` stream header

VOICES = tuple(A_SOUND_VOICE1 + voice * VOICE_STRIDE for voice in range(3))
VOICE_NUMBERS = (1, 2, 3)                              # what names.txt and the manifest call them
# The exact access stream one tick makes: registers 10..0, descending. The ORDER is the only thing
# separating this from the same flush the other way round — the register file both leave behind is
# identical — so the ledger is the only surface that can see it (src/sound.c, `flush_shadow`).
TICK_FLUSH_ORDER = tuple(range(PSG_TICK_FLUSH_REGS - 1, -1, -1))

# The whole of the driver's mutable state is the one contiguous run from the register shadow to the
# note-period table: shadow, toggle, noise block, then the three voice records. Everything above it
# (the note periods, the two offset indices and the tune data) is read-only, and nothing outside
# the text segment is touched at all — `src/sound.c` names no other global.
STATE_LO, STATE_HI = A_PSG_REG_SHADOW, A_NOTE_PERIOD_TBL
# ...and the two bytes of it that free-run at their own period; see the module docstring.
NOISE_COUNTERS_AT = A_SOUND_NOISE_BLOCK + VOICE_MOD_COUNTERS - STATE_LO
NOISE_COUNTER_BYTES = 2                                # `.b x2 for the volume machine` (sound.h)

TUNE_INDEX_ENTRY_BYTES = 2
# names.txt reads the index as 45 entries; `check_tune_count` proves it off the header's own
# addresses rather than trusting the number, and cross-checks the sign-extension boundary
# test_sound.py pins as TUNE_FIRST_NEGATIVE_OFFSET.
SOUND_COUNT = (A_MOD_TABLE_DATA - A_TUNE_INDEX) // TUNE_INDEX_ENTRY_BYTES
TUNE_OFFSET_SIGN_BIT = 0x8000

# 300 s at 50 Hz. The longest capture in the set is the boot tune, whose exact loop closes at 13121
# frames; nothing else needs more than ~10600, so this is that plus headroom rather than a guess.
SOUND_FRAME_CAP = 15000

FRAME_RATE = ym2149.FPS                                # 50: the VBL the driver ticks on
SAMPLE_RATE = ym2149.RATE                              # 44100
YM_CLOCK = ym2149.CLOCK                                # 2 MHz — the ST's YM2149 master clock

# ---- the YM2149 as the dumps see it -------------------------------------------------------------

YM_REGISTERS = 16                                      # a YM6 frame carries all of them
TONE_FINE_REGS = (0, 2, 4)
TONE_COARSE_REGS = (1, 3, 5)
VOLUME_REGS = (PSG_REG_VOLUME_A, PSG_REG_VOLUME_A + 1, PSG_REG_VOLUME_A + 2)
ENVELOPE_SHAPE_REG = 13
TONE_PERIOD_COARSE_MASK = 0x0f
NOISE_PERIOD_MASK = 0x1f
MIXER_MASK = 0x3f                                      # 3 tone gates + 3 noise gates
VOLUME_REG_MASK = 0x1f                                 # 4-bit level + the envelope-mode bit
VOLUME_LEVEL_MASK = 0x0f
VOLUME_ENVELOPE_BIT = 0x10
NOISE_MIXER_SHIFT = 3                                  # mixer bits 0..2 tone, 3..5 noise
CHANNELS = 3

# The oracle's shim models the chip's register file, and a .ym frame is a snapshot of that file's
# width. Two different numbers here would mean the shim and this tool disagree about what a YM2149
# is, and every frame written would be silently short or padded.
if emu.PSG_NREGS != YM_REGISTERS:
    raise SystemExit("the oracle models %d YM2149 registers, not the %d a YM6 frame carries. "
                     "emu.PSG_NREGS is read from liboracle.so itself, so this is a real "
                     "disagreement about what a YM2149 is, not a stale build."
                     % (emu.PSG_NREGS, YM_REGISTERS))

# Which bits of each register the CHIP decodes. This matters for the .ym and not for the render:
# YM5/YM6 reuse the dead bits of registers 1, 3, 6, 7, 14 and 15 as SPECIAL-EFFECT CODES (SID voice,
# sinus-SID, digidrum channel and timer), so a player handed a raw shadow byte with rubbish above
# the field starts an effect on whatever voice those bits happen to name. Zynaps leaves plenty:
# `sound_voice_modulate` adds an unmasked delta to the volume byte and `note_on` ORs 0xc0 into the
# mixer for the two I/O-port DIRECTION bits, neither of which the YM5/YM6 field is wide enough for.
YM_REGISTER_MASKS = bytes((
    0xff, TONE_PERIOD_COARSE_MASK,                     # 0/1: channel A tone period
    0xff, TONE_PERIOD_COARSE_MASK,                     # 2/3: channel B
    0xff, TONE_PERIOD_COARSE_MASK,                     # 4/5: channel C
    NOISE_PERIOD_MASK,                                 # 6:   noise period
    MIXER_MASK,                                        # 7:   mixer
    VOLUME_REG_MASK, VOLUME_REG_MASK, VOLUME_REG_MASK,  # 8-10: channel volumes
    0xff, 0xff, 0xff, 0xff, 0xff,                      # 11-15: never written after the reset
))

# ---- YM6 container ------------------------------------------------------------------------------
# "YM6!" + "LeOnArD!", a fixed header, three NUL-terminated strings, the frames INTERLEAVED
# (register-major) and an "End!" marker. Written uncompressed; the usual LHA wrapper is a transport,
# not part of the format. Same writer shape as projects/wonderboy/tools/extract_audio.py — it
# cannot be imported from there, because that module binds the kit to Wonder Boy at import time and
# `project.load` refuses to rebind inside one process. Lifting both copies into `tools/` would be
# the right home for it, and is deliberately left out of this change.
YM6_MAGIC = b"YM6!"
YM6_CHECK = b"LeOnArD!"
YM6_ATTRIBUTE_INTERLEAVED = 1 << 0
YM6_DIGIDRUMS = 0
YM6_EXTRA_BYTES = 0
YM6_END = b"End!"
YM6_AUTHOR = b"Hewson / Dominic Robinson, Steve Turner (custom in-house driver)"
# The three strings are 8-BIT text: a YM player renders them in the machine's own character set
# (Atari ST, DOS CP437, ...), where no byte means "em dash". They are therefore ASCII, and the
# encode says so rather than trusting whoever edits the format strings below.
YM6_TEXT_ENCODING = "ascii"
# Register 13 is WRITE-TRIGGERED on the real chip, so the YM formats spell "not written this frame"
# as 0xff rather than as a repeat of the last value. No Zynaps tick ever writes it.
ENVELOPE_SHAPE_UNTOUCHED = 0xff

TITLE_PREFIX = "Zynaps (ST) - "
COMMENT_PREFIX = "captured from ZYNAPS17.PRG by tools/extract_audio.py; "

SAMPLE_BYTES = 2                                       # 16-bit PCM
INT16_PEAK = 32767
# One 16-bit quantisation step: a render peaking below this writes an all-zero .wav, so it is the
# honest threshold for "the render is silent" and not a tolerance pulled out of the air.
RENDER_SILENCE_PEAK = 1.0 / INT16_PEAK

# ---- how a capture ended ------------------------------------------------------------------------

END_SELF = "self-ended"                                # every voice ran command 0xe1
END_LOOP = "exact-loop"                                # the driver's whole state repeated
END_MUSICAL_LOOP = "musical-loop"                      # ...all of it bar the noise counter pair
END_CAPPED = "capped"                                  # none of those inside the cap
END_REASONS = (END_SELF, END_LOOP, END_MUSICAL_LOOP, END_CAPPED)
LOOPED_ENDS = (END_LOOP, END_MUSICAL_LOOP)             # the two that give the .ym a loop frame

# ---- what a number IS ---------------------------------------------------------------------------

KIND_MUSIC = "music"                                   # it did not end: a loop, or the cap
KIND_SFX = "sfx"                                       # it stopped itself (command 0xe1)
KIND_SILENT = "silent"                                 # not one audible frame — see classify()

Capture = namedtuple("Capture", "number frames end loop_start loop_period voices psg_regs")
# One number's whole result: what came off the chip, what it was called, and how loud it rendered.
Sound = namedtuple("Sound", "capture kind audible level")


# ---- addressing by name -------------------------------------------------------------------------


def entry_of(name):
    """The address `../names.txt` gives `name`, or a loud failure.

    `harness.NAME_MAP` is the kit's own parse of that file (it is what `harness.label` reports
    diffs through), inverted here. A name that is missing or ambiguous is a bug in the map, not
    something to fall back from: capturing at a stale address would produce a plausible dump of the
    wrong routine.
    """
    matches = sorted(addr for addr, label in harness.NAME_MAP.items() if label == name)
    if len(matches) != 1:
        raise SystemExit("../names.txt gives the name %r %d addresses (%s); this tool needs exactly "
                         "one, because it enters the 68000 there"
                         % (name, len(matches), ", ".join("%#x" % a for a in matches)))
    return matches[0]


ENTRY_SOUND_RESET_PSG = entry_of("sound_reset_psg")
ENTRY_SOUND_START = entry_of("sound_start")
ENTRY_SOUND_TICK = entry_of("sound_tick")

# `sound_start` takes the channel in D0 and the sound number in D1 (names.txt, 0x16ac8), and D0
# survives only for a stream carrying no `fa <chan>` header of its own. 0 is not a voice: 1 and 2
# name voices 1 and 2 and EVERYTHING ELSE falls through to voice 3 (src/sound.c,
# `voice_for_channel`), so every headerless stream here is dumped on voice 3. In the game those
# streams are spawned mid-piece by another one — `fd 0c` puts number 12 on voice 2 — so their
# manifest rows are that stream played on the driver's fall-through voice, not on the voice the
# parent would have given it. Which voice a monophonic stream sounds on changes nothing about the
# notes; it is stated because it is a difference from the game and not an accident.
SOUND_START_FALLBACK_CHANNEL = 0


# ---- who starts what, from the game's own code --------------------------------------------------
# The manifest's "used by" column is a BYTE SCAN of the text for calls to `sound_start`, not a read
# of names.txt's prose: the prose says "sound 0x16" in one comment and "0x16b94" in another, and
# nothing but the instruction stream separates those. Every call site the scan finds is a `bsr`
# with a `moveq #n,d1` immediately in front of it, which is the whole calling convention.

BSR_OPCODE = 0x61                                      # 0110 0001 dddddddd — bsr.b
BSR_WORD_FORM = 0x00                                   # ...and 0x00 in that byte means bsr.w
BSR_BYTES = 2                                          # the opcode word; a bsr.w adds a word
BSR_WORD_BYTES = 4
MOVEQ_D1_OPCODE = 0x72                                 # 0111 001 0 dddddddd — moveq #d,d1
MOVEQ_BYTES = 2
JSR_ABSOLUTE_LONG = b"\x4e\xb9"                        # the other way to call it, if it is used
JSR_ABSOLUTE_LONG_BYTES = 6                            # opcode word + the absolute longword
# The sound driver's own code: from its first routine to the register shadow, which is the first
# byte of its data. The one `sound_start` call with no `moveq` in front of it is the interpreter's
# spawn command, which lives in here — bounding it this way survives a rename or a reorder inside
# the driver, which naming the neighbouring routine would not.
DRIVER_CODE_SPAN = (entry_of("sound_install_timer_a_dead"), A_PSG_REG_SHADOW)


def text_span():
    """[lo, hi) of the program's TEXT segment, from the .PRG header the kit's loader parses."""
    with open(harness.PRG, "rb") as handle:
        header = prg_dis.parse_header(handle.read())
    return loader.LOAD_BASE, loader.LOAD_BASE + header["tlen"]


def _call_target(image, at, hi):
    """Where the call at `at` goes, or None if `at` does not hold one that fits before `hi`."""
    if image[at] == BSR_OPCODE:
        if image[at + 1] != BSR_WORD_FORM:
            return at + BSR_BYTES + int.from_bytes(image[at + 1:at + 2], "big", signed=True)
        if at + BSR_WORD_BYTES <= hi:
            return at + BSR_BYTES + int.from_bytes(image[at + 2:at + 4], "big", signed=True)
        return None
    if (at + JSR_ABSOLUTE_LONG_BYTES <= hi
            and image[at:at + len(JSR_ABSOLUTE_LONG)] == JSR_ABSOLUTE_LONG):
        return int.from_bytes(image[at + 2:at + JSR_ABSOLUTE_LONG_BYTES], "big")
    return None


def sound_start_call_sites():
    """{sound number: [call site address, ...]} for every `sound_start` call in the TEXT.

    A site whose preceding two bytes are not a `moveq #n,d1` is filed under None: the driver's own
    spawn command is one (it computes the channel from the stream opcode and passes D1 straight
    through), and anything else would be a call this scan cannot read the argument of — which
    `check_call_sites_are_readable` treats as a finding rather than dropping silently.
    """
    image = harness.BASE_IMAGE
    lo, hi = text_span()
    sites = {}
    for at in range(lo, hi - BSR_BYTES, 2):
        if _call_target(image, at, hi) != ENTRY_SOUND_START:
            continue
        carries_number = at >= lo + MOVEQ_BYTES and image[at - MOVEQ_BYTES] == MOVEQ_D1_OPCODE
        sites.setdefault(image[at - 1] if carries_number else None, []).append(at)
    return sites


# ---- driving the driver -------------------------------------------------------------------------


def _vetted_psg_writes():
    """The last run's `(reg, value)` writes, with the two assumptions this tool rests on checked.

    A READ would mean the capture was served an answer the audio-capture mode invented rather than
    one the game's data produced (TRAP_MODEL.md, Phase 6); a write above the shadow's 14 registers
    would mean the driver touched the I/O ports, where the joystick and keyboard live. Neither can
    be discovered by listening to the result.
    """
    events = emu.psg_events()
    for kind, reg, value in events:
        if kind != os_map.OS_PSG_EVENT_WRITE:
            raise SystemExit("the driver READ PSG register %d (served %#x). Zynaps pushes its own "
                             "text-segment shadow blind and reads nothing back, so this answer is "
                             "the audio-capture mode's invention and the dump would rest on it"
                             % (reg, value))
        if reg >= PSG_SHADOW_REGS:
            raise SystemExit("the driver wrote PSG register %d (= %#x), but include/sound.h says it "
                             "keeps a %d-register shadow — registers %d and up are the I/O ports"
                             % (reg, value, PSG_SHADOW_REGS, PSG_SHADOW_REGS))
    return [(reg, value) for _kind, reg, value in events]


def _run(image, entry, regs=None):
    """One oracle run. Returns (final image, this run's PSG writes).

    `emu.run` raises on anything it cannot model, and that is left to propagate: mid-capture it
    means the replayer reached a hardware access `src/sound.c` does not describe, which is a
    finding.
    """
    image, _, _ = emu.run(image, entry, regs)
    return image, _vetted_psg_writes()


def _tick(image, number, frame):
    """One 50 Hz frame. Returns (image, the writes it made), with the flush's shape checked.

    The ORDER is checked and not merely the count, because a flush the other way round leaves an
    identical register file behind and only the ledger can see the difference — the same reason
    `src/sound.c` spells the descent out and `test_sound.py` compares the ledger at all.
    """
    image, writes = _run(image, ENTRY_SOUND_TICK)
    if tuple(reg for reg, _value in writes) != TICK_FLUSH_ORDER:
        raise SystemExit("sound %d's tick %d pushed registers %s, not the %s include/sound.h says "
                         "it flushes"
                         % (number, frame, [reg for reg, _v in writes], list(TICK_FLUSH_ORDER)))
    return image, writes


def _arm(image, number):
    """Silence the chip, then arm `number`. Returns (image, the register shadow it left).

    The reset is THIS TOOL's, not the game's: `_start` fires `sound_start` without one (the only
    caller of `sound_reset_psg` is the dead Timer-A arm at 0x16aa6). It is here because the shipped
    shadow leaves the mixer at 0xf8 rather than muted, so without it a number's first frames would
    carry two channels of whatever the shadow shipped with rather than the number's own opening.
    Its 14-register flush is the one `test_sound.py::test_reset_psg` verifies, and the count is
    asserted here so that a capture cannot silently start from a different chip state.
    """
    shadow = bytearray(YM_REGISTERS)
    image, writes = _run(image, ENTRY_SOUND_RESET_PSG)
    if len(writes) != PSG_SHADOW_REGS:
        raise SystemExit("sound_reset_psg made %d chip accesses, not the %d include/sound.h says it "
                         "pushes: every capture would start from an undeclared chip state"
                         % (len(writes), PSG_SHADOW_REGS))
    _fold(shadow, writes)
    image, writes = _run(image, ENTRY_SOUND_START,
                         {"d1": number, "d0": SOUND_START_FALLBACK_CHANNEL})
    _fold(shadow, writes)
    return image, shadow


def _fold(shadow, writes):
    """Apply one run's writes to the running register shadow. Returns the registers it touched."""
    touched = set()
    for reg, value in writes:
        shadow[reg] = value
        touched.add(reg)
    return touched


def _ym_frame(shadow, written_this_frame):
    """One frame's register file: masked to the bits the chip decodes (YM_REGISTER_MASKS), with
    register 13's "not written" convention honoured."""
    frame = bytearray(byte & mask for byte, mask in zip(shadow, YM_REGISTER_MASKS))
    if ENVELOPE_SHAPE_REG not in written_this_frame:
        frame[ENVELOPE_SHAPE_REG] = ENVELOPE_SHAPE_UNTOUCHED
    return bytes(frame)


def _driver_state(image):
    """The driver's mutable bytes, whose repetition means the output has looped forever."""
    return bytes(image[STATE_LO:STATE_HI])


def _musical_state(state):
    """`state` without the noise block's free-running counter pair — see the module docstring."""
    return state[:NOISE_COUNTERS_AT] + state[NOISE_COUNTERS_AT + NOISE_COUNTER_BYTES:]


def _live_voices(image):
    """Which of the three voices are armed right now, as the 1-based numbers names.txt uses."""
    return {number for number, voice in zip(VOICE_NUMBERS, VOICES) if image[voice + VOICE_ENABLE]}


def _first_repeat(states):
    """(index first seen, period) of the earliest repeated element, or (None, None).

    Used on the MUSICAL projection only, once a capture is over. The exact detector cannot be
    written this way — it has to answer after every tick, and rebuilding this dict each time would
    make a 15,000-frame capture quadratic — so `capture` carries its own `seen` map instead.
    """
    seen = {}
    for index, state in enumerate(states):
        if state in seen:
            return seen[state], index - seen[state]
        seen[state] = index
    return None, None


def capture(number):
    """Drive the replayer from a fresh image and return `number`'s per-frame register files.

    The tick loop runs to `SOUND_FRAME_CAP` unless the sound ends itself or its whole state
    repeats; only then is the musical fallback consulted, so the weaker rule can never pre-empt the
    exact one. `states[i]` is the state AFTER tick i+1 and `frames[i]` is the register file that
    tick FLUSHED, which the driver computed on tick i — hence `_loop_start_in_frames` shifting a
    state repeat by one frame.
    """
    image, shadow = _arm(harness.make_image(), number)
    frames, states, voices, psg_regs, state_seen = [], [], set(), set(), {}
    while len(frames) < SOUND_FRAME_CAP:
        image, writes = _tick(image, number, len(frames) + 1)
        touched = _fold(shadow, writes)
        psg_regs |= touched
        frames.append(_ym_frame(shadow, touched))
        live = _live_voices(image)
        voices |= live
        state = _driver_state(image)
        states.append(state)
        if not live:
            return Capture(number, frames, END_SELF, None, None, voices, psg_regs)
        if state in state_seen:
            return Capture(number, frames, END_LOOP, _loop_start_in_frames(state_seen[state]),
                           len(states) - 1 - state_seen[state], voices, psg_regs)
        state_seen[state] = len(states) - 1

    return _musical_capture(number, frames, states, voices, psg_regs)


def _loop_start_in_frames(state_loop_start):
    """A state repeat as a FRAME repeat: the flush that state produced is one tick later."""
    return state_loop_start + 1


def _musical_capture(number, frames, states, voices, psg_regs):
    """The fallback rule, applied to a capture that reached the cap without an exact loop.

    The file is truncated to lead-in + the loop played through twice, so a listener hears the join
    and the second period is on the page rather than merely asserted.
    """
    state_loop_start, loop_period = _first_repeat([_musical_state(state) for state in states])
    if state_loop_start is None:
        return Capture(number, frames, END_CAPPED, None, None, voices, psg_regs)
    loop_start = _loop_start_in_frames(state_loop_start)
    end_frame = loop_start + 2 * loop_period
    if end_frame > len(frames):
        return Capture(number, frames, END_CAPPED, None, None, voices, psg_regs)
    return Capture(number, frames[:end_frame], END_MUSICAL_LOOP, loop_start, loop_period,
                   voices, psg_regs)


def loop_replay_agreement(result):
    """What fraction of a musical loop's second period replays the first, frame for frame.

    NOT independent evidence, and reported for what it is: a frame IS the register shadow, and the
    shadow is inside the state the rule hashed, so a musical repeat implies a frame repeat and this
    comes out at 1.0 unless something is wrong. It is a consistency check on the frame/state
    alignment `_loop_start_in_frames` makes, not a measure of how musical the join is. None for an
    exact loop, whose capture stops AT the repeat and so holds one period.
    """
    start, period = result.loop_start, result.loop_period
    if start is None or start + 2 * period > len(result.frames):
        return None
    matched = sum(1 for offset in range(period)
                  if result.frames[start + offset] == result.frames[start + period + offset])
    return matched / period


# ---- what came out ------------------------------------------------------------------------------


def channel_sounds(frame, channel):
    """Is `channel` audible in `frame`? A gate open, and a volume that is not silence.

    Bit 4 of a volume register selects the ENVELOPE generator, and this driver never retriggers it
    (see the module docstring), so a channel-frame with that bit set is silent on hardware however
    large the byte is — which is why the level is not simply masked to four bits and compared.

    A channel with BOTH gates closed is silent here too, and that is the chip: it holds the DAC at
    a constant level, which is DC and not a sound. `check_silence_agrees_with_the_render` is where
    that meets the renderer, which emits that DC as samples.
    """
    volume = frame[VOLUME_REGS[channel]]
    if volume & VOLUME_ENVELOPE_BIT or not volume & VOLUME_LEVEL_MASK:
        return False
    mixer = frame[PSG_REG_MIXER]                                    # gates are active LOW
    return not (mixer >> channel) & 1 or not (mixer >> (channel + NOISE_MIXER_SHIFT)) & 1


def audible_frames(frames):
    """How many of `frames` would make a sound on the chip."""
    return sum(1 for frame in frames
               if any(channel_sounds(frame, channel) for channel in range(CHANNELS)))


def classify(result, audible):
    """music / sfx / silent, on what the capture DID rather than on where the number sits.

    The discriminator is whether the sound ends, not how many voices it uses. A voice count would
    misfile the several multi-voice one-shots this driver has — the ship explosion (0x14) arms two
    voices and is over in 3.8 s — while "does it stop?" separates a piece of music from an effect
    exactly. The voice count is reported beside it in the manifest, so the multi-voice one-shots
    stay visible. A capture that reached the cap without ending is music for the same reason, and
    the manifest's `ended` column is what distinguishes a proved loop from a cap.

    A number with no audible frame at all is SILENT whatever else it did: calling one "music"
    because three voices ticked would report the engine's activity rather than the chip's output.
    """
    if not audible:
        return KIND_SILENT
    return KIND_SFX if result.end == END_SELF else KIND_MUSIC


def tune_stream(number):
    """Where `sound_lookup_tune` resolves `number` to, read the same little-endian way the game
    does (docs/sound.md: the offset table is the Z80/AY original's, carried over unchanged)."""
    entry = A_TUNE_INDEX + number * TUNE_INDEX_ENTRY_BYTES
    offset = int.from_bytes(harness.BASE_IMAGE[entry:entry + TUNE_INDEX_ENTRY_BYTES], "little")
    return A_TUNE_DATA + offset


def stream_head(number, length):
    """The first `length` bytes of `number`'s stream, for a manifest line that has to show its
    working — a silent number is only a claim until its rows are on the page."""
    stream = tune_stream(number)
    return bytes(harness.BASE_IMAGE[stream:stream + length])


def has_channel_header(number):
    """Does the stream open with its own `fa <chan>`? One that does not is a CONTINUATION: it is
    reached by another stream's jump or spawn, and inherits that voice's volume/pitch tables."""
    return harness.BASE_IMAGE[tune_stream(number)] == SOUND_STREAM_CHANNEL_TAG


# ---- output -------------------------------------------------------------------------------------


def write_ym6(path, frames, loop_frame, title, comment):
    """Write `frames` (each `YM_REGISTERS` bytes) as an uncompressed interleaved YM6 file."""
    header = (YM6_MAGIC + YM6_CHECK
              + struct.pack(">IIHIHIH", len(frames), YM6_ATTRIBUTE_INTERLEAVED, YM6_DIGIDRUMS,
                            YM_CLOCK, FRAME_RATE, loop_frame, YM6_EXTRA_BYTES)
              + title.encode(YM6_TEXT_ENCODING) + b"\0" + YM6_AUTHOR + b"\0"
              + comment.encode(YM6_TEXT_ENCODING) + b"\0")
    interleaved = bytes(frame[reg] for reg in range(YM_REGISTERS) for frame in frames)
    with open(path, "wb") as handle:
        handle.write(header + interleaved + YM6_END)


def write_wav(path, frames):
    """Render `frames` through BuggyBoy's YM2149 synth and write 44100 Hz 16-bit mono.

    Returns the render's peak, in the track's own units — what `check_silence_agrees_with_render`
    compares against the register-level audibility count.

    `retriggers` is left None because no Zynaps tick writes register 13
    (`check_envelope_is_never_retriggered`), so the envelope generator never restarts. The frames
    handed over are the .YM's own, register 13 included — which carries ENVELOPE_SHAPE_UNTOUCHED
    rather than the 0 the reset pushed, and reads the same: `ym2149.render` starts its envelope
    past a full cycle, so every shape resolves to the completed (silent) level either way. So the
    .wav is a render of exactly the bytes the .ym holds.
    """
    track = ym2149.render(frames)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(SAMPLE_BYTES)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(numpy.clip(track * INT16_PEAK, -INT16_PEAK, INT16_PEAK)
                           .astype("<i2").tobytes())
    return float(max(track.max(), -track.min()))


def end_description(result):
    """How a capture ended, and for a loop what was proved."""
    if result.end not in LOOPED_ENDS:
        return result.end
    agreement = loop_replay_agreement(result)
    if agreement is None:
        return "%s (period %d frames, from frame %d)" % (result.end, result.loop_period,
                                                         result.loop_start)
    return "%s (period %d frames, from frame %d, second period replays %.0f%% of the first)" % (
        result.end, result.loop_period, result.loop_start, 100 * agreement)


def loop_frame(result):
    """The YM6 loop point. YM6 has no "does not loop" flag, so 0 — replay from the top — is the
    honest fallback for a self-ended or capped number, and the manifest is what says which."""
    return result.loop_start if result.end in LOOPED_ENDS else 0


def write_asset(out_dir, sound):
    """One number's .ym and .wav. Returns the render's peak level."""
    result = sound.capture
    stem = os.path.join(out_dir, "snd_%02d" % result.number)
    title = TITLE_PREFIX + "sound %d (%s)" % (result.number, sound.kind)
    comment = COMMENT_PREFIX + "%s, voices %s" % (sound.kind, sorted(result.voices) or "none")
    comment += "; capture ended: " + end_description(result)
    write_ym6(stem + ".ym", result.frames, loop_frame(result), title, comment)
    return write_wav(stem + ".wav", result.frames)


MANIFEST_STREAM_BYTES = 10                             # enough rows to see a header and a command
MANIFEST_COLUMNS = ("number", "kind", "voices", "frames", "seconds", "audible_frames",
                    "loops", "loop_start", "loop_period", "ended", "stream", "header", "used_by")

MANIFEST_HEADER = """\
# Zynaps (ST) — every sound the driver's index table holds, captured from ZYNAPS17.PRG by
# projects/zynaps/tools/extract_audio.py. One row per sound number; snd_NN.ym / snd_NN.wav beside
# this file. See projects/zynaps/README.md, "Music and sound effects".
#
# kind      music  = the capture proved a loop, or reached the cap: it does not end
#           sfx    = it stopped itself — command 0xe1 ran on every voice it had armed
#           silent = not one frame in which a gate was open over a non-envelope volume. Every
#                    silent number in this set is a CONTINUATION stream (header=no): it carries no
#                    0xe8 volume-table command, so `sound_voice_modulate` steps its volume byte
#                    from 0 with whatever record the voice already had. In the game they are
#                    reached by another stream's 0xe5 jump or 0xfc/0xfd/0xfe spawn, after the
#                    parent has chosen the tables; started cold there is nothing to select one.
#           A one-shot may still arm several voices — 0x14 (the ship exploding) arms two — so the
#           voices column and the kind are separate facts.
# voices    which of the driver's three voice records were armed during the capture. A stream with
#           no `fa` header of its own is dumped on voice 3, the driver's fall-through for a channel
#           byte that is neither 1 nor 2 — in the game the parent stream picks the voice instead.
# ended     self-ended / exact-loop / musical-loop / capped — see the tool's docstring
# stream    where sound_lookup_tune resolves the number to, and the first bytes of the row stream
# header    yes = the stream opens with its own `fa <chan>` and picks its voice; no = continuation
# used_by   every `bsr sound_start` in the game's TEXT with `moveq #<number>,d1` in front of it,
#           labelled through names.txt. Empty = nothing in the code starts this number directly.
"""


def manifest_row(sound, call_sites):
    result = sound.capture
    return "\t".join((
        str(result.number), sound.kind,
        ",".join(str(voice) for voice in sorted(result.voices)),
        str(len(result.frames)), "%.2f" % (len(result.frames) / FRAME_RATE), str(sound.audible),
        "yes" if result.end in LOOPED_ENDS else "no",
        str(result.loop_start) if result.loop_start is not None else "-",
        str(result.loop_period) if result.loop_period is not None else "-",
        end_description(result),
        "%#x %s" % (tune_stream(result.number),
                    stream_head(result.number, MANIFEST_STREAM_BYTES).hex(" ")),
        "yes" if has_channel_header(result.number) else "no",
        " ".join(harness.label(site) for site in call_sites.get(result.number, ())) or "-",
    ))


# ---- the checks the report rests on --------------------------------------------------------------

# The boot tune: `_start` reaches `sound_start` with `moveq #$b,d1` (names.txt, 0x1007a), and it is
# the title music — a three-voice piece that spawns 0x0c and 0x0d on voices 2 and 3.
BOOT_SOUND_NUMBER = 0x0b
BOOT_SPAWNED_VOICES = {1, 2, 3}
# The longest case in test_sound.py's `test_music_frames`, reused so the two ask the same question.
LEDGER_CHECK_FRAMES = 32
# One `sound_start` plus 32 ticks, chained through abi.STUB — test_sound.py's own MUSIC_INSN_CAP.
LEDGER_CHECK_INSN_CAP = 400_000
# The title music's own melody, measured: 571 distinct tone periods over its 13121 frames. The bar
# is an order of magnitude below that — it asks "did a melody happen?", not "is this that capture?".
MIN_BOOT_TUNE_TONE_PERIODS = 32
# Reproducibility is checked on a number that ends by itself, so the re-capture costs a hundred
# ticks rather than the boot tune's thirteen thousand.
REPRODUCIBILITY_SOUND_NUMBER = 0x1c


def check_tune_count():
    """Prove the index's length off the header's own addresses, and cross-check the boundary.

    `SOUND_COUNT` is derived, not typed: the index runs from `A_tune_index` up to
    `A_mod_table_data`, the next table's base, so its length is arithmetic on two constants
    `include/sound.h` owns. The second half is the fact `test_sound.py` pins as
    TUNE_FIRST_NEGATIVE_OFFSET — the first word past the table is the first with bit 15 set, which
    `adda.w` sign-extends to an address BELOW the data base. Two independent statements of the same
    boundary; a table that grew or moved fails here instead of dumping the next table as music.
    """
    def offset(number):
        at = A_TUNE_INDEX + number * TUNE_INDEX_ENTRY_BYTES
        return int.from_bytes(harness.BASE_IMAGE[at:at + TUNE_INDEX_ENTRY_BYTES], "little")

    negative = [number for number in range(SOUND_COUNT + 1) if offset(number) & TUNE_OFFSET_SIGN_BIT]
    if negative != [SOUND_COUNT]:
        raise SystemExit("the index at %#x holds %d entries before %#x, but its first "
                         "sign-extending offset is at entry %s rather than at %d: the two "
                         "boundaries disagree, so one of the two addresses is wrong"
                         % (A_TUNE_INDEX, SOUND_COUNT, A_MOD_TABLE_DATA, negative[:1] or "none",
                            SOUND_COUNT))


def _chained_ledger(calls, regs):
    """The PSG access stream of `calls` run as ONE oracle run through `abi.STUB`."""
    image = harness.make_image(abi.call_sequence_pokes(calls))
    emu.run(image, abi.STUB, regs, max_insns=LEDGER_CHECK_INSN_CAP)
    return _vetted_psg_writes()


def _per_tick_ledger(calls, regs):
    """...and of the same calls made as separate `emu.run`s, the way a capture drives them."""
    image, writes = harness.make_image(), []
    for entry in calls:
        image, made = _run(image, entry, regs if entry == calls[0] else None)
        writes += made
    return writes


def check_tick_ledger_matches_the_battery():
    """The tick-by-tick capture must produce the ledger `test_sound.py` verifies.

    This is what ties the dump to the verified player, and the sequence is DELIBERATELY the
    battery's own — `sound_start` then 32 ticks, no reset — because that is the case
    `test_music_frames` runs through `abi.call_sequence_pokes` as a SINGLE oracle run and compares,
    ledger and all, against the reconstruction. A capture instead makes N+1 separate `emu.run`
    calls, carrying the driver's state forward in the image and the chip's in the capture mode's
    register file. Nothing but this says the two agree, and if they did not, every .ym here would
    be a faithful recording of an artefact of how it was driven.

    The reset a real capture does first is not in the sequence for a reason beyond scope: the
    original ends `moveq #$d,d0` / `dbf d0`, so chaining it before `sound_start` would hand the
    stub's D0 to the arm as 0xffff rather than the capture's own argument. Its flush is checked
    where it happens, in `_arm`, against the count `test_sound.py::test_reset_psg` verifies.

    Returns the ledger both sides produced, so the report can quote its length.
    """
    calls = [ENTRY_SOUND_START] + [ENTRY_SOUND_TICK] * LEDGER_CHECK_FRAMES
    regs = {"d1": BOOT_SOUND_NUMBER, "d0": SOUND_START_FALLBACK_CHANNEL}
    chained = _chained_ledger(calls, regs)

    expected = LEDGER_CHECK_FRAMES * PSG_TICK_FLUSH_REGS
    if len(chained) != expected:
        raise SystemExit("%d ticks made %d chip accesses, not the %d test_sound.py asserts (%d per "
                         "tick) — the ledger this check compares is measuring the wrong thing"
                         % (LEDGER_CHECK_FRAMES, len(chained), expected, PSG_TICK_FLUSH_REGS))
    per_tick = _per_tick_ledger(calls, regs)
    if per_tick != chained:
        first = next(i for i, pair in enumerate(per_tick) if pair != chained[i])
        raise SystemExit("access %d of the boot tune's first %d frames differs between the "
                         "tick-by-tick capture (%s) and one chained run (%s): the capture's own "
                         "driving changes what the driver writes"
                         % (first, LEDGER_CHECK_FRAMES, per_tick[first], chained[first]))
    return chained


def tone_periods(frames):
    """Every distinct 12-bit tone period any channel was given across `frames`."""
    return {frame[TONE_FINE_REGS[channel]]
            | (frame[TONE_COARSE_REGS[channel]] & TONE_PERIOD_COARSE_MASK) << 8
            for frame in frames for channel in range(CHANNELS)}


def check_boot_tune_is_not_trivial(result):
    """The title music must be what names.txt says it is: three voices, looping, and playing notes.

    The period count is the part that catches a capture which ticked an engine that never started:
    a held note or a dead voice gives one or two periods, and this piece gives 571. The bar is set
    an order of magnitude below that so it reads as "a melody happened", not as a golden value.
    """
    if result.voices != BOOT_SPAWNED_VOICES:
        raise SystemExit("sound %#x armed voices %s, not %s: names.txt reads it as the title music, "
                         "which spawns 0x0c and 0x0d with `fd`/`fe`"
                         % (BOOT_SOUND_NUMBER, sorted(result.voices), sorted(BOOT_SPAWNED_VOICES)))
    if result.end not in LOOPED_ENDS:
        raise SystemExit("sound %#x ended %r; the title music is expected to loop, and a capture "
                         "that stops early is a truncated dump" % (BOOT_SOUND_NUMBER, result.end))
    periods = tone_periods(result.frames)
    if len(periods) < MIN_BOOT_TUNE_TONE_PERIODS:
        raise SystemExit("sound %#x uses only %d distinct tone period(s) over %d frames: the title "
                         "music should be a melody, so this capture ticked an engine that never "
                         "played" % (BOOT_SOUND_NUMBER, len(periods), len(result.frames)))
    return periods


def check_envelope_is_never_retriggered(captures):
    """No frame may claim a register-13 write. `sound_tick` pushes registers 10..0 and stops
    (names.txt, 0x16b94), which is what lets the renderer skip the envelope generator: the only
    reg-13 write in a capture is `sound_reset_psg`'s, before frame 1."""
    for result in captures:
        if ENVELOPE_SHAPE_REG in result.psg_regs:
            raise SystemExit("sound %d wrote PSG register %d, the envelope SHAPE: it retriggers the "
                             "envelope generator, which this dump renders as long completed"
                             % (result.number, ENVELOPE_SHAPE_REG))


def check_capture_is_reproducible(reference):
    """Re-capture one number after every other one and require the identical frame stream.

    The point is not that the emulator is deterministic — it is that nothing LEAKED between
    numbers. Every capture reloads the image, so the driver's own state is restored either way;
    what a fresh image does NOT restore is the oracle's modeled register file and select latch,
    which are process-global and span runs by design (TRAP_MODEL.md). Those are what this catches,
    and it is why `emu.audio_capturing()` scopes the whole sweep rather than each number.
    """
    again = capture(reference.number)
    if again.frames != reference.frames or again.end != reference.end:
        raise SystemExit("sound %d captured differently the second time (%d frames %s vs %d frames "
                         "%s): state leaked between captures"
                         % (reference.number, len(again.frames), again.end,
                            len(reference.frames), reference.end))


def check_silence_agrees_with_the_render(sounds):
    """A number is silent on the CHIP exactly when its .wav is silent, and vice versa.

    The two claims are made by different machinery — one counts open gates over non-envelope
    volumes in the register stream, the other is the peak of BuggyBoy's synth's output — so this is
    the one place they are made to agree. It is also the only check the peak-normalised render can
    carry: `ym2149.render` divides by its own peak, so no level here is comparable with another's,
    but a track that was zero everywhere stays zero.

    The threshold is one 16-bit quantisation step rather than exact zero, because a channel with
    both mixer gates closed holds the DAC at a constant the renderer emits as samples: `render`
    subtracts the track mean, so a steady level cancels to floating-point residue rather than to
    literal 0.0, and a level that STEPS would leave a sub-audio staircase that is inaudible and
    still not zero. Anything under one step writes an all-zero .wav, which is the claim being made.
    """
    for sound in sounds:
        silent_here = sound.kind == KIND_SILENT
        if silent_here != (sound.level < RENDER_SILENCE_PEAK):
            raise SystemExit("sound %d is %s by its register stream but its render peaks at %g "
                             "(silence threshold %g): the audibility rule and the synth disagree "
                             "about the same %d frames"
                             % (sound.capture.number, "silent" if silent_here else "audible",
                                sound.level, RENDER_SILENCE_PEAK, len(sound.capture.frames)))


def check_call_sites_are_readable(call_sites):
    """Every `sound_start` call the scan found must carry a readable `moveq #n,d1`, bar the
    driver's own spawn — which computes its channel from the stream opcode and passes D1 straight
    through (`src/sound.c`, SOUND_CMD_SPAWN_FIRST). An unreadable site anywhere else means the game
    starts a sound this manifest's "used by" column silently omits."""
    unreadable = [site for site in call_sites.get(None, ())
                  if not DRIVER_CODE_SPAN[0] <= site < DRIVER_CODE_SPAN[1]]
    if unreadable:
        raise SystemExit("`sound_start` is called from %s with no `moveq #n,d1` in front of it, so "
                         "the number started there cannot be read: the usage map would be missing "
                         "it silently" % ", ".join(harness.label(site) for site in unreadable))
    for number in call_sites:
        if number is not None and number >= SOUND_COUNT:
            raise SystemExit("the game starts sound %#x, which is past the %d-entry index at %#x — "
                             "either the scan misread a site or the table is bigger than the header "
                             "says" % (number, SOUND_COUNT, A_TUNE_INDEX))


# ---- report --------------------------------------------------------------------------------------


def kind_tally(sounds):
    """How the sweep classified the set, COUNTED — reported rather than asserted, so a number that
    stops being audible is visible instead of merely failing."""
    kinds = [sound.kind for sound in sounds]
    return ", ".join("%d %s" % (kinds.count(wanted), wanted)
                     for wanted in (KIND_MUSIC, KIND_SFX, KIND_SILENT))


def end_tally(sounds):
    ends = [sound.capture.end for sound in sounds]
    return ", ".join("%d %s" % (ends.count(reason), reason)
                     for reason in END_REASONS if reason in ends)


def report(sounds, ledger, periods, out_dir):
    total_frames = sum(len(sound.capture.frames) for sound in sounds)
    longest = max(sounds, key=lambda sound: len(sound.capture.frames)).capture
    silent = [sound.capture.number for sound in sounds if sound.kind == KIND_SILENT]
    boot = sounds[BOOT_SOUND_NUMBER].capture
    return "\n".join((
        "sounds: %d captured — %s" % (len(sounds), kind_tally(sounds)),
        "ends:   %s (cap %d frames)" % (end_tally(sounds), SOUND_FRAME_CAP),
        "length: %d frames = %.1f s at %d Hz; longest is sound %d at %.1f s"
        % (total_frames, total_frames / FRAME_RATE, FRAME_RATE, longest.number,
           len(longest.frames) / FRAME_RATE),
        "silent: %s (continuation streams — see manifest.tsv)"
        % (", ".join(str(number) for number in silent) or "none"),
        "title:  sound %#x is the boot tune AND the title music (names.txt, 0x1007a): %d frames "
        "over %d distinct tone periods on all three voices"
        % (BOOT_SOUND_NUMBER, len(boot.frames), len(periods)),
        "checks: index length derived from include/sound.h and its sign-extension boundary agree; "
        "%d chip accesses of test_sound.py's own %d-tick case identical tick-by-tick and chained; "
        "every tick flushes registers %d..0; register %d never written; no chip read served; "
        "silence agrees with the render on all %d; sound %d reproducible after the sweep"
        % (len(ledger), LEDGER_CHECK_FRAMES, PSG_TICK_FLUSH_REGS - 1, ENVELOPE_SHAPE_REG,
           len(sounds), REPRODUCIBILITY_SOUND_NUMBER),
        "",
        "wrote to %s" % out_dir,
    ))


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    check_tune_count()
    call_sites = sound_start_call_sites()
    check_call_sites_are_readable(call_sites)

    with emu.audio_capturing():
        ledger = check_tick_ledger_matches_the_battery()
        captures = [capture(number) for number in range(SOUND_COUNT)]
        # Everything that can be judged off the register stream is judged BEFORE a byte is written,
        # so a failing run does not leave a directory of files that look like a finished dump.
        periods = check_boot_tune_is_not_trivial(captures[BOOT_SOUND_NUMBER])
        check_envelope_is_never_retriggered(captures)
        check_capture_is_reproducible(captures[REPRODUCIBILITY_SOUND_NUMBER])

        sounds = []
        for result in captures:
            audible = audible_frames(result.frames)
            sound = Sound(result, classify(result, audible), audible, level=0.0)
            sounds.append(sound._replace(level=write_asset(out_dir, sound)))
        check_silence_agrees_with_the_render(sounds)

    # ...and the manifest last of all, so its presence marks the directory complete.
    with open(os.path.join(out_dir, "manifest.tsv"), "w") as handle:
        handle.write(MANIFEST_HEADER + "\t".join(MANIFEST_COLUMNS) + "\n"
                     + "\n".join(manifest_row(sound, call_sites) for sound in sounds) + "\n")
    print(report(sounds, ledger, periods, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
