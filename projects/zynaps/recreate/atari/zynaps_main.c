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

#include "init.h"
#include "input.h"
#include "irq.h"
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

#pragma GCC diagnostic pop

/* The shifter, in the bus form a C pointer needs. Every address here is a CORE header's constant
 * put through `HW_BUS` — include/video.h owns the colour block and the two video-base bytes,
 * include/init.h owns the resolution byte — so this file spells no hardware address of its own. */
#define HW_SHIFTER_RESOLUTION HW_BUS(HW_SHIFTER_MODE)
#define HW_SHIFTER_BASE_HIGH  HW_BUS(HW_SCREEN_BASE_HIGH)  /* address bits 23-16 */
#define HW_SHIFTER_BASE_MID   HW_BUS(HW_SCREEN_BASE_MID)   /* ...and 15-8; an STF has no low byte */
#define SHIFTER_PEN_MASK 0x777u   /* three bits a gun; a CPU read returns the unused fourth as noise */
#define SHIFTER_RESOLUTION_MASK 0x03u  /* $ff8260 bits 0-1; the rest read back as noise too */

/* Where the shifter's base register takes its two bytes from, as shifts of the address. */
#define VIDEO_BASE_HIGH_SHIFT 16
#define VIDEO_BASE_MID_SHIFT   8

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

/* The aligned base. Read by the interrupt entries as well as the main line, hence not a local. */
static uint8_t *g_image;

/* Written from zynaps_os.s (see zynaps_target.h), read by the hand-back. */
void *zy_saved_ssp;

volatile uint32_t zy_vbl_ticks;
volatile uint32_t zy_timer_b_ticks;

/* ================================================================================================
 * The interrupt entries' C halves. zynaps_os.s supplies the `movem` pair and the `rte`.
 * ============================================================================================= */

/* `vbl_isr` @ 0x10776 — the ONE handler in ../src/irq.c with no hardware store at all, and so the
 * only one the differential holds end to end (../STATUS.md's irq section). It clears the frame's
 * sync flag and runs `sound_tick`, whose `flush_shadow` reaches the YM2149 through
 * `psg_port_write`. That call is what makes the title music audible here.
 *
 * The count is bumped BEFORE the handler runs, so a spin that sees N has had N handler entries.
 * Nothing in M1 samples this count and an image word TOGETHER, so the sibling project's skew
 * problem — which needed a masked critical section around the pair — does not arise here; a later
 * milestone that compares the reconstruction's own vblank counter against this one will meet it. */
void zy_vbl_tick(void) {
    zy_vbl_ticks++;
    vbl_isr(g_image);
}

/* `timer_b_isr` @ 0x10782. Installed because the boot installs it (0x1006c), and NOT EXPECTED TO
 * FIRE: nothing in M1 programs an MFP timer and TOS leaves Timer B stopped on an ST. The count is
 * in the record so that "it never fired" is a number rather than a belief — and if it ever does,
 * `timer_b_isr`'s own `mfp_ack_timer_b` is there to acknowledge it. */
