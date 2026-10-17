/* deskact.c — THE DESK'S HIT TESTS AND ICON DRAGS (`desk/deskact.h`): `$fdc080..$fdcc29` less the drag loops (wave
 * 2's). Alcyon C in the ROM, ported over its own order; the bindings it calls are unit D's (`desk/deskbind.h`).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/evdoor.h"
#include "aes/gemgraf.h"
#include "aes/gemsuper.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskleaf.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

/* EVERY FRAME HANDED ON BY ADDRESS IS ITS HOST SLOT'S SIZE (`host_slot.h`). */
_Static_assert(GR_ISDOWN_FRAME_BYTES == HOST_SLOT_AES_GR_ISDOWN_ANSWERS_BYTES, "gr_isdown's answers and their host slot");
_Static_assert(GR_BWAIT_FRAME_BYTES == HOST_SLOT_AES_GR_BWAIT_ANSWERS_BYTES, "gr_bwait's answers and their host slot");
_Static_assert(ACT_CHKOBJ_FRAME_BYTES == HOST_SLOT_AES_ACT_CHKOBJ_RECTS_BYTES, "act_chkobj's rectangles and their host slot");
_Static_assert(ACT_CHG_FRAME_BYTES == HOST_SLOT_AES_ACT_CHG_RECT_BYTES, "act_chg's rectangle and its host slot");
_Static_assert(ACT_ALLCHG_FRAME_BYTES == HOST_SLOT_AES_ACT_ALLCHG_RECTS_BYTES, "act_allchg's rectangles and their host slot");

static inline int is_selected(const uint8_t *image, uint32_t tree, int16_t obj)
{
    return bus_byte(image, object_address(tree, obj, OB_STATE) + OB_WORD_LOW_BYTE) & OB_STATE_SELECTED;
}

/* A point pair's two words: the `nth` pair of the array at `points`. */
#define POINT_BYTES           (2 * M68K_WORD_BYTES)

static inline uint32_t point_at(uint32_t points, int16_t nth)
{
    return table_entry(points, nth, POINT_BYTES);
}

static inline int16_t point_x(const uint8_t *image, uint32_t points, int16_t nth)
{
    return (int16_t)bus_word(image, point_at(points, nth));
}

static inline int16_t point_y(const uint8_t *image, uint32_t points, int16_t nth)
{
    return (int16_t)bus_word(image, point_at(points, nth) + M68K_WORD_BYTES);
}

/* $fdc080 — app_afind: the ANODE in use that is — `isdesk` — the desktop icon object `obid` shows; or else the
 * first of `type`, not a desktop icon, whose data pattern or else application pattern matches `name` (wildcmp),
 * which of the two said through `isapp_out`. ANODE_NONE where none is. */
uint32_t aes_app_afind(uint8_t *image, int16_t isdesk, int16_t type, int16_t obid, uint32_t name, uint32_t isapp_out)
{
    for (uint32_t node = bus_long(image, desk_globals(image) + DESK_ANODES_IN_USE); node != ANODE_NONE;
         node = bus_long(image, node + ANODE_NEXT)) {
        if (isdesk) {
            if (obid == (int16_t)bus_word(image, node + ANODE_OBID))
                return node;
            continue;
        }
        if (type != (int16_t)bus_word(image, node + ANODE_TYPE)
            || bus_byte(image, node + ANODE_FLAGS + OB_WORD_LOW_BYTE) & 1 << ANODE_FLAG_ISDESK_BIT)
            continue;
        if (aes_wildcmp(image, bus_long(image, node + ANODE_PDATA), name)) {
            set_bus_word(image, isapp_out, APP_AFIND_DATA);
            return node;
        }
        if (aes_wildcmp(image, bus_long(image, node + ANODE_PAPPL), name)) {
            set_bus_word(image, isapp_out, APP_AFIND_APPLICATION);
            return node;
        }
    }
    return ANODE_NONE;
}

/* $fdc0fa — gr_obfind: the icon of `root` under the point — objc_find's, held by act_chkobj to the icon's own image or
 * label (an icon's object is wider than both); `root`, or NIL, where objc_find found no icon. */
