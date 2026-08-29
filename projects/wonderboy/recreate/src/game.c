/* game.c — THE SPINE. What the frame loop itself is made of; why it is a module of its own, and
 * why it could not be written before the kit's scheduled-write model, is in ../include/game.h.
 *
 * Both routines here read WB_KEY_LAST_SCANCODE, the byte the IKBD ACIA handler ($754) stores on
 * every keypress and every release. Two of the reads are BUSY-WAITS on a value that byte only takes
 * when the interrupt writes it, and those two — and only those two — go through `sched_poll8`.
 * Every other read of the same address is an ordinary guarded read: `$642` tests the PRESS code
 * before the wait below it, at the same address, and is not a poll.
 */
#include "game.h"

#include "actor.h"
#include "behavior.h"
#include "blit.h"    /* sprite_draw_pass — the loop's one call with a register interface */
#include "bus.h"
#include "hud.h"
#include "input.h"
#include "player.h"  /* the WB_PLAYER_* unwind codes the behaviour pass hands up — see the loop */
#include "scene.h"
#include "scroll.h"
#include "shifter.h"  /* the port's one shifter sink — the base publish and the flash */
#include "sound.h"
#include "stage.h"
#include "text.h"
#include "wonderboy.h"

#include "psg.h"       /* the YM2149's two ports — the floppy pair below, off target only */
#include "sched.h"     /* the kit's external-agent model — the two waits below, off target only */

/* Wait on WB_KEY_LAST_SCANCODE until it reads `code` — the shape all three of this module's byte
 * spins have. `site_pc` is the address at which the ORIGINAL re-reads the byte — here the `cmpi.b`,
 * which reads and tests in one instruction.
 *
 * It goes through the kit's `sched_wait8` rather than a `while (bus_read_byte(...))` because the
 * POLL is what the differential counts (tools/recreate_kit/include/sched.h): the oracle counts
 * arrivals at that compare and this side counts polls at that site, one per iteration, and the
 * harness compares the two. The capped form is the one to reach for — an uncapped loop turns a case
 * whose schedule never releases the wait into a HUNG suite, which decides nothing.
 *
 * THE SITE IS THE PC AND NOT THE ADDRESS, and this routine's own callers are why: all three spin on
 * WB_KEY_LAST_SCANCODE and two of them wait for the very same release code, so nothing about the
 * poll except WHERE the original makes it can tell one wait from another.
 *
 * RETURNS 0 WHEN THE WAIT WAS NEVER RELEASED, and every caller returns immediately on that: the
 * model has refused, the harness is about to throw the case away, and carrying on as though the
 * byte had arrived would run the payload on a state the original never reached. On target this is
 * an ordinary uncapped spin and the ACIA interrupt is what ends it. */
static int wait_for_scancode(uint8_t *image, uint8_t code, uint32_t site_pc) {
    return sched_wait8(image, WB_KEY_LAST_SCANCODE, code, site_pc);
}

/* $60e — game_key_actions' PAUSE arm, reached by `beq.w` from $57c and ending in its own `rts`.
 *
 * It is not a routine (nothing calls $60e) and so has no `fn` of its own in ../names.txt; it is a
 * function here because the wait plus the four stores are one act, and because the unpause payload
 * next door is its mirror image. Wait for the pause key's release, forget the scancode, raise the
 * pause flag, and post the pause message with a lifetime of zero.
 *
 * THE LIFETIME STORE IS A BYTE over a WORD. `move.b #$0,$c034.l` at $62e clears only the HIGH byte
 * of WB_TEXT_LIFETIME_REQUEST, leaving the low one as it found it — so a paused box inherits the
 * bottom half of whatever lifetime was last posted. Reproduced as the byte store it is. */
static void pause_the_game(uint8_t *image) {
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_P_RELEASE, WB_KEY_PAUSE_WAIT_PC))
        return;
    image[WB_KEY_LAST_SCANCODE] = 0;
    wr16(image + WB_GAME_PAUSED, WB_GAME_PAUSED_SET);
    image[WB_TEXT_REQUEST] = WB_PAUSE_MESSAGE_ID;
    image[WB_TEXT_LIFETIME_REQUEST] = 0;
}

