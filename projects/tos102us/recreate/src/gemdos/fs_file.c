/* fs_file.c — the GEMDOS file system's FILE layer: the end of an open file, the end of a directory
 * entry, and the one leaf that reaches an open file's entry directly.
 *
 *   $fc57ee  ofd_close      an OFD's entry written back, the OFD off its directory's list, and then
 *                           EVERY buffer of EVERY drive flushed
 *   $fc7824  delete_entry   the entry's open copies closed (or EACCDN), its chain freed, `$e5` over
 *                           its first byte, and the directory closed — which flushes everything too
 *   $fc772e  Fdatime ($57)  the entry's time and date, read or written through its directory's OFD
 *
 * CLOSE IS WHERE THE DISK IS MADE CONSISTENT, and it does it the blunt way: whatever it closed, it
 * then walks both buffer lists and flushes every buffer on them, of every drive ($fc58cc). What a
 * flush leaves is lopsided (`src/gemdos/fs_disk.c`): a DIRTY buffer is written and KEPT, clean; a
 * buffer that was already clean is EMPTIED. So after a close the cache holds exactly the sectors
 * that were waiting to be written.
 *
 * THE ENTRY IS REWRITTEN FROM THE OFD'S OWN BYTES. An OFD's time..length mirror the entry's
 * (`include/gemdos/fs.h`), time and date still in the disk's order and the cluster and length turned
 * round; so the write-back turns those two round IN THE OFD, writes the ten bytes from `OFD_TIME`
 * over the entry, and turns them back. Nothing clears `OFD_DIRTY`: a second close of the same OFD
 * writes the entry again.
 *
 * ---- WHAT HALTS ----------------------------------------------------------------------------------
 * Only what the engine under it halts on (a BIOS disk error, `src/gemdos/fs_disk.c`).
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_copy.h"
#include "gemdos/fs_file.h"
#include "gemdos/fs_io.h"
#include "gemdos/process.h"
#include "machine.h"
#include "recreate.h"

/* The date is the second of the two words `Fdatime` moves, as it is in the entry. */
#define STAMP_DATE            (DIRENT_DATE - DIRENT_TIME)

/* ---- $fc57ee: closing an OFD -------------------------------------------------------------------- */

/* The entry the OFD mirrors, rewritten through its directory's OFD: the cluster and the length
 * turned into the disk's order in place, ten bytes written from `OFD_TIME`, and turned back. A
 * DIRECTORY's entry is written with a length of 0 — the OFD's own ($7fffffff) is set aside for the
 * write and put back ($fc5842..$fc5860). The seek's answer is not looked at. */
static void write_back_entry(uint8_t *image, uint32_t ofd, uint16_t flags)
{
    uint32_t directory = be32(image + ofd + OFD_DIR_OFD);
    int directory_entry = (flags & OFD_CLOSE_DIRECTORY) != 0;
    uint32_t length;

    gemdos_ofd_seek(image, directory, be32(image + ofd + OFD_DIRPOS) + DIRENT_TIME);
    os_swap_word(image, ofd + OFD_STRTCL);
    os_swap_long(image, ofd + OFD_FILELN);
    length = be32(image + ofd + OFD_FILELN);
    if (directory_entry)
        wr32(image + ofd + OFD_FILELN, 0);
    gemdos_ofd_write(image, directory, DIRENT_TAIL_BYTES, ofd + OFD_TIME);
    if (directory_entry)
        wr32(image + ofd + OFD_FILELN, length);
    os_swap_word(image, ofd + OFD_STRTCL);
    os_swap_long(image, ofd + OFD_FILELN);
}

/* The OFD taken off its holding directory's list of open files: 1, or 0 when it is not on it. The
 * walk keeps the ADDRESS of the link that names the current OFD — the list head in the DND first,
 * then each OFD's own `OFD_LINK` — so the unlink is one store wherever the OFD is. */
