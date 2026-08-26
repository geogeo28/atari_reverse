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

/* ---- refusing a call, on BOTH sides ------------------------------------------------------
 * Every helper below answers "the model cannot serve this" with a sentinel: 0 from os_bconstat /
 * os_bconin / os_gem_trap / os_super, -1 from the file calls. On the ORACLE side shim.c turns that
 * sentinel into g_unmodeled and emu.run() throws the whole case away. On the CANDIDATE side the
 * same call is a no-op that returns — os_bconin with no key pending touches neither its out-param
 * nor the image — so without a tally the refusal is ONE-SIDED, and a reconstruction that drops a
 * guard the original has (the Bconstat gate before Bconin; a test of Fopen's handle) behaves
 * identically and stays green. It stays green precisely because the input that would expose the
 * difference is the one the oracle refuses to run.
 *
 * So the candidate counts its refusals. src/os_refusal.c keeps the tally and exports it — kit.mk
 * links it into every candidate, exactly as it does the Dosound ledger — and harness.differential()
 * clears it before EACH candidate run, the poison re-run included, and RAISES if it is non-zero. It
 * can do that unconditionally: a non-zero ORACLE tally already raised in emu.run(), before the diff.
 * test/test_os_refusal.py pins every refusal site below, since no differential case can: a correct
 * reconstruction never reaches one, so reverting a `return os_refused(...)` here to a bare `return`
 * leaves all three game suites green.
 *
 * A build that must NOT tally defines OS_NO_REFUSAL_TALLY and gets the no-op below — a compile-time
 * split, because nothing at runtime distinguishes the cases: it is one header built into different
 * binaries, and the only fact available is which translation unit is being compiled. Two callers:
 * shim.c, which keeps the oracle's own tally and does not link src/os_refusal.c; and any on-target
 * (real Atari) build whose cores call a refusing helper — real TOS refuses nothing, and that build
 * links the kit's src/ no more than the oracle does. Joust's PRG build is the second
 * (projects/joust/recreate/atari/build.sh passes the -D): its cores call os_fopen/os_fread and the
 * kit's staged-file model is kept on target, so the refusing helpers really are compiled in.
 * BuggyBoy's is not — its game_build.sh excludes src/os.c, the only caller it has. The switch being
 * named for what it selects rather than for the oracle is what made that one -D the whole remedy. */
#ifdef OS_NO_REFUSAL_TALLY
static inline int32_t os_refused(int32_t sentinel) { return sentinel; }
#else
int32_t  os_refused(int32_t sentinel);  /* tally one refusal, and hand `sentinel` back unchanged */
void     g_os_refusal_reset(void);      /* the harness clears the tally before each candidate run */
uint32_t g_os_refusal_count(void);      /* ...and raises on what it reads back */
#endif

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
/* Both sides of the direct-PSG model (oracle/shim.c, src/psg.c) carry a bit per register in a
 * uint16_t — which registers are seeded, known, or were read while unknown. The check lives here,
 * once, beside the count it is about: a copy in each file is a copy that can be updated in one. */
#if OS_PSG_NREGS > 16
#error "the direct-PSG known/seed masks are uint16_t: OS_PSG_NREGS registers no longer fit"
#endif

/* XBIOS Dosound(A0) writes the chip, not the image, so both sides record their calls in a ledger the
 * harness compares (src/dosound_log.c on the candidate side, shim.c's g_dosound_arg on the oracle's).
 * ONE cap for both: were they to differ, a run past the smaller one would drop entries on that side
 * only and diverge the comparison for a reason that has nothing to do with the reconstruction. */
#define OS_DOSOUND_LOG_MAX 256

/* ---- the direct $ff8800/$ff8802 PSG path (TRAP_MODEL.md, "Phase 6") --------------------------
 * The two ports the YM2149 answers on. They sit outside the image, so a reconstruction that drives
 * the chip does it through psg.h rather than by storing here; the oracle taps these addresses in its
 * memory callbacks. Defined once because BOTH sides need them — shim.c decodes them and
 * test/psg_model_probe.c plants 68000 code that reaches them — and two copies could drift into a
 * probe that no longer tests the guard it names. */
