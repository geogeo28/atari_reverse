/* joust_main.c — run the verified Joust reconstruction as a real GEMDOS .PRG.
 *
 * The reconstructed cores (../src/) ARE the whole game: `start()` (src/init.c) is the original's
 * _start, init chain and per-frame loop, all 75 functions. This file supplies only the hardware
 * boundary the differential harness models — and, because the harness models several of those calls
 * as having no image effect at all, it also supplies the handful of ACTIONS the reconstruction was
 * verified WITHOUT (the IKBD interrogate, the palette loads). ../atari/README.md lists every one.
 *
 * Its three jobs, in order:
 *   1. build the image — the cores address the game as `image + <Ghidra address>`, so the PRG's own
 *      pre-relocated text+data (tables, sprites, fonts, strings, the title picture) is read in at
 *      IMAGE_LOAD_BASE from JOUST.IMG (gen_image.py), and HIGH.SCO is staged into the kit's
 *      in-image file table;
 *   2. wire the hardware — screen, palette, IKBD;
 *   3. call start(), which never returns.
 *
 * PRIVILEGE. The original runs the whole game in supervisor mode. This build stays in USER mode and
 * takes supervisor only in balanced Super(0)/Super(ssp) pairs around the three privileged pokes
 * (KBDVBASE vectors, the conterm byte, the VBL queue). The cores themselves never touch privileged
 * space — every hardware access they make goes through a TOS trap — so nothing is lost, and staying
 * in user mode keeps GEMDOS handle allocation sane (a supervisor Fopen hands back handle 0 under
 * Hatari's GEMDOS drive: see projects/buggyboy/recreate/render/atari/game_os.s).
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"      /* ../atari/shim_include/os.h — the real-TOS shadow, which pulls the kit's in */
#include "tos.h"

#include "init.h"    /* start(), and (through its own includes) every A_* the shim needs */

#define IMAGE_SIZE      0x100000u   /* 1 MiB, matching project.toml's image_size */
#define PALETTE_PENS    16u         /* the ST's 16 hardware colour registers */

/* JOUST.IMG's length — the pre-relocated program, [0x10000, 0x2b7ae). build.sh passes the length
 * of the blob gen_image.py just wrote, so the two cannot drift; the load below insists on exactly
 * that many bytes, since a short read leaves the cores reading zeroes for a table. */
#ifndef PROGRAM_BYTES
#error "build.sh must define PROGRAM_BYTES as the byte length of the staged JOUST.IMG"
#endif

/* The console keys the shim watches for, and the ones build.sh's scripted console types. Ctrl-C is
 * the reconstruction's own KEY_CTRL_C (../include/input.h), which is in scope here and is shared for
 * the reason that header gives — poll_quit_key and title_screen must agree on it, and now the shim
 * must too. The other two are file-local to their cores and cannot be included: KEY_RESTART_* are
 * src/input.c's poll_quit_key keys and KEY_ONE_PLAYER is src/init.c's TITLE_KEY_ONE_PLAYER. Hoisting
 * them into a shared header is the real fix and is an INTEGRATOR'S change to a verified layer —
 * ../include/init.h already prescribes exactly that for its own second spellings — so it is reported
 * rather than taken here. build.sh passes these NAMES, not the bytes, so the scripted console and
 * the watcher cannot drift from each other. */
#define KEY_RESTART_UPPER 0x52u   /* 'R' — src/input.c */
#define KEY_RESTART_LOWER 0x72u   /* 'r' */
#define KEY_ONE_PLAYER    0x31u   /* '1' — src/init.c's TITLE_KEY_ONE_PLAYER */

/* Where the IKBD handler leaves the two joystick bytes. A free low-image slot: above the kit's
 * modelled KBDVBASE (0x500) and console state (0x600..0x61f), below the framebuffer at
 * OS_SCREEN_BASE (0x8000). ikbd_packet holds this OFFSET, which is what the cores dereference. */
#define JOY_PACKET_BUF  0x700u

/* HIGH.SCO's slot in the kit's staged-file table. os_fwrite refuses a write past the capacity, so
 * it is sized well clear of the 26-byte record the quit path writes back. */
#define HIGHSCO_NAME     "HIGH.SCO"
#define HIGHSCO_OPEN_RDWR 2   /* GEMDOS Fopen mode 2, as src/input.c's save_hiscore uses */
#define HIGHSCO_SLOT     0
#define HIGHSCO_CAPACITY 0x100u

/* ---- ST hardware and TOS variables reached directly (supervisor: the VBL handler, or a Super
 * pair). All of $fffffcxx and the low system variables are privileged. */
#define ACIA_STATUS      (*(volatile uint8_t *)0xfffffc00ul)  /* IKBD ACIA; bit 1 = Tx ready */
#define ACIA_DATA        (*(volatile uint8_t *)0xfffffc02ul)
#define ACIA_TDRE        0x02
#define SYS_NVBLS        (*(volatile int16_t *)0x454ul)       /* VBL-queue length */
#define SYS_VBLQUEUE     (*(volatile uint32_t *)0x456ul)      /* -> array of VBL routine pointers */
#define SYS_COLORPTR     (*(volatile uint32_t *)0x45aul)      /* 16 pens for TOS's VBL to load */
#define SYS_CONTERM      (*(volatile uint8_t *)0x484ul)       /* TOS: bell / key click / scancode */

/* The IKBD commands the shim issues on the reconstruction's behalf; both bytes are the GAME'S
 * own, read out of the image. ikbd_cmd_joymode ($15) puts the sticks in interrogation mode and
 * ikbd_cmd_joyread ($16) asks for one reply — neither trap has an image effect, so neither is in
 * the reconstruction. This copy of $16 is for joust_os.s's chain, which cannot read the image. */
#define IKBD_INTERROGATE          0x16
#define IKBD_ONE_BYTE             0   /* Ikbdws takes count - 1 */
#define IKBD_TWO_BYTES            1

