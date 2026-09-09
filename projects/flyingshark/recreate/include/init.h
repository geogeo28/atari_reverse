/* init.h — the boot chain, the file loader, the three palette wrappers, the per-game and per-stage
 * resets, and the frame loop `main` spends the rest of the program in.
 *
 * PROVENANCE. Every address is a `fn` or `var` line in `../names.txt` at load base 0x10000, and the
 * instruction that establishes each figure is named beside it. `../notes/frontend.md` §1-§3 has the
 * prose, and `../recreate/README.md`'s "The image model" is what the boot chain's own arithmetic
 * produces — `test/conftest.py` REPLAYS two of the routines declared here to build the image every
 * other battery runs on, so this header and that fixture describe one machine from two sides.
 *
 * WHAT THIS SUBSYSTEM OWNS: the loader's three scratch longwords, the disc probe's answer, the
 * three palettes, the vectors `boot_init` installs, and the per-game/per-stage state nothing else
 * writes. The scroller block (`A_scroll_pos`, `A_scroll_fine`, the map cursor) is
 * `include/scroll.h`'s and the level flow's counters are `include/player.h`'s and
 * `include/hud.h`'s; the resets here READ those headers rather than restating an address.
 *
 * WHAT THE MODEL CANNOT SUPPLY, named once. XBIOS `Physbase` and `Kbdvbase` have no `os_*` door in
 * the kit — the oracle answers them with `OS_SCREEN_BASE` and `OS_KBDVBASE`, and the two inlines
 * below are where the reconstruction asks for them, so that an ON-TARGET build has ONE seam to
 * shadow per call rather than a constant compiled into the middle of a routine. STATUS.md's
 * "Follow-ups the kit should absorb" carries the gap and "Not reconstructed" carries what a real
 * `Kbdvbase` would cost the core that uses it.
 */
#ifndef FS_INIT_H
#define FS_INIT_H

#include <stdint.h>

#include "os.h"

#include "globals.h"

/* THE TWO UNDOORED XBIOS CALLS, one inline each.
 *
 * Each answers with the constant the kit's own shim answers the trap with, so the reconstruction
 * and the oracle read one fact out of one header instead of this file inventing a number. THE VALUE
 * IS AN IMAGE OFFSET ONLY UNDER THE MODEL: on a real machine `Kbdvbase()` returns a TOS pointer
 * into ROM-owned RAM and `Physbase()` a screen address, and neither is an offset into this
 * program's image — so an on-target build replaces these two bodies with the real XBIOS calls and
 * whatever it is that turns their answers into something a core may index through.
 */
static inline uint32_t fs_physbase(void) { return OS_SCREEN_BASE; }
static inline uint32_t fs_kbdvbase(void) { return OS_KBDVBASE; }

/* ================================================================================================
 * load_file @ 0x10bfa and probe_disc @ 0x10c4c
 *
 * One record is `[dest.l][len.l]` then the ASCIZ DOS path (`include/globals.h`, FILE_REC_*). Both
 * longwords are RELOCATED in the image, so the destination is an absolute address at run time —
 * which is why the record is read out of the image and never transcribed.
 * ============================================================================================= */
#define A_load_file_handle 0x17774u /* WORD: `move.w d0,$17774` @ 0x10c18 — Fopen's result, narrowed
                                     * to a word, and what `Fclose` is given back @ 0x10c38 */
#define A_load_dest        0x17776u /* LONG: `move.l (a0)+,$17776` @ 0x10bfe */
#define A_load_len         0x1777au /* LONG: `move.l (a0)+,$1777a` @ 0x10c04 */
/* The `move.w #$2,-(a7)` @ 0x10c0a and @ 0x10c62 is Fopen's MODE, and it is deliberately not named
 * here: the kit's door is `os_fopen(mem, name_ptr)` and takes no mode at all, so a constant for it
 * would be a value the reconstruction cannot pass and does not honour. */

/* THERE IS NO ERROR CHECK IN `load_file` AT ALL: a failed `Fopen` yields a negative handle and the
 * `Fread` simply fails. The disc-presence handshake is `probe_disc`'s job instead, and it is the one
 * routine here that tests the handle. */
