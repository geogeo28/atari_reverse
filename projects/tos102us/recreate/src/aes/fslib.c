/* fslib.c — the FILE SELECTOR (`aes/fslib.h`): its tree found and centred (fs_start), a path cut back to its directory
 * and its spec found (fs_back, fs_pspec), a directory read, filtered and sorted (fs_active), the list's top moved a row
 * (fs_1scroll), nine names laid into the list and the slider sized (fs_format), a row selected (fs_sel), the list
 * scrolled on the screen (fs_nscroll), a directory read and shown (fs_newdir), and the selector run until OK or Cancel
 * (fs_input: its waits are fm_do's and gr_slidebox's, through the event door). Alcyon C in the ROM, ported over its
 * own order.
 *
 * Every read is where the ROM makes it: fs_input's three blocks are reached through their globals, re-read at every
 * use (a name's copy or an index store may lie over one); a row, a count or an offset is a SIGNED word, every compare a
 * signed one, every word sum a word that wraps; every pointer a caller hands in is put on the 24-bit bus.
 *
 * THE FRAMES ARE THE ROM's where an address escapes: fs_start's tree (to rs_gaddr), fs_format's two answers (to
 * fs_sset), fs_nscroll's two GRECTs (to gsx_gclip, ob_actxywh and gsx_sclip) and fs_input's answers, selected row,
 * mouse and count stand in through `host_slot.h` off target, each laid out as the ROM's `link` lays it.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/ctrl.h"
#include "aes/fmdo.h"
#include "aes/fslib.h"
#include "aes/gemdosif.h"
#include "aes/gemgraf.h"
#include "aes/grdrag.h"
#include "aes/gsxif.h"
#include "aes/obedit.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/objtext.h"
#include "aes/oblib.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/strings.h"
#include "aes/wmupdate.h"
#include "gemdos/fs.h"

/* The ROM's immediates, which are GEMDOS's values: `aes/fslib.h` spells them as the ROM does, these pin them equal. */
_Static_assert(FS_SEARCH_ATTRIBUTES == GEMDOS_ATTR_SUBDIR, "fs_active's search is not F_SUBDIR");
_Static_assert(FS_KIND_BEFORE_NAME == DTA_NAME - (DTA_FILELN + sizeof(uint32_t) - 1),
               "a name's kind is the last byte of the DTA's file length");

/* $fe7782 — fs_start: the selector's tree (the AES resource's tree 0) kept in ad_fstree, and centred: its box into
 * gl_rfs. */
void aes_fs_start(uint8_t *image)
{
    uint32_t tree_local;
    _Static_assert(sizeof tree_local == HOST_SLOT_AES_FS_START_TREE_BYTES, "fs_start's tree and its host slot");
    uint32_t tree_at = host_slot_claim(AES_FS_START_TREE, &tree_local);

    (void)aes_rs_gaddr(image, be32(image + AES_RS_SYSTEM_GLOBAL), R_TREE, FS_TREE_INDEX, tree_at);
    wr32(image + AES_AD_FSTREE, be32(image + tree_at));
    aes_ob_center(image, be32(image + tree_at), AES_GL_RFS);
    host_slot_release(AES_FS_START_TREE);
}

/* $fe77ae — fs_back: from `end` back to the nearest `:` or `\`, or to `path` itself (the two POINTERS compared whole);
 * stopped on a `:`, a `\` is put in after it (ins_char, in FS_PATH_ROOM bytes) and that is where the answer points. */
uint32_t aes_fs_back(uint8_t *image, uint32_t path, uint32_t end)
{
    while (bus_byte(image, end) != SH_DRIVE_SEPARATOR && bus_byte(image, end) != SH_DIRECTORY_SEPARATOR && end != path)
        end--;
    if (bus_byte(image, end) == SH_DRIVE_SEPARATOR) {
        end++;
        aes_ins_char(image, end, 0, SH_DIRECTORY_SEPARATOR, FS_PATH_ROOM);
    }
    return end;
}

/* $fe77ee — fs_pspec: where the file spec starts — past the `\` fs_back stops on; with none, the path becomes the
 * ROM's "A:\*.*" and the spec is that one's. */
uint32_t aes_fs_pspec(uint8_t *image, uint32_t path, uint32_t end)
{
    uint32_t spec = aes_fs_back(image, path, end);

    if (bus_byte(image, spec) == SH_DIRECTORY_SEPARATOR)
        return spec + 1;
    (void)aes_strcpy(image, AES_FS_DEFAULT_PATH, path);
    return path + FS_DEFAULT_SPEC_AT;
}

/* fs_input's blocks, each through its global where it is used. */
static inline uint32_t dta_at(const uint8_t *image, uint32_t offset)
{
    return be32(image + AES_AD_FSDTA) + offset;
}

