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
SONG_BANK_BUDGET_BYTES = 12288

# -------------------------------------------------------------------------------- the material --

# A PHRYGIAN — A, Bb, C, D, E, F, G. The lowered second (Bb against A) is the one interval in the
# scale that will not resolve, and it is the ICE: every magenta section leans on it, every cyan
# one avoids it. The root sits at A-2 (110 Hz) rather than an octave down so the bass has a
# fundamental a spectrum can actually find — below ~66 Hz a 180 ms window cannot measure pitch.
ROOT = "A-2"
ICE_ROOT = "A#2"                      # the flat second: the ICE's own root

# A Phrygian as pitch classes, and the ONE place the mode is written down. The bass shapes below
# are intervals from a bar's root, and a fixed interval planed onto a moving root does not stay in
# a mode: a fifth above the E bar is B natural, which is the one note that turns A Phrygian into A
# Aeolian — and it lands on an accent, under the slide. So every bass note is snapped back into the
# scale. Ties go DOWNWARD, which is the Phrygian instinct and which is what sends that B to B flat.
PHRYGIAN_PITCH_CLASSES = {NOTE_INDEX_BY_NAME[name] % SEMITONES_PER_OCTAVE
                          for name in ("A-2", "A#2", "C-2", "D-2", "E-2", "F-2", "G-2")}

# The chord shapes the arpeggio channel plays, as semitone offsets stepped ONE PER FRAME. Four
# notes at 50 Hz is a 12.5 Hz cycle — fast enough to hear as a chord rather than as a run, which is
# how one YM voice carries the whole harmony while the other two hold the bass and the kit.
CHORD_MINOR = [0, 3, 7, 12]           # cyan: infrastructure, stable, with its own octave on top
CHORD_ICE = [0, 1, 7, 8]              # magenta: root, flat second, fifth, flat sixth — an alarm
CHORD_SUS = [0, 5, 7, 12]             # the build's chord: hanging on the fourth, refusing to land
CHORD_LIFT = [0, 4, 7, 12]            # major, used once, by the level-clear sting

# THE CHORD VOICE IS PLANED, THE BASS IS NOT. A fixed shape moved onto every root emits notes the
# mode does not hold — CHORD_ICE on G gives G#, D#; CHORD_MINOR on F gives Ab — and that is the
# point of it: the ICE is a machine running one pattern over whatever it is pointed at, and it does
# not care what key the sector is in. The bass is the voice that does care, so its derived
# intervals are snapped back into the scale (in_the_scale, below).

# The arpeggio channel plays the SAME bar roots as the bass, two octaves up. Sharing the roots is
# what keeps the two lines spelling one chord; the shift is what stops the chord voice landing on
# top of the bass, where a 110 Hz triad is a second bass line and not a harmony.
ARP_OCTAVE_SHIFT = 2 * SEMITONES_PER_OCTAVE


