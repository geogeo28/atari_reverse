/* bubble_main.c — the shim: the image, the boot, the composition of the verified slices, and the
 * record every check is read out of.
 *
 * WHAT THIS FILE IS ALLOWED TO BE. Every routine it calls in `../src` is verified byte-for-byte
 * against the original 68000 code; nothing here reimplements one. What it adds is the four things
 * a differential harness cannot hold:
 *
 *   1. THE LOOPS. The cores are SLICES — regions entered at their own PC and diffed at a stop-PC —
 *      because nothing in this program's boot chain returns (../include/init.h says why). The slice
 *      boundaries are checkpoints, not semantic breaks, so composing them back into the original's
 *      own loops is this file's first job. `game_top_loop`, `title_menu_loop` and
 *      `game_frame_update` are written here as the control flow the disassembly has, with every
 *      branch naming the `A_*` global the original tests.
 *   2. THE STACK FRAMES. A C reconstruction has no machine stack, so a core whose original does
 *      `link a6,#-n` takes its A6 as an argument and reaches its locals as image bytes. This file
 *      owns the band those frames live in and the arithmetic that derives one from another.
 *   3. THE MACHINE. The vectors, the screen, the palette, the hand-back — and the four XBIOS calls
 *      the cores swallow, which is this build's largest deviation and is argued where it is made.
 *   4. THE RECORD. Every write the shim makes is read back and published in STATE.BIN, which is
 *      what `smoke.py` asserts on. A shim that only wrote would have no surface at all.
 *
 * IT RUNS IN USER MODE. shim_include/tos.h's header comment has the argument: this is a GEM
 * application and its AES and VDI calls are made from the mode TOS expects them from. Supervisor is
 * taken only where the original takes it — around the one byte at $484 — and the three
 * supervisor-only stores the cores make go through the trap #9 gate, which is the original's own
 * mechanism for exactly that problem.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"

/* `blit.h` — the two screens, the tile geometry, SCREEN_BYTES — comes in through `bubble_mfdb.h`,
 * which is where the two headers' spellings of the MFDB's fields are pinned against each other. */
#include "bubble_mfdb.h"
#include "clib.h"        /* CallerAddressRegisters and the trap trampoline's save slots */
#include "frontend.h"    /* the front end's slices, its frames and the palette pointers */
#include "gameplay.h"    /* game_frame_update's slices and the room loop's tests */
#include "globals.h"     /* the memory model: BG_LOAD_BASE, A4_BASE, BG_STACK_TOP */
#include "init.h"        /* the crt0, init_globals and main's three slices */
#include "sound.h"       /* the ISR, its state block and the two low-memory vectors */
#include "voice.h"       /* play_voice_arm, and the LOA entry it answers */

#include "bubble_target.h"
#include "tos.h"

/* ================================================================================================
 * BUILD MODES
 *
 * `title` boots to the drawn menu and stops at an anchor a check can photograph; `play` runs the
 * whole program for a person. The difference is one `#if`, and it is deliberately not a runtime
 * flag: a check judges the binary it ran, and a per-mode .PRG outlives an edit to build.sh.
 * ============================================================================================= */
#define BG_MODE_TITLE 0
#define BG_MODE_PLAY  1

#ifndef BG_MODE
#define BG_MODE BG_MODE_TITLE
#endif

/* How long the anchor holds after the menu is up, in 50 Hz frames. `smoke.py` breaks on
 * `bg_anchor`, waits four vertical blanks and photographs, so the hold has to outlast that by
 * enough for the shutter and the register dumps; the smoke asserts the two numbers against each
 * other rather than trusting this one. */
#ifndef BG_ANCHOR_HOLD_FRAMES
#define BG_ANCHOR_HOLD_FRAMES 100u
#endif

/* ================================================================================================
 * THE IMAGE
 *
 * One `.bss` array, its base rounded up to 256 at run time. WHY THE ROUNDING IS NOT DECORATION:
 * `image + OS_SCREEN_BASE` is handed to XBIOS Setscreen, an STF's video base register has no low
 * byte, and an unaligned address is TRUNCATED — the shifter then displays from up to 255 bytes
 * below where the program draws, which in ST low resolution PERMUTES THE BITPLANES rather than
 * merely sliding the picture (docs/on-target-execution.md class 8). Aligning the buffer inside its
 * section does not help: GEMDOS loads a .PRG at whatever the TPA gives.
 *
 * THE GUARD BAND above the array is 4 KiB of a pattern, because what follows the array in `.bss`
 * is the shim's own state — `bg_saved_ssp`, the record — and a write that lands there tears the
 * program down cleanly with every read-back green. Zero would not do: zero is also what a `memset`
 * overrun leaves.
 * ============================================================================================= */
#define IMAGE_ALIGN       256u
#define IMAGE_GUARD_BYTES 4096u
#define IMAGE_GUARD_FILL  0xa5u

static uint8_t g_image_store[BG_TARGET_IMAGE_BYTES + IMAGE_ALIGN + IMAGE_GUARD_BYTES];

uint8_t *bg_image_base;

/* Written from bubble_os.s before anything else runs. */
uint8_t *bg_basepage;
uint8_t *bg_initial_sp;
uint8_t *bg_kept_top;
uint32_t bg_mshrink_result;

/* The doors' counters, declared in the headers whose doors keep them. */
volatile uint32_t bg_file_opens;
volatile uint32_t bg_file_open_failures;
volatile uint32_t bg_file_refusals;
volatile uint32_t bg_file_write_failures;
volatile uint32_t bg_hw_writes;
uint32_t bg_heap_pointer = BG_HEAP_BASE;
uint32_t bg_malloc_calls;

volatile uint32_t bg_timer_c_ticks;
uint32_t bg_timer_c_chain;

/* ================================================================================================
 * THE FRAME BAND — where the cores' `frame` arguments point
 *
 * `main`'s `link a6,#$0` puts its A6 at the stack pointer it was entered with, and this build puts
 * that at the game's OWN stack top: `crt0_relocate_and_clear` computes it (basepage + text + data +
 * bss + 0x2100, rounded down to a word) and ../include/globals.h names it. Using the original's
 * number rather than an invented one means the frames sit where the original's did, so a dump of
 * this band is comparable with a dump of the original's stack.
 *
 * EVERY OTHER FRAME IS DERIVED, and the arithmetic is ../src/frontend.c's, not restated here:
 * `main`'s A7 is unchanged across both of its calls, so `init_gem_and_screens` and `game_top_loop`
 * both `link` at MAIN_FRAME - CALL_FRAME_COST. Deeper frames the cores compute themselves from the
 * one they are handed.
 *
 * THE DEEPEST WRITE IS `save_hiscores`' `SAVE_FRAME_SLOT`, at TOP_FRAME - 92; the band below is
 * sized for that with room to spare, and the `_Static_assert` is the check rather than this
 * sentence. `[0x2520e, 0x30000)` is free — it is between the program's last byte and the Malloc
 * arena — so the band cannot reach anything.
 */
#define MAIN_FRAME  BG_STACK_TOP
#define TOP_FRAME   (MAIN_FRAME - CALL_FRAME_COST)
#define FRAME_BAND_BYTES 256u

