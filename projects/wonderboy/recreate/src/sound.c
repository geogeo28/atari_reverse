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
#include "os.h"
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

/* `adda.l a3,An` over a SIGNED WORD — the module's own way of naming a place inside itself.
 *
 * Every table entry, every sequence offset and every `d16(a3)` operand is one of these, so the window
 * they can name is WB_SND_MODULE_BASE plus or minus 32 KiB. All of it is inside the loaded image,
 * which is why the reads that go through one need no bus guard where the reads through a stored
 * CURSOR (bus.h) do. */
static uint32_t module_address(uint32_t offset) {
    return addr_add(WB_SND_MODULE_BASE, sign_ext16(offset));
}

/* `add.w Dn,Dn / movea.w 0(An,Dn.w),An / adda.l a3,An` — one entry of an a3-relative WORD table,
 * indexed by a value the caller has already made a word.
 *
 * The ENTRY's own sign extension is load-bearing: `movea.w` widens it to 32 bits before the module
 * base is added, so an entry above $7fff names a place BELOW the base. */
static uint32_t module_table_entry(const uint8_t *image, uint32_t table, uint32_t index) {
    return module_address(be16(image + addr_add(table, index * WB_SND_TABLE_ENTRY_LEN)));
}

/* ...and the same table reached through an `ext.w Dn` first, which is how the two SFX tables are
 * indexed and how the pattern opcodes' two are NOT. A signed byte doubled still fits a signed word,
 * so the indexed operand's own `d0.w` extension is a no-op and only this one shows: an id of $80 or
 * more indexes the table BACKWARDS. */
static uint32_t module_pointer(const uint8_t *image, uint32_t table, uint32_t byte_index) {
    return module_table_entry(image, table, sign_ext8(byte_index));
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

/* ---- $18106 and $17fd4..$18105: the pattern stepper and its twenty-four opcodes -----------------
 *
 * ONE ROUTINE IN TWO PIECES. $18106's last instruction is the `jmp (a3,a2.w)` that enters a handler,
 * and every handler but one ends in a `bra` back INTO $18106's body — at $18116 to take another
 * pattern byte, or at $18148 to close the row. So the 306 bytes below the stepper and the 258 bytes
 * of the stepper are one flow graph, and the C spells it as a loop with a three-valued exit.
 *
 * WHAT THE SHIPPED DATA REACHES. A walk of all 106 patterns of all 17 songs (three channels, every
 * sequence entry) decodes ELEVEN of the twenty-four: $80 x658, $87 x95, $8f x88, $8a x51, $88 x48,
 * $92 x16, $8e x11, $89 x5, $81 x4, $93 x3, $82 x2 — and $87 plus $8e account for all 106 patterns
 * exactly, since every pattern ends in one or the other. The other thirteen are reachable only from a
 * seeded stream and test_sound.py says so per opcode.
 */

static uint32_t music_channel(unsigned channel) {
    return WB_SND_MUSIC_CHANNEL_STATE + channel * WB_SND_MUSIC_CHANNEL_LEN;
}

/* Where a pattern byte leaves the stepper's read loop. Three values because the handlers have three
 * endings, not because a status was wanted. */
typedef enum {
    PATTERN_READ_NEXT,      /* `bra $18116` — twenty-one of the twenty-four, and every note range */
    PATTERN_ROW_DONE,       /* `bra $18148` — opcodes $80 and $8f, which close the row with no note */
    PATTERN_SONG_ENDED,     /* $18014 — opcode $8e, which never comes back (sound.h) */
} pattern_exit;

/* $18188 — the OTHER path out of the stepper, taken while the row is still running: with the slide
 * flag set the current note walks by one, up or down as bit 7 says, and with it clear the routine
 * returns having done nothing but spend the countdown. */
static void apply_pitch_slide(uint8_t *image, uint32_t record) {
    uint8_t flags = image[record + WB_SND_CH_FLAGS];
    if (!(flags & WB_SND_CH_FLAG_SLIDE))
        return;
    if (flags & WB_SND_CH_FLAG_SLIDE_UP)
        image[record + WB_SND_CH_NOTE]++;
    else
        image[record + WB_SND_CH_NOTE]--;
}

/* $1811e — a note byte. It also RESTARTS THE INSTRUMENT: the envelope cursor goes back to its base
 * and the stream's first byte becomes both the held value and this tick's volume, which is why a
 * channel that has run its envelope out sounds again on the next note. */
static void start_note(uint8_t *image, uint32_t record, uint8_t note) {
    image[record + WB_SND_CH_NOTE] = note;

    /* $18122 — opcodes $8b/$8c arm this and $8a disarms it: with it set the NOISE period tracks the
     * note the channel is playing. */
    if (image[record + WB_SND_CH_NOISE_TRACKS_NOTE] != 0)
        image[WB_SND_NOISE_PERIOD_BASE] = note;

    uint32_t envelope = be32(image + record + WB_SND_CH_ENVELOPE_BASE);
    wr32(image + record + WB_SND_CH_ENVELOPE_CURSOR, envelope);
    /* The original reads `(a2)` twice, once into +40 and once into +30. The only store between the
     * two is the cursor's, so both reads see the same byte and one fetch says the same thing. */
    uint8_t first = bus_read_byte(image, envelope);
    image[record + WB_SND_CH_ENVELOPE_LAST] = first;
    image[record + WB_SND_CH_VOLUME] = first;
    image[record + WB_SND_CH_ENVELOPE_COUNT] = image[record + WB_SND_CH_ENVELOPE_SPEED];
    image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_ENVELOPE;
}

/* $18152 — the row's last act. A channel that has ASKED to yield (+45 non-zero, opcode $90) is handed
 * over only if every ARMED SFX channel has its noise turned off, and the ladder leaves the whole
 * routine the moment one does not: three `tst`/`btst` pairs whose only shared exit is the `rts`. */
static void take_yield_if_no_sfx_noise(uint8_t *image, uint32_t record) {
    if (image[record + WB_SND_CH_YIELD] == 0)
        return;
    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++) {
        uint32_t state = sfx_channel_state(channel);
        if (image[WB_SND_SFX_ACTIVE_FLAGS + channel] != 0
            && !(image[state + WB_SND_DESC_MIXER_BITS] & WB_SND_MIXER_NOISE_OFF))
            return;
    }
    image[record + WB_SND_CH_YIELD] = WB_SND_CH_YIELD_ASKED;
}

