/* voice.h — the digitised-voice path: GHOST.LOA and GHOST.VOI.
 *
 * WHAT THIS IS. The game's speech is not played by any code in `GHOST.PRG` at all. Two files are
 * read at boot: **GHOST.LOA**, an `ABSFLAG` .PRG read into the BSS AS DATA and then `jsr`ed, and
 * **GHOST.VOI**, 30,100 bytes of PCM. `play_voice` @ 0x13cea pokes the sample pointer into the
 * loaded LOA image at +0x1e and calls its text; the LOA programs MFP Timer A, installs a handler at
 * $134 and busy-waits (`../notes/loader.md`).
 *
 * WHAT IS PORTED HERE is the two routines of the GAME: the loader and the call-up to the `jsr`.
 * THE LOA PLAYER ITSELF IS NOT — the kit models no MFP timer and no interrupt, so there is nothing
 * to enter its handler from and nothing to end its wait; ../STATUS.md's "Not reconstructed" says
 * what closing it needs. `play_voice` is therefore a SLICE that stops at the `jsr`.
 * ============================================================================================= */
#ifndef BG_VOICE_H
#define BG_VOICE_H

#include <stdint.h>

#include "clib.h"    /* the buffered FILE layer and the allocator both loaders go through */

/* --- the two files, and where each lands --- */
#define A_name_ghost_loa   0x22f58u  /* `pea -8130(a4)` @ 0x13c74 — ten bytes `init_globals` builds
                                      * one at a time, which is why `strings` finds it in no file */
#define A_name_ghost_voi   0x22f4eu  /* `pea -8140(a4)` @ 0x13cb6 */
#define A_mode_ghost_loa   0x251beu  /* `pea 676(a4)`  @ 0x13c70 — "br", binary read */
#define A_mode_ghost_voi   0x251c2u  /* `pea 680(a4)`  @ 0x13cb2 — a SECOND copy of the same two
                                      * bytes, which the linker never merged */
#define A_loa_image        0x237a0u  /* `pea -6010(a4)` @ 0x13c8e: the LOA .PRG read into the BSS */
#define A_voi_buffer       0x2379cu  /* long: what `c_malloc(VOI_BUFFER_BYTES)` answered */

#define LOA_FILE_BYTES     0xa8fu    /* `move.w #$a8f,-(a7)` @ 0x13c86 — the whole of GHOST.LOA */
#define VOI_BUFFER_BYTES   0x7594u   /* `move.w #$7594,-(a7)` @ 0x13ca4: what is ALLOCATED... */
#define VOI_FILE_BYTES     0x7593u   /* ...and `move.w #$7593` @ 0x13cc8, what is READ into it —
                                      * one byte fewer, which is the program's own arithmetic and
                                      * not a transcription slip */
#define FREAD_ITEM_BYTES   1u        /* `move.w #$1,-(a7)`: both reads count in single bytes */

/* --- the three scratch longwords `play_voice` builds its poke out of --- */
#define A_loa_sample_source 0x23790u /* `move.l -6014(a4),-6026(a4)` @ 0x13d00: the VOI buffer... */
#define A_loa_sample_slot   0x23794u /* `-6022(a4)`: &loa_image + LOA_SAMPLE_POINTER_OFFSET... */
#define A_loa_sample_dest   0x23798u /* `-6018(a4)`: ...and a copy of it, which is what is
                                      * dereferenced. Three longwords for one store, which is what
                                      * an unoptimising compiler makes of `*(p + 0x1e) = q` */

#define LOA_SAMPLE_POINTER_OFFSET 0x1eu /* `addi.l #$1e,-6022(a4)` @ 0x13cf8: where in the loaded
                                         * LOA image the player expects its sample pointer */
#define LOA_ENTRY_OFFSET          0x1cu /* `lea -5982(a4),a0` @ 0x13d18 = A_loa_image + this: the
                                         * LOA's own entry point, two bytes BELOW the pointer slot */

/* ================================================================================================
 * Cores
 * ============================================================================================= */

/* `load_voice_player` @ 0x13c6c — GHOST.LOA into the BSS, then GHOST.VOI into a malloc'd buffer.
 * It threads ONE register block by pointer, for `include/clib.h`'s reason: `c_read` leaves A1 at
 * `A_c_errno` and every trap after it files that. */
void load_voice_player(uint8_t *image, CallerAddressRegisters *live);

/* `play_voice` @ 0x13cea, the slice `[0x13cea, 0x13d26)` — everything up to the `jsr` into the LOA.
 * ANSWERS the address it would have called, which is what the composition needs and what no image
 * byte carries. */
uint32_t play_voice_arm(uint8_t *image);

#endif /* BG_VOICE_H */
