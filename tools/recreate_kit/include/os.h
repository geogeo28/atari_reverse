/* os.h — deterministic TOS trap model shared by the oracle (shim.c) and reconstructed
 * OS wrappers. The oracle can't call real TOS, so GEMDOS/BIOS/XBIOS traps are serviced
 * with fixed semantics; a reconstruction must model the SAME return value and image effect
 * for its differential test to hold.
 *
 * Modeled: calls that only touch hardware TOS never reads back (Setpalette/Setcolor/Setscreen,
 * Dosound, Cconout/Cconws, Ikbdws) have NO image effect and return 0. Physbase/Logbase return
 * OS_SCREEN_BASE; Getrez returns 0 (low-res); Malloc bump-allocates from OS_HEAP_BASE;
 * Mshrink/Mfree return 0. GEMDOS file I/O is modeled by os_fopen/os_fcreate/os_fread/os_fwrite/
 * os_fclose over a staged-file table (below). The calls that DO read or write model state —
 * Bconstat/Bconin/Crawio, Super, Giaccess, Random — are the os_* helpers further down. XBIOS Supexec
 * runs the passed routine in place (its rts returns to the caller, its D0 becomes the result).
 *
 * GEM trap #2 (AES/VDI) is modeled by os_gem_trap() below — the same code the oracle's
 * shim and the reconstructed gem_aes/gem_vdi wrappers both run, so their image writes agree
 * by construction. Only the three opcodes BuggyBoy actually uses are modeled.
 *
 * BIOS console I/O (Bconstat/Bconin), GEMDOS Super, GEMDOS Fcreate/Fwrite, XBIOS Giaccess and
 * XBIOS Random are modeled below; TRAP_MODEL.md records what each does and does NOT capture.
 * OS_SCREEN_BASE is a provisional low-memory arena; OS_HEAP_BASE is main's Malloc block (below).
 */
#ifndef BB_OS_H
#define BB_OS_H

#include <string.h>
#include "machine.h"

/* ---- the model's fixed memory map -------------------------------------------------------
 * These addresses are kit-wide: one set of C constants serves every game, while load_base /
 * image_size are per-project (project.toml). They therefore assume a program that fits below
 * OS_HEAP_BASE and an image large enough to hold the staging area below the stack guard —
 * harness._vet_os_memory_map() checks both against the bound project and fails loudly if not,
 * which is the signal to move a region here (and its Python mirror in harness.py). */
#define OS_IMAGE_SIZE  0x100000u /* the flat image both cores run on is this long. Kit-wide for the
                                  * same reason the addresses below are: os_fread/os_fwrite must
                                  * bound their memcpy against something, and a reconstruction that
                                  * calls them is handed the image pointer alone, never a length.
                                  * harness._vet_os_memory_map() pins it equal to the bound
                                  * project's image_size, so a project that grows its image fails
                                  * loudly here instead of copying past the buffer unchecked. */
#define OS_SCREEN_BASE 0x8000u   /* Physbase/Logbase result (in-image screen region) */
#define OS_HEAP_BASE   0x20000u  /* Malloc bump-allocator base: an in-image region above the
                                  * program, growing up (BuggyBoy's main takes a 0x5ee08-byte work
                                  * block here, ending ~0x7ee08 — the largest claim so far) */
#define OS_CRAWIO_RESULT 0u      /* GEMDOS Crawio(0xff) raw non-blocking read: what it returns when
                                  * no key is pending. os_crawio() below serves the same poked
                                  * console state as Bconstat/Bconin, so this is its answer on an
                                  * image with nothing staged. BuggyBoy's check_abort /
                                  * console_scancode hardcode it (see os_crawio). */
#define OS_KBDVBASE    0x500u    /* XBIOS Kbdvbase() result: a fixed in-image KBDVBASE struct (free low
                                  * region, clear of the vector page and the program). install_handlers
                                  * patches its mousevec (+0x10) / joyvec (+0x18). Shared with the shim. */

/* ---- harness-poked model state, 0x600..0x61f -------------------------------------------
 * Hardware whose real value is time-varying (a keypress arriving on an IRQ, the PSG's register
 * contents, XBIOS Random) has no analogue on the candidate side, which is pure C with no
 * interrupts. Following projects/buggyboy/recreate/HARNESS.md, it is modeled at the STATE level:
 * each of these is an ordinary in-image input a test pokes, so BOTH cores read the same bytes and
 * the value is differentially verifiable. The block sits just above the KBDVBASE struct, still in
 * the free low region below every program (load_base >= 0x10000) and above TOS's documented
 * system-variable area — the same siting argument as OS_KBDVBASE.
 * Mirrored in Python by harness.py; test/test_os_memory_map.py pins the two sets equal. */
