# How much of Wonder Boy is behind the wall the differential cannot see?

`STATUS.md`'s blocker 2 says the game's I/O is all direct hardware, that the oracle models almost
none of it, and that **how much of the game sits behind that wall had not been measured.** This is
the measurement.

> ## The answer
>
> **Measured over the 47 % of the game's code Ghidra has recovered so far, the gameplay logic is
> portable today. The wall is a boot-time, disk-time and sound-time problem — but the gameplay code
> is also the part this measurement covers least.**
>
> Ghidra has recovered 252 functions / **25,696 of the ~54,854 bytes** `notes/architecture.md`
> calls CODE. Everything below is a statement about those 25,696 bytes and nothing else. Of the
> 114 game-logic functions (9,596 B) inside them, 112 touch no hardware — the two exceptions are
> the game's PRNGs, which seed from the video address counter. Transitively **104 of them
> (7,638 B) run end-to-end under the oracle: 79.6 % of what is measured, but 22.1 % of the 34,496
> bytes of game-logic code believed to exist.** Only 3 of them (372 B) carry any false-green risk,
> and both blit families (16 background-scroll routines, 12 sprite blitters) and the RAD depacker
> are completely clean.
>
> **21,534 bytes are runnable end-to-end: 83.8 % of what is measured, 39.3 % of the program's
> believed code.** Of the rest, 4,162 bytes are measured and blocked (T4/T5), and **29,158 bytes
> are in no tier at all** because they are in no function body — mostly leaf routines reached only
> through pointer tables (§8.1). What *is* measured and cannot be verified is concentrated in four
> places: the **WD1772/DMA floppy driver**, the **YM2149 replay path**, the **Copylock**, and the
> **boot chain** that calls all three.
>
> **And "runnable" is no longer the strongest thing this report can say.** 105 of the 252 functions
> / **10,376 bytes are reconstructed and green** against the oracle — 40.4 % of what is measured,
> 18.9 % of believed code, and 48.2 % of everything the harness can run at all. That is the
> right-hand column below, and it is concentrated in four subsystems.
>
> But three of the four unverifiable places are measured *better* than the gameplay code the report
> calls portable — only the Copylock, which cannot be read at all by construction, is measured worse:

| subsystem | CODE bytes | in a function | coverage | reconstructed & green |
|---|---:|---:|---:|---:|
| **game logic** (the catch-all bucket) | **34,496** | **9,596** | **27.8 %** | **2,986 B** (61 fns) |
| video (background scroll) | 6,234 | 6,140 | 98.5 % | **6,140 B** (33 fns) |
| sound (YM2149) | 3,824 | 2,634 | 68.9 % | 0 |
| video (sprite blitters) | 2,254 | 2,254 | 100.0 % | 0 |
| copylock (protection) | 2,236 | 232 | 10.4 % | 0 |
| boot | 2,114 | 1,184 | 56.0 % | 0 |
| disk (FAT12 + file load) | 1,028 | 1,030 | 100.2 % | 0 |
| disk (WD1772 FDC + DMA) | 686 | 684 | 99.7 % | 0 |
| text (message box) | 678 | 678 | 100.0 % | **678 B** (3 fns) |
| actor (table + projection) | 356 | 356 | 100.0 % | **356 B** (5 fns) |
| input (IKBD / ACIA) | 312 | 300 | 96.2 % | 0 |
| video (screen / palette / mode) | 240 | 236 | 98.3 % | 0 |
| resource depack (RAD) | 220 | 216 | 98.2 % | **216 B** (3 fns) |
| resource loader | 114 | 104 | 91.2 % | 0 |
| interrupt (VBL) | 62 | 52 | 83.9 % | 0 |
| **TOTAL** | **54,854** | **25,696** | **46.8 %** | **10,376 B** (105 fns) |

