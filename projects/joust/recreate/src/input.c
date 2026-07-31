/* input.c — Joust's input layer: the console poll that pauses, restarts or quits the game, the
 * end-of-game high-score check, and the two readers that drive the name entry it puts up.
 *
 * All of it is trap-bound, and the kit's TOS model
 * (tools/recreate_kit/TRAP_MODEL.md) decides how much of each can be verified at all:
 *
 *   * BIOS Bconstat/Bconin are harness-poked console state, and a run delivers AT MOST ONE
 *     keystroke — Bconin consumes it, and there is no second key to stage. So every branch is
 *     covered by its own fixed-input run, and a loop that waits for a SECOND key (poll_quit_key's
 *     pause) can only be verified entered at its own head.
 *   * The two never-returning exits — GEMDOS Pterm and the jump back into _start — have no `rts`
 *     to diff at, so they are verified at a checkpoint PC (harness `stop_pc`) and report themselves
 *     through the INPUT_* result instead of through control flow.
 *   * A REFUSED os_* CALL ONCE REJECTED ONLY THE ORACLE'S RUN — a general asymmetry of the kit,
 *     not one gate's quirk, and now closed. Every helper whose unmodeled answer the candidate
 *     simply discards behaved this way: the oracle's refusal set g_unmodeled and the case was
 *     thrown away, while the candidate made the same call, got the same nothing, and carried on
 *     with nothing tallying it — SO DELETING A GUARD THE ORIGINAL HAS WAS INVISIBLE TO THE
 *     DIFFERENTIAL. Both measured instances are in this file: deleting poll_console_key's Bconstat
 *     gate left the whole suite green, and save_hiscore's Fopen is the same shape without a gate to
 *     delete — os_fopen on an unstaged name returns -1 to the candidate, which then walks the
 *     Fcreate fallback, while the same call rejects the oracle's run, which is precisely why that
 *     fallback has no case at all. The kit now tallies the candidate's own refusals (os_refused in
 *     include/os.h, tools/recreate_kit/src/os_refusal.c) and harness.differential() raises on a
 *     non-zero count. Deleting the Bconstat gate now fails two named cases; the Fopen shape is
 *     caught by the same tally but NO case here reaches it, since every quit case stages HIGH.SCO
 *     and the unstaged case is oracle-only — the tally closes the class wherever a case reaches the
 *     call, it does not invent the case. And it proves a guard is REACHED, not that it is the right
 *     guard, so a Bconstat/Fopen/Super gate in init_system or title_screen is still transcribed
 *     from the original and reasoned about.
 *   * THE IKBD WAIT ITSELF CANNOT BE VERIFIED. The interrogate goes out with XBIOS Ikbdws, which
 *     the model swallows (no image effect), and the reply lands in ikbd_packet on an interrupt the
 *     oracle never runs — and the prologue CLEARS ikbd_packet, so a harness-poked reply cannot
 *     survive to end the spin either. What IS recoverable is everything past the wait, by entering
 *     the oracle AT the wait loop with a packet already staged: that is how hiscore_joystick_input
 *     is verified below, and how read_joysticks (0x11d9a, src/player.c) and title_screen's joystick
 *     start (0x10bb8, src/init.c) are. The prologue the three share is request_ikbd_packet /
 *     wait_for_ikbd_packet, at the head of this file.
 */
#include "machine.h"
#include "os.h"

#include "input.h"
#include "sound.h"   /* g_dosound: the kit's XBIOS Dosound side-effect ledger */

/* =================================================================================================
 * The IKBD joystick interrogate — the six instructions three routines of the ORIGINAL share.
 *
 * read_joysticks (0x11d9a), hiscore_joystick_input (0x14538) and title_screen's attract pass
 * (0x10ba2) each spell the same `clr.l` / Ikbdws / `tst.l` spin, byte for byte. TWO of the three
 * reconstructions call the pair below — read_joysticks (src/player.c) and title_screen
 * (src/init.c) — so a change to either half reaches both, and both batteries score it.
 *
 * THE THIRD DOES NOT, and that is not an oversight: hiscore_joystick_input is reconstructed from
 * PAST its wait (see its own section), so it has no prologue to share. Its caller, the high-score
 * entry loop, is the one that owes the interrogate on target.
 * ============================================================================================= */

void request_ikbd_packet(uint8_t *image) {
    /* The slot the IKBD's interrupt handler stores into, emptied so last frame's reply cannot be
     * read as this frame's. XBIOS Ikbdws(0, A_ikbd_cmd_joyread) follows and has no image effect
     * (see include/input.h for what an on-target build still owes). */
    wr32(image + A_ikbd_packet, 0);
}

