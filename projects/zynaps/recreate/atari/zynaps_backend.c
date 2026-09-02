/* zynaps_backend.c — the seam's target half: every symbol the differential harness MODELLED, done
 * for real on the machine.
 *
 * Off target these live in translation units this build leaves out — `tools/recreate_kit/src/hw.c`
 * (the ordered hardware read/write ledgers) and `tools/recreate_kit/src/psg.c` (the YM2149's two
 * ports). Both files say in their own headers that a build for the real Atari does not compile them
 * and drives the chips itself. This is that file. `README.md`'s seam table is the inventory; this
 * is the code.
 *
 * WHAT MAKES IT SAFE TO SUBSTITUTE. Each substitute has the same signature and the same CALL SITES
 * as the modelled routine, so the cores are compiled unchanged and the differential .so is
 * untouched — `make test` is still 3979 (build.sh measures the cores' whole include closure, and
 * checks that no symbol here collides with one a core defines). What changes is only what the
 * access lands on: an ordered ledger off target, a device register here.
 *
 * ...AND WHAT DOES NOT MAKE IT SAFE. A seam prices what the substituted code RETURNS, not what it
 * did to shared state on the way (docs/on-target-execution.md class 11). `hw_write*` is write-only
 * to a device and reads nothing back, so there is no protocol under it to drop. `hw_read8` answers
 * the real 6850 rather than the model's seeded byte, which is the whole point of it being here.
 *
 * THE DOORS THEMSELVES ARE NO LONGER IN THIS FILE. `shim_include/hw.h` and `psg.h` shadow the kit's
 * headers and define all eight as `static inline`, because a body a call site can see folds the
 * address arithmetic and the store classification away at a constant address — 205 cycles a call
 * for a 24-cycle store, before. Those headers carry that argument. What is left here is what a
 * header cannot hold: the COUNTERS the doors keep, which are the only surface a target run has for
 * a store, and the one door that is a PROTOCOL rather than a store — the shifter's video base,
 * whose value is an image offset the machine cannot use as it stands.
 */
#include <stdint.h>

#include "hw.h"            /* the doors, and `zy_note_store`, which is what they count */
#include "os.h"            /* the file seam's three counters, beside the guards that keep them */

#include "video.h"         /* HW_SCREEN_BASE_MID / _HIGH — the video base's two bytes */
#include "zynaps_target.h"

/* ================================================================================================
 * THE HARDWARE DOORS THEMSELVES ARE IN shim_include/hw.h, AND THIS IS WHAT THEY COUNT.
 *
 * The seven names the kit declares — `hw_read8`, `hw_write8/16/32`, `hw_bset8`/`hw_bclr8`/`hw_and8`
 * — used to be functions in this file. They are `static inline` in the shadowing header now, for
 * one measured reason: their callers all pass CONSTANT addresses, and a body a call site can see
 * folds the whole classification chain away, where a cross-unit call pays 205 cycles for a 24-cycle
 * store. That header carries the arithmetic and the before/after numbers.
 *
 * What stays here is what a header cannot hold: the COUNTERS the doors keep, which are the only
 * surface a target run has for a store (off target the kit's ordered ledger is), and the ONE door
 * that is a protocol rather than a store — the shifter's video base, whose value is an image offset
 * the machine cannot use as it stands.
 * ============================================================================================= */

/* Every store made through these doors, so a run that touched no hardware is separable from one
 * whose writes went somewhere unexpected. smoke.py predicts it exactly (README.md's seam table
 * carries the arithmetic), which is only possible while `zy_hw_writes++` stays one `addq.l` — see
 * zynaps_main.c's note on the boot's one critical section. */
volatile uint32_t zy_hw_writes;

/* THREE ADDRESS-KEYED TALLIES, and they exist because three CORE effects are otherwise invisible
 * here. Off target each of the three is held by the kit's ordered (address, width, value) ledger,
 * which `harness.differential` compares entry for entry; on target there is no ledger, so the shim
 * counts the stores as they pass and STATE.BIN carries the counts. Each is keyed on something the
 * shim's OWN traffic cannot forge:
 *
 *   - the resolution byte is at an address nothing else in this build writes;
 *   - the boot's title palette is the only LONGWORD-wide traffic into the colour block
 *     (`set_palette_title` ends in `movem.l #$00ff,$ff8240.l`); the shim's own pen writes and the
 *     control's injected fault are word-wide, so they cannot inflate this count;
 *   - the IKBD data port is written only by `ikbd_send_cmd`, which this build calls twice.
 *
 * They replace ../src/init.c's `init_palette_uploads` / `init_shifter_mode_writes`, which the write
 * ledger retired: the counting moved to where the store now actually happens. */
volatile uint32_t zy_shifter_mode_writes;
volatile uint32_t zy_palette_long_writes;
volatile uint32_t zy_acia_bytes_sent;

/* Read-modify-writes the cores made through `hw_bset8`/`hw_bclr8`/`hw_and8`. The three doors
 * themselves are in shim_include/hw.h, where a call site can see them; this is the count they
 * keep, and it is a surface rather than bookkeeping — a build that had somehow linked the kit's
 * own off-target `src/hw.c` instead would show 0. */
