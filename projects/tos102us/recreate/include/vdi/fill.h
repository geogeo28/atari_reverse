/* vdi/fill.h — POLYGONS and FILLS (`src/vdi/fill.c`): $a006's scanline polygon fill and the VDI's
 * Alcyon geometry over it (clip_line, polyline, plygn, v_fillarea), and $a00f's CONTOUR (seed) fill with
 * its helpers, v_contourfill and v_get_pixel.
 *
 * THE CONTOUR FILL'S STATE LIVES IN THE BIOS DISK BUFFER, as DRI's `seedfill.c` globals: every variable
 * below is a word the ROM's Alcyon C reads and writes by absolute address, so each is compared image and
 * the reconstruction keeps them there rather than in locals. Its QUEUE of pending spans starts at
 * `VDI_FILL_QUEUE` and may grow to `VDI_FILL_QUEUE_LAST` words — 3,840 bytes, through the entry's PTSIN
 * copy and the text scratch to just under LINEA_CUR_FONT — which the ROM shares with everything else that
 * borrows the buffer: the same words are `$a006`'s crossing list, vqt_extent's sum
 * (`VDI_EXTENT_SCRATCH` is queue[0]) and the dispatcher's two text-alignment copies (`VDI_TEXT_H_ALIGN`
 * and `_V_ALIGN` are LEFTCOLLISION and COLLISION).
 *
 * A QUEUE RECORD is three words: the row with `VDI_FILL_DOWN_FLAG` set when the fill goes on downwards
 * from it, and the span's two ends; a taken record's first word is `VDI_FILL_EMPTY`. Indexes count
 * WORDS from the queue, and the ROM sign-extends each into its address (`movea.w`), so an index below 0 —
 * crunch_queue asks for queue[-3] of an empty queue — reads the words under the queue.
 */
#ifndef TOS102US_VDI_FILL_H
#define TOS102US_VDI_FILL_H

#include "vdi/vdi.h"

/* $a006's crossing list is VDI_SCRATCH itself, one x a word from $16da ($fca070 lea). */

/* ---- the contour fill's globals (DRI's names) -----------------------------------------------------
 * Four are words other layers name too, and are spelt AS those names: the same RAM, borrowed in turn. */
#define VDI_FILL_SEED_TYPE    VDI_SCRATCH /* word: 1 = fill the seed's colour, 0 = up to SEARCH_COLOR ($fd0986) */
#define VDI_FILL_SEARCH_COLOR 0x16dc     /* word: the pen the fill stops at, or fills ($fd095c)      */
#define VDI_FILL_QBOTTOM      0x16de     /* word: the queue's first record, always 0 ($fd0a2a)      */
#define VDI_FILL_QTOP         0x16e0     /* word: one past its last record         ($fd0a36)        */
#define VDI_FILL_QPTR         0x16e2     /* word: the next record to take          ($fd0a30)        */
#define VDI_FILL_QTMP         0x16e4     /* word: get_seed's walk through the queue ($fd0e5c)       */
#define VDI_FILL_QHOLE        0x16e6     /* word: the first empty record it passed, -1 none ($fd0e66) */
#define VDI_FILL_OLDY         0x16e8     /* word: the row being filled, with its direction flag ($fd090e) */
#define VDI_FILL_OLDXLEFT     0x16ea     /* word                                   ($fd0ae4)        */
#define VDI_FILL_OLDXRIGHT    0x16ec     /* word                                   ($fd0afe)        */
#define VDI_FILL_NEWXLEFT     0x16ee     /* word: the next row's span               ($fd0b68 pea)   */
#define VDI_FILL_NEWXRIGHT    0x16f0     /* word                                   ($fd0b62 pea)    */
#define VDI_FILL_XLEFT        0x16f2     /* word: the seed x, then a turned-back span ($fd0902)     */
#define VDI_FILL_XRIGHT       0x16f4     /* word                                   ($fd0bd0 pea)    */
#define VDI_FILL_DIRECTION    0x16f6     /* word: +1 down, -1 up                   ($fd0b56)        */
#define VDI_FILL_DONE         0x16f8     /* word: nonzero stops the fill: SEEDABORT's answer, or a full queue ($fd0e18) */
#define VDI_FILL_GOTSEED      0x16fa     /* word                                   ($fd0a22)        */
#define VDI_FILL_LEFTOLDY     0x16fc     /* word: the left turn-back's own row     ($fd0bb0)        */
#define VDI_FILL_LEFTDIRECTION 0x16fe    /* word                                   ($fd0b92)        */
#define VDI_FILL_LEFTSEED     0x1700     /* word                                   ($fd0b9c)        */
#define VDI_FILL_LEFTCOLLISION VDI_TEXT_H_ALIGN /* word                            ($fd0ba6)        */
#define VDI_FILL_COLLISION    VDI_TEXT_V_ALIGN /* word: get_seed met a queued record and drew it ($fd0b5c pea) */
#define VDI_FILL_QUEUE        VDI_EXTENT_SCRATCH /* words[VDI_FILL_QUEUE_LAST]      ($fd0a9e adda.l) */
#define VDI_FILL_QUEUE_LAST   1920       /* words: QTOP past it is a full queue    ($fd0f68 cmp.w)  */
#define VDI_FILL_RECORD_WORDS 3          /* row, left, right                       ($fd0a78 addq #3) */
#define VDI_FILL_DOWN_FLAG    0x8000     /* a record's row: the fill continues downwards ($fd0a44 or.w) */
#define VDI_FILL_ROW_MASK     0x7fff     /* ...and the row alone                   ($fd0b2c and.w)  */
#define VDI_FILL_EMPTY        0xffff     /* a taken record's row                   ($fd0acc)        */

/* The pen mask per plane count, words 1, 3, 7, 15 indexed by INQ_TAB[4] - 1 — so a plane count of 0
 * reads the word before it, VDI_PATTERN_SOLID's $ffff ($fd09a2..$fd09b2). */
#define VDI_FILL_PEN_MASKS    0xfd3590

#ifndef __ASSEMBLER__
#include <stdint.h>

/* ---- the polygon ------------------------------------------------------------------------------------ */
void linea_filled_poly(uint8_t *image);                                    /* $fca05e $a006 */
int16_t vdi_clip_line(uint8_t *image);                                     /* $fcbf16 */
void vdi_polyline(uint8_t *image);                                         /* $fcbe8c */
void vdi_plygn(uint8_t *image);                                            /* $fcc0ea */
void vdi_v_fillarea(uint8_t *image);                                       /* $fcbbc0, opcode 9 */

/* ---- the contour fill: the helpers take and answer what their Alcyon frames do — WORD coordinates,
 * the ADDRESSES of the words they answer into, a word in D0 ------------------------------------------ */
void linea_fill_span(uint8_t *image, int16_t x1, int16_t x2, int16_t y);  /* $fcfb54 */
int16_t linea_end_pts(uint8_t *image, int16_t x, int16_t y, uint32_t xleft_at, uint32_t xright_at); /* $fcfb66 */
void linea_crunch_queue(uint8_t *image);                                   /* $fd0dc8 */
int16_t linea_get_seed(uint8_t *image, int16_t x, int16_t y, uint32_t xleft_at, uint32_t xright_at,
                       uint32_t collide_at);                               /* $fd0e22 */
void linea_contour_fill(uint8_t *image);                                   /* $fd08f4 $a00f */
void vdi_v_contourfill(uint8_t *image);                                    /* $fd08e0, opcode 103 */
void vdi_v_get_pixel(uint8_t *image);                                      /* $fd0fde, opcode 105 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_FILL_H */