Read that table before any percentage below it. It is the only table here not produced by
`hw_portability.py`; it is the intersection of four files, and each column says which:
**`CODE bytes`** = every address `notes/architecture.md`'s region table calls CODE, charged to the
first `subsystems.tsv` range that claims it (so it sums to that table's own 54,854 total);
**`in a function`** = the `F` records of `out/hw_scan.tsv`, by function ENTRY address, which is
exactly the denominator `hw_portability.py` uses and therefore what every tier below is out of;
**`reconstructed & green`** = the `F` records whose function has a **verified** row in
`STATUS.md`'s table, i.e. ported to C and pinned by a differential under `make test`.
The first two columns are measured differently and do not have to agree: a function body may run a
few bytes past a region boundary (which is why the FAT12 row reads 100.2 %), and a whole subsystem
may sit mostly outside every function body (`game logic`, `boot`).

**The verified column counts F records, and `STATUS.md` counts reconstructions — which is why it
says 103 and this says 105.** The difference is the RAD depacker: `src/rad.c` is one reconstruction
of what Ghidra splits into three functions (`rad_depack`, `rad_refill_bit_buffer`, `rad_get_bits`,
216 B between them). Same code, two counting rules; this file uses the scan's, because the scan is
what every other column here is out of.

**"Game logic" is `subsystems.tsv`'s last row, `0x0–0x21810` — the catch-all.** It is not a
positive classification; it is everything the specific ranges above it did not claim. So it is at
once the biggest bucket, the least characterised one, and the one this measurement covers worst
apart from the Copylock, which cannot be read at all by construction.

## Reproducing it

```bash
bash projects/wonderboy/reapply.sh            # ← NOT OPTIONAL, see below
bash tools/hw_scan.sh projects/wonderboy/ghidra_proj wonderboy SWB.PRG \
     projects/wonderboy/out/hw_scan.tsv 0x100000
python3 tools/hw_portability.py projects/wonderboy/out/hw_scan.tsv \
        --exclude 0xed8e:0xf540:"Copylock ciphertext" --root 0x4a0 --root 0x400 \
        --subsystems projects/wonderboy/recreate/subsystems.tsv
python3 projects/wonderboy/notes/portability_predictions.py    # 14 cases, must be green
make -C projects/wonderboy/recreate test                       # 77 cases, must be green
```

Add `--stub 0xecca` (and `--model psg:read` for the pair) to reproduce §6.1's numbers.

**`reapply.sh` is part of the measurement, not setup.** Ghidra does not reach the background
scroll blitter (`$83b6..$8dfe`, 16 functions) or `rng_1_to_4_masked` (`$51ac`) on its own — nothing
it disassembled calls them — so `ApplyNames` creating them from `../names.txt` is what puts 2,676
of the 25,696 measured bytes and 2 of the 31 hardware reads into the scan at all (§8.1). Skip it and
you get ~235 functions and every table below is wrong. And if you re-bootstrap with `run.sh` first,
`reapply.sh` is mandatory afterwards: `run.sh` re-imports and **wipes every name**.

Both tools are game-agnostic and live in `tools/`. `hw_portability.py` also takes `--stub ADDR`
and `--model BLOCK:read|write`, which is how the capability table in §6 is priced. The one table
it does not produce is the coverage table in the answer box — see the note under it.

> ### READ THIS FIRST IF YOU ARE RE-RUNNING IT: the Ghidra DB was wrong
>
> `tools/ghidra_scripts/PrgLoader.java` mis-parsed the DRI relocation table: the byte `1` means
> *advance the cursor 254 bytes and fix up nothing*, and the loader was fixing up a longword
> there anyway. For `SWB.PRG` that is **536 spurious relocations against 3 real ones** — one
> corrupted longword every 254 bytes from `$4fa` to `$217cc`.
>
> It changed the answer, in both directions. `$f90c` really is `move.b #$7,$ff8201` (a screen-base
> write); the corrupt DB read it as `$04f78201` and the site vanished. `$613e` really is
> `move.b $ff860d,d7`; the corrupt DB read it as `$ff8a05` and **invented a blitter reference in a
> game that has no blitter**. `$6154`'s word-sized `move.w #$190,$ff8606` and `$6f8`'s palette
> write were missing entirely, `$633c`'s `btst #5` had become `btst #-3`, and four in-image
> addresses had been pushed above `image_size` into fake "hardware".
>
> The fix is in, and `docs/ghidra-pipeline.md` now carries the re-bootstrap notice for every
> project. **Every project's DB was built with the broken loader and is stale**: BuggyBoy has 93
> spurious fixups, Joust 44. Their reconstructions are unaffected — `oracle/loader.py` uses
> `prg_dis.parse_reloc`, which was always right — but their `decomp.c` and Ghidra DBs are not.
> `ghidra_proj/` and `decomp.c` are gitignored, so re-bootstrapping costs nothing but time:
> `bash projects/<name>/run.sh` then `bash projects/<name>/reapply.sh`.
>
> **The numbers below come from a clean DB built with the fixed loader.** If
> `projects/wonderboy/ghidra_proj/` has not been re-bootstrapped since, run `run.sh` **and then
> `reapply.sh`** before reproducing them — `run.sh` alone leaves a DB with no names in it, which
> is 17 functions and 2,676 bytes short of what is measured here.

---

## 0. Re-measured 2026-08-02 — the game-logic/video boundary was wrong

The original measurement (2026-08-01) is unchanged in method; what changed is `subsystems.tsv`.
**Nothing about the program moved, and no tier moved.** A subsystem partition is a relabelling of
the same 252 functions, so every whole-program figure in §3, §5 and §6 is byte-identical before and
after — the two reports differ in exactly four rows of the subsystem table (checked by diffing
them). What moved is *which bucket the measured bytes are charged to*, and that is what the
headline claims about "game logic" rest on.

**The trigger.** Reconstruction batches 5–7 established that `$7522..$8228` — fifteen routines the
catch-all filed as "game logic" — is the background scroll **engine** that fills the eight
pre-shifted buffers, and that `subsystems.tsv`'s `video (background scroll)` range
(`$82f8..$8dfe`) is the **consumer** that copies one of them to the screen. Producer and consumer
are one subsystem; the boundary ran through its middle. Batches 8–9 then established two more
coherent subsystems inside the same catch-all: the actor table and its projection passes, and the
message-box text subsystem.

**What moved, and on what evidence** (each range is cited in `subsystems.tsv` itself):

| range | from | to | evidence |
|---|---|---|---|
| `$7522..$8228` (15 fns, 3,320 B) | game logic | video (background scroll) | batches 5–6: the queue drain, four axis steps, two row fills and the pre-shift, all reconstructed and green |
| `$d28..$d76` (1 fn, 78 B) | game logic | video (background scroll) | batch 5: the request raiser that drives the queue |
| `$67c2..$6822` (3 fns, 96 B) | game logic | actor (table + projection) | batch 8: the entry tier over the three parallel 19×32-byte actor tables |
| `$8dfe..$8f02` (2 fns, 260 B) | game logic | actor (table + projection) | batch 8: the two projection passes, which share 68 identical bytes |
| `$bd8a..$c030` (3 fns, 678 B) | game logic | text (message box) | batches 8–9: the lifecycle plus the plotter's two entry points, tiling the range exactly, and `$c030` is `notes/architecture.md`'s own CODE/DATA boundary |

**The `$a09c` message-pointer table is deliberately NOT in `subsystems.tsv`.** A range there is
matched against a function ENTRY address, and that table is data — inside `architecture.md`'s DATA
row `$989c..$a271`. Adding it would change no number in this file and would imply the partition
covers data, which it does not. Same for the actor tables at `$996c`/`$9bd0`/`$9e34`.

**Before → after:**

| subsystem | fns | measured B | CODE B | coverage | runnable |
|---|---|---|---|---|---|
| game logic | 138 → **114** | 14,028 → **9,596** | 38,942 → **34,496** | 36.0 % → **27.8 %** | 128 / 12,070 B → **104 / 7,638 B** |
| video (background scroll) | 17 → **33** | 2,742 → **6,140** | 2,822 → **6,234** | 97.2 % → **98.5 %** | 17 / 2,742 B → **33 / 6,140 B** |
| text (message box) | — → **3** | — → **678** | — → **678** | — → **100.0 %** | — → **3 / 678 B** |
| actor (table + projection) | — → **5** | — → **356** | — → **356** | — → **100.0 %** | — → **5 / 356 B** |

**The catch-all got WORSE, and that is the result.** The obvious expectation is that carving three
characterised subsystems out of "game logic" leaves a smaller but better-understood remainder. It
does the opposite: game logic loses 4,432 *measured* bytes and only 14 unmeasured ones, so its
coverage falls from 36.0 % to **27.8 %** and the CODE it holds outside every function body is
24,900 bytes — **72.2 %** of it, up from 64 %. What the catch-all was hiding was not confusion, it
was three subsystems that happened to be the best-measured code in it. The wall §8.1 describes is
now the *dominant* fact about the bucket, not a caveat on it.

**Two limitations of this re-measure, stated with it:**

* **The Ghidra DB is stale relative to `../names.txt`** — batches 5–9's names, `cmt`s and `proto`s
  have not been through `reapply.sh`, and the DB itself still wants the re-bootstrap the box above
  describes. So `out/hw_scan.tsv` calls `$7522` `FUN_00007522`. **It does not affect a single
  figure here**, and that was checked rather than assumed: every `fn` address in `names.txt` (171
  of them) is already an `F` record in the scan, so naming since the scan created no function body
  the scan lacks, and every column here is keyed on addresses and body extents, not names. A
  re-scan would change only the name strings.
* **The unmeasured bulk is unchanged.** 29,158 bytes are still in no function and so in no tier;
  24,900 of them are now charged to game logic. Nothing in this re-measure reaches them.

Confirmed by reading it, and then by running code through it (§4):

| tier | what the shim does | consequence |
|---|---|---|
| **modeled** | byte write to `$ff8800`/`$ff8802` → ordered `(reg, val)` ledger | diffable |
| **hard reject** | ANY read of `$ff8800..$ff88ff` at any width; any 16/32-bit access to the block; a byte write to the odd aliases | `emu.run` raises; the run cannot complete |
| **silent zero** | every other off-image read returns `0`, tallied by nothing | **both sides get the same wrong value: the diff is clean and proves nothing** |
| **silent drop** | every other off-image write is discarded, logged nowhere | the hardware effect is invisible |

Two details of that table are load-bearing and easy to get wrong:

* **The one exception to "silent zero"** is `IKBD_STATUS` (`$fffc00`), answered `IKBD_TX_RDY`. It
  is live in this game — §4 shows `ikbd_disable_mouse` exiting its transmit-ready poll because of
  it. It is still a fabricated constant, so it is still a T3 read.
* **The hard-reject test is on the whole transfer, not its first byte** (`psg_block_touched(a, n)`),
  so a longword read straddling into `$ff8800` from below is refused too. `hw_portability.py`
  mirrors that, and re-reads shim.c's own `#define`s on every run (`check_shim_agreement`) so the
  two cannot drift apart silently.

The mixed-path guard (`osh_psg_mixed_paths`, direct PSG + XBIOS `Giaccess` in one run) is
**inert here** as expected: the image contains one trap instruction and it is a `Super`, so there
is no XBIOS call anywhere to arm it.

## 2. Method, and what it can and cannot see

`tools/ghidra_scripts/HwPortabilityScan.java` reads Ghidra's **reference model**, not a linear
sweep. That choice is load-bearing twice over:

* a sweep desyncs on data and silently drops the instructions after it (`docs/m68k-disassembly.md`);
* Ghidra's constant propagation already resolves `lea $ff8240,a0` + `clr.l (a0)+` to `$ff8240`,
  which is exactly the register-indirect idiom hand-written assembly uses. **18 of the 126 hardware
  accesses in this game are register-indirect and invisible to any operand scan** — the 8-longword
  palette clear in `clear_palette`, the 8-longword `set_palette`, and the IKBD ACIA pair reached
  through `lea $fc00.w,a1`.

Read/write direction and access size come from the reference type and the pcode, not from a
"which side of the comma" heuristic. A **read-modify-write** (`bclr #6,$fffa11`, the standard MFP
interrupt acknowledge) is one Ghidra reference typed `READ_WRITE` and two accesses to the oracle —
a read it answers 0 and a write it drops — so it is counted as both. That is why 120 instructions
produce 126 access records.

Whether a read steers a branch comes from a pcode taint walk from the read to the first conditional
branch that consumes it. The walk **stops at a `bsr`/`jsr`**: this is hand-written assembly with no
register-save convention to lean on, so stepping over a call would carry the callee's clobbered
registers forward. That is not hypothetical — before the walk stopped at calls it reported three
false STEERs in `FUN_00006118`, whose DMA-counter reads feed `add.l d7,d1 / move.l d1,$6508`
(stored, never branched on *inside that function*) while the branch 80 bytes later tests a `d7`
that `bsr fdc_wait_irq_bounded` had just overwritten. The price of that conservatism is §8.5: the
walk misses the real steers that cross a call or a memory round-trip, and two of them are known.

### Site census

| block | sites | READ | WRITE | absolute | register-indirect |
|---|---:|---:|---:|---:|---:|
| PSG `$ff88xx` | 35 | 3 | 32 | 35 | 0 |
| shifter `$ff82xx` | 34 | 4 | 30 | 18 | 16 |
| FDC/DMA `$ff86xx` | 32 | 10 | 22 | 32 | 0 |
| MFP `$fffaxx` | 20 | 10 | 10 | 20 | 0 |
| ACIA `$fffcxx` | 5 | 4 | 1 | 3 | 2 |
| **total** | **126** | **31** | **95** | **108** | **18** |

The game uses **absolute long** (`$00ff8800.l`) almost throughout: of the 102 absolute-addressed
instructions, **93 are `abs.l` and 9 are `abs.w`** — six `bclr #6,$fffa11.w` and three
`move.b $fffc02.w,d1`. The scanner handles both, plus the 18 register-indirect sites.

### Reconciliation with an independent linear sweep

Cross-checked site by site against a linear sweep of `out/wonderboy_dis.txt`. Every difference is
accounted for:

* **Sites Ghidra has and the sweep does not** — the 18 register-indirect ones, plus one garbage
  "access" decoded out of the Copylock ciphertext at `$ed90` (excluded here).
* **Sites the sweep has and Ghidra did not** — three are `lea`, which computes an address and does
  not access it; one is inside the ciphertext; and **two were real**: `$51ae` and `$51b6`, both
  reading the shifter's video address counter inside a routine Ghidra never disassembled because
  nothing it *had* disassembled reaches it. Rather than carry those two in a hand-maintained side
  list, the routine is now named (`fn 0x51ac rng_1_to_4_masked` in `../names.txt`), which makes
  `ApplyNames` disassemble it — so the scanner sees both sites through its normal path and the
  tool's `--extra-hw` escape hatch is unused by this project.

**Two corrections to an independently-supplied sweep tally** (shifter 59 / MFP 19), both from the
same cause: `prg_dis` prints an `abs.l` operand as its raw value, so `$8234.l` is the **in-image**
address `$00008234`, not `$ffff8234`. Sign-extending it as if it were `abs.w` promotes ~39 ordinary
in-image variable accesses (`$8228`–`$8234`, `$8276`) into fake shifter hits and 5 `$fa2e.l`
accesses into fake MFP hits. Corrected, the sweep and Ghidra agree.

The **three PSG read sites** in that tally are **confirmed exactly**: `$6254`, `$17f08`, `$17f3e`,
and nothing else. All PSG traffic in the image is byte-sized on the two canonical ports — no
word/long access, no odd alias — so those three reads are the *entire* T4 surface.

## 3. The measurement

252 functions, 25,696 bytes of function body, 27,986 bytes of disassembled code. **Every
percentage in this section is out of those 25,696 bytes, i.e. out of 46.8 % of the program's
believed code** — see the coverage table in the answer box.

### Direct tier — what each function itself touches

| tier | functions | % | bytes | % |
|---|---:|---:|---:|---:|
| T0 CLEAN | 221 | 87.7 % | 22,496 | 87.5 % |
| T1 PSG_WRITE_ONLY | **0** | 0 % | **0** | 0 % |
| T2 HW_WRITE_ONLY | 14 | 5.6 % | 1,290 | 5.0 % |
| T3 HW_READ | 12 | 4.8 % | 912 | 3.5 % |
| T4 HARD_REJECT | 3 | 1.2 % | 818 | 3.2 % |
| T5 UNMEASURABLE | 2 | 0.8 % | 180 | 0.7 % |

> **T1 is empty, and that is a finding.** The hope in the task framing — "the sound effects are
> verifiable via the PSG ledger" — does **not** hold for this game. All three functions that write
> the PSG (`psg_set_drive_select`, `snd_music_tick`, `FUN_00017f24`) also *read* it, for a
> read-modify-write of port A (drive select) or of register 7 (the mixer). Not one byte of this
> game's sound can be verified **through the ledger**. That is a statement about the ledger, not
> about the sound module: §7.4a shows part of the module is diffable today by other means.

### Transitive tier — worst tier anywhere in the callee subtree

| tier | functions | % | bytes | % |
|---|---:|---:|---:|---:|
| T0 CLEAN | 188 | 74.6 % | 19,304 | 75.1 % |
| T2 HW_WRITE_ONLY | 10 | 4.0 % | 282 | 1.1 % |
| T3 HW_READ | 22 | 8.7 % | 1,948 | 7.6 % |
| T4 HARD_REJECT | 18 | 7.1 % | 2,694 | 10.5 % |
| T5 UNMEASURABLE | 14 | 5.6 % | 1,468 | 5.7 % |

Restricted to the 140 functions reachable from `cold_start` (`$400`) and `game_main_loop`
(`$4a0`): T0 95 / 10,440 B · T2 9 / 274 B · T3 14 / 1,102 B · T4 12 / 1,874 B · T5 10 / 1,292 B.
That table alone is qualified by the 112 statically unreachable functions in §8.3; the two tier
tables above are **not**, because a tier is computed from a function's own callee subtree and never
from whether a root reaches it.

### The two decision numbers

* **Runnable end-to-end under the oracle** (no T4 and no T5 anywhere in the subtree):
  **220 / 252 functions, 21,534 / 25,696 bytes = 83.8 % of what is measured** — and 39.3 % of the
  54,854 bytes believed to be code.
* **At false-green risk** (a control-flow-steering T3 in the subtree):
  **28 / 252 functions, 3,348 / 25,696 bytes = 13.0 %.** A **lower** bound, twice over: §8.5's
  intra-procedural walk misses steers that cross a call, and §5 documents two it demonstrably
  missed here.

Both roots close to T5, for the same reason: `game_main_loop → FUN_0000053e →
show_data_disk_prompt → load_resource_by_index → copylock_entry`. That single edge is what makes
the *whole-program* number look bad; per-function it costs almost nothing (see §6).

### Subsystem partition

| subsystem | fns | bytes | direct worst | transitive worst | direct T0 | runnable | false-green |
|---|---:|---:|---|---|---|---|---|
| game logic | 114 | 9,596 | T3 | T5 | **112 / 9,444 B** | **104 / 7,638 B** | 3 / 372 B |
| video (background scroll) | 33 | 6,140 | **T0** | **T0** | **33 / 6,140 B** | **33 / 6,140 B** | 0 |
| sound (YM2149) | 21 | 2,634 | **T4** | **T4** | 19 / 1,844 B | 13 / 1,622 B | 2 / 710 B |
| video (sprite blitters) | 12 | 2,254 | **T0** | **T0** | **12 / 2,254 B** | **12 / 2,254 B** | 0 |
| boot | 12 | 1,184 | T3 | T5 | 8 / 460 B | 5 / 408 B | 8 / 798 B |
| disk (FAT12 + file load) | 11 | 1,030 | T3 | T3 | 10 / 870 B | 11 / 1,030 B | 6 / 630 B |
| disk (WD1772 FDC + DMA) | 20 | 684 | **T4** | **T4** | 8 / 82 B | 18 / 640 B | 6 / 468 B |
| text (message box) | 3 | 678 | **T0** | **T0** | **3 / 678 B** | **3 / 678 B** | 0 |
| actor (table + projection) | 5 | 356 | **T0** | **T0** | **5 / 356 B** | **5 / 356 B** | 0 |
| input (IKBD / ACIA) | 4 | 300 | T3 | T3 | 1 / 10 B | 4 / 300 B | 1 / 230 B |
| video (screen / palette / mode) | 8 | 236 | T2 | T2 | 4 / 38 B | 8 / 236 B | 0 |
| copylock (protection) | 4 | 232 | **T5** | **T5** | 2 / 52 B | 1 / 16 B | 1 / 36 B |
| resource depack (RAD) | 3 | 216 | **T0** | **T0** | **3 / 216 B** | **3 / 216 B** | 0 |
| resource loader | 1 | 104 | T2 | T5 | 0 | 0 | 1 / 104 B |
| interrupt (VBL) | 1 | 52 | T0 | **T4** | 1 / 52 B | 0 | 0 |

**Four of those rows are now 100 % reconstructed and green** — background scroll (33 fns, 6,140 B),
text (3, 678 B), actor (5, 356 B) and the RAD depacker (3, 216 B). Every one of them is T0 direct
*and* transitive, which is why they were reconstructable with no new harness capability at all: the
answer box's right-hand column is what the §7 recommendation turned into.

The two disk rows are the shape to notice. **The FDC driver runs almost entirely** — 18 of its 20
functions, and all 11 of the FAT12 layer's. Between them those two subsystems hold **12
false-green functions and 1,098 bytes** that a differential will happily call verified. What those
runs actually report is §4 and §7.4b: the polls succeed instantly, the commands built on them fail.

**So: yes, the gameplay logic is portable today — as far as it has been recovered.** The only
game-logic functions that touch hardware are the two PRNGs, `rng_next` (`$68c6`) and
`rng_1_to_4_masked` (`$51ac`), and both are T3-DATA reads, not steering ones. The **72.2 %** of
game-logic CODE that is in no function body is outside that claim entirely — and after §0's
re-measure that is the dominant fact about the bucket, not a footnote to it.

## 4. Proving the model — 14 checks run against the real oracle

`notes/portability_predictions.py`. **Three of the first nine predictions were wrong on the first
run**, and they forced the two corrections below. Neither correction moved a tier: `fdc_wait_irq`
was T3-STEER and `snd_music_tick` T4 under both drafts, and `hw_portability.py` did not change.
What they corrected is the **prose** — what a tier was claimed to *mean* once the code runs.

| tier | function | predicted | actually happened |
|---|---|---|---|
| T0 | `copy_longs` `$f93c` | completes, writes only its destination | ✅ 18 insns, exactly its 32 destination bytes |
| T0 | `bg_scroll_copy_x0` `$83b6` | copies two seeded source rows one scanline apart | ✅ 71 insns, both rows arrived, the second from `$3a880` — the `lea -$5800(a0),a0` rewind (§8.1: this family was in no tier until it was named) |
| T0 | `snd_trigger_effect` `$1a48a` | runs clean and produces diffable image state | ✅ 61 insns, 29 image bytes, **empty PSG ledger** |
| T2 | `video_set_lowres_50hz` `$f906` | completes, hardware writes dropped | ✅ 6 insns, reached `$f91c`, **zero image writes** — resolution, screen base and 50 Hz sync all vanish |
| T2 | `clear_palette` `$e7f4` | same, through a register-indirect idiom | ✅ 11 insns, reached `$e808`, **zero image writes** |
| T3 | `fdc_wait_irq` `$62d0` | spins its 600,000-iteration timeout | ❌ **returned in 107 insns having taken the SUCCESS path** |
| T3 | `fdc_restore` `$6408` | spins its 300,000-iteration timeout | ❌ **returned in 203 insns, SUCCESS path** |
| T3 | fdc read-address command `$63c0` | (added later) | 614 insns, **d0.w = `$fffb` ERROR**, 2 image writes |
| T3 | fdc read-sector command `$6488` | (added later) | 826 insns, **d0.w = `$fffd` ERROR**, 6 image writes |
| T3 | `ikbd_disable_mouse` `$f8f0` | poll exits at once via `IKBD_TX_RDY` | ✅ 8 insns, command byte dropped |
| T4 | `psg_set_drive_select` `$624c` | rejected with the PSG diagnostic | ✅ rejected |
| T4 | `FUN_00017f24` `$17f24` | rejected with the PSG diagnostic | ✅ rejected |
| T4 | `snd_music_tick` `$17c74` | rejected with the PSG diagnostic | ❌ **completed green in 12 insns** |

Both T2 cases carry a **positive control** now: the run must reach the function's last hardware
write (`$f91c` / `$e808`), checked through the oracle's PC coverage. Without it "completes with
zero image writes" is equally the signature of a function that did nothing — pointing the case at
the bare `rts` at `$62fa` used to pass, and now fails.

**There is no T5 case in this file, deliberately.** T5's oracle-checked behaviour — an unstubbed run
never returning, a stubbed one crossing the guard in two instructions — lives in the *suite*
(`test/test_copylock.py`, §6.1), which is a stronger place for it: it runs under `make test` rather
than as a standalone script. Restating it here would mean either duplicating the Copylock addresses
that `include/wonderboy.h` is the single source of, or importing the project's test harness (and so
its compiled candidate `.so`) into a script that deliberately needs only the oracle.

