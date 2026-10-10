/* oblib.c — the OBJECT-TREE walks: `get_par` (an object's parent) and `ob_offset` (its position on the screen).
 *
 * A Line-F call in the ROM is a `jsr` here and an Alcyon return is C's own (`aes/aes.h`, "LINE-F"): nothing of
 * either is observable but the handler's patched mask word, which the batteries drop by name. The object index is
 * a SIGNED word, indexed as the ROM does (`object_address`), so an index of -1 reads the object BELOW the tree.
 */
#include <stdint.h>

#include "recreate.h"
#include "machine.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "aes/objects.h"
#include "aes/oblib.h"

/* $fed382 — the parent of `object`: walk ob_next from it until reaching the object whose ob_tail is the one just
 * left (the LAST sibling's ob_next is the parent). The root has none: -1, without a read. No tree the AES builds
 * lacks a parent on that walk; a malformed one spins in the ROM and here alike. */
int16_t aes_get_par(uint8_t *image, uint32_t tree, int16_t object)
{
    int16_t left, parent = object;

    if (object == OB_ROOT)
        return OB_NIL;
    do {
        left = parent;
        parent = object_word(image, tree, left, OB_NEXT);
    } while (object_word(image, tree, parent, OB_TAIL) != left);
    return parent;
}

/* $fea584 — the screen position of `object`: its ob_x/ob_y summed with every ancestor's, the root's included,
 * into the caller's two words. BOTH ARE STORED THROUGH AT EVERY STEP, in the ROM's order — the y word cleared
 * first, then x; then per object its ob_x read and added into x, its ob_y read and added into y — which shows
 * when the words lie over each other or over the tree itself. The answer is the walk's last get_par, -1: the
 * desk's binding hands it on as its own ($fde280). */
int16_t aes_ob_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out)
{
    set_bus_word(image, y_out, 0);
    set_bus_word(image, x_out, 0);
    do {
        set_bus_word(image, x_out, (uint16_t)(bus_word(image, x_out) + (uint16_t)object_word(image, tree, object, OB_X)));
        set_bus_word(image, y_out, (uint16_t)(bus_word(image, y_out) + (uint16_t)object_word(image, tree, object, OB_Y)));
        object = aes_get_par(image, tree, object);
    } while (object != OB_NIL);
    return object;
}

/* ob_sst's border thickness is a signed BYTE held in a word: a word past 128 (a TEDINFO's te_thickness) wraps to its
 * byte's negative (`cmp.w #128 / ble / sub.w #256`, $fed266). */
#define THICKNESS_BYTE_MAX    128
#define THICKNESS_BYTE_RANGE  256

/* The border thickness of an object of `type`, from the spec and flags ALREADY STORED through the caller's
 * pointers — the ROM reads them back through `spec_out` and `flags_out`: a box's is the spec's second byte, a text
 * object's its TEDINFO's te_thickness, a button's -1 less one for EXIT and one for DEFAULT, a title's 1, and any
 * other type's 0. */
static int16_t border_thickness(uint8_t *image, int16_t type, uint32_t spec_out, uint32_t flags_out)
{
    uint8_t flags;
    int16_t thickness;

    switch (type) {
    case G_BOX:
    case G_IBOX:
    case G_BOXCHAR:
        return (int8_t)bus_byte(image, spec_out + 1);
    case G_TEXT:
    case G_BOXTEXT:
    case G_FTEXT:
    case G_FBOXTEXT:
        return (int16_t)bus_word(image, bus_long(image, spec_out) + TE_THICKNESS);
    case G_BUTTON:
        flags = bus_byte(image, flags_out + OB_WORD_LOW_BYTE);
        thickness = -1;
        if (flags & 1u << OB_FLAG_EXIT_BIT)
            thickness--;
        if (flags & 1u << OB_FLAG_DEFAULT_BIT)
            thickness--;
        return thickness;
    case G_TITLE:
        return 1;
    default:
        return 0;
    }
}

/* $fed19e — ob_sst: an object's fields out through its caller's pointers, for drawing — in the ROM's order: the
 * rectangle's w and h (x and y are not touched), ob_flags, ob_spec, ob_state, the type (ob_type's low byte); then,
 * for an INDIRECT object, the spec replaced by the longword ob_spec (read again from the object) points at; then
 * the border thickness, which reads the type, the spec and the flags BACK through the caller's pointers, wrapped to a
 * signed byte. The answer is the stored spec's FIRST byte, read back and sign-extended. */
int16_t aes_ob_sst(uint8_t *image, uint32_t tree, int16_t object, uint32_t spec_out, uint32_t state_out,
                   uint32_t type_out, uint32_t flags_out, uint32_t rect_out, uint32_t thickness_out)
{
    int16_t thickness;

    set_bus_word(image, rect_out + GRECT_W, (uint16_t)object_word(image, tree, object, OB_WIDTH));
    set_bus_word(image, rect_out + GRECT_H, (uint16_t)object_word(image, tree, object, OB_HEIGHT));
    set_bus_word(image, flags_out, (uint16_t)object_word(image, tree, object, OB_FLAGS));
    set_bus_long(image, spec_out, bus_long(image, object_address(tree, object, OB_SPEC)));
    set_bus_word(image, state_out, (uint16_t)object_word(image, tree, object, OB_STATE));
    set_bus_word(image, type_out, (uint16_t)object_word(image, tree, object, OB_TYPE) & OB_TYPE_MASK);
    if (bus_byte(image, flags_out) & 1u << OB_FLAG_INDIRECT_BIT)
        set_bus_long(image, spec_out, bus_long(image, bus_long(image, object_address(tree, object, OB_SPEC))));
    thickness = border_thickness(image, (int16_t)bus_word(image, type_out), spec_out, flags_out);
    if (thickness > THICKNESS_BYTE_MAX)
        thickness = (int16_t)(thickness - THICKNESS_BYTE_RANGE);
    set_bus_word(image, thickness_out, (uint16_t)thickness);
    return (int8_t)bus_byte(image, spec_out);
}

