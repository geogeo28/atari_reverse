/* fs_records.c — the GEMDOS file system's RECORD layer.
 *
 *   $fc5672  fcb_name_eq        two FCB names, eleven bytes, upper-cased on both sides
 *   $fc5c3c  ofd_new            a DIRECTORY's OFD, built from its DND
 *   $fc65a2  dnd_new            a child DND for a subdirectory entry, pushed on its parent's list
 *   $fc6fdc  ofd_open           a FILE's OFD, built from its entry and put in a handle record
 *   $fc6f5c  handle_alloc       the first free handle record, and then `ofd_open` into it
 *   $fc70f6  dir_zero_cluster   every sector of a directory's current cluster zeroed in the cache
 *   $fc6b66  fcb_to_text        eleven FCB bytes -> "NAME.EXT"
 *   $fc6bd2  dnd_path           a DND -> "\A\B\", root first
 *   $fc6ebc  fill_dta           what Fsfirst/Fsnext report about a found entry
 *
 * TIME AND DATE ARE NOT SWAPPED WHERE CLUSTER AND LENGTH ARE. A DND and an OFD take the directory
 * entry's time and date with a plain `move.w` ($fc6616/$fc661c, $fc70da/$fc70e0) — they stay in the
 * entry's little-endian order — and only the first cluster (and an OFD's length) go through
 * `os_swap_word`/`os_swap_long`. The DTA is the one record that turns time and date round too.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_copy.h"
#include "gemdos/fs_records.h"
#include "gemdos/memory.h"
#include "gemdos/process.h"
#include "machine.h"

/* The first twelve bytes of an OFD's state a second open copies from the first: time, date, first
 * cluster, length — and the HIGH WORD of `OFD_DMD`, since 6 + 12 = 18 ($fc709e `move.w #12`). */
#define SHARED_STATE_BYTES   12
/* The DTA's time and date are one four-byte copy ($fc6ee6 `move.w #4`), and its length another. */
#define DTA_TIME_DATE_BYTES  4
#define LONG_BYTES           4

#define MATCHED              1           /* `moveq #1,d0`, which writes all of it */

/* $fc5672 — both names folded through `$fc50ca` a byte at a time and compared as words; the first
 * difference answers 0 in D0's low word. Unlike `$fc5c9a` there is no `?`, no `$e5` arm and no
 * attribute: this is plain equality, which is what a search uses to find a DND it already has. */
uint32_t gemdos_fcb_name_eq(uint32_t entry_d0, const uint8_t *image, uint32_t name, uint32_t other)
{
    uint16_t at;

    for (at = 0; at < DIRENT_NAME_BYTES; at++)
        if (gemdos_fs_toupper(0, image[name + at]) != gemdos_fs_toupper(0, image[other + at]))
            return set_low_word(entry_d0, 0);     /* `clr.w d0`: the caller's high half stands */
    return MATCHED;
}

/* $fc5c3c — the OFD a directory is read through. Every field but the length comes from the DND,
 * and the two that name the HOLDING directory are the DND's PARENT and the parent's OFD — the entry
 * this directory is rewritten through lives there. 0 when the pool is spent. */
uint32_t gemdos_ofd_new(uint8_t *image, uint32_t dnd)
{
    uint32_t ofd = gemdos_pool_get(image, NODE_POOL_CLASS);

    if (ofd == 0)
        return 0;
    wr16(image + ofd + OFD_STRTCL, be16(image + dnd + DND_STRTCL));
    wr32(image + ofd + OFD_FILELN, DIRECTORY_LENGTH);
    wr32(image + ofd + OFD_DIR_OFD, be32(image + dnd + DND_PARENT_OFD));
    wr32(image + ofd + OFD_DIR_DND, be32(image + dnd + DND_PARENT));
    wr32(image + ofd + OFD_DIRPOS, be32(image + dnd + DND_DIRPOS));
    wr16(image + ofd + OFD_DATE, be16(image + dnd + DND_DATE));
    wr16(image + ofd + OFD_TIME, be16(image + dnd + DND_TIME));
    wr32(image + ofd + OFD_DMD, be32(image + dnd + DND_DMD));
    return ofd;
}

/* $fc65a2 — a DND for the subdirectory `dirent` names, as the FIRST child of `parent`.
 *
 * The entry's position is taken from the parent's OFD as it stands, one entry back: this is only
 * ever called by the directory search with that entry just read. The parent's OFD is read BEFORE
 * the pool call, as the ROM does. 0 when the pool is spent, with the parent untouched. */
