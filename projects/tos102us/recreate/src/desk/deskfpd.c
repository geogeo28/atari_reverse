/* deskfpd.c — THE DESK'S PATH AND FILE NODES (`desk/deskfpd.h`): `$fdf6d0..$fdfc3b`. Alcyon C in the ROM, ported over
 * its own order.
 *
 * THREE ROM BEHAVIOURS NO C CAN HAVE, each a write to the routine's OWN ARGUMENT WORDS in its caller's frame: fpd_parse
 * moves its path, name and extension pointers on in place (`addq.l #1,16(a6)` ...), fpd_bldspec its spec pointer
 * (`addq.l #1,18(a6)`), and pn_sort counts the list into its count word (`addq.w #1,8(a6)`). A C core's arguments are its own; no ROM caller reads those words back
 * (`test/test_desk_fpd.py`).
 */
#include <stdint.h>

#include "addrs.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskmem.h"
#include "aes/gemdosif.h"
#include "aes/strings.h"
#include "desk/deskfpd.h"
#include "desk/deskleaf.h"
#include "desk/deskutil.h"
#include "desk/deskview.h"

/* $fdf6d0 — fn_init: the pool's file nodes linked in order, the free list their head; the last node's link cleared. */
void aes_fn_init(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t pool = be32(image + AES_DESK_BLOCK_16000);

    for (int16_t node = FILE_NODES - 2; node >= 0; node--)
        set_bus_long(image, pool + node * FNODE_BYTES + FNODE_NEXT, pool + (node + 1) * FNODE_BYTES);
    set_bus_long(image, desk + DESK_FILES_FREE, pool);
    set_bus_long(image, pool + (FILE_NODES - 1) * FNODE_BYTES + FNODE_NEXT, FNODE_NONE);
}

/* $fdf710 — pn_init: the path nodes linked in order — THE LAST ONE TOO, to where a sixth node would lie (g_pavail's
 * own place) — the free list their head, none open, and the last node's link cleared again. A ROM behaviour,
 * reproduced: its loop starts one node late, and the clear behind it puts that right. */
void aes_pn_init(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t pool = desk + DESK_PATH_POOL;

    for (int16_t node = PATH_NODES - 1; node >= 0; node--)
        set_bus_long(image, pool + node * PNODE_BYTES + PNODE_NEXT, pool + (node + 1) * PNODE_BYTES);
    set_bus_long(image, desk + DESK_PATHS_FREE, pool);
    set_bus_long(image, desk + DESK_PATHS_OPEN, PNODE_NONE);
    set_bus_long(image, pool + (PATH_NODES - 1) * PNODE_BYTES + PNODE_NEXT, PNODE_NONE);
}

/* $fdf756 — fpd_start: the DTA's pointer and a buffer's set to their places in the globals; both pools made. */
void aes_fpd_start(uint8_t *image)
{
    uint32_t desk = desk_globals(image);

    set_bus_long(image, desk + DESK_DTA_POINTER, desk + DESK_DTA);
    set_bus_long(image, desk + DESK_PATH_BUFFER_POINTER, desk + DESK_PATH_BUFFER);
    aes_fn_init(image);
    aes_pn_init(image);
}

/* The NUL-ended text at `from` copied to `to`, the NUL not; where the copy ends. */
static uint32_t copied_up_to_the_nul(uint8_t *image, uint32_t to, uint32_t from)
{
    while (bus_byte(image, from))
        set_bus_byte(image, to++, bus_byte(image, from++));
    return to;
}

/* $fdf77a — fpd_bldspec: "D:\path\name.ext" built at `spec` — the separator only between a path and a name, the
 * mark only before an extension of a name — where the path leaves the spec room for the rest. (The ROM's also
 * writes its own argument word in its caller's frame, `addq.l #1,18(a6)` at $fdf7e2 — the spec pointer moved on in
 * place; pn_open, its one caller, discards it. No C can, and none reads it back.) */
