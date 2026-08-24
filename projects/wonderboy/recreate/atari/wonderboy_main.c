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
 *
 * ...WITH ONE DECLARED EXCEPTION, AND IT IS THIS BUILD'S ONLY ONE. `-DSMOKE_BOOT` calls
 * ../src/boot.c's three slices, which INTERLEAVE five GEMDOS loads with `set_palette`'s sixteen
 * writes to $ff8240 and the shifter's own base — so those five run INSIDE the supervisor window,
 * five times a run, because hoisting them would mean cutting the slices open. The alternative that
 * was weighed (dropping to user mode inside `disk_read_file`), the reason it was rejected, and the
 * measurement that stands in for the rule are in atari/README.md §14. Every other build here, and
 * every other file read in this one, obeys the paragraph above.
 */
#include <stdint.h>

#include "os.h"
#include "psg.h"
#include "sched.h"
#include "wonderboy.h"
#include "game.h"
#include "boot.h"
#include "rad.h"
#include "stage.h"
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
/* THE OWN-ENTRY BUILD PRODUCES ITS OWN a5 AND DOES NOT MEASURE ONE, which is the one place that
 * build could otherwise still be leaning on the dump. The frame builds take `sprites.blit.unwind`
 * from `build/ORIGREGS.txt`'s A5, measured off the shipped binary at `$f8b4`; an own-entry run has
 * no dump to take it from and must not borrow one.
 *
 * WHO PRODUCES IT, from the listing: the boot's tail is `$f89e / bsr.w $f95c` = `stage_load_window`,
 * whose first builder `bg_build_buffer` ($fa30) carries `lea $21e90.l,a5` at `$fa5e` — the ONE
 * instruction in the hinge that writes a5, executed once per map cell on the arm the shipped tile
 * bank takes (`cmpa.l #$1d43e,a6` matches, so `bg_build_raw_tiles` is cleared and `tst.w` at $fa52
 * falls through). Its operand IS the value, and it is WB_TILE_INDEX_TABLE — the same table
 * ../src/stage.c's `tile_number` reads through, so this is not a new constant.
 *
 * MEASURED, NOT ARGUED, in two independent places: ../test/test_boot_chain.py runs the ORACLE over
 * `boot_load_stage`'s whole range and requires the 68000's own a5 at the `jmp $4a0.w` to be this
 * number, and `atari/smoke.py`'s own-entry mode cross-checks the same figure against ORIGREGS'
 * measured A5 whenever a dump happens to be present. The dump is a WITNESS here and not the source.
 *
 * WHAT IT IS WORTH, said plainly: `sprite_draw_pass` never dereferences a5 — the pass leaves it
 * alone and each wholly-off-left sprite takes WB_BLIT_UNWIND_BYTES off it (../include/blit.h) — so
 * no image byte and no hardware write in this build depends on its value. It is carried because the
 * original carries it, and it is produced rather than seeded so that no build here has to say "the
 * measurement told us". */
#if defined(SMOKE_OWNPLAY) && !defined(M2_ENTRY_UNWIND)
#define M2_ENTRY_UNWIND WB_TILE_INDEX_TABLE
#endif
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

/* ---- the TITLE build: the boot's own first picture ---------------------------------------------
 *
 * `-DSMOKE_TITLE` swaps what the shim does between taking the machine and handing it back for the
 * THIRD time, and it is the first build here whose picture the reconstruction PRODUCES rather than
 * inherits. M2 stages the original's post-boot RAM because the chain that loads a stage is unported;
 * the title screen's chain is FIVE calls long and every one of them is now reconstructed, so this
 * build starts from the program image alone — the same one M1 stages — and draws the screen:
 *
 *   $e526  load_resource_by_index(WB_RESOURCE_TITLESCR, WB_RESOURCE_LOAD_BUFFER)  (../src/boot.c)
 *   $e536  rad_depack(WB_RESOURCE_LOAD_BUFFER -> WB_TITLE_DEPACK_DEST)               (../src/rad.c)
 *   $e540  set_palette(WB_TITLE_PALETTE_SRC)                                         (../src/stage.c)
 *
 * ...with $e4ea's `clear_palette` and $e4ee's `clear_both_screens` in front of them, as the boot has
 * them. The first of those calls crosses the FILE-LOAD SEAM (the kit's include/disk.h), so this is
 * also the first build in which a reconstructed routine asks the machine for a file.
 *
 * WHAT IS DEVIATED FROM THE BOOT, and it is three things, all stated where the claim is made
 * (atari/README.md §13):
 *
 *   THE COPYLOCK IS NOT ARMED. `$e51e` writes `#$ffff` to WB_COPYLOCK_ARM_FLAG immediately before
 *   this load, and `load_resource_by_index`'s armed arm would report WB_LOAD_COPYLOCK_RAN — the
 *   port's way of saying "the protection would have run here", since the blob cannot be ported and
 *   is not stubbed. So the flag is left at the $0000 the shipped file carries, the load reports
 *   WB_LOAD_OK, and the record carries the flag as read out of the image so that the smoke asserts
 *   it rather than taking this paragraph's word for it. Nothing on the compared surfaces depends on
 *   it: the protection decrypts nothing this picture is made of — the file is on the disk in the
 *   clear and `rad_depack` is the only thing that touches it.
 *
 *   THE LOAD RUNS IN USER MODE, BEFORE the machine is taken, where everything else in this slice
 *   runs in supervisor. That is this file's standing rule for GEMDOS (see the banner: handle
 *   allocation misbehaves when entered from supervisor under Hatari's GEMDOS drive), and it costs
 *   nothing here because the load touches only image bytes — WB_LOAD_RETRY_INDEX/_DEST, WB_JOY1_STATE
 *   and the destination — and the clears that the boot performs before it touch a disjoint range
 *   ($ff8240.. and WB_SCREEN_LOW..) which nothing in the load reads.
 *
 *   THE SOUND REQUEST AT $e546 IS NOT MADE. `move.w #$8,d0 / lea $17adc.l,a0 / jsr (a0)` starts the
 *   title music between `set_palette` and the fire wait. It writes no framebuffer byte and no
 *   colour register, so neither compared surface can see it; the surface that could is M6's ordered
 *   PSG stream, and this build does not carry one.
 */
#ifdef SMOKE_TITLE
/* WHICH RESOURCE THIS BUILD DEPACKS, and the default is the one the boot loads first. The override
 * is the mode's NEGATIVE CONTROL: `build.sh titlecredits` compiles WB_RESOURCE_CREDITS, so the same
 * code draws the game's OTHER shipped picture into the same buffer through the same three calls,
 * and every row of the comparison that a different picture can break must break.
 *
 * REPORTED BY THE BINARY in the record below, for `fault_pen`'s reason: the per-mode `.PRG`s persist
 * while this file is edited, so a smoke that scraped the `-D` out of build.sh would be naming a
 * resource the running binary need not have loaded. */
#ifndef TITLE_RESOURCE
#define TITLE_RESOURCE WB_RESOURCE_TITLESCR
#endif

/* The depack destination and its palette row are ../include/wonderboy.h's WB_TITLE_DEPACK_DEST and
 * WB_TITLE_PALETTE_SRC — the ORIGINAL's own operands at $e530 and $e53a, and since batch 44 phase C
 * the SAME two constants ../src/boot.c's `boot_title_screen` uses, so this build and the core cannot
 * disagree about where the picture goes. What the first of them buys is written down as an assertion
 * instead: the depacked file is WB_RAD_PICTURE_PREFIX bytes of header-and-palette followed by exactly
 * one screen, so the destination plus the unpacked length lands on WB_SCREEN_LOW's end and the
 * picture is inflated STRAIGHT INTO the visible buffer. The record carries the unpacked length out of
 * the file's own header and smoke.py pins that arithmetic. */
#endif

/* ---- the BOOT build: the whole chain, on the machine ---------------------------------------------
 *
 * `-DSMOKE_BOOT` is the title build's rung and then two more. Where SMOKE_TITLE MIRRORS the first of
 * ../src/boot.c's three composed slices, this build CALLS all three, in the boot's own order, with
 * the boot's own fire gates between them:
 *
 *   boot_title_screen()    $e512..$e550   arm the protection, TITLESCR.RAD, depack, palette, song 8
 *   [the fire gate]        $e552..$e560   clr.b WB_JOY1_STATE, then the two spins
 *   boot_credits_screen()  $e562..$e5a2   CREDITS.RAD, depack, palette, copy down, new game, pen 10
 *   [the fire gate]        $e5aa..$e5b8   the same pair again
 *   boot_load_stage()      $e5ba..$f8b4   the sequence row, its overlay, TILEDATA.RAD, SPRITES.CRU,
 *                                         the two installers, the actors, and the hinge
 *
 * ...and then it writes the whole game span out, which is the point: `atari/original.py dump` takes
 * the ORIGINAL's RAM at `$f8b4` and `gen_image.py` stages it, because nothing in this directory ran
 * the chain that produces it. This build runs the chain. What it emits is the same span RECOMPUTED,
 * and smoke.py differences the two band by band.
 *
 * WHAT IS DEVIATED FROM THE BOOT, and it is six things. The first three are SMOKE_TITLE's, one of
 * them inverted; the last three are this build's own. atari/README.md §14 is where each is argued.
 *
 *   THE PROLOGUE AT $e4e6..$e510 IS THE SHIM'S, as it is for SMOKE_TITLE: the palette and screen
 *   clears and the video mode are made, the MFP timer masks are NOT, and the level-4 vector installed
 *   is this file's `wb_vbl_entry` rather than the game's own $716.
 *
 *   THE COPYLOCK IS ARMED — the opposite of SMOKE_TITLE, and not a change of mind. `boot_title_screen`
 *   performs $e51e's `move.w #$ffff,$e7cc.l` because the original does, so `load_resource_by_index`
 *   takes its ARMED arm and reports WB_LOAD_COPYLOCK_RAN. That code is the port's way of saying "the
 *   blob would have executed here"; the blob itself is NOT reproduced and NOT stubbed, so nothing on
 *   this machine runs the protection. The record carries all three slices' codes and smoke.py asserts
 *   which loads took which arm, so the statement is checkable rather than written down.
 *
 *   THE LOADS RUN IN SUPERVISOR. SMOKE_TITLE hoists its one load out of the machine-taken window
 *   because it can — the load is the first thing the slice does. This chain interleaves five loads
 *   with `set_palette`'s sixteen writes to $ff8240, a single colour register and the shifter's own
 *   base, and an I/O-space access from user mode is a bus error — so the loads cannot be hoisted
 *   without cutting the slices open, which would make this build a re-implementation of ../src/boot.c
 *   rather than a caller of it. README.md §14 has the alternative that was weighed (dropping to user
 *   mode inside `disk_read_file` and coming back) and why the measurement was preferred to it.
 *
 *   THE FIRE GATES ARE BOUNDED SPINS AND A DEBUGGER DRIVES THEM. The boot waits on a byte only the
 *   IKBD interrupt writes; headless, nothing presses a stick. So each half of each gate is its own
 *   `noinline` function whose address this record reports, and smoke.py pokes WB_JOY1_STATE at those
 *   PCs — the SAME mechanism atari/original.py uses on the shipped side, where `boot_script` pokes
 *   the same byte at $e556/$e55c. The bound is `SPINS_LONG`, well inside `--run-vbls`, because a
 *   wait that outruns the harness is not a watchdog (README.md's bug 3).
 *
 *   THE DATA-DISK PROMPT IS NOT REACHED. The original's boot asks a player to swap disks between the
 *   credits and the stage load ($e494's `show_data_disk_prompt`, which is unported); this build's
 *   GEMDOS drive carries disk 1's two resources and disk 2's three side by side, so
 *   `boot_load_stage` finds OVALAY01.RAD, TILEDATA.RAD and SPRITES.CRU without a swap. One volume
 *   where the original has two.
 *
 *   THE IMAGE IS SNAPSHOTTED AT THE SLICE'S OWN LAST INSTANT, not at the end of the run. The write
 *   itself is GEMDOS and so has to wait for user mode, and between the two `vbl_handler` keeps
 *   running — the music tick, the idle countdown — so a span written at the end would be the span at
 *   teardown and not the span at the `$f8b4`-equivalent moment `original.py` dumps. It is copied
 *   aside the instant `boot_load_stage` returns, with interrupts masked so no vblank can land inside
 *   the copy, and the copy is what reaches the file.
 */
