# Wonder Boy in Monsterland (Activision/Sega, 1989) — Atari ST

Third game through the workspace pipeline, and the first taken from **original, uncracked disks**
rather than a release someone had already stripped. Two Pasti `.stx` images go in; a FAT12
filesystem, a self-relocating 68000 program and a solved resource cruncher come out.

Status: **Stage 1 done** (the binary is mapped and named at the right base) and the **differential
harness is bound** ([`recreate/`](recreate/)). No function is reconstructed yet — see
[`recreate/STATUS.md`](recreate/STATUS.md).

**How much of it can the harness actually verify?** Measured, in
[`recreate/PORTABILITY.md`](recreate/PORTABILITY.md): 83.8 % of the **recovered** code runs
end-to-end under the oracle today and the gameplay logic is portable now — but "recovered" is only
46.8 % of the program's believed code, the gameplay logic is the least-covered subsystem that can
be read at all (36 %, against 56-100 % for boot, sound, disk, input and video), and
13 % of what is measured would come back *falsely* green because a branch below it depends on a
hardware read the oracle answers `0`.

> No game data is in this repository. `bin/` is gitignored; bring your own disks.

## The three things that shaped this project

### 1. The program does not run where you load it

`AUTO/SWB.PRG` is `text=0x214d8`, no data, no bss, and **three** relocation entries — the signature
of hand-written, position-dependent assembly. Its entry is a trampoline into a 48-byte stub at the
end of the text:

```
move.l  #text_end,-(sp)      <- relocated
move.w  #$20,-(sp)
trap    #1                    ; GEMDOS Super(new_ssp) — the ONLY trap in the whole image
move.w  #$2700,sr             ; supervisor, interrupts masked
lea     $400.l,a1             ; NOT relocated — a genuine absolute address
lea     image+8,a0            <- relocated
move.l  #$84f6,d0             ; 34038 longwords = 0x213d8 bytes
.l: move.l (a0)+,(a1)+
    subq.l #1,d0
    bne.w  .l
jmp     $400.l                ; NOT relocated
```

So the body copies itself to the fixed absolute address `$400` and lives at **`$400..$217D8`**:

> **runtime address = image offset + `0x3F8`**   (image offset = file offset − 28)

Loaded at the workspace default `0x10000`, every absolute operand in the body (`jsr $xxxx.l`,
`lea $xxxx.l`) dangles outside the loaded block, so Ghidra's flow analysis cannot follow one.
**That — not packing, not jump tables — is why a first bootstrap recovers only 57 functions from
136 KB and the image appears full of unexplained multi-kilobyte gaps.** At `0x3F8` the same binary
yields 186 before any naming.

`run.sh`, `names.txt` and `recreate/project.toml` all use `0x3F8`. The general lesson is written up
for any future game in [`docs/binary-formats.md`](../../docs/binary-formats.md) — *a `.PRG` with
almost no relocations is position-dependent; find its real base.*

### 2. It barely uses the operating system

**One trap instruction in 136 KB** — the `Super` above. Zero BIOS, zero XBIOS, zero GEM, no GEMDOS
file I/O, no `Malloc`. The game drives the **WD1772 floppy controller and the DMA chip directly**
and implements its own **FAT12 layer** (runtime `$6118..$64f0`) to find its files by name.

That is not an eccentricity, it is the copy protection: disk 1 carries extra sectors with **IDs 11
and 12** on cylinders 0–4, outside the standard 1–10 numbering, holding deliberately unstable
"fuzzy" bytes. No OS call can address such a sector, so the game had to talk to the hardware itself.
The driver reads ten data sectors per track in a single multi-record FDC command, which is what
leaves room for those extra IDs.

### 2b. …and it carries a Rob Northen-style Copylock

`$ed2a..$f89e` is a **trace-decrypting protection blob**, and it is live: `load_resource_by_index`
calls it at `$e7bc` on the first resource load. It installs handlers on the `illegal` (`$10`),
privilege-violation (`$20`) and trace (`$24`) vectors, deliberately executes `illegal` instructions
that vector to the following instruction, and single-steps itself while XOR-decrypting its own
instruction stream (`move.l -4(a0),d0 / not.l d0 / swap d0 / eor.l d0,(a0)`). Only its tail is
plaintext, and it compares against two accepted key values before returning.

Two consequences for the reconstruction, both recorded rather than papered over:

* **A differential harness hits `jsr $ecca` on the very first resource load.** It must model the
  Copylock or stub it out.
* The fuzzy-byte check inside it can never be pinned — not merely because fuzzy bytes are
  non-deterministic by design, but because **the code performing the check cannot be read
  statically at all**.

It also cost us a wrong turn worth recording: the block was first classified UNKNOWN on an entropy
reading of 7.73 bits/byte. The high-entropy part turned out to be a *plaintext* lookup table of
`2i mod 256` — a byte permutation, which is maximally entropic by construction. Entropy never
implied packing here.

### 3. The resource format is solved and proven

Every `.RAD` (and the stored-form `.CRU`) is a 12-byte header over a backwards-consumed LZ
bitstream. `tools/depack_rad.py` decodes it, and
[`notes/rad_differential.py`](notes/rad_differential.py) proves the decoder by running **the game's
own depack routine** under the Musashi oracle and diffing: **45 files, 0 failures**. Details in
[`docs/binary-formats.md`](../../docs/binary-formats.md) and
[`notes/rad_depacker.asm`](notes/rad_depacker.asm).

Despite the name, the `OVALAY*.RAD` files are **data, not code overlays** — a depacked one contains
no `rts`, `bsr`, `jsr` or `movem` at any even offset, and all 37 on disk depack to exactly 15592
bytes, so they are fixed-size per-stage records.