def pulse_envelope(peak, on_frames, off_frames, total_frames):
    """A volume table that beats: `on_frames` of a decaying tone then silence, filling `total_frames`.

    The repeat count is DERIVED from the total, so editing the on/off split can never silently
    change how long the cue lasts — the length is the catalogue's, not this function's.

    The decay ENDS at zero, so the last of the `on_frames` is already silent and the audible duty
    is (on_frames - 1) : (off_frames + 1). That is the shape wanted here — a hard edge back to
    silence — and it is written down because the call site reads like 6-on/3-off and is not.

    This is how a one-shot YM macro gets a siren or an alarm out of a driver that has one envelope
    per note — the pulsing is IN the table, so nothing in the tick has to know about it."""
    cycle = envelope(peak, on_frames) + [0] * off_frames
    return cycle * (total_frames // len(cycle))


def ramp_envelope(peak, rise_frames, total_frames):
    """Silence-to-peak-to-silence over exactly `total_frames`: the shape a charging or opening
    sound wants, where the demo's straight decay would announce the event before it happened.

    The peak lands twice, at the end of the rise and the start of the fall, which is a one-frame
    hold at full level and is why the rise reads as arriving rather than passing through."""
    if not 1 < rise_frames < total_frames:
        raise SystemExit(f"a {rise_frames}-frame rise does not fit in {total_frames} frames")
    rise = [round(peak * step / (rise_frames - 1)) for step in range(rise_frames)]
    return rise + envelope(peak, total_frames - rise_frames)


def in_the_scale(name):
    """`name` if A Phrygian holds it, otherwise the nearest note that is, preferring the lower."""
    index = NOTE_INDEX_BY_NAME[name]
    if index % SEMITONES_PER_OCTAVE in PHRYGIAN_PITCH_CLASSES:
        return name
    for step in (-1, 1, -2, 2):
        if (index + step) % SEMITONES_PER_OCTAVE in PHRYGIAN_PITCH_CLASSES:
            return note_name(index + step)
    raise SystemExit(f"no note within two semitones of {name} is in the scale")


def transpose(name, semitones):
    return note_name(NOTE_INDEX_BY_NAME[name] + semitones)


# ------------------------------------------------------------------------------- the channels ---

def channel_string(events, voices, rows):
    """{row: note name} + {row: instrument} -> one channel's token string.

    The instrument is named on the pattern's FIRST note and thereafter only where it CHANGES. It
    has to be named on the first: the format's "instrument 0 = keep last" is per channel and
    survives a pattern boundary, so a pattern that only named its instrument on a change would
    play the previous pattern's voice until the first switch."""
    tokens = {}
    last = None
    for row in sorted(events):
        voice = voices[row]
        tokens[row] = events[row] if voice == last else f"{events[row]}:{voice}"
        last = voice
    return spread(tokens, rows)


def line(events, instrument, rows=SCORE_ROWS):
    """One channel, one instrument, notes where `events` says. The instrument is named on the first
    note and inherited by the rest, which is what keeps a pattern from re-stating it every row."""
    return channel_string(events, {row: instrument for row in events}, rows)


# ------------------------------------------------------------------------------ the bass shapes --

# One entry per row of a bar, as a semitone offset from that bar's root; None leaves the row alone
# and the channel holds. THE OCTAVE JUMP IS THE WHOLE SOUND: a square wave alternating between a
# root and its octave every eighth is what a 1987 bass line is, and it is also the only way one
# YM voice can imply both the bottom of the mix and its own rhythm.
BASS_HOLD = (0, None, None, None, 0, None, None, 12)          # intro and break: two strikes a bar
BASS_DRIVE = (0, 0, 12, 0, 0, 12, 0, 7)                       # the verse groove
BASS_OCTAVE = (0, 12, 0, 12, 0, 12, 0, 12)                    # relentless, for the chorus
BASS_WALK = (0, 12, 0, 7, 0, 12, 3, 7)                        # the turnaround
BASS_ROLL = (0, 12, 0, 12, 0, 12, 7, 12)                      # the drop, with the fifth pushing

# The last row of a bar takes the sliding voice: a short note whose pitch falls away under it. It
# is the only slide in the arrangement and it is what makes a bar END rather than stop.
BARS_PER_PATTERN = SCORE_ROWS // ROWS_PER_BAR
BASS_ACCENT_ROWS = tuple(bar * ROWS_PER_BAR + ROWS_PER_BAR - 1
                         for bar in range(BARS_PER_PATTERN))


def bass_line(roots, shape=BASS_DRIVE, rows=SCORE_ROWS, instrument="bass",
              accent_rows=BASS_ACCENT_ROWS, accent_instrument="bass_drop"):
    """`roots` is one note name per bar; `shape` says what each row of that bar plays."""
    events, voices = {}, {}
    for bar, root in enumerate(roots):
        for step, offset in enumerate(shape):
            if offset is None:
                continue
            row = bar * ROWS_PER_BAR + step
            # A root and its octaves are WRITTEN — the build climbs F, F#, G deliberately, and
            # snapping that would flatten the climb. Everything else is an interval the shape
            # derived, and a derived note has to be one the mode holds.
            note = transpose(root, offset)
            events[row] = note if offset % SEMITONES_PER_OCTAVE == 0 else in_the_scale(note)
            voices[row] = accent_instrument if row in accent_rows else instrument
    return channel_string(events, voices, rows)


def chord_line(roots, instrument, rows=SCORE_ROWS, rows_per_chord=ROWS_PER_BAR):
    """`roots` is one chord per BAR, restruck every `rows_per_chord` rows within it.

    ROOTS ARE PER BAR, LIKE THE BASS'S, and the restrikes are derived — because the two lines have
    to spell one chord, and a roots list indexed by half-bar would run the whole progression twice
    at double speed instead. (It did: measured, 24 of chorus_b's 32 rows had the chord voice on a
    different root from the bass under it.)

    The instrument's own arpeggio table steps the note once a frame, so ONE voice sounds a
    four-note chord. That is the trick the whole harmony rests on — the YM has three channels, two
    are spoken for by the bass and the kit, and a chip-tune gets its chords out of the third by
    playing them one note at a time faster than a listener resolves them."""
    strikes = ROWS_PER_BAR // rows_per_chord
    events = {bar * ROWS_PER_BAR + strike * rows_per_chord: transpose(root, ARP_OCTAVE_SHIFT)
              for bar, root in enumerate(roots) for strike in range(strikes)}
    return channel_string(events, {row: instrument for row in events}, rows)


# ------------------------------------------------------------------- the percussion, both lanes --

# The YM percussion channel's three voices. They are pitched notes like any other — what makes a
# kick a kick is a low tone with a fast pitch drop under a 7-frame decay, and what makes a hat a
# hat is three frames of the noise generator at its shortest period.
KICK_NOTE = "A-1"
SNARE_NOTE = "D-4"
HAT_NOTE = "C-2"

# THE DMA LANE IS ONE VOICE, so a row carries exactly one drum; where two land together the earlier
# name here wins, which is the mixing decision a real kit makes with its own loudness.
DRUM_PRECEDENCE = ("kick", "snare", "clap", "hat")


def percussion_line(kick_rows, snare_rows, rows=SCORE_ROWS, hat_rows=None):
    """Channel C: a hit on EVERY row unless `hat_rows` narrows the fill.

    An unbroken grid is a musical choice — a relentless eighth-note machine pulse — and a
    measurement one: it puts a spectral line in the recording's amplitude envelope at exactly the
    row rate, which is how verify.py reads the trace band back off the audio."""
    fill = range(rows) if hat_rows is None else hat_rows
    events, voices = {}, {}
    for row in range(rows):
        if row in kick_rows:
            events[row], voices[row] = KICK_NOTE, "kick"
        elif row in snare_rows:
            events[row], voices[row] = SNARE_NOTE, "snare"
        elif row in fill:
            events[row], voices[row] = HAT_NOTE, "hat"
    return channel_string(events, voices, rows)


def drum_lane(rows=SCORE_ROWS, **rows_by_name):
    """The fourth track: `kick=[...], snare=[...], hat=[...], clap=[...]` -> one sample name a row.

    It plays through the STE's DMA voice, so it costs no chip channel and does not exist at all on
    a plain ST — which is why channel C above still carries a full kit of its own."""
    unknown = set(rows_by_name) - set(DRUM_PRECEDENCE)
    if unknown:
        raise SystemExit(f"the drum lane has no sample called {sorted(unknown)}; it knows "
                         f"{list(DRUM_PRECEDENCE)}")
    lane = {}
    for name in reversed(DRUM_PRECEDENCE):
        for row in rows_by_name.get(name, ()):
            lane[row] = name
    return spread(lane, rows)


BAR_STARTS = (0, 8, 16, 24)
BACKBEATS = (4, 12, 20, 28)
DRIVE_KICKS = (0, 6, 8, 14, 16, 22, 24, 30)
DOUBLE_KICKS = (0, 3, 6, 8, 11, 14, 16, 19, 22, 24, 27, 30)
# Every other eighth EXCEPT the backbeat, which the clap takes. The DMA is one voice and
# DRUM_PRECEDENCE puts the kick first, so a kick written on row 4 does not layer with the clap
# there — it deletes it, and the drop loses the one accent the section is built around. (It did:
# the drop's lane measured 16 kicks, 16 hats and zero claps.)
DROP_KICKS = tuple(row for row in range(0, SCORE_ROWS, 2) if row not in BACKBEATS)
OFFBEATS = tuple(range(1, SCORE_ROWS, 2))
SNARE_ROLL = tuple(range(24, SCORE_ROWS))
SPARSE_HATS = tuple(range(0, SCORE_ROWS, 4))

# --------------------------------------------------------------------------- the score's parts --

SCORE_INSTRUMENTS = {
    # Hard attack, quick drop to a level it holds: on an eighth-note grid the note is over almost
    # as soon as it starts, and a slow attack would smear the whole bass line into one tone.
    "bass": {"tone": True, "volume": [15, 15, 13, 11, 10, 10, 9], "volume_loop": 5},
    # The bar's last eighth, falling away under itself. A one-shot envelope, so the slide can never
    # accumulate past the note that started it.
    "bass_drop": {"tone": True, "pitch_slide": 26, "volume": envelope(15, 8)},
    # Cyan infrastructure: a four-note minor chord out of one voice, one note per frame.
    "chord": {"tone": True, "volume": [14, 13, 12, 12, 11, 11, 10], "volume_loop": 5,
              "arpeggio": CHORD_MINOR},
    # Magenta ICE: the same machinery with the flat second and the flat sixth in it.
    "chord_ice": {"tone": True, "volume": [15, 14, 13, 12, 12, 11, 11], "volume_loop": 5,
                  "arpeggio": CHORD_ICE},
    # The build's chord, hanging on the fourth and refusing to resolve.
    # A rung under chord_ice on purpose: the build's whole job is to be somewhere the drop is
    # louder than, and a build that sustained above its own drop would undo the section.
    "chord_sus": {"tone": True, "volume": [13, 13, 12, 12, 11, 10, 10], "volume_loop": 4,
                  "arpeggio": CHORD_SUS},
    # The break's single voice — the one place a note is allowed to be just a note.
    "lead": {"tone": True, "volume": [9, 12, 15, 15, 14, 13, 13, 12], "volume_loop": 6,
             "vibrato_depth": 5, "vibrato_speed": 15},
    # The kit. A kick IS a low tone with a fast pitch drop; a snare is the noise generator with a
    # short decay; a hat is three frames of the same generator at its shortest period.
    "kick": {"tone": True, "noise": False, "pitch_slide": 150, "volume": envelope(15, 7)},
    "snare": {"tone": False, "noise": True, "noise_period": 6, "volume": envelope(15, 7)},
    "hat": {"tone": False, "noise": True, "noise_period": 1, "volume": [9, 5, 2]},
}

SCORE_PATTERNS = {
    # INTRO: the machine coming up. Bass and grid only — the one section with an empty channel, so
    # that the chord voice arriving in intro_b is an event.
    "intro_a": [bass_line([ROOT] * 4, BASS_HOLD, accent_rows=()),
                spread({}, SCORE_ROWS),
                percussion_line(BAR_STARTS, (), hat_rows=SPARSE_HATS)],
    "intro_b": [bass_line([ROOT, ROOT, ROOT, "G-2"], BASS_DRIVE),
                chord_line([ROOT, ROOT, ROOT, "G-2"], "chord"),
                percussion_line(BAR_STARTS, BACKBEATS)],
    # VERSE (A): the main statement. Root, root, down a major third, back up a step.
    "verse_a": [bass_line([ROOT, ROOT, "F-2", "G-2"], BASS_DRIVE),
                chord_line([ROOT, ROOT, "F-2", "G-2"], "chord"),
                percussion_line(DRIVE_KICKS, BACKBEATS)],
    # Its answer, walking the Phrygian tetrachord down to the fifth.
    "verse_b": [bass_line([ROOT, "G-2", "F-2", "E-2"], BASS_DRIVE),
                chord_line([ROOT, "G-2", "F-2", "E-2"], "chord"),
                percussion_line(DRIVE_KICKS, BACKBEATS)],
    # CHORUS (B): the flat second takes the bass, the chord goes to the ICE shape, the kick doubles.
    "chorus_a": [bass_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT], BASS_OCTAVE),
                 chord_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT], "chord_ice",
                            rows_per_chord=ROWS_PER_BAR // 2),
                 percussion_line(DOUBLE_KICKS, BACKBEATS)],
    "chorus_b": [bass_line(["F-2", "G-2", ICE_ROOT, ROOT], BASS_OCTAVE),
                 chord_line(["F-2", "G-2", ICE_ROOT, ROOT], "chord_ice",
                            rows_per_chord=ROWS_PER_BAR // 2),
                 percussion_line(DOUBLE_KICKS, BACKBEATS)],
    # BREAK: everything thins. The bass strikes twice a bar, the chord voice becomes one held note,
    # and the grid goes to quarters — the only place in the loop that breathes.
    "break": [bass_line([ROOT, ROOT, "F-2", "F-2"], BASS_HOLD, accent_rows=()),
              line({0: "A-4", 16: "F-4"}, "lead"),
              percussion_line((0, 16), (), hat_rows=SPARSE_HATS)],
    # BUILD: the bass climbs F, F#, G and then leaps to the ICE root, the chord hangs on its fourth,
    # and the last bar is a snare roll. Its only job is to make the drop land.
    "build": [bass_line(["F-2", "F#2", "G-2", ICE_ROOT], BASS_OCTAVE),
              chord_line(["F-2", "F#2", "G-2", ICE_ROOT], "chord_sus"),
              percussion_line(BAR_STARTS, SNARE_ROLL)],
    # DROP: the peak. Bass on every row, the ICE chord restruck every half-bar, kick on every other
    # eighth — the densest thing in the score and the reason the break exists.
    "drop": [bass_line([ROOT, ICE_ROOT, ROOT, "G-2"], BASS_ROLL),
             chord_line([ROOT, ICE_ROOT, ROOT, "G-2"], "chord_ice",
                        rows_per_chord=ROWS_PER_BAR // 2),
             percussion_line(DROP_KICKS, BACKBEATS)],
    # TURN: four bars that walk the whole thing back to the top.
    "turn": [bass_line([ROOT, "G-2", "F-2", "E-2"], BASS_WALK),
             chord_line([ROOT, "G-2", "F-2", "E-2"], "chord"),
             percussion_line(DRIVE_KICKS, BACKBEATS)],
}

# The DMA lane, one entry per pattern. It doubles the YM kit where the kit is doing the work and
# adds the one voice the YM has no room for — a clap on the backbeat of every chorus and drop.
SCORE_DRUMS = {
    "intro_a": drum_lane(kick=BAR_STARTS, hat=SPARSE_HATS),
    "intro_b": drum_lane(kick=BAR_STARTS, snare=BACKBEATS, hat=OFFBEATS),
    "verse_a": drum_lane(kick=DRIVE_KICKS, snare=BACKBEATS, hat=OFFBEATS),
    "verse_b": drum_lane(kick=DRIVE_KICKS, snare=BACKBEATS, hat=OFFBEATS),
    "chorus_a": drum_lane(kick=DOUBLE_KICKS, clap=BACKBEATS, hat=OFFBEATS),
    "chorus_b": drum_lane(kick=DOUBLE_KICKS, clap=BACKBEATS, hat=OFFBEATS),
    "break": drum_lane(kick=(0, 16), hat=SPARSE_HATS),
    "build": drum_lane(kick=BAR_STARTS, snare=SNARE_ROLL, hat=OFFBEATS),
    "drop": drum_lane(kick=DROP_KICKS, clap=BACKBEATS, hat=OFFBEATS),
    "turn": drum_lane(kick=DRIVE_KICKS, snare=BACKBEATS, hat=OFFBEATS),
}

# 28 entries over 10 patterns, in six sections: intro, A, B, break/build/drop, B again, turnaround.
# It is deliberately longer than a loop anybody notices looping — 197 s at band 0's speed down to
# 143 s at band 3's — and the drop arrives twice from different directions.
SCORE_ORDER = [
    "intro_a", "intro_b",
    "verse_a", "verse_b", "verse_a", "verse_b",
    "chorus_a", "chorus_b",
    "verse_a", "verse_b",
    "break", "build", "drop", "drop",
    "verse_a", "verse_b",
    "chorus_a", "chorus_b", "chorus_a", "chorus_b",
    "break", "build", "drop", "drop",
    "verse_a", "verse_b", "turn", "turn",
]

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

# THE DRUM LANE'S OWN SAMPLES, packed into the SAME bank straight after the cues — the lane byte is
# a bank index, so there is one bank and one numbering, and songs/blackice_sfx.py builds it from
# this list. They are short on purpose: at band 3 a row is 160 ms, and a drum that outlived its row
# would be cut by the next one anyway.
# EVERY ONE IS SHORTER THAN THE SHORTEST ROW IT WILL EVER PLAY ON. The tightest row in the whole
# score is band 3's 160 ms (and the exfil pulse's 140 ms), and a drum that outlived its row would be
# cut off by the next hit on the same one DMA voice — which sounds like a stutter, smears the grid
# that carries the tempo, and leaves the previous drum's tail sitting under the next one where the
# verifier is trying to identify it. Measured: at 0.16 s the kick's tail put 50 of 110 hits in the
# wrong bin. Short is also simply what a punchy kit is.
DRUM_CATALOGUE = [
    {"name": "kick", "seconds": 0.11},
    {"name": "snare", "seconds": 0.12},
    {"name": "hat", "seconds": 0.055},
    {"name": "clap", "seconds": 0.13},
]
DRUM_SECONDS = {entry["name"]: entry["seconds"] for entry in DRUM_CATALOGUE}

# Bank index by name: the cues occupy 0..9 and the drums follow them.
DRUM_BANK = {entry["name"]: len(SFX_CATALOGUE) + index
             for index, entry in enumerate(DRUM_CATALOGUE)}

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
                 "volume": pulse_envelope(15, 6, 3, sting_frames("trace_alarm"))},
    # The player's own damage, which must not be mistakable for an enemy's: rough and falling fast.
    "ym_hit": {"tone": True, "noise": True, "noise_period": 6, "pitch_slide": 85,
               "volume": envelope(15, sting_frames("player_hit"))},
    # ICE coming apart — the arpeggio falls away under a long decay.
    "ym_dissolve": {"tone": True, "noise": True, "noise_period": 9, "pitch_slide": 35,
                    "arpeggio": [0, -5, -12], "volume": envelope(15, sting_frames("enemy_dissolve"))},
    # A real wail: deep vibrato at about two cycles across the sound (the phase accumulator steps
    # `speed` per frame and wraps every 256, so 256 / 8 = 32 frames a cycle).
    "ym_siren": {"tone": True, "vibrato_depth": 46, "vibrato_speed": 8,
                 "volume": pulse_envelope(15, 12, 3, sting_frames("exfil_siren"))},
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

