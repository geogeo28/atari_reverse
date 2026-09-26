/* gemdos_fs_records.h — the GEMDOS file system's RECORD layer: making DNDs and OFDs, handing out a
 * handle for an open, and the text forms of a name and a path (`src/gemdos/fs_records.c`).
 *
 * The layouts are `include/gemdos_fs.h`'s; the byte copies and swaps under these are
 * `include/gemdos_fs_copy.h`'s. Each routine is declared with its ROM address and its arguments in
 * the ROM's own order.
 */
#ifndef TOS102US_GEMDOS_FS_RECORDS_H
#define TOS102US_GEMDOS_FS_RECORDS_H

#include <stdint.h>

/* $fc5672 — do two eleven-byte FCB names agree, upper-cased? 1, or `entry_d0` with its LOW word
 * cleared — the `$fc5c9a` convention (`include/gemdos_fs.h`, "what the cores export"). */
uint32_t gemdos_fcb_name_eq(uint32_t entry_d0, const uint8_t *image, uint32_t name, uint32_t other);

uint32_t gemdos_ofd_new(uint8_t *image, uint32_t dnd);                                 /* $fc5c3c */
uint32_t gemdos_dnd_new(uint8_t *image, uint32_t parent, uint32_t dirent);             /* $fc65a2 */
uint32_t gemdos_ofd_open(uint8_t *image, uint32_t dirent, uint32_t dnd, int16_t handle,
                         uint16_t mode);                                               /* $fc6fdc */
uint32_t gemdos_handle_alloc(uint8_t *image, uint32_t dirent, uint32_t dnd, uint16_t mode); /* $fc6f5c */
uint32_t gemdos_dir_zero_cluster(uint8_t *image, uint32_t dnd);                        /* $fc70f6 */
uint32_t gemdos_fcb_to_text(uint8_t *image, uint32_t fcb, uint32_t text);              /* $fc6b66 */
uint32_t gemdos_dnd_path(uint8_t *image, uint32_t dnd, uint32_t text);                 /* $fc6bd2 */
void gemdos_fill_dta(uint8_t *image, uint32_t dirent, uint32_t dta);                   /* $fc6ebc */

#endif /* TOS102US_GEMDOS_FS_RECORDS_H */
