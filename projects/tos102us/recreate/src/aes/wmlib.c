/* wmlib.c — the WINDOW LIBRARY's half that never waits on an event (`aes/wmlib.h`): the gadget tree W_ACTIVE built
 * for one window (w_nilit, w_obadd, w_adjust, w_hvassign, w_barcalc, w_bldbar, w_bldactive) and drawn through the
 * window's visible rectangles (w_clipdraw, w_cpwalk, w_strchg, w_drawdesk), a moved window's image blitted (w_mvfix,
 * w_move), a rectangle list walked (w_owns, w_union), and the records kept — wm_start, wm_create, wm_delete, wm_get,
 * wm_find, wm_calc.
 *
 * Every GRECT the ROM keeps in its frame and hands on by address is a host slot off target (`host_slot.h`); a GRECT
 * it keeps only to read back is C locals. Every word sum is a word that wraps, every compare signed, as the ROM's
 * `add.w` / `cmp.w`.
 */
#include <stdint.h>

#include "machine.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsxif.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/rect.h"
#include "aes/rlist.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wrect.h"

#define W_TREE_BYTES          (AES_WINDOW_COUNT * OB_BYTES)     /* wm_start's clear ($fec436 move.w #192)      */
#define W_ACTIVE_BYTES        (W_ACTIVE_OBJECTS * OB_BYTES)     /* ...and W_ACTIVE's  ($fec4b8 move.w #456)    */
#define WM_FIND_DEPTH         2          /* the root and the windows: no deeper ($feca52 move.w #2)             */
#define CLEAR_BYTE            0          /* wm_start's bfill value              ($fec436 clr.w)                 */
#define MOVE_GAP_WIDTH        1          /* w_move's uncovered strip, one pixel wide ($febfe8 move.w #1)        */

/* The kind's groups are the ROM's literals; each is the gadgets it names. */
_Static_assert(WK_TITLE_BAR == (WK_NAME | WK_CLOSER | WK_FULLER), "the title bar's gadgets");
_Static_assert(WK_VERTICAL_BAR == (WK_SIZER | WK_UPARROW | WK_DNARROW | WK_VSLIDE), "the vertical bar's gadgets");
_Static_assert(WK_HORIZONTAL_BAR == (WK_SIZER | WK_LFARROW | WK_RTARROW | WK_HSLIDE), "the horizontal bar's gadgets");
_Static_assert(W_ACTIVE_ROOT_STATE == 1 << OB_STATE_SHADOWED_BIT, "W_ACTIVE's root is SHADOWED");

/* W_ACTIVE's types and specs, as wm_start sets them from its two ROM tables ($fefc3c words, $fefc62 longwords). */
static const uint8_t w_active_types[W_ACTIVE_OBJECTS] = {
    G_IBOX, G_BOX, G_BOXCHAR, G_BOXTEXT, G_BOXCHAR, G_BOXTEXT, G_IBOX, G_IBOX, G_BOXCHAR, G_BOX,
    G_BOXCHAR, G_BOXCHAR, G_BOX, G_BOX, G_BOX, G_BOXCHAR, G_BOXCHAR, G_BOX, G_BOX,
};
static const uint32_t w_active_specs[W_ACTIVE_OBJECTS] = {
    0x00011101, 0x00011101, 0x05011101, 0x00000000, 0x07011101, 0x00000000, 0x00001101, 0x00001101, 0x06011101,
    0x00011101, 0x01011101, 0x02011101, 0x00011111, 0x00011101, 0x00011101, 0x04011101, 0x03011101, 0x00011111,
    0x00011101,
};

static inline uint32_t w_active(int16_t object, uint32_t field)
{
    return object_address(AES_W_ACTIVE, object, field);
}

static inline int16_t global_word(const uint8_t *image, uint32_t global)
{
    return (int16_t)be16(image + global);
}

static inline int16_t record_word(const uint8_t *image, int16_t window, uint32_t field)
{
    return (int16_t)bus_word(image, window_record(window) + field);
}

/* An object's next, head and tail made -1 — the ROM's order: tail, head, then (w_nilit alone) next. */
static void unlink_object(uint8_t *image, uint32_t objects, int16_t object)
{
    set_object_word(image, objects, object, OB_TAIL, OB_NIL);
    set_object_word(image, objects, object, OB_HEAD, OB_NIL);
}

/* $feb3c0 — the last `count` objects of the array at `objects`, last first, each with no link. The count is a word
 * counted down to 0 (`subq.w`, then the old value tested), so a negative one runs on round the word. */
void aes_w_nilit(uint8_t *image, int16_t count, uint32_t objects)
{
    uint16_t left = (uint16_t)count;

    while (left-- != 0) {
        unlink_object(image, objects, (int16_t)left);
        set_object_word(image, objects, (int16_t)left, OB_NEXT, OB_NIL);
    }
}

/* $feb408 — ob_add's body over a bare object array (the same instructions, the same order): `child` linked in as
 * `parent`'s last child, nothing done when either is -1. */
void aes_w_obadd(uint8_t *image, uint32_t objects, int16_t parent, int16_t child)
{
    aes_ob_add(image, objects, parent, child);
}

