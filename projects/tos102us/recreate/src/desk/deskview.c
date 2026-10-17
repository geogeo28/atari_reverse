/* deskview.c — THE DESK'S WINDOWS: THE VIEW AND ITS LAYOUT LEAVES (`desk/deskview.h`; band 6 wave 1b, unit L). Alcyon
 * C in the ROM, ported over its own order. LINKED AND UNBOUND: every Line-F entry naming one of these stays the ROM's
 * (`bench/linef_table.py`, LINKED_AND_NOT_FLIPPED) while the band's opening waits (ruling W6-R1).
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "aes/aes.h"
#include "aes/deskmem.h"
#include "aes/gemgraf.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/rect.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskact.h"
#include "desk/deskbind.h"
#include "desk/deskfun.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

/* THE ONE FRAME'S SIZE IS ITS HOST SLOT'S (`host_slot.h`). */
_Static_assert(VIEW_FRAME_BYTES == HOST_SLOT_AES_DESK_VIEW_FRAME_BYTES, "the view's frame and its host slot");
_Static_assert(SCROLL_FRAME_BYTES == HOST_SLOT_AES_DESK_SCROLL_FRAME_BYTES, "the scrolls' frame and its host slot");

static inline int16_t desk_word(const uint8_t *image, uint32_t field)
{
    return (int16_t)bus_word(image, desk_globals(image) + field);
}

static inline void set_desk_word(uint8_t *image, uint32_t field, int16_t value)
{
    set_bus_word(image, desk_globals(image) + field, (uint16_t)value);
}

static inline uint32_t screen_tree(const uint8_t *image)
{
    return bus_long(image, desk_globals(image) + DESK_G_SCREEN);
}

/* The WNODE at `index` of the desk's four (a signed word index, `muls.w #230`). */
static inline uint32_t wnode(const uint8_t *image, int16_t index)
{
    return table_entry(be32(image + AES_DESK_BLOCK_920), index, WNODE_BYTES);
}

static inline int16_t wnode_word(const uint8_t *image, uint32_t window, uint32_t field)
{
    return (int16_t)bus_word(image, window + field);
}

static inline void set_wnode_word(uint8_t *image, uint32_t window, uint32_t field, int16_t value)
{
    set_bus_word(image, window + field, (uint16_t)value);
}

/* The quotient word of `divs.w`: the dividend's word sign-extended, divided by `divisor`. */
static inline int16_t divs_quotient(int16_t dividend, int16_t divisor)
{
    return (int16_t)m68k_divs_w((uint32_t)(int32_t)dividend, (uint16_t)divisor);
}

/* ================================================================================================
 * THE VIEW.
 * ============================================================================================= */

/* A view's item extents, the space beside it (the space under it always ITEM_SPACE_UNDER), and its count and points:
 * the text view's or the icon view's own. */
static void set_view_extents(uint8_t *image, uint32_t globals, int16_t width, int16_t height, int16_t beside,
                             uint32_t count, uint32_t points)
{
    set_bus_word(image, globals + DESK_G_IWEXT, (uint16_t)width);
    set_bus_word(image, globals + DESK_G_IHEXT, (uint16_t)height);
    set_bus_word(image, globals + DESK_G_IWSPC, (uint16_t)beside);
    set_bus_word(image, globals + DESK_G_IHSPC, ITEM_SPACE_UNDER);
    set_bus_word(image, globals + DESK_G_NUM, bus_word(image, globals + count));
    set_bus_long(image, globals + DESK_G_PXY, globals + points);
}

/* $fe2a7c — win_view: the view and the sort kept; for the text view or the icon view an item's extent, the space
 * beside and under it, the count and the points of its items; then the pitch across and down, and the columns the
 * desk's width holds — at least one. Any other view keeps the extents it had. */
