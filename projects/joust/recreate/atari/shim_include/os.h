/* os.h — the ON-TARGET TOS layer, shadowing the kit's deterministic model for the PRG build only.
 *
 * The verified cores call the kit's `os_*` helpers directly, and those are `static inline` in
 * tools/recreate_kit/include/os.h — there is no link-time seam to override (unlike g_dosound, which
 * is a real symbol). So the seam is the INCLUDE PATH: build.sh puts this directory ahead of the
 * kit's, every core that says `#include "os.h"` gets this file, and this file pulls the kit's in
 * through `#include_next` for everything it does NOT replace. The differential build never sees
 * this directory, so the .so is byte-identical and the suite stays green.
 *
 * WHAT IS REPLACED, and why each one has to be:
 *   Bconstat / Bconin  the console is a real keyboard here, not a poked image word
 *   Giaccess           the YM2149 is a real chip, not an in-image register file
 *   Random             a real XBIOS Random, so init_game's rng seed is not a constant
 *   Super              a NO-OP: joust_main.c owns the privilege switch (see below)
 *
 * WHAT IS DELIBERATELY KEPT — the staged-file model (os_fopen/os_fread/os_fwrite/os_fclose). Joust
 * opens HIGH.SCO from inside init_system, which the original runs in SUPERVISOR mode, and GEMDOS
 * handle allocation misbehaves when entered from supervisor under Hatari's GEMDOS drive (BuggyBoy
 * shipped that bug: see projects/buggyboy/recreate/render/atari/game_os.s). Keeping the model means
 * the cores' file calls are pure image operations with no privilege requirement at all, and the
 * shim does the one real Fread (into the staging area) in user mode before the game starts and the
 * one real Fwrite (out of it) after the game ends. Same bytes, no trap in the middle.
 *
 * PRIVILEGE. os_super returns the model's token without trapping, because entering supervisor from
 * inside a core would strand the shim's own balanced Super()/Super() pairs. joust_main.c switches
 * once, after all GEMDOS file I/O, exactly where the original's init_system does.
 */
#ifndef JOUST_TARGET_OS_H
#define JOUST_TARGET_OS_H

#include "tos.h"

/* Move the kit's modelled versions of the five replaced helpers aside, then pull in the kit's
 * header for EVERYTHING else: the constants, the staged-file model, os_in_image, os_refused. */
#define os_bconstat os_model_bconstat
#define os_bconin   os_model_bconin
#define os_super    os_model_super
#define os_giaccess os_model_giaccess
#define os_random   os_model_random
#include_next "os.h"
#undef os_bconstat
#undef os_bconin
#undef os_super
#undef os_giaccess
#undef os_random

/* ---- the shim's own hooks into the OS layer -------------------------------------------------
 * Two things the shim can only learn from inside a core's OS call, because `start()` never returns
 * and calls nothing else the shim owns. Both are defined in joust_main.c.
 *
 * shim_psg_written()  — the FIRST Giaccess WRITE in a run is snd_tone_sweep's channel-C mute, and
 *   snd_tone_sweep is called from one place only: the end of init_video, i.e. immediately after
 *   title_screen has returned. It is therefore an exact marker for "the title screen is over", and
 *   the VBL palette pusher uses it to swap title_palette for game_palette. (play_sound reaches the
 *   chip through Dosound, and snd_poll_done only READS register 7, so no other path can fire it.)
 * shim_console_polled() — one poll_quit_key per frame is the only Bconstat during play, so once
 *   the title is over this counts FRAMES for the SMOKE build's dump-and-terminate.
 * shim_console_pending() / shim_console_take() — SMOKE only: the scripted keystroke that starts the
 *   headless game, peeked at by Bconstat and consumed by Bconin, exactly as a real key is.
 * shim_console_key() — the shim watching the keys the game is handed, so it can finish the exits
 *   the reconstruction reports through a result code `start()` drops (Ctrl-C, R). See joust_main.c.
 * shim_check_exit() — ...and the point at which one of those is acted on. It is called at the TOP of
 *   every seam below, because `start()` never returns and these calls are the only places the shim
 *   gets control back. `at_console_poll` tells it which seam it is: a Ctrl-C that reaches a second
 *   console poll without quit_to_desktop having run is one the game IGNORED (the high-score entry
 *   loop does), and only then does the shim quit on the game's behalf.
 *
 *   THE FILE HELPERS MUST NEVER GAIN THIS HOOK. os_fopen/os_fwrite/os_fclose are the kit's, kept
 *   verbatim (below), and quit_to_desktop calls all three THROUGH save_hiscore while the shim is
 *   already in QUIT_TAIL_RUNNING. A hook there would fire shim_quit() in the middle of the record
 *   being written and the write-back would go out truncated, or not at all. The exit is meant to
 *   land after the tail has RETURNED, which is what makes every hook here a call the tail does not
 *   make. If a file helper ever has to be shadowed for some other reason, leave the hook out.
 *
 *   AND g_dosound IS THE TAIL'S SIGNAL because nothing else can beat it to it: both readers that
 *   act on Ctrl-C (poll_quit_key and title_screen's attract pass) test the key and call
 *   quit_to_desktop in the same statement, and quit_to_desktop's FIRST act is the Dosound silence —
 *   so no other Dosound can occur between the key and that one. check_highscore's entry loop, the
 *   one reader that ignores the key, issues none at all, which is why the second console poll is a
 *   safe way to recognise it. A new caller of g_dosound between a console read and quit_to_desktop
 *   would break the scheme. */
