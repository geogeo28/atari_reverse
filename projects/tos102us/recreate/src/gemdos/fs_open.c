/* fs_open.c — the GEMDOS leaves that FIND A NAME and act on its entry.
 *
 *   $fc6d14  sfirst          a path's first match into a DTA, with the search's state
 *   $fc6cf6  Fsfirst ($4e)   ...into the running process's DTA
 *   $fc6a7e  Dsetpath ($3b)  a path made a drive's current directory
 *   $fc7606  open            a path's file opened into a handle
 *   $fc75f2  Fopen ($3d)     ...the same, as the leaf
 *   $fc7678  Fattrib ($43)   a file's attribute byte, read or written in its entry
 *   $fc77b2  Fdelete ($41)   a path's file deleted
 *
 * EVERY ONE IS THE SAME TWO STEPS: `$fc696c` walks the path to the directory holding its last
 * component, and `$fc663c` finds that component in it from position 0. What differs is the attribute
 * the name is searched under — `Fsfirst`'s own (widened), or GEMDOS_ATTR_ANY_FILE, which no plain
 * subdirectory or volume label answers — and what is done with the entry found.
 *
 * TWO ERROR CODES FOR ONE MISS. `sfirst`, `open` and `Fdelete` answer EFILNF whether the DIRECTORY
 * or the NAME was not found; only `Fattrib` (and `Dsetpath`, which has no name step) says EPTHNF for a
 * directory that is not there.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_copy.h"
#include "gemdos/fs_dir.h"
#include "gemdos/fs_drive.h"
#include "gemdos/fs_file.h"
#include "gemdos/fs_io.h"
#include "gemdos/fs_open.h"
#include "gemdos/fs_records.h"
#include "gemdos/process.h"
#include "machine.h"

/* The entry's attribute byte, seen from the position a search leaves: its entry is
 * ENTRY_BEHIND_POSITION back, and the byte DIRENT_ATTR into that — 21 back ($fc76c2 `subi.l #21`). */
#define ATTRIBUTE_BEHIND_POSITION (ENTRY_BEHIND_POSITION - DIRENT_ATTR)

/* The one byte `Fattrib` moves — through its host slot, which is exactly as wide. */
#define ATTRIBUTE_BYTES       1
_Static_assert(GEMDOS_HOST_SLOT_ATTRIBUTE_BYTES == ATTRIBUTE_BYTES,
               "a host slot narrower or wider than the frame local it stands in for");

/* ---- the two steps -------------------------------------------------------------------------------- */

/* `name`'s entry in the directory `*dnd` of its path: a pointer into the cache, or 0 — with `*dnd` 0
 * when the path's directory was not there. `*position` is left one past the entry, and `*tail` where
 * the name starts in the text. */
static uint32_t find_entry(uint8_t *image, uint32_t name, uint16_t attr, uint32_t *dnd, int32_t *position,
                           uint32_t *tail)
{
    *position = 0;
    *dnd = gemdos_find_dir(image, name, tail, GEMDOS_WALK_TO_THE_NAME);
    if (*dnd == 0)
        return 0;
    return gemdos_dir_search(image, *dnd, *tail, attr, position);
}

static int is_read_only(const uint8_t *image, uint32_t entry)
{
    return (image[entry + DIRENT_ATTR] & GEMDOS_ATTR_READ_ONLY) != 0;
}

/* ---- $fc6d14 / $fc6cf6: the first search --------------------------------------------------------- */

/* $fc6d14 — the first entry `name` matches under `attr`, into the DTA at `dta`: 0, or EFILNF for a
 * directory or a name that is not there. A `dta` of 0 answers the same and stores nothing (`Pexec`'s
 * existence test, $fc81b0).
 *
 * The attribute is WIDENED by GEMDOS_SFIRST_ALSO_MATCHES unless the WORD is exactly VOLUME, and the
 * widened one is what the DTA keeps for `Fsnext`. THE PATTERN THE DTA KEEPS IS TWELVE BYTES OF THE
 * PATH'S TAIL whatever its length (`$fc564a` with a count of 12, $fc6d8e): a short name brings its
 * NUL and whatever the caller's buffer held after it. The position and the DND go in as the two
 * unaligned longwords, then `$fc6ebc` fills the rest from the entry. */
