/* sound.c — Flying Shark's whole audio path: the `A\MODULE.BAK` YM2149 driver and the six game
 * wrappers that call it. See include/sound.h for where the names come from and what the offsets are
 * relative to, and ../notes/sound_engine.md for the format write-up.
 *
 * The shape of the thing. `music_start` arms three channel structs with a tune's sequence lists and
 * `sfx_start` arms one parameter block with an effect record; `sound_vbl_tick` runs once a VBL and
 * does four things in order:
 *
 *   1. the SEQUENCER, once every `tempo` frames — each channel consumes pattern bytes until one
 *      ends the step (a note, a rest, or the end of the song);
 *   2. the PER-FRAME update, every frame — each channel advances its volume envelope, its arpeggio,
 *      its vibrato and its pitch slide, and answers a tone period;
 *   3. the SOUND EFFECT, if one is running — it sweeps a period and OVERWRITES channel C's volume,
 *      period and noise bit, which is the whole of "an effect pre-empts the music";
 *   4. the FLUSH — the mixer byte is computed and the 13-byte shadow goes out at the chip.
 *
 * Nothing here holds a copy of the driver's data. Every table is bytes of `A\MODULE.BAK` in the
 * image, indexed the way the 68000 indexes it, so the module's own out-of-bounds indices (a byte
 * cursor that runs off the end of a 6-entry table into the code behind it, an instrument number
 * past the fourteenth) reproduce rather than being tidied away.
 *
 * D0's HIGH HALF IS AN UNWRITTEN ARGUMENT of every routine below the tick. The original indexes its
 * tables with `(pc,d0.w)` after loading only D0's low BYTE, so the high half is whatever the caller
 * left — and `sound_vbl_tick` opens `clr.w d0`, which is what makes it zero for the whole music
 * update (`moveq #$3,d0` in the per-frame update sign-extends to zero, so the invariant survives
 * three calls). The C models that zero rather than taking it as a parameter, and the battery enters
 * every one of these routines with D0 = 0 for the same reason.
 */
#include "machine.h"
#include "common.h"  /* SCC_TRUE, the one spelling of the `Scc` byte */
#include "os.h"
#include "psg.h"
#include "hw.h"

#include "globals.h"
#include "sound.h"

/* `ror.b #1,dn`: the bit rotated out is the old bit 0, and every use here tests exactly that bit
 * through the carry it leaves. */
static uint8_t rotate_right8(uint8_t value) {
    return (uint8_t)((value >> 1) | (value << 7));
}

/* `adda.w <word>,a3` — the module's internal references are 16-bit offsets from its base, added to
 * an address register and therefore SIGN-EXTENDED. Nothing shipped uses a negative one; the sign
 * extension is the instruction's, not a claim about the data. */
static uint32_t module_offset(uint16_t offset) {
    return addr_add(A_sound_module, sign_ext16(offset));
}

/* ================================================================================================
 * The sequencer — channel_sequencer_step @ 0x58b7a and the thirteen pattern commands
 * ============================================================================================= */

/* Pattern command 0x85 @ 0x58b0a: step the channel's sequence cursor to the next pattern.
 *
 * A sequence list is a run of words, each a pattern offset from the module base, ended by 0x0000 —
 * and the terminator does not stop the list, it RESTARTS it at index 0. That is how a tune loops,
 * and why `music_active` never goes clear for a looping one. Answers the new pattern cursor. */
static uint32_t seqcmd_next_pattern(uint8_t *image, uint32_t channel) {
    uint8_t *chan = image + channel;
    uint8_t cursor = chan[CHAN_SEQ_CURSOR];
    uint32_t list = module_offset(be16(chan + CHAN_SEQ_LIST_OFFSET));

    if (be16(image + list + cursor) == 0)
        cursor = 0;
    chan[CHAN_SEQ_CURSOR] = (uint8_t)(cursor + SEQ_LIST_ENTRY_BYTES);
    return module_offset(be16(image + list + cursor));
}

/* Pattern command 0x86 @ 0x58b44: vibrato, two operands. The limit is the depth DOUBLED as a byte,
 * and the sweep runs between 0 and it, so the effective swing is centred on limit/2. */
static void seqcmd_set_vibrato(uint8_t *image, uint32_t channel, uint32_t *cursor) {
    uint8_t *chan = image + channel;
    uint8_t depth;

    chan[CHAN_VIBRATO_SPEED] = image[(*cursor)++];
    depth = image[(*cursor)++];
    chan[CHAN_VIBRATO_CURRENT] = depth;
    chan[CHAN_VIBRATO_LIMIT] = (uint8_t)(depth + depth);
    chan[CHAN_FLAGS] |= CHAN_FLAG_VIBRATO;
}

/* Pattern command 0x82 @ 0x58b36: pitch slide, two operands. The accumulator gains `step` every
 * frame once the delay has run out, and the accumulator — not the step — is added to the period. */
static void seqcmd_set_pitch_slide(uint8_t *image, uint32_t channel, uint32_t *cursor) {
    uint8_t *chan = image + channel;

    chan[CHAN_SLIDE_STEP] = image[(*cursor)++];
    chan[CHAN_FLAGS] |= CHAN_FLAG_SLIDE;
    chan[CHAN_SLIDE_DELAY] = image[(*cursor)++];
}

/* The shared tail @ 0x58c14: arm the note's duration and store the pattern cursor back as a
 * 16-bit offset from the module base (`suba.l a3,a1 / move.w a1,2(a0)`). */
