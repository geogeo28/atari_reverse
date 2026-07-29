/* rng.c — Joust's pseudo-random source (rng_advance @ 0x105c2).
 *
 * There is no arithmetic generator: randomness is harvested from the program's own bytes. A
 * cursor (rng_ptr) walks the image two bytes at a time and callers read the word it points at
 * (spawn side, spawn x, explosion dither). This file advances the cursor; reading through it
 * belongs to the callers.
 */
#include "machine.h"
#include "addrs.h"
#include "joust.h"

/* Both constants below are relocated longwords in the shipped code, so the disassembly's raw
 * `#$7832` / `#$0` are the pre-relocation spellings — at the 0x10000 load base the cursor really
 * runs over [0x10000, 0x17832), i.e. the first ~30 KiB of the program's own text. */
#define RNG_PTR_STEP   2u          /* addq.l #2 — the cursor is read as words */
#define RNG_PTR_LIMIT  0x17832u    /* cmpi.l #$17832 — wrap once the cursor reaches here */
#define RNG_PTR_RESET  IMAGE_LOAD_BASE  /* move.l #$10000 — back to the start of the image */
#define RNG_MIX_MASK   0xfeu       /* andi.l #$fe — the caller's D0 nudges the restart point by an
                                    * even offset, so the cursor stays word-aligned */

/* rng_advance(mix = D0) — step the cursor, and on wrap restart it a little way in, at an offset
 * taken from the caller's D0. The compare is `cmpi.l` + `blt`, i.e. SIGNED: a cursor that has been
 * driven negative counts as below the limit and does not wrap.
 *
 * The original writes the stepped cursor before testing it and then overwrites it on the wrap
 * path, which is why both stores appear here. D0 itself is stacked across the wrap and restored
 * (see g_rng_advance) — callers rely on it surviving the call.
 */
void rng_advance(uint8_t *image, uint32_t mix) {
    uint32_t cursor = be32(image + A_rng_ptr) + RNG_PTR_STEP;
    wr32(image + A_rng_ptr, cursor);
    if ((int32_t)cursor < (int32_t)RNG_PTR_LIMIT) return;
    wr32(image + A_rng_ptr, RNG_PTR_RESET + (mix & RNG_MIX_MASK));
}

/* Register ABI: D0 in, and D0 back out unchanged (`move.l d0,-(a7)` … `move.l (a7)+,d0`). */
uint32_t g_rng_advance(uint8_t *image, uint32_t mix) {
    rng_advance(image, mix);
    return mix;
}
