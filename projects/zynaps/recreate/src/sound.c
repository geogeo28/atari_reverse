/* sound.c — the YM2149 driver: the tune interpreter, the modulation machines, and the two flushes
 * that push the register shadow at the chip.
 *
 * The shape of the thing: `sound_start` arms one of three voice records with a tune stream;
 * `sound_tick` runs once a VBL and, for each voice, counts the current row down, fetches the next
 * row when it expires (`sound_voice_next_row`), and applies that voice's volume envelope and pitch
 * sweep (`sound_voice_modulate`). Everything writes a 14-byte SHADOW of the chip's registers, and
 * only `sound_tick` and `sound_reset_psg` push that shadow at $ff8800/$ff8802.
 *
 * The data is the Z80/AY original's, unchanged, so every table here is read little-endian; see
 * include/sound.h and docs/sound.md.
 */
#include "machine.h"
#include "psg.h"
#include "sound.h"

/* ================================================================================================
 * THE ONE BYTE ORDER THIS WHOLE FILE TURNS ON
 *
 * Every 16-bit datum the driver reads or writes — the two offset indices, the note-period table,
 * and the chip's own tone-period register pair — is LITTLE-endian on a big-endian machine
 * (`move.b 1(a0),dN / lsl.w #8,dN / move.b (a0),dN`, and its mirror on the way out). names.txt
 * reads that as data carried over unchanged from the Z80/AY original, a heritage gotcha
 * docs/sound.md covers. Reading it the 68000's own way gives nonsense: the shipped tune table reads
 * 0x019a, 0x023d, 0x02da, ... this way round and 0x9a01, 0x3d02, 0xda02, ... the other.
 *
 * It has ONE home here, rather than being spelt out at each of the five sites, so that the file's
 * central claim is greppable and a byte-order correction cannot be applied to four of them. It is
 * NOT a candidate for machine.h beside `be16`/`wr16`: those become a single native load on the
 * m68k target because the image's byte order IS the machine's, and this pair must stay a byte
 * shuffle on every target precisely because it is the opposite order.
 * ============================================================================================= */

static uint16_t le16(const uint8_t *at) {
    return (uint16_t)((at[1] << 8) | at[0]);
}

static void wr_le16(uint8_t *at, uint16_t value) {
    at[0] = (uint8_t)value;
    at[1] = (uint8_t)(value >> 8);
}

/* ================================================================================================
 * The offset tables — sound_lookup_tune @ 0x16b32, sound_lookup_modtable @ 0x16cec
 * ============================================================================================= */

/* How a BYTE index reaches a word table, which is the same two instructions at all three sites that
 * do it: the two offset indices here and the note-period table further down. Named once for that
 * reason — the mask is not the table's length, it is the whole of the routine's bounds checking. */
#define TABLE_NUMBER_MASK 0xffu  /* `andi.w #$ff,dN` — only the low byte of the number is used */
#define TABLE_ENTRY_BYTES 2u     /* `lsl.w #1,dN` — one 16-bit entry per number */

/* `number` is the whole D1 word because that is what the mask sees; the high half of D1 is never
 * touched by any step of either routine.
 *
 * NEITHER ROUTINE BOUNDS THE NUMBER: names.txt reads 45 tunes and 31 modulation tables, but the
 * mask admits all 256 and both resolve every one, reading the data behind the index as if it were
 * more offsets. So the differential drives all 256 and each routine is verified over its whole
 * input range. */
static uint16_t table_offset(const uint8_t *image, uint32_t index, uint16_t number) {
    return le16(image + index + (number & TABLE_NUMBER_MASK) * TABLE_ENTRY_BYTES);
}

/* `adda.w d1,a1` SIGN-EXTENDS, and that arm is live rather than theoretical: 52 of the 256 words a
 * tune number can reach have bit 15 set (the first is number 45, 0x80c8), so those resolve BELOW
 * the data base — 0xf2b0 for that one, under the load base entirely. Dropping the sign extension
 * turns test_every_tune_number red at 45, so this is pinned, not merely transcribed. */
uint32_t sound_lookup_tune(const uint8_t *image, uint16_t number) {
    return addr_add(A_tune_data, sign_ext16(table_offset(image, A_tune_index, number)));
}

/* The same routine one table over, register for register (`d1` in, `a0` out instead of `a1`). */
uint32_t sound_lookup_modtable(const uint8_t *image, uint16_t number) {
    return addr_add(A_mod_table_data,
                    sign_ext16(table_offset(image, A_mod_table_index, number)));
}