void sequencer_end_step(uint8_t *image, uint32_t channel, uint32_t cursor) {
    uint8_t *chan = image + channel;

    chan[CHAN_DURATION] = chan[CHAN_NOTE_LENGTH];
    wr16(chan + CHAN_PATTERN_OFFSET, (uint16_t)(cursor - A_sound_module));
}

/* The shared tail for a note byte @ 0x58be4.
 *
 * The envelope is reset only when the PREVIOUS note was non-negative: pattern command 0x8c (tie)
 * leaves 0xff there precisely so that this test fails and the running envelope carries over. */
void sequencer_start_note(uint8_t *image, uint32_t channel, uint8_t note, uint32_t cursor) {
    uint8_t *chan = image + channel;

    wr16(chan + CHAN_SLIDE_ACCUM, 0);
    if (!(chan[CHAN_NOTE] & CHAN_NOTE_TIED_BIT)) {
        chan[CHAN_ENV_BYTE] = 0;
        chan[CHAN_ENV_STEP] = 0;
    }
    chan[CHAN_NOTE] = note;
    chan[CHAN_ARP_CURSOR] = chan[CHAN_ARP_LOOP_POINT];
    chan[CHAN_OUT_FLAGS] = 0;
    if (note >= PATTERN_NOISE_NOTE_BASE) {
        chan[CHAN_OUT_FLAGS] = CHAN_OUT_NOISE_NOTE;
        image[A_sound_module + SND_NOISE_PERIOD_DEFAULT] =
            (uint8_t)(note - PATTERN_NOISE_NOTE_BASE);
    }
    sequencer_end_step(image, channel, cursor);
}

/* 1 when pattern command 0x88 ended the song, 0 otherwise — see `channel_sequencer_step`. */
#define SEQUENCER_SONG_ENDED 1
#define SEQUENCER_STEP_DONE  0

/* Consume pattern bytes from `cursor` until one ends the step @ 0x58b8a.
 *
 * Only a note byte, a rest and the end of the song end it; every other byte is a parameter or a
 * setting and parsing continues, so a note is preceded by however many bytes it needs.
 *
 * THE COMMAND DISPATCH READS ITS TARGET OUT OF THE IMAGE, exactly as `jmp (a2)` does: the byte
 * indexes a 13-word table of module-base offsets and the offset names the handler. Command bytes
 * 0x8d..0xaf index PAST that table into the code behind it and jump to whatever address the bytes
 * there make — data-dependent nonsense that no shipped pattern contains, and the one thing here
 * that has no C behaviour to reproduce. It is refused rather than guessed at.
 */
static int sequencer_fetch(uint8_t *image, uint32_t channel, uint32_t cursor) {
    uint8_t *base = image + A_sound_module;
    uint8_t *chan = image + channel;

    for (;;) {
        uint8_t byte = image[cursor++];

        if (byte >= PATTERN_ARP_LOOP_BASE) {
            if (byte >= PATTERN_NOTE_LENGTH_BASE)
                chan[CHAN_NOTE_LENGTH] = (uint8_t)(byte - PATTERN_NOTE_LENGTH_BASE + 1);
            else if (byte >= PATTERN_INSTRUMENT_BASE)
                chan[CHAN_INSTRUMENT] = (uint8_t)(byte - PATTERN_INSTRUMENT_BASE);
            else
                chan[CHAN_ARP_LOOP_POINT] =
                    base[SND_ARP_LOOP_POINT_TABLE + (byte - PATTERN_ARP_LOOP_BASE)];
            continue;
        }
        if (byte < PATTERN_COMMAND_BASE) {
            sequencer_start_note(image, channel, byte, cursor);
            return SEQUENCER_STEP_DONE;
        }

        switch (be16(base + SND_SEQ_COMMAND_TABLE
                     + (uint8_t)((byte - PATTERN_COMMAND_BASE) * 2))) {
        case SEQCMD_REST:                /* 0x80: the "finished" envelope byte for one note length */
            chan[CHAN_ENV_BYTE] = ENVELOPE_FINISHED;
            sequencer_end_step(image, channel, cursor);
            return SEQUENCER_STEP_DONE;
        case SEQCMD_END_OF_SONG:         /* 0x88 */
            sound_stop(image);
            return SEQUENCER_SONG_ENDED;
        case SEQCMD_CLEAR_FLAGS:         /* 0x81 */
            chan[CHAN_FLAGS] = 0;
            break;
        case SEQCMD_SET_PITCH_SLIDE:     /* 0x82 */
            seqcmd_set_pitch_slide(image, channel, &cursor);
            break;
        case SEQCMD_PORTAMENTO_DOWN:     /* 0x83 — falls into 0x84, so both bits go on */
            chan[CHAN_FLAGS] |= CHAN_FLAG_PORTAMENTO_DOWN | CHAN_FLAG_PORTAMENTO;
            break;
        case SEQCMD_PORTAMENTO_UP:       /* 0x84 */
            chan[CHAN_FLAGS] |= CHAN_FLAG_PORTAMENTO;
            break;
        case SEQCMD_NEXT_PATTERN:        /* 0x85 */
            cursor = seqcmd_next_pattern(image, channel);
            break;
        case SEQCMD_SET_VIBRATO:         /* 0x86 */
            seqcmd_set_vibrato(image, channel, &cursor);
            break;
        case SEQCMD_NOISE_ALTERNATE:     /* 0x87 */
            chan[CHAN_FLAGS] |= CHAN_FLAG_NOISE_ALTERNATE;
            break;
        case SEQCMD_SET_TRANSPOSE:       /* 0x89 */
            chan[CHAN_TRANSPOSE] = image[cursor++];
            break;
        case SEQCMD_NOISE_ONESHOT:       /* 0x8a — falls into 0x87 */
            chan[CHAN_FLAGS] |= CHAN_FLAG_NOISE_ONESHOT | CHAN_FLAG_NOISE_ALTERNATE;
            break;
        case SEQCMD_SET_NOISE_PERIOD:    /* 0x8b — falls into 0x8a, and so into 0x87 */
            base[SND_NOISE_PERIOD_ALT] = image[cursor++];
            chan[CHAN_FLAGS] |= CHAN_FLAG_NOISE_ONESHOT | CHAN_FLAG_NOISE_ALTERNATE;
            break;
        case SEQCMD_TIE:                 /* 0x8c */
            chan[CHAN_NOTE] = CHAN_NOTE_TIED;
            break;
        default:
            os_refused(0);
            return SEQUENCER_STEP_DONE;
        }
    }
}

