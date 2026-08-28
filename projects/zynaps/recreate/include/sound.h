/* sound.h — the YM2149 driver's tables, voice records and routines (src/sound.c). Subsystem: sound.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * The driver is a Z80/AY replayer carried across to the 68000 with its DATA UNCHANGED, which is why
 * every table below is read LITTLE-endian on a big-endian machine (docs/sound.md). It keeps its own
 * shadow copy of the chip's registers in the text segment and pushes that shadow at the ports once
 * a frame, so most of it is memory work the image diff can see; only the flush itself reaches
 * $ff8800/$ff8802, through the kit's direct-PSG surfaces (TRAP_MODEL.md, Phase 6).
 */
#ifndef ZYNAPS_SOUND_H
#define ZYNAPS_SOUND_H

#include <stdint.h>

/* ---- the four little-endian offset tables ----------------------------------------------------
 *
 * Each pairs an INDEX of 16-bit offsets with the DATA those offsets are relative to.
 */
#define A_tune_index 0x17058u  /* `lea $17058(pc),a1` — names.txt: 45 little-endian offset words */
#define A_tune_data  0x171e8u  /* `lea $171e8(pc),a1` — what those offsets are relative to */
#define A_mod_table_index 0x17008u  /* the same shape for the modulation tables: 31 used words */
#define A_mod_table_data  0x170b2u
/* 100 little-endian words, chromatic. Doubled on the way to the chip: it is a 1 MHz AY table and
 * the ST clocks its YM2149 at 2 MHz. */
#define A_note_period_tbl 0x16f40u

/* ---- the chip shadow ------------------------------------------------------------------------
 *
 * 14 bytes at `A_psg_reg_shadow`, register N at +N. The driver only ever writes the shadow; the
 * flush routines push it at the ports.
 */
#define A_psg_reg_shadow 0x16e82u
#define PSG_SHADOW_REGS      14u  /* registers 0..13 — sound_reset_psg pushes all of them */
#define PSG_TICK_FLUSH_REGS  11u  /* ...while the per-frame tick pushes only 10..0 */
#define PSG_REG_NOISE_PERIOD  6u
#define PSG_REG_MIXER         7u
#define PSG_REG_VOLUME_A      8u  /* volumes B and C follow it */
#define PSG_VOICE_PERIOD_BYTES 2u /* voice N's tone-period pair is the shadow at +2*(N-1) */
#define PSG_MIXER_ALL_OFF    0xffu  /* every tone and noise bit set = every channel silent */
/* `ori.b #$c0` on the mixer: bits 6 and 7 are the two I/O ports' DIRECTIONS, not channel enables,
 * and the driver forces both to output every time it touches the register. */
#define PSG_MIXER_PORT_DIRECTION 0xc0u
#define PSG_NOISE_PERIOD_MASK 0xfu

/* The round-robin byte that channel code 4 toggles, and the noise-period modulation block — which
 * has a voice record's first 24 bytes and nothing else. */
#define A_sfx_voice_toggle  0x16e90u
#define A_sound_noise_block 0x16e92u

/* ---- the three voice records ----------------------------------------------------------------- */
#define A_sound_voice1 0x16eaau
#define A_sound_voice2 0x16edcu
#define A_sound_voice3 0x16f0eu
#define VOICE_STRIDE   0x32u     /* 0x16edc - 0x16eaa, and again to 0x16f0e */

/* Bytes 0..0x17 are the modulation state: two independent {counter, counter, cursor} machines —
 * one driving the volume envelope, one the pitch sweep — plus the template a new note resets them
 * from. `VOICE_MOD_TEMPLATE` is 12 bytes copied down over `VOICE_MOD_COUNTERS` on every note-on,
 * which is what makes the two cursors restart together with their counters. */
#define VOICE_MOD_COUNTERS        0x00u  /* .b x2 for the volume machine, then x2 for the pitch */
#define VOICE_MOD_VOLUME_CURSOR   0x04u  /* .l — where the volume envelope has got to */
#define VOICE_MOD_PITCH_CURSOR    0x08u  /* .l — and the pitch sweep */
#define VOICE_MOD_TEMPLATE        0x0cu  /* 12 bytes: the four counters and both cursors' starts */
#define VOICE_MOD_TEMPLATE_BYTES  12u
#define VOICE_MOD_VOLUME_RESTART  0x10u  /* .l — inside the template: command 0xe8 sets it */
#define VOICE_MOD_PITCH_RESTART   0x14u  /* .l — ...and command 0xe9 this one */
/* The pitch machine's counters and cursor are one record over from the volume machine's, which is
 * how sound_voice_modulate reaches it: `addq.l #2,a4` twice, once for each pair of offsets. */
#define VOICE_MOD_PAIR_STEP       2u

