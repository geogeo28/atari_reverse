/* sound.c — $1a48a, the sound module's SFX trigger, $17b14, the stub that calls it, and the STOP
 * CHAIN below them ($17f24 -> $1aaea -> $17f30).
 *
 * THE MODULE IS PC-RELATIVE, so every address it names is an offset from `lea $1738c(pc),a3` rather
 * than an absolute operand. In the image the harness loads that base IS WB_SND_MODULE_BASE, so this
 * file addresses the module the way the rest of the reconstruction addresses the game — through
 * wonderboy.h — and the PC-relative form leaves no trace in the C. What it does leave is a trace in
 * the TABLES: their entries are a3-relative WORDS, so `module_pointer` below is the module's own way
 * of naming a place inside itself, and every one of them is sign-extended.
 *
 * ONE BODY, THREE ARMS. $1a48a's three channel arms ($1a494, $1a504, $1a56e) are the same fifteen
 * instructions with the channel's own offsets, and all four blocks they address step by a constant —
 * so `trigger_channel` is written once and indexed. That is a claim about the encodings, not a
 * convenience: test_sound.py's entry pin assembles all three arms from the same base-plus-stride and
 * fails on the bytes if any one of them steps differently.
 *
 * NO BOUNDS CHECK ANYWHERE. The id is a signed byte, doubled, used as a word index into the pointer
 * table; the volume-stream index the descriptor carries is treated the same way. Both can therefore
 * read outside their table, and a negative one reads BELOW it. Reproduced, because it is what the
 * instructions do — and reachable, since the pattern opcode at $17fd4 calls the stub without ever
 * setting d1 (../names.txt). The window is bounded whatever the id: a table entry is a word added to
 * a 32-bit base, so the descriptor always lands within 32 KiB either side of the module.
 */
#include "bus.h"
#include "machine.h"
#include "psg.h"
#include "sound.h"
#include "wonderboy.h"

/* WHERE ONE SFX CHANNEL'S BLOCKS ARE. Four of the module's per-channel blocks step by a constant
 * stride, so both the trigger and the tick derive their addresses the same way — the two spelt these
 * verbatim before they met here. The active flag and the mix volume are `base + channel` and need no
 * helper; these two are the ones with a stride other than one. */
static uint32_t sfx_channel_state(unsigned channel) {
    return WB_SND_SFX_STATE + channel * WB_SND_SFX_STATE_LEN;
}

static uint32_t sfx_mix_period(unsigned channel) {
    return WB_SND_SFX_MIX_PERIOD + channel * WB_SND_SFX_MIX_PERIOD_LEN;
}

/* `movea.w 0(An,Dn.w),An / adda.l a3,An` — one entry of an a3-relative WORD table.
 *
 * TWO SIGN EXTENSIONS, both load-bearing. `ext.w d0 / add.w d0,d0` makes the index a signed BYTE
 * doubled, so an id of $80 or more indexes the table BACKWARDS; and `movea.w` sign-extends the ENTRY
 * itself into 32 bits before the module base is added to it, so an entry above $7fff names a place
 * below the base. Either read as unsigned would give a different address for half the values a
 * caller can pass. (The `d0.w` of the indexed operand is sign-extended too, but a signed byte
 * doubled already fits a signed word, so spelling that one would be a no-op.) */
static uint32_t module_pointer(const uint8_t *image, uint32_t table, uint32_t byte_index) {
    uint32_t entry = addr_add(table, sign_ext8(byte_index) * WB_SND_TABLE_ENTRY_LEN);
    return addr_add(WB_SND_MODULE_BASE, sign_ext16(be16(image + entry)));
}

/* Arm the channel's SFX state from descriptor `effect_id`, exactly as one of $1a48a's three arms
 * does. `channel` is 0/1/2, not the caller's d1 — the mapping is snd_trigger_effect's. */
