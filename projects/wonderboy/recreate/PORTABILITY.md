# How much of Wonder Boy is behind the wall the differential cannot see?

`STATUS.md`'s blocker 2 says the game's I/O is all direct hardware, that the oracle models almost
none of it, and that **how much of the game sits behind that wall had not been measured.** This is
the measurement.

> *Tier numbers in every section written before §0g are the OLD six-tier lattice, and two of them
> changed MEANING rather than just position (old `T3 HW_READ` vs new `T3 HW_WRITE_ONLY`; old
> `T4 HARD_REJECT` vs new `T4 HW_READ`). §0g has the old→new mapping table — read it before
> comparing any number in §0–§0f or §2–§8 against a report generated after 2026-08-07. **§0i then
> renamed `T2 PSG_SEEDED_READ` to `T2 SEEDED_READ`** — the same tier, widened to cover the two
> hardware bytes kit Phase 7 seeds; the position and the numbering are unchanged.*

> ## The answer
>
> **Measured over the 47 % of the game's code Ghidra has recovered so far, the gameplay logic is
> portable today. The wall is a boot-time, disk-time and sound-time problem — but the gameplay code
> is also the part this measurement covers least.**
>
> Ghidra has recovered 256 functions / **25,786 of the ~54,854 bytes** `notes/architecture.md`
> calls CODE. Everything below is a statement about those 25,786 bytes and nothing else. Of the
> 87 game-logic functions (6,904 B) inside them, 85 touch no hardware — the two exceptions are
> the game's PRNGs, which seed from the video address counter. Transitively **78 of them
> (5,156 B) run end-to-end under the oracle: 74.7 % of what is measured, but 16.3 % of the 31,714
> bytes of game-logic code believed to exist.** Only 3 of them (372 B) carry any false-green risk,
> and both blit families (16 background-scroll routines, 12 sprite blitters) and the RAD depacker
> are completely clean.
>
> **21,334 bytes are runnable end-to-end: 82.7 % of what is measured** *(21,624 / 83.9 % until
> §0d's scan fix surfaced ten dropped call edges and re-priced `game_routine_6bb8` behind the PSG
> wall)* **, 38.9 % of the program's believed code.** Of the rest, 4,162 bytes are measured and blocked (T4/T5), and **29,068 bytes
> are in no tier at all** because they are in no function body — mostly leaf routines reached only
> through pointer tables (§8.1). What *is* measured and cannot be verified is concentrated in four
> places: the **WD1772/DMA floppy driver**, the **YM2149 replay path**, the **Copylock**, and the
> **boot chain** that calls all three.
>
> **And "runnable" is no longer the strongest thing this report can say.** 136 of the 256 functions
> / **13,172 bytes are reconstructed and green** against the oracle — 51.1 % of what is measured,
> 24.0 % of believed code, and 60.9 % of everything the harness can run at all. That is the
> right-hand column below, and after §0b–§0c it is concentrated in seven subsystems, five of which
> are complete.
>
> But three of the four unverifiable places are measured *better* than the gameplay code the report
> calls portable — only the Copylock, which cannot be read at all by construction, is measured worse:

| subsystem | CODE bytes | in a function | coverage | reconstructed & green |
|---|---:|---:|---:|---:|
| **game logic** (the catch-all bucket) | **31,714** | **6,904** | **21.8 %** | **3,098 B** (62 fns) |
| video (background scroll) | 7,104 | 7,010 | 98.7 % | **7,010 B** (39 fns) |
| sound (YM2149) | 3,824 | 2,634 | 68.9 % | 0 |
| video (sprite blitters) | 2,254 | 2,254 | 100.0 % | 0 |
| copylock (protection) | 2,236 | 232 | 10.4 % | 0 |
| boot | 2,002 | 1,072 | 53.5 % | 0 |
| disk (FAT12 + file load) | 1,028 | 1,030 | 100.2 % | 0 |
| actor (table + lifecycle) | 954 | 954 | 100.0 % | **954 B** (16 fns) |
| map (collision + settle) | 924 | 924 | 100.0 % | **924 B** (9 fns) |
| disk (WD1772 FDC + DMA) | 686 | 684 | 99.7 % | 0 |
| text (message box) | 678 | 678 | 100.0 % | **678 B** (3 fns) |
| stage (load + reset) | 458 | 458 | 100.0 % | **248 B** (3 fns) |
| input (IKBD / ACIA) | 312 | 300 | 96.2 % | 0 |
| video (screen / palette / mode) | 240 | 236 | 98.3 % | 0 |
| resource depack (RAD) | 220 | 216 | 98.2 % | **216 B** (3 fns) |
| resource loader | 158 | 148 | 93.7 % | **44 B** (1 fn) |
| interrupt (VBL) | 62 | 52 | 83.9 % | 0 |
| **TOTAL** | **54,854** | **25,786** | **47.0 %** | **13,172 B** (136 fns) |

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
says 134 / 13,172 B and this says 136 / 13,172 B.** Same code, two counting rules; this file uses
the scan's, because the scan is what every other column here is out of. Since the §0c re-scan the
two rules agree on the BYTES, and the reconciliation is one entry long:

| | reconstructions | F records | bytes |
|---|---:|---:|---:|
| `src/rad.c` — one reconstruction Ghidra splits into three (`rad_depack`, `rad_refill_bit_buffer`, `rad_get_bits`) | 1 | 3 | same 216 |
| **net** | **134** | **136** | **13,172 = 13,172** |

