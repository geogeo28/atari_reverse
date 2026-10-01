/* aes/gsxif.h — the rest of gemgsxif (`src/aes/gsxif.c`): the AES's workstation opened and its screen metrics set up,
 * the mouse's interrupt routines and form, the save-under buffer and its blits, and the mouse state read back.
 *
 * HAND 68000, every routine, entered by a Line-F call or a `bsr` over the frame its caller pushed (Alcyon's words and
 * longs), each reaching the VDI through `aes/gsx.h`'s binding — `gsx_ncode` by Line-F, or `gsx_call` ($fe8bb6/$fe8bba)
 * — and gsx_mfsave the Line-A block through `$a000` (`gsx.h`'s Line-A bridge). Read from their bodies:
 *
 *   $fe8808 gsx_init      gsx_wsopen, gsx_start, the AES's mouse routines, vq_mouse into xrat/yrat
 *   $fe8876 gsx_wsopen    intin = 1 x 10, then 2; intin[0] = gl_restype; v_opnwk; gl_restype from the size answered
 *   $fe8aae v_opnwk       the block's INTIN/INTOUT/PTSOUT pointed at the caller's arrays for the one call
 *   $fdaab0 gsx_start     the attribute caches, the clip, the screen's metrics, the two fonts' sizes, the line style,
 *                         and five GRECTs (the screen, the desktop, nothing, the menu bar, the centred box)
 *   $fe8828 gsx_graphic   escape 2 (v_exit_cur) and the AES's mouse routines, or escape 3 and the old ones back
 *   $fe883e gsx_setmb_aes gsx_setmb(the button glue, the motion glue, &drwaddr) — gsx_graphic's tail, gsx_init's bsr
 *   $fe89c6 gsx_setmb     vex_butv, vex_motv; the routines they displaced kept
 *   $fe89f8 gsx_resetmb   ...and put back
 *   $fe8866 gsx_escapes   contrl[5] = the escape, VDI 5 ($fe886a its register entry, D0 the escape: folded)
 *   $fe88de gsx_wsclose   v_clswk
 *   $fe88e4 ratinit       v_show_c(0), the hide nest 0
 *   $fe8a18 gsx_tick      vex_timv; the old routine out through a pointer; intout[0] answered
 *   $fe8a38 gsx_mfset     the cursor hidden, the form's 37 words into intin, vsc_form, the cursor shown
 *   $fe8790 gsx_malloc    gl_tmp an MFDB of the screen's, its buffer Malloc'd
 *   $fe87b0 gsx_mfree     ...and Mfree'd;  $fe87bc gsx_mret: its address, and gl_mlen, out through two pointers
 *   $fe88f8 bb_set        a rectangle widened to whole words, gl_tmp sized to it, the two corner arrays, vro_cpyfm
 *   $fe8966 bb_save       ...the screen into gl_tmp;  $fe8996 bb_restore: gl_tmp back onto the screen
 *   $fe8a54 gsx_mxmy      xrat, yrat out;  $fe8a6a gsx_button: the buttons' word;  $fe8768 gr_mkstate: all four
 *   $fee498 gsx_mfsave    `$a000`; the Line-A mouse form (74 bytes) saved, where it lives kept
 *   $fee4c0 gsx_mfrestore ...and copied back there
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h` and `aes/gsx.h`.
 */
#ifndef TOS102US_AES_GSXIF_H
#define TOS102US_AES_GSXIF_H

/* GUARDED as `aes/gsx.h` is: `src/aes/gsxif.S` reads the fields, and everything outside the guards is a plain integer
 * `#define` both languages read. */
#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"
#include "aes/aes.h"
#include "aes/gsx.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"

