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
 *   headless game, peeked at by Bconstat and consumed by Bconin, exactly as a real key is. */
void          shim_psg_written(void);
void          shim_console_polled(void);
int           shim_console_pending(void);
unsigned long shim_console_take(void);

/* ---- BIOS console (Bconstat 0x01 / Bconin 0x02) --------------------------------------------- */

static inline int os_bconstat(const uint8_t *mem, uint16_t dev, uint32_t *out) {
    (void)mem;
    shim_console_polled();
    *out = (uint32_t)Bconstat((short)dev);
    if (*out == 0 && shim_console_pending()) *out = OS_BCONSTAT_READY;
    return 1;
}

static inline int os_bconin(uint8_t *mem, uint16_t dev, uint32_t *out) {
    (void)mem;
    /* A real key always wins: the scripted one is only offered when TOS has nothing waiting. */
    if (Bconstat((short)dev) == 0 && shim_console_pending()) {
        *out = (uint32_t)shim_console_take();
        return 1;
    }
    *out = (uint32_t)Bconin((short)dev);   /* real TOS; every caller gates on Bconstat first */
    return 1;
}

/* ---- GEMDOS Super (0x20) — the shim owns the privilege switch, so this only hands the token back
 * the model does. Every call site in Joust drops the result (init_system's `addq.l #6,a7`). */
static inline int os_super(uint32_t arg, uint32_t *out) {
    (void)arg;
    *out = OS_SUPER_TOKEN;
    return 1;
}

/* ---- XBIOS Giaccess (0x1c) — the real YM2149. A write is bit 7 of `reg`; a read returns the
 * register byte, which is exactly what snd_poll_done polls for silence. */
static inline uint32_t os_giaccess(uint8_t *mem, uint16_t data, uint16_t reg) {
    (void)mem;
    if (reg & OS_PSG_WRITE) shim_psg_written();
    return (uint32_t)Giaccess((short)data, (short)reg);
}

/* ---- XBIOS Random (0x11) — masked exactly as the model does, so init_game's `andi.l #$fe` seed
 * sees the same 24-bit shape it does under the differential. */
static inline uint32_t os_random(const uint8_t *mem) {
    (void)mem;
    return (uint32_t)Random() & OS_RANDOM_MASK;
}

#endif /* JOUST_TARGET_OS_H */
