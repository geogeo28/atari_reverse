/* clib.h — the Alcyon/DRI C runtime linked into Bubble Ghost: the OS trap glue, the free-list
 * allocator, the low-level file layer and the software floating-point package.
 *
 * This is the compiler's own library rather than the game's code, so almost nothing here is
 * BubbleGhost-specific — but every address is, because the linker placed the library's state in
 * this program's BSS and DATA. Addresses are absolute (`include/globals.h`'s A4_BASE + the `n(a4)`
 * displacement the instructions carry), the way every subsystem header in this project spells them.
 *
 * WHAT VERIFIES EACH GROUP is in ../STATUS.md's "Verified — clib" section, one row per routine.
 */
#ifndef BG_CLIB_H
#define BG_CLIB_H

#include <stdint.h>

#include "machine.h"
#include "globals.h"

/* ================================================================================================
 * The OS trap trampolines — `gemdos_trap` @ 0x15e58, `xbios_trap` @ 0x15e3c
 *
 * Every GEMDOS and XBIOS call in the program goes through one of these six-instruction stubs. Each
 * parks A1, A2 and its own return address in three fixed longwords, traps, restores the two address
 * registers and returns — because TOS is free to clobber A1/A2 and the Alcyon compiler is not. The
 * three slots are the trampolines' WHOLE image effect, which is what makes them verifiable at all:
 * a reconstruction cannot execute a trap, so each wrapper below writes these three and then calls
 * the kit's model of the call itself (tools/recreate_kit/include/os.h).
 * ============================================================================================= */

/* The two address registers a trampoline parks, as the CALLER left them. The C ABI carries no such
 * thing, so every wrapper that traps takes them as an argument and files them where the trampoline
 * does — which is the whole of what a reconstruction can reproduce about the trap glue, and what
 * makes `gemdos_trap` and `xbios_trap` verifiable rather than merely read. */
typedef struct {
    uint32_t a1;
    uint32_t a2;
} CallerAddressRegisters;

#define A_trap_saved_ret 0x1e932u   /* longword: the trampoline's own return address, popped off the
                                     * stack so the selector word ends up at 2(sp) where TOS reads
                                     * it, and pushed back before the `rts` */
#define A_trap_saved_a2  0x1e936u   /* longword: A2 across the trap */
#define A_trap_saved_a1  0x1e93au   /* longword: A1 across the trap */

/* Where each wrapper's `jsr` to the trampoline returns to — the byte after the `jsr`, which is what
 * the trampoline files in A_trap_saved_ret. One per wrapper because it is a call-site constant, not
 * a value any of them computes. */
/* `xbios_trap` has no RET_* of its own: it is entered from all over the program, so the address it
 * files is its CALLER's and the case declares it. */
#define RET_GEMDOS_MALLOC          0x15c92u
#define RET_GEMDOS_MFREE           0x15ca8u
#define RET_GEMDOS_MALLOC_OR_FAIL  0x167e0u
#define RET_C_CLOSE_FCLOSE         0x14c64u
#define RET_C_CREAT_FCREATE        0x14cc2u
#define RET_C_OPEN_FOPEN           0x15e0au
#define RET_C_READ_FREAD_FIRST     0x166feu   /* the read that fills the caller's buffer */
#define RET_C_READ_FREAD_REFILL    0x16762u   /* ...and the text mode's top-up read */

/* THE TRAMPOLINE'S WHOLE IMAGE EFFECT, in one place. Both stubs write these three longwords and
 * nothing else, so every wrapper that traps calls this instead of spelling the three stores again —
 * `src/clib.c`'s wrappers and `src/sound.c`'s two `Supexec` callers, which carried a second copy
 * until this moved here. It is a header inline rather than a function because it is the only thing
 * two translation units share and a `.c` for three stores would be its own file. */
