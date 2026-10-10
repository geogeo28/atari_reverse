/* gemctrl.c — the SCREEN MANAGER's four handlers (`aes/gemctrl.h`): ct_msgup, hctl_window, hctl_button and hctl_rect.
 * Alcyon C in the ROM, ported over its own order; every callee is its C core (the window, object, graphics and menu
 * libraries', `aes_ap_sendmsg`, `aes_wm_update`, `aes_dsptch`) — a wait is reached through those cores' own door.
 *
 * THEY RUN IN THE SCREEN MANAGER'S PROCESS, called by its main loop — the ROM's ctlmgr, until wave 2 ports it.
 *
 * WHAT THE ROM LEAVES UNSET, AND WHAT THE C HANDS IN ITS PLACE.
 *   - A press on a window that is NOT the top one sends WM_TOPPED with four words (x, y, w, h) the ROM's frame was
 *     never given on that path ($fe489c..$fe48aa): the residue of the screen manager's stack — on the machine the
 *     SAME four words at every arrival (halves of a ROM address and of a RAM address ctlmgr's preceding ev_multi
 *     left at that depth). The C hands HCTL_STALE_WORD four times: A DECLARED DIVERGENCE (`aes/gemctrl.h`,
 *     `STATUS.md`), green in the differential only because the ROM's routine is entered there on a zeroed stack;
 *     `test/test_aes_gemctrl.py` holds what the real arrival carries, and that the ROM sends its frame's words.
 *     (Once ctlmgr is our C — wave 2 — the residue is our build's.)
 *   - A menu left with nothing chosen calls ct_msgup(0, D7, two frame words never set, 0, 0, 0) ($fe49a0): D7 and
 *     the two words are read by nobody — ct_msgup sends nothing for message 0.
 *
 * THE FRAME LOCALS WHOSE ADDRESS IS HANDED ON are host slots off target (`host_slot.h`). Two of hctl_window's and
 * hctl_rect's one stay live while the screen manager is PARKED inside a drag's or the menu's wait: A SLOT PER
 * PROCESS each. The window's size is read out of its slot into C locals before any wait, and that slot given back.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "host_slot.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evlib.h"
#include "aes/gemgraf.h"
#include "aes/gemctrl.h"
#include "aes/grdrag.h"
#include "aes/grwait.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/oblib.h"
#include "aes/rect.h"
#include "aes/switch.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "aes/wrect.h"

_Static_assert(HOST_SLOT_AES_HCTL_WINDOW_SIZE_BYTES == HCTL_SIZE_BYTES
               && HOST_SLOT_AES_HCTL_WINDOW_CORNER_BYTES == HCTL_CORNER_BYTES, "hctl_window's two plain slots");
_Static_assert(HOST_SLOT_AES_HCTL_WINDOW_DRAG_RECT_BYTES == HOST_PROCESSES * HCTL_DRAG_RECT_BYTES
               && HOST_SLOT_AES_HCTL_WINDOW_DRAG_ANSWERS_BYTES == HOST_PROCESSES * HCTL_DRAG_ANSWER_BYTES
               && HCTL_DRAG_RECT_BYTES == GRECT_BYTES, "a drag's rectangle and its two answers: a frame per process");
_Static_assert(HOST_SLOT_AES_HCTL_RECT_CHOICE_BYTES == HOST_PROCESSES * HCTL_CHOICE_BYTES,
               "mn_do's two answers: a frame per process");
_Static_assert(HCTL_MESSAGE_SENT == 1 && WM_END_UPDATE == 0 && WM_BEG_UPDATE == 1, "the ROM's own words");

/* The left button as the AES last saw it — its record's low byte, bit 0 — read where the ROM tests it. */
static inline int left_button_is_down(const uint8_t *image)
{
    return image[AES_BUTTON + CT_BUTTON_LOW_BYTE] & CT_LEFT_BUTTON;
}

/* $fe456a — ct_msgup: `message` and its five words sent to the process `owner`, in the screen manager's own buffer —
 * nothing for no message — then the button waited up: a yield a turn while it is down. */
void aes_ct_msgup(uint8_t *image, int16_t message, int16_t owner, int16_t word3, int16_t word4, int16_t word5,
                  int16_t word6, int16_t word7)
{
    if (message != CT_NO_MESSAGE)
        (void)aes_ap_sendmsg(image, AES_CT_MESSAGE, message, owner, word3, word4, word5, word6, word7);
    while (left_button_is_down(image))
        aes_dsptch(image);
}

/* A window's rectangle as r_get unpacks it. */
struct window_size {
    int16_t x, y, w, h;
};

/* The id of the process that owns `window`: its record's PD, read for every message (as the ROM reads it). (The
 * record's read is `wmupdate.c`'s `window_owner` again — a file-local inline there, left where it is: sharing it
 * would touch a verified object for two lines.) */