#define SETSCREEN_KEEP_REZ (-1)       /* XBIOS Setscreen: leave the resolution alone */

/* The image itself. TOS zeroes .bss at load, and tos.ld aligns it to 256 so `image + OS_SCREEN_BASE`
 * is a legal ST video base (the shifter ignores the low 8 address bits). */
static uint8_t image[IMAGE_SIZE] __attribute__((aligned(256)));

/* joy_handler is entered off an interrupt, not the C ABI, so what it needs are plain longwords. */
unsigned char *joy_buf_addr;
unsigned char *joy_slot_addr;
unsigned long  joy_packet_off = JOY_PACKET_BUF;

/* ---- freestanding libc (we link -nostdlib). Only the kit's staged-file model calls these; the
 * cores themselves call none. Long-word copies where both ends are aligned — ~4x a byte loop on a
 * 68000 — with a byte tail for the remainder. */
void *memcpy(void *dst, const void *src, unsigned long n) {
    uint8_t *dp = dst; const uint8_t *sp = src;
    if ((((uintptr_t)dp | (uintptr_t)sp) & 3) == 0) {
        uint32_t *dw = (uint32_t *)dp; const uint32_t *sw = (const uint32_t *)sp;
        for (; n >= 4; n -= 4) *dw++ = *sw++;
        dp = (uint8_t *)dw; sp = (const uint8_t *)sw;
    }
    while (n--) *dp++ = *sp++;
    return dst;
}

void *memmove(void *dst, const void *src, unsigned long n) {
    uint8_t *dp = dst; const uint8_t *sp = src;
    if (dp <= sp) { while (n--) *dp++ = *sp++; }
    else { dp += n; sp += n; while (n--) *--dp = *--sp; }
    return dst;
}

void *memset(void *dst, int c, unsigned long n) {
    uint8_t *dp = dst;
    if (((uintptr_t)dp & 3) == 0) {
        uint32_t word = (uint32_t)(uint8_t)c * 0x01010101ul;
        uint32_t *dw = (uint32_t *)dp;
        for (; n >= 4; n -= 4) *dw++ = word;
        dp = (uint8_t *)dw;
    }
    while (n--) *dp++ = (uint8_t)c;
    return dst;
}

/* ---- progress beacons: SMOKE only ------------------------------------------------------------
 * Drop a marker file B<n> on the GEMDOS drive at each startup step, so a headless run can pinpoint
 * a hang by the highest-numbered marker present. No debugger, no display. */
#ifdef SMOKE
static void beacon(int step) {
    char name[4] = { 'B', (char)('0' + step), 0, 0 };
    long handle = Fcreate(name, 0);
    if (handle >= 0) Fclose((short)handle);
}
#define BEACON(step) beacon(step)
/* ...and the same for a marker inside code that runs many times: only the first pass leaves one. */
#define BEACON_ONCE(step) do { static int dropped; if (!dropped) { dropped = 1; beacon(step); } } while (0)
#else
#define BEACON(step) ((void)0)
#define BEACON_ONCE(step) ((void)0)
#endif

/* ---- what the shim watches go past ------------------------------------------------------------
 * Counters the SMOKE build writes to C:\STATS.BIN so the headless check can assert on what the GAME
 * asked for, not on what the framebuffer happens to look like.
 *
 * THE SPLIT IS `frames`, NOT `title_over`, and the difference matters: title_over fires on
 * snd_tone_sweep's FIRST register write, so the other ~14,448 writes of that same boot sweep would
 * count as gameplay and a build whose play_sound was completely broken would still show a large
 * "in play" figure. `frames` only starts counting at the frame loop's first poll_quit_key, which is
 * past init_video entirely, so the in-play halves witness the per-frame loop and nothing else. */
static unsigned long frames;                  /* per-frame loop iterations (see shim_console_polled) */
static unsigned long dosound_calls, dosound_calls_in_play, first_sound_frame;
static unsigned long psg_writes, psg_writes_in_play;
/* THESE TWO OUTLIVE A RESTART, and are the only ones that do: they are facts about the SESSION, not
 * about the game now being played. Everything above is run-scoped and shim_reset_run_state() below
 * zeroes it — as a block, so that adding a counter here cannot silently survive a restart. */
static unsigned long restarts;                /* completed R-key restarts */
static unsigned long hiscore_bytes_written;   /* what the quit path put back into the real file */
#ifdef SMOKE_FRAME_DUMPS
static unsigned long frame_bytes_written;     /* ...and the frame differential's sample dumps */
#else
#define frame_bytes_written 0uL               /* no sample dumps in this build, so nothing wrote */
#endif
static int title_over;

/* IKBD replies filed by joy_handler (declared in tos.h with the handler's other globals). It is the
 * only evidence a headless run can give that the joystick path is LIVE: Hatari has no way to press
 * a stick without a keyboard, so what can be witnessed is that real packets keep arriving and that
 * the game's waits end on them. Steering itself is a GUI check (run.sh) — see README §11. */
volatile unsigned long ikbd_packets;

void shim_quit_tail_running(void);

/* XBIOS Dosound — the one hardware seam that IS a link-time symbol. Off target it is the kit's
 * ordered ledger (tools/recreate_kit/src/dosound_log.c) that the differential compares the two
 * cores' sound against; here it is the real trap, and TOS's per-VBL stepper — which the VBL install
 * below keeps alive behind our own handler — walks the command list. */
void g_dosound(uint8_t *img, uint32_t list_addr) {
    BEACON_ONCE(6);   /* the title screen's Dosound silence: draw_title_screen has finished */
    shim_quit_tail_running();   /* quit_to_desktop's first act — see the exit machinery below */
    dosound_calls++;
    if (frames) {
        if (!dosound_calls_in_play++) first_sound_frame = frames;
    }
    Dosound(img + list_addr);
}

