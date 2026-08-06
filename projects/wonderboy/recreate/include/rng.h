/* rng.h — the game's pseudo-random generator ($68c6) and the per-stage draw over it ($e1f0);
 * src/rng.c.
 *
 * WHY THESE TWO ARE ONE MODULE. `rng_next` has ten `bsr` callers spread across the whole program and
 * belongs to no subsystem; `stage_random_kind8` is a draw over it, and one of only two routines in
 * the image whose entire body is "advance the generator and index a table with the result". Putting
 * the draw beside the generator is what lets the battery pin the two together — the draw's result is
 * the generator's low three bits and nothing else, so a case that got the generator wrong and the
 * table right would still be red.
 *
 * THE GENERATOR IS DEGENERATE UNDER THE ORACLE, and this is the one thing to know before trusting a
 * green result here. Its entropy term is `$ff8209 ^ $b39a` — the shifter's video-address counter
 * XOR the frame tick — and `$ff8209` is off the image, so BOTH cores are served 0 and the term
 * collapses to the frame tick alone. Nothing about the reconstruction is wrong; what is gone is the
 * game's randomness, which no differential can put back. ../names.txt's `cmt 0x68c6` and
 * ../STATUS.md register it as a T3-DATA false green, and test/test_rng.py's module docstring states
 * it again where a reader of the cases will meet it.
 *
 * REGISTER ARGUMENTS, as everywhere else here: `rng_next`'s result is d0 and its entropy read is a
 * `clr.w d0` rather than a `moveq #0,d0`, so the CALLER'S HIGH WORD survives the call and comes back
 * in the result. That is why the generator takes one — see below.
 */
#ifndef WONDERBOY_RNG_H
#define WONDERBOY_RNG_H

#include <stdint.h>

/* $68c6 — advance WB_RNG_COUNTER_A/_B/_C and return
 * `(video counter ^ WB_FRAME_TICK_B39A) + A + B + C` in d0's low word.
 *
 * `entry_d0` is the caller's d0: `clr.w d0` clears the low half only, so d0's HIGH half is never
 * written and the result carries the caller's own bits there. Ten `bsr` callers ($2f50, $2fa4,
 * $3284, $3aee, $4180, $4398, $4556, $4cc6, and $e1e2/$e20a inside the two draws). It also leaves
 * WB_FRAME_TICK_B39A's word in d1, which nothing here returns — test/test_rng.py asserts the
 * oracle's d1 against a model instead, the way src/actor.c's passes do with their cursors. */
uint32_t rng_next(uint8_t *image, uint32_t entry_d0);

/* $e1f0 — draw one of the WB_STAGE_KIND_ROW candidates WB_STAGE_KIND_TABLE holds for the current
 * WB_STAGE_NUMBER, masked to WB_STAGE_KIND_MASK. Its one caller is $6d04, inside the respawn
 * continuation `actor_defeat` branches to and this project does not port: it stores the result at
 * offset 20 of the actor record and indexes a 16-byte record table at $1044c with it for the
 * record's new WB_ACTOR_TYPE and WB_ACTOR_SPRITE — so the value is which creature the slot comes
 * back as. A NEGATIVE result would make that caller free the slot instead; the mask makes one
 * impossible, which is a claim test/test_rng.py pins rather than assumes.
 *
 * `entry_d2` is the caller's d2, and it is load-bearing where the generator's d0 is not: EVERY
 * arithmetic step on the row is a `.w`, so d2's high half is never written, and then `add.l d2,d0`
 * folds it into the table INDEX. Its one caller reaches here with a `moveq #0,d2` behind it, so the
 * game only ever passes 0 — but the instruction reads the whole register and a case can show it.
 * That index then goes onto a 24-BIT ADDRESS BUS: the 68000 does not wire the top byte of an
 * effective address to anything, so a d2 of $01000000 reads the same byte a d2 of 0 does. The
 * reconstruction masks with WB_BUS_ADDR_MASK before its off-image guard, because the guard would
 * otherwise answer 0 for an address the 68000 brings back round into the image; test/test_rng.py
 * pins both the wrap and the mask's WIDTH (a 23-bit bus reproduces the wrap case but not the one
 * seeded on the bus's top bit).
 * There is no `entry_d0`, unlike the generator this calls: `andi.l #$7,d0` masks the whole longword
 * two instructions after the `bsr`, so the high half the generator hands back cannot reach the
 * result. The SIBLING draw at $e1c8 (32 candidates, table $e222) is the same routine with three
 * different operands and BRANCHES INTO this one's tail at $e214; it is not reconstructed here, and
 * test/test_rng.py pins the shared tail so that porting it later cannot silently change this one. */
uint32_t stage_random_kind8(uint8_t *image, uint32_t entry_d2);

#endif /* WONDERBOY_RNG_H */