/* ---- the screen's metrics gsx_start sets, beside `aes/aes.h`'s AES_GL_WIDTH .. AES_GL_HBOX ---------------------- */
#define AES_GL_NROWS          0x9ba2     /* word: cells down, gl_height / gl_hchar ($fdab94 move.w d0)          */
#define AES_GL_WBOX           0x9ad6     /* word: a box's width, gl_hbox in the pixels' aspect ($fdabac)        */
/* The two fonts' sizes, as vqt_attributes answers the current one (the large) and vst_height the small one. */
#define AES_GL_WPTSCHAR       0x9c08     /* word: the large font's character width ($fdab34 move.w (a1)+)       */
#define AES_GL_HPTSCHAR       0x9ad2     /* word: ...and height                ($fdab3e move.w (a1)+)          */
#define AES_GL_WSPTSCHAR      0x9c0a     /* word: the small font's character width ($fdab66 pea, vst_height's) */
#define AES_GL_HSPTSCHAR      0x9ad4     /* word: ...and height                ($fdab60 pea)                   */
#define AES_GL_WSCHAR         0x97f4     /* word: ...its cell's width          ($fdab5a pea)                   */
#define AES_GL_HSCHAR         0xc842     /* word: ...and height                ($fdab54 pea)                   */
/* A seventh attribute cache gsx_start fills with -1 beside `gsx.h`'s six — and nothing in the AES reads it. */
#define AES_GL_DEAD_CACHE     0xc916     /* word                               ($fdaac2 move.w d0)             */
/* The five rectangles, each a GRECT (`aes/aes.h`'s GRECT_*). */
#define AES_GL_RSCREEN        0x98a4     /* bytes[GRECT_BYTES]: the whole screen ($fdabc8 lea)                 */
#define AES_GL_RFULL          0x98ac     /* bytes[GRECT_BYTES]: below the menu bar ($fdabd4 lea)               */
#define AES_GL_RZERO          0x9b30     /* bytes[GRECT_BYTES]: nothing        ($fdabe4 lea)                   */
#define AES_GL_RMENU          0x971c     /* bytes[GRECT_BYTES]: the menu bar   ($fdabee lea)                   */
#define AES_GL_RCENTER        0xc862     /* bytes[GRECT_BYTES]: a box centred on the screen ($fdabfa lea)      */

/* ---- the workstation: the device code gsx_wsopen hands v_opnwk and sets from the size answered ----------------- */
#define AES_GL_RESTYPE        0x8908     /* word: the device code              ($fe888c move.w $8908,(a2))     */
#define AES_GL_RSCHANGE       0x890a     /* word: a resolution change asked    ($fe88ce clr.w)                 */
/* gsx_wsopen's intin: ten 1s, the coordinates' word, then the device code over the first ($fe887e..$fe888c). */
#define GSX_OPEN_WORDS        10         /* ($fe887e moveq #9: dbf)                                            */
#define GSX_OPEN_ATTRIBUTE    1
#define GSX_OPEN_COORDINATES  2          /* intin[10]: raster coordinates      ($fe8888 move.w #2)             */
/* The device codes it sets from work_out[0..1]: 319 wide is low resolution, 399 high is high (`vdi/workstation.h`'s
 * VDI_OPNWK_HIGH_MAX_Y, $fe88c4 cmpi.w #399), any other medium. */
#define GSX_RESTYPE_LOW       2
#define GSX_RESTYPE_MEDIUM    3
#define GSX_RESTYPE_HIGH      4
#define GSX_LOW_XRES          319        /* ($fe88b8 cmpi.w #319)                                              */
/* AES_GL_GRAPHIC's two modes: graphics, as gsx_wsopen leaves it ($fe88d4 move.w #1), and the alpha screen. */
#define GSX_ALPHA             0
#define GSX_GRAPHIC           1
/* v_opnwk's answer: intout's 45 words (DEV_TAB), then ptsout ($fe8ac0 lea 90(a1)). */
#define GSX_WS_INTOUT_BYTES   (VDI_DEV_TAB_WORDS * VDI_WORD_BYTES)
/* work_out's words gsx_start reads are `aes/gsx.h`'s GSX_WS_* (gsx_fix reads two of them too). */

/* ---- the mouse's routines: the two the AES's interrupt glue installs, what they displaced ----------------------- */
#define AES_OLD_BUTTON        0xc7fc     /* long: the button routine displaced ($fe89d4 move.l $c7f2)         */
#define AES_OLD_MOTION        0xc91c     /* long: the motion routine displaced ($fe89ec move.l $c7f2)         */
/* gsx_setmb's third argument, pushed and never read: GEM's `&drwaddr`, the cursor routine its vex_curv once took. */
#define AES_DRWADDR           0x947a     /* long                               ($fe883e pea)                   */
/* The interrupt GLUE gsx_setmb_aes pushes is `addrs.h`'s AES_ROM_BUTTON_GLUE / AES_ROM_MOTION_GLUE. */