static void trigger_channel(uint8_t *image, uint32_t effect_id, unsigned channel) {
    uint32_t active = WB_SND_SFX_ACTIVE_FLAGS + channel;
    uint32_t state = sfx_channel_state(channel);
    uint32_t mix_period = sfx_mix_period(channel);
    uint32_t mix_volume = WB_SND_SFX_MIX_VOLUME + channel;

    /* `sf 2254(a3)` — the channel is disarmed before the state is rebuilt and re-armed at the end,
     * so the flag ends at the same value either way. NOTHING A MEMORY DIFFERENTIAL CAN SEE: deleting
     * this store leaves the final image identical, and a mutation that does exactly that survives
     * the suite (../STATUS.md). What it is FOR is the interrupt the harness does not model — the
     * per-VBL tick polls this byte, and between these two stores the state is half built. */
    image[active] = 0;

    /* `move.b (a0)+,(a1)+ / dbf` — a forward BYTE copy, one byte at a time, NOT a block move. The
     * difference is observable and pinned: three of the pointer table's entries put a descriptor
     * just BELOW channel C's state and overlapping it, so the loop re-reads bytes it has already
     * written and the record propagates where a `memmove` would leave the pre-run ones
     * (test_sound.py's PROPAGATING_IDS). The destination is fixed whatever the id selects. The
     * LENGTH is only half pinned: a copy one byte SHORT reddens, but one byte long does not, because
     * the store below overwrites state+14 unconditionally (../STATUS.md). */
    uint32_t descriptor = module_pointer(image, WB_SND_SFX_PTR_TABLE, effect_id);
    for (unsigned offset = 0; offset < WB_SND_SFX_DESCRIPTOR_LEN; offset++)
        image[state + offset] = image[descriptor + offset];

    /* Every field below is read back out of the COPY (`move.b $1aa7d(pc),...` names the channel
     * state's own bytes), not out of the descriptor the copy came from. */
    image[state + WB_SND_STATE_PERIOD_COUNT] = image[state + WB_SND_DESC_PERIOD_STEP];
    wr16(image + mix_period, be16(image + state + WB_SND_DESC_TONE_PERIOD));
    if (!(image[state + WB_SND_DESC_MIXER_BITS] & WB_SND_MIXER_NOISE_OFF))
        image[WB_SND_SFX_MIX_NOISE] = image[state + WB_SND_DESC_NOISE_PERIOD];
    image[state + WB_SND_STATE_VOLUME_COUNT] = image[state + WB_SND_DESC_VOLUME_STEP];
    image[state + WB_SND_STATE_SECOND_COUNT] = image[state + WB_SND_DESC_SECOND_RELOAD];

    uint32_t stream = module_pointer(image, WB_SND_SFX_VOLUME_PTRS,
                                     image[state + WB_SND_DESC_VOLUME_INDEX]);
    wr32(image + state + WB_SND_STATE_STREAM_BASE, stream);
    wr32(image + state + WB_SND_STATE_STREAM_CURSOR, stream);
    image[mix_volume] = image[stream];

    image[active] = WB_SND_SFX_ACTIVE;
}

/* The two `cmp.b #n,d1` that pick the arm. Only d1's LOW BYTE is compared, and the third arm has no
 * test of its own at all — anything that is not 0 or 1 is channel C. */
#define SND_CHANNEL_SELECT_MASK 0xffu

void snd_trigger_effect(uint8_t *image, uint32_t effect_id, uint32_t channel) {
    uint32_t selector = channel & SND_CHANNEL_SELECT_MASK;
    trigger_channel(image, effect_id,
                    selector < WB_SND_CHANNELS ? (unsigned)selector : WB_SND_CHANNELS - 1u);
}

void snd_call_trigger_effect(uint8_t *image, uint32_t effect_id, uint32_t channel) {
    /* The `movem` pair either side of this call has no C analogue; see sound.h. */
    snd_trigger_effect(image, effect_id, channel);
}

