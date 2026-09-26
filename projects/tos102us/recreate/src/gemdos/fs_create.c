/* fs_create.c — the GEMDOS file system's CREATE layer: a directory entry made, and a directory made and
 * unmade.
 *
 *   $fc71b6  create        the path's directory found, an existing entry of the name DELETED, a free slot
 *                          found (the directory grown by a cluster when it has none), the entry written
 *                          and flushed, and then OPENED — the handle is the answer
 *   $fc719a  Fcreate ($3c) `create` with the attribute's subdirectory bit masked off
 *   $fc792a  Ddelete ($3a) an EMPTY directory's DND taken off its parent's list and freed, and its
 *                          entry deleted through `$fc7824`
 *   $fc73ce  Dcreate ($39) `create` with the subdirectory bit, then a DND, an OFD and a first cluster
 *                          for the new directory, `.` and `..` written into it — and the handle `create`
 *                          opened closed again, by hand
 *
 * AN EXISTING ENTRY IS NOT TRUNCATED, IT IS DELETED: `$fc7824` frees its whole chain and marks it `$e5`,
 * and the free-slot search then starts AT that entry, so the new one lands in the same slot. Only a
 * read-only entry or a subdirectory refuses (EACCDN).
 *
 * THE ROOT CANNOT GROW. A directory with no free slot is extended by one cluster through `$fc60f2` — but
 * only when its OFD's current cluster is not negative, and the root's pseudo-clusters are: a full root
 * is EACCDN, and so is a full disk.
 *
 * ---- WHAT HALTS ----------------------------------------------------------------------------------
 * `Ddelete` of a directory its parent's child list does not hold — the root, whose parent is 0, above
 * all: the ROM walks on through address 0 into the exception vectors and never returns. Below that,
 * only what the engine halts on (a BIOS disk error, `src/gemdos/fs_disk.c`).
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_copy.h"
#include "gemdos/fs_create.h"
#include "gemdos/fs_dir.h"
#include "gemdos/fs_drive.h"
#include "gemdos/fs_file.h"
#include "gemdos/fs_io.h"
#include "gemdos/fs_records.h"
#include "gemdos/memory.h"
#include "gemdos/process.h"
#include "machine.h"
#include "recreate.h"

/* The attribute bits that refuse an existing entry: read-only or a subdirectory ($fc7242 `and.w #17`). */
#define ATTR_NOT_REPLACEABLE  (GEMDOS_ATTR_READ_ONLY | GEMDOS_ATTR_SUBDIR)

/* What `Fcreate` keeps of its caller's attribute: the low byte, less the subdirectory bit. */
#define FCREATE_ATTR_MASK     (0xff & ~GEMDOS_ATTR_SUBDIR)

/* The DOS-reserved bytes between an entry's attribute and its time, which `create` clears one at a time
 * ($fc72f4 `cmpi.w #10`). */
#define DIRENT_RESERVED       (DIRENT_ATTR + 1)
#define DIRENT_RESERVED_BYTES (DIRENT_TIME - DIRENT_RESERVED)

/* `.` and `..`, the first two entries of every subdirectory: a scan for its contents starts past them
 * ($fc796e `move.l #64`). */
#define DOT_ENTRIES_BYTES     (2 * DIRENT_BYTES)

/* The part of the directory OFD `Dcreate` copies over the file OFD `create` opened, before closing that
 * ($fc7588 `move.w #50`): every field up to and including `OFD_MODE`. */
#define DCREATE_OFD_COPY_BYTES (OFD_MODE + OFD_MODE_BYTES)

/* `$fc71b6`'s free-slot search name: the TEXT "\xe5" and its NUL, which `$fc5d28` pads into the FCB
 * whose first byte takes `$fc5c9a`'s deleted-entry arm ($fc71be `move.b #$e5`, $fc71c4 `clr.b`). */
#define FREE_SLOT_NAME_BYTES  2

