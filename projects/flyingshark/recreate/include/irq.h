/* irq.h — the two interrupts Flying Shark installs for itself: the level-4 vertical blank at $70
 * and the MFP channel-6 IKBD/MIDI ACIA at $118, plus the TOS joystick callback the second of them
 * takes the vector away from.
 *
 * PROVENANCE. Every address is a `fn` or `var` line in `../names.txt` at load base 0x10000, and the
 * instruction that establishes each figure is named beside it. `../notes/frontend.md` §4 has the
 * prose; `boot_init` @ 0x14bee is what installs both vectors (`include/init.h`).
 *
 * THE ENTRY MODEL. Both handlers are entered by the 68000's exception sequence and leave through
 * `rte`, so on the machine they run on an exception frame the routine itself never touches: every
 * one of them balances its own pushes before the `rte`, and the frame is consumed by that
 * instruction alone. The reconstruction is therefore SLICED AT THE `rte` — the frame is never read
 * on either side, so no case has to fabricate one — and each core is an ordinary C function that
 * returns where the original executes its `rte`. `test/test_irq.py` says which `rte` each case
 * stops at, because `acia_ikbd_isr` has four.
 *
 * THE FOUR INPUT BYTES ARE THIS SUBSYSTEM'S AND ARE DECLARED HERE. `joy0_state`, `joy1_state`,
 * `key_bits` and `key_last_scancode` are written by the ACIA handler and by nothing else, so by the
 * census in `../README.md` ("A global lives in the header of the subsystem that owns the DATA")
 * they belong here — `A_vbl_tick` below is the same argument at the VBL's counter. They were on
 * loan to `include/player.h` and `include/hud.h` while this subsystem was unported; the loan is
 * paid off and those two headers now include this one to READ them, which is the direction every
 * other borrowing in this project takes.
 */
#ifndef FS_IRQ_H
#define FS_IRQ_H

#include <stdint.h>

/* ---- the ACIA vector, and the three routines that pass it between them -------------------------
 *
 * `boot_init` installs TWO exception vectors and the pair is split between two headers, one name to
 * a home: this file owns the ACIA's, `include/init.h` owns the VBL's (`VECTOR_VBL`,
 * `FN_VBL_HANDLER`) because the installer is the one thing that names it. Neither can be restated
 * in the other — `test_constants.py::test_no_constant_is_defined_in_two_files` refuses a second
 * home — so a core that needs both includes both.
 *
 * They are 68000 EXCEPTION VECTORS in the low page, not game globals, so they are deliberately not
 * `A_*` names: `test_constants.py` requires every `A_*` to lie inside the program, and these lie
 * below it.
 */
#define VECTOR_ACIA 0x118u   /* `move.l a0,$118` @ 0x14cc8 — 68000 vector 70 = MFP channel 6 */

/* ...and the three routines that pass the vector between them while a joystick packet arrives.
 * `acia_ikbd_isr` re-points $118 at one of the two continuations on a packet HEADER byte, and each
 * continuation puts it back. The addresses are IMMEDIATE OPERANDS of `move.l #$n,$118` — the
 * handlers name each other, so a wrong one here is a chain that never comes back. */
#define FN_ACIA_IKBD_ISR  0x14218u /* `move.l #$14218,$118` @ 0x14322 and @ 0x14346 */
#define FN_ACIA_JOY0_BYTE 0x1430cu /* `move.l #$1430c,$118` @ 0x14226 */
#define FN_ACIA_JOY1_BYTE 0x14330u /* `move.l #$14330,$118` @ 0x14242 */

/* ---- the four input bytes the handlers write, and every other subsystem reads ------------------
 *
 * One byte each, in one run at 0x1777e..0x17781, and `acia_ikbd_isr` and its two continuations are
 * the only instructions in the program that store to any of them (`tos_joyvec_handler` is the
 * fourth writer and is dead on the machine). Everything else — `read_player_input`, the cheat arm
 * spin, the debug key wait, the two resets — is a READER, and reads them out of this header.
 */
#define A_joy0_state        0x1777eu /* `move.b d1,$1777e` @ 0x14310 — the second bomb button,
                                      * tested `btst #7,$1777e` @ 0x143c8 */
