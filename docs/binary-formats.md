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

### The `1` byte advances the cursor and fixes up NOTHING — get it wrong and you silently corrupt the image

`1` is a *span* marker, not a fixup. A parser that adds an offset for it too writes `+= load_base`
into **one longword every 254 bytes** of a program it should never have touched. This really
happened: `tools/ghidra_scripts/PrgLoader.java` had that bug, and it hit every project in this
workspace — Wonder Boy's `SWB.PRG` has **3** real relocations and the loader applied **539**, so
536 longwords from `$4fa` to `$217cc` were corrupted. BuggyBoy got 93 spurious fixups, Joust 44.

The damage is invisible unless you look for it, and it goes both ways:

* **an operand disappears** — `move.b #$7,$00ff8201` (a screen-base write) became
  `move.b #$7,$04f78201`, no longer a hardware address, so a scan for hardware sites missed it;
* **an operand is invented** — `move.b $00ff860d,d7` (a DMA address-counter read) became
  `move.b $00ff8a05,d7`, i.e. a **blitter** reference in a game that has no blitter;
* **an immediate quietly changes** — `btst #5,$fffa01` became `btst #-3,$fffa01`;
* **an in-image address is pushed out of the image** and starts looking like I/O space.

Nothing about it desyncs the disassembly or throws an error. The cheap check is arithmetic:
count the fixups your parser produces and compare it against another implementation
(`prg_dis.parse_reloc` is the reference here); if your count is far larger, you are counting the
span markers. The cheaper check is structural — the spurious offsets are **exactly 254 bytes
apart**, which no real relocation table ever is.

## A `.PRG` with almost no relocations is position-DEPENDENT — find its real base

A game whose 136 KiB of text carries **three** relocation entries is not "unusually well written
position-independent code". It is a program that runs at a **fixed absolute address** and reaches
itself with absolute long operands (`jsr $e032.l`, `lea $44000.l`) that the reloc table deliberately
does not name. The few fixups it does have are the handful of pointers that must survive wherever
GEMDOS happened to load it — typically just the self-relocating stub's own operands.

