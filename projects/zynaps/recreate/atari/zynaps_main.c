/* zynaps_main.c — the shim: stage the image, compose the boot's VERIFIED slices in the original's
 * order, hand the machine over, run the title screen with its music, hand it back.
 *
 * WHAT THIS BUILD IS. Milestone M1: the first time any of `projects/zynaps/recreate/`'s verified
 * rows has executed on a 68000. It runs `_start`'s slices up to 0x101ba and NOT ONE INSTRUCTION
 * PAST — that is where the reconstruction stops (../STATUS.md, "Not reconstructed": 0x101ba is
 * where the ninth file would be opened and the harness's staged-file table holds eight), so this
 * composes exactly what is verified and stops where the verification stops. The frame loop, the
 * front end and the rest of the boot chain are M2's, after the next port wave.
 *
 * THE IMAGE MODEL SURVIVES ONTO THE MACHINE. The cores index a flat `uint8_t *image` at Ghidra
 * addresses; here that is a 1 MiB .bss array whose base is rounded up to 256 at RUN TIME, and the
 * game's two hard-coded framebuffers become `image + 0x70300` and `image + 0x78000` — real
 * addresses handed to a real shifter. Everything the cores route through a modelled sink (a file
 * read, a palette upload, a screen base, a resolution byte, a chip register) becomes a real store
 * here or in zynaps_backend.c; README.md's seam table is the inventory, one row per symbol.
 *
 * WHY THE BASE IS ROUNDED AT RUN TIME. An STF's video base register has no low byte — $ff8201 and
 * $ff8203 hold bits 23-16 and 15-8 and there is no third — so an address that is not 256-byte
 * aligned is TRUNCATED and the shifter displays from up to 255 bytes below where the program drew.
 * GEMDOS loads a .PRG wherever the TPA falls, which is not 256-aligned, so nothing in the linker
 * script can fix this and an `__attribute__((aligned(256)))` on the array is simply irrelevant. The
 * fix is slack plus arithmetic, and the assertion is `Physbase()`: TOS reads the register back, so
 * a published base that equals what was passed is a published base that was aligned.
 * docs/on-target-execution.md class 8 is the whole story — framebuffer-identical, picture wrong.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "os.h"
#include "psg.h"

#include "entity.h"
#include "frame.h"
#include "hud.h"
#include "init.h"
#include "input.h"
#include "irq.h"
#include "player.h"
#include "score.h"
#include "sound.h"
#include "tos.h"
#include "video.h"
#include "zynaps_target.h"

/* ================================================================================================
 * The build's own knobs. build.sh passes PROGRAM_BYTES (measured off the staged file, so the read
 * cannot be short), ZY_LOAD_BASE (scraped from ../project.toml, which is where the 0x10000 base is
 * argued for) and, for the negative control, ZY_FAULT_PEN.
 * ============================================================================================= */
#if !defined(PROGRAM_BYTES) || !defined(ZY_LOAD_BASE)
#error "build.sh must pass -DPROGRAM_BYTES=<bytes of disk/ZYNAPS.IMG> and -DZY_LOAD_BASE=<load_base>"
#endif

/* Vertical blanks the title screen runs for before the anchor. ~5 seconds at 50 Hz: long enough for
 * the tune to be unmistakably running (the driver ticks once a vblank) and for smoke.py to have
 * read BASE.BIN and armed its breakpoint, which this writes before the eight file loads. */
#ifndef ZY_SMOKE_VBLS
#define ZY_SMOKE_VBLS 250u
#endif

/* ================================================================================================
 * HOW FAR THIS BUILD RUNS — the one `#if` in this file, and the whole difference between M1 and M2.
 *
 * M1 (`build.sh title`, `titlefault`, `floppy`) composes `_start`'s first five slices, shows the
 * title picture with its music and hands the machine back. M2 (`build.sh game`, `play`) composes
 * the WHOLE PROGRAM: the rest of the boot, the attract loop, the section chain, the frame loop and
 * the endings, in the original's own order and out of nothing but verified slices.
 *
 * IT IS ONE `#if` AND NOT TWO BUILDS because everything before the fork — staging the image, the
 * boot's first five slices, the vector install, the record, the hand-back — is the same code in
 * both, and a second `main` would be a second copy of it drifting quietly out of step with the one
 * `smoke.py title` certifies.
 * ============================================================================================= */
#define ZY_PHASE_TITLE 0
#define ZY_PHASE_GAME  1
#ifndef ZY_PHASE
#define ZY_PHASE ZY_PHASE_TITLE
#endif

/* ...and how far the M2 build runs before it stops and hands the machine back. A `frame_loop_once`
 * count, because that is the unit both sides of the frame differential agree on: the original's own
 * loop head at 0x10f4e passes once per frame and the debugger counts its hits, so "frame 240" means
 * the same thing to a breakpoint as it does to this counter. `build.sh play` sets it out of reach,
 * exactly as it sets ZY_SMOKE_VBLS out of reach for the title build. */
#ifndef ZY_GAME_FRAMES
#define ZY_GAME_FRAMES 300u
#endif

/* THE FRONT END HAS NO SUCH BUDGET AND CANNOT HAVE ONE, which is worth saying rather than leaving a
 * reader to wonder. `attract_wait_for_start` and `section_start_tail`'s fire wait are VERIFIED
 * SLICES that spin inside themselves on a byte the ACIA handler writes; the shim is not in the loop
 * and has nothing to count. So an input that never arrives is an unbounded spin, exactly as it is
 * on the original — the emulator's `--run-vbls` is the bound, and the finding is a missing
 * STATE.BIN plus a `phase_reached` that never advanced. That is M1's own argument for its title
 * wait, one phase further on. */

/* ------------------------------------------------------------------------------------------------
 * THE PACING SURFACE — how many vertical blanks one `frame_loop_once` took, as a DISTRIBUTION.
 *
 * THE GAME'S FRAME RATE IS NOT A HOST STOPWATCH, it is this histogram. `frame_end_and_flip`
 * (../src/frame.c) ends by waiting for `A_vbl_wait_flag`, and the handler that clears it is
 * `vbl_menu`, whose raster phase counts up and wraps at RASTER_PHASE_PERIOD — so a frame that fits
 * its budget is released on the SECOND vertical blank and takes exactly 2, and one that overruns
 * misses that release and waits for the next. The cadence is therefore QUANTISED in steps of two,
 * and a MEAN ALONE WOULD HIDE A 2/2/2/4 STUTTER the shipped binary does not have.
 *
 * "STEPS OF TWO" IS THE MECHANISM AND NOT AN INVARIANT, which is worth the extra sentence because
 * the measurements below contain the exceptions. `A_raster_phase` is FREE-RUNNING — nothing resets
 * it at a frame boundary — so a frame whose head arrives with the phase already at
 * FRAME_RASTER_PHASE_READY skips its first wait and lands one vblank short of the step. The shipped
 * binary's own timeline, measured with `atari/profile.py original-frames` over 542 frames of
 * section 1, is 496 frames at 2 vblanks, 2 at 3, 42 at 4 and 2 at 45 (a death and its respawn);
 * ours over 534 of the `play` build is 10 at 4, 505 at 6, 2 at 7, 15 at 8 and two long entries of
 * the same kind. `smoke.py`'s `check_the_pacing` judges the mean and the tail rather than asserting
 * a parity the machine does not keep.
 *
 * IT IS MEASURED ACROSS `frame_loop_once` ALONE and not across the whole loop body, so what it
 * reports is the GAME's pacing rather than the harness's: `capture_frame_sample` writes 64 KB
 * through GEMDOS at five of a 300-frame run's frames, and a span that included it would charge the
 * program for the harness's own file I/O. The play build makes no captures at all, which is what
 * makes the two builds' histograms comparable.
 *
 * ITS COST IS ABOUT 70 CYCLES A FRAME, COUNTED OFF THE GENERATED CODE rather than guessed: twelve
 * instructions inlined into `play_one_game` — two absolute loads of `zy_vbl_ticks`, the subtraction,
 * the clamp's compare and its two `add`s of the longword index scale, the indexed `addq`, and the
 * absolute read-modify-write of `g_playing_vbls`. Against a frame that costs 815,000 that is
 * 0.009%, so unlike the address-keyed hardware ledger zynaps_backend.c describes, this is nowhere
 * near the cliff — and it is compiled into every build rather than into the smoke ones alone,
 * because a pacing surface the build a person plays did not carry would be a surface for a
 * different program. It runs on the MAIN LINE and not in an interrupt, which is the other half of
 * why it is affordable.
 *
 * Slots 0..PACING_OVERFLOW_SLOT-1 hold that exact vblank count; the LAST slot is "that many or
 * more", so a pathologically slow frame is still counted rather than indexing off the end. Seven is
 * three and a half times the budget and one past the worst frame measured on this build. */
#define PACING_SLOTS          8u
#define PACING_OVERFLOW_SLOT  (PACING_SLOTS - 1u)

/* ...and how long `zy_anchor` holds after the smoke's breakpoint fires on it. The capture is
 * STOP-THEN-SHOOT (docs/on-target-execution.md class 8): the breakpoint here stops the machine, its
 * action file arms a SECOND breakpoint some vertical blanks later, and that one photographs. So the
 * anchor has to still be standing when the shot is taken, or the picture would be of the teardown.
 *
 * PINNED AGAINST THE SMOKE'S OWN OFFSET rather than agreed with it: the number is published in
 * STATE.BIN and smoke.py refuses a build whose hold is not longer than the delay it photographs at.
 * The two live in different languages and neither can import the other, so the check is the pin
 * (CLAUDE.md §5). Sixteen against the smoke's eight leaves room for the shot to be moved later
 * without a silent race — the cost is 320 ms of a title screen that runs for five seconds. */
#define ZY_ANCHOR_HOLD_VBLS 16u

/* The negative control: one pen corrupted on its way to the shifter, and NOTHING else — the cores
 * draw the same bytes and make the same calls. So the memory, trap-ledger and timeline surfaces
 * must stay green while the pens and the rendered picture go red, and smoke.py inverts its verdict.
 * -1 is "no fault", which is what the shipped build publishes.
 *
 * THE PEN REACHES SMOKE.PY THROUGH THE RECORD, never through a scrape of build.sh: the per-mode
 * .PRGs outlive an edit to that script, so a scraped number could name a pen the running binary
 * never injected. Wonder Boy's `fault_pen` is the same rule, learned the same way. */
#ifndef ZY_FAULT_PEN
#define ZY_FAULT_PEN (-1)
#endif
/* What the fault does to it. XOR with full white inverts all three guns, so the corrupted pen is
 * maximally far from the true one and is still a legal ST colour whatever the true one was — a
 * fault that happened to land on the pen's own value would be a control that cannot fail. */
