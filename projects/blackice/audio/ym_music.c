/* ym_music.c — the YM2149 replayer. See ym_music.h for the contract and mk_song.py for the blob.
 *
 * The whole driver is one pass per frame: step the row counter, advance three channels' little
 * tables, then push eleven PSG registers. Nothing here allocates, reads back the chip, or depends
 * on how long the previous frame took — the song's clock IS the vblank.
 *
 * WHAT THE SHAPE OF THIS FILE IS BUYING. The tick has a cycle budget (see REPORT.md), and three
 * things in here look like premature optimisation and are not; each was measured with Hatari's
 * profiler and each is worth ~8% of the tick:
 *   - the eleven hardware writes are ym_psg.S, not C, and that file carries the measurement.
 *   - the register image is filled completely rather than cleared and then patched: GCC turned an
 *     11-byte clear into a byte loop costing 308 cycles, more than the eleven hardware writes.
 *   - the per-channel mixer masks are a table, not `1 << index`; a register shift on a 68000 costs
 *     6 + 2n cycles and this one is on the hot path three times a frame.
 */
#include "ym_music.h"
#include "ym_notes.h"
#include "ym_psg.h"

/* ---------------------------------------------------------------- the YM2149 register file ---- */
/* The chip's address, the register count and the publish itself are ym_psg.h / ym_psg.S; what is
 * here is which register means what. */

#define PSG_REG_TONE_A_FINE    0   /* 0..5: fine byte then coarse byte, for channels A, B, C */
#define PSG_REG_NOISE_PERIOD   6
#define PSG_REG_MIXER          7
#define PSG_REG_VOLUME_A       8   /* 8..10: channels A, B, C */

#define PSG_REGS_PER_TONE      2   /* a channel's period is a fine byte then a coarse one */

/* Mixer semantics: a SET bit DISABLES that generator on that channel. Bits 6/7 select the I/O port
 * DIRECTION and must stay at "output", which is how TOS leaves them — port A drives floppy select
 * and the printer strobe, and flipping it to input mid-run would let the drive select float. */
#define PSG_MIXER_TONE_OFF_A   0x01
#define PSG_MIXER_NOISE_OFF_A  0x08
#define PSG_MIXER_PORTS_OUTPUT 0xC0
#define PSG_MIXER_ALL_OFF      (PSG_MIXER_PORTS_OUTPUT | 0x3F)

#define PSG_TONE_PERIOD_MIN    1
#define PSG_TONE_PERIOD_MAX    0x0FFF   /* the tone counter is 12 bits */
#define PSG_TONE_FINE_MASK     0x00FF
#define PSG_TONE_COARSE_SHIFT  8
#define PSG_NOISE_PERIOD_MAX   0x1F     /* the noise counter is 5 bits */
#define PSG_VOLUME_MAX         15       /* bit 4 would hand the channel to the hardware envelope */

/* --------------------------------------------------------------------- the song blob layout ---- */

#define SONG_MAGIC              0x594D5331UL   /* 'YMS1' */

#define SONG_OFF_MAGIC             0
#define SONG_OFF_SPEED             4    /* u16: frames per row */
#define SONG_OFF_ROWS_PER_PATTERN  6    /* u8  */
#define SONG_OFF_ORDER_LEN         7    /* u8  */
#define SONG_OFF_PATTERN_COUNT     8    /* u8  */
#define SONG_OFF_INSTRUMENT_COUNT  9    /* u8  */
#define SONG_OFF_SFX_COUNT        10    /* u8  */
#define SONG_OFF_ORDER            12    /* u16: offset of the sequence, one pattern index per byte */
#define SONG_OFF_PATTERN_TABLE    14    /* u16: offset of pattern_count u16 pattern offsets */
#define SONG_OFF_INSTRUMENT_TABLE 16    /* u16: offset of instrument_count u16 instrument offsets */
#define SONG_OFF_SFX_TABLE        18    /* u16: offset of sfx_count SFX macros */
#define SONG_HEADER_BYTES         20    /* nothing below this offset is a table */

