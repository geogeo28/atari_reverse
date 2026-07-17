/* game_main.c — playable BuggyBoy: run the verified C reconstruction as a real GEMDOS .PRG.
 *
 * The reconstructed cores (recreate/src/) ARE the whole game — the attract/leg-select/race loop
 * lives in g_intermission / g_init_playfield and the per-frame pipeline. Only the cores'
 * hardware-boundary glue is a no-op in the differential harness (its effect is hardware the oracle
 * models elsewhere). This file supplies the real hardware for that boundary and mirrors the
 * original main() @0x10100: build the image, load + unpack graphics, set up double-buffering, wire
 * the IKBD joystick + the VBL sound driver, then run the game loop.
 *
 * Runs entirely in supervisor mode (Super(0) once) so it can reach the video shifter, the YM2149
 * and the IKBD ACIA directly. See render/atari/README.md + the memory note buggyboy-playable-prg-design.
 */
#include <stdint.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define IMAGE_SIZE   0x100000       /* 1 MiB, matches the host image (loader.py) */
#define MEM_BASE     0x20000        /* the big work block, inside the image (matches render_screen) */
#define BUF_AUX      (MEM_BASE + 0x57000)
#define BUF_A        (MEM_BASE + 0x1900)
#define BUF_B        (MEM_BASE + 0xf660)
#define BUF_C        (MEM_BASE + 0x1c660)
#define GFX_LOAD_OFF 0xc350
#define STATIC_LO    0x10000        /* relocated PRG static data (fonts, strings, palettes) */
#define STATIC_LEN   0xc000
#define COURSES_LEN  0xf660
#define GRAPHICS_LEN 0x40000
#define SCREEN_BYTES 32000

/* Two 256-aligned draw buffers in free image regions (below STATIC, above the graphics), referenced
 * by physbase_tbl[flip_idx] (flip_idx = 0 or 4). The image itself is 256-aligned so image+offset is
 * a valid ST video base. */
#define DRAW_BUF_0   0x00100
#define DRAW_BUF_1   0x88000

/* ---- ST hardware (reached directly; we run supervisor) ---- */
#define VID_BASE_HI   (*(volatile uint8_t *)0xffff8201ul)   /* video base bits 23..16 */
#define VID_BASE_MID  (*(volatile uint8_t *)0xffff8203ul)   /* video base bits 15..8 (256-aligned) */
#define PSG_SELECT    (*(volatile uint8_t *)0xffff8800ul)   /* YM2149 register-select port */
#define PSG_WRITE     (*(volatile uint8_t *)0xffff8802ul)   /* YM2149 data-write port */
#define ACIA_STATUS   (*(volatile uint8_t *)0xfffffc00ul)   /* IKBD ACIA status (bit1 = Tx ready) */
#define ACIA_DATA     (*(volatile uint8_t *)0xfffffc02ul)   /* IKBD ACIA data */
#define ACIA_TDRE     0x02
#define SYS_NVBLS     (*(volatile int16_t *)0x454ul)        /* VBL-queue length */
#define SYS_VBLQUEUE  (*(volatile uint32_t *)0x456ul)       /* -> array of VBL routine pointers */
#define KBDV_JOYVEC   0x18                                  /* KBDVBASE offset: joystick-packet vector */
#define KBDV_MOUSEVEC 0x10                                  /* KBDVBASE offset: mouse-packet vector */
#define IKBD_INTERROGATE 0x16                               /* IKBD "report joystick now" command */

