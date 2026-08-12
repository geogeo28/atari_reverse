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

/* ---- THE TICK ITSELF: the pattern stepper ($18106) and the body that drives it ($17ca0) ---------
 *
 * These two close the tier. $18106 walks one channel's pattern byte stream; $17ca0 is the per-VBL
 * tick minus its 44-byte tempo head, and it calls everything above.
 */

/* How a TICK SUB-PHASE ended. Both `snd_channel_step` and the tick's own fade return it, and the
 * fade reaches SND_STEP_SONG_ENDED without any channel having stepped — so it is not a property of
 * the pattern walk but of the two places the module can decide a song is over.
 *
 * The pattern walk's own reason is that one of the twenty-four opcodes does not return.
 *
 * Opcode $8e is `addq.l #4,sp / sf $17c63 / bra.w stub+28` at $18014: it throws the stepper's OWN
 * return address away and tail-jumps into the stop chain, so the stop's `rts` lands in the TICK's
 * caller and neither the rest of the row nor the rest of the tick ever runs. There is no C for
 * unwinding a frame, so the stepper reports it and the tick acts on it — which is also why a
 * differential may enter $18106 directly only on a stream with no $8e in it: entered there the
 * `addq.l #4,sp` pops the runner's own sentinel and the `rts` goes to nothing. test_sound.py pins
 * the propagation from the TICK's entry, where the stack has the frame the instruction expects.
 */
typedef enum {
    SND_STEP_RETURNED = 0,      /* a `rts` ($18186, $18190, $1819e, $181a4) or a fade with more to run */
    SND_STEP_SONG_ENDED = 1,    /* opcode $8e, or the fade's two `beq.w $18016` — see above */
} snd_step_result;

/* d1 at each of the tick's three `bsr.w $18106`, which this reconstruction does not model.
 *
 * The ONLY thing that reads it is pattern opcode $97, which hands it to snd_trigger_effect as a
 * CHANNEL without ever setting it — the module's one latent defect (../notes/sound_module_recon.md
 * §8). At the tick's call sites d1 holds whatever snd_sfx_tick left, and snd_sfx_tick's outgoing
 * registers are not reconstructed, so the tick passes this instead. It is sound because $97 occurs
 * ZERO times in all 106 patterns of all 17 songs: the tick can never reach the read. A case that
 * seeded a $97 into a pattern the TICK walks would be comparing against a register nothing models,
 * and none does — the defect is pinned from snd_channel_step's own entry, where d1 is the case's.
 */
#define SND_TRIGGER_CHANNEL_UNMODELLED 0u

/* $18106 — one channel's pattern step. `record` is the original's a0 (an ADDRESS, like $18208's) and
 * `sfx_channel` its d1.
 *
 * Two paths and nothing between them. While the note-duration countdown at +27 is still turning, the
 * step applies the PITCH SLIDE to the current note and returns. On the tick it reaches zero it clears
 * the flags, picks the pattern cursor up out of +2 and reads bytes until one ends the row: $00..$7f
 * is a note (which reloads the envelope), $80..$b7 dispatches through the 24-entry jump table at
 * $17fa4, $b8..$cf selects an arpeggio, $d0..$df an instrument and $e0..$ff a duration. Only two
 * opcodes end the row on their own ($80 and $8f); the rest loop back for another byte.
 *
 * IT INHERITS a3. Like $1aaca and $18208 — and unlike everything the stub table reaches — its first
 * instruction is not a `lea`, so a differential entering it must seed the module base.
 *
 * THE JUMP TABLE IS NOT BOUNDS-CHECKED and the range decoder's own boundary is $b8, not $98: a byte
 * from $98 to $b7 indexes PAST the 24 entries, reads a word of the handlers' own code as a table
 * entry and jumps wherever it points. src/sound.c reproduces the 24 the table holds and nothing
 * else; no pattern byte in the shipped data is one (all 106 patterns decode with zero out-of-range
 * opcodes), and ../STATUS.md records it as this batch's one unported branch. */
snd_step_result snd_channel_step(uint8_t *image, uint32_t record, uint32_t sfx_channel);