/* ---- the stop chain: $17f24 -> $1aaea -> $17f30 -----------------------------------------------
 *
 * Three routines, joined by `bra.w` rather than by `bsr` — so to a caller reaching stub +28 there is
 * one stop, and to a reader there are three entry points into one tail. Each is a function here
 * because each is separately reachable: +28 is snd_stop, +70 is snd_stop_all_sfx, and $17f30 is what
 * both of them end in.
 */

/* $17f30. THE READ-MODIFY-WRITE IS THE POINT. `ori.b #$3f,d1` sets the six tone/noise enable bits
 * (active low) and leaves bits 6-7 — the chip's port A/B I/O DIRECTION — exactly as it found them,
 * which is why the value the chip held on entry has to be an input of the run rather than something
 * this code computes. A port that ignored the read-back would write $3f, flip port A to input and
 * float the floppy drive-select lines; it is also the kit's own mutant class, since `0 | $3f` and
 * `read | $3f` agree whenever the read is fabricated as 0 (TRAP_MODEL.md, "Phase 6"). */
void snd_psg_silence(void) {
    psg_port_write(WB_PSG_REG_MIXER,
                   (uint8_t)(psg_port_read(WB_PSG_REG_MIXER) | WB_PSG_MIXER_ALL_OFF));
    psg_port_write(WB_PSG_REG_VOLUME_A, WB_PSG_VOLUME_SILENT);
    psg_port_write(WB_PSG_REG_VOLUME_B, WB_PSG_VOLUME_SILENT);
    psg_port_write(WB_PSG_REG_VOLUME_C, WB_PSG_VOLUME_SILENT);
}

/* $1aaea. The four shadow stores mirror snd_psg_silence's four chip accesses — same registers, same
 * values, `clr.w` covering the two adjacent volume shadows in one instruction — because the shadow
 * is indexed by register number (wonderboy.h). The mixer shadow takes the mask FLAT rather than
 * `ori`ed: the module's own copy has no port-direction bits to preserve. */
void snd_stop_all_sfx(uint8_t *image) {
    /* `clr.l 2254(a3)` — ONE longword store, which is why the unnamed fourth byte past the three
     * channel flags goes too (WB_SND_SFX_ACTIVE_FLAGS_LEN is 4, not 3). */
    wr32(image + WB_SND_SFX_ACTIVE_FLAGS, 0);

    image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER] = WB_PSG_MIXER_ALL_OFF;
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A] = WB_PSG_VOLUME_SILENT;
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_B] = WB_PSG_VOLUME_SILENT;
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_C] = WB_PSG_VOLUME_SILENT;

    snd_psg_silence();
}

/* $17f24. */
void snd_stop(uint8_t *image) {
    image[WB_SND_ENGINE_ENABLED] = WB_SND_ENGINE_DISABLED;
    snd_stop_all_sfx(image);
}

/* ---- the tick tier: $1aaca, $1a5da and $18208 --------------------------------------------------
 *
 * THE IMAGE IS DIRTY WHERE ALL THREE OF THESE LIVE. Everything they read out of $17bc6..$17c71,
 * $18352..$1836a, $1aa7c..$1aac9 and $1aae6..$1aae9 is state the .PRG ships holding residue from a
 * run at another load base, so the values below come from the caller's own seeding and never from
 * the image as loaded (sound.h says so at the interface, ../notes/sound_module_recon.md §6 proves
 * it). That is also why every pointer these routines follow goes through bus.h's
 * `bus_read_byte`: an envelope cursor, an arpeggio cursor and a volume-stream cursor all come out
 * of those bands, and only the READ is masked — a cursor STORED back keeps all 32 bits, because
 * `move.l a2,d16(a3)` does.
 */

/* `roxl.w <ea>` — a word in memory rotated left THROUGH the X flag. Returns the bit that left the
 * top, which is the X the next one takes. Spelt as a helper because the order of the module's two
 * calls is the whole mechanism: the LOW word first, so its top bit feeds the high word's bottom. */
static unsigned roxl_word(uint8_t *image, uint32_t at, unsigned extend) {
    uint16_t value = be16(image + at);
    wr16(image + at, (uint16_t)((value << 1) | extend));
    return value >> 15;
}