#define OS_PSG_PORT_SELECT 0xff8800u  /* register-select latch; also the chip's READ-BACK port */
#define OS_PSG_PORT_DATA   0xff8802u  /* data port: write-only on the real chip */

/* The direct path writes the chip, not the image, so it is the SECOND thing both sides record in a
 * ledger the harness compares (src/psg.c on the candidate side, shim.c's g_psg_reg/g_psg_val on the
 * oracle's). ONE cap for both, for the reason above — and it is far larger than Dosound's because
 * this ledger is also the audio-capture mode's data feed, one VBL tick's whole register stream at a
 * time. */
#define OS_PSG_LOG_MAX 4096

/* What one ledger entry IS. A READ is recorded alongside the writes, in the one ordered stream, so
 * that "this run read register 7" is a comparable fact rather than an invisible one: a
 * reconstruction that reads the WRONG register still writes the right one, leaving the write stream
 * and the register file identical on both sides (see TRAP_MODEL.md's transposed-RMW case). The
 * write-only PROJECTION of the stream is what emu.psg_writes() reports, unchanged. */
#define OS_PSG_EVENT_WRITE 0
#define OS_PSG_EVENT_READ  1

/* ---- the SEEDED HARDWARE READ model (TRAP_MODEL.md, "Phase 7") -------------------------------
 * A small NAMED SET of hardware bytes outside the PSG whose contents a case may DECLARE, exactly as
 * Phase 6 lets it declare the YM2149's registers. Everything else off-image still reads 0 and is
 * still invisible; these are singled out because the VALUE STEERS THE RUN, which is the one shape
 * where a fabricated 0 produces a green run whose behaviour is wrong on the machine (the
 * `$ffff820a` defect that survived BuggyBoy's entire differential and only appeared on real
 * hardware — see PORTABILITY.md's "the BuggyBoy defect, demonstrated concretely"). Two of the four
 * steer a BRANCH; the other two are summed into an arithmetic result, which is the same defect with
 * a wider blast radius — Wonder Boy's $51ac hashes the video counter into a 1..4 draw, so under a
 * fabricated 0 the whole draw collapses to a constant and the differential agrees on it.
 *
 * WHY A COUNTER IS ADMISSIBLE HERE and the FDC/DMA registers below are not. A per-run constant
 * cannot express a value that must CHANGE BETWEEN TWO READS OF THE SAME ADDRESS, and that is the
 * whole of the distinction. The shifter's video address counter does advance on the machine, but a
 * routine that reads $ff8207 once and $ff8209 once per run never observes it advancing: one read of
 * one address is exactly what a declared constant describes.
 *
 * AND THE CRITERION IS ENFORCED, not merely argued. Each slot carries a VOLATILE flag below: a
 * static byte (the monitor detect, the sync mode) may be read as often as a run likes, because the
 * machine's answer really is the same every time: ONE declaration describes every read of it, and
 * how many there were is no part of what the case claimed. (The tempo head reads $fffa01 once and
 * $ff820a once; what really re-reads $fffa01 is an FDC poll, and that is the shape below this model
 * excludes.) A VOLATILE one may be read ONCE per run, and a second read is a refusal beside
 * stale and wide, because the second answer a constant gives is the first one and the machine's
 * would not be. Without the flag the admissibility argument is a comment that the next handler to
 * read a counter twice quietly falsifies.
 *
 * DELIBERATELY NOT HERE: the FDC/DMA registers at $ff8604+. Those answer a per-ACCESS SEQUENCE (a
 * status byte that must change between two reads of the same address for a poll loop to terminate,
 * a DMA counter whose successive reads differ), and a per-run constant cannot express one. Phase 7
 * does not model them; TRAP_MODEL.md says so in as many words rather than leaving the omission to
 * be inferred.
 *
 * Defined here, not in shim.c, for psg.h's reason: BOTH sides need them — shim.c decodes the
 * addresses, test/hw_model_probe.c plants 68000 code that reaches them, and a reconstruction calls
 * hw.h's hw_read8() with them. The 24-bit forms are canonical (the 68000's bus aliases $fffffa01
 * onto $fffa01, and shim.c's BUS_ADDR_MASK folds an access before it is decoded). */
