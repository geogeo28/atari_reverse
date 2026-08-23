# SWB.PRG — code/data map, anchor inventory and memory map

Target: `projects/wonderboy/bin/disk1/AUTO/SWB.PRG` (136,979 bytes on disk;
`text=0x214d8`, `data=0`, `bss=0`, `sym=0`, **3** relocation entries, text
entropy 4.96 → plain code+data, not crunched).

Stage 1 deliverable. Everything below is stated with the evidence that decided
it; anything I could not decide is called out as UNVERIFIED rather than smoothed over.

---

## 0. THE HEADLINE: the program does not run where you load it

`SWB.PRG` is **position-dependent**. The 3 relocations are all in a 48-byte
bootstrap stub at the very end of the image; the body has none, because it does
not need any — it only ever runs at one absolute address.

The PRG entry is 8 bytes:

```
$3f8   3000                      (padding word)
$3fa   4ef9 000213e0    jmp bootstrap_relocate     <- relocated
```

and the stub it jumps to (image offset `0x213e0`) is:

```
2f3c 000214d8          move.l  #text_end,-(sp)     <- relocated
3f3c 0020              move.w  #$20,-(sp)
4e41                   trap    #1                   ; GEMDOS Super(new_ssp)
46fc 2700              move.w  #$2700,sr            ; supervisor, IPL7
43f9 00000400          lea     $400.l,a1
41f9 00000008          lea     image+8,a0           <- relocated
203c 000084f6          move.l  #$84f6,d0            ; 34038 longwords
22d8               .l: move.l  (a0)+,(a1)+
5380                   subq.l  #1,d0
6600 fffa              bne.w   .l
4ef9 00000400          jmp     $400.l
```

`0x84f6 * 4 = 0x213d8` bytes, copied from image offset 8 to absolute `$400`,
ending exactly where the stub itself begins. So:

> **runtime address = image offset + 0x3F8**  (image offset = file offset − 28)
>
> The program body occupies **`$400` … `$217D8`** and never moves again.

### Consequence for the Ghidra pipeline (this is the whole Stage-1 unlock)

Loaded at the workspace default `0x10000`, every absolute operand in the body
(`jsr $xxxx.l`, `lea $xxxx.l`, `move.w d0,$xxxx.l`) points *outside* the image
block, so Ghidra's flow analysis cannot follow a single one of them.
**That, not packing or jump tables, is why only 57 functions were found and why
the image looked full of unexplained multi-kilobyte gaps.**

Re-imported at base **`0x3F8`** the same binary yields **186** functions before
any naming, and every `DAT_0000xxxx` resolves to a real in-image address. The
base is not a guess — it is forced by `lea image+8,a0` / `lea $400,a1`, and it
also makes the three relocations self-consistent (they resolve to `$217d8`,
`$218d0` and `$400`, all correct in that space).

```bash
# correct bootstrap. run.sh has been corrected to pass 0x3f8, so `bash projects/wonderboy/run.sh`
# is equivalent — but it re-imports and wipes the DB, so iterate with reapply.sh.
bash tools/headless.sh projects/wonderboy/ghidra_proj wonderboy \
     projects/wonderboy/bin/disk1/AUTO/SWB.PRG 0x3f8 projects/wonderboy/decomp.c
```

**Converting older notes:** `runtime = old_ghidra_addr − 0xFC08`. Every address
in this document and in `names.txt` is a runtime address.

One artefact to keep in mind: the bootstrap stub appears at `$217d8` in this
address space, but at run time it executes at *basepage_text + 0x213e0* —
wherever GEMDOS loaded the file. It is the only part of the image for which the
`0x3F8` base is fictional.

---

## 1. REGION TABLE — every byte of `$3F8`…`$218D0`

Method key:
* **F** = Ghidra recovered functions here (after the rebase).
* **I** = instruction-idiom density measured over the region (`rts` per 1000
  words, plus `bsr`/`jsr`/`movem`/`dbf`/`lea` counts). Code runs ~14–16 `rts`
  per 1000 words with hundreds of `bsr`/`lea`; data runs 0.
* **R** = something in the image references it, and how (call vs. load).
* **B** = byte-pattern / entropy / ASCII-fraction evidence.

| start | end | size | kind | evidence |
|---|---|---:|---|---|
| `0x0003f8` | `0x000400` | 8 | **CODE** | F,R — the PRG entry `jmp`; relocation 1 points at it |
| `0x000400` | `0x000412` | 18 | **CODE** | F — `cold_start`, jump target of the stub |
| `0x000412` | `0x0004a0` | 142 | **DATA** | B — two ASCII strings (Psygnosis taunt, "Please insert data disk…") |
| `0x0004a0` | `0x008fce` | 35630 | **CODE** | F,I — the bulk of the engine. I: 16.3 rts/kW, 781 `bsr`, 942 `lea` over `$400..$1009a`. Contains interleaved word-sized variables and small tables in the holes between routines (`$712`/`$714` flip flags, `$74a` screen pointers, `$876..$8cf` input state, `$64f0..$6526` floppy state), and at `$82f8`..`$8dfe` the **background scroll blitter** — a 16-entry jump table, three scroll variables and 16 unrolled copy routines that nothing reaches statically (see below) |
| `0x008fce` | `0x00989c` | 2254 | **CODE** | F,I,R — **reclassified, see below.** 12 masked planar sprite blitters behind the three jump tables at `$989c`/`$98ac`/`$98bc`; 16 `rts` and 8 `dbf` in 1127 words |
| `0x00989c` | `0x00a271` | 2517 | **DATA** | I,B — the three 4-longword jump tables then word-pair parameter data; 88.3% zero, 0 `rts`/`bsr`/`jsr`/`movem`/`dbf` |
| `0x00a271` | `0x00b346` | 4309 | **DATA** | B — 55.9% printable ASCII; the in-game dialogue/shop strings, each with a one-byte layout prefix |
| `0x00b346` | `0x00c030` | 3306 | **CODE** | F,I — includes the score→max-vitality ladder at `$b762`..`$b7c4` (`cmp.l #$400000/$300000/$200000/$100000/$30000,d7` → `$b6f8`) |
| `0x00c030` | `0x00d93a` | 6410 | **DATA** | B — **100.0 %** zero (not 92.6 %; recounted); uninitialised state written at run time (`$c030` message id, `$c034` message timer, `$bd66/$bd68/$bd6a/$bbbe/$bbc0/$bbc2/$bbc6/$b6f8/$b6fa` player state) |
| `0x00d93a` | `0x00ed2a` | 5104 | **CODE** | F,I — includes the effect dispatcher at `$ddec`/`$de62`, and at `$ecba`..`$ed29` the Copylock's pointer table, entry stub and register save area (the blob straddles this boundary) |
| `0x00ed2a` | `0x00f576` | 2124 | **CODE (encrypted)** | F,R — **the Copylock body**, see §2.5. Plaintext at each end (`$ed46`..`$ed8c` sets the trap up, `$ee02`..`$ee66` is the decryptor, `$f542`..`$f574` is the restore + key check); `$ed8e`..`$f540` is ciphertext that only ever exists as plaintext one longword at a time |
| `0x00f576` | `0x00f89e` | 808 | **DATA** | B,R — **four 201-byte scanline-order tables**, each a permutation of 0..199 terminated by `$ff`, addressed through the 4-longword pointer table at `$ecba`; then the two words `$f89a`/`$f89c`. This block is the entire reason the region measured entropy 7.73 |
| `0x00f89e` | `0x01009a` | 2044 | **CODE** | F,I |
| `0x01009a` | `0x010200` | 358 | **DATA** | B — word pairs, a parameter table |
| `0x010200` | `0x0103ee` | 494 | **CODE** | R,B — six `move.w #imm,$xxxx / rts` stubs plus the 23 handlers of `effect_handler_table`. **Reached only through pointer tables, which is why Ghidra never created them.** Now defined via `names.txt` |
| `0x0103ee` | `0x017adc` | 30446 | **DATA** | I,B — 0 `bsr`, 0 `movem`, 0 `dbf` over 15649 words; byte pattern `00 00 00 00 00 00 ff ff` repeated = 4 bitplanes + a mask plane. Sprite/tile bitmaps and level tables |
| `0x017adc` | `0x018352` | 2166 | **CODE** | F,R — the sound module: a run of `movem` entry stubs at `$17adc`..`$17b39` (six of 14 bytes, one of 10, and three different register sets) then the YM2149 replay routine. Entirely PC-relative (`lea $xxxx(pc),a3`) |
| `0x018352` | `0x01a48a` | 8504 | **DATA** | I — 0 rts/bsr/jsr/movem/dbf over 4252 words; music/instrument data for the module above |
| `0x01a48a` | `0x01ab04` | 1658 | **CODE** | F,R — sound module tail; `$1a48a` is the effect entry reached via `snd_stub_00+56` |
| `0x01ab04` | `0x01d43d` | 10553 | **DATA** | I,B — 0 rts/bsr/jsr in 13930 words across the whole `$1ab04..$217d8` span; starts with a word pointer table, then bitmap data |
| `0x01d43d` | `0x021040` | 15363 | **DATA** | B,R — a single 15,363-byte zero run, and `$f8a4` does `lea $1d43e.l,a6`: reserved run-time working storage carried in the image |
| `0x021040` | `0x02143e` | 1022 | **DATA** | B — `ff ff xx xx` quads = mask+data pairs, a small 2-plane bitmap/font block |
| `0x02143e` | `0x0216be` | 640 | **DATA** | R — `resource_file_table`, 40 × 16 bytes, read by `load_resource_by_index` |
| `0x0216be` | `0x0216c0` | 2 | **DATA** | R — `level_seq_index` |
| `0x0216c0` | `0x0217d8` | 280 | **DATA** | R — `level_seq_table`, 8 bytes × **35 entries** — exactly the number of `OVALAY*` files in `resource_file_table` |
| `0x0217d8` | `0x021808` | 48 | **CODE** | F,R — the bootstrap stub (address fictional, see §0) |
| `0x021808` | `0x0218d0` | 200 | **DATA** | B — zero pad to the end of text |