uint8_t snd_prng_step(uint8_t *image) {
    /* `andi.b #$48 / addi.b #$38 / lsl.b #2` — the mask keeps bits 3 and 6 and the bias is what
     * carries bit 3 into bit 6, so the bit the shift pushes into X is bit 3 XOR bit 6. */
    uint8_t taps = (uint8_t)((image[WB_SND_PRNG_STATE] & WB_SND_PRNG_TAP_MASK)
                             + WB_SND_PRNG_TAP_BIAS);
    unsigned extend = (taps >> WB_SND_PRNG_FEEDBACK_BIT) & 1u;

    extend = roxl_word(image, WB_SND_PRNG_STATE + WB_SND_PRNG_LOW_WORD, extend);
    roxl_word(image, WB_SND_PRNG_STATE, extend);

    /* `move.b $1aae6(pc),d0` again — the state's NEW top byte, and a byte move, so the rest of d0
     * is the caller's (sound.h). */
    return image[WB_SND_PRNG_STATE];
}

/* ---- $1a5da: the SFX tick, one arm per channel -------------------------------------------------
 *
 * ONE BODY, THREE ARMS, exactly as snd_trigger_effect above. $1a602/$1a6bc/$1a776 are the same
 * thirty-odd instructions over four base-plus-stride blocks (the 26-byte state, the active flag, the
 * mix period word and the mix volume byte) plus two more that step by ONE: the PSG shadow volume the
 * end-of-effect arm clears, and — the surprise — the PRNG byte, so channel A takes
 * WB_SND_PRNG_STATE+0, B +1 and C +2 out of the same four-byte state.
 */

/* $1a66a..$1a683 — the constant pitch slide, applied only on the ticks the secondary counter lets
 * through. `tst.b / beq / bpl`: zero does nothing, a POSITIVE direction subtracts and a negative one
 * adds, so a descriptor byte of $ff slides the period UP. */
static void sfx_slide_period(uint8_t *image, uint32_t state, uint32_t mix_period) {
    int8_t direction = (int8_t)image[state + WB_SND_DESC_SLIDE_DIRECTION];
    if (direction == 0)
        return;

    uint16_t amount = be16(image + state + WB_SND_DESC_SLIDE_AMOUNT);
    uint16_t period = be16(image + mix_period);
    wr16(image + mix_period, (uint16_t)(direction < 0 ? period + amount : period - amount));
}

/* $1a62e..$1a654 — rewrite the channel's mix period from the descriptor's own tone period plus a
 * delta byte, which is the PRNG's when the descriptor asks for it (ids 12, 20 and 21 do).
 *
 * THE DELTA IS ADDED TO BOTH HALVES. `add.b d0,lo` then `addx.b d0,hi` puts the SAME byte into the
 * high half as well, carry included, so the effect on the 16-bit period is `+ delta * 257` and not
 * `+ delta`. With the PRNG flag clear the delta is 0 and the period is copied verbatim. */
static void sfx_reload_period(uint8_t *image, uint32_t state, uint32_t mix_period,
                              unsigned channel) {
    image[state + WB_SND_DESC_SLIDE_COUNT]--;
    image[state + WB_SND_STATE_PERIOD_COUNT] = image[state + WB_SND_DESC_PERIOD_STEP];

    uint8_t delta = image[state + WB_SND_DESC_USE_PRNG];
    if (delta != 0)
        delta = image[WB_SND_PRNG_STATE + channel];

    unsigned low = (unsigned)image[state + WB_SND_DESC_TONE_PERIOD + WB_SND_MIX_PERIOD_LOW] + delta;
    image[mix_period + WB_SND_MIX_PERIOD_LOW] = (uint8_t)low;
    image[mix_period] = (uint8_t)(image[state + WB_SND_DESC_TONE_PERIOD] + delta + (low >> 8));
}