/* `volatile` is what stops the compiler assuming this loop terminates and deleting it: the reply is
 * stored by an interrupt handler, which is exactly what volatile is for. Read as four BYTES rather
 * than through a wider type — the image is a byte array, ikbd_packet is not longword-aligned, and a
 * `tst.l` against zero does not care in which order the bytes are OR-ed. */
void wait_for_ikbd_packet(const uint8_t *image) {
    const volatile uint8_t *packet = image + A_ikbd_packet;
    while ((packet[0] | packet[1] | packet[2] | packet[3]) == 0)
        ;
}

/* The one guard both wait-entering glues share; include/input.h carries the two reasons for it. */
int ikbd_packet_readable(const uint8_t *image) {
    uint32_t packet = be32(image + A_ikbd_packet);
    return packet != 0 && packet <= OS_IMAGE_SIZE - IKBD_PACKET_BYTES;
}

/* =================================================================================================
 * poll_quit_key @ 0x11c24
 * ============================================================================================= */

/* The keys it acts on. Bconin's result is compared with `cmp.b`, so the upper/lower pairs are two
 * separate tests rather than a case fold. KEY_CTRL_C is input.h's — title_screen tests it too. */
#define KEY_PAUSE_UPPER   0x50u   /* 'P' */
#define KEY_PAUSE_LOWER   0x70u   /* 'p' */
#define KEY_RESTART_UPPER 0x52u   /* 'R' */
#define KEY_RESTART_LOWER 0x72u   /* 'r' */

/* TOS state the quit path hands back. */
#define TOS_CONTERM       0x484u  /* TOS system variable: key-click / bell / key-repeat flags */
#define KBDV_MOUSEVEC     0x10u   /* KBDVBASE (os.h OS_KBDVBASE): the IKBD mouse-packet vector... */
#define KBDV_JOYVEC       0x18u   /* ...and the joystick-packet vector */

#define HISCORE_RECORD_BYTES 0x1au  /* what Fwrite pushes out of hiscore_name */
#define HIGHSCO_OPEN_MODE    2u     /* GEMDOS Fopen mode 2 = read/write */

/* Write the pending high score back to HIGH.SCO, creating the file if it isn't there.
 *
 * The handle goes through memory as a WORD (draw_x, borrowed while nothing is being drawn) and both
 * tests of it are signed WORD tests, so a GEMDOS error code reads as negative there. It is re-read
 * from that word for every use — the original really does spell `move.w $dec.l,-(a7)` afresh for
 * Fwrite and again for Fclose — so a local cached across the calls would not be the same routine.
 *
 * THE Fcreate FALLBACK IS UNREACHABLE UNDER THE ORACLE, and reproduced unverified: the model's
 * os_fcreate is os_fopen plus a truncation, so both succeed for a staged name and both fail for an
 * unstaged one — there is no input for which Fopen fails and Fcreate then succeeds. The two `< 0`
 * tests are equally unreachable for the same reason (an Fopen the model refuses raises the run
 * rather than returning -1). See the report in ../STATUS.md.
 *
 * HIGHSCO_OPEN_MODE has no reader here because the model ignores Fopen's mode — it is named so
 * test_input.py can pin it against the word the ORIGINAL pushed for its trap, the same way score.c
 * names the Setcolor pen it cannot otherwise observe. (Fcreate's attribute word has no such pin:
 * its call is on the unreachable branch above, so there is no run in which it is pushed.)
 */
static void save_hiscore(uint8_t *image) {
    if (image[A_hiscore_dirty] == 0) return;

    wr16(image + A_quit_file_handle, (uint16_t)os_fopen(image, A_fname_highsco));
    if ((int16_t)be16(image + A_quit_file_handle) < 0) {
        wr16(image + A_quit_file_handle, (uint16_t)os_fcreate(image, A_fname_highsco));
        if ((int16_t)be16(image + A_quit_file_handle) < 0) return;
    }
    os_fwrite(image, be16(image + A_quit_file_handle), HISCORE_RECORD_BYTES, A_hiscore_name);
    os_fclose(image, be16(image + A_quit_file_handle));
}

/* Hand the machine back to TOS, in the original's order.
 *
 * Only three bytes of it are memory effects — the conterm byte and the two KBDVBASE vectors. XBIOS
 * Setscreen, the two Ikbdws command strings, GEMDOS Super(0) — whose returned stack pointer is
 * dropped on the spot — and XBIOS Setpalette all drive state TOS never reads back, so the model
 * gives them no image effect and the differential cannot see them. test_input.py reads each one's
 * arguments back out of the oracle's own stack instead, which is the only thing that can catch them.
 *
 * SO THIS IS NOT THE WHOLE HAND-BACK. An on-target .PRG built from this layer has to re-issue the
 * five omitted calls for real, or Ctrl-C returns to a desktop still in the game's palette and screen
 * mode with the IKBD still interrogating joysticks — a class of divergence the differential is blind
 * to by construction (see projects/buggyboy/recreate/HARNESS.md).
 */