/* Register map: D1 in = the sound number; A1 out = the stream pointer, and D1's low word is left
 * holding the table offset it was built from (its high half is the caller's, untouched). Neither
 * output is memory, so the test's stub stores both at A0 = `result` — see test/abi.py.
 *
 * THE TABLE IS READ EXACTLY ONCE, through the core, and the offset is recovered from the pointer
 * rather than looked up again. Both halves of that matter. Reading it a second time between the two
 * stores would diverge from the original, which derives A1 from D1 and never goes back to the
 * table, for any `result` overlapping it. Recovering it instead of computing it alongside keeps ONE
 * path through the core: a glue that rebuilt the pointer itself would leave `sound_lookup_tune`
 * untested, which is measurable — dropping its `sign_ext16` then survives the whole suite.
 *
 * The recovery is exact, not an approximation: the core adds a sign-extended 16-bit offset to a
 * constant base, and truncating that sum back to 16 bits returns the offset for every input,
 * wrap included. */
void g_sound_lookup_tune(uint8_t *image, uint32_t number_reg, uint32_t result) {
    uint32_t stream = sound_lookup_tune(image, (uint16_t)number_reg);

    wr32(image + result,     stream);
    wr32(image + result + 4, set_low_word(number_reg, (uint16_t)(stream - A_tune_data)));
}

/* Register map: D1 in = the modulation-table number; A0 out = the record, D1's low word the offset.
 * Same recovery argument as above.
 *
 * A0 IS THIS ROUTINE'S ANSWER, which is why its test uses a different stub from the tune lookup's:
 * `register_call_pokes` stores THROUGH A0, so it cannot serve a routine that overwrites it. The
 * `movem.l` stub does, and its order is the instruction's — D1 then A0 — so that is the order
 * here. */
void g_sound_lookup_modtable(uint8_t *image, uint32_t number_reg, uint32_t result) {
    uint32_t record = sound_lookup_modtable(image, (uint16_t)number_reg);

    wr32(image + result,     set_low_word(number_reg, (uint16_t)(record - A_mod_table_data)));
    wr32(image + result + 4, record);
}

/* ================================================================================================
 * sound_start @ 0x16ac8 — arm a voice with a tune
 * ============================================================================================= */

/* Which of the three records a channel code selects. 1 and 2 name voices 1 and 2; EVERYTHING ELSE
 * is voice 3, including 0 and the codes no stream uses — the original tests only those two values
 * and falls through. */
static uint32_t voice_for_channel(uint8_t channel) {
    if (channel == SOUND_CHANNEL_VOICE1)
        return A_sound_voice1;
    if (channel == SOUND_CHANNEL_VOICE2)
        return A_sound_voice2;
    return A_sound_voice3;
}

/* Start tune `number` on the voice the stream (or `channel`) names.
 *
 * `channel` is D0 ON ENTRY and is only overwritten when the stream opens with its own 0xfa header,
 * so a stream without one is armed on whatever the caller happened to be holding. That is the
 * routine, not a simplification: the interpreter's spawn commands set D0 deliberately (1/2/3 from
 * `sub.b #$fb`), and `_start` reaches it with D0 left over from the boot sequence.
 *
 * NO HARDWARE AND NO TRAP. An earlier revision of STATUS.md called this blocked on the direct-PSG
 * surfaces; it is not, and every store below lands in the text segment where the image diff sees
 * it. The chip writes belong to the flush routines further down. */