void aes_win_view(uint8_t *image, int16_t view, int16_t sort)
{
    uint32_t globals = desk_globals(image);
    int low_res = (int16_t)be16(image + AES_GL_WIDTH) == LOW_RES_WIDTH;
    int16_t char_width = (int16_t)be16(image + AES_GL_WCHAR);
    int16_t width, height, beside, columns;

    set_bus_word(image, globals + DESK_G_IVIEW, (uint16_t)view);
    set_bus_word(image, globals + DESK_G_ISORT, (uint16_t)sort);
    if (view == V_TEXT) {
        width = (int16_t)((low_res ? TEXT_CELLS_LOW_RES : TEXT_CELLS) * char_width);
        height = (int16_t)be16(image + AES_GL_HCHAR);
        beside = low_res ? 0 : (int16_t)(asl_word_by((uint16_t)char_width, 1) - 1);
        set_view_extents(image, globals, width, height, beside, DESK_G_NMTEXT, DESK_G_XYTEXT);
    } else if (view == V_ICON) {
        width = (int16_t)bus_word(image, globals + DESK_G_WICON);
        height = (int16_t)bus_word(image, globals + DESK_G_HICON);
        beside = (int16_t)be16(image + AES_GL_HEIGHT) > TALL_SCREEN_LINES ? ICON_SPACE_TALL : 0;
        set_view_extents(image, globals, width, height, beside, DESK_G_NMICON, DESK_G_XYICON);
    } else {
        width = (int16_t)bus_word(image, globals + DESK_G_IWEXT);
        height = (int16_t)bus_word(image, globals + DESK_G_IHEXT);
        beside = (int16_t)bus_word(image, globals + DESK_G_IWSPC);
    }
    width = (int16_t)(width + beside);
    set_bus_word(image, globals + DESK_G_IWINT, (uint16_t)width);
    set_bus_word(image, globals + DESK_G_IHINT, (uint16_t)(height + (int16_t)bus_word(image, globals + DESK_G_IHSPC)));
    columns = divs_quotient((int16_t)bus_word(image, globals + DESK_G_FULL_W), width);
    set_bus_word(image, globals + DESK_G_INCOL, (uint16_t)(columns ? columns : 1));
}

/* $fe2b64 — win_start: the screen's objects made, the icon view sorted by name, every WNODE free, none open. */
void aes_win_start(uint8_t *image)
{
    int16_t index;

    aes_obj_init(image);
    aes_win_view(image, V_ICON, SORT_BY_NAME);
    for (index = 0; index < DESK_WINDOWS; index++) {
        set_wnode_word(image, wnode(image, index), WNODE_OBID, 0);
        set_wnode_word(image, wnode(image, index), WNODE_ID, 0);
    }
    set_desk_word(image, DESK_G_WINDOWS_OPEN, 0);
}

/* ================================================================================================
 * THE WINDOW LIST.
 * ============================================================================================= */

/* $fe2ba2 — win_alloc: none where all four are open. The next window's saved rectangle given a root object — the
 * count of the open ones RISES BEFORE, and stays risen where no root is free (a ROM behaviour, reproduced) —; its
 * WNODE cleared round the root and the icon it was opened from, its pitch in items, and a GEM window of every gadget
 * over the desk's work area: the WNODE, or — that refused, the WNODE freed again — 0. */
uint32_t aes_win_alloc(uint8_t *image, int16_t obid)
{
    uint32_t globals = desk_globals(image), save, window;
    int16_t open = desk_word(image, DESK_G_WINDOWS_OPEN), root;

    if (open == DESK_WINDOWS)
        return 0;
    save = table_entry(globals, open, WINDOW_SAVE_BYTES) + DESK_G_WINDOW_SAVES;
    set_desk_word(image, DESK_G_WINDOWS_OPEN, (int16_t)(open + 1));
    root = aes_obj_walloc(image, (int16_t)bus_word(image, save + GRECT_X), (int16_t)bus_word(image, save + GRECT_Y),
                          (int16_t)bus_word(image, save + GRECT_W), (int16_t)bus_word(image, save + GRECT_H));
    if (!root)
        return 0;
    window = wnode(image, (int16_t)(root - DESK_FIRST_WINDOW_ROOT));
    set_wnode_word(image, window, WNODE_FLAGS, 0);
    set_wnode_word(image, window, WNODE_OBID, obid);
    set_wnode_word(image, window, WNODE_ROOT, root);
    set_wnode_word(image, window, WNODE_CVCOL, 0);
    set_wnode_word(image, window, WNODE_CVROW, 0);
    set_wnode_word(image, window, WNODE_PNCOL, divs_quotient((int16_t)bus_word(image, save + GRECT_W), desk_word(image, DESK_G_IWINT)));
    set_wnode_word(image, window, WNODE_PNROW, divs_quotient((int16_t)bus_word(image, save + GRECT_H), desk_word(image, DESK_G_IHINT)));
    set_wnode_word(image, window, WNODE_VNCOL, 0);
    set_wnode_word(image, window, WNODE_VNROW, 0);
    set_wnode_word(image, window, WNODE_ID,
                   aes_desk_wind_create(image, WINDOW_KIND_ALL, desk_word(image, DESK_G_DESK_RECT + GRECT_X),
                                        desk_word(image, DESK_G_DESK_RECT + GRECT_Y), desk_word(image, DESK_G_DESK_RECT + GRECT_W),
                                        desk_word(image, DESK_G_DESK_RECT + GRECT_H)));
    if (wnode_word(image, window, WNODE_ID) != WINDOW_NONE)
        return window;
    aes_win_free(image, window);
    return 0;
}

