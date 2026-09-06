/* clib.c — Bubble Ghost's Alcyon/DRI C runtime: the trap glue, the free-list allocator, the fd-mode
 * side table, the low-level file layer and the software floating-point package.
 *
 * Layout, addresses and the record shapes are in include/clib.h; what verifies each routine is in
 * ../STATUS.md's "Verified — clib" section. Two things decide the shape of everything here:
 *
 *   * THIS IS COMPILED C, so every routine takes its arguments on the stack and reaches its globals
 *     through A4. The cores below take the values as ordinary C parameters and the globals as
 *     absolute addresses, so a `g_*` glue is a one-line forward — there is no register map to spell.
 *   * A RECONSTRUCTION CANNOT TRAP. Each wrapper writes the three save slots the trampoline writes
 *     and then calls the kit's model of the call itself (tools/recreate_kit/include/os.h). What is
 *     NOT modeled is routed through `os_refused`, which reddens the case rather than faking it.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"
#include "clib.h"

/* ================================================================================================
 * The trap trampolines — `gemdos_trap` @ 0x15e58 and `xbios_trap` @ 0x15e3c
 * ============================================================================================= */

/* Both trampolines are the same six instructions over two different trap vectors, and their whole
 * image effect is these three longwords: A1 and A2 (which TOS may clobber and the Alcyon compiler
 * assumes it may not) plus the return address, popped off the stack so that the selector word the
 * caller pushed ends up where TOS looks for it.
 *
 * `return_pc` is a CALL-SITE CONSTANT — the byte after each wrapper's `jsr` — so every wrapper below
 * passes its own RET_* rather than computing one. */
/* A2 IS NOT ALWAYS THE CALLER'S BY THE TIME A WRAPPER TRAPS. Two routines here reach a trap with
 * their own working pointer in A2 — `c_malloc` holds the free list's roving cursor there when it
 * calls `c_morecore`, and `c_read`'s top-up Fread holds its write cursor — and the trampoline files
 * whatever it finds. Both values are DERIVABLE from the routine's own state, so each substitutes
 * the one it is carrying rather than taking a second argument (docs/agent-playbook.md §5). */
static CallerAddressRegisters carrying_in_a2(CallerAddressRegisters saved, uint32_t a2) {
    saved.a2 = a2;
    return saved;
}

/* The three stores themselves are `trap_save_registers` in include/clib.h — shared with
 * src/sound.c's two `Supexec` callers, which write the same three longwords.
 *
 * This is the other half of the pair: a routine that reaches a trap with a DERIVED a1/a2 (c_read's
 * top-up Fread, and every glue below, which is handed two loose longwords) builds the record here
 * rather than passing them separately, so a swapped pair cannot pass unnoticed. */
static CallerAddressRegisters caller_registers(uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved;

    saved.a1 = a1;
    saved.a2 = a2;
    return saved;
}

/* THE MODELED GEMDOS Malloc IS A BUMP ALLOCATOR, and the kit gives the candidate no way to ask the
 * oracle where its bump pointer is: `os.h` models Fopen/Fread/… but not Malloc, which lives in
 * oracle/shim.c as `d0 = g_heap; g_heap += (size + 1) & ~1`, reset to OS_HEAP_BASE at the top of
 * every run. So the candidate carries the same two lines, and `test/abi.py`'s `run_with_a4` resets
 * the cursor through `g_clib_heap_reset` before EVERY candidate run, exactly as `osh_run` resets the
 * oracle's. A run that allocates once — which is every call site in the game — never depends on it.
 *
 * TODO(kit os_malloc): the kit is growing `os_malloc` in a concurrent change, which is the same
 * model on the candidate's side of the wall. When it lands, delete exactly these five things and
 * nothing else: `g_heap_cursor`, `g_clib_heap_reset` (here and its declaration in include/clib.h),
 * `modeled_gemdos_malloc`, and — in test/abi.py — both the `g_clib_heap_reset` signature
 * declaration and the `lib.g_clib_heap_reset()` call inside `run_with_a4`. Then call `os_malloc`
 * from `gemdos_malloc` and `gemdos_malloc_or_fail`; the wrappers' own shapes do not change. */
static uint32_t g_heap_cursor;

void g_clib_heap_reset(void) { g_heap_cursor = 0; }

static uint32_t modeled_gemdos_malloc(uint32_t bytes) {
    uint32_t block = OS_HEAP_BASE + g_heap_cursor;

    g_heap_cursor += (bytes + 1u) & ~1u;
    return block;
}

/* ================================================================================================
 * String and 32-bit arithmetic
 * ============================================================================================= */

/* c_strlen @ 0x1683e — `move.b (a3),d0 / bne` then `a3 - a2`. Returns a LONGWORD. */
uint32_t c_strlen(const uint8_t *image, uint32_t str) {
    uint32_t cursor = str;

    while (image[cursor] != 0)
        cursor = addr_add(cursor, 1);
    return cursor - str;
}

/* c_strcmp @ 0x167fc — byte compare, stopping at the first difference or at `left`'s NUL.
 *
 * BOTH BYTES ARE SIGN-EXTENDED (`move.b (a3),d0 / ext.w d0`) before the compare and before the
 * subtraction, so a byte >= 0x80 ranks BELOW every ASCII character rather than above it. The three
 * callers only ever ask "is this string equal to CON:/AUX:/PRT:", where the ordering does not
 * matter — but the difference is what the routine returns, and a reconstruction using unsigned
 * bytes returns the wrong sign for half the pairs. */
int16_t c_strcmp(const uint8_t *image, uint32_t left, uint32_t right) {
    while (image[left] != 0 && (int8_t)image[left] == (int8_t)image[right]) {
        left = addr_add(left, 1);
        right = addr_add(right, 1);
    }
    return (int16_t)((int8_t)image[left] - (int8_t)image[right]);
}

/* c_ldiv @ 0x158fe — shift-and-subtract 32-bit divide, magnitudes first and the signs folded back.
 *
 * BOTH ANSWERS GO BACK INTO THE CALLER'S OWN ARGUMENT SLOTS (quotient over the divisor, remainder
 * over the dividend), which is how `itoa_padded` gets a digit and the next value out of one call.
 * Nothing is returned in a register: the routine restores D0-D3 on the way out.
 *
 * A DIVISOR OF ZERO EXECUTES `divu.w #0,d0` DELIBERATELY (@ 0x1590c) — the library's way of raising
 * the 68000's zero-divide exception, which a debugger can hook — and then falls straight into
 * `clr.l d0 / clr.l d1` and stores 0 over both of the caller's slots. So the answer is 0/0 PROVIDED
 * the machine's exception vector returns, and on a real Atari it does: measured under Hatari on the
 * TOS ROM, vector 5 ($14) holds $e00d68 and a user-mode `divu.w #0` comes back with D0 untouched
 * (../STATUS.md records the probe). That is why the branch below stores rather than refusing.
 *
 * THE HARNESS'S OWN IMAGE HAS NO SUCH VECTOR — $14 is zero, so the oracle's CPU takes the exception
 * to address 0 and the run is refused. The cases therefore DECLARE the machine's behaviour, poking
 * an `rte` at $14 exactly as TOS's handler leaves one, and one case pins that without the
 * declaration the oracle refuses. Without the branch the C loops for ever on `(0, n)`.
 *
 * A DIVISOR OF 0x80000000 HANGS. Its magnitude cannot be represented, so `neg.l` leaves it negative;
 * the alignment loop then shifts a 1 out of the top on its first pass, leaves zero behind, and never
 * reaches `divisor >= dividend` again. That is the original's behaviour, reproduced by transcription
 * rather than guarded against — the fuzz below stays clear of it and STATUS.md records it. */
