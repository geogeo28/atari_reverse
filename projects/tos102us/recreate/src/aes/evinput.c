/* evinput.c — THE INPUT LAYER's posts (`aes/evinput.h`): geminput's nq, downorup, post_keybd, post_button, post_mouse,
 * inorout, mowner, set_mown, b_click and b_delay, and the control manager's ct_chgown. Alcyon C in the ROM, ported
 * over its own order.
 *
 * Every read is where the ROM makes it: a wait list is walked by the link read BEFORE its EVB is posted (evremove
 * takes the EVB off the list and azombie rewrites its link), a wait's parameter is read again after downorup, a
 * global the ROM reads again after a call is read again here; a count, an index or a coordinate is a SIGNED word
 * and the clicks post_button compares are UNSIGNED ones (`bls`). A pointer is carried as the 32 bits the ROM carries
 * and put on the 24-bit bus only where it is dereferenced.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/evasync.h"
#include "aes/evfork.h"
#include "aes/evinput.h"
#include "aes/fmlib.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/rect.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"

_Static_assert(HOST_SLOT_AES_INOROUT_RECT_BYTES == INOROUT_RECT_BYTES, "inorout's rectangle and its host slot");
_Static_assert(INOROUT_RECT_BYTES == GRECT_BYTES, "inorout's frame holds one GRECT");

/* $fe5092 — nq: a key at the rear of a CDA's key queue, unless the queue is full (dropped). The key is stored through
 * the rear BEFORE the rear is moved on, and the rear and the count are counted in memory after it. */
void aes_nq(uint8_t *image, int16_t key, uint32_t queue)
{
    if (signed_field(image, queue, CQUEUE_COUNT) >= CQUEUE_ENTRIES)
        return;
    /* `movea.w` then `adda.l a1,a1`: the rear doubled as a longword. */
    set_bus_word(image, queue + CQUEUE_KEYS
                        + (uint32_t)((int32_t)signed_field(image, queue, CQUEUE_REAR) * CQUEUE_KEY_BYTES),
                 (uint16_t)key);
    set_bus_word(image, queue + CQUEUE_REAR, (uint16_t)(bus_word(image, queue + CQUEUE_REAR) + 1));
    if (signed_field(image, queue, CQUEUE_REAR) == CQUEUE_ENTRIES)
        set_bus_word(image, queue + CQUEUE_REAR, 0);
    set_bus_word(image, queue + CQUEUE_COUNT, (uint16_t)(bus_word(image, queue + CQUEUE_COUNT) + 1));
}

/* $fe5292 — downorup: whether the buttons `buttons` satisfy a button wait's `parameter` — its masked buttons in the
 * state it names, or (its sense byte set) not in it. The sense byte is compared WHOLE with the 0 / 1 of the test: a
 * sense other than 0 or 1 is satisfied either way. */
int16_t aes_downorup(uint8_t *image, int16_t buttons, uint32_t parameter)
{
    uint16_t sense = (uint16_t)(parameter >> BUTTON_PARM_SENSE_SHIFT & BUTTON_PARM_BYTE);
    uint16_t mask = (uint16_t)(parameter >> BUTTON_PARM_MASK_SHIFT & BUTTON_PARM_BYTE);
    uint16_t state = (uint16_t)(parameter & BUTTON_PARM_BYTE);
    uint16_t in_state = !(mask & (state ^ (uint16_t)buttons));

    (void)image;
    return sense != in_state;
}

/* $fe51a2 — post_keybd: a key to the process `process` — to the first EVB waiting on its CDA's keyboard wait
 * (evremove: the key its answer), else into its key queue. */
void aes_post_keybd(uint8_t *image, uint32_t process, int16_t key)
{
    uint32_t cda = bus_long(image, process + PD_CDA);
    uint32_t waiting = bus_long(image, cda + CDA_KEYBOARD_WAIT);

    if (waiting)
        aes_evremove(image, waiting, key);
    else
        aes_nq(image, key, cda + CDA_KEY_QUEUE);
}

