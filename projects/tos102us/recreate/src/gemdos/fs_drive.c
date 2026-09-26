/* fs_drive.c — the GEMDOS file system's DRIVE and PATH layer.
 *
 * A drive is LOGGED IN the first time a path names it: `$fc67de` asks BIOS `Getbpb` for the medium's
 * geometry, and `$fc53c0` turns that BPB into the drive's MEDIA DESCRIPTOR — the DMD, with the root
 * directory's node and two PSEUDO-FILES, one reading the root directory and one reading the FAT.
 * Everything above this layer (the buffer cache, the directory search, the file leaves) runs off
 * those four records; nothing below it knows what a path is.
 *
 * THE DMD'S ONE IDEA is the cluster-numbered address space `include/gemdos/fs.h` describes: data
 * clusters from 2, the root directory in the clusters just below 0, the FAT below that. The builder
 * is where those negative starting clusters and the three record biases that undo them are made.
 *
 * Then the PATH: `$fc68dc` reads an optional `X:` and a leading `\` and answers the node the walk
 * starts from, and `$fc5e08` peels one component at a time into an FCB name, with `$fc7e52` spotting
 * "." and "..". `$fc7e94` is here only because it is a string routine with nowhere better to live:
 * its one caller is the dispatcher's device-name arm.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_drive.h"
#include "gemdos/memory.h"
#include "gemdos/process.h"
#include "m68k_idioms.h"
#include "machine.h"

/* `m_fat16` is BPB_BFLAGS with every bit but this one dropped ($fc5448 `and.w #1`). */
#define BPB_BFLAGS_FAT16       0x0001

/* ---- the drive tables ---------------------------------------------------------------------------
 * Every index here is a SIGNED word, widened by the ROM's `movea.w` or `ext.w` before it is scaled,
 * and none is bounded: a drive out of range addresses outside its table, as the ROM does (and a node
 * outside its own, `gemdos_node_slot` in `include/gemdos/fs_drive.h`). */

static uint32_t dmd_slot(int16_t drive)
{
    return addr_add(GEMDOS_DMD_TABLE, (uint32_t)(int32_t)drive * DRIVE_TABLE_ENTRY_BYTES);
}

uint32_t gemdos_drive_dmd(const uint8_t *image, int16_t drive)
{
    return be32(image + dmd_slot(drive));
}

static uint32_t root_node_of(const uint8_t *image, int16_t drive)
{
    return be32(image + gemdos_drive_dmd(image, drive) + DMD_ROOT_DND);
}

uint32_t gemdos_current_directory(uint8_t *image, int16_t drive)
{
    return be32(image + gemdos_node_slot((int8_t)*gemdos_curdir_entry(image, drive)));
}

/* ---- $fc50fa: the four records ------------------------------------------------------------------ */

/* $fc50fa — the DMD, then the root DND hung off it, the root directory's OFD hung off THAT, and the
 * FAT's OFD back on the DMD; the DMD, or 0 with whatever was got returned to the pool.
 *
 * TWO THINGS THE ROM DOES THAT A TIDY VERSION WOULD NOT, both reproduced:
 *   * the DMD's pointer goes into the drive's table slot BEFORE it is tested ($fc511c), so a failed
 *     first request leaves the slot 0 — and a LATER failure leaves it naming a DMD that has just been
 *     handed back to the pool;
 *   * every pointer is stored into its parent before it is tested, so the parent carries the 0.
 * The frees run newest first: root OFD, root DND, DMD.
 */
uint32_t gemdos_dmd_alloc(uint8_t *image, int16_t drive)
{
    uint32_t dmd = gemdos_pool_get(image, DMD_POOL_CLASS);
    uint32_t root;

    wr32(image + dmd_slot(drive), dmd);
    if (dmd == 0)
        return 0;

    root = gemdos_pool_get(image, NODE_POOL_CLASS);
    wr32(image + dmd + DMD_ROOT_DND, root);
    if (root != 0) {
        uint32_t root_ofd = gemdos_pool_get(image, NODE_POOL_CLASS);

        wr32(image + root + DND_OFD, root_ofd);
        if (root_ofd != 0) {
            uint32_t fat_ofd = gemdos_pool_get(image, NODE_POOL_CLASS);

            wr32(image + dmd + DMD_FAT_OFD, fat_ofd);
            if (fat_ofd != 0)
                return dmd;
            gemdos_pool_free(image, be32(image + be32(image + dmd + DMD_ROOT_DND) + DND_OFD));
        }
        gemdos_pool_free(image, be32(image + dmd + DMD_ROOT_DND));
    }
    gemdos_pool_free(image, dmd);
    return 0;
}

