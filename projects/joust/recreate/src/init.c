/* init.c — Joust's startup chain: _start, the three initialisers it opens with, the attract screen
 * its third call puts up, and the two palette helpers that screen is built out of.
 *
 * This is the most trap-dense code in the game, so the kit's TOS model
 * (tools/recreate_kit/TRAP_MODEL.md) decides how much of it can be proved at all. Four of its
 * limits shape this file:
 *
 *   * **XBIOS Getrez always answers 0.** The model has one resolution, so init_system's monochrome
 *     branch — its MONO.ERR splash and the Pterm behind it — is UNREACHABLE under the oracle and
 *     therefore unverified. It is reproduced rather than dropped, and marked. Nothing about that
 *     answer is a hidden mirror: the routine stores it into saved_rez, where the differential
 *     compares it like any other byte.
 *   * **Setpalette / Setcolor / Setscreen / Ikbdws / Kbdvbase change no memory.** Their arguments
 *     are invisible to an image diff, so test_init.py reads each one back out of the oracle's own
 *     stack at a checkpoint placed just past the trap. That is the only thing that can catch a
 *     wrong palette pointer or a wrong IKBD command byte.
 *   * **A refused os_* call is a FALSE GREEN if only one side makes it**, which is why every guard
 *     here is transcribed rather than simplified away: the Fopen handle tests, the Bconstat gate in
 *     front of the monochrome splash's Bconin. The kit tallies the candidate's refusals now and
 *     harness.differential() raises on a non-zero count, so a dropped guard fails loudly — but only
 *     where a case reaches it, and it proves the guard is REACHED, never that it is the right one.
 *   * **_start never returns**, and neither does the monochrome branch. There is no `rts` to diff
 *     at, so the reconstruction stops where the original's next act is a call it cannot follow, and
 *     the test pins that with a checkpoint PC PAIRED with a proof the run does not reach `rts`.
 *
 * TWO BLOCKS OF init_system ARE DEAD IN THE SHIPPED BINARY and are deliberately NOT reconstructed:
 * 0x10206..0x10223 (load the music off raw floppy through 0x152c6, else halt) and
 * 0x10226..0x10263 (open JOUST.MUR and read SCREEN_BYTES of it over the data segment). Nothing
 * branches to either — 0x10204 jumps over the first and 0x10224 over the second — so the Gamex
 * release simply skips both and runs on the placeholder picture the PRG already carries. The halt
 * at 0x10214 inside the first block IS reachable, from the monochrome branch's failed Fopen, and is
 * reproduced there.
 */
#include "machine.h"
#include "os.h"

#include "init.h"

/* =================================================================================================
 * init_system @ 0x10080 — take the machine over: resolution, palette, keyboard, screen, high score.
 * ============================================================================================= */

/* XBIOS Getrez. The kit's shim answers 0 for every run, so only the low-resolution path below is
 * ever executed; TOS_REZ_MONO is what the original refuses to run in. */
#define TOS_REZ_LOW  0u
#define TOS_REZ_MONO 2u   /* `cmpi.b #$2` — ST high resolution (640x400 monochrome) */

/* XBIOS Setcolor(pen, TOS_SETCOLOR_QUERY) reads a pen back without changing it. The model has no
 * palette and answers 0 for every pen — and that zero is not invisible: it is what the loop below
 * stores into saved_palette, which the differential compares. */
#define TOS_SETCOLOR_QUERY  0xffffu
#define TOS_SETCOLOR_ANSWER 0u
#define PALETTE_PENS 0x10u  /* `cmpi.w #$10` — the ST's 16 hardware colour registers */

/* Read the whole hardware palette back so the quit path can put it there again. Both the pen and
 * the write cursor live in memory and are re-read every pass, exactly as the original spells them.
 */
static void save_palette(uint8_t *image) {
    wr16(image + A_boot_palette_pen, 0);
    wr32(image + A_boot_palette_cursor, A_saved_palette);
    do {
        uint32_t cursor = be32(image + A_boot_palette_cursor);
        wr16(image + cursor, TOS_SETCOLOR_ANSWER);   /* XBIOS Setcolor(pen, TOS_SETCOLOR_QUERY) */
        wr32(image + A_boot_palette_cursor, cursor + 2);
        wr16(image + A_boot_palette_pen, (uint16_t)(be16(image + A_boot_palette_pen) + 1));
    } while (be16(image + A_boot_palette_pen) != PALETTE_PENS);
}

/* Hook the IKBD's mouse and joystick packet handlers, keeping the vectors TOS had so poll_quit_key
 * can put them back. The handlers themselves only record the packet pointer; the interrupt that
 * calls them is what the oracle never runs. */
static void install_ikbd_handlers(uint8_t *image) {
    wr32(image + A_saved_mousevec, be32(image + OS_KBDVBASE + KBDVBASE_MOUSEVEC));
    wr32(image + A_saved_joyvec, be32(image + OS_KBDVBASE + KBDVBASE_JOYVEC));
    wr32(image + OS_KBDVBASE + KBDVBASE_MOUSEVEC, A_ikbd_mouse_handler);
    wr32(image + OS_KBDVBASE + KBDVBASE_JOYVEC, A_ikbd_joy_handler);
}

#define HISCORE_LOADED_MARK 0x20u  /* what a successful read leaves in hiscore_dirty — and
                                    * save_hiscore (src/input.c) gates on that byte with `tst.b`,
                                    * so a boot that finds HIGH.SCO is already "dirty" and every
                                    * Ctrl-C afterwards rewrites the file. Reproduced, not fixed. */