/* A pattern row is one (note, instrument) byte pair per channel, channels in A, B, C order. */
#define ROW_BYTES_PER_CHANNEL      2
#define ROW_OFF_NOTE               0
#define ROW_OFF_INSTRUMENT         1
#define ROW_BYTES  (ROW_BYTES_PER_CHANNEL * YM_CHANNEL_COUNT)

#define NOTE_EMPTY                 0    /* row says nothing: the channel plays on */
#define NOTE_OFF                   1    /* release: the channel goes silent */
#define NOTE_FIRST                 2    /* note byte n encodes semitone index n - NOTE_FIRST */
#define INSTRUMENT_KEEP            0    /* instrument byte 0: reuse the channel's last one */

/* An instrument: a fixed head, then the volume table, then the arpeggio table. */
#define INS_OFF_FLAGS              0
#define INS_OFF_VOLUME_LEN         1
#define INS_OFF_VOLUME_LOOP        2
#define INS_OFF_ARP_LEN            3
#define INS_OFF_NOISE_PERIOD       4
#define INS_OFF_VIBRATO_DEPTH      5
#define INS_OFF_VIBRATO_SPEED      6
#define INS_OFF_PITCH_SLIDE        8    /* s16: period units added per frame (+ = pitch falls) */
#define INS_HEAD_BYTES            10

#define INS_FLAG_TONE            0x01
#define INS_FLAG_NOISE           0x02
#define INS_FLAG_VOLUME_LOOP     0x04

/* An SFX macro: which instrument, at which note, at which priority. */
#define SFX_OFF_INSTRUMENT         0    /* 1-based, as in a pattern row */
#define SFX_OFF_NOTE               1    /* semitone index, NOT biased by NOTE_FIRST */
#define SFX_OFF_PRIORITY           2
#define SFX_ENTRY_BYTES            4

/* Channel C is the one an SFX steals. It is the conventional choice — a three-voice arrangement
 * puts its least structural part (here the noise percussion) last — and picking one channel rather
 * than scoring all three each time keeps the steal decision a compare instead of a search. */
#define YM_SFX_CHANNEL             2
#define SFX_PRIORITY_NONE          0    /* the channel belongs to the music */
#define SFX_REQUEST_NONE      0xFFFF    /* the pending-request slot is empty (see ym_music.h) */

/* ---------------------------------------------------------------------------- driver state ---- */

typedef struct {
    const uint8_t *instrument;    /* 0 when the channel is silent */
    uint8_t  note;                /* semitone index of the sounding note */
    uint8_t  volume_step;         /* index into the instrument's volume table */
    uint8_t  arp_step;
    uint8_t  vibrato_phase;
    int16_t  bend;                /* accumulated pitch slide, in period units */
    uint8_t  sfx_priority;        /* SFX_PRIORITY_NONE, or the macro's priority while it sounds */
    uint8_t  last_instrument;     /* the row's 1-based instrument byte, remembered for NOTE_EMPTY */
} YmChannel;

/* What one channel decided THIS FRAME. Deliberately not part of YmChannel: a field the tick writes
 * and then reads back one line later is a memory round trip the compiler cannot remove, and five
 * of them per channel measured ~350 cycles a frame. As a local the whole struct stays in
 * registers. */
typedef struct {
    uint16_t period;
    uint8_t  volume;
    uint8_t  tone;
    uint8_t  noise;
    uint8_t  noise_period;
} YmVoiceOut;

static const uint8_t *song;           /* 0 until ym_music_init accepts a blob */
static uint32_t song_bytes;           /* what the caller declared, and every span is checked to fit */
static const uint8_t *order;
static const uint8_t *pattern_table;
static const uint8_t *instrument_table;
static const uint8_t *sfx_table;
static uint16_t song_speed;
static uint8_t  song_rows_per_pattern;
static uint8_t  song_order_len;
static uint8_t  song_pattern_count;
static uint8_t  song_instrument_count;
static uint8_t  song_sfx_count;

