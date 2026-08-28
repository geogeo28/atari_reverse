#!/usr/bin/env python3
"""mk_song.py — compile a song description into the YM replayer's binary format.

    python3 mk_song.py                 # the built-in demo tune -> song_data.c/.h, ym_notes.h, out/
    python3 mk_song.py --dump-json F   # write the demo description out as JSON (the composer's
                                       # own input format, so the JSON path is a real path)
    python3 mk_song.py --json F        # compile that JSON instead

WHAT A DESCRIPTION IS. A dict with four keys, all of them small enough to hand-write:

    speed        frames per row (the whole tempo; 50 Hz / speed / rows = the song's clock)
    instruments  {name: {...}}  see INSTRUMENT_FIELDS below
    patterns     {name: [ch_a_tokens, ch_b_tokens, ch_c_tokens]} — three whitespace-separated
                 token strings of `rows` tokens each. A token is `...` (nothing), `===` (note off),
                 `D-2` (a note, holding the channel's current instrument) or `D-2:kick`.
    order        [pattern name, ...] — played in turn and then looped
    drum_bank    {sample name: index into the DMA sample bank} — optional; its presence is what
                 gives the song a drum lane
    drums        {pattern name: token string of `rows` tokens} — optional, one token per row,
                 `...` for nothing or a drum_bank name. THE FOURTH TRACK: it plays through the
                 STE's DMA voice, not the YM, so it costs no chip channel and simply does not
                 exist on a plain ST (see ym_music.h: ym_music_take_drum_hit).

THE BINARY FORMAT (big-endian; ym_music.c's SONG_OFF_* constants are the other half of this):

    header, 24 bytes
        0  'YMS2'
        4  u16 speed (frames per row)
        6  u8  rows per pattern
        7  u8  order length
        8  u8  pattern count
        9  u8  instrument count
       10  u8  sfx count
       11  u8  drum sample limit — one past the highest bank index the lane names, 0 = no lane
       12  u16 offset of the order (one pattern index per byte)
       14  u16 offset of the pattern offset table (pattern count u16 entries)
       16  u16 offset of the instrument offset table (instrument count u16 entries)
       18  u16 offset of the SFX macro table (sfx count 4-byte entries)
       20  u16 offset of the drum lane offset table (pattern count u16 entries), 0 = no lane
       22  u16 reserved (0)
    pattern      rows x 3 x (note byte, instrument byte); channels in A, B, C order
    drum lane    one byte per row, in the pattern's own row order:
                 0 = no hit, n >= 1 = DMA bank sample index n - 1
                 note 0 = nothing, 1 = note off, n >= 2 = semitone index n - 2
                 instrument 0 = keep the channel's last, n >= 1 = the nth instrument
    instrument   10-byte head then volume table then arpeggio table
        0  u8  flags: 1 = tone, 2 = noise, 4 = the volume table loops
        1  u8  volume table length          (one entry per frame; the software envelope)
        2  u8  volume loop point
        3  u8  arpeggio table length        (0 = no arpeggio; the table always loops)
        4  u8  noise period (0..31)
        5  u8  vibrato depth (period units)
        6  u8  vibrato speed (0 = off)
        7  u8  reserved (0)
        8  s16 pitch slide, period units per frame (positive = the pitch falls)
       10  u8  volume[volume table length], each 0..15
           s8  arpeggio[arpeggio table length], semitone offsets
    sfx macro    u8 instrument (1-based), u8 semitone index, u8 priority, u8 reserved

A NON-LOOPING VOLUME TABLE IS ALSO THE NOTE'S LENGTH: when it runs out the driver releases the
channel, which is how a percussion hit ends itself and how a stolen SFX channel is handed back.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"

# ------------------------------------------------------------------ notes, periods, frequencies --

# The YM2149 on an ST is clocked at half the 68000's 8 MHz bus, and its tone counter divides that
# by 16 more. So period = YM_CLOCK_HZ / (TONE_DIVISOR * frequency), and the 12-bit counter is what
# puts the floor under the lowest playable note.
YM_CLOCK_HZ = 2_000_000
TONE_DIVISOR = 16
TONE_PERIOD_MAX = 0x0FFF

NOTE_COUNT = 96
NOTE_BASE_HZ = 32.703195662574829     # C-1, i.e. semitone index 0 (MIDI note 24)
SEMITONES_PER_OCTAVE = 12
SEMITONE_NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
LOWEST_OCTAVE = 1

TOKEN_EMPTY = "..."
TOKEN_NOTE_OFF = "==="
NOTE_EMPTY = 0
NOTE_OFF = 1
NOTE_FIRST = 2
INSTRUMENT_KEEP = 0

CHANNEL_COUNT = 3
ROW_BYTES = CHANNEL_COUNT * 2

SONG_MAGIC = b"YMS2"
SONG_HEADER_BYTES = 24

# The drum lane's row byte. 0 is "no hit" so that an absent lane and a silent row encode the same
# way, which is why a bank index is stored biased by one.
DRUM_ROW_EMPTY = 0
DRUM_ROW_FIRST = 1
DRUM_BANK_INDEX_MAX = 0xFE          # biased by DRUM_ROW_FIRST, the row byte must stay a byte
INSTRUMENT_HEAD_BYTES = 10

INSTRUMENT_FLAG_TONE = 0x01
INSTRUMENT_FLAG_NOISE = 0x02
INSTRUMENT_FLAG_VOLUME_LOOP = 0x04

VOLUME_MAX = 15
NOISE_PERIOD_MAX = 31
SONG_SIZE_BUDGET = 4096               # the brief's ceiling for driver-visible song data
DEMO_SYMBOL = "demo_song"             # the C name of the demo blob, and its name in the metadata


def note_hz(index):
    """The frequency semitone `index` asks for, before the 12-bit period rounds it."""
    return NOTE_BASE_HZ * (2.0 ** (index / SEMITONES_PER_OCTAVE))


def note_period(index):
    """What ym_notes.h will hold for that index — the rounded, clamped YM tone period."""
    period = round(YM_CLOCK_HZ / (TONE_DIVISOR * note_hz(index)))
    return min(max(period, 1), TONE_PERIOD_MAX)


def played_hz(index):
    """The frequency the chip ACTUALLY produces for that index. This, not note_hz, is what a
    spectrum of the emulator's output has a peak at, so it is what verify.py compares against."""
    return YM_CLOCK_HZ / (TONE_DIVISOR * note_period(index))


