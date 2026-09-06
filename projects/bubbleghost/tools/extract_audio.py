#!/usr/bin/env python3
"""Dump Bubble Ghost's (Atari ST, ERE Informatique / Accolade 1988) audio — both halves of it.

Usage:
  python3 projects/bubbleghost/tools/extract_audio.py [--voi | --synth] [OUT_DIR]

With no flag it runs BOTH halves into their own default directories (both gitignored):

  --voi     the digitised "Welcome to Bubble Ghost" speech in `bin/GHOST.VOI`, a static read of the
            file -> `out/assets` (this is what the tool has always done; nothing about it changed)
  --synth   the 11 sound effects and 36 per-room tones the PSG synth engine inside GHOST.PRG plays,
            captured by RUNNING THE ORIGINAL 68000 CODE -> `out/audio`

OUT_DIR overrides the default for whichever half was named, and is accepted only alongside a flag.

=================================================================================================
PART 1 — THE DIGITISED SPEECH (`--voi`)
=================================================================================================

Reads only `projects/bubbleghost/bin/GHOST.VOI` and writes the WAV plus `voi_envelope.png`, the
amplitude envelope — the surface that shows the phrase's word structure without anyone here being
able to listen to it.

The evidence for everything below is in `notes/assets_survey.md` (the container) and
`notes/loader.md` (the player). What the code embodies:

* ONE SAMPLE, NOT SEVERAL. `bin/GHOST.LOA` plays [address, address+0x7594) as a single sample, and
  0x7594 = 30,100 = the whole of GHOST.VOI. So the five gaps an envelope finds are pauses BETWEEN
  WORDS of the "Welcome to Bubble Ghost" phrase, not sound boundaries, and the file is exported
  whole.

* THE BYTES PASS THROUGH UNTOUCHED. GHOST.LOA's Timer A handler biases each byte by 0x80 and uses
  it to index a table of PSG volume triples that runs loud-to-quiet — i.e. unsigned 8-bit PCM
  centred on 128, which is exactly WAV's own 8-bit format. Polarity is NOT normalised (inaudible,
  and leaving it alone keeps the WAV a byte-for-byte copy of the file).

* THE RATE IS 14,985 Hz. The LOA header's rate index 3 selects MFP Timer A prescaler /4, data 41,
  so 2,457,600 / (4 x 41) = 14,985.37 Hz. A WAV header holds an integer, so it is floored — 0.0024%
  low. CONFIRMED that index 3 is what plays: the game's loader pokes only the sample-ADDRESS field
  at +0x1e of the LOA image and leaves the rate word as shipped (notes/loader.md).

=================================================================================================
PART 2 — THE PSG SYNTH ENGINE (`--synth`)
=================================================================================================

THERE IS NO MUSIC AND NO SEQUENCER, and that is a finding rather than a gap (`notes/sound_engine.md`
§9). Bubble Ghost's audio is a three-voice software ADSR + LFO synthesiser for the YM2149, ticked at
200 Hz by a Timer C ISR (`timer_c_sound_isr`) over three 0x8c-byte voice records. Every sound is one
ONE-SHOT VOICE RECORD, filled from a 0x70-byte definition by a single `sound_play` call: 11 fixed
effects (`snd_def_fx`) and 36 per-room tones (`snd_def_level`), 47 in all. The one thing that sounds
like a tune — the end-of-room bonus tally — is `game_top_loop` re-triggering `fx8` with a rising
note as it counts the bonus down, so it is captured here as a 48th track and is the frame loop's
doing, not a replayer's.

THIS IS AN ORACLE-DRIVEN CAPTURE, NOT A STATIC PARSE, exactly as
`projects/zynaps/tools/extract_audio.py` is: the ORIGINAL 68000 code runs under the kit's Musashi
oracle (`tools/recreate_kit`, bound to `../recreate/project.toml`) and what it writes to the chip is
recorded. The definitions cannot be read out of the .PRG at all — they live in BSS and are built one
`move.w #imm,(a1)+` at a time by `init_globals` — so the capture stages the POST-INIT IMAGE first,
the same fixture `../recreate/test/conftest.py` builds and `test_image_model.py` proves equal to
what the real crt0 produces.

HOW THE ISR IS DRIVEN. `timer_c_sound_isr` is an interrupt handler, not a routine: it takes no
arguments, loads everything it needs from the 13-byte `snd_isr_state` block (four fields, 4+4+4+1,
with one byte of padding after them before `psg_gate`), and does NOT `rte` —
it restores its registers, PUSHES THE SAVED $114 VECTOR AND `rts`es, chaining to TOS's own Timer C
handler (`notes/sound_engine.md` §2). So a capture has to supply that block and that chain:

  * `snd_isr_state` is filled with what `install_sound_vectors` would write — `&snd_volume_scale`
    (the ISR's a2), `&snd_voice[2]` (its a0, the loop walks DOWN by 0x8c) and the saved $484 conterm
    — except that the chained vector is set to the ORACLE'S SENTINEL. The ISR's own `rts` then lands
    on the address `emu.run` treats as "returned", so the run ends exactly where TOS's handler would
    have started and nothing fabricates a Timer C handler that is not in this program.
  * The `trap #9` vector at $a4 is pointed at `trap9_psg_handler`, because `sound_play` reaches the
    chip only through the `psg_gate` stub and an unvectored trap would run the 68000's vector page.
  * `install_sound_vectors` itself is NOT run. It writes $fffffa17 (the MFP vector register, to put
    the MFP in automatic-EOI mode) and $114, neither of which means anything to a capture, and it
    would take the chain vector from this image's $114 — which is 0.

Then per track: stage a fresh post-init image, `sound_stop_all` (the game's own reset — it is the
second half of `sound_start`), `sound_play(def, voice, volume, note, priority)` with the arguments
the game's own call site passes, and then one `emu.run` at the ISR's entry per 200 Hz tick. Each
tick's `(reg, value)` writes are folded into a running 16-register shadow and the shadow is
snapshotted; that snapshot IS one frame of the dump.

WHERE EACH CAPTURE STOPS. Three rules, and the manifest says which one ended each track:

  idle       the voice's duration counter reached 0 — the ISR ran its release, wrote volume 0 and
             stopped. Every `note < 0` trigger ends this way; that is what a negative gate MEANS
             (`notes/sound_engine.md` §3.5).
  capped     SYNTH_TICK_CAP ticks without that. A `note >= 0` trigger SUSTAINS — its duration
             counter never runs, and only the game stops it — so `fx2` (room_wipe_in's tone) and
             `fx3` (the blow) run to the cap and their .wav is 30 s of a sound the game holds for as
             long as it wants to. Both are STILL SOUNDING there rather than a spent voice being
             ticked: `check_capped_tracks_still_sound` is what says so, and the two are different in
             kind — fx3 is continuous wind, fx2 a 33 Hz tremolo pulse its volume LFO never stops.
  stopped    the game's own `sound_stop_voice` ran, which is how the bonus tally ends (0x10aa0).

WHY THE AUDIO-CAPTURE MODE. Unlike Zynaps' driver, this one READS THE CHIP BACK: `trap9_psg_handler`
does a read-modify-write of the mixer (register 7) to preserve the other two channels' bits and
TOS's port-direction bits, and returns every register it touches. Off `emu.audio_capturing()` the
oracle refuses to invent a register nothing declared, which is right for a differential and would
end this capture at the first `sound_play`. Under the mode those reads answer from a register file
that spans runs — which is what the chip's own latch does between two interrupts. TWO CONSEQUENCES
ARE STATED RATHER THAN HIDDEN: the file starts at all-zeroes, so (a) the mixer's other channels read
back as gated ON, which is inaudible because their volumes are 0, and (b) mixer bits 6/7 — the I/O
PORT DIRECTION bits TOS owns and this game preserves — read back 0 where a real machine has them
set. Neither reaches the audio; both are in the manifest.

WHAT IS WRITTEN, per track: `<name>.ym` (uncompressed interleaved YM6, the same container
`projects/zynaps/tools/extract_audio.py` and `projects/wonderboy/tools/extract_audio.py` write) at
200 FRAMES PER SECOND — YM6 carries the player frequency in its header, so this is a declaration and
not a resampling; `<name>.wav`, rendered through BuggyBoy's `recreate/sound/ym2149.py`; and
`manifest.tsv` LAST, so its presence is what marks the directory complete. A run that fails leaves
the files it got to and no manifest.

THE RENDER RATE IS 48000 Hz AND NOT 44100. The renderer's frame is `rate // fps` samples, so an
exact number of samples per tick needs a rate divisible by the tick rate: 44100/200 = 220.5 would
make every tick 0.23% short, and 48000/200 = 240 is exact. The 200 Hz tick reaches the renderer as
`ym2149.render(..., fps=SYNTH_TICK_RATE_HZ)`, a per-call argument: its module-scope `FPS` is the
50 Hz VBL its own project's callers use, and one process can hold both.
"""

import argparse
import itertools
import os
import re
import sys
import wave
from collections import namedtuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))
RECREATE_DIR = os.path.join(PROJECT_DIR, "recreate")
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from st_pixels import to_rgb_image  # noqa: E402  (needs the path above)

BIN_DIR = os.path.join(PROJECT_DIR, "bin")
DEFAULT_VOI_DIR = os.path.join(PROJECT_DIR, "out", "assets")
DEFAULT_SYNTH_DIR = os.path.join(PROJECT_DIR, "out", "audio")

# =================================================================================================
# PART 1 — the digitised speech
# =================================================================================================

VOI_NAME = "GHOST.VOI"
VOI_SOUND_NAME = "welcome"  # the phrase the one sample holds

# Unsigned 8-bit PCM: this is the value a silent sample sits on, and WAV's own 8-bit zero.
PCM_ZERO = 128
BYTES_PER_SAMPLE = 1
CHANNELS = 1

