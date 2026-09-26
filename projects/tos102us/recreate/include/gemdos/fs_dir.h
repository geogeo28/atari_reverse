/* gemdos/fs_dir.h — the GEMDOS file system's DIRECTORY layer: searching one directory, walking a path
 * down the tree of directory nodes, and `Fsnext` (`src/gemdos/fs_dir.c`).
 *
 *   $fc663c  gemdos_dir_search   one directory, from a position, for the first entry a pattern matches
 *   $fc696c  gemdos_find_dir     a path's directories walked to the one holding its last component
 *   $fc6df4  gemdos_fsnext       ($4f) the next match of the search a DTA holds
 *
 * The records are `include/gemdos/fs.h`'s; the name and path routines under these are
 * `include/gemdos/fs_drive.h`'s and `src/gemdos/fs_name.c`'s.
 */
#ifndef TOS102US_GEMDOS_FS_DIR_H
#define TOS102US_GEMDOS_FS_DIR_H

#include <stdint.h>

#include "gemdos/fs.h"
#include "gemdos/fs_io.h"

/* The POSITION that means "resume where the directory's DND_SCANNED says" ($fc668c `cmpl #-1`) — and,
 * for a search that finds its entry, "answer the entry's DND, not the entry" ($fc67b2). Only
 * `$fc696c` passes it, as the address of a ROM longword holding -1 (`$fd2fe8`, the mask table's two
 * `$ffff` entries read as one long); a search never stores through a position of -1, so a local
 * holding -1 is the same argument. */
#define GEMDOS_SEARCH_FROM_SCANNED (-1)

/* The pattern `$fc663c` builds in its frame and `$fc696c`'s component FCB: an FCB name and then the
 * attribute byte `$fc5c9a` compares (`include/gemdos/gemdos.h`'s host slots stand in for both off
 * target). */
#define GEMDOS_SEARCH_PATTERN_BYTES (DIRENT_ATTR + 1)

/* ---- the DTA's two unaligned longwords -----------------------------------------------------------
 * DTA_DIRPOS and DTA_DND sit at ODD offsets, so the ROM moves them four bytes at a time through
 * `$fc564a` ($fc6e14, $fc6e36, $fc6e9a) — a long access there is an ADDRESS ERROR on a 68000. These
 * are the same four bytes, big-endian, one at a time. */
static inline uint32_t gemdos_dta_long(const uint8_t *image, uint32_t at)
{
    return (uint32_t)image[at] << 24 | (uint32_t)image[at + 1] << 16 | (uint32_t)image[at + 2] << 8
           | image[at + 3];
}

static inline void gemdos_dta_store_long(uint8_t *image, uint32_t at, uint32_t value)
{
    image[at] = (uint8_t)(value >> 24);
    image[at + 1] = (uint8_t)(value >> 16);
    image[at + 2] = (uint8_t)(value >> 8);
    image[at + 3] = (uint8_t)value;
}

/* ---- what a search is asked for -------------------------------------------------------------------
 * The attribute arguments `$fc663c`'s callers hand it, beside the bits `$fc5c9a` gives meaning to
 * (`include/gemdos/fs.h`). The two made of those bits are spelt as the literal the ROM pushes and
 * pinned against the bits they are, so the Python side (`test/gemdos_fs.py`) reads the one value.
 *
 * `Fopen`, `Fattrib` and `Fdelete` search with every bit but SUBDIR and VOLUME (`move.w #39` at $fc7630,
 * $fc76a4, $fc77dc), so none of them can name a plain subdirectory or a volume label — only an entry
 * whose attribute is 0 or shares one of these bits. */
#define GEMDOS_ATTR_ANY_FILE       0x27
/* ...what `$fc6d14` ORs into any search attribute but VOLUME's (`ori.w #33` at $fc6d24): an `Fsfirst`
 * also finds read-only and archive entries whatever it asked for. */
#define GEMDOS_SFIRST_ALSO_MATCHES 0x21
/* ...and `create`'s two searches, for the name and for a free slot (`move.w #-1` at $fc7222, $fc7272):
 * every attribute. */
#define GEMDOS_ATTR_ANY            ((uint16_t)-1)

_Static_assert(GEMDOS_ATTR_ANY_FILE
               == (GEMDOS_ATTR_READ_ONLY | GEMDOS_ATTR_HIDDEN | GEMDOS_ATTR_SYSTEM | GEMDOS_ATTR_ARCHIVE),
               "the name leaves' search attribute is not every bit but SUBDIR and VOLUME");
_Static_assert(GEMDOS_SFIRST_ALSO_MATCHES == (GEMDOS_ATTR_READ_ONLY | GEMDOS_ATTR_ARCHIVE),
               "Fsfirst's widening is not read-only and archive");

/* How far `$fc696c` walks a path: to the directory holding its last component (a name to be searched
 * for), or into that component too (`Dsetpath` and `Ddelete`, whose last component IS the directory). */
#define GEMDOS_WALK_TO_THE_NAME    0
#define GEMDOS_WALK_THE_WHOLE_PATH 1

/* The next entry of the directory `ofd` reads: a pointer into the cache (`$fc5e9c` with no buffer),
 * or 0 when the directory — its length, or its cluster chain — has ended ($fc674a). */
static inline uint32_t gemdos_next_entry(uint8_t *image, uint32_t ofd)
{
    return gemdos_ofd_read(image, ofd, DIRENT_BYTES, 0);
}

/* $fc663c — search `dnd`'s directory for the entry the TEXT `name` matches under `attr`, from
 * `*position` (or DND_SCANNED, for GEMDOS_SEARCH_FROM_SCANNED), making DNDs for the subdirectories it
 * passes. The entry — a pointer into the cache — or, from DND_SCANNED, its DND; 0 for none. */
uint32_t gemdos_dir_search(uint8_t *image, uint32_t dnd, uint32_t name, uint16_t attr, int32_t *position);

/* $fc696c — walk `path`'s directories from where it starts; the directory holding its last
 * component (or, with `take_tail` GEMDOS_WALK_THE_WHOLE_PATH, that component itself), 0 for a path that
 * leaves the tree.
 * `*tail` is where the walk stopped in the text — not stored when the drive will not open. */
uint32_t gemdos_find_dir(uint8_t *image, uint32_t path, uint32_t *tail, uint16_t take_tail);

/* $fc6df4 ($4f) — the next match of the search the running process's DTA holds: 0 with the DTA
 * filled, or ENMFIL. */
uint32_t gemdos_fsnext(uint8_t *image);

#endif /* TOS102US_GEMDOS_FS_DIR_H */
