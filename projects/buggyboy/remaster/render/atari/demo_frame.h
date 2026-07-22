/* demo_frame.h — the draw_game_objects frame-assembly constants shared by demo_main.c (the playable
 * frame) and bench_main.c (the per-stage cycle bench), so the bench measures exactly the passes the
 * demo draws. */
#ifndef RM_DEMO_FRAME_H
#define RM_DEMO_FRAME_H

/* How the two roadside object-list passes split: rm_ring_sprite_count over the live ring's marker
 * column (src/course.c) — the flat-image walk this replaces read the fixture's frozen copy. */
#define GOBJ_SPRITE_LAST    10
#define GOBJ_ROW_A3_STRIDE  0x20
#define GOBJ_ROW_A5_STRIDE  0x22
#define GOBJ_D6_INIT        0xb0
#define GOBJ_D6_ROW_STEP    0x10
#define GOBJ_VIEW_REAR      4
#define GOBJ_SPRITE_PASS_ROW 1       /* the sprite passes' flag stream starts at this ring row */
#define GOBJ_FIXED_PASS_ROW 12       /* the fixed-object pass's flag stream starts at this ring row */

#define GOBJ_ANIM_BUF_OFF1 0xd70     /* buf_a + this = anim_word mirror 1 (read as a record by draws) */
#define GOBJ_ANIM_BUF_OFF2 0x1250    /* buf_a + this = anim_word mirror 2 */

#define GOBJ_MARKER_RECS_BYTES 0x400 /* the marker-decay record arena the prefix mutates */

#endif /* RM_DEMO_FRAME_H */
