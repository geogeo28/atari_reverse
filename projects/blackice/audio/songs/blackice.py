#!/usr/bin/env python3
"""blackice.py — the BLACK ICE score, compiled into the YM replayer's format.

    python3 songs/blackice.py        -> blackice_song.c/.h, blackice_sfx_ids.h, out/blackice_*

FIVE SONGS COME OUT OF THIS FILE, and which one is playing is the game's whole state machine:

    blackice_title    the ~30 s attract loop — colder and sparser than the score
    blackice_score    the in-game loop, ONE blob played at FOUR speeds (see below)
    blackice_death    a 2.9 s sting; the game calls ym_music_stop() when it ends
    blackice_clear    a 3.8 s sting, same rule
    blackice_exfil    the 100% trace pulse: no melody, just the clock (DESIGN.md §16)

THE FOUR TRACE BANDS ARE ONE SONG AT FOUR SPEEDS. DESIGN.md §16 says "the tempo *is* the trace
meter" and "tempo change is a driver counter, not a new module", so four separate blobs would be
four copies of the same 1.5 KB of patterns to express a single 16-bit field. The driver reads its
tempo out of the blob header once, in ym_music_init, and holds it in `song_speed`; the game changes
band with `ym_music_set_speed(BAND_SPEEDS[band])` and the loop keeps playing from where it was.

THE TEMPO LATTICE, and why the BPMs are not the design's round numbers. A row lasts a whole number
of 50 Hz frames, so with two rows to the beat only BPM = 1500 / speed is reachable:

    band          trace     speed   BPM       DESIGN.md §16 asks for
    0 COLD        0-25%      11     136.4     140
    1 NOTICED    25-50%      10     150.0     152
    2 HUNTED     50-75%       9     166.7     168
    3 BURNED     75-100%      8     187.5     184
    - EXFIL        100%       7     214.3     200 ("one pulse, no melody")

The largest deviation is band 0's 2.6%; every other one is under 2%. Nothing between speed 11 and
10 exists to pick instead, and the escalation — the thing the meter is for — is +10%, +11%, +12.5%
per step, which is steeper than the design's own +8.6%, +10.5%, +9.5%.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
AUDIO_DIR = HERE.parent
sys.path.insert(0, str(AUDIO_DIR))

import mk_song                                                          # noqa: E402  (after path)
from mk_song import (NOTE_INDEX_BY_NAME, SEMITONES_PER_OCTAVE, envelope,  # noqa: E402  (after path)
                     note_name, spread)

OUT = AUDIO_DIR / "out"

# ------------------------------------------------------------------------------- the tempo map --

# Frames per row at 50 Hz, one per trace band; the game hands the driver BAND_SPEEDS[band].
BAND_SPEEDS = [11, 10, 9, 8]
EXFIL_SPEED = 7
TITLE_SPEED = 12                      # slower than any band: the attract loop is the cold one
STING_SPEED = 6                       # both stings, so their row grid is the same one

VBL_HZ = 50.0
ROWS_PER_BEAT = 2                     # a row is an eighth note, so a bar is ROWS_PER_BAR rows
ROWS_PER_BAR = 8
SCORE_ROWS = 32                       # four bars to a pattern
STING_ROWS = 24
EXFIL_ROWS = 16

# The whole authored set, checked against the brief's ceiling by main().
SONG_BANK_BUDGET_BYTES = 8192

# -------------------------------------------------------------------------------- the material --

# A PHRYGIAN — A, Bb, C, D, E, F, G. The lowered second (Bb against A) is the one interval in the
# scale that will not resolve, and it is the ICE: every magenta section leans on it, every cyan
# one avoids it. The root sits at A-2 (110 Hz) rather than an octave down so the bass has a
# fundamental a spectrum can actually find — below ~66 Hz a 180 ms window cannot measure pitch.
ROOT = "A-2"
ICE_ROOT = "A#2"                      # the flat second: the ICE's own root

# The three chord shapes the arpeggio channel plays, as semitone offsets stepped one per frame.
TRIAD_MINOR = [0, 3, 7]               # cyan: infrastructure, stable
TRIAD_ICE = [0, 1, 7]                 # magenta: root, flat second, fifth — an alarm, not a chord
TRIAD_LIFT = [0, 4, 7]                # major, used once, by the level-clear sting

# The arpeggio channel plays the SAME bar roots as the bass, two octaves up. Sharing the roots is
# what keeps the two lines spelling one chord; the shift is what stops the chord voice landing on
# top of the bass, where a 110 Hz triad is a second bass line and not a harmony.
ARP_OCTAVE_SHIFT = 2 * SEMITONES_PER_OCTAVE


def pulse_envelope(peak, on_frames, off_frames, repeats):
    """A volume table that beats: `on_frames` of a decaying tone, then silence, `repeats` times.

    The decay ENDS at zero, so the last of the `on_frames` is already silent and the audible duty
    is (on_frames - 1) : (off_frames + 1). That is the shape wanted here — a hard edge back to
    silence — and it is written down because the call site reads like 6-on/3-off and is not.

    This is how a one-shot YM macro gets a siren or an alarm out of a driver that has one envelope
    per note — the pulsing is IN the table, so nothing in the tick has to know about it."""
    cycle = envelope(peak, on_frames) + [0] * off_frames
    return cycle * repeats


def ramp_envelope(peak, rise_frames, total_frames):
    """Silence-to-peak-to-silence over exactly `total_frames`: the shape a charging or opening
    sound wants, where the demo's straight decay would announce the event before it happened.

    The peak lands twice, at the end of the rise and the start of the fall, which is a one-frame
    hold at full level and is why the rise reads as arriving rather than passing through."""
    if not 0 < rise_frames < total_frames:
        raise SystemExit(f"a {rise_frames}-frame rise does not fit in {total_frames} frames")
    rise = [round(peak * step / (rise_frames - 1)) for step in range(rise_frames)]
    return rise + envelope(peak, total_frames - rise_frames)


def transpose(name, semitones):
    return note_name(NOTE_INDEX_BY_NAME[name] + semitones)


def octave_up(name):
    return transpose(name, SEMITONES_PER_OCTAVE)


# ------------------------------------------------------------------------------- the channels ---

def with_instrument(events, instrument):
    """Attach `instrument` to the first token only — every later note on the channel inherits it,
    which is what keeps a pattern from re-stating the same instrument thirty times."""
    out = {}
    for position, row in enumerate(sorted(events)):
        out[row] = f"{events[row]}:{instrument}" if position == 0 else events[row]
    return out


def bass_line(roots, rows=SCORE_ROWS, instrument="bass", pulse_rows=(0, 2, 4, 6), lift_row=7):
    """The pumping root: `roots` is one note name per bar, struck on `pulse_rows` of that bar with
    its octave answering on `lift_row`. Cold and mechanical on purpose — this line is the clock."""
    events = {}
    for bar, root in enumerate(roots):
        base = bar * ROWS_PER_BAR
        for row in pulse_rows:
            events[base + row] = root
        if lift_row is not None:
            events[base + lift_row] = octave_up(root)
    return spread(with_instrument(events, instrument), rows)


def melody_line(phrase, instrument, rows=SCORE_ROWS):
    """`phrase` is {row: note name}, played on one instrument."""
    return spread(with_instrument(phrase, instrument), rows)


def arpeggio_line(roots, instrument, rows=SCORE_ROWS, rows_per_chord=ROWS_PER_BAR):
    """One struck note per chord, in the arpeggio register: the instrument's own table turns each
    into a triad."""
    events = {chord * rows_per_chord: transpose(root, ARP_OCTAVE_SHIFT)
              for chord, root in enumerate(roots)}
    return spread(with_instrument(events, instrument), rows)


# THE PERCUSSION GRID IS UNBROKEN, and that is a measurement decision as much as a musical one.
# Every row of every score pattern carries a hit — a kick, a snare, or the hat that fills the rest
# — so the recording's amplitude envelope has a spectral line at exactly the row rate. That line is
# how verify.py measures which BAND is playing without being told; a pattern that dropped its hats
# would leave the tempo check with nothing to find.
KICK_NOTE = "A-1"
SNARE_NOTE = "D-4"
HAT_NOTE = "C-2"


def drum_line(kick_rows, snare_rows, rows=SCORE_ROWS):
    """One hit per row: a kick, a snare, or the hat that fills everything else.

    The instrument is re-stated only where it CHANGES — the format's "instrument 0 = keep last" is
    per channel, so a run of hats costs one instrument byte and not thirty-two."""
    tokens = {}
    last = None
    for row in range(rows):
        if row in kick_rows:
            note, instrument = KICK_NOTE, "kick"
        elif row in snare_rows:
            note, instrument = SNARE_NOTE, "snare"
        else:
            note, instrument = HAT_NOTE, "hat"
        tokens[row] = note if instrument == last else f"{note}:{instrument}"
        last = instrument
    return spread(tokens, rows)


SILENT_SCORE = spread({}, SCORE_ROWS)

DOWNBEATS = [0, 8, 16, 24]
BACKBEATS = [4, 12, 20, 28]
DRIVING_KICKS = [0, 6, 8, 14, 16, 22, 24, 30]
HAMMER_KICKS = list(range(0, SCORE_ROWS, 2))

# --------------------------------------------------------------------------- the score's parts --

SCORE_INSTRUMENTS = {
    # Dry and short-tailed: the bass has to read as a pulse, not a pad.
    "bass": {"tone": True, "volume": [15, 14, 13, 12, 11, 11, 10, 10, 9], "volume_loop": 8},
    # Cyan infrastructure — a clean minor triad, one note per frame.
    "arp": {"tone": True, "volume": [13, 12, 12, 11, 11, 10], "volume_loop": 4,
            "arpeggio": TRIAD_MINOR},
    # Magenta ICE — the same machinery with the flat second in it.
    "ice": {"tone": True, "volume": [14, 13, 12, 12, 11, 11], "volume_loop": 4,
            "arpeggio": TRIAD_ICE},
    # The one voice with any warmth, and the vibrato is what keeps a held square from reading as a
    # test tone.
    "lead": {"tone": True, "volume": [9, 12, 15, 15, 14, 13, 13, 12], "volume_loop": 6,
             "vibrato_depth": 4, "vibrato_speed": 16},
    "kick": {"tone": True, "noise": True, "noise_period": 15, "pitch_slide": 110,
             "volume": envelope(15, 9)},
    "snare": {"tone": False, "noise": True, "noise_period": 5, "volume": envelope(14, 8)},
    "hat": {"tone": False, "noise": True, "noise_period": 1, "volume": [8, 4, 1]},
}

SCORE_PATTERNS = {
    # BOOT: the machine coming up. Bass and the grid, nothing else.
    "boot": [bass_line([ROOT] * 4, pulse_rows=(0, 4), lift_row=None), SILENT_SCORE,
             drum_line([], [])],
    # The triad arrives, a bar to a chord.
    "boot2": [bass_line([ROOT, ROOT, ROOT, "G-2"]),
              arpeggio_line([ROOT, "G-2"], "arp", rows_per_chord=2 * ROWS_PER_BAR),
              drum_line(DOWNBEATS, [])],
    # RIFF A: the main statement — root, root, down a major third, back up a step.
    "riff_a": [bass_line([ROOT, ROOT, "F-2", "G-2"]),
               melody_line({0: "A-4", 6: "C-5", 8: "A-4", 12: "G-4", 16: "F-4", 20: "G-4",
                            24: "A-4", 30: "G-4"}, "lead"),
               drum_line(DRIVING_KICKS, BACKBEATS)],
    # RIFF B: the answer, walking the Phrygian tetrachord down to the fifth.
    "riff_b": [bass_line([ROOT, "G-2", "F-2", "E-2"]),
               melody_line({0: "C-5", 4: "A#4", 8: "A-4", 12: "G-4", 16: "F-4", 24: "E-4",
                            28: "F-4"}, "lead"),
               drum_line(DRIVING_KICKS, BACKBEATS)],
    # ICE A: the flat second takes the bass and the chord goes dissonant.
    "ice_a": [bass_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT]),
              arpeggio_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT], "ice"),
              drum_line(DOWNBEATS + BACKBEATS, [])],
    # ICE B: it climbs into the flat second instead of sitting on it.
    "ice_b": [bass_line(["F-2", "G-2", ICE_ROOT, ROOT]),
              arpeggio_line(["F-2", "G-2", ICE_ROOT, ROOT], "ice"),
              drum_line(DRIVING_KICKS, BACKBEATS)],
    # DROP: the melody thins to two long notes and the bass to one strike a bar. The grid does not
    # thin at all — this is the section that says the clock is still running.
    "drop": [bass_line([ROOT, ROOT, "F-2", "F-2"], pulse_rows=(0,), lift_row=None),
             melody_line({0: "A-4", 16: "F-4"}, "lead"),
             drum_line(DOWNBEATS, [])],
    # HAMMER: the loop's peak. Bass on every row, the ICE chord over it.
    "hammer": [bass_line([ROOT, ICE_ROOT, ROOT, "G-2"],
                         pulse_rows=(0, 1, 2, 3, 4, 5, 6), lift_row=7),
               arpeggio_line([ROOT, ICE_ROOT, ROOT, "G-2"], "ice"),
               drum_line(HAMMER_KICKS, [])],
}

# 12 patterns: 84.5 s at band 0's speed 11, 61.4 s at band 3's speed 8 — inside the brief's 60-90 s
# at every tempo the meter can ask for.
SCORE_ORDER = ["boot", "boot2", "riff_a", "riff_b", "ice_a", "riff_a",
               "riff_b", "ice_b", "drop", "riff_a", "hammer", "riff_b"]

# --------------------------------------------------------------------- the SFX macros (YM path) --

# DESIGN.md §16's cue table, and THE ONLY PLACE IT IS WRITTEN DOWN. songs/blackice_sfx.py imports
# this list to decide how long each DMA sample is and what priority it carries, so the two paths
# cannot disagree about the catalogue — which is what "index N is the same event on both paths"
# has to mean if it is going to be true rather than merely intended.
SFX_CATALOGUE = [
    {"name": "buster_shot", "seconds": 0.10, "priority": 1},
    {"name": "spike_shot", "seconds": 0.35, "priority": 2},
    {"name": "watchdog_snarl", "seconds": 0.30, "priority": 1},
    {"name": "sentry_charge", "seconds": 0.45, "priority": 2},
    {"name": "gate_open", "seconds": 0.55, "priority": 2},
    {"name": "token_grab", "seconds": 0.25, "priority": 2},
    {"name": "trace_alarm", "seconds": 0.90, "priority": 3},
    {"name": "player_hit", "seconds": 0.30, "priority": 3},
    {"name": "enemy_dissolve", "seconds": 0.40, "priority": 2},
    {"name": "exfil_siren", "seconds": 1.20, "priority": 3},
]
SFX_SECONDS = {entry["name"]: entry["seconds"] for entry in SFX_CATALOGUE}

# How long the two swelling macros spend climbing, of their total length: the rise IS the tell for
# a charge and for a gate, so it is named rather than buried in the call.
CHARGE_RISE_FRAMES = 15
GATE_RISE_FRAMES = 10


# The YM stand-in for each DMA sample, for a plain ST and for the YM-only first playable. The
# volume table's length IS the sound's length (a non-looping table releases the channel when it
# runs out), so each one is the catalogue's length in 50 Hz frames.
def sting_frames(name):
    """`name`'s length in whole 50 Hz frames. Half-cases round UP — Python's round() sends them to
    the nearest EVEN integer, which splits 0.35 s and 0.45 s in opposite directions."""
    return max(int(SFX_SECONDS[name] * VBL_HZ + 0.5), 1)


SFX_INSTRUMENTS = {
    # A 2-frame noise burst with a tone under it — DESIGN.md §16's own YM form for the shot.
    "ym_buster": {"tone": True, "noise": True, "noise_period": 1, "pitch_slide": 140,
                  "volume": envelope(15, sting_frames("buster_shot"))},
    # The ICE-piercing round: a hard metallic stack, falling.
    "ym_spike": {"tone": True, "noise": True, "noise_period": 4, "pitch_slide": 45,
                 "arpeggio": [0, 7, 12], "volume": envelope(15, sting_frames("spike_shot"))},
    # The descending square sweep §16 asks for, with a growl on it.
    "ym_snarl": {"tone": True, "noise": True, "noise_period": 13, "pitch_slide": 60,
                 "vibrato_depth": 9, "vibrato_speed": 26,
                 "volume": envelope(14, sting_frames("watchdog_snarl"))},
    # Charging: pitch RISING (a negative slide shortens the period) under a swelling envelope.
    "ym_charge": {"tone": True, "pitch_slide": -14, "vibrato_depth": 3, "vibrato_speed": 30,
                  "volume": ramp_envelope(15, CHARGE_RISE_FRAMES, sting_frames("sentry_charge"))},
    # The rising sweep §16 asks for the gate, with the servo's noise in it.
    "ym_gate": {"tone": True, "noise": True, "noise_period": 19, "pitch_slide": -9,
                "volume": ramp_envelope(14, GATE_RISE_FRAMES, sting_frames("gate_open"))},
    # The two-note arpeggio §16 asks for the pickup, widened to a shimmer.
    "ym_token": {"tone": True, "arpeggio": [0, 7, 12, 19],
                 "volume": envelope(15, sting_frames("token_grab"))},
    # The alarm: a two-tone pulse, which is the table's shape and not the driver's problem.
    "ym_alarm": {"tone": True, "arpeggio": [0, 0, 0, 5, 5, 5],
                 "volume": pulse_envelope(15, 6, 3, sting_frames("trace_alarm") // 9)},
    # The player's own damage, which must not be mistakable for an enemy's: rough and falling fast.
    "ym_hit": {"tone": True, "noise": True, "noise_period": 6, "pitch_slide": 85,
               "volume": envelope(15, sting_frames("player_hit"))},
    # ICE coming apart — the arpeggio falls away under a long decay.
    "ym_dissolve": {"tone": True, "noise": True, "noise_period": 9, "pitch_slide": 35,
                    "arpeggio": [0, -5, -12], "volume": envelope(15, sting_frames("enemy_dissolve"))},
    # A real wail: deep vibrato at about two cycles across the sound (the phase accumulator steps
    # `speed` per frame and wraps every 256, so 256 / 8 = 32 frames a cycle).
    "ym_siren": {"tone": True, "vibrato_depth": 46, "vibrato_speed": 8,
                 "volume": pulse_envelope(15, 12, 3, sting_frames("exfil_siren") // 15)},
}

# The instrument and the pitch each cue's YM macro plays. The NAME, the ORDER and the PRIORITY
# come from SFX_CATALOGUE above and are not restated here.
YM_MACRO_VOICE = {
    "buster_shot": ("ym_buster", "C-5"),
    "spike_shot": ("ym_spike", "A-5"),
    "watchdog_snarl": ("ym_snarl", "A-3"),
    "sentry_charge": ("ym_charge", "D-4"),
    "gate_open": ("ym_gate", "A-2"),
    "token_grab": ("ym_token", "E-5"),
    "trace_alarm": ("ym_alarm", "A-5"),
    "player_hit": ("ym_hit", "F-4"),
    "enemy_dissolve": ("ym_dissolve", "A-4"),
    "exfil_siren": ("ym_siren", "A-4"),
}

SFX_MACROS = [{"name": entry["name"], "priority": entry["priority"],
               "instrument": YM_MACRO_VOICE[entry["name"]][0],
               "note": YM_MACRO_VOICE[entry["name"]][1]} for entry in SFX_CATALOGUE]

# --------------------------------------------------------------------------- the title theme ----

# Colder and sparser: a drone, one slow line over it, and a tick instead of a kit. Notes are held
# for four rows (0.96 s at TITLE_SPEED) — long enough that a spectrum can measure every one of
# them, which is what makes this the window verify.py checks pitch in.
TITLE_ROWS = 32
TITLE_INSTRUMENTS = {
    "drone": {"tone": True, "volume": [11, 12, 12, 11, 11, 10, 10, 9], "volume_loop": 7},
    "cold": {"tone": True, "volume": [6, 9, 11, 12, 12, 11, 11, 10], "volume_loop": 6,
             "vibrato_depth": 3, "vibrato_speed": 11},
    "tick": {"tone": False, "noise": True, "noise_period": 3, "volume": [7, 3, 1]},
}

TITLE_BASS_ROWS = (0, 4)
TITLE_TICK_ROWS = range(0, TITLE_ROWS, 4)


TITLE_TICKS = {row: "C-2" for row in TITLE_TICK_ROWS}

TITLE_PATTERNS = {
    "cold_a": [bass_line([ROOT, ROOT, "F-2", "F-2"], rows=TITLE_ROWS, instrument="drone",
                         pulse_rows=TITLE_BASS_ROWS, lift_row=None),
               melody_line({0: "A-4", 4: "E-4", 8: "F-4", 12: "E-4", 16: "D-4", 20: "C-4",
                            24: "A-3", 28: "C-4"}, "cold", rows=TITLE_ROWS),
               melody_line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
    "cold_b": [bass_line(["G-2", "G-2", ICE_ROOT, ICE_ROOT], rows=TITLE_ROWS, instrument="drone",
                         pulse_rows=TITLE_BASS_ROWS, lift_row=None),
               melody_line({0: "G-4", 4: "F-4", 8: "E-4", 12: "F-4", 16: "A#4", 20: "A-4",
                            24: "G-4", 28: "F-4"}, "cold", rows=TITLE_ROWS),
               melody_line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
    # The one place the title lets the flat second sit exposed: the ICE, before the game starts.
    "cold_c": [bass_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT], rows=TITLE_ROWS, instrument="drone",
                         pulse_rows=TITLE_BASS_ROWS, lift_row=None),
               melody_line({0: "A#4", 8: "A-4", 16: "F-4", 24: "E-4"}, "cold", rows=TITLE_ROWS),
               melody_line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
}

# 4 x 32 rows x 12 frames = 1536 frames = 30.7 s.
TITLE_ORDER = ["cold_a", "cold_b", "cold_a", "cold_c"]

# ------------------------------------------------------------------------------- the stings -----

STING_INSTRUMENTS = {
    "fall": {"tone": True, "pitch_slide": 26, "volume": [15, 15, 14, 13, 12, 12, 11, 10, 9],
             "volume_loop": 8},
    "crash": {"tone": False, "noise": True, "noise_period": 8, "volume": envelope(15, 14)},
    "rise": {"tone": True, "arpeggio": TRIAD_LIFT, "volume": [12, 14, 15, 15, 14, 13, 12, 11],
             "volume_loop": 6},
    "ping": {"tone": True, "arpeggio": [0, 12], "volume": envelope(15, 10)},
}

# DEATH — the trace closes: the bass falls a tritone, the chord goes to the flat second, a crash.
# 24 rows x 6 frames = 2.88 s. It LOOPS, like every song in this format; the game is expected to
# call ym_music_stop() when the sting's length has elapsed (see songs/README.md).
DEATH_PATTERNS = {
    "death": [spread(with_instrument({0: ROOT, 8: "D#2", 16: "A#1"}, "fall"), STING_ROWS),
              spread(with_instrument({0: "A-4", 8: "D#4", 16: "A#3"}, "fall"), STING_ROWS),
              spread(with_instrument({0: "C-2", 8: "C-2", 16: "C-2", 20: "C-2"}, "crash"),
                     STING_ROWS)],
}

# CLEAR — the one major chord in the whole score, and the only time the ICE colour is absent.
# 32 rows x 6 frames = 3.84 s.
CLEAR_ROWS = 32
CLEAR_PATTERNS = {
    "clear": [spread(with_instrument({0: "A-2", 8: "C-3", 16: "F-2", 24: "A-2"}, "rise"),
                     CLEAR_ROWS),
              spread(with_instrument({0: "A-4", 8: "C-5", 16: "F-4", 20: "A-4", 24: "C-5"},
                                     "rise"), CLEAR_ROWS),
              spread(with_instrument({0: "A-5", 12: "C-6", 20: "E-6", 28: "A-6"}, "ping"),
                     CLEAR_ROWS)],
}

# ------------------------------------------------------------------------------- the exfil pulse -

# DESIGN.md §16 at 100%: "one 200 BPM pulse, no melody". The melody channel is genuinely empty —
# this is the trace meter with the music taken away from it, and the only thing left is the clock.
# The clock's envelope is exactly EXFIL_SPEED frames long — one whole row — so the noise never
# stops between hits. At 214 BPM a gap would not read as a rest; it would read as the sound
# dropping out, and it is the one thing left in the mix at 100%.
EXFIL_INSTRUMENTS = {
    "pulse": {"tone": True, "volume": envelope(15, EXFIL_SPEED)},
    "clock": {"tone": False, "noise": True, "noise_period": 2,
              "volume": envelope(10, EXFIL_SPEED, floor=2)},
}

# THE CLOCK IS ON CHANNEL B, NOT C, AND THAT IS THE WHOLE POINT OF THIS PATTERN. C is the channel
# ym_music_sfx_play steals, and at 100% the cues firing are the trace alarm and the 1.2 s exfil
# siren — so leaving the clock on C would have the siren silence the only thing this song has.
# Everywhere else the stolen channel is the drums; here the drums ARE the track.
EXFIL_PATTERNS = {
    "pulse": [spread(with_instrument({row: ROOT for row in range(0, EXFIL_ROWS, 2)}, "pulse"),
                     EXFIL_ROWS),
              spread(with_instrument({row: "C-2" for row in range(EXFIL_ROWS)}, "clock"),
                     EXFIL_ROWS),
              spread({}, EXFIL_ROWS)],
}


# ----------------------------------------------------------------------------- the descriptions --

def merged(*mappings):
    out = {}
    for mapping in mappings:
        out.update(mapping)
    return out


def score_description():
    """The in-game loop. It carries the SFX macros because it is the song that is bound while the
    game is firing them — ym_music_sfx_play reads its table out of whatever blob is bound."""
    return {"speed": BAND_SPEEDS[0], "rows": SCORE_ROWS,
            "instruments": merged(SCORE_INSTRUMENTS, SFX_INSTRUMENTS),
            "patterns": SCORE_PATTERNS, "order": SCORE_ORDER, "sfx": SFX_MACROS}


def title_description():
    return {"speed": TITLE_SPEED, "rows": TITLE_ROWS, "instruments": TITLE_INSTRUMENTS,
            "patterns": TITLE_PATTERNS, "order": TITLE_ORDER, "sfx": []}


def death_description():
    return {"speed": STING_SPEED, "rows": STING_ROWS, "instruments": STING_INSTRUMENTS,
            "patterns": DEATH_PATTERNS, "order": ["death"], "sfx": []}


def clear_description():
    return {"speed": STING_SPEED, "rows": CLEAR_ROWS, "instruments": STING_INSTRUMENTS,
            "patterns": CLEAR_PATTERNS, "order": ["clear"], "sfx": []}


def exfil_description():
    """The 100% pulse. It carries the SFX macros too: the exfil siren and the trace alarm are
    exactly the cues that fire while this is the bound song."""
    return {"speed": EXFIL_SPEED, "rows": EXFIL_ROWS,
            "instruments": merged(EXFIL_INSTRUMENTS, SFX_INSTRUMENTS),
            "patterns": EXFIL_PATTERNS, "order": ["pulse"], "sfx": SFX_MACROS}


# The C symbol and the description behind it, in the order the header declares them. The symbol is
# also the stem of the .bin and the meta JSON in out/.
SONGS = [
    ("blackice_title", title_description),
    ("blackice_score", score_description),
    ("blackice_death", death_description),
    ("blackice_clear", clear_description),
    ("blackice_exfil", exfil_description),
]


# ---------------------------------------------------------------------------- the C emitters ----

SONG_HEADER = AUDIO_DIR / "blackice_song.h"
SONG_SOURCE = AUDIO_DIR / "blackice_song.c"
SFX_IDS_HEADER = AUDIO_DIR / "blackice_sfx_ids.h"


def band_speed_table():
    return ", ".join(str(speed) for speed in BAND_SPEEDS)


def bpm(speed):
    return VBL_HZ * 60.0 / (speed * ROWS_PER_BEAT)


def write_song_bank(built):
    """One .c and one .h for all five blobs. `built` is [(symbol, blob, meta), ...]."""
    declarations = "\n".join(
        f"#define {symbol.upper()}_BYTES {len(blob)}\nextern const unsigned char "
        f"{symbol}[{symbol.upper()}_BYTES];\n" for symbol, blob, _ in built)
    roster = "\n".join(f" *   {symbol:<16} {len(blob):5d} B  "
                       f"{meta['frames_total'] / VBL_HZ:6.1f} s at speed {meta['speed']}"
                       for symbol, blob, meta in built)
    bands = "\n".join(f" *   band {index}  speed {speed:2d}  {bpm(speed):5.1f} BPM"
                      for index, speed in enumerate(BAND_SPEEDS))
    SONG_HEADER.write_text(f"""/* blackice_song.h — GENERATED by songs/blackice.py; edit that, not this.
 *
 * The BLACK ICE score, {sum(len(blob) for _, blob, _ in built)} bytes of song data in five blobs:
{roster}
 *
 * blackice_score is played at FOUR tempi, one per trace band; the game switches with
 * ym_music_set_speed(BLACKICE_BAND_SPEED[band]) and the loop plays on from where it was:
{bands}
 */