/* $18148 — reload the countdown, store the cursor the walk stopped at, and try the hand-over. */
static void end_row(uint8_t *image, uint32_t record, uint32_t cursor) {
    image[record + WB_SND_CH_DURATION] = image[record + WB_SND_CH_DURATION_RELOAD];
    wr32(image + record + WB_SND_CH_PATTERN_CURSOR, cursor);
    take_yield_if_no_sfx_noise(image, record);
}

/* $1801e — opcode $87, the sequence walk. The table is a run of a3-relative WORD pattern offsets
 * ending in 0000, and the terminator RESTARTS it at entry 0 with the index left at 2 — so every song
 * loops for ever unless a pattern executes $8e. The restarted read takes entry 0 itself, because the
 * reset reloads the table offset WITHOUT the index it had just added to it. */
static uint32_t next_pattern(uint8_t *image, uint32_t record) {
    uint16_t table = be16(image + record + WB_SND_CH_SEQUENCE_OFFSET);
    uint16_t index = be16(image + record + WB_SND_CH_SEQUENCE_INDEX);
    uint16_t entry = (uint16_t)(table + index);    /* `adda.w d0,a2`, then read back as `a2.w` */
    uint16_t next_index = (uint16_t)(index + WB_SND_TABLE_ENTRY_LEN);

    if (be16(image + module_address(entry)) == 0) {
        entry = table;
        next_index = WB_SND_TABLE_ENTRY_LEN;
    }
    /* THE RE-READ COMES FIRST. `movea.w 0(a3,a2.w),a1` at $18036 fetches the entry again and only
     * then does `move.w d0,10(a0)` at $1803c store the new index — so a sequence table that names the
     * index field itself reads the OLD index, not the one this call is about to leave. */
    uint32_t pattern = module_address(be16(image + module_address(entry)));
    wr16(image + record + WB_SND_CH_SEQUENCE_INDEX, next_index);
    return pattern;
}