#define ZY_FAULT_XOR 0x777u
/* AND IT IS A COLOUR REGISTER INDEX, so it is bounded at COMPILE TIME. build.sh's FAULT_PEN is a
 * plain shell variable; set it to 16 and `shifter_pen_register` returns $ffff8260, the RESOLUTION
 * register, and the control's one word store changes the screen mode and hangs the machine
 * (docs/on-target-execution.md class 6). smoke.py refuses such a pen too — but only out of a record
 * a machine in that state can no longer write, so the operator would get a black screen and a
 * timeout. -1 is the shipped build's "no fault" and is the one value below the range. */
_Static_assert(ZY_FAULT_PEN < (int)PALETTE_PENS,
               "ZY_FAULT_PEN is a colour register index; $ff8260 is four registers past the last");

/* ================================================================================================
 * The machine's fixed addresses. `HW_BUS`, `SHIFTER_PEN_BYTES` and `shifter_pen_register` are
 * shim_include/zynaps_target.h's: both shim translation units need them, and one definition is what
 * stops the two spellings of an address drifting (CLAUDE.md §5).
 * ============================================================================================= */

/* The 68000 exception vectors the boot replaces. include/init.h names the IMAGE offsets the cores
 * store into (`A_vector_vbl`, `A_vector_timer_b`); these are the REAL vectors, and the two are not
 * the same thing — the cores write a vector page inside a 1 MiB array, which is diffable memory and
 * not the machine's. Derived from init.h's constants rather than retyping 0x70, which is what says
 * they are the same two vectors. */
/* Read and write one, and they exist as FUNCTIONS for a reason that is not style. Dereferencing an
 * integer constant as a pointer is an out-of-bounds `array[0]` access as far as GCC is concerned,
 * so it warns — and the obvious answer, `-Wno-array-bounds` on the command line, would switch the
 * warning off for the VERIFIED CORES too, in the one build where such an access reads live machine
 * memory rather than the harness's guarded image. Two accessors put the suppression exactly where
 * the deliberate absolute address is. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"

static uint32_t read_vector(uint32_t vector) {
    return *(volatile uint32_t *)(uintptr_t)vector;
}

static void write_vector(uint32_t vector, uint32_t handler) {
    *(volatile uint32_t *)(uintptr_t)vector = handler;
}

/* TOS's own 200 Hz counter at $4ba (`_hz_200`), which is the ONE stopwatch that runs across this
 * program's boot. `zy_vbl_ticks` cannot be it and that is a measurement, not a guess: the boot
 * loads its files BEFORE it puts its own handler on the vertical-blank vector, so the counter is
 * still 0 when both loaders have finished (measured — the first draft of the boot clock printed
 * two zeroes). Timer C drives $4ba, TOS enables it before this program starts, and the boot's
 * `bset` on the MFP's interrupt-enable B preserves it — which is exactly what the read-modify-write
 * doors exist for — so it keeps ticking the whole way through. One tick is 5 ms. */
#define TOS_HZ_200_COUNTER 0x4bau

static uint32_t read_hz_200(void) {
    return *(volatile uint32_t *)(uintptr_t)TOS_HZ_200_COUNTER;
}

#pragma GCC diagnostic pop

/* The shifter, in the bus form a C pointer needs. Every address here is a CORE header's constant
 * put through `HW_BUS` — include/video.h owns the colour block and the two video-base bytes,
 * include/init.h owns the resolution byte — so this file spells no hardware address of its own. */
#define HW_SHIFTER_RESOLUTION HW_BUS(HW_SHIFTER_MODE)
#define HW_SHIFTER_BASE_HIGH  HW_BUS(HW_SCREEN_BASE_HIGH)  /* address bits 23-16 */
#define HW_SHIFTER_BASE_MID   HW_BUS(HW_SCREEN_BASE_MID)   /* ...and 15-8; an STF has no low byte */
#define SHIFTER_PEN_MASK 0x777u   /* three bits a gun; a CPU read returns the unused fourth as noise */
#define SHIFTER_RESOLUTION_MASK 0x03u  /* $ff8260 bits 0-1; the rest read back as noise too */

/* The IKBD commands `_start` sends at 0x1001c and 0x10024 (`move.b #$12,d0` / `#$15` ahead of each
 * `bsr ikbd_send_cmd`). $12 disables the mouse — without it the 6301 reports joystick 1's fire line
 * as a MOUSE packet, which is the defect docs/on-target-execution.md class 12 is named for — and
 * $15 puts the controller into joystick INTERROGATION mode, which is what the game's later
 * PREPARE-FOR-COMBAT gate polls with $16. Neither matters to M1's picture; both are sent because
 * the boot sends them, and the record carries whether the transmitter took them. */
#define IKBD_CMD_DISABLE_MOUSE 0x12u
#define IKBD_CMD_JOYSTICK_INTERROGATION_MODE 0x15u

/* Silencing the chip on the way out: the mixer, then the three channel volumes. Both constants are
 * ../include/sound.h's (`PSG_REG_MIXER`, `PSG_MIXER_ALL_OFF`, `PSG_REG_VOLUME_A`), reused rather
 * than respelt; this is only how many volumes follow the first. */
#define PSG_VOLUME_REGISTERS 3u

/* ================================================================================================
 * The image. OS_IMAGE_SIZE is the kit's, and ../project.toml's `image_size` must equal it — so this
 * array is the same 1 MiB the differential runs on, by construction rather than by agreement.
 *
 * A 1 MiB .bss is why this build needs `--memsize 4`: TOS 1.04's TPA on a 1 MB machine leaves a
 * megabyte of program plus its stack no room at all. README.md says so where a reader will meet it.
 * ============================================================================================= */
#define IMAGE_ALIGN 256u

static uint8_t g_image_store[OS_IMAGE_SIZE + IMAGE_ALIGN];

/* The aligned base. Read by the interrupt entries as well as the main line, hence not a local — and
 * NOT static any more, because zynaps_backend.c reads it too: the video-base door is where an image
 * offset becomes a machine address (see shim_include/zynaps_target.h). */
uint8_t *zy_image_base;

/* Written from zynaps_os.s (see zynaps_target.h), read by the hand-back. */
void *zy_saved_ssp;

volatile uint32_t zy_vbl_ticks;
volatile uint32_t zy_timer_b_ticks;
volatile uint32_t zy_acia_ticks;

/* ================================================================================================
 * The interrupt entries' C halves, and the DISPATCH they are built around.
 *
 * zynaps_os.s supplies each entry's `movem` pair and its `rte`; there are three entries and SEVEN
 * handlers, because the program re-points its vectors per phase. `boot_load_title_assets` puts the
 * in-game pair on $70/$120, `boot_program_timer_b` swaps the VBL for the menu's, the raster timer
 * swaps Timer B for the split, and `title_attract_loop` swaps both for attract mode's and back
 * again — twelve stores in the whole program, of seven distinct handler addresses (the shipped
 * disassembly's own count).
 *
 * THE CORES MAKE THOSE STORES INTO THE IMAGE'S VECTOR PAGE, which on the real machine IS low memory
 * but here is a longword inside a 1 MiB array. So the store is ordinary diffable memory that the
 * differential already holds, and the shim's job is to READ IT BACK: each entry looks at the
 * longword the cores wrote and calls the handler it names. That is what makes a phase change take
 * effect without the shim knowing which phase the program thinks it is in.
 *
 * AN ADDRESS THE TABLE DOES NOT KNOW IS A HALT, never a silent skip. A skipped interrupt is the
 * worst possible failure here: the frame loop's sync waits would simply never end and the run would
 * look like a hang with nothing in it. So the value is latched, the halt is counted, and
 * `g_fatal` stops the game at its next frame boundary so that the record — which is the only thing
 * that can say what happened — is still written.
 * ============================================================================================= */

/* Set from inside an interrupt and read on the main line, hence `volatile`. `g_fatal_vector` and
 * `g_fatal_handler` say WHICH vector held WHAT, because "an unknown handler" without those two
 * numbers is not a finding anybody can act on. */
static volatile uint32_t g_fatal;
static volatile uint32_t g_fatal_vector;
static volatile uint32_t g_fatal_handler;

/* One binding per handler the program can install, with the count of times it was entered. The
 * counts are the surface: `smoke.py` reads them to say which phases actually ran, and a phase whose
 * handler was installed but never entered is exactly the shape M1's Unpinned 1 recorded. */
struct isr_binding {
    uint32_t address;                    /* the Ghidra address the cores store into the image */
    void (*handler)(uint8_t *image);     /* ...and the verified routine in ../src/irq.c */
    volatile uint32_t entries;
};

/* The one handler address no core header names, because no core reads it: ../../names.txt's
 * `vbl_isr_title`, verified in ../src/irq.c but never installed by the shipped binary (see below).
 * Spelt here rather than in ../include/irq.h so that no core acquires a constant it has no use for. */
#define A_vbl_isr_title 0x106a2u

/* `vbl_isr_title` @ 0x106a2 IS IN THE TABLE AND NO STORE IN THE PROGRAM NAMES IT — measured, by
 * grepping every `move.l #$x,$70/$118/$120` in the shipped disassembly: twelve stores, seven
 * addresses, and this is not one of them. ../../names.txt names it and it ends in `rte`, so it is a
 * handler that the shipped binary never installs. It is listed because an entry that costs eight
 * bytes and turns a halt into a dispatch is cheaper than the alternative, and its count staying 0
 * is the measurement rather than a belief. */
static struct isr_binding VBL_HANDLERS[] = {
    {A_vbl_isr, vbl_isr, 0},                    /* 0x10776 — in-game and title */
    {A_vbl_isr_title, vbl_isr_title, 0},        /* 0x106a2 — never installed; see above */
    {A_vbl_menu, vbl_menu, 0},                  /* 0x13c26 — the front end's, at half rate */
    {A_attract_vbl_isr, attract_vbl_isr, 0},    /* 0x12c9e — attract mode's colour bars */
};

/* THE M2 NEGATIVE CONTROL LIVES IN `play_one_game`, not here — see the note beside its call to
 * `section_reload_intro_screens`. The first draft put it in this table, binding the RASTER split's
 * vector (0x106ae) to the plain in-game Timer B, and it was MEASURED NOT TO ISOLATE ANYTHING: every
 * surface stayed green, because the pens are sampled at the loop head and whatever the split's
 * mid-screen upload had done to them has been undone by the time the frame ends. A control that
 * cannot go red says nothing about the checks it exists for, so it was replaced by one that does.
 *
 * The mode still reaches smoke.py through the RECORD rather than through a scrape of build.sh —
 * the per-mode .PRGs outlive an edit to that script. */
#ifndef ZY_GAME_FAULT
#define ZY_GAME_FAULT 0
#endif