int16_t aes_gr_obfind(uint8_t *image, uint32_t tree, int16_t root, int16_t mx, int16_t my)
{
    int16_t found = aes_desk_objc_find(image, tree, root, GR_OBFIND_DEPTH, mx, my);

    if (found != root && found != OB_NIL)
        found = aes_act_chkobj(image, tree, root, found, mx, my, GR_OBFIND_POINT_SIZE, GR_OBFIND_POINT_SIZE);
    return found;
}

/* $fdc152 — gr_isdown: evnt_multi until the button comes up (one click awaited, state 0) or the mouse leaves — or,
 * `leave` 0, enters — the rectangle; the mouse and the keys through the caller's four pointers, the key and the
 * clicks into its own frame. GR_ISDOWN_DOWN where no button event came. */
int16_t aes_gr_isdown(uint8_t *image, int16_t leave, int16_t x, int16_t y, int16_t w, int16_t h, uint32_t mouse_x_out,
                      uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out)
{
    uint16_t answers_local[FRAME_LOCAL_WORDS(GR_ISDOWN_FRAME_BYTES)];
    uint32_t answers = host_slot_claim(AES_GR_ISDOWN_ANSWERS, answers_local);
    /* (the second rectangle, the message buffer and the timer all zeros: `clr.w` and four `clr.l`, $fdc17c..$fdc184) */
    uint16_t events = aes_desk_evnt_multi(image, EV_MU_BUTTON | EV_MU_M1, GR_ISDOWN_CLICKS, GR_ISDOWN_MASK, GR_ISDOWN_STATE,
                                          leave, x, y, w, h, 0, 0, 0, 0, 0, 0, 0, 0, mouse_x_out, mouse_y_out, buttons_out,
                                          keys_out, answers + GR_ISDOWN_KEY_ANSWER, answers + GR_ISDOWN_CLICKS_ANSWER);

    host_slot_release(AES_GR_ISDOWN_ANSWERS);
    return (events & EV_MU_BUTTON) ? GR_ISDOWN_UP : GR_ISDOWN_DOWN;
}

/* $fdc1ba — gr_accobs: the screen corners of `root`'s SELECTED children, as point pairs at `points` — at most
 * GR_ACCOBS_MAX (the count tested after every child, selected or not) — and their count through `count_out`. */
void aes_gr_accobs(uint8_t *image, uint32_t tree, int16_t root, uint32_t count_out, uint32_t points)
{
    int16_t root_x = object_word(image, tree, root, OB_X), root_y = object_word(image, tree, root, OB_Y);
    int16_t kept = 0;

    for (int16_t obj = object_word(image, tree, root, OB_HEAD); obj > root; obj = object_word(image, tree, obj, OB_NEXT)) {
        if (is_selected(image, tree, obj)) {
            uint32_t point = point_at(points, kept);

            set_bus_word(image, point, (uint16_t)(object_word(image, tree, obj, OB_X) + root_x));
            set_bus_word(image, point + M68K_WORD_BYTES, (uint16_t)(object_word(image, tree, obj, OB_Y) + root_y));
            kept++;
        }
        if (kept >= GR_ACCOBS_MAX)
            break;
    }
    set_bus_word(image, count_out, (uint16_t)kept);
}

/* $fdc398 — gr_extent: the rectangle that holds the `count` points — its least corner started at GR_EXTENT_FAR, its
 * greatest at 0 (SIGNED compares) — set at `rect`. */
void aes_gr_extent(uint8_t *image, int16_t count, uint32_t points, uint32_t rect)
{
    int16_t least_x = GR_EXTENT_FAR, least_y = GR_EXTENT_FAR, most_x = 0, most_y = 0;

    for (int16_t nth = 0; nth < count; nth++) {
        if (point_x(image, points, nth) < least_x)
            least_x = point_x(image, points, nth);
        if (point_y(image, points, nth) < least_y)
            least_y = point_y(image, points, nth);
        if (point_x(image, points, nth) > most_x)
            most_x = point_x(image, points, nth);
        if (point_y(image, points, nth) > most_y)
            most_y = point_y(image, points, nth);
    }
    aes_r_set(image, rect, least_x, least_y, (int16_t)(most_x - least_x + 1), (int16_t)(most_y - least_y + 1));
}