/* Read the saved high score back off disk.
 *
 * Fread is handed the handle STILL IN D0 while Fclose re-reads it from memory, and the original
 * really does spell it both ways — so a single cached local would not be the same routine. The
 * negative test is on the word that was just stored, i.e. a SIGNED WORD test, which is how a GEMDOS
 * error code reads as a failure there.
 *
 * THE FAILURE ARM IS UNREACHABLE UNDER THE ORACLE and reproduced unverified: os_fopen either serves
 * a staged name or refuses the whole run, so no input makes it return -1 to a run that continues.
 */
static void load_hiscore(uint8_t *image) {
    int32_t handle = os_fopen(image, A_fname_highsco);

    wr16(image + A_boot_file_handle, (uint16_t)handle);
    if ((int16_t)handle < 0) return;
    os_fread(image, (uint16_t)handle, HISCORE_FILE_BYTES, A_hiscore_name);
    image[A_hiscore_dirty] = HISCORE_LOADED_MARK;
    os_fclose(image, be16(image + A_boot_file_handle));
}

/* ---- the monochrome branch: UNREACHABLE UNDER THE ORACLE, hence unverified -------------------
 * Getrez is modeled as one fixed resolution, so nothing below ever runs and nothing below is proved
 * by any case. It is transcribed because dropping a whole arm of a function would be a bigger lie
 * than carrying an unverified one, and because an on-target build needs it. */

#define MONO_SPLASH_BYTES     0x1f40u /* what MONO.ERR holds */
#define MONO_SPLASH_DST_OFF   0x1f54u /* where it lands in the high-resolution framebuffer */
#define MONO_SPLASH_LONGS     0xau    /* longwords copied per row (`move.b #$a,d0` + `subq.b`)... */
#define MONO_SCREEN_ROW_BYTES 0x50u   /* ...into an 80-byte 640-pixel monochrome scanline, so the
                                       * picture is half the screen's width */
#define MONO_ACK_KEY          0x0du   /* RETURN: the only key that dismisses the splash */

static void mono_error(uint8_t *image) {
    int32_t handle = os_fopen(image, A_fname_mono_err);

    wr16(image + A_boot_file_handle, (uint16_t)handle);
    /* No splash to show: the original enters supervisor mode and `stop #$2700`s for ever at 0x10214
     * — interrupts masked, so nothing wakes it. No C analogue, and no post-state to compare. */
    if ((int16_t)handle < 0) return;
    os_fread(image, (uint16_t)handle, MONO_SPLASH_BYTES, A_load_buffer);
    os_fclose(image, be16(image + A_boot_file_handle));
    wr32(image + A_screen_base, OS_SCREEN_BASE);            /* XBIOS Physbase() */

    uint32_t src = A_load_buffer, row = be32(image + A_screen_base) + MONO_SPLASH_DST_OFF;
    do {
        uint32_t dst = row;
        for (unsigned n = loop_passes(MONO_SPLASH_LONGS, COUNT_MASK_BYTE); n--; ) {
            wr32(image + dst, be32(image + src));
            src += 4;
            dst += 4;
        }
        row += MONO_SCREEN_ROW_BYTES;
    } while (src < A_load_buffer + MONO_SPLASH_BYTES);

    /* Wait for RETURN. The Bconstat gate is what stops Bconin from blocking, and is transcribed for
     * that reason; the spin itself is uncapped, faithfully — the original has no cap either. */
    for (;;) {
        uint32_t pending = 0, console = 0;
        os_bconstat(image, OS_BIOS_DEV_CON, &pending);
        if (pending != OS_BCONSTAT_READY) continue;
        os_bconin(image, OS_BIOS_DEV_CON, &console);
        if ((uint8_t)console == MONO_ACK_KEY) break;
    }
    /* GEMDOS Pterm(0): the original ends the process here and never returns. */
}

/* Take the machine over. Everything from the palette read-back on is what poll_quit_key hands back
 * again on Ctrl-C, so the two routines are each other's mirror. */
void init_system(uint8_t *image) {
    uint16_t rez = TOS_REZ_LOW;                             /* XBIOS Getrez() */
    uint32_t supervisor_stack = 0;

    if ((uint8_t)rez == TOS_REZ_MONO) {                      /* `cmpi.b`: the low byte only */
        mono_error(image);
        return;
    }
    wr16(image + A_saved_rez, rez);
    save_palette(image);

    /* GEMDOS Super(0): the returned stack pointer is dropped on the spot (`addq.l #6,a7`). The call
     * is here only so the conterm write below happens in supervisor mode. */
    os_super(OS_SUPER_ENTER, &supervisor_stack);
    (void)supervisor_stack;
    image[A_conterm_save] = image[A_tos_conterm];
    image[A_tos_conterm] &= CONTERM_KEEP;

    install_ikbd_handlers(image);
    /* XBIOS Ikbdws(0, A_ikbd_cmd_joymode): one byte to the IKBD — no image effect.
     * XBIOS Setscreen(-1, -1, 0): leave both screen pointers alone, low resolution — likewise. */
    wr32(image + A_screen_base, OS_SCREEN_BASE);            /* XBIOS Physbase() */

    load_hiscore(image);
    image[A_two_player_mode] = 0;
}

/* =================================================================================================
 * init_video @ 0x104b2 — put the playfield on the screen for the first time.
 * ============================================================================================= */

/* The score bar: two four-cell blocks, three rows tall, painted a longword at a time. The original
 * spells the six offsets in this order and folds the last one into the cursor's own `(a0)+`. */
#define HUD_BAR_OFF     0x6ae0u   /* screen offset of the bar's first cell (row 171) */
#define HUD_BAR_COLUMN  0x80u     /* ...and of the second block, 16 cells to its right */
#define HUD_BAR_PASSES  4u        /* `moveq #$4` + `subq.w`: four cells of each block */
#define HUD_BAR_PLANES01 0x0000ffffu  /* `move.l #$ffff,d1`: plane 0 clear, plane 1 solid... */
#define HUD_BAR_PLANES23 0xffffffffu  /* ...and `moveq #$ff,d2`, which SIGN-EXTENDS to all ones —
                                       * so planes 2 and 3 are both solid, not the byte the
                                       * immediate reads as. The bar is white, not two-coloured */

