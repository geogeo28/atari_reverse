/* vdi/palette.h — the numbers vs_color and vq_color are made of, for the C (`src/vdi/palette.c`) and
 * the transcription (`src/vdi/palette.S`) alike: plain integer `#define`s, which both read.
 *
 * A REQUESTED colour is per mille per gun; a REALIZED one is the shifter's three bits a gun, 0RGB in
 * the low three bits of each nibble of a palette register.
 */
#ifndef TOS102US_VDI_PALETTE_H
#define TOS102US_VDI_PALETTE_H

#include "vdi/vdi.h"

#define PALETTE_GUNS               VDI_REQ_COL_COMPONENTS   /* red, green, blue            */
#define PALETTE_REQ_COL_ROW_BYTES  (PALETTE_GUNS * 2)       /* ($fd2dec mulu.w #6)         */
#define PALETTE_PER_MILLE_MAX      1000   /* the clamp, and white     ($fd2e0a)           */
#define PALETTE_WHITE_SUM          (PALETTE_GUNS * PALETTE_PER_MILLE_MAX)   /* ($fd2e5e #3000) */
/* per mille -> level: `(v + 72) / 143`, so 70 is level 0 and 71 level 1, 1000 level 7 */
#define PALETTE_LEVEL_ROUNDING     72     /*                          ($fd2e14)           */
#define PALETTE_PER_MILLE_PER_LEVEL 143   /*                          ($fd2e18)           */
/* the monochrome gun: black below 142, white from 858, anything between kept as given */
#define PALETTE_MONO_BLACK_BELOW   142    /*                          ($fd2e6e)           */
#define PALETTE_MONO_WHITE_FROM    858    /*                          ($fd2e74)           */
#define PALETTE_MONO_PLANES        1      /* the plane count of the monochrome arm ($fd2df8 subq/beq) */
#define PALETTE_MONO_INVERT_BIT    0      /* register 0's bit the index is compared on ($fd2f10 btst) */
#define PALETTE_GUN_BITS           4      /* one nibble a gun         ($fd2e1c asl.w #4)  */
#define PALETTE_GUN_LEVEL_MASK     7      /* three bits of it                              */
/* vq_color's rotates: `rol.w #5` puts red's three bits at the top, then each `rol.w #4` brings the
 * next gun's to bits 1..3 — a WORD INDEX into VDI_VQ_COLOR_LEVELS, masked by `and.w #14`. */
#define PALETTE_FIRST_GUN_ROTATE   5      /*                          ($fd2ef0)           */
#define PALETTE_LEVEL_INDEX_MASK   14     /*                          ($fd2ef8)           */
#define PALETTE_VQ_COLOR_INTOUT_WORDS 4   /* the index and three guns ($fd2e8c)           */
#define PALETTE_INVALID            (-1)   /* intout[0] for an index over the bound ($fd2eb0) */

#endif /* TOS102US_VDI_PALETTE_H */
