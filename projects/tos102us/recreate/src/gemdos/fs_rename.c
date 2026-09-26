/* fs_rename.c — `Frename` ($56, `$fc7af0`): a file given another name, in its own directory or another
 * one of its drive.
 *
 * IT IS BUILT OUT OF LEAVES. After its own checks it OPENS the file (`Fopen`, mode 2), works on the
 * entry through the open file's DIRECTORY OFD, and — for a move — CREATES the new entry (`Fcreate`) and
 * closes both handles (`Fclose`): the entry points a program calls, with everything they do to the
 * handle table and the OFD lists, not the routines under them.
 *
 * TWO SHAPES, chosen by whether the two paths' directories are the same DND:
 *
 *   in place   the entry's eleven name bytes overwritten with the new FCB name — nothing else moves.
 *   a move     the old entry marked `$e5`, WITHOUT freeing its chain; the new one made by `Fcreate`
 *              with the old attribute byte, and the old entry's time, date, first cluster and length
 *              (its last ten bytes) written over what `Fcreate` put there. The chain changes hands.
 *
 * WHAT IS CHECKED, in the ROM's order: the new name must not already be there — searched by `sfirst`
 * with no attribute bits, which it widens to read-only and archive, so a HIDDEN or SYSTEM file, or a
 * directory, of the new name is not seen (EACCDN otherwise); both paths' directories must be there
 * (EPTHNF); both must be on the same drive — the two DMDs' drive WORDS compared (ENSAME); and `Fopen`
 * must open the old name read-write (EFILNF for a missing file or a directory, EACCDN for a read-only
 * file, ENHNDL).
 *
 * `Fcreate`'S ANSWER IS NOT LOOKED AT. A move onto a name `Fcreate` refuses (a subdirectory's), or with
 * no handle left for the new file, goes on with the negative answer as a handle — `$fc51c0` then reads a
 * byte below the process's `p_uft` (EACCDN and ENHNDL land in `p_tlen`) and names whatever record that
 * picks. A byte of 0 picks record 0, which is the old file's own when `Fopen` took the first free one:
 * the tail goes back where it came from, and the rename answers 0 with the file's entry `$e5` and its
 * chain held by nothing. When ANOTHER open file holds record 0 it is that file's: the moved file's tail
 * lands in the other file's entry, the other file's OFD is made clean under its owner's handle, and its
 * directory is closed. A running program's text of 64 KB or more makes the byte non-zero, and the record
 * whatever it picks. Reproduced as the ROM does it.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_create.h"
#include "gemdos/fs_dir.h"
#include "gemdos/fs_file.h"
#include "gemdos/fs_io.h"
#include "gemdos/fs_open.h"
#include "gemdos/fs_rename.h"
#include "gemdos/process.h"
#include "machine.h"

/* The one frame local `Frename` hands on, `-20(a6)`: the `$e5` mark, then the entry's ten tail bytes,
 * or the new FCB name — as wide as the widest of the three. */
#define ENTRY_BUFFER_BYTES    DIRENT_NAME_BYTES
#define DELETE_MARK_BYTES     1
_Static_assert(DIRENT_TAIL_BYTES <= ENTRY_BUFFER_BYTES, "the entry's tail does not fit the name buffer");
_Static_assert(GEMDOS_HOST_SLOT_RENAME_ENTRY_BYTES == ENTRY_BUFFER_BYTES,
               "a host slot narrower or wider than the frame local it stands in for");

/* The drive a directory is on: its DMD's drive word. */
static uint16_t drive_of(const uint8_t *image, uint32_t dnd)
{
    return be16(image + be32(image + dnd + DND_DMD) + DMD_DRVNUM);
}

/* The entry the directory OFD `directory` holds at `position`: its attribute byte (sign-extended, as the
 * word `Fcreate` is handed), then `$e5` over its first byte and its ten tail bytes read into `buffer`. */