static void restore_system(uint8_t *image) {
    image[TOS_CONTERM] = image[A_conterm_save];
    wr32(image + OS_KBDVBASE + KBDV_MOUSEVEC, be32(image + A_saved_mousevec));
    wr32(image + OS_KBDVBASE + KBDV_JOYVEC, be32(image + A_saved_joyvec));
}

/* The console-poll prologue both readers open with: Bconstat, and only if it says a character is
 * waiting, Bconin. Returns 1 and the ASCII byte when a key was read, 0 when there was none.
 *
 * Bconin returns scancode << 16 | ascii, and every test either reader makes on it is a `cmp.b`, so
 * only the ASCII byte is ever looked at — the scancode half is dead.
 *
 * THIS GATE IS THE MEASURED CASE of the module comment's refused-os_*-call asymmetry — which is now
 * closed, so deleting it fails test_poll_quit_key_no_key_returns_at_once and
 * test_hiscore_key_input_no_key_returns_at_once rather than passing silently. What the tally proves
 * is only that the gate is REACHED; that it is the RIGHT gate is still transcribed from the
 * original and reasoned about. On real hardware it is what stops Bconin from blocking. */
static int poll_console_key(uint8_t *image, uint8_t *key) {
    uint32_t pending = 0, console = 0;

    os_bconstat(image, OS_BIOS_DEV_CON, &pending);
    /* `cmp.l #$ffffffff`: the FULL longword. Not differentially observable — the model's Bconstat
     * answers only 0 or -1, so a narrower test would agree on every input a run can produce. Kept
     * as the original wrote it; real TOS drivers have been known to return other non-zero values. */
    if (pending != OS_BCONSTAT_READY) return 0;

    os_bconin(image, OS_BIOS_DEV_CON, &console);
    *key = (uint8_t)console;
    return 1;
}

/* Pause: hold here until the NEXT key arrives, and deliberately don't read it — so the key that
 * resumes play is still pending for the next poll.
 *
 * Reached only from poll_quit_key, and unverifiable from there: Bconin has just consumed the one
 * keystroke a run can stage, so inside poll_quit_key this loop never sees a second key and the
 * oracle spins to its instruction cap. It is verified on its own instead, with the oracle entered
 * at the loop's head (0x11d64) and a key staged — which covers exactly the pass that leaves it, and
 * proves the loop does NOT consume the key.
 *
 * THE CANDIDATE SPINS HERE TOO, with no instruction cap — faithfully, since the original has none
 * either. The oracle is capped and raises, but a candidate reached with no key pending would hang
 * its pytest worker with no output at all under `-n auto`, which is the worst failure mode a
 * differential has. TWO SEPARATE THINGS KEEP THAT FROM HAPPENING, neither of them this function:
 * g_pause_until_key refuses to enter the loop with nothing pending (see the glue below), and no
 * differential case reaches the loop through poll_quit_key at all, because test_input.py's key fuzz
 * excludes P/p by hand. The second is a test-side convention this file cannot enforce, so a case
 * that wants to stage P/p through g_poll_quit_key has to know why it currently must not.
 */
static void pause_until_key(const uint8_t *image) {
    uint32_t pending = 0;
    do {
        os_bconstat(image, OS_BIOS_DEV_CON, &pending);
    } while (pending != OS_BCONSTAT_READY);
}

/* poll_quit_key's quit tail @ 0x11c56, and THE ONE BLOCK IN THE GAME A SECOND ROUTINE BRANCHES
 * INTO: title_screen's Ctrl-C is a `beq.w` at 0x10bea straight to this address — past this
 * routine's own entry and its Bconstat/Bconin, so it is a shared tail and NOT a call to
 * poll_quit_key. Nothing here ever comes back to either caller: the original's next act after the
 * three effects below is GEMDOS Pterm. Each caller therefore reports the exit through its own
 * result code (INPUT_QUIT, TITLE_QUIT) and this function returns nothing at all. */
void quit_to_desktop(uint8_t *image) {
    g_dosound(image, A_snd_list_silence);
    save_hiscore(image);
    restore_system(image);
}

/* One poll of the console during play. Ctrl-C quits to the desktop, P/p pauses, R/r restarts, and
 * every other key — and no key at all — simply returns. */
uint32_t poll_quit_key(uint8_t *image) {
    uint8_t key;
    if (!poll_console_key(image, &key)) return INPUT_CONTINUE;

    if (key == KEY_CTRL_C) {
        quit_to_desktop(image);
        return INPUT_QUIT;                     /* the original traps Pterm here and never returns */
    }
    if (key == KEY_PAUSE_UPPER || key == KEY_PAUSE_LOWER) {
        pause_until_key(image);
        return INPUT_CONTINUE;
    }
    if (key == KEY_RESTART_UPPER || key == KEY_RESTART_LOWER)
        return INPUT_RESTART;                  /* ...and jumps to RESTART_ENTRY, likewise */
    return INPUT_CONTINUE;
}

