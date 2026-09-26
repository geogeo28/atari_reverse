/* fs_dir.c — the GEMDOS file system's DIRECTORY layer.
 *
 *   $fc663c  dir_search   one directory, from a position, for the first entry a pattern matches
 *   $fc696c  find_dir     a path walked down the DND tree to the directory of its last component
 *   $fc6df4  Fsnext ($4f) the next match of the search a DTA holds
 *
 * THE TREE IS BUILT AS A SIDE EFFECT OF SEARCHING. There is no "read directory" routine: a DND exists
 * for a subdirectory only once some search has READ PAST its entry. `$fc663c` makes one for every
 * subdirectory entry it passes beyond the directory's DND_SCANNED mark (and moves the mark), and
 * stops making them once the directory's OFD says a search has reached its end (OFD_SCANNED). So
 * `$fc696c` looks a component up on the DND's child list FIRST and searches the disk only when the
 * list runs out — resuming at the mark, where the DNDs it has not got yet begin.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_dir.h"
#include "gemdos/fs_drive.h"
#include "gemdos/fs_io.h"
#include "gemdos/fs_records.h"
#include "machine.h"

/* The pattern and the walk's component FCB are frame locals whose ADDRESS these routines hand on, so
 * off target each is a host slot (`include/gemdos/gemdos.h`) of the same twelve bytes. */
_Static_assert(GEMDOS_HOST_SLOT_SEARCH_PATTERN_BYTES == GEMDOS_SEARCH_PATTERN_BYTES
               && GEMDOS_HOST_SLOT_WALK_NAME_BYTES == GEMDOS_SEARCH_PATTERN_BYTES,
               "a host slot narrower or wider than the frame local it stands in for");

/* Is `entry` a subdirectory this search owes a DND? Only one past the directory's mark — SIGNED, and
 * an entry exactly at the mark is not — while no search has reached the directory's end, and never
 * `.`/`..` (a name starting with a dot, $fc66f0 `cmpi.b #46`) or a deleted one ($fc66de..$fc6702). */
static int is_unmade_subdirectory(const uint8_t *image, uint32_t dnd, uint32_t ofd, uint32_t entry)
{
    return (int32_t)be32(image + ofd + OFD_POS) > (int32_t)be32(image + dnd + DND_SCANNED)
           && (be16(image + ofd + OFD_FLAGS) & OFD_SCANNED) == 0
           && image[entry + DIRENT_NAME] != NAME_DOT
           && (image[entry + DIRENT_ATTR] & GEMDOS_ATTR_SUBDIR) != 0
           && image[entry + DIRENT_NAME] != DIRENT_DELETED;
}

/* The child on `dnd`'s list whose name IS the pattern (plain FCB equality, `$fc5672`), and whether
 * there was one — its compare word, 0 for "none" ($fc66aa..$fc66d8). */
static uint32_t known_child(const uint8_t *image, uint32_t dnd, uint32_t pattern, uint16_t *is_known)
{
    uint32_t child;

    *is_known = 0;
    for (child = be32(image + dnd + DND_CHILD); child != 0; child = be32(image + child + DND_SIBLING)) {
        *is_known = (uint16_t)gemdos_fcb_name_eq(0, image, pattern, child);
        if (*is_known != 0)
            break;
    }
    return child;
}

/* $fc663c — the first entry of `dnd`'s directory, from `*position`, that the TEXT `name` matches
 * under `attr` (`$fc5c9a`, the pattern's twelfth byte being `attr`'s low byte).
 *
 * THE DIRECTORY IS READ THROUGH ITS OFD, made on first use and kept on the DND. Every subdirectory
 * entry passed on the way — the matching one included — gets a DND unless `is_unmade_subdirectory`
 * says it has one, or its name is the pattern AND the child list already held that name (a DND made
 * some other way, `Dcreate`'s). THE ANSWER IS THE LAST DND MADE, not necessarily the matched entry's,
 * when the search runs from DND_SCANNED: `child` is the list walk's result and then each DND made,
 * and a matching FILE makes none — so `$fc696c` asked for a component that is a file gets a sibling
 * directory's DND, or 0, and its own name test rejects it.
 *
 * AT THE END WITH NOTHING FOUND the OFD is marked OFD_SCANNED — except where the end was a 0 entry and
 * the TEXT name starts with `$e5`: that is a search for a free slot, and the end-of-directory entry
 * is one. From a real position the position is left after the last entry read; from DND_SCANNED the
 * mark is raised to it instead, and a found entry is un-read so the next search reads it again.
 */
