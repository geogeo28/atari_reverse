/* obuser.c — the object draw path's leaves (`aes/obuser.h`): ob_format, ob_user and the far_call it calls through.
 *
 * Alcyon C in the ROM, ported over its own order. ob_format reaches its three strings a BYTE at a time, as the ROM
 * does — the template just_draw hands it is AES_TMPLT, at an ODD address — each pointer put on the 24-bit bus per
 * access. ob_user's PARMBLK is a frame local whose address the routine is handed, standing in through `host_slot.h`
 * off target.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "aes/gemgraf.h"
#include "aes/objects.h"
#include "aes/obuser.h"
#include "aes/rect.h"
#include "aes/strings.h"

/* ob_format's walk direction: forwards from the strings' starts, or back from their last bytes (OB_FORMAT_RIGHT). */
#define FORWARDS              1
#define BACKWARDS             (-1)

/* Where a walk of `length` bytes from `start` stops: `muls.w` of the step by the length, then `ext.l` — the product
 * taken back to a WORD before it is added (`$fe99f8`), so a length of -32768 stepped backwards stays -32768. */
static uint32_t walk_end(uint32_t start, int16_t step, int16_t length)
{
    return start + (uint32_t)(int32_t)(int16_t)(step * length);
}

/* $fe99a4 — ob_format: the raw text merged into the template, into `out`. A raw text starting '@' is cleared first
 * (GEM's mark for an empty one); `out` is terminated at the template's length, both lengths taken before. Then per
 * template byte: a placeholder '_' takes the raw text's next byte — or stays '_' once the raw text runs out — and any
 * other byte is copied. OB_FORMAT_RIGHT walks all three from their last bytes back, so the raw text fills the
 * template's placeholders from the right. Every pointer step a WORD added to a longword (`adda.w`); the ends compared
 * as longwords. */
void aes_ob_format(uint8_t *image, int16_t just, uint32_t raw, uint32_t tmplt, uint32_t out)
{
    int16_t template_length, raw_length, step = FORWARDS;
    uint32_t template_end, raw_end;

    if (bus_byte(image, raw) == OB_FORMAT_EMPTY_MARK)
        set_bus_byte(image, raw, STRING_NUL);
    template_length = aes_strlen(image, tmplt);
    raw_length = aes_strlen(image, raw);
    set_bus_byte(image, out + (uint32_t)(int32_t)template_length, STRING_NUL);
    if (just == OB_FORMAT_RIGHT) {
        step = BACKWARDS;
        out += (uint32_t)(int32_t)template_length - 1;
        tmplt += (uint32_t)(int32_t)template_length - 1;
        raw += (uint32_t)(int32_t)raw_length - 1;
    }
    /* The ROM also stores `out`'s end (-4(a6)) and never reads it: a frame byte, not an output. */
    template_end = walk_end(tmplt, step, template_length);
    raw_end = walk_end(raw, step, raw_length);
    for (; tmplt != template_end; tmplt += (uint32_t)(int32_t)step, out += (uint32_t)(int32_t)step) {
        uint8_t character = bus_byte(image, tmplt);

        if (character != OB_FORMAT_PLACEHOLDER) {
            set_bus_byte(image, out, character);
        } else if (raw != raw_end) {
            set_bus_byte(image, out, bus_byte(image, raw));
            raw += (uint32_t)(int32_t)step;
        } else {
            set_bus_byte(image, out, OB_FORMAT_PLACEHOLDER);
        }
    }
}

/* $fddec6 — far_call: `jsr` to `code` over `parm` pushed (`staged_call.h`'s call_alcyon_pointer), the routine's D0
 * answered whole. The 68000 jumps through 24 address lines, so a code pointer with a top byte reaches the routine
 * below it. */
uint32_t aes_far_call(uint8_t *image, uint32_t code, uint32_t parm)
{
    return call_alcyon_pointer(image, bus_dereference(code), parm);
}

/* $fe9a46 — ob_user: the PARMBLK built in the frame — the tree, the object, the two states as ONE longword, the
 * object's GRECT (rc_copy), the clip (gsx_gclip), the USERBLK's parameter — and the USERBLK's routine called over its
 * address through far_call, both USERBLK longwords read after the copies. Answers the routine's D0 whole. */
uint32_t aes_ob_user(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect, uint32_t userblk, int16_t curr,
                     int16_t new_state)
{
    uint16_t parmblk_local[PARM_BYTES / M68K_WORD_BYTES];
    _Static_assert(sizeof parmblk_local == HOST_SLOT_AES_OB_USER_PARMBLK_BYTES, "the PARMBLK and its host slot");
    uint32_t parmblk = host_slot_claim(AES_OB_USER_PARMBLK, parmblk_local);
    uint32_t answer;

    wr32(image + parmblk + PARM_TREE, tree);
    wr16(image + parmblk + PARM_OBJECT, (uint16_t)object);
    wr32(image + parmblk + PARM_PREVSTATE, words_long(curr, new_state));
    aes_rc_copy(image, rect, parmblk + PARM_RECT);
    aes_gsx_gclip(image, parmblk + PARM_CLIP);
    wr32(image + parmblk + PARM_PARM, bus_long(image, userblk + UB_PARM));
    answer = aes_far_call(image, bus_long(image, userblk + UB_CODE), parmblk);
    host_slot_release(AES_OB_USER_PARMBLK);
    return answer;
}