/* =================================================================================================
 * The high-score name entry: hiscore_key_input @ 0x144d4.
 *
 * Both readers of the entry screen — this one and the joystick one below — share three tails in the
 * original, entered by a plain branch so their `rts` returns to the reader's own caller. They are
 * the three helpers here.
 * ============================================================================================= */

#define HISCORE_COLUMNS 0x10u   /* name positions; the cursor is clamped one short of this */

/* The result of one `subq #1` on a memory operand, as the 68000's condition codes see it.
 *
 * `bge`/`bgt`/`blt` after a subq test N == V, NOT the sign of the truncated result — and taking one
 * off the most negative value of the operand's size overflows, so 0x8000 - 1 = 0x7fff and
 * 0x80 - 1 = 0x7f both compare as NEGATIVE. Doing the subtraction at full precision on the SIGNED
 * operand reproduces exactly that: the caller stores the truncated value but branches on this one.
 * Neither caller's overflow case is reachable from the values the entry screen itself produces (the
 * cursor stays 0..15, the repeat counter 0/2/6), so this is fidelity rather than a live path — but
 * both are pinned by the differential over the full input domain, and getting it wrong silently
 * changes the branch. */
static int32_t subq_condition(int32_t signed_operand) {
    return signed_operand - 1;
}

/* The shared finish @ 0x14646. draw_rows doubles as "the entering player has typed something", so
 * RETURN (or fire) before any input at all is ignored rather than accepting a blank name. */
static uint32_t hiscore_finish(const uint8_t *image) {
    return be16(image + A_hiscore_touched) ? INPUT_RESTART : INPUT_CONTINUE;
}

/* The shared step-left @ 0x14614 (backspace, or the stick pushed left). The decrement is stored
 * BEFORE it is tested, and the test is `bge` — so column 0 writes 0xffff and then clamps it back to
 * 0, and only a cursor that stayed non-negative redraws. */
static uint32_t hiscore_cursor_left(uint8_t *image) {
    int32_t cursor = subq_condition((int16_t)be16(image + A_hiscore_cursor));
    wr16(image + A_hiscore_cursor, (uint16_t)cursor);
    if (cursor >= 0) draw_hiscore_cursor(image);
    else wr16(image + A_hiscore_cursor, 0);
    return INPUT_CONTINUE;
}

/* The shared step-right @ 0x1462c (a letter accepted, or the stick pushed right). Same shape as the
 * step-left, but the clamp is an UNSIGNED compare against the column count, so a cursor that wrapped
 * to 0 counts as in range and redraws. */
static uint32_t hiscore_cursor_right(uint8_t *image) {
    uint16_t cursor = (uint16_t)(be16(image + A_hiscore_cursor) + 1u);
    wr16(image + A_hiscore_cursor, cursor);
    if (cursor < HISCORE_COLUMNS) draw_hiscore_cursor(image);
    else wr16(image + A_hiscore_cursor, HISCORE_COLUMNS - 1u);
    return INPUT_CONTINUE;
}

/* Commit `letter` to the column under the cursor and move on. */
static uint32_t hiscore_accept_letter(uint8_t *image, uint8_t letter) {
    image[A_hiscore_letter] = letter;
    draw_hiscore_entry(image);
    return hiscore_cursor_right(image);
}

#define KEY_BACKSPACE 0x08u
#define KEY_RETURN    0x0du
#define KEY_SPACE     0x20u
#define KEY_LOWER_A   0x61u   /* the fold's threshold: an UNSIGNED `cmp.b`, so 0x61..0xff all fold */
#define KEY_UPPER_A   0x41u   /* ...and the accepted range's ends, both SIGNED `cmp.b` */
#define KEY_UPPER_Z   0x5au
#define KEY_CASE_FOLD 0x20u   /* what `sub.b` takes off a lower-case letter */