#define LDIV_SIGN_DIVIDEND 3u   /* what a negative dividend adds to the sign tally... */
#define LDIV_SIGN_DIVISOR  1u   /* ...and a negative divisor. Bit 0 of the sum negates the quotient;
                                 * a tally of 3 or more negates the remainder */
void c_ldiv(uint32_t divisor, uint32_t dividend, uint32_t *quotient, uint32_t *remainder) {
    uint16_t sign_tally = 0;
    uint32_t bit;
    uint32_t result = 0;

    if (divisor == 0) {                 /* `move.l 8(a6),d2 / bne` — see the note above */
        *quotient = 0;
        *remainder = 0;
        return;
    }
    if ((int32_t)dividend < 0) {
        sign_tally += LDIV_SIGN_DIVIDEND;
        dividend = -dividend;
    }
    if ((int32_t)divisor < 0) {
        sign_tally += LDIV_SIGN_DIVISOR;
        divisor = -divisor;
    }
    for (bit = 1; divisor < dividend; bit <<= 1)
        divisor <<= 1;
    for (;;) {
        if (divisor <= dividend) {
            result |= bit;
            dividend -= divisor;
        }
        divisor >>= 1;
        if (bit & 1)
            break;
        bit >>= 1;
    }
    if (sign_tally >= LDIV_SIGN_DIVIDEND)
        dividend = -dividend;
    if (sign_tally & 1)
        result = -result;
    *quotient = result;
    *remainder = dividend;
}

/* c_lmul @ 0x15970 — signed 32x32 multiply from three 16x16 `mulu`s, magnitudes first.
 *
 * THE TWO CROSS PRODUCTS ARE ADDED AS WORDS (`add.w d0,-6(a6)` into the high half of the running
 * longword), so each contributes only its own low 16 bits and neither can carry out of the result.
 * That is exactly right for a 32-bit product and it is why the fourth partial product — high times
 * high, which lands entirely above bit 31 — is never computed at all.
 *
 * The answer is written into the SECOND argument's slot and the routine then shifts its return
 * address up over the first, so the caller pops one longword and has the product. */
uint32_t c_lmul(uint32_t left, uint32_t right) {
    uint16_t sign_tally = 0;
    uint32_t product;
    uint16_t high;

    if ((int32_t)left < 0) {
        sign_tally++;
        left = -left;
    }
    if ((int32_t)right < 0) {
        sign_tally++;
        right = -right;
    }
    product = (uint32_t)(uint16_t)left * (uint16_t)right;
    high = (uint16_t)(product >> 16);
    high = (uint16_t)(high + (uint16_t)((uint32_t)(uint16_t)(left >> 16) * (uint16_t)right));
    high = (uint16_t)(high + (uint16_t)((uint32_t)(uint16_t)left * (uint16_t)(right >> 16)));
    product = ((uint32_t)high << 16) | (uint16_t)product;
    if (sign_tally & 1)
        product = -product;
    return product;
}

/* ================================================================================================
 * The fd-mode side table
 * ============================================================================================= */

static uint32_t fd_mode_slot(unsigned index) {
    return A_fd_mode_table + index * FD_MODE_ENTRY;
}

/* c_setfdmode @ 0x15cae — file (handle, mode) in the first slot whose handle word is 0. A full
 * table silently drops the record; nothing checks. */
void c_setfdmode(uint8_t *image, uint16_t handle, uint16_t mode) {
    for (unsigned slot = 0; slot < FD_MODE_SLOTS; slot++) {
        uint32_t entry = fd_mode_slot(slot);

        if (be16(image + entry + FD_MODE_OFF_FD) == 0) {
            wr16(image + entry + FD_MODE_OFF_FD, handle);
            wr16(image + entry + FD_MODE_OFF_MODE, mode);
            return;
        }
    }
}

/* c_clearfdmode @ 0x15cfa — zero the HANDLE word of every slot that matches, leaving the mode word
 * behind. The whole table is walked; there is no early exit, so a handle filed twice is cleared
 * twice. */
void c_clearfdmode(uint8_t *image, uint16_t handle) {
    for (unsigned slot = 0; slot < FD_MODE_SLOTS; slot++) {
        uint32_t entry = fd_mode_slot(slot);

        if (be16(image + entry + FD_MODE_OFF_FD) == handle)
            wr16(image + entry + FD_MODE_OFF_FD, 0);
    }
}

/* c_getfdmode @ 0x15d36 — the mode word filed against `handle`, or the word PAST THE TABLE.
 *
 * The loop tests the handle, steps, and stops when the cursor reaches the table's end — so a search
 * that finds nothing reads its mode word from one entry beyond the last, which is where the linker
 * put the allocator's roving pointer (clib.h, A_fd_mode_overrun). c_read and c_write ask this
 * routine whether a handle is in binary mode, so an unknown handle's answer is the high half of
 * `A_c_malloc_freelist`: zero before anything has allocated, and the arena's high word afterwards. */
uint16_t c_getfdmode(const uint8_t *image, uint16_t handle) {
    for (unsigned slot = 0; slot < FD_MODE_SLOTS; slot++) {
        uint32_t entry = fd_mode_slot(slot);

        if (be16(image + entry + FD_MODE_OFF_FD) == handle)
            return be16(image + entry + FD_MODE_OFF_MODE);
    }
    return be16(image + A_c_malloc_freelist);        /* the overrun; see clib.h */
}

/* The overrun is only THAT global while the two addresses coincide. Spelling the read as
 * A_c_malloc_freelist is what keeps the reconstruction honest about which variable it reaches; this
 * is what keeps that spelling true if either address ever moves. */
_Static_assert(A_fd_mode_table + FD_MODE_SLOTS * FD_MODE_ENTRY + FD_MODE_OFF_MODE
                   == A_c_malloc_freelist,
               "c_getfdmode's off-the-end read no longer lands on A_c_malloc_freelist");

/* ...and the address it leaves in A1 is one entry-field lower, which is A_c_errno. c_read's top-up
 * Fread files that register, so the identity is load-bearing there and not merely a curiosity. */
_Static_assert(A_fd_mode_table + FD_MODE_SLOTS * FD_MODE_ENTRY == A_c_errno,
               "c_getfdmode no longer leaves A1 pointing at A_c_errno");

/* ================================================================================================
 * The allocator
 * ============================================================================================= */

/* gemdos_malloc @ 0x15c82 — GEMDOS Malloc (0x48) through the trampoline. stdio's supplier; distinct
 * from gemdos_malloc_or_fail below, which is the ALLOCATOR's and turns a 0 into -1. */
uint32_t gemdos_malloc(uint8_t *image, uint32_t bytes, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_GEMDOS_MALLOC);
    return modeled_gemdos_malloc(bytes);
}

/* gemdos_mfree @ 0x15c98 — GEMDOS Mfree (0x49). The model always succeeds and frees nothing, which
 * is what makes the arena a pure bump allocator. */
uint32_t gemdos_mfree(uint8_t *image, uint32_t block, CallerAddressRegisters saved) {
    (void)block;                                     /* Mfree always succeeds and frees nothing */
    trap_save_registers(image, saved, RET_GEMDOS_MFREE);
    return 0;
}

/* gemdos_malloc_or_fail @ 0x167c8 — Malloc with a zero-extended WORD size, reporting failure as -1
 * rather than as GEMDOS's 0. */
#define MALLOC_FAILED 0xffffffffu
uint32_t gemdos_malloc_or_fail(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved) {
    uint32_t block;

    trap_save_registers(image, saved, RET_GEMDOS_MALLOC_OR_FAIL);
    block = modeled_gemdos_malloc(bytes);
    return block == 0 ? MALLOC_FAILED : block;
}

/* c_morecore @ 0x15af2 — grow the arena by whole quanta and hand the new block to c_free.
 *
 * The request arrives in GRANULES; it is rounded up to a multiple of MORECORE_QUANTUM_GRANULES, that
 * many granules are asked of GEMDOS as BYTES (`granules * 6`), and the block is given its own size
 * header before being freed into the list — which is what links it in and coalesces it with a
 * neighbour if the arena happens to have grown contiguously. Returns the roving pointer, or 0. */
