/* gemdos_fs.h — the GEMDOS file system's DATA STRUCTURES, and the one door it reaches the disk by.
 *
 * GEMDOS makes no hardware access at all (`COMPONENTS.md`: zero in the whole `$fc4e5e..$fc9f0b`
 * range). It reaches a disk through exactly three BIOS calls — `Rwabs`, `Getbpb` and `Mediach` —
 * and those three are the dispatch table's INDIRECT entries: entries 4, 7 and 9 of the table at
 * `$fc0846` have bit 31 set, and `$fc0828`'s `movea.l (a0),a0` turns each into a jump through a RAM
 * VECTOR (`hdv_rw` `$476`, `hdv_bpb` `$472`, `hdv_mediach` `$47e`). What runs there is whatever the
 * boot left — or a hard-disk driver replaced it with — so it is an INPUT of the file system, in
 * exactly the sense `include/staged_call.h`'s vectors are inputs of the interrupt handlers.
 *
 * WHICH IS WHY THESE THREE ARE NOT IN `include/bcon.h`. That header declares RECONSTRUCTED BIOS
 * cores another translation unit calls; there is no core behind `hdv_rw` to declare. It is reused
 * here for the half that does transfer: `BIOS_TRAP_CLOBBERS`, the published register contract of a
 * real `trap #13`.
 *
 * THE TWO BUILDS, as everywhere else in this project:
 *
 *   * ON TARGET the call is the ROM's own — the trampoline's frame and a real `trap #13`, whose
 *     dispatcher reads the table, sees the sign bit, and jumps through the RAM vector.
 *   * OFF TARGET there is no 68000 to take the trap and no way to execute the 68000 routine the
 *     vector names, so control leaves through `recreate_call_disk_vector`, which the CASE binds to
 *     a host routine with the same effect as the stub it staged for the oracle
 *     (`test/gemdos_fs.py`, the STAGED RAM DISK).
 *
 * ---- THE STRUCTURES, and where each offset was read ---------------------------------------------
 *
 * Frozen deliberately (`docs/agent-playbook.md` §11): several routines in this group are ported
 * against these records, so nobody adds a field and nobody edits this block. Each carries its
 * provenance — the ROM instruction that establishes it — and the only permitted edit is adding a
 * field with its own citation.
 */
#ifndef TOS102US_GEMDOS_FS_H
#define TOS102US_GEMDOS_FS_H

#include <stdint.h>

#include "addrs.h"
#include "bcon.h"       /* read-only: BIOS_TRAP_CLOBBERS, the `trap #13` register contract */
#include "machine.h"

/* ---- the BPB, as BIOS `Getbpb` answers it ------------------------------------------------------
 * Read by `$fc53c0`, the drive-media-descriptor builder, field by field. Atari's published layout;
 * the offsets below are the displacements that routine uses.
 */
#define BPB_RECSIZ            0     /* word: bytes per logical sector          ($fc53c4 `(a0)`)   */
#define BPB_CLSIZ             2     /* word: sectors per cluster               ($fc53d0 `2(a0)`)  */
#define BPB_CLSIZB            4     /* word: bytes per cluster                 ($fc5466 `4(a1)`)  */
#define BPB_RDLEN             6     /* word: root-directory length, in sectors ($fc53da `6(a0)`)  */
#define BPB_FSIZ              8     /* word: one FAT's length, in sectors      ($fc53e4 `8(a0)`)  */
#define BPB_FATREC           10     /* word: first record of the SECOND FAT    ($fc5568 `10(a0)`) */
#define BPB_DATREC           12     /* word: first record of the data area     ($fc55a6 `12(a0)`) */
#define BPB_NUMCL            14     /* word: how many clusters the data area has ($fc547e)        */
#define BPB_BFLAGS           16     /* word: bit 0 = the FAT is 16-bit         ($fc5444)          */
#define BPB_BYTES            18