/* Where name `entry`'s offset is kept: the index's longword — the entry sign-extended, then scaled. */
static inline uint32_t index_at(const uint8_t *image, int32_t entry)
{
    return table_entry(be32(image + AES_AD_FSINDEX), entry, FS_INDEX_ENTRY_BYTES);
}

/* ...and the name itself: the names block plus that offset, a longword sum. */
static inline uint32_t name_at(const uint8_t *image, int32_t entry)
{
    return bus_long(image, index_at(image, entry)) + be32(image + AES_AD_FSNAMES);
}

/* One entry of the search ($fe785e..$fe78a6): `.` and `..` apart, it is marked with its kind — the byte below the DTA's
 * name — and then listed if it is a folder, or a file matching `spec`. Is it listed? */
static int marked_entry_is_listed(uint8_t *image, uint32_t spec)
{
    uint8_t kind;

    if (bus_byte(image, dta_at(image, DTA_NAME)) == FS_HIDDEN_FIRST)
        return 0;
    kind = bus_byte(image, dta_at(image, DTA_FOUND_ATTR)) & GEMDOS_ATTR_SUBDIR ? FS_FOLDER_MARK : FS_FILE_MARK;
    set_bus_byte(image, dta_at(image, DTA_NAME - FS_KIND_BEFORE_NAME), kind);
    return bus_byte(image, dta_at(image, DTA_NAME - FS_KIND_BEFORE_NAME)) == FS_FOLDER_MARK
           || aes_wildcmp(image, spec, dta_at(image, DTA_NAME));
}

/* The search's loop ($fe785e..$fe7914): each entry listed (above) copied — kind and name — to the names block at the
 * offset the index then holds. Fsnext after every entry; at FS_NAMES names the search is over and the bell rung
 * (GEMDOS Cconout). The count of names kept. */
static int16_t read_directory(uint8_t *image, uint32_t path, uint32_t spec)
{
    int16_t kept = 0, used = 0;
    int16_t more = aes_dos_sfirst(image, path, FS_SEARCH_ATTRIBUTES);

    while (more) {
        if (marked_entry_is_listed(image, spec)) {
            int16_t length = aes_lstcpy(image, be32(image + AES_AD_FSNAMES) + (uint32_t)(int32_t)used,
                                        dta_at(image, DTA_NAME - FS_KIND_BEFORE_NAME));

            set_bus_long(image, index_at(image, kept), (uint32_t)(int32_t)used);
            used = (int16_t)(used + length + FS_NAME_SPARE);
            kept++;
        }
        more = aes_dos_snext(image);
        if (kept >= FS_NAMES) {
            more = 0;
            (void)aes_dos_cconout(image, AES_FS_ACTIVE_BELL_RETURN, CON_BEL);
        }
    }
    return kept;
}

/* The sort ($fe7920..$fe79ee): a shell sort of the index by the names it points at — kind first, so folders (7) come
 * before files (a space) — each pair copied out to the two scratches and compared by strchk; the gap from half the
 * count down to 1. */
static void sort_names(uint8_t *image, int16_t count)
{
    int16_t gap, upper, lower;

    for (gap = (int16_t)(count / FS_SORT_SHRINK); gap > 0; gap = (int16_t)(gap / FS_SORT_SHRINK)) {
        for (upper = gap; upper < count; upper++) {
            for (lower = (int16_t)(upper - gap); lower >= 0; lower = (int16_t)(lower - gap)) {
                uint32_t offset;

                (void)aes_lstcpy(image, AES_FS_TEXT, name_at(image, lower));
                (void)aes_lstcpy(image, AES_FS_NAME, name_at(image, (int32_t)lower + gap));
                if (aes_strchk(image, AES_FS_TEXT, AES_FS_NAME) <= 0)
                    break;
                offset = bus_long(image, index_at(image, lower));
                set_bus_long(image, index_at(image, lower), bus_long(image, index_at(image, (int32_t)lower + gap)));
                set_bus_long(image, index_at(image, (int32_t)lower + gap), offset);
            }
        }
    }
}

/* $fe7826 — fs_active: the directory `path` names read into fs_input's blocks (Fsetdta, Fsfirst with folders, Fsnext),
 * its files filtered by `spec`, the count stored through `count_at`, then the names sorted; the mouse the busy form
 * while it runs and the arrow after. */
int16_t aes_fs_active(uint8_t *image, uint32_t path, uint32_t spec, uint32_t count_at)
{
    int16_t count;

    aes_gsx_mfset(image, be32(image + AES_AD_HGMICE));
    (void)aes_dos_sdta(image, AES_FS_ACTIVE_SDTA_RETURN, be32(image + AES_AD_FSDTA));
    count = read_directory(image, path, spec);
    set_bus_word(image, count_at, (uint16_t)count);
    sort_names(image, count);
    aes_gsx_mfset(image, be32(image + AES_AD_ARMICE));
    return FS_ACTIVE_ANSWER;
}

