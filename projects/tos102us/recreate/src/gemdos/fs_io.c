/* fs_io.c — the GEMDOS file system's I/O ENGINE ($fc5e6a..$fc65a0, $fc7cce..$fc7e50).
 *
 * WHAT THE ENGINE IS. An open file is an OFD (`include/gemdos/fs.h`): a first cluster, a length, and
 * a CURSOR — the byte position, the cluster it is in, that cluster's first record and the byte
 * offset inside it. Four routines keep the cursor and one moves bytes under it:
 *
 *   $fc7d2a  seek          put the cursor at a position, walking the chain to find its cluster
 *   $fc60f2  next_cluster  step the cursor to the next cluster — allocating one on a write
 *   $fc61d6  advance       move the position on after bytes moved, growing the length past the end
 *   $fc6038  fat_get       ...and the FAT they walk, read and written as a PSEUDO-FILE
 *   $fc5f44  fat_set
 *   $fc6218  xfer          the transfer itself
 *
 * THE FAT IS A FILE, and that is what makes this one component. The DMD's `DMD_FAT_OFD` is an OFD
 * over the FAT whose clusters are NEGATIVE pseudo-clusters, so `fat_get` is a seek and a two-byte
 * read of it through the SAME `xfer` a user's `Fread` takes — and `xfer` steps clusters through
 * `next_cluster`, which calls `fat_get`. It terminates because `fat_get` answers `cl + 1` for a
 * negative cluster without reading anything: the FAT OFD's chain is arithmetic, not data.
 *
 * THE CURSOR'S ONE CONVENTION, which every routine here keeps and nothing states: a position on a
 * CLUSTER BOUNDARY is held as the END of the cluster before it (`OFD_CLOFF` 0 — or `m_clsizb`,
 * after a transfer that filled the cluster exactly), not as the start of the next. So `seek` walks
 * one step fewer to a boundary, and `xfer` steps with `next_cluster` BEFORE it touches a sector at
 * in-cluster offset 0. A fresh cursor (cluster 0) is the end of "cluster 0", and the first step
 * from it goes to `OFD_STRTCL`.
 *
 * HOW `xfer` MOVES BYTES — a partial HEAD sector through the buffer cache and the caller's copy
 * routine; the rest of the head's cluster as whole sectors straight through `Rwabs`
 * (`gemdos_rwabs_data`, which flushes any cached copy first); then whole CLUSTERS, coalesced into
 * one `Rwabs` per run of CONTIGUOUS clusters; the whole sectors left over; and a partial TAIL sector
 * through the cache again. A `buffer` of 0 is how the directory layer reads an entry: the transfer
 * stops at the first cached sector and answers a pointer into it.
 *
 * THREE ROM FACTS THIS KEEPS, each pinned by a case:
 *
 *   * FAT12's ODD entries are shifted down with `asr.w #4` ($fc60d0) — SIGNED — so an odd entry
 *     with bit 11 set comes back with $f000 over it: $ff8..$ffe (and any cluster number from $800
 *     up) is NEGATIVE for an odd cluster and positive for an even one. A negative "next cluster"
 *     then walks into the pseudo-cluster space; only $fff is turned into -1.
 *   * The allocator searches `m_numcl` - 2 clusters from the current one, modulo `m_numcl` — so the
 *     last two clusters of a disk (numbered `m_numcl`, `m_numcl` + 1) are never allocated.
 *   * The head's cluster is finished with `clsiz_mask & record` whole sectors ($fc6330): the SECTOR
 *     INDEX, not the number left in the cluster (`clsiz` minus it). The two agree only when the head
 *     is the cluster's middle sector — every head of a two-sector cluster, and index 2 of a
 *     four-sector one; a one-sector cluster never takes the stretch (its mask is 0). With four-sector
 *     clusters a head at index 1 moves one sector where three are left, and one at index 3 three
 *     where one is.
 *
 * ---- WHAT HALTS ----------------------------------------------------------------------------------
 * A BIOS disk error inside the cache or `Rwabs` (`src/gemdos/fs_disk.c` says why), and a copy routine
 * that is neither of the two the ROM passes. Nothing else.
 */
