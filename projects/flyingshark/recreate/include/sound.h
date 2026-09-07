/* sound.h — the whole of Flying Shark's audio: the `A\MODULE.BAK` YM2149 driver and the six game
 * wrappers that are the only things which call it. Subsystem: sound (src/sound.c).
 *
 * WHERE THE NAMES COME FROM, and it is not the usual place. The driver is a SEPARATE GEMDOS `.PRG`
 * the boot chain reads whole into the bss, so its routines are in no `fn` line of `../names.txt`:
 * they are named in `../out/names_module.txt` (the second Ghidra project, `ghidra_proj_module`,
 * whose decompile is `../out/module_decomp.c` and whose listing is `../out/module_dis.txt`), and
 * `../notes/sound_engine.md` is the write-up. Only the six GAME-side wrappers below are in
 * `../names.txt`. The addresses agree either way: the module is loaded to `A_sound_module_file` and
 * entered at `A_sound_module` = that + 28 (`include/globals.h`), which is where its own Ghidra
 * project bases it.
 *
 * EVERYTHING THE DRIVER READS IS IN THE IMAGE, and nothing here copies it. The five tunes, the
 * thirteen effects, the note-period table, the envelopes, the arpeggio sequence and the sequencer's
 * own jump table are bytes of `A\MODULE.BAK` at fixed offsets from `A_sound_module`; the C indexes
 * them exactly as the 68000 does, so the DATA is the file's and only the code is reconstructed.
 * That is also what makes the module's own bounds bugs faithful: several of its byte-wide indices
 * run past the end of the table they address and into the next one, and an image read reproduces
 * that where a C array would not.
 *
 * THE OFFSETS BELOW ARE FROM `A_sound_module`, NOT ABSOLUTE, and deliberately. `A\MODULE.BAK` has
 * ABSFLAG set and no relocation table: every reference inside it is PC- or A3-relative, so the base
 * is the game's `lea $58944.l,a0` and the STRUCTURE is the offsets. Spelling them absolute would
 * also collide with `test_constants.py`'s "one address, one `A_*` name" rule for no gain.
 *
 * TWO SURFACES LIVE OUTSIDE THE MEMORY IMAGE, so `src/sound.c` reaches both through the kit rather
 * than by storing: the driver pushes its register shadow at `$ff8800`/`$ff8802` (`psg_port_write`,
 * TRAP_MODEL.md Phase 6) and reads `$ff820a` bit 1 to pick the 50/60 Hz tempo divider
 * (`hw_read8(OS_HW_SHIFTER_SYNC)`, Phase 7 — a case that reaches the tick must declare it with
 * `hw_seed=`, or the reconstruction is verified against a machine that does not exist).
 */
#ifndef FS_SOUND_H
#define FS_SOUND_H

#include <stdint.h>

/* ---- BORROWED: two game globals the wrappers read ---------------------------------------------
 *
 * Neither belongs to this subsystem — both are written by the level/stage setup — and each is a
 * LOAN with a row in STATUS.md's "Borrowed globals" until the subsystem that owns it lands and
 * defines it in its own header. `../names.txt` spells both names.
 */
#define A_music_suspend_flag 0x176a4u /* `tst.w $176a4` @ 0x1259c — non-zero suspends the restart;
                                       * written by init_stage_state @ 0x1139a (frontend) */
#define A_level_tune_id      0x1776eu /* the tune number start_level @ 0x11440 copies out of the
                                       * level record (frontend); read by 0x121a2 and 0x125b0 */

/* ---- the module's four entry points, as the `jsr n(a0)` offsets the game uses ------------------
 *
 * Offsets rather than addresses because that is how all fourteen call sites spell them:
 * `lea $58944.l,a0 / jsr <n>(a0)`.
 */
#define SND_ENTRY_VBL_TICK    38u    /* 0x26  — one VBL */
#define SND_ENTRY_STOP        434u   /* 0x1b2 */
#define SND_ENTRY_SFX_START   1196u  /* 0x4ac — D0.b = effect 0..12 */
#define SND_ENTRY_MUSIC_START 1256u  /* 0x4e8 — D0.b = tune 0..4 */

