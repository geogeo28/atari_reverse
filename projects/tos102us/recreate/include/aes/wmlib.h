/* aes/wmlib.h — the WINDOW LIBRARY (`src/aes/wmlib.c`): the gadget tree a window is drawn with, built and drawn, and
 * the window records claimed, read out and freed — gemwmlib's half that never waits on an event.
 *
 * ALL ALCYON C, entered by a Line-F call over the frame its caller pushed. A window is drawn as TWO trees: the window
 * tree (`aes/aes.h`'s AES_WINDOW_TREE, an object per window, where each one is) and W_ACTIVE (AES_W_ACTIVE), the
 * gadgets of ONE window, rebuilt by w_bldactive for each window drawn — its objects are the W_* below, the window's
 * kind (`WIN_KIND`) says which are built. The records and globals are `aes/aes.h`'s.
 *
 * WHAT A CALLER READS IN D0. The desk's bindings (`$fdde54..$fde4cc`) store D0.w of wm_create, wm_delete, wm_get,
 * wm_find and wm_calc as the call's answer, so each core answers the word the ROM leaves there — wm_delete's and some
 * of wm_get's arms an address's low word, wm_calc's the last height it stored — and is held to it.
 */
#ifndef TOS102US_AES_WMLIB_H
#define TOS102US_AES_WMLIB_H

#include <stdint.h>

#include "aes/objects.h"

/* ---- W_ACTIVE's objects, by index (w_bldactive's and w_bldbar's constants) ---------------------------------------- */
#define W_BOX                 0          /* the root: the window's whole rectangle ($febb22 move.l #$98fe: its ob_x) */
#define W_TITLE               1          /* the title bar                       ($febb56 move.w #1)            */
#define W_CLOSER              2          /* ($febb82 move.l #$10002)                                           */
#define W_NAME                3          /* the title's text                    ($febbe4 move.l #$10003)       */
#define W_FULLER              4          /* ($febbc6 move.l #$10004)                                           */
#define W_INFO                5          /* the information line                ($febc36 move.w #5)            */
#define W_DATA                6          /* below the bars: the work area and the scroll bars ($febc62 move.w #6) */
#define W_WORK                7          /* ($febcc6 move.l #$60007)                                           */
#define W_SIZER               8          /* ($febd8e move.l #$60008)                                           */
#define W_VBAR                9          /* the vertical scroll bar             ($febd12 move.w #9)            */
#define W_UPARROW             10         /* ($feb890 moveq #10)                                                */
#define W_DNARROW             11         /* ($feb892 move.w #11)                                               */
#define W_VSLIDE              12         /* the vertical slider's track         ($feb898 move.w #12)           */
#define W_VELEV               13         /* ...and its elevator                 ($feba0c moveq #13)            */
#define W_HBAR                14         /* the horizontal scroll bar           ($febd66 move.w #14)           */
#define W_LFARROW             15         /* ($feb8ba moveq #15)                                                */
#define W_RTARROW             16         /* ($feb8bc move.w #16)                                               */
#define W_HSLIDE              17         /* ($feb8c2 move.w #17)                                               */
#define W_HELEV               18         /* ($feba10 moveq #18)                                                */
#define W_ACTIVE_OBJECTS      19         /* w_nilit's count                     ($febae2 move.w #19)           */

/* ---- a window's KIND: its gadgets, one bit each -------------------------------------------------------------------- */
#define WK_NAME               0x0001     /* a title                             ($febbd4 btst #0)              */
#define WK_CLOSER             0x0002     /* ($febb68 btst #1)                                                  */
#define WK_FULLER             0x0004     /* ($febb9e btst #2)                                                  */
#define WK_INFO               0x0010     /* an information line                 ($febc24 btst #4)              */
#define WK_SIZER              0x0020     /* ($febda2 btst #5)                                                  */
#define WK_UPARROW            0x0040     /* ($feb87e move.w #64)                                               */
#define WK_DNARROW            0x0080     /* ($feb884 move.w #128)                                              */
#define WK_VSLIDE             0x0100     /* ($feb88a move.w #256)                                              */
#define WK_LFARROW            0x0200     /* ($feb8a8 move.w #512)                                              */
#define WK_RTARROW            0x0400     /* ($feb8ae move.w #1024)                                             */
#define WK_HSLIDE             0x0800     /* ($feb8b4 move.w #2048)                                             */
/* ...and the groups the border is laid out by: any title gadget makes a title bar, any vertical one (or the sizer) a
 * vertical bar, any horizontal one (or the sizer) a horizontal bar. */
