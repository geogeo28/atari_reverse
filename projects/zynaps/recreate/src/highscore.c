/* highscore.c — the ROLE OF HONOUR screen, the GAME OVER screen, and everything between a player's
 * last life and their name in the table.
 *
 * The table's five entries are score-plus-record pairs (highscore.h), so drawing the screen is the
 * logo, a heading, and then each entry's own record and score at the row the record already names.
 *
 * THE GAME-OVER CHAIN IS THREE ROUTINES DEEP and reads as one story: `game_over_screen` prints
 * GAME OVER PLAYER n, `highscore_check_and_insert` ranks the score and picks a screen, and
 * `highscore_enter_name` runs the on-screen keyboard. Two things about it are worth knowing before
 * reading any of them.
 *
 * FIRST, THE WAITS. The name-entry loop and the NOT RATED screen busy-wait on four bytes no
 * instruction in this file writes — the VBL flag, the IKBD scancode and the joystick byte (twice
 * over, for a press and for a release). Off target those bytes arrive from the kit's SCHEDULED
 * WRITE model, so each wait is spelt with `sched_wait8`/`sched_poll8` and names the PC the
 * ORIGINAL re-reads its byte at; include/highscore.h lists the eight sites and says why the PC and
 * not the address is the wait's identity. Every such wait can also GIVE UP — the cap is the kit's,
 * for a case whose schedule never releases it — and a caller must honour the 0 by returning rather
 * than carrying on as though the byte had arrived (sched.h). That is what the `if (!...) return;`
 * chains below are; on target the same loops are the original's, unbounded.
 *
 * SECOND, THE STACK. `highscore_check_and_insert`'s NOT RATED arm pops one longword too many and so
 * returns two levels up, which makes `game_over_screen`'s palette restore unreachable on both arms.
 * include/highscore.h's `game_over_screen` prototype has the argument; it is stated once there.
 */
#include "machine.h"
#include "os.h"        /* OS_SCHED_POLL_MAX and os_refused — the cap every wait here gives up at */
#include "sched.h"     /* the scheduled-write model's polls; include/highscore.h says why */
#include "enemy.h"     /* SCC_BYTE_TRUE / SCC_BYTE_FALSE — the two bytes `st`/`sf` store */
#include "entity.h"
#include "highscore.h"
#include "hud.h"
#include "input.h"
#include "irq.h"
#include "init.h"
#include "player.h"
#include "score.h"
#include "scroll.h"
#include "sound.h"
#include "sprite.h"
#include "text.h"
#include "video.h"

static uint32_t highscore_entry(unsigned row) {
    return addr_add(A_highscore_table, row * HIGHSCORE_ENTRY_BYTES);
}

/* `move.l (aN)+,(aM)+` in a `dbf` loop — a FOURTH copy of it in this reconstruction (src/hud.c's
 * `copy_longwords`, src/scroll.c's `copy_longs`, src/video.c's `zero_longs`), each static to its own
 * file because the shared home for it is the kit's machine.h and moving it there is a change none of
 * the four owns. STATUS.md books the debt in one place, under `src/hud.c`'s mutation sub-table.
 * Three callers here: the two palette installs and the name commit. */
static void copy_longwords(uint8_t *image, uint32_t source, uint32_t destination,
                           unsigned longwords) {
    for (unsigned i = 0; i < longwords; i++) {
        wr32(image + destination, be32(image + source));
        source = addr_add(source, sizeof(uint32_t));
        destination = addr_add(destination, sizeof(uint32_t));
    }
}

