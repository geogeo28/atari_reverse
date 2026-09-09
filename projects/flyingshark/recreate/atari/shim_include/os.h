/* os.h — the ON-TARGET TOS layer, shadowing the kit's deterministic model for the PRG build only.
 *
 * The verified cores call the kit's `os_*` helpers directly, and those are `static inline` in
 * `tools/recreate_kit/include/os.h` — there is no link-time seam to override. So the seam is the
 * INCLUDE PATH, as in `projects/joust/recreate/atari/shim_include/os.h` and
 * `projects/zynaps/recreate/atari/shim_include/os.h`: build.sh puts this directory ahead of the
 * kit's, every core that says `#include "os.h"` gets this file, and this file pulls the kit's in
 * through `#include_next` for everything it does NOT replace. The differential build never sees
 * this directory, so the `.so` is byte-identical and `make test` stays at its 3,553.
 *
 * TEN HELPERS ARE REPLACED, AND NO ELEVENTH IS LEFT MODELLED — measured every build rather than
 * asserted here: build.sh's REPLACED_OS_HELPERS gate greps the cores for `os_[a-z_0-9]*` and
 * refuses any name this file does not shadow (`os_refused` is the kit's own -DOS_NO_REFUSAL_TALLY
 * arm and counts as shadowed there).
 *
 *   os_fopen / os_fread / os_fclose   the disc is a real GEMDOS drive here, not a staged table
 *   os_super                          a NO-OP: flyshark_os.s owns the privilege switch (see below)
 *   os_in_image                       the target image is a fraction of the model's — see below
 *   os_setscreen / os_setpalette      ordered EVENTS off target; real XBIOS calls here, with every
 *   os_vsync                          address translated out of image space (shim_include/tos.h)
 *   os_ikbd_out                       BIOS Bconout to device 4, the keyboard ACIA
 *   os_cconout                        GEMDOS Cconout — the debug overlay's only output
 *
 * PRIVILEGE. `os_super` returns the model's token WITHOUT trapping, because the shim is already in
 * supervisor mode: flyshark_os.s's `_start` takes it once, before any C runs, and hands it back
 * once through `fs_leave_supervisor` (docs/on-target-execution.md class 9 — the pair is not
 * balanced, and that routine is why). `boot_init` is entered with supervisor already held, which is
 * what the original does too: its own `Super(0)` at 0x14bf4 is its fourth instruction and it never
 * returns to user mode at all. What the core's slice still gets is its answer — the token it stores
 * at `A_saved_super_ssp`, which the original stores and never reads back.
 *
 * THE FILE MODEL GOES, AS IT DOES IN ZYNAPS AND FOR THE SAME REASON. This game's loader IS its
 * boot: eight files and 288,551 bytes of them before the frame loop starts, which is more than the
 * kit's one staging window holds (../STATUS.md's "Follow-ups the kit should absorb" carries that
 * arithmetic). So the traps are real, made from the same privilege level the original makes them
 * from, and what pins that they work rather than returning handle 0 is the TRAP LEDGER: smoke.py's
 * `--trace os_base` arm compares our Fopen/Fread/Fclose sequence against the original binary's over
 * the same boot.
 */
#ifndef FS_SHIM_OS_H
#define FS_SHIM_OS_H

#include <stdint.h>

#include "tos.h"

/* Move the kit's modelled versions of the ten replaced helpers aside, then pull in the kit's header
 * for EVERYTHING else: the constants (OS_IMAGE_SIZE, OS_SUPER_TOKEN, OS_HW_*) and the inline
 * `os_refused` that -DOS_NO_REFUSAL_TALLY selects. */