#if defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
/* WB_JOY1_STATE's bit 7 is the fire button in the IKBD's joystick report, and the boot's two
 * `tst.b`/`bpl`/`bmi` pairs are testing exactly that bit through the sign. DERIVED FROM
 * WB_JOY1_FIRE_BIT rather than written as `0x80`: the bit NUMBER has one definition in
 * ../include/wonderboy.h, which ../test/layout.py scrapes for the Python side, and a third spelling
 * of the mask is a third place for the two shores to stop naming the same bit (CLAUDE.md §5). */
#define FIRE_DOWN_BIT    (1u << WB_JOY1_FIRE_BIT)
#define FIRE_NONE        0x00u
#endif

#ifdef SMOKE_BOOT
/* The span this build writes out: the game's whole address space, which is `original.py`'s
 * GAME_SPAN_END and the `movea.l #$80000,a7` the game itself performs. */
#define BOOT_SPAN_AT     WB_STAGED_AT
#define BOOT_SPAN_END    WB_ST_MEMORY_TOP
#define BOOT_SPAN_BYTES  (BOOT_SPAN_END - BOOT_SPAN_AT)
#endif

#if defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
/* A slice that never ran, told apart from WB_LOAD_OK (which is 0). Out of band because the three
 * WB_LOAD_* codes are 0, 1 and 2, and a mode that read "did not run" as "loaded fine" would report a
 * green boot for a chain that stopped at its first gate. */
#define BOOT_SLICE_NOT_RUN 0xffffffffu
#endif

/* THE TITLE AND BOOT BUILDS ARE MUTUALLY EXCLUSIVE, AND THE COMPILER IS WHAT SAYS SO. They share one
 * `photographed_screen`/`photographed_pens` pair and both write the same FRAME_FILE and PENS_FILE, so
 * a binary carrying both would photograph twice into one buffer and smoke.py could not tell which
 * routine produced the file it grades. Until now the contract rested on `build.sh`'s `case` arm
 * choosing one `-D` — a script one edit away from passing both — where PROGRAM_BYTES' own missing-`-D`
 * check is enforced here, in the file that depends on it. */
#if defined(SMOKE_TITLE) && (defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY))
#error "SMOKE_TITLE shares one capture buffer and one FRAME.BIN with SMOKE_BOOT and with SMOKE_OWNPLAY's frame anchors — build exactly one of the three"
#endif

/* THE THREE BUILDS THAT PHOTOGRAPH THE MACHINE, as one condition rather than three lists. Each
 * carries a 32000-byte framebuffer and the machine's sixteen pens off in the same two files, read
 * back by the same code in smoke.py, so what they share is defined once below and what differs is
 * theirs. */
#if defined(SMOKE_BOOT) && defined(SMOKE_OWNPLAY)
#error "SMOKE_BOOT photographs into FRAME.BIN and SMOKE_OWNPLAY's frame anchors write the same file"
#endif
#if defined(SMOKE_M2) || defined(SMOKE_TITLE) || defined(SMOKE_BOOT)
#define SMOKE_CAPTURES 1
#endif

/* ...AND THE OTHER SHARED TOKEN, for the same reason one line up: TWO builds run ../src/boot.c's
 * composed chain — the BOOT build measures it and the OWN-ENTRY build plays it — and the chain's
 * ORDER, its two fire gates and its three slice reports must have exactly ONE statement between
 * them. Two spellings of "title, gate, credits, gate, stage" is two places a slice can be inserted
 * and one place it can be forgotten, which is the shape phase C's own retracted prologue claim took.
 * Everything either build does BESIDE the chain stays that build's. */
#if defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
#define SMOKE_BOOT_CHAIN 1
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

/* ...and one longword. Only the photographing builds read one — M2 the front-buffer pointer, the
 * title build the .RAD header's two lengths — so it is compiled with them. */
#ifdef SMOKE_CAPTURES
static uint32_t image_long(uint32_t at) {
    return ((uint32_t)image_word(at) << 16) | image_word(at + 2u);
}
#endif

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

/* $ffff8201/$ffff8203 READ BACK, as the address they compose. An STF publishes the video base in two
 * write-only-looking registers holding bits 23-16 and 15-8 — there is no low byte, so what comes
 * back is 256-byte-aligned by construction and this is the whole of the number.
 *
 * ONE SPELLING, for `READ_THE_STAGE_PINS`' reason two hundred lines down: three places in this file
 * take this reading — the photograph's own instant, the ESC pass's before-the-slice reading, and the
 * frame build's at-the-exit one — and TWO of those three are the two SIDES of the row that kills the
 * P3 and P5 mutants (../STATUS.md batch 44 phase F). A compose written out three times is two
 * chances for one side of that row to shift the bytes differently from the other while both stay
 * green.
 *
 * WHEN it is read is the caller's and stays there: every one of the three has its own paragraph
 * about the instant, because `teardown` puts TOS's base back and a read after that reports the
 * desktop's screen for ever. */
static inline uint32_t read_the_shifter_base(void) {
    return ((uint32_t)*io8(SHIFTER_BASE_HI) << 16)
           | ((uint32_t)*io8(SHIFTER_BASE_MID) << 8);
}


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
static void publish_base_bytes(uint8_t high, uint8_t mid) {
    uint32_t want;

    wb_target_shifter_byte(WB_SHIFTER_SCREEN_BASE_HIGH, high);
    wb_target_shifter_byte(WB_SHIFTER_SCREEN_BASE_MID, mid);

    want = wb_target_screen_base;
    checked(RB_SCREEN_BASE_PUBLISHED,
            *io8(SHIFTER_BASE_HI) == (uint8_t)(want >> 16)
            && *io8(SHIFTER_BASE_MID) == (uint8_t)(want >> 8));
}

/* EXACTLY ONE OF THE TWO IS COMPILED, keyed on the build, because the boot publishes the base two
 * different ways at two different moments and this shim stands in for whichever one its build is at.
 *
 * THE TITLE'S BASE IS NOT WB_SCREEN_FRONT'S, and that is the boot's own arrangement rather than a
 * choice here. `video_set_lowres_50hz` ($f906) publishes it as two IMMEDIATES —
 * `move.b #$7,$ff8201.l` / `move.b #$0,$ff8203.l`, i.e. WB_SCREEN_LOW — and never reads the pointer
 * pair; WB_SCREEN_FRONT is the FRAME LOOP's, and the shipped file carries WB_SCREEN_HIGH in it,
 * which is the buffer the title picture is NOT in. Publishing that instead would display 32000
 * bytes of the screen the depack does not reach. The two bytes are taken apart from the one
 * constant rather than written as 7 and 0. */
#if defined(SMOKE_TITLE) || defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
static void publish_screen_base(void) {
    publish_base_bytes((uint8_t)(WB_SCREEN_LOW >> 16), (uint8_t)(WB_SCREEN_LOW >> 8));
}
#else
static void publish_screen_base(void) {
    publish_base_bytes(game_image[WB_SCREEN_FRONT_BITS_16_23],
                       game_image[WB_SCREEN_FRONT_BITS_8_15]);
}
#endif

#if defined(SMOKE_TITLE) || defined(SMOKE_BOOT_CHAIN)
/* $e4ea and $e4ee — the two steps of the boot's prologue ($e4e6..$e510) that ARE reconstructed, in
 * the order the boot makes them. The other four are privileged hardware setup this shim stands in
 * for its own way (`install` and `publish_screen_base`), and the SMOKE_TITLE banner declares that.
 *
 * ONE STATEMENT FOR THREE CALLERS. The title build, the boot build and the own-entry ladder all
 * make this pair; three copies of it is three places one of them can be dropped, and the pair is
 * NOT a no-op on the own-entry build's ESC restart, where the screens really do hold the last
 * stage's picture. (Over the M1 image the two clears are near no-ops — the screens are .bss and
 * `set_palette` overwrites the palette — and they are made because the boot makes them, which is
 * the only reason a slice's neighbour belongs in a build that calls the slice.) */
static void clear_the_palette_and_screens(void) {
    (void)clear_palette(game_image);            /* $e4ea */
    clear_both_screens(game_image);             /* $e4ee */
}
#endif

