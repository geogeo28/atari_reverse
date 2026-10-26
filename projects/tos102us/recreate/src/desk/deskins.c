/* deskins.c — THE DESK'S TWO INSTALL DIALOGS (`desk/deskins.h`): ins_disk `$fdf11a` and ins_app `$fdf3c8`. Alcyon C in
 * the ROM, ported over its own order; each runs its dialog through inf_show (`desk/deskinf.h`). COMPILED FOR THE TARGET
 * ALONE (the user's R3, ruling O1): no host twin, no Tier 1 — each held by its target-only rows at the hands' arrivals
 * (`test/test_desk_w3a.py`).
 */
#include <stdint.h>

#ifndef RECREATE_HOST_DIFFERENTIAL
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/objects.h"
#include "aes/objtext.h"
#include "aes/strings.h"
#include "desk/deskapp.h"
#include "desk/deskglobals.h"
#include "desk/deskinf.h"
#include "desk/deskins.h"
#include "desk/deskleaf.h"

/* A text's NUL made the INF's end mark `@`, so scan_str takes it whole. */
static void inf_text_ended(uint8_t *image, uint32_t text)
{
    set_bus_byte(image, offset_by(text, aes_strlen(image, text)), INF_TEXT_END);
}

/* Where a new disk icon steps from `spot` by one grid `step`: on, past the screen's middle `middle`, back before it. */
static int16_t stepped(int16_t middle, int16_t spot, int16_t step)
{
    return middle > spot ? (int16_t)(step + spot) : (int16_t)(spot - step);
}

/* ins_disk's NEW ANODE for a letter changed — the old one `anode` copied (its flags, object, label, icon), its type a
 * cartridge's for `c` and a disk's else, no documents' icon, the letter `letter` (its byte signed), its spot a grid
 * step from the old one's toward the screen's middle — and then, the ROM's, its y the old one's plus an icon's
 * height — snapped to the grid. app_alloc's node, unchecked (the ROM's). */
static uint32_t disk_node_made(uint8_t *image, uint32_t anode, uint8_t letter)
{
    uint32_t desk = desk_globals(image), node = aes_app_alloc(image, APP_ALLOC_AT_THE_TAIL);
    int16_t x = (int16_t)bus_word(image, anode + ANODE_XSPOT), y = (int16_t)bus_word(image, anode + ANODE_YSPOT);
    int16_t middle_x = (int16_t)((int16_t)be16(image + AES_GL_WIDTH) / INS_HALF);
    int16_t middle_y = (int16_t)((int16_t)(be16(image + AES_GL_HEIGHT) - be16(image + AES_GL_HBOX)) / INS_HALF);

    set_bus_word(image, node + ANODE_FLAGS, bus_word(image, anode + ANODE_FLAGS));
    set_bus_word(image, node + ANODE_TYPE, letter == INS_CARTRIDGE_LETTER ? AT_ISCART : AT_ISDISK);
    set_bus_word(image, node + ANODE_OBID, bus_word(image, anode + ANODE_OBID));
    set_bus_long(image, node + ANODE_PAPPL, bus_long(image, anode + ANODE_PAPPL));
    set_bus_long(image, node + ANODE_PDATA, 0);
    set_bus_word(image, node + ANODE_AICON, bus_word(image, anode + ANODE_AICON));
    set_bus_word(image, node + ANODE_DICON, (uint16_t)INS_NO_ICON);
    set_bus_word(image, node + ANODE_LETTER, (uint16_t)(int8_t)letter);
    set_bus_word(image, node + ANODE_XSPOT, (uint16_t)stepped(middle_x, x, (int16_t)bus_word(image, desk + DESK_GRID_W)));
    set_bus_word(image, node + ANODE_YSPOT, (uint16_t)stepped(middle_y, y, (int16_t)bus_word(image, desk + DESK_GRID_H)));
    set_bus_word(image, node + ANODE_YSPOT, (uint16_t)(bus_word(image, desk + DESK_G_HICON) + (uint16_t)y));
    aes_snap_disk(image, (int16_t)bus_word(image, node + ANODE_XSPOT), (int16_t)bus_word(image, node + ANODE_YSPOT),
                  node + ANODE_XSPOT, node + ANODE_YSPOT);
    return node;
}

