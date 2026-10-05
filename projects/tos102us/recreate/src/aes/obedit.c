/* obedit.c — THE OBJECT EDITOR (`aes/obedit.h`): ob_edit and the gemobed helpers it calls — Alcyon C in the ROM,
 * ported over its own order.
 *
 * Every read is where the ROM makes it, because the caller's pointers can lie over what the editor writes: the index
 * word is re-read after every store and call (`move.w (a5)` each time), and the TEDINFO's pointers out of the AES_EDBLK
 * copy when each is used. A string or index is a SIGNED word (`movea.w` / `ext.l` before it is added), every pointer a
 * caller hands in is put on the 24-bit bus.
 *
 * THE FRAMES ARE THE ROM's where an address escapes: pxl_rect's GRECT (to ob_actxywh and gr_just), curfld's two
 * GRECTs (to pxl_rect and the clip calls) and ob_edit's start/finish words and typed character (to ob_stfn and check)
 * stand in through `host_slot.h` off target, each laid out as the ROM's `link` lays it.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/obedit.h"
#include "aes/obuser.h"
#include "aes/resource.h"
#include "aes/strings.h"

#define HIGH_BYTE_SHIFT       8          /* a word's high byte, which `btst` of the flags word in memory reads ($fe9292) */
#define DRAW_THE_OBJECT_ONLY  0          /* curfld's ob_draw depth: the field alone ($fe94e6 clr.w)           */
/* Whether an edited key changed the field — ob_edit's -32(a6), which ob_delit's answer is stored into: 1 nothing to
 * redraw ($fe9766 move.w #1), 0 the changed stretch redrawn ($fe97b2 clr.w). */
#define FIELD_UNCHANGED       1
#define FIELD_CHANGED         0

/* curfld's frame (`link a6,#-20`): the cursor's GRECT at -16(a6), the clip saved at -8(a6) — its host slot laid out
 * from -16. */
#define CURFLD_CURSOR         0
#define CURFLD_SAVED_CLIP     GRECT_BYTES
/* ob_edit's frame locals whose addresses escape, from -42(a6): the typed character (a byte), the two places the edit
 * reaches after it (ob_stfn's), and the two before (ob_stfn's) — its host slot laid out from -42. */
#define EDIT_FRAME_BYTES      10
#define EDIT_CHARACTER        0          /* -42(a6), a byte                                                   */
#define EDIT_NEW_FINISH       2          /* -40(a6)                                                           */
#define EDIT_NEW_START        4          /* -38(a6)                                                           */
#define EDIT_FINISH           6          /* -36(a6)                                                           */
#define EDIT_START            8          /* -34(a6)                                                           */

/* $fe9260 — ob_getsp: the object's TEDINFO copied whole into `tedinfo` — its ob_spec, or the longword an INDIRECT
 * ob_spec names (the flags read first). */
void aes_ob_getsp(uint8_t *image, uint32_t tree, int16_t object, uint32_t tedinfo)
{
    uint16_t flags = (uint16_t)object_word(image, tree, object, OB_FLAGS);
    uint32_t spec = bus_long(image, object_address(tree, object, OB_SPEC));

    if (flags >> HIGH_BYTE_SHIFT >> OB_FLAG_INDIRECT_BIT & 1u)
        spec = bus_long(image, spec);
    aes_lbcopy(image, tedinfo, spec, TE_BYTES);
}

/* $fe9352 — scan_to_end: from `template`, the index advanced by every placeholder passed before the template's
 * `character` (its low byte) or its end. */
int16_t aes_scan_to_end(uint8_t *image, uint32_t template, int16_t index, int16_t character)
{
    uint8_t byte;

    while ((byte = bus_byte(image, template)) != STRING_NUL && byte != (uint8_t)character) {
        template++;
        if (byte == OB_FORMAT_PLACEHOLDER)
            index++;
    }
    return index;
}

/* $fe937e — ins_char: `character` (its low byte) inserted at `at`, the string's bytes from there moved up one (from
 * its last down), then the string ended: at its old length + 1 while `room` is more than that, else at `room` - 1,
 * the last byte dropped. The length a WORD, compared signed; every index a signed word. */
void aes_ins_char(uint8_t *image, uint32_t string, int16_t at, int16_t character, int16_t room)
{
    int16_t length = aes_strlen(image, string);
    int16_t place;

    for (place = length; place > at; place--)
        set_bus_byte(image, offset_by(string, place), bus_byte(image, offset_by(string, place) - 1));
    set_bus_byte(image, offset_by(string, place), (uint8_t)character);
    if (room > (int16_t)(length + 1))
        set_bus_byte(image, offset_by(string, length) + 1, STRING_NUL);
    else
        set_bus_byte(image, offset_by(string, room) - 1, STRING_NUL);
}