### Correction 1 — a T3 read is not "the code hangs", it is "the code believes 0"

`btst #5,$fffa01 / bne` loops *while the bit is set*. The MFP GPIP FDC line is **active low**, so a
permanent 0 reads as *"the controller has already finished"*. The poll therefore satisfies on its
**first** test; the 600,000-iteration timeout is never approached.

Measured, with a negative control that runs the timeout branch directly so the two outcomes are
provably distinguishable:

```
fdc_wait_irq : 107 insns, d0=0, ZERO image writes   (timeout branch $62fc returns d0=$ffff)
fdc_restore  : 203 insns, d0=0, ZERO image writes   (timeout branch $6444 returns d0=$fffb)
```

**That is a statement about the two POLLS, and only about them.** The driver's command-level
entries were never run in the first draft, and they do not agree — see §7.4b. A poll that
"succeeds" is not a driver that reports success.

### Correction 2 — T4 means "cannot be verified across its inputs", not "every run is refused"

`snd_music_tick` is T4 by code — it reads `$ff8800` at `$17f08`. It came back **green** from the
image's own initial state, because the music-playing test two instructions after entry exits
early and execution never reaches the PSG. A case selection that misses the offending access gets
a green that proves nothing. (Its PSG ledger was empty, which is how the test now pins this.)