/* $5a8..$5ce — one step of the cheat sequence walk, reached only while WB_KEY_SEQUENCE_MATCHED is
 * still clear. Returns non-zero when the walk hit the terminator, which is the arm that RAISES the
 * cheat and returns from the whole routine without running the Help block below.
 *
 * The index is `move.b (a0,d0.w),d1` over `move.w $606.l,d0`: a SIGNED word index off the sequence's
 * base, so a cursor past $7fff would read BELOW the table rather than far above it. NO REACHABLE
 * CURSOR DOES — the walk steps only while the byte at it matches, and the byte at index 4 is the
 * terminator, which raises the cheat and returns without stepping; a raised cheat then
 * short-circuits the walk for ever, so the range is 0..4. The signedness is reproduced because it
 * is the instruction's, and test_game.py drives it on a declared-fabricated seed which says so. */
static int cheat_sequence_step(uint8_t *image) {
    int16_t cursor = (int16_t)bus_read_word(image, WB_KEY_SEQUENCE_CURSOR);
    uint8_t wanted = bus_read_byte(image, addr_add(WB_KEY_SEQUENCE_SCANCODES, (uint32_t)(int32_t)cursor));

    if (wanted == WB_KEY_SEQUENCE_TERMINATOR) {
        wr16(image + WB_KEY_SEQUENCE_MATCHED, WB_KEY_SEQUENCE_MATCHED_SET);
        return 1;
    }
    if (wanted == image[WB_KEY_LAST_SCANCODE])
        wr16(image + WB_KEY_SEQUENCE_CURSOR, (uint16_t)(cursor + 1));
    return 0;
}

/* $5d0..$5f8 — the cheat's SECOND action: while the cheat is enabled, Help flips bit 3 of
 * WB_EFFECT_STATE_BD6A's low byte. The `bchg` is a byte read-modify-write however the original
 * spells the address, and it happens only after the key is RELEASED — the second of this module's
 * two waits. */
static void cheat_help_action(uint8_t *image) {
    if (!bus_read_word(image, WB_KEY_SEQUENCE_MATCHED))
        return;
    if (image[WB_KEY_LAST_SCANCODE] != WB_KEY_SCANCODE_HELP)
        return;
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_HELP_RELEASE, WB_KEY_HELP_WAIT_PC))
        return;
    image[WB_EFFECT_STATE_BD6A_LOW] ^= (uint8_t)(1u << WB_EFFECT_STATE_BD6A_CHEAT_BIT);
}

uint32_t game_key_actions(uint8_t *image) {
    /* $53e. The round-end request outranks every key: the sequence at $e032 raised it when the
     * bonus countdown finished, and this is what acts on it. */
    if (bus_read_word(image, WB_ROUND_END_RELOAD_REQUEST)) {
        wr16(image + WB_ROUND_END_RELOAD_REQUEST, 0);
        return WB_KEY_ACTIONS_ROUND_END;
    }
    /* $556. N with the cheat on skips the level — the same unwind, and it leaves the request word
     * alone because there was none. */
    if (bus_read_word(image, WB_KEY_SEQUENCE_MATCHED)
            && image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_N)
        return WB_KEY_ACTIONS_LEVEL_SKIP;
    /* $574. */
    if (image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_P) {
        pause_the_game(image);
        return WB_KEY_ACTIONS_RETURNED;
    }
    /* $580. */
    if (image[WB_KEY_LAST_SCANCODE] == WB_KEY_SCANCODE_ESC) {
        snd_start_fadeout(image);
        return WB_KEY_ACTIONS_QUIT;
    }
    /* $59e. The walk runs only while the cheat is still OFF, and its terminator arm returns at once
     * — so the frame that completes the sequence does not also run the Help action below. */
    if (!bus_read_word(image, WB_KEY_SEQUENCE_MATCHED) && cheat_sequence_step(image))
        return WB_KEY_ACTIONS_RETURNED;
    cheat_help_action(image);
    return WB_KEY_ACTIONS_RETURNED;
}

/* $638. The mirror of pause_the_game: it exists to undo it, and the two spin on the same byte for
 * the same code. Nothing happens unless the game is paused AND the pause key is still held — the
 * `cmpi.b #$19,$879.l` at $642 is a plain read of the byte the wait below then polls. */
void game_unpause_on_key_release(uint8_t *image) {
    if (!bus_read_word(image, WB_GAME_PAUSED))
        return;
    if (image[WB_KEY_LAST_SCANCODE] != WB_KEY_SCANCODE_P)
        return;
    if (!wait_for_scancode(image, WB_KEY_SCANCODE_P_RELEASE, WB_KEY_UNPAUSE_WAIT_PC))
        return;
    image[WB_KEY_LAST_SCANCODE] = 0;
    wr16(image + WB_GAME_PAUSED, 0);
    image[WB_TEXT_REQUEST] = WB_TEXT_REQUEST_DISMISS;
}


