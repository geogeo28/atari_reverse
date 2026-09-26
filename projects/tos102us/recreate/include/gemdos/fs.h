/* gemdos/fs.h — the GEMDOS file system's DATA STRUCTURES, and the one door it reaches the disk by.
 *
 * GEMDOS makes no hardware access at all (`COMPONENTS.md`: zero in the whole `$fc4e5e..$fc9f0b`
 * range). It reaches a disk through exactly three BIOS calls — `Rwabs`, `Getbpb` and `Mediach` —
 * and those three are the dispatch table's INDIRECT entries: entries 4, 7 and 9 of the table at
 * `$fc0846` have bit 31 set, and `$fc0828`'s `movea.l (a0),a0` turns each into a jump through a RAM
 * VECTOR (`hdv_rw` `$476`, `hdv_bpb` `$472`, `hdv_mediach` `$47e`). What runs there is whatever the
 * boot left — or a hard-disk driver replaced it with — so it is an INPUT of the file system, in
 * exactly the sense `include/staged_call.h`'s vectors are inputs of the interrupt handlers.
 *
 * WHICH IS WHY THESE THREE ARE NOT IN `include/bios/bcon.h`. That header declares RECONSTRUCTED BIOS
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
#include "bios/bcon.h"       /* read-only: BIOS_TRAP_CLOBBERS, the `trap #13` register contract */
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

/* ---- a directory entry: 32 bytes on disk --------------------------------------------------------
 * The eleven FCB bytes and then the attribute, which `$fc5c9a` compares as position twelve of the
 * same buffer. Bytes 12..21 are DOS-reserved and not named. Everything from DIRENT_TIME on is
 * LITTLE-ENDIAN, the DOS order, and the ROM turns a field round (`$fc4f10` a word, `$fc4f22` a long,
 * both IN PLACE after a copy) only where it needs the 68000's order: the first cluster and the length
 * going into a DND or an OFD (`$fc65a2`, `$fc6fdc`) and back out on close (`$fc57ee`), and time, date
 * and length going into a DTA (`$fc6ebc`). Time and date are NOT turned round anywhere else. */
#define DIRENT_NAME           0
#define DIRENT_NAME_BYTES    11     /* stem + extension: `move.w #11` copying it at $fc6626       */
#define DIRENT_EXT            8     /* the three extension bytes           ($fc6b9a `lea 8(a3)`)  */
#define DIRENT_ATTR          11
#define DIRENT_TIME          22     /* word, LE: modification time         ($fc70e0 `22(a5)`)     */
#define DIRENT_DATE          24     /* word, LE: modification date         ($fc70da `24(a5)`)     */
#define DIRENT_STRTCL        26     /* word, LE: first cluster             ($fc70b2 `26(a5)`)     */
#define DIRENT_FILELN        28     /* long, LE: length in bytes           ($fc70c6 `28(a5)`)     */
#define DIRENT_BYTES         32     /* the directory read step ($fc674c `move.l #32`), and $fc6612 */
/* The part of an entry an OFD mirrors, DIRENT_TIME to the end — time, date, first cluster, length:
 * the ten bytes `$fc57ee` writes back ($fc5850 `move.l #10`) — and its first two words, the four
 * `Fdatime` moves ($fc7760 `move.l #4`). */
#define DIRENT_TAIL_BYTES      (DIRENT_BYTES - DIRENT_TIME)
#define DIRENT_TIME_DATE_BYTES (DIRENT_STRTCL - DIRENT_TIME)
/* A search or a read leaves the directory's position ONE ENTRY PAST the entry it has just read, so
 * that entry's own position is this far behind it ($fc660c and $fc704c `addl #-32`, $fc724e and
 * $fc72be `subi.l #32`, $fc7806 `subi.l #32`). */
#define ENTRY_BEHIND_POSITION  DIRENT_BYTES
/* The FCB form those eleven name bytes are: a stem and an extension, each padded with spaces, no
 * dot between them ($fc5d28 builds it, $fc6b66 reads it back). */
