/* gemdos/fs_file.h — the GEMDOS file system's FILE layer: closing an OFD, deleting a directory entry,
 * and the one leaf over an open file's entry, `Fdatime` (`src/gemdos/fs_file.c`).
 *
 *   $fc57ee  gemdos_ofd_close      the entry rewritten if dirty, the OFD unlinked, EVERY buffer flushed
 *   $fc7824  gemdos_delete_entry   open copies closed (or EACCDN), the chain freed, `$e5` written
 *   $fc772e  gemdos_fdatime        ($57) an open file's time and date, read or written in its entry
 *
 * The records are `include/gemdos/fs.h`'s; the engine under them `include/gemdos/fs_io.h`'s.
 */
#ifndef TOS102US_GEMDOS_FS_FILE_H
#define TOS102US_GEMDOS_FS_FILE_H

#include <stdint.h>

/* `$fc57ee`'s FLAGS word, and what its callers pass: 0 (`Fclose` $fc577a, `$fc7876`), 2 (the
 * directory writes: `Fdatime`, `Fattrib`, `$fc7912`, `Frename`) and 6 (`Dcreate` $fc7482, $fc759c).
 * A flags word of 0 unlinks too ($fc5898 `tst.w` before the `btst`). */
#define OFD_CLOSE_DIRECTORY   0x0002  /* the entry written with length 0 ($fc583a `btst #1`)      */
#define OFD_CLOSE_UNLINK      0x0004  /* off its directory's DND_FILES list ($fc589e `btst #2`)   */

uint32_t gemdos_ofd_close(uint8_t *image, uint32_t ofd, uint16_t flags);
uint32_t gemdos_delete_entry(uint8_t *image, uint32_t dnd, uint32_t dirent, uint32_t position);
uint32_t gemdos_fdatime(uint8_t *image, uint32_t stamp, int16_t handle, uint16_t set);

#endif /* TOS102US_GEMDOS_FS_FILE_H */