#ifndef BLACKICE_SONG_H
#define BLACKICE_SONG_H

#define BLACKICE_BAND_COUNT {len(BAND_SPEEDS)}

/* Frames per row at 50 Hz, indexed by trace band (0 = 0-25%, 3 = 75-100%). */
static const unsigned short BLACKICE_BAND_SPEED[BLACKICE_BAND_COUNT] = {{ {band_speed_table()} }};

{declarations}
#endif /* BLACKICE_SONG_H */
""")
    # ONE ALIGNMENT ATTRIBUTE PER ARRAY. In C the attribute binds to the declaration that follows
    # it and to no other, so a single one ahead of five arrays aligns the first and leaves the rest
    # at the byte alignment -fdata-sections gives them. ym_music_init REFUSES an odd blob, so that
    # is a song which silently never plays, on a link the author never sees.
    bodies = "\n\n".join(f"__attribute__((aligned(2)))\n{mk_song.c_array(symbol, blob)}"
                          for symbol, blob, _ in built)
    SONG_SOURCE.write_text(f"""/* blackice_song.c — GENERATED by songs/blackice.py; five songs, """
                           f"""{sum(len(blob) for _, blob, _ in built)} bytes.
 *
 * WORD-ALIGNED because ym_music.h requires it: the driver reads a 16-bit field out of a blob every
 * frame, and a byte array's default alignment is 1. */