/* Both frame locals `create` hands on stand in off target as host slots exactly as wide. */
_Static_assert(GEMDOS_HOST_SLOT_CREATE_FREE_NAME_BYTES == FREE_SLOT_NAME_BYTES
               && GEMDOS_HOST_SLOT_CREATE_FCB_BYTES == DIRENT_NAME_BYTES,
               "a host slot narrower or wider than the frame local it stands in for");

/* ---- $fc71b6, create --------------------------------------------------------------------------- */

/* The entry at byte `position` of the directory `ofd` reads, as a pointer into the cache. */
static uint32_t entry_at(uint8_t *image, uint32_t ofd, uint32_t position)
{
    gemdos_ofd_seek(image, ofd, position);
    return gemdos_next_entry(image, ofd);
}

/* A word into an entry in the disk's (little-endian) order: stored as the 68000 holds it, then turned
 * round in place. */
static void store_disk_word(uint8_t *image, uint32_t at, uint16_t value)
{
    wr16(image + at, value);
    os_swap_word(image, at);
}

/* The first free slot of `dnd`'s directory from `*position` — a deleted entry or the end-of-directory
 * one — searched for by the name "\xe5" out of a frame local (a host slot off target). When there is
 * none the directory is grown by a zeroed cluster and searched again from its start. 0 when it cannot
 * grow: the root (a negative cluster) or a full disk.
 *
 * `*position` is left where the search left it: one entry past the slot. */
static uint32_t free_slot(uint8_t *image, uint32_t dnd, uint32_t directory, int32_t *position)
{
    uint8_t name_local[FREE_SLOT_NAME_BYTES];
    uint32_t name = gemdos_host_slot_claim(CREATE_FREE_NAME, name_local);
    uint32_t slot;

    image[name] = DIRENT_DELETED;
    image[name + 1] = '\0';
    while ((slot = gemdos_dir_search(image, dnd, name, GEMDOS_ATTR_ANY, position)) == 0) {
        if ((int16_t)be16(image + directory + OFD_CURCL) < 0
            || (uint16_t)gemdos_next_cluster(image, directory, 1) != 0)
            break;
        gemdos_dir_zero_cluster(image, dnd);
        *position = 0;
    }
    gemdos_host_slot_release(CREATE_FREE_NAME);
    return slot;
}

/* The new entry in the cached slot: `attr`'s low byte, the reserved bytes cleared, the clock in the
 * disk's order, no cluster and no length — and then its NAME written through the directory's OFD from
 * the FCB `$fc5d28` builds in a frame local (a host slot off target), which is what dirties the sector.
 * The directory's close (flag 2) flushes it, and every other buffer. */
static void write_new_entry(uint8_t *image, uint32_t directory, uint32_t slot, uint32_t position,
                            uint32_t tail, uint16_t attr)
{
    uint8_t fcb_local[DIRENT_NAME_BYTES];
    uint32_t fcb = gemdos_host_slot_claim(CREATE_FCB, fcb_local);
    int16_t reserved;

    gemdos_build_fcb_name(image, tail, fcb);
    image[slot + DIRENT_ATTR] = (uint8_t)attr;
    for (reserved = 0; reserved < DIRENT_RESERVED_BYTES; reserved++)
        image[slot + DIRENT_RESERVED + (uint32_t)reserved] = 0;
    store_disk_word(image, slot + DIRENT_TIME, be16(image + GEMDOS_TIME));
    store_disk_word(image, slot + DIRENT_DATE, be16(image + GEMDOS_DATE));
    wr16(image + slot + DIRENT_STRTCL, 0);
    wr32(image + slot + DIRENT_FILELN, 0);
    gemdos_ofd_seek(image, directory, position);
    gemdos_ofd_write(image, directory, DIRENT_NAME_BYTES, fcb);
    gemdos_host_slot_release(CREATE_FCB);
    gemdos_ofd_close(image, directory, OFD_CLOSE_DIRECTORY);
}

