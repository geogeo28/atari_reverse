/* evlib.c — THE EVENT LIBRARY's single waits and appl_read / appl_write (`aes/evlib.h`): gemevlib's ev_block, ev_rets,
 * ev_mchk, ev_keybd, ev_button, ev_mouse, ev_mesag, ev_timer and ev_dclick, and gemaplib's ap_rdwr. Alcyon C in the
 * ROM, ported over its own order.
 *
 * ap_rdwr's QPB IS ITS OWN ARGUMENTS in the ROM — the process, the length and the buffer where its caller pushed
 * them, whose address it hands on. GCC's caller pushes each as a longword, so the C lays the three out as a QPB in a
 * local (on target) or its `host_slot.h` slot (off target, where the wait's routines reach it through the image).
 * A wait that PARKS keeps that address in its EVB until another process's read or write serves it THROUGH it — two
 * processes' QPBs are live at once, each on its own stack — so off target the slot is the RUNNING PROCESS's own.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evasync.h"
#include "aes/evdoor.h"
#include "aes/evlib.h"
#include "aes/evwait.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/pdpipe.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/wmupdate.h"

_Static_assert(HOST_SLOT_AES_AP_RDWR_QPB_BYTES == HOST_PROCESSES * AP_RDWR_QPB_BYTES && AP_RDWR_QPB_BYTES == QPB_BYTES,
               "ap_rdwr's arguments after its code are one QPB, and its host slot holds one per process");

/* The id of the RUNNING process: whose stack a frame of this call is on (`host_slot.h`, A SLOT PER PROCESS). An
 * INDEX, so unsigned — and read off target alone: the ROM's ap_rdwr never reads it (ev_mesag's push of the same word,
 * below, is a `move.w`: the signed word the C's parameter is). */
static inline uint32_t running_process_id(const uint8_t *image)
{
    return bus_word(image, running(image, PD_PID));
}

/* $fe6874 — ev_block: ONE wait of `code` over `parameter` queued (iasync), waited for (mwait: the dispatcher, unless
 * the wait was satisfied where it was queued) and answered (apret: its EVB freed). */
EVDOOR_TWIN
uint16_t aes_ev_block(uint8_t *image, int16_t code, uint32_t parameter)
{
    int16_t event = (int16_t)aes_iasync(image, code, parameter);

    (void)aes_ev_mwait(image, event);
    return (uint16_t)aes_apret(image, event);
}

/* $fe65c4 — ap_rdwr (appl_read, appl_write): ev_block(`code`, the QPB) — the QPB the three arguments after the code. */
EVDOOR_TWIN
uint16_t aes_ap_rdwr(uint8_t *image, int16_t code, int16_t process, int16_t length, uint32_t buffer)
{
    uint16_t qpb_local[FRAME_LOCAL_WORDS(AP_RDWR_QPB_BYTES)];
    uint32_t qpb = host_slot_claim_for(AES_AP_RDWR_QPB, qpb_local, running_process_id(image));
    uint16_t answer;

    wr16(image + qpb + QPB_PID, (uint16_t)process);
    wr16(image + qpb + QPB_COUNT, (uint16_t)length);
    wr32(image + qpb + QPB_BUFFER, buffer);
    answer = aes_ev_block(image, code, qpb);
    host_slot_release_for(AES_AP_RDWR_QPB, qpb);
    return answer;
}

/* $fe681a — ev_rets: the four answers of a wait through `answers`, the pointer taken through the bus for each. The
 * mouse is where the last change of the buttons was made when one was counted since the last ev_rets (the click's
 * own place: the mouse may have moved on) and where it is otherwise; the buttons are the high word of the last
 * answer apret took (AES_EV_BUTTON_STATE — a button wait's buttons, and whatever any OTHER kind of wait keeps
 * there); the shift keys as they are. The count of button changes is then cleared. */
void aes_ev_rets(uint8_t *image, uint32_t answers)
{
    if (be16(image + AES_MTRANS)) {
        set_bus_word(image, answers + EV_RETS_X, be16(image + AES_PR_XRAT));
        set_bus_word(image, answers + EV_RETS_Y, be16(image + AES_PR_YRAT));
    } else {
        set_bus_word(image, answers + EV_RETS_X, be16(image + AES_XRAT));
        set_bus_word(image, answers + EV_RETS_Y, be16(image + AES_YRAT));
    }
    set_bus_word(image, answers + EV_RETS_BUTTONS, be16(image + AES_EV_BUTTON_STATE));
    set_bus_word(image, answers + EV_RETS_SHIFT_KEYS, be16(image + AES_KSTATE));
    wr16(image + AES_MTRANS, 0);
}

