/* shim.c — Musashi (MAME 68000 core) backing the differential oracle.
 *
 * Musashi calls back into these m68k_read/write_memory_* functions for every access;
 * we service them from a flat big-endian image supplied by Python and log every written
 * address (the write-set). osh_run() sets registers, runs a function to its return
 * (detected via a sentinel return address), and leaves final memory in the shared buffer.
 */
#include <stdint.h>
#include "m68k.h"
/* The oracle's CPU takes no trace exception — a stated modelling decision (TRAP_MODEL.md, "The CPU
 * configuration"), set by -DM68K_EMULATE_TRACE=0 in kit.mk's OCFLAGS. m68k.h pulls in m68kconf.h,
 * so by here the macro holds its EFFECTIVE value however it was arrived at, and this refuses the
 * build if that value is ever ON. It is the kit-wide half of the pin: the -D would otherwise be
 * silently undone by a `make OCFLAGS=...`, a dropped continuation, or an upstream m68kconf.h whose
 * #ifndef guard went away, and the only thing that would notice is one project's test suite
 * (projects/wonderboy/recreate/test/test_copylock.py::test_the_oracles_cpu_takes_no_trace_exception,
 * which stays as the behavioural half — it checks that Musashi HONOURS the setting). Same reasoning
 * as OS_NO_REFUSAL_TALLY below: a build flag can be forgotten where an adjacent check cannot. */
#if M68K_EMULATE_TRACE != M68K_OPT_OFF
#error "the oracle requires M68K_EMULATE_TRACE OFF (kit.mk OCFLAGS); see TRAP_MODEL.md"
#endif
/* The oracle keeps its own refusal tally — g_unmodeled, below — so os.h must give it the no-op
 * os_refused() rather than the candidate-side counter in ../src/os_refusal.c, which the oracle does
 * not link. Declared here rather than as a -D in kit.mk because this is the only oracle translation
 * unit that includes os.h, and a build flag can be forgotten where an adjacent #define cannot. */
#define OS_NO_REFUSAL_TALLY 1
#include "os.h"

static uint8_t *g_mem;
static uint32_t g_size;

#define MAX_WRITES (1u << 20)
static uint32_t g_waddr[MAX_WRITES];
static uint32_t g_wn;

/* --- optional executed-PC coverage (off by default; osh_cov_enable turns it on) --------------
 * A bit per image byte address, accumulated ACROSS osh_run calls (reset with osh_cov_reset), so a
 * whole test session's oracle execution can be queried. tools/coverage_gap.py uses it to flag
 * side-effecting call sites (Dosound/INITTUNE/INITFX/stop_music/... bsr sites) that no test ever
 * executes — i.e. sound/OS triggers whose effect is off-image and thus invisible to the diff.
 * Gated so it adds nothing to a normal `make test`. */
#define COV_SIZE (1u << 20)                 /* one bit per address in [0, 1 MiB) */
static uint8_t g_cov[COV_SIZE / 8];
static int     g_cov_on;
void osh_cov_enable(int on) { g_cov_on = on; }
void osh_cov_reset(void)    { for (uint32_t i = 0; i < sizeof g_cov; i++) g_cov[i] = 0; }
int  osh_cov_visited(uint32_t pc) { return pc < COV_SIZE && ((g_cov[pc >> 3] >> (pc & 7)) & 1); }

/* --- optional cycle-per-PC profile (off by default; osh_prof_enable turns it on) -------------
 * One uint32 cycle tally per even PC in [0, PROF_SIZE), accumulated across osh_run_bench calls
 * (reset with osh_prof_reset). Sized for the cross-compiled recon/remaster ELFs, which link at
 * base 0 and stay well under 1 MiB of text. remaster's tools/profile.py maps the tallies back to
 * symbols. Gated so it adds nothing to a normal bench run. */
#define PROF_SIZE (1u << 20)                /* PCs covered: [0, 1 MiB) */
static uint32_t g_prof[PROF_SIZE / 2];      /* tally per even PC */
static int      g_prof_on;
void osh_prof_enable(int on) { g_prof_on = on; }
void osh_prof_reset(void)    { for (uint32_t i = 0; i < PROF_SIZE / 2; i++) g_prof[i] = 0; }
const uint32_t *osh_prof_data(void)  { return g_prof; }
uint32_t        osh_prof_slots(void) { return PROF_SIZE / 2; }

/* --- SCHEDULED WRITES: the oracle side of the external-agent model (os.h, "Phase 8") ---------
 *
 * A routine that busy-waits on a byte its own instructions never write needs something outside it
 * to store one. os.h owns the encoding and says why; this holds the run's list, counts arrivals at
 * each entry's trigger PC, and applies each entry ONCE when it comes due.
 *
 * THE AGENT'S STORE IS NOT IN THE WRITE-SET. It goes straight into g_mem rather than through
 * m68k_write_memory_*, because the write-set is what the FUNCTION stored — the harness's attribution
 * pass poisons exactly those bytes and re-runs, and a byte the agent supplies is an input to the run,
 * not an output of it. The candidate applies the identical store from the identical list, so the
 * final images still agree byte for byte. */
static uint32_t g_sched[OS_SCHED_MAX][OS_SCHED_FIELDS];
static uint32_t g_sched_n;
static uint32_t g_sched_seen[OS_SCHED_MAX];   /* arrivals at this entry's trigger PC, so far */
static uint8_t  g_sched_fired[OS_SCHED_MAX];  /* ...and whether it has already been applied */
static uint32_t g_sched_applied;              /* entries applied this run */
static uint32_t g_sched_arrivals;             /* total arrivals at any AT_PC entry's trigger */
static uint32_t g_sched_refused;              /* entries whose store os_sched_store would not make */

/* Install the run's schedule. Entries past OS_SCHED_MAX are DROPPED and reported through
 * osh_sched_count(), which emu.run checks against what it passed (`_install_schedule`): silently
 * carrying fewer entries than the case declared would leave the wait loop spinning to the
 * instruction cap with no cause named.
 *
 * THE LIST IS NOT PER-RUN STATE and sched_enter_run does not clear it — only the counters. What
 * makes a schedule not leak into the next case is that emu.run calls this before EVERY run, an
 * empty one included; a C caller that drives osh_run directly (the probes in ../test) inherits
 * whatever the last install left and must install its own, empty or not. */
void osh_schedule(const uint32_t *entries, uint32_t n) {
    g_sched_n = os_sched_install(g_sched, entries, n);
}

/* Apply every entry the instruction about to run brings due. Called once per instruction, BEFORE it
 * executes, so an AT_PC entry with nth = 1 lands before the compare at that PC reads its byte —
 * which is what makes it the same event as the candidate's first `sched_poll8`. */
static void sched_fire(uint32_t pc, uint32_t insn_index) {
    int arrived = 0;   /* did THIS instruction match any AT_PC entry's trigger? */
    for (uint32_t i = 0; i < g_sched_n; i++) {
        int due;
        if (g_sched[i][OS_SCHED_F_KIND] == OS_SCHED_AT_PC) {
            if (pc != g_sched[i][OS_SCHED_F_TRIGGER])
                continue;
            /* ONE ARRIVAL PER INSTRUCTION, however many entries name this PC — the harness compares
             * the total against the candidate's POLL count, and a wait polls once per iteration
             * whether the case declared one store on it or three. Counted after the entry has fired
             * too: a port that polls a different number of times is what the comparison is for. */
            arrived = 1;
            g_sched_seen[i]++;
            due = g_sched_seen[i] == g_sched[i][OS_SCHED_F_NTH];
        } else {
            due = insn_index == g_sched[i][OS_SCHED_F_TRIGGER];   /* 1-based; see osh_run's loop */
        }
        if (!due || g_sched_fired[i])
            continue;
        g_sched_fired[i] = 1;
        if (os_sched_store(g_mem, g_size, g_sched[i][OS_SCHED_F_ADDR],
                           g_sched[i][OS_SCHED_F_WIDTH], g_sched[i][OS_SCHED_F_VALUE]))
            g_sched_applied++;
        else
            g_sched_refused++;
    }
    g_sched_arrivals += (uint32_t)arrived;
}

static void sched_enter_run(void) {
    g_sched_applied = 0;
    g_sched_arrivals = 0;
    g_sched_refused = 0;
    for (uint32_t i = 0; i < OS_SCHED_MAX; i++) {
        g_sched_seen[i] = 0;
        g_sched_fired[i] = 0;
    }
}

uint32_t osh_sched_count(void)     { return g_sched_n; }
uint32_t osh_sched_applied(void)   { return g_sched_applied; }
uint32_t osh_sched_arrivals(void)  { return g_sched_arrivals; }
uint32_t osh_sched_refused(void)   { return g_sched_refused; }
uint32_t osh_sched_max(void)       { return OS_SCHED_MAX; }
uint32_t osh_sched_fields(void)    { return OS_SCHED_FIELDS; }

/* The 68000 has a 24-bit address bus, so the top byte of an address is ignored: $ffff8800 and
 * $fffffc00 reach the same hardware as $ff8800 and $fffc00. Every hardware-address comparison below
 * masks with this first, so the idiom a game uses to reach a register cannot decide whether the
 * guard sees it. */