# The playback rate, from the MFP registers GHOST.LOA programs (see the docstring).
MFP_CLOCK_HZ = 2457600
TIMER_A_PRESCALE = 4   # Timer A control 1
TIMER_A_DATA = 41      # Timer A data 0x29
# Exactly 14985.3658... Hz; a WAV header holds an integer, and rounding down costs 0.0024%.
VOI_RATE_HZ = MFP_CLOCK_HZ // (TIMER_A_PRESCALE * TIMER_A_DATA)

ENVELOPE_WINDOW = 256  # ~17 ms at the real rate: long enough to ride over a waveform's zero
ENVELOPE_PNG_HEIGHT = 200
ENVELOPE_PNG_DECIMATION = 10  # one pixel column per this many samples
ENVELOPE_PNG_FULL_SCALE = 128  # |sample - 128| at the top of the plot
BACKGROUND_INDEX, WAVE_INDEX, ENVELOPE_INDEX = 0, 1, 2
ENVELOPE_PALETTE = [(0, 0, 0), (70, 70, 70), (240, 90, 90)]


def windowed_mean_deviation(samples, window, at_samples):
    """Mean |sample - 128| over a `window` centred on each of `at_samples`.

    A prefix sum makes every value one subtraction, and each mean is divided by its own CLIPPED
    span rather than by a running count: a full-window divisor at the tail made a constant input's
    last window/2 values ramp down to half of the true level.
    """
    totals = list(itertools.accumulate((abs(sample - PCM_ZERO) for sample in samples), initial=0))
    half = window // 2
    means = []
    for at in at_samples:
        start = max(0, at - half)
        stop = min(len(samples), at - half + window)
        means.append((totals[stop] - totals[start]) / (stop - start))
    return means