/* One sequencer step for one channel @ 0x58b7a. `channel` is the struct's image address.
 *
 * While the note is still sounding only portamento runs — the note number itself is walked one
 * semitone a step, which is what makes it a portamento rather than a pitch slide. When the duration
 * expires the flag byte is cut back to vibrato alone and the pattern is read on.
 *
 * ANSWERS 1 WHEN THE SONG ENDED. The original has no such return value: pattern command 0x88
 * @ 0x58af0 REWRITES THIS ROUTINE'S OWN RETURN ADDRESS on the stack to 0x589d6, so its `rts` lands
 * past the rest of the tick's music update instead of back in it. A caller flag is the same control
 * flow spelt in C, and it is why `sound_vbl_tick` abandons the remaining channels AND the per-frame
 * update — not just the channel the command was on.
 */
int channel_sequencer_step(uint8_t *image, uint32_t channel) {
    uint8_t *chan = image + channel;

    chan[CHAN_DURATION] = (uint8_t)(chan[CHAN_DURATION] - 1);
    if (chan[CHAN_DURATION] != 0) {
        if (chan[CHAN_FLAGS] & CHAN_FLAG_PORTAMENTO)
            chan[CHAN_NOTE] = (uint8_t)(chan[CHAN_NOTE]
                                        + ((chan[CHAN_FLAGS] & CHAN_FLAG_PORTAMENTO_DOWN) ? -1 : 1));
        return SEQUENCER_STEP_DONE;
    }
    chan[CHAN_FLAGS] &= CHAN_FLAGS_KEPT_BY_A_NEW_STEP;
    return sequencer_fetch(image, channel, module_offset(be16(chan + CHAN_PATTERN_OFFSET)));
}

/* @ 0x58b76: `adda.w #24,a0` and fall into the routine above — the tick's way of walking to the
 * next channel, and the reason A0 comes back advanced. */
int channel_sequencer_next(uint8_t *image, uint32_t channel) {
    return channel_sequencer_step(image, channel + SND_CHANNEL_STRIDE);
}

/* ================================================================================================
 * The per-frame update — channel_frame_update @ 0x58c46
 * ============================================================================================= */

/* Advance this channel's volume envelope one frame and write the level to the shadow.
 *
 * An envelope byte is `frames-to-hold : PSG level`. A frame subtracts 0x10 from it; the BORROW off
 * the high nibble is what fetches the next byte of the instrument's envelope, and a byte at or
 * above 0xf0 is the end of the run.
 *
 * The level then passes through `(level | 0xf0) + 1 + master_volume`, KEPT ONLY IF THAT CARRIED.
 * With the shipped master volume of 0x0f every level carries through unchanged; a smaller one
 * clips the quiet steps to silence, which is the global attenuation knob the game never turns.
 */
static void advance_volume_envelope(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                                    uint32_t arp_table) {
    uint8_t *base = image + A_sound_module;
    uint8_t *chan = image + channel;
    uint8_t level;

    if (chan[CHAN_ENV_BYTE] < ENVELOPE_FINISHED) {
        int exhausted = byte_sub_extend(chan[CHAN_ENV_BYTE], ENVELOPE_FRAME_STEP);

        chan[CHAN_ENV_BYTE] = (uint8_t)(chan[CHAN_ENV_BYTE] - ENVELOPE_FRAME_STEP);
        if (exhausted) {
            uint8_t at = (uint8_t)(base[SND_INSTRUMENT_ENV_OFFSETS + chan[CHAN_INSTRUMENT]]
                                   + chan[CHAN_ENV_STEP]);
            chan[CHAN_ENV_STEP]++;
            /* `move.b (d0.w,a1,10),14(a0)` @ 0x58c66 — off the CALLER'S A1, not the module. */
            chan[CHAN_ENV_BYTE] = image[addr_add(arp_table, SND_ENV_TABLE_FROM_ARP_TABLE + at)];
        }
    }
    level = (uint8_t)((chan[CHAN_ENV_BYTE] | ENVELOPE_FINISHED) + 1);
    image[volume_shadow] = byte_add_extend(level, base[SND_MASTER_VOLUME])
                           ? (uint8_t)(level + base[SND_MASTER_VOLUME]) : 0;
}

/* Step the arpeggio cursor and answer the semitone offset it selects.
 *
 * The cursor is READ ONE AHEAD — the byte at `cursor + 1` is what this frame plays — and a byte
 * with bit 7 set is the last of the run: its low seven bits are still used, and the cursor snaps
 * back to the channel's loop point instead of advancing. A loop point whose next byte is already
 * terminated therefore yields a constant offset, which is how "no arpeggio" is spelt.
 */