/* $fdc458 — gr_obalign: each of the `count` points moved by (-x, -y), in place. */
void aes_gr_obalign(uint8_t *image, int16_t count, int16_t x, int16_t y, uint32_t points)
{
    for (int16_t nth = 0; nth < count; nth++) {
        uint32_t point = point_at(points, nth);

        set_bus_word(image, point, (uint16_t)(bus_word(image, point) - (uint16_t)x));
        set_bus_word(image, point + M68K_WORD_BYTES, (uint16_t)(bus_word(image, point + M68K_WORD_BYTES) - (uint16_t)y));
    }
}

/* $fdc49a — gr_plns: the cursor hidden, the outline of `count` points drawn at (x, y) moved by each of the `icons`
 * corners (gsx_pline), the cursor shown again. */
void aes_gr_plns(uint8_t *image, int16_t x, int16_t y, int16_t count, uint32_t outline, int16_t icons, uint32_t corners)
{
    aes_desk_graf_mouse(image, GRAF_MOUSE_HIDE, DESK_NO_FORM);
    for (int16_t nth = 0; nth < icons; nth++)
        (void)aes_gsx_pline(image, (int16_t)(x + point_x(image, corners, nth)), (int16_t)(y + point_y(image, corners, nth)),
                            count, outline);
    aes_desk_graf_mouse(image, GRAF_MOUSE_SHOW, DESK_NO_FORM);
}

/* $fdc4fe — gr_bwait: the outlines drawn at the rectangle's corner, gr_isdown over a GR_BWAIT_BOX square at the
 * mouse — its four answers into this frame, read by nothing —, the outlines drawn again (an XOR: rubbed out). Whether
 * the button is still down. */
int16_t aes_gr_bwait(uint8_t *image, uint32_t rect, int16_t mx, int16_t my, int16_t count, uint32_t outline, int16_t icons,
                     uint32_t corners)
{
    uint16_t answers_local[FRAME_LOCAL_WORDS(GR_BWAIT_FRAME_BYTES)];
    uint32_t answers = host_slot_claim(AES_GR_BWAIT_ANSWERS, answers_local);
    int16_t down;

    aes_gr_plns(image, (int16_t)bus_word(image, rect + GRECT_X), (int16_t)bus_word(image, rect + GRECT_Y), count, outline,
                icons, corners);
    down = aes_gr_isdown(image, GR_BWAIT_LEAVE, mx, my, GR_BWAIT_BOX, GR_BWAIT_BOX, answers + GR_BWAIT_MOUSE_X,
                         answers + GR_BWAIT_MOUSE_Y, answers + GR_BWAIT_BUTTON, answers + GR_BWAIT_KEYS);
    aes_gr_plns(image, (int16_t)bus_word(image, rect + GRECT_X), (int16_t)bus_word(image, rect + GRECT_Y), count, outline,
                icons, corners);
    host_slot_release(AES_GR_BWAIT_ANSWERS);
    return down;
}

/* $fdc86e — act_chkobj: `obj` where the rectangle (x, y, w, h) touches what of it is drawn — in the text view
 * (`root` not the desktop's) its line, DESK_TEXT_LINE_CHARS cells wide; in the icon view its icon's label or image
 * (the rectangle made relative to the object) —, else `root`. A view that is neither answers `obj`. */
int16_t aes_act_chkobj(uint8_t *image, uint32_t tree, int16_t root, int16_t obj, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t rects_local[FRAME_LOCAL_WORDS(ACT_CHKOBJ_FRAME_BYTES)];
    uint32_t rects = host_slot_claim(AES_ACT_CHKOBJ_RECTS, rects_local);
    uint32_t tested = rects + ACT_CHKOBJ_TESTED, object = rects + ACT_CHKOBJ_OBJECT;
    uint32_t desk = desk_globals(image);
    int16_t object_x = (int16_t)(object_word(image, tree, root, OB_X) + object_word(image, tree, obj, OB_X));
    int16_t object_y = (int16_t)(object_word(image, tree, root, OB_Y) + object_word(image, tree, obj, OB_Y));
    int16_t view = root == DESKTOP_ROOT ? V_ICON : (int16_t)bus_word(image, desk + DESK_G_IVIEW);
    int16_t touched = obj;

    if (view == V_TEXT) {
        aes_r_set(image, object, object_x, object_y, (int16_t)((int16_t)be16(image + AES_GL_WCHAR) * DESK_TEXT_LINE_CHARS),
                  (int16_t)be16(image + AES_GL_HCHAR));
        aes_r_set(image, tested, x, y, w, h);
        if (!aes_rc_intersect(image, object, tested))
            touched = root;
    } else if (view == V_ICON) {
        uint32_t icon = desk + DESK_G_IBLIST
                        + (uint32_t)((int16_t)bus_word(image, table_entry(desk + DESK_G_INDEX, obj, M68K_WORD_BYTES)) * IB_BYTES);

        aes_r_set(image, object, (int16_t)(x - object_x), (int16_t)(y - object_y), w, h);
        aes_r_set(image, tested, (int16_t)(x - object_x), (int16_t)(y - object_y), w, h);
        if (!aes_rc_intersect(image, icon + IB_XTEXT, object) && !aes_rc_intersect(image, icon + IB_XICON, tested))
            touched = root;
    }
    host_slot_release(AES_ACT_CHKOBJ_RECTS);
    return touched;
}