def note_name(index):
    return SEMITONE_NAMES[index % SEMITONES_PER_OCTAVE] + str(index // SEMITONES_PER_OCTAVE
                                                              + LOWEST_OCTAVE)


NOTE_INDEX_BY_NAME = {note_name(index): index for index in range(NOTE_COUNT)}


class SongError(SystemExit):
    """Every refusal in this file. A SystemExit so a bad description stops the build with its own
    message rather than a traceback."""


# ---------------------------------------------------------------------------- the demo tune -----

# A dark, tense minute in D minor: a driving root-fifth bass, a slow modal lead over it, and the
# percussion on channel C (the one an SFX steals, so a hit silences the drums and nothing else).
DEMO_SPEED = 6                        # 6 frames/row at 50 Hz = 8.33 rows/s
DEMO_ROWS = 32                        # one pattern = 3.84 s


def envelope(peak, length, floor=0):
    """A straight decay from `peak` to `floor` over `length` frames — the shape most of these
    instruments want, written once."""
    if length < 2:
        return [peak]
    span = peak - floor
    return [max(floor, peak - round(span * step / (length - 1))) for step in range(length)]


DEMO_INSTRUMENTS = {
    # A sustaining bass: a short bite, then a level it holds until the row says otherwise.
    "bass": {"tone": True, "volume": [15, 15, 14, 13, 12, 12, 11, 11, 10], "volume_loop": 8},
    # The lead sustains too, and the vibrato is what stops a held square sounding like a test tone.
    "lead": {"tone": True, "volume": [10, 13, 15, 15, 14, 13, 13, 12], "volume_loop": 6,
             "vibrato_depth": 5, "vibrato_speed": 18},
    # A minor triad played one note per frame: the chip has three voices and this is how a
    # chip-tune gets a chord out of one of them.
    "chord": {"tone": True, "volume": [13, 12, 11, 11, 10, 10], "volume_loop": 4,
              "arpeggio": [0, 3, 7]},
    # Percussion. Each is a one-shot: the volume table's end is the sound's end.
    "kick": {"tone": True, "noise": True, "noise_period": 14, "pitch_slide": 90,
             "volume": envelope(15, 10)},
    "snare": {"tone": False, "noise": True, "noise_period": 6, "volume": envelope(14, 9)},
    "hat": {"tone": False, "noise": True, "noise_period": 2, "volume": [9, 5, 2]},
    # The six YM stand-ins for the DMA samples, used verbatim on a plain ST.
    "sfx_gunshot": {"tone": False, "noise": True, "noise_period": 1, "volume": envelope(15, 11)},
    "sfx_door": {"tone": False, "noise": True, "noise_period": 20,
                 "volume": [6, 8, 10, 11, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]},
    "sfx_pickup": {"tone": True, "arpeggio": [0, 4, 7, 12], "volume": envelope(15, 12)},
    "sfx_hit": {"tone": True, "noise": True, "noise_period": 8, "volume": envelope(15, 6)},
    "sfx_hurt": {"tone": True, "pitch_slide": 45, "volume": envelope(15, 14)},
    "sfx_death": {"tone": True, "noise": True, "noise_period": 11, "pitch_slide": 60,
                  "volume": envelope(15, 20)},
}

