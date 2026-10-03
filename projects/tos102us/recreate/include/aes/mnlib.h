/* aes/mnlib.h — the MENU LIBRARY (`src/aes/mnlib.c`): the menu bar shown and hidden, its titles and items changed, the
 * drop-downs saved and drawn, mn_do's tracking of the mouse through them, and the desk accessories' slots — gemmnlib,
 * all Alcyon C, entered by a Line-F call over the frame its caller pushed; and pd_nameit, the scheduler's leaf that
 * names a process (the scheduler's code, non-blocking, its callees ported).
 *
 * THE MENU TREE is an application's (gl_mntree, `aes/aes.h`'s AES_GL_MNTREE): its root's first child is the BAR, the
 * bar's only child the ACTIVE box the titles are children of, the titles from object 3 on; the root's LAST child is
 * the box the drop-downs are children of, the n-th drop-down the n-th title's. The first drop-down is the DESK
 * menu's, whose items from the third on are the registered accessories' (mn_bar rebuilds it).
 *
 * WHAT A CALLER READS IN D0: do_chg, menu_set, menu_down, mn_do and mn_register answer a word their callers read;
 * rect_change, menu_sr, mn_bar, mn_clsda and pd_nameit leave a callee's D0, which no caller reads (the dispatcher's
 * menu_bar arm answers its own 1, `$fe64de`), and answer nothing here.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h`.
 */
#ifndef TOS102US_AES_MNLIB_H
#define TOS102US_AES_MNLIB_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- the menu tree's objects ---------------------------------------------------------------------------------------- */
#define MN_THEBAR             1          /* the bar                             ($fe914a move.w #1: ob_draw's start) */
#define MN_THEACTIVE          2          /* the titles' box                     ($fe904a move.w #2: ob_actxywh) */
#define MN_DRAW_DEPTH         8          /* ob_draw's depth: the whole subtree  ($fe9146 move.w #8)            */
/* menu_down walks from the first drop-down to title t's by t - 3 ob_nexts: `t - 2`, then one step while above 1. */
#define MN_DOWN_WALK_FROM     2          /* ($fe8d1c subq.w #2,d4)                                             */
#define MN_DOWN_WALK_UNTIL    1          /* ($fe8d2e cmpw #1,d4; bgt)                                          */
/* The state mn_do will not drop a title for, nor end on outside the bar: DISABLED and nothing else — compared EQUAL,
 * not tested by its bit ($fe8efc cmpi.w #8). */
#define MN_DISABLED_ALONE     0x0008
/* The bit menu_set and menu_down change: SELECTED (`aes/objects.h`'s OB_STATE_SELECTED_BIT). */
#define MN_SELECTED           0x0001     /* ($fe8c96 move.w #1: do_chg's bits)                                 */
/* do_chg's last argument: an item whose state is DISABLED (its bit, `btst #3`) is left alone. */
#define MN_CHECK_DISABLED     1          /* ($fe8c92 move.w #1,(sp))                                           */
#define MN_REDRAW             1
#define MN_NO_REDRAW          0
#define MN_SET                1
#define MN_CLEAR              0

/* menu_sr's rectangle: the drop-down's, one pixel more on the left and two more across and down — its shadow. */
#define MN_SR_LEFT_EDGE       1          /* ($fe8cd2 subq.w #1,-8(a6))                                         */
#define MN_SR_SHADOW          2          /* ($fe8cd6 addq.w #2,-4(a6); $fe8cda addq.w #2,-2(a6))               */

/* ---- mn_do's tracking: where the mouse was last seen (its state word, -38(a6)) ------------------------------------- */
#define MN_IN_BAR             1          /* waiting to enter the titles         ($fe8d7c move.w #1,-38(a6))    */
#define MN_ON_TITLE           2          /* a title dropped, waiting to leave it ($fe8f06 move.w #2)           */
#define MN_IN_MENU            3          /* on an item of the dropped menu      ($fe8f36 moveq #3)             */
#define MN_OUT_OF_MENU        4          /* below the bar, off the dropped menu  ($fe8f3a moveq #4)             */
/* The button wait mn_do hands ev_multi: one click, the left button, the state wanted — down (1) until an item is
 * reached with the button down, then up (`aes/evdoor.h`'s EV_BUTTON_PARAMETER). */
#define MN_BUTTON_DOWN        1          /* ($fe8d86 move.l #$10101,-4(a6))                                    */
#define MN_BUTTON_UP          0          /* ($fe8e1c move.l #$10100,d0)                                        */
#define MN_BUTTON_STATE_BIT   1          /* the state's bit, flipped on a title ($fe8eac eori.l #1,-4(a6))     */

/* ---- mn_do's frame locals whose ADDRESS it hands on: ev_multi's answers and two MOBLKs (rect_change's) -------------- */
/* Words, compacted (the ROM's: the answers at -52(a6), the second MOBLK at -36(a6), the first at -26(a6)). */
#define MN_DO_ANSWERS         0          /* words[EV_MULTI_ANSWER_WORDS]: the mouse x, y first ($fe8e64 -52(a6)) */
#define MN_DO_SECOND_RECT     12         /* words[EV_MOBLK_WORDS]: the bar left  ($fe8dcc -36(a6))             */
#define MN_DO_FIRST_RECT      22         /* words[EV_MOBLK_WORDS]: a title or item entered or left ($fe8e52 -26(a6)) */
#define MN_DO_FRAME_WORDS     16         /* (12 + 10 + 10) bytes                                               */

/* ---- the menu library's globals -------------------------------------------------------------------------------------- */
/* The screen manager's mouse wait: the MOBLK its evnt_multi waits for the mouse to enter, the titles' box — mn_bar
 * sets its rectangle (GEM's gl_ctwait.m_x); and the rectangle the screen manager re-arms it from (gl_rmnactv). */