int16_t aes_fpd_bldspec(uint8_t *image, int16_t drive, uint32_t path, uint32_t name, uint32_t ext, uint32_t spec)
{
    if ((int16_t)(aes_strlen(image, path) + SPEC_ROOM_BESIDE_THE_PATH) >= SPEC_BYTES)
        return FPD_BLDSPEC_TOO_LONG;
    set_bus_byte(image, spec++, (uint8_t)drive);
    set_bus_byte(image, spec++, SPEC_DRIVE_MARK);
    set_bus_byte(image, spec++, SPEC_SEPARATOR);
    if (bus_byte(image, path)) {
        spec = copied_up_to_the_nul(image, spec, path);
        if (bus_byte(image, name))
            set_bus_byte(image, spec++, SPEC_SEPARATOR);
    }
    if (bus_byte(image, name)) {
        spec = copied_up_to_the_nul(image, spec, name);
        if (bus_byte(image, ext)) {
            set_bus_byte(image, spec++, SPEC_EXT_MARK);
            spec = copied_up_to_the_nul(image, spec, ext);
        }
    }
    set_bus_byte(image, spec, 0);
    return FPD_BLDSPEC_DONE;
}

/* The bytes `[from, end)` copied to `to`, a NUL behind them. */
static void copied_with_a_nul(uint8_t *image, uint32_t to, uint32_t from, uint32_t end)
{
    while (from != end)
        set_bus_byte(image, to++, bus_byte(image, from++));
    set_bus_byte(image, to, 0);
}

/* $fdf7f4 — fpd_parse: a spec taken apart — its drive letter (the byte before the first ':', as a SIGNED word; or the
 * current drive's, from dos_gdrv), its path (up to the last separator), its name and its extension (after the last
 * '.', which may lie in the path: the ROM's own scan). */
void aes_fpd_parse(uint8_t *image, uint32_t spec, uint32_t drive_out, uint32_t path_out, uint32_t name_out,
                   uint32_t ext_out)
{
    uint32_t at = spec, first, last_separator, last_mark = 0;

    while (bus_byte(image, at) && bus_byte(image, at) != SPEC_DRIVE_MARK)
        at++;
    if (bus_byte(image, at) == SPEC_DRIVE_MARK) {
        set_bus_word(image, drive_out, (uint16_t)(int16_t)(int8_t)bus_byte(image, at - 1));
        at++;
        if (bus_byte(image, at) == SPEC_SEPARATOR)
            at++;
    } else {
        set_bus_word(image, drive_out, (uint16_t)(aes_dos_gdrv(image, AES_FPD_PARSE_GDRV_RETURN) + DRIVE_LETTER_FIRST));
        at = spec;
    }
    first = last_separator = at;
    for (; bus_byte(image, at); at++) {
        if (bus_byte(image, at) == SPEC_SEPARATOR)
            last_separator = at;
        if (bus_byte(image, at) == SPEC_EXT_MARK)
            last_mark = at;
    }
    if (!last_mark)
        last_mark = at;
    copied_with_a_nul(image, path_out, first, last_separator);
    if (bus_byte(image, last_separator) == SPEC_SEPARATOR)
        last_separator++;
    copied_with_a_nul(image, name_out, last_separator, last_mark);
    if (bus_byte(image, last_mark))
        copied_with_a_nul(image, ext_out, last_mark + 1, at);
    else
        set_bus_byte(image, ext_out, 0);
}

/* $fdf8c6 — fpd_ofind: the file of the list `files` shown by object `obj`; FNODE_NONE where none is. */
uint32_t aes_fpd_ofind(uint8_t *image, uint32_t files, int16_t obj)
{
    for (; files != FNODE_NONE; files = bus_long(image, files + FNODE_NEXT))
        if ((int16_t)bus_word(image, files + FNODE_OBID) == obj)
            return files;
    return FNODE_NONE;
}

/* $fdf8ec — fpd_elist: the node of the list whose link is `stop` (its last, for FNODE_NONE). */
uint32_t aes_fpd_elist(uint8_t *image, uint32_t files, uint32_t stop)
{
    while (bus_long(image, files + FNODE_NEXT) != stop)
        files = bus_long(image, files + FNODE_NEXT);
    return files;
}