static YmChannel channel[YM_CHANNEL_COUNT];
static uint8_t  order_index;
static uint8_t  row_index;
static uint16_t frames_to_next_row;
static uint8_t  sequencer_running;

/* The SFX request ym_music_sfx_play lodges and the tick performs. One aligned word, written by
 * anyone and read by the tick — which is the whole of the locking, and ym_music.h says why. */
static volatile uint16_t sfx_request = SFX_REQUEST_NONE;

/* Which mixer bits each channel owns. A table, not a shift — see this file's header. */
static const uint8_t psg_mixer_tone_off[YM_CHANNEL_COUNT] = {
    PSG_MIXER_TONE_OFF_A << 0, PSG_MIXER_TONE_OFF_A << 1, PSG_MIXER_TONE_OFF_A << 2
};
static const uint8_t psg_mixer_noise_off[YM_CHANNEL_COUNT] = {
    PSG_MIXER_NOISE_OFF_A << 0, PSG_MIXER_NOISE_OFF_A << 1, PSG_MIXER_NOISE_OFF_A << 2
};

/* A sine at VIBRATO_UNIT full scale, so a depth reads directly in period units:
 * delta = wave[phase] * depth / VIBRATO_UNIT. */
#define VIBRATO_STEPS       16
#define VIBRATO_UNIT        64
#define VIBRATO_UNIT_SHIFT   6          /* log2(VIBRATO_UNIT), so the divide is a shift */
#define VIBRATO_PHASE_SHIFT  4          /* the phase accumulator's sub-step bits */

static const int8_t vibrato_wave[VIBRATO_STEPS] = {
      0,  24,  45,  59,  64,  59,  45,  24,
      0, -24, -45, -59, -64, -59, -45, -24
};

/* -------------------------------------------------------------------------- blob accessors ---- */

/* The blob is big-endian, matching the 68000 it runs on. Header and table reads go a byte at a
 * time so the format does not depend on how the caller aligned anything; the ONE field read every
 * frame (the pitch slide) is read as a word, which ym_music_init's alignment check makes safe. */
static uint16_t blob_word(const uint8_t *at)
{
    return (uint16_t)(((uint16_t)at[0] << 8) | at[1]);
}

/* may_alias: this reads a 16-bit field out of a byte-addressed image, which is exactly the
 * type-punning GCC's strict aliasing rules otherwise let it assume cannot happen. */
typedef int16_t __attribute__((may_alias)) BlobInt16;

static int16_t blob_signed_word(const uint8_t *at)
{
    return *(const BlobInt16 *)at;
}

static const uint8_t *blob_at(uint16_t offset)
{
    return song + offset;
}

static const uint8_t *instrument_by_index(uint8_t one_based)
{
    if (one_based == INSTRUMENT_KEEP || one_based > song_instrument_count) {
        return 0;
    }
    return blob_at(blob_word(instrument_table + (one_based - 1) * sizeof(uint16_t)));
}

/* The instrument an SFX macro names, or 0 when it is one this driver will not play as an SFX.
 *
 * A LOOPING VOLUME TABLE IS THE DISQUALIFIER, and it is not a detail: the envelope running out is
 * the only thing that ever hands channel C back to the music, so a macro on a looping instrument
 * takes the channel and keeps it for the rest of the run. mk_song.py refuses to emit one and
 * ym_music_init refuses to accept a blob containing one; this is the third place, and it is the one
 * that makes the property true of whatever blob is actually bound. */
static const uint8_t *sfx_instrument(const uint8_t *entry)
{
    const uint8_t *body = instrument_by_index(entry[SFX_OFF_INSTRUMENT]);

    if (body == 0 || (body[INS_OFF_FLAGS] & INS_FLAG_VOLUME_LOOP) != 0) {
        return 0;
    }
    return body;
}

/* ------------------------------------------------------------------------- channel stepping --- */