/* ins_disk's Remove: every ANODE in use with the chosen icon and the letter typed freed, the list walked again from its
 * head after each. Whether one was. */
static int16_t disks_removed(uint8_t *image, int16_t icon, uint8_t letter)
{
    uint32_t anode = bus_long(image, desk_globals(image) + DESK_ANODES_IN_USE);
    int16_t changed = INS_UNCHANGED;

    while (anode != ANODE_NONE) {
        if ((int16_t)bus_word(image, anode + ANODE_AICON) == icon && (int16_t)bus_word(image, anode + ANODE_LETTER) == (int8_t)letter) {
            aes_app_free(image, anode);
            anode = bus_long(image, desk_globals(image) + DESK_ANODES_IN_USE);
            changed = INS_CHANGED;
        } else {
            anode = bus_long(image, anode + ANODE_NEXT);
        }
    }
    return changed;
}

/* $fdf11a — ins_disk: Options > Install Disk Drive for the disk icon `anode`. Its letter and label set and the dialog
 * run; the letter typed made upper case — but a blank (nothing to do) and the cartridge's `c`. Install: a letter
 * changed makes a new ANODE (`disk_node_made`), and a label changed is kept (scan_str) in whichever. Remove: the disks
 * with the chosen icon and that letter freed. Cancel: its state cleared. The exit button's state cleared; whether an
 * ANODE changed. */
int16_t aes_desk_ins_disk(uint8_t *image, uint32_t anode)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(INS_DISK_FRAME_BYTES)];
    uint32_t frame = desk_local_address(frame_local), tree = bus_long(image, desk_globals(image) + DESK_INS_DISK_TREE);
    int16_t changed = INS_UNCHANGED, blank = 0, icon;
    uint8_t letter;

    set_bus_byte(image, frame + INS_DISK_OLD_LETTER, (uint8_t)bus_word(image, anode + ANODE_LETTER));
    set_bus_byte(image, frame + INS_DISK_OLD_LETTER + 1, 0);
    (void)aes_strcpy(image, bus_long(image, anode + ANODE_PAPPL), frame + INS_DISK_OLD_LABEL);
    aes_inf_sset(image, tree, INS_DISK_LETTER, frame + INS_DISK_OLD_LETTER);
    aes_inf_sset(image, tree, INS_DISK_LABEL, frame + INS_DISK_OLD_LABEL);
    (void)aes_desk_inf_show(image, tree, OB_ROOT);
    aes_fs_sget(image, tree, INS_DISK_LETTER, frame + INS_DISK_NEW_LETTER);
    aes_fs_sget(image, tree, INS_DISK_LABEL, frame + INS_DISK_NEW_LABEL);
    icon = (int16_t)(object_word(image, tree, INS_DISK_FLOPPY, OB_STATE) & OB_STATE_SELECTED);
    letter = bus_byte(image, frame + INS_DISK_NEW_LETTER);
    if (letter == INS_DISK_BLANK || letter == 0)
        blank = 1;
    else if (letter != INS_CARTRIDGE_LETTER)
        set_bus_byte(image, frame + INS_DISK_NEW_LETTER, (uint8_t)aes_toupper((int8_t)letter));
    letter = bus_byte(image, frame + INS_DISK_NEW_LETTER);
    if (dialog_selected(image, tree, INS_DISK_INSTALL)) {
        set_object_word(image, tree, INS_DISK_INSTALL, OB_STATE, 0);
        if (blank)
            return changed;
        if (bus_byte(image, frame + INS_DISK_OLD_LETTER) != letter) {
            anode = disk_node_made(image, anode, letter);
            changed = INS_CHANGED;
        }
        if (!aes_streq(image, frame + INS_DISK_OLD_LABEL, frame + INS_DISK_NEW_LABEL)) {
            inf_text_ended(image, frame + INS_DISK_NEW_LABEL);
            (void)aes_scan_str(image, frame + INS_DISK_NEW_LABEL, anode + ANODE_PAPPL);
            changed = INS_CHANGED;
        }
    } else if (dialog_selected(image, tree, INS_DISK_REMOVE)) {
        set_object_word(image, tree, INS_DISK_REMOVE, OB_STATE, 0);
        if (!blank)
            changed = disks_removed(image, icon, letter);
    } else if (dialog_selected(image, tree, INS_DISK_CANCEL)) {
        set_object_word(image, tree, INS_DISK_CANCEL, OB_STATE, 0);
    }
    return changed;
}

