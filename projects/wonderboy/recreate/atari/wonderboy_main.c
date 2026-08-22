/* wonderboy_main.c — the shim: stage the image, take the machine, run, hand it back, say what happened.
 *
 * The reconstruction is 314 verified functions that address one flat array and touch the world
 * through six kit symbols. wonderboy_backend.c turns those six into hardware; this file supplies
 * everything either side of them — the image, the vectors, the video mode, the teardown, and the
 * record of what was asserted.
 *
 * WHAT THIS BUILD IS AND IS NOT. It is NOT the game: `game_main_loop` is `jmp`ed into with a stage
 * already loaded, and the chain that loads one (the FDC driver, the Copylock, the tile installer,
 * `sprites_cru_install`) is unported — two of those are not even reconstructed, so their products
 * cannot be computed host-side today. gen_image.py's honesty line has the full list. What this build
 * IS: the first execution of reconstructed Wonder Boy code on a 68000, driven by a real machine.
 *
 * WHAT M1 ASSERTS, and it is chosen for what a PROGRAM IMAGE plus a REAL MACHINE can show:
 *
 *   1. `vbl_handler` (../src/game.c:334) runs on the level-4 autovector fifty times a second and its
 *      word tracks the machine's vblanks. Two independent counters — the shim's own tick count and
 *      the reconstruction's WB_VBL_COUNTER — and they must agree.
 *   2. `tempo_drop_value` (../src/sound.c:1055) chooses the music tempo from TWO REAL HARDWARE READS,
 *      and the byte it leaves in the image says which arm it took. This is PORTABILITY.md §5's
 *      false-green surface being closed: under the oracle $fffa01 and $ff820a answer whatever the
 *      case seeded and BuggyBoy shipped a green all the way to real hardware on exactly this
 *      register. The control is not a code change — it is BOOTING HATARI WITH A MONO MONITOR, which
 *      must move the byte from WB_SND_TICK_DROP_50HZ to WB_SND_TICK_DROP_MONO.
 *   3. `floppy_deselect_drives` -> `psg_set_drive_select` (../src/game.c:305) drives the REAL YM2149
 *      when the idle timer expires, and the register READS BACK with the three floppy lines high and
 *      the other five as they were.
 *   4. `sched_wait8` — the backend's uncapped spin — really ends, on a byte an interrupt really
 *      wrote. An IKBD reset is what provokes the byte; WHICH byte the controller answers with is
 *      not presumed here — `await_ikbd_reply` learns it and a second reset pins that it repeats.
 *   5. The screen base the reconstruction publishes is TRANSLATED onto the machine and reads back off
 *      the shifter as the address the image array actually lives at.
 *
 * WHAT M1 DOES NOT REACH is in README.md's milestone table, per surface, with the milestone that
 * will. The short version: no frame runs, so the four surviving shifter-sink mutants are not caught
 * here — only the base translation is.
 *
 * PRIVILEGE. Everything from the vector install to the teardown is SUPERVISOR, because the
 * backend's every read and write is I/O space ($ff8xxx, $fffaxx, $fffcxx) and a user-mode access to
 * those is a bus error. The original stays in supervisor for its whole run too. File I/O is done
 * OUTSIDE that window, in user mode, at both ends: GEMDOS handle allocation misbehaves when entered
 * from supervisor under Hatari's GEMDOS drive, which is a bug this workspace has already shipped
 * once (projects/buggyboy's game_os.s).
 */
#include <stdint.h>

#include "os.h"
#include "psg.h"
#include "sched.h"
#include "wonderboy.h"
#include "game.h"
#include "tos.h"
#include "wonderboy_target.h"

#ifndef PROGRAM_BYTES
#error "build.sh must pass -DPROGRAM_BYTES=<size of disk/WB.IMG>"
#endif
#ifndef WB_STAGED_AT
#error "build.sh must pass -DWB_STAGED_AT=<project.toml's load_base>"
#endif
#ifndef SMOKE_VBLS
#define SMOKE_VBLS 60          /* vblanks to run; 60 is well past FLOPPY_IDLE_TICKS in gen_image.py */
#endif

/* ---- M2: the frame build ----------------------------------------------------------------------
 *
 * `-DSMOKE_M2` swaps what the shim DOES between taking the machine and handing it back: M1 counts
 * vblanks, M2 calls `game_main_loop` (../src/game.c:477). Everything either side of that — the
 * staging, the vectors, the video mode, the read-backs, the teardown, the record — is the same code.
 *
 * IT IS THE IMAGE THAT MAKES M2 POSSIBLE, NOT THIS BLOCK. `game_main_loop` reads the tile bitmaps,
 * the overlay, the sprite pool and the eight scroll buffers, and none of them can be computed
 * host-side (gen_image.py's honesty line). `build.sh m2` stages the ORIGINAL's own post-boot RAM
 * instead, measured by atari/original.py at `$f8b4` — the boot's last instruction. */
#ifdef SMOKE_M2
#ifndef M2_ENTRY_UNWIND
#error "build.sh m2 must pass -DM2_ENTRY_UNWIND=<A5 at the anchor, from build/ORIGREGS.txt>"
#endif
/* WHICH FRAMES ARE PHOTOGRAPHED, and the list is chosen by MEASUREMENT of the shipped binary rather
 * than by taste. AN ANCHOR IS ONLY EVIDENCE IF A MIS-ANCHOR IS DETECTABLE, and this game at the top
 * of stage 1 draws the SAME PICTURE every frame: with no stick pushed the hero stands still and
 * nothing moves. Differencing the shipped binary's own consecutive frames over its first seventy
 * (`original.py frames 70`) finds exactly two boundaries where the screen changes, and each moves
 * the same 988 of 32000 bytes over 24 scanlines from row 60:
 *
 *     frame 1 -> 2     the first frame this loop draws, over what the boot left
 *     frame 51 -> 52   the same region again, fifty frames — one second — later
 *
 * AND IT IS A BLINK, NOT A COUNTER, which the anchors themselves measure: frame 52 is byte-identical
 * to frame 1 and frame 51 to frame 2, so the picture TOGGLES between two states on a one-second
 * cadence rather than advancing. That is why smoke.py's mis-anchor control can break only two of its
 * eight rows and prints the other six as excluded — with a toggling picture, half the shifts land on
 * an identical frame.
 *
 * So the anchors are the two frames either side of each boundary. A match at 2 that was really a
 * match at 3 would show 988 wrong bytes, and so would a match at 52 read off 51. Both sides use
 * THIS list: original.py scrapes it out of this line. */
#define M2_ANCHOR_FRAMES 1, 2, 51, 52
#endif

/* ---- the image -------------------------------------------------------------------------------
 *
 * 1 MiB, plus 256 bytes of slack the base is rounded up into. THE ROUND-UP IS NOT COSMETIC: an STF's
 * video base register has no low byte ($ffff8201/8203 hold bits 23-16 and 15-8 and there is no
 * $ffff820d), so an unaligned base is TRUNCATED and the shifter displays from up to 255 bytes below
 * what the game draws at — every byte in memory still correct, the picture's bitplanes permuted
 * (docs/on-target-execution.md, taxonomy 8). A `__attribute__((aligned(256)))` does NOT fix it: it
 * aligns the array inside .bss, and GEMDOS loads the .PRG wherever the TPA falls. The round-up is
 * done once, here, at run time, and READ BACK. */
