/* os.h — deterministic TOS trap model shared by the oracle (shim.c) and reconstructed
 * OS wrappers. The oracle can't call real TOS, so GEMDOS/BIOS/XBIOS traps are serviced
 * with fixed semantics; a reconstruction must model the SAME return value and image effect
 * for its differential test to hold.
 *
 * Modeled: calls that only touch hardware TOS never reads back (Setpalette/Setcolor/Setscreen,
 * Dosound, Cconout/Cconws, Ikbdws) have NO image effect and return 0. Physbase/Logbase return
 * OS_SCREEN_BASE; Getrez returns 0 (low-res); Malloc bump-allocates from OS_HEAP_BASE (which
 * project.toml's `heap_base` may move; see the fixed-memory-map section);
 * Mshrink/Mfree return 0. GEMDOS file I/O is modeled by os_fopen/os_fcreate/os_fread/os_fwrite/
 * os_fclose over a staged-file table (below). The calls that DO read or write model state —
 * Bconstat/Bconin/Crawio, Super, Giaccess, Random — are the os_* helpers further down. XBIOS Supexec
 * runs the passed routine in place (its rts returns to the caller, its D0 becomes the result).
 *
 * GEM trap #2 (AES/VDI) is modeled by ../src/gem.c over ../src/raster.c — the one model compiled
 * into BOTH the oracle and every candidate, reached from here through os_gem_trap()/os_vdi()/
 * os_aes(). It DRAWS: seventeen VDI opcodes including vro_cpyfm's sixteen logic operations, vr_recfl
 * and v_gtext, plus four AES ones (TRAP_MODEL.md, Phases 11-12).
 *
 * The calls that hand a byte to a DEVICE rather than storing one — Cconout/Cconws, BIOS Bconout to
 * the IKBD, graf_mouse, v_show_c/v_hide_c — are an ordered off-image ledger compared between the two
 * sides, like the Dosound one (Phase 13); so is nothing else here.
 *
 * BIOS console I/O (Bconstat/Bconin), GEMDOS's console (Cconis/Crawcin/Cnecin/Crawio), GEMDOS Super,
 * GEMDOS Fcreate/Fwrite/Fseek, XBIOS Giaccess and XBIOS Random are modeled below; TRAP_MODEL.md
 * records what each does and does NOT capture. OS_SCREEN_BASE is a provisional low-memory arena;
 * OS_HEAP_BASE is main's Malloc block (below).
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
 * OS_FS_TABLE and an image large enough to hold the staging area below the stack guard —
 * harness._vet_os_memory_map() checks both against the bound project and fails loudly if not,
 * which is the signal to move a region here (and its Python mirror in harness.py). The Malloc
 * arena is the exception: it is per-project too, see OS_HEAP_BASE below. */
#define OS_IMAGE_SIZE  0x100000u /* the flat image both cores run on is this long. Kit-wide for the
                                  * same reason the addresses below are: os_fread/os_fwrite must
                                  * bound their memcpy against something, and a reconstruction that
                                  * calls them is handed the image pointer alone, never a length.
                                  * harness._vet_os_memory_map() pins it equal to the bound
                                  * project's image_size, so a project that grows its image fails
                                  * loudly here instead of copying past the buffer unchecked. */
#define OS_SCREEN_BASE 0x8000u   /* Physbase/Logbase result (in-image screen region) */
/* ---- the Malloc arena's base: the one region of this map that MOVES ---------------------
 * Installed at run time from project.toml's optional `heap_base`, because os.h is compiled into two
 * SHARED objects and a #define cannot answer "where" per project. The whole mechanism is in
 * ../README.md, "The Malloc arena is the one region a project places".
 *
 * WHAT A READER OF THIS FILE NEEDS: OS_HEAP_BASE is a VARIABLE READ, not a constant expression. It
 * is spelt as it always was, so reconstructed code that reads it is unchanged — but it may not
 * appear in a case label, an array bound or a static initialiser. A build that does not link
 * src/os_heap.c (an on-target build, which allocates through real TOS) fails at LINK if it reads
 * it, rather than silently using a stale default. */
#define OS_HEAP_BASE_DEFAULT 0x20000u /* an in-image region above the program, growing up (BuggyBoy's
                                       * main takes a 0x5ee08-byte work block here, ending ~0x7ee08
                                       * — the largest claim so far) */
extern uint32_t g_os_heap_base;       /* the live base on the CANDIDATE side (src/os_heap.c) */
void os_set_heap_base(uint32_t base); /* ...installed once, before any run; the shim has its own */
#define OS_HEAP_BASE   (g_os_heap_base)

/* ---- the arena's CEILING, installed the same way the base is ---------------------------------
 * The first address the arena may NOT reach: os_map.OS_FS_TABLE, narrowed by project.toml's optional
 * `heap_limit`. `harness` installs the resolved value into both shared objects at import, exactly as
 * it installs the base, so `Malloc(-1)`'s answer and the ceiling check below describe the window the
 * bound project really has. A VARIABLE READ, not a constant expression, for OS_HEAP_BASE's reason.
 * (OS_FS_TABLE is declared with the staged-file map further down; a macro body is expanded where it
 * is USED, so naming it here keeps one source for the table's address rather than a second copy.) */
#define OS_HEAP_LIMIT_DEFAULT OS_FS_TABLE
extern uint32_t g_os_heap_limit;
void os_set_heap_limit(uint32_t limit);
#define OS_HEAP_LIMIT  (g_os_heap_limit)

/* ...and the CANDIDATE's Malloc itself, mirroring the bump allocator `oracle/shim.c` services the
 * GEMDOS trap with: round the request up to a word and hand back the pointer before the bump. It is
 * here so a reconstruction's Malloc wrapper calls the model rather than carrying a private copy of
 * its arithmetic — a copy is what drifts from the oracle's the day either changes.
 *
 * Malloc(-1) is GEMDOS's "how big is the LARGEST FREE BLOCK?" query and answers a SIZE, not a
 * pointer: OS_HEAP_LIMIT minus the bump pointer, without moving it, on both sides. (It used to fall
 * out of the rounding as the arena BASE, which is a plausible-looking address and the wrong answer
 * to the question — a program that then asked for that many bytes would be asking for an address's
 * worth of memory.)
 *
 * IT REFUSES a request the window cannot hold, rather than bumping past OS_HEAP_LIMIT: blocks handed
 * out over the staged-file table are plain image writes on both sides, so the two corrupted runs
 * compare equal. The ORACLE's half of the same guard is `emu._vet_heap_within_bounds`, which reads
 * the pointer after the run; this is the candidate's, and it fires at the call.
 *
 * `g_os_heap_reset()` puts the pointer back to the base; `harness.arm_candidate` calls it before
 * EVERY candidate run, the poison re-run included, for the reason every other per-run model is
 * re-armed there — otherwise the second case in a process allocates where the first left off while
 * the oracle starts from the base, and the two sides diverge for a reason no case declared.
 * `g_os_heap_pointer()` is what `harness.differential` compares against the oracle's.
 * ON-TARGET builds do not compile src/os_heap.c: there the heap is real TOS's. */
#define OS_MALLOC_LARGEST_FREE 0xffffffffu   /* Malloc(-1), spelt as the caller pushes it */
uint32_t os_malloc(uint32_t size);
void     g_os_heap_reset(void);
uint32_t g_os_heap_pointer(void);
#define OS_CRAWIO_RESULT 0u      /* GEMDOS Crawio(0xff) raw non-blocking read: what it returns when
                                  * no key is pending. os_crawio() below serves the same poked
                                  * console state as Bconstat/Bconin, so this is its answer on an
                                  * image with nothing staged. BuggyBoy's check_abort /
                                  * console_scancode hardcode it (see os_crawio). */