static const uint16_t HUD_BAR_CELL_OFFSETS[] = {
    HUD_BAR_COLUMN,
    SCREEN_ROW_BYTES + HUD_BAR_COLUMN,
    2 * SCREEN_ROW_BYTES + HUD_BAR_COLUMN,
    SCREEN_ROW_BYTES,
    2 * SCREEN_ROW_BYTES,
    0,
};

#define HUD_BAR_CELLS (sizeof HUD_BAR_CELL_OFFSETS / sizeof HUD_BAR_CELL_OFFSETS[0])

static uint32_t hud_bar_halfcell(uint8_t *image, uint32_t cursor, uint32_t planes) {
    for (unsigned index = 0; index < HUD_BAR_CELLS; index++)
        wr32(image + cursor + HUD_BAR_CELL_OFFSETS[index], planes);
    return cursor + 4;
}

void init_video(uint8_t *image) {
    uint32_t cursor;

    /* XBIOS Setpalette(A_game_palette): off-image, so only test_init.py's stack read-back sees it. */
    fill_screen(image, 0);

    cursor = be32(image + A_screen_base) + HUD_BAR_OFF;
    for (unsigned pass = HUD_BAR_PASSES; pass--; ) {
        cursor = hud_bar_halfcell(image, cursor, HUD_BAR_PLANES01);
        cursor = hud_bar_halfcell(image, cursor, HUD_BAR_PLANES23);
    }

    draw_platforms(image);
    score_update_p1(image);
    score_update_p2(image);
    draw_lives_p1(image);
    draw_lives_p2(image);
    snd_tone_sweep(image);
}

/* =================================================================================================
 * init_game @ 0x105f0 — reset one game's worth of state.
 * ============================================================================================= */

#define SPAWN_TIMER_INIT       0x3e8u  /* frames before the first pterodactyl may be scheduled */
#define GROUND_ANIM_TIMER_INIT 0x28u   /* frames before the lava's fire animation first steps */
#define GROUND_X1_INIT         0x13fu  /* 319: the ground spans the whole screen to start with */
#define RNG_SEED_MASK          0xfeu   /* `andi.l #$fe`: XBIOS Random seeds the cursor with an EVEN
                                        * offset of at most 254 bytes into the program image */

void init_game(uint8_t *image) {
    uint32_t screen = be32(image + A_screen_base);
    uint32_t src, dst;

    /* Two template copies straight out of the program's own data: the wave/HUD globals, then the two
     * player object records that sit just below them. The first bound is a SIGNED compare and the
     * second an equality test, transcribed as written — no input can tell them apart here. */
    for (src = A_init_globals_template, dst = A_players_alive; src < A_init_globals_template_END; )
        image[dst++] = image[src++];
    for (src = A_init_players_template, dst = A_object_table; src != A_init_globals_template; )
        image[dst++] = image[src++];

    /* Each player record carries the screen offset its score row is painted at. The template holds
     * the offset alone — the PRG's relocation table cannot reach a copy made at run time — so
     * init_game folds screen_base in by hand. */
    wr32(image + A_object_table + OBJ_SCORE_PTR,
         be32(image + A_object_table + OBJ_SCORE_PTR) + screen);
    wr32(image + A_player2 + OBJ_SCORE_PTR, be32(image + A_player2 + OBJ_SCORE_PTR) + screen);

    for (uint32_t pad = A_spawn_points; pad != A_spawn_points_END; pad += SPAWN_RECORD)
        image[pad + SPAWN_IN_USE] = 0;
    for (uint32_t slot = A_message_table; slot != A_message_table_END; slot += MSG_RECORD)
        image[slot + MSG_KIND] = 0;
    for (uint32_t slot = A_pterodactyl_table; slot < A_pterodactyl_table_END; slot += PT_RECORD)
        wr16(image + slot + PT_FLAGS, 0);

    wr16(image + A_spawn_timer, SPAWN_TIMER_INIT);

    for (uint32_t slot = A_effect_table; slot < A_effect_table_END; slot += EFF_RECORD)
        wr32(image + slot + EFF_TIMER, 0);          /* EFF_TIMER and EFF_KIND, as one longword */
    wr16(image + A_troll_state, 0);
    for (uint32_t byte = A_enemy_objects; byte != A_object_table_END; byte++)
        image[byte] = 0;                            /* the 12 non-player slots, wholesale */

    /* The pseudo-random cursor starts at a random EVEN offset into the program image. Its reset
     * value is a RELOCATED immediate — 0 in the file, the load base once loaded (see src/rng.c). */
    wr32(image + A_rng_ptr, IMAGE_LOAD_BASE);
    wr32(image + A_rng_ptr, be32(image + A_rng_ptr) + (os_random(image) & RNG_SEED_MASK));

    wr16(image + A_ground_anim, 0);
    image[A_ground_anim_timer] = GROUND_ANIM_TIMER_INIT;
    wr16(image + A_ground_x0, 0);
    wr16(image + A_ground_x1, GROUND_X1_INIT);
    wr32(image + A_playfield_bottom, screen + SCREEN_BYTES);
    image[A_game_over_flag] = 0;
}

/* =================================================================================================
 * The title screen's palette: xbios_setpalette @ 0x10c46 and cycle_palette @ 0x10c56.
 *
 * Both belong to title_screen @ 0x10aae and to nothing else — it is their only caller (0x10aae and
 * 0x10b64 for the first, 0x10b22 for the second), and they were the last two of its six callees to
 * be ported. They keep their own entries' batteries, which is what lets title_screen's below assert
 * on the two AS COMPOSED (its ring carries cycle_palette's output on) rather than re-derive them.
 * ============================================================================================= */