The game finds its files through a 40-entry index table at runtime `$2143E` (12-byte space-padded
8.3 name + 4 bytes of stride padding). Only **35** of the 37 `OVALAY*` files are named in it:
`OVALAY10.RAD` and `OVALAY11.RAD` are on disk 2 and depack cleanly, but nothing in the table reaches
them. Whether the game loads them by some other path is **unestablished**.

## Seeing the artwork

`tools/extract_gfx.py` decodes every piece of the game's art into PNGs, reading only `bin/` and
`tools/depack_rad.py`: one RGBA file per SPRITES.CRU sprite (482, transparent where the mask says
so) plus a contact sheet and a manifest of offsets and anchors, the 661 background tiles of
TILEDATA.RAD, the three full 320x200 screens (TITLESCR / CREDITS / DATADISK), the eight in-PRG
palettes as swatches and as `$0RGB` words, the text/frame/digit glyph sheet, and a HUD sheet of the
record bitmaps, meter cells, slot cells and panel frames. Every table address and count it uses
comes from `names.txt` / `recreate/include/wonderboy.h`, at the same `0x3F8` base, and it self-checks
before it writes: the sprite descriptors must tile the CRU body exactly (482/482) or it prints the
mismatches and exits nonzero. Run it with the workspace's python — `python3
tools/extract_gfx.py [OUT_DIR]`, output defaulting to `out/gfx` (gitignored, like the rest of the
game's data). It needs Pillow.

## Hearing the music

`tools/extract_audio.py` is the audio twin — but where the art sits in data files, the music is a
custom in-house replayer linked INTO the .PRG (`notes/sound_module_recon.md` maps all 4333 bytes of
it), so this extractor captures rather than decodes: it runs the original 68000 driver under the
recreate kit's Musashi oracle with the opt-in audio-capture mode armed (the mode exists because the
differential deliberately refuses the PSG read-backs and tempo reads the replayer needs — see
`tools/recreate_kit/README.md`), plays each of the 17 songs and 26 sound effects from a fresh
image, ticks `snd_music_tick` once per 50 Hz frame, and folds the captured YM2149 register writes
into per-frame register states. Out come `out/audio/songs/*.ym` + `sfx/*.ym` (YM6 register dumps,
masked to the bits the chip decodes, real loop frame in the header), rendered `.wav`s from its own
YM2149 synth, and a manifest of frames, durations and end reasons. Four songs end themselves via
opcode `$8e`; four reach an exact whole-state loop; the other nine have an ODD speed byte, which
puts an exact repeat out of reach, so they are captured to their MUSICAL loop instead — the same
state hash with the fractional row-clock byte left out (`notes/sound_module_recon.md`'s post-recon
addendum has the arithmetic, and the manifest header the caveat). The render answers to two checks:
every `.wav` must clear an RMS floor, and song 0's spectrum must be explained by its own register
stream — an FFT of a window of the render, each of whose strongest peaks has to be a partial of a
tone period the capture actually wrote. Run it with the workspace's python —
`python3 tools/extract_audio.py [OUT_DIR]`, output defaulting to `out/audio`. It needs numpy.

## The disks

Both `.stx` images are the original release. `tools/stx_extract.py` reports the protection and
converts to a plain `.ST`; `tools/st_extract.py` pulls the files out.

| under `bin/` | what it is |
|---|---|
| `*.stx` | the two Pasti images — the authority on the physical disks |
| `wb_disk1.st`, `wb_disk2.st` | plain FAT12 conversions |
| `wb_disk2_repaired.st` | disk 2 with the protection's holes filled — **a hybrid artefact**, see below |
| `disk1/` | `AUTO/SWB.PRG`, `TITLESCR.RAD`, `CREDITS.RAD` — **authentic and complete** |
| `disk2/` | the authentic dump: 40 files, **four of them damaged** |
| `disk2_repaired/` | the same 40 files with those four made whole |

**Disk 1 lost nothing**, because its protection lives in sectors the filesystem never references.
**Disk 2 lost 1779 bytes** to sectors that were never formatted, plus 31 bad bytes in one
CRC-flagged sector — damaging `OVALAY4B`, `OVALAY5B`, `OVALAY6A` and `OVALAY9A`.
[`notes/crack_differential.py`](notes/crack_differential.py) repairs those holes from a cracked
release under a strict safety rule (a byte may be taken only from a zero-filled or unverified
sector), producing `wb_disk2_repaired.st`.

Keep both corpora. `disk2/` is the primary record of what the physical disk gave up; `disk2_repaired/`
is a **repaired hybrid** whose filled bytes come from a crack and are therefore never evidence about
the pressed disk. The RAD differential uses the repaired copy for those four files and says so per
row.

The four damaged originals are also the only files on either disk that both implementations
*refuse*, and the differential checks that they do. Be careful what that proves: the 68000 reaches
its checksum-failure path, but the Python decoder refuses them **earlier and for different reasons**
(a match reading past the end of the output, or the stream running off the front of the file), so
the agreement is "both refuse", not "both refuse for the same reason". See
[`notes/rad_differential.py`](notes/rad_differential.py) for exactly what is and is not pinned.

## Working on it

```bash
bash run.sh          # bootstrap Ghidra at 0x3F8 (RE-IMPORTS AND WIPES NAMES)
bash reapply.sh      # the naming loop: names.txt -> DB -> decomp.c
cd recreate && make test
```

`names.txt` is the source of truth for every name, addressed at base `0x3F8`. The map, the region
table and the anchor inventory are in [`notes/architecture.md`](notes/architecture.md).