### And the BuggyBoy defect, demonstrated concretely

`snd_music_tick` opens by choosing the music replay tempo from **two** hardware reads:

```
$17c7e  btst.b #7,$fffa01     ; MFP GPIP bit 7 = monochrome-monitor detect
$17c86  bne.s  $17c90
$17c88  move.b #$48,2274(a3)  ; -> tempo := $48   (the MONO branch)
$17c90  btst.b #1,$ff820a     ; the 50/60 Hz sync register — BuggyBoy's exact register
$17c98  bne.s  $17ca0
$17c9a  move.b #$2b,2274(a3)  ; -> tempo := $2b
```

Both read 0 under the oracle, so the mono branch is taken **unconditionally** and `$17c6e` is
written `$48` on every run. On a colour ST, GPIP bit 7 is high and that branch is dead code. The
test asserts the byte comes back `$48`; nothing in a memory differential can tell, because both
sides store the same wrong value. **This is the `$ffff820a` defect that was invisible to BuggyBoy's
entire differential and only surfaced on real hardware, present here before a line is ported.**

## 5. The false-green surface — every steering hardware read

The classifier reports **10 sites in 6 functions**:

| insn | in | register | what it decides |
|---|---|---|---|
| `$62da` | `fdc_wait_irq` | `$fffa01` bit 5 | FDC done — **reads as "done" always** |
| `$633c` | `fdc_wait_irq_bounded` | `$fffa01` bit 5 | same |
| `$6422` | `fdc_restore` | `$fffa01` bit 5 | seek complete — same |
| `$6314/$631c/$6324` | `fdc_wait_irq_bounded` | `$ff8609/860b/860d` | the DMA address counter, polled to decide when the transfer is done — **always 0** |
| `$17c7e` | `snd_music_tick` | `$fffa01` bit 7 | mono/colour monitor → music tempo |
| `$17c90` | `snd_music_tick` | `$ff820a` bit 1 | **50/60 Hz sync → music tempo (the BuggyBoy register)** |
| `$756` | `ikbd_acia_handler` | `$fffc02` | the IKBD byte, dispatched on |
| `$f8f8` | `ikbd_disable_mouse` | `$fffc00` | transmit-ready (the one modeled read) |

**That count is an under-count, and both of §8.5's stated blind spots fire for real here.** Four
further reads carry the verdict `WINDOW` (undecided) yet demonstrably steer a branch:

| insn | in | verdict | where the branch actually is |
|---|---|---|---|
| `$6470` | `fdc_read_data_reg` | `WINDOW` / not stored | the value returns live in `d1`, becomes `d7` in `fdc_wait_irq` (`exg d1,d7`), and is branched on **two frames up**: `andi.b #$f9,d7 / cmp.b #$a0,d7 / bne` at `$63f0`, and `cmp.b #$80,d7 / bne` at `$64d2` |
| `$612e` `$6136` `$613e` | `FUN_00006118` | `WINDOW` / `STORED` | the three DMA-counter bytes are assembled and stored to `fdc_dma_end_track` (`$6508`), which `fdc_wait_irq_bounded` then tests at `$6332`/`$6338` (`cmp.l $6508.l,d2 / bge.w $6374`) |

So the true surface is **at least 14 sites in at least 8 functions**. The 28-function / 3,348-byte
at-risk figure survives as a lower bound — but not unchanged: forcing both refuted reads to STEER
moves it to **29 functions / 3,362 bytes**, because every function they reach was already at risk
*except* `fdc_read_data_reg` itself (14 bytes).

**A further 21 reads are not classified as steering, and the taxonomy is worth stating exactly**,
because the two columns the scanner emits are different questions:

* **There is not one `DEAD` verdict in the whole file.** All 21 non-STEER reads (after the
  Copylock exclusion) come back `WINDOW` — the taint walk was still live when it gave up. The
  classifier decided nothing about them; a human did, and got four of them wrong (above).
* Of those 21, **17 have `stored = STORED`** and **4 do not** (`$51ae`, `$51b6`, `$6470`, `$6910`).
  "The rest store the value for a caller to branch on" is therefore false for those four; `$6470`
  is one of them and it is the one that steers.

Two groups of the remaining non-steering reads matter more than their tier suggests:

* `$83c` / `$85a` — the joystick report byte, stored into `joy0_state` / `joy1_state`. Permanently
  **0**, i.e. no direction and no fire, for the whole game. (Interrupt handlers, so a differential
  never runs them — but a reconstruction must not pretend they were verified.)
* `$6910` in **`rng_next`**, and `$51ae`/`$51b6` in **`rng_1_to_4_masked`** — the game's two PRNGs
  both mix the shifter's video address counter with in-image state. Under the oracle that term is
  always 0, so both generators degenerate to deterministic functions of their counters. **The diff
  stays clean while the game's randomness silently disappears.**

## 6. What would each harness capability buy?

Priced with `--model` / `--stub`, so the cost/benefit is a number:

| capability | runnable fns | runnable bytes | false-green fns | false-green bytes |
|---|---:|---:|---:|---:|
| *(today)* | 220 | 21,534 | 28 | 3,348 |
| **Copylock stub** (`$ecca` → `rts`, or force `$e7cc := 0`) — **BUILT**, §6.1 | 223 (+3) | 21,770 (+236) | 28 | 3,348 |
| **PSG read model** | 238 (+18) | 24,228 (+2,694) | 28 | 3,348 |
| PSG read model **+ Copylock stub** | 251 (+31) | 25,612 (+4,078) | 28 | 3,348 |
| MFP read model | 220 | 21,534 | 22 (−6) | 2,934 (−414) |
| FDC/DMA read model | 220 | 21,534 | 28 | 3,348 |
| **MFP + FDC/DMA read model** | 220 | 21,534 | **10 (−18)** | **1,106 (−2,242)** |
| ACIA read model | 220 | 21,534 | 26 (−2) | 3,096 (−252) |
| shifter read model | 220 | 21,534 | 28 | 3,348 |
| hardware-WRITE ledger (all blocks) | 220 | 21,534 | 28 | 3,348 |
| everything above | 251 (+31) | 25,612 (+4,078) | **0** | **0** |

Reading it:

* **A PSG read model is the single biggest lever for "can it run at all"** — +18 functions,
  +2,694 bytes, **10.5 % of the measured program**, and a 12.5 % increase over what is runnable
  today.
  **It is not as small as it looks.** "Hand back the last value written to the selected register"
  is *insufficient*, and building it that way would recreate exactly the false-green class §4
  warns about, because all three read-modify-writes preserve bits the game never writes:
  - `psg_set_drive_select` selects register 14 (port A), then `andi.b #$f8,d1` — it **keeps port A
    bits 3–7** and only replaces the drive/side bits;
  - `snd_music_tick`'s `$17f08` selects register 7 (the mixer) and merges with
    `eor.b d0,d3 / and.b d2,d3 / eor.b d0,d3`, preserving every bit outside the `d2` mask;
  - `FUN_00017f24`'s `$17f3e` selects register 7 and does `ori.b #$3f,d1` — it **keeps bits 6–7**,
    the two port-direction bits.

  A write-ledger replay has no value for any of those bits, and on the **first** read the ledger is
  empty, so it would answer 0 — a value TOS never leaves there. The model this game needs is a
  **seeded post-TOS PSG register file** that the write ledger then updates, not a replay.
* **An MFP + FDC/DMA read model is the single biggest lever for "is the green real"** — it removes
  18 of the 28 at-risk functions and 2,242 of the 3,348 at-risk bytes. Neither register block alone
  does much; the driver polls both, and one alone leaves the other steering.
* **A hardware-write ledger buys nothing on these two axes** (writes never block a run and never
  steer a branch) but it is what turns the 14 direct-T2 functions / 1,290 bytes from "runs, proves
  nothing about the hardware" into genuinely verified. Those 14 are **not** all video: 6 are FDC/DMA
  register writers, 3 are boot (`show_data_disk_prompt` alone is 632 of the 1,290 bytes), 1 is the
  resource loader, and only 4 — `flip_screen`, `clear_palette`, `video_set_lowres_50hz`,
  `set_palette`, 198 bytes — are the video group. §4 measured that video group producing **zero
  image writes**: without a ledger, a reconstruction of `set_palette` that writes nothing at all is
  indistinguishable from a correct one.
* **The Copylock stub is cheap and mandatory before any boot-path work**, but on its own it moves
  only 3 functions — and only ONE of those is genuinely new boot-path code (§6.1 breaks the +236
  bytes down). Its real value was claimed to be that it is the single edge making both roots close
  to T5 — §6.1 re-runs the measurement with the stub actually built and finds that claim true but
  worth less than it sounds. **Its value is superadditive with the PSG read model**: the two
  together are worth 1,148 bytes more than the sum of their parts, which is ~83 % of everything the
  stub will ever be worth.

## 6.1 The Copylock stub, built — and what it turned out to be worth

`recreate/test/copylock.py`, pinned by `test/test_copylock.py` (40 cases). Re-running the
measurement with `--stub 0xecca` confirms this table's prediction **exactly**: **220 → 223
functions, 21,534 → 21,770 bytes runnable (+3 / +236), and the false-green figures do not move at
all.**

**Read that headline down, though, because it over-states the stub twice.** Of the +236 bytes:

| bytes | what | is it new boot-path code? |
|---:|---|---|
| 96 | `copylock_entry` itself | **no — tautological.** The stub replaced its body; "the stubbed function is now runnable" is a restatement of the stub |
| 36 | `copylock_key_check` | **no — unreachable from either root**, and from anything: `out/hw_scan.tsv` gives it no incoming call edge at all |
| **104** | **`load_resource_by_index`** | **yes — and it is the whole of it.** One function |

So the honest headline is **+1 genuinely-newly-in-scope boot-path function, 104 bytes**, and both
roots stay unrunnable — their T5 becomes T4, i.e. "there is no source text to port" becomes "the
run is refused". What it does to those two roots is the part the earlier draft was optimistic about:

| roots-restricted transitive tier | today | with the stub |
|---|---|---|
| T0 CLEAN | 95 / 10,440 B | 96 / 10,536 B |
| T2 HW_WRITE_ONLY | 9 / 274 B | 9 / 274 B |
| T3 HW_READ | 14 / 1,102 B | 15 / 1,206 B |
| T4 HARD_REJECT | 12 / 1,874 B | **20 / 2,966 B** |
| T5 UNMEASURABLE | 10 / 1,292 B | **0** |
| **total** | **140 / 14,982 B** | **140 / 14,982 B** |

**T5 vanishes from the roots and T4 absorbs almost all of it.** Of the 10 T5 functions, exactly one
becomes clean (`copylock_entry` itself) and one becomes T3; the other **8 were never blocked only by
the protection**, and the tool's own witness path for both roots changes subsystem:

```
game_main_loop -> FUN_0000053e -> show_data_disk_prompt -> snd_stub_00 -> FUN_00017b3a
               -> FUN_00017af8 -> FUN_00017f24          ← the sound module's PSG read-modify-write
```

So the honest reading is: **the stub does not open the boot path, it exchanges one wall for the next
one.** Both roots move from "cannot be measured" to "will be refused". The pair that opens them is
the stub **plus** the PSG read model — with both, 251/252 functions and 25,612/25,696 bytes are
runnable (99.7 %) and both roots land on T3 HW_READ, i.e. runnable-but-false-green, blocked only by
`fdc_restore` and `ikbd_disable_mouse`. Anything that must cross `load_resource_by_index` needs the
stub; anything that must cross `show_data_disk_prompt` needs both. Two subsystem rows also move:
**copylock** direct-T0 goes 2/52 B → 3/148 B and runnable 1/16 B → 3/148 B, and the **resource
loader** goes transitive-T5 → T3 with its one 104-byte function becoming runnable.

### The stub's value is an INTERACTION TERM, not a row in the table

The §6 table is read one row at a time, and that is exactly what makes it misread here. Compare the
three rows:

| built | runnable fns | runnable bytes |
|---|---:|---:|
| Copylock stub alone | +3 | **+236** |
| PSG read model alone | +18 | **+2,694** |
| both | +31 | **+4,078** |

`4,078 − 236 − 2,694 = ` **+1,148 bytes** (and `31 − 3 − 18 = ` **+10 functions**) that neither
capability delivers on its own. Those 10 functions are exactly the ones the stub converts T5 → T4:
the stub is what makes them measurable at all, and only the PSG model can then release them. So
**~83 % of the stub's eventual value (1,148 of 1,384 bytes) is locked behind the PSG read model** —
which is why §7's recommendation is to do (a) and (c) together or neither, and why "the Copylock
stub buys +236 bytes" is the wrong way to price it in both directions at once.

Reproduce with the §"Reproducing it" command line plus `--stub 0xecca`, or add `--model psg:read`
for the pair.

### The two mechanisms, and why there are two

**Clearing `$e7cc` is not universally sufficient**, and a stub that silently fails to apply is the
false-green class this document exists to measure. There are exactly four `abs.l` references to
`copylock_arm_flag` in the image (swept, not counted by eye — and `abs.w` cannot reach it and a
68000 cannot write through pc-relative, so `abs.l` is the only encoding that could arm it) and
exactly one to `copylock_entry`:

| site | what it does |
|---|---|
| `$e51e` | `move.w #$ffff,$e7cc` — ARM, immediately before the TITLESCR.RAD load |
| `$e6dc` | `move.w #$ffff,$e7cc` — ARM, immediately before the SPRITES.CRU load |
| `$e7b2` | `tst.w $e7cc / beq.w $e7c8` — the guard, inside `load_resource_by_index` |
| `$e7c2` | `clr.w $e7cc` — the game disarms it after the first call |
| `$e7bc` | `jsr $ecca.l` — the image's only reference to the protection |

* **Disarm** (`$e7cc := 0`) patches no code and is the game's own steady state: `$e7c2` puts the
  flag there itself, so every resource load after the first takes exactly this path. It is valid
  only for a run that cannot reach an arming site. Crossing `$e51e` or `$e6dc` re-arms the flag
  before the guard reads it — **demonstrated**, in one run of the boot path's own shape, not argued.
* **Stub the entry** (`$ecca := rts`) is valid for any run, because an arming site does not write
  code. The `jsr` still executes, so the stack behaves as it really would, and nothing between the
  return and the function's `rts` reads `d0` (`$e7c2` is a `clr.w`; the two arming call sites do not
  read it either — `$e52a` is a `lea`, and `$e6e8` calls `$e87c`, whose second instruction pair
  overwrites `d0`). Semantically it is "the protection passed", the branch a genuine disk takes.

Both are applied by default. Choosing between them is a judgement about a run's entry point that a
caller can get wrong silently, and there is no cost to belt-and-braces: under both, the guard skips,
and if it somehow did not, the entry is an `rts` anyway. There is a second reason — the kit's
`_attribution_check` poison pass inverts every byte the oracle wrote, and under disarm alone the
game's own `clr.w $e7cc` puts the flag in that set, so the poisoned re-run would start **re-armed**.

### The witness, and what an unstubbed run actually does

No run is reported as stubbed on the strength of the poke. After every run, `copylock.run()`
compares final memory against the memory the run started from, over the protection's own bytes
(`$ecca..$f575`) and the three exception vectors it installs (`$10`, `$20`, `$24`). Three
instructions into the blob's body comes `movem.l d0-a7,(a6)` into `copylock_reg_save`, and the two
instructions before it are `moveq #0,d0 / move.l #$ffffffff,d1` — the blob loads that `d1` itself,
so the saved `d1` differs from the zero-filled save area *whatever registers the run was entered
with*.

**State the guarantee precisely, because the loose version is false.** The witness fires on any run
that **completes that `movem`** — not on any run that "reaches the protection" — and it is
independent of the caller's inputs **because two guards enforce that**, not by construction. Both
halves were demonstrated false against an earlier draft:

* **A blind window at the blob's entrance, six checkpoints wide.** The five instructions before the
  `movem` — `moveq #0,d0 / move.l #$ffffffff,d1 / bra.s $ed46 / move.l a6,-(a7) / lea $ecd4(pc),a6`
  — write the STACK or nothing at all, so a `stop_pc` of `$ecca`, `$eccc`, `$ecd2`, `$ed46`, `$ed48`
  or `$ed4c` came back green with an empty trespass list from a run that had executed the guard's
  `jsr` and up to five instructions of the protection. `copylock.run()` now refuses a `stop_pc`
  inside `[$ecca, $f576)` outright — sound, because a correctly stubbed run cannot reach one. (The
  `bra.s` at `$ecd2` was itself missed by the first draft of the fix: the window is in two pieces,
  and the test now resolves that branch to prove they are one run of execution.)
* **Twelve caller-supplied poke bytes blinded it completely.** `stubbed_image(mechanism, pokes)`
  wrote `pokes` into the image the witness then used as its own baseline, so a poke inside the
  watched span landed on *both* sides of the comparison. The blob's entire durable delta at
  `$ed50` is 12 bytes — the saved `d1` (`$ecd8..$ecdb`), `a0` (`$ecf5..$ecf7`), `a6`
  (`$ed0e..$ed0f`) and `a7` (`$ed11..$ed13`) — and feeding exactly those back as pokes returned
  green with the `movem` executed. Any poke overlapping the watched span is now refused.

Both reproducers are kept as regression cases in `test/test_copylock.py`.

**It is a memory difference and not a write set, and that was forced by a measurement.** At
`load_base = 0x3f8` the relocator's copy of the program body to `$400` is an identity copy that
*writes* every byte of the image — all 2,220 of the protection's, 96 of them in `copylock_reg_save`
— so a write-set witness reports "the protection DID execute" for a `move.l (a0)+,(a1)+` loop. It
also cannot overflow: `shim.c`'s write ledger silently drops writes past 1,048,576 entries.

> #### The witness is sound only because the blob cannot COMPLETE
>
> This is a dependency, not a property, and it is stated nowhere else. **A Rob Northen trace
> decryptor is built to leave no trace**: it decrypts and *re-encrypts* one longword at a time, and
> it restores the exception vectors it saved. A blob that ran to completion would put the code span
> and all three vectors back by construction, and the only evidence left inside the watched span
> would be the 96-byte register save area.
>
> What stops it completing is the oracle's CPU setting, `M68K_EMULATE_TRACE=0`. That is now **pinned
> in `tools/recreate_kit/kit.mk`'s `OCFLAGS`** as a stated modelling decision rather than inherited
> from the vendored `m68kconf.h` — which matters because `oracle/musashi/` is gitignored and cloned
> from upstream HEAD at build time, so the setting was untracked and unpinned. `TRAP_MODEL.md` has
> the decision; `test_copylock.py::test_the_oracles_cpu_takes_no_trace_exception` asserts it
> behaviourally (a probe arms the T bit and requires the trace vector never to be taken).

Three negative controls, and what they measured:

