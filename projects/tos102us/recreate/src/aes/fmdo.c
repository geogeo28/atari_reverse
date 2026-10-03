/* fmdo.c — the FORM LIBRARY's half that waits on the user (`aes/fmdo.h`): fm_button and fm_do (gemfmlib), fm_dial,
 * the alerts — fm_alert (gemfmalt), fm_show, eralert, fm_error — and the bell. Alcyon C in the ROM (the bell hand
 * 68000), ported over its own order; the waits are the event layer's, reached through the event door
 * (`aes/evdoor.h`): ev_multi for fm_do, ev_button for fm_button.
 *
 * THE FRAMES ARE THE ROM's where an address escapes: the words fm_do, fm_button and fm_alert hand their callees by
 * address live in one frame each, laid out as the ROM's `link` lays it, and every one is read back through the image
 * after the call that writes it (`local_word`), as the ROM reads its frame; off target each frame is a `host_slot.h`
 * slot. eralert hands merge_str a pointer to a pointer to its drive's name, and fm_error the address of its own
 * argument: both are frame slots too.
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/ctrl.h"
#include "aes/evdoor.h"
#include "aes/fmdo.h"
#include "aes/fmlib.h"
#include "aes/gemgraf.h"
#include "aes/grwait.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/obedit.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/oblib.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "bios/bcon.h"

#define NO_KEY                0          /* ob_edit's key for EDINIT and EDEND ($fe74f6 clr.w -(sp))           */
/* w_update's bottom and top 0: from the top window down to the bottom one ($fec056, $fec066), none moved
 * ($fe7626..$fe762c clr.w). */
#define EVERY_WINDOW          0
#define NOT_MOVED             0
/* The fm_do of an alert starts on no field ($fe7156 clr.w (sp)). */
#define NO_START_FIELD        0

/* $fe3a0c — the bell: BIOS Bconout of a BEL to the console — on target the ROM's own `trap #13`, off it the BIOS's
 * core, handed the D0 the trap's dispatcher leaves (`bios/bcon.h`). What it answers no caller reads. */
void aes_bell(uint8_t *image)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    (void)bios_bconout(image, BIOS_BCONOUT, BELL_DEVICE, CON_BEL);
#else
    (void)image;
    (void)bios_trap_constant_char(BIOS_BCONOUT_FN, BELL_DEVICE, CON_BEL);
#endif
}

/* The rest of a radio group put down and `object` selected: every RBUTTON child of the object's parent, the one
 * clicked and any other SELECTED — each read by ob_fs into the frame's sibling word as the walk reaches it. The
 * object's new state, its own sibling's read with SELECTED set; `state` otherwise. */
static int16_t select_in_its_group(uint8_t *image, uint32_t tree, int16_t object, uint32_t frame, int16_t state)
{
    int16_t parent = aes_get_par(image, tree, object);
    int16_t sibling;

    for (sibling = object_word(image, tree, parent, OB_HEAD); sibling != parent;
         sibling = object_word(image, tree, sibling, OB_NEXT)) {
        int16_t sibling_state = aes_ob_fs(image, tree, sibling, frame + FM_BUTTON_SIBLING_FLAGS);

        if (!(local_word(image, frame, FM_BUTTON_SIBLING_FLAGS) & OB_FLAG_RBUTTON)
            || (!(sibling_state & OB_STATE_SELECTED) && sibling != object))
            continue;
        if (sibling == object)
            state = sibling_state = (int16_t)(sibling_state | OB_STATE_SELECTED);
        else
            sibling_state = (int16_t)(sibling_state & ~OB_STATE_SELECTED);
        aes_ob_change(image, tree, sibling, sibling_state, OB_CHANGE_REDRAW);
    }
    return state;
}

/* $fe7346 — fm_button: a click on `object`. A TOUCHEXIT object ends the form (a double click answers it with its top
 * bit set); a SELECTABLE one not DISABLED is taken — a radio button at once, its group put down, any other by
 * gr_watchbox, which toggles it while the mouse goes in and out until the button rises — and, the form going on, the
 * rise awaited (ev_button); a SELECTED EXIT object ends the form. The object stored at *next_at — the field clicked
 * when the form goes on, else 0 — and whether the form goes on answered. */
