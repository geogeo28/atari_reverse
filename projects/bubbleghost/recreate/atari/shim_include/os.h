/* os.h — the ON-TARGET TOS layer, shadowing the kit's deterministic model for the PRG build only.
 *
 * The verified cores call the kit's `os_*` helpers directly, and those are `static inline` in
 * tools/recreate_kit/include/os.h — there is no link-time seam to override. So the seam is the
 * INCLUDE PATH, exactly as in projects/zynaps/recreate/atari/shim_include/os.h: build.sh puts this
 * directory ahead of the kit's, every core that says `#include "os.h"` gets this file, and this
 * file pulls the kit's in through `#include_next` for everything it does NOT replace. The
 * differential build never sees this directory, so the `.so` is byte-identical and `make test`
 * is the same suite it was.
 *
 * WHAT IS REPLACED, and build.sh's REPLACED_OS_HELPERS gate greps the cores for `os_[a-z_0-9]*`
 * every build and refuses any name this file does not shadow — so "no helper is left modelled" is
 * a measurement rather than a claim here:
 *
 *   the seven file calls          real GEMDOS against the drive the program was booted from
 *   the six console calls         real GEMDOS Cconis/Crawcin/Cnecin/Crawio/Cconout/Cauxout/Cprnout
 *   os_ikbd_out                   real BIOS Bconout to device 4, the IKBD's ACIA
 *   os_malloc                     a bump arena inside the target image — see below
 *   os_pterm / os_super           the real traps, and `os_super` really changes privilege here
 *   os_random                     real XBIOS Random
 *   os_vdi / os_aes               a real `trap #2`, with the parameter block TRANSLATED
 *   os_in_image                   the same arithmetic against the array that actually exists
 *   os_refused                    the kit's own -DOS_NO_REFUSAL_TALLY identity
 *
 * ...AND ONE CONSTANT IS REPLACED, which is the one thing here that changes what a VERIFIED CORE
 * COMPUTES, so it is argued rather than mentioned. `OS_SCREEN_BASE` is what the model answers for
 * XBIOS Logbase, and `xbios_trap_call` (../src/frontend.c) returns it from inside a core: there is
 * no door under it. The model's 0x8000 cannot be used on target, and not for taste — the program
 * carves `screen_back = Logbase - 32000` and then the room staging area another 25,600 bytes below
 * that, so a Logbase of 0x8000 puts the staging area at -0x6100 and every stage-to-screen copy
 * reads from an address four gigabytes up. Off target that is harmless because every battery
 * STAGES the two screen pointers rather than taking them from `init_gem_and_screens`' output
 * (../STATUS.md's "Model gaps" says so in those words); on target the boot really does run that
 * routine. So the target answers a Logbase high enough for both buffers to be real, and the layout
 * below is where it comes from.
 *
 * THE OTHER XBIOS CALLS HAVE NO SEAM AT ALL, and that is this build's largest residual rather than
 * something this file can fix. `xbios_trap_call` swallows Setscreen, Setpalette, Setcolor and
 * Vsync as `return 0` — the model's no-op — so a target build cannot intercept them: they are
 * inside a verified core with no `os_*` call under them. `bubble_main.c` reissues the ones the
 * picture depends on at the composition boundary that follows the slice which would have made
 * them, which is LATER than the original makes them by the length of one slice; the README's
 * "Unpinned" section carries the cost, and closing it properly is a change to the CORES (a kit
 * door for the XBIOS group) and therefore to the differential, not to this directory.
 */
#ifndef BUBBLEGHOST_TARGET_OS_H
#define BUBBLEGHOST_TARGET_OS_H

#include <stdint.h>

#include <tos.h>   /* the real traps. ANGLE FORM: docs/on-target-execution.md class 12b — a quoted
                    * include from inside shim_include/ is found by this file's own directory, and
                    * the `#include_next` below then has no search position to resume from. */