/* xbios_setpalette: hand the whole title palette to XBIOS Setpalette.
 *
 * The trap writes the ST's colour registers, not memory, so the call has NO image effect at all and
 * an image diff can say nothing about it. As with flash_hiscore_color (src/score.c), the argument is
 * RETURNED instead of being dropped, and test_init.py compares it against the longword the ORIGINAL
 * pushed for its own `trap #14` — which is the only thing that can catch a wrong table.
 *
 * It takes `image` it never reads so that it keeps this layer's one shape and its glue stays a bare
 * forwarder like every other.
 */
uint32_t xbios_setpalette(uint8_t *image) {
    (void)image;
    return A_title_palette;
}

/* The ST colour word: one 4-bit level per component in the low 12 bits. Private to this file
 * because cycle_palette is still the only routine that takes one apart — src/score.c builds one for
 * XBIOS Setcolor but never decomposes it. The moment a second layer needs the layout it moves to
 * include/joust.h whole, rather than being spelled out twice. */
#define PALETTE_BLUE_MASK   0x00fu
#define PALETTE_GREEN_MASK  0x0f0u
#define PALETTE_RED_MASK    0xf00u
#define PALETTE_GREEN_SHIFT 4u
#define PALETTE_RED_SHIFT   8u

/* Which of title_palette's 16 pens the cycle animates — word 4, i.e. 0x10cda. Here rather than in
 * init.h beside the table's address because it is not an address and only this file reads it; the
 * mirror pin scrapes it from here. */
#define TITLE_PALETTE_HUE_PEN 4u

/* Where one of the table's 16 pens lives. Shared by cycle_palette and by the six-pen ring
 * title_screen rotates below, which is the only reason it is a function and not a `+ 8`. */
static uint32_t title_pen(unsigned pen) {
    return A_title_palette + 2u * pen;
}

/* Which components of the palette word the hue is shown in next, as bits of palette_cycle_ctr.
 * `andi.w #$700` keeps exactly these three, so the counter's low byte is a per-frame divider: the
 * selection only changes every 256 title-screen frames. The mask is spelled as the literal the
 * instruction encodes, not as the three bits OR-ed; test_init.py pins the two equal. */
#define PALETTE_CYCLE_BLUE  (1u << 8)
#define PALETTE_CYCLE_GREEN (1u << 9)
#define PALETTE_CYCLE_RED   (1u << 10)
#define PALETTE_CYCLE_SELECT_MASK 0x700u
/* When the three bits come up zero the counter is not merely masked, it is REPLACED: the whole word
 * becomes this, so a counter that had climbed past bit 10 loses those high bits too. That is what
 * keeps the selection out of the one state — no component at all — that would blank the pen.
 * The value IS the blue select bit (the cycle restarts at its first component), which is a coupling
 * the code below depends on and test_init.py asserts; it stays a literal because that is what the
 * original's `move.w #$100` encodes. */
#define PALETTE_CYCLE_FIRST 0x100u

/* cycle_palette: one step of the colour cycle running under the title screen.
 *
 * The pen holds a single 4-bit hue in one of its three components, and each step moves that same
 * level into whichever components the counter now selects — so the title's fifth colour walks
 * blue -> green -> blue+green -> red -> ... rather than changing brightness.
 *
 * WHAT SEEDS THE PEN, AND WHAT THE GAME CAN ACTUALLY PUT THERE. The shipped title_palette holds
 * 0x0000 at pen 4, so a COLD first call can only take the early return below. title_screen's six-pen
 * ring (0x10b26..0x10b5e) is a closed cycle over pens 3/4/6/8/9/10 — shipped 0x0300, 0x0000, 0x0200,
 * 0x0400, 0x0300, 0x0200 — and this routine only RELOCATES a level, never changes it, so the only
 * values the game's own data can ever circulate through pen 4 are 0 and a level in {2,3,4}. Every
 * other pen the tests stage is constructed; ../STATUS.md says which, rather than leaving the sweep
 * looking data-backed.
 */
void cycle_palette(uint8_t *image) {
    uint32_t hue_at = title_pen(TITLE_PALETTE_HUE_PEN);

    uint16_t counter = (uint16_t)(be16(image + A_palette_cycle_ctr) + 1u);   /* addq.w #1 — WORD wide */
    /* Stored before the selector is even looked at, and stored AGAIN by the reset — two `move.w`s
     * to one address, as the original spells it. The second is not a correction of the first: the
     * original bumps the counter in memory (`addq.w #1,$10d52`) and only then decides. */
    wr16(image + A_palette_cycle_ctr, counter);
    uint16_t select = counter & PALETTE_CYCLE_SELECT_MASK;
    if (select == 0) {
        select = PALETTE_CYCLE_FIRST;
        wr16(image + A_palette_cycle_ctr, PALETTE_CYCLE_FIRST);
    }

    /* The original re-reads the pen for each component; nothing writes it in between, so one read
     * is the same three values. */
    uint16_t colour = be16(image + hue_at);
    uint16_t blue = colour & PALETTE_BLUE_MASK;
    uint16_t green = (uint16_t)((colour & PALETTE_GREEN_MASK) >> PALETTE_GREEN_SHIFT);
    uint16_t red = (uint16_t)((colour & PALETTE_RED_MASK) >> PALETTE_RED_SHIFT);

    /* `move.w dN,d3 / bne` three times over: the hue is the FIRST NON-ZERO component in blue,
     * green, red order. A pen with no colour in its low 12 bits has no hue to move, and the routine
     * leaves it exactly as it found it — high nibble included, since only the rebuild below clears
     * that. The counter has already been bumped by then. */
    uint16_t hue = blue ? blue : (green ? green : red);
    if (hue == 0)
        return;

    /* Rebuilt from nibbles rather than edited in place, so bits 12-15 of the pen are dropped. */
    uint16_t cycled = 0;
    if (select & PALETTE_CYCLE_RED)
        cycled |= (uint16_t)(hue << PALETTE_RED_SHIFT);
    if (select & PALETTE_CYCLE_GREEN)
        cycled |= (uint16_t)(hue << PALETTE_GREEN_SHIFT);
    if (select & PALETTE_CYCLE_BLUE)
        cycled |= hue;
    wr16(image + hue_at, cycled);
}

