/* fmlib.c — the FORM LIBRARY's event-free half (`aes/fmlib.h`): an alert string split into the alert tree (fm_strbrk,
 * fm_parse) and laid out (fm_build), the next field or the default button found (find_obj, fm_inifld), a form key
 * turned into a move (fm_keybd), and the keyboard queue fm_do flushes (fq, dq). Alcyon C in the ROM, ported over its
 * own order.
 *
 * Every read is where the ROM makes it: the alert string is read a byte at a time between the stores into the line
 * buffers (an application's string may lie over them), each line's buffer is read out of the tree's ob_spec when the
 * line begins, and every word a routine stores through a caller's pointer is read back through it. An index is a
 * SIGNED word, every compare a signed one, every pointer a caller hands in is put on the 24-bit bus.
 *
 * THE FRAMES ARE THE ROM's where an address escapes: fm_parse's string index (to fm_strbrk) and fm_build's four GRECTs
 * (to r_set and ob_setxywh) stand in through `host_slot.h` off target, each laid out as the ROM's `link` lays it.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/fmlib.h"
#include "aes/gemgraf.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/rect.h"
#include "aes/strings.h"

/* fm_build: the box's width over the widest of the lines and the buttons row, a margin each side (ALERT_BUTTON_GAP);
 * beside an icon, the icon's cells and one more, its height the icon's and one more; the buttons on the box's last row
 * but one, the box then one row shorter and half a character cell taller in pixels. */
#define ALERT_ICON_MARGIN     1          /* ($fe6e96 addq.w #1, $fe6ea0 addq.w #1)                             */
#define ALERT_MIN_LINES       1          /* the box's height before the foot    ($fe6e2e move.w #1: max)       */
#define ALERT_BUTTONS_ABOVE   2          /* rows from the box's foot up to the buttons ($fe6ee4 subq.w #2)     */
#define ALERT_FOOT_TRIM       1          /* ($fe6ef8 subq.w #1)                                                */
#define ALERT_BUTTON_HEIGHT   1          /* ($fe6ed8 move.w #1)                                                */
#define ALERT_LINE_HEIGHT     1          /* ($fe6e50 move.w #1)                                                */
#define HALF                  2          /* ($fe6ed4, $fe6f04 divs.w #2)                                       */

/* fm_build's frame (`link a6,#-36`): ms at -32(a6), bt at -24(a6), ic at -16(a6), al at -8(a6) — its host slot laid out
 * from -32. */
#define BUILD_MESSAGE         0
#define BUILD_BUTTON          GRECT_BYTES
#define BUILD_ICON            (2 * GRECT_BYTES)
#define BUILD_ALERT           (3 * GRECT_BYTES)
#define BUILD_RECTS           4

/* A signed word added to an address, as `movea.w` then `adda.l` add it. */
static inline uint32_t offset_by(uint32_t address, int16_t index)
{
    return address + (uint32_t)(int32_t)index;
}

static inline int is_alert_delimiter(uint8_t character)
{
    return character == ALERT_SECTION_END || character == ALERT_SEPARATOR;
}

/* $fe6c98 — fm_strbrk: one section of an alert string, from *index_at to its ']', into the ob_spec strings of `object`
 * and the objects after it, their count unbounded: a '|' ends a line and starts the next; a delimiter doubled is itself,
 * once — but met at the cap its second stays a delimiter (a '|' then starts an empty line, a ']' ends the section);
 * past ALERT_LINE_CHARACTERS the line is ended and the rest skipped to its delimiter. A line ended by a NUL goes on by
 * the byte after it. Answers through the pointers, stored last and in this order: the index past the ']', the count of
 * lines, the longest line's length. */