**Totals: 54,854 bytes CODE (40.2 %), 81,554 bytes DATA (59.8 %),
0 bytes UNKNOWN.** The table tiles `$3F8`…`$218D0` with no holes and
no overlaps, summing to 136,408 (checked programmatically).

### The classification method has false positives in BOTH directions

Two of the rows above were wrong, and they were wrong in opposite ways. Both
failures come from trusting one signal.

* **`$8fce..$989c` was called DATA because it has 0 `bsr` and 0 `movem`.** It is
  code — 12 leaf blit routines. Leaf code entered *only through a pointer table*
  calls nothing and saves nothing, so `bsr`/`movem` density reads zero by
  construction. The signal that was right all along was `rts`: 16 in 1127 words
  = 14.2/kW, squarely in the CODE band. **The region that got misclassified is
  precisely the one the method is blind to.**
* **The same trap caught this project a SECOND time, inside a row already
  classified CODE.** `$83b6..$8dfe` sits in the `$4a0..$8fce` "bulk of the
  engine" row, so the region table was never wrong about it — but Ghidra put
  none of those 2,632 bytes in a function, because the only way in is
  `movea.l (0,a2,d1.w),a2 / jmp (a2)` through the 16-entry longword table at
  `$8366`. They are the background scroll blitter: 16 unrolled variants of a
  30-longword-per-scanline copy, one per 16-pixel horizontal scroll offset,
  tiling `$83b6..$8dfe` exactly. Named in `../names.txt` as `bg_scroll_blit` +
  `bg_scroll_copy_x0..x15`; found by auditing the coverage gap in
  `../recreate/PORTABILITY.md` §8.1. **A correct CODE verdict is not coverage** —
  ask separately whether anything reaches each part of the region.
* **`$a271..$b346` (the dialogue text) scores 78 `bsr`.** `$61xx` is `'a'`
  followed by any byte, and the block is 56 % ASCII. Judged on `bsr` alone it
  would be the densest "code" in the program.
* **`$103ee..$17adc` (the graphics) scores 14 `rts`, 2 `bsr`, 2 `jsr`.** In
  15,223 words that is 0.9 rts/kW, which is why it *is* correctly DATA — but the
  absolute counts are non-zero, so a threshold on counts rather than density
  would have flipped it.
* **Entropy says nothing about packing on its own** — see the UNKNOWN row's
  post-mortem in §2.5.

The working rule: classify on `rts` **density** (per 1000 words), cross-check
against Ghidra's function coverage *including functions that start outside the
region*, and always ask "could this be reached only through a pointer table?"

### What is honestly still soft in that table

* The **CODE/DATA split is solid; the sub-classification of the DATA is not.**
  I have shown `$103ee..$17adc` and `$1ab04..$1d43d` are not code (no `bsr`, no
  `movem`, no `dbf` in ~30k words) and that they look like planar bitmaps, but I
  have not decoded a single sprite. "graphics/tiles/level tables" is a category
  claim, not a verified layout.
* Inside the CODE regions the boundaries between routines and the
  variables sitting in the holes between them are **not** individually
  classified. Ghidra now covers 252 functions / 25,696 bytes there — **46.8 % of
  the 54,854 CODE bytes**. Of the 29,158 bytes it does not cover, 6,174 are
  disassembled but sit in no function and 22,984, in 65 gaps, carry no
  disassembly at all; a density screen puts roughly 16,800 of the latter
  code-like against 6,200 data-like. Separating them is Stage 2 work, and
  `../recreate/PORTABILITY.md` §8.1 measures it gap by gap (the largest,
  `$3e2c..$501a`, is 96 bytes of word table then plain engine code from `$3e8c`).
* `$ed8e..$f540` is CODE that **cannot be read at all** — see §2.5. Its size is
  known, its contents are not, and no static scan of this program (for
  addresses, traps, hardware registers or OS calls) covers those 2,000 bytes.

---

## 2. ANCHOR INVENTORY

### 2.1 OS traps — reconciled with the orchestrator's independent scan

Byte-scanned the **relocated** text at **every** alignment for all 16 `4e4x`
opcode words (never off the linear listing — see `docs/m68k-disassembly.md`).

| trap | raw hits | word-aligned | real instructions |
|---|---:|---:|---:|
| `#1` GEMDOS `4e41` | 3 | 1 | **1** |
| `#4` `4e44` | 3 | 0 | 0 |
| `#5` `4e45` | 1 | 0 | 0 |
| `#7` `4e47` | 3 | 1 | 0 |
| `#9` `4e49` | 3 | 3 | 0 |
| `#10` `4e4a` | 2 | 0 | 0 |
| `#13` BIOS `4e4d` | 0 | 0 | 0 |
| `#14` XBIOS `4e4e` | 5 | 0 | 0 |
| `#15` `4e4f` | 1 | 0 | 0 |
| **total** | **21** | **5** | **1** |

