/* ptero.h — the pterodactyl driver: update_pterodactyl @ 0x14ada.
 *
 * Addresses are Ghidra addresses (image offset + the 0x10000 load base) and mirror `var` lines in
 * ../../names.txt, which stays the source of truth for the name. Only what this routine alone
 * touches is declared here. Everything it shares comes from the header that already owns it:
 * object.h (the whole pterodactyl table and record, the hit boxes and their two stagers, the
 * platform sprites, the message table, test_overlap and the two ptero_* helpers), draw.h (the three
 * per-cell clip suppressors, draw_dst_off, blit_mask_wide / blit_sprite_planes), addrs.h (the draw
 * scratch, screen_base, rng_ptr, object_table), objects.h (active_players, PLAYFIELD_WIDTH),
 * score.h (the message record's fields), sound.h (play_sound and SND_PTERO_CRY) and wave.h (the
 * scheduler's spawn_interval / spawn_timer, and ptero_wave_countdown).
 */
#ifndef JOUST_PTERO_H
#define JOUST_PTERO_H

#include <stdint.h>

#include "addrs.h"
#include "joust.h"

/* ---- globals ---- */

/* One record per wing-beat pose, indexed by the BYTE offset (PT_ANIM & PT_ANIM_FRAME_MASK), so the
 * four poses are 0 / 8 / 0x10 / 0x18. Poses 1 and 3 are the same bitmap, which is what makes the
 * beat a four-phase cycle over three drawings. */
#define A_ptero_frame_table  0x151d6u
#define FRAME_SRC      0x0u   /* .l — the LEFTWARD sprite set; the rightward one sits
                               *      PTERO_FACING_STRIDE further on */
#define FRAME_DST_OFF  0x4u   /* .w — staged into draw_dst_off, so it is SIGN-extended later */
#define FRAME_ROWS     0x6u   /* .w */
/* The stride, which src/ptero.c never multiplies by: PT_ANIM_FRAME_MASK already yields the BYTE
 * offset, and indexing `pose * FRAME_RECORD` on top of it would double every offset. It is here
 * because the record layout is not complete without it, and because the table's length is pinned
 * against it (4 * FRAME_RECORD is exactly the gap up to A_ptero_bump_table). */
#define FRAME_RECORD   0x8u

/* One record per platform, in platform_sprites order: the two x bounds a bird that has run into
 * that platform is turned round at, and the y that decides whether it is sent over or under. */
#define A_ptero_bump_table  0x151f6u
#define BUMP_X_LEFT   0x0u   /* .w — at or left of this the bird is sent LEFT */
#define BUMP_X_RIGHT  0x2u   /* .w — at or right of this it is sent RIGHT */
/* .w — at or BELOW this on screen, i.e. bird y >= this, the bird is sent DOWN; above it, UP.
 * (Screen y grows downward, so "below" is the LARGER y — the wording the earlier comment had
 * backwards. `cmp.w 14(a0),d1 ; bgt` at 0x14cba: the bound is compared against the bird.) */
#define BUMP_Y        0x4u
#define BUMP_RECORD   0x6u

#define STR_PTERO_BOUNTY  0x152beu  /* the "1000" that pops up where a bird was killed */

/* ---- the wing-beat counter (PT_ANIM) ----
 * Bits 3-4 pick the pose and everything else is sub-frame phase, so the counter is free to run
 * round the whole word. Two of the four poses are named because the code branches on them: the dive
 * holds pose 2, and the death animation flaps between pose 3 and pose 2. They are named by INDEX
 * rather than by what the bitmaps show, which nothing in the code says. */
#define PT_ANIM_FRAME_MASK  0x18u   /* `andi.w #$18` — and, since FRAME_RECORD is 8, the offset */
#define PT_ANIM_POSE2       0x10u
#define PT_ANIM_POSE3       0x18u

/* ---- ptero.c ---- */
void update_pterodactyl(uint8_t *image);

#endif /* JOUST_PTERO_H */
