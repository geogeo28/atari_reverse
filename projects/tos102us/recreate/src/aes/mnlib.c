/* mnlib.c — the MENU LIBRARY (`aes/mnlib.h`): a menu object's rectangle into a mouse wait (rect_change), a title or an
 * item's state changed and drawn (do_chg, menu_set), a drop-down saved and drawn (menu_sr, menu_down), the mouse
 * tracked through the bar until a click (mn_do), the bar shown or hidden (mn_bar), the accessories closed and
 * registered (mn_clsda, mn_register), and the scheduler's leaf that names a process (pd_nameit). Alcyon C in the ROM.
 *
 * The EVENT LAYER mn_do and mn_bar reach — ev_multi, post_button — and ap_rdwr under mn_clsda's ap_sendmsg are the event
 * door's (`aes/evdoor.h`). Every object word is read through the tree's pointer on the 24-bit bus (`aes/objects.h`),
 * every global re-read where the ROM re-reads it, every word sum a word that wraps and every compare signed, as the
 * ROM's `add.w` / `cmp.w`.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/ctrl.h"
#include "aes/evdoor.h"
#include "aes/gemgraf.h"
#include "aes/gsxif.h"
#include "aes/mnlib.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/rect.h"
#include "aes/strings.h"

#define DISABLED              (1 << OB_STATE_DISABLED_BIT)      /* do_chg's `btst #3,d5` ($fe8c3e)            */
#define FIND_DEPTH            1          /* mn_do's ob_find: the titles, or a menu's items ($fe8eca, $fe8f1e)  */
#define MN_DO_NONE            0          /* ev_multi's timer and message: none ($fe8e6c, $fe8e72 clr.l)        */
#define MN_DO_CHOSEN          1          /* mn_do's answer: a title and item chosen ($fe8ffc move.w #1)        */
/* The button wait a pass hands ev_multi: one click of the left button, down or up (`aes/mnlib.h`). */
#define BUTTON_WAIT(state)    EV_BUTTON_PARAMETER(1, EV_BUTTON_LEFT, state)
/* gsx_button's bit mn_do reads on an item: the left button ($fe8e16 andi.w #1). */
#define LEFT_BUTTON_BIT       1

_Static_assert(MN_SELECTED == 1 << OB_STATE_SELECTED_BIT, "SELECTED, the bit menu_set changes");
_Static_assert(MN_MESSAGE_BYTES == AP_MSG_BYTES, "the screen manager's message buffer holds one message");
_Static_assert(MN_DO_FIRST_RECT + EV_MOBLK_WORDS * sizeof(uint16_t) == MN_DO_FRAME_WORDS * sizeof(uint16_t),
               "mn_do's answers and two MOBLKs fill its frame slot");

/* $fe8bf4 — the rectangle of `object` on the screen into the MOBLK at `moblk`, then the MOBLK's leave flag. */
void aes_rect_change(uint8_t *image, uint32_t tree, uint32_t moblk, int16_t object, int16_t leave)
{
    aes_ob_actxywh(image, tree, object, moblk + EV_MOBLK_RECT);
    set_bus_word(image, moblk + EV_MOBLK_LEAVE, (uint16_t)leave);
}

/* $fe8c14 — `bits` of `item`'s state set or cleared, and the item changed by ob_change (drawn, under no clip, when
 * `redraw`): 1; or, `check_disabled` and the item DISABLED, nothing and 0. */
int16_t aes_do_chg(uint8_t *image, uint32_t tree, int16_t item, uint16_t bits, int16_t set, int16_t redraw,
                   int16_t check_disabled)
{
    uint16_t state = (uint16_t)object_word(image, tree, item, OB_STATE);

    if (check_disabled && state & DISABLED)
        return 0;
    state = set ? state | bits : state & (uint16_t)~bits;
    if (redraw)
        aes_gsx_sclip(image, AES_GL_RZERO);
    aes_ob_change(image, tree, item, (int16_t)state, redraw);
    return 1;
}

/* $fe8c7a — `last` selected or deselected (`set`), unless it is none or `current` itself: do_chg's answer, else 0. */
int16_t aes_menu_set(uint8_t *image, uint32_t tree, int16_t last, int16_t current, int16_t set)
{
    if (last == OB_NIL || last == current)
        return 0;
    return aes_do_chg(image, tree, last, MN_SELECTED, set, MN_REDRAW, MN_CHECK_DISABLED);
}

/* $fe8cb6 — the screen under drop-down `menu` saved (`save`) or put back, its rectangle one pixel wider on the left
 * and two wider and taller (the shadow) — under no clip. */