/* $1a61c..$1a690 — everything between the duration decrement and the volume stream: the pitch
 * reload, the period countdown, the secondary counter that gates the slide, and the noise byte.
 *
 * THE ONE EARLY EXIT ($1a62c's `beq`) SKIPS ALL OF IT, countdown included — a channel whose period
 * countdown has expired with neither a sustain flag nor a slide step left goes straight to the
 * volume stream. */
static void sfx_step_period(uint8_t *image, uint32_t state, uint32_t mix_period, unsigned channel) {
    if (image[state + WB_SND_STATE_PERIOD_COUNT] == 0) {
        if (image[state + WB_SND_DESC_SUSTAIN] == 0 && image[state + WB_SND_DESC_SLIDE_COUNT] == 0)
            return;
        sfx_reload_period(image, state, mix_period, channel);
    }
    image[state + WB_SND_STATE_PERIOD_COUNT]--;

    /* $1a65a — a reload of 0 disables the counter entirely and the slide then runs every tick. */
    uint8_t second_reload = image[state + WB_SND_DESC_SECOND_RELOAD];
    int slide_due = 1;
    if (second_reload != 0) {
        slide_due = (--image[state + WB_SND_STATE_SECOND_COUNT] == 0);
        if (slide_due)
            image[state + WB_SND_STATE_SECOND_COUNT] = second_reload;
    }
    if (slide_due)
        sfx_slide_period(image, state, mix_period);

    /* $1a684 — the noise period is the LOW byte of whichever channel wrote it last, and all three
     * arms write the one shared byte (WB_SND_SFX_MIX_NOISE). */
    if (!(image[state + WB_SND_DESC_MIXER_BITS] & WB_SND_MIXER_NOISE_OFF))
        image[WB_SND_SFX_MIX_NOISE] = image[mix_period + WB_SND_MIX_PERIOD_LOW];
}

/* $1a692..$1a6ba — one step of the channel's volume stream, taken when the volume countdown runs
 * out. A byte from $00 to $7f is the volume; $80 loops back to the stream's base and takes the byte
 * there; ANY OTHER negative byte holds — the cursor is not advanced and the volume is not written,
 * so nothing at all is stored. */
static void sfx_step_volume(uint8_t *image, uint32_t state, unsigned channel) {
    if (--image[state + WB_SND_STATE_VOLUME_COUNT] != 0)
        return;
    image[state + WB_SND_STATE_VOLUME_COUNT] = image[state + WB_SND_DESC_VOLUME_STEP];

    uint32_t cursor = be32(image + state + WB_SND_STATE_STREAM_CURSOR);
    uint8_t value = bus_read_byte(image, cursor);
    cursor = addr_add(cursor, 1);
    if ((int8_t)value < 0) {
        if (value != WB_SND_VOLUME_STREAM_LOOP)
            return;
        cursor = be32(image + state + WB_SND_STATE_STREAM_BASE);
        value = bus_read_byte(image, cursor);
        cursor = addr_add(cursor, 1);
    }
    wr32(image + state + WB_SND_STATE_STREAM_CURSOR, cursor);
    image[WB_SND_SFX_MIX_VOLUME + channel] = value;
}

/* One arm. `channel` is 0/1/2 and every block it addresses is a base plus that channel's stride. */
static void sfx_tick_channel(uint8_t *image, unsigned channel) {
    uint32_t state = sfx_channel_state(channel);
    uint32_t mix_period = sfx_mix_period(channel);

    /* $1a602 — the effect is over only when BOTH its duration and its sustain flag have run out,
     * and then the channel disarms itself and silences the module's own PSG volume shadow (NOT the
     * SFX mix volume: the store is a3+4046, which is WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A). */
    if (image[state + WB_SND_DESC_DURATION] == 0 && image[state + WB_SND_DESC_SUSTAIN] == 0) {
        image[WB_SND_SFX_ACTIVE_FLAGS + channel] = WB_SND_SFX_INACTIVE;
        image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A + channel] = WB_PSG_VOLUME_SILENT;
        return;
    }
    image[state + WB_SND_DESC_DURATION]--;

    sfx_step_period(image, state, mix_period, channel);
    sfx_step_volume(image, state, channel);
}

