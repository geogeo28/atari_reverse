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

/* JOUST.IMG's length — the pre-relocated program, [0x10000, 0x2b7ae). build.sh passes the length
 * of the blob gen_image.py just wrote, so the two cannot drift; the load below insists on exactly
 * that many bytes, since a short read leaves the cores reading zeroes for a table. */
#ifndef PROGRAM_BYTES
#error "build.sh must define PROGRAM_BYTES as the byte length of the staged JOUST.IMG"
#endif

/* Where the IKBD handler leaves the two joystick bytes. A free low-image slot: above the kit's
 * modelled KBDVBASE (0x500) and console state (0x600..0x61f), below the framebuffer at
 * OS_SCREEN_BASE (0x8000). ikbd_packet holds this OFFSET, which is what the cores dereference. */
#define JOY_PACKET_BUF  0x700u

/* HIGH.SCO's slot in the kit's staged-file table. os_fwrite refuses a write past the capacity, so
 * it is sized well clear of the 26-byte record the quit path writes back. */
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
static int title_over;

/* XBIOS Dosound — the one hardware seam that IS a link-time symbol. Off target it is the kit's
 * ordered ledger (tools/recreate_kit/src/dosound_log.c) that the differential compares the two
 * cores' sound against; here it is the real trap, and TOS's per-VBL stepper — which the VBL install
 * below keeps alive behind our own handler — walks the command list. */
void g_dosound(uint8_t *img, uint32_t list_addr) {
    BEACON_ONCE(6);   /* the title screen's Dosound silence: draw_title_screen has finished */
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
    long size = load_file("HIGH.SCO", OS_FS_STAGING, HIGHSCO_CAPACITY);
    if (size < 0) return;

    uint8_t *entry = os_fs_slot(image, HIGHSCO_SLOT);
    memcpy(entry, "HIGH.SCO", sizeof "HIGH.SCO");
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

/* Hand the machine back, in the reverse of the order it was taken. SMOKE-only for now because the
 * SMOKE builds are the only ones with an exit at all: `start()` never returns, and the quit path
 * that would need this in the playable build (Ctrl-C -> quit_to_desktop -> Pterm) is M3's — see
 * README.md, "Known gaps". Nothing else may Pterm without calling it.
 *
 * It MUST be all four, in this order:
 *   1. the VBL queue, which stops the watchdog interrogating and stops TOS calling our handler;
 *   2. the two KBDVBASE vectors, which stops joy_handler chaining the next $16;
 *   3. the IKBD itself, with the GAME'S OWN two command strings — the reset ($80 $01) and the
 *      mouse-reporting byte ($14) that the original's quit tail sends (src/input.c's
 *      restore_system is the image half of this; the traps are the half no reconstruction has).
 *      Without it the sticks stay in interrogation mode and the desktop gets no mouse;
 *   4. conterm, so the desktop's key click and bell come back.
 * Steps 1 and 2 are the halt fix; a reply already in flight between them is harmless, because by
 * the time it lands TOS's own handler owns the vector again. */
#ifdef SMOKE
static void shim_teardown(void) {
    long saved_ssp = Super(0);
    SYS_NVBLS = 0;
    SYS_VBLQUEUE = saved_vblqueue;
    SYS_NVBLS = saved_nvbls;
    *kbdv_vector(KBDVBASE_JOYVEC) = saved_joyvec;
    *kbdv_vector(KBDVBASE_MOUSEVEC) = saved_mousevec;
    SYS_CONTERM = saved_conterm;
    Super((void *)(uintptr_t)saved_ssp);

    Ikbdws(IKBD_TWO_BYTES, image + A_ikbd_cmd_reset);       /* $80 $01 */
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_mouse_rel);    /* $14 */
}
#endif

/* Put the sticks in interrogation mode and get the first reply on its way. From there joy_handler
 * chains the next interrogate off each reply, so a wait never spins for more than one packet. */
static void start_ikbd(void) {
    joy_buf_addr = image + JOY_PACKET_BUF;
    joy_slot_addr = image + A_ikbd_packet;
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_joymode);   /* $15, the game's own command byte */
    install_ikbd_vectors();
    Ikbdws(IKBD_ONE_BYTE, image + A_ikbd_cmd_joyread);   /* $16, likewise */
}

