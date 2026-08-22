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

static int stage_image(void) {
    long handle = Fopen(IMAGE_FILE, FO_READ);
    long got;

    if (handle < 0)
        return 0;
    got = Fread((short)handle, PROGRAM_BYTES, game_image + WB_STAGED_AT);
    (void)Fclose((short)handle);
    return got == PROGRAM_BYTES;
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

static void dump_stats(const struct stats *record) {
    long handle = Fcreate(STATS_FILE, FCREATE_RW);

    if (handle < 0)
        return;
    (void)Fwrite((short)handle, (long)sizeof(*record), record);
    (void)Fclose((short)handle);
}


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
    record->vbl_counter = (uint16_t)((game_image[WB_VBL_COUNTER] << 8)
                                     | game_image[WB_VBL_COUNTER + 1]);
    record->floppy_idle_timer = (uint16_t)((game_image[WB_FLOPPY_IDLE_TIMER] << 8)
                                           | game_image[WB_FLOPPY_IDLE_TIMER + 1]);
    record->tick_drop_value = game_image[WB_SND_TICK_DROP_VALUE];
    record->key_last_scancode = game_image[WB_KEY_LAST_SCANCODE];
    wb_irq_restore(sr);
}

int wonderboy_main(void) {
    struct stats record;
    void *ssp;
    unsigned field;

    for (field = 0; field < sizeof(record); field++)
        ((uint8_t *)&record)[field] = 0;

    game_image = (uint8_t *)(((uintptr_t)image_storage + (IMAGE_ALIGN - 1u))
                             & ~(uintptr_t)(IMAGE_ALIGN - 1u));

    /* USER MODE: the staging read, and TOS's own screen, taken before anything moves. */
    if (!stage_image())
        return 1;
    saved.tos_logbase = (uint32_t)Logbase();
    saved.tos_physbase = (uint32_t)Physbase();

    /* SUPERVISOR: every I/O-space access below would bus-error in user mode. */
    ssp = (void *)Super(0);

    snapshot();
    record.psg_port_a_at_entry = saved.psg_port_a;
    install();
    publish_screen_base();

    checked(RB_VBL_TICKING, run_vblanks(SMOKE_VBLS));
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
    return 0;
}