/* ---- the VBL handler: palette + IKBD watchdog ------------------------------------------------
 *
 * THE PALETTE IS THE SHIM'S BECAUSE THE RECONSTRUCTION HAS NO WAY TO LOAD IT. XBIOS Setpalette
 * writes the shifter, not memory, so the kit models it as a pure no-op — which means
 * `xbios_setpalette` (src/init.c) faithfully returns the table address and its callers drop it, and
 * init_video's Setpalette is not even a call. Both are verified against the argument the ORIGINAL
 * pushed and neither can put a colour on screen. So the shim pushes the table itself, every VBL:
 * the title screen's while the title screen is up (which is also what animates it — cycle_palette
 * and the six-pen ring rewrite that very table in the image each attract pass), and the game's
 * afterwards.
 *
 * The switch between them is exact rather than a guess: `title_over` is set by the FIRST Giaccess
 * WRITE of the run, and the only writer of the YM2149 through Giaccess is snd_tone_sweep, whose
 * only caller is the tail of init_video — the call immediately after title_screen returns.
 * (play_sound reaches the chip through Dosound; snd_poll_done only READS register 7.)
 *
 * IT GOES THROUGH _colorptr, NOT THROUGH THE SHIFTER REGISTERS, and that is a bug fix rather than a
 * preference. TOS's own VBL loads the 16 pens from _colorptr and clears it — that is all XBIOS
 * Setpalette does — so one longword store here is a whole palette load, deferred to the next
 * vblank. Writing $ffff8240..$ffff825e directly is what this handler did first, and GCC compiled the
 * loop to `move.w (%a0)+,(%a0,%d0.l)`: on the 68000 the destination EA is computed AFTER the source
 * postincrement, so every pen landed one register high and the SIXTEENTH write went to $ffff8260 —
 * the RESOLUTION register — with pen 15's 0x0777 in it. TOS 1.04 hung on the spot; EmuTOS survived
 * it, which is exactly the shape of on-target bug docs/on-target-execution.md warns about. */
static uint32_t palette_source = A_title_palette;

/* Frames the IKBD reply slot has stayed empty. joy_handler chains the next interrogate itself, so
 * this only has to cover a chain that broke (a reply that arrived with the ACIA transmitter busy).
 * Two VBLs, because one would race a reply that is legitimately still in flight. */
#define IKBD_IDLE_VBLS_BEFORE_REPRIME 2
static int ikbd_idle_vbls;

static void vbl_handler(void) {
    SYS_COLORPTR = (uint32_t)(image + palette_source);

    if (be32(image + A_ikbd_packet) != 0) {
        ikbd_idle_vbls = 0;
        return;
    }
    if (++ikbd_idle_vbls < IKBD_IDLE_VBLS_BEFORE_REPRIME) return;
    ikbd_idle_vbls = 0;
    if (ACIA_STATUS & ACIA_TDRE) ACIA_DATA = IKBD_INTERROGATE;
}

/* Our VBL queue: slot 0 is the handler above, followed by the TOS routines we displace — the same
 * shape the original's BuggyBoy-era peers use, and the reason TOS's own per-VBL Dosound stepper
 * keeps running (play_sound's command lists are stepped by it, not by us). A function-pointer
 * initialiser in .data becomes an R_68K_32 fixup that mkprg.py relocates at load. */
#define TOS_VBL_SLOTS 8
static void (*vbl_queue[1 + TOS_VBL_SLOTS])(void) = { vbl_handler };

/* ---- startup ---------------------------------------------------------------------------------- */

/* Read a whole file into the image at `offset`; the byte count, or -1 if it is not there. */
static long load_file(const char *name, uint32_t offset, long max) {
    long handle = Fopen(name, 0);
    if (handle < 0) return -1;
    long count = Fread((short)handle, max, image + offset);
    Fclose((short)handle);
    return count;
}

/* Stage HIGH.SCO the way harness.stage_files does, so init_system's os_fopen/os_fread — which are
 * the KIT's model here, not real GEMDOS (see shim_include/os.h) — find it exactly as they do under
 * the differential. A missing file leaves the table empty, and os_fopen then returns -1 to the
 * failure arm the original has. */
static void stage_hiscore_file(void) {
    long size = load_file(HIGHSCO_NAME, OS_FS_STAGING, HIGHSCO_CAPACITY);
    if (size < 0) return;

    uint8_t *entry = os_fs_slot(image, HIGHSCO_SLOT);
    memcpy(entry, HIGHSCO_NAME, sizeof HIGHSCO_NAME);
    wr32(entry + OS_FS_OFF_STAGING, OS_FS_STAGING);
    wr32(entry + OS_FS_OFF_SIZE, (uint32_t)size);
    wr32(entry + OS_FS_OFF_CURSOR, 0);
    wr32(entry + OS_FS_OFF_OPEN, 0);
    wr32(entry + OS_FS_OFF_CAPACITY, HIGHSCO_CAPACITY);
}

/* The three privileged pokes, each in its own balanced Super pair so the PRG is back in user mode
 * (and GEMDOS usable) the moment it returns.
 *
 * EVERY ONE OF THEM IS SAVED, because every one of them points TOS at code inside this process and
 * the process can end. Leaving the joystick vector hooked past Pterm is not a cosmetic leak: the
 * IKBD is still in interrogation mode, joy_handler chains the next $16 off each reply, and the
 * memory it is chaining from has been handed back — measured on TOS 1.04 as a double bus/address
 * error and a HALTED CPU a second or so after the program exits. shim_teardown() below is the
 * mirror of all four installs and runs before any Pterm. */
static uint32_t kbdvbase_addr;
static uint32_t saved_joyvec, saved_mousevec;
static uint32_t saved_vblqueue;
static int16_t saved_nvbls;
static uint8_t saved_conterm;
static void *tos_logbase, *tos_physbase;              /* TOS's screen, before we moved the shifter */
static uint16_t desktop_palette[PALETTE_PENS];        /* ...and its 16 pens */

/* Read the desktop's palette back the way init_system's save_palette does — XBIOS Setcolor with a
 * query — so the quit path can put the real one back. The reconstruction's own copy is sixteen
 * zeros under the kit's model; see shim_teardown. */
