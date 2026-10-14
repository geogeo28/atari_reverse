/* desktop.c — UNIT K, THE DESK'S MAIN LOOP'S HELPERS (`desk/desktop.h`): Alcyon C in the ROM, each ported over its own
 * order; every menu change through unit D's binding (`desk/deskbind.h`).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gsxif.h"
#include "aes/strings.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskfpd.h"
#include "desk/desksupp.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

_Static_assert(FIND_FRAME_BYTES == HOST_SLOT_AES_MEN_UPDATE_FIND_BYTES, "men_update's two answers and their host slot");

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