/* $fe6894 — ev_keybd (evnt_keybd): a key waited for; the key. */
uint16_t aes_ev_keybd(uint8_t *image)
{
    return aes_ev_block(image, IASYNC_KEYBOARD, 0);
}

/* $fe68a4 — ev_button (evnt_button): the buttons waited for — the clicks in the parameter's high word, the mask
 * and the state a byte each of its low word, the state ORed in whole (a state above $ff reaches the mask) — then
 * the four answers; the clicks that came. */
EVDOOR_TWIN
uint16_t aes_ev_button(uint8_t *image, int16_t clicks, int16_t mask, int16_t state, uint32_t answers)
{
    uint16_t low = (uint16_t)((uint16_t)mask << BUTTON_PARM_MASK_SHIFT) | (uint16_t)state;
    uint16_t came = aes_ev_block(image, IASYNC_BUTTON, (uint32_t)(uint16_t)clicks << BUTTON_PARM_CLICKS_SHIFT | low);

    aes_ev_rets(image, answers);
    return came;
}

/* $fe68e4 — ev_mouse (evnt_mouse): the mouse waited for into or out of the MOBLK's rectangle, then the four
 * answers — and the buttons AS THEY ARE over the third: what ev_rets put there is the wait's own leftover (the
 * rectangle's width, of a wait that parked). */
uint16_t aes_ev_mouse(uint8_t *image, uint32_t moblk, uint32_t answers)
{
    uint16_t came = aes_ev_block(image, IASYNC_MOUSE, moblk);

    aes_ev_rets(image, answers);
    set_bus_word(image, answers + EV_RETS_BUTTONS, be16(image + AES_BUTTON));
    return came;
}

/* $fe6910 — ev_mesag (evnt_mesag): one message read from the running process's own pipe into `buffer`, the control
 * manager's "sent" mark cleared first. */
uint16_t aes_ev_mesag(uint8_t *image, uint32_t buffer)
{
    wr16(image + AES_CTL_MESSAGE_SENT, 0);
    return aes_ap_rdwr(image, IASYNC_READ, signed_field(image, be32(image + AES_RLR), PD_PID), AP_MSG_BYTES, buffer);
}

/* $fe6936 — ev_timer (evnt_timer): a delay of `milliseconds`, in ticks — the long divided by the tick's
 * milliseconds as a signed long (ldiv, which leaves its remainder in AES_LDIV_REMAINDER). */
uint16_t aes_ev_timer(uint8_t *image, int32_t milliseconds)
{
    return aes_ev_block(image, IASYNC_DELAY,
                        (uint32_t)aes_ldiv(image, milliseconds, (int16_t)be16(image + AES_GL_TICK_MS)));
}

/* $fe695c — ev_mchk: whether the mouse event of the MOBLK at `moblk` has come for the running process — it owns the
 * mouse, and the mouse being inside the rectangle, as a word, differs from the MOBLK's leave flag. */
uint16_t aes_ev_mchk(uint8_t *image, uint32_t moblk)
{
    if (be32(image + AES_RLR) != be32(image + AES_GL_MOWNER))
        return EV_MCHK_NOT_YET;
    if (aes_inside(image, global_word(image, AES_XRAT), global_word(image, AES_YRAT), moblk + EV_MOBLK_RECT)
        == signed_field(image, moblk, EV_MOBLK_LEAVE))
        return EV_MCHK_NOT_YET;
    return EV_MCHK_CAME;
}

/* $fe6c5e — ev_dclick (evnt_dclick): with `set`, the double-click rate stored and the ticks a click's count stays
 * open made from it — the ROM's table of milliseconds indexed by the rate AS STORED, a signed word doubled as an
 * address (a rate outside 0..4 reads the ROM round the table), divided by the tick's milliseconds (`divs.w`: the
 * quotient's word). Answers the rate, set or not. */
int16_t aes_ev_dclick(uint8_t *image, int16_t rate, int16_t set)
{
    if (set) {
        wr16(image + AES_GL_DCINDEX, (uint16_t)rate);
        wr16(image + AES_GL_DCLICK,
             (uint16_t)quotient_word(m68k_divs_w(
                 (uint32_t)(int32_t)signed_field(image, table_entry(AES_DCLICK_MS_TABLE, global_word(image, AES_GL_DCINDEX),
                                                                    sizeof(uint16_t)), 0),
                 be16(image + AES_GL_TICK_MS))));
    }
    return global_word(image, AES_GL_DCINDEX);
}