/* ---- the shim's hooks inside the cores' OS calls (shim_include/os.h explains each) ------------ */

static unsigned long console_polls;   /* every Bconstat the game makes; `frames` above counts the
                                       * ones that are a per-frame poll_quit_key */

#ifdef SMOKE
static void smoke_finish(void);
static void dump_file(const char *name, const void *from, long count);
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
    console_polls++;
    if (title_over) frames++;
#ifdef SMOKE_TITLE
    /* The first poll of the run: title_screen has painted the picture, the three text lines and one
     * pass of the colour cycle, and is now counting its 400 console polls. */
    if (console_polls == 1) smoke_finish();
#endif
#ifdef SMOKE_FRAMES
    /* poll_quit_key is the 20th of start()'s 21 calls (the 16th of the 17 the frame loop makes), so
     * the framebuffer is complete when this runs. Two frames are dumped: an early one, and the last
     * one at smoke_finish, so the check can prove the game ANIMATED rather than painted once. */
    if (frames == SMOKE_EARLY_FRAME) dump_file("SCREEN0.BIN", image + OS_SCREEN_BASE, SCREEN_BYTES);
    if (frames >= SMOKE_FRAMES) smoke_finish();
#endif
}

/* SMOKE only: the keystroke a headless run has no keyboard to type. It is offered at the shim's
 * console seam — the same place TOS delivers a real one — once the run has made SMOKE_KEY_AFTER
 * console polls, and (see shim_include/os.h) only on a poll where TOS itself has nothing waiting,
 * so a real key always wins. */
#ifdef SMOKE_KEY
static int scripted_key_left = 1;

int shim_console_pending(void) {
    return scripted_key_left && console_polls >= SMOKE_KEY_AFTER;
}

unsigned long shim_console_take(void) {
    scripted_key_left = 0;
    return SMOKE_KEY;
}
#else
int shim_console_pending(void) { return 0; }
unsigned long shim_console_take(void) { return 0; }
#endif

/* ---- the headless dump ------------------------------------------------------------------------
 * What the SMOKE build leaves on the drive for smoke.py to check:
 *   SCREEN0.BIN  an EARLY gameplay frame, and SCREEN.BIN the LAST one — two frames, so the check
 *                can tell a game that is running from one that painted frame 1 and stopped;
 *   SCREEN.BIN   the framebuffer the cores drew (screen_base is OS_SCREEN_BASE, the kit's Physbase
 *                answer, which init_system stores and every draw routine addresses from);
 *   STATS.BIN    the counters below — what the GAME asked for, which no framebuffer can show.
 * Then the machine goes back the way it was found and the process ends. */
#ifdef SMOKE
#define STATS_FIELDS 9
#define STATS_BYTES  (STATS_FIELDS * 4)

static void dump_file(const char *name, const void *from, long count) {
    long handle = Fcreate(name, 0);
    if (handle < 0) return;
    Fwrite((short)handle, count, from);
    Fclose((short)handle);
}

/* The record smoke.py parses: nine big-endian longwords, in this order. The last two are read out
 * of the IMAGE, and they are what proves the scripted '1' really drove title_screen's one-player
 * arm — nothing about one-vs-two players is legible in a framebuffer. */
static void dump_stats(void) {
    uint8_t record[STATS_BYTES];
    const unsigned long fields[STATS_FIELDS] = {
        frames, console_polls,
        dosound_calls, dosound_calls_in_play, first_sound_frame,
        psg_writes, psg_writes_in_play,
        image[A_two_player_mode], image[A_players_alive],
    };
    for (unsigned i = 0; i < STATS_FIELDS; i++) wr32(record + 4u * i, (uint32_t)fields[i]);
    dump_file("STATS.BIN", record, STATS_BYTES);
}

static void smoke_finish(void) {
    dump_stats();
    dump_file("SCREEN.BIN", image + OS_SCREEN_BASE, SCREEN_BYTES);
    shim_teardown();
    Pterm(0);
}
#endif

/* ---- entry ------------------------------------------------------------------------------------ */

void joust_main(void) {
    BEACON(0);
    if (load_file("JOUST.IMG", IMAGE_LOAD_BASE, PROGRAM_BYTES) != PROGRAM_BYTES) return;
    BEACON(1);
    stage_hiscore_file();
    BEACON(2);

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

    start(image);          /* the whole game — and it never returns */
}
