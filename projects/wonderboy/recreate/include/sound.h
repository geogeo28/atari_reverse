/* sound.h — the sound module's SFX trigger and the stub that calls it (src/sound.c).
 *
 * THE FIRST PORT INSIDE THE SOUND MODULE. Everything at $17adc..$1abc8 is one self-contained,
 * PC-RELATIVE replayer that the rest of the game reaches ONLY through the stub table at its head
 * (`lea $17adc.l,a1 / jsr N(a1)`); ../notes/sound_module_recon.md maps the whole of it. Two of its
 * routines are reconstructed here, and they are the two that touch nothing but RAM:
 *
 *   $17b14  the stub-table entry at +56 — `movem.l d0-a6,-(a7) / bsr / movem.l (a7)+ / rts`
 *   $1a48a  the trigger itself, which loads one channel's SFX state from a 14-byte descriptor
 *
 * ...and batch 21b added the STOP CHAIN, which is the first ported code in this project that drives
 * the chip: `snd_stop` -> `snd_stop_all_sfx` -> `snd_psg_silence`, three routines joined by `bra.w`
 * rather than by calls. It became portable when the kit gained a seeded PSG read model
 * (tools/recreate_kit/TRAP_MODEL.md, "Phase 6"): $17f3e reads the mixer back and `ori.b #$3f`
 * preserves bits 6-7, so before the model there was no correct value to serve and the run was
 * refused. A case declares those bits with `psg_seed={7: …}` and both cores are served the same
 * byte; the ordered access ledger and the register file the run leaves are compared alongside the
 * image, since none of it is IN the image.
 *
 * WHAT THIS DELIBERATELY DOES NOT MODEL. The trigger only ARMS a channel. Everything that makes a
 * sound is the per-VBL tick at $17c74, which reads this state, writes the PSG through $ff8800 and
 * needs supervisor mode — none of which a memory differential can see. So a green suite here says
 * the right bytes landed in the right module fields, and says nothing about what is heard.
 *
 * NOR THE SUPERVISOR WINDOW. snd_psg_silence brackets its chip writes with
 * `move sr,d2 / move #$2700,sr … move d2,sr`, i.e. it masks interrupts so the tick cannot write the
 * chip mid-sequence. C has no analogue and the reconstruction makes none: the oracle enters every
 * run at SR = $2700 already (TRAP_MODEL.md, "The entry state every run begins from"), so the mask
 * is a no-op there and the save/restore is observable only as the oracle's own d2. test_sound.py
 * asserts that d2 rather than reproducing it.
 *
 * REGISTER ARGUMENTS, as everywhere else in this reconstruction: Ghidra never entered the module at
 * all — it decompiled none of $17adc..$1abc8 — so both interfaces are read off the disassembly. The
 * register each argument arrives in is stated twice and nowhere else: in the comments below, and as
 * a `cmt` line on the routine in ../names.txt. Each register is one `uint32_t` so that the operand
 * size the original applies to it — and both of these apply a BYTE one — happens here, where a
 * differential case can pin it.
 */
#ifndef WONDERBOY_SOUND_H
#define WONDERBOY_SOUND_H

#include <stdint.h>

/* $1a48a — d0's low BYTE is the SFX id and d1's low byte the channel (0 = A, 1 = B, anything else
 * = C). Both are sign-extended, and NEITHER is bounds-checked: an id outside 0..WB_SND_SFX_IDS-1
 * indexes the pointer table past its end, and a NEGATIVE one indexes it backwards. $6b46
 * (actor_damage_template_hitpoints) passes d1 = 1, so the B arm is LIVE code reached from the
 * shipped game; every other call site passes 0, so only C is dead, and it is reproduced anyway. */
void snd_trigger_effect(uint8_t *image, uint32_t effect_id, uint32_t channel);

/* $17b14 — stub +56, and the only way anything outside the module reaches the trigger. It exists to
 * PRESERVE REGISTERS: its `movem` pair saves and restores d0-d7/a0-a6, so a caller that had live
 * values in them (`$bbca` does not; `$17fd4`, the pattern opcode, does) gets them all back. C has
 * no analogue for that, so the claim lives in the differential — test_sound.py compares every
 * register the oracle reports against the value the run was entered with. */
void snd_call_trigger_effect(uint8_t *image, uint32_t effect_id, uint32_t channel);

/* $17f30 — silence the chip: read WB_PSG_REG_MIXER back, `ori` WB_PSG_MIXER_ALL_OFF into it, and
 * zero the three volume registers. NO IMAGE ARGUMENT, because it touches no image byte at all: its
 * whole output is the four PSG accesses plus the read, which live on psg.h's ledger. Entered by
 * `bra.w` from snd_stop_all_sfx and reachable directly only because ../names.txt names it. */
void snd_psg_silence(void);

/* $1aaea — stub +70. Clear the three WB_SND_SFX_ACTIVE_FLAGS (as a `clr.l`, so the unnamed fourth
 * byte goes too), set the module's shadow of the mixer to WB_PSG_MIXER_ALL_OFF and zero its three
 * volume shadows, then TAIL-JUMP to snd_psg_silence — so the shadow ends holding exactly what the
 * chip was just given. */
void snd_stop_all_sfx(uint8_t *image);

/* $17f24 — stub +28. Clear WB_SND_ENGINE_ENABLED and tail-jump to snd_stop_all_sfx. Twelve bytes,
 * and the `bra.w` is why the module's stop is one routine to a caller and three to a reader. */
