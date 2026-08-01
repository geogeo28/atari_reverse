# Binary Formats (GEMDOS executables)

Everything you need to parse an Atari ST program before disassembly. Reference
parser: `tools/prg_dis.py` (stdlib, no deps).

## The GEMDOS `.PRG` header (28 bytes, big-endian)

| Off | Size | Field | Notes |
|----:|-----:|-------|-------|
| 0x00 | 2 | magic | **`0x601A`** (a `bra.s +26` — legacy) |
| 0x02 | 4 | text length | code segment |
| 0x06 | 4 | data length | initialized data (often 0; merged into text by Devpac) |
| 0x0A | 4 | bss length | zero-init (not stored in file) |
| 0x0E | 4 | symbol table length | 0 or a DRI symbol table |
| 0x12 | 4 | reserved | |
| 0x16 | 4 | flags | TPA/fastload bits |
| 0x1A | 2 | absflag | if non-zero, **no relocation** |

File layout: `header(28) | TEXT | DATA | SYMBOLS | RELOC-TABLE`.
Extensions `.PRG` (GEM), `.TOS` (console), `.TTP` (takes params) share this format.

TEXT and DATA load **contiguously** at the load address; BSS is a zero-filled region
right after. Everything is position-independent — it can load anywhere, fixed up by the
relocation table.

## DRI symbol table (14 bytes/entry)

`[8 bytes name (space/nul padded)] [2 bytes type] [4 bytes value]`

Type word is a bitfield; the section bits decide the address base:

| Bit | Meaning |
|----:|---------|
| 0x8000 | defined |
| 0x2000 | global |
| 0x0400 | **DATA** section → addr = base + tlen + value |
| 0x0200 | **TEXT** section → addr = base + value |
| 0x0100 | **BSS** section → addr = base + tlen + dlen + value |
| 0x0048 | (both set) extended/long name — next entries hold extra name chars |