# The SFX macro table, in the order audiotest.c fires them and mk_samples.py packs them, so index N
# is the same sound on both paths. Priorities: a death or a gunshot outranks a pickup or a door.
DEMO_SFX = [
    {"name": "gunshot", "instrument": "sfx_gunshot", "note": "C-4", "priority": 6},
    {"name": "door", "instrument": "sfx_door", "note": "C-2", "priority": 2},
    {"name": "pickup", "instrument": "sfx_pickup", "note": "G-5", "priority": 3},
    {"name": "enemy_hit", "instrument": "sfx_hit", "note": "A-4", "priority": 4},
    {"name": "player_hurt", "instrument": "sfx_hurt", "note": "A-4", "priority": 5},
    {"name": "enemy_death", "instrument": "sfx_death", "note": "D-3", "priority": 5},
]


def spread(events, rows=DEMO_ROWS):
    """Turn {row: token} into the `rows`-token channel string the format wants.

    A row past the end is refused rather than dropped: a phrase one bar too long for its pattern is
    a musical mistake with no other symptom — the tail simply never plays."""
    if events and max(events) >= rows:
        raise SongError(f"a channel places a token on row {max(events)} of a {rows}-row pattern")
    return " ".join(events.get(row, TOKEN_EMPTY) for row in range(rows))


def bass_line(roots, instrument="bass"):
    """A root-and-octave pulse: the root on every other row, its octave answering, held four rows.

    `roots` is one note name per 8-row bar."""
    events = {}
    for bar, root in enumerate(roots):
        base = bar * 8
        octave_up = note_name(NOTE_INDEX_BY_NAME[root] + SEMITONES_PER_OCTAVE)
        events[base + 0] = f"{root}:{instrument}"
        events[base + 3] = root
        events[base + 4] = octave_up
        events[base + 6] = root
    return spread(events)


def drum_line(kick_rows, snare_rows, hat_rows):
    events = {row: "C-2:hat" for row in hat_rows}
    events.update({row: "D-4:snare" for row in snare_rows})
    events.update({row: "D-1:kick" for row in kick_rows})
    return spread(events)


def lead_line(phrase, instrument="lead"):
    """`phrase` is {row: note name}; the first entry carries the instrument."""
    events = {}
    for position, (row, name) in enumerate(sorted(phrase.items())):
        events[row] = f"{name}:{instrument}" if position == 0 else name
    return spread(events)


EVERY_OTHER_ROW = range(0, DEMO_ROWS, 2)
BACKBEAT_ROWS = [4, 12, 20, 28]
DOWNBEAT_ROWS = [0, 6, 8, 14, 16, 22, 24, 30]
SILENT = spread({})