def sfx_macro(entry):
    instrument, note = YM_MACRO_VOICE[entry["name"]]
    return {"name": entry["name"], "priority": entry["priority"],
            "instrument": instrument, "note": note}


SFX_MACROS = [sfx_macro(entry) for entry in SFX_CATALOGUE]

# --------------------------------------------------------------------------- the title theme ----

# Colder and sparser than the score, but no longer thin: a sustained drone with the octave answering
# it, a chord voice that arrives only in the last section, and a tick on EVERY row. The drone still
# holds each note for two rows — 480 ms at TITLE_SPEED — which is what makes this the window
# verify.py measures pitch in, and the chord voice is skipped by that check because an arpeggio
# moves the pitch every frame (mk_song.py: song_metadata).
TITLE_ROWS = 32
TITLE_INSTRUMENTS = {
    "drone": {"tone": True, "volume": [12, 13, 13, 12, 12, 11, 11, 10], "volume_loop": 7},
    "cold": {"tone": True, "volume": [6, 9, 11, 12, 12, 11, 11, 10], "volume_loop": 6,
             "vibrato_depth": 3, "vibrato_speed": 11},
    "chord_cold": {"tone": True, "volume": [10, 11, 11, 10, 10, 9], "volume_loop": 4,
                   "arpeggio": CHORD_ICE},
    "tick": {"tone": False, "noise": True, "noise_period": 3, "volume": [7, 3, 1]},
}