/* $fe79fe — fs_1scroll: the list's top one row up (`arrow` the up arrow's object) or down (any other), kept from below
 * 0 and from leaving fewer than FS_ROWS names under it; with no more names than rows, the top as it was. */
int16_t aes_fs_1scroll(int16_t top, int16_t count, int16_t arrow)
{
    int16_t moved = (int16_t)(arrow == FS_UP_ARROW ? top - 1 : top + 1);

    if (moved < 0)
        moved++;
    if ((int16_t)(count - moved) < FS_ROWS)
        moved--;
    return count > FS_ROWS ? moved : top;
}

/* The elevator ($fe7b00..$fe7b56): as tall as the slider's track — or, with more names than rows, the rows' share of it
 * (at least half a box) — and as far down it as `top` is down the names it can scroll by. */
static void size_elevator(uint8_t *image, uint32_t tree, int16_t top, int16_t count)
{
    int16_t track = object_word(image, tree, FS_SLIDER, OB_HEIGHT);
    int16_t height = track, place = 0;

    if (count > FS_ROWS) {
        height = aes_mul_div(FS_ROWS, height, count);
        height = aes_max((int16_t)(global_word(image, AES_GL_HBOX) / FS_HALF), height);
        place = aes_mul_div(top, (int16_t)(track - height), (int16_t)(count - FS_ROWS));
    }
    set_object_word(image, tree, FS_ELEVATOR, OB_Y, place);
    set_object_word(image, tree, FS_ELEVATOR, OB_HEIGHT, height);
}

/* $fe7a44 — fs_format: the list's nine rows from name `top` on — each name's kind byte, then its 8.3 name formatted
 * (fmt_str); a row past the names a space — set as the row's text (fs_sset) and the row's state cleared; then the
 * elevator sized and placed. */
int16_t aes_fs_format(uint8_t *image, uint32_t tree, int16_t top, int16_t count)
{
    uint16_t frame_local[FS_FORMAT_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FS_FORMAT_FRAME_BYTES, "fs_format's answers and their host slot");
    uint32_t frame = host_slot_claim(AES_FS_FORMAT_FRAME, frame_local);
    int16_t named = aes_min(FS_ROWS, (int16_t)(count - top));
    int16_t row;

    for (row = 0; row < FS_ROWS; row++) {
        if (row < named) {
            (void)aes_lstcpy(image, AES_FS_NAME, name_at(image, (int32_t)row + top));
            aes_fmt_str(image, AES_FS_NAME_BODY, AES_FS_TEXT_BODY);
            image[AES_FS_TEXT] = image[AES_FS_NAME];
        } else {
            image[AES_FS_TEXT] = FS_EMPTY_ROW;
            image[AES_FS_TEXT_BODY] = STRING_NUL;
        }
        aes_fs_sset(image, tree, (int16_t)(row + FS_FIRST_NAME), AES_FS_TEXT, frame + FS_FORMAT_TEXT,
                    frame + FS_FORMAT_LENGTH);
        set_object_word(image, tree, (int16_t)(row + FS_FIRST_NAME), OB_STATE, FS_PUT_DOWN);
    }
    size_elevator(image, tree, top, count);
    host_slot_release(AES_FS_FORMAT_FRAME);
    return FS_FORMAT_ANSWER;
}

/* $fe7b70 — fs_sel: row `row` of the selector's own tree (ad_fstree) changed to `state` and drawn; row 0 is none. */
void aes_fs_sel(uint8_t *image, int16_t row, int16_t state)
{
    if (row)
        aes_ob_change(image, be32(image + AES_AD_FSTREE), (int16_t)(row + FS_ROW_OBJECT_BEFORE), state, OB_CHANGE_REDRAW);
}

/* The list moved on the screen by `moved` rows ($fe7c10..$fe7cc0): the rows that stay copied up (`moved` > 0: the
 * names scrolled on) or down, and `list` — the first row's rectangle, already made nine rows tall — cut to the rows
 * that came in, which the caller then draws. Nine rows or more: nothing copied, the whole list drawn. */
static void scroll_rows(uint8_t *image, uint32_t list, int16_t moved, int16_t row_height)
{
    int16_t down = moved <= 0;
    int16_t stay, shift;

    if (down)
        moved = (int16_t)-moved;
    if (moved >= FS_ROWS)
        return;
    stay = (int16_t)m68k_muls_w((uint16_t)(FS_ROWS - moved), (uint16_t)row_height);
    shift = (int16_t)(m68k_muls_w((uint16_t)moved, (uint16_t)row_height) + local_word(image, list, GRECT_Y));
    if (down) {
        aes_bb_screen(image, FS_SCROLL_RULE, local_word(image, list, GRECT_X), local_word(image, list, GRECT_Y),
                      local_word(image, list, GRECT_X), shift, local_word(image, list, GRECT_W), stay);
    } else {
        aes_bb_screen(image, FS_SCROLL_RULE, local_word(image, list, GRECT_X), shift, local_word(image, list, GRECT_X),
                      local_word(image, list, GRECT_Y), local_word(image, list, GRECT_W), stay);
        set_local_word(image, list, GRECT_Y, (int16_t)(local_word(image, list, GRECT_Y) + stay));
    }
    set_local_word(image, list, GRECT_H, (int16_t)m68k_muls_w((uint16_t)moved, (uint16_t)row_height));
}

