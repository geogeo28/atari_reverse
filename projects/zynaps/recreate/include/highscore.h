/* highscore.h — the ROLE OF HONOUR table and the screens around it (src/highscore.c).
 * Subsystem: highscore.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THE TABLE IS FIVE 22-BYTE ENTRIES, and each one is a BCD score followed by a `draw_text_record`
 * record — the same {column, row, characters..., 0} shape include/text.h describes. So the name row
 * needs no separate layout: the record carries its own column and row, and the five shipped rows
 * are 110, 122, 134, 146 and 158, which is where `role_of_honour_screen` draws the scores too.
 *
 *   +0x00  .l  the entry's score, packed BCD
 *   +0x04  .b  the record's column (0x10 in all five)
 *   +0x05  .b  the record's row
 *   +0x06      15 characters of name, then the record's 0 terminator
 */
#ifndef ZYNAPS_HIGHSCORE_H
#define ZYNAPS_HIGHSCORE_H

#include <stdint.h>

#define A_highscore_table 0x19d5au
#define HIGHSCORE_ENTRIES 5u
#define HIGHSCORE_ENTRY_BYTES 0x16u  /* `mulu.w #$16,d0` in highscore_check_and_insert */
#define HIGHSCORE_ENTRY_RECORD 4u    /* the text record starts one longword in */
#define HIGHSCORE_DIGITS_COLUMN 0xeu /* `move.w #$e,d1` — the rightmost digit's column */

/* WHAT THE SHIFT-DOWN ACTUALLY MOVES, and it is not the whole entry: `move.l -22(a0),(a0)`, then
 * `lea 6(a0),a0` and fifteen `move.b -22(a0),(a0)+`. So the score longword and the fifteen name
 * characters are carried down a row, while the record's own COLUMN and ROW bytes (+4, +5) and its
 * terminator (+0x15) stay where they are — which is exactly right, because those three describe the
 * ROW ON SCREEN and not the entry. A shift of all 22 bytes would carry row 110's coordinates onto
 * row 122 and the table would print itself on top of itself. */
#define HIGHSCORE_SHIFT_NAME_BYTES 0xfu   /* `move.w #$e,d0` + dbf */
#define HIGHSCORE_NAME_OFFSET 6u          /* `lea 6(a0),a0` — HIGHSCORE_ENTRY_RECORD + column+row */
/* The ranking scan starts at the LAST entry and walks BACKWARDS (`lea -22(a0),a0`), so its `dbf`
 * counter is a rank counted from the bottom. Stopping on the very first compare leaves it at
 * HIGHSCORE_ENTRIES - 1, and that is the "did not rate" answer — the one arm that leaves the
 * routine at 0x12f5a instead of 0x12f0e. Falling out of the loop leaves it at -1: the score beat
 * every entry. The table row the new score takes is the counter plus one. */
#define HIGHSCORE_NOT_RATED_COUNTER (HIGHSCORE_ENTRIES - 1u)

/* `lea 2560(a0),a0` — row 16, where `game_over_screen` prints the player's digit after the
 * GAME OVER PLAYER record. NOT include/hud.h's PLAYER_NAME_ROW_OFFSET, which is row 80: the two
 * screens print the same two pieces at different heights. */
#define GAME_OVER_DIGIT_ROW_OFFSET 0xa00u

/* BORROWED: ../out/globals.tsv assigns 0x199d9 to the **text** subsystem, with the rest of the
 * `A_msg_*` family, and `include/text.h` does not spell it — this is its first reader. Named here
 * under the same rule STATUS.md's "## Borrowed globals" table carries; moving it into text.h beside
 * its eight siblings is one line there and one deletion here. */
#define A_msg_game_over_player 0x199d9u

/* The heading above the five rows is `A_msg_role_of_honour` in include/text.h, with the other
 * shipped records; the five name records are the table's own, at HIGHSCORE_ENTRY_RECORD. */

/* Where the five SCORES go, and it is not read from the records: `role_of_honour_screen` carries a
 * `lea` displacement per entry, 1920 bytes (twelve rows) apart from 17600 (row 110). The shipped
 * records name the same five rows, so the screen looks the same either way — but the routine never
 * consults them, and src/highscore.c says why that distinction is kept. */
#define HIGHSCORE_FIRST_SCORE_OFFSET 0x44c0u
#define HIGHSCORE_SCORE_ROW_STEP 0x780u