/* ---- $fc53c0: the BPB into the drive ------------------------------------------------------------ */

static uint16_t fs_log2(uint16_t value)
{
    return (uint16_t)gemdos_fs_log2(0, value);
}

/* A log2 field and the mask beside it, the mask read out of the ROM's table by the log2 it has just
 * stored — so log2(0) = -1 reads the word below the table (`include/gemdos/fs.h`). */
static void set_log2_and_mask(uint8_t *image, uint32_t dmd, uint32_t log2_field, uint32_t mask_field,
                              uint16_t value)
{
    uint16_t log2 = fs_log2(value);

    wr16(image + dmd + log2_field, log2);
    wr16(image + dmd + mask_field, gemdos_bit_mask(image, log2));
}

/* `muls.w`: the whole signed 32-bit product of two words. */
static uint32_t muls_w(uint16_t multiplicand, uint16_t multiplier)
{
    return (uint32_t)((int32_t)(int16_t)multiplicand * (int32_t)(int16_t)multiplier);
}

/* How many clusters `sectors` fill: `(sectors + clsiz - 1) / clsiz` as the ROM computes it — a WORD
 * sum sign-extended and a `divs.w`, whose quotient is the low word ($fc54fe..$fc550a).
 *
 * A DIVISOR OF 0 takes the 68000's zero-divide exception (vector 5) and the ROM does not guard it; on
 * target the C's own `divs.w` takes the same one. Off target a C division by zero is undefined — a
 * SIGFPE on some hosts, which kills the pytest worker rather than failing a case — so the host build
 * REFUSES instead (`os_refused`, which the differential raises on): no case can pin this arm, and
 * none is let crash the run it is in. */
static uint16_t clusters_spanning(uint16_t sectors, uint16_t clsiz)
{
    int16_t rounded_up = (int16_t)(uint16_t)(sectors + clsiz - 1);

#ifdef RECREATE_HOST_DIFFERENTIAL
    if (clsiz == 0)
        return (uint16_t)os_refused(0);
#endif
    return (uint16_t)(int16_t)(rounded_up / (int16_t)clsiz);
}

/* $fc53c0 — build drive `drive`'s DMD out of the BPB at `bpb`; 0, or ENSMEM when the pool is spent.
 *
 * THE PSEUDO-CLUSTER LAYOUT: the root directory's first cluster is `-1 - its clusters`, the FAT's is
 * that minus ITS clusters, and each region's record bias is chosen so `cluster * clsiz + bias` lands
 * on the BIOS record the region really starts at. `fatrec` names the SECOND FAT copy, so the FAT's
 * bias is taken from it and the root directory's from `fatrec + fsiz`, the sector after it.
 *
 * The root directory is read as a pseudo-file of `rdlen` sectors and the FAT as one of `fsiz` —
 * one FAT copy, the second, which `src/gemdos/fs_disk.c`'s flush mirrors into the first.
 */
