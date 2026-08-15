/* effects.c — the 43 leaf routines behind the game's TWO effect dispatch tables: the 29 at
 * $10200..$103e7 that the object dispatcher at $ddec/$de62 jumps to through `effect_handler_table`
 * ($1023a) — plus the six `set_state_*` stubs sitting immediately above that table — and the 14 at
 * $105e4..$10799 that behaviour slot 38 jumps to through `pickup_effect_table` ($105ac).
 *
 * They are the smallest functions in the game — one to seven instructions each, no branches bar the
 * two clamps and the attack level's gate, no hardware, no OS. Nothing reads them back, so the whole
 * observable effect of nearly every one is a word or two of game state, which is exactly what the
 * memory differential sees; test/test_effects.py runs each against the original.
 *
 * ONE OF THE 43 HAS A CALLEE: `pickup_effect_vanish_followed` asks `followed_actor_record` which
 * record it is writing, so it is the only routine here that touches a record rather than a global
 * and the only one whose destination comes out of memory (hence bus.h). The file's "no callees" is
 * true of the other forty-two.
 *
 * WHAT THE NAMES DO AND DO NOT CLAIM, AND WHERE THAT CHANGED. Every name here is ../names.txt's, and
 * the 29 are named at the MECHANISM: `effect_set_bd66_3` says a 3 goes into $bd66, not what a 3
 * there means. The bodies are read and reproduced; the meaning of that state is open, and
 * wonderboy.h records what each global is written and read WITH — which is as far as the evidence
 * goes. Resist naming those for the "collect an item" reading until a reader is followed down.
 *
 * The 14 ARE named for what they grant, and the difference is evidence and not appetite: each one
 * POSTS A MESSAGE naming the item, which is the reader followed down. That is batch 17's method
 * (the helmet and the gauntlet slots were identified from the messages their own paths post)
 * applied to twelve more, and two of them identify a HUD slot nothing else names. The one that
 * posts no message is still `pickup_effect_grant_bbc4`.
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
#include "actor.h"
#include "bus.h"
#include "effects.h"
#include "text.h"
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

/* The four constants are wonderboy.h's rather than inline literals as of batch 38, and that is a
 * change of evidence and not of taste: the four pickup grants below push the SAME four words and
 * post a message naming each one, so the record is no longer a number with nothing to say about
 * itself. Two files spelling the same four words is exactly the drift a shared #define prevents. */
void effect_push_record_0605(uint8_t *image) {
    effect_push_record(image, WB_PICKUP_RECORD_FIRE_BALLS);
}

void effect_push_record_0508(uint8_t *image) {
    effect_push_record(image, WB_PICKUP_RECORD_BOMBS);
}

void effect_push_record_0705(uint8_t *image) {
    effect_push_record(image, WB_PICKUP_RECORD_WIND_SPOUTS);
}

void effect_push_record_0803(uint8_t *image) {
    effect_push_record(image, WB_PICKUP_RECORD_LIGHTNING);
}


/* ---- the PICKUP effects ($105e4..$10799) ------------------------------------------------------
 *
 * The second dispatch table's handlers, and the shape they all share: whatever the grant is, the
 * routine ends `move.b #id,$c030.l / move.w #$32,$c034.l / rts`. Fourteen entries, one of them a
 * bare `rts`; every other routine here is one of the three grants below plus that post.
 */

/* The tail is `text_post_message` (text.h) as of batch 40. It was a helper HERE and inline in three
 * other modules, on the argument that "three sites across three modules is an exported symbol to
 * save one `wr16`"; the player's frame made it four spellings of two stores, and text.h's
 * `static inline` exports nothing, so the objection no longer costs anything. src/scene.c's writer
 * still stands apart — it takes a LIFETIME, because its speech arm posts zero. */

static void grant_slot(uint8_t *image, uint32_t slot, uint8_t value, uint8_t message) {
    hud_slot_set(image, slot, value);
    text_post_message(image, message);
}

static void grant_record(uint8_t *image, uint16_t record, uint8_t message) {
    effect_push_record(image, record);
    text_post_message(image, message);
}

/* $105e4 — two bytes, and the byte that bounds WB_PICKUP_EFFECT_TABLE from above. It is a
 * reconstruction like any other for `actor_behavior_type38_pickup`'s dispatch: without a symbol
 * here, index 0 would have to be spelt as a refusal, which is a different answer. */
void pickup_effect_none(uint8_t *image) { (void)image; }

void pickup_effect_grant_bbc4(uint8_t *image) {
    /* The ONE grant that posts nothing, so nothing names WB_HUD_SLOT_BBC4 — its meaning is still
     * open (../names.txt) and this handler does not close it. What it does close is that slot's own
     * plate, which used to credit the address to code no batch had recovered: $105e6 is one of the
     * two writers and it is right here. */
    grant_slot(image, WB_HUD_SLOT_BBC4, WB_PICKUP_SLOT_BBC4_VALUE, WB_TEXT_REQUEST_NONE);
}

void pickup_effect_grant_wing_boots(uint8_t *image) {
    grant_slot(image, WB_HUD_SLOT_BBC2, WB_PICKUP_SLOT_WING_BOOTS_VALUE, WB_TEXT_MESSAGE_WING_BOOTS);
}

void pickup_effect_grant_helmet(uint8_t *image) {
    grant_slot(image, WB_HUD_SLOT_BBBE, WB_PICKUP_SLOT_HELMET_VALUE, WB_TEXT_MESSAGE_HELMET);
}