static void teardown(void) {
    /* SMOKE_M3_NO_HANDBACK is M3's HAND-BACK CONTROL (build.sh m3fault), and it is `novbl`'s shape at
     * the other end of the run: the two vector stores suppressed and nothing else — the same install,
     * the same frames, the same ending driven, the same record written. What must then fail is every
     * assertion that the machine was GIVEN BACK: the two read-backs here, the debugger's own
     * comparison of $70/$118 across the program's exit, and TOS's frame clock, which stops advancing
     * the moment its vertical-blank handler is no longer the one on the vector. */
#ifndef SMOKE_M3_NO_HANDBACK
    *io32(VEC_LEVEL4_VBL) = saved.vbl_vector;
#endif
    checked(RB_VBL_VECTOR_RESTORED, *io32(VEC_LEVEL4_VBL) == saved.vbl_vector);
#ifndef SMOKE_M3_NO_HANDBACK
    *io32(VEC_MFP_ACIA) = saved.acia_vector;
#endif
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

/* Zero one of this file's five records, byte by byte. FIVE HAND-WRITTEN COPIES OF THE SAME LOOP IS
 * FIVE PLACES ONE CAN BE FORGOTTEN when a sixth build arrives, and a record that is not zeroed
 * reports whatever the stack held — which every "did not run" reading in smoke.py rests on. The
 * loop variable is the macro's own, so a caller cannot accidentally share one with the code around
 * it. */
#define ZERO_RECORD(r)                                  \
    do {                                                \
        unsigned zero_at;                               \
        for (zero_at = 0; zero_at < sizeof(r); zero_at++)   \
            ((uint8_t *)&(r))[zero_at] = 0;             \
    } while (0)


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
/* ---- what the PHOTOGRAPHING builds share --------------------------------------------------------
 *
 * M2 takes four pictures of a running frame loop, the title build takes one of the screen its slice
 * drew and the BOOT build takes one of the credits screen at its own anchor — but the SURFACE is the
 * same in all three: 32000 bytes out of the image and sixteen words off the shifter, in FRAME.BIN
 * and PENS.BIN, sized from the same header constants smoke.py reads. Defined here rather than three
 * times, so a build cannot photograph a differently-shaped screen. */
#ifdef SMOKE_CAPTURES
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

static const char FRAME_FILE[] = "FRAME.BIN";
static const char PENS_FILE[] = "PENS.BIN";

/* One colour register per pen, read where the picture's colour really is. Unmasked on purpose: the
 * comparison against the shipped binary is done on both sides through `original.pen_words`, which
 * owns the masking rule, and a second application here would be a second place to correct it. */
static void read_shifter_pens(uint16_t *into) {
    unsigned pen;

    for (pen = 0; pen < PALETTE_PENS; pen++)
        into[pen] = *(volatile uint16_t *)(uintptr_t)(SHIFTER_PALETTE
                                                      + pen * WB_SHIFTER_PALETTE_STRIDE);
}
#endif /* SMOKE_CAPTURES */

/* ---- what the TWO PICTURE BUILDS share, which is the whole photograph ---------------------------
 *
 * The title build and the boot build take the same photograph of the same buffer at their own
 * anchors: the sixteen pens checked against the words the slice put there, the 32000 bytes at
 * WB_SCREEN_LOW, the chip's own sixteen registers, and the shifter base read where it means
 * something. Written once, because the pen compare and the base reassembly are the ONLY surfaces
 * that can see `set_palette` and the shifter at all (the oracle drops both writes), and a
 * correction applied to one copy would leave the other build reading the wrong thing at the only
 * instant it means anything.
 *
 * THREE BUILDS TAKE A PICTURE AND NO TWO OF THEM ARE THE SAME BUILD, so the buffers are ONE pair
 * rather than three: `build.sh` compiles exactly one of -DSMOKE_TITLE / -DSMOKE_BOOT /
 * -DSMOKE_OWNPLAY, so three pairs would be 64 KB of .bss that never fills. The title and boot builds
 * write the pair out as FRAME_FILE/PENS_FILE; the own-entry build cannot, because it also compiles
 * -DSMOKE_M2 and those two names are already the frame loop's anchor captures — so it writes
 * PROMPT_FILE/PROMPT_PENS_FILE, and smoke.py can therefore always tell which routine produced the
 * file it grades. */
#if defined(SMOKE_TITLE) || defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
static uint8_t photographed_screen[SCREEN_BYTES];
static uint16_t photographed_pens[PALETTE_PENS];

/* NO PEN IS EXPECTED TO DIFFER FROM THE PICTURE'S OWN WORD — the title slice's case, and the
 * data-disk prompt's. The boot's credits slice passes WB_CREDITS_PROMPT_PEN instead, because `$e5a2`
 * raises that one register to WB_CREDITS_PROMPT_COLOUR after `set_palette` has run. Out of band
 * because a pen index is 0..PALETTE_PENS-1, which is `NO_FAULTED_PEN`'s own trick one block over. */
#define NO_OVERRIDDEN_PEN PALETTE_PENS

/* The .RAD header the load left at WB_RESOURCE_LOAD_BUFFER, into the caller's two record fields. It
 * is what says the file arrived: a refused load leaves the buffer as it found it. Shared by the
 * title and boot builds because both read the same two longwords out of the same buffer after a
 * load — and GUARDED to those two, not to the whole photograph module around it: the own-entry
 * build reports no header, having no length row to compare one against, and a definition it never
 * calls is a -Wunused-function on a build this file otherwise compiles clean. */
#if defined(SMOKE_TITLE) || defined(SMOKE_BOOT)
static void read_rad_header(uint32_t *packed, uint32_t *unpacked) {
    *packed = image_long(WB_RESOURCE_LOAD_BUFFER + RAD_HDR_PACKED_OFF);
    *unpacked = image_long(WB_RESOURCE_LOAD_BUFFER + RAD_HDR_UNPACKED_OFF);
}
#endif

/* Photograph the visible buffer and the chip, and hand back which pens did NOT read back as the
 * slice left them. `capture_at` is the image address the 32000 bytes are read from — and it is
 * REPORTED THROUGH `*captured_at` BY THE ROUTINE THAT USES IT, not written down again by the caller:
 * smoke.py asserts `captured_at == WB_SCREEN_LOW`, and while the caller set the field and this
 * function copied from a constant of its own the two could not disagree, so the row was a compile-time
 * constant compared against itself. Now a caller that photographs the wrong buffer reds.
 * `palette_src` is the image address the slice's `set_palette` read from; `overridden_pen` /
 * `overridden_colour` are the one register a later instruction raised, or NO_OVERRIDDEN_PEN.
 * `*shifter_base` takes $ffff8201/8203 as they read AT THE PHOTOGRAPH, which is the only instant they
 * mean anything: `teardown` puts TOS's own base back and a read after that reports the desktop's
 * screen for ever.
 *
 * THE PICTURE IS READ WHERE THE SHIFTER IS POINTED, which is M2's rule and not a restatement of
 * where the depack was aimed: whether the slice's own arithmetic landed there is a SEPARATE claim,
 * carried by the record's `depack_dest`/`unpacked_bytes` and asserted by smoke.py. */
static uint32_t photograph_the_screen(uint32_t capture_at, uint32_t palette_src,
                                      unsigned overridden_pen, uint16_t overridden_colour,
                                      uint32_t *captured_at, uint32_t *shifter_base) {
    uint32_t pens_readback_failed = 0;
    unsigned pen;

    for (pen = 0; pen < PALETTE_PENS; pen++) {
        uint32_t at = pen * WB_SHIFTER_PALETTE_STRIDE;
        uint16_t wanted = (pen == overridden_pen) ? overridden_colour
                                                  : image_word(palette_src + at);
        uint16_t held = *(volatile uint16_t *)(uintptr_t)(SHIFTER_PALETTE + at);

        if ((held & ST_PEN_MASK) != (wanted & ST_PEN_MASK))
            pens_readback_failed |= 1u << pen;
    }

    memcpy(photographed_screen, game_image + capture_at, SCREEN_BYTES);
    read_shifter_pens(photographed_pens);
    *captured_at = capture_at;
    *shifter_base = read_the_shifter_base();
    return pens_readback_failed;
}
#endif /* SMOKE_TITLE || SMOKE_BOOT || SMOKE_OWNPLAY */

#ifdef SMOKE_M2
#define M2_MAGIC 0x57424132u        /* 'WBA2' */
/* How many anchors the record has room to carry. Not a limit on M2_ANCHOR_FRAMES — the static
 * assertion below refuses a longer list rather than truncating one. */
#define M2_ANCHOR_MAX 8u

static const char M2_FILE[] = "M2.BIN";
/* The pens the ORIGINAL's boot left in the shifter, staged beside WB.IMG.
 *
 * THE PALETTE IS THE BOOT'S PRODUCT AND IT DOES NOT LIVE IN RAM. `set_palette` is called from
 * `stage_load_window`, inside the unported chain, so an M2 build that staged only memory paints its
 * frame through whatever owned the shifter last — measured on the first M2 run, which came back
 * with TOS 1.04's own desktop palette (777 700 070 770 ...). This is the same sentence as the image
 * itself: the boot's result handed over, because the boot is not ported.
 *
 * ...AND THE OWN-ENTRY BUILD HAS NO SUCH FILE, which is why the name is compiled out there rather
 * than merely left unread: this build's boot chain IS ported, so its three `set_palette` calls put
 * the pens on the chip and there is nothing to stand in for. `staged_pens` itself stays, because
 * M6's re-arm control publishes it and `publish_staged_pens` is still referenced. */
#ifndef SMOKE_OWNPLAY
static const char STAGED_PENS_FILE[] = "PENS.IMG";
#endif
static uint16_t staged_pens[PALETTE_PENS];

struct m2_stats {
    uint32_t magic;
    uint32_t bytes;
    uint32_t image_base;
    uint32_t frames_requested;
    uint32_t frames_run;
    /* The WB_KEY_ACTIONS_* the last iteration returned — and M3'S EVIDENCE FIELD, not a diagnostic.
     * `game_key_actions`' three endings are the only way out of the play build's frame loop, so a
     * play session that produced a record produced it BECAUSE one of them fired, and this field
     * says WHICH: ROUND_END, LEVEL_SKIP or QUIT (../include/game.h). Reading it beats inferring the
     * exit from the frame count, which cannot tell three endings apart. */
    uint32_t loop_ending;
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
    uint32_t front = image_long(WB_SCREEN_FRONT);

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
    read_shifter_pens(captured_pens[slot]);
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
 * 588 vblanks (~11 each), so 2000 is well over three times the reading and still leaves the boot and
 * a tail inside smoke.py's run. (The figure was first written as an ESTIMATE of ~780 from a guessed
 * 15 vblanks a frame, beside a run that had already reported 583. Two numbers for one measurement,
 * and the one in the comment was the one nobody had measured. The reading itself drifts a little
 * with the build — 583, then 584, then 588 — which is why the budget is three times it and not
 * pinned to it.)
 *
 * WHAT IT CANNOT CATCH, stated because a watchdog's edge matters more than its middle: this is
 * checked BETWEEN frames, and `flip_screen`'s two waits are uncapped spins INSIDE one. A dead
 * level-4 vector therefore still hangs, and what ends that run is `--run-vbls` and a missing
 * M2.BIN. What this bounds is a loop that is merely far too slow. */
#define M2_VBL_BUDGET 2000u

/* The floor RB_VBL_TICKING holds the shim's own clock to, per frame the loop completed. ONE and not
 * the measured ~11: `flip_screen` waits for the counter to CHANGE twice a frame, so one tick a frame
 * is what the mechanism guarantees and eleven is what this stage happens to cost. A floor set at the
 * reading would red on a lighter frame and would be measuring the game rather than the machine. */
#define MIN_VBLANKS_PER_FRAME 1u

/* ---- the PLAY build: the same frames, without either bound ---------------------------------------
 *
 * `-DSMOKE_PLAY` is the switch `atari/run.sh`'s build throws (it builds `ownrun`, which is this
 * flag on top of the own-entry ladder — build.sh's own list is the authority on which modes carry
 * it), and it changes nothing about the frame except how many of them there are. Both bounds above exist for a HEADLESS run — a fixed count so the two
 * sides compare the same fifty-two frames, and a watchdog so a loop that is merely far too slow
 * ends with a record instead of hanging — and an interactive session wants neither: the original's
 * frame loop is `do { ... } while (1)` with no exit instruction (../src/game.c), and a person
 * watching is the thing that ends the run.
 *
 * THE WATCHDOG IS A FLAG RATHER THAN A HUGE BUDGET, because `shim_vbl_ticks + M2_VBL_BUDGET` is
 * computed once and a budget near UINT32_MAX wraps the deadline BELOW the current tick — the
 * watchdog would then fire on frame one and the play build would stop instantly. GCC folds the
 * constant, so the headless builds keep exactly the instruction sequence they had.
 *
 * TWO OF `run_frames`' THREE EXITS ARE GONE; THE THIRD IS NOT, and the difference matters because
 * the first draft of this comment claimed the loop could never be left. It can: a frame in which
 * `game_main_loop` reaches ANY of its five endings returns a `loop_ending` that is not
 * WB_KEY_ACTIONS_RETURNED, and the loop breaks, hands the machine back and writes STATS.BIN like any
 * other build.
 *
 * FIVE AND NOT THREE, AND THE TWO NEW ONES ARE NOT INPUT'S (../include/game.h's census): three are
 * `game_key_actions`' keys, and two are the PLAYER's own — a life spent, a game-over box expiring —
 * which a run that presses nothing can still reach if the game kills him. What `smoke.py play`
 * asserts is therefore a MEASUREMENT of this build over its window and not a proof about it: over
 * PLAY_RUN_VBLS on the staged frame image no ending fires and no record appears, and if one ever
 * does the row prints WHICH — the `loop_ending` field names it. A PERSON at `atari/run.sh` reaches
 * them deliberately, and what happens then is M3's, driven on the FRAME build: that build's exit is
 * this one's, line for line, and the only thing SMOKE_PLAY changes is how many frames come before
 * it. */
#ifdef SMOKE_PLAY
#define M2_FRAME_LIMIT    0xffffffffu
#define M2_WATCHDOG_ARMED 0
#else
#define M2_FRAME_LIMIT    M2_LAST_ANCHOR
#define M2_WATCHDOG_ARMED 1
#endif

/* ---- M6's NEGATIVE CONTROL: a re-arm that changes nothing ----------------------------------------
 *
 * `-DSMOKE_M6_REARM` re-publishes the staged palette after every frame — the SAME sixteen words,
 * through the same sink, so not one pen ever holds a different colour. Every snapshot this project
 * takes stays green: the framebuffer is untouched, the pens read back the values they already had,
 * the hardware-state vector is identical and so is the rendered picture. The only surface that can
 * see it is the ORDER AND COUNT of what reached the chip, which is M6.
 *
 * IT IS THE SIBLING PROJECT'S OWN BUG, REPRODUCED ON PURPOSE. Joust's VBL handler re-armed
 * `_colorptr` every vblank — 773 palette loads over a run in which the original performs four — and
 * every snapshot in that project was green because each of the 773 loads wrote the same correct
 * sixteen words. It was found by reading a trace by hand. Here it is a control, so that Wonder Boy's
 * timeline is shown to be able to fail rather than assumed to be. */
#ifdef SMOKE_M6_REARM
#define M6_REARM_EVERY_FRAME 1
#else
#define M6_REARM_EVERY_FRAME 0
#endif

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

#ifdef SMOKE_OWNPLAY
/* `sprites.blit.unwind` as the frame loop was ENTERED with it, published into the own-entry
 * record. A file-static because the register file is `run_frames`' local and the ladder's record is
 * two levels up — `fire_gates_crossed`'s arrangement, for the same reason. */
static uint32_t frame_entry_unwind;
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
#ifdef SMOKE_OWNPLAY
    /* READ BACK OUT OF THE REGISTER FILE, and that is the whole point of the line rather than a
     * flourish — `m2.flash_timer_at_entry`'s rule, one field over. Reporting `M2_ENTRY_UNWIND`
     * itself would publish the macro and let smoke.py compare it against the same header constant,
     * which cannot fail however the seeding above is edited (build.sh passes -DM2_ENTRY_UNWIND to
     * the FRAME modes only, so the own-entry build always takes the fallback #define). Taking it
     * from the field the loop is actually entered with is what makes an edit to the line above
     * redden the row. */
    frame_entry_unwind = sprites.blit.unwind;
#endif

    for (frame = 0; frame < M2_FRAME_LIMIT; frame++) {
        unsigned slot;

        record->loop_ending = game_main_loop(game_image, &sprites);
        if (record->loop_ending != WB_KEY_ACTIONS_RETURNED)
            break;                  /* the loop was LEFT, exactly as the original's `jmp` leaves it */
        slot = anchor_slot(frame + 1);          /* the anchors are 1-based, like the debugger's hits */
        if (slot < M2_ANCHOR_COUNT)
            capture_the_frame(record, slot);
        if (M6_REARM_EVERY_FRAME)
            publish_staged_pens(record);        /* M6's control; changes no value, only the timeline */
        /* THE TWO BREAKS COUNT DIFFERENTLY, and an earlier draft returned `frame` for both. The
         * unwind above happens INSTEAD of a frame, so `frame` is the number that completed; the
         * watchdog here happens AFTER one, so it is `frame + 1`. Reporting the smaller number would
         * have reddened "every frame ran" on a run that ran every frame it was asked for. */
        if (M2_WATCHDOG_ARMED && shim_vbl_ticks >= deadline)
            return frame + 1u;
    }
    return frame;
}

