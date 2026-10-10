/* objects.c — the OBJECT-TREE operations (`aes/objops.h`): ob_find, ob_add, ob_delete, ob_order, ob_center, and the
 * object library's helpers they share (ob_fs, ob_actxywh, ob_relxywh, ob_setxywh, get_prev).
 *
 * Alcyon C in the ROM, ported over its own ORDER: every link is read where the ROM reads it and stored where it
 * stores it, because a later read can see an earlier store (ob_order reads the links ob_delete just rewrote) and a
 * caller's GRECT or word can lie over the tree it describes. A Line-F call is a `jsr` here (`aes/aes.h`, "LINE-F").
 * Every object index is a SIGNED word (`object_address`), every pointer a caller hands in is put on the 24-bit bus.
 */
#include <stdint.h>

#include "machine.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "aes/aes.h"
#include "aes/objects.h"
#include "aes/oblib.h"
#include "aes/objops.h"
#include "aes/rect.h"
#include "aes/strings.h"

#define GRECT_WORDS           (GRECT_BYTES / M68K_WORD_BYTES)
#define ORDER_FIRST           0          /* ob_order's new position: its parent's head ($fea30a tst.w)         */
#define ORDER_LAST            (-1)       /* ...its parent's tail                ($fea31e cmpi.w #-1)           */
#define OUTLINE_BORDER        3          /* ob_center's outline: at most 3 pixels left and up ($fe931c)        */
#define OUTLINE_GROWTH        6          /* ...and 3 on each side wider and taller ($fe9338 addq.w #6)         */
#define OB_FIND_ORIGIN        0          /* ob_find's two GRECTs in their host slot: the origin, then...       */
#define OB_FIND_RECT          GRECT_BYTES  /* ...the object's rectangle on the screen                           */

static inline int flag_bit(int16_t word, unsigned bit)
{
    return (word >> bit) & 1;
}

/* $fea4b6 — the object's flags stored into the caller's word, then its state read and answered: a word laid over the
 * state answers the flags. */
int16_t aes_ob_fs(uint8_t *image, uint32_t tree, int16_t object, uint32_t flags_out)
{
    set_bus_word(image, flags_out, (uint16_t)object_word(image, tree, object, OB_FLAGS));
    return object_word(image, tree, object, OB_STATE);
}

/* $fea4e8 — the object's GRECT on the screen: ob_offset stores x and y through, then the width is read and stored,
 * then the height — each read AFTER the stores before it. */
void aes_ob_actxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect)
{
    aes_ob_offset(image, tree, object, rect + GRECT_X, rect + GRECT_Y);
    set_bus_word(image, rect + GRECT_W, (uint16_t)object_word(image, tree, object, OB_WIDTH));
    set_bus_word(image, rect + GRECT_H, (uint16_t)object_word(image, tree, object, OB_HEIGHT));
}

/* $fea538 — the object's GRECT as it stands (relative to its parent), copied out word by word FORWARD (wcopy): a
 * GRECT one word above the object's ob_x repeats that word. */
void aes_ob_relxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect)
{
    aes_wcopy(image, rect, object_address(tree, object, OB_X), GRECT_WORDS);
}

/* $fea55e — ...and copied in. */
void aes_ob_setxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect)
{
    aes_wcopy(image, object_address(tree, object, OB_X), rect, GRECT_WORDS);
}

/* $fea5dc — the sibling whose ob_next is `object`, walked from `parent`'s head; -1 when `object` IS the head. The
 * walk has no other end: an object that is not among the children spins in the ROM and here alike. */
int16_t aes_get_prev(uint8_t *image, uint32_t tree, int16_t parent, int16_t object)
{
    int16_t sibling = object_word(image, tree, parent, OB_HEAD), following;

    if (sibling == object)
        return OB_NIL;
    while ((following = object_word(image, tree, sibling, OB_NEXT)) != object)
        sibling = following;
    return sibling;
}

