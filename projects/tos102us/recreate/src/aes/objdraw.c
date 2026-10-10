/* objdraw.c — the object draw path's drawer, just_draw (`aes/objdraw.h`): one object of a tree drawn at a screen
 * position — its box, its text, image, icon or user routine, its label, then its state's marks — Alcyon C in the ROM,
 * ported over its own order.
 *
 * THE FRAME IS THE ROM's. just_draw hands nearly every local it has to a callee by address — ob_sst fills six of them,
 * gr_crack five more, gsx_chkclip and the gr_ layer take its GRECTs, ob_user the object's — so the locals live in ONE
 * frame laid out as the ROM's `link a6,#-48` lays them (the offsets below, from A6), standing in through `host_slot.h`
 * off target, every one read where the ROM reads it. The ROM's two jump tables ($fefba0 for the border and fill,
 * $fefbcc for the contents) are the two `switch`es, their fall-throughs the tables' shared arms.
 *
 * WHAT IT DRAWS, by type (`aes/objects.h`'s G_*): a box (BOX, IBOX, BOXCHAR, BUTTON, BOXTEXT, FBOXTEXT) its border
 * and, but for IBOX, its fill; a text (TEXT, BOXTEXT, FTEXT, FBOXTEXT, BOXCHAR) its TEDINFO's string — an editable
 * one merged into its template first, a BOXCHAR's character as a one-byte string; an IMAGE its BITBLK; an ICON its
 * ICONBLK; a USERDEF its USERBLK's routine, whose answer becomes the state drawn; a STRING, TITLE or BUTTON its label.
 * Then each state bit's mark: OUTLINED, SHADOWED, CHECKED, CROSSED, DISABLED, SELECTED, in that order.
 *
 * FOUR OF ITS PARTS ARE ROUTINES OF THEIR OWN (`noinline`: the clip test, the border and fill, the label, the marks),
 * FOR THE STACK (`stack_diet.h`). The ROM's just_draw is one function of 76 bytes of frame; inlined whole, GCC's is 120
 * — every `image + frame + offset` any part uses kept in a register or spilt for all of them — and that frame stands
 * under an icon's blit, a USERDEF's routine and every object a menu draws, on the screen manager's 1,196 bytes. Apart,
 * just_draw holds the frame and five registers (80), and a part's own registers lie only under that part's calls.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/oblib.h"
#include "aes/obuser.h"
#include "aes/rect.h"
#include "aes/strings.h"

/* ---- the frame: `link a6,#-48`, each local at its offset from A6 --------------------------------------------------- */
#define FRAME_BYTES           48
#define FRAME_WORDS           (FRAME_BYTES / M68K_WORD_BYTES)
#define LOCAL(offset)         (FRAME_BYTES + (offset))     /* a local's place in the slot, from its offset off A6 */
#define FRAME_CLIP            LOCAL(-48) /* GRECT: the object grown by its border, tested against the clip ($fe9af6) */
#define FRAME_RECT            LOCAL(-40) /* GRECT: the object on the screen (A5, $fe9aa0)                          */
#define FRAME_SPEC            LOCAL(-24) /* long: ob_spec, or what an INDIRECT one names (ob_sst's)               */
#define FRAME_FLAGS           LOCAL(-20) /* word: ob_flags                                                       */
#define FRAME_TYPE            LOCAL(-16) /* word: the type                                                        */
#define FRAME_STATE           LOCAL(-14) /* word: ob_state — an icon's SELECTED cleared, a USERDEF's answer         */
#define FRAME_THICKNESS       LOCAL(-12) /* word: the border's thickness, signed — made its magnitude for the marks */
#define FRAME_MODE            LOCAL(-10) /* word: the text's writing mode (gr_crack's)                            */
#define FRAME_INTERIOR        LOCAL(-8)  /* word: the fill's colour                                               */
#define FRAME_PATTERN         LOCAL(-6)  /* word: ...and its pattern, the long below it with the colour (`clr.l`)  */
#define FRAME_TEXT_COLOUR     LOCAL(-4)  /* word                                                                  */
#define FRAME_BORDER          LOCAL(-2)  /* word: the border's colour                                             */

