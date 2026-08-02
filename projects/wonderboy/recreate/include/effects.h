/* effects.h — the effect handlers and the state stubs above them (src/effects.c).
 *
 * 29 leaf routines at $10200..$103e7, each one to four instructions long, reached only through
 * `effect_handler_table` ($1023a) or a sibling dispatch — which is why Ghidra's flow analysis never
 * created them and ../names.txt has to. Every ADDRESS they touch is a game-state global named in
 * wonderboy.h, which both languages read; the one constant below is C-only, since the tests
 * transcribe the setters' immediates from the disassembly instead of composing them.
 *
 * Each takes the flat 68000 image, since the originals address their globals absolutely and have
 * neither arguments nor a return value. The names are ../names.txt's, unchanged.
 */
#ifndef WONDERBOY_EFFECTS_H
#define WONDERBOY_EFFECTS_H

#include <stdint.h>

#define WB_HUD_SLOT_CHANGED  0xffu    /* the low byte every HUD setter stamps: "this slot changed" */

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

#endif /* WONDERBOY_EFFECTS_H */
