/* fs_disk.c — the GEMDOS buffer cache, and the three routines that reach a disk through it.
 *
 * GEMDOS never touches hardware. Every sector it reads or writes goes through BIOS `Rwabs`, which
 * is an INDIRECT dispatch-table entry — a jump through the RAM vector `hdv_rw` — so what actually
 * moves the bytes is whatever driver the boot left there. `include/gemdos_fs.h` is that door.
 *
 * WHAT THE CACHE IS. Two singly-linked lists of buffer control blocks, headed at `_bufl` ($4b2):
 * list 0 holds FAT sectors and list 1 holds directory and data sectors. Each BCB names one record,
 * on one drive, in the DMD's own CLUSTER-NUMBERED address space — so a FAT sector, a root-directory
 * sector and a data sector are told apart by arithmetic on the record number alone, and
 * `m_recoff[type]` is the bias that turns one back into the number `Rwabs` takes.
 *
 * THE POLICY is MRU-to-front with LRU eviction, and the ROM spells it in one routine:
 *
 *   * a HIT is moved to the head of its list — after asking `Mediach` whether the disk is still the
 *     one those bytes came off;
 *   * a MISS takes an EMPTY buffer (`b_bufdrv == -1`) if the scan passed one, and otherwise the
 *     LAST buffer in the list, which is the least recently used by construction;
 *   * the victim is FLUSHED if it is dirty, filled by one `Rwabs` read, and moved to the head.
 *
 * A DIRTY FAT BUFFER IS WRITTEN TWICE. `m_recoff[0]` is derived from the BPB's `fatrec`, which is
 * the first record of the SECOND FAT; the first copy is `m_fsiz` records below it, and $fc59b2 is
 * the second `Rwabs` that keeps the two in step. Only buffer type 0 gets it.
 *
 * ---- WHAT IS NOT RECONSTRUCTED HERE, and it is one thing in three places -------------------------
 *
 * Every one of these routines ends its BIOS call with the same four instructions: store the result
 * at `$75b4`, and if it is non-zero record the drive at `$87cc` and LONGJMP through the
 * process-termination record at `$7ef4` ($fc4f54). That record is the 68000 frame of the `jsr` the
 * GEMDOS dispatcher armed, which `src/gemdos/dispatch.c` omits rather than reconstructs
 * (`recreate/STATUS.md`) — there is no C counterpart for it, and a longjmp out of a C function is
 * not one either. So the ERROR ARM HALTS on both builds, with the true reason, and the success arm
 * — which is every arm a working disk takes — is reconstructed whole. The store at `$75b4` is NOT
 * part of the halt: the ROM makes it unconditionally, and so does this.
 */
#include <stdint.h>

#include "gemdos_fs.h"
#include "machine.h"
#include "recreate.h"

/* The result of a BIOS disk call, stored and then tested. One helper because all five call sites
 * make exactly this sequence, and because the halt below has to be in one place to be one reason. */
static void record_disk_result(uint8_t *image, uint32_t result, uint16_t drive)
{
    wr32(image + GEMDOS_DISK_ERROR, result);
    if (result != 0) {
        wr16(image + GEMDOS_DISK_ERROR_DRIVE, drive);
        recreate_not_reconstructed(
            "GEMDOS: a BIOS disk error, which longjmps through the process-termination record");
    }
}

/* ONE BCB's own 512 bytes to or from the disk, the result recorded — the three places the ROM
 * spells out the same nine-argument sequence (`$fc5972`, `$fc59b2`, `$fc5bfa`). `bios_record` is the
 * record ALREADY BIASED into the numbering `Rwabs` takes: each caller adds a different one of the
 * DMD's three `m_recoff` entries, and that choice is the whole of what distinguishes them.
 */
static void transfer_buffer_record(uint8_t *image, uint32_t return_site, uint16_t rwflag,
                                   uint32_t bcb, uint16_t bios_record, uint16_t drive)
{
    record_disk_result(image,
                       bios_rwabs(image, return_site, rwflag, be32(image + bcb + BCB_BUFR),
                                  RWABS_ONE_RECORD, bios_record, drive),
                       drive);
}

