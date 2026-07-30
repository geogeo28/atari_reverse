/* sound.h — the sound layer: addresses and prototypes.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name.
 *
 * Joust drives the YM2149 two ways, and BOTH are off the memory image, so both need the kit's TOS
 * model (tools/recreate_kit/TRAP_MODEL.md):
 *   * XBIOS Dosound(list) hands the chip a command list the model never dereferences — it records
 *     the pointer in an ordered ledger that harness.differential() compares side against side;
 *   * XBIOS Giaccess reads and writes a modeled 16-byte register file that lives IN the image
 *     (os.h OS_PSG_REGS), so those accesses are ordinary image traffic the differential covers.
 *
 * Only what this layer alone touches is declared here; the globals a second subsystem reads are in
 * addrs.h. snd_priority is one address the object and score layers CHANGE without naming: they
 * call play_sound, which owns it.
 */
#ifndef JOUST_SOUND_H
#define JOUST_SOUND_H

#include <stdint.h>

/* ---- globals ---- */
#define A_snd_sweep_pitch   0x10d48u  /* .w — snd_tone_sweep's descending tone period */
#define A_snd_sweep_volume  0x10d4au  /* .w — snd_tone_sweep's descending amplitude */
#define A_snd_priority      0x10d4cu  /* .w — the sound now playing; LOWER index = higher priority */
#define A_sound_table       0x11774u  /* .l[] — Dosound command lists, indexed by sound number */

/* ---- the kit's XBIOS Dosound side-effect ledger (tools/recreate_kit/src/dosound_log.c) ---- */
void g_dosound(uint8_t *image, uint32_t list_addr);

/* ---- sound.c ---- */
void play_sound(uint8_t *image, uint16_t index);
void snd_poll_done(uint8_t *image);
void snd_tone_sweep(uint8_t *image);

#endif /* JOUST_SOUND_H */