/* ================================================================================================
 * `highscore_check_and_insert` @ 0x12eae — the two screens the ranking chooses between.
 *
 * THE TWO SCREENS DRAW INTO DIFFERENT BUFFERS, and that is not a detail: NEW HIGH SCORE goes into
 * the front end's compose page (`A_backdrop_page0`, video.h), because the name-entry loop below
 * blits that page onto the playfield once a frame; YOU ARE NOT RATED goes straight into
 * `A_screen_back`, on top of the GAME OVER the prologue left there, and is shown by the flip that
 * follows. A reconstruction that used one buffer for both agrees with the original on neither.
 * ============================================================================================= */
/* BORROWED, under the rule `A_msg_game_over_player` above is borrowed by: ../out/globals.tsv gives
 * both to the **text** subsystem and include/text.h does not spell them — this is their first
 * reader. text.h's header comment already names them as records "no ported routine reaches yet";
 * moving these two there is two lines there and two deletions here.
 *
 * BOTH NAMES ARE `# ctx` IN ../../names.txt (`msg_new_high_score`, also read as
 * `text_new_high_score`; `msg_you_are_not_rated`, also read as `text_not_rated`), so they are
 * proposals a later body read may overturn — README.md, "Names", obliges saying so here. What the
 * bodies DO is confirmed: this reconstruction draws each record and the differential compares the
 * pixels; it is the English name that is inferred. */
#define A_msg_new_high_score 0x199eeu
#define A_msg_you_are_not_rated 0x19a24u

/* `moveq #$1e,d1` and `moveq #$22,d1` into `sound_start`. Spelt `SFX_*` like include/weapon.h's
 * launch sounds, which is where the family's other members live. */
#define SFX_NEW_HIGH_SCORE 0x1eu
#define SFX_YOU_ARE_NOT_RATED 0x22u

/* What the routine answers in D0, and what its one caller branches on. Note that only the RATED
 * arm's answer ever reaches that branch — see `game_over_screen`'s prototype below. */
#define HIGHSCORE_RATED 1u
#define HIGHSCORE_NOT_RATED 0u

/* ================================================================================================
 * `highscore_enter_name` @ 0x12fd4 — PLEASE ENTER YOUR NAME, and the on-screen keyboard.
 *
 * The player spells fifteen characters into a `draw_text_record` record of its own
 * (`A_name_entry_record`), either by walking a gunsight over three drawn rows of letters with the
 * joystick and pressing fire, or by typing on the real keyboard; RETURN copies the record's
 * characters into the table slot the ranking freed. Everything on screen is composed into
 * `A_backdrop_page0` and blitted onto the playfield once a frame.
 *
 * ITS FIVE BUSY-WAITS ARE THE WHOLE REASON THIS ROUTINE WAS UNREACHABLE, and none of them is on a
 * byte the routine's own instructions can supply: the VBL flag is cleared by the VBL handler, the
 * scancode is stored by the ACIA handler, and the joystick byte is filled in by the packet the ACIA
 * handler assembles after each `ikbd_send_cmd`. Off target the kit's SCHEDULED WRITE model supplies
 * them (`tools/recreate_kit/include/sched.h`, TRAP_MODEL.md Phase 8), which is why every wait below
 * carries the PC the ORIGINAL re-reads its byte at: that address is the wait's identity on both
 * sides, and a poll naming a site the case did not declare is a refusal rather than a service.
 * ============================================================================================= */
/* BORROWED BY SUBJECT rather than by the table, and the distinction is the point: ../out/globals.tsv
 * has NO row for 0x19a0b. It has one for 0x19a0a — `msg_please_enter_your_name`, text — and that
 * address is the TERMINATOR of the message above, not the record: names.txt's `cmt 0x19a0a` says so
 * in as many words, and `lea $19a0b.l,a6` at 0x12fdc is what the routine actually loads. So the tsv
 * row is off by one and this name is `text_please_enter_name`, names.txt's own. The subsystem is
 * still text, and the migration is still one line there and one deletion here — but whoever makes
 * it should correct the tsv row rather than trust it. */
#define A_text_please_enter_name 0x19a0bu

/* The three drawn keyboard rows, as `draw_text_record` records — A..J, K..T and U..Z plus the four
 * wide keys. NOT include/input.h's `A_osk_row_top`/`_middle`/`_bottom`, which are the SCANCODE
 * tables `onscreen_keyboard_hit_test` indexes: those live in the text segment at 0x132e2 and hold
 * one byte per screen column, these are what the player actually sees. Two different things about
 * one keyboard, so two sets of names. */
