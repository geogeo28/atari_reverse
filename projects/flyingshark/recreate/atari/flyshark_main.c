/* flyshark_main.c — the shim: everything FLYSHARK.PRG needs that the verified cores are not.
 *
 * WHAT THIS BUILD IS. The ten verified subsystems under ../src, compiled UNCHANGED by the m68k
 * cross toolchain and wired to a real Atari through the include-path seam (build.sh and
 * shim_include/README-less headers carry that argument, one per file). Nothing here re-implements a
 * core: every routine below either composes cores in the order the original's own `bsr`s make them,
 * or does something the differential harness structurally cannot — a trap, a vector, a device.
 *
 * ================================================================================================
 * THE IMAGE MODEL SURVIVES ONTO THE MACHINE, TRANSLATED BY ONE CONSTANT
 * ================================================================================================
 *
 * The cores index a flat `uint8_t *image` at Ghidra addresses (load base 0x10000). Here that array
 * is `g_image_store` below, and an image address A is the machine address `fs_image_base + A`.
 * Everything that crosses between the two spaces goes through `fs_machine_address`
 * (shim_include/tos.h) — the two `Setscreen` bases, the `Setpalette` table, `Kbdvbase`'s answer —
 * and nothing else in the program has to know.
 *
 * WHY THE BASE IS ROUNDED AT RUN TIME. An STF's video base register has no low byte ($ff8201 and
 * $ff8203 hold bits 23-16 and 15-8), so an unaligned screen address is TRUNCATED and the shifter
 * displays from up to 255 bytes below where the program draws — a byte-identical framebuffer and a
 * wrong picture (docs/on-target-execution.md class 8). GEMDOS loads a .PRG wherever the TPA falls,
 * which is not 256-aligned, so nothing in the linker can promise this: the array reserves
 * IMAGE_ALIGN extra bytes and the base is rounded up here. `Physbase()` is read back afterwards and
 * compared with what was passed, which is the two-instruction assertion that class-8 entry asks for.
 *
 * WHY THE BASE IS NOT ZERO, which is the arrangement that would need no translation at all: it
 * would put the game's world at 0x10000..0x87600 and leave this program the 21,930 bytes below it.
 * README.md's "The load-address budget" has that arithmetic and what replaces the original's
 * `AUTO\`-only 0xd922 ceiling.
 *
 * ================================================================================================
 * WHAT THE SHIM SUPPLIES, AND WHY EACH ONE IS NOT A CORE
 * ================================================================================================
 *
 * README.md's "Shim, not core" table is the inventory. In short: what is left here of the game's own
 * control flow is `main`'s loop of loops, and it is here for one reason — the original LEAVES its
 * inner loops by throwing a return address away and branching (an `adda.l #$40,a7`, an `addq.l #4,a7`
 * and a `bra` back into `main`), which no C function can express. So the verified cores return
 * instead, and the shim WATCHES for what they have already done, one frame late
 * (docs/on-target-execution.md class 7).
 *
 * THE TITLE FLOW IS NO LONGER AMONG THEM. `enter_title`, `title_attract_prescroll`,
 * `title_attract_start_tune`, `title_attract_poll` and `title_frame_step` are cores that answer
 * with the branch they took, and this file composes them exactly as ../src/frontend.c's own
 * `title_attract_loop` does — with the smoke build's frame limit added, which is the only reason
 * that composition is not simply called.
 */
#include <stdint.h>

#include "hw.h"          /* FS_HW_BUS, and the counters the hardware doors keep */
#include "machine.h"
#include "os.h"
#include "psg.h"         /* the chip's two counters */
#include "sched.h"       /* the uncapped polls every core's wait goes through on target */
#include "string.h"      /* memset, for the guard band */
#include "tos.h"

#include "common.h"      /* SCC_TRUE — what a 68000 `Scc` writes */
#include "entity.h"      /* difficulty_apply_fire_rates */
#include "frontend.h"    /* the title flow's five cores, their exit enums, and the asset loader */
#include "globals.h"
#include "hud.h"         /* A_hard_mode, which `start_level`'s dispatch below reads */
#include "init.h"        /* the boot chain, the resets, the frame loop — and FS_TARGET_PHYSBASE */
#include "irq.h"         /* the two handlers and the bytes they write */
#include "player.h"      /* A_level_number, A_game_over_delay */
#include "scroll.h"      /* the stage-start blocks `start_level` composes */
#include "sound.h"       /* music_play, which `start_level`'s tail is */

/* ================================================================================================
 * The build's own knobs, and there are only two.
 *
 * A SMOKE BUILD WRITES TWO FILES AND STOPS; the play build writes nothing and never returns of its
 * own accord. The difference is deliberately that small — everything before the limit is the same
 * code, which is what makes an assertion about the smoke build an assertion about the play build.
 * ============================================================================================= */
#ifndef FS_SMOKE
#define FS_SMOKE 0
#endif
/* Attract-screen frames to run before tearing down and writing the record. 0 = no limit, which is
 * the play build and what a person plays. */
#ifndef FS_ATTRACT_FRAMES
#define FS_ATTRACT_FRAMES 0
#endif

/* ================================================================================================
 * The image array, and the TWO WATCHED BANDS.
 *
 * `FS_TARGET_IMAGE_BYTES` is shim_include/os.h's, which is also what `os_in_image` bounds against,
 * so the array and the check that keeps GEMDOS inside it cannot drift apart.
 *
 * THE BANDS ARE THE SURFACE FOR THE MEMORY MAP BEING WRONG. Every address the map names is one the
 * code NAMES; what no census can cover is an address the code COMPUTES — a tile blit one row past
 * the ring's base, a scroll span one word too generous. Off target such a write lands in the
 * oracle's own megabyte and the differential compares it happily on both sides (`make guarded` is
 * what catches it there, on the cases whose candidate indexes the image with a computed address);
 * here it lands in memory nothing owns. So:
 *
 *   [FS_PROGRAM_END, SCREEN_RING_BASE)   the 20,754 bytes between the program's last byte and the
 *                                        screen ring's first, checked for ZERO rather than filled:
 *                                        zero is what TOS's .bss clear and the harness's calloc
 *                                        both leave, so a pattern would make this build differ from
 *                                        the differential over a region the cores may legally read.
 *   [FS_TARGET_IMAGE_BYTES, +GUARD)      4 KiB OUTSIDE the image, where a write would reach the
 *                                        record and the run would tear down clean with every
 *                                        read-back green. Filled with a PATTERN, because zero is
 *                                        also what a `memset` overrun leaves.
 *
 * A wild store above the guard band is beyond any band, and README.md says so rather than implying
 * this covers it.
 * ============================================================================================= */
#define IMAGE_ALIGN 256u
#define IMAGE_GUARD_BYTES 4096u
#define IMAGE_GUARD_FILL 0xa5u