void sound_start(uint8_t *image, uint16_t number, uint8_t channel) {
    uint32_t stream = sound_lookup_tune(image, number);
    uint32_t voice;

    if (image[stream] == SOUND_STREAM_CHANNEL_TAG) {
        channel = image[stream + 1];
        stream = addr_add(stream, SOUND_ROW_BYTES);
    }
    /* Code 4 means "alternate": the toggle byte flips bit 0, and its NEW value is the channel.
     *
     * WHICH TWO VOICES IT ALTERNATES BETWEEN IS A FACT ABOUT THE SHIPPED BYTE, not about the code,
     * and the shipped byte is 2 — not 0 or 1. So the round robin runs 2^1 = 3 (voice 3), then
     * 3^1 = 2 (voice 2), then 3, then 2: it alternates voices 3 and 2 and never reaches voice 1.
     * names.txt's comment on 0x16e90 reads it as 1 and 3, which is what the pair WOULD be had the
     * byte started at 0 or 1; test_sound.py drives all five values and the differential is what
     * says which the machine does. */
    if (channel == SOUND_CHANNEL_ALTERNATE) {
        channel = (uint8_t)(image[A_sfx_voice_toggle] ^ 1u);
        image[A_sfx_voice_toggle] = channel;
    }
    voice = voice_for_channel(channel);

    /* The record is disarmed for the duration of the rewrite and armed again at the end, so a VBL
     * landing in the middle of it cannot tick a half-written voice. Reproduced in order. */
    image[voice + VOICE_ENABLE] = 0;
    wr32(image + voice + VOICE_STREAM, stream);
    wr32(image + voice + VOICE_STREAM_LOOP, stream);
    wr32(image + voice + VOICE_STREAM_RESTART, stream);
    image[voice + VOICE_NOTE_COUNTDOWN] = 1;      /* expires on the very next tick */
    image[voice + VOICE_TRANSPOSE] = 0;
    image[voice + VOICE_ARPEGGIO] = 0;
    image[voice + VOICE_ENABLE] = 1;
}

/* Register map: D1 = the sound number, D0.b = the channel when the stream carries no 0xfa header.
 * `movem.l #$fffe,-(a7)` / `movem.l (a7)+,#$7fff` save and restore EVERY register, so the routine's
 * whole effect is memory and the glue returns nothing. */
void g_sound_start(uint8_t *image, uint32_t number_reg, uint32_t channel_reg) {
    sound_start(image, (uint16_t)number_reg, (uint8_t)channel_reg);
}

/* ================================================================================================
 * sound_set_note_period @ 0x16e04 — a note number into a voice's tone-period shadow pair
 * ============================================================================================= */

/* The table word is DOUBLED and stored little-endian, low byte first, which is the chip's own
 * layout: register 2N is the fine byte and 2N+1 the coarse one. The doubling is the AY-to-ST clock
 * ratio (names.txt on 0x16f40); it is a WORD shift, so a period above 0x7fff loses its top bit
 * rather than widening.
 *
 * The note reaches the table through the same byte mask and word stride the two offset indices use
 * — a different table, but the same two instructions, which is why they share their names. */
void sound_set_note_period(uint8_t *image, uint16_t note, uint32_t period_shadow) {
    uint32_t entry = addr_add(A_note_period_tbl,
                              sign_ext16((uint16_t)((note & TABLE_NUMBER_MASK)
                                                    * TABLE_ENTRY_BYTES)));

    wr_le16(image + period_shadow, (uint16_t)(le16(image + entry) << 1));
}

/* Register map: D0.b = the note, A5 = the voice's tone-period pair inside the register shadow. */
void g_sound_set_note_period(uint8_t *image, uint32_t note_reg, uint32_t period_shadow) {
    sound_set_note_period(image, (uint16_t)note_reg, period_shadow);
}

/* ================================================================================================
 * sound_modtable_step @ 0x16e4a (+ its A4 entry @ 0x16e48) — advance one modulation record
 * ============================================================================================= */

/* Advance the {period, delta, repeats} record at `record`'s cursor by one frame and return the
 * delta the caller should apply.
 *
 * IT IS A RATE AND A REPEAT COUNT, NOT TWO DELAYS — the first counter is RESET to zero every time
 * it matches, so a step of {4, 0x84, 3} does not mean "wait 4 frames then push 0x84 for 3": it
 * means "push 0x84 once every 4 frames, 3 times", and the step lasts 4 x 3 = 12 frames. The other
 * nine of those twelve answer `MOD_DELTA_NEUTRAL` and move nothing. The second counter counts
 * EMISSIONS, not frames, and only when it matches does the cursor step to the next three bytes.
 *
 * That is the shape a volume envelope needs — a slope's steepness is the period and its length is
 * the repeat count — and it is why a record's three bytes are not three of a kind.
 *
 * `counters` IS A SEPARATE ARGUMENT FROM `record` because the two entries differ in exactly that:
 * 0x16e48 enters with the counters at the record's own base (the volume machine and the noise
 * block), while 0x16e4a is entered with the counters two bytes along (the pitch machine). Both
 * cursors, though, live at `record + VOICE_MOD_VOLUME_CURSOR` — the pitch machine's caller hands in
 * a `record` already advanced by two pairs, which is how one routine serves both. */
