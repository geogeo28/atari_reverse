/* deskbind.c — THE DESK'S AES BINDINGS (`desk/deskbind.h`): `$fddde6..$fde4ff`, and desk_wait `$fe1bdc`. Alcyon C in
 * the ROM, ported over its own order: each binding the implementation's call, the yield every AES call ends on, and the
 * implementation's answer.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/evdoor.h"
#include "aes/evlib.h"
#include "aes/fmdo.h"
#include "aes/gemgraf.h"
#include "aes/geminit.h"
#include "aes/gemsuper.h"
#include "aes/grdrag.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/obedit.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/oblib.h"
#include "aes/resource.h"
#include "aes/shell_buf.h"
#include "aes/switch.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskbind.h"

/* A rectangle's four words laid in the bindings' frame at `rect`, as the ROM's caller pushed them. */
static inline void lay_rect(uint8_t *image, uint32_t rect, int16_t x, int16_t y, int16_t w, int16_t h)
{
    wr16(image + rect + GRECT_X, (uint16_t)x);
    wr16(image + rect + GRECT_Y, (uint16_t)y);
    wr16(image + rect + GRECT_W, (uint16_t)w);
    wr16(image + rect + GRECT_H, (uint16_t)h);
}

/* A mouse rectangle's five words: whether leaving it is the event, then the rectangle. */
static inline void lay_moblk(uint8_t *image, uint32_t moblk, int16_t leave, int16_t x, int16_t y, int16_t w, int16_t h)
{
    wr16(image + moblk + EV_MOBLK_LEAVE, (uint16_t)leave);
    lay_rect(image, moblk + EV_MOBLK_RECT, x, y, w, h);
}

/* Answer word `index` of the bindings' frame stored through the caller's own pointer `out`. */
static inline void answer_out(uint8_t *image, uint32_t out, uint32_t answers, uint32_t index)
{
    set_bus_word(image, out, be16(image + answers + index * M68K_WORD_BYTES));
}

/* THE ONE FRAME'S SIZE IS ITS HOST SLOT'S (`host_slot.h`): two numbers, held equal where both are in sight. */
_Static_assert(BIND_FRAME_BYTES == HOST_SLOT_AES_DESK_BIND_FRAME_BYTES, "the bindings' frame and its host slot");

/* ...the first four of them, through four pointers: a point and two words, or a rectangle. */
static inline void four_answers_out(uint8_t *image, uint32_t answers, uint32_t first_out, uint32_t second_out,
                                    uint32_t third_out, uint32_t fourth_out)
{
    answer_out(image, first_out, answers, 0);
    answer_out(image, second_out, answers, 1);
    answer_out(image, third_out, answers, 2);
    answer_out(image, fourth_out, answers, 3);
}

/* THE YIELD every binding ends on — `dsptch()`, what the AES's trap would have done on its way out — A CALL AND NEVER
 * A JUMP. The ROM's binding gets control back from the dispatcher and returns by its own Line-F word. A C binding of
 * no answer would end in GCC's sibling call, a tail `jmp` into the switch, which then holds the binding's CALLER's
 * return address: the PC the process is resumed at would be no instruction of this routine's — for a row entered at
 * the binding, the run's sentinel (`transcribed.h`, EVDOOR_A_CALL_NOT_A_JUMP: the same statement, for a twin's call). */
static inline void yield(uint8_t *image)
{
    aes_dsptch(image);
    EVDOOR_A_CALL_NOT_A_JUMP;
}

/* ================================================================================================
 * THE TWO THAT YIELD NOTHING: the desk's process made known, and its two drive words kept.
 * ============================================================================================= */

/* $fddde6 — appl_init: the desk's own global[] filled in — its head ONE longword, the version and the count the other
 * way round from the AES's own appl_init (`desk/deskbind.h`) — and gl_apid kept. */