static void channel_release(YmChannel *ch)
{
    ch->instrument = 0;
    ch->sfx_priority = SFX_PRIORITY_NONE;
}

static void channel_trigger(YmChannel *ch, uint8_t note, const uint8_t *instrument)
{
    ch->instrument = instrument;
    ch->note = note;
    ch->volume_step = 0;
    ch->arp_step = 0;
    ch->vibrato_phase = 0;
    ch->bend = 0;
}

/* The volume table IS the envelope, and running off its end is what "the note finished" means: a
 * looping instrument wraps to its loop point and sustains, a one-shot releases the channel — which
 * is also how an SFX hands the channel back without the caller having to say when. */
static uint8_t channel_next_volume(YmChannel *ch, const uint8_t *instrument)
{
    uint8_t volume = instrument[INS_HEAD_BYTES + ch->volume_step];

    ch->volume_step++;
    if (ch->volume_step >= instrument[INS_OFF_VOLUME_LEN]) {
        if (instrument[INS_OFF_FLAGS] & INS_FLAG_VOLUME_LOOP) {
            ch->volume_step = instrument[INS_OFF_VOLUME_LOOP];
        } else {
            channel_release(ch);
        }
    }
    return volume;
}

static uint8_t channel_arpeggiated_note(YmChannel *ch, const uint8_t *instrument)
{
    uint8_t arp_len = instrument[INS_OFF_ARP_LEN];
    int16_t note;

    if (arp_len == 0) {
        return ch->note;
    }
    note = (int16_t)ch->note + (int8_t)instrument[INS_HEAD_BYTES
                                                  + instrument[INS_OFF_VOLUME_LEN] + ch->arp_step];
    ch->arp_step++;
    if (ch->arp_step >= arp_len) {
        ch->arp_step = 0;
    }
    if (note < 0) {
        note = 0;
    } else if (note >= YM_NOTE_COUNT) {
        note = YM_NOTE_COUNT - 1;
    }
    return (uint8_t)note;
}

static int16_t channel_vibrato_delta(YmChannel *ch, const uint8_t *instrument)
{
    uint8_t depth = instrument[INS_OFF_VIBRATO_DEPTH];
    uint8_t speed = instrument[INS_OFF_VIBRATO_SPEED];
    uint8_t step;

    if (depth == 0 || speed == 0) {
        return 0;
    }
    ch->vibrato_phase = (uint8_t)(ch->vibrato_phase + speed);
    step = (uint8_t)((ch->vibrato_phase >> VIBRATO_PHASE_SHIFT) & (VIBRATO_STEPS - 1));
    return (int16_t)((vibrato_wave[step] * (int16_t)depth) >> VIBRATO_UNIT_SHIFT);
}

/* One frame of one channel: decide the period and the volume this tick will publish. */
static void channel_step(YmChannel *ch, YmVoiceOut *out)
{
    /* Held in a LOCAL from here on: channel_next_volume can release the channel on the frame that
     * ends a one-shot envelope, and that frame still has to sound. */
    const uint8_t *instrument = ch->instrument;
    int32_t period;

    if (instrument == 0) {
        out->period = 0;
        out->volume = 0;
        out->tone = 0;
        out->noise = 0;
        return;
    }
    out->volume = channel_next_volume(ch, instrument) & PSG_VOLUME_MAX;
    out->tone = (uint8_t)(instrument[INS_OFF_FLAGS] & INS_FLAG_TONE);
    out->noise = (uint8_t)(instrument[INS_OFF_FLAGS] & INS_FLAG_NOISE);
    out->noise_period = instrument[INS_OFF_NOISE_PERIOD] & PSG_NOISE_PERIOD_MAX;

    period = (int32_t)ym_note_period[channel_arpeggiated_note(ch, instrument)];
    period += ch->bend + channel_vibrato_delta(ch, instrument);
    ch->bend = (int16_t)(ch->bend + blob_signed_word(instrument + INS_OFF_PITCH_SLIDE));

    if (period < PSG_TONE_PERIOD_MIN) {
        period = PSG_TONE_PERIOD_MIN;
    } else if (period > PSG_TONE_PERIOD_MAX) {
        period = PSG_TONE_PERIOD_MAX;
    }
    /* A tone-less instrument (pure noise percussion) still runs the arpeggio and the slide, because
     * that machinery is shared; what silences its square is the mixer bit, so the period it leaves
     * behind is inaudible and is zeroed only to keep the register image readable in a trace. */
    out->period = out->tone ? (uint16_t)period : 0;
}

