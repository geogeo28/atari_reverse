/* deskwin.c — THE DESK'S WINDOW OBJECTS AND ITS PROGRAM LEAVES (`desk/deskwin.h`; band 6 wave 1b, unit I). Alcyon C
 * in the ROM, ported over its own order. LINKED AND UNBOUND: every Line-F entry naming one of these stays the ROM's
 * (`bench/linef_table.py`, LINKED_AND_NOT_FLIPPED) while the band's opening waits (ruling W6-R1).
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskmem.h"
#include "aes/gemdosif.h"
#include "aes/gemsuper.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/rect.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "desk/deskact.h"
#include "desk/deskbind.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

/* THE ONE FRAME'S SIZE IS ITS HOST SLOT'S (`host_slot.h`). */
_Static_assert(WIN_FRAME_BYTES == HOST_SLOT_AES_DESK_WIN_FRAME_BYTES, "the window leaves' frame and its host slot");
_Static_assert(OPEN_FRAME_BYTES == HOST_SLOT_AES_DESK_OPEN_FRAME_BYTES, "the openers' frame and its host slot");

static inline void set_links_nil(uint8_t *image, uint32_t objects, int16_t object, uint32_t field)
{
    set_object_word(image, objects, object, field, OB_NIL);
}

/* ================================================================================================
 * THE SCREEN'S OBJECTS.
 * ============================================================================================= */

/* $fe0776 — obj_init: g_screen pointed at the objects, every object's three links NIL (the head, the next, the tail),
 * the root the sample root at the screen's size, and its five children the sample child, each added under it. */
void aes_obj_init(uint8_t *image)
{
    uint32_t objects = screen_objects(image);
    int16_t object;

    set_bus_long(image, desk_globals(image) + DESK_G_SCREEN, objects);
    for (object = 0; object < DESK_SCREEN_OBJECTS; object++) {
        set_links_nil(image, objects, object, OB_HEAD);
        set_links_nil(image, objects, object, OB_NEXT);
        set_links_nil(image, objects, object, OB_TAIL);
    }
    aes_movs(image, OB_BYTES, DESK_SAMPLE_ROOT, objects);
    aes_r_set(image, objects + OB_X, 0, 0, (int16_t)be16(image + AES_GL_WIDTH), (int16_t)be16(image + AES_GL_HEIGHT));
    for (object = 0; object < DESK_ROOT_CHILDREN; object++) {
        aes_movs(image, OB_BYTES, DESK_SAMPLE_CHILD, object_address(objects, (int16_t)(object + 1), 0));
        aes_desk_objc_add(image, objects, OB_ROOT, (int16_t)(object + 1));
    }
}

/* $fe0840 — obj_walloc: the first window root (2..5) that has no width or no height takes the rectangle. */
int16_t aes_obj_walloc(uint8_t *image, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint32_t objects = screen_objects(image);
    int16_t window;

    for (window = DESK_FIRST_WINDOW_ROOT - 1; window < DESK_ROOT_CHILDREN; window++)
        if (!object_word(image, objects, (int16_t)(window + 1), OB_WIDTH)
            || !object_word(image, objects, (int16_t)(window + 1), OB_HEIGHT))
            break;
    if (window >= DESK_ROOT_CHILDREN)
        return 0;
    aes_r_set(image, object_address(objects, (int16_t)(window + 1), OB_X), x, y, w, h);
    return (int16_t)(window + 1);
}

/* $fe08b4 — obj_wfree: the window root takes the rectangle; every icon linked under it (each a higher object than
 * the root) unlinked by its next, the root's tail and head NIL. The ROM leaves D0 -1 (its own last store's). */
void aes_obj_wfree(uint8_t *image, int16_t object, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint32_t objects = screen_objects(image);
    int16_t icon, next;

    aes_r_set(image, object_address(objects, object, OB_X), x, y, w, h);
    for (icon = object_word(image, objects, object, OB_HEAD); icon > object; icon = next) {
        next = object_word(image, objects, icon, OB_NEXT);
        set_links_nil(image, objects, icon, OB_NEXT);
    }
    set_links_nil(image, objects, object, OB_TAIL);
    set_links_nil(image, objects, object, OB_HEAD);
}