/* --- $882: the frame's input-and-actors pair ---------------------------------------------------- */

/* $882 — ten bytes and two `bsr`s. It exists because the two must run in this order and adjacently:
 * `joy1_latch_edge` shifts the joystick byte one frame down the pipeline, and the behaviour pass
 * below it is what reads the edge that shift produces. game_main_loop's $66e-gated block reaches it
 * last of the four, so a PAUSED frame runs neither.
 *
 * THE ORIGINAL'S d0 IS DROPPED AND THE PORT'S REPORT IS NOT, and the two are different things.
 * `bsr $8d0 / rts` leaves the walk's d0 in the register and nothing up the chain reads it — that is
 * the original, and it is why this routine takes no notice of it. What this returns is the
 * out-of-band boundary report the reconstruction invented (../include/behavior.h), and four of its
 * values are the original TRANSFERRING out of the frame loop; game_main_loop is where those four
 * are acted on. */
uint32_t game_latch_input_and_step_actors(uint8_t *image) {
    joy1_latch_edge(image);
    return actor_behavior_pass(image);
}


/* --- $50a: the follow cursor, snapped to an even pixel ------------------------------------------ */

/* $50a — game_main_loop's one `bsr`, between bg_scroll_blit and sprite_draw_pass, and what it does
 * is quantise the camera: WB_SCROLL_FOLLOW_X and _Y are forced to EVEN pixels so the sprite pass
 * draws the followed actor on a word boundary rather than a nibble-shifted one.
 *
 * BOTH HALVES ARE SNAPPED DOWN, and only x can be snapped UP instead. The `andi.l` clears bit 0 of
 * each half in one instruction, so y is always rounded down; then, while the followed actor's SIDE
 * flag is set and the masked x differs from the raw one — which is exactly the case where x was ODD
 * — the whole step is added back, rounding that x up. The bias follows the actor's facing, which is
 * what stops the camera stepping the wrong way under him on the frame he turns.
 *
 * THE COMPARE IS AGAINST MEMORY, NOT AGAINST A KEPT COPY. `cmp.w $9934.l,d0` at $528 re-reads the
 * high half out of the image after the mask, so "was x odd" is answered by the byte in memory. Read
 * back the same way here: the two orders differ for any agent that wrote the word in between, and
 * this reconstruction must be the one the original spells. */
void game_snap_follow_cursor(uint8_t *image) {
    uint32_t followed = followed_actor_record(image);
    uint32_t snapped = bus_read_long(image, WB_SCROLL_FOLLOW_X) & WB_SCROLL_FOLLOW_EVEN_MASK;
    uint16_t x = (uint16_t)(snapped >> WB_WORD_BITS);
    uint16_t y = (uint16_t)snapped;

    if (bus_read_byte(image, addr_add(followed, WB_ACTOR_FLAGS)) & (1u << WB_ACTOR_FLAG_SIDE_BIT)
            && x != bus_read_word(image, WB_SCROLL_FOLLOW_X))
        x = (uint16_t)(x + WB_SCROLL_FOLLOW_SNAP_UP);

    bus_write_long(image, WB_SCROLL_FOLLOW_X, ((uint32_t)x << WB_WORD_BITS) | y);
}


/* --- $e032/$e0a8: THE ROUND BONUS ---------------------------------------------------------------
 *
 * The sequence WB_EVENT_FINISHED_E1BE has been waiting for since batch 41 named it. Two phases,
 * one unit of WB_HUD_METER_VALUE a frame each way: drain it to zero for WB_ROUND_BONUS_SCORE a
 * unit, then refill it to WB_ROUND_BONUS_METER_TARGET and ask game_key_actions for the reload. */

