/* bubble_backend.c — the GEM door, and the three libc functions a freestanding build owes GCC.
 *
 * THE GEM DOOR IS THE INTERESTING HALF. `os_vdi`/`os_aes` (shim_include/os.h) call in here rather
 * than trapping directly, because a `trap #2` cannot be made with the block the game built: every
 * pointer in it is an IMAGE OFFSET. That is exactly right in the differential's world, where the
 * image IS the machine's memory and starts at 0, and exactly right on the original, whose arrays
 * are absolute against the base it runs at. Here the VDI would take `0x236f0` for an address and
 * read its `contrl` out of the 68000's vector page.
 *
 * THE TRANSLATION IS PATCH-TRAP-RESTORE, and the shape is deliberate. Each block is patched IN
 * PLACE to machine addresses, the trap is made, and the original offsets are put straight back — so
 * the VDI writes its answers into the game's own `intout`/`ptsout` arrays with no copy back, and
 * the image the cores read afterwards holds exactly what it held before. A copy of each block would
 * have to know which fields the VDI writes; this has to know nothing.
 *
 * NOTHING RE-ENTERS IT. The one interrupt this build installs is Timer C, whose handler is the
 * verified sound ISR and touches no GEM state at all, so a patch is never live across an interrupt
 * that could read it.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"

#include "bubble_mfdb.h"    /* ../include/blit.h, with its MFDB field offsets pinned against the
                             * kit's own — `frontend.h` below pulls blit.h in either way */
#include "bubble_target.h"
#include "frontend.h"       /* A_vdi_contrl and the parameter blocks' shapes */
#include "tos.h"

volatile uint32_t bg_vdi_calls;
volatile uint32_t bg_aes_calls;
volatile uint32_t bg_vdi_raster_copies;

/* ================================================================================================
 * The two parameter blocks, as counts of longwords
 * ============================================================================================= */

/* `vdi_pblock` @ 0x1e8ca is five array pointers — contrl, intin, ptsin, intout, ptsout — and the
 * AES block six: control, global, int_in, int_out, addr_in, addr_out. Both are spelt as counts
 * rather than as end addresses, because what the door does with them is a loop. */
#define VDI_POINTER_LONGS 5u
#define AES_POINTER_LONGS 6u
#define POINTER_BYTES     4u

/* The `contrl` word indices this door reads, the opcode whose operands are pointers, and the MFDB's
 * own length are ALL THE KIT'S — `VDI_CONTRL_OPCODE`, `VDI_CONTRL_SRC_MFDB`, `VDI_CONTRL_DST_MFDB`,
 * `VDI_VRO_CPYFM`, `MFDB_ADDR`, `MFDB_BYTES`, `MFDB_SCREEN_ADDR` in tools/recreate_kit/include/os.h,
 * which the shadow beside this file pulls in. They are the same numbers the game's own binding
 * uses, and a second spelling of them here is exactly the drift CLAUDE.md §5 is about; a first draft
 * had one, and the compiler said so. */
#define WORD_SLOT_BYTES 2u

/* An image offset becomes a machine address — except 0, which is the VDI's "the screen" and must
 * stay 0 so that TOS substitutes the logical base `Setscreen` was given (../notes/frontend.md §1:
 * for this program that base is `screen_back`). Translating it would point the raster copy at the
 * bottom of the image instead. */
static uint32_t machine_address(uint32_t offset) {
    return offset == MFDB_SCREEN_ADDR ? MFDB_SCREEN_ADDR
                                      : (uint32_t)(uintptr_t)bg_image_base + offset;
}

/* The two MFDBs a raster copy names, in the shim's own memory with their raster pointers
 * translated. They are static because their MACHINE ADDRESSES are what goes into `contrl`, so they
 * have to outlive this function by the length of the trap. */
static uint8_t g_src_mfdb[MFDB_BYTES];
static uint8_t g_dst_mfdb[MFDB_BYTES];

static void stage_mfdb(uint8_t *out, const uint8_t *mem, uint32_t mfdb_offset) {
    for (unsigned byte = 0; byte < MFDB_BYTES; byte++)
        out[byte] = mem[mfdb_offset + byte];
    wr32(out + MFDB_ADDR, machine_address(be32(mem + mfdb_offset + MFDB_ADDR)));
}

static uint32_t contrl_word_address(uint32_t contrl, unsigned index) {
    return contrl + index * WORD_SLOT_BYTES;
}

