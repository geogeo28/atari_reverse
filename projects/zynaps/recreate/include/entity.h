/* entity.h — the entity record, and the entity housekeeping in src/entity.c.
 *
 * ../../names.txt's `entity_table` (0x17a8e) is 20 of these records; `entity_boss_parts` (0x18142)
 * holds more. The layout below is a TRANSCRIPTION of names.txt's comment on 0x17a8e (plus the
 * velocity pair from its comment on 0x142d4) — the naming pass recovered the whole record from
 * full-body reads, so it is written out once here as a FROZEN block rather than grown field by
 * field. Freezing it is what lets several agents port entity routines at the same time: nobody has
 * to add a field, so nobody edits this block, and the field a routine needs is already named.
 *
 * EVERY FIELD CARRIES ITS PROVENANCE, because "named" and "held by a test" are different claims and
 * a reader porting the next routine needs to know which one they are getting. `pinned by <test>`
 * means a differential case would fail if the offset were wrong; `names.txt, unpinned` means it is
 * a read, believed but unexercised — confirm it against the disassembly before you lean on it, and
 * upgrade the tag in the change that ports a routine using it.
 *
 * Reading a global another subsystem owns is done by including ITS header; see README.md,
 * "Adding a function".
 */
#ifndef ZYNAPS_ENTITY_H
#define ZYNAPS_ENTITY_H

#include <stdint.h>

/* ================================================================================================
 * THE RECORD — frozen. names.txt 0x17a8e: "20 records x 0x2c".
 * ============================================================================================= */
#define ENTITY_STRIDE      0x2cu  /* names.txt, unpinned (no ported routine steps by it yet) */

#define ENTITY_X           0x00u  /* .w signed — playfield x.  pinned by test_entity.py */
#define ENTITY_Y           0x04u  /* .w signed — playfield y.  pinned by test_entity.py */
#define ENTITY_HEIGHT      0x08u  /* .w, masked &0x7fff — sprite rows.      names.txt, unpinned */
#define ENTITY_SPRITE      0x0au  /* .l — pointer to the sprite bank.        names.txt, unpinned */
/* .b — alive / animation state, bit 7 = exploding. PINNED BY test_entity.py, and its NEIGHBOUR
 * matters: entity_kill_if_offscreen reads the two as one word (`tst.w 14(a2)`) and clears only this
 * byte (`clr.b 14(a2)`). See src/entity.c. */
#define ENTITY_ALIVE       0x0eu
/* .b — set by the blit at 0x15b7c when the sprite overlapped background pixels. names.txt,
 * unpinned as an OFFSET: the only ported reader reaches it through the word read above, which names
 * ENTITY_ALIVE, so nothing yet fails if this number is wrong. */
#define ENTITY_PIXEL_HIT   0x0fu
#define ENTITY_TYPE        0x11u  /* .b — class id, the index into the 0x19196 / 0x191a4 / 0x191ac
                                   * class bitmaps.                          names.txt, unpinned */
#define ENTITY_DX          0x12u  /* .w — cos64[angle]*speed (0x142d4).      names.txt, unpinned */
#define ENTITY_DY          0x14u  /* .w — sin64[angle]*speed (0x142d4).      names.txt, unpinned */
#define ENTITY_HP          0x1au  /* .b — hit points, or a seeker's target.  names.txt, unpinned */
#define ENTITY_BOUNCE      0x1bu  /* .b                                      names.txt, unpinned */
#define ENTITY_ANIM_FRAME  0x20u  /* .b                                      names.txt, unpinned */
#define ENTITY_SQUADRON    0x21u  /* .b — squadron id.                       names.txt, unpinned */

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void entity_kill_if_offscreen(uint8_t *image, uint32_t entity);

#endif /* ZYNAPS_ENTITY_H */