**The orchestrator's parity reasoning is correct, and the conclusion it seemed
too strong for is the right one.** Resolution, hit by hit:

* The 16 **odd-aligned** hits cannot be instructions — the 68000 fetches on word
  boundaries and an odd PC is an address error. They are byte pairs straddling
  data or an instruction's operand.
* Four hits are **word-aligned but still not instructions**: `$a802`, `$a88a`,
  `$aa60` (`trap #9`) and `$b1a4`-region (`trap #7`). All four fall inside
  `0xa271..0xb346`, the dialogue text block; `4e49` = `"NI"` and `4e47` = `"NG"`.
  This is the exact failure mode `docs/m68k-disassembly.md` records for Joust
  (`"CONGRATULATIONS!"`), and the reason it insists every hit be classified by
  reading its bytes rather than by which trap number looks plausible.
* The single surviving instruction is **`trap #1` at `$217e2`**, inside
  `startup_relocate_and_run`, selector `$20` = **`Super()`**, preceded by the
  `3f3c 0020` selector immediate the census rule demands.

> **SWB.PRG makes exactly one OS call in its entire life: `Super()`.
> Zero BIOS, zero XBIOS, zero GEMDOS file I/O. No `Malloc` (`3f3c 0048`),
> no `Mshrink` (`3f3c 004a`) — 0 byte-scan hits for either.**

`gemdos_super` in the old 57-function decompilation was the trap annotator
naming that one site; it is the same function, at `0x313e0` in the old base and
`$217d8` in the correct one. There was never a second OS path to find.

### 2.2 How the game reaches the disk instead — raw FDC, confirmed

The orchestrator's hypothesis was right, and it is not an inference: the
decompiled bodies are in `decomp.c` and named in `names.txt`.

**A complete WD1772 + DMA driver at `$5e3e..$64f0`** (code) plus its state block
at `$64f0..$6528`. The earlier note said `$6118..$64f0`; that is the *track-read
core* only. `disk_check_signature` (`$5e3e`), `disk_load_file` (`$5e7c`) and the
FAT helpers `$5f06`, `$5f76`, `$5fc4`, `$604a`, `$6068`, `$6092`, `$60da` all sit
*below* `$6118`, and `fdc_restore` (`$6408`) calls `$645e`/`$646c`/`$64ea`
*above* it. `rad_depack` ends at `$5e3a`, immediately below the driver.

**BATCH 44 PHASE B — THIS WHOLE REGION IS NOW A DECLARED BOUNDARY, AND `disk_load_file` IS ITS SEAM.**
`$5e7c` is the lowest routine here whose INPUTS are file-shaped: a0 on a twelve-character DOS name,
a1 on a destination, 0 or negative back. Everything it reaches is sector-shaped, and the
reconstruction does not port any of it — `load_resource_by_index` calls the kit's `disk_read_file`
across the cut instead (TRAP_MODEL.md Phase 9), which is the same file's bytes at the same address
through GEMDOS rather than through the controller. The boundary's edges are ENUMERATED and machine-
checked in `recreate/test/test_boot_inventory.py`: the boot chain crosses in exactly once (`$e79c`),
the whole image encodes four edges in (the seam; the vblank handler's `jsr $6268.l` at `$73e` when
`floppy_idle_timer` expires; the Copylock's failure arm; and one operand fragment that is not an
instruction), and the band transfers OUT nowhere at all — it is a closed subgraph that leaves by
`rts`. See `recreate/STATUS.md` batch 44 phase B for the decision and its terms.

**ONE CORRECTION TO THE EXTENTS ABOVE.** This section says the driver's code runs to `$64f0`, and
`floppy_deselect_drives` (`$6268`) is inside it — but that routine is NOT part of the 1,644 unported
bytes the boundary excludes, because the boot chain never reaches it and the figure is summed over
the boot walk's own segments. It has been reconstructed since batch 42 phase B, called from the
vblank handler. Two counts, both right about different questions.

| register | hits | where |
|---|---:|---|
| `$ffff8604` FDC data/access | 2 | `$6464`, `$6472` |
| `$ffff8606` DMA mode/status | 29 | all within `$6150..$6498` |
| `$ffff8609` DMA addr 16–23 | 4 | `$6130`, `$627c`, `$62b2`, `$6316` |
| `$ffff860b` DMA addr 8–15 | 4 | `$6138`, `$6284`, `$62aa`, `$631e` |
| `$ffff860d` DMA addr 0–7 | 4 | `$6140`, `$628c`, `$62a2`, `$6326` |
| `$fffffa01` MFP GPIP bit 5 (FDC done) | 3 | `$62de`, `$6340`, `$6426` |
| `$ffff8800/8802` PSG port A (drive/side select) | 3 | `$6250`, `$6256`, `$6262` |

`$ffff8606` is written with `$80`/`$84`/`$86`/`$90` — the DMA-mode register
selects, i.e. FDC command/status, track, sector, and the sector-count register.
`$fffffa01` bit 5 is polled with a 600,000-iteration timeout. Drive and side are
selected by a read-modify-write of PSG register 14.

**And a FAT12 filesystem on top of it**, which is the answer to "either GEMDOS or
raw FDC" — it is raw FDC *for the filesystem too*:

* `fat_find_dir_entry` (`$61b8`) scans the loaded root directory at **stride 32**
  and compares `name[0..7]` vs `entry[0..7]` and `name[9..11]` vs `entry[8..10]`
  — skipping the `.` at index 8 of the search key, which is exactly why
  `resource_file_table` stores `"SPRITES .CRU"` space-padded.
* `disk_load_file` (`$5e7c`) caches `dir[26]` (first cluster) and `dir[28]`
  (file size) — the standard FAT12 directory-entry offsets.
* `fat_calc_data_start` (`$5f06`) decodes **four** BPB fields, not two: offset
  `0x10` (number of FATs) × offsets `0x16/0x17` (sectors per FAT), ×512, into
  `$650e`/`$650c`; offsets **`0x18/0x19`** (sectors per track) into `$651a`; and
  offsets **`0x11/0x12`** (root directory entries) into `fat_dir_entry_count`
  (`$6518`), shifted right by 4 into `$6512` (root-dir sectors = entries/16).

So the `OVALAY*/TILEDATA/SPRITES` files are found through the real FAT12
directory, but every sector of it is fetched by programming the controller.

**How the track read is programmed** (`$6118`, and this is what a device model
has to reproduce):

* `$6120` computes the DMA end bound as `(11 − sector) × 512` added to the DMA
  address counter read back out of `$ffff8609/860b/860d`, and stores it at
  `fdc_dma_end_track` (`$6508`).
* `$6164` writes a **sector count of 13** to the DMA sector-count register
  (`$ffff8606 := $90`) and then FDC command **`$90` = Read Sector with `m=1`
  (multiple record)**, so one command streams the whole track;
  `fdc_wait_irq_bounded` aborts it when the DMA counter reaches the bound.

That is **10 data sectors per track in one multi-record command** — exactly the
shape of a disk whose sector IDs 11 and 12 are the extra protection sectors.

