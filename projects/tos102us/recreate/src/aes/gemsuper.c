/* gemsuper.c — THE AES'S OPCODE SWITCH and the copy round it (`aes/gemsuper.h`): aes_dispatch and aes_marshal. Alcyon
 * C in the ROM, ported over its own order.
 *
 * WHO CALLS WHAT. The switch is OUTSIDE the event layer, so the three door entries its arms call (ap_rdwr, ev_button,
 * ev_multi) are called through the event door (`aes/evdoor.h`); the event layer's other routines (ev_keybd, ev_mouse,
 * ev_mesag, ev_timer, ev_dclick, ap_find, the tape) are no entries and are called as they are — each reaches the
 * door's entries by their cores, as the ROM's reach the ROM's.
 *
 * THE COUNTS. The marshal copies as many words as the program's control says, into arrays of 16 (int_in), 7 (int_out)
 * and 2 longwords (addr_in) laid one above the other in its frame. Inside the frame an over-long copy is the ROM's own
 * and is reproduced as it is — the frame is the ROM's, word for word: a seventeenth word of int_in IS THE OPCODE the
 * switch is then called with, a nineteenth the count of int_out copied back. Past the frame lie the saved A6 and the
 * return address, and the three copies are not alike there:
 *   * int_in past 20 words and addr_in past 15 longwords STORE over them, and the ROM then returns through the
 *     program's own words (a jump of its choosing, in supervisor mode). No C has that frame: the copy is REFUSED BY
 *     NAME on both builds — A DECLARED DIVERGENCE on target (a faithful one would be hand 68000);
 *   * int_out past 27 words only READS them — the copy back hands the program the saved A6, the return address and
 *     whatever the stack holds above — and the ROM returns as ever. REPRODUCED: on target the copy runs past the
 *     frame as the ROM's does, and the words it reads there are by nature OUR build's (its saved A6, its return
 *     address, its arguments); off target they are the host slot's model of them (`aes/gemsuper.h`,
 *     MARSHAL_HOST_CALLER_BYTES), and a count past the model is refused — off target alone.
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "stack_diet.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/aptape.h"
#include "aes/evdoor.h"
#include "aes/evlib.h"
#include "aes/fmdo.h"
#include "aes/fmlib.h"
#include "aes/fslib.h"
#include "aes/gemgraf.h"
#include "aes/geminit.h"
#include "aes/gemsuper.h"
#include "aes/grdrag.h"
#include "aes/grwait.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/obedit.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/oblib.h"
#include "aes/pdpipe.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/shell_buf.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"

/* ================================================================================================
 * THE ARMS that are more than one call, each inlined into the switch (`aes_dispatch`, below).
 * ============================================================================================= */

/* Word `index` of int_in or int_out, as the Alcyon `int` an arm pushes. */
static inline int16_t word_of(const uint8_t *image, uint32_t words, uint32_t index)
{
    return (int16_t)bus_word(image, words + index * M68K_WORD_BYTES);
}

/* The ADDRESS of word `index` of int_in or int_out: what an arm hands a routine that reads a rectangle in place, or
 * answers through a pointer. */
static inline uint32_t word_at(uint32_t words, uint32_t index)
{
    return words + index * M68K_WORD_BYTES;
}

/* Longword `index` of addr_in. */
static inline uint32_t address_of(const uint8_t *image, uint32_t addr_in, uint32_t index)
{
    return bus_long(image, addr_in + index * M68K_LONG_BYTES);
}

/* Inside the switch and its arms: int_in[n] and its address, int_out[n]'s address, addr_in[n]. */
#define in(index)      word_of(image, int_in, index)
#define in_at(index)   word_at(int_in, index)
#define out_at(index)  word_at(int_out, index)
#define address(index) address_of(image, addr_in, index)