The other two rows this table used to carry — `$fe4a` folded over `$fe8c`, and the
`$2b5a`/`$2b82`/`$2b8e` cluster reduced to one 20-byte function — were the Ghidra DB's staleness,
not a boundary disagreement, and §0c's reapply + re-scan discharged them: all five routines are
their own F records now, and the 90 bytes of reconstructed-and-green code that sat in **no function
body** are measured. The actor row reads 100 % because of it.

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
python3 projects/wonderboy/notes/portability_predictions.py    # 14 cases, must be green — see caveat
make -C projects/wonderboy/recreate test                       # 77 cases, must be green
pytest tools/test_hw_portability.py                            # 56 cases, the classifier's own pins (§0g, §0i)
```

Add `--stub 0xecca` (and `--model psg:read` for the pair) to reproduce §6.1's numbers.

**Caveat on line 4 — `portability_predictions.py` has not been re-run since kit Phase 6.** "14
cases, must be green" is the last state anyone observed, not a step this file's most recent
revisions checked: §0g read its assertions rather than running it (and found two passing for the
wrong reason), and §0i did not run it either — a concurrent port session owns `recreate/`, and the
script builds the oracle `.so`. It is queued in §0g's item 4 and §0i's item 2. Run it, but treat a
green as unconfirmed until that pass lands.

**`reapply.sh` is part of the measurement, not setup.** Ghidra does not reach the background
scroll blitter (`$83b6..$8dfe`, 16 functions) or `bcd_add_random_1_to_4` (`$51ac`) on its own — nothing
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

## 0b. Re-measured 2026-08-05 — four more subsystems came out of the catch-all

Same method again, same scan, same `hw_portability.py`; `subsystems.tsv` is again the only input
that changed. **Every whole-program figure is byte-identical before and after** — 252 functions,
25,696 bytes, both tier tables, the roots table, 220/21,534 runnable, 28/3,348 at false-green risk,
the 126-site census — checked by diffing the two reports rather than argued. Only subsystem rows
moved, and they moved a long way.

**The trigger.** `STATUS.md` carried the queue entry through three batches: the collision map
(batch 10–11), the stage-builder tier (batch 12) and the spawn/lifecycle tier (batch 13) were all
reconstructed and green while `subsystems.tsv` still filed every one of them under "game logic".
**Twenty-eight `F` records and 2,804 measured bytes** of the best-understood code in the program
were being charged to the bucket this report calls least characterised.

**What moved, and on what evidence** (each range is cited in `subsystems.tsv` itself):

| range(s) | from | to | evidence |
|---|---|---|---|
| `$10a2..$1208`, `$1334..$1514`, `$1af0..$1b46` (9 fns, 924 B) | game logic | **map (collision + settle)** *(new)* | batches 10–11: the two horizontal steps, the shared cell lookup, the two settles, the tier above them and the only writer — all reconstructed and green |
| `$1b68..$1bb4`, `$1f36..$1f54`, `$2af2..$2b0a`, `$2b5a..$2bc8`, `$df9e..$dfac` (6 fns, 164 B) | game logic | actor (table + lifecycle) | batches 10 and 13: the two slot allocators, the table reset, the free-marker walk, the launch and the three step reactions |
| `$ff42..$1009a` (3 fns, 344 B) | game logic | actor (table + lifecycle) | batch 13: the spawn pass, the template→record spawn and the hit-point ramp, tiling to `architecture.md`'s own CODE/DATA boundary |
| `$fa30..$fc46`, `$fd46..$fe0c` (3 fns, 732 B) | game logic | video (background scroll) | batch 12: the three routines that FILL the eight pre-shifted buffers `$7522`'s engine then maintains and `$82f8`'s consumer copies to the screen |
| `$e110..$e19a` (3 fns, 138 B) | game logic | video (background scroll) | batch 12: the three banner plotters, which write the same background buffer copy 0 at `$44000` |
| `$f95c..$fa2e`, `$fe4a..$ff42` (3 fns, 458 B) | game logic | **stage (load + reset)** *(new)* | batch 12–13: the stage loader's top, plus the new-game and lost-life resets |
| `$fe1e..$fe4a` (1 fn, 44 B) | game logic | resource loader | batch 12: it relocates the disk-loaded table's records, its one caller is `show_data_disk_prompt`, and its two operand addresses are touched only from that boot resource-install path |
| `$e80c..$e87c` (1 fn, 112 B) | **boot** | game logic | batch 13: it is `hud_draw_lives`, called by `game_life_restart_reset`. It was never boot; the partition has no status-panel subsystem, so it falls to the catch-all with the rest of the HUD |

`actor (table + projection)` is renamed **`actor (table + lifecycle)`**: it was five functions of
entry tier and projection, and it is now fourteen that also allocate, free, reset, spawn and launch.

**Before → after:**

| subsystem | fns | measured B | CODE B | coverage | runnable |
|---|---|---|---|---|---|
| game logic | 114 → **87** | 9,596 → **6,904** | 34,496 → **31,714** | 27.8 % → **21.8 %** | 104 / 7,638 B → **78 / 5,156 B** |
| video (background scroll) | 33 → **39** | 6,140 → **7,010** | 6,234 → **7,104** | 98.5 % → **98.7 %** | 33 / 6,140 B → **39 / 7,010 B** |
| actor (table + lifecycle) | 5 → **14** | 356 → **864** | 356 → **954** | 100.0 % → **90.6 %** | 5 / 356 B → **14 / 864 B** |
| boot | 12 → **11** | 1,184 → **1,072** | 2,114 → **2,002** | 56.0 % → **53.5 %** | 5 / 408 B → **4 / 296 B** |
| resource loader | 1 → **2** | 104 → **148** | 114 → **158** | 91.2 % → **93.7 %** | 0 → **1 / 44 B** |
| map (collision + settle) | — → **9** | — → **924** | — → **924** | — → **100.0 %** | — → **9 / 924 B** |
| stage (load + reset) | — → **3** | — → **458** | — → **458** | — → **100.0 %** | — → **2 / 248 B** |

**The catch-all got worse AGAIN, and harder.** §0 found that carving three subsystems out of "game
logic" lowered its coverage from 36.0 % to 27.8 %; this re-measure takes it to **21.8 %**. The
arithmetic is starker than last time: the bucket lost **2,692 measured bytes and only 90 unmeasured
ones**, so the CODE it holds outside every function body barely moved — 24,900 → **24,810 bytes,
now 78.2 % of it, up from 72.2 %.** Two re-measures in, the pattern is not a coincidence and it is
the honest reading of the whole document: **every subsystem this project characterises is one that
Ghidra had already recovered, and the reconstruction campaign is working entirely inside the 46.8 %
the scan can see.** Nothing any batch has done has reached the other 53.2 %.

**And those 90 unmeasured bytes are the most interesting number here**, because they are not
un-recovered code: they are `actor_hop_or_flip_side` (`$2b5a`, 40 B) and `actor_turn_and_launch`
(`$2b8e`, 58 B), both reconstructed, both green, both in **no `F` record at all** — Ghidra has one
20-byte function for the three-routine cluster. So the actor row is the first in this file whose
coverage is below 100 % *because the measurement under-counts the reconstruction*, not the other way
round.

**One row is a genuine surprise: `stage (load + reset)` is direct-T0 and transitive-T4.** All three
of its functions touch no hardware themselves, but `stage_load_window` (`$f95c`) ends with
`lea $17adc,a1` + `jsr (a1)` ($fa1e) / `jsr 28(a1)` ($fa28) into the sound module — both tail arms call it — so 210 of its 458 bytes are unrunnable behind the
PSG wall §6 prices. Only `interrupt (VBL)` had that shape before, through the same module and the
same kind of edge (`vbl_handler`'s `jsr 14(a0)`), and it is one 52-byte function. This is what stops
the background-scroll story being closed end to end: the three builders below it are green, and the
routine that calls them is not portable until (a) in §7 is built.

**Four limitations of this re-measure, stated with it:**

* **The Ghidra DB is stale relative to `../names.txt`, and unlike §0 that now COSTS figures.** §0
  could say the staleness changed nothing because all 171 `fn` addresses were already `F` records.
  There are 212 now and **four are not**: `$2b5a` and `$2b8e` (in no function at all, 90 bytes),
  `$fe8c` (inside `$fe4a`'s body — two routines with an entrant each that Ghidra folds into one) and
  `$17f30` (`snd_psg_silence`, inside `$17f24`'s body). `ApplyNames` creates a function for each, so
  **a re-scan would move the measurement**: roughly 252 → 256 functions and 25,696 → 25,786 bytes,
  with actor +2 fns / +90 B, stage +1 fn and sound +1 fn at unchanged bytes. Every range in
  `subsystems.tsv` already contains all four addresses, so the re-scan would change these rows'
  contents and not the partition. Until it is run, this file's actor and stage rows are **lower
  bounds by construction** and the 90 bytes above are the whole of the error.
  *(Discharged 2026-08-05 — §0c ran the reapply + re-scan and it landed exactly on this
  prediction: 256 functions, 25,786 bytes, actor +2 fns / +90 B, stage +1 fn and sound +1 fn at
  unchanged bytes.)*
* **The HUD has no subsystem, and that is now the largest known mis-partition.** Moving `$e80c` out
  of `boot` exposed it: the status panel is ~30 reconstructed functions spread over `$b346..$bd8a`,
  the restore routines at `$d93a..$db9x`, the effect stubs at `$10200..$103ee` and now `$e80c`, and
  every one of them is in the catch-all. It is not drawn here because the campaign has not
  established that those ranges *tile* — the §0 discipline is that a range is cited from a batch's
  own read, and `panel_refresh_frame` (`$b346`) is still unported and blocked. **Registered as the
  next queued measurement, not as a to-do inside this one.**
* **`resource_table_relocate` is charged to `resource loader` on its callers, not on its data.**
  What the 20-byte records at `$248d8` hold is not established (`STATUS.md` says so); what is
  established is that the table is disk-loaded, that the routine's one caller is
  `show_data_disk_prompt`, and that its two operand addresses have all nine of their sites on the
  boot resource-install path. If that table turns out not to be the resource table, one row moves by
  44 bytes.
* **The unmeasured bulk is still untouched.** 29,158 bytes are in no function and so in no tier;
  24,810 of them are now charged to game logic. Two re-measures have not reached one of them.

Confirmed by reading it, and then by running code through it (§4):

| tier | what the shim does | consequence |
|---|---|---|
| **modeled** | byte write to `$ff8800`/`$ff8802` → ordered `(reg, val)` ledger | diffable |
| **hard reject** | ANY read of `$ff8800..$ff88ff` at any width; any 16/32-bit access to the block; a byte write to the odd aliases | `emu.run` raises; the run cannot complete — unless the kit's opt-in audio-capture mode is armed, which serves the `$ff8800` byte read-back (`tools/recreate_kit/README.md`, "Opt-in: audio capture") |
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

## 0c. Re-scanned 2026-08-05 — the reapply + re-scan; the staleness limitation discharged

This one is not a re-partition: `subsystems.tsv` did not change, no code changed, no test moved.
`../reapply.sh` pushed `../names.txt` (212 `fn`, 202 `var`, 325 `cmt`, 36 `proto`) into the Ghidra
DB and `tools/hw_scan.sh` re-dumped `out/hw_scan.tsv` — the first re-scan since the figures in this
file were taken. **Pinned first:** the OLD scan, re-classified with today's `subsystems.tsv`,
reproduces every committed figure above bit-for-bit (252 fns / 25,696 B / 220 / 21,534 runnable /
28 / 3,348 at risk), so everything that moved below is the re-scan and nothing else.

**§0b's prediction was exact.** `ApplyNames` created the four missing functions, and the
measurement moved by precisely the announced amounts:

| | before | after |
|---|---|---|
| functions / function bytes | 252 / 25,696 | **256 / 25,786** |
| disassembled bytes | 27,986 | **28,076** |
| runnable end-to-end | 220 fns / 21,534 B (83.8 %) | **223 / 21,624 B (83.9 %)** *(→ 222 / 21,334 B / 82.7 % after §0d)* |
| false-green risk | 28 fns / 3,348 B (13.0 %) | **28 / 3,348 B (13.0 %)** |
| actor (table + lifecycle) | 14 fns / 864 B, coverage 90.6 % | **16 / 954 B, 100.0 %** |
| stage (load + reset) | 3 fns / 458 B, runnable 2 / 248 B | **4 / 458 B, runnable 3 / 248 B** |
| sound (YM2149) | 21 fns / 2,634 B, direct-T0 19 / 1,844 B | **22 / 2,634 B, direct-T0 20 / 1,856 B** |
| verified column (answer box) | 133 F records / 13,082 B | **136 / 13,172 B** |

The four F records, by what each did to the measurement:

* **`$2b5a` `actor_hop_or_flip_side` (40 B) and `$2b8e` `actor_turn_and_launch` (58 B)** — the 90
  bytes of reconstructed-and-green code that were in no function body. Both T0, both runnable; the
  actor row is no longer a lower bound and "reconstructed & green" no longer under-counts.
  (`$2b82` shrank 20 → 12 B: its F record loses the shared `$2b7a` tail, which now sits — and is
  measured — inside `$2b5a`'s body, where the code lays it out.)
* **`$fe8c` `game_life_restart_reset` (70 B)**, split out of `$fe4a` (136 → 66 B). Both T0 and
  runnable, so the stage row gains a function at unchanged bytes.
* **`$17f30` `snd_psg_silence` (82 B)**, split out of `$17f24` (94 → 12 B), and it takes **all
  nine PSG accesses** of the old blob with it. `$17f24` (`snd_stop`) becomes direct-T0 — the sound
  row's direct-T0 +12 B — but stays transitive-T4: its `bra.w` tail runs to `snd_stop_all_sfx`
  (`$1aaea`), whose own tail-jump now resolves to `$17f30`'s entry (a `JUMP` edge where the old
  scan had a `JUMPIN` into the middle of the blob).

**One new blind spot surfaced by the split, stated with the result: a fall-through between two
functions is no instruction, so it is no `E` edge.** `game_restart_reset` (`$fe4a`) ends with
`clr.w $bd6a.l` and falls straight into `$fe8c` — real control flow in neither ledger, the same
class as the `$bca2` drop (`STATUS.md`, batch 3). While the two shared one F record the graph hid
it; split, `$fe8c` has **no incoming edge at all** (its other caller, `jsr $fe8c.l` at `$c00`, sits
in code outside every F record and contributes nothing), so `$fe8c` and its callee `hud_draw_lives`
(`$e80c`, 112 B) moved to the UNREACHABLE side of the roots table — 112 fns / 10,714 B → 116 /
10,986 B — even though the game reaches both. Tier-neutral today (that whole subtree is T0), and
the runnable/false-green columns are unaffected; it is the reachability column that now
under-counts. `$2b5a` is NOT this case — it ends in `rts` before `$2b82`.

**And the `$bca2` anomaly REPRODUCES on a fully named DB** — same four `E 0xbbca 0xbcd6 CALL`
rows, same ten `I` rows, still no row of either kind for the `jsr 56(a1)` at `$bca2`. One
candidate explanation is now eliminated: the jump-target thunk `$17b14` **is** an F record in both
scans (14 B), so this is not `emitTransfers`' silent else-path (a resolved flow landing in no
function). Still undiagnosed; the register entry in `STATUS.md` carries the narrowed state.
*(Diagnosed and closed the same day — §0d below. The elimination above was itself wrong: it
checked the wrong address, and the else-path WAS the drop site.)*

## 0d. The `$bca2` diagnosis (2026-08-05, batch 16a): ten dropped edges, one sleigh defect

**The mechanism.** Ghidra's 68000 language models `jsr/jmp (d16,An)` one dereference too deep:
`68000.sinc`'s `addrRegD16` operand exports a *memory* varnode and the instruction is spelt
`call [operand]`, so the pcode LOADs four bytes at the effective address and calls THOSE — a real
68000 transfers control TO the EA and reads nothing. Constant propagation therefore "resolved"
`$bca2` to `0x48e7fffe` — the `movem.l` opcode STORED AT the true target `$17b14` — which is in no
function, so `emitTransfers`' no-target else-path dropped the site, and the non-empty flow list
kept it out of the `I` ledger. In neither ledger, exactly as registered. **Ten of the image's
eleven mode-5 indirect calls were dropped this way** (`$594 $a9e $1732 $67a2 $6aea $6b54 $6bd0
$6be8 $bca2 $fa28`); the eleventh (`$726`) resolved nothing and was the one honest `I` row of its
class. The ten pre-existing `I` rows were all mode-2 `jsr (An)`.

**The fix** (`tools/ghidra_scripts/HwPortabilityScan.java`): when a computed transfer's pcode
reaches its target through a `LOAD`, the EA the propagator really computed survives as the
instruction's READ data reference — take that as the edge target; and emit `I` whenever a computed
transfer produced no row at all. The invariant is now stated and kept: **every call/jump in
exactly one ledger.** 68000-specific by design (an x86 `call [reg+d]` dereference is genuine).
No test can live outside Ghidra; the pin is this before/after record, and the scan is idempotent.

**What moved (old → new), every delta explained:** ten new `E` rows, none removed, the ten `I`
rows byte-identical. Three of the new rows come from code in no F record (`$a9e`/`$1732`/`$67a2`)
and enter `edge_kinds` but not the graph. Edges 233 → 240 (CALL 369 → 379).
`panel_frame_timers` (`$bbca`) is now honestly `→ $17b14 → snd_trigger_effect` and **stays
T0/runnable** — the subtree is clean, which the §6 probe (61 insns, empty PSG ledger) had already
corroborated. `$69fe`/`$6b46` gained the same clean thunk edge, unchanged tiers. The one real
casualty: **`game_routine_6bb8` (290 B), T3 → T4** — its `jsr 28(a1)` lands on `$17af8 → snd_stop
→ snd_stop_all_sfx → snd_psg_silence`, whose `move.b $ff8800,d1` is a PSG read. So **runnable
223 fns / 21,624 B (83.9 %) → 222 / 21,334 B (82.7 %)** — the scan was pricing a sound-walled
routine as clean. Reachable +4 fns / +376 B, all T0 (`$17b14`, `$17b30`, `$17f92`, `$1a48a`),
unreachable 116 → 112. False-green risk, the site census, the roots table's tiers and the steering
table are unchanged — no `H` row moved. `portability_predictions.py`: 14/14 green, no case pinned
the old behaviour.

**§2–§8's figures move by exactly these deltas and no other.** The fall-through blind spot
(`$fe4a`/`$fe8c`, `$bf4e`) is a different mechanism — no transfer instruction exists — and stays
open above.

## 0e. The HUD partition (2026-08-05, batch 18): the largest mis-partition, drawn

The measurement queued since batch 15's re-measure ("THE STATUS PANEL HAS NO SUBSYSTEM") and
unblocked by 16b ($b346 ported). **No code changed and no test moved**; `subsystems.tsv` gained
four `hud (status panel)` ranges, cited on the spot: `$b346..$bd66` (the pass, its ten callees and
every tier under them — ending at `hud_draw_two_digits`' body end, the panel's own state words
filling `$bd66..$bd8a`), `$d93a..$dbb0` (the region-restore family; NOT `$dbc0`, which is unported
game logic), `$10200..$103e8` (the effect/state stubs that write the panel's slots, meter and
state words), and `$e80c` (`hud_draw_lives`).

**Pinned before touching anything**: the unmodified partition reproduces every §0d figure —
222/256 runnable, 21,334 B, 82.7 %, false-green 28/3,348, all fifteen subsystem rows. The re-run
then differs in EXACTLY ONE hunk of the subsystem table:

| | before | after |
|---|---|---|
| hud (status panel) | — | **62 fns / 3,372 B, T0 CLEAN direct AND transitive, runnable 62/62, 100 % reconstructed** |
| game logic | 86 / 6,700 B, runnable 76 / 4,662 B | **24 / 3,328 B, runnable 14 / 1,290 B** |

Every whole-program figure is unchanged (diffed, not argued). The HUD row is the file's cleanest:
the only whole subsystem that is simultaneously 100 % measured-runnable and 100 % reconstructed
across four disjoint address ranges. The catch-all — 138 functions before the first re-measure —
is down to 24, of which `FUN_0000dbc0` (932 B, unported, unnamed) is the largest single remainder.

**Also discharged here**: batch 15's queued `video (sprite blitters)` row re-measure — §0d's run
already used the redrawn `$8f02..$989c` range (13 fns / 2,458 B, 100 %), and today's baseline pin
makes that explicit; the row is byte-identical in both of this section's runs.

## 0f. The scene row (2026-08-06, batch 20): the first subsystem where RECONSTRUCTED exceeds RUNNABLE

The measurement batch 19 queued. Baseline pinned (every §0e figure reproduces), two rows drawn
with their citation (`$dbc0..$df9e` ending at `actor_slots_mark_free`'s entry, and
`$dfbe..$e026`), and the re-run differs in one table hunk:

| | before | after |
|---|---|---|
| scene (dialogue + shop) | — | **3 fns / 1,094 B, direct T0 CLEAN, transitive T4, runnable 0** |
| game logic | 24 / 3,328 B, runnable 14 / 1,290 B | **21 / 2,234 B, runnable 14 / 1,290 B** |

**The shape is the finding.** No scene function touches hardware (direct T0), and none can be run
WHOLE under the oracle (transitive T4): every one reaches `stage_load_window`'s sound call through
the exit tails. Yet two of the three are RECONSTRUCTED and green — 990 of 1,094 bytes — because
batch 19 ported them to a `stop_pc` boundary with the kit's coverage bitset witnessing the
transfer. So this row is the first where the reconstructed column exceeds the runnable one, and
that is not a contradiction: "runnable" prices what the oracle can execute end-to-end, and the
boundary convention is what porting does when the answer is "not quite". The catch-all's runnable
column did not move — all three departures were already in its unrunnable residue.

Every whole-program figure is unchanged (diffed, not argued).

Two checks that make the re-scan trustworthy as a baseline: the OLD-scan pin above, and a
`dump_names.sh` round-trip — every one of the 212 `fn` and 202 `var` lines in `../names.txt` comes
back verbatim (`# ctx` tags stripped, as specified); the dump's only extra line is `fn 0x3f8
_start`, the loader's own entry symbol.

**§2–§8 below still print the 2026-08-02 report.** Every figure they quote differs from today's
scan by exactly the deltas in this section and no other — no tier boundary moved, no hardware site
appeared or vanished (126 classified accesses before and after; the nine PSG sites merely
re-attributed from `FUN_00017f24` to `snd_psg_silence`), and the name strings are now
`../names.txt`'s. The remaining limitation is unchanged from §0b: 29,068 bytes are still in no
function body, and nothing here reached one of them.

## 0g. The classifier repaired against kit Phase 6 (2026-08-07, batch 22c): the PSG wall is gone

Batch 22b's blocked re-measure, discharged. **No game code changed, no test moved, no scan was
re-generated, `subsystems.tsv` untouched** — the only edited file is `tools/hw_portability.py`,
run read-only over the *same* committed `out/hw_scan.tsv` §0e/§0f were measured on, so every
number below is a pure re-pricing of unchanged evidence.

### What broke, and the repair

Two defects, fixed and validated in that order.

**1. The constants pin named the wrong file.** `check_shim_agreement()` looked for `PSG_SELECT`
and `PSG_DATA` in `oracle/shim.c`; kit Phase 6 (`bd86412`) deleted both and moved the canonical
pair to `include/os.h` as `OS_PSG_PORT_SELECT` / `OS_PSG_PORT_DATA`, same values. The pin is now
**per-file** — `PINNED_CONSTANTS` maps each kit file to the constants that file owns — so a
constant that MOVES again fails with the instruction to re-point its entry rather than to delete
it. Verified by mutation on a throwaway copy of the kit, repo untouched: renaming
`OS_PSG_PORT_SELECT` exits 1 (the Phase 6 break, replayed), changing `OS_PSG_PORT_DATA`'s value
exits 1, changing shim.c's `PSG_BLOCK_END` exits 1, and a checkout with **no** kit still
classifies (exit 0) — the one case that must not fail.

**2. The T4 read rule had drifted, and it was the expensive one.** The rule said *any* PSG-block
access that is not a modeled byte write is a hard reject. Phase 6 made that false for one access
class: `shim.c`'s `psg_read_back()` **serves** a byte read of `$ff8800` from the seeded register
file and records it in the same ordered ledger as the writes, refusing only when the case declared
no seed (`psg_seed={reg: byte}`) or nothing selected a register. That is a *case obligation*, not a
fidelity hole — which is a tier of its own, and the tool had no such tier.

### The rule, now

A new **`T2 PSG_SEEDED_READ`** sits between `T1 PSG_WRITE_ONLY` and the hardware-write tier, and
everything above it renumbers. The report's own prose now derives those numbers from `TIER_NAMES`,
so the next insertion cannot leave stale citations behind.

> ### The old→new tier mapping — READ THIS BEFORE COMPARING ANY NUMBER ABOVE
>
> **Every section of this file above §0g uses the old numbering** — not only §2–§8 (the 2026-08-02
> report), but §0, §0b, §0c, §0d, §0e and §0f, which quote tiers throughout (§0's "transitive-T4",
> §0b's and §0d's "T3 → T4", §0f's "transitive T4"). Nothing up there is wrong; it is stated in the
> vocabulary of its day. **Two numbers changed MEANING rather than merely position**, so a careless
> read silently inverts them:
>
> | old | new | note |
> |---|---|---|
> | `T0 CLEAN` | `T0 CLEAN` | unchanged |
> | `T1 PSG_WRITE_ONLY` | `T1 PSG_WRITE_ONLY` | unchanged |
> | — | **`T2 PSG_SEEDED_READ`** | **new** |
> | `T2 HW_WRITE_ONLY` | `T3 HW_WRITE_ONLY` | ⚠ old `T3` meant HW_READ; new `T3` means HW_WRITE_ONLY |
> | `T3 HW_READ` | `T4 HW_READ` | ⚠ old `T4` meant HARD_REJECT; new `T4` means HW_READ |
> | `T4 HARD_REJECT` | `T5 HARD_REJECT` | where §0–§0f's "T4" walls live |
> | `T5 UNMEASURABLE` | `T6 UNMEASURABLE` | the Copylock exclusion |
>
> So §0d's "`$bca2` is T4" and §0f's "transitive T4" both mean **HARD_REJECT**, today's `T5` — and
> §0g's tables below restate exactly those facts in the new labels. History is not rewritten here;
> the bridge is.

It ranks **below** the write-drop and
fabricated-read tiers because the ordering is *how much a differential still verifies*, not how
much work a run costs: nothing about a seeded read is invisible or invented — the byte is declared
by the case and both sides see it — and an undeclared one is refused loudly, so the tier can never
be a silent green, only a red until seeded. **Hard-reject keeps everything that still
hard-rejects**: a read of the write-only data port `$ff8802`, a read of any block mirror, ANY
16/32-bit transfer touching the block (including one starting at `$ff8800`, and one straddling in
from below), any odd-alias write, and any access Ghidra could not size.

**All of it is pinned by a committed suite: `tools/test_hw_portability.py`, 37 cases, standalone
`pytest tools/test_hw_portability.py`.** *(Marked in place — §0i: **56 cases** now, and the
`$fffa01` lattice row and the false-green positive control both moved there. The three groups below
still describe its shape, with the per-group counts restated so they reconcile: the lattice group is
**33** cases — **25 access shapes** (was 16), 5 parametrized false-green exclusions, the positive
control, and the tier order/runnability assertions; the tripwire group is **16** cases from
**11 mutations** (was 8); the arithmetic-and-report group is **7**. 33 + 16 + 7 = 56.)* It lives beside the tool rather than under any project's
`recreate/test/` because the tool is game-agnostic — it pins `tools/recreate_kit`'s model, not this
game's behaviour — and it is deliberately **not** wired into any `make test`, which builds an
oracle `.so` the suite never needs. Three groups: the 16 lattice shapes above, the 8 tripwire
mutations against throwaway copies of the kit, and the whole-program arithmetic off the committed
scan. **Mutation-tested against itself**: eight deliberate defects reintroduced into the tool (the
tier rule, the size check, the false-green exclusion, the lattice order, and each of the four pin
weaknesses the review found) — all eight caught, none survived. One caveat worth carrying: two of
those mutations are byte-length-preserving, and a same-length edit restored within the filesystem's
mtime granularity makes Python reuse cached bytecode and report a phantom survivor. Purge
`__pycache__` between mutation runs.

**The silent-zero class was checked and is NOT drifted.** Reads of `$fffa01` (MFP GPIP) and
`$ff820a` (shifter sync) price as `T4 HW_READ` — the false-green class — which is the truth:
Phase 6 gave them real answers only under the opt-in audio-capture mode, and off that mode
`m68k_read_memory_8` still falls through to `return 0`. No differential runs under capture, so
they were never rejects and are not clean.

> *(RETIRED — §0i. This paragraph was true of kit Phase 6 and is **false as of Phase 7**: those two
> bytes are now a seeded model of their own, served from the case's `hw_seed=` on both cores off any
> mode, ledgered, and REFUSED by a differential when undeclared. They price as `T2 SEEDED_READ`
> today, and the audio-capture mode is a seed installed over that model rather than a switch of its
> own. §0i re-derives the rule and names every figure it moved; the tables below are left as the
> measurement of their day.)*

### Before → after, every moved figure named

**Stage 1, the constants fix alone, changed nothing.** Pinned before touching the tier rule: the
classifier reproduces every committed §0e/§0f figure byte-for-byte — 222/256 runnable,
21,334 / 25,786 B, 82.7 %, false-green 28 / 3,348 B, all nineteen subsystem rows.

**Stage 2, the tier re-derivation**, moves exactly 20 functions, all in one direction:

| | before | after |
|---|---|---|
| Runnable end-to-end | 222 / 256 fns, 21,334 / 25,786 B, **82.7 %** | **242 / 256 fns, 24,318 / 25,786 B, 94.3 %** (+20 / +2,984 B) |
| False-green risk | 28 fns / 3,348 B | **28 fns / 3,348 B — unchanged** |
| Direct `HARD_REJECT` | 3 fns / 806 B | **0 — the row is gone from every table** |

Nothing moved the other way, and the steering set is identical function-for-function: a PSG read is
excluded from the false-green count under both rules, and since Phase 6 for two different reasons —
a refused one never completes the run, a served one is steered by a *declared* input.

**Three functions moved by their own access** (direct tier):

| fn | bytes | before | after | why |
|---|---:|---|---|---|
| `$624c` `psg_set_drive_select` | 28 | T5 HARD_REJECT | **T2** | its `$6254` `move.b $ff8800,d1` is the served read-back; its two writes are the modeled pair |
| `$17f30` `snd_psg_silence` | 82 | T5 HARD_REJECT | **T2** | batch 21b's mixer RMW at `$17f3e` — reconstructed and GREEN, and the classifier now agrees |
| `$17c74` `snd_music_tick` | 696 | T5 HARD_REJECT | **T4 HW_READ** | its `$17f08` read-back is served, so what prices it is no longer the PSG at all but its own `mfp-R!` + `shifter-R!` — it stays in the false-green 28 *(marked in place — batch 25: the two `mfp-R!`/`shifter-R!` sites are now DECLARED case inputs and a differential of them that names no machine is refused, so the false-green membership is stale. The FIGURE is a measurement and is left as the scan produced it; re-pricing the tier is the `tools/hw_portability.py` pass §7 already queues.)* **(DISCHARGED — §0i: that pass ran. `$17c74` is `T2 SEEDED_READ` today, direct and transitive, and it is out of the false-green set along with 7 others.)** |

**Seventeen more moved through the call graph.** To T2, behind a seeded read: `$716`
`vbl_handler` (52 B, via `floppy_deselect_drives`→`psg_set_drive_select`), `$6268`
`floppy_deselect_drives` (16 B), and six behind `snd_psg_silence` — `$17adc` `snd_stub_00` (14 B),
`$17af8` (14 B), `$17b22` (14 B), `$17b3a` `snd_play_song` (140 B), `$17f24` `snd_stop` (12 B),
`$1aaea` `snd_stop_all_sfx` (26 B). To T4, behind `snd_music_tick`: `$17aea` (14 B). To T3
HW_WRITE_ONLY, behind `stage_load_window`→`set_palette`: `$f95c` `stage_load_window` (210 B),
`$dbc0` (932 B), `$de80` (58 B), `$dfbe` (104 B), plus `$1ab4` (60 B), `$e032` (118 B) and `$e0a8`
(104 B).

**One witness path changed, and it is the interesting one.** `$6bb8` `game_routine_6bb8` — batch
21b/22's `actor_defeat_and_score`, 290 B, 29 callers — was priced hard-reject *behind
`snd_psg_silence`* in §0d. Its sound callee is now T2, so its verdict is re-derived from a
different edge entirely: **T4 HW_READ, witness `game_routine_6bb8 → FUN_0000e1f0 → rng_next`**, the
video-counter read. Runnable, and not in the false-green set (that `shifter-R` does not steer).

**Six subsystem rows move; the other thirteen change only their tier LABEL:**

| subsystem | before | after |
|---|---|---|
| sound (YM2149) | worst T5 HARD_REJECT direct **and** transitive, runnable 13 / 1,622 B | **T4 HW_READ / T4 HW_READ, runnable 22 / 2,634 B — the whole subsystem** (+9 / +1,012) |
| scene (dialogue + shop) | direct T0, transitive T5 HARD_REJECT, runnable **0** | **transitive T3 HW_WRITE_ONLY, runnable 3 / 1,094 B** (+3 / +1,094) |
| game logic | runnable 14 / 1,290 B | **18 / 1,862 B** (+4 / +572) |
| disk (WD1772 FDC + DMA) | worst T5 HARD_REJECT, runnable 18 / 640 B | **T4 HW_READ, runnable 20 / 684 B** (+2 / +44) |
| stage (load + reset) | transitive T5 HARD_REJECT, runnable 3 / 248 B | **T3 HW_WRITE_ONLY, runnable 4 / 458 B** (+1 / +210) |
| interrupt (VBL) | transitive T5 HARD_REJECT, runnable **0** | **T2 PSG_SEEDED_READ, runnable 1 / 52 B** (+1 / +52) |

**§0f's headline shape is dissolved.** The scene row was "the first subsystem where RECONSTRUCTED
exceeds RUNNABLE" — 990 of 1,094 bytes ported against 0 runnable — precisely because all three
functions reached `stage_load_window`'s sound call. Under the re-derived rule all three are
runnable whole. The observation §0f made was true of the classifier as it then stood, not of the
oracle as it then behaved; Phase 6 had already landed when §0f was written.

**One table shrank.** The three PSG rows left "Hardware reads whose fabricated value is STORED"
(`$6254`, `$17f08`, `$17f3e`). A served read-back is a **declared** input, not a fabricated one,
and a refused one never reaches the store — listing either under that heading was the opposite of
what happens. They read as `psg-R` in the hardware-functions table, where the tier says which.

### §6's biggest predicted lever has been built

§6 priced a hypothetical "PSG read model" as the single largest lever for *can it run at all*, and
warned that a write-ledger replay would not do — the game needs "a **seeded post-TOS PSG register
file** that the write ledger then updates". That is exactly what Phase 6 built. Measured, not
argued: the re-derived rule with **no flags** produces the identical figure to the OLD rule run
with `--model psg:read` on this scan — **242 fns / 24,318 B, both**. The hypothetical is now the
default, and `--model psg:read` on top of it buys nothing further.

### Still queued (orchestrator's next steps, not this batch's)

1. `../reapply.sh` + `tools/hw_scan.sh`, **re-baselined in its own section** — batch 22b's
   two-stage pin, unchanged: the re-scan moves whole-program figures by itself (256 → ~258 F
   records, `$6bb8` re-cut). *(DISCHARGED — §0h. 258 F records as predicted; the `$6bb8` re-cut
   moved no bytes, and the reason is a correction §0h states.)*
2. **Then** the `subsystems.tsv` partition edit batch 22 queued (`0x6cdc 0x6d5a` → actor lifecycle,
   `0xe1c8 0xe222` → stage tier), which changes nothing against the *committed* scan.
   *(DISCHARGED — §0h, stage 2.)*
3. **§6 / §6.1's capability table is now stale** and needs re-pricing: its baseline row is the
   2026-08-02 scan, and its "PSG read model" row prices a capability that ships. More broadly,
   **every section above this one states tiers in the old numbering** — bridged, not rewritten, by
   the mapping table in "The rule, now" and by the pointer at the top of this file. Re-stating them
   in place is a separate pass, and should happen only when a section is being re-measured anyway;
   editing a historical record's numbers without re-running its measurement would make it claim
   something nothing verified.
4. `notes/portability_predictions.py` needs a prose pass — **its assertions were checked by reading,
   not re-run here** (a concurrent port session owns `recreate/`, and the script builds the oracle
   `.so`). Its header describes the old six tiers. More substantively, its two `T4` cases
   (`case_t4_psg_set_drive_select`, `case_t4_sound_psg_read`) match `emu.run`'s refusal with the
   regex `accessed the PSG ports .* cannot serve` — which batch 21b's Phase 6 wording deliberately
   preserved on the **unseeded** cause, so both cases still pass **for a different reason than they
   claim**: those runs are refused because the case declares no `psg_seed`, not because the read is
   unservable. The docstrings ("the shim refuses outright — so the whole floppy stack above it can
   never run") are now false, and the honest rewrite is a pair of cases that assert BOTH halves: the
   refusal without a seed, and a green run WITH one.

## 0h. The re-scan and the partition edit (2026-08-07, batch 22b steps 2–3): two functions appear, and the score table was never counted

Batch 22b's remaining two steps, run as the two-stage pin it specified. **No game code changed and
no test moved**; the edited files are `subsystems.tsv` (two ranges) and this section, and
`../reapply.sh` + `tools/hw_scan.sh` regenerated `../decomp.c` and `../out/hw_scan.tsv`.

**Stage 0, the floor.** The repaired classifier over the **old** scan reproduces every §0g figure
byte-for-byte — 242/256 runnable, 24,318 / 25,786 B, 94.3 %, false-green 28 / 3,348 B, all nineteen
subsystem rows — so everything below is the re-scan and the partition edit, and nothing else.

### Stage 1 — the re-scan, and the prediction that was half wrong

`ApplyNames` pushed `../names.txt` (227 `fn`, 237 `var`, 377 `cmt`, 36 `proto`) into the DB and the
re-scan re-dumped the TSV. **Exactly two `F` records appear, one changes size, and not one
pre-existing function moves tier, steering or reachability** (checked function-by-function against
the old scan, not argued):

| | before (2026-08-05 scan) | after |
|---|---|---|
| functions / function bytes | 256 / 25,786 | **258 / 25,826** (+40) |
| disassembled bytes | 28,076 | **28,116** (+40) |
| call-graph edges | 240 (379 CALL, 8 JUMP, 21 JUMPIN) | **245 (381 CALL, 9 JUMP, 23 JUMPIN)** |
| hardware accesses (`H` rows) | 126 | **126 — byte-identical, every row** |
| direct `T0 CLEAN` | 225 / 22,598 B | **227 / 22,638 B** |
| transitive `T4 HW_READ` | 24 / 2,658 B | **26 / 2,698 B** |
| runnable end-to-end | 242 / 21,334→24,318 B, 94.3 % | **244 / 258 fns, 24,358 / 25,826 B, 94.3 %** |
| false-green risk | 28 fns / 3,348 B | **28 / 3,348 B — the identical function set** |
| unreachable from the roots | 112 / 10,610 B | **114 / 10,650 B** |
| `game logic` (catch-all) | 21 fns / 2,234 B | **23 / 2,274 B** |

**The two new `F` records, and the `names.txt` entry that creates each:**

* **`$6cdc` `actor_respawn_as_new_kind` (126 B)** — batch 22's respawn continuation, until now folded
  inside `$6bb8`'s body. Direct `T0`, transitive `T4 HW_READ`, runnable, not steering.
* **`$e1c8` `stage_random_kind32` (40 B)** — batch 22's 32-wide draw, which the old scan had **no
  entry for at all**: it sat in no function body, so its bytes were in no tier and its edges in no
  ledger. Direct `T0`, transitive `T4 HW_READ`, runnable, not steering. It is the whole +40.
* **`$6bb8` `actor_defeat_and_score` 290 → 164 B**, the only size change in the program.

Nothing else moved. The other 2026-08-06/07 names — batch 21b's and batch 23's `$17b14`
`snd_call_trigger_effect`, `$18106` `snd_channel_step`, `$18208` `snd_channel_period_and_volume`,
`$1a5da` `snd_sfx_tick`, `$1a602`/`$1a6bc`/`$1a776` `snd_sfx_tick_channel_a/b/c`, `$1aaca`
`snd_prng_step`, and batch 19/20's `$8f02` `sprite_draw_pass`, `$dbc0` `scene_run_frame`, `$de80`
`scene_spend_visit_budget`, `$dfbe` `scene_exit_and_reload`, plus `$69fe`/`$6b46`'s rename from
`damage_path_*` — **name existing `F` records and change no figure**. Their data neighbours
(`$1aae6` `snd_prng_state`, `$1a830` `snd_sfx_ptr_table`, `$18352` `snd_psg_shadow`) are `var`
lines, so they correctly produce no `F` record and enter no denominator, exactly as this file's
"ONLY CODE BELONGS HERE" rule requires.

**The five new edges are the re-cut spelt out** (one removed, six added):

| edge | why |
|---|---|
| − `0x6bb8 → 0xe1f0 CALL` | the `bsr` at `$6d04` now sits inside `$6cdc`, not `$6bb8` |
| + `0x6cdc → 0xe1f0 CALL` | the same instruction, re-attributed |
| + `0x6cdc → 0xe1c8 CALL` | the `bsr.w` at `$6cf2`, previously an intra-body branch |
| + `0x6bb8 → 0x6cdc JUMP` | the `ble.w $6cdc` at `$6c34` — the continuation edge |
| + `0x6cdc → 0x6bb8 JUMPIN` | the `bmi.w $6c38` at `$6d0a`, the retire tail's **third** entrance |
| + `0xe1c8 → 0x68c6 CALL` | `stage_random_kind32`'s own `bsr rng_next` — in no ledger before, because its code was in no `F` record |
| + `0xe1c8 → 0xe1f0 JUMPIN` | the `bra.w $e214` into `stage_random_kind8`'s shared fourteen-byte tail |

That last pair is why `$6cdc` and `$e1c8` price `T4 HW_READ` rather than `T0`: both reach `rng_next`
and its `$ff8209` video-counter read *(`T2 SEEDED_READ` since batch 33 modeled that byte — §0j's
transitive-`T4` note)*. `$6bb8` is unchanged at `T4 HW_READ` — §0g's witness path
(`game_routine_6bb8 → FUN_0000e1f0 → rng_next`) is now `actor_defeat_and_score → actor_respawn_as_new_kind
→ stage_random_kind8 → rng_next`, one hop longer and the same verdict.

**The score-table prediction was wrong, and the correction is worth carrying.** Batch 22b and §0g
both expected the re-cut to move whole-program bytes because `$6bb8`'s 290 "folds in the 128-byte
score table at `$6c5c`". It does not, and never did: **Ghidra's `F` size is the cardinality of a
function's address SET, not `body_end − entry`.** The old record was `0x6bb8 / 290 / body_end
0x6d5a` over a 418-byte span — already discontiguous, already skipping the table's 128 bytes.
164 + 126 = 290, so the re-cut splits one body into two at unchanged total bytes and merely makes
the hole explicit (`$6bb8` drops off the scan's discontiguous list, which is now nine records:
`$53e`, `$1492`, `$5e3e`, `$dbc0`, `$e782`, `$ecca`, `$ee02`, `$17c74`, `$1a5da`). **The whole
+40 is `$e1c8` alone.** Anywhere this file reasons about a body's extent from `body_end − entry`,
that is the trap; `$1a5da` is the mirror case — 42 bytes over a 40-byte span, because its address
set includes the shared `rts` at `$1a5d8`, two bytes *below* its entry.

### Stage 1 sanity — the verified-and-green column against `STATUS.md`'s 166

`STATUS.md` records **166 verified reconstructions / 19,226 bytes**; expanding its four family
legends (16 scroll copies, 4 sprite blitters, 4 clip-left, 4 clip-right) over its 142 verified rows
reproduces that 166 exactly. Against the new scan those map to **171 `F` records / 19,226 bytes** —
the bytes agree to the byte, as they have since §0c, and the count differs by the two counting
rules §1 already documents. The reconciliation gains **one** entry, batch 23's:

| | reconstructions | F records | bytes |
|---|---:|---:|---:|
| `src/rad.c` — one reconstruction Ghidra splits into three (`rad_depack`, `rad_refill_bit_buffer`, `rad_get_bits`) | 1 | 3 | same 216 |
| `snd_sfx_tick` (`$1a5da`) — one reconstruction Ghidra splits into four: the 42-byte head plus the three 186-byte channel arms `$1a602`/`$1a6bc`/`$1a776` | 1 | 4 | same 600 |
| **net** | **166** | **171** | **19,226 = 19,226** |

Those two rows are the *only* per-row disagreements between `STATUS.md`'s byte column and the scan's
`F` sizes — checked row by row, all 142.

**Two stale figures this surfaces, flagged and NOT edited here.** `STATUS.md`'s "74.6 % of
everything `PORTABILITY.md` measures" is 19,226 / 25,786, the old denominator; against 25,826 it is
**74.4 %**. And §1's answer box still prints the 2026-08-02 scan (256 fns / 25,786 B / 47.0 %
coverage / 136 fns / 13,172 B reconstructed-and-green) — §0g left it stale too. Re-stating it means
recomputing its `CODE bytes` column against `notes/architecture.md` as well, which is a measurement
of its own and not this section's.

### Stage 2 — the partition edit

With stage 1 pinned as the baseline, `subsystems.tsv` gains the two ranges batch 22b drafted, cited
on the spot in the file itself: **`0x6cdc..0x6d5a` → `actor (table + lifecycle)`** and
**`0xe1c8..0xe222` → `stage (load + reset)`**, ONE range over both draws rather than a split at
`$e1f0`, because `$e1c8` has no tail of its own and `bra.w`s into `$e1f0`'s. **`$e1f0` was checked
first and was in no subsystem range** — it sat in the catch-all, so nothing had to be extended or
adjusted; the range claims two catch-all members rather than moving an existing boundary. The re-run
differs from stage 1 in **exactly three rows of the subsystem table, and no whole-program figure
moves** (diffed, not argued):

| subsystem | before | after |
|---|---|---|
| actor (table + lifecycle) | 16 fns / 954 B, transitive **T0 CLEAN**, runnable 16 / 954 B | **17 / 1,080 B, transitive T4 HW_READ, runnable 17 / 1,080 B** |
| stage (load + reset) | 4 fns / 458 B, transitive T3 HW_WRITE_ONLY, runnable 4 / 458 B | **6 / 548 B, transitive T4 HW_READ, runnable 6 / 548 B** |
| game logic (catch-all) | 23 fns / 2,274 B, direct T0 21 / 2,122 B, runnable 20 / 1,902 B | **20 / 2,058 B, direct T0 18 / 1,906 B, runnable 17 / 1,686 B** |

Both receiving rows stay fully runnable and carry no false-green risk, so the −216 bytes the
catch-all loses are 216 bytes of *verified* code leaving the least-characterised bucket. **The actor
row's cost is a label**: it was one of the six subsystems that were `T0 CLEAN` transitively, and
`$6cdc`'s path to `rng_next` ends that. The tier is honest — the row's runnable column is
unchanged at 100 % — but "clean end to end" is now five subsystems, not six.

**Declined, with the reason: the three batch-23 sound bodies need no range.** `$1aaca`
`snd_prng_step`, `$1a5da` `snd_sfx_tick` and `$18208` `snd_channel_period_and_volume` — and the
three channel arms `$1a602`/`$1a6bc`/`$1a776` with them — are **already inside** the existing
`0x17adc..0x1ab04` `sound (YM2149)` range, which covers the whole module in one span. Extending or
splitting it would move no function and change no figure, and the file's convention is that a range
exists to *claim* entries, not to annotate ones already claimed.

**Also observed and NOT folded in** (it is a partition question of its own, not batch 22b's drafted
edit): `$6bb8` `actor_defeat_and_score` (164 B) and its two damage-path callers `$69fe`
`actor_damage_followed` (266 B) and `$6b46` `actor_damage_template_hitpoints` (114 B) remain in the
catch-all while the continuation `$6cdc` they run into is now `actor (table + lifecycle)` — 544
bytes of verified defeat-path code split across two buckets by a boundary nothing has argued for.
That is the largest remaining actor-shaped remainder in a catch-all now down to 20 functions.

## 0i. The classifier re-priced against kit Phase 7 (2026-08-07): the two steering bytes are declared inputs now

Batch 25's queued re-pricing, discharged. **No game code changed, no test in `recreate/` moved, no
scan was re-generated, `subsystems.tsv` untouched** — the edited files are `tools/hw_portability.py`,
`tools/test_hw_portability.py` and this section, run read-only over the *same* committed
`../out/hw_scan.tsv` §0h was measured on. Every number below is a pure re-pricing of unchanged
evidence, exactly as §0g was.

### What Phase 7 changed, and what the classifier was still claiming

Kit Phase 7 (`ca05c87`; `tools/recreate_kit/TRAP_MODEL.md`, "Phase 7") makes a **byte read of
`$fffa01` (MFP GPIP) or `$ff820a` (shifter sync) a SEEDED CASE INPUT**: served on both cores from a
file the case declares with `hw_seed=`, recorded in an ordered read ledger `harness.differential`
compares, and — when the case declared nothing — **refused** by the differential rather than served
in silence. A 16/32-bit read taking one of those bytes in is recorded and never served, and refused
too. A write is dropped and tallied, and a read of an address *this run wrote* is refused as stale.

The classifier's `T4 HW_READ` rule still priced those two addresses as the silent-zero false-green
class, in as many words: *"Phase 6 gave them real answers, but ONLY under the opt-in audio-capture
mode, and no differential runs under it. Off that mode they still fall through to a silent 0."* That
sentence is **false for exactly those two bytes** as of Phase 7, and it was load-bearing three times
over — in the tool's tier rule, in `tools/test_hw_portability.py`'s `LATTICE_CASES` (which also used
`$fffa01` as the *positive control* for the false-green counter), and in §0g's prose above. All three
moved together.

### Stage 1 — the floor, and the Phase 6 pin break did NOT recur

Pinned before touching the tier rule, because §0g's first defect was a pin that Phase 6 had silently
broken: **`pytest tools/test_hw_portability.py` was green at 37/37 on the unmodified tool**, and the
report over the committed scan reproduced every §0h figure byte-for-byte — 258 functions / 25,826 B,
runnable **244 / 24,358 = 94.3 %**, false-green **28 / 3,348**, all nineteen subsystem rows.

The reason it did not recur is worth recording rather than being lucky twice: Phase 7 **added**
constants to `include/os.h` and added functions to `oracle/shim.c`; it moved nothing. A pin that
names a file the constant left is the break §0g repaired, and only a *move* can cause it. Phase 7's
own capture-profile rework, which did move code inside `shim.c`, touched no pinned `#define` and
kept `psg_read_back()` where it was.