#define OS_HW_MFP_GPIP     0xfffa01u  /* MFP GPIP: bit 7 = colour/mono monitor detect, 5/4 = FDC/ACIA */
#define OS_HW_SHIFTER_SYNC 0xff820au  /* shifter sync mode: bit 1 SET = 50 Hz */
/* The shifter's VIDEO ADDRESS COUNTER, the address the display is currently fetching from. Three
 * bytes on the machine ($ff8205 high, $ff8207 mid, $ff8209 low); the two the games read are here
 * and the high byte is not, because nothing reaches it — it changes once a frame where these two
 * change every few scanlines, which is what makes them the pair a routine hashes for entropy. */
#define OS_HW_SHIFTER_VCOUNT_MID 0xff8207u
#define OS_HW_SHIFTER_VCOUNT_LOW 0xff8209u

/* Both sides index the modeled set by SLOT rather than by address — the seed is an array, the
 * known-mask is a bit per slot, and the ledger records a slot per entry — so the slot numbers are
 * as much a part of the shared contract as the addresses, and os_hw_addrs() below is the one table
 * that maps between them. */
#define OS_HW_SLOT_MFP_GPIP          0
#define OS_HW_SLOT_SHIFTER_SYNC      1
#define OS_HW_SLOT_SHIFTER_VCOUNT_MID 2
#define OS_HW_SLOT_SHIFTER_VCOUNT_LOW 3
#define OS_HW_NSLOTS                 4
#if OS_HW_NSLOTS > 32
#error "the seeded-hardware known/seed masks are uint32_t: OS_HW_NSLOTS slots no longer fit"
#endif

/* The ordered READ ledger's cap, on BOTH sides (shim.c's g_hw_log_* and src/hw.c's), for
 * OS_PSG_LOG_MAX's reason: were the two to differ, a long run would drop entries on one side only
 * and the streams would diverge for a reason that has nothing to do with the reconstruction. Sized
 * like the PSG's rather than like Dosound's because these addresses are POLLED — an FDC wait loop
 * reads $fffa01 once per iteration — so a modest cap would truncate an ordinary run. */
#define OS_HW_LOG_MAX 4096

/* The modeled addresses, by slot. A function-local table rather than a file-scope one so that a
 * translation unit which includes this header without using the model draws no unused-variable
 * warning, and so that both directions of the mapping are derived from ONE list. */
static inline const uint32_t *os_hw_addrs(void) {
    static const uint32_t addrs[OS_HW_NSLOTS] = {
        [OS_HW_SLOT_MFP_GPIP]          = OS_HW_MFP_GPIP,
        [OS_HW_SLOT_SHIFTER_SYNC]      = OS_HW_SHIFTER_SYNC,
        [OS_HW_SLOT_SHIFTER_VCOUNT_MID] = OS_HW_SHIFTER_VCOUNT_MID,
        [OS_HW_SLOT_SHIFTER_VCOUNT_LOW] = OS_HW_SHIFTER_VCOUNT_LOW,
    };
    return addrs;
}

/* Which slots are VOLATILE — a value the machine changes on its own, which a per-run constant can
 * describe for ONE read and not for two. A bit per slot, like every other mask in this model, and
 * derived from the same one table so that a slot added above is STATIC unless it says otherwise:
 * the conservative direction, since a static slot read twice is served twice and a volatile one is
 * refused, and a new slot wrongly called volatile would refuse runs that are fine. */
static inline uint32_t os_hw_volatile_slots(void) {
    return (1u << OS_HW_SLOT_SHIFTER_VCOUNT_MID) | (1u << OS_HW_SLOT_SHIFTER_VCOUNT_LOW);
}

/* Which slot `addr` is, or -1 for an address the model does not name. Takes a 24-bit bus address:
 * the oracle masks before it decodes, and hw.h's contract is that a reconstruction passes the
 * canonical constant above. */
static inline int os_hw_slot(uint32_t addr) {
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        if (os_hw_addrs()[slot] == addr)
            return slot;
    return -1;
}

/* Bitmask of the slots an access of `n` bytes at `addr` takes in — the WIDE form of os_hw_slot,
 * and what the oracle's write and wide-read tallies are built from. It lives here rather than in
 * shim.c so that the whole address decode is in the ONE file that owns the table: with half of it
 * next to the table and half beside the tallies, adding a third modeled address would leave byte
 * reads decoding it while wide reads and writes silently did not — and a wide read of it would then
 * be served a fabricated 0 with no tally, which is the class this model exists to close. */