#define SETCOLOR_QUERY (-1)

static void save_desktop_state(void) {
    tos_logbase = (void *)(uintptr_t)Logbase();
    tos_physbase = (void *)(uintptr_t)Physbase();
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        desktop_palette[pen] = (uint16_t)Setcolor((short)pen, SETCOLOR_QUERY);
}

static volatile uint32_t *kbdv_vector(uint32_t offset) {
    return (volatile uint32_t *)(uintptr_t)(kbdvbase_addr + offset);
}

static void install_ikbd_vectors(void) {
    long saved_ssp = Super(0);
    kbdvbase_addr = (uint32_t)Kbdvbase();
    saved_joyvec = *kbdv_vector(KBDVBASE_JOYVEC);
    saved_mousevec = *kbdv_vector(KBDVBASE_MOUSEVEC);
    *kbdv_vector(KBDVBASE_JOYVEC) = (uint32_t)joy_handler;
    *kbdv_vector(KBDVBASE_MOUSEVEC) = (uint32_t)null_handler;
    Super((void *)(uintptr_t)saved_ssp);
}

/* init_system clears the low three conterm flags (`andi.b #$f8`) — bell, key click and "put the
 * scancode in the console longword". The reconstruction writes that byte INSIDE the image (the kit
 * models the whole of low memory as image bytes), so on target the real one has to be cleared here
 * or every keypress clicks. */
static void quiet_conterm(void) {
    long saved_ssp = Super(0);
    saved_conterm = SYS_CONTERM;
    SYS_CONTERM &= CONTERM_KEEP;
    Super((void *)(uintptr_t)saved_ssp);
}

static void install_vbl_handler(void) {
    long saved_ssp = Super(0);
    saved_vblqueue = SYS_VBLQUEUE;
    saved_nvbls = SYS_NVBLS;
    uint32_t *tos_queue = (uint32_t *)(uintptr_t)saved_vblqueue;
    int16_t tos_slots = saved_nvbls;
    if (tos_slots > TOS_VBL_SLOTS) tos_slots = TOS_VBL_SLOTS;
    for (int slot = 0; slot < tos_slots; slot++)
        vbl_queue[1 + slot] = (void (*)(void))(uintptr_t)tos_queue[slot];
    SYS_NVBLS = 0;                                    /* detach while the pointer is swapped */
    SYS_VBLQUEUE = (uint32_t)(uintptr_t)vbl_queue;
    SYS_NVBLS = (int16_t)(1 + tos_slots);
    Super((void *)(uintptr_t)saved_ssp);
}

/* Hand the machine back, in the reverse of the order it was taken. It runs on EVERY exit path.
 *
 * The first half undoes what the shim installed, and it MUST be all four, in this order:
 *   1. the VBL queue, which stops the watchdog interrogating and stops TOS calling our handler;
 *   2. the two KBDVBASE vectors, which stops joy_handler chaining the next $16;
 *   3. conterm, so the desktop's key click and bell come back;
 *   4. the IKBD itself, with the GAME'S OWN two command strings — the reset ($80 $01) and the
 *      mouse-reporting byte ($14). Without it the sticks stay in interrogation mode and the
 *      desktop gets no mouse.
 * Steps 1 and 2 are the halt fix (README, "The bugs found on target"); a reply already in flight
 * between them is harmless, because by the time it lands TOS's own handler owns the vector again.
 *
 * The second half is the OFF-IMAGE half of the reconstruction's own quit tail. `restore_system`
 * (../src/input.c) puts back the three bytes it can — conterm and the two KBDVBASE vectors, INSIDE
 * the image — and its five surrounding trap calls have no reconstruction at all, because none of
 * them touches a byte the differential can see. Those five are made here, in the original's order:
 * Setscreen, Ikbdws, Ikbdws, Super, Setpalette. Two of them cannot use the image's answer:
 *   * Setscreen is handed TOS'S OWN log/phys base, saved before we pointed the shifter at the
 *     in-image framebuffer — the original never moved the screen, so it passes -1/-1;
 *   * Setpalette is handed the palette the SHIM read back at startup, because the one the
 *     reconstruction saved is sixteen zeros: `save_palette` stores what the kit models XBIOS
 *     Setcolor as answering, and the model has no palette. Restoring that would hand the desktop a
 *     black screen. The shim reads the real pens with the same Setcolor query the original uses. */
static void shim_teardown(void) {
    long saved_ssp = Super(0);
    SYS_NVBLS = 0;
    SYS_VBLQUEUE = saved_vblqueue;
    SYS_NVBLS = saved_nvbls;
    *kbdv_vector(KBDVBASE_JOYVEC) = saved_joyvec;
    *kbdv_vector(KBDVBASE_MOUSEVEC) = saved_mousevec;
    SYS_CONTERM = saved_conterm;
    Super((void *)(uintptr_t)saved_ssp);

    Setscreen(tos_logbase, tos_physbase, SETSCREEN_KEEP_REZ);
    Ikbdws(IKBD_TWO_BYTES, image + A_ikbd_cmd_reset);       /* $80 $01 */
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_mouse_rel);    /* $14 */
    Setpalette(desktop_palette);
    /* AND WAIT FOR IT. Setpalette does not write the shifter: it parks the POINTER in _colorptr and
     * TOS's own VBL copies sixteen words out of it on the next vblank. desktop_palette is in this
     * program's BSS, so returning from here straight into Pterm hands that memory back before TOS
     * has read it — the desktop would come up in whatever the freed block then contained. This is
     * the same shape as the joyvec-after-Pterm halt above, one vblank instead of one second. */
    Vsync();
}

/* Put the sticks in interrogation mode and get the first reply on its way. From there joy_handler
 * chains the next interrogate off each reply, so a wait never spins for more than one packet. */
