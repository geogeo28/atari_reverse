/* sound.c — the tune/SFX table lookup (sound_lookup_tune @ 0x16b32).
 *
 * The one leaf of the sound driver: turn a sound number into a pointer to that tune's byte stream.
 * Both tables are PC-relative data inside the text segment — the offset list at `A_tune_index` and
 * the streams themselves from `A_tune_data` on.
 *
 * Its caller `sound_start` @ 0x16ac8 is not ported yet, but it is NOT blocked: its body touches no
 * hardware and issues no trap (movem / bsr here / `cmpi.b #$fa,(a1)` / pick one of three voice-slot
 * structures at 0x16eaa, 0x16edc, 0x16f0e / stores / rts). The YM2149 writes people associate with
 * it are in the routines below it, at 0x16b82 and 0x16b9e. See STATUS.md.
 */
#include "machine.h"
#include "sound.h"

#define TUNE_NUMBER_MASK 0xffu  /* `andi.w #$ff,d1` — only the low byte of the number is used */
#define TUNE_ENTRY_BYTES 2u     /* `lsl.w #1,d1` — one 16-bit offset per tune */

/* BYTE-SWAPPED, AND DELIBERATELY SO. The high byte comes from entry+1 and the low byte from
 * entry+0 (`move.b 1(a1),d1 / lsl.w #8,d1 / move.b (a1),d1`), so the table holds its offsets
 * LITTLE-endian on a big-endian machine — names.txt reads it as data carried over from the Z80
 * original, a heritage gotcha docs/sound.md now covers. Reading it the 68000's own way would give
 * nonsense: the shipped table reads 0x019a, 0x023d, 0x02da, ... this way round and 0x9a01, 0x3d02,
 * 0xda02, ... the other.
 *
 * `number` is the whole D1 word because that is what the mask sees; the high half of D1 is never
 * touched by any step of the routine.
 *
 * HOW LONG THE TABLE IS, is not a fact this routine states, and it does not bound the number:
 * names.txt reads 45 entries, and the 400-byte gap to A_tune_data leaves room for 200 words, but
 * the mask admits all 256 numbers and the routine resolves every one. So the differential drives
 * all 256 and the routine is verified over its whole input range. */
static uint16_t tune_offset(const uint8_t *image, uint16_t number) {
    uint32_t entry = A_tune_index + (number & TUNE_NUMBER_MASK) * TUNE_ENTRY_BYTES;

    return (uint16_t)((image[entry + 1] << 8) | image[entry]);
}

/* `adda.w d1,a1` SIGN-EXTENDS, and that arm is live rather than theoretical: 52 of the 256 words a
 * number can reach have bit 15 set (the first is number 45, 0x80c8), so those resolve BELOW the
 * data base — 0xf2b0 for that one, under the load base entirely. Dropping the sign extension turns
 * test_every_tune_number red at 45, so this is pinned, not merely transcribed. */
uint32_t sound_lookup_tune(const uint8_t *image, uint16_t number) {
    return addr_add(A_tune_data, sign_ext16(tune_offset(image, number)));
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
