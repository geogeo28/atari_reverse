/* obdraw.c — just_draw's two callers (`aes/objdraw.h`): ob_draw, which draws a subtree by walking it with everyobj, just_draw
 * the routine, and ob_change, which sets one object's state and shows the change — inverted in place where only SELECTED
 * moved, else redrawn whole. Alcyon C in the ROM, ported over its own order.
 *
 * THE FRAMES ARE THE ROM's. ob_draw hands ob_offset the addresses of its two position words, ob_change hands ob_sst six of
 * its locals and ob_offset / ob_user its GRECT, so each set of locals lives in one slot laid out as the ROM's `link` lays
 * it, standing in through `host_slot.h` off target.
 *
 * WHAT EVERYOBJ IS HANDED is the one place host and target differ (`just_draw_routine`).
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/oblib.h"
#include "aes/obuser.h"

/* The routine ob_draw hands everyobj BY VALUE ($fea08c `move.l #$fe9a88,-(sp)`). On the host it is just_draw's ROM
 * address, as the ROM's: everyobj's call reaches `staged_call.h`'s hook, which a case binds to the C core. On target it
 * is the Alcyon entry linked beside this file (`obdraw.S`), which takes everyobj's ten-byte frame into the C core: the
 * ROM's just_draw run inside our build is what Tier 3's (V) rule refuses (`bench/tier3.py`, AES_OWN_SPANS). */
static inline uint32_t just_draw_routine(void)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    return AES_ROM_JUST_DRAW;
#else
    return (uint32_t)(uintptr_t)aes_just_draw_alcyon;
#endif
}

/* ---- ob_draw's frame (`link a6,#-8`): the two words ob_offset fills, y below x --------------------------------------- */
#define POSITION_WORDS        2
#define POSITION_Y            0          /* -8(a6) */
#define POSITION_X            2          /* -6(a6) */

/* ---- ob_change's frame (`link a6,#-20`), each local at its offset from A6 --------------------------------------------- */
#define CHANGE_FRAME_BYTES    20
#define CHANGE_FRAME_WORDS    (CHANGE_FRAME_BYTES / M68K_WORD_BYTES)
#define CHANGE_LOCAL(offset)  (CHANGE_FRAME_BYTES + (offset))
#define CHANGE_SPEC           CHANGE_LOCAL(-20)  /* long: ob_spec, or what an INDIRECT one names (ob_sst's)          */
#define CHANGE_STATE          CHANGE_LOCAL(-16)  /* word: the state BEFORE the change                               */
#define CHANGE_RECT           CHANGE_LOCAL(-14)  /* GRECT: the object on the screen (A5, $fea39e)                   */
#define CHANGE_THICKNESS      CHANGE_LOCAL(-6)   /* word: the border's thickness, made at least 0 ($fea40e)          */
#define CHANGE_TYPE           CHANGE_LOCAL(-4)   /* word                                                            */
#define CHANGE_FLAGS          CHANGE_LOCAL(-2)   /* word                                                            */
#define BORDER_SIDES          2          /* the inverted rectangle loses the border on both sides ($fea46c asl.w #1) */

/* $fea028 — ob_draw: `object` and everything below it, `depth` levels at most, each object by just_draw (everyobj's
 * walk, ending at `object`'s next — its sibling, or its parent — or, from the root, nowhere: -1). The walk starts at
 * the screen position of `object`'s parent (ob_offset), the root's at (0, 0) — one `clr.l` of both words. The cursor
 * is hidden round the walk. */
void aes_ob_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t depth)
{
    uint16_t position_local[POSITION_WORDS];
    _Static_assert(sizeof position_local == HOST_SLOT_AES_OB_DRAW_POSITION_BYTES, "ob_draw's position and its host slot");
    uint32_t position = host_slot_claim(AES_OB_DRAW_POSITION, position_local);
    int16_t last = object ? object_word(image, tree, object, OB_NEXT) : OB_NIL;
    int16_t parent = aes_get_par(image, tree, object);

    if (parent != OB_NIL)
        aes_ob_offset(image, tree, parent, position + POSITION_X, position + POSITION_Y);
    else
        wr32(image + position, 0);
    aes_gsx_moff(image);
    aes_everyobj(image, tree, object, last, just_draw_routine(), (int16_t)be16(image + position + POSITION_X),
                 (int16_t)be16(image + position + POSITION_Y), depth);
    aes_gsx_mon(image);
    host_slot_release(AES_OB_DRAW_POSITION);
}