/* `movem.l $195f8,d0-d7` then `movem.l d0-d7,$19f46`: the front end's sixteen pens into the shadow
 * the menu VBL uploads. src/hud.c keeps an identical static for the intro screen; this is the copy
 * the two high-score screens make, four instructions apart on either arm.
 *
 * IT ANSWERS THE BYTE D0 IS LEFT HOLDING, because that is what both call sites hand to
 * `sound_start` two instructions later — the `movem.l` loads D0 from the palette's FIRST LONGWORD
 * and nothing between reloads it, so the byte is that longword's low eighth. A shifter pen is a
 * WORD, so the longword is pens 0 and 1 and the byte is PEN 1's low half — worth spelling out,
 * because "the first pen" is the wrong place to look. `sound_start` reads it as the voice to fall
 * back on when the effect's own stream carries no 0xfa channel header (include/sound.h), and both
 * of this file's streams carry one, so it decides nothing today. Returning it here is what keeps
 * the relationship visible instead of leaving a bare `be32` at each call site.
 *
 * DUPLICATED, and knowingly: `src/hud.c` holds a byte-identical body under this same name for the
 * intro screen, and its comment there still says nothing outside that file makes the copy — which
 * this change makes false. Merging them means exporting hud.c's and widening its return type, in a
 * file this wave does not own; STATUS.md's mutation ledger records both halves of the debt. */
static uint8_t install_frontend_palette(uint8_t *image) {
    copy_longwords(image, A_palette_frontend, A_menu_palette, SHIFTER_PALETTE_PAIRS);
    return (uint8_t)be32(image + A_palette_frontend);
}

/* THE GIVE-UP the two hand-rolled waits in this file share, and it is OFF TARGET ONLY.
 *
 * It tallies through `os_refused` and NOT through the kit's own `sched_give_up`, which is static to
 * `src/sched.c` and unexported: so `harness.differential` still throws such a case away by name,
 * but `g_sched_exhausted()` does not count these two and the refusal hint reads as generic rather
 * than as "a wait ran out of polls". The remedy is an exported give-up in sched.h, which is a kit
 * change; recorded in STATUS.md rather than worked around here.
 *
 * `sched_wait8` owns its own cap because it owns its own predicate; the two loops below cannot use
 * it — one asks the IKBD for a packet before each look and tests a BIT rather than the whole byte,
 * the other draws a whole frame — so they carry the cap themselves and this is the one place it is
 * spelt. Off target a wait the case's schedule never releases must end as a named refusal rather
 * than as a hung pytest worker (sched.h); ON TARGET IT MUST NOT BIND AT ALL, which is why the body
 * is compiled away by `OS_NO_REFUSAL_TALLY`. The argument is src/input.c's, one register over:
 * `ikbd_send_cmd` makes exactly this split, and include/input.h states it once — a bound that is a
 * fact about the MODEL, kept out of a build where the VBL and the ACIA really do write these bytes
 * and a spin that gave up on a slow frame would carry on as though the key had arrived. */
static int wait_should_give_up(unsigned polls) {
#ifdef OS_NO_REFUSAL_TALLY
    (void)polls;
    return 0;                     /* on target the spin is the original's: unbounded */
#else
    if (polls < OS_SCHED_POLL_MAX)
        return 0;
    (void)os_refused(0);
    return 1;
#endif
}

/* `move.b #$16,d0 / bsr ikbd_send_cmd / tst.b $19681 / bmi` — ask the controller for a joystick
 * packet and go round again until FIRE is in the state the caller wants. Three call sites: the two
 * halves of the NOT RATED "press fire to continue", and the release wait each committed key ends
 * with.
 *
 * THE NOT RATED PAIR INTERPOSE A `dbf` OF 1001 PASSES between the send and the test, and it is not
 * reproduced: it changes no byte, so no differential can see it either way. That is a real residual
 * ON target, where it is the only thing pacing one interrogation against the next — STATUS.md's
 * "## On target" carries it, because a delay counted in 68000 cycles has no meaning in C. */
static int joystick_wait_for_fire(uint8_t *image, uint32_t site_pc, int want_fire_down) {
    for (unsigned polls = 1; ; polls++) {
        uint8_t state;

        ikbd_send_cmd(IKBD_CMD_JOYSTICK_INTERROGATE);
        state = sched_poll8(image, A_joystick_state, site_pc);
        if (((state & JOYSTICK_FIRE) != 0) == (want_fire_down != 0))
            return 1;
        if (wait_should_give_up(polls))
            return 0;
    }
}