/* ins_app's kind of program, by the radio button chosen (`index` from the first): its a_flags. THE ROM LEAVES ITS LOCAL
 * UNSET where none is chosen (inf_gindex's -1) — reached by no run: the routine selects one before the dialog and a
 * radio group keeps one — and ours keeps the flags the program had. */
static int16_t kind_flags(int16_t index, int16_t had)
{
    switch (index) {
    case INS_APP_GEM - INS_APP_KIND_FIRST:
        return INS_APP_FLAGS_GEM;
    case INS_APP_TOS - INS_APP_KIND_FIRST:
        return INS_APP_FLAGS_TOS;
    case INS_APP_TTP - INS_APP_KIND_FIRST:
        return INS_APP_FLAGS_TTP;
    }
    return had;
}

/* ins_app's NEW ANODE (app_alloc's, at the head; none where the pool is spent): flags `flags`, a file's type, no object;
 * its name and its documents' pattern ("*." and the extension, or nothing) kept as INF texts (scan_str); its two icons
 * by the icon button chosen (`icon`, from the first), no letter, no spot. The node, or ANODE_NONE. */
static uint32_t app_node_made(uint8_t *image, uint32_t frame, int16_t flags, int16_t icon)
{
    uint32_t node = aes_app_alloc(image, APP_ALLOC_AT_THE_HEAD), built = frame + INS_APP_BUILT;

    if (node == ANODE_NONE)
        return node;
    set_bus_word(image, node + ANODE_FLAGS, (uint16_t)flags);
    set_bus_word(image, node + ANODE_TYPE, AT_ISFILE);
    set_bus_word(image, node + ANODE_OBID, (uint16_t)INS_APP_NO_OBJECT);
    aes_unfmt_str(image, frame + INS_APP_NEW_NAME, built);
    inf_text_ended(image, built);
    (void)aes_scan_str(image, built, node + ANODE_PAPPL);
    if (bus_byte(image, frame + INS_APP_NEW_EXTENSION)) {
        (void)aes_strcpy(image, AES_DESK_INS_ANY_DATA, built);
        (void)aes_strcpy(image, frame + INS_APP_NEW_EXTENSION, built + INS_APP_PATTERN_HEAD);
    } else {
        set_bus_byte(image, built, 0);
    }
    inf_text_ended(image, built);
    (void)aes_scan_str(image, built, node + ANODE_PDATA);
    set_bus_word(image, node + ANODE_AICON, (uint16_t)(icon + INS_APP_ICON_BASE));
    set_bus_word(image, node + ANODE_DICON, (uint16_t)(icon + INS_APP_DOCUMENT_ICON));
    set_bus_word(image, node + ANODE_LETTER, 0);
    set_bus_word(image, node + ANODE_XSPOT, 0);
    set_bus_word(image, node + ANODE_YSPOT, 0);
    return node;
}

/* $fdf3c8 — ins_app: Options > Install Application for the program `name` of the ANODE `anode`. The name (8.3) and its
 * documents' extension (a_pdata past its dot) set, the kind button by its flags (GEM, TTP, else TOS) and its icon's
 * button selected; the dialog run, the kind and icon chosen read and their buttons cleared. OK: the kind's flags (the
 * old full-memory bit kept); where the name or the extension was edited, or the ANODE is a pattern's, a NEW ANODE
 * (`app_node_made`) takes them; flags that differ kept in the ANODE in hand; OK's state cleared. Cancel: its state
 * cleared. Whether an ANODE changed. */