/* $18044/$18064 — opcodes $8b and $8a, which are one body with two masks: this channel's own bits of
 * the noise ROUTING mask take the value `bits` selects and the rest of the mask survives, spelt as
 * the module's usual `eor/and/eor` merge. Each also writes the note-tracking flag, and the two write
 * it OPPOSITE ways round ($8b arms it, $8a clears it). */
static void merge_noise_route(uint8_t *image, uint32_t record, uint8_t bits, uint8_t tracks_note) {
    uint8_t mask = image[record + WB_SND_CH_MIXER_MASK];
    uint8_t routing = image[WB_SND_NOISE_ROUTE_MASK];
    image[WB_SND_NOISE_ROUTE_MASK] = (uint8_t)((((mask & bits) ^ routing) & mask) ^ routing);
    image[record + WB_SND_CH_NOISE_TRACKS_NOTE] = tracks_note;
}

/* $181de — opcode $d0+n. The envelope SPEED is the byte BEFORE the stream (`move.b -(a2),26(a0)`),
 * which is why the instrument data at $1ab24 is one byte longer than each envelope. */
static void select_instrument(uint8_t *image, uint32_t record, uint32_t index) {
    uint32_t stream = module_table_entry(image, WB_SND_INSTRUMENT_PTR_TABLE, index);
    wr32(image + record + WB_SND_CH_ENVELOPE_BASE, stream);
    image[record + WB_SND_CH_ENVELOPE_SPEED] = bus_read_byte(image, addr_add(stream, (uint32_t)-1));
}

/* $181bc — opcode $c0+n, and also $b8..$bf, whose decoded index is $f8..$ff: entry 248 to 255 of a
 * table that holds SIXTEEN, i.e. 232 to 239 entries past its end. Both the cursor and the loop base
 * take the stream, so a fresh arpeggio starts at its first entry. */
static void select_arpeggio(uint8_t *image, uint32_t record, uint32_t index) {
    uint32_t stream = module_table_entry(image, WB_SND_ARPEGGIO_PTR_TABLE, index);
    wr32(image + record + WB_SND_CH_ARPEGGIO_CURSOR, stream);
    wr32(image + record + WB_SND_CH_ARPEGGIO_BASE, stream);
}

/* One byte of operand, `move.b (a1)+,…`, out of the same dirty band every other cursor comes from. */
static uint8_t next_operand(const uint8_t *image, uint32_t *cursor) {
    uint8_t value = bus_read_byte(image, *cursor);
    *cursor = addr_add(*cursor, 1);
    return value;
}

/* $17fd4..$18105 — the twenty-four handlers, keyed by the jump table's own index (opcode - $80).
 *
 * The order below is the TABLE's, not the handlers' addresses', because the table is what selects
 * them and two of its entries share a target ($83 and $8d are one handler). The fall-throughs the
 * original gets for free are spelt out: $86 into $85's `bset`, and $88 into $82's control store.
 */