static uint8_t step_arpeggio(uint8_t *image, uint32_t channel, uint32_t arp_table) {
    uint8_t *chan = image + channel;
    uint8_t cursor = (uint8_t)(chan[CHAN_ARP_CURSOR] + 1);
    uint8_t offset = image[addr_add(arp_table, cursor)];   /* `move.b (d1.w,a1),d0` @ 0x58c88 */

    if (offset & ARP_RUN_ENDS) {
        cursor = chan[CHAN_ARP_LOOP_POINT];
        offset &= (uint8_t)~ARP_RUN_ENDS;
    }
    chan[CHAN_ARP_CURSOR] = cursor;
    return offset;
}

/* Apply this channel's vibrato to `period` and answer the result.
 *
 * The sweep walks `current` between 0 and `limit` by `speed` and turns round at whichever end it is
 * heading for; the period is then displaced by `current - limit/2`, computed as a byte subtraction
 * whose borrow is what makes the displacement signed (`subi.w #$100,d1` before `add.w d0,d1`).
 */
static uint16_t apply_vibrato(uint8_t *image, uint32_t channel, uint16_t period) {
    uint8_t *chan = image + channel;
    uint8_t limit = chan[CHAN_VIBRATO_LIMIT];
    uint8_t current = chan[CHAN_VIBRATO_CURRENT];
    uint8_t centre;
    int turning;

    if (chan[CHAN_FLAGS] & CHAN_FLAG_VIBRATO_UP) {
        current = (uint8_t)(current + chan[CHAN_VIBRATO_SPEED]);
        turning = (current == limit);
    } else {
        current = (uint8_t)(current - chan[CHAN_VIBRATO_SPEED]);
        turning = (current == 0);
    }
    if (turning)
        chan[CHAN_FLAGS] ^= CHAN_FLAG_VIBRATO_UP;
    chan[CHAN_VIBRATO_CURRENT] = current;

    centre = (uint8_t)(limit >> 1);
    if (byte_sub_extend(current, centre))
        period = (uint16_t)(period - 0x100u);
    return (uint16_t)(period + (uint8_t)(current - centre));
}

/* Apply this channel's pitch slide to `period` and answer the result. The delay counts down first,
 * and only then does the accumulator start gaining the (signed) step each frame. */
static uint16_t apply_pitch_slide(uint8_t *image, uint32_t channel, uint16_t period) {
    uint8_t *chan = image + channel;

    if (chan[CHAN_SLIDE_DELAY] != 0) {
        chan[CHAN_SLIDE_DELAY]--;
        return period;
    }
    wr16(chan + CHAN_SLIDE_ACCUM,
         (uint16_t)(be16(chan + CHAN_SLIDE_ACCUM) + sign_ext8(chan[CHAN_SLIDE_STEP])));
    return (uint16_t)(period + be16(chan + CHAN_SLIDE_ACCUM));
}

/* Rebuild the channel's out-flags byte, which is the only thing the mixer reads.
 *
 * Bit 1 (a noise note is sounding) is read from the PREVIOUS frame's byte and written back into the
 * new one, so a noise note sustains until the next note-on clears it. Bit 0 — the mixer's own
 * "this channel is noise" — is set either by that, or on alternate frames while the alternating
 * noise flag is up, in which case the noise period comes from the pattern's own `noise_period_alt`.
 */
static void rebuild_out_flags(uint8_t *image, uint32_t channel) {
    uint8_t *base = image + A_sound_module;
    uint8_t *chan = image + channel;
    uint8_t out = (chan[CHAN_OUT_FLAGS] & CHAN_OUT_NOISE_NOTE)
                  ? (CHAN_OUT_NOISE | CHAN_OUT_NOISE_NOTE) : 0;

    if ((chan[CHAN_FLAGS] & CHAN_FLAG_NOISE_ALTERNATE)
            && (chan[CHAN_FLAGS] & CHAN_FLAG_FRAME_TOGGLE)) {
        base[SND_SHADOW_NOISE_PERIOD] = base[SND_NOISE_PERIOD_ALT];
        out |= CHAN_OUT_NOISE;
    }
    if (chan[CHAN_FLAGS] & CHAN_FLAG_NOISE_ONESHOT)
        chan[CHAN_FLAGS] &= (uint8_t)~CHAN_FLAG_NOISE_ALTERNATE;
    chan[CHAN_OUT_FLAGS] = out;
}

/* One frame of one channel @ 0x58c46: the volume envelope (written straight to `volume_shadow`),
 * the arpeggio, the note-period lookup, the vibrato and the pitch slide. Answers the tone period
 * the tick stores in the shadow — the original answers it in D1.
 *
 * The period index is `(note + arpeggio + transpose) * 2` computed as a BYTE, so a note that runs
 * past the 84-entry table wraps into it rather than reading on for ever; and the lookup is an image
 * read, so the entries beyond the 84th — which are the instructions behind the table — are what a
 * note above 83 really gets. Nothing shipped sends one.
 */