/* $e0a8 — the setup arm, and a true routine rather than a continuation: `bsr.w $e0a8` at $e048 is
 * its one caller and it ends in its own `rts`.
 *
 * It empties the A30 actor table, loads the bonus stage through the transition hinge, switches the
 * game into A30 mode, latches WB_ROUND_BONUS_ACTIVE so the count runs from the next frame, plots
 * the banner, and computes the refill target.
 *
 * THE TARGET IS A SIGNED MINIMUM AND THE BUMP CAN WRAP. `addi.w #$4,d0 / cmp.w d0,d1 / blt` takes
 * WB_HUD_METER_MAX when it is BELOW value + 4 and the sum otherwise, both as 16-bit signed words —
 * so a meter at $7ffe bumps to $8002, reads as negative, and the target becomes the sum rather than
 * the maximum. Reproduced as the word arithmetic it is.
 *
 * THE MAP AND TILE BANK COME OUT OF THE TABLE; THE START RECORD DOES NOT. a1 is loaded from
 * WB_SCENE_MAP_BANK_TABLE and then immediately overwritten by `lea $1d434.l,a1`, so the entry's two
 * longwords are the hinge's `map` and `tiles` and its `start` is the literal. */
void round_bonus_setup(uint8_t *image) {
    actor_table_reset(image, WB_ACTOR_TABLE_A30);

    /* READ AFTER THE RESET, because $e0b6 reads it there. The reset writes WB_ACTOR_TABLE_A30 and
     * the bank table is elsewhere, so the two orders agree on the game's own image — but a READ
     * leaves no trace in the write ledger, so no surface the harness compares would see them come
     * apart. Spelt in the original's order, which is the only thing keeping it right. */
    uint32_t map_bank_entry = addr_add(WB_SCENE_MAP_BANK_TABLE, WB_ROUND_BONUS_MAP_BANK);
    uint32_t map = bus_read_long(image, map_bank_entry);
    uint32_t tiles = bus_read_long(image, addr_add(map_bank_entry, WB_LONGWORD_BYTES));

    stage_load_window(image, map, WB_ROUND_BONUS_START_RECORD, tiles);
    wr16(image + WB_STATE_FLAG_A30, WB_STATE_FLAG_SET);
    wr16(image + WB_ROUND_BONUS_ACTIVE, WB_ROUND_BONUS_ACTIVE_SET);
    bg_plot_round_banner(image);

    int16_t bumped = (int16_t)(bus_read_word(image, WB_HUD_METER_VALUE) + WB_ROUND_BONUS_METER_BUMP);
    int16_t maximum = (int16_t)bus_read_word(image, WB_HUD_METER_MAX);
    wr16(image + WB_ROUND_BONUS_METER_TARGET, (uint16_t)(maximum < bumped ? maximum : bumped));
    wr16(image + WB_ROUND_BONUS_REFILLING, 0);
}

/* $e032 — run once a frame from game_main_loop's $66e-gated block, and the first of its four calls.
 *
 * THE X IT HANDS THE SCORE ADDER IS PRODUCED INSIDE THE RUN. `subq.w #1,$b6fa.l` at $e058 is the
 * instruction immediately above the `move.l #$410,d0 / bsr bcd_add_score_bd70`, and a `move.l` of
 * an immediate does not touch X — so the extend the packed-BCD add carries in is the BORROW out of
 * that decrement, which is set exactly when the meter was already zero. Threaded rather than
 * assumed clear: this is one of the sites where the bit has a driveable producer above it.
 *
 * A METER THAT WAS ALREADY ZERO THEREFORE SCORES ONE MORE. It wraps to $ffff, the borrow rides into
 * the BCD add, and the `tst.w` below sees a non-zero word — so the drain does not end and the phase
 * does not switch. Reachable only if something else emptied the meter first; reproduced because it
 * is what the instructions say.
 *
 * THE TWO ENDINGS THAT CLEAR STATE ARE `clr.l`s OVER WORD PAIRS. $e092 clears
 * WB_EVENT_FINISHED_E1BE together with WB_ROUND_BONUS_ACTIVE and $e098 the target together with the
 * phase flag — four words in two instructions, which is why a census of the word forms at those
 * addresses finds no writer. */