#define A_disc_probe_result 0x17692u /* LONG: `move.l d0,$17692` @ 0x10c70 — Fopen's WHOLE result,
                                      * so >= 0 means disc A is in the drive */

/* ================================================================================================
 * The three palette wrappers @ 0x111a6 / 0x111be / 0x111d6
 *
 * Each is `movem.l` / push a table address / XBIOS Setpalette / `movem.l` / `rts`, and differs from
 * the other two in the address alone.
 * ============================================================================================= */
#define A_palette_title 0x16274u /* `move.l #$16274,-(a7)` @ 0x111da */
#define A_palette_game  0x16294u /* `move.l #$16294,-(a7)` @ 0x111c2 */
#define A_palette_black 0x162b4u /* `move.l #$162b4,-(a7)` @ 0x111aa — sixteen zero words */

/* ================================================================================================
 * boot_init @ 0x14bee — SLICE [0x14bee, 0x14d06), the whole routine up to `bra.w main`
 *
 * It never returns: it ends by branching into `main`. The ring arithmetic it performs is
 * `include/globals.h`'s (SCREEN_RING_*), because the memory model is what that produces; what is
 * here is the rest of the routine.
 * ============================================================================================= */
/* The Setscreen @ 0x14c18 passes two bases the routine throws away four instructions later (its
 * next act is a `Physbase` whose answer everything below is derived from). What the call is FOR is
 * its third argument: it forces the machine into low resolution before anything is drawn. */
#define BOOT_SETSCREEN_LOG   0x70000u /* `move.l #$70000,-(a7)` @ 0x14c0e */
#define BOOT_SETSCREEN_PHYS  0x78000u /* `move.l #$78000,-(a7)` @ 0x14c08 */
#define BOOT_RESOLUTION_LOW  0        /* `move.w #$0,-(a7)` @ 0x14c04 — 320x200, 16 colours */

/* The LEVEL-4 vector this routine installs, and the longword it saves the old one into. The ACIA's
 * vector is the other half of the same pair and lives in `include/irq.h` (`VECTOR_ACIA`,
 * `FN_ACIA_IKBD_ISR`), which is where the handlers that pass it between them are: one name has one
 * home, and `src/init.c` includes both headers.
 *
 * They are vectors, not game globals, so they are deliberately not `A_*`: `test_constants.py`
 * requires every `A_*` to lie inside the program and these do not. */
#define VECTOR_VBL     0x70u    /* `move.l a0,$70` @ 0x14cbc — 68000 autovector 4 */
#define FN_VBL_HANDLER 0x11636u /* `lea $11636.l,a0` @ 0x14cb6 */
#define A_vbl_chain_vector 0x11650u /* the OPERAND of `vbl_handler`'s closing `jmp`, which
                                     * `move.l $70.l,$11650.l` @ 0x14cac fills from TOS's own
                                     * handler. It lives inside TEXT and is data, not code */

/* The IKBD command that turns joystick reports on, and what the ACIA handler then decodes. Without
 * it the 6301 sends key scancodes only and `acia_ikbd_isr`'s two header arms are never taken. */
#define IKBD_CMD_JOYSTICK_EVENT_REPORTING 0x14u /* `move.w #$14,-(a7)` @ 0x14cd4, BIOS Bconout dev 4 */

/* XBIOS Kbdvbase's struct, and the one field the boot chain rewrites: TOS's own joystick-packet
 * callback. `A_saved_tos_joyvec` keeps the vector that was there, and nothing ever reads it back. */
#define KBDVBASE_JOYVEC    0x18u    /* `adda.l #$18,a0` @ 0x14cee */
#define A_saved_tos_joyvec 0x19098u /* `lea $19098(pc),a1 / move.l (a0),(a1)` @ 0x14cf4 */
#define FN_TOS_JOYVEC_HANDLER 0x141fau /* `lea $141fa(pc),a1 / move.l a1,(a0)` @ 0x14cfa */