static pattern_exit run_pattern_opcode(uint8_t *image, uint32_t record, unsigned index,
                                       uint32_t *cursor, uint32_t sfx_channel) {
    switch (index) {
    case 0x00:  /* $80 — rest: silence this row and take no note */
        image[record + WB_SND_CH_VOLUME] = 0;
        return PATTERN_ROW_DONE;
    case 0x01:  /* $81 — portamento off */
        image[record + WB_SND_CH_PORTA_CONTROL] = 0;
        return PATTERN_READ_NEXT;
    case 0x02:  /* $82 — portamento on */
        image[record + WB_SND_CH_PORTA_CONTROL] = WB_SND_CH_PORTA_ENABLED;
        return PATTERN_READ_NEXT;
    case 0x03:  /* $83 */
    case 0x0d:  /* ...and $8d, the same handler through two table entries */
        image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_MARK;
        return PATTERN_READ_NEXT;
    case 0x04:  /* $84 — vibrato on, depth and speed */
        wr16(image + record + WB_SND_CH_VIBRATO_ACC, 0);
        image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_VIBRATO;
        image[record + WB_SND_CH_VIBRATO_DEPTH] = next_operand(image, cursor);
        image[record + WB_SND_CH_VIBRATO_SPEED] = next_operand(image, cursor);
        return PATTERN_READ_NEXT;
    case 0x06:  /* $86 — slide UP, which is $85 with bit 7 set first and then FALLS INTO it */
        image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_SLIDE_UP;
        /* fall through */
    case 0x05:  /* $85 — slide on */
        image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_SLIDE;
        return PATTERN_READ_NEXT;
    case 0x07:  /* $87 — advance to the next pattern in the sequence */
        *cursor = next_pattern(image, record);
        return PATTERN_READ_NEXT;
    case 0x08:  /* $88 — portamento step, then limit and current from ONE byte, then FALL INTO $82 */
        image[record + WB_SND_CH_PORTA_STEP] = next_operand(image, cursor);
        image[record + WB_SND_CH_PORTA_LIMIT] = bus_read_byte(image, *cursor);
        image[record + WB_SND_CH_PORTA_CURRENT] = next_operand(image, cursor);
        image[record + WB_SND_CH_PORTA_CONTROL] = WB_SND_CH_PORTA_ENABLED;
        return PATTERN_READ_NEXT;
    case 0x09:  /* $89 — global transpose, which is the module's and not the channel's */
        image[WB_SND_GLOBAL_TRANSPOSE] = next_operand(image, cursor);
        return PATTERN_READ_NEXT;
    case 0x0a:  /* $8a — route the NOISE enables, and stop tracking the note */
        merge_noise_route(image, record, WB_SND_MIXER_NOISE_BITS, 0);
        return PATTERN_READ_NEXT;
    case 0x0b:  /* $8b — route the TONE enables, and track the note */
        merge_noise_route(image, record, WB_SND_NOISE_TONE_BITS, WB_SND_CH_TRACKS_NOTE_SET);
        return PATTERN_READ_NEXT;
    case 0x0c: {  /* $8c — drop this channel out of the routing mask entirely. The mask is read
                   * TWICE because the original reads it twice: `and.b d2,d0` builds `~mask & routing`
                   * in a register and `and.b d0,2273(a3)` then ANDs that back into memory. The second
                   * read is algebraically redundant — `&= ~mask` would do — and is kept because
                   * these two instructions are what the entry pin asserts. */
        uint8_t mask = image[record + WB_SND_CH_MIXER_MASK];
        image[WB_SND_NOISE_ROUTE_MASK] &= (uint8_t)(~mask & image[WB_SND_NOISE_ROUTE_MASK]);
        image[record + WB_SND_CH_NOISE_TRACKS_NOTE] = WB_SND_CH_TRACKS_NOTE_SET;
        return PATTERN_READ_NEXT;
    }
    case 0x0e:  /* $8e — end of song. sound.h says why this is a status and not a `longjmp`. */
        return PATTERN_SONG_ENDED;
    case 0x0f:  /* $8f — run the envelope, and close the row without a note */
        image[record + WB_SND_CH_FLAGS] |= WB_SND_CH_FLAG_ENVELOPE;
        return PATTERN_ROW_DONE;
    case 0x10:  /* $90 — offer this channel to the SFX engine */
        image[record + WB_SND_CH_YIELD] = WB_SND_CH_YIELD_ASKED;
        return PATTERN_READ_NEXT;
    case 0x11:  /* $91 — take it back */
        image[record + WB_SND_CH_YIELD] = 0;
        return PATTERN_READ_NEXT;
    case 0x12:  /* $92 — detune */
        image[record + WB_SND_CH_DETUNE] = next_operand(image, cursor);
        return PATTERN_READ_NEXT;
    case 0x13:  /* $93 — a new sequence table, as two BYTES over the word, and back to its entry 0 */
        image[record + WB_SND_CH_SEQUENCE_OFFSET] = next_operand(image, cursor);
        image[record + WB_SND_CH_SEQUENCE_OFFSET + 1] = next_operand(image, cursor);
        wr16(image + record + WB_SND_CH_SEQUENCE_INDEX, 0);
        return PATTERN_READ_NEXT;
    case 0x14:  /* $94 — song speed, into both the field and its copy */
        image[WB_SND_SONG_SPEED] = next_operand(image, cursor);
        image[WB_SND_SONG_SPEED_COPY] = image[WB_SND_SONG_SPEED];
        return PATTERN_READ_NEXT;
    case 0x15:  /* $95 — fade rate, and the countdown reloaded from it */
        image[WB_SND_FADE_RATE] = next_operand(image, cursor);
        image[WB_SND_FADE_COUNTDOWN] = image[WB_SND_FADE_RATE];
        return PATTERN_READ_NEXT;
    case 0x16:  /* $96 — master volume */
        image[WB_SND_MASTER_VOLUME] = next_operand(image, cursor);
        return PATTERN_READ_NEXT;
    case 0x17:  /* $97 — trigger an SFX from the music stream, ON WHATEVER CHANNEL d1 HOLDS. The
                 * module's one latent defect, reproduced and not fixed: `move.b (a1)+,d0` is the
                 * whole of what it sets before calling stub +56 (sound.h; it occurs nowhere in the
                 * shipped data, which is why nothing has ever heard it). */
        snd_call_trigger_effect(image, next_operand(image, cursor), sfx_channel);
        return PATTERN_READ_NEXT;
    default:
        /* $98..$b7 — a table index past the twenty-four entries. The original reads a word of the
         * handlers' own instruction stream and `jmp`s through it, which no C can express.
         *
         * SO IT REFUSES RATHER THAN WALKING ON. `os_refused` tallies, and harness.differential()
         * raises on a non-zero candidate tally (os.h) — so a case that ever put such a byte in a
         * pattern is thrown away instead of being compared against a fall-through the original does
         * not do. Returning PATTERN_READ_NEXT here without the tally would be indistinguishable
         * from an ordinary opcode to every consumer that is not a differential. Nothing in the
         * shipped data reaches it: all 106 patterns decode with no opcode byte above $97. */
        return (pattern_exit)os_refused(PATTERN_READ_NEXT);
    }
}