int16_t aes_desk_appl_init(uint8_t *image)
{
    wr32(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_VERSION, DESK_GLOBAL_HEAD);
    wr16(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_ID, be16(image + running(image, PD_PID)));
    wr16(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_NPLANES, be16(image + AES_GL_NPLANES));
    wr32(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_THEGLO, AES_THEGLO);
    wr16(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_BVDISK, be16(image + AES_GL_BVDISK));
    wr16(image + AES_DESK_APP_GLOBAL + AES_GLOBAL_BVHARD, be16(image + AES_GL_BVHARD));
    wr16(image + AES_GL_APID, be16(image + running(image, PD_PID)));
    return DESK_BIND_DONE;
}

/* $fdde54 — appl_bvset: the two drive bit vectors every later appl_init hands a program. */
int16_t aes_desk_appl_bvset(uint8_t *image, int16_t disks, int16_t hard_disks)
{
    wr16(image + AES_GL_BVDISK, (uint16_t)disks);
    wr16(image + AES_GL_BVHARD, (uint16_t)hard_disks);
    return DESK_BIND_DONE;
}

/* ================================================================================================
 * THE BINDINGS, in the ROM's order.
 * ============================================================================================= */

/* $fdde6c — appl_exit: the accessories told to close, whatever the desk's pipe still holds read away, every process
 * run. No yield of its own: all_run's is the last thing it does. */
int16_t aes_desk_appl_exit(uint8_t *image)
{
    aes_mn_clsda(image);
    if (be16(image + running(image, PD_QUEUE_INDEX)))
        (void)evdoor_ap_rdwr(image, AP_RDWR_READ, (int16_t)be16(image + running(image, PD_PID)),
                             (int16_t)be16(image + running(image, PD_QUEUE_INDEX)), AES_VALSTR);
    aes_all_run(image);
    return DESK_BIND_DONE;
}

/* $fddea6 — appl_write. */
uint16_t aes_desk_appl_write(uint8_t *image, int16_t process, int16_t length, uint32_t message)
{
    uint16_t written = evdoor_ap_rdwr(image, AP_RDWR_WRITE, process, length, message);

    yield(image);
    return written;
}

/* $fdded8 — evnt_multi: the clicks, mask and state packed into ev_multi's one button longword (the mask ADDED to the
 * state, `add.w`), the timer's two words made one — always, whatever the flags —, the two mouse rectangles handed in
 * place, and the six answers copied out through the caller's six pointers AFTER the yield. */
uint16_t aes_desk_evnt_multi(uint8_t *image, int16_t flags, int16_t clicks, int16_t mask, int16_t state,
                             int16_t leave1, int16_t x1, int16_t y1, int16_t w1, int16_t h1,
                             int16_t leave2, int16_t x2, int16_t y2, int16_t w2, int16_t h2,
                             uint32_t message, int16_t timer_low, int16_t timer_high,
                             uint32_t mouse_x_out, uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out,
                             uint32_t key_out, uint32_t clicks_out)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(BIND_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_BIND_FRAME, frame_local);
    uint32_t button = words_long(clicks, (int16_t)(uint16_t)(((uint16_t)mask << BUTTON_PARM_MASK_SHIFT) + (uint16_t)state));
    uint32_t timer = words_long(timer_high, timer_low);
    uint16_t events;

    lay_moblk(image, frame + BIND_MULTI_MOUSE1, leave1, x1, y1, w1, h1);
    lay_moblk(image, frame + BIND_MULTI_MOUSE2, leave2, x2, y2, w2, h2);
    events = evdoor_ev_multi(image, flags, frame + BIND_MULTI_MOUSE1, frame + BIND_MULTI_MOUSE2, timer, button, message,
                             frame + BIND_ANSWERS);
    yield(image);
    four_answers_out(image, frame + BIND_ANSWERS, mouse_x_out, mouse_y_out, buttons_out, keys_out);
    answer_out(image, key_out, frame + BIND_ANSWERS, BIND_MULTI_ANSWER_KEY);
    answer_out(image, clicks_out, frame + BIND_ANSWERS, BIND_MULTI_ANSWER_CLICKS);
    host_slot_release(AES_DESK_BIND_FRAME);
    return events;
}