void aes_menu_sr(uint8_t *image, int16_t save, uint32_t tree, int16_t menu)
{
    uint16_t rect_local[GRECT_WORDS];
    _Static_assert(sizeof rect_local == HOST_SLOT_AES_MENU_SR_RECT_BYTES, "menu_sr's GRECT, its slot");
    uint32_t rect = host_slot_claim(AES_MENU_SR_RECT, rect_local);

    aes_gsx_sclip(image, AES_GL_RZERO);
    aes_ob_actxywh(image, tree, menu, rect);
    wr16(image + rect + GRECT_X, (uint16_t)(be16(image + rect + GRECT_X) - MN_SR_LEFT_EDGE));
    wr16(image + rect + GRECT_W, (uint16_t)(be16(image + rect + GRECT_W) + MN_SR_SHADOW));
    wr16(image + rect + GRECT_H, (uint16_t)(be16(image + rect + GRECT_H) + MN_SR_SHADOW));
    if (save)
        aes_bb_save(image, rect);
    else
        aes_bb_restore(image, rect);
    host_slot_release(AES_MENU_SR_RECT);
}

/* $fe8cf4 — title `title` dropped: its drop-down found (the first one's `title - 3`-th sibling), the title selected
 * and, if it was not DISABLED, the screen under the drop-down saved and the drop-down drawn. The drop-down's index. */
int16_t aes_menu_down(uint8_t *image, uint32_t tree, int16_t title)
{
    int16_t menu = object_word(image, tree, object_word(image, tree, OB_ROOT, OB_TAIL), OB_HEAD);
    int16_t step;

    for (step = (int16_t)(title - MN_DOWN_WALK_FROM); step > MN_DOWN_WALK_UNTIL; step--)
        menu = object_word(image, tree, menu, OB_NEXT);
    if (aes_do_chg(image, tree, title, MN_SELECTED, MN_SET, MN_REDRAW, MN_CHECK_DISABLED)) {
        aes_menu_sr(image, 1, tree, menu);
        aes_ob_draw(image, tree, menu, MN_DRAW_DEPTH);
    }
    return menu;
}

/* mn_do's tracking across its passes: the tree and the frame slot's three addresses, where the mouse was last seen
 * (`aes/mnlib.h`'s MN_IN_BAR...), the dropped title, the item under the mouse, the dropped menu, the button wait. */
struct menu_track {
    uint32_t tree, first, second, answers;
    int16_t state, done, title, item, menu;
    uint32_t button;
};

/* One pass's wait ($fe8da0..$fe8e88): the first MOBLK the titles' box entered (on the bar, and off the dropped menu)
 * or the dropped title or the item left; the second, on the bar, the bar left, and off the menu the menu entered; the
 * button wait re-armed on an item. ev_multi's events back. */
static uint16_t menu_wait(uint8_t *image, struct menu_track *track)
{
    int16_t flags = EV_MU_BUTTON | EV_MU_M1, watched = MN_THEACTIVE, leave = 1;

    switch (track->state) {
    case MN_IN_BAR:
        leave = 0;
        flags |= EV_MU_M2;
        aes_rect_change(image, track->tree, track->second, MN_THEBAR, 1);
        break;
    case MN_ON_TITLE:
        watched = track->title;
        break;
    case MN_OUT_OF_MENU:
        leave = 0;
        flags |= EV_MU_M2;
        aes_rect_change(image, track->tree, track->second, track->menu, 0);
        break;
    case MN_IN_MENU:
        watched = track->item;
        track->button = BUTTON_WAIT(aes_gsx_button(image) & LEFT_BUTTON_BIT ? MN_BUTTON_UP : MN_BUTTON_DOWN);
        break;
    }
    aes_rect_change(image, track->tree, track->first, watched, leave);
    return evdoor_ev_multi(image, flags, track->first, track->second, MN_DO_NONE, track->button, MN_DO_NONE,
                           track->answers);
}

/* One pass's move ($fe8ebc..$fe8fae): where the mouse now is — a title not DISABLED alone, an item of the dropped menu,
 * off it, or off the bar — and the titles, items and drop-downs changed to show it. */