/* ---- the values it draws with -------------------------------------------------------------------------------------- */
#define COLOUR_WHITE          0          /* ($fe9eb4 clr.w: the outline's inner box, $fe9fe6 DISABLED's fill)       */
#define COLOUR_BLACK          1          /* ($fe9b40 the text's colour, the outline's outer box, labels)           */
/* The outline: one black line 3 pixels out, then two white lines inside it — (x, y) and (w, h) moved as packed
 * longwords ($fe9ea4 addi.l #$60006, $fe9eac subi.l #$30003, $fe9ec6 / $fe9ece the 4 and 2). */
#define OUTLINE_BLACK_OUT     3
#define OUTLINE_BLACK_LINES   1
#define OUTLINE_WHITE_OUT     2
#define OUTLINE_WHITE_LINES   2
#define OUTLINE_CLIP_GROWTH   3          /* the clip test's growth for an outlined object ($fe9afe moveq #-3)       */
#define BORDER_CLIP_FACTOR    3          /* ...any other's: 3 x its border's magnitude ($fe9b0e moveq #3, muls.w)    */
#define SHADOW_HEIGHT_FACTOR  3          /* the side shadow's height: h + 3 x the border ($fe9f3a muls.w #3)       */
#define SHADOW_STYLE          0          /* ($fe9f2c clr.w): bb_fill's style word, solid regardless               */
#define DISABLED_STYLE        4          /* the dither DISABLED is dimmed by ($fe9ff4 move.w #4)                   */
#define CHECK_MARK            8          /* the font's check mark ($fe9f7e move.w #8,$95ba)                        */
#define CHECK_MARK_CHARACTERS 1
#define CHECK_MARK_INDENT     2          /* ($fe9f8c addi.l #$20000: x + 2, the y word untouched)                  */
#define CROSS_LAST_PIXEL      1          /* the diagonals end at (x + w - 1, y + h - 1) ($fe9fb4 subi.l #$10001)    */
#define HALF                  2          /* a label centred by `divs.w #2`: toward zero                             */
#define FORM_BYTES_SHIFT      3          /* an IMAGE's width in pixels, its bytes x 8 ($fe9d22 asl.w #3)            */
#define NO_BACKGROUND         0          /* the IMAGE blit's background colour ($fe9d0a clr.w)                     */
#define SCREEN                0          /* gsx_blt's destination form: the screen ($fe9d36 clr.l)                 */
#define FIRST_BYTE            1          /* a one-character string: the character, then its NUL ($fe9cac $b84a)   */

/* One bit of the state's or the flags' LOW byte, as the ROM's `btst #n,-13(a6)` / `-19(a6)` reads it. */
static inline int local_bit(const uint8_t *image, uint32_t frame, uint32_t local, unsigned bit)
{
    return image[frame + local + OB_WORD_LOW_BYTE] >> bit & 1u;
}

/* A word difference halved by `ext.l` and `divs.w #2`: toward zero. */
static inline int16_t half_toward_zero(int16_t difference)
{
    return quotient_word(m68k_divs_w((uint32_t)(int32_t)difference, HALF));
}

/* The four types whose ob_spec is a TEDINFO the copy in AES_EDBLK is made of ($fe9b86..$fe9b9c). */
static inline int is_text_object(int16_t type)
{
    return type == G_TEXT || type == G_BOXTEXT || type == G_FTEXT || type == G_FBOXTEXT;
}

/* $fe9ae6 — the clip test, when the clip is on (its width and height both non-zero): a copy of the GRECT grown by 3
 * for an outlined object, else by 3 x the border's magnitude (`muls.w`, its low word), must touch the clip. */
static __attribute__((noinline)) int outside_the_clip(uint8_t *image, uint32_t frame)
{
    uint32_t clip = frame + FRAME_CLIP;
    int16_t growth = -OUTLINE_CLIP_GROWTH, thickness;

    if (!be16(image + AES_GL_WCLIP) || !be16(image + AES_GL_HCLIP))
        return 0;
    aes_rc_copy(image, frame + FRAME_RECT, clip);
    if (!local_bit(image, frame, FRAME_STATE, OB_STATE_OUTLINED_BIT)) {
        thickness = local_word(image, frame, FRAME_THICKNESS);
        growth = (int16_t)m68k_muls_w((uint16_t)thickness,
                                      (uint16_t)(thickness < 0 ? BORDER_CLIP_FACTOR : -BORDER_CLIP_FACTOR));
    }
    aes_gr_inside(image, clip, growth);
    return !aes_gsx_chkclip(image, clip);
}