_Static_assert(MAIN_FRAME > BG_PROGRAM_END + FRAME_BAND_BYTES,
               "the frame band would overlap the program's last bytes");
_Static_assert(MAIN_FRAME < BG_HEAP_BASE,
               "the frame band would overlap the Malloc arena");

/* The A1/A2 the cores file in the trap trampoline's three save slots. On the machine those come
 * from the live register file at the moment of the trap; nothing in this program ever reads them
 * back, so what they are does not matter and what matters is that they are STABLE — a value that
 * moved between two runs would move three longwords of the image with it and no surface would say
 * why. These are the differential's own constants (test/abi.py). */
#define CALLER_A1 0x00000000u
#define CALLER_A2 0x00000000u

/* ================================================================================================
 * THE RECORD — STATE.BIN
 *
 * A magic, a flat array of longwords, and a tail written last so a truncated dump is detectable.
 * `smoke.py` names every field by its index; the enum below is that list, and the two files agree
 * by the field COUNT being asserted on both sides rather than by anyone counting.
 * ============================================================================================= */
#define BG_RECORD_MAGIC 0x42474d31u   /* 'BGM1' */
#define BG_RECORD_TAIL  0x444f4e45u   /* 'DONE' */

enum bg_record_field {
    REC_MAGIC,
    REC_IMAGE_BASE,          /* the aligned array base, which is what every offset is against */
    REC_IMAGE_BYTES,
    REC_PROGRAM_BYTES,       /* what the staged read actually delivered */
    REC_A4_BASE,             /* the crt0's own answer — it must equal ../include/globals.h's */
    REC_LOW_RESOLUTION,      /* main_check_resolution's answer: the branch the gate took */
    REC_SCREEN_PHYS,         /* the two screen bases the boot left in the game's own globals */
    REC_SCREEN_BACK,
    REC_PUBLISHED_PHYSBASE,  /* what the shim handed the shifter... */
    REC_READBACK_PHYSBASE,   /* ...and what Physbase answers, which is the alignment check */
    REC_PHASE_REACHED,       /* how far the boot got, for a run that hung */
    REC_FILE_OPENS,
    REC_FILE_OPEN_FAILURES,
    REC_FILE_REFUSALS,
    REC_FILE_WRITE_FAILURES, /* every Fwrite a core made that GEMDOS answered with an error. The
                              * seam opens for READING and cannot see the mode `c_open` asked for
                              * (shim_include/os.h says why), so this is the alarm if a caller ever
                              * starts writing through a handle it opened rather than created */
    REC_SHIM_FILE_OPENS,     /* ...and the shim's OWN file calls, counted apart from the cores' so
                              * that neither count is the sum of two things */
    REC_SHIM_FILE_FAILURES,
    REC_MALLOC_CALLS,        /* how many allocations were asked of the arena... */
    REC_HEAP_POINTER,        /* ...and where its bump ended up */
    REC_HW_WRITES,           /* the MFP vector register, once per sound start and once per stop */
    REC_VDI_CALLS,
    REC_AES_CALLS,
    REC_VDI_RASTER_COPIES,
    REC_TIMER_C_TICKS,       /* 200 Hz, from the moment sound_start installed the handler */
    REC_TIMER_C_CHAIN,       /* TOS's own $114, read off the machine before the install... */
    REC_TIMER_C_SAVED,       /* ...and what the verified installer parked in the image */
    REC_TIMER_C_VECTOR,      /* what the machine's $114 held at the anchor: our entry */
    REC_TRAP9_VECTOR,        /* ...and its $a4: the supervisor gate every PSG access goes through */
    REC_CONTERM_AT_ANCHOR,   /* the real $484 — the key click the boot is supposed to silence */
    REC_ENTRY_RESOLUTION,    /* Getrez at entry: what the hand-back owes the desktop */
    REC_READBACK_LOGBASE,    /* Logbase at the anchor, against the screen the game published */
    REC_VOI_BUFFER_OFFSET,   /* the sample buffer as `os_malloc` answered it: an IMAGE OFFSET... */
    REC_VOI_POINTER_MACHINE, /* ...and the MACHINE address poked into the LOA in its place */
    REC_TPA_LOW,
    REC_TPA_HIGH,
    REC_KEPT_TOP,            /* what `_start`'s Mshrink kept... */
    REC_MSHRINK_RESULT,      /* ...and whether GEMDOS accepted it. See bubble_os.s: the whole VDI
                              * depends on the memory this gives back */
    REC_IMAGE_HEADROOM,      /* what is left between the image's top and the stack */
    REC_GUARD_DIRTY,         /* bytes of the guard band that are no longer the pattern */
    REC_FAULT_PEN,           /* the three negative controls' own arguments: the corrupted colour
                              * register, the image word XORed, and whether the Timer C vector was
                              * left uninstalled. -1 / 0 / 0 in a shipped build. THEY COME THROUGH
                              * THE RECORD and not through a scrape of build.sh, because a per-mode
                              * .PRG outlives an edit to that script and a check must judge the
                              * binary it ran */
    REC_FAULT_IMAGE_WORD,
    REC_FAULT_NO_TIMER_C,
    REC_TAIL,
    REC_FIELDS
};

static uint32_t g_record[REC_FIELDS];

/* How far the boot got. In the record, so a run that hung has still said where — the only evidence
 * an unbounded wait can leave. */
enum bg_phase {
    PHASE_ENTERED,
    PHASE_IMAGE_STAGED,
    PHASE_GLOBALS_INITIALISED,
    PHASE_GEM_OPEN,
    PHASE_BOOT_FILES_LOADED,
    PHASE_VOICE_PLAYED,
    PHASE_PRESENTATION_SHOWN,
    PHASE_SOUND_STARTED,
    PHASE_MENU_DRAWN,
    PHASE_ANCHOR_HELD,
    PHASE_HANDED_BACK
};

static void reached(uint32_t phase) { g_record[REC_PHASE_REACHED] = phase; }

/* ================================================================================================
 * Files the run writes, and the one it reads
 * ============================================================================================= */
#define FILE_PROGRAM_IMAGE "GHOST.IMG"   /* the relocated program, read into image + BG_LOAD_BASE */
#define FILE_ANCHOR_BASE   "BASE.BIN"    /* 4 bytes: where `bg_anchor` landed, for the breakpoint */
#define FILE_SCREEN_DUMP   "SCREEN.BIN"  /* 32000 bytes: the buffer the shifter was displaying */
#define FILE_STATE_RECORD  "STATE.BIN"   /* the record above */

#define GEMDOS_OPEN_READ     0
#define GEMDOS_CREATE_NORMAL 0

/* THE SHIM'S OWN OPENS ARE COUNTED TOO, and in a tally of their own. `shim_include/os.h`'s door
 * counts the CORES' file calls and `smoke.py` predicts that number exactly (six opens, one refused);
 * the four calls this file makes for itself — the staged image in, and the three files the run
 * writes back out — would turn that prediction into the sum of two unrelated things. Counted apart,
 * both stay predictions. A file that failed to open here is why a check downstream found nothing to
 * read, so the failures are counted as well as the calls. */
static uint32_t g_shim_file_opens;
static uint32_t g_shim_file_failures;

static long shim_opened(long handle) {
    g_shim_file_opens++;
    if (handle < 0)
        g_shim_file_failures++;
    return handle;
}