/* Carry every entry below `rank` one row down, LAST ONE FIRST, so that row `rank` is free.
 *
 * Only the score and the fifteen name characters move; include/highscore.h says why the record's
 * column, row and terminator stay put. The bound is what the original spells as `move.w #$2,d1 /
 * sub.w d0,d1` and a `dbf`, plus the `cmp.w #$3,d0` / `beq` that jumps the loop entirely — and that
 * branch is load-bearing rather than an optimisation, because at a counter of 3 the `dbf` count
 * would be -1 and the shift would run 65,536 times. `row > rank` is the same statement without a
 * second branch: at rank HIGHSCORE_ENTRIES - 1 it simply moves nothing. */
static void highscore_shift_down(uint8_t *image, unsigned rank) {
    for (unsigned row = HIGHSCORE_ENTRIES - 1u; row > rank; row--) {
        uint32_t into = highscore_entry(row);
        uint32_t from = highscore_entry(row - 1u);

        wr32(image + into, be32(image + from));
        for (unsigned character = 0; character < HIGHSCORE_SHIFT_NAME_BYTES; character++)
            image[into + HIGHSCORE_NAME_OFFSET + character] =
                image[from + HIGHSCORE_NAME_OFFSET + character];
    }
}

/* Clear the draw buffer, put the logo and the heading up, then one record and one score per entry.
 *
 * THE SCORES ARE DRAWN AFTER ALL SIX RECORDS, not interleaved with them, and — this is the part a
 * reader will not guess — each score's row is a `lea` DISPLACEMENT OF THE ROUTINE'S OWN, not the row
 * byte of the record beside it. The two agree entry for entry in the shipped table (110, 122, 134,
 * 146, 158 on both sides), so nothing on screen shows the difference; but the routine does not read
 * the record for it, and a table whose record rows had been edited would put the names and the
 * scores on different lines. test_highscore.py drives exactly that, so the two are not conflated.
 */
void role_of_honour_screen(uint8_t *image) {
    uint32_t buffer = be32(image + A_screen_back);

    screen_clear(image, buffer);
    hud_blit_zynaps_logo(image, buffer, LOGO_TITLE_OFFSET);
    draw_text_record(image, buffer, A_msg_role_of_honour, NULL);
    for (unsigned entry = 0; entry < HIGHSCORE_ENTRIES; entry++)
        draw_text_record(image, buffer,
                         addr_add(A_highscore_table,
                                  entry * HIGHSCORE_ENTRY_BYTES + HIGHSCORE_ENTRY_RECORD), NULL);
    for (unsigned entry = 0; entry < HIGHSCORE_ENTRIES; entry++) {
        uint32_t row_base = addr_add(buffer, HIGHSCORE_FIRST_SCORE_OFFSET
                                             + entry * HIGHSCORE_SCORE_ROW_STEP);
        uint32_t score = be32(image + addr_add(A_highscore_table,
                                               entry * HIGHSCORE_ENTRY_BYTES));

        ZY_TEXT(draw_bcd_number)(image, row_base, HIGHSCORE_DIGITS_COLUMN, score);
    }
    screen_flip_buffers(image);
}

/* game_over_screen_prologue — [0x12e66, 0x12e94), everything `game_over_screen` does before it asks
 * whether the score rated.
 *
 * Clear the playfield, print GAME OVER PLAYER into the back buffer, and put the player's digit at
 * the column the record ran out at — the same `draw_text_record` leftover `player_intro_screen`
 * uses, at a different row.
 *
 * IT DOES NOT FLIP THE BUFFERS, unlike the two front-end screens in src/hud.c: the high-score
 * screens that follow draw into the same back buffer, so the whole sequence is composed first. */
void game_over_screen_prologue(uint8_t *image) {
    uint32_t buffer;
    uint16_t column;

    playfield_clear(image);
    buffer = be32(image + A_screen_back);
    draw_text_record(image, buffer, A_msg_game_over_player, &column);
    ZY_TEXT(draw_char)(image, addr_add(buffer, GAME_OVER_DIGIT_ROW_OFFSET), column,
                       (uint16_t)sign_ext8((uint8_t)(image[A_current_player_index]
                                                     + PLAYER_DIGIT_CHAR_ZERO)));
}