/* ----------------------------------------------------------------------------- the sequencer --- */

static void sequencer_read_row(void)
{
    const uint8_t *pattern = blob_at(blob_word(pattern_table
                                               + order[order_index] * sizeof(uint16_t)));
    const uint8_t *cell = pattern + (uint16_t)row_index * ROW_BYTES;
    uint8_t index;

    for (index = 0; index < YM_CHANNEL_COUNT; index++, cell += ROW_BYTES_PER_CHANNEL) {
        YmChannel *ch = &channel[index];
        uint8_t note = cell[ROW_OFF_NOTE];
        uint8_t instrument = cell[ROW_OFF_INSTRUMENT];

        if (instrument != INSTRUMENT_KEEP) {
            ch->last_instrument = instrument;
        }
        /* A stolen channel still tracks the row's instrument (above) but plays none of it: the
         * music resumes on this channel at the next row that carries a note. */
        if (ch->sfx_priority != SFX_PRIORITY_NONE) {
            continue;
        }
        if (note == NOTE_OFF) {
            channel_release(ch);
        } else if (note >= NOTE_FIRST) {
            const uint8_t *body = instrument_by_index(ch->last_instrument);
            if (body != 0) {
                channel_trigger(ch, (uint8_t)(note - NOTE_FIRST), body);
            }
        }
    }
}

static void sequencer_advance(void)
{
    row_index++;
    if (row_index < song_rows_per_pattern) {
        return;
    }
    row_index = 0;
    order_index++;
    if (order_index >= song_order_len) {
        order_index = 0;          /* the sequence is a loop; there is no "song over" */
    }
}

static void sequencer_step(void)
{
    if (!sequencer_running) {
        return;
    }
    if (frames_to_next_row != 0) {
        frames_to_next_row--;
        return;
    }
    sequencer_read_row();
    sequencer_advance();
    frames_to_next_row = song_speed - 1;
}

/* ------------------------------------------------------------------------------ the API -------- */

static uint32_t blob_long(const uint8_t *at)
{
    return ((uint32_t)at[0] << 24) | ((uint32_t)at[1] << 16) | ((uint32_t)at[2] << 8) | at[3];
}

/* ------------------------------------------------- the blob's structure, walked once at init --- */
/*
 * THE TICK DOES NO BOUNDS CHECKING AT ALL, and this is what pays for that. Every offset in the
 * format is a 16-bit field inside the blob, and the sequencer follows them straight into memory; a
 * short Fread, a mis-sized array or one flipped byte in a table offset would have it reading a
 * pattern out of the program's own code and playing what that decoded to. So the whole structure
 * is walked ONCE, here, against the length the caller declared, and a blob that does not fit is
 * refused rather than played.
 */

/* Where a table the header pointed at sits inside the blob. The pointers were built from 16-bit
 * offsets a few lines earlier, so this is that offset back again — and it keeps every test below in
 * terms of one idea: a span inside the declared length. */
static uint32_t offset_of(const uint8_t *at)
{
    return (uint32_t)(at - song);
}

/* Is [offset, offset + length) inside the blob? Written as a subtraction rather than an addition so
 * that a large offset or length cannot wrap the comparison into agreeing. */
static int span_is_inside_the_blob(uint32_t offset, uint32_t length)
{
    return offset <= song_bytes && length <= song_bytes - offset;
}