/* $fe7b92 — fs_nscroll: the list's top moved `rows` rows by `arrow` (fs_1scroll, each from the last); if it moved, the
 * selected row (*row_at) deselected and forgotten, the list formatted from the new top, the rows that stay copied on
 * the screen and the ones that came in drawn under a clip of their own, then the slider under the caller's clip. The
 * top, moved or not. */
int16_t aes_fs_nscroll(uint8_t *image, uint32_t tree, uint32_t row_at, int16_t top, int16_t count, int16_t arrow,
                       int16_t rows)
{
    uint16_t frame_local[FS_NSCROLL_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FS_NSCROLL_FRAME_BYTES, "fs_nscroll's GRECTs and their host slot");
    uint32_t frame, clip, list;
    int16_t new_top = top, moved, step, row_height;

    for (step = 0; step < rows; step++)
        new_top = aes_fs_1scroll(new_top, count, arrow);
    moved = (int16_t)(new_top - top);
    if (!moved)
        return top;
    frame = host_slot_claim(AES_FS_NSCROLL_FRAME, frame_local);
    clip = frame + FS_NSCROLL_CLIP;
    list = frame + FS_NSCROLL_ROWS;
    aes_fs_sel(image, (int16_t)bus_word(image, row_at), FS_PUT_DOWN);
    set_bus_word(image, row_at, 0);
    (void)aes_fs_format(image, tree, new_top, count);
    aes_gsx_gclip(image, clip);
    aes_ob_actxywh(image, tree, FS_FIRST_NAME, list);
    row_height = local_word(image, list, GRECT_H);
    set_local_word(image, list, GRECT_H, (int16_t)m68k_muls_w((uint16_t)row_height, FS_ROWS));
    scroll_rows(image, list, moved, row_height);
    (void)aes_gsx_sclip(image, list);
    aes_ob_draw(image, tree, FS_FILE_BOX, FS_DRAW_DEPTH);
    (void)aes_gsx_sclip(image, clip);
    aes_ob_draw(image, tree, FS_SLIDER, FS_DRAW_DEPTH);
    host_slot_release(AES_FS_NSCROLL_FRAME);
    return new_top;
}

/* $fe7cfa — fs_newdir: the path field drawn, the directory read (fs_active) and its first nine names laid into the
 * list (fs_format), the title made " " + the spec + " " (copied to `title`), and the title, the list and the slider
 * drawn — the ROM's own list of them, read in place. */
void aes_fs_newdir(uint8_t *image, uint32_t title, uint32_t path, uint32_t spec, uint32_t tree, uint32_t count_at)
{
    uint32_t drawn;

    aes_ob_draw(image, tree, FS_DIRECTORY, FS_DRAW_DEPTH);
    (void)aes_fs_active(image, path, spec, count_at);
    (void)aes_fs_format(image, tree, 0, (int16_t)bus_word(image, count_at));
    image[AES_FS_TEXT] = STRING_SPACE;
    (void)aes_strcpy(image, spec, AES_FS_TEXT_BODY);
    (void)aes_strcat(image, AES_FS_TITLE_TAIL, AES_FS_TEXT_BODY);
    (void)aes_lstcpy(image, title, AES_FS_TEXT);
    for (drawn = AES_FS_REDRAWN; bus_byte(image, drawn) != 0; drawn++)
        aes_ob_draw(image, tree, (int8_t)bus_byte(image, drawn), FS_DRAW_DEPTH);
}

/* ---- fs_input ----------------------------------------------------------------------------------------------------- */

/* A longword of fs_input's frame — a field's text pointer, as fs_sset answered it — read where it is used. */
static inline uint32_t frame_long(const uint8_t *image, uint32_t frame, uint32_t local)
{
    return be32(image + frame + local);
}

/* The working path's end: the path's own buffer plus the length the frame holds, a word sign-extended. */
static inline uint32_t working_path_end(const uint8_t *image, uint32_t frame)
{
    return AES_RS_STRING + (uint32_t)(int32_t)local_word(image, frame, FS_INPUT_PATH_LENGTH);
}

/* fs_input's three blocks ($fe7d9e..$fe7e06): the names, the index, the DTA — each Malloc'd and kept in its global
 * before it is tested there; where one is refused, those before it freed (names first) and nothing answered. */