/* $fe0942 — obj_ialloc: the first icon object (6..132) on no list, its children none, added under `parent` — in
 * g_screen's tree — and given the rectangle. */
int16_t aes_obj_ialloc(uint8_t *image, int16_t parent, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint32_t objects = screen_objects(image);
    int16_t icon;

    for (icon = DESK_FIRST_ICON_OBJECT; icon < DESK_SCREEN_OBJECTS; icon++)
        if (object_word(image, objects, icon, OB_NEXT) == OB_NIL)
            break;
    if (icon >= DESK_SCREEN_OBJECTS)
        return 0;
    set_links_nil(image, objects, icon, OB_TAIL);
    set_links_nil(image, objects, icon, OB_HEAD);
    aes_desk_objc_add(image, bus_long(image, desk_globals(image) + DESK_G_SCREEN), parent, icon);
    aes_r_set(image, object_address(objects, icon, OB_X), x, y, w, h);
    return icon;
}

/* ================================================================================================
 * THE PROGRAM LEAVES.
 * ============================================================================================= */

/* $fe09cc — pro_chdir: drive 99 is none (the glue's verdict cleared); 0 is the current; else that drive made
 * current, and the path — the caller's, after a backslash, cut at its first blank or `*` — made its current path. */
int16_t aes_pro_chdir(uint8_t *image, int16_t drive, uint32_t path)
{
    uint32_t scratch = be32(image + AES_DESK_BLOCK_512);
    uint8_t character;
    int16_t at;

    if (drive == DESK_NO_DRIVE) {
        wr16(image + AES_DOS_ERR, 0);
        return PRO_DONE;
    }
    if (!drive)
        return PRO_DONE;
    (void)aes_dos_sdrv(image, AES_PRO_CHDIR_SDRV_RETURN, (int16_t)(drive - DRIVE_LETTER_FIRST));
    set_bus_byte(image, scratch + CHDIR_PATH, CHDIR_PATH_ROOT);
    (void)aes_strcpy(image, path, scratch + CHDIR_PATH_TEXT);
    for (at = 1; (character = bus_byte(image, offset_by(scratch, at) + CHDIR_PATH)) != STRING_NUL; at++)
        if (character == STRING_SPACE || character == STRING_WILDCARD_ANY) {
            set_bus_byte(image, offset_by(scratch, at) + CHDIR_PATH, STRING_NUL);
            break;
        }
    (void)aes_dos_chdir(image, AES_PRO_CHDIR_CHDIR_RETURN, scratch + CHDIR_PATH);
    return PRO_DONE;
}

/* $fe0a7c — pro_cmd: the command and the tail copied into g_cmd and g_tail, the tail's count byte the low byte of
 * the caller's FOURTH word; the third is read by nothing (GEM's exitflag, left in the frame). */
int16_t aes_pro_cmd(uint8_t *image, uint32_t command, uint32_t tail, int16_t unread, int16_t tail_byte)
{
    uint32_t globals = desk_globals(image);

    (void)unread;
    (void)aes_strcpy(image, command, globals + DESK_G_CMD);
    (void)aes_strcpy(image, tail, globals + DESK_G_TAIL_TEXT);
    set_bus_byte(image, globals + DESK_G_TAIL, (uint8_t)tail_byte);
    return PRO_DONE;
}

/* $fe0b26 — pro_exec: the hourglass, then shel_write(1, ...) — the two words handed on as the ROM pushes them. */
int16_t aes_pro_exec(uint8_t *image, int16_t isgraf, int16_t isover, uint32_t command, uint32_t tail)
{
    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    return aes_desk_shel_write(image, SHEL_WRITE_EXECUTE, isgraf, isover, command, tail);
}

/* $fe0b56 — desk_rsrc_load: the desk's resource is the ROM's (rom_ram's part 1, over the desk's own global[]). */
int16_t aes_desk_rsrc_load(uint8_t *image)
{
    (void)aes_rom_ram(image, ROM_RSC_DESK, AES_DESK_APP_GLOBAL, 0);
    return PRO_DONE;
}

/* $fe0b6e — ini_tree: a tree's address answered through `answer`. */
int16_t aes_ini_tree(uint8_t *image, uint32_t answer, int16_t index)
{
    return aes_desk_rsrc_gaddr(image, R_TREE, index, answer);
}