/* $fdf908 — fn_free: the file node pushed on the free list. */
void aes_fn_free(uint8_t *image, uint32_t file)
{
    set_bus_long(image, file + FNODE_NEXT, bus_long(image, desk_globals(image) + DESK_FILES_FREE));
    set_bus_long(image, desk_globals(image) + DESK_FILES_FREE, file);
}

/* $fdf926 — fl_free: a whole list put at the free list's head, its last node linked to the old head. */
void aes_fl_free(uint8_t *image, uint32_t files)
{
    if (files == FNODE_NONE)
        return;
    set_bus_long(image, aes_fpd_elist(image, files, FNODE_NONE) + FNODE_NEXT,
                 bus_long(image, desk_globals(image) + DESK_FILES_FREE));
    set_bus_long(image, desk_globals(image) + DESK_FILES_FREE, files);
}

/* $fdf952 — fn_alloc: the free list's first file node, taken off it; FNODE_NONE where none is free. */
uint32_t aes_fn_alloc(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t file = bus_long(image, desk + DESK_FILES_FREE);

    if (file == FNODE_NONE)
        return FNODE_NONE;
    set_bus_long(image, desk + DESK_FILES_FREE, bus_long(image, file + FNODE_NEXT));
    return file;
}

/* $fdf972 — pn_alloc: the free list's first path node, taken off it and pushed on the open list, its flags and its
 * file list cleared; PNODE_NONE where none is free. */
uint32_t aes_pn_alloc(uint8_t *image)
{
    uint32_t desk = desk_globals(image);
    uint32_t path = bus_long(image, desk + DESK_PATHS_FREE);

    if (path == PNODE_NONE)
        return PNODE_NONE;
    set_bus_long(image, desk + DESK_PATHS_FREE, bus_long(image, path + PNODE_NEXT));
    set_bus_long(image, path + PNODE_NEXT, bus_long(image, desk + DESK_PATHS_OPEN));
    set_bus_long(image, desk + DESK_PATHS_OPEN, path);
    set_bus_word(image, path + PNODE_FLAGS, 0);
    set_bus_long(image, path + PNODE_FLIST, FNODE_NONE);
    return path;
}

/* $fdf9aa — pn_free: the path's files freed; the path unlinked from the open list — found by the link that names it,
 * from the list's head on (a path on no open list is searched for past its end: the ROM's walk, reproduced) — and
 * pushed on the free list. */
void aes_pn_free(uint8_t *image, uint32_t path)
{
    uint32_t desk = desk_globals(image);
    uint32_t before = desk + DESK_PATHS_OPEN;

    aes_fl_free(image, bus_long(image, path + PNODE_FLIST));
    while (bus_long(image, before + PNODE_NEXT) != path)
        before = bus_long(image, before + PNODE_NEXT);
    set_bus_long(image, before + PNODE_NEXT, bus_long(image, path + PNODE_NEXT));
    set_bus_long(image, path + PNODE_NEXT, bus_long(image, desk + DESK_PATHS_FREE));
    set_bus_long(image, desk + DESK_PATHS_FREE, path);
}

/* $fdf9da — pn_open: a path node with the spec built in it and the attributes kept; PNODE_NONE where none is free —
 * or where the spec does not fit, THE NODE LEFT OPEN (taken and never given back: the ROM's, reproduced). */
uint32_t aes_pn_open(uint8_t *image, int16_t drive, uint32_t path, uint32_t name, uint32_t ext, int16_t attributes)
{
    uint32_t node = aes_pn_alloc(image);

    if (node == PNODE_NONE || !aes_fpd_bldspec(image, drive, path, name, ext, node + PNODE_SPEC))
        return PNODE_NONE;
    set_bus_word(image, node + PNODE_ATTR, (uint16_t)attributes);
    return node;
}

/* $fdfa2c — pn_fcomp: the order of two files by `key` — <0 the first first. By size, the larger first (SIGNED
 * longs), then by name; by type, the extensions' order (from each name's first '.'), then by name; by date, the
 * date words' difference, then the times' without their two-second field. ANY OTHER KEY IS ANSWERED ITSELF (the
 * switch's word left in D0: the ROM's, reproduced). */
