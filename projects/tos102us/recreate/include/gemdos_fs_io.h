/* gemdos_fs_io.h — the GEMDOS file system's I/O ENGINE: seek, the FAT, the cluster chain and the
 * transfer, and the three leaves over them (`Fread`, `Fwrite`, `Fseek`). `src/gemdos/fs_io.c`.
 *
 * ONE UNIT, because it is one strongly-connected component of the call graph: the FAT is read and
 * written as a PSEUDO-FILE (the DMD's `DMD_FAT_OFD`) through the very transfer engine it serves —
 * `$fc6038` seeks and reads the FAT OFD, the read reaches `$fc6218`, and `$fc6218` steps clusters
 * through `$fc60f2`, which calls `$fc6038` again. The recursion ENDS because the FAT OFD's clusters
 * are NEGATIVE pseudo-clusters (`include/gemdos_fs.h`, the DMD) and `$fc6038` answers `cl + 1` for a
 * negative cluster without reading anything.
 */
#ifndef TOS102US_GEMDOS_FS_IO_H
#define TOS102US_GEMDOS_FS_IO_H

#include <stdint.h>

/* `Fseek`'s three modes ($fc7ce8 `cmpi.w #2`, $fc7cfa `cmpi.w #1`, $fc7d0c `tst.w`); any other word
 * is EINVFN. */
#define GEMDOS_SEEK_FROM_START   0
#define GEMDOS_SEEK_FROM_CURRENT 1
#define GEMDOS_SEEK_FROM_END     2

/* What `$fc6038` answers for a FAT12 entry of `$fff`, and what the chain walks compare against: the
 * end of a chain, as a SIGNED word (`moveq #-1,d0` at $fc60e2; `cmp.w #-1` at $fc61aa, $fc7dd8). */
#define GEMDOS_FAT_END_OF_CHAIN  (-1)
/* ...and the twelve bits a FAT12 entry is (`andw #4095` at $fc5fa4 and $fc60d8). */
#define GEMDOS_FAT12_ENTRY_MASK  0x0fff
/* FAT12 packs two entries into three bytes: entry `n` is at `n + n/2`, in the high twelve bits of the
 * pair for an odd `n` ($fc60d0 `asr.w #4`, $fc5fb6 `asl.w #4`) and the low twelve for an even one.
 * Here rather than in `src/gemdos/fs_io.c` because `test/gemdos_fs.py` encodes the staged FAT with
 * them, and the case and the core must not spell them twice. */
#define FAT12_ODD_SHIFT          4
#define FAT12_ODD_KEEP           0x000f   /* what an odd entry's store leaves of the pair ($fc5fbc) */
#define FAT12_EVEN_KEEP          0xf000   /* ...and an even one's ($fc5fc4) */

/* $fc7e24 — `*rem = value & mask[shift]` (a WORD store), and `value >> shift`, arithmetic. The mask
 * table is one for shifts 0..17; past it, and below it, the ROM reads whatever word is there
 * (`include/gemdos_fs.h`, `gemdos_bit_mask`). */
uint32_t gemdos_split_shift(uint8_t *image, uint32_t rem, uint32_t value, uint16_t shift);

/* $fc61d6 — move an OFD's position on by `count`, its in-cluster offset too when `in_cluster`, and
 * grow its length (marking it dirty) past the old end. */
void gemdos_ofd_advance(uint8_t *image, uint32_t ofd, uint32_t count, uint16_t in_cluster);

/* $fc7d2a — position an OFD at `position`: the position itself, or ERANGE, or -1 for a chain that
 * ends before it. */
uint32_t gemdos_ofd_seek(uint8_t *image, uint32_t ofd, uint32_t position);

/* $fc6038 — the FAT entry of `cluster`. `entry_d0` for `include/gemdos_fs.h`'s Alcyon reason: the
 * negative-cluster arm writes only D0's low word. */
uint32_t gemdos_fat_get(uint32_t entry_d0, uint8_t *image, uint16_t cluster, uint32_t dmd);

/* $fc5f44 — store `value` as the FAT entry of `cluster`. */
void gemdos_fat_set(uint8_t *image, uint16_t cluster, uint16_t value, uint32_t dmd);

/* $fc60f2 — step an OFD to the next cluster of its chain, allocating one when `allocate` and the
 * chain has ended. 0, or -1. */
uint32_t gemdos_next_cluster(uint8_t *image, uint32_t ofd, uint16_t allocate);

/* $fc6218 — THE transfer: `count` bytes between an OFD and `buffer`, in the direction `rwflag` says,
 * partial sectors through the cache and `copy` (the ROM ADDRESS of `$fc55fa` or `$fc5622`), whole
 * sectors straight through `Rwabs`. The bytes moved — or, for a `buffer` of 0, a pointer into the
 * cache. */
uint32_t gemdos_ofd_xfer(uint8_t *image, uint16_t rwflag, uint32_t ofd, uint32_t count,
                         uint32_t buffer, uint32_t copy);

/* $fc5e9c / $fc5f1c — read (clamped to the file's end) and write (not clamped). */
uint32_t gemdos_ofd_read(uint8_t *image, uint32_t ofd, uint32_t count, uint32_t buffer);
uint32_t gemdos_ofd_write(uint8_t *image, uint32_t ofd, uint32_t count, uint32_t buffer);

/* $fc5e6a ($3f), $fc5eea ($40), $fc7cce ($42) — the GEMDOS leaves. */
uint32_t gemdos_fread(uint8_t *image, int16_t handle, uint32_t count, uint32_t buffer);
uint32_t gemdos_fwrite(uint8_t *image, int16_t handle, uint32_t count, uint32_t buffer);
uint32_t gemdos_fseek(uint8_t *image, uint32_t offset, int16_t handle, uint16_t mode);

#endif /* TOS102US_GEMDOS_FS_IO_H */