static void start_ikbd(void) {
    joy_buf_addr = image + JOY_PACKET_BUF;
    joy_slot_addr = image + A_ikbd_packet;
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_joymode);   /* $15, the game's own command byte */
    install_ikbd_vectors();
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_joyread);   /* $16, likewise */
}

/* The one GEMDOS write/close in this file — the SMOKE dumps and the high-score write-back share it,
 * and this project already has a recorded GEMDOS handle gotcha, so there is one place to fix if
 * another turns up. Returns what Fwrite reported, or -1 if the handle was never opened. */
static long write_and_close(long handle, const void *from, long count) {
    if (handle < 0) return -1;
    long written = Fwrite((short)handle, count, from);
    Fclose((short)handle);
    return written;
}

/* Create-or-truncate, for the SMOKE dumps: they are this run's output and nothing else's, and only
 * the SMOKE builds make any. */
#ifdef SMOKE
static long dump_file(const char *name, const void *from, long count) {
    return write_and_close(Fcreate(name, 0), from, count);
}
#endif

/* ---- the frame differential's two pins (SMOKE only) -------------------------------------------
 *
 * `smoke.py framediff` byte-compares this build's framebuffer against the SHIPPED binary's at
 * matched frame counts. Two things have to be made identical on both sides first, and one of them
 * is not obvious:
 *
 * THE RANDOM SOURCE IS THE PROGRAM'S OWN TEXT. There is no arithmetic generator — rng_ptr walks
 * [0x10000, 0x17832) and callers read the word under it (../src/rng.c). Those bytes are NOT the same
 * on both sides: 1117 of the relocation sites in that window fall inside it, and a relocated
 * longword holds `file value + load base`, which is 0x10000 for this image and 0x12596 for the
 * shipped binary under the same Hatari. Forcing the same XBIOS Random answer is therefore NOT
 * enough — it only picks the same STARTING offset into two different byte streams.
 *
 * So the cursor is parked instead, at an offset inside the largest RELOCATION-FREE stretch of the
 * window (6906 bytes at image 0x551a, i.e. Ghidra 0x1551a): there the two programs' bytes are
 * identical, so the random stream is too, for as long as the cursor stays inside. STATS.BIN reports
 * where it ended up so the test can prove it never left. The poke lands at the first console poll,
 * which is title_screen's — after init_game has seeded rng_ptr and long before the frame loop that
 * is the first thing to read through it. */
#ifdef SMOKE_RNG_PTR
static int rng_pin_pending = 1;

static void pin_rng_cursor(void) {
    if (!rng_pin_pending) return;
    rng_pin_pending = 0;
    wr32(image + A_rng_ptr, SMOKE_RNG_PTR);
}
#else
#define pin_rng_cursor() ((void)0)
#endif

/* The frames whose framebuffer is dumped, as FRAME1.BIN, FRAME2.BIN, ... in list order. One run
 * yields every sample, so the comparison is against ONE game rather than one game per depth. */
#ifdef SMOKE_FRAME_DUMPS
static const unsigned long FRAME_DUMPS[] = { SMOKE_FRAME_DUMPS };
#define FRAME_DUMP_COUNT (sizeof FRAME_DUMPS / sizeof FRAME_DUMPS[0])

/* The filenames are FRAME1..FRAME9, one digit. */
_Static_assert(FRAME_DUMP_COUNT <= 9, "SMOKE_FRAME_DUMPS holds at most nine sample frames");

static void dump_sampled_frame(void) {
    for (unsigned index = 0; index < FRAME_DUMP_COUNT; index++) {
        if (FRAME_DUMPS[index] != frames) continue;
        char name[12] = { 'F', 'R', 'A', 'M', 'E', (char)('1' + index), '.', 'B', 'I', 'N', 0, 0 };
        long written = dump_file(name, image + OS_SCREEN_BASE, SCREEN_BYTES);
        /* Totalled and reported for the same reason hiscore_bytes_written is: a dump that failed or
         * ran short leaves a file the comparison would happily read, and a short read compares equal
         * as far as it goes. The byte count is the only thing that says the frame really landed. */
        if (written > 0) frame_bytes_written += (unsigned long)written;
    }
}
#else
#define dump_sampled_frame() ((void)0)
#endif

/* ---- the shim's hooks inside the cores' OS calls (shim_include/os.h explains each) ------------ */

static unsigned long console_polls;   /* every Bconstat the game makes; `frames` above counts the
                                       * ones that are a per-frame poll_quit_key */

/* smoke_finish is the FRAME-LIMIT exit, so it only exists in the two builds that have a limit; the
 * quit/restart builds leave through the game's own exit and shim_quit(). */
#if defined(SMOKE_TITLE) || defined(SMOKE_FRAMES)
#define SMOKE_HAS_FRAME_LIMIT 1
static void smoke_finish(void);
#endif

void shim_psg_written(void) {
    psg_writes++;
    if (frames) psg_writes_in_play++;
    if (title_over) return;
    title_over = 1;
    palette_source = A_game_palette;
}

void shim_console_polled(void) {
    BEACON_ONCE(7);   /* the first console poll: the attract loop is running */
    pin_rng_cursor();
    console_polls++;
    if (title_over) frames++;
    dump_sampled_frame();
#ifdef SMOKE_TITLE
    /* The first poll of the run: title_screen has painted the picture, the three text lines and one
     * pass of the colour cycle, and is now counting its 400 console polls. */
    if (console_polls == 1) smoke_finish();
#endif
#ifdef SMOKE_FRAMES
    /* poll_quit_key is the 20th of start()'s 21 calls (the 16th of the 17 the frame loop makes), so
     * the framebuffer is complete when this runs — which is what makes it the frame anchor on BOTH
     * sides of the differential (smoke.py counts the shipped binary's entries to the same routine).
     * The `smoke` mode also dumps an early frame here, so its check can prove the game ANIMATED
     * rather than painted once. */
#ifdef SMOKE_EARLY_FRAME
    if (frames == SMOKE_EARLY_FRAME) dump_file("SCREEN0.BIN", image + OS_SCREEN_BASE, SCREEN_BYTES);
#endif
    if (frames >= SMOKE_FRAMES) smoke_finish();
#endif
}