* **Stopping just inside the blob** (`$ed50`, past the `movem`) the witness fires and names the save
  area; run on to `$ee1a` it names every range it watches, including all three vectors.
* **Letting it run from the guard** — the oracle does **not** survive executing the Copylock. It
  saves its registers, takes both anti-trace `illegal` exceptions, reaches the decryptor at `$ee02`,
  and then never returns. The **shipped** case caps it at 1,000,000 instructions — that is the bound
  under `make test`, and the bound any future claim should be read against; a one-off run to
  20,000,000 also failed to reach the far side, but nothing pins that. The
  reason is worth recording before anyone proposes modelling the protection instead of stubbing it.
  The decryptor works by setting the T bit in the exception frame's SR and decrypting one longword
  per single-step exception, so with trace emulation off it cannot even self-decrypt, and past the
  second `illegal` the CPU is executing ciphertext as instructions. `notes/architecture.md` §2.5's
  "Musashi can do this" is true of Musashi and false of this build of it.
* **Letting it run from an ARMING SITE — and it comes back.** Disarmed and entered at `$e51e` or
  `$e6dc`, the run re-arms the flag, enters the blob, and returns to the guard's far side `$e7c8`
  in **184,997 instructions with 2,053 bytes of the protection scrambled behind it**. That is the
  false green in its exact shape — a run that finishes and looks ordinary — and it is the case the
  witness is for. "An unstubbed run never comes back" is true of the guard entry only.

### KNOWINGLY UNPINNED — what the stub does not verify

The stub buys runs; it does not buy verification of what it replaced. Everything here is a permanent
or standing gap, not a to-do list:

1. **The protection's own memory effects never happen.** The 96-byte register save area
   (`$ecd4..$ed33`), the three vector installs (`$10`/`$20`/`$24`), the decrypt cursor at `$ed3e`,
   and the key it returns in `d0` are all absent from every stubbed run. A reconstruction verified
   under the stub is verified for the game's **disarmed steady state — the second and subsequent
   resource loads — and not for the first.** The first load of a real boot runs 2,236 bytes of code
   this measurement has never executed.
2. **`d0` at the guard's exit is the stub's, not the protection's.** Under the stub it is whatever
   `disk_load_file` left; on real hardware it is the Copylock key. Nothing between the return and
   `load_resource_by_index`'s `rts` reads it, and neither arming call site does, but a caller beyond
   those two has not been audited.
3. **Three things stay reachable only from inside the ciphertext, and the stub does not change
   that** — `disk_check_signature` (`$5e3e`), the `$ecba` pointer table with its four scanline-order
   tables, and the readers of `$f89a`/`$f89c`. §7.5 still applies: there is no source text to port.
4. **The witness is opt-in at the wrong layer.** It covers every run made through `copylock.run()`,
   but `recreate_kit.harness.differential()` calls `emu.run` itself, so a future boot-path
   differential written as `differential(entry, regs={"_pokes": copylock.stub_pokes()})` gets no
   witness unless its author calls `assert_did_not_execute()` by hand. **Its reachability today is
   zero** — `recreate/src/` is empty and no Wonder Boy test calls `differential()` — and under this
   build forgetting the stub fails loudly (`did not reach checkpoint`) rather than going green. The
   enabling fix is `differential()` returning its final image, which would let a caller run the
   witness itself; it is recorded in `STATUS.md` and deliberately not built, since nothing uses it
   yet. A per-run forbidden-write veto in the kit was considered and **rejected**: it would fire on
   `test_bootstrap.py`'s relocator runs, which write all 2,220 protection bytes identically — the
   exact false positive the difference witness was invented to avoid.
5. **A register-indirect write to `copylock_arm_flag` would be invisible** to the four-reference
   sweep the disarm mechanism's domain rests on, exactly as it is to every other operand scan here
   (§2). So is a fifth arming site in the 22,984 bytes §8.1 says carry no disassembly at all. The
   mirror claim on the other side of the witness — that only the Copylock changes `$10`/`$20`/`$24`
   — is swept for `move.l <ea>,abs.l`, and the blob's own are the only hits: `$ed62`, `$ed6a` and
   `$ed80` (→ `$10`), `$ee14` (→ `$20`), `$ee0a` (→ `$24`). If that is ever wrong the failure is
   loud (a spurious "the protection DID execute"), not silent.
6. **`WB_COPYLOCK_REG_SAVE_LEN`'s upper 32 bytes are pinned by reading, not by running.** The blob
   copies vectors `$8..$27` into them, and those are zeros in a fresh image — zeros copied over
   zeros, which a difference witness cannot see. The lower 64 are pinned from the `movem` mask.
7. **The blob's own four wipe-table pointers sit OUTSIDE the watched span.** It starts at `$ecca`;
   `$ecba..$ecc9` holds the four longwords pointing at the tables at `$f576`. Left outside
   deliberately, and recorded rather than closed: they are read-only constants, so no run can make
   them differ and widening the span would add witness unpinnable in exactly the way item 6's upper
   32 bytes are. They are equally unpinned in the other direction — nothing proves plaintext code
   never writes them.

## 7. Recommendation — what to reconstruct, in order

1. **The two unrolled blit families** — **the scroll half is DONE** (batch 7), and doing it pulled
   the whole `$7522..$8228` engine behind it (batches 5–6), which is what §0 re-drew the boundary
   for. The 12 sprite blitters (`$8fce..$989c`, 2,254 bytes) *and*
   the 16-routine background scroll copier (`$83b6..$8dfe`, 2,632 bytes, 17 % larger), plus its
   dispatcher `bg_scroll_blit` (`$82f8`). 100 % T0 direct **and** transitive, driven entirely by
   their arguments, nothing needs to change in the harness. Start here. Two precision notes: four
   of the twelve sprite blitters are not strictly leaves — the left-edge clip preludes `bra.w` into
   the right-edge prelude's shared body, which the scan records as `JUMPIN` edges; and
   `bg_scroll_blit`'s transitive T0 is over an empty callee set, because its jump table is a label
   and not decoded edges (§8.3). Both are harmless here: every target is itself T0.
2. **The game-logic core** (104 functions, 7,638 bytes runnable today; 61 of them / 2,986 bytes are
   already green). 112 of its 114 recovered functions touch no hardware. Avoid the 3 with a
   steering T3 below them until step 4; the two
   PRNGs are portable but must be documented as *seeded from hardware the oracle zeroes*, so any
   test over a caller of one is exercising a single fixed pseudo-random stream. **Remember the
   denominator**: this is 22.1 % of the game-logic code believed to exist, so a "done" here is not a
   done subsystem — and §0's re-measure lowered that denominator's coverage rather than raising it,
   because the three subsystems carved out of the catch-all were the best-measured code in it.
3. **The RAD depacker** (`$5d62`, 3 functions, 216 bytes) — **DONE** (`src/rad.c`). T0, and already
   independently proven by
   `notes/rad_differential.py` — 45 files, 0 failures. This is a free win and a template for how a
   verified function's row should read.
4. **Then, and only then, the harness work**, in the order the numbers give:
   a. **PSG read model** (+18 functions, +2,694 bytes runnable), built as a seeded register file,
      not a ledger replay. It unblocks the music **replay/drain** path and the floppy drive-select
      — and only those. It is *not* true that no byte of the sound module is verifiable without it:
      of the module's 7 register-saving entry stubs at `$17adc..$17b3a` (six `movem`, one bare
      `move.l a3,-(a7)`), three — `$17b06`, `$17b14`, `$17b30` — reach no hardware at all and hold
      no unresolved indirect site anywhere in their subtree, so their closures are **exact, not
      lower bounds**. `$17b14` → **`snd_trigger_effect` (`$1a48a`, 334 bytes)** is
      T0 CLEAN and diffable today with zero new harness capability; §4 runs it and it writes 29
      image bytes with an empty PSG ledger. The architecture explains why: a trigger writes RAM
      channel state, and only `snd_music_tick` drains that state to the chip. **13 of the module's
      21 functions and 1,622 of its 2,634 bytes — 62 % — are verifiable now.**
   b. **MFP + FDC/DMA read model** (−18 false-green functions, −2,242 bytes). The floppy driver's
      failure mode is worse than "always reports instant success": the *polls* return success on
      their first test, and the *commands* above them then reject the fabricated status and report
      **hard failure** — `$63c0` returns `d0.w = $fffb` after 614 instructions and 2 image writes,
      `$6488` returns `$fffd` after 826 instructions and 6 image writes (`$6500..$6503`,
      `$6526/7`). Both are driven by the same zeroed `move.w $ff8604,d1` at `$6470`. So a
      differential of a reconstructed `disk_load_file` would be pinned against a driver that
      fails, retries, and mutates state — not against one that quietly succeeds.
   c. **Copylock stub** — **built** (§6.1). Worth exactly the 3 functions this table predicted, and
      necessary for anything on the boot path; but it does not open the boot path on its own, it
      hands both roots to the PSG wall in (a). Do (a) and (c) together or neither.
   d. **Hardware-write ledger**, the direct sibling of the existing Dosound ledger, to make the 14
      direct-T2 functions mean something.
