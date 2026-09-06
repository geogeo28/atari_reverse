/* sound.h — the three-voice software ADSR + LFO synthesiser for the YM2149.
 *
 * The whole engine lives between 0x142bc and 0x149b4 and owns every global named here: a trigger
 * API (`sound_play` and its four siblings), a 200 Hz Timer C interrupt handler that runs the
 * envelopes and drives the chip, and a `trap #9` gate through which ordinary code reaches the PSG
 * without racing the handler. There is no sequencer and no note stream — every sound is one
 * one-shot VOICE RECORD filled from a 56-word definition. `../notes/sound_engine.md` is the design
 * doc; this header is the address and layout half of it.
 *
 * NAMING. `A_*` is this project's spelling for an absolute address of a GAME GLOBAL, and
 * `test_constants.py` requires every `A_*` to lie inside [BG_BSS_BASE, BG_PROGRAM_END). Three
 * kinds of address here are deliberately NOT `A_*` because they are not globals:
 *   - `SND_ISR_STATE` and the two handler entry points are in the TEXT segment (the installer
 *     writes into its own code segment, which is why the linear listing shows seven `nop`s there);
 *   - `TOS_VEC_*` / `TOS_CONTERM` are 68000/TOS low memory, below the program;
 *   - `MFP_VECTOR_REG` is a hardware register, outside the image entirely.
 */
#ifndef BG_SOUND_H
#define BG_SOUND_H

#include <stdint.h>

#include "clib.h"

/* ================================================================================================
 * The globals the engine owns (../names.txt; the globals census shows no reader outside it)
 * ============================================================================================= */

#define A_snd_voice           0x22daau  /* 3 voice records of SND_VOICE_BYTES; v is the PSG channel */
#define A_snd_note_period     0x22cd0u  /* MIDI note -> tone period. VIRTUAL base: only [24,108] is
                                         * addressable, so the live span starts at 0x22d00 and the
                                         * bytes below it are the two tables that follow */
#define A_snd_volume_scale    0x22cdau  /* 16 words, volume index 0..15 -> 0, 18, 35 ... 239, 256 */
#define A_snd_mixer_and_mask  0x22cfau  /* per-voice AND mask for PSG register 7: 0xf6 0xed 0xdb */
#define A_snd_def_level       0x1f20au  /* 36 definitions of SND_DEF_BYTES, one per room */
#define A_snd_def_fx          0x201cau  /* 11 definitions of SND_DEF_BYTES: fx0..fx10 */

/* `sound_start`/`sound_stop` reach `Supexec` through the C library's `xbios_trap` trampoline, whose
 * three save slots and `CallerAddressRegisters` type belong to the clib subsystem — included to
 * READ them, never to restate them (README.md, "Adding a function"). */

/* ================================================================================================
 * The ISR state block at 0x14932, in the TEXT segment — THIRTEEN bytes, not fifteen
 *
 * `install_sound_vectors` walks it with `(a0)+` and the ISR reads three of its four fields, so it
 * is one block rather than four variables. Pinned by test_sound.py::test_install_sound_vectors.
 * `../names.txt` reads it as 13 bytes + 1 of padding, which is what the instructions write; the
 * "15-byte block" in ../notes/sound_engine.md §2 counts to psg_gate's entry instead.
 * ============================================================================================= */

#define SND_ISR_SAVED_TIMER_C   0x14932u  /* l: TOS's own $114 vector; the ISR pushes it and rts's.
                                           * Also the block's base — `lea $14932(pc),a0` @ 0x148ea */
#define SND_ISR_VOLUME_SCALE    0x14936u  /* l: &snd_volume_scale — the ISR's a2 (read @ 0x1459e) */
#define SND_ISR_TOP_VOICE       0x1493au  /* l: &snd_voice[2] — the ISR's a0 (read @ 0x145a2); the
                                           * loop walks DOWN by SND_VOICE_BYTES */
#define SND_ISR_SAVED_CONTERM   0x1493eu  /* b: TOS's own $484, restored when all voices are idle */
#define SND_ISR_STATE_BYTES     13u       /* 4 + 4 + 4 + 1; 0x1493f is padding before psg_gate */