#define BUS_ADDR_MASK 0xffffffu

/* --- IKBD 6850 ACIA (keyboard/joystick), $fffffc00/02 -> 24-bit bus alias $fffc00/02 -----
 * read_joystick busy-waits on the status TDRE bit then sends a command; the joystick reply
 * arrives via an interrupt we don't run (input state is instead scripted as an image global —
 * see HARNESS.md). We model only what the traced code touches: the status reads back as "ready
 * to send" so the wait loop terminates. The command byte written to IKBD_DATA lands above the
 * image and is dropped by the bounds check like any other hardware write. */
#define IKBD_STATUS 0xfffc00
#define IKBD_TX_RDY 0x02        /* TDRE: transmit register empty */

/* --- PSG (YM2149) capture -----------------------------------------------------------
 * The sound driver talks to the PSG by writing a register number to $ff8800 (select
 * latch) then the value to $ff8802 (data). Those addresses sit above the 1 MiB image, so
 * the accesses would otherwise vanish. Tap them here into an ordered event log the sound
 * tools read after each REFRESH run — the register stream that drives a Python YM2149. */
/* The canonical pair is os.h's OS_PSG_PORT_SELECT / OS_PSG_PORT_DATA — one definition, because
 * test/psg_model_probe.c plants 68000 code that must reach the same two addresses this decodes.
 * (The 68000's 24-bit bus aliases $ffff8800 onto $ff8800; BUS_ADDR_MASK above is what makes the
 * comparison see both.)
 *
 * The ST decodes the YM2149 incompletely: it answers across the whole $ff8800..$ff88ff block, of
 * which those two are the canonical pair. The guards below cover the BLOCK, not the pair — a driver
 * reaching the chip through a mirror is using the direct path just as much, and guarding only the
 * pair would let it disarm the mixed-path check. */
#define PSG_BLOCK_END 0xff8900
/* The ledger's cap is os.h's OS_PSG_LOG_MAX — ONE cap for both sides, like OS_DOSOUND_LOG_MAX:
 * harness.differential compares this ledger against the candidate's (src/psg.c), and were the two
 * caps to differ a long run would drop entries on one side only and diverge for a reason that has
 * nothing to do with the reconstruction. */
static uint8_t  g_psg_kind[OS_PSG_LOG_MAX];   /* OS_PSG_EVENT_WRITE / OS_PSG_EVENT_READ (os.h) */
static uint8_t  g_psg_reg[OS_PSG_LOG_MAX];
static uint8_t  g_psg_val[OS_PSG_LOG_MAX];
static uint32_t g_psgn;        /* captured direct accesses this run — READS INCLUDED */
/* Accesses this run that did NOT fit in the ledger. The ledger is the audio-capture mode's PRIMARY
 * DATA FEED (an extractor reads a whole song out of it, tick by tick), so a silent truncation would
 * not merely lose diagnostics: it would read as a complete capture with a section of the song
 * missing. emu.run names it as its own cause, the same way it names the PSG refusals. */
static uint32_t g_psg_dropped;
static uint8_t  g_psg_latch;   /* register selected by the last $ff8800 write */
/* Has ANYTHING selected a register yet? A read of $ff8800 answers the LATCHED register, so with no
 * select the model would be answering a register the run never named — g_psg_latch's initial 0 is
 * this file's convention, not the chip's state, and on a real ST the latch holds whatever the last
 * driver to touch the chip left there. That is the same "the value is an input, do not invent it"
 * argument the register file rests on, so it gets the same answer: refuse, and name the missing
 * select. It is NOT seedable, deliberately — see TRAP_MODEL.md, Phase 6. */
static int      g_psg_latch_known;

/* --- the modeled YM2149 register file (the direct path's READABLE state) ---------------------
 * The ledger above records the ORDER of the writes; this records their EFFECT — what the chip hands
 * back to a `move.b $ff8800,dn` read of the currently selected register. It is what makes a
 * read-modify-write ("select the mixer, read it, merge in this module's channels, write it back")
 * runnable at all, and every PSG writer in Wonder Boy is one.
 *
 * THE CASE DECLARES THE CHIP'S PRIOR CONTENTS; THE MODEL NEVER INVENTS THEM. An RMW preserves
 * exactly the bits the game does NOT write — `ori.b #$3f,d1` on register 7 keeps the two port
 * DIRECTION bits, the floppy drive-select keeps port A's upper five — so the value the chip held on
 * entry steers the result and is an INPUT of the run, like a poked keystroke. Answering 0, or
 * replaying a ledger that is empty on the first read, would verify a reconstruction against a value
 * no real machine ever holds. So a register is readable only once it is KNOWN: declared by the case
 * (osh_psg_seed) or written earlier in the same run. A read of an unknown register is REFUSED —
 * g_psg_unseeded records which registers, and emu.run rejects the run and names them. */
static uint8_t  g_psg_file[OS_PSG_NREGS];   /* os.h owns the count, its mask, and the uint16_t check */
static uint16_t g_psg_known;       /* bit R set = register R's contents are known this run */
static uint8_t  g_psg_seed[OS_PSG_NREGS];   /* the contents the case declares each run STARTS from */
static uint16_t g_psg_seed_known;           /* ...and which registers it declared */
static uint16_t g_psg_unseeded;    /* registers this run read while UNKNOWN (see emu.run's cause) */
static uint32_t g_psg_no_select;   /* reads this run made before ANYTHING selected a register */

/* Which of the two PSG paths this run used. ONE chip, TWO modeled register files: the trap path's
 * lives in the image (os.h OS_PSG_REGS) and is fed by XBIOS Giaccess only; the direct path's is
 * g_psg_file above and is fed by $ff8802 writes only. Neither sees the other's stores, so a run
 * that uses BOTH would be served a read from a file it knows is stale — whichever way round. Rather
 * than answer from it, count the run unmodeled and let emu.run reject it with the diagnostic
 * osh_psg_mixed_paths backs. Joust reaches both (its sound driver calls Giaccess; its floppy
 * routine at image 0x1553c selects and rewrites PSG port A directly), so this is a live guard, not
 * a hypothetical one — and the seeded read model does not retire it: it gives the direct file
 * readable contents, which is a different question from the two files agreeing. */
static uint32_t g_psg_direct;          /* direct $ff8800/$ff8802 accesses this run (any width) */
static uint32_t g_psg_giaccess_calls;  /* XBIOS Giaccess traps served this run */
int osh_psg_mixed_paths(void) { return g_psg_direct && g_psg_giaccess_calls; }

/* Direct PSG accesses the model cannot serve at all (counted separately from g_psg_direct, which
 * merely arms the mixed-path guard). osh_run rejects the whole run on either, rather than let it be
 * verified against a fabricated value. Three kinds:
 *   - a read of the DATA port $ff8802. The chip reads back through the SELECT port; $ff8802 is
 *     write-only, and answering it would invent a port the hardware does not have. (A read of
 *     $ff8800 IS modeled, from g_psg_file above — but only for a register whose contents are known;
 *     an unknown one is refused through g_psg_unseeded, which is a different cause with a different
 *     remedy, so it is counted separately rather than folded in here.)
 *   - a SELECT of a register number outside 0..15. The YM2149 requires the upper nibble of the
 *     select byte to be zero; the ST's port is not a "the top bits are ignored" register but one
 *     whose behaviour with them set this does not model. Masking the value down (which this file
 *     used to do) would silently turn `move.b #$1e,$ff8800` into a select of register 14 here while
 *     the candidate's psg_port_write refuses the same call — so both sides refuse instead. No input
 *     binary writes one; the day one does it needs a model, not a mask.
 *   - ANY OTHER access to the chip's address block. Only the BYTE protocol on the canonical pair
 *     (select latch, then data) is modeled — not the odd-address decoding a `move.w #$0e00,$ff8800`
 *     relies on, and not the mirrors. Tallying these is also what stops such an idiom from slipping
 *     past the byte callback's equality test and silently DISARMING the mixed-path guard. No game
 *     does it (Joust's three direct accesses are byte-sized and port-aligned; BuggyBoy reaches the
 *     ports by `lea` + byte ops; Wonder Boy's 35 are all byte-sized on the canonical pair), so the
 *     guard no longer rests on that property of the inputs. */
static uint32_t g_psg_unmodeled;

