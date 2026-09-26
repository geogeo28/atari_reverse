/* GEMDOS memory management — Malloc ($48, $fc8aae), Mfree ($49, $fc8afc), Mshrink ($4a, $fc895a)
 * and the four routines under them: the descriptor allocator $fc886a, the free-list insert with
 * coalescing $fc89dc, and the record pool $fc7f1a/$fc7f9c over the bump arena $fc7ed0.
 *
 * `include/gemdos/memory.h` has the three structures and where they live. What is here is the
 * BEHAVIOUR, and the five things about it a reconstruction gets wrong by writing the obvious C:
 *
 *   1. THE SEARCH IS NEXT-FIT, NOT FIRST-FIT. `gemdos_md_alloc` starts at `mp_rover` and takes the
 *      first free block that FITS, wrapping round to the head of the list and stopping when it
 *      comes back to the rover. So the block a given request gets depends on where the last one
 *      came from, and a reconstruction that searched from `mp_mfl` passes every case whose rover
 *      happens to be the head — which is the snapshot's own state, so it would pass by default.
 *   2. THE MPB DOUBLES AS A DESCRIPTOR. `mp_mfl` is at offset 0 of the MPB and `m_link` is at
 *      offset 0 of a descriptor, so the ROM walks off the MPB's own address as if it were the
 *      descriptor before the first one, and the "unlink the head" case needs no special arm. It
 *      happens in three places here — the allocator's wrap, the insert's head store and the
 *      allocated-list search — and each says so where it does it.
 *   3. THE SPLIT KEEPS THE LOW HALF AND GIVES AWAY THE REMAINDER'S descriptor, not the other way
 *      round: the block that was on the free list stays where it is, has its length cut to the
 *      request and moves to the ALLOCATED list, and it is the REMAINDER that gets the new
 *      descriptor and takes the old one's place in the free list. A reconstruction that allocated
 *      the new descriptor leaves `m_start` right and every list pointer wrong.
 *   4. COALESCING IS FORWARD FIRST, THEN BACKWARD, and the two are ONE function with its arguments
 *      the other way round (`md_merge_if_adjacent`) — which the ROM's two nearly identical blocks
 *      do not make obvious. The order is what lets three blocks merge in a single call, and the
 *      two descriptors that go away are returned to the pool in it.
 *   5. THE ROUNDING IS TO AN EVEN SIZE and it is spelt TWICE, in `Malloc` and in `Mshrink`, at
 *      different points of each: `Malloc` rounds before it searches and exempts `-1`, `Mshrink`
 *      rounds AFTER the grow check — so `Mshrink(block, len)` with `len` one over an even length
 *      is refused, and `len` one UNDER it is accepted and rounds back up to the whole block,
 *      leaving a zero-length descriptor on the free list.
 *
 * AND EVERY ONE OF THEM SAVES A DATA REGISTER WHOSE SAVED COPY IT THEN OVERWRITES. Alcyon reserves
 * the four-byte outgoing-argument slot these routines push their callee's first argument into by
 * saving ONE EXTRA register, and the epilogue pops that slot with `tst.l (sp)+` instead of
 * restoring it: `$fc886a` saves `d5-d7/a3-a5` and restores `d6-d7/a3-a5`, so the slot the arguments
 * go into is D5's; `Malloc`'s is D6's; `Mfree`, `Mshrink`, the insert and the arena use D7's. What
 * is overwritten is the STACK SLOT and not the register — no body here writes the register itself,
 * which is why a caller's copy survives anyway — so the idiom costs a push and a discarded pop
 * rather than a register. It is the same idiom, a caller writing its first argument to `(sp)`
 * rather than pushing it, that COMPONENTS.md records as defeating Ghidra on 73 functions.
 *
 * NOTHING HERE VALIDATES A POINTER. `Mfree` and `Mshrink` find a block by walking a list and
 * comparing `m_start`, so their only refusal is "no block starts there" — an address one byte
 * inside a live block is EIMBA, and a pool whose lists have been corrupted is walked into whatever
 * it points at. That is the ROM's contract and the cases hold it to it.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "gemdos/gemdos.h"
#include "gemdos/memory.h"

/* One field of a descriptor, or of the MPB read as one. Spelt as helpers because every routine
 * below is pointer chasing and `be32(image + addr_add(md, MD_LINK))` six times a function reads as
 * arithmetic rather than as a structure. `addr_add` is the 68000's own address ALU: these addresses
 * come off the image and a corrupt pool can send one past the end of RAM, where a host pointer
 * would walk into host memory instead of wrapping (machine.h). */