/* $fe5db2 — appl_init: the program's global[] filled in, and its process's id answered. */
static inline uint16_t appl_init(uint8_t *image, uint32_t global)
{
    set_bus_word(image, global + AES_GLOBAL_VERSION, AES_VERSION);
    set_bus_word(image, global + AES_GLOBAL_COUNT, AES_APPLICATIONS);
    set_bus_word(image, global + AES_GLOBAL_ID, be16(image + running(image, PD_PID)));
    set_bus_word(image, global + AES_GLOBAL_NPLANES, be16(image + AES_GL_NPLANES));
    set_bus_long(image, global + AES_GLOBAL_THEGLO, AES_THEGLO);
    set_bus_word(image, global + AES_GLOBAL_BVDISK, be16(image + AES_GL_BVDISK));
    set_bus_word(image, global + AES_GLOBAL_BVHARD, be16(image + AES_GL_BVHARD));
    return be16(image + running(image, PD_PID));
}

/* $fe5e40 — appl_exit: the caller's accessories told to close, whatever its pipe still holds read away, and every
 * process run (all_run: a yield, then the screen's lock taken and given back). */
static inline uint16_t appl_exit(uint8_t *image)
{
    aes_mn_clsda(image);
    if (be16(image + running(image, PD_QUEUE_INDEX)))
        (void)evdoor_ap_rdwr(image, AP_RDWR_READ, (int16_t)be16(image + running(image, PD_PID)),
                             (int16_t)be16(image + running(image, PD_QUEUE_INDEX)), AES_VALSTR);
    aes_all_run(image);
    return AES_ANSWER_DONE;
}

/* $fe5ec2 — evnt_multi: the timer's two words made one long (where the flags ask for a timer: the ROM leaves its
 * local unset otherwise), the clicks, mask and state packed as ev_multi takes them, the rectangles handed in place. */
static inline uint16_t evnt_multi(uint8_t *image, uint32_t int_in, uint32_t int_out, uint32_t addr_in)
{
    int16_t flags = in(EVNT_MULTI_FLAGS);
    uint32_t timer = EVNT_MULTI_NO_TIMER;
    uint32_t button;

    if (flags & EV_MU_TIMER)
        timer = words_long(in(EVNT_MULTI_TIME_HIGH), in(EVNT_MULTI_TIME_LOW));
    button = words_long(in(EVNT_MULTI_CLICKS), (int16_t)((uint16_t)(in(EVNT_MULTI_MASK) << BUTTON_PARM_MASK_SHIFT)
                                                         | (uint16_t)in(EVNT_MULTI_STATE)));
    return evdoor_ev_multi(image, flags, in_at(EVNT_MULTI_MOUSE1), in_at(EVNT_MULTI_MOUSE2), timer, button, address(0),
                           out_at(AES_FIRST_ANSWER));
}

/* $fe5f7c — menu_ienable: the item's DISABLED bit set where the caller asks it NOT enabled, the bar redrawn where
 * the item's top bit says so. */
static inline uint16_t menu_ienable(uint8_t *image, uint32_t int_in, uint32_t addr_in)
{
    uint16_t item = (uint16_t)in(0);

    (void)aes_do_chg(image, address(0), (int16_t)(item & ~SIGN_BIT16), MENU_DISABLED, !in(1), (item & SIGN_BIT16) != 0,
                     !MN_CHECK_DISABLED);
    return AES_ANSWER_DONE;
}

/* $fe5fee — menu_text: the caller's string copied over the item's own — the text its ob_spec points at, the item an
 * UNSIGNED index (`mulu.w #24`). */
static inline uint16_t menu_text(uint8_t *image, uint32_t int_in, uint32_t addr_in)
{
    uint32_t item = (uint16_t)in(0);

    (void)aes_lstcpy(image, bus_long(image, address(0) + item * OB_BYTES + OB_SPEC), address(1));
    return AES_ANSWER_DONE;
}

/* $fe60b4 — objc_edit: the caller's index answered back first, then edited in place. */
static inline uint16_t objc_edit(uint8_t *image, uint32_t int_in, uint32_t int_out, uint32_t addr_in)
{
    uint32_t index_at = out_at(AES_FIRST_ANSWER);

    set_bus_word(image, index_at, (uint16_t)in(OBJC_EDIT_INDEX));
    return (uint16_t)aes_ob_edit(image, address(0), in(0), in(OBJC_EDIT_CHAR), index_at, in(OBJC_EDIT_KIND));
}