static int unlink_from_directory(uint8_t *image, uint32_t ofd)
{
    uint32_t link_at = be32(image + ofd + OFD_DIR_DND) + DND_FILES;
    uint32_t open = be32(image + link_at);

    while (open != 0 && open != ofd) {
        link_at = open + OFD_LINK;
        open = be32(image + link_at);
    }
    if (open == 0)
        return 0;
    wr32(image + link_at, be32(image + open + OFD_LINK));
    return 1;
}

/* Both buffer lists, head to tail, every buffer flushed — whatever drive it holds, dirty or not. */
static void flush_every_buffer(uint8_t *image)
{
    uint16_t list;
    uint32_t bcb;

    for (list = 0; list < BCB_LIST_COUNT; list++)
        for (bcb = be32(image + gemdos_buffer_list_head(list)); bcb != 0;
             bcb = be32(image + bcb + BCB_LINK))
            gemdos_buffer_flush(image, bcb);
}

/* $fc57ee — close `ofd`: 0, or EINTRN when it had to be unlinked and was not on its list — which
 * answers BEFORE the flush, so that one arm leaves the cache as it was. */
uint32_t gemdos_ofd_close(uint8_t *image, uint32_t ofd, uint16_t flags)
{
    if (be16(image + ofd + OFD_FLAGS) & OFD_DIRTY)
        write_back_entry(image, ofd, flags);
    if ((flags == 0 || (flags & OFD_CLOSE_UNLINK)) && !unlink_from_directory(image, ofd))
        return GEMDOS_EINTRN;
    flush_every_buffer(image);
    return 0;
}

/* ---- $fc7824: deleting a directory entry --------------------------------------------------------- */

/* Every handle record naming `ofd` is closed if the RUNNING process owns it; one owned by anybody
 * else refuses the delete. 1 when every holder was the caller's.
 *
 * THE OFD IS CLOSED ONCE PER RECORD, NOT ONCE: two of the caller's handles on it close it twice, and
 * the second close is the EINTRN arm (it is already unlinked), which nothing reads. And the records
 * themselves are left naming it — the handles stay open on a freed entry. */
static int close_the_callers_handles(uint8_t *image, uint32_t ofd)
{
    int16_t index;

    for (index = 0; index < GEMDOS_HANDLE_COUNT; index++) {
        uint32_t descriptor = gemdos_descriptor_at(index);

        if (be32(image + descriptor + HANDLE_VALUE) != ofd)
            continue;
        if (be32(image + descriptor + HANDLE_OWNER) != gemdos_basepage(image))
            return 0;
        gemdos_ofd_close(image, ofd, 0);
    }
    return 1;
}

/* The entry's first cluster in the 68000's order: the ROM copies the little-endian word into its frame
 * and turns it round there with `$fc4f10` ($fc78a6, $fc78b0). */
static uint16_t first_cluster_of(const uint8_t *image, uint32_t dirent)
{
    return (uint16_t)(image[dirent + DIRENT_STRTCL] | image[dirent + DIRENT_STRTCL + 1] << 8);
}

/* The chain from `cluster` given back, one FAT entry at a time: read the successor, zero the entry.
 * It stops at 0 or at the WORD -1, and at nothing else — `$fc6038` answers -1 only for an EVEN
 * cluster's `$fff`, so any other end-of-chain value (`$ff8`..`$ffe`) is followed as a cluster number
 * (`src/gemdos/fs_io.c`). */
static void free_chain(uint8_t *image, uint16_t cluster, uint32_t dmd)
{
    while (cluster != 0 && (int16_t)cluster != GEMDOS_FAT_END_OF_CHAIN) {
        uint16_t next = (uint16_t)gemdos_fat_get(0, image, cluster, dmd);

        gemdos_fat_set(image, cluster, 0, dmd);
        cluster = next;
    }
}