#include <stdint.h>

#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/fs_copy.h"
#include "gemdos/fs_io.h"
#include "gemdos/process.h"
#include "m68k_idioms.h"
#include "machine.h"
#include "recreate.h"

#define FAT_ENTRY_READ     2        /* every FAT access moves exactly one word ($fc5fda `#2`) */

#ifdef RECREATE_HOST_DIFFERENTIAL
/* `include/gemdos/gemdos.h`'s frame-word guard, defined here with the helpers below that are its only users. */
int gemdos_host_frame_word_held;
#endif

/* A word field of a DMD or an OFD, as the SIGNED word every compare in this engine makes of it. */
static int16_t field_word(const uint8_t *image, uint32_t record, uint32_t field)
{
    return (int16_t)be16(image + record + field);
}

/* ---- $fc7e24, the split -------------------------------------------------------------------------- */

/* `value >> shift` (`asr.l` by a register: a negative value stays negative, the count is modulo 64)
 * and the bits shifted out, as a word — the mask being the WORD the ROM's table holds at `shift`,
 * `ext.l`-ed ($fc7e34). The table is a mask, `(1 << shift) - 1` as a word, for shifts 0..17 only (16
 * and 17 are both $ffff, a whole-longword mask once sign-extended); the DMD builder makes -1 of a
 * zero geometry field, and the table read and the shift here are the ROM's for any word at all
 * (`include/gemdos/fs.h`, `include/m68k_idioms.h`). */
static int32_t split(const uint8_t *image, int16_t *remainder, int32_t value, uint16_t shift)
{
    *remainder = (int16_t)((int32_t)(int16_t)gemdos_bit_mask(image, shift) & value);
    return asr_long_by(value, shift);
}

/* $fc7e24 — the same, storing the remainder WORD through a pointer the way every caller hands it:
 * `seek` passes `&ofd->cloff` and `xfer` two frame locals. */
uint32_t gemdos_split_shift(uint8_t *image, uint32_t rem, uint32_t value, uint16_t shift)
{
    int16_t remainder;
    int32_t quotient = split(image, &remainder, (int32_t)value, shift);

    wr16(image + rem, (uint16_t)remainder);
    return (uint32_t)quotient;
}

/* ---- $fc61d6, the position moving on -------------------------------------------------------------- */

/* The position by `count`; the in-cluster offset too when asked (a whole-cluster run is not — the
 * cursor sits at its cluster's END, offset 0, by the header's convention); and the length grown to
 * the new position when it is past it, SIGNED, which is also what marks the entry dirty. */
void gemdos_ofd_advance(uint8_t *image, uint32_t ofd, uint32_t count, uint16_t in_cluster)
{
    uint32_t position = be32(image + ofd + OFD_POS) + count;

    wr32(image + ofd + OFD_POS, position);
    if (in_cluster != 0)
        wr16(image + ofd + OFD_CLOFF, (uint16_t)(be16(image + ofd + OFD_CLOFF) + count));
    if ((int32_t)position > (int32_t)be32(image + ofd + OFD_FILELN)) {
        wr32(image + ofd + OFD_FILELN, position);
        wr16(image + ofd + OFD_FLAGS, (uint16_t)(be16(image + ofd + OFD_FLAGS) | OFD_DIRTY));
    }
}

/* ---- $fc6038 / $fc5f44, the FAT ------------------------------------------------------------------- */

/* Where cluster `cluster`'s FAT12 entry starts, as a byte offset into the FAT: `n + n/2`, with the
 * halving an `asr.w` and the sum a word. */
static int32_t fat12_offset(int16_t cluster)
{
    return (int16_t)(cluster + (cluster >> 1));
}

static int32_t fat16_offset(int16_t cluster)
{
    return (int32_t)cluster * FAT16_ENTRY_BYTES;
}

/* One FAT word read through the FAT OFD into a frame word (`include/gemdos/gemdos.h`), then turned round IN
 * PLACE by `$fc4f10` — the ROM's own call ($fc5fee, $fc6084, $fc60c0) — and read back out of it. */