/* $181a6 — the range decoder. NOT a mask: a `cmp.b` and then a chain of `addi.b`+`bcs`, each carry
 * saying the byte had reached that range's floor. The third add's carry is never tested, so the
 * arpeggio arm takes whatever is left — which is what sends $b8..$bf past the arpeggio table. */
static pattern_exit decode_pattern_byte(uint8_t *image, uint32_t record, uint8_t byte,
                                        uint32_t *cursor, uint32_t sfx_channel) {
    if (byte < WB_SND_PATTERN_CMD_LIMIT)
        return run_pattern_opcode(image, record, byte & WB_SND_PATTERN_CMD_INDEX_MASK, cursor,
                                  sfx_channel);

    unsigned carry;
    uint8_t decoded = add_byte(byte, WB_SND_PATTERN_DURATION_BIAS, &carry);
    if (carry) {
        image[record + WB_SND_CH_DURATION_RELOAD] = (uint8_t)(decoded + WB_SND_PATTERN_DURATION_MIN);
        return PATTERN_READ_NEXT;
    }
    decoded = add_byte(decoded, WB_SND_PATTERN_INSTRUMENT_BIAS, &carry);
    if (carry) {
        select_instrument(image, record, decoded);
        return PATTERN_READ_NEXT;
    }
    select_arpeggio(image, record, add_byte(decoded, WB_SND_PATTERN_ARPEGGIO_BIAS, &carry));
    return PATTERN_READ_NEXT;
}