int16_t aes_pn_fcomp(uint8_t *image, uint32_t first, uint32_t second, int16_t key)
{
    uint32_t first_name = first + FNODE_NAME, second_name = second + FNODE_NAME;
    int16_t order;

    switch (key) {
    case SORT_BY_SIZE:
        if ((int32_t)bus_long(image, second + FNODE_SIZE) > (int32_t)bus_long(image, first + FNODE_SIZE))
            return PN_FCOMP_FIRST;
        if ((int32_t)bus_long(image, second + FNODE_SIZE) < (int32_t)bus_long(image, first + FNODE_SIZE))
            return PN_FCOMP_SECOND;
        return aes_strchk(image, first_name, second_name);
    case SORT_BY_TYPE:
        order = aes_strchk(image, aes_scasb(image, first_name, SPEC_EXT_MARK), aes_scasb(image, second_name, SPEC_EXT_MARK));
        if (order)
            return order;
        return aes_strchk(image, first_name, second_name);
    case SORT_BY_NAME:
        return aes_strchk(image, first_name, second_name);
    case SORT_BY_DATE:
        order = (int16_t)(bus_word(image, second + FNODE_DATE) - bus_word(image, first + FNODE_DATE));
        if (order)
            return order;
        return (int16_t)((bus_word(image, second + FNODE_TIME) >> FNODE_TIME_SECONDS_BITS)
                         - (bus_word(image, first + FNODE_TIME) >> FNODE_TIME_SECONDS_BITS));
    default:
        return key;
    }
}

/* $fdfaee — pn_comp: a folder before a file; two of a kind by the windows' sort key (pn_fcomp). */
int16_t aes_pn_comp(uint8_t *image, uint32_t first, uint32_t second)
{
    uint8_t first_attr = bus_byte(image, first + FNODE_ATTR);

    if ((first_attr ^ bus_byte(image, second + FNODE_ATTR)) & FNODE_ATTR_SUBDIR)
        return (first_attr & FNODE_ATTR_SUBDIR) ? PN_FCOMP_SECOND : PN_FCOMP_FIRST;
    return aes_pn_fcomp(image, first, second, (int16_t)bus_word(image, desk_globals(image) + DESK_G_ISORT));
}

/* The index's `nth` file. */
static inline uint32_t indexed(uint8_t *image, uint32_t index, int32_t nth)
{
    return bus_long(image, index + nth * M68K_LONG_BYTES);
}

/* $fdfb38 — pn_sort: the files sorted by pn_comp — counted into the index from the list first where `count` is -1 —
 * by K&R's shell sort, the gap halved as a SIGNED word; then linked in the index's order. The new head; FNODE_NONE
 * where the count is not positive. */
uint32_t aes_pn_sort(uint8_t *image, int16_t count, uint32_t files)
{
    uint32_t index = desk_globals(image) + DESK_FILE_INDEX;
    uint32_t head = FNODE_NONE, last = FNODE_NONE;

    if (count == PN_SORT_COUNT_THEM)
        for (count = 0; files != FNODE_NONE; files = bus_long(image, files + FNODE_NEXT))
            set_bus_long(image, index + count++ * M68K_LONG_BYTES, files);
    for (int16_t gap = count / 2; gap > 0; gap /= 2)
        for (int16_t place = gap; place < count; place++)
            for (int16_t before = place - gap; before >= 0; before -= gap) {
                uint32_t earlier = indexed(image, index, before);

                if (aes_pn_comp(image, earlier, indexed(image, index, before + gap)) <= 0)
                    break;
                set_bus_long(image, index + before * M68K_LONG_BYTES, indexed(image, index, before + gap));
                set_bus_long(image, index + (before + gap) * M68K_LONG_BYTES, earlier);
            }
    for (int16_t place = 0; place < count; place++) {
        uint32_t file = indexed(image, index, place);

        if (place == 0)
            head = file;
        else
            set_bus_long(image, last + FNODE_NEXT, file);
        last = file;
    }
    if (count > 0)
        set_bus_long(image, last + FNODE_NEXT, FNODE_NONE);
    return head;
}

