/* gemdos/fs_leaves.h — the two GEMDOS leaves over a whole DRIVE (`src/gemdos/fs_leaves.c`).
 *
 *   $fc7a68  gemdos_dfree          ($36) free/total clusters and the geometry, by a FAT scan
 *   $fc6c1a  gemdos_dgetpath       ($47) the process's directory on a drive, as "\A\B"
 *
 * Above the drive layer (`include/gemdos/fs_drive.h`), the FAT engine (`include/gemdos/fs_io.h`) and
 * the record layer's path printer (`include/gemdos/fs_records.h`), which is why they are not in the
 * drive layer's file.
 */
#ifndef TOS102US_GEMDOS_FS_LEAVES_H
#define TOS102US_GEMDOS_FS_LEAVES_H

#include <stdint.h>

/* The Dfree information block ($fc7ad0..$fc7ae2, four `move.l a0,(a4)+`): each field a WORD of the
 * DMD — the free count a word too — sign-extended into a long. */
#define DISKINFO_FREE         0     /* data clusters 2..m_numcl-1 whose FAT entry is 0            */
#define DISKINFO_TOTAL        4     /* DMD_NUMCL                                                  */
#define DISKINFO_SECSIZ       8     /* DMD_RECSIZ                                                 */
#define DISKINFO_CLSIZ       12     /* DMD_CLSIZ                                                  */
#define DISKINFO_BYTES       16

uint32_t gemdos_dfree(uint8_t *image, uint32_t info, int16_t drive);
uint32_t gemdos_dgetpath(uint8_t *image, uint32_t path, int16_t drive);

#endif /* TOS102US_GEMDOS_FS_LEAVES_H */
