/* aes/wmupdate.h — the WINDOW LIBRARY's half that reaches the event layer (`src/aes/wmupdate.c`): a window's change
 * drawn (draw_change, w_update, w_redraw — the redraw messages its owners get), the top window's owner given the
 * mouse and the keyboard (w_setactive), the screen lock (wm_update) and the form manager's ownership of the screen
 * (fm_own), and the four wind_* calls built on them (wm_opcl, wm_open, wm_close, wm_set); and the control manager's
 * three leaves they and the ROM's ct_chgown use (get_ctrl, set_ctrl, get_mown).
 *
 * ALL ALCYON C, entered by a Line-F call over the frame its caller pushed. The event layer and the scheduler they call
 * — tak_flag, unsync, ev_block, ct_chgown, ap_rdwr under ap_sendmsg — are the event door's (`aes/evdoor.h`).
 *
 * WHAT A CALLER READS IN D0. The desk's bindings (`$fdde54..$fde4cc`) store D0.w of wind_open, wind_close, wind_set
 * and wind_update as the call's answer, so wm_open, wm_close, wm_set and wm_update — and wm_opcl and fm_own under
 * them — answer the word the ROM leaves there: each ends on a door call (unsync, tak_flag or ct_chgown), whose D0 the
 * door answers. unsync with the lock still held afterwards answers the D0 IT WAS ENTERED WITH, its caller's — which
 * no C has (`wmupdate.c`, wm_update). The rest answer nothing a caller reads.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG").
 */
#ifndef TOS102US_AES_WMUPDATE_H
#define TOS102US_AES_WMUPDATE_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- the SCREEN LOCK: GEM's semaphore (`wind_spb`), a nesting count, its owner and the waits queued on it ------- */
#define AES_WIND_SPB          0x9aee     /* bytes[SPB_BYTES]                    ($feca7e move.l #$9aee,(sp))   */
#define SPB_COUNT             0          /* word: how deep the owner holds it   ($fe4e66 addq.w #1,(a5))       */
#define SPB_OWNER             2          /* long: the PD holding it             ($fe4e82 move.l $c794,2(a5))   */
#define SPB_WAIT              6          /* long: the EVBs waiting for it       ($fe4eca movea.l 6(a5),a4)     */
#define SPB_BYTES             10
/* ...the address ev_block is handed to wait on it by: start-up's copy of `&wind_spb`. A `ctx` name. */
#define AES_AD_WINDSPB        0xc83e     /* long                                ($feca8a move.l $c83e,(sp))    */

/* wind_update's CODES, wm_update's argument: 0 and 1 the lock released and taken, 2 and 3 the screen's ownership given
 * back and taken (fm_own(code - 2), `subq.w #2`) — compared SIGNED (`cmp.w #2; bge`), any other word below 2 taking
 * the lock as 1 does (`tst.w; beq`). */
#define WM_END_UPDATE         0
#define WM_BEG_UPDATE         1
#define WM_END_MCTRL          2          /* ($feca74 cmp.w #2,d7)                                              */
#define WM_BEG_MCTRL          3
#define EV_BLOCK_MUTEX        4          /* ev_block's code: wait for a semaphore ($feca90 move.w #4)          */

/* ---- the form manager's hold on the screen (fm_own) — what it took, given back when its count unwinds ----------- */
#define AES_FM_OWN_COUNT      0x9450     /* word: how deep fm_own holds it      ($fe719e tst.w)                */
#define AES_FM_OWN_MENU       0x9452     /* long: gl_mntree, put aside          ($fe71a6 move.l $9b26,$9452)   */
#define AES_FM_OWN_CTRL       0x9456     /* bytes[GRECT_BYTES]: the control rectangle, put aside ($fe71b6)     */
#define AES_FM_OWN_MOUSE      0x945e     /* long: the mouse's owner, put aside  ($fe71c4 move.l #$945e)        */
#define AES_FM_OWN_KEYBOARD   0x9462     /* long: the keyboard's owner, put aside ($fe71be move.l #$9462)      */

