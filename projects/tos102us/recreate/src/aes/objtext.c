/* objtext.c — the object library's text and state helpers (`aes/objtext.h`).
 *
 * The ROM reaches each object's field through OB_ADDR ($fed18e: A0 += tree + 24 * object, the field offset handed in
 * A0) — `object_address` here, the same signed-index sum, put on the bus by each access. A TEDINFO is reached through ob_spec as the
 * ROM reaches it: the pointer loaded once (`movea.l (a0),a0`), each field a displacement from it on the 24-bit bus.
 * The text copies are lstcpy's ($fecbe6, `aes/strings.h`), called as the ROM calls it: (destination, source).
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/objects.h"
#include "aes/objtext.h"
#include "aes/strings.h"

/* The TEDINFO `object`'s ob_spec names, as the ROM holds it: a longword, top byte and all. */
static inline uint32_t tedinfo_of(uint8_t *image, uint32_t tree, int16_t object)
{
    return bus_long(image, object_address(tree, object, OB_SPEC));
}

/* $fecf84 — fs_sset: `text` copied INTO the object's TEDINFO text, the text's address answered through `text_out`
 * and te_txtlen through `length_out` — in the ROM's order: the address stored FIRST, then te_ptext read again for the
 * copy, then te_txtlen read after the copy (so a copy running over the TEDINFO's own length word is read back). */
void aes_fs_sset(uint8_t *image, uint32_t tree, int16_t object, uint32_t text, uint32_t text_out, uint32_t length_out)
{
    uint32_t tedinfo = tedinfo_of(image, tree, object);

    set_bus_long(image, text_out, bus_long(image, tedinfo + TE_PTEXT));
    aes_lstcpy(image, bus_long(image, tedinfo + TE_PTEXT), text);
    set_bus_word(image, length_out, bus_word(image, tedinfo + TE_TXTLEN));
}

/* $fecfb2 — inf_sset: fs_sset with its two answers into the Alcyon frame's own locals, which only the stack sees —
 * so the copy is its whole effect. */
void aes_inf_sset(uint8_t *image, uint32_t tree, int16_t object, uint32_t text)
{
    aes_lstcpy(image, bus_long(image, tedinfo_of(image, tree, object) + TE_PTEXT), text);
}

/* $fecfd6 — fs_sget: the object's TEDINFO text copied OUT into `text`. */
void aes_fs_sget(uint8_t *image, uint32_t tree, int16_t object, uint32_t text)
{
    aes_lstcpy(image, text, bus_long(image, tedinfo_of(image, tree, object) + TE_PTEXT));
}

/* $fecfee — inf_fldset: the object's whole state word := `when_set` if `field & bits` is non-zero, else
 * `when_clear`. */
void aes_inf_fldset(uint8_t *image, uint32_t tree, int16_t object, int16_t field, int16_t bits, int16_t when_set,
                    int16_t when_clear)
{
    set_object_word(image, tree, object, OB_STATE, (field & bits) ? when_set : when_clear);
}

/* $fed010 — inf_gindex: the index, from `first`, of the first of `count` consecutive objects that is SELECTED, or -1.
 * The count is a `dbf` counter: a count of 0 walks 65,536 objects. The walk steps the ADDRESS (`adda.l #24`), each
 * state byte then put on the bus. */
int16_t aes_inf_gindex(uint8_t *image, uint32_t tree, int16_t first, int16_t count)
{
    uint32_t state = table_entry(tree, first, OB_BYTES) + OB_STATE + OB_WORD_LOW_BYTE;
    uint16_t last = (uint16_t)(count - 1), left = last;

    do {
        if (bus_byte(image, state) & 1u << OB_STATE_SELECTED_BIT)
            return (int16_t)(last - left);
        state += OB_BYTES;
    } while (left-- != 0);
    return OB_NIL;
}

/* $fed03a — inf_what: which of the OK button and the one after it is SELECTED — 1 for OK, 0 for the other, -1 for
 * neither — the selected one's state cleared. `cancel` is never read: the pair is `ok` and `ok + 1`. */
int16_t aes_inf_what(uint8_t *image, uint32_t tree, int16_t ok, int16_t cancel)
{
    int16_t field = aes_inf_gindex(image, tree, ok, INF_WHAT_BUTTONS);

    (void)cancel;
    if (field == OB_NIL)
        return OB_NIL;
    set_object_word(image, tree, (int16_t)(ok + field), OB_STATE, 0);
    return field == 0;
}