/* Count the byte at `counter` up and report whether it has just reached the byte at `limit`,
 * resetting it to zero if so.
 *
 * THE LIMIT IS AN ADDRESS, NOT A VALUE, and that is the instruction order rather than a style
 * choice: `addq.b #1,(a0) / move.b (a1),d0 / sub.b (a0),d0 / bne` reads the record's byte AFTER
 * incrementing the counter, so the two orders differ for any input where the counter and the record
 * are the same byte. The game never arranges that; the order is free to keep, so it is kept.
 *
 * The match is an equality on BYTES (a subtraction tested against zero), so a counter that somehow
 * ran past its limit goes all the way round rather than firing every frame. */
static int counter_reached(uint8_t *image, uint32_t counter, uint32_t limit) {
    image[counter] = (uint8_t)(image[counter] + 1);
    if ((uint8_t)(image[limit] - image[counter]) != 0)
        return 0;
    image[counter] = 0;
    return 1;
}

uint8_t sound_modtable_step(uint8_t *image, uint32_t counters, uint32_t record) {
    uint32_t cursor = be32(image + record + VOICE_MOD_VOLUME_CURSOR);
    uint8_t delta;

    if (!counter_reached(image, counters, cursor + MOD_STEP_PERIOD))
        return MOD_DELTA_NEUTRAL;
    delta = image[cursor + MOD_STEP_DELTA];

    if (!counter_reached(image, addr_add(counters, 1), cursor + MOD_STEP_REPEATS))
        return delta;

    cursor = addr_add(cursor, MOD_STEP_BYTES);
    if (image[cursor] == MOD_RECORD_END)
        cursor = be32(image + record + VOICE_MOD_VOLUME_RESTART);
    wr32(image + record + VOICE_MOD_VOLUME_CURSOR, cursor);
    return delta;
}

/* The two-byte entry above it: the same routine with the counters at the record's own base. */
uint8_t sound_modtable_step_a4(uint8_t *image, uint32_t record) {
    return sound_modtable_step(image, record, record);
}

/* Register map: A0 = the counter pair, A4 = the record whose cursor and restart pointer are read;
 * D1.b out = the delta. A1 and D0 are scratch. The delta is a register, so the stub dumps D1 —
 * the memory effects (the counters, the cursor) are diffed directly. */
void g_sound_modtable_step(uint8_t *image, uint32_t counters, uint32_t record, uint32_t d1_reg,
                           uint32_t result) {
    uint8_t delta = sound_modtable_step(image, counters, record);

    wr32(image + result, set_low_word(d1_reg, set_low_byte((uint16_t)d1_reg, delta)));
}

void g_sound_modtable_step_a4(uint8_t *image, uint32_t record, uint32_t d1_reg, uint32_t result) {
    uint8_t delta = sound_modtable_step_a4(image, record);

    wr32(image + result, set_low_word(d1_reg, set_low_byte((uint16_t)d1_reg, delta)));
}

/* ================================================================================================
 * sound_noise_modulate @ 0x16e28 — sweep the chip's noise period
 * ============================================================================================= */

/* The noise sweep has no voice of its own: one record at `A_sound_noise_block` (a voice's first 24
 * bytes and nothing more) drives register 6 directly. The delta is BIASED by 0x80 so a record can
 * sweep either way, and the result is masked to the register's four bits. */
void sound_noise_modulate(uint8_t *image) {
    uint8_t delta = sound_modtable_step_a4(image, A_sound_noise_block);
    uint32_t noise = A_psg_reg_shadow + PSG_REG_NOISE_PERIOD;

    image[noise] = (uint8_t)((image[noise] + delta - MOD_DELTA_NEUTRAL) & PSG_NOISE_PERIOD_MASK);
}

/* Register map: none in — the routine loads A4 with the block's address itself. */
void g_sound_noise_modulate(uint8_t *image) {
    sound_noise_modulate(image);
}

/* ================================================================================================
 * sound_voice_modulate @ 0x16da6 — one voice's per-frame volume and pitch
 * ============================================================================================= */

#define PITCH_STEP_BIAS 0x100u  /* `add.w d1,d0` twice then `subi.w #$100` — the delta doubled */