#define IMAGE_ALIGN 256u

static uint8_t image_storage[OS_IMAGE_SIZE + IMAGE_ALIGN];
static uint8_t *game_image;

uint32_t wb_target_image_base(void) {
    return (uint32_t)(uintptr_t)game_image;
}

/* One big-endian image word. `bus_read_word` is not used and this is not an oversight: that is the
 * RECONSTRUCTION's accessor, with the kit's out-of-image answer behind it, and the image is a plain
 * array to the shim. */
static uint16_t image_word(uint32_t at) {
    return (uint16_t)(((uint16_t)game_image[at] << 8) | game_image[at + 1u]);
}

/* ---- what the smoke reads back ---------------------------------------------------------------
 *
 * TWO WORDS, NOT ONE, and the reason is this workspace's sharpest recorded lesson: `readback_failed`
 * says a write did not take, `readback_attempted` says which checks RAN, and smoke.py compares the
 * second against an EXACT mask. A check that quietly stops executing is indistinguishable from a
 * passing one in a bare fault word — which is how Joust's exit detector spent a year scanning an
 * empty string. */
#define RB_IMAGE_BASE_ALIGNED    0u
#define RB_VBL_VECTOR_INSTALLED  1u
#define RB_ACIA_VECTOR_INSTALLED 2u
#define RB_RESOLUTION_SET        3u
#define RB_SYNC_SET              4u
#define RB_SCREEN_BASE_PUBLISHED 5u
#define RB_VBL_TICKING           6u
#define RB_IKBD_REPLIED          7u
#define RB_PSG_PORT_A_DESELECTED 8u
#define RB_VBL_VECTOR_RESTORED   9u
#define RB_ACIA_VECTOR_RESTORED  10u
#define RB_RESOLUTION_RESTORED   11u
#define RB_SYNC_RESTORED         12u
#define RB_SCREEN_BASE_RESTORED  13u
#define RB_PSG_PORT_A_RESTORED   14u
#define RB_IKBD_DRAINED          15u

/* NOT written from the interrupt half, and that is why one pair is enough here where Joust needs
 * two: `x |= 1u << bit` is not interrupt-atomic on the 68000, but neither of this build's two
 * handlers records a read-back — `wb_vbl_tick` calls the reconstruction and counts, `wb_acia_byte`
 * files a byte. The moment one of them gains a check it needs its own pair, and README.md says so. */
static uint16_t readback_failed;
static uint16_t readback_attempted;

static void checked(unsigned bit, int ok) {
    readback_attempted |= (uint16_t)(1u << bit);
    if (!ok)
        readback_failed |= (uint16_t)(1u << bit);
}

/* ---- hardware, in the 32-bit forms the CPU decodes -------------------------------------------
 *
 * wonderboy_backend.c translates the reconstruction's 24-bit constants; this file spells the
 * machine's own registers, which the reconstruction has no name for. */
#define VEC_LEVEL4_VBL   0x70u    /* `$70 := $716` — hw_init_vectors ($f8bc), ../names.txt */
#define VEC_MFP_ACIA     0x118u   /* `$118 := $754` — the same routine */
#define SHIFTER_RES      0xffff8260u  /* video_set_lowres_50hz ($f906): `:= 0`, 320x200x16 */
#define SHIFTER_SYNC     0xffff820au  /* ...and `:= 2`, 50 Hz PAL. os.h calls it OS_HW_SHIFTER_SYNC */
#define SHIFTER_BASE_HI  0xffff8201u
#define SHIFTER_BASE_MID 0xffff8203u
#define ACIA_STATUS      0xfffffc00u  /* IKBD ACIA; bit 1 = transmit data register empty */
#define ACIA_DATA        0xfffffc02u
#define ACIA_TDRE_BIT    1u

/* The sixteen colour registers, in the 32-bit form the CPU decodes. `WB_SHIFTER_PALETTE` is the
 * reconstruction's own 24-bit spelling of the SAME register — the high byte is the I/O page a
 * 68000's address bus ignores and a compiler does not — so the register number has one definition
 * and this derives from it rather than restating $ffff8240. */
#define SHIFTER_IO_PAGE  0xff000000u
#define SHIFTER_PALETTE  (SHIFTER_IO_PAGE | WB_SHIFTER_PALETTE)

#define LOW_RESOLUTION   0u
/* THE RESOLUTION REGISTER IS TWO BITS WIDE and the other six read back as whatever was last on the
 * bus, so a read-back must mask — measured on the first on-target run, where the unmasked compare
 * was one of three checks that failed against a machine that had in fact done what it was told.
 * The video-base bytes above have no such problem: they are full bytes of a real latch. */
#define SHIFTER_RES_MASK 0x03u

/* IKBD commands, spelt as the ORIGINAL's boot spells them where it has an opinion. */
#define IKBD_RESET_0     0x80u   /* the two-byte reset; the controller answers with a status byte
                                  * whose VALUE this build does not presume — see await_ikbd_reply */
#define IKBD_RESET_1     0x01u
/* The byte gen_image.py seeds WB_KEY_LAST_SCANCODE to, i.e. "the controller has not spoken". Zero is
 * safe as that sentinel because it is not a scancode the IKBD can send: scancode 0 does not exist,
 * and every status and header byte it does send has bit 7 set. */
#define IKBD_NOTHING_SAID 0x00u
#define IKBD_MOUSE_REL   0x08u   /* teardown: put the desktop's mouse back on relative reporting */
/* ../names.txt cmt 0x754: "$FE/$FF are the IKBD joystick-report headers". Not in
 * ../include/wonderboy.h because the handler that decodes them ($754) is unported and no
 * reconstructed routine names them; this shim stands in for that handler, so it names them. */
#define IKBD_JOY0_HEADER 0xfeu
#define IKBD_JOY1_HEADER 0xffu

/* ../names.txt's `var 0x876 joy0_state`. Not in ../include/wonderboy.h because no reconstructed
 * routine reads it — the port's input is joystick 1 alone — but ikbd_acia_handler ($754) files both,
 * and this shim stands in for that handler. */
#define WB_JOY0_STATE    0x876u

static volatile uint8_t *io8(uint32_t addr) { return (volatile uint8_t *)(uintptr_t)addr; }
static volatile uint32_t *io32(uint32_t addr) { return (volatile uint32_t *)(uintptr_t)addr; }


/* ---- the two interrupt bodies -----------------------------------------------------------------
 *
 * wonderboy_os.s owns each entry's `movem` pair, the MFP end-of-interrupt and the `rte`; these are
 * the bodies, and the first of them is the RECONSTRUCTION, called unchanged. */

static volatile uint32_t shim_vbl_ticks;   /* the shim's own clock — the independent half of M1's
                                            * first assertion, and the run loop's watchdog */

