/* ym_psg.h — where the YM2149 is, and how much of it this driver owns.
 *
 * Included by BOTH ym_music.c and ym_psg.S (which is assembled through the C preprocessor), so the
 * count the register image is sized by and the count the publish writes cannot drift apart.
 */
#ifndef YM_PSG_H
#define YM_PSG_H

/* The register-select port IS the base address; the data port is two bytes past it. */
#define PSG_CHIP_BASE_ADDRESS 0xFFFF8800
#define PSG_DATA_OFFSET       2

/* Registers 0..10: three tone periods, the noise period, the mixer and three volumes. Registers
 * 11-13 are the hardware envelope generator and this driver never writes them — every amplitude it
 * produces comes from a per-frame volume table (ym_music.h). */
#define PSG_REG_COUNT         11

/* The interrupt mask the publish holds. A PSG access is a SELECT store followed by a DATA store,
 * and any handler that touches the chip in between (TOS's floppy and keyboard code drive port A
 * through the same two addresses) writes our data into its register. Level 6 is live inside a
 * level-4 vblank, so the pair genuinely races there. */
#define CPU_IPL_MASK_ALL      0x0700

#ifndef __ASSEMBLER__
#include <stdint.h>

/* Write PSG registers 0..PSG_REG_COUNT-1 from `image`, interrupts masked for the whole burst.
 * Supervisor only. */
void ym_psg_publish(const uint8_t *image);
#endif

#endif /* YM_PSG_H */