/* ---- a directory entry, as far as the NAME layer reads it --------------------------------------
 * The eleven FCB bytes and then the attribute, which `$fc5c9a` compares as position twelve of the
 * same buffer. The rest of the 32-byte entry (time, date, cluster, length) belongs to the layer
 * that reads directories and is not named here. */
#define DIRENT_NAME           0
#define DIRENT_ATTR          11
/* The one byte a directory entry's FIRST can be that is not part of a name: `$e5` marks an entry
 * that has been DELETED, and it is the one byte a pattern has to spell exactly ($fc5cb0). Here
 * rather than in `src/gemdos/fs_name.c` because `test/gemdos_fs.py` builds directory entries with
 * it, and the case and the core must not spell it twice. */
#define DIRENT_DELETED        0xe5
/* `cmpi.b #8` at $fc5cfe, and what it does is NARROWER than it looks: a pattern attribute of 8
 * only loses the "an entry attribute of 0 matches anything" shortcut below it — the `and.w` test
 * every other pattern takes still runs, so it matches any entry sharing bit 3. */
#define GEMDOS_ATTR_VOLUME    8

/* ---- the DMD: one per open drive, built by `$fc53c0` out of the BPB -----------------------------
 *
 * THE THREE RECORD OFFSETS ARE THE WHOLE IDEA. GEMDOS addresses the FAT, the root directory and the
 * data area as ONE cluster-numbered space: the data clusters are 2.., the root directory occupies
 * the clusters just below 0 and the FAT the ones below that. `m_recoff[type]` is the bias that
 * turns a record in that space back into the BIOS record number `Rwabs` takes, which is why
 * `GEMDOS_BUFFER_GET` can hold FAT sectors, directory sectors and data sectors in one cache and
 * tell them apart by arithmetic alone.
 */
#define DMD_RECOFF            0     /* word[3], indexed by BUFFER TYPE ($fc5b66 `0(a5,a0.l)`)     */
#define DMD_RECOFF_ENTRY_BYTES 2
#define DMD_DRVNUM            6     /* word: the drive `Rwabs` is called with ($fc5bbc)           */
#define DMD_FSIZ              8     /* word: one FAT's sectors — the step back to the FIRST copy  */
#define DMD_CLSIZ            10     /* word: sectors per cluster               ($fc5458)          */
#define DMD_CLSIZB           12     /* word: bytes per cluster                 ($fc5466)          */
#define DMD_RECSIZ           14     /* word: bytes per sector                  ($fc5470)          */
#define DMD_NUMCL            16     /* word: clusters in the data area         ($fc547e)          */
#define DMD_CLSIZ_LOG2       18     /* word: log2(m_clsiz) — the shift record -> cluster ($fc5492)*/
#define DMD_CLSIZ_MASK       20     /* word: (1 << that) - 1, from the table at $fd2fc8 ($fc54aa) */
#define DMD_RECSIZ_LOG2      22     /* word: log2(m_recsiz)                    ($fc54bc)          */
#define DMD_RECSIZ_MASK      24     /* word: ...and its mask                   ($fc54d4)          */
#define DMD_CLSIZB_LOG2      26     /* word: log2(m_clsizb)                    ($fc54ea)          */
#define DMD_FAT_OFD          28     /* long: the FAT read as a pseudo-FILE     ($fc553c, $fc5f70) */
#define DMD_ROOT_DND         36     /* long: the root directory's node         ($fc53fe, $fc5aae) */
#define DMD_FAT16            40     /* word: BPB_BFLAGS & 1                    ($fc5450)          */
#define DMD_BYTES            48     /* pool size class 3 — `pool_get(3)` at $fc5102, 3*8 words    */

/* ---- the DND: a directory node. Only the fields this wave reads are named. ---------------------- */
#define DND_STRTCL           14     /* word: the directory's first cluster ($fc5ab2 `14(a0)`)     */
#define DND_OFD              20     /* long: the OFD it is read through    ($fc5140 `20(a0)`)     */
#define DND_DMD              36     /* long: the drive it is on            ($fc5434 `36(a0)`)     */