BuggyBoy kept 11 TEXT symbols (a sound driver's exports: `INITTUNE`, `EGVOL`…).
Beware: assemblers put **inline variables in the TEXT section too**, so a TEXT symbol
is not necessarily code — don't blindly make them functions.

## Relocation table (DRI format)

At `28 + tlen + dlen + slen`. Encodes offsets (into the TEXT+DATA image) of 32-bit
longwords that must have the load base added.

- First entry: a **32-bit** offset (the first fixup). `0` ⇒ no relocations.
- Then a stream of **bytes**: `0` = end; `1` = advance cursor by 254 (span > 255);
  any other `b` = advance by `b`, and fix up the longword there.

To relocate: for each fixup offset, `*(u32*)(image+off) += load_base`. Do this and
absolute references become correct — the single biggest lever for good disassembly.

**A fixup is not always a pointer in data.** The table names *longwords*, wherever they sit —
including the immediate field of an instruction. `cmpi.l #$00007832,d0` in the file is really
`cmpi.l #$00017832,d0` at a `0x10000` base, and a listing of the unrelocated bytes shows the wrong
constant with nothing to flag it: no impossible instruction, no desync, just a magic number quietly
short by the load base. This is why every listing should be taken from the **relocated** image, and
why a constant that lands near the load base is worth checking against the fixup offsets. See
[`m68k-disassembly.md`](m68k-disassembly.md) for the disassembly consequences (Joust's
`rng_advance` is the worked example).

## Quick recon

```bash
python3 tools/prg_dis.py projects/<name>/bin/GAME.PRG | head -60
```
Prints header sizes, reloc count, embedded strings, and a first-pass disassembly.
Strings often reveal filenames the program loads, menu text, and author credits
(BuggyBoy: `"coded by Martin W.Ward"`, `"COURSES.DAT"`, `"GRAPHICS.GRA"`).

## `.ST` floppy images (the container a game arrives in)

A `.ST` file is a **raw sector dump** of a floppy: no header, no compression, just
`tracks × heads × sectors × 512` bytes in order (720 KB = 1440 sectors; ST-formatted disks
often squeeze in more, e.g. 1640). Sector 0 is the boot sector, and TOS writes the standard
DOS **BPB** there — little-endian fields, even on a big-endian CPU — so the filesystem is
plain **FAT12**: `boot | FAT ×n | root directory | data clusters`. Never assume a geometry;
read it from the BPB.

```bash
python3 tools/st_extract.py projects/<name>/bin/GAME.ST              # list the tree
python3 tools/st_extract.py projects/<name>/bin/GAME.ST -o extracted # extract it
```

The lister prints the geometry it derived plus the first 4 bytes of every file, which is
usually enough to classify it (`601a` = a GEMDOS executable, see above; anything else = data
or a packed blob). It exits nonzero and prints a `WARNING` line per suspicious cluster chain
or directory entry instead of silently truncating — treat a dirty exit as "this image is
damaged", not as noise.

### `.stx` / Pasti images (when the disk is copy-protected)

A `.ST` can only hold what a normal FDC read returns: 512-byte sectors, numbered 1..N,
that read cleanly. Copy protection lives in exactly what that throws away. A **Pasti
(`.stx`)** image keeps it: per sector the raw **address field** (its claimed track/head/
sector/size + CRC), the **FDC status** the dump got when reading it, the measured read
time and bit position on the track, plus a **fuzzy-byte mask** for bits that read back
differently every revolution, and the raw **MFM length** of each track. That is enough to
re-create, in an emulator, a read that *fails in the specific way the original disk fails* —
which is what the game's protection check is looking for.

Layout: a 16-byte file header (`RSY\0`, LE `version`(=3) u16, `tool` u16, reserved u16,
**`track_count` u8**, `revision` u8, reserved u32) followed by `track_count` variable-length
track records, each walked by its leading `record_size` u32. A record is a 16-byte header
(`record_size`, `fuzzy_size` u32, `sector_count` u16, `flags` u16, `mfm_size` u16,
`track_number` u8 — side in bit 7, cylinder in bits 0..6 — and `track_type` u8), then, when
`flags` bit 0 is set, `sector_count` × 16-byte sector descriptors, then the fuzzy mask, then
the data area that the descriptors' `data_offset` fields index into. The last record must end
**exactly** at EOF — that is the cheapest whole-file integrity check, and `stx_extract.py`
refuses an image that fails it.

Note `track_count` is a **u8**, not a u16: offset 11 is `revision`, which is `2` on these
images, so a little-endian u16 read at offset 10 yields `0x0252` = 594 tracks, not 82. That
fails loudly (the walk runs off EOF long before record 594) rather than quietly — but only
because the exact-EOF rule is checked. Read the u8.

Two-step pipeline — flux image to sectors to files:

```bash
python3 tools/stx_extract.py GAME.STX                  # header, per-track table, PROTECTION report
python3 tools/stx_extract.py GAME.STX --to-st GAME.ST  # the clean FAT12 sector image
python3 tools/stx_extract.py GAME.STX --to-st GAME.ST --strict   # ...placing clean reads only
python3 tools/st_extract.py  GAME.ST -o extracted      # then as any .ST
```

**"Unreadable" is not "unrecorded" — the distinction is the whole game.** A Pasti image
stores a sector's 512 bytes *and* the status the FDC returned for them. A CRC error can be
one bad bit anywhere in the sector or in the CRC itself, so most of those bytes are usually
the real content. `stx_extract.py` therefore **places** a status-flagged sector by default
and emits a per-sector `WARNING` that its content is unverified (so the run still exits 1);
`--strict` restores the conservative rule of placing nothing whose *content* a status bit
questions (lost data, CRC error). Only a
slot with no recorded bytes at all — no descriptor, an unformatted track, or a
record-not-found status, where the FDC never reached a data field — is zero-filled, and that
`WARNING` says so in different words. Three FDC bits do not disqualify a sector at all:
Pasti's "variable read time" `0x01`, the deleted-data mark `0x20`, and Pasti's `0x80`, which
is its own overload for *"a fuzzy mask exists for this sector"* and **not** a WD1772 read
error — a sector carrying only `0x80` reads back fine on real hardware. All three are still
reported as protection.

Geometry — cylinders, sides, sectors/track — is derived from the recorded sectors rather
than the BPB, because a protected disk need not carry a filesystem at all. Sectors/track is
voted on the **count of `.ST`-shaped descriptors** per track — 512 bytes, wholly inside their
own track record — and never on how many sectors read *cleanly*: how a track was formatted is
a property of the disk, while how well it read is a property of one dump, and sectors/track is
the LBA stride. Vote it on read quality and read damage across a bare majority of tracks
silently shifts every track of the image; drop the shape test and one 1024-byte protection
sector per track does the same. (A count past any real floppy format is refused outright,
so a malformed record cannot inflate a small file into a gigabyte `.ST`.) Where a plausible
boot sector exists its BPB cross-checks the result — and *plausible* means every field is
bounds-checked before any of them is believed, or a custom loader that happens to hold
`0x0200` at offset 11 gets its garbage trusted. A disagreeing sectors/track or head count is
reported, and so is a declared volume that does not *fit* inside the derived geometry (that
is the check that catches a wrong stride). The BPB's total sector count also decides whether
a trailing unformatted track is ordinary drive padding or a hole in the filesystem — cylinder
order alone cannot tell them apart. Both modes run the placement pass,
so the verdict depends on the disk and not on whether you asked for the file. The protection
findings themselves are *not* warnings, since a protected disk having them is the expected
result.

**The protection does not survive the conversion, and cannot.** Fuzzy bits, a CRC error, a
sector claiming to live on another track, an extra sector 11/12 past a 10-sector format, a
track with one sector deliberately unformatted — none of these are expressible in a raw
sector dump, by construction. So a reconstruction that must run from a plain `.ST` (or from
a GEMDOS hard-disk folder) has only two honest options: **satisfy** the check (emulate the
drive at Pasti level, i.e. ship the `.stx` and a Pasti-aware emulator) or **bypass** it
(patch the branch the check feeds). Which one is a project decision — but record in
`STATUS.md` that the plain `.ST` is *not* a faithful copy of the disk.

Worked example — the two 1989 Wonderboy in Monsterland disks, both single-sided
82-cylinder × 10-sector formats (80 in the FAT12 volume, 2 unformatted spares):

| finding | disk 1 | disk 2 |
|---|---|---|
| cylinders 0–4 carry 12 sectors; #11/#12 read FDC `0x88` (CRC error + fuzzy) with 1024 fuzzy bytes/track | yes | yes |
| cylinder 12: 12 descriptors in the physical order 7, 11, 12, 3, 9, 10, 1, 2, 3, 4, 5, 6 — four unreadable (FDC `0x08`/`0x88`/`0x89`/`0x08`), three of them claiming `id_track=4`, sector ID 3 duplicated, and **no sector 8 at all** | — | yes |
| cylinders 7–11 formatted with only **9** sectors — one deliberately absent per track (10, 8, 6, 4, 2: a descending diagonal) | — | yes |

Disk 2's damage sits **inside allocated file clusters** — six `OVALAY*.RAD` files — and it
has **two causes that must not be conflated**:

- **Never formatted.** The 9-sector diagonal (cyl 7–11) and cylinder 12's missing sector 8
  have no address field on the disk and therefore no descriptor and no bytes in the image.
  Nothing can recover them: they were never written to the physical disk either, so a loader
  reading them gets a read error on the original too, which is the point. The zero-filled
  holes span one `.ST` sector each — 352 B of `OVALAY4B` (the file ends mid-sector), 512 B of
  `OVALAY5B`, `OVALAY6A` and `OVALAY9A` — of which 316 / 470 / 479 / 483 bytes are actually
  wrong, the rest being zeros in the real data too.
- **Present but failed CRC.** Cylinder 12 **sector 7** (FDC `0x08`) *is* recorded — its 512
  bytes are in the `.stx` — and they are demonstrably the real content: diffed against a
  crack release of the same game, **481 of the 512 bytes match exactly**, including the
  `0x0000044c` `.RAD` container magic that opens `OVALAY9A.RAD`. Only the last 31 bytes of
  the sector are corrupt, which is presumably why the CRC failed. That is why the default is
  to place such a sector and warn, not to throw it away.

(`OVALAY3A` and `OVALAY7B` lose only cluster slack past their declared length.)

**The damage is silent downstream.** The hole is *interior*: `stx_extract --to-st` zero-fills
whatever it could not place, the directory entry still claims the full length, and
`st_extract.py` then extracts a full-size file with a zero-filled middle and exits **0** — a
`.ST` carries no marker for "this sector was never readable", and none either for "these
bytes came from a sector that failed its CRC". The `WARNING` lines from `stx_extract` are the
only place either fact exists, so keep them: re-deriving them later from the `.ST` alone is
impossible. `projects/wonderboy/notes/crack_differential.py` is the harness that established
the 481/512 figure above, by diffing the converted `.ST` against a crack release and
attributing every wrong byte to the `.ST` sector and the *cause* it came from
(`ZERO-FILLED` / `UNVERIFIED`, read out of the `.stx` beside it):

```bash
python3 projects/wonderboy/notes/crack_differential.py wb_disk2.st --crack CRACK.ST
```

`--crack` is required and has no default: that release is deliberately not in this repo, so
the harness refuses to run rather than report green on nothing.

**Expect packed files.** A cracked disk rarely holds plain `.PRG`s. On the Wonderboy disk
only the `VAPOUR2` loader starts with `601a`; every other file carries a crack-group `LSD!`
stamp, and the real executable exists only in memory — see
[`packed-executables.md`](packed-executables.md) for getting at it.

## Building a `.PRG` (reverse direction: recompiling the reconstruction)

Once functions are reconstructed in C, you can cross-compile them back into a runnable
GEMDOS `.PRG` (`m68k-elf-gcc`, link at base 0 with `--emit-relocs`, `objcopy -O binary`,
then wrap with a header + reloc table). BuggyBoy does this in
`projects/buggyboy/recreate/render/atari/` (`mkprg.py`, `tos.ld`). Two gotchas cost real
debugging time — both manifest as the program *seeming* to run but silently corrupting:

**`.bss` must abut TEXT+DATA (no alignment gap).** GEMDOS places BSS immediately at
`load_base + tlen + dlen` and zeroes `blen` bytes. If a BSS symbol has a large alignment
(e.g. a 256-byte-aligned screen buffer), the linker pushes `.bss` to a boundary *past* the
end of `.data`; `objcopy -O binary` does **not** emit that trailing gap, so on-target every
BSS address is off by the gap and stores land in the wrong place (classic silent
corruption). Fix: force text+data to the same boundary and drop per-symbol alignment inside
`.bss` (`. = ALIGN(256); .bss (NOLOAD) : SUBALIGN(1)`), and pad the emitted binary up to
`_bss_start` so `tlen` reaches where GEMDOS will put BSS.

**A returned file handle of `0` means the open silently failed — never a valid file.**
GEMDOS reserves the low handles: **0 = stdin (keyboard)**, 1 = stdout, 2 = aux, 3 = prn. A
successful `Fopen`/`Fcreate` returns a real handle (≥ 6; Hatari's GEMDOS-HD uses **64+**); a
*failed* open returns a **negative** error. So handle 0 is the tell-tale of a broken build,
not a missing file — and it's insidious: `Fread(0,…)` then reads the **keyboard** (blocks
forever under headless Hatari), and `Fwrite(0,…)` writes to **stdout** (silently discarded,
0-byte output files). If your loader "hangs in the decompressor" or writes empty dumps,
check the handle first (`hatari --trace gemdos`). In the BuggyBoy build the trigger was the
order of the trap wrappers in the entry `.s`: the file-I/O wrappers (`Fopen`…`Fwrite`) must
come **first**, right after `_start`, matching the known-good demo layout — placing the
control wrappers (`Super`/`Malloc`/`Crawio`) before them made Hatari hand back handle 0.

Verify a build headlessly: run it under Hatari with a GEMDOS drive, have the shim dump a
framebuffer / result file to `C:`, read it back and diff against the host reconstruction
(`render/atari/run_golden.py`, `game_smoke.py`). See [`tos-os-calls.md`](tos-os-calls.md)
for the trap selectors and startup sequence to mirror.

→ Next: [`m68k-disassembly.md`](m68k-disassembly.md) or [`ghidra-pipeline.md`](ghidra-pipeline.md).