/* $fe93da — find_pos: the template's place of raw character `index` — `index` placeholders passed (the walk reads on
 * past the NUL until it has), then on to the next placeholder or the NUL. */
int16_t aes_find_pos(uint8_t *image, uint32_t template, int16_t index)
{
    int16_t place = 0;
    uint8_t byte;

    /* Inlined into ob_stfn the template is AES_TMPLT, a constant GCC re-adds to every byte's address; held in a
     * register instead, each byte is one indexed compare (measured: ob_stfn over a full path 1.17 -> 0.95). */
    CURSOR_BARRIER(template);
    for (; index > 0; place++)
        if (bus_byte(image, offset_by(template, place)) == OB_FORMAT_PLACEHOLDER)
            index--;
    while ((byte = bus_byte(image, offset_by(template, place))) != STRING_NUL && byte != OB_FORMAT_PLACEHOLDER)
        place++;
    return place;
}

/* $fe941c — pxl_rect: the screen cell of template `position` of the edited field — the object's GRECT (ob_actxywh),
 * its corner moved by gr_just as AES_EDBLK's template would be drawn in it, then `position` cells right — into `rect`,
 * one character cell wide and high. gr_just's count is stored and never read: a frame word, not an output. */
void aes_pxl_rect(uint8_t *image, uint32_t tree, int16_t object, int16_t position, uint32_t rect)
{
    uint16_t local[GRECT_WORDS];
    uint32_t field = host_slot_claim(AES_PXL_RECT_FIELD, local);
    _Static_assert(sizeof local == HOST_SLOT_AES_PXL_RECT_FIELD_BYTES, "pxl_rect's GRECT and its host slot");

    aes_ob_actxywh(image, tree, object, field);
    (void)aes_gr_just(image, (int16_t)be16(image + AES_EDBLK + TE_JUST), (int16_t)be16(image + AES_EDBLK + TE_FONT),
                      be32(image + AES_EDBLK + TE_PTMPLT), (int16_t)be16(image + field + GRECT_W),
                      (int16_t)be16(image + field + GRECT_H), field);
    set_bus_word(image, rect + GRECT_X, (uint16_t)(m68k_muls_w((uint16_t)position, be16(image + AES_GL_WCHAR))
                                                   + be16(image + field + GRECT_X)));
    set_bus_word(image, rect + GRECT_Y, be16(image + field + GRECT_Y));
    set_bus_word(image, rect + GRECT_W, be16(image + AES_GL_WCHAR));
    set_bus_word(image, rect + GRECT_H, be16(image + AES_GL_HCHAR));
    host_slot_release(AES_PXL_RECT_FIELD);
}

/* $fe948a — curfld: under a clip of its own, either the CURSOR at template `position` — a line down the cell from 3
 * pixels above to 3 below, black in XOR — or, for `characters` > 0, the field's object redrawn under a clip from that
 * cell `characters` cells wide. The clip it found is put back. */
void aes_curfld(uint8_t *image, uint32_t tree, int16_t object, int16_t position, int16_t characters)
{
    uint16_t local[2 * GRECT_WORDS];
    uint32_t frame = host_slot_claim(AES_CURFLD_RECTS, local);
    _Static_assert(sizeof local == HOST_SLOT_AES_CURFLD_RECTS_BYTES, "curfld's two GRECTs and their host slot");
    uint32_t cursor = frame + CURFLD_CURSOR, saved_clip = frame + CURFLD_SAVED_CLIP;

    aes_pxl_rect(image, tree, object, position, cursor);
    if (characters) {
        wr16(image + cursor + GRECT_W, (uint16_t)(be16(image + cursor + GRECT_W)
                                                  + m68k_muls_w((uint16_t)(characters - 1), be16(image + AES_GL_WCHAR))));
    } else {
        aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_XOR, CURSOR_COLOUR);
        wr16(image + cursor + GRECT_Y, (uint16_t)(be16(image + cursor + GRECT_Y) - CURSOR_ABOVE));
        wr16(image + cursor + GRECT_H, (uint16_t)(be16(image + cursor + GRECT_H) + CURSOR_GROWTH));
    }
    aes_gsx_gclip(image, saved_clip);
    (void)aes_gsx_sclip(image, cursor);
    if (characters) {
        aes_ob_draw(image, tree, object, DRAW_THE_OBJECT_ONLY);
    } else {
        int16_t x = (int16_t)be16(image + cursor + GRECT_X), top = (int16_t)be16(image + cursor + GRECT_Y);

        aes_gsx_cline(image, x, top, x, (int16_t)(top + (int16_t)be16(image + cursor + GRECT_H) - 1));
    }
    (void)aes_gsx_sclip(image, saved_clip);
    host_slot_release(AES_CURFLD_RECTS);
}