/* --- optional AUDIO CAPTURE mode (off by default; osh_audio_capture turns it on) --------------
 * An asset-extraction tool drives a game's music replayer tick by tick and reads the register
 * stream back out of the PSG ledger above. It runs the ORIGINAL only — there is no candidate and no
 * diff — so it needs answers the differential will not give, and it gets them by RELAXING the
 * seeded model above rather than by keeping a second register file of its own. Three relaxations
 * and two extra bytes:
 *
 *   - an UNKNOWN register reads 0 instead of being refused. A capture cannot declare a seed per
 *     tick, and a refusal would end the extraction at the replayer's first mixer read-back; the
 *     0 is the mode's own fabrication, and is precisely why a differential may not run under it.
 *     A register the capture has already written reads back its own value, exactly as before.
 *   - an UNSELECTED latch likewise reads register 0 rather than refusing. Same argument, and the
 *     same fabrication: a replayer selects before it reads, so this only affects a capture whose
 *     first tick does not — but refusing there would be a refusal the extractor cannot answer.
 *   - the register file and the select latch PERSIST across osh_run calls. An extractor calls
 *     osh_run once per VBL tick, and tick N's read-back must see what tick N-1 wrote, exactly as the
 *     chip's own latch and registers survive a VBL. Off the mode both are reset per run from the
 *     case's seed, which is what makes a differential deterministic (see psg_enter_run).
 *   - $fffa01 bit 7 (MFP GPIP: the monitor-detect line) and $ff820a bit 1 (the shifter's sync mode).
 *     A replayer picks its tempo from those two. Both read 0 off-image, and 0/0 is the MONOCHROME
 *     profile — so a capture ticked at 50 Hz would run the mono tick-drop rate and render every
 *     song at the wrong tempo, silently. This mode reports the 50 Hz colour ST instead. Since
 *     Phase 7 it does that by INSTALLING A SEED over the seeded-hardware model below — the same
 *     door a case uses — rather than by keeping a switch of its own in the read callback, so the
 *     mode's answers and a case's travel one code path and cannot diverge (see hw_enter_run).
 *
 * WHY IT IS OPT-IN, AND MUST STAY SO. Every one of those answers is fabricated with respect to the
 * differential: it is the model's invention, not the game's data, so a reconstruction "verified"
 * against it would be verified against this file. That is the exact false green g_psg_unseeded and
 * emu.run's refusal exist to prevent. The mode is for a tool that runs the ORIGINAL only and wants
 * its register stream; it is never valid for a differential run, and the default is unchanged.
 *
 * osh_audio_reset() clears the register file AND the select latch, which is where a new capture
 * begins; nothing else does while the mode is on. Arming is a pure toggle, so re-arming mid-capture
 * keeps it (the cov_enable/cov_reset and prof_enable/prof_reset shape) — but arming from OFF clears,
 * because the chip state is shared with the differential's model (see osh_audio_capture). */
static int     g_audio_capture;

/* --- the SEEDED HARDWARE READ model (TRAP_MODEL.md, "Phase 7") -------------------------------
 * os.h names the modeled set (OS_HW_MFP_GPIP, OS_HW_SHIFTER_SYNC and the two video-counter
 * bytes OS_HW_SHIFTER_VCOUNT_MID/_LOW) and says why those four and not the rest of the I/O map.
 * This is the state behind it, and it is Phase 6's shape exactly: a file
 * of bytes, a mask saying which of them the CASE DECLARED, a per-run reinstall from the declared
 * seed, and an ordered ledger of every read the run made — because the byte a `btst #7,$fffa01`
 * answers steers a branch, so it is an INPUT of the run and the model must not invent it.
 *
 * ONE DIVERGENCE FROM PHASE 6, deliberate: an undeclared read is NOT refused here. It is served 0 —
 * the answer the shim gave before this model existed — and recorded in g_hw_unseeded, and the
 * refusal fires one level up, in harness.differential. emu.run is what drives a game's relocator,
 * its Copylock and its bootstrap, whose hardware reads are nobody's enumerated list; refusing there
 * would sink those runs for a false-green class that only exists where something is being VERIFIED.
 * TRAP_MODEL.md, "Phase 7", argues it at length. */
static uint8_t  g_hw_file[OS_HW_NSLOTS];   /* what a byte read of each modeled address answers */
static uint32_t g_hw_known;                /* bit S = slot S's contents were declared this run */
static uint8_t  g_hw_seed[OS_HW_NSLOTS];   /* the bytes the case declares each run STARTS from */
static uint32_t g_hw_seed_known;           /* ...and which slots it declared */
static uint32_t g_hw_unseeded;             /* slots this run read while UNDECLARED */
static uint32_t g_hw_written;              /* slots this run WROTE (see hw_note_write) */
static uint32_t g_hw_stale;                /* ...and then READ: the seed no longer describes them */
/* Slots read MORE THAN ONCE in one run while os.h calls them VOLATILE. A per-run constant answers
 * the second read with the first read's byte; the machine would not, so the case is verified
 * against a value the counter cannot have held twice. Recorded rather than refused here, exactly as
 * g_hw_unseeded is, because emu.run drives bootstraps nobody enumerates — harness.differential is
 * where it becomes a refusal. */
static uint32_t g_hw_reread;
static uint32_t g_hw_seen;                 /* slots read at least once this run, for the above */
/* Slots taken in by a wide (16/32-bit) read. Only a BYTE read of a modeled address is served; a
 * wider one takes in neighbouring MFP/shifter registers the model knows nothing about, so answering
 * it would fabricate them as 0. Recorded rather than served — under audio capture emu.run sinks the
 * run on it (an extractor has no second chance), and in a differential
 * harness._vet_hw_reads_are_declared does.
 *
 * A MASK, like the two above and for their reason: the refusal has to name the address the case
 * must do something about, and "you read one of these N wide" is a refusal a reader has to bisect. */
static uint32_t g_hw_wide;
/* The ordered READ stream, slot + value per entry, compared against the candidate's (src/hw.c).
 * Reads only: a WRITE to one of these addresses is dropped, not modeled — see hw_note_write. */
static uint8_t  g_hw_log_slot[OS_HW_LOG_MAX];
static uint8_t  g_hw_log_val[OS_HW_LOG_MAX];
static uint32_t g_hw_log_n;
static uint32_t g_hw_dropped;              /* reads past the cap: never silently truncated */

/* The machine profile the AUDIO-CAPTURE mode declares, and the ONLY bits of it that are modeled: a
 * 50 Hz colour ST, the machine these games were written for. Mono would be GPIP bit 7 clear and
 * 60 Hz sync bit 1 clear — which is what an undeclared read's 0 already says, hence the mode.
 *
 * GPIP bits 4 and 5 are the ACIA (keyboard/MIDI) and FDC/HDC interrupt lines. They are ACTIVE LOW,
 * so IDLE is 1: serving bit 7 alone would report both devices as interrupting, which is a state no
 * quiescent machine is in. Every OTHER bit of the byte is a fabricated 0 (the parallel-port busy and
 * ring-indicator lines, the DMA/blitter line on an STE) — this is a two-bit answer for a tempo
 * selector, not a machine model.
 *
 * It is a SEED over the model above, not a switch beside it: hw_enter_run installs it exactly where
 * it installs a case's, so "what the mode serves" and "what a case that declared the same bytes
 * serves" are the same code answering the same file. osh_hw_capture_profile() exports it so a test
 * can pin those two against each other instead of against a copy of the constants. */
#define MFP_GPIP_COLOUR         0x80       /* bit 7 = monitor detect; SET = colour monitor */
#define MFP_GPIP_IRQ_LINES_IDLE 0x30       /* bits 5/4 = FDC + ACIA interrupts, active low: idle */
#define SHIFTER_SYNC_50HZ       0x02       /* bit 1 SET = 50 Hz */
static const uint8_t g_hw_capture_profile[OS_HW_NSLOTS] = {
    [OS_HW_SLOT_MFP_GPIP]     = MFP_GPIP_COLOUR | MFP_GPIP_IRQ_LINES_IDLE,
    [OS_HW_SLOT_SHIFTER_SYNC] = SHIFTER_SYNC_50HZ,
};
/* Which slots the profile DECLARES — named one by one rather than "all of them". The array above is
 * a designated initializer, so a slot added to os.h's table gets a silent 0 here; declaring it too
 * would mark that fabricated 0 as a real answer, which is the mono-profile failure the mode exists
 * to close, one address over. Spelled this way, adding a slot leaves it UNDECLARED under capture —
 * which reads 0 exactly as before and lands in g_hw_unseeded, where it is visible. */
#define HW_CAPTURE_PROFILE_KNOWN \
    ((1u << OS_HW_SLOT_MFP_GPIP) | (1u << OS_HW_SLOT_SHIFTER_SYNC))

/* Clear the modeled chip state — where a new capture begins.
 *
 * The SELECT LATCH goes with the register file, and that is not cosmetic: it is the other half of
 * the chip state a capture carries across runs, so a reset that cleared the file and left the latch
 * would start the next capture selecting the previous one's last register. That leak was measured —
 * select register 10, arm, write the data port bare, and the byte landed in register 10 of a capture
 * that had never named it. Every clear takes both. */
void osh_audio_reset(void) {
    for (int i = 0; i < OS_PSG_NREGS; i++) g_psg_file[i] = 0;
    g_psg_known = 0;                 /* the three move together: a cleared chip knows nothing, */
    g_psg_latch = 0;                 /* and has no register selected — 0 is a placeholder, not a */
    g_psg_latch_known = 0;           /* claim, which is exactly what g_psg_latch_known records */
}