#define OS_KBDVBASE    0x500u    /* XBIOS Kbdvbase() result: a fixed in-image KBDVBASE struct (free low
                                  * region, clear of the vector page and the program). install_handlers
                                  * patches its mousevec (+0x10) / joyvec (+0x18). Shared with the shim. */

/* ---- harness-poked model state, 0x600..OS_POKE_BLOCK_END --------------------------------
 * Hardware whose real value is time-varying (a keypress arriving on an IRQ, the PSG's register
 * contents, XBIOS Random) has no analogue on the candidate side, which is pure C with no
 * interrupts. Following projects/buggyboy/recreate/HARNESS.md, it is modeled at the STATE level:
 * each of these is an ordinary in-image input a test pokes, so BOTH cores read the same bytes and
 * the value is differentially verifiable. The block sits just above the KBDVBASE struct, still in
 * the free low region below every program (load_base >= 0x10000) and above TOS's documented
 * system-variable area — the same siting argument as OS_KBDVBASE.
 * Mirrored in Python by harness.py; test/test_os_memory_map.py pins the two sets equal. */
#define OS_CON_PENDING  0x600u   /* u32: how many keystrokes are queued, up to OS_CON_QUEUE_MAX
                                  * (nonzero = one is waiting; a larger value is the older flag
                                  * spelling and is served as a single key — see
                                  * os_console_take_key) */
#define OS_CON_CHAR     0x604u   /* u32: the longword the NEXT console read returns
                                  * (scancode << 16 | ascii). The keys BEHIND it are OS_CON_QUEUE. */
#define OS_RANDOM_VALUE 0x608u   /* u32: the value XBIOS Random returns (masked to 24 bits) */
#define OS_PSG_REGS     0x610u   /* the YM2149 register file, OS_PSG_NREGS bytes (see os_giaccess) */
#define OS_PSG_NREGS    16       /* the YM2149 has 16 registers, selected by 4 bits */
/* Both sides of the direct-PSG model (oracle/shim.c, src/psg.c) carry a bit per register in a
 * uint16_t — which registers are seeded, known, or were read while unknown. The check lives here,
 * once, beside the count it is about: a copy in each file is a copy that can be updated in one. */
#if OS_PSG_NREGS > 16
#error "the direct-PSG known/seed masks are uint16_t: OS_PSG_NREGS registers no longer fit"
#endif

/* The VDI's two INPUT devices, poked exactly as the console key is: the mouse the AES tracks
 * (vq_mouse) and the keyboard's shift/control/alt state (vq_key_s). Both are IRQ-driven on a real
 * machine and so have no analogue on the candidate side — the governing rule at the top of
 * TRAP_MODEL.md — and both are read by the SAME os.h code on both sides, so one poke is one
 * declared input. Unlike the console key, neither is CONSUMED: a query reports the staged state
 * and leaves it, which is what the real drivers do. */
#define OS_MOUSE             0x620u  /* three words: x, y, buttons (offsets below) */
#define OS_MOUSE_OFF_X       0
#define OS_MOUSE_OFF_Y       2
#define OS_MOUSE_OFF_BUTTONS 4
#define OS_MOUSE_BYTES       6
#define OS_KEY_SHIFT         0x626u  /* u16: the shift-key mask vq_key_s reports */

/* ---- the VDI WORKSTATION STATE ---------------------------------------------------------------
 * The attributes one VDI call sets and a later one reads: `vsf_color`'s fill colour, `vst_color`'s
 * text colour, the clip rectangle, and the base "the screen" means. They live IN THE IMAGE, inside
 * the harness-poked block, so both sides read the same bytes and the byte diff already covers them —
 * a reconstruction that sets the wrong fill colour diverges here, before it has drawn anything.
 * shim.c therefore tallies every serviced VDI call as a poked-input call.
 *
 * A FRESH IMAGE IS ALL ZEROES, which is not a workstation's state; `v_opnvwk` installs the caller's
 * own work_in attributes, and a case entering a program mid-way pokes what it needs
 * (`harness.vdi_state`). WHY the state is here rather than in C statics, and what that costs:
 * TRAP_MODEL.md, "Phase 12". */
#define OS_VDI_STATE              0x628u
#define OS_VDI_OFF_HANDLE          0   /* u16: the open workstation's handle, 0 = none open */
#define OS_VDI_OFF_FILL_COLOR      2   /* u16: vsf_color */
#define OS_VDI_OFF_TEXT_COLOR      4   /* u16: vst_color */
#define OS_VDI_OFF_WRITE_MODE      6   /* u16: vswr_mode (recorded; see TRAP_MODEL.md, not consulted) */
#define OS_VDI_OFF_TEXT_HEIGHT     8   /* u16: vst_height's requested height, likewise recorded */
#define OS_VDI_OFF_FILL_INTERIOR  10   /* u16: vsf_interior, likewise */
#define OS_VDI_OFF_FILL_STYLE     12   /* u16: vsf_style, likewise */
#define OS_VDI_OFF_CLIP_ON        14   /* u16: vs_clip's flag; 0 = no clip rectangle */
#define OS_VDI_OFF_CLIP_X1        16   /* u16 x4: the clip rectangle, normalised */
#define OS_VDI_OFF_CLIP_Y1        18
#define OS_VDI_OFF_CLIP_X2        20
#define OS_VDI_OFF_CLIP_Y2        22
/* u32: the base address MFDB address 0 — "the screen" — means. ZERO SELECTS OS_SCREEN_BASE, so a
 * case that never declares one draws where Physbase/Logbase already point. The model does NOT track
 * XBIOS Setscreen (still a no-op, TRAP_MODEL.md): a game that moves its logical base declares the
 * result here as an input instead, which is the same treatment every other un-modelable machine
 * fact gets. */
#define OS_VDI_OFF_SCREEN         24
#define OS_VDI_STATE_BYTES        28

/* ---- the CONSOLE KEY QUEUE, the rest of the one staged keystroke ------------------------------
 * OS_CON_PENDING/OS_CON_CHAR hold how many keys are queued and what the NEXT read returns; these are
 * the ones BEHIND it, oldest first, so a case can stage a walk of keypresses instead of one
 * (`harness.console_keys`). Every console read — Bconin, Crawio's read direction, Crawcin/Cnecin —
 * takes the head and shifts the queue up, so all of them see one ordered stream, which is the whole
 * point of their being ONE model.
 *
 * IT SITS AT THE TOP OF THE BLOCK rather than beside OS_CON_CHAR because there is no room there:
 * OS_RANDOM_VALUE and the PSG register file already follow it. Inside the block for the reason
 * everything else here is — under a program that covers these addresses they are the game's own
 * bytes, and every guard keyed on the block applies unchanged. See TRAP_MODEL.md, "Phase 13". */
#define OS_CON_QUEUE        0x644u  /* u32 x (OS_CON_QUEUE_MAX - 1), oldest first */
#define OS_CON_QUEUE_MAX    8       /* keystrokes one case may stage: OS_CON_CHAR plus the queue */
#define OS_CON_QUEUE_BYTES  ((OS_CON_QUEUE_MAX - 1) * 4)