/* SMOKE only: the keystrokes a headless run has no keyboard to type.
 *
 * A SEQUENCE, not one key, because the paths M3 has to reach need several: start a game, then quit
 * or restart, then quit again. Each entry waits SMOKE_SCRIPT_WAIT[i] console polls after the
 * PREVIOUS one was taken, which is a natural clock in both phases — the title screen polls ~400
 * times per attract pass, and during play poll_quit_key is exactly one poll per frame.
 *
 * The keys are offered at the shim's console seam, the same place TOS delivers a real one, and (see
 * shim_include/os.h) only on a poll where TOS itself has nothing waiting — so a real key wins. */
#ifdef SMOKE_SCRIPT_KEYS
static const unsigned long SCRIPT_KEYS[] = { SMOKE_SCRIPT_KEYS };
static const unsigned long SCRIPT_WAIT[] = { SMOKE_SCRIPT_WAIT };
#define SCRIPT_LENGTH (sizeof SCRIPT_KEYS / sizeof SCRIPT_KEYS[0])
/* The two arrays come from two independent -D macros on two continued lines of build.sh, and
 * SCRIPT_WAIT is indexed under SCRIPT_KEYS's bound — so a key added to one list and not the other
 * would read past the end of .rodata and the script would silently collapse or stall. */
_Static_assert(sizeof SCRIPT_WAIT == sizeof SCRIPT_KEYS,
               "SMOKE_SCRIPT_KEYS and SMOKE_SCRIPT_WAIT must have the same number of entries");

static unsigned script_next;              /* the next entry to deliver */
static unsigned long script_armed_at;     /* console_polls when the previous one was taken */

int shim_console_pending(void) {
    return script_next < SCRIPT_LENGTH && console_polls >= script_armed_at + SCRIPT_WAIT[script_next];
}

unsigned long shim_console_take(void) {
    script_armed_at = console_polls;
    return SCRIPT_KEYS[script_next++];
}
#else
int shim_console_pending(void) { return 0; }
unsigned long shim_console_take(void) { return 0; }
#endif

/* ---- the exits the reconstruction reports but `start()` drops ---------------------------------
 *
 * Three of the original's exits are a `jmp` or a `Pterm` that never comes back, so the C returns a
 * result code instead and `start()` ignores it — which is CORRECT for the differential and for the
 * original (the routine that took such a path does not return), and leaves the on-target game with
 * no way to quit or restart. The shim finishes them, from the only place it gets control: the OS
 * seams the cores call. `start()` never returns, so there is nowhere else.
 *
 * QUIT (Ctrl-C, from title_screen or poll_quit_key). The key is watched rather than intercepted,
 * because quit_to_desktop is VERIFIED CODE and must run: it silences the chip, writes the high
 * score into the staged file and puts the image's system state back. So:
 *   1. shim_console_key sees Ctrl-C go to the game               -> QUIT_KEY_SEEN
 *   2. g_dosound(silence) — quit_to_desktop's first act          -> QUIT_TAIL_RUNNING
 *   3. the next seam of any kind: the tail has returned          -> shim_quit()
 * Step 3 is the next seam after the key, because between quit_to_desktop returning and that seam
 * lie only calls with no trap in them. From PLAY that is one more rendered frame, 20 ms. From the
 * TITLE SCREEN it is more: title_screen returns TITLE_QUIT, start_init_chain drops it and runs
 * init_video, whose first hooked seam is snd_tone_sweep's Giaccess at the END — so the picture is
 * blanked and the playfield painted first. One frame of game before the desktop comes back; see
 * README §10.
 *
 * If step 2 never happens and a SECOND console poll arrives instead, the game IGNORED the key —
 * which check_highscore's name-entry loop does, since hiscore_key_input has no Ctrl-C case and that
 * loop never returns to poll_quit_key. Without this the game would be unquittable there, so the
 * shim calls quit_to_desktop ITSELF (the exported routine, not a copy of it) and then quits.
 *
 * RESTART (R/r). poll_quit_key's own exit; the original jumps to RESTART_ENTRY = _start+6, i.e.
 * back to init_game with init_system SKIPPED. shim_restart() longjmps out and re-enters `start()`,
 * which is init_system + that same chain — the loop cannot be re-entered any other way without the
 * shim owning a second copy of `_start`'s twenty-one calls, and running the VERIFIED `start()` is
 * worth more than skipping one idempotent call. Two of the things init_system writes and the
 * original's restart never touches would be OBSERVABLE, so they are snapshotted here and put back
 * at shim_init_game_started(), which is init_game's own trap and so exactly where the original
 * resumes: two_player_mode (which init_system zeroes, losing the mode a fire-button start would
 * reuse) and the in-memory high-score record (which load_hiscore would overwrite from the staged
 * file, discarding a score just typed). "Two" is not a claim that init_system writes nothing else —
 * it re-saves saved_rez, the 16-word saved_palette, conterm_save, the two KBDVBASE vectors and the
 * boot scratch as well. Every one of those is IMAGE-only state that only the reconstruction's own
 * quit tail reads, and on target the real machine is handed back from the shim's saved copies
 * (shim_teardown), so re-writing them changes nothing observable.
 *
 * THE SHIM'S OWN VIEW OF THE RUN IS RESET TOO, and forgetting that was a bug: title_over latches on
 * the first Giaccess write and never clears, so a restarted attract screen ran under the GAME
 * palette (measured: zero title-palette frames after a restart) and a SMOKE_FRAMES build would have
 * counted title polls as frames and terminated on the title.
 *
 * R IS ONLY TAKEN AS A RESTART DURING PLAY — game_over_flag clear AND title_over set — and that is
 * a deliberately narrow trade with an edge on each side, neither of which the ORIGINAL has:
 *   * game_over_flag SET: the name-entry screen may be up, and there R is a LETTER being typed into
 *     the name (hiscore_key_input accepts it). But the original's poll_quit_key tests nothing at
 *     all, so between draw_messages setting the flag mid-loop and init_game clearing it there is a
 *     window in which the original restarts and this build does not.
 *   * title_over CLEAR: the attract screen. game_over_flag is clear there (init_game ran just
 *     before title_screen), so that gate alone is wide open, and the original ignores R on the
 *     title screen like any other key — title_screen has no R case.
 * The shim cannot tell WHICH reader consumed a key, only what state the game is in, so it buys
 * fidelity on the two screens R does nothing on at the cost of one window in which it should. */