/* $fe2c5c — win_free: its GEM window deleted (where it has one), one fewer open, the WNODE cleared, its root put
 * under every other and freed at no size. */
void aes_win_free(uint8_t *image, uint32_t window)
{
    if (wnode_word(image, window, WNODE_ID) != WINDOW_NONE)
        (void)aes_desk_wind_delete(image, wnode_word(image, window, WNODE_ID));
    set_desk_word(image, DESK_G_WINDOWS_OPEN, (int16_t)(desk_word(image, DESK_G_WINDOWS_OPEN) - 1));
    set_wnode_word(image, window, WNODE_ID, 0);
    set_wnode_word(image, window, WNODE_OBID, 0);
    aes_desk_objc_order(image, screen_tree(image), wnode_word(image, window, WNODE_ROOT), ORDER_BOTTOM);
    aes_obj_wfree(image, wnode_word(image, window, WNODE_ROOT), 0, 0, 0, 0);
}

/* $fe2cb8 — win_find: the WNODE whose GEM window is `handle`, or 0. */
uint32_t aes_win_find(uint8_t *image, int16_t handle)
{
    int16_t index;

    for (index = 0; index < DESK_WINDOWS; index++)
        if (wnode_word(image, wnode(image, index), WNODE_ID) == handle)
            return wnode(image, index);
    return 0;
}

/* The window's drive and path made current — unless it is a cartridge's. win_top's and win_ontop's common tail. */
static void make_its_path_current(uint8_t *image, uint32_t window)
{
    if (!aes_streq(image, CARTRIDGE_NAME, window + WNODE_NAME))
        (void)aes_pro_chdir(image, (int16_t)(int8_t)bus_byte(image, window + WNODE_NAME_DRIVE), window + WNODE_NAME_PATH);
}

/* $fe2cf4 — win_top: its root put over every other, its path made current. */
void aes_win_top(uint8_t *image, uint32_t window)
{
    aes_desk_objc_order(image, screen_tree(image), wnode_word(image, window, WNODE_ROOT), ORDER_TOP);
    make_its_path_current(image, window);
}

/* $fe2d46 — win_ontop: the root over every other (the root's last child) — where it has a size — its WNODE, its
 * path made current; else 0. */
uint32_t aes_win_ontop(uint8_t *image)
{
    uint32_t objects = screen_objects(image), window;
    int16_t top = object_word(image, objects, OB_ROOT, OB_TAIL);

    if (!object_word(image, objects, top, OB_WIDTH) || !object_word(image, objects, top, OB_HEIGHT))
        return 0;
    window = wnode(image, (int16_t)(top - DESK_FIRST_WINDOW_ROOT));
    make_its_path_current(image, window);
    return window;
}

/* $fe2dc8 — win_cnt: the root `level` places along the root's children, as a WNODE index. The count runs as a
 * word to zero (a negative level runs it the long way round). */
int16_t aes_win_cnt(uint8_t *image, int16_t level)
{
    uint32_t objects = screen_objects(image);
    int16_t root = object_word(image, objects, OB_ROOT, OB_HEAD);
    uint16_t steps = (uint16_t)level;

    while (steps--)
        root = object_word(image, objects, root, OB_NEXT);
    return (int16_t)(root - DESK_FIRST_WINDOW_ROOT);
}

/* $fe2dfc — win_ith: ...its WNODE. */
uint32_t aes_win_ith(uint8_t *image, int16_t level)
{
    return wnode(image, aes_win_cnt(image, level));
}

/* ================================================================================================
 * THE LAYOUT LEAVES.
 * ============================================================================================= */

/* A scroll position pulled back until `shown` items from it fit in the view's `total`. */
static inline void scroll_back_to_fit(uint8_t *image, uint32_t window, uint32_t position, uint32_t total, int16_t shown)
{
    while (shown > (int16_t)(wnode_word(image, window, total) - wnode_word(image, window, position)))
        set_wnode_word(image, window, position, (int16_t)(wnode_word(image, window, position) - 1));
}

/* $fe2e12 — win_ocalc: every file of the window's path given no object, and counted; the view's columns (no more
 * than the desk's) and its rows (rounded up), each at least one; the columns and rows shown — what fits, `wfit` and
 * `hfit` at least one — and the scroll pulled back to keep them filled; the first file shown answered through
 * `first_out` (0 past the list's end). */