void round_bonus_run_frame(uint8_t *image) {
    if (!bus_read_word(image, WB_EVENT_FINISHED_E1BE))
        return;
    if (!bus_read_word(image, WB_ROUND_BONUS_ACTIVE)) {
        round_bonus_setup(image);
        return;
    }
    if (!bus_read_word(image, WB_ROUND_BONUS_REFILLING)) {
        uint16_t meter = bus_read_word(image, WB_HUD_METER_VALUE);
        unsigned borrow = word_sub_extend(meter, 1);      /* the `subq.w #1`'s own X, threaded below */

        wr16(image + WB_HUD_METER_VALUE, (uint16_t)(meter - 1));
        (void)bcd_add_score_bd70(image, WB_ROUND_BONUS_SCORE, borrow);
        if (bus_read_word(image, WB_HUD_METER_VALUE))
            return;
        wr16(image + WB_ROUND_BONUS_REFILLING, WB_ROUND_BONUS_REFILLING_SET);
        return;
    }
    wr16(image + WB_HUD_METER_VALUE, (uint16_t)(bus_read_word(image, WB_HUD_METER_VALUE) + 1));
    /* `addq.w #1,$b6fa.l` then `move.w $b6fa.l,d0` — the compare's operand is a RE-READ of the word
     * just stored and not the value the add produced, exactly as the drain arm's `tst.w` is and as
     * $50a's `cmp.w $9934.l,d0` is. Nothing writes between the two instructions, so the spellings
     * agree; the original's is the one reproduced, and the three arms now read alike. */
    if (bus_read_word(image, WB_HUD_METER_VALUE)
            != bus_read_word(image, WB_ROUND_BONUS_METER_TARGET))
        return;
    wr32(image + WB_EVENT_FINISHED_E1BE, 0);              /* ...and WB_ROUND_BONUS_ACTIVE with it */
    wr32(image + WB_ROUND_BONUS_METER_TARGET, 0);         /* ...and WB_ROUND_BONUS_REFILLING */
    wr16(image + WB_ROUND_END_RELOAD_REQUEST, WB_ROUND_END_RELOAD_REQUEST_SET);
}


/* --- $624c/$6268: the floppy's drive-select lines ------------------------------------------------
 *
 * Not sound, despite the chip. The YM2149's port A carries the floppy's side and drive-select
 * lines in its low three bits and four other peripherals' in the rest, which is why the write is a
 * read-modify-write and why the register's prior contents are an input the case must declare. */

/* $624c — replace port A's low three bits with `bits`, keeping the other five.
 *
 * `bits` is the original's d0 and only its low three bits reach the chip through the `or.b`; a
 * caller passing more would SET bits the mask meant to preserve, so the value is not masked here —
 * the instruction does not mask it either.
 *
 * TWO ENTRANTS, NOT ONE, and the second does not call it: $6242 (`floppy_select_drive_a`) loads
 * d0 = 5, clears the idle timer and FALLS THROUGH into this routine's first instruction. So the
 * `bits` the game itself produces are 5 and 7 — both inside the three floppy lines — and the values
 * above them that test_game.py drives are reachable through no path in the image. */
void psg_set_drive_select(uint8_t *image, uint32_t bits) {
    (void)image;
    uint8_t kept = (uint8_t)(psg_port_read(WB_PSG_REG_PORT_A) & WB_PSG_PORT_A_KEEP);
    psg_port_write(WB_PSG_REG_PORT_A, (uint8_t)(kept | (uint8_t)bits));
}

/* $6268 — every drive off, which is what vbl_handler calls when WB_FLOPPY_IDLE_TIMER expires. The
 * `movem.l #$c000,-(a7)` around it saves d0/d1 and is stack traffic alone. */
void floppy_deselect_drives(uint8_t *image) {
    psg_set_drive_select(image, WB_PSG_DRIVES_DESELECTED);
}


/* --- $716: THE VERTICAL-BLANK HANDLER ------------------------------------------------------------
 *
 * The program's ONE periodic tick — MFP timers A and B are masked off at boot — installed at the
 * level-4 autovector ($70) by hw_init_vectors and again at $e506. Everything else in this
 * reconstruction is called; this is called BY THE MACHINE, fifty times a second, and the two words
 * it maintains are read by code that never runs at the same time as it.
 *
 * IT ENDS IN `rte`, NOT `rts`, AND THAT IS ITS WHOLE DIFFERENTIAL PROBLEM. game.h states the
 * convention the cases use and why the alternative does not work; the C is the body and nothing
 * else. The `movem` pair is not reproduced: it saves and restores the machine's registers around a
 * handler that must not disturb the interrupted code, and a C function's own registers are its
 * compiler's business — the bytes it writes land in the runner's stack band, which the harness
 * excludes from the diff, so there is nothing there to mirror. NOR IS IT THE ONLY SUCH PAIR ON THIS
 * PATH: the tick is reached through the stub at $17aea, which is itself `movem.l #$fffe,-(a7) /
 * bsr.w $17c74 / movem.l (a7)+,#$7fff / rts`, so a run of this handler pushes 120 bytes of saved
 * registers and not 60. Calling `snd_music_tick` directly skips the second wrapper as well. */