enum { QUIT_NONE, QUIT_KEY_SEEN, QUIT_TAIL_RUNNING };
static int quit_phase;
static int restart_pending;
/* The one thing every OS seam tests, so the seams cost two instructions when nothing is pending.
 * Raised the moment a key that ENDS the run is handed to the game, lowered nowhere: from that point
 * the run is going to end or restart, and shim_take_exit() decides which and when. */
volatile int shim_exit_armed;

static shim_jmp_buf restart_point;
#define RESTART_REENTRY 1

/* What re-entering `start()` would clobber and the original's restart does not. */
static uint8_t restart_two_player;
static uint8_t restart_hiscore_record[HISCORE_FILE_BYTES];
static int restart_fixup_pending;

static void shim_quit(void);

/* Put the shim's view of the run back to cold. A restart re-enters `start()` from the top, so every
 * counter above describes a game that is over — and two of them are not just stale but WRONG if
 * left: title_over latches on the first Giaccess write and would leave the restarted attract screen
 * running under the GAME palette (measured), and `frames` would carry the old game's count into the
 * new one, so a SMOKE_FRAMES build would terminate part-way through the restarted game rather than
 * after SMOKE_FRAMES of it. The scripted console's cursor (script_next) is deliberately NOT reset:
 * it is a position in a sequence of keys, not a fact about the game. */
static void shim_reset_run_state(void) {
    frames = 0;
    console_polls = 0;
    dosound_calls = dosound_calls_in_play = first_sound_frame = 0;
    psg_writes = psg_writes_in_play = 0;
    title_over = 0;
    palette_source = A_title_palette;
    ikbd_idle_vbls = 0;
    /* Nothing is pending any more, so the seams go back to two instructions. Leaving this raised
     * would make the restarted init_video pay the ~1.9 M cycles of out-of-line hook calls that
     * shim_check_exit's inline test exists to avoid — a quarter-second pause, on every restart. */
    shim_exit_armed = 0;
#ifdef SMOKE_SCRIPT_KEYS
    script_armed_at = 0;
#endif
}

void shim_console_key(unsigned long console) {
    uint8_t key = (uint8_t)console;
    if (key == KEY_CTRL_C) {
        quit_phase = QUIT_KEY_SEEN;
        shim_exit_armed = 1;
        return;
    }
    /* Both gates, and the comment above has the trade each one makes. */
    if ((key == KEY_RESTART_UPPER || key == KEY_RESTART_LOWER)
            && title_over && image[A_game_over_flag] == 0) {
        BEACON_ONCE(8);   /* R accepted: the restart is armed */
        restart_pending = 1;
        shim_exit_armed = 1;
    }
}

void shim_quit_tail_running(void) {
    if (quit_phase == QUIT_KEY_SEEN) quit_phase = QUIT_TAIL_RUNNING;
}

void shim_take_exit(int at_console_poll) {
    if (quit_phase == QUIT_TAIL_RUNNING) shim_quit();          /* quit_to_desktop has returned */
    if (quit_phase == QUIT_KEY_SEEN && at_console_poll) {      /* ...or the game ignored the key */
        quit_to_desktop(image);
        shim_quit();
    }
    if (!restart_pending) return;
    restart_pending = 0;
    memcpy(restart_hiscore_record, image + A_hiscore_name, sizeof restart_hiscore_record);
    restart_two_player = image[A_two_player_mode];
    restart_fixup_pending = 1;
    shim_reset_run_state();
    shim_longjmp(restart_point, RESTART_REENTRY);
}

void shim_init_game_started(void) {
    if (!restart_fixup_pending) return;
    restart_fixup_pending = 0;
    memcpy(image + A_hiscore_name, restart_hiscore_record, sizeof restart_hiscore_record);
    image[A_two_player_mode] = restart_two_player;
}

/* ---- the headless dump ------------------------------------------------------------------------
 * What the SMOKE build leaves on the drive for smoke.py to check:
 *   SCREEN0.BIN  an EARLY gameplay frame, and SCREEN.BIN the LAST one — two frames, so the check
 *                can tell a game that is running from one that painted frame 1 and stopped;
 *   SCREEN.BIN   the framebuffer the cores drew (screen_base is OS_SCREEN_BASE, the kit's Physbase
 *                answer, which init_system stores and every draw routine addresses from);
 *   STATS.BIN    the counters below — what the GAME asked for, which no framebuffer can show.
 * Then the machine goes back the way it was found and the process ends. */
#ifdef SMOKE
#define STATS_FIELDS 16
#define STATS_BYTES  (STATS_FIELDS * 4)

/* The record smoke.py parses: sixteen big-endian longwords, in this order. The last six are read
 * out of the IMAGE, and are what proves things no framebuffer can show: that the scripted '1' drove
 * title_screen's ONE-player arm, and that a restart really happened.
 *
 * player_x/player_y are REPORTED, NOT ASSERTED, and are not evidence of steering — a headless run
 * has no stick to push (README §11), so they show the rider under gravity alone. They are also read
 * with be16, i.e. UNSIGNED, while the object layer treats both as int16_t: a rider at x = -4 comes
 * out as 65532, which any future range check here has to allow for. */