/* $fe6162 — form_keybd: the whole screen below the bar clipped to; the key and the next object answered back first
 * (the key in int_out[2], the object in int_out[1]), then both handed fm_keybd in place. */
static inline uint16_t form_keybd(uint8_t *image, uint32_t int_in, uint32_t int_out, uint32_t addr_in)
{
    uint32_t next_at = out_at(FORM_KEYBD_NEXT_OUT);
    uint32_t key_at = out_at(FORM_KEYBD_KEY_OUT);

    (void)aes_gsx_sclip(image, AES_GL_RFULL);
    set_bus_word(image, key_at, (uint16_t)in(FORM_KEYBD_KEY));
    set_bus_word(image, next_at, (uint16_t)in(FORM_KEYBD_NEXT));
    return (uint16_t)aes_fm_keybd(image, address(0), in(0), key_at, next_at);
}

/* $fe6216 / $fe621e — graf_growbox and graf_shrinkbox: each arm NAMES ITS ROUTINE BY VALUE (`movea.l #routine,a0`)
 * and both share one call, `jsr (a0)`, over the two rectangles in int_in. Off target the value is the ROM routine's
 * address, which this call resolves to its core; on target the routine's own entry, called through it. */
static inline void box_between(uint8_t *image, uint32_t routine, uint32_t int_in)
{
    uint32_t from = in_at(GRAF_BOX_FROM);
    uint32_t to = in_at(GRAF_BOX_TO);

#ifdef RECREATE_HOST_DIFFERENTIAL
    if (routine == AES_ROM_GR_GROWBOX)
        aes_gr_growbox(image, from, to);
    else
        aes_gr_shrinkbox(image, from, to);
#else
    ((void (*)(uint8_t *, uint32_t, uint32_t))(uintptr_t)routine)(image, from, to);
#endif
}

/* $fe6266 — graf_handle: a character cell's and a box's sizes, and the AES's workstation handle. */
static inline uint16_t graf_handle(uint8_t *image, uint32_t int_out)
{
    set_bus_word(image, out_at(GRAF_HANDLE_WCHAR), be16(image + AES_GL_WCHAR));
    set_bus_word(image, out_at(GRAF_HANDLE_HCHAR), be16(image + AES_GL_HCHAR));
    set_bus_word(image, out_at(GRAF_HANDLE_WBOX), be16(image + AES_GL_WBOX));
    set_bus_word(image, out_at(GRAF_HANDLE_HBOX), be16(image + AES_GL_HBOX));
    return be16(image + AES_GL_HANDLE);
}

/* The system resource's bit image three past graf_mouse's `number`: rs_gaddr answers its data's address into the
 * frame, and the arm reads the form through that. */
static inline uint32_t system_form(uint8_t *image, uint16_t number)
{
    uint32_t form_local;
    uint32_t answer_at = host_slot_claim(AES_DISPATCH_MOUSE_FORM, &form_local);
    uint32_t form;

    (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_BIPDATA, (int16_t)(number + GRAF_MOUSE_FIRST_IMAGE),
                       answer_at);
    form = bus_long(image, be32(image + answer_at));
    host_slot_release(AES_DISPATCH_MOUSE_FORM);
    return form;
}

/* $fe628e — graf_mouse: the cursor hidden (256) or shown (257) — any other number above 255 does nothing — or its
 * form set: the caller's own (255), else one of the AES's. */
static inline uint16_t graf_mouse(uint8_t *image, uint32_t int_in, uint32_t addr_in)
{
    uint16_t number = (uint16_t)in(0);

    if (number > GRAF_MOUSE_LAST_FORM) {
        if (number == GRAF_MOUSE_HIDE)
            aes_gsx_moff(image);
        else if (number == GRAF_MOUSE_SHOW)
            aes_gsx_mon(image);
    } else {
        aes_gsx_mfset(image, number == GRAF_MOUSE_USER_FORM ? address(0) : system_form(image, number));
    }
    return AES_ANSWER_DONE;
}