#define os_fopen      os_model_fopen
#define os_fread      os_model_fread
#define os_fclose     os_model_fclose
#define os_super      os_model_super
#define os_in_image   os_model_in_image
#define os_setscreen  os_model_setscreen
#define os_setpalette os_model_setpalette
#define os_vsync      os_model_vsync
#define os_ikbd_out   os_model_ikbd_out
#define os_cconout    os_model_cconout
#include_next "os.h"
#undef os_fopen
#undef os_fread
#undef os_fclose
#undef os_super
#undef os_in_image
#undef os_setscreen
#undef os_setpalette
#undef os_vsync
#undef os_ikbd_out
#undef os_cconout

/* ================================================================================================
 * THE TARGET'S IMAGE IS A FRACTION OF THE MODEL'S, AND THIS IS THE ONE PLACE THAT SAYS SO.
 *
 * `OS_IMAGE_SIZE` is 1 MiB and does not move: it is BOTH SIDES of the differential (the Musashi
 * oracle's buffer and the candidate's bound), and ../project.toml's `image_size` is pinned equal to
 * it by `harness._vet_os_memory_map()`. Off target that megabyte costs nothing — it is a host
 * `calloc`. On target it is a `.bss` array inside a GEMDOS TPA.
 *
 * WHAT THE REST HELD IS HARNESS-ONLY: the staged-file table and the staging window above it — whose
 * base is ../project.toml's own `fs_base` key, and MOVES whenever the game's eight boot files need a
 * wider window — the oracle's stack at the top and `test/abi.py`'s scratch map. None of it exists
 * here, because this build's file I/O is real GEMDOS and no kit source is linked into the .PRG at
 * all, which is why this file can name the key without ever naming its value. So the target image only has to cover THE GAME'S OWN WORLD, and that world ends at
 * the top of the screen ring: `test/abi.py`'s `SCREEN_RING_SPAN` is 0x60000..0x87600, and
 * ../atari/README.md's "Memory map" is the census.
 *
 * SHRINKING IT MOVES `os_in_image`, WHICH IS THE POINT: that bound is what `os_fread` checks before
 * handing GEMDOS a destination, so it MUST be the real array's length. Bounding a 550 KiB array
 * against a megabyte would let one oversized `Fread` write over the shim's own record — the failure
 * that survives a clean teardown with every read-back green.
 * ============================================================================================= */
#define FS_TARGET_IMAGE_BYTES 0x87600u

_Static_assert(FS_TARGET_IMAGE_BYTES <= OS_IMAGE_SIZE,
               "the target image must be a PREFIX of the modelled one, or an address the "
               "differential never verified would be legal on target");

static inline int os_in_image(uint32_t addr, uint32_t count) {
    return addr <= FS_TARGET_IMAGE_BYTES && count <= FS_TARGET_IMAGE_BYTES - addr;
}

/* ================================================================================================
 * THE FILE SEAM — real GEMDOS, with the two things the model does that GEMDOS does not restored.
 *
 * 1. THE IMAGE BOUND, above: `os_fread` refuses a destination outside the array rather than letting
 *    GEMDOS write past it.
 * 2. A COUNT OF WHAT HAPPENED. `load_file` (../src/init.c) has no error handling at all — that is
 *    the original's behaviour and it is reconstructed faithfully, so a missing data file simply
 *    leaves the buffer as it was. Off target an unstaged name is a refusal the harness cannot
 *    ignore; here the only thing that would say so is these counters, which reach smoke.py through
 *    the record.
 * ============================================================================================= */
extern volatile uint32_t fs_file_opens;         /* Fopen calls the cores made */
extern volatile uint32_t fs_file_open_failures; /* ...that GEMDOS answered with an error */
extern volatile uint32_t fs_file_bytes_read;    /* bytes Fread actually delivered */
extern volatile uint32_t fs_file_refusals;      /* reads this seam refused for leaving the image */

/* `move.w #$2,-(a7)` ahead of the filename at 0x10c0a and 0x10c62 — GEMDOS Fopen mode 2, READ AND
 * WRITE. The kit's door takes no mode at all (../include/init.h says why it is not a core
 * constant), so it exists only on this side of the seam. It is the original's number and it is kept
 * rather than narrowed to 0: mode 2 is what a write-protected disc refuses, so narrowing it here
 * would make this build load discs the 1988 binary cannot. ../atari/README.md says so where a
 * person choosing a floppy will read it. */