/* $17ca0 — the per-VBL tick, entered BELOW its tempo selector.
 *
 * WHY THE BODY IS A FUNCTION OF ITS OWN. The 44 bytes above it are the tempo selector, and they are
 * the module's ONLY hardware-steered code: `snd_music_tick` below reads the two machine bytes and
 * writes WB_SND_TICK_DROP_VALUE, then falls straight into this. Split so a case can enter here on a
 * POKED drop byte — all three of the values the head can write, with no declaration to make — and
 * enter the head with `hw_seed=` to run the whole tick. Both halves are pinned, and the tiling case
 * in test_sound.py is what says the head's write and this body's read meet on the same byte.
 *
 * The body in order: the gate (the engine flag, or ANY of the four bytes the `tst.l` covers at
 * WB_SND_SFX_ACTIVE_FLAGS), the drop accumulator (whose CARRY skips the entire tick, SFX and chip
 * included), snd_sfx_tick, the fade, the row step through snd_channel_step, the per-channel period
 * and volume through snd_channel_period_and_volume, the SFX mixdown over the module's PSG shadow,
 * and the chip write.
 *
 * IT CAN END THE SONG AND NOT COME BACK. Both the fade reaching zero and pattern opcode $8e enter
 * $18016, which clears WB_SND_SONG_LOADED and tail-jumps to stub +28 — so `snd_stop` runs and its
 * `rts` returns to the tick's caller with the rest of the tick unrun. Reproduced as an early return.
 *
 * IT DRIVES THE CHIP, so a case must declare the mixer with `psg_seed`: $17f08 reads register 7 back
 * and merges only the bits the unlocked channels own, exactly as snd_psg_silence's `ori` does. */
void snd_music_tick_body(uint8_t *image);

/* $17c74 — the whole per-VBL tick: the 44-byte TEMPO SELECTOR, and then the body above.
 *
 * THE TWO READS ARE INPUTS OF THE RUN, not consequences of it. `btst #7,$fffa01` asks whether a
 * MONOCHROME monitor is attached and `btst #1,$ff820a` whether the shifter is running at 50 Hz, and
 * between them they pick how many of every 256 ticks the body drops. Both addresses are outside the
 * memory image, so nothing in an image differential can see them and a fabricated 0 would steer BOTH
 * cores down the mono arm together — the `$ffff820a` defect BuggyBoy shipped green to real hardware.
 * So the reconstruction reads them through the kit's seeded model (`hw_read8`, TRAP_MODEL.md
 * "Phase 7") and a case DECLARES the machine it means with `hw_seed=`; one that declares nothing is
 * refused rather than served.
 *
 * IT ESTABLISHES a3. `lea $1738c(pc),a3` is this routine's first instruction — the one place in the
 * tick tier where the module base is set rather than inherited — so a differential entering here
 * seeds no a3 where one entering $17ca0, $18106, $18208 or $1aaca must.
 *
 * WHAT IS STILL NOT PINNED, and cannot be by a differential: that a real ST answers these bytes the
 * way a case declares. `hw_seed={$fffa01: $b0, $ff820a: $02}` states "a 50 Hz colour ST with the FDC
 * and ACIA lines idle" — the kit's own audio-capture profile, and a documented claim about hardware
 * rather than a differential result. */
void snd_music_tick(uint8_t *image);

/* $17b3a — stub +0: LOAD A SONG AND ARM THE ENGINE. `song_id` is d0, and only its low BYTE, which
 * `ext.w` sign-extends: 0..WB_SND_SONGS-1 are the shipped songs and everything else is out of bounds
 * in one direction or the other, unchecked (see the body).
 *
 * IT IS WHAT MAKES THE MODULE'S MUTABLE BANDS DEFINED. snd_music_tick and everything under it read
 * three 48-byte channel records the .PRG ships holding residue from a run at another load base; this
 * is the routine that writes them, so a tick that has been preceded by one of these needs no seeding
 * of $17bc6..$17c71 where an isolated tick case does.
 *
 * IT STOPS FIRST, through the stub at +28 — so the four PSG accesses `snd_stop` makes are on this
 * path too, and a case declares the mixer with `psg_seed` exactly as a stop-chain case does. */
void snd_play_song(uint8_t *image, uint32_t song_id);

#endif /* WONDERBOY_SOUND_H */
