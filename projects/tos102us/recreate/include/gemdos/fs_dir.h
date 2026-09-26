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

/* $fc663c — search `dnd`'s directory for the entry the TEXT `name` matches under `attr`, from
 * `*position` (or DND_SCANNED, for GEMDOS_SEARCH_FROM_SCANNED), making DNDs for the subdirectories it
 * passes. The entry — a pointer into the cache — or, from DND_SCANNED, its DND; 0 for none. */
uint32_t gemdos_dir_search(uint8_t *image, uint32_t dnd, uint32_t name, uint16_t attr, int32_t *position);

/* $fc696c — walk `path`'s directories from where it starts; the directory holding its last
 * component (or, with `take_tail`, that component itself), 0 for a path that leaves the tree.
 * `*tail` is where the walk stopped in the text — not stored when the drive will not open. */
uint32_t gemdos_find_dir(uint8_t *image, uint32_t path, uint32_t *tail, uint16_t take_tail);

/* $fc6df4 ($4f) — the next match of the search the running process's DTA holds: 0 with the DTA
 * filled, or ENMFIL. */
uint32_t gemdos_fsnext(uint8_t *image);

#endif /* TOS102US_GEMDOS_FS_DIR_H */
