/* wmupdate.c — the WINDOW LIBRARY's half that reaches the event layer (`aes/wmupdate.h`): a window's change drawn
 * (draw_change, w_update, w_redraw), its owner made the mouse's (w_setactive), the screen lock and the form manager's
 * hold on the screen (wm_update, fm_own), the wind_* calls on them (wm_opcl, wm_open, wm_close, wm_set), and the
 * control manager's three leaves (get_ctrl, set_ctrl, get_mown). Alcyon C in the ROM, ported over its own order.
 *
 * THE EVENT LAYER through the event door (`aes/evdoor.h`): tak_flag, unsync and ev_block for the lock, ct_chgown for
 * the mouse and keyboard, ap_rdwr under ap_sendmsg for the redraw messages — the ROM's own routines on both shores.
 *
 * Every GRECT the ROM keeps in its frame and hands on by address is a host slot off target (`host_slot.h`), laid out
 * as its `link` lays it. Every word sum wraps and every compare is signed, as the ROM's `add.w` / `cmp.w`.
 *
 * WHAT EVERYOBJ IS HANDED is the one place host and target differ (`staged_call.h`'s ALCYON_ROUTINE).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evdoor.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/oblib.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "aes/wrect.h"

#define WHOLE_TREE_LAST       OB_NIL     /* everyobj's last: none, the walk ends where it began ($fec14c move.w #-1) */
#define WALK_START            0          /* ...its start x and y              ($fec144 clr.l)                  */
#define TOP_BEHIND            OB_NIL     /* ob_order's place: on top of its siblings ($fec8ac move.w #-1)      */
#define NO_STRING_GADGET      (-1)       /* wm_set's gadget to redraw a string into: none ($fec854 move.w #-1) */

/* The window tree's root's first and last child: the bottom window and the top one. */
static inline int16_t bottom_window(const uint8_t *image)
{
    return object_word(image, AES_WINDOW_TREE, OB_ROOT, OB_HEAD);
}

static inline int16_t top_window(const uint8_t *image)
{
    return object_word(image, AES_WINDOW_TREE, OB_ROOT, OB_TAIL);
}

static inline uint32_t window_owner(const uint8_t *image, int16_t window)
{
    return bus_long(image, window_record(window) + WIN_OWNER);
}

/* ---- the control manager's leaves ------------------------------------------------------------------------------- */
/* $fe5008 — the control rectangle made the GRECT at `rect` (rc_copy). */
void aes_set_ctrl(uint8_t *image, uint32_t rect)
{
    aes_rc_copy(image, rect, AES_CTRL_RECT);
}

/* $fe501c — ...and copied out to it. */
void aes_get_ctrl(uint8_t *image, uint32_t rect)
{
    aes_rc_copy(image, AES_CTRL_RECT, rect);
}

/* $fe5030 — the mouse's owner and the keyboard's, each a longword stored through its pointer (the mouse's first). */
void aes_get_mown(uint8_t *image, uint32_t mouse_out, uint32_t keyboard_out)
{
    set_bus_long(image, mouse_out, be32(image + AES_GL_MOWNER));
    set_bus_long(image, keyboard_out, be32(image + AES_GL_KOWNER));
}

/* ---- the screen lock and the form manager's hold on the screen ------------------------------------------------ */
/* $feca68 — wind_update: below WM_END_MCTRL the screen lock — released for 0 (unsync), else taken (tak_flag), the
 * running process WAITING for it (ev_block) when another holds it — and from WM_END_MCTRL on fm_own(code - 2). D0 is
 * the last door call's (fm_own's); unsync's, when the lock is still held afterwards, is the D0 it was entered with:
 * the ROM's caller's, which no C caller holds — the rows on that arm compare no answer (`aes/wmupdate.h`). */
uint16_t aes_wm_update(uint8_t *image, int16_t code)
{
    uint16_t answer;

    if (code >= WM_END_MCTRL)
        return aes_fm_own(image, (int16_t)(code - WM_END_MCTRL));
    if (code == WM_END_UPDATE)
        return evdoor_unsync(image, AES_WIND_SPB);
    answer = evdoor_tak_flag(image, AES_WIND_SPB);
    if (!answer)
        answer = evdoor_ev_block(image, EV_BLOCK_MUTEX, be32(image + AES_AD_WINDSPB));
    return answer;
}

