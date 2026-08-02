/* rad.h — the .RAD/.CRU container and its bitstream, as constants (src/rad.c).
 *
 * The format is the game's own cruncher, established from the routine itself: the transcription is
 * ../../notes/rad_depacker.asm, the host reimplementation tools/depack_rad.py, and the prose
 * ../../../../docs/binary-formats.md. Nothing here is a guess about the format — every value is a
 * literal in that routine.
 *
 * The depacker's two runtime addresses and its failure status live in wonderboy.h instead, because
 * test/ needs them too and that header is the one Python scrapes (test/layout.py).
 */
#ifndef WONDERBOY_RAD_H
#define WONDERBOY_RAD_H

#include <stdint.h>

/* ---- container: `packed.l, unpacked.l, checksum.l`, then the stream ------------------------- */
#define RAD_HDR_PACKED_OFF    0u   /* be32: packed length = filesize - RAD_HDR_LEN. The routine
                                    * never learns the size of the buffer the file was read into,
                                    * so this field alone locates EOF and trailing slack is inert */
#define RAD_HDR_UNPACKED_OFF  4u   /* be32: bytes the destination ends up holding */
#define RAD_HDR_CHECKSUM_OFF  8u   /* be32: XOR of every longword of the stream; seeds d5 */
#define RAD_HDR_LEN           12u  /* the stream starts here, and is consumed BACKWARDS from EOF */
#define RAD_LONG              4u   /* the stream is walked one longword at a time */

/* Each longword carries its own end-of-longword marker: the buffer is spent once the shifted-out
 * remainder is 0, and the refill rotates a fresh 1 into bit 31 (`move #$10,ccr` + `roxr.l #1,d0`),
 * so every refilled longword yields exactly 32 data bits. The seed longword gets no injected
 * marker, so its own highest set bit ends it. */
#define RAD_END_MARKER        0x80000000u

/* ---- tokens (the output is filled backwards too, from the end of the destination down) ------- */
/* First bit: 0 = a short token, one more bit picks which; 1 = a 2-bit selector follows. */
#define RAD_SEL_BITS              2u
#define RAD_SEL_LONG_MATCH        2u   /* 8-bit length field, 12-bit offset */
#define RAD_SEL_LONG_LITERALS     3u   /* 8-bit count field */
/* Selectors 0 and 1 are fixed-length matches, and the longer one gets the wider offset. The
 * original computes both (`addq.w #2,d2` / `move.w #9,d1; add.w d2,d1`) rather than tabulating. */
#define RAD_SHORT_MATCH_LEN_BASE  3u   /* selector 0/1 -> length 3 or 4 */
#define RAD_SHORT_MATCH_OFF_BASE  9u   /* ...with 9 or 10 offset bits */
/* The "01" token: the shortest match the format can express. */
#define RAD_MATCH2_LEN            2u
#define RAD_MATCH2_OFF_BITS       8u
/* The "1 10" match: an 8-bit length field, copying field+1 bytes (the `dbf`'s own +1, folded in). */
#define RAD_LONG_MATCH_LEN_BITS   8u
#define RAD_LONG_MATCH_LEN_BASE   1u
#define RAD_LONG_MATCH_OFF_BITS   12u
/* Literal runs, with the same +1 folded into each base. */
#define RAD_LIT_SHORT_BITS        3u
#define RAD_LIT_SHORT_BASE        1u   /* -> 1..8 bytes */
#define RAD_LIT_LONG_BITS         8u
#define RAD_LIT_LONG_BASE         9u   /* -> 9..264 bytes */
#define RAD_LITERAL_BITS          8u   /* a literal byte is 8 plain stream bits, not a byte read */

/* Depack the .RAD file at image offset `src` to `dst`, both Ghidra/runtime addresses. Returns d0:
 * WB_RAD_BAD_CHECKSUM if the stream's checksum did not cancel, otherwise the spent bit buffer
 * (which is not a status — the game's five call sites ignore it). */
uint32_t rad_depack(uint8_t *image, uint32_t src, uint32_t dst);

#endif /* WONDERBOY_RAD_H */