void vbl_handler(uint8_t *image) {
    wr16(image + WB_VBL_COUNTER, (uint16_t)(bus_read_word(image, WB_VBL_COUNTER) + 1));
    snd_music_tick(image);

    uint16_t idle = bus_read_word(image, WB_FLOPPY_IDLE_TIMER);
    if (idle == 0)
        return;
    idle = (uint16_t)(idle - 1);
    wr16(image + WB_FLOPPY_IDLE_TIMER, idle);
    if (idle == 0)
        floppy_deselect_drives(image);
}


/* --- $694: THE FLIP --------------------------------------------------------------------------
 *
 * game_main_loop's last call, and the frame's own heartbeat: swap the two buffers, tell the shifter
 * where the new front one is, wait for the vertical blank, and run the white-flash countdown.
 *
 * IT WAITS TWICE, ON THE SAME WORD, AT TWO DIFFERENT INSTRUCTIONS — and that pair is why this
 * routine outlived the rest of the spine by two phases. Neither wait is hard to model; what was hard
 * is that a run TOTAL cannot tell the two apart, so the natural case balanced its counters by
 * cancellation while the two sides ran different loops (../names.txt's cmt 0x694 has the
 * arithmetic). The kit now counts polls and arrivals PER WAIT SITE, which is what makes the two
 * `sched_poll16` calls below separable — WB_FLIP_READY_WAIT_PC and WB_FLIP_TICK_WAIT_PC are the
 * original's own compare addresses, and a case declares them as its `wait_sites`.
 *
 * THE TWO WAITS ARE NOT THE SAME PREDICATE, which is also why the kit's word primitive is an
 * iterator rather than a `sched_wait16(until)`: the first is a SIGNED threshold and the second a
 * comparison against a copy taken one instruction earlier.
 *
 * THREE HARDWARE REGISTERS OVER FOUR WRITES ARE A SINK, exactly as src/stage.c's set_palette is and
 * for exactly the same reason: they are off the 68000's 24-bit bus as far as the loaded image goes,
 * and the oracle DROPS them. So what this routine puts on the screen — which buffer is displayed,
 * and the full-screen colour-0 flash — is pinned by nothing here, and ../STATUS.md says so in as
 * many words. On target the three become ordinary `volatile` stores and the sinks compile out.
 *
 * THE KIT'S REMEDY EXISTS NOW and this port has not taken it: `hw.h` exports `hw_write8/16/32` over
 * an ordered ledger `harness.differential` compares on both sides (kit TRAP_MODEL.md, "Phase 10").
 * Until the sink routes through it, the cases that reach these registers declare them in
 * `hw_waiver=` — test/harness.py's `SHIFTER_UNPINNED` lists them and says so.
 */

/* The two writes this file makes to a shifter register the differential cannot see — the screen
 * base as two BYTES and the lightning flash's colour 0 as a WORD — go through ../include/shifter.h,
 * which is the port's ONE statement of the sink and of its on-target arm. That header has the whole
 * argument; what stays here is the reads that FEED the writes and the order they are made in, which
 * is the part that is reconstruction.
 *
 * THE FLASH IS A PALETTE WRITE AND IS SPELT AS ONE. `move.w #$777,$ff8240.l` names WB_SHIFTER_PALETTE
 * itself, which is colour register 0 — WB_FLASH_PEN — so it goes through the same
 * `shifter_palette_write` the palette row does rather than through a raw-address word write of its
 * own. The store that reaches the bus is the same address at the same instant either way; what the
 * pen spelling removes is a public sink that could name any shifter register from anywhere. */

/* $6aa..$6b4 — spin while WB_VBL_COUNTER is below WB_VBL_COUNTER_READY, as a SIGNED word: `cmpi.w
 * #$1,d0 / blt.s`. Nothing in this routine raises the counter; vbl_handler does, fifty times a
 * second, and off target the case's schedule is what stands in for it. */
static int wait_for_vbl_ready(uint8_t *image) {
    uint16_t counter;

    while (sched_poll16(image, WB_VBL_COUNTER, WB_FLIP_READY_WAIT_PC, &counter))
        if ((int16_t)counter >= WB_VBL_COUNTER_READY)
            return 1;
    return 0;   /* the cap: the model has refused, and the caller returns (see sched.h) */
}

