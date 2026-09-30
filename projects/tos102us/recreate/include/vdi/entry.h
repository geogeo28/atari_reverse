/* vdi/entry.h — the two doors every VDI and Line-A call comes in by, and the VDI's dispatcher (`src/vdi/entry.c`).
 *
 *   $fc9f0c linea_dispatch   the Line-A exception (vector $28): the $Axxx word's low twelve bits, the stacked PC
 *                            stepped past it, 0..15 served through a longword table with D3-D7/A3-A5 saved round
 *                            the `jsr`, anything higher returned from untouched — `rte` either way
 *   $fc9f9e vdi_entry        `trap #2`'s VDI arm (`jsr` from $fc4ebc), D1 = the parameter block: its five pointers
 *                            into Line-A with PTSIN replaced by a capped COPY, the dispatcher, the caller's point
 *                            count given back, the word at VDI_RESULT answered — D1-A6 saved round the lot
 *   $fca9f6 vdi_dispatch     Alcyon C: contrl[2]/[4] and VDI_RESULT cleared; for every opcode but the two opens the
 *                            workstation whose handle is contrl[6] made current and its fields copied into Line-A
 *                            (an unknown handle returns having called nothing); the function the opcode tables name
 *
 * THE TWO DOORS SHIP AS THE ROM's OWN INSTRUCTIONS (`src/vdi/entry.S`, `transcribed.h`): each is an ENTRY a
 * vector or a trap arm reaches with a convention no C function has — an exception frame and `rte`, and a register
 * file kept whole but for D0 — which is `vdi_rom_timer_tick`'s reason. Their C twins below are what Tier 1 proves the
 * ORDER of every read and store against. The dispatcher is compiled C in the ROM and ships as C.
 *
 * THE CALL OUT. Each door and the dispatcher `jsr` a routine a TABLE names, which off target is 68000 code the host
 * cannot run: the host build leaves through `staged_call.h`'s hooks, which a case binds to the reconstruction (or to
 * a staged routine's effect) by address. The Line-A door hands the primitive D0/D1/A0 both ways through the
 * register-carrying shape; a VDI function takes and answers nothing in a register, so the dispatcher's is the bare
 * `movea.l <table entry>,a0 / jsr (a0)` shape.
 */
#ifndef TOS102US_VDI_ENTRY_H
#define TOS102US_VDI_ENTRY_H

#include <stdint.h>

#include "staged_call.h"

/* $fc9f0c: the exception frame at `frame` (the SR, then the PC of the $Axxx word), the primitive handed and answering
 * `registers` (D0, D1, A0 — `STAGED_REGISTERS` order). */
void linea_dispatch(uint8_t *image, uint32_t frame, uint32_t registers[STAGED_REGISTERS]);

/* $fc9f9e: the parameter block at `parameter_block` (D1). Answers the WORD at VDI_RESULT — what the ROM's
 * `move.w $171e,d0` leaves in D0's low half. The high half is whatever the dispatcher's walk and the function left
 * there: every link the walk follows is also moved into D0 (`move.l a4,d0`, $fcaa38), so a lookup one or more
 * links along leaves the found record's high word (0 for a RAM record). No caller reads it — the trap door ($fc4ec6) `rte`s and
 * the AES's `trap #2` ($fecb6a) takes D0.w — so the C twin answers the word alone. */
uint16_t vdi_entry(uint8_t *image, uint32_t parameter_block);

/* $fca9f6: the call the Line-A pointers describe. */
void vdi_dispatch(uint8_t *image);

#endif /* TOS102US_VDI_ENTRY_H */