#define A_text_osk_row1 0x19ce6u
#define A_text_osk_row2 0x19d05u
#define A_text_osk_row3 0x19d24u

/* The name being typed, as a record of exactly the table's own shape: {column 0x0b, row 0x50,
 * 15 characters, 0}. `NAME_ENTRY_FIRST_CHAR` is where its characters start — the same two bytes of
 * column and row every table entry carries — and the cursor index runs from there to
 * `NAME_ENTRY_LAST_CHAR`, which is the TERMINATOR's slot and so the fifteen-character cap. */
#define A_name_entry_record 0x19d48u
#define NAME_ENTRY_FIRST_CHAR 2u    /* `move.w #$2,d4` */
#define NAME_ENTRY_LAST_CHAR 0x11u  /* `cmp.w #$11,d4` — at this index the record is full */

/* .b — set by `st`/`sf` each edit frame: 0xff if this frame's key came from the joystick, 0 if it
 * did not. It is what picks which of the two release waits the next frame makes. */
#define A_name_entry_from_joystick 0x19ce4u
/* .b — the pixel-hit flag `draw_sprite_masked_collide` reports the gunsight's blit in (`lea
 * $19ce3,a5`). ../../names.txt has no name for this byte and ../out/globals.tsv no owner; the name
 * is this reconstruction's, proposed in ../out/names_highscore.txt. NOTHING READS IT — the blitter
 * writes it and the name-entry loop never looks — so it is a write-only side effect of drawing the
 * cursor as an entity, and the differential holds it as one of the bytes the run must produce. */
#define A_name_entry_cursor_hit 0x19ce3u

/* One character per IKBD scancode, `move.b (0,a0,d0.w),d1` with the scancode SIGN-EXTENDED — so a
 * scancode at or above 0x80 indexes BEFORE the table, into the message text below it, and a byte
 * with bit 7 set is "not a printable key" wherever it is read from. */
#define A_scancode_to_char_table 0x19a39u
/* `cmp.b #$72,d0` + `bgt` — the highest scancode the table lookup is allowed to see. It equals
 * SCANCODE_ENTER because Enter is the highest key this routine handles, and it is a separate name
 * because it is a separate instruction: one is an equality against a key, this is a bound. */
#define NAME_ENTRY_SCANCODE_MAX 0x72u

/* The six keys the dispatch names before it reaches the table. Esc and Undo clear the whole name,
 * Backspace and Delete erase one character, Return and Enter commit. */
#define SCANCODE_ESC 0x01u
#define SCANCODE_UNDO 0x61u
#define SCANCODE_BACKSPACE 0x0eu
#define SCANCODE_DELETE 0x53u
#define SCANCODE_RETURN 0x1cu
#define SCANCODE_ENTER 0x72u

/* BORROWED BY SUBJECT, the way include/init.h borrows `A_key_scancode`: this is the IKBD joystick
 * byte the ACIA handler (0x14456, unported) assembles, so it belongs beside that handler's other
 * bytes the day `input` claims it. Bits 0..3 are the four directions and bit 7 is fire, which is
 * why the original tests the first four with `btst` and the last with `tst.b` + `bmi`. */
#define A_joystick_state 0x19681u
#define JOYSTICK_UP 0x01u
#define JOYSTICK_DOWN 0x02u
#define JOYSTICK_LEFT 0x04u
#define JOYSTICK_RIGHT 0x08u
#define JOYSTICK_FIRE 0x80u
/* `move.b #$16,d0` before every `ikbd_send_cmd` here: interrogate the joystick, which makes the
 * controller send the packet the byte above is filled in from. */
#define IKBD_CMD_JOYSTICK_INTERROGATE 0x16u

/* The gunsight is drawn as ENTITY RECORD 0 of `A_entity_table` (include/player.h) — the front end
 * has no live entities, so the name-entry loop borrows the first slot and rewrites its five fields
 * every frame. The sprite is a preshift bank in bss; `../../names.txt` reaches 0x6a61e only through
 * this routine, so the name is this reconstruction's. */
#define A_gunsight_sprite 0x6a61eu
#define GUNSIGHT_ROWS 9u   /* `move.w #$9,8(a2)` — the record's height field */

/* Where the cursor starts, in the WORLD coordinates `draw_sprite_masked_collide` reads its records
 * in, and how far one joystick tick moves it (`subq.w #2` / `addq.w #2`). The two coordinates
 * themselves are include/input.h's `A_osk_cursor_x` / `A_osk_cursor_y` — the same two words
 * `onscreen_keyboard_hit_test` turns into a scancode. */