/* Move the kit's modelled versions aside, then pull in the kit's header for EVERYTHING else: the
 * constants (OS_FS_NAME, OS_SUPER_*, OS_MALLOC_LARGEST_FREE, OS_CRAWIO_*, GEM_VDI/GEM_AES) and the
 * inline `os_refused` that -DOS_NO_REFUSAL_TALLY selects. `os_gem_trap` is moved aside with the two
 * doors above it because its body calls `gem_dispatch`, which lives in the kit's `src/gem.c` and is
 * not linked here — an unused `static inline` costs nothing, but one this file's own `os_vdi` still
 * called would be an undefined reference. */
#define os_fopen      os_model_fopen
#define os_fcreate    os_model_fcreate
#define os_fread      os_model_fread
#define os_fwrite     os_model_fwrite
#define os_fclose     os_model_fclose
#define os_fseek      os_model_fseek
#define os_fdelete    os_model_fdelete
#define os_malloc     os_model_malloc
#define os_pterm      os_model_pterm
#define os_super      os_model_super
#define os_random     os_model_random
#define os_ikbd_out   os_model_ikbd_out
#define os_cconout    os_model_cconout
#define os_cauxout    os_model_cauxout
#define os_cprnout    os_model_cprnout
#define os_cconis     os_model_cconis
#define os_crawcin    os_model_crawcin
#define os_cnecin     os_model_cnecin
#define os_crawio     os_model_crawio
#define os_gem_trap   os_model_gem_trap
#define os_vdi        os_model_vdi
#define os_aes        os_model_aes
#define os_in_image   os_model_in_image
#include_next "os.h"
#undef os_fopen
#undef os_fcreate
#undef os_fread
#undef os_fwrite
#undef os_fclose
#undef os_fseek
#undef os_fdelete
#undef os_malloc
#undef os_pterm
#undef os_super
#undef os_random
#undef os_ikbd_out
#undef os_cconout
#undef os_cauxout
#undef os_cprnout
#undef os_cconis
#undef os_crawcin
#undef os_cnecin
#undef os_crawio
#undef os_gem_trap
#undef os_vdi
#undef os_aes
#undef os_in_image

/* ================================================================================================
 * THE TARGET IMAGE, AND WHERE THIS GAME'S WORLD SITS IN IT
 *
 * The cores index a flat image at Ghidra addresses, so on target the image is one `.bss` array and
 * every address below is an offset into it. `OS_IMAGE_SIZE` is 1 MiB and does not move — it is BOTH
 * SIDES of the differential, and ../project.toml's `image_size` is pinned equal to it — but a
 * megabyte of `.bss` inside a GEMDOS TPA needs more machine than this game shipped on, and most of
 * that megabyte is harness furniture: the kit's staged-file table at 0xbf000 and its staging area
 * do not exist here, because the files are real.
 *
 *   0x00000 .. 0x10000   low memory the MODEL owns: the 68000 vector longwords the sound engine
 *                        reads and writes ($a4, $114), TOS's conterm byte ($484), the kit's
 *                        KBDVBASE and its poked input block. All of it IMAGE bytes — the shim
 *                        mirrors the three that have a machine counterpart, and `bubble_main.c`
 *                        says which and when.
 *   0x10000 .. 0x2520e   the staged program: TEXT (code + 30 KB of graphics), the zeroed BSS and
 *                        DATA, in the RUN-TIME layout (../README.md, "The image model").
 *   0x2520e .. 0x30000   free. The cores take a `frame` argument — the A6 their locals hang off,
 *                        because a reconstruction has no machine stack — and `bubble_main.c` hands
 *                        them addresses descending from the program's OWN stack top, 0x2720e.
 *   0x30000 .. 0x90000   the Malloc arena, which is ../project.toml's `heap_base`/`heap_limit`
 *                        unchanged: 245 KiB of picture buffers on one boot path.
 *   0x90000 .. 0x96400   the room staging area, `screen_back - ROOM_BYTES`.
 *   0x96400 .. 0x9e100   screen_back — where the VDI draws and the room is assembled.
 *   0x9e100 .. 0xa5e00   screen_phys — what the shifter displays. This is BG_TARGET_SCREEN_BASE.
 *   0xa5e00 .. 0xa6000   slack to the end of the array, so that one low-resolution row of overrun
 *                        past the visible screen lands inside the image rather than in the shim's
 *                        own `.bss`.
 *
 * WHY THE SCREEN IS AT THE TOP AND NOT THE BOTTOM. Both buffers and the staging area are carved
 * DOWNWARDS from Logbase by the game itself, so the answer has to leave 0xe100 bytes below it; the
 * only 57 KB hole below the arena is the 64 KB of low memory the model already owns.
 *
 * IT MUST BE 256-BYTE ALIGNED, and it is not enough for it to be so as an offset: an STF's video
 * base register has no low byte (docs/on-target-execution.md class 8), so what has to be aligned is
 * `image + BG_TARGET_SCREEN_BASE`. `bubble_main.c` rounds the array's base up at RUN TIME and
 * asserts the read-back through Physbase; this offset is 256-aligned so that the sum is.
 * ============================================================================================= */