int16_t aes_desk_ins_app(uint8_t *image, uint32_t name, uint32_t anode)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(INS_APP_FRAME_BYTES)];
    uint32_t frame = desk_local_address(frame_local), tree = bus_long(image, desk_globals(image) + DESK_INS_APP_TREE);
    uint32_t extension = bus_long(image, anode + ANODE_PDATA), made;
    uint8_t first = bus_byte(image, bus_long(image, anode + ANODE_PAPPL));
    int16_t a_pattern = first == INS_APP_WILD || first == INS_APP_ANY, changed, had, flags, kind, icon;

    aes_fmt_str(image, name, frame + INS_APP_OLD_NAME);
    while (bus_byte(image, extension) != 0 && bus_byte(image, extension) != INS_APP_DOT)
        extension++;
    if (bus_byte(image, extension) == INS_APP_DOT)
        extension++;
    (void)aes_strcpy(image, extension, frame + INS_APP_OLD_EXTENSION);
    aes_inf_sset(image, tree, INS_APP_NAME, frame + INS_APP_OLD_NAME);
    aes_inf_sset(image, tree, INS_APP_EXTENSION, frame + INS_APP_OLD_EXTENSION);
    had = (int16_t)bus_word(image, anode + ANODE_FLAGS);
    if (had & AF_ISCRYS)
        set_object_word(image, tree, INS_APP_GEM, OB_STATE, OB_STATE_SELECTED);
    else if (had & AF_ISPARM)
        set_object_word(image, tree, INS_APP_TTP, OB_STATE, OB_STATE_SELECTED);
    else
        set_object_word(image, tree, INS_APP_TOS, OB_STATE, OB_STATE_SELECTED);
    set_object_word(image, tree, (int16_t)((int16_t)bus_word(image, anode + ANODE_AICON) - INS_APP_ICON_BASE + INS_APP_ICON_FIRST),
                    OB_STATE, OB_STATE_SELECTED);
    (void)aes_desk_inf_show(image, tree, OB_ROOT);
    changed = INS_UNCHANGED;
    aes_fs_sget(image, tree, INS_APP_NAME, frame + INS_APP_NEW_NAME);
    aes_fs_sget(image, tree, INS_APP_EXTENSION, frame + INS_APP_NEW_EXTENSION);
    kind = aes_inf_gindex(image, tree, INS_APP_KIND_FIRST, INS_APP_KINDS);
    flags = kind_flags(kind, had);
    set_object_word(image, tree, (int16_t)(kind + INS_APP_KIND_FIRST), OB_STATE, 0);
    icon = aes_inf_gindex(image, tree, INS_APP_ICON_FIRST, INS_APP_ICONS);
    set_object_word(image, tree, (int16_t)(icon + INS_APP_ICON_FIRST), OB_STATE, 0);
    if (!dialog_selected(image, tree, INS_APP_OK)) {
        set_object_word(image, tree, INS_APP_CANCEL, OB_STATE, 0);
        return changed;
    }
    if (had & AF_ISFMEM)
        flags |= AF_ISFMEM;
    if (!aes_streq(image, frame + INS_APP_OLD_NAME, frame + INS_APP_NEW_NAME)
        || !aes_streq(image, frame + INS_APP_OLD_EXTENSION, frame + INS_APP_NEW_EXTENSION) || a_pattern) {
        made = app_node_made(image, frame, flags, icon);
        if (made != ANODE_NONE) {
            anode = made;
            changed = INS_CHANGED;
        }
    }
    if (had != flags) {
        set_bus_word(image, anode + ANODE_FLAGS, (uint16_t)flags);
        changed = INS_CHANGED;
    }
    set_object_word(image, tree, INS_APP_OK, OB_STATE, 0);
    return changed;
}
#endif