/* ---- the CONTROL MANAGER's state the three leaves read and write ------------------------------------------------- */
#define AES_CTRL_RECT         0x9b3e     /* bytes[GRECT_BYTES]: the screen manager's own rectangle ($fe500c)   */
#define AES_GL_MOWNER         0x9afa     /* long: the PD the mouse belongs to   ($fe5038 move.l $9afa,(a0))    */
#define AES_GL_KOWNER         0x9ad8     /* long: ...and the keyboard           ($fe5042 move.l $9ad8,(a0))    */

/* ---- the window library's own -------------------------------------------------------------------------------------- */
/* Whether the window wind_set(WF_TOP) brings up was whole — none of it covered (WIN_BROKEN clear) — so draw_change can
 * redraw its gadgets alone. Written by wm_set, read by draw_change. A `ctx` name. */
#define AES_GL_WASCLR         0xc93e     /* word                                ($fec8a6 move.w d0,$c93e)      */
/* The message buffer w_redraw builds every WM_REDRAW in. */
#define AES_GL_RMSG           0x9adc     /* bytes[AP_MSG_BYTES]                 ($febebe move.l #$9adc,-(sp))  */
#define WM_REDRAW             20         /* the message's type                 ($febeba move.w #20)            */

/* wind_set's FIELDS, wm_set's switch (`subq.w #2` / `cmp.w #14`, `bhi` past it; table $fefd16, a row each from
 * WF_NAME): the rest of the numbers (`aes/wmlib.h`'s WF_*) share them. Fields 4, 6, 7, 11 and 12 have no arm. */
#define WF_NAME               2          /* ($fec866 move.w #3: W_NAME)                                        */
#define WF_INFO               3          /* ($fec870 move.w #5: W_INFO)                                        */
/* WF_NEWDESK's words: the tree's address, a longword, then the object it is drawn from. */
#define WF_NEWDESK_ROOT       4          /* ($fec90e move.w 4(a5),$9ab6)                                       */
/* A slider's position or size, clamped to -1..W_SLIDER_SCALE in the caller's word ($fec91c, $fec928). */
#define WM_SLIDER_FLOOR       (-1)

/* wm_opcl's third argument: the window added to the window tree (wm_open's) or taken out (wm_close's, which hands
 * gl_rzero for the rectangle it no longer has, $fec6f6 move.l #$9b30). */
#define WM_OPCL_REMOVE        0          /* ($fec6f4 clr.w (sp))                                               */
#define WM_OPCL_ADD           1          /* ($fec6de move.w #1,(sp))                                           */
/* wind_calc's type draw_change asks for: the work area from the border (any non-zero, `aes/wmlib.h`'s WC_BORDER the
 * other way). */
#define WC_WORK               1          /* ($fec134 move.w #1)                                                */

#ifndef __ASSEMBLER__
void aes_set_ctrl(uint8_t *image, uint32_t rect);                                                     /* $fe5008 */
void aes_get_ctrl(uint8_t *image, uint32_t rect);                                                     /* $fe501c */
void aes_get_mown(uint8_t *image, uint32_t mouse_out, uint32_t keyboard_out);                        /* $fe5030 */
uint16_t aes_fm_own(uint8_t *image, int16_t take);                                                   /* $fe718e */
void aes_w_setactive(uint8_t *image);                                                                 /* $feba54 */
void aes_w_redraw(uint8_t *image, int16_t window, uint32_t rect);                                    /* $febe2a */
void aes_w_update(uint8_t *image, int16_t bottom, uint32_t rect, int16_t top, int16_t moved);       /* $fec026 */
void aes_draw_change(uint8_t *image, int16_t window, uint32_t rect);                                 /* $fec0ca */
uint16_t aes_wm_opcl(uint8_t *image, int16_t window, uint32_t rect, int16_t add);                   /* $fec676 */
uint16_t aes_wm_open(uint8_t *image, int16_t window, uint32_t rect);                                 /* $fec6da */
uint16_t aes_wm_close(uint8_t *image, int16_t window);                                                /* $fec6f0 */
uint16_t aes_wm_set(uint8_t *image, int16_t window, int16_t field, uint32_t words);                 /* $fec83a */
uint16_t aes_wm_update(uint8_t *image, int16_t code);                                                 /* $feca68 */
#endif

#endif /* TOS102US_AES_WMUPDATE_H */
