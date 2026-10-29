/* desktop.c — UNIT K, THE DESK'S MAIN LOOP'S HELPERS (`desk/desktop.h`): Alcyon C in the ROM, each ported over its own
 * order; every menu change through unit D's binding (`desk/deskbind.h`).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskleaf.h"
#include "aes/evdoor.h"
#include "aes/evmulti.h"
#include "aes/gemctrl.h"
#include "aes/gemdosif.h"
#include "aes/gemstart.h"
#include "aes/loader.h"
#include "aes/obedit.h"
#include "aes/objdraw.h"
#include "aes/rect.h"
#include "aes/gsxif.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
#include "desk/deskinf.h"
#include "desk/deskins.h"
#include "desk/deskleaf.h"
#include "desk/desksupp.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

_Static_assert(FIND_FRAME_BYTES == HOST_SLOT_AES_MEN_UPDATE_FIND_BYTES, "men_update's two answers and their host slot");
_Static_assert(CNX_GET_FRAME_BYTES == HOST_SLOT_AES_DESK_CNX_GET_FRAME_BYTES, "cnx_get's frame and its host slot");

static inline int16_t desk_word(const uint8_t *image, uint32_t desk, uint32_t field)
{
    return (int16_t)bus_word(image, desk + field);
}

/* $fe1c8c — men_list: menu_ienable of each item of the NUL-ended byte list, each item the SIGNED byte it is
 * (`move.b (a5)+,d0 / ext.w d0`: one of $80 or more is a word with its top bit set — the binding's "redraw the bar"). */
void aes_men_list(uint8_t *image, uint32_t tree, uint32_t items, int16_t enable)
{
    while (bus_byte(image, items) != 0)
        (void)aes_desk_menu_ienable(image, tree, (int16_t)(int8_t)bus_byte(image, items++), enable);
}

/* $fe1bf6 — i_find: on the desktop (window 0) the ANODE of the icon `item` — app_afind of a desktop icon, any type,
 * by its object and its name (win_iname); in a window the FNODE of `item` in its path's file list (fpd_ofind) and,
 * where there is one, the ANODE for its name — app_afind of no desktop icon, a folder's type where its attributes
 * say so, any object. The FNODE (0 on the desktop or where none) through `fnode_out`; app_afind's is-a-program
 * through `is_app_out`. The ANODE, or 0. */
uint32_t aes_i_find(uint8_t *image, int16_t window, int16_t item, uint32_t fnode_out, uint32_t is_app_out)
{
    uint32_t anode = ANODE_NONE, fnode = FNODE_NONE;

    if (window == DESKTOP_WINDOW) {
        anode = aes_app_afind(image, AFIND_ON_THE_DESKTOP, AFIND_ANY, item, aes_win_iname(image, item), is_app_out);
    } else {
        fnode = aes_fpd_ofind(image, bus_long(image, bus_long(image, aes_win_find(image, window) + WNODE_PATH) + PNODE_FLIST), item);
        if (fnode != FNODE_NONE)
            anode = aes_app_afind(image, AFIND_IN_A_WINDOW, (bus_byte(image, fnode + FNODE_ATTR) & FNODE_ATTR_SUBDIR) ? 1 : 0,
                                  AFIND_ANY, fnode + FNODE_NAME, is_app_out);
    }
    set_bus_long(image, fnode_out, fnode);
    return anode;
}

/* The items a selected icon cannot use, by its ANODE's type: a program's or a document's, a folder's, a floppy's or a
 * hard disk's (the letter's low byte, signed, past 'B'), the trash's, the cartridge's. A type past them keeps the list
 * the loop had (the ROM's frame word; no ANODE has one: app_parse's types are 0..4). */
static uint32_t not_for(const uint8_t *image, uint32_t anode, int16_t is_app, uint32_t list)
{
    switch (bus_word(image, anode + ANODE_TYPE)) {
    case AT_ISFILE:
        return is_app ? AES_MEN_APPLICATION : AES_MEN_DOCUMENT;
    case AT_ISFOLD:
        return AES_MEN_FOLDER;
    case AT_ISDISK:
        return (int8_t)bus_byte(image, anode + ANODE_LETTER + 1) > FLOPPY_LETTER_LAST ? AES_MEN_HARD_DISK : AES_MEN_FLOPPY;
    case AT_ISTRSH:
        return AES_MEN_TRASH;
    case AT_ISCART:
        return AES_MEN_CARTRIDGE;
    }
    return list;
}

/* $fe1cb6 — men_update: every item from 18 to 40 enabled, the separators disabled; for each icon selected under the
 * selection's root (win_isel), its ANODE's list disabled (i_find's two answers handed BY ADDRESS); the window items
 * by whether a window is on top — enabled where one is —, Close disabled where the top window's name is the root's;
 * and the none-selected or many-selected list where not exactly one is. */