/* $fe718e — the screen taken by the form manager (`take`) or given back, nested by a count. Taken: the lock first;
 * on the first take the menu put aside (gl_mntree 0), the control rectangle and both owners saved, and the screen
 * handed to the running process (ct_chgown(rlr, &gl_rscreen)) — D0 ct_chgown's, else the lock's. Given back: on the
 * last, the keyboard's saved owner given the saved rectangle and the menu put back; then the lock released. */
uint16_t aes_fm_own(uint8_t *image, int16_t take)
{
    uint16_t answer;

    if (take) {
        answer = aes_wm_update(image, WM_BEG_UPDATE);
        if (!be16(image + AES_FM_OWN_COUNT)) {
            wr32(image + AES_FM_OWN_MENU, be32(image + AES_GL_MNTREE));
            wr32(image + AES_GL_MNTREE, 0);
            aes_get_ctrl(image, AES_FM_OWN_CTRL);
            aes_get_mown(image, AES_FM_OWN_MOUSE, AES_FM_OWN_KEYBOARD);
            answer = evdoor_ct_chgown(image, be32(image + AES_RLR), AES_GL_RSCREEN);
        }
        wr16(image + AES_FM_OWN_COUNT, (uint16_t)(be16(image + AES_FM_OWN_COUNT) + 1));
        return answer;
    }
    wr16(image + AES_FM_OWN_COUNT, (uint16_t)(be16(image + AES_FM_OWN_COUNT) - 1));
    if (!be16(image + AES_FM_OWN_COUNT)) {
        evdoor_ct_chgown(image, be32(image + AES_FM_OWN_KEYBOARD), AES_FM_OWN_CTRL);
        wr32(image + AES_GL_MNTREE, be32(image + AES_FM_OWN_MENU));
    }
    return aes_wm_update(image, WM_END_UPDATE);
}

/* ---- a window's change drawn --------------------------------------------------------------------------------------- */
/* $feba54 — the top window's owner (the desktop's, window 0, while none is open) given the mouse and the keyboard, the
 * control rectangle its work area (ct_chgown). gl_wtop is read twice, as the ROM's `cmpi`/`move` read it. */
void aes_w_setactive(uint8_t *image)
{
    uint16_t work_local[GRECT_WORDS];
    _Static_assert(sizeof work_local == HOST_SLOT_AES_W_SETACTIVE_RECT_BYTES, "w_setactive's GRECT and its host slot");
    uint32_t work = host_slot_claim(AES_W_SETACTIVE_RECT, work_local);
    int16_t window = global_word(image, AES_GL_WTOP) == OB_NIL ? WM_DESKTOP : global_word(image, AES_GL_WTOP);

    aes_w_getsize(image, WS_WORK, window, work);
    evdoor_ct_chgown(image, window_owner(image, window), work);
    host_slot_release(AES_W_SETACTIVE_RECT);
}

/* ---- w_redraw's frame (`link a6,#-16`): the work area cut, then the rectangle asked for ------------------------- */
#define REDRAW_FRAME_BYTES    16
#define REDRAW_WORK           0          /* -16(a6): the work area; then the window's visible bounding box      */
#define REDRAW_ASKED          8          /* -8(a6): the rectangle asked for, cut to what the window shows       */

/* $febe2a — a WM_REDRAW for window `window` to its owner (ap_sendmsg into gl_rmsg), of the GRECT at `rect` cut to the
 * window's work area and to the bounding box of its visible rectangles — none when either cut leaves nothing or the
 * window shows nothing. The first cut decides only whether to go on: the bounding box replaces it. */
void aes_w_redraw(uint8_t *image, int16_t window, uint32_t rect)
{
    uint16_t frame_local[REDRAW_FRAME_BYTES / M68K_WORD_BYTES];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_W_REDRAW_RECTS_BYTES, "w_redraw's two GRECTs and their host slot");
    uint32_t frame = host_slot_claim(AES_W_REDRAW_RECTS, frame_local);
    uint32_t work = frame + REDRAW_WORK, asked = frame + REDRAW_ASKED;

    aes_rc_copy(image, rect, asked);
    aes_w_getsize(image, WS_WORK, window, work);
    if (aes_rc_intersect(image, asked, work)
        && aes_w_union(image, bus_long(image, window_record(window) + WIN_RLIST), work)
        && aes_rc_intersect(image, work, asked))
        aes_ap_sendmsg(image, AES_GL_RMSG, WM_REDRAW, (int16_t)bus_word(image, window_owner(image, window) + PD_PID),
                       window, local_word(image, asked, GRECT_X), local_word(image, asked, GRECT_Y),
                       local_word(image, asked, GRECT_W), local_word(image, asked, GRECT_H));
    host_slot_release(AES_W_REDRAW_RECTS);
}