/* Volume first, then EITHER a pitch sweep OR an arpeggio — never both, and the voice's
 * `VOICE_ARPEGGIO` byte is the switch: zero runs the sweep, anything else is the second note of a
 * two-note arpeggio the phase byte alternates between.
 *
 * A voice whose period is still zero returns after the volume step: with no note sounding there is
 * nothing to sweep, and the arpeggio would look one up out of the note table for no reason. */
void sound_voice_modulate(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    uint8_t delta = sound_modtable_step_a4(image, voice);
    uint32_t volume = be32(image + voice + VOICE_VOLUME_PTR);

    image[volume] = (uint8_t)(image[volume] + delta - MOD_DELTA_NEUTRAL);
    if (image[period_shadow] == 0 && image[period_shadow + 1] == 0)
        return;

    if (image[voice + VOICE_ARPEGGIO] == 0) {
        uint8_t step = sound_modtable_step(image, voice + VOICE_MOD_PAIR_STEP,
                                           voice + 2 * VOICE_MOD_PAIR_STEP);

        wr_le16(image + period_shadow,
                (uint16_t)(le16(image + period_shadow) + 2 * step - PITCH_STEP_BIAS));
    } else {
        uint8_t note = image[voice + VOICE_NOTE];
        uint8_t phase = (uint8_t)(image[voice + VOICE_ARPEGGIO_PHASE] ^ 1u);

        image[voice + VOICE_ARPEGGIO_PHASE] = phase;
        if (phase == 0)
            note = (uint8_t)(note + image[voice + VOICE_ARPEGGIO]);
        sound_set_note_period(image, note, period_shadow);
    }
}

/* Register map: A4 = the voice record, A5 = its tone-period pair in the shadow. A4 IS MODIFIED on
 * the sweep arm (`addq.l #2,a4` twice, which is how the pitch machine's offsets are reached) and
 * every caller reloads it, so it is not an output. */
void g_sound_voice_modulate(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    sound_voice_modulate(image, voice, period_shadow);
}

/* ================================================================================================
 * sound_cmd_swap_tunes @ 0x16c82 — command 0xec
 * ============================================================================================= */

/* Swap the first two entries of the tune index, byte by byte, so a repeated effect alternates
 * between two streams. It is spelt as two byte swaps rather than one word swap because that is what
 * the original does, and the two agree.
 *
 * IT TAKES NO OPERAND, which is what the returned cursor says: the interpreter has already consumed
 * two bytes for the row, and this hands one of them back (`subq.l #1,a0`) so the byte after the
 * opcode is read as the NEXT opcode. */
uint32_t sound_cmd_swap_tunes(uint8_t *image, uint32_t cursor) {
    for (unsigned byte = 0; byte < TABLE_ENTRY_BYTES; byte++) {
        uint8_t first = image[A_tune_index + byte];

        image[A_tune_index + byte] = image[A_tune_index + TABLE_ENTRY_BYTES + byte];
        image[A_tune_index + TABLE_ENTRY_BYTES + byte] = first;
    }
    return addr_add(cursor, (uint32_t)-1);
}

/* ================================================================================================
 * sound_voice_next_row @ 0x16bf0 — the tune-stream interpreter
 * ============================================================================================= */

/* A note-on: latch the row's duration and note, look the period up, silence the voice's volume
 * byte, reset both modulation machines from the template, and fold this voice's bits back into the
 * mixer. */
static void note_on(uint8_t *image, uint32_t voice, uint32_t period_shadow, uint8_t note,
                    uint8_t duration) {
    uint8_t noise_pending;
    uint8_t mixer_bits;
    uint8_t mixer;

    image[voice + VOICE_NOTE_COUNTDOWN] = duration;
    image[voice + VOICE_NOTE] = note;
    sound_set_note_period(image, note, period_shadow);
    image[be32(image + voice + VOICE_VOLUME_PTR)] = 0;

    for (unsigned byte = 0; byte < VOICE_MOD_TEMPLATE_BYTES; byte++)
        image[voice + VOICE_MOD_COUNTERS + byte] = image[voice + VOICE_MOD_TEMPLATE + byte];

    /* A pending 0xe4 (noise period) is consumed here, and consuming it means this note wants NOISE
     * rather than the voice's usual tone bits: the mixer gets no bits of its own from the voice,
     * and the noise sweep's own record is rewound so the sweep starts with the note. */
    noise_pending = image[voice + VOICE_NOISE_PENDING];
    image[voice + VOICE_NOISE_PENDING] = 0;
    if (noise_pending == 1) {
        mixer_bits = 0;
        image[A_sound_noise_block + VOICE_MOD_COUNTERS] = 0;
        image[A_sound_noise_block + VOICE_MOD_COUNTERS + 1] = 0;
        wr32(image + A_sound_noise_block + VOICE_MOD_VOLUME_CURSOR,
             be32(image + A_sound_noise_block + VOICE_MOD_VOLUME_RESTART));
    } else {
        mixer_bits = image[voice + VOICE_MIXER_BITS];
    }

    mixer = (uint8_t)(image[A_psg_reg_shadow + PSG_REG_MIXER] & image[voice + VOICE_MIXER_MASK]);
    image[A_psg_reg_shadow + PSG_REG_MIXER] =
        (uint8_t)(mixer | mixer_bits | PSG_MIXER_PORT_DIRECTION);
}