/* The four tables the header names, checked before anything reads through them. */
static int header_tables_are_inside_the_blob(void)
{
    return span_is_inside_the_blob(offset_of(order), song_order_len)
        && span_is_inside_the_blob(offset_of(pattern_table),
                                   (uint32_t)song_pattern_count * sizeof(uint16_t))
        && span_is_inside_the_blob(offset_of(instrument_table),
                                   (uint32_t)song_instrument_count * sizeof(uint16_t))
        && span_is_inside_the_blob(offset_of(sfx_table),
                                   (uint32_t)song_sfx_count * SFX_ENTRY_BYTES);
}

/* Does every entry of the sequence name a pattern the blob actually holds? */
static int order_names_a_pattern(void)
{
    uint8_t index;

    for (index = 0; index < song_order_len; index++) {
        if (order[index] >= song_pattern_count) {
            return 0;
        }
    }
    return 1;
}

/* Every note byte in one pattern. A note reaches ym_note_period[] with no range test in the tick,
 * so a byte past the end of that table is a read into whatever the linker put after it. */
static int pattern_notes_are_notes(const uint8_t *pattern, uint32_t cells)
{
    uint32_t cell;

    for (cell = 0; cell < cells; cell++) {
        uint8_t note = pattern[cell * ROW_BYTES_PER_CHANNEL + ROW_OFF_NOTE];

        if (note >= NOTE_FIRST && (uint8_t)(note - NOTE_FIRST) >= YM_NOTE_COUNT) {
            return 0;
        }
    }
    return 1;
}

static int patterns_are_inside_the_blob(void)
{
    uint32_t pattern_bytes = (uint32_t)song_rows_per_pattern * ROW_BYTES;
    uint32_t cells = (uint32_t)song_rows_per_pattern * YM_CHANNEL_COUNT;
    uint8_t index;

    for (index = 0; index < song_pattern_count; index++) {
        uint16_t offset = blob_word(pattern_table + index * sizeof(uint16_t));

        if (!span_is_inside_the_blob(offset, pattern_bytes)
            || !pattern_notes_are_notes(blob_at(offset), cells)) {
            return 0;
        }
    }
    return 1;
}

/* An instrument is a fixed head and two variable tables, so the head is bounds-checked first and
 * its own lengths then say how far the rest reaches.
 *
 * THE EVEN OFFSET IS NOT TIDINESS. channel_step reads the pitch slide as a 16-bit word every frame
 * (blob_signed_word), so an instrument on an odd offset is an address error on the first note that
 * uses it — a crash three seconds into a level, from data. */
static int instruments_are_inside_the_blob(void)
{
    uint8_t index;

    for (index = 0; index < song_instrument_count; index++) {
        uint16_t offset = blob_word(instrument_table + index * sizeof(uint16_t));
        const uint8_t *body;

        if ((offset & 1) != 0 || !span_is_inside_the_blob(offset, INS_HEAD_BYTES)) {
            return 0;
        }
        body = blob_at(offset);
        /* A zero-length volume table would make channel_next_volume read the byte before the table
         * and release the channel on its first frame; a loop point past the end would walk out of
         * the blob one frame per note. */
        if (body[INS_OFF_VOLUME_LEN] == 0
            || body[INS_OFF_VOLUME_LOOP] >= body[INS_OFF_VOLUME_LEN]
            || !span_is_inside_the_blob(offset + INS_HEAD_BYTES,
                                        (uint32_t)body[INS_OFF_VOLUME_LEN]
                                        + body[INS_OFF_ARP_LEN])) {
            return 0;
        }
    }
    return 1;
}

/* Every SFX macro names an instrument that exists and a note that is one. The looping check is the
 * one rule here that is musical rather than structural: an envelope that loops never ends, so a
 * macro built on one would hold channel C for the rest of the run and the music would never get it
 * back. mk_song.py refuses to emit one; this refuses to accept one. */