/* $fe9ba6 — gr_crack of a colour word into the frame's five colour locals. */
static void crack_colours(uint8_t *image, uint32_t frame, int16_t colour)
{
    aes_gr_crack(image, colour, frame + FRAME_BORDER, frame + FRAME_TEXT_COLOUR, frame + FRAME_PATTERN,
                 frame + FRAME_INTERIOR, frame + FRAME_MODE);
}

/* $fe9bda — a box's border, when it has one (gr_box in the border's colour, `thickness` lines in or out), and, but
 * for an IBOX, its inside filled (gr_rect of the GRECT shrunk by the border's inward part, then grown back). */
static void draw_box(uint8_t *image, uint32_t frame, int16_t inward)
{
    uint32_t rect = frame + FRAME_RECT;
    uint32_t corner, size;

    if (local_word(image, frame, FRAME_THICKNESS)) {
        aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_REPLACE, local_word(image, frame, FRAME_BORDER));
        size = be32(image + rect + GRECT_W);
        corner = be32(image + rect + GRECT_X);
        aes_gr_box(image, pair_high(corner), pair_low(corner), pair_high(size), pair_low(size),
                   local_word(image, frame, FRAME_THICKNESS));
    }
    if (local_word(image, frame, FRAME_TYPE) == G_IBOX)
        return;
    aes_gr_inside(image, rect, inward);
    aes_gr_rect(image, local_word(image, frame, FRAME_INTERIOR), local_word(image, frame, FRAME_PATTERN), rect);
    aes_gr_inside(image, rect, (int16_t)-inward);
}

/* $fe9b2a..$fe9c3e — the BORDER AND FILL: the text colour black, replace; a text object's TEDINFO copied and its
 * colour word cracked; then table $fefba0 — a box cracks the spec's colour word, a BUTTON (the ROM's re-test of the
 * type, $fe9bc8) a black border round a white hollow fill, and each of those and the two boxed texts its box. */
FRAME_DIET("no-defer-pop", "no-optimize-sibling-calls")
static __attribute__((noinline)) void draw_border_and_fill(uint8_t *image, uint32_t frame, int16_t type, int16_t inward)
{
    set_local_word(image, frame, FRAME_MODE, GSX_MODE_REPLACE);
    set_local_word(image, frame, FRAME_TEXT_COLOUR, COLOUR_BLACK);
    if (is_text_object(type)) {
        aes_lbcopy(image, AES_EDBLK, be32(image + frame + FRAME_SPEC), TE_BYTES);
        crack_colours(image, frame, (int16_t)be16(image + AES_EDBLK + TE_COLOR));
    }
    switch (type) {
    case G_BOX:
    case G_IBOX:
    case G_BOXCHAR:
        crack_colours(image, frame, (int16_t)be32(image + frame + FRAME_SPEC));
        /* fall through */
    case G_BUTTON:
        if (local_word(image, frame, FRAME_TYPE) == G_BUTTON) {
            set_local_word(image, frame, FRAME_BORDER, COLOUR_BLACK);
            wr32(image + frame + FRAME_INTERIOR, 0);
        }
        /* fall through */
    case G_BOXTEXT:
    case G_FBOXTEXT:
        draw_box(image, frame, inward);
        break;
    default:
        break;
    }
}

/* $fe9c56 — an editable text: its raw text and template copied out of the TEDINFO (AES_EDBLK's pointers, read in
 * turn) and merged by ob_format into AES_FMTSTR. */
static void format_text(uint8_t *image)
{
    aes_lstcpy(image, AES_RAWSTR, be32(image + AES_EDBLK + TE_PTEXT));
    aes_lstcpy(image, AES_TMPLT, be32(image + AES_EDBLK + TE_PTMPLT));
    aes_ob_format(image, (int16_t)be16(image + AES_EDBLK + TE_JUST), AES_RAWSTR, AES_TMPLT, AES_FMTSTR);
}