#define FS_FOPEN_READ_WRITE 2

/* The name is read as a C string by GEMDOS, so its LENGTH is not known here; the bound checked is
 * the model's own name-field width, which is the longest name it can be. */
static inline int32_t os_fopen(uint8_t *mem, uint32_t name_ptr) {
    int32_t handle;

    if (!os_in_image(name_ptr, OS_FS_NAME)) {
        fs_file_refusals++;
        return -1;
    }
    handle = (int32_t)Fopen((const char *)(mem + name_ptr), FS_FOPEN_READ_WRITE);
    fs_file_opens++;
    if (handle < 0)
        fs_file_open_failures++;
    return handle;
}

/* THE HANDLE IS A WORD ON BOTH SHORES. `load_file` stores Fopen's answer as a word at
 * `A_load_file_handle` and reads it back for the close, so a negative GEMDOS error (-33, file not
 * found) reaches Fread as 0xffdf and is rejected there. The model reproduces that truncation and so
 * does this; neither invents a handle. */
static inline int32_t os_fread(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    int32_t got;

    if (!os_in_image(buf, count)) {
        fs_file_refusals++;
        return -1;
    }
    got = (int32_t)Fread((short)handle, (long)count, mem + buf);
    if (got > 0)
        fs_file_bytes_read += (uint32_t)got;
    return got;
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

/* ================================================================================================
 * THE VIDEO AND COLOUR GROUP — ordered events off target, real traps here.
 *
 * Every address a core passes these is an IMAGE address, so every one goes through
 * `fs_machine_address` (shim_include/tos.h). That is the whole of the translation, and it is why
 * the cores compile unchanged: `render_frame`'s publish is `os_setscreen(-1, screen_draw, -1)` on
 * both shores, and only what the -1 and the base MEAN differs.
 *
 * WHAT THIS RESTORES THAT THE LEDGER COULD NOT HOLD: `os_setscreen`'s event carries the LOGICAL
 * base alone, and this game always passes -1 for it (../STATUS.md's "Unpinned on target", first
 * row). So the differential compares a call that says nothing about which screen was published, and
 * on target the physical base is the whole content of it. The surface for it here is rendered
 * pixels, plus `Physbase()` read back at the anchor.
 * ============================================================================================= */
extern volatile uint32_t fs_setscreen_calls;
extern volatile uint32_t fs_setpalette_calls;
extern volatile uint32_t fs_vsync_calls;

static inline void os_setscreen(uint32_t log_base, uint32_t phys_base, int16_t resolution) {
    Setscreen(fs_machine_address(log_base), fs_machine_address(phys_base), resolution);
    fs_setscreen_calls++;
}

static inline void os_setpalette(uint32_t table) {
    Setpalette(fs_machine_address(table));
    fs_setpalette_calls++;
}

static inline void os_vsync(void) {
    Vsync();
    fs_vsync_calls++;
}

/* BIOS Bconout to device 4 — the IKBD. The one command this program sends is $14, "report joystick
 * events", and without it the 6301 sends scancodes only and two of `acia_ikbd_isr`'s three arms are
 * never taken (docs/on-target-execution.md class 12 is the sibling defect: a device left in its
 * default mode routes the input somewhere the game is not looking). */
extern volatile uint32_t fs_ikbd_commands;

static inline void os_ikbd_out(uint8_t cmd) {
    Bconout(FS_BCONOUT_IKBD, (short)cmd);
    fs_ikbd_commands++;
}

/* GEMDOS Cconout: the debug overlay's cursor-home string and its digits (../src/hud.c), and
 * `console_show_message`'s characters. Nothing in a normal run reaches either. */
static inline void os_cconout(uint8_t ch) {
    Cconout((short)ch);
}

#endif /* FS_SHIM_OS_H */