#define OSK_HOME_X 0x50u
#define OSK_HOME_Y 0x41u
#define OSK_CURSOR_STEP 2u

/* `lea 12800(a0),a0` — row 80 of the compose page, where the block cursor is drawn and erased.
 * The name record at `A_name_entry_record` carries row 0x50 too, so the two agree on the shipped
 * data; the routine never consults the record for it, exactly as `role_of_honour_screen` never
 * consults its records for the score rows. NOT include/hud.h's PLAYER_NAME_ROW_OFFSET, which is
 * the same 12800 bytes for the PLAYER digit on a different screen. */
#define NAME_ENTRY_ROW_OFFSET 0x3200u
#define NAME_ENTRY_CURSOR_COLUMN_BIAS 9u  /* `add.w #$9,d1` — cursor index to screen column */

/* The blank and the commit are the same four longwords twice over: fifteen `CHAR_CLEAR_CELL`
 * characters and the record's 0 terminator, written as `move.l #$1010101` three times and
 * `#$1010100` once, and later copied whole into the table slot at `HIGHSCORE_NAME_OFFSET`. */
#define NAME_ENTRY_NAME_LONGS 4u
#define NAME_ENTRY_BLANK_FILL 0x01010101u
#define NAME_ENTRY_BLANK_TAIL 0x01010100u

/* ---- the wait sites, as the PCs the ORIGINAL re-reads each polled byte at -----------------------
 *
 * Every one of these is the address of the instruction the original's spin loop comes back to, and
 * that is what the kit's model keys a wait on (sched.h: "THE SITE IS THE PC AND NEVER THE ADDRESS"
 * — two of the waits below poll the SAME byte). A case declares the sites its run reaches, and
 * `OS_SCHED_SITE_MAX` bounds how many one run may declare; STATUS.md's "## Coverage limits" says
 * which paths that bound keeps out of a single run. */
#define NAME_ENTRY_KEY_WAIT_PC 0x13104u             /* `move.b $19685,d0` — the edit loop's own */
#define NAME_ENTRY_IDLE_VBL_WAIT_PC 0x13118u        /* `tst.b $198a7` with no key this frame */
#define NAME_ENTRY_VBL_WAIT_PC 0x131d0u             /* ...and the one after a redraw */
#define NAME_ENTRY_FIRE_RELEASE_WAIT_PC 0x131eeu    /* `tst.b $19681` after a joystick pick */
#define NAME_ENTRY_KEY_RELEASE_WAIT_PC 0x131fau     /* `tst.b $19685` after a typed key */
#define NAME_ENTRY_COMMIT_WAIT_PC 0x13264u          /* ...and the one RETURN leaves through */
#define NOT_RATED_FIRE_PRESS_WAIT_PC 0x12f9au       /* `tst.b $19681` + `bpl` — waiting for fire */
#define NOT_RATED_FIRE_RELEASE_WAIT_PC 0x12fb2u     /* ...and `bmi`, waiting for it to come up */

void role_of_honour_screen(uint8_t *image);

/* `game_over_screen` @ 0x12e66 — clear the playfield, print GAME OVER PLAYER n, and run the
 * high-score check. The frame loop's death handler (0x1276e) calls it on the last life.
 *
 * IT HAS NOTHING AFTER THE CALL, and the four instructions that look as though it does are DEAD.
 * 0x12e98 is a `bne` over an eight-longword palette restore, set up by the `moveq #$0,d0 / tst.b
 * d0` the NOT RATED arm ends with — but that arm never gets back here: 0x12fba pops one longword
 * too many (a `movea.l (a7)+,a0` copied from the rated arm, whose matching push at 0x12f20 the
 * not-rated path never makes), so its `rts` returns to THIS routine's caller instead. The rated arm
 * does come back, with D0 = 1, and takes the `bne` over the restore. So the restore runs on neither
 * arm, and the reconstruction does not make it — which `test_highscore.py` holds by driving both
 * arms to `rts` over a seeded `A_menu_palette`.
 *
 * The stack still balances from the caller's side — both arms leave A7 where it was and land at the
 * same address — so this is an ordinary C function despite the imbalance one level down. */
void game_over_screen(uint8_t *image);
/* `game_over_screen` is a `# ctx` name in ../../names.txt (also read there as `game_over_player`),
 * so README.md, "Names", obliges the note: it is a call-context proposal. This reconstruction read
 * the body end to end and ../out/names_highscore.txt proposes dropping the tag — until that lands,
 * treat a rename as possible. */

