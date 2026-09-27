/* vdi/blit.h — the BIT-BLOCK TRANSFER (`src/vdi/blit.c`): the $a007 / $a00e front ends, the CPU engine
 * behind drawing vector 4, and the VDI's three raster functions over them.
 *
 * THE BITBLT BLOCK (`vdi/linea.h`) is the whole interface between the front ends and the engine: the
 * engine reads it as the NEGATIVE half of A6's frame, `frame - BITBLT_BYTES + field`. $a00e builds it on
 * its own stack (`link a6,#-76`) out of two MFDBs and ptsin; $a007 is handed a caller's block in A6 and
 * adds 76 — so a $a007 call leaves the engine's working words STORED in the caller's block.
 *
 * THE REGISTER CONTRACTS are the batteries' (`test/vdi_blit.py`'s `declare_primitive`s): $a007 takes the
 * block in A6; the engine D0/D2/D4/D6 = source x min, destination x min, source x max, destination x max
 * (the front ends load them from the block they have just written) and A6 = the frame.
 */
#ifndef TOS102US_VDI_BLIT_H
#define TOS102US_VDI_BLIT_H

#include "vdi/linea.h"

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- the SIXTEEN LOGIC OPS: an OP_TAB byte, the destination's new value from source S and old D ---- */
#define BLIT_OP_ZERO          0
#define BLIT_OP_S_AND_D       1
#define BLIT_OP_S_AND_NOT_D   2
#define BLIT_OP_S             3
#define BLIT_OP_NOT_S_AND_D   4
#define BLIT_OP_D             5          /* the destination left as it is: the engine skips the plane */
#define BLIT_OP_S_XOR_D       6
#define BLIT_OP_S_OR_D        7
#define BLIT_OP_NOR           8          /* ~(S | D) */
#define BLIT_OP_XNOR          9          /* ~(S ^ D) */
#define BLIT_OP_NOT_D         10
#define BLIT_OP_S_OR_NOT_D    11
#define BLIT_OP_NOT_S         12
#define BLIT_OP_NOT_S_OR_D    13
#define BLIT_OP_NAND          14         /* ~(S & D) */
#define BLIT_OP_ONE           15
#define BLIT_OP_COUNT         16         /* the op table's longwords ($fd1278); a byte past it jumps wild */
/* The ops that never read the source — 0, 5, 10 and 15 — as the bit set `$fd122a` tests the op against
 * (`move.w #$8421,d1 / btst d0,d1`). They take their own row loop, with no aligner. */
#define BLIT_NO_SOURCE_OPS_SET 0x8421

/* ---- the engine's own table ------------------------------------------------------------------------
 * The EDGE MASKS: the leftmost n pixels of a word, n = 0..16 ($fd1304). A row's right mask is entry
 * (x_max & 15) + 1, its left mask the complement of entry (x_min & 15) ($fd12e2). The C reads it by its
 * ROM address (`vdi/raster.h` says why); `blit.S` carries it where the ROM does. */
#define BLIT_EDGE_MASK_TABLE  0xfd1304
#define BLIT_EDGE_MASK_ENTRY_BYTES 2

/* The FAST COPY ($fd1352): a plain source copy (op 3 for colour bit pair 0, both colours 0), no
 * pattern, source and destination on the same bit, and source plus destination spans of at least this
 * many words — `cmp.w #4 / bcs`, so the sum of the two (x_max >> 4) - (x_min >> 4) differences. */
#define BLIT_FAST_SPAN_WORDS  4

/* ---- what $a00e builds, and from what ---------------------------------------------------------------- */
/* intin[0]'s bit 4 ($fd035a `bclr #4`): AND the source with the fill pattern at PATPTR, one word a row,
 * 16 rows ($fd037c), each plane's own 16 when MULTIFILL. The rest of intin[0] is the op, or the mode. */
#define BLIT_PATTERN_MODE_BIT 4
#define BLIT_PATTERN_ROW_BYTES 2         /* P_NXLN                              ($fd0376)           */
#define BLIT_PATTERN_INDEX_MASK 30       /* P_MASK: 16 rows of a word           ($fd037c)           */
/* The destination plane counts the engine serves: bits 1, 2 and 4 of `moveq #22` ($fd03e0 btst d1,d3),
 * the count taken modulo 32 as a register `btst` does. */
#define BLIT_PLANE_COUNTS_SET 0x16
#define BLIT_BTST_REGISTER_MASK 31
/* vrt_cpyfm's writing modes, intin[0] with bit 4 clear ($fd044e..): the op for each (foreground bit,
 * background bit) pair of a plane — the table's index is fg * 2 + bg ($fd1206). */
#define BLIT_MODE_REPLACE     1          /* 0 -> 0, bg -> ~S, fg -> S, both -> 1 ($fd0494)         */
#define BLIT_MODE_TRANSPARENT 2          /* the source in fg, the rest kept      ($fd047e)          */
#define BLIT_MODE_XOR         3          /* S ^ D whatever the colours           ($fd04b6)          */
#define BLIT_MODE_REVERSE     4          /* the clear pixels in bg, the rest kept ($fd0468)         */

#ifndef __ASSEMBLER__
void linea_copy_raster(uint8_t *image);                                 /* $fd0346, $a00e */
void linea_bitblt(uint8_t *image, uint32_t block);                      /* $fd05fc, $a007 */
void linea_cpu_blit(uint8_t *image, uint32_t source_x_min, uint32_t destination_x_min, uint32_t source_x_max,
                    uint32_t destination_x_max, uint32_t frame);        /* $fd1038, vector 4's CPU body */
void vdi_vro_cpyfm(uint8_t *image);                                     /* $fcb5aa, opcode 109 */
void vdi_vrt_cpyfm(uint8_t *image);                                     /* $fcb5dc, opcode 121 */
void vdi_vr_recfl(uint8_t *image);                                      /* $fcb614, opcode 114 */
#endif
#endif /* TOS102US_VDI_BLIT_H */