/* highscore_rank_and_shift — [0x12eb2, 0x12f0e) and [0x12eb2, 0x12f5a).
 *
 * The ranking paragraph of `highscore_check_and_insert` below: find where the player's score
 * belongs in the five-entry table and shift the entries below it down a row. It is a routine of its
 * own because its two mid-entry checkpoints are the only cases that can drive the compare's
 * boundaries without a whole composed screen on top of them.
 *
 * `cmp.l (a0),d1` + `ble` IS A SIGNED LONGWORD COMPARE and the scores are packed BCD, so a table
 * entry with bit 31 set — 0x80000000 up, which BCD spells as eight thousand million — reads as
 * negative and every player score beats it. The shipped table holds nothing like that; the compare
 * is transcribed as signed because that is the instruction.
 *
 * The answer is the table ROW, which the original leaves in D6 and turns into an address at 0x12f0e.
 * HIGHSCORE_ENTRIES means "did not rate", which is the arm that leaves at 0x12f5a instead. */
unsigned highscore_rank_and_shift(uint8_t *image) {
    int32_t score = (int32_t)be32(image + A_player_score_bcd);
    /* The `dbf` counter, and it is SIGNED because falling out of the loop leaves it at -1. */
    int counter = (int)HIGHSCORE_ENTRIES - 1;
    unsigned rank;

    while (counter >= 0 && score > (int32_t)be32(image + highscore_entry((unsigned)counter)))
        counter--;
    if (counter == (int)HIGHSCORE_NOT_RATED_COUNTER)
        return HIGHSCORE_ENTRIES;

    rank = (unsigned)(counter + 1);
    highscore_shift_down(image, rank);
    return rank;
}

/* ================================================================================================
 * highscore_enter_name @ 0x12fd4 — PLEASE ENTER YOUR NAME
 *
 * The routine is one loop with four blocks in it, and the original's four addresses are worth
 * keeping in view because every arm of the dispatch jumps to one of them:
 *
 *   0x13196  REDRAW  the name record and the block cursor, into the compose page
 *   0x131c4  SHOW    flip, wait a frame, then wait for the key that caused it to be let go
 *   0x13058  FRAME   draw the gunsight, read the joystick, and spin until a scancode arrives
 *   0x13124  KEY     turn that scancode into a character, an erase, a clear, or the commit
 *
 * The only unusual edge is KEY -> SHOW: three arms (an unknown key, an unprintable one, and a
 * fifteenth character already typed) skip the redraw and show the page unchanged, which is what
 * `redraw` below carries. Every other arm goes back to REDRAW, and RETURN leaves.
 *
 * The cursor index the blocks pass around is the original's D4: an index into the name RECORD, so
 * it starts at NAME_ENTRY_FIRST_CHAR rather than at 0 and stops at the terminator's slot. It is a
 * `uint16_t` HERE FOR THE SAME REASON IT IS D4.W THERE — every instruction that moves or tests it
 * is a word instruction, so the type is what makes `add.w`'s wrap and `bge`'s sign the C's as well.
 * That matters past the loop: `name_entry_edit_step` is exported so a case can enter one pass with
 * any cursor at all, and at 0xffff the original indexes the record from BELOW and still draws its
 * block cursor. Inside the loop the two guards (`cmp.w #$11,d4` before an insert, `cmp.w #$2,d4`
 * before an erase) keep it in [NAME_ENTRY_FIRST_CHAR, NAME_ENTRY_LAST_CHAR] and none of that shows.
 * ============================================================================================= */

/* Fifteen `CHAR_CLEAR_CELL` characters and the record's 0 terminator, as four `move.l`s. Two
 * callers, and they write the same sixteen bytes: the routine's own opening, and the Esc/Undo arm
 * (which spells it with `lea 2(a5),a5` first, so the four longwords land at the same address). */
static void name_entry_blank(uint8_t *image) {
    uint32_t at = addr_add(A_name_entry_record, NAME_ENTRY_FIRST_CHAR);

    for (unsigned i = 0; i < NAME_ENTRY_NAME_LONGS; i++) {
        wr32(image + at, i + 1u == NAME_ENTRY_NAME_LONGS ? NAME_ENTRY_BLANK_TAIL
                                                         : NAME_ENTRY_BLANK_FILL);
        at = addr_add(at, sizeof(uint32_t));
    }
}