/* $fc71b6 — make the entry `name` names in its directory, with attribute `attr`'s low byte, and open
 * it: the handle (sign-extended), or EPTHNF for a path that leaves the tree or ends in "", "." or "..",
 * EACCDN for a read-only or subdirectory entry of the name or a directory that cannot grow, ENSMEM,
 * or `$fc6f5c`'s ENHNDL — which comes AFTER the entry is on the disk.
 *
 * `$fc7824`'S ANSWER IS NOT READ. An entry another process holds open is not deleted (EACCDN), and the
 * free-slot search then starts at it, passes it and takes the next free slot: a SECOND entry of the
 * same name. And a search that cannot make a DND for a subdirectory it passes reads as a miss, so a
 * spent pool turns a root with free slots into a "full" one (EACCDN).
 *
 * THE MODE IS READ FROM THE SLOT THE SEARCH FOUND, not the entry the open is handed: after the flush
 * the ROM re-reads the entry for `$fc6f5c` and tests the read-only bit through the pointer it already
 * had ($fc737e `btst #0,11(a4)`). A kept buffer makes the two the same address. */
uint32_t gemdos_create(uint8_t *image, uint32_t name, uint16_t attr)
{
    uint32_t tail;
    uint32_t dnd = gemdos_find_dir(image, name, &tail, GEMDOS_WALK_TO_THE_NAME);
    uint32_t directory;
    int32_t position = 0;
    uint32_t slot;
    uint32_t entry;
    uint32_t opened;

    if (dnd == 0 || (uint16_t)gemdos_dot_name(0, image, tail, 0) != 0)
        return GEMDOS_EPTHNF;
    directory = be32(image + dnd + DND_OFD);
    if (directory == 0) {
        directory = gemdos_ofd_new(image, dnd);
        wr32(image + dnd + DND_OFD, directory);
        if (directory == 0)
            return GEMDOS_ENSMEM;
    }

    slot = gemdos_dir_search(image, dnd, tail, GEMDOS_ATTR_ANY, &position);
    if (slot != 0) {
        if (image[slot + DIRENT_ATTR] & ATTR_NOT_REPLACEABLE)
            return GEMDOS_EACCDN;
        position -= ENTRY_BEHIND_POSITION;
        gemdos_delete_entry(image, dnd, slot, (uint32_t)position);
    } else {
        position = 0;
    }
    slot = free_slot(image, dnd, directory, &position);
    if (slot == 0)
        return GEMDOS_EACCDN;
    position -= ENTRY_BEHIND_POSITION;

    write_new_entry(image, directory, slot, (uint32_t)position, tail, attr);
    entry = entry_at(image, directory, (uint32_t)position);
    opened = gemdos_handle_alloc(image, entry, dnd,
                                 image[slot + DIRENT_ATTR] & GEMDOS_ATTR_READ_ONLY ? OPEN_MODE_READ : OPEN_MODE_READ_WRITE);
    if ((int32_t)opened < 0)
        return opened;
    directory = (uint32_t)gemdos_ofd_of_handle(image, (int16_t)opened);
    wr16(image + directory + OFD_FLAGS, (uint16_t)(be16(image + directory + OFD_FLAGS) | OFD_DIRTY));
    return sign_ext16((uint16_t)opened);
}

/* $fc719a ($3c) — `create` over the caller's attribute BYTE with its subdirectory bit masked off: a file,
 * never a directory, whatever the caller asked for. The ROM sign-extends the byte and then masks the
 * word with $00ef ($fc71a2 `ext.w`, $fc71a6 `andi.w #239`), which leaves exactly the byte's other bits. */
uint32_t gemdos_fcreate(uint8_t *image, uint32_t name, uint16_t attr)
{
    return gemdos_create(image, name, attr & FCREATE_ATTR_MASK);
}

/* ---- $fc792a, Ddelete -------------------------------------------------------------------------- */

/* The address of the link that names `dnd` on its parent's child list: the parent's DND_CHILD, or a
 * sibling's DND_SIBLING. THE ROM'S WALK HAS NO END TEST — it follows links until one names `dnd`, so
 * the root (no parent: the walk starts at address 28, in the exception vectors) and a DND its parent
 * does not list never come back. Those two HALT here. */