/* $fe64a6 — the default arm: the alert, and the answer that says no such call. */
static inline uint16_t no_such_call(uint8_t *image)
{
    (void)aes_fm_show(image, AES_BAD_FUNCTION_STRING, AES_BAD_FUNCTION_VALUES, AES_BAD_FUNCTION_BUTTON);
    return (uint16_t)AES_ANSWER_NO_SUCH_CALL;
}

/* ================================================================================================
 * $fe5d9c — aes_dispatch.
 * ============================================================================================= */

/* THE SWITCH IS THE ROM'S JUMP TABLE, and is compiled as one on target: the build's `-fno-jump-tables` keeps
 * ABSOLUTE addresses out of the read-only data (`atari/target.mk`), and the 68000's table is neither — sixteen-bit
 * distances from the table, in the text (`test_aes_gemsuper.py` holds that no relocation of this function names its
 * own text). Compared arm by arm instead, an opcode at the tree's bottom pays seven compares for the ROM's one
 * indexed jump: measured, appl_init at 714 cycles to the ROM's 632 (1.13: OVER the bar) where the table's own line
 * reads 608 to 632 (0.96).
 * GCC DOCUMENTS `optimize` AS A DEBUGGING AID, "not suitable for production code": what holds it here is not the
 * manual but the build's own output, read on every run — the head's one compare and indexed jump on both blobs, and
 * no relocation of this function against its own text (`test_aes_gemsuper.py`, the two guards). It carries the one
 * setting the attribute would otherwise reset (`stack_diet.h`, OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS). */
#if defined(__GNUC__) && !defined(__clang__)
#define COMPILED_AS_A_JUMP_TABLE __attribute__((optimize(OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS, "jump-tables")))
#else
#define COMPILED_AS_A_JUMP_TABLE
#endif

/* aes_dispatch(opcode, global, int_in, int_out, addr_in). An arm that returns answers what its routine does; one
 * that ends on DONE keeps the 1 the ROM's switch starts with, whatever its routine answered. The opcode is a WORD
 * less 10 compared UNSIGNED with 115 ($fe64ba sub.w / $fe64be cmp.w / bhi): below 10, above 125 and the range's 48
 * gaps are one default arm. */