/* ================================================================================================
 * init_load_assets @ 0x11212 — TWO SLICES, because the middle of it is another subsystem's
 *
 * [0x11212, 0x1127e) is the title picture and its copy to the screen; [0x112b2, 0x112f8] is the
 * sprite bank and the directory relocation. Between them sits `clr.w d0 / bsr.w load_level_assets`
 * @ 0x112ac, which is the FRONTEND subsystem's routine — so there is no whole-routine core here,
 * and STATUS.md files a row per slice.
 *
 * THE DISC-PROMPT BLOCK AT 0x11280..0x112aa IS DEAD. The `bra.s $112ac` @ 0x1127e branches straight
 * over it, and its first word (0xf97a) is not even a valid instruction — the block was patched out
 * of the shipped binary and what remains is the loader's "please insert disc A" retry loop plus a
 * `probe_disc` call nothing reaches.
 * ============================================================================================= */
#define NEO_PALETTE_OFFSET 4u     /* `adda.l #$4,a0` @ 0x11250 — a NEOchrome file's 16 colour words
                                   * start at its header + 4, and XBIOS Setpalette is pointed there
                                   * IN PLACE rather than at a copy */
#define TITLE_COPY_OFFSET 0x80u   /* `suba.l #$80,a1` @ 0x11268 — the destination is Physbase MINUS
                                   * the NEO header's own length, so the header lands just below the
                                   * screen and the picture's pixels land exactly on it */
#define TITLE_COPY_LONGS 0x1f40u  /* `move.w #$1f3f,d7` + `dbf` @ 0x1126e: 8,000 longwords = 32,000
                                   * bytes, one whole 320x200 four-plane frame */
#define A_level0_assets_loaded 0x176eau /* `st $176ea` @ 0x112b2 — one byte, the boot chain's record
                                         * that level 0's five files are already in memory.
                                         * `enter_title` @ 0x1030e reads it to decide whether to
                                         * load them again */

/* ================================================================================================
 * init_new_game @ 0x112fa — SLICE [0x112fa, 0x11394)
 *
 * The per-GAME reset. It never returns to `main`: it ends `bra.w enter_title`, so the title screen
 * runs off this call's stack frame and the slice is diffed at that branch.
 * ============================================================================================= */
#define GAME_OVER_DELAY_FRAMES 0x50u /* `move.w #$50,$176aa` @ 0x1133a — 80 frames of "GAME OVER" */
#define NAME_ENTRY_TIMEOUT     0x32u /* `move.w #$32,$176de` @ 0x11370 */
/* FOUR OF ITS STORES TAKE THEIR VALUE FROM `A_const_words_0123` (include/hud.h), the table of the
 * words 0..9 this program spells small immediates with — three of them through that header's own
 * `CONST_WORD_ZERO`, and the fourth through the index below. It is a table INDEX and not the value
 * the store writes: the two coincide only because the table is the identity, and a reader who
 * "corrected" it to a count would silently change the address read. The other six bonus-life flags
 * are plain `clr.w`, the same value spelt the other way, and are reproduced as written. */
#define NEW_GAME_LIVES_INDEX  5u  /* `move.w $176b6,$17712` @ 0x11378 — five lives */

/* ================================================================================================
 * init_stage_state @ 0x1139a — SLICE [0x1139a, 0x11438)
 *
 * The per-STAGE reset. Its last two instructions are a DISPATCH and not a return:
 * `tst.b hard_mode / beq.w $12cb6 / bra.w $12cc8` picks between the two entries of
 * `difficulty_apply_fire_rates` (`include/entity.h`), each of which falls into `start_level`
 * (`include/scroll.h`). The slice therefore stops at the `beq.w`, with the `tst.b` — which writes
 * nothing — inside it.
 * ============================================================================================= */
#define STAGE_SCROLL_POS_SEED   0x2eu /* `move.w #$2e,$17758` @ 0x1142a */
#define STAGE_BOMB_CASH_PERIOD  0x0au /* `move.w #$a,$176c0` @ 0x113d8 */
#define STAGE_LANDING_SHADOW    0x02u /* `move.w #$2,$17740` @ 0x11412 */
#define STAGE_TAKEOFF_SHADOW    0x13u /* `move.w #$13,$1773e` @ 0x1141a */
#define STAGE_SHADOW_OFFSET     0x01u /* `move.w #$1,$1773c` @ 0x11422 */