/* $fe52e2 — post_button: the buttons' state `button`, come after `clicks` clicks, to every button wait of `process`
 * it satisfies (downorup): the state its answer's high word, and the clicks — no more than the wait asked for,
 * compared as UNSIGNED words — ORed into the low by evremove. Each wait's link is read before the wait is posted. */
FRAME_DIET("no-move-loop-invariants")
EVDOOR_TWIN
void aes_post_button(uint8_t *image, uint32_t process, int16_t button, int16_t clicks)
{
    uint32_t cda = bus_long(image, process + PD_CDA);
    uint32_t evb = bus_long(image, cda + CDA_BUTTON_WAIT);

    while (evb) {
        uint32_t next = bus_long(image, evb + EVB_LINK);

        if (aes_downorup(image, button, bus_long(image, evb + EVB_PARM))) {
            uint16_t asked = (uint16_t)(bus_long(image, evb + EVB_PARM) >> BUTTON_PARM_CLICKS_SHIFT) & BUTTON_PARM_BYTE;

            set_bus_long(image, evb + EVB_RETURN, (uint32_t)(uint16_t)button << HIGH_WORD_SHIFT);
            aes_evremove(image, evb, (int16_t)((uint16_t)clicks <= asked ? (uint16_t)clicks : asked));
        }
        evb = next;
    }
}

/* $fe54b8 — inorout: whether the point (x, y) satisfies the mouse wait `evb` — inside its rectangle for a wait to
 * ENTER it, outside for one to LEAVE it (EVB_FLAG_LEAVE). The rectangle is unpacked from the EVB into the frame. */
int16_t aes_inorout(uint8_t *image, uint32_t evb, int16_t x, int16_t y)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(INOROUT_RECT_BYTES)];
    int16_t leaves = (bus_byte(image, evb + EVB_FLAG_LOW_BYTE) & EVB_FLAG_LEAVE) != 0;
    uint32_t rect = host_slot_claim(AES_INOROUT_RECT, frame_local);
    int16_t is_inside;

    wr16(image + rect + GRECT_X, (uint16_t)(bus_long(image, evb + EVB_PARM) >> HIGH_WORD_SHIFT));
    wr16(image + rect + GRECT_Y, (uint16_t)bus_long(image, evb + EVB_PARM));
    wr16(image + rect + GRECT_W, (uint16_t)(bus_long(image, evb + EVB_RETURN) >> HIGH_WORD_SHIFT));
    wr16(image + rect + GRECT_H, (uint16_t)bus_long(image, evb + EVB_RETURN));
    is_inside = aes_inside(image, x, y, rect);
    host_slot_release(AES_INOROUT_RECT);
    return is_inside != leaves;
}

/* $fe5480 — post_mouse: the mouse at (x, y), to every mouse wait of `process` it satisfies (inorout), each answered
 * 0. Each wait's link is read before the wait is tested. */
FRAME_DIET("no-function-cse")
void aes_post_mouse(uint8_t *image, uint32_t process, int16_t x, int16_t y)
{
    uint32_t cda = bus_long(image, process + PD_CDA);
    uint32_t evb = bus_long(image, cda + CDA_MOUSE_WAIT);

    while (evb) {
        uint32_t next = bus_long(image, evb + EVB_LINK);

        if (aes_inorout(image, evb, x, y))
            aes_evremove(image, evb, 0);
        evb = next;
    }
}

/* $fe4ef0 — mowner: whose a point is — the control rectangle's owner's, the screen manager's (the menu bar, or any
 * window wm_find answers but the desktop's 0), or the desktop's. */
FRAME_DIET("no-function-cse")
int16_t aes_mowner(uint8_t *image, int16_t x, int16_t y)
{
    if (aes_inside(image, x, y, AES_CTRL_RECT))
        return MOWNER_IN_CONTROL;
    if (aes_inside(image, x, y, AES_GL_RMENU))
        return MOWNER_SCREEN_MANAGER;
    return aes_wm_find(image, x, y) ? MOWNER_SCREEN_MANAGER : MOWNER_DESKTOP;
}

