/* hud.h — the status panel (src/hud.c).
 *
 * Thirty-THREE routines: the thirty-two below, and `hud_draw_lives` at the end, which is the one
 * that is NOT under the frame pass — its caller is src/stage.c's reset.
 *
 * `panel_refresh_frame` ($b346) is the game loop's once-a-frame panel pass, and the other
 * thirty-one are its ten callees and everything below them. It arrived thirteen batches after the
 * leaves under it: the tenth callee, $bbca, calls the SOUND MODULE, and by an unconditional `jsr`
 * that no seeding steers a run around — so the pass waited on src/sound.c (../STATUS.md).
 * EIGHTEEN LEAVES: four packed-BCD accumulators, five blits (three of which read the `screen_back`
 * longword themselves, while the HUD-slot pair is handed a destination), the meter's clamped add,
 * the table-select / tick at the end of the pass, the digit plotter — which calls nothing, and sits
 * with the second tier below only because it landed with the tier that needs it — and the six
 * region restores.
 * TWELVE NON-LEAVES: the three digit-field walks above the plotter, the four routines $b346 itself
 * calls that draw a field, the meter's own pass, and the three table walks at the bottom of this
 * header (with the record's own two-digit walk under one of them).
 * Names are ../names.txt's, unchanged.
 *
 * Every ADDRESS they touch is a global named in wonderboy.h, which both languages read, so this
 * header carries no address of its own. The TWO constants it does carry are not addresses: they are
 * the entry X a call site claims, proved or assumed (`WB_BCD_ENTRY_EXTEND_*` below), which belong
 * beside the routines that take them and to every module that calls one. They are `WB_`-prefixed
 * and test/layout.py scrapes this header, so the batteries read them rather than restate them.
 *
 * REGISTER ARGUMENTS. Unlike the effect handlers, most of these are entered with values in
 * registers. Ghidra recovered `void FUN(void)` for all thirty, so ../names.txt carries a `proto`
 * line committing the storage for each routine whose interface that directive can express. The two
 * it cannot are `hud_blit_meter_cell` and `hud_plot_digit`, whose results are in a1 and a0 — a
 * `proto` forces a void return — and whose d7 is IN AND OUT in the second case. The C takes those
 * registers as parameters, one `uint32_t` each (a pointer for d7), so that the operand size
 * the original applies to them is applied HERE where a differential case can pin it.
 *
 * THE DIGIT REGISTER AT THE `rts`. The three field walks and the two fields loaded as a word return
 * a `uint32_t` as well — the d7 their last plot leaves. No call site in the image reads it, so it
 * is not an output the game uses and their `proto` lines still describe the entry storage right;
 * it is returned because the oracle now reports d7, which makes it the only observer of which half
 * of the caller's own d7 a `move.w field,d7 / swap d7` buries (../src/hud.c has the argument).
 */
#ifndef WONDERBOY_HUD_H
#define WONDERBOY_HUD_H

#include <stdint.h>

/* $b372 — publish one of two table addresses, then tick the counter rng_next mixes in. */
void select_table_21e8c_and_tick_b39a(uint8_t *image);

/* $b410 — a0 = the record whose first byte selects the bitmap. */
void hud_blit_record_bitmap(uint8_t *image, uint32_t record);

/* The 68000's `abcd` on ONE byte pair, with the extend bit in and out — the primitive the four
 * accumulators below are loops of. It is public because a SECOND module executes the instruction:
 * `bcd_add_random_1_to_4` ($51ac, src/behavior.c) ends in an `abcd d1,d0` over a register pair
 * rather than over memory, and two spellings of the decimal correction could disagree while both
 * batteries stayed green. Nothing else about that routine belongs here — this is the instruction,
 * not the accumulator, and sharing it does NOT close the extend chain described below: it shares
 * one instruction so two spellings of the decimal correction cannot drift, and nothing more.
 * (`sbcd_byte` stays private — no second module executes one.) Its proper home is arguably the
 * kit's machine.h, beside `sign_ext16` and the `set_low_byte` its one outside caller composes it
 * with; ../STATUS.md REGISTERS that promotion rather than this batch making it, which is the rule
 * bus.h already follows. */
uint8_t abcd_byte(uint8_t addend, uint8_t accumulator, unsigned *extend);