/* Arm or disarm audio capture.
 *
 * Re-arming an ALREADY-ARMED capture is a no-op: an extractor that arms defensively before each
 * tick, or a caller that nests the mode, must not silently wipe the capture it is in the middle of
 * (the cov_enable/cov_reset shape). osh_audio_reset() is what clears the file mid-capture.
 *
 * But arming from OFF starts a fresh one, because the chip state is now SHARED with the
 * differential's seeded model: a run made while the mode was off leaves its own registers AND its
 * own select latch behind, so without this a capture armed bare would inherit whatever the last
 * differential left — under `pytest -n auto`, an unrelated case's mixer and an unrelated case's
 * selected register, unreproducibly. (The latch half was measured, not theorised: select register 10
 * in a run, arm, write the data port bare, and the byte landed in 10.) Every caller goes through
 * emu.audio_capturing(), which resets anyway; this makes structural what was otherwise a
 * convention. */
void osh_audio_capture(int on) {
    if (on && !g_audio_capture) osh_audio_reset();
    g_audio_capture = on;
}
/* Is the mode armed? The differential must never run under it (every served read is fabricated with
 * respect to one), and harness.differential vets this rather than trusting the caller. */
int  osh_audio_capture_on(void) { return g_audio_capture; }

/* ---- the seeded-hardware model's ABI (see g_hw_file above; emu.py binds every one) ---- */
/* Declare the bytes every FOLLOWING run starts from. `known` is a bitmask of the SLOTS `values`
 * declares (os.h's OS_HW_SLOT_*); a slot outside it stays undeclared, and a read of it is served 0
 * and recorded in g_hw_unseeded. Stored rather than installed, for osh_psg_seed's reason: a seed set
 * between runs cannot reach a run already in flight, and two runs given the same seed start
 * identical whatever ran between them. */
void osh_hw_seed(const uint8_t *values, uint32_t known) {
    g_hw_seed_known = known;
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        g_hw_seed[slot] = (known & (1u << slot)) ? values[slot] : 0;   /* read only where declared */
}
const uint8_t  *osh_hw_file(void)      { return g_hw_file; }
uint32_t        osh_hw_known(void)     { return g_hw_known; }
/* Slots this run read while UNDECLARED — a refusal mask, not a count, so harness.differential can
 * name the addresses a case must seed. NOT raised by emu.run: see g_hw_file's header. */
uint32_t        osh_hw_unseeded(void)  { return g_hw_unseeded; }
/* Slots this run WROTE and then READ. The seed declares the byte the chip held ON ENTRY, and the
 * run's own store has replaced it — so the served byte contradicts an instruction that ran. */
uint32_t        osh_hw_stale(void)     { return g_hw_stale; }
/* Slots a wide read took in — a mask, so the refusal names the address rather than the whole set. */
uint32_t        osh_hw_wide(void)      { return g_hw_wide; }
uint32_t        osh_hw_count(void)     { return g_hw_log_n; }
const uint8_t  *osh_hw_log_slots(void) { return g_hw_log_slot; }
const uint8_t  *osh_hw_log_vals(void)  { return g_hw_log_val; }
uint32_t        osh_hw_dropped(void)   { return g_hw_dropped; }
/* The modeled set itself, so Python names the addresses from the .so it actually loaded rather than
 * from a second copy of os.h's table (osh_psg_nregs's argument). */
uint32_t        osh_hw_nslots(void)    { return OS_HW_NSLOTS; }
uint32_t        osh_hw_reread(void)    { return g_hw_reread; }
uint32_t        osh_hw_volatile(void)  { return os_hw_volatile_slots(); }
/* The capture profile's KNOWN mask, exported for the same reason the profile itself is: a Python
 * caller that rebuilt "which slots the mode declares" from the table's length would report the
 * fabricated 0 of every slot the mask withholds as a declared byte. */
uint32_t        osh_hw_capture_profile_known(void) { return HW_CAPTURE_PROFILE_KNOWN; }
const uint32_t *osh_hw_addr_table(void) { return os_hw_addrs(); }
/* The bytes the audio-capture mode declares, by slot — what a test pins the mode against. */
const uint8_t  *osh_hw_capture_profile(void) { return g_hw_capture_profile; }

/* Declare the register contents every FOLLOWING run starts from — the case's seed, and the only way
 * a register becomes readable before this run writes it. `known` is a bitmask of the registers
 * `values` declares; a register outside it stays unknown and reading it refuses the run.
 *
 * The seed is stored rather than installed here: osh_run copies it into the live file, so a seed set
 * between runs cannot reach a run already in flight, and two runs given the same seed start
 * identical whatever ran between them (the ENTRY_SR determinism argument). */
void osh_psg_seed(const uint8_t *values, uint32_t known) {
    g_psg_seed_known = (uint16_t)known;
    for (int i = 0; i < OS_PSG_NREGS; i++)
        g_psg_seed[i] = (known & (1u << i)) ? values[i] : 0;   /* `values` is read only where declared */
}
/* The modeled register file after the last run, and which of it is known — the differential's
 * off-image PSG state surface (harness.differential compares both against the candidate's). Under
 * audio capture the same file is the extractor's view of the chip. */
const uint8_t *osh_psg_file(void)  { return g_psg_file; }
uint32_t       osh_psg_known(void) { return g_psg_known; }
/* Registers this run READ while their contents were unknown — a refusal mask, not a count: emu.run
 * names the registers a case must seed, which is the whole remedy. */
uint32_t       osh_psg_unseeded(void) { return g_psg_unseeded; }
/* Reads this run made before any $ff8800 write selected a register (see g_psg_latch_known). Its own
 * cause because its remedy is its own: the case is missing a SELECT, not a seed. */
uint32_t       osh_psg_no_select(void) { return g_psg_no_select; }
/* Direct-path accesses this run made, READS INCLUDED. It is what "did this run use the chip?" means
 * — a run that only READS writes no register, so the ledger's write projection cannot answer it —
 * so harness.differential keys on this when deciding whether a candidate that exports no PSG ABI may
 * be served, and emu.run reports it as the witness the seed-door guard tests. */
uint32_t       osh_psg_direct(void) { return g_psg_direct; }
/* XBIOS Giaccess traps this run served — the OTHER door to the same chip. harness.differential reads
 * it to catch a case that seeded the direct path while the routine drove the trap path (see
 * _vet_psg_seed_reaches_the_path); osh_psg_mixed_paths above is the same pair, ANDed. */
uint32_t       osh_psg_giaccess(void) { return g_psg_giaccess_calls; }
/* Pins the C array's size for Python, so emu.py sizes its cast from the .so it actually loaded
 * rather than keeping a second copy of the count. */
uint32_t       osh_psg_nregs(void) { return OS_PSG_NREGS; }

/* Does an access of `n` bytes at `a` fall in the YM2149's address block? */
static int psg_block_touched(uint32_t a, uint32_t n) {
    uint32_t lo = a & BUS_ADDR_MASK;               /* the 68000 aliases $ffff88xx to $ff88xx */
    return lo < PSG_BLOCK_END && lo + n > OS_PSG_PORT_SELECT;
}

/* Tally a PSG access the model cannot serve (see g_psg_unmodeled). Callers reach this only after
 * the in-image fast path has missed, so it costs nothing on a normal access. */
static void psg_note_unmodeled(uint32_t a, uint32_t n) {
    if (!psg_block_touched(a, n)) return;
    g_psg_direct++;                                /* it is still a use of the direct path */
    g_psg_unmodeled++;
}

/* Record a WIDE read that took in a modeled hardware byte (see g_hw_wide). Unlike the byte path it
 * serves nothing: the caller returns its ordinary off-image 0, and the mask is what makes the
 * fabrication visible to emu.run (under capture) and to harness._vet_hw_reads_are_declared (in a
 * differential). */
static void hw_note_wide_read(uint32_t a, uint32_t n) {
    g_hw_wide |= os_hw_slots_touched(a & BUS_ADDR_MASK, n);   /* the 68000 aliases $fffffa01 here */
}

/* Note a write of `n` bytes at `a` that landed on a modeled hardware byte.
 *
 * The write itself is DROPPED, exactly as every other hardware write off the PSG ports is dropped —
 * Phase 7 models what these addresses ANSWER, not what storing to them does, and a game's
 * `move.b #2,$ff820a` has no readable effect this model claims to reproduce. What is recorded is
 * that it happened, because a later READ of the same address is then served the case's seed — the
 * byte the chip held on ENTRY — while an instruction of this very run has replaced it. That
 * combination is refused rather than served (g_hw_stale); a write nothing reads back is the
 * ordinary invisible hardware write it has always been. */
static void hw_note_write(uint32_t a, uint32_t n) {
    g_hw_written |= os_hw_slots_touched(a & BUS_ADDR_MASK, n);
}

/* Append one read to the ordered ledger. Overflow is counted, never silent: two ledgers that
 * diverge only past the cap would truncate to the same stream and compare equal. */
static void hw_log(int slot, uint8_t value) {
    if (g_hw_log_n >= OS_HW_LOG_MAX) {
        g_hw_dropped++;
        return;
    }
    g_hw_log_slot[g_hw_log_n] = (uint8_t)slot;
    g_hw_log_val[g_hw_log_n] = value;
    g_hw_log_n++;
}