/* ---- the OFD: an open file. Likewise. ---------------------------------------------------------- */
#define OFD_STRTCL           10     /* word: first cluster                 ($fc5c5c, $fc551c)     */
#define OFD_FILELN           12     /* long: length in bytes               ($fc5c62, $fc54fa)     */
#define OFD_DMD              16     /* long: the drive                     ($fc542a, $fc555e)     */

/* ---- the BCB: one cached sector. `$fc5a98` is the whole of its protocol. ------------------------ */
#define BCB_LINK              0     /* long: the next BCB in this list     ($fc5a2e `(a5)`)       */
#define BCB_BUFDRV            4     /* word: which drive, or -1 for EMPTY  ($fc5b04 `cmpi #-1`)   */
#define BCB_BUFTYP            6     /* word: 0 FAT, 1 root directory, 2 data ($fc5bb8)            */
#define BCB_BUFREC            8     /* word: the record, in the DMD's cluster space ($fc5bae)     */
#define BCB_DIRTY            10     /* word: written since it was read     ($fc5bb4, $fc5c28)     */
#define BCB_DM               12     /* long: the DMD it belongs to         ($fc5bc2)              */
#define BCB_BUFR             16     /* long: the sector buffer itself      ($fc5b74, $fc5c2e)     */
#define BCB_BYTES            20

/* WHICH LIST a buffer type goes on, which is not the type itself: `$fc5ace` maps type 0 to list 0
 * and BOTH directory and data types to list 1, so the FAT gets a cache of its own. */
#define BCB_TYPE_FAT          0
#define BCB_TYPE_DIR          1
#define BCB_TYPE_DATA         2
#define BCB_LIST_COUNT        2
#define BCB_EMPTY             0xffff  /* the `b_bufdrv` of a buffer holding nothing (`move.w #-1`) */

/* `Rwabs`' first argument, as this group passes it: bit 0 is the direction and nothing else in the
 * word is ever set here ($fc5b78 `clr.w -(sp)`, $fc5950/$fc59a2 `move.w #1,-(sp)`). */
#define RWABS_READ            0
#define RWABS_WRITE           1
#define RWABS_ONE_RECORD      1     /* every cache transfer is exactly one sector */

/* ---- the door ----------------------------------------------------------------------------------
 *
 * `return_site` is the longword `GEMDOS_BIOS_TRAMPOLINE` parks at `GEMDOS_BIOS_RETURN_SLOT` before
 * taking the trap: ordinary RAM, so the host build stores it too (`src/gemdos/console.c` says why
 * at length). Each caller passes the `BIOS_RETURN_*` constant for its own call site.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
/* ONE hook for all three, keyed by the BIOS function number the trap would have dispatched on —
 * which is what tells them apart on target too. `rwflag`/`buffer`/`count`/`recno` are 0 for the two
 * calls that take only a device. Bound by the case (`test/gemdos_fs.py`), which answers it out of
 * the same staged RAM disk the oracle's own stub transfers to and from. */
extern int32_t (*recreate_call_disk_vector)(uint8_t *image, uint16_t fn, uint16_t rwflag,
                                            uint32_t buffer, uint16_t count, uint16_t recno,
                                            uint16_t dev);
#endif

static inline void gemdos_park_bios_return(uint8_t *image, uint32_t return_site)
{
    wr32(image + GEMDOS_BIOS_RETURN_SLOT, return_site);
}

/* BIOS 4 — `Rwabs(rwflag.w, buffer.l, count.w, recno.w, dev.w)`: the function number, four
 * argument words and one argument longword — 14 bytes, which is what the `lea` drops.
 *
 * The pushes take `d` constraints for `include/bcon.h`'s measured reason: a `g` operand may be a
 * memory operand relative to SP, and the second push would then read it through a stack pointer the
 * first push has already moved. `fn` is an immediate, as it is at every ROM call site. */