### The rule, now — folded into T2, not given a tier of its own

`T2 PSG_SEEDED_READ` is renamed **`T2 SEEDED_READ`** and now covers a byte read of the PSG read-back
port *or* of a modeled hardware byte. The modeled set is drawn from the kit's canonical table —
`os.h`'s `OS_HW_MFP_GPIP` / `OS_HW_SHIFTER_SYNC`, pinned by name exactly as the PSG ports are, plus
`OS_HW_NSLOTS` pinned against the tool's own set SIZE (see the tripwire note below). Everything
outside that set is unchanged: a hardware read stays `T4 HW_READ`, silently 0.

**Why a fold and not a new tier.** The lattice's ordering principle (§0g) is *how much a differential
still verifies* — not what mechanism the kit uses, not what a run costs. Measured against that
question, a Phase 6 PSG read and a Phase 7 hardware read are the **same** thing: the byte is a
declaration of the case's, both sides see it, it is compared as an ordered ledger entry, and an
undeclared one is refused rather than guessed. A separate tier would have to sit somewhere in the
order, and there is no criterion to place it — which is the definition of a distinction the lattice
cannot express. Folding says the true thing; a seventh tier would have implied a difference in
verification strength that does not exist.

The one real asymmetry between the two halves was checked and is **not** an ordering difference: the
PSG refusal fires inside `emu.run` for every caller, the hardware refusal only inside
`harness.differential` (a bare run — the relocator, the Copylock, the bootstrap — is served the old
`0` and merely records it). That changes **who notices** an undeclared read, not what a differential
verifies, and this lattice orders by the latter. It is stated in the tier list rather than encoded.