static uint32_t md_field(const uint8_t *image, uint32_t md, uint32_t field)
{
    return be32(image + addr_add(md, field));
}

static void set_md_field(uint8_t *image, uint32_t md, uint32_t field, uint32_t value)
{
    wr32(image + addr_add(md, field), value);
}

/* ---- the record pool -------------------------------------------------------------------------- */

/* $fc7ed0 — hand out `words` words of the GEMDOS arena, or 0 when that many are not left.
 *
 * THE COMPARE AND THE CURSOR ARE BOTH WORD-SIZED AND SIGNED. `cmp.w $8780,d0 / ble` is a signed
 * word compare, and the byte offset is `asl.w #1` followed by `ext.l` — so a request or a cursor
 * that reached bit 15 would be read as negative. Neither is reachable from the 8000 words the init
 * writes (16,000 bytes, the largest offset this can form is $3e80), but the arithmetic is the
 * ROM's rather than the one a reconstruction would write, and `test_gemdos_memory_pool.py` drives
 * both widths at their boundaries.
 */
uint32_t gemdos_pool_arena_alloc(uint8_t *image, uint16_t words)
{
    uint16_t words_left = be16(image + GEMDOS_POOL_FREE_WORDS);
    uint16_t words_used;
    uint32_t record;

    if ((int16_t)words > (int16_t)words_left) {
        return 0;
    }
    wr16(image + GEMDOS_POOL_FREE_WORDS, (uint16_t)(words_left - words));
    /* ...and only now the cursor, which is the order the ROM stores in: two different words, so it
     * matters to nothing but a reader trying to follow the disassembly. */
    words_used = be16(image + GEMDOS_POOL_USED_WORDS);
    record = addr_add(GEMDOS_POOL_ARENA, sign_ext16((uint16_t)(words_used << 1)));
    wr16(image + GEMDOS_POOL_USED_WORDS, (uint16_t)(words_used + words));
    return record;
}

/* The free-chain head for one size class: `GEMDOS_P_ROOT[class]`, with the class SIGN-EXTENDED out
 * of a word before it is scaled — `movea.w d0,a0 / adda.l a0,a0 / adda.l a0,a0`. Both routines
 * below index it this way, which is why it is a function rather than two copies of the expression.
 */
static uint32_t pool_chain_of(uint16_t size_class)
{
    return addr_add(GEMDOS_P_ROOT, sign_ext16(size_class) * POOL_CHAIN_ENTRY_BYTES);
}

/* $fc7f1a — a ZEROED record of `size_class`, off that class's free chain if one is waiting and out
 * of the arena otherwise, or 0 when the arena is spent.
 *
 * THE CLASS IS STORED BELOW THE RECORD, in the two bytes the arena request pays for over the
 * record's own size (`words + 1`), and it is what lets `gemdos_pool_free` put a record back on the
 * right chain knowing nothing but its address. A record off the CHAIN already has that header from
 * when it was first cut, which is why only the arena arm writes one.
 *
 * AND THE RECORD IS CLEARED AFTERWARDS EITHER WAY — including over the longword the chain link was
 * just read out of, so a caller never sees the link. `gemdos_md_alloc` relies on that: it stores
 * `m_link`, `m_start` and `m_length` into the descriptor it gets back but never `m_own`, and the
 * zero that field carries is this clear.
 */