void wb_vbl_tick(void) {
    shim_vbl_ticks++;
    vbl_handler(game_image);               /* ../src/game.c:334 — $716, verified, unchanged */
}

/* The handler the reconstruction does NOT have. `ikbd_acia_handler` ($754) is unported, and it is
 * what writes the byte `sched_wait8` spins on, so without this the two key waits are hangs.
 *
 * ../names.txt cmt 0x754 is the whole specification: read the IKBD byte from $fffffc02; `$fe`/`$ff`
 * are the joystick-report headers, after which the NEXT interrupt's byte is the report; anything
 * else is a key scancode. The original re-vectors $118 to two one-shot handlers to remember which;
 * a state byte here does the same thing and costs no vector traffic.
 *
 * THE KEY BITMAP IS DELIBERATELY NOT REPRODUCED. The original also folds each scancode into
 * `key_bits` ($878) against the watch table at $87a — and ../names.txt cmt 0x878 establishes that
 * the table is all zeroes with no writer, so no scancode can ever match and nothing in the image
 * ever reads $878. Reproducing a provably dead path would be inventing work; the raw scancode at
 * WB_KEY_LAST_SCANCODE, which FIVE readers do use, is stored. */
static volatile uint32_t acia_report_slot;   /* image offset the next byte belongs to, or 0 */
static volatile uint32_t ikbd_bytes;
/* The last byte the controller sent, kept for the record. Not an assertion — a DIAGNOSTIC, and it
 * earned its place on the first on-target run, where "one byte arrived and it was not the reply"
 * and "no byte arrived" were indistinguishable from the counter alone. */
static volatile uint8_t ikbd_last_byte;

void wb_acia_byte(void) {
    uint8_t byte = *io8(ACIA_DATA);

    ikbd_bytes++;
    ikbd_last_byte = byte;
    if (acia_report_slot) {
        game_image[acia_report_slot] = byte;
        acia_report_slot = 0;
        return;
    }
    if (byte == IKBD_JOY0_HEADER) {
        acia_report_slot = WB_JOY0_STATE;
        return;
    }
    if (byte == IKBD_JOY1_HEADER) {
        acia_report_slot = WB_JOY1_STATE;
        return;
    }
    game_image[WB_KEY_LAST_SCANCODE] = byte;
}


/* ---- staging ----------------------------------------------------------------------------------
 *
 * The .IMG is the relocated program plus gen_image.py's named seeds, and its LENGTH is passed in by
 * build.sh from the file itself rather than written down twice. A short read is a hard stop: every
 * table the cores index lives in those bytes. */
#define FO_READ 0

static const char IMAGE_FILE[] = "WB.IMG";

static int stage_file(const char *name, long length, void *into) {
    long handle = Fopen(name, FO_READ);
    long got;

    if (handle < 0)
        return 0;
    got = Fread((short)handle, length, into);
    (void)Fclose((short)handle);
    return got == length;
}

static int stage_image(void) {
    return stage_file(IMAGE_FILE, PROGRAM_BYTES, game_image + WB_STAGED_AT);
}


/* ---- the machine, taken and handed back -------------------------------------------------------
 *
 * Everything installed is snapshotted first and restored at the end, and every restore is READ BACK.
 * That is not hygiene: Joust's build left the IKBD in interrogation mode with a handler chaining
 * commands out of memory GEMDOS had taken back, and the measured result was a double bus error and a
 * halted CPU a second AFTER the program exited — visible only because the smoke ran the emulator on
 * past the dump instead of killing it. */
struct saved_machine {
    uint32_t vbl_vector;
    uint32_t acia_vector;
    uint8_t  resolution;
    uint8_t  sync;
    uint8_t  psg_port_a;
    uint32_t tos_logbase;
    uint32_t tos_physbase;
};

static struct saved_machine saved;

static void snapshot(void) {
    saved.vbl_vector = *io32(VEC_LEVEL4_VBL);
    saved.acia_vector = *io32(VEC_MFP_ACIA);
    saved.resolution = *io8(SHIFTER_RES);
    saved.sync = *io8(SHIFTER_SYNC);
    saved.psg_port_a = psg_port_read(WB_PSG_REG_PORT_A);
}

/* EVERY WAIT IN THIS FILE IS BOUNDED BY A SPIN COUNT, NOT BY THE VBLANK CLOCK, and that is not a
 * preference: `teardown` waits for the ACIA to drain, and by then the vector that advances
 * `shim_vbl_ticks` may be the one being taken out. A clock a wait can stop is not a bound.
 *
 * THE TWO NUMBERS ARE MEASURED, not guessed, and the first draft's were wrong in the expensive
 * direction: at 40M the long wait alone outran Hatari's whole `--run-vbls 6000` (120 s of emulated
 * time) and the mode reported "no STATS.BIN" for a build that was working. Calibrated from that
 * run — ~24 cycles an iteration at 8 MHz — 2M iterations is ~6 s, comfortably longer than the IKBD
 * reset's ~300 ms reply and a small fraction of the run; 100k is ~0.3 s, which a transmitter that
 * needs 1.28 ms per byte cannot exhaust. */
#define SPINS_SHORT   100000u
#define SPINS_LONG   2000000u

/* Hand the IKBD a byte, once its transmitter has room. The original's own `ikbd_disable_mouse`
 * ($f8f8) does exactly this — poll $fffc00 for transmit-ready and store to $fffc02 — rather than
 * going through XBIOS Ikbdws, and this build has no reason to differ. */
static int ikbd_tx_ready(uint32_t spins) {
    while (!(*io8(ACIA_STATUS) & (1u << ACIA_TDRE_BIT)))
        if (--spins == 0)
            return 0;
    return 1;
}

static int ikbd_send(uint8_t byte) {
    if (!ikbd_tx_ready(SPINS_SHORT))
        return 0;
    *io8(ACIA_DATA) = byte;
    return 1;
}

static int ikbd_reset(void) {
    return ikbd_send(IKBD_RESET_0) && ikbd_send(IKBD_RESET_1);
}

/* Wait for the controller to say something, and return WHAT IT SAID rather than checking it against
 * a byte written down here.
 *
 * THE ACKNOWLEDGE BYTE IS DISCOVERED, AND THE FIRST DRAFT ASSUMED IT. The IKBD's documented
 * self-test-passed answer to `$80 $01` is `$f0`; the machine this ran on answered `$f1`, and the
 * mode failed on a path that was working perfectly. Which byte a controller sends is a property of
 * that controller's firmware, not of this port, and the interesting question was never "is it $f0" —
 * it is "did an interrupt write the byte the reconstruction spins on". So phase one learns the
 * answer and phase two pins that it REPEATS, which is a stronger claim than the constant was.
 *
 * THE READ IS `volatile`, AND THE FIRST DRAFT'S WAS NOT — also measured, on the very first
 * on-target run. `game_image` is a plain array to the compiler and nothing the loop body does can
 * change the byte, so GCC hoisted the load and the wait spun out its bound on a stale value. It is
 * the hazard wonderboy_backend.c's `sched_wait8` exists to not have, and it bit the SHIM instead —
 * one file over from where the comment about it is written. */