/* What a BYTE read of a modeled hardware address answers: the byte the case declared.
 *
 * An UNDECLARED slot answers 0 — the same 0 every unmodeled off-image read has always answered, so
 * a run that was green before this model existed is green after it — and is recorded in
 * g_hw_unseeded so that a differential can refuse it. The read is ledgered EITHER WAY: it happened,
 * the candidate's side ledgers its own refused read too, and a stream missing it on one side would
 * diverge for the wrong reason. */
static unsigned int hw_read(int slot) {
    unsigned int served = 0;
    if (g_hw_known & (1u << slot)) served = g_hw_file[slot];
    else                           g_hw_unseeded |= 1u << slot;
    if (g_hw_written & (1u << slot)) g_hw_stale |= 1u << slot;
    /* The SECOND read of a volatile slot, tallied on the read that repeats rather than on the one
     * that opened it — so the mask names the slot a case must do something about. */
    if ((g_hw_seen & (1u << slot)) && (os_hw_volatile_slots() & (1u << slot)))
        g_hw_reread |= 1u << slot;
    g_hw_seen |= 1u << slot;
    hw_log(slot, (uint8_t)served);
    return served;
}

/* Append one direct-path event to the ordered ledger. Reads are recorded alongside writes so that
 * "this run read register 7" is a comparable fact: a reconstruction that reads the WRONG register
 * still writes the right one, leaving the write stream AND the register file identical on both
 * sides. Overflow is counted, never silent — the ledger is also the capture mode's data feed. */
static void psg_log(uint8_t kind, uint8_t reg, uint8_t value) {
    if (g_psgn >= OS_PSG_LOG_MAX) {
        g_psg_dropped++;                           /* see g_psg_dropped: never silently */
        return;
    }
    g_psg_kind[g_psgn] = kind;
    g_psg_reg[g_psgn] = reg;
    g_psg_val[g_psgn] = value;
    g_psgn++;
}

/* What a byte read of $ff8800 answers: the contents of the currently latched register.
 *
 * It is always a USE of the direct path, served or not, so it arms the mixed-path guard exactly as a
 * write does — the file it answers from never saw a Giaccess store. Two things must be known for an
 * answer to exist: WHICH register (something must have selected one this capture/run — see
 * g_psg_latch_known) and WHAT IT HOLDS (seeded by the case or written earlier). Either missing is
 * refused, in its own tally, because the remedies differ: add the select, or add the seed.
 *
 * Under audio capture both refusals relax — a capture cannot declare a seed per tick, and a refusal
 * would end the extraction at the replayer's first read-back — and the answer becomes the file's
 * byte, 0 where nothing wrote it. That is the mode's own fabrication, and why no differential may
 * run under it. */
static unsigned int psg_read_back(void) {
    g_psg_direct++;
    unsigned int served = 0;
    if (g_audio_capture) {
        /* Both refusals relaxed at once: an unselected latch reads register 0 (its placeholder) and
         * an unknown register reads whatever the file holds, which is 0 after a clear. Exactly the
         * answer this gave before the seeded model existed, so a capture is unchanged by it. */
        served = g_psg_file[g_psg_latch];
    } else if (!g_psg_latch_known) {
        g_psg_no_select++;                         /* refused; emu.run rejects the whole run */
    } else if (!(g_psg_known & (uint16_t)(1u << g_psg_latch))) {
        g_psg_unseeded |= (uint16_t)(1u << g_psg_latch);   /* likewise refused, other remedy */
    } else {
        served = g_psg_file[g_psg_latch];
    }
    psg_log(OS_PSG_EVENT_READ, g_psg_latch, (uint8_t)served);
    return served;
}

/* --- memory callbacks: big-endian, bounds-checked to the image --- */
unsigned int m68k_read_memory_8(unsigned int a) {
    if (a < g_size) return g_mem[a];
    uint32_t lo = a & BUS_ADDR_MASK;               /* the 68000 aliases $ffff88xx to $ff88xx */
    if (lo == IKBD_STATUS) return IKBD_TX_RDY;
    if (lo == OS_PSG_PORT_SELECT) return psg_read_back();
    /* The seeded-hardware model (Phase 7). Ahead of the audio-capture mode, which no longer has a
     * switch of its own here: it arms this same model with a seed (see hw_enter_run). */
    int hw_slot = os_hw_slot(lo);
    if (hw_slot >= 0) return hw_read(hw_slot);
    psg_note_unmodeled(a, 1);
    return 0;                                      /* off-image, like any unmapped address */
}
unsigned int m68k_read_memory_16(unsigned int a) {
    if (a + 1 < g_size) return (unsigned)(g_mem[a] << 8 | g_mem[a + 1]);
    psg_note_unmodeled(a, 2);
    hw_note_wide_read(a, 2);
    return 0;
}
unsigned int m68k_read_memory_32(unsigned int a) {
    if (a + 3 >= g_size) { psg_note_unmodeled(a, 4); hw_note_wide_read(a, 4); return 0; }
    return (unsigned)(g_mem[a] << 24 | g_mem[a + 1] << 16 | g_mem[a + 2] << 8 | g_mem[a + 3]);
}

static void logw(uint32_t a) { if (g_wn < MAX_WRITES) g_waddr[g_wn++] = a; }

/* --- XBIOS Dosound (fn 0x20) side-effect ledger -------------------------------------------
 * Dosound hands the YM2149 a command list via A0; that pointer touches no RAM, so a wrong or
 * missing list is invisible to the image diff even when the call runs. Record each Dosound's
 * list pointer (the runtime A0 == a Ghidra image address) in an ordered ledger, reset per run
 * like the PSG tap. harness.differential compares it against the candidate's g_dosound ledger,
 * making the off-image A0 argument diff-verifiable (improvement #2). The cap is os.h's
 * OS_DOSOUND_LOG_MAX — the same one the candidate's ledger uses, so both truncate identically. */
static uint32_t g_dosound_arg[OS_DOSOUND_LOG_MAX];
static uint32_t g_dosound_n;
uint32_t        osh_dosound_count(void) { return g_dosound_n; }
const uint32_t *osh_dosound_args(void)  { return g_dosound_arg; }

void m68k_write_memory_8(unsigned int a, unsigned int v) {
    switch (a & BUS_ADDR_MASK) {                   /* mask to the 68000's 24-bit address bus */
        case OS_PSG_PORT_SELECT:
            g_psg_direct++;
            /* Not masked to four bits: a select with a non-zero upper nibble is refused, on both
             * sides, rather than quietly turned into a register this model does have (g_psg_unmodeled
             * above says why). The latch is left as it was, so a read that follows is refused too —
             * two causes for one mistake, which is the right count. */
            if ((unsigned)v > OS_PSG_REG_SEL) { g_psg_unmodeled++; return; }
            g_psg_latch = (uint8_t)v;
            g_psg_latch_known = 1;
            return;
        case OS_PSG_PORT_DATA:
            g_psg_direct++;                            /* see the mixed-path guard in osh_run */
            /* Both surfaces, from the one write: the file is what a read-back answers from (so an
             * RMW sees its own store), the ledger is the ORDER the chip was accessed in. */
            g_psg_file[g_psg_latch] = (uint8_t)v;
            g_psg_known |= (uint16_t)(1u << g_psg_latch);
            psg_log(OS_PSG_EVENT_WRITE, g_psg_latch, (uint8_t)v);
            return;
    }
    if (a < g_size) { g_mem[a] = (uint8_t)v; logw(a); return; }
    psg_note_unmodeled(a, 1);   /* the odd aliases $ff8801/$ff8803, whose decoding is not modeled */
    hw_note_write(a, 1);        /* dropped like any hardware write, but it makes a seed stale */
}
void m68k_write_memory_16(unsigned int a, unsigned int v) {
    if (a + 1 < g_size) { g_mem[a] = (uint8_t)(v >> 8); g_mem[a + 1] = (uint8_t)v; logw(a); logw(a + 1); return; }
    psg_note_unmodeled(a, 2);                      /* only the byte PSG protocol is modeled */
    hw_note_write(a, 2);
}
void m68k_write_memory_32(unsigned int a, unsigned int v) {
    if (a + 3 >= g_size) { psg_note_unmodeled(a, 4); hw_note_write(a, 4); return; }
    g_mem[a] = (uint8_t)(v >> 24); g_mem[a + 1] = (uint8_t)(v >> 16);
    g_mem[a + 2] = (uint8_t)(v >> 8); g_mem[a + 3] = (uint8_t)v;
    logw(a); logw(a + 1); logw(a + 2); logw(a + 3);
}

/* --- TOS trap dispatch (GEMDOS #1 / BIOS #13 / XBIOS #14, GEM #2) ------------------
 * Real code enters the OS via `trap #N`. We point each trap vector at a magic PC the run
 * loop detects; on a hit we read the 68000 exception frame (SR word + return PC long) plus
 * the function number/args from the caller's stack, apply a deterministic effect (os.h),
 * set D0, pop the frame, and resume at the caller. Vectors are installed transiently and
 * restored after the run, so the final image matches a reconstruction that never traps. */