/* The window below `window` in the window tree from `bottom` — the sibling whose next it is — found by walking the
 * siblings from `bottom` (no bound: a `window` the walk never reaches hangs the ROM too). */
static int16_t window_below(const uint8_t *image, int16_t bottom, int16_t window)
{
    int16_t walker = bottom, next;

    while (walker != window) {
        next = object_word(image, AES_WINDOW_TREE, walker, OB_NEXT);
        if (next == window)
            return walker;
        walker = next;
    }
    return window;
}

/* $fec026 — the windows from `top` down to `bottom` (0: the window tree's first and last child) each drawn under the
 * GRECT at `rect` — first cut to the desktop's area, gl_rfull, in place — its gadgets (w_cpwalk) and a WM_REDRAW to its
 * owner (w_redraw); a `moved` window that is on top is skipped (w_move blitted it). Nothing while drawing is held; the
 * cursor hidden round the rest, an empty tree (bottom -1) too. */
void aes_w_update(uint8_t *image, int16_t bottom, uint32_t rect, int16_t top, int16_t moved)
{
    int16_t done;

    if (global_word(image, AES_GL_WFROZEN))
        return;
    aes_rc_intersect(image, AES_GL_RFULL, rect);
    aes_gsx_moff(image);
    if (!bottom)
        bottom = bottom_window(image);
    if (bottom != OB_NIL) {
        if (!top)
            top = top_window(image);
        do {
            if (!moved || top != global_word(image, AES_GL_WTOP)) {
                aes_gsx_sclip(image, rect);
                aes_w_cpwalk(image, top, OB_ROOT, WM_MAX_DEPTH, 0);
                aes_w_redraw(image, top, rect);
            }
            done = bottom == top;
            top = window_below(image, bottom, top);
        } while (!done);
    }
    aes_gsx_mon(image);
}

/* ---- draw_change's frame (`link a6,#-18`): the word w_move is handed, and the window's old rectangle --------------- */
#define CHANGE_FRAME_BYTES    14
#define CHANGE_STOP           0          /* -14(a6): word, the window w_update stops at, w_move's               */
#define CHANGE_OLD            6          /* -8(a6): where the window was, then the rectangle to redraw          */

/* Whether the GRECT at `inner` lies inside the one at `outer`, edges included (each far edge a word sum). */
static int lies_inside(const uint8_t *image, uint32_t inner, uint32_t outer)
{
    return signed_field(image, outer, GRECT_X) <= signed_field(image, inner, GRECT_X)
           && signed_field(image, outer, GRECT_Y) <= signed_field(image, inner, GRECT_Y)
           && (int16_t)(signed_field(image, inner, GRECT_X) + signed_field(image, inner, GRECT_W))
              <= (int16_t)(signed_field(image, outer, GRECT_X) + signed_field(image, outer, GRECT_W))
           && (int16_t)(signed_field(image, inner, GRECT_Y) + signed_field(image, inner, GRECT_H))
              <= (int16_t)(signed_field(image, outer, GRECT_Y) + signed_field(image, outer, GRECT_H));
}

static inline int same_word(const uint8_t *image, uint32_t first, uint32_t second, uint32_t field)
{
    return signed_field(image, first, field) == signed_field(image, second, field);
}

/* An extent of the old rectangle made the larger of the two, grown by the border ($fec270 max, `addq.w #2`). */
static void widen(uint8_t *image, uint32_t old, uint32_t rect, uint32_t field)
{
    set_bus_word(image, old + field,
                 (uint16_t)(aes_max(signed_field(image, rect, field), signed_field(image, old, field)) + W_BORDER));
}

/* What draw_change decides to redraw: from which window up (`start`, 0 the whole tree: the desktop drawn too), and
 * whether the window on top was blitted into place (`moved`). The word w_update stops at is the frame's. */
struct change {
    int16_t start;
    int16_t moved;
};

/* The window's rectangle CHANGED SIZE in place (same corner): shrunk, the top window's gadgets redrawn and the
 * redraw stopped at it; anything smaller in a direction redraws from the bottom; the old rectangle grown to cover
 * both. */