int16_t aes_fm_button(uint8_t *image, uint32_t tree, int16_t object, int16_t clicks, uint32_t next_at)
{
    uint16_t frame_local[FM_BUTTON_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FM_BUTTON_FRAME_BYTES, "fm_button's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_FM_BUTTON_FRAME, frame_local);
    int16_t go_on = FM_KEYBD_GO_ON, double_click = 0;
    int16_t state = aes_ob_fs(image, tree, object, frame + FM_BUTTON_FLAGS);
    uint16_t flags = (uint16_t)local_word(image, frame, FM_BUTTON_FLAGS);

    if (flags & OB_FLAG_TOUCHEXIT) {
        if (clicks == FM_DOUBLE_CLICKS)
            double_click = (int16_t)FM_DOUBLE_CLICKED;
        go_on = FM_KEYBD_DONE;
    }
    if ((flags & OB_FLAG_SELECTABLE) && !(state & OB_STATE_DISABLED)) {
        if (flags & OB_FLAG_RBUTTON)
            state = select_in_its_group(image, tree, object, frame, state);
        else if (aes_gr_watchbox(image, tree, object, (int16_t)(state ^ OB_STATE_SELECTED), state))
            state ^= OB_STATE_SELECTED;
        /* The ROM tests the flags for SELECTABLE | EDITABLE too ($fe7450 andi.w #9), always true for the SELECTABLE
         * object this arm takes. */
        if (go_on)
            (void)evdoor_ev_button(image, FM_RISE_CLICKS, FM_RISE_BUTTON, FM_RISE_UP, frame + FM_BUTTON_ANSWERS);
    }
    if ((state & OB_STATE_SELECTED) && (flags & OB_FLAG_EXIT))
        go_on = FM_KEYBD_DONE;
    if (go_on && !(flags & OB_FLAG_EDITABLE))
        object = 0;
    set_bus_word(image, next_at, (uint16_t)(object | double_click));
    host_slot_release(AES_FM_BUTTON_FRAME);
    return go_on;
}

/* $fe74a4 — fm_do: a dialog run until it is done — the screen owned (fm_own), the keys queued before flushed, the
 * clip the screen below the bar, editing started in `start` (or the first field); then a wait per pass for a key or a
 * press: a key a move between fields or the default button (fm_keybd), else typed into the field; a press on an
 * object handled by fm_button, off the tree a bell; a move to another field — or the end — ends the edit in the old
 * one. Answers the object the form ended on. */
int16_t aes_fm_do(uint8_t *image, uint32_t tree, int16_t start)
{
    uint16_t frame_local[FM_DO_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FM_DO_FRAME_BYTES, "fm_do's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_FM_DO_FRAME, frame_local);
    uint32_t next_at = frame + FM_DO_NEXT, index_at = frame + FM_DO_INDEX;
    int16_t edit = 0, go_on = FM_KEYBD_GO_ON, next;
    uint16_t events;

    (void)aes_fm_own(image, FM_OWN_TAKE);
    aes_fq(image);
    (void)aes_gsx_sclip(image, AES_GL_RFULL);
    set_local_word(image, frame, FM_DO_NEXT, aes_fm_inifld(image, tree, start));
    do {
        next = local_word(image, frame, FM_DO_NEXT);
        if (next && edit != next) {
            edit = next;
            set_local_word(image, frame, FM_DO_NEXT, 0);
            (void)aes_ob_edit(image, tree, edit, NO_KEY, index_at, OB_EDIT_INIT);
        }
        events = evdoor_ev_multi(image, EV_MU_KEYBD | EV_MU_BUTTON, 0, 0, 0,
                                 EV_BUTTON_PARAMETER(FM_DO_CLICKS, FM_DO_BUTTONS, FM_DO_BUTTON_DOWN), 0,
                                 frame + FM_DO_ANSWERS);
        if (events & EV_MU_KEYBD) {
            go_on = aes_fm_keybd(image, tree, edit, frame + FM_DO_KEY, next_at);
            if (local_word(image, frame, FM_DO_KEY))
                (void)aes_ob_edit(image, tree, edit, local_word(image, frame, FM_DO_KEY), index_at, OB_EDIT_CHAR);
        }
        if (events & EV_MU_BUTTON) {
            set_local_word(image, frame, FM_DO_NEXT, aes_ob_find(image, tree, OB_ROOT, FM_DO_FIND_DEPTH,
                                                                  local_word(image, frame, FM_DO_MOUSE_X),
                                                                  local_word(image, frame, FM_DO_MOUSE_Y)));
            if (local_word(image, frame, FM_DO_NEXT) == FM_DO_NONE_FOUND) {
                aes_bell(image);
                set_local_word(image, frame, FM_DO_NEXT, 0);
            } else {
                go_on = aes_fm_button(image, tree, local_word(image, frame, FM_DO_NEXT),
                                      local_word(image, frame, FM_DO_CLICK_COUNT), next_at);
            }
        }
        next = local_word(image, frame, FM_DO_NEXT);
        if (!go_on || (next && next != edit))
            (void)aes_ob_edit(image, tree, edit, NO_KEY, index_at, OB_EDIT_END);
    } while (go_on);
    (void)aes_fm_own(image, FM_OWN_GIVE_BACK);
    next = local_word(image, frame, FM_DO_NEXT);
    host_slot_release(AES_FM_DO_FRAME);
    return next;
}

/* What gsx_mon leaves in D0 (`aes/fmdo.h`): 1 while the hide nest is still open, else v_show_c's answer. */
static uint16_t cursor_shown_answer(const uint8_t *image)
{
    return be16(image + AES_GL_MOFF) ? FM_DIAL_NEST_OPEN_ANSWER : FM_DIAL_SHOWN_ANSWER;
}

/* $fe75ec — fm_dial: the whole screen the clip, then FMD_GROW a box grown from `little` out to `big`, FMD_SHRINK one
 * shrunk back, FMD_FINISH the desktop and the windows redrawn under `big`; FMD_START and any other type nothing.
 * Answers the D0 the desk's binding stores (`aes/fmdo.h`). */
uint16_t aes_fm_dial(uint8_t *image, int16_t type, uint32_t little, uint32_t big)
{
    (void)aes_gsx_sclip(image, AES_GL_RSCREEN);
    switch (type) {
    case FMD_GROW:
        aes_gr_growbox(image, little, big);
        return cursor_shown_answer(image);
    case FMD_SHRINK:
        aes_gr_shrinkbox(image, little, big);
        return cursor_shown_answer(image);
    case FMD_FINISH:
        aes_w_drawdesk(image, big);
        aes_w_update(image, EVERY_WINDOW, big, EVERY_WINDOW, NOT_MOVED);
        return be16(image + AES_GL_WFROZEN) ? FM_DIAL_HELD_ANSWER : cursor_shown_answer(image);
    default:
        return (uint16_t)type;
    }
}

/* $fe7002 — fm_alert: the AES's alert tree (resource tree 1) laid out for `string` — its root OUTLINED, the string
 * parsed into it and the tree built, `default_button` (1..3, 0 none) made DEFAULT, the icon's BITBLK fetched when it
 * has one, every object fixed to pixels and the icon made 32 x 32 — centred, drawn over the screen it saves under
 * the screen lock, and run by fm_do with the mouse the AES's; then the screen and the clip put back. Answers the
 * button that ended it, 1 for the first. */
int16_t aes_fm_alert(uint8_t *image, int16_t default_button, uint32_t string)
{
    uint16_t frame_local[FM_ALERT_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FM_ALERT_FRAME_BYTES, "fm_alert's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_FM_ALERT_FRAME, frame_local);
    uint32_t clip = frame + FM_ALERT_CLIP, box = frame + FM_ALERT_BOX, tree_at = frame + FM_ALERT_TREE;
    int16_t object, button;

    (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_TREE, ALERT_TREE_INDEX, tree_at);
    set_object_word(image, be32(image + tree_at), OB_ROOT, OB_STATE, ALERT_ROOT_STATE);
    aes_fm_parse(image, be32(image + tree_at), string, frame + FM_ALERT_ICON, frame + FM_ALERT_LINES,
                 frame + FM_ALERT_LINE_LENGTH, frame + FM_ALERT_BUTTONS, frame + FM_ALERT_BUTTON_LENGTH);
    aes_fm_build(image, be32(image + tree_at), local_word(image, frame, FM_ALERT_ICON) != 0,
                 local_word(image, frame, FM_ALERT_LINES), local_word(image, frame, FM_ALERT_LINE_LENGTH),
                 local_word(image, frame, FM_ALERT_BUTTONS), local_word(image, frame, FM_ALERT_BUTTON_LENGTH));
    if (default_button) {
        uint32_t flags = object_address(be32(image + tree_at), (int16_t)(default_button + ALERT_BUTTON_NUMBERED),
                                        OB_FLAGS);

        set_bus_word(image, flags, (uint16_t)(bus_word(image, flags) | OB_FLAG_DEFAULT));
    }
    if (local_word(image, frame, FM_ALERT_ICON)) {
        (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_BITBLK,
                           (int16_t)(local_word(image, frame, FM_ALERT_ICON) - 1), frame + FM_ALERT_BITBLK);
        set_bus_long(image, object_address(be32(image + tree_at), ALERT_ICON_OBJECT, OB_SPEC),
                     be32(image + frame + FM_ALERT_BITBLK));
    }
    for (object = 0; object < ALERT_OBJECTS; object++)
        (void)aes_rs_obfix(image, be32(image + tree_at), object);
    set_object_word(image, be32(image + tree_at), ALERT_ICON_OBJECT, OB_WIDTH, ALERT_ICON_PIXELS);
    set_object_word(image, be32(image + tree_at), ALERT_ICON_OBJECT, OB_HEIGHT, ALERT_ICON_PIXELS);
    aes_ob_center(image, be32(image + tree_at), box);
    (void)aes_wm_update(image, WM_BEG_UPDATE);
    aes_gsx_gclip(image, clip);
    aes_bb_save(image, box);
    (void)aes_gsx_sclip(image, box);
    aes_ob_draw(image, be32(image + tree_at), OB_ROOT, ALERT_DRAW_DEPTH);
    aes_ct_mouse(image, CT_MOUSE_GRAB);
    button = aes_fm_do(image, be32(image + tree_at), NO_START_FIELD);
    aes_ct_mouse(image, CT_MOUSE_RELEASE);
    (void)aes_gsx_sclip(image, box);
    aes_bb_restore(image, box);
    (void)aes_gsx_sclip(image, clip);
    (void)aes_wm_update(image, WM_END_UPDATE);
    host_slot_release(AES_FM_ALERT_FRAME);
    return (int16_t)(button - ALERT_BUTTON_NUMBERED);
}

/* $fe764c — fm_show: the AES's string `string_number` (rs_str's copy), merged with `values` into AES_FM_SHOW_ALERT
 * when there are any, shown as an alert with `default_button`; its answer. */
int16_t aes_fm_show(uint8_t *image, int16_t string_number, uint32_t values, int16_t default_button)
{
    uint32_t alert = aes_rs_str(image, string_number);

    if (values) {
        aes_merge_str(image, AES_FM_SHOW_ALERT, alert, values);
        alert = AES_FM_SHOW_ALERT;
    }
    return aes_fm_alert(image, default_button, alert);
}

/* eralert's and fm_error's answer out of fm_show's: 0 when the alert's first button ended it, 1 otherwise. */
static int16_t first_button_answers_0(int16_t answer)
{
    return answer == ALERT_FIRST_ANSWERED ? 0 : 1;
}

/* $fe768c — eralert: the critical error handler's alert for `error` on `drive` — the string and the default button
 * read from the ROM's two tables (an index past them reads on, as the ROM's does), the drive's name ("A" + drive)
 * handed when the string names it. Answers 0 when the first button ended it, 1 otherwise (Retry). */
int16_t aes_eralert(uint8_t *image, int16_t error, int16_t drive)
{
    uint16_t frame_local[ERALERT_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_ERALERT_FRAME_BYTES, "eralert's frame and its host slot");
    uint32_t frame = host_slot_claim(AES_ERALERT_FRAME, frame_local);
    uint32_t level_at = table_entry(AES_ERALERT_LEVELS, error, sizeof(uint16_t));
    uint32_t values;
    int16_t level, answer;

    set_bus_byte(image, frame + ERALERT_DRIVE_NAME, (uint8_t)(drive + ERALERT_DRIVE_LETTER));
    set_bus_byte(image, frame + ERALERT_DRIVE_NAME + 1, STRING_NUL);
    set_bus_long(image, frame + ERALERT_DRIVE_POINTER, frame + ERALERT_DRIVE_NAME);
    level = (int16_t)(bus_word(image, level_at) & ERALERT_LEVEL_MASK);
    values = bus_word(image, level_at) & ERALERT_NAMES_DRIVE ? frame + ERALERT_DRIVE_POINTER : 0;
    answer = aes_fm_show(image, (int16_t)bus_word(image, table_entry(AES_ERALERT_STRINGS, error, sizeof(uint16_t))),
                         values, level);
    host_slot_release(AES_ERALERT_FRAME);
    return first_button_answers_0(answer);
}

/* fm_error's string for `code` — the jump table $fefa68, a row per code from FM_ERROR_FIRST_CODE, indexed UNSIGNED
 * (`subq.w #2`, `bhi`): every code it has no row for "TOS error #%W". */
#define ERROR_ROW(code)       ((code) - FM_ERROR_FIRST_CODE)

static int16_t error_string(int16_t code)
{
    switch ((uint16_t)ERROR_ROW(code)) {
    case ERROR_ROW(DOS_FILE_NOT_FOUND):
    case ERROR_ROW(DOS_PATH_NOT_FOUND):
    case ERROR_ROW(DOS_NO_MORE_FILES):        return FM_ERROR_NOT_FOUND;
    case ERROR_ROW(DOS_NO_HANDLES):           return FM_ERROR_NO_HANDLES;
    case ERROR_ROW(DOS_ACCESS_DENIED):        return FM_ERROR_DENIED;
    case ERROR_ROW(DOS_NO_MEMORY):
    case ERROR_ROW(DOS_BAD_ENVIRONMENT):
    case ERROR_ROW(DOS_BAD_FORMAT):           return FM_ERROR_NO_MEMORY;
    case ERROR_ROW(DOS_BAD_DRIVE):            return FM_ERROR_NO_DRIVE;
    default:                                  return FM_ERROR_TOS_ERROR;
    }
}

/* $fe7712 — fm_error: an MS-DOS error number's alert — nothing for one past FM_ERROR_LAST_CODE (a signed compare:
 * every negative code is shown) — "TOS error #%W" merged over the code's own word. Answers 0 when the first button
 * ended it, 1 otherwise; 0 for a code it does not show. */
int16_t aes_fm_error(uint8_t *image, int16_t code)
{
    uint16_t code_local = (uint16_t)code;
    _Static_assert(sizeof code_local == HOST_SLOT_AES_FM_ERROR_CODE_BYTES, "fm_error's argument and its host slot");
    uint32_t code_at;
    int16_t string, answer;

    if (code > FM_ERROR_LAST_CODE)
        return 0;
    string = error_string(code);
    code_at = host_slot_claim(AES_FM_ERROR_CODE, &code_local);
    host_slot_store_words(image, code_at, &code_local, 1);
    answer = aes_fm_show(image, string, string == FM_ERROR_TOS_ERROR ? code_at : 0, FM_ERROR_LEVEL);
    host_slot_release(AES_FM_ERROR_CODE);
    return first_button_answers_0(answer);
}