/* [0x12e66, 0x12e94) — the paragraph of `game_over_screen` above the `bsr`, kept as a routine of
 * its own because its checkpoint slice is still the only case that can drive the digit's column
 * and row without a screen full of high-score composition on top of it. */
void game_over_screen_prologue(uint8_t *image);

/* `highscore_check_and_insert` @ 0x12eae — rank the player's score, and run whichever screen the
 * answer calls for. Answers `HIGHSCORE_RATED` / `HIGHSCORE_NOT_RATED` in D0.
 *
 * ITS NOT-RATED ARM CANNOT BE RUN TO ITS OWN `rts`, for the stack reason `game_over_screen` above
 * states: the `rts` at 0x12fc0 returns one level too far. A case drives that arm either as a
 * checkpoint at 0x12fc0 or through `game_over_screen`, which does reach an `rts` on both arms. */
unsigned highscore_check_and_insert(uint8_t *image);

/* [0x12eb2, 0x12f0e) and [0x12eb2, 0x12f5a) — where the score ranks and the shift-down that makes
 * room for it, kept as a routine of its own for `game_over_screen_prologue`'s reason: its two
 * mid-entry checkpoints are what drive the ranking's boundaries without a screen attached. Returns
 * the TABLE ROW the new score takes, or HIGHSCORE_ENTRIES when it did not rate. */
unsigned highscore_rank_and_shift(uint8_t *image);

/* `highscore_enter_name` @ 0x12fd4 — spell a name into `slot`, which is the table entry
 * `highscore_check_and_insert` has just freed. Returns when RETURN or Enter commits it, or early
 * (with nothing more written) when one of its waits gives up — see src/highscore.c. */
void highscore_enter_name(uint8_t *image, uint32_t slot);

/* WHICH BLOCK OF THE EDIT LOOP RUNS NEXT, and the original states it as the address it jumps to
 * rather than as data — so the addresses are what these name, and a case that drives one arm stops
 * the oracle at that address. */
enum name_entry_step {
    NAME_ENTRY_STEP_REDRAW,   /* 0x13196 — the record changed, or the cursor moved */
    NAME_ENTRY_STEP_KEEP,     /* 0x131c4 — nothing changed; show the page as it stands.
                               * NOT A DISTINCT EXIT in the original: 0x131c2 falls through into
                               * 0x131c4, so a case that stops the oracle here has not proved the
                               * redraw was skipped — the compose page's bytes are what say that. */
    NAME_ENTRY_STEP_COMMIT    /* 0x1324a — RETURN: the name goes into the table slot */
};

/* [0x13196, 0x131c4) — the REDRAW block on its own: the name record into the compose page and the
 * block cursor over the slot the next character would take, or no cursor once the record is full.
 * Exported for one reason the loop cannot serve — `cmp.w #$11,d4` + `bge` is a SIGNED compare, and
 * the loop's own guards keep D4 in [2, 0x11], where signed and unsigned agree. Entered here a case
 * can hand it any cursor at all. `cursor` is D4 and the record is A5, a constant of this routine. */
void name_entry_redraw(uint8_t *image, uint16_t cursor);

/* [0x13058, 0x13196) / [0x13058, 0x131c4) / [0x13058, 0x1324a) — the loop's body: draw the frame
 * and spin until a scancode arrives, then apply it. Exported so that the differential can enter the
 * loop where the original does, at whichever of the three addresses the key chooses — the same code
 * `highscore_enter_name` runs, rather than a second composition of the two halves.
 *
 * `cursor` is the original's D4 in and out, a WORD; `step` is written only on a 1. The 0 is a wait
 * the harness refused and NOT an arm of the original, which is why it is an `int` here rather than
 * a fourth enumerator — every other wait in src/highscore.c reports the same thing the same way. */
int name_entry_edit_step(uint8_t *image, uint16_t *cursor, enum name_entry_step *step);
/* How `g_name_entry_edit_step` packs its two answers: the cursor in the low word, the step above
 * it. The two constants are a pair — a shift that moved without its mask would OR a step over a
 * cursor — so they are defined together and mirrored together. */
#define NAME_ENTRY_STEP_SHIFT 16u
#define NAME_ENTRY_STEP_CURSOR_MASK 0xffffu

/* Lets a frame stage in another agent's file drop its temporary `game_over_screen` stub. */
#define ZYNAPS_HIGHSCORE_HAS_GAME_OVER 1

#endif /* ZYNAPS_HIGHSCORE_H */