static void sized(uint8_t *image, int16_t window, uint32_t rect, uint32_t frame, struct change *change)
{
    uint32_t old = frame + CHANGE_OLD;

    if (signed_field(image, rect, GRECT_W) <= signed_field(image, old, GRECT_W)
        && signed_field(image, rect, GRECT_H) <= signed_field(image, old, GRECT_H)) {
        wr16(image + frame + CHANGE_STOP, (uint16_t)window);
        aes_w_cpwalk(image, global_word(image, AES_GL_WTOP), OB_ROOT, WM_MAX_DEPTH, 1);
        change->moved = 1;
    }
    if (signed_field(image, rect, GRECT_W) < signed_field(image, old, GRECT_W)
        || signed_field(image, rect, GRECT_H) < signed_field(image, old, GRECT_H))
        change->start = 0;
    widen(image, old, rect, GRECT_W);
    widen(image, old, rect, GRECT_H);
}

/* The window MOVED: the old rectangle replaced by the new when the new covers it (or the old was empty); else the top
 * window, the same size, blitted (w_move), and the redraw from the window up only while the two rectangles' union is
 * the new one. */
static void moved_away(uint8_t *image, int16_t window, uint32_t rect, uint32_t frame, struct change *change)
{
    uint32_t old = frame + CHANGE_OLD;

    if (!signed_field(image, old, GRECT_W) || !signed_field(image, old, GRECT_H) || lies_inside(image, old, rect)) {
        aes_rc_copy(image, rect, old);
        return;
    }
    if (same_word(image, rect, old, GRECT_W) && same_word(image, rect, old, GRECT_H)
        && window == global_word(image, AES_GL_WTOP)) {
        change->moved = aes_w_move(image, window, frame + CHANGE_STOP, old);
        change->start = 0;
    }
    if (!signed_field(image, rect, GRECT_W) || !signed_field(image, rect, GRECT_H))
        change->start = 0;
    if (change->start) {
        aes_rc_union(image, rect, old);
        if (!aes_rc_equal(image, rect, old))
            change->start = 0;
    }
}

/* Only the ORDER changed (same rectangle): nothing to do unless `window` came to the top. Then the old top's gadgets
 * redrawn as no longer on top, and — both windows whole (the old top unbroken, gl_wasclr) — the new top's gadgets
 * alone: the change is drawn (1). Otherwise (0) the redraw goes on. */
static int topped(uint8_t *image, int16_t window, int16_t old_top)
{
    int whole = 1;

    if (window != top_window(image) || window == old_top)
        return 1;
    if (old_top != OB_NIL) {
        aes_w_cpwalk(image, old_top, OB_ROOT, WM_MAX_DEPTH, 1);
        whole = !(bus_word(image, window_record(old_top) + WIN_FLAGS) & WIN_BROKEN);
    }
    if (whole && be16(image + AES_GL_WASCLR)) {
        aes_w_cpwalk(image, global_word(image, AES_GL_WTOP), OB_ROOT, WM_MAX_DEPTH, 1);
        return 1;
    }
    return 0;
}

/* The redraw the change asks for: when the top window changed, its rectangle — copied over the CALLER's `rect` —
 * added to the old one, the old top's gadgets redrawn; the desktop under the old rectangle unless the redraw starts
 * above it; then the windows (w_update). */
static void redraw_the_change(uint8_t *image, int16_t window, uint32_t rect, uint32_t frame, int16_t old_top,
                              const struct change *change)
{
    uint32_t old = frame + CHANGE_OLD;

    if (old_top != top_window(image) && global_word(image, AES_GL_WTOP) != OB_NIL) {
        aes_w_getsize(image, WS_CURR, global_word(image, AES_GL_WTOP), rect);
        aes_rc_union(image, rect, old);
        if (old_top != OB_NIL && old_top != window)
            aes_w_cpwalk(image, old_top, OB_ROOT, WM_MAX_DEPTH, 1);
    }
    if (!change->start)
        aes_w_drawdesk(image, old);
    aes_w_update(image, change->start, old, local_word(image, frame, CHANGE_STOP), change->moved);
}

/* What changed decides what is redrawn: a MOVE or a RESIZE goes on to the redraw; an unchanged rectangle only when the
 * window came to the top and `topped` did not draw the change itself. */
static int goes_on_to_redraw(uint8_t *image, int16_t window, uint32_t rect, uint32_t frame, int16_t old_top,
                             struct change *change)
{
    uint32_t old = frame + CHANGE_OLD;

    if (!same_word(image, rect, old, GRECT_X) || !same_word(image, rect, old, GRECT_Y)) {
        moved_away(image, window, rect, frame, change);
        return 1;
    }
    if (!same_word(image, rect, old, GRECT_W) || !same_word(image, rect, old, GRECT_H)) {
        sized(image, window, rect, frame, change);
        return 1;
    }
    return !topped(image, window, old_top);
}