/* $fe9cc2 — a text in its GRECT shrunk by the border's inward part: gr_gtext of the copy's string, justification
 * and font, the GRECT grown back after. */
static void draw_text(uint8_t *image, uint32_t frame, int16_t inward)
{
    uint32_t rect = frame + FRAME_RECT;

    aes_gr_inside(image, rect, inward);
    aes_gr_gtext(image, (int16_t)be16(image + AES_EDBLK + TE_JUST), (int16_t)be16(image + AES_EDBLK + TE_FONT),
                 be32(image + AES_EDBLK + TE_PTEXT), rect);
    aes_gr_inside(image, rect, (int16_t)-inward);
}

/* $fe9cfa — an IMAGE: its BITBLK copied into AES_BI and its form blitted transparently onto the screen at the GRECT's
 * corner, `bi_wb` x 8 pixels wide (`asl.w`), in its colour. The screen's row, gl_width / 8 (`divs.w`), is computed and
 * handed on as the ROM does — and never read: gsx_fix's screen arm takes the screen's own width. */
static void draw_image(uint8_t *image, uint32_t frame)
{
    uint32_t corner, from;
    uint16_t form_bytes;

    aes_lbcopy(image, AES_BI, be32(image + frame + FRAME_SPEC), BI_BYTES);
    form_bytes = be16(image + AES_BI + BI_WB);
    corner = be32(image + frame + FRAME_RECT + GRECT_X);
    from = be32(image + AES_BI + BI_X);
    aes_gsx_blt(image, be32(image + AES_BI + BI_PDATA), pair_high(from), pair_low(from), (int16_t)form_bytes, SCREEN,
                pair_high(corner), pair_low(corner),
                gsx_screen_row_bytes(image),
                (int16_t)(uint16_t)(form_bytes << FORM_BYTES_SHIFT), (int16_t)be16(image + AES_BI + BI_HL),
                GSX_MODE_TRANSPARENT, (int16_t)be16(image + AES_BI + BI_COLOR), NO_BACKGROUND);
}

/* $fe9d56 — an ICON: its ICONBLK copied into AES_IB, the copy's two GRECTs moved by the object's corner (`add.l`,
 * packed), gr_gicon of the copy — then SELECTED cleared from the state, which gr_gicon has drawn by its colours. */
static void draw_icon(uint8_t *image, uint32_t frame)
{
    uint32_t corner, character;

    aes_lbcopy(image, AES_IB, be32(image + frame + FRAME_SPEC), IB_BYTES);
    corner = be32(image + frame + FRAME_RECT + GRECT_X);
    wr32(image + AES_IB + IB_XICON, packed_add(be32(image + AES_IB + IB_XICON), corner));
    wr32(image + AES_IB + IB_XTEXT, packed_add(be32(image + AES_IB + IB_XTEXT), corner));
    character = be32(image + AES_IB + IB_CHAR);
    aes_gr_gicon(image, local_word(image, frame, FRAME_STATE), be32(image + AES_IB + IB_PMASK),
                 be32(image + AES_IB + IB_PDATA), be32(image + AES_IB + IB_PTEXT), pair_high(character),
                 pair_low(character), (int16_t)be16(image + AES_IB + IB_YCHAR), AES_IB + IB_XICON,
                 AES_IB + IB_XTEXT);
    set_local_word(image, frame, FRAME_STATE,
                   (int16_t)(local_word(image, frame, FRAME_STATE) & ~(1 << OB_STATE_SELECTED_BIT)));
}

/* $fe9c3e..$fe9de8 — the CONTENTS: the text colour and mode set, then table $fefbcc — an editable text formatted, it or
 * a BOXCHAR (its character a one-byte string, centred in the IBM font) pointed at AES_FMTSTR, and every text drawn;
 * an IMAGE, an ICON, or a USERDEF's routine, whose answer is the state drawn from here on. */