#define FCB_STEM_BYTES       DIRENT_EXT
#define FCB_EXTENSION_BYTES  (DIRENT_NAME_BYTES - DIRENT_EXT)
#define FCB_PAD              ' '    /* `moveq #32` padding a field ($fc5d90); ends a field too  */
/* ...and the two characters of the TEXT form every path routine splits on (`cmpi.b #46` at
 * $fc5d60, $fc7e6a; `cmpi.b #92` at $fc5d5a, $fc5e1e; written by $fc6ba4 `move.b #46`). */
#define NAME_DOT             '.'
#define PATH_SEPARATOR       '\\'
/* The one byte a directory entry's FIRST can be that is not part of a name: `$e5` marks an entry
 * that has been DELETED, and it is the one byte a pattern has to spell exactly ($fc5cb0). Here
 * rather than in `src/gemdos/fs_name.c` because `test/gemdos_fs.py` builds directory entries with
 * it, and the case and the core must not spell it twice. */
#define DIRENT_DELETED        0xe5
/* `cmpi.b #8` at $fc5cfe, and what it does is NARROWER than it looks: a pattern attribute of 8
 * only loses the "an entry attribute of 0 matches anything" shortcut below it — the `and.w` test
 * every other pattern takes still runs, so it matches any entry sharing bit 3. */
#define GEMDOS_ATTR_VOLUME    8
/* The other attribute bits the file system TESTS or WRITES. */
#define GEMDOS_ATTR_READ_ONLY 0x01  /* `btst #0,11(an)` at $fc737e, $fc764e, $fc77fa (EACCDN)     */
#define GEMDOS_ATTR_SUBDIR    0x10  /* `btst #4,11(a3)` at $fc66f6; written `move.b #16` $fc74f2  */
/* ...and two it never names: no routine in `$fc4e5e..$fc9f0b` tests or writes hidden or system — each
 * reaches `$fc5c9a` only inside a caller's pattern attribute, through its generic `and.w` ($fc5d14).
 * Named for the entries a battery stages with them. */
#define GEMDOS_ATTR_HIDDEN    0x02
#define GEMDOS_ATTR_SYSTEM    0x04
/* Only ever inside a search attribute: `ori.w #33` at $fc6d24 (Fsfirst with any attribute but VOLUME
 * also matches read-only and archive entries) and `move.w #39` at $fc7630/$fc76a4/$fc77dc (the name
 * leaves' GEMDOS_ATTR_ANY_FILE, `include/gemdos/fs_dir.h`). No routine tests or sets it alone. */
#define GEMDOS_ATTR_ARCHIVE   0x20

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
/* The pool SIZE CLASSES the records are cut from ($fc5102 `move.w #3`; $fc5120, $fc5c48, $fc65b8,
 * $fc6ff0 `#4`): a DMD is class 3, and every DND and OFD class 4 — DMD_BYTES and DND_BYTES/OFD_BYTES. */
#define DMD_POOL_CLASS        3
#define NODE_POOL_CLASS       4
/* The data area's first cluster: FAT entries 0 and 1 are not clusters, so the data bias subtracts
 * `clsiz << 1` ($fc55ae `asl.w #1`) and the allocator's probe starts no lower ($fc6146). */
#define FIRST_DATA_CLUSTER    2
/* A FAT16 entry is a word: `asl.l #1` on the cluster ($fc5f6c, $fc605e). */
#define FAT16_ENTRY_BYTES     2

/* ---- the DND: a directory node, one per directory the tree has reached -------------------------
 * Built from its parent and its directory entry by `$fc65a2`, which pushes it on the FRONT of the
 * parent's child list. Offsets 11..13: no access found. */
#define DND_NAME              0     /* DIRENT_NAME_BYTES: the entry's FCB name ($fc662a copy of 11) */
#define DND_STRTCL           14     /* word: the directory's first cluster ($fc5ab2 `14(a0)`)     */
#define DND_TIME             16     /* word: the entry's time, AS STORED (LE) ($fc6616 `16(a3)`)  */
#define DND_DATE             18     /* word: the entry's date, AS STORED (LE) ($fc661c `18(a3)`)  */
#define DND_OFD              20     /* long: the OFD it is read through    ($fc5140 `20(a0)`)     */
#define DND_PARENT           24     /* long: the parent DND, 0 at the root ($fc65dc; $fc6bda)     */
#define DND_CHILD            28     /* long: the first child DND           ($fc65d8; $fc66aa)     */
#define DND_SIBLING          32     /* long: the next child of the parent  ($fc65d2; $fc66ce)     */
#define DND_DMD              36     /* long: the drive it is on            ($fc5434 `36(a0)`)     */
#define DND_PARENT_OFD       40     /* long: the parent's OFD, holding this entry ($fc65fe)       */
#define DND_DIRPOS           44     /* long: the entry's byte offset in it ($fc6612, parent pos-32) */
/* long: how far a search of this directory has already made DNDs for subdirectories ($fc677c
 * writes it, $fc66e2 skips the DND creation below it; a position of -1 resumes here, $fc6694). */