static int16_t owner_of(const uint8_t *image, int16_t window)
{
    return (int16_t)bus_word(image, bus_long(image, window_record(window) + WIN_OWNER) + PD_PID);
}

static uint16_t kind_of(const uint8_t *image, int16_t window)
{
    return bus_word(image, window_record(window) + WIN_KIND);
}

/* $fe45e6..$fe461e — where `window` is: w_getsize's rectangle, unpacked by r_get. */
static struct window_size size_of(uint8_t *image, int16_t window)
{
    uint16_t size_local[FRAME_LOCAL_WORDS(HCTL_SIZE_BYTES)];
    uint32_t size = host_slot_claim(AES_HCTL_WINDOW_SIZE, size_local);
    struct window_size found;

    aes_w_getsize(image, WS_CURR, window, size + HCTL_SIZE_RECT);
    aes_r_get(image, size + HCTL_SIZE_RECT, size + HCTL_SIZE_X, size + HCTL_SIZE_Y, size + HCTL_SIZE_W, size + HCTL_SIZE_H);
    found.x = (int16_t)be16(image + size + HCTL_SIZE_X);
    found.y = (int16_t)be16(image + size + HCTL_SIZE_Y);
    found.w = (int16_t)be16(image + size + HCTL_SIZE_W);
    found.h = (int16_t)be16(image + size + HCTL_SIZE_H);
    host_slot_release(AES_HCTL_WINDOW_SIZE);
    return found;
}

/* $fe4636 — the closer or the fuller, watched until the button rises: its message if it rose inside the box (the box
 * drawn normal again), none otherwise. */
static int16_t box_watched(uint8_t *image, int16_t gadget)
{
    if (!aes_gr_watchbox(image, be32(image + AES_GL_AWIND), gadget, OB_STATE_SELECTED, HCTL_BOX_NORMAL))
        return CT_NO_MESSAGE;
    aes_ob_change(image, be32(image + AES_GL_AWIND), gadget, HCTL_BOX_NORMAL, OB_CHANGE_REDRAW);
    return gadget == W_CLOSER ? WM_CLOSED : WM_FULLED;
}

/* $fe4670 — the title of a window that has a MOVER: the window's outline dragged, kept on the screen below the menu
 * bar; where it was let go, into `at`. */
static int16_t title_dragged(uint8_t *image, int16_t window, struct window_size *at)
{
    uint16_t bound_local[GRECT_WORDS], corner_local[FRAME_LOCAL_WORDS(HCTL_DRAG_ANSWER_BYTES)];
    uint32_t bound, corner;
    int16_t right;

    if (!(kind_of(image, window) & WK_MOVER))
        return CT_NO_MESSAGE;
    bound = host_slot_claim_for(AES_HCTL_WINDOW_DRAG_RECT, bound_local, running_process_id(image));
    corner = host_slot_claim_for(AES_HCTL_WINDOW_DRAG_ANSWERS, corner_local, running_process_id(image));
    right = (int16_t)(be16(image + AES_GL_RSCREEN + GRECT_W) + at->w - global_word(image, AES_GL_WBOX) - HCTL_DRAG_TITLE_KEPT);
    aes_r_set(image, bound, HCTL_DRAG_LEFT, global_word(image, AES_GL_HBOX), right, HCTL_DRAG_NO_BOUND);
    aes_gr_dragbox(image, at->w, at->h, at->x, at->y, bound, corner + HCTL_DRAG_FIRST, corner + HCTL_DRAG_SECOND);
    at->x = (int16_t)be16(image + corner + HCTL_DRAG_FIRST);
    at->y = (int16_t)be16(image + corner + HCTL_DRAG_SECOND);
    host_slot_release_for(AES_HCTL_WINDOW_DRAG_ANSWERS, corner);
    host_slot_release_for(AES_HCTL_WINDOW_DRAG_RECT, bound);
    return WM_MOVED;
}

/* $fe46ea — the sizer of a window that has one: the window rubber-banded from its corner, no smaller than a character
 * cell — seven boxes along a side with a scroll bar — its work area's outline following; the new size into `at`. */