static int sfx_macros_are_playable(void)
{
    uint8_t index;

    for (index = 0; index < song_sfx_count; index++) {
        const uint8_t *entry = sfx_table + (uint16_t)index * SFX_ENTRY_BYTES;

        if (sfx_instrument(entry) == 0 || entry[SFX_OFF_NOTE] >= YM_NOTE_COUNT) {
            return 0;
        }
    }
    return 1;
}

/* The whole walk, in the one order that is safe: a table is only read through after the check that
 * it is inside the blob, and `&&` is what sequences them. */
static int song_structure_is_sound(void)
{
    /* A song with no rows or no sequence would step forever on row 0; refuse it here rather than
     * let the tick divide the machine's time among nothing. */
    return song_speed != 0 && song_rows_per_pattern != 0 && song_order_len != 0
        && header_tables_are_inside_the_blob()
        && order_names_a_pattern()
        && patterns_are_inside_the_blob()
        && instruments_are_inside_the_blob()
        && sfx_macros_are_playable();
}

int ym_music_init(const void *song_blob, uint32_t bytes)
{
    const uint8_t *blob = (const uint8_t *)song_blob;

    song = 0;
    sequencer_running = 0;
    sfx_request = SFX_REQUEST_NONE;
    /* An odd blob would make blob_signed_word an address error two frames in, so it is refused
     * here where the caller can still do something about it. */
    if (blob == 0 || (((uint32_t)blob) & 1) != 0 || bytes < SONG_HEADER_BYTES) {
        return 0;
    }
    if (blob_long(blob + SONG_OFF_MAGIC) != SONG_MAGIC) {
        return 0;
    }

    /* The statics are filled in BEFORE the walk, because the walk reads through them. Nothing else
     * has been published at this point, and a blob that fails clears `song` again below — so a
     * refusal leaves the driver exactly as stopped as it was. */
    song = blob;
    song_bytes = bytes;
    song_speed = blob_word(blob + SONG_OFF_SPEED);
    song_rows_per_pattern = blob[SONG_OFF_ROWS_PER_PATTERN];
    song_order_len = blob[SONG_OFF_ORDER_LEN];
    song_pattern_count = blob[SONG_OFF_PATTERN_COUNT];
    song_instrument_count = blob[SONG_OFF_INSTRUMENT_COUNT];
    song_sfx_count = blob[SONG_OFF_SFX_COUNT];
    order = blob_at(blob_word(blob + SONG_OFF_ORDER));
    pattern_table = blob_at(blob_word(blob + SONG_OFF_PATTERN_TABLE));
    instrument_table = blob_at(blob_word(blob + SONG_OFF_INSTRUMENT_TABLE));
    sfx_table = blob_at(blob_word(blob + SONG_OFF_SFX_TABLE));

    if (!song_structure_is_sound()) {
        song = 0;
        return 0;
    }
    ym_music_stop();
    return 1;
}

void ym_music_start(void)
{
    uint8_t index;

    if (song == 0) {
        return;
    }
    for (index = 0; index < YM_CHANNEL_COUNT; index++) {
        channel_release(&channel[index]);
        channel[index].last_instrument = INSTRUMENT_KEEP;
    }
    order_index = 0;
    row_index = 0;
    frames_to_next_row = 0;
    sfx_request = SFX_REQUEST_NONE;
    sequencer_running = 1;
}

void ym_music_set_speed(uint16_t frames_per_row)
{
    if (frames_per_row != 0) {
        song_speed = frames_per_row;
    }
}

void ym_music_stop(void)
{
    uint8_t reg[PSG_REG_COUNT];
    uint8_t index;

    sequencer_running = 0;
    sfx_request = SFX_REQUEST_NONE;
    for (index = 0; index < PSG_REG_COUNT; index++) {
        reg[index] = 0;
    }
    reg[PSG_REG_MIXER] = PSG_MIXER_ALL_OFF;
    for (index = 0; index < YM_CHANNEL_COUNT; index++) {
        channel_release(&channel[index]);
    }
    ym_psg_publish(reg);
}