#define DND_SCANNED          48
#define DND_FILES            52     /* long: head of the OFDs open on its entries, via OFD_LINK ($fc708a) */
#define DND_BYTES            64     /* pool size class 4 — `pool_get(4)` at $fc65b8, 4*8 words    */

/* ---- the OFD: an open file, or a directory read as one ------------------------------------------
 * `$fc6fdc` builds a file's from its directory entry and `$fc5c3c` a directory's from its DND.
 * OFD_TIME..OFD_FILELN mirror DIRENT_TIME..DIRENT_FILELN in order — time and date in the entry's own
 * little-endian order, the cluster and the length turned round into the 68000's. So `$fc57ee`'s
 * write-back on close turns ONLY those two round ($fc5826, $fc5834), writes the ten bytes from +6
 * back over the entry, and turns them back ($fc5884, $fc5892). A second open of one entry copies 12
 * bytes from +6 of the OFD already open on it ($fc70a2). */
#define OFD_LINK              0     /* long: next OFD on DND_FILES          ($fc7082; $fc58c4)     */
#define OFD_FLAGS             4     /* word: OFD_DIRTY | OFD_SCANNED   ($fc6208 `ori.w`; $fc5800)  */
#define OFD_TIME              6     /* word: the entry's time, AS STORED   ($fc70e0 `6(a4)`)      */
#define OFD_DATE              8     /* word: the entry's date, AS STORED   ($fc70da `8(a4)`)      */
#define OFD_STRTCL           10     /* word: first cluster                 ($fc5c5c, $fc551c)     */
#define OFD_FILELN           12     /* long: length in bytes               ($fc5c62, $fc54fa)     */
#define OFD_DMD              16     /* long: the drive                     ($fc542a, $fc555e)     */
/* long: the DND of the directory HOLDING this entry — for a directory's own OFD that is its DND's
 * PARENT ($fc5c70), not the DND itself. Open sets it ($fc7030), close unlinks from it ($fc58a6). */
#define OFD_DIR_DND          20
#define OFD_DIR_OFD          24     /* long: that directory's OFD, the entry is rewritten through ($fc703a; $fc5814) */
#define OFD_DIRPOS           28     /* long: the entry's byte offset in it ($fc7052; $fc580a +22)  */
#define OFD_POS              32     /* long: the current byte position     ($fc7e10; $fc61e6)     */
#define OFD_CURCL            36     /* word: the cluster OFD_POS is in, 0 = unknown ($fc7dfe; $fc7d98) */
#define OFD_CURREC           38     /* word: that cluster's first record   ($fc7e0c; $fc625e)     */
#define OFD_CLOFF            40     /* word: OFD_POS's byte offset in its cluster ($fc7d90; $fc61f4) */
/* word: cleared by open ($fc7024 `clr.w 42(a4)`) and read by nothing in $fc4e5e..$fc9f0b. */
#define OFD_UNUSED           42
/* long: stored on an OFD ALREADY open on the entry, pointing at the NEWER one ($fc70ac) — each
 * open overwrites it, so it is not a chain; nothing in $fc4e5e..$fc9f0b reads it. */
#define OFD_NEXT_SAME_FILE   44
#define OFD_MODE             48     /* word: Fopen/Fcreate's mode ($fc7006); no reader in the group */
#define OFD_MODE_BYTES        2
/* ...and what it holds: `Fopen`'s mode argument, the WORD — read, write, both. One routine tests it,
 * `open`, and only for 0 ($fc7656 `tst.w`); `create` stores read or read/write by the new entry's
 * read-only bit ($fc7386 `clr.w`, $fc738a `move.w #2`). */