uint32_t gemdos_pool_get(uint8_t *image, uint16_t size_class)
{
    uint16_t record_words = (uint16_t)(size_class << POOL_CLASS_WORDS_SHIFT);
    uint32_t chain = pool_chain_of(size_class);
    uint32_t record;
    uint16_t word;

    if (be32(image + chain) != 0) {
        record = be32(image + chain);
        wr32(image + chain, be32(image + record));   /* pop: the link is the record's first long */
    } else {
        record = gemdos_pool_arena_alloc(image, (uint16_t)(record_words + 1));
        if (record != 0) {
            wr16(image + record, size_class);
            record = addr_add(record, POOL_CLASS_HEADER_BYTES);
        }
    }
    if (record != 0) {
        for (word = 0; (int16_t)word < (int16_t)record_words; word++) {
            wr16(image + addr_add(record, (uint32_t)word * 2), 0);
        }
    }
    return record;
}

/* $fc7f9c — push `record` back onto its own class's free chain, the class read out of its header. */
void gemdos_pool_free(uint8_t *image, uint32_t record)
{
    uint16_t size_class = be16(image + addr_add(record, (uint32_t)-POOL_CLASS_HEADER_BYTES));
    uint32_t chain = pool_chain_of(size_class);

    wr32(image + record, be32(image + chain));
    wr32(image + chain, record);
}

/* ---- the free list ----------------------------------------------------------------------------- */

/* ---- the three arms `gemdos_md_alloc` is made of, in the order it runs them ---------------------
 * Separate functions so that the WALK below reads as a walk; each is straight-line and each is
 * entered from exactly one place, which is what lets them be read as that routine's body. */

/* The request is the whole block: unlink it, leaving its length and start alone. */
static void md_unlink_exact_fit(uint8_t *image, uint32_t previous, uint32_t block)
{
    set_md_field(image, previous, MD_LINK, md_field(image, block, MD_LINK));
}

/* ...otherwise the block is cut at `amount` and the REMAINDER takes its place on the free list.
 * Answers 0 when the pool has no descriptor to put the remainder in, which is the failure a
 * machine with plenty of free RAM still meets. The five stores are in the ROM's own order, and so
 * is the RE-READ of the block's `m_length` AFTER the pool call ($fc88d6): both only matter to a
 * pool corrupt enough for the new descriptor to alias the block, which is exactly the state the
 * differential is there to reproduce faithfully rather than to tidy. */
static int md_split_off_remainder(uint8_t *image, uint32_t previous, uint32_t block,
                                  uint32_t amount)
{
    uint32_t remainder = gemdos_pool_get(image, MD_SIZE_CLASS);

    if (remainder == 0) {
        return 0;
    }
    set_md_field(image, remainder, MD_LENGTH, md_field(image, block, MD_LENGTH) - amount);
    set_md_field(image, remainder, MD_START, addr_add(md_field(image, block, MD_START), amount));
    set_md_field(image, remainder, MD_LINK, md_field(image, block, MD_LINK));
    set_md_field(image, block, MD_LENGTH, amount);
    set_md_field(image, previous, MD_LINK, remainder);
    return 1;
}

/* ...and either way the block goes to the head of the allocated list, owned by the process running
 * now, and the rover is left at the predecessor (see the routine's own note on the MPB arm). */
static void md_take_ownership(uint8_t *image, uint32_t mpb, uint32_t previous, uint32_t block)
{
    set_md_field(image, block, MD_LINK, md_field(image, mpb, MPB_ALLOCATED_LIST));
    set_md_field(image, mpb, MPB_ALLOCATED_LIST, block);
    set_md_field(image, block, MD_OWNER, gemdos_basepage(image));
    set_md_field(image, mpb, MPB_ROVER,
                 previous == mpb ? md_field(image, previous, MD_LINK) : previous);
}