void aes_men_update(uint8_t *image, uint32_t tree)
{
    uint32_t desk = desk_globals(image), list = AES_MEN_NEVER, top, found, anode;
    uint16_t found_local[FRAME_LOCAL_WORDS(FIND_FRAME_BYTES)];
    int16_t item, selected = 0;

    for (item = MENU_FIRST_ITEM; item <= MENU_LAST_ITEM; item++)
        (void)aes_desk_menu_ienable(image, tree, item, MENU_ITEM_ENABLED);
    aes_men_list(image, tree, AES_MEN_NEVER, MENU_ITEM_DISABLED);
    item = 0;
    while ((item = aes_win_isel(image, desk + DESK_G_SCREEN_OBJECTS, desk_word(image, desk, DESK_SELECTION_ROOT), item)) != 0) {
        found = host_slot_claim(AES_MEN_UPDATE_FIND, found_local);
        anode = aes_i_find(image, desk_word(image, desk, DESK_SELECTION_WINDOW), item, found + FIND_FNODE, found + FIND_IS_APP);
        list = not_for(image, anode, (int16_t)be16(image + found + FIND_IS_APP), list);
        host_slot_release(AES_MEN_UPDATE_FIND);
        aes_men_list(image, tree, list, MENU_ITEM_DISABLED);
        selected++;
    }
    list = aes_win_ontop(image) ? AES_MEN_A_WINDOW : AES_MEN_NO_WINDOW;
    aes_men_list(image, tree, list, list == AES_MEN_A_WINDOW ? MENU_ITEM_ENABLED : MENU_ITEM_DISABLED);
    top = aes_win_ontop(image);
    if (top != 0)
        aes_men_list(image, tree, AES_MEN_CLOSE, aes_streq(image, top + WNODE_NAME, AES_DESK_ROOT_NAME) ? MENU_ITEM_DISABLED : MENU_ITEM_ENABLED);
    if (selected != 1)
        aes_men_list(image, tree, selected ? AES_MEN_MANY_SELECTED : AES_MEN_NONE_SELECTED, MENU_ITEM_DISABLED);
}

/* A View menu check moved from the item `field` names to `item`, which it then names. */
static void check_moved(uint8_t *image, uint32_t desk, uint32_t field, int16_t item)
{
    uint32_t menu = bus_long(image, desk + DESK_MENU_TREE);

    (void)aes_desk_menu_icheck(image, menu, desk_word(image, desk, field), 0);
    set_bus_word(image, desk + field, (uint16_t)item);
    (void)aes_desk_menu_icheck(image, bus_long(image, desk + DESK_MENU_TREE), item, 1);
}

/* $fe1f2a — do_viewmenu: a View item — icons or text, or a sort key; another item changes nothing. Where the view or
 * the sort is not what the desk has, the changed one's check moved to the item, and the windows made again in the
 * new view and sort (win_view). 0. */
int16_t aes_do_viewmenu(uint8_t *image, int16_t item)
{
    uint32_t desk = desk_globals(image);
    int16_t view = desk_word(image, desk, DESK_G_IVIEW), sort = desk_word(image, desk, DESK_G_ISORT);

    switch (item) {
    case VIEW_ITEM_ICONS: view = V_ICON; break;
    case VIEW_ITEM_TEXT: view = V_TEXT; break;
    case SORT_ITEM_NAME: sort = SORT_BY_NAME; break;
    case SORT_ITEM_DATE: sort = SORT_BY_DATE; break;
    case SORT_ITEM_SIZE: sort = SORT_BY_SIZE; break;
    case SORT_ITEM_TYPE: sort = SORT_BY_TYPE; break;
    }
    if (view == desk_word(image, desk, DESK_G_IVIEW) && sort == desk_word(image, desk, DESK_G_ISORT))
        return VIEWMENU_DONE;
    if (view != desk_word(image, desk, DESK_G_IVIEW))
        check_moved(image, desk, DESK_VIEW_ITEM, item);
    if (sort != desk_word(image, desk, DESK_G_ISORT))
        check_moved(image, desk, DESK_SORT_ITEM, item);
    aes_win_view(image, view, sort);
    return VIEWMENU_DONE;
}

/* $fe2536 — cnx_put: g_cnxsave's view and sort (their items less the first's), the three preferences, the resolution
 * from 0; then each of the four WNODEs in turn (win_ith, from 1) that has a GEM window, packed into the next entry —
 * its current rectangle (wind_get WF_CXYWH, then do_xyfix of its corner), its scroll, its icon and its path; the
 * entries left over emptied (path and icon). */
void aes_cnx_put(uint8_t *image)
{
    uint32_t desk = desk_globals(image), wnode, entry;
    int16_t level, saved = 0, preference;

    set_bus_word(image, desk + DESK_CNX_VIEW, (uint16_t)(desk_word(image, desk, DESK_VIEW_ITEM) - VIEW_ITEM_ICONS));
    set_bus_word(image, desk + DESK_CNX_SORT, (uint16_t)(desk_word(image, desk, DESK_SORT_ITEM) - SORT_ITEM_NAME));
    for (preference = 0; preference < PREFERENCE_WORDS; preference++)
        set_bus_word(image, desk + DESK_CNX_PREFERENCES + 2 * (uint32_t)preference,
                     bus_word(image, desk + DESK_PREFERENCES + 2 * (uint32_t)preference));
    set_bus_word(image, desk + DESK_CNX_RESOLUTION, (uint16_t)(be16(image + AES_GL_RESTYPE) - 1));
    for (level = 0; level < DESK_WINDOWS; level++) {
        wnode = aes_win_ith(image, (int16_t)(level + 1));
        if (bus_word(image, wnode + WNODE_ID) == 0)
            continue;
        entry = desk + DESK_G_WINDOW_SAVES + (uint32_t)m68k_muls_w((uint16_t)saved++, WINDOW_SAVE_BYTES);
        (void)aes_desk_wind_get(image, (int16_t)bus_word(image, wnode + WNODE_ID), WF_CXYWH, entry + SAVE_X, entry + SAVE_Y,
                                entry + SAVE_W, entry + SAVE_H);
        aes_do_xyfix(image, entry + SAVE_X, entry + SAVE_Y);
        set_bus_word(image, entry + SAVE_CVCOL, bus_word(image, wnode + WNODE_CVCOL));
        set_bus_word(image, entry + SAVE_CVROW, bus_word(image, wnode + WNODE_CVROW));
        set_bus_word(image, entry + SAVE_OBID, bus_word(image, wnode + WNODE_OBID));
        (void)aes_strcpy(image, bus_long(image, wnode + WNODE_PATH) + PNODE_SPEC, entry + SAVE_PATH);
    }
    for (; saved < DESK_WINDOWS; saved++) {
        entry = desk + DESK_G_WINDOW_SAVES + (uint32_t)m68k_muls_w((uint16_t)saved, WINDOW_SAVE_BYTES);
        set_bus_byte(image, entry + SAVE_PATH, 0);
        set_bus_word(image, entry + SAVE_OBID, 0);
    }
}