/* $feb47a — window `window`'s record claimed for `pd`: its owner, IN USE (the other flags kept), its kind, both
 * sliders at 0 and both slider sizes -1 (the default size). */
void aes_w_setup(uint8_t *image, uint32_t pd, int16_t window, int16_t kind)
{
    uint32_t record = window_record(window);

    set_bus_long(image, record + WIN_OWNER, pd);
    set_bus_word(image, record + WIN_FLAGS, (uint16_t)(bus_word(image, record + WIN_FLAGS) | WIN_IN_USE));
    set_bus_word(image, record + WIN_KIND, (uint16_t)kind);
    set_bus_word(image, record + WIN_VSLIDE, 0);
    set_bus_word(image, record + WIN_HSLIDE, 0);
    set_bus_word(image, record + WIN_VSLSIZE, (uint16_t)OB_NIL);
    set_bus_word(image, record + WIN_HSLSIZE, (uint16_t)OB_NIL);
}

/* $feb57c — the GRECT at `rect` copied into window `window`'s rectangle `which` (`aes/wrect.h`'s WS_*). */
void aes_w_setsize(uint8_t *image, int16_t which, int16_t window, uint32_t rect)
{
    aes_rc_copy(image, rect, aes_w_getxptr(which, window));
}

/* $feb594 — W_ACTIVE's `object` placed at (x, y, w, h) — the ROM rc_copies its own four argument words — with no
 * children, and added as `parent`'s last child. */
void aes_w_adjust(uint8_t *image, int16_t parent, int16_t object, int16_t x, int16_t y, int16_t w, int16_t h)
{
    set_object_word(image, AES_W_ACTIVE, object, OB_X, x);
    set_object_word(image, AES_W_ACTIVE, object, OB_Y, y);
    set_object_word(image, AES_W_ACTIVE, object, OB_WIDTH, w);
    set_object_word(image, AES_W_ACTIVE, object, OB_HEIGHT, h);
    unlink_object(image, AES_W_ACTIVE, object);
    aes_w_obadd(image, AES_W_ACTIVE, parent, object);
}

/* $feb5f8 — a gadget of a scroll bar placed the bar's way: a vertical one at (vertical_x, vertical_y), a box wide
 * and `h` high; a horizontal one at (horizontal_x, horizontal_y), `w` wide and a box high. */
void aes_w_hvassign(uint8_t *image, int16_t vertical, int16_t parent, int16_t object, int16_t vertical_x,
                    int16_t vertical_y, int16_t horizontal_x, int16_t horizontal_y, int16_t w, int16_t h)
{
    if (vertical)
        aes_w_adjust(image, parent, object, vertical_x, vertical_y, global_word(image, AES_GL_WBOX), h);
    else
        aes_w_adjust(image, parent, object, horizontal_x, horizontal_y, w, global_word(image, AES_GL_HBOX));
}

/* $feb646 — `object` of `tree` drawn to `depth` once per visible rectangle of window `window` that meets `clip`
 * (gl_rfull when 0; a clip handed in is cut to gl_rfull IN PLACE first). Nothing is drawn, and 1 answered, while
 * window drawing is held or for window -1; else 0, the list's end, which the ROM's loop test leaves in D0. Each link
 * is read after the rectangle's draw, the list's head after the clip's cut, as the ROM reads them. */
int16_t aes_w_clipdraw(uint8_t *image, int16_t window, uint32_t tree, int16_t object, int16_t depth, uint32_t clip)
{
    uint16_t piece_local[GRECT_WORDS];
    uint32_t piece, orect;
    _Static_assert(sizeof piece_local == HOST_SLOT_AES_W_CLIPDRAW_RECT_BYTES, "w_clipdraw's GRECT and its host slot");

    if (global_word(image, AES_GL_WFROZEN) || window == OB_NIL)
        return 1;
    if (clip)
        aes_rc_intersect(image, AES_GL_RFULL, clip);
    else
        clip = AES_GL_RFULL;
    piece = host_slot_claim(AES_W_CLIPDRAW_RECT, piece_local);
    for (orect = bus_long(image, window_record(window) + WIN_RLIST); orect; orect = bus_long(image, orect + ORECT_LINK)) {
        aes_rc_copy(image, orect + ORECT_X, piece);
        if (aes_rc_intersect(image, clip, piece)) {
            aes_gsx_sclip(image, piece);
            aes_ob_draw(image, tree, object, depth);
        }
    }
    host_slot_release(AES_W_CLIPDRAW_RECT);
    return 0;
}

/* A GRECT's width and height each grown by `by`, in place (`addq.w` twice: each word wraps). */
static void grow_extent(uint8_t *image, uint32_t rect, int16_t by)
{
    set_bus_word(image, rect + GRECT_W, (uint16_t)(bus_word(image, rect + GRECT_W) + by));
    set_bus_word(image, rect + GRECT_H, (uint16_t)(bus_word(image, rect + GRECT_H) + by));
}

/* $feb6c8 — the desktop redrawn under `rect`, its width and height first grown by the border IN PLACE: the desk's
 * own tree from its root to the whole depth when one is set (gl_newdesk, gl_newroot), else the window tree's root
 * alone. */