void snd_sfx_tick(uint8_t *image) {
    snd_prng_step(image);

    /* `tst.b 2254(a3) / bmi` — channel A's flag alone can end the WHOLE tick, before B and C are
     * even looked at. Below that the three are one test each. */
    if ((int8_t)image[WB_SND_SFX_ACTIVE_FLAGS + WB_SND_CHANNEL_A] < 0)
        return;

    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++)
        if (image[WB_SND_SFX_ACTIVE_FLAGS + channel] != 0)
            sfx_tick_channel(image, channel);
}

/* ---- $18208: one music channel's period and volume ---------------------------------------------- */

/* `addi.b #imm,Dn` — the wrapped byte sum, and the CARRY OUT the `bcc`/`bcs` after it reads. Both
 * of the portamento's octave steps are this instruction, and the second is a loop condition. */
static uint8_t add_byte(uint8_t value, uint8_t addend, unsigned *carry) {
    unsigned sum = (unsigned)value + addend;
    *carry = sum >> 8;
    return (uint8_t)sum;
}

/* $18214..$18236 — one step of the volume envelope.
 *
 * `subq.b #1 / bcc` means the borrow is the trigger, so the envelope advances on the tick AFTER the
 * countdown reaches zero. The next byte is PEEKED through `move.b 1(a2),d0` before the cursor moves
 * and a negative one ends the envelope: neither the cursor nor the last value changes, and the
 * volume holds. The volume is written from the last value either way. */
static void step_envelope(uint8_t *image, uint32_t record) {
    uint8_t count = image[record + WB_SND_CH_ENVELOPE_COUNT];
    image[record + WB_SND_CH_ENVELOPE_COUNT] = (uint8_t)(count - 1);
    if (count == 0) {
        image[record + WB_SND_CH_ENVELOPE_COUNT] = image[record + WB_SND_CH_ENVELOPE_SPEED];

        uint32_t cursor = be32(image + record + WB_SND_CH_ENVELOPE_CURSOR);
        uint8_t next = bus_read_byte(image, addr_add(cursor, 1));
        if ((int8_t)next >= 0) {
            wr32(image + record + WB_SND_CH_ENVELOPE_CURSOR, addr_add(cursor, 1));
            image[record + WB_SND_CH_ENVELOPE_LAST] = next;
        }
    }
    image[record + WB_SND_CH_VOLUME] = image[record + WB_SND_CH_ENVELOPE_LAST];
}

/* $18244..$18258 — one byte of the arpeggio stream. `move.b (a1)+,d1 / bclr #7,d1 / beq`: the cursor
 * has already advanced when the terminator is tested, and on a terminator it is replaced by the
 * stream's base rather than by base + 1 — so the entry that ends the stream is also played. */
static uint8_t next_arpeggio_step(uint8_t *image, uint32_t record) {
    uint32_t cursor = be32(image + record + WB_SND_CH_ARPEGGIO_CURSOR);
    uint8_t step = bus_read_byte(image, cursor);
    cursor = addr_add(cursor, 1);
    if (step & WB_SND_ARPEGGIO_END) {
        step &= (uint8_t)~WB_SND_ARPEGGIO_END;
        cursor = be32(image + record + WB_SND_CH_ARPEGGIO_BASE);
    }
    wr32(image + record + WB_SND_CH_ARPEGGIO_CURSOR, cursor);
    return step;
}

/* $18272..$182cc — the portamento's contribution to the period, in the note table's own units.
 *
 * Register map: note_index = d5 (the note's BYTE offset into the period table), limit = d4,
 * current = d1, control = d6, flags = d7. `limit` is the record's field DOUBLED (`lsl.b #1`) for
 * the compare and halved again (`lsr.b #1`) for the subtraction, so a field with its top bit set
 * loses it — reproduced rather than tidied.
 *
 * The value returned is d1's whole low word, which the caller both adds to the period AND carries
 * out as the second byte of its own d1. */