uint32_t c_morecore(uint8_t *image, uint16_t granules_wanted, CallerAddressRegisters saved) {
    uint16_t quanta = (uint16_t)((uint16_t)(granules_wanted + MORECORE_QUANTUM_GRANULES - 1u)
                                 / MORECORE_QUANTUM_GRANULES);
    uint16_t granules = (uint16_t)(MORECORE_QUANTUM_GRANULES * quanta);
    uint32_t block = gemdos_malloc_or_fail(image, (uint16_t)(granules * MALLOC_GRANULE), saved);

    if (block == MALLOC_FAILED)
        return 0;
    wr16(image + block + FREE_OFF_SIZE, granules);
    c_free(image, addr_add(block, FREE_HEADER_BYTES));
    return be32(image + A_c_malloc_freelist);
}

/* c_malloc @ 0x15b54 — first fit over the circular free list, carving from the TOP of the block.
 *
 * The size is converted to granules first: one for the header plus as many as the payload needs.
 * An empty list (root == 0) is self-initialised to the zero-length sentinel at A_c_malloc_sentinel,
 * so the very first call falls straight through to c_morecore. A block of exactly the right size is
 * unlinked whole; a larger one is shortened and the TAIL is what the caller gets, which is why the
 * roving pointer can stay where it is. */
uint32_t c_malloc(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved) {
    uint16_t granules = (uint16_t)(1u + (uint16_t)((uint16_t)(bytes + MALLOC_GRANULE - 1u)
                                                   / MALLOC_GRANULE));
    uint32_t previous;
    uint32_t block;

    if (be32(image + A_c_malloc_freelist) == 0) {
        wr32(image + A_c_malloc_freelist, A_c_malloc_sentinel);
        wr32(image + A_c_malloc_sentinel + FREE_OFF_NEXT, A_c_malloc_sentinel);
        wr16(image + A_c_malloc_sentinel + FREE_OFF_SIZE, 0);
    }
    previous = be32(image + A_c_malloc_freelist);
    block = be32(image + previous + FREE_OFF_NEXT);
    for (;;) {
        uint16_t size = be16(image + block + FREE_OFF_SIZE);

        if (size >= granules) {
            if (size == granules) {
                wr32(image + previous + FREE_OFF_NEXT, be32(image + block + FREE_OFF_NEXT));
            } else {
                size = (uint16_t)(size - granules);
                wr16(image + block + FREE_OFF_SIZE, size);
                block = addr_add(block, (uint32_t)size * MALLOC_GRANULE);
                wr16(image + block + FREE_OFF_SIZE, granules);
            }
            wr32(image + A_c_malloc_freelist, previous);
            return addr_add(block, FREE_HEADER_BYTES);
        }
        if (block == be32(image + A_c_malloc_freelist)) {
            /* A2 holds `previous` at the `jsr`, and that is what the trampoline files. */
            previous = c_morecore(image, granules, carrying_in_a2(saved, previous));
            if (previous == 0)
                return 0;
        } else {
            previous = block;
        }
        block = be32(image + previous + FREE_OFF_NEXT);
    }
}

/* c_free @ 0x15bfe — link the block back into the ascending list and coalesce both ways.
 *
 * The search walks from the roving pointer until the block sits between a node and its successor,
 * or until it reaches the list's WRAP — the one node whose successor address is not above its own,
 * where an address below every node and one above every node are both "in the gap". Both compares
 * are SIGNED longword compares in the original, which is faithful for an arena inside the image and
 * would not be for one above 0x80000000. */
void c_free(uint8_t *image, uint32_t payload) {
    uint32_t block = payload - FREE_HEADER_BYTES;
    uint32_t node = be32(image + A_c_malloc_freelist);
    uint32_t next;

    for (;;) {
        next = be32(image + node + FREE_OFF_NEXT);
        if ((int32_t)block > (int32_t)node && (int32_t)block < (int32_t)next)
            break;                                  /* the ordinary case: strictly between them */
        if ((int32_t)node < (int32_t)next) {
            node = next;                            /* not the wrap yet — keep walking */
            continue;
        }
        if ((int32_t)block > (int32_t)node)
            break;                                  /* at the wrap, above the highest node */
        if ((int32_t)block >= (int32_t)next) {
            node = next;
            continue;
        }
        break;                                      /* at the wrap, below the lowest node */
    }
    {
        uint16_t block_size = be16(image + block + FREE_OFF_SIZE);

        if (addr_add(block, (uint32_t)block_size * MALLOC_GRANULE) == next) {
            wr16(image + block + FREE_OFF_SIZE,
                 (uint16_t)(block_size + be16(image + next + FREE_OFF_SIZE)));
            wr32(image + block + FREE_OFF_NEXT, be32(image + next + FREE_OFF_NEXT));
        } else {
            wr32(image + block + FREE_OFF_NEXT, next);
        }
    }
    {
        uint16_t node_size = be16(image + node + FREE_OFF_SIZE);

        if (addr_add(node, (uint32_t)node_size * MALLOC_GRANULE) == block) {
            wr16(image + node + FREE_OFF_SIZE,
                 (uint16_t)(node_size + be16(image + block + FREE_OFF_SIZE)));
            wr32(image + node + FREE_OFF_NEXT, be32(image + block + FREE_OFF_NEXT));
        } else {
            wr32(image + node + FREE_OFF_NEXT, block);
        }
    }
    wr32(image + A_c_malloc_freelist, node);
}

/* ================================================================================================
 * The low-level file layer
 * ============================================================================================= */

/* The pseudo-handle `path` names, or 0 for a real file. The two callers compare against their own
 * copy of the name table (the linker emitted one each), so the table address is a parameter. */
static uint16_t device_handle(const uint8_t *image, uint32_t path, uint32_t names) {
    static const uint16_t handles[] = { FD_DEVICE_CON, FD_DEVICE_AUX, FD_DEVICE_PRT };

    for (unsigned i = 0; i < sizeof handles / sizeof handles[0]; i++) {
        if (c_strcmp(image, path, addr_add(names, i * DEVICE_NAME_STRIDE)) == 0)
            return handles[i];
    }
    return 0;
}

/* c_open @ 0x15d64 — resolve a pseudo-device, else GEMDOS Fopen, then file the text/binary mode.
 *
 * The device names short-circuit before GEMDOS is reached at all, and the pseudo-handle they yield
 * still goes through c_setfdmode, which is why a later c_write can ask a CON: handle whether it is
 * in binary mode. Returns the handle as a WORD, or -1. */
int16_t c_open(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved) {
    uint16_t device = device_handle(image, path, A_open_device_names);
    int16_t handle;

    if (device != 0) {
        handle = (int16_t)device;
    } else {
        if (mode & OPEN_MODE_TRUNCATE) {
            /* The truncating open deletes the file first (GEMDOS Fdelete, `c_unlink` @ 0x16868),
             * which the kit does not model. Nothing in the game asks for it — c_creat requests
             * OPEN_MODE_WRITE only — so this refuses rather than fabricating a result, and a case
             * that reached it would fail loudly instead of passing (harness._vet_no_os_refusal). */
            return (int16_t)os_refused(-1);
        }
        trap_save_registers(image, saved, RET_C_OPEN_FOPEN);
        /* The original passes GEMDOS the two access bits (`mode & 3`); `os_fopen` takes no mode at
         * all — the model ignores it (TRAP_MODEL.md, Phase 4) — so there is nothing here for a
         * constant to name and nothing a case could pin. */
        handle = (int16_t)os_fopen(image, path);
        wr16(image + A_c_errno, (uint16_t)handle);
        if (handle < 0)
            return -1;
    }
    c_setfdmode(image, (uint16_t)handle, (uint16_t)(mode & FD_MODE_BINARY));
    return handle;
}

