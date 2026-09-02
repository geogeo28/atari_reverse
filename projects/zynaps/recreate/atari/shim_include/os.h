/* os.h — the ON-TARGET TOS layer, shadowing the kit's deterministic model for the PRG build only.
 *
 * The verified cores call the kit's `os_*` helpers directly, and those are `static inline` in
 * tools/recreate_kit/include/os.h — there is no link-time seam to override. So the seam is the
 * INCLUDE PATH, exactly as in projects/joust/recreate/atari/shim_include/os.h: build.sh puts this
 * directory ahead of the kit's, every core that says `#include "os.h"` gets this file, and this
 * file pulls the kit's in through `#include_next` for everything it does NOT replace. The
 * differential build never sees this directory, so the .so is byte-identical and `make test` stays
 * at its 2700.
 *
 * FIVE HELPERS ARE REPLACED, AND NO SIXTH IS LEFT MODELLED — measured every build rather than
 * asserted here: build.sh's REPLACED_OS_HELPERS gate greps the cores for `os_[a-z_0-9]*` and
 * refuses any name this file does not shadow (`os_refused` is the kit's own -DOS_NO_REFUSAL_TALLY
 * arm, and counts as shadowed there).
 *
 *   os_fopen / os_fread / os_fclose   the disk is a real GEMDOS drive here, not a staged table
 *   os_super                          a NO-OP: zynaps_os.s owns the privilege switch (see below)
 *   os_in_image                       the target image is HALF the model's — see the block below
 *
 * WHY THE FILE MODEL GOES AND JOUST'S STAYS. Joust keeps the staged-file model on target because
 * it opens its high-score file from inside a routine the original runs in supervisor mode, and
 * GEMDOS handle allocation misbehaved there. Zynaps has no such choice to make: its loader IS the
 * program — `load_file` @ 0x144e8 is called about thirty times by `_start` alone, for a megabyte
 * of graphics — and the original issues every one of those traps in supervisor mode itself, having
 * taken `Super(0)` as its first instruction. Staging thirty files into the image would mean
 * shipping the whole data disk inside the .PRG. So the traps are real, and they are made from the
 * same privilege level the original makes them from. What pins that this works rather than
 * returning handle 0 is the TRAP LEDGER: `smoke.py`'s `--trace gemdos` arm compares our
 * Fopen/Fread/Fclose sequence against the original binary's over the same boot slice.
 *
 * PRIVILEGE. `os_super` returns the model's token WITHOUT trapping, because the shim is already in
 * supervisor mode: zynaps_os.s's `_start` takes it once, before any C runs, and hands it back once
 * through `zy_leave_supervisor` at the very end (docs/on-target-execution.md class 9 — the pair is
 * not balanced, and that routine is why). A core taking supervisor mode a second time from the
 * middle of the boot would strand that hand-back. What the core's slice still gets is its answer:
 * `boot_enter_supervisor` returns the token, zynaps_main.c publishes it, and smoke.py checks it —
 * so the slice is observed to have run rather than assumed to have.
 *
 * WHAT THE ORIGINAL DOES WITH THAT ANSWER AND THIS BUILD DOES NOT. `_start` follows its Super(0)
 * with `movea.l d0,a7`: it adopts the old supervisor stack as its own and runs on it for the rest
 * of the program's life. This build keeps the stack GEMDOS gave it. The switch is unobservable to
 * the differential (../STATUS.md's `boot_enter_supervisor` row records exactly that residual: "that
 * A7 becomes that token is unpinned"), and reproducing it here would move the C stack out from
 * under the compiler mid-function. Recorded as a deliberate deviation in README.md.
 */
#ifndef ZYNAPS_TARGET_OS_H
#define ZYNAPS_TARGET_OS_H

#include <stdint.h>

#include "tos.h"

/* Move the kit's modelled versions of the FIVE replaced helpers aside, then pull in the kit's
 * header for EVERYTHING else: the constants (OS_IMAGE_SIZE, OS_SUPER_TOKEN) and the inline
 * `os_refused` that -DOS_NO_REFUSAL_TALLY selects. */
#define os_fopen     os_model_fopen
#define os_fread     os_model_fread
#define os_fclose    os_model_fclose
#define os_super     os_model_super
#define os_in_image  os_model_in_image
#include_next "os.h"
#undef os_fopen
#undef os_fread
#undef os_fclose
#undef os_super
#undef os_in_image

/* ================================================================================================
 * THE TARGET'S IMAGE IS HALF THE MODEL'S, AND THIS IS THE ONE PLACE THAT SAYS SO.
 *
 * `OS_IMAGE_SIZE` is 1 MiB and does not move: it is BOTH SIDES of the differential (the Musashi
 * oracle's buffer and the candidate's bound), and ../project.toml's `image_size` is pinned equal to
 * it by harness._vet_os_memory_map(). Off target that megabyte costs nothing — it is a host
 * `calloc`. On target it is a `.bss` array inside a GEMDOS TPA, and a 1 MiB one needs a 2 MB Atari
 * for a game that shipped on a 512 KB one.
 *
 * WHAT THE UPPER HALF HELD IS HARNESS-ONLY. The kit's fixed map puts the staged-file table at
 * 0xbf000 and its staging area at 0xc0000, and the oracle's stack at the top — none of the three
 * exists here: this build's file I/O is real GEMDOS (see the header comment above), it runs on the
 * stack GEMDOS gave it, and no kit source file is linked into the .PRG at all. So the target image
 * only has to cover THE GAME'S OWN WORLD, and that world ends at 0x7fd00 — README.md's "Memory"
 * section is the census, and build.sh's `A_*` gate is the census re-run every build.
 *
 * SHRINKING IT MOVES `os_in_image`, WHICH IS THE POINT. The bound below is what `os_fread` checks
 * before handing GEMDOS a destination, so it MUST be the real array's length: bounding a 512 KiB
 * array against 1 MiB would let one oversized Fread write over `zy_saved_ssp` and the record, which
 * is the failure that survives a clean teardown with every read-back green. The cores' own two
 * guards (../src/init.c's attract-bar and section-table walks) move with it, and that is argued
 * rather than tolerated: neither walk can produce an address in [0x80000, 0x100000), because both
 * start from an `A_*` below 0x7fd00 and step by 2 or 4 until they pass a cursor.
 *
 * `os_in_image_fixed` IS DELIBERATELY LEFT ON THE MODEL'S BOUND. No core calls it, and one that
 * started to would be REFUSED BY build.sh's REPLACED_OS_HELPERS gate — that grep lists the exact
 * names this file shadows, and `os_in_image_fixed` is not one of them, so the build stops rather
 * than compiling a core against the wrong image length.
 * ============================================================================================= */