/* $fddf82 — evnt_button: its four answers copied out after the yield. */
uint16_t aes_desk_evnt_button(uint8_t *image, int16_t clicks, int16_t mask, int16_t state, uint32_t mouse_x_out,
                              uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out)
{
    uint16_t answers_local[EV_BUTTON_ANSWER_WORDS];
    uint32_t answers = host_slot_claim(AES_DESK_BIND_FRAME, answers_local);
    uint16_t clicked = evdoor_ev_button(image, clicks, mask, state, answers + BIND_ANSWERS);

    yield(image);
    four_answers_out(image, answers + BIND_ANSWERS, mouse_x_out, mouse_y_out, buttons_out, keys_out);
    host_slot_release(AES_DESK_BIND_FRAME);
    return clicked;
}

/* $fddfc2 — evnt_dclick. */
int16_t aes_desk_evnt_dclick(uint8_t *image, int16_t rate, int16_t set)
{
    int16_t speed = aes_ev_dclick(image, rate, set);

    yield(image);
    return speed;
}

/* $fe1bdc — desk_wait: the cursor the hourglass while the desk is `busy`, the arrow again. */
void aes_desk_wait(uint8_t *image, int16_t busy)
{
    aes_desk_graf_mouse(image, busy ? DESK_CURSOR_HOURGLASS : DESK_CURSOR_ARROW, DESK_NO_FORM);
}

/* $fddfda — form_do: the arrow first (desk_wait(0): a yield of its own), then the dialog. */
int16_t aes_desk_form_do(uint8_t *image, uint32_t tree, int16_t start)
{
    int16_t exit_object;

    aes_desk_wait(image, 0);
    exit_object = aes_fm_do(image, tree, start);
    yield(image);
    return exit_object;
}