DEMO_PATTERNS = {
    # Bass alone, then the hats arrive: two bars of nothing but the pulse.
    "intro": [bass_line(["D-2", "D-2", "D-2", "D-2"]), SILENT,
              drum_line([], [], range(16, DEMO_ROWS, 4))],
    "intro2": [bass_line(["D-2", "D-2", "A#1", "A-1"]),
               lead_line({8: "D-4", 12: "F-4", 16: "E-4", 24: "D-4"}),
               drum_line([0, 8, 16, 24], [], EVERY_OTHER_ROW)],
    # The main riff, and its answer a fourth down.
    "main_a": [bass_line(["D-2", "D-2", "F-2", "E-2"]),
               lead_line({0: "D-4", 4: "F-4", 6: "G-4", 8: "A-4", 16: "A#4", 20: "A-4",
                          24: "F-4", 28: "E-4"}),
               drum_line(DOWNBEAT_ROWS, BACKBEAT_ROWS, EVERY_OTHER_ROW)],
    "main_b": [bass_line(["D-2", "A#1", "C-2", "A-1"]),
               lead_line({0: "D-5", 4: "C-5", 8: "A#4", 12: "A-4", 16: "G-4", 20: "F-4",
                          24: "E-4", 26: "D-4"}),
               drum_line(DOWNBEAT_ROWS, BACKBEAT_ROWS, EVERY_OTHER_ROW)],
    # The tense middle: the lead voice becomes a chord, the bass climbs.
    "tense_a": [bass_line(["A#1", "A#1", "C-2", "C-2"]),
                lead_line({0: "D-4", 8: "D#4", 16: "F-4", 24: "E-4"}, "chord"),
                drum_line([0, 8, 16, 24], BACKBEAT_ROWS, EVERY_OTHER_ROW)],
    "tense_b": [bass_line(["A-1", "A-1", "A#1", "C-2"]),
                lead_line({0: "A-4", 8: "G-4", 16: "F-4", 20: "E-4", 24: "D-4"}, "chord"),
                drum_line(DOWNBEAT_ROWS, BACKBEAT_ROWS, EVERY_OTHER_ROW)],
    # The break: everything drops but the bass and one long lead note.
    "break": [bass_line(["D-2", "D-2", "D-2", "D-2"]),
              lead_line({0: "A-4", 16: "F-4"}),
              drum_line([0, 16], [], [])],
    # The outro walks the riff down and stops.
    "outro": [bass_line(["D-2", "C-2", "A#1", "A-1"]),
              lead_line({0: "D-4", 8: "C-4", 16: "A#3", 24: "A-3"}),
              drum_line([0, 8, 16], [24], range(0, 24, 2))],
}

DEMO_ORDER = ["intro", "intro2", "main_a", "main_b", "main_a", "main_b", "tense_a", "tense_b",
              "main_a", "main_b", "break", "tense_a", "tense_b", "main_a", "main_b", "outro"]


def demo_description():
    return {"speed": DEMO_SPEED, "rows": DEMO_ROWS, "instruments": DEMO_INSTRUMENTS,
            "patterns": DEMO_PATTERNS, "order": DEMO_ORDER, "sfx": DEMO_SFX}


# --------------------------------------------------------------------------------- the compiler --

def encode_instrument(name, spec):
    volume = spec["volume"]
    arpeggio = spec.get("arpeggio", [])
    if not volume:
        raise SongError(f"instrument '{name}' has an empty volume table — a note with no envelope "
                        f"has no length either, and the driver would release it on its first frame")
    if any(not 0 <= level <= VOLUME_MAX for level in volume):
        raise SongError(f"instrument '{name}' has a volume outside 0..{VOLUME_MAX}")
    loop = spec.get("volume_loop")
    flags = (INSTRUMENT_FLAG_TONE if spec.get("tone", True) else 0)
    flags |= (INSTRUMENT_FLAG_NOISE if spec.get("noise", False) else 0)
    if loop is not None:
        if not 0 <= loop < len(volume):
            raise SongError(f"instrument '{name}' loops to {loop}, outside its volume table")
        flags |= INSTRUMENT_FLAG_VOLUME_LOOP
    noise_period = spec.get("noise_period", 0)
    if not 0 <= noise_period <= NOISE_PERIOD_MAX:
        raise SongError(f"instrument '{name}' has a noise period outside 0..{NOISE_PERIOD_MAX}")

    head = bytes([flags, len(volume), loop or 0, len(arpeggio), noise_period,
                  spec.get("vibrato_depth", 0), spec.get("vibrato_speed", 0), 0])
    head += int(spec.get("pitch_slide", 0)).to_bytes(2, "big", signed=True)
    assert len(head) == INSTRUMENT_HEAD_BYTES
    return head + bytes(volume) + bytes(offset & 0xFF for offset in arpeggio)