/* $fec0ca — window `window` given the GRECT at `rect`: its previous and current rectangles and its work area set,
 * every window's list rebuilt (everyobj with newrect), the top window made the tree's last and the mouse its owner's
 * (w_setactive) — then, unless drawing is held, the change drawn: `goes_on_to_redraw` decides, `redraw_the_change`
 * redraws. */
void aes_draw_change(uint8_t *image, int16_t window, uint32_t rect)
{
    uint16_t frame_local[CHANGE_FRAME_BYTES / M68K_WORD_BYTES];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_DRAW_CHANGE_FRAME_BYTES, "draw_change's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_DRAW_CHANGE_FRAME, frame_local);
    uint32_t old = frame + CHANGE_OLD, work;
    struct change change = {window, 0};
    int16_t old_top;

    aes_w_getsize(image, WS_CURR, window, old);
    aes_w_setsize(image, WS_PREV, window, old);
    aes_w_setsize(image, WS_CURR, window, rect);
    work = aes_w_getxptr(WS_WORK, window);
    aes_wm_calc(image, WC_WORK, (int16_t)bus_word(image, window_record(window) + WIN_KIND), signed_field(image, rect, GRECT_X),
                signed_field(image, rect, GRECT_Y), signed_field(image, rect, GRECT_W), signed_field(image, rect, GRECT_H),
                work + GRECT_X, work + GRECT_Y, work + GRECT_W, work + GRECT_H);
    /* newrect handed BY VALUE ($fec146 `move.l #$fe5cee,-(sp)`): its ROM address on the host, its Alcyon entry beside
     * this file (`wmupdate.S`) on target — spelt at the call, where the ROM-address census sees the use. */
    aes_everyobj(image, be32(image + AES_GL_WTREE), OB_ROOT, WHOLE_TREE_LAST,
                 ALCYON_ROUTINE(AES_ROM_NEWRECT, aes_newrect_alcyon), WALK_START, WALK_START, WM_MAX_DEPTH);
    old_top = global_word(image, AES_GL_WTOP);
    wr16(image + AES_GL_WTOP, (uint16_t)top_window(image));
    aes_w_setactive(image);
    if (!global_word(image, AES_GL_WFROZEN)) {
        wr16(image + frame + CHANGE_STOP, 0);
        if (goes_on_to_redraw(image, window, rect, frame, old_top, &change))
            redraw_the_change(image, window, rect, frame, old_top, &change);
    }
    host_slot_release(AES_DRAW_CHANGE_FRAME);
}

/* ---- the wind_* calls ------------------------------------------------------------------------------------------- */
/* $fec676 — window `window` added to the window tree as its top child (`add`, w_obadd over the tree itself) or taken
 * out of it (ob_delete over gl_wtree), with the screen locked round it: the change drawn over a COPY of the GRECT at
 * `rect` (the frame's: draw_change can overwrite what it is handed), the window's previous rectangle the caller's
 * when added. D0 the lock's release. */
uint16_t aes_wm_opcl(uint8_t *image, int16_t window, uint32_t rect, int16_t add)
{
    uint16_t copy_local[GRECT_WORDS];
    _Static_assert(sizeof copy_local == HOST_SLOT_AES_WM_OPCL_RECT_BYTES, "wm_opcl's GRECT and its host slot");
    uint32_t copy = host_slot_claim(AES_WM_OPCL_RECT, copy_local);

    aes_rc_copy(image, rect, copy);
    aes_wm_update(image, WM_BEG_UPDATE);
    if (add)
        aes_w_obadd(image, AES_WINDOW_TREE, OB_ROOT, window);
    else
        aes_ob_delete(image, be32(image + AES_GL_WTREE), window);
    aes_draw_change(image, window, copy);
    if (add)
        aes_w_setsize(image, WS_PREV, window, rect);
    host_slot_release(AES_WM_OPCL_RECT);
    return aes_wm_update(image, WM_END_UPDATE);
}

/* $fec6da — wind_open. */
uint16_t aes_wm_open(uint8_t *image, int16_t window, uint32_t rect)
{
    return aes_wm_opcl(image, window, rect, WM_OPCL_ADD);
}

/* $fec6f0 — wind_close: no rectangle left (gl_rzero). */
uint16_t aes_wm_close(uint8_t *image, int16_t window)
{
    return aes_wm_opcl(image, window, AES_GL_RZERO, WM_OPCL_REMOVE);
}