/* Where one character of the name sits, indexed the way the original does it — `(0,a5,d4.w)` off
 * the record's base, so the index carries the record's own column and row bytes with it. */
static uint32_t name_entry_character(uint16_t cursor) {
    return addr_add(A_name_entry_record, sign_ext16(cursor));
}

/* 0x13196 — the name into the compose page, then the block cursor over the slot the next character
 * would take. `cmp.w #$11,d4` + `bge` hides the cursor once the record is full, and it is SIGNED:
 * include/highscore.h says why that is worth its own entry point. */
void name_entry_redraw(uint8_t *image, uint16_t cursor) {
    draw_text_record(image, A_backdrop_page0, A_name_entry_record, NULL);
    if ((int16_t)cursor < (int16_t)NAME_ENTRY_LAST_CHAR)
        ZY_TEXT(draw_char)(image, addr_add(A_backdrop_page0, NAME_ENTRY_ROW_OFFSET),
                           (uint16_t)(cursor + NAME_ENTRY_CURSOR_COLUMN_BIAS), CHAR_FILL_CELL);
}

/* `move.b #$1,$198a7` and then spin until the VBL handler clears it. Two sites, one per path
 * through the loop, which is why the PC is a parameter (include/highscore.h). */
static int name_entry_wait_vblank(uint8_t *image, uint32_t site_pc) {
    image[A_vbl_wait_flag] = 1;
    return sched_wait8(image, A_vbl_wait_flag, 0, site_pc);
}

/* 0x131da — waiting for the key that produced this frame to be let go, and it forks on which
 * device produced it. A joystick pick clears the scancode itself and then waits for FIRE to come
 * up, asking the IKBD each time round; a typed key is waited out on the scancode byte alone, which
 * the ACIA handler zeroes on the release code. */
static int name_entry_wait_for_release(uint8_t *image) {
    if (image[A_name_entry_from_joystick] != 0) {
        image[A_key_scancode] = 0;
        return joystick_wait_for_fire(image, NAME_ENTRY_FIRE_RELEASE_WAIT_PC, 0);
    }
    return sched_wait8(image, A_key_scancode, 0, NAME_ENTRY_KEY_RELEASE_WAIT_PC);
}

/* 0x13058, the drawing half of one edit frame: the gunsight cursor into entity record 0, the
 * compose page onto the playfield, the cursor on top of it, and then one joystick interrogation.
 *
 * THE ORDER IS LOAD-BEARING: the page is blitted BEFORE the sprite, so the gunsight sits over the
 * keyboard rather than under the next frame's copy of them. The five record fields are written in
 * the original's order too, though only the bytes matter to the diff. */
static void name_entry_draw_frame(uint8_t *image) {
    const uint32_t gunsight = A_entity_table;   /* record 0 — the front end has no live entities */

    wr16(image + addr_add(gunsight, ENTITY_X), be16(image + A_osk_cursor_x));
    wr16(image + addr_add(gunsight, ENTITY_Y), be16(image + A_osk_cursor_y));
    wr16(image + addr_add(gunsight, ENTITY_HEIGHT), GUNSIGHT_ROWS);
    image[addr_add(gunsight, ENTITY_ALIVE)] = 1;
    wr32(image + addr_add(gunsight, ENTITY_SPRITE), A_gunsight_sprite);
    blit_page0_to_playfield(image);
    ZY_SPRITE(draw_sprite_masked_collide)(image, gunsight, A_name_entry_cursor_hit);
    ikbd_send_cmd(IKBD_CMD_JOYSTICK_INTERROGATE);
}

/* 0x130a4 — the four direction bits move the cursor two pixels each, and FIRE turns where it is
 * into a scancode.
 *
 * THE FOUR DIRECTIONS ARE NOT EXCLUSIVE: the original tests each bit in turn and applies each one
 * it finds, so up-and-down together move the cursor down and then back. One read of the byte
 * serves all five tests here where the original makes five — nothing off target can change it in
 * between, and the scheduled-write model lands its stores only at a declared poll.
 *
 * The hit test takes the caller's D0 as scratch and gives it back on a hit (include/input.h), but
 * only the LOW BYTE is stored, and a miss clears the register outright — so what D0 held on the way
 * in cannot reach memory, and 0 is passed rather than threading the original's carried-over value. */