def encode_row_token(token, instrument_ids, where):
    """One channel's token -> (note byte, instrument byte)."""
    if token == TOKEN_EMPTY:
        return NOTE_EMPTY, INSTRUMENT_KEEP
    if token == TOKEN_NOTE_OFF:
        return NOTE_OFF, INSTRUMENT_KEEP
    name, _, instrument = token.partition(":")
    if name not in NOTE_INDEX_BY_NAME:
        raise SongError(f"{where}: '{name}' is not a note name (C-1 .. B-8)")
    if instrument and instrument not in instrument_ids:
        raise SongError(f"{where}: no instrument called '{instrument}'")
    return (NOTE_FIRST + NOTE_INDEX_BY_NAME[name],
            instrument_ids[instrument] if instrument else INSTRUMENT_KEEP)


def encode_pattern(name, channels, rows, instrument_ids):
    if len(channels) != CHANNEL_COUNT:
        raise SongError(f"pattern '{name}' has {len(channels)} channels, not {CHANNEL_COUNT}")
    columns = []
    for index, text in enumerate(channels):
        tokens = text.split()
        if len(tokens) != rows:
            raise SongError(f"pattern '{name}' channel {index} has {len(tokens)} tokens, not {rows}")
        columns.append(tokens)
    out = bytearray()
    for row in range(rows):
        for index, tokens in enumerate(columns):
            note, instrument = encode_row_token(tokens[row], instrument_ids,
                                                f"pattern '{name}' channel {index} row {row}")
            out += bytes([note, instrument])
    assert len(out) == rows * ROW_BYTES
    return bytes(out)


def encode_drum_lane(name, tokens_text, rows, drum_bank):
    """One pattern's drum lane -> `rows` bytes, one per row.

    The lane is the ONE part of a pattern that names no YM channel: each byte is an index into the
    DMA sample bank, biased by DRUM_ROW_FIRST so that 0 can mean "no hit". It is a fourth track
    that costs no chip voice, which is the whole reason it exists."""
    tokens = tokens_text.split()
    if len(tokens) != rows:
        raise SongError(f"pattern '{name}' has a {len(tokens)}-token drum lane, not {rows}")
    out = bytearray()
    for row, token in enumerate(tokens):
        if token == TOKEN_EMPTY:
            out.append(DRUM_ROW_EMPTY)
        elif token in drum_bank:
            out.append(DRUM_ROW_FIRST + drum_bank[token])
        else:
            raise SongError(f"pattern '{name}' drum row {row}: '{token}' is not in the drum bank "
                            f"({', '.join(sorted(drum_bank)) or 'which is empty'})")
    return bytes(out)


def drum_sample_limit(drum_bank):
    """One past the highest bank index the lane can name — the driver's own range check, and 0 when
    the song has no lane at all.

    EVERY index is range-checked, not just the highest: a negative one would encode as
    DRUM_ROW_FIRST + (-1) = DRUM_ROW_EMPTY and turn a hit into silence, which is the one kind of
    mistake in this file that produces a valid blob and a wrong song."""
    if not drum_bank:
        return 0
    for name, index in sorted(drum_bank.items()):
        if not 0 <= index <= DRUM_BANK_INDEX_MAX:
            raise SongError(f"drum '{name}' is bank index {index}, outside "
                            f"0..{DRUM_BANK_INDEX_MAX}")
    return max(drum_bank.values()) + 1