/* $fc590a — one BCB back to the disk, if it is holding anything and is dirty.
 *
 * THE INVALIDATION IS THE FIRST THING IT DOES, not the last: `b_bufdrv` is set to -1 BEFORE the
 * write ($fc593a) and restored after it ($fc59e0), so a disk error taken inside leaves the buffer
 * EMPTY rather than holding bytes the drive did not take. The early-out at $fc5924 stores the same
 * -1 over a buffer that was already empty, or one that is not dirty — a store either way.
 */
void gemdos_buffer_flush(uint8_t *image, uint32_t bcb)
{
    uint16_t drive = be16(image + bcb + BCB_BUFDRV);
    uint16_t type;
    uint32_t dmd;
    uint16_t record;

    if (drive == BCB_EMPTY || be16(image + bcb + BCB_DIRTY) == 0) {
        wr16(image + bcb + BCB_BUFDRV, BCB_EMPTY);
        return;
    }

    dmd = be32(image + bcb + BCB_DM);
    type = be16(image + bcb + BCB_BUFTYP);
    record = be16(image + bcb + BCB_BUFREC);
    wr16(image + bcb + BCB_BUFDRV, BCB_EMPTY);

    transfer_buffer_record(image, BIOS_RETURN_BUFFER_FLUSH, RWABS_WRITE, bcb,
                           (uint16_t)(be16(image + dmd + DMD_RECOFF
                                           + type * DMD_RECOFF_ENTRY_BYTES) + record),
                           drive);

    /* ...and the FIRST FAT copy, `m_fsiz` records below the one just written. */
    if (type == BCB_TYPE_FAT)
        transfer_buffer_record(image, BIOS_RETURN_BUFFER_FLUSH_FAT1, RWABS_WRITE, bcb,
                               (uint16_t)(record
                                          + be16(image + dmd + DMD_RECOFF
                                                 + BCB_TYPE_FAT * DMD_RECOFF_ENTRY_BYTES)
                                          - be16(image + dmd + DMD_FSIZ)),
                               drive);

    wr16(image + bcb + BCB_BUFDRV, drive);
    wr16(image + bcb + BCB_DIRTY, 0);
}

/* The head of the list a region's buffers live on — `_bufl[0]` for the FAT, `_bufl[1]` for both
 * the directory and the data regions ($fc5ace: `type ? 1 : 0`, then `<< 2`). */
static uint32_t list_head_of(uint16_t region)
{
    return SYSVAR_BUFL + (region != BCB_TYPE_FAT ? 1u : 0u) * SYSVAR_BUFL_ENTRY_BYTES;
}

/* $fc59f2 — a span of DATA records straight to `Rwabs`, bypassing the cache.
 *
 * This is how a whole file's worth of clusters moves without going through 512 bytes at a time. The
 * cache is not bypassed silently, though: the DATA list is walked first and every buffer whose
 * record falls inside the span is FLUSHED, so a dirty buffer cannot be overwritten by the read that
 * follows and a stale one cannot survive the write. Only list 1 is walked — a FAT sector can never
 * be inside a data span.
 *
 * The bound is `start <= b_bufrec < start + count`, and both halves are `.w` compares on records.
 */
void gemdos_rwabs_data(uint8_t *image, uint16_t rwflag, uint16_t count, uint16_t recno,
                       uint32_t buffer, uint32_t dmd)
{
    uint16_t drive = be16(image + dmd + DMD_DRVNUM);
    uint32_t bcb = be32(image + list_head_of(BCB_TYPE_DATA));

    while (bcb != 0) {
        int16_t held = (int16_t)be16(image + bcb + BCB_BUFREC);

        if (be16(image + bcb + BCB_BUFDRV) == drive && held >= (int16_t)recno
            && (int16_t)(recno + count) > held)
            gemdos_buffer_flush(image, bcb);
        bcb = be32(image + bcb + BCB_LINK);
    }

    record_disk_result(image,
                       bios_rwabs(image, BIOS_RETURN_RWABS_DATA, rwflag, buffer, count,
                                  (uint16_t)(be16(image + dmd + DMD_RECOFF
                                                  + BCB_TYPE_DATA * DMD_RECOFF_ENTRY_BYTES)
                                             + recno),
                                  drive),
                       drive);
}

