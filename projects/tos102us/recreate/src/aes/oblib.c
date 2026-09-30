/* oblib.c — the OBJECT-TREE walks: `get_par` (an object's parent) and `ob_offset` (its position on the screen).
 *
 * A Line-F call in the ROM is a `jsr` here and an Alcyon return is C's own (`aes/aes.h`, "LINE-F"): nothing of
 * either is observable but the handler's patched mask word, which the batteries drop by name. The object index is
 * a SIGNED word, indexed as the ROM does (`object_field`), so an index of -1 reads the object BELOW the tree.
 */
#include <stdint.h>

#include "machine.h"
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
    uint8_t *x_word = image + bus_dereference(x_out);
    uint8_t *y_word = image + bus_dereference(y_out);

    wr16(y_word, 0);
    wr16(x_word, 0);
    do {
        wr16(x_word, (uint16_t)(be16(x_word) + (uint16_t)object_word(image, tree, object, OB_X)));
        wr16(y_word, (uint16_t)(be16(y_word) + (uint16_t)object_word(image, tree, object, OB_Y)));
        object = aes_get_par(image, tree, object);
    } while (object != OB_NIL);
    return object;
}