void pickup_effect_grant_gauntlet(uint8_t *image) {
    grant_slot(image, WB_HUD_SLOT_BBC0, WB_PICKUP_SLOT_GAUNTLET_VALUE, WB_TEXT_MESSAGE_GAUNTLET);
}

void pickup_effect_grant_revival(uint8_t *image) {
    grant_slot(image, WB_HUD_SLOT_BBC6, WB_PICKUP_SLOT_REVIVAL_VALUE, WB_TEXT_MESSAGE_REVIVAL);
}

void pickup_effect_grant_fire_balls(uint8_t *image) {
    grant_record(image, WB_PICKUP_RECORD_FIRE_BALLS, WB_TEXT_MESSAGE_FIRE_BALLS);
}

void pickup_effect_grant_bombs(uint8_t *image) {
    grant_record(image, WB_PICKUP_RECORD_BOMBS, WB_TEXT_MESSAGE_BOMBS);
}

void pickup_effect_grant_wind_spouts(uint8_t *image) {
    grant_record(image, WB_PICKUP_RECORD_WIND_SPOUTS, WB_TEXT_MESSAGE_WIND_SPOUTS);
}

void pickup_effect_grant_lightning(uint8_t *image) {
    grant_record(image, WB_PICKUP_RECORD_LIGHTNING, WB_TEXT_MESSAGE_LIGHTNING);
}

/* $106f0 — `move.w max,meter`, `effect_restore_b6fa_to_max`'s one instruction with the panel's own
 * countdown restarted above it and no test at all, so it fills the meter even from above the
 * maximum. */
void pickup_effect_refill_meter(uint8_t *image) {
    wr16(image + WB_PANEL_FRAME_DELAY, WB_PANEL_FRAME_DELAY_INIT);
    wr16(image + WB_HUD_METER_VALUE, be16(image + WB_HUD_METER_MAX));
    text_post_message(image, WB_TEXT_REQUEST_NONE);
}

/* $10714 — AND IT IS NOT `effect_add4_clamped_b6fa` AT ANOTHER ADDRESS. Both compute
 * `meter + WB_PICKUP_METER_STEP` and both branch on `bgt` against the maximum; that one then STORES
 * the maximum and this one stores nothing, so a meter within three of full is left exactly where it
 * was instead of being topped up. Same shipped-bug class as slot 30's missing store, reproduced for
 * the same reason.
 *
 * The compare is the SIGNED 16-bit one of its sibling, and the add wraps, so the two cases that
 * make the signedness observable are the same two — a meter near $7fff comes out negative and
 * stores. */
void pickup_effect_add4_meter(uint8_t *image) {
    uint16_t raised;

    wr16(image + WB_PANEL_FRAME_DELAY, WB_PANEL_FRAME_DELAY_INIT);
    raised = (uint16_t)(be16(image + WB_HUD_METER_VALUE) + WB_PICKUP_METER_STEP);
    if ((int16_t)raised <= (int16_t)be16(image + WB_HUD_METER_MAX))
        wr16(image + WB_HUD_METER_VALUE, raised);
    text_post_message(image, WB_TEXT_REQUEST_NONE);
}

/* $10746 — the attack level, and the ONE handler here whose last write happens on BOTH arms.
 * `cmpi.b #$3,$b444.l / bgt $10768` skips the bump AND the message, but $10768's
 * `move.w #$ffff,$1079a.l` is below the join, so a pickup taken at a full attack level still raises
 * WB_SCENE_EXIT_REQUEST. The byte is WB_EFFECT_RECORD_LIST's own first one — ../names.txt records
 * that collision and this port reproduces it rather than resolving it. */
void pickup_effect_bump_attack_level(uint8_t *image) {
    if ((int8_t)image[WB_EFFECT_RECORD_LIST] <= (int8_t)WB_ATTACK_LEVEL_MAX) {
        image[WB_EFFECT_RECORD_LIST]++;
        text_post_message(image, WB_TEXT_MESSAGE_ATTACK_UP);
    }
    wr16(image + WB_SCENE_EXIT_REQUEST, WB_SCENE_EXIT_REQUESTED);
}

/* $10772 — the only routine in this file with a callee, and the only one that writes a record
 * rather than a global. `jsr $67e0.w` hands back the followed record and the three writes are
 * $69fe's own damage-flicker state at its maximum: WB_ACTOR_FLICKER_COUNTDOWN full,
 * WB_ACTOR_FLAG_FLICKER_BIT (which makes the projection publish no sprite) and
 * WB_ACTOR_FLAGS2_INVULNERABLE_BIT (which makes $69fe return without writing anything at all). The
 * message is "Vanished !", and the three writes are why.
 *
 * The record's address comes out of MEMORY — $67e0 reads a table pointer — so the three writes go
 * through bus.h and not through `image + addr`. */
void pickup_effect_vanish_followed(uint8_t *image) {
    uint32_t followed = followed_actor_record(image);
    uint32_t flags = addr_add(followed, WB_ACTOR_FLAGS);
    uint32_t flags2 = addr_add(followed, WB_ACTOR_FLAGS2);

    bus_write_byte(image, addr_add(followed, WB_ACTOR_FLICKER_COUNTDOWN),
                   WB_PICKUP_VANISH_FLICKER);
    bus_write_byte(image, flags,
                   (uint8_t)(bus_read_byte(image, flags) | (1u << WB_ACTOR_FLAG_FLICKER_BIT)));
    bus_write_byte(image, flags2,
                   (uint8_t)(bus_read_byte(image, flags2)
                             | (1u << WB_ACTOR_FLAGS2_INVULNERABLE_BIT)));
    text_post_message(image, WB_TEXT_MESSAGE_VANISHED);
}