#define TRAP_VEC_GEMDOS 0x84    /* trap #1  */
#define TRAP_VEC_GEM    0x88    /* trap #2  (AES/VDI — modeled via os_gem_trap) */
#define TRAP_VEC_BIOS   0xb4    /* trap #13 */
#define TRAP_VEC_XBIOS  0xb8    /* trap #14 */
#define MAGIC_GEMDOS 0x120      /* unused vector-page slots, even, never real code (>= 0x10000) */
#define MAGIC_GEM    0x124
#define MAGIC_BIOS   0x128
#define MAGIC_XBIOS  0x12c

/* The status register every run starts from: supervisor, interrupt mask 7, condition codes clear.
 *
 * IT IS FORCED, NOT INHERITED FROM THE RESET. A 68000 reset does not clear the condition codes, and
 * Musashi is faithful about it: m68k_pulse_reset() touches T, the interrupt mask and S, and leaves
 * FLAG_X/N/Z/V/C exactly as the PREVIOUS run left them. Without the force a run inherits the last
 * one's CCR, and any routine that reads a condition code ON ENTRY — `abcd`/`sbcd` fold in X, `addx`
 * and `roxl` likewise — answers differently depending on what ran before it in the same process.
 *
 * WHY THIS VALUE: the requirement is DETERMINISM — two identical runs must give identical answers
 * whatever ran before them — and $2700 is the kit's convention for meeting it: the S bit and IPL the
 * reset itself selects, with the CCR cleared. It is NOT a claim about the SR any game's own boot
 * code leaves behind; nothing here reads one. A caller cannot ask for another entry condition either
 * (emu.run has no entry-CCR parameter), so the entry CCR is guaranteed clear, and an original that
 * the GAME reaches with X set is unreachable from a case.
 *
 * Pinned behaviourally on both sides, the same split as the M68K_EMULATE_TRACE #error above:
 * kit-side by tools/recreate_kit/test/test_entry_state.py, whose probe runs one `abcd` three times
 * in one process; game-side by projects/wonderboy/recreate/test/test_hud.py::
 * test_the_oracle_enters_every_run_with_the_condition_codes_clear, over the packed-BCD accumulators
 * that surfaced the defect. */
#define ENTRY_SR 0x2700

/* The CPU state EVERY run begins from. Both entry points go through this one place so that the reset
 * and the ENTRY_SR force cannot drift apart — osh_run_bench once reset without forcing, and so
 * inherited the condition codes of whatever had run before it. */
/* Put the modeled YM2149 back to this run's declared entry state, and clear its per-run tallies.
 *
 * It lives with the CPU reset, and is reached by osh_run_bench as well as osh_run, because "the
 * chip's contents at entry" is exactly as much a per-run input as the entry SR: a bench issued
 * after a seeded differential must not read that case's registers, and its own PSG traffic must not
 * be attributed to the run before it.
 *
 * Off the audio-capture mode the file and the latch are rebuilt from the case's seed — a run must
 * start from the contents its own case declares and nothing else, which is the same determinism
 * defect ENTRY_SR closed for the condition codes, and under `pytest -n auto` "whatever ran before"
 * is not stable. Under the mode the capture spans runs BY CONTRACT (an extractor calls osh_run once
 * per VBL tick and a tick reads back what an earlier tick wrote to a register it selected, exactly
 * as the chip's own latch and registers survive a VBL), so the file and latch are left alone there;
 * osh_audio_reset() is what clears them. The ledger and the refusal tallies are per-run in BOTH
 * modes — an extractor reads one tick's register stream at a time. */
static void psg_enter_run(void) {
    if (!g_audio_capture) {
        for (int i = 0; i < OS_PSG_NREGS; i++) g_psg_file[i] = g_psg_seed[i];
        g_psg_known = g_psg_seed_known;
        g_psg_latch = 0;
        g_psg_latch_known = 0;
    }
    g_psgn = 0;                       /* the ledger is this run's accesses only... */
    g_psg_dropped = 0;                /* ...and so is its overflow tally */
    g_psg_unseeded = 0;               /* the three refusal tallies are per-run in either mode */
    g_psg_no_select = 0;
    g_psg_unmodeled = 0;
    g_psg_direct = 0;                 /* ...as are the two the mixed-path guard is built from */
    g_psg_giaccess_calls = 0;
}

/* Put the modeled HARDWARE BYTES back to this run's declared entry state, and clear the per-run
 * ledger and tallies. Sibling of psg_enter_run, reached from the same place and for the same reason:
 * what `btst #7,$fffa01` answers is as much a per-run input as the chip's register contents, so a
 * run must start from the bytes its OWN case declared and never from the previous run's.
 *
 * THE AUDIO-CAPTURE FOLD. Under the mode the installed seed is the 50 Hz colour-ST profile instead
 * of the case's — one code path, so "what the mode serves" is by construction "what a case that
 * declared those bytes serves", and the mode cannot drift away from the model it relaxes. It is
 * installed per RUN rather than at arming, which is what stops it leaking: disarm the mode and the
 * very next run reinstalls the case's seed, with no reset call required. (emu.run refuses an
 * explicit hw_seed under the mode for the same reason it refuses a psg_seed: the mode's profile
 * would silently win.) Unlike the PSG file this one does NOT span runs — a machine's monitor and
 * sync mode are constants of the capture, not state a tick accumulates. */
static void hw_enter_run(void) {
    const uint8_t *seed = g_audio_capture ? g_hw_capture_profile : g_hw_seed;
    uint32_t known = g_audio_capture ? HW_CAPTURE_PROFILE_KNOWN : g_hw_seed_known;
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        g_hw_file[slot] = (known & (1u << slot)) ? seed[slot] : 0;
    g_hw_known = known;
    g_hw_unseeded = 0;
    g_hw_written = 0;
    g_hw_stale = 0;
    g_hw_reread = 0;
    g_hw_seen = 0;
    g_hw_wide = 0;
    g_hw_log_n = 0;
    g_hw_dropped = 0;
}

static void enter_from_reset(void) {
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_pulse_reset();
    m68k_set_reg(M68K_REG_SR, ENTRY_SR);
    psg_enter_run();
    hw_enter_run();
    sched_enter_run();
}

static uint32_t g_heap;         /* Malloc bump pointer */
static uint32_t g_malloc_n;     /* GEMDOS Malloc calls serviced this run (see osh_malloc_count) */
static uint32_t g_unmodeled;    /* count of traps whose real effect we do NOT model (fabricated D0) */
/* Traps serviced this run that REACH the harness-poked model state (see osh_poked_input_calls). The
 * six the project.toml waiver `tos_poked_input_unused` names: Bconstat, Bconin, Crawio, Random,
 * Giaccess, Kbdvbase. Reaching it, not reading it: a Giaccess WRITE stores into the register file
 * and Bconin clears the pending flag, and under the overlap those are writes over the game's own
 * code — worse than a read, not better. Sibling of g_malloc_n: it is the per-run witness that lets
 * emu.run() re-test a layout waiver's claim about the GAME instead of trusting it once at import. */
static uint32_t g_poked_input_calls;
static uint32_t g_min_a7;       /* lowest A7 (deepest stack pointer) reached this run */
static uint32_t g_ninsns;       /* instructions executed in the last osh_run (perf profiling) */
static uint64_t g_ncycles;      /* 68000 clock cycles executed in the last osh_run (perf profiling) */

/* Service the trap the CPU jumped to (vec = 1/2/13/14). Reads the exception frame at A7,
 * services the OS call, and returns control to the caller with D0 set. Calls we faithfully
 * model set `modeled`; anything else (an unmodeled GEM opcode, a non-console BIOS device, an
 * unstaged file, an unknown fn) is counted in g_unmodeled so the run can be rejected rather
 * than trusted against a fabricated result. */
