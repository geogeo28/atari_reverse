/* vdi/raster.h — the Line-A PIXEL / SCANLINE primitives and their CPU bodies (`src/vdi/raster.c`).
 *
 * THE SCREEN'S SHAPE, which every routine here computes the same way: the screen is `v_bas_ad`
 * onwards, BYTES_LIN bytes a line, and a line is a run of 16-pixel GROUPS of PLANES consecutive words,
 * plane 0 first; pixel x is bit 15 - (x & 15) of its group's words. `$fca1b8` (concat) is the ROM's
 * own spelling of the address arithmetic, and `concat_offset` is it for the other layers' C.
 *
 * THE REGISTER CONTRACTS are the batteries' (`test/test_vdi_raster_*.py`, `test/test_vdi_line.py`,
 * through `test/vdi.py`'s `declare_primitive`): a core's arguments are the registers named there, in
 * that order. Two hidden inputs no core takes: A4 (A2 for the rectangle body) is the Line-A base,
 * which every caller has loaded ($fca57e, $fca1ea, $fcfb5c, $fcfc56), and the vertical line's D0 is 2,
 * the XOR write mode its one caller loads ($fca1f0) — any other D0 runs code the ROM never built.
 */
#ifndef TOS102US_VDI_RASTER_H
#define TOS102US_VDI_RASTER_H

#include "vdi/linea.h"

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- the ROM tables these routines read -------------------------------------------------------
 * The C reads each BY ITS ROM ADDRESS, the project's convention for a ROM table (`addrs.h`'s
 * KEYTBL_*_ROM are the precedent): the host runs over the captured ROM, so the address IS the table.
 * `raster.S` instead carries its own copy of every table it reads, in the ROM's layout, and references
 * the copy. The transcribed C cores are never linked by a ROM build (`vdi/transcribed.h`), but the C
 * that is not transcribed still reads a ROM address — `concat_offset`, which other layers call, reads
 * RASTER_CONCAT_SHIFT_TABLE — so a ROM build that lays its image out differently must hand that C a
 * table the build itself carries. */
/* concat's shift of (x & ~15) by the plane count: 3, 2, 0, 1 for 1..4 planes, 0 for 5..8 — a byte
 * table whose index 0 is the low byte of concat's own `rts` ($fca1c8 `move.b (pc,d3.w)` at $fca1e1). */
#define RASTER_CONCAT_SHIFT_TABLE 0xfca1e1
/* The FRINGE masks, $ffff >> n for n = 0..16: a span's left word keeps [x1 & 15] and its right word
 * ~[(x2 & 15) + 1] ($fca5b0, $fca5b8; the rectangle's $fcfcb0 and TextBlt's $fd2284 read it too). */
#define RASTER_FRINGE_MASK_TABLE 0xfca55c
#define RASTER_FRINGE_MASK_ENTRY_BYTES 2
/* ...and the table before it, $fca54c: the blitter's (HOP, OP) byte pairs by write mode and colour bit,
 * read ONLY by the deferred blitter bodies ($fca288, $fca610, $fcfd14) — no CPU routine touches it. */
#define RASTER_BLITTER_OP_TABLE  0xfca54c
/* The three opcode words `$fca3f4` builds its per-plane code from ($fca3f6 `movem.w (pc),d0-d2`):
 * `and.w d0,(a5)+` (clear the pixel), `or.w d1,(a5)+` (set it), and the `jmp (a3)` that ends the run. */
#define RASTER_PLANE_OPCODES     0xfca41a
#define RASTER_PLANE_OPCODE_CLEAR 0
#define RASTER_PLANE_OPCODE_SET   2
#define RASTER_PLANE_OPCODE_END   4
/* The most planes the line bodies draw: more and they return untouched ($fca328, $fd19e4 `cmp.w #8`),
 * which is the room their 20-byte stack buffer has for a plane word each and the `jmp`. */
#define RASTER_LINE_PLANES_MAX   8

/* The write modes ($fd1b0e's four arms, `vswr_mode`'s 1..4 less one). */
#define RASTER_MODE_REPLACE      0
#define RASTER_MODE_TRANSPARENT  1
#define RASTER_MODE_XOR          2
#define RASTER_MODE_REVERSE      3
/* A multi-plane pattern (MULTIFILL) keeps each plane's 16 rows one after the other ($fca59e, $fd1b7c). */
#define RASTER_MULTIFILL_PLANE_BYTES 32

#ifndef __ASSEMBLER__
/* The byte offset of (x, y)'s group from the screen base — `$fca1b8`'s D1 — for the C of every layer. */
int32_t concat_offset(const uint8_t *image, uint16_t x, uint16_t y);
#endif
#endif /* TOS102US_VDI_RASTER_H */
