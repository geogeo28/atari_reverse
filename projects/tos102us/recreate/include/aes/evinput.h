/* aes/evinput.h — THE INPUT LAYER's posts (`src/aes/evinput.c`, geminput and the control manager's ct_chgown): an
 * event that came handed to the waits it satisfies — a key (post_keybd, nq), the buttons (post_button, downorup), the
 * mouse (post_mouse, inorout) — the mouse's and the keyboard's OWNER decided (mowner, set_mown, ct_chgown), and the
 * click counter the button interrupt drives (b_click, b_delay).
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame — but b_click, which the button
 * interrupt's glue enters by `jsr` ($fed3d0), and b_delay, which the tick's glue enters by `jsr` ($fed460) and
 * mchange by Line-F. downorup, inorout and mowner answer a WORD; ct_chgown leaves D0 the end of post_button's walk
 * (a null EVB pointer, `move.l a3,d0`, $fe5346) under set_mown's stores, which change no register: 0 on every path —
 * the word fm_own, wm_set and w_setactive's callers hand on. The rest leave a callee's D0, which no caller reads.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG").
 */
#ifndef TOS102US_AES_EVINPUT_H
#define TOS102US_AES_EVINPUT_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- a CDA's key queue (`aes/fmlib.h`'s CQUEUE_*): where nq puts the next key --------------------------------------- */
#define CQUEUE_REAR           18         /* word: the next slot nq fills        ($fe50a8 movea.w 18(a5),a1)    */
#define CQUEUE_KEY_BYTES      2          /* a slot: one key's word              ($fe50ac adda.l a1,a1: the rear doubled) */

/* ---- THE CLICK COUNTER: b_click's state, counted down by b_delay ----------------------------------------------------
 * A press while multi-click waits are pending (`aes/evasync.h`'s AES_GL_BPEND) opens a count of AES_GL_DCLICK ticks
 * (`aes/aes.h`'s AES_GL_CLICK_TICKS); every later change back to the button the count was opened on counts one more
 * click and lengthens it; when it runs out b_delay queues the button change with the clicks counted. */
#define AES_GL_BDESIRED       0x9ad0     /* word: the buttons as b_click last saw them ($fe4f4c cmp.w $9ad0,d7) */
#define AES_GL_BTRUE          0xc798     /* word: the buttons the count was opened on  ($fe4f86 move.w d7,$c798) */
#define AES_GL_BCLICK         0xc72c     /* word: the clicks counted                   ($fe4f64 addq.w #1,$c72c) */
#define CLICK_EXTENSION_TICKS 3          /* a counted click lengthens the count by ($fe4f6a addq.w #3,$c6ca)   */
#define FIRST_CLICK           1          /* ($fe4f7e move.w #1,$c72c; $fe4f98 move.w #1,(sp))                  */

/* ---- THE OWNERS: who the mouse and the keyboard belong to (`aes/wmupdate.h`: AES_GL_MOWNER, AES_GL_KOWNER) ----------- */
/* The process the mouse goes back to inside the control rectangle: set_mown's owner, kept beside AES_GL_MOWNER, which
 * bchange and mchange hand to the screen manager and back (GEM's gl_cowner). */
#define AES_GL_COWNER         0x989c     /* long                                ($fe5058 move.l d0,$989c)      */
/* The screen manager's own mouse wait, GEM's gl_ctwait: a MOBLK whose rectangle is `aes/mnlib.h`'s AES_GL_RMNACTV
 * ($96da) — this is its first word, whether it waits for the mouse to LEAVE the rectangle. */
#define AES_GL_CTWAIT_LEAVE   0x96d8     /* word                                ($fe5456 cmp.w $96d8,d0)       */
/* The owner of window 0, the DESKTOP (`aes/aes.h`'s window records): whose the mouse is on a press over the desktop. */
#define AES_DESKTOP_OWNER     (AES_WINDOWS + WIN_OWNER)   /* ($fe5232 move.l $c4b0,d0)                           */
/* mowner's answers: where a point lies. */
#define MOWNER_IN_CONTROL     1          /* inside the control rectangle        ($fe4f12 moveq #1,d0)          */
#define MOWNER_SCREEN_MANAGER (-1)       /* on the menu bar or a window         ($fe4f28, $fe4f38 moveq #-1)   */
#define MOWNER_DESKTOP        0          /* on the desktop                      ($fe4f3c clr.w d0)             */
/* set_mown's button post: the buttons as they are, as one click ($fe5074 move.w #1,(sp)). */
#define SET_MOWN_CLICKS       1

/* ---- a BUTTON wait's parameter, as downorup and post_button take it apart: `aes/aes.h`'s BUTTON_PARM_* (the sense
 * byte, the clicks, the mask, the state). A button event's ANSWER is the buttons' state in the high word
 * (HIGH_WORD_SHIFT, $fe532c), the clicks ORed into the low by evremove. */

/* ---- a MOUSE wait's rectangle, packed into its EVB by amouse ($fe56b8..): x and y in EVB_PARM, w and h in
 * EVB_RETURN, a word each (HIGH_WORD_SHIFT: $fe54e2, $fe54f6) — inorout unpacks them into a GRECT of its own frame. */
#define INOROUT_RECT_BYTES    8          /* -8(a6)..-2(a6): x, y, w, h          ($fe54e6..$fe5502)             */

#ifndef __ASSEMBLER__
void aes_nq(uint8_t *image, int16_t key, uint32_t queue);                                             /* $fe5092 */
int16_t aes_downorup(uint8_t *image, int16_t buttons, uint32_t parameter);                            /* $fe5292 */
void aes_post_keybd(uint8_t *image, uint32_t process, int16_t key);                                   /* $fe51a2 */
void aes_post_button(uint8_t *image, uint32_t process, int16_t button, int16_t clicks);               /* $fe52e2 */
void aes_post_mouse(uint8_t *image, uint32_t process, int16_t x, int16_t y);                          /* $fe5480 */
int16_t aes_inorout(uint8_t *image, uint32_t evb, int16_t x, int16_t y);                              /* $fe54b8 */
int16_t aes_mowner(uint8_t *image, int16_t x, int16_t y);                                             /* $fe4ef0 */
void aes_set_mown(uint8_t *image, uint32_t mouse_owner, uint32_t keyboard_owner);                     /* $fe504a */
uint16_t aes_ct_chgown(uint8_t *image, uint32_t owner, uint32_t rect);                                /* $fe49ba */
void aes_b_click(uint8_t *image, int16_t buttons);                                                    /* $fe4f40 */
void aes_b_delay(uint8_t *image, int16_t ticks);                                                      /* $fe4fb0 */
#endif

#endif /* TOS102US_AES_EVINPUT_H */