#define A_joy1_state        0x1777fu /* `move.b d1,$1777f` @ 0x14334 — the player's stick, tested
                                      * `btst #7,$1777f` @ 0x149f0 */
#define A_key_bits          0x17780u /* the eight watched keys, one bit each: `bset`/`bclr d0,(a1)`
                                      * @ 0x14274..0x142fa. Read `btst #0,$17780` @ 0x10d9a */
#define A_key_last_scancode 0x17781u /* `move.b d1,(a0)+` @ 0x14268 — the RAW byte, break bit and
                                      * all, kept whatever the ladder below does with it */

/* ---- the frame counter the VBL keeps ----------------------------------------------------------
 *
 * A LONGWORD, and the only thing in the program that moves it is `vbl_handler`'s `addq.l #1`. Every
 * reader is a WAITER: `render_frame` @ 0x14786 spins until it reaches its frame budget and then
 * clears it (`include/sprite.h`, which held this define on loan while this subsystem was unported).
 */
#define A_vbl_tick 0x17720u /* `addq.l #1,$17720` @ 0x1163a */

/* ---- the MFP's in-service register, and the bit every one of the four `rte` paths clears --------
 *
 * `bclr #6,$fffffa11` — the 24-bit bus form is what `hw_bclr8` takes (tools/recreate_kit/include/
 * hw.h). It is a READ-MODIFY-WRITE and not a store: the five other channels' in-service bits have
 * to survive it, which is what `hw_bclr8` exists to say.
 */
#define MFP_ISRB          0xfffa11u /* in-service register B */
#define MFP_ISRB_ACIA_BIT 6u        /* channel 6 = the IKBD/MIDI ACIA */

/* ---- the IKBD's packet protocol, as the ACIA handler decodes it -------------------------------
 *
 * The 6301 sends joystick reports as three bytes: a header naming the stick, then that stick's
 * state byte, then a second byte the game never waits for. `boot_init`'s `Bconout(4, $14)` is what
 * turns the reports on. Anything that is not one of the two headers is a KEY.
 */
#define IKBD_JOY0_PACKET_HEADER 0xfeu /* `cmpi.b #$fe,d1` @ 0x14220 */
#define IKBD_JOY1_PACKET_HEADER 0xffu /* `cmpi.b #$ff,d1` @ 0x1423c */

/* ---- the eight watched keys ------------------------------------------------------------------
 *
 * `key_bits` is an eight-bit keyboard state, one bit per entry of this table: the handler compares
 * the scancode against all eight in order and `bset`s or `bclr`s the bit of every one that matches.
 * The table is initialised DATA and nothing at run time writes it (`../names.txt`, 0x17782).
 */
#define A_key_watch_scancodes 0x17782u /* the `lea` @ 0x1425c loads 0x17781 and NOT this address:
                                        * `move.b d1,(a0)+` @ 0x14268 spends the first byte on
                                        * `A_key_last_scancode` and leaves a0 one on, at the table.
                                        * The eight `cmp.b (a0)+,d1` rungs start here */
#define KEY_WATCH_SCANCODES   8u       /* ...and there are exactly eight of those comparisons */
#define SCANCODE_BREAK_BIT    7u       /* `bclr #7,d1` @ 0x1426a: set on a key RELEASE */

/* ---- the cores -------------------------------------------------------------------------------
 *
 * None of them takes an argument the original does not: `tos_joyvec_handler` alone has one, TOS's
 * three-byte joystick packet in A0.
 */
void vbl_handler(uint8_t *image);
void acia_ikbd_isr(uint8_t *image);
void acia_joy0_byte(uint8_t *image);
void acia_joy1_byte(uint8_t *image);
void tos_joyvec_handler(uint8_t *image, uint32_t packet);

/* The offsets `tos_joyvec_handler` reads out of that packet. Byte 0 is the report's own header,
 * which the callback is handed and ignores. */
#define IKBD_JOY_PACKET_JOY0 1u /* `move.b 1(a0),$1777e` @ 0x14202 */
#define IKBD_JOY_PACKET_JOY1 2u /* `move.b 2(a0),$1777f` @ 0x1420a */

#endif /* FS_IRQ_H */
