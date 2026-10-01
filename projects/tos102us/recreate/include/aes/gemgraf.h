/* aes/gemgraf.h — the AES's graphics library (`src/aes/gemgraf.c`) and the non-interactive part of its box animations
 * (`src/aes/grlib.c`): every routine HAND 68000, entered by a Line-F call or a `bsr` over the frame its caller pushed
 * (Alcyon's words and longs), each reaching the VDI through `aes/gsx.h`'s binding. Read from their bodies:
 *
 *   $fda7f8 gsx_sclip    the clip GRECT into the four clip words; vs_clip on over its corners, off when it is empty
 *   $fda846 gsx_gclip    ...and the four words back out;  $fda864 gsx_chkclip: 1 when a GRECT touches the clip
 *   $fda8d2 gsx_cline    one line from the frame's own two points, the cursor hidden round it
 *   $fda8e6 gsx_attr     the writing mode and the text or line colour, each set only when its cache differs
 *   $fda956 gsx_bxpts    a GRECT's five corners (closed) into ptsin;  $fda97c gsx_box: drawn as one polyline
 *   $fda9ce gsx_blt      two MFDBs (gsx_fix) and the two rectangles' corners; vrt_cpyfm in two colours, else vro_cpyfm
 *   $fdaa48 bb_screen    gsx_blt from the screen to the screen;  $fdaa6a gsx_trans: vrn_trnfm of a form
 *   $fdac28 bb_fill      gsx_attr, the fill interior and style through their caches, vr_recfl over the screen
 *   $fdaca4 gsx_tcalc    a string into intin (xstrpix) and its size in a font: width, height and characters that fit
 *   $fdad0a gsx_tblt     the font changed (vst_height) when its cache differs, the baseline added, v_gtext of intin
 *   $fdada4 gsx_xbox     a dotted box;  $fdadce gsx_xcbox: its four corners;  $fdae38 gsx_xline: a dotted polyline
 *   $fda56e gr_inside    a GRECT shrunk by a thickness on every side
 *   $fda582 gr_rect      a GRECT filled in a colour and a pattern (bb_fill, replace mode)
 *   $fda5c2 gr_just      a string's size, and the GRECT's corner moved to centre it down and justify it across
 *   $fda62c gr_gtext     a string drawn justified in a GRECT (a copy of it gr_just moves)
 *   $fda66a gr_crack     an object's colour word into its border, text, pattern, interior and writing mode
 *   $fda6c4 gr_gicon     an icon: its mask and data blitted, its character, its text in its box
 *   $fda7a4 gr_box       a box `thickness` lines thick, inwards or (negative) outwards
 *   $fe85b0 gr_setup     the clip the whole screen, XOR in a colour
 *   $fe8472 gr_scale     how many steps a distance takes, and each step's size
 *   $fe82e6 gr_stepcalc  a size centred in a GRECT, and gr_scale of the half-differences
 *   $fe83be gr_xor       a box (or its corners) XORed in place, stepped, `count` + 1 times
 *   $fe8402 gr_movebox   a box XORed along the line from one place to another, and XORed back
 *   $fe8340 gr_growbox   ...from a GRECT to one centred in another, grown out to it;  $fe837a gr_shrinkbox: back
 *
 * FOLDED, no rows of their own (each reads its CALLER's frame or registers — the OB_ADDR precedent): $fda76e,
 * gr_gicon's blit of one form (D0 the form, D1/D2 the colours, A3 the icon's GRECT); $fe82d6, gr_stepcalc's half-
 * difference (D2 the coordinate, its caller's frame by SP); $fe831e, the growbox/shrinkbox prologue that reads ITS
 * caller's arguments at 44(sp) and hands gr_stepcalc five pointers into that caller's own saved registers.
 */
#ifndef TOS102US_AES_GEMGRAF_H
#define TOS102US_AES_GEMGRAF_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"
#include "aes/aes.h"
#include "aes/gsx.h"
#include "aes/objects.h"

#define GRECT_WORDS           (GRECT_BYTES / (GRECT_Y - GRECT_X))  /* x, y, w, h: a C local standing in for a GRECT */