/* The ring's base, from `boot_init`'s own arithmetic at the Physbase this build chooses: the two
 * constants are the core header's, so a header that moved either moves this with it. */
#define SCREEN_RING_BASE \
    ((FS_TARGET_PHYSBASE - SCREEN_RING_BYTES + SCREEN_RING_ALIGN) & ~(SCREEN_RING_ALIGN - 1u))
#define IMAGE_TAIL_BASE  FS_PROGRAM_END
#define IMAGE_TAIL_BYTES (SCREEN_RING_BASE - IMAGE_TAIL_BASE)

_Static_assert(SCREEN_RING_BASE + SCREEN_RING_BYTES + SCREEN_BYTES == FS_TARGET_IMAGE_BYTES,
               "the image must end exactly at the top of the screen ring surface — test/abi.py's "
               "SCREEN_RING_SPAN");

static uint8_t g_image_store[FS_TARGET_IMAGE_BYTES + IMAGE_ALIGN + IMAGE_GUARD_BYTES];

/* The aligned base. Read by the interrupt entries as well as the main line, and by every `os_*`
 * door in shim_include/os.h, hence a global rather than an argument. */
uint8_t *fs_image_base;

static uint8_t *image_tail(void)  { return fs_image_base + IMAGE_TAIL_BASE; }
static uint8_t *image_guard(void) { return fs_image_base + FS_TARGET_IMAGE_BYTES; }

/* Written from flyshark_os.s (see shim_include/tos.h): the basepage GEMDOS handed `_start`, the
 * stack pointer it was entered with — both latched before the `Super(0)` push moved the stack — and
 * the supervisor stack to hand back. */
uint8_t *fs_basepage;
uint8_t *fs_initial_sp;
void *fs_saved_ssp;

/* GEMDOS basepage fields. The floor of this program's memory is `p_bbase + p_blen` and NOT the top
 * of the image array — a .bss object linked after it sits above it — and the ceiling is the LOWER
 * of `p_hitpa` and the SP we were entered with, because a launcher that pushed an environment
 * breaks the convention that they are equal (docs/on-target-execution.md, "Fitting the machine"). */
#define BASEPAGE_LOW_TPA  0x00u
#define BASEPAGE_HI_TPA   0x04u
#define BASEPAGE_BSS_BASE 0x1cu
#define BASEPAGE_BSS_LEN  0x20u

static uint32_t basepage_field(uint32_t offset) {
    return be32(fs_basepage + offset);
}

/* ================================================================================================
 * The machine's own addresses — the three the image translation cannot reach.
 *
 * Dereferencing an integer constant as a pointer is an out-of-bounds `array[0]` access as far as
 * GCC is concerned, so it warns; the obvious answer, `-Wno-array-bounds` on the command line, would
 * switch the warning off for the VERIFIED CORES too, in the one build where such an access reads
 * live machine memory rather than a bounded array. Two accessors put the suppression exactly where
 * the deliberate absolute address is.
 * ============================================================================================= */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"

static uint32_t read_vector(uint32_t vector) {
    return *(volatile uint32_t *)(uintptr_t)vector;
}

static void write_vector(uint32_t vector, uint32_t handler) {
    *(volatile uint32_t *)(uintptr_t)vector = handler;
}

/* TOS's own 200 Hz counter at $4ba (`_hz_200`), the one stopwatch that runs across this program's
 * boot. Timer C drives it, TOS enables it before this program starts, and nothing this program does
 * touches Timer C — so a mark taken at the boot and another at the teardown say how long the run
 * took in the MACHINE's time rather than the host's. One tick is 5 ms. */
#define TOS_HZ_200_COUNTER 0x4bau

static uint32_t read_hz_200(void) {
    return *(volatile uint32_t *)(uintptr_t)TOS_HZ_200_COUNTER;
}

#pragma GCC diagnostic pop

/* The shifter, in the bus form a C pointer needs. `FS_HW_BUS` is shim_include/hw.h's, which is
 * where the doors are; the addresses are the ST's own and are spelt once here. */
#define HW_PALETTE_BASE     0xff8240u   /* sixteen colour words */
#define HW_SCREEN_BASE_HIGH 0xff8201u   /* the video base's bits 23-16 ... */
#define HW_SCREEN_BASE_MID  0xff8203u   /* ...and 15-8; an STF has no low byte */
#define HW_SHIFTER_MODE     0xff8260u   /* the resolution byte */
#define PALETTE_PENS 16u
#define SHIFTER_PEN_BYTES 2u
#define SHIFTER_PEN_MASK 0x777u         /* three bits a gun; a read returns the fourth as noise */
#define SHIFTER_RESOLUTION_MASK 0x03u   /* $ff8260 bits 0-1; the rest read back as noise too */
#define VIDEO_BASE_HIGH_SHIFT 16
#define VIDEO_BASE_MID_SHIFT   8

static uint32_t read_pen(unsigned pen) {
    return *(volatile uint16_t *)FS_HW_BUS(HW_PALETTE_BASE + pen * SHIFTER_PEN_BYTES)
           & SHIFTER_PEN_MASK;
}

/* What the shifter is really fetching from, assembled from its two bytes. This is the READ-BACK the
 * class-8 check compares against the address that was handed to `Setscreen`: they are equal only if
 * the address was 256-aligned. */
static uint32_t read_raw_video_base(void) {
    return ((uint32_t)*(volatile uint8_t *)FS_HW_BUS(HW_SCREEN_BASE_HIGH) << VIDEO_BASE_HIGH_SHIFT)
           | ((uint32_t)*(volatile uint8_t *)FS_HW_BUS(HW_SCREEN_BASE_MID) << VIDEO_BASE_MID_SHIFT);
}

static uint32_t read_resolution(void) {
    return *(volatile uint8_t *)FS_HW_BUS(HW_SHIFTER_MODE) & SHIFTER_RESOLUTION_MASK;
}

/* ================================================================================================
 * The two interrupt entries' C halves, and the DISPATCH they are built around.
 *
 * flyshark_os.s supplies each entry's `movem` pair and its `rte`; there are two entries and four
 * handlers, because `acia_ikbd_isr` is a two-state machine held IN THE VECTOR: a joystick report
 * arrives as a header byte and then the stick's state, one interrupt each, so the handler re-points
 * $118 at the continuation that reads the second byte and the continuation puts it back
 * (../src/irq.c). The cores make those stores into the IMAGE's vector page — ordinary diffable
 * memory the differential already holds — so the shim's job is to READ IT BACK and call the handler
 * it names. That is what makes the state machine work here with no knowledge of it in this file.
 *
 * AN ADDRESS THE TABLE DOES NOT KNOW IS A HALT, never a silent skip. A skipped interrupt is the
 * worst failure available here: every wait the front end and the frame loop spell reads a byte only
 * these handlers write, so the run would look like a hang with nothing in it. The value is latched,
 * and `g_fatal` stops the program at its next frame boundary so that the record — the only thing
 * that can say what happened — is still written.
 * ============================================================================================= */