# The drone's own bar: root, root, root, octave — two rows to a strike.
TITLE_BASS = (0, None, 0, None, 0, None, 12, None)
TITLE_TICKS = {row: "C-2" for row in range(TITLE_ROWS)}


def title_bass(roots):
    return bass_line(roots, TITLE_BASS, rows=TITLE_ROWS, instrument="drone", accent_rows=())


TITLE_PATTERNS = {
    "cold_a": [title_bass([ROOT, ROOT, "F-2", "F-2"]),
               line({0: "A-4", 8: "E-4", 16: "F-4", 24: "E-4"}, "cold", rows=TITLE_ROWS),
               line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
    "cold_b": [title_bass(["G-2", "G-2", ICE_ROOT, ICE_ROOT]),
               line({0: "G-4", 8: "F-4", 16: "A#4", 24: "A-4"}, "cold", rows=TITLE_ROWS),
               line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
    # The one place the title lets the flat second sit exposed, and the only one with a chord in it:
    # the ICE, before the game starts.
    "cold_c": [title_bass([ICE_ROOT, ICE_ROOT, ROOT, ROOT]),
               chord_line([ICE_ROOT, ICE_ROOT, ROOT, ROOT], "chord_cold", rows=TITLE_ROWS),
               line(TITLE_TICKS, "tick", rows=TITLE_ROWS)],
}

# The title gets the drum lane too, but NO KICK — hats on the quarters and a snare in the last
# section. Musically that is what a cold attract screen wants; it is also the honest thing to do to
# the measurement. The kick is a 400 -> 52 Hz chirp and the title's drone sits at 87-110 Hz, so a
# kick struck on a drone's own onset row puts foreign energy inside the exact band verify.py reads
# that note's pitch out of — measured at 4.5% on the F-2, against a 4% tolerance. That is the
# MEASUREMENT reason; the musical one is that a cold attract screen does not want a kick drum.
# They point the same way. The score's lane keeps its kick: nothing measures pitch there.
TITLE_DRUMS = {
    "cold_a": drum_lane(rows=TITLE_ROWS, hat=SPARSE_HATS),
    "cold_b": drum_lane(rows=TITLE_ROWS, hat=SPARSE_HATS),
    "cold_c": drum_lane(rows=TITLE_ROWS, snare=BACKBEATS, hat=SPARSE_HATS),
}

# 4 x 32 rows x 12 frames = 1536 frames = 30.7 s.
TITLE_ORDER = ["cold_a", "cold_b", "cold_a", "cold_c"]

# ------------------------------------------------------------------------------- the stings -----

# Both stings strike a note every STING_NOTE_ROWS rows, which is what bounds `fall`'s slide.
STING_NOTE_ROWS = 8
STING_NOTE_FRAMES = STING_NOTE_ROWS * STING_SPEED

STING_INSTRUMENTS = {
    # THE ONLY SLIDING VOICE THAT IS NOT ALSO A ONE-SHOT would be a bug: the driver accumulates the
    # bend for as long as a note sounds and never bounds it, so a looping envelope plus a slide is
    # a voice that walks to the 12-bit period ceiling and parks there. A table exactly as long as
    # the note is what makes "the trace closes" a controlled fall rather than a slide into a wall.
    "fall": {"tone": True, "pitch_slide": 2,
             "volume": envelope(15, STING_NOTE_FRAMES, floor=4)},
    "crash": {"tone": False, "noise": True, "noise_period": 8, "volume": envelope(15, 14)},
    "rise": {"tone": True, "arpeggio": CHORD_LIFT, "volume": [12, 14, 15, 15, 14, 13, 12, 11],
             "volume_loop": 6},
    "ping": {"tone": True, "arpeggio": [0, 12], "volume": envelope(15, 10)},
}

# DEATH — the trace closes: both voices fall a tritone and then to the flat second, over a crash.
# 24 rows x 6 frames = 2.88 s. It LOOPS, like every song in this format; the game is expected to
# call ym_music_stop() when the sting's length has elapsed (see songs/README.md).
DEATH_PATTERNS = {
    "death": [line({0: ROOT, 8: "D#2", 16: "A#1"}, "fall", rows=STING_ROWS),
              line({0: "A-4", 8: "D#4", 16: "A#3"}, "fall", rows=STING_ROWS),
              line({0: "C-2", 8: "C-2", 16: "C-2", 20: "C-2"}, "crash", rows=STING_ROWS)],
}

# CLEAR — the one major chord in the whole score, and the only time the ICE colour is absent.
# 32 rows x 6 frames = 3.84 s.
CLEAR_ROWS = 32
CLEAR_PATTERNS = {
    "clear": [line({0: "A-2", 8: "C-3", 16: "F-2", 24: "A-2"}, "rise", rows=CLEAR_ROWS),
              line({0: "A-4", 8: "C-5", 16: "F-4", 20: "A-4", 24: "C-5"}, "rise", rows=CLEAR_ROWS),
              line({0: "A-5", 12: "C-6", 20: "E-6", 28: "A-6"}, "ping", rows=CLEAR_ROWS)],
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
# The 100% lane: a hard four-on-the-floor under the pulse. At EXFIL_SPEED a row is 140 ms, so the
# kick is cut a little short by the next one — which at 214 BPM is what a kick is supposed to sound
# like.
EXFIL_DRUMS_ROWS = tuple(range(0, EXFIL_ROWS, 2))

EXFIL_PATTERNS = {
    "pulse": [line({row: ROOT for row in range(0, EXFIL_ROWS, 2)}, "pulse", rows=EXFIL_ROWS),
              line({row: "C-2" for row in range(EXFIL_ROWS)}, "clock", rows=EXFIL_ROWS),
              spread({}, EXFIL_ROWS)],
}


EXFIL_DRUMS = {
    "pulse": drum_lane(rows=EXFIL_ROWS, kick=EXFIL_DRUMS_ROWS,
                       hat=tuple(range(1, EXFIL_ROWS, 2))),
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
            "patterns": SCORE_PATTERNS, "order": SCORE_ORDER, "sfx": SFX_MACROS,
            "drum_bank": DRUM_BANK, "drums": SCORE_DRUMS}


def title_description():
    return {"speed": TITLE_SPEED, "rows": TITLE_ROWS, "instruments": TITLE_INSTRUMENTS,
            "patterns": TITLE_PATTERNS, "order": TITLE_ORDER, "sfx": [],
            "drum_bank": DRUM_BANK, "drums": TITLE_DRUMS}


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
            "patterns": EXFIL_PATTERNS, "order": ["pulse"], "sfx": SFX_MACROS,
            "drum_bank": DRUM_BANK, "drums": EXFIL_DRUMS}


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

/* The smallest frames-per-row any band is played at — so the fastest the drum lane can ever step,
 * and therefore the most hits a window of N frames can hold. A compile-time constant because the
 * harness sizes its drum ledger against it, and BLACKICE_BAND_SPEED[] is an array. */
#define BLACKICE_FASTEST_BAND_SPEED {min(BAND_SPEEDS)}

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
    drum_ids = "\n".join(f"#define SFX_DRUM_{name.upper():<11} {index}"
                          for name, index in sorted(DRUM_BANK.items(), key=lambda pair: pair[1]))
    drum_count = len(DRUM_BANK)
    drum_first = min(DRUM_BANK.values())
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

/* THE DRUM LANE'S SAMPLES share the same bank, straight after the cues. No game code names these —
 * the song's drum lane carries the bank index and ym_music_take_drum_hit hands it back — but they
 * are declared here because the numbering is a contract between the song and the bank, and a
 * contract nobody can see is one somebody will break. */
#define BLACKICE_DRUM_COUNT {drum_count}
#define BLACKICE_DRUM_FIRST {drum_first}

{drum_ids}

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
    for symbol, _, meta in built:
        if meta["drum_hits_per_loop"]:
            print(f"  {symbol} drum lane: {meta['drum_hits_per_loop']} hits per loop over "
                  f"{len(meta['drum_bank'])} samples (bank indices "
                  f"{min(meta['drum_bank'].values())}..{max(meta['drum_bank'].values())})")
    print("  trace bands: " + ", ".join(f"{index}={speed}f/row ({bpm(speed):.1f} BPM)"
                                        for index, speed in enumerate(BAND_SPEEDS))
          + f", exfil={EXFIL_SPEED}f/row ({bpm(EXFIL_SPEED):.1f} BPM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