#define BG_TARGET_IMAGE_BYTES  0xa6000u
#define BG_TARGET_SCREEN_BASE  0x9e100u

_Static_assert(BG_TARGET_IMAGE_BYTES <= OS_IMAGE_SIZE,
               "the target image must be a PREFIX of the modelled one, or an address the "
               "differential never verified would be legal on target");
_Static_assert((BG_TARGET_SCREEN_BASE & 0xffu) == 0,
               "the screen offset must be 256-aligned or the shifter truncates the base it is "
               "handed and displays from below the buffer");

/* The model's Logbase, replaced. See this file's header comment for the whole argument; the two
 * numbers the replacement has to clear are `SCREEN_BYTES` (32000, the buffer under it) and
 * `ROOM_BYTES` (0x6400, the staging area under that), and the `_Static_assert` is the check that
 * they still fit rather than a comment claiming they do. Both live in ../include/blit.h, which this
 * header must not include (it is a CORE header, and pulling it in here would put it in the include
 * closure of every core that says `#include "os.h"`), so the clearance is spelt as one number. */
#define BG_SCREEN_WORLD_BELOW_LOGBASE 0xe100u  /* SCREEN_BYTES + ROOM_BYTES, ../include/blit.h */
_Static_assert(BG_TARGET_SCREEN_BASE >= BG_SCREEN_WORLD_BELOW_LOGBASE,
               "screen_back and the room staging area are carved below Logbase and would land "
               "outside the image");
#undef OS_SCREEN_BASE
#define OS_SCREEN_BASE BG_TARGET_SCREEN_BASE

static inline int os_in_image(uint32_t addr, uint32_t count) {
    return addr <= BG_TARGET_IMAGE_BYTES && count <= BG_TARGET_IMAGE_BYTES - addr;
}

/* ================================================================================================
 * WHAT A REAL TRAP LOSES, AND WHAT IS PUT BACK
 *
 * A seam that swaps a modelled call for a real one drops the model's CONTRACT along with its
 * implementation. The kit's file helpers bound every copy against the image and tally every
 * refusal; real GEMDOS does neither, and an unguarded destination would let a `Fread` write past
 * the array into the shim's own `.bss` — where `bg_saved_ssp` lives, which is the shape that dies
 * at the hand-back AFTER a clean teardown with every read-back green. Both are restored, and each
 * keeps a count STATE.BIN publishes and `smoke.py` asserts: a restored guard with no surface is a
 * guard nobody can watch fire.
 *
 * THE SECOND HALF MATTERS MORE HERE THAN IT DID IN ZYNAPS, because this program's C library hands
 * a failed open straight on: `c_open` (../src/clib.c) files Fopen's answer in `c_errno` and returns
 * -1, but `load_voice_player` and the four picture loaders read into whatever `c_malloc` gave them
 * regardless. A data file missing from the drive would therefore leave a buffer of zeros and draw
 * a black screen, with nothing anywhere saying why. The tally is what says why.
 * ============================================================================================= */