def encode_sfx(entry, instrument_ids, instruments):
    if entry["instrument"] not in instrument_ids:
        raise SongError(f"sfx '{entry['name']}' names no instrument called '{entry['instrument']}'")
    if entry["note"] not in NOTE_INDEX_BY_NAME:
        raise SongError(f"sfx '{entry['name']}' has an unknown note '{entry['note']}'")
    if not 1 <= entry["priority"] <= 0xFF:
        raise SongError(f"sfx '{entry['name']}' needs a priority of at least 1 — 0 is the driver's "
                        f"'this channel belongs to the music'")
    # AN SFX MACRO MAY NOT LOOP ITS ENVELOPE, and this is the one authoring rule whose violation
    # would be silent and permanent. The volume table running out is the ONLY thing that hands
    # channel C back to the music, so a macro on a looping instrument takes the channel at the first
    # sound effect of the game and never gives it up — no crash, no error, just a third of the
    # arrangement missing from that point on. Refused here, where the description that caused it is
    # the thing being read; ym_music_init refuses such a blob and ym_music_sfx_play refuses to play
    # one, so the property holds whatever route the data took.
    if instruments[entry["instrument"]].get("volume_loop") is not None:
        raise SongError(f"sfx '{entry['name']}' uses instrument '{entry['instrument']}', whose "
                        f"volume table loops. An SFX macro must use a one-shot envelope: the "
                        f"envelope ending is what releases the SFX channel back to the music, so a "
                        f"looping one would hold it for ever")
    return bytes([instrument_ids[entry["instrument"]], NOTE_INDEX_BY_NAME[entry["note"]],
                  entry["priority"], 0])


def compile_song(description):
    """A description -> (blob bytes, a metadata dict the verifier reads)."""
    rows = description["rows"]
    instrument_names = list(description["instruments"])
    instrument_ids = {name: index + 1 for index, name in enumerate(instrument_names)}
    pattern_names = list(description["patterns"])
    pattern_ids = {name: index for index, name in enumerate(pattern_names)}

    instruments = [encode_instrument(name, description["instruments"][name])
                   for name in instrument_names]
    patterns = [encode_pattern(name, description["patterns"][name], rows, instrument_ids)
                for name in pattern_names]
    sfx = [encode_sfx(entry, instrument_ids, description["instruments"])
           for entry in description["sfx"]]
    order = bytes(pattern_ids[name] for name in description["order"])
    # THE LANE IS PER PATTERN AND ALWAYS COMPLETE. A pattern the description left out of `drums`
    # still gets a lane of silence, so the driver can index the lane table by pattern with no
    # second "does this one have drums" test in the tick.
    drum_bank = description.get("drum_bank", {})
    drum_text = description.get("drums", {})
    unknown = set(drum_text) - set(pattern_names)
    if unknown:
        raise SongError(f"the drum lane names patterns that do not exist: {sorted(unknown)}")
    if drum_text and not drum_bank:
        raise SongError("the description has `drums` but no `drum_bank`, so every token in it "
                        "names nothing — which would compile to a song with no lane at all")
    drum_sample_limit(drum_bank)      # range-checked here, before any index is encoded
    drum_lanes = [encode_drum_lane(name, drum_text.get(name, spread({}, rows)), rows, drum_bank)
                  for name in pattern_names] if drum_bank else []

    # Lay the sections out after the header, each on an even offset: the blob may be Fread into a
    # buffer and a 68000 must not meet an odd word inside it.
    body = bytearray()
    offsets = {}

    def place(name, chunk):
        if len(body) & 1:
            body.append(0)
        offsets[name] = SONG_HEADER_BYTES + len(body)
        body.extend(chunk)
        return offsets[name]

    place("order", order)
    pattern_offsets = [place(f"pattern{index}", chunk) for index, chunk in enumerate(patterns)]
    instrument_offsets = [place(f"instrument{index}", chunk)
                          for index, chunk in enumerate(instruments)]
    sfx_offset = place("sfx", b"".join(sfx))
    pattern_table = place("pattern_table",
                          b"".join(off.to_bytes(2, "big") for off in pattern_offsets))
    instrument_table = place("instrument_table",
                             b"".join(off.to_bytes(2, "big") for off in instrument_offsets))
    drum_offsets = [place(f"drum{index}", chunk) for index, chunk in enumerate(drum_lanes)]
    drum_table = place("drum_table",
                       b"".join(off.to_bytes(2, "big") for off in drum_offsets)) if drum_lanes else 0

    header = bytearray(SONG_MAGIC)
    header += description["speed"].to_bytes(2, "big")
    header += bytes([rows, len(order), len(patterns), len(instruments), len(sfx),
                     drum_sample_limit(drum_bank)])
    header += offsets["order"].to_bytes(2, "big")
    header += pattern_table.to_bytes(2, "big")
    header += instrument_table.to_bytes(2, "big")
    header += sfx_offset.to_bytes(2, "big")
    header += drum_table.to_bytes(2, "big")
    header += (0).to_bytes(2, "big")
    assert len(header) == SONG_HEADER_BYTES

    blob = bytes(header) + bytes(body)
    if len(blob) > SONG_SIZE_BUDGET:
        raise SongError(f"the song is {len(blob)} bytes, over the {SONG_SIZE_BUDGET}-byte budget")
    return blob, song_metadata(description, rows, pattern_ids)