/* A rectangle's four words, read off the bus. */
/* $fdc268 — move_drvicon: each SELECTED desktop icon of `root` put down where the drag left it — its corner (x, y)
 * moved by its own of `corners`, snapped to the icons' grid by snap_disk into the object's own place —, the ANODE
 * it is shown by told the new place, and the desktop redrawn over the icon's old place and its new one. */
void aes_move_drvicon(uint8_t *image, uint32_t tree, int16_t root, int16_t x, int16_t y, uint32_t corners)
{
    uint32_t desk = desk_globals(image);
    int16_t moved = 0;

    for (int16_t obj = object_word(image, tree, root, OB_HEAD); obj > root; obj = object_word(image, tree, obj, OB_NEXT)) {
        int16_t old_x, old_y;

        if (!is_selected(image, tree, obj))
            continue;
        old_x = object_word(image, tree, obj, OB_X);
        old_y = object_word(image, tree, obj, OB_Y);
        aes_snap_disk(image, (int16_t)(x + point_x(image, corners, moved)), (int16_t)(y + point_y(image, corners, moved)),
                      object_address(tree, obj, OB_X), object_address(tree, obj, OB_Y));
        for (uint32_t node = bus_long(image, desk + DESK_ANODES_IN_USE); node != ANODE_NONE; node = bus_long(image, node + ANODE_NEXT))
            if ((int16_t)bus_word(image, node + ANODE_OBID) == obj) {
                set_bus_word(image, node + ANODE_XSPOT, (uint16_t)object_word(image, tree, obj, OB_X));
                set_bus_word(image, node + ANODE_YSPOT, (uint16_t)object_word(image, tree, obj, OB_Y));
            }
        aes_do_wredraw(image, MOVE_DRVICON_REDRAWN, old_x, old_y, (int16_t)bus_word(image, desk + DESK_G_WICON),
                       (int16_t)bus_word(image, desk + DESK_G_HICON));
        aes_do_wredraw(image, MOVE_DRVICON_REDRAWN, object_word(image, tree, obj, OB_X), object_word(image, tree, obj, OB_Y),
                       (int16_t)bus_word(image, desk + DESK_G_WICON), (int16_t)bus_word(image, desk + DESK_G_HICON));
        moved++;
    }
}

/* The object's rectangle copied to `rect` and moved by its root's place: where it lies on the screen. */
static void act_on_the_screen(uint8_t *image, uint32_t tree, int16_t root, int16_t obj, uint32_t rect)
{
    aes_rc_copy(image, object_address(tree, obj, OB_X), rect);
    set_bus_word(image, rect + GRECT_X, (uint16_t)(rect_word(image, rect, GRECT_X) + object_word(image, tree, root, OB_X)));
    set_bus_word(image, rect + GRECT_Y, (uint16_t)(rect_word(image, rect, GRECT_Y) + object_word(image, tree, root, OB_Y)));
}

static inline uint16_t changed_state(uint16_t state, int16_t value, int16_t set)
{
    return set ? (uint16_t)(state | (uint16_t)value) : (uint16_t)(state & ~(uint16_t)value);
}

/* The window's objects redrawn over the part of `rect` inside `clip` (rc_intersect leaves it there), where any is.
 * INLINED in both callers (W6-R4): a call of its own stands its four arguments and its return under do_wredraw, on a
 * deep path of PD0. */