static volatile uint32_t g_fatal;
static volatile uint32_t g_fatal_vector;
static volatile uint32_t g_fatal_handler;

/* One binding per handler the program can install, with the count of times it was entered. The
 * counts are the surface: `smoke.py` reads them to say which arms actually ran, and a handler that
 * was installed but never entered is a measurement rather than a belief. */
struct isr_binding {
    uint32_t address;                    /* the Ghidra address the cores store into the image */
    void (*handler)(uint8_t *image);     /* ...and the verified routine in ../src/irq.c */
    volatile uint32_t entries;
};

static struct isr_binding VBL_HANDLERS[] = {
    {FN_VBL_HANDLER, vbl_handler, 0},            /* 0x11636 — the only one; it also chains to TOS */
};

static struct isr_binding ACIA_HANDLERS[] = {
    {FN_ACIA_IKBD_ISR, acia_ikbd_isr, 0},        /* 0x14218 — the header byte and the key ladder */
    {FN_ACIA_JOY0_BYTE, acia_joy0_byte, 0},      /* 0x1430c — joystick 0's second byte */
    {FN_ACIA_JOY1_BYTE, acia_joy1_byte, 0},      /* 0x14330 — joystick 1's, which is the player's */
};

volatile uint32_t fs_vbl_chain;
volatile uint32_t fs_vbl_ticks;
volatile uint32_t fs_acia_ticks;

/* Answer 1 when a handler ran, 0 when the vector named one the table does not know. */
static int dispatch_image_vector(uint32_t image_vector, struct isr_binding *table, unsigned slots) {
    uint32_t handler = be32(fs_image_base + image_vector);

    for (unsigned slot = 0; slot < slots; slot++)
        if (table[slot].address == handler) {
            table[slot].entries++;
            table[slot].handler(fs_image_base);
            return 1;
        }
    g_fatal_vector = image_vector;
    g_fatal_handler = handler;
    g_fatal = 1;
    return 0;
}

#define DISPATCH(vector, table) \
    dispatch_image_vector((vector), (table), sizeof (table) / sizeof (table)[0])

/* The count is bumped BEFORE the handler runs, so a spin that sees N has had N handler entries. */
void fs_vbl_tick(void) {
    fs_vbl_ticks++;
    if (!DISPATCH(VECTOR_VBL, VBL_HANDLERS)) {
        /* THE HALT HAS TO KEEP THE CLOCK RUNNING, or it is not a halt but a hang. `vbl_handler` is
         * what bumps `A_vbl_tick`, and `render_frame`'s pacer spins on that longword UNCAPPED here
         * (shim_include/sched.h) — so a vector this table does not know would leave the main line
         * inside `publish_and_wait` for ever, and the record `g_fatal` exists to get written would
         * never be written. The counter is advanced by hand instead: the frame the main line then
         * finishes is meaningless, and it reaches its next boundary, sees `g_fatal` and stops with
         * the offending vector and handler in the record. */
        wr32(fs_image_base + A_vbl_tick, be32(fs_image_base + A_vbl_tick) + 1u);
    }
    /* `vbl_handler`'s tail, which its own slice stops at: the operand of the `jmp` at 0x1164e, which
     * `boot_init` filled from the $70 vector TOS had. Read afresh every entry rather than latched at
     * the boot, because it is the program's own self-modified longword and reading it here is what
     * makes that true on the machine as well as in the image. flyshark_os.s does the jump. */
    fs_vbl_chain = be32(fs_image_base + A_vbl_chain_vector);
}

void fs_acia_tick(void) {
    fs_acia_ticks++;
    DISPATCH(VECTOR_ACIA, ACIA_HANDLERS);
}

/* ================================================================================================
 * The record. STATE.BIN, one big-endian longword per field, in this order.
 *
 * PINNED ACROSS THE LANGUAGE BOUNDARY BY ITS OWN LENGTH: field 1 is the field count, and smoke.py
 * refuses a record whose count does not equal the length of its name list. So a field added here
 * and not there fails at the parse with the two numbers printed, rather than silently shifting
 * every value after it by one and reporting a wrong pen (CLAUDE.md §5).
 * ============================================================================================= */
#define FS_RECORD_MAGIC 0x46534b31u   /* 'FSK1' */
#define FS_RECORD_TAIL  0x444f4e45u   /* 'DONE' — written last, so a truncated dump is detectable */

enum {
    REC_MAGIC, REC_FIELDS,
    /* The image, and the memory budget MEASURED off the basepage rather than assumed. */
    REC_IMAGE_BASE, REC_IMAGE_BYTES, REC_PROGRAM_STAGED_BYTES,
    REC_TPA_LOW, REC_TPA_HIGH, REC_PROGRAM_TOP, REC_HEADROOM,
    REC_IMAGE_TAIL_DIRTY, REC_IMAGE_GUARD_CHANGED,
    /* The screen: what was asked for, what the chip took, and what the cores derived from it. */
    REC_PHYSBASE_WANTED, REC_PHYSBASE_AT_BOOT, REC_RAW_VIDEO_BASE_AT_BOOT,
    REC_SCREEN_RING_BASE, REC_SCREEN_RING_0, REC_SCREEN_RING_1, REC_SCREEN_RING_2, REC_SCREEN_RING_3,
    /* The boot's own answers. */
    REC_SUPER_TOKEN, REC_TOS_JOYVEC_SAVED, REC_VBL_CHAIN,
    REC_TICKS_AT_BOOT, REC_TICKS_AT_END,
    /* What ran. */
    REC_VBL_TICKS, REC_ACIA_TICKS, REC_VBL_ENTRIES, REC_ACIA_ENTRIES, REC_ACIA_JOY0_ENTRIES,
    REC_ACIA_JOY1_ENTRIES, REC_ATTRACT_FRAMES, REC_ATTRACT_FRAME_LIMIT,
    REC_FATAL, REC_FATAL_VECTOR, REC_FATAL_HANDLER,
    /* The status register the run ends on. The original establishes its own (`move.w #$2300,sr`
     * @ 0x14cce — supervisor, IPL 3); this build keeps whatever GEMDOS entered it with, because the
     * mask pair around the vector installs is all the model had to say about interrupts. The number
     * is carried so that "which IPL was this measured at" is answerable rather than assumed. */
    REC_SR_AT_END,
    /* The seams' counters — the only surface a target run has for a store or a trap. */
    REC_FILE_OPENS, REC_FILE_OPEN_FAILURES, REC_FILE_BYTES_READ, REC_FILE_REFUSALS,
    REC_SETSCREEN_CALLS, REC_SETPALETTE_CALLS, REC_VSYNC_CALLS, REC_IKBD_COMMANDS,
    REC_HW_WRITES, REC_HW_RMW, REC_HW_READS, REC_PSG_WRITES, REC_PSG_REFUSED,
    /* THE HARDWARE-STATE VECTOR AT THE END OF THE RUN, and the game state that dates it. Not the
     * same instant as `smoke.py`'s framebuffer anchor (attract frame 120, taken by the emulator's
     * own breakpoint): this is wherever the frame limit stopped the shim, which is why the names
     * say `_AT_END`. What it is worth is the PER-FRAME PUBLISH — the game moves the physical screen
     * base every frame and the harness's `Setscreen` event drops that argument entirely, so a
     * shifter base read back here and compared with `image base + screen_draw` is the only check
     * there is that the publish reaches the chip, at the one address that MOVES. */
    REC_PHYSBASE_AT_END, REC_RAW_VIDEO_BASE_AT_END, REC_REZ_AT_END,
    REC_SCREEN_DRAW_AT_END, REC_SCREEN_PREV1_AT_END, REC_SCROLL_POS_AT_END,
    REC_LEVEL0_ASSETS_LOADED,
    REC_PENS_AT_END, REC_PENS_AT_END_LAST = REC_PENS_AT_END + PALETTE_PENS - 1,
    /* ...and after the hand-back, which is the surface for a teardown that only looks clean. */
    REC_VBL_VECTOR_AFTER, REC_ACIA_VECTOR_AFTER, REC_JOYVEC_AFTER,
    REC_PHYSBASE_AFTER, REC_REZ_AFTER, REC_TICKS_AT_TEARDOWN,
    /* ...and what two of those are compared against: what TOS had before this program took the
     * machine. `$70`'s before-value is the chain the boot itself saved (`REC_VBL_CHAIN`), but $118
     * is taken OUTRIGHT with nothing saving it, so the shim's own reading is the only one there is
     * — and a $118 left pointing into a freed TPA is the class-7 halt a second after `Pterm`. */
    REC_ACIA_VECTOR_BEFORE, REC_REZ_BEFORE,
    REC_TAIL,
    REC_FIELD_COUNT
};

