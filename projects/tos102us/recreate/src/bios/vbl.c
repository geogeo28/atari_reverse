/* The VERTICAL BLANK handler — vector $70, $fc06de. Fifty times a second, and the routine the boot
 * snapshot itself is captured inside (../README.md, "The snapshot").
 *
 *      addq.l  #1,_frclock         ; blanks that HAPPENED — counted before anything can refuse
 *      subq.w  #1,vblsem
 *      bmi.w   .release            ; ...the semaphore was already taken: do nothing at all
 *      movem.l d0-a6,-(sp)
 *      addq.l  #1,_vbclock         ; ...and blanks SERVICED
 *      suba.l  a5,a5
 *      <follow the monitor>        ; $ff8260 vs the MFP's monitor bit; on a change, swv_vec
 *      bsr     $fc4666             ; blink the alpha cursor
 *      suba.l  a5,a5
 *      <load the palette>          ; colorptr -> $ff8240, sixteen words, then clear colorptr
 *      <program the screen base>   ; screenpt -> _v_bas_ad -> $ff8203/$ff8201
 *      bsr     $fc1bc4             ; the floppy's own VBL service
 *      <walk _vblqueue>            ; nvbls slots, each a routine or 0
 *      suba.l  a5,a5
 *      tst.w   _dumpflg
 *      bne.s   .restore
 *      bsr     $fc0d50             ; Scrdmp: jsr (scr_dump), then set _dumpflg
 * .restore:
 *      movem.l (sp)+,d0-a6
 * .release:
 *      addq.w  #1,vblsem
 *      rte
 *
 * THE TWO CLOCKS ARE NOT THE SAME CLOCK, and the order says which is which: `_frclock` is bumped
 * BEFORE the semaphore is tested, so it counts blanks that happened; `_vbclock` after, so it counts
 * blanks this handler actually serviced. A machine that spent time inside a routine which had taken
 * `vblsem` has the two apart, which is exactly what `Vsync` ($fc07d0) is spinning on.
 *
 * THE SEMAPHORE IS RELEASED ON BOTH PATHS, and it is RE-READ to do it. `subq.w #1` then `addq.w #1`
 * over a word: anything the body left in `vblsem` is what gets the increment, not the value the
 * entry computed.
 *
 * WHAT IT CALLS IS RAM, not ROM. `swv_vec`, every slot of `_vblqueue` and `scr_dump` are longwords
 * the boot fills and anything may replace, so they are INPUTS of the handler: `include/staged_call.h`
 * is how the reconstruction transfers control to one and `test/isr.py` is how a case stages it.
 *
 * WHAT IS NOT RECONSTRUCTED HERE, and each halts rather than guessing (`recreate.h`):
 *
 *   * THE FLOPPY VBL SERVICE ($fc1bc4) past its `flock` gate, and the reason is now ONE thing rather
 *     than two. It makes TWO word reads of the FDC's data/status register at $ff8604 — at $fc1c0a
 *     for the media-change poll and again through $fc1ea4 for the motor-off check — which a
 *     declared SEQUENCE describes exactly (TRAP_MODEL.md, Phase 16: `io_seed={0xff8604: [...],
 *     0xff8605: [...]}`, a word read taking one entry from each). It is NOT a poll LOOP, which is
 *     what this comment used to say.
 *
 *     What it still needs is the YM2149's DIRECT path. Between those two reads it calls $fc1e60,
 *     which selects PSG register 14, READS PORT A BACK and merges the drive-select bits into it —
 *     Phase 6's read-modify-write, which this project has never used (its only PSG door so far is
 *     the XBIOS `Giaccess` trap, and a run that reached both would be refused by the mixed-path
 *     guard). That is a floppy wave's first piece of work, not this one's.
 *
 *     What IS reconstructed is the `st` it makes before it looks at anything and the early return
 *     `flock` buys, which is the arm a machine with a disk operation in flight takes.
 *   * nothing else: the monitor follower, the cursor blink INCLUDING the cell inversion at $fc4a1e,
 *     the palette load, the screen base, the queue walk and the dump hook are all here.
 */
#include <stdint.h>

#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif

#include "machine.h"
#include "recreate.h"
#include "m68k_idioms.h"
#include "hw.h"
#include "addrs.h"
#include "staged_call.h"

