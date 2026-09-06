/* raster.h — the bit-level raster model the VDI opcodes draw through.
 *
 * THE CONTRACT. ONE implementation compiled into BOTH sides (kit.mk sweeps `src/raster.c` into every
 * candidate and names it in the `$(ORACLE)` rule), and DELIBERATELY STATELESS — every byte it reads
 * or writes is in the image, the workstation attributes included (`os.h`, the VDI state block). Why
 * a shared `.c` rather than a header of inlines, why statelessness is what makes two copies of these
 * symbols in one process harmless, and what the model does not capture: TRAP_MODEL.md, "Phase 11".
 *
 * THE FORMAT IS THE ST's DEVICE FORMAT: planes interleaved a word at a time, most significant bit
 * leftmost. Pixel (x, y) of plane p lives in the word at
 *
 *     addr + y * wdwidth * 2 * nplanes + (x / 16) * 2 * nplanes + p * 2
 *
 * at bit 15 - (x % 16). A one-plane raster degenerates to the same formula with no interleave, which
 * is why the helpers take `nplanes` rather than assuming four. `fd_stand = 1` (VDI STANDARD format,
 * whose planes are consecutive rather than interleaved) is a DIFFERENT layout and is refused by the
 * caller — see gem.c.
 */
#ifndef RECREATE_KIT_RASTER_H
#define RECREATE_KIT_RASTER_H

#include <stdint.h>

#include "machine.h"

#define RASTER_PIXELS_PER_WORD 16
#define RASTER_WORD_BYTES      2
/* A raster the model will serve. One plane is a mask/mono bitmap and eight is the widest an ST-shaped
 * device format reaches; outside that the interleave formula above is describing nothing real, so
 * raster_valid() refuses rather than compute an address from it. */
#define RASTER_MIN_PLANES 1
#define RASTER_MAX_PLANES 8

/* A raster the model can address. Built from an MFDB by the caller (gem.c), or synthesised for
 * "the screen" — the MFDB address 0 means, which in this model is the VDI state block's screen
 * base (see os.h). Signed extents, because ptsin coordinates are signed and the arithmetic that
 * clips against them must be too. */
typedef struct {
    uint32_t addr;      /* image address of the raster's first byte */
    int32_t  w;         /* extent in pixels */
    int32_t  h;
    int32_t  wdwidth;   /* 16-pixel words per plane per row */
    int32_t  nplanes;
} raster_t;

/* ---- the 16 VDI logic operations -------------------------------------------------------------
 * `vro_cpyfm`'s intin[0]. Each is a truth table over (source bit, destination bit): op number n,
 * written as the four bits b3 b2 b1 b0, answers b(3 - ((S << 1) | D)). The two the games here use
 * are named; the other fourteen are implemented and pinned by the kit's own reference table rather
 * than left to a call site to discover.
 */
#define RASTER_OP_ALL_WHITE   0    /* 0                 */
#define RASTER_OP_S_AND_D     1    /* S & D             */
#define RASTER_OP_S_AND_NOT_D 2    /* S & ~D            */
#define RASTER_OP_S_ONLY      3    /* S  — a plain copy */
#define RASTER_OP_NOT_S_AND_D 4    /* ~S & D            */
#define RASTER_OP_D_ONLY      5    /* D                 */
#define RASTER_OP_S_XOR_D     6    /* S ^ D             */
#define RASTER_OP_S_OR_D      7    /* S | D — the transparent-sprite mode */
#define RASTER_OP_NOR_S_D     8    /* ~(S | D)          */
#define RASTER_OP_XNOR_S_D    9    /* ~(S ^ D)          */
#define RASTER_OP_NOT_D       10   /* ~D                */
#define RASTER_OP_S_OR_NOT_D  11   /* S | ~D            */
#define RASTER_OP_NOT_S       12   /* ~S                */
#define RASTER_OP_NOT_S_OR_D  13   /* ~S | D            */
#define RASTER_OP_NAND_S_D   14    /* ~(S & D)          */
#define RASTER_OP_ALL_BLACK   15   /* 1                 */
#define RASTER_OP_COUNT       16