static inline uint32_t bios_rwabs(uint8_t *image, uint32_t return_site, uint16_t rwflag,
                                  uint32_t buffer, uint16_t count, uint16_t recno, uint16_t dev)
{
    gemdos_park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return (uint32_t)recreate_call_disk_vector(image, BIOS_RWABS_FN, rwflag, buffer, count, recno,
                                               dev);
#else
    register uint32_t result __asm__("d0");

    (void)image;
    __asm__ volatile ("move.w %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "move.w %3,-(%%sp)\n\t"
                      "move.l %4,-(%%sp)\n\t"
                      "move.w %5,-(%%sp)\n\t"
                      "move.w %6,-(%%sp)\n\t"
                      "trap #13\n\t"
                      "lea 14(%%sp),%%sp"
                      : "=d"(result)
                      : "d"(dev), "d"(recno), "d"(count), "d"(buffer), "d"(rwflag),
                        "i"(BIOS_RWABS_FN)
                      : BIOS_TRAP_CLOBBERS);
    return result;
#endif
}

/* BIOS 9 — `Mediach(dev.w)`: 0, 1 or 2, the three-way protocol `addrs.h` names.
 *
 * THERE IS NO `bios_getbpb` HERE, and that is deliberate: nothing in this wave calls `Getbpb` — the
 * routine that does is the drive-media-descriptor builder at `$fc53c0`, which is not reconstructed.
 * A door with no caller is code nobody proves, so it lands with its caller. (The `hdv_bpb` VECTOR is
 * still staged by a case: a machine with two of its three disk vectors pointed at a staged driver
 * and the third at whatever the snapshot left would be a machine nobody built.) */
static inline uint32_t bios_mediach(uint8_t *image, uint32_t return_site, uint16_t dev)
{
    gemdos_park_bios_return(image, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return (uint32_t)recreate_call_disk_vector(image, BIOS_MEDIACH_FN, 0, 0, 0, 0, dev);
#else
    (void)image;
    return bios_trap_device(BIOS_MEDIACH_FN, dev);
#endif
}

/* ---- what the cores export ---------------------------------------------------------------------
 * `src/gemdos/fs_disk.c` and `src/gemdos/fs_name.c`; declared here because the layers above them
 * (the directory search, the file leaves) call them by name, exactly as the ROM's C does.
 *
 * `entry_d0` ON THREE OF THEM is the Alcyon result convention read honestly: `$fc539a`,
 * `$fc50ca` and `$fc5c9a` end in `move.w`/`clr.w` on D0, which write the LOW WORD and leave the
 * caller's high half standing. Taking the register in as an argument and handing the whole of it
 * back is what lets the differential compare all 32 bits (`test/case.py`, `assert_result_is_d0`)
 * instead of agreeing with a reconstruction that cleared what the ROM left alone. `$fc55e6` needs
 * none: its `muls.w` writes the whole register.
 */
uint32_t gemdos_fs_log2(uint32_t entry_d0, uint16_t value);
uint32_t gemdos_fs_toupper(uint32_t entry_d0, uint16_t character);
uint32_t gemdos_cluster_record(const uint8_t *image, uint16_t cluster, uint32_t dmd);
uint32_t gemdos_name_match(uint32_t entry_d0, const uint8_t *image, uint32_t pattern,
                           uint32_t entry);
void gemdos_build_fcb_name(uint8_t *image, uint32_t path, uint32_t fcb);
void gemdos_buffer_flush(uint8_t *image, uint32_t bcb);
void gemdos_rwabs_data(uint8_t *image, uint16_t rwflag, uint16_t count, uint16_t recno,
                       uint32_t buffer, uint32_t dmd);
uint32_t gemdos_buffer_get(uint8_t *image, uint16_t recno, uint32_t dmd, uint16_t dirty);

#endif /* TOS102US_GEMDOS_FS_H */