/* =================================================================================================
 * title_screen @ 0x10aae — the attract screen, and where the game is chosen.
 *
 * It paints the title picture and three lines of text once, then loops: one step of the colour
 * cycle above, one console poll TITLE_POLL_PASSES deep, and — if no key came — one IKBD joystick
 * interrogation. '1' and '2' pick the game and return; Ctrl-C leaves for the desktop; either
 * stick's fire button starts a game in whatever mode was chosen last.
 *
 * THREE OF ITS FOUR EXITS ARE NOT AN `rts`, and each needs its own treatment:
 *
 *   * THE IKBD WAIT (0x10bb8) blocks for a reply an INTERRUPT delivers, which the oracle never
 *     runs — and the routine clears ikbd_packet on the way in, so no poked reply survives to end
 *     it either (TRAP_MODEL.md's limit 1, and read_joysticks' wall). It is reproduced as the honest
 *     infinite loop it is; g_title_screen stops exactly where every oracle run must, so no case
 *     enters it.
 *   * CTRL-C IS A SEVENTH TRANSFER THAT IS NOT A CALL: a `beq.w` at 0x10bea into 0x11c56, the
 *     MIDDLE of poll_quit_key — past that routine's entry and its own Bconstat/Bconin. So it cannot
 *     be written as a call to poll_quit_key; what it reaches is the shared tail src/input.c exports
 *     as quit_to_desktop, and the never-returning exit comes back as TITLE_QUIT.
 *   * THE JOYSTICK START is reachable only from past that wait, so it is verified at its own
 *     rotated entry — title_ikbd_pass, which the oracle enters at 0x10bb8 with a reply staged.
 * ============================================================================================= */

/* The three lines painted over the picture, each in its own colour (`move.b #imm,text_color`). */
#define TITLE_COLOR_PROMPT   0xfu
#define TITLE_COLOR_HISCORE  2u
#define TITLE_COLOR_CREDITS  1u

#define TITLE_POLL_PASSES 400u  /* console polls per attract pass before the joysticks are asked */
#define SND_TITLE_TUNE    0xeu  /* sound_table index: the tune the attract loop keeps alive */
#define TITLE_STARTING_LIVES 4u /* turns each player is given when a game starts */

/* The two console keys that pick the game. Compared with `cmp.w` against the WHOLE low word of
 * Bconin's result — unlike Ctrl-C one instruction earlier, which is a `cmp.b`. */
#define TITLE_KEY_ONE_PLAYER 0x31u  /* '1' */
#define TITLE_KEY_TWO_PLAYER 0x32u  /* '2' */

/* 0x10aae..0x10b1e — the one-shot painting, run once before the attract loop. */
static void draw_title_screen(uint8_t *image) {
    (void)xbios_setpalette(image);   /* the table it hands the trap is dropped here */
    fill_screen(image, 0);

    /* The picture is SCREEN_BYTES straight out of the program's own data segment — one whole
     * low-resolution framebuffer, a longword at a time, with an EXCLUSIVE `cmpa.l` bound on the
     * source. fill_screen has just painted eight bytes MORE than that (see src/fill.c) and those
     * eight survive the copy. The bound is a constant and the start is a constant, so testing it
     * before the body is the original's post-test loop exactly. */
    for (uint32_t src = A_load_buffer, dst = be32(image + A_screen_base);
         src != A_load_buffer + SCREEN_BYTES; src += 4, dst += 4)
        wr32(image + dst, be32(image + src));

    image[A_text_color] = TITLE_COLOR_PROMPT;
    draw_string(image, STR_TITLE_PROMPT);
    image[A_text_color] = TITLE_COLOR_HISCORE;
    draw_string(image, STR_TITLE_HISCORE);
    image[A_text_color] = TITLE_COLOR_CREDITS;
    draw_string(image, STR_TITLE_CREDITS);

    g_dosound(image, A_snd_list_silence);   /* XBIOS Dosound: silence the chip behind the title */
}

/* The six pens the attract loop rotates, in the order the ORIGINAL moves them (0x10b26..0x10b5e):
 * each takes its successor's colour and the last takes the first's, so the six walk one place round
 * a closed ring every pass. TITLE_PALETTE_HUE_PEN is one of the six, so cycle_palette's write is
 * carried on by the very next step — which is why the order of those two IS held by the
 * differential here, unlike most transcribed orders in this reconstruction. */
#define TITLE_HUE_RING_PENS 6u
static const uint8_t TITLE_HUE_RING[TITLE_HUE_RING_PENS] = {10, 9, 8, 3, 6, 4};

static void rotate_title_hues(uint8_t *image) {
    uint16_t carried = be16(image + title_pen(TITLE_HUE_RING[0]));
    for (unsigned step = 0; step + 1u < TITLE_HUE_RING_PENS; step++)
        wr16(image + title_pen(TITLE_HUE_RING[step]),
             be16(image + title_pen(TITLE_HUE_RING[step + 1u])));
    wr16(image + title_pen(TITLE_HUE_RING[TITLE_HUE_RING_PENS - 1u]), carried);
}