/* ================================================================================================
 * BAND 6 WAVE 2 (group G3).
 * ============================================================================================= */

/* $fe22a6 — hndl_kbd (`desk/desktop.h`): Esc re-reads the window on top (fun_rebld); any other key nothing. 0. */
int16_t aes_hndl_kbd(uint8_t *image, int16_t key)
{
    uint32_t top;

    if (key == OB_EDIT_KEY_ESCAPE && (top = aes_win_ontop(image)) != 0)
        aes_desk_fun_rebld(image, top);
    return HNDL_KBD_DONE;
}

/* $fe2618 — cnx_get (`desk/desktop.h`). */
void aes_cnx_get(uint8_t *image)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(CNX_GET_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_CNX_GET_FRAME, frame_local), desk = desk_globals(image);
    uint32_t drive = frame + CNX_GET_FRAME_DRIVE;
    int16_t level, preference;

    (void)aes_do_viewmenu(image, (int16_t)(desk_word(image, desk, DESK_CNX_VIEW) + VIEW_ITEM_ICONS));
    (void)aes_do_viewmenu(image, (int16_t)(desk_word(image, desk, DESK_CNX_SORT) + SORT_ITEM_NAME));
    for (preference = 0; preference < PREFERENCE_WORDS; preference++)
        set_bus_word(image, desk + DESK_PREFERENCES + 2 * (uint32_t)preference,
                     bus_word(image, desk + DESK_CNX_PREFERENCES + 2 * (uint32_t)preference));
    (void)aes_desk_evnt_dclick(image, CNX_DCLICK_RATE, CNX_DCLICK_SET);
    wr16(image + GEM_START_WORD_890C, (uint16_t)(desk_word(image, desk, DESK_CNX_RESOLUTION) + CNX_RESOLUTION_BASE));
    for (level = 0; level < DESK_WINDOWS; level++) {
        uint32_t entry = desk + DESK_G_WINDOW_SAVES + (uint32_t)m68k_muls_w((uint16_t)level, WINDOW_SAVE_BYTES), window;

        if (!bus_byte(image, entry + SAVE_PATH))
            continue;
        window = aes_win_alloc(image, desk_word(image, entry, SAVE_OBID));
        if (!window)
            continue;
        set_bus_word(image, window + WNODE_CVCOL, bus_word(image, entry + SAVE_CVCOL));
        set_bus_word(image, window + WNODE_CVROW, bus_word(image, entry + SAVE_CVROW));
        aes_fpd_parse(image, entry + SAVE_PATH, drive, desk + DESK_G_1TEXT, frame + CNX_GET_FRAME_NAME, frame + CNX_GET_FRAME_EXT);
        aes_do_xyfix(image, entry + SAVE_X, entry + SAVE_Y);
        (void)aes_pro_chdir(image, (int16_t)be16(image + drive), desk + DESK_G_1TEXT);
        if (be16(image + AES_DOS_ERR))
            aes_win_free(image, window);
        else
            (void)aes_do_diropen(image, window, CNX_NEW_WINDOW, desk_word(image, entry, SAVE_OBID), (int16_t)be16(image + drive),
                                 desk + DESK_G_1TEXT, frame + CNX_GET_FRAME_NAME, frame + CNX_GET_FRAME_EXT, entry);
    }
    aes_cnx_put(image);
    host_slot_release(AES_DESK_CNX_GET_FRAME);
}

/* ==== BAND 6 W3a, STAGE 2: TWO MENUS' HANDLERS ========================================================================
 * COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1): no host twin, no Tier 1 — each held by its target-only rows
 * at the hands' arrivals (`test/test_desk_w3a_stage2.py`). */
#ifndef RECREATE_HOST_DIFFERENTIAL

/* Install Disk Drive's change shown: the desktop's icons made again (app_blddesk) and the desk's work area (wind_get of
 * window 0, into the handler's box) redrawn. */
static void the_desktop_rebuilt(uint8_t *image, uint32_t box)
{
    (void)aes_app_blddesk(image);
    (void)aes_desk_wind_get(image, DESKTOP_WORK_WINDOW, WF_WORKXYWH, box + OPTN_BOX_X, box + OPTN_BOX_Y, box + OPTN_BOX_W,
                            box + OPTN_BOX_H);
    aes_do_wredraw(image, DESKTOP_WORK_WINDOW, rect_word(image, box, OPTN_BOX_X), rect_word(image, box, OPTN_BOX_Y),
                   rect_word(image, box, OPTN_BOX_W), rect_word(image, box, OPTN_BOX_H));
}

/* Whether the alert `alert` (its default button the first) is OK'd: Save Desktop's and Print Screen's question. */
static int ok_asked(uint8_t *image, uint32_t alert)
{
    return aes_desk_form_alert(image, OPTN_ALERT_DEFAULT, alert) == OPTN_ALERT_OK;
}

/* The Blitter item: Blitmode through the ROM's trp14 door (its return site parked: `desk/deskleaf.h`'s idiom) set to
 * the opposite of the preference, which then flips and the item's check follows it. */
static void blitter_toggled(uint8_t *image, uint32_t desk)
{
    const uint16_t frame[] = {XBIOS_BLITMODE_FN, bus_word(image, desk + DESK_BLITTER_ON) ? 0 : 1};

    desk_xbios_parked(image, AES_OPTNMENU_BLITMODE_RETURN);
    (void)desk_xbios_trap(frame, sizeof frame / sizeof frame[0]);
    set_bus_word(image, desk + DESK_BLITTER_ON, bus_word(image, desk + DESK_BLITTER_ON) ? 0 : 1);
    (void)aes_desk_menu_icheck(image, bus_long(image, desk + DESK_MENU_TREE), OPTN_BLITTER,
                               (int16_t)bus_word(image, desk + DESK_BLITTER_ON));
}

