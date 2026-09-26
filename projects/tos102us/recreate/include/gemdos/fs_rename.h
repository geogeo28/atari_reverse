/* gemdos/fs_rename.h — `Frename`, the GEMDOS leaf that gives a file another name or another directory
 * (`src/gemdos/fs_rename.c`).
 *
 *   $fc7af0  gemdos_frename   ($56) a file renamed in place, or moved to another directory of its drive
 *
 * It sits on top of the whole file system: the name leaves (`include/gemdos/fs_open.h`), the create
 * layer (`include/gemdos/fs_create.h`) and `Fclose` (`include/gemdos/process.h`) — the LEAVES, called by
 * their entry points, not the routines under them.
 */
#ifndef TOS102US_GEMDOS_FS_RENAME_H
#define TOS102US_GEMDOS_FS_RENAME_H

#include <stdint.h>

/* $fc7af0 ($56) — rename the file `old` names to `new`: 0, EACCDN for a `new` already there, EPTHNF,
 * ENSAME for two drives, or what `Fopen` or `Fclose` answered. `reserved` is the ABI's unused word. */
uint32_t gemdos_frename(uint8_t *image, uint16_t reserved, uint32_t old, uint32_t new);

#endif /* TOS102US_GEMDOS_FS_RENAME_H */