void aes_fm_strbrk(uint8_t *image, uint32_t tree, uint32_t string, int16_t object, uint32_t index_at,
                   uint32_t count_at, uint32_t longest_at)
{
    int16_t index = (int16_t)bus_word(image, index_at);
    int16_t count = 0, longest = 0, length;
    uint8_t character = STRING_NUL;
    int16_t following = 0;                 /* -6(a6): the byte after the character, sign-extended */

    while (character != ALERT_SECTION_END) {
        uint32_t line = bus_long(image, object_address(tree, (int16_t)(count + object), OB_SPEC));

        length = 0;
        do {
            character = bus_byte(image, offset_by(string, index));
            if (length >= ALERT_LINE_CHARACTERS) {
                set_bus_byte(image, offset_by(line, length), STRING_NUL);
                while (!is_alert_delimiter(character = bus_byte(image, offset_by(string, index))))
                    index++;
            }
            index++;
            following = (int8_t)bus_byte(image, offset_by(string, index));
            if (is_alert_delimiter(character)) {
                if ((int8_t)character != following) {
                    following = (int8_t)character;
                    character = STRING_NUL;
                } else if (length < ALERT_LINE_CHARACTERS) {
                    index++;
                } else {
                    character = STRING_NUL;
                }
            }
            set_bus_byte(image, offset_by(line, length), character);
            length++;
        } while (character != STRING_NUL);
        character = (uint8_t)following;
        longest = aes_max((int16_t)(length - 1), longest);
        count++;
    }
    set_bus_word(image, index_at, (uint16_t)index);
    set_bus_word(image, count_at, (uint16_t)count);
    set_bus_word(image, longest_at, (uint16_t)longest);
}

/* $fe6d84 — fm_parse: the icon's digit, then the message section into the lines from ALERT_FIRST_LINE and the buttons'
 * into the buttons from ALERT_FIRST_BUTTON (the '[' between them skipped), the longest button counted one more. */
void aes_fm_parse(uint8_t *image, uint32_t tree, uint32_t string, uint32_t icon_at, uint32_t lines_at,
                  uint32_t line_length_at, uint32_t buttons_at, uint32_t button_length_at)
{
    uint16_t local;
    uint32_t index = host_slot_claim(AES_FM_PARSE_INDEX, &local);
    _Static_assert(sizeof local == HOST_SLOT_AES_FM_PARSE_INDEX_BYTES, "fm_parse's index and its host slot");

    set_bus_word(image, icon_at, (uint16_t)((int8_t)bus_byte(image, string + ALERT_ICON_DIGIT) - DIGIT_ZERO));
    wr16(image + index, ALERT_FIRST_LINE_AT);
    aes_fm_strbrk(image, tree, string, ALERT_FIRST_LINE, index, lines_at, line_length_at);
    wr16(image + index, (uint16_t)(be16(image + index) + 1));
    aes_fm_strbrk(image, tree, string, ALERT_FIRST_BUTTON, index, buttons_at, button_length_at);
    set_bus_word(image, button_length_at, (uint16_t)(bus_word(image, button_length_at) + 1));
    host_slot_release(AES_FM_PARSE_INDEX);
}

static inline void add_local_word(uint8_t *image, uint32_t frame, uint32_t local, int16_t addend)
{
    set_local_word(image, frame, local, (int16_t)(local_word(image, frame, local) + addend));
}

/* $fe6df8 — fm_build: the alert tree laid out for `lines` lines `line_length` long and `buttons` buttons
 * `button_length` wide (an icon beside them when `have_icon`): every object unlinked, the root sized, the icon, the
 * lines and the buttons placed and linked under it in turn, the buttons made SELECTABLE|EXIT and unselected, the last
 * one the tree's end. Sizes in cells; the root's height carries half a cell in pixels. */