void snd_stop(uint8_t *image);

/* ---- THE TICK TIER: what snd_music_tick ($17c74) calls, in the order it calls them --------------
 *
 * The tick's own body is NOT here. What is, is the three routines below it that touch no port and
 * make no call of their own — the SFX engine it runs FIRST (before any music, which the $17c74 plate
 * had backwards until this batch), the PRNG that engine steps, and the per-channel pass that turns a
 * music channel's record into the period and volume the tick hands the chip.
 *
 * ALL THREE RUN ON MUTABLE IMAGE THAT THE .PRG SHIPS DIRTY. $17bc6..$17c71, $18352..$1836a,
 * $1aa7c..$1aac9 and $1aae6..$1aae9 hold residue from a run at another load base (the stale pointer
 * at $17bc6+2 is the clearest one), so nothing here may be entered on the image's own bytes: a
 * caller seeds the band, or reaches it through snd_play_song / snd_trigger_effect.
 */

/* $1aaca — the SOUND MODULE's PRNG, which is not the game's (src/rng.c owns that one). One 32-bit
 * shift left through the X flag, with bit 3 XOR bit 6 of the top byte entering at the bottom.
 *
 * Returns the BYTE the original leaves in d0's low byte — the state's new top byte. d0's upper three
 * bytes are the caller's and are not reproduced here (a `uint8_t` cannot carry them): every
 * operation in the body is a `.b` one, and test_sound.py asserts that on the ORACLE's d0. The one
 * caller, snd_sfx_tick, ignores the value — each arm re-reads WB_SND_PRNG_STATE + its own channel
 * number instead, so the three channels take three DIFFERENT bytes of the same state.
 *
 * IT IS STEPPED EVERY TICK, unconditionally, and snd_play_song does not reset it. Any case that
 * compares two ticks therefore seeds WB_SND_PRNG_STATE itself. */
uint8_t snd_prng_step(uint8_t *image);

/* $1a5da — stub +14's FIRST callee: step the PRNG, then run each of the three SFX channels whose
 * WB_SND_SFX_ACTIVE_FLAGS byte is set.
 *
 * CHANNEL A'S FLAG IS TESTED TWICE. `tst.b / bmi` returns from the WHOLE routine when it is
 * negative — so B and C do not run either — and only then does `beq` skip A alone. B and C get the
 * `beq` and no sign test, so a negative flag runs their arm. Nothing in the shipped code writes a
 * negative flag (the trigger `sf`s it to 0 and `move.b #1`s it to 1), which is why the `bmi` is
 * reached only from a seeded state.
 *
 * The three arms at $1a602/$1a6bc/$1a776 are 186 bytes each and identical bar their offsets, so they
 * are one parametrised body here exactly as snd_trigger_effect's are — and the differential still
 * enters each at its own address. `rts` for all of them, and for the entry, is the ONE at $1a5d8
 * that ../names.txt used to call an orphan. */
void snd_sfx_tick(uint8_t *image);

/* The two registers $18208 hands back. Both are read by the tick as PARTS of a register, so both
 * carry bits the routine never wrote. */
typedef struct {
    uint32_t period;   /* d0. IN as well as out: every write to it is a `.w` or a `.b`, so the
                        * caller's HIGH WORD comes back untouched. Its low word is the note period
                        * the tick splits across two PSG registers. */
    uint32_t volume;   /* d1. A pure OUTPUT — `moveq #0,d1` destroys the entry value. Its low byte is
                        * WB_SND_CH_VOLUME and its SECOND byte is the portamento's own leftover
                        * scratch, which the caller's `sub.b` never reads and the differential
                        * compares anyway; above that it is always zero, because nothing in the body
                        * writes d1 wider than a word. */
} snd_channel_mix;

/* $18208 — turn one music channel's 48-byte record into a period and a volume.
 *
 * `record` is the original's a0: the ADDRESS of one channel's 48-byte block, which the tick supplies
 * as WB_SND_MUSIC_CHANNEL_STATE + n * WB_SND_MUSIC_CHANNEL_LEN. It is an ADDRESS and not a channel
 * NUMBER — unlike the `channel` the SFX half of src/sound.c indexes its blocks by — because that is
 * what a0 carries. `mix` is d0/d1, in and out.
 *
 * Six arms over one channel, in the order the body runs them: the volume ENVELOPE (a peeked byte,
 * so a negative one holds the last value and moves no cursor), the note plus the global TRANSPOSE
 * and the channel's DETUNE, the ARPEGGIO byte and its loop, the period-table lookup, PORTAMENTO
 * (whose offset is doubled once per octave the note sits below the table's reference index), and
 * VIBRATO. It ends by publishing the noise period and merging this channel's bits into the module's
 * shadow of the PSG mixer — so it writes module globals as well as the record, and is not a pure
 * function of its argument.
 *
 * THE PERIOD TABLE ALIASES. The index is `add.b d0,d0`, a BYTE double, and nothing bounds it to the
 * WB_SND_NOTE_PERIOD_ENTRIES the table holds: a note from 96 to 127 reads the 32 ENTRIES — 64 bytes
 * — past the table (the arpeggio pointer table and the first arpeggio streams) as though they were
 * periods, and a note from 128 up wraps back to the table's start. Reproduced; the read stays inside
 * the image by construction, since the base is a constant and the index is a byte. */
void snd_channel_period_and_volume(uint8_t *image, uint32_t record, snd_channel_mix *mix);

#endif /* WONDERBOY_SOUND_H */