static void handle_trap(int vec) {
    uint32_t sp     = m68k_get_reg(0, M68K_REG_A7);
    uint32_t sr     = m68k_read_memory_16(sp);       /* pushed status register */
    uint32_t retpc  = m68k_read_memory_32(sp + 2);   /* return address (past the trap) */
    uint32_t caller = sp + 6;                         /* caller's stack: fn word, then args */
    uint16_t fn     = (uint16_t)m68k_read_memory_16(caller);
    uint32_t arg1   = caller + 2;
    uint32_t d0 = 0;                                  /* default: success / no image effect */
    int modeled = 1;

    if (vec == 14 && fn == 0x26) {                    /* XBIOS Supexec: run the routine nested */
        uint32_t routine = m68k_read_memory_32(arg1); /* pea'd routine address */
        m68k_write_memory_32(caller - 4, retpc);      /* routine's rts returns to the caller */
        m68k_set_reg(M68K_REG_SR, sr);                /* restore SR first (may reselect SSP) */
        m68k_set_reg(M68K_REG_A7, caller - 4);
        m68k_set_reg(M68K_REG_PC, routine);           /* D0 (Supexec's result) is set by the routine */
        return;
    }

    if (vec == 1) {                                   /* GEMDOS */
        switch (fn) {
        case 0x48:                                    /* Malloc: bump-allocate a block */
            /* Count the CALL, not the bump: a zero/rounds-to-zero size (Malloc(-1), the "largest
             * free block?" query) is still fully serviced — it returns OS_HEAP_BASE — yet leaves
             * g_heap where it was. See osh_malloc_count. */
            g_malloc_n++;
            d0 = g_heap; g_heap += (m68k_read_memory_32(arg1) + 1u) & ~1u; break;
        case 0x20:                                    /* Super(stack): supervisor-mode token model */
            modeled = os_super(m68k_read_memory_32(arg1), &d0);
            break;
        case 0x3c: {                                  /* Fcreate(fname, attr) -> handle */
            int32_t h = os_fcreate(g_mem, m68k_read_memory_32(caller + 2));
            if (h < 0) modeled = 0; else d0 = (uint32_t)h;
            break;
        }
        case 0x3d: {                                  /* Fopen(fname, mode) -> handle */
            int32_t h = os_fopen(g_mem, m68k_read_memory_32(caller + 2));
            if (h < 0) modeled = 0; else d0 = (uint32_t)h;
            break;
        }
        case 0x3f: {                                  /* Fread(handle, count, buf) -> bytes read */
            int32_t nread = os_fread(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                                     m68k_read_memory_32(caller + 4),
                                     m68k_read_memory_32(caller + 8));
            if (nread < 0) modeled = 0; else d0 = (uint32_t)nread;
            break;
        }
        case 0x40: {                                  /* Fwrite(handle, count, buf) -> bytes written */
            int32_t nwrote = os_fwrite(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                                       m68k_read_memory_32(caller + 4),
                                       m68k_read_memory_32(caller + 8));
            if (nwrote < 0) modeled = 0; else d0 = (uint32_t)nwrote;
            break;
        }
        case 0x3e:                                    /* Fclose(handle) */
            if (os_fclose(g_mem, (uint16_t)m68k_read_memory_16(caller + 2)) < 0) modeled = 0;
            break;
        case 0x49: case 0x4a:                         /* Mfree / Mshrink -> success */
        case 0x02: case 0x09: break;                  /* Cconout / Cconws -> no image effect */
        case 0x06: {                                  /* Crawio(w): raw console I/O, either way */
            uint16_t w = (uint16_t)m68k_read_memory_16(caller + 2);
            /* Only the READ direction looks at the poked console state; the write direction is a
             * character bound for the screen and touches nothing (os.h). Tallying it too would
             * redden a legitimate run for printing a character. */
            if (w == OS_CRAWIO_READ) g_poked_input_calls++;
            d0 = os_crawio(g_mem, w);
            break;
        }
        default: modeled = 0; break;                  /* Pterm, Dgetdrv, Pexec, unknown */
        }
    } else if (vec == 14) {                           /* XBIOS */
        switch (fn) {
        case 0x02: case 0x03: d0 = OS_SCREEN_BASE; break;   /* Physbase / Logbase */
        /* Kbdvbase hands the program a POINTER to poked state rather than reading it, but the claim
         * the tally serves is the same one: nothing in the game may reach that block. */
        case 0x22: g_poked_input_calls++; d0 = OS_KBDVBASE; break;   /* -> in-image KBDVBASE struct */
        case 0x11:                                    /* Random -> the harness-poked 24-bit value */
            g_poked_input_calls++;
            d0 = os_random(g_mem);
            break;
        case 0x1c:                                    /* Giaccess(data, reg): YM2149 read/write */
            g_psg_giaccess_calls++;
            g_poked_input_calls++;
            d0 = os_giaccess(g_mem, (uint16_t)m68k_read_memory_16(caller + 2),
                             (uint16_t)m68k_read_memory_16(caller + 4));
            break;
        case 0x04:                                    /* Getrez -> low-res */
        case 0x05: case 0x06: case 0x07:              /* Setscreen / Setpalette / Setcolor */
        case 0x19:                                    /* Ikbdws: serial write to the IKBD, no image effect */
            break;
        case 0x20:                                    /* Dosound: writes the YM2149, no image effect */
            if (g_dosound_n < OS_DOSOUND_LOG_MAX)    /* log A0 (the command-list pointer) into the ledger */
                g_dosound_arg[g_dosound_n++] = m68k_read_memory_32(arg1);
            break;
        case 0x25: break;                             /* Vsync: waits for the VBL, no image effect */
        default: modeled = 0; break;                  /* unknown */
        }
    } else if (vec == 2) {                            /* GEM: AES/VDI parameter-block calls */
        uint32_t reg_d0 = m68k_get_reg(0, M68K_REG_D0);   /* subsystem: AES 0xc8 / VDI 0x73 */
        uint32_t reg_d1 = m68k_get_reg(0, M68K_REG_D1);   /* -> parameter block */
        modeled = os_gem_trap(g_mem, reg_d0, reg_d1);     /* results land in the param block */
    } else if (vec == 13) {                           /* BIOS: console input only (os.h) */
        uint16_t dev = (uint16_t)m68k_read_memory_16(caller + 2);
        switch (fn) {
        case 0x01: g_poked_input_calls++; modeled = os_bconstat(g_mem, dev, &d0); break;  /* Bconstat */
        case 0x02: g_poked_input_calls++; modeled = os_bconin(g_mem, dev, &d0); break;    /* Bconin */
        default: modeled = 0; break;                  /* Bconout, Setexc, Kbshift, unknown */
        }
    } else {
        modeled = 0;
    }
    if (!modeled) g_unmodeled++;

    m68k_set_reg(M68K_REG_SR, sr);                    /* restore SR first (may reselect SSP) */
    m68k_set_reg(M68K_REG_A7, caller);                /* then pop the 6-byte exception frame */
    m68k_set_reg(M68K_REG_PC, retpc);
    m68k_set_reg(M68K_REG_D0, d0);
}

/* What a run REPORTS BACK: D0..D7 at out_regs[0..7], then A0..A6 at out_regs[8..14]. A caller must
 * size its buffer to OSH_OUT_REGS; nothing past it is written.
 *
 * A7 IS DELIBERATELY NOT REPORTED. It is not the function's register but the HARNESS's: osh_run
 * forces it to `sp` on entry and the run's own rts pops the sentinel frame back off it, so what it
 * holds at the end describes the frame the harness built, not anything the function computed. The
 * one fact about it a case can use — how deep the run pushed — is osh_min_a7(), which the harness
 * already vets its diff exclude bands against. Reporting it as if it were an output would invite a
 * case to assert the harness's own convention (STACK_TOP + 4) and call it verified.
 *
 * The set is the full `movem` register set for a reason: a routine whose outputs live in registers
 * the oracle does not report cannot be pinned by a differential at all, only by whatever memory it
 * happens to touch. See TRAP_MODEL.md, "What a run reports back". */
#define OSH_OUT_DREGS 8                              /* D0..D7 */
#define OSH_OUT_AREGS 7                              /* A0..A6 — A7 excluded, see above */
#define OSH_OUT_REGS  (OSH_OUT_DREGS + OSH_OUT_AREGS)

/* Run `entry` until it returns to the sentinel (its rts) or reaches `stop_pc` — a checkpoint
 * PC that lets a never-returning function (e.g. _start, whose call to the game loop never
 * comes back) be diffed at a chosen point instead of at rts. Pass stop_pc = 0 to disable.
 * dregs/aregs are D0..D7 / A0..A7 inputs (aregs[7] overridden by sp). Returns 1 if it stopped
 * at the sentinel or the checkpoint, 0 if it hit the instruction cap first (a truncated run
 * whose memory must NOT be trusted as final). out_regs receives OSH_OUT_REGS values as above. */