uint16_t channel_frame_update(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                              uint32_t arp_table) {
    uint8_t *base = image + A_sound_module;
    uint8_t *chan = image + channel;
    uint8_t index;
    uint16_t period;

    advance_volume_envelope(image, channel, volume_shadow, arp_table);

    index = (uint8_t)((step_arpeggio(image, channel, arp_table)
                       + chan[CHAN_NOTE] + chan[CHAN_TRANSPOSE]) * 2);
    period = be16(base + SND_NOTE_PERIOD_TABLE + index);
    if (chan[CHAN_FLAGS] & CHAN_FLAG_VIBRATO)
        period = apply_vibrato(image, channel, period);

    chan[CHAN_FLAGS] ^= CHAN_FLAG_FRAME_TOGGLE;
    if (chan[CHAN_FLAGS] & CHAN_FLAG_SLIDE)
        period = apply_pitch_slide(image, channel, period);

    rebuild_out_flags(image, channel);
    return period;
}

/* @ 0x58c42: `adda.w #24,a0` and fall into the routine above. */
uint16_t channel_frame_next(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                            uint32_t arp_table) {
    return channel_frame_update(image, channel + SND_CHANNEL_STRIDE, volume_shadow, arp_table);
}

/* ================================================================================================
 * The tick — sound_vbl_tick @ 0x5896a, and the two halves it is made of
 * ============================================================================================= */

/* Does the sequencer run this frame? @ 0x5897a.
 *
 * On a 50 Hz machine every frame is a tick. On a 60 Hz one the divider counts 6,5,...,1 and the
 * frame that reloads it to 6 is DROPPED — five ticks in six of 60 Hz is 50 sequencer steps a
 * second, so the music runs at the same tempo on both machines.
 */
static int music_frame_is_due(uint8_t *base) {
    if (hw_read8(OS_HW_SHIFTER_SYNC) & SHIFTER_SYNC_50HZ)
        return 1;
    base[SND_VBL_50HZ_DIVIDER] = (uint8_t)(base[SND_VBL_50HZ_DIVIDER] - 1);
    if (base[SND_VBL_50HZ_DIVIDER] != 0)
        return 1;
    base[SND_VBL_50HZ_DIVIDER] = VBL_50HZ_DIVIDER_RELOAD;
    return 0;
}

/* Run the sequencer over all three channels, once the tempo counter has expired @ 0x58992.
 * Answers 1 when a channel's pattern ended the song. */
static int run_the_sequencer(uint8_t *image) {
    uint32_t previous_channel = A_sound_module + SND_CHANNEL_A;
    unsigned rest;

    if (channel_sequencer_step(image, previous_channel))
        return SEQUENCER_SONG_ENDED;
    /* THE CALLEE STEPS THE CHANNEL. `channel_sequencer_next` is the original's `adda.w #24,a0` in
     * front of the same body (0x58b72), so what this hands it is the channel BEFORE the one it
     * runs — which is why the local lags the iteration and is named for what it holds. */
    for (rest = 1; rest < SND_CHANNELS; rest++) {
        if (channel_sequencer_next(image, previous_channel))
            return SEQUENCER_SONG_ENDED;
        previous_channel += SND_CHANNEL_STRIDE;
    }
    return SEQUENCER_STEP_DONE;
}

/* The music half of a tick @ 0x58992. The sequencer runs once every `tempo` frames; everything
 * after it runs on EVERY frame, which is what separates "the notes" from "the modulation".
 *
 * A song that ended under the sequencer abandons the per-frame update as well as the remaining
 * channels — that is the reach of command 0x88's rewritten return address (`channel_sequencer_step`)
 * and it is why the noise shadow below is not refreshed on such a frame either.
 */
static void music_update(uint8_t *image) {
    uint8_t *base = image + A_sound_module;
    uint32_t previous_channel = A_sound_module + SND_CHANNEL_A;
    uint32_t volume_shadow = A_sound_module + SND_SHADOW_VOLUME_A;
    uint32_t arp_table = A_sound_module + SND_ARP_SEQUENCE_TABLE;   /* `lea $59115(pc),a1` @ 0x589b8 */
    unsigned rest;

    base[SND_MUSIC_TEMPO_COUNTER] = (uint8_t)(base[SND_MUSIC_TEMPO_COUNTER] - 1);
    if (base[SND_MUSIC_TEMPO_COUNTER] == 0) {
        base[SND_MUSIC_TEMPO_COUNTER] = base[SND_MUSIC_TEMPO_RELOAD];
        if (run_the_sequencer(image))
            return;
    }

    base[SND_SHADOW_NOISE_PERIOD] = base[SND_NOISE_PERIOD_DEFAULT];
    wr16(base + SND_SHADOW_PERIOD_A,
         channel_frame_update(image, previous_channel, volume_shadow, arp_table));
    /* THE CALLEE STEPS THE CHANNEL, as in `run_the_sequencer` above: `channel_frame_next` is the
     * `adda.w #24,a0` @ 0x58c42 in front of `channel_frame_update`, so the local it is handed is
     * the channel BEFORE the one whose period comes back. */
    for (rest = 1; rest < SND_CHANNELS; rest++) {
        uint16_t period = channel_frame_next(image, previous_channel, volume_shadow + rest,
                                             arp_table);

        wr16(base + SND_SHADOW_PERIOD_A + rest * SND_SHADOW_PERIOD_BYTES, period);
        previous_channel += SND_CHANNEL_STRIDE;
    }
}

