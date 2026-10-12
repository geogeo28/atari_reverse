# Reconstruction status — TOS 1.02 US — ARCHIVE

**History, split out of `STATUS.md` on 2026-10-11 at `9808780`.** Closed waves' entries, moved here VERBATIM and in
their original order. NOT MAINTAINED AND NOT RE-DERIVED: its counts, ratios and line numbers are those of the day
each entry was written, and "above" / "below" in an entry mean the wave log as it stood then. ONE SENTENCE IS STILL
HELD BY A TEST and is corrected in place if its count moves: "THE 14 TIER 1-ONLY CASES of those handlers", in band 5
wave 2's slice E (`test_aes_ctlmgr.py`, `THE_LEDGER_S_ARCHIVE`). The ledger — the Components table, the verified
rows, the suite line, `* **Next**`, the AWAITING list and the current wave's entries — is `STATUS.md`. A wave's
entries are appended here when the wave closes.

## Wave log — Wave 1 (2026-09-13) through AES band 5 wave 2 (2026-10-10)

* **Wave 1 (2026-09-13/14)** — three agents on disjoint paths, each reviewed by eight finder angles + a
  verifier, fixed, and committed by the orchestrator: (1) Ghidra bootstrap + `COMPONENTS.md` (the
  Line-F call mechanism, the a5 pin, 1,292 functions); (2) the kit's ROM mode + the boot snapshot +
  `Random`/`Giaccess`; (3) the rebuilt ROM image, boot surface, TOSTEST and TOSBENCH. Review found
  real defects in all three (a mask test that could not detect what it claimed, an unguarded stack
  band, I/O reads answered 0 silently, a stub at 50 Hz on an NTSC ROM, a benchmark that graded a
  failed workload "within the bar"). Parked from review: the kit-wide `OS_IMAGE_SIZE` limit
  (TRAP_MODEL.md), extracting a shared engine for LineAResolve/LineFResolve, deriving `gen_seeds.py`'s
  tables from the dispatcher signatures, and `projects/flyingshark/tools/extract_audio.py:155`
  catching only `(OSError, ImportError)` around its kit import (its siblings also catch `RuntimeError`).
  Parked from wave 2: `tools/test_hw_portability.py` has three PRE-EXISTING reds at HEAD (stale published
  figures for Wonder Boy's committed portability scan: at_risk 22/3658 vs the asserted 23/3888, 1 vs 2
  seeded-hardware writes) — fixing them means re-running that scan and re-publishing its numbers with the
  record that accounts for the move; the PSG-block pin that this wave moved to `os.h` is fixed (53 of 56).
* **Wave 2 (2026-09-14)** — three agents in parallel, each through the eight-angle review + verifier +
  fix cycle: (1) **Tier 3's numerator** — `tools/recreate_kit/rom_bench.py` + kit.mk's `$(BENCH_*)` rules +
  `bench/tier3.py` + `test/test_tier3.py`; rows are DERIVED from `test_boot_snapshot.VERIFIED_CASES`, so a
  verified function with no row is red (`tier3.UNPRICED`), STATUS's cells are pinned to `build/bench/tier3.txt`
  by `test_status.py`, and the second differential compares all four off-image streams and every refusal
  tally. (2) **the declared I/O map** (Phase 15) with `Getrez` as its first consumer. (3) **BIOS wave 1** —
  16 RAM-only BIOS/XBIOS leaves (the `## Verified — bios` section and 8 xbios rows above). Review found:
  host-only asserts that compiled away into fabricated returns on target (now `recreate_not_reconstructed`
  halts on both builds), a Supexec signature that was not the ROM's frame, a Cursconf return type that
  could not express two arms' `moveq #0`, Giaccess's missing interrupt-mask bracket (88 % of its measured
  speed-up — now `ipl.h`, 0.39 → 0.60), a kit make rule that silently disabled the numerator, and the
  stack-band guard from befc249 breaking Bubble Ghost (Alcyon writes its arguments back) and Wonder Boy
  (blits to the image's last word) — fixed by one formula: the band ends at the frame area and everything
  above it is COMPARED.
* **The Tier 3 finding, and the decision.** 17 of 30 measured rows are over the 1.10 bar and none is a
  reconstruction defect. At leaf scale one instruction is the whole ratio (Drvmap: 32 → 48 cycles = 1.50x),
  and three mechanisms account for every acceptance, each recorded in `bench/tier3.py`'s `PERF_ACCEPTED`
  with its measured cycles: **(A)** the C ABI's `uint8_t *image` load (`movea.l 4(sp),a0`, 12–16 cycles)
  where the ROM's dispatcher zeroes a5 once for every routine — a lever for the SHIPPED build (cores
  compiled with the image base a link-time 0), not for the C; **(B)** the Bcon* device dispatch as a
  compare chain under `-fno-jump-tables` vs the ROM's `jmp (a0)`; **(C)** Cursconf's arm selection vs
  `jmp TABLE(pc,d0.w)` — 2.29x, 104 → 238 cycles, the first lever worth a wave. Decision: the bar stays
  at 1.10 as the *ratio* instrument; acceptances carry their cycle deltas; the bar's shape for leaves (an
  absolute slack beside the ratio) is decided when the dispatcher wave exists to price a whole trap call.
* **Wave 3 (2026-09-15), BIOS wave 2** — four agents on disjoint sets, each through the finder/verifier/fix cycle:
  (S) the XBIOS screen + sound leaves (Physbase, Setscreen two of three arms, Setpalette, Setcolor, Vsync under Phase 8,
  Dosound, Setprt, Ongibit/Offgibit over Giaccess); (M) the MFP/timer/IKBD/serial XBIOS (Jdisint/Jenabint, Mfpint as a
  slice + the composed core candidate-only, the timer programmer's five clears, Rsconf, Ikbdws/Midiws, Kbdvbase, Initmous
  from the disassembly; Xbtimer's install arm with the RAW table byte); (I) the four interrupt handlers (HBL, VBL, timer C
  with the whole Dosound interpreter, ACIA) through a machine-entry case shape; (D) the trap #13/#14 dispatcher as
  `src/bios/trap.S`, proved by the numerator's TRANSCRIPTION differential (the whole register file required equal) and a
  byte pin against the ROM. Review found: Vsync sampling before the unmask (a one-frame-early return no tier can see);
  `void` cores clobbering a D0 the ROM preserves (Ongibit/Offgibit/Setscreen/Setpalette/Jdisint/Jenabint/Mfpint/Getmpb);
  Xbtimer entering Mfpint PAST its mask; a signed→unsigned branch swap in the transcription surviving every case (the byte
  pin); the ISR cores with no entry stubs (a C handler cannot sit on a vector); the staged caller in both bench columns
  (26 % leniency on the dispatcher rows, now `shared_entry`); the IKBD settle loop 14 % short of the ROM's elapsed time.
* **The leaf bar, decided.** A whole `Bios(10)` call is 496 cycles, 93.5 % of it the dispatcher; every mechanism-(A)
  leaf is 3–7 % of a real call. `bench/tier3.py` now applies the LEAF RULE: an (A)-only trap leaf is accepted when its
  excess is ≤ 40 cycles AND ≤ 7.5 % of (the measured full-dispatch cost, 464, read off the dispatcher rows + the leaf's
  own cost); nine leaves fall under it, `isr_vbl`'s +94 does not and keeps a written entry. The transcription rows are net
  of the staged caller on BOTH columns. Mechanism (I) — the ROM's entry glue in the original's column only — is retired
  by the ISR entry stubs (see the bios rows).
* **Kit items wave 3 named, and what became of them.** BUILT in wave 4 (below): the WRITE-THROUGH arm of the declared
  I/O map (a stored byte replaces the declared one for later reads — it unblocked Mfpint's enable half, the timer
  programmer, Xbtimer and Rsconf's baud arm), and the `schedule` door on `run_bench` with the 7th `VERIFIED_CASES`
  field (Vsync's Tier 3 row). BUILT in wave 5 (below): the declared ORDERED SEQUENCE per address (TRAP_MODEL Phase 16)
  — GPIP's second loop pass and Bcostat's declared bytes are its consumers; the ACIA data list per read and the FDC
  status are describable by it now and are deferred on their own evidence, not on the model. STILL NOT BUILT: the
  door's OTHER half, a registry of SLICES with a `stop_pc` for a routine whose arguments no `CALL` form can spell —
  which is why `$fc25b0` is verified and unpriced; a cross-stream order between image stores and hardware writes
  (Initmous mode 0). WAVE 6 BUILT NOTHING KIT-SIDE: the ACIA input chain and Bconout's six drivers were reconstructed
  entirely on the doors waves 4 and 5 opened (write-through, the read-triggered schedule, the declared SEQUENCE), and
  the one registry gap wave 6 opened was this project's own — `bench/tier3.py` could not price a routine reached
  through a RAM vector — and its review closed it with a third `_routine` relation (`VECTOR_ROUTINE_NAMES`), five rows
  and one deferral (see `## Not reconstructed, and why`).
  Parked from review: `test/trap.py`'s TRAP_BAND at SCRATCH+0x800 overlaps Supexec's staged decoys at +0x800/+0xa00
  (different cases, never staged together; `isr.py` asserts its own band clear of both) — move D's band. Set I's C cores keep
  the C ABI's `rts` entry as their own Tier 1 instrument beside the `.S` entry rows.
  Parked from the wave-4 review: `src/xbios/acia.c`'s two unbounded status spins are the same hole class as the timer
  programmer's was (a mis-addressed ACIA status hangs pytest rather than reds) and are left faithful for now; the
  trigger-door table (`TRIGGER_DOORS` + `triggers_not_runnable_at`) as a follow-up; `tier3`'s `RegArg` generalization, so
  `$fc25b0` can be priced at its own entry rather than only inside its callers; `VERIFIED_CASES` as a `NamedTuple` with
  defaults, now that the tuple is seven fields wide; the `os.h` I/O map as one struct rather than four parallel arrays;
  and a sharper refusal for an RMW helper (`hw_bset8`/`hw_bclr8`/`hw_and8`) aimed at a DECLARED address — today it reds on
  the Phase 10 value and the Phase 15 read stream, which is a correct red pointing one layer away from the cause.
  Parked from the wave-5 review: Zynaps's `ikbd_acia_isr` loop can now be modeled (lists on `$fffc02` and `$fffa01`) —
  deliberately NOT revisited, it is the control this model is measured against; `tools/hw_portability.py` knows nothing
  of sequences (a sequenced read is still classified by the model that OWNS the address); and `emu.io_seq_entries` has
  no memo, which is asymmetric with `io_seed_entries`.
* **Wave 4 (2026-09-15), the two kit doors wave 3 named** — two agents on disjoint doors:
  (A) **the WRITE-THROUGH arm of the declared I/O map** — `emu.write_through(byte)` is an `io_seed` VALUE rather than a
  second door, so a case declares which registers read back what was stored; every store the candidate makes goes
  through one `hw_write`, which is what makes the two sides' ledgers comparable at all. Its honest limit is written
  down: IPRA/IPRB/ISRA/ISRB are WRITE-TO-CLEAR on the real 68901, and the model's plain read-back claim holds only
  because every store these routines make is a pure `and` clear — found by the refusal naming `$fffa0b`, not by
  reading the datasheet first. The timer DATA register is a reload latch, which is why the programmer writes it and
  reads it once: the fifth clear STOPS the timer, pinned as a run-order assertion rather than as a comment. With it:
  `Mfpint` whole, the MFP timer programmer whole, `Xbtimer` (both arms) and `Rsconf`'s baud arm — the four rows above.
  The programmer's spin is faithful on target and CAPPED off target (`MFP_VERIFY_PASSES`, ending in `os_refused(0)`),
  because a mis-addressed register makes it never agree — which on target is the ROM's own hang and in pytest was a hung
  worker rather than a red. That closes the row's last mutation: 8/8.
  (B) **the SCHEDULE DOOR on `run_bench`** — a new `OS_SCHED_AT_READ` trigger keyed on the Nth read of the WAIT
  ADDRESS, because a PC belongs to one build and the cross-compiled column has nothing at the ROM's; the 7th
  `VERIFIED_CASES` field carries it, and `rom_bench._vet_same_wait` compares the two runs' reads per address so a
  build that spins differently cannot be priced as if it spun the same. `Vsync` is priced at 0.97 / 0.92 over two
  arrival counts, both PINNED UNDER the bar so that a vanished `ipl.h` bracket reds (measured 0.64 / 0.75 with it
  deleted). Phase 8's one aliasing hole is now measured in its Tier 3 form as well: a double-reading build agrees
  with the original at every EVEN spin count, so `PRICED_SPINS` holds an odd one.
  Review found: a stale candidate `.so` passing the ABI probe and segfaulting on the new `g_io_reset` (now
  `g_io_writeback_count` in the probe list + an `nm` pin); the timer programmer's faithful spin hanging pytest on a
  mis-addressed register (host-only pass cap ending in a refusal; the HUNG mutant now reds, 8/8); the bench came-due vet
  firing on a door stop and never on a resume (moved into `_bench_result`, pinned through the real door); a duplicated
  bench installer and never-came-due sentence; the per-byte store loop spelt on both shores (now one `os_io_store`);
  `baud_chip` indexing Python literals where its docstring claimed the image; a tautology where the odd-spin-count claim
  should be. Refuted: the RMW helpers latching a fabricated half on a write-through byte — two unconditional vets
  (Phase 10 value, Phase 15 read stream) already red it; a documented limit, a sharper refusal parked.
* **Wave 5 (2026-09-16), the DECLARED SEQUENCE and the two routines waiting on it** — one agent, the kit door and both
  consumers together. THE DESIGN DECISION was ONE address-keyed table rather than a list per Phase-7 slot beside a list
  per Phase-15 address: the second shape is one rule written twice, which is the wave-4 review's own "one rule, one
  helper" class (the per-byte store loop spelt on both shores), so `os_io_seq_install`/`os_io_seq_next`/`os_io_seq_store`
  are shared verbatim by `oracle/shim.c` and `src/hw.c` and are consulted from INSIDE each read path — the owning model
  keeps its ledger, its wide-read refusal and its store rule while the list only decides which byte is served. THE TWO
  CONSUMERS: `isr_acia`'s TWO-PASS entry (`io_seed={MFP_GPIP: [asserted, idle]}`, the shape the handler is a loop for),
  and `Bcostat`'s whole table, where the sequence is what lets one case sweep both sides of a bit in an ordered stream.
  THE FLOPPY VBL FINDING: `$fc1bc4` is NOT a poll loop, which `src/bios/vbl.c` used to say. It makes two WORD reads of
  `$ff8604` that a list describes exactly — but BETWEEN them it calls `$fc1e60`, which selects YM2149 register 14 and
  READS PORT A BACK to merge the drive-select bits. That is Phase 6's direct-PSG read-modify-write, a path this project
  has never used (its only PSG door is the `Giaccess` trap), and a run reaching both would be refused by the mixed-path
  guard — so the floppy service stays halted for a floppy wave, on the PSG's account rather than the FDC's.
  `Bconin`'s two remaining arms stay halted, and WAVE 6 FOUND THIS SENTENCE WRONG THREE TIMES — twice in the wave and
  once more in its own review. PRT: (`$fc2104`) reaches the parallel port through `Giaccess` (not a direct PSG access)
  and then spins on GPIP bit 0 until it is ASSERTED (not until it clears), so a declared GPIP list describes it exactly
  — it is a DEFERRAL, not a limit. And AUX: (`$fc2150`) does NOT wait on a ring an interrupt fills, which is what the
  wave-6 integration re-wrote this sentence to claim: it is `rs232_ring_get` on the INPUT ring, which a case stages,
  plus a flow-control tail of a PSG write and this wave's own transmitter prime. Both are deferrals; see
  `## Not reconstructed, and why`. `Bconstat`'s own halt is unreachable on the captured
  machine (its three drivers are all ring readers and all three are reconstructed — `src/bios/bcon.c`'s header says
  "four", which `test_bios_bconstat.py` contradicts: devices 1/2/3 carry drivers, 0 and 4-7 the bare `rts`); it stays
  because the table is RAM.
  Mutation sweep 24/24, with ONE first-pass survivor: an EMPTY list, which Python refused at the door and C admitted —
  the two shores disagreed about a declaration neither had a byte for. Closed with a probe case that pins the refusal on
  both. Review found: the staleness refusal's formatter crashing on a list (now renders it and prescribes the remedy a
  LIST really has — the case's shape, since a mark is refused at the door and a longer list answers a store no better —
  pinned by a store-then-read over a sequenced address); the ACIA handler's host bound spelt as an `assert` that would
  abort the pytest worker (now the kit's `hw_poll8`/`io_poll8` primitive, the read plus the model's own "could I still
  serve it?", so there is no cap constant anywhere and `kit_candidate.c`'s two poll cores dropped theirs too — the
  over-read-by-one mutant still reds, now naming the read and the address); a list on a named slot skipping the
  double-claim refusal in `seed_split`; the public `refusal_hints()` missing the sequence hint, and that hint being a
  guess — it is now a fact from the candidate's own `g_io_seq_spent{,_addr,_index}`, the newest names in
  `harness._HW_LEDGER_ABI`; the wide-read span resolver spelt on both shores (one `os_io_resolve_span`, with
  `os_io_seq_has_next` for the three `cursor >= length` spellings and `os_io_seedable` now derived from
  `os_io_seq_seedable`; breaking the named-slot exclusion on the oracle shore alone reds `test_io_model.py`);
  `io_seq_entries` re-spelling `io_seed_entries`' three address rules (one `_vet_io_address`); the bench door's
  split/merge/split (`_bench_io_seed` now drops the routed named constants and hands the caller's own dict back); and
  both probes' candidate helpers resetting one declaration and not the other (one helper each, plus a
  `cand_sequence_does_not_leak` row on both). Parked: one per-address byte-source table with a kind and a length
  (constant = a length-1 repeating sequence) collapsing Phase 15/16's two encoders; `run_bench` installing all three
  seeded models per run so `_bench_io_seed` becomes the identity; `test_status.py` deriving the Components table's
  ratio-range cells (the bios cell had drifted to 0.62–1.96x unnoticed).
* **Wave 6 (2026-09-19), BIOS wave 3** — two agents on disjoint halves of the character-device surface, each through the
  finder/verifier/fix cycle:
  (K) **the ACIA INPUT CHAIN** — the six routines under the IKBD handler's two KBDVECS slots: both 6850 service entries
  and their shared body, the byte splitter that sorts IKBD from MIDI by `cmpa.l #$c76,a0`, the ROM's own `midivec`, the
  scancode arm and the key-into-the-IOREC arm. Two case SHAPES for `isr_acia` now: the staged one that isolates the
  handler, and a REAL-VECTOR one that leaves the captured machine's own `$fc29fc`/`$fc2a0c` in KBDVECS and declares the
  two 6850s instead — the first case in this project needing TWO declared SEQUENCES at once (`$fffa01`'s line and
  `$fffc02`'s bytes), which is what assembles a three-byte relative-mouse report over three passes of the loop. THE
  FINDING: every routine TOS installs in a RAM vector is entered with A5 = 0, which the ROM's handlers establish once
  with `lea 0,a5` and which `src/bios/isr.S` had been spelling as the pushed image argument instead. It is pinned as an
  OPERAND of every vector call in `include/staged_call.h` — one `suba.l %a5,%a5`, 8 cycles a call — and it has NO Tier 1
  surface: delete it and every differential stays green, which is why the rows that carry it are PINNED rather than
  accepted (mechanism (K) in `bench/tier3.py`). It also un-halted timer C's auto-repeat injection at `$fc2c42`, which is
  a real call to `kbd_queue_key` now. Mutation 16/16.
  (C) **`Bconout` and its six drivers** — the table walk, the two 6850 senders, the printer's whole YM2149 send, the
  RS232 output ring, and the VT52 CONSOLE: the six-state machine at `$4a8`, the control codes `$07..$0d`, every escape
  the ROM's three jump tables really implement, and the four screen routines reached through RAM vectors. FINDINGS: the
  printer's serial redirect is a BYTE `btst` on a WORD field and so reads bit 12, not bit 4 — `$0010` prints and `$1000`
  redirects; the hold-off's `bcs` is UNSIGNED and the BUSY timeout's `blt` SIGNED, proved by a failure stamp ahead of
  the clock and by a clock half the longword range on; the escape SET is read out of the ROM's own tables rather than
  from a VT52 manual (nine table entries point at a bare `rts`); the cursor lock is a DEPTH whose unlock leaves that
  depth in D0, so `ESC l` puts the cursor in column `depth`; and the BLITTER screen set halts, the captured ST holding
  the CPU set. The console's POISON pass is OFF and stays off with its reason written down: the bytes the oracle writes
  ARE the driver's control state, so poison cannot be told from output — `vt52.canary` stands in for the pixel cases.
  `Cursconf`'s arms 0/1 stopped halting with it, and its `blink` row fell 2.29 -> 1.65. Mutation 21/21.
  STILL HALTING: `Bconin(PRT:)` and `Bconin(AUX:)`, the four blitter screen routines, `$fc4a42`, a console of six or
  more planes, and the floppy VBL — each with its reason in `## Not reconstructed, and why`.
  Review found: the console's cursor clamp transcribed as a SIGNED COMPARE where the ROM's `cmp.w / bpl` tests the N
  flag of the word difference — two different functions at the overflow window, and now driven there
  (`m68k_idioms.h`, `word_difference_is_negative`); the two `isr_acia, real vectors` rows pricing the ROM against the
  ROM — the cross-compiled handler jumps through KBDVECS too, so the six new cores were invisible to the gate as well
  as to those rows — closed with a third `_routine` relation, five priced rows and `acia_take_byte` deferred; the
  scroll and the clear running at 2x for a reason the compiler CONTRADICTED, respelled to the ROM's own loops (scroll
  2.03 -> 1.03, clear 2.24 -> 1.49) and the rows re-pinned; the IOREC ring step, the Dosound list plant and the
  differential runner each spelt three times by the wave's two halves (now `include/bios/iorec.h`, `include/sound.h` and
  `test/acia.py`); the A5 pin spelt five times in `staged_call.h`; and the `Bconin(AUX:)` and printer wait-site
  comments both describing something the code does not do.
  Parked: `-ffixed-a5` plus the ROM's own `suba.l a5,a5` in each `isr.S` stub as the deeper A5 lever (mechanism (K)) —
  zero per-call cost, one fewer allocatable address register everywhere, unmeasured; a kit `poison_keep=` span so a
  control-state routine can keep the automatic attribution pass (`vt52.canary` is the interim, hand-placed in five
  cases only); the poll primitives refusing the Nth re-read of a CONSTANT past `OS_SCHED_POLL_MAX`, because a spin on a
  constant that never satisfies its test hangs a worker today; `tools/addrs.py` binding ONE header (`addrs.h` is every
  wave's merge hotspot); a Tier 3 row for the console's SCROLL DOWN (`ESC I`/`ESC L` reach it, but only through Tier 1);
  timer C's auto-repeat injection has no registry entry and no Tier 3 row of its own; the console clear's two EDGE
  groups a scan line, which the ROM masks with `and.l`/`or.l` pairs where this fills a word at a time (the 1.49 row's
  remainder); and a process note — never run a mutation sweep in the background while editing, because a killed sweep
  skips its `finally` and leaves the mutation in the tree (it happened once this wave).
* **Wave 7 (2026-09-19/20), GEMDOS wave 1** — three agents on disjoint paths, each mutation-swept and
  merged by the orchestrator: (1) the `trap #1` ENTRY (`src/gemdos/trap1.S`, a byte-identical
  transcription), the dispatcher and the RAM-only leaves; (2) the CHARACTER-DEVICE group
  (`console.c`, fifteen leaves); (3) the MEMORY MANAGER (`memory.c`, the three trap leaves and the
  five routines under them). 36 verified rows and 98 new Tier 3 rows in one component.
  FINDINGS: the trap #1 entry frames into the calling process's own BASEPAGE rather than a shared
  save area, which is what lets `Pterm` unwind the PARENT; the dispatcher's descriptor word is a
  frame CLASS (4/8/12/14 bytes) plus bit 7 "this argument is a standard handle", with the
  rewrite/redirect split hanging off it; the YEAR bound of `Tsetdate` and the HOUR bound of
  `Tsettime` are DEAD CODE in TOS 1.02, both through a sign extension, and both are reproduced with
  a case; GEMDOS's clock is RAM advanced by an `etv_timer` hook (`$fc9cc0`), which is why
  `Tgettime`/`Tgetdate` are pure RAM reads; the console group's device model is `handle + 3`, with a
  typeahead queue between GEMDOS and `Bconin`, `Cconws` sign-extending bytes where `Cconout` does
  not, an empty `Cconws` returning the handle in D0's low word, and the `Cconrs` editor's real
  nine-key table whose ninth key is 0 and shares the DEFAULT arm; and the memory manager is NEXT-FIT
  with 2-byte rounding over a 16,000-byte record arena at `$2a6e` whose exhaustion is TOS 1.02's
  "out of memory descriptors", coalescing FORWARD then BACKWARD, EGSBF is −67 and not −37, ENSMEM is
  never used, and `Mshrink` on a spent pool writes a descriptor THROUGH NULL into the reset vectors
  and reports success. Mutation: G1 15/15, G2 20/20 (+2 coverage holes closed), G3 41/42 — the one
  survivor is the null guard on the forward merge, which no producible pool can reach.
  STILL HALTING: the dispatcher's three unreconstructed arms (redirected handles, handle resolution,
  the device-name arm of `Fopen`/`Fcreate`), the accepting arm of both clock setters, and the
  `Pterm` group — each with its reason in `## Not reconstructed, and why`.
  Process notes: agents' mutation sweeps against one `build/` serialise badly, and a killed sweep
  leaves a MUTANT BLOB behind — `build/bench/bench.*` must be deleted with the `.so`, not just the
  `.so` (it bit an agent this wave, and the orchestrator's gate now clears both before every run).
  Parked: `tools/addrs.py` binding MULTIPLE headers (this wave ran both conventions at once and the
  merge settled it one way — ROUTINE ADDRESSES and function numbers in `addrs.h`, where the
  registries key on them, and STRUCTURES in the group's own header — but the parser still reads one
  file, so a group with its own header still binds it by hand); a SHARED `AddressHook` class for
  `test/gemdos.py`, `test/isr.py` and `test/acia.py`, which are three copies of one
  dispatch-by-address recorder; a KIT-LEVEL DECLARED TRAP-FRAME EFFECT, so that the `savptr` poke is
  one convention rather than one wave's note; `bench/tier3.py` as ONE registry (address -> name,
  role, table) instead of three maps consulted in order; a STAGING BAND registry, so a battery's
  band is allocated rather than asserted against its neighbours; and a PER-MUTANT TIMEOUT in the
  sweep scripts (a mutation that unbounds a loop is detected by hanging, which costs a worker).
  Review found: the TARGET-SIDE BIOS DOOR — the cores took no `trap #13` on the bench blob, so the
  measured GEMDOS rows were our leaf against the ROM's leaf-plus-trap and twenty-three of them sat
  over the bar on an acceptance; the target build now takes the ROM's own trap and all 27 console
  rows re-measured under it, `Dsetdrv` with them (it was UNPRICED). The DISPATCHER'S POP COUNT lived
  in D2 across a `jsr` into drivers that write D2 (`xconout_rs232`, the bell) — now D3, which both
  ABIs preserve, with D2 clobbered. The SPLIT read a stale `m_length` across `gemdos_pool_get`
  (unreachable; the ROM re-reads it). `p_run` was defined in two headers and the memory manager's
  eight routine addresses in none of them. The hook was copied from `isr.py` without its call cap.
  Three copies of the basepage accessor and six of "read a longword out of an image".
* **Wave 8 (2026-09-22), GEMDOS wave 2** — two agents on disjoint groups, each mutation-swept and merged by
  the orchestrator. (F) THE FILE SYSTEM, over a verification shape this project did not have: a STAGED RAM
  DISK — a FAT12 image at `$68000` (44 KB) and three 68000 stubs in `hdv_rw`/`hdv_bpb`/`hdv_mediach`, so the
  ROM's own file system and the cross-compiled cores BOTH take a real `trap #13` into the staged driver
  (`recreate/README.md` has the section). Eight cores: the buffer cache (`_bufl[0]` FAT, `_bufl[1]` dir AND
  data, MRU to the front, LRU at the tail, the media-change answer TRUNCATED to a word and a MAYBE re-reading
  the hit IN PLACE), the flush that writes a FAT buffer TWICE because `fatrec` names the SECOND copy, the
  data-span transfer, and the 8.3 name layer — where a bare `*` is NOT `*.*`. (P) THE PROCESS GROUP and the
  handle machinery under it, twelve cores: `Pterm` does NOT longjmp (it `jsr`s into the trap entry's epilogue;
  the termination record is the FILE SYSTEM's critical-error target, and wave 7 had this wrong in three
  places), `Ptermres` = release then terminate, the 75×10-byte handle table at `$8092`, `Fdup` copying the
  VALUE but not the reference count (a ROM defect, reproduced), `Pexec` modes 0/3/4/5 with 1 and 2 a GAP and
  two dead branches, the basepage clear running eight bytes past its own end, `$8066` proved to be
  per-DIRECTORY-NODE reference counts (wave 7 named it `GEMDOS_PROCESS_FLAGS` — wrong), and the Mega ST
  battery clock re-read once per process end. The dispatcher's handle-resolution arm (`$fc9924`) came with
  it, which moved `$fc973e` from 0.82-0.83 to 0.78-0.79.
  REGISTRY: `VERIFIED_CASES` grew an EIGHTH field, `stop_pc` — a CHECKPOINT row for a routine that never
  returns — read through one `test_boot_snapshot.fields()` so the hundred rows with nothing to say about it
  did not have to be rewritten; `bench/tier3.py` gained a PER-TRAMPOLINE slice cost (the dispatcher's stub is
  three instructions, `Pexec`'s two — built and PRICED by one builder since the fix pass, so a stub whose shape
  changes cannot keep an entry cost nobody ran) and lists checkpoint cases under the table instead of reddening
  on them. The MAKEFILE's snapshot rule stopped depending on the whole of `include/addrs.h`: it depends on a
  CONTENT STAMP of the two constants `tools/boot_snapshot.py` really reads, plus the ROM image — every wave
  edits that header, and two agents' `make`s raced on the 15-second re-capture (the losing one failed at
  `$cc46`).
  Mutation: F 25/27 (two EQUIVALENT survivors, both written down), P 16/16. Independent reviews inside both
  agents found real defects (a 32-bit `Mediach` compare where the ROM truncates to a word; an assert in the
  wrong order).
  THE RAM DISK IS A FOURTH TENANT OF THE FREE WINDOW AND IS NOT DECLARED IN `project.toml`, on
  purpose and measured: the kit's `_vet_tenancy` knows three bands and has no named-tenant door, and
  growing `staging_bytes` to cover `$68000..$73000` reds `test_gemdos_fs_disk.py::test_the_ram_disk_
  span_is_clear_of_the_three_declared_tenants`, whose own arithmetic requires the case band to END
  at `$68000` (measured at the merge). It buys nothing either: Tier 3's blob can only reach the disk
  by first crossing the case band at `$60000`, which `_vet_bands` already refuses, and the span's
  emptiness in the snapshot is that battery's own claim. The door that would make it a declaration
  rather than an arithmetic is a NAMED TENANT LIST in `project.toml` — parked kit-side.
  Parked: the DMD BUILDER (`$fc53c0`) is the file system's next step (LANDED in wave 9, and the staged descriptor
  PROVED equal to what it builds; `hdv_bpb` now has its caller, `$fc67de`); the Mega ST clock wants a THIRD I/O column beside `OS_IO_DECLARED_CONSTANT`/`OS_IO_WRITE_THROUGH`
  ("a register a store does not reach"), without which the plain-ST arm stays an oracle claim; the shared
  `AddressHook` — the RECORD-AND-REFUSE hook is copied FOUR times (`test/isr.py`, `test/acia.py`,
  `test/gemdos.py` and this wave's `test/gemdos_fs.py`) and the fix pass could only level the copies, not
  merge them, so it is a **HARD PRECONDITION for the next file-system wave**: the fifth copy is not to be
  written (LANDED 2026-09-25, see below); NETTING THE STAGED DRIVER out of the three disk rows (`gemdos_buffer_flush`/`_get`/`gemdos_rwabs_data`
  measure ~11k of stub against ~1-2k of core, see the note under the table) — a per-row `staged_entry` from a
  zero-count `Rwabs`; and a BENCH TRANSCRIPTION CASE for `Pterm`'s epilogue path, which is the only surface that
  would see the exit code's D0 pin (see `## Not reconstructed, and why`).
  Still open in this component: the FILE LEAVES themselves (`Fopen`/`Fcreate`/`Fread`/`Fwrite`/`Fclose`'s file
  arm/`Fseek`, the `D*` group, `Fsfirst`/`Fsnext`) and the dispatcher's REDIRECTED (`$fd328a`) and DEVICE-NAME
  (`$fc9aca`) arms, which are the same functions seen from the dispatcher's side.
  Review found, and the fix pass landed, nine things. CORRECTNESS: `Pterm`'s `jsr` into the trap entry's epilogue
  left D0 UNPINNED, where the epilogue's first instruction re-stores it as the parent's saved D0 — a target-only
  corruption of every exit code, pinned now as an asm input and recorded unpinned by any surface; the battery
  clock's probe read its two registers in ONE C expression, where `movep.w` reads +5 then +7 and the ledger
  compares the stream in order; `Fclose` HALTED on the whole arm both `bge`s fall into, where the ROM answers
  EIHNDL for the half of it that names nothing — which is exactly what `Fdup` of an unused standard handle
  leaves, so a process owning one could not terminate; and the 8.3 name battery's staging band sat ON TOP of
  `test/gemdos_console.py`'s (`staging.SCRATCH + 0x600`, both of its hand-written neighbour assertions still
  passing). MEASUREMENT: `gemdos_resync_clock` was ACCEPTED at 1.18 on a rationale that blamed the ordered
  ledger, which was false on target — the excess was two image OFFSETS swapped each pass; respelt as pointers it
  measures 1.04 with the same reads in the same order and the acceptance is deleted. STRUCTURE: the
  record-and-refuse hook's FOURTH copy served calls from outside a pass, and four copies of `final_image`
  dropped the overflow guard the fifth had; `$87cc` was defined under two names and three wave-7 "process table"
  constants had no user at all (deleted, and `test/test_addrs.py` now refuses a second name for one address);
  and two arms had no candidate-side case — the dispatcher's resolved-FILE fall-through and `Pexec`'s copy of
  the outer termination record. Every one of the four correctness findings and both coverage holes was
  RED-before / GREEN-after under a mutation of its own.
* **Harness (2026-09-25), the shared `AddressHook`** — the file-system wave's HARD PRECONDITION, landed. The
  record-and-refuse hook is ONE class in `test/address_hook.py` (with `bind_pointer`, the one place a `.so` function
  pointer is bound): dispatch by key; a PASS WITH AN END — `recording()` opens one around each candidate run and closes
  it in `finally`, and any call while none is open is refused; `calls` = the FIRST pass alone (a pass counter, so the
  attribution pass is served but not recorded); the `CALLS_MAX` cap (moved from `test/case.py`); and ONE lifecycle,
  `staged(effects, describe_refusals)`, which drops the table on exit and FAILS the case if anything was refused — the
  battery supplies the wording, so the check cannot be skipped. Its four copies are thin uses: `test/isr.py` and
  `test/test_xbios_supexec.py` through `staged_routines` (one projection, one message), `test/gemdos.py` through
  `bound_handlers` (was `bind_handlers` + a separate `assert_every_handler_was_bound`), `test/gemdos_fs.py` through
  `staged_disk` (a fixed `{Getbpb, Mediach, Rwabs}` table, so an unmodelled BIOS function is REFUSED where it was
  served as `Rwabs`). The wave-8 note had one copy wrong: `test/acia.py` never had one; Supexec's was the fourth and
  the weakest. `final_image` was already one helper. Review of the first merge (5 finders) found the pass was never
  CLOSED — a stray call after a case was appended to that case's `calls` and, in the two GEMDOS modules, SERVED out
  of its table; fixed, RED-before/GREEN-after. Mutation 15/15, and the pass-close, the exit refusal and the table
  drop are caught ONLY by the new `test/test_address_hook.py`, which drives the real Supexec door. Suites 2,485 /
  1 skipped, guarded the same (3,292 runs), Tier 3 table byte-identical.
* **Wave 9 (2026-09-25), GEMDOS fs wave 3 band 1 — the DRIVE, the I/O ENGINE and the RECORD LAYER.** 33 routines, three
  agents on disjoint files after a read-only call-graph map found the file system's one STRONGLY-CONNECTED COMPONENT:
  the FAT is read as a pseudo-FILE through the same transfer engine it serves ({`$fc7d2a` seek, `$fc6038`/`$fc5f44`
  FAT get/set, `$fc60f2` next_cluster, `$fc6218` xfer, `$fc5e9c`/`$fc5f1c` read/write}), terminating only because
  the FAT OFD's clusters are negative — so it was built as ONE unit. The record layouts (OFD/DND/DTA/directory
  entry, every field cited to a ROM instruction) landed in `include/gemdos/fs.h` FIRST so three agents shared one
  spelling; the map's guesses it refuted: OFD+0x14 is the HOLDING directory's DND, OFD+0x2c is not a chain, the open
  mode is never read, DND/OFD time and date are NOT byte-swapped. (A) `src/gemdos/fs_drive.c`: the DMD builder
  `$fc53c0` — the staged descriptor is now PROVED equal to what the ROM builds, which found the FAT pseudo-file's
  start at position 3 the staging lacked — and `open_drive` taking the ROM's own `trap #13` Getbpb on target, the
  path start, dot names, the component splitter. (B) `src/gemdos/fs_io.c`: the SCC plus `Fread`/`Fwrite`/`Fseek`;
  the dispatcher's file arm is now a full slice differential against the ROM's own leaves; the ROM's `-2(a6)` frame
  word has a host stand-in in the dropped stack band with a re-entrancy assert. (C) `src/gemdos/fs_records.c` +
  `fs_copy.c`: the three byte copies (one loop), the byte swaps, the DND/OFD makers over the pool in its three
  states, handle allocation, directory-cluster zeroing, name/path/DTA text. FINDINGS: odd FAT12 entries come back
  NEGATIVE for any value with bit 11 set (`asr.w #4`); `$fc6330` finishes the head cluster with the sector INDEX, so
  four-sector clusters transfer wrong at head indices 1 and 3; the allocator never uses the last two clusters; seek
  has no end-of-chain test on its last step; a zero-byte `Fwrite` dirties a sector; `$fc50fa` leaves `$8380[drv]`
  naming a freed DMD on failure; `$fc67de` never drops the old curdir's count; the second open's 12-byte copy runs
  two bytes into OFD_DMD. REVIEW (6 finders: C faithful to the asm everywhere) found the real defects at the SEAMS:
  `$fc7e24` COMPUTED its mask where the ROM indexes `$fd2fc8` by a SIGNED word — and A's builder yields log2 -1 for a
  zero sector size (RED-before/GREEN-after, now one `gemdos_bit_mask()` both files use, shifts modulo 64 through
  `asl_word_by`/`asr_long_by`); the builder read `fatrec` at entry where the ROM reads it after its stores (RED/GREEN);
  a runtime `fn` into an `"i"` asm constraint (now a macro); a zero `clsiz` dividing on the host (now a refusal);
  two surviving `dir_zero_cluster` mutants and its unpinned loop order (killed/pinned); and the duplication three
  concurrent agents make — a staged-disk run wrapper ×6 (now `gemdos_fs.run`), a second staging registry (now
  `staging.Registry`, and every fs tenant claims through `gemdos_fs.SPAN` — which found a transfer buffer overlapping
  the record slots), constants spelt in C and Python apart (now one parse of the fs headers), `D0_CALLERS_HIGH_HALF`
  ×3 (now the kit's `set_low_word`). Mutation: the bands 51/51, 58/58, 64/65; after the fix pass 182/184 over all
  three, the two survivors EQUIVALENT (the root name `clr.b` over a pool-cleared record; the split mask's `ext.l`,
  of which only the low word is stored). Unpinned: the disk-error/media-change longjmp arms; a FAT access at the
  FAT's last byte (a stale stack byte); an unknown copy address in `$fc6218`; the zero-`clsiz` divide; the `"i"`
  constraint (no build flag isolates it). Parked: a kit-level `poison_exempt` for machine-owned pointers (savptr,
  pool heads — five fs batteries run unpoisoned for that reason); the RAM disk and user buffer as `project.toml`
  tenants; `claim()` allocating addresses; running the pure-arithmetic routines without the whole staged disk.
* **Wave 9 band 2 (2026-09-25) — the DIRECTORY LAYER and the FILE LAYER.** Two agents: (D) `src/gemdos/fs_dir.c` — the search
  `$fc663c`, the walk `$fc696c` and `Fsnext`, over a staged directory tree; (E) `src/gemdos/fs_file.c` — close `$fc57ee`, delete
  `$fc7824`, `Fdatime`, and `Fclose`'s FILE arm in `handles.c`; `Dfree`/`Dgetpath` in a new `fs_leaves.c` (moved there by the fix
  pass so the drive layer stays at the bottom). FINDINGS: the DND tree is built as a SIDE EFFECT of searching, and a search from
  the mark answers the LAST DND MADE rather than the matched entry's; the walk's tail lands AT or PAST a missing component by how it
  missed; `$fd2fe8` is the mask table's two `$ffff` entries read as -1; a close flushes EVERY buffer of every drive, writing dirty
  ones and EMPTYING clean ones; OFD_DIRTY is never cleared; `Fdatime` has no OFD check; `Dfree` never counts the last two clusters;
  and a real TOS 1.02 DOUBLE FREE — `Fdup` gives the new descriptor its own count of one over the same OFD, so closing both frees
  the OFD twice: a self-looped pool chain and the same record handed out by the next two `pool_get`s, pinned by chained
  differentials. REVIEW (4 finders; C faithful to the asm) found the tests weaker than their claims: find_dir's sibling walk (the
  COMMON walk) and the known-name walk never crossed a link, the mark-raise signedness was unpinned, a Dfree case could not see
  what it named — each proved SURVIVED then killed by staged data — and band 2 had re-invented band 1's host frame word four times
  over three mechanisms: now ONE host-slot table in `include/gemdos/gemdos.h` (`GEMDOS_HOST_SLOT_*`, claim/release with a held mask,
  so nesting is ASSERTED) and one table-driven placement test; one leaf/dispatch-slice door with one table test over every fs leaf;
  `tools/addrs.py` reads `(-1)`. Mutation 114/116 (fs_dir 47/47, fs_file 41/42, handles 7/7, fs_leaves 14/14, shared 5/6): the
  survivors are the caller's unobservable second close in `delete_entry` and the held-mask assert (an equivalent guard, proven live).
  Unpinned: the NULL-OFD `Fdatime`; `$ff8`..`$ffe` chain ends in delete; `ofd_close`'s failing seek; `Fclose` on p_uft 1..5; a
  parent with children but no OFD; `Fsnext` on a garbage DND; Fsnext's re-read of p_dta after the search ($fc6e7e/$fc6ea0,
  equivalent on reachable data); Dfree/Dgetpath storing the resolved drive into their argument word (dropped band).
* **Wave 9 band 3 (2026-09-25) — the NAME and CREATE leaves.** `src/gemdos/fs_open.c` (sfirst, Fsfirst, Dsetpath, open, Fopen,
  Fattrib, Fdelete) and `src/gemdos/fs_create.c` (create, Fcreate, Ddelete, Dcreate) — 11 routines, two agents. FINDINGS: `create`
  DELETES an existing entry rather than truncating it and ignores the delete's answer, so a file another process holds gets a
  SECOND entry of the same name; `Dcreate`'s 50-byte OFD copy + close(6) unlinks every OFD opened earlier in the parent; `Ddelete`
  has no current-directory check and an EMPTY root makes its child walk run from address 28 forever; any position-0 search makes a
  fresh DND for every subdirectory it passes (only the walk moves DND_SCANNED), so a directory can carry duplicate DNDs;
  `Dsetpath("B:\X")` logs B: in but walks `\X` on the CURRENT drive, and the walk's own log-in can take the node slot Dsetpath just
  chose; `Fopen`/`Fdelete` answer EFILNF for a missing DIRECTORY; the $27 search attribute means Fopen/Fattrib/Fdelete never name a
  plain subdirectory or the volume label, yet `Fattrib` checks nothing and can clear a directory's subdirectory bit reached through
  its archive bit. REVIEW (3 finders; C faithful) found the Fopen mode tested as a byte by nothing (it is a WORD), a FABRICATED
  staging for Ddelete's EINTRN arms — now both reached by REAL call chains — and twins of committed helpers: the fix pass exported
  the drive prefix and node slots (fs_drive.h), descriptor_of/release_descriptor (process.h), next_entry, the walk flags and
  search attributes (fs_dir.h), ENTRY_BEHIND_POSITION and the open modes (fs.h), and gave the tests ONE `gemdos_fs.continued`
  (chaining one run's end state into the next — a real differential) and ONE `gemdos_fs.routine` door for unnumbered routines.
  Mutation 142/153, the 11 survivors argued equivalent or unreachable (listed in the rows). `path_start` 0.99 → 0.98 (the shared
  prefix parse inlined). Unpinned: the DISPATCHED Fopen/Fcreate — the dispatcher's device-name arm $fc9aca halts — which is the
  next step.
* **Wave 9 band 4 (2026-09-26) — the LAST of GEMDOS: `Frename`, the dispatcher's three arms, `Pexec`'s loader.** Three agents:
  `src/gemdos/fs_rename.c` (`Frename` $fc7af0), `src/gemdos/dispatch.c` (the REDIRECTED arms `$fd328a`, the DEVICE arm
  `$fc99bc`, the DEVICE-NAME arm `$fc9aca`, and the media-change helpers `$fc93f4`/`$fc9468` standalone — which unblocked the
  dispatched `Fopen`/`Fcreate` slices), `src/gemdos/pexec_load.c` (the loader and relocator `$fc85ea` with `$fc4b7c`'s clear,
  `Pexec` modes 0 and 3 end to end over synthesised PRGs). FINDINGS: a cross-directory `Frename` MOVES the entry (`$e5`, then
  `Fcreate` and a 10-byte tail copy — no FAT traffic) and never checks `Fcreate`'s answer, so a refusal reads a basepage byte as a
  handle and the file silently loses its name; its new-name check cannot see hidden/system/directory entries (duplicates);
  redirected `Cconout` writes the byte at `(char<<16)|$7ef4`, redirected `Cconrs` reads its maximum SIGNED (a buffer overrun),
  redirected `Cconin` ignores Fread's answer, `$fc9468` compares against the caller's A4 and never its argument; the loader
  takes `Fopen`'s mode from the high half of the CALLER'S D5, checks no `Fread`, bounds relocation only at chunk edges, leaves
  the file open on every error, and a failed `Pexec(3)` leaks its blocks to the caller. REVIEW (3 finders; C faithful to the asm)
  found: a HOST out-of-bounds read (the broken Cconout pointer was not folded onto the 24-bit bus — now masked, RED/GREEN);
  a misaligned `uint32_t*` store (now `wr32`); the saved-D5 offset pinned only against the header both shores read (now against
  the ROM trap entry's own frame); Tier 3 met by CASE CHOICE — a 3-byte AUX: Fwrite at 1.098 while the 1-byte form was 1.17 and an
  empty redirected Cconws 1.87 — fixed by one noinline call per arm with the resolution inlined (1-byte AUX: 1.08, Fseek on CON
  1.07, the six old dispatch rows back to 0.78-0.80), the SHORT rows registered, and the empty Cconws ACCEPTED at 1.71 on its
  measured mechanism; and an oracle-only record poke that was a comparison MASK disguised as input — now `case.run(dropped=…)`,
  a span dropped by name with its reason. Mutation 144/156 over the band (survivors equivalent / unreachable / unpinnable,
  listed in the rows). Remaining in GEMDOS: the E_CHG recovery behind the termination record's longjmp (see `## Not
  reconstructed`); the aes/desk boundary and VDI/Line-A are the next components.
* **Wave 10 (2026-09-26) — VDI + LINE-A FOUNDATION.** A read-only map of `$fc9f0c..$fd2f21` (199 functions; the Line-A
  rasterizers set up then `jmp` through RAM vectors `$2A24..$2A38`, which boot fills with the CPU set — ~11 KB of CPU pixel
  loops Ghidra never decompiled; the blitter set unreachable on this machine), then ONE foundation agent: `include/vdi/`
  headers (every field cited, width-tagged), `test/vdi.py` (records by name, the workstation staged AS THE DISPATCHER LEAVES
  IT — record + its 21 copies into Line-A, pinned against the ROM's dispatcher — byte-wise merged pokes, screen/pixel helpers
  and a compact screen diff, run doors for functions, register-contract primitives and the Line-A exception), shared machinery
  hoisted for every component (`case.merge_pokes` / `verified_row` / `Result` / `continued` / `SLACK_FILL`; the host-slot table
  moved to `include/host_slot.h` + `src/host_slot.c`; `include/ram_vector.h`), and tier3 deriving every VDI row from its
  `VDI_ROM_*`/`_OPCODE` pair (the kit's `os.h` already owns `VDI_<FN>` as opcode numbers, hence `VDI_ROM_`). Review (2 finders:
  every header field correct) found the staging helpers would have tested the WRONG MACHINE silently — the dispatcher's copies
  not staged, pokes replacing each other by address, non-fields accepted as fields, an unbounded ptsin — each fixed RED→GREEN.
  Worked examples: `vsf_perimeter` 0.72 and `$a000` 2.43 (accepted: (N), the dual of (M) — a C core answers in D0 alone, so
  several answer registers go through a results pointer; Tier 1 compares all of them, Tier 3 holds D0).
* **Wave 10 band 0 (2026-09-26) — the VDI's HELPERS, SETTERS, INQUIRIES, PALETTE and the PIXEL / SCANLINE primitives.** Four
  agents, 70 routines: `src/vdi/helpers.c` (the math/geometry/text helpers, `vr_trnfm`), `attributes.c` (every attribute setter,
  `st_fl_ptr`, `arb_corner`, the vex exchanges), `inquire.c` + `palette.c` (the inquiries, `vs_color`/`vq_color`), `raster.c` (concat,
  `$a001`..`$a005`, the three arms of `$a003` incl. the diagonal Bresenham that runs code BUILT ON THE STACK, and the CPU bodies of
  vectors 6/7/8). THE USER'S POLICY for the hand-written 68000 — C first, a byte-pinned `.S` where the C is over 1.10 — ran for the
  first time: 22 routines ship as `helpers.S` / `palette.S` / `raster.S`, every one BYTE-EXACT to the ROM (named encodings, no
  avoidable excusals; raster's cross-region displacements and its fringe-table reference pinned to their exact relocated values) and
  1.00 on every `.S` row. REVIEW (5 finders) found the policy had NO MECHANISM behind it — the bench linked both twins and ~40 over-bar
  C rows were justified by hand-typed prose — now ONE table, `include/vdi/transcribed.h` (`include/transcribed.h` since the AES
  foundation; entry, ROM routine, C core, the registers it leaves changed vs the GCC ABI), from which Tier 3's rule (T) is DERIVED (a transcribed routine's C rows pass only while every
  `.S` row is ≤ the bar — shown RED on a deleted and on a drifted `.S`), the future ROM build's contract (`atari/target.mk`
  TRANSCRIBED_*, pinned) and the `.S` entry declarations for C callers. Real divergences fixed RED→GREEN: the palette address not
  folded to 24 bits (30 low-res indexes wrap into the vector page), `vq_color`'s and the inquiries' read points, the four colour
  setters' bound wrapping at DEV_TAB[13]=$8000, concat's shift count (mod 64, ≥16 sign fill), get_pixel's word accumulator; and the
  tests made honest: a weakened mutant restored (row placement by BYTES_LIN), the "unreachable" PLANES>8 guards reached, the `.S`
  pattern paths exercised, ptsout store-order overlaps, the code-pointer masks narrowed to the registers that really hold code.
  Names unified: `VDI_ROM_*` / `LINEA_ROM_*` for routine addresses. FINDINGS: no setter updates the dispatcher's Line-A copies (Line-A
  draws with the old write mode/clip until the next VDI call); a pattern style carried into hatch points PATPTR at MAP_COL; vqin_mode
  does not round-trip; vqt_name writes 34 words and reports 33; smul_div's `neg.l` rounding; clc_dda's equal-size arm unreachable;
  concat's shift table starts at its own `rts`; `$a005` stores clipped corners on a miss. Mutation (logged, private builds): helpers.c
  83/88, attributes.c 105/108, inquire+palette 92/92, raster.c 89/91, raster.S 55/57, helpers.S 32/33 — every survivor named in the
  sweep logs and equivalent or a documented memory smash.
* **Wave 10 band 1 (2026-09-27) — BIT-BLIT, TEXT RASTER, POLYGONS & FILLS, MOUSE & INPUT.** Four agents, ~50 routines: `blit.c`/`.S`
  (the threaded CPU blit engine — 57 absolute fragment addresses relocated and pinned — `$a007`, `$a00e`, vro/vrt_cpyfm, vr_recfl),
  `text_raster.c`/`.S` (TextBlt $fd1df6, the ROM's largest hand loop, and fast text; the `.S` generated from the disassembly),
  `fill.c`/`.S` (`$a006`, clip_line/polyline/plygn, the contour seed fill with DRI's globals and a 1920-word queue), `mouse.c`/`.S`
  (sprites, hide/show, vsc_form, the mouse ISR, the VBL cursor, mouse_init/off, the polls, locator/choice/string). REVIEW (5
  finders) found ~12 real divergences — each RED-before/GREEN-after: the blit re-tests P_ADDR PER PLANE and re-reads MIDDLE_COUNT
  per row; an odd TextBlt op index is the ROM's address error and an op slot naming an effect fragment must halt (mode 44 + LIGHTEN
  hung the suite); `$a006` takes an overflowed crossing's sign from the 32-bit PRODUCT; the contour fill's walks are true signed
  compares; polyline clears LSTLIN and v_get_pixel answers BEFORE their reads; end_pts' `adda.w` sign extension and A5 drift;
  draw_sprite saves a row BEFORE reading its form words; the mouse ISR reads through the A0 a user vector hands back — and a
  BUILD-CONTRACT HOLE (GCC inlined transcribed C cores into their callers: now `TRANSCRIBED_CORE` = noipa on all 42). The 16
  hand-typed "(T) through a call" acceptances are GONE: a SECOND bench blob (`build/bench_shipped/`) links every C caller of a
  transcribed core to the `.S` through glue thunks GENERATED from the table (`bench/shipped_glue.py`) — band 0's deferred call-site
  glue, built and exercised by every bench run — and legend rule (T→) prices those rows AS THEY SHIP (0.78–1.08; drifting a callee's
  `.S` reddens them, shown). ONE register-carrying RAM-vector hook (D0/D1/A0) in staged_call.h; one Alcyon signature registry;
  cross-file `.S` relocations must land in a byte-pinned region; every ROM-address-as-data site enumerated (test_vdi_rom_data.py).
  MUTATION TOTALS WERE UNRELIABLE (every sweep counted any nonzero exit — timeouts and an agent's `pkill` SIGTERMs — as a kill):
  a STRICT classifier (README "Mutation sweeps") found 10 real holes, all now killed; honest totals blit.c 101/109, blit.S 54/56,
  text_raster.c 203/224 (six thicken-first survivors equivalent by argument, not proof), text_raster.S 24/28, fill.c 123/145 (11
  abnormal = non-terminating mutants), fill.S 47/51, mouse.c 157/161, mouse.S 58/59. FINDINGS: the ROM's CONTOUR FILL CAN HANG
  (only SEEDABORT stops it) and `v_choice` REQUEST MODE HANGS FOR EVER; `$a00e`'s bit 4 is the pattern flag; TextBlt modes past
  19 read an easter egg as op indexes; vdi_locator writes the caller's intin; plygn permanently increments the caller's contrl[1].
* **Wave 10 band 2 (2026-09-28) — WIDE LINES & MARKERS, the TEXT LAYER's C, the TIMER & SCREEN plumbing.** Three agents, 22
  routines: `lines.c` (v_pline, v_pmarker and the Alcyon geometry of a wide line — cir_dda, perp_off, do_circ, wline, arrow, do_arrow —
  all C, five host slots standing in for the frames the ROM points LINEA_PTSIN at), `text.c` (text_init, make_header, vst_height/point/
  font, vqt_extent/width, vst_load_fonts over REAL fonts: byte copies of the ROM headers, a GDOS set behind the ring, Intel-order forms,
  a proportional face with a HOR table), `screen.c`/`.S` (v_clrwk, setres, init/restore_timer_mouse, the etv_timer tick, and the BIOS
  span clear `$fc4b7c` moved out of `pexec_load.c` into a byte-exact `.S` because its C is 3.87× the ROM's `movem` loop — so the Pexec
  loader now prices THROUGH it and its rows fell: 0.84 → 0.79). `timer_tick` ALSO ships as the ROM's own 24 bytes, on the
  trap1.S/isr.S entry precedent rather than the >1.10 rule: etv_timer holds its address and the C core does not take that convention
  (transcribed.h row = the vector set, measured; USER_TIM stubs clobber everything so the `movem` bracket is pinned; `.S` 1.00, C 0.98).
  REVIEW (3 finders + a seams pass) found real defects, each fixed RED→GREEN: TARGET STRICT ALIASING merged vqt_width's HOR_TABLE
  re-read after a ptsout store (Tier 3's second differential, one byte at $c4049) — `-fno-strict-aliasing` now in `atari/target.mk`
  for every target build, PINNED by asking make for the expanded flags; it moved rows by hundredths (five pinned Bconout acceptances
  re-pinned, vs_clip respelt faithfully to one PTSIN read, 1.06 → 0.83); setres's switching arms were pinned ONLY AS HALTS (3 mutants
  survived) — now the mode is named in the halt and read off the ROM's pushed word, the image checked unchanged in a shared-memory
  child; do_arrow's hand "(D) through smul_div's glue" acceptance was the band-1 "(T) through a call" in disguise — replaced by a
  DERIVED rule (T→G `glue`): every (T→) row is profiled on the shipped blob, the cycles inside the sized glue thunks netted out, and a
  row over the bar passes only if its NET ratio is ≤ 1.10 (arrow 1.10/0.99, do_arrow 1.14/1.01 and 1.13/1.01, vqt_width 1.15/1.08; vq_key_s
  and vdi_choice stay accepted, OVER even net); the WORST realistic rows registered (width 1 for arrow/do_arrow, a bus high-byte chain
  for vst_height, ptsout over HOR_TABLE); the poison opt-outs narrowed to one named constant (`vdi.READS_A_POINTER_IT_WRITES`) used only
  where the pass reads the I/O page (arrow, the four text-size routines) — v_pmarker's pass now really attributes; helper duplication
  collapsed (one COLBIT loop, one contrl/workstation/device-table word helper set, one `bus_dereference` idiom with its base-0
  precondition, one trap #14 helper header for five sites, one `refusal_over`), the init IPL mask pinned on the shipped ELF, and the
  call graph taught to see a function address loaded as an immediate (GCC had hidden make_header's act_siz calls from the pricing).
  MUTATION (strict, private .so per mutant): lines.c 89/98 (6 equivalent, 3 abnormal = the host's named zero-divide refusals), text.c
  104/109 (5 equivalent), screen.c 36/45 (6 equivalent span splits, 3 abnormal = host aborts on a detection), the tick `.S` 8/8 by the
  byte pin. FINDINGS: the wide line leaves the CALLER's contrl[1] at 5 and v_pmarker at its last polyline's count, with LINEA_CLIP
  left 1; the quarter circle is cached by WIDTH only; nothing bounds cir_dda's width (79 writes STR_MODE); the dead arrow end-style bit
  also draws round discs; `$fd3664..$fd36eb` is the marker-shape data; vqt_extent at 270° answers the wrong box and sums in the shared
  word at `$1706`; vst_height/vst_point after vst_unload_fonts take ADDRESS 0 as the font; text_init turns Intel forms WITHOUT flagging
  them (every v_opnwk re-swaps); vst_load_fonts makes no GEMDOS call; on a colour ST every setres word but 1 and 3 opens LOW; a
  second v_opnwk CHAINS THE TIMER TICK TO ITSELF (unbounded recursion on the next tick); restore with a negative NEXT_TIM leaves the
  VDI's tick installed.
  THE CODE-REVIEW GATE (my-code-review, high) then fixed, RED→GREEN each: `span_bytes`' host bound spelt as a sum wrapped for a `to`
  below `from` and let the host clear run off the image (SIGSEGV) — now `width <= RAM && driven <= RAM - width`, pinned by a child-process
  abort; the `xbios.h` trap helpers took plain `d` inputs, so a second argument took callee-saved D3 and every caller saved it (Tsettime
  0.76 → 0.93, Tsetdate 0.60 → 0.66, mouse_off +16) — inputs now bound in D0/D1/D2 as `+d`, HEAD's cycles back and setres 0.02 better;
  vs_clip's single PTSIN read is now pinned by a ptsin laid over Line-A's own INTIN/PTSIN pointers (the per-word form reddens); the init
  mask test now orders the NEXT_TIM store before the SR restore; the call graph's immediate rule reads only a `move.l`/`movea.l` of the
  constant into a register or frame slot (a compared or stored constant equal to a function start no longer forges an edge; both
  graphs unchanged). Harness: one `symbol_table(elf)` and one `vdi.SHIPPED_ELF`; the glue read as slices (`emu.prof_slice`, ~27 ms a
  (T→) row, was ~49); `glue_cycles_of` defaults 0; `refusal_over` encodes its I/O seed through the kit. Cleanups left every object
  byte-identical but one operand swap (`asks_for_arrows`).
* **Wave 10 band 3 (2026-09-28) — ARCS & ROUNDED BOXES, GRAPHIC TEXT, the WORKSTATIONS.** Three agents, 12 routines, all Alcyon C:
  `arcs.c` (clc_pts, clc_arc, gdp_arc, gdp_ell, gdp_rbox, entered by `jsr` as vdi_gdp's arms leave the machine; the seven arc-scratch
  words named, two of them below CUR_FONT; v_pline and the rounded box share `line_style_mask`/`set_line_attributes` with no non-arc
  row moved), `gtext.c` (v_gtext and d_justified over REAL fonts — the ROM faces and GDOS-shaped RAM copies — through TextBlt, the fast
  path and `$a003`; `style_asks_for`/`font_flag` hoisted with objects byte-identical; the empty string was 1.71 until the body moved out
  of line behind the count test), `workstation.c` (init_wk, v_opnwk over a FILLed machine with the shifter and palette declared and
  its switching arms pinned as halts equal to the ROM's image, v_opnvwk/v_clsvwk/v_clswk through the REAL `trap #1` into the ROM's
  GEMDOS, their list built by chained opens and closes that reach the duplicate-handle bug by themselves). Every row is priced: (T→)
  through the shipped blob at 0.42–1.07, six (T→G) at 1.10–1.17 shipped and 0.90–1.02 net, init_wk plain at 1.07; no acceptance.
  REVIEW (3 finders + a seams pass) found real defects, each fixed RED→GREEN: v_gtext RE-READ CUR_FONT for the first glyph where the
  ROM draws glyph 0 in the A5 font it loaded at entry (`$fcd76e`, reloading only after each TextBlt at `$fcdc38`; a font at `$b0010`
  pins it, and the "DELY stored once" mutant it kills had been labelled equivalent); place_origin read the font's lines before the
  DESTX store. TESTS WEAKER THAN CLAIMED: v_clsvwk's walk never crossed more than one link (`while` → `if` survived; now close the last
  of four and the second of two 3s — first match wins, the first 3 falls off the list still allocated); arms called unreachable were
  reached (H_ALIGN > 2 / V_ALIGN > 5 through the workstation record's copies, the 3600-rotation underline via vst_rotation(3150),
  vsl_width's stored negatives −3 / −1, seven WRAPPED rounded boxes that do return — the "y wraps" one killed a half-height word-wrap
  hole); cases that had silently taken the fast path (x on a byte) made TextBlt twins; the WORST realistic rows were unregistered
  (d_justified's long spaced lines scrolled away, 1.11 / 1.11 / 1.13, and v_gtext's ninety missing characters, 1.06) — registered;
  a Malloc spy (= 308) killed the Malloc(307) survivor. Band 1's HOST TextBlt OVERRAN its scratch: a huge WEIGHT or a wide glyph turned
  SIGSEGV'd/SIGBUS'd in the pre-pass and the quarter/half turns, and the DDA SCALE copy of a 22,330-wide glyph doubled wrote 37,954 B
  over the vectors, VDI and Line-A RAM before anything refused — both now named host refusals (`require_scratch_room`, a row at a time
  `require_scaled_row_room`; legitimate copies peak at 228 B, more than one 204-byte half, inside the 532 B before the PTSIN copy),
  target `.text` identical. The GEMDOS-trap rows were first UNPRICED ("the whole-image relation differs by nature"); now priced over the
  STAGED recording `trap #1`, and the kit's `RomBench.measure(dropped=)` names `[$2848, $284c)` LINEA_RETSAV. THE CODE-REVIEW GATE
  (my-code-review, high) then made that drop rule PER BYTE and SHARED: `rom_bench.vet_dropped` refuses a dropped byte the ORIGINAL did
  not write (a drop one longword wider than the park went through before) or a truncated ledger, and `case.run` calls the same rule —
  which TIGHTENED committed Tier 1 drops: the GEMDOS door's 0x100-deep stack drop covered 124–200 bytes the ROM never writes, and the
  save-area/termination-record drops were dead in the no-trap cases and two never-nesting Cconrs cases; they became
  `case.run(dropped_windows=)` (only the window's bytes the original stores are dropped, the rest compared again). A Tier 3 drop now
  needs `undropped=` (a companion differential over the row's own pokes that drops nothing, run by `test_tier3`). The staged trap's
  ledger APPENDS (8 entries; a v_clswk mutant freeing records in a swapped order survived the single slot, now red; +4 insns / +48
  cycles a trap on BOTH columns, so seven rows moved toward 1). The call graph QUALIFIES a function name objdump gives twice by its
  defining FILE (`readelf` FILE symbols; two statics' `.isra`/`.constprop` clones had folded into one node), an address-less
  reference to a shared name reaches every node of it, and a qualified base that is a row symbol or a transcribed core is refused.
  `declare_alcyon(host_arguments=)` lets glue be generated for C calling gemdos_call (its thunk now executes, 136 cycles). DRY: one
  `table_entry`/`word_entry`, `copy_words`, `set_work_word`/`set_work_long`, the colour clamp/map helpers and clamp constants in
  `attributes.h` (init_wk's high-first interior and fill-style clamps kept spelt out: 2–4 cycles through the helper), one XFM family,
  `VDI_POINT_WORDS`; the ROM-data census now reads `include/vdi/*.h` inlines. MUTATION (strict, private .so per mutant): arcs.c 82/83
  (1 equivalent), gtext.c 143/144 (1 abnormal = the named scratch refusal), workstation.c 141/152 (8 equivalent, 3 abnormal = a host
  abort and two non-terminating walks), the gate's C changes 15/15. FINDINGS: v_opnvwk hands out a DUPLICATE HANDLE after a close from
  the middle (1,2,4 → 3 appended, then a second 3 inserted); init_wk stores the fill style 1-BASED where vsf_style stores it 0-based,
  and line type 0 as −1; v_clswk leaves the physical WS_NEXT naming freed memory; v_clsvwk's walk has NO END TEST (a record not on the
  list wanders through address 0's vectors); gdp_rbox sorts through its CALLER's A5 (= PTSIN at both of vdi_gdp's `jsr`s); an OUTLINED
  box whose wrapped segments send clip_line into a cycle never returns; the last arc point is END_ANG, never START + DEL, and angles
  are never normalised; the HOR table is read ONE BYTE a glyph where vqt_width reads (left, right) pairs; centred or right-aligned
  text leaves VDI_RESULT = 1 and the extent in `$1706`/`$1708`; a non-right-angle rotation draws at the stale DESTX/DESTY; the map's
  "`$fd2e84`" is vq_color, v_gtext is 1862 bytes (cfg.txt said 1682), and `$fcd9f2`'s `ijmp` is the V_ALIGN switch (`$fd3990`).
* **Wave 10 band 4 (2026-09-29) — the GDP, the ENTRIES, the ESCAPE: the VDI complete (but the blitter).** Three agents, five
  routines and Scrdmp's export: `gdp.c` (vdi_gdp `$fcbbcc`, the ten-arm switch at `$fd3954`, inline Alcyon C — the bar, circle and
  ellipse arms do their own set-up, every other arm `jsr`s a band-3 worker), `entry.c` + `entry.S` (linea_dispatch `$fc9f0c`,
  linea_init's `.S`, vdi_entry `$fc9f9e`, vdi_dispatch `$fca9f6`), `escape.c` + `escape.S` (the escape `$fc427a`, 22 arms), and
  `vbl.c`'s static `screen_dump` exported as `xbios_scrdmp` ($fc0d50). vdi_gdp's arms PROVE BAND 3'S STAGING BYTE FOR BYTE: the real
  arm runs over the staging band 3 used for each worker and its final machine is held to the worker's run from it
  (`vdi_gdp.assert_same_machine`), so band 3's "machine as the arm leaves it" is measured rather than trusted; the aspect and
  ellipse-reading helpers moved into `vdi/arcs.h` inlines with every arcs row unmoved to the cycle. THE ENTRIES: the Line-A exception,
  `$a000` and the `trap #2` entry ship as ONE byte-pinned region `$fc9f0c..$fc9ffb` with 16 declared words (`$a000`'s two `lea`s and
  the 14 table longwords of `.S`-shipped primitives relocated to their entries; `$a009`/`$a00f` keep the ROM's) — the timer_tick
  precedent, entries with a register convention no C function has; the dispatcher ships as C through a new `staged_call.h` shape,
  `call_vector_keeping`, which saves the callee-saved file round the `jsr` only (the ordinary shape measured 1.09 on a lookup that
  calls nothing). THE ESCAPE, under the user's hand-68000 policy: its word table points mostly INTO the VT52 driver's own ESC bodies at
  the addresses ESC's tables name, and the author's first cut (C entering nine per-body `vt52.c` exports, 32 hand acceptances up to
  3.13) was refused at the fix list — the escape is hand 68000 over the bar, so its OWN code ships as a byte-exact `.S` (four spans,
  386 ROM bytes, 27 exact relocations incl. a new table-based `Relocated.base` and `Relocated.thunk`) with 13 `.S`→C thunks into the
  console bodies, which stay C under Bconout's acceptances; ESC E's thunk sits at the ROM's own body address, so v_exit_cur's fall
  through and v_enter_cur's `bsr.s` keep the ROM's bytes. THE DERIVED (T←) `own` RULE, from the code-review gate, replaced a LOOSE
  (T) extension (a written entry for a `.S` row carried its C rows) and the 24 hand `vdi_rom_escape` acceptances that leaned on it:
  every `.S` row of a routine that calls C is PROFILED on both sides — on ours the cycles inside its sized thunks and the C they reach
  (the m68k call graph's closure) are subtracted, on the ROM's the ROM-window cycles inside its transcribed spans are its own; the row
  is `own` iff its own instructions are within the bar AND every cited Bconout(CON:) acceptance still stands, an own ratio over the bar
  reds a row even when the row is under it, and a written entry for a `.S` row now carries NOTHING. For that the KIT PROFILER COUNTS
  THE ROM WINDOW (`shim.c` tallied PCs below 1 MiB and only in `run_bench`: now `PROF_ROM_SIZE` slots after the RAM ones, one
  `osh_prof_slot`, `prof_tally()` in both loops, `emu.prof_cycles(lo, hi)`; the RAM slot layout unchanged). RED first: a +24-cycle
  spill in the escape's dispatch reds 26 of 38 rows; deleting each cited acceptance in turn reds the rows it carries. THE REVIEW AND
  THE GATE found real defects, each RED→GREEN: (1) THE BIOS CONSOLE'S 24-BIT WRAP, a LATENT Bconout DIVERGENCE — a cell address past
  16 MB (vs_curaddress row 0, or an ESC Y row byte below the $20 bias through v_curtext OR Bconout) is where the ROM wraps to the row
  above the screen and the host aborted; the gate made it ONE console bus policy, `vt52.h`'s `console_screen_block` (form, wrap, then
  bound) for every console screen writer — cursor, glyph, clear, both scrolls (`test_bios_console_bus.py`, 7 cases, and a Bconout ESC
  Y case that also newly DRIVES `bpl` against `bcc` on the row clamp); target objects byte-identical. (2) The Line-A dispatch's
  declared clobbers missed A6 (`$a007` adds 76, `$a00d` loads it) — the case choice hid it; a `$a007` transcription row measures it.
  (3) FIVE dispatcher mutants survived the battery, two called equivalent wrongly (the handle read after VDI_RESULT's clear with
  contrl[6] on it; MONO_STATUS from a record partly over `$2610`) and three never swept — each killed by a new differential. (4) The
  ptsin copy's DIRECTION and the dispatcher copies' ORDER against the ROM were unpinned (a backwards copy and 4 of 20 adjacent swaps
  fully green) — now one ordered `vdi.DISPATCH_STEPS` list the ROM's stores are held to (20/20 swaps and 24/24 dropped steps red).
  (5) Scrdmp's COUNT and ORDER: `scr_dump` called twice, or the flag set before the call, passed all 282 escape + VBL tests — a
  recording stub now. (6) THE LAYER-WIDE BUS POLICY for the VDI accessors: a trap #2 block with top-byte-dirty pointers SIGBUS'd
  vsm_height/vqin_mode and read outside the image in v_pline/wline — `vdi.h`'s call and workstation accessors now SUM THEN MASK (the
  68000's `d16(An)`), `caller_word` serves a held cursor and vdi_wline's PTSIN reads (`test_vdi_bus_pointers.py`, 7); target objects
  identical but one GCC-internal `CSWTCH` label. Also: the WORST realistic rows registered (the width-3 outlined box, the TALL ellipse
  — band 3's gdp_ell row too, 1.01 → 1.02 — v_curtext's one ESC / one NUL, escape 20); the two light mouse paths the escape's `jmp`s
  leave to the ROM priced on v_show_c/v_hide_c themselves; each escape arm's transcription mask derived per ARM from what the two
  measurably disagree in; the perimeter constant's four spellings → `vdi.h`'s one; `next_of`/`handle_of` hoisted into
  `vdi/workstation.h`; `M68K_Dn`/`M68K_An` for entry.S, fill.S and blit.S; `c_call_glue.h` shared by isr.S and escape.S;
  `vdi.CallerPool.staged` with a pool-overlap refusal; `assert_same_machine`'s 16 MB Python walk → `harness.differing_addresses` and
  the order search once per placement (≈4 min → 48 s). THE MUTATION TOOL: `privlib` swapped only `src/` files, so a HEADER mutant
  was compiled UNMUTATED and counted SURVIVED — earlier bands' header totals could only UNDERSTATE kills, never claim a false one; a
  per-tag shadow include dir fixes it, and a replacement nothing compiles is refused. MUTATION (strict, a private .so or blob per
  mutant): gdp.c 50/56 (5 equivalent, 1 unpinned) + the perimeter constants 6/6; entry.c 103/112 (5 equivalent, 2 unpinned
  host-only, 2 abnormal); the escape's C 68/71 (1 equivalent, 2 abnormal — the named zero-divide refusal and the bus-wrap revert, each
  caught by an abort) and its `.S` 8/9 (1 equivalent) — 235 of 254 killed, 12 equivalent, 3 unpinned, 4 abnormal. ROM FINDINGS:
  vdi_gdp is 434 bytes (cfg.txt said 92), `$fcbd5e`'s `bra` and `$fcbd60`'s `bhi` are dead and D7 is "restored" by `tst.l (sp)+`; the
  bar's outline is the FILL colour through polyline (line style, colour and width ignored), and only for WS_FILL_PER exactly 1;
  v_opnvwk inserts its duplicate handle AHEAD of the older one, so the newest wins and the older cannot be reached by handle until it
  closes; the entry doubles the point count in a WORD ($8000 copies nothing, $8200 copies 1024 words with no cap) and gives the count
  back through a re-read LINEA_CONTRL, which a function's intout can move; opcodes outside both tables still load the workstation;
  v_opnwk and v_opnvwk ignore contrl[6]; vdi_entry is 94 bytes (the map: 92); the escape serves 101 (v_offset) and 102 (v_fontinit)
  beyond the documented 1..19, its bound is UNSIGNED, vs_curaddress validates nothing (0 → $ffff, which with the cursor drawn inverts
  a cell far outside RAM), v_dspcur writes the caller's intin[0] and ignores ptsin, v_curtext's count is an unsigned `dbf` (≥ $8000
  walks up to 128 KB), v_offset never re-places the cursor, v_fontinit has no zero-divisor guard, vq_chcells stores columns first and
  the table's entry 0 is its `rts`; the map's "`$fcb148` (hide cursor)" is v_hide_c, the MOUSE hide; and `$fc4a42` is escape 102,
  whose body past its intin read (`$fc4a48`) is what the console re-init `$fca914` `bsr`s into.
* **Wave 11 (2026-09-30) — AES FOUNDATION.** THE MAP, read-only over `$fd9eca..$fefff3` (736 functions, `projects/tos102us/AES_MAP.md`
  + `aes_map/`): the aes/desk boundary is `$fe387c` — the desk (`$fdb014..$fe387b`) is a SUBROUTINE of the shell in PD0
  (deskmain `$fe272e`, called once from sh_main) and calls the AES's INTERNAL routines directly through Line-F, never
  `trap #2` (its own binding layer `$fdde54..$fde4cc`, each `dsptch(); <internal>()`), so the AES's testable surface is ~60
  internal entry points and the desk can only follow them; the boot snapshot sits INSIDE the dispatcher's idle loop (`rlr`
  NULL, `indisp` 1, both PDs on `nrl` in evnt_multi, the CPU in `idle` polling the keyboard through the VDI); every
  internal call is a Line-F word through a Malloc'd RAM copy of the handler (`$2c` → `$cc0e`) that SELF-PATCHES its own
  `movem` mask word at `$cc44` on every masked Alcyon return — a word a C candidate never writes; and `decomp.c` is
  UNRELIABLE in this range (472 of 726 functions end in `halt_baddata` at a Line-F return, ~355 Line-F calls mis-decoded as
  coprocessor ops, some calls simply absent, every call's D0 invisible) — port from the map's own Line-F-aware disassembler.
  The map was wrong in places a body read corrected: "optimize" is not all hand 68000 (`$fecfb2`, `$fed19e`, `$fed27c`,
  `$fed382` are Alcyon C), three names in it were misassigned (`$fed19e` is ob_sst, everyobj is `$fed27c`, get_par
  `$fed382`), `$b74a` is window 0's ORECT list and not a tree, the three UDAs are NOT one stride, and the Line-F table names
  42 routines more than once. THE DOOR: `test/aes.py` (fields through `test/layouts.py`, the width-tag reader hoisted out of
  vdi.py; the ROM-routine naming rule hoisted into `test/routines.py`, by which tier3 labels every VDI/Line-A/AES row; every
  component's rows and drops through `case.Rows`; `staging.Registry.require_claimed`; `table_entry` moved to
  `m68k_idioms.h` with every other source's m68k code byte-identical), the addrs.h AES block (86 routines, 62 `_OPCODE` pairs
  held to the dispatcher's arms, the 48 table gaps to its default arm), `include/aes/{aes,objects}.h` (25 table immediates
  pinned against the ROM, the tables tiling THEGLO). THE `$cc44` DROP: the mask word is dropped by name
  (`aes.LINE_F_MASK_WINDOW`, a window: only where the ROM's run stores it) and every priced row drops it at Tier 3 with its
  UNDROPPED companion, the word staged at the value the run leaves. AES CASES RUN POISONED: the foundation found the kit's
  attribution pass could not coexist with a drop (it pre-inverted every oracle-written byte before `case.run` could drop
  one, so a case whose ROM run rewrote the word failed the pass and one that changed it skipped the pass in silence) — the
  kit now takes the drops as DATA, `differential(dropped=drops.Dropped(spans, windows))`, leaves them out of the plain
  compare BEFORE the pass's gate and neither poisons nor compares them (the gate then held fixed spans to the PLAIN run
  only, the re-run cutting only windows, and `_vet_poison_is_attributable` leaving dropped bytes out of its clash set, each
  RED first; `tools/recreate_kit/drops.py`, which imports nothing, so Tier 1 no longer imports the Tier 3 module).
  COMPONENT-NEUTRAL `.S` MACHINERY: the byte-exact transcription table is `include/transcribed.h` (was
  `include/vdi/transcribed.h`), its machinery `test/transcription.py` (moved out of vdi.py, ~560 lines), its test
  `test/test_transcribed.py` (was `test_vdi_transcribed.py`), `atari/target.mk` compiling `src/vdi/*.S` and `src/aes/*.S`;
  an AES `.S` is held to its EXECUTED path (the oracle's cycle-per-PC profile over the row's cases) running no Line-F word
  and reaching no return tail outside its own pinned region — a static word scan was tried and REFUTED (`cmp.w #-1` at
  `$fed04a` reads as a Line-F return word); a scratch `src/aes/rect.S` for `$fecd22..$fed070` went through the whole
  machinery at 1.00 and was not committed; every object, both blobs and every tier3 number byte-identical across the move.
  THE KIT WATCHDOG: a mutant that makes host C spin used to hang the run; a per-call faulthandler guard inside
  `harness.differential` was built, then REFUTED at the gate four ways (the dump lost under fd capture, every differential
  erroring under `--capture=sys`, pytest's own `faulthandler_timeout` silently disarmed, only two of ~300 call paths
  covered) and replaced by a PLUGIN, `-p recreate_kit.watchdog` (kit.mk's `test`/`guarded`, the kit's Makefile): one timer
  per TEST, written to a dup of the REAL stderr taken at configure, budget `TEST_BUDGET_SECONDS` = 300 s from the measured
  maxima (buggyboy's `test_hi_fuzz` 46 s is the longest; tos102us 5.8 s), `--watchdog-seconds` to change it, an outer
  `faulthandler_timeout` REFUSED rather than clobbered. THE MUTATION RULE it forced: a watchdog exit or a segfaulted worker
  is under xdist a "crashed" test counted in `N failed` with exit 1 — the shape of a kill with no assertion — so a run is
  KILLED only when it failed MORE tests than crashed (README "Mutation sweeps"); re-classifying the saved tails moved TWO
  verdicts KILLED → ABNORMAL, so the foundation's recorded kill tally was 2 too high. REVIEW (2 reviewers) AND GATE (5
  finders) FINDINGS, each fixed RED→GREEN or pinned: the kit gap above; test_status's table pattern stopped at `$fd` and
  would have left every AES row unpinned in both directions (widened to `$fe`); the pointer arguments' 24-bit bus (a
  top-byte `BUS_TAG` on every pointer); ob_offset's two call words ($f208 ×4, $f154 ×3) pinned site by site; the sixteen
  fork-function immediates enumerated (`aes.FORK_FUNCTION_IMMEDIATES`: six queue pushes, three ap_tplay stores, three
  compares in forker's recorder, four in ap_trecd — the review had counted six), with `AES_ROM_{T,K,B,M}CHANGE` in addrs.h;
  rc_intersect at the bus top (below); the Line-A `.S` rows now labelled by the one naming rule (`Line-A linea_hline
  (.S)`). MUTATION (strict, a private .so per mutant): 35 — 30 killed, 3 equivalent (ob_offset's swapped clears,
  rc_intersect's origin ties and extent-before-origin), 2 ABNORMAL (`object_field` and rc_intersect's clip without the bus
  mask: only a segfaulted worker); get_par 5/5 (its three spins killed by failed assertions beside the crashed tests),
  ob_offset 7/8 + its answer word's bus mask, rc_intersect 12/14, the headers 5/5 (OB_X, OB_TAIL, GRECT_H, the signed
  object index, the signed `table_entry` index); the kit's own — the four drop mutants, the watchdog's missing `file=`, its
  missing refusal and its missing cancel — all killed. The Line-F CALL path costs +15 instructions / +190 cycles through
  the staged caller; priced rows enter by `jsr`, so the ROM column carries the Line-F RETURN's cost and not the CALL's —
  conservative.
* **Wave 11 bands 0+1 (2026-09-30) — the AES's LEAVES and OBJECT/RESOURCE layer.** Five slice agents (0A the optimize
  layer's memory and string helpers; 0B the rectangle helpers, object text and state, ob_sst/everyobj and the DESKTOP.INF
  scanners; 0C gemrlist; 1A the object-tree operations; 1B the resource layer and the shell/scrap buffers), four reviewers,
  two fix agents (P the C and its harness, Q the kit and the shared Python) and a gate-fix pass: 90 routines, all ✅ but
  `dos_free` (a host argument), 290 AES Tier 3 rows. THE OPTIMIZE LAYER IS ONE BYTE-EXACT `.S`: 35 of its helpers measured
  over the bar in C (1.11–2.78 — two-to-three-instruction loops a compiler cannot match), and because the ROM's shared
  return tails `$fed066`/`$fed06a`/`$fed06e` are reached from strlen, streq, rc_equal and inf_what alike they share one
  region with every user, so 0A's `strings.S` and 0B's `rect.S` merged into `src/aes/optimize.S` — the object-text helpers
  laid out in it as unentered words; inside and rc_intersect ship as C (under the bar); merge_str's two `jsr`s relocated into
  the lmul/ldiv region; the executed-path check now names all three tails (the review found the third, `$fed06e`, missing).
  THREE DIVERGENCES FOUND BY REVIEW, each fixed RED→GREEN: ob_find STARTED AT -1 — the ROM steps back only when `dosibs &&
  lastfound != -1` (`$fea182`) and the C had dropped the second test as "redundant", and its model agreed by construction;
  everyobj CLIMBING ABOVE ITS FIRST LEVEL (a tree whose object names its sibling as ob_tail) — the ROM reads its own frame,
  the C read `across[-1]` with no refusal; and THE TOP-OF-BUS WRITES — a tree-table entry at `$00ffffff` sent rs_saddr's
  store 3 bytes past the 16 MB host image, and the same raw `image + address` sat in rs_gaddr, fix_long and the object
  accessors. The fix for the last is the SHARED BUS ACCESSOR FAMILY: `bus_span` and its byte/word/long readers and setters
  in `m68k_idioms.h`, ~12 re-spellings under 9 names in 8 files collapsed into it (three `word_at`s with three return
  types among them), the bound written so it cannot wrap (`at <= OS_BUS_ADDR_MASK - (bytes - 1)`), plus ONE GEMDOS trap
  helper (`gemdos/gemdos.h`'s `gemdos_trap_word_long`, the VDI's and the AES's copies deleted, one `HOST_SLOT_GEMDOS_WORDS`).
  THE KIT PRICES A >6-ARGUMENT CORE: its argument area holds six C arguments, and ob_sst (9), everyobj (8) and inf_fldset
  (7) were unpriced; `rom_bench._call` now enters OUR side with its stack pointer lowered by exactly the bytes that do not
  fit (the ORIGINAL reads the frame its case poked, unchanged) — 8 of the project's 1,111 Tier 3 calls, every other entered
  where it was — and `call_alcyon_object`'s 10-byte frame is really exercised (swapping its x/y pushes reds both everyobj
  rows). THE REAL-DATA RELOCATION CHECK IS EXACT: a fresh ROM copy of each resource, staged where start-up put it and
  relocated again, equals the snapshot byte for byte but for 17 named bytes the AES and the desk edited since — asserted
  `==`, where it had been a subset test over whole fields excusing 34. POISON OPT-OUTS ARE PER CASE, each measured by
  forcing the pass on: the edit battery runs poisoned with only its link longwords unpoisoned, gemrlist's ten green
  functions opted back in, rom_ram's four sites; the staged-trap battery stays opted out as a whole (below). THE GATE'S
  TWO FINDINGS: (G1) the recording `trap #1` handler's host twin stored through the ledger pointer it read out of the
  image, unbounded — the attribution pass inverts that pointer, so a poisoned run wrote into host memory (two false greens
  under xdist); it is bounded to the ledger now and refuses by name, and `AddressHook` records an effect that raises and
  fails the case (a ctypes callback cannot raise into C: it was printed and the run carried on); (G2) everyobj ON TARGET
  wrote `across[8]`/`down[8]` past its arrays for a valid 8-deep tree while the host refused — both builds now take the
  same named halt (`trap #7` on target, pinned by running the blob), tested only where the level moves (everyobj's rows
  unchanged at 0.71/0.69; a per-object test had cost 0.71→0.81). ROM FINDINGS (each pinned by a case): TOS 1.02's everyobj
  keeps its levels in two 8-word frame arrays, so an 8-level walk stores x over its saved A6 and y over x[0] (≥10, its
  return address) — REACHABLE, since objc_draw hands the caller's depth straight on and GEM programs pass 8; the ORECT
  pool's exhaustion is never checked (mkpiece builds its piece at `$0`, brkrct answers "no overlap" after cutting) and
  or_start leaves the desktop's ORECT on both the free list and window 0's list; ob_order of an only child to -1 rewrites
  the word 24 bytes below the tree; lbcopy's backward loop from 32,770 bytes up moves ONE byte; mul_div's overflow arm is
  ORACLE-DEFINED — DIVS's N is undefined there, Musashi answers -15808 for mul_div(1000,1000,1) and the machine (Hatari)
  -15809, so the C follows the oracle, the shipped `.S` is the machine's and no row prices it; wfill's guard tests the
  value, not the count; lstcpy counts in a byte (255 → -1); inf_gindex's count 0 walks 65,536 objects and inf_what never
  reads `cancel`; ob_center tests OUTLINED, not SHADOWED; fix_chpos's offsets run -127..128; get_addr's tree ≥ `$2000`
  reads below its table; rom_rsc_init neither checks its Malloc nor sizes the AES part right (5 bytes of the desk's);
  dos_alloc never clears DOS_ERR; the capture's `$9c40` is 2, a value rom_ram never tests. MAP ERRATA, fixed in
  `AES_MAP.md` and `COMPONENTS.md`: the TEDINFO text helpers reversed, `$fee4de` the bundle copy, `$fe3db4`/`$fe3e08` Alcyon's
  lmul/ldiv, `$fecc6c` strlen, the resources' real starts. MUTATION (strict, a private `.so` per mutant): the slices
  68/68, 97/104, 55/56, 73/74, 159/164; P's re-sweep of all five lists re-spelt over the new accessors plus 24 new, **490 —
  474 killed, 12 survived, 4 ABNORMAL** — the 11 survivors the slices argued equivalent and `bus_span`'s bound one long
  (equivalent: with odd addresses refused first every even address meets both bounds alike), the four ABNORMAL a named
  halt reached before the assertion; Q's kit mutants 3/3 (sp not lowered, off by 2, staged at STACK_TOP); the gate pass's
  everyobj halts 6/6 and G1's two RED-proved (the unbounded store crashed the worker; the swallowed exception passed).
* **Wave 11 band 2 wave 1 (2026-10-01) — the `trap #2` BRIDGE, SHELL FIND + RESOURCE LOAD, NEWRECT and the AES census.**
  Three slice agents (F the foundation, S the shell and resource load, N newrect and the census), four reviewers (R1 F's C,
  asm, bridge and door; R2 the measurement and census machinery; R3 slice S; R4 slice N and the cross-cutting conventions),
  two fix agents (X gsx and Tier 3, Y the shell, resource and newrect plus the conventions): 27 ✅ routines, `dos_sdta` and
  `dos_close` verified and unpriced (a host argument, dos_free's precedent). THE FOUNDATION: the AES's one `trap #2` is
  gsx2's (`$fecb6a`), over the parameter block at `$9466` — the "two direct trap sites" of the map are Line-F calls of gsx2.
  `include/aes/gsx.h`'s `gsx_trap` checks both hops on the host (vector `$88`, SYSVAR_VDI_ENTRY `$8c2a` → `$fc4ebc`), halting by
  name on either, then runs the VDI's C twin of its entry with the VDI's C cores bound per case; the target makes the real trap.
  gemgsxif's atoms verified end to end against the whole image, screen included (21 VDI opcodes reached); the Line-F-free five
  (gsx2, gsx_ncode, gsx_1code, gsx_mon, gsx_fix) ship as `src/aes/gsx.S` (four pinned regions, two relocations). Tier 3 gained
  mechanism (V) "through the OS": a row whose C reaches `trap #2` is priced on its OWN cycles (blob − glue against the AES
  text + Line-F handler, the trap path and the VDI in neither), derived and RED-proved (a 1,734-cycle delay: whole 1.06, own
  4.26 → OVER); the measurement itself refuses an OS remainder that differs by a cycle, and a row under the bar only net of
  its thunks reads `glue` as (T→G) (vst_height's large font 1.17, gsx_moff's v_hide_c 1.12 with them). gsx_moff's open nest
  is ACCEPTED at 1.23 (62 → 76: the image pointer and `$c86a`'s address, the C's floor, once its hide path was split off; it
  had been 1.52). SHELL FIND + RESOURCE LOAD over REAL GEMDOS on the staged RAM disk (the ROM's own AES and desk resources as
  files) plus a SCRIPTED trap — its own 68000 stub, whose ledger records every frame whole (10 bytes) — for the error arms and
  every Tier 3 row; sh_find's caller routine by a new `call_alcyon_pointer` (one pushed long; its target asm runs in the
  logger row). The two frames whose address escapes (sh_envrn's, sh_find's) are kept whole in host slots in the ROM's layout,
  plus the caller's saved A6's top byte past them. NEWRECT (`src/aes/wrect.c`, with w_getsize and w_getxptr) closes band
  0C's deferral. THE CENSUS: `test/rom_data.py` holds the scanner the VDI's census and the AES's share (the VDI's table and
  output unchanged), and `test/test_aes_rom_data.py` holds the AES both ways — its sources' ROM values by kind, and the ROM
  text's 39 immediates naming AES code (owner + band, the 16 fork functions folded in, `owed_by` once ported) plus its 10
  pc-relative data references — each direction proved by a planted use. The header's window GRECTs were mislabeled (+16 is
  FULL, +24 WORK, +32 PREV; TOS 1.02's WS_* are FULL 0, CURR 1, PREV 2, WORK 3, TRUE 4) — renamed. THE REVIEW (4 finders):
  R1 measured gsx_moff's acceptance above the C's floor (1.52 → 1.23) and six unpinned arms of gsx's wrappers (PTSIN put
  back on the hide path and by vsl_width, vst_height's chain past its first link, gsx_fix's reads after its stores and its
  32-bit address test, vr_recfl's tagged pointer) — the poison pass is VACUOUS on gsx_moff/gsx_mon's call arms (it inverts
  gl_moff and steers the ROM to the counter path), so staging pins them; R2 found (V) `net` silently stacking the (T→G)
  thunk lenience (now the `glue` rule) and the remainder check living only in a test; R3 found both frame-overrun HALTS one
  byte early (the ROM serves the input), sh_path's D6 argued for the wrong reason, top-byte cases missing for most pointer
  arguments and the ledger missing Fread's buffer low word; R4 found newrect's area test after the border wrap unpinned and
  the Tier 3 rows short of the worst realistic one. THE FIXES: X split gsx_moff, added the six RED-proved cases, the (V)
  `glue` rule, the in-measurement remainder check; Y moved the shell halts one byte later (a 0 on the saved A6's top byte is
  served as the ROM serves it; a nonzero byte or anything further halts; ROM-alone cases pin both sides), entered sh_path's
  cases with the dispatcher's D6 = 1, registered the worst rows (the failed loads 0.89/0.85, dos_sfirst found 1.05, sh_find
  with its routine 0.91, newrect over a desktop already in four 0.89), added top-byte cases for every reachable pointer and
  newrect's `$fffe` wrap case. MUTATION (strict, a private `.so` per mutant): gsx.c and the bridge 78 — 74 killed, 3
  survived (R1's equivalents), 1 ABNORMAL (the bridge handed pb+4: the host aborts); the (V) mechanism 9/9 and the `glue`
  rule 5/5; shell, glue, resource and wrect 67 — 66 killed, 1 survived (equivalent: DOS_ERR is already 1); wrect's first
  sweep 30 — 27 killed, 3 equivalent. FOUND: the GEMDOS host dispatcher reads an Fopen name unmasked (PARKED, `## Not
  reconstructed`). THE CODE-REVIEW GATE then found Y's +1-byte halt fix had made both shell frames ODD-sized `uint8_t` locals
  (47 / 23 bytes), which GCC placed at odd stack offsets (`sp+29`, `sp+37`) under word/long accesses — an address error on
  every call on a 68000, green everywhere because the host reads bytes and Musashi runs with address errors off. Fixed as
  `uint16_t` word arrays (the text.c / workstation.c precedent, `FRAME_LOCAL_WORDS`), and given a surface: the oracle shim now
  COUNTS odd word/long accesses (the CPU unchanged for every project) and `rom_bench` refuses an m68k-build row that makes any
  unless its count and its first 8 addresses, in order, equal the ROM's — RED-proved (the `uint8_t` frames back: exactly the
  10 shell rows red, naming address and PC; the PC is the jmp/jsr for a fetch at an odd target); `docs/on-target-execution.md`
  taxonomy 14. The same pass dropped sh_find/rs_readit/rs_load's numerators by one instruction (rs_readit's failed load 0.89
  → 0.88). PARKED (unpinned for this class): odd frame bases that are byte-only today — aes_merge_str `sp@(43)`,
  redirected_read_character `sp@(7)` — red only if a later word access lands on a path a Tier 3 row drives; Tier 1 and every
  other project's target C (asm_twin runs) never consult the counter (TRAP_MODEL.md, "Odd word and long accesses"); and the
  bench blob's frame layout can differ from the shipped ROM image's after inlining — the five-ELF objdump scan was one-off,
  not a standing test.
* **Wave 11 band 2 wave 2 (2026-10-01) — GRAPHICS OVER THE VDI: the rest of gemgsxif with the `$a000` bridge, gemgraf, and
  gemgrlib's non-interactive animations.** Two slice agents (A gemgsxif's rest + the `$a000` bridge + gr_mkstate; B gemgraf
  and gemgrlib's non-interactive part), four reviewers (R1 slice A's C, asm and bridge; R2 slice B's gsx_ layer; R3 slice B's
  gr_ layer and grlib; R4 cross-cutting), two fix agents (FA slice A + the shared hoist, FB slice B): 54 ✅ routines. SLICE A
  (24): the start-up (gsx_init; gsx_wsopen with REAL opens of the physical workstation in all three ST modes; v_opnwk's wrapper;
  gsx_start), the graphics mode and the mouse's interrupt routines (gsx_graphic, gsx_setmb, gsx_setmb_aes, gsx_resetmb,
  gsx_escapes, gsx_wsclose, ratinit, gsx_tick), the mouse form (gsx_mfset; gsx_mfsave/restore through the new `$a000` half of
  the bridge), the save-under buffer and its blits (gsx_malloc/mfree/mret, bb_set/save/restore) and the mouse state
  (gr_mkstate, gsx_mxmy, gsx_button); gsx_mret, ratinit, gsx_mxmy and gsx_button ship as `src/aes/gsxif.S` (3 pinned regions,
  1 relocation). THE `$a000` BRIDGE (`include/aes/gsx.h`'s `gsx_linea_base`): the host `require_cpu_routine(VECTOR_LINE_A,
  LINEA_ROM_DISPATCH)` halts by name on a moved vector, then runs the VDI's linea_init C twin and answers A0 (linea.c's
  answer order hoisted to `vdi.h` as `LINEA_INIT_*` and pinned to the VDI battery's); the target is `.short M68K_LINE_A_INIT`
  with A0 out and d0/d2/a1/a2 clobbered (the dispatcher saves d3-d7/a3-a5). gsx_call moved into gsx.h as one `always_inline`
  (as a function it re-pushed its caller's four arguments; no existing row moved). SLICE B (30): gemgraf's gsx_ layer (clip,
  attributes, lines, boxes, blits, text) and gr_ layer (inside, rect, just, gtext, crack, gicon, box), and grlib's gr_setup,
  gr_scale, gr_stepcalc, gr_xor, gr_movebox, gr_growbox and gr_shrinkbox; five Line-F-free leaves ship as `src/aes/gemgraf.S`
  (4 regions, no relocations); `$fda76e`, `$fe82d6` and `$fe831e` folded; one address register for contrl took gsx_attr's
  cached arm 1.21 → 0.90; the host-slot mask widened to 64 bits (A's slot made 33). THE REVIEW (4 finders): R1 measured
  gsx_mfset at the bar only by its copy loop's spelling (1.0993 own → 0.92), gsx_graphic's held mode above the C's floor
  (76 → 72 cycles), bb_set's logical shift REACHABLE (a right edge past `$7fff`) and its five pointers untagged (RED probes),
  a docstring claiming an unobservable order, and GSX_SHOW_AT_ONCE naming the opposite of v_show_c(1); R2 found gsx_tcalc's
  registered row not the worst (the empty string, 1.097), the index macros spelled in three files, magic literals, a
  mis-spelled mutant and a mutation total merged from two runs; R3 found `shrinkbox-to-once` NOT equivalent (the ROM's run
  ends — it is only long), gr_just's read order and gr_gicon's re-read of its icon unpinned, gr_gicon's row flattering (an
  empty label crosses to `glue`), and gr_box's -32768 thickness REACHABLE; R4 found B's transcription caller machinery a
  copy of wave 1's, door helpers copied, unused imports, `AES_GL_MFORM_AT` misnamed (it is GEM's ad_intin), gr_setup's own
  immediate read as data by unported ROM code, an unguarded host-slot mask width, ROM routine addresses outside addrs.h and
  magic numbers. THE FIXES: FA paired gsx_mfset's copy (two words a pass + the 37th: 1.10 `glue` → 0.92 `net`, shown 0.93),
  spelled gsx_graphic's compare with a split displacement and re-pinned the acceptance at 1.24 (58 → 72, the floor counted from
  the instructions), added bb_set's past-`$7fff` and tagged-pointer cases, a form whose 37 words are all distinct (it killed a
  `mfset-last-stale` survivor the battery's alike last rows hid), renamed GSX_SHOW_AT_ONCE → GSX_SHOW_COUNTED and
  AES_GL_MFORM_AT → AES_AD_INTIN, hoisted INTIN_WORD/PTSIN_WORD/WS_WORD/NO_POINTS/NO_WORDS and one GSX_STYLE_SOLID into gsx.h,
  added `HOST_SLOT_ID_COUNT` with a `_Static_assert` on the mask width (RED: 33 <= 32), moved the AES's three interrupt glue
  routines into addrs.h (`$fed3be`, `$fed3e4`, `$fed426`), and pinned the `$a000` halt message and the LINEA_INIT_* order; FB
  added shrink/growbox `to` over ptsin (+0/+4/+8, a 2,000,000-instruction budget), gr_just's corner after gsx_tcalc, gr_gicon's
  icon re-read and text box over ptsin, registered the two worst rows as they are (gsx_tcalc 1.10 `through`, gr_gicon 1.01
  `glue`), commented gr_box's -32768 (reachable, unpinned) and gr_xor's `$ffff` (unreachable), switched the transcription battery
  onto wave 1's atoms pool and imported the door helpers. MUTATION (strict): slice A 107 — 104 killed, 3 survived (two
  equivalent, `wsopen-no-else` unreachable); FA's 14 — 12 killed, 1 equivalent (`mfset-ad-intin-early`), 1 ABNORMAL (a host bus
  error inside the new corners case, not counted); slice B after FB, one run, 158 — 156 killed, 1 survived (`blt-moff-late`,
  equivalent), 1 ABNORMAL (`attr-no-handle`: the host VDI aborts on the poisoned handle); every `.S` byte-pinned. FOUND: two
  more VDI host gaps reading guest pointers unmasked (vdi_init_wk's arrays, vdi_vr_trnfm's forms), PARKED with the GEMDOS one
  (`## Not reconstructed`).
* **Wave 11 band 2 wave 3 (2026-10-01) — THE OBJECT DRAW PATH: ob_format, far_call, ob_user, just_draw, ob_draw, ob_change.
  BAND 2 COMPLETE.** A read-only SCOPING pass first (the inventory read from the bodies — every routine Alcyon C, so no `.S`
  question; just_draw's type × state matrix with the real data reaching each cell, by a LINK walk over the snapshot's trees;
  the ROM's ob_draw / ob_change measured through the oracle), then three slice agents — U and J in parallel, O once J was
  green — three reviewers (R1 slice J; R2 slice U and cross-cutting; R3 slice O) and one fix agent: 6 ✅ routines, 263 tests in
  four batteries (`test_aes_obuser.py` 49, `test_aes_just_draw.py` 52 and `_staged.py` 84, `test_aes_ob_draw.py` 78), 43 Tier 3
  rows (ob_format 7 `through`, far_call 1, ob_user 1 `through`, just_draw 17 / ob_draw 9 / ob_change 8 (V) `net`). SLICE U
  (`src/aes/obuser.c`): ob_format, far_call and ob_user, `test/aes_obuser.py` the shared USERDEF door (a 68000 routine logging
  the 30-byte PARMBLK into a compared log and answering D0, with its host twin); `staged_call.h`'s call_alcyon_pointer now
  ANSWERS D0, held live across the target `jsr` by an empty-asm output so sh_find stays byte-identical (`cmp` of the .o). SLICE
  J (`src/aes/objdraw.c`): just_draw over its ROM frame (one 48-byte host slot in `link #-48`'s layout; the jump tables
  `$fefba0`/`$fefbcc` as two `switch`es with their fall-throughs), every type × state cell over the snapshot's own trees or
  staged on a real object, the packed-longword sites through one helper family (`packed_add`/`packed_sub`/`pair_high`/
  `pair_low`, hoisted by O into `m68k_idioms.h`), the frame staged STALE on both shores. SLICE O (`src/aes/obdraw.c`): ob_draw
  and ob_change over their frames, and THE ALCYON ENTRY (`src/aes/obdraw.S`): ob_draw hands everyobj just_draw BY VALUE
  (`$fea08c`), and a target ob_draw handing it `$fe9a88` would run the ROM's just_draw inside our build — which the (V) bench
  REFUSES (RED-proved: 248,590 cycles in the AES's spans, refused by name) and which a rebuilt ROM cannot owe. The entry repacks
  everyobj's 10-byte Alcyon frame into the GCC call (image base 0, each word sign-extended into its slot); it is target-only
  glue (`atari/target.mk` ALCYON_ENTRY_SOURCES, filtered out of TRANSCRIBED_SOURCES so the `.globl` pin stays exact), Tier 3
  counts it as glue (`tier3.ALCYON_ENTRIES`, T→G), `test_transcribed.py` pins its `.globl`s to that list. Its four mutants,
  judged by Tier 3's second differential (no host surface sees it): x/y swapped, the object pushed as x and image base 4 RED;
  the three `ext.l` dropped GREEN — equivalent BY GCC's design (R3: the m68k callee re-extends an `int16_t` from the slot's
  low word at every -O level), kept as the correct promotion. THE REVIEW: R1 (just_draw) proved J's "tree 2's TEXT has no
  writer" ROM finding WRONG — sh_draw (`$feada0`) stores the shell's command through ad_pfile (`$c7a2` = tree 2 obj 2's ob_spec,
  TEDINFO `$d18c`) at `$feadca` right before its ob_draw; the -1 is the resource's placeholder until the first launch, so TEXT is
  NOT app-only (RETRACTED, here and in AES_MAP) — and found five non-equivalent survivors J's 114-mutant sweep had passed (every
  snapshot colour word has border colour = text colour; the only negative-thickness BOXTEXT carries no state; the menu's titles
  are exactly as wide as their labels; no CHECKED case moved ad_intin), a CROSSED h=0 case whose borrow carried back (y ≠ 0),
  and a TITLE+SHADOWED row in black that drew like STALE. R2 (ob_format and cross-cutting) found te_just's WORD compare
  unpinned (0/1/2 only — `$0101`, 5, -1 kill two survivors), the priced worst row a case choice (a FULL 38-character path, est.
  0.88), and duplication across slices (two `object_word`s, three spellings of "tree N of a resource", copied `tedinfo` /
  `string_at` / REGISTER / loggers / raw-text seeders / `real()`, PARM missing from `aes.RECORDS`, literals the headers name).
  R3 (ob_draw / ob_change, C faithful instruction by instruction) found O's desktop-band case DEAD — its TEXT lay wholly above
  the snapshot's clip, so te_ptext was never read and any string passed — and THE UNREACHABLE FONT MACHINE: J's default
  `IBM_FONT_CACHED` staged gl_font 3 over the VDI's SMALL face, a pair (3, small) no AES path makes (gl_font's two writers,
  gsx_start `$fdaace` and gsx_tblt `$fdad4a`, keep it true to the VDI), so every IBM label over the default machine drew in the
  6×6 font, and one case's "screen changed" evidence held only because of it (in the real font the title redraws the
  snapshot's own pixels). The lesson: a machine is DERIVED from a ROM run, never poked — a poked cache can describe a state the
  machine cannot reach, and every differential over it still passes. R3 also recorded the D0 ob_draw / ob_change leave for the
  bindings `$fde2fe` / `$fde32c` (`## Not reconstructed`). THE FIX (one agent): IBM_FONT_CACHED re-derived as the write-delta of
  the ROM's own gsx_tblt(IBM, 0 chars) (`case.written_by`, the new helper `continued_from` now shares), the whole-screen-clip
  machine built OVER it, a permanent pin that the cached font draws the VDI's own IBM face, the menu-title case split into
  "redrawn in place = the snapshot's pixels" and "drawn elsewhere"; the desktop band staged as sh_draw leaves it in both J and
  O (`AES_AD_PFILE` `$c7a2` in aes.h) plus R3's dead-staging probe kept as a pin; R1's five survivors and R2's two as permanent
  cases; the full-path ob_format row (0.87, the new worst); one `object_word`, one `aes.resource_tree(index, image,
  application_global)`, `isr.REGISTER` / `answer_d0` / `frame_long_logger`, one raw-text seeder, PARM in `aes.RECORDS`; obdraw.S's
  REGISTERS line widened (D0-D1/A0-A1 with the C core); and the wave-2 files' inline `pair_high`/`pair_low` folded (gsxif.c,
  grlib.c, gemgraf.c — byte-identical, `cmp` of all 9 objects under three flag sets). The J label rows' whole-run counts moved
  with the real font; no (V) gated ratio moved and no row outside wave 3 did. MUTATION (strict), honestly as two runs: the
  authors' sweeps — J 109/114 (5 equivalent), U 32/32, O 41/43 with 2 ABNORMAL (`last-nil`, `last-head`: everyobj's guard aborts
  on the full battery; each KILLED cleanly by `-k scroll`) — and the reviews showing J's true tally 109/114 PLUS 5 non-equivalent
  holes (R1) and ob_format 2 more (R2); the fix re-run, all 209 over the fixed batteries: 199 KILLED, 8 SURVIVED (all equivalent:
  J's clip-w-only, clip-h-only, image-row-16, marks-always, marks-low-byte; R1's set-aside label-chars-byte,
  userdef-state-low-byte, shadow-after-neg-signed), 2 ABNORMAL (O's two, KILLED by `-k scroll`).
* **Wave 12 band 3 wave 0 (2026-10-02) — THE EVENT DOOR, the object editor, the window library's pure half.** A read-only
  SCOPING pass first (the band-3 inventory read from the bodies: ≈16 KB, 87 routines unported; each classified by how it
  reaches the scheduler — LOOP, ONE call, or none — measured through the oracle; the band-4 code band 3 reaches named: eight
  door entries and five non-blocking leaves to port in band 3; the slices and waves F ∥ O ∥ W1, then W2 ∥ G, then M, then S;
  the map's errata), then three slice agents in parallel, four reviewers (R1 slice F; R2 slice O; R3 slice W1; R4
  cross-cutting) and three fix agents (FD ∥ FO, then FW): 38 ✅ routines, 121 Tier 3 rows (gr_stilldn 7, gr_watchbox 4,
  ap_sendmsg 3, ct_mouse 4; the object editor 48; the window library 55). SLICE F — THE EVENT DOOR + pilots
  (`include/aes/evdoor.h`, `src/aes/evdoor.c`, `test/aes_event.py`; `src/aes/grwait.c`, `apmsg.c`, `ctrl.c`): one wrapper per
  door entry keyed by ROM address — on target an INLINE Alcyon call (a `.S` call-out repacking GCC's slots measured gr_stilldn
  at 1.84; the inline frame 1.09, then 1.04 once a constant-zero argument pushes the already-zero A1), on the host a nested
  oracle run of the ROM's routine over the candidate's image, the Line-F hop checked first; the BIOS trap's register save
  under the keyboard poll (`$8de..$905`, the caller's registers) the one thing that differs by nature, dropped by name in
  Tier 1, priced rows moving savptr into the stack band; door cases unpoisoned (the pass inverts the fork queue / CDA / EVB
  links: measured), stale staging their stand-in. Tier 3's letter (E) was taken, so the mechanism is (EV): our run WATCHED at
  the door's entries (the kit's `RomBench.measure(watch=)` + `emu.bench_door_arm`, its own commit), each door call a window
  off the ROM's own cycles, AES cycles outside a window refused — RED both ways (a delayed body OVER while the whole run stays
  ~1.0; an unwatched run refused) and five target mutants of the door judged by Tier 3's second differential. SLICE O
  (`src/aes/obedit.c`): ob_edit (812 B, not the inventory's 1,942) and ten gemobed helpers, Alcyon C over their own read /
  write order, three host slots, every EDCHAR case from the ROM's own EDINIT; ob_stfn 1.17 → 0.95 by holding the inlined
  template in a register (`CURSOR_BARRIER`). SLICE W1 (`src/aes/wmlib.c`): gemwmlib's non-blocking half, 23 routines, every
  machine derived from the ROM's own window chain (wm_create → wm_open → wm_set: move, sliders, sizes, the drawing hold,
  NEWDESK), every D0 the desk's bindings store modelled (wm_delete's and wm_get's address leaks, wm_calc's height);
  w_bldactive's -1 test kept apart from its body (1.15 → 0.12). THE REVIEW. R1 found THE FOUNDATION FLAW: 4 of gr_stilldn's
  9 priced rows stood on ev_multi answering "no event" — under the snapshot's indisp = 1 the dispatcher `dsptch` (`$fe387c`)
  is a bare `rts`, so ev_mwait's blocking call (`$fe40de`) RETURNED where the machine would block; a process calling ev_multi
  always has indisp 0 (switchto clears it on every switch in), so that outcome is unreachable — and NESTED_RUN_INSNS, the
  slow-path case and Tier 3's RED-proof row all stood on it. And `pd0_running()` was a POKED hybrid: acancel over
  leaf_machine's poked rlr left PD_STAT 1 and PD0 on the not-ready list, chaining PD1 into the ready list (`[PD0, PD1]`); the
  "parked" machines ran PD0 while it was parked in its own evnt_multi (ap_sendmsg "to PD0 parked" was PD0 sending ITSELF a
  message, sender word 0). R1 also proved F's mutation total OVERSTATED: the child-process refusal cases bound the hook into the
  SHARED `build/` lib while the child called the PRIVATE mutant lib, so 13 "kills" were segfaults (rc -11) that fail with no
  mutant at all — honest 53 K / 8 S, three of the survivors REAL holes (gr_watchbox's rectangle, x/y order and leave flag were
  never observed: ev_multi's rise is satisfied whatever MOBLK it gets) — and that (EV) never checked the ROM's event-layer
  cycles against our windows. R2 (slice O; no C divergence, instruction by instruction) found the "unobservable" refused-key
  `start++` OBSERVABLE (an application's objc_edit index of `$7fff`: the scan's word wraps and the fill runs — a FALSE
  EQUIVALENT), the stretch's `copied > 0` unpinned (a 255-character validation string), one unmeasured poison opt-out, the
  Tier 3 rows below the worst (80 placeholders: find_pos 1.058, ob_stfn 1.035; STANUM; 'N'), three pointers never tagged.
  R3 (slice W1) found WM_MAX_DEPTH pinned only to ≥ 4 (depths 4 and 5 survive), 19 untagged pointer cases, the mutation total
  reproducible only with `-x` (strict: 149 K / 8 S / 5 ABNORMAL — real FAILs, then an abort or a 5-minute hang), the held
  w_move's D0 "pin" circular (the ROM leaves the caller's D0), and reconciled W1's "ob_draw never returns seven levels down"
  with band 1's everyobj divergence counted from the start object. R4 (cross-cutting) found wmlib's four frames not
  `_Static_assert`ed to their host slots (RED: a halved slot built and passed), DERIVATION_INSNS's stale justification and
  unpinned margin, duplicated helpers (`stored_nothing`, frame packing, retyped WF_* field numbers — field 13 had three names),
  `aes.line_f_call_sites` scanning the AES text per name at import (1.75 s per process), the addrs.h wm_* rows without "read:",
  and the AES staging window full. THE PRINCIPLE (the fix list, binding): a case may only stand on a state the real scheduler
  produces; a nested run that reaches the blocking dispatcher is REFUSED ("would block"), and a running process is DERIVED —
  the event it waits for delivered, the ROM's own scheduler run — never rlr / indisp / PD_STAT / the lists poked; a derivation
  impossible within one oracle run is refused with its measured reason. THE FIXES. FD: the nested run stops at `dsptch` and
  refuses by name (a kit addition: `emu.run` reports `checkpoint` through a new shim export `osh_final_pc`); 2 of the 4 rows
  re-staged on a satisfied event, 2 turned into child-process "would block" refusals, the "PD0 parked" gr_* rows removed;
  NESTED_RUN_INSNS 20,000 at a pinned margin of 20 over the deepest reachable call (ap_rdwr handing to PD0's parked wait, 933);
  `aes_event.machine(woken=…)` = an event delivered, disp's loop `$fe4dda` run until the woken process leaves its evnt_multi at
  `$fe6c5c` (Return wakes PD0 in 1,972 instructions, the left button 1,412, the mouse on the menu bar wakes PD1 in 1,539),
  then the ROM's gsx_moff — a scheduler-invariants test RED over the old poked mix; ap_sendmsg "to PD0 parked" now sent BY PD1;
  the child binds into its own lib (RED: the old binding rc -11); every door call's frame compared with the ROM's own call's
  (watched at the entries — killing R1's three holes), and Tier 3's (EV) watching the ORIGINAL too, windows and frames equal
  both sides (RED: a window one cycle dearer, a ROM timer +1); DERIVATION_INSNS' margin enforced; one cached Line-F call index
  (1.76 s → 0.03 s, identical answers for all 280 names); the staging window 8 KB → 16 KB with every claim at its old address;
  GSX_SHOW_AT_ONCE one name. FO: the `$7fff` case landed in 1.1 s (the save-under buffer staged as placeholders: the ROM run
  35,836,288 → 1,944,393 instructions, budget re-measured by the test), the 255 / 256-character cases, the opt-out dropped,
  the worst rows registered (find_pos 1.06, ob_stfn 1.04, instr 0.98, check 0.59, ob_edit 0.80), the tags, one INDIRECT /
  EDITABLE / stored_nothing. FW: an 8-box desk (six levels below object 1) plus a 6-box one beside it (the 8-box tree alone
  turned the wrong-root mutant ABNORMAL), R3's 19 tags folded in, the held arm asserting `stored_nothing` and the caller's D0,
  four `_Static_assert`s (RED each), one W_BORDER and one WF_RESVD name, `aes_event.frame_of` / `window_created` the single
  source, the window machines over the scheduler's running PD0 (pinned: rlr == [PD0], indisp 0); objects byte-identical.
  MUTATION (strict, a private `.so` per mutant, NO `-x` credit), honestly as three runs: the authors claimed F 59 / 61 killed,
  O 132 / 136 (4 "equivalent"), W1 154 / 160 (6 equivalent); the reviews showed F at 53 K / 8 S (13 kills were segfaults of a
  mis-bound child), O's `start++` a false equivalent plus two unpinned arms, W1 at 149 / 8 / 5 ABNORMAL without `-x` plus two
  real depth holes; the fix re-runs on the final code — F host 61: **59 KILLED / 2 SURVIVED (equivalent) / 0 ABNORMAL**, F
  target (Tier 3) 7: **6 KILLED / 1 SURVIVED** (equivalent: no caller passes a non-zero second rectangle, timer or message);
  O 143: **139 KILLED / 3 SURVIVED (equivalent) / 1 ABNORMAL** (bus-find-first: SIGSEGV in all three attempts, not counted
  killed); W1 162: **156 KILLED / 6 SURVIVED (equivalent) / 0 ABNORMAL**.
  Code-review gate (4 finders + verifier): the button pressed through the VDI's mouse interrupt (AES, VDI and interrupt state
  agree — the glue-only press was a state no hardware holds); interrupt-level derivations stand on no lever; every
  process-level derivation refuses a dsptch; the child binds the VDI vector too and refuses ANY exception (one had escaped
  the ctypes callback and read as "served"); gr_watchbox's second pass pinned to its wait; the door watches exact entry PCs
  (kit stop sets); the general ev_multi arm removed (a compile error until a caller needs it). Re-sweep after the child fix:
  F host 62 → **60 KILLED / 2 SURVIVED (equivalent) / 0 ABNORMAL**, target 6/6 KILLED.
* **Wave 12 band 3 wave 1 (2026-10-02) — the window messages and update, the drag loops, the menu library.** Two slice
  agents in parallel, four reviewers (R1 slice W2; R2 slice G; R3 the shared machinery; R4 cross-cutting), a fix list with
  one binding DECISION, then three fix agents (FS first, then FG ∥ FW2) and a finishing agent. Result: 29 ✅ routines and
  91 Tier 3 rows (W2 45, G 46), every one within the bar.
  - SLICE W2 (`src/aes/wmupdate.c`, `wmupdate.h`, the target-only `wmupdate.S`): 13 routines and four door entries
    (tak_flag, unsync, ev_block, ct_chgown). draw_change hands everyobj newrect BY VALUE. On target that is an ALCYON ENTRY
    for newrect AND one for mkrect: before it, our target newrect handed the ROM's mkrect, which is ROM AES code inside our
    build, and (V) refuses that. newrect's two cut rows were re-priced honestly as a result (0.81 → 0.67, 0.89 → 0.72).
  - W2 found the UNBALANCED END_UPDATE deadlock (a ROM finding, pinned on a ROM-produced state) and left the hand-over of
    the lock to a waiting process unpinned. Four overlapping-window arms were left over the bench's cap (Tier 1 only).
  - SLICE G (`src/aes/grdrag.c`, `mnlib.c`): the drag loops and the menu library, 16 routines plus gr_draw / gr_xdraw /
    `$fe86c2` folded. post_button joined the door, and ev_multi gained its two-rectangle target shape. The door stopped
    laying back the Line-F mask word `$cc44`: measured, 19 Tier 3 companions of routines that make their own masked return
    after their last door call failed with it laid back. The child binding gained just_draw.
  - G left "every state after the first pass" UNPINNED as "needing the mouse or button to change inside one run".
  THE REVIEWS.
  - G's COVERAGE WAS WEAKER THAN CLAIMED (R2). The unpinned arms were a harness limit, not a machine limit. R2's prototype
    delivered the ROM's own ISR at the k-th door entry on both sides. With it, mn_do reached MN_IN_MENU and exited with an
    item chosen, byte-identical, and four real mutants of those arms that pass the whole battery died
    (exit-title-item-swapped, in-menu-button-inverted, exit-no-restore, exit-item-redraw). The drag steps and both busy
    loops were reachable the same way.
  - Three of G's "equivalents" were FALSE. bar-height-wchar: high resolution is derivable from the ROM's own gsx_wsopen.
    down-depth-1 and do-find-depth-2: an item with a child is ordinary resource data. do-item-not-cleared was reachable by
    interrupts.
  - Every G machine ran with the cursor HIDDEN, so xdraw-no-cursor (gr_xdraw's moff/mon dropped) survived. pd_nameit's
    finding and comment were wrong: strscn writes no NUL. rc-no-bus-flag was an invalid mutant.
  - R1 (W2): survivor 96 was a FALSE equivalent. rc_union writes INTO `old`, so a far zero-height move redraws more.
  - R1 measured the four "Tier 1 only" arms as priceable over title-bar windows. R4 found that the "their arms are priced
    below" comment was false: topped's redraw arm, the old top's w_cpwalk and wind_set(13, 0)'s release were priced by no
    row, shown by an llvm-cov run of every companion.
  - R1: all 12 of W2's ABNORMAL mutants were KILLS. Serial runs lost them to the first abort, and drawing cases CAN run in
    a child.
  - R1: ev_block's "answered" door row stood on an UNREACHABLE state. Its only caller hands code 4 after tak_flag refused,
    and amutex refuses again. The unsync hand-over looked derivable from ROM runs alone.
  - R1 recorded the target D0 divergence under a held lock.
  - R3 (shared): the nested-run cap was broken by mn_do's two-rectangle ev_multi (1,237 × 20 > 20,000) while the pin
    checked the wrong call. The host-slot mask was at 60 of 64 bits. The default child binding still dropped walker calls
    silently. The `$cc44` comment overstated (only NON-EMPTY masks are written). ev_block's `ad_windspb` read was unpinned
    (equivalent).
  - R3 ran the RED W2 had not: with the Alcyon entries bypassed, every draw row is REFUSED by the bench (19,060 cycles in
    the AES's own spans).
  - R4 (cross-cutting): "refused where the ROM blocks" was spelled four times and the child-first guard twice. The routine
    handed by value was copied three times (C), and so was the walker map (Python). `_cached`'s cache never hit.
    `AES_ROM_GR_WAIT`'s comment had the two-box rule wrong, and mnlib.h carried a "band 4" label.
  - R4: import cost — test_aes_wm_update's own import was 5.2 s (40 ROM runs for `settled_mask_word`, 259 merges), and
    test_aes_event now imported the batteries at module top.
  THE DECISION (the fix list, binding): adopt interrupt delivery at door entries as shared machinery. It obeys THE
  PRINCIPLE because:
  - an interrupt arriving while a process is inside an event call is a REACHABLE interleaving;
  - its effect is a ROM-run delta of the ROM's own ISR, never a poke;
  - both sides receive it at the same door-entry ordinal, and the frame comparison and (EV)'s window equality still hold;
  - a RED proves the injection is applied on both sides.
  THE FIXES.
  - FS (shared):
    - `aes_event.interrupted`, with one correction measured: an `emu.run` inside a watched run's stop derails it, so each
      interrupt is computed with no run in flight and laid in at the entry. RED on each side and one ordinal off.
    - the child's register hook always bound: walked routines are served or refused BY NAME (exit 5).
    - the nested-run margin checked at run time, the cap 30,000.
    - the host slots' held flags an array of bytes; one `ALCYON_ROUTINE` (objects identical); one walker map.
    - `refused_where_the_rom_blocks` and `returns_in_a_child` in aes_event; `shown_machine`; moves that keep a held
      button; aes_event imports no test module.
  - FG:
    - mn_do's ten later-pass sequences and nine drag sequences through interrupts.
    - an item with a child staged from the desk's spare objects (a G_BOX: the first version's blank G_STRING let
      down-depth-1 survive).
    - cursor-shown machines; pd_nameit's nine-character case; the conventions.
    - a high-resolution workstation built from the ROM's gsx_wsopen + gsx_start.
  - FW2:
    - five rows priced over title-bar windows and wind_set(13, 0)'s release over an area (0.70–0.75).
    - survivor 96 killed; ev_block's answered row dropped (`NEVER_ANSWERED`).
    - unsync's HAND-OVER PINNED (`aes_event.parked`): PD0 holds the lock and parks, the screen manager queues on it, and
      Return wakes PD0. The door refuses it as a YIELD.
    - 14 drawing door users guarded in a child; the import at 2.4 s with 45 rows.
    - THE WOULD-BLOCK / YIELD SUBSTRING BUG: the core's generic halt line names "a call that would block … or yield", so
      `"would block" in stderr` passed a yield as a block (measured: the RED did not raise). `BLOCKS` / `YIELDS` now match
      the dispatcher's own words.
  - FINISH:
    - the high-resolution mn_bar case DROPPED as an unreal machine. A composed low/high workstation writes 216 B below the
      screen base in a 160 stride, over MASKed boot-noisy bytes (the noise test went red). A real resolution switch is not
      derivable, so bar-height-wchar is unpinned again.
    - the cap raised to 40,000 from mn_do's interrupted first ev_multi (1,697, pinned exactly), which pins pass 1's
      interrupted wait.
    - every block / yield match spelled by the dispatcher's words.
    - the Tier 3 pricing of interrupted rows NOT landed. Its blocker is measured: it needs a kit change, so it was deferred
      (`## Not reconstructed`).
  MUTATION (strict: a private `.so` per mutant, xdist, no `-x`), honestly:
  - W2 claimed 123 KILLED / 14 SURVIVED / 12 ABNORMAL of 149. R1 measured **136 / 13 / 0** with probe 96 and the child
    cases, and FW2's re-sweep on the final code confirmed **136 / 13 / 0**: the 13 equivalent, `## Not reconstructed`.
  - G claimed 142 / 9 / 0 of 151, the 9 "equivalent". Honestly, of 150 valid mutants, 4 of the 9 were killable, and 5
    mutants R2 wrote against the "unpinned" arms survived the battery.
  - FG's re-sweep of 169 (150 + R2's 6 + 13 on the newly reached arms): **165 / 4 / 0**. The finish's dropped
    high-resolution case brings bar-height-wchar back to SURVIVED, so it stands at **164 / 5 / 0** (derived, not
    re-swept): 3 equivalent, door-post-words-swap latent, bar-height-wchar unpinned.
  - G target (Tier 3): 8 — **6 KILLED / 2 SURVIVED** (post-words-swap; post-no-d2-clobber, nothing live in D2).
  - The finish's 2 logic changes (the cap, the delivery in `rom_s_first_call`): **2 KILLED**.
* **Wave 12 band 3 wave 2 (2026-10-02/03) — the forms and the alerts; interrupted rows priced.** A foundation agent (K)
  first, then two slice agents in parallel (M1 the event-free half, M2 the forms that wait), four reviewers (R1 K and
  M2's machinery; R2 slice M1; R3 slice M2; R4 cross-cutting), a fix list, then two fix agents in parallel (FK the kit and
  the shared machinery; FM the forms). Result: 16 ✅ routines, 81 Tier 3 rows (K 4, M1 20, M2 51, FM 6), every one within
  the bar; no pre-existing row's numbers moved.
  - K (FOUNDATION + KIT, the kit's own commit): the bench run's own write ledger (`osh_run_bench` clears it after its entry
    stores; `emu.bench_writes`); `rom_bench.watched_original` and `RomBench.measure(original_watch=)`, the original run as
    a watched bench run entered as `emu.run` enters it, every vet live. In the project: the `delivered` ninth field,
    deliveries laid on all four of a row's runs and in the snapshot's sweeps, a call reaching dsptch refused by name on
    every watch; the 18 returning interrupted cases of the time through the bench's second differential; mn_do's,
    gr_dragbox's, gr_slidebox's and gr_rubwind's worst interrupted rows registered (0.63 / 0.80 / 0.75 / 0.80); keys on the
    in-place delivery path (`key`, `typed`) in ONE watched run, set aside and continued at each entry (linear where it was
    quadratic). Found on the way: `run_watched` entered with the previous run's registers, so the BIOS trap save under
    the keyboard poll differed between runs (red under xdist); now seeded and pinned.
  - M1 (`src/aes/fmlib.c`): fm_strbrk, fm_parse, fm_build, find_obj, fm_inifld, fm_keybd, dq, fq — 100% regions, lines
    and branches (64/64) under llvm-cov. fm_strbrk has no bound on lines or buttons; button buffers are 11 bytes against a
    31-character cap.
  - M2 (`src/aes/fmdo.c`): fm_button, fm_do, fm_dial, fm_alert, fm_show, eralert, fm_error and the bell; ev_button the
    sixth door entry; K's `Typed` generalised into `Waits`; `double_click` through the VDI mouse ISR. The bell is BIOS
    Bconout by `trap #13`, not the DOS glue the brief named (`bios_trap_constant_char`: the register shape had cost 1.09).
  THE REVIEWS.
  - THE REAL DIVERGENCE (R2): fm_strbrk's 5th button or 10th line stores at `$ff1100` — object 11, tree 2's object 1,
    ABOVE RAM. The oracle drops the store (an ST loses it or bus-errors); the host C wrote it into the image: RED,
    `0xff1100: oracle=0x00 cand=0x45`. M1's own `INDEX_STEERS_THE_PASS` comment had seen this walk ("where the oracle's
    store is lost and the host's lands") and opted the pass out rather than refuse it; and R2 measured the opt-out wider
    than its measurement (15 of 18 direct cases pass poisoned).
  - STALE CHIP STATE ACROSS BENCH RUNS (R1): `watched_original` installed no PSG / named-hardware seed, so it read the
    previous run's — the printer's Bcostat answered $0 or $ffff by which case ran before, and the refusal `emu.run` makes
    ("nothing declared") disappeared. `parked` entered with the previous run's registers (94 bytes of its machine
    differed). `Waits` checked its entry only on an ordinal's first sight and counted `pending` across runs (R1, R4: a
    schedule handed to another routine laid a key at a non-ev_multi call). Two spellings of the watched entry; tier3.txt's
    cost cells ran together on 29 rows.
  - THE HAND-WRITTEN INTERRUPTED LIST (R4): K2's "every returning interrupted case gets the second differential" was a
    list over three modules; M2's **35** returning cases (fm_do 27, fm_alert 7, eralert 1) were not on it. All 35 passed
    when R4 ran them — coverage, not a divergence. The deliveries were derived twice per registered row (+3.4 s of
    test_boot_snapshot import per worker).
  - FALSE "UNREACHABLE" (R3): fm_error's `1` answer is reachable — an application's form_alert(-1, …) leaves DEFAULT on
    a message line of the shared alert tree, and Return in any later alert then answers -1. Two mutants survived both
    batteries on it (fm_error `return 0`; fm_alert `default_button > 0`).
  - FLATTERING ROWS (R3): fm_do's worst was picked (0.70), not measured — every row typed into an EMPTY field, and the
    "per-key shapes, each priced" had no rows; with the path field filled as fs_input fills it, 0.75. The bell's 1.06 was
    not its worst (1.07 with the console mid-escape; the excess is the d2/a2 save round `trap #13`).
  - Also: fq's choice of gl_cda over gl_kowner unpinned (a surviving mutant, R2); the fm_keybd errata misread `$fefa64`
    (R2); eralert's ">6 maps into 0..6" reason wrong (R3: the critic keeps ~error's high byte); icon digits past 3
    unstaged; the over-cap alert shape unnamed; frame-word helpers written three times, flag masks and the fm_keybd
    answers redefined per file, test helpers re-implementing `aes.parent_of`, `typed`, the ROM's ob_offset; magic numbers
    in the new tests (R4).
  THE FIXES.
  - FK: one chip declaration (`emu.install_chip_seeds`) and one entry spelling (`rom_bench.original_entered`) under every
    bench entry of ROM code, RED at the kit level; `parked` seeded (RED: two stale register files, one machine); `Waits`
    checks its entry at every call and counts per run; THE SECOND DIFFERENTIAL BY CONSTRUCTION — `aes_event.interrupted`
    runs it for every returning case (56 today), the hand list deleted; deliveries derived once per registered row (32
    deliveries runs at import → 16); tier3.txt's cost columns sized from the data; `_registered_runs` refuses a delivered
    row; README's stale line.
  - FM: the bus accessors refuse BY NAME a store at or above `ST_RAM_BYTES` (five-button and ten-line fm_parse cases, the
    bound itself pinned both sides; no existing case wrote there); `INDEX_STEERS_THE_PASS` re-measured after the refusal
    and made per case (11 of 18 steer above RAM and refuse; 7 run poisoned); fq with the keyboard handed to PD1 by the
    ROM's own ct_chgown; fm_error's `1` and the negative default as permanent cases (the machine the ROM's own fm_alert
    run leaves); the long-path fm_do rows (0.75 ×3, 0.72) and the mid-escape bell rows (1.07 ×2) registered; icon digits
    4, 5, 6, 9, ':'; the over-cap alert named; the flag masks in `objects.h`, one frame-word helper (objects byte-identical,
    106 target objects compared section by section); the test duplication and magic numbers.
  MUTATION (strict: a private `.so` per mutant, xdist, no `-x`), honestly:
  - K: 29 — 28 KILLED / 1 SURVIVED (the derivation run's register seed: equivalent, the compared replay is seeded) /
    0 ABNORMAL; its 7 kit mutants all KILLED.
  - fmlib.c: M1 claimed 60 / 3 / 0 of 63 (first pass 55 / 5 / 3). R2's fq-kowner SURVIVED it. FM's re-sweep of 73 (+R2's
    10): **66 / 7 / 0** — following-unsigned equivalent; build-no-min and build-row-unsigned UNREACHABLE (not equivalent:
    each needs the 5th button / 10th line, which faults first); R2's four equivalent on every reachable machine.
  - fmdo.c + evdoor.h: M2's final 102 / 4 / 0 of 106 (first pass 98 / 8 / 0). R3's two SURVIVED it (the false
    unreachable). FM's re-sweep of 108: **104 / 4 / 0**, the four equivalent.
  - The store-above-RAM refusal: 8 — **5 KILLED / 3 SURVIVED**: ram-word-as-byte equivalent (a word store is even after
    the odd-address refusal); ram-long-unchecked and ram-long-as-word UNPINNED (`## Not reconstructed`).
  - FK: 19 — **17 KILLED / 2 SURVIVED**: the chip declaration dropped from `parked` and from `_continued_at`, equivalent
    today and unpinned (`## Not reconstructed`).
* **Wave 12 band 3 wave 3 (2026-10-03) — the file selector; a case's own budget, sessions priced by their slices.** A
  foundation agent (K) and a slice agent (S1, the event-free half) in parallel, then S2 (fs_input) on both; four
  reviewers (R1 K's machinery and S2's additions to it; R2 slice S1; R3 slice S2; R4 cross-cutting: cost, bands,
  duplication, conventions); a fix list; two fix agents in parallel (FP performance and mechanism; FT tests, rows and C
  conventions). Result: 11 ✅ routines and one ⚠️, 74 Tier 3 rows (K 5, S1 29 then 32, S2 27 then 37), every one within
  the bar; no pre-existing row's numbers moved. BAND 3 IS COMPLETE. The kit is untouched.
  - K (FOUNDATION, `test/aes_event.py` + `bench/tier3.py`):
    - THE PER-ROW BUDGET. `DERIVATION_INSNS` (1.5 M) and its margin of 5 are untouched; a case that needs more passes
      `budget=`, which is also its run's cap, held by name: above the default, fitted by the margin, and — for a run that
      ended — not stale (`DERIVATION_STALE` = 2), so 5N <= B <= 10N. A registered row records it (`InterruptedRow`).
      RED on fm_do's 38-key session (728,664 instructions) and on the ROM's own fs_input (635,277), each refused under
      the default in the default's own words.
    - SLICE PRICING. Measured first, and it changed the design: door calls alone do not cut fs_input under the cap — its
      first door call comes after 354K–371K instructions — so a slice end is an ARRIVAL both shores make at one PC:
      `door_call`, `trap_taken` (a VDI or GEMDOS call outside any door call), `ENTRY`, `RETURN`. Both shores run the
      whole session, marked at the two ends; the row is the difference of the marks; our memory must equal the ROM's at
      both, after the same door calls (`vet_the_marks_agree`); a slice past `SLICE_INSNS` (200,000) is refused.
    - Shown on the ROM's own fs_input as oracle on both shores (eight shapes, 5K–185K, summing to the whole) and, C
      against ROM, on fm_do's 38-key session: five rows, 0.67 / 0.68 / 0.76 / **0.77** the last character typed / 0.71 —
      fm_do's new worst (it was 0.75).
  - S1 (`src/aes/fslib.c`, `gemdosif.c`): fs_start, fs_back, fs_pspec, fs_active, fs_1scroll, fs_format, fs_sel,
    fs_nscroll, fs_newdir, dos_snext and the Cconout glue. Machines the ROM's own fs_input stopped at each routine's
    entry over a staged disk and REAL GEMDOS; GEMDOS REPLAYED for Tier 3 (a staged `trap #1` handler with a ledger, the
    script derived from the ROM's own GEMDOS call by call). dos_sfirst's tail extracted as `search_found`, which
    dos_snext shares as the ROM does (dos_sfirst's rows unmoved); `gemdos_trap_word`, the function-word-only trap shape.
    The scoping's "dos_snext shares `$fe3c28`" was wrong: it is dos_sfirst's tail `$fe3a2c`.
  - S2 (`aes_fs_input`): the selector run whole as SESSIONS — 75 returning and 20 cut short at a wait at first, held at
    the end, at the wait, and by every VDI call in order; real GEMDOS on both shores for keys typed ahead and the three
    no-memory arms. Priced as 24 slices of four sessions plus the three no-memory rows. `declare_child_doors` (the
    child's `trap #1` door), `stopped_at(budget=)`; the AES window to 24 KB; K's survivor b21 pinned by the session that
    blocks with nothing delivered.
  THE REVIEWS. Verdict of all four: THE C IS FAITHFUL TO THE ROM EVERYWHERE — R2 and R3 read it instruction by
  instruction and R3 ran 37 more sessions C against ROM; every finding was a test, pricing, cost or convention defect.
  - WHAT WAS PRICED (R1). fs_input's proposed worst, 0.84, depended on where the Return row's cut fell: the selector's
    PUT-AWAY (fm_do's last unsync to the return) measures 0.88 own / 0.98 with thunks in every session, averaged down
    to 0.81 behind fm_do's own key handling. And the registered slices PARTITIONED NO SESSION: 49–93 % of each session's
    ROM instructions were in no row, and nothing said so (no gap hid a row over the bar; the mechanism could not show
    it). A budget could be declared over a run the default covers (the rule tested the declaration's size, never the
    run's need — K's own positive case sat in that window, its `budget=` really raising `emu.run`'s cap); `stopped_at`'s
    budget was not pinned as the cap (a surviving mutant); trap arrivals are matched by ordinal and memory, never by
    count. K's five ABNORMAL mutants were shown honest kills (armed after collection: each KILLED by 7+ tests).
  - THE EVENT-FREE HALF (R2). Four holes, each a mutant passing all 275 cases and a real-data case that kills it: the
    folder test is a BIT test and no staged folder carried a second attribute bit; the 100-name cap was never run under
    a spec that filters (names KEPT against names SEEN); fs_1scroll's arrow and fs_sel's row are WORD tests no case
    pinned. `fmt-kind-first` was labelled equivalent and is only unreachable; `snext-function` was credited a kill its
    full run never finishes. The registered rows were not each routine's worst (fs_back 1.03 at 60 characters against
    1.077 at 250; the with-thunks headlines each ~0.01 low).
  - fs_input (R3). Three order holes shown by surviving mutants: the read block's order (a row put down against OK put
    down), `top := 0` by a read pinned only when the read had a pass to itself, and the survivor `row-folder-is-file`,
    called EQUIVALENT, killed by real data — a NEW ROM FINDING (a spec past ~25 characters overruns the title into
    the first row's kind byte: the row is taken for a folder). Memory between the last wait and the end was held by
    nothing but the VDI arguments. The spin refusal's comment claimed no other path reaches it; one does.
  - COST (R4). `make test` quiet went **140 s → 397 s**: xdist's `load` handed one worker the whole of
    `test_aes_fs_input.py` (391 s of the 397); each session was derived 5 times where 2 are needed and its C run in
    two children; the sweeps and Tier 3 redid a whole session once per slice row; registry import +15.7 CPU-s per
    process and 2.1–2.35 GB peak RSS per worker (the 16 MB image kept per GEMDOS call); `make bench` +56 % CPU. Three
    generations of recording trap handler; `RUN_INSNS` a second budget mechanism; `aes_fs_input` 87 lines, five deep.
  THE FIXES.
  - FP (performance and mechanism; no bench row moved, the table byte-identical before and after its levers; all 1,574
    rows + 29 slices hash identical under the old and the new `merge_pokes`):
    - `--dist worksteal` in the PROJECT Makefile's `PYTEST_ARGS` (no kit change) and `test/conftest.py`, which collects
      the cases of one session back to back so a steal does not split them (the second session test: 163.6 s summed
      when spread → 33.9 s);
    - one derivation per case and one child per session (deliveries per session per process 5 → 2; the digest read
      off the session's own child); the sweeps once per session (`test_boot_snapshot` 195.2 → 97.7 s summed);
      `tier3.Sessions`, one pair of runs for all of a session's slice rows and companions (35.8 → 8.1 s, 26.0 → 4.3 s);
    - `case.merge_pokes` run-wise (import 26.7 → 20.9 CPU-s); `GemdosCalls` keeps the low 1 MB only (peak RSS at import
      2,348 → 510 MB; the bench process 2,500 → 1,278 MB);
    - `make test`, quiet: **140 s (HEAD) → 397 s (the wave) → 193.03 s** (load 2.6) and 194.64 s (load 8.2), CPU-bound
      on ten workers (1,476 s summed, with 111 more tests than R4 measured). The slowest test protocol 75.7 → 37.5 s.
    - THE PARTITION TEST (`tier3.uncovered_stretches`), RED-proved: on the table without the put-away it fails by name
      on two sessions (0.8784 and 0.8767 against a worst registered 0.8389). One test per sliced session, 3–13 s each.
    - The budget NEED-BASED (`_vet_not_stale` refuses 5N <= `DERIVATION_INSNS`; RED: fm_alert's 208,880 instructions
      under 1,500,001, which every size rule passed) and `run_event`'s one number split into `budget=` and `cap=`;
      `stopped_at`'s budget pinned as the cap (R1's survivor killed); `RUN_MARGIN` gone, `RUN_INSNS` a declared budget
      held to the margin by name; ONE ledger machinery, `aes_shell.Table`, under the scripted trap and the replay.
  - FT (tests, rows, C conventions):
    - PINS: a read-only (`$11`) and an archived (`$30`) folder on a disk of their own; `A:\BIG\F?0?.DAT` (101 read, eleven
      kept, no bell) with its replay twin; arrow `$0108`, row `$0100`; five sessions (80 now) for the read block's
      order, `top := 0` in the pass that reads, and the long spec's first row — each of R2's and R3's mutants killed.
    - WHAT THE SELECTOR HOLDS at every VDI call hashed into the ledger on both shores (`held_in`): R3's
      `SELECTED | 0x40` mutant, which neither suggested surface could see (inf_what clears OK's whole state word
      before the first free), is KILLED.
    - THE SPIN'S SECOND ROAD, derived from a ROM run and pinned (R3's mechanism was misread: under the path lie the
      AES's four text buffers, not a linked table): the ROM's own ob_draw of a formatted text whose template runs 77
      characters, then `\*.*` and the close box.
    - WORST ROWS re-registered from `make bench`: the put-away as its own slice in every priced session (0.88), the
      Return and Cancel rows split at fm_do's last unsync, fs_back and fs_pspec at 79 characters (1.04 / 0.96),
      fs_active's hundred 8.3 names (0.83, 0.94 with thunks), fs_nscroll eight rows down (0.80), fs_newdir thirty-four
      names (0.82), two more priced sessions (a root with no drive; a spec that fills the title's scratch).
    - `aes_fs_input` split into `struct selector_run` + five helpers (the entry 19 lines; 258 bytes shorter; 18 of its
      rows moved by -102..+40 cycles, no printed ratio); the glue's park / trap / verdict in one helper per frame shape
      (the target `gemdosif.o` byte-identical); the duplicated constants onto the existing ones.
    - THE CLOSE BOX'S ARM, 1.20 → 0.96. Cut alone from fm_do's end (R1's own argument for the put-away), the close box
      over a root with no drive measured **1.2043 own / 1.2506 with thunks** — over the bar — behind a wait-cut row of
      1.03: GCC had INLINED fs_back's downward scan into fs_input at both of the close box's sites, reloading the
      image pointer every byte (94 and 114 cycles a byte against the ROM's 64), and only the ROM's 849-byte defect scan
      runs it long. The ROM CALLS fs_back there (`$fe815e`, `$fe818a`, Line-F), so the C now does (`fs_back_called`,
      noinline, 78 cycles a byte): the arm alone **0.96 own (0.9553) / 1.00 with thunks**, registered; the wait-cut row
      0.85 / 0.90. 19 fs_input rows moved, no other printed ratio.
  MUTATION (strict: a private `.so` or overlay per mutant, xdist, no `-x`; FT's with a CONTROL every fifteen), as
  finally reported:
  - fslib.c's event-free half + fslib.h + the glue: S1 claimed 223 / 8 / 0 of 231 (first pass 211 / 18 / 1). FT's
    final 239: **231 KILLED / 8 SURVIVED / 0 ABNORMAL** — four equivalent, two equivalent on every reachable machine
    (`fmt-kind-first` relabelled), two unobservable. `snext-function` is KILLED on its targeted run and ABNORMAL in its
    full run (the host's Fsfirst spins over real GEMDOS), not repeated.
  - fs_input: S2 claimed 205 / 8 / 0 of 213 (first pass, stopped at 106, 89 / 14 / 3). FT's final 224: **217 / 7 /
    0** — five equivalent, one equivalent on every staged machine, one unreachable; `row-folder-is-file` KILLED.
  - K (`aes_event.py`, `tier3.py`): 70 — **63 KILLED / 2 SURVIVED / 5 ABNORMAL** (first pass 57 / 8 / 5); the five
    are refused by name at import (a collection error, not a strict kill) and R1 showed each KILLED once armed after
    collection. Survivors: s19 equivalent; b21 unpinned then, pinned since by S2's blocking session.
  - FP (S2's `aes_event.py` additions + its own changes): 57 — **54 KILLED / 2 SURVIVED / 1 ABNORMAL**: a badly chosen
    mutant (it weakens a passing test's own assertion), one equivalent on every caller, and one refused by name at
    import. All five over S2's `declare_child_doors` / `stopped_at` KILLED.
  THE GATE (four finders over the fix pass: no candidate against the shipped C, no stale or order-dependent memo; 18
  items of test honesty, budget doors, memory, duplication and conventions) AND ITS FIX, which supersedes the lines
  above where it says so:
  - TEST HONESTY. One test failed ALONE (`test_a_routine_s_child_doors_are_declared_once`: the registry filled by
    another module's import) — fixed, and every test FUNCTION of the wave's 14 test files run alone, one id each in a
    fresh process: **515 run, 0 red**. Two REDs passed for another reason than they stated and one asserted nothing of
    its name's claim; a GREEN half had no case. Now: the cap's and the frames' budget's refusals are matched in their
    own words; a watched prefix's margin is asserted; fm_do's 38-key session with its keys in the ring (728,664
    instructions in ONE oracle run) is the in-process door case that declares one `budget=` for both its runs;
    `aes_shell.Table` refuses in words a pointer outside it or BETWEEN two entries (`next` too); `ram_in` refuses a
    memory of another length in its own words; the snapshot's three sweeps hold the premise they skip a session's
    other rows on (one machine), by name.
  - ONE BUDGET DOOR. `aes_event.capped_run` is where every in-process differential of the door's batteries is capped
    and vetted: `run_event`, `aes_fslib.run` / `run_replayed` / `run_session`, `test_aes_wm_update.run`. A raw
    `max_insns` is refused by name; a case's own cap is held both ways whichever battery it comes through (it was
    held only when it EQUALLED `RUN_INSNS`); a battery's is `aes_event.battery_cap(insns, deepest=)` — `RUN_INSNS` is
    now `aes_fslib.RUN_CAP`, and test_aes_wm_update's `CASE_INSNS` at a margin of 2 is `CASE_CAP`, re-declared from
    its measured 244,097 at the one margin (1,220,485). `held_to_the_margin` is gone. No verified content moved.
  - DISTRIBUTION AND ORDER. `--dist worksteal` is set by `test/conftest.py` for any xdist run that names no `--dist`
    (it was in the project Makefile's `PYTEST_ARGS`, which every documented override dropped), pinned on real runs;
    the collection order is declared by each battery with the marker `collected_with` — the selector's sessions, its
    priced sessions' cases, and Tier 3's sliced sessions (rows, companions and partition back to back) —
    `test/test_conftest.py`.
  - MEMORY, measured (`/usr/bin/time -l`, one serial process, before → after): the partition test of the selector's
    longest session alone **1,924 → 946 MB**; `test_tier3.py` **3,781 → 963 MB**; `test_boot_snapshot.py` **1,071 →
    730 MB**. A watch was a reference cycle (its own bound methods handed to itself), so a session's marks outlived
    its pricing until a later collection; a kept refusal's traceback held them too. ONE memo class
    (`aes_event.OncePerSession`, built with its computation; `tier3.Sessions(bench)` is one build's) keeps sliced
    sessions alone, the companions' memo keeps four small fields and not two images, the io sweep keeps nothing; a
    pass's memory is its megabyte of RAM; `_trapped` no longer copies sixteen megabytes per GEMDOS re-enactment. A
    test with the collector OFF holds the marks' release.
  - SCAFFOLDING AND DUPLICATION. K's pre-C rig of fs_input (a third staging of its machine, raw object numbers, "no C
    fs_input exists yet") is gone: the mechanism's tests — the eight-shape partition, every RED — run over
    `aes_fslib.fs_input_machine` (the TEN folder; 631,480 ROM instructions, the shapes re-measured) through the public
    `rom_sliced` / `rom_timeline` / `slice_cost`; the private twins are removed. A Tier 3 row carries its registered
    name (`Row.registered`, `tier3.session_of(row)` — a sliced row that names no session is refused), the nine
    re-spellings gone. One `string_in`, one set of selector spans, one `folder` / ROOT_PATH, one UNREAD_BYTE and one
    astray-run helper, one VDI_TRAP; the unused parameters and `DOTTED_DISK` removed; the child's GEMDOS refusal
    (`CHILD_GEMDOS_REFUSED`) reached by a test. A session cut at two trap handlers one of which nests in the other is
    refused by name where it happens (RED on the watch; no session does).
  - CONVENTIONS. The drag distances, the frame offsets (`aes_fslib.active_arguments` / `newdir_arguments`, …) and the
    priced sessions' wait ordinals are named; `SLICE_INSNS` is `DIFFERENTIAL_INSNS`. `read_directory`'s four levels
    are two (`marked_entry_is_listed`, the same statements in the same order): the target `fslib.o` is the ONLY object
    that differs from the pre-fix build (106 of 107 byte-identical), and **15 rows moved** — fs_active's 6, fs_newdir's
    4, fs_input's 5 that read a directory — by +1..+201 instructions and -378..+6 cycles on ours; no ROM column, no
    printed ratio and no verdict moved, none added or removed.
  - MUTATION of the gate fix (strict; Python mutants as private copies loaded in place of the module, in the children
    too; three CONTROLS, all SURVIVED): 53 over `aes_event.py`, `tier3.py`, `conftest.py`, `aes_shell.Table`,
    `aes_fslib.py` and the batteries' group declarations — **51 KILLED / 0 SURVIVED / 2 ABNORMAL** (both refused by
    name at import: a sliced row whose registered name is its label; a watch whose `opened` is not kept — collection
    errors, not strict kills). Over the restructured `read_directory` and FS_EMPTY_ROW: **10 / 10 KILLED**.
  COVERAGE (llvm-cov, -O0, after the split and `fs_back_called`; 492 tests): `fslib.c` **99.27 % of lines** (3 of 410
  missed), **98.51 % of branches** (2 of 134) — the host refusal's taken arm (it runs in a child that aborts: no
  profile) and `act_on_the_object`'s dead upper bound. S1's own build had the event-free half at 100 % (58 branches).
* **Wave 13 band 4 wave 0 (2026-10-04) — the door made rebindable and tak_flag rebound; gemasync's lists; the PDs and
  the pipes.** A read-only scoping of the band first (81 routines / 7,074 B, 74 to port; the switch measured; every
  (EV) row re-priced in prediction — the section intro has it), the orchestrator's rulings Q1–Q7 on its open questions
  (the section intro), then three agents in one tree with disjoint owners — F (the rebinding protocol and the tak_flag
  pilot), A (gemasync's lists), P (PDs and pipes) — four reviewers (R1 slice F; R2 slice A; R3 slice P; R4
  cross-cutting: cost, seams, shared headers, the table, conventions, bands, children, claims), a fix list, and two fix
  agents in parallel (XA the protocol, the lock, the lists and the seams; XP the processes and pipes). Result: 18 ✅
  routines, 55 new Tier 3 rows (50 C, 5 `.S`), every one within the bar or `transcribed`; 88 committed rows moved by
  FLIP 1 and no other. The kit is untouched (ruling Q7).
  - F (THE PROTOCOL, `include/aes/evdoor.h`, `src/aes/evdoor.c`, `include/aes/switch.h`, `test/aes_event.py`,
    `bench/tier3.py`; the pilot `src/aes/evsync.c`):
    - THE THIRD ANSWER. `recreate_call_event_door` answers REFUSED / SERVED (the nested ROM run, as before) / ARRIVED
      ("noted: run the twin"). A rebound entry's wrapper packs its frame and asks as before; the case records the frame
      for the frames-handed comparison and lays the interrupt due at that call; the twin runs; its answer is reported
      to a second hook, `recreate_event_door_returned`. On target the wrapper is `return aes_<twin>(image, …)` and
      nothing else. A wrapper and a hook that disagree halt by name, both ways.
    - `REBOUND` IS DERIVED — the entries whose core the candidate library exports (`aes_event.rebound_in`), and at
      Tier 3 the blob's symbols (`tier3.twin_entries`), held equal; an entry that has a twin AND a `jsr` into the ROM
      is refused by name.
    - THE SHADOW (`aes_event.SHADOWED`, the flip in flight): the ROM routine's nested run over a COPY of the image at
      the arrival, the twin's answer and image held to it at its return. It names where a red is — at the twin's own
      call, not 400,000 instructions later at a session's end.
    - THE REFUSING DISPATCH HOOK (`recreate_dispatch`, ruling Q1): a twin that reaches dsptch asks it before any
      guard, and it refuses by name, a block told from a yield by PD_STAT as disp tells them. WHAT IS COMPARED TODAY:
      the hook and the halt store nothing — the child's image is the image it was handed, the ROM's at dsptch. No C
      runs between an entry and dsptch yet, so NO C IS HELD TO THE ROM AT dsptch BY THIS WAVE; the mechanism that will
      hold one (a blocked rebound entry compared where its twin stops) is pinned on the ROM's side, and THE COMPOSED
      PATH FIRST RUNS IN WAVE 1.
    - TIER 3's ARRIVALS RULE: both runs still arrive at a rebound entry — ordinal, delivery, slice mark, frame held
      equal — and it opens a window of NOTHING: the ROM routine's cycles stay the ROM's own, the twin's are ours. A
      twin that runs any AES ROM cycle is refused by name. Mixed rows (one rebound call, one ROM-served) work because
      windows are per call; the table's sub-line counts "N call(s) of a rebound entry in the own cycles".
    - THE SR SAVE WORDS: ONE named drop exists, psetup's (`aes_event.SR_PSETUP_DROP`). The dispatcher's and
      spl7_save's are named when a case first reaches their bracket — none does in this wave.
    - FOUR RED PROOFS: a mutated twin reds in the shadow at its call (four real C mutants, each killed by the shadow's
      own words over door cases of OTHER routines); an entry left ROM-served while its twin exists reds the derived
      test (a scratch blob with the target wrapper left on `jsr`); a delivery laid one arrival late reds on a rebound
      entry (the ordinal — a delivery tak_flag neither reads nor writes commutes with it, measured over all 56
      interrupted rows: 442 addresses written, none in the semaphore or rlr); dsptch reached is refused by name.
  - FLIP 1 = tak_flag (`$fe4e5a`): count up; the owner is rlr or the count is 1 → the owner stored, 1; else the count
    put back, 0. Its own battery: every lock state the scheduler's own, the lock with a process queued on it included.
    - THE TABLE: 1,689 → 1,743 rows before the fix pass — none removed, 54 added, **88 MOVED, no other row moved**
      (three parsers agree: F's, R1's raw diff, R4's). Every moved row keeps the original's column; ours changed.
    - WHY: the ROM's tak_flag — its body and its Line-F return — is **364 / 384 / 376 cycles** a call (the caller's
      own / free / refused), exactly the old window sizes, now in the ROM's own column; the twin is **226 / 214**
      (free / the caller's own). 80 of the 88 carry "call(s) of a rebound entry" (1–5 calls). The other 8 moved by
      the wrapper's change of SHAPE: wm_update's two releases and "2: the screen given back" (`aes_wm_update` compiles
      30 / 28 cycles smaller now that tak_flag is an ordinary call and not an inline `jsr` with D2/A2 given up), and
      five fs_input slices (-30: a wm_update(0) inside; +8 ×4: a slice ending at the lock's arrival is marked at the
      twin's first instruction, the call's pushes before the mark).
    - HOW FAR: 20 rows moved at two decimals — wm_update's six (0.43 → 0.48 ×2, 0.43 → 0.36 ×2, 0.34 → 0.36, 0.34 →
      0.33), fm_own's three (0.34 → 0.38 ×2, 0.28 → 0.38), wm_set's four (0.20 → 0.27, 0.22 → 0.28, 0.21 → 0.28, 0.36
      → 0.39), gr_dragbox's four (0.78 → 0.77), gr_slidebox's three (0.71 → 0.70 ×2, 0.75 → 0.74). Largest +0.10 and
      -0.07. **The highest moved row is 0.82; nothing is within 0.03 of the bar that was not before; NO VERDICT
      CHANGED** (all still `net`). Against the prediction: wm_update 6 as predicted; fm_own 3 of 4 (its give-back
      takes no lock); every row that takes the lock through them, by one tak_flag window (~380 predicted).
    - R1 re-derived five moved rows instruction by instruction from the two blobs' listings: both columns close, in
      a mixed row too. GCC now inlines wm_opcl into wm_close, so `aes_wm_close` calls `aes_rc_copy` itself (one pair
      added to `transcription.C_CALLERS_OF_TRANSCRIBED_CORES`); `wmupdate.c` is the only pre-existing object of 126
      that differs. Every sliced session's partition test is green.
  - A (`src/aes/evasync.c`): signal, azombie, get_evb, evinsert, takeoff, apret, acancel and geminput's evremove — C
    at 0.48–0.83, no acceptance, no `.S`. Their machines are ARRIVALS: the ROM's own run of a scenario (the
    dispatcher's loop taking a key, a press, a mouse move, ticks; an evnt_multi parked and woken; a message; the lock
    handed over) watched at the eight entries (`aes_event.EntryStops`), each call verified from the machine and the
    frame the ROM makes it with — 187 calls in 20 scenarios, direct and through Line-F; two scenarios over the staged
    application (two delays pending), Tier 1 only. Arms no caller reaches (apret's 100 / 101 and its non-last unlink,
    acancel's filter, signal's evwait test) are pinned by arguments handed directly over ROM-made machines, each
    labelled. All 167 unlabelled arrivals were priced before registering; each routine's worst is its first row.
  - P (`src/aes/pdpipe.c`, `pdpipe.S`): pd_match, fpdnm, getpd, pstart, doq, aqueue, ap_find in C at 0.19–0.98;
    gemdosif's uda_insuper and psetup measured over the bar in C (1.50, 1.24: the image pointer's floor on a tiny
    hand-68000 body) and ship byte-pinned as `src/aes/pdpipe.S` (1.00; region `$fe3970..$fe39a5`, two
    `include/transcribed.h` rows) — the design had put psetup's words in wave 2's `switch.S`; the bench gate could
    not go green without them now. psetup's SR dance is `aes/switch.h`'s pair over `$8998`; its `.S` rows drop
    nothing, the one place the word is compared.
    - THE STAGED APPLICATION (ruling Q2, `test/aes_pdpipe.py`): the ROM's own pstart over a stub of exactly three
      instructions — a push of one immediate, ONE Line-F call of an allow-list (`ALLOWED_CALLS`: ev_mesag, ev_timer,
      wm_update, each with its reason), `jmp (SENTINEL).w` — vetted where it is made AND as it lies in the machine
      where it is entered; `called` is the dispatcher's own run carried on until the application's call parks it.
      Used for: fpdnm / ap_find's third PD, psetup's second frame, two waiters on one list, a third process's
      reader, the lists' two pending delays. No row of any registry runs over one (`case.ROW_REGISTRIES`,
      `transcription.TRANSCRIPTIONS`: held by a test with a companion that registers three and sees all three).
  THE REVIEWS. Verdict: THE SHIPPED C IS FAITHFUL TO THE ROM — R1, R2 and R3 read all 18 routines instruction by
  instruction — BUT FOR ONE BOUNDARY: ap_find's named refusal fired ONE CHARACTER EARLY (R3). Every other finding was
  test honesty, dead code, a helper that was not what its docstring said, wording a measurement contradicts, or cost.
  - THE RULE (R1): **A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION.** 22 real C
    mutants of `aes_tak_flag` against the door batteries of seven routines (1,126 tests): five that are not
    equivalent pass every one — the refusal with a real other owner, the owner's and the pointer's widths, the wait
    list — shadow ON OR OFF, because a door case reaches an entry only in the states its caller makes and the shadow
    sees the same states. `test_aes_evsync.py` alone kills all five. The shadow changes where a red is NAMED, never
    what is covered: "the shadow / the door cases cover it" is no coverage argument for a flip.
  - R1, the rest: the three SR save-word drops were dead code and `switch.h` said they were in use; a RED matched
    any dead child (its `match=` was the head of every refusal); RED proof 4 compares nothing a C wrote (above);
    tak_flag was never handed the one real state whose wait list is not empty; a twin that called another entry's
    WRAPPER would shift every later ordinal on the host alone (the hook counts every wrapper call, both watches the
    outermost) — unreachable for a leaf, a trap for wave 1. The arrivals rule's accounting: CLEAN, to the cycle.
  - R2 (the lists): apret's unlink from its process's list never stored a non-zero link (a surviving mutant; no ROM
    call can show it — ev_multi's aprets take the deepest EVB first); evremove's comment claimed a delay's ticks could
    be taken for a click count (tchange clears the parameter first); the child-first guard's cost and its proposed
    lever both mis-stated (205 children, not ~250; the reduced guard LOSES a kill); "every read is where the ROM
    makes it" pinned for one alias only; the `$c84e` finding incomplete (three writers unread).
  - R3 (the pipes): ap_find's boundary (the ROM serves eleven characters — measured through its own trap door);
    five survivors called "equivalent" killable on machines the ROM itself makes (its own pipe overrun taken 96
    bytes further rewrites PD1's queue pointer and the spare PD's status); no 68000-semantics or re-read mutant in
    the sweep, eight surviving; `called()` re-entered the stub from the harness instead of carrying the dispatcher's
    run on; three holes in the staged application's guards; the attribution opt-out per ROUTINE hid five aqueue
    cases that pass poisoned; "the ROM's run never returns" false for doq's own refusal case; an odd index walked
    past.
  - R4 (cross-cutting): the wave cost +4.3..7.1 s of suite wall; three things A and P asked F for were built and not
    adopted (each then existed twice); the child-first guard keyed by `id(machine)` (a freed dict's address is the
    next one's: RED-probed); the same helper spelt three and five times; `test_aes_evsync` not child-first. CLEAN:
    the table, the pre-existing objects, the staging bands, the host slots, the children, the rows' hashes.
  THE FIX PASS (where it contradicts an author's report or a proposal, the fix report and the final table stand).
  - XP — ap_find SERVES ELEVEN, the one behaviour change: the slot is the frame plus the saved A6's two top bytes,
    the refusal on the twelfth byte; one byte of the target object differs (a displacement, 1,408 B both); its two
    rows did not move. The ROM's side is pinned IN the battery through its own trap door. R3's five "equivalents"
    and eight semantics mutants all KILLED, the "unreachable" count re-read too (a queue pointer the ROM's overrun
    moved to just below the QPB), on machines nothing is poked into. `called` is ONE watched run of the dispatcher's
    loop. The staged application vetted where entered, against pstart's own ledger, by an allow-list. The opt-out
    per CASE with a named reason (69 ids steered, 125 poisoned, measured each alone). doq's refusal KEPT for every
    count with its reason corrected (`## Not reconstructed`); the odd index pinned on three shores; doq's worst row
    re-registered from 23 candidates (+1 row, **0.98**, was 0.97). `offset_by`, `FRAME_LOCAL_WORDS` and
    `onto_the_woken_list` hoisted (the m68k objects of fmlib / obedit / shell_find / evasync byte-identical).
  - XA — the dead drops deleted (one `SR_PSETUP_DROP`); the loose RED matched on its reason, with a test that a child
    dead of anything else is not taken for it; the lock with a process queued pinned (SPB_WAIT left alone); THE RULE
    written into `aes_event`'s docstring and held by a derived test (`test_every_rebound_entry_has_a_leaf_battery_s_
    rows`); "a twin calls a core, never a wrapper" documented in `aes/evdoor.h` and held by the build
    (`test_no_twin_s_object_calls_a_door_wrapper`); apret's non-zero unlink pinned by a labelled case; the case over
    the lever's poked list DROPPED (the strict re-sweep without it kills the same 110 of 117); `AES_TIMER_LIST`
    renamed `AES_ZOMBIE_LIST`; `$c84e` re-derived from every reference in the GEM text (the first report's "never
    returns to 0" RETRACTED). ONE child-first guard, `aes_event.returns_in_a_child`, remembered by CONTENT; the
    FORK guard adopted on measurement for cores that reach no hook (the lists' battery serial 18.2 s with a fresh
    interpreter and a 16 MB image file per call → 12.2 s forked, 10.5 s with no guard; five whole-suite runs under
    xdist green; the three mutants whose C does not return still FAILED cases). Public `as_pokes`, `EntryStops`,
    `dispatched`, `ticks`; one list walker. No shipped-C behaviour change: the m68k objects of `evasync.c`,
    `evsync.c`, `wmupdate.c`, `evdoor.c` byte-identical to the pre-fix tree's, all 1,651 row hashes identical but
    XP's 26, and NO table line moved by XA (the table gained XP's one doq row: 1,744).
  THE PRE-COMMIT GATE (gate 8: four finders over the fixed tree) found NO DEFECT IN THE SHIPPED C — sixteen routines
  re-read against the disassembly, all four build configurations linking, the blobs byte-identical — and eighteen
  items in the fork guard, the watches, the tests' honesty and the conventions. ITS FIX PASS (2026-10-04) changed
  no shipped behaviour: all 130 m68k objects, the bench and the shipped configuration both, are byte-identical to
  the pre-fix build's (one accessor for a record's signed word hoisted over three copies, getpd's accessory-table
  read put on the bus — a host-only difference —, `pdpipe.S`'s mark named); every one of the 1,652 rows' hashes is
  identical; no line of the table moved.
  - THE FORK GUARD IS MADE AT THE CALL. `aes_event.run_core_guarded` makes EVERY run of a hook-free core's C in a
    fork first — the plain pass's AND the attribution pass's, each over the image and the library state the kit
    hands that run (`aes.run_function`'s `first=`) — so the poisoned run is guarded and no verdict depends on the
    test before. The pipes' battery runs behind it like the lists' and the lock's; its 23 fresh-interpreter
    children are forks too (`core_in_a_fork`: the image read back through a shared mapping, the library armed
    first). `returns_in_a_child` is the door users' alone again (`door=` is gone), remembered by THE IMAGE the
    pokes make (two overlapping pokes laid in the other order are another machine: RED-probed, forked once before).
    In a fork: Python's `sys.stderr` is the pipe too (a hook's words were lost without `-s`); a fork whose own
    Python raised says so, traceback and all, under an exit status of its own (it shared 3 with a child's VDI
    refusal, and read "the C did not return"); EVERY hook the library exports is bound to a refuser that names it
    (a core reaching a `void` hook returned having skipped the effect: a vacuous green) — the list held to `nm -g`,
    and the fork-guarded cores held clear of them on any path by the host build's own call graph; the alarm is the
    fork's first act, which bounds an orphan (README: the check that sees one — the old `/ctypes/` check could not).
    XP's ABNORMAL mutant `sem-getpd-unsigned` — an abort in the attribution pass, in process — is a clean KILL.
  - THE ATTRIBUTION OPT-OUT IS ONE SPELLING, AND AN ASSERTION: `aes.run_function(steered=<reasons>)`, used by the
    pipes and the lists alike. A reason names THE WORDS that steer, and a steered case still makes the pass —
    NARROWED to them: every other byte the ROM's run stored inverted. So a wrong or incomplete label fails by name,
    and 467 case ids that ran with NO pass (393 of the lists', 74 of the pipes') now run all of it but those words;
    157 run the kit's whole pass (75, 69 and the lock's 13). The 17 mislabelled
    opt-outs are corrected (pstart: the PD count, then the stack — a new reason; the eight aqueue writes: the index,
    then the lists), two overlap reasons added (a queue pointer, a QPB the run's own copy lands on), and the sweep
    that asks whether each reason is NEEDED (`AES_STEERED_FOR_NOTHING`, on demand) found six named for nothing —
    three aprets that refuse, two doq overlaps, aqueue's one-byte write — which now run what they can.
  - THE WATCHES. `EntryStops` refuses by name a run that would END having executed nothing (an end that is its own
    entry: the "machine" handed on would be the staged one) and a gate that is itself an end, and never arms the PC
    it is stopped at — on which the KIT's watch loop spins for ever (deferred: `## Not reconstructed`); its
    docstring says when an entry is watched again, and what that cannot see. A twin's arrival is BOUNDED to our
    blob's own text. Tier 3 tells a rebound call from a served one by what the watch saw, not by a window of zero.
    REBOUND is read at the moment a run is made, one derivation. The shadows are a binding's own list, emptied when
    a case opens it, a call's place taken before its shadow is made. The settled SR word is derived through the
    vetted run, once per routine.
  - THE DERIVED TESTS. "A twin calls a core, never a wrapper" follows calls ACROSS FILES — the host build's own call
    graph, function by function (`test_no_twin_reaches_a_door_wrapper`, replacing the one-object `nm -u`), its
    compile taken from kit.mk as make expands it; the leaf-battery test says what it holds (that a battery exists).
  - THE STAGED APPLICATION is vetted on EVERY road that runs the dispatcher into its stub (the dispatcher run to its
    aqueue, and the lists' two-delays scenarios, were not), for its ARGUMENT and its width too — the width now the
    call's (`ALLOWED_CALLS`), not a caller's flag; a QPB that would land on the stub's room is refused where staged.
  - TEST HONESTY: psetup's "is all that is dropped" holds that ONLY `$8998` differs; each forged stub is refused by
    its own reason; the two cases over a poked field (a tagged owner, a tagged `rlr`) are LABELLED argument-class
    cases, the lock battery's docstring corrected; the lists' three cases over the staged application carry the
    label and a test holds that battery to it.
  - STRICT MUTATION of what the fix pass changed, 72 Python mutants of the guard, the watches, the vets and the
    steered pass: **69 KILLED / 3 SURVIVED**, each equivalent (the shadow's fast path skipped or laid wider falls to
    the address-by-address compare; an SR word asked of every row is the same rows). The entry-left-armed mutant —
    "not swept, by nature" before: it spun for ever — is a clean kill. THE WAVE'S 328 C MUTANTS RE-SWEPT under the
    new guard and the narrowed pass, no test weakened: the pipes' 156 — **141 KILLED / 12 / 0 ABNORMAL** (+3 refused
    by the compiler; `sem-getpd-unsigned` killed), the lists' 129 — **115 / 14** (`e12-pending-unsigned`, reported
    EQUIVALENT, is KILLED by the narrowed pass: the pending count inverted is negative, and evremove's compare is
    signed), the twin's 43 — 40 / 3, as before. These supersede the totals below.
  - Corrected counts: test_aes_evsync is 10 functions / 13 cases (F reported "10 / 12" over 9 / 12); tak_flag has no
    REGISTERED Line-F row (F's proposed "+ 2 Line-F" are two Tier 1 cases); F's "every in-process case of mine runs
    its child first" was not true of test_aes_evsync until the fix pass.
  MUTATION (strict: a private `.so` or module per mutant, never while editing), as the first fix pass reported it —
  the gate's fix pass re-swept every C list (above: 141 / 12 / 0, 115 / 14, 40 / 3):
  - XA, the lists' C (`evasync.c` + `evasync.h` + the two `aes.h` fields; A's 117 + R2's 12): **129 — 114 KILLED /
    15 SURVIVED / 0 ABNORMAL**. A's seven as before (4 equivalent, 1 equivalent on every reachable machine, 2
    unreachable: get_evb's empty list, NOCANCEL alone); of R2's twelve, 4 killed, 4 survive ALIAS-ONLY (the unpinned
    re-reads), 4 are no-ops by construction.
  - XA, the twin and the protocol's C (`evsync.c`, `evdoor.h`'s host protocol, `switch.h`'s dispatcher entry; F's 35
    + R1's 8): **43 — 40 / 3 / 0**: rlr read once for the store and the owner stored only when free (both
    equivalent), a transient scribble of the count put back inside the call (unobservable at any return).
  - XA, the Python machinery (`aes_event.py`, `tier3.py`, `aes_evasync.py`; F's 43 + 34 of the fixes'): **77 — 75 /
    2 / 0**, three controls green; the two are the shadow's one-compare pass (equivalent: each falls through to the
    address-by-address compare with the same verdict). One mutant NOT SWEPT by nature: a watch left armed at its own
    stop never ends.
  - XP, `pdpipe.c` + its constants (P's 128 reworked + 28 new): **156 — 140 KILLED / 12 SURVIVED / 1 ABNORMAL**, 3
    more refused by the compiler (static asserts). The twelve: 4 equivalent, 4 the accessories' arm (band 5), 3 a
    re-read no store reaches on any machine made, 1 the room wider than a word (`## Not reconstructed`). The
    abnormal one differs only for a count the attribution pass's inverted word reaches — it aborts there, no failed
    assertion. `pdpipe.S` is not swept (byte pin + 5 `.S` rows + `test_transcribed`).
  - Authors' own first sweeps, superseded: F C 35 — 34 / 1 / 0, Python 43 — 42 / 0 / 1; A 117 — 110 / 7 / 0; P 128 —
    114 / 13 / 0.
  COVERAGE (llvm-cov, -O0, the authors' builds BEFORE the fix pass, not re-run after it): `evasync.c` 100 % of lines
  and regions, one branch of 44 one-sided (get_evb's empty list); `pdpipe.c` 91.95 % of lines, 84.09 % of branches
  (the accessory arms and the three refusals, which run in children that abort without a profile). No coverage claim
  is made for `evsync.c`: its three arms are each pinned by killed mutants.
  SUITE TIME, quiet, pytest's own figure under `-n auto`: HEAD **193–197 s** (193.1 and 195.8 in the fix pass's A/B,
  195.8 and 197.2 in R4's); the wave before its fixes 201–203 s; the tree after them **196.8–202.4 s over seven runs,
  mean 200.0** (three with a five-minute cool-down: 202.43 / 199.72 / 199.12). THE 200 s LINE IS NOT HELD WITH
  MARGIN: the wave sits AT it, about +5 s over HEAD, run to run ±3 s. The fixes took the wave's CPU overhead from
  +59..67 CPU-s to about +20 (the shadow's one-compare pass, the fork guard, no image read back by a guard's child,
  the image compared by blocks); what is left is 877 more tests. Nothing was weakened to get closer.
* **Wave 14 band 4 wave 1, PHASE A (2026-10-06 → 10-07) — the input and the waits in C, six
  twins PENDING, nothing flipped; the wave-1 prerequisites; the suite's speed.** Three agents in one tree with
  disjoint owners — F1 (the prerequisites), I (input), S (waits) — four reviewers (R1 slice F1 with a rehearsal of all
  six flips; R2 slice I; R3 slice S; R4 cross-cutting: cost and levers, seams, objects, the table, conventions), a
  fix list, three fix agents in parallel (XF the machinery and the phase-B blockers, XI input, XS waits) and a fourth
  alone afterwards (XK: the kit's two fixes, the speed, the helper hoist). Result: 34 ✅ routines, 3 verified and
  unpriced, dsptch as `.S`; 107 new Tier 3 rows, every one within the bar with no acceptance; NO COMMITTED LINE OF THE
  TABLE MOVED (against HEAD's: 0 lines removed or changed, 270 added). The kit changed twice, in its own commit.
  - F1 — THE EIGHT PREREQUISITES, built once (no routine ported, no row added), each with its RED proof:
    (a) A WATCHED RUN ENTERED AT A DOOR ENTRY: `DoorStops.entered_at(pc)` takes the run's own first stop as the entry
    it is, on both Tier 3 shores; `aes_event.rom_at_dsptch` public. (b) THE SHADOW KEYED ON HOW THE NESTED RUN ENDS —
    returned (answer, image), or blocked / yielded (its image AT DSPTCH, vetted at the dispatcher's hook before it
    refuses); a twin that ends the other way refused by name; `SHADOWED` derived (every rebound entry of the library a
    binding serves). (c) ONE `ENTRY_FRAMES` ROW PER ENTRY — frame, inputs, answer kind (post_button and unsync answer
    nothing a shadow compares) — and the wrapper macros `EVDOOR_REBOUND` / `EVDOOR_REBOUND_VOID`, tak_flag re-spelt
    through them with its objects byte-identical. (d) `EVDOOR_TWIN` (`noipa`): a twin's first instruction stays an
    arrival point. (e) `src/aes/switch.S`, dsptch's twenty bytes, a third kind of the build contract
    (`SWITCH_SOURCES`), and `__ASSEMBLER__` guards in `switch.h` / `evsync.h`. (f) `aes_event.SR_DROPS`, one table
    `{save word: why}` in place of a drop chosen by routine name. (g) A NESTED ARRIVAL REFUSED AT RUN TIME, by name.
    (h) THE FORK GUARD CARRIES THE DISPATCHER'S WORDS ("would block" / "would yield"), and a fork may serve the two
    drawing hooks (`serves=`). And the thing rule 8 needed first: **REBOUND DERIVED FROM THE WRAPPER'S SPELLING** — a
    marker the macro leaves in the host library, "a twin linked and no `jsr` left" on the blobs, the two held equal —
    so a twin that merely exists is PENDING, which is what let six twins land under their final names unflipped. Its
    own rehearsal of unsync's flip found two defects of the "RED passing for the wrong reason" class in its first
    cut (a child read the shadowed set off the WORKER's library, so no shadow was made; `interrupted` took a shadow's
    refusal that names the yield for the yield itself), both fixed with their tests.
  - I (`src/aes/evinput.c`, `evfork.c`): nq, downorup, post_keybd, post_button, post_mouse, inorout, mowner, set_mown,
    ct_chgown, b_click, b_delay; forkq, forker, chkkbd, kchange, bchange, mchange, tchange and drawrat's call — C at
    0.31–0.87, no acceptance, no `.S`. THE FORK HOOK IS NO NEW HOOK: forker's call is exactly `staged_call.h`'s
    `call_alcyon_pointer` (ruling Q3: the host stores the ROM's addresses, bound per case to the candidate's fork
    functions; on target a queue entry's code is the function's own plain-C entry; a row whose run QUEUES a fork
    function drops that code long at Tier 3 by name). A GCC trap found and fixed on the way: with the image base a
    constant null inlined into a core, `-fisolate-erroneous-paths` ended `aes_kchange_fork` after its first store with
    `trap #7`. forker is verified and UNPRICED (its row says why; ruled: wave 2).
  - S (`src/aes/evwait.c`, `evlib.c`): iasync + akbin / adelay / abutton / amouse / amutex, mwait, unsync; ev_block,
    ap_rdwr, ev_keybd / button / mouse / mesag / timer, ev_rets, ev_mchk, ev_dclick — C at 0.38–0.91, no acceptance,
    no `.S`. Every dispatcher-reaching call held to the ROM AT DSPTCH; ev_timer has no row by nature.
  THE REVIEWS. Verdict: **THE C IS FAITHFUL TO THE ROM ON THE HOST IN ALL 37 ROUTINES** — R2 and R3 read every one
  instruction by instruction and found no host-visible divergence — with ONE TARGET-ONLY BUG, and phase B blocked.
  - THE TARGET-ONLY BUG (R2): forker's count was decremented in a register in the m68k object (`move.w count,d0` …
    `subq.w #1,d0 / move.w d0,count`: seven instructions wide on first entry) where the ROM has `subq.w #1,$c906` on
    memory. forkq's `addq.w` runs in the interrupts; one landing in that window was overwritten — the entry in the
    ring, the count one short, every later event served one event late. Tier 1 cannot see it (no interrupt lands
    inside a core) and Tier 3 neither (no row interleaves): the BuggyBoy "hardware-only, invisible to the whole
    differential" class. R2's proof was static (the object's instructions).
  - PHASE B WAS BLOCKED (R1, rehearsing all six flips on a private tree over I's and S's real twins): a flipped
    wrapper in RETURN position (`return evdoor_unsync(…)` in wm_update, `return evdoor_ap_rdwr(…)` in ap_sendmsg)
    compiled to a tail `jmp` into its twin, the twin entered holding its caller's CALLER's return address — 17 of 222
    door rows refused "not a door call" and `bench/tier3.py --out` dead with a traceback. Beside it: ap_rdwr had no
    priced row of its own (the flip would be refused, and nothing said so while the twin was pending); the parked-QPB
    drop a flipped ap_rdwr needs was asked for by NO committed test (no door battery sent a message to a full pipe);
    `interrupted` never compared the four SR save bytes; a run entered at an entry took door call 0's interrupt twice.
  - THE LEAF BATTERIES HAD HOLES (the rule: a rebound twin is held by its leaf battery alone). R2: 6 of 65 mutants of
    the input's two twins survived both batteries (the walk past an unsatisfied wait, the clicks' and the asked
    byte's widths, downorup's mask and state bits, set_mown's button state) and five of bchange's were never spelt.
    R3: of 45 mutants of the four wait twins and their callees 34 survived, 17 of them killable (the owner's, the
    code's, the event bit's, the pid's, the length's widths; ap_rdwr's answer; ev_button's mask and state), and three
    of S's "unreachable" survivors were reachable by the ROM's own iasync called more than once.
  - R2, the rest: the gl_play arm and drawrat's caller, reported as needing band 5, are DERIVABLE now (the desk's own
    appl_tplay of one mouse record); the attribution pass was narrowed FOR NOTHING in 315 of 1,031 cases (a reason
    named wherever the ROM STORED a word, not where it steers); one of I's 220 mutants was a duplicate; bchange's
    registered worst row was not its worst (0.873 against 0.870).
  - R3, the rest: adelay's honest worst is the walk (0.589, never priced); unsync's list arm stood on one
    staged-application case; ap_rdwr's ONE host slot cannot outlive a switch (wave 3's commonest two-process machine
    would abort); the spl7 bracket's presence on target pinned by nothing.
  - R4 (cross-cutting): a derived machine depended on the oracle's LEFTOVER USP — one derivation answered two
    machines by run order, 20 rows hashed differently under `make bench`'s import order than in a worker's; the suite
    +20.9 s near-quiet (+179 CPU-s) with no wave-local lever returning it; three copies of `watched` / `Arrival` /
    `machine_of` / the scenario family, a second interrupt vocabulary, one longword's layout named in three headers.
    CLEAN: the twins' contract, the pre-existing objects (131 + 137 byte-identical), the table, the two reds (the
    docs' alone), `guarded`, the orphans. Its "48 pre-existing rows' bytes moved" was RETRACTED by the fix pass
    (below).
  THE FIX PASS (where it contradicts an author's report, a review or a proposal, the fix report and the final table
  stand).
  - XF, THE MACHINERY. **A TWIN IS CALLED, NEVER JUMPED TO**: the target wrapper's call is followed by
    `EVDOOR_A_CALL_NOT_A_JUMP` (a read of the function's own return address, dropped: no instruction and no weight
    in GCC's inline estimate — the review's suggested empty `asm` weighs one instruction, and measured it stopped
    wm_opcl being inlined into wm_close and moved a committed object); held on both blobs, and both blobs and the
    host library are byte-identical with nothing flipped. SR save words are dropped only where the ROM's run stored
    them, at every comparison, and SYMMETRIC at Tier 3 with no kit change: a row that drops one is held to OUR run's
    ledger having stored it too (`tier3.vet_our_run_stored_its_sr_words` — which pins the spl7 bracket's presence on
    target on adelay's, tchange's, iasync's delay row, psetup's and pstart's). Interrupted, replayed and marked runs
    may be entered at an entry (an interrupt is asked for only at an ARRIVAL). The four tests a flip reddened or
    emptied hold both states (the census's `aes/evdoor.h` row and two Tier 3 lists DERIVED from `REBOUND`). Pending
    twins are held to "no wrapper"; the macro builds its own twin's call (marker ⇔ calls its own twin, by
    construction); a nested arrival IN PROCESS fails its case by name instead of aborting the worker. Every LINKED
    twin, pending too, owes priced leaf rows (`test_every_twin_has_a_leaf_battery_s_rows`). The parked-QPB drop and
    its door case, with XS.
    - **THE SIX-FLIP REHEARSAL** (a private tree, the six wrappers re-spelt through the fixed macro, host library
      and both blobs built by the tree's own rules): the whole suite 3 failed / 21,659 passed, all three `test_status`
      (the two docs reds of phase A, and STATUS quoting pre-flip ratios — a flip's edit by definition). **Of 230
      door-arriving rows 0 are RED** (R1: 17) **and 137 MOVE**, each with a lower numerator and the same original, all
      still `net`, no OVER, no DRIFTED; `bench/tier3.py --out` exits 0; each flip alone 5,539 passed of a reduced
      set. **THE DESIGN PREDICTED 48 ROWS MOVING ACROSS FLIPS 1 AND 2. FLIP 1 MOVED 88 AND FLIP 2 WILL MOVE 137: THE
      PREDICTION WAS LOW BY ABOUT A FACTOR OF THREE.** No verdict rests on the count (ruling Q6 accepts a moved row;
      a row over the bar is what it does not accept, and none is) — the count itself was wrong.
      The shadow's cost with seven entries rebound: +2.5 ms an arrival × 2,177 newly shadowed ≈ +5.4 CPU-s a suite
      (R1); no retire rule is needed for flip 2.
    - R4's "48 pre-existing rows moved" is NOT A MOVE: its HEAD tree (a `git archive`, no `build/`) captured a FRESH
      boot snapshot, 451 bytes of 1,048,576 from the working tree's. Over ONE snapshot 0 of 1,511 rows differ.
  - XI, THE INPUT. THE BUG FIXED AND THE CLASS AUDITED BY MEASUREMENT: the denominator is the ROM's COMPLETE
    reference list of the eleven interrupt-shared words (61 references over `$fd8000..$fee900`), nineteen sites in
    reconstructed routines each read as the ROM's instruction, ours on target, and whether an interrupt writes it.
    Five counts and two re-reads were not the ROM's (forker's count — the bug; forkq's tail — WORSE than the ROM's own
    race: head and tail parted for good; b_delay's `sub.w`; b_click's `addq.w #3`; mchange's count and b_delay's
    buttons each read once where the ROM reads twice). `m68k_idioms.h`'s three helpers are one instruction on memory
    on target and the plain C off it.
    - THE NEW SURFACE, `test/test_aes_evfork_interrupted.py` (19 tests, 4 s serial): a routine run once per
      instruction boundary of its own body — on the ROM and on BOTH blobs — the 68000 itself taking the ROM's own
      interrupt glue (button, motion, tick) there: the instruction at the boundary replaced for one step by a `jsr`
      to a 30-byte trampoline, the watch stepping by the successors the routine's own disassembly names (a successor
      the listing misses refused by name). ITS RULE, derived from the ROM alone: **the set of states our routine can
      be left in == the set the ROM's is left in at the boundaries of its own**, and a state the ROM is left in at
      ONE boundary alone is left by ours along one straight line of instructions. RED on private blobs built from
      the tree before the fix, 6 of 6 instruction shapes; two shapes GCC already made memory-direct are not
      distinguishable on this compiler.
    - The twins' six survivors and two of bchange's five each killed by a case built for it (the other three
      unpinned by name); the three forker transients killed by holding the C's image at the hook's call to the
      ROM's memory at the fork function's arrival. The playback is the ROM's own (`aes_evinput.playing`: the desk's appl_tplay; the staged `$9800` case
      deleted; a priced row). The attribution table now names the reasons that STEER, measured by leaving each out
      in turn (`aes_evinput.STEERS`; forker and bchange's lists tried without the reason first): the on-demand
      sweep over both batteries 1,163 passed, 0 refused. All 58 `trap #7` of each blob are source refusals (the
      per-function counts identical with GCC's erroneous-path isolation off; a positive control traps).
  - XS, THE WAITS. ap_rdwr PRICED (three rows; the read of a FULL pipe is each pipe routine's new worst and is
    registered first for iasync, ev_block, ap_rdwr and ev_mesag). R3's 17 killable survivors and S's own four each
    killed by a named case — and ONE ROM FINDING CORRECTED BY IT: ap_rdwr does not "always answer 0". adelay's walk
    and its insert between two, mwait's mask as a word, amouse's copy-then-store order: pinned on machines of the
    ROM's own iasync, off the unpinned list. unsync's list arm has a second machine with no staged application.
    - **THE HOST SLOT PER PROCESS**: ap_rdwr's QPB is a frame local that stays live while its process is PARKED,
      with its address in an EVB another process reads. `HOST_SLOT_AES_AP_RDWR_QPB` is nine frames of eight bytes
      (three static PDs and the six accessories the loader stops at), the RUNNING process's id choosing one
      (`host_slot_claim_for`) — an address the image alone decides, because a parked frame is laid in one host run
      and read in another. On target nothing changes (both m68k objects of `evlib.c` byte-identical). Pinned with two
      processes' frames live at once: with one slot the writer's QPB lands on the reader's.
    - The parked QPB's address dropped BY NAME AND VETTED wherever a blocked ap_rdwr is compared at dsptch — the leaf
      batteries, the shadow, a door user's blocked call (`aes_event.parked_qpb_drop`) — and the door case no battery
      had: a message to a FULL pipe parks the sender where the ROM does (`test_aes_apmsg.py`).
  - XK, THE KIT — ITS OWN COMMIT (ruling Q7), with the kit's suite and the six other projects':
    - USP SEEDED AT A RUN'S ENTRY (`ENTRY_USP` = 0, beside `ENTRY_SR`): a reset leaves the inactive stack pointer
      alone and no caller hands a run its USP, so a run inherited the last run's, and a derivation that parks or
      dispatches a process SAVED it. 0 is what a process's first run always had.
    - THE WATCH LOOP'S SPIN: `rom_bench.watched` refuses, by name and before arming it, a door that holds the PC the
      run is stopped at (`rom_bench.door_holds`) — wave 0's deferred kit fix.
    - WHAT MOVED: **28 of 1,793 row hashes** (9 committed at HEAD — takeoff ×2 and its caller's call, apret behind
      another on both lists, acancel ×2, evremove's double-click wait and its caller's call, tak_flag refused — and 19
      of this wave's): the saved USP of a parked or dispatched process is now the snapshot's own. **0 Tier 3
      lines.** The row-hash set is now the same under `make bench`'s import order and pytest's collection order
      (R4 found 20 apart). Kit **1,200 passed** (1,192 + 8); the six other suites green at their carried counts.
  - XK, THE SPEED (the user's direction, 2026-10-06: optimise the tests freely, weaken nothing — "content-neutral"
    = the same case ids, row hashes over one pinned snapshot, table lines, and kills on a sample). Quiet starts
    (1-minute load under 4), pytest's own wall under `-n auto` (10 workers = every core, 8 P + 2 E):

    | run | wall | CPU-s | collection per worker (CPU / wall) |
    |---|---|---|---|
    | step 1's tree (before) | **223.3 s** | 1,987 | 37.7 / 40.5 s |
    | final, zygote off, cache off (levers B, D, the lazy final image, `as_pokes`; +134 tests) | 221.9 s | 1,971 | 35.4 / 37.7 |
    | + A, the zygote | 219.1 s | 1,943 | 35.4 / 37.8 |
    | + C, the cache, COLD — a bare `pytest`, nothing made first | **212.6 s** | 1,891 | 36.0 / 38.8 |
    | pytest inside a cold `make test`, after `make derived` | **183.6 s** | — | — |
    | + C WARM (the same tree again) | **166.7 s** | 1,466 | 9.4 / 10.5 |

    `make test` from `rm build/*.so` and an empty cache: 241 s (build, `make derived` 17 s, the table 35 s, pytest
    183.6 s) against ≈ 381 s before. `make bench` **143 s → 35–40 s**; `make guarded`'s pytest 226.2 → 169.8 s.
    - THE LEVERS TAKEN. A — THE ZYGOTE (`test/zygote.py`): each test process forks a zygote as its session starts,
      and a guard's fork is made BY IT from the call's content (a fork costs what its parent holds resident: 1.2 ms
      at 85 MB, 23 ms at 1 GB, and a worker is a gigabyte). B — a scenario step's buffer handed on, not copied three
      times. C — ROM-ONLY DERIVATIONS KEPT ON DISK BY CONTENT (`test/derived.py`, 12 derivers; registry import 25.8
      → 4.4 CPU-s, collection 40.5 → 10.5 s a worker). D — no extra ROM run for a routine no reason steers. G —
      `bench/tier3.py --jobs` (the measuring pass over forks, judged and written by the parent: the table the same
      line for line), `make derived`, `make gates`.
    - `make gates` IS NOT ONE WALL TIME FOR THREE: the two suites are the same CPU-bound work twice on ten cores
      (side by side each takes 360 s where alone 170–184). It buys one command, one build, one set of derivations:
      417 s against 423 s for the four in turn; a full gate was ≈ 592 s before the levers.
    - WHAT THE REMAINING SECONDS ARE MADE OF: the KIT's handling of the 16 MB image — per differential `emu.run` 2.9
      ms, `make_image` 1.4, `candidate_image` 1.4, the whole-image compare 3.1, and the attribution pass again: 78 %
      of a battery's serial time, a third of the suite's CPU in `sys` (40.9 M page reclaims a run) — and 170 CPU-s
      of fresh interpreters (1,994 door children a run). Both deferred (`## Not reconstructed`).
    - LEVERS REFUSED, measured. E (repeats): a guard-verdict memo gains nothing after A (a repeated guard is 3.5 ms;
      a content key of the image costs 0.4–0.9 ms on EVERY guard), S's "direct / through Line-F" forks are NOT the
      same content (another stub and frame), and one differential shared by several test functions would remove the
      repeated executions that expose ORDER DEPENDENCE — which is how the USP was found. F (band 3 wave 3's parked
      lever, "reuse the real-disk run's deliveries for the replay"): **REFUTED as content-neutral** — built, and 5
      of 80 sessions were refused by name (a session that rings the bell: the BIOS's sound state under the next
      key's click), and a delivery records the bytes an interrupt writes OVER, not those it reads, so "they fit"
      does not prove "they are the replay's". Reverted; the replay's OWN deliveries are kept by content instead.
      The lighter second differential: not taken (it drops (EV)'s window vets).
    - THE ZYGOTE'S FIRST SEGV STRESS WAS RED (a private library storing 1 GB past its image: 5 guards of 20 passed,
      9 workers crashed) — a fork of the zygote has another address space than the worker's, so its image is GUARDED
      ON EVERY RUN, in `make test` too. After: abort / spin / segv 20 of 20 fail by name, plain and under the
      guarded-image plugin; a worker SIGKILLed mid-run leaves no zygote 0.1 s later.
    - THE CACHE CANNOT SERVE A STALE ANSWER: its key is content — the tree (every file a derivation could read or be
      made by, the candidate `.so` as loaded), the base image in force, the deriver read as a value, its arguments by
      value — 62 tests, one changed thing each. Cold = warm = off, measured: 1,793 row hashes, 150 scenario hashes,
      21,799 case ids and outcomes, the table.
  - XK, THE HOIST. ONE family in `aes_event.py` — `Layer` (a battery's routines: entries, frames, what a machine
    leaves out, which argument is restaged out of its caller's stack) and `Scenarios` (declared arrivals, each run
    held to them) — bound by `aes_evasync`, `aes_evlib`, `aes_evinput`; the input's block-wise `machine_of` IS
    `aes_event.as_pokes`; ONE interrupt vocabulary (`Interrupt`, `PRESSING`, `CLICKING`, `moving_to` … under two
    runners); ONE rule for "the ROM stored the word" (`not_compared_where_the_rom_stored`, the stricter of XF's
    two); in C one name for the high-word shift and one family for a button wait's parameter (eight names retired).
    Row hashes 1,793 / 1,793 and scenario hashes 150 / 150 equal before and after; both blobs, the host `.so` and
    all 136 shipped objects byte-identical. NOT hoisted, said: the duplicates inside test files.
  MUTATION (strict: a private `.so`, blob or mirror per mutant, never while editing), each sweep as finally reported:
  - XF, the machinery (51 Python + 8 C): **59 — 59 KILLED / 0 SURVIVED / 0 ABNORMAL**.
  - XI, the input's C and headers (I's 219 distinct + R2's 11 + 9): **239 — 225 / 14 / 0**. The 14: six equivalent,
    two orders no callee sees, six unpinned by name (`## Not reconstructed`). Target text: 6 of 6 shapes RED on
    private blobs.
  - XS, the waits' C and headers (S's 151 + R3's 45 + 6): **202 — 176 / 24 / 0**, +2 refused by the compiler; its
    Python helper 6 / 6.
  - XK, the machinery it changed (zygote, guard, cache, layers, interrupts, the bench's pass, the kit): **120 — 119
    / 1 / 0**, the one equivalent; and a SAMPLE of step 1's C mutants on the final tree (every 7th of XS's and XI's):
    64 — 63 the recorded verdict, 0 differ, 1 no longer applicable.
  - F1's own sweep stands for what the fix pass did not re-sweep: Python **75 — 74 / 0 / 1**, C **7 — 6 / 0 / 1**,
    each ABNORMAL a refusal by name at import (a collection error by nature, also held by a unit test).
  - Authors' first sweeps, superseded: I 220 — 205 / 15 / 0 (one mutant a duplicate); S 151 — 138 / 11 / 0 (+2).
  COVERAGE (llvm-cov, -O0, the authors' builds BEFORE the fix pass, not re-run): `evinput.c` and `evfork.c` 100 % of
  regions, lines and branches; `evwait.c` 93.7 % of lines / 95.8 % of branches, `evlib.c` 95.9 % / 100 % — every
  uncovered line one that runs only in a fork that ends at the dispatcher's hook (a halted fork writes no profile),
  each pinned by killed mutants.
  THE ROM'S FINDINGS, the KNOWN ROM RACES among them, are in `## Not reconstructed` (band 4 wave 1), each once.
  THE PRE-COMMIT GATE AND ITS FIX PASS (2026-10-07). Four finders over the whole diff: NO DEFECT IN THE SHIPPED C, the
  hoist lost nothing, every pre-existing m68k object byte-identical. The defects were in the NEW SPEED MACHINERY, the
  kit hunks' pins, and cleanup — each fixed with its RED, nothing flipped, all 272 m68k objects (136 sources under
  the bench's flags and the shipped ones) byte-identical before and after, the table byte-identical (2,997 lines),
  1,793 row hashes and 150 scenario hashes equal before and after and with the cache on and off:
  - **THE CACHE COULD SERVE A STALE ANSWER, LIVE.** The tree's key was made at the first kept question — 0.6 s into a
    worker's life, 43 modules imported: an edit landing in between was keyed as the NEW tree by a process running
    the OLD module, and what it kept was served to every later process of the edited tree (reproduced on a private
    copy: the pre-edit helper's `$30e0` served where the tree derives `$30e1`). NOW THE KEY NAMES THE TREE THE PROCESS
    IS MADE OF: when the process BEGAN is asked of the kernel and a file changed since — by its modification date or
    its inode's — puts the cache out of use for that process for good; the files are stamped as `derived` is imported
    (first, in `conftest.py` and the bench); every WRITE asks again exactly (every file, the listing, every module of
    the repository imported — one the key does not read puts its importer out: four were in no key), every READ at a
    read's price. Proved both ways on the private copy: with the rule, the process keeps 0 files; with it taken out,
    258 poisoned files are written — and the next process is then stopped by the sampler below.
  - **A KEPT ANSWER IS HELD TO ITS DERIVATION ON EVERY RUN**: each process makes a few of the answers it is served
    AGAIN and holds them equal (29–30 a run over ten workers, said in the run's last lines) — what every process did
    by itself before there was a cache, which is how the USP's run-order dependence was found. Every kept file
    carries the digest of what it holds (one flipped bit of a small file loaded as ANOTHER answer 57 times in 300);
    pokes that overlap are read in the order they are laid; the interpreter's version and `-O` are in the key.
  - A TEST THAT PATCHES MAKES ITS OWN FORKS: the zygote froze every module as the session started, so a patch on the
    fork's side never ran in its fork (a patched arming that raises: exit 0 where 8 is right). `conftest.py`
    sidelines the zygote, as it switches the cache off, for every test that takes `monkeypatch`.
  - A DEAD FORK HUNG `make bench` AND `make derived` FOR EVER (a `multiprocessing.Pool` loses a dead worker's share
    and waits for it; both are every gate's prerequisites). `test/fork_pool.py`: a fork that dies ends the pass by
    name, a pass no share comes back from is ended with its forks killed (100 × the longest share's 3.2 s; 40 × the
    longest import's 22 s), and the pass is held to the rows it was asked for.
  - THE KIT (its own commit): the USP's and the entry SR's pins READ THROUGH BOTH DOORS — the USP's read through
    `osh_run` alone, so a force that lived in `osh_run` only was green (five variants of the shim: none, each door
    alone for each register — every one reds the read through the door it leaves out); `rom_bench.watched` reads
    the PC AFTER the watch answers (a watch that services its stop and keeps its door was refused) and reads a door
    ONCE (a one-shot iterable was emptied by the check and armed nothing); and two measured speed levers below.
    **What the USP seed moved, in full: 28 of 1,793 row hashes AND 8 of the 150 scenario hashes** (7 of the waits', 1
    of the input's), **0 Tier 3 lines.**
  - THE IN-MEMORY IDIOMS HAVE THEIR INSTRUCTION PIN: each routine stepped with no interrupt on the ROM and on both
    blobs, every change of a shared word read off the instruction that made it and held to the ROM's kind — counted
    in memory, or stored (`test_aes_evfork_interrupted.py`; the header had named a surface that did not exist).
  - A host slot per process is released BY THE ADDRESS ITS CLAIM ANSWERED (not by the process running when the wait
    comes back) and refuses a process id that is none of the AES's BY NAME; `interrupted`'s stored-word rule is
    asked of the machine WITH ITS DELIVERIES LAID (an interrupt's own store of an SR save word is not the run's);
    psetup's SR word is asked of EACH row's run; ONE QPB layout, its words signed as the ROM reads them.
  - THE SPEED, content-neutral (the same ids and outcomes, row and scenario hashes, table). Quiet starts, pytest's
    own wall, ten workers; CPU-s is user + sys of the whole tree:

    | run | before the fix pass | after | CPU-s before → after |
    |---|---|---|---|
    | bare `pytest`, cold (nothing made first) | 212.2 s | **207.4 s** | 1,881 → 1,835 |
    | bare `pytest`, warm | 166.2 s | **151.3 s** | 1,465 → 1,324 |
    | pytest inside a cold `make test` | 183.6 s | **170.8 s** | — |
    | `make test` whole, from `rm build/*.so` and an empty cache | 241 s | **226 s** | 1,825 → 1,642 |
    | `make guarded` right after | 176 s | **159 s** | — → 1,363 |
    | `make bench` (the table removed, the cache warm) | 23.3 s | **21.2 s** | 137 → 125 |
    | `make gates`, cold / warm | 417 / 364 s | **388 / 309 s** | 3,495 / 3,186 → 3,190 / 2,777 |

    The levers: the kit's second differential no longer walks the blob's 168 KB byte by byte in Python on every
    compare only to discard each address (25 of a compare's 28 ms; `test_tier3`'s per-row test 113.8 → 63.5 s
    summed); the kit's compare narrows a differing 64 KB chunk to its 256-byte lines before walking; the VDI's
    `dispatched_pokes` reads a workstation's fields off the pokes instead of building two 16 MB images (11,196
    calls); the ROM runs behind `aes_event.derived` are kept by content (a process's warm import 5.1 → 3.2 CPU-s).
    NOT BUILT, measured: the door's 737 fresh-interpreter children forked by the zygote (bound ≈ 60–90 CPU-s, 6–9 s
    of wall — `**Next**`); and Tier 3's per-row test answered from the bench's table where the table is this
    tree's (now 63.5 s summed, 6 s of wall): it would trade the suite's own second measurement of every row — made
    in another process and another import order than the bench's, which is the standing detector of an
    order-dependent oracle — for a sample of one row in sixteen. Refused as a weakening.
  - MUTATION of what this pass changed (strict, private mirrors of the tree): **77 — 74 KILLED / 3 SURVIVED / 0
    ABNORMAL** at first; each survivor a hole in a TEST, now closed (3 of 3 killed — one of them the removal of a
    true premise's assertion, unkillable by nature, whose rule became a helper with its own killed mutant). TARGET
    TEXT, both blobs rebuilt: each in-memory idiom put back to plain C is KILLED, and the instruction pin reds
    forker, forkq and b_click where the interrupted sweep reds b_click alone. And TEN OF STEP 1'S C MUTANTS with
    the cache and the zygote ON and then OFF: the same verdict and the same count of failed tests ten times out of
    ten, each the verdict its author recorded (8 killed, 2 survive). THE REBUILD TRAP BIT THE FIRST ON/OFF SWEEP
    (a mutant written in the second its mirror's last build ended in was "up to date" to `make`: three killed
    mutants read SURVIVED) — the runner now removes the library before it rebuilds it.
* **Wave 15 band 4 wave 1, PHASE B (2026-10-07) — FLIP 2: post_button, ct_chgown, unsync, ev_block, ap_rdwr and
  ev_button rebound.** One agent, its own commit (ruling Q6), on the tree phase A left (`d86776f`). No routine
  ported, no test written or edited: the flip, its proof, its price, its docs.
  - THE ONE HAND EDIT, `include/aes/evdoor.h`: the six wrappers re-spelt through `EVDOOR_REBOUND` (post_button
    through `EVDOOR_REBOUND_VOID`), the three includes that declare the twins (`aes/evinput.h`, `aes/evwait.h`,
    `aes/evlib.h`) — and, the flip's own orphan, `EVDOOR_CALL_LONG` removed (unsync's inline `jsr` was its last
    user). NOTHING ELSE was forced: `REBOUND`, the shadowed set, the census's `aes/evdoor.h` row, Tier 3's lists and
    the door tests followed by derivation, as phase A built them to.
  - THE SUITE, the shadow on all seven rebound entries: **1 failed, 21,865 passed, 2 skipped** — the one red
    `test_status`'s ratio pin (21 STATUS rows quoting pre-flip ratios: the rehearsal's 21), green once re-quoted. NO
    SHADOW REFUSAL: no twin differs from the ROM's routine at any of its 3,541 shadowed arrivals a run.
  - THE TABLE (`make bench` on `d86776f` saved before, the flipped tree's after): 1,851 rows both, 2,997 lines both,
    0 added, 0 removed, **137 MOVED** — THE REHEARSAL'S 137 — in 25 routines: fs_input 27, fm_do 15, wm_set 10,
    draw_change 9, fm_button 8, fm_alert 7, eralert 7, fm_error 7, wm_update 6, gr_dragbox 5, gr_slidebox 5, mn_bar
    5, fm_own 4, ap_sendmsg 3, gr_rubbox 3, fm_show 3, w_setactive 2, w_update 2, wm_close 2, gr_rubwind 2, w_redraw
    1, wm_opcl 1, wm_open 1, mn_clsda 1, fm_dial 1. EVERY ONE: the original's column unchanged, our cycles LOWER,
    the verdict still `net`. No other row's line or sub-line differs; the verdict tally is the same nine numbers.
    - BY ENTRY (the entries a moved row's priced run arrives at, a sliced row's inside its slice; a row counts for
      each): unsync 92, ct_chgown 78, ap_rdwr 19, ev_button 7, post_button 5, ev_block 0 (no priced door row reaches
      it: wind_update's mutex wait blocks). 10 moved rows arrive at none of the six — the wrapper's change of SHAPE,
      as 8 of flip 1's: five fm_button rows that reach no wait (−32 / −36 cycles: `aes_fm_button` saves seven
      registers where it saved ten, its ev_button no longer an inline `jsr` with D2/A2 given up — read off the two
      objects), wm_update's two takes (−8), fm_own taken again (−22), two fs_input slices (−8).
    - HOW FAR: moved rows 0.27 / 0.68 / 0.96 (min / median / max) → 0.31 / 0.67 / 0.95; every row with a window or
      a rebound call (173) 0.27 / 0.68 / 1.04 → 0.31 / 0.67 / 1.04 (1.04 is gr_stilldn's seven, ev_multi's, not
      moved). 78 rows moved at two decimals, 61 down and 17 up; 11 by more than 0.05 — UP wm_update's release 0.36 →
      0.43, "3: the screen taken" 0.36 → 0.43, "2: the screen given back" 0.33 → 0.43, fm_own taken ×2 0.38 → 0.45
      and given back 0.34 → 0.46, w_setactive 0.37 → 0.44 and 0.35 → 0.43; DOWN mn_bar hidden 0.65 → 0.50, mn_clsda's
      two messages 0.64 → 0.58, fs_input's elevator let go 0.78 → 0.72. **NO MOVED ROW IS WITHIN 0.03 OF THE BAR OR
      OVER IT, net or with its thunks** (the highest: fs_input's close box's arm alone 0.96 → 0.95, 1.00 with thunks
      both times; next 0.88). A row that rose is not dearer C: it was net of a window and is now twin against
      routine. The six twins cost 0.38–0.71 of the ROM's routines a call (the section intro has each).
    - AGAINST THE PREDICTION (design §3: all 152 (EV) rows re-priced with the event layer on both sides at r = our
      layer / the ROM's between 0.45 and 1.10 → min 0.27–0.46, median 0.71–0.81, max 1.00–1.10, no row over the bar,
      34–53 rows moving by more than 0.05 across the three flips; "48 rows" for flips 1 and 2): the BAND held — r
      measured 0.38–0.71, nothing over the bar, the median below the predicted one — and the COUNT did not: 88 + 137
      = 225 rows moved where 48 were predicted (20 + 78 = 98 of them at two decimals), the factor the rehearsal
      reported; why the design's count was low was not looked into here. AGAINST THE REHEARSAL: the same 137 rows,
      each by the same number of cycles (the rehearsal's per-row lines against this table), the same single red
      class, no RED row; one thing differs — the suite's cost (below).
    - Every sliced session's partition test is green on the flipped table (`test_tier3.py`'s four: no stretch
      dearer than its routine's worst row, the stretches and slices partition the run, the uncovered stretches are
      what the slices leave, a dear stretch is refused).
  - WHAT THE FLIP NEWLY HOLDS — BLOCKED DOOR CASES AT DSPTCH. Of the suite's 97 ROM runs that block inside a door
    call, 12 now end in an entry whose twin runs on to the dispatcher's hook and are compared with the ROM's memory
    AT DSPTCH (measured: the memory each is compared with differs from the one at the call's entry by 43–98 bytes —
    the wait's EVB, its lists, the PD — and each case is green): five band 3 cases (wind_update(1) and fm_own(1)
    after an unbalanced release → ev_block; the lock released to a waiter → unsync, a yield; fm_do's radio button
    held down → ev_button; a message to a full pipe → ap_rdwr), two composed cases of the door's own tests over
    wind_update, five runs entered at ev_button. 83 block in ev_multi and stay at the entry until FLIP 3. Counted
    with the derivation cache off and on: the same 97.
  - TWELVE REAL MUTANTS, two a twin, each through the DOOR batteries (fourteen files, 2,101 tests, the shadow on)
    and through its twin's LEAF battery alone (strict rule, a private library per mutant, both controls green):
    **LEAF 12 / 12 KILLED; DOOR 9 / 12** — the three the door lets through: post_button's clicks not capped at the
    clicks asked (mn_bar posts one click), ap_rdwr answering nothing (it answers 0 in every machine a door user
    makes), ev_button's answers not written (fm_button reads none of them, they lie in its frame, and — what the
    shadow's pass implies — every other byte ev_rets writes already held its value in its machines). At least five of the nine door kills carry the shadow's own words,
    naming the twin at its own call (the saved tails are sixty lines: the other four were not read whole). THE
    RULE HOLDS FOR ALL SIX: a rebound twin is held by its leaf battery; the door cases hold the composition. (The
    mutation plugin switches the bench's second differential off, so the five tests OF that differential are
    deselected in a host sweep — they fail on the control.)
  - THE COST, quiet, one sample a side, pytest's own wall under `-n auto`: bare cold 208.7 → 210.3 s; inside a cold
    `make test` 170.2 → 173.9 s; warm 151.5 → 155.3 s; CPU-s 1,841 → 1,857 / 1,541 → 1,568 / 1,324 → 1,362. Nested
    ROM runs a suite run 4,927 → 4,873, of them shadows 1,063 → 3,541 (+2,478: a call the door served is a shadow
    now, one nested run either way, and the twin runs beside it). THE REHEARSAL ESTIMATED +5.4 CPU-s; measured +16
    to +38 — a difference, not explained: one sample a side, the spread unmeasured.
  - OBJECTS (164 m68k objects, blobs and ROM-build products hashed before and after, each from a clean build): 8
    changed — the two blobs (`bench.elf` / `bench.bin`, both configurations) and the four objects that hold a
    flipped wrapper's call, `apmsg`, `fmdo`, `mnlib`, `wmupdate`; 156 identical, `evdoor`'s among them (its markers
    are the host library's) and everything `make -C atari -B all` writes.
  - GATES, from `rm build/*.so` and an empty derivation cache: `make gates` rc 0 (393 s) — test 21,866 passed / 2
    skipped, guarded 21,866 passed / 2 skipped (28,979 candidate runs guarded), the table rebuilt byte-identical to
    the flip's saved one, the ROM build rc 0 — and again, the same way, on the final tree with these docs in: the
    same counts. The ten cases the flip changes the comparison of, and `test_status`, each ALONE in its own process:
    green. Strays: none. Orphans (README's check): none. No test file changed. NOT RUN by this pass:
    `my-code-review` (the orchestrator's gate) and the four gates in turn.
* **Wave 16 band 4 wave 2, PHASE A (2026-10-07) — the dispatcher on target, ev_multi's twin PENDING, nothing flipped;
  the wave-2 prerequisites; the two-count pricing rule; one pricing gap found and left to the user; the suite's
  speed.** Three agents in one tree with disjoint owners — F2 (the prerequisites), M (ev_multi), D (the dispatcher) —
  four reviewers (R1 slice F2 with a rehearsal of FLIP 3; R2 slice M; R3 slice D; R4 cross-cutting: cost and levers,
  seams, objects, the table, conventions), a fix list carrying EIGHT ORCHESTRATOR RULINGS (U1–U8, below), three fix
  agents in parallel (YF the machinery and flip 3's blockers, YM ev_multi's battery, YD the dispatcher) and a fourth
  alone afterwards (YZ). **AGENT YD WAS STOPPED BY MISTAKE BEFORE IT REPORTED** (around 18:30, near its end: its edits
  were whole in the shared tree, it had written no report and no docs proposal, and the gate it had running died with
  it — all ten xdist workers "node down" at once at 90 %: a log that ends in a kill is NOT a result). YZ took its
  files over, decided DONE / PARTIAL / NOT DONE for each of its six items BY RE-RUNNING each RED → green proof, never
  by a log, completed what was missing, wrote its report, and then did step 2 (the kit's two levers, the leftovers).
  Where an author's report, a review or a proposal disagrees with a fix report, THE FIX REPORT AND THE FINAL TABLE ARE
  WHAT THIS ENTRY QUOTES. Result: 14 more ✅ rows and five ⚠️; 52 new Tier 3 rows (ev_multi 26, the dispatcher 26),
  every one within the bar with no acceptance; against HEAD's table 0 rows removed, 4 moved IN THEIR VERDICT TAG
  ALONE, NO RATIO OF A COMMITTED ROW MOVED; ev_multi's twin PENDING — `include/aes/evdoor.h` and `src/aes/evdoor.c`
  untouched. The kit changed, in its own commit.
  - F2 — THE WAVE-2 PREREQUISITES, built once (no routine ported, no row added), each with its RED proof. (a) WHO
    PARKS A QPB IS READ OFF THE MACHINE, no routine named: every EVB of the running process queued on a pipe's end
    whose parameter is a stack address (`aes_event.parked_qpbs`), vetted pairwise (`parked_where_blocked`: the same
    EVBs, each shore's parameter a place in its own stack band, the same eight bytes) — at a leaf's dsptch, at a
    shadow's, where a door user blocks inside a rebound entry (`Entry.parks`) — and AT A RETURN the address a
    cancelled or answered wait leaves in its FREED EVB (`qpb_addresses_kept`, by the ROM run's ledger). ev_multi's QPB
    is a slot per process of its own (`HOST_SLOT_AES_EV_MULTI_QPB`). RED: the shadow of a blocked ev_multi(MU_MESAG +
    MU_TIMER) was refused at HEAD on `$b238/$b239` — the pipe wait is not the newest EVB and its QPB lies 16 bytes
    BELOW the first argument. (b) TIER 3'S SYMMETRIC-DROP RULE HAS ONE HOME (`tier3.vet_what_our_run_stored`;
    `measure` holds that it RAN): the real hole was the `.S` / (T←) path, which read no drop at all — a transcription
    row that names a drop is refused by name. (c) ONE SETTLING of a leaf row's words that differ by nature
    (`aes_event.settled` / `register_row`: the mask word, every SR save word — the dispatcher's `$8994` in the table
    —, `savptr` under a poll; SINCE BAND 5 WAVE 1 the dispatcher's is staged and COMPARED at Tier 3, whole but for the X
    flag on the two rows that declare it). (d) FLIP 3'S BINDINGS ARE THE DOOR'S, keyed on ev_multi REBOUND (`polls_in_c`): the
    VDI's polled functions, the handed routines (the four fork functions, justretf, default_user_cur) in process and
    in a child, the trap frame's PC and SR. (e) SPEED: the zygote makes the forks that serve a NAMED hook
    (`aes_event.named_hook`) and the door users' children (`door_child`: 176 fresh interpreters a run are left of
    737); a derivation IN FLIGHT is claimed (`derived.py`), so ten cold processes make it once. (f) PARTLY: steering
    DERIVED (`steering_reasons` read off the layers' modules), `fork_code_drops` naming no routine; NOT BUILT, and
    still owed: the single interrupt runner (`taken(layer=)`) and `Layer.restaged`'s generic form. (g) FLIP 3
    REHEARSED on a private tree. Beyond the list, required by (g) and by D: THE FORK QUEUE'S CODES RELOCATED AT TIER 3
    (`tier3.RomBench`, `fork_relocation`), and the dispatcher's stack put back for a row that drops it. Measured like
    for like (the same 1,765 cases of the nine batteries the two fork levers touch, warm, `-n 4`, alternated; R4
    re-measured): −38 % CPU (259.8 / 257.7 → 161.2 / 161.3 CPU-s); the in-flight claim, ten cold importers side by
    side: 308–318 → 183–193 CPU-s (−40 %; F2's first figures, 345 → 115–160, did not reproduce under load) and 360 →
    275 CPU-s in the suite's own cold collection.
  - M — `ev_multi` (`$fe6998`, 710 B), the door's last entry, as a PENDING twin (`src/aes/evmulti.c`,
    `include/aes/evmulti.h`; `test/aes_evmulti.py`, `test/test_aes_evmulti.py`). It calls wave 0/1's CORES only
    (chkkbd, forker, dq, downorup, ev_mchk, ev_mesag, iasync, ldiv, mwait, acancel, ev_rets, apret). A case is AN
    APPLICATION'S OWN evnt_multi — a frame over a machine the ROM made (`aes_evlib`'s running processes;
    `after(machine, interrupts…)`: the ROM's own interrupts taken while the process was busy, which ev_multi's own
    chkkbd and forker then post, in C under the twin). As the authors left it: 266 tests, 15 rows (worst 0.81), and
    NOTHING after a switch run in C. As the fix pass left it: its row.
  - D — THE DISPATCHER: the switch as `.S`, disp as the ROM's stream, the scheduler's C, the host's model of the
    switch, forker priced. 18 routines, five batteries (`test_aes_irq.py` 80, `test_aes_switch.py` 58,
    `test_aes_evdisp_model.py` 52, `test_aes_evdisp.py` 43, `test_aes_switch_forker.py` 11: 244 tests as the fix pass
    left them), 26 new Tier 3 rows.
    - WHAT SHIPS AS BYTE-PINNED `.S`, AND WHY: dsptch, spl7_save, spl_restore, cli, sti, gotopgm, savestate, switchto
      (`$fe387c..$fe395b`: one relocated word, dsptch's `jmp` operand, which names OUR disp); the button, motion and
      tick glue with drawrat and justretf (`$fed3be..$fed477`: six words that name code — three `jsr`s to Alcyon
      thunks of our C, two fork functions pushed by value, forkq twice); and disp. A context switch has no C spelling,
      and disp — Alcyon C in the ROM — must be assembly too: savestate reads disp's caller's frame through disp's own
      A6 and returns to it on another stack with A0 and A5 changed, a contract no compiled function keeps. This is
      INSIDE the user's policy "C first, `.S` where C cannot meet the bar"; disp_act, mwait_act and idle are C.
    - THE `stream` TRANSCRIPTION KIND: `transcription.stream(lo, hi, symbol, {ROM address: CallWord(routine,
      symbol)})` + `assert_stream` — "the ROM's instruction stream with its Line-F call words as `jsr`s", held
      INSTRUCTION BY INSTRUCTION: each call word named and held to the ROM's own table entry, each short branch's
      displacement followed, every other instruction equal, a Line-F RETURN refused, the symbol's size exactly the
      stream's. disp's SIX SUBSTITUTIONS: `$fe4db0` `$f7c8` → `aes_rom_savestate`; `$fe4dc6` `$f7c0` →
      `disp_to_aes_disp_act`; `$fe4dcc` `$f7cc` → `disp_to_aes_mwait_act`; `$fe4dda` `$f7d0` → `disp_to_aes_forker`;
      `$fe4ddc` `$f7d4` → `disp_to_aes_idle`; `$fe4dfe` `$f7d8` → `aes_rom_switchto` (four local thunks into the C;
      the `LF_RET` at `$fe4e00` is dead — switchto ends in `rte` on every path — and not transcribed).
      `transcription.SWITCH_ENTRIES` is the kind's table, its lengths derived from the addresses. WHAT THE PINS DO NOT
      REACH is held beside them (the fix pass): each thunk's BODY (which C it calls, its argument slots, a word's sign
      extension) and that a source's entries and thunks lie end to end with only the assembler's fill after the last
      (an `rts` after disp's `.size` passed every pin before).
    - THE HOST SCHEDULER MODEL, BEHIND A SWITCH THAT DEFAULTS TO REFUSING (ruling Q1's option S):
      `aes_switch.scheduling(reference, foreign=)` binds, for its own runs alone, the dispatch hook to `aes_disp` (C,
      host only: disp's loop), the idle hook to the case's deliveries and the process hook to a nested run of the ROM.
      Self-resume = the C returns; a FOREIGN process = the ROM's own code from switchto until the ROM's disp is about
      to re-enter the caller; the idle hook lays the delivery the ROM's run took at the same idle ordinal, after
      vetting the machine and the guard. THE ROM'S SIDE is `aes_switch.scheduled`: one run through the ROM's own
      dispatcher, interrupts delivered at the n-th IDLE. Compared: the answer, the idle count, the whole image less
      the named drops, each only where the ROM's run stored it. No committed case moved: everywhere else the hook
      still refuses.
    - THE SHAPES: savestate / switchto entered AS DISP ENTERS THEM by callers staged in the machine, ONE register file
      on both shores — so the UDA's context block is compared byte for byte; the by-nature drops each only where the
      ROM's run stored it (the caller's saved D1/D2 for the bare yield, the dispatcher's stack `$899a..$8c1a`, SR word
      `$8994`, the mask word); the glue entered as the ROM's own interrupt code enters it (`vet_the_glue`); idle swept
      at every instruction boundary with a move through OUR motion glue, on both blobs.
  - THE REVIEW'S VERDICT: **NO DEFECT IN THE SHIPPED C OR `.S`** — `evmulti.c`, `evdisp.c`, `switch.S` and `irq.S` all
    match the ROM, instruction by instruction. Everything found was about what HOLDS them, what flip 3 needs, one
    uninstalled piece, harness holes, memory and speed: (R2) THE TWIN'S POST-WAKE TAIL WAS EXECUTED BY NO TEST — a
    trap planted in its message arm and in its timer arm left 266 tests green, the "156 / 156 regions" coverage claim
    had been read off a file older than the battery, and the scratch wake probe no longer ran (it read a name deleted
    since); (R3) OUR GLUE WAS INSTALLED BY NOTHING — `gsx_setmb_aes` still handed the VDI the ROM's addresses on
    target, so `irq.S` was dead weight and every guarantee proved of it was proved of code the shipped path did not
    enter; (R3) THE DISPATCHER-STACK CHECK WAS MET BY CASE CHOICE — asked of the bare yield (230 / 240 bytes, 66 on
    top for an interrupt) where two forks queued go 264 / 274 and the ROM's own Timer C handler takes 140; forker's
    recorder MERGE arm red on target and silently outside the table; a width mutant of shipped C surviving (idle's
    fork count read as a long: `$c908` after it is live data); (R1) FLIP 3'S REHEARSAL REPRODUCED — 87 reds, NONE A
    DEFECT OF THE TWIN — AND WAS MISDIAGNOSED IN TWO PLACES that decide the flip's edits: the 59 file-selector reds
    were not "the C chkkbd's polls counted" (they are ONE `vq_mouse`, mchange's, and chkkbd's polls were in no ledger
    at all — the fix proposed would have left the event layer's VDI calls held by nothing), and four tests filed under
    "premise: ev_multi is the ROM's call" were real gaps on our shore (a twin that blocks at Tier 3 spun 16,000,000
    instructions instead of being refused; a door user's body diluted into ev_multi's cost — a gr_stilldn body ×7.4
    its ROM cost would have passed); also: 8 rows still DROPPED a fork code that compares exactly, the "one settling"
    differed from the older spellings on 5 of 111 rows, a plain C row could run the AES's ROM through a code pointer
    and be priced, the parked-QPB vet accepted any stack-band address holding the right bytes, six latent zygote
    defects, the in-flight claim's untested bound; (R4) the wave cost nothing and F2's levers are real, M's battery
    was the suite's fifth dearest file and held 2.0–2.1 GB a worker, the hoist into `aes_event` was a copy (eight
    definitions standing twice), and two kit levers (below).
  - THE ORCHESTRATOR'S RULINGS, binding, recorded as decisions:
    - **U1 — PRICING AFTER A FLIP: TWO COUNTS.** A door-arriving row is held twice, by derivation, for every rebound
      entry: our run against the ROM's with the rebound entries' calls in both, AND the caller's own cycles NET of the
      rebound entries (twin windows on our shore, the ROM routine's on the original's), each ≤ the bar. The RED test
      built for a delayed body through the door STAYS and must be red on both counts where it applies. STATUS quotes
      both where they differ by more than 0.05 (the section intro).
    - **U2** — a companion differential may leave out a VETTED BY-NATURE longword (the freed EVB's QPB address; a
      relocated code pointer): the rule "a dropped row has a differential that drops nothing" admits exactly those,
      each vetted. ev_multi's two message-wait rows are registered under it.
    - **U3** — get_evb's NULL is REFUSED BY NAME ON THE HOST at iasync (the oracle writes on through the vectors where
      a 68000 bus-errors: a pin there holds a state iron never reaches); the target keeps the plain store; a named
      divergence (`## Not reconstructed`). "Two accessories are enough" for EVB exhaustion is WRONG: argument-class
      only. (CORRECTED BY BAND 5 WAVE 0's MEASURE: the FIRST accessory brings no EVBs, so the supply is 15 + 5 per
      ALLOCATED accessory — 20 with two — and the list empties when PD0 asks six beside two six-way accessories:
      21 against 20. It needs PD0 asking 6: not booted.)
    - **U4** — the wake probes are COMMITTED as Tier 1 woken cases before the flip (the author's 27 interrupt wakes +
      the review's 13 writer wakes), host-only, with vetted only-where-stored drops, the ROM runs kept as derivations.
    - **U5** — OUR GLUE IS INSTALLED BY OUR CODE: on target gsx_setmb_aes / gsx_init / graphic_mode_change name OUR
      button and motion glue (the host stores the ROM's addresses; at Tier 3 the difference is a RELOCATION compared
      exactly, not a drop). The sites in code not reconstructed yet are recorded as band 5's (`## Not reconstructed`).
    - **U6** — the four relabelled rows (ev_mwait ×1, unsync ×3 gain `net`) are accepted; the legend says the tag
      follows the static call graph. **U7** — forker's recorder buffer is relocated like the queue's codes (no row
      choice hides the merge arm). **U8** — the eight rows that still DROP a fork code where it compares exactly lose
      the drop.
  - THE FIX PASS, step 1 — YF (the machinery and flip 3's blockers), thirteen items each RED → green: THE
    WHOLE-SESSION VDI LEDGER — the file selector's sessions compare EVERY `trap #2` of the ROM's run (inside its door
    calls of rebound entries too) with every VDI function a door binding serves on ours, chkkbd's polls and mchange's
    vq_mouse among them (the review proved 80 of 80 sessions equal; the flipped tree's 65 reds → 212 / 212). OUR OWN
    dsptch IS WATCHED: `DoorStops(dispatchers=)` names our blob's `aes_dsptch` beside the ROM's — a twin that blocks
    at Tier 3 is refused by name in one stop. THE TWO COUNTS (U1): the delayed-body test red before, green after on
    both trees, asserting which count catches it. `aes_fslib.run_session` child-first inside its own pass (the six
    real-GEMDOS runs: a dead worker → a named refusal or green); `NESTED_RUN_INSNS` 40,000 → 60,000, DERIVED from the
    deepest block a shadow runs (ev_multi asked for every event: 2,970 instructions to dsptch). The 17 flip-sensitive
    tests re-spelt on `aes_event.REBOUND`; three cases of the ROM-served road SKIP BY DERIVATION once the last entry
    is rebound (retire them with the dead code). THE GENERAL GUARD (`tier3.vet_our_run_kept_out_of_the_aes`): EVERY
    row's own run is profiled and its cycles in the AES's ROM held to the row's declared windows — over all 1,890 rows
    of its table ONE trip, DECLARED and held to exactly 16 cycles (`tier3.ENTERED_BY_THE_MACHINE_S_POINTER`: drawrat's
    `.S` row runs the ROM's justretf because the snapshot's `$947a` holds the ROM's address). NO CODE ADDRESS IS
    DROPPED ANY MORE (U7, U8): nine "dropped" lines leave the table (8 queue codes, the recorder's one) — the fork
    queue's codes, appl_trecord's records and the glue handed to the VDI are relocated and compared exactly; the
    symmetric-drop rule covers EVERY kind of drop but the Line-F mask word. The parked-QPB vet asks WHERE (our QPB's
    place must be the entry's own host slot of the running process); its "equal-address arm vets the bytes" was TRIED
    AND REFUSED BY MEASUREMENT (a staged machine carries no stack band: three committed cases red), reverted and
    pinned with the reason. THE ZYGOTE'S SIX LATENT DEFECTS, each with a RED test (block-buffered stderr; a named hook
    in a battery module made the zygote import the battery — the contract is now "a named hook lives in a module the
    zygote already holds"; a rebind without `monkeypatch` sidelines the zygote; fractional seconds; a request's own
    function object; one name per hook). THE CLAIM: a stopped maker is taken over at once, a derivation that RAISES is
    made by its waiters side by side, malformed claims have no maker, waiters back off (5 ms → 50 ms after 1 s), the
    bound exercised at its own value. ONE steering loop in `aes_event` (`steered_as_needed`: a fixpoint, the plain
    pass once, the answer kept by content); `fork_pool`'s submissions inside the `try` (the 1-in-15 BrokenProcessPool
    flake).
  - THE FIX PASS, step 1 — YM (ev_multi's battery): 41 WOKEN CASES committed (U4; `aes_evmulti.woken`: 28 by an
    interrupt, 13 by a writer), the ROM's shore ONE derivation kept by content, nothing dropped whole — a byte is left
    out only if it lies in the resumed process's own UDA, the mask word or an SR save word AND the ROM's run stored it
    after the resume AND the C holds the resume's byte there (23–42 bytes a case; six mutants that store where a drop
    could hide them are killed BY THE WOKEN TESTS ALONE). THE TAIL'S TRAPS ARE RED NOW: the message arm 17 tests, the
    timer arm 16, the key arm 19 (they left 266 green). A FRESH COVERAGE BUILD of this battery: `evmulti.c` 156 / 156
    regions. The review's nine survivors killed by nine new cases; the screen manager's REAL frame as the "216
    buttons" case. ROWS 15 → 26: the true worst (the fork queue full of moves, 0.87 / 0.92 with thunks) replaces the
    one-move row; the two message-wait rows registered (U2: the only runs of the frame-QPB arm on the 68000 build);
    THE PRESS FAMILY priced, nine rows 0.68–0.82 — it was NOT made measurable by a flip (the author's expectation,
    measured false): the ROM's bchange reaches post_button, a rebound entry, by its Line-F word under the ROM's
    forker, where ours calls the core, and Tier 3 now opens no window at an entry the build has rebound on either
    shore. get_evb's NULL refused by name on the host (U3; `evwait_c.o` byte-identical). THE BATTERY'S COST, serial,
    365 tests where it was 266: 36.1 → **7.1 CPU-s warm** (37.2 → 32.6 with every derivation made), ROM runs 1,444 →
    408, differentials 966 → 203, forks 719 → 265, and **peak RSS 2,100 → 587 MB** — the plain pass made once per
    steered case, which reasons a case needs kept by content, a bounded memo with the tests of one case collected back
    to back. No check weakened: every case's verdict is the run that returns, made every time.
  - THE FIX PASS, step 1 — the dispatcher (YD's items, re-run and finished by YZ): THE GLUE IS INSTALLED ON TARGET BY
    SIX RELOCATIONS (U5): `src_aes_gsxif_c.o` carries six `R_68K_32` against `aes_rom_button_glue` /
    `aes_rom_motion_glue` (two per function, three functions); the review's probe "named by value in aes_gsx_init,
    aes_gsx_setmb_aes, graphic_mode_change" answers NOTHING on both blobs; the three installer rows keep their cycles
    and ratios to the digit and gain no dropped line (six slots that can hold a glue's address relocated at our run's
    EXIT, compared exactly); the shipped path END TO END — over the machine OUR gsx_init left, the ROM's own VDI mouse
    interrupt enters OUR glue and spends 0 cycles in the AES's ROM text. THE STACKS, DERIVED: how deep our build can
    take the dispatcher's 640 bytes is READ OFF THE BLOB'S LISTING down every path (`aes_switch.StackReading`): **the
    bound 356 bytes on both blobs** (forker → bchange → mowner → wm_find → ob_find → ob_actxywh → ob_offset, an arm no
    machine reaches and the bound keeps; 360 before the gate's reading resolved each call through a register to the
    functions THAT register holds), **the deepest RUN 300 (bench blob) / 312 (shipped)** — a press on a window's
    title — **against the ROM's 188 whatever is queued**; the deepest `trap #2` taken at 168 / 178, EXACTLY the
    listing's, with the OS's own 130 under it; WHAT AN INTERRUPT NEEDS ON TOP measured from the ROM's own handlers
    entered from their vectors: **140** (ACIA, a mouse packet's last byte; Timer C on the tick that reaches the VDI's
    and the AES's), 100 (a vertical blank that redraws the cursor), **240 nested**; 356 + 240 = **596 of 640** — WITH
    THE ROM'S BIOS UNDER IT. THE GATE MEASURED OUR OWN ENTRIES (192 / 188 / 152: 344 nested) and our C VDI under the
    trap (162): **700 of 640 — the KNOWN ON-TARGET RISK under the Components table**. A
    frame deepened by 300 bytes under forker reds the derived check on both blobs (the first check passed it). The
    glue's private stacks 78 / 60 / 58 of 92 / 92 / 96: the listing's deepest path equal to the deepest case. forker's
    recorder MERGE arm green on target and priced (U7), Control-backslash a row. The width mutants killed 10 of 10 on
    a ROM-made machine with `$c908` nonzero; the interleaved sweep's arrival now REACHES `tst.w $c906`; the model's
    third arm a labelled case; the model nothing ran (`aes_switchto_model`) deleted; one reading of a run's three
    stops (`dispatcher_stop`).
  - THE FIX PASS, step 2 (YZ, alone in the tree): THE KIT'S TWO LEVERS, its own commit — the compare finds an EQUAL 64
    KB chunk by one `memcmp` over the two buffers IN PLACE (only a chunk that differs is copied out and walked, the
    same addresses in the same order), and the candidate's image is READ IN PLACE instead of `bytes(buf)` (16 MB a
    case, twice a poisoned one; sound by the ordering `candidate_image` already states: every compare is made before
    the next candidate run is handed a buffer). Content: the same 22,680 ids pass in `test` and `guarded`, the
    registry's 1,831 row hashes equal, the table byte-identical; the kit's own suite and the six other projects' side
    by side on HEAD's kit and the new one, test for test. THE ZYGOTE WAS LOST FOR A PROCESS'S WHOLE LIFE and nobody
    had seen it: the frozen-modules rule took `isr._BENCH`, the blob's LAZY CACHE (None → the bench at first use), for
    a rebound value, so the first transcription pin of a process sidelined its zygote for good (one battery alone:
    1,066 forks by the zygote; after one file of another: 0, the worker's own 1,072; in the whole suite one worker of
    ten made 860 forks itself) — and it was a latent RED by test order. Fixed (the cache named as not frozen; since the gate frozen BY ITS SHAPE,
    `aes_event.LAZY_CACHES`), with a census over the whole suite that found no other. THE ONE SETTLING, THE ONE REGISTRAR:
    `aes_event.settled_in_windows` is the one spelling (a word and a window alike); `aes_evlib.settled`,
    `aes_evinput.settled` and `aes_pdpipe`'s are DELETED and the three layers' `register` end on
    `aes_event.register_row` — 1,831 row hashes identical before and after, the equality test over EVERY registered
    row of the three layers. The hoist's leftover copies gone (the fork queue's code slots defined once,
    `aes_event.FORK_CODE_SLOTS`). `AddressHook._dispatch` records WHATEVER an effect raises (`pytest.fail` inside a
    hook passed green; the wrapper that did this at one seam is deleted: one mechanism). Conventions: one `jsr` macro
    (`M68K_JSR_LONG`), `running_process_id()` in `aes/evlib.h` — all 139 shipped objects byte-identical before and
    after step 2.
  - **THE PRE-COMMIT GATE (four finders, recall-biased) AND ITS FIX PASS.** Verdict: no defect in the shipped C or `.S`
    of this wave, no false green in the kit's compare (28,500 randomized pairs). What it found is what the checks
    could not see, and each is now held or said:
    - **THE DISPATCHER'S STACK UNDER OUR OWN INTERRUPT ENTRIES** — the derived check added the ROM's handlers' need to
      our frames. Measured with the build's own entries and its own C VDI under a trap: 356 + 152 + 192 = **700 of
      640**. NOT fixed: a strict xfail and the KNOWN ON-TARGET RISK under the Components table — which also holds
      what the measurement ran into, **our vertical blank does not survive the VDI's cursor redraw** (A6 kept across a
      RAM vector's `jsr`; a second strict xfail). The static reader's four silent shapes are named refusals (a call
      through a pointer of the machine — declared or refused —, a register nothing loads, a trap other than `trap
      #2`, a path off a listed body; and a jump through a table); a call through a register is resolved to what
      THAT register holds at the call, which made the bound 356 where the looser reading said 360.
      `vet_the_glue`'s three refusals each have a RED of their own.
    - **TIER 3, BEFORE FLIP 3**: (1) A RELOCATION LEFT UN-APPLIED IN THE BUILD IS REFUSED BY NAME — a blob whose
      `fork_bchange()` answered the ROM's address measured 26 of 26 rows green; now the four rows whose run queues it
      are refused at measure level (`vet_no_slot_names_the_rom`), the slots read off ONE RELOCATION REGISTRY
      (`aes_event.CODE_RELOCATIONS`) that every site reads (no table fetched from a battery by string with a silent
      default). (2) THE CALLER'S OWN IS A FIRST-CLASS COUNT: its own thunks measured call by call
      (`DoorWindows.glue_inside`) and counted back, the `glue` verdict on both counts, a pin on both
      (`CALLER_PINS`), a line of its own in the table that `test_status.py` PINS both ways — which found one row of
      this ledger quoting its pair in another form. THE ROWS the gate asked about (gr_stilldn ×7, ap_rdwr ×3,
      ev_mesag's three on the rehearsed flip), settled by measurement: every thunk of theirs ran INSIDE the rebound
      entry's call — 0 of 276 / 316 / 424 / 208 are the caller's — so their second counts are 1.04 (354 against 340)
      and 0.51 with their thunks as without: none over the bar. (3) every door call opened is closed; the companion
      of a freed QPB's address holds it to the entry's own slot; the dispatcher's stack is put back over the frames
      our run PUSHED alone (a stray store under them stays, and differs); the one declared entry by a pointer is
      held to its SPAN, and a stale declaration is refused in its own words.
    - **THE KIT** (its own commit): a compare chunk that began below 0 reached `memcmp` (a dead worker, or two
      unrelated regions compared equal) — bounded; an image of no bytes answers as it did; the in-place view is
      RELEASED after each compare (a reader that outlives it fails loudly); the watchdog's own test no longer depends
      on where `$TMPDIR` lies. Fuzz against HEAD's compare: 28,800 cases, 0 mismatches. The kit's suite 1,241 passed;
      the six other projects' suites unchanged test for test.
    - **THE HARNESS**: a word that differs by nature is settled WHOLE or refused (half a word stored was staged and
      dropped in silence); the registry of settled rows is held to an INDEPENDENT spelling (the oracle's own run, not
      the function the registrar calls) and to a CENSUS of the wider kinds (psetup's bracket: psetup, pstart;
      savptr moved by the run alone: mchange's playback row); what a hook's effect raises is the case's outcome
      by type and traceback, a skip is a skip, and a Ctrl-C inside an effect stops the session once the C has
      returned; a lazy cache is frozen BY SHAPE (None → its first value, no further), held without a zygote.
    - **SPEED AND MEMORY, content-neutral** (all 139 shipped objects and both blobs byte-identical before and
      after; the table's every measured line equal — only the `TWO COUNTS` lines and one legend sentence added):
      fs_input's 117 fresh interpreters are the zygote's forks (its declared child doors run in the fork: 171 → 155
      CPU-s for that battery, warm); the in-flight claim's rest grows from the first look; the dispatcher model's
      nine cached ROM runs are two at a time and keep a megabyte of start image, not sixteen (670 → 464 MB at the
      file's end); the replay machinery's cases give their images back as each ends (639 → 230 MB).
      The whole suite on a tree with its bytecode, ten workers, each run started as the last ended (1-minute load
      8 → 53): warm 139.3 s / 1,221 CPU-s before, **138.7 s / 1,213 CPU-s** after with 45 more tests; cold 198.4 s /
      1,489 → **196.0 s / 1,464**.
    - NOT DONE, said: the two fork harnesses that serve the dispatch hook from a ROM run are still two
      (`aes_evmulti._the_twin_s_tail`, `aes_switch.modelled`); `aes_switch`'s hand-rolled bench loops; the C's
      milliseconds-into-ticks spelt three times and the mouse-owner test twice (a hoist moves no object, and was not
      made); the door users' rows still settle through `aes.register` where no SR bracket is reached (the census
      does not reach them); ev_multi's two QPB rows are in no layer's census; `acancel`'s answer OR'd into what
      arrived is UNPINNED and said so where the woken cases are claimed.
  - **K5 — A PRICING GAP MEASURED AND DELIBERATELY NOT LANDED (the user's ruling pending; the block under the
    Components table has the rows).** (V)'s classifier reads `trap #2` off the build's call graph; widened to `trap #1
    / #2 / #13 / #14` for the AES's rows the existing machinery prices them with no refusal — and 26 committed rows
    move, 16 become `net` at or under the bar, TEN END OVER (aes_bell ×4 1.60; dos_alloc "no memory" 1.19; dos_lseek
    1.18; dos_read 1.13; dos_sfirst "found" 1.12; dos_open ×2 1.12 / 1.103). The sixteen that do not: dos_sfirst
    "EFILNF" 1.06 (342 against 322), dos_snext ×2 1.06 / 1.05, rom_rsc_init 1.00, dos_alloc ×2 0.96 / 0.89, gsx_mfree
    0.90, sh_find ×3 0.81 / 0.81 / 0.64, rs_readit ×2 0.79 / 0.18, rs_load ×2 0.76 / 0.19, gsx_malloc 0.77, rs_free
    0.75. THE LEAF RULE DOES NOT CARRY THE TEN as written: it admits only rows NAMED as (A)-only trap leaves and is
    not asked of a (V) row; on its numbers alone (an excess of at most 40 cycles AND at most 7.5 % of the dispatched
    call) aes_bell's +52 and dos_lseek's +48 fail the first — named, and with the rule asked of (V) rows, five of the
    ten would be `rule`. The patch (67 lines) is in the scratchpad and is NOT in the tree: on the patched tree
    `test_tier3.py` + `test_status.py` are 12 failed / 2,809 passed — exactly those ten rows and STATUS's two. Nine
    rows of the same class in the VDI and GEMDOS were measured by a probe (the block).
  - FLIP 3 REHEARSED ON THE FINAL TREE (a private tree = the final tree + the one edit in `evdoor.h`): `make bench`
    1,903 rows, 0 OVER / DRIFTED; the whole suite **2 failed, 22,676 passed, 5 skipped** — THE ONLY REDS ARE THE
    FLIP'S OWN DOCS (`test_status`'s two: STATUS rows quoting pre-flip ratios, and this phase's 14 addresses, red on
    the plain tree until this docs pass); three more skips by derivation (the ROM-served road's cases). The review's
    rehearsal, before any fix, was 87 reds (F2's first, 92; before the relocation, 348 and `make bench` dead at its
    first interrupted row). **98 ROWS WILL MOVE**, every one's OUR column alone (the ROM's in 0), 56 at two decimals;
    their ratios 0.53 / 0.68 / 1.04 (min / median / max) → 0.58 / 0.68 / **0.85**. By routine: fs_input 21, fm_do 18,
    gr_stilldn 7, fm_alert 7, eralert 7, fm_error 7, gr_dragbox 5, gr_slidebox 5, gr_watchbox 4, mn_do 4, gr_wait 4,
    gr_rubbox 3, fm_show 3, gr_rubwind 2, fm_button 1. UNDER THE TWO-COUNT RULE AFTER THE FLIP: gr_stilldn ×7
    **0.71–0.72 own, 1.04 the caller's own** (354 against 340 — its pre-flip number, to the cycle: the dilution the
    review measured is closed); bchange ×4 0.58–0.87 / 0.63–1.01; fs_input "a drag, a page, …" 0.73 / 0.78; mn_bar
    "hidden" 0.50 / 0.66; mn_do ×2 0.66–0.67 / 0.61; 176 rows then carry both, 43 differ by more than 0.05, 8 are over
    1.00 on the caller's own, none over 1.05 on either count.
  - THE TABLE AGAINST HEAD'S (2,997 → 3,126 lines; 1,851 → 1,903 rows): 0 removed; **52 added** (the dispatcher's 26:
    forker 6, idle 4, savestate 3, disp_act 2, switchto 2, drawrat 2, mwait_act 1, dsptch 1, cli, spl7_save,
    spl_restore, sti, justretf; ev_multi's 26); **4 moved in their verdict tag alone** (blank → `net`, U6: ev_mwait
    "its event come already" 0.61, unsync ×3 0.57 / 0.45 / 0.45 — cycles and ratios identical: their routines call
    `aes_dsptch`, which reaches `trap #2` in our build's call graph through disp, idle and chkkbd); 157 rows'
    SUB-lines change (U1's second count printed; nine "dropped" lines gone); NO RATIO OF HEAD'S ROWS MOVES. OBJECTS,
    shipped configuration: 136 → 139; 134 byte-identical; DIFFER `src_aes_gsxif_c.o` (U5) and `src_aes_switch_S.o`;
    NEW `src_aes_evdisp_c.o`, `src_aes_evmulti_c.o`, `src_aes_irq_S.o`. The ROM build's image is HEAD's own (sha256
    1d736545…): nothing of the wave is linked into it.
  - THE SUITE'S SPEED, content-neutral (the same ids and outcomes, the row hashes, the table, the guarded suite). The
    whole suite as `make test` runs pytest; "before" is the tree as step 2 found it, "after" the final tree; CPU-s is
    user + sys of the whole process tree; THE LOADS ARE THE SUITE'S OWN (ten workers, their zygotes and children) —
    quiet at each start:

    | run (bare `pytest -n auto`, ten workers, one machine) | before step 2 (22,675 passed + the docs' red) | the final tree (22,680 + the same red) | 1-minute load, before / after |
    |---|---|---|---|
    | COLD (`rm -rf build/derived` first) | 231 s; 1,778 CPU-s (1,132 user + 646 sys) | **209 s; 1,560 CPU-s** (997 + 563): −12 % CPU, −10 % wall | 7.7 → 55 / 10.5 → 58 |
    | WARM, first | 170 s; 1,492 CPU-s (987 + 505) | **146 s; 1,288 CPU-s** (855 + 433): −14 % | 55 → 49 / 58 → 38 |
    | WARM, second | 171 s; 1,485 CPU-s (984 + 501) | 156 s (collect-only probes beside it); **1,287 CPU-s** (853 + 434) | 49 → 47 / 38 → 77 |
    | `make gates` from an EMPTY build, a private copy (cold; NOT quiet: load 100–125) | 497 s; 3,387 CPU-s (YD's last, load 18 → 119) | 459 s; 3,064 CPU-s (1,972 + 1,092) | — |
    | `make gates` from an EMPTY build, the SHARED tree (cold) | — | **375 s; 2,985 CPU-s** (1,933 + 1,052) | 7.5 at its start → 144 at its end (its own two suites) |

    Of the warm 1,488 → 1,288 CPU-s the zygote's fix is at least ≈ −60 and the kit's two levers ≈ −140 (the
    attribution run was made under load 60–85). HEAD's handed figures were 1,841 CPU-s cold and 1,324 warm for 21,866
    tests: the wave adds 815 tests and the suite is cheaper than it was. The review's whole-suite pair, under load
    75–290, before any lever of the fix pass: cold bare 1,819 → 1,717 CPU-s, warm 1,449 → 1,429. A worker's peak RSS,
    1.7–2.4 GB at the review (HEAD: 0.70–0.84), is back under 0.6 GB for the battery that held it. No check was
    weakened for time.
  - MUTATION, strict, as each sweep finally reported it (private builds, the rebuild forced, a control no-op surviving
    in each): **the prerequisites (F2)** 36 hand mutants — 34 KILLED / 2 SURVIVED / 0 ABNORMAL (one redundant by
    construction, one equivalent in effect), and the claim's 20 / 20; **the machinery's fix (YF)** 61 — 60 / 0 / 1
    ABNORMAL (the fork-first guard removed crashes the worker in the guard's own RED test: the pre-fix state itself);
    **ev_multi (YM)** 222 mutants of `evmulti.c` / `evmulti.h` / iasync's refusal, the leaf battery ALONE — **202 / 20
    / 0**: the author's 114 → 113 / 1, the review's 88 → 69 / 19 (it was 44 / 44), the three traps in the tail 3 / 3,
    the fix's own 17 / 17; of the 20, 19 argued equivalent and ONE unpinned by name (`j09`); **the dispatcher on the
    final tree (YZ)** `evdisp.c` 66 — 64 / 2 / 0 (both equivalent: the poll moved after the drain of the woken list;
    the guard decremented where it is cleared), the target's text 16 — 16 / 0 / 0 (both blobs rebuilt each: the glue's
    addresses, the thunks, bytes outside a sized symbol, two frames deepened, the `jsr` macro), the harness's Python
    30 — 29 / 1 / 0 (equivalent: a glue's stack count not restarted — each `lea <stack top>,sp` is its glue's second
    instruction) plus two "mutants" that delete a TEST's own assertion (no mutants of code under test: nothing tests a
    test); **step 2 (YZ)** the kit's two levers 12 / 12, the one settling 8 / 8, the zygote's fix 2 / 2, the hook's
    BaseException 1 / 1, the code slots 1 / 1 — and two PRE-EXISTING survivors met and left, by name: unsync's
    `answer_compared` arm (wave 1's: pinned by no test) and the handed routines in `CURSOR_HOOKS` (unused by its one
    case). TWO MUTANTS ARE BLIND TO A WARM PYTHON SWEEP — they change what a KEPT derivation computes, and the
    unmutated answer is served — and are KILLED with `AES_DERIVED_OFF=1`. NOT swept by a generator: `aes_event.py` and
    `tier3.py` as wholes (hand mutants of what changed only; the review's sampled sweep ran 14 of 50 queued).
  - COVERAGE, fresh instrumented builds (llvm, `-O0`, continuous mode so the forks count) made by the fix pass:
    `evmulti.c` 156 / 156 regions, 8 / 8 functions, 119 / 119 lines, 66 / 66 branch outcomes (the tail's key arm 31
    times, its message arm 19, its timer arm 18); `evdisp.c` 78 / 78 regions, 7 / 7 functions, 69 / 69 lines, 30 / 30
    branch outcomes. No other coverage claim is made.
  - GATES: the shared tree, ONCE, at the end of the fix pass, from an EMPTY build and a cold cache — test 22,680
    passed / 1 failed / 2 skipped, guarded the same, the ROM build 0 with HEAD's own image; the one red in both suites
    `test_status::test_every_address_the_table_prices_has_a_verified_row` (this phase's 14 addresses with no STATUS
    row yet: expected, and nothing else); no worker died; 375 s, 2,985 CPU-s. Every new or changed test ALONE: the
    dispatcher's 259 / 259 warm and 43 / 43 of a cold sample, ev_multi's 365 / 365 warm and 40 / 40 cold.
    `AES_STEERED_FOR_NOTHING=1` over evmulti / evdisp / evlib / evinput / evfork: 1,938 passed. Strays: none. Orphans
    (README's check): none. Then this docs pass, with the rows in: `## Suite`. NOT RUN by any agent: `my-code-review`
    (the orchestrator's gate).
  - FOUND IN THE HARNESS ON THE WAY, and closed: a Python exception inside a ctypes hook callback was SWALLOWED — an
    `Exception` in the scheduler's own hooks, and any `BaseException` that is none (`pytest.fail`) in every
    `AddressHook`; `run_core_steered`'s reasons were order-dependent (the fixpoint); a mutant tree gone stale against
    the shared tree made one "KILLED" a baseline red (check the baseline before trusting a kill); a test's
    `monkeypatch.undo()` undid the file's own-cache fixture and left a dangling `*.claim` link in whatever cache it
    ran in (fixed the same hour; the shared build held none).
* **Wave 17 band 4 wave 2, FLIP 3 (2026-10-08) — ev_multi rebound: every entry of the event door is C on both
  builds.** One agent, its own commit, on the tree phase A left (`a092f2b`). No routine ported, no source but the
  header; one test added (`test_status`'s pin of the door's state), none edited, weakened or deleted.
  - THE ONE HAND EDIT, `include/aes/evdoor.h` (the rehearsed `flip3.py`, then read): `evdoor_ev_multi` re-spelt
    through `EVDOOR_REBOUND`, the include that declares the twin (`aes/evmulti.h`); the ROM-serving wrapper — the
    host's frame for the nested run, the target's two-shape inline `jsr` (`EVDOOR_EV_MULTI_CALL`) — deleted with it;
    and ONE COMMENT made true (the wrappers' heading said "first the entry the ROM still serves"). NOTHING ELSE was
    forced: `REBOUND`, `PENDING` (now empty), the shadowed set, the door's bindings (`polls_in_c`: the poll's VDI
    calls and the fork queue served under every door call), Tier 3's lists and the flip-proof tests followed by
    derivation. LEFT IN THE HEADER, dead, for the retirement the Next line names: `event_door` (the SERVED answer's
    reader), `evdoor_shape_unbuilt`, the heading comment's "until it is" paragraphs.
  - THE SUITE on the flipped tree before any doc moved (the rehearsal's result): the only reds `test_status`'s three —
    the ratio cells, the quoted second counts, the differing pairs not quoted — green once the ledger was re-quoted
    from the flip's own table. THREE TESTS NOW SKIP BY DERIVATION, each naming its retirement in its reason (the
    ROM-served road has no entry left): `test_aes_event.py::test_the_door_s_writes_are_compared`,
    `::test_an_entry_left_to_a_twin_its_wrapper_does_not_call_halts_by_name`,
    `test_tier3.py::test_the_door_rule_refuses_rom_aes_code_run_outside_a_window`. NO SHADOW REFUSAL: the twin differs
    from the ROM's routine at none of its shadowed arrivals.
  - THE TABLE (`make bench` on `a092f2b` saved before, the flipped tree's after, each from a removed library and
    removed blobs): 1,903 rows both, 0 added, 0 removed, the same nine verdict counts, **0 OVER, 0 DRIFTED on either
    count**; 3,289 → 3,311 lines (22 more `TWO COUNTS` lines). BYTE-IDENTICAL to the gate-fix pass's rehearsed table.
    **98 MOVED** in 15 routines: fs_input 21, fm_do 18, gr_stilldn 7, fm_alert 7, eralert 7, fm_error 7, gr_dragbox
    5, gr_slidebox 5, gr_watchbox 4, mn_do 4, gr_wait 4, gr_rubbox 3, fm_show 3, gr_rubwind 2, fm_button 1. Every
    one: the original's column unchanged, the verdict still `net`; our cycles LOWER in 90, HIGHER in 8 (+8 to +40:
    slices of fm_do's 38-key session and of three fs_input sessions — three of them arrive at no door call at all, the
    wrapper's change of shape in their routine's frame).
    - THE FIRST COUNT (own, the ratio column): 0.53 / 0.68 / 1.04 (min / median / max) → 0.58 / 0.68 / **0.85**; 56
      moved at two decimals (30 down, 26 up), 8 by more than 0.05 (gr_stilldn ×7 1.04 → 0.71–0.72; mn_do "the button
      pressed off the bar" 0.61 → 0.67). With thunks 0.61 / 0.74 / 0.92.
    - THE SECOND COUNT (the caller's own, 95 of the 98 — 22 had ONE count before, their ev_multi a window): 0.53 /
      0.68 / **1.04**; the highest is gr_stilldn's seven, 354 cycles against the ROM's 340 (20 cycles under the bar),
      1.04 with its thunks; next bchange's 1.01 (not moved). 185 rows of the table carry both (163 before), 40 apart
      by more than 0.05 (33).
    - THE WHOLE RUN: 0.79 / 0.95 / 1.00 → 0.76 / 0.94 / 0.99.
    - A ratio that ROSE did not get dearer: the ROM's ev_multi and its twin are in both columns now (5,328–5,434
      cycles against 3,662–3,818 a call under gr_stilldn: 0.69–0.70).
    - EVERY MOVED ROW (cycles; `own` is the ratio column's pair, ours / the ROM's in the AES's text; `the caller's
      own` is net of the rebound entries' calls; "a window" = one count before the flip, ev_multi off both sides):

      | routine | case | the ROM's whole run, cycles | ours, whole: before → after | whole-run ratio | own, ours against the ROM's (the ratio column): before → after | the caller's own, ours against the ROM's: before → after |
      |---|---|---|---|---|---|---|
      | gr_stilldn | the button up, waiting to leave: it rose | 12560 | 12574 → 11240 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4162 / 5758 = 0.72 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button up, waiting to enter: the rise wins over the rectangle | 12576 | 12590 → 11250 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4172 / 5774 = 0.72 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button up, outside, waiting to enter: it rose | 12514 | 12528 → 11208 | 1.00 → 0.90 | 354 / 340 = 1.04 → 4130 / 5712 = 0.72 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button down, inside, waiting to enter: the rectangle | 12516 | 12530 → 11126 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4048 / 5714 = 0.71 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button down, outside, waiting to leave: the rectangle | 12470 | 12484 → 11094 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4016 / 5668 = 0.71 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button down, an empty rectangle at the mouse, waiting to leave: left | 12470 | 12484 → 11094 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4016 / 5668 = 0.71 | one count (a window) → 354 / 340 = 1.04 |
      | gr_stilldn | the button down, a rectangle at negative words, waiting to enter: inside | 12516 | 12530 → 11126 | 1.00 → 0.89 | 354 / 340 = 1.04 → 4048 / 5714 = 0.71 | one count (a window) → 354 / 340 = 1.04 |
      | gr_watchbox | OK, selected while inside: it rose, inside | 40780 | 36442 → 35150 | 0.89 → 0.86 | 8078 / 12840 = 0.63 → 11838 / 18168 = 0.65 | one count (a window) → 8108 / 12840 = 0.63 |
      | gr_watchbox | Cancel | 40474 | 36232 → 34940 | 0.90 → 0.86 | 7864 / 12530 = 0.63 → 11624 / 17858 = 0.65 | one count (a window) → 7894 / 12530 = 0.63 |
      | gr_watchbox | the arrow, crossed while inside | 133980 | 127910 → 126614 | 0.95 → 0.95 | 25018 / 33796 = 0.74 → 28834 / 39184 = 0.74 | one count (a window) → 25048 / 33796 = 0.74 |
      | gr_watchbox | OK, drawn normal while inside | 21798 | 19220 → 17928 | 0.88 → 0.82 | 4340 / 7010 = 0.62 → 8100 / 12338 = 0.66 | one count (a window) → 4370 / 7010 = 0.62 |
      | mn_do | the mouse moved off the bar | 64418 | 53074 → 51314 | 0.82 → 0.80 | 13466 / 25434 = 0.53 → 19810 / 33906 = 0.58 | one count (a window) → 13544 / 25434 = 0.53 |
      | mn_do | the button pressed on a title | 53488 | 47212 → 45674 | 0.88 → 0.85 | 10552 / 17344 = 0.61 → 16388 / 24994 = 0.66 | one count (a window) → 10624 / 17344 = 0.61 |
      | mn_do | the button pressed off the bar | 57654 | 51378 → 49646 | 0.89 → 0.86 | 10552 / 17344 = 0.61 → 18250 / 27142 = 0.67 | one count (a window) → 10624 / 17344 = 0.61 |
      | mn_do | a DISABLED item clicked: nothing chosen, the title put back | 1186762 | 1122130 → 1117558 | 0.95 → 0.94 | 130062 / 206178 = 0.63 → 147214 / 228914 = 0.64 | one count (a window) → 130108 / 206178 = 0.63 |
      | gr_wait | the button up, one box: it rose | 90990 | 90108 → 88774 | 0.99 → 0.98 | 12924 / 15834 = 0.82 → 16732 / 21252 = 0.79 | one count (a window) → 12924 / 15834 = 0.82 |
      | gr_wait | the button up, two boxes | 171216 | 169706 → 168372 | 0.99 → 0.98 | 24462 / 29856 = 0.82 → 28270 / 35274 = 0.80 | one count (a window) → 24462 / 29856 = 0.82 |
      | gr_wait | the button down, the pixel away from the mouse: it left | 90900 | 90018 → 88628 | 0.99 → 0.97 | 12924 / 15834 = 0.82 → 16586 / 21162 = 0.78 | one count (a window) → 12924 / 15834 = 0.82 |
      | gr_wait | the button down, two boxes, the pixel away | 171126 | 169616 → 168226 | 0.99 → 0.98 | 24462 / 29856 = 0.82 → 28124 / 35184 = 0.80 | one count (a window) → 24462 / 29856 = 0.82 |
      | gr_rubbox | stretched to the mouse | 111594 | 109142 → 107808 | 0.98 → 0.97 | 16910 / 21654 = 0.78 → 20718 / 27072 = 0.77 | 16476 / 20904 = 0.79 → 16476 / 20904 = 0.79 |
      | gr_rubbox | held at the minimum | 102008 | 99556 → 98234 | 0.98 → 0.96 | 16914 / 21658 = 0.78 → 20644 / 26986 = 0.76 | 16480 / 20908 = 0.79 → 16480 / 20908 = 0.79 |
      | gr_rubbox | the mouse left of the box | 110930 | 108478 → 107156 | 0.98 → 0.97 | 16912 / 21656 = 0.78 → 20642 / 26984 = 0.76 | 16478 / 20906 = 0.79 → 16478 / 20906 = 0.79 |
      | gr_rubwind | a window's outline twin | 200318 | 197172 → 195838 | 0.98 → 0.98 | 28216 / 35510 = 0.79 → 32024 / 40928 = 0.78 | 27782 / 34760 = 0.80 → 27782 / 34760 = 0.80 |
      | gr_dragbox | the mouse inside: it stays | 104674 | 101996 → 100662 | 0.97 → 0.96 | 17140 / 22294 = 0.77 → 20948 / 27712 = 0.76 | 16706 / 21544 = 0.78 → 16706 / 21544 = 0.78 |
      | gr_dragbox | below and right of the mouse: it jumps to it | 104662 | 102006 → 100672 | 0.97 → 0.96 | 17166 / 22298 = 0.77 → 20974 / 27716 = 0.76 | 16732 / 21548 = 0.78 → 16732 / 21548 = 0.78 |
      | gr_dragbox | outside the bound: pulled in | 104178 | 101500 → 100166 | 0.97 → 0.96 | 17156 / 22310 = 0.77 → 20964 / 27728 = 0.76 | 16722 / 21560 = 0.78 → 16722 / 21560 = 0.78 |
      | gr_dragbox | wider than the bound: past its left edge | 111260 | 108604 → 107270 | 0.98 → 0.96 | 17184 / 22316 = 0.77 → 20992 / 27734 = 0.76 | 16750 / 21566 = 0.78 → 16750 / 21566 = 0.78 |
      | gr_slidebox | at the top, the mouse outside: 0 | 107116 | 101290 → 99956 | 0.95 → 0.93 | 20118 / 28620 = 0.70 → 23926 / 34038 = 0.70 | 19684 / 27870 = 0.71 → 19684 / 27870 = 0.71 |
      | gr_slidebox | low, the mouse above it in the track: it jumps up | 107088 | 101250 → 99916 | 0.95 → 0.93 | 20094 / 28608 = 0.70 → 23902 / 34026 = 0.70 | 19660 / 27858 = 0.71 → 19660 / 27858 = 0.71 |
      | gr_slidebox | the whole track: no room | 118764 | 112924 → 111590 | 0.95 → 0.94 | 19748 / 28172 = 0.70 → 23556 / 33590 = 0.70 | 19314 / 27422 = 0.70 → 19314 / 27422 = 0.70 |
      | gr_slidebox | across, one pixel of room | 106990 | 101142 → 99808 | 0.95 → 0.93 | 20078 / 28602 = 0.70 → 23886 / 34020 = 0.70 | 19644 / 27852 = 0.71 → 19644 / 27852 = 0.71 |
      | gr_dragbox | moved, the cursor shown | 284590 | 281034 → 278306 | 0.99 → 0.98 | 33802 / 42414 = 0.80 → 44144 / 56128 = 0.79 | 33368 / 41664 = 0.80 → 33368 / 41664 = 0.80 |
      | gr_rubwind | a window's outline stretched | 406096 | 400892 → 398164 | 0.99 → 0.98 | 53116 / 66444 = 0.80 → 63458 / 80158 = 0.79 | 52682 / 65694 = 0.80 → 52682 / 65694 = 0.80 |
      | gr_slidebox | the elevator dragged down | 200560 | 193656 → 190928 | 0.97 → 0.95 | 33664 / 45456 = 0.74 → 44006 / 59170 = 0.74 | 33230 / 44706 = 0.74 → 33230 / 44706 = 0.74 |
      | fm_button | OK: watched, selected, an exit | 49886 | 41640 → 40348 | 0.83 → 0.81 | 13176 / 21946 = 0.60 → 16936 / 27274 = 0.62 | 9092 / 14558 = 0.62 → 9122 / 14558 = 0.63 |
      | fm_do | Return in the ring | 142732 | 115770 → 113304 | 0.81 → 0.79 | 58380 / 88142 = 0.66 → 63000 / 95504 = 0.66 | 55550 / 82548 = 0.67 → 55594 / 82548 = 0.67 |
      | fm_do | abc, then Return, in the ring | 828920 | 723612 → 713706 | 0.87 → 0.86 | 278908 / 401272 = 0.70 → 297346 / 430720 = 0.69 | 276078 / 395678 = 0.70 → 276212 / 395678 = 0.70 |
      | fm_do | OK clicked, released on it | 184308 | 147746 → 145120 | 0.80 → 0.79 | 71112 / 111374 = 0.64 → 83130 / 126662 = 0.66 | 64198 / 98392 = 0.65 → 64272 / 98392 = 0.65 |
      | fm_do | off the dialog: the bell, then Return | 169004 | 140954 → 136946 | 0.83 → 0.81 | 60116 / 91242 = 0.66 → 74334 / 110204 = 0.67 | 57286 / 85648 = 0.67 → 57356 / 85648 = 0.67 |
      | fm_do | the name field clicked, a key typed, Return | 437318 | 363458 → 357106 | 0.83 → 0.82 | 159458 / 244442 = 0.65 → 176780 / 269036 = 0.66 | 156628 / 238848 = 0.66 → 156736 / 238848 = 0.66 |
      | fm_do | a DISABLED OK clicked, then Return | 176370 | 143398 → 139518 | 0.81 → 0.79 | 66650 / 103130 = 0.65 → 79358 / 120362 = 0.66 | 63820 / 97536 = 0.65 → 63890 / 97536 = 0.66 |
      | fm_do | typed, Left, Delete, Right, Return | 991374 | 861452 → 846586 | 0.87 → 0.85 | 339862 / 490044 = 0.69 → 367512 / 534216 = 0.69 | 337032 / 484450 = 0.70 → 337226 / 484450 = 0.70 |
      | fm_do | Tab to the name, typed, Return | 408018 | 344696 → 337274 | 0.84 → 0.83 | 145450 / 218648 = 0.67 → 159286 / 240734 = 0.66 | 142620 / 213054 = 0.67 → 142728 / 213054 = 0.67 |
      | fm_do | a 37-character path: Backspace, Return | 405298 | 357840 → 352894 | 0.88 → 0.87 | 162522 / 217668 = 0.75 → 171748 / 232392 = 0.74 | 159692 / 212074 = 0.75 → 159766 / 212074 = 0.75 |
      | fm_do | a 37-character path: a key, Return | 413196 | 363126 → 358180 | 0.88 → 0.87 | 167408 / 225294 = 0.74 → 176634 / 240018 = 0.74 | 164578 / 219700 = 0.75 → 164652 / 219700 = 0.75 |
      | fm_do | a 37-character path: Left, Delete, Return | 500316 | 440294 → 432868 | 0.88 → 0.87 | 206632 / 275974 = 0.75 → 220464 / 298060 = 0.74 | 203802 / 270380 = 0.75 → 203906 / 270380 = 0.75 |
      | fm_do | a 37-character path: Escape, Return | 719194 | 670544 → 665598 | 0.93 → 0.93 | 143118 / 199364 = 0.72 → 152344 / 214088 = 0.71 | 140288 / 193770 = 0.72 → 140362 / 193770 = 0.72 |
      | fm_do | a radio button clicked, then Return | 145782 | 114618 → 110758 | 0.79 → 0.76 | 45030 / 78718 = 0.57 → 57758 / 95950 = 0.60 | 38116 / 65736 = 0.58 → 38182 / 65736 = 0.58 |
      | fm_do | a 38-key session: the dialog taken, to its first wait | 58116 | 45704 → 45744 | 0.79 → 0.79 | 26732 / 40564 = 0.66 → 26772 / 40564 = 0.66 | 25308 / 37758 = 0.67 → 25348 / 37758 = 0.67 |
      | fm_do | a 38-key session: the first key, to a VDI call inside it | 110168 | 90538 → 88032 | 0.82 → 0.80 | 49826 / 72788 = 0.68 → 54406 / 80150 = 0.68 | one count (a window) → 49830 / 72788 = 0.68 |
      | fm_do | a 38-key session: the first key, from that VDI call to the next wait | 123192 | 116714 → 116740 | 0.95 → 0.95 | 24762 / 32772 = 0.76 → 24788 / 32772 = 0.76 | one count (no door call) → one count (no door call) |
      | fm_do | a 38-key session: the last character typed | 245426 | 221214 → 218734 | 0.90 → 0.89 | 95842 / 124674 = 0.77 → 100448 / 132036 = 0.76 | one count (a window) → 95872 / 124674 = 0.77 |
      | fm_do | a 38-key session: Return, to the return | 94186 | 80046 → 77540 | 0.85 → 0.82 | 36754 / 52426 = 0.70 → 41334 / 59788 = 0.69 | 35348 / 49638 = 0.71 → 35352 / 49638 = 0.71 |
      | fm_alert | the longest alert (AES string 16), Return | 1617946 | 1553492 → 1551022 | 0.96 → 0.96 | 164158 / 245060 = 0.67 → 168774 / 252422 = 0.67 | 160972 / 238788 = 0.67 → 161012 / 238788 = 0.67 |
      | fm_alert | the shortest alert (AES string 18), Return | 909106 | 855926 → 853456 | 0.94 → 0.94 | 99732 / 163984 = 0.61 → 104348 / 171346 = 0.61 | 96546 / 157712 = 0.61 → 96586 / 157712 = 0.61 |
      | fm_alert | an application's: no icon, one button, Return | 660246 | 608752 → 606282 | 0.92 → 0.92 | 91094 / 152280 = 0.60 → 95710 / 159642 = 0.60 | 87908 / 146008 = 0.60 → 87948 / 146008 = 0.60 |
      | fm_alert | an application's: three buttons, Return | 1379178 | 1321036 → 1318566 | 0.96 → 0.96 | 132628 / 206322 = 0.64 → 137244 / 213684 = 0.64 | 129442 / 200050 = 0.65 → 129482 / 200050 = 0.65 |
      | fm_alert | an application's: five lines at the cap, three buttons, Return | 1776364 | 1708674 → 1706204 | 0.96 → 0.96 | 180916 / 267294 = 0.68 → 185532 / 274656 = 0.68 | 177730 / 261022 = 0.68 → 177770 / 261022 = 0.68 |
      | fm_alert | the third of three buttons clicked | 1414716 | 1350488 → 1347858 | 0.95 → 0.95 | 141368 / 221724 = 0.64 → 153382 / 237012 = 0.65 | 134098 / 208064 = 0.64 → 134168 / 208064 = 0.64 |
      | fm_alert | the documented maximum, the cursor shown, Return typed | 2108632 | 2040632 → 2038162 | 0.97 → 0.97 | 187642 / 274714 = 0.68 → 192258 / 282076 = 0.68 | 184456 / 268442 = 0.69 → 184496 / 268442 = 0.69 |
      | fm_show | Bad Function #, no values (an unimplemented call's) | 975854 | 920154 → 917684 | 0.94 → 0.94 | 101884 / 168748 = 0.60 → 106500 / 176110 = 0.60 | 98698 / 162476 = 0.61 → 98738 / 162476 = 0.61 |
      | fm_show | TOS error #%W, a word | 1048926 | 993152 → 990682 | 0.95 → 0.94 | 109614 / 176704 = 0.62 → 114230 / 184066 = 0.62 | 106428 / 170432 = 0.62 → 106468 / 170432 = 0.62 |
      | fm_show | insert disk %S, a name | 1129794 | 1072260 → 1069790 | 0.95 → 0.95 | 115468 / 185102 = 0.62 → 120084 / 192464 = 0.62 | 112282 / 178830 = 0.63 → 112322 / 178830 = 0.63 |
      | eralert | error 0, Return | 1530738 | 1464106 → 1461636 | 0.96 → 0.95 | 173160 / 256484 = 0.68 → 177776 / 263846 = 0.67 | 169974 / 250212 = 0.68 → 170014 / 250212 = 0.68 |
      | eralert | error 1, Return | 1556012 | 1489468 → 1486998 | 0.96 → 0.96 | 172314 / 255550 = 0.67 → 176930 / 262912 = 0.67 | 169128 / 249278 = 0.68 → 169168 / 249278 = 0.68 |
      | eralert | error 2, Return | 1594880 | 1528056 → 1525586 | 0.96 → 0.96 | 175134 / 258650 = 0.68 → 179750 / 266012 = 0.68 | 171948 / 252378 = 0.68 → 171988 / 252378 = 0.68 |
      | eralert | error 3, Return | 1634806 | 1567482 → 1565012 | 0.96 → 0.96 | 179926 / 263942 = 0.68 → 184542 / 271304 = 0.68 | 176740 / 257670 = 0.69 → 176780 / 257670 = 0.69 |
      | eralert | error 4, Return | 1585004 | 1518176 → 1515706 | 0.96 → 0.96 | 165380 / 248748 = 0.66 → 169996 / 256110 = 0.66 | 162194 / 242476 = 0.67 → 162234 / 242476 = 0.67 |
      | eralert | error 5, Return | 913556 | 857474 → 855004 | 0.94 → 0.94 | 101188 / 168434 = 0.60 → 105804 / 175796 = 0.60 | 98002 / 162162 = 0.60 → 98042 / 162162 = 0.60 |
      | eralert | error 6, Return | 1130486 | 1072444 → 1069974 | 0.95 → 0.95 | 115652 / 185794 = 0.62 → 120268 / 193156 = 0.62 | 112466 / 179522 = 0.63 → 112506 / 179522 = 0.63 |
      | fm_error | code 2, Return | 1296012 | 1235594 → 1233124 | 0.95 → 0.95 | 125696 / 198846 = 0.63 → 130312 / 206208 = 0.63 | 122510 / 192574 = 0.64 → 122550 / 192574 = 0.64 |
      | fm_error | code 4, Return | 1409502 | 1345394 → 1342924 | 0.95 → 0.95 | 145918 / 224326 = 0.65 → 150534 / 231688 = 0.65 | 142732 / 218054 = 0.65 → 142772 / 218054 = 0.65 |
      | fm_error | code 5, Return | 1360112 | 1297768 → 1295298 | 0.95 → 0.95 | 136452 / 212312 = 0.64 → 141068 / 219674 = 0.64 | 133266 / 206040 = 0.65 → 133306 / 206040 = 0.65 |
      | fm_error | code 8, Return | 1367306 | 1305270 → 1302800 | 0.95 → 0.95 | 134052 / 209604 = 0.64 → 138668 / 216966 = 0.64 | 130866 / 203332 = 0.64 → 130906 / 203332 = 0.64 |
      | fm_error | code 15, Return | 1480904 | 1416324 → 1413854 | 0.96 → 0.95 | 149668 / 228548 = 0.65 → 154284 / 235910 = 0.65 | 146482 / 222276 = 0.66 → 146522 / 222276 = 0.66 |
      | fm_error | code 0, Return | 981638 | 925376 → 922906 | 0.94 → 0.94 | 103834 / 171412 = 0.61 → 108450 / 178774 = 0.61 | 100648 / 165140 = 0.61 → 100688 / 165140 = 0.61 |
      | fm_error | code -1, Return | 1049548 | 993170 → 990700 | 0.95 → 0.94 | 109632 / 177326 = 0.62 → 114248 / 184688 = 0.62 | 106446 / 171054 = 0.62 → 106486 / 171054 = 0.62 |
      | fs_input | rows, a scroll, a folder, the close box, Return: the form taken, to its first wait | 63622 | 54388 → 54420 | 0.85 → 0.86 | 18830 / 29536 = 0.64 → 18862 / 29536 = 0.64 | 17406 / 26730 = 0.65 → 17438 / 26730 = 0.65 |
      | fs_input | rows, a scroll, a folder, the close box, Return: a file's row clicked: selected, its name the selection | 327012 | 286854 → 285494 | 0.88 → 0.87 | 85612 / 133262 = 0.64 → 92464 / 141842 = 0.65 | 82782 / 127668 = 0.65 → 82826 / 127668 = 0.65 |
      | fs_input | rows, a scroll, a folder, the close box, Return: another row clicked: the first put down | 372662 | 330190 → 328352 | 0.89 → 0.88 | 92786 / 143026 = 0.65 → 101204 / 153650 = 0.66 | 89956 / 137432 = 0.65 → 90000 / 137432 = 0.65 |
      | fs_input | rows, a scroll, a folder, the close box, Return: the same row clicked again | 269230 | 234028 → 232318 | 0.87 → 0.86 | 78578 / 120476 = 0.65 → 85486 / 129370 = 0.66 | 75748 / 114882 = 0.66 → 75792 / 114882 = 0.66 |
      | fs_input | rows, a scroll, a folder, the close box, Return: the down arrow: the list scrolled a row | 911746 | 864520 → 862682 | 0.95 → 0.95 | 177180 / 245230 = 0.72 → 185598 / 255854 = 0.73 | 174350 / 239636 = 0.73 → 174394 / 239636 = 0.73 |
      | fs_input | rows, a scroll, a folder, the close box, Return: a folder's row clicked: the path made, to its directory's read | 521350 | 477900 → 476022 | 0.92 → 0.91 | 108984 / 162662 = 0.67 → 117362 / 173286 = 0.68 | 107578 / 159874 = 0.67 → 107582 / 159874 = 0.67 |
      | fs_input | rows, a scroll, a folder, the close box, Return: an empty list formatted and drawn | 1489480 | 1465354 → 1465362 | 0.98 → 0.98 | 240634 / 297328 = 0.81 → 240642 / 297328 = 0.81 | one count (no door call) → one count (no door call) |
      | fs_input | rows, a scroll, a folder, the close box, Return: the close box: the path cut, to its directory's read | 387590 | 357808 → 355930 | 0.92 → 0.92 | 81906 / 119576 = 0.68 → 90284 / 130200 = 0.69 | 80500 / 116788 = 0.69 → 80504 / 116788 = 0.69 |
      | fs_input | rows, a scroll, a folder, the close box, Return: Return: to the form's end | 119906 | 108036 → 105494 | 0.90 → 0.88 | 25602 / 39188 = 0.65 → 31436 / 47840 = 0.66 | 24404 / 36766 = 0.66 → 24408 / 36766 = 0.66 |
      | fs_input | a spec typed, a row: the list formatted and drawn | 1490376 | 1465760 → 1465768 | 0.98 → 0.98 | 261844 / 320876 = 0.82 → 261852 / 320876 = 0.82 | one count (no door call) → one count (no door call) |
      | fs_input | a spec typed, a row: the path edited, a row clicked: to its directory's read | 313900 | 282558 → 281158 | 0.90 → 0.90 | 76006 / 112996 = 0.67 → 82818 / 121576 = 0.68 | 74600 / 110208 = 0.68 → 74604 / 110208 = 0.68 |
      | fs_input | a spec typed, a row: the new spec's names read, listed, the row selected | 1871134 | 1819992 → 1820032 | 0.97 → 0.97 | 394272 / 496730 = 0.79 → 394312 / 496730 = 0.79 | 392848 / 493924 = 0.80 → 392888 / 493924 = 0.80 |
      | fs_input | a drag, a page, the title, Cancel: the elevator pressed: the screen taken, to the drag's first wait | 174422 | 149716 → 148338 | 0.86 → 0.85 | 44922 / 73928 = 0.61 → 51756 / 82508 = 0.63 | 41878 / 67970 = 0.62 → 41904 / 67970 = 0.62 |
      | fs_input | a drag, a page, the title, Cancel: the elevator dragged: a move | 134922 | 133944 → 132502 | 0.99 → 0.98 | 15086 / 18460 = 0.82 → 20322 / 25506 = 0.80 | one count (a window) → 15086 / 18460 = 0.82 |
      | fs_input | a drag, a page, the title, Cancel: the elevator let go: the screen given back | 77214 | 74702 → 73384 | 0.97 → 0.95 | 9674 / 13430 = 0.72 → 14788 / 20138 = 0.73 | 8334 / 10694 = 0.78 → 8312 / 10694 = 0.78 |
      | fs_input | a drag, a page, the title, Cancel: the list scrolled to where it was dragged: ten rows | 2128616 | 2098656 → 2098664 | 0.99 → 0.99 | 210726 / 267050 = 0.79 → 210734 / 267050 = 0.79 | 210518 / 266684 = 0.79 → 210526 / 266684 = 0.79 |
      | fs_input | a drag, a page, the title, Cancel: the track clicked: a page scrolled | 2131800 | 2098962 → 2098970 | 0.98 → 0.98 | 213552 / 272938 = 0.78 → 213560 / 272938 = 0.78 | 213344 / 272572 = 0.78 → 213352 / 272572 = 0.78 |
      | fs_input | a drag, a page, the title, Cancel: the title clicked: to its directory's read | 387102 | 359096 → 357218 | 0.93 → 0.92 | 79810 / 115504 = 0.69 → 88188 / 126128 = 0.70 | 78404 / 112716 = 0.70 → 78408 / 112716 = 0.70 |
      | fs_input | a drag, a page, the title, Cancel: Cancel clicked: to the form's end | 165958 | 145796 → 142524 | 0.88 → 0.86 | 36604 / 59274 = 0.62 → 51658 / 78336 = 0.66 | 31322 / 49464 = 0.63 → 31356 / 49464 = 0.63 |
      | fs_input | a root with no drive: the close box: fs_back's scan below the path's buffer, to its directory's read | 438316 | 420016 → 418616 | 0.96 → 0.96 | 146090 / 172346 = 0.85 → 152902 / 180926 = 0.85 | 144684 / 169558 = 0.85 → 144688 / 169558 = 0.85 |
      | fs_input | a spec that fills the title's scratch: a row clicked whose kind is the title's overrun: the path made, to its directory's read | 497182 | 453562 → 452162 | 0.91 → 0.91 | 123212 / 177168 = 0.70 → 130024 / 185748 = 0.70 | 121806 / 174380 = 0.70 → 121810 / 174380 = 0.70 |
  - WHAT THE FLIP NEWLY HOLDS — EVERY BLOCKED DOOR CASE AT DSPTCH. Of the suite's 97 ROM runs that block inside a door
    call (FLIP 2's 97), the 83 that block in ev_multi — gr_watchbox 24, fs_input 22, fm_alert 16, mn_do 11, fm_do 2,
    gr_stilldn 2, gr_wait, gr_rubbox, gr_dragbox, gr_slidebox, fm_button and eralert one each — now run the twin on
    to the dispatcher's hook and are compared with the ROM's memory AT DSPTCH, 112–240 bytes further than the entry's
    image (the waits' EVBs, their lists, the PD): with FLIP 2's twelve, 95 of the 97 are held there, each green; the
    other two are the door's own tests, each naming its own rebound set. (Read off `_watched_through` by FLIP 2's logger. ITS COUNTER OF SHADOWS WAS NOT
    RE-RUN TO A NUMBER: it keeps one descriptor across the zygote's forks and reds 632 door cases by itself —
    "Bad file descriptor" — so the shadows a suite run makes since this flip are unmeasured.)
  - THE FLIP ITSELF, MUTATED (in the tree; the library and the blobs removed and rebuilt, `test/__pycache__` cleared,
    each file restored and `git diff` back to the intended change):
    (a) THE HEADER UN-FLIPPED, the whole `make test` from removed blobs: **4 failed**, all `test_status.py`'s, by
    name — `test_every_door_entry_s_row_says_what_the_build_says_of_its_twin` ("0xfe6998: the build says PENDING,
    its row says REBOUND": the pin this commit adds), `…quotes_its_measured_tier_3_ratios`,
    `…second_count_the_ledger_quotes_is_one_the_table_measured`, `…two_counts_differ_is_quoted_with_both`; 22,723
    passed, 2 skipped (the three served-road cases run again). NO CODE TEST REDS, by design: every other test is
    spelt for both states.
    (b) THE TWIN BROKEN, each mutant through the DOOR batteries (FLIP 2's fourteen files, 2,146 tests; control green)
    and, for the record, the leaf battery alone (365; control green): the buttons-as-they-are arm answering no event —
    door **KILLED** (260 failed), leaf killed (57); the first rectangle's test reading the second — door **KILLED**
    (144), leaf killed (24); a queued key taken and not answered as an event — door **KILLED** (312), leaf killed
    (45). The door's kills carry the shadow's own words at the twin's call ("the twin of 0xfe6998 answered 0x4 where
    the ROM's routine … answers 0x6"). A FOURTH, chosen to be subtle — the buttons as they are stored over the
    answer when BUTTON IS asked (the stale `$c792` rule inverted) — door **SURVIVED**, leaf KILLED (51): in every
    machine a door user makes the two words are equal. THE RULE STANDS for the eighth entry as for the seven: a
    rebound twin is held by its leaf battery; the door cases hold the composition.
  - OBJECTS (the 139 shipped m68k objects against the gate-fix pass's hashes of `a092f2b`'s): 3 changed — `fmdo`,
    `grwait`, `mnlib`, the three that held `evdoor_ev_multi`'s inline `jsr` — 136 identical, `evmulti`'s and
    `evdoor`'s among them; both blobs changed.
  - GATES, from an EMPTY `build/` (the old one moved aside, not removed: the snapshot captured again, the derivation
    cache cold), with every doc of this entry in but this line and the Suite line: `make gates` rc 0 (399 s wall,
    3,047 CPU-s; 1-minute load 122 at its end — not a timing) — **test 22,724 passed / 5 skipped / 4 xfailed, guarded
    the same** (29,268 candidate runs guarded), the ROM build rc 0 (sha256 1d736545…: the same image `a092f2b` builds;
    why the flip leaves it unchanged was not looked into), the table rebuilt byte-identical to the flip's saved one, 0 OVER / 0 DRIFTED. 22,724 =
    phase A's 22,726 less the three cases that skip by derivation, plus the one test added. Then `test_status.py`
    alone on the final ledger: green. The boot snapshot's bytes differ from the one the BEFORE table was made over
    (three captures this night, three hashes: the by-nature bytes `atari/README.md` names) and the table does not.
    Strays: none. New untracked files: none. NOT RUN by this pass: `my-code-review` (the orchestrator's gate).
* **Wave 18 (2026-10-08) — THE INTERRUPT HANDLERS SHIP AS THE ROM'S OWN INSTRUCTIONS; the vertical blank's A6 defect
  fixed by it, and the dispatcher stack's overrun closed on every arm measured (600 of 640) — after a first closure
  that had not measured them all.** One agent, alone in the tree, in three passes: a C fix of the blank (correct, and
  it moved four pinned VBL rows — 0.97 → 0.93, 1.14 → 1.18, 1.23 → 1.20, 1.24 → 1.27: raising an accepted pin is a
  new acceptance, so the project's rule for hand 68000 whose C measures over the bar applied instead); the
  transcription; and the gate's fix pass.
  - WHAT WAS WRONG, and wider than the block this entry removes said: `service_this_vertical_blank` holds its IMAGE
    POINTER in A6 across `swv_vec` and `scr_dump` as well as its queue pointer across each `_vblqueue` slot. A `jsr`
    cannot be told to lose A6 by a clobber (measured again: even an empty `asm` clobbering it makes GCC 16 want a
    frame pointer and die in `print_operand_address`); an OUTPUT operand in A6 does tell it, was measured in the
    first pass, costs over the bar, and is NOT USED. The VDI's cursor routine in slot 0 returns with A6 = `$fd00fe`
    when it redraws: the blank after a mouse move never reached its `rte`. The ROM keeps D7/A0 round each slot ON THE
    STACK and reads everything else through absolute addresses or a re-zeroed A5.
  - WHAT `src/bios/isr.S` IS NOW: the three handlers WHOLE (the HBL always was), and the ROM routines they reach by
    `bsr` / `bra` — Scrdmp `$fc0d50`, the cursor's blink `$fc4666` and the cell inversion `$fc4a1e`, the Dosound
    driver's step `$fc312a`, the keyboard's queue-a-key routine `$fc2c42..$fc2ea0`, and the floppy's VBL service
    `$fc1bc4` as far as its `flock` gate (past it, to the `rts` the gate branches to, a field of `trap #7`: the arm
    is not reconstructed and halts as before). 1,406 bytes of text for 132. BYTES EQUAL TO THE ROM'S BUT FIVE WORDS,
    each the displacement of a `bsr.w` / `bra.w` from one region into another of the same file, held to its exact
    value by the one pin every `.S` here has (`transcription.pinned_region` / `assert_transcribed`, which takes a
    routine of `isr.S` by its `addrs.h` name: `isr.TRANSCRIBED_AS`). NO CALL LEAVES FOR C. `isr.LITERAL_SPANS` (48
    words, four excused) is gone; the HBL is pinned the same way, its `and.w #imm` spelt as the ROM's word.
  - THE QUEUE-A-KEY ROUTINE IS THERE BECAUSE THE FIRST CLOSURE WAS WRONG ON ITS ARM. Timer C's auto-repeat calls
    `$fc2c42`, which the build has as `kbd_queue_key`; the transcription first reached that C through a thunk. The
    stack measurement took eight ticks none of which injects, so "ours needs the ROM's 140" was true of the arms
    measured and said of the handler. THE GATE MEASURED THE INJECTING TICKS: a plain key 154 for the ROM's 140, and
    Alternate + an arrow — a mouse packet, the VDI's mouse interrupt and the AES's glue under the tick — **196 for
    the ROM's 144: 356 + 100 + 196 = 652 of 640, 12 OVER**. `_needs_measured` now takes THE WORST OF EVERY ARM, the
    two injecting ticks among them, each state made by the handlers' own runs (the key's make code through the
    ACIA's handler, the delay and the interval counted down by the ticks); RED on the thunk (the needs 140 /
    196 / 100, 652), GREEN on the ROM's bytes. The routine is 606 bytes, self-contained but for
    `mousevec`; its span carries `midivec`'s jump and the MIDI ring's put (`$fc2e34..$fc2e5c`) as bytes never
    entered, so no branch across them is relocated; its two operands that name the ROM (the key click's Dosound
    list, the Alternate button-key table) stay the ROM's addresses, as the C's are. IT EXISTS TWICE IN A BUILD — the
    C for the ACIA chain, these bytes for the one caller that is an interrupt handler.
  - THE C BODIES ARE KEPT AS TWINS (the orchestrator's ruling), as the HBL's always was beside its transcribed entry:
    `isr_vbl`, `isr_timer_c`, `isr_acia` and the two `service_this_*` functions are what Tier 1 proves and what the C
    rows price, and NO ENTRY CALLS THEM. Their bytes are HEAD's (`vbl.c`, `timerc.c`, `ikbd.c`: comments only; the
    settle count moved to `addrs.h`), so their rows and written entries stand unmoved — and the twin of the blank
    still has the A6 hazard, said at the function. NOT wired into mechanism (T): owed (Next).
  - TIER 3, `make bench` 0 OVER / 0 DRIFTED, 1,903 rows, ONLY ten of the twelve ISR-entry rows moved (two were
    1.00): every one **1.00**, instruction for instruction and cycle for cycle (HBL 0.98 / 0.97; VBL 1.01 pinned,
    1.23, 1.24; timer C 1.33; ACIA 1.71 / 1.52 / 1.12 / 1.18). EIGHT WRITTEN ENTRIES REMOVED from `PERF_ACCEPTED`
    (seven acceptances and the 1.01 pin), none added, none re-quoted: 56 accepted rows for 63. No registered tick
    injects, so no row prices the queue-a-key copy: the transcription relation holds it on both blobs, unregistered.
  - THE INTERRUPTED STACK, measured on both blobs, the worst of every arm: ACIA **140**, Timer C **144**, vertical
    blank **100** — the ROM's own, which is 140 / 144 / 100 too (192 / 188 / 152 under C bodies, on the arms then
    measured). Worst nesting 244: **356 + 244 = 600 of 640, 40 to spare**; 582 on the path a machine runs with our C
    VDI under the trap. `test_our_frames_fit_the_dispatcher_s_stack_under_our_own_handlers` is a plain pass,
    `test_our_own_handlers_need_what_the_rom_s_do_and_leave_what_status_says` pins the three needs equal to the ROM's
    and the 40, and `test_our_vertical_blank_returns_after_the_vdi_redrew_the_cursor` lost its mark: no xfail is
    left. WHAT "EVERY ARM" IS, so that it is not read as more: a mouse packet and a key's make and break through the
    ACIA; ticks divided away, ticks that reach the VDI's, and the two injecting ticks; a blank that redraws the
    cursor. NOT MEASURED: a blank that changes resolution (`swv_vec`) or dumps the screen (`scr_dump` — the ROM's own
    routine prints the screen), a tick whose sound list runs, the Alternate button keys' arm, and anything a
    program installs in a vector. Still the machine's under those entries, as before: KBDVECS' service routines and
    the packet machine, the BIOS's VDI door, the AES's `trap #2` handler.
  - TESTS ADDED: `isr.keeps_nothing` — a staged routine leaving ALL ONES in D0-D7/A0-A6, which only a run of the
    blob can be held to — under the blank's entry at `swv_vec`, a slot and `scr_dump` (a premise test on the ROM,
    the transcription relation on both blobs: `isr.run_transcribed`); the same routine behind the VDI's own in the
    machine's `_vblqueue`, the cursor shown and moved by ROM runs; under timer C's entry the tick that injects a
    plain key, the one that injects Alternate + an arrow, and an `etv_timer` that keeps nothing; the byte pins of
    nine regions, each on both blobs; the floppy's field of traps and its `rts`, on both blobs.
  - MUTATION (private tree, forced rebuild a mutant, the four handler batteries and the dispatcher model), 14 / 14
    KILLED over the two passes. A behaviour-neutral byte in each transcription, killed by the BYTE PIN ALONE: the
    blank's settle count 1999, the blink's `bchg` as `bset`, timer C's `movea.w #0` as `suba.l`, the queue-a-key
    routine's `move.b #0` as `clr.b` and its fine mouse step 2, the ACIA's `lea 0.l` as `.w`, the HBL's `and.w` as
    gas's `andi`. A relocation left un-applied (the ROM's own displacement kept), the blank's and timer C's: refused
    BY NAME ("$fc310e is relocated (timer C's `bsr` to the keyboard's queue-a-key routine) and equals the ROM's").
    A `bsr` to the wrong routine, the mouse packet's two bytes swapped, the floppy's field one trap short: killed.
    ONE TRAP AS A `nop` IN THE SHIPPED BLOB ALONE: killed by the gate test's shipped-blob case and nothing else.
    HEAD's `isr.S` back: 25 failed, the cursor test among them. The thunk's own mutant of the first pass (its two
    slots swapped: killed) died with the thunk. WHAT THE SWEEP SAYS OF THE SETTLE LOOP: its count in the entry is
    held by the byte pin and by nothing else (the absolute-cycle pin of `test_bios_vbl.py` is the C twin's).
  - OBJECTS (139 shipped m68k objects against HEAD's): ONE changed, `src_bios_isr_S.o`; both blobs changed; `glue.S`
    equal. The ROM build links none of it and is byte-identical.
* **Cleanup pass before wave 3 (2026-10-08) — THE ROM-SERVED DOOR ROAD RETIRED; one registrar, one hook-raise
  mechanism, the kit's watched loop.** One agent, alone in the tree. CONTENT-NEUTRAL: every one of the 139 shipped
  objects and both blobs byte-identical to wave 18's, `tier3.txt` identical BUT ITS LEGEND'S ONE LINE (line 10, which
  described a served window: every row, count and verdict line equal; dcf6e6fd…), the ROM build's image unchanged
  (1d736545…).
  - THE SERVED ROAD, GONE: in `aes/evdoor.h` `event_door`, `EVDOOR_SERVED`, the hook's `answer` out-parameter and
    `evdoor_shape_unbuilt` (host-only code and one unused target declaration: no object moved), the heading rewritten
    for a door whose every entry is rebound; in the harness `aes_event._served` (the nested run is the SHADOW's
    alone), the at-the-entry arm of a blocked call's comparison (a sixteen-megabyte copy per door call with it) and
    the parked-QPB rule's; in `bench/tier3.py` the windows' VALUES and their equality (`DoorWindows.windows`,
    `to_a_rebound_entry`, `Measurement.door_windows`, `goes_through_the_door`, the ROM's-forker arm of the fork
    relocation): a call closed at no rebound entry is now REFUSED BY NAME where it was priced as a window.
  - THE GUARDS, AND WHERE EACH LIVES NOW. (1) `test_the_door_s_writes_are_compared` held that the nested run's
    writes were laid into the C's image: nothing is laid any more — the twin makes the writes, and one that does not
    is red at its own call (`vet_the_shadow`: `test_a_twin_that_leaves_other_bytes_than_the_rom_s_routine_is_red_at_its_call`)
    and at its case's differential. (2) `test_an_entry_left_to_a_twin_its_wrapper_does_not_call_halts_by_name` held a
    wrapper left on the nested run while the hook answered ARRIVED: no wrapper can be spelt that way (the reader is
    gone: a compile error); the other direction is kept and has two REDs — a hook that knows no twin of an entry
    refuses it (`test_an_entry_the_hook_knows_no_twin_of_is_refused_and_the_core_halts_by_name`), and an answer that
    is neither ARRIVED nor a refusal halts (`test_a_hook_that_answers_another_word_than_arrived_halts_by_name`, new).
    (3) `test_the_door_rule_refuses_rom_aes_code_run_outside_a_window` held `_held_through_the_os`'s "no AES-span
    cycle of ours outside a window": the assertion is KEPT (nothing is a window: no cycle at all) with a RED that
    needs no served entry (`test_a_row_whose_run_enters_the_aes_s_rom_outside_any_door_call_is_refused_by_name`,
    new: ev_multi's own row over a queued move, the fork relocation off), beside the twin's own
    (`test_a_twin_that_runs_the_aes_s_rom_is_refused_by_name`), the general guard's
    (`OURS_IN_THE_AES_UNDECLARED`), the new refusal's (`test_a_call_closed_at_no_rebound_entry_is_refused_by_name`)
    and the build's (`test_no_jsr_of_the_build_enters_the_aes_s_text_and_the_door_s_users_arrive_at_twins`).
    Two more cases went with the values they pinned: `test_the_door_rule_holds_the_two_sides_windows_equal` (a
    window's cycles: there are none; that both shores make the same calls is held by the frames' equality and
    `vet_every_call_closed`) and `test_a_call_s_kind_is_what_the_watch_saw_not_a_window_that_came_out_empty` (the
    table's line for a served call: no line is printed for one).
  - MUTATION SPOT-CHECK, each rebuilt from nothing and RED BY NAME: tak_flag's twin answering REFUSED where it took
    the lock — "the shadow: the twin of 0xfe4e5a answered 0x0 where the ROM's routine … answers 0x1"; unsync's
    wrapper calling tak_flag's twin — "the shadow: the twin of 0xfe4eb8 left another image than the ROM's routine";
    a `jsr` of our build into the ROM's tak_flag — `make bench` rc 2, "door call 0: an arrival at 0xfe4e5a that is
    no rebound entry's", and the two derived tests on both blobs; the fork relocation off — `make bench` rc 2, "our
    twin of 0xfe6998 ran 1910 cycles of the AES's own ROM".
  - ONE REGISTRAR, AND THE CENSUS: a door user's row (`aes_event.register`) is settled by `settled_where_stored`
    over every word that differs by nature — one kept ROM run a row where there were two — and
    `test_tier3.DOOR_USERS_CENSUS` pins which of them settle more than the mask word (none); ev_multi's own rows are
    a fourth layer of `test_aes_event.BY_NATURE_CENSUS`, held to the independent spelling (its two QPB rows).
  - THE HARNESS: `aes_switch`'s three hand-rolled bench loops (the dispatcher's loop, idle's stops, a foreign
    process) run through `rom_bench.watched` — one budget a run, the armed-PC refusal, each vetted
    (`vet_the_run_just_made`); a hook that raises has ONE mechanism (`address_hook.answered_or_recorded`,
    `raise_what_stops_the_session`, `as_the_case_s_outcome`: the scheduler's binding now gives a raise the outcome
    an `AddressHook`'s gets); `aes_event.one_run_of` / `inside_its_own_pass` / `uda_of` and `aes_evinput.recorder`
    are public and spelt once; test_aes_evmulti's literals named; five comments that named a review or a flip say
    the why. LEFT, with reasons: **Next**. The review's fixes: the two shores' door calls are held equal BY ENTRY AND
    IN ORDER on their own (`DoorWindows.closed_at`: with the windows' equality gone the frames' was its one holder);
    a skip, an xfail and a `pytest.exit` raised in a hook are themselves where the binding closes.
  - SPEED: the interrupt needs' measurement releases Return before it presses it (the snapshot holds Return as the
    repeating key: its make takes the "already repeating" arm — still measured, by a first make — and the repeat then came after a
    wrap, 1,013 ticks) — 53
    ticks, 2.2 s → 0.3 s a measurement, the same three needs (140 / 144 / 100), and the wait is now BOUNDED by
    Kbrate's own two counts. Bare warm `pytest -n auto`, one sample each: 142.9 s / 1,253 CPU-s before, 141.4 s /
    1,240 CPU-s after (the load 2 and 6 at their starts). NOT BUILT: an in-tree counter of shadows a suite run —
    flip 2's script dies in the zygote's forks ("Bad file descriptor"); one that counts in `shadow_of` and reports
    through `derived`'s end-of-session line would survive them, if the number is wanted again.

* **Band 4 wave 3, THE FOUNDATION "F3" (2026-10-08) — A ROW THAT REALLY SWITCHES: one watch at the dispatcher for
  both shores, the foreign window, four pilot rows parked by our own dispatcher and woken, on both blobs.**
  Harness only (`test/`, `bench/`): NO `src/`, `include/`, `atari/` file changed and no object of either blob or
  of the ROM build moved. The wave's measured plan is the orchestrator's (not in the tree).
  - WHAT THE FIRST REAL SWITCH SHOWED (a private probe, before anything was written): every case the host's model
    held — a yield, a key / a press / a delay woken by an interrupt, the lock handed over, and the two in which THE
    SCREEN MANAGER RUNS — already runs end to end on the bench blob through `switch.S` and `evdisp.c` and passes the
    kit's whole second differential, once the harness can lay an interrupt at OUR idle. With another process in the
    run THREE things broke, one of them silently: the rule "no slot names the ROM after our run" (the ROM's own poll
    queues the ROM's kchange inside that process's turn); the guards on AES-ROM cycles of ours (155,862 of them);
    and — the image compare green — a delivery relocated for OUR forker while the ROM's forker takes it (5,112
    cycles of our mchange inside the other process's turn). And FLIP 3's first debt is REAL: a delay's row is red at
    `$8997` without the mask bracket's save word dropped.
  - `test/aes_switching.py` (new) — `Switching`, A WATCH FOR EITHER SHORE: idles numbered where the machine waits
    for an interrupt (the ROM's `AES_ROM_IDLE_LOOP`; ours `aes_chkkbd` reached from `aes_idle`), the row's delivery
    of that ordinal checked and laid there, one idle more than the ROM's run refused by name and one fewer refused
    as the run ends; every process entered followed at switchto's `rte` to the instruction it resumes at; the door
    watch (`DoorWindows(blocks=False)`) the row's own process's — a call that reaches the dispatcher STAYS OPEN and
    closes when its process is resumed; A FOREIGN WINDOW tallied for every run of another process, no door entry a
    stop inside it, no fork queued at either edge, the code slots it stored kept. `register` / `settled` (one kept
    derivation a row: the scheduled run, its watched replay held to it, the drops cut to that replay's ledger) /
    `companion` / `measured_on(blob, row)`.
  - `aes_event.Switches` — a switching row's NINTH FIELD (the deliveries at idles, the ROM's idle count, the row's
    process, its door-call deliveries): neither a dict nor a tuple, read through `switching()` / `at_door_calls()`;
    `delivering` answers the watch for every sweep's replay and Tier 3's originals, `rederived` the noise sweep's.
  - `bench/tier3.py` — THE FOREIGN-WINDOW RULE: the two shores' windows are the same TO THE CYCLE, whole and in the
    AES's text, ours holding no cycle of our build; they are in neither own column, printed under the row, and the
    one thing the general guard lets our run spend in the AES's ROM. `vet_no_slot_names_the_rom` excepts a slot a
    window stored while it holds that code. A sliced session that switches is refused by name.
  - THE PILOTS, `ev_block` (`$fe6874`), `net`, on the shipped blob (its C reaches a transcribed core); the whole
    run on both blobs beside them (bench / shipped, the ROM's cycles first):
    | the row | own (ours / the ROM's) | ratio, with thunks | whole run, bench | shipped |
    |---|---|---|---|---|
    | a key typed ahead, polled by the dispatcher's own idle | 11046 / 17146 | 0.64, 0.68 | 31690 / 26556 | 31690 / 26242 |
    | woken by Return DELIVERED at the first idle | 11046 / 17146 | 0.64, 0.68 | 31690 / 26556 | 31690 / 26242 |
    | a delay run out by its ticks at the first idle (drops `$8996`) | 11088 / 16642 | 0.67, 0.71 | 30166 / 25576 | 30166 / 25264 |
    | the mouse onto the bar wakes the screen manager, which runs and waits; then Return | 13018 / 18972 | 0.69, 0.73 | 831626 / 826684 | 831626 / 826416 |
    The last has ONE FOREIGN WINDOW: 797,112 cycles of the ROM's own code on both shores, 155,862 in the AES's text.
    A row here has one count (no rebound entry is called inside ev_block); THE TWO COUNTS across a switch are
    measured, unregistered: `wind_update(END_UPDATE)` handing the lock over inside unsync's call — 957 / 14628
    against 726 / 12052, own 4974 / 7826 = 0.64, the caller's own 150 / 474 = 0.32 (a door user has no Tier 1
    companion until a door child runs under the model: the wave's slice).
  - TIER 1 of each pilot: `aes_switching.companion` — the C through its own scheduler (`aes_switch.modelled`) held
    to the ROM's scheduled run over the row's settled machine: the idles, the answer at its declared width, and the
    image with nothing left out but the run's own stack; where the screen manager runs, the dispatcher's stack and
    the mask word held to what the ROM's run holds at its disp's last call of switchto (the model's nested run of
    a foreign process ends there). THE HOST DOES NOT SWITCH STACKS: the switch and GCC's frame across it are the
    bench's second differential.
  - WHAT A REAL SWITCH TAKES OF THE DISPATCHER'S STACK, measured on the pilots: the ROM 188 bytes; ours 230 (bench)
    / 240 (shipped), 264 / 274 with mchange under it — inside the build's read bound (356), which the 640 is held
    against: a real switch adds nothing to it (savestate re-tops SP at every dispatch; a foreign dispatch is the
    ROM's).
  - TESTS, +50 (+14 more in the fix pass, below): `test_aes_switching.py` (40: the pilots' premises, both blobs, the table's own cycles; every refusal
    of the watch and of the foreign window made to happen; a door user's call open across the switch),
    `test_aes_switching_registrar.py` (3: the derivation held where no battery that registers a row is imported),
    the four rows' companions and Tier 3 cases in `test_tier3.py` / the three sweeps.
  - MUTATION, strict, private trees. 42 mutants of the machinery (`aes_switching.py` 23, `tier3.py` 15,
    `aes_event.py` 4): **42 KILLED**. The first pass left 5 survivors and 4 ABNORMAL (mutants that broke the
    battery's IMPORT: errors, not failures) — closed by `test_aes_switching_registrar.py`, two REDs of the
    companion, a refusal held to the ROM's own dispatcher, and one condition found redundant and DELETED (the
    hand-back was observed "for the row's process": the last call of switchto is that one). 4 C / target mutants on
    private builds, both blobs rebuilt and held to differ: **4 KILLED** by name on the pilots alone — switchto
    handing back D3 changed and savestate saving no A6 (GCC's frame across the switch: "a callee-saved register
    that was not restored"), idle moving no woken process ("idle 1 …: the dispatcher idles once more than the ROM's
    own run did"), mwait entering the dispatcher still READY.
  - FOUND WHILE BUILDING: the answer width of a row was handed to the kit in BITS where it takes BYTES (my own
    `measured_on`, before it landed): pinned by the companion's "same answer under another high word" case.
  - THE REVIEW'S FIX PASS (same day; no pilot was a false green, two gaps let a FUTURE row past the new rules):
    (1) `aes_switching.measured_on` — the path that holds a row on BOTH blobs — tallied nothing: every delivery
    relocated for our forker passed there in silence. It is `tier3.switching_run_on` now: the two runs one schedule,
    the windows equal to the cycle with no cycle of ours inside, our run in the AES's ROM nowhere else, the drops
    held to our own stores. (2) A row carrying a `Switches` (or plain deliveries) that is neither (V) nor (EV) was
    measured on a path that read neither — tak_flag said to idle three times, priced at 0.59 over a run that idles
    none: a switching row is ALWAYS measured through the dispatcher's watch, and deliveries on any other kind of
    row are refused by name. (3) A DOOR CALL OPEN ACROSS A FOREIGN WINDOW was refused under another routine's name
    ("our twin … ran 155862 cycles of the AES's own ROM"): refused by its own now, where the window would open —
    NOT PRICED YET (the window must come off both shores' `own_inside` and the twin's AES-ROM count: the door
    users' slice); a call open across a SELF-RESUME is priced (ev_keybd round ev_block's twin; wind_update). (4) A
    delivery named at an idle the run never makes was neither laid nor refused: refused where the watch is made.
    (5) A routine of no argument (ev_keybd) and an arm that sets no D0 (`answered=False`) are spelt. (6) "A drop is
    one OUR run stored too" was read off the whole run's ledger, which a foreign window's ROM stores satisfy: held
    to the stores made OUTSIDE the windows (conservative: a byte a window stored and ours only after it is refused,
    never passed). (7) Every sweep's replay of a switching row ends by the watch's `vet_ended`. THE SWITCHING ROWS'
    DROPS ARE A LAYER OF THE ONE CENSUS (`test_aes_event.BY_NATURE_CENSUS`, "the rows that switch": the caller's
    context ×4, the dispatcher's stack ×4, spl7's save word ×1), held to an independent spelling. +14 tests (53 in
    `test_aes_switching.py`), 13 more mutants in private mirrors, 13 KILLED (one survivor closed by a case for the
    unanswered arm). The table byte-identical, no object moved.
  - THE PRICING RULE, PROVISIONAL (the user's to overturn): a FOREIGN WINDOW — another process's run and the
    dispatch that hands the machine back, which is that process's own — is the ROM's code on both shores and in
    NEITHER own column, held equal to the cycle. The reason: while that process's program (ctlmgr) is the ROM's,
    nothing of ours runs in its turn. The consequence, said plainly: after a foreign turn our process is woken by
    the ROM's dispatcher; "through our own dispatcher" is the PARKING in such a row, and both halves only where no
    other process runs.
  - NOT BUILT, each refused by name or said in README: a sliced session that switches; a door call open across a
    foreign window; one derivation taking
    interrupts at door calls AND at idles; the parked QPB's address in a switching row (the menu chain — the screen
    manager's own appl_write waking a message wait — runs end to end on the blob and differs in that one longword);
    a door user under the host's model.

* **Band 4 wave 3, THE SLICES W / M / U (2026-10-08) — THE ROWS THAT SWITCH: 78 more calls blocked, parked by our own
  dispatcher and woken, as one returning run on both shores — the waits (22), ev_multi (42), the door users (14) — and
  the memory-laying hook road RETIRED.** Three parallel slices on the foundation above, disjoint files. Harness, bench
  and tests only: no `src/` or `atari/` file changed, and the one header edit (`include/host_slot.h`) is a comment —
  the slot audit. This entry is the docs pass's: every ratio, count and pair in it is RE-DERIVED from `make bench` on
  the merged tree and from the batteries' own tables; the mutation results are THE AUTHORS' RUNS, read off their sweep
  logs and not run again.
  - THE TABLE: 1,907 rows → 1,985. The 78 are ADDED and nothing else moved (504 lines more; no line of the
    foundation's table changed or removed), `make bench` rc 0, 0 OVER, 0 DRIFTED. All 78 are `net`: 0.61–0.75 on their
    own cycles (0.64–0.83 with their thunks). The highest first count is gr_wait's 0.75 (0.83 with thunks), the lowest
    ap_sendmsg's 0.61. TWO COUNTS: 185 → 223 rows carry both, 40 → 55 apart by more than 0.05; of the 78, 38 carry
    both (the door users' 14, ev_multi 11, ev_timer 4, ev_block 2, ev_button 2, ap_rdwr 2, ev_keybd, ev_mouse,
    ev_mesag) and 15 are apart; the highest second count is gr_stilldn's 1.04 — 354 against 340, the SAME cycles as
    its seven returning rows: a switch moves nothing of the caller's own. FOREIGN WINDOWS: 25 rows of the table have
    one (the pilot's and 24 new: the waits 8, ev_multi 14, the door users 2), 36,414–1,150,402 cycles of the ROM's own
    code a row, equal to the cycle on both shores. In five rows the row's process is the SCREEN MANAGER (its context
    `$a3a4` the one dropped).
  - SLICE W — THE WAITS, 22 rows (`test/aes_evlib.py`'s last part, `evlib.register_woken`, `test_aes_evlib_woken.py`:
    186 tests): ev_block ×7 — a double click; leaving a rectangle; a READ woken by the screen manager's own write
    through the menu chain; a WRITE BY THE SCREEN MANAGER to the desk's full pipe, freed by the desk's read; the MUTEX
    handed over when the screen manager's menu lets go; a key wait while the screen manager queues itself on the lock;
    a key wait in which the screen manager, handed the lock, runs with it — ev_keybd, ev_button ×2, ev_mouse, ev_timer
    ×4 (ITS FIRST ROWS: ⚠️ unpriced → ✅, the section 339 → 340), ev_mesag, ap_rdwr ×2, mwait ×2, unsync ×2. Own
    0.62–0.71. Every code of ev_block is now blocked AND woken. Every blocked arrival of the leaf batteries is either
    taken on through the dispatcher to its return or named in `evlib.NOT_WOKEN` with its reason and held on the ROM's
    own run (ONE OF THOSE WAS WRONGLY NAMED, the screen manager's wait for a rectangle: the fix pass, below). tak_flag gets NO switching row: it never reaches the dispatcher (the census's two entries are RED
    tests). A staged application's woken cases stay Tier 1 and register nothing.
  - W's MACHINERY IN THE REGISTRAR (`test/aes_switching.py`): (1) THE PARKED QPB COMPOSES — the QPB addresses a run
    leaves in freed EVBs are read WHILE THE FRAME IS LIVE (the first stop that sees the address: an idle, or where a
    process is resumed), kept with the row (`Settled.qpbs`), dropped by name at Tier 3, vetted on both shores
    (`vet_our_qpbs`: a blob's parked wait must name the ROM's QPB; the companion holds it to the slot of its own
    entry's role) and never staged; an address no stop saw live is refused by name. (2) `left_by` — THE MACHINE A RUN LEAVES IS MADE BY
    THE WRITE LEDGER: every byte the run or an interrupt stored, at its final value — not "the bytes that differ from
    the snapshot", which over another capture of the boot turned a byte the run had stored with the snapshot's own
    value back into that capture's noise (the lock's row never returned there). (3) A ROW WHOSE PROCESS IS NOT THE
    DESK — the writer's rows are the screen manager's, their foreign window the desk's turn.
  - SLICE M — ev_multi, 42 rows (`aes_evmulti.WAKES`; `test_aes_evmulti.py` 365 → 578 tests): 28 woken BY AN INTERRUPT
    at the dispatcher's first idle (the "in one idle" combinations are one delivery), 13 BY A WRITER through THE MENU
    CHAIN — three idles (the mouse onto a title, onto an item, the press), the screen manager's own appl_write serving
    the parked message wait through the QPB in the twin's own frame, one foreign window of 1,131,220–1,150,402 cycles
    a row — and 1 a ROM finding (a key before the writer writes: 954,308; CORRECTED by the gate's fix pass, below: the
    slice read it as "a key and a message never come in one wake", which holds only for a key in the press's own
    idle). Own 0.65–0.72, 0.68–0.77 with thunks; 11 on two counts, all within 0.05. THE MEMORY-LAYING HOOK ROAD IS RETIRED: `aes_evmulti.woken`, `rom_woken`, the
    `WOKEN*` tables and the tests that stood on the hook are gone, each replaced by a real switch held by the same
    assertion (71 test ids by the author's count: its old → new list is the commit message's). STILL UNREACHED: a
    message AND a rectangle in one wake — through the real chain too the mouse is the writer's while its menu is
    down, and the desk's rectangle waits are not posted in that wake (the two rows that ask for both answer the
    message alone).
  - SLICE U — THE DOOR USERS, 14 rows, each on two counts with its call of a rebound entry OPEN ACROSS THE SWITCH:
    gr_stilldn, gr_watchbox ×2 (the later passes, and BOTH answers after a block: its 0 answer is pinned), gr_wait,
    gr_rubbox, gr_dragbox, gr_slidebox, fm_do ×2, fm_button, wm_update (the foundation's unregistered measurement, to
    the cycle: 0.64 / 0.32), mn_do ×2 and ap_sendmsg. MACHINERY: (1) ONE DERIVATION THAT TAKES INTERRUPTS AT DOOR
    CALLS AND AT IDLES (`aes_switch.scheduled(..., at_calls=)`; a delivery named at a door call the run never makes is
    refused by name). (2) A DOOR CHILD UNDER THE MODEL (`aes_switch.modelled(..., door=DoorUser(...))`): the door's
    binding and the scheduler in one child, the twin held to its shadow AT DSPTCH, then the C scheduler run on — what
    gives a door user its Tier 1 companion. (3) `aes_switch.STORED_BY_NO_C`: a foreign process's nested ROM run is no
    longer laid back over the dispatcher's stack, the Line-F mask word and the SR save words (NARROWED by the fix
    pass, below: the stack and the mask word; the save words are laid back and compared) — the earlier hand-back
    rule was exact only for a row that never dispatches again (measured: mn_do woken twice after the desk's turn, 24
    bytes of the dispatcher's stack, on no fault of the C). (4) THE BATTERY API `aes_event.woken_row` /
    `blocked_then_woken` / `register_woken`: the premise first (with nothing delivered the call BLOCKS), the at-dsptch
    whole-image compare, then the woken run. (5) THE HOST-SLOT AUDIT (`test_aes_event.SLOTS_HELD_WHERE_PARKED`, the
    header's comment): every frame a door user holds while parked, read off the runs; each is ONE frame for every
    process, sound while one C process can be inside the routine — the slots STAY SINGLE-FRAME until band 5; a call
    that returns holding a slot is refused by name.
  - A DOOR CALL OPEN ACROSS A FOREIGN WINDOW IS PRICED (the foundation refused it by name). The window comes off three
    things together, at the call's close, on both shores: the call's own cost (`own_inside`), its glue, and the twin's
    count of AES-ROM cycles (`in_the_rom`). Rows: mn_do with the desk's turn inside its ev_multi (103,504 cycles,
    58,896 in the AES's text) and ap_sendmsg with the desk's read inside its ap_rdwr (619,596 / 342,354). REDs: a
    window left in on any one count is refused by name; a cycle of our build inside such a window is refused at that
    call; a window BETWEEN two door calls comes off no call.
  - THE CENSUS OF WHAT DIFFERS BY NATURE (`test_aes_event.BY_NATURE_CENSUS`, "the rows that switch") names the 82 by
    routine. Read off the table for the 78: the mask word, the caller's saved context and the dispatcher's stack in
    every one; a parked QPB's address in 29 (ev_multi 25, ap_rdwr 2, ev_mesag, ap_sendmsg); the mask bracket's save
    word `$8996` in 23 (ev_multi 19, ev_timer 4).
  - EIGHT ROM BEHAVIOURS FOUND, each on the ROM's own run (`## Not reconstructed`, band 4 wave 3, has them in full):
    (1) the woken list is LAST IN, FIRST OUT and a key THAT ARRIVES IN THE PRESS'S OWN IDLE is that idle's last fork
    — it wakes the desk before the screen manager writes, and the desk answers the key ALONE (the slice's wider
    claim, that no run answers a key and a message together, was FALSE: the fix pass, below); (2) a press brings the ticks
    of its click count (11 here): a 5-tick timer runs out with the press; (3) the menu chain's message is MN_SELECTED
    byte for byte and never sets the control manager's sent mark; (4) ev_mesag's QPB is overwritten by its own Line-F
    return's trap frame before the run ends; (5) the control manager holds the lock through a press in a loop of
    yields — the dispatcher never idles there; (6) a delay behind others of one process runs out one delay an idle;
    (7) mwait_act's "arrived" arm is unreachable in a real run; (8) mn_do over a title left SELECTED and DISABLED, the
    mouse straight off the bar, does not return within 1.49 M instructions — RECORDED, cause not investigated.
  - TESTS: the suite 22,828 → 23,473 (+645). New file `test_aes_evlib_woken.py` (186); `test_aes_evmulti.py` 365 →
    578; `test_aes_switching.py` 53 → 55; `test_aes_switching_registrar.py` 3 → 11 (the QPB's composition and the
    ledger-made machine, held where no registering battery is imported); the rest in the users' batteries,
    `test_aes_event.py` and `test_tier3.py`.
  - MUTATION — THE AUTHORS' RUNS (strict, private trees and builds; counts as their sweep logs stand, not run again by
    this pass). W, C tails (`evlib.c` / `evwait.c` / `evasync.c` / `evdisp.c`, 17): 16 KILLED, 1 SURVIVED and accepted
    equivalent (idle polling the keyboard after it moves the woken: two commuting statements). W, the registrar (the
    QPB's composition 18, the ledger-made machine 3): 19 KILLED — one only after a test was added (a companion that
    vets against any role's slot) — and 2 SURVIVED in the logs with no argument on record (`q2b`, an unseen QPB
    address settled as none where the same address is refused by the line before it; `q16`, a QPB seen at the ROM's
    idle inside a foreign window too). M, `evmulti.c`'s tail (33, host and blob as two runs, the woken cases alone):
    31 KILLED on both, 2 SURVIVED on both — the known pair (mwait's answer or acancel's thrown away singly). U, the
    machinery (`aes_switch.py` 11, `aes_event.py` 10, `tier3.py` 13): 33 KILLED — two of them after a closure (a named
    blob's door calls held equal; a door call's delivery booked as an idle's, first ABNORMAL) — 1 SURVIVED, accepted
    equivalent (a window's glue left in the call's glue). U, C and target (8, host and both blobs as two runs): every
    one KILLED on at least one surface and each survival by nature — switchto handing back a callee-saved register
    changed and savestate saving no A6 are the BLOB's alone (the host does not switch stacks), a host slot given back
    before the wait is the HOST's alone (no object of the blobs moves).
  - UNPINNED / OWED, each by name (`## Not reconstructed`, band 4 wave 3): idle moving ONE woken process a turn (no
    row wakes two processes in one idle: the leaf battery holds it, no blob row does); ev_mesag's sent-mark order in a
    woken run; a bare dsptch yield into another process as a registered row (step T's ap_tplay yields); fm_alert's two
    ends-blocked cases (step S); the blocked cases NO wake reaches (wm_update / fm_own after an unbalanced release,
    ap_sendmsg to the sender's own full pipe); `sr_drops` on INTERRUPTED rows read by memory change, not by the ledger
    (loud, not silent); `aes_event.qpb_addresses_kept` still reading where the run ends (harmless for today's direct
    rows); `refused_where_the_rom_blocks` has no caller left in the users' batteries — six calls in
    `test_aes_event.py`'s own tests and fs_input's two remain (step S, then R).

* **Band 4 wave 3, THE SLICES' REVIEW AND ITS FIX PASS (2026-10-08, gate 12) — two claims pinned by passing tests
  were FALSE, one pricing hole was open, and five more rows switch (87).** The pre-commit review of the three slices
  (three finders, read-only, probes and mutants in private copies) and one fix agent alone in the tree. Harness, bench,
  tests and docs; ONE source edit, host-only (`src/aes/evdisp.c`, `include/aes/evdisp.h`: the model's poll hook, under
  `RECREATE_HOST_DIFFERENTIAL` — both blobs byte-identical, the table's earlier lines unmoved).
  - **FALSE CLAIM 1 — "no real run answers a key and a message in one wake (`$11`)".** True of interrupts delivered AT
    IDLES, which is all the driver could do. The ROM's idle polls the keyboard EVERY time round its loop, with a
    process woken or ready too: Return taken at the poll after the press's forks ran makes the ROM's ev_multi answer
    `$11`, key `$1c0d` (ROM finding 9, `## Not reconstructed`). BUILT: a delivery AT A POLL THAT IS NO IDLE, named by
    the poll's ordinal, on every shore — the derivation (`aes_switch.scheduled(..., at_polls=)`), both shores' watch
    (`aes_switching.Switching`: `Switches.at_polls` / `.polls`), and the host's model (a poll hook, `recreate_poll`,
    asked at every poll of the C's idle; the nested ROM run of a foreign process counts on in the same sequence). A
    poll named that the run never makes, or that is an idle, is refused by name; a run that polls more or fewer
    times than the ROM's is refused as it ends; and A POLL'S DELIVERY IS CHECKED AGAINST THE THREE WORDS IDLE TESTS
    (which process ready, which woken, how many forks queued), so the PLACE in its loop where a dispatcher polls is
    held. THE RETIRED CASE IS BACK AS A ROW: "a writer and a key in one wake: a key and a message", `$11`, its
    companion and both blobs (own 20382 against 29772, one foreign window of 1,142,416 cycles). The LIFO finding
    stands, said where it holds: of the processes woken out of ONE idle's forks.
  - **FALSE CLAIM 2 — `evlib.NOT_WOKEN["evnt_multi by the screen manager for a rectangle"]`.** It IS woken: the entry
    had "tried" a move OUT of a rectangle the process waits to ENTER. Moved to `WAKES` and registered (mwait's third
    row, the row's process the screen manager, no other process's turn). THE CLASS IS HELD BY A SWEEP NOW
    (`evlib.what_wakes`): every kind of interrupt there is — a key, each button event, the ticks, the mouse into and
    out of every rectangle a scenario names, onto the bar — each alone at the dispatcher's first idle, over all 30
    blocked arrivals of the 11 scenarios left, on the ROM's own run: none returns in its caller; and the sweep is
    shown to wake a wait of each kind an interrupt satisfies (so it cannot pass by trying nothing).
  - **THE PRICING HOLE — a second count pinned by nobody on the waits' and ev_multi's rows.** The door users' battery
    pinned the caller's own cycles; the pilots', the waits' and ev_multi's pinned the first count and asked only that
    the second be under the bar — which a second count net of a foreign window TWICE still is. CLOSED THREE WAYS: (1)
    ONE SPELLING of what a battery holds of its rows, called by all four (`aes_switching.vet_the_premise` /
    `vet_on_a_blob` / `vet_the_table_s_price` over `Premise` and `Priced`): the caller's own and the calls it is net
    of are PINNED on every row that has them (39), and the whole run's cycles on both blobs on every row (ev_multi's
    45 had none); (2) THE INVARIANT of a second count, where it is read and call by call
    (`tier3.caller_own_cycles`, `DoorWindows._closed`): what the calls cost is neither negative nor more than the
    run; (3) the named-blob path's accounting of windows has a RED of its own. TWO WINDOWS IN ONE RUN is a registered
    row (mn_do, the desk's turn in two of its waits: each window off the call it lay inside); two in ONE call and two
    BETWEEN the same calls are reached by no run and are held on stand-in counters, said unpinned (`## Not
    reconstructed`). `STORED_BY_NO_C` is NARROWED to what a row needs — the dispatcher's stack and the mask word,
    each with a RED; the SR save words are laid back and compared.
  - **ROBUSTNESS.** A Python exception in the door child's dispatcher hook under the model was printed by ctypes and
    DROPPED — the twin ran on and the child exited 0: it ends the child by name now (and a shadow's vet that raised
    anything but its own refusal is no pass); a door user's modelled run says how many times its process was parked,
    and the host-slot audit refuses a run that read nothing. A PARKED QPB IS HELD TO ITS PLACE on the blob too: at or
    above the stack pointer its process stood parked at (a dead frame's address named the right eight bytes and
    passed), and a wait still queued is read again where its address was seen before. The two "no shadow" places are
    distinct by value. The pilots' table test says "run `make bench`" where the bench's file predates the tree, and
    asks the file for THIS row's line.
  - **CHECKS RESTORED OR MADE TO COUNT.** The switching rows' census asks BOTH ways again — a kind is dropped only
    where the run changes something of it — with ONE named exemption (ev_timer behind three delays × spl7's save
    word: stored with the value the ROM-made machine already holds). `test_status` holds each routine's count of rows
    that switch, the three sentences that count them and the Components cell's two-count figure to the registry
    and the table (a ledger naming one of ev_multi's rows fewer reds). Rows that were another row's run to the cycle
    are priced once: unsync's hand-over (the harness-queued manager stays a Tier 1 case), and ev_timer's "shorter
    than a tick" — replaced by a tick and a half, run out by ONE tick, which holds the division's dropped remainder.
  - **THE FIVE ROWS** (all `net`, both blobs, each with its companion): ev_block "Return polled while the screen
    manager stands woken" 17368 / 26258 = 0.66; ev_multi "a writer and a key in one wake" 20382 / 29772 = 0.68, "a key
    polled while the screen manager stands woken" 24294 / 36578 = 0.66, "a key and the mouse onto the bar in one idle,
    two processes woken" 18694 / 27944 = 0.67; mwait "the screen manager's wait for a rectangle" 10186 / 14252 = 0.71;
    mn_do "the desk's turn again, in the next wait" 170926 / 269486 = 0.63, the caller's own 101158 / 165168 = 0.61,
    two foreign windows (204,310 cycles). MINUS ONE (unsync's duplicate), ONE REPLACED (ev_timer's). The table 1,985
    → 1,990 rows; 0 OVER, 0 DRIFTED; no line of the foundation's table moved.
  - **DUPLICATION TAKEN OUT**: one registrar (`aes_switching.register_row`) under the three `register_woken`s; the
    menu chain and its points in one home (`aes_event`); one builder of the desk's full pipe (`aes_pdpipe`); one
    `blob` fixture (`conftest.py`); the three meanings of "woken" three names (`aes_evasync.woken`, the arrivals of a
    wake; `aes_evlib.woken_counterpart`, a blocked arrival's row; `aes_event.held_through_its_wake`, its Tier 1 run).
    NOT DONE, and why: `tier3.glue_of` at the table's own measurement — the two spellings differ where a caller
    hands the shipped bench to a row that does not ship through a call.
  - MUTATION — THIS PASS'S OWN RUNS (strict: private mirrors, the host library and both blobs removed and rebuilt
    for a C mutant, `__pycache__` cleared, each mutant restored and verified). THE REVIEW'S SURVIVORS FIRST: a
    second count net of a window twice in the call (A2) and at the table (A7) — KILLED by the invariant AND, with
    both invariants taken out, by the waits' pins alone (ev_mesag, ap_rdwr ×2); a second window in a call replacing
    the first (A3) and a second between calls (A6) — KILLED by the stand-in cases; the named blob's accounting
    never asked (A5) — KILLED; with A1 and A4, 9 of 9. THE POLL RULE, 10 (never laid, a poll late, not checked
    against what idle tests, the host laying none, the count not held on a watch, on the host's nested run, by the
    companion, on our own dispatcher, a poll never made, a poll that is an idle): 10 KILLED — eight of them only in
    the battery that imports no registering one (a mutant of the watch fails every battery that registers such a
    row at its IMPORT: an error, no kill). THE QPB'S PLACE 3, THE DOOR CHILD'S GUARD 3, THE TWO SHADOW PLACES 1, THE
    SWEEP 1, `STORED_BY_NO_C`'s mask word 1: 9 KILLED. SURVIVED, 2, both argued (`## Not reconstructed`): the
    author's `q2b` and `q16` re-made. ABNORMAL, 1, said as it is: the screen manager's rectangle put back among
    NOT_WOKEN breaks the import of the battery that registers its row (the module's own partition assert) — the
    sweep's RED stands as a test instead. THE WAITS' SEVENTEEN C MUTANTS, RE-RUN AND RE-READ (`evlib.c`, `evwait.c`,
    `evasync.c`, `evdisp.c`; the waits', the pilots' and ev_multi's batteries; every failure classed BEHAVIOUR or
    CYCLE PIN): 17 KILLED. By behaviour on a row that switches, on a blob: 15, all but the two named below. `t13`, idle polling the keyboard
    after it moves the woken — the slice's accepted equivalent — is KILLED on both blobs by the rows taken at a
    poll (the delivery refused where the manager stands ready instead of woken); on the host it survives by nature.
    `t16`, idle moving one woken process a turn, is KILLED on the host and both blobs by ev_multi's two-processes
    row. HELD ON THE ROWS THAT SWITCH BY CYCLE PINS ALONE, their behaviour killed only by the old leaf batteries:
    `t5` (ev_mesag clearing the sent mark after its read) and `t14` (mwait_act with no arrived arm). `t7` (mwait
    answering the events it read before the dispatcher) is behaviour on the waits' rows and pins alone on
    ev_multi's — the known equivalent there (acancel's answer holds the same bits).
  - TESTS AND GATES: the suite 23,473 → 23,579 (+106): `test_aes_evlib_woken.py` 186 → 227, `test_aes_evmulti.py`
    578 → 600, `test_aes_switching.py` 55 → 67, the registrar's 11 → 22, `test_status.py` 10 → 12, the rest in
    `test_tier3.py` and `test_aes_event.py`; one test renamed (`test_idle_moves_two_processes_woken_at_once_in_the_
    order_they_were_woken` → `…_in_the_woken_list_s_order_last_in_first_out`: what it asserts). `make gates` rc 0
    from an EMPTY build/: test and guarded 23,579 passed / 2 skipped each, the ROM build's sha256 `1d736545…`
    unchanged; `make bench` 0 OVER, 0 DRIFTED. STAGE 1 OF THE HOOK ROAD'S RETIREMENT (the real switches in, the
    memory-laying hook and its 71 tests still there) was run whole in a private copy over this tree's other files:
    23,650 passed / 2 skipped — the retirement is its own commit.

* **Band 4 wave 3, THE STEPS S AND T (2026-10-08) — THE SESSIONS THAT SWITCH AND THE EVENT TAPE: a sliced session
  whose waits block is priced, every session that ended blocked goes on through its wake, and ap_trecd / ap_tplay are
  in C — 21 more rows switch (108), two more routines are verified (342).** Two serial steps on the slices' tree. S is
  harness, bench and tests only (no `src/` or `atari/` file). T adds `src/aes/aptape.c` and `include/aes/aptape.h` and
  two comments in `include/addrs.h`; no existing source moved. This entry is the docs pass's: every ratio, count and
  pair in it is RE-DERIVED from `make bench` on the merged tree (the table byte-identical to step T's own final one)
  and from the batteries' tables; the mutation results are THE AUTHORS' RUNS, read off their sweep logs, not run again.
  - THE TABLE: 1,990 rows → 2,011. The 21 are ADDED and nothing else moved (134 lines more; no earlier line changed or
    removed), `make bench` rc 0, 0 OVER, 0 DRIFTED. All 21 are `net`: 0.64–0.88 on their own cycles (0.68–0.97 with
    their thunks) — fs_input's put-away slice 0.88 (0.97), every other 0.64–0.74 (0.68–0.81). TWO COUNTS: 224 → 241
    rows carry both, 56 → 62 apart by more than 0.05 (59 → 65 unrounded), the caller's own the higher in 105 → 111,
    still nine over 1.00, the highest still gr_stilldn's 1.04. Of the 21, 17 carry both (ap_trecd 6, fs_input 5,
    ap_tplay 4, fm_alert 2) and 6 are apart — ap_trecd's, each LOWER on the second (0.50–0.60). FOREIGN WINDOWS: 29 →
    31 rows of the table have one.
  - **STEP T — `ap_trecd` (`$fe6766`) AND `ap_tplay` (`$fe6610`), `src/aes/aptape.c`** (gemaplib, Alcyon C; their rows
    have the bodies). 14 priced rows, ALL OF WHICH SWITCH — neither routine has an arm that returns without the
    dispatcher: ap_trecd 6 (own 0.65–0.71, the caller's own 0.50–0.60), ap_tplay 8 (own 0.71–0.74; the four with a
    timer record on two counts, the caller's own 0.74–0.75). 26 cases in all (`test/aes_aptape.py`): ten recordings
    MADE BY THE ROM'S OWN ap_trecd with real interrupts at its dispatcher's idles, thirteen playbacks of them over the
    machines they left, three of one labelled argument class. `test_aes_aptape.py`: 164 tests — the premise on the
    ROM's run, the image AT DSPTCH, Tier 1 through the host's scheduler, both blobs with the whole run pinned, the
    table's price on both counts, and two pins on the BUILD'S OWN INSTRUCTIONS for what no run of a bench can see
    (ap_trecd's two mask brackets; the order of ap_tplay's two exchanges).
  - T's ROM BEHAVIOURS, each reproduced and pinned (`## Not reconstructed`, band 4 wave 3, findings 10–16): a count
    of 0 or below records everything; a timer record waits ticks × 100 / scale ms, real time at a scale of 5 alone;
    a scale of 0 is the runtime's divide by zero, which the C refuses by name; a record's number is its low word and
    a number that is none of the four is queued as a code address; ap_trecd's own sleeps are the timer records of a
    recording, Control going down is a key record and Control-backslash in one poll is not; ap_trecd's compare
    against tchange is dead; `$c852` / `$c854` are written and read by nothing.
  - WHAT T CLOSES OF **Next**: THE BARE dsptch YIELD INTO ANOTHER PROCESS AS A REGISTERED ROW — ap_tplay's played move
    onto the menu bar: mchange hands the screen manager the mouse under OUR forker, the third yield enters it (one
    foreign window, 65,624 cycles, 52,100 in the AES's text). It needed NO change of the watch or the tally (the
    author measured it; the brief had predicted one): a window opens at the manager's first instruction after our
    switchto's `rte` as after any wait's. `$fcff0a`'s TRAP-FRAME HALF (FLIP 3's last debt): with the BIOS trap's save
    area in compared RAM a playback differs from the ROM's run in the trap's saved registers alone and in no byte of
    the frame's PC and SR — a playback needs no `TRAP_FRAME_DROP`, and none is made for it.
  - T's TWO EDITS OUTSIDE ITS OWN FILES (`test/aes_event.py`, applied by S): `VDI_ROM_VEX_CURV` joins
    `POLLED_FUNCTIONS` (ap_tplay's exchange of the cursor routine; vex_motv was served already), and justretf is A
    RELOCATED HANDED ROUTINE (`HANDED_ENTRY_SYMBOLS` → `GLUE_CODES`): where appl_tplay returns after a mouse record
    contrl[9..10] holds what its last vex_motv displaced — the ROM's `$fed424` on the ROM's shore, `aes_rom_justretf`
    on a blob — compared exactly, not dropped. The census (`BY_NATURE_CENSUS`) has the two routines; its named
    exemption (a save word stored with the value the ROM-made machine holds) is a SET of five now (ev_timer's one and
    ap_tplay's four rows with a timer record). `test_transcribed`'s "an AES routine with an opcode and no contract"
    is a PLANTED name: every such routine is declared since this step.
  - T, UNPINNED / OWED, by name: A RECORDING WITH ANOTHER PROCESS'S TURN INSIDE IT is RED on a blob (the two records
    made inside the foreign window) — pinned as a refusal, Tier 1 green, registered nowhere; RULING: Tier 1 only for
    now. A scale that makes a wait below −1 tick never wakes (the author's finding: no case). More than 4,095 records
    (the word divide's sign) STOOD HERE AS "unreachable in the buffer's band" — FALSE, corrected by gate 13: a count
    of 0 records until Control-backslash, any free RAM is a buffer, and the ROM's own run of 4,110 packets answers
    `$f00e` and numbers nothing (a Tier 1 row now; ap_trecd's row). D0's high word after ap_trecd: the ROM's is
    pinned (`$00fe` after a record numbered, 0 after none), ours not compared — the answer is a word. The C reads a record byte-wise off the bus where the ROM calls lbcopy into a frame local: ACCEPTED by
    ruling (the same bytes; `transcription.C_CALLERS_OF_TRANSCRIBED_CORES` lists no lbcopy call of ap_tplay's).
  - **STEP S — THE SESSIONS THAT SWITCH.** (1) A SLICE'S MARKS ARE PER PROCESS (`aes_event.Marks`; the foundation's
    fourth prerequisite, refused by name until now): a mark is an arrival of the row's own process — none is taken
    inside a foreign window (an arrival handed to the marks there is refused by name), every total a mark holds is
    NET of the windows closed before it, the windows inside a slice are kept beside it and held the same on both
    shores, and the memory at a mark is compared outside the dispatcher's stack WHOLE (ours until the run ends).
    `aes_event.register_woken_slices(row, slices)`: one session, one settling, one `Registered` under every slice's
    name. (2) `SwitchingRow.budget`: a row's own derivation budget, declared from its measured run. (3) 7 ROWS:
    fm_alert 2 (own 0.64 / 0.64) and fs_input 5 — the slices of "the user waited for at each wait" (0.65, 0.67, 0.88)
    and of "the screen manager's menu holding the screen" (0.66 with ONE FOREIGN WINDOW of 338,080 cycles INSIDE THE
    SLICE AND INSIDE ev_block's OPEN CALL, 0.64). (4) EVERY ENDS-BLOCKED CASE GOES ON: fs_input's 20 sessions cut
    short at a wait are each continued through the wake at Tier 1, GEMDOS replayed from the script of the same user
    never waited for — held, not assumed: the calls made are the script's to the last, the end is that session's —
    and fm_alert's two are rows. `test_aes_fs_input_woken.py` (20 tests) is the priced sessions' battery, with the
    REDs of what makes a slice's marks one process's.
  - S, WHAT IT CLOSES OF THE LAST REVIEW'S FOUR: (1) THE NOT_WOKEN SWEEP TAKES CHAINS (`aes_evlib.EVERY_CHAIN`, 14,
    beside the 12 interrupts taken alone: the menu chain, ticks at four successive idles, each kind of event after
    the mouse went onto the bar or off it, a key / a click / the ticks at the poll between two processes' turns) and
    is HELD TO WAKE EVERY ARRIVAL A REGISTERED WAKE IS KNOWN TO WAKE (it answered nothing for sixteen of them while
    it took one interrupt alone); the five "only another process could" reasons are FACTS READ OFF THE ROM-MADE
    MACHINE (`ONLY_ANOTHER_PROCESS`: who holds the lock, who could read or write the pipe, who is parked), each with
    a RED. (2) `test_status` holds WHICH rows switch, by name, and the prose counts of ev_multi's paragraph — and
    FOUND FOUR OF ev_block's ROW NAMES PARAPHRASED in this ledger (they read as the table does now). (3)
    `aes_event._laid_into` is guarded whole: a delivery that cannot be laid ends the child by name whatever was
    raised. (4) TWO WINDOWS INSIDE ONE DOOR CALL: unreachable, restated with its reason (`## Not reconstructed`).
  - S's ROM BEHAVIOURS (findings 17–18): a press HELD on an item of the dropped menu, where the caller is not the
    message's reader, is waited out by ctlmgr in a loop of yields — the dispatcher never idles again (`aes_evlib.SPINS`,
    a derivation's whole budget); the lock the screen manager's menu holds is given up to no interrupt alone and to
    exactly two chains.
  - THE HOST SLOTS: `AES_FS_INPUT_FRAME` and `AES_FM_ALERT_FRAME` (with fm_do's, the watch's and fm_button's under
    them) are newly audited as HELD ACROSS A WAIT (`test_aes_event.SLOTS_HELD_WHERE_PARKED`): one frame for every
    process, sound while one C process can be inside the routine; band 5 owes each `HOST_PROCESSES` frames.
  - MUTATION — THE AUTHORS' RUNS (strict, private trees and builds; as their sweep logs stand). T: 56 — ap_tplay 31,
    ap_trecd 21, forker's recorder 4 — 56 KILLED; one (the two exchanges swapped) survived until the
    instruction-order test was written; five are killed by cycle pins alone and argued equivalent on every reachable
    machine (the playing flag not cleared at the start; ap_trecd's flag not cleared after the loop, the records
    counted unsigned, the distance not cut to a word, the sleep's first look skipped) — TWO OF THE FIVE WERE NOT
    (gate 13's fix pass, below: the two counts differ past 32,767 bytes, and a third is equivalent only while one
    process plays). S, the harness (marks, the
    registrar, the sweep, the facts: 34): 34 KILLED, one (fm_alert's woken row taking no key at its first wait) only
    after the case asserted that the SECOND wait is the one that blocks. S, C mutants of fslib.c / fmdo.c (9, host
    and both blobs as two runs): every one KILLED on the host, eight on a blob too — the ninth (fs_input returning
    with its host slot held) is the host's alone by nature: the macro is empty on target.
  - TESTS: the suite 23,579 → 23,921 (+342). New: `test_aes_aptape.py` 164, `test_aes_fs_input_woken.py` 20;
    `test_aes_evlib_woken.py` 227 → 306, `test_status.py` 12 → 15, `test_aes_switching.py` 67 → 66 (the refusal of a
    sliced session that switches is gone with the refusal); the rest in `test_aes_fs_input.py` (233), `test_aes_event.py`
    (395), `test_tier3.py` and the snapshot's sweeps, where each new row is several cases.

* **Band 4 wave 3, GATE 13's FIX PASS (2026-10-08) — the review of steps S and T: NO FIDELITY DEFECT in
  `src/aes/aptape.c`; every finding was a hole in what HOLDS it, a false claim, or duplication.** No shipped byte
  moved: every object of both blobs and of the ROM build hashes as before the pass (`aptape.o` among them; the bench
  ELF differs in 24 bytes, the compiler's temporary file names in its symbol table — its binary is the same), and
  `make bench` writes THE SAME TABLE, byte for byte (2,011 rows, 0 OVER, 0 DRIFTED). No row added: the new cases
  are Tier 1 and text.
  - **T — THE EVENT TAPE.** (1) "MORE THAN 4,095 RECORDS IS UNREACHABLE" WAS FALSE, and two mutants argued
    equivalent on it were not: the ROM's own appl_trecord(buffer, 0) over 4,110 mouse packets answers `$f00e` and
    numbers nothing (finding 21) — a Tier 1 row with a declared budget
    (`test_a_recording_past_32767_bytes_is_counted_below_zero_and_numbered_nowhere`; no blob: ten seconds a ROM run).
    (2) THE BRACKET PIN HOLDS THE FLAG AND THE ORDER: every STORE to the recorder's three words lies inside a
    bracket, each bracket in the ROM's order — the flag armed, or cleared, outside its bracket and the count armed
    after the cursor each survived 164 green tests. (3) A timer record's ticks are a LONG: a labelled playback of
    32,768 ticks at a scale of 32,767 (Tier 1). (4) "The playing flag not cleared at the start" is re-worded: no
    ROM-made machine of this harness, DIFFERS WITH A SECOND CALLER (the staged application's stub pushes one
    immediate; ap_tplay takes three arguments) — not "equivalent". (5) THE CENSUS OF THE ROM'S CODE IMMEDIATES had
    ap_tplay's two rows "owed by nobody" beside its C, and `test_aes_irq.SITES_OWED` at 6: the rows name
    `aes/aptape.h` (the census's own key spelling — the test indexed headers by bare file name and would have
    raised), `SITES_OWED` is 4 with the playback's two apart (`HANDED_BY_A_PLAYBACK`), and THE RULE IS A TEST —
    a row is owed by a file exactly when its routine has a C core
    (`test_a_row_is_owed_by_a_file_exactly_when_its_routine_is_c`, the routine read off the ROM's own text). (6) D0's
    high word after ap_trecd: the ROM's pinned on its ten recordings (finding 20), ours not compared, with the
    reason in the row. (7) `aes_aptape.py`: its own `_point` and `A_CLICK` / `OFF_THE_BAR` are `aes.words_long` and
    `aes_evlib`'s; the recorded points are computed from the named points a packet at a time, not typed in hex.
  - **S — THE SESSIONS' HARNESS.** (1) THE SWEEP'S "NONE RETURNED IN THE CALLER" WAS NOT "NONE WAKES IT": two
    NOT_WOKEN scenarios hold the lock in a harness-parked process that a single Return un-parks — an UNPINNED TAIL,
    said so now in the table, the fact (it reads what the holder waits for) and `## Not reconstructed`; every
    answer of the sweep is pinned (`evlib.swept`), a chain never taken counts as no evidence, and the tail is run
    over A ROM-RUN HOLDER (the new scenario `wind_update(BEG), the lock the screen manager's menu holds`: two more
    woken arrivals at Tier 1, 62 → 64; finding 19). (2) `test_status`'s names hold is a LIST with each name's OWN
    ratio and one verified row an address — three green wrong ledgers refused. (3) A woken session's replayed
    GEMDOS is held FRAME FOR FRAME (`Script.frames`), the end-state property is claimed only over the same user's
    own machine (the menu's session differs by the mouse alone: pinned), and the PARTITION is held on both priced
    sessions. (4) `register_woken_slices` ends on the one registrar (`register_row(row, under=)`). (5) THE
    PRESENT-TENSE PROSE COUNTS ARE HELD OR GONE: the rows taken through interrupts were 56, not 55 (and from 0.60,
    not 0.57), now held with the slices' and sessions' counts, the two counts' three further numbers and `THE TABLE
    TODAY`'s two; the "+21" is deleted.
  - MUTATION (strict, a private tree: the .so and both blobs removed and rebuilt, each held to differ). The
    reviewers' survivors, each killed by a BEHAVIOUR or TEXT test now: the records counted unsigned and the
    distance not cut to a word (the long recording); the flag armed before the mask, cleared before the second
    bracket, the count armed after the cursor (the instruction pin); a timer record's ticks cut to a word
    (the labelled playback's companion). Of the harness: the lock's fact not reading what the holder waits for, the
    sweep taking a return in another process for an idle (10 arrivals red), a woken session's frames not compared
    — each KILLED; the three wrong ledgers refused (`test_a_wrong_list_of_the_rows_that_switch_is_refused_each_way`).
    STILL BY CYCLE PINS ALONE, and said so: the playing flag not cleared at the start (above).
  - TESTS: the suite 23,921 → 23,946 (+25): `test_aes_aptape.py` 164 → 168, `test_aes_evlib_woken.py` 306 → 311,
    `test_aes_evwait.py` +7 and `test_aes_evlib.py` +1 (the new scenario's arrivals), `test_status.py` 15 → 20,
    `test_aes_rom_data.py` 10 → 12, `test_aes_fs_input_woken.py` 20 → 21. None retired, none weakened.
  - OUT OF SCOPE, NOTED: `aes_fslib.NAME_ROOM` (the selector's name scratch's span) runs to `AES_SH_SCRATCH` and
    so takes in `gl_mouse_shown` (`$9b6e`) — which is how the menu's session "differs in the name scratch".

* **Band 4 wave 3, STEP R (2026-10-09) — THE RETIREMENT: the nested run and the shadow, the hop checks,
  `refused_where_the_rom_blocks`, the mechanism's name (EV), and the model's tests a registered row now holds —
  AND THE SHADOW'S ANSWER HALF BUILT AGAIN AT NO RUN: THE ANSWERS HANDED BACK.**
  CONTENT-NEUTRAL FOR WHAT SHIPS AND FOR TIER 3: every object of both blobs and of the ROM build hashes as at
  `084c11e` (both `bench.bin`, the shipped configuration's 140 objects, the ROM build's six and `TOS102RC.IMG`);
  the host library alone moved (the hop checks were host-only code). `make bench` rc 0, 0 OVER, 0 DRIFTED, and THE TABLE DIFFERS IN ONE LINE — line 10,
  the legend's `net` paragraph, where "(EV): C that reaches the event layer … is priced the same way" now says what
  the mechanism is: (V), with ARRIVALS, TWO COUNTS and FOREIGN WINDOWS. No row, no number, no verdict moved.
  THE QUESTION ASKED OF EACH CANDIDATE: not "is it old?" but "what does it still hold that nothing else holds?"
  - **THE GUARD MAP — what each retired mechanism held, and where that lives now.**
    - THE SHADOW (`aes_event.nested_run`, `NESTED_RUN_INSNS` / `_MARGIN`, `shadow_of`, `vet_the_shadow`,
      `vet_the_shadow_at_dsptch`, `SHADOWED`, `HELD_AT_THE_DISPATCHER`, `CHILD_SHADOW_REFUSED`, `Entry.answers`):
      COUNTED FIRST — 5,473 nested ROM runs a suite run (5,200 that returned: ct_chgown 1,378, ev_multi 1,370,
      tak_flag 1,137, unsync 1,072, ap_rdwr 160, ev_button 55, post_button 28; 273 that ended at dsptch: ev_multi
      250, ev_block 7, ap_rdwr 6, unsync 6, ev_button 4 — every one of those inside a door child). What it held:
      (a) a twin's ANSWER and IMAGE where it returns → the twin's leaf battery, at the entry (every arm, swept
      alone: `test_tier3.py::test_every_twin_has_a_leaf_battery_s_rows`), and the door case's own compare (the
      answer its caller reads, the whole image at the end, the frame every later call is handed); (b) a twin's
      image AT DSPTCH in a door child that ends there → `interrupted` ending blocked, which compares the WHOLE
      image there, caller and twin (`blocked_then_woken`'s first half: a superset by construction — the shadow
      started from the C's own image at the arrival and never saw the caller); (c) the same under the model, then
      run on → the same first half for the run's first block, the wake's companion and the blob's second
      differential for all that follows, and `switches_where_the_rom_does` for the twin itself at dsptch (228
      calls a suite run at the wave's census); (d) "the nested run touched no hardware / overflowed no ledger / fits its cap" → guards of the
      nested run itself, which is gone; (e) a return that answers no arrival → KEPT, and sharpened: `_returned`
      refuses a return for another entry than the innermost in flight (`CHILD_RETURN_REFUSED`). 
    - **THE ANSWERS HANDED BACK (`aes_event.vet_the_answers_handed_back`; the orchestrator's ruling on this step) —
      the successor of the shadow's ANSWER half, and no run of the ROM is made for it.** The return hook is handed
      the word each twin answered (`recreate_event_door_returned`'s argument, read again); the ROM's own watched
      run — the one every door case already makes for the frames — reads D0 where it comes back from each door
      call (`DoorStops.answers`, `Calls.answers`). Held equal call by call, at the WORD, wherever the entry
      answers one (`ENTRY_FRAMES`' column, back: post_button and unsync answer nothing a caller reads, and are
      compared with nothing), and refused by name: "door call N, entry X: the twin answered A where the ROM's
      routine answers B". ON WHICH ROADS (corrected by the review pass, below — "every road" was wrong): in
      process (`run_event`, and a real-GEMDOS session, `aes_fslib.run_session`), every child `door_child` makes
      and the model's child (`Scheduled.answers`, `Modelled.answered`, `aes_switching.companion`). REDs: the rule
      itself, a twin's answer another word in process, in a child, and under the model.
    - **THE SHADOW'S IMAGE HALF HAS ITS SUCCESSORS TOO (the review pass, below): nothing measured is given up.**
      As first handed in, this step gave up the twin's image at a call's return and at a modelled run's second
      and later dispatches, "the leaf batteries' to hold". The review measured that wrong for the second (mutant
      G4b: 10 door cases red at HEAD, none in the tree). Both are held now, with no run of the ROM. What is left
      of the shadow's precision: a fault at a stop in the middle is named by its 16 KB PAGE, not its byte.
    - THE HOP CHECKS (`evdoor.h`: vector `$2c` → the handler's RAM copy → the call table; host only): held "a case
      that moved the hop halts by name". No case moves it, no other C call of the AES ever checked it (a wrapper
      is a C call of a C twin like any other), and a machine with the hop moved never passes: the ROM's own run
      does not return (`test_a_machine_whose_line_f_hop_is_moved_is_refused_on_the_rom_s_shore`, both hops).
      `AES_LINEF_TABLE` left `test_aes_rom_data`'s census with it: `aes/evdoor.h` names no ROM address.
    - `refused_where_the_rom_blocks`: a five-line name over `interrupted(…, {})` no battery called. Its six
      own-tests keep every assertion, spelt on `interrupted` ending blocked (`_ends_blocked`, the test file's).
      KEPT BY RULING: the at-dsptch whole-image compare itself, and `Blocked` as an outcome.
    - MECHANISM "(EV)" AS A NAME: the table's legend, `bench/tier3.py`'s mechanism block (rewritten: it still
      described the served road's WINDOWS) and its comments, `test_tier3.py`'s (`EV_ROW` → `DOOR_ROW`), README.
    - THE MODEL'S TESTS A REGISTERED ROW HOLDS (`test_aes_evdisp_model.py`): four of its nine cases ARE registered
      rows — the same entry, arguments, settled machine and deliveries, MEASURED and now HELD
      (`test_a_case_a_registered_row_holds_is_that_row_s_call_over_its_machine_through_its_deliveries`): the key,
      the delay, the screen manager's turn (three pilots) and the press (`aes_ev_button, a press waited for,
      blocked; woken by it`). For those the premise is the row's (`aes_switching.vet_the_premise`: the pilots' and
      the waits' batteries) and the C through the host's scheduler is the row's companion
      (`test_tier3.py::test_every_dropped_row_has_a_differential_that_drops_nothing[<row>]`: nothing left out but
      the run's stack, where the case's compare left out the model's drops) — 8 parametrized instances retired.
      The other five cases (the two yields, the delay with an idle passed, the harness-queued lock, the manager
      entered twice) are no row's and stay.
  - **KEPT, each because it still holds something**: `aes_switch.modelled` (Tier 1 of every row that switches),
    `scheduled` (the derivation), `switches_where_the_rom_does` (the bisecting surface), the dispatcher hook's
    default refusal, `blocked_then_woken`'s at-dsptch compare and `Blocked`; `polls_in_c` (always true since FLIP
    3 — but its removal makes `drawing=` dead at 25 call sites in seven batteries: not mechanical);
    `DoorWindows`' name (it holds the foreign windows inside a call; 43 uses); Tier 3's `arrived_at_by_a_twin` /
    `_door_calls_held_by` / `_reaching_the_door` (the refusal's readers, each with a RED);
    `recreate_event_door_returned`'s answer argument (read by the answers handed back). GONE WITH
    THE SHADOW: the `rebound=` an arrival read, `io_seed` on `door_hook` / `event_hook`, `parked_where_blocked`'s
    `rom_stack=`.
  - **MUTATION — 50 WRONG-TWIN MUTANTS (host C: tak_flag 5, unsync 5, ev_block 3, ap_rdwr 4, ev_button 3, ev_rets
    3, ct_chgown / set_mown 4, post_button 3, ev_multi 14, what a wait writes before the dispatcher 6), each on a
    private mirror, the library rebuilt and held to differ, STRICT (found with `-x`, then the tests found run
    again without it: exit 1 and FAILED).** AFTER THE RETIREMENT (this tree): **49 KILLED, 1 SURVIVED** — 34 in
    the door USERS' batteries (the composition: fm_alert, wm_update, apmsg, mn_do, fm_do; nine files, then the
    selector's six), 15 in the event layer's own (leaf) batteries alone; the survivor, ev_multi's zero-timer
    test moved after its message test, is EQUIVALENT (two tests with no effect on one another: the ROM's order
    has no surface) and survives at `084c11e` with the shadow on, every battery run. BEFORE (`084c11e`, the
    shadow on): the same tests kill the same 49 — and there the failures of 32 carry the shadow's words ("the
    twin of 0x… answered … where the ROM's routine …"): the NAMING is what the retirement gives up.
    THE SHADOW ADDED ONE DOOR-LEVEL KILL IN FIFTY: of the 15 mutants the door users' batteries let through with
    the shadow gone, 14 were let through by them BEFORE too, shadow on (users + sessions, 1,758 tests each) — a
    door user reaches an entry only in the states it makes, and the shadow saw the same states (the pilot's rule,
    wave 13). THE ONE: ev_multi answering the SECOND rectangle's event as the FIRST's — mn_do does not read which
    rectangle came. WITH THE ANSWERS HANDED BACK IT IS KILLED AT THE DOOR AGAIN, by name:
    `test_aes_mnlib.py::test_mn_do_ends_in_its_first_pass[the mouse moved off the bar]` — "AES_ROM_MN_DO: door call
    0, entry 0xfe6998: the twin answered 0x4 where the ROM's routine answers 0x8" (and by 16 leaf and companion
    tests beside). The 15 swept again over the door users: TWO are killed there now — that one, and ev_button
    answering no click (`test_aes_fmdo.py::test_a_radio_button_held_down_waits_as_the_rom_s_and_goes_on_when_it_
    rises`: an answer after a WAKE, which the shadow never compared — it survived the door at `084c11e`); 13 stay
    the leaf batteries' alone, as before.
    THE THREE THE REVIEW NAMED (ev_multi's as-they-are arm answering no event, the first rectangle's test
    reading the second, a queued key taken and not answered), over the door users' 1,758 tests: 261 / 146 / 308
    failed at `084c11e` with the shadow on; 194 / 45 / 308 with it gone; **195 / 128 / 308 with the answers handed
    back** (the third not run again: its count never moved). So OF THE 101 CASES OF THE SECOND THAT THE SHADOW
    ALONE FAILED, 83 FAIL AGAIN (18 do not); OF THE 67 OF THE FIRST, 1 (66 do not) — and those 66 and 18 are what
    the image at a return holds now (the review pass, below): the twin's ANSWER there is the ROM's (it took another road to the same word), its IMAGE at
    the return was not, and the routine's end is the ROM's all the same. No test fails with the answers compare that did not fail under the shadow.
  - **TESTS: 51 ids retired, 25 added (net −26; the suite 23,946 → 23,920).** Retired: the model's eight; the
    two hop REDs; 41 of the shadow, its cap and its places. Added: the model's premise (1), the hop on the ROM's
    shore (2 cases), four of the answers handed back (the rule; a twin's answer another word in process, in a
    child, under the model) and 18 of those 41 RE-SPELT WITH THEIR ASSERTIONS KEPT — the two blocked message-wait
    batteries on the door's parked-QPB rule alone (5 + 5), the place an arrival takes and the return that must
    answer the innermost in flight, the nested arrival, the binding's own list, the child's own library's
    rebound set, `interrupted` taking no refused return for the switch it waits for, the entries' answered
    calls, and the lock's argument-class case, which is now a door DIFFERENTIAL ending blocked
    (`test_the_twin_s_answer_is_the_word_its_wrapper_hands_on_and_the_door_user_goes_on_as_the_rom_s`). The eight
    `test_an_entry_s_row_answers_what_its_wrapper_returns` stay: the column has a reader again. The other 23 were
    REDs of the mechanism itself (a made-up nested answer, the one-compare pass, the cap and its margin, the
    statuses) and go with it.
  - **SPEED, content-neutral**: no nested run (5,473 a suite run) and no 16 MB copy of the image at an arrival
    (`aes_event._in_place`: the frame's pointers are read through the image where it lies). Bare warm `pytest -n
    auto`, one sample a side: 164.1 s / 1,442 CPU-s before (load 23 at its start, 69 at its end), 153.0 s /
    1,341 CPU-s after (load 23 at its start, 49 at its end).
  - **A TEST THAT PASSED ONLY IN COMPANY, FOUND AND FIXED — and the standing rule asked again.**
    `test_aes_event.py::test_a_registered_row_keeps_its_declared_budget_for_every_later_derivation` failed when run
    ALONE, at `084c11e` as before the fix: it reads three registries (`INTERRUPTED_ROWS`, `SWITCHING_ROWS`,
    `SLICED_ROWS`) that the batteries' imports fill, and imported none — it now imports what it reads
    (`test_boot_snapshot`: every battery). THEN, because the rule "every test passes alone" had been broken
    unnoticed: of the tests added or modified since `d21b493` in `test_aes_event.py`, `test_aes_switching.py`,
    `test_aes_switching_registrar.py`, `test_tier3.py` and `test_status.py` (117 functions, 1,036 ids) — EACH FILE
    ALONE in a fresh process, no xdist: 376 / 66 / 22 / 3,107 / 20 passed, none failed; and 40 of those ids drawn
    at random (seed 4), EACH ALONE in a process of its own: 40 passed. NO OTHER IMPORT-ORDER DEPENDENCE FOUND.
  - TIMING WITH THE ANSWERS HANDED BACK (it reads D0 at stops the watched runs already make, and parses one line
    more of a child's stderr): bare warm `pytest -n auto`, one sample, 153.0 s / 1,353 CPU-s (load 21 at its start, 67 at its end).
  - **THE REVIEW PASS (one real loss and four small ones; all content-neutral for what ships and the table).**
    - THE IMAGE AT EACH DOOR CALL'S RETURN AND AT EVERY DISPATCH (`aes_event.image_pages`: the 1 MB of RAM as
      4-byte digests of 16 KB pages). At a RETURN it is the third field of the answers handed back — the
      candidate's at the return hook, the ROM's where its watched run comes back from the same call, a stop it
      already makes for D0 ("door call N, entry X: the twin left another image than the ROM's routine where it
      returns — in $lo..$hi"). At a DISPATCH (`vet_the_images_at_the_dispatcher`): the model child's at each
      call of the dispatcher's hook, the ROM's at dsptch's entry each time ITS OWN process reaches it
      (`aes_switch._Idling`, `Scheduled.dispatches`; another process's dispatch is not watched) — "dispatch N:
      the image the C holds at the dispatcher is not the ROM's …", and the count of dispatches held equal.
      WHAT A PAGE LEAVES OUT, both shores alike (`image_pages`; wider than a run's END needs, since a stop in
      the middle cannot ask what the ROM's run stored): the stack band, the Line-F mask word, the keyboard
      poll's trap save and frame, every SR save word, an EVB's parameter WHERE IT HOLDS A STACK ADDRESS (a QPB's
      place — MARKED, see the delta review below), and beside — under the model, the caller's saved context
      and the dispatcher's stack (`left_out_under_the_model`); over real GEMDOS, its three windows. NOT TAKEN: by a case run through its caller's
      Line-F word (its shores are staged apart; its direct sibling takes them), and by a LEAF's modelled run (no
      door child: its hook is the C scheduler itself). `interrupted`'s child ends at its FIRST dispatch (the
      hook refuses, the core halts): "a second block" does not exist there, and its first is the byte compare.
    - WHO HOLDS A CHILD'S DOOR CALLS IS SAID AT EVERY CALL: `door_child(..., door_calls=)` has no default. WATCHED
      — `door_child` makes the ROM's watched run and holds the child's frames, answers and images to it (the
      batteries' refusals in `test_aes_grwait.py` / `test_aes_apmsg.py`, `aes_fslib.child_vdi_calls`; and
      `returns_in_a_child`, every guarded case's precondition) — or a `HeldElsewhere` with its reason:
      `interrupted` (holds them itself, after how the run ended), mn_do's binding RED (ended before any door
      call). (fs_input's two spinning passes and the zygote/timeout tests, first said here, are held since the
      delta review, below.) A child made by `aes_event.refusal`
      directly is a RED of the door's own machinery, not a battery's road.
    - THE CHILD'S REAL EXIT ON A REFUSED RETURN: a real child whose door forgets its arrival in flight ends with
      `CHILD_RETURN_REFUSED` and the hook's words (it was held only under a monkeypatched `refusal`).
    - THE TWO UNPINNED INSTRUCTION COUNTS (1,697; 2,970) are deleted from the comments that quoted them.
      `vet_the_premise` holds the run's END too: the row's process the ready list's head, AES_INDISP clear.
    - MUTATION, HEAD → the step as first handed in → now (private mirrors, forced rebuild, strict reruns). The
      reviewer's 18: G4b (ev_multi parks with $c792 scribbled from its second block on) 10 door cases → 0 → 10,
      each by "dispatch 1: the image the C holds at the dispatcher …"; G4 22 → 1 → 22; G9 66 → 28 → 66; G1 G2 G3
      G6 G7 G8 N1 N2 N3 N5 N11 A1 killed by door cases at all three; G5 N8 N9 survive the door cases at all
      three (HEAD's too); the leaf batteries kill them in the tree, then and now (not run at HEAD). Step R's own 50: 49 killed (37 by door cases, 12
      by leaf / registry), m10 equivalent — as before. NO MUTANT KILLED AT HEAD SURVIVES NOW.
    - TESTS: 5 added (23,920 → 23,925): the page rule and its exclusions, a store undone after the return RED at
      its call, the real child's exit, `door_calls` and its RED, the dispatch images with two REDs (ordinal, count).
    - COST: bare warm `pytest -n auto`, one sample, 158.1 s / 1,379 CPU-s against 153.0 s / 1,353 (load 21 at
      its start, 53 at its end): about +2% CPU for both images together, under the 10% the review allowed.
  - **THE DELTA REVIEW OF THE IMAGE COMPARES (one measured false green, one unpinned list; content-neutral).**
    - A QPB'S PLACE IS MARKED, NOT BLANKED (`aes_event.image_pages`). The exclusion of an EVB's parameter that
      holds a stack address was decided by each shore's own value and left ZEROS: a stack address compared equal
      to 0, either way, and the top byte was masked first. The reviewer's X3 (ev_multi, from its second block on,
      a stack-band address in the last free EVB's parameter across the dispatch) survived 10 of 10 door cases.
      Now the page's digest reads WHERE a place was left out, and only a WHOLE longword in the stack band is one
      (the suite stays green unmasked: both shores store a QPB's address with its top byte clear). REDs: stack
      against 0 both ways, the place in another EVB, an address under a top byte. X3: KILLED, 10 of 10.
    - THE EXCLUSION LISTS ARE PINNED BY NUMBER, each with the byte before and after every span held red through
      the candidate's own page road (`test_what_an_image_at_a_stop_leaves_out_is_these_spans_by_number_…`):
      every page's — the keyboard poll's trap save (one frame under the snapshot's savptr: below), $8994..$899a,
      $cc44..$cc46, $7f100..$8001c — and, under the model,
      `aes_switch.left_out_under_the_model`, now ITS OWN LIST and not `model_drops`' (the end compare's, each
      byte conditioned on what the ROM's run stored): $9c5a..$9c9e the caller's saved context, $899a..$8c1a the
      dispatcher's stack, and no other. The reviewer's H2 (a page more left out) passed 152 harness tests and,
      with G4b, all 10 door cases: KILLED now, alone and with G4b, by that test.
    - BOTH SHORES OR NEITHER: an image at a return on one shore only is refused by name; NO_IMAGE_TAKEN is the
      one way to carry none, and the Line-F road now tells the ROM's watched run so too (it was silently skipped).
    - fs_input's TWO SPINNING PASSES ARE HELD: the ROM's run is watched to the refused pass (`fsl.looping`'s
      `door_calls`), and the child — which the C ends by `abort()` — says each door call as it goes
      (`SAY_EACH_DOOR_CALL`). Frames, answers and return images held on the close-box road (with two REDs); the
      empty-path child is held to making NO door call, as the ROM's run makes none before its first pass.
    - A LATENT ORDER DEPENDENCE OF THE REVIEW PASS, FOUND AND FIXED: `run_guarded`'s guard held its child's door
      calls under the case's budget, and so preempted the differential's own refusal of a stale budget —
      unless an earlier test in the same worker had memoized the guard
      (`test_an_in_process_door_case_s_declared_budget_is_held_from_above_too`, red alone). The guard says its
      holder now (the in-process differential that follows); `returns_in_a_child` called directly is WATCHED.
    - The child-machinery tests are WATCHED (gr_stilldn, gr_rubbox) or name the one test that holds them
      (fs_input over an empty path); `said_in` is the one reader of a child's line.
    - YIELDS AGAINST BLOCKS (`test_a_call_that_would_yield_is_refused_by_its_own_name` went with the nested run):
      held by `test_a_yield_is_not_taken_for_a_block` and `test_a_core_that_switches_is_held_to_the_rom_at_dsptch`
      (unsync handing the lock on: the C halted at the hook as a call that YIELDS, its image the ROM's at dsptch).
    - UNPINNED, recorded: DISPATCH-ORDINAL ALIGNMENT ACROSS A DELIVERY AT A NON-IDLE POLL. No door row has one (0
      of the 22 door rows; the three registered rows with `at_polls` are leaf waits, asked no dispatch image).
    - MUTATION (private mirrors, forced rebuild): X3 10/10 and X1 10/10 by "dispatch 1: the image the C holds at
      the dispatcher …"; H1 10/10; H2 and H2 + G4b by the pin test; G4b 10, G4 22, G9 66 door cases, as at HEAD.
    - TESTS: 3 added (23,925 → 23,928): both-or-neither, the pinned lists (2 cases); the other REDs in place.
  - **A NUMBER A CAPTURE DECIDES WAS PINNED, AND THE GATES FROM AN EMPTY build/ SAID SO.** The pin above first
    spelt the poll's trap save $90c..$93a; over a freshly captured boot snapshot it is $8de..$90c, and every
    import of `aes_event` failed. WHY: the span is ONE TRAP FRAME (46 bytes) UNDER THE SNAPSHOT'S `savptr` ($4a2),
    and the snapshot is taken at vertical blank 900, which interrupts the desktop's idle loop at whatever phase
    it is in (`tools/boot_snapshot.py`, "WHAT IS NOT DETERMINISTIC") — between two keyboard polls (`savptr` at
    the save area's top, $93a, where the ROM's boot leaves it: `move.l #$93a,savptr(a5)` at $fc02f2) or INSIDE
    one BIOS trap (a frame lower, $90c). Same PC, same `_frclock` ($35d) in both logs; ISP $8b7a against $8b5e.
    410 bytes differ between the two captures. NOW PINNED BY WHAT IT IS
    (`test_the_poll_s_trap_save_lies_one_frame_under_the_snapshot_s_savptr_which_a_capture_decides`): the top is
    the ROM's immediate ($93a); `savptr` is that or whole frames below; the span is one frame ending at it; the
    three other spans by number; the model's two — the dispatcher's stack by number, the caller's context by
    its place in the shell's UDA (the same on both captures). Byte-before / byte-after REDs kept for every
    span. HELD OVER BOTH CAPTURES in private copies (2,606 touched tests + `test_status.py` each), then the whole
    suite over the fresh one. One test added (23,928 → 23,929).
    - WORTH KNOWING BEYOND THIS STEP: `savptr` ITSELF differs between captures, and so do bytes OUTSIDE the
      snapshot tool's documented MASK ($4a5; $1461..$1463; $95ba..$95bd; $9707; $9fa1..$9fa4; $a15c..$a19a) —
      its comment says every system variable is bit-identical, measured over three boots that never landed
      inside a trap. Not fixed here (the tool is not this step's). A candidate for the "noise over another
      capture" seen before and for the guarded candidate-run count that varies run to run: any count or address
      read through `savptr`, or a stack depth at the capture, moves with the phase.

* **AES band 5 (2026-10-09)** — the band's waves, one sub-entry each.
  - **WAVE 0 — THE HARNESS: the pre-init machines and the ROM's own boot** (`tools/preinit_snapshot.py`,
    `tools/accessory_disk.py`, `test/aes_boot.py`, `test/acc/`; `recreate/README.md`, "The pre-init machine and the
    ROM's own boot"). No routine ported, no row added. TWO PRE-INIT MACHINES (Hatari stopped at `gem_entry`: RAM,
    registers, palette — `make preinit` with the blank floppy, `make preinit-acc` with the test accessories' in the
    drive from power-on) and THE MACHINES THE ROM BOOTS OUT OF THEM in the oracle, to the desktop's first idle, with
    no poke: `desk_machine()` and `accessory_machine(first, second)`. The oracle serves the floppy at the ROM
    driver's three entries (a device off the machine), the blitter probe's bus error, the shifter by declaration, and
    one horizontal blank; no time passes. TESTS: `test_aes_boot.py`, 117, none pinning a number a capture decides;
    green over three trees' fresh captures, plain / guarded / cold / alone. SWEEP of the harness (private mirror,
    cold, serial): 41 mutants, 39 KILLED, 2 SURVIVED, 0 ABNORMAL (the survivors: below, and the reviewer's N11 —
    D0 forced after the probe's fault — EQUIVALENT: `Blitmode(-1)` discards the probe's answer).
    - WHAT PLAN §0 READ FROM THE CODE, MEASURED (identical over every capture; held by invariants, not addresses):
      THE FIRST ACCESSORY runs in the spare static PD2 (pid 2; its UDA the third static one, 1,474 bytes, below
      64 KB), is NOT in `$c6b2[]`, brings NO EVBs, and its basepage is parked in `$9724`. THE SECOND is the one
      entry of `$c6b2[]` (`$c682` = 1 with two loaded: it counts ALLOCATED accessories), pid 3, in a 2,226-byte
      block GEMDOS allocated ABOVE 64 KB (`$11502`: PD, UDA 1,866 bytes, CDA, FIVE EVBs). THE SUPPLY IS 15 + 5 PER
      ALLOCATED ACCESSORY (`$fda0ce cmp.w #15`, `$fe455c cmp.w #5`): 20 with two. FREE EVBs AT THE FIRST IDLE: 12
      (two quiet accessories: the desk 3, the screen manager 3, one each), 7 (the first finds the second, writes to
      it and waits six ways), 2 (both wait six ways). So RULING U3's "unreachable by counting" is WRONG AS COUNTED —
      it gave every accessory five EVBs, and the first brings none: an APPLICATION in PD0 asking six beside two
      six-way accessories asks 21 against 20. NOT BOOTED: such a machine needs PD0 asking 6 where the desk asks 3
      (corrected where U3 stands, below and in `## Not reconstructed`).
    - `gem_main` RETURNS ON A RESOLUTION CHANGE — BY CODE, NO RUN: deskmain's tail tests `$890a` (`$fe2a40`) and
      answers 0 only when it is set; `$fdbae0` alone sets it (its argument differing from `$8908`); sh_main then
      clears `$98a0` (`$feb224`) and leaves. A run needs the desktop's Set Preferences dialog driven by the mouse.
    - HELD TO THE MACHINE: the desk's machine is the snapshot's own boot (vectors, the TPA but the Line-F mask word
      and the AUTO runner's abandoned stack — derived, noise-proven: the gate's entry (b') below — both PDs and saved
      contexts, the lists, the screen — a test); the accessory machine against a real Hatari boot of its disk
      differs in 109 bytes outside both masks, every one time or interrupt residue (`--cross-check`, opt-in, the
      quiet pair; README has the table). A first version swapped the disk in at `gem_entry` and differed in 821
      (GEMDOS's buffers, records, each basepage's current directory): removed.
    - ROM FACTS MET: TOS 1.02's `Pexec` clears the WHOLE TPA (a RAM disk staged in free memory dies at the loader's
      `Pexec(3)`); `sti` (`$fe38aa`) clears the mask to 0 and the HBL handler is what puts the machine at 3; the
      palette load the AES asks for stays pending in `colorptr` until a vertical blank; PD0's name is eight blanks
      at the first idle (`appl_find("DESKTOP ")` is −1 there); the blitter probe's two callers are `$fc0418` and
      `$fc0ef6`.
    - RULING R3 (each shore booted by its own init), ADOPTED AS WAVE 2's STARTING DESIGN: drops are spans computed
      from each machine's own pointers (`[uda+74, uda+size)`), never a diff; code pointers are MAPPED through the
      relocation registry, not dropped; the desk's frames (ROM code on both shores) are compared SHIFTED by one δ
      per process; pointers into a stack stored outside it follow the same δ, their list read off the ROM-booted
      machine; every dropped span must be NOISE-PROOF (noise in it, the continuation unchanged); frames of our own
      code are vetted by what they DO when resumed (same deliveries, same door calls, same non-stack memory at the
      next park); a `StackReading` per process entry for the margin. The oracle boot is phase-free, so everything
      outside those classes must be equal to the byte.
    - UNPINNED / OWED: (1) the survivor "the next HBL not re-armed where one is taken" — every boot takes exactly
      one (pinned `== 1`), so that half of the model is unpinned by data; (2) `--cross-check` was measured for the
      quiet pair only since the swap was removed (the other mode pairs' images are byte-equal outside the two mode
      words, and all five boots pass the suite); (3) a KIT ACCESSOR for "set the registers / take an exception /
      raise an IRQ at a door stop": `aes_boot.py` reaches `emu._LIB.m68k_set_reg` / `m68k_get_reg` / `m68k_set_irq`
      (accepted for now); (4) `preinit_snapshot.MASK` MAY BE INCOMPLETE — two of its regions were first seen at the
      tenth and twelfth capture of eighteen (no test depends on its completeness); (5) `tools/boot_snapshot.py`'s
      MASK COMMENT IS WRONG that everything outside it is bit-identical: over three fresh captures 32 bytes outside
      it moved — `$1459` +11, `$8920` +14, `$9fa1` +3, `$a075`, `$a098` +4, `$a24a` +2, `$c7e9` — and a fourth
      capture showed `$754e` +2, `$95ba` +4, `$9707`, `$1662` +2 against the desk's machine (tool not edited: the
      snapshot's procedure stays as it is); (6) the full suite and `make bench` were not re-run after the review's
      pass (only `test_aes_boot.py`; no row and no shared file but the Makefile hunk); (7) continuing a booted
      machine from its idle with interrupts is not built (`aes_switch.scheduled` over `machine.pokes`); the
      resolution-change run that makes `gem_main` return is not made.
* **Band 5 wave 1, THE OPCODE SWITCH AND THE COPY ROUND IT (slice S, 2026-10-09; two passes, two independent
  reviews between them — no fidelity error found in the switch or the marshal) — `aes_dispatch` `$fe5d9c` AND
  `aes_marshal` `$fe64e6` IN C (`src/aes/gemsuper.c`, `include/aes/gemsuper.h`): every arm of the table reached
  through the switch and again through the marshal.** (aes_entry `$fe65aa` — which calls the marshal for selector
  200, then dsptch — ships with the trap door: not this slice's.)
  - WHAT THE ROM HAS: ONE Alcyon routine `$fe5d9c..$fe64e5` (1,866 B) — a head (`moveq #1,d6`, the opcode less 10
    compared unsigned with 115), a jump through the table at `$fef834` (116 longwords: 68 arms and the default,
    which 48 gaps share with every opcode outside 10..125), a ladder of `tst.w (sp)+` the arms leave by, `move.w
    d6,d0`. The inventory's 69 "functions" are the arms: labels inside the one body. The marshal (`link a6,#-66`)
    lays addr_in[2], int_out[7], int_in[16] and four words of control one above the other in 62 bytes and copies
    by the counts the program's control states.
  - HOW THE CASES ARE MADE — LIFTED, not written: every routine an arm calls has a battery whose registered rows
    are the ROM's own calls of it over ROM-made machines; a case of the switch is one of those rows turned back
    into the int_in / addr_in a program would hand (`test/aes_gemsuper.py`'s ARMS: the inverse of what each arm's
    instructions read), over the same machine, taken through the same interrupts or deliveries. What the lifted
    call adds is the arm. Where a routine has no second row, the call is made AGAIN over that machine with words
    of its own, or with a top byte on every pointer (`aes.BUS_TAG`).
  - TWO STYLES OF ARM (the switch is the first caller OUTSIDE the event layer of routines that are no door
    entries): a DOOR USER's arm — band 3's C, or ap_rdwr / ev_button / ev_multi through `evdoor_*` — runs with the
    event door bound and every frame it is handed held to the ROM's (`aes_event.run_guarded`); THE EVENT LAYER'S
    OWN (ev_keybd, ev_mouse, ev_mesag, ev_timer, ev_dclick, ap_find, ap_tplay, ap_trecd) are called as they are
    and reach the entries by their cores (`run_layer_case`). The four arms that trap into GEMDOS (rsrc_load,
    rsrc_free, shel_find, fsel_input) run over their batteries' scripted or replayed trap, the C first in a fork.
  - THE JUMP-TABLE LEVER (ruled: accepted). The build's `-fno-jump-tables` keeps absolute addresses out of
    read-only data; as a compare tree an opcode at the tree's bottom pays seven compares for the ROM's one indexed
    jump — appl_init MEASURED 714 cycles to the ROM's 632 (1.13, over the bar). `aes_dispatch` ALONE is built with
    `__attribute__((optimize("jump-tables")))`: on the 68000 GCC's table is sixteen-bit distances from the table,
    IN THE FUNCTION'S OWN TEXT — no absolute address, no relocation, no read-only data — and appl_init is 608 /
    632 = 0.96. GCC documents `optimize` as a debugging aid, "not suitable for production code": what holds it is
    the build's own output, read by TWO GUARDS on every run — the head is one range compare and one `jmp
    %pc@(...)` on both blobs (its RED names the regression and its cost), and no relocation of the function names
    its own text (read off the shipped blob's object; owed again for the `atari/` ROM link's object when
    gemsuper.c joins it). `aes_switch.StackReading` reads the table since wave 3 slice S (`aes_switch.jump_tables`; ruling W2-R5 — no path the
    screen manager's reading reads goes through the switch: `test_aes_stack.py` holds both).
  - ROM BEHAVIOURS PINNED, none mended: graf_mkstate answers -1 (the arm keeps gr_mkstate's D0, its `dbf` counter
    run out); 32 arms answer 1 whatever their routine did (appl_read, appl_write, menu_bar, objc_draw, scrp_read,
    scrp_write, fsel_input, wind_open, wind_close, wind_get, wind_set ...: no `move.w d0,d6`); menu_text's item is
    an UNSIGNED index (`mulu.w #24`: item `$8000` is the object 786,432 bytes ABOVE the tree — labelled class);
    int_out words an arm does not write come back as the supervisor stack held them (the marshal never clears its
    array — labelled class, NOT coverage of the stale values); evnt_multi without MU_TIMER pushes a local the ROM
    never set (`-4(a6)`) — the C hands 0, EQUIVALENT because ev_multi reads the timer under MU_TIMER alone (shown
    on the ROM: the staged local is what ev_multi is handed, and nothing of the run changes); rsrc_gaddr's
    address goes through addr_out BY THE COPIED OPCODE (re-read after the copies); wm_open of a window already
    open, or of the desk's, DOES NOT RETURN on the ROM (met looking for a second handle: no case can be made of
    it).
  - THE COUNTS. Inside the frame an over-long copy is the ROM's own, reproduced word for word: a seventeenth word
    of int_in IS the opcode the switch is called with, a nineteenth the count of int_out, a twentieth addr_in's;
    a third longword of addr_in lands in the answers, a fourteenth is the opcode; addr_in's count is doubled in a
    word (`$8001` copies one longword, `$8000` none). Eleven such cases at Tier 1; the three largest that stay in
    the frame (20 words in, 15 longwords, 27 words out) are ROWS, so both blobs run them — on target the frame is
    a GCC local and a store past it is invisible to the host (a host test reads the C's image back and holds the
    sixteen bytes above the frame untouched on every count).
  - PAST THE FRAME, the three copies are not alike:
    - int_out > 27 words only READS past it — the ROM hands the program its saved A6, its return address, its
      argument, and returns as ever. REPRODUCED (ruled, pass 2): on target the copy back is unbounded; the words
      are each build's own caller's (GCC's frame has the saved A6, the return address, THE IMAGE POINTER and then
      the block's address, where the ROM has the block's address straight after the return address). OFF TARGET
      the frame's host slot runs on by sixteen bytes — A MODEL of a caller's words, staged by the case (labelled
      class), never written by the C — and a count above 35 is refused BY NAME, off target alone. Rows of 28 and
      of 35 words on both blobs (0.81), the differing words dropped by name (the saved A6: the ROM's run is
      entered with the case's registers, ours with the bench's seeds; the argument words), their companion the
      host differential over the model with nothing dropped, and each blob's own words vetted (the seed A6, the
      sentinel, the image pointer 0, the block's address). The return address is COMPARED: on the bench both
      shores return to the same sentinel.
    - int_in > 20 words and addr_in > 15 longwords STORE over the saved A6 and the return address, and the ROM
      then returns through the program's own words (shown on the ROM: 24 words of int_in choose its A6 and the
      address it returns to, in supervisor mode). REFUSED BY NAME on both builds, before the copy (read back from
      the fork: nothing but the copied control has moved — on target a count of 65,535 words would have copied
      128 KB first). A DECLARED DIVERGENCE on target, AWAITING THE USER'S RULING (`## Not reconstructed`).
  - THE WAKES: 31 arms' calls at the switch and 3 at the marshal BLOCK OR YIELD AND ARE WOKEN through our own
    dispatcher — each its routine's own wake lifted (the same deliveries at the same idles: an arm adds no wait,
    held on the ROM's run), appl_exit's three (all_run's bare yield), and appl_tplay made again at half speed.
    The marshal's copies live in GCC's frame across the wait. Held as every row that switches is: the premise on
    the ROM's run, the C at dsptch, Tier 1 through the host's scheduler, both blobs, the table's price on both
    counts. FOUR MORE CALLS ARE HELD AT THE DISPATCHER ALONE (no rows, by nature — a row's run returns): evnt_timer
    and evnt_multi with a time of 65,543 ticks (the HIGH word of the time: its only case), appl_trecord with a
    top byte on its buffer, appl_read of the screen manager's empty pipe.
  - THE GENERAL GUARD — EVERY WORD AN ARM READS TAKES TWO VALUES ACROSS ITS CASES (review's T3): an arm handed one
    value of a word by every case is not held to reading it (`in(7)` replaced by the constant passed). A test
    derives the words from the arm table and holds it for every arm, int_in and addr_in; the words the ROM's arm
    never reads (objc_change's int_in[1], graf_watchbox's int_in[0]) are marked `Unread`, handed stale, and the
    ROM is asked that it reads none. NO word is excused today. NECESSARY, NOT SUFFICIENT: with the guard green
    the sweep still found three words with two values and ONE ANSWER (evnt_dclick's rate — both rows hand 0;
    objc_find's start object — the row from the slider's track finds what the root's search finds; shel_write's
    isgem, a flag — 1 and 3 are one value). Cases added; the sweep is what says a word is read.
  - THE HARNESS, TWO SHARED CHANGES: (1) A HOOK CALLED WHILE NO PASS IS OPEN FAILS ITS TEST AT TEARDOWN
    (`address_hook.OUTSIDE_A_PASS`, an autouse fixture in `conftest.py`; the three tests of the mechanism opt in
    by name). Before, such a call was answered 0 and recorded in a ledger the next `staged()` cleared unread — a
    switch that handed sh_find addr_in[1] for a routine passed. CLOSED IN PASS 3 where the first form saw
    nothing: IN A CHILD (a fork left serving the hook, a fresh interpreter — any process but pytest's own) the
    call ends the process at once, by name and with a status of its own, which every child road's parent reads
    as its case's failure (the sh_find mutant now fails in the guard's fork, "did not return in a child (12)");
    and a record found at a test's SETUP — made at import, at collection, or in a module's or the session's
    fixture — is that test's error, never cleared unread. The whole suite makes no such call but the
    mechanism's own tests. (2) `aes_event.register(..., also_dropped=)`: a door
    user's row's own Tier 3 drops beside the settled words.
  - ONE HOST SLOT FOR THE MARSHAL'S FRAME (ruled: accepted for wave 1) — `HOST_SLOT_AES_MARSHAL_FRAME`, `$7f390`,
    78 bytes (the frame and the model above it), live across every wait an arm makes; sound while the one C
    process inside the marshal is the caller. WAVE 3 (an accessory's trap running our marshal on the host while
    the desk is parked in its own) OWES `host_slot_claim_for` and HOST_PROCESSES frames of room.
  - MUTATION (strict: four private mirrors, forced rebuild, caches cleared, each mutant restored): 751 — every
    index, swap, exchange, dropped store, answer and sense of pass 1, and every `in(k)` made 0 and made 1, each
    refusal moved after its copy, the model's room a word either way — **733 killed, 10 equivalent, 8 unbuilt, 0
    abnormal**. THE EQUIVALENTS, accepted: the answer kept made DONE on sh_read, sh_write, sh_get, sh_put, rs_obfix
    and objc_edit (their routines answer 1 on every path); shel_write's third word at another index, as 0, as 1
    (sh_write never reads `isover`); R_BIPDATA made R_BITBLK in graf_mouse's own lookup (one arm of rs_gaddr's
    get_addr: the data pointer is the BITBLK's first field). UNBUILT: six in/out swaps in helpers with one array in scope, two layouts the static asserts
    refuse. By hand: the refusal at 27 words restored ON TARGET reds six tests on both blobs; a compare-tree
    build reds the table's guard; the sh_find mutant with no door bound reds at teardown.
  - PRICED: 239 rows (215 at the switch, 24 at the marshal), every one `net`; worst 0.96 (appl_init), the marshal's
    0.48–0.86. 93 rows on TWO COUNTS. No row OVER, none DRIFTED; no other routine's line moved (measured against
    the same tree with one build's refusal put back: only the marshal's own lines differ).
  - TESTS: `test_aes_gemsuper.py` 606 (new), `test_address_hook.py` 16 → 20. None retired, none weakened.

  - **WAVE 1, SLICES H AND G — THE LEAVES ROUND gem_main AND THE SHELL: 26 routines, seven of them shipped as the
    ROM's own instructions** (`src/aes/{geminit,shlib,cart,deskmem,deskleaf,trp14}.c`, `gemdosif.c` extended,
    `src/aes/{gemdosif,trp14}.S`; `test/aes_gemdosif.py`, `test/aes_trap_order.py`, twelve batteries, 356 tests;
    their rows above, from `0xfd9ffc` on). geminit's ini_dlongs, all_run and pinit; gemshlib's sh_tographic,
    sh_toalpha, sh_draw and sh_show; the cartridge chain's cart_init and cart_find; the desk's memory (size_theglo,
    desk_alloc, desk_free) and three desk leaves (app_reschange, set_defdrv, the desk's rsrc_free binding);
    gemdosif's dos_gdrv, dos_chdir, dos_sdrv, isdrive and pgmld; the five vector takes; the XBIOS door trp14.
    gem_main, the accessory loader and sh_main — every one of these routines' real callers — are waves 3 and 4:
    each row says what it is run over meanwhile and what it is OWED (the list at this entry's end).
    - WHAT SHIPS AS `.S`, AND THE MEASURED C THAT DECIDED EACH (the user's rule: port to C first; over the bar,
      ship the byte-pinned transcription). THE VECTOR TAKES, `$fe3c62..$fe3cbd`, with `__DOS` `$fe3c3e` in front:
      restore_trap2's C measures 1.42, install_trap2's 1.23, giveerr's and retake's 1.13 (the image pointer's
      floor on two to six instructions, the BIOS's whole Setexc in both columns of the three that trap), takeerr's
      1.04 in the table and some 1.15 on its own cycles (two Setexc dispatches dilute it) — and three of the five
      are ONE body (retake falls into the Setexc tail, giveerr branches into it, takeerr calls it and branches into
      it). pgmld, `$fe39b4..$fe3a0b`: 1.02 on the two arms that reach Mshrink and 1.11 on the arm where Pexec fails
      (80 cycles over the ROM's 716; three registers saved round a trap for a half that arm never runs; two
      re-spellings measured, neither helps) — first handed in "verified, unpriced behind a switch", REFUSED by the
      review's ruling (a row over the bar is shown OVER or shipped as `.S`), and shipped. trp14, `$fee488`: no C
      function's shape at all (it pops its own return address so the trap finds its caller's frame) — `.S` from
      the start, its C twin serving Getrez's frame on the host. Every `.S` row is 1.00; the C twins' rows read
      `transcribed` while that holds.
    - THE UNPRICED, EACH WITH ITS REASON, AND ONE RULE FOR A `.S`-SHIPPED ROUTINE'S C TWIN. dos_gdrv, dos_chdir,
      dos_sdrv: a HOST ARGUMENT (their caller's return site, parked through `$fe3c28`: dos_free's precedent),
      priced inside isdrive's and set_defdrv's rows. THE TWINS: a C twin's row OVER the bar is in the table,
      verdict `transcribed`; one that measures UNDER it would print with a blank verdict and read as C that ships,
      so it is registered verified and unpriced — takeerr's (1.04), pgmld's two arms that reach Mshrink (1.02,
      their cycles pinned by the battery), trp14's (a host argument besides). ALL OF THEM ARE REGISTERED, swept
      with the registry, and listed by name with why in A CENSUS this wave adds —
      `test_tier3.UNPRICED_AT_A_ROM_ENTRY`: every case registered `priced=False` AT A ROM ROUTINE'S OWN ENTRY (nine
      today: the VDI's gemdos_call twin, takeerr's, pgmld's two, trp14's, the three drive entries, and dos_free —
      the precedent, registered by this wave; OWED the same way: dos_sdta, dos_close, dos_cconout), a new one red
      until listed. THE REST of the unpriced cases are held to be what they were said to be: the AES's Line-F
      caller over a routine the table prices by a row of its own, or one of four named Line-A exception-stub cases.
      `test_status.py` demands a row for the same set. README states the twins' rule once.
    - ROM BEHAVIOURS PINNED AS THEY ARE. desk_alloc checks NO answer of its five Mallocs: a refused block is
      kept as NULL — and a refused FIRST block makes the ROM clear 19,094 bytes from address 0 (`trap #1`'s vector
      among them) and never return from its next trap: pinned on the ROM ("did not reach rts"), and the host twin
      HALTS BY NAME there instead of returning with the page zeroed (a fabricated outcome, found by the review).
      sh_tographic goes on over a refused save buffer. takeerr called a second time saves crit_err itself.
      giveerr of a saved longword with bit 31 set installs nothing (Setexc's `bmi`). cart_find looks for the entry
      through the cursor AS IT STANDS AFTER its clear of the DTA (a DTA laid over the cursor walks address 12).
      pgmld's sizes are a longword sum, unrounded and unchecked, and its verdict is the LONG's sign (a basepage at
      `$8000` is a load).
    - THE X FLAG IN THE DISPATCHER'S SAVE WORD, ON THE TWO ROWS THAT DECLARE IT (`aes_switching.THE_X_FLAG_ALONE`,
      `SwitchingRow.x_flag_differs`). WHAT IT IS: dsptch pushes its caller's status register and switchto parks
      the SR it is entered under in `$8994`; bit `$10` of its low byte `$8995` is the X flag the caller's last
      arithmetic left. WHY BY NATURE: Alcyon's in the ROM, GCC's in a rebuilt one — measured on the desk's
      rsrc_free binding where GEMDOS frees the block (GCC's `seq` / `neg` over rs_free's answer precedes the
      yield: `$00` against `$10`), and on desk_free through it. HOW HELD: the row DECLARES it and names it among
      its drops (the table prints "ONE BIT excused" under those two rows and no other); NOTHING is left out of the
      compare — Tier 3 flips that bit in the image our run leaves and compares the byte whole, so N, Z, V and C
      and the system byte `$8994` stay compared; a declaring row whose bytes are equal without the flip is
      REFUSED (a declaration it does not need), as is a wrong C bit beside it and a non-declaring row whose X
      differs — each a RED in `test_aes_deskleaf.py`. THE FIRST CUT WAS TOO WIDE AND WAS NARROWED BY THE DELTA
      REVIEW: it dropped the whole byte `$8995` for EVERY row that switches (ruling R-1 as first given). Measured,
      294 of 298 switching runs hold that byte EQUAL — the drop hid a compared, equal byte on 147 rows, and its
      "held to both ledgers" vet proved nothing (both stores are the same transcribed instructions). The table's
      pre-existing lines are again an exact subsequence of the table before the wave, nothing added under them.
    - THE GEMDOS GLUE'S OWN TEXT, NAMED IN RAM, IS MAPPED — NOT DROPPED (`aes_event.TEXT_SITES`, a third member of
      the relocation registry; ruling R-2). pgmld's `.S` reaches `__DOS` by `bsr`, so the return `__DOS` parks in
      `$8c22` is a site INSIDE pgmld (`$fe39ce` / `$fe39fa` in the ROM, the `.S`'s own labels in a build), the
      recording trap copies it into its ledger at each call, Pexec's frame holds the address of pgmld's zero word
      (`$fe39b4`), and `__DOS` leaves by `jmp (a0)` with the site in A0. All four places are mapped ROM ↔ ours where
      our run ends (`tier3.RomBench._call`: the slots, and the register file for this kind alone) and compared
      exactly, and a ROM site our run leaves in a slot or a register is refused by name first; the recorder's own
      module declares the ledger longwords that can hold one (`declare_text_site_slots`, in `aes_gemdosif.py`).
      MAPPED ONLY FOR A RUN THAT CAN PARK A SITE — the `.S` entry's own, and a declared C caller's on the shipped
      blob (`aes_event.TEXT_SITE_CALLERS`): NONE YET. pgmld has no C caller, so no thunk is generated and
      `aes_pgmld` on the shipped blob is still the weak C twin, which parks the ROM's sites as the data they are
      (only giveerr and retake, which the screen switches call, have thunks of this file's routines). ITS FIRST
      CALLER IS THE ACCESSORY LOADER (wave 3): its pair in `transcription.C_CALLERS_OF_TRANSCRIBED_CORES` — the
      table `test_transcribed.py` holds to the build's call graph and the thunks are generated from — must be
      named in `TEXT_SITE_CALLERS` too (`test_aes_pgmld.py` reds while they disagree). No kit change was needed.
    - CALL ORDER HAS A SURFACE (`test/aes_trap_order.py`; the review's finding T4). Three reorderings of the
      screen switches survived the whole battery — text mode before the save buffer is freed, giveerr before the
      arrow, Malloc before the clip: the calls commute in memory and each door's own ledger holds one door's
      sequence. `TrapOrder` is a bench watch armed where the four trap vectors point (GEMDOS, GEM, the BIOS, the
      XBIOS) — the same addresses on both shores, since both run over one machine: at each arrival the trap, the
      function its frame names (the VDI opcode for `trap #2`) and five witness longwords (the two vectors GEM
      takes, what it saved of each, the mouse's hide count). One ledger across the doors, the ROM's run and our
      build's on each blob, nothing staged, no cycle moved. It also holds the order of a C twin's STORES round its
      trap (retake's vector before its Setexc; takeerr's save before its install). IT IS A SURFACE OF THE TWO BLOBS:
      the host build takes no trap, and its call order is held by nothing (the same C). Its handlers are read BY
      VECTOR (one stub behind two vectors is refused by name). The recorder's third parked
      longword (the hide count, added for one such question) is gone again: a handler's instructions are cycles
      in both columns of every row recorded through it (isdrive's, set_defdrv's, pgmld's, the desk's and the
      switches' rows moved by that and nothing else).
    - HARNESS, BESIDE THOSE. `aes_gemdosif.Recorder`: one recording, scripted trap per vector (GEMDOS's, the
      BIOS's, the XBIOS's) that records each call's function and ITS FRAME'S OWN BYTES — nothing above them,
      which is the caller's — and the sites the glue parked at that call. `SwitchingRow.child_doors`: a row that
      SWITCHES AND TRAPS and makes no door call (desk_free, the desk's rsrc_free binding) binds its scripted
      GEMDOS in the Tier 1 fork and is held at every dispatch as a door user's is (the first cut of this lost
      that hold — a mutant "the yield before the free" survived — and `_door_of` restored it). A case whose
      mutant would ABORT THE SUITE (a halt by name, the host's bus guard) is run FIRST AND IN A CHILD
      (`aes_event.refusal`), so the verdict is a failed test: pgmld past a failed Pexec, cart_find's stale
      cursor, trp14 refusing Getrez, desk_alloc refusing every block; sh_show's walk one object too long is
      taken first over a tree that HAS a third object. `bios_setexc_by_trap` (`bios/bcon.h`) is the one spelling
      of Setexc's two-way glue (three before; the other two files' objects byte-identical after), and
      `gemdos_host_trap_over` the host trap's laying for a frame wider than the GEMDOS words' slot (Pexec's
      sixteen bytes, in a slot of its own). `test_aes_rom_data.py` now reads an entry's KIND off the ROM's text
      (a RETURN_SITE follows a call, CODE follows an unconditional exit).
    - REVIEW AND MUTATION. Two independent reviews found no fidelity defect in the 26 routines and, in the tests
      and the pricing: the unpriced arm above, order with no surface, desk_alloc's fabricated host outcome,
      trp14's register set measured over Getrez alone (now `d2 a2`, the trap's contract), and smaller holes — all
      fixed in the fix pass. Sweeps over private copies, forced rebuild, caches cleared: HOST 147 mutants, 145
      KILLED, 2 SURVIVED (cart_find's re-read of the cursor: EQUIVALENT, nothing stored between the two reads; "the
      buffer freed before the mouse is hidden": its surface is the trap watch on the blobs, where it is killed),
      0 ABNORMAL; TARGET AND MACHINERY 18 of 18 (the three orders, the two twins' store orders, six `.S`
      mutants, the drop widened or not made, a text site left unmapped in A0 or in `$8c22`, the twin mapped too).
    - UNPINNED, AND WHY. (1) cart_init's PRESENT arm: no oracle machine has a cartridge (ruling R-5: the port is
      wave 3's, with the cartridge loader) — its constants are read off the ROM's instructions and the C run alone.
      (2) the cart_init twin's ORDER "cursor stored at the port, THEN read through it": the ROM's is pinned (its
      run stopped at the read); a twin that read the port directly leaves the same image and takes no trap.
      (3) "EVERY registered row that switches has a premise vet, a blob vet and a table pin" is held for THREE
      batteries only (`test_aes_switching_rows_held.py`: this wave's): a static reading ties 29 of 141 rows to
      their three tests — the other batteries key theirs by a scenario, a wake or a session — and the general
      rule needs the vetters to note what they held and the suite to sum it across workers. OWED. (4) the VECTOR
      TAKES INSTALL THE ROM'S OWN HANDLERS on target until wave 3 (`$fe3ea6` into `$88`, `$fe3cbe` to Setexc: four
      immediates of `gemdosif.S`); `test_aes_rom_data.py` reds the day the build has an entry for either while the
      `.S` holds the ROM's operand — then: relocate the operand, declare the `Relocated` in the pin.
    - OWED ON MACHINES THIS WAVE DOES NOT HAVE, with the caller's site. PRE-INIT (`gem_entry` / gem_main):
      size_theglo `$fd9f72`; install_trap2 `$fda074`; ini_dlongs and pinit's three (gem_main's start); takeerr
      `$fda2bc`; sh_tographic's first call `$fda2c0`; and, once the desk has returned, all_run `$fda396`, giveerr
      `$fda39e`, restore_trap2 `$fda3d0`. THE ACCESSORY MACHINE: pgmld from the loader (`$fe433e`), through the
      ROM's real Pexec of a real `.ACC`; pinit from the accessory allocator; cart_init / cart_find from the
      loader's cartridge arm. sh_main (wave 4): desk_alloc `$feb1da` and desk_free `$feb1e8` round the desk (the
      second needs a deskmain that RETURNS), sh_toalpha `$feb178` and sh_tographic round a launched program,
      sh_draw `$feb19c`, sh_find handed sh_show `$feb272` (a by-value site), trp14's Getrez.
    - FOR WAVES 3 AND 4. A C caller of pgmld, of trp14 or of a vector take reaches the `.S` through a generated
      thunk on the shipped blob: add the pair to `transcription.C_CALLERS_OF_TRANSCRIBED_CORES`; pgmld's text sites
      are then mapped for that caller's run without more (the shipped blob's rule). The C twin of trp14 serves ONE
      frame (the function word alone): a C caller pushing more needs the twin widened or its own shape. A routine
      that traps and switches registers with `child_doors=gd.CHILD_DOORS`. A new order question is asked of
      `aes_trap_order.on_both_shores(tier3, bench, row)`, with its own witnesses where the five do not answer it.
      gem_main returning needs gl_rschange set by app_reschange (the Set Preferences dialog: wave 0's note).
  - **WAVE 1, SLICE C — THE SCREEN MANAGER'S FOUR HANDLERS, AT THE ROM'S OWN ARRIVALS** (`src/aes/gemctrl.c`,
    `include/aes/gemctrl.h`; `test/aes_gemctrl.py`, `test/test_aes_gemctrl.py`, 149 tests; their rows above, from
    `0xfe456a` on; `recreate/README.md`, "AN ARRIVAL"). ct_msgup `$fe456a`, hctl_window `$fe45a2`, hctl_button `$fe48ce`
    and hctl_rect `$fe4908` in C — 1,104 bytes of the ROM; ctlmgr `$fe49d2`, their one caller, and ictlmgr stay the
    ROM's (wave 2, flip 4). NAMES: DRI's gemctrl.c has these four bodies under these names (the plan's `(cand)`
    reading of ct_msgup holds: ap_sendmsg, then dsptch while the button is down).
    - THE MACHINE WAS THE HARD PART, AND EVERY CASE IS AN ARRIVAL. A handler runs in the screen manager's process
      when the ROM's ctlmgr is woken. So: (1) A MACHINE THE ROM BOOTED — the desk alone, or with the two test
      accessories, which since this slice can `menu_register` an entry of the desk menu, hide the menu bar when it
      is chosen, and `wind_create` / `wind_open` a window of any kind (GEM's gadget bits) before they sleep: real
      processes the ROM's loader loaded, making real AES calls through `trap #2` (CHOSEN over the desk opening a
      drive window: that needs the floppy's driver under a double click, a device the booted machine's idle has no
      model of; an accessory's window needs nothing but the AES, and its kind is ours to choose — ten machines since the review's pass (three more whose bars carry one gadget each), first seven:
      the desk alone, two windows of every gadget with the first's menu entry, a window without its MOVER, one
      without its SIZER, one with a sizer and the vertical bar alone, one with the horizontal bar alone, and one
      whose accessory hides the bar). A mode is now a LONGWORD of the accessory's text (the window's kind, then the
      flags): still one disk to the machine for every pair (the test, over the new modes too). (2) THE ROM'S OWN
      DISPATCHER RUN FROM THAT MACHINE'S IDLE with real mouse packets through the ROM's interrupt handlers at its
      idles and polls — onto a gadget, a click or a press held, a drag, the menu — STOPPED AT THE HANDLER'S FIRST
      INSTRUCTION (`aes_gemctrl.at(Arrival(...))`: a kept derivation; a chain that never arrives, or arrives with a
      delivery still due, is refused by name). (3) The arguments are the frame ctlmgr pushed, the machine every
      byte of RAM there. ONE ARRIVAL IS THE BOOT'S OWN: the desk's menu_bar posts the screen manager a click and
      the ROM's boot calls hctl_button with it before its first idle (`aes_boot.booted(until=)`). Nothing is poked;
      no argument-class staging was needed.
    - TWO KINDS OF CASE. A handler that RETURNS (a click: the button is up where the screen manager runs): a door
      user's differential and a priced row — 17. One that LEAVES BY THE DISPATCHER — a gadget watched, a window
      dragged or rubber-banded, an elevator dragged, an arrow (it yields even for a click), the menu, the button
      waited up: A ROW THAT SWITCHES, THE SCREEN MANAGER ITS PROCESS — 21 priced and 15 at Tier 1 only (the six
      other words of the arrows' table; the drag stopped by its bound at the right edge and at the top left; three
      windows with one gadget alone on each bar shrunk past the smallest size; the elevator dragged to its track's
      end; the left button let go as the right one goes down; the
      desk's own item with an accessory registered; the menu left by a press held). Its deliveries are numbered
      from the handler's own entry: at an idle (a wait that blocked), at a POLL THAT IS NO IDLE (the button's rise
      while the handler yields — it stays ready, the machine never idles) or AT A DOOR CALL (below). Two rows have
      an ACCESSORY's turn inside: a foreign window that is a real third process's.
    - EVERY ARM OF THE FOUR IS REACHED BY A ROM RUN (the rows say which): no arm is named unreached.
    - ROM BEHAVIOURS FOUND, each pinned, none mended. (1) WM_TOPPED CARRIES FOUR WORDS OF THE STACK — x, y, w, h are
      never set on that path: the same residue at every arrival, where OUR C SENDS ZEROS — A DECLARED DIVERGENCE
      awaiting the user (`## Not reconstructed`, slice C). (2) A SIZER HELD BELOW THE SMALLEST SIZE SPINS: gr_rubwind waits for the mouse to
      leave the CLAMPED corner's pixel, every wait returns at once, the screen manager never sleeps until the
      button rises. (3) A CLICK ON THE SIZER RESIZES the window to the point clicked; one on the title "moves" it
      to where it is. (4) THE ARROWS LET THE SCREEN'S LOCK GO: WM_ARROWED is sent between `wm_update(0)` and
      `wm_update(1)`, again each time its reader has cleared `$97fe`, a yield a turn. (5) MN_SELECTED GOES TO THE
      HIGH WORD OF gl_mnppd'S LONGWORD — 0 for every process id (mn_bar stores the owner's id sign-extended; the
      handler reads the word at `$9730`). (6) WITH NO MENU BAR ctlmgr SPINS: a click on the bar's place and a move
      along it, and hctl_rect is called again and again — it returns at once and the manager's wait is satisfied
      as it is made (ctlmgr's own: wave 2 must reproduce it). (7) A CLICK ON THE DESKTOP NEVER REACHES
      hctl_button (bchange hands it to the desk); its `window <= 0` arm is a click on the bar past the titles.
      (8) mchange hands the screen manager the mouse only while a menu is shown: with none, its rectangle wait is
      satisfied only once a PRESS on the bar has given it the mouse.
    - THE HARNESS, FIVE SHARED CHANGES, each with its test. (1) `aes_boot.booted(until=)`. (2) THE DISPATCHER'S
      OWN DOOR CALLS ARE NOT THE CALLER'S (`aes_switch._Idling`): bchange's post_button, run by the dispatcher's
      forker for a button delivered at a poll while the caller yields by its own dsptch, was counted as the run's
      next door call — which the C's forker hands to no door; with its RED. EIGHTEEN PRE-EXISTING ROWS' DERIVATIONS
      MOVED BY IT (ev_multi 11, ap_tplay 4, the opcode switch 2, ev_block 1: each loses the forker's post_button
      from `Scheduled.calls` / `.answers` — rows that are themselves a door entry, no call open while they sleep);
      harmless (none a door user's, no compare read those lists, no line of the table moved) and held row by row
      (`## Not reconstructed`, slice C). (3) `SwitchingRow.also_dropped` — A ROW'S OWN BY-NATURE BYTES: at a
      real arrival the mouse is shown, so the menu's ct_mouse(0) re-shows it and contrl[3] is the ROM's stack word
      (`ctrl.c`'s MISSING ARGUMENT); dropped by name in three of hctl_rect's rows, left out of the companion's end
      compare and of its images at every stop, each byte required changed by the ROM's run, counted by both
      censuses; and `companion(at_stops_only=)` for the one case where a later VDI call of both builds overwrites
      the word before the run ends. (4) A machine's pokes leave the harness's free window out (a megabyte in one
      run covers the argument frame Tier 3 reads by key, and the blob). (5) The probe that keeps STAGED
      APPLICATIONS out of the registries tells them from an accessory the ROM's loader loaded
      (`test_aes_pdpipe.an_accessory_the_rom_loaded`). And two pairs in `C_CALLERS_OF_TRANSCRIBED_CORES`
      (hctl_window's r_get and r_set: thunks on the shipped blob).
    - WHAT IS HELD LESS FINELY THAN ELSEWHERE, said: a handler whose FIRST switch is its OWN dsptch after door calls
      (an arrow, ct_msgup after its send) has no byte-for-byte compare at that dispatcher — no road stops a door
      user's child at a dispatcher reached outside a door call; the companion's image at every dispatch holds it,
      a page named.
    - HOST SLOTS. hctl_window's rectangle-and-four-words and the elevator's corner: plain slots, read out and
      given back before any wait. THE RECTANGLE A DRAG IS HELD BY, THE TWO WORDS IT ANSWERS INTO and mn_do's TWO
      ANSWERS under hctl_rect are live across waits: A SLOT PER PROCESS each (`host_slot_claim_for`, 72 + 36 + 36
      bytes, in three gaps of the band — COMPACTED: no gap holds nine frames of the ROM's 36 bytes). The audit
      (`SLOTS_HELD_WHERE_PARKED`) now reads, under the screen manager: hctl_window — gr_stilldn's two, gr_watchbox's
      rectangle, gr_dragbox's frame, gr_rubwind's rectangle, gr_slidebox's rectangles (ONE FRAME FOR EVERY PROCESS
      still: wave 2 owes each `host_slot_claim_for` before ctlmgr and the desk can both be C inside them) and its
      own two per process; hctl_rect — mn_do's frame (single: wave 2's) and its own; ct_msgup and hctl_button none.
    - PRICED: 38 rows, C everywhere (no `.S`: nothing measured near the bar), 0.28–0.80 on their own cycles; 28 on
      TWO COUNTS, five apart, none over 0.77 on either; no row OVER, none DRIFTED; the table's 5,013 earlier lines
      all still there in order, one block of the handlers' rows inserted, nothing under any other row.
    - MUTATION (strict: private copies, each library rebuilt from nothing and held different from the unmutated
      one, caches cleared, the source restored and verified). HOST, the battery alone, AFTER THE REVIEW'S PASS — the
      author's 126 mutants and the reviewer's 30 in one sweep: 156 — **149 KILLED, 7 SURVIVED, 0 ABNORMAL, 0
      unbuilt**. HOW IT GOT THERE: the author's first pass killed 109 of 126 — 17 holes, 13 closed by cases added
      for them (a window with a SIZER and no MOVER, and the reverse; the drag stopped by its bound on both sides;
      the hidden bar's click arriving with the mouse on a window; the mouse off the titles but still on the bar;
      the desk's own item with and without an accessory registered; the menu left by a press held); the review's
      sweep then found nine more survivors of its own, six closed in pass 2 (each bit of the two gadget masks —
      three; the left button alone; the count counted down, not cleared; the slider's whole thousand). THE SEVEN
      THAT REMAIN are `## Not reconstructed`'s list for this slice, each with its reason and what was tried: one
      EQUIVALENT (`<=` at the elevator's corner, shown on the ROM) and six UNPINNED BY DATA (w_bldactive's call;
      gl_mnppd's low word; the no-bound 10000; do_chg's check-disabled argument; the button read before the send;
      the two cell minima). ON THE BLOBS (both rebuilt per mutant, the handlers' rows of `test_tier3.py` alone):
      the author's 12 of 12, before the review's pass and AGAIN after it, over the final tree — killed
      by the second differential's image or, first, by a pinned cycle count; a state held only ACROSS a yield is the pin's alone there (`## Not reconstructed`).
    - THE REVIEW'S PASS (two independent reviews, which reported no fidelity defect in the four routines). CORRECTED: WM_TOPPED's four words were described as "any value is as faithful" — measured,
      they are one residue at every arrival: now a DECLARED DIVERGENCE awaiting the user; "no pre-existing row's
      derivation moved" was FALSE (eighteen lost the forker's post_button from their door-call lists: said, and
      held row by row). ADDED: the six pins above; a RED for each of the three new refusals (a boot that never
      arrives at `until`, a chain that idles first, an arrival with a delivery still due) and for
      `companion(at_stops_only=)` where a row passes without it; "each of the four rows NEEDS its stale-count
      drop" in place of a test that restated how the row is built; every machine's pokes held to be its boot's
      own RAM; the one-disk test reading its modes off the batteries' machines. A ROM BEHAVIOUR MORE, found by the
      count's pin: two menu_bar calls count two clicks, the screen manager is woken once and takes one — the count
      stays 1 and the next real click on a window is swallowed.
    - THE GATE THAT FAILED, AND ITS GUARD (the third pass). From an EMPTY `build/`, `make gates` died in
      `shipped-glue`: the battery registers its rows from machines the ROM booted, so THE REGISTRY'S IMPORT READS
      THE TWO PRE-INIT CAPTURES, and only `test guarded gates` had them as prerequisites — after their recipe
      rule's, whose first leaf imports the registry. No run in a built tree can see that. MENDED in the Makefile
      (`REGISTRY_READS`: the snapshot and both pre-init machines, a prerequisite of the three rules whose recipe
      imports the registry — `shipped-glue`, `derived`, the table) and HELD (`test/test_makefile.py`: every recipe
      that runs a Python script or pytest has the three captures among its prerequisites, but the four tools that
      make them, which import no test module; RED for each rule as it stood). AT IMPORT, STILL: the seven
      machines the REGISTERED rows arrive on are booted and their 38 arrivals made (a row's name, arguments and
      pokes are its arrival's — registration, the tree's pattern); the three machines only Tier-1 cases use are no
      longer booted there (`aes_gemctrl.gadget_arrival_later`). `import test_boot_snapshot` with nothing kept:
      36.9 s at HEAD `497a635`, 43.4 s now (+6.5 s, once a tree: `make derived` keeps it); kept, 4.0 s against 4.4 s.
    - OVER FRESH CAPTURES: the battery, its rows on both blobs and the table's pins hold over two more sets of the
      three captures, each made from nothing in a private copy — and over two more after the review's pass (a pre-init capture's
      clocks move; no cycle of a row does; WM_TOPPED's residue is one at every arrival on each). A PD's address is the layout's, not a capture's — a premise names processes.
    - FOR WAVE 2 (ctlmgr in C). The four are called with the screen's lock held (ctlmgr's `wm_update(1)`); an
      arrow gives it up and takes it back. ctlmgr's loop must keep THE SPIN with no menu (behaviour 6) and its
      `$c84e` counts. Every slot the handlers' callees hold across a wait is single-frame (the audit's list). A
      handler's rows are entered on the harness's stack from an arrival made by the ROM's ctlmgr: once ctlmgr is
      ours the same arrivals are its door calls' — the chains (`aes_gemctrl`) carry over, the `Arrival` stops move
      to our entries. The accessory's modes are there for the loader's wave too (a third process that owns a
      window, a menu entry, the mouse).
  - **BAND 5 WAVE 2 — GROUNDWORK FOR FLIP 4 (nothing bound)** (2026-10-09/10; three slices in one tree, each reviewed
    independently and fixed; the design and its rulings W2-R1..R6: `scratchpad/b5/W2/design.md`). FLIP 4 — the screen
    manager in C — DID NOT LAND IN THIS WAVE, by ruling W2-R3: the flip does not land over an unproven stack, and
    slice A's reading says our build's screen manager does not yet fit its 1,196 bytes. What the wave leaves is
    everything the flip stands on, with NO ROUTINE BOUND, NO ROW ADDED AND NO TABLE LINE MOVED (the table is
    byte-identical to `daa2aef`'s): A — the stack's reading and its verdict; B — the machine whose screen manager is
    ours; C — the twins themselves, pending. Three sub-entries, in that order.
  - **WAVE 2, SLICE A — THE SCREEN MANAGER'S STACK, READ AND MEASURED: IT DID NOT FIT (it does since THE FRAME DIET,
    this wave's fourth sub-entry)** (`test/aes_stack.py`,
    `test/test_aes_stack.py`; the reading's successor in `test/aes_switch.py`; `recreate/README.md`). THE WHOLE
    ACCOUNTING IS UNDER `## Not reconstructed`, KNOWN THIN MARGINS, "THE SHIPPED BLOB'S SCREEN MANAGER FITS ITS STACK" —
    every number there a pinned finding. AS SLICE A FOUND IT, in one line: read off both blobs from `aes_rom_ctlmgr`, our own
    deepest chain is 908 bytes and fits with the interrupts' nest (252: a horizontal blank is in it since this
    wave's review) with 36 to spare; the deepest `trap #2` chain (the icon's) with the worst VDI call's need (the ROM's handlers' + 32, as
    it was then measured) and the nest is 1,480 / 1,490 — OVER BY 284 / 294; measured from the real entry on a takeover machine, a plain menu drop is
    over by 8 / 12 with the worst nest. A property of code committed at `daa2aef` and earlier, not of the pending
    twins (ctlmgr's own frame is the ROM's 24 bytes). THE FIX WAS THE FRAME DIET (below).
  - **WAVE 2, SLICE B — THE TAKEOVER MACHINE: a booted machine whose screen manager is OURS** (`test/aes_boot.py`,
    `test/test_aes_boot.py`, one registry entry in `test/aes_event.py`; `recreate/README.md`, "A machine whose screen
    manager is ours"). Harness only: no routine ported, no row added, nothing priced.
    - THE TAKEOVER. `aes_boot.booted(pre, disk, ours=aes_boot.ours_of(blob))` (`desk_machine(ours=blob)`,
      `accessory_machine(..., ours=blob)`) is the ROM's own boot with ONE change, made at a stop BY ADDRESS — switchto's
      `rte` (`$fe395a`) about to pop the frame psetup pushed for ctlmgr: the blob is laid and the two longwords the
      machine keeps the entry in (PD1's p_ldaddr; the frame's PC at the stack's top − 4) are mapped `$fe49d2` →
      `aes_rom_ctlmgr`, found BY SYMBOL in the blob's ELF. No register is set: the ROM's own `rte` enters our entry.
      VETTED AT THE STOP by name (SCRENMGR; on its own stack; its 1,196 bytes below the frame all zero; D0-A6 as
      switchto loaded them all zero; the slots the registry's and holding the ROM's ctlmgr; the free window clear where
      the blob goes) and WHERE THE BOOT ENDS (the `rte` landed on the stack's top; p_ldaddr ours; the screen manager
      parked in the blob — `whose(pc, ours)`: OURS / the ROM's AES text / refused). Kept by content: pre-init machine
      + disk + the blob's bytes and ELF addresses.
    - THE FOUR CLASSES (`by_nature`, `compared`), MEASURED over 14 machines (this battery's five and the screen
      manager's handlers' nine) × both blobs: beside the ROM-booted machine a takeover machine differs in 0 bytes
      outside — the dispatcher's dead frames (19 bench / 21 shipped), the screen manager's saved context (20), its
      stack span (170–174), its p_ldaddr (MAPPED, then equal) — and the blob's span; the registers at the idle are
      equal and every boot ends in THE ROM'S idle (the desk parks last). Each class is located from the machine's
      own pointers; a byte flipped beside any of them is seen. The dead parts are NOISE-PROVED (the dispatcher's stack
      below the idle's SP, the manager's stack below its parked SP, the BIOS's save frame under `savptr`: the
      continuation takes the same instructions), at the ROM's idle and at ours.
    - THE CONTINUED MACHINES (`Machine.continued(mouse_to(x, y) | ikbd(...) | CLICK_TICKS)`): IKBD bytes through the
      ROM's ACIA handler and ticks through Timer C's, from the machine's own vectors, then the CPU entered with the
      idle's whole register file to the next idle of EITHER dispatcher. On both shores the same receptions give the
      same handler calls (`hctl_rect (136, 5)` on the View title; `hctl_button` on a window's closer) and the same
      megabyte outside the classes. Where the screen manager parks LAST the takeover machine idles in OUR dispatcher
      (the stop: the blob's `aes_chkkbd` returning into `aes_idle`); there the whole dispatcher stack is the class
      and two more are nameable per comparison, refused where not needed — the Line-F mask word (2 bytes) and the
      BIOS's last save frame (12) — their spans pinned from the ROM's text and the machine's `savptr`.
    - THE BLOB'S PROTECTION AND THE STANDING LIMIT. A boot is refused if one store lands in the blob after the lay
      (the run's ledger from the lay on + the harness's sector reads; accessory boots clear the whole span BEFORE it —
      Pexec — and a blob laid earlier is refused there: the RED). A CONTINUATION is refused the same way (ledger ∪
      interrupt handlers' stores ∪ sectors, and the bytes): THE BLOB LIES IN MEMORY GEMDOS BELIEVES FREE, so a
      takeover machine cannot be continued through a Malloc or a Pexec that reaches it. A case that stages the blob's
      own text (the build's VDI under `trap #2`) says so through `aes_boot.restaged`.
    - THE INTERRUPT-MASK REFUSAL: a reception is refused by name when the idle's mask is at or above the MFP's
      level 6 ("on iron this machine is dead"); every idle of both shores is held to supervisor mode at the horizontal
      blank's mask (the condition codes are each build's own last test: by nature).
    - THE REGISTRY. `aes_event.SCREEN_MANAGER_ENTRY` ("the screen manager's entry": the two slots, `$fe49d2` ↦
      `aes_rom_ctlmgr`, read off ictlmgr's two immediates) is declared BESIDE `CODE_RELOCATIONS` and named in
      `DECLARED_NOT_YET_MAPPED_AT_TIER3` with its owner (slice D: `tier3.code_relocations` must map it): a test holds
      every `RelocatedCode` to be in the tuple or in that list, and the list EMPTY once a Tier 3 row's machine holds a
      blob's entry in PD1's p_ldaddr.
    - ROM BEHAVIOURS FOUND: switchto overwrites the status word of the frame it pops with its own caller's SR (`move.w
      $8994,(sp)` at `$fe3954`) — psetup's `$2000` is never what a process is entered under (`$2300` here); the
      accessory loader's Pexec stores EVERY byte of the harness's free window before the screen manager first runs;
      with the button held on a menu's item the machine NEVER idles (ct_msgup waits the button up by yielding); the
      four bytes at the ROM's idle's own stack pointer are read by nothing before they are written.
    - MUTATION 70 / 70 in one run (the author's 33, the independent review's 29 — its 11 survivors closed by name —
      and 8 over the second pass's code). TWO CAVEATS: the sweep deselects the one test that reads Tier 3's whole row
      registry (a cold registry import per mutant; the list it reads is killed by the test beside it), and
      `aes_boot.restaged` with its test was added after the sweep and is unswept.
  - **WAVE 2, SLICE C — THE SCREEN MANAGER'S TWINS, PENDING AND BOUND NOWHERE** (`src/aes/ctlmgr.c`,
    `include/aes/gemctrl.h`; `test/aes_gemctrl.py`, `test/test_aes_gemctrl.py`, +69 tests; `test/test_aes_event.py`,
    +2; `recreate/README.md`, "A TURN"). ctlmgr `$fe49d2` (152 B) and ictlmgr `$fe4a6a` (46 B) in C. EVERY MACHINE'S
    SCREEN MANAGER IS STILL THE ROM'S (psetup's frame names `$fe49d2`): no row is registered, no table line added or
    moved, neither routine is a verified row yet — the flip (slice D) binds them.
    - THE ENTRY. On target ctlmgr is ONE function, `aes_rom_ctlmgr` (C, `noreturn`), entered by switchto's `rte` on
      the process's empty stack: no return address, no argument, nothing expected in any register — the image base
      through a register (`staged_call.h`'s `target_image`, hoisted from `evfork.c`: every shipped object and both
      blob binaries byte-identical). Off target its two parts are two calls that return: `aes_ctlmgr_begins` and
      `aes_ctlmgr_turn` (one turn, from the loop's top `$fe49f2` to the next arrival there). IN A FILE OF ITS OWN:
      in gemctrl.c's translation unit GCC splits hctl_rect (`.part.0`) and inlines hctl_button into the loop, and
      every handler row's cycles would move (gemctrl.o is byte-identical).
    - THE STACK (ruling W2-R3's first lever). ITS FRAME IS 24 BYTES ON BOTH BLOBS — THE ROM'S OWN 24 (`link a6,#-12`
      + two registers) — where the design pass's prototype took 72: no thunk and no parameter; the answers read as
      the locals they are (`host_slot_load_words`); the multi-click step a routine of its own; and
      `optimize("no-function-cse")` (36 bytes without it; GCC documents `optimize` as no production lever — taken
      for one flag that changes no semantics, HELD by a test that reads the frame off both blobs and reds at 25).
      MEASURED from the screen manager's first entry in the ROM's boot to its first dispatch, both captures, bytes
      below PD1's top: at ev_multi's entry 50 (ROM) / 64 (ours, both blobs); at dsptch 116 / 144; PARKED 118 / 146
      (the prototype: 194). The 28 more: 14 the call's ABI (36 argument bytes against 22), 14 below ev_multi's
      entry — not ctlmgr's; bounded by a test.
    - WHAT IS HELD. ictlmgr at its own arrival in the ROM's boot (`booted(until=$fe4a6a)`, both captures), Tier 1,
      its two counts and the words it must NOT write staged (argument classes); ON BOTH BLOBS its image the ROM's
      once the two code longwords are mapped through `aes_event.SCREEN_MANAGER_ENTRY` (each holds our entry), its
      write ledger the ROM's, AND ITS PRICE IN ITS OWN TEST — 2,598 / 2,560 cycles against the ROM's 3,614: 0.71 /
      0.70 — until slice D registers the row (the registry maps no row through that entry before the flip). ctlmgr's
      once-only part at `booted(until=$fe49d2)`. ONE TURN at Tier 1 (`aes_gemctrl.Turn`, `held_to_the_rom_s_turn`):
      the ROM's own dispatcher run to an arrival at the loop's top and on, ON THE SCREEN MANAGER'S OWN STACK, to
      the next; the C's turn through the host's model — every door call's frame in the ROM's order, each answer
      and image at a call's return and at a dispatch, the whole end image. 25 turn cases (a box clicked, a box
      watched, a drag, a rubber band, a slider, an arrow's yield, the bar's menu on two machines, a button and the
      bar in one wake with and without a menu, the no-menu spin at two arrivals, the multi-click count at −1, 0,
      2, 3, 4), two key turns, WM_TOPPED. The handlers the ROM's ctlmgr calls in each kind of wake read at their
      entries. On both blobs the entry run from the ROM's first-entry machine, the bytes above its stack poisoned,
      to its first dispatch: the ROM's machine there.
    - THE HOST-SLOT INVARIANT (ruling W2-R4). `host_slot.h`'s audit said the single-frame roles owe a frame per
      process "the day a second process is C"; CORRECTED: they owe it THE DAY THE HOST RUNS A SECOND PROCESS'S C.
      A host run holds one process's C, its caller's — any other process the model enters is the ROM's nested run
      — and that is held by two tests (`test_aes_event.py`): the process hook enters the oracle at the ROM's
      switchto and nothing else, and a hook bound to enter the screen manager's C is refused by name where it
      begins; a single-frame slot claimed again before its release halts by name (`host_slot_take`: a named halt,
      no longer an `assert`). One slot added: ctlmgr's six answer words (`AES_CTLMGR_ANSWERS`, one frame).
    - THE TEST ACCESSORY HAS A SIXTH MODE, `ACC_DOUBLE` (its six-way wait asks for two clicks): 1,010 of the
      cluster's 1,024 bytes (was 993), the accessory disk another disk, `preinit_acc.bin` re-captured — and the
      table byte-identical over it. Two such accessories bring gl_bpend to 3 at the idle and 2 where a second turn
      starts: the count's step at 2 is the ROM's own machine's, no longer staged.
    - 27 WAVE-1 TESTS COMMITTED AT `daa2aef` WERE CAPTURE-DEPENDENT, AND ARE FIXED HERE. The tree's trap-save
      exclusion is THE SNAPSHOT's frame (`aes_event.TRAP_SAVE_AT`: one frame under the savptr the snapshot was
      captured with — the save area's top between polls, one 46-byte frame lower inside a BIOS trap); a BOOTED
      machine's savptr is always the top. Over a snapshot captured inside a trap the handlers' first halves and
      returning cases compared the booted machine's own frame (`$90c..$93a`) byte for byte — red at HEAD over such
      a capture set, and 27 of this slice's turns with them. FIXED: the turns name the machine's own frame
      (`aes_gemctrl.its_trap_save`, off its own savptr, only where it is not the snapshot's; noise-proven dead);
      wave 1's two paths run over the row's own staged machine (`savptr_in_the_band`: what each row's companion
      and Tier 3 row already use — ruled). Green over two in-trap capture sets and three between-polls ones.
      OWED: the other batteries' compares over booted machines were NOT audited for the class.
    - ROM BEHAVIOURS FOUND. ctlmgr asks its main wait for keys and never gets one on a booted machine (w_setactive
      hands the keyboard to the top window's owner at the head of every turn) — and eats one if it does; gl_bpend
      is 1 at every wake unless a second process waits for a double click, and under a menu the menu's own
      evremove counts it down to 1 whatever ctlmgr's steps left; gem_main pushes the running pid to ictlmgr, which
      never reads it; one wake that brings a button and the bar calls both handlers in one turn, the button's
      first, and the order shows (the menu's images differ with the two swapped); with the bar hidden a move onto
      its place wakes nobody, a click and a move there run both handlers.
    - UNPINNED, by name. (1) A MOUSE AT y >= 256 ON BEHAVIOUR: every machine is 320 x 200 (a test says so), so no
      turn tells a handler handed y whole from one handed its low byte — held on both blobs' TEXT only (the two
      answer words moved whole); a monochrome pre-init capture pins it. (2) THE KEY IN THE SCREEN MANAGER'S QUEUE
      IS STAGED (the ROM's own nq over the turn's start, an argument class). TRIED: gem_main makes PD1 the
      keyboard's first owner (`$fda1e4`), and a key laid at the boot's stop at `$fda1f0` is in PD1's queue at its
      first entry and gone after its first turn — seen only on a continuation WITHOUT the boot's device model (six
      floppy calls lie in that stretch); `aes_boot.booted` taking an interrupt at a stop is owed. (3) gl_bpend at
      0, −1, 3, 4, under a menu and with no bar: staged argument classes (no third waiter; a first turn or the menu
      counts it down). (4) "hctl_rect's y := the buttons word" survives: UNREACHABLE BY THIS HARNESS (it delivers
      at idles, polls and door calls — on iron an interrupt between the wake and ev_rets can leave y off the bar).
      (5) The blob side of every TURN: no machine's screen manager is ours before the takeover (slice D).
    - MUTATION (`scratchpad/b5/W2/C/mut/sweep3.log`, one run, two passes: the library alone, then the library and
      both blobs for survivors and target text): 47 mutants, 45 KILLED, 2 SURVIVED — "the answers read after the
      lock" (equivalent) and (4) above. The reviewer's seven survivors are among the killed, by name: R10, R17, R20
      on the host (the key turn on a gadget, the count at 2), R21 on the host and both blobs, R22 / R23 on the
      blobs' text.
    - FOR SLICE D. Add `SCREEN_MANAGER_ENTRY` to `CODE_RELOCATIONS` and map it in `tier3.code_relocations`, then
      register ictlmgr (`aes_pdpipe.register` over `test_aes_gemctrl._ictlmgr_arrived`) and drop its in-test price.
      The turns are `test_aes_gemctrl.TURNS` (+ `THE_OTHER_WINDOW_CLICKED`, `KEY_STARTS`): the same chains from a
      takeover machine's idle; the stale-count drop on the menu turns; WM_TOPPED's residue is then our build's own
      stack words.
  - **WAVE 2 — THE FRAME DIET: THE SHIPPED BLOB'S SCREEN MANAGER FITS ITS 1,196 BYTES, 36 SPARE, ITS OWN VDI UNDER
    ITS TRAPS** (2026-10-10, three passes; `include/stack_diet.h`, `test/test_stack_diet.py`; the bound's form in
    `test/aes_stack.py`; `recreate/README.md`, "The frame diet"). No routine ported, no row added: 18 sources
    recompiled, every pin that moved re-derived. THE VERDICT IS UNDER `## Not reconstructed`, KNOWN THIN MARGINS
    (its tables: bound, measured runs, the ROM beside each; the bench blob's figure reported there, not gated).
    - WHAT THE SECOND PASS CLAIMED AND THE REVIEWS OVERTURNED. "Fits, 44 / 40 spare" was measured with THE ROM'S VDI
      HANDLERS behind our dispatcher: the staging linked the blob's entry and dispatcher under the trap, and the
      dispatcher reads the opcode tables where they lie — ROM data naming the ROM's handlers. The uniform "+32 under
      every call" was the dispatcher's frame, not 22 C handlers. With the blob's own handlers bound that build was
      OVER BY 16 on the shipped blob (v_gtext 398, not 342) and by 190 on the bench one; a v_gtext frame 100 bytes
      deeper moved no pin. The third pass put the truth first (the mapping, who ran, the SP bound), then found the
      bytes.
    - WHAT IT IS. (1) `FRAME_DIET("no-<pass>", ...)` — GCC's per-function `optimize` attribute — on 34 routines:
      33 of the screen manager's paths (ctlmgr's entry among them, its `no-function-cse` spelt the same way with
      `no-defer-pop` beside it: 44 → 36 held over a handler) and the VDI's v_gtext's deep frame: the -O2 passes that
      spend STACK turned off where each was MEASURED to deepen that function's frame (an exhaustive search of seven
      flags per function, then every flag that buys nothing taken off again). (2) just_draw's four parts — the clip
      test, the border and fill, the label, the marks — routines of their own; gsx_blt's ptsin stores a leaf of
      their own. (3) THREE BODIES HELD BY THEIR ONE DEEP CALLER where the ROM calls (ruled): menu_down's by mn_do's
      pass, gsx_blt's by gr_gicon's two blits, bb_fill's by gr_rect — the extern routine and its rows unchanged.
      (4) THE VDI DISPATCHER'S CALL OF THE FUNCTION KEEPS NO REGISTER, AS THE ROM'S DOES NOT
      (`call_vector_as_the_last_act`): it saved eleven round the `jsr` — 44 bytes under every VDI function on
      whichever stack the trap was taken, 196 cycles a call — which the ROM's entry has saved already; the entry's
      C twin makes that save itself now, and both blobs' listings are held to "nothing after the call but pops and
      the return". No `.S`: every routine stays C.
    - WHAT IT BOUGHT (the shipped blob — the gate; own handlers bound; the ROM's own listing read the same way
      beside it): own frames 908 → 744 (704); the deepest trap 896 → 624 (554); AT ITS TRAPS, each site charged
      its own VDI call's need and the unstored allocation under it, + the nest: 36 SPARE — the worst an icon's blit
      in a menu (588 + 244 + 76), its label's text next (562 + 342: 40 spare) — where the second pass's build was
      over by 16; a plain menu drop measured from the real entry 864 (722: 80 spare with the nest), an icon in it
      904 (814: 40 spare); a USERDEF's routine entered 682 → 538 down (472). THE DISPATCHER'S STACK, by the same
      marks and the same bare call: bound 356 → 292, and with the 252 nest it is charged from now 544 of 640 — 96
      spare where band 4 had 40 (32 with the horizontal blank). The marks alone are 188 bytes of the own bound and
      160 of the trap bound (pinned: the blob linked a second time with every mark off). THE BENCH BLOB, reported:
      over by 134 at the icon's label, under the C twin of the text blit (520 for the shipped 342).
    - WHAT EACH LEVER OF THE THIRD PASS BOUGHT UNDER THE TRAP (shipped): the dispatcher's bare call 44 (v_gtext 398
      → 354; every opcode 44); v_gtext's mark 12 (354 → 342). Charged against them: the copy-raster's unstored 76
      under the two blits (a bound the store did not show).
    - WHAT IT COST: `make bench` 0 OVER / 0 DRIFTED; against the table at de408fd 648 lines moved, 356 ratios down
      and 90 up. SLOWER BY 0.04 OR MORE, each named: just_draw "a checked menu item" 0.87 → 0.95, "a box outside
      the clip" 0.86 → 0.94, "an image" 0.94 → 1.01, "a USERDEF answering SELECTED" 0.84 → 0.91, "a string" 0.87 →
      0.93 (its parts are calls now); ob_draw "the menu bar" 0.84 → 0.88; gsx_blt "the screen onto the screen" 0.97
      → 1.01 and "an icon's form in two colours" 1.01 → 1.05 (the corners' leaf, arguments read where they lie).
      ONE ROW WENT OVER THE BAR AS SHIPPED AND IS ADMITTED NET OF ITS THUNKS: just_draw "an image", `net` 0.94 (1.06
      with its thunks) → `glue` 1.01 (1.13 with them). Two rows went the other way, `glue` → `net`: gsx_tblt "the
      font changed" (1.03 → 0.95) and gr_gicon "whitebak over white: an empty label" (1.01 → 0.91). The third
      pass's own: VDI dispatch 1.02 → 0.84 and 1.01 → 0.86 (the bare call); v_gtext's mark +0.01 on six rows of
      d_justified and gdp that reach it (the highest 1.13 → 1.14, `glue`, a row already over as shipped).
      Faster, for the record: forker "nothing queued" 1.04 → 0.89, gr_gicon's rows −0.10, bchange −0.09, b_delay
      −0.11. 555 pinned cycle pairs of the rows that switch moved (11 files) and were RE-DERIVED FROM A RECORDED RUN
      by tool (`tools/pin_recorder.py`, `tools/repin.py`), a dozen more by hand with the reason beside each; the
      third pass moved none of them (a row that switches runs the ROM's VDI on both shores).
    - THE GUARDS. `test_stack_diet.py`: each mark, under each blob's flags, compiles to exactly what the marks-off
      source compiles to with its flags on the command line, and to other instructions than no flag at all; what
      the marks buy is pinned per function. AN `optimize` ATTRIBUTE DOES RESET ONE SETTING OF THE BUILD (the first
      review): `-ffreestanding`'s implied `-fno-tree-loop-distribute-patterns` — a fill loop under a bare attribute
      compiles to `jsr memset`; the setting is spelt INSIDE both macros that make an attribute (the diet's, the
      opcode switch's jump table's), both blobs byte-identical with it, and a test holds a fill loop a loop under
      each. `test_aes_stack.py`: the findings re-pinned whole, each blob's needs BY OPCODE its own; WHO RAN under
      the trap; the 71-slot mapping; the unstored allocations; the trap sites (an opcode two paths can name, or
      whose slot is stored over, refused by name). `test_aes_evdisp_model.py`: the dispatcher's stack under the
      same nest and the build's own handlers. `test_vdi_entry.py`: the dispatcher's call its last act.
      `test_status.py`: a quoted row's VERDICT WORD is the table's, and an "own N against M" in a row's notes is a
      pinned pair (41 were stale after the second pass; re-quoted by tool).
    - ALSO IN THESE PASSES: `UNSTEP_MEASURED_INSNS` (`test_aes_ob_edit.py`) was a CAPTURE-DEPENDENT PIN — its walk
      crosses bytes of the snapshot's MASK, where one capture held a placeholder (`$74df`: nine instructions more;
      not the snapshot's phase). The case now STAGES the masked bytes it crosses and the count is exact again; the
      MASK's own test never saw it because it runs the registered rows and compares what they leave, and this is
      neither. The make-variable probe two test modules spelt is one function (`transcription.make_variable`);
      `test_derived`'s "the registry is among the last" was a count with no slack and is the property now (every
      module handed out after the registry imports it); `tools/repin.py` refuses a record whose ROM-side count
      moved and rewrites a pair only in the recording test's file or a battery it imports (`test/test_repin.py`).
    - MUTATION (one sweep, one log, a private copy; every mutant's build forced, bytecode cleared, the file's digest
      restored): 34 mutants, 33 KILLED, 1 SURVIVED, 0 not a kill. Killed among them, the review's own: v_gtext's deep
      frame 100 bytes deeper (12 reds, the need's pin first); the staging mapping no table slot (23); the unstored
      allocation not charged; the freestanding setting out of the attribute; the entry's twin keeping no register;
      an opcode stored over after its push read all the same; the re-pin letting a ROM-side move through; STATUS
      quoting an old verdict word, and an old cycle count. THE SURVIVOR is the owed item below: gsx_blt's corners
      stored before its second gsx_fix — an order of AES stores no surface sees.
    - GATES: `make gates` rc 0 from a private copy with NO `build/` (`test` and `guarded` each 26,569 passed / 8
      skipped, atari 0; `make bench` 0 OVER / 0 DRIFTED); the whole suite over the other snapshot phase's capture
      set (`savptr` `$90c`): 26,569 passed / 8 skipped; ob_edit's exact count over the capture that holds the
      placeholder at `$74df`. Nothing has run on iron.
    - THE FOURTH PASS (the same day; TESTS AND DOCS ONLY — every shipped and bench object, both blobs and the Tier 3
      table BYTE-IDENTICAL to the third pass's). Its review confirmed the 36 and the dispatcher's contract, and found
      that "its own VDI, handlers and all" stopped one level short: THE LINE-A DRAWING VECTORS WERE LEFT NAMING THE
      ROM'S ENGINES, so under the blob's 71 handlers every text, line, fill and blit ran the ROM's raster code. They
      are mapped now (six, on the blob that ships its transcriptions; vetted, refused by name), and `engines_ran`
      holds per opcode that no engine of the ROM's is entered. WHAT MOVED: nothing stored (the same instructions) —
      and the unstored bound under v_pline and vr_recfl, 0 → 20 each (the blob's own engines' frames, never reached
      before): those two sites are 1,076 and 1,068 with the nest. THE WORST CHAIN IS UNMOVED: 1,160, 36 SPARE; the
      text's site 40. Beside it: the unstored reader reads a `link` on any register, every instruction of the
      listing whatever labels it, and "stored under" down the straight line — refusing what it does not know
      (TextBlt's `link a5,#-84` is stored under three instructions on: 40 by the reader's word); the watch is armed
      again at every trap; the largest reached is a function with a test of its own; the dispatcher's stack carries
      an unstored term (0 under its five calls, pinned); `who_ran` looks for the handler of the opcode's own name,
      not the mapping's; `vdi_dispatch` has its two entries for callers and no other, on both blobs, and the twin's
      register save is read off both; ob_edit's case is shown to use its staging on any capture (a placeholder
      planted beneath it: the exact count; above it: nine more, twelve in one region); `test_status` skips no quote
      (65 verdict words not named as the table names them are held by the ratio they stand beside; an "own N
      against M" whose M is no pinned count is a failure); `repin.py` refuses a pair spelt for more rows than
      recorded its move. MUTATION (one sweep, a private copy, builds forced): 14 mutants —
      the review's four survivors (the case not staging its masked bytes; an "own N against M" with an unpinned M; a
      verdict word in a cell not named as the table names it; the smallest unstored charge) ALL KILLED now; its
      swapped-handlers mutant red in eight tests, the who-ran test among them; the vectors left, a `link` on A6
      alone, a branch not leaving the line, a place not armed again, the ROM's engines not counted, no opcode
      recorded under disp, a second C caller of the dispatcher, the re-pin's shared pair: killed. One survived the
      first run (only the labelled functions scanned: no allocation of today's blobs under no label is reached) and
      is killed since by a hold on the scan itself. GATES: `make gates` rc 0 from a private copy with NO `build/`
      — `test` and `guarded` each 26,591 passed / 8 skipped, atari 0; all 151 shipped objects, both blobs' binaries
      and the table byte-identical to the third pass's (the bench blob's ELF alone differs: it carries the
      assembler's temporary object names, new at every link); the whole suite over the other phase's capture set.
    - NOT TAKEN / OWED: the Alcyon-call contract narrowed for our own thunks (everyobj's `d2` / `a2`: about 8
      bytes; not without the user); the shipped blob's 10-byte glue at gsx_ncode (the transcription's own entry);
      the order of an AES store against a VDI trap, which no behavioural surface sees (KNOWN THIN MARGINS, the
      block's last item). No run of the PRE-diet build with its own handlers bound was made: the "before" of the
      measured runs with our own VDI is not known.
  - **WAVE 2 — FLIP 4: THE SCREEN MANAGER IS OURS. ctlmgr `$fe49d2` AND ictlmgr `$fe4a6a` BOUND AND VERIFIED (373); NO
    SHIPPED OBJECT CHANGED** (2026-10-10, slice D, one agent alone in the tree; `test/aes_takeover.py`,
    `test/aes_ctlmgr.py`, `test/aes_turns_pinned.py`, their two batteries; `test/aes_switching.py`, `bench/tier3.py`;
    one line of `test/aes_event.py`'s registry; `tools/pin_recorder.py`, `tools/repin.py`; `recreate/README.md`:
    "ctlmgr's OWN ROWS", THE SCREEN MANAGER'S TURN, THE BLOB-SIDE HOLD). The C was written by slice C and slimmed by
    the frame diet: THIS SLICE CHANGES NO SOURCE AND NO HEADER — every shipped object, both blobs' binaries and the
    ROM image are byte-identical to `6439927`'s (`src/`, `include/`, `atari/`, the Makefile and the bench's C are
    HEAD's files, and 156 built objects, libraries and blob binaries compared with a build of HEAD's tree made before
    the slice: 155 identical, the bench blob's `.elf` other in 29 bytes of an unloaded section, its `.text`, `.data`,
    `.rodata`, symbols, disassembly and `bench.bin` identical). What the flip is: the harness now RUNS our ctlmgr
    wherever the screen manager runs, and holds it.
    - WHAT RUNS OUR ctlmgr NOW, four things. (1) ictlmgr's ROW, at the ROM's boot's own call of it (two words staged over it: pass 2, below): its two code
      longwords (the PD's p_ldaddr; the PC of the frame psetup lays at the top of the new process's stack) are the
      relocation registry's fourth entry, `SCREEN_MANAGER_ENTRY` — in `CODE_RELOCATIONS` since this slice
      (`tier3.screen_manager_relocation`; `DECLARED_NOT_YET_MAPPED_AT_TIER3` is empty) — mapped and compared exactly:
      **0.59** `net` on the shipped blob (its whole call 2,560 cycles against the ROM's 3,614). That row is what makes
      the takeover no poke (ruling W2-R6). (2) ctlmgr's OWN ROWS, eleven: THE SCREEN MANAGER WOKEN, both shores from a
      booted machine's idle to its next — the ROM's shore the machine the ROM booted, ours THE SAME BOOT WITH THE
      SCREEN MANAGER OURS (the takeover machine itself: `aes_rom_ctlmgr` on the screen manager's real 1,196 bytes,
      nothing laid over it). (3) THE HANDLERS' OWN CASES CARRY OVER: every arrival of the handlers' battery (47 of the
      battery's 52 cases with a chain of them, both blobs) is met by OUR ctlmgr at OUR core of the handler with the
      ROM's frame over the ROM's machine (`tier3.arrives_alike_on`) — but ct_msgup's, which GCC inlines into its two
      callers on both blobs (no arrival of its own: held, and refused by name where asked for). (4) EVERY ROW WHOSE
      RUN ENTERS THE SCREEN MANAGER (32 registered names: read off each row's ROM run, none excused) runs, on our
      shore, WITH THE SCREEN MANAGER OURS, its turn our ctlmgr's and priced by itself (31 turns in the table).
    - RULING W2-R1 AS BUILT — "RE-BASED ONTO TAKEOVER MACHINES" IS AN OVERLAY OF TWO SPANS, NOT ANOTHER MACHINE (the
      slice's own provisional decision D-1, the orchestrator's and the user's to rule on). A row's machine is ONE set
      of pokes for both shores; a machine whose screen manager is ours differs from the ROM-made one, by nature, in
      the screen manager's saved context and its stack alone (beside its p_ldaddr, mapped; the dispatcher's dead
      frames; the blob — `aes_boot.by_nature`, measured on every takeover machine). So the ROM's shore runs each row's
      pokes AS THEY WERE — NO ROM-SIDE COUNT MOVED, no own column, no second count, no window's figure — and our shore
      lays over those two spans WHAT OUR BUILD'S OWN RUN THROUGH THE MACHINE'S HISTORY LEAVES THERE (`aes_takeover`):
      the takeover boot's, where the machine's screen manager stands as the ROM's boot leaves it (measured: THE BOOT
      SNAPSHOT'S DOES, context and live frames byte for byte, nine hundred vertical blanks on — and all eleven booted
      machines park it alike, on the ROM's shore and on each blob: 26 of the 31 rows); and, where a ROM run left it
      elsewhere (its menu holding the screen: three rows; queued on the lock and handed it: one; a recording across
      its turn: one), OUR BUILD'S RUN OF THAT SAME CALL on that blob (`aes_switching.left_by` notes each such run;
      three states today). A state no history reaches is refused by name. At the run's end the stack is put back as the machine came with it and what the ROM's run stored there is dropped by name; the saved context is dropped WHOLE (the ROM's savestate stores every byte of it) and nothing of it is put back (pass 2, below).
    - CLASSIFICATION, READ OFF THE RUN. At every switchto `rte` the watch follows, the PC a process resumes at lies in
      the blob — OURS — or in the AES's ROM text — the ROM's. REFUSED BY NAME: a row that names the screen manager's
      spans whose screen manager resumes in the ROM's text; a foreign process resumed in the blob on any other row; a
      PC that is neither's; a window of the ROM's process with a cycle of ours inside; a turn of ours with a cycle of
      the AES's ROM inside. A window is one kind's: it closes where the turn passes between the screen manager and
      another process (on both shores alike: the ROM's reads no kind off its PCs).
    - THE PRICE OF A TURN (ruling W2 §5 as built; D-2). `screen manager's turn: ours N / ROM M = r` under the row: our build's own cycles inside the window (the blob's less its thunks') against the ROM's WHOLE AES SUBTREE's in the same window of the ROM's run (its text and its Line-F handler: pass 2, below, says what that ratio is made of), the dispatch that hands the machine back in both; held ≤ 1.10 WITH ITS THUNKS BY ITSELF
      — a row with a turn over the bar is OVER whatever its own counts — and off both of the caller's columns. THE 31
      TURNS INSIDE OTHER ROWS: 0.53–0.67 on their own cycles, 0.55–0.72 WITH THEIR THUNKS on the shipped blob (the
      table's), the three highest ev_multi's `a key polled while the screen manager stands woken` and ev_block's
      `Return polled while it stands woken` (ours 98,918 and 7,528 in thunks against the ROM's 148,618: 0.72 both) and
      ev_block's `handed the lock, runs with it` (100,556 + 7,804 against 151,888: 0.71); on the bench blob the same
      three are 0.76, 0.76, 0.75, the highest of all 42 pinned lines 0.76. THE IDENTITY is asserted on the table's path (`vet_the_identity`: book-keeping, pass 2 below): whole = own + thunks + our turns + the ROM's windows + the OS outside them, the last
      ONE number on both shores. No turn is over the bar; none is within 0.30 of it.
    - ctlmgr's ELEVEN ROWS (`net`, own cycles = its turns'; the shipped blob; the bench blob pinned beside): 0.50–0.67
      on their own cycles, 0.54–0.71 with their thunks, the highest the mouse onto a menu title (97,272 + 7,268
      against 146,226: 0.71; the bench blob's 0.76). Each names the classes its two machines differ in where the runs
      end — the dispatcher's stack, the screen manager's context and its stack on all eleven; the Line-F mask word and
      the BIOS's save frame on the three where the screen manager parks last (the machine idles in OUR dispatcher), the save frame alone on the accessory-entry row; WM_TOPPED's four stale words on the row that sends them — and
      EACH CLASS NAMED MUST DIFFER (one not needed is refused, one needed and not named is red by its bytes). WHO RAN,
      held on every one: not one cycle of our run in the ROM's ctlmgr (`$fe49d2..$fe4a6a`) nor anywhere in the AES's
      ROM but the ROM's processes' windows and the ROM's dispatch that brings the first process in; our entry's own
      body run.
    - THE BLOB-SIDE HOLD (owed from slice C; item 5). On every path that measures a run that switches — the table's, a
      named blob's, ctlmgr's rows — OUR IMAGE IS THE ROM'S AT EVERY STOP OF THE DISPATCHER'S WATCH (every poll of the
      idle, every process resumed: a digest a page), outside what every page leaves out, the dispatcher's stack and
      the row's process's saved context whole, the screen manager's two spans where it is ours, the blob and the row's
      own drops — every code address of the registry mapped first. TWO THINGS IT FOUND AT ONCE, both mapped, neither
      left out: the records of a recording in flight hold fork-function entries (ap_trecd turns them into numbers only
      as it returns), and the VDI's cursor vector holds the routine that draws nothing while a playback runs
      (`aes_event.HANDED_WHILE_A_PLAYBACK_RUNS`: restored before any run ends, so no registry slot).
    - WM_TOPPED'S FOUR STALE WORDS ON THE REAL STACK (ruling W2-R2). On ctlmgr's row that sends it the ROM's message
      carries the high half of an address of the AES's text and the low half of one inside the screen manager's stack
      — vetted as that — and ours four zeroes: named on that row alone (the manager's buffer, the owner's pipe, the
      buffer it reads into), red without, refused on a row that sends another message. The zeros stay.
    - THE PINS. 62 whole-run pairs (30 rows + the file selector's session, two blobs) RE-DERIVED BY TOOL from one
      recorded run — reason: FLIP 4, 2026-10-10, the screen manager's turn inside those runs is our ctlmgr's — in
      seven batteries; OUR member alone moved (the recorder's 128 records, 64 whole runs and 64 turns: 0 refused, no ROM-side count moved, NO
      PRICE MOVED: 0 `priced` records). The turns are a third kind of record, lines of ONE data file
      (`test/aes_turns_pinned.py`: a row's blob a line; the tools extended, `test_repin.py`).
    - THE STACK (item 7; ruling W2-R3). No object changed, so the bound stands as the frame diet left it: THE SHIPPED
      BLOB FITS, 36 SPARE at its worst site, and the six measured runs from the real entry with the build's own VDI
      under its traps are unmoved (a menu dropped 864: 80 spare with the nest). ADDED: every row of ctlmgr's measures,
      on its own run on the real stack, how deep each ctlmgr went (the machine's VDI — the ROM's — under the traps):
      the deepest a menu dropped, 722 bytes the ROM's, 828 the bench blob's, 832 the shipped blob's of the 1,196; the
      accessory's entry 616 / 740 / 750; a drag 548 / 640 / 650; the shallowest, the mouse past the titles, 272 / 298
      / 308 — each fits with this build's worst nest on top, on both blobs.
    - FOUND. (1) A RECORDING ACROSS THE SCREEN MANAGER'S TURN IS NO LONGER REFUSED ON A BLOB: the events inside its
      turn are run by OUR forker, whose recorder copies our own entries — the limit of the mixture stands for a turn
      of the ROM's process alone (held on the row left on the ROM's). (2) THE COUNT'S STEP (`$c84e`) SHOWS AT NO RUN'S
      END on any machine at hand: 1 everywhere but the machine with two two-click waiters (3), where the woken
      accessory waits again and the count is 3 once more, and under a menu the menu's own waits count it on — it is
      held by the image at the dispatcher's stops (the two rows on that machine). (3) THE DESIGN'S NUMBERS, verified:
      our ctlmgr parks 134 bytes down (the ROM's 118; the design's prototype 194, slice C's 146 before the diet). (4)
      THE FIRST DELIVERY OF A RUN FROM IDLE is taken at the ROM's idle on both shores (the desk parks last in every
      boot): the fork codes it queues are the ROM's, excepted by slot and code.
    - NOT A ROW, each said in the battery: A KEY EATEN (no machine routes a key to the screen manager: slice C's
      labelled staging, Tier 1); THE SPIN WITH NO MENU BAR (the machine never idles again: no end to run to; Tier 1's
      two turns); the multi-click count's argument classes (0, −1, 3 and above under a menu: Tier 1). UNPINNED, as
      before: a mouse at y >= 256 (a 400-row capture). ctlmgr's rows are no `VERIFIED_CASES` entry (they are no call
      over one machine): the capture-mask sweep and the Tier 1 companion do not run them — their Tier 1 is the loop's
      turn on the host.
    - MUTATION (`scratchpad/b5/W2/D2/sweep.log`, one sweep in a private mirror, every build forced, bytecode cleared,
      each file's digest restored): 43 MUTANTS, 43 KILLED, IN THREE PASSES OF ONE LOG, and the passes are the finding.
      Eleven of the C (the handlers' order swapped; the `$c84e` step dropped on the button's arm, and on the bar's;
      wm_update(0) dropped, wm_update(1) dropped; w_setactive, the once-only copy, the mouse's x and y, the wait's
      button, ictlmgr's load address and its gl_dafirst) and 32 of the harness (the entry mapped to the wrong
      longword, and to another routine; a window misclassified each way; the identity off by one window, twice; the
      spans not laid, not put back, named by no row; the image at the stops asked nowhere and on each path; the frame
      our ctlmgr hands a handler; the re-pin letting a ROM-side count move). WHAT THE FIRST PASS GOT WRONG, said here
      because the log says it: (a) the mirror held ONE TEST RED BEFORE ANY MUTANT, and two kills rested on it alone —
      void, run again over a green baseline; (b) run again, FOUR SURVIVED: the identity never asked, WHO RAN never
      asked (a guard is silent on honest numbers whether called or not), a turn over the bar not making its row OVER
      (no test built such a turn), an arrival's frame not compared (the battery's own reading hid it). Each got a test
      — the guards' CALLS held by themselves, a turn made dearer by hand, a case asked with another frame — and is
      killed in the log's last passes. (c) One mutant (the ROM's text read as ours) is refused by `make derived`
      itself: no kill by the sweep's rule, so it was run without that step and killed by the batteries (16 failures).
    - GATES: `make gates` rc 0 FROM A PRIVATE COPY WITH NO `build/` — `test` and `guarded` each **26,804 passed / 8
      skipped**, atari 0, the table 0 over / 0 drifted — and the whole suite again over a capture set of THE OTHER
      SNAPSHOT PHASE (savptr `$90c`; the gates' own captures `$93a`): 26,804 / 8. +213 on the frame diet's 26,591: the
      takeover's battery (43), ctlmgr's (154, 94 of them the arrivals on two blobs), and the rest in the batteries the
      twelve rows and the turns reach (the table's own, the registrar's, the re-pin's).
  - **WAVE 2 — FLIP 4, PASS 2: THE TWO REVIEWS' ELEVEN FIXES; NOBODY BUT THE SCREEN MANAGER STORES IN ITS CONTEXT AND
    ITS STACK** (2026-10-10; one agent alone in the tree, after two independent reviews — the mechanism's, the rows'
    and pins' — that found no blocker and eleven things to fix; `test/aes_switching.py`, `bench/tier3.py`,
    `test/aes_takeover.py`, `test/aes_ctlmgr.py`, `test/aes_gemctrl.py`, `test/aes_event.py`'s registrar,
    `tools/repin.py`, their batteries; two source comments). NO SHIPPED OBJECT CHANGED (`src/` and `include/` differ
    from `6439927` in ten comment lines of two files, line counts kept; `atari/` and the Makefile not at all; of 156
    built objects, libraries and blob binaries compared with the pre-slice build 155 are identical — gemctrl's own on
    every build among them — and the bench blob's `.elf` is other in the same unloaded bytes as at pass 1, every
    loaded section of both blobs identical). RULINGS, the orchestrator's: D-1, the overlay, is ACCEPTED PROVISIONALLY
    GIVEN ITEM 1 (still the user's to rule); D-2, D-3, D-4 accepted as built and stated as they are (AWAITING 12).
    - 1. WHAT THE OVERLAY HID, AND WHAT HOLDS IT NOW. On the 32 rows whose screen manager is ours its saved context
      and its stack — 1,264 bytes — are out of every compare of the two shores (two builds' frames), where before the
      flip they were compared: a store there by THE ROW'S OWN PROCESS (a target-only stray, which crashes the screen
      manager at its next wake on iron) passed unseen wherever it cost no cycle (the review's probe: one byte flipped
      at `$a400`, `$a878`, `$a3aa` after the turn — every pin kept). NOW: `Switching` keeps the two spans BY CONTENT
      wherever the screen manager does not run — from the run's entry to its first turn, between its turns, from its
      last to where the run ends — on BOTH shores, on every path (the table's, a named blob's, ctlmgr's own rows, the
      arrivals), and REFUSES BY NAME, with the bytes, at the stop that finds one changed. THE DISPATCHER HANDING BACK,
      AS MEASURED: one word — the SR of the `rte` frame switchto stores at the stack pointer the screen manager stood
      parked at (`$2304 → $2700`, and nothing else on any row, either shore, either blob) — excepted where it is
      resumed alone, by its address; the ROM's shore stores nothing else there outside its screen manager's turns
      either. THE PROBE IS RED on both blobs, in the three places, found where the screen manager is next resumed (a
      row whose own process is resumed before its turn) and where the run ends (the pilot); a store before the run's
      first stop is held too (our shore is held from the overlay, not from its watch's first stop). THE C MUTANT THAT
      KEEPS EVERY PIN: a zero-cycle stray store cannot be written in C, so the mutant (ev_block, target-only, one
      store into the screen manager's dead stack after its wait) had its cycles ABSORBED BY A RE-PIN BY TOOL — the way
      a build change's are — and is then KILLED BY THIS HOLD ALONE, where with the hold's refusal off and the pins
      re-pinned it passes (the sweep's C1..C4, below). RF1's F2 (the context's put-back was seen by nothing): the
      put-back is DELETED — the ROM's savestate stores every byte of the context wherever its screen manager parks, so
      the row drops it whole, which is now held by name where a measurement begins.
    - 1b. HOW A ROW LEAVES OUR SCREEN MANAGER PARKED — WHICH WAS DONE, AND WHAT REMAINS UNSEEN. Not done: waking it
      once more by a neutral delivery (no delivery is neutral for every park: its main wait, a menu's wait, the lock's
      queue each wake on other things). DONE, the minimum and a little more (`tier3.how_the_screen_manager_is_left`,
      on every such run): (a) the two shores are held to agree that it ends PARKED AS IT BEGAN or NOT — and where the
      ROM's does, ours must, byte for byte (NO ROW TODAY: every one of the 32 moves it); (b) where the ROM's run ends
      in a state OUR BUILD'S OWN RUN IS KNOWN TO REACH (the takeover boot's park, or a noted run's: made for the rows
      that begin there), ours ends EXACTLY as that run left it, context and live frames — THREE ROWS (ev_block's `the
      lock the desk's; the screen manager queues itself on the lock`, `the mouse onto the bar wakes the screen
      manager, which runs and waits` and `Return polled while it stands woken`: each equal to what another call of our
      build leaves there, on both blobs). (c) THE LOSS, STATED: on THE OTHER 29 ROWS (ev_multi's 16, ev_block's other
      3, the dispatch's 3, fs_input's 2 slices, ev_mesag, ap_rdwr, ap_tplay, all_run, the marshal) our screen
      manager's FINAL saved context and live frames are compared with nothing where the run ends
      (`test_how_each_row_leaves_our_screen_manager_parked_is_what_status_says` pins the census). They are vetted only
      by the runs that wake it again FROM A PARK OF THAT KIND: the menu's wait (ctlmgr's own rows with the menu
      worked; the rows that begin with its menu holding the screen), the lock's queue (the row handed the lock), the
      main wait (every row's first turn). ALSO UNSEEN, by nature: the two bytes of that `rte` SR word at the parked
      stack pointer (rewritten at every resume), and whatever the screen manager stores in its own context and stack
      inside its own turns (its behaviour is what the images at the stops, the streams and the schedule hold).
    - 2. ictlmgr's ROW (RF2 F1). Its machine is the boot's arrival WITH TWO WORDS STAGED (`$8998`, `$cc44`: the values
      the ROM's run leaves) and its two drops were not needed: REMOVED (`staged_alone`; the row is compared whole,
      both blobs; its table lines lost the two drop lines). WHY NO REFUSAL FIRED: there is none for a registrar's row
      — "needed, or refused" is the rule of the rows that switch and of ctlmgr's classes; a registrar's row is held to
      the kit's (the original stores every dropped byte) and, for an SR save word, to "our run stored it too". The
      registrar's STANDING CONVENTION stages each word by nature at the value the ROM's run leaves AND drops it by
      kind, and so staged the drop is needed only where a build leaves another value: MEASURED OVER THE WHOLE TABLE
      (the bench blob, a probe: each such drop removed in turn), OF 943 SUCH DROPS ON 931 ROWS (counted before this
      row's own two went) THE BENCH BLOB NEEDS 49 (45 of the mask word, 4 of `$8996`); 894 are not needed —
      aes_psetup's and aes_pstart's rows among them. THOSE ARE NOT TOUCHED (931 rows' drop lines and companions would
      move): OWED, the user's or the orchestrator's ruling on the convention (AWAITING 12). The row cannot see either
      clear (RF2 M6): said beside it, with the Tier 1 tests that hold them.
    - 3. THE TURNS' RE-PIN (RF2 F2). A record is held to WHAT THE FILE HOLDS: refused, its line left, where its `old`
      is not the file's line (no `old` over a row the file holds; an `old` for a row it does not), and where the ROM's
      member of a turn — or the number of turns — is not the file's; an unchanged record is no line written. The
      review's three crafted cases are tests.
    - 4. STALE STATEMENTS (RF2 F3): corrected — the handlers' battery's section header and two comments, AES_MAP's
      groundwork line (now marked history), an empty code span, and the two source comments (`src/aes/gemctrl.c`,
      `include/aes/gemctrl.h`: comment only, line counts kept; the objects are identical). The project grepped once
      more for "pending", "bound nowhere", "nothing bound", "does not yet fit": what is left is the door twins' own
      vocabulary (`aes_event.PENDING`) and wave-log history.
    - 5. LEAVE-OUTS NOBODY NEEDS (RF2 F4), tried on BOTH capture phases: the three classes no row names (the
      dispatcher's SR word, the bracket's, a QPB in the screen manager's stack) and `_parms_out` are REMOVED — needed
      on neither phase. THE STOP-LEVEL LEAVE-OUT OF THE BIOS'S SAVE FRAME IS THE OTHER PHASE'S: the booted machines'
      savptr is `$93a`, and every page already leaves out the frame under the snapshot's own savptr — the same frame
      on a capture set taken at `$93a` (no window is named), another on one taken at `$90c`, where without it a row is
      red at a stop (a test says which, and runs the red on the phase that has it).
    - 6. TWO CLASSES VETTED AS WHAT THEY ARE (RF2 F5). THE BIOS'S SAVE FRAME: the class is its TEN SAVED REGISTERS
      alone (`tier3.the_trap_save_s_registers`); the saved PC (`$fca7d4`) and SR are compared, and a class two bytes
      wider is refused (the review's mutant dies). The measured reasons are beside the rows: both shores make the same
      BIOS and VDI calls on all eleven; where the screen manager parks last the saved A6 / A7 point into its own stack
      and D3-D7 hold each ctlmgr's registers; on the accessory-entry row they point into the dispatcher's stack.
      WM_TOPPED'S FOUR WORDS, TRACED IN THE ROM'S RUN: they are residue of hctl_button's wm_find, the call before
      hctl_window's — last stored inside wm_find's Line-F call of ob_find (`$feca5e`) — word 4 the high half of a
      return address into the AES's text, words 6:5 ONE longword, a saved frame pointer (`$0000a85a`: wm_find's frame,
      saved by ob_find's `link`), word 7 the word under it, 2 on this machine (ob_find's first local: its depth
      argument and the window it found are both 2 there — not told apart). (The earlier reading, "ctlmgr's preceding
      ev_multi", was wrong.) The places are THREE, one inside the owner's pipe by the machine's own pointer; the
      third, the buffer the owner read into, is named by nothing on the machine once its read has returned, so the
      places are still found by the bytes.
    - 7. CLASSIFICATION (RF1 F3): a process that is NOT the screen manager resumed in the blob is refused by name on
      any machine; a slice of a session whose run has windows of BOTH kinds is refused where a window lies inside it
      (it was lumped as one turn on a claim nothing checked); the AES text's two edges are cases (the review's
      boundary mutant dies).
    - 8. THE IDENTITY (RF1 F4) is said for what it is — book-keeping held with `==`, asked on the table's path alone;
      the ROM's half of its second check an algebraic tautology — in its docstring and the README, and the test of its
      call is named for the path it covers. The batteries' path and ctlmgr's rows carry no own columns to re-add: they
      pin the whole run and every turn exactly.
    - 9. WHAT A TURN'S RATIO IS MADE OF (RF1 F5; ruling D-2 stated as it is). Both sides are THE TURN'S WHOLE AES
      SUBTREE — ctlmgr, its handlers, the event layer, the dispatch that hands the machine back — and the ROM's side
      is counted, by the table's standing convention for every row through the OS (`AES_OWN_SPANS`), in the AES's text
      AND ITS LINE-F HANDLER'S RAM COPY: how Alcyon's AES calls itself, a real cost of the ROM, and 39-46 % of a turn
      with the F-line exceptions' own cycles (the review's recount of four turns, equal to the pins to the cycle). So
      0.50-0.76 is not "our code is that much faster": NET OF THAT CALL MACHINERY OUR TURNS ARE 0.99-1.17 ON THE
      SHIPPED BLOB AND 1.23-1.24 ON THE BENCH BLOB on the four recounted (pilot 1.17 / 1.24, the largest 1.16 / 1.23,
      the up arrow 0.99, a button and the bar 1.16). The label "our ctlmgr's own against the ROM's ctlmgr's own" is
      gone everywhere. PRINTED ON THE TURN'S LINE (cheap: one more tally on the ROM's shore): the Line-F HANDLER's
      share alone, and the ratio net of it — 30 of the 31 lines (a slice's marks carry none): 0.90-1.13, 19 of them
      1.01 (the handler alone is 31-42 %; the exceptions' own cycles, in the text, are beside it). THE BAR'S RULE IS
      UNCHANGED.
    - 10. COVERAGE (RF2 §4): the bar's arm staged at the count 0 and −1 (and 2, 3) where nothing else counts (no menu
      bar) — it was held at 2 alone; ctlmgr's row in the ledger says what is held by a row on the real stack, by Tier
      1 only, and by nothing.
    - 11. CONVENTIONS (RF2 F6): the arrivals' ROM watch is the handlers' own (`aes_gemctrl.ToAnArrival`, with a
      keeping mixin shared with the woken rows' watch); the deliveries' tail is spelt once
      (`aes_switch.taken_at_the_idles` / `taken_at_the_polls`); the two idle-to-idle paths share their setup
      (`tier3._two_shores`); 1196 is the imported `USABLE_STACK_BYTES`; the provenance states are exactly three; the
      vacuous `all(...)` names its one row; the save frame's comment gives the measured reason.
    - THE TABLE, against the reviewed one (`scratchpad/final27/tier3.txt`): 63 lines' TEXT moved and 2 are gone (5,535
      lines → 5,533); NO NUMBER, NO VERDICT AND NO ROW MOVED. The 31 turn lines carry the new label and, 30 of them,
      the Line-F handler's share (the four figures of each unchanged: ours, the ROM's, the OS inside, the thunks');
      the 32 drop lines of the screen manager's saved context now say it is dropped whole and held by content (the
      same spans); ictlmgr's two drop lines are gone. Bench: 0 over, 0 drifted.
    - MUTATION (the same log, `scratchpad/b5/W2/D2/sweep.log`, "PASS 2"): 26 harness mutants and one C mutant in four
      steps. THE REVIEWERS' FIVE SURVIVORS: RF1 MP1 (the AES text's bound inclusive) KILLED; RF1 MP10 (the context not
      put back) NO LONGER EXPRESSIBLE — the put-back is deleted, and what replaced it (a context dropped in part) is
      KILLED; RF2 M7 (the save frame not left out at the stops) IS THE CODE on a `$93a` capture set — it survives
      there by being identical — and is KILLED, 44 failures, over the `$90c` set; RF2 M8 (`_parms_out` a no-op) NO
      LONGER EXPRESSIBLE — removed; RF2 M9 (the class two bytes wider) KILLED. THE PROBE q6: RED on both blobs, in the
      three places, on two rows (tests now). THE NEW HOLDS' OWN, ALL KILLED: the hold a no-op, not asked where the run
      ends, not asked where the screen manager is resumed, its refusal off, the dispatcher's word excepted four bytes
      wide or wherever asked, our shore held from its first stop, the ledger half off, a run's earlier stores taken
      for the screen manager's own; the two shores' parks free to disagree, a known park not compared or never looked
      up; a context dropped in part; the re-pin's three; the two classification refusals; ictlmgr's drops back and
      `staged_alone` ignored; the Line-F share untallied or mis-tallied; WM_TOPPED's places cut to one. THE C MUTANT
      (ev_block, target-only: one store into the screen manager's dead stack after its wait), over the pilot's five
      rows on both blobs: C1, the hold's refusal off and the pins as they are — killed by the pins and, on the rows
      without the screen manager, by the image; C2, the pins RE-PINNED BY TOOL to the mutant (14 records); C3, the
      refusal off and every pin kept — THE FOUR RUNS THROUGH THE SCREEN MANAGER PASS: the review's hole, as it was;
      C4, the hold on, every pin kept — KILLED, the hold's own refusal on those four. WHAT THE EXPERIMENT FOUND ON THE
      WAY, all in the log: (a) its first attempt ran no test (a `-k` expression that was not one): void; (b) at its
      second THE HOLD BY CONTENT ALONE DID NOT SEE THE MUTANT — its constant was already in the overlay, stored
      through the same routine by our screen manager's own boot, and the row's process storing it again changed no
      byte — which is why the hold has a LEDGER half (an address of the two spans first stored outside the screen
      manager's turns is refused whatever value it left); (c) WHAT NEITHER HALF SEES is held as a test of its own that
      passes: the same byte stored again, after the screen manager's turn, at an address that turn itself stored in
      the same run (the ledger keeps addresses, not who stored last).
    - GATES: `make gates` rc 0 FROM A PRIVATE COPY WITH NO `build/` — `test` and `guarded` each **26,876 passed / 8
      skipped**, atari 0 — and the whole suite over the capture set of THE OTHER SNAPSHOT PHASE (savptr `$90c`):
      26,876 / 8. +72 on FLIP 4's 26,804: the stray stores and the parks' census in the takeover's battery, the save
      frame's two and the arrivals' in ctlmgr's, the bar's arm's four stagings and ictlmgr's machine in the handlers',
      the re-pin's crafted cases.
  - **WAVE 2 — SLICE E, THE WAVE'S CLOSE: THE HANDLERS' ROWS ARE MEASURED WHERE OUR ctlmgr RUNS THEM; NO NUMBER OF EITHER
    SHORE MOVED; NO SHIPPED OBJECT CHANGED** (2026-10-10; one agent alone in the tree, by the orchestrator's ruling
    "slice E is this and no more"; `bench/tier3.py`, `test/aes_switching.py`, `test/aes_ctlmgr.py`,
    `test/test_aes_ctlmgr.py`, `test/test_aes_gemctrl.py`, `test/aes_aptape.py` and its battery, three censuses; two
    source comments; `recreate/README.md`: "A HANDLER'S ROW AT ITS ARRIVAL"). Since FLIP 4 the screen manager's loop is
    our C wherever a build runs it, and its handlers were still PRICED as kit calls over the machine the ROM's ctlmgr
    arrives with (met at our ctlmgr's arrivals, measured at the ROM's). No longer.
    - WHAT A HANDLER'S ROW IS NOW (`tier3.at_its_arrival_on`, `aes_switching.ThroughAHandler`). ONE RUN A SHORE, each a
      bench run of code in place from a booted machine's idle — the ROM-booted machine on the ROM's shore, THE TAKEOVER
      MACHINE of the same boot on ours — through the case's own chain to the handler's first instruction (the ROM's
      ctlmgr calling the ROM's routine; OUR ctlmgr, and our handlers above the one arrived at, calling OUR core) AND ON
      THROUGH THE HANDLER TO ITS RETURN, on the screen manager's real 1,196 bytes. THE ROW IS THE SLICE between the
      arrival and the return. Two watches in turn, neither new: `ToAnArrival` to the arrival (what the flip's
      "arrives alike" ran), then — made AT the arrival — the very `Switching` round `DoorWindows` that a kit call of
      the handler is followed by, so the row's own deliveries are laid at ITS idles, polls and door calls as its
      registry row derived them and the row is held to EVERYTHING the kit's path holds a row that switches to (one
      schedule; the windows of the ROM's processes equal to the cycle; the same door calls handed the same frames, net
      of the same windows; the image at every stop; the OS both run equal; the identity; both counts under the bar).
      BESIDE IT: the frame our ctlmgr hands the handler is the ROM's; the image at every stop on the way and at the
      arrival; THE MEGABYTE WHERE THE HANDLER RETURNS, the ROM's outside the classes the row NAMES (as a woken row's:
      each must differ, one not needed is refused) and its own named windows (each must differ too); the streams.
    - WHICH ROWS: 33 — hctl_window's 22, hctl_rect's 6, hctl_button's 5 — every priced case whose handler a blob's
      ctlmgr arrives at; and THE 14 TIER 1-ONLY CASES of those handlers (hctl_window's 12, hctl_rect's 2) are held the same way on both blobs, to the
      same rules, pinned nowhere (they were "met"; they are now run through to the return). NOT MOVED, each said in
      the battery and beside its row: ct_msgup's 4 rows — ON A BLOB IT HAS NO ARRIVAL OF ITS OWN (GCC inlines it into
      hctl_window and hctl_rect: held on both listings; a run asked to arrive there is refused by name): they stay
      calls of the out-of-line body over the ROM's arrival's machine, and WHAT OUR BUILD RUNS OF IT IS HELD BY ITS
      CALLERS' MOVED ROWS (the sweep's C1 and C2, mutants of ct_msgup's body: 78 and 62 of the 94 runs at our
      arrivals red, hctl_window's, hctl_rect's and hctl_button's); and THE BOOT'S OWN ARRIVAL's row (hctl_button, a
      click the bar posted for itself: no run from a machine's idle reaches it — our ctlmgr is held to arrive there
      with the ROM's frame, the row stays a kit call).
    - NO NUMBER MOVED, ON EITHER SHORE — the finding. The brief expected ours to move once, by tool. MEASURED: on all
      33 rows, on both blobs, the ROM's slice on the real stack costs what its kit call cost TO THE CYCLE, AND SO DOES OURS: the whole-run
      pairs, both own columns, the caller's own, the calls and the windows are the pinned ones — the recorder
      (`tools/pin_recorder.py`) over the moved rows' batteries wrote NO RECORD (4,468 tests; its only records of the slice are the new row's two turn lines, which `tools/repin.py` added). A handler's cost does not depend on
      whose stack it runs on or on who called it, and now that is a measurement, not an assumption. THE COSTS ARE THE
      SLICE'S IN THE TABLE'S UNIT: the kit's entry constant (1 instruction, 40 cycles: the oracle's reset) is added
      to both, as every row's two costs carry it. NEW PINS, none replacing another: the 14 returning rows' whole runs
      on both blobs (`test_aes_ctlmgr.RETURNING_WHOLE_RUN`: the shipped blob's pairs are the reviewed table's costs
      less the constant; the bench blob's were pinned nowhere before).
    - WHAT A FALL BACK TO THE KIT'S ROAD WOULD SHOW: NOTHING IN A PIN (the numbers are the same) — so THE ROAD TAKEN IS
      HELD BY ITSELF: the table's measurement of a handler's row asks `at_its_arrival_on` once, a named blob's
      (`aes_switching.measured_on`: `vet_on_a_blob`, the recorder) goes `through_its_handler_on` once, and the rows the
      table measures so are exactly the declared ones (`aes_ctlmgr.HANDLED`), carrying no kit drop (the sweep's H19,
      H20, H21).
    - THE CLASSES, per row (`test_aes_gemctrl.differs_where_it_returns`; measured, both blobs, both capture phases).
      On all 33: the dispatcher's stack, the screen manager's saved context and its stack — two builds' frames — and
      THE LINE-F MASK WORD (the ROM's handler's own masked return wrote it last; no C does). THE BIOS'S SAVE FRAME (its
      ten saved registers; the saved PC and SR compared) on 23: MEASURED — at the arrival the frame is the same on
      both shores on every case, so it is a class exactly where THE HANDLER ITSELF takes the last BIOS trap before it
      returns (a wait's keyboard poll, its own dispatcher's); not on the nine whose handler takes none, nor on the
      arrow held, whose last trap is the ROM's dispatcher's on both shores (handing back from the accessory).
      WM_TOPPED'S FOUR STALE WORDS on the two rows that send it (ruling W2-R2: the zeros stay): where the handler
      returns in the manager's buffer and the owner's pipe — AND IN THE FRAME THE WRITE IS HANDED, so on those rows
      the two shores' door calls are compared with the ROM's frame read as the C sends it
      (`the_topped_words_as_the_c_sends_them`: that message's words 4..7, nothing else); without the class the row
      is refused by the frame. THE STALE COUNT (contrl[3] after the menu's ct_mouse re-show) on hctl_rect's three:
      the row's own named window, required to differ where the handler returns.
    - WHAT A KIT CALL HELD AND A ROW AT ITS ARRIVAL DOES NOT, said: of the memory, the screen manager's two spans
      (context, stack) are out of the compare where the handler returns, as on a woken row. THE CALLEE-SAVED FILE IS
      HELD (pass 2, below: this entry first said it could not be — "no bench run reads a register at a stop" — which
      was wrong). WHAT IT
      HOLDS THAT A KIT CALL DID NOT: the real stack (every case's deepest store from the idle to the return fits the
      1,196 bytes with the build's worst nest on top, both blobs: the deepest a menu worked, 832 the shipped blob's);
      the real caller's frame; WM_TOPPED's words as the machine really carries them; who ran, from the idle on.
    - WHO RAN (`vet_who_ran_the_handler`, asked of every such row; its call and its arithmetic each held): from the
      machine's idle to the handler's return NOT ONE CYCLE of our run in the ROM's own text of the handler, nor in the
      ROM's ctlmgr; some in our core between the arrival and the return; the ROM's run some in its handler and none
      in the blob; and our slice's cycles in the AES's ROM exactly its windows of the ROM's processes (the general
      guard asked too).
    - FOUND ON THE WAY, a harness gap of the flip's: A DELIVERY AT THE ROM'S DISPATCHER'S OWN POLL — the first
      dispatch of a run from idle, before any process is entered — queues the ROM's fork codes for the ROM's forker
      at a poll that is no idle exactly as at an idle, and only the idle's were kept as a window's are
      (`foreign_codes`). No woken row delivers at such a poll, and "arrives alike" never asked whether a slot names
      the ROM; the first row that did both (hctl_rect, the mouse off the titles again before the manager ran) was
      refused for "OUR code stored the ROM's address". One spelling for both now
      (`Switching._lay_for_the_rom_s_forker`); the sweep's H22 puts the gap back and that row is red.
    - THE RECORDING ACROSS THE SCREEN MANAGER'S TURN IS A REGISTERED, PRICED ROW (the flip's author: "it could be").
      ap_trecd, the mouse onto the menu bar and off it: its machine is the running desk's as every recording's, the
      screen manager inside it ours from the takeover boot (the overlay, D-1), its one window a turn of our ctlmgr:
      **0.66** own (0.70 with thunks), the caller's own 0.50 (0.53) — `87818 / 922254` against `81982 / 845258` —
      and THE TURN, by itself, ours 139,152 + 9,764 in thunks against the ROM's 219,072: 0.64, 0.68 with them (the
      bench blob's 0.72), net of the Line-F handler 1.02. It holds on both blobs (Tier 1 companion, both pins, the
      turn's line by tool). Where it ends our park is held to our build's own run to that state (it is its own
      provenance: the fourth row so held; 29 stay compared with nothing there, as pass 2 says). THE LIMIT THAT STANDS
      — a recording across a turn of THE ROM'S PROCESS — is held on the same row left on the ROM's screen manager.
      171 rows switch; 33 registered names enter the screen manager; the table prices a turn under 32 rows.
    - RETIRED: `tier3.arrives_alike_on` and its battery (the "met, not measured" arrangement: every hold it made is
      made by the row now, and the 14 unpriced cases gained the run through the handler); the wording that said the
      handlers are measured at the ROM's arrivals (the batteries' docstrings, README, this ledger's rows, two source
      comments — comment only, line counts kept); an import the removal orphaned; and the flip's own named leftover —
      "map our shore back" was spelt at three sites, now `tier3._mapped_back` (the sweep's H27: 0 maps, red in three
      batteries). NOT TOUCHED, by the ruling: the registrar's staged-drop convention, the overlay (D-1), the bar's
      rule. NOTICED, not changed: the registry still files the handlers' kit-path drops (context, dispatcher's
      stack, mask word, the stale count) — they are what the Tier 1 companions stage and compare, and the census of
      the rows that switch counts them; the table no longer prints them under a row measured at its arrival.
    - THE TABLE, against the reviewed one (`scratchpad/final28/tier3.txt`): NO NUMBER AND NO VERDICT OF ANY ROW THAT
      WAS THERE MOVED. 74 lines gone — the 33 moved rows' "dropped from the image compare" lines (the mask word 33,
      the saved context 19, the dispatcher's stack 19, the stale count 3) — and 160 in their place, "left out of the
      compare of the two machines where the handler returns: …" (4 a row, the save frame on 23, WM_TOPPED's words on
      2, the stale count on 3); and ONE ROW MORE, the recording's, with its 16 lines under it (the whole run, the two
      counts, the turn, 13 drops). 5,533 lines → 5,636. Bench: 0 over, 0 drifted.
    - MUTATION (`scratchpad/b5/W2/E/sweep.log`, one sweep in a private mirror, every build forced — a C mutant's
      objects, host library and both blobs made again from nothing and their digests checked changed and, restored,
      back — bytecode cleared, each file's digest restored): 36 MUTANTS, 36 KILLED, in one log of two runs — the first ended at its seventh mutant, which DID NOT COMPILE as
      first written (a parameter left unused): no kill; written again, the sweep resumed over a build made again from
      nothing and held to the baseline's digests. EIGHT OF THE C, each run on ITS OWN MOVED ROWS (the 94 runs at our
      arrivals), the table's road and Tier 1 APART, and counted killed only by the first: ct_msgup's body twice — the
      message sent only where there is none (78 of the 94 red), the button never waited up (62): no arrival of its
      own, held by its callers' rows; hctl_window's closer and fuller swapped (8) and its elevators' messages (6);
      hctl_button's desktop taken for a window (2) and its count stepped twice (94); hctl_rect's menu worked off the
      titles (20) and an accessory's entry sent as its item (8) — every one killed by Tier 1 and by the table's road
      too. 28 OF THE HARNESS, each killed: the slice ended where it began; a return address reached with the frame
      still pushed; WHO RAN unasked, and each of its three conditions off; the image unheld inside the handler, and
      to the arrival; the megabyte where the handler returns uncompared, any class taken, the save frame named by
      every row; a row's own window not required to differ, not left out where it returns, not left out at the
      stops; the door calls uncompared, WM_TOPPED's reading applied to every row, and to every message; the frame
      our ctlmgr hands unheld; the ROM's cost without the entry constant; either own column miscounted (the windows
      kept, the thunks kept); the table's road and a named blob's fallen back to the kit's call, a row's registry
      drops kept; the poll's delivery laid with its codes unrecorded; the row's deliveries laid unrelocated; the
      mapped-back helper mapping nothing; the recording left unregistered. (The baseline: 4,684 passed over a build
      from nothing, its three artifacts the reviewed flip's digests.)
    - GATES: `make gates` rc 0 FROM A PRIVATE COPY WITH NO `build/` — `test` and `guarded` each **26,893 passed / 8
      skipped**, atari 0 — and the whole suite over the capture set of THE OTHER SNAPSHOT PHASE (savptr `$90c`):
      26,893 / 8. +17 on pass 2's 26,876: ctlmgr's battery (+9: the arrivals' 101 tests are 110 — the 94 runs now measured through the handler, their REDs, the road's two) and the batteries the recording's row reaches (+8). THE 151 SHIPPED OBJECTS ARE BYTE-IDENTICAL to `73eaf53`'s
      build (and the host library and both blobs' binaries reproduce the reviewed flip's digests).
    - DECIDED BY THE SLICE, the orchestrator's (and the user's) to overturn: E-1, a slice's two costs carry the kit's
      entry constant (the table's unit; it is what keeps the ROM's pinned costs the same numbers); E-2 (AS CORRECTED AT
      PASS 2), a row at its arrival holds the callee-saved registers where our handler returns, read off the oracle's
      CPU at the two marks, and the screen manager's two spans are classes there; E-3, the
      recording across the screen manager's turn is registered (its ledger row said "Tier 1 ONLY by ruling" while
      its turn was the ROM's code); E-4, the Tier 1-only cases are run through the handler at our arrivals, unpinned;
      E-5, ct_msgup's four rows and the boot's own arrival's stay kit calls.
  - **WAVE 2 — SLICE E, PASS 2: THE REVIEW'S SIX FIXES; THE CALLEE-SAVED REGISTERS ARE HELD WHERE OUR HANDLER RETURNS**
    (2026-10-10; one agent alone in the tree, after an independent review — `scratchpad/RE1/review.md` — that found no
    blocker and six things to fix; `bench/tier3.py`, `test/aes_ctlmgr.py`, `test/aes_boot.py`, ctlmgr's battery; docs).
    NO SHIPPED OBJECT CHANGED; NO NUMBER, NO LINE OF THE TABLE MOVED against pass 1's (5,636 lines, byte for byte).
    - 1. E-2's REASON WAS WRONG, AND THE COMPARE IS RESTORED WITHOUT A KIT EDIT. Pass 1 said "no bench run reads a
      register at a stop". The oracle's CPU stands stopped with its whole register file at every stop; what is true
      is that the kit's `watched` loop hands a watch the PC, A7 and the memory only. So the two marks of a row at
      its arrival READ THE CPU (`aes_boot.registers_at_the_stop`: Musashi's accessor, the reach this ledger already
      lists as an owed kit accessor) and `tier3.vet_the_handler_kept_its_caller_s_registers` holds, on all 33 rows
      and the 14 unpinned cases, both blobs, that D2-D7 and A2-A6 are back where our handler returns as its real
      caller held them where it called — the kit call's own eleven, on the caller's own values. THE REVIEW'S MUTANT
      (`moveq #-1,%d7` in hctl_rect under `__m68k__`: a register dead in ctlmgr, which before this moved cycle pins
      and nothing else) IS KILLED AS A REGISTER: its 16 runs at our arrivals red by "`aes_hctl_rect` RETURNED TO ITS
      CALLER WITH d7 = 0xffffffff, entered with 0x0"; the same in hctl_window (D6): 72 runs. Tier 1 cannot see
      either (the host build), as before. Nothing of the CPU is unseen that a kit call saw.
    - 2. E-1..E-5 ARE AWAITING ITEM (13), E-2 as corrected.
    - 3. THE TIER 1-ONLY CASES ARE 14, not 13 (hctl_window 12, hctl_rect 2: 47 arrivals less the 33 rows) — a
      miscount of the entry's, in three places; now counted off the registries and held to this ledger's sentence
      (`test_the_cases_held_at_their_arrival_and_pinned_nowhere_are_the_ones_status_counts`).
    - 4. THREE GUARDS THAT NO TEST REDDENED (the review's survivors N4, N5, N6), each given its red and its mutant
      killed. WHO RAN'S RANGE: the ROM's own text of a handler is pinned to `names.txt`'s routine bounds — WHICH
      FOUND IT ONE ROUTINE TOO WIDE for hctl_rect (it ran on to ctlmgr, over ct_chgown `$fe49ba`: our cycles there
      are none either way, the ROM's "some in its handler" was the looser for it); corrected. THE STREAMS and THE OS
      BOTH RUN: a crafted run each (one hardware write more on ours; the shared cycles read one apart), refused by
      name.
    - 5. THE SOFT EDGES OF "NEEDED, OR REFUSED". A WINDOW LEFT OUT AT THE STOPS ALONE (`Handled.at_stops_only`) must
      now DIFFER AT A STOP of the handler's own run or the row is refused (the review's probe — the stale count named
      on the closer held — is a test, red). STATED, NOT CLOSED: a row's own window (`also_dropped`) is needed where
      ANY byte of it differs, so one named two bytes too wide still passes — not cheap to refuse (an edge byte of the
      one window at hand, the stale count's word, may by nature be equal on the two shores); it is the three
      stale-count rows' window alone, the classes being located centrally and the save frame's width pinned. AND:
      on a handler that does next to nothing the four classes every row names already differ AT THE ARRIVAL —
      "each must differ" is there a fact of the road to the handler, not of the handler.
    - 6. QUALITY: the two road tests assert that what is priced IS the arrival's road's own measurement (the review's
      sham roads died of an `AttributeError`; they die of the assert now); WM_TOPPED's stale words' width is
      `aes_ctlmgr.STALE_WORDS_AT`'s, one spelling; the redundant clause of `is_measured_at_its_arrival` is gone; the
      streams' compare is one helper for a woken row and a handler's. NOT DONE: `through_its_handler_on` is not split
      into its four phases (the review: "may be recorded") — it stays one sequential function of four commented
      phases, as `idle_to_idle_on` and `_held_through_the_os` are.
    - MUTATION (the same log, `scratchpad/b5/W2/E/sweep.log`, "PASS 2"): 11 MUTANTS, 11 KILLED. The review's three
      survivors and its two sham roads; the register hold unasked, and its refusal off; the stops-only refusal off;
      hctl_rect's text run on to ctlmgr; and the two register mutants of the C — WHICH THE SWEEP FIRST CALLED "NO
      KILL" BY ITS OWN RULE that a C mutant change the host library too (a target-only mutant leaves it: the rule
      said for what they are, both run again: killed by their own moved rows, 28 and 144 lines of the register's own
      refusal; Tier 1 green on both, as it must be).
    - GATES: `make gates` rc 0 FROM A PRIVATE COPY WITH NO `build/` — `test` and `guarded` each **26,898 passed / 8
      skipped**, atari 0. +5 on pass 1's 26,893: the register hold's, the handlers' text bounds, the two crafted
      holds, the stops-only refusal, the count of the unpinned cases. The 151 shipped objects byte-identical to
      `73eaf53`'s build.

## Suite — the re-sums before AES band 5 wave 3

- BAND 5 WAVE 2's CLOSE, SLICE E, PASS 2 (2026-10-10; the review's six fixes — the callee-saved registers held where our
  handler returns, three guards given their reds, the stops-only window needed or refused; tests, harness and docs;
  every shipped object byte-identical, the table's 5,636 lines unchanged): `make gates` rc 0 from a private copy
  with NO `build/`, `test` and `guarded` each **26,898 passed / 8 skipped**, atari 0. +5 on the line below.
- BAND 5 WAVE 2's CLOSE, SLICE E (2026-10-10; the handlers' 33 rows measured where each shore's own ctlmgr arrives at
  its handler — no number of either shore moved —, the recording across the screen manager's turn registered: one row
  added to the table, 5,636 lines; tests, harness and docs, two source comments; every shipped object byte-identical):
  `make gates` rc 0 from a private copy with NO `build/`, `test` and `guarded` each **26,893 passed / 8 skipped**,
  atari 0; and over the other snapshot phase's capture set. +17 on the line below.
- BAND 5 WAVE 2's FLIP 4, PASS 2 (2026-10-10; the two reviews' eleven fixes: tests, harness and docs; two source
  comments; every object byte-identical; the table's 5,533 lines the same numbers, 63 of them other text): `make
  gates` rc 0 from a private copy with NO `build/`, `test` and `guarded` each **26,876 passed / 8 skipped**, atari 0;
  and over the other snapshot phase's capture set. +72 on the line below.
- BAND 5 WAVE 2's FLIP 4 (2026-10-10; ctlmgr and ictlmgr verified, 12 rows added to the table, 31 rows given a turn's
  line and their whole-run pins moved once by tool; every object byte-identical): `make gates` rc 0 from a private
  copy with NO `build/`, `test` and `guarded` each **26,804 passed / 8 skipped**, atari 0; and over the other snapshot
  phase's capture set. +213 on the line below (the wave log's FLIP 4 entry counts them).
- THE FRAME DIET's FOURTH PASS (2026-10-10; tests and docs only, every object byte-identical): `make gates` rc 0 from
  a private copy with NO `build/`, `test` and `guarded` each **26,591 passed / 8 skipped**, atari 0; and over the
  other snapshot phase's capture set. +22 on the line below: the engines and the vectors, the unstored reader's
  shapes, the dispatcher's callers, ob_edit's staging by region, the re-pin's shared pair.
- BAND 5 WAVE 2's FRAME DIET, its three passes (2026-10-10; no routine bound, no row added; the table's lines are
  the same 5,201, 648 of them with other numbers): the headline is `make gates` rc 0 FROM A PRIVATE COPY WITH NO
  `build/` on the diet's final tree — `test` and `guarded` each **26,569 passed / 8 skipped**, atari 0 — and the
  whole suite again over the capture set of the OTHER snapshot phase (`savptr` `$90c`; the gate's own was `$93a`):
  26,569 passed / 8 skipped. +114 on the line below, all tests of the diet's guards: `test_stack_diet.py`, the
  stack's findings and who ran under the trap (`test_aes_stack.py`), `test_repin.py`, the dispatcher's call
  (`test_vdi_entry.py`), two holds of this file's own quotes (`test_status.py`), ob_edit's declaration.
- BAND 5 WAVE 2's GROUNDWORK (2026-10-10; slices A, B, C — no routine bound, no row added: THE TABLE IS BYTE-IDENTICAL
  TO `daa2aef`'s, 5,201 lines, over a re-captured accessory machine too): the headline above is the reconciliation's
  own `make gates` FROM AN EMPTY `build/` on the three slices' final tree (three fresh captures): `test` and
  `guarded` each **26,455 passed / 8 skipped**, atari 0 — +451 on the line below, all tests of the three slices'
  harness and of the pending twins (slice C's share: +69 in `test_aes_gemctrl.py`, +2 in `test_aes_event.py`).
  CONFIRMED AT THE ORCHESTRATOR'S OWN GATE (the same counts, another three fresh captures). 150 of the 151 shipped objects are byte-identical to
  `daa2aef`'s; the one new is `src_aes_ctlmgr_c.o`.
- CONFIRMED AT THE ORCHESTRATOR'S GATE for slice C with the family test's fix (`make gates` from an empty `build/`,
  three fresh captures, 2026-10-09): `test` and `guarded` each **26,004 passed / 8 skipped** (+3 on the line below:
  the family test's two new tests and its RED); the 149 shipped objects before the slice byte-identical, one new.
- Re-summed at BAND 5 WAVE 1's SLICE C, after its review's pass (the screen manager's four handlers, 2026-10-09):
  **26,001 passed / 8 skipped / 0 xfailed**, 0 failed — `make gates` rc 0 from a private copy with NO `build/`
  directory and no oracle library (test and guarded 26,001 each, the ROM build 0; three fresh captures). +312 against the reconciliation below (25,689):
  `test_aes_gemctrl.py`'s 149, the 138 parametrised cases its 38 rows add to `test_tier3.py`, the eighteen rows
  of the dispatcher's-own-calls rule in `test_aes_switching.py` (six more skipped: on request), and the seven of
  `test_makefile.py`. `make bench` rc 0 (0
  OVER, 0 DRIFTED); every one of the table's 5,013 earlier lines still there in order, one block of 188 lines
  inserted (the handlers' rows and what prints under them). WHAT THE SLICE ADDS TO THE WARM SUITE, measured by the
  review on a quiet machine: band 4 (`a2e0519`) 156.3 s, HEAD `497a635` 187 s, with the slice 193.7 s — about +7 s
  (the author's own pair, a busy machine, 255.8 s against 263.4 s: the same difference); its tests sum to some 30 s
  of test time, the blob runs of its rows held once, in `test_tier3.py`. No content-neutral lever was found in how
  its rows enter that file's parametrised tests on a short look (each is one measured run a row and a blob).
  THE BATTERY AND ITS ROWS' PINS over fresh sets of the three captures, each made from nothing in a private copy:
  green over two before the review's pass and two after (266 and 138 each time).
- Re-summed at BAND 5 WAVE 1's docs reconciliation (slices S, H and G with their fix passes, 2026-10-09): **25,689
  passed / 2 skipped / 0 xfailed**, 0 failed, on a bare `pytest -q -n auto test` in a private copy of the wave's
  final tree over a FRESH boot capture (250.9 s, the machine shared with other runs: no timing to quote). +1,760
  against step R below (23,929): band 5 wave 0's harness battery, slice S's and slices H / G's batteries and the
  rows they add to the registry's sweeps. `make bench` rc 0 (0 OVER, 0 DRIFTED); every line of the table before the
  wave is still there, in order, with nothing added under it. CONFIRMED AT THE ORCHESTRATOR'S GATE (`make gates`
  from an empty `build/`, three fresh captures): `test` and `guarded` each 25,689 passed / 2 skipped; 139 of the 140
  shipped objects of step R byte-identical, the 140th `gemdosif.c`'s (the port extends it), nine new.
- Re-summed by STEP R of band 4 wave 3 (THE RETIREMENT and the answers handed back, 2026-10-09): **23,929 passed / 2
  skipped / 0 xfailed**, 0 failed, on a bare `pytest -q -n auto test` over the step's final tree, twice (cold 232.7
  s; warm 153.0 s / 1,353 CPU-s, the 1-minute load 21 at its start and 67 at its end — against 164.1 s / 1,442
  CPU-s at `084c11e`, one sample a side). −26 against gate 13's fix pass below (23,946): 51 ids retired with the
  shadow, the hop checks and the model's subsumed cases, 25 added (the entry's TESTS line). `make bench` rc 0: the
  table that of gate 13 but for ONE line, the legend's (0 OVER, 0 DRIFTED), and every shipped object's hash
  unchanged. BEFORE THE ANSWERS HANDED BACK the step's tree (23,908) had passed `make gates` FROM AN EMPTY `build/`
  (test and guarded side by side, 391 s each, 29,277 candidate runs guarded; the ROM build rc 0 — which
  re-captured the boot snapshot: 593 bytes of it differ from the capture before, and neither the table nor a test
  moved with them); THE FULL `make gates` OF THIS STATE IS THE ORCHESTRATOR'S.
- Re-summed by GATE 13's FIX PASS of band 4 wave 3's steps S and T (2026-10-08): **23,946 passed / 2 skipped / 0
  xfailed**, 0 failed, twice in one `make gates` FROM AN EMPTY `build/` (the old one moved aside; `make test` and
  `make guarded` side by side, 416 s each, 29,233 candidate runs guarded; the ROM build rc 0), the machine loaded
  (1-minute load 125 at its end): NO TIMING TO QUOTE. +25 against the docs pass below (the entry's TESTS line has
  them by file). `make bench` rc 0: the table BYTE-IDENTICAL to the one before the pass (2,011 rows, 0 OVER, 0
  DRIFTED), and every shipped object's hash unchanged.
- Re-summed by THE DOCS PASS of band 4 wave 3's steps S and T (2026-10-08): **23,921 passed / 2 skipped / 0
  xfailed**, 0 failed, on a bare `pytest -q -n auto test` over the merged tree, started after this pass's last edit
  of `names.txt` (a derivation-cache input: the cache was cold for the tree) — 624 s of wall, 1,306 CPU-s user and
  854 sys, NO TIMING TO QUOTE: the load was 117 at its start and 147 at its end (the review's finders at work).
  +342 against the fix pass below (23,579): `test_aes_aptape.py` new (164), `test_aes_fs_input_woken.py` new (20),
  `test_aes_evlib_woken.py` 227 → 306, `test_status.py` 12 → 15, `test_aes_switching.py` 67 → 66, the rest in
  `test_aes_fs_input.py`, `test_aes_event.py`, `test_tier3.py` and the snapshot's sweeps. The two authors' own
  last runs of the same tree were 23,916 passed and 5 failed — the five `test_status` cases this pass's ledger
  then answered (the same 23,921). `make bench` rc 0 on this tree: the fix pass's table plus 134 lines, none of its
  own changed (1,990 → 2,011 rows), byte-identical to step T's final table. The full `make gates` of this state
  is the orchestrator's.
- Re-summed by THE FIX PASS of band 4 wave 3's review (gate 12, 2026-10-08): **23,579 passed / 2 skipped / 0
  xfailed**, twice in one `make gates` from an empty build/ (`make test` and `make guarded`, side by side: 346 s
  and 347 s of wall under a load of 30–40 — no timing to quote from it) — +106 against the docs pass below (23,473):
  `test_aes_evlib_woken.py` 186 → 227, `test_aes_evmulti.py` 578 → 600, `test_aes_switching.py` 55 → 67, the
  registrar's 11 → 22, `test_status.py` 10 → 12, `test_tier3.py`, `test_aes_event.py`. `make bench` rc 0: the
  foundation's table plus 536 lines, none of its own changed (1,907 → 1,990 rows).
- Re-summed by THE DOCS PASS of band 4 wave 3's slices W / M / U (2026-10-08): **23,473 passed / 2 skipped / 0
  xfailed** on a bare `pytest -n auto` over the merged tree — 297 s / 1,049 CPU-s user, NO TIMING TO QUOTE: the
  load was 69 at its start and 133 at its end (three review finders at work) and the derivation cache was cold for
  this tree (`names.txt`, one of its inputs, had just been edited). +645 against the foundation's fix pass below
  (22,828): `test_aes_evlib_woken.py` new (186), `test_aes_evmulti.py` 365 → 578, the door users' batteries,
  `test_aes_event.py`, `test_tier3.py`, the registrar's 3 → 11. `make bench` rc 0 on this tree: the table the
  foundation's plus 504 lines, none of its own changed (1,907 → 1,985 rows). TWO EARLIER RUNS OF THE PASS, said so
  the number is not read as three greens: the first, before the ledger was written, 23,471 passed and
  `test_status`'s 2 red (the rows and pairs this pass then wrote); the second 70 red, ALL in `test_derived.py` —
  `names.txt` edited under the run, the cache out of use for those workers by its own rule. The full `make gates`
  of this state is the orchestrator's.
- Re-summed by THE REVIEW'S FIX PASS of band 4 wave 3's foundation (2026-10-08): **22,828 passed / 2 skipped / 0
  xfailed** on a bare `pytest -n auto` over the built tree (169 s, the tree just edited: a cold collection) — +14
  against the foundation's 22,814 below: `test_aes_switching.py` 40 → 53, one case of the census in
  `test_aes_event.py`. `make bench` rc 0, the table BYTE-IDENTICAL to the foundation's, the host library and both
  blobs' `bench.bin` unchanged. The full `make gates` of this state is the orchestrator's.
- Re-summed by BAND 4 WAVE 3's FOUNDATION (a row that really switches, 2026-10-08) from its own `make gates` FROM
  AN EMPTY `build/` (the old one moved aside; the snapshot captured again, the derivation cache cold; 11:21 → 11:28,
  401 s and 3,067 CPU-s; made a second time after the last edit, 11:36 → 11:43, 401 s and 3,061 CPU-s, the same
  counts): **test 22,814 passed / 2 skipped / 0 xfailed, guarded the same** (29,269 candidate runs guarded, 29,267
  the second time), the ROM build rc 0 (sha256 1d736545…, unchanged),
  `make gates` rc 0, `make bench` 0 OVER / 0 DRIFTED — the table's every earlier line unchanged over the new capture,
  22 lines added (four rows of `ev_block` and what is printed under them). 22,814 passed then: **+50** against the
  cleanup pass's 22,764: `test_aes_switching.py` 40, `test_aes_switching_registrar.py` 3, and the four new rows' cases in
  `test_tier3.py` and the sweeps (the one row that was registered unpriced is priced: no count moved for it). NO
  OBJECT MOVED: the host library, `bench.bin`, the shipped blob's `bench.bin` and `bench.elf` byte-identical to the
  build moved aside (the bench blob's `bench.elf` differs in the compiler's temporary object names alone — 24 bytes
  one build, 23 the next — its sections, symbols and disassembly identical). Bare warm `pytest -n auto`, one sample each side: 141.8 s / 1,226
  CPU-s before (22,764), 142.2 s / 1,251 CPU-s after (22,814).
- Re-summed by THE CLEANUP PASS BEFORE WAVE 3 (the ROM-served door road retired, 2026-10-08) from its own `make
  gates` FROM AN EMPTY `build/` (the old one moved aside; the snapshot captured again, the derivation cache cold;
  08:58 → 09:05): **test 22,758 passed / 2 skipped / 0 xfailed, guarded the same** (29,227 candidate runs guarded),
  the ROM build rc 0 (sha256 1d736545…, unchanged), `make gates` rc 0, `make bench` 0 OVER / 0 DRIFTED, the table
  byte-identical to wave 18's. +4 passed and −3 skipped against wave 18's 22,754 / 5. REMOVED, five: the three
  cases of the served road that skipped by derivation (`test_aes_event.py::test_the_door_s_writes_are_compared`,
  `::test_an_entry_left_to_a_twin_its_wrapper_does_not_call_halts_by_name`,
  `test_tier3.py::test_the_door_rule_refuses_rom_aes_code_run_outside_a_window`) and two that pinned a served
  window's values (`test_tier3.py::test_the_door_rule_holds_the_two_sides_windows_equal`,
  `::test_a_call_s_kind_is_what_the_watch_saw_not_a_window_that_came_out_empty`) — the pass's entry says where each
  guard lives now. ADDED, six: `test_a_hook_that_answers_another_word_than_arrived_halts_by_name`, the census's
  `[ev_multi]` layer, `test_a_call_closed_at_no_rebound_entry_is_refused_by_name`,
  `test_a_row_whose_run_enters_the_aes_s_rom_outside_any_door_call_is_refused_by_name`,
  `test_the_door_users_rows_that_settle_more_than_the_mask_word_are_the_census_s`, and a second blob's case of
  `test_no_jsr_of_the_build_enters_the_aes_s_text_and_the_door_s_users_arrive_at_twins` (once
  `test_the_door_calls_are_the_door_s_entries_and_their_users_the_aes_s`). Eight more renamed for what they hold
  now (a window's name out of each). NOT A TIMING: 397 s, 3,052 CPU-s, the 1-minute load 10 → 125.
  THEN THE REVIEW'S FIXES, re-summed from a bare `pytest -n auto` (not a gate: the orchestrator's follows):
  **22,764 passed / 2 skipped**, +6 — `test_the_door_rule_holds_the_two_sides_calls_equal_by_entry_and_in_order`
  (the calls closed on each shore, held by name beside the frames), pytest's own outcomes raised inside a hook
  (an xfail beside the skip and `pytest.exit` beside what stops the session in `test_address_hook`, +2; a skip, an
  xfail and an exit through the scheduler's binding, +3); `make bench` rc 0, the table's legend line the one line
  moved.
- Re-summed by WAVE 18's FIX PASS (the interrupt handlers as the ROM's instructions, 2026-10-08) from its own `make
  gates` FROM AN EMPTY `build/` (the old one moved aside; the snapshot captured again, the derivation cache cold;
  ended 03:00): **test 22,754 passed / 5 skipped / 0 xfailed, guarded the same** (29,264 candidate runs guarded),
  the ROM build rc 0 (sha256 1d736545…, unchanged: it links no handler), `make gates` rc 0, `make bench` 0 OVER / 0
  DRIFTED. +30 over FLIP 3's 22,724: the four xfails now passing, and 26 tests added — 9 keeps-no-register cases of
  the blank (3 on the ROM, 6 on the blobs), 2 of the ROM-made machine's, 7 of timer C's entry (6 on the blobs, 1
  premise), 5 more pinned regions (four of the blank's, the queue-a-key routine), the blank's relocation
  declarations, and the floppy's gate on both blobs (2). No test deleted; the pinned-numbers test renamed
  (`test_our_own_handlers_need_what_the_rom_s_do_and_leave_what_status_says`). The first attempt of this run ended
  at the snapshot's capture (Hatari stopped at PC $cc3a, not at the blank's vector: before any of the tree's code
  ran) and was repeated from empty. NOT A TIMING: the machine loaded throughout (1-minute load 133 at its end). The
  table: 1,903 rows, ten moved against FLIP 3's, none added or removed; 56 rows `accepted` for 63. (The wave's first
  gates, before the fix pass: 22,750 passed, 29,275 guarded.)
- Re-summed by FLIP 3 (band 4 wave 2, 2026-10-08) from its own `make gates` FROM AN EMPTY `build/` (the snapshot
  captured again, the derivation cache cold; 00:12 → 00:19): **test 22,724 passed / 5 skipped / 4 xfailed, guarded
  the same** (29,268 candidate runs guarded), the ROM build rc 0 (sha256 1d736545…, unchanged), `make gates` rc 0,
  `test_status` GREEN in both suites. −2 against the gate-fix pass's 22,726: three tests moved from passed to skipped
  by derivation (no entry is ROM-served), one added (`test_status`'s pin of the door's state). No test edited or
  deleted. NOT A TIMING: 399 s, 3,047 CPU-s, the machine loaded throughout (1-minute load 56 → 122). The table: 1,903
  rows, the same nine verdict counts, **98 rows moved by the flip, none added or removed**, 3,311 lines (22 more
  `TWO COUNTS` lines); 185 rows carry the two counts.
- Re-summed by THE GATE'S FIX PASS (2026-10-07) from its own `make gates` on the shared tree FROM AN EMPTY `build/`
  (the pinned snapshot kept; the derivation cache cold; 23:16 → 23:25): **test 22,726 passed / 2 skipped / 4 xfailed,
  guarded the same** (29,270 candidate runs guarded), the ROM build rc 0 (sha256 1d736545…: HEAD's own image), `make
  gates` rc 0, `test_status` GREEN in both suites — +45 over the docs pass's 22,681: the gate's own REDs (the stack
  reader's shapes, the glue vet's refusals, the un-applied relocation, the caller's thunks and pins, the two counts'
  pins in `test_status.py`, a half word, the hook's outcomes, the lazy cache's shape, the declared child doors, the
  claim's rests, the source's first symbol). All 139 shipped objects and both blobs byte-identical to the tree the
  docs pass gated; the table's measured lines equal, 163 `TWO COUNTS` lines and one legend sentence added. NOT A
  TIMING: 552 s and 2,984 CPU-s with a mutation sweep beside it (1-minute load 35 at its start, 122 at its end).
- Re-summed by the band 4 wave 2 phase A DOCS PASS (2026-10-07) from its own `make gates` on the shared tree with this
  ledger's rows in (20:43 → 20:55; the libraries, blobs, table and derivations as the fix pass's final gate had just
  made them — "derived: made already for this tree" — nothing removed first): **test 22,681 passed / 2 skipped,
  guarded 22,681 passed / 2 skipped** (29,172 candidate runs guarded), the ROM build rc 0 (sha256 1d736545…: HEAD's
  own image), `make gates` rc 0, `test_status` GREEN in both suites. That is the fix pass's 22,680 and its one red —
  `test_status`'s 14 addresses with no row — now passing. +815 over FLIP 2's 21,866: ev_multi's battery 365, the
  dispatcher's five 244, the rest, net, 206 (the machinery's own tests: Tier 3, the event door, the derivation cache
  and its claim, the zygote, the hook — less the few the wave renamed or retired with their code, which were not
  re-tallied id by id on the final tree). THE TABLE the
  gate read is byte-identical to the fix pass's final one (3,126 lines). NOT A TIMING: the machine was loaded by the
  reviewers' own runs throughout (1-minute load 71 at the start, 221 at the end; pytest's wall 735 / 746 s side by
  side, 755 s whole).
- AND AGAIN, `make test` on the final docs tree (21:02 → 21:12, rc 0): **22,681 passed / 2 skipped**, `test_status`
  green — run because `names.txt`, which the kit's harness reads and the derivation cache keys, was edited by this
  pass WHILE the gates above were running (their workers had loaded the file as it was, and the edit put the cache out
  of use for them): this second run began after the last edit of it, the derivations made again for the new tree
  ("derived: made, over 10 processes"). Loaded too (150 → 173): 588 s is not a timing.
- WALL TIME, QUIET — the fix pass's figures (step 2's agent alone on the machine, every run started quiet, the loads
  the suite's own), pytest's own wall under `-n auto` (10 workers): **209 s and 1,560 CPU-s for a bare cold `pytest`**
  (the derivation cache emptied first), **146 s and 1,288 CPU-s warm**; before the kit read images in place and the
  zygote's lazy-cache fix, the same tree but those: 231 s / 1,778 CPU-s and 170 s / 1,492 CPU-s. `make gates` from an
  EMPTY `build/` on the shared tree: **375 s, 2,985 CPU-s** (load 7.5 at its start). FLIP 2's figures for 21,866 tests
  were 210.3 s cold and 155.3 s warm (1,857 / 1,362 CPU-s): 815 more tests, and the suite is cheaper warm and cold.
  THE 200 s LINE is held warm; a bare cold `pytest` is 9 s over it.
- `make bench` judges **1,903 rows**: 821 ok / 425 net / 297 through / 220 transcribed / 63 accepted / 31 glue / 24
  own / 13 pinned / 9 rule, none OVER or DRIFTED (counted from `build/bench/tier3.txt`, 3,311 lines since FLIP 3). **READ WITH THE
  KNOWN PRICING GAP under the Components table**: ten AES rows and nine of the VDI / GEMDOS counted here as within the
  bar (`ok`, `net`, `through` or `pinned`) are over it on their OWN cycles behind an OS trap the net-pricing
  classifier does not see — the user's ruling pending, nothing accepted.
- The AES has 1,079 of them: 425 net / 336 ok (the 104 `.S` rows included) / 202 through / 97 transcribed / 17 glue /
  2 accepted. 185 carry the two counts of a row that calls a rebound entry (163 before FLIP 3; the section intro of
  `## Verified — aes`).
- The wave added 52 rows (ev_multi's 26, all `net`; the dispatcher's 26: 12 `.S` at 1.00, 3 ok, 5 net, 6 through).
  Against FLIP 2's table: **0 rows removed, 52 added, 4 moved in their verdict tag alone** (blank → `net`: ev_mwait
  ×1, unsync ×3, the same cycles and ratios), 157 rows' sub-lines changed (the second count printed; nine "dropped"
  lines gone) — NO RATIO OF A COMMITTED ROW MOVED (nothing is flipped). FLIP 3 then moved 98, the rehearsal's.
- THE KIT CHANGED (its own commit: an equal 64 KB chunk of two images found by one `memcmp` in place; the candidate's
  image read where it lies instead of copied): kit **1,236 passed** (1,222 + 14; this pass's own run from the
  repository's `tools/recreate_kit`, 46 s at load 190). The kit's suite and the six other projects' suites were run
  SIDE BY SIDE on HEAD's kit and on the new one by the fix pass (2026-10-07), each unchanged test for test at its
  carried count: Zynaps 4,751 passed / 4 skipped, BuggyBoy 296, Joust 4,368, Flying Shark 3,851, Bubble Ghost 1,909,
  Wonder Boy 6,465. (One kit test reds in any COPY of the kit under `/private/tmp`, at HEAD too — it depends on where
  `$TMPDIR` lies; green from the repository.)
- `names.txt`: 937 fn / 556 var / 494 cmt (+8 / +3 / +14; ONE `cmt` replaced in place — ev_multi's, merged with what
  the old one said that is still true — and six `# ctx` tags dropped from names whose bodies this wave read: the three
  interrupt glues, `pr_button`, `pr_mclick`, `mclick`; one `cmt` per address, no name twice, checked over the whole
  file). `reapply.sh` was NOT run by the docs pass (it rewrites `decomp.c` and the Ghidra project): run it before the
  next naming pass.
- EARLIER RE-SUMS, kept as the record of their waves (their counts and walls are theirs):
- Re-summed by FLIP 2 (band 4 wave 1 phase B, 2026-10-07) from its own `make gates`, cold from `rm build/*.so` and
  an empty derivation cache: test **21,866 passed** / 2 skipped, guarded **21,866 passed** / 2 skipped, the table
  written (rc 0), the ROM build rc 0 — phase A's count (the flip adds, removes and edits no test).
  Pytest's own wall, quiet, one sample: 210.3 s bare cold, 173.9 s inside a cold `make test`, 155.3 s warm (the
  same day before the flip: 208.7 / 170.2 / 151.5 — phase A's figures below, re-measured). `make gates` cold 393 s.
  The table: 1,851 rows, the same nine verdict counts as below, **137 rows moved by the flip, none added or removed**.
- Re-summed by the AES band 4 wave 1 phase A GATE-FIX PASS on 2026-10-07 from its own runs of the final tree, each
  from `rm build/*.so` and an empty derivation cache: the four in turn (`make test`, `make guarded`, `make bench`,
  `make -C atari -B all` — every one rc 0) and `make gates` cold and again warm. SIX RUNS OF THE SUITE — the two of
  the serial sequence, the two of `make gates`, a bare cold `pytest` and a warm one — collected the SAME ids with
  the same outcomes (0 added, 0 removed, 0 changed between any two); two tests the mutation sweep then asked for
  were added, and `make gates` (cold, from `rm build/*.so`) and a warm bare `pytest` run AGAIN on that tree: 21,868
  ids, the six runs' and those two, 0 outcomes changed — and `make test` once more, cold from `rm build/*.so`, after
  one of the two was made independent of the test before it (it failed ALONE): the same ids and outcomes. +68 over the docs pass's 21,798 (the cache's and the pool's
  tests 26, the instruction pin 28, the others 14), none removed; +2,591 over band 4 wave 0's 19,275.
- `make guarded`: **21,866 passed**, 2 skipped, 0 failed. `make -C atari -B all`: rc 0.
- WALL TIME, QUIET (the pass was alone on the machine; every timed run started at a 1-minute load under 4), pytest's
  own wall under `-n auto` (10 workers): **151.3 s warm; 170.8 s as a cold `make test` runs it** (the derivations
  made first by `make derived`); **207.4 s for a bare cold `pytest`** with nothing made. Before this pass: 166.2 /
  183.6 / 212.2 s; the tree before the speed work: 223.3 s; HEAD (band 4 wave 0): 197–201 s. THE 200 s LINE IS HELD
  warm and through the makefile; a bare cold `pytest` is not under it. `make test` whole, from `rm build/*.so` and an
  empty cache: 226 s (241 s before this pass, ≈ 381 s before the speed work); `make guarded` right after: 159 s;
  `make gates` 388 s cold, 309 s warm (417 / 364 s; the four in turn: 389 s; ≈ 592 s before the levers).