/* WHICH REGION a record is in, which is the piece of arithmetic the whole cache rests on.
 *
 * The record is shifted down to its cluster (`m_clsiz` is a power of two, so the shift is an
 * arithmetic one and a negative record stays negative) and compared with the root directory's own
 * first cluster. Below it is the FAT; at or above it, a NEGATIVE record is the root directory and a
 * non-negative one is data. That ordering is built by `$fc53c0`: the root directory is given the
 * pseudo-clusters just below 0 and the FAT the ones below those.
 *
 * The shift count is the DMD's own `m_clsizlog2`, which `$fc53c0` computes as the log2 of a power
 * of two between 1 and 32 — the ROM's `asr.w d0,d6` would take it modulo 64 where C leaves a count
 * past the width undefined, and the difference is a DMD no BPB can produce. Said rather than
 * guarded: a bound here would be a claim about the ROM that is not in it.
 */
static uint16_t region_of_record(const uint8_t *image, int16_t recno, uint32_t dmd)
{
    int16_t cluster = (int16_t)(recno >> (int16_t)be16(image + dmd + DMD_CLSIZ_LOG2));
    uint32_t root = be32(image + dmd + DMD_ROOT_DND);

    if (cluster < (int16_t)be16(image + root + DND_STRTCL))
        return BCB_TYPE_FAT;
    return (recno < 0) ? BCB_TYPE_DIR : BCB_TYPE_DATA;
}

/* The buffer this list will give up: `victim` if the scan found an empty one, else the LAST buffer
 * in the list. Returns the PREDECESSOR's link slot, which is what the relink below needs, and
 * writes the chosen buffer back through `chosen`.
 *
 * The ROM's loop stops on whichever comes first — reaching `victim`, or reaching a buffer whose
 * link is 0 — so an empty list answers with the head slot itself and a `chosen` of 0.
 */
static uint32_t find_the_victim(const uint8_t *image, uint32_t head, uint32_t victim,
                                uint32_t *chosen)
{
    uint32_t previous = head;
    uint32_t bcb = be32(image + head);

    /* The ROM tests the LINK at the top and the identity inside ($fc5b4c, $fc5b3a), in that order,
     * which is transcribed rather than tidied: on an EMPTY list it reads the link of BCB 0 — the
     * reset vector at address 0 — before deciding anything, and a rewritten condition would not. */
    while (be32(image + bcb + BCB_LINK) != 0) {
        if (bcb == victim)
            break;
        previous = bcb;
        bcb = be32(image + bcb + BCB_LINK);
    }
    *chosen = bcb;
    return previous;
}

/* $fc5a98 — THE buffer cache. `recno` is a record in the DMD's cluster-numbered space; the answer
 * is the address of a 512-byte buffer holding it.
 *
 * `dirty` marks the buffer as written the moment it is handed out, which is how a caller that is
 * about to modify a sector says so without a second call.
 *
 * WHAT A MEDIA CHANGE DOES, and it is three different things:
 *   0  the medium has not changed        -> the hit stands
 *   1  it MIGHT have                     -> the buffer is re-read from the disk, in place
 *   2  it definitely has                 -> E_CHNG, and the call longjmps out (halted here)
 * `Mediach` is asked ONLY on a hit: a miss is about to read the sector anyway. It is asked with the
 * BUFFER's `b_bufdrv` rather than with the DMD's `m_drvnum` ($fc5bc8 `move.w 4(a4),(sp)`) — which
 * the hit test has just proved equal, so no case can tell the two apart and a mutation swapping
 * them survives. Transcribed as the ROM has it rather than simplified, and recorded as an
 * EQUIVALENT mutant rather than as a coverage hole (`recreate/STATUS.md`).
 */