/* $fe0b86 — ini_str: a free string copied into g_lngstr; the buffer's address. */
uint32_t aes_ini_str(uint8_t *image, int16_t index)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(WIN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_WIN_FRAME, frame_local);
    uint32_t buffer = desk_globals(image) + DESK_G_LONG_STRING;

    (void)aes_desk_rsrc_gaddr(image, R_STRING, index, frame + WIN_FRAME_STRING);
    (void)aes_lstcpy(image, buffer, be32(image + frame + WIN_FRAME_STRING));
    host_slot_release(AES_DESK_WIN_FRAME);
    return buffer;
}

/* ================================================================================================
 * THE WINDOW LEAVES.
 * ============================================================================================= */

/* A window's four words of `field` answered into the rectangle at `rect` (wind_get: x, y, w, h). */
static inline void get_rect(uint8_t *image, int16_t window, int16_t field, uint32_t rect)
{
    (void)aes_desk_wind_get(image, window, field, rect + GRECT_X, rect + GRECT_Y, rect + GRECT_W, rect + GRECT_H);
}

/* get_rect AS A CALL OF ITS OWN, for the routines that hold a rectangle under the desk's deepest draws (W6-R4: PD0):
 * inlined, wind_get's seven arguments and the rectangle's four addresses are kept in the caller's frame, under its
 * redraw. */
__attribute__((noinline)) static void get_rect_called(uint8_t *image, int16_t window, int16_t field, uint32_t rect)
{
    get_rect(image, window, field, rect);
}

/* $fe0c9a — do_wredraw: the window's objects (its root; the desktop's for window 0) drawn over each rectangle of
 * its list that meets the caller's rectangle — handed BY ADDRESS, the ROM's own argument words — and the screen,
 * the cursor hidden round the walk. */
void aes_do_wredraw(uint8_t *image, int16_t window, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(WIN_FRAME_REDRAW_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_WIN_FRAME, frame_local);
    uint32_t piece = frame + WIN_FRAME_FIRST_RECT, clip = frame + WIN_FRAME_SECOND_RECT;
    uint32_t tree = bus_long(image, desk_globals(image) + DESK_G_SCREEN);
    int16_t root = DESKTOP_ROOT;

    lay_rect(image, clip, x, y, w, h);
    if (window)
        root = (int16_t)bus_word(image, aes_win_find(image, window) + WNODE_ROOT);
    aes_desk_graf_mouse(image, GRAF_MOUSE_HIDE, DESK_NO_FORM);
    for (get_rect_called(image, window, WF_FIRSTXYWH, piece); rect_word(image, piece, GRECT_W) && rect_word(image, piece, GRECT_H);
         get_rect_called(image, window, WF_NEXTXYWH, piece))
        if (aes_rc_intersect(image, clip, piece) && aes_rc_intersect(image, AES_GL_RSCREEN, piece))
            aes_desk_objc_draw(image, tree, root, REDRAW_DEPTH, rect_word(image, piece, GRECT_X),
                               rect_word(image, piece, GRECT_Y), rect_word(image, piece, GRECT_W),
                               rect_word(image, piece, GRECT_H));
    aes_desk_graf_mouse(image, GRAF_MOUSE_SHOW, DESK_NO_FORM);
    host_slot_release(AES_DESK_WIN_FRAME);
}

/* $fe0d5a — get_xywh: an object's four words out through the caller's four pointers. */
void aes_get_xywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out, uint32_t w_out,
                  uint32_t h_out)
{
    set_bus_word(image, x_out, bus_word(image, object_address(tree, object, OB_X)));
    set_bus_word(image, y_out, bus_word(image, object_address(tree, object, OB_Y)));
    set_bus_word(image, w_out, bus_word(image, object_address(tree, object, OB_WIDTH)));
    set_bus_word(image, h_out, bus_word(image, object_address(tree, object, OB_HEIGHT)));
}

/* $fe0db8 — get_spec: an object's ob_spec. */
uint32_t aes_get_spec(uint8_t *image, uint32_t tree, int16_t object)
{
    return bus_long(image, object_address(tree, object, OB_SPEC));
}