extern volatile uint32_t bg_file_opens;         /* Fopen/Fcreate calls the cores made */
extern volatile uint32_t bg_file_open_failures; /* ...that GEMDOS answered with an error */
extern volatile uint32_t bg_file_refusals;      /* copies this seam refused for leaving the image */
extern volatile uint32_t bg_file_write_failures; /* Fwrites GEMDOS answered with an error */

/* GEMDOS Fopen's mode, AND THE ONE THING THIS SEAM CANNOT DO ANYTHING ABOUT.
 *
 * The original passes GEMDOS the two access bits of the mode word `c_open` was called with
 * (`mode & 3`). THE KIT'S `os_fopen` TAKES NO MODE — its signature is `(mem, name_ptr)` and the
 * model ignores the argument (TRAP_MODEL.md, Phase 4), so `../src/clib.c`'s `c_open` drops it
 * before the door and there is nothing here to read it out of. Giving the door a mode is a KIT
 * change plus a differential, which this directory may not make (../README.md's "Unpinned").
 *
 * WHAT MAKES READ-ONLY THE RIGHT ANSWER MEANWHILE, and it is not a guess: every `c_open` in this
 * program asks for one of `C_OPEN_MODE_READ_BINARY` / `C_OPEN_MODE_READ_TEXT` (../include/
 * frontend.h), and `c_fopen`'s "r"/"rb" arms fold to the same thing. The one file the game WRITES,
 * GHOST.SCR, is reached through `c_creat` -> `os_fcreate`, whose Fcreate handle GEMDOS opens for
 * reading and writing. So read-only is the mode every live caller wants, and it is also the mode
 * that still works on a write-protected floppy.
 *
 * ...AND THE ALARM IF THAT EVER STOPS BEING TRUE. A write down a read-only handle is refused by
 * GEMDOS with an error, which `c_write` files in `c_errno` and no caller in this program reads —
 * exactly the shape of silent failure the refusal tally below exists for. So `os_fwrite` counts a
 * failed write, the record publishes the count and `smoke.py` predicts it as zero. */
#define BG_FOPEN_READ_ONLY 0
#define BG_FCREATE_NORMAL  0   /* Fcreate attr: an ordinary read/write file */

/* The name is read as a C string by GEMDOS, so its LENGTH is not known here; the bound checked is
 * the model's own name field width, which is the longest name it could be. */
static inline int32_t bg_open_common(uint8_t *mem, uint32_t name_ptr, int creating) {
    int32_t handle;

    if (!os_in_image(name_ptr, OS_FS_NAME)) {
        bg_file_refusals++;
        return -1;
    }
    handle = creating ? (int32_t)Fcreate((const char *)(mem + name_ptr), BG_FCREATE_NORMAL)
                      : (int32_t)Fopen((const char *)(mem + name_ptr), BG_FOPEN_READ_ONLY);
    bg_file_opens++;
    if (handle < 0)
        bg_file_open_failures++;
    return handle;
}

static inline int32_t os_fopen(uint8_t *mem, uint32_t name_ptr) {
    return bg_open_common(mem, name_ptr, 0);
}

static inline int32_t os_fcreate(uint8_t *mem, uint32_t name_ptr) {
    return bg_open_common(mem, name_ptr, 1);
}

static inline int32_t os_fread(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    if (!os_in_image(buf, count)) {
        bg_file_refusals++;
        return -1;
    }
    return (int32_t)Fread((short)handle, (long)count, mem + buf);
}

static inline int32_t os_fwrite(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    int32_t written;

    if (!os_in_image(buf, count)) {
        bg_file_refusals++;
        return -1;
    }
    written = (int32_t)Fwrite((short)handle, (long)count, mem + buf);
    if (written < 0)
        bg_file_write_failures++;
    return written;
}

static inline int32_t os_fclose(uint8_t *mem, uint16_t handle) {
    (void)mem;
    return (int32_t)Fclose((short)handle);
}

static inline int32_t os_fseek(uint8_t *mem, uint32_t offset, uint16_t handle, uint16_t mode) {
    (void)mem;
    return (int32_t)Fseek((long)(int32_t)offset, (short)handle, (short)mode);
}