/* $fe9516 — instr: 1 when `character` (its low byte) lies in `set` — each of the set's characters, or a range "a..z"
 * from its first to its last, compared as SIGNED bytes — else 0. A range's last character is taken whatever it is,
 * the set's NUL too, and the walk goes on past it. */
int16_t aes_instr(uint8_t *image, int16_t character, uint32_t set)
{
    int8_t wanted = (int8_t)character, first, last;

    while (bus_byte(image, set) != STRING_NUL) {
        first = last = (int8_t)bus_byte(image, set++);
        if (bus_byte(image, set) == INSTR_RANGE_DOT && bus_byte(image, set + 1) == INSTR_RANGE_DOT) {
            set += 2;
            last = (int8_t)bus_byte(image, set++);
        }
        if (wanted >= first && wanted <= last)
            return 1;
    }
    return 0;
}

/* The resource string a validation character names, and whether a character it takes is upcased (`aes/obedit.h`):
 * CHECK_NO_SET for one that names none. */
static int16_t set_of(int8_t valid, int *upcase)
{
    *upcase = 1;
    switch (valid) {
    case VALID_DIGIT:              *upcase = 0; return STNUM;
    case VALID_ALPHA:              return STALPHA;
    case VALID_ALPHANUMERIC:       return STANUM;
    case VALID_PATH:               return STPATH;
    case VALID_LOWER_PATH:         return STLPATH;
    case VALID_FILE:               return STFILE;
    case VALID_LOWER_FILE:         return STLFILE;
    case VALID_LOWER_ALPHA:        *upcase = 0; return STLALPHA;
    case VALID_LOWER_ALPHANUMERIC: *upcase = 0; return STLANUM;
    default:                       return CHECK_NO_SET;
    }
}

/* The character at `character` upcased in place (toupper of it sign-extended, its low byte stored). */
static void upcase_in_place(uint8_t *image, uint32_t character)
{
    set_bus_byte(image, character, (uint8_t)aes_toupper((int8_t)bus_byte(image, character)));
}

/* $fe9556 — check: 1 when the character at `character` passes validation character `valid` (its low byte; search table
 * $fefb10) — 'X' anything, 'x' anything upcased in place, the others a character of the resource string they name
 * (rs_str, then the character read), upcased in place by the upper-case ones — else 0. */
int16_t aes_check(uint8_t *image, uint32_t character, int16_t valid)
{
    int upcase;
    int16_t set;
    uint32_t members;

    if ((int8_t)valid == VALID_ANY)
        return 1;
    if ((int8_t)valid == VALID_ANY_UPPER) {
        upcase_in_place(image, character);
        return 1;
    }
    set = set_of((int8_t)valid, &upcase);
    if (set == CHECK_NO_SET)
        return 0;
    members = aes_rs_str(image, set);
    if (!aes_instr(image, (int8_t)bus_byte(image, character), members))
        return 0;
    if (upcase)
        upcase_in_place(image, character);
    return 1;
}

/* $fe95f2 — ob_stfn: where raw character `index` and the raw text's end lie in the template (find_pos of each), into
 * `start` and `finish` — the first stored before the raw text is measured. */
void aes_ob_stfn(uint8_t *image, int16_t index, uint32_t start, uint32_t finish)
{
    set_bus_word(image, start, (uint16_t)aes_find_pos(image, AES_TMPLT, index));
    set_bus_word(image, finish, (uint16_t)aes_find_pos(image, AES_TMPLT, aes_strlen(image, AES_RAWSTR)));
}

/* $fe962a — ob_delit: the raw text's character at `index` deleted (strcpy of the rest down over it), answering 0 — or
 * 1, and nothing done, when the index is at the text's end. */
int16_t aes_ob_delit(uint8_t *image, int16_t index)
{
    uint32_t at = offset_by(AES_RAWSTR, index);

    if (bus_byte(image, at) == STRING_NUL)
        return 1;
    (void)aes_strcpy(image, at + 1, at);
    return 0;
}

/* ---- ob_edit ------------------------------------------------------------------------------------------------------ */
/* The index word the caller's pointer names, read where the ROM reads it (`move.w (a5)`), and stored. */
static inline int16_t index_at(const uint8_t *image, uint32_t index)
{
    return (int16_t)bus_word(image, index);
}

static inline void set_index(uint8_t *image, uint32_t index, int16_t value)
{
    set_bus_word(image, index, (uint16_t)value);
}