static int blocks_allocated(uint8_t *image)
{
    wr32(image + AES_AD_FSNAMES, aes_dos_alloc(image, FS_NAMES_BLOCK_BYTES));
    if (!be32(image + AES_AD_FSNAMES))
        return 0;
    wr32(image + AES_AD_FSINDEX, aes_dos_alloc(image, FS_INDEX_BLOCK_BYTES));
    if (!be32(image + AES_AD_FSINDEX)) {
        (void)aes_dos_free(image, AES_FS_INPUT_NAMES_ONLY_FREE_RETURN, be32(image + AES_AD_FSNAMES));
        return 0;
    }
    wr32(image + AES_AD_FSDTA, aes_dos_alloc(image, FS_DTA_BLOCK_BYTES));
    if (!be32(image + AES_AD_FSDTA)) {
        (void)aes_dos_free(image, AES_FS_INPUT_NAMES_FREE_RETURN_NO_DTA, be32(image + AES_AD_FSNAMES));
        (void)aes_dos_free(image, AES_FS_INPUT_INDEX_FREE_RETURN_NO_DTA, be32(image + AES_AD_FSINDEX));
        return 0;
    }
    return 1;
}

/* The selector made ready ($fe7e0a..$fe7ec0): the title " *.* ", the caller's path and its selection — formatted to
 * the field's 8.3 — set as the three fields' texts, each field's text pointer answered into the frame; the clip its
 * box; the form begun; the last path read forgotten, so the first pass reads; the root and its children drawn. */
static void show_selector(uint8_t *image, uint32_t tree, uint32_t frame, uint32_t path, uint32_t selection)
{
    aes_fs_sset(image, tree, FS_TITLE, AES_FS_FIRST_TITLE, frame + FS_INPUT_TITLE_TEXT, frame + FS_INPUT_TITLE_LENGTH);
    aes_fs_sset(image, tree, FS_DIRECTORY, path, frame + FS_INPUT_PATH_TEXT, frame + FS_INPUT_PATH_LENGTH);
    (void)aes_lstcpy(image, AES_FS_TEXT, selection);
    aes_fmt_str(image, AES_FS_TEXT, AES_FS_NAME);
    aes_fs_sset(image, tree, FS_SELECTION, AES_FS_NAME, frame + FS_INPUT_SELECTION_TEXT,
                frame + FS_INPUT_SELECTION_LENGTH);
    (void)aes_gsx_sclip(image, AES_GL_RFS);
    (void)aes_fm_dial(image, FMD_START, AES_GL_RCENTER, AES_GL_RFS);
    image[AES_SH_PATH_BUFFER] = STRING_NUL;
    aes_ob_draw(image, tree, OB_ROOT, FS_FIRST_DRAW_DEPTH);
}

/* A path that is not the one last read ($fe7f2c..$fe7fe6): the selected row and an OK or Cancel that brought it put
 * down; the path kept as the last read, its spec found there (fs_pspec may rewrite it: copied back to the field); the
 * working path's own spec made "*.*" — GEMDOS is searched for every name, the user's spec is wildcmp's — and the
 * directory read and shown (fs_newdir); no row selected, the list at its top. */
static void read_directory_of_the_path(uint8_t *image, uint32_t tree, uint32_t frame, int16_t object)
{
    uint32_t spec, every_name;

    aes_fs_sel(image, local_word(image, frame, FS_INPUT_SELECTED), FS_PUT_DOWN);
    if (object == FS_OK || object == FS_CANCEL)
        aes_ob_change(image, tree, object, FS_PUT_DOWN, OB_CHANGE_REDRAW);
    (void)aes_strcpy(image, AES_RS_STRING, AES_SH_PATH_BUFFER);
    spec = aes_fs_pspec(image, AES_SH_PATH_BUFFER,
                        AES_SH_PATH_BUFFER + (uint32_t)(int32_t)local_word(image, frame, FS_INPUT_PATH_LENGTH));
    (void)aes_lstcpy(image, frame_long(image, frame, FS_INPUT_PATH_TEXT), AES_SH_PATH_BUFFER);
    every_name = aes_fs_pspec(image, AES_RS_STRING, working_path_end(image, frame));
    (void)aes_strcpy(image, AES_FS_EVERY_NAME, every_name);
    aes_fs_newdir(image, frame_long(image, frame, FS_INPUT_TITLE_TEXT), AES_RS_STRING, spec, tree,
                  frame + FS_INPUT_COUNT);
    set_local_word(image, frame, FS_INPUT_SELECTED, 0);
}

/* fs_back CALLED, as the ROM calls it at both of the close box's sites ($fe815e, $fe818a). Inlined into fs_input its
 * scan keeps the image in the frame and reloads it on every byte — 94 and 114 cycles a byte at the two sites against
 * the ROM's 64 — and the second site's scan is the one that can run long: from below the path's buffer, with nothing
 * to stop it but a `:` or a `\` (849 bytes in the snapshot's machine). Out of line GCC keeps ONE copy for the two
 * sites, the image in a register and the path a constant it compares against: 78 cycles a byte. */