#define OPEN_MODE_READ        0
#define OPEN_MODE_WRITE       1
#define OPEN_MODE_READ_WRITE  2
#define OFD_BYTES            64     /* pool size class 4 — `pool_get(4)` at $fc6ff0               */
/* A directory read as a file has no length of its own: the largest positive long ($fc5c62). */
#define DIRECTORY_LENGTH     0x7fffffffu

/* OFD_FLAGS' bits, as word masks; the `btst`s read the LOW byte, +5. */
#define OFD_DIRTY             0x0001  /* length/entry changed: rewrite the entry on close ($fc6208; $fc5800) */
/* A search reached this directory's end ($fc67a4), so every subdirectory already has a DND and
 * later searches create none ($fc66e8 `btst #1,5(a4)`). */
#define OFD_SCANNED           0x0002

/* ---- the DTA: Fsfirst's search state, then what it found ----------------------------------------
 * `$fc6d14` writes the first 21 bytes, `$fc6df4` (Fsnext) reads them back, and `$fc6ebc` fills the
 * rest. DTA_DIRPOS and DTA_DND sit at ODD offsets and are copied four bytes at a time ($fc564a),
 * never as longs. Nothing in the ROM gives the record's total size. */
#define DTA_PATTERN           0     /* the text pattern, DTA_PATTERN_BYTES ($fc6d92 `move.w #12`) */
#define DTA_PATTERN_BYTES    12
#define DTA_ATTR             12     /* byte: the search attribute          ($fc6da0; $fc6e46)     */
#define DTA_DIRPOS           13     /* long, unaligned: where the next search resumes ($fc6dba; $fc6e36) */
#define DTA_DND              17     /* long, unaligned: the directory searched ($fc6dd6; $fc6e14) */
#define DTA_FOUND_ATTR       21     /* byte: the found entry's attribute   ($fc6ecc `21(a0)`)     */
#define DTA_TIME             22     /* word: its time, byte-swapped        ($fc6efa)              */
#define DTA_DATE             24     /* word: its date, byte-swapped        ($fc6f0a)              */
#define DTA_FILELN           26     /* long: its length, byte-swapped      ($fc6f38)              */
#define DTA_NAME             30     /* its "NAME.EXT" text, NUL-ended by $fc6b66 ($fc6f42)        */

/* ---- the BCB: one cached sector. `$fc5a98` is the whole of its protocol. ------------------------ */
#define BCB_LINK              0     /* long: the next BCB in this list     ($fc5a2e `(a5)`)       */
#define BCB_BUFDRV            4     /* word: which drive, or -1 for EMPTY  ($fc5b04 `cmpi #-1`)   */
#define BCB_BUFTYP            6     /* word: 0 FAT, 1 root directory, 2 data ($fc5bb8)            */
#define BCB_BUFREC            8     /* word: the record, in the DMD's cluster space ($fc5bae)     */
#define BCB_DIRTY            10     /* word: written since it was read     ($fc5bb4, $fc5c28)     */
/* ...and the value that says so, which is also `$fc5a98`'s `dirty` argument asking for it ($fc5c28;
 * `$fc70f6` passes it with `move.w #1` at $fc7118). */
#define BCB_MARKED_DIRTY      1
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

/* The head longword of buffer list `list` in `_bufl` — the lookup (`$fc5ace`) and the close's flush of
 * every buffer (`$fc58cc`) both index it. */
static inline uint32_t gemdos_buffer_list_head(uint16_t list)
{
    return SYSVAR_BUFL + (uint32_t)list * SYSVAR_BUFL_ENTRY_BYTES;
}

/* `Rwabs`' first argument, as this group passes it: bit 0 is the direction and nothing else in the
 * word is ever set here ($fc5b78 `clr.w -(sp)`, $fc5950/$fc59a2 `move.w #1,-(sp)`). */
#define RWABS_READ            0
#define RWABS_WRITE           1
#define RWABS_ONE_RECORD      1     /* every cache transfer is exactly one sector */

/* ---- what the file system answers ---------------------------------------------------------------
 * Only the codes no other header defines: EFILNF (-33), ENHNDL (-35) and ENSMEM (-39) are in
 * `include/gemdos/process.h`, EIHNDL (-37) in `include/addrs.h`. Each is a `moveq` at the sites
 * cited. */