/* $fe504a — set_mown: the mouse given to `mouse_owner` — which is told where the mouse is and how the buttons are,
 * as events (its waits they satisfy are posted) — and the keyboard to `keyboard_owner`, stored last. */
void aes_set_mown(uint8_t *image, uint32_t mouse_owner, uint32_t keyboard_owner)
{
    wr32(image + AES_GL_MOWNER, mouse_owner);
    wr32(image + AES_GL_COWNER, mouse_owner);
    aes_post_mouse(image, be32(image + AES_GL_MOWNER), global_word(image, AES_XRAT), global_word(image, AES_YRAT));
    aes_post_button(image, be32(image + AES_GL_MOWNER), global_word(image, AES_BUTTON), SET_MOWN_CLICKS);
    wr32(image + AES_GL_KOWNER, keyboard_owner);
}

/* $fe49ba — ct_chgown: the control rectangle set to `rect`'s and the mouse and the keyboard both given to `owner`.
 * Its D0 is the end of post_button's walk under set_mown — a null link, on every path (`aes/evinput.h`). */
EVDOOR_TWIN
uint16_t aes_ct_chgown(uint8_t *image, uint32_t owner, uint32_t rect)
{
    aes_set_ctrl(image, rect);
    aes_set_mown(image, owner, owner);
    return 0;
}

/* $fe4f40 — b_click: the button interrupt's — the buttons are now `buttons`. Unchanged: nothing. While a click
 * count is open: a change back to the button it was opened on is one more click, and lengthens it; any other is
 * only noted. With none open: a press while a multi-click wait is pending opens one; anything else is queued for
 * forker as a button change of one click, at once. */
void aes_b_click(uint8_t *image, int16_t buttons)
{
    if (buttons == global_word(image, AES_GL_BDESIRED))
        return;
    if (be16(image + AES_GL_CLICK_TICKS)) {
        if (buttons == global_word(image, AES_GL_BTRUE)) {
            add_word_in_memory(image, AES_GL_BCLICK, 1);
            add_word_in_memory(image, AES_GL_CLICK_TICKS, CLICK_EXTENSION_TICKS);
        }
    } else if (be16(image + AES_GL_BPEND) && buttons) {
        wr16(image + AES_GL_BCLICK, FIRST_CLICK);
        wr16(image + AES_GL_BTRUE, (uint16_t)buttons);
        wr16(image + AES_GL_CLICK_TICKS, be16(image + AES_GL_DCLICK));
    } else {
        aes_forkq(image, fork_bchange(), words_long(buttons, FIRST_CLICK));
    }
    wr16(image + AES_GL_BDESIRED, (uint16_t)buttons);
}

/* $fe4fb0 — b_delay: an open click count counted down by `ticks`; run out EXACTLY (a count stepped past 0 goes on
 * counting, round the word), the button it was opened on is queued with the clicks counted — and, when the buttons
 * have changed since, that change after it as one click. Called by the tick AND, under mchange, by a process the
 * button interrupt can land in: the count is counted off in memory (`sub.w d0,$c6ca`), and the buttons queued second
 * are read AGAIN after the compare ($fe4ff6), as b_click may have stored them between. */
FRAME_DIET("no-caller-saves")
void aes_b_delay(uint8_t *image, int16_t ticks)
{
    if (!be16(image + AES_GL_CLICK_TICKS))
        return;
    sub_word_in_memory(image, AES_GL_CLICK_TICKS, (uint16_t)ticks);
    if (be16(image + AES_GL_CLICK_TICKS))
        return;
    aes_forkq(image, fork_bchange(), words_long(global_word(image, AES_GL_BTRUE), global_word(image, AES_GL_BCLICK)));
    if (be16(image + AES_GL_BTRUE) != be16(image + AES_GL_BDESIRED))
        aes_forkq(image, fork_bchange(), words_long((int16_t)word_read_again(image, AES_GL_BDESIRED), FIRST_CLICK));
}