snd_step_result snd_channel_step(uint8_t *image, uint32_t record, uint32_t sfx_channel) {
    /* $18106 — the countdown, and the test is on the RESULT of the decrement. */
    if (--image[record + WB_SND_CH_DURATION] != 0) {
        apply_pitch_slide(image, record);
        return SND_STEP_RETURNED;
    }

    image[record + WB_SND_CH_FLAGS] = 0;
    uint32_t cursor = be32(image + record + WB_SND_CH_PATTERN_CURSOR);
    for (;;) {
        uint8_t byte = bus_read_byte(image, cursor);
        cursor = addr_add(cursor, 1);
        if (byte < WB_SND_PATTERN_NOTE_LIMIT) {         /* `bmi` — $00..$7f is a note */
            start_note(image, record, byte);
            break;
        }
        pattern_exit exit = decode_pattern_byte(image, record, byte, &cursor, sfx_channel);
        if (exit == PATTERN_SONG_ENDED)
            return SND_STEP_SONG_ENDED;
        if (exit == PATTERN_ROW_DONE)
            break;
    }
    end_row(image, record, cursor);
    return SND_STEP_RETURNED;
}

/* ---- $17ca0: the tick body ----------------------------------------------------------------------
 *
 * Everything above this line is what it calls. The 44 bytes ABOVE it are the tempo selector, which
 * reads two hardware registers and is not ported (sound.h).
 */

/* `rol.b #n,Dn` — and for channel A, no instruction at all, which is a rotate by zero. The tick's
 * three `ori.b` immediates ($09, $12, $24) are one constant rotated by the channel number, and so is
 * the descriptor's own mixer byte on the mixdown path. */
static uint8_t rotate_left_byte(uint8_t value, unsigned count) {
    unsigned wide = (unsigned)value << count;
    return (uint8_t)(wide | (wide >> 8));
}

static uint8_t channel_mixer_bits(unsigned channel) {
    return rotate_left_byte(WB_SND_MIXER_CHANNEL_A_BITS, channel);
}

/* The PSG register NUMBER of a channel's fine tone period — which is also its offset into the
 * module's shadow, since the shadow is indexed BY register number. The chip write needs the number
 * and the mixdown needs the address, so the number is the primitive and the address is derived. */
static unsigned channel_tone_register(unsigned channel) {
    return WB_PSG_REG_TONE_A + channel * WB_PSG_REG_TONE_LEN;
}

static uint32_t shadow_tone_period(unsigned channel) {
    return WB_SND_PSG_SHADOW + channel_tone_register(channel);
}

/* $18016 — the tail both endings share. It clears "song loaded" and tail-jumps to stub +28, so the
 * stop's `rts` returns to the TICK's caller: nothing below the call site runs, chip write included.
 * Opcode $8e enters two bytes earlier only to unwind snd_channel_step's frame first. */
static void end_song(uint8_t *image) {
    image[WB_SND_SONG_LOADED] = WB_SND_SONG_UNLOADED;
    snd_stop(image);
}

/* $17cc2 — the fade. A rate of zero disables it; otherwise the countdown spends one tick per call and
 * the master volume one per countdown, and the song ENDS the moment the volume is spent — as it does
 * on entry if the volume is already zero, which is the arm a fade started at silence takes. */
static snd_step_result step_fade(uint8_t *image) {
    uint8_t rate = image[WB_SND_FADE_RATE];
    if (rate == 0)
        return SND_STEP_RETURNED;
    if (image[WB_SND_MASTER_VOLUME] == 0)
        return SND_STEP_SONG_ENDED;
    if (--image[WB_SND_FADE_COUNTDOWN] != 0)
        return SND_STEP_RETURNED;
    if (--image[WB_SND_MASTER_VOLUME] == 0)
        return SND_STEP_SONG_ENDED;
    image[WB_SND_FADE_COUNTDOWN] = rate;
    return SND_STEP_RETURNED;
}

/* $17cea — the ROW rate. The song-speed byte is a fraction of a row per tick: it accumulates in one
 * byte and all three channels step on its CARRY, so a speed of $30 steps every 5.3 ticks. */