static inline int32_t os_fdelete(uint8_t *mem, uint32_t name_ptr) {
    if (!os_in_image(name_ptr, OS_FS_NAME)) {
        bg_file_refusals++;
        return -1;
    }
    return (int32_t)Fdelete((const char *)(mem + name_ptr));
}

/* ================================================================================================
 * The Malloc arena, which is the model's and not TOS's — and that is deliberate.
 *
 * `c_malloc` (../src/clib.c) hands out blocks of an image the cores index by OFFSET, so a real
 * GEMDOS Malloc's answer — an absolute machine address — is not a value any of them could use.
 * The arena therefore stays inside the image, at ../project.toml's own `heap_base`/`heap_limit`, so
 * that a block is at the same offset on both shores and `test_image_model.py`'s pin (a served
 * Malloc landing at 0x30000) describes this build too.
 *
 * THE BODY IS THE KIT'S `src/os_heap.c`, which a target build does not link — its own header says
 * so. Word rounding, `Malloc(-1)` reporting the free window without moving the pointer, and a
 * request the window cannot hold REFUSED rather than served past the ceiling, are all the model's
 * semantics restated here because there is nothing to link them from.
 * ============================================================================================= */
#define BG_HEAP_BASE  0x30000u   /* ../project.toml's heap_base */
#define BG_HEAP_LIMIT 0x90000u   /* ...and its heap_limit, the first address the arena may not reach */

_Static_assert(BG_HEAP_LIMIT <= BG_TARGET_SCREEN_BASE - BG_SCREEN_WORLD_BELOW_LOGBASE,
               "the Malloc arena would grow into the room staging area");

extern uint32_t bg_heap_pointer;      /* the bump, in bubble_main.c so the record can publish it */
extern uint32_t bg_malloc_calls;      /* ...and how many allocations were asked of it, which is what
                                       * turns the bump into a prediction: one total can be reached
                                       * by any number of requests of the wrong sizes. `Malloc(-1)`
                                       * is not one — it reports and allocates nothing */

static inline uint32_t os_malloc(uint32_t size) {
    uint32_t block = bg_heap_pointer;
    uint32_t free_bytes = bg_heap_pointer < BG_HEAP_LIMIT ? BG_HEAP_LIMIT - bg_heap_pointer : 0;
    uint32_t want;

    if (size == OS_MALLOC_LARGEST_FREE) return free_bytes;
    bg_malloc_calls++;
    want = (size + 1u) & ~1u;
    if (want > free_bytes) return 0;
    bg_heap_pointer += want;
    return block;
}

/* ================================================================================================
 * Console, keyboard and the process
 * ============================================================================================= */

/* The three writers. Real GEMDOS answers a result for two of them and the model answers none, which
 * is why only `os_cprnout` has a return type: the kit's contract is the one both shores keep. */
static inline void os_cconout(uint8_t ch)   { (void)Cconout((short)ch); }
static inline void os_cauxout(uint8_t ch)   { (void)Cauxout((short)ch); }
static inline int32_t os_cprnout(uint8_t ch) { return (int32_t)Cprnout((short)ch); }

/* BIOS Bconout to device 4 — the IKBD's ACIA. `game_top_loop` sends exactly two commands, $12 to
 * disable the mouse before the presentation and $08 to put it back into relative reporting. */
#define BG_BIOS_DEV_IKBD 4
static inline void os_ikbd_out(uint8_t cmd) { (void)Bconout(BG_BIOS_DEV_IKBD, (short)cmd); }

/* The readers. THE MODEL'S REFUSAL HAS NO COUNTERPART HERE and that is the whole point of the seam:
 * off target a blocking read with nothing staged is refused, because there is no key to wait for
 * and any answer would be fabricated; on target the machine waits, which is what the program means.
 * So `os_crawcin`/`os_cnecin` always answer 1 — the "modeled" flag — and the wait is real.
 *
 * That also retires the model gap ../STATUS.md's table opens with. The idiom at every one of this
 * program's key reads is `while (Cconis()) Crawcin(); c = Cnecin();` — a FLUSH and then a blocking
 * read — and no staging can put a key on the far side of a flush, which is why the front end is
 * verified as regions that meet at each `Cnecin`. Here the flush empties a real queue and the read
 * really blocks, so the menu is one loop again. */