static long write_file(const char *name, const void *data, long bytes) {
    long handle = shim_opened(Fcreate(name, GEMDOS_CREATE_NORMAL));
    long written;

    if (handle < 0)
        return handle;
    written = Fwrite((short)handle, bytes, data);
    Fclose((short)handle);
    return written;
}

/* THE STAGED READ MUST FIT THE IMAGE, and this is the one place both numbers are in scope. GEMDOS
 * would happily write PROGRAM_BYTES past the end of a too-small array, over the record and
 * `bg_saved_ssp`; build.sh measures PROGRAM_BYTES off the staged file, so a bigger binary is
 * exactly how that would arrive. A compile-time refusal costs nothing. */
_Static_assert((uint32_t)BG_LOAD_BASE + (uint32_t)PROGRAM_BYTES <= BG_TARGET_IMAGE_BYTES,
               "the staged program does not fit the image at BG_LOAD_BASE");

/* AND SO MUST THE SCREENS AND THE STAGING AREA, which is the layout's load-bearing claim as a
 * compile-time check rather than as the comment in shim_include/os.h. */
_Static_assert((uint32_t)OS_SCREEN_BASE + SCREEN_BYTES <= BG_TARGET_IMAGE_BYTES,
               "the visible screen runs past the end of the target image");
_Static_assert((uint32_t)OS_SCREEN_BASE >= SCREEN_BYTES + ROOM_BYTES,
               "screen_back and the room staging area are carved below Logbase and would underflow");

/* AND THE ONE NUMBER `shim_include/os.h` SPELLS THAT CLEARANCE AS IS THE SUM OF THESE TWO. That
 * header cannot include `blit.h` — it is a CORE header, and pulling it in would put it in the
 * include closure of every core that says `#include "os.h"` — so it carries `0xe100` as a literal
 * with a comment naming the two constants. This file includes both headers, so the derivation is
 * checked HERE rather than trusted there (CLAUDE.md §5). */
_Static_assert(BG_SCREEN_WORLD_BELOW_LOGBASE == SCREEN_BYTES + ROOM_BYTES,
               "shim_include/os.h's clearance below Logbase is no longer screen_back plus the room "
               "staging area");

static long stage_program_image(void) {
    long handle = shim_opened(Fopen(FILE_PROGRAM_IMAGE, GEMDOS_OPEN_READ));
    long read;

    if (handle < 0)
        return handle;
    read = Fread((short)handle, PROGRAM_BYTES, bg_image_base + BG_LOAD_BASE);
    Fclose((short)handle);
    return read;
}

/* ================================================================================================
 * THE BASEPAGE THE CRT0 READS
 *
 * The staged image is the FILE layout — `[TEXT][DATA][BSS]`, exactly as GEMDOS would have loaded
 * the original — so the verified `crt0_relocate_and_clear` really runs on target and really
 * establishes A4. What it reads is a basepage, and the one GEMDOS gave THIS program describes this
 * program; so one is fabricated for the game, in the image, immediately below its load base, which
 * is where GEMDOS puts a real one.
 *
 * This is `test/test_init.py`'s own fixture shape, and the equivalence it produces is what
 * `test/test_image_model.py` pins: the crt0 run on a file-layout image with a fabricated basepage
 * leaves memory equal to the run-time layout the differential loads. So the target boot and the
 * harness's base image are the same bytes by a proof that already exists.
 * ============================================================================================= */
#define BG_BASEPAGE (BG_LOAD_BASE - BG_BASEPAGE_BYTES)

static void build_basepage(uint8_t *image) {
    const uint32_t text = BG_LOAD_BASE;
    const uint32_t data = text + BG_TEXT_BYTES;
    const uint32_t bss = data + BG_DATA_BYTES;

    wr32(image + BG_BASEPAGE + BASEPAGE_TBASE, text);
    wr32(image + BG_BASEPAGE + BASEPAGE_TLEN, BG_TEXT_BYTES);
    wr32(image + BG_BASEPAGE + BASEPAGE_DBASE, data);
    wr32(image + BG_BASEPAGE + BASEPAGE_DLEN, BG_DATA_BYTES);
    wr32(image + BG_BASEPAGE + BASEPAGE_BBASE, bss);
    wr32(image + BG_BASEPAGE + BASEPAGE_BLEN, BG_BSS_BYTES);
}

/* ================================================================================================
 * THE MACHINE: the screen, the palette and the two vectors
 *
 * THE FOUR XBIOS CALLS THE CORES SWALLOW ARE REISSUED HERE, AND THIS IS THE BUILD'S LARGEST
 * DEVIATION. `xbios_trap_call` (../src/frontend.c) answers Setscreen, Setpalette, Setcolor and
 * Vsync with the model's `return 0` — a no-op inside a verified core with no `os_*` door under it,
 * so no include-path seam can reach them. What this file can do is make the same call at the
 * composition boundary that FOLLOWS the slice which would have made it. The cost is a latency of
 * one slice, and it is stated per call site rather than waved at:
 *
 *   Setscreen  the logical base moves between the visible screen and the work buffer around every
 *              text card and the whole menu. Reissued either side of the slice that moves it, so
 *              the VDI draws where the original's VDI drew.
 *   Setpalette the two picture palettes. Reissued after the slice that loads the picture, so a
 *              freshly shown picture is in the DESKTOP's colours until that slice returns —
 *              seconds, on a floppy, for the presentation.
 *   Setcolor   not reissued at all in this build: both sites are end-of-room animations, which the
 *              title mode never reaches. Recorded as unpinned.
 *   Vsync      not reissued. Its only three sites are inside `menu_attract_slideshow_room`, in the
 *              middle of a slice, so there is nowhere outside it to put them; the attract
 *              slideshow therefore runs at renderer speed. Recorded as unpinned.
 *
 * Closing this properly is a change to the CORES — a kit door for the XBIOS group, verified by the
 * differential — and therefore not a change this directory may make.
 * ============================================================================================= */
/* XBIOS Setscreen's third argument IS A RESOLUTION AND NOT A "leave it alone". 0 is ST LOW; -1 is
 * the code that keeps whatever the machine is already in. The first draft of this file called the 0
 * `SETSCREEN_KEEP_RESOLUTION`, which is what a reader would then have believed at the hand-back —
 * the one call in the file where the machine's own resolution is the thing that must come back.
 *
 * 0 is the FAITHFUL argument at every one of the game's own call sites: `main_check_resolution` has
 * already refused to run anywhere but ST low, so the original's Setscreens set the mode they are in.
 * The hand-back passes the `Getrez` read at entry instead, which is the same 0 on this machine and
 * the right value on one where the program was started from another mode. */
#define SETSCREEN_ST_LOW 0
#define PALETTE_PENS 16u
#define SETCOLOR_READ_ONLY (-1)       /* Setcolor(index, -1) reports a pen without changing it */

static void *machine_screen(uint32_t offset) { return bg_image_base + offset; }

/* Point the shifter at the image, and read the answer back. `Setscreen` takes effect at the next
 * vertical blank, so the read-back needs a `Vsync` in front of it or it reports the old base —
 * and the read-back is the whole alignment check: `Physbase` answers what the register HOLDS, and
 * the register has no low byte, so the two are equal only if what was handed over was aligned. */