The tell, and how to read the base straight out of the entry point (Wonder Boy's `SWB.PRG`):

```
+0x00000  3000                 move.w  d0,d0
+0x00002  4ef9 000213e0        jmp     $213e0.l          <- RELOCATED (fixup at +4)
...                            ; the stub at the END of the text:
+0x213f0  43f9 00000400        lea     $400.l,a1         ; NOT relocated -> the RUNTIME base
+0x213f6  41f9 00000008        lea     $8.l,a0           <- RELOCATED  -> the source offset
+0x213fc  203c 000084f6        move.l  #$84f6,d0         ; longwords to copy
+0x21402  22d8 5380 66fa       move.l (a0)+,(a1)+ ; subq.l #1,d0 ; bne
+0x2140a  4ef9 00000400        jmp     $400.l            ; NOT relocated
```

Read off `dest` (the unrelocated `lea`/`jmp` constant) and `src_off` (the relocated one), then

> **`load_base = dest - src_off`**

and the loaded image *is* the runtime image: the stub's copy becomes an identity copy, every
absolute operand resolves, and no staging step is needed. Wonder Boy: `0x400 - 8 = 0x3f8`.

Why it matters more than it looks:

- **Ghidra's yield is the symptom.** The same binary at `0x10000` gave 57 functions; at `0x3f8`,
  186. Absolute operands landing outside the loaded block break the call graph, and nothing
  announces it — you just get a thin decompile.
- **Pass the base everywhere.** `tools/headless.sh … <base>`, `names.txt` (whose addresses are then
  *runtime* addresses), and `recreate/project.toml`'s `load_base` must all agree, or one address
  means two things. Put the base in `names.txt`'s header so the next reader cannot miss it.
- **A low base can collide with the harness.** `tools/recreate_kit` reserves fixed low addresses for
  the TOS model; a program running at `0x400` covers them, and there is nothing below `0x400` to
  move them to (that is the 68000 vector page). The kit's two `project.toml` waivers —
  `tos_malloc_unused`, `tos_poked_input_unused` — exist for exactly that, and both are claims about
  the *game* that have to be evidenced, not conveniences.
- **Do not reach for the Hatari dump.** This is not a packed executable (see
  [`packed-executables.md`](packed-executables.md)); the bytes are already plain, only the base is
  wrong. Entropy tells the two apart: Wonder Boy's text is 4.96 bits/byte.

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

**"0 files" usually means a wrong BPB field, not an empty disk.** The lister derives the root
directory's position arithmetically — `reserved + nfats × fat_sectors` — so a single wrong byte
there points it at the middle of a FAT and it finds no directory entries at all. The field that
gets this wrong in practice is **`nfats` at offset 16**: Zynaps' 1988 disk declares `1` and really
carries `2` FATs of 3 sectors, so its root directory starts at sector 7 and the lister was reading
sector 4.

**Why TOS does not care, and it is not because it "reads the directory some other way".** The Atari
BPB — the structure `Getbpb` returns and the whole BIOS works from — *has no FAT-count field at
all*. It carries `recsiz, clsiz, clsizb, rdlen, fsiz, fatrec, datrec, numcl, bflags`, and `fatrec`
is defined as **the sector number of the SECOND FAT**, with the data area at `fatrec + fsiz +
rdlen`. Two FATs are baked into the layout TOS computes, whatever the DOS byte says — which on this
disk is exactly right, so the volume is perfectly coherent to a real ST and only a host tool that
believes `nfats` is misled. (The root-entry count at offset 17 fixes the directory's SIZE, not its
address, so it is not the field that saves anything here.) A disk can therefore ship like this and
work for its whole commercial life.

Diagnose it by looking for the directory rather than trusting the field, which is what
`st_extract.py` now does: a root that yields zero live entries is a WARNING and a non-zero exit, and
it scans the early sectors for 32-byte records that have the shape of 8.3 directory entries and
reports which BPB field would place the root there ("sector 7 ⇒ nfats=2"). Read the volume with
`st_extract.py --nfats 2 IMAGE.ST`, which touches no bytes. Write the corrected byte into a **copy**
only when something else has to mount the image too (an emulator, a mounter) — never into the dump —
and *script* that copy so the derived tree is reproducible rather than a one-off hand edit:
`projects/zynaps/tools/make_bin.sh` is the worked example, one byte, refusing to patch unless the
byte still reads what the master is known to hold.

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
  `0x0000044c` `.RAD` container header that opens `OVALAY9A.RAD` (that long is the file's
  packed length, not a magic — the container has none; see below). Only the last 31 bytes of
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
(`ZERO-FILLED` / `UNVERIFIED`, read out of the `.stx` the `.ST` was converted from):

```bash
python3 projects/wonderboy/notes/crack_differential.py wb_disk2.st --crack CRACK.ST \
        --stx "Wonderboy … (Disk 2 of 2)[a][!].stx"        # sibling NAME.stx if omitted
```

`--crack` is required and has no default: that release is deliberately not in this repo, so
the harness refuses to run rather than report green on nothing. The `.stx` is the second
dependency and the *only* authority on which sectors are holes, so it is never merely assumed:
every sector the dump read cleanly must match the `.ST` byte for byte, or the run refuses
rather than apply another disk's hole map. Exit status is `0` clean, `1` could not run (missing
or untrusted input) or ran with a warning, `2` the output would have overwritten an input, `3`
`--patch` refused bytes differing inside a cleanly-read sector, `4` `--patch` left a hole lost.

**Two failure modes a differential like this must not confuse.** A sector the FDC flagged is
still *placed*, so its bytes are present but unproven; a sector nothing could be placed into is
gone. Reporting both as "missing" makes a clean run impossible on any protected disk, and
reporting both as "fine" hides the real loss — so the harness's `--patch` ledger counts them
apart, and only the second is an error.