static uint16_t take_entry(uint8_t *image, uint32_t directory, uint32_t position, uint32_t buffer)
{
    uint32_t entry;
    uint16_t attr;

    entry = gemdos_next_entry(image, directory);
    attr = (uint16_t)sign_ext8(image[entry + DIRENT_ATTR]);
    gemdos_ofd_seek(image, directory, position);
    gemdos_ofd_write(image, directory, DELETE_MARK_BYTES, buffer);
    gemdos_ofd_seek(image, directory, position + DIRENT_TIME);
    gemdos_ofd_read(image, directory, DIRENT_TAIL_BYTES, buffer);
    return attr;
}

/* The move's second half: `new` made by `Fcreate` with `attr`, the ten tail bytes in `buffer` written
 * over its entry, its OFD's dirty bit cleared so the close does not write them back, and the handle
 * closed — then its directory closed too, through the OFD `Fclose` has just given back to the pool
 * ($fc7c74 reads `24(a3)` after the free; the pool rewrites only a record's link). */
static void make_entry(uint8_t *image, uint32_t new, uint16_t attr, uint32_t buffer)
{
    int16_t handle = (int16_t)gemdos_fcreate(image, new, attr);
    uint32_t file = (uint32_t)gemdos_ofd_of_handle(image, handle);

    gemdos_ofd_seek(image, be32(image + file + OFD_DIR_OFD), be32(image + file + OFD_DIRPOS) + DIRENT_TIME);
    gemdos_ofd_write(image, be32(image + file + OFD_DIR_OFD), DIRENT_TAIL_BYTES, buffer);
    wr16(image + file + OFD_FLAGS, (uint16_t)(be16(image + file + OFD_FLAGS) & ~OFD_DIRTY));
    gemdos_fclose(image, handle);
    gemdos_ofd_close(image, be32(image + file + OFD_DIR_OFD), OFD_CLOSE_DIRECTORY);
}

/* $fc7af0 ($56) — rename `old` to `new`: see the top of the file. The answer after a rename is the
 * directory close's, which is 0 — its flags (2) never unlink. */
uint32_t gemdos_frename(uint8_t *image, uint16_t reserved, uint32_t old, uint32_t new)
{
    uint8_t buffer_local[ENTRY_BUFFER_BYTES];
    uint32_t old_tail, new_tail;
    uint32_t old_dnd, new_dnd;
    uint32_t opened, closed;
    uint32_t file, directory, position;
    uint32_t buffer;

    (void)reserved;
    if (gemdos_sfirst(image, new, GEMDOS_SFIRST_PLAIN_FILES, GEMDOS_SFIRST_NO_DTA) == 0)
        return GEMDOS_EACCDN;
    old_dnd = gemdos_find_dir(image, old, &old_tail, GEMDOS_WALK_TO_THE_NAME);
    if (old_dnd == 0)
        return GEMDOS_EPTHNF;
    new_dnd = gemdos_find_dir(image, new, &new_tail, GEMDOS_WALK_TO_THE_NAME);
    if (new_dnd == 0)
        return GEMDOS_EPTHNF;
    if (drive_of(image, old_dnd) != drive_of(image, new_dnd))
        return GEMDOS_ENSAME;
    opened = gemdos_fopen(image, old, OPEN_MODE_READ_WRITE);
    if ((int32_t)opened < 0)
        return opened;

    file = (uint32_t)gemdos_ofd_of_handle(image, (int16_t)opened);
    directory = be32(image + file + OFD_DIR_OFD);
    position = be32(image + file + OFD_DIRPOS);
    buffer = gemdos_host_slot_claim(RENAME_ENTRY, buffer_local);
    image[buffer] = DIRENT_DELETED;
    gemdos_ofd_seek(image, directory, position);
    if (old_dnd != new_dnd) {
        make_entry(image, new, take_entry(image, directory, position, buffer), buffer);
    } else {
        gemdos_build_fcb_name(image, new_tail, buffer);
        gemdos_ofd_write(image, directory, DIRENT_NAME_BYTES, buffer);
    }
    gemdos_host_slot_release(RENAME_ENTRY);

    closed = gemdos_fclose(image, (int16_t)opened);
    if ((int32_t)closed < 0)
        return closed;
    return gemdos_ofd_close(image, directory, OFD_CLOSE_DIRECTORY);
}