/* c_creat @ 0x14c7a — GEMDOS Fcreate, or c_open for a pseudo-device.
 *
 * It compares against its OWN copy of the device-name table (A_creat_device_names), which holds the
 * same three strings as c_open's at a different address — two copies the linker never merged. */
int16_t c_creat(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved) {
    int16_t handle;

    if (device_handle(image, path, A_creat_device_names) != 0)
        return c_open(image, path, (uint16_t)(OPEN_MODE_WRITE | (mode & FD_MODE_BINARY)), saved);

    trap_save_registers(image, saved, RET_C_CREAT_FCREATE);
    handle = (int16_t)os_fcreate(image, path);
    if (handle < 0) {
        wr16(image + A_c_errno, (uint16_t)handle);
        return -1;
    }
    c_setfdmode(image, (uint16_t)handle, (uint16_t)(mode & FD_MODE_BINARY));
    return handle;
}

/* c_close @ 0x14c3c — drop the mode record, then GEMDOS Fclose for a real file.
 *
 * THE TEST IS A SIGNED WORD COMPARE against FD_DEVICE_CON, which is 0x8300 = -32000: the three
 * pseudo-handles are the only values at or below it, so "handle > CON:" means "a real GEMDOS
 * handle". Closing a pseudo-device succeeds without reaching the OS. */
int16_t c_close(uint8_t *image, uint16_t handle, CallerAddressRegisters saved) {
    int16_t result;

    c_clearfdmode(image, handle);
    if ((int16_t)handle <= (int16_t)FD_DEVICE_CON)
        return 0;
    trap_save_registers(image, saved, RET_C_CLOSE_FCLOSE);
    result = (int16_t)os_fclose(image, handle);
    wr16(image + A_c_errno, (uint16_t)result);
    return result == 0 ? 0 : -1;
}

/* c_read @ 0x1667c — GEMDOS Fread, plus the text mode's carriage-return strip.
 *
 * In BINARY mode the routine is one Fread and the count. In TEXT mode it walks what it read,
 * dropping every 0x0d, and TOPS THE BUFFER UP with further Freads until it has handed the caller
 * `length` bytes or hit end of file — so a text read of n bytes can issue many traps and can move
 * the file cursor well past what it returns.
 *
 * TWO NARROWINGS ARE THE ORIGINAL'S. The pointer differences are `ext.l` of a WORD, so a buffer
 * walk past 32 KB reads as negative; and the "did Fread fail" test is a WORD compare of the result,
 * so a byte count with bit 15 set would read as an error. Neither is reachable at the sizes the
 * game asks for, and both are transcribed rather than corrected.
 *
 * The console path — a handle at or below FD_DEVICE_CON, served by `c_conin` @ 0x16518 — is NOT
 * reconstructed: its body is GEMDOS Crawcin/Cnecin, which the kit does not model. It refuses. */
int32_t c_read(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
               CallerAddressRegisters saved) {
    int32_t count;
    uint32_t read_cursor;
    uint32_t write_cursor;

    wr16(image + A_c_errno, 0);
    if ((int16_t)handle <= (int16_t)FD_DEVICE_CON)
        return os_refused(-1);          /* the cooked console reader; see the note above */

    trap_save_registers(image, saved, RET_C_READ_FREAD_FIRST);
    count = os_fread(image, handle, length, buffer);
    wr16(image + A_c_errno, (uint16_t)count);
    if ((int16_t)count < 0)
        return -1;

    if (c_getfdmode(image, handle) != 0) {
        wr16(image + A_c_errno, 0);     /* binary: the bytes are already where the caller wants them */
        return count;
    }

    length = (uint16_t)count;           /* the text pass hands back at most what was read */
    read_cursor = buffer;
    write_cursor = buffer;
    while ((int16_t)length != 0) {
        if ((int32_t)(int16_t)(read_cursor - buffer) >= count) {
            int32_t refill;

            /* NEITHER SAVED REGISTER IS THE CALLER'S HERE. A2 is the write cursor, which c_read
             * loaded before the loop; and A1 is A_c_errno's address, because `c_getfdmode` — asked
             * about the handle just above — ends with A1 one entry PAST the fd-mode table and
             * nothing puts it back. Both are derived rather than taken as arguments. */
            trap_save_registers(image, caller_registers(A_c_errno, write_cursor),
                                RET_C_READ_FREAD_REFILL);
            refill = os_fread(image, handle, (uint32_t)length, write_cursor);

            wr16(image + A_c_errno, (uint16_t)refill);
            if ((int16_t)refill < 0)
                return -1;
            if (be16(image + A_c_errno) == 0)
                break;                  /* end of file: hand back what has been packed so far */
            count -= (uint16_t)(length - be16(image + A_c_errno));
            read_cursor = write_cursor;
        }
        if ((int16_t)(int8_t)image[read_cursor] == TEXT_MODE_CR) {
            read_cursor = addr_add(read_cursor, 1);
        } else {
            image[write_cursor] = image[read_cursor];
            write_cursor = addr_add(write_cursor, 1);
            read_cursor = addr_add(read_cursor, 1);
            length = (uint16_t)(length - 1u);
        }
    }
    count = (int32_t)(int16_t)(write_cursor - buffer);
    wr16(image + A_c_errno, 0);
    return count;
}

/* ================================================================================================
 * The software floating-point package
 *
 * Shared by every routine below: the WORKING FORM. An IEEE double's sign, 11-bit biased exponent
 * and top 31 mantissa bits are pulled out into a 32-bit mantissa with the implicit leading 1 in
 * bit 31 and a separate exponent word; the sign stays where it is, in the destination's own high
 * word, and is only ever read (or XORed) there. The double's lowest 21 mantissa bits take no part
 * in any operation — see clib.h for what that costs.
 * ============================================================================================= */

#define FP_MANTISSA_SHIFT 11u   /* `asl.l #8` + `asl.l #3`: how far the high longword moves up so
                                 * that the exponent falls off the top and bit 31 is free for the
                                 * implicit 1 */
#define FP_MANTISSA_SPLICE 5u   /* `lsr.w #5` on the double's third word: the 11 bits that fill the
                                 * hole the shift above left at the bottom */
#define FP_IMPLICIT_ONE 0x80000000u
#define FP_SIGN_BIT_HIGH_BYTE 0x80u  /* `btst #7,(a0)`: the sign bit read as the first BYTE's top */
#define LONG_SIGN_BIT   0x80000000u  /* `bset #31,Dn` — the same bit under its other meaning */
#define FP_MANTISSA_SHIFT_FLOAT 9u  /* `lsr.l #1` + `lsr.l #8` in the single tail */
#define FP_EXPONENT_SHIFT_FLOAT 7u  /* ...and `asl.w #7` on its 8-bit exponent */
#define FP_EXPONENT_BITS_FLOAT 0xffu /* `and.w #$ff,d3`: a single's exponent field is eight bits */
#define FP_ADD_MAX_SHIFT 31u        /* `cmp.w #$1f,d0 / bgt`: a wider gap drops the
                                     * smaller operand instead of shifting it away */

/* What the double's packing tail keeps, and where it puts what it kept. */
#define FP_PACK_KEEP_DOUBLE     0xfe00u /* `and.w #$fe00,d2`: drop the nine bits below the double's
                                         * last representable one */
#define FP_PACK_MANTISSA_NIBBLE 0x000fu /* `and.w #$f,d2`: the four mantissa bits that share the
                                         * first longword's high word with the exponent and sign */

/* fp_float_to_double's two: what the 64-bit shift right by three leaves to be corrected, and by
 * how much. */