void aes_w_drawdesk(uint8_t *image, uint32_t rect)
{
    uint32_t tree = be32(image + AES_GL_NEWDESK);
    int16_t depth = 0, root = OB_ROOT;

    if (tree) {
        depth = WM_MAX_DEPTH;
        root = global_word(image, AES_GL_NEWROOT);
    } else {
        tree = be32(image + AES_GL_WTREE);
    }
    grow_extent(image, rect, W_BORDER);
    aes_w_clipdraw(image, WM_DESKTOP, tree, root, depth, rect);
}

/* $feb712 — window `window`'s gadgets built (w_bldactive) and `object` of them drawn to `depth`: under the window's
 * whole rectangle when it is the top window or `use_true` says so, else under the clip as it stands, grown by the
 * border. */
void aes_w_cpwalk(uint8_t *image, int16_t window, int16_t object, int16_t depth, int16_t use_true)
{
    uint16_t under_local[GRECT_WORDS];
    _Static_assert(sizeof under_local == HOST_SLOT_AES_W_CPWALK_RECT_BYTES, "w_cpwalk's GRECT and its host slot");
    uint32_t under = host_slot_claim(AES_W_CPWALK_RECT, under_local);

    if (window == global_word(image, AES_GL_WTOP) || use_true) {
        aes_w_getsize(image, WS_TRUE, window, under);
    } else {
        aes_gsx_gclip(image, under);
        grow_extent(image, under, W_BORDER);
    }
    aes_w_bldactive(image, window);
    aes_w_clipdraw(image, window, be32(image + AES_GL_AWIND), object, depth, under);
    host_slot_release(AES_W_CPWALK_RECT);
}

/* $feb768 — window `window`'s title (W_NAME) or, for any other object, information line set to `text` — in its
 * record and in the TEDINFO the gadget is drawn from — and the gadget drawn whole, under its whole rectangle. */
void aes_w_strchg(uint8_t *image, int16_t window, int16_t object, uint32_t text)
{
    if (object == W_NAME) {
        set_bus_long(image, window_record(window) + WIN_NAME, text);
        wr32(image + AES_GL_ANAME + TE_PTEXT, text);
    } else {
        set_bus_long(image, window_record(window) + WIN_INFO, text);
        wr32(image + AES_GL_AINFO + TE_PTEXT, text);
    }
    aes_w_cpwalk(image, window, object, WM_MAX_DEPTH, 1);
}

/* $feb7ca — a slider's elevator laid in a track `space` long: its size `size` per mille of the track (no less than
 * `minimum`; -1 is `minimum` itself) and its position `value` per mille of what is left — at (0, position, a box,
 * size) in the GRECT at `vertical_rect` for a vertical slider, at (position, 0, size, a box) in `horizontal_rect`
 * for a horizontal one. */
void aes_w_barcalc(uint8_t *image, int16_t vertical, int16_t space, int16_t value, int16_t size, int16_t minimum,
                   uint32_t vertical_rect, uint32_t horizontal_rect)
{
    int16_t position;

    if (size == OB_NIL)
        size = minimum;
    else
        size = aes_max(minimum, aes_mul_div(size, space, W_SLIDER_SCALE));
    position = aes_mul_div((int16_t)(space - size), value, W_SLIDER_SCALE);
    if (vertical)
        aes_r_set(image, vertical_rect, 0, position, global_word(image, AES_GL_WBOX), size);
    else
        aes_r_set(image, horizontal_rect, position, 0, size, global_word(image, AES_GL_HBOX));
}

/* One scroll bar's gadgets, by its direction: the kind bits that ask for them, their W_ACTIVE objects, and the size
 * of an arrow along the bar (a box's height down a vertical bar, its width along a horizontal one). */
struct scroll_bar {
    uint16_t first_arrow, second_arrow, slider;
    int16_t first_arrow_object, second_arrow_object, slider_object, elevator_object;
    uint32_t arrow_global;
};

static const struct scroll_bar vertical_bar = {
    WK_UPARROW, WK_DNARROW, WK_VSLIDE, W_UPARROW, W_DNARROW, W_VSLIDE, W_VELEV, AES_GL_HBOX,
};
static const struct scroll_bar horizontal_bar = {
    WK_LFARROW, WK_RTARROW, WK_HSLIDE, W_LFARROW, W_RTARROW, W_HSLIDE, W_HELEV, AES_GL_WBOX,
};

/* A gadget's length less the one border line it shares with the next. */
static inline int16_t overlapped(const uint8_t *image, uint32_t box_global)
{
    return (int16_t)(global_word(image, box_global) - W_BAR_OVERLAP);
}

/* $feb84e — scroll bar `bar` (W_VBAR or, any other, the horizontal one) placed at (x, y, w, h) in W_DATA, and — on the
 * top window only — its gadgets the window's `kind` asks for laid in it: the first arrow at its start, the second
 * at its end, the slider's track between them holding the elevator w_barcalc sizes from `value` and `size`. */