### Protection pattern: the address field claims another track

The cheapest protection to format and the easiest to misread as a bad dump. A track is written
with the **wrong track number in every sector's address field**, so a controller that seeks there
and asks for that track gets record-not-found, while a flux-level image records all ten sectors
perfectly. Zynaps (1988) is the worked example: cylinder 77's sectors claim track 76, cylinder
78's claim 73 and cylinder 79's claim 72 — thirty findings, one per sector, and `read.log` fills
with `Ignoring unexpected sector C:73 H:0 R:3 N:2`. `stx_extract.py` reports the class directly:
`cyl N side 0 sector M: address field claims track K, physically on cylinder N`.

Three things to establish before drawing any conclusion from it:

- **It is a format, not damage.** Every sector of the track is affected, the claimed track is
  *consistent* across the track, and the flux read is clean. One bad sector on one track with a CRC
  error is the other thing entirely.
- **Whether any file lives there.** Compare the highest cluster the FAT allocates against the
  affected cylinders. On Zynaps the last used cluster maps to cylinder 73 and cylinders 74–79 are
  free, so the 30-sector hole in the converted `.ST` costs nothing. If the protected track *is*
  allocated, the `.ST` has an interior hole and everything in "The damage is silent downstream"
  above applies.
- **Whether the program actually reads it.** Protection on the disk does not imply a check in the
  binary — the format may exist only to defeat a whole-disk copier. Settle it both ways: scan the
  whole image for `$ff8604`/`$ff8606`/`$ff860x` at *any* alignment (not just at instruction
  boundaries a desyncing linear sweep found) and for `Floprd`/`Flopver`/`Flopfmt`/`Rwabs` trap
  sites, **and** boot the stripped `.ST` — or a GEMDOS folder with no floppy at all — and see how
  far it gets. Zynaps has zero FDC references and four GEMDOS traps in the whole binary, and plays
  to level 1 from a plain folder. Where the two disagree, the boot wins and the scan was
  incomplete.

Whatever the verdict, the `.ST` is not a faithful copy of the disk; say so in the project's README
and keep the `.stx` as the one that is.

**Expect packed files — but check *whose* packing.** A cracked disk rarely holds plain
`.PRG`s: on the Wonderboy **crack** release only the `VAPOUR2` loader starts with `601a`,
every other file carries a crack-group `LSD!` stamp, and the real executable exists only in
memory — see [`packed-executables.md`](packed-executables.md) for getting at it. The
**original** disks of the same game are the opposite: `AUTO/SWB.PRG` is a plain `601a`
executable and no file carries the `LSD!` magic. Both disks then use the game's *own*
container below. Establish which release you are holding before you attribute a format to
the game, because the two crunchers wrap the same 12-byte header shape.

## Game resource containers (a worked example: `.RAD` / `.CRU`)

A game's data files usually go through a cruncher the game itself carries, and the depacker
is therefore *in the binary* — which makes the format provable rather than guessable. Wonder
Boy in Monsterland's `.RAD`/`.CRU` files are the worked example; the routine is transcribed in
[`projects/wonderboy/notes/rad_depacker.asm`](../projects/wonderboy/notes/rad_depacker.asm)
and reimplemented in `tools/depack_rad.py`.

**Container** (no magic — the game reaches these files only through its own 40-entry file
index table, so it never needs one):

| offset | type | meaning |
|---|---|---|
| `+0` | be32 | packed length = filesize − 12 (the only thing that locates EOF) |
| `+4` | be32 | unpacked length |
| `+8` | be32 | checksum: XOR of every longword of the stream |
| `+12` | … | packed stream, consumed **backwards** from EOF down to `+12` |