static struct isr_binding TIMER_B_HANDLERS[] = {
    {A_timer_b_isr, timer_b_isr, 0},                    /* 0x10782 */
    {A_timer_b_raster_isr, timer_b_raster_isr, 0},      /* 0x106ae — the in-game raster split */
    {A_attract_rasterbar_isr, attract_rasterbar_isr, 0},/* 0x12cc0 — one bar per scanline */
};

static struct isr_binding ACIA_HANDLERS[] = {
    {A_ikbd_acia_isr, ikbd_acia_isr, 0},                /* 0x14456 — the only one */
};

#define VBL_HANDLER_SLOTS     (sizeof VBL_HANDLERS / sizeof VBL_HANDLERS[0])
#define TIMER_B_HANDLER_SLOTS (sizeof TIMER_B_HANDLERS / sizeof TIMER_B_HANDLERS[0])
/* ../include/frame.h's enum is the five addresses the last stage leaves through; this is how many,
 * so the record can carry one tally per exit and `smoke.py` can name which one ended the run. */
#define FRAME_EXIT_COUNT (FRAME_EXIT_NEXT_FRAME + 1)
/* `acknowledge` IS THE MFP'S, AND IT IS WHY THIS TAKES A FOURTH ARGUMENT. Every handler in the two
 * MFP tables ends by clearing its own in-service bit, and the MFP blocks every LOWER-priority
 * channel until that happens — so the halt path below, which by definition calls no handler, has to
 * make that store itself or the machine is wedged for good and cannot even write the record. The
 * vertical blank is an autovector and has none, so it passes 0. */
static void dispatch_image_vector(uint32_t image_vector, struct isr_binding *table, unsigned slots,
                                  void (*acknowledge)(void)) {
    uint32_t handler = be32(zy_image_base + image_vector);

    for (unsigned slot = 0; slot < slots; slot++)
        if (table[slot].address == handler) {
            table[slot].entries++;
            table[slot].handler(zy_image_base);
            return;
        }
    g_fatal_vector = image_vector;
    g_fatal_handler = handler;
    g_fatal = 1;
    if (acknowledge != 0)
        acknowledge();
}

#define DISPATCH(vector, table, acknowledge) \
    dispatch_image_vector((vector), (table), sizeof (table) / sizeof (table)[0], (acknowledge))

/* The count is bumped BEFORE the handler runs, so a spin that sees N has had N handler entries.
 * Nothing here samples a count and an image word TOGETHER, so the sibling project's skew problem —
 * which needed a masked critical section around the pair — does not arise; the one place two of
 * these counters ARE read together is the anchor, and that read is masked. */
void zy_vbl_tick(void) {
    zy_vbl_ticks++;
    DISPATCH(A_vector_vbl, VBL_HANDLERS, 0);
}

void zy_timer_b_tick(void) {
    zy_timer_b_ticks++;
    DISPATCH(A_vector_timer_b, TIMER_B_HANDLERS, mfp_ack_timer_b);
}

void zy_acia_tick(void) {
    zy_acia_ticks++;
    DISPATCH(A_vector_acia, ACIA_HANDLERS, mfp_ack_acia);
}

/* ================================================================================================
 * The record. STATE.BIN, one big-endian longword per field, in this order.
 *
 * PINNED ACROSS THE LANGUAGE BOUNDARY BY ITS OWN LENGTH: field 1 is the field count, and smoke.py
 * refuses a record whose count does not equal the length of its name list. So a field added here
 * and not there fails at the parse with the two numbers printed, rather than silently shifting
 * every value after it by one and reporting a wrong pen (CLAUDE.md §5).
 * ============================================================================================= */
#define ZY_RECORD_MAGIC 0x5a594d31u   /* 'ZYM1' */
#define ZY_RECORD_TAIL  0x444f4e45u   /* 'DONE' — written last, so a truncated dump is detectable */

/* The three `*_END` members are not read by anything: they exist so that a pen block's WIDTH is
 * declared where the block is, and the field after it follows the last pen rather than the first. */
enum {
    REC_MAGIC, REC_FIELDS,
    REC_IMAGE_BASE, REC_PROGRAM_STAGED_BYTES, REC_SUPER_TOKEN,
    REC_ACIA_BYTES_AFTER_MOUSE_OFF, REC_ACIA_BYTES_AFTER_JOYSTICK_MODE,
    REC_SHIFTER_MODE_WRITES, REC_SHIFTER_MODE_MASK, REC_PALETTE_LONG_WRITES,
    REC_IMAGE_SAVED_VBL_VECTOR, REC_TOS_VBL_VECTOR, REC_TOS_TIMER_B_VECTOR,
    REC_IMAGE_SCREEN_BACK, REC_IMAGE_SCREEN_FRONT, REC_PUBLISHED_SCREEN_BASE,
    REC_PHYSBASE_AT_ANCHOR, REC_RAW_VIDEO_BASE_AT_ANCHOR, REC_REZ_AT_ANCHOR,
    REC_VBL_TICKS_AT_ANCHOR, REC_TIMER_B_TICKS_AT_ANCHOR,
    REC_TICKS_AT_TITLE_ASSETS, REC_TICKS_AFTER_TITLE_ASSETS,
    REC_TICKS_AT_GAMEPLAY_ASSETS, REC_TICKS_AFTER_GAMEPLAY_ASSETS, REC_TICKS_AT_TEARDOWN,
    REC_PSG_WRITES, REC_PSG_REFUSED, REC_HW_WRITES,
    REC_FILE_OPENS, REC_FILE_OPEN_FAILURES, REC_FILE_REFUSALS,
    REC_FAULT_PEN, REC_SMOKE_VBLS, REC_ANCHOR_HOLD_VBLS, REC_SCREEN_BYTES_WRITTEN,
    REC_PENS_AT_ENTRY,  REC_PENS_AT_ENTRY_END  = REC_PENS_AT_ENTRY  + PALETTE_PENS - 1,
    REC_PENS_AT_ANCHOR, REC_PENS_AT_ANCHOR_END = REC_PENS_AT_ANCHOR + PALETTE_PENS - 1,
    REC_VBL_VECTOR_AFTER, REC_TIMER_B_VECTOR_AFTER, REC_PHYSBASE_AFTER, REC_REZ_AFTER,
    REC_PENS_AFTER,     REC_PENS_AFTER_END     = REC_PENS_AFTER     + PALETTE_PENS - 1,

    /* ---- M2's own fields: the program's own account of the run — how far it got, what it
     * dispatched, what it wrote and where it stopped. Every one is a number the machine cannot be
     * asked for afterwards.
     *
     * THE ONES UNDER THE `#if` ARE 0 IN A TITLE BUILD and the ones outside it are not, which is a
     * distinction worth drawing because `smoke.py title`'s `check_the_game_fork_was_not_taken`
     * rests on it: `phase_reached`, `attract_passes`, `section_starts` and `frames_run` are written
     * only by the game path, while `acia_ticks`, the dispatch counts, the two ACIA vectors and the
     * video-base trio are written by both (a title build publishes a screen base and substitutes
     * the `$ff8260` read-modify-write like any other). */
    REC_PHASE_REACHED, REC_ATTRACT_PASSES, REC_SECTION_STARTS, REC_FRAMES_RUN,
    REC_FRAME_EXITS,   REC_FRAME_EXITS_END   = REC_FRAME_EXITS + FRAME_EXIT_COUNT - 1,
    REC_VBL_DISPATCHES, REC_VBL_DISPATCHES_END = REC_VBL_DISPATCHES + VBL_HANDLER_SLOTS - 1,
    REC_TIMER_B_DISPATCHES,
    REC_TIMER_B_DISPATCHES_END = REC_TIMER_B_DISPATCHES + TIMER_B_HANDLER_SLOTS - 1,
    REC_ACIA_TICKS, REC_ACIA_DISPATCHES,
    REC_UNKNOWN_VECTOR_HALTS, REC_UNKNOWN_VECTOR, REC_UNKNOWN_VECTOR_HANDLER,
    REC_MFP_SETTLE_RESTORES, REC_RMW_STORES,
    REC_TOS_ACIA_VECTOR, REC_ACIA_VECTOR_AFTER,
    REC_PLAYER_COUNT, REC_LEVEL_SECTION, REC_LIVES, REC_SCORE_BCD, REC_FRAME_DUMP_BYTES,
    REC_GAME_FAULT, REC_FIRST_LIFE_ENDED_AT,
    /* The video-base door's own account — the offset the cores last published, the machine address
     * it was translated to, and how many pairs went up. */
    REC_VIDEO_BASE_OFFSET, REC_VIDEO_BASE_PUBLISHED, REC_VIDEO_BASE_PUBLISHES,
    /* THE PACING SURFACE: one slot per vertical-blank count a frame took (see `note_frame_pacing`),
     * plus the vblanks the frame loop spent in total, which is what gives the exact mean. The two
     * interrupt SERVICE RATES are computed from the dispatch counts already above: a handler's
     * entry count over the vertical blanks its own phase's VBL handler was the installed one. */
    REC_FRAME_VBLS,    REC_FRAME_VBLS_END    = REC_FRAME_VBLS + PACING_SLOTS - 1,
    REC_PLAYING_VBLS,

    REC_TAIL,
    REC_FIELD_COUNT
};

static uint32_t g_record[REC_FIELD_COUNT];

/* TOS's machine as it stood when this program was loaded, so the teardown can give exactly it back.
 * One struct rather than six arguments: every field is restored by the same routine and read back
 * by the same routine, so they are one thing. */
struct tos_state {
    uint32_t vbl_vector;
    uint32_t timer_b_vector;
    /* MFP channel 6's vector, $118, where TOS's own keyboard handler lives. Saved and restored like
     * the other two because the game displaces it (0x104e2) and a handler left there keeps being
     * entered out of memory GEMDOS has taken back — with a keyboard behind it, which means every
     * keypress after the exit. */
    uint32_t acia_vector;
    /* Interrupt-enable A and its mask. The program stores them WHOLE — `clr.b $fffa07` at 0x12ac2
     * and `move.b #$1,$fffa07`/`$fffa13` in `boot_enable_interrupts` — so every channel of A that
     * TOS had open is closed by the time this build hands back, and unlike the B pair (which the
     * cores read-modify-write) nothing preserved them. Saved as bytes and put back. */
    uint8_t mfp_iera;
    uint8_t mfp_imra;
    /* ...and the B pair, which the game only ever SETS a bit in — so TOS's other bits survive the
     * run today. They are saved anyway because what makes that true is a TEMPORARY bridge in
     * zynaps_backend.c, and the hand-back must not depend on a block whose own header says to
     * delete it. See `hand_the_machine_back`. */
    uint8_t mfp_ierb;
    uint8_t mfp_imrb;
    uint32_t logbase;
    uint32_t physbase;
    short rez;
    uint32_t pens[PALETTE_PENS];
};