#define OS_CON_PENDING  0x600u   /* u32: nonzero = a character is waiting at the console (Bconstat) */
#define OS_CON_CHAR     0x604u   /* u32: the longword Bconin returns (scancode << 16 | ascii) */
#define OS_RANDOM_VALUE 0x608u   /* u32: the value XBIOS Random returns (masked to 24 bits) */
#define OS_PSG_REGS     0x610u   /* the YM2149 register file, OS_PSG_NREGS bytes (see os_giaccess) */
#define OS_PSG_NREGS    16       /* the YM2149 has 16 registers, selected by 4 bits */

/* XBIOS Dosound(A0) writes the chip, not the image, so both sides record their calls in a ledger the
 * harness compares (src/dosound_log.c on the candidate side, shim.c's g_dosound_arg on the oracle's).
 * ONE cap for both: were they to differ, a run past the smaller one would drop entries on that side
 * only and diverge the comparison for a reason that has nothing to do with the reconstruction. */
#define OS_DOSOUND_LOG_MAX 256

/* ---- GEM trap #2 (AES / VDI) --------------------------------------------------------
 * A trap #2 selects the subsystem by D0 and points D1 at a parameter block of array
 * pointers. AES: apb = {contrl, global, intin, intout, addrin, addrout}; VDI:
 * vpb = {contrl, intin, ptsin, intout, ptsout}. The opcode is contrl[0]; results go into
 * intout (and ptsout for VDI). BuggyBoy issues exactly three calls, all during _start:
 * appl_init, graf_handle, v_opnvwk — anything else is left unmodeled on purpose. */
#define GEM_AES 0xc8u            /* D0 for an AES call */
#define GEM_VDI 0x73u            /* D0 for a VDI call */

#define AES_APPL_INIT   10       /* -> ap_id in intout[0] */
#define AES_GRAF_HANDLE 77       /* -> phys handle + font cell sizes in intout[0..4] */
#define VDI_V_OPNVWK    100      /* -> device attributes in intout[0..] (work_out) */

/* Deterministic "realistic low-res ST" results (320x200, 16 colours). None are read back by
 * the game — _start only reuses graf_handle's handle as the VDI handle — so the exact values
 * matter for faithfulness/documentation, not for downstream behaviour. */
#define OS_AES_AP_ID    0        /* appl_init: single-application id */
#define OS_VDI_HANDLE   1        /* graf_handle: physical workstation handle */
#define OS_FONT_CELL_W  8        /* low-res system font cell / box width  (px) */
#define OS_FONT_CELL_H  8        /* low-res system font cell / box height (px) */
#define OS_SCREEN_MAX_X 319      /* v_opnvwk work_out[0]: max addressable x (xres-1) */
#define OS_SCREEN_MAX_Y 199      /* v_opnvwk work_out[1]: max addressable y (yres-1) */

/* Service a trap #2. Reads the parameter block at `pblk` in `mem`, writes the modeled
 * outputs, and returns 1 if the opcode is modeled, 0 otherwise (an unmodeled opcode must be
 * rejected, never diffed against a fabricated result). Shared verbatim by shim.c and the
 * gem_aes/gem_vdi reconstruction so both sides produce identical image writes. */
static inline int os_gem_trap(uint8_t *mem, uint32_t d0, uint32_t pblk) {
    uint32_t contrl = be32(mem + pblk);              /* apb[0] / vpb[0] */
    uint16_t opcode = be16(mem + contrl);            /* contrl[0] */

    if (d0 == GEM_AES) {
        uint32_t intout = be32(mem + pblk + 3 * 4);  /* apb[3] */
        if (opcode == AES_APPL_INIT) {
            wr16(mem + intout, OS_AES_AP_ID);
            return 1;
        }
        if (opcode == AES_GRAF_HANDLE) {
            wr16(mem + intout + 0, OS_VDI_HANDLE);
            wr16(mem + intout + 2, OS_FONT_CELL_W);  /* wchar */
            wr16(mem + intout + 4, OS_FONT_CELL_H);  /* hchar */
            wr16(mem + intout + 6, OS_FONT_CELL_W);  /* wbox  */
            wr16(mem + intout + 8, OS_FONT_CELL_H);  /* hbox  */
            return 1;
        }
        return 0;
    }
    if (d0 == GEM_VDI) {
        uint32_t intout = be32(mem + pblk + 3 * 4);  /* vpb[3] */
        if (opcode == VDI_V_OPNVWK) {
            /* work_out: only the two determinate low-res fields; the rest of the VDI
             * attribute table is left zero (no code reads it). */
            wr16(mem + intout + 0, OS_SCREEN_MAX_X);
            wr16(mem + intout + 2, OS_SCREEN_MAX_Y);
            return 1;
        }
        return 0;
    }
    return 0;
}

