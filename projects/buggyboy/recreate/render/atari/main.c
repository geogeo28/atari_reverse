/* main.c — Atari GEMDOS shim that runs the reconstructed leg-results screen on a real 68000.
 *
 * Mirrors render/render_screen.py, but on-target: build the flat game image in BSS, load the
 * static PRG data (STATIC.BIN) + graphics (GRAPHICS.GRA) off the mounted drive, set the buffer
 * pointers, run the *verified* g_unpack_graphics then g_draw_leg_results, copy the painted
 * framebuffer to the physical screen, load a (placeholder) palette, and wait for a key.
 *
 * The cores are unchanged: they operate on `image + offset`, never on absolute addresses baked
 * into the binary, so nothing here depends on where TOS loads us. See render/atari/README.md.
 */
#include <stdint.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define IMAGE_SIZE  0x100000        /* 1 MiB, matches the host image (loader.py) */

/* Buffer layout, exactly as `main` computes it off the big block (see render_screen.py). */
#define MEM_BASE    0x20000
#define BUF_A       (MEM_BASE + 0x1900)
#define BUF_B       (MEM_BASE + 0xf660)
#define BUF_C       (MEM_BASE + 0x1c660)
#define BUF_AUX     (MEM_BASE + 0x57000)
#define GFX_LOAD_OFFSET  0xc350
#define SCREEN_BASE 0x2000          /* free zeroed region below LOAD_BASE; the draw buffer */

#define STATIC_LO   0x10000         /* where STATIC.BIN (relocated PRG data) lands in the image */
#define STATIC_LEN  0xc000
#define SCREEN_BYTES 32000

static uint8_t image[IMAGE_SIZE];   /* BSS: TOS zeroes it at load */

/* Placeholder 16-colour palette (ST 0x0RGB, 3 bits/channel). RGB is not the game's — the real
 * palette is set by a Setpalette call we haven't reconstructed — but the pixel indices are, so
 * distinct legible hues make the screen's structure readable. Mirrors render_screen.py's PALETTE. */
static const uint16_t PALETTE[16] = {
    0x000, 0x777, 0x700, 0x070, 0x007, 0x077, 0x707, 0x770,
    0x555, 0x740, 0x744, 0x474, 0x447, 0x030, 0x300, 0x333,
};

extern long Fopen(const char *name, short mode);
extern long Fread(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Fcreate(const char *name, short attr);
extern long Fwrite(short handle, long count, void *buf);
extern long Cconin(void);
extern long Physbase(void);
extern void Setpalette(const void *pal16);

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

/* Read a whole file into image+dst; returns bytes read, or -1 if it won't open. */
static long load_file(const char *name, uint32_t dst, long max) {
    long h = Fopen(name, 0);
    if (h < 0) return -1;
    long n = Fread((short)h, max, image + dst);
    Fclose((short)h);
    return n;
}

void main(void) {
    load_file("STATIC.BIN", STATIC_LO, STATIC_LEN);              /* fonts, labels, fill patterns */
    load_file("GRAPHICS.GRA", BUF_C + GFX_LOAD_OFFSET, 0x40000); /* the packed graphics */

    wr32(image + A_buf_aux, BUF_AUX);
    wr32(image + A_buf_a, BUF_A);
    wr32(image + A_buf_b, BUF_B);
    wr32(image + A_buf_c, BUF_C);
    wr16(image + A_flip_idx, 0);
    wr32(image + A_physbase_tbl, SCREEN_BASE);
    wr16(image + A_leg_index, 0);

    g_unpack_graphics(image);       /* decode GRAPHICS.GRA -> buf_c tables (verified) */
#ifdef DEMO_RESULTS
    /* Demo state for the results screen (must match render_screen.py RESULTS_MODE/RESULTS_POS). */
    wr16(image + A_results_mode, 0);
    wr16(image + A_hiscore_pos, 5);
    g_draw_results_screen(image);   /* paint the race-end results screen (verified) */
#else
    g_draw_leg_results(image);      /* paint the leg-results screen (verified) */
#endif

    /* Dump the painted framebuffer to the drive so a headless run can be verified off-target. */
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) {
        Fwrite((short)h, SCREEN_BYTES, image + SCREEN_BASE);
        Fclose((short)h);
    }

    Setpalette(PALETTE);
    memcpy((void *)Physbase(), image + SCREEN_BASE, SCREEN_BYTES);
    Cconin();                       /* hold the screen until a key is pressed */
}