/* `moveq #-1`: GEMDOS's generic ERROR — `$fc67de` for a drive with no BPB ($fc680e) or no free
 * directory node ($fc6880), and the I/O engine for a cluster chain that ended ($fc7dde, $fc61b0). */
#define GEMDOS_ERROR        0xffffffffu
#define GEMDOS_EPTHNF       0xffffffdeu /* -34: path not found  (Dsetpath $fc6b06, $fc71de, Frename $fc7b26) */
#define GEMDOS_EACCDN       0xffffffdcu /* -36: access denied   ($fc7248 create, $fc765c open, $fc7802 delete) */
#define GEMDOS_EDRIVE       0xffffffd2u /* -46: no such drive   (Dgetpath $fc6c52)                    */
#define GEMDOS_ENSAME       0xffffffd0u /* -48: not the same drive (Frename $fc7b64)                  */
#define GEMDOS_ENMFIL       0xffffffcfu /* -49: no more files   (Fsnext $fc6e7a)                      */
#define GEMDOS_ERANGE       0xffffffc0u /* -64: seek out of range ($fc7d40, $fc7d4c)                  */
#define GEMDOS_EINTRN       0xffffffbfu /* -65: internal error  ($fc58c8 OFD not on its list; $fc79dc) */

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
 * The pushes take `d` constraints for `include/bios/bcon.h`'s measured reason: a `g` operand may be a
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

/* The two calls that take only a device — the function number and one word, `addq.l #2` after the
 * Alcyon slot — which differ in nothing but that number.
 *
 * A MACRO, NOT A FUNCTION, because of where `fn` goes on target: `bios_trap_device`'s `"i"`
 * constraint needs a compile-time constant, and a function parameter is one only once the compiler
 * has inlined every layer between it and the literal. Expanded in place, the literal each wrapper
 * below spells is what reaches the constraint — the shape `bios_mediach` had before `bios_getbpb`
 * joined it. */
#ifdef RECREATE_HOST_DIFFERENTIAL
#define BIOS_DISK_DEVICE_CALL(image, return_site, fn, dev)                                       \
    (gemdos_park_bios_return((image), (return_site)),                                           \
     (uint32_t)recreate_call_disk_vector((image), (fn), 0, 0, 0, 0, (dev)))
#else
#define BIOS_DISK_DEVICE_CALL(image, return_site, fn, dev)                                       \
    (gemdos_park_bios_return((image), (return_site)), bios_trap_device((fn), (dev)))
#endif

/* BIOS 9 — `Mediach(dev.w)`: 0, 1 or 2, the three-way protocol `addrs.h` names. */
static inline uint32_t bios_mediach(uint8_t *image, uint32_t return_site, uint16_t dev)
{
    return BIOS_DISK_DEVICE_CALL(image, return_site, BIOS_MEDIACH_FN, dev);
}

/* BIOS 7 — `Getbpb(dev.w)`: a pointer to the drive's BPB, or 0 when it has none. One caller in the
 * whole of GEMDOS, the drive log-in at `$fc67de` (`src/gemdos/fs_drive.c`). */
static inline uint32_t bios_getbpb(uint8_t *image, uint32_t return_site, uint16_t dev)
{
    return BIOS_DISK_DEVICE_CALL(image, return_site, BIOS_GETBPB_FN, dev);
}

/* ---- the ROM's mask table ----------------------------------------------------------------------
 * `$fd2fc8`: the word `(1 << n) - 1` for n = 0..17 (16 and 17 both `$ffff`), and from 18 on the ROM's
 * next bytes — `GEMDOS_DOT_ENTRY_HEAD`, the template `Dcreate` copies `.`'s entry from. Both readers
 * index it with a SIGNED word and no bound — `movea.w` then `adda.l` at $fc549e (the DMD builder) and
 * $fc7e28 (`$fc7e24`) — so a log2 of -1 reads the word BELOW it, and any index at all reads SOME word
 * of the ROM. The one reading of it, for both. */
#define GEMDOS_BIT_MASK_ENTRY_BYTES 2

static inline uint16_t gemdos_bit_mask(const uint8_t *image, uint16_t index)
{
    return be16(image + addr_add(GEMDOS_BIT_MASK_TABLE, sign_ext16(index) * GEMDOS_BIT_MASK_ENTRY_BYTES));
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