#define ZY_TARGET_IMAGE_BYTES 0x80000u

_Static_assert(ZY_TARGET_IMAGE_BYTES <= OS_IMAGE_SIZE,
               "the target image must be a PREFIX of the modelled one, or an address the "
               "differential never verified would be legal on target");

static inline int os_in_image(uint32_t addr, uint32_t count) {
    return addr <= ZY_TARGET_IMAGE_BYTES && count <= ZY_TARGET_IMAGE_BYTES - addr;
}

/* `clr.w -(a7)` ahead of the filename at 0x144ec — GEMDOS Fopen mode 0, read-only. The kit's model
 * takes no mode at all, so this constant exists only on this side of the seam. */
#define ZY_FOPEN_READ_ONLY 0

/* THE HANDLE IS A WORD ON BOTH SHORES. `load_file` stores Fopen's answer as a word at
 * `A_file_handle` and reads it back for the close, so a negative GEMDOS error (-33, file not found)
 * reaches Fread as 0xffdf and is rejected there. The model reproduces that truncation and so does
 * this; neither invents a handle. See ../src/fileio.c's header comment. */

/* ================================================================================================
 * THE TWO THINGS THE MODEL DOES THAT REAL GEMDOS DOES NOT, RESTORED.
 *
 * The kit's helpers are not just traps — they are traps with a CONTRACT, and substituting a real
 * trap silently drops both halves of it. Each is restored below, and each keeps a count the record
 * publishes and smoke.py asserts, because a restored guard with no surface is a guard nobody can
 * see fire.
 *
 * 1. THE IMAGE BOUND. `os_fread` copies through `os_fs_copy_in_image` -> `os_in_image(buf, count)`,
 *    "written as a subtraction, never `addr + count`: that sum wraps for a large count and waves
 *    the copy through". Off target a destination past the image is a REFUSAL and the harness throws
 *    the case away, so a mutated address or an off-by-one length is caught by construction. On
 *    target, unguarded, GEMDOS would write those bytes into whatever follows the image in `.bss` —
 *    `zy_saved_ssp` among them, which is the shape that dies at `zy_leave_supervisor` AFTER a clean
 *    teardown with every read-back green.
 *
 * 2. THE REFUSAL TALLY. `-DOS_NO_REFUSAL_TALLY` compiles `os_refused` to an identity, which is
 *    right for the cores' own sentinel path but leaves nothing counting a FAILED OPEN — and
 *    `load_file` (../src/fileio.c) has no error handling at all, faithfully: it hands Fopen's -33
 *    straight to Fread as a handle. Under the harness an unstaged name was a refusal the harness
 *    could not ignore; on target a missing data file would simply leave the buffer zeroed, and M1
 *    draws none of the four files whose absence would show. So the opens are counted here.
 * ============================================================================================= */
extern volatile uint32_t zy_file_opens;            /* Fopen calls the cores made */
extern volatile uint32_t zy_file_open_failures;    /* ...that GEMDOS answered with an error */
extern volatile uint32_t zy_file_refusals;         /* reads this seam refused for leaving the image */

/* The name is read as a C string by GEMDOS, so its LENGTH is not known here; the bound checked is
 * the model's own name field width, which is the longest name it can be (`OS_FS_NAME`). */
static inline int32_t os_fopen(uint8_t *mem, uint32_t name_ptr) {
    int32_t handle;

    if (!os_in_image(name_ptr, OS_FS_NAME)) {
        zy_file_refusals++;
        return -1;
    }
    handle = (int32_t)Fopen((const char *)(mem + name_ptr), ZY_FOPEN_READ_ONLY);
    zy_file_opens++;
    if (handle < 0)
        zy_file_open_failures++;
    return handle;
}

static inline int32_t os_fread(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    if (!os_in_image(buf, count)) {
        zy_file_refusals++;
        return -1;
    }
    return (int32_t)Fread((short)handle, (long)count, mem + buf);
}

static inline int32_t os_fclose(uint8_t *mem, uint16_t handle) {
    (void)mem;
    return (int32_t)Fclose((short)handle);
}

/* No trap. `_start` is already supervisor; see the header comment. The answers are the model's own
 * constants so that the core's return value means the same thing on both shores. */
static inline int os_super(uint32_t arg, uint32_t *out) {
    if (arg == OS_SUPER_ENTER)   { *out = OS_SUPER_TOKEN;    return 1; }
    if (arg == OS_SUPER_INQUIRE) { *out = OS_SUPER_IS_SUPER; return 1; }
    if (arg == OS_SUPER_TOKEN)   { *out = 0;                 return 1; }
    return 0;
}

#endif /* ZYNAPS_TARGET_OS_H */