/* ---- the save-under buffer and the mouse state ------------------------------------------------------------------ */
#define GSX_SAVE_BUFFER_BYTES 0x3400     /* gl_tmp's buffer                    ($fe879c pea $3400)             */
#define AES_GL_MLEN           0xc920     /* long: gsx_mret's length — which nothing in the AES writes ($fe87ca) */
#define AES_KSTATE            0xc72a     /* word: the keyboard's shift state   ($fe5184)                       */
/* gsx_malloc's dos_free call returns here, the word after its Line-F call: what dos_free parks (a host argument). */
#define AES_GSX_MFREE_RETURN  0xfe87b8

/* ---- the mouse FORM: the Line-A block's sprite form from M_POS_HX on, saved and put back ------------------------ */
#define AES_MFORM_AT          0x9560     /* long: where the Line-A form lives  ($fee4a0 move.l a0)             */
#define AES_MFORM_SAVE        0x9564     /* bytes[GSX_MOUSE_FORM_BYTES]: the form saved ($fee4ac move.l #)    */
/* The form: hot spot, planes, two colours (`vdi/mouse.h`'s SPRITE_FORM_*), sixteen rows of mask and data — 74
 * bytes ($fee4a6 move.w #74), 37 words (gsx_mfset's `moveq #36`: dbf). A number, for the width tag above (`test/aes.py`
 * parses this header alone); `gsxif.c` holds it to the sprite form's layout. */
#define GSX_MOUSE_FORM_BYTES  74
#define GSX_MOUSE_FORM_WORDS  (GSX_MOUSE_FORM_BYTES / VDI_WORD_BYTES)
/* $a000 answers the block's base; the form is $358 below it ($fee49a suba.l #$358,a0). */
#define GSX_MOUSE_FORM_BELOW_LINEA (LINEA_BASE - LINEA_M_POS_HX)

#ifndef __ASSEMBLER__
/* ---- the routines ------------------------------------------------------------------------------------------------ */
void aes_gr_mkstate(uint8_t *image, uint32_t mouse_x, uint32_t mouse_y, uint32_t buttons, uint32_t keys);
                                                                                                    /* $fe8768 */
void aes_gsx_malloc(uint8_t *image);                                                                /* $fe8790 */
void aes_gsx_mfree(uint8_t *image);                                                                 /* $fe87b0 */
void aes_gsx_mret(uint8_t *image, uint32_t address, uint32_t length);                               /* $fe87bc */
void aes_gsx_init(uint8_t *image);                                                                  /* $fe8808 */
void aes_gsx_graphic(uint8_t *image, int16_t graphic);                                              /* $fe8828 */
void aes_gsx_setmb_aes(uint8_t *image);                                                             /* $fe883e */
void aes_gsx_escapes(uint8_t *image, int16_t escape);                                               /* $fe8866 */
void aes_gsx_wsopen(uint8_t *image);                                                                /* $fe8876 */
void aes_gsx_wsclose(uint8_t *image);                                                               /* $fe88de */
void aes_ratinit(uint8_t *image);                                                                   /* $fe88e4 */
void aes_bb_set(uint8_t *image, int16_t x, int16_t y, int16_t width, int16_t height, uint32_t screen_corners,
                uint32_t form_corners, uint32_t screen_mfdb, uint32_t source, uint32_t destination);  /* $fe88f8 */
void aes_bb_save(uint8_t *image, uint32_t rect);                                                    /* $fe8966 */
void aes_bb_restore(uint8_t *image, uint32_t rect);                                                 /* $fe8996 */
void aes_gsx_setmb(uint8_t *image, uint32_t button, uint32_t motion, uint32_t cursor);              /* $fe89c6 */
void aes_gsx_resetmb(uint8_t *image);                                                               /* $fe89f8 */
uint16_t aes_gsx_tick(uint8_t *image, uint32_t routine, uint32_t old);                              /* $fe8a18 */
void aes_gsx_mfset(uint8_t *image, uint32_t form);                                                  /* $fe8a38 */
void aes_gsx_mxmy(uint8_t *image, uint32_t mouse_x, uint32_t mouse_y);                              /* $fe8a54 */
uint16_t aes_gsx_button(uint8_t *image);                                                            /* $fe8a6a */
void aes_v_opnwk(uint8_t *image, uint32_t work_in, uint32_t handle, uint32_t work_out);              /* $fe8aae */
void aes_gsx_start(uint8_t *image);                                                                 /* $fdaab0 */
void aes_gsx_mfsave(uint8_t *image);                                                                /* $fee498 */
void aes_gsx_mfrestore(uint8_t *image);                                                             /* $fee4c0 */
#endif /* !__ASSEMBLER__ */

#endif /* TOS102US_AES_GSXIF_H */
