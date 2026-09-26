/* gemdos/fs_drive.h — the file system's DRIVE and PATH layer: logging a drive in, and the first steps
 * of walking a path on it (`src/gemdos/fs_drive.c`).
 *
 *   $fc50fa  gemdos_dmd_alloc      the four records one drive needs, out of the GEMDOS pool
 *   $fc53c0  gemdos_dmd_build      a BPB -> that drive's media descriptor and its two pseudo-files
 *   $fc67de  gemdos_open_drive     log the drive in (BIOS `Getbpb`), give the process a directory
 *   $fc68dc  gemdos_path_start     `X:` and a leading `\` -> the directory node a path starts in
 *   $fc7e52  gemdos_dot_name       is this component "", "." or ".."?
 *   $fc5e08  gemdos_split_path     the next component of a path, into an FCB name
 *   $fc7e94  gemdos_strneq         n bytes of two strings equal? (the dispatcher's device-name arm)
 *
 * The records these routines build and read are `include/gemdos/fs.h`'s; the RAM tables they index
 * (`GEMDOS_DMD_TABLE`, `GEMDOS_DIRECTORY_NODES`, `GEMDOS_DRIVES_OPENED`) are `include/addrs.h`'s.
 *
 * `entry_d0` ON THE THREE STRING ROUTINES is `include/gemdos/fs.h`'s convention: each can return
 * through a `move.w`/`clr.w` that leaves the caller's high half of D0 standing.
 */
#ifndef TOS102US_GEMDOS_FS_DRIVE_H
#define TOS102US_GEMDOS_FS_DRIVE_H

#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "machine.h"

/* The two drive tables' stride: `GEMDOS_DMD_TABLE` and `GEMDOS_DIRECTORY_NODES` hold one pointer per
 * entry, indexed `adda.l a0,a0` twice ($fc5112, $fc6852). */
#define DRIVE_TABLE_ENTRY_BYTES 4

/* ---- a path's drive prefix, and the directory node slots -----------------------------------------
 * `Dsetpath` ($fc6a7e) repeats two pieces of this layer instruction for instruction: `$fc6a8a..$fc6aa6`
 * reads `X:` exactly as `$fc68dc` does, and `$fc6ae8..$fc6afe` searches the node slots exactly as
 * `$fc67de` does. Written once, here, for both. */
#define DRIVE_LETTER_SEPARATOR ':'
#define FIRST_DRIVE_LETTER     'A'
/* `X:` — the letter and its colon, consumed together ($fc6902 `addq.l #2`, $fc6aa6). */
#define DRIVE_PREFIX_BYTES     2
/* The directory slot search starts at 1: a p_curdir byte of 0 means "no directory", so node 0 is
 * never handed out ($fc6862 `moveq #1,d6`). */
#define FIRST_DIRECTORY_SLOT   1

/* The drive `X:` at `text` names, with `*text` stepped past the prefix — or, with no `:` as the text's
 * SECOND byte, the running process's current drive and `*text` untouched. The letter is upper-cased and
 * `'A'` subtracted as a WORD, with no bound: `1:` is drive -16. The `:` test reads the second byte
 * before anything checks the first, so an empty text reads one byte past its NUL. */
static inline int16_t gemdos_drive_of_prefix(const uint8_t *image, uint32_t *text)
{
    int16_t drive;

    if (image[*text + 1] != DRIVE_LETTER_SEPARATOR)
        return gemdos_current_drive(image);
    drive = (int16_t)(uint16_t)(gemdos_fs_toupper(0, (uint16_t)sign_ext8(image[*text])) - FIRST_DRIVE_LETTER);
    *text += DRIVE_PREFIX_BYTES;
    return drive;
}

/* The first directory node slot from FIRST_DIRECTORY_SLOT with no holder (a reference count of 0), or
 * GEMDOS_DIRECTORY_NODE_COUNT when all are held. */
static inline int16_t gemdos_free_directory_slot(const uint8_t *image)
{
    int16_t slot;

    for (slot = FIRST_DIRECTORY_SLOT;
         slot < GEMDOS_DIRECTORY_NODE_COUNT && image[GEMDOS_CURDIR_REFCOUNTS + slot] != 0;
         slot++)
        ;
    return slot;
}

/* Every index into the drive tables is a SIGNED word, widened by the ROM's `movea.w` or `ext.w`
 * before it is scaled, and none is bounded: a node out of range addresses outside its table, as the
 * ROM does. `node`'s longword in `GEMDOS_DIRECTORY_NODES`: */
static inline uint32_t gemdos_node_slot(int16_t node)
{
    return addr_add(GEMDOS_DIRECTORY_NODES, (uint32_t)(int32_t)node * DRIVE_TABLE_ENTRY_BYTES);
}

/* ...and the running process's p_curdir byte for `drive`, which holds a node as a signed byte. */
static inline uint8_t *gemdos_curdir_entry(uint8_t *image, int16_t drive)
{
    return gemdos_basepage_byte(image, gemdos_basepage(image), BASEPAGE_CURDIR + (uint32_t)(int32_t)drive);
}

/* THE FAT PSEUDO-FILE STARTS AT POSITION 3, byte offset 3 in its cluster ($fc55be `move.l #3`,
 * $fc55ca `move.w #3`), with no current cluster. Nothing in the builder says why; the root
 * directory's pseudo-file starts at 0 like every other OFD. Reproduced, not explained. */
#define FAT_OFD_START_POSITION 3

/* `$fc7e52`'s answer for an EMPTY component (`moveq #1` at $fc7e62); the other two are the number
 * of dots NEGATED, and 0 is "an ordinary name". `$fc696c` climbs on DOT_NAME_PARENT ($fc69ae `cmp.w
 * #-2`) and steps over either. */
#define DOT_NAME_EMPTY        1
#define DOT_NAME_SELF         (-1)  /* "." */
#define DOT_NAME_PARENT       (-2)  /* ".." */

uint32_t gemdos_dmd_alloc(uint8_t *image, int16_t drive);
uint32_t gemdos_dmd_build(uint8_t *image, uint32_t bpb, int16_t drive);
uint32_t gemdos_open_drive(uint8_t *image, int16_t drive);
uint32_t gemdos_path_start(uint8_t *image, uint32_t path_pointer);
uint32_t gemdos_dot_name(uint32_t entry_d0, const uint8_t *image, uint32_t name, uint16_t terminator);
uint32_t gemdos_split_path(uint32_t entry_d0, uint8_t *image, uint32_t path, uint32_t fcb,
                           uint16_t take_tail);
uint32_t gemdos_strneq(uint32_t entry_d0, const uint8_t *image, uint16_t count, uint32_t left,
                       uint32_t right);
/* A drive's DMD, out of its table slot (0 for one never logged in), and the running process's current
 * directory node on it — its `p_curdir` byte's slot — for the leaves above this layer. */
uint32_t gemdos_drive_dmd(const uint8_t *image, int16_t drive);
uint32_t gemdos_current_directory(uint8_t *image, int16_t drive);

#endif /* TOS102US_GEMDOS_FS_DRIVE_H */