/* ---- the PSG register shadow, `A_sound_module` + 0x00 .. 0x0c -------------------------------
 *
 * Thirteen bytes the whole driver writes and only the tick's tail reads, pushed at the chip in one
 * burst. A tone-period pair is stored COARSE BYTE FIRST — which is the order the two registers go
 * out in (1 then 0), so a plain big-endian word read of the shadow IS the register pair.
 */
#define SND_SHADOW_PERIOD_A      0x00u
#define SND_SHADOW_PERIOD_B      0x02u
#define SND_SHADOW_PERIOD_C      0x04u
#define SND_SHADOW_PERIOD_BYTES  2u
#define SND_SHADOW_NOISE_PERIOD  0x06u
#define SND_SHADOW_VOLUME_A      0x07u  /* volumes B and C follow, one per channel */
#define SND_SHADOW_ENV_PERIOD    0x0au  /* word, coarse first: registers 12 then 11 */
#define SND_SHADOW_ENV_SHAPE     0x0cu  /* a ONE-SHOT latch: pushed only when non-zero, then zeroed */
#define SND_SHADOW_BYTES         12u    /* +0x00..+0x0b — what the burst pushes unconditionally */

/* ---- the sound-effect generator's parameter block, +0x0d .. +0x1d --------------------------
 *
 * `sfx_start` fills all of it from one 18-byte record; the tick's second half is its whole
 * interpreter. An effect owns channel C and pre-empts the music there, and nowhere else.
 */
#define SND_SFX_DURATION       0x0du  /* ticks left; at 0 it silences channel C and clears active */
#define SND_SFX_PERIOD_DELTA   0x0eu  /* word, added to the running period EVERY tick */
#define SND_SFX_PERIOD_RESET   0x10u  /* word, snapped back to when the reset counter fires */
#define SND_SFX_ALT_DELTA      0x12u  /* LONG: two alternative word deltas, A at +0x12, B at +0x14 */
#define SND_SFX_PERIOD_CURRENT 0x16u  /* word — the running channel-C period */
#define SND_SFX_RESET_RELOAD   0x18u  /* 0 disables the reset entirely */
#define SND_SFX_ALT_RELOAD     0x19u  /* 0 disables the alternation entirely */
#define SND_SFX_ALT_PATTERN    0x1au  /* rotated right one bit per alternation; carry picks A or B */
#define SND_SFX_NOISE_PATTERN  0x1bu  /* rotated right one bit per tick; carry puts C on noise */
#define SND_SFX_RESET_COUNTER  0x1cu
#define SND_SFX_ALT_COUNTER    0x1du

/* ---- the rest of the variable block, +0x1e .. +0x25 ---------------------------------------- */
#define SND_MUSIC_ACTIVE         0x1eu /* the ONLY "tune finished" signal the module exposes */
#define SND_SFX_ACTIVE           0x1fu
/* What `st <flag>` leaves in either of the two above is `SCC_TRUE` (include/common.h). */
#define SND_VBL_50HZ_DIVIDER     0x20u /* 60 Hz only: 6,5,...,1, and the reload tick skips */
#define SND_MUSIC_TEMPO_RELOAD   0x21u /* frames per sequencer step, from the tune record */
#define SND_MUSIC_TEMPO_COUNTER  0x22u
#define SND_NOISE_PERIOD_DEFAULT 0x23u /* pushed to the noise shadow at the top of every music tick */
#define SND_NOISE_PERIOD_ALT     0x24u /* pattern command 0x8b; used by the alternating-noise flags */
#define SND_MASTER_VOLUME        0x25u /* ships 0x0f; the one byte a capture inherits from the file */
#define SND_VARIABLE_BLOCK_BYTES 0x26u /* +0x00 .. +0x25, and the whole of the driver's own state */