/* Apply logic op `op` to one source bit and one destination bit. `op` outside 0..15 answers 0; the
 * caller refuses such a call before drawing, so this is a bound and not a policy. */
int raster_logic_op(int op, int src_bit, int dst_bit);

/* Is this raster one the model can address end to end — sane extents, a plane count it knows, and
 * every byte of it inside the image? Asked ONCE per raster, before a single pixel moves, so a
 * rectangle can never be half-drawn and then refused. */
int raster_valid(const raster_t *raster);

/* The total byte length of a raster: rows x interleaved plane words. Widened to 64 bits because
 * every factor comes off the emulated program's stack, and the product of three word-sized fields
 * overflows 32 bits long before raster_valid() could notice it had. */
uint64_t raster_bytes(const raster_t *raster);

/* Is (x, y) inside the raster's extent? Signed, so a negative coordinate answers no. */
int raster_in_extent(const raster_t *raster, int32_t x, int32_t y);

/* ---- ONE PIXEL'S ADDRESS, resolved once ------------------------------------------------------
 * Where plane 0's bit for (x, y) lives, and its mask. Every plane of that pixel is the SAME mask one
 * word further on, so a caller that walks the planes of a pixel — which is every drawing operation
 * here — resolves the division, the modulo, the two multiplies and the high-byte test once and then
 * steps by RASTER_WORD_BYTES. The per-pixel semantics are unchanged: this is the same address the
 * formula at the top of this file gives, computed in one place instead of once per plane.
 *
 * The caller must have vetted the raster (`raster_valid`) and the coordinate (`raster_in_extent`). */
typedef struct {
    uint32_t byte;      /* image address of the byte holding PLANE 0's bit */
    uint8_t  mask;      /* ...and the bit within it, the same for every plane */
} raster_at_t;

raster_at_t raster_locate(const raster_t *raster, int32_t x, int32_t y);
int  raster_at_plane_bit(const uint8_t *mem, const raster_at_t *at, int plane);
void raster_at_set_plane_bit(uint8_t *mem, const raster_at_t *at, int plane, int bit);
void raster_at_set_pixel(uint8_t *mem, const raster_at_t *at, int nplanes, int colour);

/* One plane's bit at (x, y). The caller must have vetted the raster and the coordinate. */
int raster_plane_bit(const uint8_t *mem, const raster_t *raster, int32_t x, int32_t y, int plane);
void raster_set_plane_bit(uint8_t *mem, const raster_t *raster, int32_t x, int32_t y,
                          int plane, int bit);

/* The colour INDEX at (x, y): plane p contributes bit p, exactly as the ST's shifter reads it. */
int raster_pixel(const uint8_t *mem, const raster_t *raster, int32_t x, int32_t y);
void raster_set_pixel(uint8_t *mem, const raster_t *raster, int32_t x, int32_t y, int colour);

/* ---- the model's 8x8 font — NOT TOS's ---------------------------------------------------------
 * The kit has no ST system font and may not invent a copy of one, so `v_gtext` draws through a
 * SYNTHETIC glyph set defined here in one line: row r of the glyph for character c is c's low byte
 * ROTATED LEFT by r. Every character therefore has a distinct 8x8 pattern (two characters agreeing
 * on every row would have to agree on row 0, which is the character itself), the mapping is a pure
 * function of the character, and nothing about it resembles a real typeface.
 *
 * What that buys and what it does not: both sides draw the SAME pixels from the same parameter
 * block, which is the whole of what a differential can pin. Text that reads as text on a real
 * machine is an on-target matter (docs/on-target-execution.md), and this model says nothing about
 * it. See TRAP_MODEL.md, "Phase 12".
 */
#define RASTER_FONT_W 8
#define RASTER_FONT_H 8

uint8_t raster_font_row(uint8_t ch, int row);

#endif /* RECREATE_KIT_RASTER_H */
