/* effects.h — the effect handlers and the state stubs above them, and the PICKUP effects behind the
 * game's second dispatch table (src/effects.c).
 *
 * 43 leaf routines over two bands — 29 at $10200..$103e7 and 14 at $105e4..$10799 — each one to
 * seven instructions long and reached ONLY through `effect_handler_table` ($1023a) or
 * `pickup_effect_table` ($105ac), which is why Ghidra's flow analysis never created them and
 * ../names.txt has to. Every ADDRESS all but one of them touches is a game-state global named in
 * wonderboy.h, which both languages read; the one constant below is C-only, since the tests
 * transcribe the setters' immediates from the disassembly instead of composing them.
 *
 * Each takes the flat 68000 image, since the originals address their globals absolutely and have
 * neither arguments nor a return value. The names are ../names.txt's, unchanged.
 */
#ifndef WONDERBOY_EFFECTS_H
#define WONDERBOY_EFFECTS_H

#include <stdint.h>

/* The low byte every HUD setter stamps: "this slot changed". It is also the low byte of
 * wonderboy.h's WB_HUD_SLOT_REARM, which the two damage paths write as a whole word — one byte
 * spelt in two headers because neither #define can be built from the other and stay visible to
 * test/layout.py, which scrapes plain integer literals. test_effects.py's
 * `test_the_two_headers_spell_one_slot_byte` pins the two together in place of that derivation. */
#define WB_HUD_SLOT_CHANGED  0xffu

/* $10200..$10239 — the six stubs Ghidra never reached. Five write one HUD slot; the sixth is the
 * odd one out in both its target and its encoding (abs.w, and 8 bytes rather than 10). */
void set_state_bbc8_1ff(uint8_t *image);
void set_state_bbc8_2ff(uint8_t *image);
void set_state_bbc8_3ff(uint8_t *image);
void set_state_bbc8_4ff(uint8_t *image);
void set_state_bbc8_6ff(uint8_t *image);
void set_state_6f9c_ffff(uint8_t *image);

/* $10296, $102bc — raise the meter, clamped to its maximum. */
void effect_add4_clamped_b6fa(uint8_t *image);
void effect_add2_clamped_b6fa(uint8_t *image);

/* $102e2..$1034f — plain state writers: one `move.w #n,<abs>.l` each. */
void effect_set_bd6a_1(uint8_t *image);
void effect_set_bd6a_2(uint8_t *image);
void effect_set_bd6a_3(uint8_t *image);
void effect_set_bd6a_4(uint8_t *image);
void effect_set_bbc2_80ff(uint8_t *image);
void effect_set_bd66_1(uint8_t *image);
void effect_set_bd66_2(uint8_t *image);
void effect_set_bd66_3(uint8_t *image);
void effect_set_bd66_4(uint8_t *image);
void effect_set_bd66_5(uint8_t *image);
void effect_set_bbbe_05ff(uint8_t *image);

/* $10350..$1037f — NOT plain writers: each stamps effect_state_21e4 := 2 before its own ordinal. */
void effect_set_bd68_1(uint8_t *image);
void effect_set_bd68_2(uint8_t *image);
void effect_set_bd68_3(uint8_t *image);

/* $10380..$10393 — two more plain state writers. */
void effect_set_bbc0_05ff(uint8_t *image);
void effect_set_bbc6_01ff(uint8_t *image);

/* $10394..$103db — push one record onto the growing list at $b546. */
void effect_push_record_0605(uint8_t *image);
void effect_push_record_0508(uint8_t *image);
void effect_push_record_0705(uint8_t *image);
void effect_push_record_0803(uint8_t *image);

/* $103dc — the meter straight to its maximum. */
void effect_restore_b6fa_to_max(uint8_t *image);

/* ---- the PICKUP effects, $105e4..$10799 (batch 38) --------------------------------------------
 *
 * FOURTEEN more leaves of the same kind, behind WB_PICKUP_EFFECT_TABLE — the sibling of
 * WB_EFFECT_HANDLER_TABLE, reached from `actor_behavior_type38_pickup` and from nowhere else. They
 * are here rather than in src/behavior.c for the reason the twenty-nine above are here: their
 * addresses sit in the effect band, every one is a straight-line leaf whose whole surface is a word
 * or two of game state, and four of them are `effect_push_record`'s own three instructions — the
 * SAME four records, so one copy serves both tables.
 *
 * WHAT SEPARATES THEM FROM THE TWENTY-NINE is the tail: each posts a message id into
 * WB_TEXT_REQUEST and WB_TEXT_LIFETIME_DEFAULT into WB_TEXT_LIFETIME_REQUEST beside it (the
 * first is an ADDRESS and the second a VALUE). That id is what NAMES each handler, which
 * is batch 17's method (the helmet and the gauntlet slots were identified from the messages their
 * own paths post) applied to twelve more. Three of them post WB_TEXT_REQUEST_NONE and so post
 * NOTHING — and, since slot 38's score arm has already posted WB_TEXT_MESSAGE_BONUS_POINTS by the
 * time a handler runs, those three CANCEL that box rather than merely declining to open one.
 *
 * ONE OF THEM IS NOT A LEAF: `pickup_effect_vanish_followed` calls `followed_actor_record`, by a
 * `jsr $67e0.w` — the SHORT absolute form, which is the encoding batch 31's hidden caller hid in.
 */
void pickup_effect_none(uint8_t *image);              /* $105e4 — a bare `rts` */
void pickup_effect_grant_bbc4(uint8_t *image);        /* $105e6 — and it posts no message */
void pickup_effect_grant_wing_boots(uint8_t *image);  /* $10600 */
void pickup_effect_grant_helmet(uint8_t *image);      /* $1061a */
void pickup_effect_grant_gauntlet(uint8_t *image);    /* $10634 */
void pickup_effect_grant_revival(uint8_t *image);     /* $1064e */
void pickup_effect_grant_fire_balls(uint8_t *image);  /* $10668 — the four appends */
void pickup_effect_grant_bombs(uint8_t *image);       /* $1068a */
void pickup_effect_grant_wind_spouts(uint8_t *image); /* $106ac */
void pickup_effect_grant_lightning(uint8_t *image);   /* $106ce */
void pickup_effect_refill_meter(uint8_t *image);      /* $106f0 */
void pickup_effect_add4_meter(uint8_t *image);        /* $10714 — NOT the clamped add above */
void pickup_effect_bump_attack_level(uint8_t *image); /* $10746 */
void pickup_effect_vanish_followed(uint8_t *image);   /* $10772 */

#endif /* WONDERBOY_EFFECTS_H */