#endif /* SMOKE_M2 */


/* ---- the title screen, drawn by the reconstruction ---------------------------------------------
 *
 * The SMOKE_TITLE banner near the top of this file says what this build is and what it deviates
 * from. This is the code: a record, one screen's worth of capture, and the boot slice in the two
 * halves the privilege rule cuts it into.
 *
 * A THIRD RECORD FOR THE THIRD BUILD, for the reason M2 got a second one: smoke.py checks each
 * record's size against its own format string, so one record that grew per build mode would make
 * every other mode's version check fire. Three records, three magics, three readers. */
#ifdef SMOKE_TITLE
#define TITLE_MAGIC 0x57424133u     /* 'WBA3' */

static const char TITLE_FILE[] = "TITLE.BIN";

struct title_stats {
    uint32_t magic;
    uint32_t bytes;                 /* sizeof(struct title_stats) — the version check */
    uint32_t image_base;
    /* WHICH ROW OF WB_RESOURCE_FILE_TABLE THIS BINARY ASKED FOR. Reported rather than scraped out
     * of build.sh, for `fault_pen`'s reason: the per-mode `.PRG`s outlive an edit to the script. */
    uint32_t resource_index;
    /* WB_COPYLOCK_ARM_FLAG as the load found it. The boot arms it at $e51e and this build does not
     * (see the banner), so this must be $0000 and `load_result` must be WB_LOAD_OK — the pair is
     * the honesty note made checkable instead of merely written down. */
    uint32_t copylock_arm_flag;
    uint32_t load_result;           /* load_resource_by_index's WB_LOAD_* (../include/wonderboy.h) */
    /* The .RAD header's OWN two lengths, read back out of the destination after the load. They are
     * what says the file arrived — a refused load leaves the buffer's zeros — and `unpacked_bytes`
     * is what pins the geometry claim WB_TITLE_DEPACK_DEST rests on. */
    uint32_t packed_bytes;
    uint32_t unpacked_bytes;
    uint32_t depack_result;         /* rad_depack's d0; WB_RAD_BAD_CHECKSUM is its one status */
    uint32_t depack_dest;
    uint32_t captured_at;           /* where the 32000 photographed bytes were read from */
    uint32_t screen_base_published; /* ...and the machine address the shifter was pointed at */
    uint32_t shifter_base;          /* $ffff8201/8203 READ BACK, at the instant of the photograph */
    /* Which of the sixteen pens `set_palette` put on the chip does not read back as the word it
     * was given. Not an RB_* bit, for the reason M2's own pen field is not one. */
    uint32_t pens_readback_failed;
};

/* USER MODE, before the machine is taken: the one file read the RECONSTRUCTION itself performs. */
static void load_the_title(struct title_stats *record) {
    record->resource_index = TITLE_RESOURCE;
    record->copylock_arm_flag = image_word(WB_COPYLOCK_ARM_FLAG);
    record->load_result = load_resource_by_index(game_image, TITLE_RESOURCE,
                                                 WB_RESOURCE_LOAD_BUFFER);
    read_rad_header(&record->packed_bytes, &record->unpacked_bytes);
}

/* SUPERVISOR: the boot's two clears, the depack, the palette — and the photograph.
 *
 * THE CANONICAL COMPOSITION IS ../src/boot.c's `boot_title_screen` ($e512..$e550, batch 44 phase C),
 * which this function deliberately MIRRORS rather than calls. It departs from it in exactly the
 * three ways README.md §13 declares: the Copylock is not armed, the load runs in USER mode, and the
 * sound request at $e546 is not made. So a change to the boot's ORDER or OPERANDS belongs in that
 * function first, and here only to keep the mirror true.
 *
 * THE PICTURE IS READ WHERE THE SHIFTER IS POINTED, which is M2's rule and not a restatement of
 * where the depack was aimed. This build's `publish_screen_base` put WB_SCREEN_LOW on the bus, so that is
 * what a display shows and that is what is compared; whether the depack's own arithmetic lands
 * there is a SEPARATE claim, carried by `depack_dest` and `unpacked_bytes` and asserted by
 * smoke.py. A capture taken at `depack_dest + prefix` would make those two agree by construction. */
static void draw_the_title(struct title_stats *record) {
    clear_the_palette_and_screens();            /* $e4ea, $e4ee */

    record->depack_dest = WB_TITLE_DEPACK_DEST;
    record->depack_result = rad_depack(game_image, WB_RESOURCE_LOAD_BUFFER, WB_TITLE_DEPACK_DEST);
    (void)set_palette(game_image, WB_TITLE_PALETTE_SRC);

    /* THE PALETTE'S PLUMBING, CHECKED SEPARATELY FROM THE DIFFERENTIAL — the same split
     * `publish_staged_pens` makes for M2's control: this asks only whether the sixteen words the
     * depacked prefix holds are the sixteen the chip holds, so a divergence against the SHIPPED
     * binary's pens is about the picture and not about the shim's wiring. Nothing raises a pen
     * after `set_palette` in this slice, so no register is overridden. */
    record->pens_readback_failed = photograph_the_screen(WB_SCREEN_LOW, WB_TITLE_PALETTE_SRC,
                                                         NO_OVERRIDDEN_PEN, 0,
                                                         &record->captured_at,
                                                         &record->shifter_base);
}

#endif /* SMOKE_TITLE */

#if defined(SMOKE_BOOT) || defined(SMOKE_OWNPLAY)
/* ---- the boot's FIRE GATE, and the two waits that make it ---------------------------------------
 *
 * `$e552` / `$e5aa` / `$e4d6`: `clr.b WB_JOY1_STATE`, then `tst.b / bpl` until the IKBD handler
 * makes the byte negative and `tst.b / bmi` until it is positive again. Shared by the BOOT build
 * and the OWN-ENTRY build, which crosses more of them than the boot has — the ESC ending's ladder
 * walks the prompt's gate and then the boot's two again.
 *
 * ONE HALF PER FUNCTION, SO THAT EACH HAS ITS OWN ADDRESS. The record reports both, smoke.py
 * breakpoints them, and the poke it makes there is the joystick byte the IKBD would have filed —
 * which is exactly what `original.py`'s `boot_script` does to the shipped binary at $e556 and $e55c.
 *
 * BOUNDED IN THE HEADLESS BUILDS AND GENUINELY UNCAPPED IN THE PLAY ONE, which is `M2_FRAME_LIMIT`'s
 * split and is made the same way. Headless, the bound has to be shorter than `--run-vbls` or an
 * undriven run reports "no record", which says nothing about WHICH half of the gate was never
 * answered. With a person at the stick there is nothing to bound: the original's waits are
 * `bpl.s`/`bmi.s` with no counter at all, and a gate that gave up would drop the player into the
 * credits on its own.
 *
 * A HUGE COUNTER IS NOT "UNCAPPED", AND THE ARITHMETIC SAYS SO: `0xffffffff` spins of a
 * two-instruction loop is about ninety minutes on an 8 MHz 68000, which a title screen left up over
 * a lunch break really reaches. So the play build has NO COUNTER — `FIRE_SPIN_DECL` declares
 * nothing and `FIRE_GAVE_UP` folds to 0 — and the two builds still share ONE statement of the loop,
 * which is what the macro is for. The declaration goes with the test so the headless build has no
 * unused variable and the play build has no variable at all.
 *
 * `volatile`, because the byte is written by an interrupt (or by the debugger) and nothing the loop
 * body does can change it — README.md's bug 1, one file over from the comment about it. THE TWO
 * HALVES DIFFER ONLY IN `WAITED_FOR`, so the body — and the `volatile` that fixed bug 1 — is written
 * ONCE and the macro stamps out the two DISTINCT symbols the record has to report separately.
 *
 * THE COUNTERS ARE FILE-STATIC AND NOT A RECORD'S, because two builds with two different records
 * cross these gates and a gate that wrote into one of them could not be shared. Each build copies
 * them into its own record on the way out. */
#ifdef SMOKE_PLAY
#define FIRE_SPIN_DECL
#define FIRE_GAVE_UP     0
#else
#define FIRE_SPIN_DECL   uint32_t spins = SPINS_LONG;
#define FIRE_GAVE_UP     (--spins == 0u)
#endif

#define FIRE_WAIT(name, waited_for)                                                     \
    static __attribute__((noinline)) int name(void) {                                   \
        volatile uint8_t *fire = (volatile uint8_t *)(game_image + WB_JOY1_STATE);      \
        FIRE_SPIN_DECL                                                                  \
                                                                                        \
        while (!(waited_for))                                                           \
            if (FIRE_GAVE_UP)                                                           \
                return 0;                                                               \
        return 1;                                                                       \
    }

FIRE_WAIT(wait_fire_pressed, (*fire & FIRE_DOWN_BIT) != 0u)
FIRE_WAIT(wait_fire_released, (*fire & FIRE_DOWN_BIT) == 0u)

static uint32_t fire_gates_crossed;
static uint32_t fire_waits_timed_out;
static uint32_t fire_wait_timed_out_pc;   /* ...and WHICH half that was, or 0 if none ran out */

/* The five gate fields BOTH records carry, filled from the counters above.
 *
 * A MACRO AND NOT A NESTED STRUCT, which is a constraint from the other shore rather than a taste:
 * `smoke.py`'s `assert_the_record_matches_the_c` pins each record's field ORDER by scraping
 * `uint32_t <name>;` lines out of this file, and a `struct fire_gate_report gates;` member would
 * simply vanish from that scrape — the check would then pass while five longwords went unnamed. So
 * the records stay flat and the ASSIGNMENT is what is written once. */
#define PUBLISH_FIRE_GATES(record)                                              \
    do {                                                                        \
        (record).fire_press_pc = (uint32_t)(uintptr_t)&wait_fire_pressed;       \
        (record).fire_release_pc = (uint32_t)(uintptr_t)&wait_fire_released;    \
        (record).fire_gates_crossed = fire_gates_crossed;                       \
        (record).fire_waits_timed_out = fire_waits_timed_out;                   \
        (record).fire_wait_timed_out_pc = fire_wait_timed_out_pc;               \
    } while (0)

/* THE EIGHT STAGE PINS BOTH RECORDS CARRY, read out of the image in ONE place.
 *
 * `take_the_span` reads them at the boot's `$f8b4`-equivalent instant and `take_the_own_pins` at the
 * ladder's exit; through batch 44 phase E each spelled all eight out, which is eight chances for one
 * build's reading to drift from the other's while both stay green — the two are compared against the
 * SAME `original.py dump` fields. A MACRO and not a function or a nested struct, for
 * `PUBLISH_FIRE_GATES`' two reasons directly above: two builds with two different record types
 * cannot share a function that writes into one, and a nested member would vanish from smoke.py's
 * `uint32_t <name>;` field-order scrape.
 *
 * THE INTERRUPT MASK IS THE CALLER'S, deliberately. Both callers hold one — `vbl_handler` writes the
 * image, so pins read across a vblank could describe two moments — but the boot build's mask also
 * has to cover half a megabyte of `memcpy` after these reads, and a macro that took the mask would
 * either leave that copy outside it or hide a second one inside. What is shared is the eight reads;
 * WHAT MOMENT they are taken at stays where each build's own comment argues it. */