static uint16_t read_fat_word(uint8_t *image, uint32_t dmd, int32_t offset)
{
    uint32_t fat = be32(image + dmd + DMD_FAT_OFD);
    uint16_t local;
    uint32_t word_at = gemdos_frame_word_claim(&local);
    uint16_t word;

    gemdos_ofd_seek(image, fat, (uint32_t)offset);
    gemdos_ofd_read(image, fat, FAT_ENTRY_READ, word_at);
    os_swap_word(image, word_at);
    word = be16(image + word_at);
    gemdos_frame_word_release();
    return word;
}

/* ...and one written back through it: stored, turned round in place, then written.
 *
 * WHERE THE WORD IS differs from the ROM in one arm, invisibly. The FAT12 arm stores the new pair in
 * `-2(a6)` and swaps it there ($fc6008); the FAT16 arm stores nothing — it swaps its own `value`
 * ARGUMENT slot, `10(a6)`, in place ($fc5f62) and transfers from THAT. Both are in the stack band the
 * differential drops, so which frame slot holds the swapped word is not a byte either shore compares,
 * and one helper serves both arms. */
static void write_fat_word(uint8_t *image, uint32_t dmd, int32_t offset, uint16_t value)
{
    uint32_t fat = be32(image + dmd + DMD_FAT_OFD);
    uint16_t local;
    uint32_t word_at = gemdos_frame_word_claim(&local);

    wr16(image + word_at, value);
    os_swap_word(image, word_at);
    gemdos_ofd_seek(image, fat, (uint32_t)offset);
    gemdos_ofd_write(image, fat, FAT_ENTRY_READ, word_at);
    gemdos_frame_word_release();
}

/* $fc6038 — the entry `cluster` holds.
 *
 * A NEGATIVE cluster is a pseudo-cluster of the FAT or the root directory, and its successor is
 * arithmetic: `cl + 1`, written into D0's LOW WORD only (`move.w d7,d0 / addq.w #1,d0`), so the
 * caller's high half comes back — `entry_d0`. That arm is what ends the FAT-reads-itself recursion.
 *
 * Every other arm leaves D0's high half 0 — it is the high half of the two-byte read's result,
 * which is at most 2 — and the FAT12 end-of-chain `$fff` alone is the whole longword -1.
 */
uint32_t gemdos_fat_get(uint32_t entry_d0, uint8_t *image, uint16_t cluster, uint32_t dmd)
{
    int16_t signed_cluster = (int16_t)cluster;
    uint16_t pair;
    uint16_t entry;

    if (signed_cluster < 0)
        return set_low_word(entry_d0, (uint16_t)(signed_cluster + 1));
    if (be16(image + dmd + DMD_FAT16) != 0)
        return read_fat_word(image, dmd, fat16_offset(signed_cluster));

    pair = read_fat_word(image, dmd, fat12_offset(signed_cluster));
    /* SIGNED for an odd entry — the header's first ROM fact. */
    entry = (signed_cluster & 1) ? (uint16_t)((int16_t)pair >> FAT12_ODD_SHIFT)
                                 : (uint16_t)(pair & GEMDOS_FAT12_ENTRY_MASK);
    if (entry == GEMDOS_FAT12_ENTRY_MASK)
        return (uint32_t)GEMDOS_FAT_END_OF_CHAIN;     /* `moveq #-1`: the whole longword */
    return entry;
}

/* The chain walks' view of `$fc6038`: every caller reads the word alone, so the high half the
 * negative arm hands back is not theirs to see. */
static int16_t fat_next(uint8_t *image, int16_t cluster, uint32_t dmd)
{
    return (int16_t)gemdos_fat_get(0, image, (uint16_t)cluster, dmd);
}

/* $fc5f44 — `value` into `cluster`'s entry. FAT16 is one word written; FAT12 is a read-modify-write
 * of the pair the entry shares with its neighbour, the neighbour's nibbles kept. Both go through the
 * FAT OFD, so the cache holds the sector dirty and `fs_disk.c`'s flush writes it to BOTH FAT copies. */