extern long Super(void *stack);
extern long Malloc(long amount);
extern long Crawio(short w);
extern long Fopen(const char *name, short mode);
extern long Fread(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Physbase(void);
extern void Vsync(void);
extern void Setpalette(const void *pal16);
extern long Kbdvbase(void);
extern void joy_handler(void);      /* asm joyvec handler: IKBD packet -> input_state */

/* joy_handler needs the image address of input_state (it is entered off the C ABI). */
uint8_t *input_state_ptr;

static uint8_t image[IMAGE_SIZE] __attribute__((aligned(256)));   /* BSS: TOS zeroes it at load */

/* Our VBL queue: one entry, the sound driver. A function-pointer initializer in .data becomes an
 * R_68K_32 reloc that mkprg fixes up at load, so this points at the real vbl_handler address. */
static void vbl_handler(void);
void (*vbl_queue[1])(void) = { vbl_handler };

/* freestanding libc the cores need (we link -nostdlib) */
void *memcpy(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    while (n--) *dp++ = *sp++;
    return d;
}
void *memmove(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    if (dp <= sp) { while (n--) *dp++ = *sp++; }
    else { dp += n; sp += n; while (n--) *--dp = *--sp; }
    return d;
}
void *memset(void *d, int c, unsigned long n) {
    uint8_t *dp = d;
    while (n--) *dp++ = (uint8_t)c;
    return d;
}

static long load_file(const char *name, uint32_t dst, long max) {
    long h = Fopen(name, 0);
    if (h < 0) return -1;
    long n = Fread((short)h, max, image + dst);
    Fclose((short)h);
    return n;
}

/* Progress beacon: drop a marker file B<n> on the GEMDOS drive at each init step, so a headless
 * run can pinpoint a hang by the highest-numbered marker present (no debugger needed). SMOKE only. */
#ifdef SMOKE
extern long Fcreate(const char *name, short attr);
extern long Fclose(short handle);
extern long Fwrite(short handle, long count, void *buf);
static void beacon(int n) {
    char name[4] = { 'B', (char)('0' + n), 0, 0 };
    long h = Fcreate(name, 0);
    if (h >= 0) Fclose((short)h);
}
#define BEACON(n)  beacon(n)
#else
#define BEACON(n)  ((void)0)
#endif

/* Set once we enter supervisor mode; gates all direct hardware access (video shifter, YM2149, IKBD
 * ACIA — all in privileged $ffff8xxx/$fffffcxx). Before that (file load, unpack, SMOKE render) the
 * hardware pokes are skipped so a user-mode access can't bus-error. */
static int hw_ready;

/* Send one command byte to the IKBD (busy-wait the ACIA transmit-ready bit, bounded so a hardware
 * quirk can't hang the game forever). The ACIA lives in the supervisor-only $fffffcxx region, so
 * this is a no-op until we are in supervisor (hw_ready) — before that there is no input to poll. */
static void ikbd_send(uint8_t b) {
    if (!hw_ready) return;
    for (uint32_t spin = 0; spin < 100000; spin++)
        if (ACIA_STATUS & ACIA_TDRE) break;
    ACIA_DATA = b;
}

/* ---- VBL sound driver: TOS calls this every 50 Hz vertical blank (supervisor) ---- */
static void vbl_handler(void) {
    if (be32(image + A_vbl_sound_vec) != A_refresh) return;   /* stop_music parks the vec at an rts */
    uint8_t reg[16], val[16];
    uint16_t n = (uint16_t)g_REFRESH(image, reg, val, sizeof reg);
    for (uint16_t i = 0; i < n; i++) { PSG_SELECT = reg[i]; PSG_WRITE = val[i]; }
}

/* ---- hardware-boundary overrides of the cores' no-op glue (weak in the .so) ---- */

/* flip_screen @0x121f8 — point the ST video shifter at the buffer the cores just drew
 * (image[physbase_tbl[flip_idx]]), Vsync so it latches for the whole next frame, then toggle
 * flip_idx (the sole image effect the harness verified). The video-base poke lives in the
 * supervisor-only $ffff8xxx region, so it is gated on hw_ready (set once we are in supervisor);
 * before that (file load / unpack, and the SMOKE render) only the flip_idx toggle happens. */
void g_flip_screen(uint8_t *img) {
    uint16_t flip_idx = be16(img + A_flip_idx);
    if (hw_ready) {
        uint32_t base = (uint32_t)(img + be32(img + A_physbase_tbl + flip_idx));
        VID_BASE_MID = (uint8_t)(base >> 8);
        VID_BASE_HI  = (uint8_t)(base >> 16);
        Vsync();
    }
    wr16(img + A_flip_idx, (uint16_t)((flip_idx + 4) & 4));
}

/* wait_vbl_set_offset @0x102ee — 51 Vsyncs, then set the road-scroll offset (the image effect). */
void g_wait_vbl_set_offset(uint8_t *img) {
    for (int i = 0; i < 51; i++) Vsync();
    g_set_screen_offset(img);
}

/* xbios_setpalette @0x12eb0 — load the 16 colour registers from the image palette. */
void g_xbios_setpalette(uint8_t *img, uint32_t palette_ptr) { Setpalette(img + palette_ptr); }

/* xbios_setscreen @0x12226 — no-op: we manage the video base ourselves in g_flip_screen. */
void g_xbios_setscreen(uint8_t *img) { (void)img; }

/* set_rez @0x120f8 — the original's misnamed "send an IKBD command byte" (D0.b -> IKBD via XBIOS
 * Ikbdws). Store the observable config byte, then send it to the chip. */
void g_set_rez(uint8_t *img, uint32_t mode) {
    img[A_setrez_mode] = (uint8_t)mode;
    ikbd_send((uint8_t)mode);
}

/* read_joystick @0x12110 — interrogate the IKBD joystick; the reply arrives asynchronously and the
 * joyvec handler copies it into input_state (one frame of latency, exactly as the original). */
void g_read_joystick(uint8_t *img) { (void)img; ikbd_send(IKBD_INTERROGATE); }

/* install_handlers @0x12124 — Kbdvbase() then patch the joystick vector to our handler (and the
 * mouse vector to a harmless rts) so IKBD joystick packets land in input_state. */
void g_install_handlers(uint8_t *img) {
    uint32_t kbdvbase = (uint32_t)Kbdvbase();
    wr32(img + A_kbdvbase, kbdvbase);
    *(volatile uint32_t *)(uintptr_t)(kbdvbase + KBDV_JOYVEC) = (uint32_t)joy_handler;
}

/* load_graphics @0x12166 — read the two data files into the image, then unpack the graphics. */
void g_load_graphics(uint8_t *img) {
    load_file("COURSES.DAT", MEM_BASE, COURSES_LEN);
    load_file("GRAPHICS.GRA", BUF_C + GFX_LOAD_OFF, GRAPHICS_LEN);
    g_unpack_graphics(img);
}

/* ---- the game (mirrors main @0x10100) ---- */
void game_main(void) {
    /* Phase 1 — user mode: all GEMDOS file I/O. (GEMDOS handle allocation misbehaves if entered
     * from supervisor, so we must load + unpack the graphics before Super(0).) */
    input_state_ptr = image + A_input_state;

    load_file("STATIC.BIN", STATIC_LO, STATIC_LEN);   /* fonts, strings, palettes */
    wr32(image + A_buf_aux, BUF_AUX);
    wr32(image + A_mem_base, MEM_BASE);
    wr32(image + A_buf_a, BUF_A);
    wr32(image + A_buf_b, BUF_B);
    wr32(image + A_buf_c, BUF_C);

    /* Double buffer: two draw buffers, referenced by physbase_tbl[flip_idx] (flip_idx = 0 or 4).
     * The ST video shifter can only display from a 256-byte-aligned base (it ignores the low 8
     * address bits), so the buffers' RUNTIME addresses must be 256-aligned — the load address of
     * `image` is whatever GEMDOS chose (not 256-aligned), so we can't rely on the array alignment.
     * Store each entry as an offset whose `image + offset` is rounded up to a 256 boundary. */
    wr16(image + A_flip_idx, 0);
    uint32_t base = (uint32_t)image;
    uint32_t buf0 = ((base + DRAW_BUF_0 + 0xff) & ~0xffu) - base;   /* 256-aligned screen buffers */
    uint32_t buf1 = ((base + DRAW_BUF_1 + 0xff) & ~0xffu) - base;
    wr32(image + A_physbase_tbl + 0, buf0);
    wr32(image + A_physbase_tbl + 4, buf1);

    load_file("COURSES.DAT", MEM_BASE, COURSES_LEN);
    long gra_n = load_file("GRAPHICS.GRA", BUF_C + GFX_LOAD_OFF, GRAPHICS_LEN);
    BEACON(8);                      /* files loaded, about to unpack */
#ifdef SMOKE
    {   /* dump the loaded byte count + the RLE source window, to compare against the host loader */
        extern long Fcreate(const char *name, short attr);
        extern long Fwrite(short handle, long count, void *buf);
        long h = Fcreate("GRAN.BIN", 0);
        if (h >= 0) { Fwrite((short)h, 4, &gra_n); Fclose((short)h); }
        h = Fcreate("RLESRC.BIN", 0);
        if (h >= 0) { Fwrite((short)h, 64, image + BUF_C + 0xd050); Fclose((short)h); }
    }
#else
    (void)gra_n;
#endif
    g_unpack_graphics(image);
    BEACON(1);                      /* unpack done */

    /* Phase 2 — supervisor: from here on we touch the video shifter / YM2149 / IKBD directly.
     * The SMOKE build stays in user mode: it renders into the image buffer and dumps it via GEMDOS
     * (which needs user mode), and its flip is a no-op (hw_ready stays 0) — no hardware needed. */
#if !defined(SMOKE) && !defined(SMOKE_NOSUPER)
    Super(0);
    hw_ready = 1;
#endif

#ifndef SMOKE
    /* IKBD joystick setup: same command sequence the original issues (disable auto joystick/mouse
     * reporting, then interrogation mode), install the joystick vector, prime one interrogate. */
    g_set_rez(image, 0x1a);         /* disable joystick auto-report */
    g_set_rez(image, 0x08);         /* relative mouse mode */
    g_install_handlers(image);
    g_set_rez(image, 0x12);         /* disable mouse */
    g_set_rez(image, 0x15);         /* joystick interrogation mode */
    g_read_joystick(image);
    BEACON(2);

    /* Install the VBL sound driver (mirrors main writing REFRESH into _vblqueue). */
    wr32(image + A_vbl_sound_vec, A_refresh);
    SYS_NVBLS = 0;
    SYS_VBLQUEUE = (uint32_t)(uintptr_t)vbl_queue;
    SYS_NVBLS = 1;
    BEACON(3);
#endif

    g_init_scoretable(image);       /* default high-score table */
    BEACON(4);

#ifdef SMOKE
    /* Headless smoke test: skip the leg-select wait (no fire is pressed under a scripted run), force
     * leg 0, run a fixed number of race frames, dump the drawn framebuffer, and terminate — so a
     * headless Hatari run proves the whole init + render pipeline works on a real 68000. */
    extern long Fwrite(short handle, long count, void *buf);
    wr16(image + A_leg_index, 0);

#ifdef SMOKE_LEG
    /* Leg-select variant: draw exactly what the host render_leg_results produces (deterministic,
     * no game state), dump it, and terminate — for a byte-exact draw-vs-host comparison. */
    g_init_leg_dash(image);
    g_draw_leg_results(image);
    {
        uint32_t buf = be32(image + A_physbase_tbl + be16(image + A_flip_idx));
        long h = Fcreate("SCREEN.BIN", 0);
        if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, image + buf); Fclose((short)h); }
    }
    return;