**`$6408` is *not* the protection check.** It is `move.w #5,d1` → WD1772 Type I
**Restore with verify** (seek track 0), `$493e0` = 300,000-iteration timeout,
status read back through `fdc_read_data_reg`, error code −5. It is now named
`fdc_restore`. Ghidra's
`/* WARNING: Instruction at 0x6436 overlaps instruction at 0x6434 */` is a decode
artefact of the `bsr.w` displacement word at `$6436` — **not** self-modifying
code. `$6408` is called by `disk_check_signature`, by `disk_load_file` twice, and
by the Copylock's failure path at `$f56a`.

**The protection check is at `$ecca`, and it is a Rob Northen Copylock — see
§2.5.** That section replaces this one's "I did not find it".

**KNOWINGLY UNPINNED (record this in `recreate/STATUS.md` when the harness
exists):** the fuzzy bytes on the protection sectors are *deliberately unstable* —
they read back differently on each revolution, which is the entire mechanism. So
any reconstruction of the check is impossible to pin with a deterministic
differential. **And it is worse than non-determinism:** the code that performs the
check lives inside the Copylock's encrypted body, so it cannot even be *read*
statically to know what it compares. Both halves of the exclusion must be recorded
— this is not merely "the oracle has no stable expected value", it is "there is no
source text to port". Same class of exclusion as Joust's raw-floppy routine, one
notch harder.

### 2.3 Other hardware registers