static inline void trap_save_registers(uint8_t *image, CallerAddressRegisters saved,
                                       uint32_t return_pc) {
    wr32(image + A_trap_saved_a1, saved.a1);
    wr32(image + A_trap_saved_a2, saved.a2);
    wr32(image + A_trap_saved_ret, return_pc);
}

/* ================================================================================================
 * Shared C-library state
 * ============================================================================================= */

#define A_c_errno 0x1ea6eu          /* word: the last GEMDOS return code the library saw */

/* ================================================================================================
 * The free-list allocator — `c_malloc` @ 0x15b54, `c_free` @ 0x15bfe, `c_morecore` @ 0x15af2
 *
 * A textbook K&R circular free list. Every block carries a six-byte header — a `next` pointer and a
 * size in GRANULES — and `c_malloc` hands back the address just past the header of the block it
 * carved. The list is kept in ascending address order and `c_free` coalesces with the neighbour on
 * each side.
 * ============================================================================================= */

#define A_c_malloc_freelist 0x1ea70u /* longword: the roving pointer c_malloc searches from. Zero
                                      * until the first allocation, which self-initialises the list
                                      * to the empty sentinel below */
#define A_c_malloc_sentinel 0x1ea74u /* the zero-length block the empty list points at: its `next`
                                      * is itself and its size word (0x1ea78) is 0 */

#define MALLOC_GRANULE      6u       /* bytes per granule — also the header's own size, so a block
                                      * of n granules spans n*6 bytes INCLUDING its header */
#define FREE_OFF_NEXT       0u       /* longword: the next free block, ascending, wrapping */
#define FREE_OFF_SIZE       4u       /* word: the block's size in granules, header included */
#define FREE_HEADER_BYTES   6u       /* = MALLOC_GRANULE; what c_malloc adds to reach the payload */

/* c_morecore rounds its request up to a whole number of these and asks GEMDOS for that many
 * granules — 0x418 granules is 6,288 bytes, the library's arena quantum. */
#define MORECORE_QUANTUM_GRANULES 0x418u

/* ================================================================================================
 * The fd-mode side table — `c_setfdmode` @ 0x15cae, `c_clearfdmode` @ 0x15cfa, `c_getfdmode` 0x15d36
 *
 * GEMDOS handles carry no text/binary flag, so the library keeps its own: 76 (handle, mode) word
 * pairs, searched linearly. `c_read` and `c_write` ask it whether to translate CR/LF.
 * ============================================================================================= */

#define A_fd_mode_table   0x1e93eu
#define FD_MODE_SLOTS     0x4cu      /* 76 — the loop bound all three routines carry */
#define FD_MODE_ENTRY     4u         /* handle word, then mode word */
#define FD_MODE_OFF_FD    0u
#define FD_MODE_OFF_MODE  2u
#define FD_MODE_BINARY    0x2000u    /* the one mode bit anything sets; 0 means text */

/* WHERE c_getfdmode READS WHEN THE HANDLE IS NOT IN THE TABLE. Its loop tests, steps, and stops
 * when the cursor reaches the table's end — so an exhausted search leaves the cursor one entry PAST
 * the last slot and the `move.w 2(a0),d0` that follows reads a word that is not in the table at
 * all. `A_fd_mode_table + FD_MODE_SLOTS * FD_MODE_ENTRY + FD_MODE_OFF_MODE` is A_c_malloc_freelist,
 * so an unknown handle is answered with the HIGH HALF OF THE ALLOCATOR'S ROVING POINTER: zero until
 * something has allocated, and the arena's high word afterwards. Reproduced rather than fixed, and
 * src/clib.c holds the `_Static_assert` that keeps the two addresses equal.
 */

/* ================================================================================================
 * The low-level file layer — `c_open` 0x15d64, `c_creat` 0x14c7a, `c_close` 0x14c3c, `c_read` 0x1667c
 *
 * Three names are intercepted before GEMDOS ever sees them and answered with a pseudo-handle, which
 * is why the handles are large NEGATIVE words: a real GEMDOS handle is a small positive number, so
 * `handle > FD_DEVICE_CON` (a SIGNED word compare) is the library's test for "a real file".
 * ============================================================================================= */