static void draw_contents(uint8_t *image, uint32_t tree, int16_t object, uint32_t frame, int16_t type, int16_t inward,
                          uint8_t character)
{
    aes_gsx_attr(image, GSX_TEXT_TEXT, local_word(image, frame, FRAME_MODE), local_word(image, frame, FRAME_TEXT_COLOUR));
    switch (type) {
    case G_FTEXT:
    case G_FBOXTEXT:
        format_text(image);
        /* fall through */
    case G_BOXCHAR:
        wr32(image + AES_EDBLK + TE_PTEXT, AES_FMTSTR);
        if (local_word(image, frame, FRAME_TYPE) == G_BOXCHAR) {
            image[AES_FMTSTR] = character;
            image[AES_FMTSTR + FIRST_BYTE] = STRING_NUL;
            wr16(image + AES_EDBLK + TE_JUST, GSX_JUST_CENTRE);
            wr16(image + AES_EDBLK + TE_FONT, GSX_FONT_IBM);
        }
        /* fall through */
    case G_TEXT:
    case G_BOXTEXT:
        draw_text(image, frame, inward);
        break;
    case G_IMAGE:
        draw_image(image, frame);
        break;
    case G_ICON:
        draw_icon(image, frame);
        break;
    case G_USERDEF:
        set_local_word(image, frame, FRAME_STATE,
                       (int16_t)aes_ob_user(image, tree, object, frame + FRAME_RECT, be32(image + frame + FRAME_SPEC),
                                            local_word(image, frame, FRAME_STATE), local_word(image, frame, FRAME_STATE)));
        break;
    default:
        break;
    }
}

/* $fe9dea — a STRING's, TITLE's or BUTTON's LABEL: the spec's string into the AES's intin (xstrpix); if it has any
 * characters, black and transparent, drawn in the IBM font centred down the GRECT — and, a BUTTON's, across it — each
 * a WORD difference halved toward zero. */
static __attribute__((noinline)) void draw_label(uint8_t *image, uint32_t frame)
{
    uint32_t rect = frame + FRAME_RECT;
    int16_t characters = aes_xstrpix(image, be32(image + AES_AD_INTIN), be32(image + frame + FRAME_SPEC));
    int16_t x, y;

    if (!characters)
        return;
    aes_gsx_attr(image, GSX_TEXT_TEXT, GSX_MODE_TRANSPARENT, COLOUR_BLACK);
    y = (int16_t)(half_toward_zero((int16_t)(be16(image + rect + GRECT_H) - be16(image + AES_GL_HCHAR)))
                  + be16(image + rect + GRECT_Y));
    x = (int16_t)be16(image + rect + GRECT_X);
    if (local_word(image, frame, FRAME_TYPE) == G_BUTTON)
        x = (int16_t)(half_toward_zero((int16_t)(be16(image + rect + GRECT_W)
                                                 - (uint16_t)m68k_muls_w((uint16_t)characters,
                                                                         be16(image + AES_GL_WCHAR))))
                      + x);
    aes_gsx_tblt(image, GSX_FONT_IBM, x, y, characters);
}

/* One of the outline's boxes: `lines` thick in `colour`, its corner `out` pixels outside the GRECT's on each side. */
static inline void outline_box(uint8_t *image, uint32_t rect, int16_t colour, int16_t out, int16_t lines)
{
    uint32_t size, corner;

    aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_REPLACE, colour);
    size = packed_add(be32(image + rect + GRECT_W), words_long(2 * out, 2 * out));
    corner = packed_sub(be32(image + rect + GRECT_X), words_long(out, out));
    aes_gr_box(image, pair_high(corner), pair_low(corner), pair_high(size), pair_low(size), lines);
}

/* $fe9e88 — OUTLINED: a black line 3 pixels outside the GRECT, then two white ones inside that. */
static void draw_outline(uint8_t *image, uint32_t rect)
{
    outline_box(image, rect, COLOUR_BLACK, OUTLINE_BLACK_OUT, OUTLINE_BLACK_LINES);
    outline_box(image, rect, COLOUR_WHITE, OUTLINE_WHITE_OUT, OUTLINE_WHITE_LINES);
}