/* ================================================================================================
 * The files this build moves. Uppercase 8.3 so a GEMDOS drive cannot rename them, and named here
 * once because smoke.py's TRAP-LEDGER arm has to tell the SHIM's own I/O from the GAME's: that
 * check compares our Fopen/Fread/Fclose sequence against the original binary's, and the original
 * opens no ZYNAPS.IMG and writes nothing at all. README.md states the exclusion rule; these four
 * names are it.
 * ============================================================================================= */
#define FILE_PROGRAM_IMAGE "ZYNAPS.IMG"   /* the relocated program, read into image + ZY_LOAD_BASE */
#define FILE_ANCHOR_BASE   "BASE.BIN"     /* 4 bytes: where `zy_anchor` landed, for the breakpoint */
#define FILE_SCREEN_DUMP   "SCREEN.BIN"   /* 32000 bytes: the buffer the shifter was displaying */
#define FILE_STATE_RECORD  "STATE.BIN"    /* the record above */

#define GEMDOS_OPEN_READ     0            /* Fopen mode: read-only, the mode `load_file` uses */
#define GEMDOS_CREATE_NORMAL 0            /* Fcreate attr: an ordinary read/write file */

/* Write a whole buffer to a fresh file. Returns what GEMDOS says it wrote, or a negative error, so
 * a caller can put the answer in the record rather than assume it. */
static long write_file(const char *name, const void *data, long bytes) {
    long handle = Fcreate(name, GEMDOS_CREATE_NORMAL);
    long written;

    if (handle < 0)
        return handle;
    written = Fwrite((short)handle, bytes, data);
    Fclose((short)handle);
    return written;
}

/* THE STAGED READ MUST FIT THE IMAGE, and this is the one place both numbers are in scope. GEMDOS
 * would happily write PROGRAM_BYTES at `zy_image_base + ZY_LOAD_BASE` past the end of a too-small array,
 * over `g_record` and `zy_saved_ssp`; build.sh measures PROGRAM_BYTES off the staged file, so a
 * bigger game binary is exactly how that would arrive. A compile-time refusal costs nothing. */
_Static_assert((uint32_t)ZY_LOAD_BASE + (uint32_t)PROGRAM_BYTES <= OS_IMAGE_SIZE,
               "the staged program does not fit the image at ZY_LOAD_BASE");

/* The relocated program into the image. Everything above ZY_LOAD_BASE + PROGRAM_BYTES is the game's
 * own BSS, which is zero at boot on both shores — TOS zeroes this array and gen_image.py's header
 * says why it does not ship 346 KB of zeros to do the same job. */
static long stage_program_image(void) {
    long handle = Fopen(FILE_PROGRAM_IMAGE, GEMDOS_OPEN_READ);
    long read;

    if (handle < 0)
        return handle;
    read = Fread((short)handle, PROGRAM_BYTES, zy_image_base + ZY_LOAD_BASE);
    Fclose((short)handle);
    return read;
}

/* ================================================================================================
 * Reading the machine back. Every write this shim makes is read back and published — the practical
 * form of docs/on-target-execution.md's rule, and the reason the record is as long as it is.
 * ============================================================================================= */
/* THE REGISTERS ARE READ RAW AND RESTORED RAW; ONLY THE RECORD IS MASKED, and the difference is a
 * machine this build has not run on yet. An STF implements three bits a gun and returns the fourth
 * as bus noise, which is why a COMPARISON has to mask (docs/on-target-execution.md, "mask to the
 * bits the machine implements"). An STE implements four. Masking on the way IN would make the
 * teardown hand back a desktop with the low bit of every gun cleared — and `pen_at_entry` against
 * `pen_after` could not see it, because both would be masked reads. So the round trip carries the
 * whole word and `record_pens` masks. On an STF the extra bit is noise the shifter ignores. */
static void read_pens(uint32_t *out) {
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        out[pen] = *(volatile uint16_t *)shifter_pen_register(pen);
}

/* ...and into the record, masked, so the two sides of every comparison mean the same thing. */
static void record_pens(unsigned field, const uint32_t *pens) {
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        g_record[field + pen] = pens[pen] & SHIFTER_PEN_MASK;
}

static void write_pens(const uint32_t *pens) {
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        hw_write16(shifter_pen_register(pen), (uint16_t)pens[pen]);
}

static uint32_t read_raw_video_base(void) {
    uint32_t high = *(volatile uint8_t *)HW_SHIFTER_BASE_HIGH;
    uint32_t mid = *(volatile uint8_t *)HW_SHIFTER_BASE_MID;

    /* There is no low byte to read, so what comes back always ends in 0x00 — which is the point: if
     * the address handed over did not, this is where the missing bits went. */
    return (high << VIDEO_BASE_HIGH_SHIFT) | (mid << VIDEO_BASE_MID_SHIFT);
}

static uint32_t read_resolution(void) {
    return *(volatile uint8_t *)HW_SHIFTER_RESOLUTION & SHIFTER_RESOLUTION_MASK;
}

/* ================================================================================================
 * THE TWO SHIFTER EFFECTS THE SHIM STILL OWNS — and there used to be three.
 *
 * The cores make their own hardware stores now: `set_palette_title` ends in eight `hw_write32`s
 * over the colour block and `shifter_select_low_resolution` in one `hw_write8` to $ff8260, and
 * zynaps_backend.c turns each into the real store. So the two publishes that used to REPLAY those
 * writes on the cores' behalf are gone, and what is left below is what the cores genuinely cannot
 * do from inside a relocated image.
 *
 * $ff8260 NEEDED NO REPLAY AND NEEDS NO APOLOGY EITHER. ../include/init.h calls the core's
 * `hw_write8(HW_SHIFTER_MODE, 0 & mask)` an on-target defect, because off target the read half of
 * `andi.b #$fc,$ff8260` answers a fabricated 0 and the mask's other six bits are lost. On this
 * register they are lost to nothing: $ff8260 decodes TWO bits, and both `andi.b #$fc,<anything>`
 * and a plain 0 leave them clear, which is ST low resolution either way. The rule the kit states —
 * a read-modify-write must not be shipped as a store — is real and stands for $fffa0f (README.md's
 * unpinned list carries that one); this particular instance is measured harmless and the record
 * says so through `rez_at_anchor`.
 * ============================================================================================= */

/* `move.b d0,$ff8203` then `move.b d0,$ff8201` at the tail of `screen_flip_buffers` (0x1297a) —
 * publish the buffer just drawn into, as the CORE spells it: an image offset, which the hardware
 * door translates (shim_include/zynaps_target.h, and zynaps_backend.c's `video_base_store`).
 *
 * WHY THIS STILL EXISTS NOW THE DOOR TRANSLATES. The core has already published the buffer it drew
 * into, and this re-publishes the FRONT buffer — the same bytes, and normally the same value. What
 * it is for is the record: `published_screen_base` is the address the shim believes the shifter is
 * pointed at, and `raw_video_base_at_anchor` reads the register back, so the pair is the surface
 * for a translation that silently stopped happening. Deleting it would leave that assertion with
 * nothing on one side of it.
 *
 * IT PUBLISHES THE OFFSET AND NOT THE MACHINE ADDRESS, which is the M1 shape inverted: pre-adding
 * the base here and then letting the door add it again would translate twice. */
static uint32_t publish_screen_base(void) {
    uint32_t front = be32(zy_image_base + A_screen_front);

    hw_write8(HW_SHIFTER_BASE_MID, (uint8_t)(front >> VIDEO_BASE_MID_SHIFT));
    hw_write8(HW_SHIFTER_BASE_HIGH, (uint8_t)(front >> VIDEO_BASE_HIGH_SHIFT));
    return (uint32_t)(uintptr_t)zy_image_base + front;
}

/* THE NEGATIVE CONTROL, and it is now literally what the mode's name claims: ONE PEN corrupted on
 * its way to the shifter and nothing else. The core has already uploaded the true row, so this
 * reads that pen back off the chip and stores it inverted — one word-wide store, which is also why
 * it cannot disturb `zy_palette_long_writes` (zynaps_backend.c keys that on the LONGWORD width the
 * core's `movem` upload uses).
 *
 * It compiles to nothing at all in the shipped build: ZY_FAULT_PEN is -1 there and the `if` is a
 * compile-time constant. The pen number still reaches smoke.py through the record rather than
 * through a scrape of build.sh — the per-mode .PRGs outlive an edit to that script. */
static void inject_pen_fault(void) {
    if (ZY_FAULT_PEN < 0)
        return;
    {
        uint32_t register_address = shifter_pen_register((unsigned)ZY_FAULT_PEN);
        uint16_t truth = *(volatile uint16_t *)register_address;

        hw_write16(register_address, (uint16_t)(truth ^ ZY_FAULT_XOR));
    }
}

/* ================================================================================================
 * The anchor. smoke.py breaks on THIS function's entry — its runtime address is what BASE.BIN
 * carries — and its action file arms the next-vertical-blank breakpoint that photographs the screen
 * and dumps the shifter. So the routine's job is to still be here a few vblanks later.
 *
 * `noinline` is not decoration: inlined, the symbol would have no address to break on and the smoke
 * would report a breakpoint that never fired, which reads like a crash.
 * ============================================================================================= */
__attribute__((noinline)) static void zy_anchor(void) {
    uint32_t until = zy_vbl_ticks + ZY_ANCHOR_HOLD_VBLS;

    while (zy_vbl_ticks < until)
        ;
}

#if ZY_PHASE == ZY_PHASE_GAME
/* ================================================================================================
 * M2: THE WHOLE PROGRAM.
 *
 * Everything below composes VERIFIED SLICES in the original's own order and adds exactly two things
 * the reconstruction cannot hold: the four MFP read-back spins, and a `frame_loop_once` budget so a
 * headless run stops somewhere a check can name. Both are argued where they stand.
 * ============================================================================================= */

/* How far the run got, in the order the phases happen. In the record, so a run that hung has still
 * said where — which is the only evidence an unbounded wait can leave. */
enum zy_phase_reached {
    PHASE_STAGING = 0,
    PHASE_TITLE_ASSETS,          /* 0x1002c..0x101ba done */
    PHASE_GAMEPLAY_ASSETS,       /* 0x101ba..0x10500 done */
    PHASE_ATTRACT,               /* inside title_attract_loop @ 0x12ac2 */
    PHASE_FRONT_END_SCREENS,     /* 0x10524..0x10792, the panel and the two MFP programmings */
    PHASE_SECTION_START,         /* 0x10814..0x10f4e, the section chain */
    PHASE_PLAYING,               /* inside the frame loop @ 0x10f4e */
    PHASE_BUDGET_SPENT,          /* the frame budget ran out — the ordinary headless ending */
    PHASE_HALTED                 /* an interrupt named a handler the dispatch table does not know */
};