/* Keep the attract tune going. snd_poll_done releases snd_priority to idle once the chip has fallen
 * silent; the gate then RE-READS snd_priority rather than looking at what snd_poll_done did, so a
 * pass that arrives already idle restarts the tune too. */
static void restart_title_tune_when_idle(uint8_t *image) {
    snd_poll_done(image);
    if (be16(image + A_snd_priority) == SND_PRIORITY_IDLE)
        play_sound(image, SND_TITLE_TUNE);
}

/* One console poll. Bconstat's answer is tested here with `tst.b` + `blt` rather than with the full
 * `cmp.l #-1` poll_quit_key uses, so it is the SIGN OF THE LOW BYTE that says a key is waiting. */
static int title_key_waiting(const uint8_t *image) {
    uint32_t pending = 0;
    os_bconstat(image, OS_BIOS_DEV_CON, &pending);
    return (int8_t)pending < 0;
}

/* Both key branches and the joystick one end here: 0x10bfa for two players, 0x10c1e for one, and
 * both fall into the shared tail at 0x10c32 that arms player 1. Each player gets a fresh turn count
 * and its score's units digit put back to '0' — the game holds that digit there and never carries
 * into it (score.h). The one-player arm additionally clears player 2's flags WORD, which is what
 * takes that rider off the playfield. */
static void start_game(uint8_t *image, int two_player) {
    if (two_player) {
        image[A_two_player_mode] = 1;
        image[A_players_alive] = 2;
        image[A_player2 + OBJ_SCORE_LAST_DIGIT] = '0';
        image[A_player2 + OBJ_LIVES] = TITLE_STARTING_LIVES;
    } else {
        image[A_two_player_mode] = 0;
        wr16(image + A_player2 + OBJ_FLAGS, 0);
        image[A_players_alive] = 1;
    }
    image[A_object_table + OBJ_SCORE_LAST_DIGIT] = '0';
    image[A_object_table + OBJ_LIVES] = TITLE_STARTING_LIVES;
}

/* The two `cmp.w`s at 0x10bde and 0x10be4 — the only decision in the game that picks the mode, and
 * the ONLY console input title_screen ever returns for. Named and shared rather than spelled twice
 * because _start's glue has to ask the same question before it may enter title_screen at all: on
 * anything else that routine ends in the IKBD wait no run leaves, and a bound with two
 * implementations is a bound that drifts. */
static int title_key_chooses_game(uint32_t console, int *two_player) {
    if ((uint16_t)console == TITLE_KEY_ONE_PLAYER) {
        *two_player = 0;
        return 1;
    }
    if ((uint16_t)console == TITLE_KEY_TWO_PLAYER) {
        *two_player = 1;
        return 1;
    }
    return 0;
}

/* 0x10b22..0x10bb6 — one pass of the attract loop, ending either in a key that decides the game or
 * at the IKBD interrogate no oracle run gets past. */
static uint32_t title_attract_pass(uint8_t *image) {
    cycle_palette(image);
    rotate_title_hues(image);
    (void)xbios_setpalette(image);
    restart_title_tune_when_idle(image);

    wr16(image + A_title_poll_left, TITLE_POLL_PASSES);
    for (;;) {
        if (title_key_waiting(image)) {
            uint32_t console = 0;
            os_bconin(image, OS_BIOS_DEV_CON, &console);
            /* Ctrl-C is a `cmp.b` and the two digits are `cmp.w`s, so a console longword whose low
             * word is 0x0131 is NOT '1' — the only input that can tell the two widths apart. */
            if ((uint8_t)console == KEY_CTRL_C) {
                quit_to_desktop(image);
                return TITLE_QUIT;
            }
            int two_player;
            if (title_key_chooses_game(console, &two_player)) {
                start_game(image, two_player);
                return TITLE_STARTED;
            }
            continue;   /* any other key: straight back to the poll, WITHOUT spending a pass */
        }
        /* `subq.w #1` + `bne`: a zero test on the word, not a sign test. */
        uint16_t left = (uint16_t)(be16(image + A_title_poll_left) - 1u);
        wr16(image + A_title_poll_left, left);
        if (left == 0) break;
    }

    /* Ask the IKBD for both joysticks — the same prologue read_joysticks and the name entry's
     * joystick poll open with, so it is src/input.c's request_ikbd_packet rather than a third copy.
     * It is also why no poked reply survives into the wait below: the packet is cleared first. */
    request_ikbd_packet(image);
    return TITLE_IKBD_WAIT;
}

/* 0x10bb8..0x10bd7 — the wait, and what the reply says. */
static uint32_t title_ikbd_pass(uint8_t *image) {
    wait_for_ikbd_packet(image);

    /* Either stick's fire button starts the game: the two joystick bytes are OR-ed and the branch
     * reads the SIGN of that byte, which is the IKBD's fire bit. */
    uint32_t packet = be32(image + A_ikbd_packet);
    if ((int8_t)(image[packet + IKBD_JOYSTICK_0] | image[packet + IKBD_JOYSTICK_1]) >= 0)
        return TITLE_ATTRACT;

    start_game(image, image[A_two_player_mode] != 0);   /* `tst.b`: whatever was chosen last */
    return TITLE_STARTED;
}

/* The painting and the first attract pass — which is as far as ANY run gets, since every input
 * either decides the game in that pass or reaches the IKBD wait. It is a named seam rather than two
 * statements because g_title_screen has to stop exactly here, and a glue that re-composed it would
 * be a second copy of the composition: a step added to the painting would then be executed by the
 * routine and silently skipped by every case. */
static uint32_t title_first_pass(uint8_t *image) {
    draw_title_screen(image);
    return title_attract_pass(image);
}