/* $fe1fde — do_optnmenu (`desk/desktop.h`). The selection read first, whatever the item: the root's box (get_xywh, into
 * the frame wind_get later answers into) and its first selected icon's ANODE and FNODE (i_find's answers BY ADDRESS;
 * none selected, no ANODE — the ROM's register keeps its caller's then, on an arm no menu enables). */
int16_t aes_do_optnmenu(uint8_t *image, int16_t item)
{
    uint16_t box_local[FRAME_LOCAL_WORDS(OPTN_BOX_BYTES)], found_local[FRAME_LOCAL_WORDS(FIND_FRAME_BYTES)];
    uint32_t box = desk_local_address(box_local), found = desk_local_address(found_local), desk = desk_globals(image);
    uint32_t anode = ANODE_NONE;
    int16_t root = desk_word(image, desk, DESK_SELECTION_ROOT), selected, done = MENU_NOTHING_DONE;

    aes_get_xywh(image, screen_objects(image), root, box + OPTN_BOX_X, box + OPTN_BOX_Y, box + OPTN_BOX_W, box + OPTN_BOX_H);
    selected = aes_win_isel(image, screen_objects(image), desk_word(image, desk, DESK_SELECTION_ROOT), 0);
    if (selected)
        anode = aes_i_find(image, desk_word(image, desk, DESK_SELECTION_WINDOW), selected, found + FIND_FNODE, found + FIND_IS_APP);
    switch (item) {
    case OPTN_INSTALL_DISK:
        if (anode != ANODE_NONE && aes_desk_ins_disk(image, anode))
            the_desktop_rebuilt(image, box);
        break;
    case OPTN_INSTALL_APP:
        if (anode != ANODE_NONE && be16(image + found + FIND_IS_APP)
            && aes_desk_ins_app(image, be32(image + found + FIND_FNODE) + FNODE_NAME, anode)) {
            aes_desk_wait(image, DESK_WAIT_BUSY);
            aes_win_bdall(image);
            aes_win_shwall(image);
            aes_desk_wait(image, DESK_WAIT_DONE);
        }
        break;
    case OPTN_PREFERENCES:
        done = aes_desk_inf_pref(image);
        break;
    case OPTN_SAVE_DESKTOP:
        if (ok_asked(image, AES_SAVE_DESKTOP_ALERT)) {
            aes_desk_wait(image, DESK_WAIT_BUSY);
            aes_cnx_put(image);
            aes_app_save(image, APP_SAVE_TO_DISK);
            aes_desk_wait(image, DESK_WAIT_DONE);
        }
        break;
    case OPTN_PRINT_SCREEN:
        if (ok_asked(image, AES_PRINT_SCREEN_ALERT)) {
            aes_desk_wait(image, DESK_WAIT_BUSY);
            aes_gsx_hardcopy(image);
            aes_desk_wait(image, DESK_WAIT_DONE);
        }
        break;
    case OPTN_BLITTER:
        blitter_toggled(image, desk);
        break;
    }
    return done;
}

/* $fe1e4c — do_deskmenu (`desk/desktop.h`). */
int16_t aes_do_deskmenu(uint8_t *image, int16_t item)
{
    uint32_t tree;

    if (item == DESK_INFO_ITEM) {
        tree = bus_long(image, desk_globals(image) + DESK_ABOUT_TREE);
        (void)aes_desk_inf_show(image, tree, OB_ROOT);
        set_object_word(image, tree, ABOUT_OK, OB_STATE, 0);
    }
    return MENU_NOTHING_DONE;
}

/* ==== BAND 6 W3a, STAGE 3: THE DESK'S THREE DISPATCHERS AND THE FILE MENU ===============================================
 * COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1): no host twin, no Tier 1 — each held by its target-only rows
 * at the hands' arrivals (`test/test_desk_w3a_stage3.py`). hndl_msg is THE CYCLE'S BACK-EDGE's callee: inf_show calls it
 * as the C it is (`desk/deskinf.h`), no call through the table left. */

/* $fe1e80 — do_filemenu (`desk/desktop.h`). The window on top and the first icon selected read first, whatever the
 * item. */
int16_t aes_do_filemenu(uint8_t *image, int16_t item)
{
    uint32_t desk = desk_globals(image), top = aes_win_ontop(image);
    int16_t selected = aes_win_isel(image, screen_objects(image), desk_word(image, desk, DESK_SELECTION_ROOT), 0);

    switch (item) {
    case FILE_ITEM_OPEN:
        return selected ? aes_do_open(image, selected) : FILEMENU_NOTHING_DONE;
    case FILE_ITEM_SHOW_INFO:
        return selected ? aes_do_info(image, selected) : FILEMENU_NOTHING_DONE;
    case FILE_ITEM_NEW_FOLDER:
        if (top) {
            (void)aes_desk_fun_mkdir(image, top);
            aes_desk_clear(image, DESKTOP_WINDOW);
        }
        break;
    case FILE_ITEM_CLOSE:
    case FILE_ITEM_CLOSE_WINDOW:
        if (top) {
            aes_desk_clear(image, desk_word(image, desk, DESK_SELECTION_WINDOW));
            (void)aes_fun_close(image, top, item == FILE_ITEM_CLOSE ? FUN_CLOSE_A_FOLDER : FUN_CLOSE_THE_WINDOW);
        }
        break;
    case FILE_ITEM_FORMAT:
        return selected ? aes_desk_do_format(image, selected) : FILEMENU_NOTHING_DONE;
    }
    return FILEMENU_NOTHING_DONE;
}