void aes_win_ocalc(uint8_t *image, uint32_t window, int16_t wfit, int16_t hfit, uint32_t first_out)
{
    uint32_t files = bus_long(image, bus_long(image, window + WNODE_PATH) + PNODE_FLIST), file;
    int16_t count = 0, columns = desk_word(image, DESK_G_INCOL), shown;
    uint32_t rows;
    uint16_t skipped;

    for (file = files; file; file = bus_long(image, file + FNODE_NEXT)) {
        set_bus_word(image, file + FNODE_OBID, (uint16_t)OB_NIL);
        count++;
    }
    set_wnode_word(image, window, WNODE_VNCOL, count < columns ? count : columns);
    rows = m68k_divs_w((uint32_t)(int32_t)count, (uint16_t)columns);
    set_wnode_word(image, window, WNODE_VNROW, (int16_t)rows);
    if ((int16_t)(rows >> 16))
        set_wnode_word(image, window, WNODE_VNROW, (int16_t)(wnode_word(image, window, WNODE_VNROW) + 1));
    if (!wnode_word(image, window, WNODE_VNROW))
        set_wnode_word(image, window, WNODE_VNROW, 1);
    if (!wnode_word(image, window, WNODE_VNCOL))
        set_wnode_word(image, window, WNODE_VNCOL, 1);
    if (!wfit)
        wfit++;
    shown = aes_min(wfit, wnode_word(image, window, WNODE_VNCOL));
    set_wnode_word(image, window, WNODE_PNCOL, shown);
    scroll_back_to_fit(image, window, WNODE_CVCOL, WNODE_VNCOL, shown);
    if (!hfit)
        hfit++;
    shown = aes_min(hfit, wnode_word(image, window, WNODE_VNROW));
    set_wnode_word(image, window, WNODE_PNROW, shown);
    scroll_back_to_fit(image, window, WNODE_CVROW, WNODE_VNROW, shown);
    skipped = (uint16_t)(wnode_word(image, window, WNODE_CVROW) * desk_word(image, DESK_G_INCOL) + wnode_word(image, window, WNODE_CVCOL));
    for (file = files; skipped-- && file; file = bus_long(image, file + FNODE_NEXT))
        ;
    set_bus_long(image, first_out, file);
}

/* $fe2f0a — win_icalc: the file's ANODE — among the folders' for a folder, the files' for any other — found by its
 * name (app_afind), kept in the FNODE with what app_afind answers of it. */
void aes_win_icalc(uint8_t *image, uint32_t file)
{
    int16_t type = bus_byte(image, file + FNODE_ATTR) & FNODE_ATTR_SUBDIR ? AT_ISFOLD : AT_ISFILE;

    set_bus_long(image, file + FILE_ANODE,
                 aes_app_afind(image, AFIND_NOT_ON_THE_DESK, type, AFIND_BY_NAME, file + FNODE_NAME, file + FILE_ISAPP));
}

/* A text view's item: a G_USERDEF object over the object's own USERBLK — the desk's draw code, the file's fields from
 * f_attr on — and the file's ANODE found. */
static void lay_text_item(uint8_t *image, uint32_t globals, int16_t object, uint32_t file)
{
    uint32_t userblk = globals + word_index((uint16_t)object, USERBLK_BYTES) + DESK_G_USERBLKS;

    set_object_word(image, globals + DESK_G_SCREEN_OBJECTS, object, OB_TYPE, G_USERDEF);
    set_bus_long(image, object_address(globals + DESK_G_SCREEN_OBJECTS, object, OB_SPEC), userblk);
    set_bus_long(image, userblk + UB_CODE, be32(image + AES_DESK_USERDEF_CODE));
    set_bus_long(image, userblk + UB_PARM, file + FNODE_ATTR);
    aes_win_icalc(image, file);
}

/* An icon view's item: a G_ICON object over the object's own ICONBLK — a copy of the icon its ANODE gives an
 * application or a document, its text the file's name — and that icon kept for the object. */
static void lay_icon_item(uint8_t *image, uint32_t globals, int16_t object, uint32_t file)
{
    uint32_t iconblk = table_entry(globals, object, ICONBLK_BYTES) + DESK_G_ICONS, anode;
    int16_t icon;

    set_object_word(image, globals + DESK_G_SCREEN_OBJECTS, object, OB_TYPE, G_ICON);
    aes_win_icalc(image, file);
    anode = bus_long(image, file + FILE_ANODE);
    icon = (int16_t)bus_word(image, anode + (bus_word(image, file + FILE_ISAPP) ? ANODE_AICON : ANODE_DICON));
    set_bus_word(image, table_entry(globals, object, M68K_WORD_BYTES) + DESK_G_INDEX, (uint16_t)icon);
    set_bus_long(image, object_address(globals + DESK_G_SCREEN_OBJECTS, object, OB_SPEC), iconblk);
    aes_movs(image, ICONBLK_BYTES, table_entry(globals, icon, ICONBLK_BYTES) + DESK_MASK_ICONBLKS, iconblk);
    set_bus_long(image, iconblk + IB_PTEXT, file + FNODE_NAME);
}