__attribute__((always_inline)) static inline void act_redrawn_inside(uint8_t *image, int16_t window, uint32_t clip, uint32_t rect)
{
    if (aes_rc_intersect(image, clip, rect))
        aes_do_wredraw(image, window, rect_word(image, rect, GRECT_X), rect_word(image, rect, GRECT_Y),
                       rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
}

/* $fdc9e4 — act_chg: object `obj`'s state with `value` set or cleared — refused (ACT_CHG_REFUSED) where it is DISABLED
 * and the caller asks that checked —; where the state changes, objc_change over the clip (no redraw of its own), and
 * the window redrawn over the object's rectangle inside the clip where `draw` asks. */
int16_t aes_act_chg(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t obj, uint32_t clip, int16_t value,
                    int16_t set, int16_t draw, int16_t check_disabled)
{
    uint16_t rect_local[FRAME_LOCAL_WORDS(ACT_CHG_FRAME_BYTES)];
    uint32_t rect = host_slot_claim(AES_ACT_CHG_RECT, rect_local);
    uint16_t old_state = bus_word(image, object_address(tree, obj, OB_STATE));
    uint16_t state;

    if (check_disabled && old_state & OB_STATE_DISABLED) {
        host_slot_release(AES_ACT_CHG_RECT);
        return ACT_CHG_REFUSED;
    }
    act_on_the_screen(image, tree, root, obj, rect);
    state = changed_state(old_state, value, set);
    if (state != old_state) {
        aes_desk_objc_change(image, tree, obj, ACT_CHG_OBJC_CHANGE_UNREAD, rect_word(image, clip, GRECT_X),
                             rect_word(image, clip, GRECT_Y), rect_word(image, clip, GRECT_W), rect_word(image, clip, GRECT_H),
                             (int16_t)state, ACT_CHG_NO_REDRAW);
        if (draw)
            act_redrawn_inside(image, window, clip, rect);
    }
    host_slot_release(AES_ACT_CHG_RECT);
    return ACT_CHG_DONE;
}

/* $fdcabc — act_allchg: every icon of `root` but `except` whose rectangle touches `rect` — and whose image or label
 * the touched part touches (act_chkobj) — with `value` set or cleared in its state, stored by hand; the extent of
 * those that changed gathered (rc_union, the first copied), and the window redrawn over it inside the clip where
 * `draw` asks. */
void aes_act_allchg(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t except, uint32_t rect,
                    uint32_t clip, int16_t value, int16_t set, int16_t draw)
{
    uint16_t rects_local[FRAME_LOCAL_WORDS(ACT_ALLCHG_FRAME_BYTES)];
    uint32_t rects = host_slot_claim(AES_ACT_ALLCHG_RECTS, rects_local);
    uint32_t extent = rects + ACT_ALLCHG_EXTENT, object = rects + ACT_ALLCHG_OBJECT;

    set_bus_word(image, extent + GRECT_H, 0);
    set_bus_word(image, extent + GRECT_W, 0);
    for (int16_t obj = object_word(image, tree, root, OB_HEAD); obj > root; obj = object_word(image, tree, obj, OB_NEXT)) {
        uint16_t state;

        if (obj == except)
            continue;
        act_on_the_screen(image, tree, root, obj, object);
        if (!aes_rc_intersect(image, rect, object)
            || aes_act_chkobj(image, tree, root, obj, rect_word(image, object, GRECT_X), rect_word(image, object, GRECT_Y),
                              rect_word(image, object, GRECT_W), rect_word(image, object, GRECT_H)) == root)
            continue;
        state = changed_state(bus_word(image, object_address(tree, obj, OB_STATE)), value, set);
        if (state == bus_word(image, object_address(tree, obj, OB_STATE)))
            continue;
        set_object_word(image, tree, obj, OB_STATE, (int16_t)state);
        act_on_the_screen(image, tree, root, obj, object);
        if (rect_word(image, extent, GRECT_W))
            aes_rc_union(image, object, extent);
        else
            aes_rc_copy(image, object, extent);
    }
    if (draw)
        act_redrawn_inside(image, window, clip, extent);
    host_slot_release(AES_ACT_ALLCHG_RECTS);
}

/* ---- band 6 wave 2, group G4: the drag's loop and the button's two handlers ---------------------------------------- */
_Static_assert(DRGPLNS_FRAME_BYTES == HOST_SLOT_AES_GR_DRGPLNS_FRAME_BYTES, "gr_drgplns's frame and its host slot");
_Static_assert(ACT_BDOWN_FRAME_BYTES == HOST_SLOT_AES_ACT_BDOWN_FRAME_BYTES, "act_bdown's frame and its host slot");

/* The icon lit under a drag — the window, tree, root and object act_chg was handed — and its light put out again. */
struct lit_icon {
    int16_t window;
    uint32_t tree;
    int16_t root;
    int16_t object;
};

static void lit_icon_put_out(uint8_t *image, struct lit_icon *lit, uint32_t clip)
{
    (void)aes_act_chg(image, lit->window, lit->tree, lit->root, lit->object, clip, OB_STATE_SELECTED, 0, 1, 1);
    *lit = (struct lit_icon){0, 0, 0, DRGPLNS_NO_OBJECT};
}

/* An icon a drag may be let go on: a folder, a disk, the cartridge or the trash — not a file. (The ROM reads i_find's
 * ANODE with no test of it: a file's object has one.) */
static int takes_a_drop(const uint8_t *image, uint32_t anode)
{
    uint16_t type = bus_word(image, anode + ANODE_TYPE);

    return type == AT_ISFOLD || type == AT_ISDISK || type == AT_ISCART || type == AT_ISTRSH;
}

/* $fdc57a — gr_drgplns: THE DRAG. The outline's extent and the icons' (their corners made relative to it, its size
 * grown by the outline's), then until the button comes up: the mouse read (graf_mkstate, into the two argument words
 * — the ROM's own frame), the icons' rectangle moved with it inside the clip, the outlines drawn and rubbed out round
 * the wait (gr_bwait); the window under the mouse (a desk window's tree and root, else the desktop's), the icon under
 * it (gr_obfind, stored at once through `object_out`) — an unselected folder, disk, cartridge or trash LIT, the one lit
 * before put out. At the end the last one put out, and the icons' corner and the window stored through the pointers. */
void aes_gr_drgplns(uint8_t *image, int16_t mx, int16_t my, uint32_t clip, int16_t count, uint32_t outline, int16_t icons,
                    uint32_t corners, uint32_t x_out, uint32_t y_out, uint32_t window_out, uint32_t object_out)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(DRGPLNS_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_GR_DRGPLNS_FRAME, frame_local);
    uint32_t extent = frame + DRGPLNS_OUTLINE_EXTENT, rect = frame + DRGPLNS_ICONS_RECT;
    uint32_t mouse_x = frame + DRGPLNS_MOUSE_X, mouse_y = frame + DRGPLNS_MOUSE_Y;
    struct lit_icon lit = {0, 0, 0, DRGPLNS_NO_OBJECT};
    int16_t off_x, off_y, down, window, root, object;
    uint32_t tree, wnode;

    set_bus_word(image, mouse_x, (uint16_t)mx);
    set_bus_word(image, mouse_y, (uint16_t)my);
    aes_gr_extent(image, count, outline, extent);
    aes_gr_extent(image, icons, corners, rect);
    set_bus_word(image, rect + GRECT_W, (uint16_t)(rect_word(image, rect, GRECT_W) + rect_word(image, extent, GRECT_W)));
    set_bus_word(image, rect + GRECT_H, (uint16_t)(rect_word(image, rect, GRECT_H) + rect_word(image, extent, GRECT_H)));
    aes_gr_obalign(image, icons, rect_word(image, rect, GRECT_X), rect_word(image, rect, GRECT_Y), corners);
    off_x = (int16_t)(mx - rect_word(image, rect, GRECT_X));
    off_y = (int16_t)(my - rect_word(image, rect, GRECT_Y));
    do {
        (void)aes_gsx_sclip(image, AES_GL_RSCREEN);
        aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_XOR, DRGPLNS_OUTLINE_COLOUR);
        aes_desk_graf_mkstate(image, mouse_x, mouse_y, frame + DRGPLNS_BUTTON, frame + DRGPLNS_KEYS);
        mx = (int16_t)bus_word(image, mouse_x);
        my = (int16_t)bus_word(image, mouse_y);
        set_bus_word(image, rect + GRECT_X, (uint16_t)(mx - off_x));
        set_bus_word(image, rect + GRECT_Y, (uint16_t)(my - off_y));
        aes_rc_constrain(image, clip, rect);
        down = aes_gr_bwait(image, rect, mx, my, count, outline, icons, corners);
        window = aes_desk_wind_find(image, mx, my);
        tree = bus_long(image, desk_globals(image) + DESK_G_SCREEN);
        root = DESKTOP_ROOT;
        if (window) {
            wnode = aes_win_find(image, window);
            if (wnode) {
                tree = bus_long(image, desk_globals(image) + DESK_G_SCREEN);
                root = (int16_t)bus_word(image, wnode + WNODE_ROOT);
            } else {
                window = 0;
            }
        }
        object = aes_gr_obfind(image, tree, root, mx, my);
        set_bus_word(image, object_out, (uint16_t)object);
        if (object == root || object == OB_NIL) {
            if (lit.object)
                lit_icon_put_out(image, &lit, clip);
        } else if (object != lit.object) {
            if (lit.object)
                lit_icon_put_out(image, &lit, clip);
            if (!is_selected(image, tree, object)
                && takes_a_drop(image, aes_i_find(image, window, object, frame + DRGPLNS_FNODE, frame + DRGPLNS_IS_APP))) {
                lit = (struct lit_icon){window, tree, root, object};
                (void)aes_act_chg(image, window, tree, root, object, clip, OB_STATE_SELECTED, 1, 1, 1);
            }
        }
    } while (down);
    if (lit.object)
        lit_icon_put_out(image, &lit, clip);
    set_bus_word(image, x_out, (uint16_t)rect_word(image, rect, GRECT_X));
    set_bus_word(image, y_out, (uint16_t)rect_word(image, rect, GRECT_Y));
    set_bus_word(image, window_out, (uint16_t)window);
    host_slot_release(AES_GR_DRGPLNS_FRAME);
}