/* The sound-effect half of a tick @ 0x589de.
 *
 * The period sweeps by two independent amounts: a constant delta every tick, and — every
 * `alt_reload` ticks — one of two alternatives picked by the next bit of `alt_pattern`. A third
 * counter periodically snaps the period back to `period_reset`, which is what makes a sweep repeat.
 *
 * The last four statements are the pre-emption: channel C's volume shadow is forced to the chip's
 * hardware-envelope mode, its period shadow to the swept value, and its mixer bit to noise or tone
 * from the next bit of `noise_pattern` — over whatever the music just put there, and on channel C
 * only. THE NOISE PERIOD IS THE SWEPT PERIOD'S OWN LOW BYTE, so the noise tracks the sweep;
 * ../notes/sound_engine.md reads that source as `noise_period_default` and is wrong (the
 * instruction is `move.b $5895b(pc),6(a3)` @ 0x58a54, and 0x5895b is SND_SFX_PERIOD_CURRENT + 1).
 */
static void sfx_update(uint8_t *image) {
    uint8_t *base = image + A_sound_module;
    uint32_t channel_c_flags = A_sound_module + SND_CHANNEL_A
                               + (SND_CHANNELS - 1) * SND_CHANNEL_STRIDE + CHAN_OUT_FLAGS;
    uint8_t noise_pattern;

    base[SND_SFX_DURATION] = (uint8_t)(base[SND_SFX_DURATION] - 1);
    if (base[SND_SFX_DURATION] == 0) {
        base[SND_SHADOW_VOLUME_A + (SND_CHANNELS - 1)] = 0;
        base[SND_SFX_ACTIVE] = 0;
        return;
    }

    if (base[SND_SFX_ALT_RELOAD] != 0) {
        base[SND_SFX_ALT_COUNTER] = (uint8_t)(base[SND_SFX_ALT_COUNTER] - 1);
        if (base[SND_SFX_ALT_COUNTER] == 0) {
            uint32_t both = be32(base + SND_SFX_ALT_DELTA);
            uint8_t pattern = base[SND_SFX_ALT_PATTERN];
            uint16_t delta = (pattern & 1) ? (uint16_t)both : (uint16_t)(both >> 16);

            base[SND_SFX_ALT_COUNTER] = base[SND_SFX_ALT_RELOAD];
            base[SND_SFX_ALT_PATTERN] = rotate_right8(pattern);
            wr16(base + SND_SFX_PERIOD_CURRENT,
                 (uint16_t)(be16(base + SND_SFX_PERIOD_CURRENT) + delta));
        }
    }
    wr16(base + SND_SFX_PERIOD_CURRENT,
         (uint16_t)(be16(base + SND_SFX_PERIOD_CURRENT) + be16(base + SND_SFX_PERIOD_DELTA)));

    if (base[SND_SFX_RESET_RELOAD] != 0) {
        base[SND_SFX_RESET_COUNTER] = (uint8_t)(base[SND_SFX_RESET_COUNTER] - 1);
        if (base[SND_SFX_RESET_COUNTER] == 0) {
            base[SND_SFX_RESET_COUNTER] = base[SND_SFX_RESET_RELOAD];
            wr16(base + SND_SFX_PERIOD_CURRENT, be16(base + SND_SFX_PERIOD_RESET));
        }
    }

    base[SND_SHADOW_VOLUME_A + (SND_CHANNELS - 1)] = PSG_VOLUME_ENVELOPE_MODE;
    wr16(base + SND_SHADOW_PERIOD_C, be16(base + SND_SFX_PERIOD_CURRENT));
    image[channel_c_flags] &= (uint8_t)~CHAN_OUT_NOISE;
    noise_pattern = base[SND_SFX_NOISE_PATTERN];
    if (noise_pattern & 1) {
        /* `addq.b #1` on a byte whose bit 0 the line above cleared — a `bset #0` spelt as an add. */
        image[channel_c_flags] = (uint8_t)(image[channel_c_flags] + 1);
        base[SND_SHADOW_NOISE_PERIOD] = base[SND_SFX_PERIOD_CURRENT + 1];
    }
    base[SND_SFX_NOISE_PATTERN] = rotate_right8(noise_pattern);
}

/* Registers 1,0,3,2,5,4,6 then 8,9,10,12,11, one per shadow byte in shadow order. The mixer
 * (register 7) is not in the shadow: it is computed and pushed between the two runs. */
static const uint8_t SHADOW_FLUSH_REGS[SND_SHADOW_BYTES] = {1, 0, 3, 2, 5, 4, 6, 8, 9, 10, 12, 11};
#define SHADOW_MIXER_GOES_BEFORE 7u   /* ...before shadow byte 7, the first volume */

/* Compute the mixer byte and push the whole shadow at the chip @ 0x58a5e.
 *
 * The envelope shape is a ONE-SHOT LATCH: pushed only on the ticks its shadow byte is non-zero, and
 * zeroed by the push. A per-tick register vector must therefore carry "not written" as a value
 * distinct from "written 0" — which is why the flush is the last thing the tick does and why the
 * ledger, not the image, is the surface that sees it.
 */
static void flush_shadow_to_psg(uint8_t *image) {
    uint8_t *base = image + A_sound_module;
    static const uint8_t MIXER_EOR[SND_CHANNELS] = {PSG_MIXER_EOR_A, PSG_MIXER_EOR_B,
                                                    PSG_MIXER_EOR_C};
    uint8_t mixer = PSG_MIXER_TONES_ON;
    unsigned index;

    for (index = 0; index < SND_CHANNELS; index++) {
        uint32_t out_flags = A_sound_module + SND_CHANNEL_A + index * SND_CHANNEL_STRIDE
                             + CHAN_OUT_FLAGS;

        if (image[out_flags] & CHAN_OUT_NOISE)
            mixer ^= MIXER_EOR[index];
    }

    for (index = 0; index < SND_SHADOW_BYTES; index++) {
        if (index == SHADOW_MIXER_GOES_BEFORE)
            psg_port_write(PSG_REG_MIXER, mixer);
        psg_port_write(SHADOW_FLUSH_REGS[index], base[index]);
    }
    if (base[SND_SHADOW_ENV_SHAPE] != 0) {
        psg_port_write(PSG_REG_ENV_SHAPE, base[SND_SHADOW_ENV_SHAPE]);
        base[SND_SHADOW_ENV_SHAPE] = 0;
    }
}