#define VOICE_ENABLE          0x18u  /* .b — 0 stops the voice; the driver clears it around a rearm */
#define VOICE_NOTE_COUNTDOWN  0x19u  /* .b — frames left on this row; 0 fetches the next */
#define VOICE_STREAM          0x1au  /* .l — the tune cursor */
#define VOICE_STREAM_LOOP     0x1eu  /* .l — where command 0xff goes back to */
#define VOICE_STREAM_RESTART  0x22u  /* .l — ...and where it goes if THAT is exhausted */
#define VOICE_TRANSPOSE       0x26u  /* .b — added to every note (command 0xe6) */
#define VOICE_NOISE_PENDING   0x27u  /* .b — command 0xe4 sets it; the next note-on consumes it */
#define VOICE_MIXER_BITS      0x28u  /* .b — this voice's bits to OR into the mixer */
#define VOICE_MIXER_MASK      0x29u  /* .b — ...and the bits it owns, to AND away first */
#define VOICE_VOLUME_PTR      0x2au  /* .l — points at this voice's volume byte in the shadow */
#define VOICE_ARPEGGIO        0x2eu  /* .b — 0 = pitch sweep, otherwise the arpeggio's second note */
#define VOICE_NOTE            0x2fu  /* .b — the note the row selected, before arpeggio */
#define VOICE_ARPEGGIO_PHASE  0x30u  /* .b — toggles 0/1 so the arpeggio alternates frame by frame */

/* ---- the modulation record -------------------------------------------------------------------
 *
 * Three bytes a step — {period, delta, repeats} — walked by sound_modtable_step. NOT two delays
 * around a delta: the period is how often the delta is applied and `repeats` is how many times, so
 * a step lasts `period * repeats` frames and answers `MOD_DELTA_NEUTRAL` on the rest of them. A
 * fourth byte of 0xff where the next step's period would be restarts the record from
 * `VOICE_MOD_*_RESTART`.
 */
#define MOD_STEP_PERIOD    0u
#define MOD_STEP_DELTA     1u
#define MOD_STEP_REPEATS   2u
#define MOD_STEP_BYTES     3u
#define MOD_RECORD_END     0xffu
#define MOD_DELTA_NEUTRAL  0x80u  /* what a step that has not elapsed returns; deltas are biased */

/* ---- the tune stream ------------------------------------------------------------------------
 *
 * Rows are {opcode, operand} pairs. An opcode under `SOUND_ROW_NOTE_MAX` is a note and everything
 * from 0xe1 up is a command.
 *
 * OPCODE 0 IS A NOTE TOO, and the ONLY thing it skips is the transpose: the original branches past
 * the `add.b 38(a4),d0` at 0x16d46 straight into the note-on at 0x16d4a, so a rest still looks its
 * period up (note 0's own table entry), still silences the volume byte and still resets both
 * modulation machines. It is a note the transpose cannot move, not a row that leaves the chip
 * alone.
 */
#define SOUND_ROW_BYTES        2u
#define SOUND_ROW_NOTE_MAX     0x65u  /* `cmpi.b #$65` + `bcs` — the first opcode that is NOT a note */
#define SOUND_CMD_END          0xe1u
#define SOUND_CMD_NOISE_PERIOD 0xe4u
#define SOUND_CMD_JUMP         0xe5u
#define SOUND_CMD_TRANSPOSE    0xe6u
#define SOUND_CMD_VOLUME_TABLE 0xe8u
#define SOUND_CMD_PITCH_TABLE  0xe9u
#define SOUND_CMD_NOISE_TABLE  0xeau
#define SOUND_CMD_SWAP_TUNES   0xecu
#define SOUND_CMD_ARPEGGIO     0xf0u
#define SOUND_CMD_LOOP         0xffu
/* 0xfc/0xfd/0xfe start a tune on voice 1/2/3. Anything else at or above 0xe1 that no case above
 * names is SKIPPED — the row is consumed and the interpreter reads the next one. */
#define SOUND_CMD_SPAWN_FIRST  0xfcu
#define SOUND_CMD_SPAWN_BIAS   0xfbu  /* `sub.b #$fb,d0` — 0xfc becomes channel 1 */

/* A stream may open with this two-byte header naming the voice it wants. Any code that is not 1 or
 * 2 selects voice 3, which is the fall-through and not a case of its own. */
#define SOUND_STREAM_CHANNEL_TAG 0xfau
#define SOUND_CHANNEL_VOICE1     1u
#define SOUND_CHANNEL_VOICE2     2u
/* "whichever came round": the toggle byte at `A_sfx_voice_toggle` flips bit 0 and its NEW value is
 * the channel. WHICH pair that alternates between depends on the byte, and the shipped byte is 2 —
 * so it runs voice 3, voice 2, voice 3, ..., not the voice 1 / voice 3 pair names.txt assumes. */
#define SOUND_CHANNEL_ALTERNATE  4u

uint32_t sound_lookup_tune(const uint8_t *image, uint16_t number);
uint32_t sound_lookup_modtable(const uint8_t *image, uint16_t number);
void sound_start(uint8_t *image, uint16_t number, uint8_t channel);
void sound_set_note_period(uint8_t *image, uint16_t note, uint32_t period_shadow);
uint8_t sound_modtable_step(uint8_t *image, uint32_t counters, uint32_t record);
uint8_t sound_modtable_step_a4(uint8_t *image, uint32_t record);
void sound_noise_modulate(uint8_t *image);
void sound_voice_modulate(uint8_t *image, uint32_t voice, uint32_t period_shadow);
uint32_t sound_cmd_swap_tunes(uint8_t *image, uint32_t cursor);
void sound_voice_next_row(uint8_t *image, uint32_t voice, uint32_t period_shadow);
void sound_voice_tick(uint8_t *image, uint32_t voice, uint32_t period_shadow);
void sound_reset_psg(uint8_t *image);
void sound_tick(uint8_t *image);

#endif /* ZYNAPS_SOUND_H */