/* NOT `static`, AND THAT IS LOAD-BEARING RATHER THAN STYLE. In a PLAY build nothing reads this
 * array — `write_file` is compiled out with the rest of the smoke — so a file-static one is a set of
 * dead stores and GCC removes it entirely, taking the only thing that says WHERE THE IMAGE IS with
 * it (measured: `smoke.py --floppy-only` on a play build found the magic at zero addresses in a
 * megabyte of RAM). External linkage stops that, because the compiler cannot prove no other
 * translation unit reads it. `build.sh` asserts the symbol survives into the .PRG's ELF, so the
 * class reddens at the build rather than as a check that cannot find the program. */
uint32_t g_record[REC_FIELD_COUNT];

/* ================================================================================================
 * The files this build moves. Uppercase 8.3 so a GEMDOS drive cannot rename them.
 * ============================================================================================= */
#define FILE_PROGRAM_IMAGE "FLYSHARK.IMG"   /* the original's relocated text+data, staged by build.sh */
#define FILE_STATE_RECORD  "STATE.BIN"      /* the record, written at the teardown */
/* ...and a BEACON, written as early as a file can be: the first thing a smoke build does after it
 * knows where its image is.
 *
 * IT IS A WAKE-UP AND NOT A LOCATE. Where the image array is comes out of `g_record`'s first fields
 * in a RAM dump, which works on every medium and in every build; what a RAM dump cannot do is tell a
 * driver WHEN to look. The title picture is on screen from the boot's copy until the attract
 * screen's first published frame, and on a GEMDOS drive the eight file loads between those two
 * moments take a fraction of a second — so a driver polling for the program at any interval it can
 * afford will usually arm its capture too late, and a breakpoint on a state that is already true
 * fires immediately, on the wrong picture. A file appears on the host the instant GEMDOS writes it,
 * which is what makes this the one signal fast enough.
 *
 * A FLOPPY RUN CANNOT USE IT (Hatari 2.6.1 writes no modified `.ST` back to the host) and a PLAY
 * build does not write it at all; both are located by the RAM dump instead, and neither needs the
 * title's moment. `smoke.py` says which it used. */
#define FILE_BEACON        "STARTED.BIN"

#if FS_SMOKE
static long write_file(const char *name, const void *data, long bytes) {
    long handle = Fcreate(name, 0);
    long written;

    if (handle < 0)
        return handle;
    written = Fwrite((short)handle, bytes, data);
    Fclose((short)handle);
    return written;
}
#endif

/* The original's TEXT+DATA, read into the image at its own load base. Its BSS is not in the file
 * and is not read: TOS has already zeroed `g_image_store`, which is exactly what the harness's
 * `loader.load_image` leaves there, and the eight data files the boot loads fill it.
 *
 * WHY A FILE AND NOT A `.data` BLOB in this program: the same bytes either way, and this keeps the
 * .PRG small enough to read at a glance — the same choice Joust's JOUST.IMG and Zynaps' ZYNAPS.IMG
 * make. It is the ONE file on the disc that the original does not have. */
_Static_assert(FS_LOAD_BASE + FS_TEXT_BYTES + FS_DATA_BYTES <= FS_TARGET_IMAGE_BYTES,
               "the staged program would not fit the image array — this read is the one that does "
               "not go through os_fread's bound, because it is the shim's own file and its length "
               "is a compile-time constant, so the bound is asserted here instead");

static long stage_program_image(void) {
    long handle = Fopen(FILE_PROGRAM_IMAGE, FS_FOPEN_READ_WRITE);
    long got;

    if (handle < 0)
        return handle;
    got = Fread((short)handle, (long)(FS_TEXT_BYTES + FS_DATA_BYTES), fs_image_base + FS_LOAD_BASE);
    Fclose((short)handle);
    return got;
}

/* How many bytes of a band are not what they should be. */
static uint32_t bytes_not(const uint8_t *from, uint32_t count, uint8_t expected) {
    uint32_t wrong = 0;

    while (count--)
        if (*from++ != expected)
            wrong++;
    return wrong;
}

/* ================================================================================================
 * THE SHIM'S HALF OF THE PROGRAM — the routines ../STATUS.md files under "Not reconstructed".
 *
 * Each one is the original's own control flow with a verified core at every `bsr`. The addresses in
 * the comments are `../out/prg_dis.txt`'s, so a reader can put the two side by side.
 * ============================================================================================= */

/* The three levels beyond which `start_level` forces hard mode (0x114fa and 0x11510), and the tune
 * its tail plays (`clr.w d0 / bra.w music_play` @ 0x11568). Spelt here rather than in a core header
 * so that no core acquires a constant it has no use for — the routine they belong to has no core. */
#define LEVEL_FORCES_HARD_MODE 3u
#define LEVEL_TUNE 0u

