/* game_frame.h — the prefix-arena assembly constants shared by game_main.c (the playable frame) and
 * bench_main.c (the per-stage cycle bench). The object-list pass-split constants (GOBJ_SPRITE_LAST,
 * GOBJ_D6_INIT, ...) moved into include/game.h alongside rm_draw_frame, which now owns the pass split;
 * what stays here is the buf_a anim-word mirror layout + the marker-decay arena size the prefix
 * asset-bundle setup needs. */
#ifndef RM_GAME_FRAME_H
#define RM_GAME_FRAME_H

#define GOBJ_ANIM_BUF_OFF1 0xd70     /* buf_a + this = anim_word mirror 1 (read as a record by draws) */
#define GOBJ_ANIM_BUF_OFF2 0x1250    /* buf_a + this = anim_word mirror 2 */

#define GOBJ_MARKER_RECS_BYTES 0x400 /* the marker-decay record arena the prefix mutates */

#endif /* RM_GAME_FRAME_H */