/* $fe0dce — do_xyfix: the corner's x put on a 16-pixel column (the next where it lies in its column's right half),
 * its y no higher than the desktop's work area. */
void aes_do_xyfix(uint8_t *image, uint32_t x_inout, uint32_t y_inout)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(WIN_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_WIN_FRAME, frame_local) + WIN_FRAME_FIRST_RECT;
    uint16_t x;

    get_rect(image, WINDOW_DESKTOP, WF_WORKXYWH, work);
    x = bus_word(image, x_inout);
    set_bus_word(image, x_inout, x & XYFIX_IN_COLUMN_MASK);
    if ((int16_t)bus_word(image, x_inout) < XYFIX_HALF_COLUMN)
        set_bus_word(image, x_inout, x & XYFIX_COLUMN_MASK);
    else
        set_bus_word(image, x_inout, (uint16_t)((x & XYFIX_COLUMN_MASK) + XYFIX_COLUMN));
    set_bus_word(image, y_inout, (uint16_t)aes_max((int16_t)bus_word(image, y_inout), rect_word(image, work, GRECT_Y)));
    host_slot_release(AES_DESK_WIN_FRAME);
}

/* $fe0f36 — zoom_closed: the window's work area asked, the window closed where `close` says, and a box shrunk from
 * the icon's corner — at an icon's size — onto the work area. */
void aes_zoom_closed(uint8_t *image, int16_t close, int16_t window, int16_t icon_x, int16_t icon_y)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(WIN_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_WIN_FRAME, frame_local) + WIN_FRAME_FIRST_RECT;
    uint32_t globals = desk_globals(image);

    get_rect(image, window, WF_WORKXYWH, work);
    if (close)
        (void)aes_desk_wind_close(image, window);
    aes_desk_graf_shrinkbox(image, icon_x, icon_y, (int16_t)bus_word(image, globals + DESK_G_WICON),
                            (int16_t)bus_word(image, globals + DESK_G_HICON), rect_word(image, work, GRECT_X),
                            rect_word(image, work, GRECT_Y), rect_word(image, work, GRECT_W),
                            rect_word(image, work, GRECT_H));
    host_slot_release(AES_DESK_WIN_FRAME);
}

