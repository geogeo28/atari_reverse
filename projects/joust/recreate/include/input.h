/* input.h — the input layer: the console poll that quits or restarts the game, and the two
 * high-score name-entry readers.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name.
 *
 * Only what this layer alone touches is spelled out here. The name-entry display it drives
 * (draw_hiscore_cursor / draw_hiscore_entry) belongs to score.h, and the sprite-draw scratch the
 * entry screen borrows is spread over addrs.h (draw_shift, draw_rows, draw_src), draw.h
 * (draw_dst_off, player2) and object.h (draw_x) — this layer is a second reader of all four, so
 * each is INCLUDED rather than restated (a second copy would drift silently; see the pin in
 * test/test_constants.py). All four are included by name rather than left to score.h's own
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

#include "addrs.h"    /* A_draw_shift / A_draw_rows / A_draw_src, aliased below */
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
#define A_snd_list_silence  0x1150fu  /* the XBIOS Dosound list that silences the chip when quitting.
                                       * It is not one of sound_table's entries, so the input layer
                                       * names it; move it to sound.h if that layer needs it too. */
#define A_ikbd_packet       0x10e06u  /* .l — where the IKBD interrupt handler leaves the joystick
                                       * reply: a 2-byte packet, joystick 0 then joystick 1 */
#define A_ikbd_cmd_joyread  0x1145bu  /* 1 byte ($16), the IKBD "interrogate joysticks" command */
#define A_ikbd_cmd_mouse_rel 0x11d56u /* 1 byte ($14), the IKBD "relative mouse reporting" command.
                                       * It sits in the two dead bytes AFTER poll_quit_key's Pterm
                                       * trap, which is why a linear disassembly renders it as code */
#define A_fname_highsco     0x102c8u  /* "HIGH.SCO" — the high-score file */
#define A_hiscore_dirty     0x18388u  /* .b — a new high score is waiting to be written out */

/* THE QUIT PATH AND THE NAME ENTRY BORROW SPRITE-DRAW GLOBALS, the same way score.h's high-score
 * screen does: nothing is being drawn at either moment. Aliased rather than redefined so there is
 * still one address per name. */
#define A_quit_file_handle  A_draw_x     /* .w — HIGH.SCO's GEMDOS handle while it is being written */
#define A_hiscore_touched   A_draw_rows  /* .w — set once the entering player has moved the stick;
                                          * RETURN/fire before that is ignored */
#define A_hiscore_stick     A_draw_src   /* .l — which player object is entering the name, and so
                                          * which joystick of the IKBD packet to read */

/* --- input.c ----------------------------------------------------------------------------------- */
uint32_t poll_quit_key(uint8_t *image);
uint32_t hiscore_key_input(uint8_t *image);

/* Reconstructed from the IKBD WAIT LOOP (0x1454e) onward, so it reads whatever ikbd_packet already
 * holds instead of asking the IKBD for a fresh one. A caller that drives it per frame — which is
 * what check_highscore @ 0x1437a does — must issue the interrogate itself, or the entry screen acts
 * on a stale reply for ever. See the module comment above and in src/input.c. */
uint32_t hiscore_joystick_input(uint8_t *image);

#endif /* JOUST_INPUT_H */