def song_metadata(description, rows, pattern_ids):
    """What verify.py needs to predict what the emulator should sound like: the tempo, and every
    note the sequencer will trigger, with the frequency the CHIP will produce for it.

    Each event carries three properties of the instrument SOUNDING IT, because the spectral check
    can only look for a fundamental where one will be there long enough to find: `tone` (the
    percussion channel's notes still pick a period, and it is the noise generator that is audible),
    `sustains` (a one-shot envelope is over in a few frames, so its note has no steady state) and
    `arpeggiated` — an arpeggio steps the pitch EVERY FRAME, so the note's written root is present
    for only its share of the window and the peak there is not evidence about the driver either
    way. A checker that did not know this would read a chord as a detuned note."""
    events = []
    frame = 0
    playing = [None] * CHANNEL_COUNT
    for order_index, pattern_name in enumerate(description["order"]):
        columns = [text.split() for text in description["patterns"][pattern_name]]
        for row in range(rows):
            for channel, tokens in enumerate(columns):
                token = tokens[row]
                name, _, instrument = token.partition(":")
                if instrument:
                    playing[channel] = instrument
                if token in (TOKEN_EMPTY, TOKEN_NOTE_OFF) or playing[channel] is None:
                    continue
                spec = description["instruments"][playing[channel]]
                index = NOTE_INDEX_BY_NAME[name]
                events.append({"frame": frame, "order": order_index, "row": row,
                               "channel": channel, "note": index, "hz": played_hz(index),
                               "instrument": playing[channel],
                               "tone": bool(spec.get("tone", True)),
                               "noise": bool(spec.get("noise", False)),
                               "sustains": spec.get("volume_loop") is not None,
                               "arpeggiated": bool(spec.get("arpeggio"))})
            frame += description["speed"]
    drum_bank = description.get("drum_bank", {})
    drum_text = description.get("drums", {})
    hits_per_loop = sum(sum(1 for token in drum_text.get(name, "").split() if token != TOKEN_EMPTY)
                        for name in description["order"])
    return {"drum_bank": drum_bank, "drum_hits_per_loop": hits_per_loop,
            "speed": description["speed"], "rows": rows,
            "order": [pattern_ids[name] for name in description["order"]],
            "frames_total": frame, "sfx": [entry["name"] for entry in description["sfx"]],
            "events": events}


# ------------------------------------------------------------------------------ the C emitters ---

def c_array(name, blob):
    lines = [f"const unsigned char {name}[{len(blob)}] = {{"]
    for start in range(0, len(blob), 16):
        lines.append("    " + " ".join(f"0x{byte:02x}," for byte in blob[start:start + 16]))
    lines.append("};")
    return "\n".join(lines)