#define FP_WIDEN_CLEAR_SIGN_FILL 0x8fffffffu /* `and.l #$8fffffff`: keep the sign bit and clear the
                                              * THREE bits the arithmetic shift filled beneath it */
#define FP_WIDEN_BIAS_SHIFTED    0x38000000u /* the bias difference, already in place:
                                              * (1023 - 127) << 20 */

/* The 68000 condition-code bits, in the order `move.w sr,` files them. */
#define CCR_X 0x10u
#define CCR_N 0x08u
#define CCR_Z 0x04u
#define CCR_V 0x02u
#define CCR_C 0x01u

static uint32_t fp_mantissa(const uint8_t *image, uint32_t operand) {
    uint32_t mantissa = (be32(image + operand) << FP_MANTISSA_SHIFT) | FP_IMPLICIT_ONE;

    return set_low_word(mantissa,
                        (uint16_t)((uint16_t)mantissa |
                                   (uint16_t)(be16(image + operand + 4) >> FP_MANTISSA_SPLICE)));
}

static uint16_t fp_exponent(const uint8_t *image, uint32_t operand) {
    /* `asr.w #4` then `and.w #$7ff`: the arithmetic shift's sign fill lands entirely above the
     * mask, so this is the plain 11-bit exponent field however the sign bit reads. */
    return (uint16_t)(((int16_t)be16(image + operand) >> FP_EXPONENT_SHIFT) & FP_EXPONENT_BITS);
}

/* The normalise-and-round both packing tails open with: shift the mantissa up until the bit leaving
 * the top is a 1 (giving the exponent back the two counts that costs), then round, repeating if the
 * round carried all the way out.
 *
 * THE ROUNDING TEST IS THE SAME IN BOTH TAILS AND THE INCREMENT IS NOT, which is the surprise worth
 * stating: the single-precision tail @ 0x1514c tests `and.w #$100` and `and.w #$2ff` exactly as the
 * double's @ 0x153ac does — the DOUBLE's guard and sticky masks — and then adds 0x200 where the
 * double adds 0x100. So only the increment is a parameter here.
 *
 * ON A ZERO VALUE it returns 0 and writes NEITHER output, because the two tails do different things
 * there: the double clears the mantissa (`clr.l d2` @ 0x153a0) and the float clears only the
 * exponent word (`clr.w d3` @ 0x15140), leaving the mantissa to be shifted as it stands. */
#define FP_ROUND_MANTISSA_ZERO 0xffffff00u  /* `and.l #$ffffff00`: what "the value is zero" tests */

static int fp_normalise_and_round(uint32_t *mantissa_out, uint16_t *exponent_out,
                                  uint32_t increment) {
    uint32_t mantissa = *mantissa_out;
    uint16_t exponent = *exponent_out;

    if ((mantissa & FP_ROUND_MANTISSA_ZERO) == 0)
        return 0;
    for (;;) {
        unsigned bit_shifted_out = (mantissa >> 31) & 1u;

        exponent = (uint16_t)(exponent - 1u);
        mantissa <<= 1;
        if (bit_shifted_out)
            break;
    }
    exponent = (uint16_t)(exponent + 2u);
    while ((mantissa & FP_ROUND_GUARD_DOUBLE) != 0 && (mantissa & FP_ROUND_STICKY_DOUBLE) != 0) {
        unsigned carried = long_add_extend(mantissa, increment);

        mantissa += increment;
        if (!carried)
            break;
        mantissa >>= 1;
        exponent = (uint16_t)(exponent + 1u);
    }
    *mantissa_out = mantissa;
    *exponent_out = exponent;
    return 1;
}

/* fp_pack_double @ 0x15394 — the shared `rts` of add, sub, mul, div and fp_long_to_double.
 *
 * IT IS A TAIL, NOT A FUNCTION: it pops the ten registers its caller pushed and unlinks its
 * caller's frame, so it is only ever reached by falling or jumping into it. `dst` supplies the sign
 * — the routines that change the sign have already XORed the destination's own high word — and a
 * zero mantissa stores eight zero bytes, dropping that sign with them. */
void fp_pack_double(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent) {
    uint16_t low_word;
    uint32_t shifted;
    uint16_t high_word;

    if (!fp_normalise_and_round(&mantissa, &exponent, FP_ROUND_INCREMENT_DOUBLE)) {
        wr32(image + dst, 0);                        /* `clr.l d1 / clr.l d2` and the two stores */
        wr32(image + dst + 4, 0);
        return;
    }
    /* `and.w #$fe00,d2` drops the nine bits below the double's last representable one. What is left
     * of the low word becomes the second longword's top nibble-aligned field; the rest of the
     * mantissa, shifted down twelve, becomes the first longword under the exponent and the sign. */
    mantissa = set_low_word(mantissa, (uint16_t)(mantissa & FP_PACK_KEEP_DOUBLE));
    low_word = (uint16_t)mantissa;
    shifted = mantissa >> 12;
    high_word = (uint16_t)(((uint16_t)(shifted >> 16) & FP_PACK_MANTISSA_NIBBLE) |
                           (uint16_t)((exponent & FP_EXPONENT_BITS) << FP_EXPONENT_SHIFT) |
                           (uint16_t)(be16(image + dst) & FP_SIGN_BIT));
    wr32(image + dst, ((uint32_t)high_word << 16) | (uint16_t)shifted);
    wr32(image + dst + 4, (uint32_t)(uint16_t)(low_word << 4) << 16);
}

/* fp_pack_float @ 0x15132 (body at 0x15136) — the same tail for SINGLE precision: an 8-bit exponent
 * shifted left seven, one longword stored.
 *
 * NOTHING IN THE PROGRAM REACHES IT. It is `fp_op_table[6]`, and all four of the game's fp_dispatch
 * call sites carry opcodes 0x0800..0x0804; the `link a6,#0` stub in front of the body is the only
 * other way in and has no caller. It is reconstructed and verified anyway, entered at that stub. */
void fp_pack_float(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent) {
    uint16_t high_word;

    /* THE ZERO PATH CLEARS THE EXPONENT AND NOT THE MANTISSA (`clr.w d3` @ 0x15140, then `bra` to
     * the shift at 0x1516a over the UNCHANGED d2) — unlike the double's, which clears both. It
     * makes no difference to the bytes stored, because the test that got here guarantees the
     * mantissa is at most 0xff and the shift below takes nine bits off it; it is transcribed this
     * way so that each tail says what its own instructions say rather than sharing one. */
    if (!fp_normalise_and_round(&mantissa, &exponent, FP_ROUND_INCREMENT_FLOAT))
        exponent = 0;
    mantissa >>= FP_MANTISSA_SHIFT_FLOAT;
    /* `swap d2 / or.w … / swap d2` puts the exponent and sign in the HIGH word, which is where a
     * single-precision one lives; the mantissa's own top bits share that word beneath them. */
    high_word = (uint16_t)((uint16_t)(mantissa >> 16) |
                           (uint16_t)((exponent & FP_EXPONENT_BITS_FLOAT)
                                      << FP_EXPONENT_SHIFT_FLOAT) |
                           (uint16_t)(be16(image + dst) & FP_SIGN_BIT));
    wr32(image + dst, ((uint32_t)high_word << 16) | (uint16_t)mantissa);
}

/* fp_long_to_double @ 0x15552 — a signed longword in place, sign-magnitude then packed.
 *
 * The exponent is preset to FP_LONG_EXPONENT (0x41d = 1053, i.e. 2^30 scaled for the working form)
 * and given ONE eight-bit prescale if the magnitude has nothing in its top byte; fp_pack_double's
 * own normalise loop does the rest. The sign comes from the ORIGINAL longword, which is still in
 * memory — the negation happened in a register. */