/* ---- the monitor follower ----------------------------------------------------------------------
 * `move.w #2000,d0 / dbf d0,*` — 2001 passes of nothing, which is the shifter being given time to
 * settle before the resolution changes under it. It is PURE DELAY: it touches no memory, no
 * register the caller can see and no chip, so the ONLY surface it has is its cost, and the only
 * instrument that can see one is the Tier 3 row `test_bios_vbl.py` registers for this arm (`ipl.h`
 * makes the same argument for its interrupt mask).
 *
 * WHICH IS WHY IT IS THE `dbf` AND NOT A C LOOP. An empty C loop is deleted outright; a C loop with
 * a barrier in it survives but costs three instructions a pass where the original costs one —
 * measured, 6044 instructions and 44,618 cycles against the original's 2048 and 20,910, which is
 * the whole of a 2.14x row. The split is on `__m68k__` rather than on the differential's own macro,
 * exactly as `machine.h`'s register barriers are: it is a question about the TARGET's instruction
 * set and not about which harness is looking. Off target the loop is kept (the two builds stay the
 * same program) and its cost is nobody's measurement. */
#define SHIFTER_SETTLE_DBF_COUNT 2000

static void wait_for_the_shifter(void)
{
    unsigned passes = SHIFTER_SETTLE_DBF_COUNT;

#ifdef __m68k__
    __asm__ volatile ("1: dbf %0,1b" : "+d"(passes));
#else
    /* `dbf` exits at -1, so the register holds one FEWER than the passes it makes: the count has to
     * be bumped here for the two builds to be the same program. */
    passes++;
    while (passes-- != 0)
        COUNT_BARRIER(passes);
#endif
}

/* Is a monochrome monitor plugged in? The MFP's GPIP bit 7 is LOW when one is, which is why every
 * test of it in the ROM reads as the opposite of what it says. */
static int monochrome_monitor_attached(void)
{
    return (hw_read8(MFP_GPIP) & (1u << MFP_GPIP_MONOCHROME_BIT)) == 0;
}

/* The shifter against the monitor socket, once a frame. Nothing happens while the two agree; when
 * they do not, the new resolution is written to the register AND shadowed in `sshiftmd`, and
 * `swv_vec` is called so the VDI can rebuild itself around the new screen. */
static void follow_the_monitor(uint8_t *image)
{
    uint8_t resolution = io_read8(SHIFTER_RESOLUTION) & GETREZ_MODE_MASK;
    uint8_t wanted;

    if (resolution < SHIFTER_MODE_HIGH) {
        if (!monochrome_monitor_attached())
            return;                                 /* still a colour monitor: nothing to do */
        wait_for_the_shifter();
        wanted = SHIFTER_MODE_HIGH;
    } else {
        if (monochrome_monitor_attached())
            return;                                 /* still mono */
        /* `cmp.b #2,d0 / blt` — SIGNED, so a `defshiftmd` with bit 7 set is kept as it stands
         * rather than replaced: only 2..127 is out of range as far as this test is concerned. */
        wanted = image[SYSVAR_DEFSHIFTMD];
        if ((int8_t)wanted >= SHIFTER_MODE_HIGH)
            wanted = 0;
    }
    image[SYSVAR_SSHIFTMD] = wanted;
    hw_write8(SHIFTER_RESOLUTION, wanted);
    call_vector(image, be32(image + SYSVAR_SWV_VEC));
}

/* ---- the alpha cursor's blink ($fc4666), and the cell inversion it ends in ($fc4a1e) ------------ */

/* `not.b` down one column of every bit plane — the cursor cell, inverted in place on the screen.
 * Two nested `dbf`s, so both counts are "the register plus one" and a zero count is a full 65,536
 * passes rather than none (`loop_passes`). That zero arm is EXERCISED by a case and its pass count
 * is not PINNED by one — `test_bios_vbl.py`'s `test_a_cell_height_of_zero_is_a_full_sixty_five
 * _thousand_passes` says why, and what it would take.
 *
 * The inner step is a SIGN-EXTENDED word add, the outer a full address add: `adda.w` against
 * `addq.w #2,a1`, which on an address register is 32 bits wide whatever its suffix says. The outer
 * step is two bytes because that is how far apart an ST's bit planes are: the four words of one
 * 16-pixel screen cell sit side by side (`SCREEN_PLANE_WORD_BYTES` is in `addrs.h`, because the
 * battery computes the same set of inverted bytes). */
static void invert_cursor_cell(uint8_t *image, uint32_t cursor)
{
    uint16_t line_bytes = be16(image + CON_LINE_BYTES);
    unsigned rows = loop_passes(be16(image + CON_CELL_HEIGHT), COUNT_MASK_WORD);
    unsigned planes = loop_passes(be16(image + CON_PLANES), COUNT_MASK_WORD);

    while (planes-- != 0) {
        uint32_t at = cursor;
        unsigned row = rows;

        while (row-- != 0) {
#ifdef RECREATE_HOST_DIFFERENTIAL
            /* HOST-ONLY, the way the kit prescribes: the cursor address, the cell height and the
             * line pitch are all RAM the console driver keeps, so a machine whose block held
             * nonsense would walk off the image here — where the original walks its own address
             * space. Nothing a case stages can reach it (../README.md, the staging band). */
            assert(at < ST_RAM_BYTES);
#endif
            image[at] = (uint8_t)~image[at];
            at = addr_add(at, sign_ext16(line_bytes));
        }
        cursor = addr_add(cursor, SCREEN_PLANE_WORD_BYTES);
    }
}

