/* fileio.c — load_file @ 0x144e8, the only route anything on the disk takes into RAM.
 *
 * `_start` calls it thirty-odd times from the filename table at 0x19686 — the sprite banks, the
 * level maps, the title picture, the font. Open, read, close, with no error handling of any kind:
 * a failed open is passed straight to Fread as a handle, which is what the game does and so what
 * this does. Under the harness the three traps are served from `harness.stage_files` staging
 * (TRAP_MODEL.md, Phase 4), so the bytes land in the image and the diff covers them.
 *
 * `asteroids_load_and_build` @ 0x156ac is here too, and it is here because it is a LOADER: one file
 * in, six preshifted sprite banks out. The two halves of the build it composes belong to `sprite`
 * and are called from there, so what this file owns is the file and the order.
 */
#include "machine.h"
#include "os.h"
#include "fileio.h"
/* `asteroids_load_and_build` composes three other subsystems: the level file buffer it stages
 * through (scroll), the store the banks are built in (video), and both halves of the build
 * (sprite). Each address lives in its owner's header and is included here to be read. */
#include "scroll.h"
#include "sprite.h"
#include "video.h"

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

/* asteroids_load_and_build @ 0x156ac — everything an asteroid-field section needs, in one call.
 *
 * BIGAST.DAT holds six 32x32 masked sprites and is read into `A_tile_set_base`, the same staging
 * buffer the level loads use — so the file is scratch here and nothing reads it again once the six
 * banks are built. Each sprite becomes one 0x1e00-byte bank of eight three-cell frames
 * (`asteroid_sprite_expand`, src/sprite.c) and each bank is then shifted in place
 * (`asteroid_preshift_bank`), so the game can draw an asteroid at any of the eight 2-pixel phases.
 *
 * THE BANKS ARE LAID OVER `A_backdrop_page0`, and they are BIGGER THAN IT LOOKS: six banks is
 * 0xb400 bytes from 0x1a8ae, which is two playfields' worth — the front end's compose buffer
 * (include/video.h) and the scroll ring's page 1 (0x202ae, `A_map_page_table`) both live inside it.
 * Nothing collides only because of WHEN each is used: the front end is finished by the time a
 * section loads, and an asteroid section renders no backdrop at all, so `section_start_prefill`
 * leaves the pages alone (it reads `A_asteroid_section_flag`, which this arm has just set).
 *
 * THE TWO PASSES ARE SEPARATE in the original — all six expansions first, then all six preshifts —
 * and that ORDER IS UNOBSERVABLE, which is recorded rather than tested: `asteroid_sprite_expand`
 * reads only the staging buffer and writes only bank i, and `asteroid_preshift_bank` reads and
 * writes only bank i, so interleaving them into one loop produces identical bytes for every input.
 * The two loops are kept apart because that is what the instructions do, not because a case holds
 * them; STATUS.md's fileio row carries the residual. */
void asteroids_load_and_build(uint8_t *image) {
    load_file(image, A_filename_bigast_dat, A_tile_set_base, ASTEROID_FILE_BYTES);
    for (unsigned sprite = 0; sprite < ASTEROID_SPRITES; sprite++)
        asteroid_sprite_expand(image, addr_add(A_tile_set_base, sprite * ASTEROID_SOURCE_BYTES),
                               addr_add(A_backdrop_page0, sprite * ASTEROID_BANK_BYTES));
    for (unsigned sprite = 0; sprite < ASTEROID_SPRITES; sprite++)
        asteroid_preshift_bank(image, addr_add(A_backdrop_page0, sprite * ASTEROID_BANK_BYTES));
}

/* Register map: A0 = the filename (a 0-terminated lowercase string in the table at 0x19686),
 * A1 = where the bytes go, D1 = how many. D1 and A1 are saved across the Fopen and restored
 * (`movem.l #$4040` / `#$0202`), which is what lets one register set serve all three calls. */
void g_load_file(uint8_t *image, uint32_t name, uint32_t destination, uint32_t length) {
    load_file(image, name, destination, length);
}

/* No register arguments: every address it touches is one of its own literals. */
void g_asteroids_load_and_build(uint8_t *image) {
    asteroids_load_and_build(image);
}