/* $fe22ce — hndl_menu (`desk/desktop.h`). */
int16_t aes_hndl_menu(uint8_t *image, int16_t title, int16_t item)
{
    int16_t done = MENU_NOTHING_DONE;

    switch (title) {
    case MENU_TITLE_DESK:
        done = aes_do_deskmenu(image, item);
        break;
    case MENU_TITLE_FILE:
        done = aes_do_filemenu(image, item);
        break;
    case MENU_TITLE_VIEW:
        done = aes_do_viewmenu(image, item);
        aes_desk_wait(image, DESK_WAIT_BUSY);
        aes_win_srtall(image);
        aes_win_bdall(image);
        aes_win_shwall(image);
        aes_desk_wait(image, DESK_WAIT_DONE);
        break;
    case MENU_TITLE_OPTIONS:
        done = aes_do_optnmenu(image, item);
        break;
    }
    (void)aes_desk_menu_tnormal(image, bus_long(image, desk_globals(image) + DESK_MENU_TREE), title, MENU_TITLE_NORMAL);
    return done;
}

static inline int16_t message_word(const uint8_t *image, uint32_t desk, uint32_t field)
{
    return desk_word(image, desk, DESK_G_RMSG + field);
}

/* WM_TOPPED: the window put on top (wind_set WF_TOP), its work area asked (into this frame, read by no one), its WNODE
 * made the top one (win_top), verified and kept as the last window. A ROUTINE OF ITS OWN (`noinline`, PD0): the box is
 * no frame of hndl_msg's under MN_SELECTED's menus. */
__attribute__((noinline)) static void window_topped(uint8_t *image, uint32_t desk, int16_t handle)
{
    uint16_t box_local[FRAME_LOCAL_WORDS(GRECT_BYTES)];
    uint32_t box = desk_local_address(box_local), window;

    (void)aes_desk_wind_set(image, handle, WF_TOP, TOPPED_ZERO, TOPPED_ZERO, TOPPED_ZERO, TOPPED_ZERO);
    (void)aes_desk_wind_get(image, handle, WF_WORKXYWH, box + GRECT_X, box + GRECT_Y, box + GRECT_W, box + GRECT_H);
    window = aes_win_find(image, handle);
    aes_win_top(image, window);
    aes_desk_verify(image, (int16_t)bus_word(image, window + WNODE_ID), DESK_VERIFY_UNCHANGED);
    set_bus_word(image, desk + DESK_G_WLASTSEL, bus_word(image, window + WNODE_ID));
}

/* WM_SIZED / WM_MOVED: the message's rectangle, its corner on do_xyfix's column, made the window's (wind_set
 * WF_CURRXYWH); sized, the window verified as changed; moved, its root object put on its new work area (wind_get into
 * the same box, r_set). A ROUTINE OF ITS OWN (`noinline`) for `window_topped`'s reason. */
__attribute__((noinline)) static void window_placed(uint8_t *image, uint32_t desk, int16_t type)
{
    uint16_t box_local[FRAME_LOCAL_WORDS(GRECT_BYTES)];
    uint32_t box = desk_local_address(box_local), window;
    int16_t handle = message_word(image, desk, RMSG_HANDLE);

    lay_rect(image, box, message_word(image, desk, RMSG_X), message_word(image, desk, RMSG_Y), message_word(image, desk, RMSG_W),
             message_word(image, desk, RMSG_H));
    aes_do_xyfix(image, box + GRECT_X, box + GRECT_Y);
    (void)aes_desk_wind_set(image, handle, WF_CURRXYWH, rect_word(image, box, GRECT_X), rect_word(image, box, GRECT_Y),
                            rect_word(image, box, GRECT_W), rect_word(image, box, GRECT_H));
    if (type == WM_SIZED) {
        aes_desk_verify(image, handle, DESK_VERIFY_CHANGED);
        return;
    }
    (void)aes_desk_wind_get(image, handle, WF_WORKXYWH, box + GRECT_X, box + GRECT_Y, box + GRECT_W, box + GRECT_H);
    window = aes_win_find(image, handle);
    aes_r_set(image, object_address(screen_objects(image), (int16_t)bus_word(image, window + WNODE_ROOT), OB_X),
              rect_word(image, box, GRECT_X), rect_word(image, box, GRECT_Y), rect_word(image, box, GRECT_W),
              rect_word(image, box, GRECT_H));
}

/* A window's message (WM_REDRAW .. WM_MOVED) handled: whether the INF's windows are to be kept after it (cnx_put). */
static int window_message_handled(uint8_t *image, uint32_t desk, int16_t type)
{
    int16_t handle = message_word(image, desk, RMSG_HANDLE), value = message_word(image, desk, RMSG_X);

    switch (type) {
    case WM_REDRAW:
        if (handle != REDRAW_NO_WINDOW)
            aes_do_wredraw(image, handle, value, message_word(image, desk, RMSG_Y), message_word(image, desk, RMSG_W),
                           message_word(image, desk, RMSG_H));
        return 0;
    case WM_TOPPED:
        window_topped(image, desk, handle);
        return 0;
    case WM_CLOSED:
        (void)aes_do_filemenu(image, FILE_ITEM_CLOSE);
        return 1;
    case WM_FULLED:
        aes_do_wfull(image, handle);
        aes_desk_verify(image, handle, DESK_VERIFY_CHANGED);
        return 1;
    case WM_ARROWED:
        aes_win_arrow(image, handle, value);
        return 0;
    case WM_HSLID:
        aes_win_slide(image, handle, value, SLIDE_HORIZONTAL);
        return 0;
    case WM_VSLID:
        aes_win_slide(image, handle, value, SLIDE_VERTICAL);
        return 0;
    case WM_SIZED:
    case WM_MOVED:
        window_placed(image, desk, type);
        return 1;
    }
    return 0;
}