/* $b562/$b582 — d0's low WORD is the packed-BCD amount; $b5a2/$b5c6 — d0's whole LONGWORD is.
 *
 * ALL FOUR CARRY THE EXTEND BIT, IN AND OUT, as of batch 33 — which is the whole of this comment,
 * because until then they folded in a hard-wired zero. `entry_extend` is the X the caller's last
 * instruction left, which the FIRST `abcd`/`sbcd` folds into the lowest digit pair (`movem.l`,
 * `move.<n> d0,$bd78` and `lea` all leave X alone, so it really is the call site's own). The return
 * value is the X the LAST pair leaves, which is a carry out of the accumulator's TOP byte — four
 * digits for the counter, eight for the score — and `movem.l (a7)+` and `rts` do not disturb it,
 * so it is what the instruction after the `bsr` sees.
 *
 * TWO PORTED CHAINS THREAD IT and are pinned at caller level in test_behavior.py:
 * `bcd_add_counter_bd6e` -> `bcd_add_score_bd70` at $4e5a/$4e64 (slot 28's collect arm; the
 * `move.l #imm,d0` between them does not touch X), and `bcd_add_random_1_to_4` ->
 * `bcd_add_counter_bd6e` at $5184/$5188 (the payout's own `abcd`, then the gold counter).
 *
 * THERE IS A THIRD ADJACENCY AND IT IS SOUND, which is worth stating so a later scope does not
 * treat the pair above as the whole list: $5188 (counter) and $5196 (score) inside
 * `hud_award_gold_from_descriptor` are also back to back, with `bsr $51d8` between them — and that
 * routine's LAST X-writer on both of its exit paths is `addi.b #$30` on a nibble masked to $0..$f,
 * which cannot carry out of $30..$3f. `ror.w`, `andi.w` and `move.b` leave X alone. So X really is
 * 0 at $5196 and that site passes CLEAR by construction rather than by luck.
 *
 * A THIRD SITE THREADS IT WITHOUT BEING A CHAIN: `actor_defeat_and_score`'s score add at $6c26 is
 * entered with the bit `lsl.w #2,d2` pushed out of the spawn type at $6c20 — produced INSIDE that
 * routine, so an ordinary differential row drives it either way (test_actor.py).
 *
 * WHAT IS STILL UNPINNABLE, and it is the harness rather than the model: `emu.run` forces SR =
 * $2700 after its reset and has no entry-CCR parameter, so no case can enter one of these routines,
 * or any routine that calls one, with X already set. What that costs is listed in ../STATUS.md; the
 * short form is a run ENTERED with X set ($e064's shape, unported) and the shop site below. */

/* THE ENTRY X A CALL SITE CLAIMS, in TWO spellings, because the sites do not all rest on the same
 * kind of evidence and one name would have hidden that. `grep -r WB_BCD_ENTRY_EXTEND ../src` is the
 * audit and returns FOUR CALL SITES — three proved, one assumed. The three THREADED sites carry no
 * marker at all, by construction, and are named above.
 *
 * PROVED (three): $5196 and $e130 by a reading of the bytes — see each call — and $4e5a by the
 * DIFFERENTIAL, whose seed is sensitive to the bit ($0100 + 5 is $0105 with X clear and $0106 with
 * it set), which is evidence of a different kind but not a weaker one.
 *
 * ASSUMED (one): the shop's subtract at $ddae/$de24, src/scene.c. Nothing on the path from
 * `scene_run_frame`'s entry writes X, so the bit is the CALLER's — and the caller is the
 * `jsr $dbc0.l` at $4be, whose preceding instruction is `jsr $b346.l`, whose last act before its
 * `rts` is `bsr $b372` -> `addq.w #1,frame_tick_b39a` at $b392 (both single-caller). An `addq.w`
 * leaves X SET when the word wraps, so the assumption is not open-ended but exactly quantified: it
 * holds on 65535 frames out of 65536 and fails on the one where the frame tick rolls $ffff -> $0000,
 * on which a purchase spends one extra unit of gold. No case can drive that frame, because every
 * run is entered with the CCR forced clear. ../STATUS.md tracks it as an OPEN row.
 *
 * Both constants are 0. The value is not the point — which claim a site is making is. */