/* The two handlers the installer puts on vectors, spelt as the addresses they are stored AS. */
#define SND_ISR_ENTRY           0x1459au  /* timer_c_sound_isr -> $114 */
#define SND_TRAP9_HANDLER_ENTRY 0x14950u  /* trap9_psg_handler -> $a4 */

/* ---- TOS low memory and the one hardware register the engine names -------------------------- */
#define TOS_VEC_TRAP9    0x00a4u    /* the trap #9 vector psg_gate dispatches through */
#define TOS_VEC_TIMER_C  0x0114u    /* MFP channel 5 = Timer C, 200 Hz */
#define TOS_CONTERM      0x0484u    /* TOS's key-click/bell flags: cleared while a voice sounds */
#define MFP_VECTOR_REG   0xfffa17u  /* 24-bit bus form of $fffffa17 */
#define MFP_VECTOR_AUTO_EOI 0x40u   /* bit 3 clear = AUTOMATIC end-of-interrupt, what the game runs */
#define MFP_VECTOR_SW_EOI   0x48u   /* bit 3 set = software EOI, what TOS runs and what is restored */

/* ================================================================================================
 * THE VOICE RECORD — 0x8c bytes, THREE OF THEM, AND THIS BLOCK IS FROZEN
 *
 * Freezing it is what lets the trigger API, the interrupt handler and their tests be written
 * against one layout: nobody has to add a field, so nobody edits this block. Each field carries its
 * provenance — either the differential case that would fail if the offset were wrong, or the note
 * that believes it. THE ONLY PERMITTED EDIT IS UPGRADING A TAG in the same change that ports the
 * routine which pins it.
 *
 * A DEFINITION IS THE RECORD'S FIRST 0x70 BYTES: `sound_play` copies def[1..55] straight into
 * offsets 0x02..0x6e, so def word k lands at record offset 2k. The six accumulators (0x74..0x88)
 * and the tail (0x70/0x72) are not in the definition and are set by the trigger.
 * ============================================================================================= */

#define SND_VOICES        3u      /* pinned by test_sound.py::test_sound_stop_all */
#define SND_VOICE_BYTES   0x8cu   /* `muls.w #$8c,dn` @ 0x142e6; pinned by test_sound_play_* */
#define SND_DEF_WORDS     56u     /* pinned by test_sound.py::test_sound_play_every_definition */
#define SND_DEF_BYTES     0x70u   /* = 2 * SND_DEF_WORDS; pinned by the same */

/* ---- header ---- */
#define SND_VC_DURATION        0x00u /* w: 200 Hz ticks left; 0 = idle. pinned by test_isr_* */
#define SND_VC_TONE_PERIOD     0x02u /* w: base 12-bit tone period; <0 = this channel's tone is off.
                                      * pinned by test_isr_pitch_out / test_sound_play_tone_off */
#define SND_VC_NOISE_PERIOD    0x04u /* w: base 5-bit noise period; <0 = noise off.
                                      * pinned by test_isr_noise_out / test_sound_play_noise_off */
#define SND_VC_VOLUME_INDEX    0x06u /* w: index into snd_volume_scale. pinned by test_isr_volume_out */

/* ---- volume machine: an ADSR plus a triangle LFO ---- */
#define SND_VC_VOL_PHASE       0x08u /* w: 0 idle, 1 attack, 2 decay, 3 sustain-hold, 4 release */
#define SND_VC_VOL_ATTACK_STEP 0x0au /* l: per tick, positive; the target is hard-wired */
#define SND_VC_VOL_DECAY_STEP  0x0eu /* l: per tick, negative */
#define SND_VC_VOL_SUSTAIN     0x12u /* l: the decay's target */
#define SND_VC_VOL_RELEASE_STEP 0x16u /* l: per tick, negative; the target is 0 */
#define SND_VC_VOL_LFO_LIMIT   0x1au /* l: amplitude limit; 0 = LFO off */
#define SND_VC_VOL_LFO_STEP    0x1eu /* l: per tick, negated at each limit */
#define SND_VC_VOL_LFO_DELAY   0x22u /* w: onset delay in ticks, counted down once */
/* all six above pinned by test_sound.py::test_isr_volume_machine and the record fuzz */