/* $6ca..$6d6 — spin until WB_VBL_COUNTER differs from the copy taken at $6ca.
 *
 * THE COPY IS NOT A POLL. `move.w $74a.l,d0` runs ONCE, above the loop, and the branch goes back to
 * the compare below it — so this wait always spins at least once and cannot be seeded past, which is
 * the property that made the composite case at the top of this routine look driveable. */
static int wait_for_vbl_tick(uint8_t *image) {
    uint16_t before = bus_read_word(image, WB_VBL_COUNTER);
    uint16_t counter;

    while (sched_poll16(image, WB_VBL_COUNTER, WB_FLIP_TICK_WAIT_PC, &counter))
        if (counter != before)
            return 1;
    return 0;
}

void flip_screen(uint8_t *image) {
    uint32_t was_front = bus_read_long(image, WB_SCREEN_FRONT);

    bus_write_long(image, WB_SCREEN_FRONT, bus_read_long(image, WB_SCREEN_BACK));
    bus_write_long(image, WB_SCREEN_BACK, was_front);

    if (!wait_for_vbl_ready(image))
        return;
    /* AFTER the swap and AFTER the wait, so what is published is the buffer that has just BECOME
     * the front one — the two `move.b`s read $74d/$74e, which are inside the longword written two
     * instructions above. */
    shifter_screen_base_write(bus_read_byte(image, WB_SCREEN_FRONT_BITS_16_23),
                              bus_read_byte(image, WB_SCREEN_FRONT_BITS_8_15));

    if (!wait_for_vbl_tick(image))
        return;
    wr16(image + WB_VBL_COUNTER, 0);
    /* `not.w $712.l` — a 0 <-> $ffff TOGGLE, not a decrement. */
    wr16(image + WB_FRAME_TOGGLE, (uint16_t)~bus_read_word(image, WB_FRAME_TOGGLE));

    uint16_t flash = bus_read_word(image, WB_FLASH_TIMER);
    if (flash == 0)
        return;
    flash = (uint16_t)(flash - 1);
    wr16(image + WB_FLASH_TIMER, flash);
    /* The two arms are EXCLUSIVE and both write colour 0: white while the countdown still has
     * frames to run, black on the frame it reaches zero. `subq.w #1 / beq.w` branches on the
     * DECREMENT's result, which is the word just stored. */
    shifter_palette_write(WB_FLASH_PEN, flash ? WB_FLASH_COLOUR_WHITE : 0);
}


/* --- $4a0: THE FRAME LOOP ITSELF ---------------------------------------------------------------
 *
 * `do { ... } while (1)`: $508 is `bra.s $4a0` and there is no exit instruction. The boot chain
 * `jmp $4a0.w`s into it once, from $f8b4 — the instruction after `stage_load_window` — and the
 * program spends the rest of its life here. Two addresses in the image hold that `jmp` and an
 * earlier revision of this plate named both as entries; only $f8b4 is live, because $e6fc's
 * `bsr.w $f89e` never returns ($f89e falls off its own end into $f8b4). ../names.txt cmt 0x4a0 has
 * the census.
 *
 * FIFTEEN CALLS, and this function is nothing else — two leading `bsr`s, a four-call block that runs
 * only while the game is NOT paused, eight more, and the flip. Every one of them is reconstructed,
 * which is what made this the last row of the spine rather than the first: a caller is only as
 * portable as its callees.
 *
 * ONE ITERATION IS THE DIFFERENTIAL UNIT. A case enters at $4a0 and checkpoints the backward branch
 * at $508 — the same shape the scene driver's tails use — so what is compared is the whole frame's
 * memory at the instant control turns round.
 *
 * BUT $508 IS NOT THE ONLY WAY OUT OF ONE ITERATION — THERE ARE FIVE MORE, AND THEY ARE NOT ALL
 * game_key_actions'. Three of that routine's endings POP this routine's return address and `jmp`
 * into the boot chain, so a frame entered with the round-end request raised — or with the cheat on
 * and N held, or with ESC held — leaves through the second `bsr` and never reaches $508. The other
 * two leave through the FOURTH call of the gated block: the behaviour pass hands its callee's
 * report up unchanged, and four of that report's values are the player's own `jmp`s into the very
 * same two boot addresses (../include/game.h's census). This function reports WHICH of the five, in
 * place of the transfer it cannot make, and a case for such a frame checkpoints the original's own
 * `jmp` instead.
 *
 * THE ONE ARGUMENT IS THE SPRITE PASS'S REGISTER FILE. Everything else the loop calls reads and
 * writes memory alone; `sprite_draw_pass` is register glue (include/blit.h), and its `unwind` is a
 * real input the frame carries in a5. */