#define WB_BCD_ENTRY_EXTEND_CLEAR          0u
#define WB_BCD_ENTRY_EXTEND_ASSUMED_CLEAR  0u

unsigned bcd_add_counter_bd6e(uint8_t *image, uint32_t addend, unsigned entry_extend);
unsigned bcd_sub_counter_bd6e(uint8_t *image, uint32_t subtrahend, unsigned entry_extend);
unsigned bcd_add_score_bd70(uint8_t *image, uint32_t addend, unsigned entry_extend);
unsigned bcd_sub_score_bd70(uint8_t *image, uint32_t subtrahend, unsigned entry_extend);

/* $b6c2 — a1 = the cursor into the cell-offset table, a2 = the cell's 32 bytes. Returns the
 * ADVANCED cursor, which is the one register its caller reads back (see src/hud.c). */
uint32_t hud_blit_meter_cell(uint8_t *image, uint32_t offset_cursor, uint32_t cell);

/* $b6fe — d0's low word is added to the meter, which is then clamped to its maximum. */
void hud_meter_add_clamped(uint8_t *image, uint32_t amount);

/* $bb8a/$bba0 — a0 = source cell, a1 = destination in screen_back. */
void hud_blit_cell_copy(uint8_t *image, uint32_t source, uint32_t destination);
void hud_blit_cell_or(uint8_t *image, uint32_t source, uint32_t destination);

/* $bcd6 — no arguments: the frame index comes out of memory. RETURNS the d0 its last `movem` leaves
 * (the panel frame's last row, first longword), because `panel_frame_timers` hands that on and
 * `panel_refresh_frame` spends it as the stage number's font select. */
uint32_t hud_blit_panel_frame(uint8_t *image);

/* ---- the second tier: the four routines panel_refresh_frame calls, and their two helpers -------
 *
 * All but the first of these CALL a reconstruction above, which is why their differential cases run
 * the original's callees under the oracle while the C calls the ported C directly. `hud_plot_digit`
 * is the exception and is itself a leaf; it sits here because the walks below cannot be ported
 * without it.
 *
 * `font_select` is the 68000's d0 and `digits` its d7, both taken as whole longwords for the same
 * reason as above: the original applies `cmpi.w` to one and `rol.l`/`swap` to the other, and those
 * operand sizes belong where a case can pin them. `digits` is IN/OUT on `hud_plot_digit` because the
 * original's d7 is: every plot rotates it left by a nibble, and its caller keeps the rotated value.
 */

/* $b850 — d0 = font_select, a0 = the cursor, d7 = the digit register (rotated in place).
 * Returns the cursor eight scanlines lower, which is what the original leaves in a0. */
uint32_t hud_plot_digit(uint8_t *image, uint32_t font_select, uint32_t cursor, uint32_t *digits);

/* $b5ea / $b7ea / $bd4a — one field of digits, left to right, from the top nibble of `digits` down.
 * Only the four-digit form forces the glyphs (`moveq #0,d0`); the other two pass the caller's d0
 * through, the eight-digit one to its FIRST digit only.
 * Each RETURNS the digit register the original leaves in d7 — one nibble rotation per plot. */
uint32_t hud_draw_four_digits(uint8_t *image, uint32_t cursor, uint32_t digits);
uint32_t hud_draw_eight_digits(uint8_t *image, uint32_t font_select, uint32_t cursor,
                               uint32_t digits);
uint32_t hud_draw_two_digits(uint8_t *image, uint32_t font_select, uint32_t cursor,
                             uint32_t digits);

/* $b54c — d7's LOW word is the dead half: `move.w bcd_counter_bd6e,d7` overwrites it and the `swap`
 * then lifts the counter into the high half, leaving the caller's own HIGH word below the digits —
 * live input, but buried where no rotation brings it back under a drawn nibble. d0 is unread, since
 * the four-digit form forces its own. Returns d7 as the `rts` leaves it: the walk's four rotations
 * come to a `swap`, so the buried half is back on top and the counter is below it. */
uint32_t hud_draw_counter_bd6e(uint8_t *image, uint32_t digits);

/* $b74a / $b7c6 — d7 is dead at both (each reloads it from memory); d0 reaches the first digit. */
void hud_draw_score_and_size_meter(uint8_t *image, uint32_t font_select);
void hud_draw_larger_score(uint8_t *image, uint32_t font_select);