__attribute__((noinline))
static uint32_t fs_back_called(uint8_t *image, uint32_t path, uint32_t end)
{
    return aes_fs_back(image, path, end);
}

/* The close box ($fe8144): the working path cut back to the folder above — "\FOLDER\spec" made "\spec" by the spec's
 * `\` and all after it copied down over the `\` before the folder — unless the path is a drive's root ("X:\spec": the
 * byte before the last `\` a `:`). Whether the directory is to be read again: whenever the path has a `\` at all. */
static int16_t close_folder(uint8_t *image, uint32_t frame)
{
    uint32_t spec_separator = fs_back_called(image, AES_RS_STRING, working_path_end(image, frame));
    uint32_t before;

    if (bus_byte(image, spec_separator) != SH_DIRECTORY_SEPARATOR)
        return 0;
    before = spec_separator - 1;
    if (bus_byte(image, before) != SH_DRIVE_SEPARATOR) {
        before = fs_back_called(image, AES_RS_STRING, before);
        if (bus_byte(image, before) == SH_DIRECTORY_SEPARATOR)
            (void)aes_strcpy(image, spec_separator, before);
    }
    return 1;
}

/* A click in the slider's track ($fe8016): a page — the arrow the side of the elevator the mouse is on (below it:
 * down), the mouse as gsx_mxmy answered it when fm_do ended. */
static int16_t page_arrow(uint8_t *image, uint32_t tree, uint32_t frame)
{
    (void)aes_ob_offset(image, tree, FS_ELEVATOR, frame + FS_INPUT_ELEVATOR_X, frame + FS_INPUT_ELEVATOR_Y);
    return local_word(image, frame, FS_INPUT_MOUSE_Y) > local_word(image, frame, FS_INPUT_ELEVATOR_Y) ? FS_DOWN_ARROW
                                                                                                         : FS_UP_ARROW;
}

/* The elevator dragged ($fe804c): the screen taken round gr_slidebox; where it was left along its track (0..1000)
 * scaled to a top, and the rows from the list's top to there — signed: at or above the top is up. */
static int16_t rows_dragged(uint8_t *image, uint32_t tree, uint32_t frame, int16_t top)
{
    int16_t slid;

    (void)aes_fm_own(image, FM_OWN_TAKE);
    slid = aes_gr_slidebox(image, tree, FS_SLIDER, FS_ELEVATOR, FS_SLIDE_VERTICAL);
    (void)aes_fm_own(image, FM_OWN_GIVE_BACK);
    return (int16_t)(top - aes_mul_div(slid, (int16_t)(local_word(image, frame, FS_INPUT_COUNT) - FS_ROWS),
                                       FS_SLIDE_SCALE));
}

/* A row of the list clicked ($fe8098): the row selected in place of any other; its text read out (fs_sget). A FILE's
 * (its kind a space — an empty row's too) becomes the selection: answered 0, the caller redraws the field. A FOLDER's
 * name goes into the working path before its spec — the spec and its `\` set aside in the name scratch, the folder's
 * name unformatted over them, the spec put back after it — answered 1: a new directory. */
static int16_t row_clicked(uint8_t *image, uint32_t tree, uint32_t frame, int16_t object)
{
    int16_t row = (int16_t)(object - FS_ROW_OBJECT_BEFORE);
    uint32_t spec;

    if (local_word(image, frame, FS_INPUT_SELECTED) && row != local_word(image, frame, FS_INPUT_SELECTED))
        aes_fs_sel(image, local_word(image, frame, FS_INPUT_SELECTED), FS_PUT_DOWN);
    if (row != local_word(image, frame, FS_INPUT_SELECTED)) {
        set_local_word(image, frame, FS_INPUT_SELECTED, row);
        aes_fs_sel(image, local_word(image, frame, FS_INPUT_SELECTED), OB_STATE_SELECTED);
    }
    aes_fs_sget(image, tree, object, AES_FS_TEXT);
    if (image[AES_FS_TEXT] == FS_FILE_MARK)
        return 0;
    spec = aes_fs_pspec(image, AES_RS_STRING, working_path_end(image, frame));
    (void)aes_strcpy(image, spec - 1, AES_FS_NAME);
    aes_unfmt_str(image, AES_FS_TEXT_BODY, spec);
    (void)aes_strcat(image, AES_FS_NAME, spec);
    return 1;
}

/* The selector put away ($fe824e..$fe82d2): the path field copied to the caller's path, the selection unformatted to
 * the caller's; the screen under the box redrawn; the button answered — 1 OK, 0 Cancel or neither, both put down
 * (inf_what) — and the three blocks freed, the DTA first. */
