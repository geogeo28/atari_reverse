/* zynaps_cheats.h — the trainer watcher's interface to the rest of the shim.
 *
 * A SHIM HEADER, and only zynaps_main.c includes it. `shim_include/hw.h` — which every VERIFIED
 * CORE reaches — must NOT include this file: its own comment says why in those words ("whatever
 * this file includes lands in ~six verified translation units"), so the ONE name the ACIA door
 * needs is declared in that header directly, exactly as `zy_store_video_base_byte` already is.
 *
 * THE TRAINER IS A DELIBERATE DIVERGENCE FROM THE ORIGINAL and the only one in this build. It is
 * inert until a player arms it, no core is edited to carry it, and every judged smoke mode asserts
 * the counts below are still zero — see README.md's "Trainer" section and smoke.py's
 * `check_the_trainer_stayed_dormant`.
 */
#ifndef ZYNAPS_SHIM_CHEATS_H
#define ZYNAPS_SHIM_CHEATS_H

#include <stdint.h>

/* Z, Y and N — the three letters held together to arm the trainer. The letters are the contract;
 * which SCANCODE each one is depends on the keyboard, which is what `zy_cheats_resolve_scancodes`
 * is for (zynaps_cheats.c carries the layout argument). */
#define CHEAT_COMBO_KEYS 3u

/* Which of the two arms below was compiled, as a number the record can carry: it is what separates
 * a PURIST binary's zeros — built without -DZY_CHEATS, with no watcher in it at all — from a
 * dormant trainer's identical zeros. */
#ifdef ZY_CHEATS
#define ZY_CHEATS_BUILT 1u
#else
#define ZY_CHEATS_BUILT 0u
#endif

/* What the run's record publishes about the trainer, so `smoke.py` can judge it. One struct rather
 * than seven externs: `record_the_run` reads all of them at one point and nothing else reads any. */
struct zy_cheat_counts {
    uint32_t armed;                 /* 0 or 1 — did the combo ever complete? */
    uint32_t arm_jingles;           /* how many times the arming fanfare was started */
    uint32_t invulnerable_fires;    /* F1 presses acted on */
    uint32_t lives_fires;           /* F2 */
    uint32_t power_fires;           /* F3 */
    /* THE TWO READ-BACKS, and they are read-backs rather than mirrors of what the code asked for:
     * each is the GAME'S OWN byte re-read straight after the trainer wrote it, so a poke that
     * landed somewhere else shows up as the wrong number here. `smoke.py cheats` is racing the
     * frame loop for both — the panel bits are cleared by the next repaint and the tune cursor
     * moves every tick — so neither could be sampled from outside at all.
     *
     * `panel_requests` is the union of `A_panel_redraw_mask` after each poke that asked for one;
     * `jingle_stream` is voice 3's restart pointer after the arming fanfare was started, which
     * `sound_lookup_tune` predicts exactly. */
    uint32_t panel_requests;
    uint32_t jingle_stream;
    /* The scancode each combo letter resolved to out of the GAME'S OWN table, in Z, Y, N order.
     * 0 means the table does not spell that letter — see zynaps_cheats.c's fallback. */
    uint32_t scancode[CHEAT_COMBO_KEYS];
};

/* Read the game's own scancode->ASCII table for the three combo letters. Call once, after the
 * program image is staged and before any interrupt can arrive. */
void zy_cheats_resolve_scancodes(const uint8_t *image);

/* The two state windows the watcher is gated on, each opened and closed at exactly one place in
 * zynaps_main.c. Arming is refused outside the title/attract screen; a cheat key does nothing
 * outside the frame loop. */
void zy_cheats_arming_window(unsigned open);
void zy_cheats_play_window(unsigned open);

/* One vertical blank of the watcher: the hold timer, the arming, and the pokes a cheat key asked
 * for. Called from `zy_vbl_tick` AFTER the program's own handler has run. */
void zy_cheats_tick(void);

void zy_cheats_report(struct zy_cheat_counts *out);

#endif /* ZYNAPS_SHIM_CHEATS_H */