/* ---- pitch machine: a three-segment envelope plus a two-rate LFO ---- */
#define SND_VC_PITCH_PHASE     0x24u /* w: same 0/1/2/3/4 encoding */
#define SND_VC_PITCH_STEP1     0x26u /* l */
#define SND_VC_PITCH_TARGET1   0x2au /* l: the compare's direction follows the step's sign */
#define SND_VC_PITCH_STEP2     0x2eu /* l */
#define SND_VC_PITCH_TARGET2   0x32u /* l */
#define SND_VC_PITCH_RELEASE_STEP 0x36u /* l: target 0; its sign is flipped at key-off if it does
                                         * not already point back toward zero */
#define SND_VC_PITCH_LFO_LIMIT_HI 0x3au /* l: positive limit; 0 = LFO off */
#define SND_VC_PITCH_LFO_STEP  0x3eu /* l: MUTABLE — reloaded from one of the two below on a carry */
#define SND_VC_PITCH_LFO_STEP_RELOAD_UP 0x42u   /* l: reload while rising */
#define SND_VC_PITCH_LFO_LIMIT_LO 0x46u /* l: negative limit, used while the step is negative */
#define SND_VC_PITCH_LFO_STEP_RELOAD_DOWN 0x4au /* l: reload while falling */
#define SND_VC_PITCH_LFO_DELAY 0x4eu /* w: onset delay in ticks */
/* all pinned by test_sound.py::test_isr_pitch_machine and the record fuzz */

/* ---- noise machine: the same envelope again, plus a plain triangle LFO ---- */
#define SND_VC_NOISE_PHASE     0x50u /* w */
#define SND_VC_NOISE_STEP1     0x52u /* l */
#define SND_VC_NOISE_TARGET1   0x56u /* l */
#define SND_VC_NOISE_STEP2     0x5au /* l */
#define SND_VC_NOISE_TARGET2   0x5eu /* l */
#define SND_VC_NOISE_RELEASE_STEP 0x62u /* l: target 0; sign flipped at key-off like the pitch one */
#define SND_VC_NOISE_LFO_LIMIT 0x66u /* l: 0 = LFO off */
#define SND_VC_NOISE_LFO_STEP  0x6au /* l */
#define SND_VC_NOISE_LFO_DELAY 0x6eu /* w */
/* all pinned by test_sound.py::test_isr_noise_machine and the record fuzz */

/* ---- tail: the two fields a definition does NOT carry ---- */
#define SND_VC_GATE      0x70u /* w: the `note` argument. NEGATIVE => the duration counter runs and
                                * the sound auto-releases; >= 0 => it sustains until a caller stops
                                * it. pinned by test_sound_release_voice */
#define SND_VC_PRIORITY  0x72u /* w: 0 = the voice is free; a new sound is refused if lower.
                                * pinned by test_sound_play_priority_refusal */

/* ---- the six accumulators, all 16.16 and all zeroed by the trigger ---- */
#define SND_VC_VOL_ENV_ACC     0x74u /* l */
#define SND_VC_VOL_LFO_ACC     0x78u /* l */
#define SND_VC_PITCH_ENV_ACC   0x7cu /* l */
#define SND_VC_PITCH_LFO_ACC   0x80u /* l */
#define SND_VC_NOISE_ENV_ACC   0x84u /* l */
#define SND_VC_NOISE_LFO_ACC   0x88u /* l; 0x88 + 4 = 0x8c, so the record is exactly full */
/* all six pinned by test_sound.py::test_sound_play_zeroes_the_accumulators */

/* ---- the two contiguous sub-layouts the three machines share ------------------------------------
 * The pitch and noise envelopes are the SAME machine at two bases, and so are the volume and noise
 * LFOs. Naming the strides is what lets one helper serve both instead of the body being written
 * twice; the offsets above are the pin, these are the arithmetic between them. */