static void menu_move(uint8_t *image, struct menu_track *track)
{
    uint32_t mouse = bus_long(image, track->answers);
    int16_t last_title = track->title, last_item = track->item, last_menu = track->menu, state;

    track->title = aes_ob_find(image, track->tree, MN_THEACTIVE, FIND_DEPTH, pair_high(mouse), pair_low(mouse));
    state = object_word(image, track->tree, track->title, OB_STATE);
    if (track->title != OB_NIL && state != MN_DISABLED_ALONE) {
        track->item = OB_NIL;
        track->state = MN_ON_TITLE;
    } else {
        track->title = last_title;
        if (last_menu != OB_NIL) {
            track->item = aes_ob_find(image, track->tree, last_menu, FIND_DEPTH, pair_high(mouse), pair_low(mouse));
            track->state = track->item != OB_NIL ? MN_IN_MENU : MN_OUT_OF_MENU;
        } else {
            track->state = MN_IN_BAR;
            if (state != MN_DISABLED_ALONE)
                track->done = 1;
        }
    }
    aes_menu_set(image, track->tree, last_item, track->item, MN_CLEAR);
    if (aes_menu_set(image, track->tree, last_title, track->title, MN_CLEAR))
        aes_menu_sr(image, 0, track->tree, last_menu);
    if (aes_menu_set(image, track->tree, track->title, last_title, MN_SET))
        track->menu = aes_menu_down(image, track->tree, track->title);
    aes_menu_set(image, track->tree, track->item, last_item, MN_SET);
}

/* $fe8d6e — the mouse tracked through gl_mntree's bar and drop-downs until a click: 1, the title and item through
 * `title_out` / `item_out`, for an enabled item clicked (the title left selected); 0 for none. The mouse is the
 * AES's round it (ct_mouse). */
int16_t aes_mn_do(uint8_t *image, uint32_t title_out, uint32_t item_out)
{
    uint16_t frame_local[MN_DO_FRAME_WORDS];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_MN_DO_FRAME_BYTES, "mn_do's answers and MOBLKs, their slot");
    uint32_t frame = host_slot_claim(AES_MN_DO_FRAME, frame_local);
    struct menu_track track = {
        .tree = be32(image + AES_GL_MNTREE), .first = frame + MN_DO_FIRST_RECT, .second = frame + MN_DO_SECOND_RECT,
        .answers = frame + MN_DO_ANSWERS, .state = MN_IN_BAR, .done = 0, .title = OB_NIL, .item = OB_NIL,
        .menu = OB_NIL, .button = BUTTON_WAIT(MN_BUTTON_DOWN),
    };
    int16_t chosen = 0;

    aes_ct_mouse(image, CT_MOUSE_GRAB);
    while (!track.done) {
        if (menu_wait(image, &track) & EV_MU_BUTTON) {
            if (track.state != MN_ON_TITLE)
                track.done = 1;
            else
                track.button ^= MN_BUTTON_STATE_BIT;
        }
        if (!track.done)
            menu_move(image, &track);
    }
    if (track.title != OB_NIL) {
        aes_menu_sr(image, 0, track.tree, track.menu);
        if (track.item != OB_NIL
            && aes_do_chg(image, track.tree, track.item, MN_SELECTED, MN_CLEAR, MN_NO_REDRAW, MN_CHECK_DISABLED)) {
            set_bus_word(image, title_out, (uint16_t)track.title);
            set_bus_word(image, item_out, (uint16_t)track.item);
            chosen = MN_DO_CHOSEN;
        } else {
            aes_do_chg(image, track.tree, track.title, MN_SELECTED, MN_CLEAR, MN_REDRAW, MN_CHECK_DISABLED);
        }
    }
    aes_ct_mouse(image, CT_MOUSE_RELEASE);
    host_slot_release(AES_MN_DO_FRAME);
    return chosen;
}

/* mn_bar's desk menu ($fe9076..$fe913c): the box its items hang from found (the root's last child's first), emptied,
 * and the desk's own items and every registered accessory's — its text from AES_DESK_ACC — added back, the box as tall
 * as the items. The box's index is re-read from gl_dabox at every use. */
static void desk_menu(uint8_t *image, uint32_t tree)
{
    int16_t items = MN_DESK_ALONE, height = 0, item;

    wr16(image + AES_GL_DABOX, (uint16_t)object_word(image, tree, object_word(image, tree, OB_ROOT, OB_TAIL), OB_HEAD));
    set_object_word(image, tree, global_word(image, AES_GL_DABOX), OB_HEAD, OB_NIL);
    set_object_word(image, tree, global_word(image, AES_GL_DABOX), OB_TAIL, OB_NIL);
    if (global_word(image, AES_GL_DACNT)) {
        items = (int16_t)(global_word(image, AES_GL_DACNT) + MN_DESK_ITEMS);
        wr16(image + AES_GL_DAFIRST, (uint16_t)(global_word(image, AES_GL_DABOX) + MN_DAFIRST_PAST_BOX));
    }
    for (item = 1; item <= items; item++) {
        int16_t object = (int16_t)(item + global_word(image, AES_GL_DABOX));

        aes_ob_add(image, tree, global_word(image, AES_GL_DABOX), object);
        if (item > MN_DESK_ITEMS)
            set_bus_long(image, object_address(tree, object, OB_SPEC),
                         be32(image + table_entry(AES_DESK_ACC, item - (MN_DESK_ITEMS + 1), sizeof(uint32_t))));
        height = (int16_t)(height + global_word(image, AES_GL_HCHAR));
    }
    set_object_word(image, tree, global_word(image, AES_GL_DABOX), OB_HEIGHT, height);
}