#define FD_DEVICE_CON 0x8300u        /* "CON:" — the console, as a word: -32000 */
#define FD_DEVICE_AUX 0x82ffu        /* "AUX:" — the serial port */
#define FD_DEVICE_PRT 0x82feu        /* "PRT:" — the printer */

/* The two copies of the device-name table the linker emitted, one per caller. Each is three
 * NUL-terminated names on a six-byte stride, in CON:/AUX:/PRT: order. */
#define A_creat_device_names 0x251c6u   /* c_creat compares against this copy */
#define A_open_device_names  0x251ecu   /* ...and c_open against this one */
#define DEVICE_NAME_STRIDE   6u

#define OPEN_MODE_TRUNCATE 0x0001u   /* bit 0: unlink the file first (GEMDOS Fdelete) */
#define OPEN_MODE_WRITE    0x0002u   /* what c_creat asks c_open for */

#define TEXT_MODE_CR 0x0du           /* the byte c_read's text path drops */

/* ================================================================================================
 * The software floating-point package — `fp_dispatch` @ 0x153fe and the seven routines it calls
 *
 * THE WORKING FORM IS NOT AN IEEE DOUBLE. Every arithmetic routine unpacks its operands into a
 * 32-BIT mantissa whose implicit leading 1 sits in bit 31 and an 11-bit biased exponent, does its
 * work there, and repacks. The 21 lowest mantissa bits of an IEEE double are therefore DISCARDED on
 * the way in and rebuilt as zeros on the way out — this package carries about 32 bits of precision,
 * not 53, and that is what decides the demo/slideshow ranges the front end computes from
 * XBIOS Random (../names.txt, the plate at 0x115d6).
 * ============================================================================================= */

#define A_fp_op_table       0x1ea7eu /* 7 longwords, indexed by fp_dispatch's low opcode byte. Each
                                      * points into the `jmp` island at BG_LOAD_BASE rather than at
                                      * the routine, which is how the linker resolved them */
#define A_fp_acc            0x1ea9au /* the 8-byte accumulator fp_acc_load_long / fp_acc_to_long use */
#define A_fp_sub_sign_flag  0x1eaa2u /* word: 0x8000 when fp_sub entered the shared add body, 0 when
                                      * fp_add did. The body XORs it back into the SOURCE's sign
                                      * word on the way out, undoing the flip fp_sub made */
#define A_fp_ccr            0x1eaa4u /* word: the whole SR fp_cmp captured, which fp_dispatch loads
                                      * back into the real CCR so a float compare can be followed by
                                      * an ordinary Bcc */

#define FP_OP_ADD          0u
#define FP_OP_SUB          1u
#define FP_OP_MUL          2u
#define FP_OP_DIV          3u
#define FP_OP_CMP          4u
#define FP_OP_SELECTOR     0x00ffu   /* the low byte of fp_dispatch's opcode word indexes the table */
#define FP_OP_SOURCE_KIND  0xff00u   /* ...and the high byte says what the source operand IS */
#define FP_SOURCE_SHORT    0x2000u   /* a 16-bit int, widened through fp_long_to_double */
#define FP_SOURCE_LONG     0x2800u   /* a 32-bit int, likewise */
#define FP_SOURCE_FLOAT    0x1000u   /* a 32-bit float, widened through fp_float_to_double */
/* Anything else — 0x0800 is what the game's own four call sites carry — means the source already IS
 * an eight-byte double and is passed through untouched. */