/* $fdcc2a — act_bsclick: A CLICK. On no icon (the root, or none) every icon of the root put out; on one, with no Shift
 * key: the others put out first where it is double-clicked or not yet selected, and it SELECTED; with a Shift key: it
 * TOGGLED alone. (act_chg, drawn, the disabled check asked.) */
void aes_act_bsclick(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t mx, int16_t my, int16_t keys,
                     uint32_t clip, int16_t double_click)
{
    int shifted = (keys & SHIFT_KEYS) != 0;
    int16_t object = aes_gr_obfind(image, tree, root, mx, my);
    uint16_t state;

    if (object == root || object == OB_NIL) {
        aes_act_allchg(image, window, tree, root, object, AES_GL_RFULL, clip, OB_STATE_SELECTED, 0, 1);
        return;
    }
    state = bus_word(image, object_address(tree, object, OB_STATE));
    if (!shifted) {
        if (double_click || !(state & OB_STATE_SELECTED)) {
            aes_act_allchg(image, window, tree, root, object, AES_GL_RFULL, clip, OB_STATE_SELECTED, 0, 1);
            state |= OB_STATE_SELECTED;
        }
    } else {
        state ^= OB_STATE_SELECTED;
    }
    (void)aes_act_chg(image, window, tree, root, object, clip, OB_STATE_SELECTED, (int16_t)(state & OB_STATE_SELECTED), 1, 1);
}