/* Perform whatever ym_music_sfx_play lodged since the last tick.
 *
 * THE SLOT IS CLEARED ONLY IF IT STILL HOLDS WHAT WE READ. A caller can store into it between the
 * read and the clear — that is the whole race this design is here to survive — and clearing
 * unconditionally would drop that request on the floor. Leaving it means the newcomer is performed
 * next tick instead. The one case still lost is a second request for the SAME sound inside those
 * two instructions, which is indistinguishable from asking twice in one frame.
 *
 * Called AFTER the sequencer's row, so an SFX arriving on the same frame as a music note on channel
 * C takes the channel, which is what stealing means. */
static void sfx_perform_request(void)
{
    uint16_t request = sfx_request;
    const uint8_t *entry;
    const uint8_t *body;

    if (request == SFX_REQUEST_NONE) {
        return;
    }
    if (sfx_request == request) {
        sfx_request = SFX_REQUEST_NONE;
    }
    if (request >= song_sfx_count) {
        return;
    }
    entry = sfx_table + request * SFX_ENTRY_BYTES;
    body = sfx_instrument(entry);
    if (body == 0) {
        return;
    }
    channel_trigger(&channel[YM_SFX_CHANNEL], entry[SFX_OFF_NOTE], body);
    channel[YM_SFX_CHANNEL].sfx_priority = entry[SFX_OFF_PRIORITY];
}

void ym_music_tick(void)
{
    uint8_t reg[PSG_REG_COUNT];
    uint8_t mixer = PSG_MIXER_ALL_OFF;
    uint8_t noise_period = 0;
    uint8_t index;

    if (song == 0) {
        return;
    }
    sequencer_step();
    sfx_perform_request();

    /* Every one of the eleven bytes is assigned here or below — the image is never cleared first,
     * which is worth 308 cycles a frame (this file's header). */
    for (index = 0; index < YM_CHANNEL_COUNT; index++) {
        uint8_t *tone = &reg[PSG_REG_TONE_A_FINE + index * PSG_REGS_PER_TONE];
        YmVoiceOut voice;

        channel_step(&channel[index], &voice);
        tone[0] = (uint8_t)(voice.period & PSG_TONE_FINE_MASK);
        tone[1] = (uint8_t)(voice.period >> PSG_TONE_COARSE_SHIFT);
        reg[PSG_REG_VOLUME_A + index] = voice.volume;
        if (voice.tone) {
            mixer &= (uint8_t)~psg_mixer_tone_off[index];
        }
        if (voice.noise) {
            /* One noise generator for three channels: the last channel to ask sets its colour. */
            mixer &= (uint8_t)~psg_mixer_noise_off[index];
            noise_period = voice.noise_period;
        }
    }
    reg[PSG_REG_NOISE_PERIOD] = noise_period;
    reg[PSG_REG_MIXER] = mixer;
    ym_psg_publish(reg);
}

int ym_music_sfx_play(uint8_t sfx_index)
{
    const uint8_t *entry;
    const YmChannel *ch = &channel[YM_SFX_CHANNEL];

    if (song == 0 || sfx_index >= song_sfx_count) {
        return 0;
    }
    entry = sfx_table + (uint16_t)sfx_index * SFX_ENTRY_BYTES;
    if (sfx_instrument(entry) == 0) {
        return 0;
    }
    /* Equal priority restarts (a repeated gunshot re-fires); only a strictly quieter claim loses to
     * a macro still sounding. The channel is READ here and written only by the tick, so the worst a
     * concurrent tick can do is answer from the state one frame either side of the question — which
     * is what "is it busy right now" means when the asker is not the tick. */
    if (ch->sfx_priority != SFX_PRIORITY_NONE && ch->instrument != 0
        && entry[SFX_OFF_PRIORITY] < ch->sfx_priority) {
        return 0;
    }
    /* The whole of the hand-off: one aligned word, which the 68000 stores indivisibly. */
    sfx_request = sfx_index;
    return 1;
}