static void dump_stats(void) {
    uint8_t record[STATS_BYTES];
    const unsigned long fields[STATS_FIELDS] = {
        frames, console_polls,
        dosound_calls, dosound_calls_in_play, first_sound_frame,
        psg_writes, psg_writes_in_play,
        ikbd_packets, restarts, hiscore_bytes_written, frame_bytes_written,
        image[A_two_player_mode], image[A_players_alive],
        be16(image + A_object_table + OBJ_X), be16(image + A_object_table + OBJ_Y),
        be32(image + A_rng_ptr),
    };
    for (unsigned i = 0; i < STATS_FIELDS; i++) wr32(record + 4u * i, (uint32_t)fields[i]);
    dump_file("STATS.BIN", record, STATS_BYTES);
}

static void dump_screen(void) {
    dump_file("SCREEN.BIN", image + OS_SCREEN_BASE, SCREEN_BYTES);
}


#else
#define dump_stats()  ((void)0)
#define dump_screen() ((void)0)
#endif

/* ---- quitting ---------------------------------------------------------------------------------
 *
 * HIGH.SCO IS WRITTEN HERE, and it is the other half of a routine the harness could only verify
 * halfway. save_hiscore (../src/input.c) writes the 26-byte record through the KIT'S staged-file
 * model — os_fwrite into the image's staging area — because that is what the differential runs
 * against and what shim_include/os.h deliberately keeps on target. Nothing has touched the real
 * file. So the shim copies the staged bytes out through real GEMDOS, at the size the model's own
 * table entry now reports, gated on the same `hiscore_dirty` byte save_hiscore gates on.
 *
 * The gate is always set in practice and that is the ORIGINAL's behaviour, not an accident:
 * init_system marks a successfully loaded HIGH.SCO as dirty (HISCORE_LOADED_MARK), so every Ctrl-C
 * rewrites the file. ../src/init.c calls that out as reproduced, not fixed. */
static void write_hiscore_file(void) {
    if (image[A_hiscore_dirty] == 0) return;
    const uint8_t *entry = os_fs_slot(image, HIGHSCO_SLOT);
    if (entry[0] == 0) return;                        /* no HIGH.SCO was staged at startup */

    /* OPEN BEFORE CREATE, which is save_hiscore's own order (../src/input.c) and matters for the
     * same reason there: Fcreate TRUNCATES, so reaching for it first would empty the player's
     * record before knowing the write can succeed — on a full or write-protected drive that is a
     * quit which destroys the high score it was saving. The record is fixed-length, so opening
     * without truncating leaves no tail of an older one. */
    long handle = Fopen(HIGHSCO_NAME, HIGHSCO_OPEN_RDWR);
    if (handle < 0) handle = Fcreate(HIGHSCO_NAME, 0);
    long written = write_and_close(handle, image + be32(entry + OS_FS_OFF_STAGING),
                                   (long)be32(entry + OS_FS_OFF_SIZE));
    /* Reported in STATS.BIN because the file ALONE cannot witness this: the same name is staged as
     * an input, so a check that only compares the file's contents passes on a build that never got
     * here (measured — the title build passed it). */
    if (written > 0) hiscore_bytes_written = (unsigned long)written;
}

/* THE one exit. Whatever is added here — another teardown undo, another dump — is added for every
 * way out at once, which matters because an incomplete hand-back is invisible until a second after
 * the process is gone (README, "The bugs found on target").
 *
 * `writing_back` is the whole difference between the two ways out: the game's own quit path has run
 * quit_to_desktop and its record is waiting in the staged file, while a SMOKE frame limit is the
 * harness stopping a game that never asked to end — and check_hiscore's proof depends on those two
 * being distinguishable (a build that never reaches the quit path must report zero bytes written). */
static void shim_exit(int writing_back) {
    if (writing_back) write_hiscore_file();
    dump_stats();
    dump_screen();
    shim_teardown();
    Pterm(0);
}

#define SHIM_EXIT_WRITES_HISCORE 1
#define SHIM_EXIT_NO_WRITE_BACK  0

static void shim_quit(void) {
    shim_exit(SHIM_EXIT_WRITES_HISCORE);
}

#ifdef SMOKE_HAS_FRAME_LIMIT
static void smoke_finish(void) {
    shim_exit(SHIM_EXIT_NO_WRITE_BACK);
}
#endif

/* ---- entry ------------------------------------------------------------------------------------ */

void joust_main(void) {
    BEACON(0);
    if (load_file("JOUST.IMG", IMAGE_LOAD_BASE, PROGRAM_BYTES) != PROGRAM_BYTES) return;
    BEACON(1);
    stage_hiscore_file();
    BEACON(2);

    save_desktop_state();
    quiet_conterm();
    start_ikbd();
    BEACON(3);

    /* Point TOS at the in-image framebuffer instead of copying to its own every frame. Joust draws
     * straight into the displayed screen (no double buffer), and the cores' screen_base is an image
     * OFFSET, so `image + OS_SCREEN_BASE` is exactly the buffer they paint — 256-aligned by tos.ld,
     * which is all the shifter requires. Setscreen rather than a poke at $ffff8201/8203, because
     * TOS's own VBL routine reloads the shifter from _v_bas_ad and would undo a bare poke. */
    Setscreen(image + OS_SCREEN_BASE, image + OS_SCREEN_BASE, SETSCREEN_KEEP_REZ);
    Vsync();               /* TOS latches the new base on the next vblank — let it, BEFORE the VBL
                            * queue is swapped underneath it (a run without this hung once) */
    BEACON(4);
    install_vbl_handler();
    BEACON(5);

    /* `start()` is the whole game and never returns; it leaves only through a shim seam. A quit
     * ends the process from there, so the only way back HERE is a restart's longjmp — which lands
     * on the setjmp below and runs the game again, exactly as the original's `jmp _start+6` does. */
    for (;;) {
        if (shim_setjmp(restart_point) == RESTART_REENTRY) { BEACON_ONCE(9); restarts++; }  /* a restart landed */
        start(image);
    }
}