void fp_long_to_double(uint8_t *image, uint32_t operand) {
    uint32_t value = be32(image + operand);
    uint16_t exponent;

    if (value == 0) {
        fp_pack_double(image, operand, 0, 0);
        return;
    }
    if ((int32_t)value < 0)
        value = -value;
    exponent = FP_LONG_EXPONENT;
    if ((value & FP_ROUND_MANTISSA_ZERO) == 0) {
        value <<= 8;
        exponent = (uint16_t)(exponent - 8u);
    }
    fp_pack_double(image, operand, value, exponent);
}

/* fp_float_to_double @ 0x154d0 — widen a 32-bit float in place.
 *
 * The 64-bit shift right by three (`asr.l #1 / roxr.l #1`, three times) moves the single's 8-bit
 * exponent into the double's 11-bit field; `and.l #$8fffffff` then clears the THREE bits the
 * arithmetic shift filled from the sign — bits 30..28, the top of the new exponent field — while
 * keeping the sign itself, and adding the bias difference completes it. A zero input widens to a
 * zero double rather than going through the arithmetic. */
void fp_float_to_double(uint8_t *image, uint32_t operand) {
    uint32_t high = be32(image + operand);
    uint32_t low = 0;

    if (high != 0) {
        for (unsigned i = 0; i < 3; i++) {
            unsigned bit_shifted_out = high & 1u;

            high = (uint32_t)((int32_t)high >> 1);
            low = (low >> 1) | ((uint32_t)bit_shifted_out << 31);
        }
        high = (high & FP_WIDEN_CLEAR_SIGN_FILL) + FP_WIDEN_BIAS_SHIFTED;
    }
    wr32(image + operand, high);
    wr32(image + operand + 4, low);
}

/* fp_double_to_long @ 0x1550a — truncate a double in place to a signed longword.
 *
 * The mantissa is shifted down by however far the exponent falls short of FP_TRUNC_EXPONENT, which
 * is the exponent at which bit 31 of the working mantissa IS bit 0 of the integer. A zero exponent
 * yields 0. The result is truncated toward zero, which is what makes the front end's
 * `Random()/16794009 * 11 + 5` a 5..15 range rather than a rounded one.
 *
 * THE SHIFT COUNT IS TAKEN MODULO 64, because that is what the 68000's register shift does — so an
 * exponent 64 above FP_TRUNC_EXPONENT shifts by nothing at all rather than by 64. Reproduced. */
#define SHIFT_COUNT_MOD 64u
void fp_double_to_long(uint8_t *image, uint32_t operand) {
    uint32_t mantissa = fp_mantissa(image, operand);
    uint16_t exponent = fp_exponent(image, operand);

    if (exponent == 0) {
        mantissa = 0;
    } else {
        uint16_t shift = (uint16_t)-(uint16_t)(exponent - FP_TRUNC_EXPONENT);

        if (shift != 0) {
            unsigned count = shift % SHIFT_COUNT_MOD;

            mantissa = count >= 32u ? 0u : mantissa >> count;
        }
    }
    if (image[operand] & FP_SIGN_BIT_HIGH_BYTE)      /* `btst #7,(a0)`: the double's sign bit */
        mantissa = -mantissa;
    wr32(image + operand, mantissa);
}

/* fp_acc_load_long @ 0x154b0 — store a longword in the package's accumulator and widen it there.
 * Every random-number computation in the front end starts here, straight off XBIOS Random. */
void fp_acc_load_long(uint8_t *image, uint32_t value) {
    wr32(image + A_fp_acc, value);
    fp_long_to_double(image, A_fp_acc);
}

/* fp_acc_to_long @ 0x154c0 — truncate the accumulator in place and return it. */
uint32_t fp_acc_to_long(uint8_t *image) {
    fp_double_to_long(image, A_fp_acc);
    return be32(image + A_fp_acc);
}

/* The shared body of fp_add @ 0x152fa and fp_sub @ 0x152e0 (the body itself is 0x1530a).
 *
 * Subtraction IS addition here: fp_sub flips the source's sign word in memory, records that it did
 * so in A_fp_sub_sign_flag, and falls in; the body XORs the flag back out at the end, so the
 * caller's source operand comes back unchanged. That flip and that restore are both image writes.
 *
 * The larger operand is put in `dst`'s registers — swapping the destination's whole high word for
 * the source's if it has to, which is how the result takes the larger operand's sign — and the
 * smaller is shifted down by the exponent difference before being added. A difference above 31
 * drops the smaller operand entirely. Both mantissas are halved first, so the add cannot carry out
 * of bit 31 before fp_pack_double renormalises. */
static void fp_add_body(uint8_t *image, uint32_t dst, uint32_t src) {
    /* `major` is whichever operand turns out to be the larger; `minor` is the one that gets shifted
     * down to meet it. They start out as destination and source and are swapped if they are the
     * wrong way round. */
    uint32_t major_mantissa = fp_mantissa(image, dst);
    uint16_t major_exponent = fp_exponent(image, dst);
    uint32_t minor_mantissa;
    uint16_t minor_exponent;
    uint16_t dst_sign_word;
    uint32_t sum;

    if (major_exponent == 0)
        major_mantissa = 0;
    minor_mantissa = fp_mantissa(image, src);
    minor_exponent = fp_exponent(image, src);
    if (minor_exponent == 0)
        minor_mantissa = 0;

    dst_sign_word = be16(image + dst);
    /* Halving both first is what lets the sum below run without carrying out of bit 31; the
     * exponent it costs is given back by fp_pack_double's normalise. */
    major_mantissa >>= 1;
    minor_mantissa >>= 1;
    if (!((int16_t)(major_exponent - minor_exponent) > 0 ||
          (major_exponent == minor_exponent &&
           (int32_t)major_mantissa >= (int32_t)minor_mantissa))) {
        uint32_t swap_mantissa = major_mantissa;
        uint16_t swap_exponent = major_exponent;

        major_exponent = minor_exponent;
        major_mantissa = minor_mantissa;
        minor_exponent = swap_exponent;
        minor_mantissa = swap_mantissa;
        wr16(image + dst, be16(image + src));        /* the result takes the larger operand's word */
    }
    sum = major_mantissa;
    if (minor_mantissa != 0) {
        uint16_t shift = (uint16_t)(major_exponent - minor_exponent);

        if (shift <= FP_ADD_MAX_SHIFT) {
            minor_mantissa >>= shift;
            /* The signs are compared through the word captured BEFORE the swap, so "do the two
             * operands point the same way" is asked of the original pair, not the reordered one. */
            if (((be16(image + src) ^ dst_sign_word) & FP_SIGN_BIT) != 0)
                minor_mantissa = -minor_mantissa;
            sum += minor_mantissa;
        }
    }
    /* Undo fp_sub's flip of the source's sign word, so the caller's operand comes back unchanged.
     * The flag is READ BACK from memory rather than carried in a register, which is what makes
     * fp_add and fp_sub one body with one exit. */
    wr16(image + src, (uint16_t)(be16(image + src) ^ be16(image + A_fp_sub_sign_flag)));
    fp_pack_double(image, dst, sum, major_exponent);
}

void fp_add(uint8_t *image, uint32_t dst, uint32_t src) {
    wr16(image + A_fp_sub_sign_flag, 0);
    fp_add_body(image, dst, src);
}

void fp_sub(uint8_t *image, uint32_t dst, uint32_t src) {
    wr16(image + A_fp_sub_sign_flag, FP_SIGN_BIT);
    wr16(image + src, (uint16_t)(be16(image + src) ^ FP_SIGN_BIT));
    fp_add_body(image, dst, src);
}

/* fp_mul @ 0x1524e — three 16x16 partial products over the 32-bit mantissas, exponents folded.
 *
 * The fourth partial product (low x low) contributes nothing above bit 31 of the result, so it is
 * computed only to be tested: if it is nonzero, bit 1 of the result is forced on as a STICKY bit so
 * fp_pack_double's round-to-even sees that something was thrown away. A zero exponent on either
 * side short-circuits to a zero result, sign and all. */