#define WK_TITLE_BAR          0x0007     /* NAME, CLOSER, FULLER                ($febb42 andi.w #7)            */
#define WK_VERTICAL_BAR       0x01e0     /* SIZER, UPARROW, DNARROW, VSLIDE     ($febc80 andi.w #480)          */
#define WK_HORIZONTAL_BAR     0x0e20     /* SIZER, LFARROW, RTARROW, HSLIDE     ($febc86 andi.w #3616)         */

/* ---- what the gadgets are drawn as -------------------------------------------------------------------------------- */
#define W_NAME_COLOUR_TOP     0x11a1     /* the title's te_color on the top window ($febbf8 move.w #4513)      */
#define W_NAME_COLOUR         0x1100     /* ...on any other                     ($febc02 move.w #4352)         */
#define W_SIZER_SPEC_TOP      0x06011100 /* the sizer's ob_spec, drawn, on the top window ($febda8 move.l)     */
#define W_SIZER_SPEC          0x00011100 /* ...a blank box on any other          ($febdb0 move.l #69888)       */
#define W_SLIDER_SCALE        1000       /* a slider's position and size, per mille ($feb7ec move.w #1000)     */
#define W_EDGE                1          /* ...one side: the work area inset     ($febc70 addq.w #1)           */
#define W_BAR_OVERLAP         1          /* adjacent gadgets share one line of border ($feb930 subq.w #1)      */
#define WM_MAX_DEPTH          8          /* ob_draw's depth for a whole tree     ($feb6e2 moveq #8, $feb7bc)    */
#define WM_SCREEN_TO_SCREEN   3          /* bb_screen's rule: the source copied ($febfc8 move.w #3)             */

/* ---- wm_start's tables, from the ROM's: W_ACTIVE's types ($fefc3c) and specs ($fefc62), and the TEDINFO the title
 * and information line are copied from ($fefcae) ----------------------------------------------------------------- */
#define W_TREE_ROOT_TYPE      G_BOX      /* the window tree's root: the desktop pattern ($fec494 move.w #20)   */
#define W_TREE_WINDOW_TYPE    G_IBOX     /* ...each window's object             ($fec486 move.w #25)           */
#define W_ACTIVE_ROOT_STATE   0x0020     /* SHADOWED (OB_STATE_SHADOWED_BIT)     ($fec514 move.w #32)          */
#define W_TITLE_JUST          2          /* the title's te_just: centred        ($fec5e4 move.w #2)            */
#define W_TEDINFO_FONT        3          /* the template's te_font: the IBM font ($fefcba)                     */
#define W_TEDINFO_RESERVED    1          /* ...its te_resvd1                     ($fefcbc)                     */
#define W_TEDINFO_COLOUR      W_NAME_COLOUR  /* ...its te_color                  ($fefcc0)                     */
#define W_TEDINFO_THICKNESS   1          /* ...its te_thickness                 ($fefcc4)                      */
#define W_TEDINFO_LENGTH      80         /* ...its te_txtlen and te_tmplen      ($fefcc6, $fefcc8)             */
#define WM_DESKTOP            0          /* window 0, the desktop's             ($fec54c clr.l: handle and kind) */

/* ---- wind_get's FIELDS, wm_get's switch (`subq.w #4` / `cmp.w #13`, `bhi` the default; table $fefcde, a row each
 * from WF_FIRST): the four rectangles' arms hand w_getsize WS_WORK/CURR/PREV/FULL ($fec742..$fec754), the slider
 * arms read the record ($fec75a..$fec790, $fec77e..), WF_TOP gl_wtop ($fec7a2), the two list arms w_owns ($fec7ba). */