/* $fc886a — take `amount` bytes out of `mpb`'s free list, or report the largest free block.
 *
 * Answers the DESCRIPTOR of the allocated block; for `MALLOC_LARGEST_FREE_BLOCK` it allocates
 * nothing and answers the largest `m_length` it saw; and 0 when nothing fits, when the rover is
 * null, or when the pool has no descriptor left for a split. A caller cannot tell those three
 * apart, which is why `Malloc` reports every one of them as 0.
 *
 * THE WALK IS CIRCULAR AND THE ROVER IS BOTH ITS START AND ITS STOP. `previous` starts at the
 * rover and the candidate is the block AFTER it; the end of the list wraps to the MPB, whose
 * `mp_mfl` is read as that pseudo-descriptor's `m_link`; and the sweep ends when `previous` comes
 * back to the rover — re-read from the MPB each pass, exactly as the ROM re-reads it, though
 * nothing in the search writes it.
 *
 * WHERE THE ROVER IS LEFT is the subtle half: at the block's PREDECESSOR, so the next search
 * starts at whatever took the block's place (the remainder of a split, or the block after it) —
 * unless the predecessor is the MPB itself, in which case the rover is set to `mp_mfl` instead, so
 * that the MPB's address never ends up stored as a descriptor pointer.
 */
uint32_t gemdos_md_alloc(uint8_t *image, uint32_t amount, uint32_t mpb)
{
    uint32_t previous = md_field(image, mpb, MPB_ROVER);
    uint32_t largest = 0;
    uint32_t block;
    int report_largest;

    if (previous == 0) {
        return 0;
    }
    report_largest = (amount == MALLOC_LARGEST_FREE_BLOCK);
    block = md_field(image, previous, MD_LINK);
    for (;;) {
        uint32_t length;

        if (block == 0) {                      /* the end of the list wraps to the MPB's own head */
            previous = mpb;
            block = md_field(image, previous, MD_LINK);
        }
        length = md_field(image, block, MD_LENGTH);
        if (!report_largest && (int32_t)length >= (int32_t)amount) {
            if (length == amount) {
                md_unlink_exact_fit(image, previous, block);
            } else if (!md_split_off_remainder(image, previous, block, amount)) {
                return 0;                       /* no descriptor left for the remainder */
            }
            md_take_ownership(image, mpb, previous, block);
            return block;
        }
        if ((int32_t)largest < (int32_t)length) {
            largest = length;
        }
        previous = block;
        block = md_field(image, previous, MD_LINK);
        if (previous == md_field(image, mpb, MPB_ROVER)) {
            break;
        }
    }
    return report_largest ? largest : 0;
}

/* One of the insert's two merges: `keeper` swallows `eaten` if the two blocks touch, and the
 * descriptor that is left over goes back to the pool.
 *
 * THE TWO ARE THE SAME FUNCTION with the arguments the other way round, which is not obvious from
 * the ROM's two nearly identical blocks and is worth having said once: the forward merge is
 * `(md, successor)` and the backward one `(previous, md)`, so what differs between them is only
 * WHICH of the two descriptors survives. The rover fix-up falls out of that — it moves off the
 * descriptor that is about to be recycled and onto the one that is not — and so does the order the
 * insert makes the calls in, which is what lets three blocks become one: the forward merge has
 * already put the successor's length into `md` by the time the backward merge puts `md`'s into the
 * predecessor.
 *
 * BOTH ARGUMENTS MUST NAME A DESCRIPTOR. "No neighbour that way" — the end of the list above,
 * nothing below — is tested by the caller, because the ROM tests it there: folding it in here costs
 * the no-merge path two compares the original does not make, which is 10% of the insert's cycles on
 * a call that merges nothing (measured, `make bench`). */