#define READ_THE_STAGE_PINS(record)                                                     \
    do {                                                                                \
        (record).stage_map_ptr = image_long(WB_STAGE_MAP_PTR);                          \
        (record).stage_start_ptr = image_long(WB_STAGE_START_PTR);                      \
        (record).resource_signature = game_image[WB_RESOURCE_HEADER];                   \
        (record).stage_number = image_word(WB_STAGE_NUMBER);                            \
        (record).level_seq_index = image_word(WB_LEVEL_SEQ_INDEX);                      \
        (record).stage_second_load_flag = game_image[WB_STAGE_SECOND_LOAD_FLAG];        \
        (record).stage_side_flag = image_word(WB_STAGE_SIDE_FLAG);                      \
        (record).life_restart_entry_c26 = image_word(WB_LIFE_RESTART_ENTRY_C26);        \
    } while (0)

static int fire_gate(void) {
    game_image[WB_JOY1_STATE] = FIRE_NONE;
    if (!wait_fire_pressed())
        fire_wait_timed_out_pc = (uint32_t)(uintptr_t)&wait_fire_pressed;
    else if (!wait_fire_released())
        fire_wait_timed_out_pc = (uint32_t)(uintptr_t)&wait_fire_released;
    else {
        fire_gates_crossed++;
        return 1;
    }
    fire_waits_timed_out++;
    return 0;
}

#endif

/* ---- the BOOT build's record, its two waits, and the recomputed span ----------------------------
 *
 * A FOURTH RECORD FOR THE FOURTH BUILD, for the reason M2 got a second one and the title build a
 * third: smoke.py checks each record's size against its own format string, so one record that grew
 * per build mode would make every other mode's version check fire. Four records, four magics, four
 * readers, and none can silently misread another's bytes. */
#ifdef SMOKE_BOOT
#define BOOT_MAGIC 0x57424134u      /* 'WBA4' */

static const char BOOT_FILE[] = "BOOT.BIN";
/* The recomputed span. Named for what it is rather than for the mode: `WB.IMG` is what GEMDOS hands
 * this program on the way IN, and this is what the program computed on the way out. */
static const char BOOT_IMAGE_FILE[] = "BOOT.IMG";

struct boot_stats {
    uint32_t magic;
    uint32_t bytes;                 /* sizeof(struct boot_stats) — the version check */
    uint32_t image_base;
    /* THE THREE SLICES' OWN REPORTS, each one of ../include/wonderboy.h's WB_LOAD_* codes or
     * BOOT_SLICE_NOT_RUN. Two of them must be WB_LOAD_COPYLOCK_RAN, because the title slice and the
     * stage slice's SPRITES.CRU load are the two the original arms. */
    uint32_t title_result;
    uint32_t credits_result;
    uint32_t stage_result;
    /* WHERE THE TWO FIRE WAITS ARE, so smoke.py can aim its pokes at the addresses the BINARY
     * reports about itself rather than at a symbol read out of a possibly-stale ELF — `capture_pc`'s
     * rule, and the reason M3's first pass exists. Each is entered twice: once for the title gate
     * and once for the credits gate. */
    uint32_t fire_press_pc;
    uint32_t fire_release_pc;
    uint32_t fire_gates_crossed;    /* both halves answered */
    uint32_t fire_waits_timed_out;  /* ...and a half that spun out its bound instead */
    /* WHICH HALF THE LAST TIMEOUT WAS IN — one of the two PCs above, or 0 if none ran out. The
     * banner says the waits are separate functions so a timeout can name itself; a shared counter
     * alone could not, and "0 of 2 gates, 1 timed out" reads the same whether the press poke missed
     * or the release one did.
     *
     * IT IS THE LAST ONE AND NOT THE ONLY ONE, which matters because the own-entry build crosses up
     * to FIVE gates and can therefore run more than one of them out. `fire_gate` overwrites this on
     * every timeout, so read it WITH `fire_waits_timed_out` beside it (how many) and
     * `fire_gates_crossed` (how many were answered): the pair says whether this address is the
     * whole story or the last chapter of it. On the boot build, whose chain has two gates and stops
     * at the first refusal, the two readings coincide.
     *
     * It is the undriven pass's own strongest row either way: with nothing injected the run must
     * stop at the FIRST half of the FIRST gate, one timeout, zero crossed, and this address must be
     * `fire_press_pc` and no other. */
    uint32_t fire_wait_timed_out_pc;
    /* Each picture's .RAD header as read back out of the load buffer AFTER its own load — what says
     * the file arrived, since a refused load leaves the buffer as it found it. */
    uint32_t title_packed;
    uint32_t title_unpacked;
    uint32_t credits_packed;
    uint32_t credits_unpacked;
    /* WB_COPYLOCK_ARM_FLAG at the end of the chain. `load_resource_by_index` clears it on the armed
     * arm, so a chain that ran to the end must leave it clear; a chain that stopped on a refused
     * load it had armed leaves it standing (../src/boot.c's `load_or_stop`). */
    uint32_t copylock_arm_flag;
    /* Which of the sixteen pens does not read back as the word the credits slice put there. Pen
     * WB_CREDITS_PROMPT_PEN is expected to hold WB_CREDITS_PROMPT_COLOUR and the other fifteen the
     * depacked prefix's own words — which is the ONE surface that can see `$e5a2`'s write at all
     * (../STATUS.md batch 44 phase C, §4's C3: the oracle drops it). */
    uint32_t pens_readback_failed;
    uint32_t captured_at;           /* where the 32000 photographed bytes were read from */
    uint32_t screen_base_published;
    uint32_t shifter_base;          /* $ffff8201/8203 READ BACK, at the instant of the photograph */
    /* THE PINS FROM THE INSIDE, at the instant `boot_load_stage` returns. These are M2's own seven
     * (atari/original.py's `check_pins`) asked of the RECOMPUTED image instead of the measured one:
     * state the shipped `.PRG` does not carry and only a completed chain leaves. */
    uint32_t stage_map_ptr;
    uint32_t stage_start_ptr;
    uint32_t resource_signature;
    uint32_t stage_number;
    uint32_t level_seq_index;
    uint32_t stage_second_load_flag;
    uint32_t stage_side_flag;
    /* ...and the word `$e6ec`'s `clr.w` takes down, which is what makes the sprite load one-shot:
     * a life lost re-enters the stage with this raised and the SPRITES.CRU load — and the
     * protection with it — is suppressed. */
    uint32_t life_restart_entry_c26;
    /* The span written to BOOT.IMG, and the shim's own vblank count at the two instants that bound
     * the chain — which is what says how much of `vbl_handler`'s work is inside the picture. */
    uint32_t span_bytes;
    uint32_t vbl_ticks_at_span;
    uint32_t vbl_ticks_at_exit;
};

/* THE SPAN IS COPIED ASIDE RATHER THAN WRITTEN WHERE IT IS TAKEN, and the banner argues it: the
 * write is GEMDOS and so waits for user mode, and `vbl_handler` runs in between. Half a megabyte of
 * .bss against a machine `smoke.py` boots with --memsize 4. */
static uint8_t boot_span[BOOT_SPAN_BYTES];

/* The credits picture, photographed at the boot's OWN anchor — `$e5aa`, the instruction after
 * `boot_credits_screen`'s last and before the gate. Read where the SHIFTER IS POINTED, which is M2's
 * rule: `publish_screen_base` put WB_SCREEN_LOW on the bus and `copy_screen` brought the picture
 * down onto it, so that is the buffer a display shows and that is the buffer compared. */
static void capture_the_credits(struct boot_stats *record) {
    /* THE PROMPT PEN IS EXPECTED TO DIFFER FROM THE PICTURE'S OWN WORD, and that is the check rather
     * than an exception to it: `$e5a2` raises WB_CREDITS_PROMPT_PEN to WB_CREDITS_PROMPT_COLOUR
     * after `set_palette` has run, so the chip must hold the depacked prefix's fifteen words and
     * that one. It is the ONE surface that can see that instruction at all — ../STATUS.md batch 44
     * phase C §4's C3 records it SURVIVING every host differential, because the oracle drops a write
     * to a register off the loaded image. */
    record->pens_readback_failed = photograph_the_screen(WB_SCREEN_LOW, WB_CREDITS_PALETTE_SRC,
                                                         WB_CREDITS_PROMPT_PEN,
                                                         WB_CREDITS_PROMPT_COLOUR,
                                                         &record->captured_at,
                                                         &record->shifter_base);
}

/* The span, and the seven pins, taken at the instant `boot_load_stage` returns — the
 * `$f8b4`-equivalent, which is where `atari/original.py dump` takes the image this one is compared
 * against.
 *
 * INTERRUPTS ARE MASKED FOR THE COPY, and not for tidiness: `vbl_handler` is the reconstruction's
 * own and it writes the image — the music tick, the idle countdown, its own counter — so a vblank
 * landing inside half a megabyte of `memcpy` would leave a span that is two moments spliced. */
static void take_the_span(struct boot_stats *record) {
    unsigned short sr = wb_irq_disable();

    /* THE PINS ARE INSIDE THE SAME MASK AS THE COPY, and that is the whole point of the mask rather
     * than an extra. Every one of them is compared against `original.py dump`'s, which Hatari takes
     * atomically at `$f8b4`; read outside the mask they could describe a moment `vbl_handler` had
     * already moved the span past, and a pin disagreeing with the span it describes would be an
     * INTERMITTENT red on a correct build — the shape `sample_the_two_clocks` one block over exists
     * to not have. */
    record->vbl_ticks_at_span = shim_vbl_ticks;
    READ_THE_STAGE_PINS(*record);
    memcpy(boot_span, game_image + BOOT_SPAN_AT, BOOT_SPAN_BYTES);
    wb_irq_restore(sr);
    record->span_bytes = BOOT_SPAN_BYTES;
}

/* THE RECORD THE CHAIN'S BOOT-ONLY HOOKS FILL. A file-static rather than a parameter threaded
 * through the shared chain below, for `fire_gates_crossed`'s reason one block up: the chain is
 * written ONCE and two builds with two DIFFERENT record types run it, so an argument typed as
 * either could not be shared. Set by `run_the_boot` immediately before the chain, read by the two
 * hooks, and by nothing else. */
static struct boot_stats *the_boot_record;

#endif /* SMOKE_BOOT */


/* ---- THE COMPOSED CHAIN, WRITTEN ONCE FOR THE TWO BUILDS THAT RUN IT ---------------------------
 *
 * `title, gate, credits, gate, stage` is ../src/boot.c's own order, and it is stated here and
 * nowhere else. The BOOT build runs it to measure the image it computes; the OWN-ENTRY build runs
 * it to reach a playable stage, and runs it AGAIN on every ESC. What differs between them is
 * everything BESIDE the chain — the boot's per-picture read-backs and its span, the ladder's legs
 * and endings — and that is what the two hooks and the two drivers carry.
 *
 * THE THREE REPORTS ARE FILE-STATIC AND EACH BUILD PUBLISHES THEM, which is `PUBLISH_FIRE_GATES`'
 * arrangement one block up and for the identical reason. They start at BOOT_SLICE_NOT_RUN rather
 * than at zero: WB_LOAD_OK IS zero, so a chain that stopped at its first gate would otherwise
 * report clean loads it never made. */
#ifdef SMOKE_BOOT_CHAIN
static uint32_t chain_title_result = BOOT_SLICE_NOT_RUN;
static uint32_t chain_credits_result = BOOT_SLICE_NOT_RUN;
static uint32_t chain_stage_result = BOOT_SLICE_NOT_RUN;

#define PUBLISH_CHAIN_RESULTS(record)                   \
    do {                                                \
        (record).title_result = chain_title_result;     \
        (record).credits_result = chain_credits_result; \
        (record).stage_result = chain_stage_result;     \
    } while (0)

/* What the BOOT build does BETWEEN the chain's slices, and what the own-entry build does not. Each
 * picture's .RAD header has to be read back before the NEXT load overwrites the buffer it sits in,
 * and the credits screen has to be photographed at the boot's own `$e5aa` anchor — so neither can
 * be lifted out of the chain and done afterwards. Empty in the own-entry build, which measures no
 * picture and keeps no span. */
