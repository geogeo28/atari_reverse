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
#include "machine.h"
#include "psg.h"
#include "sound.h"
#include "wonderboy.h"

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
    uint32_t state = WB_SND_SFX_STATE + channel * WB_SND_SFX_STATE_LEN;
    uint32_t mix_period = WB_SND_SFX_MIX_PERIOD + channel * WB_SND_SFX_MIX_PERIOD_LEN;
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