void gemdos_fat_set(uint8_t *image, uint16_t cluster, uint16_t value, uint32_t dmd)
{
    int16_t signed_cluster = (int16_t)cluster;
    int32_t offset;
    uint16_t keep;
    uint16_t pair;

    if (be16(image + dmd + DMD_FAT16) != 0) {
        write_fat_word(image, dmd, fat16_offset(signed_cluster), value);
        return;
    }
    offset = fat12_offset(signed_cluster);
    value &= GEMDOS_FAT12_ENTRY_MASK;
    if (signed_cluster & 1) {
        value = (uint16_t)(value << FAT12_ODD_SHIFT);
        keep = FAT12_ODD_KEEP;
    } else {
        keep = FAT12_EVEN_KEEP;
    }
    pair = read_fat_word(image, dmd, offset);
    write_fat_word(image, dmd, offset, (uint16_t)((pair & keep) | value));
}

/* ---- $fc7d2a, seek -------------------------------------------------------------------------------- */

/* $fc7d2a — the cursor to `position`: ERANGE past the length or below 0, and otherwise the position
 * back, with `OFD_CURCL`/`OFD_CURREC` naming its cluster.
 *
 * THE WALK STARTS FROM THE CURRENT CLUSTER when there is one and the target is not behind it, and
 * from `OFD_STRTCL` otherwise. From the current cluster the step count is the difference of the two
 * cluster INDICES, plus one when the old cursor sat at its cluster's end (offset 0 or `m_clsizb` —
 * the header's convention). The walk takes all but one step, and the last one only when the new
 * position is INSIDE a cluster: a boundary is left at the end of the cluster before it.
 *
 * `OFD_CLOFF` IS STORED FIRST, by the split, so a chain that ends mid-walk answers -1 with the
 * offset already moved and the cluster, record and position not.
 */
uint32_t gemdos_ofd_seek(uint8_t *image, uint32_t ofd, uint32_t position)
{
    int32_t target = (int32_t)position;
    uint32_t dmd;
    int16_t cluster = 0;

    if ((int32_t)be32(image + ofd + OFD_FILELN) < target || target < 0)
        return GEMDOS_ERANGE;
    dmd = be32(image + ofd + OFD_DMD);

    if (target == 0) {
        wr16(image + ofd + OFD_CLOFF, 0);
    } else {
        uint16_t shift = be16(image + dmd + DMD_CLSIZB_LOG2);
        int16_t old_offset = field_word(image, ofd, OFD_CLOFF);
        int16_t at_cluster_end = (old_offset == 0 || old_offset == field_word(image, dmd, DMD_CLSIZB));
        int32_t old_position = (int32_t)be32(image + ofd + OFD_POS);
        int16_t steps = (int16_t)gemdos_split_shift(image, ofd + OFD_CLOFF, position, shift);
        int16_t step;

        if (field_word(image, ofd, OFD_CURCL) != 0 && old_position <= target) {
            steps = (int16_t)(steps - (int16_t)asr_long_by(old_position, shift) + at_cluster_end);
            cluster = field_word(image, ofd, OFD_CURCL);
        } else {
            cluster = field_word(image, ofd, OFD_STRTCL);
        }
        for (step = 1; step < steps; step++) {
            cluster = fat_next(image, cluster, dmd);
            if (cluster == GEMDOS_FAT_END_OF_CHAIN)
                return GEMDOS_ERROR;
        }
        /* ...and NO end-of-chain test on the last step ($fc7df6). */
        if (field_word(image, ofd, OFD_CLOFF) != 0 && steps != 0)
            cluster = fat_next(image, cluster, dmd);
    }
    wr16(image + ofd + OFD_CURCL, (uint16_t)cluster);
    wr16(image + ofd + OFD_CURREC, (uint16_t)gemdos_cluster_record(image, (uint16_t)cluster, dmd));
    wr32(image + ofd + OFD_POS, position);
    return position;
}

/* ---- $fc60f2, the next cluster --------------------------------------------------------------------- */