static snd_step_result step_rows(uint8_t *image) {
    unsigned carry;
    image[WB_SND_SPEED_ACC] = add_byte(image[WB_SND_SPEED_ACC], image[WB_SND_SONG_SPEED], &carry);
    if (!carry)
        return SND_STEP_RETURNED;

    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++)
        if (snd_channel_step(image, music_channel(channel), SND_TRIGGER_CHANNEL_UNMODELLED)
            == SND_STEP_SONG_ENDED)
            return SND_STEP_SONG_ENDED;
    return SND_STEP_RETURNED;
}

/* $17d0c — turn each channel's record into the four PSG shadow bytes the chip write reads.
 *
 * THE PERIOD GOES THROUGH A SCRATCH WORD. The low byte is stored from the register and the HIGH byte
 * read back out of WB_SND_PERIOD_SCRATCH, which is the module's own way of splitting a 12-bit period
 * across two chip registers.
 *
 * THE MASTER VOLUME IS AN ATTENUATION. `eori.b #15` turns 0..15 into 15..0 and the channel's own
 * volume is reduced by it, with the borrow clamping at silence rather than wrapping. */
static void publish_channels(uint8_t *image) {
    image[WB_SND_MASTER_VOLUME] &= WB_SND_MASTER_VOLUME_MASK;

    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++) {
        /* d0/d1 on entry. Only d0's LOW WORD and d1's low byte are read back, and $18208 writes both
         * before the tick looks — so what the register carried in cannot reach the image. */
        snd_channel_mix mix = {0, 0};
        snd_channel_period_and_volume(image, music_channel(channel), &mix);

        wr16(image + WB_SND_PERIOD_SCRATCH, (uint16_t)mix.period);
        image[shadow_tone_period(channel)] = (uint8_t)mix.period;
        image[shadow_tone_period(channel) + WB_PSG_REG_TONE_COARSE] =
            image[WB_SND_PERIOD_SCRATCH];

        uint8_t attenuation = (uint8_t)(image[WB_SND_MASTER_VOLUME] ^ WB_SND_MASTER_VOLUME_FULL);
        uint8_t volume = (uint8_t)mix.volume;
        image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A + channel] =
            (uint8_t)(volume >= attenuation ? volume - attenuation : 0);
    }
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_NOISE_PERIOD] = image[WB_SND_NOISE_PERIOD_OUT];
}

/* $17d90 — the SFX mixdown: an armed SFX channel OVERRIDES the music's period, volume and mixer bits
 * in the shadow, so the chip write below sees the effect rather than the tune.
 *
 * CHANNEL A'S FLAG IS TESTED TWICE HERE TOO, exactly as it is in snd_sfx_tick: a NEGATIVE flag
 * abandons the whole tick — the mixer mask at the end and the CHIP WRITE included — where for B and
 * C a negative flag is merely non-zero and runs the arm. Returns whether the tick may go on.
 *
 * The three arms are one body bar the rotate: channel A's mixer byte is used as it stands and B's and
 * C's are rotated into their own bit positions, which is the same rotate the `ori` immediates are. */
static int mix_sfx_into_shadow(uint8_t *image) {
    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++) {
        uint8_t flag = image[WB_SND_SFX_ACTIVE_FLAGS + channel];
        if (flag == 0)
            continue;
        if (channel == WB_SND_CHANNEL_A && (int8_t)flag < 0)
            return 0;

        uint32_t mix_period = sfx_mix_period(channel);
        image[shadow_tone_period(channel)] = image[mix_period + WB_SND_MIX_PERIOD_LOW];
        image[shadow_tone_period(channel) + WB_PSG_REG_TONE_COARSE] = image[mix_period];

        uint8_t mixer_bits = image[sfx_channel_state(channel) + WB_SND_DESC_MIXER_BITS];
        if (!(mixer_bits & WB_SND_MIXER_NOISE_OFF))
            image[WB_SND_PSG_SHADOW + WB_PSG_REG_NOISE_PERIOD] = image[WB_SND_SFX_MIX_NOISE];

        image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER] |= channel_mixer_bits(channel);
        image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER] &= rotate_left_byte(mixer_bits, channel);
        image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A + channel] =
            image[WB_SND_SFX_MIX_VOLUME + channel];
    }
    /* $17e2e — and then the shadow keeps only the six enables, whatever the arms left above them. */
    image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER] &= WB_PSG_MIXER_ALL_OFF;
    return 1;
}

