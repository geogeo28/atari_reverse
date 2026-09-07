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
/* AND A1 IS NOT THE CALLER'S ONCE THE fd-MODE TABLE HAS BEEN ASKED. `c_getfdmode` @ 0x15d36 opens
 * `lea table,a1 / adda.w #$130,a1` and never restores it, so A1 comes back holding the address one
 * entry past the table — which is `A_c_errno` — and every trap AFTER that files it, in the routine
 * that asked and in every routine above it. (`c_setfdmode` and `c_clearfdmode` walk the same table
 * through A0 and leave A1 alone, so only the reader does this.)
 *
 * THE CLOBBER TRAVELS WITH THE CALL rather than being predicted by each caller. `c_read` and
 * `c_write` are the only two routines that ask, so they are the only two that record it — and every
 * routine that can reach one of them takes the register record BY POINTER, so a caller three levels
 * up files the right A1 without knowing which arm ran. Predicting it per caller was the first shape
 * here, and it was already wrong once (`c_fputs`, whose second flush files a different A1 from its
 * first) and overstated once (`c_fread`, which used to claim every refill had asked). */
static void note_fd_modes_consulted(CallerAddressRegisters *saved) { saved->a1 = A_c_errno; }

/* ================================================================================================
 * The C runtime's startup hooks
 * ============================================================================================= */

/* crt0_setup_args @ 0x10116 — the Alcyon runtime's argv hook. A BARE `rts`.
 *
 * The crt0 calls it with the basepage's command tail (`pea 128(a0) / jsr $10116` @ 0x100b2) so that
 * a program which wants `argc`/`argv` can parse it; this one was linked against the stub, so the
 * whole routine is two bytes. Reconstructed rather than left out because a routine nobody
 * reconstructs and nobody records is indistinguishable from one nobody noticed — and because the
 * claim "it writes nothing" is exactly what a differential can check (`test_clib.py`).
 *
 * It is HERE and not with the boot chain in ../STATUS.md's `init` section because it belongs to the
 * C library rather than to the game: it is the runtime's hook, and the crt0 is its only caller. */
void crt0_setup_args(uint8_t *image, uint32_t command_tail) {
    (void)image;            /* it reads nothing... */
    (void)command_tail;     /* ...not even the argument the crt0 pushes for it */
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
 * from gemdos_malloc_or_fail below, which is the ALLOCATOR's and turns a 0 into -1.
 *
 * `os_malloc` IS THE MODEL, not a copy of it: the kit's bump arena (tools/recreate_kit/src/os_heap.c)
 * is the same allocator `oracle/shim.c` services the trap from, over the base and ceiling
 * project.toml's `heap_base`/`heap_limit` install into both sides. So the two bump pointers are
 * comparable per run (`harness._vet_heap_pointers_agree`), which a private copy of the arithmetic
 * here was not. `Malloc(-1)`'s free-size answer and the refusal past the ceiling are the model's
 * too; both wrappers below simply forward. */
uint32_t gemdos_malloc(uint8_t *image, uint32_t bytes, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_GEMDOS_MALLOC);
    return os_malloc(bytes);
}

/* gemdos_mfree @ 0x15c98 — GEMDOS Mfree (0x49). The model always succeeds and frees nothing, which
 * is what makes the arena a pure bump allocator. */
uint32_t gemdos_mfree(uint8_t *image, uint32_t block, CallerAddressRegisters saved) {
    (void)block;                                     /* Mfree always succeeds and frees nothing */
    trap_save_registers(image, saved, RET_GEMDOS_MFREE);
    return 0;
}

/* gemdos_malloc_or_fail @ 0x167c8 — Malloc with a zero-extended WORD size, reporting failure as -1
 * rather than as GEMDOS's 0. A request the modeled arena cannot hold comes back from `os_malloc` as
 * that same 0 (through `os_refused`, which also reddens the case), so the `block == 0` test below
 * reads on the model exactly as it reads on the machine. */
