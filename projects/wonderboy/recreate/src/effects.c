/* effects.c — the 29 leaf routines at $10200..$103e7: the effect handlers the object dispatcher at
 * $ddec/$de62 jumps to through `effect_handler_table` ($1023a), plus the six `set_state_*` stubs
 * sitting immediately above that table.
 *
 * They are the smallest functions in the game — one to four instructions each, no branches bar the
 * two clamps, no callees, no hardware, no OS. Nothing reads them back, so the whole observable
 * effect of every one is a word or two of game state, which is exactly what the memory differential
 * sees; test/test_effects.py runs each against the original.
 *
 * WHAT THE NAMES DO AND DO NOT CLAIM. Every name here is ../names.txt's, and every one is at the
 * MECHANISM: `effect_set_bd66_3` says a 3 goes into $bd66, not what a 3 there means. The bodies are
 * read and reproduced; the meaning of the state is open, and wonderboy.h records what each global
 * is written and read WITH — which is as far as the evidence goes. Resist naming these for the
 * "collect an item" reading until a reader is followed all the way down.
 *
 * The one thing worth reading twice is the clamp, which is signed and 16-bit: see
 * effect_add_clamped below.
 *
 * ONE ADDRESS HERE COMES OUT OF MEMORY rather than out of the instruction stream — the record
 * list's write pointer — so effect_push_record inherits the divergence class src/rad.c's comment
 * registers: off the mapped image the oracle's shim drops the write while this C indexes a host
 * buffer, which is undefined behaviour. Every case in test/test_effects.py seeds a pointer well
 * inside the image, so the battery never enters that territory; bounding it would be a kit change.
 */
#include "machine.h"
#include "effects.h"
#include "wonderboy.h"

/* ---- the HUD slots ---------------------------------------------------------------------------
 *
 * `move.w #$Nff,slot.l` writes both bytes of a slot at once: the value in the high byte, and the
 * "changed" byte below it that makes the redraw scanner at $b8f0 pick the slot up next frame.
 * Splitting it into two byte stores would be equivalent here and is deliberately not done — the
 * original's single word write is what makes the pair atomic against an interrupt.
 */
static void hud_slot_set(uint8_t *image, uint32_t slot, uint8_t value) {
    wr16(image + slot, (uint16_t)((value << 8) | WB_HUD_SLOT_CHANGED));
}

void set_state_bbc8_1ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC8, 1); }
void set_state_bbc8_2ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC8, 2); }
void set_state_bbc8_3ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC8, 3); }
void set_state_bbc8_4ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC8, 4); }
void set_state_bbc8_6ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC8, 6); }
void effect_set_bbc2_80ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC2, 0x80); }
void effect_set_bbbe_05ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBBE, 5); }
void effect_set_bbc0_05ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC0, 5); }
void effect_set_bbc6_01ff(uint8_t *image) { hud_slot_set(image, WB_HUD_SLOT_BBC6, 1); }

/* The one stub that is not a HUD slot, and the only one encoded with a short absolute operand
 * (`31fc ffff 6f9c`, 8 bytes against the others' 10). $ffff is this game's usual "true". */
void set_state_6f9c_ffff(uint8_t *image) { wr16(image + WB_STATE_WORD_6F9C, 0xffffu); }

/* ---- the state words -------------------------------------------------------------------------
 *
 * `move.w #n,state.l` and nothing else. The ordinals are the whole content of each routine — they
 * are what its ../names.txt name records — so they stay inline rather than becoming a constant that
 * would only restate its own value.
 */
void effect_set_bd6a_1(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD6A, 1); }
void effect_set_bd6a_2(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD6A, 2); }
void effect_set_bd6a_3(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD6A, 3); }
void effect_set_bd6a_4(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD6A, 4); }
void effect_set_bd66_1(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD66, 1); }
void effect_set_bd66_2(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD66, 2); }
void effect_set_bd66_3(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD66, 3); }
void effect_set_bd66_4(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD66, 4); }
void effect_set_bd66_5(uint8_t *image) { wr16(image + WB_EFFECT_STATE_BD66, 5); }