int osh_run(uint8_t *mem, uint32_t size, uint32_t entry,
            const uint32_t *dregs, const uint32_t *aregs,
            uint32_t sp, uint32_t sentinel, uint32_t stop_pc, uint32_t max_insns,
            uint32_t *out_regs) {
    g_mem = mem; g_size = size;

    enter_from_reset();
    for (int i = 0; i < 8; i++) {
        m68k_set_reg((m68k_register_t)(M68K_REG_D0 + i), dregs[i]);
        m68k_set_reg((m68k_register_t)(M68K_REG_A0 + i), aregs[i]);
    }
    m68k_set_reg(M68K_REG_A7, sp);
    m68k_set_reg(M68K_REG_PC, entry);
    m68k_write_memory_32(sp, sentinel);   /* return address: rts -> sentinel */

    /* Install trap vectors transiently (restored below so the final image is trap-free). */
    uint32_t save_g = m68k_read_memory_32(TRAP_VEC_GEMDOS), save_x = m68k_read_memory_32(TRAP_VEC_XBIOS);
    uint32_t save_b = m68k_read_memory_32(TRAP_VEC_BIOS),   save_a = m68k_read_memory_32(TRAP_VEC_GEM);
    m68k_write_memory_32(TRAP_VEC_GEMDOS, MAGIC_GEMDOS);
    m68k_write_memory_32(TRAP_VEC_XBIOS, MAGIC_XBIOS);
    m68k_write_memory_32(TRAP_VEC_BIOS, MAGIC_BIOS);
    m68k_write_memory_32(TRAP_VEC_GEM, MAGIC_GEM);
    g_heap = OS_HEAP_BASE;
    g_malloc_n = 0;
    g_unmodeled = 0;
    g_poked_input_calls = 0;

    g_wn = 0;                             /* write-set = the function's writes only */
    /* The whole PSG model's per-run state is reset by psg_enter_run(), which enter_from_reset()
     * above already called — so osh_run_bench gets it too. */
    g_dosound_n = 0;                      /* Dosound ledger = this run's XBIOS Dosound calls only */
    g_min_a7 = sp;                        /* deepest stack pointer (for exclude-band sanity checks) */
    /* The external agent's per-run state is reset by sched_enter_run(), which enter_from_reset()
     * above already called — the same split psg_enter_run() and hw_enter_run() use. */
    uint32_t n = 0;
    g_ncycles = 0;                                  /* 68000 cycle tally = this run's game code only */
    for (; n < max_insns; n++) {
        uint32_t pc = m68k_get_reg(0, M68K_REG_PC);
        if (pc == sentinel || (stop_pc && pc == stop_pc)) break;
        /* After the stop tests, so an entry triggered on the sentinel or the checkpoint never fires
         * — the run ends at that PC and nothing could read the byte. Before the instruction
         * executes, which is the point that matches the candidate's poll (see sched_fire).
         *
         * `n` NON-ZERO IS THE OTHER HALF OF THAT. Musashi's first m68k_execute() after a reset
         * spends the reset's own cycles and executes NO instruction, so iteration 0 observes the
         * entry PC and iteration 1 observes it again and runs it. Every counter here has always
         * included that observation (g_ninsns is one more than the instructions executed, and
         * changing it would move every pinned perf number), but an arrival count that did would be
         * one too many for a wait loop whose compare IS the entry instruction — and it is compared
         * against the candidate's poll count. Skipping iteration 0 makes both trigger kinds 1-based
         * and costs nothing: nothing executed there. */
        if (g_sched_n && n) sched_fire(pc, n);
        if (g_cov_on && pc < COV_SIZE) g_cov[pc >> 3] |= (uint8_t)(1u << (pc & 7));   /* coverage */
        uint32_t cur_a7 = m68k_get_reg(0, M68K_REG_A7);
        if (cur_a7 < g_min_a7) g_min_a7 = cur_a7;
        if      (pc == MAGIC_GEMDOS) handle_trap(1);
        else if (pc == MAGIC_XBIOS)  handle_trap(14);
        else if (pc == MAGIC_BIOS)   handle_trap(13);
        else if (pc == MAGIC_GEM)    handle_trap(2);
        else                         g_ncycles += (uint32_t)m68k_execute(1);   /* one insn; tally its cycles */
    }
    g_ninsns = n;                                   /* instruction count for perf profiling */
    /* The four PSG rejections (mixed paths, an unservable access, an unseeded read, a read with no
     * select) are NOT folded into g_unmodeled: emu.run tests every counter and names every cause
     * that applies, so a run that both mixes the PSG paths and makes an unmodeled OS call reports
     * both rather than sending the reader after one of them twice. They also have four different
     * remedies. */
    for (int i = 0; i < OSH_OUT_DREGS; i++)
        out_regs[i] = m68k_get_reg(0, (m68k_register_t)(M68K_REG_D0 + i));
    for (int i = 0; i < OSH_OUT_AREGS; i++)
        out_regs[OSH_OUT_DREGS + i] = m68k_get_reg(0, (m68k_register_t)(M68K_REG_A0 + i));

    uint32_t wn = g_wn;                              /* keep the restore writes out of the write-set */
    m68k_write_memory_32(TRAP_VEC_GEMDOS, save_g);   /* restore vectors */
    m68k_write_memory_32(TRAP_VEC_XBIOS, save_x);
    m68k_write_memory_32(TRAP_VEC_BIOS, save_b);
    m68k_write_memory_32(TRAP_VEC_GEM, save_a);
    g_wn = wn;
    uint32_t final_pc = m68k_get_reg(0, M68K_REG_PC);  /* reached rts or the checkpoint? */
    return final_pc == sentinel || (stop_pc && final_pc == stop_pc);
}

/* Benchmark a cross-compiled C function (our reconstruction, built to m68k and loaded into `mem` at
 * its link addresses) — for comparing the reconstruction's on-target cycle cost against the original
 * (osh_run). Unlike osh_run this installs NO OS-trap vectors: the target is pure computation over the
 * image pointer, and those vectors sit inside the reconstruction's own .text (linked at base 0), so
 * writing them would corrupt code. `arg0` is the single 32-bit C argument, placed at 4(sp) per the
 * m68k SysV ABI; `sentinel` is the return address (an even PC outside the loaded code). Reports cycles
 * + instructions via the shared osh_num_* getters. Returns 1 if it returned to the sentinel. */
int osh_run_bench(uint8_t *mem, uint32_t size, uint32_t entry, uint32_t arg0,
                  uint32_t sp, uint32_t sentinel, uint32_t max_insns, uint32_t *out_regs) {
    g_mem = mem; g_size = size;
    enter_from_reset();
    m68k_set_reg(M68K_REG_A7, sp);
    m68k_set_reg(M68K_REG_PC, entry);
    m68k_write_memory_32(sp, sentinel);       /* return address: rts -> sentinel */
    m68k_write_memory_32(sp + 4, arg0);       /* first C argument (the image pointer) */
    g_min_a7 = sp;

    uint32_t n = 0;
    g_ncycles = 0;
    for (; n < max_insns; n++) {
        uint32_t pc = m68k_get_reg(0, M68K_REG_PC);
        if (pc == sentinel) break;
        uint32_t cur_a7 = m68k_get_reg(0, M68K_REG_A7);
        if (cur_a7 < g_min_a7) g_min_a7 = cur_a7;
        uint32_t cyc = (uint32_t)m68k_execute(1);
        g_ncycles += cyc;
        if (g_prof_on && pc < PROF_SIZE) g_prof[pc >> 1] += cyc;
    }
    g_ninsns = n;
    out_regs[0] = m68k_get_reg(0, M68K_REG_D0);
    return m68k_get_reg(0, M68K_REG_PC) == sentinel;
}

/* How many values osh_run writes into its out_regs buffer. A caller allocates that buffer, so a
 * caller built against a different OSH_OUT_REGS than the .so it loads either reads slots the run
 * never wrote or is overrun by it — the second corrupts the caller's memory. emu.py sizes its
 * buffer from its own mirror and checks it against this before the first run. */
uint32_t        osh_out_regs(void)    { return OSH_OUT_REGS; }
uint32_t        osh_num_writes(void)  { return g_wn; }
const uint32_t *osh_write_addrs(void) { return g_waddr; }
uint32_t        osh_unmodeled(void)   { return g_unmodeled; }
uint32_t        osh_min_a7(void)      { return g_min_a7; }
/* The Malloc bump pointer left by the last osh_run — diagnostics only (how far the heap grew). */
uint32_t        osh_heap(void)        { return g_heap; }
/* How many GEMDOS Malloc calls the last osh_run serviced. This, NOT the bump pointer, is what
 * "did this run allocate?" means: a serviced Malloc whose rounded size is 0 hands back a block at
 * OS_HEAP_BASE without moving g_heap, so a pointer comparison would miss it. emu.run() keys the
 * heap-over-program guard on this count (see emu._vet_no_malloc_over_program). */
uint32_t        osh_malloc_count(void) { return g_malloc_n; }
/* How many traps the last osh_run serviced that reached the harness-poked model state. emu.run() keys
 * the poked-input-over-program guard on this count (see emu._vet_no_poked_input_read), the same way
 * it keys the heap guard on osh_malloc_count: both waivers claim something about the GAME, so both
 * are re-tested per run rather than trusted once. */
uint32_t        osh_poked_input_calls(void) { return g_poked_input_calls; }
uint32_t        osh_num_insns(void)   { return g_ninsns; }
uint64_t        osh_num_cycles(void)  { return g_ncycles; }
uint32_t        osh_psg_count(void)   { return g_psgn; }
/* PSG accesses this run that did not fit in the ledger (see g_psg_dropped) — emu.run names them. */
uint32_t        osh_psg_dropped(void) { return g_psg_dropped; }
/* Direct PSG accesses the model refused this run — emu.run names them in its diagnostic. */
uint32_t        osh_psg_unmodeled(void) { return g_psg_unmodeled; }
const uint8_t  *osh_psg_kinds(void)   { return g_psg_kind; }     /* OS_PSG_EVENT_* per entry */
const uint8_t  *osh_psg_regs(void)    { return g_psg_reg; }
const uint8_t  *osh_psg_vals(void)    { return g_psg_val; }
const uint8_t  *osh_cov_data(void)    { return g_cov; }          /* the visited-PC bitset (for merge) */
uint32_t        osh_cov_bytes(void)   { return sizeof g_cov; }