/* start_level @ 0x11440 — its two verified slices, the per-level asset dispatch between them, and
 * the stage start it shares with the title screen.
 *
 * THE DISPATCH AT 0x11494 IS FIVE ARMS ON `A_level_number` and is the only part with no core: each
 * arm decides whether level 0's assets are already in memory (the flag `init_load_assets` set) and
 * loads the level's own, and the last two also force hard mode. */
static void start_level(uint8_t *image) {
    uint16_t level = be16(image + A_level_number);

    start_level_reset_actors(image);        /* [0x11440, 0x1145a) */
    clear_actor_arrays(image);              /* 0x1145a */
    start_level_install_record(image);      /* [0x1145e, 0x11494) — clear_object_list and the record */

    if (level == 0) {                       /* 0x114be */
        if (be16(image + A_level0_assets_loaded) == 0) {
            image[A_level0_assets_loaded] = SCC_TRUE;    /* `st`, one byte */
            load_level_assets(image, 0);
        }
    } else {
        wr16(image + A_level0_assets_loaded, 0);         /* `clr.w` on every other arm */
        if (level >= LEVEL_FORCES_HARD_MODE)             /* 0x114fa and 0x11510 */
            image[A_hard_mode] = SCC_TRUE;
        load_level_assets(image, level);
    }

    seed_map_row_cursor(image);             /* 0x1151e */
    set_palette_black(image);               /* 0x11540 */
    prescroll_stage(image);                 /* 0x11544 */
    set_palette_game(image);                /* 0x11564 */
    music_play(image, LEVEL_TUNE);          /* 0x11568: `clr.w d0 / bra.w music_play` */
}

/* ---- the attract screen -----------------------------------------------------------------------
 *
 * FIVE VERIFIED CORES, AND THE ONE THING THIS BUILD ADDS TO THEM. `enter_title`,
 * `title_attract_prescroll`, `title_attract_start_tune`, `title_attract_poll` and
 * `title_frame_step` are ../src/frontend.c's, and each answers with the branch the original took
 * (../include/frontend.h names every exit). `title_attract_loop` there composes them into the whole
 * attract screen — but its ONLY way out is the fire button, and this build needs two more: a smoke
 * run stops at a frame count, and a fatal interrupt has to get out of the tune arm, which spins
 * without drawing anything. So the composition is restated below — the same five calls in the same
 * order — with the frame counter and the stop test between them. That is `run_the_frame_loop`'s
 * arrangement one flow up: the cores decide, the shim watches (docs/on-target-execution.md class 7).
 *
 * NOTHING HERE READS THE GAME'S OWN STATE ANY MORE. The page timer, the two text pages, the mode
 * word and the "just entered" flag are all inside `title_attract_poll`, and the stick byte its spin
 * polls is the one `acia_ikbd_isr` writes — through shim_include/sched.h's uncapped `sched_poll8`,
 * which is the whole of what this build changes about a core's wait. */

/* How many attract frames have been drawn, and the limit a smoke build stops at. */
static uint32_t g_attract_frames;

/* Set when the run is to end: the smoke build's frame limit, or a fatal interrupt. Read at every
 * loop boundary the shim owns. */
static int run_should_stop(void) {
    if (g_fatal)
        return 1;
#if FS_ATTRACT_FRAMES
    return g_attract_frames >= (uint32_t)FS_ATTRACT_FRAMES;
#else
    return 0;
#endif
}

/* What ended a pass of the attract screen. Three of these are the original's own branches, relayed
 * from the two exit enums the cores answer with; the fourth is this build's alone. */
enum attract_exit {
    ATTRACT_START_GAME,      /* 0x105a6 `rts` — fire, with no high score waiting to be entered */
    ATTRACT_TUNE_ENDED,      /* 0x1057e `beq.s $1054a` — the module says the tune has finished */
    ATTRACT_RESTART_SCROLL,  /* 0x105a2 `bra.w $104f2` — the scroll has run out of map */
    ATTRACT_STOPPED          /* not the original's: this build's own frame limit, or a fatal ISR */
};
/* THE ORIGINAL'S FOURTH EXIT IS NOT IN THAT LIST, and that is the point: `bra.w $106f2` @ 0x10590
 * goes to `hiscore_show_entry_screen`, which falls into `hiscore_name_entry`, whose every arm
 * branches to 0x10594 — the frame step the loop was about to run anyway. So it leaves and comes
 * straight back, once per frame, and `title_attract_poll` spells it as the call it is rather than
 * as a return value. An earlier draft of THIS file returned it here and re-entered the attract loop
 * at its head: `hiscore_name_entry` was then never called, nothing ever cleared
 * `new_hiscore_pending`, and a player who beat a score got an endless prescroll with no frame drawn
 * and no way out. */

/* The spin at 0x10562, one attract frame a pass: poll, and draw the frame the poll built.
 *
 * THE FRAME IS COUNTED ON EVERY PASS THAT DRAWS ONE, the pass whose scroll test ends the attract
 * cycle included — that frame reached the screen like any other. The stop is tested only on the
 * pass that goes round again, because the three that do not are answered to the caller, which
 * tests it there. */
static enum attract_exit run_the_attract_spin(uint8_t *image) {
    for (;;) {
        title_poll_exit poll = title_attract_poll(image);   /* [0x10562, 0x10594) — verified */
        title_frame_exit frame;

        if (poll == TITLE_POLL_START_GAME)
            return ATTRACT_START_GAME;
        if (poll == TITLE_POLL_TUNE_ENDED)
            return ATTRACT_TUNE_ENDED;

        frame = title_frame_step(image);                    /* [0x10594, 0x10562) — verified */
        g_attract_frames++;
        if (frame == TITLE_FRAME_ATTRACT_OVER)
            return ATTRACT_RESTART_SCROLL;
        if (run_should_stop())
            return ATTRACT_STOPPED;
    }
}

/* title_attract_loop @ 0x104f2 — the stage start, the tune, and the two exits that come back to it.
 *
 * The prescroll blacks the palette itself (../src/frontend.c opens the slice on `set_palette_black`
 * @ 0x104f2), so the head of the loop is that one call and not two. */
static enum attract_exit run_the_attract_loop(uint8_t *image) {
    title_attract_prescroll(image);                  /* [0x104f2, 0x1054a) — verified */
    for (;;) {
        enum attract_exit why;

        title_attract_start_tune(image);             /* [0x1054a, 0x10562) — verified */
        why = run_the_attract_spin(image);

        if (why == ATTRACT_RESTART_SCROLL) {
            title_attract_prescroll(image);          /* `bra.w $104f2` @ 0x105a2 */
            continue;
        }
        if (why == ATTRACT_TUNE_ENDED) {
            /* Back to 0x1054a to start the tune again — the original's own loop, and it draws no
             * frame on the way round. So the stop is tested HERE as well as after a drawn frame: a
             * module whose "still playing" byte never comes on (a short or unreadable
             * `A\MODULE.BAK`, which `load_file` reports to nobody, faithfully) spins in this arm in
             * the original too, and this is what lets a fatal interrupt out of it. */
            if (run_should_stop())
                return ATTRACT_STOPPED;
            continue;
        }
        return why;
    }
}

