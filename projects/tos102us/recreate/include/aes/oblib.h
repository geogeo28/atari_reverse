/* aes/oblib.h — the OBJECT-TREE walks (`src/aes/oblib.c`): an object's parent, its screen position, its fields
 * read out for drawing (ob_sst), and the depth-first walk that calls a routine per object (everyobj).
 *
 * All ALCYON C, entered by a Line-F call over the frame their caller pushed — the tree a LONGWORD, the object
 * a WORD (an Alcyon `int`) — and those that answer, answer a word in D0, which is all their callers read (`tst.w
 * d0`, `move.w d0,…`); everyobj answers nothing.
 * The layout they walk is `aes/objects.h`'s.
 */
#ifndef TOS102US_AES_OBLIB_H
#define TOS102US_AES_OBLIB_H

#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "aes/objects.h"

int16_t aes_get_par(uint8_t *image, uint32_t tree, int16_t object);                                   /* $fed382 */
int16_t aes_ob_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out); /* $fea584 */
int16_t aes_ob_sst(uint8_t *image, uint32_t tree, int16_t object, uint32_t spec_out, uint32_t state_out,
                   uint32_t type_out, uint32_t flags_out, uint32_t rect_out, uint32_t thickness_out);  /* $fed19e */
void aes_everyobj(uint8_t *image, uint32_t tree, int16_t first, int16_t last, uint32_t routine, int16_t start_x,
                  int16_t start_y, int16_t max_depth);                                                  /* $fed27c */

/* ---- everyobj's walk, as a body its callers hold --------------------------------------------------------------------- */
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

/* What a walk does with each object: the object's tree, itself and its screen position, and the `routine` the walk
 * was handed (call_alcyon_object's own arguments — everyobj's visit — in its order). */
typedef void everyobj_visit(uint8_t *image, uint32_t routine, uint32_t tree, int16_t object, int16_t x, int16_t y);

/* THE WALK ITSELF (`src/aes/oblib.c`, everyobj, says what it walks and where both builds halt), each object handed
 * to `visit`. A BODY, NOT A ROUTINE: everyobj is it with the Alcyon call as the visit; ob_draw HOLDS IT AS ITS OWN
 * with just_draw called as C calls (`src/aes/obdraw.c` says what that takes off the stack under every object drawn). */
static inline __attribute__((always_inline)) void everyobj_walk(uint8_t *image, uint32_t tree, int16_t first, int16_t last,
                                                                uint32_t routine, int16_t start_x, int16_t start_y,
                                                                int16_t max_depth, everyobj_visit *visit)
{
    int16_t across[EVERYOBJ_LEVELS], down[EVERYOBJ_LEVELS];
    int16_t object = first, depth = EVERYOBJ_FIRST_LEVEL, next;

    across[0] = start_x;
    down[0] = start_y;
    while (object != last) {
        across[depth] = (int16_t)(across[depth - 1] + object_word(image, tree, object, OB_X));
        down[depth] = (int16_t)(down[depth - 1] + object_word(image, tree, object, OB_Y));
        visit(image, routine, tree, object, across[depth], down[depth]);
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

#endif /* TOS102US_AES_OBLIB_H */