/* ---- BIOS console input (Bconstat 0x01 / Bconin 0x02) --------------------------------
 * Only the console device is modeled: a keystroke on any other BIOS device would have to be
 * invented, and the contract is to refuse rather than answer wrongly. The pending keystroke is
 * the harness-poked state above, so one poke is one keypress — Bconin CONSUMES it (clearing
 * OS_CON_PENDING), the way the real console does, so a polling loop sees exactly one key. */
#define OS_BIOS_DEV_CON  2       /* BIOS device 2 = CON: (the screen/keyboard console) */
#define OS_BCONSTAT_READY 0xffffffffu   /* Bconstat: -1L = a character is waiting, 0 = none */

/* Bconstat(dev) -> *out. Returns 1 if modeled, 0 for a device the model has no state for. */
static inline int os_bconstat(const uint8_t *mem, uint16_t dev, uint32_t *out) {
    if (dev != OS_BIOS_DEV_CON) return 0;
    *out = be32(mem + OS_CON_PENDING) ? OS_BCONSTAT_READY : 0;
    return 1;
}

/* Bconin(dev) -> *out, consuming the pending keystroke. Returns 1 if modeled, 0 otherwise.
 * Reading with no character pending is refused: on real hardware Bconin BLOCKS until a key
 * arrives, and there is no key to wait for here, so any answer would be fabricated. */
static inline int os_bconin(uint8_t *mem, uint16_t dev, uint32_t *out) {
    if (dev != OS_BIOS_DEV_CON || !be32(mem + OS_CON_PENDING)) return 0;
    *out = be32(mem + OS_CON_CHAR);
    wr32(mem + OS_CON_PENDING, 0);
    return 1;
}

/* Crawio(w): GEMDOS raw console I/O. `w` selects the direction — OS_CRAWIO_READ is a NON-BLOCKING
 * read, and any other value is a character to WRITE to the console. The read yields the pending
 * keystroke (consumed, in Bconin's scancode << 16 | ascii shape) or OS_CRAWIO_RESULT when idle; it
 * reads the same poked state as Bconstat/Bconin rather than being a second, disconnected console
 * model, so one staged key is visible to every console call, which is what a real run does. Unlike
 * Bconin it never refuses — "no key" is a legitimate answer for a non-blocking read.
 *
 * The write direction touches no image state (like Cconout) and must NOT consume a staged key: it
 * is the same trap number, so servicing every Crawio as a read would let a program that prints a
 * character swallow the keystroke a later Bconin is waiting for. BuggyBoy's eight sites all pass
 * OS_CRAWIO_READ (all `move.w #$ff,-(a7)`) and Joust issues no Crawio at all, so only the read path
 * is exercised today; the direction is still honoured rather than assumed.
 *
 * BuggyBoy's candidate (src/input.c check_abort, src/os.c console_scancode) does not call this; it
 * returns OS_CRAWIO_RESULT unconditionally. That agrees with the oracle byte for byte while no test
 * stages a key — which is every BuggyBoy test, none of which pokes OS_CON_PENDING — and if one ever
 * does, the two sides differ in D0, i.e. the divergence is loud rather than silently absorbed. */
#define OS_CRAWIO_READ 0x00ffu   /* Crawio's argument for "read"; anything else is a char to write */

static inline uint32_t os_crawio(uint8_t *mem, uint16_t w) {
    uint32_t key;
    if (w != OS_CRAWIO_READ) return 0;              /* console output: no image effect, no key eaten */
    return os_bconin(mem, OS_BIOS_DEV_CON, &key) ? key : OS_CRAWIO_RESULT;
}