static uint16_t portamento_offset(uint8_t *image, uint32_t record, unsigned note_index,
                                  uint8_t flags, uint8_t control) {
    uint8_t limit = (uint8_t)(image[record + WB_SND_CH_PORTA_LIMIT] << 1);
    uint8_t current = image[record + WB_SND_CH_PORTA_CURRENT];
    uint8_t step = image[record + WB_SND_CH_PORTA_STEP];

    /* `btst #7,d6 / beq / btst #0,d7 / bne $182b4` — a HELD portamento skips its step on the ticks
     * whose WB_SND_CH_FLAG_TOGGLE is set, so it advances every other call. */
    int stepping = !((control & WB_SND_CH_PORTA_HELD) && (flags & WB_SND_CH_FLAG_TOGGLE));
    if (stepping) {
        if (control & WB_SND_CH_PORTA_AT_LIMIT) {
            current = (uint8_t)(current + step);
            if (current >= limit) {          /* `cmp.b d4,d1 / bcs` — an UNSIGNED compare */
                image[record + WB_SND_CH_PORTA_CONTROL] &= (uint8_t)~WB_SND_CH_PORTA_AT_LIMIT;
                current = limit;
            }
        } else if (current < step) {         /* `sub.b / bcc` — the borrow is the underflow */
            image[record + WB_SND_CH_PORTA_CONTROL] |= WB_SND_CH_PORTA_AT_LIMIT;
            current = 0;
        } else {
            current = (uint8_t)(current - step);
        }
        image[record + WB_SND_CH_PORTA_CURRENT] = current;
    }

    /* $182b4 — the offset is `current - limit/2` as a SIGNED word: `sub.b` leaves a byte and the
     * `subi.w #256` on its borrow is what sign-extends it. */
    uint8_t half_limit = (uint8_t)(limit >> 1);
    uint16_t offset = (uint16_t)(uint8_t)(current - half_limit);
    if (current < half_limit)
        offset = (uint16_t)(offset - 0x100u);

    /* $182be — one doubling per octave the note sits below the table's reference index, because the
     * period table halves once per octave. Both steps are `addi.b`, so the condition is an ADD's
     * carry out of the byte and not a subtraction's borrow. */
    unsigned carry;
    uint8_t octave = add_byte((uint8_t)note_index, WB_SND_PORTA_OCTAVE_BIAS, &carry);
    while (!carry) {
        offset = (uint16_t)(offset << 1);
        octave = add_byte(octave, WB_SND_PORTA_OCTAVE_STEP, &carry);
    }
    return offset;
}

/* $182d6..$182fe — one step of the vibrato.
 *
 * THE SPEED BYTE IS A DELAY, NOT A DIVIDER, and the original is what says so: the tick that takes
 * the countdown to zero does NOT store the zero back, so the field stays at its last non-zero value
 * and the accumulator then steps on every call from then on. Reproduced. */
static uint16_t vibrato_step(uint8_t *image, uint32_t record) {
    uint8_t speed = (uint8_t)(image[record + WB_SND_CH_VIBRATO_SPEED] - 1);
    if (speed != 0) {
        image[record + WB_SND_CH_VIBRATO_SPEED] = speed;
        return 0;
    }

    /* `clr.w d6 / move.b depth,d6 / bpl / addi.w #-256,d6` — a byte sign-extended into a word. */
    int8_t depth = (int8_t)image[record + WB_SND_CH_VIBRATO_DEPTH];
    uint16_t accumulator = (uint16_t)(be16(image + record + WB_SND_CH_VIBRATO_ACC) + (int16_t)depth);
    wr16(image + record + WB_SND_CH_VIBRATO_ACC, accumulator);
    return accumulator;
}

/* $18300..$1834a — publish the noise period and merge this channel's bits into the module's shadow
 * of the PSG mixer. These are the two MODULE GLOBALS the pass writes, which is what makes it more
 * than a function of the record it is handed. */