#define SND_ENV_STEP1_FROM_PHASE    0x02u /* 0x26-0x24 == 0x52-0x50 */
#define SND_ENV_STEP2_FROM_PHASE    0x0au /* 0x2e-0x24 == 0x5a-0x50 */
#define SND_ENV_RELEASE_FROM_PHASE  0x12u /* 0x36-0x24 == 0x62-0x50 */
#define SND_ENV_TARGET_FROM_STEP    0x04u /* each segment's target follows its own step */
#define SND_LFO_STEP_FROM_LIMIT     0x04u /* 0x1e-0x1a == 0x6a-0x66 */
#define SND_LFO_DELAY_FROM_LIMIT    0x08u

/* ================================================================================================
 * The envelope phases, the volume peak, and the two output clamps
 * ============================================================================================= */

#define SND_PHASE_IDLE     0u
#define SND_PHASE_ATTACK   1u  /* segment 1 for the pitch/noise machines */
#define SND_PHASE_DECAY    2u  /* segment 2 */
#define SND_PHASE_HOLD     3u  /* stores nothing — the sustain */
#define SND_PHASE_RELEASE  4u

#define SND_VOL_ENV_PEAK    0x000f0000  /* the attack's hard-wired target (`cmp.l #$f0000` @ 0x145d6)
                                         * and what a no-envelope trigger sets the accumulator to */
#define SND_VOL_MAX         0x0f        /* `cmp.w #$f,d0` @ 0x14676 — the PSG's 4-bit level */
#define SND_TONE_PERIOD_MAX 0x0fff      /* `cmp.w #$fff,d0` @ 0x14772 — the PSG's 12-bit period */
#define SND_NOISE_PERIOD_MAX 0x1f       /* `cmp.b #$1f,d0` @ 0x14854 — see sound.c, it is a BYTE
                                         * compare on a word and the quirk is reproduced */
#define SND_PITCH_MOD_SHIFT 4           /* `asl.l #4` @ 0x14760: period = base * (1 + delta/4096) */
#define SND_VOL_ENV_SHIFT   8           /* `asr.l #8` @ 0x14670 before the scale multiply */

/* The MIDI window `sound_play` folds a note into before indexing snd_note_period, and the octave it
 * steps by (`subi.w #$c` / `addi.w #$c` @ 0x143d0 / 0x143e0). */
#define SND_NOTE_MAX       0x6c
#define SND_NOTE_MIN       0x18
#define SND_NOTE_OCTAVE    0x0c

/* ================================================================================================
 * The YM2149 registers this engine names, and the mixer bits it clears
 * ============================================================================================= */

#define PSG_REG_TONE_LOW(v)   (2u * (v))      /* `add.b d1,d1` @ 0x1477e */
#define PSG_REG_TONE_HIGH(v)  (2u * (v) + 1u) /* `addq.b #1,d1` @ 0x14786 */
#define PSG_REG_NOISE         6u
#define PSG_REG_MIXER         7u
#define PSG_REG_VOLUME(v)     (8u + (v))      /* `addq.b #8,d1` @ 0x14680 */
#define PSG_REG_SELECT_MASK   0x0fu   /* `and.b #$f,d1` @ 0x1495c */
#define PSG_MIXER_TONE_OFF(v)  (1u << (v))
#define PSG_MIXER_NOISE_OFF(v) (8u << (v))

/* ================================================================================================
 * The cores and their glue (src/sound.c)
 * ============================================================================================= */

int16_t sound_play(uint8_t *image, uint32_t definition, int16_t voice, int16_t volume,
                   int16_t note, int16_t priority);
void    sound_stop_voice(uint8_t *image, int16_t voice);
void    sound_release_voice(uint8_t *image, int16_t voice);
int16_t sound_voice_priority(const uint8_t *image, int16_t voice);
void    sound_stop_all(uint8_t *image);
void    timer_c_sound_isr(uint8_t *image);
uint8_t psg_gate(uint16_t reg, int16_t value, uint16_t mask);
uint8_t trap9_psg_handler(uint16_t reg, int16_t value, uint16_t mask);
void    install_sound_vectors(uint8_t *image);
void    remove_sound_vectors(uint8_t *image);
void    sound_start(uint8_t *image, CallerAddressRegisters saved);
void    sound_stop(uint8_t *image, CallerAddressRegisters saved);

#endif /* BG_SOUND_H */