#ifdef SMOKE_BOOT
static void after_the_title_slice(void) {
    read_rad_header(&the_boot_record->title_packed, &the_boot_record->title_unpacked);
}

static void after_the_credits_slice(void) {
    read_rad_header(&the_boot_record->credits_packed, &the_boot_record->credits_unpacked);
    capture_the_credits(the_boot_record);
}
#else
static void after_the_title_slice(void) { }
static void after_the_credits_slice(void) { }
#endif

/* $e4e6..$e510's reconstructed half, IN THE BOOT'S OWN ORDER: the base publish that is
 * `video_set_lowres_50hz`'s ($f906) first, then the palette clear at $e4ea, then the screens' at
 * $e4ee.
 *
 * THE ORDER IS LOAD-BEARING ON THE ESC RESTART AND ONLY THERE, which is exactly why it could drift
 * unnoticed. `boot_prompt_screen` leaves the shifter on WB_SCREEN_HIGH with the data-disk picture
 * in it; publishing the base FIRST takes the display off that buffer before `clear_both_screens`
 * wipes it, which is what the boot does. On the way IN the shifter is already where `main` put it
 * and either order looks the same. */
static void chain_prologue(void) {
    publish_screen_base();                      /* $f906's own two immediates: base := WB_SCREEN_LOW */
    clear_the_palette_and_screens();            /* $e4ea, $e4ee */
}

/* $e5ba..$f8b4, and the chain's only stage load: the boot's first one and every one of the ladder's
 * reloads are the same call, so a run that reloaded four times has taken this arm five times. */
static int run_the_stage_slice(void) {
    chain_stage_result = boot_load_stage(game_image);
    return chain_stage_result != WB_LOAD_DISK_ERROR;
}

/* $e512..$f8b4: the chain, STOPPING WHERE THE BOOT WOULD STOP. A refused load leaves the original
 * sitting in `load_resource_by_index`'s interactive retry, so ../src/boot.c's slices return
 * WB_LOAD_DISK_ERROR rather than inflating a buffer the file never arrived in; this honours the
 * same contract one level up, and an unanswered fire gate stops it for the same reason — the
 * original would still be waiting. Every stop is reported, so a short run is a red with a reason
 * rather than a missing record. */
static int run_the_boot_chain(void) {
    chain_title_result = boot_title_screen(game_image);
    after_the_title_slice();
    if (chain_title_result == WB_LOAD_DISK_ERROR || !fire_gate())
        return 0;

    /* BOOT_FAULT_SKIP_CREDITS is the boot build's mis-run control (build.sh bootfault), and it is
     * `novbl`'s shape in the middle of the chain: one call suppressed and nothing else — the same
     * two gates, the same other two slices, the same record, the same span written. The hook still
     * runs, so the buffer it reports is the TITLE's file left over, which is the control saying out
     * loud that no credits file was asked for. */
#ifndef BOOT_FAULT_SKIP_CREDITS
    chain_credits_result = boot_credits_screen(game_image);
#endif
    after_the_credits_slice();
    if (chain_credits_result == WB_LOAD_DISK_ERROR || !fire_gate())
        return 0;

    return run_the_stage_slice();
}
#endif /* SMOKE_BOOT_CHAIN */


#ifdef SMOKE_BOOT
/* THE BOOT BUILD'S DRIVER: the prologue, the chain, and the span the chain's end is about. */
static void run_the_boot(struct boot_stats *record) {
    the_boot_record = record;
    chain_prologue();
    if (run_the_boot_chain())
        take_the_span(record);
}

#endif /* SMOKE_BOOT */

/* ---- THE OWN-ENTRY BUILD: the boot loads the stage, and every ending comes back to it -----------
 *
 * `-DSMOKE_OWNPLAY` is the fifth build here and the first that is a GAME rather than a measurement
 * of one. It stages M1's image — the shipped program plus gen_image.py's named seeds, not one byte
 * of the original's measured RAM — runs ../src/boot.c's four composed slices, and then enters
 * `game_main_loop`. Where the frame builds are `jmp`ed into a stage the DUMP already holds, this one
 * loads its own; where `SMOKE_PLAY` ends when a `game_key_actions` ending fires, this one WIRES THE
 * ENDINGS to the addresses the original's own `jmp`s name:
 *
 *   WB_KEY_ACTIONS_ROUND_END   `jmp $e5ba.l` -> boot_load_stage, and back into the frame loop
 *   WB_KEY_ACTIONS_LEVEL_SKIP  `jmp $e5ba.l` -> the same
 *   WB_LOOP_EXIT_RELOAD        `jmp $e5ba.l` -> the same again, and it is THE PLAYER'S: a life
 *                              spent ($c20) or the collision map's triple pop ($1626)
 *   WB_KEY_ACTIONS_QUIT        `jmp $e494.l` -> boot_prompt_screen, its fire gate, and then the
 *                              FALL-THROUGH the original takes at $e4e4 into $e4e6 — so ESC walks
 *                              the whole chain again: title, gate, credits, gate, stage
 *   WB_LOOP_EXIT_DATA_DISK     `jmp $e494.l` -> the same ladder, and it is the PLAYER'S again: the
 *                              game-over box expiring ($bdc) or slot 61's message sequence ending
 *                              ($700e). NO MUSIC FADE ON THIS ONE and none is wanted: the fade is
 *                              `jsr 84(a0)` at $594, INSIDE game_key_actions' ESC arm and ported
 *                              there (../src/game.c), and the original's $bd8 pops and `jmp`s with
 *                              nothing in between
 *
 * FIVE ENDINGS AND NOT THREE, which is batch 44 phase E's gate: `game_main_loop` used to discard the
 * behaviour pass's report, so on this build a player's death kept the frame loop turning where the
 * original had left it. ../include/game.h carries the seven-`jmp` census the two new codes come
 * from.
 *
 * WHAT IT SHARES AND WHAT IT DOES NOT. It compiles -DSMOKE_M2 for `run_frames`, `capture_the_frame`
 * and the M2 record, so the frame loop, its watchdog and M3's poke anchor are the SAME code the
 * frame builds run and not a second copy. It does NOT stage `PENS.IMG`: the palette is the boot's
 * own product here, put on the chip by the title, credits and stage slices' `set_palette` calls,
 * which is exactly the thing a staged palette stood in for.
 *
 * THE DEVIATIONS ARE THE BOOT BUILD'S, and atari/README.md §14 argues each: the prologue at
 * $e4e6..$e510 is the shim's, the loads run in supervisor, the Copylock is armed but not executed,
 * the two disks are one GEMDOS volume, and the fire gates are bounded spins the debugger drives
 * headless. What this build ADDS to that list is one thing and it is the retry policy below.
 *
 * THE RETRY POLICY, WHICH IS TO STOP. `boot_load_stage` returning WB_LOAD_DISK_ERROR leaves TWO
 * residues neither of which is recoverable from the other (../src/boot.c's `load_or_stop`):
 * WB_LEVEL_SEQ_INDEX has already been stepped past the row the run consumed, and WB_COPYLOCK_ARM_
 * FLAG may be left armed. The original never has that problem — it retries the SAME load in place,
 * inside `load_resource_by_index`'s interactive error arm, which this port declines to model — so a
 * caller that retried by CALLING THE SLICE AGAIN would skip a sequence row and re-arm a guard it
 * did not mean to. This ladder therefore stops, records WHERE it stopped and WHAT the slice
 * reported, and hands the machine back. On this build's GEMDOS substitution a refusal means a file
 * the drive does not carry, so stopping with the code in the record is the honest answer: the run
 * says "the overlay for stage 3 is not on this volume" rather than silently replaying stage 2.
 */
#ifdef SMOKE_OWNPLAY
#define OWN_MAGIC 0x57424135u       /* 'WBA5' */

static const char OWN_FILE[] = "OWN.BIN";

/* WHY THE LADDER STOPPED. Out of band from every WB_LOAD_* and from WB_KEY_ACTIONS_*, because those
 * are what the FIELDS beside it carry: this says which of the ladder's own five exits was taken. */
#define OWN_STOP_BOOT          1u   /* the chain never reached its first stage */
#define OWN_STOP_FRAME_LIMIT   2u   /* the frame loop ran out its own bound — the headless norm */
#define OWN_STOP_RELOAD        3u   /* an ending asked for the next stage and the load was refused */
#define OWN_STOP_RESTART       4u   /* ESC's ladder was refused (the prompt, or the chain after it) */
#define OWN_STOP_LEG_LIMIT     5u   /* the run took more endings than OWN_LEG_LIMIT allows */

/* HOW MANY TIMES THE FRAME LOOP MAY BE ENTERED, and it is `M2_FRAME_LIMIT`'s split made again one
 * level up: a headless run needs a bound so a ladder that cycles reports rather than hangs, and an
 * interactive session must have none — a player who finishes twenty rounds must get twenty stages.
 * Four is what the headless mode drives: one leg to the driven ending, one after the reload it
 * causes, and two of slack so a run that took an unexpected ending still reports the NEXT stop
 * rather than the limit. */
#ifdef SMOKE_PLAY
#define OWN_LEG_LIMIT 0xffffffffu
#else
#define OWN_LEG_LIMIT 4u
#endif