uint32_t title_screen(uint8_t *image) {
    uint32_t outcome = title_first_pass(image);
    for (;;) {
        if (outcome != TITLE_IKBD_WAIT) return outcome;
        outcome = title_ikbd_pass(image);
        if (outcome != TITLE_ATTRACT) return outcome;
        outcome = title_attract_pass(image);   /* round again, to the loop head at 0x10b22 */
    }
}

/* =================================================================================================
 * _start @ 0x10000 — twenty-one `jsr`s and a `bra` back into the middle of them.
 *
 * The first four run once (init_system, init_game, title_screen, init_video) and the `bra.s` at
 * 0x1007e goes back to the FIFTH, so calls 5..21 are the per-frame loop and the routine never
 * returns. It has no code of its own — no test, no register set-up, nothing between the calls — so
 * what there is to reconstruct is which routines it calls, in what order, and where the loop closes.
 *
 * THE ONE SEAM NEITHER CORE CAN CROSS is the ninth call. read_joysticks (src/player.c) blocks in
 * the IKBD wait whose reply arrives on an interrupt the oracle never runs, so the loop is written
 * as three named pieces around it and verified in two ROTATIONS that between them execute all
 * twenty-one calls and the back edge:
 *
 *   * 0x10000 -> 0x10030 — the four one-shot calls and calls 5..8, diffed at the `jsr` to
 *     read_joysticks with a console key that chooses a game staged;
 *   * 0x10036 -> 0x10030 — calls 10..21, the `bra`, and calls 5..8 again: one whole lap, rotated to
 *     begin where the oracle can begin.
 *
 * WHAT NEITHER ROTATION HOLDS is that read_joysticks sits BETWEEN the two pieces, or that the loop
 * laps at all on the C side. Both are held by the one test that is not a differential: the
 * candidate is a shared library in this process and the IKBD wait is `volatile` precisely because
 * something outside the routine ends it, so a thread poking the image IS that interrupt — the
 * technique test_read_joysticks_blocks_until_a_reply_lands introduced. ../STATUS.md records what is
 * left over.
 *
 * ONE THING A C `_start` CANNOT REPRODUCE, and it is a fidelity gap rather than a harness limit:
 * update_objects reads D0 and D2 before writing them (objects.h), and at 0x10036 both hold whatever
 * read_joysticks' last control_player left behind. The rotated pass takes them as arguments and is
 * driven with the same pair on both sides, so the argument chain is executed rather than merely
 * declared — but no frame of the walk makes those two registers observable, so nothing here would
 * catch a pass that dropped them (../STATUS.md discloses it; update_objects' own battery is what
 * holds them). And `start` has no way to carry a register across a call at all: it passes zero.
 * ============================================================================================= */

/* 0x10000..0x10017 — the four calls that run once, in the original's order. */
static void start_init_chain(uint8_t *image) {
    init_system(image);
    init_game(image);
    title_screen(image);
    init_video(image);
}

/* 0x10018..0x1002f — the frame's first four calls, up to the one that blocks. */
static void frame_pass_head(uint8_t *image) {
    raise_floor(image);
    animate_ground_shrink(image);
    count_objects_and_pad(image);
    update_eggs(image);
}

/* 0x10036..0x1007c — everything past the joystick read, ending at the `bra` back to 0x10018.
 * `flags_in`/`probe_in` are the D0 and D2 update_objects reads before writing (see above). */
static void frame_pass_tail(uint8_t *image, uint16_t flags_in, uint16_t probe_in) {
    update_objects(image, flags_in, probe_in);
    update_pterodactyl(image);
    render_objects(image);
    collision_check(image);
    draw_platforms(image);
    draw_messages(image);
    lava_troll(image);
    dissolve_platforms(image);
    wave_manager(image);
    snd_poll_done(image);
    poll_quit_key(image);
    check_highscore(image);
}

/* FOUR of the calls above have paths the ORIGINAL never comes back from — title_screen's IKBD wait
 * and its Ctrl-C, read_joysticks' restart, poll_quit_key's quit/restart/pause, and
 * check_highscore's entry loop. Each reconstruction reports its exit as a result code instead, and
 * `_start` ignores every one of them exactly as the original's twenty-one `jsr`s do: on target the
 * routine that took such a path does not return, so the next line is simply never reached. */