static uint32_t search(uint8_t *image, uint32_t dnd, uint32_t name, uint16_t attr, int32_t *position,
                       uint32_t pattern)
{
    uint32_t ofd = be32(image + dnd + DND_OFD);
    int32_t start;
    uint16_t is_known;
    uint16_t found = 0;
    uint32_t child;
    uint32_t entry;

    gemdos_build_fcb_name(image, name, pattern);
    image[pattern + DIRENT_ATTR] = (uint8_t)attr;
    if (ofd == 0) {
        ofd = gemdos_ofd_new(image, dnd);
        wr32(image + dnd + DND_OFD, ofd);
        if (ofd == 0)
            return 0;
    }
    start = *position;
    if (start == GEMDOS_SEARCH_FROM_SCANNED)
        start = (int32_t)be32(image + dnd + DND_SCANNED);
    gemdos_ofd_seek(image, ofd, (uint32_t)start);

    child = known_child(image, dnd, pattern, &is_known);
    for (entry = gemdos_next_entry(image, ofd); entry != 0 && image[entry] != 0; entry = gemdos_next_entry(image, ofd)) {
        if (is_unmade_subdirectory(image, dnd, ofd, entry)
            && ((uint16_t)gemdos_fcb_name_eq(0, image, pattern, entry) == 0 || is_known == 0)) {
            child = gemdos_dnd_new(image, dnd, entry);
            if (child == 0)
                return 0;
        }
        found = (uint16_t)gemdos_name_match(0, image, pattern, entry);
        if (found != 0)
            break;
    }

    if (*position == GEMDOS_SEARCH_FROM_SCANNED) {
        if ((int32_t)be32(image + ofd + OFD_POS) > (int32_t)be32(image + dnd + DND_SCANNED))
            wr32(image + dnd + DND_SCANNED, be32(image + ofd + OFD_POS));
    } else {
        *position = (int32_t)be32(image + ofd + OFD_POS);
    }

    if (found == 0) {
        if (entry != 0 && image[name] == DIRENT_DELETED)
            return entry;
        wr16(image + ofd + OFD_FLAGS, (uint16_t)(be16(image + ofd + OFD_FLAGS) | OFD_SCANNED));
        return 0;
    }
    if (*position == GEMDOS_SEARCH_FROM_SCANNED) {
        gemdos_ofd_seek(image, ofd, be32(image + ofd + OFD_POS) - ENTRY_BEHIND_POSITION);
        return child;
    }
    return entry;
}

/* ...with its pattern a frame local, whose address `search` hands to three routines. */
uint32_t gemdos_dir_search(uint8_t *image, uint32_t dnd, uint32_t name, uint16_t attr, int32_t *position)
{
    uint8_t pattern_local[GEMDOS_SEARCH_PATTERN_BYTES];
    uint32_t found = search(image, dnd, name, attr, position, gemdos_host_slot_claim(SEARCH_PATTERN, pattern_local));

    gemdos_host_slot_release(SEARCH_PATTERN);
    return found;
}

/* ---- $fc696c, the walk ------------------------------------------------------------------------- */

/* `$fc68dc` over the path cursor, which it reads and writes through an ADDRESS — the frame local. */
static uint32_t path_start(uint8_t *image, uint32_t *cursor)
{
    uint32_t cursor_at = gemdos_host_slot_claim(WALK_CURSOR, cursor);
    uint32_t dir;

    gemdos_host_slot_store_long(image, cursor_at, cursor);
    dir = gemdos_path_start(image, cursor_at);
    gemdos_host_slot_load_long(image, cursor_at, cursor);
    gemdos_host_slot_release(WALK_CURSOR);
    return dir;
}

/* A search of `dir` from its mark for a DIRECTORY named by the component at `cursor` ($fc69ca,
 * $fc6a10): what `$fc663c` answers from DND_SCANNED is a DND. */
static uint32_t search_for_directory(uint8_t *image, uint32_t dir, uint32_t cursor)
{
    int32_t from_scanned = GEMDOS_SEARCH_FROM_SCANNED;

    return gemdos_dir_search(image, dir, cursor, GEMDOS_ATTR_SUBDIR, &from_scanned);
}

/* From `child` on, the DND of `dir` that `name` names: along the sibling list, and when that runs out
 * a search of the directory from its mark — which makes the DNDs it has not got yet — unless a search
 * has already reached its end. 0 when neither finds it ($fc6a32..$fc6a48).
 *
 * The ROM also tests `dir` for 0 before the OFD_SCANNED test ($fc6a00); it is the directory the walk
 * is IN, non-zero by the loop's own condition, so the test is dropped here. */
