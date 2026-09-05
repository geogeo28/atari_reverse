# Wonder Boy in Monsterland (Activision/Sega, 1989) — Atari ST

Third game through the workspace pipeline, and the first taken from **original, uncracked disks**
rather than a release someone had already stripped. Two Pasti `.stx` images go in; a FAT12
filesystem, a self-relocating 68000 program and a solved resource cruncher come out — and then a
`.PRG` that is the first thing in this repository to leave the emulator entirely. It boots a **real
4 MB STE from its own 720 KB floppy**, through TOS's `AUTO` folder, with no host in the machine —
and three sessions at that machine found two defects every emulated surface here had been green on.

**Status: 330 functions verified · 41,652 bytes of the original's machine code · 6465 differential
tests** (plus 464 in the shared kit). The per-function table, every boundary and every limit that is
disclosed rather than closed are in [`recreate/STATUS.md`](recreate/STATUS.md).

**How much of it can the harness actually verify?** Measured rather than asserted, in
[`recreate/PORTABILITY.md`](recreate/PORTABILITY.md): **80.7 % of the program's believed code is now
inside the measurement**, and only **226 bytes** of it remain genuinely unknown.

When the harness was first bound, before any function was reconstructed, only 46.8 % of the
program's believed code was even recovered; the history of how that became 80.7 % is in the same
file.

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

## Four things had to move in the tooling