/* $fe902a — the menu bar `tree` shown: the screen manager's wait set to its titles' box, whose menu it is (the running
 * process's id, a longword), the desk menu rebuilt, the bar drawn under no clip and the line under it; or none: the
 * wait set to the bar's whole rectangle. Then a fake click posted to the screen manager — counted so its button handler
 * swallows it — which wakes it to re-arm its wait. */
void aes_mn_bar(uint8_t *image, uint32_t tree, int16_t show)
{
    if (show) {
        int16_t line_y;

        wr32(image + AES_GL_MNTREE, tree);
        aes_ob_actxywh(image, tree, MN_THEACTIVE, AES_GL_CTWAIT_RECT);
        aes_rc_copy(image, AES_GL_CTWAIT_RECT, AES_GL_RMNACTV);
        wr32(image + AES_GL_MNPPD, (uint32_t)(int32_t)(int16_t)bus_word(image, running(image, PD_PID)));
        desk_menu(image, tree);
        aes_gsx_sclip(image, AES_GL_RZERO);
        aes_ob_draw(image, tree, MN_THEBAR, MN_DRAW_DEPTH);
        line_y = (int16_t)(global_word(image, AES_GL_HBOX) - 1);
        aes_gsx_cline(image, 0, line_y, (int16_t)(global_word(image, AES_GL_WIDTH) - 1), line_y);
    } else {
        wr32(image + AES_GL_MNTREE, 0);
        aes_rc_copy(image, AES_GL_RMENU, AES_GL_RMNACTV);
    }
    wr16(image + AES_GL_MNCLICKS, (uint16_t)(global_word(image, AES_GL_MNCLICKS) + 1));
    evdoor_post_button(image, be32(image + AES_CTL_PD), MN_BAR_BUTTON, MN_BAR_CLICKS);
}

/* $fe91a4 — AC_CLOSE sent to every registered accessory, its slot's index the message's first word. */
void aes_mn_clsda(uint8_t *image)
{
    int16_t slot;

    for (slot = 0; slot < global_word(image, AES_GL_DACNT); slot++)
        aes_ap_sendmsg(image, AES_CT_MESSAGE, MN_AC_CLOSE, global_word(image, word_entry(AES_DESK_PID, slot)), slot,
                       0, 0, 0, 0);
}

/* $fe91e2 — `pid` -1: the running process named `name` (copied into the frame first), 1; any other: an accessory's
 * slot taken — its process id and its item's text — and its index answered, or -1 when all six are taken. */
int16_t aes_mn_register(uint8_t *image, int16_t pid, uint32_t name)
{
    if (pid == MN_REGISTER_PROCESS) {
        uint8_t copy_local[MN_REGISTER_NAME_BYTES];
        _Static_assert(sizeof copy_local == HOST_SLOT_AES_MN_REGISTER_NAME_BYTES, "mn_register's copy, its slot");
        uint32_t copy = host_slot_claim(AES_MN_REGISTER_NAME, copy_local);

        aes_lstcpy(image, copy, name);
        aes_pd_nameit(image, be32(image + AES_RLR), copy);
        host_slot_release(AES_MN_REGISTER_NAME);
        return MN_REGISTER_NAMED;
    }
    if (global_word(image, AES_GL_DACNT) >= MN_DA_SLOTS)
        return MN_REGISTER_FULL;
    wr16(image + word_entry(AES_DESK_PID, global_word(image, AES_GL_DACNT)), (uint16_t)pid);
    wr32(image + table_entry(AES_DESK_ACC, global_word(image, AES_GL_DACNT), sizeof(uint32_t)), name);
    wr16(image + AES_GL_DACNT, (uint16_t)(global_word(image, AES_GL_DACNT) + 1));
    return (int16_t)(global_word(image, AES_GL_DACNT) - 1);
}

/* $fe5856 — `pd`'s name blank-filled, then `name` copied into it up to its extension's dot. */
void aes_pd_nameit(uint8_t *image, uint32_t pd, uint32_t name)
{
    aes_bfill(image, PD_NAME_BYTES, PD_NAME_FILL, pd + PD_NAME);
    aes_strscn(image, name, pd + PD_NAME, PD_NAME_STOP);
}