/* XBIOS Dosound(A0) writes the chip, not the image, so both sides record their calls in a ledger the
 * harness compares (src/dosound_log.c on the candidate side, shim.c's g_dosound_arg on the oracle's).
 * ONE cap for both: were they to differ, a run past the smaller one would drop entries on that side
 * only and diverge the comparison for a reason that has nothing to do with the reconstruction. */
#define OS_DOSOUND_LOG_MAX 256

/* ---- the OFF-IMAGE OS EVENT LEDGER -----------------------------------------------------------
 * ONE ordered (kind, value) stream, kept on BOTH sides — `oracle/shim.c`'s mirror and
 * `../src/os_log.c`'s — and compared per run by `harness.differential`. It carries the calls whose
 * whole effect is off-image, so that a reconstruction which makes them is separable from one which
 * does not:
 *
 *   GEMDOS Cconout / Cconws / Crawio(write)   a character to the console
 *   BIOS   Bconout(dev 4, b)                  a COMMAND byte to the IKBD 6301
 *   AES    graf_mouse(mode)                   show/hide the GEM mouse pointer
 *   VDI    v_show_c / v_hide_c                show/hide the graphics cursor
 *
 * ONE CAP FOR BOTH SIDES, for the Dosound ledger's reason: were they to differ, a run past the
 * smaller one would drop entries on that side only and diverge for a reason that has nothing to do
 * with the reconstruction. `harness` refuses a comparison AT the cap rather than trust it.
 *
 * WHY one stream rather than four, why Dosound is left where it is, and what an on-target build
 * substitutes: TRAP_MODEL.md, "Phase 13". */
#define OS_EVENT_LOG_MAX   4096
#define OS_EVENT_NONE       0    /* the out-parameter's "this call had no off-image effect" */
#define OS_EVENT_CONOUT     1    /* value = the character byte written to the console */
#define OS_EVENT_IKBD       2    /* value = the command byte sent to the IKBD (BIOS Bconout, dev 4) */
#define OS_EVENT_GEM_MOUSE  3    /* value = AES graf_mouse's mode word (M_OFF = 256, M_ON = 257) */
#define OS_EVENT_VDI_CURSOR 4    /* value = 1 for v_show_c, 0 for v_hide_c */

/* One off-image event a modeled call produced. `../src/gem.c` reports through this rather than
 * logging, because it is compiled into both sides and each side owns a different ledger.
 *
 * THE VALUE IS 32 BITS although no kind above needs more than 16. That is deliberate headroom: the
 * two ledgers still outside this stream — Dosound's (a command-list POINTER) and the hardware write
 * ledger's (an address and a longword) — could fold into it the day retiring them buys something,
 * and a width change afterwards would have to move every reader on both sides at once. NOTHING IS
 * MIGRATED NOW: Dosound and the hardware ledgers are working surfaces and stay where they are. */
typedef struct {
    uint16_t kind;               /* OS_EVENT_*; OS_EVENT_NONE = the call had no off-image effect */
    uint32_t value;
} os_event_t;

/* THE CANDIDATE'S recording side (`src/os_log.c`). An ON-TARGET build does not compile that file
 * and supplies its own definition — the trap that really writes the console or the IKBD — exactly as
 * it supplies its own `g_dosound`. Declared, never defined here, so that substitution is a link-time
 * choice rather than a `#ifdef` inside every core. */
void g_os_event(uint16_t kind, uint32_t value);

/* The two a reconstruction calls by name, so a core reads as what it does rather than as a ledger
 * append. `os_cconout` is GEMDOS Cconout/Cconws's byte; `os_ikbd_out` is a BIOS Bconout to the
 * keyboard. Neither can refuse: sending a byte to a device always succeeds in this model. */