static volatile uint32_t g_phase;
static uint32_t g_attract_passes;
static uint32_t g_section_starts;
static uint32_t g_frames_run;
static uint32_t g_frame_exits[FRAME_EXIT_COUNT];
static uint32_t g_mfp_settle_restores;

/* The pacing histogram and the vblanks the frame loop spent — the surface argued for beside
 * PACING_SLOTS at the top of this file. The histogram alone cannot give the exact mean, because its
 * last slot is "seven or more" and has thrown the exact count away; this is the sum before that. */
static uint32_t g_frame_vbls[PACING_SLOTS];
static uint32_t g_playing_vbls;

static void note_frame_pacing(uint32_t vbls) {
    g_frame_vbls[vbls < PACING_OVERFLOW_SLOT ? vbls : PACING_OVERFLOW_SLOT]++;
    g_playing_vbls += vbls;
}

/* THE FRAME THE FIRST LIFE ENDED ON, and it is what pins the sample list to one life. Every sample
 * frame must be below it: past it the ship has died, `section_start_tail` has asked for the fire
 * button again, and that wait calls `rand16` a driver-dependent number of times — so the random
 * stream the next life runs on is not the same on the two sides and nothing after it is comparable.
 * 0 means the loop never left. `smoke.py game` asserts the relation rather than trusting the list. */
static uint32_t g_first_life_ended_at;

/* ------------------------------------------------------------------------------------------------
 * TEMPORARY — `frame_loop_once`'s two register parameters.
 *
 * The frame loop carries two 68000 registers across a verified callee's `rts`: D1 at the `bsr` into
 * `enemy_fire_and_update_shots` (0x118cc) and D7 at the two ground-spawn calls. Neither is derivable
 * from outside `src/frame.c` — a differential of a leaf compares memory and not the registers the
 * leaf never promised — so `../include/frame.h` makes them PARAMETERS and `../STATUS.md`'s
 * "## Coverage limits" carries the residual. Off target `test_frame.py` takes them FROM THE ORACLE
 * at that PC; on target there is no oracle, and this build must pass something.
 *
 * WHAT EACH ZERO COSTS, MEASURED RATHER THAN ASSUMED:
 *
 *   * `ground_spawn_y_register` costs NOTHING that the shipped data can reach.
 *     `frame_wave_script` returns the value the loop's own instructions write on every path but
 *     three, and the parameter is only those three's fallback. Its high word reaches the spawner's
 *     guard only when the scripted y is exactly 0xffe0, and
 *     `test_no_shipped_ground_script_can_make_the_spawner_read_its_carried_register` walks all
 *     thirteen shipped scripts and finds no such record. So 0 is as right as any other value.
 *
 *   * `chance_index_register` IS A REAL RESIDUAL and this build's chief one. Its high byte indexes
 *     the per-section fire-chance table, so it decides whether enemies fire this frame; measured
 *     over the shipped worlds it takes at least four different values. Zero is a DECLARED input,
 *     not a derivation, and the frame differential is exactly the surface that measures what it
 *     costs — a divergence in enemy fire is a finding with a frame number on it, not a threshold.
 *
 * THE ORCHESTRATOR DELETES THIS BLOCK when the core-fidelity agent's change lands: `frame_loop_once`
 * becomes `frame_loop_once(image)` and derives both for itself, and the call below loses its two
 * arguments with it.
 * --------------------------------------------------------------------------------------------- */
#ifndef ZY_CHANCE_INDEX_REGISTER
#define ZY_CHANCE_INDEX_REGISTER    0u
#endif
#ifndef ZY_GROUND_SPAWN_Y_REGISTER
#define ZY_GROUND_SPAWN_Y_REGISTER  0u
#endif

/* ------------------------------------------------------------------------------------------------
 * The frame differential's own dumps.
 *
 * At each declared frame the program writes what the SHIPPED binary can be asked for by the
 * debugger at the same frame — its front framebuffer, the shifter's sixteen colour registers and
 * the twenty entity records — so the two sides are compared on ranges rather than on anything this
 * build invented. `smoke.py game` breaks the original on its own loop head at 0x10f4e with a hit
 * count and `savebin`s the same three.
 *
 * THE FRAME NUMBER IS THE LOOP HEAD'S OWN PASS COUNT, which is what makes the two comparable: one
 * `frame_loop_once` here is one arrival at 0x10f4e there.
 *
 * THE WRITES HAPPEN WITH TOS'S VERTICAL BLANK DISPLACED, which M1 deliberately never did
 * (docs/on-target-execution.md class 11). It is safe for the same reason the original's own
 * fourteen file LOADS are — they are made in exactly that state and the game works — and it is
 * measured rather than argued: `file_opens` counts them and the run's own GEMDOS ledger shows every
 * one completing. It is also confined to this harness build; `build.sh play`, the one a person
 * watches and the one that goes on a floppy, declares no samples and writes none.
 * --------------------------------------------------------------------------------------------- */
/* EVERY SAMPLE IS INSIDE THE FIRST LIFE, and that bound is the harness's rather than a choice.
 * With a neutral stick and the front end's leftovers still in the entity table the ship died at
 * frame 176 (measured; 184 before the cores' `abcd` carry threading landed) — the frame loop takes
 * its RESTART exit
 * and `section_start_tail` asks for the fire button again — and that wait calls `rand16` once a
 * pass, so the number of passes DECIDES the random state the second life starts from. The two sides
 * are held in that wait by two different drivers (a phase-gated poke here, a breakpoint on the poll
 * there), so they leave it after different numbers of passes and the second life's stream is not
 * pinned. Measured: a sample at frame 240 came out byte-identical once and 42 framebuffer bytes
 * apart twice. README.md's M2 unpinned list carries it, and what would close it is a pin on the
 * random state at each SECTION START rather than only at the first.
 *
 * SO THE LIST STOPS WELL SHORT OF THE DEATH RATHER THAN JUST SHORT OF IT. The frame the ship dies
 * on is EMERGENT — it moved from 184 to 176 when the cores' `abcd` carry threading landed, which is
 * a change to the score and not to the ship — so a last sample chosen to sit a few frames under it
 * would be a list that goes stale on somebody else's commit. `smoke.py`'s
 * `check_the_game_ran` reads the frame the program reports the first life ending on and refuses a
 * sample at or past it, so the margin is checked rather than assumed. */
#ifndef ZY_FRAME_SAMPLES
#define ZY_FRAME_SAMPLES 1u, 30u, 60u, 120u, 240u
#endif

static const uint32_t FRAME_SAMPLES[] = {ZY_FRAME_SAMPLES};
#define FRAME_SAMPLE_COUNT (sizeof FRAME_SAMPLES / sizeof FRAME_SAMPLES[0])

/* The twenty entity records the frame loop drives, as one range: `smoke.py` compares it against the
 * same range of the original's RAM, with the sprite pointers rebased (they are absolute on both
 * sides and the two sides load at different addresses). */
#define ENTITY_TABLE_BYTES (ENTITY_SLOTS * ENTITY_STRIDE)

static uint32_t g_frame_dump_bytes;

/* "FRAME12.BIN" is the longest name this makes: 8.3, uppercase, so a GEMDOS drive cannot rename it.
 * The index is 1-based and formatted by hand — there is no printf in a freestanding build — and it
 * handles TWO digits, which the assertion below is what keeps true. */
#define SAMPLE_NAME_BYTES 12u          /* "FRAME" + two digits + ".BIN" + the terminator */
#define SAMPLE_NAME_MAX_INDEX 99u      /* ...and what two digits can spell */

static void sample_file_name(char *out, const char *stem, unsigned index) {
    while (*stem)
        *out++ = *stem++;
    if (index >= 10u)
        *out++ = (char)('0' + index / 10u);
    *out++ = (char)('0' + index % 10u);
    *out++ = '.';
    *out++ = 'B';
    *out++ = 'I';
    *out++ = 'N';
    *out = '\0';
}

/* A hundredth sample would write a third digit past the end of `name` and spell a wrong one on the
 * way — the buffer has no slack at all, by design, since it is an 8.3 name. */
_Static_assert(FRAME_SAMPLE_COUNT <= SAMPLE_NAME_MAX_INDEX,
               "sample_file_name spells two digits into an 8.3 name");

static void capture_frame_sample(uint32_t frame) {
    char name[SAMPLE_NAME_BYTES];

    for (unsigned sample = 0; sample < FRAME_SAMPLE_COUNT; sample++) {
        /* THE PENS GO OUT AS SIXTEEN WORDS, not as the record's sixteen longwords: the other side of
         * this comparison is `savebin $ff8240 32`, the colour block as the shifter holds it, and a
         * dump that widened each pen would be comparing two different things. */
        uint16_t pens[PALETTE_PENS];
        long written;

        if (FRAME_SAMPLES[sample] != frame)
            continue;
        sample_file_name(name, "FRAME", sample + 1u);
        written = write_file(name, zy_image_base + be32(zy_image_base + A_screen_front),
                             (long)SCREEN_BYTES);
        if (written > 0)
            g_frame_dump_bytes += (uint32_t)written;
        for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
            pens[pen] = *(volatile uint16_t *)shifter_pen_register(pen);
        sample_file_name(name, "PAL", sample + 1u);
        written = write_file(name, pens, (long)sizeof pens);
        if (written > 0)
            g_frame_dump_bytes += (uint32_t)written;
        sample_file_name(name, "ENT", sample + 1u);
        written = write_file(name, zy_image_base + A_entity_table, (long)ENTITY_TABLE_BYTES);
        if (written > 0)
            g_frame_dump_bytes += (uint32_t)written;
    }
}

/* ------------------------------------------------------------------------------------------------
 * The four `$fffa21` read-back spins, which are the ONE place this shim carries instructions of the
 * program rather than composing them.
 *
 * `../STATUS.md`'s "Not reconstructed" table has them as its only remaining KIT row. Each is ten
 * bytes — `move.b #n,$fffa21` / `cmpi.b #n,$fffa21` / `bne` back to the store — and the differential
 * cannot run them: the read is of a register the run itself wrote two instructions earlier, which
 * the kit's seeded READ model declares as what the chip held on ENTRY and therefore refuses as
 * stale. So each slice STOPS on the store and the next begins after the spin, and this is the ten
 * bytes in between, done for real on the real register.
 *
 * THE SLICE HAS ALREADY MADE THE FIRST STORE, which is why this reads before it writes: control
 * arrives at the `cmpi`, not at the `move`. The loop is the original's exactly — read, and on a
 * mismatch store again.
 *
 * WHY THE SPIN IS NOT ONE READ, MEASURED: `mfp_settle_restores` comes back at 244 over a run, not
 * at 0. Two of the four spins run with Timer B ALREADY STARTED (`move.b #$8,$fffa1b` at 0x10638 and
 * 0x12b14 precede the 0xc8 and 0x02 spins), and on the MC68901 a running timer's data register
 * reads the live DOWN-COUNTER while a write to it updates only the reload value — so the compare
 * succeeds on the pass that happens to catch the counter at its reload point, and re-stores until
 * then. That is the original's own behaviour and the reason it spins at all; the number is a fact
 * about the MFP and about how many passes the catch took, not a fault count.
 *
 * IT IS UNBOUNDED, exactly as the original's is, and the bound is the emulator's `--run-vbls`. A
 * Timer B whose data register never reads back the period at all hangs here with no record written,
 * which is the same shape — and the same evidence — as every other wait in this build.
 *
 * THE SURFACE IS THE HARDWARE-STATE VECTOR: `$fffa21` is Timer B's data register, the count of
 * scanlines between raster interrupts, and this is the one place in the build that writes it from
 * outside a verified slice.
 * --------------------------------------------------------------------------------------------- */