/* One poll of the keyboard while a name is being entered. */
uint32_t hiscore_key_input(uint8_t *image) {
    uint8_t key;
    if (!poll_console_key(image, &key)) return INPUT_CONTINUE;

    if (key == KEY_BACKSPACE) return hiscore_cursor_left(image);
    if (key == KEY_RETURN) return hiscore_finish(image);

    /* Space jumps straight to the store, past both range tests. Everything else is folded to upper
     * case first — an UNSIGNED threshold, so 0x61..0xff ALL lose 0x20, and the two range tests that
     * follow are SIGNED: a folded 0xe1 becomes 0xc1, which reads as negative and is rejected.
     *
     * Both signednesses are written as the original has them, but NEITHER is observable: every byte
     * from 0x80 up is rejected whether it is folded or not, and whether the window is tested signed
     * or unsigned, so the accepted set is 'A'-'Z', 'a'-'z' and space either way. Mutating either one
     * leaves the whole differential green — an equivalent mutant, not a coverage hole. */
    if (key != KEY_SPACE) {
        if (key >= KEY_LOWER_A) key -= KEY_CASE_FOLD;
        if ((int8_t)key < (int8_t)KEY_UPPER_A || (int8_t)key > (int8_t)KEY_UPPER_Z)
            return INPUT_CONTINUE;
    }
    return hiscore_accept_letter(image, key);
}

/* =================================================================================================
 * hiscore_joystick_input @ 0x14538 — reconstructed from its IKBD wait loop (0x1454e) onward.
 *
 * The three instructions before that loop clear ikbd_packet and hand XBIOS Ikbdws the "interrogate
 * joysticks" command; the reply then arrives on an interrupt the oracle never runs. So the spin can
 * only be left by staging the packet and entering the oracle AT the loop — which is what
 * test_input.py does, and which leaves exactly those three instructions and the "block until the
 * reply lands" behaviour unverified. Everything from the packet read on is proved byte for byte.
 * ============================================================================================= */

#define JOY_FIRE       0x80u   /* `btst #7` — on the whole longword, but only its low byte is set */
#define JOY_UP         0x01u
#define JOY_DOWN       0x02u
#define JOY_LEFT       0x04u
#define JOY_RIGHT      0x08u
#define JOY_DIRECTIONS 0x0fu   /* `and.b #$f` — the four direction bits, tested in this order */

#define REPEAT_DELAY_FIRST 6u  /* frames a held direction waits before it repeats... */
#define REPEAT_DELAY_NEXT  2u  /* ...and between repeats after that */

/* The alphabet the entry steps through is ' ' followed by 'A'..'Z', so each direction runs off the
 * end twice: once past the letters and once past the single space. */
#define LETTER_PAST_Z       0x5bu
#define LETTER_PAST_SPACE   0x21u
#define LETTER_BEFORE_A     0x40u
#define LETTER_BEFORE_SPACE 0x1fu

/* Step the letter under the cursor by `step` and redraw it. The second wrap test RE-READS the byte,
 * so it sees the substitution the first one may just have made — which is how stepping up off 'Z'
 * lands on ' ' and stepping up off ' ' lands on 'A'. */
static uint32_t hiscore_step_letter(uint8_t *image, uint8_t step,
                                    uint8_t off_alphabet, uint8_t off_space, uint8_t wrapped) {
    image[A_hiscore_letter] = (uint8_t)(image[A_hiscore_letter] + step);
    if (image[A_hiscore_letter] == off_alphabet) image[A_hiscore_letter] = KEY_SPACE;
    if (image[A_hiscore_letter] == off_space) image[A_hiscore_letter] = wrapped;
    draw_hiscore_entry(image);
    return INPUT_CONTINUE;
}

/* One poll of the joystick while a name is being entered. */
uint32_t hiscore_joystick_input(uint8_t *image) {
    uint32_t packet = be32(image + A_ikbd_packet);   /* what the wait loop spun for */

    /* The stick belonging to the player entering the name: player 2 reads joystick 0, anyone else
     * joystick 1 — a FULL 32-bit `cmpi.l` against player 2's slot. */
    uint8_t stick = image[packet + IKBD_JOYSTICK_0];
    if (be32(image + A_hiscore_stick) != A_player2) stick = image[packet + IKBD_JOYSTICK_1];

    if (stick & JOY_FIRE) return hiscore_finish(image);   /* fire before the flag below is set is
                                                           * ignored, so it cannot end an untouched
                                                           * entry on the frame it starts */
    wr16(image + A_hiscore_touched, 1);

    stick &= JOY_DIRECTIONS;
    if (stick == 0) {
        image[A_repeat_delay] = 0;        /* centred: the next push acts on the frame it arrives */
        return INPUT_CONTINUE;
    }

    /* Auto-repeat. The counter is decremented in memory and the branch reads the 68000's condition
     * codes, not the stored byte (see subq_condition): still positive means wait, exactly zero
     * means a repeat is due, and negative means this is the first frame of a new push. */
    int32_t delay = subq_condition((int8_t)image[A_repeat_delay]);
    image[A_repeat_delay] = (uint8_t)delay;
    if (delay > 0) return INPUT_CONTINUE;
    image[A_repeat_delay] = (uint8_t)(delay < 0 ? REPEAT_DELAY_FIRST : REPEAT_DELAY_NEXT);

    if (stick & JOY_UP)
        return hiscore_step_letter(image, 1, LETTER_PAST_Z, LETTER_PAST_SPACE, KEY_UPPER_A);
    if (stick & JOY_DOWN)
        return hiscore_step_letter(image, (uint8_t)-1, LETTER_BEFORE_A, LETTER_BEFORE_SPACE,
                                   KEY_UPPER_Z);
    if (stick & JOY_LEFT) return hiscore_cursor_left(image);
    if (stick & JOY_RIGHT) return hiscore_cursor_right(image);
    return INPUT_CONTINUE;
}