/* The first FREE cluster at or after `from`, wrapping — or -1 when `m_numcl - 2` probes found none.
 *
 * `from` IS PROBED FIRST, though it is the chain's own last cluster and cannot be free; a probe below
 * the first data cluster is lifted to it; and the wrap is `(probe + 1) % m_numcl` (`divs.w`), so
 * the clusters numbered `m_numcl` and `m_numcl + 1` — the last two of the disk — are never reached
 * by the wrap and never allocated from below. */
static int16_t find_free_cluster(uint8_t *image, int16_t from, uint32_t dmd)
{
    int16_t clusters = field_word(image, dmd, DMD_NUMCL);
    int16_t probe = from;
    int16_t probes;

    for (probes = FIRST_DATA_CLUSTER; probes < clusters; probes++) {
        if (probe < FIRST_DATA_CLUSTER)
            probe = FIRST_DATA_CLUSTER;
        if (fat_next(image, probe, dmd) == 0)
            return probe;
        probe = (int16_t)((int16_t)(probe + 1) % clusters);
    }
    return GEMDOS_FAT_END_OF_CHAIN;
}

/* A free cluster linked onto the end of the chain: marked end-of-chain, then named by the old last
 * cluster — or, for an EMPTY file, by the OFD's own first cluster, which dirties the entry. */
static int16_t allocate_cluster(uint8_t *image, uint32_t ofd, int16_t last, uint32_t dmd)
{
    int16_t found = find_free_cluster(image, last, dmd);

    if (found == GEMDOS_FAT_END_OF_CHAIN)
        return found;
    gemdos_fat_set(image, (uint16_t)found, (uint16_t)GEMDOS_FAT_END_OF_CHAIN, dmd);
    if (last != 0) {
        gemdos_fat_set(image, (uint16_t)last, (uint16_t)found, dmd);
    } else {
        wr16(image + ofd + OFD_STRTCL, (uint16_t)found);
        wr16(image + ofd + OFD_FLAGS, (uint16_t)(be16(image + ofd + OFD_FLAGS) | OFD_DIRTY));
    }
    return found;
}

/* $fc60f2 — the cursor one cluster on: the pseudo-cluster above a NEGATIVE one, the FAT's successor
 * of a data cluster, and `OFD_STRTCL` from a fresh cursor (cluster 0), where an empty file's 0 reads
 * as the end of the chain. With `allocate`, an ended chain is extended rather than refused. The
 * cursor lands at the new cluster's start: its record, and in-cluster offset 0. */
uint32_t gemdos_next_cluster(uint8_t *image, uint32_t ofd, uint16_t allocate)
{
    uint32_t dmd = be32(image + ofd + OFD_DMD);
    int16_t current = field_word(image, ofd, OFD_CURCL);
    int16_t next;

    if (current < 0) {
        next = (int16_t)(current + 1);
    } else {
        if (current > 0) {
            next = fat_next(image, current, dmd);
        } else {
            int16_t first = field_word(image, ofd, OFD_STRTCL);

            next = first != 0 ? first : GEMDOS_FAT_END_OF_CHAIN;
        }
        if (allocate != 0 && next == GEMDOS_FAT_END_OF_CHAIN)
            next = allocate_cluster(image, ofd, current, dmd);
        if (next == GEMDOS_FAT_END_OF_CHAIN)
            return GEMDOS_ERROR;
    }
    wr16(image + ofd + OFD_CURCL, (uint16_t)next);
    wr16(image + ofd + OFD_CURREC, (uint16_t)gemdos_cluster_record(image, (uint16_t)next, dmd));
    wr16(image + ofd + OFD_CLOFF, 0);
    return 0;
}

/* ---- $fc6218, the transfer -------------------------------------------------------------------------- */

/* One transfer's fixed facts and its moving buffer — the frame `$fc6218` keeps them in. */
struct transfer {
    uint8_t *image;
    uint16_t rwflag;        /* the direction; also `buffer_get`'s dirty flag and `next_cluster`'s
                             * allocate flag, which is how a write extends a file */
    uint32_t ofd;
    uint32_t dmd;
    uint32_t buffer;        /* the caller's buffer, moved on as bytes go (`18(a6)`) */
    gemdos_copy_fn copy;    /* the copy routine the caller named, or 0 for one not reconstructed */
};

