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
            if ((uint16_t)console == TITLE_KEY_ONE_PLAYER) {
                start_game(image, 0);
                return TITLE_STARTED;
            }
            if ((uint16_t)console == TITLE_KEY_TWO_PLAYER) {
                start_game(image, 1);
                return TITLE_STARTED;
            }
            continue;   /* any other key: straight back to the poll, WITHOUT spending a pass */
        }
        /* `subq.w #1` + `bne`: a zero test on the word, not a sign test. */
        uint16_t left = (uint16_t)(be16(image + A_title_poll_left) - 1u);
        wr16(image + A_title_poll_left, left);
        if (left == 0) break;
    }

    /* Ask the IKBD for both joysticks. The reply lands in ikbd_packet on an interrupt, so the
     * routine clears the word first — which is also why no poked reply can survive to end the wait.
     * XBIOS Ikbdws(0, A_ikbd_cmd_joyread) follows and has no image effect. */
    wr32(image + A_ikbd_packet, 0);
    return TITLE_IKBD_WAIT;
}

/* The wait itself. `volatile` is what stops the compiler assuming this loop terminates and deleting
 * it: the reply is stored by an interrupt handler, which is exactly what volatile is for. Read as
 * four BYTES rather than through a wider type — the image is a byte array, `ikbd_packet` is not
 * longword-aligned, and a `tst.l` against zero does not care in which order the bytes are OR-ed. */
static void wait_for_ikbd_packet(const uint8_t *image) {
    const volatile uint8_t *packet = image + A_ikbd_packet;
    while ((packet[0] | packet[1] | packet[2] | packet[3]) == 0)
        ;
}

/* 0x10bb8..0x10bd7 — the wait, and what the reply says. */
static uint32_t title_ikbd_pass(uint8_t *image) {
    wait_for_ikbd_packet(image);

    /* Either stick's fire button starts the game: the two joystick bytes are OR-ed and the branch
     * reads the SIGN of that byte, which is the IKBD's fire bit. */
    uint32_t packet = be32(image + A_ikbd_packet);
    if ((int8_t)(image[packet] | image[packet + 1u]) >= 0) return TITLE_ATTRACT;

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
 * _start @ 0x10000 — RECONSTRUCTED ONLY AS FAR AS ITS THIRD CALL.
 *
 * The original is twenty-one `jsr`s and a `bra` back into the middle of them. The first four —
 * init_system, init_game, title_screen, init_video — run once; the `bra` at 0x1007e returns to the
 * fifth, so the remaining seventeen are an endless per-frame loop. It never returns, so there is no
 * `rts` to diff at; test_init.py stops the oracle at the THIRD call and pairs that with a proof the
 * run really does not come back.
 *
 * title_screen IS RECONSTRUCTED NOW, above, so that is no longer what stops the checkpoint here.
 * What stops it is what the third call needs in order to be entered SAFELY. title_screen returns only for a console key that
 * chooses a game ('1' or '2'); on every other input its attract loop falls into the IKBD wait,
 * which never ends on either side. The oracle is capped and raises there, but the CANDIDATE is not,
 * and a forwarding g_start reached with the wrong key staged would hang the pytest worker with no
 * output at all under `-n auto` — the one failure a differential cannot report. Moving the
 * checkpoint to the FIFTH call therefore needs g_start to refuse such a run, and the only honest
 * refusal duplicates title_attract_pass's two `cmp.w`s. That is _start's own design decision, not
 * title_screen's, so it is recorded in ../STATUS.md and left for _start's next pass rather than
 * folded in here.
 *
 * The frame loop past the fifth call is blocked regardless: read_joysticks @ 0x11d9a is unported
 * and cannot be verified at all, and check_highscore @ 0x1437a — ported — does not come back once
 * a record is set.
 *
 * So what this proves is exactly: _start does nothing of its own before those two calls, and makes
 * them in that order.
 * ============================================================================================= */
void start(uint8_t *image) {
    init_system(image);
    init_game(image);
    /* title_screen(image); init_video(image); then the per-frame loop, for ever. */
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * Nothing in this layer takes a stack frame — each routine works entirely off globals and the
 * modeled OS state — so every g_* below is a bare forwarder bar the two title-screen ones. The one
 * result an image diff cannot see (the table xbios_setpalette hands the trap) comes back as a
 * return value, exactly as g_flash_hiscore_color's colour word does, and the test compares it
 * against what the oracle really pushed.
 */

void g_init_system(uint8_t *image) { init_system(image); }

void g_init_video(uint8_t *image) { init_video(image); }

void g_init_game(uint8_t *image) { init_game(image); }

void g_start(uint8_t *image) { start(image); }

uint32_t g_xbios_setpalette(uint8_t *image) { return xbios_setpalette(image); }

void g_cycle_palette(uint8_t *image) { cycle_palette(image); }

/* THE FIRST GLUE HERE THAT IS NOT A BARE FORWARDER: it stops where every oracle run must stop.
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

/* Both packet bytes must be readable, so the last address the routine touches is packet + 1. */
#define IKBD_PACKET_BYTES 2u

uint32_t g_title_ikbd_pass(uint8_t *image) {
    uint32_t packet = be32(image + A_ikbd_packet);
    if (packet == 0 || packet > OS_IMAGE_SIZE - IKBD_PACKET_BYTES) return TITLE_PASS_REFUSED;
    return title_ikbd_pass(image);
}