/* enter_title @ 0x1030e — the verified four instructions, and the load its `bne.w` skips.
 *
 * The core answers which branch it took rather than making the call, because `load_level_assets` is
 * the frontend's own routine and `enter_title`'s slice stops at that `bsr` (../include/frontend.h). */
static enum attract_exit run_the_title(uint8_t *image) {
    if (enter_title(image) == ENTER_TITLE_LOAD_LEVEL0)   /* [0x1030e, 0x1032a) — verified */
        load_level_assets(image, 0);                     /* `clr.w d0 / bsr.w $10332` @ 0x1032a */
    return run_the_attract_loop(image);
}

/* ---- the frame loop, and the three exits its cores cannot express -----------------------------
 *
 * `frame_loop_once` is the whole of `main`'s 45-call body and is verified. What it cannot carry is
 * the three ways the original LEAVES that body: two of its callees throw their caller's return
 * address away and branch (`adda.l #$40,a7` in `read_player_input`, `addq.l #4,a7` at 0x13c62), and
 * the third re-enters the loop's own top. A C function cannot express any of them
 * (../src/init.c says so at the function), so the reconstruction returns instead and the SHIM
 * watches for what the verified code has already done — the class-7 pattern
 * (docs/on-target-execution.md): watch, do not intercept, and pay one frame of lateness.
 *
 * EACH WATCH IS A STATE THE VERIFIED CORE ITSELF WROTE, and each costs the rest of one frame that
 * the original's unwind skips:
 *
 *   the level advance   `level_advance` (../src/player.c) has bumped `A_level_number`
 *   the game over       the banner's dwell has run out, which is when `player_game_over_display`
 *                       calls `game_over_hiscore_check` — the routine that in the original never
 *                       returns
 *   the abort key       F10's bit in `A_key_bits`, which `read_player_input` has just acted on
 */
#define FS_ABORT_KEY_MASK (1u << 2)   /* ../src/player.c's KEY_ABORT_BIT (F10), which is private to
                                       * that core; spelt here as a MASK because the shim needs the
                                       * same bit to notice an exit the core cannot express.
                                       * ../STATUS.md proposes it move to include/irq.h, which owns
                                       * `A_key_bits`. */

enum frame_exit { FRAME_EXIT_LEVEL, FRAME_EXIT_GAME_OVER, FRAME_EXIT_STOPPED };

static enum frame_exit run_the_frame_loop(uint8_t *image) {
    uint16_t level = be16(image + A_level_number);

    for (;;) {
        frame_loop_once(image);                              /* [0x1575c, 0x15816) — verified */
        if (be16(image + A_level_number) != level)
            return FRAME_EXIT_LEVEL;                         /* 0x1251c `addq.l #4,a7 / bra $15758`,
                                                              * inside `level_advance` @ 0x12504 */
        if ((int16_t)be16(image + A_game_over_delay) < 0)
            return FRAME_EXIT_GAME_OVER;                     /* game_over_hiscore_check ran */
        if ((image[A_key_bits] & FS_ABORT_KEY_MASK) != 0)
            return FRAME_EXIT_GAME_OVER;                     /* 0x1439e, the abort key */
        if (run_should_stop())
            return FRAME_EXIT_STOPPED;
    }
}

/* main @ 0x15750 — the three-call boot slice and the loop of loops behind it.
 *
 * The original's three "calls" are a chain: `init_new_game` ends `bra.w enter_title` and
 * `init_stage_state` tail-calls `start_level`, so the front end runs off `main`'s stack frame and
 * the two re-entry labels the game uses (0x15754 "restart the game" and 0x1575c "the frame loop's
 * top") are branch targets rather than returns. Here they are the two loops.
 *
 * THE DIFFICULTY DISPATCH IS ONE HALF-REPRODUCED ARM, and it is this build's one deliberate
 * gameplay divergence. `init_stage_state` ends `tst.b hard_mode / beq.w $12cb6 / bra.w $12cc8` —
 * two entries into `difficulty_apply_fire_rates` that differ in FOUR register immediates, and the
 * reconstruction verifies the HARD one (0x12cc8). So an easy game gets the hard arm's fire rates.
 * README.md's "Deliberate divergences" and ../STATUS.md's "Unpinned on target" both carry it, and
 * nothing pins it: the smoke never starts a game, so no check in this tree has ever seen either
 * arm's constants reach the enemy table. The STATUS row says so rather than this comment claiming
 * a measurement that does not exist. */
static void run_the_whole_program(uint8_t *image) {
    init_load_assets(image);                             /* 0x15750 */

    for (;;) {                                           /* 0x15754 — a new game */
        init_new_game(image);                            /* 0x15754, ends `bra.w enter_title` */
        if (run_the_title(image) != ATTRACT_START_GAME)
            return;                                      /* the frame limit, or a fatal interrupt */

        for (;;) {                                       /* 0x15758 — a new stage */
            init_stage_state(image);                     /* [0x1139a, 0x11438) */
            difficulty_apply_fire_rates(image);          /* 0x12cc8 — see the note above */
            start_level(image);
            if (run_the_frame_loop(image) != FRAME_EXIT_LEVEL)
                break;
        }
        if (run_should_stop())
            return;
    }
}

/* ================================================================================================
 * The boot, the hand-back, and the record around them.
 * ============================================================================================= */

/* What TOS had before this program took the machine, so that every one of it can be given back.
 * Anything installed into TOS outlives the process, and an IKBD handler still chaining into a freed
 * TPA halts the machine about a second after `Pterm` (docs/on-target-execution.md class 7). */
struct tos_state {
    uint32_t vbl_vector;
    uint32_t acia_vector;
    uint32_t joyvec;
    void *physbase;
    void *logbase;
    short rez;
};

static void take_the_machine(struct tos_state *tos) {
    tos->vbl_vector = read_vector(VECTOR_VBL);
    tos->acia_vector = read_vector(VECTOR_ACIA);
    tos->joyvec = be32((uint8_t *)Kbdvbase() + KBDVBASE_JOYVEC);
    tos->physbase = (void *)Physbase();
    tos->logbase = (void *)Logbase();
    tos->rez = Getrez();
}

/* The two IKBD commands that put the 6301 back the way TOS had it, and they are the shim's own —
 * the original never terminates, so it never needs them. `boot_init` sends `$14` (report joystick
 * events), which is what makes the 6301 send `$FE`/`$FF` packets AND stops it sending mouse
 * packets; a program that returned to the desktop without undoing it would leave the GEM pointer
 * dead until the machine was reset. That is the mirror of docs/on-target-execution.md class 12: a
 * device left in the wrong mode, routing input somewhere nobody is looking.
 *
 * THEY HAVE NO SURFACE HERE and ../STATUS.md says so: what would show it is a mouse pointer, which
 * a headless run has no way to move. */