struct own_stats {
    uint32_t magic;
    uint32_t bytes;                 /* sizeof(struct own_stats) — the version check */
    uint32_t image_base;
    /* THE FOUR SLICES' OWN REPORTS, each a WB_LOAD_* code or BOOT_SLICE_NOT_RUN. `prompt_result`
     * stays BOOT_SLICE_NOT_RUN on any run in which ESC was never taken, which is what tells an
     * undriven run apart from a restarted one. `stage_result` is the LAST stage load's, because
     * every reload goes through the same slice and the interesting one is the one that stopped. */
    uint32_t prompt_result;
    uint32_t title_result;
    uint32_t credits_result;
    uint32_t stage_result;
    /* THE PROMPT PICTURE, PHOTOGRAPHED — the three fields `capture_the_prompt` fills, and the ONLY
     * surface in this directory that can see `boot_prompt_screen`'s screen-base publish happen.
     *
     * `prompt_captured_at` is the image address the 32000 bytes were read from, reported BY the
     * photograph rather than restated by the caller (`photograph_the_screen`'s own rule), and it is
     * 0 on every run in which ESC was never taken — which is what says PROMPT.BIN is absent because
     * no prompt was drawn rather than because a write failed. `prompt_shifter_base` is
     * $ffff8201/8203 as they READ at that instant: the prompt is the one slice of the four that
     * publishes a base, and until this rung both the write's deletion and its two bytes swapped
     * SURVIVED every surface this project had (../STATUS.md batch 44 phase E §4, P3 and P5).
     * `prompt_pens_readback_failed` is one bit per colour register that did not read back as
     * DATADISK.RAD's own palette row left it.
     *
     * THE LAST RESTART'S, on a run that took more than one. The headless passes take exactly one
     * (`restarts` is asserted per pass), and a ladder that restarted twice would leave the second
     * picture here — which is the right answer for a field describing where the run got to. */
    uint32_t prompt_captured_at;
    /* THE BASE AS THE ENDING LEFT IT, read one instruction before `boot_prompt_screen` is called —
     * and the field without which `prompt_shifter_base` below is a row that cannot fail.
     *
     * MEASURED, AND IT IS THE REASON THIS FIELD EXISTS. `flip_screen` publishes the buffer that has
     * just become the front one, so the base at an ending is decided by how many frames the leg
     * ran; on an EVEN count it is already WB_SCREEN_HIGH, which is the very buffer the prompt
     * publishes. A run driven at such a frame reports the right answer whether or not `$e498`/`$e4a0`
     * ran at all — the phase-E mutant P3 (the publish deleted) was applied and SURVIVED exactly that
     * way. So the pass asserts that the base MOVED, and this is where it moved from. */
    uint32_t prompt_base_before;
    uint32_t prompt_shifter_base;
    uint32_t prompt_pens_readback_failed;
    /* The shared fire gate's five (PUBLISH_FIRE_GATES). Flat and in this order for
     * smoke.py's field-order scrape — see that macro. */
    uint32_t fire_press_pc;
    uint32_t fire_release_pc;
    uint32_t fire_gates_crossed;
    uint32_t fire_waits_timed_out;
    uint32_t fire_wait_timed_out_pc;
    /* THE a5 THE FRAME LOOP WAS ENTERED WITH, and the field that says this build measured nothing to
     * get it: M2_ENTRY_UNWIND is WB_TILE_INDEX_TABLE here, which is `bg_build_buffer`'s own `lea`
     * operand, and the SMOKE_M2 banner has the census. Reported so smoke.py can cross-check it
     * against `build/ORIGREGS.txt`'s measured A5 when a dump happens to be present. */
    uint32_t entry_unwind;
    /* THE LADDER, counted. `legs_run` is how many times the frame loop was entered — one more than
     * the number of endings taken, on a run that ends by exhausting a leg's frame bound. */
    uint32_t legs_run;
    uint32_t reloads;               /* every ending whose `jmp` goes to $e5ba */
    uint32_t restarts;              /* ...and every one that goes to $e494, chain and all */
    /* THE LAST ENDING THAT LEFT THE FRAME LOOP — not the last leg's return, which is a different
     * question with a different answer. A driven run takes its ending on leg one and then runs leg
     * two to its own frame bound, so the last leg comes back WB_KEY_ACTIONS_RETURNED and a field
     * that reported it would say "no ending" about a run that took one. Stays
     * WB_KEY_ACTIONS_RETURNED while no ending has ever fired, which is the undriven answer. */
    uint32_t last_ending;
    uint32_t stopped_at;            /* one of OWN_STOP_* */
    uint32_t frames_total;          /* summed over every leg */
    /* ...AND THE SHIM'S OWN VBLANKS SPENT INSIDE THOSE LEGS, which is a different number from
     * `vbl_ticks_at_exit` and is the one RB_VBL_TICKING is graded on here. See the accumulation in
     * `run_the_own_entry` for why the exit reading cannot carry that bit on this build. */
    uint32_t frame_loop_vbl_ticks;
    /* THE PINS, READ AT THE EXIT rather than at the first stage load — which is the whole point of
     * this build. `stage_number` and `level_seq_index` are what a driven reload MOVES: the boot's
     * own first stage leaves them at the sequence's first row, and an ending that reloads steps
     * both. The boot build reports the same seven at `$f8b4` and cannot report a second set. */
    uint32_t stage_map_ptr;
    uint32_t stage_start_ptr;
    uint32_t resource_signature;
    uint32_t stage_number;
    uint32_t level_seq_index;
    uint32_t stage_second_load_flag;
    uint32_t stage_side_flag;
    uint32_t life_restart_entry_c26;
    /* THE START RECORD'S OWN ENTRY POSITION, out of the overlay the last stage load inflated — and
     * it is what says WHICH FILE crossed the seam. Every stage's overlay inflates to the same
     * WB_OVERLAY_DEPACK_DEST, so `stage_map_ptr` and `stage_start_ptr` are the same two numbers
     * whichever stage is loaded and cannot tell a reload from a repeat. These two words can: they
     * are `4(a1)`/`6(a1)`, the position `stage_load_window` copies into the followed actor, and they
     * are read as ONE longword because that is what the pair is. smoke.py inflates the shipped
     * OVALAY0N.RAD host-side and compares — and asserts the two rows' values DIFFER first, so the
     * comparison cannot pass by their happening to be equal. Read from the OVERLAY rather than from
     * WB_ACTOR_FOLLOWED_DEFAULT, because the frame loop moves the actor and not the file. */
    uint32_t stage_entry_follow;
    uint32_t copylock_arm_flag;
    uint32_t vbl_ticks_at_exit;
};

static const char PROMPT_FILE[] = "PROMPT.BIN";
static const char PROMPT_PENS_FILE[] = "PROMPTPN.BIN";

/* The data-disk prompt, photographed at the boot's OWN anchor — `$e4d6`, the `clr.b $877.w` that
 * opens the fire wait, which is the instruction AFTER `boot_prompt_screen`'s last (`jsr $f944.l` at
 * $e4d0) and before anything waits for a player. `original.py prompt` stops the SHIPPED binary at
 * that very PC after driving its own ESC ending, and `smoke.py ownplay` pass 4 compares the two.
 *
 * $e4d6 AND NOT $e4d4, and the listing is why: `jsr $f944.l` is six bytes, so $e4d4 is inside its
 * operand and no instruction begins there. $e4d6 is `WB_BOOT_PROMPT_END` — the same choice, one
 * slice over, that made `$e5aa` the credits anchor and `$e556` the title's.
 *
 * READ WHERE THE SHIFTER IS POINTED, which is M2's rule: this slice publishes WB_PROMPT_SCREEN_BASE
 * and then inflates DATADISK.RAD into that very buffer, so the buffer a display shows is the buffer
 * compared. That the publish really happened is a SEPARATE claim and `prompt_shifter_base` is what
 * carries it — read off the chip here, where it means something, because `teardown` puts TOS's own
 * base back and a read after that reports the desktop for ever. */
static void capture_the_prompt(struct own_stats *record) {
    record->prompt_pens_readback_failed =
        photograph_the_screen(WB_PROMPT_SCREEN_BASE, WB_PROMPT_PALETTE_SRC,
                              NO_OVERRIDDEN_PEN, 0,
                              &record->prompt_captured_at, &record->prompt_shifter_base);
}

/* ESC's ending, whole: $e494's picture, its fire gate, and the fall-through at $e4e4 into the boot
 * continuation. `chain_prologue` is made again because the original makes it again — $e4e6 is the
 * very instruction the wait falls into — and its base publish is what takes the shifter back off
 * WB_SCREEN_HIGH, where `boot_prompt_screen` pointed it, onto the buffer the title lands in, BEFORE
 * the screen clear wipes the picture that is still on the bus. */
static int own_restart(struct own_stats *record) {
    /* BEFORE THE SLICE, because what the next line's two `move.b`s do is only observable as a
     * CHANGE — see `prompt_base_before`. */
    record->prompt_base_before = read_the_shifter_base();
    record->prompt_result = boot_prompt_screen(game_image);
    if (record->prompt_result == WB_LOAD_DISK_ERROR)
        return 0;
    /* BEFORE THE GATE, because the gate is where a person looks at the picture: $e4d6 is the
     * instruction the slice falls into and the photograph is of the screen as `set_palette` leaves
     * it. A capture after the gate would be of the same pixels at a later moment on a good run and
     * of nothing at all on a run whose gate was never answered. */
    capture_the_prompt(record);
    if (!fire_gate())
        return 0;
    chain_prologue();
    return run_the_boot_chain();
}


static void take_the_own_pins(struct own_stats *record) {
    unsigned short sr = wb_irq_disable();

    /* MASKED, for `take_the_span`'s reason one build over: `vbl_handler` is the reconstruction's own
     * and it writes the image, so nine pins read across a vblank could describe two moments. */
    READ_THE_STAGE_PINS(*record);
    /* ...AND THE NINTH, WHICH IS THIS BUILD'S ALONE: which overlay is in memory. The boot build has
     * no reload to tell from a repeat, so the shared eight above are all it needs. */
    record->stage_entry_follow = image_long(WB_OVERLAY_DEPACK_DEST + WB_START_FOLLOW_X);
    wb_irq_restore(sr);
}

/* THE LADDER. Boot once, then run frames until an ending, act on it, and go round.
 *
 * `run_frames` is the frame builds' own and it already stops on any ending (`loop_ending !=
 * WB_KEY_ACTIONS_RETURNED`) — so what this adds is the SWITCH, which is the port's statement of the
 * five `jmp`s the frame loop stands in for: three `game_key_actions`' and two the behaviour pass
 * hands up from the player tier. WB_KEY_ACTIONS_RETURNED reaching the switch means the leg
 * ended on its own bound instead (the headless build's normal stop, and unreachable in the play
 * build, whose M2_FRAME_LIMIT is exhausted by nothing). */
static void run_the_own_entry(struct own_stats *record, struct m2_stats *frames) {
    uint32_t leg;

    chain_prologue();
    if (!run_the_boot_chain()) {
        record->stopped_at = OWN_STOP_BOOT;
        return;
    }
    for (leg = 0; leg < OWN_LEG_LIMIT; leg++) {
        /* THE FRAME LOOP'S OWN VBLANKS, SUMMED OVER THE LEGS AND NOT TAKEN AT THE EXIT. `shim_vbl_
         * ticks` at the end of this ladder counts the boot chain's several hundred as well —
         * measured, ~525 on the way in and as many again on every ESC — and RB_VBL_TICKING's floor
         * (`MIN_VBLANKS_PER_FRAME` per frame) is satisfied by those alone, whatever the frame loop
         * did. Bracketing each leg is what keeps the bit meaning liveness OF THE FRAME LOOP, which
         * is what it is named for. */
        uint32_t at_leg_entry = shim_vbl_ticks;

        record->frames_total += run_frames(frames);
        record->frame_loop_vbl_ticks += shim_vbl_ticks - at_leg_entry;
        record->legs_run++;
        /* ONLY A REAL ENDING IS RECORDED. `run_frames` also comes back on its own frame bound, and
         * a field that took every leg's answer would report WB_KEY_ACTIONS_RETURNED about a run
         * whose first leg ended on an ending and whose second ran out. */
        if (frames->loop_ending != WB_KEY_ACTIONS_RETURNED)
            record->last_ending = frames->loop_ending;
        switch (frames->loop_ending) {
        case WB_KEY_ACTIONS_ROUND_END:
        case WB_KEY_ACTIONS_LEVEL_SKIP:
        case WB_LOOP_EXIT_RELOAD:
            record->reloads++;
            if (!run_the_stage_slice()) {
                record->stopped_at = OWN_STOP_RELOAD;
                return;
            }
            break;
        case WB_KEY_ACTIONS_QUIT:
        case WB_LOOP_EXIT_DATA_DISK:
            record->restarts++;
            if (!own_restart(record)) {
                record->stopped_at = OWN_STOP_RESTART;
                return;
            }
            break;
        default:
            record->stopped_at = OWN_STOP_FRAME_LIMIT;
            return;
        }
    }
    record->stopped_at = OWN_STOP_LEG_LIMIT;
}

#endif /* SMOKE_OWNPLAY */



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

/* One reset, and WHAT THE CONTROLLER ANSWERED — discovered rather than assumed, for the reason
 * `await_ikbd_reply` gives.
 *
 * THE SCANCODE IS CLEARED BEFORE THE RESET IS SENT, and that clear is the fix for a HANG rather than
 * tidiness. `await_ikbd_reply` returns as soon as the byte is not IKBD_NOTHING_SAID, so whatever the
 * frame loop left in it is taken for the controller's answer — and the uncapped wait below is then
 * aimed at a byte the IKBD will never send. Measured by `smoke.py m3`'s first key-driven ending, and
 * isolated: poking the scancode ALONE, with no ending driven at all, hangs the run identically. */
static uint8_t reset_and_hear_back(void) {
    game_image[WB_KEY_LAST_SCANCODE] = IKBD_NOTHING_SAID;
    return ikbd_reset() ? await_ikbd_reply() : IKBD_NOTHING_SAID;
}

/* The `sched_wait8` pin, and it is a genuine spin rather than a byte already in place.
 *
 * The reply is waited for on the shim's own bounded clock first — that is what establishes that this
 * machine's IKBD answers at all. Only then is the byte cleared, a further reset sent, and
 * `sched_wait8` called: it cannot hang, because the reply that will end it is the reply the bounded
 * waits just observed. Without that half this would be an uncapped spin taken on faith.
 *
 * ...AND THE ANSWER IS ASKED FOR TWICE, because one reading can be a KEY. The bounded wait cannot
 * tell the controller's status byte from a scancode the ACIA delivers while it is waiting, and in an
 * interactive session that is not a corner case but the normal path: the player's ESC or N ENDS the
 * frame loop, and the RELEASE of the same key lands inside the ~300 ms the reset takes to answer. Two
 * resets that answer the same byte cannot both be that, because a press and a release carry different
 * codes and neither repeats. If they disagree the pin is simply NOT TAKEN — recorded through
 * RB_IKBD_REPLIED and `sched_wait_returned`, which is a measurement the run survives, where aiming
 * the uncapped wait at a key's code is a machine that never reaches its own dump. */