static uint8_t await_ikbd_reply(void) {
    volatile uint8_t *scancode = (volatile uint8_t *)(game_image + WB_KEY_LAST_SCANCODE);
    uint32_t spins = SPINS_LONG;
    uint8_t seen;

    while ((seen = *scancode) == IKBD_NOTHING_SAID)
        if (--spins == 0)
            return IKBD_NOTHING_SAID;
    return seen;
}

static void install(void) {
    checked(RB_IMAGE_BASE_ALIGNED, ((uintptr_t)game_image & (IMAGE_ALIGN - 1u)) == 0);

    /* SMOKE_NO_VBL_INSTALL is M1's negative control (build.sh novbl), and it is deliberately the
     * SMALLEST possible difference: one store suppressed, everything else — the ACIA handler, the
     * video mode, the screen-base translation, the teardown, the record — identical. What must then
     * fail is every assertion that depends on the MACHINE driving the reconstruction. */
#ifndef SMOKE_NO_VBL_INSTALL
    *io32(VEC_LEVEL4_VBL) = (uint32_t)(uintptr_t)wb_vbl_entry;
#endif
    checked(RB_VBL_VECTOR_INSTALLED, *io32(VEC_LEVEL4_VBL) == (uint32_t)(uintptr_t)wb_vbl_entry);

    *io32(VEC_MFP_ACIA) = (uint32_t)(uintptr_t)wb_acia_entry;
    checked(RB_ACIA_VECTOR_INSTALLED, *io32(VEC_MFP_ACIA) == (uint32_t)(uintptr_t)wb_acia_entry);

    /* video_set_lowres_50hz ($f906), minus the screen base, which goes out below through the
     * reconstruction's own translated path instead of as a raw poke. MFP timers A and B are NOT
     * masked, although the boot masks them ($e4e6: IERA/IMRA := 0): this build hands the machine
     * back and does GEMDOS I/O afterwards, both of which want TOS's own clock alive. The deviation
     * changes interrupt load, not an image byte, and is recorded in README.md. */
    *io8(SHIFTER_RES) = LOW_RESOLUTION;
    checked(RB_RESOLUTION_SET, (*io8(SHIFTER_RES) & SHIFTER_RES_MASK) == LOW_RESOLUTION);
    *io8(SHIFTER_SYNC) = WB_SHIFTER_SYNC_50HZ;
    checked(RB_SYNC_SET, (*io8(SHIFTER_SYNC) & WB_SHIFTER_SYNC_50HZ) == WB_SHIFTER_SYNC_50HZ);
}

/* Publish the image's own front buffer, through the SAME translation `flip_screen`'s two sink writes
 * take. The two bytes are the image's, read exactly where flip_screen reads them ($74d/$74e, i.e.
 * bits 23-16 and 15-8 of WB_SCREEN_FRONT), so this is the boot's `screen base := $70000` performed
 * on the reconstruction's terms rather than on the shim's. */
static void publish_screen_base(void) {
    uint32_t want;

    wb_target_shifter_byte(WB_SHIFTER_SCREEN_BASE_HIGH, game_image[WB_SCREEN_FRONT_BITS_16_23]);
    wb_target_shifter_byte(WB_SHIFTER_SCREEN_BASE_MID, game_image[WB_SCREEN_FRONT_BITS_8_15]);

    want = wb_target_screen_base;
    checked(RB_SCREEN_BASE_PUBLISHED,
            *io8(SHIFTER_BASE_HI) == (uint8_t)(want >> 16)
            && *io8(SHIFTER_BASE_MID) == (uint8_t)(want >> 8));
}

static void teardown(void) {
    *io32(VEC_LEVEL4_VBL) = saved.vbl_vector;
    checked(RB_VBL_VECTOR_RESTORED, *io32(VEC_LEVEL4_VBL) == saved.vbl_vector);
    *io32(VEC_MFP_ACIA) = saved.acia_vector;
    checked(RB_ACIA_VECTOR_RESTORED, *io32(VEC_MFP_ACIA) == saved.acia_vector);

    *io8(SHIFTER_RES) = saved.resolution;
    checked(RB_RESOLUTION_RESTORED,
            (*io8(SHIFTER_RES) & SHIFTER_RES_MASK) == (saved.resolution & SHIFTER_RES_MASK));
    *io8(SHIFTER_SYNC) = saved.sync;
    checked(RB_SYNC_RESTORED, *io8(SHIFTER_SYNC) == saved.sync);

    *io8(SHIFTER_BASE_HI) = (uint8_t)(saved.tos_physbase >> 16);
    *io8(SHIFTER_BASE_MID) = (uint8_t)(saved.tos_physbase >> 8);
    checked(RB_SCREEN_BASE_RESTORED,
            *io8(SHIFTER_BASE_HI) == (uint8_t)(saved.tos_physbase >> 16)
            && *io8(SHIFTER_BASE_MID) == (uint8_t)(saved.tos_physbase >> 8));

    psg_port_write(WB_PSG_REG_PORT_A, saved.psg_port_a);
    checked(RB_PSG_PORT_A_RESTORED, psg_port_read(WB_PSG_REG_PORT_A) == saved.psg_port_a);

    /* The IKBD is put back with the two commands its own reset displaced.
     *
     * THE WEAKEST CHECK IN THE FILE, and stated as such. The DRAIN IS WAITED FOR — asserting TDRE
     * the instant `ikbd_send` returns tests timing rather than delivery, because the transmitter
     * only just took the byte, and the first on-target run failed exactly there. Even waited for,
     * TDRE means the last byte reached the SHIFT register and is still going out for another
     * ~1.28 ms, so this witnesses every byte but the final one — and a byte that leaves says nothing
     * about the controller obeying it. It is the strongest reading a write-only device offers. */
    (void)ikbd_reset();
    (void)ikbd_send(IKBD_MOUSE_REL);
    checked(RB_IKBD_DRAINED, ikbd_tx_ready(SPINS_SHORT));
}


/* ---- the record --------------------------------------------------------------------------------
 *
 * Written after the hand-back, in user mode, as one big-endian struct. smoke.py names every field in
 * the same order and CHECKS THE SIZE, so a field added in C and not in Python is a loud parse error
 * rather than a silently misread record. */
#define STATS_MAGIC   0x57424131u   /* 'WBA1' */

struct stats {
    uint32_t magic;
    uint32_t bytes;                 /* sizeof(struct stats) — the version check */
    uint32_t image_base;
    uint32_t screen_base_published;
    uint32_t shim_vbl_ticks;
    uint32_t ikbd_bytes;
    uint16_t readback_failed;
    uint16_t readback_attempted;
    uint16_t vbl_counter;           /* the image's WB_VBL_COUNTER — the reconstruction's own clock */
    uint16_t floppy_idle_timer;     /* ...and the countdown vbl_handler decremented to reach the PSG */
    uint8_t  tick_drop_value;       /* which arm tempo_drop_value's two REAL hardware reads chose */
    uint8_t  psg_port_a_at_entry;
    uint8_t  psg_port_a_after_run;
    uint8_t  key_last_scancode;
    uint8_t  sched_wait_returned;
    uint8_t  ikbd_last_byte;
    uint8_t  pad[2];
};