Three of them are now shared in [`tools/recreate_kit/`](../../tools/recreate_kit/README.md), the
differential harness every game here binds through its `recreate/project.toml`. The kit gained a
**file-load seam**: a game whose boot chain bottoms
out in a sector driver cuts it at the lowest routine whose inputs are *file-shaped* — a name and a
destination — and calls `disk_read_file` across the cut, which is the staged-file model off target
and real GEMDOS on it ([`TRAP_MODEL.md`](../../tools/recreate_kit/TRAP_MODEL.md)'s Phase 9). The
**boot chain is composed from slices** rather than ported as one routine, because the original cuts
itself into four with fire waits only an IKBD interrupt can end: `boot_title_screen`,
`boot_credits_screen`, `boot_load_stage` and `boot_prompt_screen`, each verified whole against the
oracle across the seam. The port has **one shifter sink** (`recreate/src/shifter.c`) — the screen
base and the sixteen colour registers are off the 68000's 24-bit bus as far as the loaded image
goes, so every write to them meets in one file with one on-target arm, and a build gate refuses a
second copy of it. And `recreate/atari/mkprg.py`, `../../tools/st_build.py`,
[`recreate/atari/HARDWARE.md`](recreate/atari/HARDWARE.md) and `../../tools/assert_trap_registers.sh` are
what turn the cross-compiled cores into a **bootable 720 KB FAT12 floppy** and keep them safe on the
way — that last one because TOS preserves fewer registers across a trap than GCC's m68k ABI believes
are callee-saved, which was three bombs in Buggy Boy.

## On target — the ladder runs to ten rungs

[`recreate/atari/`](recreate/atari/README.md) cross-compiles the same verified cores to m68k and
climbs from "a real machine drives the reconstruction" (M1: `vbl_handler` runs on the level-4
autovector fifty times a second, and its own word has to agree with the shim's independent tick
count) to "the reconstruction boots itself off a floppy" (M10). In between: at four anchored frames
of real play the **32000 framebuffer bytes**, the **sixteen hardware pens** and Hatari's own
**rendered picture** are identical to the shipped 1989 binary's, on EmuTOS and on TOS 1.04 (M2/M5);
the screen-base publications match flip for flip, and the shipped binary's 1,155 PSG writes over the
window are an exact prefix of ours (M6); the boot chain then **recomputes** the post-boot RAM those
rungs had staged from a dump of the original — **~522,500 of 523,272 bytes identical, the rest
inside ten named bands and nothing unnamed left over** (M8); and M9 wires every one of
`game_main_loop`'s five endings back into the boot chain, so `atari/run.sh` opens a build that boots
its own title screen, reloads on a round end and restarts on ESC. M10 puts all forty resources and
the 144,831-byte `WB-ownrun.PRG` on one 720 KB disk — **689,152 bytes in 673 clusters, 38,912 free
of 728,064** — booted by TOS's own `AUTO` loader with no host directory behind it.

## Then somebody switched an Atari on

…and it said two things nothing here could. The disk booted a 4 MB STE (TOS 1.62) **to the
desktop**: our own `vbl_handler` was counting down an idle fuse that expired one vblank into the
first GEMDOS sector read, dropped the drive-select lines mid-transfer, and the ROM's retry did not
re-select. The protocol that arms and disarms that fuse lives in two instructions *below* the
declared seam, so the substitution had dropped it — and because the arm overwrites the disarm, a
final-memory differential sees the same bytes either way and cannot ask the question at all. Fixed,
and the disk came back with **the title screen up and fire doing nothing**. The boot's eight-byte
`init_ikbd` sends the only IKBD command in the whole binary — `$12`, *disable mouse* — and the port
had not reproduced it; on a real ST joystick 1's fire line and the mouse's right button are the same
wire, so the 6301 was reporting every press as a mouse packet the game does not read. The machine's
own record showed 35 IKBD bytes delivered and not one of them a joystick report. Both fixed, and the
third run played: title, fire, credits, fire, stage 1's overlay, tiles and sprites, and the frame
loop — on the machine.

The two shapes are entries **11** and **12** of
[`docs/on-target-execution.md`](../../docs/on-target-execution.md)'s thirteen-entry taxonomy — *a
live interrupt handler reading state whose protocol lives below a declared seam*, and *a gate
crossed by a poke is a gate whose input path never ran* — and they are Wonder Boy's own two
contributions to it from the machine. It is not the first: entry 3's register half is Buggy Boy's
three-bombs-on-the-STE crash, found the same way.

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

## Gallery

`gen_readme_assets.py` is the smaller, tracked cousin of that extractor: it renders the pictures
below into `assets/wonderboy/*.png` by *running the reconstruction* rather than by decoding the
files — **host-side, with no emulator and no TOS ROM in the loop**. It loads your own `SWB.PRG`
through the kit, serves the game's own resource files across the file-load seam, and drives the same
entry points the tests drive — the four composed boot slices and `game_main_loop` itself — then
de-interleaves the framebuffer they paint with the game's own palette words. Run it under
`recreate/`'s venv: `./.venv/bin/python ../gen_readme_assets.py`.

One thing the seam cannot do: `SPRITES.CRU` is 279,034 bytes and the kit's whole staging area is
258,048, so the file is placed at the address the boot's own load lands on and the stage's sprite
install is redone over it whole — with every marked sprite's installed cells then checked byte for
byte against the file, because without that check 28 of stage 1's 143 sprites quietly installed
depacked tile data instead. The two vertical-blank waits inside `flip_screen` are answered by the
kit's scheduled-write model and the play frames come from one fixed joystick script. The game's only
entropy is the shifter's video address counter at `$ff8207`/`$ff8209`, which `rng_next` and
`bcd_add_random_1_to_4` read and which the kit's seeded-hardware model answers with whatever the run
declares: on a machine that counter is a clock, so each play frame here declares the next byte of
**one fixed pseudo-random sequence keyed by the frame index** rather than a single constant for the
whole run. The whole set is therefore a function of the binary, the game's own files, that joystick
script and that sequence — which the script asserts by rendering the set twice and refusing to write
a picture whose two renderings differ.

Every play picture is drawn on a screen the **whole boot chain** built, in the boot's own order —
the prologue's clears, then the title, credits and stage slices — because the status panel's
artwork is drawn by no routine at all: it is part of the CREDITS picture, which
`boot_credits_screen` copies down onto the buffer the shifter is showing, and the play window is
then painted over the middle of it. That is checked rather than assumed: at the instant
`boot_load_stage` returns, **both 32000-byte screen buffers are byte-identical to the original
1989 binary's own post-boot RAM** — `recreate/atari/build/ORIGRAM.BIN`, dumped off the shipped game
under Hatari at `$f8b4`, the same anchor the on-target rungs use — and the script fails if one byte
of either differs.

| Title | Credits | The data-disk prompt |
|:---:|:---:|:---:|
| ![](../../assets/wonderboy/title.png) | ![](../../assets/wonderboy/credits.png) | ![](../../assets/wonderboy/prompt.png) |

`boot_title_screen` ($e512..$e550) arms the protection, asks `load_resource_by_index` for
`TITLESCR.RAD` across the seam, inflates it with `rad_depack` straight onto the screen buffer and
hands its palette row to `set_palette`. `boot_credits_screen` does the same for `CREDITS.RAD`,
copies the result down onto the buffer the shifter is showing, and then runs `game_restart_reset`
over it — a new game, which is what draws the status panel's lives over the picture. The third is
`boot_prompt_screen` ($e494..$e4d4), the slice all three of the game's `jmp $e494.l`
endings land in: ESC, the game-over box expiring, and the message terminator the protection's own
failure path also reaches.

| Stage 1 begins | …and is played | The cast |
|:---:|:---:|:---:|
| ![](../../assets/wonderboy/stage1-start.png) | ![](../../assets/wonderboy/stage1-walk.png) | ![](../../assets/wonderboy/sprites.png) |

`boot_load_stage` ($e5ba..$f8b4) is the fourth slice and the longest: the level-sequence row, its
overlay, `TILEDATA.RAD` through `bg_tile_install`, `SPRITES.CRU` through `sprites_cru_install`,
the actor tables, and `stage_load_window`, which fills the scroll engine's **eight pre-shifted
copies** of the visible window. Everything after that is the frame loop's own fifteen calls, run
whole and in its order: the two keyboard ones, then the round bonus, then `panel_refresh_frame`
over `hud_draw_lives`, `hud_draw_meter` and the rest, the scene driver, and
`game_latch_input_and_step_actors` — which is where the joystick edge and every actor's behaviour
happen. Then the drawing: `project_followed_actor`, `bg_scroll_run_queue`, `project_actor_list`,
`bg_scroll_blit` — whose sixteen straight-line bodies, `bg_scroll_copy_x0` through `_x15`, differ
only in where each splits its thirty `move.l`s about the source row's 128-byte ring seam —
`game_snap_follow_cursor`, `sprite_draw_pass` and the twelve blitters it dispatches into
(`blit_sprite_w2`..`w5` and their left- and right-clipping siblings), `actor_spawn_pass`,
`text_run_message_box`, and `flip_screen` last. The middle frame is lap 157 of a fixed joystick
script — walk held, jump on a beat, fire on another — and it is **not a lap number chosen here**:
the run stops at the first frame that draws at least three sprites whole inside the play window,
and fails if none does, so a caption naming what is in a picture cannot go stale under a fix that
shifts the run. What that frame has is the hero in the air between a spinning gold coin and the
tree stump with the shop's door in it, with a red cobra on the ledge ahead beside the arrow sign.
The sheet beside it is the game's own bitmaps at their own addresses, drawn by `sprite_draw_pass`
onto the screen `clear_both_screens` left behind; only the destinations are ours. Which twenty are
shown is not a list chosen here either — it is every sprite that same run actually put into a
screen record, so the sheet is this stage's cast rather than a selection: four green snakes, two
red cobras, four frames of the hero's own walk, the seven-frame spin of a gold coin, and three
boulders.

| Round 4 — over the brick platforms | Round 5 — the wood | Round 5 — the vine shaft |
|:---:|:---:|:---:|
| ![](../../assets/wonderboy/stage4-sky.png) | ![](../../assets/wonderboy/stage5-woods.png) | ![](../../assets/wonderboy/stage5-cave.png) |

The later rounds are reached through **the game's own level-skip cheat**, typed rather than poked:
`game_key_actions`' walk at $5a8 steps a cursor along the four scancodes the binary carries at
$608 — `$61 $30 $13 $1e`, which are UNDO, B, R and A — and raises the cheat word when the cursor
meets its terminator. With that word up, N takes the arm at $556, which pops the frame loop's
return address and `jmp`s to $e5ba: `boot_load_stage` again, one sequence row further on. The
reconstruction cannot make that transfer, so it reports `WB_KEY_ACTIONS_LEVEL_SKIP` and the caller
runs the slice — which is exactly the wiring the on-target build uses for the same ending. One
thing here is this script's own and not the game's: the sequence cursor is put at the row before
the one being shown, because the honest route to round eight — playing there — is not something a
fixed joystick script can do. Everything either side of that is the boot's.

Two things about **which** rounds these are came out of getting the pictures wrong first, and both
are now checks rather than choices. The script takes the walk direction from the loaded row's own
start record: `boot_load_stage` drops the hero at `WB_START_FOLLOW_X`, and two of these rows start
him at 1928 and 1432 — the far end of a map he is meant to walk *back* along, with an arrow tile on
the ground saying so. Holding right there pinned him against a wall for 1400 frames with every
creature off the left edge, which is what the first published desert and castle pictures were. And
`sprites_cru_install` writes an UNMARKED sentinel into every descriptor the **round's** mask does
not mark, wholesale — rounds 2, 3, 10 and 11 do not mark the frames of a hero who has not picked up
the armour of the rounds before him, and arriving with a round-1 hero is exactly what the cheat
does, so in those rounds he was drawn as a band of scrambled bytes at his own position. The town of
round 2 and the golden keep of round 11 were in this gallery until that was found; the set is now
chosen among the rounds the skip can honestly show, and the script refuses a picture whose hero has
no cells.

| Round 6 — the spiked corridor | Round 8 — over the lava |
|:---:|:---:|
| ![](../../assets/wonderboy/stage6-dungeon.png) | ![](../../assets/wonderboy/stage8-lava.png) |

Each is a different overlay file, and each frame was chosen the same way stage 1's was — the first
frames 100…800 with at least a stated number of sprites whole inside the window, asserted before
the PNG is written. So the wood really does have three monkeys in its trees with gold hanging
between them — and a `GOLD` counter reading 16 beside a `SCORE` of 20, both earned by that run —
the vine shaft really has a blue flier, a falling boulder and thrown blades around a helmeted hero
with his sword out, and the lava has three creatures and two more pieces of gold. The message box
every stage entry posts — the frame loop's fourteenth call, `text_run_message_box`, composing the
first entry of the message table at `$a09c` — is long gone by then, so it is checked on the way
past at frame 30 instead of photographed, and checked in both directions: three of these five rows
hold it over frames 0…49 exactly, and two — the vine shaft and the lava — post no message at all.

The panel is the same one in all seven play pictures, and reading it is the quickest way to see
that the boot chain did its work: `LIFE`, `SCORE`, `HIGH`, `GOLD` and the slot frames are the
credits picture's own artwork, while the hearts, the digits and the `RND:` number are what
`game_restart_reset`, `panel_refresh_frame` and the `hud_draw_*` routines paint over it. `RND:` is
also the quickest check on a figure this write-up once had wrong: `WB_STAGE_NUMBER` is packed BCD,
so `$11` is round eleven and not seventeen, and the panel spells the digits out. Four of the data
disk's overlays are damaged on the pressed original — `OVALAY4B`, `OVALAY5B`, `OVALAY6A` and
`OVALAY9A`, the only files this project keeps two corpora of (see [The disks](#the-disks)) — and
every picture here is rendered from the **authentic** `bin/disk2/` dump, with the script refusing
to load one of those four, so no stage that needs them is shown.

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

cd recreate                                  # needs your own bin/disk1/ and bin/disk2/
make venv && make test                       # the shared kit + the C cores, the differential suite
./.venv/bin/python ../gen_readme_assets.py   # re-render this README's images, host-side
bash atari/build.sh ownrun && bash atari/run.sh   # ...or play it on a 68000, under Hatari
python3 atari/smoke.py floppy                # ...or build atari/out/WBOOT.ST — a bootable 720 KB
                                             # FAT12 floppy carrying the build and all 40 resources.
                                             # gw/write_disk.sh puts it on real media; see
                                             # atari/HARDWARE.md for the STE runbook.
```

`names.txt` is the source of truth for every name, addressed at base `0x3F8`. The map, the region
table and the anchor inventory are in [`notes/architecture.md`](notes/architecture.md).