uint32_t gemdos_dmd_build(uint8_t *image, uint32_t bpb, int16_t drive)
{
    uint16_t recsiz = be16(image + bpb + BPB_RECSIZ);
    uint16_t clsiz = be16(image + bpb + BPB_CLSIZ);
    uint16_t rdlen = be16(image + bpb + BPB_RDLEN);
    uint16_t fsiz = be16(image + bpb + BPB_FSIZ);
    uint32_t dmd = gemdos_dmd_alloc(image, drive);
    uint32_t root, root_ofd, fat_ofd;
    uint16_t root_start;

    if (dmd == 0)
        return GEMDOS_ENSMEM;
    root = be32(image + dmd + DMD_ROOT_DND);
    root_ofd = be32(image + root + DND_OFD);
    fat_ofd = be32(image + dmd + DMD_FAT_OFD);

    wr16(image + dmd + DMD_FSIZ, fsiz);
    wr16(image + dmd + DMD_DRVNUM, (uint16_t)drive);
    wr32(image + root_ofd + OFD_DMD, dmd);
    wr32(image + root + DND_DMD, dmd);
    /* `clr.b (a0)` over a record the pool has just cleared: no run can see it, and it is kept. */
    image[root + DND_NAME] = 0;
    wr16(image + dmd + DMD_FAT16, be16(image + bpb + BPB_BFLAGS) & BPB_BFLAGS_FAT16);
    wr16(image + dmd + DMD_CLSIZ, clsiz);
    wr16(image + dmd + DMD_CLSIZB, be16(image + bpb + BPB_CLSIZB));
    wr16(image + dmd + DMD_RECSIZ, recsiz);
    wr16(image + dmd + DMD_NUMCL, be16(image + bpb + BPB_NUMCL));
    set_log2_and_mask(image, dmd, DMD_CLSIZ_LOG2, DMD_CLSIZ_MASK, clsiz);
    set_log2_and_mask(image, dmd, DMD_RECSIZ_LOG2, DMD_RECSIZ_MASK, recsiz);
    wr16(image + dmd + DMD_CLSIZB_LOG2, fs_log2(be16(image + dmd + DMD_CLSIZB)));

    wr32(image + root_ofd + OFD_FILELN, muls_w(rdlen, recsiz));
    root_start = (uint16_t)(-1 - (int16_t)clusters_spanning(rdlen, clsiz));
    wr16(image + root_ofd + OFD_STRTCL, root_start);
    wr16(image + root + DND_STRTCL, root_start);
    wr16(image + fat_ofd + OFD_STRTCL,
         (uint16_t)(be16(image + root + DND_STRTCL) - clusters_spanning(fsiz, clsiz)));
    wr32(image + fat_ofd + OFD_DMD, dmd);

    /* `fatrec` is read HERE, twice, as the ROM reads it ($fc5568, $fc5584) — after the stores above,
     * which a BPB lying over the records just cut from the pool would see. */
    wr16(image + dmd + DMD_RECOFF + BCB_TYPE_FAT * DMD_RECOFF_ENTRY_BYTES,
         (uint16_t)(be16(image + bpb + BPB_FATREC) - muls_w(be16(image + fat_ofd + OFD_STRTCL), clsiz)));
    wr16(image + dmd + DMD_RECOFF + BCB_TYPE_DIR * DMD_RECOFF_ENTRY_BYTES,
         (uint16_t)(be16(image + bpb + BPB_FATREC) + fsiz - muls_w(be16(image + root + DND_STRTCL), clsiz)));
    wr16(image + dmd + DMD_RECOFF + BCB_TYPE_DATA * DMD_RECOFF_ENTRY_BYTES,
         (uint16_t)(be16(image + bpb + BPB_DATREC) - (uint16_t)(clsiz * FIRST_DATA_CLUSTER)));

    wr32(image + fat_ofd + OFD_POS, FAT_OFD_START_POSITION);
    wr16(image + fat_ofd + OFD_CLOFF, FAT_OFD_START_POSITION);
    wr32(image + fat_ofd + OFD_FILELN, muls_w(fsiz, recsiz));
    return 0;
}

/* ---- $fc67de: logging a drive in ---------------------------------------------------------------- */

/* `asl.w` by the drive number: drive 16..63 has no bit at all and drive 64 is drive 0 again
 * ($fc67ec). */
static uint16_t drive_bit(int16_t drive)
{
    return asl_word_by(1, (uint16_t)drive);
}

/* $fc67de — make sure `drive` is logged in and that the running process has a directory on it; the
 * drive (sign-extended), or ERROR (-1) / ENSMEM.
 *
 * LOGGING IN is one `Getbpb` and one `$fc53c0`, and the drive's bit is set only when both succeed.
 * THE DIRECTORY is the process's p_curdir byte for the drive: kept if it is non-zero AND its node
 * table entry is non-zero, and otherwise replaced by the first node slot from 1 whose reference count
 * is 0, which is given the drive's ROOT node and a count of 1. The old byte's count is not dropped.
 * Forty slots all held is ERROR, with nothing stored.
 */
uint32_t gemdos_open_drive(uint8_t *image, int16_t drive)
{
    uint16_t bit = drive_bit(drive);
    int16_t node;
    int16_t slot;

    if ((be16(image + GEMDOS_DRIVES_OPENED) & bit) == 0) {
        uint32_t bpb = bios_getbpb(image, BIOS_RETURN_OPEN_DRIVE_GETBPB, (uint16_t)drive);

        if (bpb == 0)
            return GEMDOS_ERROR;
        if (gemdos_dmd_build(image, bpb, drive) != 0)
            return GEMDOS_ENSMEM;
        wr16(image + GEMDOS_DRIVES_OPENED, be16(image + GEMDOS_DRIVES_OPENED) | bit);
    }

    node = (int8_t)*gemdos_curdir_entry(image, drive);
    if (node != 0 && be32(image + gemdos_node_slot(node)) != 0)
        return sign_ext16((uint16_t)drive);

    slot = gemdos_free_directory_slot(image);
    if (slot == GEMDOS_DIRECTORY_NODE_COUNT)
        return GEMDOS_ERROR;
    image[GEMDOS_CURDIR_REFCOUNTS + slot]++;
    wr32(image + gemdos_node_slot(slot), root_node_of(image, drive));
    *gemdos_curdir_entry(image, drive) = (uint8_t)slot;
    return sign_ext16((uint16_t)drive);
}

