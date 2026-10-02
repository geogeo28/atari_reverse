/* grwait.c — the box loops that wait on the mouse (`aes/grwait.h`): gr_stilldn and gr_watchbox, hand 68000 in the ROM,
 * ported over its own order. The wait is ev_multi, reached through the event door (`aes/evdoor.h`): the ROM's own event
 * layer on both shores, the C round it here.
 *
 * gr_stilldn's MOUSE RECTANGLE IS ITS OWN FRAME: the ROM pushes `pea 36(sp)` — the address of its arguments, the leave
 * flag and the rectangle, which are GEM's MOBLK word for word — and its answer words are the twelve bytes it reserved
 * below its return. Both are frame locals here, handed on by address (`host_slot.h` off target).
 *
 * gr_watchbox's RECTANGLE IS ITS SAVED D2/D3: it hands ob_actxywh the stack word its `movem` pushed D2 at, and restores
 * D4-D7/A5/A6 alone — the ROM's D2/D3 come back as they went in only because nothing of it changes them. A frame local
 * here. Its clip is gl_rscreen BY VALUE: the ROM reads gr_setup's `move.l #$98a4` immediate at $fe85b2 as data
 * (`test_aes_rom_data.py`, CODE_BYTES), the one address that immediate holds.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/evdoor.h"
#include "aes/gemgraf.h"
#include "aes/grwait.h"
#include "aes/gsxif.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"

/* ev_multi as gr_stilldn asks it ($fe8508..$fe8522): the button's rise or the mouse rectangle, no second rectangle, no
 * timer, no message. */
#define STILLDN_EVENTS        (EV_MU_BUTTON | EV_MU_M1)                                 /* ($fe851e move.w #6) */
#define STILLDN_RISE          EV_BUTTON_PARAMETER(1, EV_BUTTON_LEFT, EV_BUTTON_UP)    /* ($fe8510 move.l #$10100) */
#define NONE                  0                                                       /* ($fe850e/$fe8516/$fe8518 clr.l) */
#define REDRAW                1          /* ob_change's draw flag                ($fe84da moveq #1,d4)         */

uint16_t aes_gr_stilldn(uint8_t *image, int16_t leave, int16_t x, int16_t y, int16_t width, int16_t height)
{
    /* The MOBLK, in EV_MOBLK_LEAVE / EV_MOBLK_RECT's order: the flag, then GRECT_X..GRECT_H. */
    const uint16_t rectangle_local[EV_MOBLK_WORDS] = {(uint16_t)leave, (uint16_t)x, (uint16_t)y, (uint16_t)width,
                                                      (uint16_t)height};
    uint16_t answers_local[EV_MULTI_ANSWER_WORDS];
    _Static_assert(sizeof rectangle_local == HOST_SLOT_AES_GR_STILLDN_RECTANGLE_BYTES, "gr_stilldn's MOBLK, its slot");
    _Static_assert(sizeof answers_local == HOST_SLOT_AES_GR_STILLDN_ANSWERS_BYTES, "gr_stilldn's answers, their slot");
    uint32_t rectangle = host_slot_claim(AES_GR_STILLDN_RECTANGLE, rectangle_local);
    uint32_t answers = host_slot_claim(AES_GR_STILLDN_ANSWERS, answers_local);
    uint16_t events;

    host_slot_store_words(image, rectangle, rectangle_local, EV_MOBLK_WORDS);
    events = evdoor_ev_multi(image, STILLDN_EVENTS, rectangle, NONE, NONE, STILLDN_RISE, NONE, answers);
    host_slot_release(AES_GR_STILLDN_ANSWERS);
    host_slot_release(AES_GR_STILLDN_RECTANGLE);
    return events & EV_MU_BUTTON ? GR_RISEN : GR_STILL_DOWN;      /* ($fe8528 lsr.w #1; not.w; andi.w #1) */
}

/* The object drawn `in_state` and `out_state` in turn — `in` first — until the button rises: the answer is 1 if it rose
 * on an `in` (the mouse inside, waiting for it to leave), 0 on an `out`. */
uint16_t aes_gr_watchbox(uint8_t *image, uint32_t tree, int16_t object, int16_t in_state, int16_t out_state)
{
    uint16_t rect_local[GRECT_WORDS];
    _Static_assert(sizeof rect_local == HOST_SLOT_AES_GR_WATCHBOX_RECT_BYTES, "gr_watchbox's rectangle, its slot");
    uint32_t rect = host_slot_claim(AES_GR_WATCHBOX_RECT, rect_local);
    uint16_t leave = 0;                                                         /* ($fe84d8 moveq #0,d7) */

    aes_gsx_sclip(image, AES_GL_RSCREEN);
    aes_ob_actxywh(image, tree, object, rect);
    do {
        aes_ob_change(image, tree, object, leave ? out_state : in_state, REDRAW);
        leave ^= 1;                                                             /* ($fe84e8 eor.w d4,d7) */
    } while (aes_gr_stilldn(image, (int16_t)leave, (int16_t)bus_word(image, rect + GRECT_X),
                            (int16_t)bus_word(image, rect + GRECT_Y), (int16_t)bus_word(image, rect + GRECT_W),
                            (int16_t)bus_word(image, rect + GRECT_H)));
    host_slot_release(AES_GR_WATCHBOX_RECT);
    return leave;
}