void fp_mul(uint8_t *image, uint32_t dst, uint32_t src) {
    uint32_t dst_mantissa = fp_mantissa(image, dst);
    uint16_t exponent = fp_exponent(image, dst);
    uint32_t src_mantissa;
    uint16_t src_exponent;
    uint32_t low_product;
    uint32_t high_product;
    uint32_t cross_a;
    uint32_t cross_b;

    if (exponent == 0) {
        fp_pack_double(image, dst, 0, exponent);
        return;
    }
    src_mantissa = fp_mantissa(image, src);
    src_exponent = fp_exponent(image, src);
    if (src_exponent == 0) {
        fp_pack_double(image, dst, 0, exponent);
        return;
    }
    exponent = (uint16_t)(exponent - FP_BIAS_MUL);
    exponent = (uint16_t)(exponent + src_exponent);

    high_product = (uint32_t)(uint16_t)(dst_mantissa >> 16) * (uint16_t)(src_mantissa >> 16);
    low_product = (uint32_t)(uint16_t)dst_mantissa * (uint16_t)src_mantissa;
    cross_a = (uint32_t)(uint16_t)(dst_mantissa >> 16) * (uint16_t)src_mantissa;
    cross_b = (uint32_t)(uint16_t)dst_mantissa * (uint16_t)(src_mantissa >> 16);

    /* Each cross product straddles the halfway line: its high word adds into the result and its low
     * word adds into what is being discarded. `swap` + `clr.w` is how the original splits them. */
    {
        uint32_t discarded = low_product;

        high_product += (cross_a >> 16) + long_add_extend(discarded, cross_a << 16);
        discarded += (cross_a << 16);
        high_product += (cross_b >> 16) + long_add_extend(discarded, cross_b << 16);
        discarded += (cross_b << 16);
        if (discarded != 0)
            high_product |= 2u;                      /* `bset #1,d1` — the sticky bit */
    }
    wr16(image + dst, (uint16_t)(be16(image + dst) ^ be16(image + src)));
    fp_pack_double(image, dst, high_product, exponent);
}

/* fp_div @ 0x151d0 — 32 steps of restoring division over a 64-bit remainder.
 *
 * The divisor sits in a 64-bit register pair that is shifted right one place per step while the
 * remainder stays put; each step subtracts when the divisor still fits and shifts a bit into the
 * quotient. A zero exponent on either side gives a zero result, as in fp_mul. */
#define FP_DIV_STEPS 32u
void fp_div(uint8_t *image, uint32_t dst, uint32_t src) {
    uint32_t remainder_high = fp_mantissa(image, dst);
    uint16_t exponent = fp_exponent(image, dst);
    uint32_t divisor_high;
    uint16_t src_exponent;
    uint32_t remainder_low = 0;
    uint32_t divisor_low = 0;
    uint32_t quotient = 0;

    if (exponent == 0) {
        fp_pack_double(image, dst, 0, exponent);
        return;
    }
    divisor_high = fp_mantissa(image, src);
    src_exponent = fp_exponent(image, src);
    if (src_exponent == 0) {
        fp_pack_double(image, dst, 0, exponent);
        return;
    }
    exponent = (uint16_t)(exponent - src_exponent);
    exponent = (uint16_t)(exponent + FP_BIAS_DIV);

    for (unsigned step = 0; step < FP_DIV_STEPS; step++) {
        quotient <<= 1;
        if (divisor_high < remainder_high ||
            (divisor_high == remainder_high && divisor_low <= remainder_low)) {
            /* `addq.w #1,d1` is a WORD add, which can never carry here: the shift above has just
             * cleared bit 0, so the low word is even. */
            quotient = set_low_word(quotient, (uint16_t)(quotient + 1u));
            {
                unsigned borrow = long_sub_extend(remainder_low, divisor_low);

                remainder_low -= divisor_low;
                remainder_high -= divisor_high + borrow;
            }
        }
        divisor_low = (divisor_low >> 1) | (divisor_high << 31);
        divisor_high >>= 1;
    }
    wr16(image + dst, (uint16_t)(be16(image + dst) ^ be16(image + src)));
    fp_pack_double(image, dst, quotient, exponent);
}

/* fp_cmp @ 0x15190 — an ORDER-PRESERVING integer compare of two doubles, left in A_fp_ccr.
 *
 * A negative operand is one's-complemented and given its sign bit back, which maps the whole
 * sign-magnitude line onto the two's-complement one; the 64-bit subtraction that follows then
 * orders the pair correctly. Nothing is stored but the flags: `move.w sr,` files the WHOLE status
 * register, so `status_high` is the machine word above the condition codes, which the arithmetic
 * does not touch and the reconstruction cannot compute.
 *
 * `subx` CLEARS Z on a nonzero result and leaves it alone otherwise, which is exactly what turns
 * two 32-bit subtractions into one 64-bit compare. */
void fp_cmp(uint8_t *image, uint32_t left, uint32_t right, uint16_t status_high) {
    uint32_t left_high = be32(image + left);
    uint32_t left_low = be32(image + left + 4);
    uint32_t right_high = be32(image + right);
    uint32_t right_low = be32(image + right + 4);
    uint32_t low_result;
    uint32_t high_result;
    unsigned borrow;
    unsigned condition;

    if ((int32_t)left_high < 0) {
        left_high = ~left_high | LONG_SIGN_BIT;
        left_low = ~left_low;
    }
    if ((int32_t)right_high < 0) {
        right_high = ~right_high | LONG_SIGN_BIT;
        right_low = ~right_low;
    }
    low_result = left_low - right_low;
    borrow = long_sub_extend(left_low, right_low);
    high_result = left_high - right_high - borrow;

    condition = 0;
    if ((int32_t)high_result < 0)
        condition |= CCR_N;
    if (low_result == 0 && high_result == 0)
        condition |= CCR_Z;                          /* Z survives the `sub` only if both halves are 0 */
    if ((((left_high ^ right_high) & (left_high ^ high_result)) >> 31) & 1u)
        condition |= CCR_V;
    if ((uint64_t)right_high + borrow > (uint64_t)left_high)
        condition |= CCR_C | CCR_X;
    wr16(image + A_fp_ccr, (uint16_t)(status_high | condition));
}

/* fp_dispatch @ 0x153fe — the whole floating-point ABI in one entry point.
 *
 * The opcode's high byte says what the SOURCE is: a short, a long or a single, each widened into
 * the caller's own stack local first, or (anything else, and 0x0800 is what the game's four call
 * sites carry) an eight-byte double passed through as it stands. The low byte indexes
 * A_fp_op_table. `widen_scratch` is that stack local — the eight bytes at -10(a6) — which the
 * differential's stack guard hides, so what pins the widening is the result it feeds. */
void fp_dispatch(uint8_t *image, uint16_t opcode, uint32_t dst, uint32_t src,
                 uint32_t widen_scratch, uint16_t status_high) {
    uint16_t source_kind = opcode & FP_OP_SOURCE_KIND;

    if (source_kind == FP_SOURCE_SHORT) {
        wr32(image + widen_scratch, sign_ext16(be16(image + src)));
        fp_long_to_double(image, widen_scratch);
        src = widen_scratch;
    } else if (source_kind == FP_SOURCE_LONG || source_kind == FP_SOURCE_FLOAT) {
        wr32(image + widen_scratch, be32(image + src));
        if (source_kind == FP_SOURCE_LONG)
            fp_long_to_double(image, widen_scratch);
        else
            fp_float_to_double(image, widen_scratch);
        src = widen_scratch;
    }
    switch (opcode & FP_OP_SELECTOR) {
    case FP_OP_ADD: fp_add(image, dst, src); break;
    case FP_OP_SUB: fp_sub(image, dst, src); break;
    case FP_OP_MUL: fp_mul(image, dst, src); break;
    case FP_OP_DIV: fp_div(image, dst, src); break;
    case FP_OP_CMP: fp_cmp(image, dst, src, status_high); break;
    default:
        /* A_fp_op_table's last two entries are the PACKING TAILS, which pop ten saved registers and
         * unlink a frame fp_dispatch never pushed — dispatching one would unwind fp_dispatch's own
         * stack rather than return. No call site in the program asks for either (all four carry
         * 0x0800..0x0804), so this refuses instead of inventing a behaviour for it. */
        os_refused(-1);
        break;
    }
}