static inline uint32_t os_hw_slots_touched(uint32_t addr, uint32_t n) {
    uint32_t touched = 0;
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++) {
        uint32_t modeled = os_hw_addrs()[slot];
        if (addr <= modeled && addr + n > modeled)
            touched |= 1u << slot;
    }
    return touched;
}

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
    } else if (d0 == GEM_VDI) {
        uint32_t intout = be32(mem + pblk + 3 * 4);  /* vpb[3] */
        if (opcode == VDI_V_OPNVWK) {
            /* work_out: only the two determinate low-res fields; the rest of the VDI
             * attribute table is left zero (no code reads it). */
            wr16(mem + intout + 0, OS_SCREEN_MAX_X);
            wr16(mem + intout + 2, OS_SCREEN_MAX_Y);
            return 1;
        }
    }
    return os_refused(0);                       /* unmodeled subsystem or opcode */
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
    if (dev != OS_BIOS_DEV_CON) return os_refused(0);
    *out = be32(mem + OS_CON_PENDING) ? OS_BCONSTAT_READY : 0;
    return 1;
}

/* Take the pending keystroke from the console, if there is one: 1 and *out on success, 0 when the
 * device isn't the console or nothing is staged. NOT a refusal in itself — "no key" is a legitimate
 * answer for the non-blocking os_crawio below, and only os_bconin turns it into one. */
static inline int os_console_take_key(uint8_t *mem, uint16_t dev, uint32_t *out) {
    if (dev != OS_BIOS_DEV_CON || !be32(mem + OS_CON_PENDING)) return 0;
    *out = be32(mem + OS_CON_CHAR);
    wr32(mem + OS_CON_PENDING, 0);
    return 1;
}

/* Bconin(dev) -> *out, consuming the pending keystroke. Returns 1 if modeled, 0 otherwise.
 * Reading with no character pending is refused: on real hardware Bconin BLOCKS until a key
 * arrives, and there is no key to wait for here, so any answer would be fabricated. */
static inline int os_bconin(uint8_t *mem, uint16_t dev, uint32_t *out) {
    if (os_console_take_key(mem, dev, out)) return 1;
    return os_refused(0);
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
    /* os_console_take_key, not os_bconin: an idle console is a RESULT here, not a refusal, so it
     * must not reach the tally that os_bconin's blocking-read refusal feeds. */
    return os_console_take_key(mem, OS_BIOS_DEV_CON, &key) ? key : OS_CRAWIO_RESULT;
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
    return os_refused(0);                      /* a stack pointer we never handed out */
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

/* THE SAME QUESTION FOR AN OPERAND WHOSE WIDTH IS A COMPILE-TIME CONSTANT — a bus accessor's 1, 2 or
 * 4, a blitter's screen word — AS THE ONE COMPARISON IT IS. The two clauses above collapse when the
 * count cannot wrap: given `addr <= OS_IMAGE_SIZE`, the second is exactly `addr <= OS_IMAGE_SIZE -
 * width`, which already implies the first, and an `addr` past OS_IMAGE_SIZE fails both. So this is
 * EQUAL to os_in_image for every address a longword can hold, at the image's last byte as well as
 * inside it — not a loosening. What it is not equal to is os_in_image's CODE: GCC does not fold the
 * pair on its own even with the count a literal, and each surviving comparison is a branch its two
 * arms get duplicated through. Measured on Wonder Boy (2026-08-26, -O3, on the linked ELF): 8,420
 * bytes of .text over the whole program, nearly all of it the behaviour tier, where the six
 * accessors in its include/bus.h inline at ~980 call sites. Not a cycle lever — the walking frame
 * did not move — a FLOPPY one; that project's STATUS.md, "## Performance", has both halves.
 *
 * The width is asserted rather than assumed: os_in_image's wrap-safety argument is what makes the
 * subtraction on the left safe here, and a width larger than the image would underflow it into a
 * 4 GB bound that says yes to everything. `__extension__` is what lets a declaration — the assertion
 * — sit inside an expression; both toolchains the kit builds under take it. */
#define os_in_image_fixed(addr, width) __extension__ ({                                            \
    _Static_assert((width) <= OS_IMAGE_SIZE,                                                       \
                   "os_in_image_fixed subtracts its width from OS_IMAGE_SIZE, which underflows "   \
                   "into a 4 GB bound for a width larger than the image");                         \
    (uint32_t)(addr) <= OS_IMAGE_SIZE - (uint32_t)(width);                                         \
})

