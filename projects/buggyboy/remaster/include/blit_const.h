/* blit_const.h — fine-x blit engine constants shared by the C reference cores (src/blit.c) and the
 * hand-written m68k objshift2 core (src/asm/objshift2.S). ONE source of truth (CLAUDE.md §5): these
 * literals were duplicated as blit.c #defines and objshift2.S .equ directives.
 *
 * #define-ONLY so it is safe to #include from a .S file: the m68k builds run cpp over objshift2.S,
 * then the assembler sees the expanded text — anything but preprocessor directives (a typedef, an
 * `#include <stdint.h>`) would break assembly. SCREEN_ROW_BYTES is NOT here: it lives in screen.h,
 * which objshift2.S includes directly (screen.h guards its C-only parts behind __ASSEMBLER__).
 */
#ifndef RM_BLIT_CONST_H
#define RM_BLIT_CONST_H

#define OBJSH_CELL_BYTES      8      /* one 16-pixel 4-plane cell / column step */

/* Shared fine-x geometry — consumed by blit.c (the C engines) and the colour-indexed hand-asm core
 * objshift.S; OBJSH_RIGHT_BOUND is objshift-only. Hoisted out of blit.c so that asm and C read ONE
 * definition (F11). objshift2.S also #includes this header, but only for OBJSH_CELL_BYTES / OBJSH2_*
 * — it bakes its own immediates from phase 1's frozen-verified state and uses NONE of these four. */
#define OBJSH_NIBBLE          0xf    /* fine-x / colour-index low nibble */
#define OBJSH_SUBPX_BITS      16     /* left-shift count = 16 - fine_x */
#define COL_ALIGN             0xfff8 /* aligned_col = ((int16)x >> 1) & this (8-byte column) */
#define OBJSH_RIGHT_BOUND     0x98   /* absolute right screen bound (aligned_col); objshift base ceiling */

#define OBJSH2_RIGHT_BOUND    0x88   /* fixed right ladder base bound (aligned_col) */
#define OBJSH2_LADDER_STEP    8      /* clip-ladder column step */
#define OBJSH2_BASE_STRADDLE  3      /* base straddle for width_idx 0 */
#define OBJSH2_SRC_ROW_BYTES  0x50   /* the sprite source row stride: source cursor's net per-row step */

#endif /* RM_BLIT_CONST_H */
