/* fileio.c — load_file @ 0x144e8, the only route anything on the disk takes into RAM.
 *
 * `_start` calls it thirty-odd times from the filename table at 0x19686 — the sprite banks, the
 * level maps, the title picture, the font. Open, read, close, with no error handling of any kind:
 * a failed open is passed straight to Fread as a handle, which is what the game does and so what
 * this does. Under the harness the three traps are served from `harness.stage_files` staging
 * (TRAP_MODEL.md, Phase 4), so the bytes land in the image and the diff covers them.
 */
#include "machine.h"
#include "os.h"
#include "fileio.h"

/* THE HANDLE IS STORED BEFORE THE READ AND RE-READ FOR THE CLOSE, rather than kept in a register.
 * That is not incidental: `Fopen`'s answer goes to memory at `A_file_handle` and `Fclose` reads it
 * back from there, so the store is program output the differential can see, and a reconstruction
 * that carried the handle in a local would leave that word holding the previous load's.
 *
 * The word is what is written and what is read back. `Fopen` returns a LONG (a negative error code
 * uses the whole of it), so the truncation is real: an error of -33 (file not found) becomes 0xffdf
 * and is handed to Fread as an unsigned handle. Reproduced.
 *
 * The original pushes a mode word of 0 (read-only) — `clr.w -(a7)` before the filename — which has
 * no counterpart here because `os_fopen` takes no mode at all: the model ignores it (TRAP_MODEL.md,
 * Phase 4), so there is nothing for a constant to name and nothing a case could pin. */
void load_file(uint8_t *image, uint32_t name, uint32_t destination, uint32_t length) {
    int32_t handle = os_fopen(image, name);

    wr16(image + A_file_handle, (uint16_t)handle);
    os_fread(image, (uint16_t)handle, length, destination);
    os_fclose(image, be16(image + A_file_handle));
}

/* Register map: A0 = the filename (a 0-terminated lowercase string in the table at 0x19686),
 * A1 = where the bytes go, D1 = how many. D1 and A1 are saved across the Fopen and restored
 * (`movem.l #$4040` / `#$0202`), which is what lets one register set serve all three calls. */
void g_load_file(uint8_t *image, uint32_t name, uint32_t destination, uint32_t length) {
    load_file(image, name, destination, length);
}