#define FP_EXPONENT_BITS   0x07ffu   /* the 11-bit biased exponent, once shifted down out of word 0 */
#define FP_EXPONENT_SHIFT  4u        /* ...and how far down: the mantissa's top nibble is below it */
#define FP_SIGN_BIT        0x8000u   /* word 0's bit 15 */
#define FP_BIAS_MUL        0x03ffu   /* fp_mul's exponent fold: e = ea - BIAS + eb */
#define FP_BIAS_DIV        0x03feu   /* fp_div's:                e = ea - eb + this */
#define FP_LONG_EXPONENT   0x041du   /* fp_long_to_double presets this before normalising */
#define FP_TRUNC_EXPONENT  0x041eu   /* fp_double_to_long's "the point is here" exponent */

/* fp_pack_double's rounding: bit 8 is the guard bit, and the mask below is the guard bit plus the
 * sticky bits under it — an exact halfway with nothing beneath it rounds to even by doing nothing. */
#define FP_ROUND_GUARD_DOUBLE  0x0100u
#define FP_ROUND_STICKY_DOUBLE 0x02ffu
#define FP_ROUND_INCREMENT_DOUBLE 0x0100u
#define FP_ROUND_INCREMENT_FLOAT  0x0200u   /* the single-precision tail rounds one bit higher */

/* ================================================================================================
 * Cores and glue
 * ============================================================================================= */

/* --- string and 32-bit arithmetic --- */
uint32_t c_strlen(const uint8_t *image, uint32_t str);
int16_t  c_strcmp(const uint8_t *image, uint32_t left, uint32_t right);
void     c_ldiv(uint32_t divisor, uint32_t dividend, uint32_t *quotient, uint32_t *remainder);
uint32_t c_lmul(uint32_t left, uint32_t right);

/* --- the fd-mode side table --- */
void     c_setfdmode(uint8_t *image, uint16_t handle, uint16_t mode);
void     c_clearfdmode(uint8_t *image, uint16_t handle);
uint16_t c_getfdmode(const uint8_t *image, uint16_t handle);

/* --- the allocator --- */
uint32_t c_malloc(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved);
void     c_free(uint8_t *image, uint32_t payload);
uint32_t c_morecore(uint8_t *image, uint16_t granules_wanted, CallerAddressRegisters saved);
uint32_t gemdos_malloc(uint8_t *image, uint32_t bytes, CallerAddressRegisters saved);
uint32_t gemdos_mfree(uint8_t *image, uint32_t block, CallerAddressRegisters saved);
uint32_t gemdos_malloc_or_fail(uint8_t *image, uint16_t bytes, CallerAddressRegisters saved);

/* --- the file layer --- */
int16_t  c_open(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved);
int16_t  c_creat(uint8_t *image, uint32_t path, uint16_t mode, CallerAddressRegisters saved);
int16_t  c_close(uint8_t *image, uint16_t handle, CallerAddressRegisters saved);
int32_t  c_read(uint8_t *image, uint16_t handle, uint32_t buffer, uint16_t length,
                CallerAddressRegisters saved);

/* --- the floating-point package --- */
void     fp_pack_double(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent);
void     fp_pack_float(uint8_t *image, uint32_t dst, uint32_t mantissa, uint16_t exponent);
void     fp_long_to_double(uint8_t *image, uint32_t operand);
void     fp_float_to_double(uint8_t *image, uint32_t operand);
void     fp_double_to_long(uint8_t *image, uint32_t operand);
void     fp_acc_load_long(uint8_t *image, uint32_t value);
uint32_t fp_acc_to_long(uint8_t *image);
void     fp_add(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_sub(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_mul(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_div(uint8_t *image, uint32_t dst, uint32_t src);
void     fp_cmp(uint8_t *image, uint32_t left, uint32_t right, uint16_t status_high);
void     fp_dispatch(uint8_t *image, uint16_t opcode, uint32_t dst, uint32_t src,
                     uint32_t widen_scratch, uint16_t status_high);

/* --- the XBIOS trampoline, exercised through one modeled call --- */
uint32_t xbios_physbase(uint8_t *image, CallerAddressRegisters saved, uint32_t return_pc);

#endif /* BG_CLIB_H */