static void put_selector_away(uint8_t *image, uint32_t tree, uint32_t frame, uint32_t path, uint32_t selection,
                              uint32_t button_at)
{
    int16_t button;

    (void)aes_lstcpy(image, path, frame_long(image, frame, FS_INPUT_PATH_TEXT));
    (void)aes_lstcpy(image, AES_FS_TEXT, frame_long(image, frame, FS_INPUT_SELECTION_TEXT));
    aes_unfmt_str(image, AES_FS_TEXT, AES_FS_NAME);
    (void)aes_lstcpy(image, selection, AES_FS_NAME);
    (void)aes_fm_dial(image, FMD_FINISH, AES_GL_RCENTER, AES_GL_RFS);
    button = aes_inf_what(image, tree, FS_OK, FS_CANCEL);
    set_bus_word(image, button_at, (uint16_t)button);
    if (button == FS_NO_BUTTON)
        set_bus_word(image, button_at, FS_CANCELLED);
    (void)aes_dos_free(image, AES_FS_INPUT_DTA_FREE_RETURN, be32(image + AES_AD_FSDTA));
    (void)aes_dos_free(image, AES_FS_INPUT_INDEX_FREE_RETURN, be32(image + AES_AD_FSINDEX));
    (void)aes_dos_free(image, AES_FS_INPUT_NAMES_FREE_RETURN, be32(image + AES_AD_FSNAMES));
}

/* THE ROM NEVER RETURNS FROM AN EMPTY WORKING PATH. A directory still to be read skips fm_do, and only reading one
 * clears that; but a path equal to the one last read is not read — and the path last read is forgotten (made empty)
 * whenever a directory is to be read. So with the working path EMPTY too, every pass puts the same empty path back
 * in its field and redraws the selection, for ever, with no wait in it. The target build does the same. Off target a
 * run that cannot end is refused by name on the pass it is first certain — THE CONDITION TESTED: a directory to read
 * (-44(a6) set, so the path last read is ""), and streq(path last read, working path) true, so the working path is
 * "" as well. Two roads lead there:
 *   - the caller's path is empty: the first pass;
 *   - the close box over a path whose only `\` is its first byte ("\*.*"): fs_back scans DOWN from below the path's
 *     buffer and the path's "\spec" is copied to where it stops — into the text buffers that lie under it
 *     (AES_FMTSTR's 81 bytes end where the path begins). A formatted text drawn before, long enough to have left a
 *     `:` or a `\` just under the path, puts the copy's NUL on the path's first byte. */
static inline void refuse_a_pass_that_never_ends(int16_t new_directory)
{
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (new_directory)
        recreate_not_reconstructed("fs_input with a directory to read and its working path empty: the ROM never "
                                   "returns — the path equals the one last read (both empty), so no directory is "
                                   "read, fm_do is never called and the selection field is redrawn for ever");
#else
    (void)new_directory;
#endif
}

/* fs_input's own state across its passes: the selector's tree and where its frame stands; three of the four flags the
 * ROM keeps in that frame (-46, -44, -42(a6): the fourth, -40(a6), is stored and read inside one pass — the double
 * click's, `act_on_the_object`'s local) and the list's top (-4(a6)), by value; and a pass's own two registers — the
 * object fm_do ended on (D7: its double-click bit until the switch, then the arrow a scroll goes by) and the rows to
 * scroll by (D6). */
struct selector_run {
    uint32_t tree, frame;
    int16_t redraw_selection, new_directory, go_on, top;
    int16_t object, rows;
};

/* A pass's head, past fm_do ($fe7eec..$fe7fe6): the mouse asked; the path field copied to the working path, its
 * length kept; and when that is not the path last read, its directory read and shown — the list then at its top, and
 * no directory left to read. */
static void take_the_path(uint8_t *image, struct selector_run *run)
{
    aes_gsx_mxmy(image, run->frame + FS_INPUT_MOUSE_X, run->frame + FS_INPUT_MOUSE_Y);
    set_local_word(image, run->frame, FS_INPUT_PATH_LENGTH,
                   aes_lstcpy(image, AES_RS_STRING, frame_long(image, run->frame, FS_INPUT_PATH_TEXT)));
    if (!aes_streq(image, AES_SH_PATH_BUFFER, AES_RS_STRING)) {
        read_directory_of_the_path(image, run->tree, run->frame, run->object);
        run->top = 0;
        run->new_directory = 0;
    } else {
        refuse_a_pass_that_never_ends(run->new_directory);
    }
}

/* The elevator's arm ($fe804c..$fe8094): the rows it was dragged by, and the arrow they scroll by — up, or for a
 * negative count down, by that many. */
static void drag_the_elevator(uint8_t *image, struct selector_run *run)
{
    run->rows = rows_dragged(image, run->tree, run->frame, run->top);
    run->object = FS_UP_ARROW;
    if (run->rows < 0) {
        run->object = FS_DOWN_ARROW;
        run->rows = (int16_t)-run->rows;
    }
}