5. **Never**: the Copylock's fuzzy-byte check. `$ed8e..$f540` is ciphertext that only ever exists
   as plaintext one longword at a time — **there is no source text to port**, so "unverified" here
   is a permanent state and not a to-do. (`notes/architecture.md` §2.5.)

## 8. Blind spots — state these with the results, not after them

1. **Coverage, and it is the biggest one. Ghidra put 25,696 bytes inside a function body;
   `notes/architecture.md`'s region table calls ~54,854 bytes CODE.** So every tier table describes
   **46.8 %** of what is believed to be code, and the answer box's per-subsystem breakdown is part
   of the result, not a footnote. (The disassembler *reached* 27,986 bytes; the 2,290-byte
   difference is in no function and so in no tier — §8.2 — and 506 of those bytes land inside
   DATA-classified regions, so they are not even in the CODE denominator.)

   **This is not an abstract worry — it hid a whole subsystem.** `$8366` is a 16-entry longword
   jump table (`$83b6, $8450, $84ea, $8590 … $8d58`, stride `$9a` then `$a6`), loaded at `$8336`
   (`movea.l (0,a2,d1.w),a2`, `d1` = the scroll column × 4) and entered by the two `jmp (a2)` at
   `$8350`/`$8364`. Its targets tile `$83b6..$8dfe` **exactly**, 2,632 bytes, and every one opens
   with unrolled `22d8 22d8 22d8` = `move.l (a0)+,(a1)+`. That is 16 real blit routines — the
   background scroll copier — that were in **no tier at all**: the identical "leaf code behind a
   pointer table" failure `docs/methodology.md` records for `$8fce`, in the same program, 3 KB
   away. They are named in `../names.txt` now, and naming them moved the measurement by 16
   functions and 2,632 bytes.

   What is left after that: **22,984 bytes of CODE-region address space carry no disassembly at
   all, in 65 gaps.** Definition, so it can be re-derived: subtract from the CODE rows of
   `notes/architecture.md`'s region table every `F` record's `entry..body_end` span and every `O`
   record's span in `out/hw_scan.tsv`; what remains is address space no instruction of Ghidra's
   sits in. Screening each gap on `rts`+`dbf` density per 1000 words and zero-word fraction puts
   **16,766 bytes code-like and 6,218 data-like**, so the 54,854 CODE figure over-counts code by
   about 11 % — the un-disassembled bulk is real code Ghidra never reached, not a region-table
   error. Worked example, the largest gap: `$3e2c..$501a` (4,590 B) is a 96-byte word table
   (`00de 00de 00de 00de 00df …`) and then unambiguous engine code from `$3e8c` —
   `btst #2,9(a0) / bne.w $698a / btst #0,9(a0) / bne.w $3fb6 / bsr.w $23b6 / … / bsr.w $5c6e`.
   Genuinely data sitting inside CODE rows: `$e978..$ecca`, `$1a830..$1aaca`, `$64f0..$6796`
   (it opens with the floppy driver's state block, `../names.txt`'s `$64f0..$6528`),
   `$17bc6..$17c72` (music data), `$73ce..$7522`.

   **One reassuring result.** Sweeping every word-aligned longword in those gaps for a value that
   decodes into a hardware block finds **5 candidates outside the Copylock ciphertext, and not one
   is a plausible instruction operand**: four are `$fbfffc05`-shaped mask longwords inside the
   bitmap block at `$e978..$ecca`, and the fifth (`$00fffc00` at `$17c62`) is a coincidental
   alignment inside a run of `00 00 00 00 00 ff fc 00 00 00 00 c7` music data. So the coverage gap
   hides no *absolute* hardware site. A **register-indirect** access in undisassembled code would
   still be invisible to every method here, and there is no bound on that.
2. **2,290 bytes of disassembled code sit in no function** (12 runs spanning 6,304 bytes of address
   range) and are in no tier above.
3. **10 unresolved indirect call/jump sites** (`jsr (a0)`, `jmp (a1)`, `jmp (0,a3,a2.w)` at `$726`,
   `$936`, `$8350`, `$8364`, `$8fbc`, `$ddfe`, `$de74`, `$dfd6`, `$e8fc`, `$18204`), in 8
   functions. Every transitive tier is a **lower bound** wherever one appears — including the three
   jump tables at `$989c/$98ac/$98bc` that reach the sprite blitters, `bg_scroll_blit`'s own two
   `jmp (a2)`, and `vbl_handler`'s `jsr 14(a0)` into the sound module. But the damage is bounded
   and small: **only 22 of the 252 functions (3,792 bytes, 14.8 %) have an unresolved indirect site
   anywhere in their subtree**, so for the other 85.2 % the closure is a **tight** bound and the
   tier is exact.

   **112 of the 252 functions (10,714 bytes) are unreachable in the static call graph** from the
   roots. That qualifies the roots-restricted table in §3 and nothing else — a tier does not depend
   on reachability. And "unreachable" overstates it twice over. First, `parse_scan` **drops every
   call-graph edge whose source is code attributed to no function** (47 edges here), so some of
   those 112 are reached in reality by a `bsr` sitting in one of §8.2's orphan runs. Second, the
   whole growth of that count in this revision — from 96 / 8,082 B to 112 / 10,714 B — is the 16
   scroll routines themselves: naming a jump table with `var` creates a label, not pointer data, so
   no `bg_scroll_blit → bg_scroll_copy_x*` edge exists even though the table is decoded in
   `../names.txt`. The same gap makes `bg_scroll_blit`'s "T0 transitive" a statement about an
   **empty** callee set. `hw_portability.py` has `--extra-hw` for the analogous *access* blind spot
   but nothing for a known-but-unresolvable *call edge*; here it is harmless (all 16 targets are T0
   themselves) and it would not be in general.
4. **The Copylock ciphertext `$ed8e..$f540` (1,970 bytes) is unreadable by construction.** No scan
   of any kind — hardware, traps, addresses, OS calls — covers it. "No blitter, no STE, one trap"
   are claims about **98.6 %** of the image. The sweep does produce plausible-looking hardware
   operands inside it (an `$8800` at `$f1c6`, an `add.w D7,($40862ada)` at `$ed90`); they are decode
   artefacts and are excluded here.
5. **The steering analysis is intra-procedural, window-bounded (48 instructions) and stops at
   calls.** 10 reads came back `STEER` and 21 `WINDOW`; there is not one `DEAD` verdict in the file.
   Reading all 21 by hand: 6 are `bclr #6,$fffa11` interrupt acknowledges, 3 are the PSG
   read-modify-writes, **and 4 of them do steer** — see §5. **A read whose value crosses a `jsr`
   into a callee's branch, or a store/reload through memory, is missed by construction.** That is
   the price of not manufacturing false STEERs, and it is why the false-green number is a *lower*
   bound. The first draft of this document claimed the hand review found no steer among them; it
   was wrong, and both documented blind spots turned out to fire in the same driver.
6. **Tiering is static; running is dynamic.** §4's correction 2: a T4 function returns green on a
   run that never reaches its PSG access. The tiers describe the code, not any one run.
7. **Interrupt handlers are tiered but never execute under the oracle.** `vbl_handler`,
   `ikbd_acia_handler` and the two joystick handlers are the game's only clock and its only input
   path, and a differential never runs them at all.
8. **`--model` prices a capability by assuming it is perfect.** A real FDC model that returned
   plausible-but-wrong status would move the same functions out of the false-green count while
   leaving them just as unverified. The table says what the ceiling is worth, not what a given
   implementation would deliver. §6's PSG entry is the worked example: the obvious implementation
   is already known to be insufficient.