/* everyobj's two frame arrays: the x and the y of each level of the walk, 8 words each ($fed27c `link a6,#-32`);
 * level 0 is the caller's start position, and `first` is walked at level 1. */
#define EVERYOBJ_LEVELS       8
#define EVERYOBJ_FIRST_LEVEL  1

/* The halt both builds take on a level the arrays do not hold (oblib.c's everyobj says why). */
static inline RECREATE_NORETURN void everyobj_outside_the_frame(void)
{
    recreate_not_reconstructed("AES everyobj: a level outside its 8-word frame arrays — eight deep the ROM stores over "
                               "its saved A6 and x[0], above the first level it reads its own frame");
}

/* $fed27c — everyobj: a depth-first walk from `first` until the walk reaches `last`, calling `routine` (an Alcyon
 * routine, `call_alcyon_object`) with each object's screen position — the sum of `start_x`/`start_y` and the ob_x/
 * ob_y of every object from `first`'s level down. After each call the object is read AGAIN (the routine may change the
 * tree): the walk goes down to its first child unless it has none, is HIDETREE, or the walk is already `max_depth`
 * levels below `first`'s parent; else across to its next sibling, or — when that is its parent (the parent's tail is
 * the object just left) — up, until the walk comes back to `last` or to the root.
 *
 * THE LEVELS ARE THE ROM's FRAME: level `depth` (`first`'s is 1) is x[depth] and y[depth] of two 8-word arrays, so
 * a walk eight levels deep stores its x over the SAVED FRAME POINTER (x[8] is the `link`'s A6) and its y over x[0];
 * nine deep, x[9] over A6's low word and y[9] over x[1]; ten and deeper, over everyobj's own return address. That is
 * REACHABLE in TOS 1.02: objc_draw (opcode 42) hands the CALLER's depth straight on (ob_draw, $fea080), GEM programs
 * pass 8, and a user tree eight levels below `start` then corrupts the A6 ob_draw's Line-F return unlinks through.
 * The AES's own trees run four deep at most. The climb has no lower bound either: a tree whose object names its own
 * sibling as ob_tail climbs above `first`'s level, where the ROM reads x[-1] and y[-1] — y[7] and the saved D7, its
 * own frame. C has neither a saved A6 nor a D7 to reach, so BOTH BUILDS HALT on a level outside the arrays
 * (`recreate_not_reconstructed`, the arm not reproduced) rather than index past them — on target too, where the
 * store would otherwise be a silent write past `across[]`/`down[]` (undefined behaviour) instead of the ROM's into
 * its own frame. A DIVERGENCE (recreate/STATUS.md, "Not reconstructed"): the ROM goes on with a corrupted A6 or x[0],
 * the recreate stops; `test_aes_oblib_walk.py` pins both halts. Each bound is tested where the level MOVES that way
 * and only when a store at it follows — a descent onto `last` ends the walk, and a climb to level 0 may end it too
 * (from a `first` below the root, the last sibling's climb reaches the root's level and stops), neither storing. */
FRAME_DIET("no-tree-dominator-opts")
void aes_everyobj(uint8_t *image, uint32_t tree, int16_t first, int16_t last, uint32_t routine, int16_t start_x,
                  int16_t start_y, int16_t max_depth)
{
    int16_t across[EVERYOBJ_LEVELS], down[EVERYOBJ_LEVELS];
    int16_t object = first, depth = EVERYOBJ_FIRST_LEVEL, next;

    across[0] = start_x;
    down[0] = start_y;
    while (object != last) {
        across[depth] = (int16_t)(across[depth - 1] + object_word(image, tree, object, OB_X));
        down[depth] = (int16_t)(down[depth - 1] + object_word(image, tree, object, OB_Y));
        call_alcyon_object(image, routine, tree, object, across[depth], down[depth]);
        next = object_word(image, tree, object, OB_HEAD);
        if (next != OB_NIL && !(bus_byte(image, object_address(tree, object, OB_FLAGS + OB_WORD_LOW_BYTE))
                                & 1u << OB_FLAG_HIDETREE_BIT) && depth <= max_depth) {
            depth++;
            object = next;
            if (depth == EVERYOBJ_LEVELS && object != last)
                everyobj_outside_the_frame();
            continue;
        }
        for (;;) {
            next = object_word(image, tree, object, OB_NEXT);
            if (next == last || object == OB_ROOT)
                return;
            if (object_word(image, tree, next, OB_TAIL) != object)
                break;
            depth--;
            object = next;
        }
        if (depth < EVERYOBJ_FIRST_LEVEL)
            everyobj_outside_the_frame();
        object = next;
    }
}