static void mfp_settle_timer_b_data(uint8_t period) {
    while (hw_read8(HW_MFP_TIMER_B_DATA) != period) {
        hw_write8(HW_MFP_TIMER_B_DATA, period);
        g_mfp_settle_restores++;
    }
}

/* ------------------------------------------------------------------------------------------------
 * `title_attract_loop` @ 0x12ac2..0x12c74 — the `bsr` at 0x10520, in four slices and two spins.
 *
 * It returns when the player has chosen: key '1', key '2' or the fire button, with `A_player_count`
 * left holding what they chose. Every one of those three is a byte only `ikbd_acia_isr` writes, so
 * this is where a real keyboard and a real joystick first matter.
 * --------------------------------------------------------------------------------------------- */
static void title_attract_loop(void) {
    g_phase = PHASE_ATTRACT;
    g_attract_passes++;
    attract_program_timer_b(zy_image_base);                          /* 0x12ac2 */
    mfp_settle_timer_b_data(MFP_TIMER_B_PERIOD_ATTRACT_SETUP);       /* 0x12b0a */
    attract_program_rasterbar_timer(zy_image_base);                  /* 0x12b14 */
    mfp_settle_timer_b_data(MFP_TIMER_B_PERIOD_ATTRACT_BARS);        /* 0x12b48 */
    attract_build_colour_bars(zy_image_base);                        /* 0x12b52 */
    attract_wait_for_start(zy_image_base);                           /* 0x12bb4..0x12c74 */
}

/* ------------------------------------------------------------------------------------------------
 * The section chain and the frame loop — 0x10814 through 0x1296e, and the four addresses the frame
 * loop's last stage branches back to.
 *
 * THE THREE STEPS ARE THE ORIGINAL'S THREE `bra` TARGETS, and nothing else about the shape is this
 * file's: 0x10814 falls into 0x1083a, whose gate either falls into the asset load or branches to
 * 0x10b6e, which runs on into 0x10c4e, 0x10d96 and the loop head. `FRAME_EXIT_*` names which of the
 * five the last stage left through, and the switch below is that `bra` written out.
 * --------------------------------------------------------------------------------------------- */
enum section_step {
    SECTION_STEP_ADVANCE = 0,   /* 0x10814 — the section is over, take the next one */
    SECTION_STEP_RELOAD,        /* 0x1083a — re-ask whether this section's assets are in RAM */
    SECTION_STEP_RESTART        /* 0x10b6e — the per-life reset, assets untouched */
};

/* Returns 1 when the game ended at the title (FRAME_EXIT_TITLE, 0x10500) and the outer loop should
 * go round again; 0 when the run is over — the headless build's frame budget spent, or an interrupt
 * named a handler the dispatch table does not know. */
static int play_one_game(void) {
    enum section_step step = SECTION_STEP_ADVANCE;

    for (;;) {
        frame_exit exit;

        g_phase = PHASE_SECTION_START;
        g_section_starts++;
        if (step == SECTION_STEP_ADVANCE) {
            section_advance(zy_image_base);                          /* 0x10814 */
            step = SECTION_STEP_RELOAD;
        }
        if (step == SECTION_STEP_RELOAD && section_reload_needed(zy_image_base)) {  /* 0x1083a */
            /* THE M2 NEGATIVE CONTROL IS THIS ONE STEP DROPPED, and nothing else: `build.sh
             * gamefault` leaves out the two `bsr`s at 0x1085a — the player intro screen and the
             * whole-panel repaint — so the game plays into a screen the front end never prepared.
             * Every sampled framebuffer moves and the entity table moves with it; the PENS do not,
             * because no palette is touched, and neither does the exit path nor the program's own
             * record. `smoke.py gamefault` requires exactly that split.
             *
             * A DROPPED COMPOSITION STEP is the defect this milestone is most exposed to: the whole
             * of M2 is calls to verified slices in the original's order, so what can be wrong is
             * the order and the set. It compiles to nothing in the shipped build. */
            if (!ZY_GAME_FAULT)
                section_reload_intro_screens(zy_image_base);         /* 0x1085a */
            section_load_assets(zy_image_base);                      /* 0x10862 */
        }
        section_restart_prologue(zy_image_base);                     /* 0x10b6e */
        section_start_prefill(zy_image_base);                        /* 0x10c4e */
        section_start_tail(zy_image_base);                           /* 0x10d96 — waits for FIRE */

        g_phase = PHASE_PLAYING;
        do {
            uint32_t vbls_at_frame_start = zy_vbl_ticks;

            exit = frame_loop_once(zy_image_base, ZY_CHANCE_INDEX_REGISTER,
                                   ZY_GROUND_SPAWN_Y_REGISTER);
            note_frame_pacing(zy_vbl_ticks - vbls_at_frame_start);
            g_frames_run++;
            if (exit < FRAME_EXIT_COUNT)
                g_frame_exits[exit]++;
            if (exit != FRAME_EXIT_NEXT_FRAME && g_first_life_ended_at == 0)
                g_first_life_ended_at = g_frames_run;
            capture_frame_sample(g_frames_run);
            /* AN UNKNOWN VECTOR STOPS THE RUN, it does not restart it. Returning 1 here would
             * mean "the game ended at the title" to the caller, which would send control back
             * round the outer loop into `title_attract_loop` — overwriting `phase_reached` with
             * ATTRACT and spinning for ever in a wait, so the one record that could say what
             * happened would never be written. */
            if (g_fatal) {
                g_phase = PHASE_HALTED;
                return 0;
            }
            if (g_frames_run >= ZY_GAME_FRAMES) {
                g_phase = PHASE_BUDGET_SPENT;
                return 0;
            }
        } while (exit == FRAME_EXIT_NEXT_FRAME);

        switch (exit) {
        case FRAME_EXIT_ADVANCE_SECTION: step = SECTION_STEP_ADVANCE; break;
        case FRAME_EXIT_RELOAD_SECTION:  step = SECTION_STEP_RELOAD;  break;
        case FRAME_EXIT_RESTART_SECTION: step = SECTION_STEP_RESTART; break;
        case FRAME_EXIT_TITLE:           return 1;
        case FRAME_EXIT_NEXT_FRAME:      break;   /* unreachable: the `do` above loops on it */
        }
    }
}

/* The outer loop of loops — the original's own, entered at 0x10500 and left only by dying.
 *
 * `boot_front_end_prologue` is what the frame loop's TITLE exit comes back to, which is why the
 * attract call sits inside this loop and not before it: the second and every later pass finds
 * `game_initialised` set, rebuilds the panel master and restarts the title tune, and the one after
 * that finds the same. GAME OVER AND THE HIGH SCORES ARE NOT HERE — they happen INSIDE the frame
 * loop's last stage, which calls `game_over_screen` on the last life and comes back with the exit
 * that sends control to 0x10500. */
static void run_the_whole_program(void) {
    for (;;) {
        boot_front_end_prologue(zy_image_base);                      /* 0x10500 */
        title_attract_loop();                                        /* 0x10520 -> 0x12ac2 */

        g_phase = PHASE_FRONT_END_SCREENS;
        boot_stage_frontend_screens(zy_image_base);                  /* 0x10524 */
        boot_program_timer_b(zy_image_base);                         /* 0x105c6 */
        mfp_settle_timer_b_data(MFP_TIMER_B_PERIOD_PLAIN);           /* 0x1062e */
        boot_program_raster_timer(zy_image_base);                    /* 0x10638 */
        mfp_settle_timer_b_data(MFP_TIMER_B_PERIOD_RASTER);          /* 0x1066c */
        boot_enable_interrupts();                                    /* 0x10676 -> bra 0x10792 */
        boot_new_game_records(zy_image_base);                        /* 0x10792 */

        if (!play_one_game())
            return;
    }
}
#endif /* ZY_PHASE == ZY_PHASE_GAME */

/* ================================================================================================
 * The boot, and the hand-back.
 * ============================================================================================= */

/* Give the machine back, in the order that makes each step safe for the next: the vectors first (so
 * nothing of ours is still running), then the chip, then the display.
 *
 * ANYTHING INSTALLED INTO TOS OUTLIVES THE PROCESS. A handler left on $70 keeps being entered out
 * of memory GEMDOS has taken back, and the machine dies about a second after Pterm — invisible
 * while the program runs, which is why smoke.py keeps `--run-vbls` going past the exit and asserts
 * on what the emulator reports rather than stopping at the dump. */
static void hand_the_machine_back(const struct tos_state *tos) {
    uint16_t sr = zy_irq_disable();

    /* SILENCE THE CHIP FIRST, AND INSIDE THE MASK, and the order is the whole of the argument.
     * Every tone and noise bit SET in the mixer is every channel off; the three volumes go to zero
     * as well, because a mixer bit is not what a hardware envelope obeys. That is
     * `sound_reset_psg`'s own pair of steps (../src/sound.c) without its image half — the cores are
     * finished and the image is about to stop being anybody's.
     *
     * Each write is a `move.b reg,$ff8800` / `move.b val,$ff8802` PAIR with a window between the
     * two stores, and there are exactly two writers of that latch: OUR vertical-blank handler until
     * the vector goes back, and TOS's afterwards (its own vertical blank drives the chip for
     * `Dosound` and the floppy's drive-select lines). So an unmasked silence is racy whichever side
     * of the vector restore it sits on — handing the vector back does not remove the other writer,
     * it INTRODUCES it. Masked, and before the restore, there is no other writer at all. */
    psg_port_write(PSG_REG_MIXER, PSG_MIXER_ALL_OFF);
    for (unsigned voice = 0; voice < PSG_VOLUME_REGISTERS; voice++)
        psg_port_write(PSG_REG_VOLUME_A + voice, 0);

    write_vector(A_vector_vbl, tos->vbl_vector);
    write_vector(A_vector_timer_b, tos->timer_b_vector);
    write_vector(A_vector_acia, tos->acia_vector);
    /* AND THE MFP BACK THE WAY IT WAS FOUND, which the three vectors alone do not do. The game
     * stops and restarts Timer B and rewrites both interrupt-enable registers, and leaving a
     * started Timer B behind means TOS taking a raster interrupt through a handler that no longer
     * exists.
     *
     * ALL FOUR REGISTERS GO BACK, INCLUDING THE B PAIR, and the reason is that the thing which
     * preserves TOS's bits in them today is zynaps_backend.c's TEMPORARY bridge — not the cores,
     * which still spell `hw_write8(HW_MFP_IERB, 1u << 6)`. The bridge's own header tells the
     * orchestrator to delete it when the cores learn `hw_bset8`, and a hand-back that relied on it
     * would quietly stop restoring Timer C, TOS's 200 Hz clock and the floppy's motor timeout, on
     * the commit that removed it. Restoring what was read at entry depends on nothing. */
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_STOPPED);
    hw_write8(HW_MFP_IERA, tos->mfp_iera);
    hw_write8(HW_MFP_IMRA, tos->mfp_imra);
    hw_write8(HW_MFP_IERB, tos->mfp_ierb);
    hw_write8(HW_MFP_IMRB, tos->mfp_imrb);
    zy_irq_restore(sr);

    /* Only Setscreen puts `_v_bas_ad` and `sshiftmd` back, which the direct pokes never touched;
     * TOS reads both from its own vertical blank and its own line A. It also resets the palette, so
     * the pens go back AFTER it and not before. */
    Setscreen((void *)(uintptr_t)tos->logbase, (void *)(uintptr_t)tos->physbase, tos->rez);
    write_pens(tos->pens);
}