/* One slider of the window: its size the part shown of the view's `total` in thousandths (asked back at once,
 * through the frame), its place the scroll in thousandths of what is not shown — 0 where all of it is. */
static void set_slider(uint8_t *image, uint32_t window, uint32_t frame, int16_t size_field, int16_t place_field,
                       uint32_t shown, uint32_t total, uint32_t scroll)
{
    int16_t handle = wnode_word(image, window, WNODE_ID);
    int16_t place = 0;

    (void)aes_desk_wind_set(image, handle, size_field,
                            aes_mul_div(wnode_word(image, window, shown), SLIDER_SCALE, wnode_word(image, window, total)), 0, 0, 0);
    (void)aes_desk_wind_get(image, handle, size_field, frame + BLDVIEW_SLIDER, frame + BLDVIEW_UNREAD, frame + BLDVIEW_UNREAD,
                            frame + BLDVIEW_UNREAD);
    if (wnode_word(image, window, total) > wnode_word(image, window, shown))
        place = aes_mul_div(wnode_word(image, window, scroll), SLIDER_SCALE,
                            (int16_t)(wnode_word(image, window, total) - wnode_word(image, window, shown)));
    (void)aes_desk_wind_set(image, handle, place_field, place, 0, 0, 0);
}

/* win_bldview's items: the window's root freed at the rectangle, win_ocalc over what the rectangle fits (the first
 * file shown into the frame), then each file an item object under the root (win_bldview's comment, below). */
static void lay_the_items(uint8_t *image, uint32_t window, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(VIEW_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_VIEW_FRAME, frame_local), globals = desk_globals(image), file;
    int16_t columns, rows, column = 0, row = 0;

    aes_obj_wfree(image, wnode_word(image, window, WNODE_ROOT), x, y, w, h);
    aes_win_ocalc(image, window, divs_quotient(w, desk_word(image, DESK_G_IWINT)), divs_quotient(h, desk_word(image, DESK_G_IHINT)),
                  frame + BLDVIEW_FIRST_FILE);
    columns = aes_min((int16_t)(wnode_word(image, window, WNODE_PNCOL) + 1),
                      (int16_t)(wnode_word(image, window, WNODE_VNCOL) - wnode_word(image, window, WNODE_CVCOL)));
    rows = aes_min((int16_t)(wnode_word(image, window, WNODE_PNROW) + 1),
                   (int16_t)(wnode_word(image, window, WNODE_VNROW) - wnode_word(image, window, WNODE_CVROW)));
    file = be32(image + frame + BLDVIEW_FIRST_FILE);
    while (column < columns && row < rows && file) {
        int16_t object = aes_obj_ialloc(image, wnode_word(image, window, WNODE_ROOT),
                                        (int16_t)(desk_word(image, DESK_G_IWSPC) + (int16_t)(desk_word(image, DESK_G_IWINT) * column)),
                                        (int16_t)(desk_word(image, DESK_G_IHSPC) + (int16_t)(desk_word(image, DESK_G_IHINT) * row)),
                                        desk_word(image, DESK_G_IWEXT), desk_word(image, DESK_G_IHEXT));

        set_bus_word(image, file + FNODE_OBID, (uint16_t)object);
        set_object_word(image, globals + DESK_G_SCREEN_OBJECTS, object, OB_STATE, ITEM_STATE);
        set_object_word(image, globals + DESK_G_SCREEN_OBJECTS, object, OB_FLAGS, ITEM_FLAGS);
        if (desk_word(image, DESK_G_IVIEW) == V_TEXT)
            lay_text_item(image, globals, object, file);
        else if (desk_word(image, DESK_G_IVIEW) == V_ICON)
            lay_icon_item(image, globals, object, file);
        file = bus_long(image, file + FNODE_NEXT);
        if (++column == columns) {
            uint16_t skipped = (uint16_t)(wnode_word(image, window, WNODE_VNCOL) - columns);

            row++;
            column = 0;
            while (skipped-- && file)
                file = bus_long(image, file + FNODE_NEXT);
        }
    }
    host_slot_release(AES_DESK_VIEW_FRAME);
}