/* $fea0a8 — the deepest object under (x, y), searched from `object` down at most `depth` levels (a negative depth is
 * as good as none: it counts down through the word): -1 when `object` itself is missed. An object is hit when the
 * point is inside its rectangle and it is not HIDETREE; a hit with children goes on to them, LAST first (the one
 * drawn on top), and a miss among them steps back to the previous sibling until the head is passed.
 *
 * The two GRECTs are frame locals the ROM hands its helpers by address — the origin its children are placed from,
 * and each candidate's rectangle — so off target they are a host slot. The step back needs BOTH halves of the ROM's
 * test ($fea17c `tst.w`, $fea182 `cmpi.w #-1`): a descent, and a found object that is not -1 — a start at object -1
 * (objc_find's `startob` is the caller's word, and object -1 of a resource's later tree is a real object) hits,
 * descends, and a miss then ENDS the search with -1 rather than stepping among -1's children. */
FRAME_DIET("no-defer-pop", "no-gcse", "no-move-loop-invariants")
int16_t aes_ob_find(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t x, int16_t y)
{
    uint8_t rects_local[2 * GRECT_BYTES];
    uint32_t rects = host_slot_claim(AES_OB_FIND_RECTS, rects_local);
    uint32_t origin = rects + OB_FIND_ORIGIN, rect = rects + OB_FIND_RECT;
    uint16_t levels_left = (uint16_t)depth;
    int16_t found = OB_NIL, child, flags;
    int descended = 0;

    if (object == OB_ROOT)
        aes_r_set(image, origin, 0, 0, 0, 0);
    else
        aes_ob_actxywh(image, tree, aes_get_par(image, tree, object), origin);
    for (;;) {
        aes_ob_relxywh(image, tree, object, rect);
        set_bus_word(image, rect + GRECT_X, (uint16_t)(bus_word(image, rect + GRECT_X) + bus_word(image, origin + GRECT_X)));
        set_bus_word(image, rect + GRECT_Y, (uint16_t)(bus_word(image, rect + GRECT_Y) + bus_word(image, origin + GRECT_Y)));
        flags = object_word(image, tree, object, OB_FLAGS);
        if (aes_inside(image, x, y, rect) && !flag_bit(flags, OB_FLAG_HIDETREE_BIT)) {
            found = object;
            child = object_word(image, tree, object, OB_TAIL);
            if (child == OB_NIL || !levels_left)
                break;
            object = child;
            levels_left--;
            set_bus_word(image, origin + GRECT_X, bus_word(image, rect + GRECT_X));
            set_bus_word(image, origin + GRECT_Y, bus_word(image, rect + GRECT_Y));
            descended = 1;
        } else {
            if (!descended || found == OB_NIL)
                break;
            object = aes_get_prev(image, tree, found, object);
            if (object == OB_NIL)
                break;
        }
    }
    host_slot_release(AES_OB_FIND_RECTS);
    return found;
}

/* $fea1ba — `child` linked in as `parent`'s LAST child: its ob_next the parent, then the old tail's ob_next (or the
 * parent's head, when it had none) and the parent's tail it. Nothing is done when either is -1. */
void aes_ob_add(uint8_t *image, uint32_t tree, int16_t parent, int16_t child)
{
    int16_t last;

    if (parent == OB_NIL || child == OB_NIL)
        return;
    set_object_word(image, tree, child, OB_NEXT, parent);
    last = object_word(image, tree, parent, OB_TAIL);
    if (last == OB_NIL)
        set_object_word(image, tree, parent, OB_HEAD, child);
    else
        set_object_word(image, tree, last, OB_NEXT, child);
    set_object_word(image, tree, parent, OB_TAIL, child);
}

/* $fea21e — `object` unlinked from its parent's children (the root never): the head moves on to its next sibling —
 * -1 with the tail when it was the only child — or its previous sibling takes its ob_next, and the tail when it was
 * the last. Its own ob_next, read before the parent is found, is left as it was. */
