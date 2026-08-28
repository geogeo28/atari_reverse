/* dma_sfx.h — STE DMA one-shot sample player: 8-bit signed mono at 12.5 kHz, no CPU mixing.
 *
 * The STE plays a sample by being handed a start and an end address and told to go; the CPU is not
 * in the loop and the cost of a sound is the four register stores below. One voice: a second
 * request either replaces the first or is refused, decided by priority.
 *
 * SUPERVISOR ONLY. Everything here writes $ffff89xx. Call from the VBL or under Supexec.
 *
 * ON A PLAIN ST every entry point below refuses (`dma_sfx_available` is 0 and nothing is written),
 * so the same .PRG runs on both machines; the caller routes its SFX to ym_music_sfx_play instead.
 */
#ifndef DMA_SFX_H
#define DMA_SFX_H

#include <stdint.h>

/* Is this machine one whose $ffff89xx registers are the STE DMA sound chip? Answered from the
 * cookie jar, and valid before dma_sfx_init. */
int dma_sfx_available(void);

/* Bind the player to a sample bank `bytes` long (mk_samples.py's layout) and bring the LMC1992 up
 * to a known route and volume. Returns 1 when the machine has DMA sound and the bank is one this
 * player understands, 0 otherwise — a 0 means every dma_sfx_play will refuse.
 *
 * `bytes` IS CHECKED, ONCE, AGAINST EVERY ENTRY IN THE BANK. What dma_sfx_play hands the chip is a
 * pair of raw addresses, and the DMA then walks between them with the CPU nowhere near it: an entry
 * whose offset or length ran past the end of a truncated blob would have the hardware read the rest
 * of the program's memory out of the speaker, with nothing to stop it and no way to see it in a
 * register dump. Validating the table here is what lets the play path stay four stores. The
 * generator emits the length beside the array (SFX_BANK_BYTES, BLACKICE_SFX_BANK_BYTES). */
int dma_sfx_init(const void *bank_blob, uint32_t bytes);

/* Start sample `index` at `priority`. A request of HIGHER OR EQUAL priority restarts the voice; a
 * strictly lower one is refused while a sample is still playing. Returns 1 if the voice was
 * started. */
int dma_sfx_play(uint8_t index, uint8_t priority);

/* Is the DMA still walking a frame? (The play bit clears itself at the end of a one-shot.) */
int dma_sfx_busy(void);

/* Teardown: stop the DMA. Leaves the LMC1992 where init put it — TOS does not depend on it. */
void dma_sfx_stop(void);

#endif /* DMA_SFX_H */