static inline void os_cconout(uint8_t ch)   { g_os_event(OS_EVENT_CONOUT, ch); }
static inline void os_ikbd_out(uint8_t cmd) { g_os_event(OS_EVENT_IKBD, cmd); }

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
 * Phase 6 lets it declare the YM2149's registers (one of the five, the ACIA status, carries a MODEL
 * DEFAULT instead — os_hw_model_defaults() below says why it is the only one that may). Everything else off-image still reads 0 and is
 * still invisible; these are singled out because the VALUE STEERS THE RUN, which is the one shape
 * where a fabricated 0 produces a green run whose behaviour is wrong on the machine (the
 * `$ffff820a` defect that survived BuggyBoy's entire differential and only appeared on real
 * hardware — see PORTABILITY.md's "the BuggyBoy defect, demonstrated concretely"). Three of the five
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
 * static byte (the monitor detect, the sync mode, the ACIA's TDRE) may be read as often as a run
 * likes, because the
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
/* The IKBD 6850 ACIA's STATUS register. Bit 1 (TDRE) is "the transmit register is empty", which is
 * what every IKBD send loop spins on before it stores the command byte to the data port next door;
 * bit 7 (IRQ) and bit 0 (RDRF) are what an ACIA interrupt handler tests once on entry.
 *
 * STATIC, NOT VOLATILE, and the distinction is worth spelling out because a status register looks
 * like the FDC poll this model excludes. The excluded shape is a byte whose two successive reads
 * must DIFFER for the run to proceed — a busy flag that has to go from set to clear. TDRE is not
 * that: a send loop exits on the FIRST read that finds it set, so a per-run constant with the bit
 * set describes every read the loop makes (there is exactly one) and both sides leave the loop at
 * the same poll. Declared the other way — the bit clear — a constant would hang both sides equally,
 * which is a case that never terminates rather than a case that lies. What the constant cannot
 * describe is how many polls the machine would really have taken; the loop body is empty and writes
 * nothing, so that count has no image effect, and the read ledger pins the poll the reconstruction
 * DOES make against the oracle's rather than claiming a number of them. */
#define OS_HW_ACIA_STATUS  0xfffc00u
#define OS_ACIA_TX_RDY     0x02u   /* bit 1 of the byte above: the transmit register is empty */
/* The ACIA's DATA port, one word up. A send loop only ever WRITES it, which the write ledger
 * compares; an ACIA INTERRUPT HANDLER reads it, and that read is what this slot is for.
 *
 * VOLATILE, and it is the one modeled address whose volatility is a property of the PROTOCOL rather
 * than of a counter ticking. Each read POPS the receive register: the byte the keyboard controller
 * put there is consumed, and the next read answers whatever arrived after it. So one per-run
 * constant describes exactly ONE read of it — which is enough for a handler that reads the byte
 * once per entry, and is refused (os.h's volatile re-read rule) for anything that reads it twice.
 * That refusal is the honest answer rather than a limitation worked around: a run needing two
 * different bytes out of this port is two runs, each declaring the byte the machine held then.
 *
 * WHAT IT IS STILL NOT is a SEQUENCE model. A handler that drains a whole IKBD packet inside one
 * entry — reading the port until the controller stops asserting — needs a declared LIST of bytes,
 * one per read, and nothing here has one. TRAP_MODEL.md, "Still unmodeled", says so. */
#define OS_HW_ACIA_DATA    0xfffc02u

/* Both sides index the modeled set by SLOT rather than by address — the seed is an array, the
 * known-mask is a bit per slot, and the ledger records a slot per entry — so the slot numbers are
 * as much a part of the shared contract as the addresses, and os_hw_addrs() below is the one table
 * that maps between them. */
#define OS_HW_SLOT_MFP_GPIP          0
#define OS_HW_SLOT_SHIFTER_SYNC      1
#define OS_HW_SLOT_SHIFTER_VCOUNT_MID 2
#define OS_HW_SLOT_SHIFTER_VCOUNT_LOW 3
#define OS_HW_SLOT_ACIA_STATUS       4
#define OS_HW_SLOT_ACIA_DATA         5
#define OS_HW_NSLOTS                 6
#if OS_HW_NSLOTS > 32
#error "the seeded-hardware known/seed masks are uint32_t: OS_HW_NSLOTS slots no longer fit"
#endif

/* The ordered READ ledger's cap, on BOTH sides (shim.c's g_hw_log_* and src/hw.c's), for
 * OS_PSG_LOG_MAX's reason: were the two to differ, a long run would drop entries on one side only
 * and the streams would diverge for a reason that has nothing to do with the reconstruction. Sized
 * like the PSG's rather than like Dosound's because these addresses are POLLED — an FDC wait loop
 * reads $fffa01 once per iteration — so a modest cap would truncate an ordinary run. */
#define OS_HW_LOG_MAX 4096

/* ---- the HARDWARE WRITE ledger (TRAP_MODEL.md, "Phase 10") ------------------------------------
 * The read model above is only half of the off-image surface. A STORE to a hardware register — the
 * shifter's colour row, the MFP's in-service register, the ACIA's data port — lands outside the
 * image too, so the oracle DROPS it and a reconstruction that made no store at all is byte-for-byte
 * identical to one that made every store the original makes. Phase 10 closes that half the way
 * Phase 6 closed the YM2149's: both sides keep an ORDERED ledger of (address, width, value) and
 * harness.differential compares them exactly.
 *
 * ONE CAP FOR BOTH SIDES (shim.c's g_hww_* and src/hw.c's), for OS_PSG_LOG_MAX's reason: were they
 * to differ, a long run would drop entries on one side only and the streams would diverge for a
 * reason that has nothing to do with the reconstruction. Sized like the read ledger's rather than
 * like Dosound's because a palette upload is eight stores and a frame can hold several. */
#define OS_HW_WRITE_LOG_MAX 4096

/* WHERE A HARDWARE REGISTER IS, and the whole of what this ledger covers: the three blocks the ST
 * DECODES, and not the whole of the address space above them.
 *
 *   $ff8000..$ff8fff  the internal registers — memory configuration, the shifter's video base and
 *                     its sixteen colour words, the resolution byte, the DMA/FDC pair, the YM2149's
 *                     mirrored block, the STE's DMA sound and blitter.
 *   $fffa00..$fffaff  the MFP 68901 — its interrupt-enable, pending, in-service and mask registers,
 *                     the four timers, and the GPIP the read model already names.
 *   $fffc00..$fffcff  the two 6850 ACIAs, keyboard/IKBD and MIDI.
 *
 * THE LEDGER IS NOT "EVERY OFF-IMAGE WRITE", and the distinction is load-bearing twice over. A
 * store past the end of the 1 MiB image is usually a RUNAWAY POINTER rather than a device: Joust's
 * `update_pterodactyl` driven with a y of 0x8000 computes a screen address around $570000 and
 * stores a sprite there, and BuggyBoy's `poke_color_reg` with a wild register selector reaches
 * $ff95ea — unmapped on the machine in both cases, dropped by both sides as they always were.
 * Ledgering those would make a reconstruction answer for arithmetic the byte diff cannot see
 * either, on inputs the game never produces; the surface that holds a runaway store is
 * guarded_image.py's, not this one.
 *
 * THE RESIDUAL, stated rather than hidden: a runaway that lands INSIDE one of these three blocks is
 * indistinguishable here from a deliberate register store, and is ledgered. That is the right way
 * round — a store into the decoded I/O space is a store the machine acts on, whatever the
 * reconstruction meant by it. */
#define OS_HW_IO_INTERNAL_LO 0xff8000u   /* shifter / DMA / YM2149 / blitter */
#define OS_HW_IO_INTERNAL_HI 0xff8fffu
#define OS_HW_IO_MFP_LO      0xfffa00u   /* MFP 68901 */
#define OS_HW_IO_MFP_HI      0xfffaffu
#define OS_HW_IO_ACIA_LO     0xfffc00u   /* IKBD + MIDI 6850s */
#define OS_HW_IO_ACIA_HI     0xfffcffu
/* The page all three blocks live in. Not a fourth block: it is the ONE comparison that rejects the
 * runaway class before the table is walked at all, which matters because a runaway store happens
 * inside a per-pixel loop (Joust's $570000 sprite) and reaches this predicate thousands of times a
 * frame, while a real register store is a handful per frame. */
#define OS_HW_IO_PAGE      0xff0000u
#define OS_HW_IO_PAGE_MASK 0xff0000u

/* Is `addr` inside one of those blocks?
 *
 * IT TAKES THE 24-BIT BUS FORM AND DOES NOT MASK, which is hw.h's contract for `hw_read8` stated
 * once more for the write door: the oracle folds an access with `BUS_ADDR_MASK` before it decodes,
 * because that is what the 68000's bus does to an instruction's operand; a RECONSTRUCTION spells
 * the address itself, and `$ffff8240` there is a mistake worth a refusal rather than a silent
 * equivalence. Masking here would make the candidate ledger `$ffff8240` where the oracle ledgers
 * `$ff8240` and red as a wrong-register bug — and it would defeat an address-keyed `hw_waiver`,
 * which could then match one side only.
 *
 * Written over a table rather than as three ORed comparisons so the blocks are a LIST both sides
 * read, the way the modeled read addresses are — a fourth block is then one row. */
static inline int os_hw_is_io(uint32_t bus_addr) {
    static const uint32_t blocks[][2] = {
        {OS_HW_IO_INTERNAL_LO, OS_HW_IO_INTERNAL_HI},
        {OS_HW_IO_MFP_LO,      OS_HW_IO_MFP_HI},
        {OS_HW_IO_ACIA_LO,     OS_HW_IO_ACIA_HI},
    };
    if ((bus_addr & OS_HW_IO_PAGE_MASK) != OS_HW_IO_PAGE)
        return 0;
    for (unsigned block = 0; block < sizeof blocks / sizeof blocks[0]; block++)
        if (bus_addr >= blocks[block][0] && bus_addr <= blocks[block][1])
            return 1;
    return 0;
}

/* What one write-ledger entry's WIDTH field is. The 68000's three store widths, recorded as the
 * byte count rather than as an opcode size code, so an entry reads as the number of image bytes the
 * store would have covered had the address been in the image. */
#define OS_HW_WRITE_WIDTH_8  1
#define OS_HW_WRITE_WIDTH_16 2
#define OS_HW_WRITE_WIDTH_32 4

/* THE WIDTH OF A LEDGERED STORE, AS THE MASK ITS VALUE IS RECORDED UNDER. Both sides mask, so that
 * a caller handing a longword to an 8-bit store records the byte the 68000 would have put on the
 * bus rather than a value no store made — and they mask from ONE table, or the two ledgers would
 * disagree about the same instruction for a reason that is not the reconstruction's. */
static inline uint32_t os_hw_write_mask(uint32_t width) {
    static const uint32_t masks[] = {
        [OS_HW_WRITE_WIDTH_8]  = 0xffu,
        [OS_HW_WRITE_WIDTH_16] = 0xffffu,
        [OS_HW_WRITE_WIDTH_32] = 0xffffffffu,
    };
    return masks[width];
}

/* The modeled addresses, by slot. A function-local table rather than a file-scope one so that a
 * translation unit which includes this header without using the model draws no unused-variable
 * warning, and so that both directions of the mapping are derived from ONE list. */
static inline const uint32_t *os_hw_addrs(void) {
    static const uint32_t addrs[OS_HW_NSLOTS] = {
        [OS_HW_SLOT_MFP_GPIP]          = OS_HW_MFP_GPIP,
        [OS_HW_SLOT_SHIFTER_SYNC]      = OS_HW_SHIFTER_SYNC,
        [OS_HW_SLOT_SHIFTER_VCOUNT_MID] = OS_HW_SHIFTER_VCOUNT_MID,
        [OS_HW_SLOT_SHIFTER_VCOUNT_LOW] = OS_HW_SHIFTER_VCOUNT_LOW,
        [OS_HW_SLOT_ACIA_STATUS]        = OS_HW_ACIA_STATUS,
        [OS_HW_SLOT_ACIA_DATA]          = OS_HW_ACIA_DATA,
    };
    return addrs;
}

/* ---- the ONE slot the MODEL declares, rather than the case (TRAP_MODEL.md, "Phase 7") --------
 * The ACIA status byte is the single modeled address whose answer is not a machine CONFIGURATION a
 * case has to know, but a TRANSIENT that always resolves the same way: the 6850's transmitter goes
 * empty microseconds after the last byte leaves it, so "TDRE set" is the state a quiescent ACIA is
 * in on entry to any send, and serving 0 instead is the one answer the machine never settles at —
 * it hangs the send loop for ever, which is why shim.c answered this address 0x02 unconditionally
 * from before Phase 7 existed.
 *
 * So it is the model's DEFAULT rather than a switch beside the model: an undeclared read is served
 * this byte, is NOT recorded as unseeded, and IS ledgered like any other — while a case that wants
 * another status (the transmitter busy, a receive byte pending) declares one with hw_seed and
 * overrides it. Both sides install it from this one table, on the same code path a case's seed
 * takes, exactly as shim.c's audio-capture profile does; without that the two implementations would
 * hold two copies of the same byte.
 *
 * NOTHING ELSE BELONGS HERE. Every other modeled address answers a fact about the machine the case
 * is describing — which monitor, which sync rate, where the beam is — and a default for one of
 * those is the fabricated-0 class this whole model exists to close. */
static inline const uint8_t *os_hw_model_defaults(void) {
    static const uint8_t defaults[OS_HW_NSLOTS] = {
        [OS_HW_SLOT_ACIA_STATUS] = OS_ACIA_TX_RDY,
    };
    return defaults;
}

/* Which slots os_hw_model_defaults() actually declares — named one by one rather than derived from
 * the array, for shim.c's HW_CAPTURE_PROFILE_KNOWN reason: the array is a designated initializer,
 * so a slot added above gets a silent 0 there, and declaring it here would publish that 0 as a real
 * answer. Spelled this way a new slot has NO default and stays the case's to declare. */
static inline uint32_t os_hw_default_slots(void) { return 1u << OS_HW_SLOT_ACIA_STATUS; }

/* INSTALL A RUN'S DECLARED BYTES INTO `file`, and return the mask of slots that end up KNOWN.
 *
 * The case's declaration wins; the model's own defaults fill in under it; everything else is 0. It
 * lives here, shared verbatim by shim.c's hw_enter_run and src/hw.c's g_hw_reset, for os_gem_trap's
 * reason: two copies of this are two places a precedence rule can be changed in one, and the
 * failure that produces is the oracle serving a byte the candidate does not — which surfaces as a
 * read-stream mismatch blamed on the reconstruction rather than on the model.
 *
 * `seed` is read only where `known` declares a slot, so a caller with nothing to declare may pass
 * NULL. */
static inline uint32_t os_hw_install_seed(uint8_t *file, const uint8_t *seed, uint32_t known) {
    const uint8_t *defaults = os_hw_model_defaults();
    uint32_t defaulted = os_hw_default_slots() & ~known;

    for (int slot = 0; slot < OS_HW_NSLOTS; slot++) {
        if (known & (1u << slot))          file[slot] = seed[slot];
        else if (defaulted & (1u << slot)) file[slot] = defaults[slot];
        else                               file[slot] = 0;
    }
    return known | defaulted;
}

/* Which slots are VOLATILE — a value the machine changes on its own, which a per-run constant can
 * describe for ONE read and not for two. A bit per slot, like every other mask in this model, and
 * derived from the same one table so that a slot added above is STATIC unless it says otherwise:
 * the conservative direction, since a static slot read twice is served twice and a volatile one is
 * refused, and a new slot wrongly called volatile would refuse runs that are fine. */
/* Which slots are TWO REGISTERS BEHIND ONE ADDRESS — a write lands in one and a read pops the
 * other — so a store to them does NOT make a later read's declaration stale.
 *
 * The ACIA's data port is the whole set and the reason the mask exists. `$fffc02` written is the
 * 6850's TRANSMIT register and `$fffc02` read is its RECEIVE register; they are different silicon
 * behind one bus address, so "the run wrote this byte, so the seed no longer describes it" — true
 * of every other modeled address — is simply false here. Without this, the first case to compose an
 * IKBD SEND with ACIA servicing in one run would be refused with a diagnosis that does not hold and
 * a remedy (end the case before the write) that throws the case away.
 *
 * It is deliberately NOT a general escape hatch. A slot belongs here only when the datasheet says
 * the two directions are different registers; a slot wrongly listed would serve a seed the run's own
 * store really had invalidated, which is the fabrication the staleness rule exists to refuse. */
static inline uint32_t os_hw_split_slots(void) {
    return 1u << OS_HW_SLOT_ACIA_DATA;
}

static inline uint32_t os_hw_volatile_slots(void) {
    return (1u << OS_HW_SLOT_SHIFTER_VCOUNT_MID) | (1u << OS_HW_SLOT_SHIFTER_VCOUNT_LOW)
         | (1u << OS_HW_SLOT_ACIA_DATA);
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
 * A trap #2 selects the subsystem by D0 and points D1 at a parameter block of array pointers.
 * The opcode is contrl[0]; results go into intout (and ptsout for the VDI), and the VDI reports how
 * many of each it wrote in contrl[2]/contrl[4] — which games read, so the model sets them.
 *
 * THE MODEL ITSELF IS ../src/gem.c, compiled into BOTH sides (raster.h's header says why a shared
 * .c and not a header of inlines). What is here is the two THIN WRAPPERS that turn its "did I model
 * this?" answer into the kit's refusal convention, plus the layout constants both sides and the
 * kit's own tests spell. `os_gem_trap` is for the oracle's trap dispatch and for a reconstruction
 * that reproduces the original's `trap #2` glue; `os_vdi` is the one-argument door for a
 * reconstruction that fills the block and calls the VDI directly. Both read the SAME block out of
 * the image, so the two sides' writes agree by construction.
 *
 * What each opcode does, what it deliberately does NOT capture, and what pins it: TRAP_MODEL.md,
 * "Phase 11" (the raster model) and "Phase 12" (the VDI opcodes and the AES).
 */
#define GEM_AES 0xc8u            /* D0 for an AES call */
#define GEM_VDI 0x73u            /* D0 for a VDI call */

/* The parameter block is an array of LONGS; these index it.
 * AES: apb = {contrl, global, intin, intout, addrin, addrout}
 * VDI: vpb = {contrl, intin, ptsin, intout, ptsout} */
#define AES_PB_CONTRL  0
#define AES_PB_GLOBAL  1
#define AES_PB_INTIN   2
#define AES_PB_INTOUT  3
#define AES_PB_ADDRIN  4
#define AES_PB_ADDROUT 5
#define VDI_PB_CONTRL  0
#define VDI_PB_INTIN   1
#define VDI_PB_PTSIN   2
#define VDI_PB_INTOUT  3
#define VDI_PB_PTSOUT  4

/* contrl[] is an array of WORDS; these index it. [2] and [4] are the VDI's OUTPUT counts — ptsout
 * PAIRS and intout entries written — and [6] is where v_opnvwk RETURNS the workstation handle. */
#define VDI_CONTRL_OPCODE     0
#define VDI_CONTRL_PTSIN_N    1
#define VDI_CONTRL_PTSOUT_N   2
#define VDI_CONTRL_INTIN_N    3
#define VDI_CONTRL_INTOUT_N   4
#define VDI_CONTRL_SUBOPCODE  5
#define VDI_CONTRL_HANDLE     6
#define VDI_CONTRL_SRC_MFDB   7   /* ...and [8]: the source MFDB address, high word first */
#define VDI_CONTRL_DST_MFDB   9   /* ...and [10]: the destination MFDB address */

/* The AES opcodes the model serves. Everything else is refused BY NAME (gem.c). */
#define AES_APPL_INIT   10       /* -> ap_id in intout[0] */
#define AES_APPL_EXIT   19       /* -> intout[0] = 1; no other effect */
#define AES_GRAF_HANDLE 77       /* -> phys handle + font cell sizes in intout[0..4] */
#define AES_GRAF_MOUSE  78       /* intin[0] = mode; an OS_EVENT_GEM_MOUSE ledger entry */
#define AES_M_OFF      256       /* graf_mouse's two modes, the only ones any game here uses */
#define AES_M_ON       257

/* ...and the VDI opcodes. */
#define VDI_V_CLRWK       3
#define VDI_V_GTEXT       8
#define VDI_VST_HEIGHT   12
#define VDI_VST_COLOR    22
#define VDI_VSF_INTERIOR 23
#define VDI_VSF_STYLE    24
#define VDI_VSF_COLOR    25
#define VDI_VSWR_MODE    32
#define VDI_V_OPNVWK    100
#define VDI_V_CLSVWK    101
#define VDI_VRO_CPYFM   109
#define VDI_VR_RECFL    114
#define VDI_V_SHOW_C    122
#define VDI_V_HIDE_C    123
#define VDI_VQ_MOUSE    124
#define VDI_VQ_KEY_S    128
#define VDI_VS_CLIP     129

/* v_opnvwk's work_in array (intin), which IS the workstation's opening attribute state. Only the
 * four the model keeps are named; [0] is the device id, [1..5] the line/marker/text faces the model
 * has no state for, and [10] the coordinate system. See gem.c's v_opnvwk. */
#define VDI_WORK_IN_TEXT_COLOR     6
#define VDI_WORK_IN_FILL_INTERIOR  7
#define VDI_WORK_IN_FILL_STYLE     8
#define VDI_WORK_IN_FILL_COLOR     9

/* vsf_interior's five values. The model fills HOLLOW with the background (colour 0) and SOLID with
 * the fill colour; the three that need a pattern table it does not have are REFUSED by name rather
 * than filled solid, which would draw pixels no real machine draws (gem.c's vdi_fill_colour). */
#define VDI_FILL_HOLLOW  0
#define VDI_FILL_SOLID   1
#define VDI_FILL_PATTERN 2
#define VDI_FILL_HATCH   3
#define VDI_FILL_USER    4

/* An MFDB — the block `vro_cpyfm` describes a raster with. fd_addr 0 means "the screen"; fd_stand 1
 * means the VDI's device-INDEPENDENT plane order, a different layout the model refuses rather than
 * silently reads as the interleaved one. */
#define MFDB_ADDR             0   /* long */
#define MFDB_W                4   /* word: width in pixels */
#define MFDB_H                6   /* word: height in pixels */
#define MFDB_WDWIDTH          8   /* word: width in 16-pixel words */
#define MFDB_STAND           10   /* word: 0 = device format, 1 = standard format */
#define MFDB_NPLANES         12   /* word */
#define MFDB_BYTES           20   /* ...plus fd_r1..fd_r3, three reserved words */
#define MFDB_SCREEN_ADDR      0u  /* fd_addr == this means the VDI's own screen */
#define MFDB_STANDARD_FORMAT  1   /* fd_stand == this: refused, see gem.c */

/* Deterministic "realistic low-res ST" results. */
#define OS_AES_AP_ID    0        /* appl_init: single-application id */
#define OS_VDI_HANDLE   1        /* graf_handle / v_opnvwk: the physical workstation handle */
#define OS_FONT_CELL_W  8        /* low-res system font cell / box width  (px) */
#define OS_FONT_CELL_H  8        /* low-res system font cell / box height (px) */
#define OS_SCREEN_MAX_X 319      /* v_opnvwk work_out[0]: max addressable x (xres-1) */
#define OS_SCREEN_MAX_Y 199      /* v_opnvwk work_out[1]: max addressable y (yres-1) */
#define OS_SCREEN_W     (OS_SCREEN_MAX_X + 1)
#define OS_SCREEN_H     (OS_SCREEN_MAX_Y + 1)
#define OS_SCREEN_PLANES  4      /* ST low resolution: 16 colours, four interleaved planes */
#define OS_SCREEN_WDWIDTH (OS_SCREEN_W / 16)
#define OS_SCREEN_COLOURS 16     /* v_opnvwk work_out[13] */
/* The number of entries v_opnvwk reports having written. They are what a real VDI reports; all but
 * the three named above are left ZERO, because inventing the rest of the attribute table would be
 * fabrication and no code here reads it (TRAP_MODEL.md, Phase 12). */
#define OS_VDI_WORK_OUT_INTS   45
#define OS_VDI_WORK_OUT_POINTS 6

/* The workstation attributes a freshly opened workstation carries. The last two are what v_opnvwk
 * really installs — work_in cannot express them — while the four above them are what a CASE that
 * pokes a workstation instead of opening one starts from (`harness.vdi_state`): the VDI's documented
 * defaults, which a program passing them in work_in[6..9] would get from the call itself. */
#define OS_VDI_DEFAULT_FILL_COLOR    1
#define OS_VDI_DEFAULT_TEXT_COLOR    1
#define OS_VDI_DEFAULT_FILL_INTERIOR 0   /* hollow; pinned equal to VDI_FILL_HOLLOW below */
#define OS_VDI_DEFAULT_FILL_STYLE    1
#define OS_VDI_DEFAULT_WRITE_MODE    1   /* replace */
#define OS_VDI_DEFAULT_TEXT_HEIGHT   8   /* the model has one font; see vst_height */
/* Spelt as a literal because test_os_memory_map.py parses these against their Python mirror and
 * reads integer literals only — so the equality it stands for is asserted here instead. */
#if OS_VDI_DEFAULT_FILL_INTERIOR != VDI_FILL_HOLLOW
#error "the default fill interior is no longer VDI_FILL_HOLLOW"
#endif

/* Service one `trap #2`. Reads the parameter block at `pblk` in `mem`, writes the modeled outputs,
 * and returns 1 if the call is modeled, 0 if it is not — an unmodeled opcode must be REFUSED by the
 * caller, never diffed against a fabricated result. `event` reports the call's off-image effect (see
 * os_event_t); it is always written, with OS_EVENT_NONE when there is none. Defined in ../src/gem.c
 * and compiled into both sides. */
int gem_dispatch(uint8_t *mem, uint32_t d0, uint32_t pblk, os_event_t *event);

/* Does a serviced call of this shape touch the harness-poked block? True for every VDI call — they
 * all read or write the VDI state block, which lives inside it — and false for the AES, whose four
 * modeled opcodes touch only the caller's own arrays. shim.c tallies on this so the poked-input
 * guard covers the VDI exactly as it covers Bconin (TRAP_MODEL.md, Phase 12). */
static inline int gem_touches_poked_input(uint32_t d0) { return d0 == GEM_VDI; }

/* Record whatever off-image effect a serviced call had. The candidate's half of the ledger; the
 * oracle's shim keeps its own mirror and does not call this. */
static inline void os_gem_note_event(const os_event_t *event) {
    if (event->kind != OS_EVENT_NONE) g_os_event(event->kind, event->value);
}

/* The oracle's and a trap-glue reconstruction's door: subsystem in `d0`, parameter block in `pblk`. */
static inline int os_gem_trap(uint8_t *mem, uint32_t d0, uint32_t pblk) {
    os_event_t event;
    if (!gem_dispatch(mem, d0, pblk, &event)) return os_refused(0);
    os_gem_note_event(&event);
    return 1;
}

/* ...and the one-argument door for a reconstruction that fills the VDI parameter block and calls the
 * VDI directly, rather than transcribing the original's `d0 = 0x73; trap #2` glue. Same code, same
 * block, same image writes as the oracle's trap. */
static inline int os_vdi(uint8_t *mem, uint32_t pblk) { return os_gem_trap(mem, GEM_VDI, pblk); }

/* ...and the AES's, for symmetry: a reconstruction reading as `os_aes(image, apb)` says which
 * subsystem it means without spelling a magic 0xc8 at every call site. */
static inline int os_aes(uint8_t *mem, uint32_t pblk) { return os_gem_trap(mem, GEM_AES, pblk); }

/* ---- BIOS console input (Bconstat 0x01 / Bconin 0x02) --------------------------------
 * Only the console device is modeled: a keystroke on any other BIOS device would have to be
 * invented, and the contract is to refuse rather than answer wrongly. The pending keystroke is
 * the harness-poked state above, so one poke is one keypress — Bconin CONSUMES it (clearing
 * OS_CON_PENDING), the way the real console does, so a polling loop sees exactly one key. */
#define OS_BIOS_DEV_CON  2       /* BIOS device 2 = CON: (the screen/keyboard console) */
/* ...and device 4 = the IKBD's serial line. A byte written there is a COMMAND to the 6301 keyboard
 * processor (reset, mouse off, joystick reporting) — off-image by definition, so BIOS Bconout to it
 * is a ledger entry rather than an image effect. Every other device is refused; see TRAP_MODEL.md,
 * "Phase 13". */
#define OS_BIOS_DEV_IKBD 4
#define OS_BCONSTAT_READY 0xffffffffu   /* Bconstat: -1L = a character is waiting, 0 = none */

/* Bconstat(dev) -> *out. Returns 1 if modeled, 0 for a device the model has no state for. */
static inline int os_bconstat(const uint8_t *mem, uint16_t dev, uint32_t *out) {
    if (dev != OS_BIOS_DEV_CON) return os_refused(0);
    *out = be32(mem + OS_CON_PENDING) ? OS_BCONSTAT_READY : 0;
    return 1;
}

/* Take the pending keystroke from the console, if there is one: 1 and *out on success, 0 when the
 * device isn't the console or nothing is staged. NOT a refusal in itself — "no key" is a legitimate
 * answer for the non-blocking os_crawio below, and only os_bconin turns it into one.
 *
 * The head of the staged WALK: OS_CON_CHAR is what this returns and OS_CON_QUEUE holds the keys
 * behind it, so taking one shifts the queue up by an entry and decrements the count.
 *
 * A COUNT THE MODEL CANNOT HOLD IS ONE KEY. OS_CON_PENDING's contract has always been "nonzero = a
 * character is waiting", and a hand-written poke dict may put any nonzero longword there (Joust's
 * test_os_traps.py does); the queue refines it without replacing it, so a count above
 * OS_CON_QUEUE_MAX is read as that older spelling and served as a single keystroke. That keeps the
 * one-key path writing exactly the one word it always wrote — which matters under a program that
 * covers this block, where every other longword in it is the game's own code. */
static inline int os_console_take_key(uint8_t *mem, uint16_t dev, uint32_t *out) {
    uint32_t queued = be32(mem + OS_CON_PENDING);
    if (dev != OS_BIOS_DEV_CON || !queued) return 0;
    *out = be32(mem + OS_CON_CHAR);
    if (queued < 2 || queued > OS_CON_QUEUE_MAX) {  /* the last key, or the flag spelling */
        wr32(mem + OS_CON_PENDING, 0);
        return 1;
    }
    /* Shift rather than carry a head index: the queue is seven entries at most, and one more field
     * in the poked block is one more thing for a case to stage half of. */
    wr32(mem + OS_CON_PENDING, queued - 1);
    wr32(mem + OS_CON_CHAR, be32(mem + OS_CON_QUEUE));
    for (unsigned i = 1; i < OS_CON_QUEUE_MAX - 1u; i++)
        wr32(mem + OS_CON_QUEUE + (i - 1) * 4, be32(mem + OS_CON_QUEUE + i * 4));
    wr32(mem + OS_CON_QUEUE + (OS_CON_QUEUE_MAX - 2u) * 4, 0);
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
 * character swallow the keystroke a later Bconin is waiting for. It IS console output, so it takes
 * the same OS_EVENT_CONOUT ledger entry Cconout takes — the one thing that can tell a reconstruction
 * which prints from one which does not. BuggyBoy's eight sites all pass OS_CRAWIO_READ (all
 * `move.w #$ff,-(a7)`) and Joust issues no Crawio at all, so only the read path is exercised by a
 * game today; the direction is still honoured rather than assumed.
 *
 * BuggyBoy's candidate (src/input.c check_abort, src/os.c console_scancode) does not call this; it
 * returns OS_CRAWIO_RESULT unconditionally. That agrees with the oracle byte for byte while no test
 * stages a key — which is every BuggyBoy test, none of which pokes OS_CON_PENDING — and if one ever
 * does, the two sides differ in D0, i.e. the divergence is loud rather than silently absorbed. */
#define OS_CRAWIO_READ 0x00ffu   /* Crawio's argument for "read"; anything else is a char to write */

/* The READ direction alone, named because the ORACLE needs exactly this half: `oracle/shim.c` keeps
 * its own ledger and does not link the candidate's, so it services the write direction itself and
 * calls this for the read — rather than re-typing the take-a-key line, which is the model. */
static inline uint32_t os_crawio_read(uint8_t *mem) {
    uint32_t key;
    /* os_console_take_key, not os_bconin: an idle console is a RESULT here, not a refusal, so it
     * must not reach the tally that os_bconin's blocking-read refusal feeds. */
    return os_console_take_key(mem, OS_BIOS_DEV_CON, &key) ? key : OS_CRAWIO_RESULT;
}

static inline uint32_t os_crawio(uint8_t *mem, uint16_t w) {
    if (w == OS_CRAWIO_READ) return os_crawio_read(mem);
    os_cconout((uint8_t)w);                         /* console output: a ledger entry, no key eaten */
    return 0;
}

/* ---- GEMDOS console input: Cconis (0x0b) / Crawcin (0x07) / Cnecin (0x08) -------------------
 * The SAME one staged keystroke Bconstat/Bconin/Crawio serve, through GEMDOS's door rather than the
 * BIOS's — deliberately one model and not a second, disconnected one, so a program that polls with
 * `Cconis` and reads with `Cnecin` (the idiom Bubble Ghost uses everywhere) sees exactly the key a
 * case staged, once. GEMDOS's console calls take no device argument, so unlike the BIOS pair there
 * is no device to refuse.
 *
 * Cconis(): -1L if a character is waiting, 0 if not. It only LOOKS — a poll loop may run it as many
 * times as it likes — and it is the non-refusing half of the pair, exactly as Bconstat is. */
static inline uint32_t os_cconis(const uint8_t *mem) {
    /* OS_BCONSTAT_READY, not a second constant: "a character is waiting, reported as -1L" is one
     * fact, and two spellings of it could drift. */
    return be32(mem + OS_CON_PENDING) ? OS_BCONSTAT_READY : 0;
}

/* The BLOCKING read behind both Crawcin and Cnecin. Consumes the staged key and returns 1; with
 * nothing staged it REFUSES, for os_bconin's reason — the real call waits for a keypress and there
 * is nothing here to wait for, so any answer would be fabricated. Never spins: a model that looped
 * would hang the oracle instead of failing it. */
static inline int os_conin_blocking(uint8_t *mem, uint32_t *out) {
    if (os_console_take_key(mem, OS_BIOS_DEV_CON, out)) return 1;
    return os_refused(0);
}

/* Crawcin (0x07) and Cnecin (0x08) are ONE model. On a real machine they differ in what they do
 * BESIDES returning the key: Cnecin honours ^C/^S/^Q and Crawcin does not, and neither echoes. The
 * model has no signal delivery and no flow control and does not echo either, so the two are the same
 * function here; they keep separate names so a reconstruction still reads as the call the original
 * made, and so the day one of them grows a difference there is a place to put it. See
 * TRAP_MODEL.md, "Phase 13". */
static inline int os_crawcin(uint8_t *mem, uint32_t *out) { return os_conin_blocking(mem, out); }
static inline int os_cnecin(uint8_t *mem, uint32_t *out)  { return os_conin_blocking(mem, out); }

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
/* WHY 32 AND NOT 8. The table held eight entries while the games that used it opened one or two
 * files; Zynaps's boot opens about thirty in one straight line (`_start` @ 0x10000 makes 22
 * `load_file` calls before 0x10814, and each level section loads five more), and 0x101ba is where
 * the ninth would have been — a wall in that project's STATUS.md rather than a seam in the program.
 * Thirty-two is the next power of two above what the longest known boot needs, and the two regions
 * it has to fit between are checked below rather than left to arithmetic in a reader's head. */
#define OS_FS_SLOTS        32
#define OS_FS_NAME         16        /* name field width; filenames must be < 16 chars */
#define OS_FS_OFF_STAGING  16        /* u32: where this file's bytes live in the staging area */
#define OS_FS_OFF_SIZE     20        /* u32: current length in bytes */
#define OS_FS_OFF_CURSOR   24        /* u32: read/write position */
#define OS_FS_OFF_OPEN     28        /* u32: nonzero while a handle is open on this slot */
#define OS_FS_OFF_CAPACITY 32        /* u32: staging bytes reserved; os_fwrite refuses to exceed it */
#define OS_FS_ENTRY        36
#define OS_FS_FIRST_HANDLE 6         /* GEMDOS handles 0..5 are reserved; files start here */

/* THE TABLE MUST END BELOW THE STAGING AREA. It grew from 8 slots to 32 and could grow again, and
 * the failure it would then have is silent: entry N's bytes would be written over the first staged
 * file's, which os_fread would go on serving as if they were the file. A compile-time check rather
 * than a runtime one because both numbers are constants here — the harness's Python mirror is
 * pinned equal to them by test/test_os_memory_map.py, so this covers that side too. */
#if OS_FS_TABLE + OS_FS_SLOTS * OS_FS_ENTRY > OS_FS_STAGING
#error "the staged-file table overruns OS_FS_STAGING: fewer OS_FS_SLOTS, or move the staging area up"
#endif

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
    uint32_t size = be32(entry + OS_FS_OFF_SIZE);
    /* Bytes remaining. Written as a test rather than a bare subtraction because os_fseek may leave
     * the cursor PAST the length (a seek into the file's reserved capacity is legal, and is how a
     * program extends a file it is writing); the subtraction alone would wrap to ~4 GB and serve
     * the whole image as file content. */
    uint32_t n = cursor >= size ? 0 : size - cursor;
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

/* ---- GEMDOS Fseek (0x42) -------------------------------------------------------------------
 * The one accessor of the staged-file cursor the model never grew. `offset` is SIGNED (a seek
 * backwards from the current position or the end is ordinary), `mode` selects what it is relative
 * to, and the result is the new absolute position.
 *
 * THE BOUND IS THE FILE'S RESERVED CAPACITY, NOT ITS LENGTH. Seeking past the end is legal on real
 * GEMDOS and is how a program extends a file it is writing, so a position in (size, capacity] is
 * served and os_fread answers 0 bytes there. Past the capacity there is no staging space at all —
 * the next file's bytes begin — and a negative position is not a position, so both refuse rather
 * than clamp: a clamp would hand the program a cursor it did not ask for and go on serving reads
 * from it.
 *
 * A REFUSAL IS NOT AN ERROR RETURN. Real GEMDOS answers a bad seek with a negative error code, and
 * a C library's `lseek` has a fallback path for exactly that; the model cannot tell the two apart,
 * so it refuses the RUN (loudly, naming the call) instead of fabricating an error code whose value
 * it would be inventing. See TRAP_MODEL.md, "Phase 13". */
#define OS_FSEEK_FROM_START   0
#define OS_FSEEK_FROM_CURRENT 1
#define OS_FSEEK_FROM_END     2

static inline int32_t os_fseek(uint8_t *mem, uint32_t offset, uint16_t handle, uint16_t mode) {
    uint8_t *entry = os_fs_entry(mem, handle);
    if (!entry || be32(entry + OS_FS_OFF_OPEN) == 0) return os_refused(-1);
    int64_t base;
    switch (mode) {
    case OS_FSEEK_FROM_START:   base = 0; break;
    case OS_FSEEK_FROM_CURRENT: base = be32(entry + OS_FS_OFF_CURSOR); break;
    case OS_FSEEK_FROM_END:     base = be32(entry + OS_FS_OFF_SIZE); break;
    default:                    return os_refused(-1);
    }
    /* 64-bit, so that neither the sum nor the signed offset can wrap before it is bounded: both
     * come off the emulated program's stack. */
    int64_t pos = base + (int32_t)offset;
    if (pos < 0 || pos > (int64_t)be32(entry + OS_FS_OFF_CAPACITY)) return os_refused(-1);
    wr32(entry + OS_FS_OFF_CURSOR, (uint32_t)pos);
    return (int32_t)pos;
}

#endif /* BB_OS_H */