/* ---- the tables, all of them bytes of `A\MODULE.BAK` ---------------------------------------- */
#define SND_SEQ_COMMAND_TABLE      0x2deu /* 13 words, (cmd - 0x80) * 2; each an offset from base */
#define SND_ARP_LOOP_POINT_TABLE   0x2f8u /* 6 bytes, (cmd - 0xb0) */
#define SND_INSTRUMENT_ENV_OFFSETS 0x384u /* 14 bytes: instrument -> offset into the envelopes */
#define SND_NOTE_PERIOD_TABLE      0x392u /* 84 words, indexed by (note + arp + transpose) * 2 */
#define SND_TUNE_TABLE             0x540u /* 5 records of 8 bytes */
#define SND_CHANNEL_A              0x568u /* three 24-byte channel structs, back to back */
#define SND_ARP_SEQUENCE_TABLE     0x7d1u /* 10 bytes, walked by the channel's arpeggio cursor */
#define ARP_RUN_ENDS               0x80u  /* bit 7 of an entry: last of the run, low 7 bits still
                                           * the offset, and the cursor snaps to the loop point */
#define SND_VOLUME_ENVELOPE_TABLE  0x7dbu /* = SND_ARP_SEQUENCE_TABLE + 10 — but the per-frame
                                           * update never spells it that way: see below */
/* THE PER-FRAME UPDATE DOES NOT KNOW EITHER ADDRESS. `sound_vbl_tick` loads `lea $59115(pc),a1`
 * @ 0x5896a-relative and hands it down, and `channel_frame_update` reads its two tables as
 * `(d1.w,a1)` @ 0x58c88 and `(d0.w,a1,10)` @ 0x58c66 — off that register, not off the module base.
 * So the table base is an ARGUMENT, and this is the displacement between the two. */
#define SND_ENV_TABLE_FROM_ARP_TABLE 10u
#define SND_SFX_TABLE              0xf5eu /* 13 records of 18 bytes, to the exact end of TEXT */

#define SND_TUNES  5u
#define SND_EFFECTS 13u
#define SND_CHANNELS 3u
#define SND_CHANNEL_STRIDE 24u

/* One tune record: `music_start` reads it at SND_TUNE_TABLE + number * 8. */
#define TUNE_RECORD_BYTES  8u
#define TUNE_TEMPO         1u  /* the LOW byte of word 0 — the high byte is never read */
#define TUNE_SEQ_LIST      2u  /* three words: channel A, B, C sequence-list offsets */

/* A sequence list is a run of these, each a pattern offset from the module base, ended by a 0x0000
 * that RESTARTS the list rather than stopping it. The channel's cursor is a byte index in them. */
#define SEQ_LIST_ENTRY_BYTES 2u

/* One sound-effect record: `sfx_start` reads it at SND_SFX_TABLE + number * 18. Words 0..6 land at
 * SND_SFX_PERIOD_DELTA and follow the block's layout exactly, so only the last two are named. */
#define SFX_RECORD_BYTES     18u
#define SFX_COPIED_WORDS     7u   /* `moveq #$6,d0` + `dbf`: words 0..6, block order */
#define SFX_ENV_PERIOD_WORD  14u  /* -> SND_SHADOW_ENV_PERIOD */
#define SFX_ENV_SHAPE_WORD   16u  /* -> SND_SHADOW_ENV_SHAPE : SND_SFX_DURATION */

/* ---- one 24-byte channel struct ------------------------------------------------------------ */
#define CHAN_FLAGS            0x00u
#define CHAN_SEQ_CURSOR       0x01u /* byte index into the word sequence list */
#define CHAN_PATTERN_OFFSET   0x02u /* word, from the module base */
#define CHAN_SEQ_LIST_OFFSET  0x04u /* word, from the module base */
#define CHAN_SLIDE_STEP       0x06u /* signed */
#define CHAN_SLIDE_DELAY      0x07u
#define CHAN_SLIDE_ACCUM      0x08u /* word */
#define CHAN_DURATION         0x0au /* counts down once per sequencer step */
#define CHAN_NOTE_LENGTH      0x0bu
#define CHAN_NOTE             0x0cu
#define CHAN_NOTE_TIED        0xffu /* what command 0x8c leaves here... */
#define CHAN_NOTE_TIED_BIT    0x80u /* ...and the bit `tst.b`+`bmi` really test, so ANY negative
                                     * note carries the running envelope into the next one */
