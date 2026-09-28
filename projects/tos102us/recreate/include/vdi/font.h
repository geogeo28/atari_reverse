/* vdi/font.h — the GEM FONT HEADER, the three ROM fonts, and where the VDI keeps its copies.
 *
 * The header is GEM's published one. `$fce116` (make_header, which builds a scaled copy into
 * WS_SCRATCH_HEAD) reads or copies every field of it from +0 to +82 in order, so that one routine
 * is the citation for most of them; the rest are cited where they are used.
 *
 * WHAT TOS COPIES IS 90 BYTES, not the 88 the published layout ends at: `v_opnwk` moves 45 words
 * ($fcb700 `moveq #44` + dbf) per font, and WS_SCRATCH_HEAD is 90 bytes long. In all three ROM fonts
 * the 45th word is 0 and the offset table starts right after it (the 6x6 font's FONT_OFF_TABLE is its
 * header + 90); nothing in the ROM reads it.
 *
 * `vdi/linea.h`'s WIDTH TAG applies: a field's comment opens with its width, and nothing else does.
 */
#ifndef TOS102US_VDI_FONT_H
#define TOS102US_VDI_FONT_H

#include "addrs.h"

/* ---- the header -------------------------------------------------------------------------------- */
#define FONT_ID               0          /* word                                ($fce12c)           */
#define FONT_POINT            2          /* word: size in points                ($fce12e)           */
#define FONT_NAME             4          /* bytes[FONT_NAME_BYTES]: its text    ($fce13a + $fce0ee) */
#define FONT_NAME_BYTES       32         /*                                     ($fce106 cmp.w #32) */
#define FONT_FIRST_ADE        36         /* word: first character               ($fce144)           */
#define FONT_LAST_ADE         38         /* word: last character                ($fce14a)           */
#define FONT_TOP              40         /* word                                ($fce15c)           */
#define FONT_ASCENT           42         /* word                                ($fce16a)           */
#define FONT_HALF             44         /* word                                ($fce178)           */
#define FONT_DESCENT          46         /* word                                ($fce1b0)           */
#define FONT_BOTTOM           48         /* word                                ($fce1be)           */
#define FONT_MAX_CHAR_WIDTH   50         /* word                                ($fce1cc)           */
#define FONT_MAX_CELL_WIDTH   52         /* word                                ($fce1da)           */
#define FONT_LEFT_OFFSET      54         /* word: italic                        ($fce1e8)           */
#define FONT_RIGHT_OFFSET     56         /* word: italic                        ($fce1f6)           */
#define FONT_THICKEN          58         /* word: bold                          ($fce204)           */
#define FONT_UL_SIZE          60         /* word: underline                     ($fce212)           */
#define FONT_LIGHTEN          62         /* word: lighten mask                  ($fce220)           */
#define FONT_SKEW             64         /* word: italic skew mask              ($fce226)           */
#define FONT_FLAGS            66         /* word                                ($fce22c)           */
#define FONT_HOR_TABLE        68         /* long                                ($fce232)           */
#define FONT_OFF_TABLE        72         /* long: character offsets             ($fce238)           */
#define FONT_DAT_TABLE        76         /* long: the font form                 ($fce23e)           */
#define FONT_FORM_WIDTH       80         /* word: form width in bytes           ($fce244)           */
#define FONT_FORM_HEIGHT      82         /* word: form height in lines          ($fce24a)           */
#define FONT_NEXT             84         /* long: next font in the ring, 0 ends ($fcdf8e)           */
#define FONT_HEADER_BYTES     90         /* what TOS copies — see above         ($fcb700)           */

/* ---- FONT_FLAGS' bits ------------------------------------------------------------------------ */
#define FONT_FLAG_DEFAULT_MASK 0x0001    /* the system font                     ($fcb7b6 eori.w #1) */
#define FONT_FLAG_HOR_TABLE_MASK 0x0002  /* FONT_HOR_TABLE is in use            ($fce87a btst #1)   */
#define FONT_FLAG_SWAPPED_MASK 0x0004    /* the form is in 68000 byte order     ($fced76 eori.w #4) */
#define FONT_FLAG_MONOSPACE_MASK 0x0008   /* -> LINEA_MONO_STATUS                ($fcaae2 and.w #8)  */

/* ---- the three ROM fonts, and the two the VDI copies into RAM ---------------------------------
 * `v_opnwk` copies the 8x8 and 8x16 headers into RAM ($fcb6f4, $fcb708) so it can PATCH them for the
 * resolution: in high resolution it stores 9 and 10 into their FONT_POINT ($fcb7a6, $fcb7ae) and
 * flips FONT_FLAG_DEFAULT_MASK in their FONT_FLAGS ($fcb7b6 eori, $fcb7be ori) — each site is the RAM
 * header's base plus the field, which `test_vdi_staging.py` reads out of those instructions rather than
 * spelling a second address for. The ring that holds them is `LINEA_FONT_RING`, and $a000's table of
 * the three ROM headers is `LINEA_FONT_TABLE` (`vdi/linea.h`). */
#define FONT_ROM_6X6          0xfd39f6   /*                                     ($fcdec0)           */
#define FONT_ROM_8X8          0xfd40d2   /*                                     ($fcb6f4)           */
#define FONT_ROM_8X16         0xfd5b2e   /*                                     ($fcb708)           */
#define FONT_RAM_8X8          0x68fe     /*                                     ($fcb6fa)           */
#define FONT_RAM_8X16         0x87d4     /*                                     ($fcb70e)           */
/* The FACE all three are: text_init measures SIZ_TAB's character sizes over the ring's fonts of this id
 * alone, and counts them into DEV_TAB as the character heights ($fcdf0e `cmpi.w #1`). */
#define FONT_SYSTEM_FACE      1

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "vdi/vdi.h"

/* ---- a font header, through the 24-bit bus ------------------------------------------------------
 * The target build is the ROM's own `move.w 40(a5),d0`, top byte and all (`bus_dereference`). */

/* A font's header in the image. Its fields are then reached off it, which is where the ROM reaches them
 * (`d16(a5)`) — and exact but for a header in the last 90 bytes of the address space, the I/O page, which
 * no case can stage a font in. */
static inline const uint8_t *font_header(const uint8_t *image, uint32_t font)
{
    return image + bus_dereference(font);
}

static inline uint16_t font_word(const uint8_t *image, uint32_t font, uint32_t field)
{
    return be16(font_header(image, font) + field);
}

static inline uint32_t font_long(const uint8_t *image, uint32_t font, uint32_t field)
{
    return be32(font_header(image, font) + field);
}

/* The four points the size setters and vqt_attributes answer for a font (`$fce382..`, `$fce5e8..`, the
 * same instructions): the widest character, the top, the widest cell and the cell's height — the top read
 * once, after the first point is stored. The callers' contrl counts and result flag are theirs. */
#define FONT_SIZE_ANSWER_POINTS 2

static inline void answer_font_size(uint8_t *image, uint32_t font)
{
    uint8_t *ptsout = image + linea_pointer(image, LINEA_PTSOUT);
    uint16_t top;

    wr16(ptsout, font_word(image, font, FONT_MAX_CHAR_WIDTH));
    top = font_word(image, font, FONT_TOP);
    wr16(ptsout + VDI_WORD_BYTES, top);
    wr16(ptsout + 2 * VDI_WORD_BYTES, font_word(image, font, FONT_MAX_CELL_WIDTH));
    wr16(ptsout + 3 * VDI_WORD_BYTES, (uint16_t)(top + font_word(image, font, FONT_BOTTOM) + 1));
}
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_FONT_H */
