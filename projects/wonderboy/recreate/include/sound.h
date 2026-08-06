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

#endif /* WONDERBOY_SOUND_H */