/* $fe2344 — hndl_msg (`desk/desktop.h`). The message's type read once, as the ROM's two switches read the same word. */
int16_t aes_hndl_msg(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    int16_t type = message_word(image, desk, RMSG_TYPE), done = HNDL_MSG_NOTHING_DONE;

    if (type >= WM_REDRAW && type <= WM_MOVED) {
        aes_desk_clear(image, desk_word(image, desk, DESK_SELECTION_WINDOW));
        if (window_message_handled(image, desk, type))
            aes_cnx_put(image);
    } else if (type == MN_SELECTED_MESSAGE) {
        aes_desk_verify(image, desk_word(image, desk, DESK_G_WLASTSEL), DESK_VERIFY_UNCHANGED);
        done = aes_hndl_menu(image, message_word(image, desk, RMSG_TITLE), message_word(image, desk, RMSG_ITEM));
    }
    set_bus_word(image, desk + DESK_G_RMSG + RMSG_TYPE, 0);
    aes_men_update(image, bus_long(image, desk + DESK_MENU_TREE));
    return done;
}

/* hndl_button's one click: the click handed act_bsclick (the selection's window, the screen, its root) over the work
 * area of `window`; then the button read again (graf_mkstate, its mouse and keys into one discarded word) INTO `button`
 * — the ROM's `14(a6)`, its own argument slot, here this routine's copy of it — and, still down, the drag act_bdown
 * makes (the object dragged into `object`). Where it was let go — a window's handle, 0 the desktop —, or
 * BDOWN_NOTHING_DRAGGED. A ROUTINE OF ITS OWN (`noinline`, PD0): its box and words are no frame under the drag's act
 * (fun_drag, its copy) or under two clicks' opener. */
__attribute__((noinline)) static int16_t one_click(uint8_t *image, uint32_t desk, int16_t window, int16_t x, int16_t y,
                                                  int16_t button, int16_t keys, uint32_t object)
{
    uint16_t box_local[FRAME_LOCAL_WORDS(GRECT_BYTES)], discard_local;
    uint32_t box = desk_local_address(box_local), discard = desk_local_address(&discard_local);

    (void)aes_desk_wind_get(image, window, WF_WORKXYWH, box + GRECT_X, box + GRECT_Y, box + GRECT_W, box + GRECT_H);
    aes_act_bsclick(image, desk_word(image, desk, DESK_SELECTION_WINDOW), bus_long(image, desk + DESK_G_SCREEN),
                    desk_word(image, desk, DESK_SELECTION_ROOT), x, y, keys, box, BSCLICK_ONE);
    aes_desk_graf_mkstate(image, discard, discard, desk_local_address(&button), discard);
    if (!(button & BUTTON_LEFT_DOWN))
        return BDOWN_NOTHING_DRAGGED;
    return aes_act_bdown(image, desk_word(image, desk, DESK_SELECTION_WINDOW), bus_long(image, desk + DESK_G_SCREEN),
                         desk_word(image, desk, DESK_SELECTION_ROOT), x, y, keys, box, object);
}

/* hndl_button's two clicks: the click handed act_bsclick as a double one, over the work area of `window`. A ROUTINE OF
 * ITS OWN (`noinline`) for `one_click`'s reason: the box is no frame under the opener that follows. */
__attribute__((noinline)) static void two_clicks(uint8_t *image, uint32_t desk, int16_t window, int16_t x, int16_t y,
                                                 int16_t keys)
{
    uint16_t box_local[FRAME_LOCAL_WORDS(GRECT_BYTES)];
    uint32_t box = desk_local_address(box_local);

    (void)aes_desk_wind_get(image, window, WF_WORKXYWH, box + GRECT_X, box + GRECT_Y, box + GRECT_W, box + GRECT_H);
    aes_act_bsclick(image, desk_word(image, desk, DESK_SELECTION_WINDOW), bus_long(image, desk + DESK_G_SCREEN),
                    desk_word(image, desk, DESK_SELECTION_ROOT), x, y, keys, box, BSCLICK_TWO);
}

/* $fe2172 — hndl_button (`desk/desktop.h`). */
int16_t aes_hndl_button(uint8_t *image, int16_t clicks, int16_t x, int16_t y, int16_t button, int16_t keys)
{
    uint16_t object_local;
    uint32_t desk = desk_globals(image), object = desk_local_address(&object_local);
    int16_t window = aes_desk_wind_find(image, x, y), done = BUTTON_NOTHING_DONE, onto;

    if (window != desk_word(image, desk, DESK_SELECTION_WINDOW))
        aes_desk_clear(image, desk_word(image, desk, DESK_SELECTION_WINDOW));
    aes_desk_verify(image, window, DESK_VERIFY_UNCHANGED);
    set_bus_word(image, desk + DESK_G_WLASTSEL, (uint16_t)window);
    if (clicks == BUTTON_ONE_CLICK) {
        onto = one_click(image, desk, window, x, y, button, keys, object);
        if (onto != BDOWN_NOTHING_DRAGGED)
            done = aes_desk_fun_drag(image, window, onto,
                                     onto ? (int16_t)bus_word(image, aes_win_find(image, onto) + WNODE_ROOT) : DESKTOP_ROOT,
                                     (int16_t)bus_word(image, object));
    } else {
        two_clicks(image, desk, window, x, y, keys);
        done = aes_do_filemenu(image, FILE_ITEM_OPEN);
    }
    aes_men_update(image, bus_long(image, desk + DESK_MENU_TREE));
    return done;
}

/* ==== BAND 6 W3b: deskmain, THE DESK ITSELF ==========================================================================
 * COMPILED FOR THE TARGET ALONE (the user's R3, read to cover W3b: the orchestrator's O1): no host twin, no Tier 1 —
 * held by its target-only rows at its arrivals (`test/test_desk_w3b.py`). sh_main's desk door `jsr`s its thunk
 * (`aes/deskdoor.h`). Its bring-up and its exit are ROUTINES OF THEIR OWN (`noinline`, PD0): the loop's frame, under
 * which every handler runs, is the six answer words alone. */