/* The copy's te_txtlen less OB_EDIT_TEXT_SPARE: the last index a character is typed or deleted at — AES_EDBLK read
 * at each use, as the ROM reads it ($fe97ba, $fe97f2, $fe9888 move.w $9c38). */
static inline int16_t last_index(const uint8_t *image)
{
    return (int16_t)((int16_t)be16(image + AES_EDBLK + TE_TXTLEN) - OB_EDIT_TEXT_SPARE);
}

/* $fe96d4 — the validation string copied into AES_VALSTR and stretched to the template's length (te_tmplen, read each
 * time round) by repeating its last character, then ended. lstcpy's count is a BYTE's: a string of 256 counts 0. */
static void stretch_the_validation(uint8_t *image)
{
    int16_t copied = aes_lstcpy(image, AES_VALSTR, be32(image + AES_EDBLK + TE_PVALID));
    int16_t length = copied;

    while (copied > 0 && (int16_t)be16(image + AES_EDBLK + TE_TMPLEN) > length) {
        set_bus_byte(image, offset_by(AES_VALSTR, length), bus_byte(image, offset_by(AES_VALSTR, copied) - 1));
        length++;
    }
    set_bus_byte(image, offset_by(AES_VALSTR, length), STRING_NUL);
}

/* $fe97f0 — a TYPED key: past the last index, the index and `start` are first stepped back one (so the character
 * replaces the last). Its character (the key's low byte, a frame byte check may upcase) is inserted when its
 * validation character takes it; otherwise, when it is a literal of the template (scan_to_end from `start`), the raw
 * text is blank-filled up to the literal's place and ended there, the index moved to it — the step back undone
 * first, in the index and the walk's start but not in the frame's `start`. A NUL character does nothing. */
static int16_t type_key(uint8_t *image, uint32_t frame, uint32_t index, int16_t key, int16_t start)
{
    int stepped_back = 0;
    int16_t place;

    if (last_index(image) < index_at(image, index)) {
        start--;
        set_local_word(image, frame, EDIT_START, start);
        stepped_back = 1;
        set_index(image, index, (int16_t)(index_at(image, index) - 1));
    }
    image[frame + EDIT_CHARACTER] = (uint8_t)(key & OB_EDIT_ASCII_MASK);
    if (image[frame + EDIT_CHARACTER] == STRING_NUL)
        return FIELD_UNCHANGED;
    if (aes_check(image, frame + EDIT_CHARACTER, (int8_t)bus_byte(image, offset_by(AES_VALSTR, index_at(image, index))))) {
        aes_ins_char(image, AES_RAWSTR, index_at(image, index), (int8_t)image[frame + EDIT_CHARACTER],
                     (int16_t)be16(image + AES_EDBLK + TE_TXTLEN));
        set_index(image, index, (int16_t)(index_at(image, index) + 1));
        return FIELD_CHANGED;
    }
    if (stepped_back) {
        set_index(image, index, (int16_t)(index_at(image, index) + 1));
        start++;
    }
    place = aes_scan_to_end(image, offset_by(AES_TMPLT, start), index_at(image, index),
                            (int8_t)image[frame + EDIT_CHARACTER]);
    if (last_index(image) <= place)
        return FIELD_UNCHANGED;
    /* The ROM pushes bfill's byte as the word $3920; bfill stores its low byte. */
    aes_bfill(image, (int16_t)(place - index_at(image, index)), STRING_SPACE,
              offset_by(AES_RAWSTR, index_at(image, index)));
    set_bus_byte(image, offset_by(AES_RAWSTR, place), STRING_NUL);
    set_index(image, index, place);
    return FIELD_CHANGED;
}

/* $fe97ac..$fe97ec — the five editing keys (search table $fefb70) and the typed one, over the raw text in AES_RAWSTR:
 * whether the field changed. */
static int16_t edit_key(uint8_t *image, uint32_t frame, uint32_t index, int16_t key, int16_t start)
{
    int16_t unchanged = FIELD_UNCHANGED;

    switch (key) {
    case OB_EDIT_KEY_ESCAPE:
        set_index(image, index, 0);
        set_bus_byte(image, AES_RAWSTR, STRING_NUL);
        return FIELD_CHANGED;
    case OB_EDIT_KEY_BACKSPACE:
        if (index_at(image, index) > 0) {
            set_index(image, index, (int16_t)(index_at(image, index) - 1));
            unchanged = aes_ob_delit(image, index_at(image, index));
        }
        return unchanged;
    case OB_EDIT_KEY_DELETE:
        if (last_index(image) >= index_at(image, index))
            unchanged = aes_ob_delit(image, index_at(image, index));
        return unchanged;
    case OB_EDIT_KEY_LEFT:
        if (index_at(image, index) > 0)
            set_index(image, index, (int16_t)(index_at(image, index) - 1));
        return unchanged;
    case OB_EDIT_KEY_RIGHT:
        if (aes_strlen(image, AES_RAWSTR) > index_at(image, index))
            set_index(image, index, (int16_t)(index_at(image, index) + 1));
        return unchanged;
    default:
        return type_key(image, frame, index, key, start);
    }
}