/* $fe9ef8 — SHADOWED, with a border: in the border's colour, a solid band `2 x border` deep below the GRECT (it and
 * the border wide) and one `2 x border` wide down its right (from its top to the band's bottom). Word sums. */
static void draw_shadow(uint8_t *image, uint32_t frame)
{
    uint32_t rect = frame + FRAME_RECT;
    int16_t x, y, width, height;

    aes_gsx_1code(image, VDI_ROM_VSF_COLOR_OPCODE, local_word(image, frame, FRAME_BORDER));
    height = (int16_t)(local_word(image, frame, FRAME_THICKNESS) << 1);
    width = (int16_t)(be16(image + rect + GRECT_W) + local_word(image, frame, FRAME_THICKNESS));
    y = (int16_t)(be16(image + rect + GRECT_Y) + be16(image + rect + GRECT_H) + local_word(image, frame, FRAME_THICKNESS));
    x = (int16_t)be16(image + rect + GRECT_X);
    aes_bb_fill(image, GSX_MODE_REPLACE, GSX_FIS_SOLID, SHADOW_STYLE, x, y, width, height);
    height = (int16_t)(m68k_muls_w((uint16_t)local_word(image, frame, FRAME_THICKNESS), SHADOW_HEIGHT_FACTOR)
                       + be16(image + rect + GRECT_H));
    width = (int16_t)(local_word(image, frame, FRAME_THICKNESS) << 1);
    y = (int16_t)be16(image + rect + GRECT_Y);
    x = (int16_t)(be16(image + rect + GRECT_X) + be16(image + rect + GRECT_W) + local_word(image, frame, FRAME_THICKNESS));
    aes_bb_fill(image, GSX_MODE_REPLACE, GSX_FIS_SOLID, SHADOW_STYLE, x, y, width, height);
}

/* The far corner CROSSED draws to: (x, y) + (w, h) - (1, 1), PACKED — a height of 0 borrows from the width. */
static uint32_t far_corner(const uint8_t *image, uint32_t rect)
{
    return packed_add(be32(image + rect + GRECT_X),
                      packed_sub(be32(image + rect + GRECT_W), words_long(CROSS_LAST_PIXEL, CROSS_LAST_PIXEL)));
}

/* $fe9fa4 — CROSSED: white lines, transparent, corner to corner — (x, y) to the far corner, then (x, its y) to (its
 * x, y). */
static void draw_cross(uint8_t *image, uint32_t rect)
{
    uint32_t corner, far;

    aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_TRANSPARENT, COLOUR_WHITE);
    far = far_corner(image, rect);
    corner = be32(image + rect + GRECT_X);
    aes_gsx_cline(image, pair_high(corner), pair_low(corner), pair_high(far), pair_low(far));
    far = far_corner(image, rect);
    corner = be32(image + rect + GRECT_X);
    aes_gsx_cline(image, pair_high(corner), pair_low(far), pair_high(far), pair_low(corner));
}

/* bb_fill over the frame's GRECT, its two longwords read as the ROM pushes them (w and h, then x and y). */
static void fill_rect(uint8_t *image, int16_t mode, int16_t interior, int16_t style, uint32_t rect)
{
    uint32_t size = be32(image + rect + GRECT_W), corner = be32(image + rect + GRECT_X);

    aes_bb_fill(image, mode, interior, style, pair_high(corner), pair_low(corner), pair_high(size), pair_low(size));
}

/* $fe9e80 — the STATE's marks, when there is any state at all (the whole word): each bit in turn. A positive border
 * shrinks the GRECT first (the marks drawn inside it), a negative one is made its magnitude (`neg.w` in the frame). */