/* The window's current size set to the rectangle at `rect`. */
static inline void set_current(uint8_t *image, int16_t window, uint32_t rect)
{
    (void)aes_desk_wind_set(image, window, WF_CURRXYWH, rect_word(image, rect, GRECT_X), rect_word(image, rect, GRECT_Y),
                            rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
}

/* $fe0f9c — do_wfull: a window at its full size goes back to its previous one (a box shrunk from that to the full),
 * any other is made full (a box grown from its current size to the full). */
void aes_do_wfull(uint8_t *image, int16_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(WIN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_WIN_FRAME, frame_local);
    uint32_t current = frame + WIN_FRAME_FIRST_RECT, previous = frame + WIN_FRAME_SECOND_RECT;
    uint32_t full = frame + WIN_FRAME_THIRD_RECT;

    get_rect(image, window, WF_CURRXYWH, current);
    get_rect(image, window, WF_PREVXYWH, previous);
    get_rect(image, window, WF_FULLXYWH, full);
    if (aes_rc_equal(image, current, full)) {
        set_current(image, window, previous);
        aes_desk_graf_shrinkbox(image, rect_word(image, previous, GRECT_X), rect_word(image, previous, GRECT_Y),
                                rect_word(image, previous, GRECT_W), rect_word(image, previous, GRECT_H),
                                rect_word(image, full, GRECT_X), rect_word(image, full, GRECT_Y),
                                rect_word(image, full, GRECT_W), rect_word(image, full, GRECT_H));
    } else {
        aes_desk_graf_growbox(image, rect_word(image, current, GRECT_X), rect_word(image, current, GRECT_Y),
                              rect_word(image, current, GRECT_W), rect_word(image, current, GRECT_H),
                              rect_word(image, full, GRECT_X), rect_word(image, full, GRECT_Y),
                              rect_word(image, full, GRECT_W), rect_word(image, full, GRECT_H));
        set_current(image, window, full);
    }
    host_slot_release(AES_DESK_WIN_FRAME);
}

/* ================================================================================================
 * BAND 6 WAVE 2 (group G3): THE OPENERS.
 * ============================================================================================= */

/* pro_run's command run: the tail counted and ended where it has no count yet, pro_exec over the desk's command and
 * tail, the count cleared — pro_exec's answer. A frame of its own (W6-R4): its registers would otherwise stand under
 * do_wopen's redraw, a deep path of PD0. */
__attribute__((noinline)) static int16_t the_command_run(uint8_t *image, int16_t isgraf, int16_t isover)
{
    uint32_t globals = desk_globals(image);
    int16_t answer, length;

    if (!bus_byte(image, globals + DESK_G_TAIL)) {
        length = aes_strlen(image, globals + DESK_G_TAIL_TEXT);
        set_bus_byte(image, globals + DESK_G_TAIL, (uint8_t)length);
        set_bus_byte(image, offset_by(globals, length) + DESK_G_TAIL_TEXT, PRO_RUN_TAIL_END);
    }
    answer = aes_pro_exec(image, isgraf, isover, bus_long(image, globals + DESK_G_A_CMD), bus_long(image, globals + DESK_G_A_TAIL));
    set_bus_byte(image, globals + DESK_G_TAIL, 0);
    return answer;
}

/* $fe0ab6 — pro_run: where the tail has no count yet, its length the count and a CR after it (the length a signed
 * word, the CR's place `adda.w`); pro_exec over the desk's command and tail, the count cleared; where a window is
 * named, do_wopen of it again over the desk's area — no new GEM window. pro_exec's answer. */
int16_t aes_pro_run(uint8_t *image, int16_t isgraf, int16_t isover, int16_t window, int16_t icon)
{
    uint32_t globals = desk_globals(image);
    int16_t answer = the_command_run(image, isgraf, isover);

    if (window != PRO_RUN_NO_WINDOW)
        aes_do_wopen(image, DO_WOPEN_OLD_WINDOW, window, icon, rect_word(image, globals + DESK_G_DESK_RECT, GRECT_X),
                     rect_word(image, globals + DESK_G_DESK_RECT, GRECT_Y), rect_word(image, globals + DESK_G_DESK_RECT, GRECT_W),
                     rect_word(image, globals + DESK_G_DESK_RECT, GRECT_H));
    return answer;
}

/* The root object a window's icons hang from: its WNODE's, or the desktop's for window 0. */
static int16_t root_of(uint8_t *image, int16_t window)
{
    return window ? (int16_t)bus_word(image, aes_win_find(image, window) + WNODE_ROOT) : DESKTOP_ROOT;
}

/* $fe0bbc — desk_clear: every icon of the window's root (the desktop's for window 0) not SELECTED — tested against
 * the area below the menu bar, redrawn inside the window's work area. */
void aes_desk_clear(uint8_t *image, int16_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(OPEN_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_OPEN_FRAME, frame_local) + OPEN_FRAME_WORK;

    get_rect(image, window, WF_WORKXYWH, work);
    aes_act_allchg(image, window, bus_long(image, desk_globals(image) + DESK_G_SCREEN), root_of(image, window),
                   ACT_NONE_SPARED, AES_GL_RFULL, work, OB_STATE_SELECTED, ACT_CLEARED, ACT_DRAWN);
    host_slot_release(AES_DESK_OPEN_FRAME);
}

/* $fe0c2a — desk_verify: where a window is named and `changed`, its view rebuilt over its work area; the window's
 * root (the desktop's for window 0) and handle made the desk's current, g_croot and g_cwin. */
void aes_desk_verify(uint8_t *image, int16_t window, int16_t changed)
{
    uint32_t globals = desk_globals(image), node;
    int16_t root = DESKTOP_ROOT;

    if (window) {
        node = aes_win_find(image, window);
        if (changed) {
            uint16_t frame_local[FRAME_LOCAL_WORDS(OPEN_FRAME_WORK + GRECT_BYTES)];  /* to its work area's end, held under win_bldview */
            uint32_t work = host_slot_claim(AES_DESK_OPEN_FRAME, frame_local) + OPEN_FRAME_WORK;

            get_rect_called(image, window, WF_WORKXYWH, work);
            aes_win_bldview(image, node, rect_word(image, work, GRECT_X), rect_word(image, work, GRECT_Y),
                            rect_word(image, work, GRECT_W), rect_word(image, work, GRECT_H));
            host_slot_release(AES_DESK_OPEN_FRAME);
        }
        root = (int16_t)bus_word(image, node + WNODE_ROOT);
    }
    set_bus_word(image, globals + DESK_SELECTION_ROOT, (uint16_t)root);
    set_bus_word(image, globals + DESK_SELECTION_WINDOW, (uint16_t)window);
}

/* do_wopen's rectangles read into its frame (do_wopen's comment, below): the corner put on do_xyfix's column in place,
 * the icon's rectangle and the current root's, the root's corner added to the icon's. A frame of its own (W6-R4): the
 * registers of its eight addresses would otherwise stand under act_chg's redraw, a deep path of PD0. */
__attribute__((noinline)) static void the_rectangles_read(uint8_t *image, uint32_t frame, int16_t icon)
{
    uint32_t globals = desk_globals(image), objects = screen_objects(image);
    uint32_t box = frame + OPEN_FRAME_ICON, root = frame + OPEN_FRAME_ROOT;

    aes_do_xyfix(image, frame + OPEN_FRAME_CORNER_X, frame + OPEN_FRAME_CORNER_Y);
    aes_get_xywh(image, objects, icon, box + GRECT_X, box + GRECT_Y, box + GRECT_W, box + GRECT_H);
    aes_get_xywh(image, objects, (int16_t)bus_word(image, globals + DESK_SELECTION_ROOT), root + GRECT_X, root + GRECT_Y,
                 root + GRECT_W, root + GRECT_H);
    set_bus_word(image, box + GRECT_X, (uint16_t)(rect_word(image, box, GRECT_X) + rect_word(image, root, GRECT_X)));
    set_bus_word(image, box + GRECT_Y, (uint16_t)(rect_word(image, box, GRECT_Y) + rect_word(image, root, GRECT_Y)));
}

/* $fe0e38 — do_wopen: the corner put on do_xyfix's column (IN PLACE: the routine's own argument words); a box grown
 * from the icon — its rectangle on the screen, the root's corner added; a text view's line (G_USERDEF) as wide as the
 * window — to the rectangle; the icon not SELECTED (a DISABLED one refused), redrawn inside the root's rectangle;
 * where `new_window`, the GEM window opened at the rectangle. g_wlastsel the window. */
void aes_do_wopen(uint8_t *image, int16_t new_window, int16_t window, int16_t icon, int16_t x, int16_t y, int16_t w,
                  int16_t h)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(OPEN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_OPEN_FRAME, frame_local), globals = desk_globals(image);
    uint32_t objects = screen_objects(image), corner_x = frame + OPEN_FRAME_CORNER_X, corner_y = frame + OPEN_FRAME_CORNER_Y;
    uint32_t box = frame + OPEN_FRAME_ICON, root = frame + OPEN_FRAME_ROOT;

    wr16(image + corner_x, (uint16_t)x);
    wr16(image + corner_y, (uint16_t)y);
    the_rectangles_read(image, frame, icon);
    if (object_word(image, objects, icon, OB_TYPE) == G_USERDEF)
        set_bus_word(image, box + GRECT_W, (uint16_t)w);
    aes_desk_graf_growbox(image, rect_word(image, box, GRECT_X), rect_word(image, box, GRECT_Y), rect_word(image, box, GRECT_W),
                          rect_word(image, box, GRECT_H), (int16_t)be16(image + corner_x), (int16_t)be16(image + corner_y), w, h);
    (void)aes_act_chg(image, (int16_t)bus_word(image, globals + DESK_SELECTION_WINDOW), bus_long(image, globals + DESK_G_SCREEN),
                      (int16_t)bus_word(image, globals + DESK_SELECTION_ROOT), icon, root, OB_STATE_SELECTED, ACT_CLEARED,
                      ACT_DRAWN, ACT_DISABLED_CHECKED);
    if (new_window)
        (void)aes_desk_wind_open(image, window, (int16_t)be16(image + corner_x), (int16_t)be16(image + corner_y), w, h);
    set_bus_word(image, globals + DESK_G_WLASTSEL, (uint16_t)window);
    host_slot_release(AES_DESK_OPEN_FRAME);
}