static inline uint32_t os_cconis(const uint8_t *mem) { (void)mem; return (uint32_t)Cconis(); }

static inline int os_crawcin(uint8_t *mem, uint32_t *out) {
    (void)mem;
    *out = (uint32_t)Crawcin();
    return 1;
}

static inline int os_cnecin(uint8_t *mem, uint32_t *out) {
    (void)mem;
    *out = (uint32_t)Cnecin();
    return 1;
}

/* Crawio(w): OS_CRAWIO_READ is a NON-BLOCKING read and any other value is a character to write.
 * `game_frame_update`'s key poll is the one caller and it always reads. TOS answers 0 for "no key",
 * which is what the model's OS_CRAWIO_RESULT is. */
static inline uint32_t os_crawio(uint8_t *mem, uint16_t w) {
    (void)mem;
    return (uint32_t)Crawio((short)w);
}

/* GEMDOS Pterm. On the real machine it does not return, and here it does not either — which is the
 * one place this seam is SIMPLER than the model, whose `os_pterm` has to return because it is a C
 * call. The kit's rule that a caller must return immediately after it still holds for the cores;
 * nothing after this line runs on target whether they do or not. */
static inline void os_pterm(uint16_t code) { Pterm((short)code); }

/* XBIOS Random. The model serves a poked 24-bit constant; the machine has a real generator, and
 * the mask is what makes the two the same SHAPE — `../src/frontend.c`'s attract-mode arithmetic
 * divides by 16794009.0 and relies on the value never reaching 2^24 (../notes/frontend.md §2). */
static inline uint32_t os_random(const uint8_t *mem) {
    (void)mem;
    return (uint32_t)Random() & OS_RANDOM_MASK;
}

/* GEMDOS Super, REALLY. This build runs in user mode (tos.h), so the two calls
 * `init_gem_and_screens` makes around its one poke at $484 are the real trap on both ends — and the
 * way back is `bg_leave_supervisor`, which plants the USP itself rather than trusting the depth the
 * compiler left the stack at (docs/on-target-execution.md class 9). The core passes the value it
 * saved, so "arg is not 0 or 1" IS the return leg. */
static inline int os_super(uint32_t arg, uint32_t *out) {
    if (arg == OS_SUPER_ENTER)   { *out = (uint32_t)Super((void *)0); return 1; }
    if (arg == OS_SUPER_INQUIRE) { *out = (uint32_t)Super((void *)1); return 1; }
    *out = (uint32_t)bg_leave_supervisor((void *)arg);
    return 1;
}

/* ================================================================================================
 * GEM: the real `trap #2`, and the pointers that have to be translated to reach it
 *
 * The game's own bindings put IMAGE OFFSETS in their parameter blocks — `vdi_pblock`'s five array
 * pointers, the AES block's six, the two MFDB addresses in `contrl[7..10]` and the raster pointer
 * inside each MFDB. That is exactly right in the differential's world, where the image IS the
 * machine's memory and starts at 0, and exactly right on the original, whose arrays are absolute
 * against the base it runs at. Here the VDI would dereference an offset as an address and write
 * over the 68000's vector page.
 *
 * So the translation lives in the door, and `bg_gem_dispatch` (bubble_backend.c) is it: it builds a
 * machine-address parameter block over the image's own arrays, walks the MFDB chain for a raster
 * copy, makes the trap, and leaves every ANSWER where the game's code reads it — the output arrays
 * are the image's, so the VDI writes straight into them and nothing is copied back.
 * ============================================================================================= */
int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock);

static inline int os_vdi(uint8_t *mem, uint32_t pblk) { return bg_gem_dispatch(mem, GEM_VDI, pblk); }
static inline int os_aes(uint8_t *mem, uint32_t pblk) { return bg_gem_dispatch(mem, GEM_AES, pblk); }

#endif /* BUBBLEGHOST_TARGET_OS_H */