/* $fddffa — form_dial: the two rectangles handed by the address of the caller's own words. */
uint16_t aes_desk_form_dial(uint8_t *image, int16_t type, int16_t little_x, int16_t little_y, int16_t little_w,
                            int16_t little_h, int16_t big_x, int16_t big_y, int16_t big_w, int16_t big_h)
{
    uint16_t rects_local[FRAME_LOCAL_WORDS(BIND_RECT_PAIR_BYTES)];
    uint32_t rects = host_slot_claim(AES_DESK_BIND_FRAME, rects_local);
    uint16_t done;

    lay_rect(image, rects + BIND_FIRST_RECT, little_x, little_y, little_w, little_h);
    lay_rect(image, rects + BIND_SECOND_RECT, big_x, big_y, big_w, big_h);
    done = aes_fm_dial(image, type, rects + BIND_FIRST_RECT, rects + BIND_SECOND_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
    return done;
}

/* $fde022 — form_alert. */
int16_t aes_desk_form_alert(uint8_t *image, int16_t default_button, uint32_t string)
{
    int16_t button = aes_fm_alert(image, default_button, string);

    yield(image);
    return button;
}

/* $fde03e — form_error. */
int16_t aes_desk_form_error(uint8_t *image, int16_t code)
{
    int16_t button = aes_fm_error(image, code);

    yield(image);
    return button;
}

/* $fde054 — form_center: ob_center's rectangle copied out through the caller's four pointers BEFORE the yield (the
 * one binding that copies first). The ROM answers what ob_center left in D0; ob_center answers nothing in C. */
void aes_desk_form_center(uint8_t *image, uint32_t tree, uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out)
{
    uint16_t rect_local[GRECT_WORDS];
    uint32_t rect = host_slot_claim(AES_DESK_BIND_FRAME, rect_local);

    aes_ob_center(image, tree, rect + BIND_ANSWERS);
    four_answers_out(image, rect + BIND_ANSWERS, x_out, y_out, w_out, h_out);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
}

/* $fde094 — graf_mouse: above 255 — as a SIGNED word (`ble`), where the AES's own arm compares unsigned — the cursor
 * hidden (256) or shown (257); else its form set: the caller's own (255), or the system resource's bit image three
 * past the number, which rs_gaddr answers the address of into the frame. No answer of its own. */
void aes_desk_graf_mouse(uint8_t *image, int16_t number, uint32_t form)
{
    if (number > GRAF_MOUSE_LAST_FORM) {
        if (number == GRAF_MOUSE_HIDE)
            aes_gsx_moff(image);
        if (number == GRAF_MOUSE_SHOW)
            aes_gsx_mon(image);
    } else {
        if (number != GRAF_MOUSE_USER_FORM) {
            uint32_t form_local;
            uint32_t answer = host_slot_claim(AES_DESK_BIND_FRAME, &form_local);

            (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_BIPDATA,
                               (int16_t)(number + GRAF_MOUSE_FIRST_IMAGE), answer + BIND_FORM);
            form = bus_long(image, be32(image + answer + BIND_FORM));
            host_slot_release(AES_DESK_BIND_FRAME);
        }
        aes_gsx_mfset(image, form);
    }
    yield(image);
}

/* $fde122 — graf_rubbox. No answer of its own. */
void aes_desk_graf_rubbox(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height,
                          uint32_t width_out, uint32_t height_out)
{
    aes_gr_rubbox(image, x, y, min_width, min_height, width_out, height_out);
    yield(image);
}

/* $fde142 — graf_mkstate. The ROM answers what gr_mkstate left in D0; gr_mkstate answers nothing in C. */
void aes_desk_graf_mkstate(uint8_t *image, uint32_t mouse_x_out, uint32_t mouse_y_out, uint32_t buttons_out,
                           uint32_t keys_out)
{
    aes_gr_mkstate(image, mouse_x_out, mouse_y_out, buttons_out, keys_out);
    yield(image);
}

/* The two rectangles of a growing or shrinking box, laid in the bindings' frame; the frame's address. */
static inline uint32_t lay_box_pair(uint8_t *image, uint32_t rects, int16_t from_x, int16_t from_y, int16_t from_w,
                                    int16_t from_h, int16_t to_x, int16_t to_y, int16_t to_w, int16_t to_h)
{
    lay_rect(image, rects + BIND_FIRST_RECT, from_x, from_y, from_w, from_h);
    lay_rect(image, rects + BIND_SECOND_RECT, to_x, to_y, to_w, to_h);
    return rects;
}

/* $fde16a — graf_growbox. No answer of its own. */
void aes_desk_graf_growbox(uint8_t *image, int16_t from_x, int16_t from_y, int16_t from_w, int16_t from_h,
                           int16_t to_x, int16_t to_y, int16_t to_w, int16_t to_h)
{
    uint16_t rects_local[FRAME_LOCAL_WORDS(BIND_RECT_PAIR_BYTES)];
    uint32_t rects = lay_box_pair(image, host_slot_claim(AES_DESK_BIND_FRAME, rects_local), from_x, from_y, from_w,
                                  from_h, to_x, to_y, to_w, to_h);

    aes_gr_growbox(image, rects + BIND_FIRST_RECT, rects + BIND_SECOND_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
}

/* $fde182 — graf_shrinkbox. No answer of its own. */
void aes_desk_graf_shrinkbox(uint8_t *image, int16_t from_x, int16_t from_y, int16_t from_w, int16_t from_h,
                             int16_t to_x, int16_t to_y, int16_t to_w, int16_t to_h)
{
    uint16_t rects_local[FRAME_LOCAL_WORDS(BIND_RECT_PAIR_BYTES)];
    uint32_t rects = lay_box_pair(image, host_slot_claim(AES_DESK_BIND_FRAME, rects_local), from_x, from_y, from_w,
                                  from_h, to_x, to_y, to_w, to_h);

    aes_gr_shrinkbox(image, rects + BIND_FIRST_RECT, rects + BIND_SECOND_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
}

/* $fde19a — menu_tnormal: the title's SELECTED bit set where the caller asks it NOT normal, redrawn. */
int16_t aes_desk_menu_tnormal(uint8_t *image, uint32_t tree, int16_t title, int16_t normal)
{
    int16_t changed = aes_do_chg(image, tree, title, MENU_SELECTED, !normal, MN_REDRAW, MN_CHECK_DISABLED);

    yield(image);
    return changed;
}

/* $fde1d4 — menu_bar. The ROM answers what mn_bar left in D0; mn_bar answers nothing in C. */
void aes_desk_menu_bar(uint8_t *image, uint32_t tree, int16_t show)
{
    aes_mn_bar(image, tree, show);
    yield(image);
}

/* $fde1f0 — menu_icheck. */
int16_t aes_desk_menu_icheck(uint8_t *image, uint32_t tree, int16_t item, int16_t check)
{
    int16_t changed = aes_do_chg(image, tree, item, MENU_CHECKED, check, MN_NO_REDRAW, !MN_CHECK_DISABLED);

    yield(image);
    return changed;
}

/* $fde21a — menu_ienable: the item's DISABLED bit set where the caller asks it NOT enabled, the bar redrawn where the
 * item's top bit says so. */
int16_t aes_desk_menu_ienable(uint8_t *image, uint32_t tree, int16_t item, int16_t enable)
{
    uint16_t item_word = (uint16_t)item;
    int16_t changed = aes_do_chg(image, tree, (int16_t)(item_word & ~SIGN_BIT16), MENU_DISABLED, !enable,
                                 (item_word & SIGN_BIT16) != 0, !MN_CHECK_DISABLED);

    yield(image);
    return changed;
}

/* $fde264 — objc_offset. */
int16_t aes_desk_objc_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out)
{
    int16_t done = aes_ob_offset(image, tree, object, x_out, y_out);

    yield(image);
    return done;
}

/* $fde28c — objc_order. The ROM answers what ob_order left in D0; ob_order answers nothing in C. */
void aes_desk_objc_order(uint8_t *image, uint32_t tree, int16_t object, int16_t position)
{
    aes_ob_order(image, tree, object, position);
    yield(image);
}

/* $fde2a8 — objc_find. */
int16_t aes_desk_objc_find(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t x, int16_t y)
{
    int16_t found = aes_ob_find(image, tree, object, depth, x, y);

    yield(image);
    return found;
}

/* $fde2cc — objc_add. The ROM answers what ob_add left in D0; ob_add answers nothing in C. */
void aes_desk_objc_add(uint8_t *image, uint32_t tree, int16_t parent, int16_t child)
{
    aes_ob_add(image, tree, parent, child);
    yield(image);
}

/* The clip set to the rectangle a drawing binding was handed, by the address of the caller's own words. */
static inline void clip_to(uint8_t *image, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t clip_local[GRECT_WORDS];
    uint32_t clip = host_slot_claim(AES_DESK_BIND_FRAME, clip_local);

    lay_rect(image, clip + BIND_FIRST_RECT, x, y, w, h);
    (void)aes_gsx_sclip(image, clip + BIND_FIRST_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
}

/* $fde2e8 — objc_draw: the clip set first. The ROM answers what ob_draw left in D0; ob_draw answers nothing in C. */
void aes_desk_objc_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t clip_x, int16_t clip_y,
                        int16_t clip_w, int16_t clip_h)
{
    clip_to(image, clip_x, clip_y, clip_w, clip_h);
    aes_ob_draw(image, tree, object, depth);
    yield(image);
}

/* $fde30e — objc_change: the clip set first; the caller's word between the object and the clip is read by nothing.
 * The ROM answers what ob_change left in D0; ob_change answers nothing in C. */
void aes_desk_objc_change(uint8_t *image, uint32_t tree, int16_t object, int16_t reserved, int16_t clip_x,
                          int16_t clip_y, int16_t clip_w, int16_t clip_h, int16_t new_state, int16_t redraw)
{
    (void)reserved;
    clip_to(image, clip_x, clip_y, clip_w, clip_h);
    aes_ob_change(image, tree, object, new_state, redraw);
    yield(image);
}

/* $fde354 — rsrc_gaddr, over the desk's own global[]. */
int16_t aes_desk_rsrc_gaddr(uint8_t *image, int16_t type, int16_t index, uint32_t answer)
{
    int16_t found = aes_rs_gaddr(image, AES_DESK_APP_GLOBAL, type, index, answer);

    yield(image);
    return found;
}

/* $fde376 — shel_write. */
int16_t aes_desk_shel_write(uint8_t *image, int16_t doexec, int16_t isgem, int16_t isover, uint32_t command,
                            uint32_t tail)
{
    int16_t done = aes_sh_write(image, doexec, isgem, isover, command, tail);

    yield(image);
    return done;
}

/* $fde39e — shel_get. */
int16_t aes_desk_shel_get(uint8_t *image, uint32_t buffer, int16_t bytes)
{
    int16_t done = aes_sh_get(image, buffer, bytes);

    yield(image);
    return done;
}

/* $fde3ba — shel_put. */
int16_t aes_desk_shel_put(uint8_t *image, uint32_t data, int16_t bytes)
{
    int16_t done = aes_sh_put(image, data, bytes);

    yield(image);
    return done;
}

/* $fde3d6 — wind_close. */
uint16_t aes_desk_wind_close(uint8_t *image, int16_t window)
{
    uint16_t done = aes_wm_close(image, window);

    yield(image);
    return done;
}

/* $fde3ec — wind_delete: wm_delete's leftover word, its core's own answer (`aes/wmlib.h`). */
uint16_t aes_desk_wind_delete(uint8_t *image, int16_t window)
{
    uint16_t left = aes_wm_delete(image, window);

    yield(image);
    return left;
}

/* $fde402 — wind_find. */
int16_t aes_desk_wind_find(uint8_t *image, int16_t x, int16_t y)
{
    int16_t window = aes_wm_find(image, x, y);

    yield(image);
    return window;
}

/* $fde41a — wind_update. */
uint16_t aes_desk_wind_update(uint8_t *image, int16_t code)
{
    uint16_t done = aes_wm_update(image, code);

    yield(image);
    return done;
}

/* $fde430 — wind_create: the rectangle handed by the address of the caller's own words. */
int16_t aes_desk_wind_create(uint8_t *image, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t rect_local[GRECT_WORDS];
    uint32_t rect = host_slot_claim(AES_DESK_BIND_FRAME, rect_local);
    int16_t window;

    lay_rect(image, rect + BIND_FIRST_RECT, x, y, w, h);
    window = aes_wm_create(image, kind, rect + BIND_FIRST_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
    return window;
}

/* $fde450 — wind_open: the same. */
uint16_t aes_desk_wind_open(uint8_t *image, int16_t window, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t rect_local[GRECT_WORDS];
    uint32_t rect = host_slot_claim(AES_DESK_BIND_FRAME, rect_local);
    uint16_t done;

    lay_rect(image, rect + BIND_FIRST_RECT, x, y, w, h);
    done = aes_wm_open(image, window, rect + BIND_FIRST_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
    return done;
}

/* $fde470 — wind_get: its four words copied out after the yield. */
uint16_t aes_desk_wind_get(uint8_t *image, int16_t window, int16_t field, uint32_t first_out, uint32_t second_out,
                           uint32_t third_out, uint32_t fourth_out)
{
    uint16_t words_local[GRECT_WORDS];
    uint32_t words = host_slot_claim(AES_DESK_BIND_FRAME, words_local);
    uint16_t done = aes_wm_get(image, window, field, words + BIND_ANSWERS);

    yield(image);
    four_answers_out(image, words + BIND_ANSWERS, first_out, second_out, third_out, fourth_out);
    host_slot_release(AES_DESK_BIND_FRAME);
    return done;
}

/* $fde4ac — wind_set: the four words handed by the address of the caller's own. */
uint16_t aes_desk_wind_set(uint8_t *image, int16_t window, int16_t field, int16_t first, int16_t second, int16_t third,
                           int16_t fourth)
{
    uint16_t words_local[GRECT_WORDS];
    uint32_t words = host_slot_claim(AES_DESK_BIND_FRAME, words_local);
    uint16_t done;

    lay_rect(image, words + BIND_FIRST_RECT, first, second, third, fourth);
    done = aes_wm_set(image, window, field, words + BIND_FIRST_RECT);
    host_slot_release(AES_DESK_BIND_FRAME);
    yield(image);
    return done;
}

/* $fde4cc — wind_calc: wm_calc's leftover word, its core's own answer (`aes/wmlib.h`). */
int16_t aes_desk_wind_calc(uint8_t *image, int16_t type, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h,
                           uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out)
{
    int16_t left = aes_wm_calc(image, type, kind, x, y, w, h, x_out, y_out, w_out, h_out);

    yield(image);
    return left;
}