static void publish_screen(uint32_t logical, uint32_t physical) {
    Setscreen(machine_screen(logical), machine_screen(physical), SETSCREEN_ST_LOW);
    g_record[REC_PUBLISHED_PHYSBASE] = (uint32_t)(uintptr_t)machine_screen(physical);
    Vsync();
    g_record[REC_READBACK_PHYSBASE] = (uint32_t)Physbase();
}

/* The logical base alone — what the game's own `Setscreen` calls move, always with the same
 * physical base (../notes/frontend.md §5: "Setscreen is only ever called with phys = screen_phys"). */
static void publish_logical_screen(uint32_t logical) {
    Setscreen(machine_screen(logical), machine_screen(be32(bg_image_base + A_screen_phys)),
              SETSCREEN_ST_LOW);
}

/* One of the two 32-byte palette blocks the picture loaders read off the tail of their file. The
 * argument is the ADDRESS OF THE POINTER, because that is how the game holds them. */
static void publish_palette(uint32_t palette_pointer) {
    Setpalette(bg_image_base + be32(bg_image_base + palette_pointer));
}

/* ================================================================================================
 * THE THREE NEGATIVE CONTROLS
 *
 * One fault each, each aimed at a DIFFERENT surface, so that a check reporting green is reporting
 * something. Each is a build-time `-D` and not a runtime flag — a check judges the binary it ran —
 * and each publishes its own argument in the record, so `smoke.py` can refuse to grade a control
 * mode against a .PRG that carries no fault.
 *
 *   BG_FAULT_PEN        one colour register corrupted on its way to the shifter, and nothing else.
 *                       Reds the HARDWARE-STATE VECTOR (the chip's own registers) and the RENDERED
 *                       PIXELS (whose palette-mode PNG carries those sixteen registers), and must
 *                       leave the framebuffer, the record and the trap ledger untouched.
 *   BG_FAULT_IMAGE_WORD one word of the staged program XORed after the crt0 has placed it. Reds the
 *                       MEMORY surface — the displayed framebuffer against the original's — and the
 *                       rendered pixels with it, and leaves the pens alone.
 *   BG_FAULT_NO_TIMER_C the sound engine installed in the image and NOT on the machine's $114.
 *                       Reds the RECORD: no tick ever fires and the vector at the anchor is TOS's.
 *
 * All three compile to nothing in a shipped build, where the `if` is a compile-time constant.
 * ============================================================================================= */
#ifndef BG_FAULT_PEN
#define BG_FAULT_PEN (-1)
#endif
#ifndef BG_FAULT_IMAGE_WORD
#define BG_FAULT_IMAGE_WORD 0
#endif
#ifndef BG_FAULT_NO_TIMER_C
#define BG_FAULT_NO_TIMER_C 0
#endif

/* The controls are TITLE-mode instruments: `play` has no anchor and nothing photographs it, so the
 * injectors would be dead code there and GCC says so. */
#if BG_MODE == BG_MODE_TITLE
/* WHAT THE PEN FAULT XORS, AND WHY IT IS NOT AN INVERSION. The first draft used 0x777, which turned
 * the menu's only ink colour (hardware pen 15, white) black — and a capture with ONE colour is
 * rejected by `check_the_rendered_pixels` before it ever compares the two pictures, so the picture
 * COMPARISON itself was never exercised by the control that was supposed to exercise it. 0x007
 * takes white to yellow: two colours still on the screen, and the comparison runs and fails. */
#define BG_FAULT_PEN_XOR 0x007
#define BG_FAULT_IMAGE_XOR 0x0101   /* one bit in each byte: two menu glyphs move, neither to NUL */

_Static_assert(BG_FAULT_PEN < (int)PALETTE_PENS,
               "the fault names a colour register that does not exist");
_Static_assert((uint32_t)BG_FAULT_IMAGE_WORD + sizeof(uint16_t) <= BG_TARGET_IMAGE_BYTES,
               "the image fault names a word outside the image");

static void inject_pen_fault(void) {
    if (BG_FAULT_PEN < 0)
        return;
    /* XBIOS Setpalette IS DEFERRED — it parks the block's address in TOS's `_colorptr` and TOS's own
     * vertical-blank handler loads the sixteen registers from it at the next blank. So a Setcolor
     * made immediately after one is overwritten a frame later, which is what the first draft of this
     * control did: the pens read back unchanged and the control reported both colour-sensitive
     * surfaces as green under a fault that never reached the chip. The `Vsync` is inside the fault
     * arm rather than in `publish_palette`, so the shipped build's timing is the original's. */
    Vsync();
    (void)Setcolor((short)BG_FAULT_PEN,
                   (short)(Setcolor((short)BG_FAULT_PEN, SETCOLOR_READ_ONLY) ^ BG_FAULT_PEN_XOR));
}

/* AFTER THE CRT0, NOT BEFORE IT. The staged file is `[TEXT][DATA][BSS]` and the crt0 moves the DATA
 * to `A4_BASE`, so a word poked into the file layout would be poked again from the file's copy and
 * the fault would vanish. The address the control names is therefore the RUN-TIME one, which is
 * also the one `../include/frontend.h` gives it a name for. */
static void inject_image_fault(uint8_t *image) {
    if (BG_FAULT_IMAGE_WORD == 0)
        return;
    wr16(image + BG_FAULT_IMAGE_WORD,
         (uint16_t)(be16(image + BG_FAULT_IMAGE_WORD) ^ BG_FAULT_IMAGE_XOR));
}
#endif /* BG_MODE == BG_MODE_TITLE */

static void read_palette(uint16_t *pens) {
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        pens[pen] = (uint16_t)Setcolor((short)pen, SETCOLOR_READ_ONLY);
}

static void write_palette(const uint16_t *pens) {
    for (unsigned pen = 0; pen < PALETTE_PENS; pen++)
        (void)Setcolor((short)pen, (short)pens[pen]);
}

/* ---- the two vectors, and the conterm byte -----------------------------------------------------
 * All three are low memory, all three are supervisor-only, and all three are IMAGE bytes to the
 * cores: `install_sound_vectors` writes image[$114] and image[$a4], `init_gem_and_screens` clears
 * image[$484] inside a real Super bracket, and the ISR rewrites image[$484] every tick. So the shim
 * MIRRORS them, in both directions and at named moments.
 *
 * The Supexec thunks below are how: XBIOS Supexec takes a routine and no arguments, so each one
 * reads a static that the caller set. */
static uint32_t g_supexec_address;
static uint32_t g_supexec_value;

static void supexec_read_long(void) { g_supexec_value = bg_read_long(g_supexec_address); }
static void supexec_write_long(void) { bg_write_long(g_supexec_address, g_supexec_value); }
static void supexec_write_byte(void) { bg_write_byte(g_supexec_address, (uint8_t)g_supexec_value); }

static uint32_t peek_long(uint32_t address) {
    g_supexec_address = address;
    Supexec(supexec_read_long);
    return g_supexec_value;
}

static void poke_long(uint32_t address, uint32_t value) {
    g_supexec_address = address;
    g_supexec_value = value;
    Supexec(supexec_write_long);
}