/* One VBL @ 0x5896a — the module's only entry the game calls per frame, from `vbl_handler`. */
void sound_vbl_tick(uint8_t *image) {
    uint8_t *base = image + A_sound_module;

    if (base[SND_MUSIC_ACTIVE] && music_frame_is_due(base))
        music_update(image);
    if (base[SND_SFX_ACTIVE])
        sfx_update(image);
    flush_shadow_to_psg(image);
}

/* ================================================================================================
 * The three arming entries — sound_stop @ 0x58af6, sfx_start @ 0x58df0, music_start @ 0x58e2c
 * ============================================================================================= */

/* Silence the music @ 0x58af6: clear `music_active` and the three volume shadows, so the NEXT tick
 * is what actually quietens the chip. It leaves `sfx_active` alone — a running effect plays on. */
void sound_stop(uint8_t *image) {
    uint8_t *base = image + A_sound_module;

    base[SND_MUSIC_ACTIVE] = 0;
    base[SND_SHADOW_VOLUME_A] = 0;
    wr16(base + SND_SHADOW_VOLUME_A + 1, 0);   /* `clr.w`: volumes B and C in one instruction */
}

/* Arm sound effect `number` @ 0x58df0.
 *
 * The record's first seven words are copied straight into the parameter block, which is laid out in
 * the record's own order; the last two are unpacked into the envelope shadow and the duration.
 * `sfx_active` is cleared before the copy and set after it, so a tick that interrupted the copy
 * would see the block as idle rather than half-written.
 *
 * THE INDEX IS NOT BOUNDED. `ext.w` sign-extends the byte and `mulu.w` multiplies the whole word,
 * and only the product's LOW WORD reaches the address (`adda.w`) — so effect 0x80 reads 18 bytes
 * from below the table rather than above it. Nothing shipped asks for one: the six call sites pass
 * 6, 10, 5, 2, 5 and 11.
 */
void sfx_start(uint8_t *image, uint8_t number) {
    uint8_t *base = image + A_sound_module;
    uint32_t product = (sign_ext8(number) & 0xffffu) * SFX_RECORD_BYTES;
    const uint8_t *record = image + addr_add(A_sound_module + SND_SFX_TABLE,
                                             sign_ext16((uint16_t)product));
    unsigned word;

    base[SND_SFX_ACTIVE] = 0;
    for (word = 0; word < SFX_COPIED_WORDS; word++)
        wr16(base + SND_SFX_PERIOD_DELTA + word * sizeof(uint16_t),
             be16(record + word * sizeof(uint16_t)));
    wr16(base + SND_SHADOW_ENV_PERIOD, be16(record + SFX_ENV_PERIOD_WORD));
    wr16(base + SND_SHADOW_ENV_SHAPE, be16(record + SFX_ENV_SHAPE_WORD));
    /* Both countdowns armed from both reloads in one word move: the two are adjacent, in order. */
    wr16(base + SND_SFX_RESET_COUNTER, be16(base + SND_SFX_RESET_RELOAD));
    base[SND_SFX_ACTIVE] = SCC_TRUE;
}

/* Arm tune `number` @ 0x58e2c.
 *
 * Each of the three channels gets a note duration of 1 (so the first tick steps the sequencer
 * immediately), a cleared flag byte with the sequence cursor already past entry 0, no transpose,
 * its sequence-list offset, and that list's first pattern. `music_active` goes up last, for
 * `sfx_start`'s reason.
 *
 * THE RECORD INDEX IS A BYTE SHIFT over a sign-extended byte (`ext.w` then `asl.b #3`), so it wraps
 * at 256 while the high half keeps the sign — which is the whole of the bounds checking on a tune
 * number, and there are five tunes.
 */
void music_start(uint8_t *image, uint8_t number) {
    uint8_t *base = image + A_sound_module;
    uint16_t index = (uint16_t)((sign_ext8(number) & 0xff00u) | (uint8_t)(number * TUNE_RECORD_BYTES));
    const uint8_t *record = image + addr_add(A_sound_module + SND_TUNE_TABLE, sign_ext16(index));
    uint32_t channel = A_sound_module + SND_CHANNEL_A;
    unsigned index_of;

    base[SND_MUSIC_ACTIVE] = 0;
    base[SND_VBL_50HZ_DIVIDER] = VBL_50HZ_DIVIDER_RELOAD;
    base[SND_MUSIC_TEMPO_COUNTER] = 1;
    base[SND_MUSIC_TEMPO_RELOAD] = record[TUNE_TEMPO];

    for (index_of = 0; index_of < SND_CHANNELS; index_of++) {
        uint8_t *chan = image + channel;
        uint16_t list = be16(record + TUNE_SEQ_LIST + index_of * sizeof(uint16_t));

        chan[CHAN_DURATION] = 1;
        /* One `move.w #$2,(a0)` over the two adjacent bytes: no flags, and a sequence cursor that
         * already points past the entry whose pattern is being installed below. */
        wr16(chan + CHAN_FLAGS, SEQ_LIST_ENTRY_BYTES);
        chan[CHAN_TRANSPOSE] = 0;
        wr16(chan + CHAN_SEQ_LIST_OFFSET, list);
        wr16(chan + CHAN_PATTERN_OFFSET, be16(image + module_offset(list)));
        channel += SND_CHANNEL_STRIDE;
    }
    base[SND_MUSIC_ACTIVE] = SCC_TRUE;
}