/* The copy routine at the ROM ADDRESS a caller passes, mapped ONCE at the transfer's entry. Only two
 * are ever passed — `$fc5e9c` hands the READ copy and `$fc5f1c` the WRITE one — so this is those two
 * reconstructions, and any other address is 0: it HALTS at the first copy (`copy_through`), not
 * here, because a transfer that moves only whole sectors — or answers a pointer into the cache —
 * never calls its copy routine, in the ROM either. */
static gemdos_copy_fn copy_routine_at(uint32_t copy)
{
    if (copy == GEMDOS_COPY_OUT)
        return gemdos_copy_out;
    if (copy == GEMDOS_COPY_IN)
        return gemdos_copy_in;
    return 0;
}

/* `jsr (a0)` at $fc62fc and $fc6580. (The second pushes the direction word as a fourth argument and
 * pops twelve bytes; neither copy routine reads it.) */
static void copy_through(const struct transfer *t, uint16_t count, uint32_t cached)
{
    if (t->copy == 0)
        recreate_not_reconstructed("GEMDOS: a transfer copy routine other than $fc55fa/$fc5622");
    t->copy(t->image, count, cached, t->buffer);
}

/* `count` whole sectors from `record` straight through `Rwabs`, then the buffer moved on. */
static void transfer_sectors(struct transfer *t, int16_t count, int16_t record, int32_t bytes)
{
    gemdos_rwabs_data(t->image, t->rwflag, (uint16_t)count, (uint16_t)record, t->buffer, t->dmd);
    t->buffer += (uint32_t)bytes;
}

static int16_t cursor_record(const struct transfer *t)
{
    return field_word(t->image, t->ofd, OFD_CURREC);
}

/* `clusters` whole clusters, one `Rwabs` per CONTIGUOUS run ($fc63ce..$fc648c). Returns non-zero when
 * the chain ended (or the disk filled) before they were all moved, which ends the transfer.
 *
 * A run is `run_record`/`run_sectors`/`run_bytes`, and it is flushed when the next cluster does not
 * continue it — and once more on the LAST cluster, contiguous or not, which is why a last cluster
 * that breaks the run is remembered in `last_pending` and flushed by a second pass. After a flush the
 * run restarts at the cluster just stepped to. The position moves by whole clusters with the
 * in-cluster offset left at 0: the cursor is at the end of its cluster. */
static int transfer_clusters(struct transfer *t, int16_t clusters)
{
    int16_t cluster_sectors = field_word(t->image, t->dmd, DMD_CLSIZ);
    int16_t cluster_bytes = field_word(t->image, t->dmd, DMD_CLSIZB);
    int16_t run_record = 0;
    int16_t run_sectors = 0;
    int32_t run_bytes = 0;
    int16_t last_pending = 0;

    while (clusters-- != 0) {
        int32_t stepped = (int16_t)gemdos_next_cluster(t->image, t->ofd, t->rwflag);

        if (stepped == 0 && (int16_t)(run_record + run_sectors) == cursor_record(t)) {
            run_sectors = (int16_t)(run_sectors + cluster_sectors);
            run_bytes += cluster_bytes;
            if (clusters != 0)
                continue;
        } else if (clusters == 0) {
            last_pending = 1;
        }
        for (;;) {
            /* An empty run moves nothing — its byte count is 0 exactly when its sectors are. */
            if (run_sectors != 0)
                transfer_sectors(t, run_sectors, run_record, run_bytes);
            gemdos_ofd_advance(t->image, t->ofd, (uint32_t)run_bytes, 0);
            if (stepped != 0)
                return 1;
            run_record = cursor_record(t);
            run_sectors = cluster_sectors;
            run_bytes = cluster_bytes;
            if (clusters != 0 || last_pending == 0)
                break;
            last_pending = 0;
        }
    }
    return 0;
}

