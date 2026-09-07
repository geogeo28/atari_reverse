/* voice.c — the digitised-voice path. What each address means is `include/voice.h`.
 *
 * TWO ROUTINES, and between them they are the whole of what the GAME does about speech: read the
 * two files, and hand the LOA player a pointer to the samples before calling it. The player itself
 * is a second program and is not ported (`include/voice.h`'s header comment, and ../STATUS.md).
 */
#include "machine.h"

#include "clib.h"
#include "voice.h"

/* load_voice_player @ 0x13c6c — GHOST.LOA into the BSS, GHOST.VOI into a buffer of its own.
 *
 * UNLIKE THE FOUR PICTURE/DEMO LOADERS this one goes through the BUFFERED layer (`c_fopen` /
 * `c_fread` / `c_fclose`) rather than the raw one, and it has NO RETRY: a failed open is not tested
 * at all, so a missing file leaves the read working on whatever `c_fopen` answered. Transcribed as
 * the straight line it is.
 */
void load_voice_player(uint8_t *image, CallerAddressRegisters *live) {
    uint32_t file;

    file = c_fopen(image, A_name_ghost_loa, A_mode_ghost_loa, *live);
    c_fread(image, A_loa_image, (int16_t)FREAD_ITEM_BYTES, (int16_t)LOA_FILE_BYTES, file, live);
    c_fclose(image, file, live);

    /* The sample buffer is one byte LARGER than what is read into it. */
    wr32(image + A_voi_buffer, c_malloc(image, (uint16_t)VOI_BUFFER_BYTES, *live));

    file = c_fopen(image, A_name_ghost_voi, A_mode_ghost_voi, *live);
    c_fread(image, be32(image + A_voi_buffer), (int16_t)FREAD_ITEM_BYTES, (int16_t)VOI_FILE_BYTES,
            file, live);
    c_fclose(image, file, live);
}

/* play_voice @ 0x13cea, the slice `[0x13cea, 0x13d26)` — poke the sample pointer into the loaded
 * LOA image and call it.
 *
 * The one store this makes is built through THREE scratch longwords, which is what an unoptimising
 * compiler makes of `*(loa + 0x1e) = voi`: the address, the value and a copy of the address, each
 * in its own global. All three are compared, so a reconstruction that computed the store directly
 * would differ in twelve bytes even though the store itself landed correctly.
 */
uint32_t play_voice_arm(uint8_t *image) {
    wr32(image + A_loa_sample_slot, A_loa_image);
    wr32(image + A_loa_sample_slot,
         addr_add(be32(image + A_loa_sample_slot), LOA_SAMPLE_POINTER_OFFSET));
    wr32(image + A_loa_sample_source, be32(image + A_voi_buffer));
    wr32(image + A_loa_sample_dest, be32(image + A_loa_sample_slot));
    wr32(image + be32(image + A_loa_sample_dest), be32(image + A_loa_sample_source));
    return A_loa_image + LOA_ENTRY_OFFSET;
}

/* ================================================================================================
 * Glue
 * ============================================================================================= */

void g_load_voice_player(uint8_t *image, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    load_voice_player(image, &live);
}

uint32_t g_play_voice_arm(uint8_t *image) { return play_voice_arm(image); }