/* The outline a drag of the selection carries: the icon view's, from the desktop's root or a window of icons; the text
 * view's from a window of text. Its point count through `count`. */
static uint32_t drag_outline(const uint8_t *image, int16_t root, int16_t *count)
{
    uint32_t desk = desk_globals(image);
    int16_t view = root == DESKTOP_ROOT ? V_ICON : (int16_t)bus_word(image, desk + DESK_G_IVIEW);

    if (view == V_ICON) {
        *count = (int16_t)bus_word(image, desk + DESK_G_NMICON);
        return desk + DESK_G_XYICON;
    }
    *count = (int16_t)bus_word(image, desk + DESK_G_NMTEXT);
    return desk + DESK_G_XYTEXT;
}

/* act_bdown's press on a selected icon: the selection's corners gathered and dragged; a drop back onto the icon it
 * began on — or, from the desktop, onto the bare desktop, the icons put down there (move_drvicon) — is no drop. */
static void dragged_selection(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t object, uint32_t frame,
                              uint32_t object_out)
{
    uint32_t corners = desk_globals(image) + DESK_G_XYOBPTS, outline;
    uint32_t drop_window = frame + ACT_BDOWN_DROP_WINDOW;
    int16_t icons, count;

    aes_gr_accobs(image, tree, root, frame + ACT_BDOWN_COUNT, corners);
    icons = (int16_t)bus_word(image, frame + ACT_BDOWN_COUNT);
    if (!icons)
        return;
    outline = drag_outline(image, root, &count);
    aes_gr_drgplns(image, (int16_t)bus_word(image, frame + ACT_BDOWN_MOUSE_X), (int16_t)bus_word(image, frame + ACT_BDOWN_MOUSE_Y),
                   AES_GL_RFULL, count, outline, icons, corners, frame + ACT_BDOWN_DROP_X, frame + ACT_BDOWN_DROP_Y,
                   drop_window, object_out);
    if (bus_word(image, drop_window)) {
        if (window == (int16_t)bus_word(image, drop_window) && (int16_t)bus_word(image, object_out) == object)
            set_bus_word(image, drop_window, (uint16_t)ACT_BDOWN_NOTHING);
    } else if (!window && (int16_t)bus_word(image, object_out) == root) {
        aes_move_drvicon(image, tree, root, (int16_t)bus_word(image, frame + ACT_BDOWN_DROP_X),
                         (int16_t)bus_word(image, frame + ACT_BDOWN_DROP_Y), corners);
        set_bus_word(image, drop_window, (uint16_t)ACT_BDOWN_NOTHING);
    }
}