#define CHAN_ENV_STEP         0x0du /* cursor into this instrument's envelope */
#define CHAN_ENV_BYTE         0x0eu /* high nibble = frames left, low nibble = PSG volume */
#define CHAN_INSTRUMENT       0x0fu
#define CHAN_VIBRATO_LIMIT    0x10u /* = depth * 2; the sweep runs 0..limit and turns round */
#define CHAN_VIBRATO_SPEED    0x11u
#define CHAN_VIBRATO_CURRENT  0x12u
#define CHAN_TRANSPOSE        0x13u
#define CHAN_OUT_FLAGS        0x14u /* rebuilt every frame; bit 0 is what the mixer reads */
#define CHAN_ARP_LOOP_POINT   0x15u
#define CHAN_ARP_CURSOR       0x16u
/* +0x17 is never read or written by any instruction in the module. */

#define CHAN_FLAG_FRAME_TOGGLE    (1u << 0) /* flipped once per frame by channel_frame_update */
#define CHAN_FLAG_NOISE_ALTERNATE (1u << 1)
#define CHAN_FLAG_NOISE_ONESHOT   (1u << 2) /* clears NOISE_ALTERNATE after one frame */
#define CHAN_FLAG_SLIDE           (1u << 3)
#define CHAN_FLAG_VIBRATO         (1u << 4)
#define CHAN_FLAG_VIBRATO_UP      (1u << 5)
#define CHAN_FLAG_PORTAMENTO      (1u << 6)
#define CHAN_FLAG_PORTAMENTO_DOWN (1u << 7)
/* `andi.b #$30,(a0)`: a new sequencer step keeps VIBRATO and its direction and drops everything
 * else, which is why vibrato survives a note change and a slide does not. */
#define CHAN_FLAGS_KEPT_BY_A_NEW_STEP (CHAN_FLAG_VIBRATO | CHAN_FLAG_VIBRATO_UP)

#define CHAN_OUT_NOISE      (1u << 0) /* the mixer bit: this channel plays noise, not tone */
#define CHAN_OUT_NOISE_NOTE (1u << 1) /* a 0x54..0x7f pattern byte; re-arms CHAN_OUT_NOISE */

/* ---- the pattern byte encoding -------------------------------------------------------------- */
#define PATTERN_NOISE_NOTE_BASE  0x54u /* 0x00..0x53 tone note, 0x54..0x7f noise note */
#define PATTERN_COMMAND_BASE     0x80u /* 0x80..0x8c through SND_SEQ_COMMAND_TABLE */
#define PATTERN_ARP_LOOP_BASE    0xb0u /* 0xb0..0xb5 through SND_ARP_LOOP_POINT_TABLE */
#define PATTERN_INSTRUMENT_BASE  0xc0u /* 0xc0..0xdd select instrument (byte - 0xc0) */
#define PATTERN_NOTE_LENGTH_BASE 0xe0u /* 0xe0..0xff set the note length to (byte - 0xe0 + 1) */

/* The thirteen entries of SND_SEQ_COMMAND_TABLE, as the module-base offsets the table holds — the
 * dispatch reads the word out of the image and lands on the handler it names, so these are the
 * values a command byte resolves to and not a second numbering of the commands. */
