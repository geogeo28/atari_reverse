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

void load_file(uint8_t *image, uint32_t name, uint32_t destination, uint32_t length);

#endif /* ZYNAPS_FILEIO_H */