/* contrl[7..8] and contrl[9..10] are each one LONGWORD written across two word slots, which is how
 * `vdi_set_src_mfdb` @ 0x16890 stores them. */
static uint32_t contrl_long(const uint8_t *mem, uint32_t contrl, unsigned index) {
    return be32(mem + contrl_word_address(contrl, index));
}

static void set_contrl_long(uint8_t *mem, uint32_t contrl, unsigned index, uint32_t value) {
    wr32(mem + contrl_word_address(contrl, index), value);
}

/* ================================================================================================
 * The door
 * ============================================================================================= */

/* Patch a block of `longs` image offsets to machine addresses, remembering what was there. */
static void translate_block(uint8_t *mem, uint32_t block, unsigned longs, uint32_t *saved) {
    for (unsigned slot = 0; slot < longs; slot++) {
        uint32_t at = block + slot * POINTER_BYTES;
        saved[slot] = be32(mem + at);
        wr32(mem + at, machine_address(saved[slot]));
    }
}

static void restore_block(uint8_t *mem, uint32_t block, unsigned longs, const uint32_t *saved) {
    for (unsigned slot = 0; slot < longs; slot++)
        wr32(mem + block + slot * POINTER_BYTES, saved[slot]);
}

/* A raster copy's two MFDB pointers, staged and patched. Answers whether it did anything, so the
 * restore below runs only for the call that needs it. */
static int stage_raster_copy(uint8_t *mem, uint32_t contrl, uint32_t *saved_mfdbs) {
    if (be16(mem + contrl_word_address(contrl, VDI_CONTRL_OPCODE)) != VDI_VRO_CPYFM)
        return 0;

    saved_mfdbs[0] = contrl_long(mem, contrl, VDI_CONTRL_SRC_MFDB);
    saved_mfdbs[1] = contrl_long(mem, contrl, VDI_CONTRL_DST_MFDB);
    stage_mfdb(g_src_mfdb, mem, saved_mfdbs[0]);
    stage_mfdb(g_dst_mfdb, mem, saved_mfdbs[1]);
    set_contrl_long(mem, contrl, VDI_CONTRL_SRC_MFDB, (uint32_t)(uintptr_t)g_src_mfdb);
    set_contrl_long(mem, contrl, VDI_CONTRL_DST_MFDB, (uint32_t)(uintptr_t)g_dst_mfdb);
    bg_vdi_raster_copies++;
    return 1;
}

int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock) {
    uint32_t saved_pointers[AES_POINTER_LONGS];
    uint32_t saved_mfdbs[2];
    const unsigned longs = selector == GEM_VDI ? VDI_POINTER_LONGS : AES_POINTER_LONGS;
    int raster = 0;

    if (selector == GEM_VDI) {
        raster = stage_raster_copy(mem, A_vdi_contrl, saved_mfdbs);
        bg_vdi_calls++;
    } else {
        bg_aes_calls++;
    }

    translate_block(mem, pblock, longs, saved_pointers);
    (void)bg_gem_trap((long)selector, mem + pblock);
    restore_block(mem, pblock, longs, saved_pointers);

    if (raster) {
        set_contrl_long(mem, A_vdi_contrl, VDI_CONTRL_SRC_MFDB, saved_mfdbs[0]);
        set_contrl_long(mem, A_vdi_contrl, VDI_CONTRL_DST_MFDB, saved_mfdbs[1]);
    }
    /* The kit's door answers "modeled" — 1 when it serviced the call. TOS services every opcode
     * this program makes, and a `trap #2` has no way to say otherwise, so the answer is always 1
     * and the cores' refusal arms are unreachable here. That is a residual and not a claim: the
     * README's "Unpinned" section carries it. */
    return 1;
}

/* ================================================================================================
 * The three libc functions, hand-written
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC noticing that each of these is a memcpy or
 * a memset and replacing its body with a call to itself; `build.sh` passes it and there is no other
 * defence, so a build that lost the flag would recurse until the stack ran out.
 * ============================================================================================= */

void *memcpy(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    while (n--)
        *to++ = *from++;
    return dst;
}

void *memmove(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    if (to > from) {                       /* descending, so an overlap is read before it is written */
        to += n;
        from += n;
        while (n--)
            *--to = *--from;
        return dst;
    }
    while (n--)
        *to++ = *from++;
    return dst;
}

void *memset(void *dst, int c, unsigned long n) {
    uint8_t *to = dst;

    while (n--)
        *to++ = (uint8_t)c;
    return dst;
}