/* The whole sectors of a transfer — `bytes` of them, from `record` on — without the cache: the rest
 * of the head's cluster, the whole clusters, then what is left over in one more cluster. Non-zero
 * when the chain ended first. */
static int transfer_whole_sectors(struct transfer *t, int16_t record, int32_t bytes)
{
    uint16_t sector_shift = be16(t->image + t->dmd + DMD_RECSIZ_LOG2);
    int16_t in_cluster = (int16_t)(field_word(t->image, t->dmd, DMD_CLSIZ_MASK) & record);
    int16_t leftover;
    int16_t clusters;

    if (in_cluster != 0) {
        /* The SECTOR INDEX as the count — the header's third ROM fact. */
        int16_t moved = (int16_t)asl_word_by((uint16_t)in_cluster, sector_shift);

        transfer_sectors(t, in_cluster, record, moved);
        bytes -= moved;
        gemdos_ofd_advance(t->image, t->ofd, (uint32_t)(int32_t)moved, 1);
    }
    clusters = (int16_t)split(t->image, &leftover, asr_long_by(bytes, sector_shift),
                              be16(t->image + t->dmd + DMD_CLSIZ_LOG2));
    if (transfer_clusters(t, clusters) != 0)
        return 1;
    if (leftover != 0) {
        int16_t moved;

        if ((int16_t)gemdos_next_cluster(t->image, t->ofd, t->rwflag) != 0)
            return 1;
        /* ...the position moved BEFORE these sectors go, where every other stretch moves after. */
        moved = (int16_t)asl_word_by((uint16_t)leftover, sector_shift);
        gemdos_ofd_advance(t->image, t->ofd, (uint32_t)(int32_t)moved, 1);
        transfer_sectors(t, leftover, cursor_record(t), moved);
    }
    return 0;
}

/* $fc6218 — the transfer.
 *
 * `count` is SIGNED and so is every piece of it; the answer is the distance the position moved —
 * which is less than `count` when the chain ends or the disk fills — or, when `buffer` is 0, the
 * address of the bytes inside the first cached sector the transfer reached (the head's, or else the
 * tail's). A buffer of 0 that has whole sectors to move hands `Rwabs` address 0 on the way: the
 * directory layer, the only caller that passes 0, only ever asks for one 32-byte entry.
 */
uint32_t gemdos_ofd_xfer(uint8_t *image, uint16_t rwflag, uint32_t ofd, uint32_t count,
                         uint32_t buffer, uint32_t copy)
{
    struct transfer t = { image, rwflag, ofd, be32(image + ofd + OFD_DMD), buffer, copy_routine_at(copy) };
    uint16_t sector_shift = be16(image + t.dmd + DMD_RECSIZ_LOG2);
    uint32_t start = be32(image + ofd + OFD_POS);
    int32_t remaining = (int32_t)count;
    int16_t offset;
    int16_t record = (int16_t)(split(image, &offset, field_word(image, ofd, OFD_CLOFF), sector_shift)
                               + field_word(image, ofd, OFD_CURREC));
    int16_t tail;

    if (offset != 0) {
        int32_t room = (int16_t)(field_word(image, t.dmd, DMD_RECSIZ) - offset);
        int16_t head = (int16_t)(room > remaining ? remaining : room);
        uint32_t cached = gemdos_buffer_get(image, (uint16_t)record, t.dmd, rwflag);

        gemdos_ofd_advance(image, ofd, (uint32_t)(int32_t)head, 1);
        remaining -= head;
        record++;
        if (t.buffer == 0)
            return cached + (uint32_t)(int32_t)offset;
        copy_through(&t, (uint16_t)head, cached + (uint32_t)(int32_t)offset);
        t.buffer += (uint32_t)(int32_t)head;
    }

    tail = (int16_t)(field_word(image, t.dmd, DMD_RECSIZ_MASK) & remaining);
    if (remaining - tail != 0 && transfer_whole_sectors(&t, record, remaining - tail) != 0)
        return be32(image + ofd + OFD_POS) - start;

    if (tail != 0) {
        int16_t sector = (int16_t)split(image, &offset, field_word(image, ofd, OFD_CLOFF), sector_shift);
        uint32_t cached;

        /* At a cluster's start — or its end, `m_clsiz` sectors in — the cursor steps first. */
        if (sector == 0 || sector == field_word(image, t.dmd, DMD_CLSIZ)) {
            if ((int16_t)gemdos_next_cluster(image, ofd, rwflag) != 0)
                return be32(image + ofd + OFD_POS) - start;
            sector = 0;
        }
        cached = gemdos_buffer_get(image, (uint16_t)(field_word(image, ofd, OFD_CURREC) + sector),
                                   t.dmd, rwflag);
        gemdos_ofd_advance(image, ofd, (uint32_t)(int32_t)tail, 1);
        if (t.buffer == 0)
            return cached;
        copy_through(&t, (uint16_t)tail, cached);
    }
    return be32(image + ofd + OFD_POS) - start;
}