static int16_t corner_rubbered(uint8_t *image, int16_t window, uint16_t kind, struct window_size *at)
{
    uint16_t inset_local[GRECT_WORDS], size_local[FRAME_LOCAL_WORDS(HCTL_DRAG_ANSWER_BYTES)];
    uint32_t inset, size;
    int16_t min_width, min_height;

    if (!(kind & WK_SIZER))
        return CT_NO_MESSAGE;
    inset = host_slot_claim_for(AES_HCTL_WINDOW_DRAG_RECT, inset_local, running_process_id(image));
    size = host_slot_claim_for(AES_HCTL_WINDOW_DRAG_ANSWERS, size_local, running_process_id(image));
    aes_w_getsize(image, WS_WORK, window, inset);
    wr16(image + inset + GRECT_X, (uint16_t)(be16(image + inset + GRECT_X) - at->x));
    wr16(image + inset + GRECT_Y, (uint16_t)(be16(image + inset + GRECT_Y) - at->y));
    wr16(image + inset + GRECT_W, (uint16_t)(be16(image + inset + GRECT_W) - at->w));
    wr16(image + inset + GRECT_H, (uint16_t)(be16(image + inset + GRECT_H) - at->h));
    min_width = global_word(image, AES_GL_WCHAR);
    min_height = global_word(image, AES_GL_HCHAR);
    if (kind_of(image, window) & HCTL_HORIZONTAL_GADGETS)
        min_width = (int16_t)(global_word(image, AES_GL_WBOX) * HCTL_BAR_BOXES);
    if (kind_of(image, window) & HCTL_VERTICAL_GADGETS)
        min_height = (int16_t)(global_word(image, AES_GL_HBOX) * HCTL_BAR_BOXES);
    aes_gr_rubwind(image, at->x, at->y, min_width, min_height, inset, size + HCTL_DRAG_FIRST, size + HCTL_DRAG_SECOND);
    at->w = (int16_t)be16(image + size + HCTL_DRAG_FIRST);
    at->h = (int16_t)be16(image + size + HCTL_DRAG_SECOND);
    host_slot_release_for(AES_HCTL_WINDOW_DRAG_ANSWERS, size);
    host_slot_release_for(AES_HCTL_WINDOW_DRAG_RECT, inset);
    return WM_SIZED;
}

/* $fe4798 — a slider's TRACK pressed beside its elevator: the gadget numbered one further on where the mouse is at or
 * past the elevator's corner (the page after), as it is before it. */
static int16_t page_of(uint8_t *image, int16_t track, int16_t mouse_x, int16_t mouse_y)
{
    uint16_t corner_local[FRAME_LOCAL_WORDS(HCTL_CORNER_BYTES)];
    uint32_t corner = host_slot_claim(AES_HCTL_WINDOW_CORNER, corner_local);
    int16_t mouse, elevator;

    (void)aes_ob_offset(image, be32(image + AES_GL_AWIND), (int16_t)(track + 1), corner + HCTL_CORNER_X,
                        corner + HCTL_CORNER_Y);
    mouse = track == W_HSLIDE ? mouse_x : mouse_y;
    elevator = (int16_t)be16(image + corner + (track == W_HSLIDE ? HCTL_CORNER_X : HCTL_CORNER_Y));
    host_slot_release(AES_HCTL_WINDOW_CORNER);
    return mouse < elevator ? track : (int16_t)(track + HCTL_PAGE_AFTER);
}

/* $fe482c..$fe4896 — WM_ARROWED, repeated while the button is down: the screen's lock let go so the owner can
 * scroll; the message sent whenever the last one has been read (the reader clears AES_CTL_MESSAGE_SENT); a yield a
 * turn; the lock taken again. */
static void arrow_repeated(uint8_t *image, int16_t window, int16_t gadget, const struct window_size *at)
{
    int16_t action = (int16_t)bus_word(image, table_entry(AES_ARROW_ACTIONS, gadget - W_UPARROW, HCTL_ARROW_ACTION_BYTES));

    (void)aes_wm_update(image, WM_END_UPDATE);
    do {
        if (!be16(image + AES_CTL_MESSAGE_SENT)) {
            (void)aes_ap_sendmsg(image, AES_CT_MESSAGE, WM_ARROWED, owner_of(image, window), window, action, at->y,
                                 at->w, at->h);
            wr16(image + AES_CTL_MESSAGE_SENT, HCTL_MESSAGE_SENT);
        }
        aes_dsptch(image);
    } while (left_button_is_down(image));
    (void)aes_wm_update(image, WM_BEG_UPDATE);
}