FRAME_DIET("no-defer-pop", "no-caller-saves")
static __attribute__((noinline)) void draw_state_marks(uint8_t *image, uint32_t frame)
{
    uint32_t rect = frame + FRAME_RECT, corner;
    int16_t border;

    if (local_bit(image, frame, FRAME_STATE, OB_STATE_OUTLINED_BIT))
        draw_outline(image, rect);
    border = local_word(image, frame, FRAME_THICKNESS);
    if (border > 0)
        aes_gr_inside(image, rect, border);
    else
        set_local_word(image, frame, FRAME_THICKNESS, (int16_t)-border);
    if (local_bit(image, frame, FRAME_STATE, OB_STATE_SHADOWED_BIT) && local_word(image, frame, FRAME_THICKNESS))
        draw_shadow(image, frame);
    if (local_bit(image, frame, FRAME_STATE, OB_STATE_CHECKED_BIT)) {
        aes_gsx_attr(image, GSX_TEXT_TEXT, GSX_MODE_TRANSPARENT, COLOUR_BLACK);
        wr16(image + GSX_INTIN_WORD(0), CHECK_MARK);
        corner = packed_add(be32(image + rect + GRECT_X), words_long(CHECK_MARK_INDENT, 0));
        aes_gsx_tblt(image, GSX_FONT_IBM, pair_high(corner), pair_low(corner), CHECK_MARK_CHARACTERS);
    }
    if (local_bit(image, frame, FRAME_STATE, OB_STATE_CROSSED_BIT))
        draw_cross(image, rect);
    if (local_bit(image, frame, FRAME_STATE, OB_STATE_DISABLED_BIT)) {
        aes_gsx_1code(image, VDI_ROM_VSF_COLOR_OPCODE, COLOUR_WHITE);
        fill_rect(image, GSX_MODE_TRANSPARENT, GSX_FIS_PATTERN, DISABLED_STYLE, rect);
    }
    if (local_bit(image, frame, FRAME_STATE, OB_STATE_SELECTED_BIT))
        fill_rect(image, GSX_MODE_XOR, GSX_FIS_SOLID, GSX_PATTERN_SOLID, rect);
}

/* The whole drawing, over the frame `aes_just_draw` holds. */
static void draw_object(uint8_t *image, uint32_t tree, int16_t object, int16_t x, int16_t y, uint32_t frame)
{
    uint8_t character;
    int16_t type, inward;

    character = (uint8_t)aes_ob_sst(image, tree, object, frame + FRAME_SPEC, frame + FRAME_STATE, frame + FRAME_TYPE,
                                    frame + FRAME_FLAGS, frame + FRAME_RECT, frame + FRAME_THICKNESS);
    if (local_bit(image, frame, FRAME_FLAGS, OB_FLAG_HIDETREE_BIT) || be32(image + frame + FRAME_SPEC) == OB_SPEC_NONE)
        return;
    set_local_word(image, frame, FRAME_RECT + GRECT_X, x);
    set_local_word(image, frame, FRAME_RECT + GRECT_Y, y);
    if (outside_the_clip(image, frame))
        return;
    type = local_word(image, frame, FRAME_TYPE);
    if (type != G_STRING) {
        inward = local_word(image, frame, FRAME_THICKNESS);
        if (inward < 0)
            inward = 0;
        draw_border_and_fill(image, frame, type, inward);
        draw_contents(image, tree, object, frame, local_word(image, frame, FRAME_TYPE), inward, character);
    }
    type = local_word(image, frame, FRAME_TYPE);
    if (type == G_STRING || type == G_TITLE || type == G_BUTTON)
        draw_label(image, frame);
    if (local_word(image, frame, FRAME_STATE))
        draw_state_marks(image, frame);
}

/* $fe9a88 — just_draw. THE BORDER COLOUR IS READ UNSET for one cell: a TITLE (its border 1, from ob_sst) that is
 * SHADOWED reaches the shadow's `vsf_color` with FRAME_BORDER never written — no crack, no BUTTON — so it draws in
 * whatever the stack held there (in the ROM, a dead caller's frame word); the C reads its own frame's word the same
 * way. The AES's own trees carry no SHADOWED state (`test_aes_just_draw*.py` pins the read by staging both). */
FRAME_DIET("no-defer-pop", "no-gcse", "no-caller-saves")
void aes_just_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t x, int16_t y)
{
    uint16_t frame_local[FRAME_WORDS];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_JUST_DRAW_FRAME_BYTES, "just_draw's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_JUST_DRAW_FRAME, frame_local);

    draw_object(image, tree, object, x, y, frame);
    host_slot_release(AES_JUST_DRAW_FRAME);
}