uint32_t gemdos_buffer_get(uint8_t *image, uint16_t recno, uint32_t dmd, uint16_t dirty)
{
    uint16_t region = region_of_record(image, (int16_t)recno, dmd);
    uint16_t drive = be16(image + dmd + DMD_DRVNUM);
    uint32_t head = list_head_of(region);
    uint32_t empty = 0;
    uint32_t previous = head;
    uint32_t bcb = be32(image + head);
    int refill;

    while (bcb != 0) {
        if (be16(image + bcb + BCB_BUFDRV) == drive && be16(image + bcb + BCB_BUFREC) == recno)
            break;
        /* EVERY empty buffer the scan passes overwrites the one before it — the ROM's store at
         * $fc5b0c is unconditional — so what a miss takes is the LAST empty buffer in the list,
         * not the first. */
        if (be16(image + bcb + BCB_BUFDRV) == BCB_EMPTY)
            empty = bcb;
        previous = bcb;
        bcb = be32(image + bcb + BCB_LINK);
    }

    refill = (bcb == 0);
    if (refill && empty != 0)
        bcb = empty;

    if (!refill) {
        /* `move.w d0,d5` at $fc5bd8: the answer is TRUNCATED to a word before the three compares,
         * so a driver whose high half is not zero is still read by its low word alone. It matters
         * because `hdv_mediach` is a RAM vector — the assumption would be about somebody else's
         * hard-disk driver rather than about this ROM. */
        uint16_t changed = (uint16_t)bios_mediach(image, BIOS_RETURN_BUFFER_MEDIACH,
                                                  be16(image + bcb + BCB_BUFDRV));

        if (changed == MEDIACH_CHANGED) {
            wr16(image + GEMDOS_DISK_ERROR_DRIVE, be16(image + bcb + BCB_BUFDRV));
            wr32(image + GEMDOS_DISK_ERROR, E_CHNG_LONG);
            recreate_not_reconstructed(
                "GEMDOS: a definite media change, which longjmps through the termination record");
        }
        refill = (changed == MEDIACH_MAYBE);
    }

    if (refill) {
        /* The scan above left `previous` at the END of the list, which is right only when nothing
         * was chosen; a chosen empty buffer has to be found again to know what precedes it. Both
         * are the ROM's one walk at $fc5b2c, which the media-change arm re-enters as well. */
        previous = find_the_victim(image, head, bcb, &bcb);
        gemdos_buffer_flush(image, bcb);
        transfer_buffer_record(image, BIOS_RETURN_BUFFER_READ, RWABS_READ, bcb,
                               (uint16_t)(be16(image + dmd + DMD_RECOFF
                                               + region * DMD_RECOFF_ENTRY_BYTES) + recno),
                               drive);
        wr16(image + bcb + BCB_BUFREC, recno);
        wr16(image + bcb + BCB_DIRTY, 0);
        wr16(image + bcb + BCB_BUFTYP, region);
        wr16(image + bcb + BCB_BUFDRV, drive);
        wr32(image + bcb + BCB_DM, dmd);
    }

    /* MRU to the front, in the ROM's own three stores: unlink, then push onto the head. A buffer
     * that is ALREADY the head writes its own link to itself and then back — which is what the ROM
     * does, so it is what this does.
     *
     * `previous` IS A LINK SLOT, not a BCB: it is either a BCB's address or the list head itself,
     * and the first store works on both only because `BCB_LINK` is 0. That is the ROM's own
     * arrangement ($fc5c10 `move.l (a4),(a0)` with A0 holding either), and the reason the scan
     * starts with `previous = head`. */
    wr32(image + previous, be32(image + bcb + BCB_LINK));
    wr32(image + bcb + BCB_LINK, be32(image + head));
    wr32(image + head, bcb);

    if (dirty != 0)
        wr16(image + bcb + BCB_DIRTY, 1);
    return be32(image + bcb + BCB_BUFR);
}

/* $fc55e6 — where a cluster starts, in records: `cluster * m_clsiz`, as a SIGNED 16x16 multiply
 * whose whole 32-bit product is the result. Negative clusters are the FAT's and the root
 * directory's, and the multiply carries them down exactly as it carries a data cluster up. */
uint32_t gemdos_cluster_record(const uint8_t *image, uint16_t cluster, uint32_t dmd)
{
    return (uint32_t)((int32_t)(int16_t)be16(image + dmd + DMD_CLSIZ) * (int16_t)cluster);
}

#ifdef RECREATE_HOST_DIFFERENTIAL
/* The one definition of the disk door's hook. On target the machine has a `trap #13` instead. */
int32_t (*recreate_call_disk_vector)(uint8_t *image, uint16_t fn, uint16_t rwflag, uint32_t buffer,
                                     uint16_t count, uint16_t recno, uint16_t dev);
#endif