/* ---- the VDI's attribute values the library hands it --------------------------------------------------------- */
#define GSX_MODE_REPLACE      1          /* gr_rect's bb_fill                   ($fda5b2 move.w #1)             */
#define GSX_MODE_TRANSPARENT  2          /* gr_gicon's text, gr_crack's plain pattern ($fda6b4 move.w #2)       */
#define GSX_MODE_XOR          3          /* gr_setup's                          ($fe85bc moveq #3)             */
#define GSX_FIS_HOLLOW        VDI_INTERIOR_HOLLOW  /* gr_rect's interiors: a pattern of 0 is hollow ($fda596 clr.w d5) */
#define GSX_FIS_SOLID         VDI_INTERIOR_SOLID   /* ...7 solid                          ($fda59e moveq #1)    */
#define GSX_FIS_PATTERN       VDI_INTERIOR_PATTERN /* ...any other a pattern              ($fda590 moveq #2)    */
#define GSX_PATTERN_HOLLOW    0          /* ($fda592 tst.w d4)                                                  */
#define GSX_PATTERN_SOLID     7          /* ($fda598 cmp.w #7,d4)                                               */
#define GSX_TEXT_LINE         0          /* gsx_attr's first argument: the line colour (vsl_color)              */
#define GSX_TEXT_TEXT         1          /* ...or the text colour (vst_color)   ($fda72c's `move.l #$10002`)    */
#define GSX_NO_COLOUR         (-1)       /* gsx_blt's foreground: no colours, vro_cpyfm ($fdaa30 cmpi.w #-1)   */
/* vsl_udsty's dots, shifted by a point's parity; gsx_xline's last call puts `aes/gsx.h`'s GSX_STYLE_SOLID back. */
#define GSX_STYLE_DOTTED      0x5555     /* ($fdae44 move.w)                                                    */
#define GSX_STYLE_PARITY_MASK 1          /* ($fdae54 and.w d4,d1: d4 = 1)                                       */

/* ---- the fonts: the two the AES draws text in, each with the words vst_height answers into ------------------- */
#define GSX_FONT_IBM          3          /* the large font                      ($fdacc0 cmpw #3)              */
#define GSX_FONT_SMALL        5          /* the small font                      ($fdacd4 cmpw #5)              */
/* gr_just's justifications (a TEDINFO's te_just). */
#define GSX_JUST_RIGHT        1          /* ($fda61e cmpw #1)                                                   */
#define GSX_JUST_CENTRE       2          /* ($fda60c cmpw #2)                                                   */

/* ---- gr_crack: an object's COLOUR WORD, four nibbles and the writing-mode bit -------------------------------- */
#define CRACK_BORDER_SHIFT    12         /* ($fda674 lsr.w #8, $fda678 asr.w #4)                                */
#define CRACK_TEXT_SHIFT      8          /* ($fda674 lsr.w #8)                                                  */
#define CRACK_PATTERN_SHIFT   4          /* ($fda692 asr.w #4)                                                  */
#define CRACK_NIBBLE_MASK     0x000f     /* ($fda67a and.w #15)                                                 */
#define CRACK_LOW_BYTE_MASK   0x00ff     /* ($fda68c and.w #255)                                                */
/* The pattern nibble's top bit is the writing mode — set, replace and a pattern of the low three bits; clear,
 * transparent and the whole nibble ($fda6a2 btst #3,1(a0)). */
#define CRACK_REPLACE_BIT     3
#define CRACK_PATTERN_MASK    0x0007     /* ($fda6aa andi.w #7,(a0))                                            */

/* ---- gr_gicon: an icon's state and its character word ---------------------------------------------------------- */
#define ICON_STATE_SELECTED_BIT 0        /* ...of the state's low byte: the colours swapped ($fda6e6 btst #0)   */
#define ICON_STATE_WHITEBAK_BIT 6        /* ...the mask not drawn over a white background ($fda6f6 btst #6)     */
#define ICON_COLOUR_WHITE     0          /* ($fda6fe tst.w d3)                                                  */
#define ICON_FOREGROUND_SHIFT 12         /* the character word's colours: ($fda6d0 moveq #12, asr.w d0,d4)     */
#define ICON_BACKGROUND_SHIFT 8          /* ($fda6dc asr.w #8)                                                  */
#define ICON_CHARACTER_MASK   0x00ff     /* ($fda6e2 and.w #255)                                                */
#define ICON_CHARACTERS       1          /* the one character drawn            ($fda73a move.w #1)             */
#define BITS_PER_BYTE         8          /* a form's width in bytes, `divs.w #8` ($fda782, $fda792)             */

/* ---- grlib ------------------------------------------------------------------------------------------------------ */
#define GROW_STEPS_PASSES     2          /* the box XORed in, then out again ($fe8350 moveq #1: dbf)            */
#define GROW_MINIMUM_STEP     1          /* gr_scale's floor on a step          ($fe8494 moveq #1)             */
#define GROW_COLOUR           1          /* gr_scale's gr_setup(BLACK)          ($fe8480 move.w #1)            */

#ifndef __ASSEMBLER__
/* ---- gemgraf ---------------------------------------------------------------------------------------------------- */
void aes_gr_inside(uint8_t *image, uint32_t rect, int16_t thickness);                               /* $fda56e */
uint16_t aes_gr_rect(uint8_t *image, int16_t colour, int16_t pattern, uint32_t rect);              /* $fda582 */
uint16_t aes_gr_just(uint8_t *image, int16_t just, int16_t font, uint32_t text, int16_t width, int16_t height,
                     uint32_t rect);                                                                /* $fda5c2 */