uint32_t gemdos_sfirst(uint8_t *image, uint32_t name, uint16_t attr, uint32_t dta)
{
    uint32_t tail;
    uint32_t dnd;
    uint32_t entry;
    int32_t position;

    if (attr != GEMDOS_ATTR_VOLUME)
        attr |= GEMDOS_SFIRST_ALSO_MATCHES;
    entry = find_entry(image, name, attr, &dnd, &position, &tail);
    if (entry == 0)
        return GEMDOS_EFILNF;
    if (dta != 0) {
        gemdos_bcopy(image, DTA_PATTERN_BYTES, tail, dta + DTA_PATTERN);
        image[dta + DTA_ATTR] = (uint8_t)attr;
        gemdos_dta_store_long(image, dta + DTA_DIRPOS, (uint32_t)position);
        gemdos_dta_store_long(image, dta + DTA_DND, dnd);
        gemdos_fill_dta(image, entry, dta);
    }
    return 0;
}

/* $fc6cf6 ($4e) — `sfirst` into the running process's DTA. */
uint32_t gemdos_fsfirst(uint8_t *image, uint32_t name, uint16_t attr)
{
    return gemdos_sfirst(image, name, attr, be32(image + gemdos_basepage(image) + BASEPAGE_DTA));
}

/* ---- $fc6a7e: Dsetpath ---------------------------------------------------------------------------- */

/* A node's reference count — a SIGNED index, widened from the p_curdir byte ($fc6ade `movea.w`). */
static uint8_t *node_references(uint8_t *image, int16_t node)
{
    return image + addr_add(GEMDOS_CURDIR_REFCOUNTS, (uint32_t)(int32_t)node);
}

/* $fc6a7e ($3b) — make `path` the running process's current directory on its drive: 0, EPTHNF, or
 * whatever negative the drive's log-in answered.
 *
 * THE OLD DIRECTORY IS LET GO FIRST AND NEVER TAKEN BACK. Once the drive is open, the node the
 * process's p_curdir byte names loses a reference ($fc6ae6); only then are a free node slot and the
 * new directory looked for, and when either is missing the byte still names the node it no longer
 * holds a count on. The slot search runs AFTER the drop, so a node the process was the only holder of
 * is free again and is handed straight back — when no slot below it is free first. (The ROM also skips
 * the drop for a byte of 0, $fc6adc; `$fc67de` has just made the byte non-zero, so that arm is
 * unreachable and not kept.)
 *
 * THE DRIVE PREFIX IS FOR THE LOG-IN ONLY. `X:` picks the drive whose byte is set and is then stepped
 * over in the ARGUMENT ($fc6aa6 `addq.l #2,8(a6)`), so `$fc696c` walks the rest on the CURRENT drive:
 * "B:\FOO" with A: current makes A:'s \FOO the current directory OF B:. And that walk logs the current
 * drive in: if ITS byte is 0, `$fc67de` gives it the first free slot — the very one just chosen — so the
 * two drives end naming one node, counted twice.
 *
 * A NEGATIVE DRIVE IS AN ERROR. The log-in answers the drive sign-extended, and `bge` takes any
 * negative answer for a failure: a letter with bit 7 set makes a negative drive, which `$fc67de`
 * accepts and `Dsetpath` then answers as though it were an error code. */
uint32_t gemdos_dsetpath(uint8_t *image, uint32_t path)
{
    int16_t drive = gemdos_drive_of_prefix(image, &path);
    int32_t opened = (int32_t)gemdos_open_drive(image, drive);
    uint8_t *curdir;
    int16_t slot;
    uint32_t tail;
    uint32_t directory;

    if (opened < 0)
        return (uint32_t)opened;

    curdir = gemdos_curdir_entry(image, drive);
    (*node_references(image, (int8_t)*curdir))--;
    slot = gemdos_free_directory_slot(image);
    if (slot == GEMDOS_DIRECTORY_NODE_COUNT)
        return GEMDOS_EPTHNF;
    directory = gemdos_find_dir(image, path, &tail, GEMDOS_WALK_THE_WHOLE_PATH);
    if (directory == 0)
        return GEMDOS_EPTHNF;
    (*node_references(image, slot))++;
    wr32(image + gemdos_node_slot(slot), directory);
    *curdir = (uint8_t)slot;
    return 0;
}