#include "blackice_song.h"

{bodies}
""")


def write_sfx_ids():
    """The SFX catalogue as C. Distinct names from sfx_ids.h's (SFX_COUNT, sfx_priority) so a
    translation unit can include both without one silently shadowing the other."""
    ids = "\n".join(f"#define SFX_{entry['name'].upper():<16} {index}"
                    for index, entry in enumerate(SFX_MACROS))
    priorities = ", ".join(str(entry["priority"]) for entry in SFX_MACROS)
    SFX_IDS_HEADER.write_text(f"""/* blackice_sfx_ids.h — GENERATED by songs/blackice.py; edit that, not this.
 *
 * DESIGN.md §16's cue table. Index N is the same event on both paths: blackice_sfx.py packs the
 * DMA samples in this order and blackice.py's SFX_MACROS lists the YM stand-ins in it. */
#ifndef BLACKICE_SFX_IDS_H
#define BLACKICE_SFX_IDS_H

#define BLACKICE_SFX_COUNT {len(SFX_MACROS)}

{ids}

/* Indexed by the ids above. A request of HIGHER OR EQUAL priority preempts the playing one; a
 * strictly lower one is dropped, never queued (DESIGN.md §16). */
static const unsigned char blackice_sfx_priority[BLACKICE_SFX_COUNT] = {{ {priorities} }};

