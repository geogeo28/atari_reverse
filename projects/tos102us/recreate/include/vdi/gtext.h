/* vdi/gtext.h — GRAPHIC TEXT (`src/vdi/gtext.c`): v_gtext (opcode 8), which places a string by the current
 * font, alignment and rotation and draws it a glyph at a time through $a008 (or all at once through the fast
 * path), and d_justified, GDP 10's worker, which spreads a string to a length and draws it through v_gtext.
 *
 * THE JUSTIFIED GAPS. d_justified leaves two GAP records in the VDI scratch for v_gtext to walk, one for the
 * gaps AFTER A SPACE and one for the gaps AFTER EVERY CHARACTER: the step every gap of that kind takes, and
 * a count of the first gaps that take one pixel more — each of them spending one of that count. v_gtext
 * knows it is drawing justified text when contrl[0] is the GDP's opcode, and only then reads them.
 *
 * Both are Alcyon C. v_gtext is a VDI function (`vdi/vdi.h`); d_justified an Alcyon call with no
 * arguments, `jsr`ed by the GDP's arm 10 ($fcbd56).
 */
#ifndef TOS102US_VDI_GTEXT_H
#define TOS102US_VDI_GTEXT_H

/* ---- a GAP record, by field --------------------------------------------------------------------- */
#define VDI_GAP_STEP_X        0          /* word: every gap's step along the text ($fceb1c)         */
#define VDI_GAP_STEP_Y        2          /* word                                ($fceb22)           */
#define VDI_GAP_EXTRA         4          /* word: gaps still to take one pixel more ($fcea9a)       */
#define VDI_GAP_EXTRA_X       6          /* word: ...that pixel                 ($fceb28)           */
#define VDI_GAP_EXTRA_Y       8          /* word                                ($fceb2e)           */
/* ...and the two records, in the VDI's scratch past the extent words (`vdi/vdi.h`). */
#define VDI_GAP_AFTER_SPACE   0x170a     /* the gap after a space               ($fceb1c)           */
#define VDI_GAP_AFTER_CHARACTER 0x1714   /* ...and after every character        ($fcec2e)           */

/* ---- v_gtext ------------------------------------------------------------------------------------ */
/* The word a missing character is drawn as ($fcdbe6 `move.w #63`): '?'. */
#define VDI_TEXT_MISSING_CHARACTER 63
/* The character whose gap is a word gap ($fcdc90 `cmpi.w #32`). */
#define VDI_TEXT_SPACE        32

#ifndef __ASSEMBLER__
#include <stdint.h>

void vdi_v_gtext(uint8_t *image);             /* $fcd756, opcode 8 */
void vdi_d_justified(uint8_t *image);         /* $fce9e8, GDP 10's worker */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_GTEXT_H */
