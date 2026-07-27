/* frame.c — the whole-frame render composition (draw_frame @0x12e22 + draw_game_objects @0x12dcc).
 *
 * The platform-independent per-frame render pipeline hoisted out of the on-target shell so the shell
 * (render/atari/game_main.c) calls ONE composition; the bench (bench_main.c) deliberately mirrors it with staged HUD scalars,
 * and so `make test` can run the shell's real frame end-to-end (the composed-frame differential in
 * test/equiv.py) and catch any missing wiring between the individually-verified stages. Transcribed
 * one-for-one from the shell's former draw_frame body; the order — including the wrap-frame's second
 * geometry build (the caller's game-update step builds once before the event tail, this builds again
 * off the ring bands the tail poked) — is preserved exactly (see STATUS "Perf": do not dedupe it).
 */
#include "game.h"

/* UNIFIED ST/STE binary (PERF30 C5 slice 1): route the road fine-scroll through rm_blit_road_scroll_fn —
 * a function pointer bound ONCE at boot (rm_blit_bind_all) to the hardware-blitter dispatch when a
 * blitter is present, else left at the C reference. The seam lives HERE, at the sole call site, and not
 * in include/game.h — exactly as object_list.c does for the two object engines, and in the same shape: an
 * UPPERCASE seam name, so the call site reads as a seam and the real function's name is never shadowed.
 * Gated on RM_BLITTER (the m68k target build), so the host differential keeps calling the C reference. */
#ifdef RM_BLITTER
#include "scroll_const.h"
#define RM_BLIT_ROAD_SCROLL rm_blit_road_scroll_fn        /* boot-bound: blitter (STE) or the C reference */
#else
#define RM_BLIT_ROAD_SCROLL rm_blit_road_scroll
#endif

void rm_draw_frame(const RmScene *sc, Framebuffer *fb) {
    GobjPrefixState *pfx = sc->pfx;
    ObjListCtx *objlist = sc->objlist;

    rm_gobj_prefix(pfx, sc->pfx_assets);             /* off-frame: advance view_parity/anim/marker */
    /* The three LIVE globals the object dispatcher reads. In the original each is one word/byte it
     * loads at draw time, so all three must be refreshed HERE, every frame, not captured at a leg
     * start: view_parity and bonus_timer are advanced by the prefix just above (bonus_timer opens the
     * 5-flag window that clamps low object types), and p24_flag is score_str[1], which §I bumps at
     * every checkpoint. */
    objlist->view_parity = pfx->view_parity;         /* the dispatcher (handler_lo) reads the advanced parity */
    objlist->bonus_timer = pfx->bonus_timer;
    objlist->p24_flag = sc->hud_text[RM_HUD_P24_DIGIT_OFF];
    objlist->px = fb->px;                            /* the dispatcher's draw target: this frame's buffer */
    rm_build_road_geometry(sc->pose, sc->src, sc->ring, sc->ctrl, sc->scanline);
    sc->road->width_tbl = sc->ctrl + RM_CTRL_WIDTH_OFF;
    /* The object dispatcher's per-row x-offset table aliases the freshly-built road control table in
     * the original (obj_xoff_tbl == road_width_tbl + 2), so rebind it to this frame's ctrl. */
    objlist->xoff_tbl = sc->ctrl + RM_CTRL_WIDTH_OFF + 2;
    sc->scroll->seg_head = sc->pose->seg_head;       /* the scroll step follows the near slope */
    rm_render_road(sc->road, fb);
    RM_BLIT_ROAD_SCROLL(sc->scroll, sc->shifted, fb);

    /* --- draw_game_objects tree ---
     * GAME_DUMP_STAGE (on-target debug builds only; never defined for the host lib) cuts the frame
     * short after a chosen stage, so a headless run's SCREEN.BIN dump is a partial frame and can
     * pinpoint the first stage whose on-target output diverges from the host reference. */
#if defined(GAME_DUMP_STAGE) && GAME_DUMP_STAGE == 0
    return;
#endif
    rm_draw_ground(sc->ground, sc->ground_assets, fb);
#if defined(GAME_DUMP_STAGE) && GAME_DUMP_STAGE == 1
    return;
#endif
    rm_draw_fg_sprite(sc->sprite, sc->sprite_assets, fb);
#if defined(GAME_DUMP_STAGE) && GAME_DUMP_STAGE == 2
    return;
#endif

    /* The dispatcher's flag streams and the pass split all come from the LIVE ring: the sprite passes
     * walk the serialized grid from row 1, the fixed pass from row 12 — the same aliasing the original
     * gets from pointing into its flat row grid. */
    int count = rm_ring_sprite_count(sc->ring);
    if (count - 1 >= 0)                               /* pass 1: the active sprite rows */
        rm_draw_object_list(objlist, sc->obj_sprite_disp, 0,
                            sc->ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, 0,
                            (uint16_t)(count - 1), GOBJ_D6_INIT, (uint16_t)count);
#if defined(GAME_DUMP_STAGE) && GAME_DUMP_STAGE == 3
    return;
#endif
    rm_draw_object(sc->object, fb);
    if (GOBJ_SPRITE_LAST - count >= 0)               /* pass 2: the remaining rows */
        rm_draw_object_list(objlist, sc->obj_sprite_disp, (uint16_t)(count * GOBJ_ROW_A5_STRIDE),
                            sc->ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES,
                            (uint16_t)(count * GOBJ_ROW_A3_STRIDE),
                            (uint16_t)(GOBJ_SPRITE_LAST - count),
                            (uint16_t)(GOBJ_D6_INIT - count * GOBJ_D6_ROW_STEP), 0);
    if ((objlist->view_flags & GOBJ_VIEW_REAR) == 0) {   /* pass 3 (fixed) + buggy, view-ordered */
        rm_draw_object_list(objlist, sc->obj_fixed_list, 0,
                            sc->ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
        rm_draw_buggy(sc->sprite, sc->sprite_assets, fb);
    } else {
        rm_draw_buggy(sc->sprite, sc->sprite_assets, fb);
        rm_draw_object_list(objlist, sc->obj_fixed_list, 0,
                            sc->ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
    }

    /* Fan the flag-sequence state pfx OWNS into the HUD view (phase-4 bars + phase-5 colour cursor),
     * right before the HUD draw — the original's g_draw_game_objects-then-g_draw_hud order, and after
     * rm_gobj_prefix above (which advances these). Without it the flag bars never appear. */
    rm_gobj_hud_view(pfx, sc->hud);
    rm_draw_hud(sc->hud, sc->hud_assets, fb);
}