/* ---- SCHEDULED WRITES: what an EXTERNAL AGENT stores mid-run (TRAP_MODEL.md, "Phase 8") -----
 *
 * A routine that BUSY-WAITS on a memory byte its own instructions never write cannot be run at all
 * by a differential as the harness was built: nothing changes memory while a run is in flight, so
 * the loop is infinite on both sides. The byte is written by something outside the routine — an
 * ACIA keyboard interrupt storing a release scancode, the VBL bumping a frame counter — and that
 * agent is what this models: a small list of stores the case DECLARES, each applied once when its
 * trigger comes due.
 *
 * ONE ENCODING FOR BOTH SIDES, `OS_SCHED_FIELDS` uint32s per entry, flattened:
 *
 *   [OS_SCHED_F_KIND]    OS_SCHED_AT_PC or OS_SCHED_AT_INSN — what the trigger counts
 *   [OS_SCHED_F_TRIGGER] the PC to arrive at, or the instruction index to reach (1-based)
 *   [OS_SCHED_F_NTH]     which arrival fires it (1 = the first); AT_INSN ignores it
 *   [OS_SCHED_F_ADDR]    where the agent stores
 *   [OS_SCHED_F_WIDTH]   1, 2 or 4 bytes, big-endian
 *   [OS_SCHED_F_VALUE]   what it stores
 *
 * The oracle counts arrivals at a PC (oracle/shim.c); the candidate has no program counter and
 * counts POLLS instead (src/sched.c, `sched_poll8`) — a reconstruction's wait loop reads its byte
 * through that one call, so its Nth poll IS the original's Nth arrival at the compare, and the
 * harness compares the two counts rather than assuming they agree. OS_SCHED_AT_INSN has no
 * candidate equivalent at all and a differential refuses one; it exists for oracle-only runs.
 *
 * ...AND THE COUNTS ARE PER WAIT SITE, which is the half a run TOTAL cannot carry. A run with two
 * waits in it has two counters on each shore, keyed by the same thing: the address of the
 * instruction that re-reads the byte the wait spins on. See "WAIT SITES" below.
 */
#define OS_SCHED_MAX      8      /* entries one run may schedule (both sides size their tables here) */
/* THE CANDIDATE'S RUNAWAY GUARD. A reconstruction's wait is a real loop in C, so a case whose store
 * never releases it does not fail — it HANGS, and a hung suite decides nothing (six mutants in this
 * model's first sweep failed that way). Past this many polls of one wait, `sched_wait8` gives up and
 * tallies a refusal, which the harness turns into a rejected case with a name on it. Sized far above
 * any wait a case can declare — `nth` is bounded by it, and the oracle's own instruction cap bites
 * first for anything realistic — so it can only be reached by a wait that was never going to end. */
#define OS_SCHED_POLL_MAX 4096u
#define OS_SCHED_FIELDS   6      /* uint32s per entry in the flattened array, as listed above */
#define OS_SCHED_F_KIND    0
#define OS_SCHED_F_TRIGGER 1
#define OS_SCHED_F_NTH     2
#define OS_SCHED_F_ADDR    3
#define OS_SCHED_F_WIDTH   4
#define OS_SCHED_F_VALUE   5
#define OS_SCHED_AT_PC    0u     /* fire before the NTH execution of the instruction at TRIGGER */
#define OS_SCHED_AT_INSN  1u     /* fire before the run's TRIGGERth instruction, 1 = the first
                                  * (oracle only: the candidate counts polls, not instructions) */

/* Copy `n` entries of the flattened array into `dst`, clamped to OS_SCHED_MAX; return how many were
 * kept. The two sides share this for os_sched_store's reason — the STRIDE and the drop policy must
 * be one decision, or a change applied to one file alone leaves the two decoding different stores
 * from the same array, which presents as "the wait loop never ended". Both callers report the kept
 * count (osh_sched_count / g_sched_count) and both harness sides assert it against what they sent. */