#endif
    g_init_leg(image);
    g_draw_frame(image);
    g_xbios_setpalette(image, A_race_palette);
    g_flip_screen(image);
    for (int f = 0; f < SMOKE; f++) {
        g_game_update(image);
        g_render_road(image);
        g_blit_road_scroll(image);
        g_draw_game_objects(image);
        g_draw_hud(image);
        g_flip_screen(image);
    }
    {
        uint16_t drawn = be16(image + A_flip_idx);           /* the just-flipped buffer is the OTHER one */
        uint32_t buf = be32(image + A_physbase_tbl + ((drawn + 4) & 4));
        long h = Fcreate("SCREEN.BIN", 0);
        if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, image + buf); Fclose((short)h); }
    }
    SYS_NVBLS = 0;                  /* detach the VBL handler before we terminate */
    return;
#endif

    for (;;) {                      /* outer loop @0x101f4 */
        g_init_playfield(image);    /* attract demo + leg-select; returns when a leg is started */
        g_init_leg(image);          /* reset per-leg state */
        g_draw_frame(image);
        g_xbios_setpalette(image, A_race_palette);
        g_flip_screen(image);
        g_draw_frame(image);
        g_flip_screen(image);

        g_stop_music(image); g_wait_vbl_set_offset(image);   /* four settle frames @0x226..0x254 */
        g_stop_music(image); g_wait_vbl_set_offset(image);
        g_stop_music(image); g_wait_vbl_set_offset(image);
        g_stop_music(image); g_wait_vbl_set_offset(image);

        for (;;) {                  /* per-frame race loop @0x254 */
            g_game_update(image);
            g_render_road(image);
            g_blit_road_scroll(image);
            g_draw_game_objects(image);
            g_draw_hud(image);
            g_flip_screen(image);

            if ((int16_t)be16(image + A_abort_flag) < 0) break;   /* crash/abort countdown done */
            long key = Crawio((short)0xff) & 0xff;                /* non-blocking key poll */
            if (key == 0x1b) break;                               /* ESC quits the leg */
            if (key) wr16(image + A_last_key, (uint16_t)key);     /* feed read_input's fallback */
        }

        g_update_highscore(image);
        wr16(image + A_game_over_flag, (uint16_t)(be16(image + A_game_over_flag) + 1));
        g_intermission(image);      /* between-legs attract screen */
        wr16(image + A_game_over_flag, 0);
    }
}