/* Read rows until one of them is a note or the voice stops.
 *
 * The loop has TWO re-entry points in the original and the difference matters: most commands
 * continue from the cursor in hand, while the four that call a lookup routine (which clobbers the
 * cursor register) go back and RELOAD it from the record. They agree only because those four leave
 * `VOICE_STREAM` alone — writing the reload out is what keeps that true if one ever stops. */
void sound_voice_next_row(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    uint32_t cursor = be32(image + voice + VOICE_STREAM);

    for (;;) {
        uint8_t opcode = image[cursor];
        uint8_t operand = image[cursor + 1];

        cursor = addr_add(cursor, SOUND_ROW_BYTES);
        wr32(image + voice + VOICE_STREAM, cursor);

        if (opcode == 0) {
            note_on(image, voice, period_shadow, 0, operand);
            return;
        }
        if (opcode < SOUND_ROW_NOTE_MAX) {
            note_on(image, voice, period_shadow,
                    (uint8_t)(opcode + image[voice + VOICE_TRANSPOSE]), operand);
            return;
        }
        switch (opcode) {
        case SOUND_CMD_END:
            image[voice + VOICE_ENABLE] = 0;
            image[be32(image + voice + VOICE_VOLUME_PTR)] = 0;
            return;
        case SOUND_CMD_NOISE_PERIOD:
            image[A_psg_reg_shadow + PSG_REG_NOISE_PERIOD] = operand;
            image[voice + VOICE_NOISE_PENDING] = 1;
            break;
        case SOUND_CMD_TRANSPOSE:
            image[voice + VOICE_TRANSPOSE] = operand;
            break;
        case SOUND_CMD_ARPEGGIO:
            image[voice + VOICE_ARPEGGIO] = operand;
            break;
        case SOUND_CMD_VOLUME_TABLE:
            wr32(image + voice + VOICE_MOD_VOLUME_RESTART,
                 sound_lookup_modtable(image, operand));
            cursor = be32(image + voice + VOICE_STREAM);
            break;
        case SOUND_CMD_PITCH_TABLE:
            wr32(image + voice + VOICE_MOD_PITCH_RESTART, sound_lookup_modtable(image, operand));
            cursor = be32(image + voice + VOICE_STREAM);
            break;
        case SOUND_CMD_NOISE_TABLE:
            wr32(image + A_sound_noise_block + VOICE_MOD_VOLUME_RESTART,
                 sound_lookup_modtable(image, operand));
            cursor = be32(image + voice + VOICE_STREAM);
            break;
        case SOUND_CMD_JUMP:
            /* The cursor SAVED here is the row after the jump, which is where 0xff comes back to. */
            wr32(image + voice + VOICE_STREAM_LOOP, cursor);
            cursor = sound_lookup_tune(image, operand);
            break;
        case SOUND_CMD_LOOP:
            cursor = be32(image + voice + VOICE_STREAM_LOOP);
            if (image[cursor] == SOUND_CMD_LOOP)
                cursor = be32(image + voice + VOICE_STREAM_RESTART);
            break;
        case SOUND_CMD_SWAP_TUNES:
            cursor = sound_cmd_swap_tunes(image, cursor);
            break;
        default:
            if (opcode < SOUND_CMD_SPAWN_FIRST)
                break;                        /* a command nothing implements — skip the row */
            sound_start(image, operand, (uint8_t)(opcode - SOUND_CMD_SPAWN_BIAS));
            cursor = be32(image + voice + VOICE_STREAM);
            break;
        }
    }
}