void aes_w_bldbar(uint8_t *image, int16_t kind, int16_t is_top, int16_t bar, int16_t value, int16_t size, int16_t x,
                  int16_t y, int16_t w, int16_t h)
{
    int16_t vertical = bar == W_VBAR;
    const struct scroll_bar *gadgets = vertical ? &vertical_bar : &horizontal_bar;
    int16_t arrow = global_word(image, gadgets->arrow_global);

    aes_w_hvassign(image, vertical, W_DATA, bar, x, y, x, y, w, h);
    x = y = 0;
    if (!is_top)
        return;
    if (kind & gadgets->first_arrow) {
        aes_w_adjust(image, bar, gadgets->first_arrow_object, x, y, global_word(image, AES_GL_WBOX),
                     global_word(image, AES_GL_HBOX));
        if (vertical) {
            y = (int16_t)(y + overlapped(image, AES_GL_HBOX));
            h = (int16_t)(h - overlapped(image, AES_GL_HBOX));
        } else {
            x = (int16_t)(x + overlapped(image, AES_GL_WBOX));
            w = (int16_t)(w - overlapped(image, AES_GL_WBOX));
        }
    }
    if (kind & gadgets->second_arrow) {
        w = (int16_t)(w - overlapped(image, AES_GL_WBOX));
        h = (int16_t)(h - overlapped(image, AES_GL_HBOX));
        aes_w_hvassign(image, vertical, bar, gadgets->second_arrow_object, x, (int16_t)(y + h - W_BAR_OVERLAP),
                       (int16_t)(x + w - W_BAR_OVERLAP), y, global_word(image, AES_GL_WBOX), global_word(image, AES_GL_HBOX));
    }
    if (!(kind & gadgets->slider))
        return;
    aes_w_hvassign(image, vertical, bar, gadgets->slider_object, x, y, x, y, w, h);
    aes_w_barcalc(image, vertical, vertical ? h : w, value, size, arrow, w_active(W_VELEV, OB_X),
                  w_active(W_HELEV, OB_X));
    unlink_object(image, AES_W_ACTIVE, gadgets->elevator_object);
    aes_w_obadd(image, AES_W_ACTIVE, gadgets->slider_object, gadgets->elevator_object);
}

/* A gadget of the title bar, a box square, at the title bar's (x, y). */
static void title_gadget(uint8_t *image, int16_t object, int16_t x, int16_t y)
{
    aes_w_adjust(image, W_TITLE, object, x, y, global_word(image, AES_GL_WBOX), global_word(image, AES_GL_HBOX));
}

/* w_bldactive's body, apart from its one test so that window -1 costs no more than the ROM's `cmp` and return: the
 * body's register saves alone priced the bare test over the ROM's. */
static __attribute__((noinline)) void build_active(uint8_t *image, int16_t window)
{
    int16_t is_top, kind, x, y, w, h, title_width, vertical, horizontal;
    uint32_t record = window_record(window), place = aes_w_getxptr(WS_CURR, window);

    is_top = window == global_word(image, AES_GL_WTOP);
    kind = (int16_t)bus_word(image, record + WIN_KIND);
    aes_w_nilit(image, W_ACTIVE_OBJECTS, AES_W_ACTIVE);
    wr32(image + AES_GL_ANAME + TE_PTEXT, bus_long(image, record + WIN_NAME));
    wr32(image + AES_GL_AINFO + TE_PTEXT, bus_long(image, record + WIN_INFO));
    w = (int16_t)bus_word(image, place + GRECT_W);
    h = (int16_t)bus_word(image, place + GRECT_H);
    aes_rc_copy(image, place, w_active(W_BOX, OB_X));
    x = y = 0;
    if (kind & WK_TITLE_BAR) {
        aes_w_adjust(image, W_BOX, W_TITLE, x, y, w, global_word(image, AES_GL_HBOX));
        title_width = w;
        if ((kind & WK_CLOSER) && is_top) {
            title_gadget(image, W_CLOSER, x, y);
            x = (int16_t)(x + global_word(image, AES_GL_WBOX));
            title_width = (int16_t)(title_width - global_word(image, AES_GL_WBOX));
        }
        if ((kind & WK_FULLER) && is_top) {
            title_width = (int16_t)(title_width - global_word(image, AES_GL_WBOX));
            title_gadget(image, W_FULLER, (int16_t)(title_width + x), y);
        }
        if (kind & WK_NAME) {
            aes_w_adjust(image, W_TITLE, W_NAME, x, y, title_width, global_word(image, AES_GL_HBOX));
            wr16(image + AES_GL_ANAME + TE_COLOR, is_top ? W_NAME_COLOUR_TOP : W_NAME_COLOUR);
        }
        x = 0;
        y = (int16_t)(y + overlapped(image, AES_GL_HBOX));
        h = (int16_t)(h - overlapped(image, AES_GL_HBOX));
    }
    if (kind & WK_INFO) {
        aes_w_adjust(image, W_BOX, W_INFO, x, y, w, global_word(image, AES_GL_HBOX));
        y = (int16_t)(y + overlapped(image, AES_GL_HBOX));
        h = (int16_t)(h - overlapped(image, AES_GL_HBOX));
    }
    aes_w_adjust(image, W_BOX, W_DATA, x, y, w, h);
    w = (int16_t)(w - 2 * W_EDGE);
    h = (int16_t)(h - 2 * W_EDGE);
    vertical = kind & WK_VERTICAL_BAR;
    horizontal = kind & WK_HORIZONTAL_BAR;
    if (vertical)
        w = (int16_t)(w - overlapped(image, AES_GL_WBOX));
    if (horizontal)
        h = (int16_t)(h - overlapped(image, AES_GL_HBOX));
    x = y = W_EDGE;
    aes_w_adjust(image, W_DATA, W_WORK, x, y, w, h);
    if (vertical) {
        x = (int16_t)(x + w);
        aes_w_bldbar(image, kind, is_top, W_VBAR, record_word(image, window, WIN_VSLIDE),
                     record_word(image, window, WIN_VSLSIZE), x, 0, (int16_t)(w + W_BORDER), (int16_t)(h + W_BORDER));
    }
    if (horizontal) {
        y = (int16_t)(y + h);
        aes_w_bldbar(image, kind, is_top, W_HBAR, record_word(image, window, WIN_HSLIDE),
                     record_word(image, window, WIN_HSLSIZE), 0, y, (int16_t)(w + W_BORDER), (int16_t)(h + W_BORDER));
    }
    if (vertical && horizontal) {
        aes_w_adjust(image, W_DATA, W_SIZER, x, y, global_word(image, AES_GL_WBOX), global_word(image, AES_GL_HBOX));
        wr32(image + w_active(W_SIZER, OB_SPEC), is_top && (kind & WK_SIZER) ? W_SIZER_SPEC_TOP : W_SIZER_SPEC);
    }
}