/* $bd32 — d0 reaches BOTH digits; d7's LOW word is the dead half and its high word survives buried,
 * as in hud_draw_counter_bd6e. Its `rol.l #8` plus the two-digit walk's two nibbles come to 16 as
 * well, so the returned register carries the buried half back in its high word too. */
uint32_t hud_draw_stage_number(uint8_t *image, uint32_t font_select, uint32_t digits);

/* $b61e — no registers at all: every input is a word in memory. */
void hud_draw_meter(uint8_t *image);

/* ---- the third tier: the pass's three table walks ----------------------------------------------
 *
 * `panel_refresh_frame`'s remaining callees. Each finds its work by testing a byte something else
 * raised, so each one's write set can include bytes it was told about as well as the pixels it
 * drew. TWO of the three then CLEAR that byte; `hud_draw_newest_record` does not — nothing in the
 * image clears `record_fresh_flag`, which is the original's own shape and not an omission here.
 */

/* $d93a — no registers: the flag array, both screen pointers and every origin come out of memory.
 * Copies one region from `screen_front` to `screen_back` per raised flag. */
void panel_restore_dirty_regions(uint8_t *image);

/* The six blits it dispatches to, named for their geometry (`<row bytes>x<rows>`) because what each
 * region DEPICTS is only known for some of them — ../names.txt records which. a0 = the source in
 * the front buffer, a1 = the destination in the back one; both are whole addresses their caller has
 * already offset, as with the HUD-cell pair. `panel_restore_none` ($db34) is a bare `rts` and takes
 * the same arguments so that one table can hold all six. */
typedef void panel_restore_fn(uint8_t *image, uint32_t source, uint32_t destination);

panel_restore_fn panel_restore_44x8;    /* $daf8 — one `movem` of eleven registers a row */
panel_restore_fn panel_restore_32x20;   /* $db12 */
panel_restore_fn panel_restore_32x29;   /* $db36 */
panel_restore_fn panel_restore_16x14;   /* $db58 — the HUD-slot cell's geometry */
panel_restore_fn panel_restore_24x32;   /* $db72 — the panel frame's */
panel_restore_fn panel_restore_none;    /* $db34 */

/* $b39c — no registers: the list, its write pointer and the fresh-record flag are all in memory. */
void hud_draw_newest_record(uint8_t *image);

/* $b3da — a0 = the record. d0 and d7 are both dead input (`move.w #1,d0` before each of the two
 * plots, `moveq #0,d7` before the byte is loaded into it). */
void hud_draw_record_digits(uint8_t *image, uint32_t record);

/* $b8f0 — no registers: the six slot records and `screen_back` are all in memory. */
void hud_refresh_dirty_slots(uint8_t *image);

/* ---- $bbca and $b346: the panel's animation, and the pass itself ------------------------------
 *
 * The last two of the subsystem. `panel_frame_timers` is the one routine of the thirty-two that
 * leaves this file for another (src/sound.c), which is what kept it — and therefore $b346 — out of
 * batches 3, 4 and 13; see ../STATUS.md.
 */

/* $bbca — no registers in: five timer words and the frame index are all in memory. RETURNS the d0
 * it leaves, which is `hud_blit_panel_frame`'s: every one of its arms ends with that call, and
 * $bd32 is entered with it two instructions later. */
uint32_t panel_frame_timers(uint8_t *image);

/* $b346 — no registers either way. It sets neither d0 nor d7 before any of its ten calls, so what
 * flows between them is whatever each one left; src/hud.c reads the ten bodies and shows that only
 * one of those values can reach a drawn byte. */
void panel_refresh_frame(uint8_t *image);

/* $e80c — draw WB_LIVES_ICON_SLOTS cells at WB_LIVES_ICON_BACK / _FRONT, the first WB_LIVES of them
 * from WB_LIVES_ICON_BITMAP and the rest blank. No registers, and no `screen_back`: both
 * destinations are absolute, so this writes the buffer being displayed as well as the one being
 * drawn. Its one caller is `game_life_restart_reset` (src/stage.c). */
void hud_draw_lives(uint8_t *image);

#endif /* WONDERBOY_HUD_H */