#define FCREATE_RW 0

static const char STATS_FILE[] = "STATS.BIN";

/* The one file writer. Both records and both capture files come through here — an earlier draft had
 * M2's own copy of these five lines beside this one. */
static void write_file(const char *name, const void *data, long length) {
    long handle = Fcreate(name, FCREATE_RW);

    if (handle < 0)
        return;
    (void)Fwrite((short)handle, length, data);
    (void)Fclose((short)handle);
}

static void dump_stats(const struct stats *record) {
    write_file(STATS_FILE, record, (long)sizeof(*record));
}


/* ---- M2's own record, and the two surfaces it exists to carry off the machine -------------------
 *
 * A SECOND FILE RATHER THAN FOUR MORE FIELDS IN `struct stats`, and that is not filing: smoke.py
 * checks STATS.BIN's size against a format string, so growing the record per build mode would make
 * the M1 parser's own version check fire on an M2 run and vice versa. Two records, two magics, two
 * readers, and neither can silently misread the other's bytes. */
#ifdef SMOKE_M2
#define M2_MAGIC 0x57424132u        /* 'WBA2' */
/* How many anchors the record has room to carry. Not a limit on M2_ANCHOR_FRAMES — the static
 * assertion below refuses a longer list rather than truncating one. */
#define M2_ANCHOR_MAX 8u
/* DERIVED, not restated. Both numbers already have one canonical definition in ../include/
 * wonderboy.h, which ../test/layout.py scrapes for the Python side — so smoke.py and this file
 * compute them from the SAME two constants instead of each writing 32000 and 16 down. */
#define SCREEN_BYTES (WB_SCREEN_LINE * WB_SCREEN_SCANLINES)
#define PALETTE_PENS WB_PALETTE_COLOURS
/* The ST implements THREE bits per gun; the fourth bit of each nibble does not exist and a CPU read
 * of a colour register returns it as whatever was last on the bus. A read-back compare that did not
 * mask would fail against a shifter that had done exactly what it was told — which is the same
 * lesson the resolution register taught this file on its first on-target run, one register over. */
#define ST_PEN_MASK  0x0777u

static const char M2_FILE[] = "M2.BIN";
static const char FRAME_FILE[] = "FRAME.BIN";
static const char PENS_FILE[] = "PENS.BIN";
/* The pens the ORIGINAL's boot left in the shifter, staged beside WB.IMG.
 *
 * THE PALETTE IS THE BOOT'S PRODUCT AND IT DOES NOT LIVE IN RAM. `set_palette` is called from
 * `stage_load_window`, inside the unported chain, so an M2 build that staged only memory paints its
 * frame through whatever owned the shifter last — measured on the first M2 run, which came back
 * with TOS 1.04's own desktop palette (777 700 070 770 ...). This is the same sentence as the image
 * itself: the boot's result handed over, because the boot is not ported. */
static const char STAGED_PENS_FILE[] = "PENS.IMG";
static uint16_t staged_pens[PALETTE_PENS];

struct m2_stats {
    uint32_t magic;
    uint32_t bytes;
    uint32_t image_base;
    uint32_t frames_requested;
    uint32_t frames_run;
    uint32_t loop_ending;           /* the WB_KEY_ACTIONS_* the last iteration returned */
    uint32_t screen_front;          /* the image-space longword the last flip published */
    uint32_t screen_base_published; /* ...and the machine address it was translated to */
    uint32_t poll16_calls;          /* sched_poll16's iteration count — see run_frames */
    uint32_t shim_vbl_ticks;
    /* Which of the sixteen staged pens did not read back off the shifter, as a bit each. NOT an
     * RB_* bit: smoke.py compares `readback_attempted` against an EXACT mask, so a bit only the M2
     * build ever attempts would make the M1 run's own version check fire. Two records, two readers.
     */
    uint32_t pens_readback_failed;
    /* WHAT THE SHIFTER ITSELF HOLDS after the last frame, read back off $ffff8201/8203.
     *
     * THIS IS THE ROW THAT CATCHES THE TWO FLIP-SITE MUTANTS AND THE FRAMEBUFFER COMPARE CANNOT.
     * `flip_screen`'s two `shifter_write_byte`s change no image byte — they change which buffer the
     * hardware DISPLAYS — so publishing the back buffer instead of the front, or sending the two
     * base bytes to each other's registers, leaves every pixel this run compares untouched and
     * every one of them correct. What moves is this number.
     *
     * Read off the hardware rather than taken from `wb_target_screen_base`, which is what the
     * backend believes it wrote. */
    uint32_t shifter_base;
    /* Set when `screen_front` named an address outside the image, i.e. the capture was refused
     * rather than taken. Its own field because "no capture" and "a capture of zeros" are the same
     * bytes in FRAME.BIN, and only one of them is a reconstruction defect. */
    uint32_t screen_front_out_of_range;
    /* WHERE `capture_the_frame` IS, AT RUN TIME — the address M5's debugger script breakpoints so
     * that the hardware-state vector is taken at the very instant this shim photographs the frame.
     *
     * REPORTED BY THE BINARY ABOUT ITSELF rather than read out of build/wonderboy.elf: that ELF is
     * overwritten by every build while the per-mode .PRGs persist, so it is not necessarily the
     * running program's — the sibling project once anchored four bytes out off a stale one and went
     * green on the wrong breakpoint. A binary reporting its own address cannot be the wrong binary.
     * smoke.py additionally re-reads this field from the DEBUGGER run and requires it to equal the
     * value the first run reported, which is what pins GEMDOS having placed the program identically
     * in both. */
    uint32_t capture_pc;
    /* WB_FLASH_TIMER AS THE FRAME LOOP FINDS IT, and it is a measurement in both builds. Zero is the
     * staged image's own value — the reason `flip_screen`'s flash arms are unreachable across all
     * fifty-two frames, which atari/README.md §9 cites — and M5_FLASH_SEED is what a run that arms
     * them declares. Read back out of the image AFTER any seeding, so the field witnesses the write
     * landing rather than the constant the build was given. */
    uint32_t flash_timer_at_entry;
    /* WHICH PEN THIS BUILD CORRUPTED on its way to the shifter, or PALETTE_PENS for "none".
     *
     * REPORTED BY THE BINARY, for `capture_pc`'s reason one control over: the per-mode `.PRG`s
     * persist while atari/build.sh is edited, so a smoke that scraped `-DM5_FAULT_PEN=` out of the
     * script would be naming a pen the running binary need not have injected. The sentinel is
     * OUT OF BAND — a pen number is 0..15 and this is 16 — so "no fault" cannot collide with pen 0. */
    uint32_t fault_pen;
    /* THE ANCHOR LIST THE BINARY WAS COMPILED WITH, carried off the machine rather than re-read.
     * smoke.py scrapes the same `#define` out of this file at CHECK time, so without this the two
     * can be from different edits: change M2_ANCHOR_FRAMES and run the smoke without rebuilding,
     * and the count still matches, the size row still passes, and slot 2 — the binary's frame 51 —
     * is compared against, and LABELLED, the shipped frame 50. A green or a red, both mislabelled.
     * Fixed-width so the record's own `bytes` field pins the layout; `anchor_count` says how much
     * of it is real. */
    uint32_t anchor_count;
    uint16_t anchor_frames[M2_ANCHOR_MAX];
};

