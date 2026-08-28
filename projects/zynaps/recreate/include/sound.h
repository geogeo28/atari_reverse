/* sound.h — the tune/SFX tables and the sound leaves in src/sound.c. Subsystem: sound.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_SOUND_H
#define ZYNAPS_SOUND_H

#include <stdint.h>

/* The two PC-relative tables inside the text segment that sound_lookup_tune walks. They stay here
 * They are this subsystem's; a routine elsewhere that needs one includes this header. */
#define A_tune_index 0x17058u  /* `lea $17058(pc),a1` — names.txt: 45 little-endian offset words */
#define A_tune_data  0x171e8u  /* `lea $171e8(pc),a1` — what those offsets are relative to */

uint32_t sound_lookup_tune(const uint8_t *image, uint16_t number);

#endif /* ZYNAPS_SOUND_H */