void aes_ob_delete(uint8_t *image, uint32_t tree, int16_t object)
{
    int16_t following, parent, previous;

    if (object == OB_ROOT)
        return;
    following = object_word(image, tree, object, OB_NEXT);
    parent = aes_get_par(image, tree, object);
    if (object_word(image, tree, parent, OB_HEAD) == object) {
        if (object_word(image, tree, parent, OB_TAIL) == object) {
            following = OB_NIL;
            set_object_word(image, tree, parent, OB_TAIL, OB_NIL);
        }
        set_object_word(image, tree, parent, OB_HEAD, following);
        return;
    }
    previous = aes_get_prev(image, tree, parent, object);
    set_object_word(image, tree, previous, OB_NEXT, following);
    if (object_word(image, tree, parent, OB_TAIL) == object)
        set_object_word(image, tree, parent, OB_TAIL, previous);
}

/* $fea2be — `object` unlinked (ob_delete) and linked back in at `position` among its siblings: 0 the head, -1 after
 * the tail, n after the n-th — the walk counts ob_next links from the head, so a position past the end walks on
 * through the parent. The parent's links are read AFTER the unlink rewrote them, and the tail is set to `object`
 * only when its new ob_next is the parent: so an only child ordered to the head is left with no tail. */
void aes_ob_order(uint8_t *image, uint32_t tree, int16_t object, int16_t position)
{
    int16_t parent, before, step;

    if (object == OB_ROOT)
        return;
    parent = aes_get_par(image, tree, object);
    aes_ob_delete(image, tree, object);
    before = object_word(image, tree, parent, OB_HEAD);
    if (position == ORDER_FIRST) {
        set_object_word(image, tree, object, OB_NEXT, before);
        set_object_word(image, tree, parent, OB_HEAD, object);
    } else {
        if (position == ORDER_LAST)
            before = object_word(image, tree, parent, OB_TAIL);
        else
            for (step = 1; step < position; step++)
                before = object_word(image, tree, before, OB_NEXT);
        set_object_word(image, tree, object, OB_NEXT, object_word(image, tree, before, OB_NEXT));
        set_object_word(image, tree, before, OB_NEXT, object);
    }
    if (object_word(image, tree, object, OB_NEXT) == parent)
        set_object_word(image, tree, parent, OB_TAIL, object);
}

/* $fe92ae — form_center: the tree's root placed in the middle of the screen below the menu bar, x on a character
 * cell (both halves by `divs`, toward zero), stored into the root; then, for an OUTLINED root, the GRECT answered
 * grown by the outline (the origin never below 0). The root's size is read before its position is stored. A zero
 * cell width is the 68000's zero-divide trap, which the host refuses (`m68k_divs_w`). */
void aes_ob_center(uint8_t *image, uint32_t tree, uint32_t rect)
{
    int16_t width = object_word(image, tree, OB_ROOT, OB_WIDTH), height = object_word(image, tree, OB_ROOT, OB_HEIGHT);
    int16_t cell = (int16_t)be16(image + AES_GL_WCHAR), bar = (int16_t)be16(image + AES_GL_HBOX);
    int16_t x = (int16_t)((int16_t)be16(image + AES_GL_WIDTH) - width) / 2;
    int16_t y = (int16_t)((int16_t)((int16_t)be16(image + AES_GL_HEIGHT) - bar) - height) / 2;

    x = (int16_t)m68k_muls_w((uint16_t)quotient_word(m68k_divs_w((uint32_t)(int32_t)x, (uint16_t)cell)), (uint16_t)cell);
    y = (int16_t)(y + bar);
    set_object_word(image, tree, OB_ROOT, OB_X, x);
    set_object_word(image, tree, OB_ROOT, OB_Y, y);
    if (flag_bit(object_word(image, tree, OB_ROOT, OB_STATE), OB_STATE_OUTLINED_BIT)) {
        x = (int16_t)(x - (x < OUTLINE_BORDER ? x : OUTLINE_BORDER));
        y = (int16_t)(y - (y < OUTLINE_BORDER ? y : OUTLINE_BORDER));
        width = (int16_t)(width + OUTLINE_GROWTH);
        height = (int16_t)(height + OUTLINE_GROWTH);
    }
    aes_r_set(image, rect, x, y, width, height);
}