/* Which of the loop's two REMAINING exits `report` names, or WB_KEY_ACTIONS_RETURNED for a report
 * that leaves the frame running. `report` is `actor_behavior_pass`' answer for the whole walk.
 *
 * THE FOUR VALUES ARE A CENSUS OF THE IMAGE AND NOT A GUESS, and ../include/game.h has it beside
 * the two codes: they are the four `jmp`s into the boot chain that lie BELOW this pass in the call
 * graph, out of the seven the shipped bytes hold. The other three are game_key_actions' own and
 * never reach here.
 *
 * A `switch` RATHER THAN A RANGE TEST, because the report's number space is shared by three headers
 * (behavior.h's four codes, player.h's six, and a handler's entry ADDRESS) and nothing about a
 * value's magnitude says which it is. Every unlisted value — a refusal, a runaway, an
 * unreconstructed handler, or WB_ACTOR_DISPATCH_RAN itself — leaves the loop running: those are
 * boundaries of THIS PORT rather than places the original went, so there is no transfer to stand in
 * for. ../STATUS.md §6 records what that costs on target. */
static uint32_t loop_exit_for_pass_report(uint32_t report) {
    switch (report) {
    case WB_PLAYER_GATE_DATADISK_UNWIND:    /* $bd8/$bdc — the game-over box's expiry */
    case WB_SHOW_DATA_DISK_PROMPT:          /* $700a/$700e — slot 61's terminator */
        return WB_LOOP_EXIT_DATA_DISK;
    case WB_PLAYER_GATE_RESTART_UNWIND:     /* $c1c/$c20 — a life spent, the stage reloaded */
    case WB_PLAYER_COLLIDE_UNWIND:          /* $1622/$1626 — the collision map's triple pop */
        return WB_LOOP_EXIT_RELOAD;
    default:
        return WB_KEY_ACTIONS_RETURNED;
    }
}

uint32_t game_main_loop(uint8_t *image, sprite_pass_regs *sprites) {
    game_unpause_on_key_release(image);                     /* $4a0 */
    uint32_t action = game_key_actions(image);              /* $4a4 */
    if (action != WB_KEY_ACTIONS_RETURNED)
        return action;                                      /* $550 / $56e / $598: the loop is LEFT */

    /* $4a8. Pausing does not stop the frame — it stops these four calls. The screen still flips, the
     * message box still runs, and the sprites are still drawn from the projection the last unpaused
     * frame left, which is why a paused game shows a still picture rather than a black one. */
    if (!bus_read_word(image, WB_GAME_PAUSED)) {
        round_bonus_run_frame(image);                       /* $4b2 */
        panel_refresh_frame(image);                         /* $4b8 */
        (void)scene_run_frame(image);                       /* $4be — which tail it took is dropped */
        /* $4c4. THE PASS'S REPORT IS NOT DROPPED, and four of its values end the iteration where
         * the original's own `jmp` does — see `loop_exit_for_pass_report` above. */
        uint32_t unwound = loop_exit_for_pass_report(game_latch_input_and_step_actors(image));
        if (unwound != WB_KEY_ACTIONS_RETURNED)
            return unwound;                                 /* $bdc / $700e / $c20 / $1626 */
    }
    project_followed_actor(image);                          /* $4ca */
    bg_scroll_run_queue(image);                             /* $4d0 */
    project_actor_list(image);                              /* $4d6 */
    bg_scroll_blit(image);                                  /* $4dc */
    game_snap_follow_cursor(image);                         /* $4e2 */
    sprite_draw_pass(image, sprites);                       /* $4e6 */
    /* $4ec. The A30 mode — the round-bonus stage — spawns nothing. */
    if (!bus_read_word(image, WB_STATE_FLAG_A30))
        actor_spawn_pass(image);                            /* $4f6 */
    text_run_message_box(image);                            /* $4fc */
    flip_screen(image);                                     /* $502 */
    return WB_KEY_ACTIONS_RETURNED;                         /* $508 `bra.s $4a0` */
}