/* The desk's work area (window 0's, into DESK_G_DESK_RECT) and its full rectangle (wind_calc of every gadget round it,
 * into DESK_G_FULL_RECT). */
static void desk_area_kept(uint8_t *image, uint32_t desk)
{
    uint32_t area = desk + DESK_G_DESK_RECT, full = desk + DESK_G_FULL_RECT;

    (void)aes_desk_wind_get(image, DESKTOP_WORK_WINDOW, WF_WORKXYWH, area + GRECT_X, area + GRECT_Y, area + GRECT_W,
                            area + GRECT_H);
    (void)aes_desk_wind_calc(image, WC_WORK, WINDOW_KIND_ALL, rect_word(image, area, GRECT_X), rect_word(image, area, GRECT_Y),
                             rect_word(image, area, GRECT_W), rect_word(image, area, GRECT_H), full + GRECT_X, full + GRECT_Y,
                             full + GRECT_W, full + GRECT_H);
}

/* The launch's command and tail, the two FCBs and evnt_multi's message: each pointer to its buffer in the block. */
static void buffers_pointed(uint8_t *image, uint32_t desk)
{
    set_bus_long(image, desk + DESK_G_A_CMD, desk + DESK_G_CMD);
    set_bus_long(image, desk + DESK_G_A_TAIL, desk + DESK_G_TAIL);
    set_bus_long(image, desk + DESK_A_FCB1, desk + DESK_G_FCB1);
    set_bus_long(image, desk + DESK_A_FCB2, desk + DESK_G_FCB2);
    set_bus_long(image, desk + DESK_A_RMSG, desk + DESK_G_RMSG);
}

/* Blitmode(`mode`) through the ROM's trp14 door, its return site parked (`desk/deskleaf.h`'s idiom). Its answer. */
static int16_t blitmode(uint8_t *image, uint32_t return_site, int16_t mode)
{
    const uint16_t frame[] = {XBIOS_BLITMODE_FN, (uint16_t)mode};

    desk_xbios_parked(image, return_site);
    return (int16_t)desk_xbios_trap(frame, sizeof frame / sizeof frame[0]);
}

/* THE BLITTER ITEM, by what Blitmode(-1) answers: a blitter — the Options box made to end at the item (its last child,
 * the line under Print Screen next, the box eight lines high), the INF's preference made the item's check and Blitmode
 * set to it — or none: the box ending at Print Screen, six lines high. */
static void blitter_item_shown(uint8_t *image, uint32_t desk)
{
    uint32_t menu = bus_long(image, desk + DESK_MENU_TREE);
    int16_t hchar = (int16_t)be16(image + AES_GL_HCHAR);

    if (!(blitmode(image, AES_DESKMAIN_BLITMODE_ASKED_RETURN, BLITMODE_ASK) & BLITMODE_BLITTER_BIT)) {
        set_object_word(image, menu, OPTIONS_BOX, OB_TAIL, OPTN_PRINT_SCREEN);
        set_object_word(image, menu, OPTN_PRINT_SCREEN, OB_NEXT, OPTIONS_BOX);
        set_object_word(image, menu, OPTIONS_BOX, OB_HEIGHT, (int16_t)(hchar * OPTIONS_LINES_NONE));
        return;
    }
    set_object_word(image, menu, OPTIONS_BOX, OB_TAIL, OPTN_BLITTER);
    set_object_word(image, menu, OPTN_PRINT_SCREEN, OB_NEXT, OPTN_BLITTER_LINE);
    set_object_word(image, menu, OPTIONS_BOX, OB_HEIGHT, (int16_t)(hchar * OPTIONS_LINES_BLITTER));
    set_bus_word(image, desk + DESK_BLITTER_ON, bus_word(image, desk + DESK_CNX_BLITTER_ON));
    (void)aes_desk_menu_icheck(image, bus_long(image, desk + DESK_MENU_TREE), OPTN_BLITTER,
                               desk_word(image, desk, DESK_BLITTER_ON));
    (void)blitmode(image, AES_DESKMAIN_BLITMODE_SET_RETURN, desk_word(image, desk, DESK_BLITTER_ON));
}

/* The menu shown: brought up to date, View's items enabled, its separator — and Save Desktop where there is no drive —
 * disabled, the view and the sort the desk starts in checked, the first two preferences on. */
static void menu_shown(uint8_t *image, uint32_t desk)
{
    int16_t item;

    aes_desk_menu_bar(image, bus_long(image, desk + DESK_MENU_TREE), MENU_SHOWN);
    aes_men_update(image, bus_long(image, desk + DESK_MENU_TREE));
    for (item = VIEW_ITEM_ICONS; item <= SORT_ITEM_TYPE; item++)
        aes_ob_change(image, bus_long(image, desk + DESK_MENU_TREE), item, 0, OB_CHANGE_NO_REDRAW);
    aes_ob_change(image, bus_long(image, desk + DESK_MENU_TREE), VIEW_SEPARATOR, OB_STATE_DISABLED, OB_CHANGE_NO_REDRAW);
    if (!(uint16_t)aes_isdrive(image))
        aes_ob_change(image, bus_long(image, desk + DESK_MENU_TREE), OPTN_SAVE_DESKTOP, OB_STATE_DISABLED, OB_CHANGE_NO_REDRAW);
    set_bus_word(image, desk + DESK_VIEW_ITEM, VIEW_ITEM_ICONS);
    (void)aes_desk_menu_icheck(image, bus_long(image, desk + DESK_MENU_TREE), desk_word(image, desk, DESK_VIEW_ITEM),
                               MENU_ITEM_CHECKED);
    set_bus_word(image, desk + DESK_SORT_ITEM, SORT_ITEM_NAME);
    (void)aes_desk_menu_icheck(image, bus_long(image, desk + DESK_MENU_TREE), desk_word(image, desk, DESK_SORT_ITEM),
                               MENU_ITEM_CHECKED);
    set_bus_word(image, desk + DESK_PREFERENCES, PREFERENCE_ON);
    set_bus_word(image, desk + DESK_PREFERENCES + M68K_WORD_BYTES, PREFERENCE_ON);
}