#define IKBD_CMD_DISABLE_JOYSTICKS 0x1au
#define IKBD_CMD_RELATIVE_MOUSE    0x08u

static void hand_the_machine_back(const struct tos_state *tos) {
    uint16_t sr = fs_irq_disable();

    write_vector(VECTOR_VBL, tos->vbl_vector);
    write_vector(VECTOR_ACIA, tos->acia_vector);
    /* TOS's own joystick callback, which `boot_init` replaced with an IMAGE address (0x141fa) that
     * means nothing to TOS's parser. It is unreachable while this program owns the ACIA vector and
     * would be reached the moment the line above gives that vector back — a vector into a freed TPA
     * halts the machine about a second after `Pterm` (docs/on-target-execution.md class 7).
     *
     * RESTORED FROM THIS SHIM'S OWN READING, taken before any core ran, and NOT from the copy the
     * core saved at `A_saved_tos_joyvec`. That leaves the two independent, which is what makes the
     * record's comparison of them worth making: they are equal only if the core's
     * `image + fs_kbdvbase() + 0x18` really landed on TOS's struct, which is the whole of that
     * seam (shim_include/init.h). Restoring from the core's copy would have compared it with
     * itself. */
    wr32((uint8_t *)Kbdvbase() + KBDVBASE_JOYVEC, tos->joyvec);
    fs_irq_restore(sr);

    /* The keyboard controller, before the screen: TOS owns the ACIA vector again by now, so its own
     * handler is what receives the replies. */
    Bconout(FS_BCONOUT_IKBD, IKBD_CMD_DISABLE_JOYSTICKS);
    Bconout(FS_BCONOUT_IKBD, IKBD_CMD_RELATIVE_MOUSE);

    /* The screen last, and through `Setscreen` rather than the shifter's own bytes: only the trap
     * updates `_v_bas_ad` and `sshiftmd` as well, which is what the desktop draws through. */
    Setscreen(tos->logbase, tos->physbase, tos->rez);
    Vsync();
}