/* The anchor frames, and only those: fifty-two whole screens would be 1.6 MB of bss on a machine
 * that has 4 MB and is already carrying a 1 MiB image. Static because a 32000-byte automatic would
 * be a stack this shim does not have. */
static const uint16_t m2_anchors[] = { M2_ANCHOR_FRAMES };
#define M2_ANCHOR_COUNT (sizeof(m2_anchors) / sizeof(m2_anchors[0]))
/* A list longer than the record can carry would be SILENTLY truncated in the report while the
 * capture arrays sized themselves correctly — a mislabelling, not a crash. Refuse it at compile
 * time instead. */
typedef char m2_anchor_list_fits[(M2_ANCHOR_COUNT <= M2_ANCHOR_MAX) ? 1 : -1];
/* HOW MANY FRAMES THE LOOP RUNS: the last anchor, DERIVED. An earlier draft wrote the number down a
 * second time on the line under M2_ANCHOR_FRAMES, under a comment claiming it had not — and that is
 * the duplication with teeth, because extending the anchor list without noticing would leave the
 * later slots as zeroed bss and report them as full-screen rendering divergences. */
#define M2_LAST_ANCHOR (m2_anchors[M2_ANCHOR_COUNT - 1u])

static uint8_t captured_frames[M2_ANCHOR_COUNT][SCREEN_BYTES];
static uint16_t captured_pens[M2_ANCHOR_COUNT][PALETTE_PENS];

/* Which slot a 1-based frame number is photographed into, or M2_ANCHOR_COUNT for "not an anchor". */
static unsigned anchor_slot(uint32_t frame) {
    unsigned slot;

    for (slot = 0; slot < M2_ANCHOR_COUNT; slot++)
        if (m2_anchors[slot] == frame)
            return slot;
    return M2_ANCHOR_COUNT;
}

/* Publish the staged palette, through the SAME sink `set_palette` writes it through — one call per
 * colour, which is `../src/stage.c`'s own iteration and not a loop over an indexed pointer (that
 * addressing mode is what put Joust's sixteenth pen in the resolution register). Read back per pen,
 * because a partially-published palette and a fully-published one differ by one wrong colour. */
/* M5'S SENSITIVITY CONTROL, and it is a real injected fault rather than a rearrangement of numbers
 * already in hand. One pen is corrupted on its way to the shifter — the palette the hardware ends up
 * holding is wrong by exactly one register while every byte the reconstruction DRAWS is untouched —
 * so the surfaces that read the machine's colour (the pen compare and the hardware-state vector)
 * must go red and the framebuffer compare must not. smoke.py's `m5fault` names both halves.
 *
 * The corrupted value is the pen's own bits inverted inside ST_PEN_MASK, so the fault cannot be
 * masked away and cannot collide with the right answer. */
/* Out of band on purpose: a pen number is 0..15, so this cannot be mistaken for pen 0. */
#define NO_FAULTED_PEN PALETTE_PENS
#ifdef M5_FAULT_PEN
#define FAULTED_PEN M5_FAULT_PEN
static uint16_t faulted(unsigned pen, uint16_t value) {
    return pen == M5_FAULT_PEN ? (uint16_t)(value ^ ST_PEN_MASK) : value;
}
#else
#define FAULTED_PEN NO_FAULTED_PEN
static uint16_t faulted(unsigned pen, uint16_t value) { (void)pen; return value; }
#endif

static void publish_staged_pens(struct m2_stats *record) {
    unsigned pen;

    for (pen = 0; pen < PALETTE_PENS; pen++) {
        uint32_t reg = WB_SHIFTER_PALETTE + pen * sizeof(uint16_t);
        /* THE READ-BACK IS AGAINST WHAT WAS PUBLISHED, not against the staged word, and the
         * distinction is what keeps `m5fault` a targeted control: the shim really did put this value
         * in the register, so its own plumbing check stays green and the only thing that reddens is
         * the DIFFERENTIAL against the shipped binary. A control whose run is unsound proves
         * nothing, and a corrupted publish that also broke this row would look like one. */
        uint16_t published = faulted(pen, staged_pens[pen]);

        wb_target_shifter_word(reg, published);
        if ((*(volatile uint16_t *)(uintptr_t)(SHIFTER_PALETTE + pen * sizeof(uint16_t))
             & ST_PEN_MASK) != (published & ST_PEN_MASK))
            record->pens_readback_failed |= 1u << pen;
    }
}

/* The two surfaces, read where each of them really lives: the picture out of the IMAGE at the
 * address the game itself published, and the pens off the SHIFTER. Neither is read from a place the
 * reconstruction chose to put a copy — that would compare our intention with the original's pixels.
 *
 * `noinline` BECAUSE ITS ENTRY IS AN ANCHOR: M5 breakpoints this address to take the hardware-state
 * vector at the same instant the two surfaces above are captured, and its Nth arrival IS the Nth
 * anchor. Inlined, `capture_pc` would name an out-of-line copy the run never enters and the vector
 * would simply never be taken — a loud failure rather than a wrong one, but a needless one. */
static __attribute__((noinline)) void capture_the_frame(struct m2_stats *record, unsigned slot) {
    uint32_t front = ((uint32_t)game_image[WB_SCREEN_FRONT] << 24)
                     | ((uint32_t)game_image[WB_SCREEN_FRONT + 1] << 16)
                     | ((uint32_t)game_image[WB_SCREEN_FRONT + 2] << 8)
                     | game_image[WB_SCREEN_FRONT + 3];
    unsigned pen;

    record->screen_front = front;
    /* THE ADDRESS IS BOUNDED BEFORE IT IS FOLLOWED, and it is the one image value this shim reads
     * that the reconstruction could get WRONG — a bad `flip_screen` publish is precisely what M2
     * exists to catch. Unbounded, that failure would `memcpy` 32000 bytes from outside
     * `image_storage`, bus-error in supervisor, and take the run down with no record at all: the
     * detector destroyed by the defect it detects. Out of range the capture is skipped and
     * `screen_front` still carries the offending value, so the smoke sees the number and reds. */
    if (front > OS_IMAGE_SIZE - SCREEN_BYTES) {
        record->screen_front_out_of_range = 1u;
        return;
    }
    memcpy(captured_frames[slot], game_image + front, SCREEN_BYTES);
    for (pen = 0; pen < PALETTE_PENS; pen++)
        captured_pens[slot][pen] = *(volatile uint16_t *)(uintptr_t)(SHIFTER_PALETTE
                                                                     + pen * sizeof(uint16_t));
}