/* $feba9c — W_ACTIVE built for window `window` (nothing for -1): every object unlinked, the title's and information
 * line's TEDINFOs pointed at the window's strings, the root placed where the window is, then — down from its top
 * edge — the title bar (closer, fuller and name on the top window, the name alone on any other), the information line,
 * W_DATA holding the work area, and the scroll bars and sizer the kind asks for. The window's own offsets are
 * dropped: every gadget is relative to the root. Answers nothing a caller reads. */
void aes_w_bldactive(uint8_t *image, int16_t window)
{
    if (window != OB_NIL)
        build_active(image, window);
}

/* $febece — the GRECT at `source` cut to gl_rfull in place; when its x was -1 (read BEFORE the cut: a window one
 * pixel off the screen's left edge), the GRECT at `destination` moved one pixel right and narrowed by one, and 1
 * answered, else 0. */
int16_t aes_w_mvfix(uint8_t *image, uint32_t source, uint32_t destination)
{
    int16_t x = (int16_t)bus_word(image, source + GRECT_X);

    aes_rc_intersect(image, AES_GL_RFULL, source);
    if (x != OB_NIL)
        return 0;
    set_bus_word(image, destination + GRECT_X, (uint16_t)(bus_word(image, destination + GRECT_X) + 1));
    set_bus_word(image, destination + GRECT_W, (uint16_t)(bus_word(image, destination + GRECT_W) - 1));
    return 1;
}

/* Where w_move's two GRECTs sit in its slot: the frame's own layout, -16(a6) up. */
#define MOVE_NOW              0          /* -16(a6): where the window is now, WS_TRUE                          */
#define MOVE_BEFORE           GRECT_BYTES  /* -8(a6): where it was, WS_PREV grown by the border               */

/* Whether the window's old rectangle ran off the screen's right (bottom) edge on the side it moved away from — its
 * image there was never on the screen, so it cannot be blitted. */
static int moved_off_an_edge(const uint8_t *image, uint32_t now, uint32_t before)
{
    return ((int16_t)(local_word(image, before, GRECT_X) + local_word(image, before, GRECT_W))
            > global_word(image, AES_GL_WIDTH)
            && local_word(image, now, GRECT_X) < local_word(image, before, GRECT_X))
           || ((int16_t)(local_word(image, before, GRECT_Y) + local_word(image, before, GRECT_H))
               > global_word(image, AES_GL_HEIGHT)
               && local_word(image, now, GRECT_Y) < local_word(image, before, GRECT_Y));
}

/* $febf00 — window `window` moved: its image blitted from where it was to where it is when it can be — the word at
 * `stop` made the window (else 0, the rectangle to redraw the union of the two) — and the one-pixel strip a window
 * at the screen's left edge leaves drawn by the top window's root; the rectangle the caller redraws copied to `rect`
 * (the old one after a blit, else the union). Answers whether the word at `stop`, READ BACK after that copy, is the
 * window. While window drawing is held it does nothing and the ROM leaves its caller's D0, which the C cannot see:
 * it answers 0 (its one caller, draw_change, returns before calling while drawing is held). */