/* $17e34 — the chip write, and the only place in the tick that leaves the image.
 *
 * A LOCKED CHANNEL IS NOT WRITTEN AND DOES NOT VOTE. Its three registers are skipped and its bits
 * stay out of the mask the mixer merge uses, so whatever the chip already held in them survives —
 * which is the same read-modify-write snd_psg_silence does, over the same register 7 and for the same
 * reason: bits 6-7 are the port A/B direction lines. THE NOISE PERIOD needs ALL FOUR lock bytes clear
 * (`tst.l`), because one noise generator is shared by the three channels.
 *
 * The `move.w sr,d1 / move.w #$2700,sr … move.w d1,sr` around it has no C analogue and is not
 * reproduced; the oracle enters at $2700 already, so the only trace is the d1 the run leaves. */
static void write_shadow_to_psg(const uint8_t *image) {
    uint8_t owned = 0;

    if (be32(image + WB_SND_CHANNEL_LOCKS) == 0)
        psg_port_write(WB_PSG_REG_NOISE_PERIOD, image[WB_SND_PSG_SHADOW + WB_PSG_REG_NOISE_PERIOD]);

    for (unsigned channel = 0; channel < WB_SND_CHANNELS; channel++) {
        if (image[WB_SND_CHANNEL_LOCKS + channel] != 0)
            continue;
        unsigned fine = channel_tone_register(channel);
        psg_port_write(fine, image[WB_SND_PSG_SHADOW + fine]);
        psg_port_write(fine + WB_PSG_REG_TONE_COARSE,
                       image[WB_SND_PSG_SHADOW + fine + WB_PSG_REG_TONE_COARSE]);
        psg_port_write(WB_PSG_REG_VOLUME_A + channel,
                       image[WB_SND_PSG_SHADOW + WB_PSG_REG_VOLUME_A + channel]);
        owned |= channel_mixer_bits(channel);
    }

    uint8_t chip = psg_port_read(WB_PSG_REG_MIXER);
    uint8_t shadow = image[WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER];
    psg_port_write(WB_PSG_REG_MIXER, (uint8_t)((((chip ^ shadow) & owned) ^ chip)));
}

void snd_music_tick_body(uint8_t *image) {
    /* $17ca0 — the gate. The SFX flags are read as a LONG, so the unnamed fourth byte past the three
     * keeps the tick alive as surely as a real one does. */
    if (image[WB_SND_ENGINE_ENABLED] == WB_SND_ENGINE_DISABLED
        && be32(image + WB_SND_SFX_ACTIVE_FLAGS) == 0)
        return;

    /* $17cac — a fractional tick DROPPER and not a tempo scaler: on the accumulator's carry the whole
     * tick is abandoned, SFX engine and chip write included. */
    unsigned carry;
    image[WB_SND_TICK_DROP_ACC] = add_byte(image[WB_SND_TICK_DROP_ACC],
                                           image[WB_SND_TICK_DROP_VALUE], &carry);
    if (carry)
        return;

    snd_sfx_tick(image);

    /* $17cba — re-read, because snd_sfx_tick's end-of-effect arm can have cleared it. */
    if (image[WB_SND_ENGINE_ENABLED] != WB_SND_ENGINE_DISABLED) {
        if (step_fade(image) == SND_STEP_SONG_ENDED) {
            end_song(image);
            return;
        }
        /* $17ce4 — the noise period is reseeded from its base every tick, before the channels get a
         * chance to publish their own. */
        image[WB_SND_NOISE_PERIOD_OUT] = image[WB_SND_NOISE_PERIOD_BASE];
        if (step_rows(image) == SND_STEP_SONG_ENDED) {
            end_song(image);
            return;
        }
        publish_channels(image);
    }

    if (!mix_sfx_into_shadow(image))
        return;
    write_shadow_to_psg(image);
}