void aes_gr_gtext(uint8_t *image, int16_t just, int16_t font, uint32_t text, uint32_t rect);         /* $fda62c */
void aes_gr_crack(uint8_t *image, int16_t colour, uint32_t border, uint32_t text, uint32_t pattern, uint32_t interior,
                  uint32_t mode);                                                                   /* $fda66a */
void aes_gr_gicon(uint8_t *image, int16_t state, uint32_t mask, uint32_t data, uint32_t text, int16_t character,
                  int16_t char_x, int16_t char_y, uint32_t icon, uint32_t text_rect);                /* $fda6c4 */
void aes_gr_box(uint8_t *image, int16_t x, int16_t y, int16_t width, int16_t height, int16_t thickness);
                                                                                                    /* $fda7a4 */
uint16_t aes_gsx_sclip(uint8_t *image, uint32_t rect);                                              /* $fda7f8 */
void aes_gsx_gclip(uint8_t *image, uint32_t rect);                                                  /* $fda846 */
uint16_t aes_gsx_chkclip(uint8_t *image, uint32_t rect);                                            /* $fda864 */
void aes_gsx_cline(uint8_t *image, int16_t x1, int16_t y1, int16_t x2, int16_t y2);                 /* $fda8d2 */
void aes_gsx_attr(uint8_t *image, int16_t text, int16_t mode, int16_t colour);                      /* $fda8e6 */
void aes_gsx_bxpts(uint8_t *image, uint32_t rect);                                                  /* $fda956 */
uint16_t aes_gsx_box(uint8_t *image, uint32_t rect);                                                /* $fda97c */
void aes_gsx_blt(uint8_t *image, uint32_t source, int16_t source_x, int16_t source_y, int16_t source_bytes,
                 uint32_t destination, int16_t destination_x, int16_t destination_y, int16_t destination_bytes,
                 int16_t width, int16_t height, int16_t rule, int16_t foreground, int16_t background);
                                                                                                    /* $fda9ce */
void aes_bb_screen(uint8_t *image, int16_t rule, int16_t source_x, int16_t source_y, int16_t destination_x,
                   int16_t destination_y, int16_t width, int16_t height);                           /* $fdaa48 */
uint16_t aes_gsx_trans(uint8_t *image, uint32_t source, int16_t source_bytes, uint32_t destination,
                       int16_t destination_bytes, int16_t height);                                  /* $fdaa6a */
uint16_t aes_bb_fill(uint8_t *image, int16_t mode, int16_t interior, int16_t pattern, int16_t x, int16_t y,
                     int16_t width, int16_t height);                                                /* $fdac28 */
uint16_t aes_gsx_tcalc(uint8_t *image, int16_t font, uint32_t text, uint32_t width, uint32_t height,
                       uint32_t characters);                                                        /* $fdaca4 */
uint16_t aes_gsx_tblt(uint8_t *image, int16_t font, int16_t x, int16_t y, int16_t characters);      /* $fdad0a */
uint16_t aes_gsx_xbox(uint8_t *image, uint32_t rect);                                               /* $fdada4 */
uint16_t aes_gsx_xcbox(uint8_t *image, uint32_t rect);                                              /* $fdadce */
uint16_t aes_gsx_xline(uint8_t *image, int16_t count, uint32_t points);                             /* $fdae38 */

/* ---- grlib ------------------------------------------------------------------------------------------------------ */
void aes_gr_setup(uint8_t *image, int16_t colour);                                                  /* $fe85b0 */
uint16_t aes_gr_scale(uint8_t *image, int16_t x_distance, int16_t y_distance, uint32_t count, uint32_t x_step,
                      uint32_t y_step);                                                             /* $fe8472 */
void aes_gr_stepcalc(uint8_t *image, int16_t width, int16_t height, uint32_t rect, uint32_t centre_x,
                     uint32_t centre_y, uint32_t count, uint32_t x_step, uint32_t y_step);          /* $fe82e6 */
void aes_gr_xor(uint8_t *image, int16_t corners, int16_t count, int16_t x, int16_t y, int16_t width, int16_t height,
                int16_t x_step, int16_t y_step, int16_t grows);                                     /* $fe83be */
void aes_gr_movebox(uint8_t *image, int16_t width, int16_t height, int16_t source_x, int16_t source_y,
                    int16_t destination_x, int16_t destination_y);                                  /* $fe8402 */
void aes_gr_growbox(uint8_t *image, uint32_t from, uint32_t to);                                    /* $fe8340 */
void aes_gr_shrinkbox(uint8_t *image, uint32_t from, uint32_t to);                                  /* $fe837a */
#endif /* !__ASSEMBLER__ */

#endif /* TOS102US_AES_GEMGRAF_H */