/* xbios_trap @ 0x15e3c — the XBIOS half of the trampoline, exercised through XBIOS Physbase (0x02).
 *
 * Nothing in the C library calls it: the game's own XBIOS bindings do, from every other subsystem.
 * A reconstruction cannot trap, so what it reproduces is the three save slots plus the modeled
 * result, and Physbase is the selector this file uses because its answer is a distinctive constant
 * rather than the 0 most modeled XBIOS calls return. `return_pc` is the CALLER's, not a constant of
 * this routine — every one of the program's XBIOS bindings passes its own. */
uint32_t xbios_physbase(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc) {
    trap_save_registers(image, saved, return_pc);
    return OS_SCREEN_BASE;
}

/* ================================================================================================
 * Glue
 *
 * Every routine here is compiled C with its arguments on the stack, so a glue is a forward: the
 * case puts the arguments where the callee reads them (test/abi.py's `stack_args`) and hands the
 * same values to the core. The three that take more than that are noted where they are.
 * ============================================================================================= */

uint32_t g_c_strlen(uint8_t *image, uint32_t str) { return c_strlen(image, str); }

/* Returned as a signed longword so the case can compare it against the oracle's D0 low word; the
 * original leaves D0's high half untouched, so only the low word is a two-sided check. */
int32_t g_c_strcmp(uint8_t *image, uint32_t left, uint32_t right) {
    return c_strcmp(image, left, right);
}

/* c_ldiv and c_lmul answer through the CALLER'S OWN ARGUMENT SLOTS, which lie in the band the
 * differential drops as stack. The oracle side is therefore driven by a stub that pops those slots
 * into `test/abi.py`'s RESULT area, and these two glues write the same words to the same place —
 * the glue mirrors the stub, and the image diff compares them. */
void g_c_ldiv(uint8_t *image, uint32_t divisor, uint32_t dividend, uint32_t result) {
    uint32_t quotient;
    uint32_t remainder;

    c_ldiv(divisor, dividend, &quotient, &remainder);
    wr32(image + result, quotient);
    wr32(image + result + 4, remainder);
}

void g_c_lmul(uint8_t *image, uint32_t left, uint32_t right, uint32_t result) {
    wr32(image + result, c_lmul(left, right));
}

void g_c_setfdmode(uint8_t *image, uint32_t handle, uint32_t mode) {
    c_setfdmode(image, (uint16_t)handle, (uint16_t)mode);
}

void g_c_clearfdmode(uint8_t *image, uint32_t handle) { c_clearfdmode(image, (uint16_t)handle); }

uint32_t g_c_getfdmode(uint8_t *image, uint32_t handle) {
    return c_getfdmode(image, (uint16_t)handle);
}

uint32_t g_c_malloc(uint8_t *image, uint32_t bytes, uint32_t a1, uint32_t a2) {
    return c_malloc(image, (uint16_t)bytes, caller_registers(a1, a2));
}

void g_c_free(uint8_t *image, uint32_t payload) { c_free(image, payload); }

uint32_t g_c_morecore(uint8_t *image, uint32_t granules, uint32_t a1, uint32_t a2) {
    return c_morecore(image, (uint16_t)granules, caller_registers(a1, a2));
}

uint32_t g_gemdos_malloc(uint8_t *image, uint32_t bytes, uint32_t a1, uint32_t a2) {
    return gemdos_malloc(image, bytes, caller_registers(a1, a2));
}

uint32_t g_gemdos_mfree(uint8_t *image, uint32_t block, uint32_t a1, uint32_t a2) {
    return gemdos_mfree(image, block, caller_registers(a1, a2));
}

uint32_t g_gemdos_malloc_or_fail(uint8_t *image, uint32_t bytes, uint32_t a1, uint32_t a2) {
    return gemdos_malloc_or_fail(image, (uint16_t)bytes, caller_registers(a1, a2));
}

uint32_t g_xbios_physbase(uint8_t *image, uint32_t a1, uint32_t a2, uint32_t return_pc) {
    return xbios_physbase(image, caller_registers(a1, a2), return_pc);
}

int32_t g_c_open(uint8_t *image, uint32_t path, uint32_t mode, uint32_t a1, uint32_t a2) {
    return c_open(image, path, (uint16_t)mode, caller_registers(a1, a2));
}

int32_t g_c_creat(uint8_t *image, uint32_t path, uint32_t mode, uint32_t a1, uint32_t a2) {
    return c_creat(image, path, (uint16_t)mode, caller_registers(a1, a2));
}

int32_t g_c_close(uint8_t *image, uint32_t handle, uint32_t a1, uint32_t a2) {
    return c_close(image, (uint16_t)handle, caller_registers(a1, a2));
}

int32_t g_c_read(uint8_t *image, uint32_t handle, uint32_t buffer, uint32_t length,
                 uint32_t a1, uint32_t a2) {
    return c_read(image, (uint16_t)handle, buffer, (uint16_t)length, caller_registers(a1, a2));
}

/* The two packing tails take their operands in REGISTERS (D2 the mantissa, D3's low word the
 * exponent, A0 the destination), which is why these two glues carry them as arguments where every
 * other glue in this file just forwards a stack argument. */
void g_fp_pack_double(uint8_t *image, uint32_t dst, uint32_t mantissa, uint32_t exponent) {
    fp_pack_double(image, dst, mantissa, (uint16_t)exponent);
}

void g_fp_pack_float(uint8_t *image, uint32_t dst, uint32_t mantissa, uint32_t exponent) {
    fp_pack_float(image, dst, mantissa, (uint16_t)exponent);
}

void g_fp_long_to_double(uint8_t *image, uint32_t operand) { fp_long_to_double(image, operand); }
void g_fp_float_to_double(uint8_t *image, uint32_t operand) { fp_float_to_double(image, operand); }
void g_fp_double_to_long(uint8_t *image, uint32_t operand) { fp_double_to_long(image, operand); }

/* fp_acc_load_long takes its longword in D0 — the only register argument in the package's own ABI. */
void g_fp_acc_load_long(uint8_t *image, uint32_t value) { fp_acc_load_long(image, value); }

uint32_t g_fp_acc_to_long(uint8_t *image) { return fp_acc_to_long(image); }

void g_fp_add(uint8_t *image, uint32_t dst, uint32_t src) { fp_add(image, dst, src); }
void g_fp_sub(uint8_t *image, uint32_t dst, uint32_t src) { fp_sub(image, dst, src); }
void g_fp_mul(uint8_t *image, uint32_t dst, uint32_t src) { fp_mul(image, dst, src); }
void g_fp_div(uint8_t *image, uint32_t dst, uint32_t src) { fp_div(image, dst, src); }

/* `status_high` is the SR above the condition codes — see fp_cmp. */
void g_fp_cmp(uint8_t *image, uint32_t left, uint32_t right, uint32_t status_high) {
    fp_cmp(image, left, right, (uint16_t)status_high);
}

void g_fp_dispatch(uint8_t *image, uint32_t opcode, uint32_t dst, uint32_t src,
                   uint32_t widen_scratch, uint32_t status_high) {
    fp_dispatch(image, (uint16_t)opcode, dst, src, widen_scratch, (uint16_t)status_high);
}
