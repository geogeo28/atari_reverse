/* aes/objdraw.h — the OBJECT DRAW PATH's drawer (`src/aes/objdraw.c`): just_draw, which draws ONE object of a tree at
 * a screen position — the routine ob_draw hands everyobj as a VALUE ($fea08c `move.l #$fe9a88`) and ob_change calls
 * by Line-F ($fea4ac) — and the AES globals it draws through.
 *
 * ALCYON C: entered over its caller's frame — the tree a LONGWORD, the object, x and y WORDS — and answering
 * nothing a caller reads. Every drawing call reaches the VDI through `aes/gsx.h`'s bridge.
 *
 * ITS GLOBALS ARE COPIES. A text object's TEDINFO is copied whole into AES_EDBLK, an image's BITBLK into AES_BI, an
 * icon's ICONBLK into AES_IB, and the copy is what the drawing reads (the ICONBLK's two GRECTs moved to the screen in
 * place); an editable text's raw string and template are copied into AES_RAWSTR / AES_TMPLT and merged into
 * AES_FMTSTR, which then stands in for the text (a BOXCHAR's character too, as a one-byte string). The block fields
 * read are `aes/objects.h`'s TE_*, BI_*, IB_*, at these copies' addresses. The string the label path measures goes
 * through `aes/gsx.h`'s AES_AD_INTIN.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h`.
 */
#ifndef TOS102US_AES_OBJDRAW_H
#define TOS102US_AES_OBJDRAW_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "addrs.h"
#include "aes/objects.h"

/* GEM's MAX_LEN: each of the three string buffers runs to the next global, 81 bytes on (`$b756`, `$b7a7`, a buffer
 * of the editor's at `$b7f8`, `$b849`, then rs_str's `$b89a`). A number, for the width tags below. */
#define AES_TEXT_BUFFER_BYTES 81

#define AES_EDBLK             0x9c20     /* bytes[TE_BYTES]: a text object's TEDINFO ($fe9b5a move.l #$9c20, lbcopy) */
#define AES_RAWSTR            0xb756     /* bytes[AES_TEXT_BUFFER_BYTES]: an FTEXT's raw text ($fe9c5c move.l #$b756) */
/* ODD: byte access only — lstcpy and ob_format reach it a byte at a time, and so must the C. */
#define AES_TMPLT             0xb7a7     /* bytes[AES_TEXT_BUFFER_BYTES]: ...its template ($fe9c6a move.l #$b7a7)   */
#define AES_FMTSTR            0xb849     /* bytes[AES_TEXT_BUFFER_BYTES]: the two merged, or a BOXCHAR's character
                                            ($fe9c72 move.l #$b849, $fe9ca4 move.b, $fe9cac clr.b $b84a)          */
#define AES_BI                0xc732     /* bytes[BI_BYTES]: an image's BITBLK  ($fe9d02 move.l #$c732, lbcopy)    */
#define AES_IB                0xc740     /* bytes[IB_BYTES]: an icon's ICONBLK  ($fe9d5e move.l #$c740, lbcopy)    */

#ifndef __ASSEMBLER__
void aes_just_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t x, int16_t y);            /* $fe9a88 */
/* ...and its two callers (`src/aes/obdraw.c`): a subtree drawn, and one object's state changed and redrawn. */
void aes_ob_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t depth);                     /* $fea028 */
void aes_ob_change(uint8_t *image, uint32_t tree, int16_t object, int16_t new_state, int16_t redraw); /* $fea38e */
#ifndef RECREATE_HOST_DIFFERENTIAL
/* TARGET ONLY (`src/aes/obdraw.S`): just_draw entered as everyobj enters the ROM's — over its ten-byte Alcyon frame —
 * the routine the target ob_draw hands everyobj BY VALUE where the ROM hands $fe9a88. Never called from C. */
void aes_just_draw_alcyon(void);
#endif

#include "machine.h"

/* A word of a host-slot frame (just_draw's and ob_change's locals), and one stored back. */
static inline int16_t local_word(const uint8_t *image, uint32_t frame, uint32_t local)
{
    return (int16_t)be16(image + frame + local);
}

static inline void set_local_word(uint8_t *image, uint32_t frame, uint32_t local, int16_t value)
{
    wr16(image + frame + local, (uint16_t)value);
}
#endif

#endif /* TOS102US_AES_OBJDRAW_H */