/* ---- GEMDOS Super (0x20) -------------------------------------------------------------
 * TOKEN model, not a privilege model. The oracle runs the whole program in supervisor mode
 * (Musashi's reset state) and never switches, so Super(0) hands back a fixed cookie instead of a
 * real stack pointer and Super(cookie) accepts it back. Every call site verified so far either
 * discards the result or saves it only to pass it back, so the cookie is never inspected; a site
 * that did arithmetic on it would be mismodeled, which is why any OTHER restore value is refused
 * rather than served. See TRAP_MODEL.md for what this deliberately does not capture. */
#define OS_SUPER_ENTER    0u          /* Super(0): enter supervisor, return the old stack pointer */
#define OS_SUPER_INQUIRE  1u          /* Super(1): -1 if already in supervisor mode, else 0 */
#define OS_SUPER_TOKEN    0x00535550u /* the cookie Super(0) returns ('\0SUP'); even, never a real SP */
#define OS_SUPER_IS_SUPER 0xffffffffu /* Super(1)'s "yes, supervisor" answer */

static inline int os_super(uint32_t arg, uint32_t *out) {
    if (arg == OS_SUPER_ENTER)   { *out = OS_SUPER_TOKEN;    return 1; }
    if (arg == OS_SUPER_INQUIRE) { *out = OS_SUPER_IS_SUPER; return 1; }  /* always supervisor here */
    if (arg == OS_SUPER_TOKEN)   { *out = 0;                 return 1; }  /* accept our own cookie */
    return 0;                                       /* a stack pointer we never handed out */
}

/* ---- XBIOS Giaccess (0x1c) — the YM2149 register file --------------------------------
 * Giaccess(data, reg): bit 7 of reg set = write `data` to register reg & 0x0f; clear = read that
 * register. The register file is plain image state (OS_PSG_REGS), so a Giaccess write is an
 * ordinary image write the differential covers, and a fresh image starts every register at 0 —
 * the model asserts nothing about the chip's power-on contents; a test that depends on a
 * register's starting value pokes it.
 *
 * The file is fed by Giaccess ONLY. Code that instead touches $ff8800/$ff8802 directly goes to the
 * shim's PSG ledger, which is off-image by design, so those accesses are invisible here; shim.c
 * therefore REFUSES any run that mixes the two paths rather than serve a read from a register file
 * it knows is stale. That is a live guard: Joust uses Giaccess for sound AND rewrites PSG port A
 * directly in its floppy routine, so a run spanning both is rejected (see TRAP_MODEL.md). */
#define OS_PSG_WRITE  0x80u      /* bit 7 of the register argument selects write over read */
/* The register number is the low bits of the argument. DERIVED from OS_PSG_NREGS (a power of two,
 * so nregs - 1 is its mask) rather than written out as 0x0f: harness.psg_regs() bounds a staged
 * register against the Python mirror of OS_PSG_NREGS while os_giaccess masks with this, and
 * test_os_memory_map pins only OS_PSG_NREGS — so an independent literal here could disagree with
 * the Python bound in silence. */
#define OS_PSG_REG_SEL ((unsigned)(OS_PSG_NREGS - 1))

static inline uint32_t os_giaccess(uint8_t *mem, uint16_t data, uint16_t reg) {
    uint8_t *cell = mem + OS_PSG_REGS + (reg & OS_PSG_REG_SEL);
    if (reg & OS_PSG_WRITE) {
        *cell = (uint8_t)data;
        return 0;                                   /* a write's result is not defined by TOS */
    }
    return *cell;                                   /* a read zero-extends the register byte */
}

/* ---- XBIOS Random (0x11) -------------------------------------------------------------
 * Returns the harness-poked 24-bit value — Random is a test INPUT here, not a generator. Every
 * call in one run returns the same value, so a program that loops until Random differs would
 * spin and the run would be rejected for exceeding its instruction cap (a loud failure, not a
 * silent wrong answer). See TRAP_MODEL.md. */
#define OS_RANDOM_MASK 0x00ffffffu   /* XBIOS Random yields a 24-bit value */

static inline uint32_t os_random(const uint8_t *mem) {
    return be32(mem + OS_RANDOM_VALUE) & OS_RANDOM_MASK;
}