#define MALLOC_FAILED 0xffffffffu
uint32_t gemdos_malloc_or_fail(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved) {
    uint32_t block;

    trap_save_registers(image, saved, RET_GEMDOS_MALLOC_OR_FAIL);
    block = os_malloc(bytes);
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
            /* The truncating open makes the file EMPTY in three steps — delete it, create it, close
             * the handle that created it — and then falls through into the ordinary Fopen below,
             * which is what the caller actually gets back. A failed delete abandons the whole call.
             * Nothing in the GAME asks for this mode (`c_creat` requests OPEN_MODE_WRITE only), but
             * the model serves all three calls now, so the arm is run rather than refused. */
            int16_t emptied;

            if (c_unlink(image, path, saved) != 0)
                return -1;
            trap_save_registers(image, saved, RET_C_OPEN_TRUNC_FCREATE);
            emptied = (int16_t)os_fcreate(image, path);
            trap_save_registers(image, saved, RET_C_OPEN_TRUNC_FCLOSE);
            /* The original discards BOTH answers: a failed create is closed like any other handle
             * and the error is never looked at. */
            (void)os_fclose(image, (uint16_t)emptied);
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
int32_t c_read_reporting(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
                         CallerAddressRegisters *saved) {
    int32_t count;
    uint32_t read_cursor;
    uint32_t write_cursor;
    int binary;

    wr16(image + A_c_errno, 0);
    if ((int16_t)handle <= (int16_t)FD_DEVICE_CON)
        return os_refused(-1);          /* the cooked console reader; see the note above */

    trap_save_registers(image, *saved, RET_C_READ_FREAD_FIRST);
    count = os_fread(image, handle, length, buffer);
    wr16(image + A_c_errno, (uint16_t)count);
    if ((int16_t)count < 0)
        return -1;

    binary = c_getfdmode(image, handle) != 0;
    note_fd_modes_consulted(saved);     /* ...and A1 stays there for every trap from here up */
    if (binary) {
        wr16(image + A_c_errno, 0);     /* the bytes are already where the caller wants them */
        return count;
    }

    length = (uint16_t)count;           /* the text pass hands back at most what was read */
    read_cursor = buffer;
    write_cursor = buffer;
    while ((int16_t)length != 0) {
        if ((int32_t)(int16_t)(read_cursor - buffer) >= count) {
            int32_t refill;

            /* A2 is the write cursor this routine loaded before the loop; A1 is already
             * `A_c_errno`, recorded above where `c_getfdmode` left it. */
            trap_save_registers(image, carrying_in_a2(*saved, write_cursor),
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

/* THE BY-VALUE SPELLINGS, for a caller that makes ONE of these calls and then traps no more.
 * Everything inside this file goes through the `_reporting` forms above, because A1 has to travel
 * up the call chain; a caller elsewhere that makes several calls in a row needs the same and should
 * call those directly rather than re-deriving `A_c_errno` afterwards. */
int32_t c_read(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
               CallerAddressRegisters saved) {
    return c_read_reporting(image, handle, buffer, length, &saved);
}

int16_t c_write(uint8_t *image, uint16_t handle, uint32_t buffer, int16_t length,
                CallerAddressRegisters saved) {
    return c_write_reporting(image, handle, buffer, length, &saved);
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
    exponent = (uint16_t)(exponent - FP_EXPONENT_BIAS);
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
 * The console writers, and the low-level write and seek the buffered layer sits on
 * ============================================================================================= */

/* One byte back, the way the 68000's `-(an)` wraps — `addr_add`'s counterpart. */
static uint32_t addr_back(uint32_t address) { return addr_add(address, (uint32_t)-1); }

/* A FILE record's fields. Every routine below reaches them through these six rather than spelling
 * `be16(image + file + 10)`, so a wrong offset is wrong in one place instead of thirty. */
static uint32_t file_ptr(const uint8_t *image, uint32_t file) {
    return be32(image + file + FILE_OFF_PTR);
}
static uint32_t file_base(const uint8_t *image, uint32_t file) {
    return be32(image + file + FILE_OFF_BASE);
}
static uint16_t file_flags(const uint8_t *image, uint32_t file) {
    return be16(image + file + FILE_OFF_FLAGS);
}
static int16_t file_count(const uint8_t *image, uint32_t file) {
    return (int16_t)be16(image + file + FILE_OFF_CNT);
}
static int16_t file_handle(const uint8_t *image, uint32_t file) {
    return (int16_t)be16(image + file + FILE_OFF_FD);
}
static int16_t file_bufsiz(const uint8_t *image, uint32_t file) {
    return (int16_t)be16(image + file + FILE_OFF_BUFSIZ);
}
static void file_set_flags(uint8_t *image, uint32_t file, uint16_t flags) {
    wr16(image + file + FILE_OFF_FLAGS, flags);
}
static void file_add_flags(uint8_t *image, uint32_t file, uint16_t flags) {
    file_set_flags(image, file, (uint16_t)(file_flags(image, file) | flags));
}

/* Store one byte through the stream's cursor and step it — the `move.l (a3),a0 / addq.l #1,(a3) /
 * move.b d0,(a0)` that c_putc and c_flsbuf both spell out. */
static void file_put_through_cursor(uint8_t *image, uint32_t file, uint8_t byte) {
    uint32_t cursor = file_ptr(image, file);

    wr32(image + file + FILE_OFF_PTR, addr_add(cursor, 1));
    image[cursor] = byte;
}

/* ...and the other direction, which c_filbuf and c_fread spell out the same way. */
static uint8_t file_take_through_cursor(uint8_t *image, uint32_t file) {
    uint32_t cursor = file_ptr(image, file);

    wr32(image + file + FILE_OFF_PTR, addr_add(cursor, 1));
    return image[cursor];
}

/* What a routine that answers with the character it just moved returns: the byte, zero-extended.
 * The original reaches it as `ext.w d0 / and.w #$ff`, which is the same thing said twice. */
static int16_t byte_answer(uint8_t byte) { return (int16_t)byte; }

/* c_conout_write @ 0x16b5e — `length` bytes to the console through GEMDOS Cconout, one call each,
 * with a carriage return inserted before every newline.
 *
 * ITS WHOLE SURFACE IS OFF-IMAGE: the ordered console-byte ledger (TRAP_MODEL.md, Phase 13) plus
 * the three trampoline save slots, whose RET_* says which of the two Cconout sites ran last. The
 * loop tests the count BEFORE decrementing it, so a length of 0 writes nothing and a negative one
 * runs 0x10000 + length times. */
void c_conout_write(uint8_t *image, uint32_t buffer, int16_t length,
                    CallerAddressRegisters saved) {
    while (length-- != 0) {
        uint8_t byte = image[buffer];

        if (byte == TEXT_MODE_LF) {
            trap_save_registers(image, saved, RET_C_CONOUT_CR);
            os_cconout(TEXT_MODE_CR);
        }
        trap_save_registers(image, saved, RET_C_CONOUT_BYTE);
        os_cconout(byte);
        buffer = addr_add(buffer, 1);
    }
}

/* ================================================================================================
 * The five wrappers that were waiting on the trap model — c_unlink @ 0x16868,
 * c_auxout_write @ 0x16ba8, c_prtout_write @ 0x16bd6, c_exit_pterm @ 0x14d16, c_exit @ 0x14d2c
 *
 * Each is one GEMDOS call the kit did not model until Phase 13 grew Fdelete, Cauxout, Cprnout and
 * Pterm (tools/recreate_kit/TRAP_MODEL.md). None of them is reachable in play; they are ported
 * because the C library is otherwise complete, and each one's own surface is now real.
 * ============================================================================================= */

/* c_unlink @ 0x16868 — GEMDOS Fdelete. The result is filed in `A_c_errno` as a word and answered as
 * 0 or -1, so a caller learns only whether it worked. Only `c_open`'s TRUNCATING arm calls it, and
 * `c_creat` never asks for that mode. */
int16_t c_unlink(uint8_t *image, uint32_t path, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_C_UNLINK_FDELETE);
    wr16(image + A_c_errno, (uint16_t)os_fdelete(image, path));
    return be16(image + A_c_errno) == 0 ? 0 : -1;
}

/* The shape `c_auxout_write` and `c_prtout_write` share exactly: `length` bytes to one character
 * device, one call each, with no translation of any kind. Like `c_conout_write` the loop tests the
 * count BEFORE decrementing it, so a length of 0 writes nothing and a negative one runs
 * 0x10000 + length times; unlike it, neither of these two touches the image at all, so the ordered
 * event ledger and the trampoline's save slots are the whole of what a case compares. */
static void write_to_character_device(uint8_t *image, uint32_t buffer, int16_t length,
                                      uint32_t return_pc, void (*send)(uint8_t),
                                      CallerAddressRegisters saved) {
    while (length-- != 0) {
        trap_save_registers(image, saved, return_pc);
        send(image[buffer]);
        buffer = addr_add(buffer, 1);
    }
}

/* GEMDOS Cprnout answers whether the byte went out and the original DISCARDS the answer, so this
 * adapter is what lets the two devices share the loop above. The model's printer never times out
 * (os.h), which is why nothing here tests it. */
static void send_to_printer(uint8_t byte) { (void)os_cprnout(byte); }

/* c_auxout_write @ 0x16ba8 — the AUX: arm of `c_write`. */
void c_auxout_write(uint8_t *image, uint32_t buffer, int16_t length,
                    CallerAddressRegisters saved) {
    write_to_character_device(image, buffer, length, RET_C_AUXOUT_BYTE, os_cauxout, saved);
}

/* c_prtout_write @ 0x16bd6 — and the PRT: arm. */
void c_prtout_write(uint8_t *image, uint32_t buffer, int16_t length,
                    CallerAddressRegisters saved) {
    write_to_character_device(image, buffer, length, RET_C_PRTOUT_BYTE, send_to_printer, saved);
}

/* c_exit_pterm @ 0x14d16 — GEMDOS Pterm, which does not return on the real machine.
 *
 * The model's `os_pterm` LATCHES the event ledger, so anything a reconstruction did afterwards
 * would be refused rather than silently accepted — which is what makes "returns" here safe to spell
 * (tools/recreate_kit/include/os.h, "ON THE REAL MACHINE THIS DOES NOT RETURN"). Every caller must
 * therefore return immediately, and both of this one's do. */
void c_exit_pterm(uint8_t *image, uint16_t code, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_C_EXIT_PTERM);
    os_pterm(code);
}

/* c_exit @ 0x14d2c — close every FILE the library still holds open, then terminate.
 *
 * The walk is over ALL C_IOB_SLOTS records rather than over the open ones: a slot is in use exactly
 * when its flags carry FILE_READ or FILE_WRITE, and the bound is the table's end address compared
 * as a LONG, which is how the original spells it. */
void c_exit(uint8_t *image, uint16_t code, CallerAddressRegisters *saved) {
    uint32_t file;

    for (file = A_c_iob; (int32_t)file < (int32_t)C_IOB_END; file = addr_add(file, C_IOB_STRIDE)) {
        if (be16(image + file + FILE_OFF_FLAGS) & FILE_IN_USE)
            c_fclose(image, file, saved);
    }
    c_exit_pterm(image, code, *saved);
}

/* c_write @ 0x16c04 — the library's `write(2)`: a pseudo-device's own byte writer, or GEMDOS
 * Fwrite with the text mode's newline expansion.
 *
 * The three pseudo-handles are answered before the fd-mode table is even consulted, and each is a
 * different GEMDOS character call; only CON:'s is modeled, so AUX: and PRT: refuse (see the
 * per-routine table in ../STATUS.md).
 *
 * IN TEXT MODE IT WRITES A RUN AT A TIME: everything up to a newline in one Fwrite, then the two
 * bytes of `A_crlf` in another, and the tail in a third. A short write on any of them abandons the
 * call with -1 and leaves `A_c_errno` holding the count GEMDOS did manage. The returned count
 * charges ONE byte for each newline, not the two that went out.
 *
 * A2 IS NOT THE CALLER'S AT ANY OF THE THREE SITES, and A1 is not either: A2 is the walk cursor
 * this routine carries, and A1 is where `c_getfdmode` left it — which this routine RECORDS in the
 * caller's register block, because every trap its callers reach afterwards files it too. */
int16_t c_write_reporting(uint8_t *image, uint16_t handle, uint32_t buffer, int16_t length,
                          CallerAddressRegisters *saved) {
    uint32_t cursor = buffer;       /* how far the walk has got */
    uint32_t run_start = buffer;    /* ...and where the bytes not yet written begin */
    int16_t written = 0;
    int32_t run;
    int binary;

    if (handle == FD_DEVICE_CON) {
        /* A2 ALREADY CARRIES THE BUFFER: `movea.l a3,a2` is the routine's second instruction, so
         * even this arm — which never advances the cursor — traps with A2 holding it. */
        c_conout_write(image, buffer, length, carrying_in_a2(*saved, cursor));
        return length;
    }
    if (handle == FD_DEVICE_AUX || handle == FD_DEVICE_PRT) {
        /* GEMDOS Cauxout (0x04) and Cprnout (0x05). Like CON:'s arm, A2 already carries the buffer:
         * `movea.l a3,a2` is the routine's second instruction. */
        if (handle == FD_DEVICE_AUX)
            c_auxout_write(image, buffer, length, carrying_in_a2(*saved, cursor));
        else
            c_prtout_write(image, buffer, length, carrying_in_a2(*saved, cursor));
        return length;
    }

    binary = c_getfdmode(image, handle) != 0;
    note_fd_modes_consulted(saved);     /* ...and A1 stays there for every trap from here up */
    if (binary) {
        cursor = addr_add(buffer, (uint32_t)(uint16_t)length);   /* nothing to translate */
    } else {
        while ((uint16_t)(cursor - buffer) < (uint16_t)length) {
            if (image[cursor] != TEXT_MODE_LF) {
                cursor = addr_add(cursor, 1);
                continue;
            }
            if ((int16_t)(cursor - run_start) > 0) {
                run = (int32_t)(int16_t)(cursor - run_start);
                trap_save_registers(image, carrying_in_a2(*saved, cursor),
                                    RET_C_WRITE_FWRITE_RUN);
                wr16(image + A_c_errno, (uint16_t)os_fwrite(image, handle, (uint32_t)run,
                                                            run_start));
                if ((int32_t)sign_ext16(be16(image + A_c_errno)) != run)
                    return -1;
                written = (int16_t)(written + (int16_t)be16(image + A_c_errno));
            }
            trap_save_registers(image, carrying_in_a2(*saved, cursor),
                                RET_C_WRITE_FWRITE_CRLF);
            wr16(image + A_c_errno, (uint16_t)os_fwrite(image, handle, CRLF_BYTES, A_crlf));
            if (be16(image + A_c_errno) != CRLF_BYTES)
                return -1;
            written = (int16_t)(written + 1);   /* the newline counts once, however it went out */
            cursor = addr_add(cursor, 1);
            run_start = cursor;
        }
    }
    run = (int32_t)(int16_t)(cursor - run_start);
    trap_save_registers(image, carrying_in_a2(*saved, cursor), RET_C_WRITE_FWRITE_TAIL);
    wr16(image + A_c_errno, (uint16_t)os_fwrite(image, handle, (uint32_t)run, run_start));
    if ((int32_t)sign_ext16(be16(image + A_c_errno)) != run)
        return -1;
    written = (int16_t)(written + (int16_t)be16(image + A_c_errno));
    wr16(image + A_c_errno, 0);
    return written;
}

/* c_lseek @ 0x159dc — GEMDOS Fseek, with a fallback for the seek GEMDOS refuses.
 *
 * The fallback is READ-VERIFIED AND UNREACHABLE HERE, and the two facts are the same fact: the trap
 * model REFUSES a seek it cannot serve rather than answering an error code (TRAP_MODEL.md, Phase
 * 13's "a refusal is not an error return"), so the seek below never comes back negative in a green
 * run. What the original then does — ask GEMDOS for the current position and the file's length,
 * re-base the offset against whichever the caller asked for, EXTEND the file by Fwriting
 * `offset - length` bytes read off its own uninitialised stack frame, and seek again — is recorded
 * in ../STATUS.md. It is not transcribed because its output would be those frame bytes, which no
 * reconstruction can reproduce and no case could compare. */
int32_t c_lseek(uint8_t *image, int16_t handle, int32_t offset, int16_t whence,
                CallerAddressRegisters saved) {
    int32_t position;

    if (handle < 0)
        return -1;                  /* the three pseudo-handles are all negative words */
    trap_save_registers(image, saved, RET_C_LSEEK_FSEEK);
    position = os_fseek(image, (uint32_t)offset, (uint16_t)handle, (uint16_t)whence);
    if (position >= 0)
        return position;
    return os_refused(-1);
}

/* ================================================================================================
 * The buffered `FILE` layer
 * ============================================================================================= */

/* Where an UNBUFFERED stream's single byte of buffer lives: `A_c_unbuf_chars` indexed by the
 * record's own slot number.
 *
 * THE SLOT NUMBER IS COMPUTED WITH `divs.w`, WHOSE REMAINDER LANDS IN D0'S HIGH WORD, and the
 * `adda.l` that follows adds the WHOLE longword — so a `file` that is not exactly on the 20-byte
 * stride lands 65536 bytes per leftover byte away. Transcribed rather than tidied; every real
 * caller passes a record address, where the remainder is 0. */
static uint32_t unbuffered_char_slot(uint32_t file) {
    int32_t distance = (int32_t)(file - A_c_iob);
    uint32_t quotient = (uint32_t)(distance / (int32_t)C_IOB_STRIDE) & 0xffffu;
    uint32_t remainder = (uint32_t)(distance % (int32_t)C_IOB_STRIDE) & 0xffffu;

    return addr_add(A_c_unbuf_chars, quotient | (remainder << 16));
}

/* The buffer both `c_filbuf` and `c_flsbuf` acquire on first use, spelt identically in each: an
 * unbuffered stream takes its own single byte, anything else asks GEMDOS for `bufsiz` and becomes
 * unbuffered on the spot if that fails. It is a LOOP because the failure arm sets UNBUFFERED and
 * falls back to the test, so the second pass takes the one-byte slot and the stream ends up with a
 * buffer either way. */
static void file_acquire_buffer(uint8_t *image, uint32_t file, CallerAddressRegisters saved) {
    while (file_base(image, file) == 0) {
        uint32_t buffer;
        int from_gemdos = 0;

        if (file_flags(image, file) & FILE_UNBUFFERED) {
            buffer = unbuffered_char_slot(file);
        } else {
            buffer = gemdos_malloc(image, sign_ext16((uint32_t)file_bufsiz(image, file)), saved);
            from_gemdos = 1;
        }
        wr32(image + file + FILE_OFF_PTR, buffer);
        wr32(image + file + FILE_OFF_BASE, buffer);
        if (from_gemdos)
            file_add_flags(image, file, buffer == 0 ? FILE_UNBUFFERED : FILE_MYBUF);
    }
}

/* c_fflush @ 0x14dc4 — push a write stream's buffer out, or drop a read stream's and put the file
 * cursor back where the caller thinks it is.
 *
 * The two directions are told apart by DIRTY rather than by READ/WRITE: a buffer holding bytes
 * nobody has written out goes to `c_write` (after an append stream seeks to the end), and the
 * stream's OFFSET — the file position its buffer starts at — advances by what went out. A read
 * stream instead seeks BACKWARDS by the count it never handed to the caller, so the GEMDOS cursor
 * ends where the reads stopped rather than where the buffer ended. Either way `ptr` goes back to
 * `base` and `cnt` to zero. */
int16_t c_fflush(uint8_t *image, uint32_t file, CallerAddressRegisters *saved) {
    int32_t buffered;

    if ((file_flags(image, file) & FILE_IN_USE) == 0)
        return -1;
    buffered = (int32_t)(file_ptr(image, file) - file_base(image, file));

    if (file_flags(image, file) & FILE_DIRTY) {
        if ((file_flags(image, file) & FILE_WRITE) == 0)
            return -1;
        if (file_flags(image, file) & FILE_APPEND)
            c_lseek(image, file_handle(image, file), 0, OS_FSEEK_FROM_END, *saved);
        if (c_write_reporting(image, (uint16_t)file_handle(image, file), file_base(image, file),
                              (int16_t)buffered, saved) == -1)
            return -1;
        file_set_flags(image, file, (uint16_t)(file_flags(image, file) & ~FILE_DIRTY));
        wr32(image + file + FILE_OFF_OFFSET,
             addr_add(be32(image + file + FILE_OFF_OFFSET), sign_ext16((uint32_t)buffered)));
    } else if (file_handle(image, file) > 0) {
        wr32(image + file + FILE_OFF_OFFSET,
             (uint32_t)c_lseek(image, file_handle(image, file),
                               (int32_t)sign_ext16((uint32_t)-file_count(image, file)),
                               OS_FSEEK_FROM_CURRENT, *saved));
    }
    wr32(image + file + FILE_OFF_PTR, file_base(image, file));
    wr16(image + file + FILE_OFF_CNT, 0);
    return 0;
}

/* c_fclose @ 0x14d72 — flush, hand a GEMDOS-allocated buffer back, mark the slot free, close. */
int16_t c_fclose(uint8_t *image, uint32_t file, CallerAddressRegisters *saved) {
    if (c_fflush(image, file, saved) != 0)
        return -1;
    if (file_flags(image, file) & FILE_MYBUF)
        gemdos_mfree(image, file_base(image, file), *saved);
    file_set_flags(image, file, 0);
    return c_close(image, (uint16_t)file_handle(image, file), *saved) != 0 ? -1 : 0;
}

/* c_filbuf @ 0x14e80 — refill an empty read buffer and hand back its first byte.
 *
 * It records where the buffer starts in the file (a GEMDOS Fseek of its own, not through
 * `c_lseek`), flushes stdout first if it is about to read the console — so a prompt appears before
 * the answer is typed — and asks `c_read` for ONE byte if the stream is unbuffered or line
 * buffered and for `bufsiz` otherwise.
 *
 * THE STDOUT FLUSH IS READ-VERIFIED, not covered: it fires only for a stream on the CON: handle,
 * and `c_read` refuses that handle two lines later (its console arm is `c_conin`, which the trap
 * model cannot serve from inside a buffered read). So no green case reaches it, and ../STATUS.md
 * records that rather than the comment above reading as tested behaviour.
 *
 * A short answer sets EOF, a negative one ERR, and both return -1.
 *
 * 0x14eac..0x14eb2 IS DEAD CODE: nothing branches there, and the two stores it holds (ptr = base,
 * cnt = 0) are the compiler's leftovers from a path the optimiser removed. */
int16_t c_filbuf(uint8_t *image, uint32_t file, CallerAddressRegisters *saved) {
    int16_t wanted;
    int16_t got;

    if ((file_flags(image, file) & FILE_READ) == 0)
        file_add_flags(image, file, FILE_ERR);
    if (file_flags(image, file) & FILE_AT_END)
        return -1;
    file_acquire_buffer(image, file, *saved);

    trap_save_registers(image, *saved, RET_C_FILBUF_FSEEK);
    wr32(image + file + FILE_OFF_OFFSET,
         (uint32_t)os_fseek(image, 0, (uint16_t)file_handle(image, file), OS_FSEEK_FROM_CURRENT));
    wr32(image + file + FILE_OFF_PTR, file_base(image, file));
    if ((uint16_t)file_handle(image, file) == FD_DEVICE_CON)
        c_fflush(image, A_c_stdout, saved);

    wanted = (file_flags(image, file) & FILE_BYTE_AT_A_TIME) ? 1 : file_bufsiz(image, file);
    got = (int16_t)c_read_reporting(image, (uint16_t)file_handle(image, file),
                                    file_ptr(image, file), (uint16_t)wanted, saved);
    wr16(image + file + FILE_OFF_CNT, (uint16_t)(got - 1));
    if (file_count(image, file) < 0) {
        file_add_flags(image, file, file_count(image, file) == -1 ? FILE_EOF : FILE_ERR);
        wr16(image + file + FILE_OFF_CNT, 0);
        return -1;
    }
    return byte_answer(file_take_through_cursor(image, file));
}

/* c_flsbuf @ 0x14fb0 — take the byte `c_putc` had no room for, and get the buffer emptied.
 *
 * THREE STREAMS, THREE SHAPES. An unbuffered one stores the byte and flushes it straight away; a
 * line-buffered one stores it and flushes only at a newline or a full buffer, so it can return
 * without a flush at all; a fully buffered one flushes what is already there FIRST and stores the
 * byte into the emptied buffer, which is why that arm is the only one that also reloads `cnt`. */
int16_t c_flsbuf(uint8_t *image, uint16_t byte, uint32_t file, CallerAddressRegisters *saved) {
    uint8_t stored = (uint8_t)byte;

    wr16(image + file + FILE_OFF_CNT, 0);
    if ((file_flags(image, file) & FILE_WRITE) == 0)
        file_add_flags(image, file, FILE_ERR);
    if (file_flags(image, file) & FILE_ERR)
        return -1;
    file_acquire_buffer(image, file, *saved);

    if (file_flags(image, file) & FILE_UNBUFFERED) {
        file_put_through_cursor(image, file, stored);
        file_add_flags(image, file, FILE_DIRTY);
    } else if (file_flags(image, file) & FILE_LINEBUF) {
        file_add_flags(image, file, FILE_DIRTY);
        file_put_through_cursor(image, file, stored);
        if (stored != TEXT_MODE_LF
            && (int16_t)(file_ptr(image, file) - file_base(image, file))
                   < file_bufsiz(image, file))
            return byte_answer(stored);
    }

    if (c_fflush(image, file, saved) != 0) {
        file_add_flags(image, file, FILE_ERR);
        return -1;
    }
    if (file_flags(image, file) & FILE_BYTE_AT_A_TIME) {
        wr16(image + file + FILE_OFF_CNT, 0);   /* the byte went out with the flush above */
        return byte_answer(stored);
    }
    wr16(image + file + FILE_OFF_CNT, (uint16_t)(file_bufsiz(image, file) - 1));
    file_add_flags(image, file, FILE_DIRTY);
    file_put_through_cursor(image, file, stored);
    return byte_answer(stored);
}

/* c_putc @ 0x150ee — the fast path, and `c_flsbuf` when the buffer is full.
 *
 * `cnt` is decremented BEFORE it is tested, so a stream whose count is 0 goes to c_flsbuf with -1
 * already stored — which is what makes the "flush then reload cnt" arm there correct. */
int16_t c_putc(uint8_t *image, uint16_t byte, uint32_t file, CallerAddressRegisters *saved) {
    int16_t remaining = (int16_t)(file_count(image, file) - 1);

    wr16(image + file + FILE_OFF_CNT, (uint16_t)remaining);
    if (remaining < 0)
        return c_flsbuf(image, byte, file, saved);
    file_put_through_cursor(image, file, (uint8_t)byte);
    return byte_answer((uint8_t)byte);
}

/* c_fread @ 0x15878 — `items` records of `size` bytes, through the buffered getc.
 *
 * IT COUNTS IN BYTES AND ANSWERS IN RECORDS. The loop runs `items * size` times as a WORD product,
 * taking one character each pass; when the stream ends part-way, the answer is the bytes actually
 * moved divided by the record size, so a partial record is not reported. A complete read answers
 * `items` (or 0 if the caller asked for a non-positive number of them) without looking at what the
 * loop counted. */
int16_t c_fread(uint8_t *image, uint32_t buffer, int16_t size, int16_t items, uint32_t file,
                CallerAddressRegisters *saved) {
    int16_t wanted = (int16_t)(items * size);
    int16_t remaining = wanted;

    while (remaining > 0) {
        int16_t byte;
        int16_t left = (int16_t)(file_count(image, file) - 1);

        wr16(image + file + FILE_OFF_CNT, (uint16_t)left);
        if (left >= 0) {
            byte = byte_answer(file_take_through_cursor(image, file));
        } else {
            byte = c_filbuf(image, file, saved);
        }
        if (byte == -1)
            return (int16_t)((int32_t)(int16_t)(wanted - remaining) / size);
        image[buffer] = (uint8_t)byte;
        buffer = addr_add(buffer, 1);
        remaining = (int16_t)(remaining - 1);
    }
    return items > 0 ? items : 0;
}

/* c_fopen @ 0x156e2 — parse the mode string, claim a free `c_iob` slot, open the file.
 *
 * THE MODE STRING IS READ IN THIS ORDER and no other: an optional leading 'b' (binary, which is the
 * only thing this library's 'b' means — it is a PREFIX here, so "rb" does not parse), then one of
 * r/w/a, then an optional '+' one byte further on. The game's own two calls pass "br".
 *
 * `A_c_fopen_slot_hint` is a record c_fopen should reuse before scanning; nothing in this program
 * ever sets it, so the scan is what always runs, and the hint is cleared again on the way past. */
uint32_t c_fopen(uint8_t *image, uint32_t path, uint32_t mode, CallerAddressRegisters saved) {
    uint32_t cursor = mode;
    uint16_t binary = 0;
    uint16_t update = 0;
    uint32_t file;
    int16_t handle;
    CallerAddressRegisters carrying_the_record;

    if (image[cursor] == FOPEN_MODE_BINARY_PREFIX) {
        binary = FD_MODE_BINARY;
        cursor = addr_add(cursor, 1);
    }
    if (image[cursor] != FOPEN_MODE_READ && image[cursor] != FOPEN_MODE_WRITE
        && image[cursor] != FOPEN_MODE_APPEND)
        return 0;

    file = be32(image + A_c_fopen_slot_hint);
    if (file == 0) {
        for (file = A_c_iob; (int32_t)file < (int32_t)C_IOB_END; file += C_IOB_STRIDE)
            if ((file_flags(image, file) & FILE_IN_USE) == 0)
                break;
    }
    if ((int32_t)file >= (int32_t)C_IOB_END)
        return 0;
    wr32(image + A_c_fopen_slot_hint, 0);
    file_set_flags(image, file, 0);
    /* A2 CARRIES THE RECORD from here on, so every trap the three openers below reach files it
     * rather than the caller's A2 (docs/agent-playbook.md §5, "derivable"). */
    carrying_the_record = carrying_in_a2(saved, file);

    if (image[addr_add(cursor, 1)] == FOPEN_MODE_UPDATE) {
        update = OPEN_MODE_WRITE;
        file_add_flags(image, file, FILE_IN_USE);
    }
    if (image[cursor] == FOPEN_MODE_WRITE) {
        handle = c_creat(image, path, binary, carrying_the_record);
        file_add_flags(image, file, FILE_WRITE);
    } else if (image[cursor] == FOPEN_MODE_APPEND) {
        handle = c_open(image, path, (uint16_t)(OPEN_MODE_WRITE | binary), carrying_the_record);
        if (handle == -1)
            handle = c_creat(image, path, binary, carrying_the_record);
        c_lseek(image, handle, 0, OS_FSEEK_FROM_END, carrying_the_record);
        file_add_flags(image, file, (uint16_t)(FILE_WRITE | FILE_APPEND));
    } else {
        handle = c_open(image, path, (uint16_t)(update | binary), carrying_the_record);
        file_add_flags(image, file, FILE_READ);
    }
    if (handle == -1) {
        file_set_flags(image, file, 0);
        return 0;
    }
    wr16(image + file + FILE_OFF_FD, (uint16_t)handle);
    wr16(image + file + FILE_OFF_CNT, 0);
    wr32(image + file + FILE_OFF_PTR, 0);
    wr32(image + file + FILE_OFF_BASE, 0);
    wr32(image + file + FILE_OFF_OFFSET,
         (uint32_t)c_lseek(image, handle, 0, OS_FSEEK_FROM_CURRENT, carrying_the_record));
    wr16(image + file + FILE_OFF_BUFSIZ, be16(image + A_c_bufsiz));
    return file;
}

/* ================================================================================================
 * The console reader
 * ============================================================================================= */

/* One byte to the console through GEMDOS Cconout, filing the site's own return address first —
 * `c_conin` echoes from six places and each is a distinct RET_*. */
static void conin_echo(uint8_t *image, uint8_t byte, uint32_t return_pc,
                       CallerAddressRegisters saved) {
    trap_save_registers(image, saved, return_pc);
    os_cconout(byte);
}

/* Append one byte to the line c_conin is gathering. The index is a WORD added to the buffer's
 * address, so a line longer than 32767 would run backwards; nothing bounds it. */
static void conin_append(uint8_t *image, uint8_t byte) {
    uint16_t length = be16(image + A_c_conin_length);

    wr16(image + A_c_conin_length, (uint16_t)(length + 1));
    image[addr_add(A_c_conin_buffer, sign_ext16(length))] = byte;
}

/* c_conin @ 0x16518 — the COOKED console reader: gather a whole line, echoing as it goes, then
 * hand it back one character at a time.
 *
 * The line is re-gathered only when the caller has taken all of the last one (read position ==
 * length), which is why both counters are reset before the gathering loop rather than after it.
 * RETURN stores a LINE FEED and echoes CR LF; BACKSPACE un-stores the last byte and echoes the VT52
 * "cursor left"; the end-of-file character is stored, echoed and then answered as -1 when the
 * caller reaches it. Everything else is stored and echoed as itself.
 *
 * TWO ARMS REFUSE. ^C runs `c_exit` @ 0x14d2c, whose tail is GEMDOS Pterm, and the AUX: handle is
 * GEMDOS Cauxin — neither is modeled (../STATUS.md's per-routine table). Note that the original
 * FALLS THROUGH from the ^C branch into the end-of-file test, so on a machine where Pterm returned
 * it would store and echo the ^C like any other byte. */
int16_t c_conin(uint8_t *image, uint16_t handle, CallerAddressRegisters saved) {
    uint32_t at;
    uint8_t byte;

    if (handle != FD_DEVICE_CON) {
        if (handle == FD_DEVICE_AUX)
            return (int16_t)os_refused(-1);   /* GEMDOS Cauxin (0x03), unmodeled */
        return -1;
    }
    if (be16(image + A_c_conin_read_pos) == be16(image + A_c_conin_length)) {
        wr16(image + A_c_conin_read_pos, 0);
        wr16(image + A_c_conin_length, 0);
        for (;;) {
            uint32_t key;
            uint16_t typed;

            trap_save_registers(image, saved, RET_C_CONIN_CRAWCIN);
            if (!os_crawcin(image, &key))
                return -1;              /* nothing staged: os_crawcin has refused the run already */
            typed = (uint16_t)key;              /* the low WORD: scancode << 16 | ascii */

            if (typed == CONIN_BACKSPACE) {
                if (be16(image + A_c_conin_length) != 0) {
                    wr16(image + A_c_conin_length,
                         (uint16_t)(be16(image + A_c_conin_length) - 1));
                    conin_echo(image, CONIN_ECHO_ESCAPE, RET_C_CONIN_ECHO_ESC, saved);
                    conin_echo(image, CONIN_ECHO_LEFT, RET_C_CONIN_ECHO_LEFT, saved);
                }
                continue;
            }
            if (typed == CONIN_RETURN) {
                conin_append(image, TEXT_MODE_LF);
                conin_echo(image, TEXT_MODE_CR, RET_C_CONIN_ECHO_EOL_CR, saved);
                conin_echo(image, TEXT_MODE_LF, RET_C_CONIN_ECHO_EOL_LF, saved);
                break;
            }
            if (typed == CONIN_INTERRUPT) {
                /* ^C ends the program. The original FALLS THROUGH into the end-of-file test from
                 * here, which is code the real machine never reaches — GEMDOS Pterm does not
                 * return — so the reconstruction returns instead. Running on would append to a
                 * ledger `os_pterm` has latched, and every entry after it is refused. */
                CallerAddressRegisters live = saved;

                c_exit(image, CONIN_EXIT_CODE, &live);
                return -1;
            }
            if (typed == CONIN_EOF) {
                conin_append(image, (uint8_t)typed);
                conin_echo(image, TEXT_MODE_CR, RET_C_CONIN_ECHO_EOF_CR, saved);
                conin_echo(image, TEXT_MODE_LF, RET_C_CONIN_ECHO_EOF_LF, saved);
                break;
            }
            conin_append(image, (uint8_t)typed);
            conin_echo(image, (uint8_t)typed, RET_C_CONIN_ECHO_CHAR, saved);
        }
    }
    at = addr_add(A_c_conin_buffer, sign_ext16(be16(image + A_c_conin_read_pos)));
    byte = image[at];
    if (byte == CONIN_EOF)
        return -1;
    wr16(image + A_c_conin_read_pos, (uint16_t)(be16(image + A_c_conin_read_pos) + 1));
    return (int16_t)(int8_t)byte;               /* SIGN-extended, unlike c_putc's answer */
}

/* ================================================================================================
 * The printf engine
 * ============================================================================================= */

/* Emit one byte through a `char **` and step it — the `movea.l (an),a0 / addq.l #1,(an) /
 * move.b d0,(a0)` that c_doprnt, c_fmt_integer and c_fmt_float all spell out at every one of their
 * exits. */
static void emit_byte(uint8_t *image, uint32_t *out, uint8_t byte) {
    image[*out] = byte;
    *out = addr_add(*out, 1);
}

/* c_fmt_getnum @ 0x161b8 — the decimal number in a `%` field's width or precision, or 0 for none.
 *
 * The digit test SIGN-EXTENDS the byte, so anything with bit 7 set ranks below '0' and stops the
 * scan; the accumulation is 16-bit and wraps. */
int16_t c_fmt_getnum(const uint8_t *image, uint32_t *cursor) {
    int16_t value = 0;

    while ((int16_t)(int8_t)image[*cursor] >= '0' && (int16_t)(int8_t)image[*cursor] <= '9') {
        value = (int16_t)(value * 10 + (int16_t)(int8_t)image[*cursor] - '0');
        *cursor = addr_add(*cursor, 1);
    }
    return value;
}

/* `asr.l #n` on a longword: shift right, filling from the sign bit. C's `>>` on a negative signed
 * value is implementation-defined, so the fill is spelt out. */
static uint32_t shift_right_arithmetic(uint32_t value, unsigned bits) {
    uint32_t fill = (int32_t)value < 0 ? (uint32_t)(~0u << (32 - bits)) : 0u;

    return (value >> bits) | fill;
}

/* c_fmt_integer @ 0x15e74 — one integer, in the base its conversion character names.
 *
 * OCTAL AND HEX NEVER DIVIDE: they mask and shift. The shift is `asr.l`, so a negative value comes
 * back with its top bits set, and the mask that follows is what clears them again — which is why it
 * is written as a sign-fill below rather than as C's implementation-defined right shift of a
 * negative, and why the mask is load-bearing rather than decorative. Decimal goes through `c_ldiv`,
 * twice per digit: once for the remainder, once for the quotient.
 *
 * A NEGATIVE VALUE IS SIGNED ONLY FOR `%d`. Every other conversion of a `short` argument masks the
 * sign extension back off (`%x` of -1 is "FFFF", not "FFFFFFFF"), and of a `long` argument leaves
 * it, so the digits come out of a value the base arithmetic then treats as negative.
 *
 * `base_when_conversion_unknown` is D7 as the caller left it — see PrintfCallerState in
 * include/clib.h. From `c_doprnt` it is the conversion character itself, and `c_doprnt` only ever
 * asks for the four below, so nothing in the program reaches it. */
void c_fmt_integer(uint8_t *image, uint16_t conversion, uint16_t is_long, uint32_t *out_cursor,
                   int32_t value, uint16_t base_when_conversion_unknown) {
    int16_t digits[FMT_DIGIT_SLOTS];
    uint16_t count = 0;
    uint16_t base = base_when_conversion_unknown;

    if (conversion == FMT_CONV_SIGNED || conversion == FMT_CONV_UNSIGNED)
        base = FMT_BASE_DECIMAL;
    else if (conversion == FMT_CONV_OCTAL)
        base = FMT_BASE_OCTAL;
    else if (conversion == FMT_CONV_HEX)
        base = FMT_BASE_HEX;

    if (value < 0) {
        if (conversion == FMT_CONV_SIGNED) {
            emit_byte(image, out_cursor, '-');
            value = -value;
        } else if (is_long == 0) {
            value = (int32_t)((uint32_t)value & 0xffffu);
        }
    }
    do {
        uint32_t quotient;
        uint32_t remainder;

        if (count >= FMT_DIGIT_SLOTS) {
            /* THE ORIGINAL OVERRUNS ITS OWN `-40(a6)` FRAME HERE and carries on; in C the same
             * write lands outside `digits` and takes the harness's process with it, which arrives
             * as a worker vanishing rather than as a difference. Only an unreachable base gets
             * here — the four this library names need at most 11 slots for a longword, and it is
             * `base_when_conversion_unknown` that can be 2 (32 digits) or 1 (never terminating) —
             * so refusing is the honest answer rather than a behaviour to reproduce. */
            os_refused(-1);
            return;
        }
        if (base == FMT_BASE_OCTAL) {
            digits[count++] = (int16_t)((uint32_t)value & 7u);
            value = (int32_t)(shift_right_arithmetic((uint32_t)value, 3) & FMT_OCTAL_STEP_MASK);
        } else if (base == FMT_BASE_HEX) {
            digits[count++] = (int16_t)((uint32_t)value & 0xfu);
            value = (int32_t)(shift_right_arithmetic((uint32_t)value, 4) & FMT_HEX_STEP_MASK);
        } else {
            c_ldiv(base, (uint32_t)value, &quotient, &remainder);
            digits[count++] = (int16_t)remainder;
            c_ldiv(base, (uint32_t)value, &quotient, &remainder);
            value = (int32_t)quotient;
        }
    } while (value != 0);

    while (count != 0) {
        int16_t digit = digits[--count];

        emit_byte(image, out_cursor,
                  (uint8_t)(digit < 10 ? digit + '0' : digit - 10 + FMT_HEX_LETTER_BASE));
    }
}

/* The eight bytes of the accumulator every float conversion goes through: `c_fcvt`, `c_fmt_float`
 * and `c_doprnt` each fill it from the caller's argument before doing anything else, and it is
 * ordinary image memory the differential compares. */
static void fp_acc_store(uint8_t *image, uint32_t value_high, uint32_t value_low) {
    wr32(image + A_fp_acc, value_high);
    wr32(image + A_fp_acc + 4, value_low);
}

/* c_fcvt @ 0x15588 — a double as `ndigits` decimal digits plus the power of ten they scale by.
 *
 * IT SCALES BEFORE IT CONVERTS: multiply or divide the value by ten (`A_fcvt_ten`, which
 * init_globals writes as 0x4024000000000001 — ten, one ulp high) until its binary exponent lands in
 * [-3, 0], counting the decimal places in `*decimal_point`. The mantissa is then a plain fraction,
 * and each digit is that fraction times ten with the integer part carried out — the original does
 * the multiply as `asl/roxl` three times and an `addx`, which is the 64-bit product below.
 *
 * ROUNDING IS DONE ON THE DIGITS, not on the value: 5 is added to the digit one past the last one
 * kept and the carry walks back down the string. A zero exponent — the package's only special case,
 * and its only test for a zero value — skips all of it and fills the buffer with '0'.
 *
 * The working copy lives at `CLIB_SCRATCH_FCVT_DOUBLE` because `fp_mul`/`fp_div` take IMAGE
 * addresses; see include/clib.h for why that address is in the band the differential drops. */
void c_fcvt(uint8_t *image, uint32_t value_high, uint32_t value_low, uint8_t *digits,
            int16_t *decimal_point, int16_t ndigits) {
    const uint32_t working = CLIB_SCRATCH_FCVT_DOUBLE;
    int16_t decimal_exponent = 0;
    int16_t binary_exponent = 0;
    int value_is_zero = 0;
    uint8_t *cursor = digits;

    if (ndigits < 0) {
        /* NOT TRANSCRIBED. The original's `dbf` would run 65536 times on a negative counter and
         * the round would then step BELOW the caller's buffer; the one caller floors its second
         * call at 1, and `c_fmt_float` refuses a precision that could produce a negative here, so
         * nothing in the program asks. Refusing reddens a case that finds a way rather than
         * writing out of bounds in the harness's own process. */
        os_refused(-1);
        *decimal_point = 0;
        return;
    }
    fp_acc_store(image, value_high, value_low);
    wr32(image + working, value_high);
    wr32(image + working + 4, value_low);

    for (;;) {
        binary_exponent = (int16_t)((be16(image + working) >> FP_EXPONENT_SHIFT)
                                    & FP_EXPONENT_BITS);
        if (binary_exponent == 0) {
            value_is_zero = 1;
            break;
        }
        binary_exponent = (int16_t)(binary_exponent - FP_EXPONENT_BIAS);
        if (binary_exponent > 0) {
            decimal_exponent = (int16_t)(decimal_exponent + 1);
            fp_div(image, working, A_fcvt_ten);
        } else if (binary_exponent < -3) {
            decimal_exponent = (int16_t)(decimal_exponent - 1);
            fp_mul(image, working, A_fcvt_ten);
        } else {
            break;
        }
    }

    if (value_is_zero) {
        int32_t written;

        cursor = digits;
        for (written = 0; written < (int32_t)ndigits; written++)
            *cursor++ = '0';
        *cursor = 0;
    } else {
        uint32_t fraction = (be32(image + working) << 11)
                          | (uint32_t)(be16(image + working + 4) >> 5);
        int16_t remaining;
        uint8_t *round;

        fraction |= 0x80000000u;                  /* the implicit leading one */
        if (binary_exponent != 0)
            fraction >>= (uint16_t)(-binary_exponent);
        *cursor++ = (uint8_t)('0' + (fraction >> 31));
        fraction <<= 1;
        /* ndigits + 1 of them: the original's `dbf` runs one more time than its counter says.
         * (A NEGATIVE ndigits is refused at the top: see the guard there.) */
        for (remaining = 0; remaining <= ndigits; remaining++) {
            uint64_t scaled = (uint64_t)fraction * 10u;

            *cursor++ = (uint8_t)('0' + (uint16_t)(scaled >> 32));
            fraction = (uint32_t)scaled;
        }
        *cursor = 0;

        /* Round half up at the digit one past the last one kept, carrying down the string. The
         * leading digit is 0 or 1, so the carry stops inside the buffer. */
        round = digits + ndigits + 1;
        if (digits[0] == '0')
            round++;
        round--;
        *round = (uint8_t)(*round + 5);
        while ((int16_t)(int8_t)*round > '9') {
            *round = (uint8_t)(*round - 10);
            round--;
            *round = (uint8_t)(*round + 1);
        }
        if (digits[0] == '0') {                   /* shift the leading zero off, one decade down */
            uint8_t *dst = digits;
            uint8_t *src = digits + 1;

            while ((*dst++ = *src++) != 0)
                ;
            decimal_exponent = (int16_t)(decimal_exponent - 1);
        }
        digits[ndigits] = 0;
    }
    *decimal_point = decimal_exponent;
}

/* `slt` after fp_dispatch's compare: LESS THAN is N differing from V, read out of the condition
 * codes `fp_cmp` parked at A_fp_ccr and `fp_dispatch` loaded back into the real CCR. */
static int fp_compared_less(const uint8_t *image) {
    uint16_t condition = be16(image + A_fp_ccr);

    return ((condition & CCR_N) != 0) != ((condition & CCR_V) != 0);
}

/* c_fmt_float @ 0x15fe0 — one double, as `%f` or as `%e`.
 *
 * `%g` IS `%e`: the routine tests for 'f' and takes the exponent form for everything else, so the
 * three conversions c_doprnt routes here are really two.
 *
 * THE `%f` PATH CONVERTS TWICE. The first `c_fcvt` (precision + 1 digits) is what finds the decimal
 * point and the sign; only then is the digit count knowable — decimal point plus precision plus
 * one, capped at `A_fcvt_max_digits`, which is 7 — so it converts again for the digits it will
 * actually print. Everything after that is placement: the digits before the point, zeros out to it,
 * the point itself, leading zeros of a fraction smaller than a tenth, and then digits or zeros to
 * the precision.
 *
 * THE `%e` PATH PRINTS ITS EXPONENT THROUGH `c_sprintf`, so the engine calls itself; the arguments
 * it pushes for that call are `CLIB_SCRATCH_EXPONENT_ARGS` here (include/clib.h says why). */
void c_fmt_float(uint8_t *image, uint16_t conversion, int16_t precision, uint32_t *out_cursor,
                 uint32_t value_high, uint32_t value_low, PrintfCallerState caller) {
    uint8_t digits[C_FCVT_DIGITS_MAX];
    int16_t decimal_point;
    int16_t remaining;              /* digits of the conversion still unprinted */
    int16_t taken = 0;              /* ...and how many have been */
    int negative;

    if (precision == (int16_t)FMT_NO_PRECISION)
        precision = FMT_FLOAT_DEFAULT_PRECISION;
    if (precision < 0 || precision + 1 > (int16_t)C_FCVT_NDIGITS_MAX) {
        /* THE PRECISION COMES FROM THE FORMAT STRING, so `%.70f` would ask c_fcvt for more digits
         * than `digits` holds and `%.65534f` for a negative count (c_fmt_getnum's accumulation is
         * 16-bit and wraps). The original overflows its own 30-byte frame from about 27 onwards,
         * which ../STATUS.md records as read-verified; the reconstruction refuses instead, well
         * above anything the original survives, rather than writing outside its array. */
        os_refused(-1);
        return;
    }
    fp_acc_store(image, value_high, value_low);
    fp_dispatch(image, (uint16_t)(FP_SOURCE_DOUBLE | FP_OP_CMP), A_fp_acc, A_fmt_float_zero,
                0, caller.status_high);
    negative = fp_compared_less(image);
    c_fcvt(image, value_high, value_low, digits, &decimal_point, (int16_t)(precision + 1));

    if (negative) {
        emit_byte(image, out_cursor, '-');
    }
    if (digits[0] == '0' && digits[1] == 0) {     /* the value is exactly zero: one '0' and done */
        emit_byte(image, out_cursor, digits[0]);
        return;
    }

    if (conversion == FMT_CONV_FIXED) {
        remaining = (int16_t)(decimal_point + precision + 1);
        if (remaining > (int16_t)be16(image + A_fcvt_max_digits))
            remaining = (int16_t)be16(image + A_fcvt_max_digits);
        c_fcvt(image, value_high, value_low, digits, &decimal_point,
               remaining < 0 ? 1 : remaining);
        while (remaining != 0 && decimal_point >= 0) {
            emit_byte(image, out_cursor, digits[taken++]);
            remaining = (int16_t)(remaining - 1);
            decimal_point = (int16_t)(decimal_point - 1);
        }
        while (decimal_point >= 0) {
            emit_byte(image, out_cursor, '0');
            decimal_point = (int16_t)(decimal_point - 1);
        }
        if (precision != 0) {
            emit_byte(image, out_cursor, FMT_PRECISION_MARK);
        }
        while (precision != 0 && decimal_point < -1) {
            emit_byte(image, out_cursor, '0');
            decimal_point = (int16_t)(decimal_point + 1);
            precision = (int16_t)(precision - 1);
        }
        while (precision-- != 0) {
            emit_byte(image, out_cursor, remaining > 0 ? digits[taken++] : (uint8_t)'0');
            remaining = (int16_t)(remaining - 1);
        }
        return;
    }

    emit_byte(image, out_cursor, digits[0]);
    if (precision != 0) {
        emit_byte(image, out_cursor, FMT_PRECISION_MARK);
    }
    remaining = 1;
    while (precision-- != 0) {
        emit_byte(image, out_cursor, digits[remaining++]);
    }
    emit_byte(image, out_cursor, 'E');
    wr32(image + CLIB_SCRATCH_EXPONENT_ARGS, A_fmt_float_exponent_format);
    wr16(image + CLIB_SCRATCH_EXPONENT_ARGS + C_EXPONENT_ARGS_OFF_VALUE, (uint16_t)decimal_point);
    {
        /* D7 IS THE DIGIT INDEX AT THIS CALL, not the conversion character — c_fmt_float has been
         * using D7 as its own counter since the loop above, and c_doprnt inherits whatever is
         * there. "%d" never ends in a bare `%`, so nothing reads it; it is passed rather than
         * invented because that is what the machine hands over. */
        PrintfCallerState nested = { (uint16_t)remaining, caller.status_high };

        c_sprintf(image, *out_cursor, CLIB_SCRATCH_EXPONENT_ARGS, nested);
    }
    *out_cursor = addr_add(*out_cursor, c_strlen(image, *out_cursor));
}

/* Lay a finished conversion out in a field `width` wide.
 *
 * LEFT JUSTIFICATION PADS AFTER; right justification does not pad before — it MOVES the bytes up to
 * the end of the field, backwards so an overlap is safe, and then fills the gap it opened. Either
 * way the cursor ends one past the field. `pad` is a space unless the format asked for '0'. */
static void doprnt_pad_field(uint8_t *image, uint32_t *out, uint32_t field_start, int16_t width,
                             int16_t left_justified, uint8_t pad) {
    int16_t moved = (int16_t)(*out - field_start);
    uint32_t last;
    uint32_t gap;

    if (moved >= width)
        return;
    if (left_justified) {
        int16_t missing = (int16_t)(width - moved);

        while (missing != 0) {
            emit_byte(image, out, pad);
            missing = (int16_t)(missing - 1);
        }
        return;
    }
    last = addr_add(field_start, sign_ext16((uint32_t)(int16_t)(width - 1)));
    gap = last;
    while (moved != 0) {
        image[gap] = image[addr_add(field_start, sign_ext16((uint32_t)(int16_t)(moved - 1)))];
        gap = addr_back(gap);
        moved = (int16_t)(moved - 1);
    }
    while ((int32_t)field_start <= (int32_t)gap) {
        image[field_start] = pad;
        field_start = addr_add(field_start, 1);
    }
    *out = addr_add(last, 1);
}

/* c_doprnt @ 0x1620c — the whole of the format engine: walk the format, copy what is not a
 * conversion, and place what is.
 *
 * `argp` POINTS AT THE FORMAT POINTER, not past it — this is a caller's argument list, and the
 * format string is its first element. The list is then walked by the SIZE THE CALLER PUSHED: two
 * bytes for a `short`, four for a `long` or a pointer, eight for a double. There is no `%%` and no
 * `*` width; an unrecognised conversion character is emitted as itself, which is how a literal `%`
 * is usually got out of this engine by accident.
 *
 * `caller.inherited_conversion` is what a format ending in a BARE `%` dispatches on: the load is
 * skipped when the conversion character is the terminator, leaving D7 as the caller left it. */
int32_t c_doprnt(uint8_t *image, uint32_t out, uint32_t argp, PrintfCallerState caller) {
    uint32_t start = out;
    uint32_t format = be32(image + argp);
    uint16_t conversion = caller.inherited_conversion;

    argp = addr_add(argp, 4);
    while (image[format] != 0) {
        uint32_t field_start;
        int16_t left_justified;
        int16_t width;
        int16_t precision;
        int16_t is_long;
        uint8_t pad;

        if (image[format] != FMT_ESCAPE) {
            emit_byte(image, &out, image[format]);
            format = addr_add(format, 1);
            continue;
        }
        format = addr_add(format, 1);

        left_justified = 0;
        precision = (int16_t)FMT_NO_PRECISION;
        is_long = 0;
        pad = ' ';
        if (image[format] == FMT_FLAG_LEFT) {
            left_justified = 1;
            format = addr_add(format, 1);
        }
        if (image[format] == FMT_FLAG_ZERO) {
            pad = FMT_FLAG_ZERO;
            format = addr_add(format, 1);
        }
        width = c_fmt_getnum(image, &format);
        if (image[format] == FMT_PRECISION_MARK) {
            format = addr_add(format, 1);
            precision = c_fmt_getnum(image, &format);
        }
        if (image[format] == FMT_LONG_MARK) {
            is_long = 1;
            format = addr_add(format, 1);
        }
        if (image[format] != 0) {
            conversion = (uint16_t)(int16_t)(int8_t)image[format];
            format = addr_add(format, 1);
        }
        field_start = out;

        if (conversion == FMT_CONV_SIGNED || conversion == FMT_CONV_OCTAL
            || conversion == FMT_CONV_HEX || conversion == FMT_CONV_UNSIGNED) {
            int32_t value = is_long ? (int32_t)be32(image + argp)
                                    : (int32_t)(int16_t)be16(image + argp);

            c_fmt_integer(image, conversion, (uint16_t)is_long, &out, value, conversion);
            argp = addr_add(argp, is_long ? 4 : 2);
        } else if (conversion == FMT_CONV_CHAR) {
            emit_byte(image, &out, image[addr_add(argp, 1)]);   /* the low byte of the word */
            argp = addr_add(argp, 2);
        } else if (conversion == FMT_CONV_STRING) {
            uint32_t text = be32(image + argp);
            int16_t left_to_copy = precision;

            argp = addr_add(argp, 4);
            while (left_to_copy != 0 && image[text] != 0) {
                emit_byte(image, &out, image[text]);
                text = addr_add(text, 1);
                left_to_copy = (int16_t)(left_to_copy - 1);
            }
        } else if (conversion == FMT_CONV_EXPONENT || conversion == FMT_CONV_FIXED
                   || conversion == FMT_CONV_GENERAL) {
            uint32_t value_high = be32(image + argp);
            uint32_t value_low = be32(image + argp + 4);

            fp_acc_store(image, value_high, value_low);   /* the argument goes through it first */
            c_fmt_float(image, conversion, precision, &out, value_high, value_low, caller);
            argp = addr_add(argp, 8);
        } else {
            emit_byte(image, &out, (uint8_t)conversion);
        }
        doprnt_pad_field(image, &out, field_start, width, left_justified, pad);
    }
    image[out] = 0;
    return (int32_t)(out - start);
}

/* c_sprintf @ 0x164d8 — c_doprnt onto the caller's own buffer, and its count.
 *
 * `argp` is the address of c_sprintf's SECOND argument, so the format string and the values after
 * it are one list to c_doprnt. */
int32_t c_sprintf(uint8_t *image, uint32_t out, uint32_t argp, PrintfCallerState caller) {
    return c_doprnt(image, out, argp, caller);
}

/* c_fputs @ 0x164ee — every byte of a string through c_putc, and no terminator. */
void c_fputs(uint8_t *image, uint32_t text, uint32_t file, CallerAddressRegisters *saved) {
    while (image[text] != 0) {
        c_putc(image, (uint16_t)(int16_t)(int8_t)image[text], file, saved);
        text = addr_add(text, 1);
    }
}

/* c_vfprintf @ 0x16496 — format into a 256-byte buffer, then push the buffer at a stream.
 *
 * There is no bound on what c_doprnt writes into that buffer: a format that produces more than 256
 * bytes runs off the end of the original's frame. The reconstruction's buffer is
 * `CLIB_SCRATCH_VFPRINTF_BUFFER` (include/clib.h says why it is where it is); ../STATUS.md records the
 * overflow as read-verified rather than reproduced. */
int16_t c_vfprintf(uint8_t *image, uint32_t file, uint32_t argp, PrintfCallerState caller,
                   CallerAddressRegisters *saved) {
    int16_t count = (int16_t)c_doprnt(image, CLIB_SCRATCH_VFPRINTF_BUFFER, argp, caller);

    c_fputs(image, CLIB_SCRATCH_VFPRINTF_BUFFER, file, saved);
    return count;
}

/* c_printf @ 0x164c2 — c_vfprintf on `c_stdout`. The program's ONE call site passes the "Please
 * reboot in LOW REZ" message and no conversions at all (`main` @ 0x100dc). */
int16_t c_printf(uint8_t *image, uint32_t argp, PrintfCallerState caller,
                 CallerAddressRegisters *saved) {
    return c_vfprintf(image, A_c_stdout, argp, caller, saved);
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

/* The buffered layer and the console. Every one of these traps somewhere, so each takes the
 * caller's A1/A2 the way the file layer's do. */
uint32_t g_c_fopen(uint8_t *image, uint32_t path, uint32_t mode, uint32_t a1, uint32_t a2) {
    return c_fopen(image, path, mode, caller_registers(a1, a2));
}

int32_t g_c_fclose(uint8_t *image, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_fclose(image, file, &saved);
}

int32_t g_c_fflush(uint8_t *image, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_fflush(image, file, &saved);
}

int32_t g_c_filbuf(uint8_t *image, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_filbuf(image, file, &saved);
}

int32_t g_c_flsbuf(uint8_t *image, uint32_t byte, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_flsbuf(image, (uint16_t)byte, file, &saved);
}

int32_t g_c_putc(uint8_t *image, uint32_t byte, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_putc(image, (uint16_t)byte, file, &saved);
}

int32_t g_c_fread(uint8_t *image, uint32_t buffer, uint32_t size, uint32_t items, uint32_t file,
                  uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_fread(image, buffer, (int16_t)size, (int16_t)items, file, &saved);
}

int32_t g_c_lseek(uint8_t *image, uint32_t handle, uint32_t offset, uint32_t whence,
                  uint32_t a1, uint32_t a2) {
    return c_lseek(image, (int16_t)handle, (int32_t)offset, (int16_t)whence,
                   caller_registers(a1, a2));
}

int32_t g_c_write(uint8_t *image, uint32_t handle, uint32_t buffer, uint32_t length,
                  uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_write_reporting(image, (uint16_t)handle, buffer, (int16_t)length, &saved);
}

void g_c_auxout_write(uint8_t *image, uint32_t buffer, uint32_t length, uint32_t a1, uint32_t a2) {
    c_auxout_write(image, buffer, (int16_t)length, caller_registers(a1, a2));
}

void g_c_prtout_write(uint8_t *image, uint32_t buffer, uint32_t length, uint32_t a1, uint32_t a2) {
    c_prtout_write(image, buffer, (int16_t)length, caller_registers(a1, a2));
}

int32_t g_c_unlink(uint8_t *image, uint32_t path, uint32_t a1, uint32_t a2) {
    return c_unlink(image, path, caller_registers(a1, a2));
}

void g_c_exit_pterm(uint8_t *image, uint32_t code, uint32_t a1, uint32_t a2) {
    c_exit_pterm(image, (uint16_t)code, caller_registers(a1, a2));
}

/* `c_exit` threads the register block by POINTER for `c_fclose`'s reason: each close leaves A1 at
 * `A_c_errno` and the traps after it file that, not what the caller was holding. */
void g_c_exit(uint8_t *image, uint32_t code, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters live = caller_registers(a1, a2);

    c_exit(image, (uint16_t)code, &live);
}

void g_c_conout_write(uint8_t *image, uint32_t buffer, uint32_t length, uint32_t a1, uint32_t a2) {
    c_conout_write(image, buffer, (int16_t)length, caller_registers(a1, a2));
}

int32_t g_c_conin(uint8_t *image, uint32_t handle, uint32_t a1, uint32_t a2) {
    return c_conin(image, (uint16_t)handle, caller_registers(a1, a2));
}

/* The printf engine. `cursor` is the image cell holding the `char *` the emitters advance — the
 * original's is its caller's argument slot, which is stack the differential drops, so a case puts
 * one in ordinary image memory and the glue does the round trip. */
int32_t g_c_fmt_getnum(uint8_t *image, uint32_t cursor) {
    uint32_t at = be32(image + cursor);
    int16_t value = c_fmt_getnum(image, &at);

    wr32(image + cursor, at);
    return value;
}

void g_c_fmt_integer(uint8_t *image, uint32_t conversion, uint32_t is_long, uint32_t cursor,
                     uint32_t value, uint32_t base_when_conversion_unknown) {
    uint32_t at = be32(image + cursor);

    c_fmt_integer(image, (uint16_t)conversion, (uint16_t)is_long, &at, (int32_t)value,
                  (uint16_t)base_when_conversion_unknown);
    wr32(image + cursor, at);
}

void g_c_fmt_float(uint8_t *image, uint32_t conversion, uint32_t precision, uint32_t cursor,
                   uint32_t value_high, uint32_t value_low, uint32_t inherited_conversion,
                   uint32_t status_high) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };
    uint32_t at = be32(image + cursor);

    c_fmt_float(image, (uint16_t)conversion, (int16_t)precision, &at, value_high, value_low,
                caller);
    wr32(image + cursor, at);
}

/* c_fcvt writes its digits through a `char *` and its decimal exponent through a `short *`; both
 * are frame locals in the original, and a case gives it image cells instead. */
void g_c_fcvt(uint8_t *image, uint32_t value_high, uint32_t value_low, uint32_t digits,
              uint32_t decimal_point, uint32_t ndigits) {
    int16_t exponent = 0;

    c_fcvt(image, value_high, value_low, image + digits, &exponent, (int16_t)ndigits);
    wr16(image + decimal_point, (uint16_t)exponent);
}

int32_t g_c_doprnt(uint8_t *image, uint32_t out, uint32_t argp, uint32_t inherited_conversion,
                   uint32_t status_high) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };

    return c_doprnt(image, out, argp, caller);
}

int32_t g_c_sprintf(uint8_t *image, uint32_t out, uint32_t argp, uint32_t inherited_conversion,
                    uint32_t status_high) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };

    return c_sprintf(image, out, argp, caller);
}

void g_c_fputs(uint8_t *image, uint32_t text, uint32_t file, uint32_t a1, uint32_t a2) {
    CallerAddressRegisters saved = caller_registers(a1, a2);

    c_fputs(image, text, file, &saved);
}

int32_t g_c_vfprintf(uint8_t *image, uint32_t file, uint32_t argp, uint32_t inherited_conversion,
                     uint32_t status_high, uint32_t a1, uint32_t a2) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };

    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_vfprintf(image, file, argp, caller, &saved);
}

int32_t g_c_printf(uint8_t *image, uint32_t argp, uint32_t inherited_conversion,
                   uint32_t status_high, uint32_t a1, uint32_t a2) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };

    CallerAddressRegisters saved = caller_registers(a1, a2);

    return c_printf(image, argp, caller, &saved);
}

void g_crt0_setup_args(uint8_t *image, uint32_t command_tail) {
    crt0_setup_args(image, command_tail);
}
