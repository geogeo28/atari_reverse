/* input.h — the input layer: the console poll that quits or restarts the game, the end-of-game
 * high-score check, and the two name-entry readers it drives.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name.
 *
 * Only what this layer alone touches is spelled out here. The name-entry display it drives
 * (draw_hiscore_cursor / draw_hiscore_entry) belongs to score.h, and the sprite-draw scratch the
 * entry screen borrows is spread over addrs.h (draw_shift, draw_rows, draw_src, draw_y), draw.h
 * (draw_dst_off, player2) and object.h (draw_x) — this layer is a second reader of all six, so
 * each is INCLUDED rather than restated (a second copy would drift silently; see the pin in
 * test/test_constants.py). All six are included by name rather than left to score.h's own
 * includes, so a tidy-up there cannot silently take an address out from under the aliases below.
 *
 * TWO ROUTINES OF THIS LAYER ARE NOT HERE, and cannot be: read_joysticks (0x11d9a) and the IKBD
 * prologue of hiscore_joystick_input (0x14538..0x1454d) send the IKBD an "interrogate joysticks"
 * command and then spin until an interrupt handler stores the reply in ikbd_packet. The oracle runs
 * no interrupts and XBIOS Ikbdws has no image effect, so that spin never ends — and the routine
 * CLEARS ikbd_packet on entry, so a harness-poked reply cannot survive it either. See the module
 * comment in src/input.c and tools/recreate_kit/TRAP_MODEL.md.
 */
#ifndef JOUST_INPUT_H
#define JOUST_INPUT_H

#include <stdint.h>

#include "addrs.h"    /* A_draw_shift / A_draw_rows / A_draw_src / A_draw_y, aliased below */
#include "draw.h"     /* A_draw_dst_off, A_player2 */
#include "object.h"   /* A_draw_x, aliased below */
#include "score.h"    /* the name-entry display this layer drives */

/* --- what a reader tells its caller to do next ------------------------------------------------
 * The original expresses these as control flow, not as a return value: it drops its caller's return
 * address with `addq.w #4,a7` and jumps to _start+6 to restart, or traps GEMDOS Pterm to quit.
 * Neither ever comes back, so neither has a post-state the differential could compare at an `rts`;
 * both are verified at a checkpoint PC instead (harness `stop_pc`), and the code below reports which
 * one it took so the test can pin the branch as well as the memory. */
#define INPUT_CONTINUE  0u   /* the routine returned normally */
#define INPUT_RESTART   1u   /* the original jumps to RESTART_ENTRY and never returns */
#define INPUT_QUIT      2u   /* the original traps GEMDOS Pterm and never returns */

#define RESTART_ENTRY   0x10006u  /* _start+6: where both never-returning restarts land */

/* The quit key, tested with `cmp.b` by BOTH layers that read the console: poll_quit_key during play
 * (0x11c4e) and title_screen on the title screen (0x10be6). Shared here rather than spelled twice
 * because the two tests must agree — they reach the same quit tail. */
#define KEY_CTRL_C      0x03u

/* --- globals -----------------------------------------------------------------------------------
 * Four of these have no reader in input.c because what they feed is an OFF-IMAGE trap argument the
 * differential cannot see (Setscreen's resolution, the two IKBD command strings, Setpalette's
 * table). They are named so test_input.py can pin them against the words the original pushed —
 * the same reason src/input.c names HIGHSCO_OPEN_MODE. */
#define A_saved_mousevec    0x10d18u  /* .l — KBDVBASE mousevec, saved before the game hooked it */
#define A_saved_joyvec      0x10d1cu  /* .l — ...and its joyvec */
#define A_saved_rez         0x10d20u  /* .w — the resolution XBIOS Setscreen is handed on the way out */
#define A_conterm_save      0x10d22u  /* .b — the TOS conterm byte as it was at startup */
#define A_ikbd_cmd_reset    0x10d24u  /* 2 bytes ($80 $01), the IKBD reset the game leaves behind */
#define A_saved_palette     0x10d26u  /* the 16-word palette XBIOS Setpalette is handed on the way out */
#define A_repeat_delay      0x1415eu  /* .b — frames until the joystick name-entry auto-repeat fires */
#define A_ikbd_packet       0x10e06u  /* .l — where the IKBD interrupt handler leaves the joystick
                                       * reply: a 2-byte packet, joystick 0 then joystick 1 */