/* THE PROGRAM'S OWN ACCOUNT OF THE RUN, and it is the only surface a headless game has for most of
 * what it did. Everything here is a number the machine cannot be asked for afterwards: which phase
 * was reached, which handler each interrupt entry dispatched to and how often, what the frame loop
 * did and where it left, how many hardware stores landed on each register, and what the player's
 * state was when the budget ran out.
 *
 * In a title build every M2 field below is 0 and stays 0, which is what says the fork was not
 * taken — `smoke.py title` asserts exactly that rather than skipping the fields. */
static void record_the_run(void) {
    g_record[REC_ACIA_TICKS] = zy_acia_ticks;
    for (unsigned slot = 0; slot < VBL_HANDLER_SLOTS; slot++)
        g_record[REC_VBL_DISPATCHES + slot] = VBL_HANDLERS[slot].entries;
    for (unsigned slot = 0; slot < TIMER_B_HANDLER_SLOTS; slot++)
        g_record[REC_TIMER_B_DISPATCHES + slot] = TIMER_B_HANDLERS[slot].entries;
    g_record[REC_ACIA_DISPATCHES] = ACIA_HANDLERS[0].entries;
    g_record[REC_UNKNOWN_VECTOR_HALTS] = g_fatal;
    g_record[REC_UNKNOWN_VECTOR] = g_fatal_vector;
    g_record[REC_UNKNOWN_VECTOR_HANDLER] = g_fatal_handler;
    g_record[REC_RMW_STORES] = zy_rmw_stores;
    g_record[REC_VIDEO_BASE_OFFSET] = zy_video_base_offset;
    g_record[REC_VIDEO_BASE_PUBLISHED] = zy_video_base_published;
    g_record[REC_VIDEO_BASE_PUBLISHES] = zy_video_base_publishes;
#if ZY_PHASE == ZY_PHASE_GAME
    g_record[REC_PHASE_REACHED] = g_phase;
    g_record[REC_ATTRACT_PASSES] = g_attract_passes;
    g_record[REC_SECTION_STARTS] = g_section_starts;
    g_record[REC_FRAMES_RUN] = g_frames_run;
    for (unsigned exit = 0; exit < FRAME_EXIT_COUNT; exit++)
        g_record[REC_FRAME_EXITS + exit] = g_frame_exits[exit];
    g_record[REC_MFP_SETTLE_RESTORES] = g_mfp_settle_restores;
    g_record[REC_FIRST_LIFE_ENDED_AT] = g_first_life_ended_at;
    for (unsigned slot = 0; slot < PACING_SLOTS; slot++)
        g_record[REC_FRAME_VBLS + slot] = g_frame_vbls[slot];
    g_record[REC_PLAYING_VBLS] = g_playing_vbls;
    g_record[REC_PLAYER_COUNT] = zy_image_base[A_player_count];
    g_record[REC_LEVEL_SECTION] = zy_image_base[A_level_section];
    g_record[REC_LIVES] = zy_image_base[A_lives];
    g_record[REC_SCORE_BCD] = be32(zy_image_base + A_player_score_bcd);
    g_record[REC_FRAME_DUMP_BYTES] = g_frame_dump_bytes;
    g_record[REC_GAME_FAULT] = ZY_GAME_FAULT;
#endif
}