/* ---- GEMDOS file I/O (Fcreate 0x3c / Fopen 0x3d / Fclose 0x3e / Fread 0x3f / Fwrite 0x40) ----
 * The oracle can't touch a real filesystem, so files are *staged* into the image: the harness
 * writes each file's raw bytes into the staging area and one table entry per file. os_fopen
 * resolves a filename to a handle, os_fread/os_fwrite move bytes in and out of staging, os_fclose
 * releases the slot — all pure image operations shared by the shim and the reconstructed loaders.
 * An unstaged filename / bad handle returns -1, which the caller treats as unmodeled (rejected),
 * so a loader reading a file we didn't stage can never be falsely "verified".
 *
 * THE HARNESS DECLARES THE FILESYSTEM. Staging reserves OS_FS_OFF_CAPACITY bytes per file, and
 * nothing here ever invents a staging address: os_fcreate only truncates a file the harness
 * already declared (a program creating an undeclared name is refused, not given a fabricated
 * block), and os_fwrite refuses a write that would run past the reserved capacity rather than
 * silently overrun the next file's bytes.
 *
 * Table entry (OS_FS_ENTRY bytes), field offsets below: name[16] (nul-terminated) | staging addr |
 * size | cursor | open flag | capacity. The harness mirrors this layout in Python (see
 * harness.stage_files); tools/recreate_kit/test/test_os_memory_map.py pins the two constant sets
 * equal, and the create/write/open/read round-trip test proves they agree end to end. */
#define OS_FS_TABLE        0xbf000u  /* staged-file table: OS_FS_SLOTS entries of OS_FS_ENTRY bytes.
                                      * Kit-wide (see the memory-map note above): it must sit above
                                      * every game's program and below emu.STACK_GUARD_LO */
#define OS_FS_STAGING      0xc0000u  /* raw file bytes, laid out below the stack by the harness */
#define OS_FS_SLOTS        8
#define OS_FS_NAME         16        /* name field width; filenames must be < 16 chars */
#define OS_FS_OFF_STAGING  16        /* u32: where this file's bytes live in the staging area */
#define OS_FS_OFF_SIZE     20        /* u32: current length in bytes */
#define OS_FS_OFF_CURSOR   24        /* u32: read/write position */
#define OS_FS_OFF_OPEN     28        /* u32: nonzero while a handle is open on this slot */
#define OS_FS_OFF_CAPACITY 32        /* u32: staging bytes reserved; os_fwrite refuses to exceed it */
#define OS_FS_ENTRY        36
#define OS_FS_FIRST_HANDLE 6         /* GEMDOS handles 0..5 are reserved; files start here */

/* Does the byte range [addr, addr + count) lie inside the image? Every m68k_*_memory_* callback
 * bounds-checks its access against the image length, and the two helpers below must too: `buf` and
 * `count` come straight off the emulated program's stack, so an unchecked memcpy would run outside
 * the buffer (Fwrite(handle, 4, 0xfffffff0) copying ~4 GiB) instead of being refused. Written as a
 * subtraction, never `addr + count`: that sum wraps for a large count and waves the copy through. */
static inline int os_in_image(uint32_t addr, uint32_t count) {
    return addr <= OS_IMAGE_SIZE && count <= OS_IMAGE_SIZE - addr;
}

/* Can `count` bytes move between a program buffer at `buf` and a staged file's bytes at
 * `staging + cursor` without leaving the image? One helper for both directions, so the write side —
 * the one that corrupts memory rather than merely reading garbage — cannot be fixed alone. The
 * cursor is bounded before it is added, since a program that scribbled the table could make
 * staging + cursor wrap on its own. */
static inline int os_fs_copy_in_image(uint32_t staging, uint32_t cursor, uint32_t buf,
                                      uint32_t count) {
    return os_in_image(staging, cursor) && os_in_image(staging + cursor, count) &&
           os_in_image(buf, count);
}

static inline int os_fs_name_eq(const uint8_t *a, const uint8_t *b) {
    for (int i = 0; i < OS_FS_NAME; i++) {
        if (a[i] != b[i]) return 0;
        if (a[i] == 0) return 1;
    }
    return 1;                                        /* matched the whole (unterminated) field */
}

/* The table entry for a slot index. */
static inline uint8_t *os_fs_slot(uint8_t *mem, int slot) {
    return mem + OS_FS_TABLE + slot * OS_FS_ENTRY;
}

/* The slot holding `name_ptr`'s file, or -1 if the harness staged no such name. */
static inline int os_fs_find_slot(uint8_t *mem, uint32_t name_ptr) {
    for (int slot = 0; slot < OS_FS_SLOTS; slot++) {
        uint8_t *entry = os_fs_slot(mem, slot);
        if (entry[0] && os_fs_name_eq(mem + name_ptr, entry)) return slot;
    }
    return -1;
}