static void poke_byte(uint32_t address, uint8_t value) {
    g_supexec_address = address;
    g_supexec_value = value;
    Supexec(supexec_write_byte);
}

/* ---- $484, mirrored in both directions, and the ORDER is the whole of whether it means anything
 *
 * `init_gem_and_screens` clears TOS's key-click byte inside a real `Super` bracket — but what it can
 * clear is image[$484], because that is all a core can reach — and the sound ISR rewrites the same
 * image byte every tick. Three moments, in this order:
 *
 *   BEFORE the boot   the machine's byte is read INTO the image, so the core's clear lands on top of
 *                     TOS's real value rather than on a value the shim invented.
 *   AFTER the GEM is open   the image byte is written BACK to the machine. THIS is the poke the
 *                     original makes for real, and the reason the key click actually stops.
 *   EVERY TICK        the ISR's own write is mirrored out — from inside the interrupt, which is
 *                     already supervisor, so `bg_timer_c_tick` stores directly instead of Supexec'ing.
 *
 * The first draft ran the first two the other way round and then poked the machine's byte back onto
 * itself: a no-op that read as a mirror, with `CONTERM_AT_ANCHOR` sitting at TOS's own 7 all the way
 * to the hand-back while every check stayed green.
 *
 * $484 is longword-aligned, so its byte is the TOP byte of the longword at its own address — which
 * is what `bg_read_long` can fetch and a plain byte read cannot be Supexec'd to do. */
#define CONTERM_BYTE_SHIFT 24u
_Static_assert((TOS_CONTERM & 3u) == 0,
               "conterm is no longer longword-aligned, so it is not the top byte of its own longword");

static uint8_t peek_conterm(void) {
    return (uint8_t)(peek_long(TOS_CONTERM) >> CONTERM_BYTE_SHIFT);
}

static void seed_conterm(uint8_t *image) { image[TOS_CONTERM] = peek_conterm(); }

static void mirror_conterm(const uint8_t *image) { poke_byte(TOS_CONTERM, image[TOS_CONTERM]); }

/* The C half of the Timer C entry. The verified ISR is the whole body; the count is the surface —
 * a run whose sound is silent because the vector never took is a run whose tick count is 0, which
 * no screenshot could tell from a run whose music simply has not started. */
void bg_timer_c_tick(void) {
    bg_timer_c_ticks++;
    timer_c_sound_isr(bg_image_base);
    /* The ISR's own $484 write, made for real. An exception handler already runs in supervisor mode,
     * so this is a plain store where `mirror_conterm` needs a Supexec from user code. */
    bg_write_byte(TOS_CONTERM, bg_image_base[TOS_CONTERM]);
}

/* ================================================================================================
 * The anchor. `smoke.py` breaks on THIS function's entry — its runtime address is what BASE.BIN
 * carries — and its action file arms the next-vertical-blank breakpoints that photograph the screen.
 * So the routine's job is to still be here a few frames later.
 *
 * `noinline` is not decoration: inlined, the symbol would have no address to break on and the smoke
 * would report a breakpoint that never fired, which reads like a crash.
 *
 * IT PACES ON `Vsync` AND NOT ON A COUNT. The one clock this build has that is not the sound
 * driver's is the raster, and the hold has to be measured in the same unit the smoke's
 * `b VBL > VBL` breakpoints are.
 * ============================================================================================= */
__attribute__((noinline)) static void bg_anchor(void) {
    for (unsigned frame = 0; frame < BG_ANCHOR_HOLD_FRAMES; frame++)
        Vsync();
}

/* ================================================================================================
 * THE COMPOSITION
 *
 * From here down, every function is the original's own control flow with the verified slices in it.
 * Each carries the address range it composes; the branches name the `A_*` global the disassembly
 * tests, so a reader can check this file against `../out/prg_dis.txt` without reading any C.
 * ============================================================================================= */

/* `title_menu_loop` @ 0x115d6 — the whole front end.
 *
 * The four keys are `../notes/frontend.md`'s table and the four `cmpi.w` at 0x11700, 0x117d6,
 * 0x11928 and 0x11cb2. Everything else is a slice.
 *
 * THE SETSCREEN REISSUES ARE THE DEVIATION NAMED ABOVE. `menu_draw` draws the four menu lines onto
 * the VISIBLE page — its own `Setscreen(phys, phys)` @ 0x11618 is what puts them there — and
 * `menu_read_key_and_fold` puts the logical base back to the work buffer @ 0x116e4. Both are
 * swallowed by the core, so they are made here, either side of the slice.
 */
#define MENU_KEY_GAME     'G'
#define MENU_KEY_PRACTICE 'P'
#define MENU_KEY_DEMO     'D'
#define MENU_KEY_HALL     'H'

#if BG_MODE == BG_MODE_PLAY
static void draw_the_menu(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    publish_logical_screen(be32(image + A_screen_phys));
    menu_draw(image, frame, *live);
    publish_palette(A_dat_palette);
}

static void title_menu_loop(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    publish_logical_screen(be32(image + A_screen_phys));
    title_menu_open(image, frame, live);          /* [0x115d6, 0x116c4) — includes menu_draw */
    publish_palette(A_dat_palette);

    for (;;) {
        int16_t key = menu_read_key_and_fold(image, frame, *live);   /* [0x116c4, 0x11700) */

        publish_logical_screen(be32(image + A_screen_back));
        if (key == MENU_KEY_GAME) {
            publish_logical_screen(be32(image + A_screen_phys));
            menu_ask_player_count(image, frame, *live);              /* [0x11708, 0x11774) */
            while (!menu_read_player_count(image, frame, *live))     /* [0x11774, 0x117cc) */
                ;
            publish_logical_screen(be32(image + A_screen_back));
        } else if (key == MENU_KEY_PRACTICE) {
            publish_logical_screen(be32(image + A_screen_phys));
            menu_ask_practice_level(image, *live);                   /* [0x117de, 0x1183e) */
            menu_read_level_tens(image, *live);                      /* [0x1183e, 0x1186c) */
            menu_read_level_units(image, frame, *live);              /* [0x1186c, 0x1191e) */
            publish_logical_screen(be32(image + A_screen_back));
        } else if (key == MENU_KEY_DEMO) {
            menu_attract_sequence(image, frame, *live);              /* [0x11930, 0x11ae6) */
            menu_attract_slideshow(image, frame, *live);             /* [0x11ae6, 0x11c34) */
            menu_attract_title(image, frame, *live);                 /* [0x11c34, 0x11ca8) */
            publish_palette(A_pre_palette);                          /* the title picture's */
        } else if (key == MENU_KEY_HALL) {
            menu_hall_of_fame(image, frame, *live);                  /* [0x11cba, 0x11d60) */
        }

        /* @ 0x11d60: a non-zero `chose` returns to `game_top_loop`; zero redraws the menu. */
        if ((int16_t)be16(image + frame + MENU_FRAME_CHOSE) != 0)
            return;
        draw_the_menu(image, frame, live);
    }
}

/* `game_frame_update` @ 0x12322 — one frame of the room simulation. Two of its slices ANSWER a
 * branch the original simply falls through, which is what a reconstruction has instead of a
 * condition code: `frame_poll_input` says the key was ^P, and `frame_step_live_bubble` says the
 * bubble died. */