static uint32_t named_child(uint8_t *image, uint32_t dir, uint32_t child, uint32_t cursor, uint32_t name)
{
    while (child != 0 && (uint16_t)gemdos_fcb_name_eq(0, image, name, child) == 0) {
        uint32_t sibling = be32(image + child + DND_SIBLING);

        if (sibling != 0)
            child = sibling;
        else if ((be16(image + be32(image + dir + DND_OFD) + OFD_FLAGS) & OFD_SCANNED) == 0)
            child = search_for_directory(image, dir, cursor);
        else
            child = 0;
    }
    return child;
}

/* $fc696c — from where `path` starts (`$fc68dc`: a drive, the root or the current directory), one
 * component at a time (`$fc5e08`, which stops short of the last unless `take_tail`): `.` stays, `..`
 * climbs DND_PARENT, and a name descends into the child it names. Answers the directory reached, 0
 * when a component names nothing (or `..` climbs off the root), and stores in `*tail` how far into
 * the text the walk got.
 *
 * WHERE THE TAIL IS LEFT depends on HOW a component was not found. A directory with NO child list at
 * all is searched once, and a miss there ends the walk AT the component ($fc69f0); a directory whose
 * list runs out ends it PAST the component and its separator, like a success ($fc6a2c -> $fc6a4a). */
static uint32_t walk(uint8_t *image, uint32_t path, uint32_t *tail, uint16_t take_tail, uint32_t name)
{
    uint32_t cursor = path;
    uint32_t dir = path_start(image, &cursor);
    int16_t step;

    if (dir == 0)
        return 0;
    for (;;) {
        step = (int16_t)gemdos_split_path(0, image, cursor, name, take_tail);
        if (step == 0)
            break;
        if (step < 0) {
            if (step == DOT_NAME_PARENT)
                dir = be32(image + dir + DND_PARENT);
            step = (int16_t)-step;
        } else {
            uint32_t first = be32(image + dir + DND_CHILD);

            if (first == 0)
                first = search_for_directory(image, dir, cursor);
            if (first == 0) {
                dir = 0;
                break;
            }
            dir = named_child(image, dir, first, cursor, name);
        }
        cursor += (uint32_t)(int32_t)step;
        if (image[cursor] == '\0')
            break;
        cursor++;
        if (dir == 0)
            break;
    }
    *tail = cursor;
    return dir;
}

/* ...with its component FCB a frame local, whose address `walk` hands on for every component. */
uint32_t gemdos_find_dir(uint8_t *image, uint32_t path, uint32_t *tail, uint16_t take_tail)
{
    uint8_t name_local[GEMDOS_SEARCH_PATTERN_BYTES];
    uint32_t dir = walk(image, path, tail, take_tail, gemdos_host_slot_claim(WALK_NAME, name_local));

    gemdos_host_slot_release(WALK_NAME);
    return dir;
}

/* ---- $fc6df4, Fsnext ----------------------------------------------------------------------------- */

/* $fc6df4 ($4f) — the search `Fsfirst` left in the DTA, continued: its directory, its position, its
 * TEXT pattern and its attribute, through `$fc663c`. A match stores the position after it and fills
 * the DTA; none is ENMFIL with the DTA untouched.
 *
 * The ROM reads `p_dta` out of the basepage afresh for each use ($fc6e00, $fc6e22, $fc6e3c, $fc6e5c,
 * and after the search $fc6e7e, $fc6ea0); this reads it once. The same address on every data a case
 * can stage — nothing under `$fc663c` writes `p_run` or the basepage — so the difference is
 * unobservable and unpinned. */
uint32_t gemdos_fsnext(uint8_t *image)
{
    uint32_t dta = be32(image + gemdos_basepage(image) + BASEPAGE_DTA);
    uint32_t dnd = gemdos_dta_long(image, dta + DTA_DND);
    int32_t position = (int32_t)gemdos_dta_long(image, dta + DTA_DIRPOS);
    uint32_t found = gemdos_dir_search(image, dnd, dta + DTA_PATTERN, image[dta + DTA_ATTR], &position);

    if (found == 0)
        return GEMDOS_ENMFIL;
    gemdos_dta_store_long(image, dta + DTA_DIRPOS, (uint32_t)position);
    gemdos_fill_dta(image, found, dta);
    return 0;
}