COMPILED_AS_A_JUMP_TABLE
uint16_t aes_dispatch(uint8_t *image, int16_t opcode, uint32_t global, uint32_t int_in, uint32_t int_out,
                      uint32_t addr_in)
{
    switch ((uint16_t)opcode) {
    case AES_APPL_INIT_OPCODE:
        return appl_init(image, global);
    case AES_APPL_READ_OPCODE:  /* appl_read */
        (void)evdoor_ap_rdwr(image, AP_RDWR_READ, in(0), in(1), address(0));
        return AES_ANSWER_DONE;
    case AES_ROM_AP_RDWR_OPCODE:  /* appl_write */
        (void)evdoor_ap_rdwr(image, AP_RDWR_WRITE, in(0), in(1), address(0));
        return AES_ANSWER_DONE;
    case AES_ROM_AP_FIND_OPCODE:  /* appl_find */
        return (uint16_t)aes_ap_find(image, address(0));
    case AES_ROM_AP_TPLAY_OPCODE:  /* appl_tplay */
        aes_ap_tplay(image, address(0), in(0), in(1));
        return AES_ANSWER_DONE;
    case AES_ROM_AP_TRECD_OPCODE:  /* appl_trecord */
        return aes_ap_trecd(image, address(0), in(0));
    case AES_APPL_EXIT_OPCODE:
        return appl_exit(image);
    case AES_ROM_EV_KEYBD_OPCODE:  /* evnt_keybd */
        return aes_ev_keybd(image);
    case AES_ROM_EV_BUTTON_OPCODE:  /* evnt_button */
        return evdoor_ev_button(image, in(0), in(1), in(2), out_at(AES_FIRST_ANSWER));
    case AES_ROM_EV_MOUSE_OPCODE:  /* evnt_mouse */
        return aes_ev_mouse(image, in_at(0), out_at(AES_FIRST_ANSWER));
    case AES_ROM_EV_MESAG_OPCODE:  /* evnt_mesag */
        return aes_ev_mesag(image, address(0));
    case AES_ROM_EV_TIMER_OPCODE:  /* evnt_timer */
        return aes_ev_timer(image, (int32_t)words_long(in(1), in(0)));
    case AES_ROM_EV_MULTI_OPCODE:
        return evnt_multi(image, int_in, int_out, addr_in);
    case AES_ROM_EV_DCLICK_OPCODE:  /* evnt_dclick */
        return (uint16_t)aes_ev_dclick(image, in(0), in(1));
    case AES_ROM_MN_BAR_OPCODE:  /* menu_bar */
        aes_mn_bar(image, address(0), in(0));
        return AES_ANSWER_DONE;
    case AES_ROM_DO_CHG_OPCODE:  /* menu_icheck */
        (void)aes_do_chg(image, address(0), in(0), MENU_CHECKED, in(1), MN_NO_REDRAW, !MN_CHECK_DISABLED);
        return AES_ANSWER_DONE;
    case AES_ROM_DO_CHG_OPCODE_32:
        return menu_ienable(image, int_in, addr_in);
    case AES_ROM_DO_CHG_OPCODE_33:  /* menu_tnormal */
        (void)aes_do_chg(image, address(0), in(0), MENU_SELECTED, !in(1), MN_REDRAW, MN_CHECK_DISABLED);
        return AES_ANSWER_DONE;
    case AES_MENU_TEXT_OPCODE:
        return menu_text(image, int_in, addr_in);
    case AES_ROM_MN_REGISTER_OPCODE:  /* menu_register */
        return (uint16_t)aes_mn_register(image, in(0), address(0));
    case AES_ROM_OB_ADD_OPCODE:  /* objc_add */
        aes_ob_add(image, address(0), in(0), in(1));
        return AES_ANSWER_DONE;
    case AES_ROM_OB_DELETE_OPCODE:  /* objc_delete */
        aes_ob_delete(image, address(0), in(0));
        return AES_ANSWER_DONE;
    case AES_ROM_OB_DRAW_OPCODE:  /* objc_draw */
        (void)aes_gsx_sclip(image, in_at(OBJC_DRAW_CLIP));
        aes_ob_draw(image, address(0), in(0), in(1));
        return AES_ANSWER_DONE;
    case AES_ROM_OB_FIND_OPCODE:  /* objc_find */
        return (uint16_t)aes_ob_find(image, address(0), in(0), in(1), in(2), in(3));
    case AES_ROM_OB_OFFSET_OPCODE:  /* objc_offset */
        (void)aes_ob_offset(image, address(0), in(0), out_at(OBJC_OFFSET_X), out_at(OBJC_OFFSET_Y));
        return AES_ANSWER_DONE;
    case AES_ROM_OB_ORDER_OPCODE:  /* objc_order */
        aes_ob_order(image, address(0), in(0), in(1));
        return AES_ANSWER_DONE;
    case AES_ROM_OB_EDIT_OPCODE:
        return objc_edit(image, int_in, int_out, addr_in);
    case AES_ROM_OB_CHANGE_OPCODE:  /* objc_change */
        (void)aes_gsx_sclip(image, in_at(OBJC_CHANGE_CLIP));
        aes_ob_change(image, address(0), in(0), in(OBJC_CHANGE_STATE), in(OBJC_CHANGE_REDRAW));
        return AES_ANSWER_DONE;
    case AES_ROM_FM_DO_OPCODE:  /* form_do */
        return (uint16_t)aes_fm_do(image, address(0), in(0));
    case AES_ROM_FM_DIAL_OPCODE:  /* form_dial */
        return aes_fm_dial(image, in(0), in_at(FORM_DIAL_LITTLE), in_at(FORM_DIAL_BIG));
    case AES_ROM_FM_ALERT_OPCODE:  /* form_alert */
        return (uint16_t)aes_fm_alert(image, in(0), address(0));
    case AES_ROM_FM_ERROR_OPCODE:  /* form_error */
        return (uint16_t)aes_fm_error(image, in(0));
    case AES_ROM_OB_CENTER_OPCODE:  /* form_center */
        aes_ob_center(image, address(0), out_at(AES_FIRST_ANSWER));
        return AES_ANSWER_DONE;
    case AES_ROM_FM_KEYBD_OPCODE:
        return form_keybd(image, int_in, int_out, addr_in);
    case AES_ROM_FM_BUTTON_OPCODE:  /* form_button */
        (void)aes_gsx_sclip(image, AES_GL_RFULL);
        return (uint16_t)aes_fm_button(image, address(0), in(0), in(1), out_at(AES_FIRST_ANSWER));
    case AES_ROM_GR_RUBBOX_OPCODE:  /* graf_rubberbox */
        aes_gr_rubbox(image, in(0), in(1), in(2), in(3), out_at(GRAF_RUBBOX_WIDTH), out_at(GRAF_RUBBOX_HEIGHT));
        return AES_ANSWER_DONE;
    case AES_ROM_GR_DRAGBOX_OPCODE:  /* graf_dragbox */
        aes_gr_dragbox(image, in(0), in(1), in(2), in(3), in_at(GRAF_DRAGBOX_BOUND), out_at(GRAF_DRAGBOX_X),
                       out_at(GRAF_DRAGBOX_Y));
        return AES_ANSWER_DONE;
    case AES_ROM_GR_MOVEBOX_OPCODE:  /* graf_movebox */
        aes_gr_movebox(image, in(0), in(1), in(2), in(3), in(4), in(5));
        return AES_ANSWER_DONE;
    case AES_ROM_GR_GROWBOX_OPCODE:  /* graf_growbox */
        box_between(image, ALCYON_ROUTINE(AES_ROM_GR_GROWBOX, aes_gr_growbox), int_in);
        return AES_ANSWER_DONE;
    case AES_ROM_GR_SHRINKBOX_OPCODE:  /* graf_shrinkbox */
        box_between(image, ALCYON_ROUTINE(AES_ROM_GR_SHRINKBOX, aes_gr_shrinkbox), int_in);
        return AES_ANSWER_DONE;
    case AES_ROM_GR_WATCHBOX_OPCODE:  /* graf_watchbox */
        return aes_gr_watchbox(image, address(0), in(GRAF_WATCHBOX_OBJECT), in(GRAF_WATCHBOX_INSIDE),
                               in(GRAF_WATCHBOX_OUTSIDE));
    case AES_ROM_GR_SLIDEBOX_OPCODE:  /* graf_slidebox */
        return (uint16_t)aes_gr_slidebox(image, address(0), in(0), in(1), in(2));
    case AES_GRAF_HANDLE_OPCODE:
        return graf_handle(image, int_out);
    case AES_GRAF_MOUSE_OPCODE:
        return graf_mouse(image, int_in, addr_in);
    case AES_ROM_GR_MKSTATE_OPCODE:  /* graf_mkstate */
        aes_gr_mkstate(image, out_at(GRAF_MKSTATE_X), out_at(GRAF_MKSTATE_Y), out_at(GRAF_MKSTATE_BUTTONS),
                       out_at(GRAF_MKSTATE_KEYS));
        return (uint16_t)GRAF_MKSTATE_ANSWER;
    case AES_ROM_SC_READ_OPCODE:  /* scrp_read */
        (void)aes_sc_read(image, address(0));
        return AES_ANSWER_DONE;
    case AES_ROM_SC_WRITE_OPCODE:  /* scrp_write */
        (void)aes_sc_write(image, address(0));
        return AES_ANSWER_DONE;
    case AES_ROM_FS_INPUT_OPCODE:  /* fsel_input */
        (void)aes_fs_input(image, address(0), address(1), out_at(AES_FIRST_ANSWER));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_CREATE_OPCODE:  /* wind_create */
        return (uint16_t)aes_wm_create(image, in(0), in_at(WIND_RECT));
    case AES_ROM_WM_OPEN_OPCODE:  /* wind_open */
        (void)aes_wm_open(image, in(0), in_at(WIND_RECT));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_CLOSE_OPCODE:  /* wind_close */
        (void)aes_wm_close(image, in(0));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_DELETE_OPCODE:  /* wind_delete */
        (void)aes_wm_delete(image, in(0));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_GET_OPCODE:  /* wind_get */
        (void)aes_wm_get(image, in(0), in(1), out_at(AES_FIRST_ANSWER));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_SET_OPCODE:  /* wind_set */
        (void)aes_wm_set(image, in(0), in(1), in_at(WIND_SET_VALUES));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_FIND_OPCODE:  /* wind_find */
        return (uint16_t)aes_wm_find(image, in(0), in(1));
    case AES_ROM_WM_UPDATE_OPCODE:  /* wind_update */
        (void)aes_wm_update(image, in(0));
        return AES_ANSWER_DONE;
    case AES_ROM_WM_CALC_OPCODE:  /* wind_calc */
        (void)aes_wm_calc(image, in(0), in(1), in(2), in(3), in(4), in(5), out_at(WIND_CALC_X), out_at(WIND_CALC_Y),
                          out_at(WIND_CALC_W), out_at(WIND_CALC_H));
        return AES_ANSWER_DONE;
    case AES_ROM_RS_LOAD_OPCODE:  /* rsrc_load */
        return (uint16_t)aes_rs_load(image, global, address(0));
    case AES_ROM_RS_FREE_OPCODE:  /* rsrc_free */
        return (uint16_t)aes_rs_free(image, global);
    case AES_ROM_RS_GADDR_OPCODE:  /* rsrc_gaddr */
        return (uint16_t)aes_rs_gaddr(image, global, in(0), in(1), AES_RS_ADDROUT);
    case AES_ROM_RS_SADDR_OPCODE:  /* rsrc_saddr */
        return (uint16_t)aes_rs_saddr(image, global, in(0), in(1), address(0));
    case AES_ROM_RS_OBFIX_OPCODE:  /* rsrc_obfix */
        return (uint16_t)aes_rs_obfix(image, address(0), in(0));
    case AES_ROM_SH_READ_OPCODE:  /* shel_read */
        return (uint16_t)aes_sh_read(image, address(0), address(1));
    case AES_ROM_SH_WRITE_OPCODE:  /* shel_write */
        return (uint16_t)aes_sh_write(image, in(0), in(1), in(2), address(0), address(1));
    case AES_ROM_SH_GET_OPCODE:  /* shel_get */
        return (uint16_t)aes_sh_get(image, address(0), in(0));
    case AES_ROM_SH_PUT_OPCODE:  /* shel_put */
        return (uint16_t)aes_sh_put(image, address(0), in(0));
    case AES_ROM_SH_FIND_OPCODE:  /* shel_find */
        return (uint16_t)aes_sh_find(image, address(0), SH_FIND_NO_ROUTINE);
    case AES_ROM_SH_ENVRN_OPCODE:  /* shel_envrn */
        return (uint16_t)aes_sh_envrn(image, address(0), address(1));
    default:
        return no_such_call(image);
    }
}