int16_t aes_w_move(uint8_t *image, int16_t window, uint32_t stop, uint32_t rect)
{
    uint16_t rects_local[2 * GRECT_WORDS];
    uint32_t rects, now, before, redraw;
    int16_t now_fixed, before_fixed;
    _Static_assert(sizeof rects_local == HOST_SLOT_AES_W_MOVE_RECTS_BYTES, "w_move's two GRECTs and their host slot");

    if (global_word(image, AES_GL_WFROZEN))
        return 0;
    rects = host_slot_claim(AES_W_MOVE_RECTS, rects_local);
    now = rects + MOVE_NOW;
    before = rects + MOVE_BEFORE;
    aes_w_getsize(image, WS_PREV, window, before);
    grow_extent(image, before, W_BORDER);
    aes_w_getsize(image, WS_TRUE, window, now);
    if (moved_off_an_edge(image, now, before)) {
        aes_rc_union(image, before, now);
        set_bus_word(image, stop, 0);
    } else {
        set_bus_word(image, stop, (uint16_t)window);
    }
    now_fixed = aes_w_mvfix(image, before, now);
    before_fixed = aes_w_mvfix(image, now, before);
    redraw = now;
    if ((int16_t)bus_word(image, stop) == window) {
        aes_gsx_sclip(image, AES_GL_RFULL);
        aes_bb_screen(image, WM_SCREEN_TO_SCREEN, local_word(image, before, GRECT_X), local_word(image, before, GRECT_Y),
                      local_word(image, now, GRECT_X), local_word(image, now, GRECT_Y),
                      local_word(image, before, GRECT_W), local_word(image, before, GRECT_H));
        if (now_fixed != before_fixed) {
            if (before_fixed)
                wr16(image + before + GRECT_X, (uint16_t)(local_word(image, before, GRECT_X) - 1));
            if (now_fixed) {
                wr16(image + now + GRECT_X, (uint16_t)(local_word(image, now, GRECT_X) - 1));
                wr16(image + now + GRECT_W, MOVE_GAP_WIDTH);
                aes_gsx_sclip(image, now);
                aes_w_cpwalk(image, global_word(image, AES_GL_WTOP), OB_ROOT, 0, 0);
            }
        }
        redraw = before;
    }
    aes_rc_copy(image, redraw, rect);
    host_slot_release(AES_W_MOVE_RECTS);
    return (int16_t)bus_word(image, stop) == window;
}

/* $fec39a — the next rectangle of the list from `orect` that meets the GRECT at `rect`: each one copied to `out`, the
 * window's list cursor moved past it (WIN_RNEXT), then cut by `rect` in place — the first non-empty cut answered 1.
 * At the list's end `out`'s width and height are 0 and 0 is answered. Each link is read after the copy, which can
 * overwrite it. */
int16_t aes_w_owns(uint8_t *image, int16_t window, uint32_t orect, uint32_t rect, uint32_t out)
{
    while (orect) {
        aes_rc_copy(image, orect + ORECT_X, out);
        orect = bus_long(image, orect + ORECT_LINK);
        set_bus_long(image, window_record(window) + WIN_RNEXT, orect);
        if (aes_rc_intersect(image, rect, out))
            return 1;
    }
    set_bus_word(image, out + GRECT_H, 0);
    set_bus_word(image, out + GRECT_W, 0);
    return 0;
}

/* $fec3ea — the GRECT at `rect` made the bounding box of the list from `orect`: the first rectangle copied, each
 * next one's union taken. Answers 0 for an empty list (`rect` untouched), else 1. */
int16_t aes_w_union(uint8_t *image, uint32_t orect, uint32_t rect)
{
    if (!orect)
        return 0;
    aes_rc_copy(image, orect + ORECT_X, rect);
    for (orect = bus_long(image, orect + ORECT_LINK); orect; orect = bus_long(image, orect + ORECT_LINK))
        aes_rc_union(image, orect + ORECT_X, rect);
    return 1;
}

/* wm_start's template TEDINFO ($fefcae), copied whole into the title's and the information line's: no strings, the
 * IBM font, a colour, a thickness and both lengths — the words in te_ order, two per pointer. */
static const uint16_t tedinfo_template[TE_BYTES / M68K_WORD_BYTES] = {
    0, 0, 0, 0, 0, 0, W_TEDINFO_FONT, W_TEDINFO_RESERVED, 0, W_TEDINFO_COLOUR, 0, W_TEDINFO_THICKNESS,
    W_TEDINFO_LENGTH, W_TEDINFO_LENGTH,
};

static void copy_tedinfo_template(uint8_t *image, uint32_t tedinfo)
{
    for (uint32_t word = 0; word < TE_BYTES / M68K_WORD_BYTES; word++)
        wr16(image + tedinfo + word * M68K_WORD_BYTES, tedinfo_template[word]);
}

/* The desktop's visible-rectangle list: ONE ORECT, the screen below the menu bar. */
static void desktop_list(uint8_t *image)
{
    uint32_t orect = aes_get_orect(image);
    int16_t bar = global_word(image, AES_GL_HBOX);

    wr32(image + window_record(WM_DESKTOP) + WIN_RLIST, orect);
    set_bus_long(image, orect + ORECT_LINK, 0);
    set_bus_word(image, orect + ORECT_X, 0);
    set_bus_word(image, orect + ORECT_Y, (uint16_t)bar);
    set_bus_word(image, orect + ORECT_W, (uint16_t)global_word(image, AES_GL_WIDTH));
    set_bus_word(image, orect + ORECT_H, (uint16_t)(global_word(image, AES_GL_HEIGHT) - global_word(image, AES_GL_HBOX)));
}