static void name_entry_apply_joystick(uint8_t *image) {
    uint8_t stick = image[A_joystick_state];

    if (stick & JOYSTICK_UP)
        wr16(image + A_osk_cursor_y, (uint16_t)(be16(image + A_osk_cursor_y) - OSK_CURSOR_STEP));
    if (stick & JOYSTICK_DOWN)
        wr16(image + A_osk_cursor_y, (uint16_t)(be16(image + A_osk_cursor_y) + OSK_CURSOR_STEP));
    if (stick & JOYSTICK_LEFT)
        wr16(image + A_osk_cursor_x, (uint16_t)(be16(image + A_osk_cursor_x) - OSK_CURSOR_STEP));
    if (stick & JOYSTICK_RIGHT)
        wr16(image + A_osk_cursor_x, (uint16_t)(be16(image + A_osk_cursor_x) + OSK_CURSOR_STEP));

    image[A_name_entry_from_joystick] = SCC_BYTE_FALSE;
    if (stick & JOYSTICK_FIRE) {
        image[A_name_entry_from_joystick] = SCC_BYTE_TRUE;
        image[A_key_scancode] = (uint8_t)onscreen_keyboard_hit_test(image, 0);
    }
}

/* The FRAME block as a whole: draw and read the stick until a scancode is there to dispatch.
 *
 * The scancode byte is the loop's clock — it is what the ACIA handler stores and what 0x13104 comes
 * back to — so it is read through `sched_poll8` at that PC and nowhere else. A frame with no key
 * shows the page and waits for the next one, which is the second of the routine's two VBL waits. */
static int name_entry_wait_for_key(uint8_t *image, uint8_t *key) {
    for (unsigned frame = 0; frame < OS_SCHED_POLL_MAX; frame++) {
        name_entry_draw_frame(image);
        name_entry_apply_joystick(image);
        *key = sched_poll8(image, A_key_scancode, NAME_ENTRY_KEY_WAIT_PC);
        if (*key != 0)
            return 1;
        screen_flip_buffers(image);
        if (!name_entry_wait_vblank(image, NAME_ENTRY_IDLE_VBL_WAIT_PC))
            return 0;
    }
    return (int)os_refused(0);
}

/* The character a scancode types, or a byte with bit 7 set for "not a printable key".
 *
 * `ext.w d0` before `move.b (0,a0,d0.w),d1` SIGN-extends the scancode, so 0x80 and above index
 * BEFORE the table — into the message text below it, where most bytes are letters and a few are
 * not. That is reachable: the `bgt` above admits every negative byte, because it is a SIGNED
 * compare against 0x72. Faithful, in-image, and driven by the fuzz. */
static uint8_t scancode_character(const uint8_t *image, uint8_t scancode) {
    return image[addr_add(A_scancode_to_char_table, sign_ext8(scancode))];
}

/* 0x13124 — what one scancode does. The six named keys first, then the table. */
static enum name_entry_step name_entry_apply_key(uint8_t *image, uint8_t key, uint16_t *cursor) {
    uint8_t character;

    if (key == SCANCODE_ESC || key == SCANCODE_UNDO) {
        *cursor = NAME_ENTRY_FIRST_CHAR;
        name_entry_blank(image);
        return NAME_ENTRY_STEP_REDRAW;
    }
    if (key == SCANCODE_BACKSPACE || key == SCANCODE_DELETE) {
        /* `cmp.w #$2,d4` + `beq` — an empty name erases nothing, and the erase is a CLEAR CELL
         * character in the record rather than a shortening of it: the record is always fifteen
         * characters long and the cursor says how much of it is real. */
        if (*cursor != NAME_ENTRY_FIRST_CHAR) {
            (*cursor)--;
            image[name_entry_character(*cursor)] = CHAR_CLEAR_CELL;
        }
        return NAME_ENTRY_STEP_REDRAW;
    }
    if (key == SCANCODE_RETURN || key == SCANCODE_ENTER)
        return NAME_ENTRY_STEP_COMMIT;
    if ((int8_t)key > (int8_t)NAME_ENTRY_SCANCODE_MAX)
        return NAME_ENTRY_STEP_KEEP;