/* ...and its two sliders, the horizontal then the vertical, set over a frame of their own (wind_get's answers). */
__attribute__((noinline)) static void the_sliders_set(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(VIEW_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_VIEW_FRAME, frame_local);

    set_slider(image, window, frame, WF_HSLSIZE, WF_HSLIDE, WNODE_PNCOL, WNODE_VNCOL, WNODE_CVCOL);
    set_slider(image, window, frame, WF_VSLSIZE, WF_VSLIDE, WNODE_PNROW, WNODE_VNROW, WNODE_CVROW);
    host_slot_release(AES_DESK_VIEW_FRAME);
}

/* $fe2f68 — win_bldview: THE VIEW BUILDER. The window's root freed at the rectangle; win_ocalc over what the
 * rectangle fits; then, row by row from the first file shown, each file an item object under the root — one column
 * and one row more than fit, where the view has them — at its place on the grid (the items of the view's columns not
 * shown skipped at each row's end); then the two sliders. TWO ROUTINES OF ITS OWN, AND THE SECOND ENTERED AS A JUMP
 * (W6-R4): the item loop keeps eleven registers, and the sliders' wind_set redraws the window — the deepest path of
 * PD0 — so nothing of win_bldview's, nor of the loop's, stands under it. (GCC keeps the loop out of line unasked: an
 * attribute there measured nothing. `test_aes_desk_ours.py` holds both as routines of the shipped ELF, and the jump.) */
void aes_win_bldview(uint8_t *image, uint32_t window, int16_t x, int16_t y, int16_t w, int16_t h)
{
    lay_the_items(image, window, x, y, w, h);
    the_sliders_set(image, window);
}

/* $fe3760 — win_isel: the first child of `root` after `current` (from its first, for none) that is SELECTED. */
int16_t aes_win_isel(uint8_t *image, uint32_t tree, int16_t root, int16_t current)
{
    int16_t child = current ? object_word(image, tree, current, OB_NEXT) : object_word(image, tree, root, OB_HEAD);

    for (; child > root; child = object_word(image, tree, child, OB_NEXT))
        if (bus_byte(image, object_address(tree, child, OB_STATE + OB_WORD_LOW_BYTE)) & 1u << OB_STATE_SELECTED_BIT)
            return child;
    return 0;
}

/* $fe37c4 — win_iname: the text of the icon object `object` of the screen's. */
uint32_t aes_win_iname(uint8_t *image, int16_t object)
{
    return bus_long(image, bus_long(image, object_address(screen_objects(image), object, OB_SPEC)) + IB_PTEXT);
}

/* $fe36fa — win_shwall: every window that has a GEM window — by its place along the root's children, the last first —
 * sent the desk's own redraw message over its work area. */
void aes_win_shwall(uint8_t *image)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(VIEW_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_VIEW_FRAME, frame_local);
    int16_t level;

    for (level = DESK_WINDOWS; level; level--) {
        uint32_t window = aes_win_ith(image, level);
        int16_t handle = wnode_word(image, window, WNODE_ID);

        if (!handle)
            continue;
        (void)aes_desk_wind_get(image, handle, WF_WORKXYWH, work + GRECT_X, work + GRECT_Y, work + GRECT_W, work + GRECT_H);
        (void)aes_desk_fun_msg(image, WM_REDRAW, (int16_t)be16(image + AES_GL_APID), wnode_word(image, window, WNODE_ID),
                               (int16_t)be16(image + work + GRECT_X), (int16_t)be16(image + work + GRECT_Y),
                               (int16_t)be16(image + work + GRECT_W), (int16_t)be16(image + work + GRECT_H));
    }
    host_slot_release(AES_DESK_VIEW_FRAME);
}

/* $fe37ee — win_sinfo: the info line's template copied into the desk's 512-byte block, merged with the path's bytes
 * and files into the window's info line. */
void aes_win_sinfo(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(VIEW_FRAME_BYTES)];
    uint32_t parameters = host_slot_claim(AES_DESK_VIEW_FRAME, frame_local);
    uint32_t path = bus_long(image, window + WNODE_PATH), alert = desk_globals(image) + DESK_G_ALERT;

    wr32(image + parameters + SINFO_SIZE, bus_long(image, path + PATH_FILE_BYTES));
    wr16(image + parameters + SINFO_COUNT, bus_word(image, path + PATH_FILE_COUNT));
    (void)aes_desk_rsrc_gaddr(image, R_STRING, STINFOST, alert);
    (void)aes_lstcpy(image, be32(image + AES_DESK_BLOCK_512), bus_long(image, alert));
    aes_merge_str(image, window + WNODE_INFO, be32(image + AES_DESK_BLOCK_512), parameters);
    host_slot_release(AES_DESK_VIEW_FRAME);
}