/* $fec424 — the window library set up: the ORECT pool emptied; the window tree cleared and unlinked, every window's
 * record closed with no list and its object an IBOX, the root a BOX drawn with the desktop band's pattern; W_ACTIVE
 * cleared, unlinked and typed from the ROM's tables, its root SHADOWED; window 0, the desktop, claimed for the running
 * process with one visible rectangle, its current and previous rectangles the screen, its full and work areas the
 * screen below the menu bar; no top window, no desk tree, drawing not held; and the title's and information line's
 * TEDINFOs copied from the template, the title centred, and pointed at by their gadgets. */
void aes_wm_start(uint8_t *image)
{
    int16_t window, object;

    aes_or_start(image);
    aes_bfill(image, W_TREE_BYTES, CLEAR_BYTE, AES_WINDOW_TREE);
    aes_w_nilit(image, AES_WINDOW_COUNT, AES_WINDOW_TREE);
    for (window = 0; window < AES_WINDOW_COUNT; window++) {
        wr16(image + window_record(window) + WIN_FLAGS, 0);
        wr32(image + window_record(window) + WIN_RLIST, 0);
        wr16(image + object_address(AES_WINDOW_TREE, window, OB_TYPE), W_TREE_WINDOW_TYPE);
    }
    wr16(image + object_address(AES_WINDOW_TREE, OB_ROOT, OB_TYPE), W_TREE_ROOT_TYPE);
    wr32(image + object_address(AES_WINDOW_TREE, OB_ROOT, OB_SPEC),
         bus_long(image, object_address(be32(image + AES_AD_STDESK), OB_ROOT, OB_SPEC)));
    aes_bfill(image, W_ACTIVE_BYTES, CLEAR_BYTE, AES_W_ACTIVE);
    aes_w_nilit(image, W_ACTIVE_OBJECTS, AES_W_ACTIVE);
    for (object = 0; object < W_ACTIVE_OBJECTS; object++) {
        wr16(image + w_active(object, OB_TYPE), w_active_types[object]);
        wr32(image + w_active(object, OB_SPEC), w_active_specs[object]);
    }
    wr16(image + w_active(W_BOX, OB_STATE), W_ACTIVE_ROOT_STATE);
    desktop_list(image);
    aes_w_setup(image, be32(image + AES_RLR), WM_DESKTOP, 0);
    aes_w_setsize(image, WS_CURR, WM_DESKTOP, AES_GL_RSCREEN);
    aes_w_setsize(image, WS_PREV, WM_DESKTOP, AES_GL_RSCREEN);
    aes_w_setsize(image, WS_FULL, WM_DESKTOP, AES_GL_RFULL);
    aes_w_setsize(image, WS_WORK, WM_DESKTOP, AES_GL_RFULL);
    wr16(image + AES_GL_WTOP, (uint16_t)OB_NIL);
    wr32(image + AES_GL_WTREE, AES_WINDOW_TREE);
    wr32(image + AES_GL_AWIND, AES_W_ACTIVE);
    wr32(image + AES_GL_NEWDESK, 0);
    wr16(image + AES_GL_WFROZEN, 0);
    copy_tedinfo_template(image, AES_GL_ANAME);
    copy_tedinfo_template(image, AES_GL_AINFO);
    wr16(image + AES_GL_ANAME + TE_JUST, W_TITLE_JUST);
    wr32(image + w_active(W_NAME, OB_SPEC), AES_GL_ANAME);
    wr32(image + w_active(W_INFO, OB_SPEC), AES_GL_AINFO);
}

/* $fec602 — the first window not in use (the flags' low byte's bit 0) claimed for the running process with `kind`,
 * its current and previous rectangles empty and its full one the GRECT at `rect`; answers its handle, or -1 when all
 * eight are in use. The desktop, window 0, is in use from wm_start on. */
int16_t aes_wm_create(uint8_t *image, int16_t kind, uint32_t rect)
{
    int16_t window = 0;

    while (window < AES_WINDOW_COUNT && (bus_word(image, window_record(window) + WIN_FLAGS) & WIN_IN_USE))
        window++;
    if (window >= AES_WINDOW_COUNT)
        return OB_NIL;
    aes_w_setup(image, be32(image + AES_RLR), window, kind);
    aes_w_setsize(image, WS_CURR, window, AES_GL_RZERO);
    aes_w_setsize(image, WS_PREV, window, AES_GL_RZERO);
    aes_w_setsize(image, WS_FULL, window, rect);
    return window;
}

/* $fec706 — window `window`'s record no longer in use. The ROM leaves THEGLO + 56 * window in D0 — the `muls.w` and
 * `addl` it indexed the table by, before adding the table's offset — which the desk's binding stores as wind_delete's
 * answer: its low word is answered. */
uint16_t aes_wm_delete(uint8_t *image, int16_t window)
{
    uint32_t record = window_record(window);

    set_bus_word(image, record + WIN_FLAGS, (uint16_t)(bus_word(image, record + WIN_FLAGS) & ~WIN_IN_USE));
    return (uint16_t)table_entry(AES_THEGLO, window, WIN_BYTES);
}