/* Run the reconstruction's own frame loop, and stop for any of three reasons rather than one.
 *
 * THE WATCHDOG IS NOT OPTIONAL AND IT IS NOT A CLOCK. `flip_screen`'s two waits are uncapped spins
 * on WB_VBL_COUNTER — that is the whole of `sched_poll16`'s on-target story — so a level-4 vector
 * that never fires turns this into a hang, and a hang reports nothing at all. `shim_vbl_ticks` is
 * the bound because it is the very thing whose absence would cause the hang: if the vblank is alive
 * the budget is generous, and if it is dead the loop exits immediately with a record.
 *
 * ONE FRAME IS TENS OF VBLANKS (~245,000 instructions, ../names.txt cmt 0x4a0), so the budget is
 * per frame and measured rather than a round number. */
/* THE BUDGET IS A TOTAL AND IT IS WELL INSIDE `--run-vbls`, which is the M1 lesson taken rather than
 * relearned: a bound longer than the harness's own limit is not a bound — the run simply ends and
 * the mode reports "no record", which says nothing about what went wrong. Measured: 52 frames cost
 * 583 vblanks (~11 each), so 2000 is well over three times the reading and still leaves the boot and
 * a tail inside smoke.py's run. (The figure was first written as an ESTIMATE of ~780 from a guessed
 * 15 vblanks a frame, beside a run that had already reported 583. Two numbers for one measurement,
 * and the one in the comment was the one nobody had measured.)
 *
 * WHAT IT CANNOT CATCH, stated because a watchdog's edge matters more than its middle: this is
 * checked BETWEEN frames, and `flip_screen`'s two waits are uncapped spins INSIDE one. A dead
 * level-4 vector therefore still hangs, and what ends that run is `--run-vbls` and a missing
 * M2.BIN. What this bounds is a loop that is merely far too slow. */
#define M2_VBL_BUDGET 2000u

/* ---- M5's DECLARED FABRICATION: arming the flash ------------------------------------------------
 *
 * `flip_screen`'s last four instructions are a white-screen flash — `tst.w $714.l` at `$6e4` gates
 * them, `subq.w #1,$714.l` at `$6ee` counts the frames, and the two exclusive arms at `$6f8` and
 * `$702` write colour 0 white or black. WB_FLASH_TIMER is `$0000` in the staged image, so all four
 * are dead across every one of the fifty-two frames, and the mutant that swaps the two arms survives
 * the whole differential suite for that reason and no other.
 *
 * IT CANNOT BE DRIVEN IN THIS WINDOW, and that is a census rather than an impression. The image has
 * exactly ONE writer that RAISES the timer — `move.w #$2,$714.w` at `$1328`, inside
 * `player_weapon_fire` ($1208), the LIGHTNING arm — and two independent gates stand in front of it
 * here: this run injects no joystick byte at all (so `joy1_newly_pressed()` can never read `$80`),
 * and the staged image's WB_EFFECT_RECORD_WRITE_PTR sits exactly at the list base, i.e. the player
 * holds no item to fire. Reaching it honestly needs an item collected and two frames of held input,
 * which is a milestone away.
 *
 * SO THE VALUE IS SEEDED, AND THE SEED IS THE ORIGINAL'S OWN OPERAND — `WB_PLAYER_LIGHTNING_FLASH`,
 * the `#$2` at `$1328` — applied to BOTH sides at the SAME instant: this shim writes it into the
 * image immediately before the first `game_main_loop`, and atari/original.py pokes the same word at
 * `$4a0`'s FIRST arrival, which is the boot's own `jmp` landing before any frame has run. Two frames
 * of countdown then put a white anchor and a black anchor inside the window, which is both arms.
 *
 * WHAT THIS IS NOT: it is not the game reaching the flash. It is the two sides given the same
 * unreachable state and required to agree about what they do with it, and atari/README.md §10 says
 * so where the claim is made. */
#ifdef M5_FLASH_SEED
static void arm_the_flash(void) {
    game_image[WB_FLASH_TIMER] = (uint8_t)(M5_FLASH_SEED >> 8);
    game_image[WB_FLASH_TIMER + 1u] = (uint8_t)M5_FLASH_SEED;
}
#else
static void arm_the_flash(void) { }
#endif

static uint32_t run_frames(struct m2_stats *record) {
    sprite_pass_regs sprites;
    uint32_t deadline = shim_vbl_ticks + M2_VBL_BUDGET;
    uint32_t frame;
    unsigned field;

    /* Zero, then the one field that is a real input. `sprite_draw_pass` has no argument — a6, a4 and
     * a2 come from `lea`s and everything else it reads is memory — so the only inherited register
     * that matters is a5, and it is the ORIGINAL's own, measured at the anchor. */
    for (field = 0; field < sizeof(sprites); field++)
        ((uint8_t *)&sprites)[field] = 0;
    sprites.blit.unwind = M2_ENTRY_UNWIND;

    for (frame = 0; frame < M2_LAST_ANCHOR; frame++) {
        unsigned slot;

        record->loop_ending = game_main_loop(game_image, &sprites);
        if (record->loop_ending != WB_KEY_ACTIONS_RETURNED)
            break;                  /* the loop was LEFT, exactly as the original's `jmp` leaves it */
        slot = anchor_slot(frame + 1);          /* the anchors are 1-based, like the debugger's hits */
        if (slot < M2_ANCHOR_COUNT)
            capture_the_frame(record, slot);
        /* THE TWO BREAKS COUNT DIFFERENTLY, and an earlier draft returned `frame` for both. The
         * unwind above happens INSTEAD of a frame, so `frame` is the number that completed; the
         * watchdog here happens AFTER one, so it is `frame + 1`. Reporting the smaller number would
         * have reddened "every frame ran" on a run that ran every frame it was asked for. */
        if (shim_vbl_ticks >= deadline)
            return frame + 1u;
    }
    return frame;
}

#endif /* SMOKE_M2 */


/* ---- the run ----------------------------------------------------------------------------------- */

/* An escape from the vblank loop that does not depend on the vblank loop's own clock, so a dead VBL
 * vector is a RED WITH A RECORD rather than a run Hatari has to kill.
 *
 * SPINS_LONG is ~6 s at 8 MHz against SMOKE_VBLS's 1.2 s, and the margin is the whole point of
 * sharing the constant: the `novbl` control's first run used a bound five times longer, outran
 * `--run-vbls`, and reported "no STATS.BIN" — which says nothing about WHICH checks the control
 * broke, and a control that cannot say that is not a control. */
static int run_vblanks(uint32_t want) {
    uint32_t spins = SPINS_LONG;

    while (shim_vbl_ticks < want)
        if (--spins == 0)
            return 0;
    return 1;
}

/* The `sched_wait8` pin, and it is a genuine spin rather than a byte already in place.
 *
 * The FIRST reset's reply is waited for on the shim's own bounded clock — that is what establishes
 * that this machine's IKBD answers at all. Only then is the byte cleared and a SECOND reset sent,
 * and `sched_wait8` called: it cannot hang, because the reply that will end it is the same reply the
 * bounded wait just observed. Without the first half this would be an uncapped spin taken on faith;
 * with it, the risk is a controller that answers once and not twice. */