/* The $bd68 trio alone stamps $21e4 first, with the same 2 every time — the ordinal that varies is
 * the second word, so the pair reads as "mode 2, variant n". */
static void effect_set_bd68(uint8_t *image, uint16_t variant) {
    wr16(image + WB_EFFECT_STATE_21E4, 2);
    wr16(image + WB_EFFECT_STATE_BD68, variant);
}

void effect_set_bd68_1(uint8_t *image) { effect_set_bd68(image, 1); }
void effect_set_bd68_2(uint8_t *image) { effect_set_bd68(image, 2); }
void effect_set_bd68_3(uint8_t *image) { effect_set_bd68(image, 3); }

/* ---- the meter -------------------------------------------------------------------------------
 *
 * `move.w meter,d0 / addq.w #n,d0 / cmp.w max,d0 / bgt clamp`. Two details the C has to keep:
 *   * the add is 16-BIT and wraps, so a meter close to $7fff comes out NEGATIVE rather than large;
 *   * `bgt` is SIGNED, so that wrapped value then compares BELOW the maximum and is stored as is.
 * Neither is reachable from the meter's real range ($18..$28), but the port is of the instruction,
 * not of the range — test/test_effects.py seeds both sides of the boundary and the wrap.
 * `bgt` is also STRICT — a raise landing EXACTLY on the maximum takes the store arm — and the `>`
 * below reproduces that. No case can hold it, though: at raised == max both arms store the same
 * word, so `>` and `>=` are observationally equivalent here. Faithful, not pinned; STATUS.md
 * registers it as an equivalence rather than as a coverage hole.
 */
static void effect_add_clamped(uint8_t *image, uint16_t amount) {
    uint16_t raised = (uint16_t)(be16(image + WB_HUD_METER_VALUE) + amount);
    int16_t max = (int16_t)be16(image + WB_HUD_METER_MAX);
    wr16(image + WB_HUD_METER_VALUE, (int16_t)raised > max ? (uint16_t)max : raised);
}

void effect_add4_clamped_b6fa(uint8_t *image) { effect_add_clamped(image, 4); }
void effect_add2_clamped_b6fa(uint8_t *image) { effect_add_clamped(image, 2); }

/* `move.w max,meter` — one memory-to-memory move, no test, so it fills the meter even from above
 * the maximum. The two clamps above cannot: the meter only ever moves to `max` through this one. */
void effect_restore_b6fa_to_max(uint8_t *image) {
    wr16(image + WB_HUD_METER_VALUE, be16(image + WB_HUD_METER_MAX));
}

/* ---- the record list -------------------------------------------------------------------------
 *
 * `addq.l #2,ptr / movea.l ptr,a1 / move.w #record,(a1)`. The pointer is advanced BEFORE it is
 * re-read, so the record lands at the NEW pointer and the list grows upward — and the pointer ends
 * up addressing the newest record rather than the next free slot.
 *
 * The record is a word whose two byte fields are not identified; ../names.txt names each routine
 * for the constant it pushes because that is all that is established, so the constant stays inline
 * here for the same reason (a `#define EFFECT_RECORD_0605 0x0605u` would restate its own value).
 */
static void effect_push_record(uint8_t *image, uint16_t record) {
    /* addr_add, not `image + ptr + 2`: the advance wraps at 32 bits on the 68000 (machine.h). */
    uint32_t write_ptr = addr_add(be32(image + WB_EFFECT_RECORD_WRITE_PTR), WB_EFFECT_RECORD_LEN);
    wr32(image + WB_EFFECT_RECORD_WRITE_PTR, write_ptr);
    wr16(image + write_ptr, record);
}

void effect_push_record_0605(uint8_t *image) { effect_push_record(image, 0x0605); }
void effect_push_record_0508(uint8_t *image) { effect_push_record(image, 0x0508); }
void effect_push_record_0705(uint8_t *image) { effect_push_record(image, 0x0705); }
void effect_push_record_0803(uint8_t *image) { effect_push_record(image, 0x0803); }