/* =================================================================================================
 * check_highscore @ 0x1437a — the end-of-game high-score check, and the name-entry screen it puts
 * up for the winner.
 *
 * Three exits. Not game over, or nobody beat the record: an ordinary `rts`. A new record: the
 * routine DROPS ITS CALLER'S RETURN ADDRESS (`addq.w #4,a7` at 0x143e0), puts the entry screen up
 * and falls into a loop with no exit instruction — 0x1448e..0x144af polls the keyboard, polls the
 * joystick, and steps the colour cycle, for ever. The only way out is one of the two readers
 * jumping to RESTART_ENTRY, which is why they have INPUT_* results at all.
 * ============================================================================================= */

#define HISCORE_SCORE_DIGITS  7u     /* `move.b #$7,d0`: what both comparisons MEANT to walk — and
                                      * what the copy at 0x1440a, whose counter survives, does walk */
#define HISCORE_DIRTY_SET     0x20u  /* what marks a record as needing writing back to HIGH.SCO */
#define HISCORE_ENTRY_COLOR   6u     /* text_color for the name being typed */
#define HISCORE_FLASH_PASSES  1u     /* colour-cycle steps per pass of the entry loop */

/* `move.w #$3e80,d0 / subq.w #1,d0 / bne` — 16,000 spins of pure register arithmetic and the only
 * thing pacing the entry screen's colour cycle. It touches no memory, so the differential cannot
 * see it AT ALL: not the count, not the loop, not even whether this is called. test_input.py pins
 * the ORIGINAL's encoding; nothing pins the C, and STATUS.md says so.
 *
 * Reproduced rather than dropped because an on-target build without it would run the cycle at the
 * CPU's speed. What it reproduces is the COUNT, not the cost: `volatile` is what stops the compiler
 * deleting an empty loop, and it also forces a load/store per pass, so on a real 68000 this spins
 * roughly 2.5x slower than the original's two instructions. An on-target build that wants the
 * original's pacing needs the register spin, not this. */
#define HISCORE_FLASH_DELAY_SPINS 0x3e80u

static void hiscore_flash_delay(void) {
    for (volatile uint16_t spins = HISCORE_FLASH_DELAY_SPINS; spins != 0u; spins--)
        ;
}

/* THE COUNTER-DESTRUCTION BUG, reproduced: this is a WALK, not a seven-byte compare.
 *
 * Both score comparisons open with `move.b #$7,d0` and then immediately overwrite that count with
 * the character they have just fetched (`move.b (a0)+,d0`), so `subq.b #1,d0 / bne` can only ever
 * end the loop on a character equal to 1. Two strings that agree therefore keep walking PAST both
 * records into whatever follows them. Measured on the real image: with player 1's and player 2's
 * seven digits equal, the walk runs 79 bytes, far enough that what decides the winner is player
 * 2's own score digits against enemy slot 2's.
 *
 * Both `cmp.b` operands are SIGNED. Returns +1 when `left` is the greater string, -1 when `right`
 * is, and 0 when a character of 1 stopped the walk — the two callers disagree about what that last
 * answer means, so it is theirs to read.
 *
 * A walk over two regions that never differ would run off the end of the image — as would one
 * started from a wild draw_src. Neither can reach here through the harness: every path into the
 * candidate runs the oracle first (harness.differential, and its poison re-run), and the oracle
 * spends an instruction per byte, so it exceeds max_insns and raises before the candidate is
 * called. A caller that skips that ordering does NOT get the guarantee: reaching the end of the
 * image here is undefined behaviour on the host, which during the mutation sweep showed up as a
 * crashed pytest worker rather than a failing case.
 */
static int walk_scores(const uint8_t *image, uint32_t left, uint32_t right) {
    for (;;) {
        int8_t character = (int8_t)image[left++];     /* d0.b := the character; the count is gone */
        int8_t against = (int8_t)image[right++];
        if (character > against) return 1;
        if (character < against) return -1;
        if (character == 1) return 0;    /* `subq.b #1,d0 / bne`: only a 1 leaves zero behind */
    }
}

/* Which player's score is the higher. A walk stopped by a character of 1 falls through into player
 * 1's store at 0x143a8, so player 1 takes the tie. */