static uint32_t link_naming(const uint8_t *image, uint32_t dnd)
{
    uint32_t parent = be32(image + dnd + DND_PARENT);
    uint32_t link_at = parent + DND_CHILD;
    uint32_t child;

    if (parent == 0)
        recreate_not_reconstructed("GEMDOS: Ddelete of the root — a child walk from address 0");
    for (child = be32(image + link_at); child != dnd; child = be32(image + link_at)) {
        if (child == 0)
            recreate_not_reconstructed("GEMDOS: Ddelete of a DND its parent does not list");
        link_at = child + DND_SIBLING;
    }
    return link_at;
}

/* Is the directory `ofd` reads empty — nothing past `.` and `..` but deleted entries, up to its
 * end-of-directory entry or the end of its chain? */
static int is_empty_directory(uint8_t *image, uint32_t ofd)
{
    uint32_t entry;

    gemdos_ofd_seek(image, ofd, DOT_ENTRIES_BYTES);
    do
        entry = gemdos_next_entry(image, ofd);
    while (entry != 0 && image[entry] == DIRENT_DELETED);
    return entry == 0 || image[entry] == 0;
}

/* $fc792a ($3a) — delete the directory `path` names: EPTHNF for a path that leaves the tree (or names a
 * file), EACCDN for one with anything in it, EINTRN for one with open files or child DNDs — and
 * otherwise its DND off its parent's list, its OFD and DND back to the pool, and `$fc7824` over its
 * entry.
 *
 * NOTHING ASKS WHETHER IT IS A PROCESS'S CURRENT DIRECTORY: `p_curdir` and the node table go on naming
 * the freed DND.
 *
 * AN OFD MADE HERE IS NEVER KEPT OR FREED. A DND with no OFD gets one from `$fc5c3c` for the emptiness
 * scan, and it is not stored on the DND — so it leaks. One the DND had is freed, and its entry position
 * and holding directory are then read out of the freed record ($fc7a1e; the pool rewrites only its
 * link). */
uint32_t gemdos_ddelete(uint8_t *image, uint32_t path)
{
    uint32_t tail;
    uint32_t dnd = gemdos_find_dir(image, path, &tail, GEMDOS_WALK_THE_WHOLE_PATH);
    uint32_t ofd;
    uint32_t link_at;
    uint32_t parent;
    uint32_t position;
    uint32_t holding;

    if (dnd == 0)
        return GEMDOS_EPTHNF;
    ofd = be32(image + dnd + DND_OFD);
    if (ofd == 0) {
        ofd = gemdos_ofd_new(image, dnd);
        if (ofd == 0)
            return GEMDOS_ENSMEM;
    }
    if (!is_empty_directory(image, ofd))
        return GEMDOS_EACCDN;

    link_at = link_naming(image, dnd);
    if (be32(image + dnd + DND_FILES) != 0 || be32(image + dnd + DND_CHILD) != 0)
        return GEMDOS_EINTRN;
    wr32(image + link_at, be32(image + dnd + DND_SIBLING));
    if (be32(image + dnd + DND_OFD) != 0)
        gemdos_pool_free(image, be32(image + dnd + DND_OFD));
    parent = be32(image + dnd + DND_PARENT);
    gemdos_pool_free(image, dnd);

    position = be32(image + ofd + OFD_DIRPOS);
    holding = be32(image + ofd + OFD_DIR_OFD);
    return gemdos_delete_entry(image, parent, entry_at(image, holding, position), position);
}

/* ---- $fc73ce, Dcreate -------------------------------------------------------------------------- */

/* The file OFD `create` opened, closed by hand: written back and unlinked (flags 6, so the entry's
 * length is written as 0), freed, and its handle record released. */
static void close_created(uint8_t *image, uint32_t file, int16_t handle)
{
    gemdos_ofd_close(image, file, OFD_CLOSE_DIRECTORY | OFD_CLOSE_UNLINK);
    gemdos_pool_free(image, file);
    gemdos_release_descriptor(image, gemdos_descriptor_of(handle));
}