#define AES_GL_CTWAIT_RECT    0xc928     /* bytes[GRECT_BYTES]                  ($fe9044 move.l #$c928,(sp))   */
#define AES_GL_RMNACTV        0x96da     /* bytes[GRECT_BYTES]                  ($fe9054 move.l #$96da,(sp))   */
/* Whose menu it is: the running process's id, stored SIGN-EXTENDED AS A LONGWORD ($fe906e ext.l) — and read back by
 * the screen manager as the WORD at the same address ($fe4998 move.w $9730,d7), the longword's high half. */
#define AES_GL_MNPPD          0x9730     /* long                                ($fe9070 move.l d0,$9730)      */
/* The desk menu: the drop-down the accessories' items are added to, and the item index of the first accessory. */
#define AES_GL_DABOX          0xc686     /* word                                ($fe908a move.w (a0),$c686)    */
#define AES_GL_DAFIRST        0x9bc0     /* word: the box's index + 3           ($fe90d4 move.w d0,$9bc0)      */
/* The registered accessories: how many, each one's process id and its item's text. */
#define AES_GL_DACNT          0xc684     /* word                                ($fe924a addq.w #1,$c684)      */
#define AES_DESK_PID          0xc930     /* words[MN_DA_SLOTS]                  ($fe9230 adda.l #$c930)        */
#define AES_DESK_ACC          0xc6ce     /* longs[MN_DA_SLOTS]                  ($fe9242 adda.l #$c6ce)        */
#define MN_DA_SLOTS           6          /* ($fe921e cmpi.w #6,$c684)                                          */
/* The desk menu's items before the accessories': the desk's own, and the line under it. */
#define MN_DESK_ITEMS         2          /* ($fe90ca addq.w #2,d3; $fe90f6 cmpw #2,d6)                         */
#define MN_DESK_ALONE         1          /* ...no accessory: the desk's own item alone ($fe90dc moveq #1,d3)   */
#define MN_DAFIRST_PAST_BOX   3          /* ($fe90d2 addq.w #3,d0)                                             */
/* The clicks mn_bar's post_button will hand the screen manager, which its button handler swallows one by one
 * ($fe48de tst.w $c6cc; subq.w #1) — the bar's fake click, sent to make it re-arm its mouse wait. */
#define AES_GL_MNCLICKS       0xc6cc     /* word                                ($fe918a addq.w #1,$c6cc)      */
/* The screen manager's PD, and the message buffer it and mn_clsda send from. */
#define AES_CTL_PD            0x9b3a     /* long                                ($fda1de move.l d0,$9b3a)      */
#define AES_CT_MESSAGE        0x98b4     /* bytes[MN_MESSAGE_BYTES]             ($fe91c8 move.l #$98b4,-(sp))  */
#define MN_MESSAGE_BYTES      16         /* `aes/apmsg.h`'s AP_MSG_BYTES (`mnlib.c` holds them equal)            */
/* mn_bar's fake click: the left button, one click ($fe9190 move.w #1,(sp); move.w #1,-(sp)). */
#define MN_BAR_BUTTON         1
#define MN_BAR_CLICKS         1
/* mn_clsda's message: AC_CLOSE ($fe91c4 move.w #41,-(sp)). */
#define MN_AC_CLOSE           41

/* ---- mn_register: a process's own name, copied into its frame first (-14(a6), `link a6,#-14`) -------------------- */
#define MN_REGISTER_NAME_BYTES 14
#define MN_REGISTER_PROCESS   (-1)       /* the pid that names the caller's process ($fe91f2 cmp.w #-1,d7)     */
#define MN_REGISTER_FULL      (-1)       /* ($fe925c moveq #-1,d0)                                             */
#define MN_REGISTER_NAMED     1          /* ($fe9218 moveq #1,d0)                                              */
/* pd_nameit: the name blank-filled, then copied up to its extension's dot. */
#define PD_NAME_FILL          0x20       /* ' '                                 ($fe5864 move.l #$80020)       */
#define PD_NAME_STOP          0x2e       /* '.'                                 ($fe586e move.w #46)           */

#ifndef __ASSEMBLER__
void aes_rect_change(uint8_t *image, uint32_t tree, uint32_t moblk, int16_t object, int16_t leave);       /* $fe8bf4 */
int16_t aes_do_chg(uint8_t *image, uint32_t tree, int16_t item, uint16_t bits, int16_t set, int16_t redraw,
                   int16_t check_disabled);                                                                 /* $fe8c14 */
int16_t aes_menu_set(uint8_t *image, uint32_t tree, int16_t last, int16_t current, int16_t set);         /* $fe8c7a */
void aes_menu_sr(uint8_t *image, int16_t save, uint32_t tree, int16_t menu);                               /* $fe8cb6 */
int16_t aes_menu_down(uint8_t *image, uint32_t tree, int16_t title);                                      /* $fe8cf4 */
int16_t aes_mn_do(uint8_t *image, uint32_t title_out, uint32_t item_out);                                  /* $fe8d6e */
void aes_mn_bar(uint8_t *image, uint32_t tree, int16_t show);                                              /* $fe902a */
void aes_mn_clsda(uint8_t *image);                                                                         /* $fe91a4 */
int16_t aes_mn_register(uint8_t *image, int16_t pid, uint32_t name);                                       /* $fe91e2 */
void aes_pd_nameit(uint8_t *image, uint32_t pd, uint32_t name);                                            /* $fe5856 */
#endif

#endif /* TOS102US_AES_MNLIB_H */