/* $fe98fa — a changed field redrawn: merged again (ob_format), its new start and finish found (ob_stfn), and the
 * object redrawn under a clip from the lower start to the higher finish — when that stretch is not empty. */
static void redraw_the_change(uint8_t *image, uint32_t frame, uint32_t tree, int16_t object, uint32_t index)
{
    int16_t characters;

    aes_ob_format(image, (int16_t)be16(image + AES_EDBLK + TE_JUST), AES_RAWSTR, AES_TMPLT, AES_FMTSTR);
    aes_ob_stfn(image, index_at(image, index), frame + EDIT_NEW_START, frame + EDIT_NEW_FINISH);
    set_local_word(image, frame, EDIT_START,
                   aes_min(local_word(image, frame, EDIT_START), local_word(image, frame, EDIT_NEW_START)));
    characters = (int16_t)(aes_max(local_word(image, frame, EDIT_FINISH), local_word(image, frame, EDIT_NEW_FINISH))
                           - local_word(image, frame, EDIT_START));
    if (characters)
        aes_curfld(image, tree, object, local_word(image, frame, EDIT_START), characters);
}

/* $fe9766 — EDCHAR: the cursor taken off (curfld at the index's start, which ob_stfn finds with the field's finish),
 * the key edited in, the raw text copied back into te_ptext, and a changed field redrawn. */
static void edit_a_key(uint8_t *image, uint32_t frame, uint32_t tree, int16_t object, int16_t key, uint32_t index)
{
    int16_t start, unchanged;

    aes_ob_stfn(image, index_at(image, index), frame + EDIT_START, frame + EDIT_FINISH);
    start = local_word(image, frame, EDIT_START);
    aes_curfld(image, tree, object, start, 0);
    unchanged = edit_key(image, frame, index, key, start);
    (void)aes_lstcpy(image, be32(image + AES_EDBLK + TE_PTEXT), AES_RAWSTR);
    if (unchanged == FIELD_CHANGED)
        redraw_the_change(image, frame, tree, object, index);
}

/* $fe9678 — ob_edit(tree, obj, key, &index, kind): EDSTART, or an object at or below the root, answers 1 and does
 * nothing. Otherwise the object's TEDINFO is copied into AES_EDBLK (ob_getsp), its template, raw text and validation
 * string into the editor's buffers — the validation stretched — and the two merged into AES_FMTSTR; then EDINIT puts
 * the index at the raw text's end and EDCHAR edits `key` in (`edit_a_key`); and every kind ends with the cursor drawn
 * at the index's place in the template (curfld, XOR). Answers 1. */
int16_t aes_ob_edit(uint8_t *image, uint32_t tree, int16_t object, int16_t key, uint32_t index, int16_t kind)
{
    uint16_t local[EDIT_FRAME_BYTES / M68K_WORD_BYTES];
    uint32_t frame;
    _Static_assert(sizeof local == HOST_SLOT_AES_OB_EDIT_FRAME_BYTES, "ob_edit's escaping locals and their host slot");

    if (kind == OB_EDIT_START || object <= 0)
        return 1;
    frame = host_slot_claim(AES_OB_EDIT_FRAME, local);
    aes_ob_getsp(image, tree, object, AES_EDBLK);
    (void)aes_lstcpy(image, AES_TMPLT, be32(image + AES_EDBLK + TE_PTMPLT));
    (void)aes_lstcpy(image, AES_RAWSTR, be32(image + AES_EDBLK + TE_PTEXT));
    stretch_the_validation(image);
    aes_ob_format(image, (int16_t)be16(image + AES_EDBLK + TE_JUST), AES_RAWSTR, AES_TMPLT, AES_FMTSTR);
    if (kind == OB_EDIT_INIT)
        set_index(image, index, aes_strlen(image, AES_RAWSTR));
    else if (kind == OB_EDIT_CHAR)
        edit_a_key(image, frame, tree, object, key, index);
    aes_curfld(image, tree, object, aes_find_pos(image, AES_TMPLT, index_at(image, index)), 0);
    host_slot_release(AES_OB_EDIT_FRAME);
    return 1;
}