/* Register map: A4 = the voice record, A5 = its tone-period pair. A0/D0/D1 are scratch. */
void g_sound_voice_next_row(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    sound_voice_next_row(image, voice, period_shadow);
}

/* ================================================================================================
 * sound_voice_tick @ 0x16bd6 — one voice, one frame
 * ============================================================================================= */

/* THE ENABLE BYTE IS TESTED TWICE, and the second test is not redundant: fetching a row can run
 * command 0xe1, which stops the voice, and a stopped voice must not then be modulated. */
void sound_voice_tick(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    if (image[voice + VOICE_ENABLE] == 0)
        return;

    image[voice + VOICE_NOTE_COUNTDOWN] = (uint8_t)(image[voice + VOICE_NOTE_COUNTDOWN] - 1);
    if (image[voice + VOICE_NOTE_COUNTDOWN] == 0) {
        sound_voice_next_row(image, voice, period_shadow);
        if (image[voice + VOICE_ENABLE] == 0)
            return;
    }
    sound_voice_modulate(image, voice, period_shadow);
}

void g_sound_voice_tick(uint8_t *image, uint32_t voice, uint32_t period_shadow) {
    sound_voice_tick(image, voice, period_shadow);
}

/* ================================================================================================
 * The two flushes — sound_reset_psg @ 0x16b4e and sound_tick @ 0x16b94
 * ============================================================================================= */

/* Push shadow registers `count - 1` down to 0 at the chip, which is the order both flushes use.
 *
 * DESCENDING IS NOT COSMETIC. The volumes are written before the periods, so a period the same
 * frame changed is never heard at the old volume; and, whatever the reason, the ORDER is the only
 * thing separating this from a loop the other way round — the register file both leave behind is
 * identical, and only the kit's ordered access ledger can tell them apart (TRAP_MODEL.md, Phase 6).
 *
 * The ports are outside the memory image, so these are the one part of the driver the image diff
 * cannot see; `psg_port_write` is the surface that does. */
static void flush_shadow(const uint8_t *image, unsigned count) {
    for (unsigned reg = count; reg-- > 0; )
        psg_port_write(reg, image[A_psg_reg_shadow + reg]);
}

/* Silence everything: stop all three voices, zero the three volumes, mute every channel in the
 * mixer, and push the whole shadow — all 14 registers, envelope and I/O ports included. */
void sound_reset_psg(uint8_t *image) {
    image[A_sound_voice1 + VOICE_ENABLE] = 0;
    image[A_sound_voice2 + VOICE_ENABLE] = 0;
    image[A_sound_voice3 + VOICE_ENABLE] = 0;
    image[A_psg_reg_shadow + PSG_REG_VOLUME_A] = 0;
    image[A_psg_reg_shadow + PSG_REG_VOLUME_A + 1] = 0;
    image[A_psg_reg_shadow + PSG_REG_VOLUME_A + 2] = 0;
    image[A_psg_reg_shadow + PSG_REG_MIXER] = PSG_MIXER_ALL_OFF;
    flush_shadow(image, PSG_SHADOW_REGS);
}

void g_sound_reset_psg(uint8_t *image) {
    sound_reset_psg(image);
}

/* The VBL tick: push LAST frame's shadow, then compute this frame's.
 *
 * That order is the driver's whole timing model — the chip is updated at a fixed point in the frame
 * from state computed a frame earlier, so a long tick cannot smear a register update across the
 * raster. Only registers 10..0 go out; 11..13 are the envelope period and shape, which this driver
 * never uses, and pushing register 13 would RETRIGGER the envelope every frame. */
void sound_tick(uint8_t *image) {
    flush_shadow(image, PSG_TICK_FLUSH_REGS);
    sound_voice_tick(image, A_sound_voice1, A_psg_reg_shadow + 0 * PSG_VOICE_PERIOD_BYTES);
    sound_voice_tick(image, A_sound_voice2, A_psg_reg_shadow + 1 * PSG_VOICE_PERIOD_BYTES);
    sound_voice_tick(image, A_sound_voice3, A_psg_reg_shadow + 2 * PSG_VOICE_PERIOD_BYTES);
    sound_noise_modulate(image);
}

/* Register map: none — `movem.l #$fffe,-(a7)` / `movem.l (a7)+,#$7fff` save and restore every
 * register, so the tick's whole effect is the shadow, the voice records and the chip. */
void g_sound_tick(uint8_t *image) {
    sound_tick(image);
}