/* $fe384c — win_sname: the window's name — a blank, its path's spec to its first `*`, a blank. */
void aes_win_sname(uint8_t *image, uint32_t window)
{
    uint32_t spec = bus_long(image, window + WNODE_PATH) + PNODE_SPEC, name = window + WNODE_NAME;

    set_bus_byte(image, name++, STRING_SPACE);
    for (; bus_byte(image, spec) && bus_byte(image, spec) != STRING_WILDCARD_ANY; spec++)
        set_bus_byte(image, name++, bus_byte(image, spec));
    set_bus_byte(image, name++, STRING_SPACE);
    set_bus_byte(image, name, STRING_NUL);
}

/* ================================================================================================
 * BAND 6 WAVE 2 (group G3): THE SCROLLS AND THE WINDOWS' REBUILDS.
 * ============================================================================================= */

/* The window's work area answered into the rectangle at `rect`. */
static inline void get_work(uint8_t *image, int16_t handle, uint32_t rect)
{
    (void)aes_desk_wind_get(image, handle, WF_WORKXYWH, rect + GRECT_X, rect + GRECT_Y, rect + GRECT_W, rect + GRECT_H);
}

/* $fe3310 — win_blt: the first row (`vertical`) or column made `first` — no less than 0, no more than the view's less
 * what is shown; none moved: done (the ROM's D0 0). The view rebuilt over the work area; where the work area lies
 * wholly below the menu bar (its copy clipped there unchanged) and the step is less than what is shown, the rows
 * (columns) still shown blitted along by the step's pitches — up for a step down, down for a step up — and the
 * work area cut to the strip they left; then that redrawn. */
void aes_win_blt(uint8_t *image, uint32_t window, int16_t vertical, int16_t first)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SCROLL_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_SCROLL_FRAME, frame_local);
    uint32_t work = frame + SCROLL_FRAME_WORK, clipped = frame + SCROLL_FRAME_CLIPPED;
    uint32_t shown_field = vertical ? WNODE_PNROW : WNODE_PNCOL, scroll = vertical ? WNODE_CVROW : WNODE_CVCOL;
    int16_t shown, step;

    first = aes_max(WIN_BLT_FIRST, first);
    first = aes_min((int16_t)(wnode_word(image, window, vertical ? WNODE_VNROW : WNODE_VNCOL) - wnode_word(image, window, shown_field)),
                    first);
    shown = wnode_word(image, window, shown_field);
    step = (int16_t)(first - wnode_word(image, window, scroll));
    set_wnode_word(image, window, scroll, (int16_t)(wnode_word(image, window, scroll) + step));
    if (!step) {
        host_slot_release(AES_DESK_SCROLL_FRAME);
        return;
    }
    get_work(image, wnode_word(image, window, WNODE_ID), work);
    aes_win_bldview(image, window, rect_word(image, work, GRECT_X), rect_word(image, work, GRECT_Y),
                    rect_word(image, work, GRECT_W), rect_word(image, work, GRECT_H));
    aes_rc_copy(image, work, clipped);
    (void)aes_rc_intersect(image, AES_GL_RFULL, clipped);
    if (aes_rc_equal(image, work, clipped)) {
        int16_t backward = step < 0;

        if (backward)
            step = (int16_t)-step;
        if (step < shown) {
            int16_t source_x = 0, source_y = 0, to_x = 0, to_y = 0, width, height, swapped;

            if (vertical) {
                source_y = (int16_t)(step * desk_word(image, DESK_G_IHINT));
                width = rect_word(image, work, GRECT_W);
                height = (int16_t)(rect_word(image, work, GRECT_H) - source_y);
            } else {
                source_x = (int16_t)(step * desk_word(image, DESK_G_IWINT));
                width = (int16_t)(rect_word(image, work, GRECT_W) - source_x);
                height = rect_word(image, work, GRECT_H);
            }
            if (backward) {
                swapped = source_x, source_x = to_x, to_x = swapped;
                swapped = source_y, source_y = to_y, to_y = swapped;
            }
            (void)aes_gsx_sclip(image, work);
            aes_bb_screen(image, WIN_BLT_RULE, (int16_t)(rect_word(image, work, GRECT_X) + source_x),
                          (int16_t)(rect_word(image, work, GRECT_Y) + source_y), (int16_t)(rect_word(image, work, GRECT_X) + to_x),
                          (int16_t)(rect_word(image, work, GRECT_Y) + to_y), width, height);
            if (vertical) {
                if (!backward)
                    set_bus_word(image, work + GRECT_Y, (uint16_t)(rect_word(image, work, GRECT_Y) + height));
                set_bus_word(image, work + GRECT_H, (uint16_t)(rect_word(image, work, GRECT_H) - height));
            } else {
                if (!backward)
                    set_bus_word(image, work + GRECT_X, (uint16_t)(rect_word(image, work, GRECT_X) + width));
                set_bus_word(image, work + GRECT_W, (uint16_t)(rect_word(image, work, GRECT_W) - width));
            }
        }
    }
    aes_do_wredraw(image, wnode_word(image, window, WNODE_ID), rect_word(image, work, GRECT_X), rect_word(image, work, GRECT_Y),
                   rect_word(image, work, GRECT_W), rect_word(image, work, GRECT_H));
    host_slot_release(AES_DESK_SCROLL_FRAME);
}

