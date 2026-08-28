/* mothership.c — the boss encounter.
 *
 * Only the two routines that need no unported callee are here. The rest of the subsystem hangs off
 * the actor script VM (0x14c66), the formation spawner (0x14a7c) and the sprite draw (0x15ace);
 * STATUS.md's "Not reconstructed" table says which is waiting on which.
 *
 * BOTH ROUTINES ARE STEPS OF ONE STATE MACHINE, driven by the byte at A_mothership_prep_stage:
 * mothership_place_tail sets it to 1, and mothership_sprite_build_step walks it 1 -> 2 -> 3 -> 4,
 * doing one frame's worth of work per call and clearing the stage when it arrives.
 */
#include "machine.h"
#include "entity.h"
#include "mothership.h"
#include "sprite.h"

/* Eight phase slots of MOTHERSHIP_FRAME_BYTES each — the shape sprite_preshift8_2px builds, so the
 * relation is expressed rather than restated as a second literal. */
#define MOTHERSHIP_BANK_BYTES (SPRITE_PRESHIFT_SLOTS * MOTHERSHIP_FRAME_BYTES)

#define PREP_STAGE_COPY 1        /* `cmpi.b #$1` — the stage that copies the raw frames in */
#define PREP_STAGE_PRESHIFT 2    /* ...and the first that pre-shifts one; `sub.b #$2,d0` */
#define PREP_STAGE_DONE 4        /* `cmpi.b #$4` — the stage that arms the encounter and resets */

/* ================================================================================================
 * mothership_place_tail @ 0x14f18 — lay the five boss segments out from the anchor.
 *
 * The anchor's x is read ONCE, before the loop, and stepped in the register; its y is re-read from
 * A_mothership_y inside the loop and written unchanged to every segment. So the five records end up
 * on one horizontal row, MOTHERSHIP_SEGMENT_X_STEP apart, each pointing at its own slice of the
 * sprite bank.
 * ============================================================================================= */
void mothership_place_tail(uint8_t *image) {
    uint32_t segment = A_entity_boss_parts;
    uint32_t sprite = A_mothership_sprite_bank;
    uint16_t x = be16(image + A_mothership_x);

    for (unsigned i = 0; i < MOTHERSHIP_TAIL_SEGMENTS; i++) {
        wr32(image + segment + ENTITY_SPRITE, sprite);
        wr16(image + segment + ENTITY_HEIGHT, MOTHERSHIP_SEGMENT_HEIGHT);
        image[segment + ENTITY_ALIVE] = 1;
        wr16(image + segment + ENTITY_Y, be16(image + A_mothership_y));
        wr16(image + segment + ENTITY_X, x);

        x = (uint16_t)(x + MOTHERSHIP_SEGMENT_X_STEP);
        sprite = addr_add(sprite, MOTHERSHIP_SEGMENT_SPRITE_BYTES);
        segment = addr_add(segment, ENTITY_STRIDE);
    }
    image[A_mothership_prep_stage] = PREP_STAGE_COPY;
}

/* Register map: no register inputs. A2 walks the segments, A4 the sprite bank, D0 carries x and D6
 * counts. No outputs but memory. */
void g_mothership_place_tail(uint8_t *image) {
    mothership_place_tail(image);
}

/* ================================================================================================
 * mothership_sprite_build_step @ 0x15128 — one frame's slice of building the boss sprite banks.
 *
 * Spread over three calls so no single frame pays for the whole build: call one copies both raw
 * frames into the banks, calls two and three pre-shift one bank each, and the third also arms the
 * encounter and resets the stage.
 *
 * THE STAGE ARITHMETIC IS SIGNED THEN UNSIGNED, in that order, and the mix is what bounds the
 * routine: `sub.b #$2` / `ext.w` sign-extends, and `mulu.w` then reads the result as UNSIGNED. A
 * stage of 0 therefore multiplies 0xfffe by the bank size and addresses ~0x5030000 — far outside
 * the image. It is unreachable rather than tolerated: the routine's only caller (0x1117e) is behind
 * `tst.b A_mothership_prep_stage / beq`, so the stage is non-zero on entry, and the stage-3 arm
 * clears it before anyone can call again. See STATUS.md.
 * ============================================================================================= */
static void mothership_copy_raw_frames(uint8_t *image) {
    uint32_t src = A_mothership_sprite_source;
    uint32_t dst = A_mothership_sprite_bank;

    for (unsigned bank = 0; bank < MOTHERSHIP_BANKS; bank++) {
        /* `movem.l` saves both cursors around the copy, so each bank starts from the base below
         * rather than from where the previous run left off — the strides differ, and that is why. */
        for (unsigned offset = 0; offset < MOTHERSHIP_FRAME_BYTES; offset += 4)
            wr32(image + addr_add(dst, offset), be32(image + addr_add(src, offset)));
        src = addr_add(src, MOTHERSHIP_FRAME_BYTES);
        dst = addr_add(dst, MOTHERSHIP_BANK_BYTES);
    }
}

static void mothership_preshift_one_bank(uint8_t *image, uint8_t stage) {
    uint16_t bank_index = (uint16_t)sign_ext8((uint8_t)(stage - PREP_STAGE_PRESHIFT));
    uint32_t bank_at = addr_add(A_mothership_sprite_bank,
                                (uint32_t)bank_index * MOTHERSHIP_BANK_BYTES);

    /* Source and destination are the SAME address: the pre-shift is in place (`movea.l a0,a1`). */
    sprite_preshift8_2px(image, bank_at, bank_at, MOTHERSHIP_FRAME_BYTES);
}

void mothership_sprite_build_step(uint8_t *image) {
    if (image[A_mothership_prep_stage] == PREP_STAGE_COPY) {
        mothership_copy_raw_frames(image);
        image[A_mothership_prep_stage]++;
        return;
    }

    mothership_preshift_one_bank(image, image[A_mothership_prep_stage]);
    image[A_mothership_prep_stage]++;
    if (image[A_mothership_prep_stage] != PREP_STAGE_DONE)
        return;

    image[A_mothership_ready] = 1;
    wr32(image + A_mothership_phase_timer, 0);
    image[A_mothership_prep_stage] = 0;
}

/* Register map: no register inputs. A0/A1 are the copy's cursors and the preshift's source and
 * destination (the same address — the pre-shift is in place); D0 carries the stage, D2 the frame
 * width, D7 counts the banks. No outputs but memory. */
void g_mothership_sprite_build_step(uint8_t *image) {
    mothership_sprite_build_step(image);
}
