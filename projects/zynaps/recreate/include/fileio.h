/* fileio.h — the game's one GEMDOS file loader (src/fileio.c). Subsystem: fileio.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_FILEIO_H
#define ZYNAPS_FILEIO_H

#include <stdint.h>

/* The one handle the loader keeps. It is a WORD and it is global rather than local, so a second
 * load overwrites it — which is safe only because the routine opens, reads and closes in one go. */
#define A_file_handle 0x18246u

/* BIGAST.DAT's own name in the game's filename table at 0x19686 (../../names.txt
 * `filename_bigast_dat`). It is NOT one of include/init.h's `A_filename_*` family, and that is the
 * ownership line rather than an oversight: that family is the BOOT's and the level-section flow's,
 * patched per section, while this one name is read by exactly one routine — this file's
 * `asteroids_load_and_build`. */
#define A_filename_bigast_dat 0x1974du
/* `move.l #$f00,d1` — the read count for it. Six 32x32 masked sprites is exactly this many bytes
 * (`ASTEROID_SPRITES * ASTEROID_SOURCE_BYTES`, include/sprite.h), and the two are pinned equal by
 * test_fileio.py rather than one being written as the other: the shipped file's size and the
 * routine's read count are two facts that happen to agree, the way include/init.h's two level
 * caps do NOT. */
#define ASTEROID_FILE_BYTES 0xf00u

void load_file(uint8_t *image, uint32_t name, uint32_t destination, uint32_t length);
void asteroids_load_and_build(uint8_t *image);

#endif /* ZYNAPS_FILEIO_H */
