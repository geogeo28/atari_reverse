/* vdi/screen.h — the SCREEN AND WORKSTATION PLUMBING (`src/vdi/screen.c`): what v_opnwk and v_clswk stand
 * the physical workstation on and take it off again.
 *
 *   $fc4b7c clear_span              the BIOS's `bzero(from, to)`, which GEMDOS's loader ends in too
 *   $fca654 v_clrwk (3)             the screen cleared: the span clear over _v_bas_ad .. +32000
 *   $fca6d4 setres                  the resolution the workstation opens in, and its palette queued
 *   $fca670 init_timer_mouse        USER_TIM defaulted, etv_timer taken, the mouse on, the cursor off
 *   $fca78a timer_tick              the etv_timer the VDI installs: USER_TIM, then the old handler
 *   $fca7a2 restore_timer_mouse     etv_timer given back, the mouse off, the cursor on
 *
 * All six are hand 68000 reached by `jsr`/`bra`, so their contracts are `test/vdi_screen.py`'s
 * declarations: clear_span an Alcyon frame, v_clrwk a VDI function, setres an answer in D0, timer_tick the
 * etv_timer word under its return address, the other two nothing either way. clear_span and timer_tick
 * ship as the ROM's own instructions (`src/vdi/screen.S`, `vdi/transcribed.h`): the clear because its C is
 * nearly four times the ROM's `movem` loop, the tick because etv_timer holds its ADDRESS and timer C enters
 * it with a convention no C function has.
 */
#ifndef TOS102US_VDI_SCREEN_H
#define TOS102US_VDI_SCREEN_H

/* ---- the clear ------------------------------------------------------------------------------------ */
#define VDI_SCREEN_BYTES       32000     /* every ST mode's screen              ($fca65a addi.l)    */
/* The span clear's whole 256-byte blocks, for the C twin and the `.S` alike (`and.l #-256,d0`). */
#define VDI_CLEAR_BLOCK_MASK   0xffffff00 /*                                    ($fc4ba6 and.l)     */

/* ---- the timer ------------------------------------------------------------------------------------ */
#define VDI_TIMER_VECTOR       0x100     /* Setexc's number for etv_timer      ($fca686 move.w #256) */

/* ---- setres: intin[0] of v_opnwk, the shifter mode, and the answer ------------------------------------
 * Only two device words mean anything: 1 keeps a colour mode as it is, 3 asks for medium. EVERY other word
 * — 2 and 4, which GEM calls low and high, among them — asks for LOW; a mono machine answers high whatever
 * is asked, never switching. */
#define VDI_SETRES_DEVICE_CURRENT  1     /*                                     ($fca6ec cmp.w #1)  */
#define VDI_SETRES_DEVICE_MEDIUM   3     /*                                     ($fca6f8 cmp.w #3)  */
#define VDI_SETRES_ANSWER_LOW      1     /*                                     ($fca722 moveq #1)  */
#define VDI_SETRES_ANSWER_MEDIUM   2     /*                                     ($fca74c moveq #2)  */
#define VDI_SETRES_ANSWER_HIGH     3     /*                                     ($fca75e moveq #3)  */
/* The modes themselves are Getrez's answers: addrs.h's SHIFTER_MODE_LOW / _MEDIUM / _HIGH. */
/* The two palettes Setpalette queues, which are ONE table read at two starts: sixteen words from
 * VDI_PALETTE_MEDIUM are white, red, green, black (a medium screen's four) and then the first twelve of
 * the low palette, which starts four words in. Mono queues the medium one. */
#define VDI_PALETTE_MEDIUM     0xfca762  /* ROM, between setres and timer_tick  ($fca73e pea)       */
#define VDI_PALETTE_LOW        0xfca76a  /*                                     ($fca714 pea)       */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* ---- the cores ------------------------------------------------------------------------------------ */
/* $fc4b7c — the BIOS's span clear, an Alcyon call (from.l, to.l): v_clrwk's body, and `Pexec`'s loader's
 * last step (`src/gemdos/pexec_load.c`). */
void vdi_clear_span(uint8_t *image, uint32_t from, uint32_t to);
void vdi_v_clrwk(uint8_t *image);
uint32_t vdi_setres(uint8_t *image);
void vdi_init_timer_mouse(uint8_t *image);
/* `tick_ms` is the word timer C pushes in front of the call (`_timr_ms`): the ROM never reads it, and
 * passes it on to the handler it chains to, which does. */
void vdi_timer_tick(uint8_t *image, int16_t tick_ms);
void vdi_restore_timer_mouse(uint8_t *image);
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_SCREEN_H */