static uint32_t higher_scoring_player(const uint8_t *image) {
    return walk_scores(image, A_object_table + OBJ_SCORE_FIRST_DIGIT,
                       A_player2 + OBJ_SCORE_FIRST_DIGIT) < 0 ? A_player2 : A_object_table;
}

/* ...and whether that score beats the record. Here the same stop falls through to the `rts` at
 * 0x143de instead — the opposite verdict, from the same bug. */
static int beats_the_high_score(const uint8_t *image, uint32_t player) {
    return walk_scores(image, player + OBJ_SCORE_FIRST_DIGIT, A_hiscore_score) > 0;
}

/* Silence the chip, take the new record, and put the name-entry screen up: 0x143e0..0x1448d.
 *
 * `player` is the entering player's object slot. The original re-reads draw_src for the banner
 * (`cmpi.l #$10f36,draw_src` at 0x1441e) rather than keeping it in a register — folded here, since
 * the only thing between the two reads is fill_screen, which writes the framebuffer.
 */
static void show_hiscore_entry_screen(uint8_t *image, uint32_t player) {
    g_dosound(image, A_snd_list_silence);
    image[A_hiscore_dirty] = HISCORE_DIRTY_SET;

    for (unsigned digit = 0; digit < HISCORE_SCORE_DIGITS; digit++)
        image[A_hiscore_score + digit] = image[player + OBJ_SCORE_FIRST_DIGIT + digit];

    fill_screen(image, 0);
    draw_string(image, player == A_object_table ? STR_HISCORE_P1 : STR_HISCORE_P2);

    for (unsigned column = 0; column < HISCORE_COLUMNS; column++)
        image[A_hiscore_name + column] = KEY_SPACE;

    image[A_text_flags] |= TEXT_FLAG_BACKGROUND;
    image[A_text_bg_color] = 0;
    image[A_text_color] = HISCORE_ENTRY_COLOR;
    image[A_repeat_delay] = 0;
    wr16(image + A_hiscore_touched, 0);
    /* One WORD store fills both halves of draw_dst_off: the letter under the cursor (' ') in the
     * high byte, and in the low one the NUL that terminates the single-character string
     * draw_hiscore_entry hands to draw_string. */
    wr16(image + A_hiscore_letter, (uint16_t)(KEY_SPACE << 8));
    wr16(image + A_hiscore_cursor, 0);
    draw_hiscore_cursor(image);
}

/* 0x1437a..0x1448d: everything before the entry loop. Non-zero once the screen is up, i.e. once the
 * original has fallen into a loop it never leaves. */
static int start_hiscore_entry(uint8_t *image) {
    if (image[A_game_over_flag] == 0) return 0;

    /* draw_src carries the leader on to the name entry, which reads it to pick the joystick. The
     * original re-reads it from memory for each of the three uses below (0x143be, 0x143fa,
     * 0x1441e); folded, because nothing between those reads writes draw_src itself — the entry
     * screen touches its NEIGHBOURS draw_shift/draw_rows/draw_dst_off, never it. */
    uint32_t leader = higher_scoring_player(image);
    wr32(image + A_hiscore_stick, leader);
    if (!beats_the_high_score(image, leader)) return 0;

    show_hiscore_entry_screen(image, leader);
    return 1;
}

/* One colour-cycle step of the entry loop @ 0x14494..0x144ad. The pass count lives in a byte of the
 * sprite-draw scratch rather than a register, and is reloaded with 1 every time round the loop
 * above it, so the `subq.b`/`bne` around the delay and the flash always runs exactly once. */
static void hiscore_flash_pass(uint8_t *image) {
    image[A_hiscore_flash_passes] = HISCORE_FLASH_PASSES;
    do {
        hiscore_flash_delay();
        flash_hiscore_color(image);
    } while (--image[A_hiscore_flash_passes] != 0u);
}

/* THE JOYSTICK POLL BELOW IS SHORT OF ITS PROLOGUE. The original's `bsr` at 0x14490 enters
 * hiscore_joystick_input at 0x14538, which clears ikbd_packet and sends the IKBD its interrogate
 * before waiting for the reply; the reconstruction starts at the WAIT LOOP (0x1454e) because no
 * oracle run can get through that wait (see the section above and include/input.h). So this loop
 * asks for no fresh packet, and an on-target build has to issue the interrogate itself before it
 * can be used — until then the entry screen would act on whatever byte ikbd_packet last held.
 * Under the harness it costs nothing: no run reaches a second pass. */