/* The blink itself. Three gates, and each of the writes below happens whether or not it CHANGES
 * anything — `subq.b`, `bchg` and `bset` are read-modify-writes, so the byte is stored back even
 * when the value is the one it already held.
 *
 * TWO OF THE THREE ARE HELD BY THE PLAIN BYTE DIFF and the third is the ORACLE'S CLAIM ALONE, which
 * is worth saying because it looks like the others. `subq.b` and `bchg` always CHANGE the byte they
 * store, so a reconstruction that skipped either leaves a different image and the differential says
 * so outright. `bset #1` on a byte whose bit 1 is ALREADY SET does not: it writes what is there, and
 * nothing in the image, in any ledger or in the cycle count separates "store it back" from "leave
 * it", so that one store is transcribed and read-verified rather than proved (measured: it is the
 * one mutation of this wave's 26 that survives).
 *
 * AND THE ATTRIBUTION PASS REACHES NONE OF IT, which is the other half of why the plain diff has to
 * carry them. Poisoning inverts every byte the oracle wrote, and one of them is `vblsem`: a case
 * whose semaphore was 1 re-enters the poisoned run at $fffe, the `bmi` takes the release path, and
 * the cursor is never looked at. Measured on this battery: 74 of its 77 poisoned passes take that
 * path; the three that do not are the semaphore-boundary cases ($7fff, $8000, $8001), whose
 * poisoned word happens to stay open. */
static void blink_cursor(uint8_t *image)
{
    uint8_t flags;

    if (be16(image + CON_CURSOR_DISABLE) != 0)
        return;                                     /* the cursor is suppressed outright */
    image[CON_BLINK_TIMER] = (uint8_t)(image[CON_BLINK_TIMER] - 1);
    if (image[CON_BLINK_TIMER] != 0)
        return;                                     /* ...not this frame */
    image[CON_BLINK_TIMER] = image[CON_BLINK_RATE];

    flags = image[CON_STATE_FLAGS];
    if (flags & (1u << CON_FLAG_BLINKS)) {
        image[CON_STATE_FLAGS] = (uint8_t)(flags ^ (1u << CON_FLAG_DRAWN));   /* bchg */
    } else {
        /* `bset #1,(a4) / beq` — a cursor that does NOT blink is simply made sure of: the bit is
         * stored set either way, and the cell is only inverted if it had been clear. */
        image[CON_STATE_FLAGS] = (uint8_t)(flags | (1u << CON_FLAG_DRAWN));
        if (flags & (1u << CON_FLAG_DRAWN))
            return;
    }
    invert_cursor_cell(image, be32(image + CON_CURSOR_ADDRESS));
}

/* ---- the two things the screen leaves queue for this handler ------------------------------------ */

/* Sixteen words from wherever `Setpalette` left them, straight into the shifter's colour row, and
 * then the pointer is cleared so the next frame does nothing. */
static void load_the_palette(uint8_t *image)
{
    uint32_t source = be32(image + SYSVAR_COLORPTR);
    unsigned entry;

    if (source == 0)
        return;
#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, as in `invert_cursor_cell` above: `colorptr` is whatever `Setpalette` was handed,
     * so a caller that pointed it outside RAM would walk off the image here where the original
     * walks its own address space. */
    assert(source <= ST_RAM_BYTES - SHIFTER_PALETTE_ENTRIES * PALETTE_ENTRY_BYTES);
#endif
    for (entry = 0; entry < SHIFTER_PALETTE_ENTRIES; entry++)
        hw_write16(SHIFTER_PALETTE + entry * PALETTE_ENTRY_BYTES,
                   be16(image + addr_add(source, entry * PALETTE_ENTRY_BYTES)));
    wr32(image + SYSVAR_COLORPTR, 0);
}

/* ...and the screen base `Setscreen` left, into `_v_bas_ad` and then into the shifter's two base
 * bytes, MID first. `screenpt` is deliberately NOT cleared — unlike `colorptr` one line up — so the
 * same base is re-programmed on every frame until something else stores there. That asymmetry is
 * the ROM's, and `test_bios_vbl.py` pins it rather than leaving it to read as an omission here. */