static inline uint32_t os_sched_install(uint32_t dst[][OS_SCHED_FIELDS], const uint32_t *entries,
                                        uint32_t n) {
    uint32_t kept = n > OS_SCHED_MAX ? OS_SCHED_MAX : n;
    for (uint32_t i = 0; i < kept; i++)
        for (uint32_t f = 0; f < OS_SCHED_FIELDS; f++)
            dst[i][f] = entries[i * OS_SCHED_FIELDS + f];
    return kept;
}

/* ---- WAIT SITES: WHICH wait a poll or an arrival belongs to -----------------------------------
 *
 * A run may hold more than one busy-wait, and a COUNTER PER RUN cannot tell them apart. That is not
 * a theoretical gap: with two waits under one trigger PC the oracle's arrivals and the candidate's
 * polls can balance BY CANCELLATION — the second wait runs one iteration fewer on the candidate and
 * the first wait's poll makes the total up — so the comparison agrees while the two sides ran
 * different loops, and a port that DELETED the first wait passes. (Wonder Boy's `flip_screen` is the
 * arrangement; projects/wonderboy/recreate/STATUS.md's batch 42 phases B and C are the measurement.)
 *
 * So a run DECLARES its wait sites, and both sides count per site:
 *
 *   * a SITE is the address of the instruction that RE-READS THE POLLED BYTE — not merely some
 *     instruction the loop re-executes. That is the load-bearing half: `sched_fire` applies a due
 *     store just BEFORE the instruction at the site runs, and the candidate's poll applies it just
 *     before its own read, so the two sides see the new value at the same iteration only when the
 *     site is the READ. Wonder Boy's `$6aa` is the `move.w $74a.l,d0` and not the `cmpi.w` two
 *     instructions below it; where a wait reads and compares in ONE instruction (`cmpi.b
 *     #$99,$879.l`) the two coincide, which is what makes the looser reading easy to write down.
 *     It is the same address an AT_PC entry names as its trigger, and every AT_PC trigger must be
 *     one of the declared sites;
 *   * the ORACLE bumps site S's arrival count each time it executes the instruction at S;
 *   * the CANDIDATE names the site at every poll (`sched_poll8(image, addr, site_pc)`) and bumps the
 *     same counter, because it has no program counter of its own to be asked;
 *   * an AT_PC entry fires when ITS SITE's count reaches its `nth`, on both shores;
 *   * `harness.differential` compares the two counts SITE BY SITE.
 *
 * WHICH HALF DOES THE WORK: the FIRING rule. An entry keyed to its own site's count makes the two
 * sides' run totals diverge on a port that ran a different loop, so the totals catch it before the
 * per-site comparison is reached. That comparison is kept as a tripwire and is NOT claimed as
 * covered — every composite written to isolate it came back caught by the firing rule instead.
 *
 * A poll naming a site the run did not declare is a REFUSAL (os_refused), for the seeded models'
 * reason: an uncounted poll is exactly the hole above, and quietly serving one would leave the
 * comparison blind to the wait it came from.
 *
 * A per-ADDRESS counter would not do: Wonder Boy's `game_key_actions` has two waits on the SAME
 * byte at two addresses, so the poll's ADDRESS says nothing about which wait made it. The site is
 * the PC, always. */
#define OS_SCHED_SITE_MAX 4      /* distinct wait sites one run may declare (both sides size here) */
#define OS_SCHED_NO_SITE  0xffffffffu   /* os_sched_site_index: this PC is not a declared site */

/* Copy `n` site PCs into `dst`, clamped to OS_SCHED_SITE_MAX; return how many were kept.
 * os_sched_install's rule, for os_sched_install's reason: one decision about the drop policy. */
static inline uint32_t os_sched_install_sites(uint32_t *dst, const uint32_t *sites, uint32_t n) {
    uint32_t kept = n > OS_SCHED_SITE_MAX ? OS_SCHED_SITE_MAX : n;
    for (uint32_t i = 0; i < kept; i++)
        dst[i] = sites[i];
    return kept;
}

/* Where `pc` sits in the run's declared site list, or OS_SCHED_NO_SITE. Shared so that "which wait
 * is this" is answered identically on both shores — the two counters being compared are only
 * comparable while they are keyed the same way. */