void aes_fm_build(uint8_t *image, uint32_t tree, int16_t have_icon, int16_t lines, int16_t line_length,
                  int16_t buttons, int16_t button_length)
{
    uint16_t local[BUILD_RECTS * GRECT_WORDS];
    uint32_t frame = host_slot_claim(AES_FM_BUILD_RECTS, local);
    _Static_assert(sizeof local == HOST_SLOT_AES_FM_BUILD_RECTS_BYTES, "fm_build's four GRECTs and their host slot");
    uint32_t message = frame + BUILD_MESSAGE, button = frame + BUILD_BUTTON, icon = frame + BUILD_ICON;
    uint32_t alert = frame + BUILD_ALERT;
    uint16_t row = (uint16_t)(m68k_muls_w((uint16_t)button_length, (uint16_t)buttons)
                              + (uint16_t)((buttons - 1) * ALERT_BUTTON_GAP));
    int16_t width = aes_max((int16_t)row, line_length);
    int16_t object;

    aes_r_set(image, alert, 0, 0, (int16_t)(width + ALERT_BUTTON_GAP), aes_max(lines, ALERT_MIN_LINES));
    aes_r_set(image, message, pair_high(ALERT_LINES_AT), pair_low(ALERT_LINES_AT), line_length, ALERT_LINE_HEIGHT);
    if (have_icon) {
        aes_r_set(image, icon, pair_high(ALERT_ICON_AT), pair_low(ALERT_ICON_AT), ALERT_ICON_CELLS, ALERT_ICON_CELLS);
        add_local_word(image, alert, GRECT_W, ALERT_ICON_CELLS + ALERT_ICON_MARGIN);
        set_local_word(image, alert, GRECT_H, aes_max(local_word(image, alert, GRECT_H), ALERT_ICON_CELLS + ALERT_ICON_MARGIN));
        add_local_word(image, message, GRECT_X, ALERT_ICON_CELLS);
    }
    add_local_word(image, alert, GRECT_H, ALERT_BOX_FOOT);
    row = (uint16_t)(local_word(image, alert, GRECT_W) - (buttons - 1) * ALERT_BUTTON_GAP
                     - m68k_muls_w((uint16_t)button_length, (uint16_t)buttons));
    aes_r_set(image, button, (int16_t)((int16_t)row / HALF), (int16_t)(local_word(image, alert, GRECT_H) - ALERT_BUTTONS_ABOVE),
              button_length, ALERT_BUTTON_HEIGHT);
    add_local_word(image, alert, GRECT_H, -ALERT_FOOT_TRIM);
    add_local_word(image, alert, GRECT_H,
                   (int16_t)(uint16_t)((uint16_t)((int16_t)be16(image + AES_GL_HCHAR) / HALF) << ALERT_PIXEL_SHIFT));
    aes_ob_setxywh(image, tree, OB_ROOT, alert);
    /* lbcopy of six $ff bytes from $fefa0e: the three link words of each object none. */
    for (object = 0; object < ALERT_OBJECTS; object++) {
        set_object_word(image, tree, object, OB_NEXT, OB_NIL);
        set_object_word(image, tree, object, OB_HEAD, OB_NIL);
        set_object_word(image, tree, object, OB_TAIL, OB_NIL);
    }
    if (have_icon) {
        aes_ob_setxywh(image, tree, ALERT_ICON_OBJECT, icon);
        aes_ob_add(image, tree, OB_ROOT, ALERT_ICON_OBJECT);
    }
    for (object = 0; object < lines; object++) {
        aes_ob_setxywh(image, tree, (int16_t)(object + ALERT_FIRST_LINE), message);
        add_local_word(image, message, GRECT_Y, ALERT_LINE_HEIGHT);
        aes_ob_add(image, tree, OB_ROOT, (int16_t)(object + ALERT_FIRST_LINE));
    }
    for (object = 0; object < buttons; object++) {
        set_object_word(image, tree, (int16_t)(object + ALERT_FIRST_BUTTON), OB_FLAGS, ALERT_BUTTON_FLAGS);
        set_object_word(image, tree, (int16_t)(object + ALERT_FIRST_BUTTON), OB_STATE, 0);
        aes_ob_setxywh(image, tree, (int16_t)(object + ALERT_FIRST_BUTTON), button);
        add_local_word(image, button, GRECT_X, (int16_t)(button_length + ALERT_BUTTON_GAP));
        aes_ob_add(image, tree, OB_ROOT, (int16_t)(object + ALERT_FIRST_BUTTON));
    }
    set_object_word(image, tree, (int16_t)(buttons + ALERT_FIRST_BUTTON - 1), OB_FLAGS, ALERT_LAST_BUTTON_FLAGS);
    host_slot_release(AES_FM_BUILD_RECTS);
}

/* $fe7214 — find_obj: from `start`, FORWARD to the next EDITABLE object or BACKWARD to the one before it, or from the
 * root to the first DEFAULT (FMD_DEFLT) — any other `which` the first EDITABLE from the root. A walk by index that
 * stops at the tree's LASTOB object (or below the root); `start` when none is found. */