/* The deleted mark, written from a byte of the frame (`$fc78fa` `move.b #$e5,-4(a6)`) whose ADDRESS
 * the transfer is handed — a host slot off target (`include/gemdos/gemdos.h`). Not the FAT routines'
 * frame word: the write can step a cluster and read the FAT, which claims that one underneath. */
static void write_deleted_mark(uint8_t *image, uint32_t directory)
{
    uint8_t mark;
    uint32_t mark_at = gemdos_host_slot_claim(DELETE_MARK, &mark);

    image[mark_at] = DIRENT_DELETED;
    gemdos_ofd_write(image, directory, 1, mark_at);
    gemdos_host_slot_release(DELETE_MARK);
}

/* $fc7824 — delete the entry `dirent` that sits at byte `position` of `dnd`'s directory: EACCDN if
 * another process has it open (with the caller's own opens on the way there already closed), else 0.
 *
 * `dirent` is only read for its first cluster; the mark goes through the directory's OFD at
 * `position`, and the directory's own close (flag 2) is what flushes it — and every other buffer. */
uint32_t gemdos_delete_entry(uint8_t *image, uint32_t dnd, uint32_t dirent, uint32_t position)
{
    uint32_t ofd;
    uint32_t directory;

    for (ofd = be32(image + dnd + DND_FILES); ofd != 0; ofd = be32(image + ofd + OFD_LINK))
        if (be32(image + ofd + OFD_DIRPOS) == position && !close_the_callers_handles(image, ofd))
            return GEMDOS_EACCDN;

    free_chain(image, first_cluster_of(image, dirent), be32(image + dnd + DND_DMD));

    directory = be32(image + dnd + DND_OFD);
    gemdos_ofd_seek(image, directory, position);
    write_deleted_mark(image, directory);
    gemdos_ofd_close(image, directory, OFD_CLOSE_DIRECTORY);
    return 0;
}

/* ---- $fc772e: Fdatime -------------------------------------------------------------------------- */

/* $fc772e ($57) — the time and date of the file `handle` has open, as two words at `stamp`: read
 * out of its entry when `set` is 0, written into it otherwise.
 *
 * THE BUFFER IS TURNED ROUND IN PLACE EITHER WAY. Reading, the two words arrive in the disk's order
 * and are swapped into the 68000's; writing, the caller's two words are swapped into the DISK's order
 * and written — and left like that, so an `Fdatime` set hands the caller's buffer back byte-swapped.
 *
 * NO RESULT OF ITS OWN. The ROM sets no D0: a read answers whatever the second swap left, which is
 * the transfer's count with its low word replaced by the swapped DATE; a write answers the directory
 * close's 0.
 *
 * THE OFD IS NOT CHECKED. A handle naming nothing makes it 0, and the ROM goes on to read the
 * "directory OFD" and "entry position" out of the exception vectors at 24 and 28 (see
 * `test_gemdos_fs_leaves2.py`); that arm HALTS here. */
uint32_t gemdos_fdatime(uint8_t *image, uint32_t stamp, int16_t handle, uint16_t set)
{
    uint32_t ofd = (uint32_t)gemdos_ofd_of_handle(image, handle);
    uint32_t directory;
    uint32_t result = 0;

    if (ofd == 0)
        recreate_not_reconstructed("GEMDOS: Fdatime of a handle that names no open file");
    directory = be32(image + ofd + OFD_DIR_OFD);
    gemdos_ofd_seek(image, directory, be32(image + ofd + OFD_DIRPOS) + DIRENT_TIME);
    if (set == 0)
        result = gemdos_ofd_read(image, directory, DIRENT_TIME_DATE_BYTES, stamp);
    os_swap_word(image, stamp);
    os_swap_word(image, stamp + STAMP_DATE);
    if (set == 0)
        return set_low_word(result, be16(image + stamp + STAMP_DATE));
    gemdos_ofd_write(image, directory, DIRENT_TIME_DATE_BYTES, stamp);
    return gemdos_ofd_close(image, directory, OFD_CLOSE_DIRECTORY);
}