/* The entry a handle refers to, or NULL if the handle names no staged file. */
static inline uint8_t *os_fs_entry(uint8_t *mem, uint16_t handle) {
    int slot = (int)handle - OS_FS_FIRST_HANDLE;
    if (slot < 0 || slot >= OS_FS_SLOTS) return 0;
    uint8_t *entry = os_fs_slot(mem, slot);
    return entry[0] ? entry : 0;                     /* an empty name means the slot is unused */
}

/* Fopen(name): match the staged-file table, reset the cursor, return a handle (>= 6), or -1. */
static inline int32_t os_fopen(uint8_t *mem, uint32_t name_ptr) {
    int slot = os_fs_find_slot(mem, name_ptr);
    if (slot < 0) return -1;
    uint8_t *entry = os_fs_slot(mem, slot);
    wr32(entry + OS_FS_OFF_CURSOR, 0);
    wr32(entry + OS_FS_OFF_OPEN, 1);
    return OS_FS_FIRST_HANDLE + slot;
}

/* Fcreate(name, attr): open the staged file the same way Fopen does, then truncate it to zero
 * length. -1 if the harness never staged that name — the model has no staging space to hand out,
 * so it refuses instead of inventing an address. */
static inline int32_t os_fcreate(uint8_t *mem, uint32_t name_ptr) {
    int32_t handle = os_fopen(mem, name_ptr);
    if (handle < 0) return -1;
    wr32(os_fs_slot(mem, handle - OS_FS_FIRST_HANDLE) + OS_FS_OFF_SIZE, 0);
    return handle;
}

/* Fread(handle, count, buf): copy min(count, remaining) bytes from the cursor into buf, advance
 * the cursor, return the byte count. -1 if the handle isn't an open staged file, or if either end
 * of the copy would leave the image — this one WRITES through `buf`, so an unchecked wild pointer
 * corrupts the harness's own memory rather than merely reading garbage. */
static inline int32_t os_fread(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    uint8_t *entry = os_fs_entry(mem, handle);
    if (!entry || be32(entry + OS_FS_OFF_OPEN) == 0) return -1;   /* not staged / not open */
    uint32_t staging = be32(entry + OS_FS_OFF_STAGING);
    uint32_t cursor = be32(entry + OS_FS_OFF_CURSOR);
    uint32_t n = be32(entry + OS_FS_OFF_SIZE) - cursor;  /* remaining; cursor never exceeds size */
    if (count < n) n = count;
    if (!os_fs_copy_in_image(staging, cursor, buf, n)) return -1;
    memcpy(mem + buf, mem + staging + cursor, n);
    wr32(entry + OS_FS_OFF_CURSOR, cursor + n);
    return (int32_t)n;
}

/* Fwrite(handle, count, buf): copy count bytes into staging at the cursor, extend the length, and
 * return the byte count. -1 if the handle isn't open, the write would exceed the staged capacity,
 * or either end of the copy would leave the image — a short write would fabricate a disk-full
 * result the harness has no basis for, and a wild `buf` would read outside the buffer. */
static inline int32_t os_fwrite(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    uint8_t *entry = os_fs_entry(mem, handle);
    if (!entry || be32(entry + OS_FS_OFF_OPEN) == 0) return -1;
    uint32_t staging = be32(entry + OS_FS_OFF_STAGING);
    uint32_t cursor = be32(entry + OS_FS_OFF_CURSOR), capacity = be32(entry + OS_FS_OFF_CAPACITY);
    /* Written as a subtraction, never `cursor + count > capacity`: `count` comes straight off the
     * emulated program's stack, so the sum wraps for a large count and would wave through a memcpy
     * that runs off the end of the image. */
    if (cursor > capacity || count > capacity - cursor) return -1;
    if (!os_fs_copy_in_image(staging, cursor, buf, count)) return -1;
    memcpy(mem + staging + cursor, mem + buf, count);
    wr32(entry + OS_FS_OFF_CURSOR, cursor + count);
    if (cursor + count > be32(entry + OS_FS_OFF_SIZE))
        wr32(entry + OS_FS_OFF_SIZE, cursor + count);
    return (int32_t)count;
}

/* Fclose(handle): mark the slot closed. -1 on a bad handle. */
static inline int32_t os_fclose(uint8_t *mem, uint16_t handle) {
    uint8_t *entry = os_fs_entry(mem, handle);
    if (!entry) return -1;
    wr32(entry + OS_FS_OFF_OPEN, 0);
    return 0;
}

#endif /* BB_OS_H */