volatile uint32_t zy_rmw_stores;

/* ================================================================================================
 * THE ADDRESS-KEYED LEDGER THAT IS NOT HERE, and the measurement that took it out.
 *
 * README.md's Unpinned 15 asked for one: the three tallies above are keyed on arguments about
 * today's call sites (a width, an address nothing else writes), and the depth-correct replacement is
 * a small on-target ledger of stores PER ADDRESS, which would subsume all three. It was written,
 * twice, and both drafts had to be deleted for a reason that is a finding in its own right.
 *
 * ATTRACT MODE'S TIMER B FIRES EVERY TWO SCANLINES — about 1024 CPU cycles at 8 MHz — and its
 * handler makes two hardware stores (pen 0 and the MFP acknowledge). MEASURED on `build.sh game`
 * under Hatari: WITH the ledger the handler took about 2000 cycles, i.e. longer than its own
 * period, and the main line advanced a couple of instructions a frame — twenty seconds inside an
 * eight-iteration palette upload, and the title page never drawn. WITHOUT it the same build runs the
 * attract loop, starts a game and reaches the section start. The second draft replaced the linear
 * scan with a direct-mapped hash and was still over the cliff: what costs is the extra CALL and its
 * argument, not the search.
 *
 * THE RATE THIS PARAGRAPH USED TO QUOTE — "only 79 of the frame's 156 interrupts arrived" — WAS
 * WRONG IN BOTH HALVES AND IS RETRACTED. Timer B is in EVENT-COUNT mode, so the event it counts is
 * the shifter's display-enable pulse, one per DISPLAYED scanline: ST low resolution has 200 of
 * those, not 313, and at a period of 2 the chip offers 100 interrupts a vertical blank rather than
 * 156. And the build this file describes serves 6,263 of them over 64 attract vertical blanks —
 * 98% — which `smoke.py`'s `check_the_pacing` now holds to a floor. What is quoted above is the
 * measurement that stands: the ledger made the handler longer than its period, and deleting it is
 * what fixed that.
 *
 * So the shape a target build can afford is a fixed set of NAMED counters — the three above, which
 * compile to one compare and one `addq` each — and not a table. `docs/on-target-execution.md`'s
 * taxonomy 13 is the class this belongs to, and atari/README.md's PERFORMANCE section carries the
 * whole table.
 * ============================================================================================= */

/* ================================================================================================
 * THE VIDEO BASE, WHICH IS THE ONE STORE WHOSE VALUE MEANS SOMETHING ELSE HERE.
 *
 * `screen_flip_buffers` publishes `offset >> 8` and `offset >> 16` of the buffer it has just drawn
 * into — an IMAGE offset, because in the differential's world the image is the machine's memory and
 * starts at 0, and because the original's framebuffers are absolute against the base it runs at.
 * This build stages the image in a `.bss` array, so the shifter needs `zy_image_base + offset`.
 *
 * IT IS DONE HERE AND NOT IN THE SHIM'S MAIN LINE, and that is M2's change: the frame loop flips
 * every frame, so re-publishing the machine address after the fact — M1's arrangement, workable
 * while the boot flipped once — would leave the shifter pointed at $0703xx for most of every frame.
 * The door is the one place the CORE ITSELF REACHES.
 *
 * THE OFFSET IS ASSEMBLED ACROSS THE TWO STORES because a byte of a sum is not the sum of a byte:
 * `zy_image_base + offset` carries out of bits 8-15 into 16-23, so neither store can be translated
 * on its own. Each store updates its own half of the remembered offset and then publishes the WHOLE
 * translated address, so after the pair the register is right whichever order the two arrive in.
 * What that costs is the same transient the original has: between the two stores the register holds
 * an address one byte of which is a frame old — and the shifter latches its base at the next
 * vertical blank, not at the store, so no frame is ever fetched from the intermediate value unless
 * a vertical blank falls exactly between two instructions. The original's own pair has that window
 * too, and this build does not widen it. */
static volatile uint32_t g_video_base_offset;

/* What the cores have published, for the record: the offset they last named and the machine address
 * this file translated it to. `smoke.py game` asserts that the second is the first plus the image
 * base, which is the surface for a translation that silently stopped happening. */
volatile uint32_t zy_video_base_offset;
volatile uint32_t zy_video_base_published;
volatile uint32_t zy_video_base_publishes;

static void publish_translated_video_base(void) {
    uint32_t machine = (uint32_t)(uintptr_t)zy_image_base + g_video_base_offset;

    *(volatile uint8_t *)HW_BUS(HW_SCREEN_BASE_MID) = (uint8_t)(machine >> VIDEO_BASE_MID_SHIFT);
    *(volatile uint8_t *)HW_BUS(HW_SCREEN_BASE_HIGH) = (uint8_t)(machine >> VIDEO_BASE_HIGH_SHIFT);
    zy_note_store(HW_BUS(HW_SCREEN_BASE_MID), sizeof (uint8_t));
    zy_note_store(HW_BUS(HW_SCREEN_BASE_HIGH), sizeof (uint8_t));
    zy_video_base_offset = g_video_base_offset;
    zy_video_base_published = machine;
    zy_video_base_publishes++;
}

