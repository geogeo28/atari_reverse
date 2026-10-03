/* aes/wrect.h — a WINDOW's rectangles (`src/aes/wrect.c`): where each of its GRECTs lives, one read out, and its
 * visible-rectangle list rebuilt over the windows below it (newrect).
 *
 * All ALCYON C, entered by a Line-F call over the frame their caller pushed (or, newrect, by everyobj's `jsr (a0)`,
 * on the address the window-change redraw pushes, $fec146). w_getxptr answers a LONGWORD pointer in D0 and reads no
 * memory (its core takes no image); the other two answer nothing a caller reads. The records are `aes/aes.h`'s
 * WINDOW and its window tree.
 */
#ifndef TOS102US_AES_WRECT_H
#define TOS102US_AES_WRECT_H

#include <stdint.h>

#include "m68k_idioms.h"
#include "aes/aes.h"

/* WHICH of a window's rectangles, w_getxptr's switch index (table $fefcca, five rows). The values are the callers':
 * wind_get's four WF_*XYWH arms hand 0..3 ($fec742..$fec754), newrect hands 4. */
#define WS_FULL               0          /* the record's full GRECT           (wind_get WF_FULLXYWH: $fec754 clr.w d6) */
#define WS_CURR               1          /* the window tree's object: where it is (WF_CURRXYWH: $fec748 moveq #1,d6)    */
#define WS_PREV               2          /* the record's previous GRECT       (WF_PREVXYWH: $fec74e moveq #2,d6)       */
#define WS_WORK               3          /* the record's work area            (WF_WORKXYWH: $fec742 moveq #3,d6)       */
#define WS_TRUE               4          /* the tree's object again, grown by its border ($fe5d44 move.w #4)            */
/* A window's BORDER, both sides: a rectangle's w and h each grown by it to take the border in — WS_TRUE's when both
 * are non-zero ($feb572 addq.w #2), the window library's redraw rectangles ($feb6f6, $feb742, $febf28) and its
 * scroll bars over the work area ($febce2). */
#define W_BORDER              2
/* newrect's walk over the window tree: everyobj's depth bound ($fe5d62 move.w #8,(sp)). */
#define NEWRECT_WALK_DEPTH    8

/* Window `window`'s record: its handle a signed word index (`muls.w #56`, then the table's address added). */
static inline uint32_t window_record(int16_t window)
{
    return table_entry(AES_WINDOWS, window, WIN_BYTES);
}

uint32_t aes_w_getxptr(int16_t which, int16_t window);                                               /* $feb4be */
void aes_w_getsize(uint8_t *image, int16_t which, int16_t window, uint32_t rect);                    /* $feb53e */
void aes_newrect(uint8_t *image, uint32_t tree, int16_t window);                                      /* $fe5cee */
#ifndef RECREATE_HOST_DIFFERENTIAL
/* TARGET ONLY (`src/aes/wmupdate.S`): newrect and mkrect entered as everyobj enters the ROM's — over the ten-byte
 * Alcyon frame of a walker's routine — the routines the target draw_change and newrect hand everyobj BY VALUE where
 * the ROM hands $fe5cee and $fe5c9a. Never called from C. */
void aes_newrect_alcyon(void);
void aes_mkrect_alcyon(void);
#endif

#endif /* TOS102US_AES_WRECT_H */