void start(uint8_t *image) {
    start_init_chain(image);
    for (;;) {
        frame_pass_head(image);
        read_joysticks(image);
        frame_pass_tail(image, 0, 0);   /* D0/D2 at 0x10036 — see the fidelity gap above */
    }
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Nothing in this layer takes a stack frame — each routine works entirely off globals and the
 * modeled OS state — so every g_* below is a bare forwarder bar four: title_screen's two, and
 * _start's two at the end, each of which stops where the oracle has to stop. The one
 * result an image diff cannot see (the table xbios_setpalette hands the trap) comes back as a
 * return value, exactly as g_flash_hiscore_color's colour word does, and the test compares it
 * against what the oracle really pushed.
 */

void g_init_system(uint8_t *image) { init_system(image); }

void g_init_video(uint8_t *image) { init_video(image); }

void g_init_game(uint8_t *image) { init_game(image); }

uint32_t g_xbios_setpalette(uint8_t *image) { return xbios_setpalette(image); }

void g_cycle_palette(uint8_t *image) { cycle_palette(image); }

/* THE FIRST OF THE FOUR THAT ARE NOT BARE FORWARDERS: it stops where every oracle run must stop.
 *
 * No run of title_screen can go round its attract loop twice. Either the first pass reads a key
 * that decides the game — '1', '2' or Ctrl-C — or it falls through to the IKBD wait, and that wait
 * never ends on either side: the reply arrives on an interrupt neither core runs, and the pass has
 * just cleared the word a poke could have put one in. So the glue runs the painting and exactly one
 * pass and reports where it stopped, which is precisely the state the oracle has at its 0x10bb8
 * checkpoint. A forwarder would hang the pytest worker with no output at all under `-n auto`.
 *
 * THE PRICE, STATED RATHER THAN HIDDEN: nothing executes title_screen's `for (;;)`, so the loop's
 * RE-ENTRY — the two calls it makes on a second time round — is not held by the differential. What
 * the shared `title_first_pass` seam buys is that everything BEFORE that loop is: the glue drives
 * the same function the routine does, so a step dropped from the painting or from the pass fails a
 * case rather than vanishing. ../STATUS.md records what is left. */
uint32_t g_title_screen(uint8_t *image) {
    return title_first_pass(image);
}

/* ...and the second: the IKBD wait and the fire test, entered where the ORACLE can enter them — at
 * the wait head (0x10bb8) with a reply already staged, the same rotation hiscore_joystick_input is
 * verified through. The probe is g_pause_until_key's (src/input.c): an unstaged packet would spin
 * for ever, and nothing but harness.differential's oracle-first ordering keeps a case from getting
 * here, so the refusal is reported rather than left to that ordering.
 *
 * IT REFUSES AN OUT-OF-IMAGE PACKET POINTER TOO, and that half is not about hanging. The routine
 * dereferences the pointer the wait spun for, and the two cores disagree about what lies outside
 * the image: the oracle's memory callbacks answer 0 for any address past its size, while the
 * candidate would index real host memory past the end of the buffer — undefined behaviour that
 * either fabricates a diff or kills the worker outright. Refusing is the only honest answer, since
 * neither reading is the original's. The reconstruction itself stays unguarded and faithful. */
#define TITLE_PASS_REFUSED 4u   /* glue-only: the wait was refused, so it was never entered */

/* Both refusals are one predicate, `ikbd_packet_readable` (input.h) — read_joysticks' glue asks the
 * same question, and a bound with two implementations is a bound that drifts. */
uint32_t g_title_ikbd_pass(uint8_t *image) {
    if (!ikbd_packet_readable(image)) return TITLE_PASS_REFUSED;
    return title_ikbd_pass(image);
}

/* Will title_screen COME BACK for the console this image is staged with? Only the two keys that
 * choose a game make it return; every other input — an empty console included — ends it in the IKBD
 * wait no run leaves, and Ctrl-C ends it in a GEMDOS Pterm the model refuses. It asks
 * title_key_chooses_game, the same pair of `cmp.w`s the attract pass decides with, and PEEKS at the
 * console rather than taking the key, which title_screen's own Bconin must still find there. */
static int title_screen_comes_back(const uint8_t *image) {
    uint32_t console;
    int two_player;

    if (!console_key_pending(image, &console))
        return 0;
    return title_key_chooses_game(console, &two_player);
}

/* THE INIT CHAIN AND THE FRAME LOOP'S HEAD — 0x10000 up to the `jsr` at 0x10030, which is where
 * every oracle run must stop: the ninth call blocks for ever.
 *
 * IT REFUSES A CONSOLE THAT WOULD NOT LET title_screen RETURN, and that refusal is what let this
 * checkpoint move past the third call at all. The reconstruction's title_screen is uncapped and
 * faithful, so a forwarder handed the wrong key would spin in the attract loop's IKBD wait and hang
 * the pytest worker with no output at all under `-n auto` — the one failure a differential cannot
 * report. Only harness.differential's oracle-first ordering would otherwise keep a case out of it,
 * and nothing pins that ordering, so the refusal is reported here instead. */
uint32_t g_start(uint8_t *image) {
    if (!title_screen_comes_back(image)) return START_REFUSED;
    start_init_chain(image);
    frame_pass_head(image);
    return START_AT_JOYSTICKS;
}

/* ...and ONE WHOLE LAP OF THE FRAME LOOP, rotated to begin where the oracle can begin: at the tenth
 * call (0x10036), round the `bra` at 0x1007e and back to the ninth. It drives the same two seams
 * `start`'s own loop drives rather than a glue-side copy of them, so a call added to either is
 * executed by every case here.
 *
 * IT REFUSES TWO STAGINGS, both for the reason above — the pass contains a routine that would not
 * come back:
 *
 *   * a console key poll_quit_key acts on. Ctrl-C ends in Pterm, R/r jumps to _start's second call,
 *     and P/p spins for a second keystroke the model cannot deliver.
 *   * a finished game whose leader has beaten the record, which sends check_highscore into a
 *     name-entry loop no staged input ends on either side.
 *
 * Both questions are asked of the routine that owns them — poll_quit_key_comes_back and
 * check_highscore_comes_back, both src/input.c's, each deciding through the very constants and
 * helpers its own routine decides with — so neither bound has a second copy here to drift from.
 *
 * BOTH ARE ASKED OF THE STAGED IMAGE, AND THE PASS CAN INVALIDATE THEM FROM INSIDE: the fifteenth
 * call (draw_messages) can set game_over_flag, and score_update moves the very digits the record is
 * compared against — so a lap that starts safe can reach the twenty-first call unsafe. That is a
 * bound on the refusal, not a hole in it: such a run fails LOUDLY on both sides (the oracle raises
 * at its instruction cap, the candidate at the test's wall-clock deadline) rather than passing, and
 * no frame of the walk gets there. It is recorded in ../STATUS.md rather than guessed at with a
 * second, mid-pass check that would have nothing to test itself against. */
uint32_t g_start_frame_pass(uint8_t *image, uint32_t flags_in, uint32_t probe_in) {
    if (!poll_quit_key_comes_back(image)) return START_REFUSED;
    if (!check_highscore_comes_back(image)) return START_REFUSED;

    frame_pass_tail(image, (uint16_t)flags_in, (uint16_t)probe_in);
    frame_pass_head(image);
    return START_AT_JOYSTICKS;
}