static inline void md_merge_if_adjacent(uint8_t *image, uint32_t mpb, uint32_t keeper,
                                        uint32_t eaten)
{
    if (addr_add(md_field(image, keeper, MD_START), md_field(image, keeper, MD_LENGTH)) !=
            md_field(image, eaten, MD_START)) {
        return;
    }
    set_md_field(image, keeper, MD_LENGTH,
                 md_field(image, keeper, MD_LENGTH) + md_field(image, eaten, MD_LENGTH));
    set_md_field(image, keeper, MD_LINK, md_field(image, eaten, MD_LINK));
    if (md_field(image, mpb, MPB_ROVER) == eaten) {
        set_md_field(image, mpb, MPB_ROVER, keeper);
    }
    gemdos_pool_free(image, eaten);
}

/* $fc89dc — put `md` back on `mpb`'s free list, in `m_start` order, and merge it with whichever of
 * its two neighbours it touches.
 *
 * FORWARD FIRST, THEN BACKWARD, and both can fire on one call — three blocks become one and two
 * descriptors go back to the pool, the successor's before `md`'s own. Each merge fixes the rover
 * only in the one way that merge can leave it dangling: the forward one moves a rover that was on
 * the successor onto `md`, and the backward one moves a rover that was on `md` onto the
 * predecessor. A third fix-up, for a rover that is null, is made BEFORE either — a free list that
 * had emptied (`Malloc` of the last block exactly) leaves the rover null, and this is what gets it
 * pointing at a descriptor again.
 */
void gemdos_md_free_insert(uint8_t *image, uint32_t md, uint32_t mpb)
{
    uint32_t previous = 0;
    uint32_t successor = md_field(image, mpb, MPB_FREE_LIST);

    while (successor != 0) {
        if ((int32_t)md_field(image, md, MD_START) <= (int32_t)md_field(image, successor, MD_START)) {
            break;
        }
        previous = successor;
        successor = md_field(image, previous, MD_LINK);
    }
    set_md_field(image, md, MD_LINK, successor);
    if (previous != 0) {
        set_md_field(image, previous, MD_LINK, md);
    } else {
        /* ...and `mp_mfl` is the MPB read as the descriptor before the first one (see the file's
         * note 2), which is the same store one field further up. */
        set_md_field(image, mpb, MPB_FREE_LIST, md);
    }
    if (md_field(image, mpb, MPB_ROVER) == 0) {
        set_md_field(image, mpb, MPB_ROVER, md);
    }
    if (successor != 0) {
        md_merge_if_adjacent(image, mpb, md, successor);    /* forward: the block above `md` */
    }
    if (previous != 0) {
        md_merge_if_adjacent(image, mpb, previous, md);     /* ...and then the one below it */
    }
}

/* The descriptor BEFORE the allocated block that starts at `address`, or 0 when no block does.
 *
 * `Mfree` and `Mshrink` both find their block this way and neither checks anything else about the
 * address, so an address one byte inside a live block is as unknown as an address in ROM. The
 * PREDECESSOR is what comes back rather than the block itself, because `Mfree` needs it to unlink
 * — and 0 is an unambiguous "not found" here, since the walk starts at the MPB's own `mp_mal`
 * field read as a descriptor's `m_link` (the file's note 2) and that address is never 0. */
static uint32_t md_allocated_before(uint8_t *image, uint32_t address)
{
    uint32_t previous = addr_add(GEMDOS_MPB, MPB_ALLOCATED_LIST);
    uint32_t block = md_field(image, previous, MD_LINK);

    while (block != 0) {
        if (md_field(image, block, MD_START) == address) {
            return previous;
        }
        previous = block;
        block = md_field(image, previous, MD_LINK);
    }
    return 0;
}

/* ---- the three trap routines -------------------------------------------------------------------- */

/* GEMDOS $48 Malloc ($fc8aae) — `amount` bytes, or the largest free block for -1.
 *
 * THE ROUNDING IS THE ROUTINE'S WHOLE BODY besides the call. An odd request is rounded UP to an
 * even one before the search, so the blocks GEMDOS hands out — and therefore every length on
 * either list — stay even; and -1 is exempted by a test made on the whole longword FIRST, without
 * which the "report the largest" request would become a request for 0 bytes and allocate the head
 * of the free list.
 */