static void game_frame_update(uint8_t *image, uint32_t top_frame, CallerAddressRegisters saved) {
    const uint32_t hud_frame = top_frame - TOP_LOCAL_BYTES - CALL_FRAME_COST - CALL_FRAME_COST;

    frame_advance_bubble_frame(image);                  /* [0x12322, 0x1233a) */
    if (frame_poll_input(image, saved))                 /* [0x1233a, 0x12434) */
        frame_poll_pause(image, saved);                 /* [0x1239e, 0x123de) */
    frame_scale_mouse_to_ghost(image);                  /* [0x12434, 0x124a4) */
    frame_blow_or_recover(image, saved);                /* [0x124a4, 0x1255c) */
    frame_step_facing(image);                           /* [0x1255c, 0x125e6) */
    frame_apply_fans(image);                            /* [0x125e6, 0x126e2) */
    if (frame_step_live_bubble(image))                  /* [0x126e2, 0x1294a) */
        frame_death_sequence(image, hud_frame, saved);  /* [0x1273c, 0x1294a) */
    frame_drift_pulse(image);                           /* [0x1294a, 0x129b0) */
}

/* The rest of `game_top_loop` @ 0x101e6 — one whole game per pass of the outer loop, one turn per
 * pass of the middle one, one frame per pass of the inner one. Every test names the global the
 * disassembly tests and the address it tests it at. */
static void game_play_loop(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    for (;;) {                                           /* @ 0x10dde, unconditional */
        game_new_game(image);                            /* [0x1027e, 0x102b0) */
        title_menu_loop(image, frame - TOP_LOCAL_BYTES - CALL_FRAME_COST, live);
        game_turn_init(image);                           /* [0x102b4, 0x1037a) */

        do {
            game_player_change(image, frame, *live);     /* [0x1037a, 0x105e0) */
            game_room_setup(image, frame, *live);        /* [0x105e0, 0x1078a) */

            /* The room loop is ENTERED AT ITS TEST — `bra.w $108d2` @ 0x1078a. */
            while (be16(image + A_in_room) != 0                             /* @ 0x108d2 */
                   && (int32_t)be32(image + A_lives) > HUD_LIVES_EXHAUSTED) /* @ 0x108d8 */
            {
                game_frame_update(image, frame, *live);      /* jsr @ 0x1078e */
                game_room_frame_tail(image, frame, *live);   /* [0x10792, 0x108d2) */
            }

            if (be16(image + A_level_complete) != 0)         /* @ 0x108e4 */
                game_ending_sequence(image, frame, *live);   /* [0x108ec, 0x10ce0) */
            else
                game_room_exit(image, frame, *live);         /* [0x10af8, 0x10ce0) */

            game_end_of_turn(image);                         /* [0x10ce0, 0x10d34) */
        } while (be16(image + A_p1_playing) != 0             /* @ 0x10d34 */
                 || be16(image + A_p2_playing) != 0);        /* @ 0x10d3c */

        game_over_card(image, frame, *live);                 /* [0x10d44, 0x10dde) */
    }
}
#endif /* BG_MODE == BG_MODE_PLAY */

/* The LOA's sample pointer, translated — the other half of the seam the `jsr` below is one half of.
 *
 * `play_voice_arm` pokes the value of `voi_buffer` into the loaded LOA image at +0x1e, and that
 * value is an IMAGE OFFSET: `os_malloc` answers offsets, because a core indexes a flat image and
 * could not use a machine address. THE LOA IS REAL 68000 CODE HERE and dereferences that longword
 * as an ADDRESS, so left untranslated it reads its samples from wherever the offset lands in the
 * machine's own low memory and the speech is noise — with every check green, because no surface in
 * this build listens. The record carries the offset and the address it became, so the arithmetic is
 * asserted rather than trusted. */
static void translate_the_loa_sample_pointer(uint8_t *image) {
    const uint32_t slot = A_loa_image + LOA_SAMPLE_POINTER_OFFSET;
    const uint32_t offset = be32(image + slot);

    g_record[REC_VOI_BUFFER_OFFSET] = offset;
    g_record[REC_VOI_POINTER_MACHINE] = (uint32_t)(uintptr_t)(bg_image_base + offset);
    wr32(image + slot, g_record[REC_VOI_POINTER_MACHINE]);
}

/* `game_top_loop`'s boot, `[0x101e6, 0x1027e)` — the four slices and the one thing between two of
 * them that no core can be: the `jsr` into GHOST.LOA.
 *
 * THE LOA IS A SECOND PROGRAM. `load_voice_player` reads it into the BSS as data — an `ABSFLAG`
 * .PRG, so it needs no relocation — and `play_voice_arm` pokes the sample pointer into it and
 * ANSWERS the address it would have called. On target that address is real memory holding real
 * 68000 code, so the call is a call. The LOA programs MFP Timer A and busy-waits on a flag its own
 * handler sets, which is why the harness stops the slice at the `jsr` and why this line is the
 * composition's one hard join. */
static void boot_the_program(uint8_t *image, uint32_t frame, CallerAddressRegisters *live) {
    game_top_boot(image, frame, live);                   /* [0x101e6, 0x10232) */
    publish_logical_screen(be32(image + A_screen_back)); /* its swallowed Setscreen @ 0x1022a */
    reached(PHASE_BOOT_FILES_LOADED);

    {   /* @ 0x10232: jsr play_voice */
        uint32_t entry = play_voice_arm(image);          /* [0x13cea, 0x13d26) */

        translate_the_loa_sample_pointer(image);
        ((void (*)(void))(bg_image_base + entry))();
    }
    reached(PHASE_VOICE_PLAYED);

    game_top_boot_tail(image, frame, live);              /* [0x10236, 0x1024e) */
    publish_palette(A_pre_palette);                      /* show_presentation's, one slice late */
    reached(PHASE_PRESENTATION_SHOWN);

    game_top_free_voice_buffer(image);                   /* @ 0x1024e: c_free(voi_buffer) */
    game_top_boot_arm(image, live);                      /* [0x10258, 0x1027e) — sound_start */
}

/* ================================================================================================
 * Sound: the vectors around `game_top_boot_arm`'s `sound_start`
 *
 * `install_sound_vectors` is verified and writes IMAGE bytes. Two things have to happen around it
 * and neither can be inside it:
 *   - the machine's $114 is copied into the image FIRST, so the installer saves the real vector;
 *   - our own entry stub goes on the machine's $114 afterwards, and the chain it `rts`es through is
 *     taken from what the installer saved — the two are asserted equal in the record, so a mismatch
 *     means the installer did not run.
 * $484's own mirror is `seed_conterm`/`mirror_conterm` above and is NOT part of this pair: the byte
 * belongs to `init_gem_and_screens`, which runs long before any of this.
 * ============================================================================================= */
static void seed_the_timer_c_chain(uint8_t *image) {
    wr32(image + TOS_VEC_TIMER_C, peek_long(TOS_VEC_TIMER_C));
}

static void install_the_timer_c_vector(uint8_t *image) {
    bg_timer_c_chain = be32(image + SND_ISR_SAVED_TIMER_C);
    g_record[REC_TIMER_C_SAVED] = bg_timer_c_chain;
#if BG_MODE == BG_MODE_TITLE
    if (BG_FAULT_NO_TIMER_C)      /* the third control: installed in the image, not on the machine */
        return;
#endif
    poke_long(TOS_VEC_TIMER_C, (uint32_t)(uintptr_t)bg_timer_c_entry);
}