uint32_t gemdos_dnd_new(uint8_t *image, uint32_t parent, uint32_t dirent)
{
    uint32_t parent_ofd = be32(image + parent + DND_OFD);
    uint32_t child = gemdos_pool_get(image, NODE_POOL_CLASS);

    if (child == 0)
        return 0;
    if (be32(image + parent + DND_CHILD) != 0)
        wr32(image + child + DND_SIBLING, be32(image + parent + DND_CHILD));
    wr32(image + parent + DND_CHILD, child);
    wr32(image + child + DND_PARENT, parent);
    wr32(image + child + DND_OFD, 0);
    wr16(image + child + DND_STRTCL, be16(image + dirent + DIRENT_STRTCL));
    os_swap_word(image, child + DND_STRTCL);
    wr32(image + child + DND_DMD, be32(image + parent + DND_DMD));
    wr32(image + child + DND_PARENT_OFD, parent_ofd);
    wr32(image + child + DND_DIRPOS, be32(image + parent_ofd + OFD_POS) - ENTRY_BEHIND_POSITION);
    wr16(image + child + DND_TIME, be16(image + dirent + DIRENT_TIME));
    wr16(image + child + DND_DATE, be16(image + dirent + DIRENT_DATE));
    gemdos_bcopy(image, DIRENT_NAME_BYTES, dirent + DIRENT_NAME, child + DND_NAME);
    return child;
}

/* The OFD already open on the entry at `dirpos` of this directory, or 0. Matched on the position
 * alone: every OFD on a DND's list is an entry of that one directory. */
static uint32_t ofd_already_open(const uint8_t *image, uint32_t dnd, uint32_t dirpos)
{
    uint32_t open = be32(image + dnd + DND_FILES);

    while (open != 0 && be32(image + open + OFD_DIRPOS) != dirpos)
        open = be32(image + open + OFD_LINK);
    return open;
}

/* ...a first open takes the entry's own fields: cluster and length turned round from the disk's
 * order, time and date copied as they are ($fc70b2..$fc70e0). */
static void ofd_take_entry(uint8_t *image, uint32_t ofd, uint32_t dirent)
{
    wr16(image + ofd + OFD_STRTCL, be16(image + dirent + DIRENT_STRTCL));
    os_swap_word(image, ofd + OFD_STRTCL);
    wr32(image + ofd + OFD_FILELN, be32(image + dirent + DIRENT_FILELN));
    os_swap_long(image, ofd + OFD_FILELN);
    wr16(image + ofd + OFD_DATE, be16(image + dirent + DIRENT_DATE));
    wr16(image + ofd + OFD_TIME, be16(image + dirent + DIRENT_TIME));
}

/* $fc6fdc — an OFD for the file `dirent` names in directory `dnd`, stored as handle `handle`'s value
 * and pushed on the directory's open-file list. Answers the handle, sign-extended, or ENSMEM.
 *
 * A SECOND OPEN of an entry already open does not re-read the entry: it copies twelve bytes of the
 * first OFD's state from +6 — which runs two bytes into `OFD_DMD`, harmless only because both OFDs
 * are on one drive — and stores a pointer to itself in the FIRST's `OFD_NEXT_SAME_FILE`, overwriting
 * whatever an earlier second open left there. */
uint32_t gemdos_ofd_open(uint8_t *image, uint32_t dirent, uint32_t dnd, int16_t handle,
                         uint16_t mode)
{
    uint32_t dmd = be32(image + dnd + DND_DMD);
    uint32_t ofd = gemdos_pool_get(image, NODE_POOL_CLASS);
    uint32_t dir_ofd;
    uint32_t first;

    if (ofd == 0)
        return GEMDOS_ENSMEM;
    wr16(image + ofd + OFD_MODE, mode);
    wr32(image + ofd + OFD_DMD, dmd);
    wr32(image + gemdos_descriptor_of(handle) + HANDLE_VALUE, ofd);
    wr16(image + ofd + OFD_UNUSED, 0);
    wr16(image + ofd + OFD_CURCL, 0);
    wr16(image + ofd + OFD_CLOFF, 0);
    wr32(image + ofd + OFD_DIR_DND, dnd);
    dir_ofd = be32(image + dnd + DND_OFD);
    wr32(image + ofd + OFD_DIR_OFD, dir_ofd);
    wr32(image + ofd + OFD_DIRPOS, be32(image + dir_ofd + OFD_POS) - ENTRY_BEHIND_POSITION);

    first = ofd_already_open(image, dnd, be32(image + ofd + OFD_DIRPOS));
    wr32(image + ofd + OFD_LINK, be32(image + dnd + DND_FILES));
    wr32(image + dnd + DND_FILES, ofd);
    if (first != 0) {
        gemdos_bcopy(image, SHARED_STATE_BYTES, first + OFD_TIME, ofd + OFD_TIME);
        wr32(image + first + OFD_NEXT_SAME_FILE, ofd);
    } else {
        ofd_take_entry(image, ofd, dirent);
    }
    return sign_ext16((uint16_t)handle);
}

/* $fc6f5c — the first handle record no process owns, claimed for `p_run` with one reference, and
 * then `ofd_open` into it. ENHNDL when all 75 are owned. A record is free when its OWNER is 0, not
 * its value. */
uint32_t gemdos_handle_alloc(uint8_t *image, uint32_t dirent, uint32_t dnd, uint16_t mode)
{
    int16_t index;
    uint32_t record;

    for (index = 0; index < GEMDOS_HANDLE_COUNT; index++)
        if (be32(image + gemdos_descriptor_at(index) + HANDLE_OWNER) == 0)
            break;
    if (index == GEMDOS_HANDLE_COUNT)
        return GEMDOS_ENHNDL;
    record = gemdos_descriptor_at(index);
    wr32(image + record + HANDLE_OWNER, gemdos_basepage(image));
    wr16(image + record + HANDLE_REFCOUNT, 1);
    return gemdos_ofd_open(image, dirent, dnd, (int16_t)(index + GEMDOS_FIRST_FILE_HANDLE), mode);
}

