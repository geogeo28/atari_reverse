/* rng.h — the game's pseudo-random generator ($68c6) and the two per-stage draws over it ($e1f0,
 * $e1c8); src/rng.c.
 *
 * WHY THESE ARE ONE MODULE. `rng_next` has ten `bsr` callers spread across the whole program and
 * belongs to no subsystem; the two draws over it are THE only two routines in the image whose entire
 * body is "advance the generator and index a table with the result". Putting them beside the
 * generator is what lets the battery pin them together — a draw's result is the generator's low
 * three (resp. five) bits and nothing else, so a case that got the generator wrong and the table
 * right would still be red.
 *
 * THE GENERATOR'S ENTROPY IS DECLARED NOW, and that is the one thing to know before reading an old
 * note about it. Its entropy term is `$ff8209 ^ $b39a` — the shifter's video-address counter XOR
 * the frame tick. Until batch 33 that address was merely off-image: both cores were served a
 * fabricated 0, the term collapsed to the frame tick alone, and every green run here was green
 * about a generator with no randomness in it — the T3-DATA false green ../names.txt's `cmt 0x68c6`
 * and ../STATUS.md registered. The kit's Phase 7 table now MODELS the byte
 * (`OS_HW_SHIFTER_VCOUNT_LOW`), so it is served from what the case DECLARES, it lands on the
 * ordered read ledger both sides compare, and an undeclared read is refused rather than answered.
 * The randomness is still not the machine's — a per-run constant is not a counter that advances —
 * but it is a value a case states and varies rather than one the model invented.
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

/* $e1f0 / $e1c8 — draw one of the WB_STAGE_KIND_ROW (resp. WB_STAGE_KIND32_ROW) candidates the
 * matching table holds for the current WB_STAGE_NUMBER, masked to WB_STAGE_KIND_MASK.
 *
 * THEY ARE ONE ROUTINE with three operands changed — the table, the row shift and the draw mask —
 * and $e1c8 has no tail of its own: it `bra.w`s into $e1f0's last fourteen bytes, which therefore
 * belong to both. src/rng.c spells that as one static body with three parameters, the way
 * src/actor.c's two pool allocators are one function; test/test_rng.py pins the shared tail from
 * BOTH sides, so neither port can move it without reddening the other.
 *
 * BOTH ARE CALLED FROM `actor_respawn_as_new_kind` AND NOWHERE ELSE: $6cf2 takes the 32-wide draw
 * while the template still has respawns to spare, $6d04 the 8-wide one on the last. That caller
 * stores the result at WB_ACTOR_KIND and indexes WB_ACTOR_KIND_TABLE with it for the record's new
 * WB_ACTOR_TYPE and WB_ACTOR_SPRITE — so the value is which creature the slot comes back as. A
 * NEGATIVE result would make that caller free the slot instead; the closing mask makes one
 * impossible, which is a claim test/test_rng.py pins rather than assumes.
 *
 * `entry_d2` is the caller's d2, and it is load-bearing where the generator's d0 is not: EVERY
 * arithmetic step on the row is a `.w`, so d2's high half is never written, and then `add.l d2,d0`
 * folds it into the table INDEX. The one caller reaches here with d2's HIGH HALF zeroed by the
 * `moveq #0,d2` at $6c14 — its low word by then is the scaled spawn type, which `move.w $bd88.l,d2`
 * overwrites — so the game only ever passes an effective 0. The instruction reads the whole
 * register, and a case can show it.
 * That index then goes onto a 24-BIT ADDRESS BUS: the 68000 does not wire the top byte of an
 * effective address to anything, so a d2 of $01000000 reads the same byte a d2 of 0 does. The
 * reconstruction masks with WB_BUS_ADDR_MASK before its off-image guard, because the guard would
 * otherwise answer 0 for an address the 68000 brings back round into the image; test/test_rng.py
 * pins both the wrap and the mask's WIDTH (a 23-bit bus reproduces the wrap case but not the one
 * seeded on the bus's top bit) for EACH draw, since each computes its own address.
 * There is no `entry_d0`, unlike the generator these call: `andi.l #$7,d0` (`#$1f` for the sibling)
 * masks the whole longword two instructions after the `bsr`, so the high half the generator hands
 * back cannot reach the result. */
uint32_t stage_random_kind8(uint8_t *image, uint32_t entry_d2);
uint32_t stage_random_kind32(uint8_t *image, uint32_t entry_d2);

#endif /* WONDERBOY_RNG_H */