/* ---- $fc7606 / $fc75f2: opening ------------------------------------------------------------------- */

/* $fc7606 — open `name`'s file for `mode` (0 read, anything else writing): a handle, EFILNF, EACCDN
 * for a read-only entry opened with any mode but 0, or what `$fc6f5c` answers (ENHNDL, ENSMEM). */
uint32_t gemdos_open(uint8_t *image, uint32_t name, uint16_t mode)
{
    uint32_t dnd;
    int32_t position;
    uint32_t tail;
    uint32_t entry = find_entry(image, name, GEMDOS_ATTR_ANY_FILE, &dnd, &position, &tail);

    if (entry == 0)
        return GEMDOS_EFILNF;
    if (is_read_only(image, entry) && mode != OPEN_MODE_READ)
        return GEMDOS_EACCDN;
    return gemdos_handle_alloc(image, entry, dnd, mode);
}

/* $fc75f2 ($3d) — `open`. */
uint32_t gemdos_fopen(uint8_t *image, uint32_t name, uint16_t mode)
{
    return gemdos_open(image, name, mode);
}

/* ---- $fc7678: Fattrib ----------------------------------------------------------------------------- */

/* $fc7678 ($43) — `name`'s attribute byte, read when `set` is 0 and otherwise written as `attribute`'s
 * low byte: that byte, sign-extended to a word, or EPTHNF / EFILNF.
 *
 * THE BYTE IS MOVED THROUGH THE DIRECTORY'S OFD, one byte at `ATTRIBUTE_BEHIND_POSITION` before where
 * the search stopped, into or out of the argument word itself — a host slot off target
 * (`include/gemdos/gemdos.h`). A write closes the directory (flag 2, which flushes every buffer); a
 * read does not. Nothing is checked or masked: a read-only file's byte can be cleared, and any byte at
 * all written, the subdirectory and volume bits included.
 *
 * THE ANSWER IS ONLY A WORD (`ext.w d0`): the high half is what the read or the close left in D0. */
uint32_t gemdos_fattrib(uint8_t *image, uint32_t name, uint16_t set, uint16_t attribute)
{
    uint32_t dnd;
    int32_t position;
    uint32_t tail;
    uint32_t entry = find_entry(image, name, GEMDOS_ATTR_ANY_FILE, &dnd, &position, &tail);
    uint32_t directory;
    uint8_t attribute_local;
    uint32_t attribute_at;
    uint32_t result;

    if (dnd == 0)
        return GEMDOS_EPTHNF;
    if (entry == 0)
        return GEMDOS_EFILNF;
    directory = be32(image + dnd + DND_OFD);
    gemdos_ofd_seek(image, directory, (uint32_t)position - ATTRIBUTE_BEHIND_POSITION);
    attribute_at = gemdos_host_slot_claim(ATTRIBUTE, &attribute_local);
    image[attribute_at] = (uint8_t)attribute;
    if (set == 0) {
        result = gemdos_ofd_read(image, directory, ATTRIBUTE_BYTES, attribute_at);
    } else {
        gemdos_ofd_write(image, directory, ATTRIBUTE_BYTES, attribute_at);
        result = gemdos_ofd_close(image, directory, OFD_CLOSE_DIRECTORY);
    }
    result = set_low_word(result, (uint16_t)sign_ext8(image[attribute_at]));
    gemdos_host_slot_release(ATTRIBUTE);
    return result;
}

/* ---- $fc77b2: Fdelete ----------------------------------------------------------------------------- */

/* $fc77b2 ($41) — delete `name`'s file: 0, EFILNF, EACCDN for a read-only entry, or `$fc7824`'s own
 * EACCDN for one another process has open (the caller's own opens of it are closed on the way). */
uint32_t gemdos_fdelete(uint8_t *image, uint32_t name)
{
    uint32_t dnd;
    int32_t position;
    uint32_t tail;
    uint32_t entry = find_entry(image, name, GEMDOS_ATTR_ANY_FILE, &dnd, &position, &tail);

    if (entry == 0)
        return GEMDOS_EFILNF;
    if (is_read_only(image, entry))
        return GEMDOS_EACCDN;
    return gemdos_delete_entry(image, dnd, entry, (uint32_t)position - ENTRY_BEHIND_POSITION);
}