/* One sector of the cache, marked dirty and zeroed over `bytes`. Answers the buffer. */
static uint32_t zeroed_sector(uint8_t *image, uint16_t recno, uint32_t dmd, int16_t bytes)
{
    uint32_t buffer = gemdos_buffer_get(image, recno, dmd, BCB_MARKED_DIRTY);
    int16_t at;

    for (at = 0; at < bytes; at++)
        image[buffer + (uint32_t)at] = 0;
    return buffer;
}

/* $fc70f6 — zero the cluster a directory's OFD is positioned in, through the cache, and answer the
 * buffer holding its FIRST sector.
 *
 * The first sector is done LAST, so it is the one left most recently used. Geometry (sectors per
 * cluster, bytes per sector) is read from the OFD's DMD, but the cache is asked with the DND's —
 * two fields a consistent tree keeps equal. Both counts are compared SIGNED. */
uint32_t gemdos_dir_zero_cluster(uint8_t *image, uint32_t dnd)
{
    uint32_t ofd = be32(image + dnd + DND_OFD);
    uint32_t geometry = be32(image + ofd + OFD_DMD);
    int16_t sector_bytes = (int16_t)be16(image + geometry + DMD_RECSIZ);
    uint16_t first_record = be16(image + ofd + OFD_CURREC);
    int16_t sector;

    for (sector = 1; sector < (int16_t)be16(image + geometry + DMD_CLSIZ); sector++)
        zeroed_sector(image, (uint16_t)(first_record + (uint16_t)sector), be32(image + dnd + DND_DMD),
                      sector_bytes);
    return zeroed_sector(image, first_record, be32(image + dnd + DND_DMD), sector_bytes);
}

/* Up to `width` bytes of an FCB field, stopping at a NUL or a pad space. Answers the new end. */
static uint32_t copy_name_field(uint8_t *image, uint32_t field, uint32_t text, uint16_t width)
{
    uint16_t copied;

    for (copied = 0; copied < width && image[field] != '\0' && image[field] != FCB_PAD; copied++)
        image[text++] = image[field++];
    return text;
}

/* $fc6b66 — "NAME.EXT" from eleven FCB bytes, NUL-terminated; answers the address of the NUL.
 *
 * Three ways it stops short: an FCB whose first byte is NUL is the empty string; a stem starting
 * with `.` (the `.` and `..` entries) gets no extension at all; and an extension whose first byte
 * is a space gets no dot. A first extension byte of NUL is NOT a space, so it still gets the dot. */
uint32_t gemdos_fcb_to_text(uint8_t *image, uint32_t fcb, uint32_t text)
{
    if (image[fcb] != '\0') {
        text = copy_name_field(image, fcb, text, FCB_STEM_BYTES);
        if (image[fcb] != NAME_DOT && image[fcb + FCB_STEM_BYTES] != FCB_PAD) {
            image[text++] = NAME_DOT;
            text = copy_name_field(image, fcb + FCB_STEM_BYTES, text, FCB_EXTENSION_BYTES);
        }
    }
    image[text] = '\0';
    return text;
}

/* $fc6bd2 — the path of `dnd`, root first, each name followed by a `\`: recursion up the parent
 * chain, then this DND's own name. The root's name is empty, so a path starts with `\`. Each `\`
 * overwrites the NUL `fcb_to_text` left, so the text ends UNTERMINATED after its last `\` — `Dgetpath`
 * steps back one and writes the NUL there ($fc6c84). Answers one past the last `\`. */
uint32_t gemdos_dnd_path(uint8_t *image, uint32_t dnd, uint32_t text)
{
    if (be32(image + dnd + DND_PARENT) != 0)
        text = gemdos_dnd_path(image, be32(image + dnd + DND_PARENT), text);
    text = gemdos_fcb_to_text(image, dnd + DND_NAME, text);
    image[text] = PATH_SEPARATOR;
    return text + 1;
}

/* $fc6ebc — the found entry into the DTA: its attribute, its time and date and its length turned
 * round from the disk's order, and its name as text. */
void gemdos_fill_dta(uint8_t *image, uint32_t dirent, uint32_t dta)
{
    image[dta + DTA_FOUND_ATTR] = image[dirent + DIRENT_ATTR];
    gemdos_bcopy(image, DTA_TIME_DATE_BYTES, dirent + DIRENT_TIME, dta + DTA_TIME);
    os_swap_word(image, dta + DTA_TIME);
    os_swap_word(image, dta + DTA_DATE);
    gemdos_bcopy(image, LONG_BYTES, dirent + DIRENT_FILELN, dta + DTA_FILELN);
    os_swap_long(image, dta + DTA_FILELN);
    gemdos_fcb_to_text(image, dirent + DIRENT_NAME, dta + DTA_NAME);
}