static int pin_sched_wait8(void) {
    uint8_t acknowledge = ikbd_reset() ? await_ikbd_reply() : IKBD_NOTHING_SAID;

    checked(RB_IKBD_REPLIED, acknowledge != IKBD_NOTHING_SAID);
    if (acknowledge == IKBD_NOTHING_SAID)
        return 0;

    game_image[WB_KEY_LAST_SCANCODE] = IKBD_NOTHING_SAID;
    if (!ikbd_reset())
        return 0;
    return sched_wait8(game_image, WB_KEY_LAST_SCANCODE, acknowledge, WB_KEY_UNPAUSE_WAIT_PC);
}

/* M1's first assertion compares the RECONSTRUCTION's clock against the SHIM's, so the two have to be
 * read at one instant. THEY ARE READ WITH INTERRUPTS MASKED, and the reason is a race the first
 * draft had: `record.vbl_counter` was taken here, before the hand-back, and `record.shim_vbl_ticks`
 * in the trailing block after it, so a vblank anywhere in between left the shim one ahead and the
 * gate red on a correct build — perhaps once in a few thousand runs, which is exactly the frequency
 * at which a real red gets dismissed as flake.
 *
 * Masking rather than a retry loop: `wb_vbl_tick` increments the shim's counter BEFORE calling
 * `vbl_handler`, so a handler already in flight can write the image between two equal readings of
 * the shim's counter. wonderboy_os.s has the full argument.
 *
 * Everything read here is read BEFORE the hand-back, because the hand-back stops the handler that
 * writes it. `bus_read_word` is not used: this is the shim, not the reconstruction, and the image is
 * a plain array here. */
static void sample_the_two_clocks(struct stats *record) {
    unsigned short sr = wb_irq_disable();

    record->shim_vbl_ticks = shim_vbl_ticks;
    record->vbl_counter = image_word(WB_VBL_COUNTER);
    record->floppy_idle_timer = image_word(WB_FLOPPY_IDLE_TIMER);
    record->tick_drop_value = game_image[WB_SND_TICK_DROP_VALUE];
    record->key_last_scancode = game_image[WB_KEY_LAST_SCANCODE];
    wb_irq_restore(sr);
}

int wonderboy_main(void) {
    struct stats record;
#ifdef SMOKE_M2
    struct m2_stats m2;
#endif
    void *ssp;
    unsigned field;

    for (field = 0; field < sizeof(record); field++)
        ((uint8_t *)&record)[field] = 0;
#ifdef SMOKE_M2
    for (field = 0; field < sizeof(m2); field++)
        ((uint8_t *)&m2)[field] = 0;
#endif

    game_image = (uint8_t *)(((uintptr_t)image_storage + (IMAGE_ALIGN - 1u))
                             & ~(uintptr_t)(IMAGE_ALIGN - 1u));

    /* USER MODE: the staging read, and TOS's own screen, taken before anything moves. */
    if (!stage_image())
        return 1;
#ifdef SMOKE_M2
    if (!stage_file(STAGED_PENS_FILE, (long)sizeof(staged_pens), staged_pens))
        return 1;
#endif
    saved.tos_logbase = (uint32_t)Logbase();
    saved.tos_physbase = (uint32_t)Physbase();

    /* SUPERVISOR: every I/O-space access below would bus-error in user mode. */
    ssp = (void *)Super(0);

    snapshot();
    record.psg_port_a_at_entry = saved.psg_port_a;
    install();
    publish_screen_base();

#ifdef SMOKE_M2
    /* M2 runs FRAMES, and the vblank check comes with them rather than before them: `flip_screen`
     * waits for the counter twice per frame, so a run that produced frames produced vblanks. */
    publish_staged_pens(&m2);
    arm_the_flash();
    /* READ BACK OUT OF THE IMAGE, so the field witnesses the seed landing rather than repeating the
     * constant the build was given — and so the unseeded builds report the $0000 that is the whole
     * reason the flash arms are unreachable. */
    m2.flash_timer_at_entry = image_word(WB_FLASH_TIMER);
    m2.capture_pc = (uint32_t)(uintptr_t)&capture_the_frame;
    m2.fault_pen = FAULTED_PEN;
    m2.frames_requested = M2_LAST_ANCHOR;
    m2.frames_run = run_frames(&m2);
    checked(RB_VBL_TICKING, m2.frames_run == m2.frames_requested);
    /* IN SUPERVISOR, AND BEFORE THE TEARDOWN, which is the only window in which this means
     * anything: `teardown` puts TOS's own base back, and a read after that would report the
     * desktop's screen and pass for ever. */
    m2.shifter_base = ((uint32_t)*io8(SHIFTER_BASE_HI) << 16)
                      | ((uint32_t)*io8(SHIFTER_BASE_MID) << 8);
#else
    checked(RB_VBL_TICKING, run_vblanks(SMOKE_VBLS));
#endif
    record.psg_port_a_after_run = psg_port_read(WB_PSG_REG_PORT_A);
    checked(RB_PSG_PORT_A_DESELECTED,
            (record.psg_port_a_after_run & ~WB_PSG_PORT_A_KEEP) == WB_PSG_DRIVES_DESELECTED
            && (record.psg_port_a_after_run & WB_PSG_PORT_A_KEEP)
               == (saved.psg_port_a & WB_PSG_PORT_A_KEEP));

    record.sched_wait_returned = (uint8_t)pin_sched_wait8();

    sample_the_two_clocks(&record);

    teardown();
    (void)Super(ssp);

    /* USER MODE again: TOS's screen pointer as well as the shifter (only Setscreen updates
     * `_v_bas_ad`, which TOS's own — now restored — VBL reloads the shifter from). */
    Setscreen((void *)(uintptr_t)saved.tos_logbase, (void *)(uintptr_t)saved.tos_physbase, -1);

    record.magic = STATS_MAGIC;
    record.bytes = sizeof(record);
    record.image_base = (uint32_t)(uintptr_t)game_image;
    record.screen_base_published = wb_target_screen_base;
    record.ikbd_bytes = ikbd_bytes;
    record.ikbd_last_byte = ikbd_last_byte;
    record.readback_failed = readback_failed;
    record.readback_attempted = readback_attempted;
    dump_stats(&record);

#ifdef SMOKE_M2
    m2.magic = M2_MAGIC;
    m2.bytes = sizeof(m2);
    m2.image_base = (uint32_t)(uintptr_t)game_image;
    m2.screen_base_published = wb_target_screen_base;
    m2.poll16_calls = wb_target_poll16_calls;
    m2.shim_vbl_ticks = shim_vbl_ticks;
    m2.anchor_count = M2_ANCHOR_COUNT;
    for (field = 0; field < M2_ANCHOR_COUNT; field++)
        m2.anchor_frames[field] = m2_anchors[field];
    write_file(M2_FILE, &m2, (long)sizeof(m2));
    write_file(FRAME_FILE, captured_frames, (long)sizeof(captured_frames));
    write_file(PENS_FILE, captured_pens, (long)sizeof(captured_pens));
#endif
    return 0;
}