/* wm_get's rectangle arms: the WS_* each field hands w_getsize ($fec742..$fec754). */
static int16_t rectangle_of_field(int16_t field)
{
    switch (field) {
    case WF_WORKXYWH:
        return WS_WORK;
    case WF_CURRXYWH:
        return WS_CURR;
    case WF_PREVXYWH:
        return WS_PREV;
    case WF_FULLXYWH:
        return WS_FULL;
    default:
        return OB_NIL;
    }
}

/* wm_get's field arms' answer: the switch index the jump left in D0's low word, `(field - WF_FIRST) * 4`. */
static inline uint16_t switch_offset(int16_t field)
{
    return (uint16_t)((field - WF_FIRST) << 2);
}

/* $fec722 — wind_get: field `field` of window `window` out through `out` — a rectangle (w_getsize; the D0 it leaves,
 * the rectangle's address), a slider word, the top window (0 for none), the first or next of its visible rectangles
 * over its work area (w_owns, from its list or its cursor; its answer), or the save buffer (gsx_mret). A field with
 * no arm stores nothing. Answers D0's low word as the ROM leaves it, which the desk's binding stores. */
uint16_t aes_wm_get(uint8_t *image, int16_t window, int16_t field, uint32_t out)
{
    int16_t which = rectangle_of_field(field), top, answer;
    uint16_t work_local[GRECT_WORDS];
    uint32_t work, list;
    _Static_assert(sizeof work_local == HOST_SLOT_AES_WM_GET_RECT_BYTES, "wm_get's GRECT and its host slot");

    if (which != OB_NIL) {
        aes_w_getsize(image, which, window, out);
        return (uint16_t)aes_w_getxptr(which, window);
    }
    switch (field) {
    case WF_HSLIDE:
    case WF_VSLIDE:
    case WF_HSLSIZE:
    case WF_VSLSIZE:
        set_bus_word(image, out, (uint16_t)record_word(image, window, field == WF_HSLIDE ? WIN_HSLIDE
                                                                     : field == WF_VSLIDE ? WIN_VSLIDE
                                                                     : field == WF_HSLSIZE ? WIN_HSLSIZE : WIN_VSLSIZE));
        return switch_offset(field);
    case WF_TOP:
        top = global_word(image, AES_GL_WTOP);
        set_bus_word(image, out, (uint16_t)(top == OB_NIL ? 0 : top));
        return (uint16_t)(top == OB_NIL ? 0 : top);
    case WF_FIRSTXYWH:
    case WF_NEXTXYWH:
        work = host_slot_claim(AES_WM_GET_RECT, work_local);
        aes_w_getsize(image, WS_WORK, window, work);
        list = bus_long(image, window_record(window) + (field == WF_FIRSTXYWH ? WIN_RLIST : WIN_RNEXT));
        answer = aes_w_owns(image, window, list, work, out);
        host_slot_release(AES_WM_GET_RECT);
        return (uint16_t)answer;
    case WF_SCREEN:
        aes_gsx_mret(image, out, out + M68K_LONG_BYTES);
        return switch_offset(field);
    default:
        if ((uint16_t)(field - WF_FIRST) <= (uint16_t)(WF_SCREEN - WF_FIRST))
            return switch_offset(field);
        return (uint16_t)(field - WF_FIRST);
    }
}

/* $feca4a — the window under (x, y): ob_find over the window tree from its root, two levels deep. */
int16_t aes_wm_find(uint8_t *image, int16_t x, int16_t y)
{
    return aes_ob_find(image, be32(image + AES_GL_WTREE), OB_ROOT, WM_FIND_DEPTH, x, y);
}

/* $fecaac — wind_calc: a window of `kind`'s border, one pixel each side and a bar's width (less the shared line) for
 * a title bar, an information line and each scroll bar, added round the work area (x, y, w, h) — or, for WC_BORDER,
 * taken off the window's rectangle — and the result stored through the four pointers in order. Answers the height
 * stored, which the ROM leaves in D0 and the desk's binding stores. */
int16_t aes_wm_calc(uint8_t *image, int16_t type, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h,
                    uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out)
{
    int16_t left = W_EDGE, right = W_EDGE, bottom = W_EDGE, top = W_EDGE, height;

    if (kind & WK_TITLE_BAR)
        top = (int16_t)(top + overlapped(image, AES_GL_HBOX));
    if (kind & WK_INFO)
        top = (int16_t)(top + overlapped(image, AES_GL_HBOX));
    if (kind & WK_VERTICAL_BAR)
        right = (int16_t)(right + overlapped(image, AES_GL_WBOX));
    if (kind & WK_HORIZONTAL_BAR)
        bottom = (int16_t)(bottom + overlapped(image, AES_GL_HBOX));
    if (type == WC_BORDER) {
        left = (int16_t)-left;
        top = (int16_t)-top;
        right = (int16_t)-right;
        bottom = (int16_t)-bottom;
    }
    set_bus_word(image, x_out, (uint16_t)(left + x));
    set_bus_word(image, y_out, (uint16_t)(top + y));
    set_bus_word(image, w_out, (uint16_t)(w - left - right));
    height = (int16_t)(h - top - bottom);
    set_bus_word(image, h_out, (uint16_t)height);
    return height;
}