static void program_the_screen_base(uint8_t *image)
{
    uint32_t queued = be32(image + SYSVAR_SCREENPT);
    uint32_t base;

    if (queued == 0)
        return;
    wr32(image + SYSVAR_V_BAS_AD, queued);
    base = be32(image + SYSVAR_V_BAS_AD);           /* the ROM reads it back, and so do we */
    hw_write8(SHIFTER_BASE_MID, (uint8_t)(base >> SHIFTER_BASE_SHIFT));
    hw_write8(SHIFTER_BASE_HIGH, (uint8_t)(base >> (2 * SHIFTER_BASE_SHIFT)));
}

/* ---- the floppy's own VBL service ($fc1bc4), as far as this wave reconstructs it ----------------- */
static void floppy_vbl(uint8_t *image)
{
    image[FLOPPY_VBL_ENTERED] = 0xff;               /* `st` — unconditional, before anything else */
    if (be16(image + SYSVAR_FLOCK) != 0)
        return;                                     /* a disk operation owns the FDC: hands off */
    recreate_not_reconstructed(
        "the floppy VBL service ($fc1bc4) with `flock` clear — it drives the drive-select bits "
        "through the YM2149's port A ($fc1e60 reads register 14 back and merges them), which is the "
        "DIRECT PSG path this project has no case for yet; its two reads of $ff8604 a declared "
        "sequence already describes");
}

/* ---- the queue, and the dump hook ---------------------------------------------------------------- */

/* `nvbls` slots of `_vblqueue`, each a routine address or 0. The count and the cursor are saved
 * across every call (`movem.l d7/a0`), so a routine that rewrites either system variable does not
 * change the walk it is being run by — which is what our own locals reproduce. */
static void run_the_vbl_queue(uint8_t *image)
{
    unsigned slots = be16(image + SYSVAR_NVBLS);
    uint32_t cursor = be32(image + SYSVAR_VBLQUEUE);

    if (slots == 0)
        return;
    while (slots-- != 0) {
        uint32_t routine;

#ifdef RECREATE_HOST_DIFFERENTIAL
        /* HOST-ONLY, as above: `_vblqueue` and `nvbls` are both system variables a case may set,
         * and a walk off the end of RAM is the original's own address space rather than ours. */
        assert(cursor <= ST_RAM_BYTES - VBLQUEUE_ENTRY_BYTES);
#endif
        routine = be32(image + cursor);
        cursor = addr_add(cursor, VBLQUEUE_ENTRY_BYTES);
        if (routine != 0)
            call_vector(image, routine);
    }
}

/* BIOS Scrdmp's whole body ($fc0d50): call whatever `scr_dump` names, then set `_dumpflg` so the
 * next frame does not ask again. The VBL reaches it when the flag is ZERO — Alt-Help clears it. */
static void screen_dump(uint8_t *image)
{
    call_vector(image, be32(image + SYSVAR_SCR_DUMP));
    wr16(image + SYSVAR_DUMPFLG, 0xffff);
}

/* Declared here rather than in a header because `src/bios/isr.S` is its only other caller and an
 * assembler reads no prototype: this says the symbol is deliberately exported, and to whom. */
void service_this_vertical_blank(uint8_t *image);

/* The SERVICED body — everything past the semaphore, which is what the ROM saves the register file
 * across. EXPORTED because it is what the machine's own entry sequence calls: `src/bios/isr.S` is
 * the handler a shipped ROM installs in vector $70, and the three instructions in front of this one
 * (`_frclock`, the semaphore, the `bmi`) are the handler rather than the body. `isr_vbl` below is
 * the same shape as C, which is what Tier 1 proves. */
void service_this_vertical_blank(uint8_t *image)
{
    wr32(image + SYSVAR_VBCLOCK, be32(image + SYSVAR_VBCLOCK) + 1);
    follow_the_monitor(image);
    blink_cursor(image);
    load_the_palette(image);
    program_the_screen_base(image);
    floppy_vbl(image);
    run_the_vbl_queue(image);
    if (be16(image + SYSVAR_DUMPFLG) == 0)
        screen_dump(image);
}

void isr_vbl(uint8_t *image)
{
    uint16_t semaphore;

    wr32(image + SYSVAR_FRCLOCK, be32(image + SYSVAR_FRCLOCK) + 1);
    semaphore = (uint16_t)(be16(image + SYSVAR_VBLSEM) - 1);
    wr16(image + SYSVAR_VBLSEM, semaphore);
    if (!(semaphore & SIGN_BIT16))
        service_this_vertical_blank(image);
    wr16(image + SYSVAR_VBLSEM, (uint16_t)(be16(image + SYSVAR_VBLSEM) + 1));
}