/* One of the two entries a new directory opens with: its first 22 bytes from the ROM's template
 * (`GEMDOS_DOT_ENTRY_HEAD` or `GEMDOS_DOT_DOT_ENTRY_HEAD`), the subdirectory attribute, the clock
 * words — NOT turned round, unlike `create`'s ($fc74f8 plain `move.w`) — `cluster` in the disk's order
 * and length 0. */
static void write_dot_entry(uint8_t *image, uint32_t entry, uint32_t head, uint16_t cluster)
{
    gemdos_bcopy(image, DIRENT_TIME, head, entry);
    image[entry + DIRENT_ATTR] = GEMDOS_ATTR_SUBDIR;
    wr16(image + entry + DIRENT_TIME, be16(image + GEMDOS_TIME));
    wr16(image + entry + DIRENT_DATE, be16(image + GEMDOS_DATE));
    store_disk_word(image, entry + DIRENT_STRTCL, cluster);
    wr32(image + entry + DIRENT_FILELN, 0);
}

/* $fc73ce ($39) — make the directory `path` names: 0, or `create`'s error, or ENSMEM (the entry left
 * made and its handle open), or EACCDN when no cluster can be had — after `Ddelete` of the path undoes
 * the entry.
 *
 * THE NEW DIRECTORY'S DND AND OFD come from its entry, re-read through the holding directory at the
 * position the file OFD recorded. Its first cluster is allocated through its own OFD, zeroed through
 * the cache, and `.` (that cluster) and `..` (the holding directory's first cluster, 0 for the root's
 * negative one) written into it.
 *
 * THE FILE OFD IS THEN OVERWRITTEN WITH THE DIRECTORY OFD'S FIRST 50 BYTES and closed with flags 6.
 * The entry is written back with the new cluster — and the UNLINK walks the holding directory's open
 * files with the directory OFD's LINK, 0: the file OFD was the head of that list (`$fc6fdc` pushes on
 * the front), so every OFD opened in the directory before it drops off the list with it. */
uint32_t gemdos_dcreate(uint8_t *image, uint32_t path)
{
    uint32_t created = gemdos_create(image, path, GEMDOS_ATTR_SUBDIR);
    int16_t handle = (int16_t)created;
    uint32_t file;
    uint32_t entry;
    uint32_t dnd;
    uint32_t directory;
    uint32_t first;
    int16_t parent_cluster;

    if (handle < 0)
        return created;
    file = (uint32_t)gemdos_ofd_of_handle(image, handle);
    entry = entry_at(image, be32(image + file + OFD_DIR_OFD), be32(image + file + OFD_DIRPOS));
    dnd = gemdos_dnd_new(image, be32(image + file + OFD_DIR_DND), entry);
    if (dnd == 0)
        return GEMDOS_ENSMEM;
    directory = gemdos_ofd_new(image, dnd);
    wr32(image + dnd + DND_OFD, directory);
    if (directory == 0)
        return GEMDOS_ENSMEM;
    if ((uint16_t)gemdos_next_cluster(image, directory, 1) != 0) {
        close_created(image, file, handle);
        gemdos_ddelete(image, path);
        return GEMDOS_EACCDN;
    }

    first = gemdos_dir_zero_cluster(image, dnd);
    write_dot_entry(image, first, GEMDOS_DOT_ENTRY_HEAD, be16(image + directory + OFD_STRTCL));
    parent_cluster = (int16_t)be16(image + be32(image + file + OFD_DIR_OFD) + OFD_STRTCL);
    write_dot_entry(image, first + DIRENT_BYTES, GEMDOS_DOT_DOT_ENTRY_HEAD,
                    (uint16_t)(parent_cluster < 0 ? 0 : parent_cluster));

    gemdos_bcopy(image, DCREATE_OFD_COPY_BYTES, directory, file);
    wr16(image + file + OFD_FLAGS, (uint16_t)(be16(image + file + OFD_FLAGS) | OFD_DIRTY));
    close_created(image, file, handle);
    return 0;
}
