/* init.h — the startup chain: _start and the three initialisers it opens with.
 *
 * Every A_* address is a Ghidra address (image offset + the 0x10000 load base) and mirrors a `var`
 * line in ../../names.txt, which stays the source of truth for the name.
 *
 * This layer is the game's TOP, so it reads almost every other one: it includes the headers whose
 * globals and entry points it drives rather than restating a single address (a second copy would
 * drift silently — see the pins in test/test_constants.py).
 *
 * FOUR CONSTANTS BELOW ARE A SECOND SPELLING OF ONE src/input.c ALREADY HAS, and are marked where
 * they are defined. src/input.c's copies are private to that translation unit, so they cannot be
 * reached from here, and this layer may not edit it — the fix is to hoist each pair into addrs.h
 * once, which is an integrator's change and is reported rather than taken. They are: A_tos_conterm
 * (TOS_CONTERM), KBDVBASE_MOUSEVEC / KBDVBASE_JOYVEC (KBDV_MOUSEVEC / KBDV_JOYVEC) and
 * HISCORE_FILE_BYTES (HISCORE_RECORD_BYTES).
 */
#ifndef JOUST_INIT_H
#define JOUST_INIT_H

#include <stdint.h>

#include "addrs.h"
#include "draw.h"     /* fill_screen, draw_string, A_player2 */
#include "input.h"    /* the system state init_system saves for the quit path to hand back */
#include "object.h"   /* A_message_table / MSG_*, A_pterodactyl_table / PT_*, A_draw_x */
#include "player.h"   /* A_two_player_mode */
#include "render.h"   /* SPAWN_IN_USE, SPAWN_RECORD */
#include "score.h"    /* score_update_p1/p2, draw_lives_p1/p2, OBJ_SCORE_PTR, A_game_over_flag */
#include "sound.h"    /* snd_tone_sweep */
#include "wave.h"     /* A_spawn_timer */
#include "world.h"    /* draw_platforms, the spawn/effect tables, the ground-fire edges */

/* The whole low-resolution framebuffer: 200 rows of SCREEN_ROW_BYTES. init_game puts the lava
 * surface one byte past its end, and the title picture is exactly this long. */
#define SCREEN_BYTES 0x7d00u

/* ---- TOS state ------------------------------------------------------------------------------ */
#define A_tos_conterm  0x484u   /* TOS system variable: key-click / bell / key-repeat flags.
                                 * SECOND SPELLING of src/input.c's TOS_CONTERM — see above */
#define CONTERM_KEEP   0xf8u    /* `andi.b #$f8`: init_system turns the low three flags off */
#define KBDVBASE_MOUSEVEC 0x10u /* KBDVBASE (os.h OS_KBDVBASE): the IKBD mouse-packet vector...
                                 * SECOND SPELLING of src/input.c's KBDV_MOUSEVEC */
#define KBDVBASE_JOYVEC   0x18u /* ...and the joystick-packet vector. Likewise KBDV_JOYVEC */

/* The two IKBD packet handlers init_system hooks into KBDVBASE. Each is three instructions — store
 * the packet pointer and return — so the game reads its input out of ikbd_packet rather than from
 * the interrupt. They are what the oracle can never run (TRAP_MODEL.md's IKBD limit). */
#define A_ikbd_mouse_handler 0x102d2u  /* -> ikbd_packet - 4 (the mouse packet's own slot) */
#define A_ikbd_joy_handler   0x102dau  /* -> ikbd_packet */

#define A_ikbd_cmd_joymode 0x1145au /* 1 byte ($15, SET JOYSTICK INTERROGATION MODE): sent once at
                                     * startup, which is what makes the $16 interrogations that
                                     * read_joysticks and title_screen send later answerable */

/* ---- files ---------------------------------------------------------------------------------- */
#define A_fname_mono_err 0x102beu   /* "MONO.ERR" — the "this game needs colour" splash */
/* Where every file the game loads lands: the PRG's own data segment, which the loaded file
 * overwrites. MONO.ERR puts MONO_SPLASH_BYTES of high-resolution bitmap here, and JOUST.MUR
 * SCREEN_BYTES — the title picture title_screen paints straight out of it (../recreate/README.md
 * treats JOUST.MUR as music; the copy at 0x10ac0 is what says otherwise). */
#define A_load_buffer 0x23aaeu
#define HISCORE_FILE_BYTES 0x1au    /* what init_system reads back out of HIGH.SCO.
                                     * SECOND SPELLING of src/input.c's HISCORE_RECORD_BYTES */

/* ---- palettes ------------------------------------------------------------------------------- */
#define A_game_palette 0x1143au     /* the 16 words XBIOS Setpalette is handed when play starts */
#define A_title_palette 0x10cd2u    /* ...and the 16 the TITLE screen is handed, by xbios_setpalette.
                                     * A RELOCATED longword immediate: 0xcd2 in the file, 0x10cd2
                                     * once loaded at IMAGE_LOAD_BASE (see rng.c for the same trap) */
#define A_palette_cycle_ctr 0x10d52u /* .w — bumped once per title-screen frame; its bits 8-10 are
                                      * what pick the components the hue is next shown in */

/* ---- the templates init_game copies into RAM ------------------------------------------------ */
#define A_init_players_template 0x1145cu /* the two player object records, back to back... */
#define A_init_globals_template 0x114f8u /* ...and, immediately after them, the wave/HUD globals.
                                          * Also the players' template's exclusive bound */
#define A_init_globals_template_END 0x1150fu

/* ---- startup roles of the sprite-draw scratch ------------------------------------------------
 * init_system borrows two of the drawing layer's globals before anything is drawn, exactly as the
 * quit path and the name-entry screen do (see input.h). draw_x carries two unrelated values in one
 * routine — the palette pen being read back, and then a GEMDOS file handle — so it earns a name per
 * role rather than one vague one. Aliases, so there is still one address per name. */
#define A_boot_palette_pen    A_draw_x    /* .w — 0..15 while the startup palette is read back */
#define A_boot_palette_cursor A_draw_dst  /* .l — where the next Setcolor answer is stored */
#define A_boot_file_handle    A_draw_x    /* .w — MONO.ERR's, then HIGH.SCO's, GEMDOS handle */

/* --- init.c ---------------------------------------------------------------------------------- */
void init_system(uint8_t *image);
void init_video(uint8_t *image);
void init_game(uint8_t *image);

/* The title screen's two palette helpers — see src/init.c for both, including why the first
 * returns a value. */
uint32_t xbios_setpalette(uint8_t *image);
void cycle_palette(uint8_t *image);

/* _start @ 0x10000, RECONSTRUCTED ONLY AS FAR AS ITS THIRD CALL — see the comment in src/init.c. */
void start(uint8_t *image);

#endif /* JOUST_INIT_H */