void zynaps_main(void) {
    struct tos_state tos;
    uint32_t anchor_address;

    /* The image's runtime base, rounded up — see the header comment. */
    zy_image_base = (uint8_t *)(((uintptr_t)g_image_store + (IMAGE_ALIGN - 1))
                                & ~(uintptr_t)(IMAGE_ALIGN - 1));

    /* BEFORE ANYTHING ELSE, and before the eight file loads that take real time: tell the smoke
     * where to put its breakpoint. GEMDOS relocated us to wherever the TPA fell, so `zy_anchor`'s
     * address is a run-time fact, and a driver that guessed it would arm a breakpoint on nothing. */
    anchor_address = (uint32_t)(uintptr_t)&zy_anchor;
    write_file(FILE_ANCHOR_BASE, &anchor_address, (long)sizeof anchor_address);

    tos.vbl_vector = read_vector(A_vector_vbl);
    tos.timer_b_vector = read_vector(A_vector_timer_b);
    tos.acia_vector = read_vector(A_vector_acia);
    tos.mfp_iera = hw_read8(HW_MFP_IERA);
    tos.mfp_imra = hw_read8(HW_MFP_IMRA);
    tos.mfp_ierb = hw_read8(HW_MFP_IERB);
    tos.mfp_imrb = hw_read8(HW_MFP_IMRB);
    tos.physbase = (uint32_t)Physbase();
    tos.logbase = (uint32_t)Logbase();
    tos.rez = Getrez();
    read_pens(tos.pens);

    g_record[REC_MAGIC] = ZY_RECORD_MAGIC;
    g_record[REC_FIELDS] = REC_FIELD_COUNT;
    g_record[REC_IMAGE_BASE] = (uint32_t)(uintptr_t)zy_image_base;
    g_record[REC_TOS_VBL_VECTOR] = tos.vbl_vector;
    g_record[REC_TOS_TIMER_B_VECTOR] = tos.timer_b_vector;
    g_record[REC_TOS_ACIA_VECTOR] = tos.acia_vector;
    g_record[REC_FAULT_PEN] = (uint32_t)ZY_FAULT_PEN;
    g_record[REC_SMOKE_VBLS] = ZY_SMOKE_VBLS;
    g_record[REC_ANCHOR_HOLD_VBLS] = ZY_ANCHOR_HOLD_VBLS;
    record_pens(REC_PENS_AT_ENTRY, tos.pens);

    g_record[REC_PROGRAM_STAGED_BYTES] = (uint32_t)stage_program_image();

    /* THE CORES' VECTOR PAGE IS SEEDED FROM THE REAL ONE. `boot_save_vbl_vector` (0x10012) copies
     * `image[0x70]` to `image[0x195d0]`, and on the real machine that low memory IS the vector page
     * — so seeding the image's copy is what makes the slice's output mean anything here. Reading
     * `image[0x195d0]` back after the slice is then a memory-surface check that the slice ran, on a
     * value nothing else in the image holds. */
    wr32(zy_image_base + A_vector_vbl, tos.vbl_vector);

    /* ------------------------------------------------------------------------------------------
     * `_start`, in the original's order, out of the verified slices and nothing else.
     *   0x10000  boot_enter_supervisor        ../src/init.c
     *   0x10010  the Line-A opcode            zynaps_os.s (MODELLED as a no-op off target)
     *   0x10012  boot_save_vbl_vector         ../src/init.c
     *   0x1001c  ikbd_send_cmd($12)           ../src/input.c
     *   0x10024  ikbd_send_cmd($15)           ../src/input.c
     *   0x1002c  boot_load_title_assets       ../src/init.c — through 0x101b9
     * and 0x101ba, where the reconstruction stops, is where this stops.
     * --------------------------------------------------------------------------------------- */
    init_shifter_sink_reset();

    g_record[REC_SUPER_TOKEN] = boot_enter_supervisor();
    zy_line_a_hide_mouse();
    boot_save_vbl_vector(zy_image_base);
    /* Each command is recorded by the RUNNING TOTAL of bytes that reached $fffc02, so the two
     * fields are 1 and 2 rather than a verdict apiece: the core's spin is unbounded now
     * (shim_include/tos.h), so a transmitter that never empties never returns and there is no
     * verdict to publish — the missing STATE.BIN is that finding. What these two say is the thing a
     * returning call could still get wrong, which is whether the byte was actually stored. */
    ikbd_send_cmd(IKBD_CMD_DISABLE_MOUSE);
    g_record[REC_ACIA_BYTES_AFTER_MOUSE_OFF] = zy_acia_bytes_sent;
    ikbd_send_cmd(IKBD_CMD_JOYSTICK_INTERROGATION_MODE);
    g_record[REC_ACIA_BYTES_AFTER_JOYSTICK_MODE] = zy_acia_bytes_sent;
    /* THE BOOT'S OWN CLOCK, and it is here because no host-side instrument can take it. A
     * breakpoint would do the job, but the driver that would arm one learns where GEMDOS put the
     * program by READING A FILE the program writes — and by the time a host poll notices that file,
     * both loaders have already run (measured: the earliest breakpoint anything outside could arm
     * landed after the boot, at vertical blank 1,936). The program is the only thing in the room
     * that knows when it entered its own loaders, so it says so.
     *
     * WHAT THE FOUR MARKS SEPARATE is the boot's two halves: the eight title files and their
     * preshift banks, the fourteen gameplay files and theirs, and whatever came before either.
     * That is README.md's Unpinned 25 asked as a number a run answers rather than a gap somebody
     * has to go and measure, and it is what says whether the boot is GEMDOS reading files or this
     * build's C building banks. The last two stay 0 in a title build, which does not load them.
     *
     * EACH LOADER IS BRACKETED BY ITS OWN PAIR, and the second pair does not start where the first
     * one ended. A draft reused the title loader's end as the gameplay span's start, which billed
     * everything between the two calls — six record reads, the masked window that installs both
     * vectors, `publish_screen_base` and `inject_pen_fault` — to `boot_load_gameplay_assets`. It
     * was right by luck, all of it being far under one 5 ms tick, and would have drifted silently
     * the moment anything grew in between; an instrument for a question about WHERE the time goes
     * is the one thing that must not do that. */
    g_record[REC_TICKS_AT_TITLE_ASSETS] = read_hz_200();
    boot_load_title_assets(zy_image_base);
    g_record[REC_TICKS_AFTER_TITLE_ASSETS] = read_hz_200();

    g_record[REC_IMAGE_SAVED_VBL_VECTOR] = be32(zy_image_base + A_saved_tos_vbl_vector);
    g_record[REC_IMAGE_SCREEN_BACK] = be32(zy_image_base + A_screen_back);
    g_record[REC_IMAGE_SCREEN_FRONT] = be32(zy_image_base + A_screen_front);
    g_record[REC_SHIFTER_MODE_WRITES] = zy_shifter_mode_writes;
    g_record[REC_SHIFTER_MODE_MASK] = init_shifter_mode_mask_written();
    g_record[REC_PALETTE_LONG_WRITES] = zy_palette_long_writes;

    /* ------------------------------------------------------------------------------------------
     * The machine changes hands here. The boot's own order is resolution (0x10056), the two
     * exception vectors (0x10062/0x1006c, bracketed by the original's own `move.w #$27xx,sr`), the
     * screen base (0x10080) and the palette (0x10084) — and three of those four are now made by the
     * CORES, inside the slice above, through the real stores zynaps_backend.c supplies. What is left
     * here is the vector install, the screen base the cores can only publish as an image offset,
     * and (in the control build only) the injected pen fault.
     *
     * THE VECTORS GO IN AFTER THE SLICE AND THE ORIGINAL PUTS THEM IN DURING IT, and that is a
     * deliberate deviation with a cost worth stating. The original is ticking its sound driver from
     * 0x10076 — through all eight file loads — while this build's driver does not start until the
     * loads are done. Two reasons: the slice is one C call and has no seam in the middle, and
     * (the load-bearing one) every GEMDOS trap this build makes would otherwise run with TOS's
     * vertical-blank handler displaced, which is the shape of docs/on-target-execution.md class 11.
     *
     * THAT SECOND REASON IS M1'S AND M2 SPENDS IT, which is worth saying here rather than only in
     * the README: the game build opens fourteen more files in `boot_load_gameplay_assets`, every
     * section's assets after that, and three dumps per sampled frame — all with TOS's vertical
     * blank displaced. The exposure is taken deliberately, because the ORIGINAL takes it (its own
     * vector goes in at 0x10062 and it opens fourteen more files afterwards) and the original
     * works; what makes it a measurement rather than a hope is the GEMDOS ledger, which shows every
     * one of those opens completing. What the deviation still buys is the M1 build, where the risk
     * really is zero. What it costs is the tune's PHASE: at the anchor this build's driver has ticked
     * ZY_SMOKE_VBLS times and the original's has ticked however long its loads took. That is
     * precisely why smoke.py's timeline arm compares the register stream's SHAPE, cut on the
     * driver's own descending 10..0 flush, and not vblank numbers.
     * --------------------------------------------------------------------------------------- */
    /* THE INSTALL AND THE PUBLISHES ARE ONE CRITICAL SECTION, which is one instruction more than
     * the original's own bracket. The original masks around the vector stores (`move.w #$2700,sr`
     * at 0x1005e, `#$2300` at 0x10076) for the obvious reason: a vertical blank between them would
     * enter a handler through a vector whose other half still points at TOS.
     *
     * Extending it over the stores below is this build's, and what it protects is the COUNT. Once
     * the vertical-blank vector is ours, `sound_tick` runs between any two instructions here and
     * every one of its chip writes goes through the same `zy_hw_writes++` — so an unmasked publish
     * makes the count depend on whether GCC keeps compiling that increment to one `addq.l` (it does
     * today, checked in the disassembly) rather than to a load/add/store the interrupt could split.
     * smoke.py asserts the count exactly, so an intermittent red caused by codegen rather than by a
     * change is precisely what must not be possible.
     *
     * It costs about three microseconds of masked time, once, during the boot. */
    {
        uint16_t sr = zy_irq_disable();

        write_vector(A_vector_vbl, (uint32_t)(uintptr_t)&zy_vbl_entry);
        write_vector(A_vector_timer_b, (uint32_t)(uintptr_t)&zy_timer_b_entry);
        g_record[REC_PUBLISHED_SCREEN_BASE] = publish_screen_base();
        inject_pen_fault();
        zy_irq_restore(sr);
    }

#if ZY_PHASE == ZY_PHASE_GAME
    /* ---- M2: the rest of the boot, and then the whole program -------------------------------
     *   0x101ba  boot_load_gameplay_assets   ../src/init.c — fourteen files and the banks
     *   0x104c8  boot_install_ikbd_isr       ../src/init.c — image[$118] = 0x14456
     *   0x10500  the loop of loops           run_the_whole_program above
     *
     * THE REAL ACIA VECTOR GOES IN WHERE THE PROGRAM'S DOES, immediately after the slice that
     * stores the image's — the same rule as the pair above, so the window in which TOS still owns
     * the keyboard is the original's window (0x10062 to 0x104e2) and not a shorter or longer one. */
    g_phase = PHASE_TITLE_ASSETS;
    g_record[REC_TICKS_AT_GAMEPLAY_ASSETS] = read_hz_200();
    boot_load_gameplay_assets(zy_image_base);
    g_record[REC_TICKS_AFTER_GAMEPLAY_ASSETS] = read_hz_200();
    boot_install_ikbd_isr(zy_image_base);
    {
        uint16_t sr = zy_irq_disable();

        write_vector(A_vector_acia, (uint32_t)(uintptr_t)&zy_acia_entry);
        zy_irq_restore(sr);
    }
    g_phase = PHASE_GAMEPLAY_ASSETS;

    run_the_whole_program();
    zy_anchor();
#else
    /* ---- M1: the title screen runs, with its music -------------------------------------------
     * UNBOUNDED ON PURPOSE, and the bound is the emulator's. If the vertical blank never arrives
     * this spins for ever; `smoke.py` runs Hatari under `--run-vbls`, so the machine stops anyway
     * and the missing STATE.BIN is the finding. A counter here could not tell "no interrupt" from
     * "a slow host" without a second clock, and there is no second clock in M1. */
    while (zy_vbl_ticks < ZY_SMOKE_VBLS)
        ;
    zy_anchor();
#endif

    g_record[REC_PHYSBASE_AT_ANCHOR] = (uint32_t)Physbase();
    g_record[REC_RAW_VIDEO_BASE_AT_ANCHOR] = read_raw_video_base();
    g_record[REC_REZ_AT_ANCHOR] = read_resolution();
    g_record[REC_VBL_TICKS_AT_ANCHOR] = zy_vbl_ticks;
    g_record[REC_TIMER_B_TICKS_AT_ANCHOR] = zy_timer_b_ticks;

    /* THE INTERRUPT'S OWN COUNTERS ARE LATCHED TOGETHER, UNDER THE MASK, and the reason is that
     * smoke.py compares them by an EXACT equality: `hw_writes` must be `2 x psg_writes` plus a
     * fixed number of stores the cores and the shim make. Both operands are ticked by the same
     * interrupt — `zy_vbl_tick` runs `sound_tick`, whose per-frame flush pushes eleven PSG
     * registers through `psg_port_write`, which is twenty-two `hw_write8`s and eleven
     * `zy_psg_writes++` — so a vertical blank landing BETWEEN two of these reads latches one
     * operand from before the flush and the other from after, and the equality fails by exactly
     * twenty-two. That is an intermittent red caused by interrupt timing rather than by a change,
     * which is the thing this build's one other critical section exists to make impossible.
     *
     * It costs a handful of microseconds, once, at the anchor. The file counters below are not in
     * here because nothing ticks them from an interrupt — `load_file` runs on the main line and the
     * boot slice has long since returned. */
    {
        uint16_t sr = zy_irq_disable();

        g_record[REC_PSG_WRITES] = zy_psg_writes;
        g_record[REC_PSG_REFUSED] = zy_psg_refused;
        g_record[REC_HW_WRITES] = zy_hw_writes;
        zy_irq_restore(sr);
    }

    g_record[REC_FILE_OPENS] = zy_file_opens;
    g_record[REC_FILE_OPEN_FAILURES] = zy_file_open_failures;
    g_record[REC_FILE_REFUSALS] = zy_file_refusals;
    {
        uint32_t pens[PALETTE_PENS];

        read_pens(pens);
        record_pens(REC_PENS_AT_ANCHOR, pens);
    }
    record_the_run();

    /* ---- and hands the machine back ---------------------------------------------------------- */
    hand_the_machine_back(&tos);

    g_record[REC_VBL_VECTOR_AFTER] = read_vector(A_vector_vbl);
    g_record[REC_TIMER_B_VECTOR_AFTER] = read_vector(A_vector_timer_b);
    g_record[REC_ACIA_VECTOR_AFTER] = read_vector(A_vector_acia);
    g_record[REC_PHYSBASE_AFTER] = (uint32_t)Physbase();
    g_record[REC_REZ_AFTER] = read_resolution();
    {
        uint32_t pens[PALETTE_PENS];

        read_pens(pens);
        record_pens(REC_PENS_AFTER, pens);
    }

    /* The picture the shifter was displaying, byte for byte, out of the buffer the CORE named.
     * Dumped after the hand-back on purpose: the framebuffer is in this program's own .bss and
     * nothing TOS did to the display touched it, so the bytes are the same — and no GEMDOS call has
     * then run while TOS's vertical-blank handler was displaced. */
    g_record[REC_SCREEN_BYTES_WRITTEN] =
        (uint32_t)write_file(FILE_SCREEN_DUMP, zy_image_base + be32(zy_image_base + A_screen_front),
                             (long)SCREEN_BYTES);

    /* TOS'S 200 Hz CLOCK, ONE LAST TIME, AND IT IS A CHECK RATHER THAN A COST. Timer C drives
     * `$4ba` and lives in MFP interrupt-enable B beside the channel `boot_enable_interrupts` turns
     * on; the whole reason the cores spell that store `hw_bset8` instead of `hw_write8` is that a
     * plain `move.b #$40,$fffa09` would DISABLE Timer C along with every other channel — taking
     * TOS's clock and the floppy's motor timeout with it. Off target the kit's ledger records that
     * the store happened and, by its own header's admission, CANNOT hold which bits it preserved.
     * This is the surface that can: if the boot clobbered Timer C, `$4ba` stops advancing and this
     * mark comes back equal to the boot's. `smoke.py` compares the two. */
    g_record[REC_TICKS_AT_TEARDOWN] = read_hz_200();

    g_record[REC_TAIL] = ZY_RECORD_TAIL;
    write_file(FILE_STATE_RECORD, g_record, (long)sizeof g_record);

    zy_leave_supervisor(zy_saved_ssp);
}