#define WF_WORKXYWH           4
#define WF_CURRXYWH           5
#define WF_PREVXYWH           6
#define WF_FULLXYWH           7
#define WF_HSLIDE             8
#define WF_VSLIDE             9
#define WF_TOP                10
#define WF_FIRSTXYWH          11
#define WF_NEXTXYWH           12
/* Field 13: no arm in wind_get ($fefd02 -> $fec828, the switch's end); wind_set's holds window drawing for a
 * non-zero handle, releases it for 0 (`aes/aes.h`'s AES_GL_WFROZEN, $fec8e4 / $fec8ee). */
#define WF_RESVD              13
#define WF_NEWDESK            14         /* no arm in wind_get                  ($fefd06 -> $fec828)           */
#define WF_HSLSIZE            15
#define WF_VSLSIZE            16
#define WF_SCREEN             17         /* the save buffer's address and length: gsx_mret ($fec80a)           */
#define WF_FIRST              WF_WORKXYWH  /* ($fec812 subq.w #4)                                              */
/* wind_calc's TYPE: 0 the border from the work area, any other the work area from the border ($fecb06 tst.w). */
#define WC_BORDER             0

void aes_w_nilit(uint8_t *image, int16_t count, uint32_t objects);                                    /* $feb3c0 */
void aes_w_obadd(uint8_t *image, uint32_t objects, int16_t parent, int16_t child);                    /* $feb408 */
void aes_w_setup(uint8_t *image, uint32_t pd, int16_t window, int16_t kind);                          /* $feb47a */
void aes_w_setsize(uint8_t *image, int16_t which, int16_t window, uint32_t rect);                     /* $feb57c */
void aes_w_adjust(uint8_t *image, int16_t parent, int16_t object, int16_t x, int16_t y, int16_t w,
                  int16_t h);                                                                          /* $feb594 */
void aes_w_hvassign(uint8_t *image, int16_t vertical, int16_t parent, int16_t object, int16_t vertical_x,
                    int16_t vertical_y, int16_t horizontal_x, int16_t horizontal_y, int16_t w, int16_t h); /* $feb5f8 */
int16_t aes_w_clipdraw(uint8_t *image, int16_t window, uint32_t tree, int16_t object, int16_t depth,
                       uint32_t clip);                                                                 /* $feb646 */
void aes_w_drawdesk(uint8_t *image, uint32_t rect);                                                   /* $feb6c8 */
void aes_w_cpwalk(uint8_t *image, int16_t window, int16_t object, int16_t depth, int16_t use_true);  /* $feb712 */
void aes_w_strchg(uint8_t *image, int16_t window, int16_t object, uint32_t text);                     /* $feb768 */
void aes_w_barcalc(uint8_t *image, int16_t vertical, int16_t space, int16_t value, int16_t size, int16_t minimum,
                   uint32_t vertical_rect, uint32_t horizontal_rect);                                 /* $feb7ca */
void aes_w_bldbar(uint8_t *image, int16_t kind, int16_t is_top, int16_t bar, int16_t value, int16_t size, int16_t x,
                  int16_t y, int16_t w, int16_t h);                                                    /* $feb84e */
void aes_w_bldactive(uint8_t *image, int16_t window);                                                 /* $feba9c */
int16_t aes_w_mvfix(uint8_t *image, uint32_t source, uint32_t destination);                          /* $febece */
int16_t aes_w_move(uint8_t *image, int16_t window, uint32_t stop, uint32_t rect);                    /* $febf00 */
int16_t aes_w_owns(uint8_t *image, int16_t window, uint32_t orect, uint32_t rect, uint32_t out);     /* $fec39a */
int16_t aes_w_union(uint8_t *image, uint32_t orect, uint32_t rect);                                   /* $fec3ea */
void aes_wm_start(uint8_t *image);                                                                    /* $fec424 */
int16_t aes_wm_create(uint8_t *image, int16_t kind, uint32_t rect);                                  /* $fec602 */
uint16_t aes_wm_delete(uint8_t *image, int16_t window);                                               /* $fec706 */
uint16_t aes_wm_get(uint8_t *image, int16_t window, int16_t field, uint32_t out);                    /* $fec722 */
int16_t aes_wm_find(uint8_t *image, int16_t x, int16_t y);                                            /* $feca4a */
int16_t aes_wm_calc(uint8_t *image, int16_t type, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h,
                    uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out);                   /* $fecaac */

#endif /* TOS102US_AES_WMLIB_H */