/* $fe45a2 — hctl_window: a press at (`mouse_x`, `mouse_y`) on `window`. */
void aes_hctl_window(uint8_t *image, int16_t window, int16_t mouse_x, int16_t mouse_y)
{
    struct window_size at = { HCTL_STALE_WORD, HCTL_STALE_WORD, HCTL_STALE_WORD, HCTL_STALE_WORD };
    int16_t message = CT_NO_MESSAGE, gadget;
    uint16_t kind;

    if (window != global_word(image, AES_GL_WTOP)) {
        aes_ct_msgup(image, WM_TOPPED, owner_of(image, window), window, at.x, at.y, at.w, at.h);
        return;
    }
    aes_w_bldactive(image, window);
    gadget = aes_ob_find(image, be32(image + AES_GL_AWIND), W_BOX, HCTL_FIND_DEPTH, mouse_x, mouse_y);
    at = size_of(image, window);
    kind = kind_of(image, window);
    switch (gadget) {
    case W_CLOSER:
    case W_FULLER:
        message = box_watched(image, gadget);
        break;
    case W_NAME:
        message = title_dragged(image, window, &at);
        break;
    case W_SIZER:
        message = corner_rubbered(image, window, kind, &at);
        break;
    case W_VSLIDE:
    case W_HSLIDE:
        gadget = page_of(image, gadget, mouse_x, mouse_y);
        message = WM_ARROWED;
        break;
    case W_UPARROW:
    case W_DNARROW:
    case W_LFARROW:
    case W_RTARROW:
        message = WM_ARROWED;
        break;
    case W_VELEV:
    case W_HELEV:
        message = gadget == W_HELEV ? WM_HSLID : WM_VSLID;
        at.x = aes_gr_slidebox(image, be32(image + AES_GL_AWIND), (int16_t)(gadget - 1), gadget, gadget == W_VELEV);
        break;
    default:
        break;
    }
    if (message == WM_ARROWED) {
        arrow_repeated(image, window, gadget, &at);
        return;
    }
    aes_ct_msgup(image, message, owner_of(image, window), window, at.x, at.y, at.w, at.h);
}

/* $fe48ce — hctl_button: a button the menu bar posted for itself (mn_bar counts each in gl_mnclicks) is counted off
 * and swallowed; any other goes to the window under the mouse, unless that is the desktop or nothing. */
void aes_hctl_button(uint8_t *image, int16_t mouse_x, int16_t mouse_y)
{
    int16_t window;

    if (be16(image + AES_GL_MNCLICKS)) {
        wr16(image + AES_GL_MNCLICKS, (uint16_t)(be16(image + AES_GL_MNCLICKS) - 1));
        return;
    }
    window = aes_wm_find(image, mouse_x, mouse_y);
    if (window > WM_DESKTOP)
        aes_hctl_window(image, window, mouse_x, mouse_y);
}

/* $fe4940..$fe4996 — is the choice (`title`, `item`) an accessory's entry of the desk menu: with one registered, the
 * first title, an item from gl_dafirst on. */
static int is_an_accessory_s(const uint8_t *image, int16_t title, int16_t item)
{
    return be16(image + AES_GL_DACNT) && title == HCTL_DESK_TITLE && item >= global_word(image, AES_GL_DAFIRST);
}

/* $fe4908 — hctl_rect: the mouse at (`mouse_x`, `mouse_y`) came onto the bar. With a menu shown and the point on
 * its titles the menu is worked; a choice is sent on — an accessory's entry as AC_OPEN to that accessory, its index
 * among the accessories in place of the item and the title drawn normal again; any other as MN_SELECTED to the
 * process word gl_mnppd's longword BEGINS with (its high word: 0 for every process id) — and the button waited up. */
void aes_hctl_rect(uint8_t *image, int16_t mouse_x, int16_t mouse_y)
{
    uint16_t choice_local[FRAME_LOCAL_WORDS(HCTL_CHOICE_BYTES)];
    uint32_t choice;
    int16_t message = CT_NO_MESSAGE, owner = HCTL_STALE_WORD, title = HCTL_STALE_WORD, item = HCTL_STALE_WORD;

    if (!be32(image + AES_GL_MNTREE) || !aes_inside(image, mouse_x, mouse_y, AES_GL_CTWAIT_RECT))
        return;
    choice = host_slot_claim_for(AES_HCTL_RECT_CHOICE, choice_local, running_process_id(image));
    if (aes_mn_do(image, choice + HCTL_CHOICE_TITLE, choice + HCTL_CHOICE_ITEM)) {
        title = (int16_t)be16(image + choice + HCTL_CHOICE_TITLE);
        item = (int16_t)be16(image + choice + HCTL_CHOICE_ITEM);
        if (is_an_accessory_s(image, title, item)) {
            item = (int16_t)(item - global_word(image, AES_GL_DAFIRST));
            owner = (int16_t)bus_word(image, table_entry(AES_DESK_PID, item, HCTL_DESK_PID_BYTES));
            (void)aes_do_chg(image, be32(image + AES_GL_MNTREE), title, MN_SELECTED, MN_CLEAR, MN_REDRAW, MN_CHECK_DISABLED);
            message = AC_OPEN;
        } else {
            owner = global_word(image, AES_GL_MNPPD);
            message = MN_SELECTED_MESSAGE;
        }
    }
    host_slot_release_for(AES_HCTL_RECT_CHOICE, choice);
    aes_ct_msgup(image, message, owner, title, item, 0, 0, 0);
}