/* $fdcd34 — act_bdown: A PRESS. The root stored through `object_out`; on no icon a rubber box from the mouse (the
 * icons it holds lit); on a SELECTED icon the selection dragged (`dragged_selection`); then the button awaited up
 * (evnt_button, its answers into the argument words — the ROM's own frame, read by no caller). The window the drag
 * was let go over, ACT_BDOWN_NOTHING where there was no drop. */
int16_t aes_act_bdown(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t mx, int16_t my, int16_t keys,
                      uint32_t clip, uint32_t object_out)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(ACT_BDOWN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_ACT_BDOWN_FRAME, frame_local);
    uint32_t box = frame + ACT_BDOWN_BOX;
    int16_t object, dropped;

    set_bus_word(image, frame + ACT_BDOWN_MOUSE_X, (uint16_t)mx);
    set_bus_word(image, frame + ACT_BDOWN_MOUSE_Y, (uint16_t)my);
    set_bus_word(image, frame + ACT_BDOWN_KEYS, (uint16_t)keys);
    set_bus_word(image, frame + ACT_BDOWN_DROP_WINDOW, (uint16_t)ACT_BDOWN_NOTHING);
    set_bus_word(image, object_out, (uint16_t)root);
    object = aes_gr_obfind(image, tree, root, mx, my);
    if (root == object || object == OB_NIL) {
        aes_r_set(image, box, mx, my, RUBBER_BOX_MIN, RUBBER_BOX_MIN);
        aes_desk_graf_rubbox(image, rect_word(image, box, GRECT_X), rect_word(image, box, GRECT_Y), RUBBER_BOX_MIN,
                             RUBBER_BOX_MIN, box + GRECT_W, box + GRECT_H);
        aes_act_allchg(image, window, tree, root, object, box, clip, OB_STATE_SELECTED, 1, 1);
    } else if (is_selected(image, tree, object)) {
        dragged_selection(image, window, tree, root, object, frame, object_out);
    }
    (void)aes_desk_evnt_button(image, ACT_BDOWN_CLICKS, ACT_BDOWN_MASK, ACT_BDOWN_STATE, frame + ACT_BDOWN_MOUSE_X,
                               frame + ACT_BDOWN_MOUSE_Y, frame + ACT_BDOWN_BUTTON, frame + ACT_BDOWN_KEYS);
    dropped = (int16_t)bus_word(image, frame + ACT_BDOWN_DROP_WINDOW);
    host_slot_release(AES_ACT_BDOWN_FRAME);
    return dropped;
}
