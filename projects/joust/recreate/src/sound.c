/* sound.c — Joust's sound layer.
 *
 * Two independent paths onto the YM2149, and neither writes the chip through memory:
 *
 *   * play_sound (0x10a56) starts a canned effect by handing XBIOS Dosound one of sound_table's
 *     command lists. Which list it picks is the only observable choice it makes, so the kit's
 *     Dosound ledger — not the image diff — is what pins it (see include/sound.h).
 *   * snd_poll_done (0x10a8a) and snd_tone_sweep (0x1096e) talk to the chip register by register
 *     through XBIOS Giaccess, which the kit models as a 16-byte register file inside the image.
 *
 * All three go through os_giaccess()/g_dosound() from the kit rather than modelling the trap here,
 * which is what makes the oracle and this code agree on the trap's effect by construction.
 */
#include "machine.h"
#include "os.h"
#include "sound.h"

/* YM2149 registers, by the number XBIOS Giaccess selects them with; os.h supplies OS_PSG_WRITE,
 * the bit 7 that turns a Giaccess read into a write. */
#define PSG_TONE_A_FINE     0x0u
#define PSG_TONE_A_COARSE   0x1u
#define PSG_TONE_B_FINE     0x2u
#define PSG_TONE_B_COARSE   0x3u
#define PSG_MIXER           0x7u
#define PSG_VOLUME_A        0x8u
#define PSG_VOLUME_B        0x9u
#define PSG_VOLUME_C        0xau

/* The mixer's six enables are ACTIVE LOW: a set bit silences that tone or noise generator. */
#define PSG_MIXER_ALL_OFF   0x3fu     /* all three tones + all three noises silenced */
#define PSG_MIXER_TONE_A    (1u << 0)
#define PSG_MIXER_TONE_B    (1u << 1)

static uint16_t psg_read(uint8_t *image, unsigned reg) {
    return (uint16_t)os_giaccess(image, 0, (uint16_t)reg);   /* Giaccess(0, reg): bit 7 clear */
}

static void psg_write(uint8_t *image, unsigned reg, uint16_t data) {
    os_giaccess(image, data, (uint16_t)(OS_PSG_WRITE | reg));
}

/* ------------------------------------------------------------------------ play_sound @ 0x10a56 */

#define SOUND_TABLE_STRIDE  4u   /* lsl.l #2: the table holds longword command-list pointers */

/* play_sound(index.w @ 4(a7)) — start sound `index`, unless something louder is already playing.
 *
 * A LOWER index outranks a higher one and snd_priority holds what is playing (SND_PRIORITY_IDLE
 * when nothing is), so a request that does not beat it is dropped entirely. The routine saves and
 * restores every register, so it returns nothing at all — its whole effect is snd_priority plus
 * the off-image Dosound call.
 */
void play_sound(uint8_t *image, uint16_t index) {
    if ((int16_t)index > (int16_t)be16(image + A_snd_priority)) return;   /* cmp.w + bgt: signed */
    wr16(image + A_snd_priority, index);
    /* `move.l (0,a0,d0.w)`: only the LOW WORD of the scaled index reaches the table, SIGN-EXTENDED.
     * So an index selects an entry by its bottom 14 bits, and bit 13 flips the direction — 0x2000
     * indexes 0x8000 bytes BELOW sound_table, while 0x4000 reads the same entry 0 does. Nothing
     * the game passes gets near that; the shape is reproduced because the differential can reach
     * it. (The `clr.l d0` before the argument load is inert: neither the `cmp.w` nor this
     * word-sized index ever looks at D0's high half.) */
    uint32_t entry = A_sound_table + sign_ext16((uint32_t)index * SOUND_TABLE_STRIDE);
    g_dosound(image, be32(image + entry));
}

/* --------------------------------------------------------------------- snd_poll_done @ 0x10a8a */

/* snd_poll_done() — release the priority once the effect Dosound started has run out.
 *
 * TOS's Dosound engine clears the enables as a command list finishes, so a mixer with all six set
 * means silence. Called once a frame from _start; nothing else ever writes snd_priority back to
 * idle, so without this every later play_sound would be outranked forever.
 */