    character = scancode_character(image, key);
    if ((int8_t)character < 0 || *cursor == NAME_ENTRY_LAST_CHAR)
        return NAME_ENTRY_STEP_KEEP;

    image[name_entry_character(*cursor)] = character;
    /* Erase the block cursor's own cell before the redraw paints the letter into it: `draw_char`
     * ORs its planes through the glyph's mask, so a letter drawn over a filled cell would keep the
     * fill. The redraw that follows puts the cursor back one column along. */
    ZY_TEXT(draw_char)(image, addr_add(A_backdrop_page0, NAME_ENTRY_ROW_OFFSET),
                       (uint16_t)(*cursor + NAME_ENTRY_CURSOR_COLUMN_BIAS), CHAR_CLEAR_CELL);
    (*cursor)++;
    return NAME_ENTRY_STEP_REDRAW;
}

/* 0x1324a — the fifteen characters and the terminator into the slot, then the release wait.
 *
 * `lea 6(a4),a4` is HIGHSCORE_NAME_OFFSET, so the slot's own column and row bytes survive the
 * commit exactly as they survive the shift-down that made room for it. */
static int name_entry_commit(uint8_t *image, uint32_t slot) {
    copy_longwords(image, addr_add(A_name_entry_record, NAME_ENTRY_FIRST_CHAR),
                   addr_add(slot, HIGHSCORE_NAME_OFFSET), NAME_ENTRY_NAME_LONGS);
    return joystick_wait_for_fire(image, NAME_ENTRY_COMMIT_WAIT_PC, 0);
}

int name_entry_edit_step(uint8_t *image, uint16_t *cursor, enum name_entry_step *step) {
    uint8_t key;

    if (!name_entry_wait_for_key(image, &key))
        return 0;
    *step = name_entry_apply_key(image, key, cursor);
    return 1;
}

void highscore_enter_name(uint8_t *image, uint32_t slot) {
    uint16_t cursor = NAME_ENTRY_FIRST_CHAR;
    int redraw = 1;

    draw_text_record(image, A_backdrop_page0, A_text_please_enter_name, NULL);
    wr32(image + slot, be32(image + A_player_score_bcd));
    name_entry_blank(image);
    draw_text_record(image, A_backdrop_page0, A_text_osk_row1, NULL);
    draw_text_record(image, A_backdrop_page0, A_text_osk_row2, NULL);
    draw_text_record(image, A_backdrop_page0, A_text_osk_row3, NULL);
    wr16(image + A_osk_cursor_x, OSK_HOME_X);
    wr16(image + A_osk_cursor_y, OSK_HOME_Y);

    for (;;) {
        enum name_entry_step step;

        if (redraw)
            name_entry_redraw(image, cursor);
        screen_flip_buffers(image);
        if (!name_entry_wait_vblank(image, NAME_ENTRY_VBL_WAIT_PC))
            return;
        if (!name_entry_wait_for_release(image))
            return;

        if (!name_entry_edit_step(image, &cursor, &step))
            return;
        if (step == NAME_ENTRY_STEP_COMMIT) {
            (void)name_entry_commit(image, slot);
            return;
        }
        redraw = step == NAME_ENTRY_STEP_REDRAW;
    }
}

/* ================================================================================================
 * highscore_check_and_insert @ 0x12eae, and game_over_screen @ 0x12e66
 * ============================================================================================= */

/* 0x12f5a — YOU ARE NOT RATED, and press fire to carry on.
 *
 * IT DRAWS INTO `screen_back`, not into the compose page the rated arm uses: the message lands on
 * top of the GAME OVER the prologue left there and the flip below is what shows it.
 *
 * The joystick byte is cleared first, so the wait for a PRESS cannot be satisfied by a fire that
 * was already down when the screen appeared. */