> **Superseded as a census by [`recreate/PORTABILITY.md`](../recreate/PORTABILITY.md) §2**, which
> counts the same registers out of Ghidra's reference model instead of a longword byte scan. Three
> differences worth carrying back here: (a) the scan's `abs.w` caveat below is real and costs 3
> sites; (b) it is also blind to **register-indirect** access, which is 18 more sites — the
> 8-longword palette clear in `clear_palette`, the 8-longword `set_palette`, and the IKBD ACIA pair
> reached through `lea $fc00.w,a1`; (c) the table below was built from a Ghidra DB whose loader
> mis-applied 536 spurious relocations (see PORTABILITY.md's banner), which is why nothing in it
> should be trusted to the last site. The totals that replace it, **counted as ACCESS RECORDS the
> way PORTABILITY.md §2's census counts them**: PSG 35 (3 read), shifter 34 (4 read), FDC/DMA 32
> (10 read), MFP 20 (10 read), ACIA 5 (4 read) = **126 records, 31 reads**. Those come from **120
> instructions**: a read-modify-write (`bclr #6,$fffa11`, six of them here) is one instruction and
> two accesses to the oracle — a read it answers 0 and a write it drops — so it is counted twice.
> Quote whichever number you mean and say which. "No blitter, no STE" survives the recount.

Scanned the whole relocated image for `$00ff8xxx`/`$ffff8xxx`/`$fffffaxx`/
`$fffffcxx` longwords, then filtered to word-aligned sites inside code regions.
**Caveat: this scan is blind to `abs.w` addressing** — `$fffffc00` reachable as
the extension word `fc00`, `$ffff8240` as `8240`. `ikbd_disable_mouse` uses
exactly that (`lea $fc00.w,a1`), so the IKBD counts below are a lower bound.

| register | role | sites |
|---|---|---|
| `$ffff8201/8203` | screen base high/mid | `$6bc`,`$6c6` (`flip_screen`), `$e49c`,`$e4a4`, `$f910`,`$f918` |
| `$ffff8207/8209` | video address counter (read) | `$51b8`, `$51b0`, `$6912` — `$6912` XORs it into a PRNG |
| `$ffff820a` | sync mode (50/60 Hz) | `$f920` (`:= 2`, PAL), `$17c94` (sound module) |
| `$ffff8240`–`$ffff825e` | 16 palette registers | `$6fc`,`$704`,`$e7aa`,`$e7e6`,`$e7f6`,`$f946`,`$e5a6`,`$408` |
| `$ffff8260` | resolution | `$f908` (`:= 0`, low res) |
| `$ffff8604`–`$ffff860d` | FDC/DMA | §2.2 |
| `$ffff8800/8802` | YM2149 | `$6250`–`$6262` (drive select), `$f1c6`, `$17e46`–`$17f5a` (music) |
| `$fffffa01` | MFP GPIP | `$62de`,`$6340`,`$6426` (FDC done), `$f212`,`$f264`,`$17c82` |
| `$fffffa07/fa13` | MFP IERA / IMRA | `$e4fa`, `$e502` — both written `0` at boot: **timers A and B are disabled** |
| `$fffffa09/fa15` | MFP IERB / IMRB | `$f8da`, `$f8e2` — both `:= $40`, bit 6 = ACIA |
| `$fffffa11` | MFP ISRB | `$768`,`$780`,`$832`,`$846`,`$864` — `bclr #6` at the end of every ACIA handler |
| `$fffffc00/fc02` | IKBD ACIA status/data | `$f8f4` (`abs.w`), `$756`, `$83c`, `$85a` |

There is **no blitter use** (`$ffff8a00`–`$ffff8a3c` never written; the two
`$ff8a05` byte-scan hits are odd-aligned data) and **no STE hardware**
(`$ffff8900`+ absent). This is a plain-ST 512 KB, CPU-only, low-resolution game.

> **Every table in §2.3 is a statement about the *statically visible* image, and
> ~2,000 bytes of this program are not statically visible.** The Copylock body
> (`$ed8e..$f540`) is ciphertext; no scan for hardware registers, traps, addresses
> or OS calls reaches inside it. "No blitter, no STE, no XBIOS" is therefore a
> claim about 98.5 % of the image, not 100 %.

**The vector list is also incomplete.** Above, the program "installs `$70` and
`$118`". The Copylock additionally writes three more, all of them at run time and
none of them visible to a scan of the boot path:

| vector | what | where |
|---|---|---|
| `$10` | illegal instruction | `$ed62` (temporary, for the anti-trace probe) and `$ed80` (the real decryptor) |
| `$20` | privilege violation | `$ee14` → `copylock_key_check` (`$f552`) |
| `$24` | trace | `$ee0a` → the re-encrypt handler (`$ee3c`) |

A harness that models only `$70`/`$118` will silently lose control the first time
the Copylock runs.

### 2.4 Strings and what references them

| addr | string | referenced by |
|---|---|---|
| `$412` | "If you keep running out, you soon run out of places to run!  Psygnosis!!   And so do I!!!!!!" | **nothing** — inert filler in the hole after `cold_start` |
| `$46e` | `1b 59 2b 20` = VT52 `ESC Y` + row/col, then at **`$472`** "Please insert data disk and press a key.", NUL at `$49a` | **nothing** — see below |
| `$8a0` | "Wheres Saigon??????", NUL at `$8b3` | **nothing** |
| `$8b4` | "I Dunno Im not Psychic!!!!!", NUL at `$8cf` | **nothing** |
| `$a271..$b346` | ~90 dialogue/shop/hint strings, each with a one-byte layout prefix (`'<'`, `'2'`) | the dialogue engine; I did **not** trace the indexer |
| `$2143e..$216be` | the 40 8.3 filenames | `load_resource_by_index` (`$e792`, the only reference) |

Three corrections to the earlier version of this table:

* **The data-disk string starts at `$46e`, not `$46f`.** `$46e/$46f` are the two
  bytes of a VT52 `ESC Y` cursor-position sequence and `$46f` is just the `'Y'`;
  the text proper begins at `$472`.
* **`$8b4` is "I Dunno Im not Psychic!!!!!", not "Wheres Saigon??????"** — that one
  starts at `$8a0`. The old label was 20 bytes off.
* **"`$46f` rendered by the `show_data_disk_prompt` path" is REFUTED.** A scan of
  every `abs.l`, `abs.w` and pc-relative-`d16` operand in the image found **zero**
  references to `$412`, `$46e`, `$46f`, `$472`, `$8a0` or `$8b4`.
  `show_data_disk_prompt` displays the **bitmap** `DATADISK.RAD` (loaded to
  `$49800`, depacked to `$77f80`, palette from `$77f84`). The VT52 prefix is the
  tell: it was written for GEMDOS `Cconws`, and this program makes no GEMDOS call
  but `Super()`. All four strings are Cconws-era leftovers, inert exactly like the
  Psygnosis taunt.

One nuance worth keeping: "zero references" is decisive for the four filler
strings, but **not** for `$a271` — that block is certainly indexed through a
table, so a computed address would be invisible to the same scan.

And one trap in the opposite direction: the NUL terminators at **`$8b3` and
`$8cf` are live variables** (`joy1_prev` and `joy1_current`, the two-frame
joystick pipeline that `$682` diffs to get a rising-edge mask). The filler text is
dead; two bytes sitting inside it are not.

---

## 2.5 THE HEADLINE FOR STAGE 2: `$ed2a..$f89e` is a Rob Northen Copylock

The earlier pass left `$ed2a..$f89e` as **UNKNOWN**, "entropy 7.73, near-random,
i.e. packed or compressed". That was wrong twice over. There is nothing packed in
it, and it is not inert: it is a **trace-decrypting copy-protection blob, and it
is live on the boot path.**

### It runs on the very first resource load

```
$e51e   move.w #$ffff,$e7cc          ; ARM  (immediately before the TITLESCR.RAD load)
$e6dc   move.w #$ffff,$e7cc          ; ARM  (immediately before the SPRITES.CRU load)

load_resource_by_index ($e782):
$e7b2   tst.w  $e7cc
$e7b8   beq.w  $e7c8                 ; not armed -> skip
$e7bc   jsr    $ecca.l               ; <-- THE COPY PROTECTION
$e7c2   clr.w  $e7cc
```

Two of the seven load sites arm it, and the first of those is the boot's first
disk access. **This is not an optional side path.**

### The mechanism, read from the plaintext ends

```
$ecca   moveq #0,d0 / move.l #$ffffffff,d1 / bra.s $ed46
$ecd4   96 bytes of zeroed save area (d0-a7, then vectors $8..$27)
$ed3e   8 bytes: the decrypt cursor  [addr, original ciphertext]

$ed46   move.l a6,-(a7)
        lea    $ecd4(pc),a6          ; pc - $76
        movem.l d0-a7,(a6)           ; save every register
        lea    64(a6),a6
        move.l (a7)+,-8(a6)          ; patch the saved a6 slot
        move.l $10.l,d0              ; keep the old illegal-instruction vector
        pea    $ed6a(pc)
        move.l (a7)+,$10.l           ; point $10 at the NEXT instruction
        illegal                      ; ...and take the exception. Pure anti-trace.
$ed6a   move.l d0,$10.l              ; restore it
        movem.l $8.l,d0-d7 / movem.l d0-d7,(a6)   ; save vectors $8..$27
        lea    $ee02(pc),a0 / move.l a0,$10.l     ; install the DECRYPTOR
        lea    $ed3e(pc),a0 / move.l a0,(a0)
        illegal                      ; second trap -> $ee02, and from here on
$ed8e   <<< ciphertext >>>           ; every instruction is decrypted one step
                                     ; ahead of the PC and re-encrypted behind it
```

`$ee02` is the decryptor, and it is the whole proof:

```
$ee02   movem.l d0/a0/a1,-(a7)
        lea $ee3c(pc),a0 / move.l a0,$24.l    ; TRACE vector
        lea $f552(pc),a0 / move.l a0,$20.l    ; PRIVILEGE VIOLATION vector
        addi.l #2,14(a7)                      ; step the frame's PC past `illegal`
        ori.b  #7,12(a7)                      ; force IPL7 in the frame's SR
        bchg   #7,12(a7)                      ; flip the frame's TRACE bit
        ...
$ee58   move.l -4(a0),d0 / not.l d0 / swap d0 / eor.l d0,(a0)
$ee66   rte
```

`move.l -4(a0),d0 / not.l d0 / swap d0 / eor.l d0,(a0)` is **single-step XOR
decryption of the instruction stream**, keyed on the previous (already executed)
longword. The trace handler at `$ee3c` does the mirror-image re-encrypt first, so
at most one instruction is ever plaintext in memory. This is the canonical Rob
Northen Copylock structure.

The tail is plaintext again and confirms the alignment is real, not a coincidence:

```
$f542   movem.l d0-d7,$8.l           ; restore vectors $8..$27
$f54a   movem.l $ecd4(pc),d0-a6      ; restore the entry registers
$f550   rte
$f552   cmp.l #$b472043f,d0 / beq.s $f562
$f55a   cmp.l #$8f25c241,d0 / bne.s $f564
$f562   rts                          ; either key accepted
$f564   jsr $e782.l / jsr $6408.w / jsr $6f9e.w / jmp $6bb8.w      ; failure
```

Two accepted 32-bit key values; anything else diverts. **`$f564` is also the answer
to the memory map's "seventh call site of `load_resource_by_index`, index and
destination not determined"** — it is the failure path, and its `d0`/`a1` are set
up inside the ciphertext, so they are unreadable by construction.

### Three things in the image are reachable only from inside the ciphertext

Scanned for `abs.l`, `abs.w` and pc-relative-`d16` operands, and for every
`jsr`/`jmp`/`bsr`/`bra` target:

| thing | status |
|---|---|
| `copylock_table_ptrs` (`$ecba`) and the four wipe tables it points at | **no plaintext reference at all** |
| `disk_check_signature` (`$5e3e`) — checks boot-sector+2 against `$face` | **no plaintext caller at all** |
| `$f89a` / `$f89c` | written by plaintext (`$fb8a`), read by **nothing** plaintext |

That is consistent with the usual Copylock deployment: the encrypted body is not
just a check, it holds **real game code**, so the protection cannot be no-op'd
out. Treat that as strongly suggestive rather than proven — the alternative
(all three are dead) is not excluded by a static scan.

### The post-mortem: entropy never said "packed"

`$f576..$f89e` measures **7.65 bits/byte** — and it is four plaintext lookup
tables, each a **permutation of 0..199** (200 scanlines) terminated by `$ff`:

| table | order |
|---|---|
| `$f576` | 0,2,4,…,198 then 199,197,…,1 — even lines top-down, odd lines bottom-up |
| `$f63f` | 0,199,2,197,… — top and bottom converging |
| `$f708` | every 4th line, four passes |
| `$f7d1` | 0,50,100,150, 2,52,102,152, … — four interleaved bands |

A permutation is **maximally entropic by construction**: every byte value occurs
exactly once, which is the definition of a flat histogram. "Entropy 7.73 ⇒ packed"
was never a valid inference, and here it cost a whole region. Shannon entropy
answers "is the byte histogram flat?", which a permutation table, a palette ramp,
a pixel-shift table and a compressed stream all answer "yes" to.

Two secondary corrections while we are here:

* **"Ghidra created no function in the region" was false.** `FUN_0000ecca` exists
  and its body reaches to about `$ed8e`, i.e. *inside* the region. The previous
  pass enumerated functions by **start** address and this one starts at `$ecca`,
  36 bytes below the region boundary. Filter by body, not by entry.
* The region was reported as holding "12 `rts`, 12 `bsr`, 4 `jsr`, 3 `movem`" —
  those counts are over ciphertext and mean nothing.

### >>> CONSEQUENCE FOR THE HARNESS — read this before writing one <<<

**A differential harness will hit `jsr $ecca` on the very first resource load of
the boot.** It has exactly two options:

1. **Model it.** That means a CPU with working `illegal` (vector `$10`), `trace`
   (`$24`) and `privilege violation` (`$20`) exceptions, an exception frame whose
   SR and PC the handler can *edit on the stack*, and correct T-bit semantics —
   because the blob decrypts itself by single-stepping. Musashi can do this in
   principle; **the kit's build of it cannot**, because `tools/recreate_kit/kit.mk`
   sets `-DM68K_EMULATE_TRACE=0` — a stated modelling decision
   (`tools/recreate_kit/TRAP_MODEL.md`), and one the Copylock stub's witness
   depends on: a trace decryptor that ran to completion would cover its own
   tracks. Run
   unstubbed under the oracle, the blob gets as far as installing its decryptor
   at `$ee02`, and then the trace exception it depends on never fires: past the
   second `illegal` the CPU executes ciphertext as if it were instructions and
   the run never returns (measured — `recreate/test/test_copylock.py`).
2. **Stub it out.** Force `copylock_arm_flag` (`$e7cc`) to 0, or make `$ecca` an
   immediate `rts`. Cheap, and it is the right call for porting the *game*.
   **This is built**: `recreate/test/copylock.py` offers both, defaults to
   applying both, and refuses any run whose memory shows the protection ran.
   The two are not interchangeable — the flag poke is undone by `$e51e`/`$e6dc`,
   so only the `rts` survives the boot path. `recreate/PORTABILITY.md` §6 has
   what the stub is worth and what it costs.

Either way, record in `recreate/STATUS.md` that the fuzzy-byte check is
**structurally unpinnable** — not merely because fuzzy bytes are
non-deterministic, but because **the code performing the check cannot be read
statically at all.** There is no source text to reconstruct, so "unverified" here
is a permanent state, not a to-do.

---

## 3. THE MEMORY MAP — and the `image_size` bound

**Every address is established from an instruction I read, not inferred.**

| range | size | what | evidence |
|---|---:|---|---|
| `$000`–`$400` | 1 KB | 68000 exception vectors. The game installs `$70` (autovector 4 = VBL) and `$118` (MFP ch. 6 = ACIA), and re-vectors `$118` per-interrupt for joystick reports | `move.l #$716,$70.w` at `$f8c6`; `move.l #$754,$118.w` at `$f8ce` |
| `$400`–`$217D8` | 136,152 | **the program itself** (code + data + in-image zero-filled state) | the bootstrap copy loop, §0 |
| `$217D8`– | — | **the depacked level overlay**, immediately after the program. (The overlay is loaded raw to `$49800` at `$e5fa`, then depacked here.) | `lea $49800,a0 / lea $217d8,a1 / jsr rad_depack` at `$e638` |
| `$24898` | 3200 | **saved and restored around every overlay depack** — not just "the source of a copy". See below | `$e624`, `$e648`, `$e87c` |
| `$25298` | — | **`SPRITES.CRU` load address** (raw, never depacked; body base `$252d8` = +64) | `lea $25298,a1 / move.l #$26,d0 / bsr load_resource_by_index` at `$e6d0` |
| `$44000`–`$70000` | 163,840 | **8 scroll/tile buffers of `$5800` each**: `$44000 $49800 $4f000 $54800 $5a000 $5f800 $65000 $6a800`. Line pitch is `$100`. `$82a6..$82e2` is **8 pairs** of longwords, one pair per buffer — see below | `$fba4`–`$fc43`, then `$7642`–`$7691` |
| `$44000` | — | **`TILEDATA.RAD` load address**, and it **is** depacked: to `$4f000` | `move.l #$25,d0 / lea $44000,a1 / jsr load_resource_by_index` at `$e662`, then `lea $44000,a0 / lea $4f000,a1 / jsr rad_depack` at `$e66e`–`$e67a` |
| `$49800` | — | **staging buffer for every other file** (title, credits, overlays, data-disk screen) — loaded raw here, then depacked elsewhere | four call sites, table below |
| `$6FF80`, `$77F80` | — | depack destinations, 128 bytes below each screen: a header (palette at +4) followed by the 32000-byte bitmap | `lea $49800,a0 / lea $6ff80,a1 / jsr rad_depack` at `$e530`; same with `$77f80` at `$e578`; `set_palette($77f84)` at `$e4ca` |
| `$70000`–`$77D00` | 32,000 | **screen buffer B** | `move.b #$07,$ff8201 / move.b #$00,$ff8203` at `$f90c`; `$750` initialised to `$070000` |
| `$78000`–`$7FD00` | 32,000 | **screen buffer A** | `move.b #$07,$ff8201 / move.b #$80,$ff8203` at `$e498`; `$74c` initialised to `$078000` |
| `$7FD00`–`$80000` | 768 | **supervisor stack**, growing down from `$80000` | `movea.l #$80000,a7` at `$f8c0` |

### `$24898` — a save/restore pair straddling the overlay depack

The earlier note recorded the symptom and missed the mechanism. Reading
`$e624..$e65c` end to end:

```
$e624   move.w #$31f,d0 / lea $24898,a0 / lea $5f800,a1 / bsr copy_longs   ; SAVE 3200 B
$e638   lea $49800,a0   / lea $217d8,a1 / jsr rad_depack                   ; depack the overlay
$e648   move.w #$31f,d0 / lea $5f800,a0 / lea $24898,a1 / bsr copy_longs   ; RESTORE
```

It is a save/restore *pair*, and it is necessary: every `OVALAY*.RAD` carries an
unpacked size of `$3ce8` = **15,592 bytes** in its header (bytes 4..7 — verified
across all 38 overlay files on disk 2), so the depack at `$217d8` writes up to
`$254c0` and would otherwise destroy the first 3,112 bytes of the sprite image at
`$24898`. `$5f800` is buffer 6 of the scroll pool, used here as scratch.

### `$82a6..$82e2` — two interleaved tables, not one

The earlier note said this block "holds *last line* addresses (`$49700`…`$6ff00`)".
That conflates two different initialisers:

* **`$fba4`** writes all 16 longwords as **pairs**, one pair per buffer:
  `(start, start + $4F00)` — `$44000/$48f00`, `$49800/$4e700`, `$4f000/$53f00`,
  `$54800/$59700`, `$5a000/$5ef00`, `$5f800/$64700`, `$65000/$69f00`,
  `$6a800/$6f700`.
* **`$7642`**, guarded by `tst.w $83a8` and after `$83a8 := $ae`, then overwrites
  only the **even** slots (`$82a6, $82ae, $82b6, …, $82de`) with `start + $5700`
  — and `$5700` = `$5800 − $100` = the buffer size minus one line pitch, i.e. the
  buffer's **last line**. Those are the `$49700`…`$6ff00` values.

So the "last line" reading is right for eight of the sixteen longwords, only after
`$7642` has run, and the odd slots hold something else entirely.

### The bound

> ## `image_size` = **`0x80000` (512 KB)**.
> The highest byte the program can touch is **`$7FFFF`** (the first stack push
> writes `$7FFFC..$7FFFF`). The highest byte it *writes as data* is `$7FCFF`.

Four independent instructions pin this and they agree exactly:

1. `movea.l #$80000,a7` (`$f8c0`, `hw_init_vectors`) — the stack is placed at the
   512 KB ceiling.
2. `movea.l #$80000,a7` **again at `$7008`** — `clr.b $7014 / movea.l #$80000,a7 /
   jmp $e494.l`, i.e. the data-disk-prompt path resets the stack to the same
   ceiling. The earlier note missed this one; it is a second, independent witness.
3. `clear_both_screens` (`$f926`): `lea $70000,a0 / move.w #$3f3f,d0 / clr.l (a0)+ / dbf` — `$3f40` longwords = `$FD00` bytes = `$70000..$7FD00`, i.e. the two 32000-byte screens exactly back to back, ending 768 bytes short of `$80000`.
4. A **rigorous** operand scan — immediate and absolute operands only, classified
   by the preceding opcode word, *not* every 2-aligned longword (the naive scan
   reports 6,326 hits in the `$80000..$ff8000` band, essentially all of them
   fragments of unrelated data) — finds **8** real constants at or above `$80000`,
   and **none of them is an address**:

   | value | sites | what it is |
   |---|---|---|
   | `#$927c0` | `$62d0`, `$6308` | 600,000 — the FDC poll timeout |
   | `#$80000` | `$7008`, `$f8c0` | the stack ceiling itself |
   | `cmp.l #$400000/$300000/$200000/$100000,d7` | `$b762`, `$b776`, `$b78a`, `$b79e` | BCD **score thresholds** (4/3/2/1 million) in the ladder that raises `$b6f8`, the maximum vitality, to `$28/$24/$20/$1c` |

   Highest genuinely address-like constant in the whole image: **`$784d8`**, at
   `lea $784d8.l,a2` (`$e81a`). No `abs.l` operand anywhere reaches `$80000`.

The 768 bytes between the top screen and `$80000` are the entire stack. That is
tight but it is the standard TOS layout (on a 512 KB machine `phystop = $80000`
and TOS itself puts the screen at `$78000`), and it means **the harness must not
model less than 512 KB, and does not need more**. The game never queries
`phystop` or the cookie jar; 512 KB is hardcoded.

**Three caveats a harness needs, all of them limits on the above:**

* The bound holds only for **statically visible code**. The Copylock body is
  encrypted (§2.5), so no scan of this program for addresses, traps, blitter or
  STE registers covers `$ed8e..$f540`.
* The vector list in §3's first row is incomplete: the Copylock also writes
  **`$10` (illegal), `$20` (privilege violation) and `$24` (trace)**.
* **Nothing statically bounds the DMA destination.** `load_resource_by_index`
  takes the destination in `a1` and the *length* comes from the FAT directory
  entry at run time, so the highest address the floppy DMA can write is a property
  of the disk, not of the binary.

### Where each file is loaded — the complete call table

`load_resource_by_index` (`$e782`) is the only loader. `d0` = index into
`resource_file_table`, `a1` = destination. All seven call sites:

| call site | index | file | destination | then |
|---|---:|---|---|---|
| `$e4b4` | `$27` = 39 | `DATADISK.RAD` | `$49800` | `rad_depack` → `$77f80`, `set_palette($77f84)` |
| `$e526` | `$00` = 0 | `TITLESCR.RAD` | `$49800` | `rad_depack` → `$6ff80` |
| `$e56e` | `$01` = 1 | `CREDITS.RAD` | `$49800` | `rad_depack` → `$77f80` |
| `$e5fa` | `level_seq[n][0] + 2` | `OVALAY*.RAD` | `$49800` | — |
| `$e668` | `$25` = 37 | `TILEDATA.RAD` | `$44000` | `rad_depack` → `$4f000` |
| `$e6e4` | `$26` = 38 | `SPRITES.CRU` | `$25298` | `sprites_cru_install` |
| `$f564` | **unreadable** | **unreadable** | **unreadable** | the **Copylock failure path** (§2.5). The `jsr` itself is plaintext; the `d0`/`a1` setup is not — it is in the encrypted body. This is a permanent gap, not a to-do |

Note also that `$e51e` and `$e6dc` arm `copylock_arm_flag` immediately before the
`$e526` and `$e6e4` calls, so the TITLESCR and SPRITES loads are the two that run
the protection.

### On the 4 zero bytes per file-table entry

The orchestrator's hypothesis was that they are a run-time-filled slot holding
the load address, which would have made the table itself the memory map.
**They are not.** `load_resource_by_index` computes `resource_file_table +
index*16` and passes that pointer straight to `disk_load_file`, which reads only
the 12-byte name; nothing in the program writes into the table. The destination
is a *parameter in A1* at each call site, as tabulated above. The 4 bytes are
padding that rounds the stride to a power of two so the index can be scaled with
`lsl.l #4`.

### On "is SWB.PRG an engine that pulls CODE overlays off disk 2?"

**No.** The overlays land in `$49800`, which is buffer 1 of the eight
`$5800`-byte scroll/tile buffers — a graphics/level staging area inside the
buffer pool, never executed. There is no `jmp`/`jsr` to any address in
`$44000..$70000` anywhere in the image. The `~50 KB gap` that prompted the
question (`0x1b1ce..0x276f2` in the old 0x10000 base) was an artefact of the
wrong load base, not an overlay landing zone; at the correct base that span is
ordinary in-image graphics data and the sound module. `SWB.PRG` is a
self-contained engine and the `.RAD` files are pure data.

### The level sequence

```
$216be  level_seq_index      word, post-incremented per stage, cleared on restart ($fe4a)
$216c0  level_seq_table      35 entries × 8 bytes
```

Dispatcher at `$e5be`:
```
lea   $216c0,a0
moveq #0,d0
move.w $216be,d0
addq.w #1,$216be
lsl.l #3,d0
lea   (a0,d0.l),a0
moveq #0,d0
move.b (a0),d0            ; entry[0]
addq.b #2,d0              ; skip TITLESCR + CREDITS
move.b 1(a0),$e70c        ; entry[1]
lea   $49800,a1
bsr   load_resource_by_index
tst.b 2(a0)               ; entry[2] -> $e70e := $ffff / 0
...
move.b 3(a0),d0           ; entry[3]
move.w d0,$bd88           ;   -> the stage number
```

All four low fields are verified from the reader:

| field | goes to | consumed by |
|---|---|---|
| `[0]` | `+2` → `resource_file_table` index | `load_resource_by_index` |
| `[1]` | `$e70c` | tested at `$e6c6` to decide whether `SPRITES.CRU` is reloaded |
| `[2]` | `$e70e` (`$ffff`/`0`) | tested at `$e768` |
| `[3]` | `$bd88` — **the stage/round number** | `sprites_cru_install` (`$e87c`): `if ($bd88 > 9) $bd88 -= 6`, then indexes a table at `$e978` with a stride of `$40` bytes per stage |

`[4..7]` are zero in every entry and have no reader I found — **UNVERIFIED**.
The table's 35 entries is exactly the number of `OVALAY*` files in
`resource_file_table`, which is the strongest available cross-check that it is a
complete stage list. Field `[3]`'s observed run `1,2,2,2,3,3,…` therefore groups
several overlays per stage, which is consistent with the `OVALAY5A/5B/5C/5D`
naming on disk.

---

## 4. STARTUP SEQUENCE

```
$3fa   jmp startup_relocate_and_run           ; PRG entry (relocated)
  └─ $217d8  Super($214d8+loadbase)           ; the one and only OS call
             move.w #$2700,sr                 ; supervisor, all interrupts masked
             copy $213d8 bytes: image+8 -> $400
             jmp $400
$400   cold_start
         move.w #$2700,sr
         move.w #$77,$ff825e                  ; palette entry 15
         jmp $e482
$e482  sys_save_tos_stack
         move.l a7,$f8b8                      ; the only recorded route back to TOS
$f8bc  hw_init_vectors
         movea.l #$80000,a7                   ; <-- the 512 KB bound
         move.l #vbl_handler,$70.w            ; autovector 4
         move.l #ikbd_acia_handler,$118.w     ; MFP channel 6
         move.b #$40,$fffa09 / $fffa15        ; IERB/IMRB bit 6 = ACIA
         move.w #$2300,sr                     ; IPL3: VBL and ACIA now get through
         jmp $e48c
$e48c  init_ikbd                              ; 8 bytes, and that is all it is
         bsr ikbd_disable_mouse               ; IKBD cmd $12 via $fffffc02
         bra $e4e6
$e4e6  (boot continuation — Ghidra folds this into show_data_disk_prompt @ $e494,
        because that function falls through into it at $e4e4)
         video_set_lowres_50hz                ; $ff8260:=0, base:=$70000, $ff820a:=2
         clear_palette
         clear_both_screens                   ; $70000..$7FD00
         move.b #0,$fffa07 / $fffa13          ; MFP timers A and B off for good
         move.l #vbl_handler,$70.w
         move.w #$2300,sr
         move.w #$ffff,$e7cc                  ; ARM THE COPYLOCK  (see 2.5)
         load_resource_by_index(0=TITLESCR.RAD -> $49800)   ; ...which runs it
         …
$4a0   game_main_loop                         ; entered by jmp from $f8b4 ONLY ($e708 is dead code:
                                              ;   $e6fc's bsr to $f89e never returns — see cmt 0x4a0)
         do { …; jsr flip_screen } while (1)  ; $508 = bra.s $4a0, no exit
```

From that point the only periodic activity is:
* **`vbl_handler` (`$716`)** — increments `vbl_counter`, calls the music tick
  through `snd_stub_00+14`, and decrements `floppy_idle_timer`, calling
  **`floppy_deselect_drives` (`$6268`)** when it expires. **This is the program's
  only clock:** MFP timers A and B are explicitly masked, so there is no timer
  interrupt at all.
* **`ikbd_acia_handler` (`$754`)** — decodes IKBD bytes. `$FE`/`$FF` are the
  joystick-report headers; it re-points `$118` at a one-shot handler so the
  *next* interrupt captures the data byte into `joy0_state` (`$876`) or
  `joy1_state` (`$877`), then restores itself. Everything else is a key
  scancode, folded into the key bitmap at `$878`.

> A naming trap worth recording: `$877` looks like a "key pressed" flag because
> the boot path spins on it. It is the **joystick-1 report byte**; the spin
> `clr.b $877 / tst.b $877 / bpl.s * / tst.b $877 / bmi.s *` is testing bit 7 =
> **fire**. Naming it from position would have been wrong, which is the failure
> mode `docs/methodology.md` exists to prevent.

> And a second one, in the same 200 bytes: `$878` (`key_bits`) *looks* like the
> live input state — `ikbd_acia_handler` maintains it with `bset`/`bclr`. But the
> 8 scancodes it matches against (`$87a..$881`) are **all zero in the image and
> nothing ever writes them**, and **nothing ever reads `$878`** either (checked
> `abs.l`, `abs.w` and pc-relative). The whole keyboard path is vestigial; the
> game reads `joy1_state` (`$877`) and diffs `$8b3`/`$8cf` for edges. A name can be
> mechanically correct — the handler really does maintain a key bitmap — and still
> mislead about what the program *does*.

> A third: `$6242` was named `floppy_idle_drive` "called from `vbl_handler` when
> the idle timer expires". It writes `d0 = 5 = %101`, and PSG port A bits 1/2 are
> the drive selects **active low** — so that is *drive A SELECTED*, at the start of
> a load. The idle routine is `$6268` (`d0 = 7 = %111`, both deselected), and that
> is the one `vbl_handler` calls. The two had been swapped.

---

## 5. Notes for the other agents

* **`.RAD`/`.CRU` format agent** — the depacker is `rad_depack` at **`$5d62`**
  (`$1596a` in the old base), with `rad_refill_bit_buffer` at `$5e14` and
  `rad_get_bits` at `$5e20`. Your `names.txt` entries were merged and rebased;
  every address you derived matched mine independently, which is a good
  cross-check on the `$3F8` base. `SPRITES.CRU` is loaded **raw** to `$25298`
  and never passed to `rad_depack` — `sprites_cru_install` (`$e87c`) consumes it
  directly, body base `$252d8` = load + 64.
* **Harness agent** — `image_size` is **`0x80000`**, and the program must be
  placed at **`$400`**, not at a GEMDOS load address: model the bootstrap stub's
  copy, or simply load the image body at `$400` directly. The stack starts at
  `$80000`. There are no OS calls to model except `Super()`, so a TOS trap model
  is almost entirely unnecessary — but a **raw FDC/DMA device model is
  mandatory**, because all file I/O goes through `$ffff8604`–`$ffff860d` and
  polls `$fffffa01` bit 5. Specifically: WD1772 command `$05` (Restore, from
  `fdc_restore`), command `$90` (Read Sector, multiple record) with a DMA sector
  count of 13 bounded by software at 10 sectors/track, and the DMA address
  counter must be **readable back** through `$ffff8609/860b/860d` because
  `fdc_wait_irq_bounded` polls it to decide when a transfer is done.
* **Harness agent, the thing that will bite first** — `load_resource_by_index`
  does `jsr $ecca` on the **first** resource load of the boot. That is a
  trace-decrypting Copylock (§2.5): it installs vectors `$10`/`$20`/`$24`, edits
  its own exception frame's SR and PC, and single-steps itself through 2 KB of
  ciphertext. Either run it on a CPU model with faithful `illegal`/`trace`/
  `privilege` semantics, or **stub it**: force `$e7cc` (`copylock_arm_flag`) to 0,
  or make `$ecca` an `rts`. Whichever you choose, record in `STATUS.md` that the
  fuzzy-byte check is unpinnable *because it is unreadable*, not merely because
  it is non-deterministic.
* **Everyone** — the linear listing `out/wonderboy_dis.txt` is now regenerated at
  the correct base and its banner says so. Regenerate with
  `python3 tools/prg_dis.py projects/wonderboy/bin/disk1/AUTO/SWB.PRG --base 0x3f8`.
  A listing produced **without** `--base` is at base 0, i.e. every address in it is
  `runtime − 0x3F8`, and cross-referencing it against `names.txt` silently
  mismatches on every line.