/* ---- band 6 wave 2, group G2 (unit G) ------------------------------------------------------------------------------ */
/* $fdfa20 — pn_close: the path node freed (pn_free). */
void aes_pn_close(uint8_t *image, uint32_t path)
{
    aes_pn_free(image, path);
}

/* The entry the DTA holds is listed: any name but "." and ".." (a name that begins with '.' and goes on is). */
static int is_listed(uint8_t *image, uint32_t dta)
{
    return bus_byte(image, dta + DTA_NAME) != SPEC_EXT_MARK
        || (bus_byte(image, dta + DTA_NAME + 1) != SPEC_EXT_MARK && bus_byte(image, dta + DTA_NAME + 1));
}

/* $fdfc3c — pn_active: the path's files read anew. The old list freed; a search of the spec — the cartridge's where
 * its drive is 'c' — each entry found taken into a file node (one taken AHEAD of the entry it is for: a node short
 * ends the search, AES_DOS_AX E_NOFNODES), counted, its bytes added, indexed at ml_pfndx and linked on; the node
 * taken last and left over freed; the list sorted. Its answer: AES_DOS_AX — the search's last verdict. */
int16_t aes_pn_active(uint8_t *image, uint32_t path)
{
    int16_t on_the_cartridge = bus_byte(image, path + PNODE_SPEC) == CARTRIDGE_DRIVE;
    int16_t attributes = (int16_t)bus_word(image, path + PNODE_ATTR);
    uint32_t file = FNODE_NONE, link = path + PNODE_FLIST;
    int16_t found;

    set_bus_word(image, path + PATH_FILE_COUNT, 0);
    set_bus_long(image, path + PATH_FILE_BYTES, 0);
    aes_fl_free(image, bus_long(image, path + PNODE_FLIST));
    if (on_the_cartridge) {
        found = aes_cart_sfirst(image, bus_long(image, desk_globals(image) + DESK_DTA_POINTER), attributes);
    } else {
        (void)aes_dos_sdta(image, AES_PN_ACTIVE_SDTA_RETURN, bus_long(image, desk_globals(image) + DESK_DTA_POINTER));
        found = aes_dos_sfirst(image, path + PNODE_SPEC, attributes);
    }
    while (found) {
        if (file == FNODE_NONE) {
            file = aes_fn_alloc(image);
            if (file == FNODE_NONE) {
                found = 0;
                wr16(image + AES_DOS_AX, DOS_AX_NO_FILE_NODES);
            }
            continue;
        }
        if (is_listed(image, desk_globals(image) + DESK_DTA)) {
            int16_t count = (int16_t)bus_word(image, path + PATH_FILE_COUNT);

            aes_movs(image, DTA_COPIED_BYTES, desk_globals(image) + DESK_DTA + DTA_COPIED_FROM, file + FNODE_FROM_THE_DTA);
            set_bus_long(image, path + PATH_FILE_BYTES, bus_long(image, path + PATH_FILE_BYTES) + bus_long(image, file + FNODE_SIZE));
            set_bus_long(image, desk_globals(image) + DESK_FILE_INDEX + (uint32_t)(count * M68K_LONG_BYTES), file);
            set_bus_long(image, link, file);
            set_bus_word(image, path + PATH_FILE_COUNT, (uint16_t)(count + 1));
            link = file + FNODE_NEXT;
            file = FNODE_NONE;
        }
        found = on_the_cartridge ? aes_cart_snext(image) : aes_dos_snext(image);
    }
    set_bus_long(image, link, FNODE_NONE);
    if (file != FNODE_NONE)
        aes_fn_free(image, file);
    set_bus_long(image, path + PNODE_FLIST,
                 aes_pn_sort(image, (int16_t)bus_word(image, path + PATH_FILE_COUNT), bus_long(image, path + PNODE_FLIST)));
    return (int16_t)be16(image + AES_DOS_AX);
}
/* ---- end of group G2's wave-2 ---- */