int16_t aes_find_obj(uint8_t *image, uint32_t tree, int16_t start, int16_t which)
{
    int16_t object = 0, step = 1;
    uint16_t wanted = OB_FLAG_EDITABLE;                /* ($fe7222 moveq #8) */

    if (which == FMD_FORWARD) {
        object = (int16_t)(start + step);
    } else if (which == FMD_BACKWARD) {
        step = -1;
        object = (int16_t)(start + step);
    } else if (which == FMD_DEFLT) {
        wanted = OB_FLAG_DEFAULT;                      /* ($fe7236 moveq #2) */
    }
    while (object >= 0) {
        uint16_t flags = (uint16_t)object_word(image, tree, object, OB_FLAGS);

        if (flags & wanted)
            return object;
        object = flags & OB_FLAG_LASTOB ? -1 : (int16_t)(object + step);
    }
    return start;
}

/* $fe727a — fm_inifld: the field fm_do starts in — `field`, or for 0 the first EDITABLE after the root. */
int16_t aes_fm_inifld(uint8_t *image, uint32_t tree, int16_t field)
{
    return field ? field : aes_find_obj(image, tree, OB_ROOT, FMD_FORWARD);
}

/* $fe7298 — fm_keybd: a key that moves between fields — the arrows and the tabs to the field after or before
 * `object`, Return and Enter to the default button — taken (*key_at cleared) and the object it reaches stored at
 * *next_at; a default button found is selected and drawn, and the form is done. Any other key goes on, untouched. */
int16_t aes_fm_keybd(uint8_t *image, uint32_t tree, int16_t object, uint32_t key_at, uint32_t next_at)
{
    int16_t direction;

    switch (bus_word(image, key_at)) {
    case FM_KEY_BACKTAB:
    case FM_KEY_UP:     direction = FMD_BACKWARD; break;
    case FM_KEY_TAB:
    case FM_KEY_DOWN:   direction = FMD_FORWARD; break;
    case FM_KEY_RETURN:
    case FM_KEY_ENTER:  object = OB_ROOT; direction = FMD_DEFLT; break;
    default:            return FM_KEYBD_GO_ON;
    }
    set_bus_word(image, key_at, 0);
    set_bus_word(image, next_at, (uint16_t)aes_find_obj(image, tree, object, direction));
    if (direction != FMD_DEFLT || !bus_word(image, next_at))
        return FM_KEYBD_GO_ON;
    aes_ob_change(image, tree, (int16_t)bus_word(image, next_at),
                  (int16_t)(object_word(image, tree, (int16_t)bus_word(image, next_at), OB_STATE) | OB_STATE_SELECTED),
                  OB_CHANGE_REDRAW);
    return FM_KEYBD_DONE;
}

/* $fe50ca — dq: the key at the queue's front taken off — the count one less, the front one on (round the ring) — and
 * answered, read after both stores. */
int16_t aes_dq(uint8_t *image, uint32_t queue)
{
    int16_t front;

    set_bus_word(image, queue + CQUEUE_COUNT, (uint16_t)(bus_word(image, queue + CQUEUE_COUNT) - 1));
    front = (int16_t)bus_word(image, queue + CQUEUE_FRONT);
    set_bus_word(image, queue + CQUEUE_FRONT, (uint16_t)(front + 1));
    if ((int16_t)bus_word(image, queue + CQUEUE_FRONT) == CQUEUE_ENTRIES)
        set_bus_word(image, queue + CQUEUE_FRONT, 0);
    /* `movea.w` then `adda.l a0,a0`: the index doubled as a longword. */
    return (int16_t)bus_word(image, queue + CQUEUE_KEYS + (uint32_t)((int32_t)front * (int32_t)sizeof(uint16_t)));
}

_Static_assert(CDA_KEY_COUNT == CDA_KEY_QUEUE + CQUEUE_COUNT, "the CDA's key count is its queue's");

/* $fe50f8 — fq: every key queued for the running process (gl_cda, re-read at each) taken off. */
void aes_fq(uint8_t *image)
{
    while (bus_word(image, bus_long(image, AES_GL_CDA) + CDA_KEY_COUNT))
        (void)aes_dq(image, bus_long(image, AES_GL_CDA) + CDA_KEY_QUEUE);
}
