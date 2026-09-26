/* gemdos/fs_create.h — the GEMDOS file system's CREATE layer: making a directory entry, and the three
 * leaves that make and unmake one (`src/gemdos/fs_create.c`).
 *
 *   $fc71b6  gemdos_create    an entry made (an existing one deleted first), and opened
 *   $fc719a  gemdos_fcreate   ($3c) the same, with the subdirectory bit taken out of the attribute
 *   $fc792a  gemdos_ddelete   ($3a) an EMPTY directory's DND unlinked and freed, and its entry deleted
 *   $fc73ce  gemdos_dcreate   ($39) a subdirectory entry, its first cluster, and `.` and `..` in it
 *
 * Above the directory layer (`include/gemdos/fs_dir.h`) and the file layer (`include/gemdos/fs_file.h`);
 * the records are `include/gemdos/fs.h`'s.
 */
#ifndef TOS102US_GEMDOS_FS_CREATE_H
#define TOS102US_GEMDOS_FS_CREATE_H

#include <stdint.h>

/* $fc71b6 — make the entry `name` names, with attribute `attr`'s low byte, and open it: the handle,
 * or EPTHNF / EACCDN / ENSMEM / ENHNDL. */
uint32_t gemdos_create(uint8_t *image, uint32_t name, uint16_t attr);

/* $fc719a ($3c), $fc792a ($3a), $fc73ce ($39) — the three leaves. */
uint32_t gemdos_fcreate(uint8_t *image, uint32_t name, uint16_t attr);
uint32_t gemdos_ddelete(uint8_t *image, uint32_t path);
uint32_t gemdos_dcreate(uint8_t *image, uint32_t path);

#endif /* TOS102US_GEMDOS_FS_CREATE_H */