/* THE HAND-BACK RUNS THE VERIFIED TEARDOWN AND THEN MIRRORS WHAT IT WROTE.
 *
 * `sound_stop` @ 0x1499c is the routine the game itself calls: it silences all three voices through
 * the PSG doors — real writes to $ff8800/$ff8802 through the trap #9 gate — files the trampoline's
 * three save slots, and calls `remove_sound_vectors`, which restores image[$114] and image[$484] and
 * puts the MFP's vector register back into SOFTWARE end-of-interrupt, which is the mode TOS runs in.
 * Everything it does off-image already goes out through a door; what is left for this file is the
 * two IMAGE bytes that are machine state here.
 *
 * The first draft ran none of it — it poked $114 and $484 from the shim and called no core at all —
 * so the chip kept whatever the last note left in it and the MFP stayed in automatic EOI, which is
 * TOS's business and not this program's.
 *
 * $484 IS DELIBERATELY NOT MIRRORED OUT OF HERE. `remove_sound_vectors` restores image[$484] to the
 * ZERO `init_gem_and_screens` wrote, because the original means the key click to stay off: it stays
 * resident for the life of the machine. This build exits, so the byte goes back to what the desktop
 * had — with the screen and the palette, in the same block, as one write. */
static void hand_the_sound_engine_back(uint8_t *image, CallerAddressRegisters live) {
    sound_stop(image, live);                                  /* [0x1499c, 0x149b6) */
    poke_long(TOS_VEC_TIMER_C, be32(image + TOS_VEC_TIMER_C));
}

/* ---- the trap #9 gate, and WHY IT GOES IN FIRST ------------------------------------------------
 * THE GATE IS THE SHIM'S, NOT THE GAME'S, and installing it where the game installs its own is a
 * bug this build shipped for exactly one run. `install_sound_vectors` writes image[$a4] — an image
 * byte — and the same routine's very next line is `hw_write8(MFP_VECTOR_REG, …)`, which on target IS
 * a `trap #9`. So the FIRST use of the gate happens inside the routine that was supposed to install
 * it, and with TOS's own $a4 still on the vector that trap reached the ROM's exception handler:
 * bombs, `Pterm(-1)`, and a GEMDOS ledger that looked perfect right up to the last call. The gate is
 * a property of this BUILD's user-mode choice (shim_include/tos.h), not of the game's boot, so it is
 * installed before any core runs and taken back at the hand-back.
 *
 * THE ORIGINAL DELIBERATELY DOES NOT RESTORE $a4 — `remove_sound_vectors` leaves its handler on the
 * vector, because the program stays resident for the life of the machine. This build exits, and a
 * vector pointing into a freed TPA is docs/on-target-execution.md class 7's second trap. So the
 * restore is a deliberate divergence, and it is the direction that leaves the machine usable. */
static uint32_t g_tos_trap9_vector;

static void install_the_supervisor_gate(void) {
    g_tos_trap9_vector = peek_long(TOS_VEC_TRAP9);
    poke_long(TOS_VEC_TRAP9, (uint32_t)(uintptr_t)bg_super_gate_entry);
}

static void remove_the_supervisor_gate(void) {
    poke_long(TOS_VEC_TRAP9, g_tos_trap9_vector);
}

/* ================================================================================================
 * The image's own bookkeeping: alignment, the guard band, and what the machine had room for
 * ============================================================================================= */
static void align_the_image(void) {
    uint32_t raw = (uint32_t)(uintptr_t)g_image_store;

    bg_image_base = (uint8_t *)(uintptr_t)((raw + (IMAGE_ALIGN - 1u)) & ~(IMAGE_ALIGN - 1u));
    memset(bg_image_base + BG_TARGET_IMAGE_BYTES, IMAGE_GUARD_FILL, IMAGE_GUARD_BYTES);
}

static uint32_t guard_bytes_dirty(void) {
    uint32_t dirty = 0;

    for (uint32_t byte = 0; byte < IMAGE_GUARD_BYTES; byte++)
        if (bg_image_base[BG_TARGET_IMAGE_BYTES + byte] != IMAGE_GUARD_FILL)
            dirty++;
    return dirty;
}

/* The basepage's own account of the TPA, floored at the stack `_start` was entered on — whichever
 * is lower is the ceiling this program really has. */
#define BASEPAGE_LOWTPA 0u
#define BASEPAGE_HITPA  4u

static void record_memory_budget(void) {
    uint32_t low = be32(bg_basepage + BASEPAGE_LOWTPA);
    uint32_t high = be32(bg_basepage + BASEPAGE_HITPA);
    uint32_t stack = (uint32_t)(uintptr_t)bg_initial_sp;
    uint32_t image_top = (uint32_t)(uintptr_t)bg_image_base + BG_TARGET_IMAGE_BYTES
                         + IMAGE_GUARD_BYTES;

    if (stack < high)
        high = stack;
    g_record[REC_TPA_LOW] = low;
    g_record[REC_TPA_HIGH] = high;
    g_record[REC_KEPT_TOP] = (uint32_t)(uintptr_t)bg_kept_top;
    g_record[REC_MSHRINK_RESULT] = bg_mshrink_result;
    /* THE HEADROOM IS MEASURED AGAINST THE KEPT TOP, not the TPA's. `_start` gave the rest back, so
     * what stands between the image and the C stack is the shrink's own reserve and nothing more. */
    high = (uint32_t)(uintptr_t)bg_kept_top;
    g_record[REC_IMAGE_HEADROOM] = high > image_top ? high - image_top : 0;
}

/* ================================================================================================
 * bubble_main
 * ============================================================================================= */
/* The counters that keep moving after the anchor — the hand-back makes file, heap and hardware
 * calls of its own — read into the record at the last possible moment, which is the line before
 * STATE.BIN is written. Called from BOTH paths that write it, so the early return's record is a
 * short record and not a stale one. */
static void publish_the_tallies(void) {
    g_record[REC_FILE_OPENS] = bg_file_opens;
    g_record[REC_FILE_OPEN_FAILURES] = bg_file_open_failures;
    g_record[REC_FILE_REFUSALS] = bg_file_refusals;
    g_record[REC_FILE_WRITE_FAILURES] = bg_file_write_failures;
    g_record[REC_SHIM_FILE_OPENS] = g_shim_file_opens;
    g_record[REC_SHIM_FILE_FAILURES] = g_shim_file_failures;
    g_record[REC_MALLOC_CALLS] = bg_malloc_calls;
    g_record[REC_HEAP_POINTER] = bg_heap_pointer;
    g_record[REC_HW_WRITES] = bg_hw_writes;
    g_record[REC_VDI_CALLS] = bg_vdi_calls;
    g_record[REC_AES_CALLS] = bg_aes_calls;
    g_record[REC_VDI_RASTER_COPIES] = bg_vdi_raster_copies;
    g_record[REC_TIMER_C_TICKS] = bg_timer_c_ticks;
    g_record[REC_FAULT_PEN] = (uint32_t)(int32_t)BG_FAULT_PEN;
    g_record[REC_FAULT_IMAGE_WORD] = (uint32_t)BG_FAULT_IMAGE_WORD;
    g_record[REC_FAULT_NO_TIMER_C] = (uint32_t)BG_FAULT_NO_TIMER_C;
}