#undef in
#undef in_at
#undef out_at
#undef address

/* ================================================================================================
 * $fe64e6 — aes_marshal.
 * ============================================================================================= */

/* A word of the marshal's frame, read where the ROM reads it — after whatever copy ran over it. */
static inline uint16_t frame_count(const uint8_t *image, uint32_t frame, uint32_t word)
{
    return be16(image + frame + word);
}

/* A copy of `words` words that starts in the frame with room for `room`: past it lie the saved A6 and the return
 * address. wcopy counts in an UNSIGNED word, so every count above `room` leaves the frame. */
static inline void stay_in_the_frame(uint16_t words, uint16_t room, const char *what)
{
    if (words > room)
        recreate_not_reconstructed(what);
}

/* The copy BACK of `words` words of int_out leaves the frame freely, as the ROM's does (the file's head, THE
 * COUNTS): on target nothing is asked. OFF TARGET what it reads above the frame is the host slot's model of a
 * caller's words, and a count past the model would read bytes that stand for nothing. */
static inline void stay_in_the_model_off_target(uint16_t words)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    stay_in_the_frame(words, MARSHAL_HOST_INT_OUT_ROOM,
                      "aes_marshal: more than 35 words of int_out OFF TARGET — the copy back reads past the words the "
                      "host slot models above the frame (on target it runs on, as the ROM's does)");