/* A slider's word of the record: wind_set's field names which (`aes/wmlib.h`'s WF_*). */
static uint32_t slider_field(int16_t field)
{
    switch (field) {
    case WF_HSLIDE:
        return WIN_HSLIDE;
    case WF_VSLIDE:
        return WIN_VSLIDE;
    case WF_HSLSIZE:
        return WIN_HSLSIZE;
    default:
        return WIN_VSLSIZE;
    }
}

/* wind_set's slider arms: the caller's word clamped to -1..1000 IN PLACE (each bound stored, then re-read), stored in
 * the record, and the slider's gadgets redrawn when the window is on top. The ROM also reads the record's other word
 * of the pair and three box globals into registers and frame words it never uses again — reads with no effect. */
static void set_slider(uint8_t *image, int16_t window, int16_t field, uint32_t words)
{
    int16_t horizontal = field == WF_HSLSIZE || field == WF_HSLIDE;

    set_bus_word(image, words, (uint16_t)aes_max(WM_SLIDER_FLOOR, (int16_t)bus_word(image, words)));
    set_bus_word(image, words, (uint16_t)aes_min(W_SLIDER_SCALE, (int16_t)bus_word(image, words)));
    set_bus_word(image, window_record(window) + slider_field(field), bus_word(image, words));
    if (window == global_word(image, AES_GL_WTOP))
        aes_w_cpwalk(image, window, horizontal ? W_HSLIDE : W_VSLIDE, WM_MAX_DEPTH, 1);
}

/* wind_set(WF_TOP): a window not on top brought there — whether it was whole remembered (gl_wasclr), it made the
 * window tree's last child (ob_order), and its unchanged rectangle redrawn as a change (draw_change). */
static void set_top(uint8_t *image, int16_t window)
{
    uint16_t rect_local[GRECT_WORDS];
    _Static_assert(sizeof rect_local == HOST_SLOT_AES_WM_SET_RECT_BYTES, "wm_set's GRECT and its host slot");
    uint32_t rect;

    if (window == global_word(image, AES_GL_WTOP))
        return;
    wr16(image + AES_GL_WASCLR, (uint16_t)!(bus_word(image, window_record(window) + WIN_FLAGS) & WIN_BROKEN));
    aes_ob_order(image, be32(image + AES_GL_WTREE), window, TOP_BEHIND);
    rect = host_slot_claim(AES_WM_SET_RECT, rect_local);
    aes_w_getsize(image, WS_CURR, window, rect);
    aes_draw_change(image, window, rect);
    host_slot_release(AES_WM_SET_RECT);
}

/* $fec83a — wind_set, the screen locked round it: `field` of window `window` set from the words at `words` — its
 * title or information line (a string's address, redrawn by w_strchg), its rectangle (draw_change), the top window,
 * drawing held for a non-zero handle or released (the desktop and every window redrawn under `words`), a new desk
 * tree and root, a slider. A field with no arm sets nothing. D0 the lock's release. */
uint16_t aes_wm_set(uint8_t *image, int16_t window, int16_t field, uint32_t words)
{
    int16_t gadget = NO_STRING_GADGET;

    aes_wm_update(image, WM_BEG_UPDATE);
    switch (field) {
    case WF_NAME:
        gadget = W_NAME;
        break;
    case WF_INFO:
        gadget = W_INFO;
        break;
    case WF_CURRXYWH:
        aes_draw_change(image, window, words);
        break;
    case WF_TOP:
        set_top(image, window);
        break;
    case WF_RESVD:
        if (window) {
            wr16(image + AES_GL_WFROZEN, 1);
            break;
        }
        wr16(image + AES_GL_WFROZEN, 0);
        aes_w_drawdesk(image, words);
        aes_w_update(image, 0, words, 0, 0);
        break;
    case WF_NEWDESK:
        wr32(image + AES_GL_NEWDESK, bus_long(image, words));
        wr16(image + AES_GL_NEWROOT, bus_word(image, words + WF_NEWDESK_ROOT));
        break;
    case WF_HSLIDE:
    case WF_VSLIDE:
    case WF_HSLSIZE:
    case WF_VSLSIZE:
        set_slider(image, window, field, words);
        break;
    default:
        break;
    }
    if (gadget != NO_STRING_GADGET)
        aes_w_strchg(image, window, gadget, bus_long(image, words));
    return aes_wm_update(image, WM_END_UPDATE);
}