void flyshark_main(void) {
    struct tos_state tos;
    uint32_t staged;
    uint32_t program_top;
    void *wanted_physbase;
    unsigned pen;

    /* The aligned base, and the guard band, before anything else can write through either. The
     * offset is the distance to the next 256-byte boundary — zero when the array is already on one
     * — and it is spelt as an offset FROM THE ARRAY rather than as an integer cast back to a
     * pointer, so the pointer never leaves the object it came from. */
    fs_image_base = g_image_store
                    + ((IMAGE_ALIGN - ((uintptr_t)g_image_store & (IMAGE_ALIGN - 1u)))
                       & (IMAGE_ALIGN - 1u));
    memset(image_guard(), IMAGE_GUARD_FILL, IMAGE_GUARD_BYTES);

    g_record[REC_MAGIC] = FS_RECORD_MAGIC;
    g_record[REC_FIELDS] = REC_FIELD_COUNT;
    g_record[REC_IMAGE_BASE] = (uint32_t)(uintptr_t)fs_image_base;
    g_record[REC_IMAGE_BYTES] = FS_TARGET_IMAGE_BYTES;
    /* Those four fields are filled BEFORE anything else in this function, and no build makes that
     * conditional: they are how a driver finds the image array in RAM, and a play build has to be
     * findable too (`smoke.py --floppy-only` is what judges the build a person gets). */
#if FS_SMOKE
    write_file(FILE_BEACON, &g_record[REC_IMAGE_BASE], (long)sizeof g_record[0]);
#endif

    /* The budget, measured off the basepage GEMDOS filled rather than off a spec sheet. */
    program_top = basepage_field(BASEPAGE_BSS_BASE) + basepage_field(BASEPAGE_BSS_LEN);
    g_record[REC_TPA_LOW] = basepage_field(BASEPAGE_LOW_TPA);
    g_record[REC_TPA_HIGH] = basepage_field(BASEPAGE_HI_TPA);
    g_record[REC_PROGRAM_TOP] = program_top;
    {
        uint32_t ceiling = (uint32_t)(uintptr_t)fs_initial_sp;

        if (g_record[REC_TPA_HIGH] < ceiling)
            ceiling = g_record[REC_TPA_HIGH];
        g_record[REC_HEADROOM] = ceiling > program_top ? ceiling - program_top : 0;
    }

    take_the_machine(&tos);
    g_record[REC_ACIA_VECTOR_BEFORE] = tos.acia_vector;
    g_record[REC_REZ_BEFORE] = (uint32_t)tos.rez;
    g_record[REC_TICKS_AT_BOOT] = read_hz_200();

    /* THE SCREEN, BEFORE ANY CORE RUNS. The original's `boot_init` opens with
     * `Setscreen(0x70000, 0x78000, 0)` and then derives its whole world from `Physbase` — two
     * absolute addresses that are only right for a program that IS the machine. Here the screen is
     * inside this program's own array, at the image address `shim_include/init.h` answers
     * `fs_physbase()` with, and the logical base keeps the original's own relationship to it
     * (`BOOT_SETSCREEN_PHYS - BOOT_SETSCREEN_LOG`). The resolution argument is what the call is
     * FOR: it forces low resolution before anything is drawn.
     *
     * THEN READ IT BACK, which is the whole of the class-8 assertion: `Physbase()` answers what the
     * shifter really took, and an address the register truncated comes back different. */
    wanted_physbase = fs_machine_address(FS_TARGET_PHYSBASE);
    Setscreen(fs_machine_address(FS_TARGET_PHYSBASE - (BOOT_SETSCREEN_PHYS - BOOT_SETSCREEN_LOG)),
              wanted_physbase, BOOT_RESOLUTION_LOW);
    Vsync();
    g_record[REC_PHYSBASE_WANTED] = (uint32_t)(uintptr_t)wanted_physbase;
    g_record[REC_PHYSBASE_AT_BOOT] = (uint32_t)Physbase();
    g_record[REC_RAW_VIDEO_BASE_AT_BOOT] = read_raw_video_base();

    staged = (uint32_t)stage_program_image();
    g_record[REC_PROGRAM_STAGED_BYTES] = staged;

    /* THE VECTOR PAGE THE CORES SEE. `boot_init` reads `image + $70` to fill its own `jmp` operand,
     * so the image has to hold what the MACHINE holds there before the core runs — otherwise the
     * chain the vertical-blank handler jumps through would be the zero TOS never wrote. */
    wr32(fs_image_base + VECTOR_VBL, tos.vbl_vector);
    wr32(fs_image_base + VECTOR_ACIA, tos.acia_vector);

    boot_init(fs_image_base);            /* 0x14bee — the whole slice, including the real IKBD $14 */
    g_record[REC_SUPER_TOKEN] = be32(fs_image_base + A_saved_super_ssp);
    g_record[REC_TOS_JOYVEC_SAVED] = be32(fs_image_base + A_saved_tos_joyvec);
    g_record[REC_VBL_CHAIN] = be32(fs_image_base + A_vbl_chain_vector);
    g_record[REC_SCREEN_RING_BASE] = be32(fs_image_base + A_screen_ring_base);
    g_record[REC_SCREEN_RING_0] = be32(fs_image_base + A_screen_ring);
    g_record[REC_SCREEN_RING_1] = be32(fs_image_base + A_screen_ring_1);
    g_record[REC_SCREEN_RING_2] = be32(fs_image_base + A_screen_ring_2);
    g_record[REC_SCREEN_RING_3] = be32(fs_image_base + A_screen_ring_3);

    /* THE REAL VECTORS GO IN WHERE THE PROGRAM'S OWN DO — immediately after the slice that stored
     * the image's, and as a pair under the mask the original brackets its two stores with. The
     * window in which TOS still owns the keyboard is therefore the original's window plus this
     * slice's own length, and no longer: the $14 command `boot_init` sent has already gone out, so
     * the first joystick packet may arrive during it and be taken by TOS's handler. README.md's
     * "What is unpinned" carries that window. */
    {
        uint16_t sr = fs_irq_disable();

        write_vector(VECTOR_VBL, (uint32_t)(uintptr_t)&fs_vbl_entry);
        write_vector(VECTOR_ACIA, (uint32_t)(uintptr_t)&fs_acia_entry);
        fs_irq_restore(sr);
    }

    run_the_whole_program(fs_image_base);

    /* ---- the anchor: the machine as it stands with the program still owning it ---------------- */
    g_record[REC_TICKS_AT_END] = read_hz_200();
    g_record[REC_PHYSBASE_AT_END] = (uint32_t)Physbase();
    g_record[REC_RAW_VIDEO_BASE_AT_END] = read_raw_video_base();
    g_record[REC_REZ_AT_END] = read_resolution();
    g_record[REC_SCREEN_DRAW_AT_END] = be32(fs_image_base + A_screen_draw);
    /* ...and the buffer published one frame BEFORE it, which is the one the shifter is fetching:
     * `render_frame` publishes `screen_draw` in its phase 5 and its phase 6 then rotates the ring,
     * so at any point between two frames `screen_prev1` holds the base that was handed to the chip
     * (../src/sprite.c, `advance_scroll`: prev2 = prev1; prev1 = draw; draw = *slot). */
    g_record[REC_SCREEN_PREV1_AT_END] = be32(fs_image_base + A_screen_prev1);
    g_record[REC_SCROLL_POS_AT_END] = be16(fs_image_base + A_scroll_pos);
    g_record[REC_LEVEL0_ASSETS_LOADED] = fs_image_base[A_level0_assets_loaded];
    for (pen = 0; pen < PALETTE_PENS; pen++)
        g_record[REC_PENS_AT_END + pen] = read_pen(pen);

    g_record[REC_VBL_TICKS] = fs_vbl_ticks;
    g_record[REC_ACIA_TICKS] = fs_acia_ticks;
    g_record[REC_VBL_ENTRIES] = VBL_HANDLERS[0].entries;
    g_record[REC_ACIA_ENTRIES] = ACIA_HANDLERS[0].entries;
    g_record[REC_ACIA_JOY0_ENTRIES] = ACIA_HANDLERS[1].entries;
    g_record[REC_ACIA_JOY1_ENTRIES] = ACIA_HANDLERS[2].entries;
    g_record[REC_ATTRACT_FRAMES] = g_attract_frames;
    g_record[REC_ATTRACT_FRAME_LIMIT] = FS_ATTRACT_FRAMES;
    {
        /* The SR, sampled with the one routine that answers it: `fs_irq_disable` returns the
         * register as it stood and masks, and `fs_irq_restore` puts it back. */
        uint16_t sr = fs_irq_disable();

        g_record[REC_SR_AT_END] = sr;
        fs_irq_restore(sr);
    }
    g_record[REC_FATAL] = g_fatal;
    g_record[REC_FATAL_VECTOR] = g_fatal_vector;
    g_record[REC_FATAL_HANDLER] = g_fatal_handler;

    g_record[REC_FILE_OPENS] = fs_file_opens;
    g_record[REC_FILE_OPEN_FAILURES] = fs_file_open_failures;
    g_record[REC_FILE_BYTES_READ] = fs_file_bytes_read;
    g_record[REC_FILE_REFUSALS] = fs_file_refusals;
    g_record[REC_SETSCREEN_CALLS] = fs_setscreen_calls;
    g_record[REC_SETPALETTE_CALLS] = fs_setpalette_calls;
    g_record[REC_VSYNC_CALLS] = fs_vsync_calls;
    g_record[REC_IKBD_COMMANDS] = fs_ikbd_commands;
    /* The interrupt ticks these three through `sound_vbl_tick`, so they are latched with the
     * vertical blank masked: a blank landing between two of them would put one operand from before
     * the driver's per-frame flush beside another from after it, which is an intermittent red
     * caused by interrupt timing rather than by a change. */
    {
        uint16_t sr = fs_irq_disable();

        g_record[REC_HW_WRITES] = fs_hw_writes;
        g_record[REC_HW_RMW] = fs_hw_rmw;
        g_record[REC_HW_READS] = fs_hw_reads;
        g_record[REC_PSG_WRITES] = fs_psg_writes;
        g_record[REC_PSG_REFUSED] = fs_psg_refused;
        fs_irq_restore(sr);
    }

    hand_the_machine_back(&tos);

    g_record[REC_VBL_VECTOR_AFTER] = read_vector(VECTOR_VBL);
    g_record[REC_ACIA_VECTOR_AFTER] = read_vector(VECTOR_ACIA);
    g_record[REC_JOYVEC_AFTER] = be32((uint8_t *)Kbdvbase() + KBDVBASE_JOYVEC);
    g_record[REC_PHYSBASE_AFTER] = (uint32_t)Physbase();
    g_record[REC_REZ_AFTER] = read_resolution();
    g_record[REC_TICKS_AT_TEARDOWN] = read_hz_200();

    /* LAST, so they cover everything the run did. */
    g_record[REC_IMAGE_TAIL_DIRTY] = bytes_not(image_tail(), IMAGE_TAIL_BYTES, 0);
    g_record[REC_IMAGE_GUARD_CHANGED] = bytes_not(image_guard(), IMAGE_GUARD_BYTES, IMAGE_GUARD_FILL);
    g_record[REC_TAIL] = FS_RECORD_TAIL;

#if FS_SMOKE
    write_file(FILE_STATE_RECORD, g_record, (long)sizeof g_record);
#endif

    fs_leave_supervisor(fs_saved_ssp);
}