static void publish_mixer_and_noise(uint8_t *image, uint32_t record, uint8_t flags) {
    /* `eori.b #$ff,d7 / andi.b #3,d7 / bne` — the arm runs only when BOTH of the two low flag bits
     * are SET, one of them being the bit the caller has just toggled. */
    uint8_t routing = image[WB_SND_NOISE_ROUTE_MASK];
    if ((flags & WB_SND_CH_NOISE_ROUTE_FLAGS) == WB_SND_CH_NOISE_ROUTE_FLAGS) {
        image[WB_SND_NOISE_PERIOD_OUT] =
            (uint8_t)(image[WB_SND_NOISE_PERIOD_BASE] ^ WB_SND_NOISE_PERIOD_XOR);
        routing = WB_SND_NOISE_TONE_BITS;
    }

    /* `eor.b d2,d3 / and.b 47(a0),d3 / eor.b d2,d3` — the shadow's own bits survive everywhere this
     * channel's constant mask does not select. */
    uint8_t mask = image[record + WB_SND_CH_MIXER_MASK];
    uint8_t shadow = image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER];
    uint8_t merged = (uint8_t)(((routing ^ shadow) & mask) ^ shadow);

    /* $1832a — a channel handed to the SFX engine gives up its three noise enables for this tick,
     * and the yield flag's top bit is cleared so the hand-over happens once. */
    if (image[record + WB_SND_CH_YIELD] & WB_SND_CH_YIELD_TAKEN) {
        image[record + WB_SND_CH_YIELD] &= WB_SND_CH_YIELD_MASK;
        merged &= (uint8_t)~(mask & WB_SND_MIXER_NOISE_BITS);
        image[WB_SND_NOISE_PERIOD_OUT] = WB_SND_NOISE_ROUTE_YIELDED;
    }
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER] = merged;
}

void snd_channel_period_and_volume(uint8_t *image, uint32_t record, snd_channel_mix *mix) {
    uint8_t flags = image[record + WB_SND_CH_FLAGS];               /* d7 */

    if (flags & WB_SND_CH_FLAG_ENVELOPE)
        step_envelope(image, record);

    /* $18238 — the note, the global transpose, the channel's detune and the arpeggio step, all
     * added as BYTES, and then doubled as a byte again: the table index is (note * 2) & $ff, so it
     * never leaves the 256 bytes at WB_SND_NOTE_PERIOD_TABLE however large the note is (sound.h). */
    uint8_t note = (uint8_t)(image[record + WB_SND_CH_NOTE] + image[WB_SND_GLOBAL_TRANSPOSE]
                             + image[record + WB_SND_CH_DETUNE]);
    note = (uint8_t)(note + next_arpeggio_step(image, record));

    unsigned note_index = (uint8_t)(note << 1);
    uint16_t period = be16(image + WB_SND_NOTE_PERIOD_TABLE + note_index);
    uint16_t scratch = (uint16_t)note_index;                        /* d1 */

    uint8_t control = image[record + WB_SND_CH_PORTA_CONTROL];     /* d6 */
    if (control & WB_SND_CH_PORTA_ENABLED) {
        scratch = portamento_offset(image, record, note_index, flags, control);
        period = (uint16_t)(period + scratch);
    }

    flags ^= WB_SND_CH_FLAG_TOGGLE;
    image[record + WB_SND_CH_FLAGS] = flags;

    if (flags & WB_SND_CH_FLAG_VIBRATO)
        period = (uint16_t)(period + vibrato_step(image, record));

    publish_mixer_and_noise(image, record, flags);

    mix->period = set_low_word(mix->period, period);
    /* `move.b 30(a0),d1` over a register whose high half `moveq #0,d1` cleared — so the volume's own
     * byte is the low one, the portamento's leftover is the second, and the rest is zero. */
    mix->volume = set_low_byte(scratch, image[record + WB_SND_CH_VOLUME]);
}