#endif /* BLACKICE_SFX_IDS_H */
""")


def main():
    OUT.mkdir(exist_ok=True)
    built = []
    for symbol, describe in SONGS:
        blob, meta = mk_song.compile_song(describe())
        meta["symbol"] = symbol
        meta["bytes"] = len(blob)
        meta["band_speeds"] = BAND_SPEEDS
        (OUT / f"{symbol}.bin").write_bytes(blob)
        (OUT / f"{symbol}_meta.json").write_text(json.dumps(meta, indent=1))
        built.append((symbol, blob, meta))

    total = sum(len(blob) for _, blob, _ in built)
    if total > SONG_BANK_BUDGET_BYTES:
        raise SystemExit(f"the five songs are {total} bytes, over the "
                         f"{SONG_BANK_BUDGET_BYTES}-byte budget")
    write_song_bank(built)
    write_sfx_ids()

    print(f"blackice songs: {total} bytes total (budget {SONG_BANK_BUDGET_BYTES}), "
          f"{len(SFX_MACROS)} SFX macros")
    for symbol, blob, meta in built:
        print(f"  {symbol:<16} {len(blob):5d} B  {len(meta['order']):2d} in the sequence  "
              f"{meta['frames_total'] / VBL_HZ:6.1f} s at speed {meta['speed']}")
    print("  trace bands: " + ", ".join(f"{index}={speed}f/row ({bpm(speed):.1f} BPM)"
                                        for index, speed in enumerate(BAND_SPEEDS))
          + f", exfil={EXFIL_SPEED}f/row ({bpm(EXFIL_SPEED):.1f} BPM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