void snd_poll_done(uint8_t *image) {
    uint16_t mixer = psg_read(image, PSG_MIXER);
    if ((mixer & PSG_MIXER_ALL_OFF) != PSG_MIXER_ALL_OFF) return;  /* andi.b/cmpi.b: the low byte */
    wr16(image + A_snd_priority, SND_PRIORITY_IDLE);
}

/* -------------------------------------------------------------------- snd_tone_sweep @ 0x1096e */

#define SWEEP_VOLUME_START  0x0fu    /* full amplitude, stepped down by 1 per outer pass */
#define SWEEP_PITCH_START   0x100u   /* tone period, stepped down by SWEEP_PITCH_STEP per inner pass */
#define SWEEP_PITCH_STEP    2u
#define SWEEP_TONE_B_COARSE 0x0cu    /* channel B's coarse period, fixed: it drones under channel A */

/* snd_tone_sweep() — the two-channel descending sweep played at the end of init_video.
 *
 * Both loops are `subq.w` + `bge`, i.e. SIGNED and testing the value AFTER the step, so each runs
 * one pass more than its start value suggests: the pitch loop ends on the pass at 0, and the volume
 * loop likewise. There is no delay anywhere — the sweep's speed is just the cost of 8 XBIOS traps
 * per inner pass, which is why it audibly differs between an ST and a faster machine.
 *
 * Both counters live in the image (snd_sweep_pitch / snd_sweep_volume) rather than in registers,
 * and the original re-reads each one for every use. Reading each once per pass is exact: the only
 * thing the pass writes is the modeled PSG register file at os.h's OS_PSG_REGS (0x610), which
 * cannot alias two globals up at 0x10d48.
 */
void snd_tone_sweep(uint8_t *image) {
    psg_write(image, PSG_VOLUME_C, 0);            /* channel C is not part of the sweep: mute it */
    wr16(image + A_snd_sweep_volume, SWEEP_VOLUME_START);

    int16_t volume_left, pitch_left;              /* each counter as its own `bge` sees it */
    do {
        wr16(image + A_snd_sweep_pitch, SWEEP_PITCH_START);
        do {
            uint16_t volume = be16(image + A_snd_sweep_volume);
            uint16_t pitch = be16(image + A_snd_sweep_pitch);

            psg_write(image, PSG_TONE_A_COARSE, 0);
            psg_write(image, PSG_TONE_B_COARSE, SWEEP_TONE_B_COARSE);
            psg_write(image, PSG_VOLUME_A, volume);
            psg_write(image, PSG_VOLUME_B, volume);
            psg_write(image, PSG_TONE_A_FINE, pitch);
            psg_write(image, PSG_TONE_B_FINE, pitch);

            /* Read-modify-write the mixer every pass: silence all six generators, then re-enable
             * the two tones. The two bits above the six enables are whatever was there — the
             * `or.l`/`bclr` pair never touches them — so a staged port-direction setting survives
             * the whole sweep. */
            uint16_t mixer = psg_read(image, PSG_MIXER);
            mixer = (uint16_t)((mixer | PSG_MIXER_ALL_OFF) & ~(PSG_MIXER_TONE_A | PSG_MIXER_TONE_B));
            psg_write(image, PSG_MIXER, mixer);

            pitch_left = (int16_t)(pitch - SWEEP_PITCH_STEP);
            wr16(image + A_snd_sweep_pitch, (uint16_t)pitch_left);
        } while (pitch_left >= 0);

        volume_left = (int16_t)(be16(image + A_snd_sweep_volume) - 1u);
        wr16(image + A_snd_sweep_volume, (uint16_t)volume_left);
    } while (volume_left >= 0);
}

/* ---- glue: the I/O contract the differential harness drives (see test/test_sound.py) ---- */

void g_play_sound(uint8_t *image, uint32_t index) {
    play_sound(image, (uint16_t)index);
}

void g_snd_poll_done(uint8_t *image) {
    snd_poll_done(image);
}

void g_snd_tone_sweep(uint8_t *image) {
    snd_tone_sweep(image);
}