/* ================================================================================================
 * THE TEMPORARY BRIDGE THAT USED TO BE HERE IS GONE, and its absence is worth a paragraph.
 *
 * Until kit commit `2db68f6` the cores spelt all six read-modify-write sites as
 * `hw_write8(<register>, <the byte a fabricated 0 read produces>)`, and this file recognised those
 * five registers by ADDRESS and made the real operation anyway — because shipping the plain store
 * would have disabled Timer C, TOS's 200 Hz clock and the floppy's motor timeout, the first time
 * the game enabled its keyboard. The cores call `hw_bclr8`, `hw_bset8` and `hw_and8` themselves
 * now, so the bridge would be a second implementation of an operation its callers already spell,
 * and the only honest thing to do with it was delete it. `zy_rmw_stores` above is what is left:
 * the count that says the operation really happens on the machine.
 * ============================================================================================= */

/* THE ONE BYTE STORE THAT IS A PROTOCOL AND NOT A STORE, which is why it stays here while the
 * other six doors moved into shim_include/hw.h. `hw_write8` recognises the shifter's two base
 * bytes at their call site — both constants, so the recognition itself folds away — and hands them
 * here, where the accumulated offset lives.
 *
 * OUT OF LINE ON PURPOSE. It runs twice a frame, so nothing about its cost is worth inlining, and
 * keeping the offset's only writer in one translation unit is what makes `g_video_base_offset`
 * `static`.
 *
 * IT TESTS FOR BOTH ADDRESSES AND FALLS BACK TO AN ORDINARY STORE, which is what the `switch` this
 * replaced did with its `default:` arm. `hw_write8`'s guard names these two registers and nothing
 * else, so the third arm is unreachable through it today — but this is a GLOBAL now, where the
 * `switch` was `static` in the file that owned its only caller, and an `else` that assumed HIGH
 * would take any other address, OR it into bits 23-16 of the offset and point the shifter at
 * `zy_image_base + garbage`. That failure is invisible to the record's own check, which compares
 * `zy_video_base_published` against what this function computed — it would agree with the garbage. */
void zy_store_video_base_byte(uint32_t bus_addr, uint32_t value) {
    if (bus_addr == HW_BUS(HW_SCREEN_BASE_MID))
        g_video_base_offset = (g_video_base_offset & ~(uint32_t)VIDEO_BASE_MID_MASK)
                              | ((value & 0xffu) << VIDEO_BASE_MID_SHIFT);
    else if (bus_addr == HW_BUS(HW_SCREEN_BASE_HIGH))
        g_video_base_offset = (g_video_base_offset & ~(uint32_t)VIDEO_BASE_HIGH_MASK)
                              | ((value & 0xffu) << VIDEO_BASE_HIGH_SHIFT);
    else {
        *(volatile uint8_t *)bus_addr = (uint8_t)value;
        zy_note_store(bus_addr, sizeof (uint8_t));
        return;
    }
    publish_translated_video_base();
}

/* The YM2149's two ports are shim_include/psg.h's door, for `flush_shadow` in ../src/sound.c — and
 * these are the writes it made and the writes it REFUSED. A register outside 0..15 is refused
 * rather than masked down, because the ST's select latch decodes four bits and a driver that put
 * anything in the upper nibble meant something the chip does not do; masking would leave a mutated
 * driver silently steering a real chip, and counting the refusal makes it a number STATE.BIN
 * carries. */
volatile uint32_t zy_psg_writes;
volatile uint32_t zy_psg_refused;

/* ...and the file seam's, declared in shim_include/os.h beside the guards that keep them. Defined
 * HERE rather than in zynaps_main.c because os.h is included by the CORES too: a definition in a
 * header would be one per translation unit, and the counts would be per-file rather than per-run. */
volatile uint32_t zy_file_opens;
volatile uint32_t zy_file_open_failures;
volatile uint32_t zy_file_refusals;

/* ================================================================================================
 * The freestanding libc the cores need. m68k-elf ships none, and `-ffreestanding -nostdlib` is
 * what makes that explicit rather than accidental.
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC recognising each of these loops and
 * replacing it with a call to itself.
 * ============================================================================================= */
void *memset(void *dst, int c, unsigned long n) {
    unsigned char *out = dst;

    while (n--)
        *out++ = (unsigned char)c;
    return dst;
}

void *memcpy(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    while (n--)
        *out++ = *in++;
    return dst;
}

/* Overlap-safe, which memcpy is not: ../src/text.c is the caller and it is the reason this is a
 * separate body rather than an alias. */
void *memmove(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    if (out <= in)
        return memcpy(dst, src, n);
    out += n;
    in += n;
    while (n--)
        *--out = *--in;
    return dst;
}