#else
    (void)words;
#endif
}

/* The marshal over its frame at `frame`: the three copies in, each count read from the copied control WHERE THE ROM
 * READS IT (addr_in's after int_in's copy, the opcode after both — a count past its array has changed them by
 * then), each REFUSED BEFORE IT IS MADE where it would store past the frame; the switch; its answer; int_out copied
 * back, past the frame where the count says so; and, where the opcode is rsrc_gaddr's, the address it parked stored
 * through addr_out. The program's six pointers are each read where it is used. */
static inline void marshal_over(uint8_t *image, uint32_t block, uint32_t frame)
{
    uint16_t words;

    aes_wcopy(image, frame + MARSHAL_CONTROL, bus_long(image, block + AESPB_CONTROL), MARSHAL_CONTROL_WORDS);
    words = frame_count(image, frame, MARSHAL_N_INT_IN);
    if (words) {
        stay_in_the_frame(words, MARSHAL_INT_IN_ROOM,
                          "aes_marshal: more than 20 words of int_in — the copy runs past the frame, over the saved A6 "
                          "and the return address the ROM then returns through");
        aes_wcopy(image, frame + MARSHAL_INT_IN, bus_long(image, block + AESPB_INT_IN), (int16_t)words);
    }
    words = frame_count(image, frame, MARSHAL_N_ADDR_IN);
    if (words) {
        words = (uint16_t)(words << 1);
        stay_in_the_frame(words, MARSHAL_ADDR_IN_ROOM,
                          "aes_marshal: more than 15 longwords of addr_in — the copy runs past the frame, over the "
                          "saved A6 and the return address the ROM then returns through");
        aes_wcopy(image, frame + MARSHAL_ADDR_IN, bus_long(image, block + AESPB_ADDR_IN), (int16_t)words);
    }
    wr16(image + frame + MARSHAL_INT_OUT,
         aes_dispatch(image, (int16_t)frame_count(image, frame, MARSHAL_OPCODE), bus_long(image, block + AESPB_GLOBAL),
                      frame + MARSHAL_INT_IN, frame + MARSHAL_INT_OUT, frame + MARSHAL_ADDR_IN));
    words = frame_count(image, frame, MARSHAL_N_INT_OUT);
    if (words) {
        stay_in_the_model_off_target(words);
        aes_wcopy(image, bus_long(image, block + AESPB_INT_OUT), frame + MARSHAL_INT_OUT, (int16_t)words);
    }
    if (frame_count(image, frame, MARSHAL_OPCODE) == AES_ROM_RS_GADDR_OPCODE)
        set_bus_long(image, bus_long(image, block + AESPB_ADDR_OUT), be32(image + AES_RS_ADDROUT));
}

/* aes_marshal(parameter block): the frame is the call's own — live for as long as the call is, across every wait
 * an arm makes (off target ONE host slot, as every frame a door user holds across a wait is: `host_slot.h`, THE
 * AUDIT — and the slot's own note of what wave 3 owes). Answers nothing: its caller reads no D0. */
void aes_marshal(uint8_t *image, uint32_t parameter_block)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(MARSHAL_FRAME_BYTES)];
    _Static_assert(sizeof frame_local == MARSHAL_FRAME_BYTES, "the frame, as the ROM's `link` lays it");
    _Static_assert(HOST_SLOT_AES_MARSHAL_FRAME_BYTES == MARSHAL_FRAME_BYTES + MARSHAL_HOST_CALLER_BYTES,
                   "the host slot: the frame, then the model of a caller's words above it");

    marshal_over(image, parameter_block, host_slot_claim(AES_MARSHAL_FRAME, frame_local));
    host_slot_release(AES_MARSHAL_FRAME);
}