**What stays refused, and is therefore `T5 HARD_REJECT`:** a 16/32-bit read taking a modeled byte in,
including one straddling into `$ff820a` from `$ff8209` below it — the model would have to fabricate
the neighbouring MFP/shifter register as `0`, which is the false green one address over, so it is
recorded and never served and no `hw_seed=` can lift it. The overlap test is a span test, mirroring
`os.h`'s `os_hw_slots_touched()`. An operand Ghidra could not size gets the same answer as at the PSG
— it is not assumed to be the modeled byte shape.

**A write to a modeled byte stays `T3 HW_WRITE_ONLY`**, because it is still dropped: Phase 7 models
what those addresses *answer*, not what storing to them does.

### The one Phase 7 refusal this classifier cannot price — stated, not invented

A read of an address **this run already wrote** is refused as stale (`osh_hw_stale()`), and no
declaration can fix it. Wonder Boy has a live instance: `video_set_lowres_50hz` writes
`move.b #2,$ff820a` at `$f91c` and `snd_music_tick` reads bit 1 of the same address at `$17c90`, so
any whole-frame run covers both.

**`hw_portability.py` cannot see that, and it is not made to pretend it can.** The refusal is a
property of a **run** — which addresses this run has written, in what order — while the classifier is
static and per-function, taking the worst of a function's own accesses and closing that over the call
graph. A subtree containing both a writer and a reader does not mean one run does both, and it
certainly does not mean it does them in that order; pricing it would manufacture a claim. So the tool
**reports** it instead: the "What this method cannot see" section now names every write to a seeded
byte, with the reason a case has to be read against them. That paragraph is pinned by the end-to-end
script case, so it cannot be dropped in silence.

Two properties of that sweep are load-bearing enough to state. It walks **every** access, including
the ones the scan attributed to no function — those live outside `scan.funcs`, so a functions-only
walk would quietly break the word "every" the bullet uses. And it skips a write the run was given a
`--model` for: under `--model shifter:write` the tier tables price `$f91c` CLEAN, and a report that
priced it clean and listed it as a dropped write in the same breath would contradict itself. Both are
cases.

### Before → after, every moved figure named

Runnable is **unchanged** — a seeded read was already runnable under §0g's rule, so nothing crossed
the `T5` line. The whole movement is on the false-green axis and in the tier labels.

| | before (§0h) | after |
|---|---|---|
| Runnable end-to-end | 244 / 258 fns, 24,358 / 25,826 B, 94.3 % | **unchanged**, function for function |
| False-green risk | 28 fns / 3,348 B, 13.0 % | **20 fns / 2,224 B, 8.6 %** (−8 / −1,124 B) |
| Steering sites | 10 sites in 6 functions | **5 sites in 3 functions** |
| Direct `T2` | 2 fns / 110 B | **3 / 806 B** |
| Direct `T3` | 14 / 1,290 B | **16 / 1,414 B** |
| Direct `T4` | 13 / 1,608 B | **10 / 788 B** |
| Transitive `T2` | 10 / 398 B | **12 / 1,108 B** |
| Transitive `T4` | 26 / 2,698 B | **24 / 1,988 B** |

**Three functions moved by their own access** (direct tier), and they are the only three:

| fn | bytes | before | after | why |
|---|---:|---|---|---|
| `$62d0` `fdc_wait_irq` | 56 | T4 HW_READ | **T3 HW_WRITE_ONLY** | its only read was the `$62da` `btst #5,$fffa01` FDC-done poll; what prices it now is the `$ff8606` mode-word write left behind |
| `$6408` `fdc_restore` | 68 | T4 HW_READ | **T3 HW_WRITE_ONLY** | same shape at `$6422`, with two `$ff8606` writes left |
| `$17c74` `snd_music_tick` | 696 | T4 HW_READ | **T2 SEEDED_READ** | batch 25's consumer proof, priced: its `$17c7e` GPIP and `$17c90` sync reads join its `$17f08` PSG read-back as declared inputs, and its 22 PSG writes are T1 — nothing it touches is fabricated any more |

**Two functions moved transitively**, and one of them is `$17c74` itself: `$17aea`
`FUN_00017aea` (14 B) T4 HW_READ → **T2 SEEDED_READ**, purely inherited from `$17c74`, the same edge
§0g moved it along. **`$62d0` and `$6408` did NOT move transitively** — both still witness
`fdc_wait_irq → fdc_read_data_reg`, whose `$ff8604` read is nobody's modeled set.

**The false-green set lost exactly eight functions, and no function joined it:**

| fn | bytes | why it left |
|---|---:|---|
| `$62d0` `fdc_wait_irq` | 56 | its own `$fffa01` steer is now a declared input |
| `$6408` `fdc_restore` | 68 | its own `$fffa01` steer, likewise |
| `$17c74` `snd_music_tick` | 696 | its own `$fffa01` **and** `$ff820a` steers — the pair the Phase 7 model was built from |
| `$5e3e` `disk_check_signature` | 64 | transitive, witness `disk_check_signature → fdc_restore` |
| `$637e` `FUN_0000637e` | 56 | transitive, witness `→ fdc_wait_irq` |
| `$63c0` `FUN_000063c0` | 72 | transitive, witness `→ fdc_wait_irq` |
| `$6488` `FUN_00006488` | 98 | transitive, witness `→ fdc_wait_irq` |
| `$17aea` `FUN_00017aea` | 14 | transitive, witness `→ snd_music_tick` |

**Four of the nineteen subsystem rows change at all; the other fifteen are byte-identical:**

| subsystem | before | after |
|---|---|---|
| sound (YM2149) | direct **and** transitive worst T4 HW_READ, false-green 2 fns / 710 B | **T2 SEEDED_READ / T2 SEEDED_READ, false-green 0 / 0 B** — the whole subsystem is now declared-input-or-cleaner |
| disk (WD1772 FDC + DMA) | false-green 6 fns / 468 B | **1 / 118 B** (−5 / −350) |
| disk (FAT12 + file load) | false-green 6 fns / 630 B | **5 / 566 B** (−1 / −64) |
| interrupt (VBL) | transitive T2 PSG_SEEDED_READ | **T2 SEEDED_READ** — label only |

**What is left in the false-green 20 / 2,224 B, and it is now a two-source list.** Only three
functions steer on a read of their own: `$754` `ikbd_acia_handler` (`$fffc02`, the IKBD byte),
`$f8f0` `ikbd_disable_mouse` (`$fffc00`, transmit-ready) and `$6308` `fdc_wait_irq_bounded`
(`$ff8609`/`$860b`/`$860d`, the DMA address counter — **it keeps its `$633c` `$fffa01` poll too, but
that one no longer counts; the DMA reads are what hold it**). The other 17 are transitive: the boot
chain and the disk stack above those three.

### The new positive control for the false-green counter

The suite's positive control — the case proving `steers` still *fires* — was `$fffa01`, which is now
exactly the wrong address for the job. It is **`$ff8609`**, the FDC DMA address counter
`fdc_wait_irq_bounded` polls at `$6314` (a real `STEER` row in `../out/hw_scan.tsv`, not a synthetic
address). It is the right choice rather than merely an available one: Phase 7 rules the FDC/DMA
registers out **structurally** — a status byte that must *change* between two reads of the same
address cannot be expressed by a per-run constant, and `TRAP_MODEL.md` says so under "the explicit
NON-GOAL" — so it will not quietly become modeled the way `$fffa01` did while still standing as a
control.

### §6's MFP lever has been built too, and the two named bytes carry all of it

§0g measured Phase 6 against §6's largest predicted lever. The same measurement for Phase 7, on this
scan: the re-derived rule with **no flags** produces the identical false-green figure to the OLD rule
run with `--model mfp:read --model shifter:read` — **20 fns / 2,224 B, and the same 20 functions** —
and those flags on top of the new rule buy **nothing further**. §6 priced a model for those two whole
BLOCKS; Phase 7 shipped two BYTES of them, and on this program that is the same thing, because every
steering read in either block is one of the two. Pinned as a case, so a future scan that reaches a
steering read elsewhere in the MFP or the shifter goes red and says so.

§6's own table is not restated here — its baseline is the 2026-08-02 scan and re-pricing it is the
separate pass §0g queued as item 3. Its `MFP read model` row (−6 fns / −414 B against that scan) is
marked in place below as delivered.

### What is pinned

**`tools/test_hw_portability.py`, 56 cases** (was 37), standalone `pytest tools/test_hw_portability.py`:

* the **lattice** grew from 16 shapes to 25 — the two modeled bytes as `T2`, the `$fffffa01` bus
  alias, a wide read *at* `$ff820a` and one straddling in from `$ff8209` *(batch 33 put that start
  address in the set as well, so the word now takes in TWO modeled slots and is refused for both)*,
  an unsized read of a modeled address, the byte read of `$ff8209`, priced `T4` at this pass as the
  row one address BELOW the set *(batch 33: it is the set's fourth address, and the row pins
  `T2 SEEDED_READ`)*, the `$ff820a` **write** (still `T3`, Wonder Boy's own `$f91c`), `$ff8609` as an
  unmodeled read, and the two unsized-at-a-boundary rows described under "the edge left open" below;
* the **false-green exclusion** is parametrized over five shapes at seeded addresses, with the new
  `$ff8609` positive control;
* the **tripwires** grew by three mutations: a renamed `OS_HW_MFP_GPIP` fails; a kit that grows the
  set to a THIRD modeled byte fails on `OS_HW_NSLOTS` *(batch 33 made the set four, so the mutation
  grows it to a FIFTH today and there are four address pins beside the count — what is pinned is the
  COUNT, not the number it happened to be)* — the drift the address pins cannot catch,
  and the expensive direction, since every pinned name would still match while the tool went on
  pricing the new address as a silent-zero `T4`; and `shim.c` renaming `hw_read()` fails, the Phase 7
  half of the behavioural pin that `psg_read_back()` already carried;
* the **arithmetic** case moves to `(20, 2224)`; both capability pins compare sorted function
  **sets** rather than `(count, bytes)` totals, so "the same 20 functions" is what is actually
  pinned; and the script case asserts the new tier label, the stale-write paragraph and its `$f91c`
  site, that `--model shifter:write` removes that paragraph rather than contradicting the tier
  tables, and — via a synthetic `--extra-hw` pair — that both new blind-spot sweeps reach code
  attributed to no function.

### The edge left open, deliberately, in both models

An operand Ghidra could not SIZE is priced as one byte. That decides two things it cannot decide: it
is priced as **not** the modeled byte shape (pessimistic, so it hard-rejects at a modeled address)
and as **not** straddling into the PSG block or a seeded byte from just below (optimistic, so an
unsized read at `$ff8209` or `$ff87ff` prices `T4`-runnable where a real word there would be
refused). *(Batch 33 moved the first of those two examples across the edge: `$ff8209` is a modeled
address now, so its lattice row is the PESSIMISTIC half — unsized AT the model, hard-rejected — and
`$ff87ff` below the PSG block is what pins the optimistic half. The optimistic edge still stands one
byte below any Phase 7 address; no lattice row holds it there today.)* Widening it means assuming a
maximum transfer width for an operand nobody could read — inventing a refusal rather than measuring
one — so the tool **names every unsized operand** in "What this method cannot see" instead, and two
lattice rows pin today's answer at both models together with that caveat. Wonder Boy's scan has
**no** unsized operand, so the sweep is silent here; the end-to-end case plants one to prove it is
not silent by accident. The edge is pre-existing at the PSG and was previously unstated; Phase 7
reproduced it exactly, and stating both together is what keeps the two models' treatment consistent.

**Mutation-tested against itself, twice** — once on the tier re-derivation and again after the
review pass moved the sweeps. Twelve deliberate defects: dropping `$ff820a` from the set, a
start-address test instead of the span test, serving any width at a modeled address, collapsing the
seeded-surface predicate to its PSG half, a modeled size of 2, unpinning `OS_HW_NSLOTS`, pricing a
modeled-byte *write* as seeded, deleting the stale-write paragraph, assuming an unsized operand is
4 bytes wide, making `all_accesses()` skip code attributed to no function, dropping the
`--model` filter from the stale list, and deleting the unsized sweep. **All twelve caught, none
survived**, with `__pycache__` purged between runs (§0g's byte-length caveat).

One methodological note worth carrying, because it cost a false result here: a mutation written as
`old_list and new_list` is a **no-op** in Python — the truthy first operand is discarded and the
original expression is returned. It reported SURVIVED for a sweep that is in fact covered. Mutate the
function the sweep calls, not the call site's expression, and re-read any survivor's diff before
believing it.

### §-consistency: what this falsifies above, marked in place

Nothing above is rewritten. Marked in place where a reader would otherwise carry a stale fact
forward: the header note (the `T2` rename), §0g's "silent-zero class was checked and is NOT drifted"
paragraph (**the claim this section retires**), §0g's `$17c74` row and its 37-case count, §3's
false-green bullet (28 / 3,348 held from the original measurement through §0g and §0h, and moves for
the first time here), §5's "10 sites in 6 functions", and §6's `MFP read model` / `shifter read
model` rows plus the `MFP + FDC/DMA` reading beneath them.

**Outside this file, one live doc was falsified and is corrected rather than marked**:
`docs/on-target-execution.md`'s tier table is the transferable statement of this lattice, so its `T2`
row now names both models and the seed contract, its `T3` row carries the stale-read consequence, its
`T4` row is scoped to addresses **outside** the modeled sets, and its change-note distinguishes the
two same-day moves (§0g renumbered; §0i renamed `T2` without renumbering, so only the label separates
a report written between them). Its two worked T4 examples — BuggyBoy's `$ffff820a` and Wonder Boy's
`$fffa01` FDC poll — are both `T2` today; the measurements stand and are marked as the defects the
tier was named from, with the FDC/DMA status registers named as the live instances.

**Also corrected, and it is a method note rather than a number**: §0's reproduce block listed
`portability_predictions.py` as a checked step. It has not been re-run since kit Phase 6 — §0g read
it, §0i could not run it — so the block now says so and points at the queue.

### Still queued (not this pass)

1. **§6 / §6.1's capability table re-priced** — §0g's item 3, now with a second delivered row. Its
   baseline is still the 2026-08-02 scan.
2. `notes/portability_predictions.py` — §0g's item 4 is unchanged and now has a second half: its
   `T4`-tier docstrings describe `$fffa01`/`$ff820a` as unservable. A concurrent port session owns
   `recreate/`, so the script (which builds the oracle `.so`) was **not** re-run here.
3. **A `T2` case is only as good as its case's declaration.** `TRAP_MODEL.md`'s "honest limit"
   applies verbatim to every function this section moved: `snd_music_tick` is now runnable *given* a
   case that says which machine it means. That `$fffa01 = $b0` / `$ff820a` bit 1 is what a 50 Hz
   colour ST answers is a documented hardware claim, not a differential result.

## 0j. Re-scanned 2026-08-11 (batches 23–27): twenty-six functions appear, and not one tier moves

The two-stage pin §0h specified, run over the names batches 23–27 added. **No game code changed and
no test in `recreate/` moved** — `make test` is 3,594 before and after; the edited files are
`subsystems.tsv` (one range), `tools/test_hw_portability.py` (two literal pins) and this section,
and `../reapply.sh` + `tools/hw_scan.sh` regenerated `../decomp.c` and `../out/hw_scan.tsv`.

**Stage 0, the floor.** The classifier over the **committed** scan reproduces every §0i figure
byte-for-byte — 258 functions / 25,826 B, runnable **244 / 24,358 = 94.3 %**, false-green
**20 / 2,224 = 8.6 %**, all nineteen subsystem rows — so everything below is the re-scan and the
partition edit, and nothing else.

### Stage 1 — the re-scan, and the largest function gain since the measurement began

`ApplyNames` pushed `../names.txt` (**253** `fn`, 240 `var`, 385 `cmt`, 37 `proto` — up from 227
`fn`) into the DB and the re-scan re-dumped the TSV. **Twenty-six `F` records appear, one changes
size, and not one pre-existing function moves tier, steering or reachability** — checked
function-by-function against the old scan, both tiers, as sets and not as totals:

| | before (§0h/§0i scan) | after |
|---|---|---|
| functions / function bytes | 258 / 25,826 | **284 / 26,194** (+26 / +368) |
| disassembled bytes | 28,116 | **28,414** (+298) |
| code in no function body | 2,290 B in 12 runs | **2,220 B in 10 runs** (−70) |
| call-graph edges | 245 (381 CALL, 9 JUMP, 23 JUMPIN) | **269 (382 CALL, 11 JUMP, 45 JUMPIN)** |
| hardware accesses (`H` rows) | 126 | **126 — byte-identical in content, every row** |
| direct `T0 CLEAN` | 227 / 22,638 B | **252 / 23,012 B** |
| direct `T2 SEEDED_READ` | 3 / 806 B | **4 / 800 B** |
| transitive `T0 CLEAN` | 191 / 19,394 B | **215 / 19,758 B** |
| transitive `T2 SEEDED_READ` | 12 / 1,108 B | **14 / 1,112 B** |
| runnable end-to-end | 244 / 258 fns, 24,358 / 25,826 B, 94.3 % | **270 / 284 fns, 24,726 / 26,194 B, 94.4 %** |
| false-green risk | 20 / 2,224 B, 8.6 % | **20 / 2,224 B, 8.5 %** — the identical function set |
| unreachable from the roots | 114 / 10,650 B | **140 / 11,018 B** |

**Every one of the 26 new `F` records is runnable and none is false-green**, so the whole +368 lands
in the runnable column: 24,358 + 368 = 24,726, and the runnable *set* gains exactly those 26 and
loses none. The `T3`, `T4` and `T6` rows of both tier tables are **unchanged to the byte**.

**The +368 closes exactly, and in three parts:**

| | fns | bytes | where the bytes came from |
|---|---:|---:|---|
| `$101bc` `scene_exit_action_none` + `$101be` `scene_exit_action_select_a30_table` | +2 | **+68** | the `O` run `0x101bc..0x10200`, which the old scan had in **no function body** and therefore in no tier |
| `$17c74` `snd_music_tick` 696 → 44 B, splitting off `$17ca0` `snd_music_tick_body` (646 B) | +1 | **−6** | a re-cut, not a gain: 8 bytes of the old address set pass to the handlers below, 2 come back from the `O` run at `0x17c72` |
| the 23 pattern-opcode handlers `$17fd4..$18106` | +23 | **+306** | 298 B the disassembler had **never reached** plus the 8 B leaving `$17c74` |

`+68 − 6 + 306 = +368`; and on the disassembly axis `28,116 + 298 = 28,414`, with the −70 of
code-in-no-function being the two `O` runs (`0x101bc..0x10200`, 68 B, and `0x17c72..0x17c74`, 2 B)
that entered a function body. The **`O` list is otherwise byte-identical**, run for run.

**The `$17c74` split is the §0h size trap again, in its second live instance.** `snd_music_tick`
loses 652 bytes to a routine that gains 646, and the two do not sum back to 696 — because Ghidra's
`F` size is the cardinality of an address SET, not `body_end − entry`. `$17ca0`'s 646 covers
`0x17c72..0x17ca0` (2 bytes *below* its own entry — the shared tail, exactly `$1a5da`'s shape) plus
`0x17ca0..0x17f24`, while the old record reached to `body_end 0x1801e` and so held 8 bytes the
handler records now own. Nothing was lost and nothing was double-counted: the sum of every `F`
size equals the reported 26,194 exactly.

**The 24 new edges are the re-cut spelt out** (four removed, twenty-eight added). `$17c74`'s four
outgoing `CALL`s are re-attributed to `$17ca0`, which gains a `JUMP` in from the 44-byte head; the
`- → 0x1b68 CALL` out of unattributed code becomes `$101be → actor_alloc_slot_low`, the same
instruction with a source node at last; and **20 of the 23 handlers carry a `JUMPIN` back into
`snd_channel_step`'s body** — the `jmp` return the batch-24 port derived. The three that do not are
worth naming, because they are the structure rather than an omission: `$18014`
`snd_pattern_op_8e_end_song` calls `$17af8` instead (it ends the song rather than resuming the
stepper), and `$180bc` `snd_pattern_op_86_slide_up` and `$180ca` `snd_pattern_op_88_portamento_set`
fall through into their neighbour instead of jumping.

**The batch-26/27 names all landed where `../names.txt` says.** Cross-checked mechanically rather
than spot-checked: **all 253 `fn` addresses have an `F` record at that exact address, and all 253
names agree with the scan's** — `$f944` `set_palette`, `$f95c` `stage_load_window`, `$17b3a`
`snd_play_song`, `$dfbe` `scene_exit_and_reload`, `$1aaca` `snd_prng_step`, `$1a5da` `snd_sfx_tick`,
`$18208`, `$18106` included. `$f944` and `$f95c` were already `F` records and did **not** move, so
neither is a partition question; they sit in `video (screen / palette / mode)` (`0xf906..0xf95c`)
and `stage (load + reset)` (`0xf95c..0xfa2e`) as before.

### Stage 1 sanity — the verified column against `STATUS.md`'s 175

`STATUS.md`'s table carries **152 verified rows**; expanding its four family legends (16 scroll
copies, 4 sprite blitters, 4 clip-left, 4 clip-right) gives **176 reconstructions / 21,024 bytes**.
Against the new scan those map to **203 `F` records / 21,026 bytes**. The reconciliation gains one
counting-rule row (batch 24's) and, for the first time since §0c, **one row where the BYTES differ**:

| | reconstructions | F records | bytes |
|---|---:|---:|---:|
| `src/rad.c` — one reconstruction Ghidra splits into three (`rad_depack`, `rad_refill_bit_buffer`, `rad_get_bits`) | 1 | 3 | same 216 |
| `snd_sfx_tick` (`$1a5da`) — one reconstruction Ghidra splits into four: the 42-byte head plus three 186-byte channel arms | 1 | 4 | same 600 |
| the pattern-opcode handlers (`$17fd4`) — **one `STATUS.md` row, 23 `F` records**, one per opcode body | 1 | 23 | same 306 |
| `snd_music_tick_body` (`$17ca0`) — one reconstruction, one `F` record, **644 vs 646** | 1 | 1 | **+2** |
| **net** | **176** | **203** | **21,024 + 2 = 21,026** |

That last row is not a disagreement about what is ported; it is the address-set rule again.
`STATUS.md` states the contiguous body `$17ca0..$17f24` = 644, and Ghidra's set adds the 2-byte
shared tail at `$17c72` below the entry. It is the *third* instance of the same trap in this file
and the first to reach the verified column, so: **wherever a byte column is compared against an `F`
size, expect a shared tail below an entry to make the scan's number larger.** Checked row by row,
all 152 — it is the only one.

**Two `STATUS.md` figures this surfaces, flagged and NOT edited here** (`STATUS.md` is outside this
pass's scope):

* its headline reads **`Verified: 175/?`** while its own table now expands to **176**. §0h's
  expansion was exact (142 rows → 166); the table has gained 10 rows since and the headline moved 9.
* the handler row is titled **"the 24 pattern-opcode handlers"** while its own prose says "23
  distinct bodies" and the scan finds 23 `F` records. The opcode range `$80..$97` holds 24 values
  and `$8d` has no handler, which is the likely origin.

Neither changes a byte of this measurement — both byte columns agree — but the next pass that
re-derives a count from `STATUS.md`'s prose rather than its table will be one out.

### Stage 2 — the partition edit

With stage 1 pinned as the baseline, `subsystems.tsv` gains **one** range, cited in the file itself:
**`0x101bc..0x10200` → `scene (dialogue + shop)`**. `$101bc` and `$101be` are entries 0 and 1 of
`scene_exit_action_table` (`$1019c`), and the only site in the image that reaches either is
`scene_exit_and_reload`'s `jsr (a6)` at `$dfd6` — the indirect dispatch the scan already lists under
`$dfbe`. `hi` is `$10200`, where the first `set_state_*` stub begins: entries 2..7 of the same table
are those six stubs and they **stay** in `hud (status panel)` (`0x10200..0x103e8`), because the
panel's state words are what they write. The range was checked for overlap first and claims two
catch-all members rather than moving any boundary. The re-run differs from stage 1 in **exactly two
rows, and no whole-program figure moves** (diffed, not argued):

| subsystem | stage 1 | stage 2 |
|---|---|---|
| scene (dialogue + shop) | 3 fns / 1,094 B, runnable 3 / 1,094 B | **5 / 1,162 B, runnable 5 / 1,162 B** |
| game logic (catch-all) | 22 fns / 2,126 B, direct T0 20 / 1,974 B, runnable 19 / 1,754 B | **20 / 2,058 B, direct T0 18 / 1,906 B, runnable 17 / 1,686 B** |

**The catch-all lands back on its §0i figure exactly** — 20 fns / 2,058 B — which is the cleanest
statement of what this pass did to it: batch 27's 68 bytes passed straight through it into `scene`
without disturbing anything already there.

**§0f's "runnable 0" shape has fully inverted, and it did so in two steps.** That row was drawn as
the first subsystem where RECONSTRUCTED exceeds RUNNABLE — 3 fns, transitive `T4`, **runnable 0**,
because every scene function reached `stage_load_window`'s sound call. §0g's classifier repair
removed that wall and the row has read runnable 3 / 1,094 B since (it already did in stage 0, so it
is not a delta of this re-scan); batch 27's port of `$dfbe` then made the tier **3 of 3
reconstructed**, and this section's range makes it **5 of 5, all runnable, transitive
`T3 HW_WRITE_ONLY`, zero false-green**. The subsystem that motivated the "reconstructed exceeds
runnable" note no longer illustrates it — the note is kept in `subsystems.tsv`, marked in place, as
the record of why the rows were drawn.

**Declined, with the reason: the sound splits need no range.** `$17ca0` and all 23 handlers
(`$17fd4..$18106`) are **already inside** the existing `0x17adc..0x1ab04` `sound (YM2149)` span,
which covers the whole module in one range — verified against the new scan rather than assumed, and
visible in stage 1's table, where `sound` absorbs all 24 without any edit (22 fns / 2,634 B →
**46 / 2,934 B**, `+300` = the handlers' 306 less the split's 6). The file's convention is that a
range exists to *claim* entries, not to annotate ones already claimed.

### The coverage wall, measured — the ground truth for the campaign that follows

The headline of this file has always been that its tiers describe only what is inside a function
body. That denominator has now moved for the first time in five sections, so here is the wall
itself, stated once:

| | bytes | % of believed CODE |
|---|---:|---:|
| total believed CODE (`notes/architecture.md`'s own region table, 12 rows) | **54,854** | 100 % |
| in an `F` record — everything every tier above is out of | **26,194** | **47.8 %** |
| disassembled but in **no** `F` record (the 10 `O` runs) | 2,220 | — (not wholly inside CODE) |
| ⤷ of those, inside a region `architecture.md` calls CODE | 1,782 | 3.2 % |
| ⤷ of those, in a region it calls DATA (`0x105e4..0x1079a`) | 438 | — |
| **CODE in no function body at all** | **28,660** | **52.2 %** |
| ⤷ reached by the disassembler, attributed to nothing | 1,782 | 3.2 % |
| ⤷ **never reached as code at all** | **26,878** | **49.0 %** |

**The wall is not "unattributed code" — it is code Ghidra never disassembled.** Of the 28,660 bytes
outside every function, 94 % were never decoded at all; the `O` runs are a rounding error beside
them. That is the shape of the campaign: it is a *reachability* problem (pointer tables, indirect
dispatch — §8.1), not an attribution one.

**The ten largest contiguous no-function-body gaps inside CODE**, which is where a campaign starts.
Cut against merged function *extents*, so a discontiguous body's own hole is not counted as a gap:

| # | range | bytes | disassembled inside it | note |
|---|---|---:|---:|---|
| 1 | `0x02bc8..0x0501a` | **9,298** | 430 | by far the largest — a third of the whole wall; runs from `actor_turn_and_launch`'s body end to `FUN_0000501a`, inside `architecture.md`'s "bulk of the engine" |
| 2 | `0x051d8..0x05c6e` | 2,710 | 206 | |
| 3 | `0x06d5a..0x07522` | 1,992 | 316 | starts at `actor_respawn_as_new_kind`'s body end, ends at `bg_scroll_run_queue` |
| 4 | `0x0ee68..0x0f542` | 1,754 | 0 | **the Copylock ciphertext** — unreadable by construction, not a campaign target |
| 5 | `0x02462..0x02af2` | 1,680 | 398 | |
| 6 | `0x01514..0x01ab4` | 1,440 | 130 | ends where `scene_spend_visit_budget`'s unported arm goes. **Batch 40 phase C took NONE of this gap** — `$1b46` lies PAST its end (and was already inside a named `fn`), so booking it here would be a phantom credit — but it DIVIDED the gap exactly: 6 bytes of data (`$1514`) + 1,170 (`player_run_map_cell`, `$151a..$19ab`, which BATCH 41 PHASE A then took whole) + 264 (`scene_spawn_from_script`'s head as far as `$1ab4`) = 1,440. Note the head does NOT end there: it runs on to `$1aef`, and those last 60 bytes lie in neither this gap nor gap 10 |
| 7 | `0x01f54..0x023b6` | 1,122 | 0 | **656 of these are gone as of batch 40 phase C** — `player_stage_transition` is `$1f54..$21e3` and the 466 above it are its own DATA, now read field by field (three 88-byte posture records and four cursor-plus-table animations). So this gap is CLOSED but for its data; the figures in this table are the 2026-08-11 re-scan's and are not re-run here |
| 8 | `0x00938..0x00d28` | 1,008 | 132 | |
| 9 | `0x0e91c..0x0ecca` | 942 | 76 | runs up to `copylock_entry` |
| 10 | `0x01bb4..0x01f36` | 898 | 0 | |

Those ten are **22,844 bytes, 79.9 % of the wall**, and excluding the Copylock, **21,090 bytes in
nine ranges**. There are 58 gaps in all; the tail beyond these ten is 5,744 bytes.

### What is pinned

`tools/test_hw_portability.py` stays at **56 cases**, green. Two literal pins track the working scan
and moved with it, in this commit, per the batch-22b-closed precedent:

* `test_the_committed_scan_reproduces_its_published_figures`: `258 → 284` functions,
  `25,826 → 26,194` bytes, runnable `(244, 24358) → (270, 24726)`. **The false-green pin
  `(20, 2224)` is NOT touched** — the re-scan moved no function's tier, so only the denominator
  under it moved, which is precisely what the two set-comparison capability cases already guard.
* `test_the_tool_runs_end_to_end_as_a_script`: the headline string
  `244/258 functions, 24358/25826 bytes = 94.3 %` → `270/284 functions, 24726/26194 bytes = 94.4 %`.

Every other case is untouched and green, including both `--model` capability pins (which compare
function **sets**) — so §0i's claim that the two modeled bytes carry the whole MFP/shifter block
capability survives a scan that added 26 functions.

### Still queued (not this pass)

§0i's three items stand unchanged (`§6`/`§6.1` re-pricing, `notes/portability_predictions.py`, and
the `T2`-declaration caveat). This section adds two:

4. **`STATUS.md`'s headline count and the handler row's title** — the two off-by-ones flagged above.
5. **`§1`'s answer box and its `CODE bytes` column are now three scans stale** (they still print
   2026-08-02: 256 fns / 25,786 B / 47.0 % coverage). The coverage table in this section supplies
   the whole-program half of what a re-statement needs — 54,854 / 26,194 / 47.8 % — but the
   per-subsystem `CODE bytes` column has to be re-charged against `architecture.md` region by
   region, which is a measurement of its own and not this section's.

## 0k. The coverage-wall yield (2026-08-11, batch 28): one `lea` opens 18,068 bytes

§0j measured the wall and called it "a *reachability* problem (pointer tables, indirect dispatch),
not an attribution one". Batch 28's coverage scout tested that claim by naming the mechanism, and
this section measures what naming it bought. **It is the largest single movement in this file's
history: +123 `F` records, +18,068 bytes, coverage 47.8 % → 80.7 % of believed CODE.** No game code
changed and no test in `recreate/` moved — `make test` is 3,594 before and after; the edited files
are `../names.txt` (the scout's 125 `fn`, 8 `var`, 134 `cmt`), `tools/test_hw_portability.py` (five
literal assertions across two cases) and this section, and `../reapply.sh` + `tools/hw_scan.sh`
regenerated `../decomp.c`, `../out/hw_scan.tsv` and `../out/reapply.log`. **`subsystems.tsv` is not
edited** — see stage 2.

**Stage 0, the floor.** The classifier over the **committed** scan reproduces every §0j figure
byte-for-byte — 284 functions / 26,194 B, runnable **270 / 24,726 = 94.4 %**, false-green
**20 / 2,224 = 8.5 %**, and the coverage table's 54,854 / 26,194 / 1,782 / 438 / 28,660 / 26,878 —
so everything below is the re-scan, and nothing else.

### The mechanism, in one instruction

```
00928  moveq #0,d1 / move.w 4(a0),d1 / lsl.w #2,d1
00930  lea (0x938,PC,d1.w),a1        <- 43fb 1006, PC-relative INDEXED lea
00934  movea.l (a1),a1
00936  jmp (a1)
```

The base `$938` exists nowhere in the image as an operand — it is the 8-bit displacement of a
PC-relative **indexed** brief extension word. Ghidra follows a plain `lea abs.l` and does not follow
this, so `actor_behavior_table` and all 61 of its targets were invisible, and with them everything
only those targets call. That is one instruction standing between the measurement and a third of
the program.

### Stage 1 — the yield

`ApplyNames` pushed `../names.txt` (**378** `fn`, 248 `var`, 519 `cmt`, 37 `proto` — up from 253
`fn`) into the DB and reported `applied 378 functions`; its counter increments only on a non-null
`Function`, so all 378 landed, and `ExportDecompC` returned `407/407 functions (0 failed)`. **125
`fn` lines produced 123 new `F` records and 2 renames** — `$8d0 FUN_000008d0 → actor_behavior_pass`
and `$928 FUN_00000928 → actor_dispatch_behavior`, both already `F` records, neither changing size.

| | before (§0j scan) | after |
|---|---|---|
| functions / function bytes | 284 / 26,194 | **407 / 44,262** (+123 / +18,068) |
| disassembled bytes | 28,414 | **44,516** (+16,102) |
| code in no function body | 2,220 B in 10 runs | **254 B in 4 runs** (−1,966) |
| call-graph edges | 269 (382 CALL, 11 JUMP, 45 JUMPIN) | **753 (782 CALL, 130 JUMP, 60 JUMPIN)** |
| hardware accesses (`H` rows) | 126 | **126 — byte-identical in content, every row** |
| direct `T0 CLEAN` | 252 / 23,012 B | **375 / 41,080 B** |
| direct `T2`/`T3`/`T4`/`T6` | 4/800, 16/1,414, 10/788, 2/180 | **unchanged to the byte, all four** |
| transitive `T0 CLEAN` | 215 / 19,758 B | **301 / 26,434 B** |
| transitive `T4 HW_READ` | 24 / 1,988 B | **56 / 10,680 B** *(pre-batch-33 pricing — see below)* |
| transitive `T6 UNMEASURABLE` | 14 / 1,468 B | **18 / 3,154 B** |
| runnable end-to-end | 270 / 284 fns, 24,726 / 26,194 B, 94.4 % | **389 / 407 fns, 41,108 / 44,262 B, 92.9 %** |
| false-green risk | 20 / 2,224 B, 8.5 % | **24 / 3,910 B, 8.8 %** |
| reachable from the roots | 144 / 15,176 B | **144 / 15,176 B — identical, see below** |

**The +18,068 closes exactly:** 16,102 bytes the disassembler had never reached, plus 1,966 that
were reached but attributed to nothing (the `O` runs). And **not one of the 284 pre-existing
functions moved** — checked function by function as sets, on all four axes at once (direct tier,
transitive tier, steering, reachability): **0 of 284**. No `F` record was removed, none was resized,
so the §0h address-set trap did not recur and there are no individual pre-existing deltas to name.

**The 123 new records, grouped by the mechanism that hid them:**

| group | fns | bytes |
|---|---:|---:|
| the 61 `actor_behavior_table` handlers (slots 0..61; slots 0 and 58 share the `rts` at `$a36`) | 61 | **11,546** |
| the player subtree — slot 1's private tree (`player_*`, `stub_rts_205c`) | 10 | 3,274 |
| the shared subtree the handlers call (`actor_step_facing`, `actor_vanish_anim_step`, `sound_request_*`, `scene_spawn_from_script`, …) | 27 | 2,398 |
| the pickup-effect table behind slot 38 (`pickup_effect_table`, `$105ac`) | 14 | 438 |
| the swoop/dive state machine behind slot 7 (`actor_swoop_state_table`, `$7490`) | 4 | 268 |
| the sprite copy-row-unrolled family (`sprite_cru_copy_table`, `$e91c`) | 4 | 76 |
| the byte-code gate table `scene_spawn_from_script` dispatches through (`spawn_script_gate_table`, `$e42e`) | 3 | 68 |
| **total** | **123** | **18,068** |

**The `O` runs, run for run.** **No new `O` run appeared** and none grew: six of the ten were
absorbed whole, four were absorbed in part. Note the distinction the `O` record forces — a function
body is an address SET, so an `F` record can *span* a run while leaving bytes inside it in no body:

| run (before) | bytes | absorbed | left in no body | absorbed by |
|---|---:|---:|---:|---|
| `0x3000..0x3e2c` | 430 | 430 | — | `actor_face_and_step4`, `actor_pick_facing_list` |
| `0x6fc2..0x73ce` | 316 | 316 | — | `actor_behavior_type61`, `actor_face_followed_step` |
| `0x698a..0x69bc` | 50 | 50 | — | `actor_vanish_anim_step` |
| `0x6796..0x67c2` | 44 | 44 | — | `sound_request_8_and_face` |
| `0xe92c..0xe978` | 76 | 76 | — | the four `sprite_cru_copy_*` |
| `0x105e4..0x1079a` | 438 | 438 | — | the 14 `pickup_effect_*` — the 438 B §0j found in a region `architecture.md` calls DATA |
| `0x25a8..0x2736` | 398 | 374 | **24** (`0x25a8..0x25c0`) | `actor_behavior_type03` |
| `0x5a6e..0x5b3c` | 206 | 202 | **4** (`0x5aae..0x5ab2`) | `actor_behavior_type50`, `actor_behavior_type51` |
| `0x1712..0x17f4` | 130 | 34 | **96** (`0x1712..0x1772`) | `player_run_map_cell` |
| `0xa84..0xb08` | 132 | 2 | **130** (`0xa84..0xb06`) | `player_meter_empty_check` |
| **total** | **2,220** | **1,966** | **254** | |

The last two are worth reading rather than skimming: `player_meter_empty_check` is `$a76..$b07` and
`player_run_map_cell` is `$151a..$19ab`, so both **contain** their run's address span, yet 226
of those 262 bytes are still in no function body. *(Both extents are corrected by one byte here,
batch 40: `$b08` is `WB_STAGE_RESET_BLOCK`'s first byte and `$19ac` is `scene_spawn_from_script`'s
entry, so the old figures named the NEXT thing's first byte as this one's last. The arithmetic in
the table above is unaffected — it is cut against the runs' own address sets, `$a84..$b06` and
`$1712..$1772`, both of which still lie wholly inside the corrected extents.)* Both bodies are discontiguous — the scout's own
plate for `$a76` says it "swallows the `O` run `$a84..$b08`", and on the extent it does; on the
address set it does not. That is the §0h trap in its fourth instance, and **226 of the residual 254
bytes are it**: those two runs lie wholly inside a function's extent and would vanish from any
measurement cut against extents rather than address sets. The other 28 B (`0x25a8..0x25c0` and
`0x5aae..0x5ab2`) are ordinary holes between functions.

### Every new function that is not runnable, or is false-green — named with its steer

The false-green count moves for the first time since §0i, and it moves **only** because of new
functions: **+4 fns / +1,686 B**, all four not-runnable and false-green together, all four for the
same reason.

| function | bytes | why |
|---|---:|---|
| `$a38 actor_behavior_type01_player` | 62 | slot 1 of the table — the player, and the LAST of the 62 rows to go live. **RECONSTRUCTED, batch 41 phase F**, and this row's 62 was already checked rather than scanned by phase D: the body decoded from the raw image is `$a38..$a75` = 62 bytes exactly, so unlike the two rows below it the scan did not lose phase here (there is no data inside this code). Its false-green edge is INHERITED and not its own, and the port does not retire it: the routine has no transfer of any kind — nine `bsr`s, two memory guards and an `rts` — so every tier it carries comes from `$b1a` and `$151a`, whose `jmp $e5ba.l` unwinds are the path to the prompt, and the reconstruction REPORTS those endings rather than following them. What blocked the port was not that edge but the X flag it must compose between `$a4a` and `$a4e`; batches 41 phase E and F threaded it (STATUS.md, batch 41 phase F) |
| `$b1a player_pending_event_gate` | 440 | **RECONSTRUCTED, batch 41 phase C, and this row's EXTENT is corrected with it**: the routine is `$b1a..$d27` = **526 bytes**, bounded by `bg_scroll_raise_requests`' entry at `$d28`. The 440 here is the scan's figure and it is short by 86, for the reason that made this routine unreadable at all — TWO DATA WORDS INSIDE THE CODE (`WB_LIVES` at `$be2`, `WB_LIFE_RESTART_ENTRY_C26` at `$c26`) desync a linear sweep, so the scan stopped counting where it lost phase. The reconstruction was decoded from the raw image and its entry pin covers all 526. The false-green edge is unchanged: this routine still reaches `show_data_disk_prompt`, and directly — `jmp $e494.l` at `$bdc` |
| `$151a player_run_map_cell` | 1,066 | the largest single routine the wall hid. **RECONSTRUCTED, batch 41 phase A, and this row's edge is corrected with it**: a whole-image census of its $151a..$19ab finds THREE outward transfers — `bsr.w $1b8e`, `bra.w $6ade` and `jmp $e5ba.l` — and none of them is `show_data_disk_prompt`. Whatever reaches the prompt from here does so through `$e5ba`, which is a TAIL JUMP after a stack unwind and not a call this routine returns from |
| `$6f9e actor_behavior_type61` | 118 | |

All four reach `show_data_disk_prompt → load_resource_by_index → copylock_entry` (direct `T6`,
hence not runnable) and, on the same edge, `→ disk_load_file → FUN_00005fc4 → FUN_00006118 →
fdc_wait_irq_bounded` (the FDC status poll, the live `T4-STEER` §5 already names). **Not one of the
123 has a hardware access of its own** — the `H` table is byte-identical, all 126 rows — so every
tier any of them carries is inherited.

**The transitive `T4` explosion is `rng_next`, and it does not steer.** 24 → 56 functions and
1,988 → 10,680 B looks alarming and is not. Of the 32 new `T4` functions, **29 reach `$68c6
rng_next`** (`move.b $ff8209,d0` — the shifter video-counter low byte as an entropy source) and **4
reach `$51ac bcd_add_random_1_to_4`** (`$ff8209` and `$ff8207`); one reaches both, so the two account
for all 32. Both are `T4-DATA` — the scan records `steers=False` on every one of those reads — so
they cost fidelity, not a false green. That is why +32 transitive `T4` bought only +4 false-green.
*(Marked in place — this scan predates batch 33, which put `$ff8207` and `$ff8209` in the kit's
modeled set: all 32 read nothing else off-image, so they price `T2 SEEDED_READ` today. The tier
moved under the scan; the scan did not lie, and the figures above are left as it produced them.)*

### The finding this pass did not expect: the tier is unreachable from the roots

**`reachable from the roots` did not move at all — 144 functions / 15,176 B, identical.** `$928
actor_dispatch_behavior` has **zero callees in the scan**: the `jmp (a1)` is exactly as opaque to
Ghidra's reference model as the `lea` was to its disassembler. `actor_behavior_pass → 
actor_dispatch_behavior → ∅`, so all 123 new functions are a call-graph **island**, and the
restricted table below now understates the running game by ~17 KB.

Their own tiers are unaffected — each is the root of its own subtree, and a missing edge *into* a
function cannot change what it or its callees touch. What the missing edge changes is the
restricted table and the roots' witness paths. Modelled as a sensitivity, edges added by hand and
**not committed**, in two steps so the second is separable from the first:

| | as scanned | +61 dispatch edges | +the four smaller tables |
|---|---|---|---|
| reachable from the roots | 144 / 15,176 B | **267 / 33,874 B** | **289 / 34,656 B** |
| runnable (whole program) | 389 / 41,108 B | 386 / 40,994 B | 386 / 40,994 B |
| false-green | 24 / 3,910 B | 27 / 4,024 B | 27 / 4,024 B |
| runnable **and** reachable | 134 / 13,884 B | **250 / 30,782 B** | **272 / 31,564 B** |

Column 2 adds only `$928 → each of the 61 handlers`. Column 3 additionally resolves
`actor_swoop_state_table` (`$7060 →` 4), `pickup_effect_table` (`$5408 →` 14) and
`sprite_cru_copy_table` (4) — 22 functions / 782 B. Resolving `spawn_script_gate_table` adds nothing,
because its dispatcher `scene_spawn_from_script` is itself still unreachable.

The three functions that move are exactly the dispatch chain — `$882 FUN_00000882`, `$8d0
actor_behavior_pass`, `$928 actor_dispatch_behavior` (114 B) — which inherit the player slot's `T6`
and its FDC steer the moment the edge exists; that is invariant across both columns, and **nothing
else in the program changes**. The honest reading: the whole-program tiers in this section are sound,
the *restricted* table is not, and closing that gap is a scan capability (`--extra-edges`, or a
Ghidra reference the loader plants), queued below.

### Stage 1 sanity — the verified column against `STATUS.md`'s 176

**Unchanged, and unchanged by construction.** §0j's reconciliation — **203 `F` records / 21,026 B
over 176 reconstructions**, with its four counting-rule rows (`rad.c` 1→3, `snd_sfx_tick` 1→4, the
pattern handlers 1→23, `snd_music_tick_body` +2 B) — is **carried forward, not re-derived here**: it
was obtained by expanding `STATUS.md`'s four family legends by hand, which a parse of the table does
not reproduce. What this pass verifies is the *invariant* that lets it be carried forward, and that
is checked mechanically: no `F` record was removed or resized (0 of 284), the only two renamed
(`$8d0`, `$928`) appear nowhere in `STATUS.md`, and every `$addr` `STATUS.md`'s table names that was
an `F` record before is one now at the same size and the same name — 0 changed. A pass that needs
the 203 itself should re-derive it rather than trust this sentence.

`STATUS.md`'s headline now reads `Verified: 176/?`, which closes §0j's queued item 4a — the
off-by-one against its own table is gone. The handler row's title (item 4b) is not this section's
to check.

### The coverage wall, re-measured — and the denominator caveat

Same method as §0j, same `architecture.md` region table, so the before column below reproduces its
published figures byte-for-byte:

| | §0j | **§0k** |
|---|---:|---:|
| total believed CODE (`notes/architecture.md`, 12 CODE rows) | 54,854 | 54,854 |
| in an `F` record | 26,194 (**47.8 %**) | **44,262 (80.7 %)** |
| disassembled but in no `F` record | 2,220 (10 runs) | **254 (4 runs)** |
| ⤷ inside a region it calls CODE | 1,782 (3.2 %) | **254 (0.5 %)** |
| ⤷ inside a region it calls DATA | 438 | **0** |
| **CODE in no function body at all** | **28,660 (52.2 %)** | **10,592 (19.3 %)** |
| ⤷ reached, attributed to nothing | 1,782 | 254 |
| ⤷ **never reached as code at all** | **26,878 (49.0 %)** | **10,338 (18.8 %)** |
| gaps inside CODE, cut against merged extents | 58 gaps / 28,588 B | **95 gaps / 10,582 B** |

**Against the scout's forecast — it under-promised, slightly.** It expected "~16,000 gap bytes + the
1,782 `O`-run bytes" ≈ 17,800; the measurement is **18,068**, which splits as 16,540 off the
never-reached line and 1,528 of the CODE `O`-run bytes. (Those two account for the whole `F`-byte
gain under this method: 28,660 − 10,592 = 18,068. The remaining 438 `O`-run bytes — the
`pickup_effect_*` handlers, which sit in a row `architecture.md` calls DATA — are *inside* the
16,540 rather than additional to it, because this method charges every `F` byte to the CODE
denominator. That is the same simplification the caveat below concedes, seen from the other side.)

> **The denominator is soft, and it is soft in the direction that flatters this table.**
> `architecture.md`'s region table over-claims CODE, and the scout's own reads say by how much in at
> least three places it names explicitly: `$21e4..$23b6` (466 B) is a sprite-id word table,
> `$e978..$ecca` (850 B) is sprite bitmap data, and `$73ce..$7522` (340 B) is
> `actor_swoop_path_table` and its payload — all three sit in rows the table calls CODE. That is
> 1,656 B of the 10,582 B residue already known not to be code, and the residue map below puts the
> confirmed-DATA total far higher. **Read `80.7 %` as a lower bound on coverage of the real code and
> `10,592` as an upper bound on the wall.** `architecture.md` is NOT edited here — the
> re-classification is a registered finding for a pass of its own, and it is the same measurement
> §0j's queued item 5 needs.
>
> A second, smaller caveat in the other direction: this method counts every `F` byte against the
> CODE denominator, and 506 B of the merged function extent now falls in rows `architecture.md`
> calls DATA (the 14 `pickup_effect_*` handlers at `$105e4..$1079a`, plus 68 B carried from §0j).
> Intersecting extents with the CODE regions properly gives coverage 44,272 / 54,854 = **80.7 %**
> and a wall of **10,582 B** — the same numbers to a tenth, which is why the simpler method is kept
> for continuity with §0j.

### The residue map — what the remaining 10,582 bytes are

Only **226 bytes, 2.1 %, are genuinely unaccounted for.** Every other gap is either unreadable by
construction, or has a `var` from `../names.txt` sitting inside it naming what the bytes are:

| what | gaps | bytes | % of residue |
|---|---:|---:|---:|
| Copylock ciphertext `0xee68..0xf542` — unreadable by construction, not a campaign target | 1 | 1,754 | 16.6 % |
| **confirmed DATA** — a named `var` inside the gap | 44 | **4,734** | 44.7 % |
| inter-handler holes in the behaviour tier `$2462..$7522` — the handlers' own inline frame-word tables | 41 | 3,868 | 36.6 % |
| **still unknown** | 9 | **226** | **2.1 %** |

The largest confirmed-DATA gaps, each with the `var` that names it: `0xe978..0xecca` 850 B (sprite
bitmaps), `0x1a830..0x1aaca` 666 B (`$1a830`/`$1a864`/`$1a9d0`, sound tables), `0xe222..0xe43e`
540 B (`spawn_script_gate_table`), `0x21e4..0x23b6` 466 B (sprite-id words — and batch 40 phase C DIVIDED that one exactly: a flag word, three 88-byte posture records and four cursor-plus-table animations, all read by `player_stage_transition` and by nothing else), `0x73ce..0x7522` 340 B
(`actor_swoop_path_table` + `actor_swoop_paths`), `0xb444..0xb54c` 264 B (`effect_record_list`),
`0x938..0xa36` 254 B — **`actor_behavior_table` itself**, 62 longwords plus the three
`state_flag_a30/a32/a34` words, exactly 254 B, bounded above by its own first target.

The third row is the campaign's remaining question and it is a small one: 9 of the 41 holes are
cited by a handler's own plate as "its own PC-relative frame word table(s) at `$…`" (624 B), and
`$6586..$6786` (512 B) is `actor_aim_velocity_table`, the 32-byte-stride table
`actor_aim_velocity` ($6528) indexes — sixteen signed byte PAIRS a row, and batch 37 read the
routine: it allocates nothing and writes no memory at all, where the name and plate it carried
until then said it spawned from the table. Only row 6 has a ported reader (behaviour slot 21),
so what bounds the table above that row is still slot 45's business. The rest
are the same shape between consecutive handlers and are almost certainly the same thing, but they
are **not individually read**, so they are counted as inter-handler holes rather than as confirmed
DATA. The whole `still unknown` column is nine fragments, the largest 102 B (`0xed9c..0xee02`,
inside the Copylock's plaintext head).

### Stage 2 — the partition, DECLINED, with the numbers

The new tier landed where §0j predicted: **`game logic` (catch-all) went 20 fns / 2,058 B → 139 fns
/ 20,050 B**, 45 % of every measured byte in the one row that is not a positive classification. Only
one other row moved — `boot` +4 fns / +76 B, the `sprite_cru_copy_*` family at `$e92c..$e978`, which
lands there because its caller `sprites_cru_install` is already inside `0xe87c..0xecba boot`. Every
other row is byte-identical.

A new `actor (behaviour)` row is the obvious partition and **it is not drawn**, for three measured
reasons rather than a preference:

1. **No range set is both clean and stable.** Two closure rules were tried, both seeded with
   `$8d0`, `$928`, the 61 handlers and the targets of the four smaller indirect tables:
   * **rule A, "reached from the tier, stopping at any function another row owns"** — walk callees
     but descend only into members of the `game logic` catch-all: **125 fns / 18,046 B**;
   * **rule B, "private to the tier"** — iterate to a fixpoint, admitting a catch-all function only
     when *every* one of its callers is already in the tier: **122 fns / 17,756 B**.

   (Neither is the full transitive closure, which is not a candidate: unrestricted it reaches 284
   fns / 34,546 B, swallowing the whole disk, FDC, RAD, HUD and scroll stack.) Expressing rule A
   exactly — every range claiming closure members only — takes **13 ranges cut against today's
   function boundaries**, so any function a later batch names in one of the 41 inter-handler holes
   silently lands back in the catch-all. Merging them under the file's first-match-wins convention
   gets to 6 ranges, but the `0x53bc..0x73ce` one then spans **38 foreign functions** — the entire
   `disk (FAT12 + file load)`, `disk (WD1772 FDC + DMA)` and `resource depack (RAD)` stack — kept
   out of an "actor" row by nothing but row order. §0j's standard was a range that "claims catch-all
   members rather than moving any boundary"; this one leans on the boundary instead of respecting it.
2. **The tier has no principled edge — and the two rules fail differently.** **B is a strict subset
   of A**: `A \ B` is exactly three functions totalling **290 B** (which closes: 18,046 − 17,756),
   and `B \ A` is **empty**.
   * **A over-reaches, by exactly those three.** `$682 joy1_newly_pressed` (18 B — an *input*
     helper, also called by `scene_run_frame`), `$68c6 rng_next` (108 B, also
     `stage_random_kind32`/`_kind8`) and `$6bb8 actor_defeat_and_score` (164 B, also
     `actor_respawn_as_new_kind` and `copylock_key_check`). All three are shared services with named
     callers outside the tier; a row containing them is wrong. `actor_damage_followed` is **not** one
     of them — all 37 of its callers are inside the tier, so both rules keep it.
   * **Neither rule reaches `$19ac scene_spawn_from_script` at all** — 1,014 bytes, the second-largest
     routine the wall hid. It has **zero callers in the scan**: it is reached only through the same
     unresolved indirect dispatch this whole section is about, so A never walks to it and B's
     "every caller already in the tier" is vacuously unsatisfiable. That is not a tie-breaker
     between the rules; it is the argument for **landing the dispatch edge before drawing any row**,
     and it is the same defect the reachability sensitivity above measures.
3. **The player and the monsters are two mechanisms sharing one table.** Slot 1 is 3,336 B reaching
   the disk stack and the Copylock — all four of this pass's new false-greens; slots 2..61 are
   11,484 B that touch no hardware at all. Averaging those into one row is precisely the
   mis-partition §0 and §0e were drawn to undo.

**And there is a concrete reason to wait rather than a vague one:** 0 of the 123 are reachable from
the roots because the dispatch edge is unresolved. Adding it moves reachability from 144 to 289
functions and changes three functions' tiers. A partition should be drawn against the graph the
program actually has, not against an island — so the edge comes first, then the row.

`subsystems.tsv` is therefore **unedited this pass**.

### What is pinned

`tools/test_hw_portability.py` stays at **56 cases**, green. Five literal assertions across two
cases track the working scan and moved with it, in this commit, per the batch-22b-closed precedent:

* `test_the_committed_scan_reproduces_its_published_figures`: `284 → 407` functions,
  `26,194 → 44,262` bytes, runnable `(270, 24726) → (389, 41108)`, and — for the first time since
  §0i — **the false-green pin `(20, 2224) → (24, 3910)`**, with the four functions and the single
  shared witness path named in the case's comment.
* `test_the_tool_runs_end_to_end_as_a_script`: `270/284 functions, 24726/26194 bytes = 94.4 %` →
  `389/407 functions, 41108/44262 bytes = 92.9 %`.

Every other case is untouched and green, **including both `--model` capability cases**, which
compare function SETS: `psg:read` still buys nothing on top of Phase 6, and the two Phase-7 bytes
still carry the whole MFP/shifter block capability — across a scan that added 123 functions and
18,068 bytes. That is the strongest evidence yet for §0i's claim.

A fourth pin was checked and needed no edit: **all 378 `fn` addresses have an `F` record at that
exact address carrying that exact name**, 0 missing and 0 disagreeing, with no duplicate name and no
duplicate address in `../names.txt`. `ApplyNames` placed every one of the scout's 125 where the map
says.

### Still queued (not this pass)

§0i's three items and §0j's item 5 stand (`§6`/`§6.1` re-pricing, `notes/portability_predictions.py`,
the `T2`-declaration caveat, and `§1`'s stale answer box — whose whole-program half is now
54,854 / 44,262 / 80.7 %). §0j's item 4a is closed. This section adds three:

6. **The dispatch edge.** `$928`'s `jmp (a1)` and the four smaller `jsr (a1)` tables leave 123
   functions off the call graph, so the restricted table understates the running game by ~17 KB.
   Either teach the scan an `--extra-edges` input (the sibling of `--extra-hw`, and the same
   argument applies: prefer fixing the source) or plant the references in the DB.
7. **The `actor (behaviour)` partition**, once item 6 lands — with the player split out from the
   monsters, on the evidence above.
8. **`architecture.md`'s region table over-claims CODE** by at least 1,656 B that the scout read
   directly, and the residue map implies more. It is the denominator of every coverage figure in
   this file.

## 0l. Batch 42 phase A (2026-08-21): what moved, and what was NOT re-scanned

**NO RE-SCAN WAS RUN**, and this section exists so the figures above are not read as current. Every
count in §0a..§0k comes from `../out/hw_scan.tsv`, which still predates batch 33's decoder fix (the
queue in `STATUS.md` carries its regeneration). What this phase changed, stated so the next pass
knows what to expect rather than discovering it:

* **THREE FUNCTIONS became verified**, and each was blocked by a DIFFERENT thing, which is worth
  keeping straight because only one of them is the registration everybody remembers:
  `game_unpause_on_key_release` (`$638`, 54 B) carried the batch-12 REJECTED-with-a-registration
  plate and was blocked by its busy-wait; `game_key_actions` (`$53e`, 240 B of code) had no `fn` at
  all — it was unnamed, and what blocked it was the poked-input collision at `$604` rather than its
  own two waits; and `snd_start_fadeout` (`$17f92`, 16 B) was named, unblocked and simply unported,
  reached this phase because `$53e`'s ESC arm calls it. The first two sit in the
  `$420..$694` gap that no `subsystems.tsv` range claims, so they will land in the CATCH-ALL until
  the queued partition edit gives the spine a range of its own.
* **NO ROW'S HARDWARE CLASSIFICATION MOVES.** None of the three touches a hardware address: the pair
  reads and writes ordinary image bytes, and the fade trigger writes two of the sound module's own.
  The `T2 SEEDED_READ` and `T4 HW_READ` tiers are untouched, and so is §0i's four-false-green table.
* **THE `T*` LADDER GAINS NOTHING AND LOSES NOTHING, but the model behind it grew**: the kit's
  scheduled-write capability (TRAP_MODEL.md, "Phase 8") makes a routine that BUSY-WAITS on a memory
  byte an interrupt writes runnable at all. That is not a hardware tier — the byte is in the image —
  but it is the same shape of obstacle as `T2`'s, and the classifier prices neither. **A busy-wait on
  an image byte no instruction in the routine writes is invisible to this census**: it reads as
  ordinary code, and `$638` sat unportable for thirty batches without a row here ever saying so.
  Naming it is a candidate for the next re-pricing pass, beside `§6`'s.
* **ONE COUNT THAT IS NOT IN THIS FILE MOVED, and it belongs in the same paragraph**: the number of
  arms this project cannot drive because the kit's poked-input block covers game data. It was four
  in `game_key_actions` plus one in `player_meter_empty_check`; it is now zero, on the strength of
  `project.toml`'s `poked_input_program_data` declaration.

## 0m. Batch 42 phase B (2026-08-21): the first interrupt handler ever to run, and the floppy's PSG pair discharged

**Seven of the spine's nine remaining rows are reconstructed and green**, and between them they
discharge five tier predictions this document made — one direct and four transitive, itemised in
the table below — and narrow one blind spot. Nothing was re-scanned —
the tier figures below are §0i's and §0j's, quoted, not recomputed — so this section is about which
of those prices turned out to be payable, which is the only thing a port can add to a measurement.

| fn | bytes | tier this document priced it at | now |
|---|---:|---|---|
| `$624c` `psg_set_drive_select` | 28 | **T2**, direct, by its own `$6254` read-back | **RECONSTRUCTED & GREEN.** The price was exactly right and the mechanism is the one §0h named: the read-back is served from `psg_seed`, the write lands in the ledger, and both surfaces are compared. Its cases drive eight declared port-A bytes across seven `bits` values |
| `$6268` `floppy_deselect_drives` | 16 | **T2**, transitively, behind the above | **RECONSTRUCTED & GREEN** |
| `$716` `vbl_handler` | 52 | **T2**, transitively, behind the pair | **RECONSTRUCTED & GREEN — and it is the first interrupt handler in this project, or in either sibling, that a differential has ever executed.** Blind spot 7 is narrowed accordingly. What made it runnable is a checkpoint at its `rte`, which is the kit's existing `stop_pc` and not a new device |
| `$e032` | 118 | **T3 HW_WRITE_ONLY**, behind `stage_load_window`→`set_palette` | **RECONSTRUCTED & GREEN** as `round_bonus_run_frame`. The T3 edge is real and is inherited whole: the sixteen colour writes its setup arm reaches are dropped by the oracle and stay unpinned |
| `$e0a8` | 104 | **T3 HW_WRITE_ONLY**, same edge | **RECONSTRUCTED & GREEN** as `round_bonus_setup` |
| `$50a`, `$882` | 62 | T0 | **RECONSTRUCTED & GREEN** |

**AND THE LAST TWO MOVED IN BATCH 42 PHASE C, WHICH CLOSES THE SPINE — and what the previous
version of this section got right is worth keeping.** `$694` `flip_screen` is T3 HW_WRITE_ONLY —
three dropped registers over FOUR write instructions: `$ffff8201` at `$6b6`, `$ffff8203` at `$6c0`,
and `$ffff8240` twice, `$777` at `$6f8` and a `clr.w` at `$702`, the flash's two mutually exclusive
arms — and on that pricing it is as portable as `set_palette`, which has been green since batch 12.
It was not ported for two phases, and **the hardware was not why**. What stopped it was the HARNESS,
in the worse of the two possible ways: the model did not refuse the natural one-run case, it ACCEPTED
it and balanced its poll and arrival totals by an off-by-one that cancelled, so a case went green
while the two sides ran different iteration counts. Both busy-waits compare a WORD, and the model
counted polls per RUN rather than per SITE.

| addr | bytes | tier | what happened in batch 42 phase C |
| --- | ---: | --- | --- |
| `$694` `flip_screen` | 118 | **T3 HW_WRITE_ONLY** | **RECONSTRUCTED & GREEN.** The kit now counts polls and arrivals per WAIT SITE (`TRAP_MODEL.md`, Phase 8), so the routine's two waits are separable in one run. Its THREE registers stay dropped and unpinned, and the sweep MEASURES that rather than asserting it: four named mutants over them — the wrong buffer published, the two base bytes swapped, the flash's two arms swapped, the sink write moved above the timer store — all survive the whole suite |
| `$4a0` `game_main_loop` | 106 | T0 itself; T3 transitively, through the flip | **RECONSTRUCTED & GREEN.** A composition of fifteen calls, and the tier it inherits is the worst of its callees' |

**AND THE THREE DROPPED REGISTERS ARE NO LONGER UNPINNED — THE PIN IS OFF TARGET'S REACH, NOT THE
ORACLE'S.** Batch 43 phase B runs the reconstruction on a 68000 with the shipped binary's own
post-boot RAM staged, and phase D adds the hardware-state vector and the rendered picture on top of
it. `atari/README.md` §9 and §10 measure the five mutants above again *there*:

| mutant over `flip_screen`'s dropped registers | under the differential suite | on target |
| --- | --- | --- |
| the two base bytes swapped (shared translation) | survives | **CAUGHT at M1** |
| the two base bytes swapped (flip_screen's own two call sites) | survives | **CAUGHT at M2** |
| the wrong buffer published | survives | **CAUGHT at M2** |
| the flash's two arms swapped | survives | **CAUGHT at M5** (`smoke.py m5flash`), on three surfaces and at both arms. Its phase-B survival was a data-reachability hole and not a surface hole, exactly as recorded: `WB_FLASH_TIMER` is `$0000` in the staged image, and the census in `../names.txt` `cmt 0x714` shows the image's only raiser is unreachable in the anchored window twice over. M5 seeds the word on BOTH sides with that raiser's own operand |
| the sink write moved above the timer store | survives | **SURVIVES ON TARGET TOO, and structurally.** Measured under `m5flash` with the flash live — the strongest snapshot this project can build. It changes no value, only the order of two writes, so no snapshot will ever see it. M6's, the write timeline |

**WHAT THAT ADDS TO THIS DOCUMENT'S ARGUMENT.** A T3 price says the oracle cannot see the write. It
does not say the write is unpinnable — it says the pin is not in this harness. Four of the five
mutants above died the moment a real shifter was on the other end of the call, and the fourth needed
only a state the anchor's own data could not reach, seeded identically into both sides. The tier
tells you which surface a pin has to come from; it does not tell you there is none.

**AND THE FIFTH IS THE INTERESTING ONE.** It is the only mutant here whose survival is a statement
about the KIND of surface rather than about coverage: it is invisible to a snapshot at any anchor,
under any data, because the two orderings leave identical state. That is a genuinely different
verdict from "the oracle drops the write" and from "the window never reaches it", and it is the case
this document's tier vocabulary has no word for — a routine whose price is not what the oracle can
see, nor what the harness can drive, but what a *point-in-time comparison* can distinguish at all.

**WHAT M5 DOES AND DOES NOT PIN ABOUT THE PSG.** Phase D captures the whole YM-2149 register file on
both sides at every anchor and compares NONE of it, and the reason is measured rather than assumed:
two boots of the SHIPPED BINARY ITSELF write different sound registers at the same anchor
(`original.py vecnoise` — `ym00`, `ym02`, `ym04`, `ym08`, `ym10`), because the music's cursors depend
on which vblank the boot finished on. So this document's T2 PSG pricing keeps its meaning unchanged
on target: the direct YM ports are real hardware there, and what a snapshot still cannot supply is
an *assertion* about them. The only surface that could is the ordered write timeline, M6's.

**THE LESSON FOR THIS DOCUMENT STANDS UNCHANGED, and it is now paid for twice: a T0 or T3 price is a
statement that the oracle can SEE the routine, not that the harness can DRIVE it** — the two come
apart wherever a routine waits on something outside itself, and §6's capability table has no column
for that. What phase C adds is the other half: the gap was closable, and closing it was a change to
the MODEL rather than to the tier.

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
  list, the routine is now named (`fn 0x51ac bcd_add_random_1_to_4` in `../names.txt`), which makes
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
  missed here. *(Marked in place — §0i. This figure survived §0d, §0g and §0h unchanged and moves
  for the first time there: kit Phase 7 makes `$fffa01` and `$ff820a` declared case inputs, which
  takes 8 functions / 1,124 bytes out. Today's measurement is **20 / 258 functions, 2,224 /
  25,826 bytes = 8.6 %**, and it is still a lower bound for both reasons above.)*

Both roots close to T5, for the same reason: `game_main_loop → FUN_0000053e →
show_data_disk_prompt → load_resource_by_index → copylock_entry`. That single edge is what makes
the *whole-program* number look bad; per-function it costs almost nothing (see §6).

### Subsystem partition

| subsystem | fns | bytes | direct worst | transitive worst | direct T0 | runnable | false-green |
|---|---:|---:|---|---|---|---|---|
| video (background scroll) | 39 | 7,010 | **T0** | **T0** | **39 / 7,010 B** | **39 / 7,010 B** | 0 |
| game logic | 87 | 6,904 | T3 | T5 | **85 / 6,752 B** | **78 / 5,156 B** | 3 / 372 B |
| sound (YM2149) | 21 | 2,634 | **T4** | **T4** | 19 / 1,844 B | 13 / 1,622 B | 2 / 710 B |
| video (sprite blitters) | 12 | 2,254 | **T0** | **T0** | **12 / 2,254 B** | **12 / 2,254 B** | 0 |
| boot | 11 | 1,072 | T3 | T5 | 7 / 348 B | 4 / 296 B | 8 / 798 B |
| disk (FAT12 + file load) | 11 | 1,030 | T3 | T3 | 10 / 870 B | 11 / 1,030 B | 6 / 630 B |
| map (collision + settle) | 9 | 924 | **T0** | **T0** | **9 / 924 B** | **9 / 924 B** | 0 |
| actor (table + lifecycle) | 14 | 864 | **T0** | **T0** | **14 / 864 B** | **14 / 864 B** | 0 |
| disk (WD1772 FDC + DMA) | 20 | 684 | **T4** | **T4** | 8 / 82 B | 18 / 640 B | 6 / 468 B |
| text (message box) | 3 | 678 | **T0** | **T0** | **3 / 678 B** | **3 / 678 B** | 0 |
| stage (load + reset) | 3 | 458 | **T0** | **T4** | **3 / 458 B** | 2 / 248 B | 0 |
| input (IKBD / ACIA) | 4 | 300 | T3 | T3 | 1 / 10 B | 4 / 300 B | 1 / 230 B |
| video (screen / palette / mode) | 8 | 236 | T2 | T2 | 4 / 38 B | 8 / 236 B | 0 |
| copylock (protection) | 4 | 232 | **T5** | **T5** | 2 / 52 B | 1 / 16 B | 1 / 36 B |
| resource depack (RAD) | 3 | 216 | **T0** | **T0** | **3 / 216 B** | **3 / 216 B** | 0 |
| resource loader | 2 | 148 | T2 | T5 | 1 / 44 B | 1 / 44 B | 1 / 104 B |
| interrupt (VBL) | 1 | 52 | T0 | **T4** | 1 / 52 B | 0 | 0 |

**Five of those rows are now 100 % reconstructed and green** — background scroll (39 fns, 7,010 B),
map (9, 924 B), actor (14, 864 B), text (3, 678 B) and the RAD depacker (3, 216 B). Every one of
them is T0 direct *and* transitive, which is why they were reconstructable with no new harness
capability at all: the answer box's right-hand column is what the §7 recommendation turned into.
(The actor row's *coverage* still reads 90.6 %, for the counting reason under the answer box's
table: two of its reconstructions are in no `F` record.)

**The `stage (load + reset)` row is the one to read twice.** With `interrupt (VBL)` it is one of the
only two rows that are **T0 direct and T4 transitive** — nothing in either touches hardware, and
both reach the sound module through a call: `stage_load_window`'s `jsr (a1)`/`jsr 28(a1)` pair and `vbl_handler`'s
`jsr 14(a0)`. 210 of the stage row's 458 bytes are unrunnable behind the PSG wall §6 prices. Every
other blocked row is blocked by hardware of its own.

The two disk rows are the shape to notice. **The FDC driver runs almost entirely** — 18 of its 20
functions, and all 11 of the FAT12 layer's. Between them those two subsystems hold **12
false-green functions and 1,098 bytes** that a differential will happily call verified. What those
runs actually report is §4 and §7.4b: the polls succeed instantly, the commands built on them fail.

**So: yes, the gameplay logic is portable today — as far as it has been recovered.** The only
game-logic functions that touch hardware are the two PRNGs, `rng_next` (`$68c6`) and
`bcd_add_random_1_to_4` (`$51ac`), and both are T3-DATA reads, not steering ones. **Neither is a false
green any more (batch 33):** the two bytes between them — `$ff8207`, `$ff8209` — are now in the
kit's Phase 7 modeled set, so a case DECLARES what the counter held, the read lands on the ordered
ledger both sides compare, and an undeclared one refuses the differential instead of being answered
with a fabricated 0. The modeled census is four addresses, not two: `$fffa01`, `$ff820a`, `$ff8207`,
`$ff8209` — and `tools/hw_portability.py`'s seeded set grew with them, so a byte read of either
counter byte prices **`T2 SEEDED_READ`** today, not the silent-zero read tier this section's own
tables put it in. Two limits ride with the retirement. A declared byte still does not model a
counter read TWICE in one call and expected to differ — neither of these two does that, and the
model calls both slots VOLATILE and refuses the second read rather than serving the first one's byte
again. And the retirement is a DIFFERENTIAL's: under AUDIO CAPTURE the profile declares only
`$fffa01` and `$ff820a` (`HW_CAPTURE_PROFILE_KNOWN` in the shim), so the two counter bytes go on
reading a fabricated 0 there — deliberately, because a capture run verifies nothing against a second
core and so cannot be falsely green. The **78.2 %** of game-logic CODE that is in no function body
is outside that claim entirely — and after §0b's re-measure that is not merely the dominant fact
about the bucket, it is the dominant fact about the whole report: two re-measures have lowered the
catch-all's coverage from 36.0 % to 21.8 % without reaching a single unmeasured byte.

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
| T4 | `snd_music_tick` `$17c74` | rejected with the PSG diagnostic | ❌ **completed green in 12 insns** *(RETIRED — batch 25. That green is no longer reachable: `$17c74` is reconstructed, and a differential of it whose case declares no `hw_seed` is REFUSED. See the two markers below.)* |

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

*(Marked in place — batch 25. The correction above still stands as written; what has moved is the
example. `$17c74` is now reconstructed, and its 44-byte head runs under the kit's SEEDED HARDWARE
READ model, so the run this paragraph describes is refused rather than green whenever a case fails to
declare the machine. The general point — "T4 means cannot be verified ACROSS ITS INPUTS, not every
run is refused" — is unchanged and is exactly why a per-case declaration was the fix.)*

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

*(CLOSED — batch 25, and this is the section the kit's Phase 7 was built from. The two reads are now
DECLARED inputs: `harness.differential` refuses a case that does not name what the machine holds, so
"both sides store the same wrong value" is no longer a green a case can reach. The three arms are
reconstructed and pinned one machine each, and the mono row's ordered read stream is what says the
sync register is not even touched. What is still **not** pinned is unchanged and is the model's own
honest limit: that a real ST answers `$b0`/`$02`. `tools/recreate_kit/TRAP_MODEL.md`, "Phase 7", and
`../STATUS.md`'s batch-25 section.)*

## 5. The false-green surface — every steering hardware read

> *(Marked in place — **batch 43 phase A, 2026-08-21**. Two of the rows below are no longer a
> surface at all in the on-target build: `atari/wonderboy_backend.c` implements `hw_read8` as the
> read itself, so `$17c7e`'s `$fffa01` and `$17c90`'s `$ff820a` — **the BuggyBoy register** — answer
> for themselves on the machine. It is measured rather than asserted: `atari/smoke.py m1` reads the
> byte `tempo_drop_value` leaves in the image and gets `WB_SND_TICK_DROP_50HZ` on a colour boot, and
> the SAME BINARY booted with `--monitor mono` gets `WB_SND_TICK_DROP_MONO`. A code control cannot
> show that a hardware read is live rather than folded; changing the machine can, and that is the
> only evidence in this project that any of these reads is real.*
>
> *The two VOLATILE rows — `$6910` in `rng_next` and `$51ae`/`$51b6` in `bcd_add_random_1_to_4`,
> which mix the video address counter — are ALSO real on target, and that is where "the diff stays
> clean while the game's randomness silently disappears" stops being true. They are not yet
> EXERCISED: neither routine runs in M1. Registered, not discharged.*
>
> *Every other row below is unchanged. The FDC rows in particular are untouched — the floppy driver
> is unported and the on-target build stages its image through GEMDOS instead.*

The classifier reports **10 sites in 6 functions**:

> *(Marked in place — §0i. **5 sites in 3 functions** today. The five `$fffa01`/`$ff820a` rows below
> — `$62da`, `$633c`, `$6422`, `$17c7e`, `$17c90` — are no longer part of this surface: kit Phase 7
> serves those two bytes from the case's own `hw_seed=` and refuses a differential that declares
> neither, so a branch on them is steered by a declared input. The rows are left as the measurement
> of their day; what each read DECIDES is unchanged and still worth reading, and the "reads as
> 'done' always" / "always 0" annotations now describe what an UNDECLARED case gets — which a
> differential refuses rather than runs. The under-count below is unaffected: both `WINDOW` reads it
> names are FDC registers, outside the modeled set.)*

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
* `$6910` in **`rng_next`**, and `$51ae`/`$51b6` in **`bcd_add_random_1_to_4`** — the game's two PRNGs
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
| MFP read model — **BUILT**, §0i | 220 | 21,534 | 22 (−6) | 2,934 (−414) |
| FDC/DMA read model | 220 | 21,534 | 28 | 3,348 |
| **MFP + FDC/DMA read model** | 220 | 21,534 | **10 (−18)** | **1,106 (−2,242)** |
| ACIA read model | 220 | 21,534 | 26 (−2) | 3,096 (−252) |
| shifter read model — **BUILT**, §0i | 220 | 21,534 | 28 | 3,348 |
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
  *(Marked in place — §0i: the MFP and shifter halves are BUILT, as a named set of two BYTES rather
  than as whole blocks, and on the current scan the two bytes are worth every function the two whole
  blocks were. The FDC/DMA half is Phase 7's explicit NON-GOAL — a status byte that must change
  between two reads cannot be expressed by a per-run seed — so this row's remaining value is a
  transaction model nobody has built, and the whole `−18` was never available from one phase.)*
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
loader** goes transitive-T5 → T3 with `load_resource_by_index` becoming runnable, so that row goes
1 / 44 B → 2 / 148 B (it gained `resource_table_relocate`, already runnable, in §0b).

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
2. **The game-logic core** (78 functions, 5,156 bytes runnable today; 62 of them / 3,098 bytes are
   already green). 85 of its 87 recovered functions touch no hardware. Avoid the 3 with a
   steering T3 below them until step 4; the two
   PRNGs are portable but must be documented as *seeded from hardware the oracle zeroes*, so any
   test over a caller of one is exercising a single fixed pseudo-random stream. **Remember the
   denominator**: this is 16.3 % of the game-logic code believed to exist, so a "done" here is not a
   done subsystem — and §0b's re-measure lowered that denominator's coverage again rather than
   raising it, because every subsystem carved out of the catch-all so far was among the
   best-measured code in it.
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
   **AND WHAT IS THERE AT RUN TIME IS NOT SIMPLY THE PLAINTEXT, MEASURED (batch 43 phase B).** The
   sub-range `$f314..$f514` — 512 of these 1,970 bytes — holds something DIFFERENT after every boot:
   `atari/original.py variance` differences two boots of the shipped disks stopped at the same
   instruction and that band turns over completely each time, as a descending, wrapping sequence.
   So those 512 bytes are the protection's own trace/timing scratch rather than code it decrypted,
   and a dump of the running machine does not recover them as anything. It changes nothing about
   this row's conclusion — the region is still unreadable and still outside every scan — but "the
   ciphertext only ever exists decrypted at run time" is too strong for that part of it.
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
7. **Interrupt handlers are tiered, and until batch 42 phase B none of them had ever executed under
   the oracle.** `vbl_handler`, `ikbd_acia_handler` and the two joystick handlers are the game's only
   clock and its only input path. **`vbl_handler` NOW RUNS** — §0m above — so the blind spot is
   narrower than it was and is stated as it now stands rather than deleted: the remaining three have
   still never been executed by a differential, and what made the fourth runnable (a checkpoint at
   its `rte`, since the runner's stack frame is an `rts` frame) applies to them unchanged. What
   neither the old form of this item nor the new one claims is that the handlers run *when the
   machine would run them*: a differential enters one deliberately, on a seeded frame, and the
   scheduling is the case's claim and not the model's.
8. **`--model` prices a capability by assuming it is perfect.** A real FDC model that returned
   plausible-but-wrong status would move the same functions out of the false-green count while
   leaving them just as unverified. The table says what the ceiling is worth, not what a given
   implementation would deliver. §6's PSG entry is the worked example: the obvious implementation
   is already known to be insufficient.

---

## 0n. Batch 43 phase C — no classification moves, and a defect class the classifier does not price

**Nothing in this file's tables changes.** No function was ported, no hardware access appeared or
disappeared, and the runnable/false-green split is exactly as §0m left it. The batch is recorded here
only because it found a portability defect of a KIND this classifier is blind to, and a reader who
trusts these tables should know the shape of what they do not cover.

**WHAT THE CLASSIFIER PRICES** is a function's reachability into hardware: which `$ff8xxx` operands
it touches, and whether the kit models them. **WHAT IT DOES NOT PRICE** is where a reconstruction's C
*puts* an address the game computed. `src/scene.c` read a scene descriptor through the raw pointer at
WB_RECORD_PTR_10420 and `src/map.c` read every actor field through a raw `actor`; on a seed the suite
has driven since batch 42 those reads landed 2.4 GiB past the ctypes buffer, in the host heap. Both
routines were classified RUNNABLE throughout and both were: the classifier's question is about the
ORIGINAL's operands, and this is a property of the PORT. See `../recreate/STATUS.md`, batch 43 phase
C, for the diagnosis and the fold.

**THE THIRD STANDING CHECK.** `Reproducing it` above lists `pytest tools/test_hw_portability.py`
(56 cases) as the classifier's own pins. The guarded-image sweep now sits beside it and is the
instrument that measures this other class:

```bash
cd projects/wonderboy/recreate && PYTHONPATH=../../../tools .venv/bin/python -m pytest -q -n auto \
    -p recreate_kit.guarded_image test
```

It read **5 crashing cases of 6,140** against the reconstruction at this batch's HEAD and **0** after
the fold. It is not in `make test` and it cannot see a raw access that stays inside the buffer —
`tools/recreate_kit/README.md` states both limits.

**AND IT LEAVES AN UNPINNED MODELLING DECISION ON TARGET.** Routing an address through `include/bus.h`
answers a read outside the loaded image with zero and drops a write there, which is the oracle's
answer and not a real ST's — that machine has RAM or the `$ff8000` I/O page at those addresses.
`atari/README.md`'s "Known gaps" carries it. It is the same class as this file's own §6 caveat 8: a
model priced as perfect is still a model.

## 0o. Batch 43 phase E — no classification moves, and the first on-target evidence about the PSG

Like phase C, this phase moves **no tier and no figure in this file**: it touches `atari/` only, and
the classifier's question is about the ORIGINAL's operands. It is recorded here because it produces
the first measurement this file has ever had about two of its own standing caveats.

**§5's false-green surface, and the PSG.** §5 enumerates every steering hardware read and prices the
harness's blindness to what the game *writes* to the sound chip as unmeasured on target. It is
measured now, one window deep: `atari/smoke.py m6` compares the **ordered stream** of YM-2149 writes
against the shipped binary's over fifty-two frames, and the shipped side's 1,155 (register, value)
pairs are an **exact prefix** of the reconstruction's 6,424. That is not a claim about the model —
the harness still cannot see a PSG write's effect — but it is a claim about the port: over that
window, every write the original made, the reconstruction made, in the same order.

**AND IT COMES WITH ITS OWN NOISE FLOOR, which §8's discipline requires.** `original.py psgnoise`
boots the shipped binary a second time and differences the streams. Four pairs on TOS 1.04: two
**unflashed** pairs, **0 of 1,155** writes differing in each; two **flashed** pairs, one differing in
**42** — all of them channel A's tone period (registers 0 and 1) inside the first eleven frames — and
one differing in none. So the assertion above is over all eleven registers in the unflashed window
and nine in the flashed one, and the exclusion is printed rather than absorbed.

**THE PAIRING IS INTERMITTENT, and that is the part §8 would want stated first.** One flashed pair
differed and the next did not, so a reading taken today can license comparing a register the project
has already watched move. Two mitigations, both of them §8's own shape: the per-machine reading
ACCUMULATES rather than overwrites (a register once seen to move stays excluded, and a stored `pairs`
count says how much looking is behind it), and `original.py`'s `PSG_REGISTERS_KNOWN_UNSTABLE` carries
a **committed floor** — `build/` is gitignored, so a reading kept only there starts empty on every
clone. The measurement is one-directional in exactly the sense §8 insists on: a register that moves
is demonstrably one boot's accident; one that does not is **not thereby shown to be stable**, and two
pairs is not a sample that could bound anything.

**A SECOND UNPINNED MODELLING DECISION, in the same family as phase C's.** The timeline reads five
registers — the screen base's two bytes, the sixteen pens and the two YM ports. The MFP, FDC and
RS-232 writes that share the trace are dropped, because they belong to TOS and to the floppy and
differ between a GEMDOS drive and a real one by construction. A reconstruction bug that reached one
of those would not be seen by anything in this workspace. Same shape as §6 caveat 8, one surface
over: an instrument priced as complete is still an instrument, and this one names its five.

**THE FOURTH STANDING CHECK** — `atari/smoke.py m6`, `m6rearm` and `m6flash`, green on both ROMs, and
`original.py timeline` / `psgnoise` (plus their `F`-prefixed pair) as their prerequisites.
`atari/README.md` §11 carries the argument and the instrument's three measured gotchas.

## 0p. Batch 43 phase F — no classification moves, and the exit path priced

Like phases C and E, this phase moves **no tier and no figure in this file**: it touches `atari/`
only. It is recorded here because it found a defect of a class this file's model prices at zero, and
because it puts a measurement under a caveat §8 has carried since the on-target arc opened.

**THE CLASS THE CLASSIFIER CANNOT SEE IS "CODE NO SURFACE EXECUTES", and the exit path was it.**
`game_key_actions`' three endings and everything after them — `run_frames`' third exit, `teardown`,
`Pterm` — were compiled into thirteen green on-target modes and executed by **none** of them, because
every mode ran the loop to its frame count and left by the watchdog's door. Driving the endings
found, on the first try, an **uncapped wait aimed at the wrong byte**: `pin_sched_wait8` took the
scancode the frame loop had exited on for the IKBD's reset acknowledge and then spun for a byte the
controller will never send. The program never reached `Pterm`, so nothing was written and nothing was
handed back. `atari/README.md` §8 has the fix and the isolation.

This is not a portability tier and it is not a modelling hole; it is the plainest possible reminder
that **the tiers in this file classify code the harness RUNS**. A T1 routine nothing executes is
verified in exactly the sense that an unexecuted assertion is passing.

**§8's "the joystick and key arms are unexercised" caveat is now a MEASUREMENT.** It used to rest on
"a headless run cannot press anything", and that half is false: Hatari 2.6.1's `--control-socket`
takes `hatari-event keydown/keyup <ST scancode>`, and the injected code really does arrive in
`WB_KEY_LAST_SCANCODE` through the real ACIA interrupt — scancodes `$50`, `$29` and `$4b` read back
out of the running image, with the shim's `ikbd_bytes` rising from 3 to 10. What that path cannot do
is press the STICK: it injects at the emulated IKBD while `--joy1 keys` maps host SDL key events, so
`WB_JOY0_STATE`/`WB_JOY1_STATE` stayed `$00` under all four injected scancodes including both arrows.
The `$fe`/`$ff` arms therefore stay unexecuted **for a measured reason** rather than an assumed one.

**THE FIFTH STANDING CHECK** — `atari/smoke.py m3` and `m3fault`, green on both ROMs (four runs
each: the undriven boot, the cheat word's own control, and the three endings), plus
`atari/smoke.py runsh`, which parses the one command line no headless mode executes.
`atari/README.md` §12 carries the argument, including why the tail readings hang off the program's
own `Pterm` and not off a vblank count.

## 0q. Batch 44 phase A (2026-08-22): the BOOT CHAIN counted, and why its remainder is a hardware wall

**NO RE-SCAN WAS RUN** — §0l's banner still stands, and `../out/hw_scan.tsv` still predates batch
33's decoder fix. What this phase adds is a census of a region no `subsystems.tsv` row has ever
claimed: the boot chain, `recreate/test/test_boot_inventory.py`, 57 routines and 4,598 bytes reached
from the PRG entry and from `show_data_disk_prompt`.

**IT MATTERS TO THIS FILE BECAUSE THE REMAINDER IS ALMOST ALL `T4`.** Of the 2,730 unported bytes,
**1,644 — sixty per cent — are the raw WD1772/DMA driver and the FAT12 layer above it** (`$5e3e..$6528`,
summed over the walk's own segments rather than estimated) — the
routines architecture.md §2.2 enumerates, whose entire observable surface is `$ffff8604`-`$ffff860d`,
`$ffff8800/8802` and `$fffffa01` bit 5. **The memory differential cannot see any of it**, and the
kit has no floppy device model, so these are not "unported because nobody got to them": they are
unportable with today's capabilities, in the same sense §5's steering reads were before Phase 7.
That is the honest reason the `.PRG` still cannot boot from its own entry, and it is a capability
question for §6 rather than a scheduling one.

**WHAT DID MOVE, and none of it changes a hardware classification.** Ten routines became verified
(362 bytes): three block movers, the two boot products (`bg_tile_install` `$e67e`,
`sprites_cru_install` `$e87c`) and four cell copiers — all PURE MEMORY, which is exactly why they
were takeable — plus `clear_palette` (`$e7f4`), which is pure shifter.

**`clear_palette` JOINS `set_palette` ON §5's LIST, and it is the same entry twice.** Sixteen writes
to `$ffff8240`, all dropped by the oracle because the address is off the loaded image, so the
routine's whole differential surface is "it touched no image byte". WHICH registers were cleared is
unpinned and unpinnable until the dropped-hardware-write ledger §6 prices gets built. The count of
routines in this project whose OUTPUT is a dropped hardware write is now **two**, not one.

**AND ONE BLIND SPOT §8 DID NOT HAVE.** Every count in this file comes from a scan of a LISTING or of
Ghidra's reference model, and this phase found `tools/prg_dis.py` reporting the wrong LENGTH for
`move to SR`/`CCR` — eight sites in the boot chain, including `cold_start`'s first instruction. A
sweep that desyncs there drops instructions rather than printing nonsense (docs/m68k-disassembly.md
§"A desynced sweep **drops** instructions"), so any hardware-access count taken from a listing across
one of those sites was a LOWER BOUND without saying so. `hw_scan.tsv` is Ghidra-derived and so is not
affected; the byte scans in `../notes/architecture.md` §2.3 are operand scans and are not either. It
is recorded here because the next re-scan should not re-learn it.

## 0r. Batch 44 phase B (2026-08-22): the wall is a SEAM, and a T4 region became a declared boundary

**NO RE-SCAN WAS RUN** — §0l's banner stands. What changes here is not a measurement but a
CLASSIFICATION: §0q priced 1,644 bytes as "unportable with today's capabilities", and this phase
shows that the right answer for them is not a capability at all but a **boundary with one edge**.

**THE CHANGE OF KIND, in one sentence.** §0q read the disk driver the way this file reads every other
hardware region — count the accesses, price the model that would be needed, and register it. But a
loader is not a steering read: its whole output is *the file's bytes at an address*, and the routine
that asks for them (`disk_load_file`, `$5e7c`) is entered with **a name and a destination**. So the
region does not need to be modelled, it needs to be **cut around**, and the kit's new
`disk_read_file` (TRAP_MODEL.md Phase 9) is the cut. That is a different answer from "build a WD1772
model", and the difference is worth stating in this file because §6's price list would otherwise
carry a device model nobody should build.

**WHAT MAKES IT A BOUNDARY AND NOT A HOLE**, measured in `test_boot_inventory.py`:

* the boot chain crosses into `[$5e3e,$6528)` **exactly once**, at `jsr $5e7c.w` (`$e79c`);
* the whole image encodes **four** edges in, each classified — the seam, an INTERRUPT edge at `$73e`
  (the vblank handler's floppy-motor timeout, which no walk over call edges can see), the Copylock's
  failure arm, and one operand fragment;
* and **the band transfers out nowhere at all** — a closed subgraph that leaves by `rts`. A boundary
  whose interior called back into ported code would be a hole; this one is an edge.

**THE HARDWARE CLASSIFICATIONS THEMSELVES ARE UNCHANGED.** `disk (WD1772 FDC + DMA)` is still T4,
still 684 bytes of hardware surface, still unportable. What moved is that it is now EXCLUDED by
declaration rather than pending, and the exclusion has terms: the substitution reproduces the seam's
contract and nothing else — no seek, no motor, no `floppy_idle_timer`, and no way to fail the way a
real disk fails.

**ONE INTERACTION THIS FILE SHOULD OWN.** The vblank handler counts `floppy_idle_timer` (`$64f2`)
down and calls `floppy_deselect_drives` (`$6268`, reconstructed since batch 42 phase B) when it
expires. A GEMDOS substitution **never arms that timer**, so on target the two mechanisms do not
meet: the reconstruction will never deselect a drive because it never selects one. Harmless — nothing
else reads the timer — but it is a real difference between the substitution and the original, and it
is the kind of thing that is invisible until a later phase wonders why a PSG port-A write it expected
never happens.

**AND ONE NEW ENTRY FOR §6's PRICE LIST, which is cheap rather than a device model.** The staged-file
model answers served or REFUSED, and a refusal sinks the run — so a reconstructed loader's ERROR arm
has no differential available to it and is candidate-only. What is missing is a third answer: a
staged name declared **present but unreadable**. It is a field in an existing table and a branch in
`os_fopen`, not a subsystem.