def write_notes_header(path):
    table = [note_period(index) for index in range(NOTE_COUNT)]
    rows = []
    for start in range(0, NOTE_COUNT, SEMITONES_PER_OCTAVE):
        octave = " ".join(f"{value:5d}," for value in table[start:start + SEMITONES_PER_OCTAVE])
        rows.append(f"    {octave}   /* {note_name(start)} .. "
                    f"{note_name(start + SEMITONES_PER_OCTAVE - 1)} */")
    body = "\n".join(rows)
    path.write_text(f"""/* ym_notes.h — GENERATED by mk_song.py; edit that, not this.
 *
 * The YM tone period for each semitone index, index 0 = {note_name(0)} at
 * {NOTE_BASE_HZ:.3f} Hz. period = {YM_CLOCK_HZ} / ({TONE_DIVISOR} * frequency), rounded.
 *
 * NOTHING IN THIS TABLE IS CLAMPED. The tone counter is 12 bits — 1 to {TONE_PERIOD_MAX} — and these
 * {NOTE_COUNT} notes span {max(table)} down to {min(table)}, clear of both ends, which is how the
 * note range was chosen: every entry is the pitch it says it is, with no flat spot at the bottom
 * where the counter would have run out. (mk_song.py's note_period() does clamp, and that is what
 * would catch a NOTE_COUNT or a base frequency edited past what the hardware can play.)
 */
#ifndef YM_NOTES_H
#define YM_NOTES_H

#include <stdint.h>

static const uint16_t ym_note_period[{NOTE_COUNT}] = {{
{body}
}};

#endif /* YM_NOTES_H */
""")


def write_sfx_ids_header(description, path):
    """The SFX CATALOGUE as C: one id per sound and the priority the description gave it.

    The DMA player is handed a priority per request and the YM driver reads its own out of the song
    blob; generating both from THIS description is what keeps the two paths agreeing about which
    sound outranks which, instead of a table hand-copied into the C."""
    entries = description["sfx"]
    ids = "\n".join(f"#define SFX_{entry['name'].upper():<14} {index}"
                     for index, entry in enumerate(entries))
    priorities = ", ".join(str(entry["priority"]) for entry in entries)
    path.write_text(f"""/* sfx_ids.h — GENERATED by mk_song.py; edit the description there, not this. */
#ifndef SFX_IDS_H
#define SFX_IDS_H

#define SFX_COUNT {len(entries)}

{ids}

/* Indexed by the ids above. Higher wins: a request is refused only by a STRICTLY higher one that
 * is still sounding. */
static const unsigned char sfx_priority[SFX_COUNT] = {{ {priorities} }};

#endif /* SFX_IDS_H */
""")


def write_song_source(blob, header_path, source_path, symbol):
    header_path.write_text(f"""/* song_data.h — GENERATED by mk_song.py; edit the description there, not this. */
#ifndef SONG_DATA_H
#define SONG_DATA_H

#define {symbol.upper()}_BYTES {len(blob)}

extern const unsigned char {symbol}[{symbol.upper()}_BYTES];

#endif /* SONG_DATA_H */
""")
    source_path.write_text(f"""/* song_data.c — GENERATED by mk_song.py; {len(blob)} bytes of song.
 *
 * WORD-ALIGNED because ym_music.h requires it: the driver reads a 16-bit field out of the blob
 * every frame, and a byte array's default alignment is 1. */
#include "song_data.h"

__attribute__((aligned(2)))
{c_array(symbol, blob)}
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=pathlib.Path, help="compile this description instead")
    parser.add_argument("--dump-json", type=pathlib.Path,
                        help="write the built-in demo description out as JSON and stop")
    args = parser.parse_args()

    if args.dump_json:
        args.dump_json.write_text(json.dumps(demo_description(), indent=2))
        print(f"wrote {args.dump_json}")
        return 0

    description = json.loads(args.json.read_text()) if args.json else demo_description()
    blob, meta = compile_song(description)

    OUT.mkdir(exist_ok=True)
    meta["symbol"] = DEMO_SYMBOL
    meta["bytes"] = len(blob)
    (OUT / "demo_song.bin").write_bytes(blob)
    (OUT / "song_meta.json").write_text(json.dumps(meta, indent=1))
    write_notes_header(HERE / "ym_notes.h")
    write_sfx_ids_header(description, HERE / "sfx_ids.h")
    write_song_source(blob, HERE / "song_data.h", HERE / "song_data.c", DEMO_SYMBOL)

    seconds = meta["frames_total"] / 50.0
    print(f"song: {len(blob)} bytes (budget {SONG_SIZE_BUDGET}), "
          f"{len(description['patterns'])} patterns, {len(description['order'])} in the sequence, "
          f"{len(description['instruments'])} instruments, {len(description['sfx'])} sfx macros, "
          f"{meta['frames_total']} frames = {seconds:.1f} s at 50 Hz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