void bubble_main(void) {
    CallerAddressRegisters live = caller_registers(CALLER_A1, CALLER_A2);
    uint8_t *image;
    uint16_t entry_pens[PALETTE_PENS];
    uint32_t entry_physbase;
    uint16_t entry_resolution;
    uint8_t entry_conterm;
    uint32_t a4;

    g_record[REC_MAGIC] = BG_RECORD_MAGIC;
    reached(PHASE_ENTERED);
    align_the_image();
    image = bg_image_base;
    g_record[REC_IMAGE_BASE] = (uint32_t)(uintptr_t)image;
    g_record[REC_IMAGE_BYTES] = BG_TARGET_IMAGE_BYTES;
    record_memory_budget();

    /* WHAT THE DESKTOP GETS BACK, latched before anything is changed. The resolution is read as
     * well as the screen, because XBIOS Setscreen's third argument SETS a mode: handing back a
     * constant 0 would drop a machine started in medium resolution into ST low. */
    entry_physbase = (uint32_t)Physbase();
    entry_resolution = (uint16_t)Getrez();
    g_record[REC_ENTRY_RESOLUTION] = entry_resolution;
    entry_conterm = peek_conterm();
    read_palette(entry_pens);
    install_the_supervisor_gate();

    /* The anchor's runtime address, written before anything can go wrong, so `smoke.py` can arm its
     * breakpoint on a program that then crashes. */
    {
        uint32_t anchor = (uint32_t)(uintptr_t)bg_anchor;
        (void)write_file(FILE_ANCHOR_BASE, &anchor, (long)sizeof anchor);
    }

    g_record[REC_PROGRAM_BYTES] = (uint32_t)stage_program_image();
    reached(PHASE_IMAGE_STAGED);

    /* ---- the crt0, for real. `../src/init.c`'s slice runs on the FILE layout this build stages,
     * establishes A4 and ANSWERS it; the record carries the answer so that a boot which silently
     * built the wrong globals base is a red rather than a black screen. */
    build_basepage(image);
    a4 = crt0_relocate_and_clear(image, BG_BASEPAGE);
    g_record[REC_A4_BASE] = a4;
    wr32(image + a4 + (uint32_t)(int32_t)CRT0_BASEPAGE_SLOT, BG_BASEPAGE);
    init_globals(image, BG_LOAD_BASE);
    crt0_setup_args(image, BG_BASEPAGE + BASEPAGE_TAIL);
    reached(PHASE_GLOBALS_INITIALISED);

    /* ---- main @ 0x100dc. The gate's answer is the branch, and on target it is a real Getrez. */
    g_record[REC_LOW_RESOLUTION] = (uint32_t)main_check_resolution(image, live);
    if (!g_record[REC_LOW_RESOLUTION]) {
        /* The original prints and then spins for ever (`move.w #$1,d0 / bne` @ 0x100fe). A headless
         * run that spun would look exactly like a hang, so this build says so and leaves instead —
         * a deliberate divergence, and the only one on this arm. */
        remove_the_supervisor_gate();
        publish_the_tallies();
        (void)write_file(FILE_STATE_RECORD, g_record, (long)sizeof g_record);
        return;
    }

    /* ---- init_gem_and_screens @ 0x10118, then the screen the whole program draws on.
     * The conterm seed goes in FIRST, so that the byte the routine clears inside its `Super` bracket
     * is TOS's own; the mirror straight after is that clear, made on the machine. */
    seed_conterm(image);
    main_start_game(image, TOP_FRAME, live);
    mirror_conterm(image);
    g_record[REC_SCREEN_PHYS] = be32(image + A_screen_phys);
    g_record[REC_SCREEN_BACK] = be32(image + A_screen_back);
    publish_screen(be32(image + A_screen_phys), be32(image + A_screen_phys));
    reached(PHASE_GEM_OPEN);

    /* ---- game_top_loop's boot, with the Timer C vector around its installer. */
    seed_the_timer_c_chain(image);
    boot_the_program(image, TOP_FRAME, &live);
    install_the_timer_c_vector(image);
    reached(PHASE_SOUND_STARTED);

#if BG_MODE == BG_MODE_PLAY
    game_play_loop(image, TOP_FRAME, &live);
#else
    /* The title mode stops where a headless check can judge: the menu is drawn and nothing is
     * waiting on a key. `game_new_game` is the slice `title_menu_loop` is called from, and
     * `title_menu_open` is the front end's first region — it ends AT the blocking `Cnecin`, which
     * is exactly the point this mode must not reach. */
    inject_image_fault(image);
    game_new_game(image);
    publish_logical_screen(be32(image + A_screen_phys));
    title_menu_open(image, TOP_FRAME - TOP_LOCAL_BYTES - CALL_FRAME_COST, &live);
    publish_palette(A_dat_palette);
    inject_pen_fault();
    reached(PHASE_MENU_DRAWN);

    bg_anchor();
    reached(PHASE_ANCHOR_HELD);
#endif

    /* ---- what the machine held AT THE ANCHOR, read before anything is handed back ------------ */
    g_record[REC_TIMER_C_CHAIN] = bg_timer_c_chain;
    g_record[REC_TIMER_C_VECTOR] = peek_long(TOS_VEC_TIMER_C);
    g_record[REC_TRAP9_VECTOR] = peek_long(TOS_VEC_TRAP9);
    g_record[REC_CONTERM_AT_ANCHOR] = peek_conterm();
    g_record[REC_READBACK_LOGBASE] = (uint32_t)Logbase();
    g_record[REC_GUARD_DIRTY] = guard_bytes_dirty();

    (void)write_file(FILE_SCREEN_DUMP, image + be32(image + A_screen_phys), SCREEN_BYTES);

    /* HAND THE MACHINE BACK ON EVERY PATH THAT REACHES HERE. Anything installed into TOS outlives
     * the process, and a Timer C handler still chaining out of freed memory halts the machine about
     * a second after Pterm — invisible while the program runs, which is why `smoke.py` lets the
     * emulator run on past the exit and asserts on what it reports (docs/on-target-execution.md
     * class 7). */
    hand_the_sound_engine_back(image, live);
    remove_the_supervisor_gate();
    Setscreen((void *)(uintptr_t)entry_physbase, (void *)(uintptr_t)entry_physbase,
              (short)entry_resolution);
    write_palette(entry_pens);
    /* ...AND THE KEY CLICK, which the faithful teardown does NOT put back: `remove_sound_vectors`
     * restores the zero `init_gem_and_screens` wrote, because the original stays resident and means
     * it to stay off. This build exits, so the byte is returned with the screen and the palette —
     * the same deliberate divergence, in the same direction, for the same reason (class 7). */
    poke_byte(TOS_CONTERM, entry_conterm);
    reached(PHASE_HANDED_BACK);

    publish_the_tallies();
    g_record[REC_TAIL] = BG_RECORD_TAIL;
    (void)write_file(FILE_STATE_RECORD, g_record, (long)sizeof g_record);
}