#define A_ikbd_cmd_joyread  0x1145bu  /* 1 byte ($16), the IKBD "interrogate joysticks" command */
#define A_ikbd_cmd_mouse_rel 0x11d56u /* 1 byte ($14), the IKBD "relative mouse reporting" command.
                                       * It sits in the two dead bytes AFTER poll_quit_key's Pterm
                                       * trap, which is why a linear disassembly renders it as code */
#define A_fname_highsco     0x102c8u  /* "HIGH.SCO" — the high-score file */
#define A_hiscore_dirty     0x18388u  /* .b — a new high score is waiting to be written out */
#define A_hiscore_score     0x183a9u  /* the record holder's 7 ASCII score digits, the tail of the
                                       * same HISCORE_RECORD_BYTES block that starts at
                                       * A_hiscore_name (score.h) and that HIGH.SCO holds verbatim */

/* The two banners the entry screen opens with — "CONGRATULATIONS! / YOU HAVE HIGH SCORE PLAYER n",
 * one per player, picked by which object slot is entering the name. */
#define STR_HISCORE_P1      0x18301u
#define STR_HISCORE_P2      0x18341u

/* THE QUIT PATH AND THE NAME ENTRY BORROW SPRITE-DRAW GLOBALS, the same way score.h's high-score
 * screen does: nothing is being drawn at either moment. Aliased rather than redefined so there is
 * still one address per name. */
#define A_quit_file_handle  A_draw_x     /* .w — HIGH.SCO's GEMDOS handle while it is being written */
#define A_hiscore_touched   A_draw_rows  /* .w — set once the entering player has moved the stick;
                                          * RETURN/fire before that is ignored */
#define A_hiscore_stick     A_draw_src   /* .l — which player object is entering the name, and so
                                          * which joystick of the IKBD packet to read */
#define A_hiscore_flash_passes A_draw_y  /* .b — draw_y's HIGH half: how many colour-cycle steps
                                          * the entry loop still owes this pass */

/* --- check_highscore ---------------------------------------------------------------------------
 * Two of its three exits are an ordinary `rts`. The third is the name-entry loop, which has no exit
 * instruction at all: it is left only by one of the two readers jumping to RESTART_ENTRY. The glue
 * reports that the screen went up rather than entering a loop it could not leave — see src/input.c. */
#define CHECK_HIGHSCORE_RETURNED  0u  /* not a high score (or not game over): the original returns */
#define CHECK_HIGHSCORE_ENTERED   1u  /* the entry screen is up and the original is now in the loop */
#define CHECK_HIGHSCORE_RESTART   2u  /* a reader ended the entry and jumped to RESTART_ENTRY */

/* --- input.c ----------------------------------------------------------------------------------- */

/* poll_quit_key's quit tail @ 0x11c56 — silence the chip, write HIGH.SCO back and hand the machine
 * to TOS. Declared here because title_screen @ 0x10aae BRANCHES into it (`beq.w` at 0x10bea), which
 * makes it a shared tail rather than a private block. It never returns in the original (GEMDOS
 * Pterm follows), so its callers report the exit themselves. */
void quit_to_desktop(uint8_t *image);

uint32_t poll_quit_key(uint8_t *image);
uint32_t hiscore_key_input(uint8_t *image);

/* Reconstructed from the IKBD WAIT LOOP (0x1454e) onward, so it reads whatever ikbd_packet already
 * holds instead of asking the IKBD for a fresh one. A caller that drives it per frame — which is
 * what check_highscore @ 0x1437a does — must issue the interrogate itself, or the entry screen acts
 * on a stale reply for ever. See the module comment above and in src/input.c. */
uint32_t hiscore_joystick_input(uint8_t *image);

/* The whole of 0x1437a, entry loop included. NOTHING IN THE TEST SUITE CALLS IT: the loop cannot be
 * left (see src/input.c), so the glue stops where every oracle run must stop and the two halves are
 * verified through that. It is the shape _start and control_player `jsr` into, and is declared here
 * so an Atari build has it — but that build must ALSO issue the IKBD interrogate the entry loop's
 * joystick poll is missing (the paragraph above), or the screen acts on a stale packet for ever. */
uint32_t check_highscore(uint8_t *image);

#endif /* JOUST_INPUT_H */