static void highscore_not_rated_screen(uint8_t *image) {
    draw_text_record(image, be32(image + A_screen_back), A_msg_you_are_not_rated, NULL);
    screen_flip_buffers(image);
    sound_start(image, SFX_YOU_ARE_NOT_RATED, install_frontend_palette(image));
    image[A_joystick_state] = 0;
    if (!joystick_wait_for_fire(image, NOT_RATED_FIRE_PRESS_WAIT_PC, 1))
        return;
    (void)joystick_wait_for_fire(image, NOT_RATED_FIRE_RELEASE_WAIT_PC, 0);
}

unsigned highscore_check_and_insert(uint8_t *image) {
    unsigned rank;

    clear_backdrop_page0(image);
    rank = highscore_rank_and_shift(image);
    if (rank == HIGHSCORE_ENTRIES) {
        highscore_not_rated_screen(image);
        return HIGHSCORE_NOT_RATED;
    }

    draw_text_record(image, A_backdrop_page0, A_msg_new_high_score, NULL);
    screen_flip_buffers(image);
    sound_start(image, SFX_NEW_HIGH_SCORE, install_frontend_palette(image));
    highscore_enter_name(image, highscore_entry(rank));
    sound_reset_psg(image);
    return HIGHSCORE_RATED;
}

void game_over_screen(uint8_t *image) {
    game_over_screen_prologue(image);
    /* Nothing follows the call. The `bne` at 0x12e98 and the palette restore behind it are dead on
     * both arms — include/highscore.h's prototype has the stack argument for why. */
    (void)highscore_check_and_insert(image);
}

/* Register map: none in; everything is clobbered. */
void g_role_of_honour_screen(uint8_t *image) {
    role_of_honour_screen(image);
}

/* Register map: none in. A0 carries the draw buffer and D1 the column the record left behind. */
void g_game_over_screen_prologue(uint8_t *image) {
    game_over_screen_prologue(image);
}

/* Register map: none in; the answer is D6, and the glue returns it so a case can compare the rank
 * as well as the shifted bytes. */
uint32_t g_highscore_rank_and_shift(uint8_t *image) {
    return highscore_rank_and_shift(image);
}

/* Register map: none in; everything is clobbered. D0 comes back as HIGHSCORE_RATED /
 * HIGHSCORE_NOT_RATED, which the glue returns so a case can compare the answer as well as the
 * bytes — the arm the run took is otherwise only inferable from the screen. */
uint32_t g_highscore_check_and_insert(uint8_t *image) {
    return highscore_check_and_insert(image);
}

/* Register map: A0 = the table slot the ranking freed; nothing comes back. */
void g_highscore_enter_name(uint8_t *image, uint32_t slot) {
    highscore_enter_name(image, slot);
}

/* Register map: D4 = the cursor; A5 is the name record, a constant of the routine rather than an
 * argument. Nothing comes back — the block draws into the compose page and the diff sees it. */
void g_name_entry_redraw(uint8_t *image, uint32_t cursor) {
    name_entry_redraw(image, (uint16_t)cursor);
}

/* Register map: D4 in and out is the cursor, and A5 is the name record — a constant of this
 * reconstruction, so the glue takes only D4. The answer packs the BLOCK the step chose above the
 * cursor, because the ORIGINAL states that as the address it lands on and a case can then compare
 * the arm as well as the bytes: the two halves are the two things this step decides. */
uint32_t g_name_entry_edit_step(uint8_t *image, uint32_t cursor) {
    uint16_t moved = (uint16_t)cursor;
    enum name_entry_step step = NAME_ENTRY_STEP_KEEP;

    /* A refused wait has already tallied and the harness throws the case away before it reads this,
     * so the step it comes back with is whatever the initialiser above says. */
    (void)name_entry_edit_step(image, &moved, &step);
    return ((uint32_t)step << NAME_ENTRY_STEP_SHIFT) | (moved & NAME_ENTRY_STEP_CURSOR_MASK);
}

/* Register map: none in; everything is clobbered, and D0's answer belongs to the routine this one
 * calls rather than to this one — the branch that would have read it is dead (include/highscore.h). */
void g_game_over_screen(uint8_t *image) {
    game_over_screen(image);
}
