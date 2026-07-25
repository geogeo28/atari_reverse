/* game_frame.h — what is left of the shell/bench assembly constants after three hoists into
 * include/game.h: the object-list pass split moved there with rm_draw_frame, and the anim-word mirror
 * offsets moved there with rm_bind_gobj_prefix_assets, which now owns the whole prefix bundle.
 *
 * ONE constant remains, and only render/atari/bench_main.c uses it — the bench deliberately gives the
 * prefix a SEPARATE decay arena (it stages one frozen frame and never arms a decay) where the shell
 * must alias it onto the dispatcher's grid. A real shell wants rm_ring_decay_base(), not this. */
#ifndef RM_GAME_FRAME_H
#define RM_GAME_FRAME_H

/* The anim-word mirror offsets moved to include/game.h (RM_GOBJ_ANIM_MIRROR1_OFF /
 * RM_GOBJ_ANIM_MIRROR2_OFF) when rm_bind_gobj_prefix_assets took over the binding. */

#define GOBJ_MARKER_RECS_BYTES 0x400 /* the marker-decay record arena the prefix mutates */

#endif /* RM_GAME_FRAME_H */