**Compression**: backwards LZ77. Bits leave a *longword* buffer LSB-first, refilled from
decreasing addresses; each longword carries its own end marker, so the refill (`move #$10,ccr`
+ `roxr.l #1,dn`) rotates a fresh 1 into bit 31 and every refilled longword yields exactly 32
data bits. The seed longword gets no injected marker, so its own top set bit ends it. Tokens,
with the output filled backwards too:

| prefix | meaning |
|---|---|
| `00` | literal run, 3-bit count → 1..8 bytes, each 8 bits off the stream |
| `01` | match, length 2, 8-bit offset |
| `1 00` | match, length 3, 9-bit offset |
| `1 01` | match, length 4, 10-bit offset |
| `1 10` | match, 8-bit length field → 1..256, 12-bit offset |
| `1 11` | literal run, 8-bit count → 9..264 bytes |

A match copies from `offset` bytes **above** the write pointer (already-written output),
one byte at a time, so an offset below the length repeats a run.

Three things here generalise to other in-game containers:

- **The length field is measured from the end of the header, not from the file.** The routine
  never learns the size of the buffer the file was read into, so trailing slack — a
  cluster-rounded read, a slice of a larger file — must not change the result. Take EOF from
  the header field.
- **A checksum field doubles as a decoder self-test.** This one is seeded into `d5` and XORed
  with every longword read; a correct decode both fills the output exactly and returns `d5` to
  0 with the stream pointer back at `+12`. Three independent invariants closing at once is
  strong enough to confirm a format *before* you ever emulate the original routine. It also
  gives the differential a *failure branch* to pin, using the disk's own damaged sectors — but
  see the trap below, because it pins the branch on only one of the two sides.
- **A packed length that must be a multiple of 4** is the tell that the stream is walked by
  longwords. On the 68000 an unaligned one is an address error, not a wrong answer.

```bash
python3 tools/depack_rad.py IN [-o OUT]     # default output: IN.out
```

**The trap: "both sides refused it" is not "both sides took the same branch."** The original
routine has *one* failure branch, the checksum; a host reimplementation grows a dozen guards the
original does not have, because it must not read and write outside its buffers the way the 68000
happily does. On real damage those host guards fire **earlier**, so a differential that only
checks "the 68000 returned its failure status and my depacker raised" pins the original's branch
and *nothing at all* on the reimplementation's — deleting its checksum test outright leaves the
run green. Wonder Boy's four damaged overlays do exactly this: two refuse on a match sourced past
the end of the output, two on a stream underrun, and none of them reach the Python checksum test.
Two things fix it, and both are cheap: make each refusal carry the **name of the guard** that
fired and assert that name per file, and, for whatever is then pinned nowhere, say so in the
harness (`KNOWINGLY UNPINNED`) and pin it with a synthetic case instead. The general rule: a
mutation test on the *reimplementation* is what tells you which side of a differential a green
row is actually holding.

**The stored form.** `SPRITES.CRU` carries the same two leading longs but they are *equal*
(both filesize − 64): the container's uncompressed form. The game never passes it to the
depack routine — the loader reads it to a buffer and the sprite setup indexes its body at
load address + 64. Detect it on `packed == unpacked` and refuse, rather than decoding noise.
Its 64-byte header is not all length fields either: `+$20..+$3f` is a 16-entry ST palette (every
word ≤ `$777`), while the body at `+$40` is not — worth checking for, since a stored container's
header is the natural place for a game to park the palette its data is drawn with.

**Gotcha: a `.PRG` whose text is not position-independent.** `SWB.PRG` has only 3 relocation
entries, yet its body is full of absolute references like `$5e3a` — because the entry stub
does `Super()`, copies text `$8..` down to absolute `$400` and jumps there. Every absolute
operand in the body therefore reads as *text offset + `$3f8`*. Two consequences: relocation
count is not evidence of position-independence, and to enter one of its routines under an
emulator you must reproduce the stub's copy (assert the stub's bytes, so a different build
cannot be laid out at the wrong base) instead of loading the `.PRG` at a base of your own.

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