/* A row's arm ($fe8098..$fe8140): a folder's — a new directory; a file's — the selection field to redraw, and
 * double-clicked, the selector done. */
static void click_the_row(uint8_t *image, struct selector_run *run, int16_t double_clicked)
{
    if (row_clicked(image, run->tree, run->frame, run->object)) {
        run->new_directory = 1;
    } else {
        run->redraw_selection = 1;
        if (double_clicked)
            run->go_on = 0;
    }
}

/* The switch ($fefab0, on the object less its double-click bit): the close box, the title, an arrow, the slider's
 * track or its elevator, a row, OK or Cancel — what each leaves the pass's tail to do. */
static void act_on_the_object(uint8_t *image, struct selector_run *run)
{
    int16_t double_clicked = ((uint16_t)run->object & FM_DOUBLE_CLICKED) != 0;

    run->object = (int16_t)((uint16_t)run->object & ~FM_DOUBLE_CLICKED);
    switch (run->object) {
    case FS_CLOSER:
        if (close_folder(image, run->frame))
            run->new_directory = 1;
        break;
    case FS_TITLE:
        run->new_directory = 1;
        break;
    case FS_UP_ARROW:
    case FS_DOWN_ARROW:
        run->rows = FS_ARROW_ROWS;
        break;
    case FS_SLIDER:
        run->object = page_arrow(image, run->tree, run->frame);
        run->rows = FS_ROWS;
        break;
    case FS_ELEVATOR:
        drag_the_elevator(image, run);
        break;
    case FS_OK:
    case FS_CANCEL:
        run->go_on = 0;
        break;
    default:        /* a row; else the list's and the slider's own boxes (FS_FILE_BOX, FS_SLIDER_BOX), or no object */
        if (run->object >= FS_FIRST_NAME && run->object <= FS_LAST_NAME)
            click_the_row(image, run, double_clicked);
        break;
    }
}

/* A pass's tail ($fe81be..$fe824a): a directory to read — the working path back in its field, the path last read and
 * the selection forgotten; the selection field redrawn (the selector done: OK shown SELECTED); the list scrolled. */
static void finish_the_pass(uint8_t *image, struct selector_run *run)
{
    if (run->new_directory) {
        (void)aes_lstcpy(image, frame_long(image, run->frame, FS_INPUT_PATH_TEXT), AES_RS_STRING);
        image[AES_SH_PATH_BUFFER] = STRING_NUL;
        image[AES_FS_TEXT_BODY] = STRING_NUL;
        run->redraw_selection = 1;
    }
    if (run->redraw_selection) {
        (void)aes_lstcpy(image, frame_long(image, run->frame, FS_INPUT_SELECTION_TEXT), AES_FS_TEXT_BODY);
        aes_ob_draw(image, run->tree, FS_SELECTION, FS_DRAW_DEPTH);
        if (!run->go_on)
            aes_ob_change(image, run->tree, FS_OK, OB_STATE_SELECTED, OB_CHANGE_REDRAW);
        run->redraw_selection = 0;
    }
    if (run->rows)
        run->top = aes_fs_nscroll(image, run->tree, run->frame + FS_INPUT_SELECTED, run->top,
                                  local_word(image, run->frame, FS_INPUT_COUNT), run->object, run->rows);
}

/* $fe7d90 — fs_input: the file selector run over `path` (a directory and a spec) and `selection` (a name) until OK or
 * Cancel. Each pass: the form run (fm_do, from the selection field) unless a directory is still to be read; the path
 * field taken, its directory read and shown when it is not the path last read; then the object fm_do ended on, and
 * what it leaves to do. At the end both strings handed back, the button stored through `button_at`. Answers 1 — or
 * 0, nothing shown, when GEMDOS has no memory for its three blocks. */
int16_t aes_fs_input(uint8_t *image, uint32_t path, uint32_t selection, uint32_t button_at)
{
    uint16_t frame_local[FS_INPUT_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_FS_INPUT_FRAME_BYTES, "fs_input's frame and its host slot");
    struct selector_run run = {.new_directory = 1, .go_on = 1};

    if (!blocks_allocated(image))
        return FS_INPUT_NO_MEMORY;
    run.frame = host_slot_claim(AES_FS_INPUT_FRAME, frame_local);
    run.tree = be32(image + AES_AD_FSTREE);
    show_selector(image, run.tree, run.frame, path, selection);
    set_local_word(image, run.frame, FS_INPUT_SELECTED, 0);
    while (run.go_on) {
        run.object = run.new_directory ? 0 : aes_fm_do(image, run.tree, FS_SELECTION);
        run.rows = 0;
        take_the_path(image, &run);
        act_on_the_object(image, &run);
        finish_the_pass(image, &run);
    }
    put_selector_away(image, run.tree, run.frame, path, selection, button_at);
    host_slot_release(AES_FS_INPUT_FRAME);
    return FS_INPUT_DONE;
}