uint32_t check_highscore(uint8_t *image) {
    if (!start_hiscore_entry(image)) return CHECK_HIGHSCORE_RETURNED;

    /* 0x1448e..0x144af. The original's loop has no exit: both readers END the entry by dropping
     * this frame's return address and jumping to RESTART_ENTRY, which the C reports as a result. */
    for (;;) {
        if (hiscore_key_input(image) == INPUT_RESTART) return CHECK_HIGHSCORE_RESTART;
        if (hiscore_joystick_input(image) == INPUT_RESTART) return CHECK_HIGHSCORE_RESTART;
        hiscore_flash_pass(image);
    }
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Nothing in this layer takes a stack frame — each routine works entirely off globals and the
 * modeled console state — so each g_* is a bare forwarder, bar the three noted below. The one thing
 * an image diff cannot see is WHICH exit a routine took, since several of them never return and
 * none of them differs in memory: that comes back as the INPUT_* / CHECK_HIGHSCORE_* result, and
 * the test pins it against the checkpoint the oracle had to stop at.
 */

uint32_t g_poll_quit_key(uint8_t *image) {
    return poll_quit_key(image);
}

/* The one glue here that is NOT a bare forwarder: it refuses a call that would never come back.
 *
 * pause_until_key's spin is uncapped, so entering it with no key pending hangs the caller for ever
 * — silently, since an xdist worker prints nothing while it spins. Nothing enforces the ordering
 * that makes that unreachable today (harness.differential happens to run the capped oracle first,
 * and its raise is what a test with no key staged actually sees), and this file has no way to make
 * the kit enforce it. So the glue probes the console once and turns the hang into an ordinary
 * result the caller can assert on. A staged key takes the real path, unchanged and uncapped, so
 * the loop itself is verified exactly as before.
 *
 * This closes the DIRECT route into the spin only. poll_quit_key's own call to pause_until_key is
 * behind no such probe — see that function's comment for what keeps the candidate out of it. */
#define PAUSE_LEFT_ON_KEY 0u   /* the loop was entered and a key ended it */
#define PAUSE_NO_KEY      1u   /* nothing was pending: refused, so the loop was NOT entered */

uint32_t g_pause_until_key(const uint8_t *image) {
    uint32_t pending = 0;
    os_bconstat(image, OS_BIOS_DEV_CON, &pending);
    if (pending != OS_BCONSTAT_READY) return PAUSE_NO_KEY;

    pause_until_key(image);
    return PAUSE_LEFT_ON_KEY;
}

uint32_t g_hiscore_key_input(uint8_t *image) {
    return hiscore_key_input(image);
}

uint32_t g_hiscore_joystick_input(uint8_t *image) {
    return hiscore_joystick_input(image);
}

/* THE SECOND GLUE THAT IS NOT A BARE FORWARDER: it stops where every oracle run must stop.
 *
 * check_highscore's entry loop cannot be left by any input a run can stage. The oracle blocks
 * inside the joystick reader's IKBD wait on its FIRST pass, and the candidate is no better off:
 * the entry screen clears hiscore_touched, so RETURN and fire are both ignored on the pass that
 * follows, and the console delivers only one key while the IKBD packet never changes. So there is
 * no image in which either core leaves the loop, and a forwarder would hang the pytest worker with
 * no output at all under `-n auto`.
 *
 * It therefore runs 0x1437a..0x1448d and reports whether the screen went up, which is exactly the
 * state the oracle has at its 0x1448e checkpoint. The loop itself is verified on its own, one pass
 * at a time, through g_hiscore_entry_pass below; check_highscore stays uncapped and faithful
 * precisely because the refusal lives here. */
uint32_t g_check_highscore(uint8_t *image) {
    return start_hiscore_entry(image) ? CHECK_HIGHSCORE_ENTERED : CHECK_HIGHSCORE_RETURNED;
}

/* One pass of the entry loop, entered where the ORACLE can enter it: at the colour-cycle tail
 * (0x14494), round the branch at 0x144ae, and through the keyboard poll at 0x1448e. It stops before
 * the joystick reader at 0x14490 — the instruction past which no run comes back.
 *
 * THE ORDER OF THESE TWO STATEMENTS IS TRANSCRIBED FROM THE DISASSEMBLY, NOT HELD BY THE DIFF.
 * hiscore_flash_pass writes only draw_x/draw_y and the keyboard poll neither reads nor writes
 * either, so the two steps are independent and a final-image compare cannot tell them apart:
 * SWAPPING THEM LEAVES THE WHOLE SUITE GREEN (measured). What the diff does hold is that both are
 * PRESENT — dropping the flash diverges on A_hiscore_flash, dropping the poll on the letter it
 * types. The same is true of check_highscore's own loop, and worse: nothing executes it, so not
 * even presence is pinned there. ../STATUS.md lists both as surviving mutants. */
uint32_t g_hiscore_entry_pass(uint8_t *image) {
    hiscore_flash_pass(image);
    return hiscore_key_input(image);
}