/* THE BRING-UP, under wind_update and the busy bee: whether app_start read the INF (where it did not, the AES left). */
__attribute__((noinline)) static int desk_brought_up(uint8_t *image, uint32_t desk)
{
    uint32_t screen;
    int16_t tree;

    (void)aes_desk_appl_init(image);
    (void)aes_desk_wind_update(image, WM_BEG_UPDATE);
    desk_area_kept(image, desk);
    buffers_pointed(image, desk);
    aes_desk_wait(image, DESK_WAIT_BUSY);
    (void)aes_desk_rsrc_load(image);
    for (tree = 0; tree < DESKMAIN_TREES; tree++)
        (void)aes_ini_tree(image, desk + DESK_MENU_TREE + (uint32_t)tree * M68K_LONG_BYTES, tree);
    if (!aes_app_start(image)) {
        (void)aes_desk_appl_exit(image);
        return 0;
    }
    aes_win_start(image);
    aes_fpd_start(image);
    aes_desk_verify(image, DESKTOP_WINDOW, DESK_VERIFY_UNCHANGED);
    menu_shown(image, desk);
    (void)aes_app_blddesk(image);
    aes_do_wredraw(image, DESKTOP_WORK_WINDOW, rect_word(image, desk + DESK_G_DESK_RECT, GRECT_X),
                   rect_word(image, desk + DESK_G_DESK_RECT, GRECT_Y), rect_word(image, desk + DESK_G_DESK_RECT, GRECT_W),
                   rect_word(image, desk + DESK_G_DESK_RECT, GRECT_H));
    screen = bus_long(image, desk + DESK_G_SCREEN);
    (void)aes_desk_wind_set(image, DESKTOP_WORK_WINDOW, WF_NEWDESK, (int16_t)(screen >> 16), (int16_t)screen, NEWDESK_ROOT,
                            NEWDESK_ZERO);
    aes_desk_verify(image, DESKTOP_WINDOW, DESK_VERIFY_UNCHANGED);
    set_bus_word(image, desk + DESK_G_WLASTSEL, 0);
    aes_cnx_get(image);
    blitter_item_shown(image, desk);
    (void)aes_desk_wind_update(image, WM_END_UPDATE);
    aes_desk_wait(image, DESK_WAIT_DONE);
    return 1;
}

/* THE EXIT: the INF's windows kept and the INF saved, the menu put away, the AES left — then, where a resolution change
 * was asked, the current drive made again (set_defdrv) and, where there is a drive, checked, and AES_DISK_USABLE made
 * whether that went without a GEMDOS error. deskmain's word. */
__attribute__((noinline)) static int16_t desk_left(uint8_t *image)
{
    aes_cnx_put(image);
    aes_app_save(image, APP_SAVE_KEPT);
    aes_desk_menu_bar(image, 0, MENU_PUT_AWAY);
    (void)aes_desk_appl_exit(image);
    if (!be16(image + AES_GL_RSCHANGE))
        return DESKMAIN_DONE;
    (void)aes_set_defdrv(image);
    if ((uint16_t)aes_isdrive(image)) {
        aes_drive_check(image, (int16_t)((int16_t)aes_dos_gdrv(image, AES_DESKMAIN_GDRV_RETURN) + DRIVE_LETTER_FIRST));
        wr16(image + AES_DISK_USABLE, be16(image + AES_DOS_ERR) ? 0 : GEM_DISK_USABLE);
    }
    return DESKMAIN_GEM_LEFT;
}

/* $fe272e — deskmain (`desk/desktop.h`). evnt_multi's six answers into this frame, BY ADDRESS — the mouse, the button,
 * the keys, the key, the clicks — read back off the bus as the handlers are handed them. */
int16_t aes_deskmain(uint8_t *image)
{
    uint16_t answers_local[EV_MULTI_ANSWER_WORDS];
    uint32_t desk = desk_globals(image), answers = desk_local_address(answers_local);
    uint16_t events;
    int16_t done = DESKMAIN_NOT_DONE;

    if (!desk_brought_up(image, desk))
        return DESKMAIN_GEM_LEFT;
    while (!done) {
        events = aes_desk_evnt_multi(image, DESKMAIN_EVENTS, DESKMAIN_CLICKS, DESKMAIN_BUTTON_MASK, DESKMAIN_BUTTON_STATE,
                                     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, bus_long(image, desk + DESK_A_RMSG), 0, 0,
                                     answers + EV_RETS_X, answers + EV_RETS_Y, answers + EV_RETS_BUTTONS,
                                     answers + EV_RETS_SHIFT_KEYS, answers + EV_MULTI_KEY, answers + EV_MULTI_CLICKS);
        (void)aes_desk_wind_update(image, WM_BEG_UPDATE);
        if (events & EV_MU_MESAG)
            done = aes_hndl_msg(image);
        if (events & EV_MU_KEYBD)
            done = aes_hndl_kbd(image, (int16_t)bus_word(image, answers + EV_MULTI_KEY));
        if (events & EV_MU_BUTTON)
            done = aes_hndl_button(image, (int16_t)bus_word(image, answers + EV_MULTI_CLICKS),
                                   (int16_t)bus_word(image, answers + EV_RETS_X), (int16_t)bus_word(image, answers + EV_RETS_Y),
                                   (int16_t)bus_word(image, answers + EV_RETS_BUTTONS),
                                   (int16_t)bus_word(image, answers + EV_RETS_SHIFT_KEYS));
        (void)aes_desk_wind_update(image, WM_END_UPDATE);
    }
    return desk_left(image);
}
#endif