void          shim_psg_written(void);
void          shim_console_polled(void);
int           shim_console_pending(void);
unsigned long shim_console_take(void);
void          shim_console_key(unsigned long console);
/* THE HOOK IS AN INLINE FLAG TEST, and it has to be: os_giaccess is called ~14,450 times by
 * init_video's boot sweep alone, so an out-of-line `jsr` here cost ~1.9 M cycles — about a quarter
 * of a second at 8 MHz, on every boot and again on every restart. The flag is set only by
 * shim_console_key, so the common case is `tst.l` + `beq` and the real work stays in
 * shim_take_exit(). `volatile` because the flag is read in the seam and written elsewhere. */
extern volatile int shim_exit_armed;
void          shim_take_exit(int at_console_poll);

static inline void shim_check_exit(int at_console_poll) {
    if (shim_exit_armed) shim_take_exit(at_console_poll);
}
/* init_game's XBIOS Random is the one trap it makes, and init_game IS the original's RESTART_ENTRY
 * (_start+6) — so this call is exactly where a restarted run resumes. joust_main.c uses it to put
 * back the two pieces of state re-entering `start()` would clobber and the original's restart never
 * touches, because the original skips init_system on the way back in. */
void          shim_init_game_started(void);

/* ---- BIOS console (Bconstat 0x01 / Bconin 0x02) --------------------------------------------- */

#define SHIM_AT_CONSOLE_POLL 1
#define SHIM_AT_OTHER_SEAM   0

static inline int os_bconstat(const uint8_t *mem, uint16_t dev, uint32_t *out) {
    (void)mem;
    shim_check_exit(SHIM_AT_CONSOLE_POLL);
    shim_console_polled();
    *out = (uint32_t)Bconstat((short)dev);
    if (*out == 0 && shim_console_pending()) *out = OS_BCONSTAT_READY;
    return 1;
}

static inline int os_bconin(uint8_t *mem, uint16_t dev, uint32_t *out) {
    (void)mem;
    shim_check_exit(SHIM_AT_OTHER_SEAM);
    /* A real key always wins: the scripted one is only offered when TOS has nothing waiting. */
    if (Bconstat((short)dev) == 0 && shim_console_pending())
        *out = (uint32_t)shim_console_take();
    else
        *out = (uint32_t)Bconin((short)dev);  /* real TOS; every caller gates on Bconstat first */
    shim_console_key(*out);
    return 1;
}

/* ---- GEMDOS Super (0x20) — the shim owns the privilege switch, so this only hands the token back
 * the model does. Every call site in Joust drops the result (init_system's `addq.l #6,a7`). */
static inline int os_super(uint32_t arg, uint32_t *out) {
    (void)arg;
    shim_check_exit(SHIM_AT_OTHER_SEAM);
    *out = OS_SUPER_TOKEN;
    return 1;
}

/* ---- XBIOS Giaccess (0x1c) — the real YM2149. A write is bit 7 of `reg`; a read returns the
 * register byte, which is exactly what snd_poll_done polls for silence. */
static inline uint32_t os_giaccess(uint8_t *mem, uint16_t data, uint16_t reg) {
    (void)mem;
    shim_check_exit(SHIM_AT_OTHER_SEAM);
    if (reg & OS_PSG_WRITE) shim_psg_written();
    return (uint32_t)Giaccess((short)data, (short)reg);
}

/* ---- XBIOS Random (0x11) — masked exactly as the model does, so init_game's `andi.l #$fe` seed
 * sees the same 24-bit shape it does under the differential. */
static inline uint32_t os_random(const uint8_t *mem) {
    (void)mem;
    shim_check_exit(SHIM_AT_OTHER_SEAM);
    shim_init_game_started();
    return (uint32_t)Random() & OS_RANDOM_MASK;
}

#endif /* JOUST_TARGET_OS_H */