/* ---- $fc68dc: where a path starts --------------------------------------------------------------- */

/* $fc68dc — the directory node the path at `*path_pointer` starts in, with `*path_pointer` advanced
 * past the `X:` and the leading `\` it consumed; 0 (and the pointer untouched) if the drive will not
 * open.
 *
 * The prefix is `gemdos_drive_of_prefix`'s (`include/gemdos/fs_drive.h`): `1:` is drive -16, which
 * `$fc67de` then asks the BIOS about, and an empty path reads one byte past its NUL.
 */
uint32_t gemdos_path_start(uint8_t *image, uint32_t path_pointer)
{
    uint32_t text = be32(image + path_pointer);
    int16_t drive = gemdos_drive_of_prefix(image, &text);
    uint32_t node;

    if ((int32_t)gemdos_open_drive(image, drive) < 0)
        return 0;

    if (image[text] == PATH_SEPARATOR) {
        node = root_node_of(image, drive);
        text++;
    } else {
        node = gemdos_current_directory(image, drive);
    }
    wr32(image + path_pointer, text);
    return node;
}

/* ---- the component layer ------------------------------------------------------------------------ */

/* $fc7e52 — is the component at `name` empty (1), "." (-1), ".." (-2), or anything else (0)?
 *
 * A dot COUNTS only when the character after it is `terminator`: the loop takes up to two dots, and
 * after each asks whether the next byte ends the component. So "." and ".." need the terminator
 * right after them, "..." is an ordinary name, and a terminator of '.' makes ".." answer -1. Only the
 * terminator's LOW BYTE is compared (`cmp.b 13(a6)`). Every answer but "empty" is a `move.w`/`clr.w`.
 */
uint32_t gemdos_dot_name(uint32_t entry_d0, const uint8_t *image, uint32_t name, uint16_t terminator)
{
    uint16_t dots;

    if (image[name] == '\0')
        return DOT_NAME_EMPTY;
    for (dots = 1; dots <= 2; dots++) {
        if (image[name++] != NAME_DOT)
            break;
        if (image[name] == (uint8_t)terminator)
            return set_low_word(entry_d0, (uint16_t)-dots);
    }
    return set_low_word(entry_d0, 0);
}

/* $fc5e08 — the next component of `path` (up to a `\` or the NUL) as an FCB name at `fcb`; its
 * length, or -1/-2 for "."/"..", or 0 for "nothing to take".
 *
 * THE LAST COMPONENT IS TAKEN ONLY WHEN `take_tail` SAYS SO: without it, a component ending at the
 * NUL answers 0 without being looked at — which is how the directory walk stops one short of the
 * file name. A component of length 0 (the path is at a `\`) builds no FCB.
 *
 * WHICH HALF OF D0 COMES BACK is the three paths' own: the tail and the dot answers are `clr.w`/
 * `move.w` over the caller's high half; after a BUILT name it is 0, because `$fc5d28` ends in a
 * `moveq` (its padding character); and an empty component answers `$fc7e52`'s D0 — whole for
 * "empty" (`moveq #1`), the caller's high half otherwise.
 */
uint32_t gemdos_split_path(uint32_t entry_d0, uint8_t *image, uint32_t path, uint32_t fcb,
                           uint16_t take_tail)
{
    uint32_t end = path;
    uint16_t length = 0;
    uint32_t result;

    while (image[end] != '\0' && image[end] != PATH_SEPARATOR) {
        end++;
        length++;
    }
    if (image[end] == '\0' && take_tail == 0)
        return set_low_word(entry_d0, 0);

    result = gemdos_dot_name(entry_d0, image, path, (uint16_t)sign_ext8(image[end]));
    if ((int16_t)result < 0)
        return result;
    if (length != 0) {
        gemdos_build_fcb_name(image, path, fcb);
        result = 0;     /* ...its closing `moveq` */
    }
    return set_low_word(result, length);
}

/* $fc7e94 — are the `count` bytes at `left` and `right` equal? 1, or 0 over the caller's high half.
 * No NUL stops it, and the count is a word decremented to 0, so a count of 0 compares nothing. */
uint32_t gemdos_strneq(uint32_t entry_d0, const uint8_t *image, uint16_t count, uint32_t left,
                       uint32_t right)
{
    while (count-- != 0)
        if (image[left++] != image[right++])
            return set_low_word(entry_d0, 0);
    return 1;
}