/* ================================================================================================
 * The game side — the six wrappers in ../names.txt, and nothing else in FLYSHARK.PRG reaches the
 * chip: `$ff8800`/`$ff8802` appear nowhere in its 50,358 bytes.
 * ============================================================================================= */

void sfx_play_2(uint8_t *image)  { sfx_start(image, SFX_PLAY_2_NUMBER); }
void sfx_play_5(uint8_t *image)  { sfx_start(image, SFX_PLAY_5_NUMBER); }
void sfx_play_6(uint8_t *image)  { sfx_start(image, SFX_PLAY_6_NUMBER); }
void sfx_play_10(uint8_t *image) { sfx_start(image, SFX_PLAY_10_NUMBER); }

/* @ 0x12588. The tune number arrives as a WORD and the module takes only its low byte. */
void music_play(uint8_t *image, uint16_t tune) {
    music_start(image, (uint8_t)tune);
}

/* @ 0x12192. It loads `level_tune_id` into D0 before the call, which `sound_stop` ignores — and
 * then clears `music_active` a SECOND time, which `sound_stop` has already done. Both are the
 * original's, reproduced rather than tidied: the load is dead and the clear is redundant. */
void music_stop(uint8_t *image) {
    sound_stop(image);
    image[A_sound_module + SND_MUSIC_ACTIVE] = 0;
}

/* @ 0x1259c. The game's own use of "the tune has finished": restart the level theme once the
 * module's `music_active` has gone clear, unless the stage state has suspended the music. */
void music_restart_if_stopped(uint8_t *image) {
    if (be16(image + A_music_suspend_flag) != 0)
        return;
    if (image[A_sound_module + SND_MUSIC_ACTIVE] != 0)
        return;
    music_start(image, (uint8_t)be16(image + A_level_tune_id));
}

/* ================================================================================================
 * Glue — the register ABI, one line per routine
 * ============================================================================================= */

/* A0 in = the module base (`lea $58944.l,a0`), which every entry re-derives PC-relatively and none
 * of them reads; nothing is answered in a register. */
void g_sound_vbl_tick(uint8_t *image) { sound_vbl_tick(image); }
void g_sound_stop(uint8_t *image) { sound_stop(image); }

/* D0.b in = the effect / tune number; A0 in = the module base, as above. */
void g_sfx_start(uint8_t *image, uint32_t number_reg) { sfx_start(image, (uint8_t)number_reg); }
void g_music_start(uint8_t *image, uint32_t number_reg) { music_start(image, (uint8_t)number_reg); }

/* A0 in = the channel struct, A3 in = the module base, D0's high half in = 0 (file docstring); A0
 * comes back advanced by one channel out of `_next`, and the answer is the control flow described
 * at `channel_sequencer_step` rather than a register. */
void g_channel_sequencer_step(uint8_t *image, uint32_t channel) {
    channel_sequencer_step(image, channel);
}
void g_channel_sequencer_next(uint8_t *image, uint32_t channel) {
    channel_sequencer_next(image, channel);
}

/* A0 in = the channel struct, A1 in = the pattern cursor, A3 in = the module base, D0.b in = the
 * note byte, D0's high half in = 0. */
void g_sequencer_start_note(uint8_t *image, uint32_t channel, uint32_t note_reg,
                            uint32_t cursor_reg) {
    sequencer_start_note(image, channel, (uint8_t)note_reg, cursor_reg);
}

/* A0 in = the channel struct, A1 in = the pattern cursor, A3 in = the module base. */
void g_sequencer_end_step(uint8_t *image, uint32_t channel, uint32_t cursor_reg) {
    sequencer_end_step(image, channel, cursor_reg);
}

/* A0 in = the channel struct, A1 in = `arp_sequence_table`, A2 in = the volume shadow byte (and
 * out, post-incremented), A3 in = the module base, D0's high half in = 0; D1 out = the tone period,
 * which is the value these glues RETURN so a case can compare it with the oracle's D1. */
uint32_t g_channel_frame_update(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                                uint32_t arp_table) {
    return channel_frame_update(image, channel, volume_shadow, arp_table);
}
uint32_t g_channel_frame_next(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                              uint32_t arp_table) {
    return channel_frame_next(image, channel, volume_shadow, arp_table);
}

/* The wrappers take no arguments at all — each loads its own constant — bar `music_play`, whose
 * D0.w in is the tune number. */
void g_sfx_play_2(uint8_t *image)  { sfx_play_2(image); }
void g_sfx_play_5(uint8_t *image)  { sfx_play_5(image); }
void g_sfx_play_6(uint8_t *image)  { sfx_play_6(image); }
void g_sfx_play_10(uint8_t *image) { sfx_play_10(image); }
void g_music_play(uint8_t *image, uint32_t tune_reg) { music_play(image, (uint16_t)tune_reg); }
void g_music_stop(uint8_t *image) { music_stop(image); }
void g_music_restart_if_stopped(uint8_t *image) { music_restart_if_stopped(image); }