static inline uint32_t os_sched_site_index(const uint32_t *sites, uint32_t n, uint32_t pc) {
    for (uint32_t i = 0; i < n; i++)
        if (sites[i] == pc)
            return i;
    return OS_SCHED_NO_SITE;
}

/* Store `value` at `addr` in the `size`-byte `image`, big-endian, at 1/2/4 bytes — the agent's write,
 * and the one spelling of it. Both sides call this so that a straddle of the image's top, or an
 * unsupported width, cannot be handled one way by the oracle and another by the candidate. Returns 0
 * (and stores nothing) for a width the model does not carry or a range outside the image; the
 * callers treat that as a refusal rather than a silent no-op.
 *
 * `size` is a parameter rather than OS_IMAGE_SIZE because the ORACLE is handed its buffer's length
 * per run (shim.c's g_size) and the kit's own probes run it on a 64 KiB scratch image — bounding a
 * store against the constant there would write past the buffer. The candidate side has no such
 * parameter to pass and uses OS_IMAGE_SIZE, which is the image every reconstruction is given.
 * Written as a subtraction, never `addr + width`, for os_in_image's reason. */
static inline int os_sched_store(uint8_t *image, uint32_t size, uint32_t addr, uint32_t width,
                                 uint32_t value) {
    if (width != 1 && width != 2 && width != 4)
        return 0;
    if (addr > size || width > size - addr)
        return 0;
    for (uint32_t i = 0; i < width; i++)
        image[addr + i] = (uint8_t)(value >> (8 * (width - 1 - i)));
    return 1;
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
    if (slot < 0) return os_refused(-1);
    uint8_t *entry = os_fs_slot(mem, slot);
    wr32(entry + OS_FS_OFF_CURSOR, 0);
    wr32(entry + OS_FS_OFF_OPEN, 1);
    return OS_FS_FIRST_HANDLE + slot;
}

/* Fcreate(name, attr): open the staged file the same way Fopen does, then truncate it to zero
 * length. -1 if the harness never staged that name — the model has no staging space to hand out,
 * so it refuses instead of inventing an address. */
static inline int32_t os_fcreate(uint8_t *mem, uint32_t name_ptr) {
    int32_t handle = os_fopen(mem, name_ptr);        /* which already tallied the refusal, if any */
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
    if (!entry || be32(entry + OS_FS_OFF_OPEN) == 0) return os_refused(-1);  /* not staged/not open */
    uint32_t staging = be32(entry + OS_FS_OFF_STAGING);
    uint32_t cursor = be32(entry + OS_FS_OFF_CURSOR);
    uint32_t n = be32(entry + OS_FS_OFF_SIZE) - cursor;  /* remaining; cursor never exceeds size */
    if (count < n) n = count;
    if (!os_fs_copy_in_image(staging, cursor, buf, n)) return os_refused(-1);
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
    if (!entry || be32(entry + OS_FS_OFF_OPEN) == 0) return os_refused(-1);
    uint32_t staging = be32(entry + OS_FS_OFF_STAGING);
    uint32_t cursor = be32(entry + OS_FS_OFF_CURSOR), capacity = be32(entry + OS_FS_OFF_CAPACITY);
    /* Written as a subtraction, never `cursor + count > capacity`: `count` comes straight off the
     * emulated program's stack, so the sum wraps for a large count and would wave through a memcpy
     * that runs off the end of the image. */
    if (cursor > capacity || count > capacity - cursor) return os_refused(-1);
    if (!os_fs_copy_in_image(staging, cursor, buf, count)) return os_refused(-1);
    memcpy(mem + staging + cursor, mem + buf, count);
    wr32(entry + OS_FS_OFF_CURSOR, cursor + count);
    if (cursor + count > be32(entry + OS_FS_OFF_SIZE))
        wr32(entry + OS_FS_OFF_SIZE, cursor + count);
    return (int32_t)count;
}

/* Fclose(handle): mark the slot closed. -1 on a bad handle. */
static inline int32_t os_fclose(uint8_t *mem, uint16_t handle) {
    uint8_t *entry = os_fs_entry(mem, handle);
    if (!entry) return os_refused(-1);
    wr32(entry + OS_FS_OFF_OPEN, 0);
    return 0;
}

#endif /* BB_OS_H */