/* $fe3504 — win_slide: the slider's size asked (and never read), the place `value` in thousandths of what is not
 * shown made the first row (column): win_blt. */
void aes_win_slide(uint8_t *image, int16_t handle, int16_t value, int16_t vertical)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SCROLL_FRAME_BYTES)];
    uint32_t window = aes_win_find(image, handle), frame;
    int16_t total = wnode_word(image, window, vertical ? WNODE_VNROW : WNODE_VNCOL);
    int16_t shown = wnode_word(image, window, vertical ? WNODE_PNROW : WNODE_PNCOL);

    frame = host_slot_claim(AES_DESK_SCROLL_FRAME, frame_local);
    (void)aes_desk_wind_get(image, handle, vertical ? WF_VSLSIZE : WF_HSLSIZE, frame + SCROLL_FRAME_SIZE,
                            frame + SCROLL_FRAME_UNREAD, frame + SCROLL_FRAME_UNREAD, frame + SCROLL_FRAME_UNREAD);
    host_slot_release(AES_DESK_SCROLL_FRAME);
    aes_win_blt(image, window, vertical, aes_mul_div(value, (int16_t)(total - shown), SLIDER_SCALE));
}

/* $fe359a — win_arrow: a page or a line up or down (a row), left or right (a column) from the first shown: win_blt. */
void aes_win_arrow(uint8_t *image, int16_t handle, int16_t arrow)
{
    uint32_t window = aes_win_find(image, handle);
    int16_t row = wnode_word(image, window, WNODE_CVROW), column = wnode_word(image, window, WNODE_CVCOL);
    int16_t vertical = 1, first;

    switch (arrow) {
    case WA_UPPAGE: first = (int16_t)(row - wnode_word(image, window, WNODE_PNROW)); break;
    case WA_DNPAGE: first = (int16_t)(row + wnode_word(image, window, WNODE_PNROW)); break;
    case WA_UPLINE: first = (int16_t)(row - 1); break;
    case WA_DNLINE: first = (int16_t)(row + 1); break;
    case WA_LFPAGE: first = (int16_t)(column - wnode_word(image, window, WNODE_PNCOL)), vertical = 0; break;
    case WA_RTPAGE: first = (int16_t)(column + wnode_word(image, window, WNODE_PNCOL)), vertical = 0; break;
    case WA_LFLINE: first = (int16_t)(column - 1), vertical = 0; break;
    case WA_RTLINE: first = (int16_t)(column + 1), vertical = 0; break;
    default:
        recreate_not_reconstructed("win_arrow of an arrow word past WA_RTLINE: the ROM scrolls to its caller's D6");
    }
    aes_win_blt(image, window, vertical, first);
}

/* $fe3622 — win_srtall: every window that has a GEM window, its path's files sorted again. */
void aes_win_srtall(uint8_t *image)
{
    int16_t index;

    for (index = 0; index < DESK_WINDOWS; index++) {
        uint32_t path;

        if (!wnode_word(image, wnode(image, index), WNODE_ID))
            continue;
        path = bus_long(image, wnode(image, index) + WNODE_PATH);
        set_bus_long(image, bus_long(image, wnode(image, index) + WNODE_PATH) + PNODE_FLIST,
                     aes_pn_sort(image, SORT_AGAIN, bus_long(image, path + PNODE_FLIST)));
    }
}

/* $fe3684 — win_bdall: every window that has a GEM window, its view rebuilt over its work area. */
void aes_win_bdall(uint8_t *image)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SCROLL_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_SCROLL_FRAME, frame_local) + SCROLL_FRAME_WORK;
    int16_t index;

    for (index = 0; index < DESK_WINDOWS; index++) {
        int16_t handle = wnode_word(image, wnode(image, index), WNODE_ID);

        if (!handle)
            continue;
        get_work(image, handle, work);
        aes_win_bldview(image, wnode(image, index), rect_word(image, work, GRECT_X), rect_word(image, work, GRECT_Y),
                        rect_word(image, work, GRECT_W), rect_word(image, work, GRECT_H));
    }
    host_slot_release(AES_DESK_SCROLL_FRAME);
}