/* $fea464 — SELECTED's change shown in place: the object inside its border XORed solid black. The corner moves in by
 * the border as ONE packed longword (`swap` / `add.l`: a y carrying past $ffff moves x), the size shrinks by it on
 * both sides as words. */
static void invert_inside_the_border(uint8_t *image, uint32_t frame)
{
    uint32_t rect = frame + CHANGE_RECT;
    int16_t thickness = local_word(image, frame, CHANGE_THICKNESS);
    uint32_t corner = packed_add(be32(image + rect + GRECT_X), words_long(thickness, thickness));

    aes_bb_fill(image, GSX_MODE_XOR, GSX_FIS_SOLID, GSX_PATTERN_SOLID, pair_high(corner), pair_low(corner),
                (int16_t)(be16(image + rect + GRECT_W) - BORDER_SIDES * thickness),
                (int16_t)(be16(image + rect + GRECT_H) - BORDER_SIDES * thickness));
}

/* The change, over the frame `aes_ob_change` holds. Nothing happens to an object already in `new_state` or with no spec
 * (-1); else its state is stored, and with `redraw` it is shown — the cursor hidden round it: a USERDEF by its own
 * routine (its answer unread), an ICON redrawn whole, any other object whose SELECTED bit moved inverted in place, and
 * the rest redrawn whole. */
static void change_object(uint8_t *image, uint32_t tree, int16_t object, int16_t new_state, int16_t redraw,
                          uint32_t frame)
{
    uint32_t rect = frame + CHANGE_RECT;
    int16_t type;

    aes_ob_sst(image, tree, object, frame + CHANGE_SPEC, frame + CHANGE_STATE, frame + CHANGE_TYPE, frame + CHANGE_FLAGS,
               rect, frame + CHANGE_THICKNESS);
    if (local_word(image, frame, CHANGE_STATE) == new_state || be32(image + frame + CHANGE_SPEC) == OB_SPEC_NONE)
        return;
    set_object_word(image, tree, object, OB_STATE, new_state);
    if (!redraw)
        return;
    aes_ob_offset(image, tree, object, rect + GRECT_X, rect + GRECT_Y);
    aes_gsx_moff(image);
    if (local_word(image, frame, CHANGE_THICKNESS) < 0)
        set_local_word(image, frame, CHANGE_THICKNESS, 0);
    type = local_word(image, frame, CHANGE_TYPE);
    if (type == G_USERDEF) {
        aes_ob_user(image, tree, object, rect, be32(image + frame + CHANGE_SPEC), local_word(image, frame, CHANGE_STATE),
                    new_state);
        redraw = 0;
    } else if (type != G_ICON && ((uint16_t)new_state ^ be16(image + frame + CHANGE_STATE)) & 1u << OB_STATE_SELECTED_BIT) {
        invert_inside_the_border(image, frame);
        redraw = 0;
    }
    if (redraw)
        aes_just_draw(image, tree, object, (int16_t)be16(image + rect + GRECT_X), (int16_t)be16(image + rect + GRECT_Y));
    aes_gsx_mon(image);
}

/* $fea38e — ob_change: `object`'s state made `new_state`, shown when `redraw` (a word) is non-zero. */
void aes_ob_change(uint8_t *image, uint32_t tree, int16_t object, int16_t new_state, int16_t redraw)
{
    uint16_t frame_local[CHANGE_FRAME_WORDS];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_OB_CHANGE_FRAME_BYTES, "ob_change's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_OB_CHANGE_FRAME, frame_local);

    change_object(image, tree, object, new_state, redraw, frame);
    host_slot_release(AES_OB_CHANGE_FRAME);
}