def write_wav(path, samples):
    with wave.open(path, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(BYTES_PER_SAMPLE)
        handle.setframerate(VOI_RATE_HZ)
        handle.writeframes(samples)


def waveform_stats(samples):
    """(DC offset from 128, peak deviation, RMS deviation) — the listen test stand-in."""
    deviations = [sample - PCM_ZERO for sample in samples]
    mean = sum(deviations) / len(deviations)
    rms = (sum(value * value for value in deviations) / len(deviations)) ** 0.5
    return mean, max(abs(value) for value in deviations), rms


def plot_row(deviation):
    """The pixel row a deviation from 128 plots at, 0 being the top of the picture."""
    scaled = int(deviation / ENVELOPE_PNG_FULL_SCALE * (ENVELOPE_PNG_HEIGHT - 1))
    return ENVELOPE_PNG_HEIGHT - 1 - max(0, min(ENVELOPE_PNG_HEIGHT - 1, scaled))


def write_envelope_png(path, samples):
    """The waveform under its smoothed envelope: the phrase's words show as separated bursts."""
    width = len(samples) // ENVELOPE_PNG_DECIMATION
    at_samples = [column * ENVELOPE_PNG_DECIMATION for column in range(width)]
    envelope = windowed_mean_deviation(samples, ENVELOPE_WINDOW, at_samples)
    rows = [[BACKGROUND_INDEX] * width for _ in range(ENVELOPE_PNG_HEIGHT)]
    for column, (at, mean) in enumerate(zip(at_samples, envelope)):
        for row in range(plot_row(abs(samples[at] - PCM_ZERO)), ENVELOPE_PNG_HEIGHT):
            rows[row][column] = WAVE_INDEX
        rows[plot_row(mean)][column] = ENVELOPE_INDEX
    to_rgb_image(rows, ENVELOPE_PALETTE).save(path)


def extract_voi(out_dir):
    """Part 1: GHOST.VOI -> one WAV and its envelope plot. Returns the report line."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(BIN_DIR, VOI_NAME), "rb") as handle:
        samples = handle.read()

    name = "voi_%s_%dhz.wav" % (VOI_SOUND_NAME, VOI_RATE_HZ)
    write_wav(os.path.join(out_dir, name), samples)
    write_envelope_png(os.path.join(out_dir, "voi_envelope.png"), samples)

    seconds = len(samples) / VOI_RATE_HZ
    dc, peak, rms = waveform_stats(samples)
    return ("speech: %d bytes -> one %.2f s sample at %d Hz (DC %+.1f, peak %d, RMS %.1f) -> %s"
            % (len(samples), seconds, VOI_RATE_HZ, dc, peak, rms, out_dir))


# =================================================================================================
# PART 2 — the PSG synth engine
# =================================================================================================
# The kit is imported EAGERLY, as projects/zynaps/tools/extract_audio.py does, but a failure is
# recorded rather than raised: a `--voi` run is a static read of one file and must not need a built
# oracle, a built candidate library, or numpy.

try:
    from recreate_kit import project                    # noqa: E402  (needs REPO_ROOT/tools above)

    project.load(RECREATE_DIR)                          # binds the kit to this game's project.toml
    sys.path.insert(0, os.path.join(RECREATE_DIR, "test"))       # harness.py, abi.py
    # BuggyBoy's YM2149 synth is the workspace's ONE renderer (docs/sound.md): imported, never
    # copied, so there is one set of DAC and envelope approximations rather than two.
    sys.path.insert(0, os.path.join(REPO_ROOT, "projects", "buggyboy", "recreate", "sound"))
    from recreate_kit import os_map                     # noqa: E402  (must follow project.load)
    import emu                                          # noqa: E402
    import harness                                      # noqa: E402  (recreate/test/harness.py)
    import abi                                          # noqa: E402  (recreate/test/abi.py)
    import ym2149                                       # noqa: E402  (BuggyBoy's YM2149 synth)
    # The .ym/.wav writers and the audibility rule, shared with the sibling projects' extractors.
    # It needs numpy, as `ym2149` does, which is why both are imported HERE and not beside
    # `st_pixels`: a `--voi` run is a static read of one file and must keep working without it.
    import ym_capture                                   # noqa: E402  (REPO_ROOT/tools)
except (OSError, RuntimeError, ImportError) as error:
    # OSError is the ctypes.CDLL behind the oracle or the candidate; RuntimeError is the kit's own
    # stale-.so check; ImportError is numpy, which only the render and the writers need.
    KIT_ERROR = error
else:
    KIT_ERROR = None

KIT_ERROR_HELP = ("the --synth capture drives the kit's Musashi oracle, this project's own library "
                  "and BuggyBoy's YM2149 renderer, and one of them is missing or out of date "
                  "(%s):\n"
                  "  make -C projects/bubbleghost/recreate oracle\n"
                  "  make -C projects/bubbleghost/recreate\n"
                  "...and run it with the atari_reverse conda env's python (ym2149 needs numpy).")

# ---- the engine's own numbers, from notes/sound_engine.md ----------------------------------------
# Every one is pinned there against the instruction that reads it; the section is named beside it.
# The layout half of them is ALSO spelt by `../recreate/include/sound.h`, and
# `check_layout_matches_the_reconstruction` is where the two readings are made to agree.

# TOS's Timer C rate, READ OUT OF TOS AND NOT MEASURED HERE. §2 pins which MFP channel the installer
# puts the ISR on — channel 5, Timer C — and nothing in this image programs that timer's divider, so
# 200 Hz is the rate TOS itself sets it to at boot. It is the one number below that this program's
# own bytes do not contain, and the manifest header says so.
SYNTH_TICK_RATE_HZ = 200
DEF_STRIDE = 0x70               # §7 step 5: a definition IS a voice record's first 0x70 bytes
RECORD_STRIDE = 0x8c            # §3: snd_voice[v] = snd_voice + 0x8c*v; v is also the PSG channel
RECORD_DURATION = 0x00          # §3.1: the duration counter, in ticks. 0 = the voice is idle
DEF_TONE_PERIOD = 0x02          # §3.1: base tone period; negative = this voice's tone is off
DEF_NOISE_PERIOD = 0x04         # §3.1: base noise period; negative = noise off
VOICES = 3                      # §3: three voice records, three PSG channels
ROOM_COUNT = 36                 # §8.2, and re-derived from the table addresses by check_table_sizes
FX_COUNT = 11                   # §8.1, likewise
CANDLE_FX_FIRST = 5             # §8: room_candle_sfx[room] picks snd_def_fx[5 + n], -1 = none
ROOM_RECORD_STRIDE = 0x78       # §8: room_candle_sfx is room_table + 0x74, one word per room
NO_CANDLE = -1

# The four bytes of `snd_isr_state` install_sound_vectors fills, in the order it walks them with
# `(a0)+` (§2). The ISR reads the second and third into a2 and a0 and chains through the first.
ISR_STATE_CHAIN_VECTOR = 0x00   # long: TOS's own $114. The ISR pushes it and rts's
ISR_STATE_VOLUME_SCALE = 0x04   # long: &snd_volume_scale, into a2 at 0x1459e
ISR_STATE_VOICE_TOP = 0x08      # long: &snd_voice[2], into a0 at 0x145a2
ISR_STATE_CONTERM = 0x0c        # byte: TOS's own $484, restored when all three voices are idle

TOS_CONTERM = 0x484             # the byte the ISR zeroes every tick so TOS's key click cannot
                                # reach the PSG under it (§2)
TRAP_VECTOR_BASE = 0x80         # the 68000's TRAP #0 vector; trap #n is four bytes further on
PSG_GATE_TRAP = 9               # `trap #9` in psg_gate (0x1494c), vectored at 0x14906 to
                                # trap9_psg_handler — the ONLY door this engine has to the chip
                                # outside the ISR
TRAP9_VECTOR = TRAP_VECTOR_BASE + 4 * PSG_GATE_TRAP

# The a5 `init_globals` needs, and the two instruction counts, from the recipe
# `../recreate/test/conftest.py` documents at length and `test_image_model.py` proves against the
# real crt0. THAT FILE IS THE PINNED ORIGINAL and this is a copy: a test module is not a library,
# and importing one would drag pytest's fixtures in behind it. So the copy is checked rather than
# trusted — `post_init_image` asserts the run really executed INIT_GLOBALS_INSNS instructions, which
# is the same assertion `test_image_model.py::test_the_post_init_run_is_the_length_conftest_states`
# makes.
INIT_GLOBALS_A5_DEFINE = "BG_LOAD_BASE"  # = p_tbase; the last paragraph builds `lea n(a5)` pointers
INIT_GLOBALS_INSNS = 7_871      # measured; one long `move #imm,n(a4)` run over the whole BSS
INIT_GLOBALS_MAX_INSNS = 50_000  # bounded by the BSS size, not by a loop — loose, not a tuning knob

PLAY_INSN_CAP = 50_000          # sound_play copies 55 words and makes six trap #9 gate calls
TICK_INSN_CAP = 20_000          # one ISR tick is three voice records of straight-line arithmetic

# 30 s of ticks. The longest definition in the set runs 1,400 ticks (fx0, 7 s) and the longest room
# tone 940, so this is not a bound on anything that ends — it is where a SUSTAINED sound is cut.
SYNTH_TICK_CAP = 30 * SYNTH_TICK_RATE_HZ

# ---- the YM2149 as the dump sees it --------------------------------------------------------------
# The register numbers and the audibility rule are the CHIP's, not this game's, and live in
# `tools/ym_capture.py` with the two writers — this section names only what is specific to the dump.

PSG_TONE_FINE_REGS = (0, 2, 4)                         # register 2v for voice v
PSG_TONE_COARSE_REGS = (1, 3, 5)                       # ...and 2v+1
PSG_NOISE_PERIOD_REG = 6
PSG_MIXER_REG = 7
PSG_ENVELOPE_REGS = (11, 12, 13)                       # never written by this engine (§1)
TONE_PERIOD_COARSE_MASK = 0x0f
NOISE_PERIOD_MASK = 0x1f
MIXER_MASK = 0x3f                                      # 3 tone gates + 3 noise gates
VOLUME_REG_MASK = 0x1f                                 # 4-bit level + the envelope-mode bit

# Which bits of each register the CHIP decodes. It matters for the .ym and not for the render:
# YM5/YM6 reuse the dead bits of registers 1, 3, 6, 7, 14 and 15 as SPECIAL-EFFECT CODES, so a
# player handed a raw shadow byte with rubbish above the field starts an effect on whatever voice
# those bits happen to name.
YM_REGISTER_MASKS = bytes((
    0xff, TONE_PERIOD_COARSE_MASK,                     # 0/1: channel A tone period
    0xff, TONE_PERIOD_COARSE_MASK,                     # 2/3: channel B
    0xff, TONE_PERIOD_COARSE_MASK,                     # 4/5: channel C
    NOISE_PERIOD_MASK,                                 # 6:   noise period
    MIXER_MASK,                                        # 7:   mixer
    VOLUME_REG_MASK, VOLUME_REG_MASK, VOLUME_REG_MASK,  # 8-10: channel volumes
    0xff, 0xff, 0xff, 0xff, 0xff,                      # 11-15: never written at all
))

# Register 13 is WRITE-TRIGGERED on the real chip, so the YM formats spell "not written this frame"
# as 0xff rather than as a repeat. This engine never writes it — check_envelope_registers_silent is
# what says so — and every frame therefore carries this.
ENVELOPE_SHAPE_REG = 13
ENVELOPE_SHAPE_UNTOUCHED = 0xff

# ---- the render ----------------------------------------------------------------------------------
# 44100 is NOT divisible by the 200 Hz tick (220.5 samples), 48000 is (240). See the docstring.
SYNTH_SAMPLE_RATE = 48000

if SYNTH_SAMPLE_RATE % SYNTH_TICK_RATE_HZ:
    raise SystemExit("a render rate of %d Hz is not divisible by the %d Hz tick, so a tick would "
                     "be a fractional number of samples and the renderer would floor "
                     "it: every track would run short by the remainder, tick after tick"
                     % (SYNTH_SAMPLE_RATE, SYNTH_TICK_RATE_HZ))

# ---- how a capture ended -------------------------------------------------------------------------

END_IDLE = "idle"                                      # the voice's duration counter reached 0
END_CAPPED = "capped"                                  # a sustained sound, cut at SYNTH_TICK_CAP
END_STOPPED = "stopped"                                # the game's own sound_stop_voice ran
END_REASONS = (END_IDLE, END_CAPPED, END_STOPPED)

KIND_FX = "fx"                                         # one of snd_def_fx[0..10]
KIND_ROOM = "room"                                     # one of snd_def_level[0..35]
KIND_TALLY = "tally"                                   # the bonus glissando — 57 retriggers of fx8
KINDS = (KIND_FX, KIND_ROOM, KIND_TALLY)

# One `sound_play` call, with the arguments the game's own call site passes. `volume` is the
# NOMINAL index k: every site multiplies it by `sound_enabled` (§8), which this capture reads out
# of the image rather than assuming.
Trigger = namedtuple("Trigger", "definition voice volume note priority")
# `plays` is [(Trigger, hold_ticks)]; hold_ticks None means "tick until the voice goes idle, or the
# cap". `stop_voice` is the voice the GAME hard-stops when it is done, or None.
Track = namedtuple("Track", "name kind plays stop_voice call_site what")
Capture = namedtuple("Capture", "track frames end regs writes reads tick_writes trigger_periods")


# ---- addressing by name --------------------------------------------------------------------------


def entry_of(name):
    """The address `../names.txt` gives `name`, or a loud failure.

    `harness.NAME_MAP` is the kit's own parse of that file, inverted here. A name that is missing or
    ambiguous is a bug in the map, not something to fall back from: capturing at a stale address
    would produce a plausible dump of the wrong routine or the wrong table.
    """
    matches = sorted(addr for addr, label in harness.NAME_MAP.items() if label == name)
    if len(matches) != 1:
        raise SystemExit("../names.txt gives the name %r %d addresses (%s); this tool needs "
                         "exactly one, because it enters or reads the 68000 there"
                         % (name, len(matches), ", ".join("%#x" % a for a in matches)))
    return matches[0]


# Every address the capture enters or reads, by name. `object_table` is here for one reason: it is
# what BOUNDS snd_def_fx at 11 entries (§8.2), and check_table_sizes derives the count from it.
SOUND_NAMES = ("sound_play", "sound_stop_voice", "sound_stop_all", "timer_c_sound_isr",
               "snd_isr_state", "trap9_psg_handler", "snd_voice", "snd_volume_scale",
               "snd_note_period", "snd_def_fx", "snd_def_level", "room_candle_sfx",
               "sound_enabled", "object_table")
Sound = namedtuple("Sound", SOUND_NAMES)

SND = Sound(*(entry_of(name) for name in SOUND_NAMES)) if KIT_ERROR is None else None
# The crt0's last call, looked up the same way — the capture ENTERS it, so a stale address here
# would stage an image whose 47 definitions are still the BSS's zeroes.
INIT_GLOBALS = entry_of("init_globals") if KIT_ERROR is None else None


# ---- the reconstruction's own spelling of the layout ---------------------------------------------
# The record and ISR-state offsets above are read off the ORIGINAL's disassembly
# (notes/sound_engine.md); `../recreate/include/sound.h` states the same layout for the port. Two
# readings of one program have to agree, and CLAUDE.md's rule for a value that cannot cross a
# language boundary applies: pick one canonical definition and pin the other equal.
#
# The pin is ONE-WAY on purpose. Sourcing these values FROM the header would make a capture of the
# original silently follow a mistake in the port, which is the one thing a capture must not do.

# The ten-line `#define` scraper, RE-SPELT here rather than imported from
# `../recreate/test/test_constants.py::_iter_defines`, which has the same one: that is a test module
# and not a library, and importing it would drag pytest's fixtures in behind it. A value built from
# other macros or from arithmetic is deliberately out of reach — evaluating one would be a C
# preprocessor rather than a scraper — so every pin below names a define that is a plain literal.
DEFINE_RE = re.compile(r"^#define\s+(?P<name>\w+)\s+(?P<value>0[xX][0-9a-fA-F]+|\d+)[uU]?"
                       r"(?=\s*(?:/[/*]|$))", re.M)
SOUND_H = os.path.join(RECREATE_DIR, "include", "sound.h")
GLOBALS_H = os.path.join(RECREATE_DIR, "include", "globals.h")


def header_defines(path):
    """{name: value} for every plain-integer `#define` in one C header."""
    with open(path) as handle:
        return {found["name"]: int(found["value"], 0)
                for found in DEFINE_RE.finditer(handle.read())}


def header_value(path, name):
    """One `#define`'s value, or a loud failure naming the define and the header it is missing from.

    A name that has been renamed or turned into an expression is a stale reference here, not a
    satisfied pin: falling back to a number typed in this file is exactly the drift the pin exists
    to catch.
    """
    defines = header_defines(path)
    if name not in defines:
        raise SystemExit("%s does not define %s as a plain integer literal, so this tool cannot "
                         "read it out of the reconstruction's own header — it has been renamed, or "
                         "built from other macros, and the reference here is stale"
                         % (os.path.relpath(path, PROJECT_DIR), name))
    return defines[name]


# (this tool's name for it, its value, the `sound.h` define that has to agree).
SOUND_H_PINS = (
    ("VOICES", VOICES, "SND_VOICES"),
    ("RECORD_STRIDE", RECORD_STRIDE, "SND_VOICE_BYTES"),
    ("DEF_STRIDE", DEF_STRIDE, "SND_DEF_BYTES"),
    ("RECORD_DURATION", RECORD_DURATION, "SND_VC_DURATION"),
    ("DEF_TONE_PERIOD", DEF_TONE_PERIOD, "SND_VC_TONE_PERIOD"),
    ("DEF_NOISE_PERIOD", DEF_NOISE_PERIOD, "SND_VC_NOISE_PERIOD"),
    ("TOS_CONTERM", TOS_CONTERM, "TOS_CONTERM"),
    ("TRAP9_VECTOR", TRAP9_VECTOR, "TOS_VEC_TRAP9"),
    ("PSG_NOISE_PERIOD_REG", PSG_NOISE_PERIOD_REG, "PSG_REG_NOISE"),
    ("PSG_MIXER_REG", PSG_MIXER_REG, "PSG_REG_MIXER"),
)
# ...and the ISR-state offsets, which the header spells as the ABSOLUTE addresses the installer
# writes to. Each is its distance from the block's base, which is the first field — so the base
# itself is pinned against `../names.txt` rather than against a distance from itself.
ISR_STATE_BASE_DEFINE = "SND_ISR_SAVED_TIMER_C"
ISR_STATE_OFFSET_PINS = (
    ("ISR_STATE_VOLUME_SCALE", ISR_STATE_VOLUME_SCALE, "SND_ISR_VOLUME_SCALE"),
    ("ISR_STATE_VOICE_TOP", ISR_STATE_VOICE_TOP, "SND_ISR_TOP_VOICE"),
    ("ISR_STATE_CONTERM", ISR_STATE_CONTERM, "SND_ISR_SAVED_CONTERM"),
)


# ---- who plays what, from the game's own call sites ----------------------------------------------
# Read off `out/prg_dis.txt` at each `jsr $142bc`, cross-checked against notes/sound_engine.md §8:
# the pushes run priority, note, sound_enabled*k, voice, &definition, so the argument list is that
# list reversed. (fx, call site, voice, k, note, priority, what the surrounding code is doing.)

ROOM_TRIGGER = (0x108b6, 0, 7, -1, 5, "room start in game_top_loop, after Random/Setpalette")
# fx5..fx10 have no direct call site: the room's candle picks one through room_candle_sfx.
CANDLE_TRIGGER = (0x12e1e, 1, 13, -1, 10, "the room's candle, in ghost_blow")
FX_TRIGGERS = {
    0: (0x10910, 2, 9, -1, 10, "end of room: releases voice 1, flashes colour 15, then tallies"),
    1: (0x10b40, 2, 8, -1, 10, "the other end-of-room arm (releases voice 1 first)"),
    2: (0x13b5a, 0, 8, 60, 5, "room_wipe_in's sustained C4, stopped 190 bytes later at 0x13bdc"),
    3: (0x11a6e, 1, 8, 250, 5, "THE BLOW - sustained; released at 0x11a7c / by ghost_blow"),
    4: (0x11aa4, 2, 11, -1, 5, "the bubble popping (guarded on bubble_frame == 0)"),
}

# The bonus tally (§9), the one thing in this game that sounds like a melody. `game_top_loop` runs
#   while (bonus_bar > 0x23) { sound_play(fx8, 2, sound_enabled*8, 100 - bonus_bar/4, 10);
#                              bonus_bar -= 5; ... }
#   sound_stop_voice(2);
# at 0x10a36..0x10aa0. Every number below is that loop's, read off the disassembly.
TALLY_FX = 8
TALLY_TRIGGER = (0x10a68, 2, 8, 10, "the bonus tally in game_top_loop - a retrigger per 5 points")
BONUS_BAR_START = 0x13e         # what game_top_loop sets bonus_bar to at room start (0x10292)
BONUS_BAR_FLOOR = 0x23          # the loop's `cmpi.w #$23` — and where the HUD bar stops shrinking
BONUS_BAR_STEP = 5              # `subq.w #5,bonus_bar` per note
TALLY_NOTE_BASE = 100           # `move.w #$64,d0` — note = 100 - bonus_bar/4
TALLY_NOTE_DIVISOR = 4          # `divs.w #$4,d1`, which truncates toward zero (bonus_bar > 0 here)
# THE ONE NUMBER THE BINARY DOES NOT FIX. The tally loop has no Vsync and no timer wait — its pace
# is however long hud_bonus_bar_shrink + hud_draw_counters + present_score_strip take, which is four
# VDI v_gtext calls and a 4 KB screen copy per note. 50 ms is a plausible reading of that on an 8
# ST and is the only value here that is an estimate rather than a measurement; the manifest says so.
TALLY_TICKS_PER_NOTE = 10


def bonus_bar_values():
    """The bonus_bar the tally loop plays a note at, in order — the game's own `while`/`subq`."""
    bar = BONUS_BAR_START
    while bar > BONUS_BAR_FLOOR:
        yield bar
        bar -= BONUS_BAR_STEP


def tally_note(bonus_bar):
    """`note = 100 - bonus_bar/4`, the argument game_top_loop computes at 0x10a44."""
    return TALLY_NOTE_BASE - bonus_bar // TALLY_NOTE_DIVISOR


def definition_of(table, index):
    """`table[index]`, the definitions being 0x70 bytes and contiguous."""
    return table + index * DEF_STRIDE


def rooms_playing_fx(image, fx):
    """Which rooms' candles select `snd_def_fx[fx]`, from room_candle_sfx — the provenance for the
    six effects that have no direct call site of their own (§8.1)."""
    return [room for room in range(ROOM_COUNT)
            if candle_fx_of(image, room) == fx - CANDLE_FX_FIRST]


def candle_fx_of(image, room):
    """`room_candle_sfx[room]`: the index into snd_def_fx[5..10], or -1 for a candle-less room."""
    at = SND.room_candle_sfx + room * ROOM_RECORD_STRIDE
    return int.from_bytes(image[at:at + 2], "big", signed=True)


def tracks(image):
    """Every track the sweep captures: 36 rooms, 11 effects, and the bonus tally."""
    for room in range(ROOM_COUNT):
        site, voice, volume, note, priority, what = ROOM_TRIGGER
        yield Track("room%02d" % room, KIND_ROOM,
                    [(Trigger(definition_of(SND.snd_def_level, room), voice, volume, note,
                              priority), None)],
                    None, site, what)

    for fx in range(FX_COUNT):
        site, voice, volume, note, priority, what = FX_TRIGGERS.get(fx, CANDLE_TRIGGER)
        if fx not in FX_TRIGGERS:
            what += " in rooms %s" % ", ".join(str(r) for r in rooms_playing_fx(image, fx))
        yield Track("fx%02d" % fx, KIND_FX,
                    [(Trigger(definition_of(SND.snd_def_fx, fx), voice, volume, note, priority),
                      None)],
                    None, site, what)

    site, voice, volume, priority, what = TALLY_TRIGGER
    definition = definition_of(SND.snd_def_fx, TALLY_FX)
    yield Track("fx%02d_bonus_tally" % TALLY_FX, KIND_TALLY,
                [(Trigger(definition, voice, volume, tally_note(bar), priority),
                  TALLY_TICKS_PER_NOTE) for bar in bonus_bar_values()],
                voice, site, what)


# ---- driving the engine --------------------------------------------------------------------------


def post_init_image():
    """`harness.BASE_IMAGE` with `init_globals` run over it: the image `main` is entered on.

    The definitions this tool dumps do not exist before it — they are in BSS, written one
    `move.w #imm,(a1)+` at a time — so a capture staged on the loaded .PRG would faithfully record
    an engine playing 47 tables of zeroes.

    The instruction count is asserted because this is a COPY of `../recreate/test/conftest.py`'s
    recipe (see INIT_GLOBALS_INSNS): the run has to be the same run that fixture makes, and a stale
    a5 or a moved entry would otherwise produce a plausible image nobody compared with anything.
    """
    image, _writes, regs = emu.run(harness.BASE_IMAGE, INIT_GLOBALS,
                                   regs={"a4": abi.A4_BASE,
                                         "a5": header_value(GLOBALS_H, INIT_GLOBALS_A5_DEFINE)},
                                   max_insns=INIT_GLOBALS_MAX_INSNS)
    if regs["ninsns"] != INIT_GLOBALS_INSNS:
        raise SystemExit("init_globals ran %d instructions, not the %d "
                         "../recreate/test/conftest.py pins (and test_image_model.py asserts): "
                         "this is not the run that builds "
                         "the post-init image every definition below is read out of"
                         % (regs["ninsns"], INIT_GLOBALS_INSNS))
    return bytes(image)


def staged_image(base):
    """`base` with the two things `install_sound_vectors` would establish — see the docstring.

    Returns a bytearray, because a capture pokes its argument list into it and hands it forward from
    one `emu.run` to the next: the voice records live in the image, and that is the engine's state.
    """
    image = bytearray(base)
    _poke_long(image, SND.snd_isr_state + ISR_STATE_CHAIN_VECTOR, emu.SENTINEL)
    _poke_long(image, SND.snd_isr_state + ISR_STATE_VOLUME_SCALE, SND.snd_volume_scale)
    _poke_long(image, SND.snd_isr_state + ISR_STATE_VOICE_TOP,
               SND.snd_voice + (VOICES - 1) * RECORD_STRIDE)
    image[SND.snd_isr_state + ISR_STATE_CONTERM] = image[TOS_CONTERM]
    _poke_long(image, TRAP9_VECTOR, SND.trap9_psg_handler)
    return image


def _poke_long(image, at, value):
    image[at:at + 4] = value.to_bytes(4, "big")


ABI_ARGUMENT_WIDTHS = (2, 4)    # the Alcyon compiler pushes a `short` as a word, a `long` as two


def _stack_args(image, *args):
    """Place `args` where an Alcyon/DRI C routine reads them, in the image the run is about to make.

    `abi.stack_args` returns POKES for `harness.make_image`, which builds an image from
    `BASE_IMAGE`; a capture cannot use that — its image is the engine's own state, carried forward
    from tick to tick — so the same convention is applied in place. Each argument is
    `(width, value)`, the widths being what the CALLER pushes: `sound_play` takes a longword pointer
    and four words (`names.txt`, 0x142bc).

    The two guards are `abi.stack_args`' own, restated with it. They are not defensiveness about
    this file's five call sites: a width the ABI has no push for, or a value that fits neither the
    signed nor the unsigned range, would be TRUNCATED into a legal-looking argument here and the
    engine would then play a different sound perfectly faithfully.
    """
    at = abi.FIRST_ARG
    for width, value in args:
        if width not in ABI_ARGUMENT_WIDTHS:
            raise SystemExit("an Alcyon C argument is a word or a longword, not %d bytes" % width)
        bits = 8 * width
        if not -(1 << (bits - 1)) <= value < (1 << bits):
            raise SystemExit("%d fits neither a signed nor an unsigned %d-byte argument [%d, %d]"
                             % (value, width, -(1 << (bits - 1)), (1 << bits) - 1))
        image[at:at + width] = (value & ((1 << bits) - 1)).to_bytes(width, "big")
        at += width


def _run(image, entry, regs=None, max_insns=200_000):
    """One oracle run over `image`. Returns (final image, its PSG access events).

    `emu.run` raises on anything it cannot model and that is left to propagate: mid-capture it means
    the engine reached a hardware access `notes/sound_engine.md` does not describe, which is a
    finding rather than something to survive.

    The image it returns is already a fresh `bytearray` of its own making, so it is handed straight
    back for the next run to poke and carry forward; copying it again cost a fifth of the sweep.
    """
    image, _writes, _regs = emu.run(image, entry, regs, max_insns=max_insns)
    return image, emu.psg_events()


def _fold(shadow, events):
    """Apply one run's PSG events to the running register shadow.

    Returns (registers written, number of writes, number of reads). The reads are counted rather
    than ignored because they are this capture's one dependency on the audio-capture mode: they are
    `trap9_psg_handler`'s read-back, and the register file that answers them starts at zero.
    """
    writes = [(reg, value) for kind, reg, value in events
              if kind == os_map.OS_PSG_EVENT_WRITE]
    return ym_capture.fold(shadow, writes), len(writes), len(events) - len(writes)


def _ym_frame(shadow):
    """One frame's register file: masked to the bits the chip decodes, with register 13's
    "not written this frame" convention honoured — this engine never writes it at all."""
    frame = bytearray(byte & mask for byte, mask in zip(shadow, YM_REGISTER_MASKS))
    frame[ENVELOPE_SHAPE_REG] = ENVELOPE_SHAPE_UNTOUCHED
    return bytes(frame)


def tone_period(registers, voice):
    """The 12-bit tone period `voice`'s two PSG registers hold in one register file.

    Serves both the running shadow (`capture`, for the base period a retrigger just wrote) and a
    finished frame (`tone_periods`): the two are the same 16 bytes at different moments.
    """
    return (registers[PSG_TONE_FINE_REGS[voice]]
            | (registers[PSG_TONE_COARSE_REGS[voice]] & TONE_PERIOD_COARSE_MASK) << 8)


def _voice_is_idle(image, voice):
    """Is `snd_voice[voice]`'s duration counter 0? That is what "the sound is over" MEANS here: the
    ISR skips such a voice entirely, and its own key-off path is what sets it (§4 step 10)."""
    at = SND.snd_voice + voice * RECORD_STRIDE + RECORD_DURATION
    return int.from_bytes(image[at:at + 2], "big", signed=True) == 0


def capture(base, track):
    """Drive `track` from a freshly staged image and return the per-tick register files.

    The chip is silenced first with the game's OWN reset — `sound_stop_all`, which is the second
    half of `sound_start` (§2) — so a capture starts from a state the program itself establishes
    rather than from whatever the last one left.

    THE MODELLED CHIP IS RESET TOO, and it has to be. `sound_stop_all` zeroes the three volumes and
    nothing else; the mixer it leaves alone, and `trap9_psg_handler` READS THAT MIXER BACK to
    preserve the bits it does not own. Under the audio-capture mode the oracle's register file spans
    runs by contract — which is right within one capture, where it is the chip's own latch surviving
    an interrupt — so without this every track's mixer would depend on which track ran before it,
    and `check_capture_is_reproducible` is what caught that.
    """
    emu.audio_reset()
    image = staged_image(base)
    shadow = bytearray(ym_capture.YM_REGISTERS)
    frames, regs, tick_writes, trigger_periods = [], set(), [], []
    writes, reads = 0, 0

    def account(events):
        """Fold a run's chip traffic into the shadow and the running totals. Returns its writes."""
        nonlocal writes, reads
        written, made, served = _fold(shadow, events)
        regs.update(written)
        writes += made
        reads += served
        return made

    def tick(image):
        """One 200 Hz tick, and the frame it left behind."""
        image, events = _run(image, SND.timer_c_sound_isr, max_insns=TICK_INSN_CAP)
        tick_writes.append(account(events))
        frames.append(_ym_frame(shadow))
        return image

    def result(end):
        return Capture(track, frames, end, regs, writes, reads, tick_writes, trigger_periods)

    image, events = _run(image, SND.sound_stop_all, regs={"a4": abi.A4_BASE})
    account(events)

    for trigger, hold in track.plays:
        image, events = _play(image, trigger)
        account(events)
        # The base period sound_play just wrote, BEFORE any tick let the pitch machine move it —
        # which is the only place a retriggered note's own pitch is visible (check_tally_rises).
        trigger_periods.append(tone_period(shadow, trigger.voice))
        held = 0
        while hold is None or held < hold:
            if len(frames) >= SYNTH_TICK_CAP:
                return result(END_CAPPED)
            image = tick(image)
            held += 1
            if hold is None and _voice_is_idle(image, trigger.voice):
                break

    if track.stop_voice is None:
        return result(END_IDLE)

    # The game's own end: sound_stop_voice writes volume 0 through the gate, and one more tick is
    # what turns that write into a frame (the ISR skips the now-idle voice and adds nothing).
    _stack_args(image, (2, track.stop_voice))
    image, events = _run(image, SND.sound_stop_voice, regs={"a4": abi.A4_BASE})
    account(events)
    tick(image)
    return result(END_STOPPED)


def _play(image, trigger):
    """`sound_play(def, voice, volume, note, priority)`, refusing to continue if the engine did.

    A refusal is `-1` and means the voice's priority beat this trigger's (§7 step 2). It cannot
    happen in this sweep — every track starts from a silenced engine, where all three priorities are
    0 — so it is a broken argument list rather than a case to handle.
    """
    _stack_args(image, (4, trigger.definition), (2, trigger.voice), (2, play_volume(trigger)),
                (2, trigger.note), (2, trigger.priority))
    image, _writes, out = emu.run(image, SND.sound_play, {"a4": abi.A4_BASE},
                                  max_insns=PLAY_INSN_CAP)
    got = out["d0"] & 0xffff
    if got != trigger.voice:
        raise SystemExit("sound_play(%#x, voice %d, volume %d, note %d, priority %d) returned %d, "
                         "not the voice it was asked for: the engine refused the trigger or the "
                         "argument list is wrong"
                         % (trigger.definition, trigger.voice, play_volume(trigger), trigger.note,
                            trigger.priority, got - 0x10000 if got > 0x7fff else got))
    return image, emu.psg_events()


SOUND_ENABLED = None            # read out of the post-init image by check_sound_enabled


def play_volume(trigger):
    """The volume argument the call site really passes: `sound_enabled * k` (§8).

    `sound_enabled` is 1 in the image `init_globals` leaves and 0 only after the player presses ^S,
    which mutes everything — so the sweep captures the game as it starts up, and reads the byte
    rather than assuming it.
    """
    return SOUND_ENABLED * trigger.volume


# ---- what came out -------------------------------------------------------------------------------


def tone_periods(frames, channel):
    """Every distinct 12-bit tone period `channel` was given across `frames`, in order of first
    appearance — the surface a pitch sweep or an LFO wobble shows up on."""
    seen = []
    for frame in frames:
        period = tone_period(frame, channel)
        if period not in seen:
            seen.append(period)
    return seen


# ---- output --------------------------------------------------------------------------------------
# The two containers are `tools/ym_capture.py`'s; what this file supplies is what is Bubble Ghost's
# about them — the three strings, the 200 Hz frame rate and the render.

YM6_LOOP_FRAME = 0            # YM6 has no "does not loop" flag; nothing in this game loops, and the
                              # manifest's `ended` column is what says so
YM6_AUTHOR = "ERE Informatique / Accolade 1988 (in-house 3-voice ADSR+LFO synth, no sequencer)"
TITLE_PREFIX = "Bubble Ghost (ST) - "
COMMENT_PREFIX = "captured from GHOST_RT.PRG by tools/extract_audio.py --synth; "


def render(frames):
    """`frames` through BuggyBoy's YM2149 synth, as a float track on the CHIP's scale.

    `normalise=False` and not each track's own peak: normalising every file separately would make a
    4-tick blip as loud as a 4.7 s room tone and pull a nearly silent track up to full scale, which
    is a gain stage inventing a fact about the machine. On the chip's scale the loudest a mix can be
    is three channels at volume 15, so nothing clips by construction and the .wav levels are the
    levels the game plays at, relative to one another.

    `fps` is the engine's 200 Hz Timer C tick and not the renderer's default 50 Hz VBL; stretched to
    a VBL every one of these sounds would be four times too long, its ADSR four times too slow.

    `retriggers` is left None because no tick writes register 13 — the engine does not use the
    chip's envelope generator at all (§1), which `check_envelope_registers_silent` verifies — so the
    generator reads as long completed, which is what the chip does.
    """
    return ym2149.render(frames, rate=SYNTH_SAMPLE_RATE, normalise=False, fps=SYNTH_TICK_RATE_HZ)


MANIFEST_COLUMNS = ("name", "kind", "definition", "voice", "volume", "note", "priority", "ticks",
                    "seconds", "audible_ticks", "psg_writes", "psg_regs", "peak_dbfs", "ended",
                    "call_site", "what")

MANIFEST_HEADER = """\
# Bubble Ghost (ST) — every sound the PSG synth engine plays, captured from GHOST_RT.PRG by
# projects/bubbleghost/tools/extract_audio.py --synth. One row per track; <name>.ym / <name>.wav
# beside this file. See projects/bubbleghost/notes/sound_engine.md for the engine.
#
# THERE IS NO MUSIC IN THIS GAME. It has no sequencer and no note stream (sound_engine.md §9): the
# 47 definitions below are one-shot voice records, and the only thing that sounds like a melody is
# the `tally` row — game_top_loop retriggering fx8 with a rising note as it counts the bonus down.
#
# kind      fx    = snd_def_fx[0..10], the fixed effects
#           room  = snd_def_level[0..35], one per room, played on voice 0 at room start
#           tally = the bonus glissando: %d retriggers of fx8, note = 100 - bonus_bar/4, then the
#                   game's own sound_stop_voice(2). ITS PACE IS AN ESTIMATE (%d ticks = %d ms per
#                   note): the loop has no Vsync and no timer wait, so nothing in the binary fixes
#                   it.
#
# TWO NUMBERS HERE ARE NOT MEASURED FROM THIS PROGRAM, and they are the only two. The tally's pace
# just above is one. The other is THE 200 Hz TICK ITSELF, which is READ OUT OF TOS rather than out
# of this image: the game installs its handler on MFP channel 5 (Timer C) and never programs that
# timer's divider, so the rate is whatever TOS set it to at boot — 200 Hz. Every `ticks`, `seconds`
# and frame-rate figure below rests on it. Everything else in this file is measured from the running
# code.
# volume    the argument the call site passes: sound_enabled (1 at startup) x the site's own index.
# note      sound_play's `note`. NEGATIVE = a one-shot: the duration counter runs and the sound
#           auto-releases. >= 0 = a MIDI note AND a sustain — the sound plays until the game stops
#           it, which is why the two such rows the game does not stop here end `capped`.
# ticks     200 Hz Timer C ticks, one .ym frame each. seconds = ticks / 200.
# psg_regs  which YM2149 registers the whole capture wrote — the leading sound_stop_all included,
#           which is why registers 8, 9 and 10 (all three channel volumes) appear in every row
#           whatever voice the track uses. Registers 11-13 are the chip's envelope generator and
#           appear in NO row: this engine does not use it (sound_engine.md §1).
# peak_dbfs the .wav's peak on the CHIP's scale (0 dBFS = three channels at volume 15), so the
#           numbers are comparable between files. Rendered at %d Hz, which unlike 44100 is
#           divisible by the 200 Hz tick.
# ended     idle    = the voice's duration counter reached 0 — the sound finished by itself
#           capped  = a SUSTAINED sound (note >= 0) still audible at %d ticks (%d s). Not a limit
#                     of the capture: its duration counter never runs, and the game holds it until
#                     it releases or stops it — so the .wav is 30 s of a sound with no end of its
#                     own, and it is still sounding at the cut (see the tool's own docstring).
#           stopped = the game's own sound_stop_voice ran
# call_site where the game plays it (out/prg_dis.txt); `what` is what the surrounding code is doing.
#
# TWO THINGS THE MODELLED CHIP GETS WRONG, both inaudible and both stated rather than hidden. The
# oracle's register file starts at zero and trap9_psg_handler reads the mixer back to preserve the
# bits it does not own, so (a) the channels this track does not use read as gated ON — their volumes
# are 0, so they are silent — and (b) mixer bits 6/7, the I/O PORT DIRECTION bits TOS owns, read 0
# where a real machine has them set. Neither is part of the audio.
"""


def manifest_row(sound):
    result, level = sound
    track = result.track
    notes = sorted({trigger.note for trigger, _hold in track.plays})
    return "\t".join((
        track.name, track.kind, "%#x" % track.plays[0][0].definition,
        str(track.plays[0][0].voice), str(play_volume(track.plays[0][0])),
        str(notes[0]) if len(notes) == 1 else "%d..%d" % (notes[0], notes[-1]),
        str(track.plays[0][0].priority),
        str(len(result.frames)), "%.2f" % (len(result.frames) / SYNTH_TICK_RATE_HZ),
        str(ym_capture.audible_frames(result.frames)), str(result.writes),
        ",".join(str(reg) for reg in sorted(result.regs)),
        ym_capture.peak_dbfs(level), result.end, "%#x" % track.call_site, track.what,
    ))


def write_assets(out_dir, result):
    """One track's .ym and .wav. Returns the render's peak."""
    stem = os.path.join(out_dir, result.track.name)
    title = TITLE_PREFIX + "%s (%s)" % (result.track.name, result.track.kind)
    comment = COMMENT_PREFIX + "%s; %d ticks at %d Hz; ended: %s" % (
        result.track.what, len(result.frames), SYNTH_TICK_RATE_HZ, result.end)
    ym_capture.write_ym6(stem + ".ym", result.frames, title, YM6_AUTHOR, comment,
                         SYNTH_TICK_RATE_HZ, ym2149.CLOCK, YM6_LOOP_FRAME)
    return ym_capture.write_wav(stem + ".wav", render(result.frames), SYNTH_SAMPLE_RATE)


# ---- the checks the report rests on --------------------------------------------------------------

# fx3 is the blow, and it is the engine's only NOISE-ONLY definition (§8.1): tone off, noise period
# 28, volume index 3. Read out of the image rather than asserted, so a moved table fails here.
BLOW_FX = 3
BLOW_VOICE = 1
# A room tone's pitch LFO has to actually wobble. All 36 have one (§8.2) and the shipped data gives
# them dozens of distinct periods; the bar asks "did the LFO run?", not "is this that capture?".
MIN_ROOM_TONE_PERIODS = 8
ROOM_LFO_CHECK = 0              # room 0 — one of the two constant-volume definitions, so what moves
                                # in its frames is the pitch machine and nothing else
REPRODUCIBILITY_TRACK = "fx04"  # 4 ticks: the cheapest track in the set to capture twice
# §5: sound_play folds a note by octaves until it lands in [24, 108], so only those slots of
# snd_note_period are ever addressed — 24 is C1 and 60 is middle C.
NOTE_TABLE_LOW = 24
NOTES_PER_OCTAVE = 12
# The window `check_capped_tracks_still_sound` asks about. One second is many times the period of
# any volume LFO in this set, so an audible sound cannot dip through the whole of it.
CAPPED_TAIL_TICKS = 1 * SYNTH_TICK_RATE_HZ
# Tracks `check_every_track_is_audible` does not ask about. IT IS EMPTY, and that is the finding:
# all 48 sounds this game plays make a noise. A track added here has to carry the reason it is
# silent ON THE CHIP — a definition whose volume envelope never leaves 0 — because the alternative
# reading of a silent capture is that the sweep broke, which is what the check is for.
AUDIBILITY_EXEMPT = ()


def check_layout_matches_the_reconstruction():
    """This tool's voice-record and ISR-state layout must equal `../recreate/include/sound.h`'s.

    Two readings of one program: the constants at the top of this file are read off the ORIGINAL's
    disassembly (notes/sound_engine.md), and the header states the same layout for the port. They
    have to agree, and a `#define` that is absent counts as a disagreement — it has been renamed,
    and a pin that quietly matches nothing is worse than no pin.

    Everything is reported at once rather than first-match: a layout edit moves several offsets
    together, and a message naming one sends the reader back for the next one.
    """
    defines = header_defines(SOUND_H)
    isr_base = defines.get(ISR_STATE_BASE_DEFINE)
    checked = [(name, mine, define, defines.get(define)) for name, mine, define in SOUND_H_PINS]
    checked += [(name, mine, define, None if isr_base is None or defines.get(define) is None
                 else defines[define] - isr_base)
                for name, mine, define in ISR_STATE_OFFSET_PINS]
    # ...and the block's own base, which the offsets above are measured from: `../names.txt` and the
    # header have to name the same address for those distances to mean anything.
    checked.append(("SND.snd_isr_state", SND.snd_isr_state, ISR_STATE_BASE_DEFINE, isr_base))

    wrong = ["%s is %#x here, %s is %s there" % (name, mine, define,
                                                 "absent" if theirs is None else "%#x" % theirs)
             for name, mine, define, theirs in checked if mine != theirs]
    if wrong:
        raise SystemExit("this tool and %s disagree about the engine's layout: %s. One of the two "
                         "readings of the original is wrong, and a capture staged on the wrong "
                         "offsets records a plausible dump of the wrong bytes"
                         % (os.path.relpath(SOUND_H, PROJECT_DIR), "; ".join(wrong)))


def check_table_sizes():
    """Derive the two definition counts from the table addresses and refuse a disagreement.

    `snd_def_level` is bounded above by `snd_def_fx` and `snd_def_fx` by `object_table` — four
    consecutive per-room tables, each ending exactly where the next begins (§8.2). So the counts are
    arithmetic on three names.txt addresses rather than numbers typed here, and a table that grew or
    moved fails here instead of dumping the next table as a sound.
    """
    for name, lo, hi, expected in (("snd_def_level", SND.snd_def_level, SND.snd_def_fx, ROOM_COUNT),
                                   ("snd_def_fx", SND.snd_def_fx, SND.object_table, FX_COUNT)):
        derived, remainder = divmod(hi - lo, DEF_STRIDE)
        if remainder or derived != expected:
            raise SystemExit("%s runs %#x..%#x, which is %d definitions of %#x bytes plus %d spare "
                             "— notes/sound_engine.md reads it as %d, so either the table moved or "
                             "the stride is wrong" % (name, lo, hi, derived, DEF_STRIDE, remainder,
                                                      expected))


def check_sound_enabled(image):
    """`sound_enabled` must be the 1 `init_globals` sets: it multiplies into every volume (§8).

    Captured at 0 the whole sweep would be 48 silent files, each of them a truthful recording of a
    muted game. Returns the value, which `play_volume` then uses.
    """
    value = int.from_bytes(image[SND.sound_enabled:SND.sound_enabled + 2], "big", signed=True)
    if value != 1:
        raise SystemExit("sound_enabled is %d in the post-init image, not the 1 init_globals sets. "
                         "Every trigger's volume is sound_enabled * k, so this sweep would capture "
                         "a muted game and every file would be silent." % value)
    return value


def check_candle_selectors(image):
    """`room_candle_sfx` must select only snd_def_fx[5..10] or -1, and cover all six (§8.1).

    This is what makes "all 11 effects are reachable" a census rather than a claim, and it is also
    the manifest's provenance for the six that have no direct call site.
    """
    selected = {candle_fx_of(image, room) for room in range(ROOM_COUNT)}
    wanted = set(range(FX_COUNT - CANDLE_FX_FIRST))
    if not selected <= wanted | {NO_CANDLE} or not wanted <= selected:
        raise SystemExit("room_candle_sfx takes the values %s over %d rooms; sound_engine.md reads "
                         "it as %s plus %d for a room with no candle, and every one of those has "
                         "to appear or an effect this file dumps is unreachable"
                         % (sorted(selected), ROOM_COUNT, sorted(wanted), NO_CANDLE))


def check_envelope_registers_silent(captures):
    """No capture may write registers 11-13 — the chip's envelope period and shape.

    It is what lets the render skip the envelope generator (`render`), and notes/sound_engine.md §1
    states it of the whole engine: every volume byte is a plain 0..15 level with bit 4 clear.

    TWO STATEMENTS, not one, and the second is about the FILES. The first is about the capture: no
    run touched an envelope register. The second is about every frame that reaches a .ym and the
    render — register 13 must carry ENVELOPE_SHAPE_UNTOUCHED there — and it is a separate claim
    because `_ym_frame` is what puts that byte in, so a mask or an index that stopped doing so would
    write files whose envelope generator restarts on every frame while this check still passed.
    """
    for result in captures:
        touched = sorted(set(PSG_ENVELOPE_REGS) & result.regs)
        if touched:
            raise SystemExit("%s wrote PSG register(s) %s — the envelope generator, which "
                             "sound_engine.md §1 says this engine never uses and which the render "
                             "treats as long completed" % (result.track.name, touched))
        wrong = [at for at, frame in enumerate(result.frames)
                 if frame[ENVELOPE_SHAPE_REG] != ENVELOPE_SHAPE_UNTOUCHED]
        if wrong:
            raise SystemExit("%s has %d frame(s) whose register %d is not the %#x that means "
                             "\"not written this frame\" (the first is frame %d, holding %#x): a "
                             "player reads that as a shape write and restarts the envelope "
                             "generator"
                             % (result.track.name, len(wrong), ENVELOPE_SHAPE_REG,
                                ENVELOPE_SHAPE_UNTOUCHED, wrong[0],
                                result.frames[wrong[0]][ENVELOPE_SHAPE_REG]))


def check_every_track_is_audible(captures):
    """Every track must make a sound on the chip in at least one of its frames.

    Without it a sweep that captured 48 silent files would pass everything else here: the definition
    counts, the candle census and the reproducibility check all hold of a set of empty tracks, and
    only two of the 48 (the blow and room 0) had a check that looked at what came out at all. The
    bar is one frame rather than a proportion, because a 4-tick blip and a 30 s tone are both in
    this set and any threshold above 1 would be a claim about the sound, not about the capture.
    """
    silent = [result.track.name for result in captures
              if result.track.name not in AUDIBILITY_EXEMPT
              and not ym_capture.audible_frames(result.frames)]
    if silent:
        raise SystemExit("%d of %d tracks are silent on the chip across every one of their frames "
                         "(%s): no gate open over a non-envelope volume anywhere. A sweep that "
                         "records the game muted is a truthful dump of nothing"
                         % (len(silent), len(captures), ", ".join(silent)))


def check_finished_tracks_end_silent(captures):
    """A track that ENDED must end on three volumes of zero — the engine's own key-off.

    `_voice_is_idle` reads the duration counter as `== 0`, which is what the ISR's key-off path
    writes; a counter that stepped PAST zero would satisfy no test here and end the capture on the
    tick it happened to be seen, losing up to 20% of a release tail. This is the surface for that:
    the ISR writes volume 0 as it keys off, so a track that really ran to its end has it in the last
    frame, and one cut early does not.

    Capped tracks are exempt, and that is the whole point of `capped` — fx3 is still blowing at
    volume 7 when the cap cuts it, which `check_capped_tracks_still_sound` is what says.
    """
    for result in captures:
        if result.end == END_CAPPED or not result.frames:
            continue
        last = result.frames[-1]
        levels = [last[ym_capture.PSG_VOLUME_A_REG + voice] for voice in range(VOICES)]
        if any(levels):
            raise SystemExit("%s ended %s but its last frame still holds volumes %s: the engine's "
                             "key-off writes 0 to all three, so this capture stopped before the "
                             "release finished — the end rule saw an idle voice that was not one"
                             % (result.track.name, result.end, levels))


def check_silence_agrees_with_the_render(sounds):
    """A track is silent on the CHIP exactly when its .wav is silent, and vice versa.

    The two claims are made by different machinery — one counts open gates over non-envelope volumes
    in the register stream, the other is the peak of BuggyBoy's synth's output — so this is the one
    place they are made to agree. Ported from `projects/zynaps/tools/extract_audio.py`, where the
    same check earns its keep on a driver with genuinely silent streams.

    The threshold is one 16-bit quantisation step rather than exact zero, because a channel with
    both mixer gates closed holds the DAC at a constant the renderer emits as samples: `render`
    high-passes it away the way the machine's own AC coupling does, which leaves floating-point
    residue rather than literal 0.0. Anything under one step writes an all-zero .wav.
    """
    for result, level in sounds:
        silent_here = not ym_capture.audible_frames(result.frames)
        if silent_here != (level < ym_capture.RENDER_SILENCE_PEAK):
            raise SystemExit("%s is %s by its register stream but its render peaks at %g (silence "
                             "threshold %g): the audibility rule and the synth disagree about the "
                             "same %d frames"
                             % (result.track.name, "silent" if silent_here else "audible", level,
                                ym_capture.RENDER_SILENCE_PEAK, len(result.frames)))


def check_blow_is_noise_only(image, result):
    """fx3 is the blow: noise and nothing else, at the period and volume its definition holds.

    Three independent statements of one sound. The DEFINITION says tone off / noise 28 / volume 3;
    the CAPTURE must have written the noise period and this voice's volume and NEITHER of its two
    tone registers; and the two must agree about the period. A capture that silently played the
    wrong definition passes none of them.
    """
    definition = definition_of(SND.snd_def_fx, BLOW_FX)
    tone = int.from_bytes(image[definition + DEF_TONE_PERIOD:definition + DEF_TONE_PERIOD + 2],
                          "big", signed=True)
    noise = int.from_bytes(image[definition + DEF_NOISE_PERIOD:definition + DEF_NOISE_PERIOD + 2],
                           "big", signed=True)
    if tone >= 0 or noise < 0:
        raise SystemExit("fx%d at %#x has tone period %d and noise period %d; sound_engine.md "
                         "reads it as the blow — tone OFF (negative) and noise ON"
                         % (BLOW_FX, definition, tone, noise))
    tone_regs = {PSG_TONE_FINE_REGS[BLOW_VOICE], PSG_TONE_COARSE_REGS[BLOW_VOICE]}
    wanted = {PSG_NOISE_PERIOD_REG, PSG_MIXER_REG, ym_capture.PSG_VOLUME_A_REG + BLOW_VOICE}
    if result.regs & tone_regs or not wanted <= result.regs:
        raise SystemExit("the blow's capture wrote registers %s: a noise-only sound writes %s and "
                         "neither of voice %d's tone registers %s"
                         % (sorted(result.regs), sorted(wanted), BLOW_VOICE, sorted(tone_regs)))
    if not any(frame[PSG_NOISE_PERIOD_REG] == noise for frame in result.frames):
        raise SystemExit("the blow's capture never wrote its definition's own noise period %d to "
                         "register %d, so the frames are not this definition's"
                         % (noise, PSG_NOISE_PERIOD_REG))
    return noise


def note_period(image, note):
    """`snd_note_period[note]`: the 12-bit PSG period a MIDI note plays at (§5)."""
    at = SND.snd_note_period + note * 2
    return int.from_bytes(image[at:at + 2], "big")


def check_tally_rises(image, result):
    """The bonus glissando must really rise, and its one discontinuity must be the octave fold.

    The note argument rising is arithmetic THIS file does; that the chip was handed rising pitches
    is what the capture is evidence for, and the two are the same only if `sound_play`'s note fold
    and the note table do what §5 says. So the base period each retrigger wrote — before any tick
    let fx8's pitch LFO move it — is checked two ways:

      * over the notes the table holds directly, the periods fall strictly (a falling period IS a
        rising pitch), one per retrigger;
      * the notes BELOW the table's live span are the fold, and are checked against the table entry
        an octave up. This is not a curiosity: at the very top of the bonus the note goes below 24
        and `sound_play` folds it UP an octave, so the game's own glissando starts three notes high
        and drops an octave into the run. NOTE_TABLE_LOW is where that boundary is.

    Returns (all the periods, how many of them were folded).
    """
    notes = [trigger.note for trigger, _hold in result.track.plays]
    periods = result.trigger_periods
    if len(periods) != len(notes):
        raise SystemExit("the bonus tally made %d retriggers but wrote %d base periods: a note "
                         "went to the chip without a pitch" % (len(notes), len(periods)))
    direct = [period for note, period in zip(notes, periods) if note >= NOTE_TABLE_LOW]
    if direct != sorted(set(direct), reverse=True):
        raise SystemExit("the tally's %d unfolded notes gave periods %s: the glissando is "
                         "note = 100 - bonus_bar/4 with bonus_bar FALLING, so its periods must "
                         "fall strictly" % (len(direct), direct))
    folded = [(note, period) for note, period in zip(notes, periods) if note < NOTE_TABLE_LOW]
    for note, period in folded:
        if period != note_period(image, note + NOTES_PER_OCTAVE):
            raise SystemExit("the tally's note %d played period %d; sound_play folds a note below "
                             "%d up by an octave (sound_engine.md §5), so it should have played "
                             "note %d's period %d"
                             % (note, period, NOTE_TABLE_LOW, note + NOTES_PER_OCTAVE,
                                note_period(image, note + NOTES_PER_OCTAVE)))
    return periods, len(folded)


def check_room_theme_wobbles(result):
    """A room tone's pitch LFO has to show up as register 0/1 traffic, or the ISR never ran it."""
    periods = tone_periods(result.frames, result.track.plays[0][0].voice)
    if len(periods) < MIN_ROOM_TONE_PERIODS:
        raise SystemExit("%s used %d distinct tone period(s) over %d ticks; every room definition "
                         "has a pitch LFO (sound_engine.md §8.2), so this capture ticked an engine "
                         "whose pitch machine never ran"
                         % (result.track.name, len(periods), len(result.frames)))
    return periods


def check_capped_tracks_still_sound(captures):
    """A track cut at the cap must still be AUDIBLE there, or the cap hid a sound that was over.

    `capped` claims the game holds this sound indefinitely, and 30 s of a voice whose envelope
    decayed to nothing would be that claim made about silence. The last second is the window because
    a volume LFO folds at its limit every few ticks, so an audible sound dips through zero
    constantly — asking about the final frame alone would fail on the dip.
    """
    for result in captures:
        if result.end != END_CAPPED:
            continue
        voice = result.track.plays[0][0].voice
        tail = result.frames[-CAPPED_TAIL_TICKS:]
        if not any(ym_capture.channel_sounds(frame, voice) for frame in tail):
            raise SystemExit("%s was cut at the %d-tick cap, but voice %d has been silent for the "
                             "last %d ticks: the capture recorded %.0f s of a sound that was over"
                             % (result.track.name, SYNTH_TICK_CAP, voice, CAPPED_TAIL_TICKS,
                                SYNTH_TICK_CAP / SYNTH_TICK_RATE_HZ))


def check_capture_is_reproducible(base, reference):
    """Re-capture one track after the sweep and require the identical frames.

    The point is not that the emulator is deterministic — every track is staged from the same
    post-init image, so the ENGINE's state is restored either way. What a fresh image does not
    restore is the oracle's modelled register file and select latch, which span runs by design under
    the audio-capture mode; those are what this catches.
    """
    again = capture(base, reference.track)
    if again.frames != reference.frames or again.end != reference.end:
        raise SystemExit("%s captured differently the second time (%d frames %s vs %d frames %s): "
                         "chip state leaked between captures"
                         % (reference.track.name, len(again.frames), again.end,
                            len(reference.frames), reference.end))


# ---- report --------------------------------------------------------------------------------------


def kind_tally(captures):
    kinds = [result.track.kind for result in captures]
    return ", ".join("%d %s" % (kinds.count(kind), kind) for kind in KINDS)


def end_tally(captures):
    ends = [result.end for result in captures]
    return ", ".join("%d %s" % (ends.count(reason), reason)
                     for reason in END_REASONS if reason in ends)


def synth_report(sounds, blow_noise, tally_periods, folded_notes, room_periods, out_dir):
    captures = [result for result, _level in sounds]
    ticks = sum(len(result.frames) for result in captures)
    writes = sum(result.writes for result in captures)
    reads = sum(result.reads for result in captures)
    longest = max(captures, key=lambda result: len(result.frames))
    loudest = max(sounds, key=lambda sound: sound[1])
    per_tick = sorted(count for result in captures for count in result.tick_writes)
    return "\n".join((
        "synth:  %d tracks captured — %s" % (len(captures), kind_tally(captures)),
        "ends:   %s (cap %d ticks = %d s)"
        % (end_tally(captures), SYNTH_TICK_CAP, SYNTH_TICK_CAP // SYNTH_TICK_RATE_HZ),
        "length: %d ticks = %.1f s at %d Hz; longest is %s at %.1f s"
        % (ticks, ticks / SYNTH_TICK_RATE_HZ, SYNTH_TICK_RATE_HZ, longest.track.name,
           len(longest.frames) / SYNTH_TICK_RATE_HZ),
        "chip:   %d register writes (%d..%d per tick, %.1f mean) and %d read-backs, all of them "
        "trap9_psg_handler's; registers %s never written — the envelope generator is unused"
        % (writes, per_tick[0], per_tick[-1], sum(per_tick) / len(per_tick), reads,
           ",".join(str(reg) for reg in PSG_ENVELOPE_REGS)),
        "levels: rendered at %d Hz on the chip's scale (0 dBFS = 3 channels at volume 15), so no "
        "file clips and the .wav levels are comparable; loudest is %s at %s dBFS"
        % (SYNTH_SAMPLE_RATE, loudest[0].track.name, ym_capture.peak_dbfs(loudest[1])),
        "checks: the record layout equals recreate/include/sound.h's; both definition counts "
        "derived from the table addresses; sound_enabled = 1; room_candle_sfx covers fx%d..fx%d; "
        "all %d tracks audible and their renders agree; every ended track keys off at volume 0 and "
        "every capped one is still audible at the cut; the blow is noise-only at period %d; the "
        "tally's %d notes rise strictly (its first %d fold up an octave — see the manifest); room "
        "%d's pitch LFO gives %d periods; %s reproducible after the sweep"
        % (CANDLE_FX_FIRST, FX_COUNT - 1, len(captures), blow_noise, len(tally_periods),
           folded_notes, ROOM_LFO_CHECK, len(room_periods), REPRODUCIBILITY_TRACK),
        "",
        "wrote to %s" % out_dir,
    ))


def extract_synth(out_dir):
    """Part 2: run the original engine over the 47 definitions and the tally. Returns the report."""
    if KIT_ERROR is not None:
        raise SystemExit(KIT_ERROR_HELP % KIT_ERROR)
    os.makedirs(out_dir, exist_ok=True)
    check_layout_matches_the_reconstruction()
    check_table_sizes()

    global SOUND_ENABLED
    base = post_init_image()
    SOUND_ENABLED = check_sound_enabled(base)
    check_candle_selectors(base)
    by_name = {track.name: track for track in tracks(base)}

    with emu.audio_capturing():
        captures = [capture(base, track) for track in by_name.values()]
        # Everything that can be judged off the register stream is judged BEFORE a byte is written,
        # so a failing run does not leave a directory of files that look like a finished dump.
        found = {result.track.name: result for result in captures}
        check_envelope_registers_silent(captures)
        check_every_track_is_audible(captures)
        check_finished_tracks_end_silent(captures)
        check_capped_tracks_still_sound(captures)
        blow_noise = check_blow_is_noise_only(base, found["fx%02d" % BLOW_FX])
        tally_periods, folded_notes = check_tally_rises(
            base, found["fx%02d_bonus_tally" % TALLY_FX])
        room_periods = check_room_theme_wobbles(found["room%02d" % ROOM_LFO_CHECK])
        check_capture_is_reproducible(base, found[REPRODUCIBILITY_TRACK])

        sounds = [(result, write_assets(out_dir, result)) for result in captures]
        # ...and the one check that needs a render: the manifest is still unwritten, so a
        # disagreement here still leaves the directory unmarked.
        check_silence_agrees_with_the_render(sounds)

    # ...and the manifest last of all, so its presence marks the directory complete.
    header = MANIFEST_HEADER % (len(by_name["fx%02d_bonus_tally" % TALLY_FX].plays),
                                TALLY_TICKS_PER_NOTE,
                                1000 * TALLY_TICKS_PER_NOTE // SYNTH_TICK_RATE_HZ,
                                SYNTH_SAMPLE_RATE, SYNTH_TICK_CAP,
                                SYNTH_TICK_CAP // SYNTH_TICK_RATE_HZ)
    with open(os.path.join(out_dir, "manifest.tsv"), "w") as handle:
        handle.write(header + "\t".join(MANIFEST_COLUMNS) + "\n"
                     + "\n".join(manifest_row(sound) for sound in sounds) + "\n")
    return synth_report(sounds, blow_noise, tally_periods, folded_notes, room_periods,
                        out_dir)


# =================================================================================================


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # MUTUALLY EXCLUSIVE, because the two halves are alternatives and not filters: `--voi --synth`
    # used to satisfy both `not args.synth` and `not args.voi` as false, run neither half, print an
    # empty line and exit 0 — a silent no-op wearing the exit status of a finished dump.
    half = parser.add_mutually_exclusive_group()
    half.add_argument("--voi", action="store_true",
                      help="only the digitised speech in GHOST.VOI (default: %s)" % DEFAULT_VOI_DIR)
    half.add_argument("--synth", action="store_true",
                      help="only the PSG synth engine's 47 sounds and the bonus tally "
                           "(default: %s)" % DEFAULT_SYNTH_DIR)
    parser.add_argument("out_dir", nargs="?", metavar="OUT_DIR",
                        help="override the default for whichever half was named; it takes one of "
                             "--voi/--synth, because the two halves have separate directories")
    args = parser.parse_args(argv[1:])
    if args.out_dir and not (args.voi or args.synth):
        parser.error("OUT_DIR names one output directory, so it needs one of --voi/--synth "
                     "(with neither, both halves run into %s and %s)"
                     % (DEFAULT_VOI_DIR, DEFAULT_SYNTH_DIR))

    lines = []
    if not args.synth:
        lines.append(extract_voi(args.out_dir or DEFAULT_VOI_DIR))
    if not args.voi:
        lines.append(extract_synth(args.out_dir or DEFAULT_SYNTH_DIR))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