#define A_keep_enemy_fire_inhibit 0x177cbu /* `tst.b $177cb` @ 0x113e6 and @ 0x14b40 — when set, the
                                         * stage reset leaves `A_enemy_fire_inhibit` alone. WRITTEN
                                         * NOWHERE in
                                         * the image: a sixth cheat flag with no handler behind it,
                                         * so the guarded `clr.w` always runs */

/* The two words the resets clear that NOTHING EVER READS. Both were swept for over the whole
 * program, in the relocated long-absolute form every access to a global here takes: 0x176a2 is
 * named by the `clr.w` @ 0x1135e and by no other instruction, 0x176a8 by the `clr.w` @ 0x113be and
 * by no other. They are spelt out rather than folded into a neighbour's clear because each really
 * is its own `clr.w` and the differential sees both. */
#define A_unread_word_176a2 0x176a2u
#define A_unread_word_176a8 0x176a8u

/* ================================================================================================
 * main @ 0x15750 — the frame loop
 *
 * Three `bsr`s and then an ENDLESS 45-call loop from 0x1575c to 0x1580c that ends
 * `clr.w level_just_started / bra.w $1575c`. `frame_loop_once` is one pass of it.
 * ============================================================================================= */
#define FRAME_LOOP_TOP 0x1575cu /* the address the loop's `bra.w` @ 0x15816 goes back to, and the
                                 * one `restart_level_at_checkpoint` @ 0x14bea branches to */
#define FRAME_LOOP_CALLS 45u    /* `bsr.w` at 0x1575c, 0x15760, ... 0x1580c inclusive */

/* THE THREE REGISTER INPUTS THE LOOP CARRIES BETWEEN CALLS. This game's routines take arguments in
 * registers, and three of the forty-five read one their PREDECESSOR in the loop left behind rather
 * than one their own code sets. `src/init.c` says how each value is established and
 * `test_init.py::test_the_frame_loops_register_carries_are_what_the_original_leaves` re-derives all
 * three from the ORACLE, so a claim here that stopped being true fails by name.
 */
#define FRAME_BLAST_SCRATCH_D0 0u /* D0 at `bsr bomb_blast_step` @ 0x157d4: its high word indexes
                                   * `A_blast_offset_tbl` (src/weapons.c) */
#define FRAME_TEXT_X_D1 0u        /* D1 and D2 at `bsr player_publish` @ 0x15774, which passes them */
#define FRAME_TEXT_Y_D2 0u        /* on to the game-over banner's text script (src/player.c) */

/* ================================================================================================
 * The cores
 * ============================================================================================= */
void load_file(uint8_t *image, uint32_t record);
void probe_disc(uint8_t *image);
void set_palette_black(uint8_t *image);
void set_palette_game(uint8_t *image);
void set_palette_title(uint8_t *image);
void derive_screen_ring(uint8_t *image, uint32_t physbase);
void boot_init(uint8_t *image);
void entry_stub(uint8_t *image);
void init_load_assets_title(uint8_t *image);
void init_load_assets_sprites(uint8_t *image);
/* `init_load_assets` @ 0x11212 WHOLE — the two slices above with `load_level_assets(0)` between
 * them, which is the frontend subsystem's and was unported when the two slices were cut. */
void init_load_assets(uint8_t *image);
void init_new_game(uint8_t *image);
void init_stage_state(uint8_t *image);
void clear_actor_arrays(uint8_t *image);
void frame_loop_once(uint8_t *image);

/* `main` @ 0x15750, SLICE [0x15750, 0x15758) — its first two `bsr`s. THE C CANNOT BE CALLED `main`:
 * that name is the C runtime's and a translation unit cannot spell it with this signature, so the
 * core carries the slice's name instead and `../names.txt`'s `fn 0x15750 main` is what it is filed
 * under. What is NOT here is the third `bsr` @ 0x15758: `init_new_game` ends `bra.w enter_title`,
 * so control leaves for the title screen and 0x15758 is reached only when `title_attract_loop`'s
 * own `rts` comes back to it. `test_init.py` composes that whole path in one case; a C function
 * cannot, because the stack unwind between them is not an expression. */
void main_boot(uint8_t *image);

#endif /* FS_INIT_H */