/* ---- $fc5e9c / $fc5f1c, read and write ------------------------------------------------------------ */

/* $fc5e9c — at most what is left of the file, SIGNED: a count at or past the end, or a negative
 * one, moves nothing and answers 0. */
uint32_t gemdos_ofd_read(uint8_t *image, uint32_t ofd, uint32_t count, uint32_t buffer)
{
    int32_t left = (int32_t)(be32(image + ofd + OFD_FILELN) - be32(image + ofd + OFD_POS));
    int32_t wanted = (int32_t)count;

    if (wanted > left)
        wanted = left;
    if (wanted <= 0)
        return 0;
    return gemdos_ofd_xfer(image, RWABS_READ, ofd, (uint32_t)wanted, buffer, GEMDOS_COPY_OUT);
}

/* $fc5f1c — no clamp and no zero test: a write of 0 bytes still reaches the transfer, which fetches
 * (and DIRTIES) the cursor's sector when the cursor is inside one. */
uint32_t gemdos_ofd_write(uint8_t *image, uint32_t ofd, uint32_t count, uint32_t buffer)
{
    return gemdos_ofd_xfer(image, RWABS_WRITE, ofd, count, buffer, GEMDOS_COPY_IN);
}

/* ---- the leaves ------------------------------------------------------------------------------------ */

/* $fc5e6a ($3f) — EIHNDL for a handle that names nothing, else the OFD's read. */
uint32_t gemdos_fread(uint8_t *image, int16_t handle, uint32_t count, uint32_t buffer)
{
    uint32_t ofd = (uint32_t)gemdos_ofd_of_handle(image, handle);

    if (ofd == 0)
        return GEMDOS_EIHNDL;
    return gemdos_ofd_read(image, ofd, count, buffer);
}

/* $fc5eea ($40) — ...and its write. */
uint32_t gemdos_fwrite(uint8_t *image, int16_t handle, uint32_t count, uint32_t buffer)
{
    uint32_t ofd = (uint32_t)gemdos_ofd_of_handle(image, handle);

    if (ofd == 0)
        return GEMDOS_EIHNDL;
    return gemdos_ofd_write(image, ofd, count, buffer);
}

/* $fc7cce ($42) — the offset made absolute by the mode (the END is the length, the CURRENT the
 * position), then seek. The handle is resolved FIRST, so a bad handle is EIHNDL whatever the mode. */
uint32_t gemdos_fseek(uint8_t *image, uint32_t offset, int16_t handle, uint16_t mode)
{
    uint32_t ofd = (uint32_t)gemdos_ofd_of_handle(image, handle);

    if (ofd == 0)
        return GEMDOS_EIHNDL;
    if (mode == GEMDOS_SEEK_FROM_END)
        offset += be32(image + ofd + OFD_FILELN);
    else if (mode == GEMDOS_SEEK_FROM_CURRENT)
        offset += be32(image + ofd + OFD_POS);
    else if (mode != GEMDOS_SEEK_FROM_START)
        return GEMDOS_EINVFN;
    return gemdos_ofd_seek(image, ofd, offset);
}
