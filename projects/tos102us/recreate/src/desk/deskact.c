/* deskact.c — THE DESK'S HIT TESTS AND ICON DRAGS (`desk/deskact.h`): `$fdc080..$fdcc29` less the drag loops (wave
 * 2's). Alcyon C in the ROM, ported over its own order; the bindings it calls are unit D's (`desk/deskbind.h`).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/evdoor.h"
#include "aes/gemsuper.h"
#include "aes/objects.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskleaf.h"
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

/* The window's objects redrawn over the part of `rect` inside `clip` (rc_intersect leaves it there), where any is. */
static void act_redrawn_inside(uint8_t *image, int16_t window, uint32_t clip, uint32_t rect)
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