#define SEQCMD_REST              0x298u /* 0x80 — one note length of silence, and ends the step */
#define SEQCMD_CLEAR_FLAGS       0x220u /* 0x81 */
#define SEQCMD_SET_PITCH_SLIDE   0x1f2u /* 0x82, two operands: step (signed), delay */
#define SEQCMD_PORTAMENTO_DOWN   0x216u /* 0x83 */
#define SEQCMD_PORTAMENTO_UP     0x21au /* 0x84 */
#define SEQCMD_NEXT_PATTERN      0x1c6u /* 0x85 — step the sequence list; 0x0000 restarts it */
#define SEQCMD_SET_VIBRATO       0x200u /* 0x86, two operands: speed, depth */
#define SEQCMD_NOISE_ALTERNATE   0x22cu /* 0x87 */
#define SEQCMD_END_OF_SONG       0x1acu /* 0x88 — the only thing that clears music_active by itself */
#define SEQCMD_SET_TRANSPOSE     0x1ecu /* 0x89, one operand */
#define SEQCMD_NOISE_ONESHOT     0x228u /* 0x8a */
#define SEQCMD_SET_NOISE_PERIOD  0x224u /* 0x8b, one operand, then as 0x8a */
#define SEQCMD_TIE               0x1e6u /* 0x8c */

/* ---- the volume envelope ------------------------------------------------------------------- */
#define ENVELOPE_FINISHED   0xf0u /* a byte at or above this is the end of the run: silence */
#define ENVELOPE_FRAME_STEP 0x10u /* one frame off the high nibble; the borrow fetches the next */

/* ---- what the tick pushes at the chip ------------------------------------------------------ */
#define PSG_REG_MIXER      7u
#define PSG_REG_ENV_SHAPE  13u
/* The mixer starts with all three tones gated on, all three noises off and both ports set to
 * INPUT, and is EOR'd once per channel whose out-flags say noise: each constant flips that
 * channel's tone bit off and its noise bit on together. */
#define PSG_MIXER_TONES_ON 0xf8u
#define PSG_MIXER_EOR_A    0x09u
#define PSG_MIXER_EOR_B    0x12u
#define PSG_MIXER_EOR_C    0x24u
/* Volume 0x10 is the YM2149's "follow the hardware envelope" bit rather than a level, which is how
 * an effect gets its decay from the chip instead of from a table. */
#define PSG_VOLUME_ENVELOPE_MODE 0x10u

/* ---- the 50/60 Hz divider ------------------------------------------------------------------ */
#define SHIFTER_SYNC_50HZ       (1u << 1) /* `btst #1,$ffff820a`: SET = 50 Hz, so every tick runs */
#define VBL_50HZ_DIVIDER_RELOAD 6u        /* ...clear = 60 Hz, and one tick in six is dropped */

/* ---- the cores ------------------------------------------------------------------------------
 *
 * `channel` and `volume_shadow` are absolute image addresses, as A0 and A2 hold them.
 * `channel_sequencer_step` and `channel_sequencer_next` answer 1 when pattern command 0x88 ended
 * the song, which the original expresses by rewriting its own return address (src/sound.c).
 */
void     sound_vbl_tick(uint8_t *image);
void     sound_stop(uint8_t *image);
void     sfx_start(uint8_t *image, uint8_t number);
void     music_start(uint8_t *image, uint8_t number);
int      channel_sequencer_step(uint8_t *image, uint32_t channel);
int      channel_sequencer_next(uint8_t *image, uint32_t channel);
void     sequencer_start_note(uint8_t *image, uint32_t channel, uint8_t note, uint32_t cursor);
void     sequencer_end_step(uint8_t *image, uint32_t channel, uint32_t cursor);
uint16_t channel_frame_update(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                              uint32_t arp_table);
uint16_t channel_frame_next(uint8_t *image, uint32_t channel, uint32_t volume_shadow,
                            uint32_t arp_table);

/* ---- the game-side wrappers (these ARE `fn` lines in ../names.txt) --------------------------- */
void sfx_play_2(uint8_t *image);
void sfx_play_5(uint8_t *image);
void sfx_play_6(uint8_t *image);
void sfx_play_10(uint8_t *image);
void music_play(uint8_t *image, uint16_t tune);
void music_stop(uint8_t *image);
void music_restart_if_stopped(uint8_t *image);

/* The effect numbers those four wrappers are hard-coded to (`move.w #$n,d0` at each site). */
#define SFX_PLAY_2_NUMBER  2u
#define SFX_PLAY_5_NUMBER  5u
#define SFX_PLAY_6_NUMBER  6u
#define SFX_PLAY_10_NUMBER 10u

#endif /* FS_SOUND_H */