uint32_t gemdos_malloc(uint8_t *image, uint32_t amount)
{
    uint32_t block;

    if (amount != MALLOC_LARGEST_FREE_BLOCK && (amount & 1) != 0) {
        amount = addr_add(amount, 1);
    }
    block = gemdos_md_alloc(image, amount, GEMDOS_MPB);
    if (block == 0) {
        return 0;
    }
    /* ...and for -1 the answer is not a descriptor at all — it is the LENGTH `gemdos_md_alloc`
     * measured, handed straight back. */
    return amount == MALLOC_LARGEST_FREE_BLOCK ? block : md_field(image, block, MD_START);
}

/* GEMDOS $49 Mfree ($fc8afc) — give back the block that STARTS at `address`.
 *
 * `md_allocated_before` is what makes the head need no arm of its own, and nothing checks the
 * OWNER: any process may free any block, and the only refusal is that no block starts there.
 */
uint32_t gemdos_mfree(uint8_t *image, uint32_t address)
{
    uint32_t previous = md_allocated_before(image, address);
    uint32_t block;

    if (previous == 0) {
        return GEMDOS_EIMBA;
    }
    block = md_field(image, previous, MD_LINK);
    set_md_field(image, previous, MD_LINK, md_field(image, block, MD_LINK));
    gemdos_md_free_insert(image, block, GEMDOS_MPB);
    return 0;
}

/* GEMDOS $4a Mshrink ($fc895a) — cut the block at `block` down to `new_length` and free the rest.
 *
 * The caller pushes a reserved ZERO WORD below the block address and the ROM never reads it, so it
 * is not a parameter here; a case pokes it anyway, because it is what moves the two real arguments
 * to the offsets the routine reads them at.
 *
 * TWO REFUSALS AND A ROUNDING, IN THAT ORDER. No block starting at `block` is EIMBA; a
 * `new_length` LONGER than the block is EGSBF (-67, the "growth failure" a caller of `Mshrink` to
 * grow a TPA gets, and a SIGNED compare); and only then is an odd length rounded up. The order is
 * observable: a length one over the block's is refused, while one UNDER it is accepted, rounds
 * back up to the block's own length and leaves a ZERO-LENGTH descriptor on the free list.
 *
 * AND THE DESCRIPTOR IS NOT CHECKED. The ROM stores through whatever `gemdos_pool_get` answered,
 * so a spent pool makes this routine write `m_start` and `m_length` to addresses 4 and 8 — the
 * 68000's reset vector — and then insert a descriptor at address 0 into the free list. That is a
 * defect in TOS 1.02 rather than in this transcription, and
 * `test_gemdos_memory_mshrink.py::test_a_spent_descriptor_pool_makes_mshrink_write_through_null`
 * is the case that holds it in place: faithfulness here means reproducing it.
 */
uint32_t gemdos_mshrink(uint8_t *image, uint32_t block, uint32_t new_length)
{
    uint32_t previous = md_allocated_before(image, block);
    uint32_t md, remainder;

    if (previous == 0) {
        return GEMDOS_EIMBA;
    }
    md = md_field(image, previous, MD_LINK);
    if ((int32_t)md_field(image, md, MD_LENGTH) < (int32_t)new_length) {
        return GEMDOS_EGSBF;
    }
    if ((new_length & 1) != 0) {
        new_length = addr_add(new_length, 1);
    }
    remainder = gemdos_pool_get(image, MD_SIZE_CLASS);
    set_md_field(image, remainder, MD_START, addr_add(md_field(image, md, MD_START), new_length));
    set_md_field(image, remainder, MD_LENGTH, md_field(image, md, MD_LENGTH) - new_length);
    set_md_field(image, md, MD_LENGTH, new_length);
    gemdos_md_free_insert(image, remainder, GEMDOS_MPB);
    return 0;
}