static int pin_sched_wait8(void) {
    uint8_t acknowledge = reset_and_hear_back();

    if (acknowledge != reset_and_hear_back())
        acknowledge = IKBD_NOTHING_SAID;
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
#ifdef SMOKE_TITLE
    struct title_stats title;
#endif
#ifdef SMOKE_BOOT
    struct boot_stats boot;
#endif
#ifdef SMOKE_OWNPLAY
    struct own_stats own;
#endif
    void *ssp;
#ifdef SMOKE_M2
    unsigned field;                 /* the anchor-table copy at the foot of this function */
#endif

    ZERO_RECORD(record);
#ifdef SMOKE_M2
    ZERO_RECORD(m2);
#endif
#ifdef SMOKE_TITLE
    ZERO_RECORD(title);
#endif
#ifdef SMOKE_BOOT
    ZERO_RECORD(boot);
#endif
#ifdef SMOKE_OWNPLAY
    ZERO_RECORD(own);
    /* THE CHAIN'S THREE SLICE REPORTS NEED NO SENTINEL HERE: they are file-static, they start at
     * BOOT_SLICE_NOT_RUN, and PUBLISH_CHAIN_RESULTS copies them in at the end (WB_LOAD_OK is 0, so a
     * zeroed record would otherwise claim clean loads a stopped chain never made). The PROMPT's is
     * this build's own — $e494 is an ENDING's slice and not the chain's — so it is set here, and it
     * staying at this value is the positive evidence that ESC was never taken.
     *
     * `last_ending` is left at the zeroing's 0, which IS WB_KEY_ACTIONS_RETURNED — the right answer
     * for a run in which no ending ever fired, and the reason it needs no sentinel of its own. */
    own.prompt_result = BOOT_SLICE_NOT_RUN;
#endif

    game_image = (uint8_t *)(((uintptr_t)image_storage + (IMAGE_ALIGN - 1u))
                             & ~(uintptr_t)(IMAGE_ALIGN - 1u));

    /* USER MODE: the staging read, and TOS's own screen, taken before anything moves. */
    if (!stage_image())
        return 1;
#if defined(SMOKE_M2) && !defined(SMOKE_OWNPLAY)
    /* THE OWN-ENTRY BUILD STAGES NO PALETTE, and that is the point of it rather than an omission:
     * `PENS.IMG` is the ORIGINAL's post-boot shifter, staged because the chain that produces it was
     * unported. This build runs that chain, so its three `set_palette` calls put the pens up. */
    if (!stage_file(STAGED_PENS_FILE, (long)sizeof(staged_pens), staged_pens))
        return 1;
#endif
#ifdef SMOKE_TITLE
    /* THE RECONSTRUCTION'S OWN FILE READ, and it happens HERE — in user mode, with the rest of this
     * file's GEMDOS I/O — rather than beside the depack it feeds. The SMOKE_TITLE banner argues it. */
    load_the_title(&title);
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
#ifndef SMOKE_OWNPLAY
    publish_staged_pens(&m2);
#endif
    arm_the_flash();
    /* READ BACK OUT OF THE IMAGE, so the field witnesses the seed landing rather than repeating the
     * constant the build was given — and so the unseeded builds report the $0000 that is the whole
     * reason the flash arms are unreachable. */
    m2.flash_timer_at_entry = image_word(WB_FLASH_TIMER);
    m2.capture_pc = (uint32_t)(uintptr_t)&capture_the_frame;
    m2.fault_pen = FAULTED_PEN;
    /* THE LOOP'S OWN BOUND, not a second spelling of it. This was `M2_LAST_ANCHOR` until the play
     * build made the two differ. */
    m2.frames_requested = M2_FRAME_LIMIT;
#ifdef SMOKE_OWNPLAY
    /* THE WHOLE GAME: the boot chain, the frame loop, and every ending wired back into the chain.
     * `frames_run` is the SUM over the ladder's legs, so it can exceed `frames_requested` — which is
     * per leg — and smoke.py's own-entry mode reads the ladder's own record for the shape. */
    run_the_own_entry(&own, &m2);
    /* THE PINS AT THE EXIT, which is where this build's are taken and the boot build's are not: the
     * boot build's moment is `$f8b4` and it has exactly one, while this ladder's whole claim is that
     * WB_STAGE_NUMBER and WB_LEVEL_SEQ_INDEX MOVED after an ending. Taken here rather than at each
     * of `run_the_own_entry`'s five exits, so there is one reading and it is the last one. */
    take_the_own_pins(&own);
    m2.frames_run = own.frames_total;
#else
    m2.frames_run = run_frames(&m2);
#endif
    /* RB_VBL_TICKING MEANS WHAT ITS NAME SAYS, and it did not until this edit. It was
     * `frames_run == frames_requested` — a proxy, on the reasoning that `flip_screen` waits on the
     * vblank counter twice a frame so a run that produced frames produced vblanks. The proxy is
     * FALSE ON EVERY PLAYER-DRIVEN EXIT: `run_frames`' third exit is reachable in the play build
     * (one of `game_key_actions`' three endings), and it returns a frame count far below the
     * 0xffffffff cap, so the bit would be raised on a run that did exactly what it was told —
     * arriving as a red precisely at the M3-exits moment this build exists to drive.
     *
     * It is also REDUNDANT as a frame-count check: `m2_checks`' "every frame ran" row already
     * compares those two fields, on the modes where the comparison is meaningful. So this asserts
     * the liveness it is named for instead — the counter the shim keeps independently of the
     * reconstruction's own advanced, and advanced WITH the frames rather than merely being nonzero.
     * A dead level-4 vector cannot satisfy it: `flip_screen`'s waits are uncapped spins, so frames
     * would be 0 and the floor of one vblank per frame is what a stalled counter fails.
     *
     * AND ON THE OWN-ENTRY BUILD THE CLOCK TO READ IS NOT `shim_vbl_ticks`. That counter includes
     * the boot chain's several hundred vblanks — five loads and four depacks on the way in, and as
     * many again on every ESC — which satisfy the floor by themselves whatever the frame loop did.
     * `frame_loop_vbl_ticks` is the same clock bracketed around the legs alone (`run_the_own_entry`
     * accumulates it), so the bit means the same thing on both builds. */
#ifdef SMOKE_OWNPLAY
    checked(RB_VBL_TICKING,
            m2.frames_run > 0u
            && own.frame_loop_vbl_ticks >= MIN_VBLANKS_PER_FRAME * m2.frames_run);
#else
    checked(RB_VBL_TICKING,
            m2.frames_run > 0u && shim_vbl_ticks >= MIN_VBLANKS_PER_FRAME * m2.frames_run);
#endif
    /* IN SUPERVISOR, AND BEFORE THE TEARDOWN, which is the only window in which this means
     * anything: `teardown` puts TOS's own base back, and a read after that would report the
     * desktop's screen and pass for ever. */
    m2.shifter_base = read_the_shifter_base();
#else
#ifdef SMOKE_TITLE
    /* THE PICTURE IS DRAWN AND PHOTOGRAPHED BEFORE THE VBLANK COUNT, not after it. The count is
     * M1's — every read-back below it needs the machine to have driven the reconstruction for a
     * while, and RB_PSG_PORT_A_DESELECTED needs gen_image.py's seeded floppy countdown to expire —
     * but the moment this build is a differential ABOUT is the one the boot's own `$e556` is: the
     * screen as `set_palette` leaves it. Photographing after sixty vblanks of `vbl_handler` would
     * be comparing a different instant from the shipped side's for no gain. */
    draw_the_title(&title);
#endif
#ifdef SMOKE_BOOT
    /* THE WHOLE CHAIN. The moment this build is a differential ABOUT is `$f8b4`, the instant
     * `boot_load_stage` returns, and every vblank after it moves `vbl_handler`'s own writes further
     * from the span the shipped side dumped — which is why `take_the_span` copies the image aside
     * THERE rather than letting the file write decide the instant. What follows this line therefore
     * costs the comparison nothing. */
    run_the_boot(&boot);
    boot.copylock_arm_flag = image_word(WB_COPYLOCK_ARM_FLAG);
#endif
    /* THE SAME BOUNDED WAIT EVERY OTHER NON-FRAME BUILD MAKES — and IN THE BOOT BUILD IT IS
     * ENTRY-STATE-VACUOUS, which is stated here rather than left for a reader to infer from the
     * count. Five disk loads and four depacks have already cost hundreds of vblanks by the time this
     * line runs (measured: ~525, `vbl_ticks_at_span`), so `run_vblanks` returns without waiting and
     * RB_VBL_TICKING is satisfied by the state the chain arrived in. It witnesses nothing there. THE
     * NON-VACUOUS READING OF THE SAME FACT is `vbl_ticks_at_span` against the same SMOKE_VBLS floor,
     * which smoke.py's "the machine drove the chain, not just the tail" row asserts and which
     * `boot_checks` PRINTS this bit's vacuity beside (`unreachable_readbacks`' rule, one mode over).
     *
     * It is still a WAIT rather than a sample because a chain that stopped early on its own terms —
     * a resource the drive does not carry — would otherwise redden this bit and make the real cause,
     * which is the load rows below, the SECOND thing a reader sees. `run_vblanks` is bounded by
     * SPINS_LONG, so a dead level-4 vector still reds here with a record rather than hanging. */
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
    /* NOT `Super(ssp)`, and wonderboy_os.s has the measurement: TOS returns to user mode on the USP
     * the FIRST `Super(0)` froze, so a plain round trip only works while the compiler leaves the
     * stack at the same depth at both call sites. It did until this file grew a third build. */
    (void)wb_leave_supervisor(ssp);

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
#ifdef SMOKE_OWNPLAY
    own.magic = OWN_MAGIC;
    own.bytes = sizeof(own);
    own.image_base = (uint32_t)(uintptr_t)game_image;
    own.entry_unwind = frame_entry_unwind;
    own.copylock_arm_flag = image_word(WB_COPYLOCK_ARM_FLAG);
    own.vbl_ticks_at_exit = shim_vbl_ticks;
    PUBLISH_FIRE_GATES(own);
    PUBLISH_CHAIN_RESULTS(own);
    write_file(OWN_FILE, &own, (long)sizeof(own));
    /* THE PROMPT PICTURE, AND ONLY IF ONE WAS TAKEN. `photographed_screen` is .bss, so an
     * unconditional write would put 32000 zero bytes on the drive for every pass that never took
     * ESC — a picture of nothing, which is exactly the artefact `original.py`'s own capture refuses
     * to produce. The record's `prompt_captured_at` is the flag and it is a field smoke.py grades. */
    if (own.prompt_captured_at) {
        write_file(PROMPT_FILE, photographed_screen, (long)sizeof(photographed_screen));
        write_file(PROMPT_PENS_FILE, photographed_pens, (long)sizeof(photographed_pens));
    }
#endif
#ifdef SMOKE_BOOT
    boot.magic = BOOT_MAGIC;
    boot.bytes = sizeof(boot);
    boot.image_base = (uint32_t)(uintptr_t)game_image;
    boot.screen_base_published = wb_target_screen_base;
    /* The shim's own clock at the program's exit, against `vbl_ticks_at_span`'s reading at the
     * `$f8b4`-equivalent instant: the pair is what says how much of `vbl_handler`'s work happened
     * AFTER the span was taken and therefore cannot be in it. */
    boot.vbl_ticks_at_exit = shim_vbl_ticks;
    PUBLISH_FIRE_GATES(boot);
    PUBLISH_CHAIN_RESULTS(boot);
    write_file(BOOT_FILE, &boot, (long)sizeof(boot));
    write_file(FRAME_FILE, photographed_screen, (long)sizeof(photographed_screen));
    write_file(PENS_FILE, photographed_pens, (long)sizeof(photographed_pens));
    /* THE HEADLINE, and it is written LAST because it is the largest: half a megabyte of image the
     * reconstruction computed, where `gen_image.py --dump` stages half a megabyte it was handed. */
    if (boot.span_bytes)
        write_file(BOOT_IMAGE_FILE, boot_span, (long)sizeof(boot_span));
#endif
#ifdef SMOKE_TITLE
    title.magic = TITLE_MAGIC;
    title.bytes = sizeof(title);
    title.image_base = (uint32_t)(uintptr_t)game_image;
    title.screen_base_published = wb_target_screen_base;
    write_file(TITLE_FILE, &title, (long)sizeof(title));
    write_file(FRAME_FILE, photographed_screen, (long)sizeof(photographed_screen));
    write_file(PENS_FILE, photographed_pens, (long)sizeof(photographed_pens));
#endif
    return 0;
}