void zy_timer_b_tick(void) {
    zy_timer_b_ticks++;
    timer_b_isr(g_image);
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
    REC_PSG_WRITES, REC_PSG_REFUSED, REC_HW_WRITES,
    REC_FILE_OPENS, REC_FILE_OPEN_FAILURES, REC_FILE_REFUSALS,
    REC_FAULT_PEN, REC_SMOKE_VBLS, REC_ANCHOR_HOLD_VBLS, REC_SCREEN_BYTES_WRITTEN,
    REC_PENS_AT_ENTRY,  REC_PENS_AT_ENTRY_END  = REC_PENS_AT_ENTRY  + PALETTE_PENS - 1,
    REC_PENS_AT_ANCHOR, REC_PENS_AT_ANCHOR_END = REC_PENS_AT_ANCHOR + PALETTE_PENS - 1,
    REC_VBL_VECTOR_AFTER, REC_TIMER_B_VECTOR_AFTER, REC_PHYSBASE_AFTER, REC_REZ_AFTER,
    REC_PENS_AFTER,     REC_PENS_AFTER_END     = REC_PENS_AFTER     + PALETTE_PENS - 1,
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
 * would happily write PROGRAM_BYTES at `g_image + ZY_LOAD_BASE` past the end of a too-small array,
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
    read = Fread((short)handle, PROGRAM_BYTES, g_image + ZY_LOAD_BASE);
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
 * publish the buffer just drawn into.
 *
 * THE CORE ALREADY MADE THIS STORE AND IT WAS THE WRONG ADDRESS, which is the one seam a relocated
 * image cannot close from inside. `screen_flip_buffers` publishes two bytes of an IMAGE OFFSET
 * (0x70300) — right in the differential's world, where the image IS the machine's memory and starts
 * at 0, and right on the original, which runs at the base its framebuffers are absolute against.
 * This build's image is a .bss array at `g_image`, so the shifter needs `image + 0x70300`, and the
 * core has no way to know that. It stores the offset; this re-stores the machine address after the
 * slice, and `raw_video_base_at_anchor` reads the register back to say which one won.
 *
 * WHAT IT COSTS is one transient: between the core's store inside the slice and this one after it,
 * the shifter is pointed at $0703xx and displays whatever is there while the remaining seven files
 * load. Nothing this smoke photographs can see it (every shot is at the anchor, seconds later) and
 * README.md's unpinned list carries it as the residual it is — with the note that M2's frame loop,
 * which flips every frame, needs a real answer rather than a republish.
 *
 * The pointer read back is the CORE's output: the swap is ordinary diffable memory that
 * ../STATUS.md's video row holds, and smoke.py compares both framebuffer words in the record
 * against the two addresses `boot_load_title_assets` hard-codes, swapped. The one thing added here
 * is `+ image base`, and Physbase reads that back. */
static uint32_t publish_screen_base(void) {
    uint32_t front = be32(g_image + A_screen_front);
    uint32_t base = (uint32_t)(uintptr_t)g_image + front;

    hw_write8(HW_SHIFTER_BASE_MID, (uint8_t)(base >> VIDEO_BASE_MID_SHIFT));
    hw_write8(HW_SHIFTER_BASE_HIGH, (uint8_t)(base >> VIDEO_BASE_HIGH_SHIFT));
    return base;
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
    zy_irq_restore(sr);

    /* Only Setscreen puts `_v_bas_ad` and `sshiftmd` back, which the direct pokes never touched;
     * TOS reads both from its own vertical blank and its own line A. It also resets the palette, so
     * the pens go back AFTER it and not before. */
    Setscreen((void *)(uintptr_t)tos->logbase, (void *)(uintptr_t)tos->physbase, tos->rez);
    write_pens(tos->pens);
}

void zynaps_main(void) {
    struct tos_state tos;
    uint32_t anchor_address;

    /* The image's runtime base, rounded up — see the header comment. */
    g_image = (uint8_t *)(((uintptr_t)g_image_store + (IMAGE_ALIGN - 1))
                          & ~(uintptr_t)(IMAGE_ALIGN - 1));

    /* BEFORE ANYTHING ELSE, and before the eight file loads that take real time: tell the smoke
     * where to put its breakpoint. GEMDOS relocated us to wherever the TPA fell, so `zy_anchor`'s
     * address is a run-time fact, and a driver that guessed it would arm a breakpoint on nothing. */
    anchor_address = (uint32_t)(uintptr_t)&zy_anchor;
    write_file(FILE_ANCHOR_BASE, &anchor_address, (long)sizeof anchor_address);

    tos.vbl_vector = read_vector(A_vector_vbl);
    tos.timer_b_vector = read_vector(A_vector_timer_b);
    tos.physbase = (uint32_t)Physbase();
    tos.logbase = (uint32_t)Logbase();
    tos.rez = Getrez();
    read_pens(tos.pens);

    g_record[REC_MAGIC] = ZY_RECORD_MAGIC;
    g_record[REC_FIELDS] = REC_FIELD_COUNT;
    g_record[REC_IMAGE_BASE] = (uint32_t)(uintptr_t)g_image;
    g_record[REC_TOS_VBL_VECTOR] = tos.vbl_vector;
    g_record[REC_TOS_TIMER_B_VECTOR] = tos.timer_b_vector;
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
    wr32(g_image + A_vector_vbl, tos.vbl_vector);

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
    boot_save_vbl_vector(g_image);
    /* Each command is recorded by the RUNNING TOTAL of bytes that reached $fffc02, so the two
     * fields are 1 and 2 rather than a verdict apiece: the core's spin is unbounded now
     * (shim_include/tos.h), so a transmitter that never empties never returns and there is no
     * verdict to publish — the missing STATE.BIN is that finding. What these two say is the thing a
     * returning call could still get wrong, which is whether the byte was actually stored. */
    ikbd_send_cmd(IKBD_CMD_DISABLE_MOUSE);
    g_record[REC_ACIA_BYTES_AFTER_MOUSE_OFF] = zy_acia_bytes_sent;
    ikbd_send_cmd(IKBD_CMD_JOYSTICK_INTERROGATION_MODE);
    g_record[REC_ACIA_BYTES_AFTER_JOYSTICK_MODE] = zy_acia_bytes_sent;
    boot_load_title_assets(g_image);

    g_record[REC_IMAGE_SAVED_VBL_VECTOR] = be32(g_image + A_saved_tos_vbl_vector);
    g_record[REC_IMAGE_SCREEN_BACK] = be32(g_image + A_screen_back);
    g_record[REC_IMAGE_SCREEN_FRONT] = be32(g_image + A_screen_front);
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
     * As it stands NO file is opened after the install, so that risk is zero rather than argued
     * about. What it costs is the tune's PHASE: at the anchor this build's driver has ticked
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

    /* ---- the title screen runs, with its music -----------------------------------------------
     * UNBOUNDED ON PURPOSE, and the bound is the emulator's. If the vertical blank never arrives
     * this spins for ever; `smoke.py` runs Hatari under `--run-vbls`, so the machine stops anyway
     * and the missing STATE.BIN is the finding. A counter here could not tell "no interrupt" from
     * "a slow host" without a second clock, and there is no second clock in M1. */
    while (zy_vbl_ticks < ZY_SMOKE_VBLS)
        ;
    zy_anchor();

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

    /* ---- and hands the machine back ---------------------------------------------------------- */
    hand_the_machine_back(&tos);

    g_record[REC_VBL_VECTOR_AFTER] = read_vector(A_vector_vbl);
    g_record[REC_TIMER_B_VECTOR_AFTER] = read_vector(A_vector_timer_b);
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
        (uint32_t)write_file(FILE_SCREEN_DUMP, g_image + be32(g_image + A_screen_front),
                             (long)SCREEN_BYTES);

    g_record[REC_TAIL] = ZY_RECORD_TAIL;
    write_file(FILE_STATE_RECORD, g_record, (long)sizeof g_record);

    zy_leave_supervisor(zy_saved_ssp);
}
