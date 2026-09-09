# BUBBLE.PRG — the reconstruction on a 68000

Bubble Ghost's 132 verified cores, compiled for m68k and run on a real 68000 under Hatari, judged
against the original binary on the six surfaces of
[`docs/on-target-execution.md`](../../../../docs/on-target-execution.md).

```bash
bash atari/build.sh title            # -> atari/build/BUBBLE.PRG, atari/disk/{c,GHOST.ST}
python3 atari/smoke.py title         # the gate: 9 checks, ours against the original
bash atari/build.sh titlefault && python3 atari/smoke.py titlefault   # control: one colour pen
bash atari/build.sh titlepoke  && python3 atari/smoke.py titlepoke    # control: one image word
bash atari/build.sh titleisr   && python3 atari/smoke.py titleisr     # control: no Timer C
bash atari/build.sh title floppy && python3 atari/smoke.py floppy     # the bootable volume
bash atari/build.sh play  && python3 atari/smoke.py game              # G, then 1: the room loop
bash atari/build.sh play  && bash atari/run.sh                        # for a person
```

**What it does today.** It boots — the crt0, `init_globals`, `main`, the GEM workstation, the six
data files, the digitised speech, the presentation picture, the sprite bank, the sound driver — and
draws the game's own menu. The menu it draws is **byte-identical to the original's**, all 32,000
bytes of it, measured against a `savebin` of the shipped binary's own framebuffer at the same point.

```
-- title on st / TOS104US.img at 1 MB: image base 0x36d00, the original at 0x12596
   memory: TPA [0x12496, 0xf7ff8), kept to 0xe5dc4, image 664 KiB at 0x36d00,
           32964 B headroom, 0 guard byte(s) dirty
   the boot: 6 file opens (1 refused by the disk) + 3 the shim's, 11 Mallocs to 0x6f310,
             68 VDI and 3 AES traps, 354 Timer C ticks
   the speech: GHOST.VOI at image offset 0x3073a, poked into the LOA as 0x6743a
   pens read off the chip, unmasked: 0000 0700 0256 0040 0050 0060 0237 0245
                                     0000 0757 0771 0333 0444 0555 0666 0777
   timelines: power-on to the anchor, ours 30 s and the original's 28 s — REPORTED, not
              asserted: the original's decrypt and this driver's poll for it are in front
              of its number only
   [green] exit status + log
   [green] exit status + log (the fault scan can fail)
   [green] hardware-state vector (the pens when the speech starts)
   [green] hardware-state vector (the pens, $ff8260, the video base)
   [green] memory (the displayed framebuffer, against the original's)
   [green] memory (the program's own record)
   [green] rendered pixels (neither capture is a photograph of nothing)
   [green] rendered pixels (the two captures, byte for byte)
   [green] trap ledger
-- OK
```

**The Timer C tick count is a RANGE, not a figure.** It is `STATE.BIN`'s `TIMER_C_TICKS` at the
hand-back — how many 200 Hz interrupts the run took between `sound_start` and the end of the
anchor's hold — and it lands between **350 and 360** across runs, because the anchor holds for a
count of vertical blanks and the boot before it is a real floppy-and-GEMDOS timeline. `smoke.py`
asserts only that it is **non-zero**, which is the thing with meaning: a run whose sound is silent
because the vector never took is a run whose count is 0, and no screenshot could tell that from a
run whose music has simply not started.

## What is different from the sibling builds

`projects/zynaps/recreate/atari` is the pattern this directory follows — the include-path seam, the
gated `build.sh`, the record, the negative controls — and three things here are not that build's.

**It runs in USER mode.** Zynaps takes supervisor once in `_start` and keeps it. Bubble Ghost is a
GEM application: it makes `trap #2` AES and VDI calls throughout, from the mode TOS expects them
from, and it takes supervisor exactly twice — around the one byte it pokes at `$484`. This build
reproduces that, so `os_super` is the real trap here rather than a no-op. What that costs is that
the three supervisor-only stores the cores make cannot be plain stores: the two YM2149 ports and the
MFP's vector register go through a **`trap #9` gate**, which is not a workaround but *the original's
own mechanism* — `psg_access` @ `0x14940` is a user-mode stub that pushes three words and traps into
the game's supervisor handler at `$a4` for exactly this reason.

**The crt0 really runs.** The differential loads `GHOST_RT.PRG`, the program in its RUN-TIME layout,
because the kit's loader runs no crt0 and this game's crt0 is what rearranges the segments. Here the
crt0 *is* a verified core, so the build stages the FILE layout (`GHOST_PLAIN.PRG`) with a fabricated
basepage below it and runs `crt0_relocate_and_clear` on the machine. Its answer — the globals base
every `n(a4)` in the program is against — is in the record, and the smoke pins it at `0x24f1a`. That
the two layouts agree is not this directory's claim: `test/test_image_model.py` already proves the
crt0 run on a file-layout image equals the run-time layout the harness loads.

**The data files are on a floppy even for the GEMDOS run.** Three of the six are opened as
`"A:GHOST.DAT"`, `"A:GHOST.PRE"` and `"A:GHOST.DEM"` — a hard-coded drive letter in the program's
own DATA segment — so the drive letter is the original's and this build does not patch it. The other
three names carry no drive at all and open on whatever drive the program was started from; that
asymmetry is not visible in the source and was found by the trap ledger of the first run, which
opened `GHOST.LOA` on C: and got `-33`.

## The layout

```
atari/
├── build.sh          the build: one CONTENT gate (git refuses a dirty or untracked core) and
│                     the isolation, codegen and size gates that refuse a wrong .PRG
├── tos.ld            link at base 0; .bss abuts text+data, SUBALIGN(2)
├── mkprg.py          ELF -> GEMDOS .PRG (the workspace's third copy; see its header)
├── gen_image.py      the relocated program image the shim reads back into its array
├── mkfloppy.py       the A: data volume, and the bootable one
├── bubble_os.s       _start, the Mshrink, 29 trap wrappers, the two exception entries and
│                     THE GEM DOOR (`bg_gem_dispatch`, hand-written 68000 since wave 5a)
│                     (the Timer C one calls ../src/asm/sound_tick.S, which is a core and lives
│                     with the cores — see "The one core this build does NOT run")
├── bubble_main.c     the image, the composition of the verified slices, the record
├── bubble_backend.c  the GEM door's three counters, and three libc functions
├── shim_include/     the seam: shadows of the kit's os.h / hw.h / psg.h / string.h, plus tos.h,
│                     bubble_target.h (what the three shim files hand each other) and
│                     bubble_mfdb.h (the one place blit.h's MFDB offsets are pinned to the kit's)
├── smoke.py          the gate: two Hatari runs, nine checks, three negative controls, and two
│                     modes of its own — the bootable floppy, and the G key's room loop
├── profile.py        what a room frame COSTS, ours against the original's, over one window
└── run.sh            the `play` build, with a mouse and sound, for a person
```

## The seam inventory

Every symbol the differential harness models, and what it becomes here. **The seam is the include
path plus one omitted directory** — the kit's own `src/`. No core is edited and no core is left out,
and `build.sh` measures both halves of that: `git` refuses a core that differs from its committed
content or that git does not track at all, and five isolation gates refuse a core that includes a
shim-only header, reads a target-only `-D`, collides with a shim symbol, calls a kit `os_*` helper
this build does not replace, or calls a `hw_*` door it does not define (at a number of call sites
the record's own prediction is built on).

| symbol | what the HARNESS modelled | what the TARGET does |
|---|---|---|
| the seven file calls | a staged-file table in the image, bounds-checked, a bad name refused | real GEMDOS against the drive the program was booted from, **with the model's image bound and its refusal tally restored**. `Fopen`'s MODE cannot cross the seam — the kit's `os_fopen` does not take one — so it opens read-only, which is what every live caller asks for, and a failed `Fwrite` is counted as the alarm |
| the six console calls | one poked keystroke; a blocking read with nothing staged REFUSES | real GEMDOS. The refusal has no counterpart: the machine waits, which is what the program means — and that retires the model gap the whole front end is sliced around |
| `os_ikbd_out` | a ledger entry | real BIOS `Bconout` to device 4 |
| `os_malloc` | the kit's bump arena (`src/os_heap.c`) | the same arena, restated — the blocks are IMAGE OFFSETS, so a real GEMDOS `Malloc`'s answer is not a value any core could use |
| `os_super` | returns the cookie, no privilege change | **the real trap**, and the way back is `bg_leave_supervisor`, which plants the USP itself (class 9) |
| `os_random` | a poked 24-bit constant | real XBIOS `Random`, masked to the same 24 bits |
| `os_pterm` | a ledger entry that RETURNS | the real trap, which does not |
| `os_vdi` / `os_aes` | the kit's software VDI/AES over the image | a real `trap #2`, with the parameter block **translated** — one hand-written 68000 routine, `bg_gem_dispatch` in `bubble_os.s`, which stages the block's five (or six) pointers, patches a raster copy's two MFDBs, traps and puts the image back. See below |
| `os_setscreen` / `os_setpalette` / `os_setcolor` / `os_vsync` | an ordered entry in the OS event ledger, and no image effect | the real XBIOS traps, made where the core makes them. The two screen bases and the palette table are image OFFSETS and are translated |
| `psg_port_write` / `psg_port_read` | an ordered ledger and a register file | the real `$ff8800`/`$ff8802`, through the `trap #9` gate at IPL 7 from user mode. The ISR's own writes no longer come through here at all: `../src/asm/sound_tick.S` writes the two ports itself, which is the original's own shape, so `bg_in_timer_c` is never raised and `psg_untrapped_write` is an unreached branch this build keeps for the argument in `shim_include/psg.h` |
| `hw_write8` | an ordered (address, width, value) ledger | a real byte store through the same gate. Two core call sites, both the MFP vector register — and `build.sh` counts them, because `HW_WRITES` is predicted exactly |
| `os_in_image` | the model's 1 MiB | the same arithmetic against the 664 KiB array that actually exists |
| `OS_SCREEN_BASE` | `0x8000`, XBIOS `Logbase`'s answer | **`0x9e100`** — the one constant this build changes, and the only change to what a verified core computes. See below |
| the Timer C ISR | never entered; the harness drives it explicitly | installed at `$114`, and the vector IS `../src/asm/sound_tick.S` — one routine that saves the register set, runs the original's own transcribed instructions and CHAINS to TOS's own handler rather than `rte`ing, exactly as the original's does. Not the C core, and since wave 6a not a call to anything (below) |
| `image[$a4]`, `image[$114]`, `image[$484]` | ordinary diffable image bytes | **not vectors.** `$114` is seeded from the machine before the installer runs (so it saves something real) and taken by the shim's entry after. `$484` is seeded before `init_gem_and_screens`, mirrored OUT after it — which is the poke that really stops the key click — and mirrored out again by every tick of the ISR, from inside the interrupt |
| `sound_stop` at the hand-back | not run: the harness has no teardown | **run**, so the PSG is really silenced and the MFP's vector register really goes back to software EOI. `$114` and `$484` are then mirrored out the same way the install's were |

### The one core this build does NOT run, and what replaces it

Every row above is a core running as written. **There is one exception, and it is the only one:**
the 200 Hz Timer C handler. `../src/sound.c`'s `timer_c_sound_isr` is still linked into the .PRG,
but nothing calls it — the machine's `$114` vector IS `../src/asm/sound_tick.S`, a hand-written m68k
routine added by wave 5b because the tick runs 200 times a second in a loop that has no Vsync, and
GCC's version of it cost 2,297 cycles against the original's 1,704 with the C already at the
compiler's floor (`../STATUS.md`, "Performance").

**THE FILE HAS TWO ENTRIES AND EACH BUILD ASSEMBLES ONE**, behind `RECREATE_HOST_DIFFERENTIAL` —
kit.mk's own mark for the off-target assembly of a twin. Off target it is
`timer_c_sound_isr_asm(uint8_t *image)`, the C signature the differential runs against the core.
On target it is `bg_timer_c_entry`, the vector itself: the tick count, the image base, the body, the
`$484` mirror and the chain, in one routine with no call in it. Wave 6a folded it that way and the
glue outside the body went 356 cycles a tick to 260.

**It is a TRANSCRIPTION, not a translation**, and that is what makes the substitution safe to make
at all: 792 of its 856 bytes are the original binary's own 0x145be..0x148d6, byte for byte, and the
64 that are not are the prologue, the two image-relative pointer loads and the epilogue — the
places where a C function on a based image cannot be a vector handler on absolute memory.
`../src/asm/sound_tick.S`'s header lists all four differences and says why each one is one.

**Three pins hold it, and the build refuses without them:**

| what it says | where |
|---|---|
| the twin leaves the image and the PSG ledger exactly where the C core leaves them, over every case the C core is verified on | `../test/test_sound_asm.py`, called from `test_sound.py::isr_case` |
| the 792-byte body IS the original's machine code | `test_asm_body_transcribes_the_original` |
| the constants it restates (`u`-suffixed C the assembler cannot parse) hold their headers' values | `../test/test_constants.py::test_asm_twin_equates_match_the_headers` |
| the linked .PRG's `$114` vector IS the twin: its routine calls nothing, contains the transcribed body's own label, saves and restores `%d0-%d3/%a0-%a3`, pushes TOS's chain first and mirrors `$484` at the core header's own address | `build.sh`, over `bubble.dis` — five checks, because none of this is reachable by any differential |
| the object about to be LINKED carries the same 792 bytes the host blob was verified over | `build.sh`, via `asm_twin_ships.py` — the `.S` is assembled twice and the `#ifdef` above is the only thing that may differ |

The first of those needs no callback door and no second model of the chip: the twin writes
`$ffff8800`/`$ffff8802` with the original's own `move.b` pairs, and the kit's oracle decodes those
two ports in its memory callback — so off target the twin's register writes land in the oracle's PSG
ledger while the C core's land in the candidate's, and the suite compares the two streams. **One
spelling serves both builds INSIDE THE BRACKET**, chip writes included, so what the differential runs
there is instruction-for-instruction what the machine runs; the `#ifdef` is the entry and the
epilogue and nothing else, and the last pin above is what holds the two assemblies to that.

### The one constant this build changes, and why it has to

`xbios_trap_call` (`../src/frontend.c`) answers XBIOS `Logbase` with the kit's `OS_SCREEN_BASE`,
from inside a verified core with no `os_*` door under it — so the shim's `os.h` redefines the
constant. It is not taste. The program carves `screen_back = Logbase - 32000` and then the room
staging area another 25,600 bytes below that, so a Logbase of `0x8000` puts the staging area at
`-0x6100` and every stage-to-screen copy reads from four gigabytes up. Off target that is harmless
because every battery **stages the two screen pointers** rather than taking them from
`init_gem_and_screens`' output (`../STATUS.md`'s "Model gaps" says so in those words); on target the
boot really runs that routine.

### What a real trap loses, and what is put back

A seam that swaps a modelled call for a real one drops the model's CONTRACT along with its
implementation. Two halves of the kit's file helpers are restored in `shim_include/os.h`, and each
keeps a count the record publishes and `smoke.py` asserts — a restored guard with no surface is a
guard nobody can watch fire.

* **The image bound.** `os_fread` copies through `os_in_image(buf, count)`, written as a subtraction
  so a large count cannot wrap it. Unguarded on target, GEMDOS writes those bytes into whatever
  follows the image in `.bss` — the record among them, which is the shape that tears down cleanly
  with every read-back green.
* **The refusal tally.** This program's C library hands a failed open straight on: `c_open` files
  Fopen's answer in `c_errno` and returns -1, and the four picture loaders read into whatever
  `c_malloc` gave them regardless. A data file missing from the drive leaves a buffer of zeros and
  draws a black screen with nothing saying why. The tally says why, and the smoke predicts it
  exactly: **6 opens, 1 failure** — `A:GHOST.SCR`, the hall of fame, which does not exist on a fresh
  disk and does not exist on the original's either.

### The GEM door, and the pointers it translates

The game's own bindings put IMAGE OFFSETS in their parameter blocks: `vdi_pblock`'s five array
pointers, the AES block's six, the two MFDB addresses in `contrl[7..10]`, and the raster pointer
inside each MFDB. That is exactly right in the differential's world, where the image IS the
machine's memory and starts at 0, and exactly right on the original, whose arrays are absolute
against the base it runs at. Here the VDI would take `0x236f0` for an address and read its `contrl`
out of the 68000's vector page.

`bg_gem_dispatch` is the translation, and it does two different things with the two kinds of
pointer. **It is hand-written 68000** (`bubble_os.s`, "GEM (trap #2): the whole door") because a C
door cannot keep a value in a register across a `jsr` to a routine that traps: every live value went
through the stack frame, and the door cost 8,493 cycles a frame for ~1.7K of actual work. That file's
header comment carries the register map and the argument; "Performance" below carries the
measurement. `bubble_backend.c` keeps only the three counters the record publishes — in C, so that
the width the assembly's `addq.l` assumes is pinned by a `_Static_assert`.

**The parameter block is RESTATED, not patched.** The trap is handed `bg_gem_staged_pblock`, a block
of the shim's own holding the same five (or six) pointers translated — so the VDI still reads its
operands out of, and writes its answers into, the game's OWN arrays, with no copy back and no field
this door has to know the meaning of, and the image's block is never touched at all.

**A raster copy is still patch-trap-restore**, because two of its operands are reached by
DEREFERENCING the image rather than by being handed over: `contrl[7..10]` names two MFDBs and each
MFDB names a raster. Those four longwords are patched in place and put straight back, so the image
the cores read afterwards holds what it held before. `fd_addr == 0` is left at 0, because that is the
VDI's "the screen" and TOS substitutes the logical base `Setscreen` was given — which for this
program is `screen_back`.

**The eleven numbers the door is built out of are the kit's and the cores'**, not the shim's:
`GEM_VDI`/`GEM_AES`, the four `contrl` indices, `VDI_VRO_CPYFM`, `MFDB_ADDR`, `MFDB_SCREEN_ADDR` and
the two block lengths come from `tools/recreate_kit/include/os.h`, and `A_vdi_contrl` from
`../include/frontend.h`. In assembly they are immediates where they used to be macros the compiler
resolved, so `build.sh`'s two-language loop scrapes every one of them back out of the header that
owns it and refuses a disagreement — and the assembler itself refuses a `MFDB_SCREEN_ADDR` that is
no longer 0, which is what the door's `beq` tests for.

Until 2026-09-07 both halves were patch-trap-restore, and each MFDB was COPIED into the shim's memory
so its `fd_addr` could be translated. That copy cost more than everything else in the door put
together: `g_src_mfdb` was a `uint8_t[]`, GCC knows a byte array's alignment is one, so each `wr32`
through it became four byte stores and the 20-byte copy became a byte loop. "Performance" below has
the before and the after.

## The XBIOS group's seam, and the deviation it replaced

Until 2026-09-06 this section said the group had NO seam, and it was this build's largest deviation.
`xbios_trap_call` (`../src/frontend.c`) swallowed **Setscreen, Setpalette, Setcolor and Vsync** as
the model's `return 0` — inside a verified core with no `os_*` call under them, so no include-path
seam could reach them — and `bubble_main.c` reissued the ones the picture depends on at the
composition boundary FOLLOWING the slice that would have made them. Two of the four were not
reissued at all.

**A person found what that cost, and no check here could have.** The presentation picture was in the
DESKTOP's colours for the whole length of "Welcome to Bubble Ghost": `show_presentation` loads
`GHOST.PRE`'s palette and `game_top_loop`'s very next instruction is the `jsr` into `GHOST.LOA`, the
second program that plays the digitised voice — so the reissue could not happen until the voice had
finished. Every surface in this directory was green, because the only anchor was seconds later.

The kit now gives the group four doors (`os_setscreen`, `os_setpalette`, `os_setcolor`, `os_vsync`;
`tools/recreate_kit/TRAP_MODEL.md`, Phase 14). Off target each is an ordered entry in the OS event
ledger and still touches no image byte, so the differential is unchanged in what it compares about
memory and gains the calls themselves; here `shim_include/os.h` shadows all four with the real
traps. Each call is therefore made where the original makes it, and:

| call | what it does now | what it cost while it had no door |
|---|---|---|
| `Setscreen` | the real trap, both bases translated from image offsets | the base moved at a slice boundary rather than mid-slice |
| `Setpalette` | the real trap, the table translated | a freshly shown picture was in the DESKTOP's colours until the slice returned — for the presentation, the whole of the speech |
| `Setcolor` | the real trap. **Three of its five sites were not in the C at all** — the sixth defect below | the ghost did not change colour when its breath ran out |
| `Vsync` | the real trap | the attract slideshow ran at renderer speed |

**The surface under the palette row is new too**: `smoke.py` breaks at the instant the LOA is
entered, on BOTH sides, and asserts the sixteen colour registers there are `GHOST.PRE`'s own
palette. See "the anchors" below.

## The six defects this build shipped, and what found them

All six are worth reading before the next on-target build in this workspace, because none is
visible in any source and each looks like something else. The first two crashed or blanked the
machine; **the last four were silent, and the surfaces that eventually caught them did not exist
until they were built** — which is the more useful half of the lesson. The last two were not found
by a check at all: one by a person playing the game, and one by the kit door that person's report
led to.

**1. The trap #9 gate was installed where the GAME installs its own, which is one instruction too
late.** `install_sound_vectors` writes `image[$a4]` — an image byte — and the same routine's very
next line is `hw_write8(MFP_VECTOR_REG, …)`, which on target IS a `trap #9`. So the first use of the
gate happened inside the routine that was supposed to install it, and with TOS's own `$a4` still on
the vector that trap reached the ROM's exception handler: bombs, `Pterm(-1)`, and a GEMDOS ledger
that looked perfect right up to the last call. The gate is a property of this build's user-mode
choice, not of the game's boot, so it goes in before any core runs.

**2. The program never `Mshrink`ed, and TOS'S OWN VDI ran out of memory.** GEMDOS hands a `.PRG` the
whole TPA and expects the program to give back what it does not need; this one's `.bss` is a 664 KB
image, so without the shrink it owned every free byte of a 1 MB machine. `v_opnvwk` allocates its
virtual workstation with GEMDOS `Malloc` — 308 bytes, from ROM PC `$fd0622` — got 0, and answered
**workstation handle 0**. Every later VDI call carried that handle and drew nothing at all, so the
menu's four text lines, the sprite grabs and the HUD were silently absent *while the AES, the file
I/O, the sound engine, the crt0 and the reconstruction's own raw blitters all worked perfectly*. The
visible screen was black and every check the program made of itself was green.

What found it was **the original**, run under the same emulator with the same ROM: its `v_opnvwk`
answers handle 2 where ours answered 0, from a `contrl` array that was identical going in. The
general rule the workspace already has (`docs/on-target-execution.md`'s "measure the original, do
not reason about it") earned its keep here in about ten minutes after an hour of hypotheses.

**3. The speech player was handed an image OFFSET where it wanted a machine ADDRESS.**
`play_voice_arm` pokes `voi_buffer` into the loaded `GHOST.LOA` at `+0x1e`; that value comes from
`os_malloc`, which answers offsets, because a core indexes a flat image and could not use an address.
The shim translated the LOA's *entry* for the `jsr` and not the pointer, so on target the second
program dereferenced an offset and read its samples out of the machine's own low memory. **Every
check stayed green**: the harness runs with `--sound off` and nothing in this build listens to the
PSG. The record now carries `VOI_BUFFER_OFFSET` and `VOI_POINTER_MACHINE` and the smoke asserts the
second is the first plus the image base — which is arithmetic, not audio, and is all this build can
honestly claim (`../STATUS.md` says so where it used to say the LOA "runs the second program").

**4. The `$484` mirror was a no-op that read like a mirror.** `init_gem_and_screens` clears TOS's
key-click byte inside a real `Super` bracket — but what a core can clear is `image[$484]`. The shim
seeded the image byte from the machine *after* that routine ran, which threw the clear away, and
then poked the machine byte back onto itself. Three moving parts, all present, all in the wrong
order, and `CONTERM_AT_ANCHOR` sat at TOS's own `7` from boot to hand-back with every check green.
What found it was **adding that field to the assertions**: the record already carried the number and
nothing compared it. The seed now runs before the routine, the mirror after it, and every tick of
the ISR mirrors its own write from inside the interrupt.

**5. The presentation played its whole voice in the DESKTOP's palette.** Not found by anything here:
a person ran `bash atari/build.sh play && bash atari/run.sh` and said so. `show_presentation`'s
`Setpalette` was swallowed inside a verified core, the shim's only place to reissue it was after the
slice — and the very next instruction of that slice is the `jsr` into `GHOST.LOA`, which plays about
a second and a half of digitised speech. So the reissue was, exactly, the length of the voice late.
Every surface in this directory was green, because the only anchor was the menu, seconds later.

The fix was a KIT DOOR for the XBIOS video group, not a change here (the section above; `TRAP_MODEL.md`
Phase 14), and the surface that keeps it fixed is a second anchor: `smoke.py` breaks at the instant
the LOA is entered on BOTH sides and asserts the sixteen colour registers are `GHOST.PRE`'s own
palette. It went from a defect nobody could see to a check that compares three things — our chip,
the original's chip, and the shipped data file.

**6. Three `Setcolor` calls were not in the reconstruction at all**, and the door found them the
first time it ran. `frame_blow_or_recover` (twice) and `frame_death_sequence` file the trap
trampoline's three save slots and made no call — so the ghost never turned pink when its breath ran
out and never went back to white. Forty-five differential cases went red the moment the group became
an ordered event, and were green again once the three `os_setcolor` calls were written. **They had
been green for the whole life of the project**: the only difference was off-image, which is the one
thing a byte diff cannot see and is precisely what the ledger is for.

## The six surfaces, and what each one measured

`python3 atari/smoke.py title`, TOS 1.04, both sides at 1 MB on the same machine settings.

| surface | what it compared | result |
|---|---|---|
| **exit status + log** | Hatari's return code and its own `Bus Error`/`Address Error`/`CPU halted` lines on BOTH sides, read from the log; the emulator kept running three seconds past `Pterm`; and the program's own `STATE.BIN`, complete to its `'DONE'` tail | clean. The scan's own control proves on every run that it can still go red — and it spells the markers with a **capital E**, because Hatari 2.6.1 does and the shared list in `tools/hatari_headless.py` does not |
| **memory** | the 32,000-byte displayed framebuffer, written by the program from `image + screen_phys`, against a `savebin` of the original's own `screen_phys` | **byte-identical** |
| **memory (the record)** | EVERY field of `STATE.BIN` against what the boot owes: the crt0's `a4`, the `Getrez` read at entry, the Mshrink's answer and the top it kept, `PROGRAM_BYTES` against the staged file's own size, the image's base (256-aligned) and extent, the two screen offsets against `Physbase`/`Logbase` read back, 6 file opens and 1 refusal plus the shim's own 3, 11 Mallocs and where they left the arena, 68 VDI and 3 AES traps, 60 raster copies, 2 MFP writes, the two vectors landing INSIDE this program's TPA, the speech pointer against the buffer it was translated from, a `$484` of 0, a clean guard band, and the TPA the size gate weighs against | all exact. The TPA figure is a MEASUREMENT pinned on every 1 MB run — the first draft carried Zynaps' number and was 8 bytes out |
| **hardware-state vector** | the sixteen colour registers, `$ff8260` and the video base read off the chip by the DEBUGGER **at both anchors**, ours against the original's; and `Physbase`/`Logbase` read back against what the shim published | pens identical, `$ff8260` = 0 (low res) on both sides, and the read-back equals the published address — so it was 256-aligned and nothing was truncated |
| **hardware-state vector, at the VOICE anchor** | the sixteen colour registers at the instant the `jsr` into `GHOST.LOA` is made, on BOTH sides, against `GHOST.PRE`'s own sixteen colour words read off the shipped file | identical on all three. It is the surface defect 5 did not have |
| **trap ledger** | `--trace gemdos`: our `Fopen`/`Fread`/`Fclose` sequence against the original's, minus the shim's own four files and TOS's `DESKTOP.INF`, with the buffer address and the handle deliberately dropped — **and by LENGTH as well as content**, because a prefix comparison is green on a ledger missing its tail | identical, call for call, and the same number of them |
| **rendered pixels** | a Hatari screenshot of each side, byte for byte, with `--frameskips 0 --statusbar off --drive-led off` and stop-then-shoot | **byte-identical** |
| **timelines** | power-on to the anchor, on both sides | **reported, not asserted** — 30 s ours, 28 s the original's on this host. BOTH anchors are moments now (see below), but the two runs do not start together: the original's own decrypt, and this driver's polling of RAM for it, are in front of its number and not in front of ours. Saying so is more useful than a check that looks like coverage |

## The anchors, and why none of them is a clock

`BASE.BIN` is the shim's ANCHOR TABLE — one longword per slot of `bubble_main.c`'s
`enum bg_anchor_slot`, written before anything else the run does, so `smoke.py` can arm its
breakpoints on a program that then crashes. Three of the slots are addresses to break on
(`bg_anchor`, `enter_the_voice_player`, `game_frame_update`), one is where a counter lives and one is
where the image landed. The two files agree by the SLOT COUNT being asserted on both sides, exactly
as the record's fields do.

**The voice anchor** is the second of them and the one defect 5 needed. Ours is
`enter_the_voice_player`, the `jsr` into `GHOST.LOA` given a function of its own so it has an
address; the original's is that same `jsr` at `0x10232`. Both sides settle two vertical blanks —
XBIOS `Setpalette` is DEFERRED, so TOS loads the sixteen registers from its own VBL handler and a
dump taken AT the breakpoint can read the frame before — and then dump the chip.

**The menu anchor.** Ours is `bg_anchor`, a `Vsync`-paced hold the shim enters once the menu is
drawn; its runtime address is in the table, so `smoke.py` can arm a breakpoint on a
program that then crashes. **The original's** is `menu_read_key_and_fold` @ `0x116c4` — the slice
boundary immediately after `title_menu_open`, where the shipped program has drawn the same menu and
is about to block on a key it never gets. So the two are *the same place in the same program*, and
the picture comparison is a comparison of two programs at one moment rather than of two waits.

The original's PC is not knowable in advance: its `.PRG` is encrypted against the protection track
and decrypts itself into RAM, so the driver polls RAM for the plaintext (`locate_by_signature`, the
same recipe as `../../tools/boot_ghost.py`) and every Ghidra address is then that load base plus an
offset. **The first draft waited 26 s by the wall clock instead**, and the vblank counts it reported
as "timelines" were a measurement of that wait. `--run-vbls 12000` (~240 s of emulated time) is a
hard cap and not a schedule: the original is the slower side and reaches its anchor in about 27 s,
so the cap is roughly seven times the run it has to survive.

## The three negative controls

Each is the title build with **one** thing wrong, and each names the surfaces that must go red for
it. Every other check must stay green under every one of them: a control that only required
"something failed" would pass on a build that crashed. Each also publishes its own argument in
`STATE.BIN`, so `smoke.py` refuses to grade a control mode against a shipped `.PRG` that carries no
fault — `the fault is the one claimed` is that refusal, plus the arm that says the fault could
actually move the surface it is aimed at.

| mode | the one fault | must go red | must stay green |
|---|---|---|---|
| `titlefault` | pen 15 read back off the chip and stored **XOR `$007`** — white to yellow. One register, no memory touched | the hardware-state vector; the two captures | the framebuffer, the record, the ledger — and *neither capture is blank* |
| `titlepoke` | one word of the staged program XORed after the crt0 placed it: `A_text_menu_game`, the first menu line's text. Two glyphs move | the displayed framebuffer against the original's; the two captures | the pens, the record, the ledger |
| `titleisr` | the sound engine installed in the image and **not** on the machine's `$114` | the record: `TIMER_C_TICKS` is 0 and the vector at the anchor is still TOS's | everything else — the menu draws identically without a tick |

```
-- titlefault on st / TOS104US.img at 1 MB
   pens read off the chip, unmasked: ... 0666 0770
   [red ] hardware-state vector ...                                     (must FAIL)
           pen 15 is 770 on the chip and the original's is 777
   [green] memory (the displayed framebuffer, against the original's)   (must PASS)
   [green] rendered pixels (neither capture is ... nothing)             (must PASS)
   [red ] rendered pixels (the two captures, byte for byte)             (must FAIL)
           the two captures differ
   [green] the fault is the one claimed                                 (must PASS)
-- OK
```

**The pen control needed three controls of its own.** All three drafts were vacuous, in three
different ways, and each is worth recording:

* **The fault never reached the chip.** XBIOS `Setpalette` is DEFERRED — it parks the block's
  address in TOS's `_colorptr` and TOS's own vertical-blank handler loads the sixteen registers a
  frame later — so a `Setcolor` made immediately after one is overwritten. The pens read back
  unchanged and both colour-sensitive surfaces reported green under a fault that was never there.
  The injector now waits a `Vsync` first, inside the fault arm, so the shipped build's timing is the
  original's.
* **The fault landed on a pen no pixel uses.** The menu text is drawn with `vst_color(handle, 1)`,
  and the VDI's colour 1 is WHITE — which in ST low resolution is hardware register **15**. Faulting
  register 1 moved the chip's state and left the rendered picture byte-identical. `smoke.py` now
  asserts that the faulted pen is one the picture actually draws (`the fault is the one claimed`),
  so the arm cannot go back to being vacuous quietly.
* **The fault blanked the screen, so the picture comparison never ran.** The XOR was `$777`, which
  took the menu's only ink colour to black; a capture with one colour is a photograph of nothing and
  `smoke.py` rejected it *before* comparing the two pictures — so the check that reported a
  satisfying red was the blank-capture guard, and `same_picture` was never called under any control
  at all. The XOR is now `$007` (white to yellow), and "neither capture is blank" is a check of its
  own that must stay GREEN in every mode, including the controls.

## The bootable floppy

`bash atari/build.sh title floppy` writes `atari/disk/BUBBLE.ST` — a 720 KB FAT12 volume with the
`.PRG`, the staged program image, the five data files and a `DESKTOP.INF`, written by
`tools/st_build.py` and read back by `tools/st_extract.py`'s parser, file by file, byte for byte. It
boots TOS 1.04 to its desktop with no fault of any kind, and the game is started by
**double-clicking it** — which is how the original's own disk is started.

**`python3 atari/smoke.py floppy` is the surface under that sentence**, and until it existed the
sentence was a claim with nothing behind it. It boots the volume in A: with no `--auto`, waits for
the desktop to `Fopen` the `DESKTOP.INF` *on the disk* (which is what mounting it as a filesystem
means), and then asserts the emulator exited 0, that Hatari logged no fault, and that the capture is
a picture rather than a blank screen.

**It corrected this section on its first run.** The sentence used to say the disk came up "with a
window open on `A:\`", from the `#W` line in the original's own `DESKTOP.INF`. It does not: the
capture is the desktop with its two drive icons and the trash and NO directory window, at three
seconds after the read and at fifteen. TOS 1.04's desktop reads that line and does not act on it,
just as it reads a `#Z` autostart line and does not act on it — so the game is two double-clicks
away, the drive and then the `.PRG`. What the check still cannot do is make either of them: Hatari's
control protocol has six events and no mouse motion of any kind, which is "Unpinned" item 4.

**Two ways to autostart were tried and both are measured failures**, and they are recorded because
the second is not obvious:

* `\AUTO\BUBBLE.PRG` — TOS runs an AUTO-folder program **before GEM exists**, and this is a GEM
  application whose second act is `appl_init`. The run reached nothing at all: no record, no first
  file, and a disk that came back carrying only what was written on it.
* a `#Z 01 A:\BUBBLE.PRG@` line in `DESKTOP.INF` — TOS 1.04's desktop READ the file (its `Fopen` is
  in the GEMDOS trace) and made no `Pexec`. That line is a later desktop's.

## The `game` mode — the G key, and the room behind it

`bash atari/build.sh play && python3 atari/smoke.py game` is the first check in this directory that
PRESSES A KEY. It exists because a person reported that pressing G on the menu returned them to the
desktop, and nothing headless had ever pressed one: `smoke.py title` stops at the menu deliberately,
one instruction before the blocking read.

It drives both binaries the same way — wait for the menu, then send `G` and `1` until a room opens —
and judges three things: that neither program is gone when the run is stopped, that neither machine
faulted, and that ours ran at least ten frames of `game_frame_update`. **Both waits are on the
program's own state, never on a delay**: `bg_play_tally` is two longwords in the shim (menus opened,
room frames run) and the driver reads them out of the running machine through the debugger. It
refuses a `title` .PRG rather than grading one, the way the negative controls refuse a shipped
build.

At the room's first TWO frame calls — deterministic moments on both sides, with the mouse untouched
because nothing headless can move it — it compares the 32,000 displayed bytes against the
original's, at each, and the sixteen colour registers once, off the settle after the second.
**All of it is byte-identical**, which makes this the second place in this directory where the two
programs' memory is compared and the first inside the game.

**THE SECOND ARRIVAL IS THE ONE THAT PINS THE GEM DOOR**, and it is why there are two. At the first,
the room has been composed and `game_frame_update` has not run once, so no `vro_cpyfm` has reached
the displayed screen and the MFDB raster translation in `bubble_os.s`'s `bg_gem_raster_copy` is
invisible — two mutations of it survived this mode AND `title` (`../STATUS.md`). One whole frame
later — `save_sprite_backgrounds`, `draw_sprites`, `present_room`, `restore_sprite_backgrounds`,
`objects_animate_and_draw` — the framebuffer carries the ghost and the bubble as the VDI drew them
through that door, and deleting the source raster's translation now reddens it by 414 bytes. The
second breakpoint is `b pc = $room_pc :2 :once`: Hatari's `:<count>` is "break only on every
`<count>` hit", it rejects an explicit `:1`, and two breakpoints on one PC keep their own hit counts
so the pair fires on consecutive arrivals (measured on 2.6.1). **The two captures are asserted to
DIFFER** on each side — 361 bytes, the ghost and the bubble — because a second capture equal to the
first is not a second arrival, and would compare the same pre-`vro_cpyfm` moment to itself and pass.

**THE FRAMEBUFFERS ARE DUMPED AT THE BREAKPOINTS AND THE PICTURE FOUR BLANKS LATER**, and the split
is what makes the comparison mean anything. Memory is exact at the instruction; the DISPLAY surface is
built scanline by scanline and needs the settle (class 8). Four blanks is four more frames of the
room loop, and the ghost and the bubble are ERASED AND REDRAWN every one of them — so the first
draft, which dumped memory after the settle like the picture, compared two runs on opposite sides of
that cycle and reported 556 of 32,000 bytes differing. Those 556 bytes were the ghost.

**AND BOTH KEYS ARE RESENT UNTIL THE ROOM OPENS.** A single `G` then `1` at a fixed gap failed three
runs in four: `menu_ask_player_count` ends with a console flush, so a `1` sent while its two lines
are still drawing is eaten by the program's own drain, and a `G` that arrives before the program
reaches its `Cnecin` is not there when the read happens. The pair is safe to repeat on every screen
the program can be on, which is why the loop sends both.

**WHAT IT DID NOT DO IS REPRODUCE THE DEFECT.** The G path is green here across every configuration
it was tried in — sound on and off, trace on and off, one player and two, up to sixty seconds inside
the room — so the reported "returns to TOS" is not in anything this mode can reach. What this mode
CANNOT reach is the mouse, which is most of Bubble Ghost's input: the ghost follows it, and Hatari's
control protocol has no mouse-motion event of any kind. That is where the remaining suspicion sits,
and it is written here as an open question rather than as a closed one.

## Performance — `atari/profile.py`, and the first measurement

The room loop has **no Vsync and no wait of any kind** (`notes/gameplay.md` §2), so it turns at the
renderer's speed: the game's pace AND its mouse-to-screen latency ARE the frame cost, and the target
is parity with the original's cycles per frame rather than a budget to come in under.

**WHERE THE MERGE OF WAVES 5a+5b+5c LEAVES IT — MEASURED, NOT ADDED UP: 473.6K cycles a frame,
16.94 fps (282 frames in 1000 vblanks), x1.014** of the original's 466.9K / 17.18, both sides
profiled back to back in one session on the merged tree at `7a2d648` (2026-09-08); the 200 Hz tick
is **1,844 cycles a tick against 1,697, x1.09** in the same window. The three waves' own windows
were 482.2K, 476.8K and 482.2K, each in its own worktree against its own baseline — which is why
this row exists rather than a sum. **The remaining gap is 6.7K a frame.**

**AND WHERE THE MERGE OF WAVES 6a+6b LEAVES IT — MEASURED THE SAME WAY: 470.4K cycles a frame,
17.05 fps (284 frames in 1000 vblanks), x1.0075** of the original's 466.9K / 17.18 (286 frames), two
back-to-back windows on the merged tree at `7cfbfcf` (2026-09-08) reading 470.4K both times, the
tick 1,750 and 1,755 a tick against the original's 1,700. **The gap is 3.5K a frame, about twice
the instrument's spread**, and it is the GEM door's translation (~6.7K, which the shipped binary
does not do) less the leads the port holds elsewhere — the copy runs, the collision probe and the
sprite protocol are each under the original's own cost. Every smoke was green on this tree:
`title` 9/9, the `titleisr` control red as designed, `game` 3/3 at both room-frame arrivals.

Every wave below reports its OWN window against its own baseline — wave 2's is 809.2K, waves
3a and 3b's is 517.4K, wave 4's is 489.1K, wave 5a's is the saved 483.8K — so a figure quoted
mid-section is that wave's and not this one, and the first measurement below is the pre-wave-1 table
rather than the current cost. **This instrument's own spread is 0.3%** (four windows of one binary
in one session read 485.6K three times and 487.1K once), so a change worth less than that is an
objdump claim and not a profiler one.

**WAVE 4 SAID THE CAMPAIGN STOPPED HERE unless something changed shape, and wave 5a changed the
door's.** Its 18.6K was two rows: the shim's GEM door at 8.4K, which the shipped binary has NO
counterpart for because its parameter block already holds machine addresses, and the 200 Hz tick at
8.0K. The door is now 6.7K, one hand-written 68000 routine, and what is left in it is priced line by
line in `../STATUS.md`'s wave 5a — the five-slot restatement and the two MFDBs' patch and restore are
3.8K a frame of work the original never does at all.

```
python3 atari/profile.py ours            # builds the play .PRG, profiles one room's window
python3 atari/profile.py original        # boots the shipped disk, profiles the same window
python3 atari/profile.py compare         # reads both .json files back and ranks the difference
python3 atari/profile.py frames ours     # the per-frame cost itself, over the same window
python3 atari/profile.py frames original
```

Both sides are driven exactly as `smoke.py game` drives them — wait for the menu, send `G` and `1`
until a room opens — and the window is then 1000 vblanks of Hatari's CPU profiler, opened at the
FIRST arrival at `game_frame_update` and closed from inside that breakpoint's own action file. A
frame is a COUNT, not an estimate: the arrivals at that one routine, which is one room frame on
either side. **Because profiling stops on every debugger entry, the host may not issue a single
`hatari-debug` command between arming the window and the dump landing** — so "the room is open" is a
marker file the window's own script writes, and the two keys (which are `hatari-event`, not debugger
entries) are the only thing the host does after that. `profile.py`'s header carries the rest.

**THE MACHINE IS AT 60 Hz, NOT 50.** `hatari_arguments` boots TOS104US on an RGB monitor, which is a
508 x 263 = 133,604-cycle video frame; the first window measured 133,545 cycles a vblank (0.04%
off), where a 50 Hz frame would have been 160,256. Assuming the wrong one is a 20% error on every
fps, so `refuse_a_window_of_the_wrong_length` keeps that measurement as a check.

### The first measurement (2026-09-07, `play` build at -O2, TOS 1.04 US, 1 MB, mouse idle)

| | ours | the original | |
|---|---|---|---|
| frames in 1000 vblanks (16.65 s) | 165 | 286 | |
| **fps** | **9.91** | **17.18** | x0.58 |
| **cycles/frame, whole window** | **809.2K** | **466.9K** | **x1.73** |
| cycles/frame inside `game_frame_update` | 48.0K | 31.4K | x1.53 |
| `frames` mode: median / p90 / max | 813.3K / 836.8K / 860.1K | 466.5K / 478.7K / 502.8K | |
| `frames` mode: vblanks a frame (median) | 6.09 | 3.49 | |
| `frames` mode: fps off the frames' own cycles | 9.90 | 17.18 | |

**The two instruments agree to 0.1%** — the profiler's window average against the per-frame clock's
mean — which is what makes either of them worth reading.

**Where the 342.3K a frame goes.** `compare`'s ranked table, inclusive cycles per frame:

| function | ours | the original | over | x |
|---|---|---|---|---|
| `present_room` | 412,937 | 139,959 | **+272,978** | 2.95 |
| `game_frame_update` | 47,956 | 31,441 | +16,515 | 1.53 |
| `save_sprite_backgrounds` | 105,602 | 90,150 | +15,452 | 1.17 |
| `restore_sprite_backgrounds` | 113,597 | 98,349 | +15,248 | 1.16 |
| `draw_sprites` | 107,319 | 92,344 | +14,975 | 1.16 |
| `fp_dispatch` | 18,524 | 8,147 | +10,376 | 2.27 |

**A ROW IS ONLY A RATIO WHERE BOTH SIDES WERE CHARGED,** and `compare` now prints the rest under
their own heading rather than ranking them. Hatari attaches cycle totals to SUBROUTINE arrivals
alone, so a routine the two binaries ENTER DIFFERENTLY carries a full total on one side and almost
none on the other. `timer_c_sound_isr` is the measured example: both sides tick 3,329 times in the
window, ours reached by a `jsr` out of `bg_timer_c_entry` and the shipped one straight off its
autovector — of which Hatari charged 21. Ranked as a ratio it read **x81 and second in the table**;
the original's ISR cost is not in that row at all, it is spread through the exclusive totals of
whatever the interrupt landed in. `objects_animate_and_draw` is the same class the other way (theirs
10,692 a frame, ours branch-entered and charged nothing). Ours costs 88.4K a frame through
`bg_timer_c_entry` (through `bg_timer_c_tick`, the C half wave 4 deleted), 10.9% of the window,
and **the original's is unmeasured by this instrument**.

`game_room_frame_tail` has no shipped row for the same reason: it is the branch-entered slice
`[0x10792, 0x108d2)` of `game_top_loop`, so ours' 760.6K a frame stands alone.

**What each side has that the other has no name for**, exclusive (inclusive totals nest, so they
cannot be summed over a set) — and this is **not** a shim budget, because the two maps are not
equally fine (ours is the linked ELF at 447 names, the shipped side's is `../names.txt` at 133):

* named only in OUR map — 24 symbols, **350,474** cycles/frame: `bg_gem_trap` 268,459,
  `bg_gem_dispatch` 23,373, `game_room_frame_tail` 14,290, `step_swept_envelope` 11,748,
  `step_triangle_lfo` 9,566. The last three are ported GAME code our source named more finely, not
  shim.
* named only in `../names.txt` — 11 symbols, **291,626** cycles/frame: `vdi_call` 280,100, which is
  the real ROM VDI and 60% of the shipped window.

So **the raster engine is at parity**: `bg_gem_trap` is our own `trap #2` into that same ROM VDI, at
268K a frame against its 280K. The gap is elsewhere, and it is mostly one function.

### Wave 1 (2026-09-07) — the copy runs, and why the table above still stands

**The table above is the last window this instrument MEASURED, and it is the pre-wave-1 one.** The
copy every raw blit is built out of has since been rewritten to walk two barriered local cursors in
spelt-out blocks of `COPY_RUN_UNROLL` — `present_room`'s own 32-fold unroll — instead of recomputing
`image + offset` per longword. `../include/common.h` carries the shape and the GCC facts behind it;
`../STATUS.md`'s "Performance" carries the objdump evidence (20.6 cycles a longword against 57.5,
with the shipped binary at 21.9) and the projection that follows from it.

**It is a projection because this directory refuses to build the change**: `build.sh`'s
committed-cores gate has no override, so `profile.py ours` cannot run against an uncommitted core.
**After the commit, run `profile.py ours` and `profile.py compare` and replace the table above with
what they say** — `profile.py original` need not be re-run, since nothing about the shipped side
moved. Note when you do that the wave's own arithmetic is on `present_room`'s EXCLUSIVE total: 45.1K
of its 412.9K inclusive is the Timer C ISR nested inside it, which the window already counts
elsewhere and which this change does not touch.

### Wave 2 (2026-09-07) — the shim's two costs, MEASURED before and after

`build.sh`'s committed-cores gate reads `src` and `include` and nothing else, so a change confined to
THIS directory can be built and profiled while the cores are untouched — which is how these two were
measured on their own, before wave 1 landed: 809.2K cycles a frame -> 776.2K, 9.91 fps -> 10.33,
x1.73 -> x1.66, wave 1 not in it. The two waves together came to 809.2K -> 517.4K, 9.91 fps -> 15.50,
x1.73 -> x1.11; **waves 3a and 3b below carry it to 489.1K and 16.40 fps, x1.05, which is the number
to hold the next change against** (3a alone 496.4K/16.16, 3b alone 509.5K/15.74; the pair was
measured together). The table above is the pre-wave-1 window and stays as the baseline it was.

| | before | after |
|---|---|---|
| `bg_gem_dispatch`, exclusive | 23,373 cyc/frame over 8.6 calls | **10,224** — x0.43 |
| `save_sprite_backgrounds` / `draw_sprites` / `restore_sprite_backgrounds`, against the original's | x1.17 / x1.16 / x1.16 | **x1.09 / x1.09 / x1.08** |
| one YM2149 write from the sound ISR | 324 cyc through the `trap #9` gate | **100** through `bg_psg_write_super` |
| the 200 Hz tick, whole | 4,011 cyc/tick | **3,451 to 3,899** over four windows, 3,887 in the last |
| ...against the original's 1,696-1,699 | x2.36 | **x2.03 to x2.30**, x2.29 in the last |

The dispatch half is the MFDB copy, above. The tick half is the `trap #9`, and **the original's ISR
does not make one** — its own `psg_gate` @ `0x14940` carries 0.7 cycles a tick, because the handler
writes the ports itself and only USER-mode callers trap. A 68000 exception handler is already
supervisor and `bg_timer_c_entry` never lowers the interrupt's own IPL 6, so both of the things the
gate provides are already true inside the tick: `bg_timer_c_entry` raises `bg_in_timer_c` for the
length of the call and `shim_include/psg.h`'s door wrote the ports through `bg_psg_write_super`
(`bubble_os.s`, beside the gate and out of its own constants) instead of trapping — a routine wave
3a then deleted, folding the two stores into the header itself. The whole tick's
cost tracks how many voices happen to be sounding, which the unseeded ambience varies window to
window (2.5 to 3.0 chip writes a tick over those four) — which is why the per-WRITE figure is the one
to read, and it came back as **100 cycles exactly** in every one. Each side's ranges are reported in
BYTES beside the figure (1,932 of ours against the shipped handler's 914), because both lists are
hand-maintained against what the maps say today and a map that gained a symbol would truncate a range
silently.

**How the tick was costed at all** is the transferable half. Hatari attaches cycles to SUBROUTINE
arrivals, and both binaries reach their handler off the MFP's autovector, so 3,330 ticks arrive on the
shipped side and **21** of them are charged. `profile.py` therefore sums the profiler's per-ADDRESS
data over each side's own handler ranges (`SOUND_TICK_SYMBOLS`), which knows nothing about how an
address was reached. Two Hatari facts that cost a run each, and are now in
`docs/on-target-execution.md`: `profile save <file>` prints its rows to the debugger's OUTPUT and
writes a file holding only the labels and one `[...]` per row; and `profile addresses` PAGES — one
call printed 17 rows of 3,613 active addresses and looked complete.

**What is left in the tick is the CORE**: `timer_c_sound_isr` plus the two step routines GCC did not
inline cost the 2,770-3,165 cycles a tick `../STATUS.md` records, against the original's 1,696 for
its whole handler.
`../STATUS.md`'s "Performance" names the lever and says why this wave could not take it — wave 3a
took it.

### Wave 3a (2026-09-07) — the sound tick's core, and the chip write that was still a call

**Both halves measured in one before/after pair, in a throwaway worktree** so that `build.sh`'s
committed-cores gate would build a modified `src/sound.c` at all (`../STATUS.md`, "Performance",
wave 3a, says what each half was). The two windows are back to back on the same machine:

| | before | after |
|---|---|---|
| **cycles/frame, whole window** | 517.4K | **496.4K** |
| **fps** | 15.50 | **16.16** |
| ...against the original's 465.3K / 17.24 in the same session | x1.11 | **x1.07** |
| **the 200 Hz tick, whole** | 3,906 cyc/tick | **2,423** |
| ...against the original's 1,693 (wave 2 read 1,696-1,699; re-measured, see `../STATUS.md`) | x2.31 | **x1.43** |
| the tick's share of a frame | 50.4K a frame, 9.7% | **30.0K, 6.0%** |
| one YM2149 write from the ISR | 100 cyc through `bg_psg_write_super` | **~32**, two `move.b`s inline |
| `timer_c_sound_isr` + the two step routines | 3,154 cyc/tick over three symbols | **~1,990** in one |

The core half is `../src/sound.c`'s: the record's base is resolved ONCE per voice as a host pointer
and every field is `d16(An)` off it, which is what the original's `a0` does — 109 such accesses in
the ISR's own code against 10 that still index a register. The step routines are `static inline` with
it, so their offsets are constants at each of the four call sites instead of index registers, and the
4 `jsr`s with their 3 stack arguments are gone. **Every ADDRESS the file computes is still 32-bit
and wrapping** — the record base, the handler's own descending cursor and the volume table's signed
word index — and a pointer is formed from each only once it is final, always as `image +` that
wrapped `uint32_t`. What the accessors carry is a field displacement of 0..0x8a, and that one is
added to the POINTER: it does not wrap where `d16(a0)` would. That is visible only for a base within
0x8a of the top of the map, which only a corrupted `SND_ISR_TOP_VOICE` produces — and `make guarded`
IS the surface that tells the two spellings apart, so it is unpinned (no case seeds such a base)
rather than unpinnable. `timer_c_sound_isr` and `../STATUS.md`'s sound residuals carry it.

The shim half is `shim_include/psg.h`'s `psg_untrapped_write`: the ISR's untrapped write was a `jsr`
into `bubble_os.s` with two stack arguments around two `move.b`, and most of its 100 cycles was the
plumbing (the two stores that replaced it profile at 32 a write, so the call carried about 68). It is
two stores inline now, and `bg_psg_write_super` is deleted rather than left dead. It
**masks nothing, because the original's ISR does not** — all five of its write pairs are bare, from
0x14682 to 0x1487c, against the trap handler's `and.b #$f,d1` @ 0x1495c — so our two doors disagree
about the mask exactly where the original's two do, and `reg` being 0..15 is a caller's precondition
that the kit's own refusal holds off target. Masking here too was measured at zero (`core_sound.o`
byte-identical) and declined anyway; `../STATUS.md` and the header carry why — including the chip
claim the header used to argue it away with, now withdrawn as unmeasured.

**Two gates came with it**, because a store inlined into a verified core is a store no counted door
sees: `>> the chip's 2 ports agree between psg.h and bubble_os.s, the ISR's store is those 2 stores
and nothing else, and only the trapped door masks` pins the two constants against `bubble_os.s`'s,
pins the function's body to be those two stores in select→data order WITH their value expressions,
and pins `bg_super_gate_entry`'s own `andi.l #PSG_REG_MASK` — the two doors are meant to disagree
about the mask, and until this pass neither half was watched;
`>> the sound tick's helpers are inlined` refuses an out-of-line
`step_swept_envelope` / `step_triangle_lfo` / `psg_untrapped_write`, which is the one direction
`profile.py`'s own range list cannot see. Each was shown to red on a mutation — a `BG_PSG_DATA_OFFSET`
of 1, a swapped store pair, an added `& 15` and a `__attribute__((noinline))`, all four listed in
`../STATUS.md` — and **the inlining gate's first draft did not**, for a
`set -o pipefail` reason `../STATUS.md` records in full: a `nm | grep -q` pipeline reports 141 when
grep matches and kills nm with SIGPIPE, so the gate was green on exactly the case it existed to
catch.

**Two levers were measured and declined**, and `../STATUS.md`'s wave 3a carries both numbers: the
ISR's $484 mirror through `bg_write_byte` (45 cyc/tick, and a permanent `-Warray-bounds` if spelt as
a direct store from C), and the `volatile bg_in_timer_c` test in front of every chip write (50.8
cyc/tick, and no behaviour-preserving way to drop it without moving the core/shim seam).

### Wave 3b (2026-09-07) — the per-frame game logic: the Alcyon fp package, and the GEM door again

**Measured twice in a throwaway worktree off the same committed baseline wave 3a used** — once for
the change and again after the pre-commit review moved two more loops, and the table is the second
window, which is the code that ships. On the DISJOINT tier: this wave touched `../src/clib.c`'s floating-point package and `bubble_backend.c`,
and nothing in the sound path. So the two "after" figures below and wave 3a's are two INDEPENDENT
measurements of the same 517.4K frame, not a sum — the merge is measured below rather than added.

| | before | after |
|---|---|---|
| **cycles/frame, whole window** | 517.4K | **509.5K** |
| **fps** | 15.50 | **15.74** |
| ...against the original's 466.9K / 17.18 | x1.11 | **x1.09** |
| `game_frame_update`, inclusive | 46,472 cyc/frame, x1.49 | **38,638, x1.24** |
| `frame_scale_mouse_to_ghost`, inclusive | 23,184 | **15,218** |
| `fp_dispatch` | 8,959 cyc/call, x2.26 | **5,368, x1.36** |
| `fp_pack_double` | 974 cyc/call | **786** |
| `fp_acc_load_long` | 1,617 cyc/call, x1.41 | **1,295, x1.13** |
| the whole fp package, both calls a frame | 22,647 cyc/frame | **14,595** (the original's 11,438) |
| `bg_gem_dispatch`, exclusive | 10,552 cyc/frame over 8.65 calls | **10,353** |

**AND THE MERGE IS MEASURED, not left as arithmetic.** Wave 3a landed as code (`5c7a9de`) while this
was in review, so both waves were built together in a third worktree and BOTH sides were profiled in
one session:

| | wave 2 | 3a alone | 3b alone | **both** |
|---|---|---|---|---|
| cycles/frame | 517.4K | 496.4K | 509.5K | **489.1K** |
| fps | 15.50 | 16.16 | 15.74 | **16.40** |
| against the original's 466.9K / 17.18 | x1.11 | x1.06 | x1.09 | **x1.05** |
| the 200 Hz tick | 3,906 cyc/tick | 2,423 | 3,889 | **2,434** |

They compose: 517.4 − 21.0 − 7.9 = 488.5 predicted against 489.1 measured, which is what two disjoint
tiers should do and is worth having rather than assuming. **The original was re-measured in the same
session and came back at 466.9K / 17.18 — wave 2's figure exactly**, so the quoted denominator above
is the live one after all. It is also why the 3a column reads x1.06 here and x1.07 in wave 3a's own
table: the same 496.4K, over that session's own reading of the original (465.3K / 17.24).

**AND THE PREDICTION THIS WAVE MADE CAME TRUE, which is the point of having made it.** The three
sprite rows were x1.09-x1.10 with only wave 3b in, and the claim above was that almost none of that
was the VDI — it was the tick nested in their inclusive totals, so halving the tick would collapse
them with no work on the sprite path at all. With both waves in they read **x1.05, x1.05, x1.05**,
and `present_room` went x1.08 -> x1.03 by the same mechanism. `game_frame_update` is x1.49 -> **x1.18**
over the two waves.

**The whole of it is two loops, and `m68k-elf-objdump -d` is what found both.** `../STATUS.md`'s
"Performance" carries the instruction-level evidence; what it comes to is that `fp_div`'s 32-step
divisor halving, written as two 32-bit halves, compiled to `moveq #31,d5 / lsl.l d5,d3` — the
68000's register shift at **8 + 2 per bit = 70 cycles**, once a step — where the original spends
`lsr.l #1 / roxr.l #1` (20). Spelt as one `uint64_t` GCC emits exactly that pair. `fp_pack_double`'s
normalise loop was the same shape one size down: 40 cycles a pass, now **22**, against the original's
24. What did NOT change is the div step's compare: GCC still spends a whole throwaway
`sub.l`/`subx.l` in front of the real subtract, and the cheaper spelling is worse. That correction
came out of the review, and in a repo whose performance gate IS the objdump, a codegen claim the
objdump refutes is exactly the drift the gate exists to stop. **[WAVE 5c took that compare after
all** — spelt as the two 32-bit halves rather than the pair, the throwaway subtract is gone and the
step is the original's own 64/78. See wave 5c below.**]**

**The GEM door's row moved 302 cycles a frame, which is inside this instrument's own ~2% noise**, and
is carried on the objdump rather than on the profiler: `A_vdi_contrl` is 0x236f0, past the 68000's
word displacement, so every `contrl` slot was `move.l #145136,d0` plus an indexed access (26-32
cycles) and is now `d16(An)` off one `CURSOR_BARRIER`ed address register (16-20). **Hoisting a plain
local changes nothing** — GCC re-folds the constant — which is the transferable half; deleting the
barrier again puts every slot back, +56 B of code. Both live inside the `selector == GEM_VDI` arm, so
an AES dispatch — which reads no `contrl` slot — pays nothing for them.

**NEITHER LOOP NAMES A SURFACE.** Both changes are codegen, so the differential is green on the fast
spelling and the slow one alike and nothing here reddens if a later editor simplifies either back.
The shape of the fix is a third `build.sh` codegen scan beside the postincrement and endianness ones;
it was not added, because `build.sh` was being edited by wave 3a in the same tree. Recorded unpinned
in `../STATUS.md`, with two kit-shaped facts this wave registered rather than hoisted.

**AND THE ROW THAT DID NOT MOVE IS THE FINDING.** `save_sprite_backgrounds` / `draw_sprites` /
`restore_sprite_backgrounds` sit at x1.09-x1.10, +26K a frame between them, and **almost none of that
is the VDI or our wrappers.** Split three ways: our core wrappers cost 6,824 cyc/frame against the
original's 6,431 for the same work (`vro_cpyfm` + `vdi_set_src_mfdb` + `vdi_set_dst_mfdb` + the three
routines' own exclusives) — parity, and no lever; the shim door adds 7,320; and the remaining ~18K is
**the Timer C tick nested inside their inclusive totals**. The mechanism is visible in one row:
`copy_longs_ascending` is a leaf, and its inclusive exceeds its exclusive by 14,001 cyc/frame —
28% of our 50K tick, in a function that calls nothing. Hatari pushes the tick's own routine on the
callstack because the ISR `jsr`s to it, so every ancestor's INCLUSIVE carries the interrupt; on the
shipped side nothing `jsr`s and the same cycles land in the interrupted routine's EXCLUSIVE instead.
**A wave that halves the tick therefore collapses those three rows too**, and no work on the sprite
path would have — which the merged window above then confirmed, at x1.05 each.

### What this instrument does not measure

Each of these is measured rather than feared; `profile.py`'s header carries the same list.

1. **The two windows are equal in VBLANKS, not in FRAMES**, and the room loop advances per frame. The
   original ran 286 frames to our 165 from the same first frame, ticked its bonus bar 95 times to
   our 55 and fired 8 ambience sounds to our 3. The bias is one-way — the faster side's window is
   likelier to contain the expensive events — so it **flatters the slower side**, which is ours.
   Closing on the Nth arrival (`b pc = $... :N`) is the fix, and it has not been made.
2. **A run is not reproducible to better than about 2%**: two `ours` windows minutes apart gave 165
   and 168 frames. The ambience re-roll draws `Random()` from an unseeded stream and
   `smoke.press_the_game_keys` injects on a host wall clock, so whether a stray key is drained
   inside the window is a real-time race. One run of each side is taken.
3. **The mouse is idle on both sides** — this is a drifting bubble, not a played game.
4. **The shipped map is coarser than ours** (~7 KB of shipped `.text` past the last `fn` line), so a
   shipped row can absorb code our map splits out. That tilts a same-name ratio toward the original
   looking more expensive than it is.

## Unpinned, and why

1. **`Setscreen`'s physical base and resolution are not in the ordered stream.** The event ledger
   carries one 32-bit value per call and that trap has three arguments, so the entry is the LOGICAL
   base; the other two reach this build through the door's own parameters and nothing compares them
   (`TRAP_MODEL.md` Phase 14). A reconstruction that passed the wrong physical base would be
   invisible to the differential and visible only as a wrong picture here.
2. **The `-1` bases are not recognised.** XBIOS `Setscreen` takes `-1` for "leave that base where it
   is"; this game never passes one, and `shim_include/os.h`'s door would translate it like any other
   image offset if it did.
3. **The reported G-key defect is not reproduced and not closed.** See the `game` mode above: every
   headless configuration is green, and the one input that mode cannot exercise is the mouse.
4. **The `play` build is judged by a person, not a check.** It composes the whole program — the
   endings, the hall of fame, the practice and demo branches — and nothing headless can play it.
   `run.sh` and the floppy are the discharge, and the author discharged it under Hatari on
   2026-09-06 ("the game works well"). That is a play-through, not a surface: it says nothing
   re-derivable about which branches were reached.
5. **The floppy path is not run end to end headless**, for the same reason: it needs a double-click
   and the pointer cannot be moved. What IS checked is the volume (byte-for-byte readback, a boot
   sector TOS mounts and does not execute, free space and root slots for the three files a run
   writes) and — since `smoke.py floppy` — that it really boots TOS to a drawn desktop that has read
   the `DESKTOP.INF` off it, with no fault and exit 0. The `.PRG` on it is never started.
6. **Nothing has run on iron.** Every measurement here is Hatari 2.6.1 with TOS 1.04. The workspace's
   own taxonomy has two entries (11 and 12) that were only ever found on a real Atari.
7. **One TOS, one machine.** `docs/on-target-execution.md` class 6's working rule is to run the smoke
   on more than one ROM; `tools/hatari/` carries TOS 1.02 as well, but Hatari refuses a GEMDOS drive
   below TOS 1.04, so the second ROM would need the floppy medium — which item 4 cannot drive.
8. **`os_vdi`/`os_aes` always answer "modeled".** A real `trap #2` has no way to say otherwise, so
   the cores' refusal arms are unreachable on target.
9. **`Fopen`'s mode cannot cross the seam.** The original passes GEMDOS `mode & 3`; the kit's
   `os_fopen` takes no mode at all, so `src/clib.c`'s `c_open` drops it before the door and this
   build opens read-only. That is what every live caller asks for — every `c_open` in the program
   requests a READ mode and the one file it writes goes through `c_creat` — but it is a value the
   seam GUESSES rather than carries, and giving the door a mode is a kit change plus a differential.
   The alarm meanwhile is `FILE_WRITE_FAILURES`, which the record publishes and the smoke pins at 0
   — a tally the title path never makes fire, because nothing on it writes a file through a core.
   That is why it is an alarm and not a check, and it is said here rather than left to look like
   coverage.
10. **The conterm byte is mirrored, not shared, and the mirror is one-way per moment.** The cores
   write `image[$484]`; the shim seeds it from the machine before `init_gem_and_screens`, writes the
   core's clear back out after it, and mirrors the ISR's per-tick write from inside the interrupt.
   What is NOT mirrored is a write TOS makes to the real `$484` while the program runs — the image's
   copy would not see it — and nothing in this program cares, because the byte is only ever written.
11. **The trap wrappers are the project's one wholly unverified surface** (class 3). What stands in
    for a test is `tools/assert_trap_registers.sh`, which runs on every build over all 29 of them and
    proves on every run that it can fail.
12. **Five files here are near-copies of `projects/zynaps/recreate/atari`'s** — `mkprg.py`, `tos.ld`,
    `run.sh`, `gen_image.py` and `mkfloppy.py` — and each says so in its own header. They are not
    hoisted, because the right home is a shared `tools/target/` that both games' `build.sh` bind by
    their `project.toml`, exactly as `tools/recreate_kit/` is bound today; doing that is a change to
    Zynaps as well as to this directory and belongs to whoever moves the second one. `settle_chain`
    and `await_file`, which were the same shape of copy in `smoke.py`, HAVE been hoisted — into
    `tools/hatari_headless.py`, where Zynaps' own copies still shadow them until someone deletes
    those.

### Wave 4 (2026-09-07) — the GEM door and the tick's shim, and the NO-GO ledger

**489.1K -> 485.6K cycles a frame, 16.40 -> 16.52 fps, x1.05 -> x1.04.** `atari/` only; the cores are
untouched, so `make test` is green either side of it and is not the evidence. `../STATUS.md`'s wave 4
carries the objdump table, the per-lever NO-GO prices and the mutation sweep; the short version:

| | before | after |
|---|---|---|
| the GEM door, exclusive | `bg_gem_dispatch` 10,241 a frame, 1,184 a call | `bg_gem_dispatch` + `raster_copy_call` **8,411**, **971 a call** |
| the 200 Hz tick | 2,434 cyc/tick, 29.7K a frame | **2,297, 27.8K** |
| ...the shim's own half of it | 428, three routines | **~296**, one — `bg_timer_c_entry` is the whole tick outside the ISR now, and `bg_timer_c_tick` is deleted |
| the three sprite rows | x1.05 / x1.05 / x1.05 | **x1.04 / x1.05 / x1.04** |

**Two gates came with it.** $484 joined the PSG ports in `build.sh`'s two-language loop — scraped from
`../include/sound.h` and from `bubble_os.s` — and a second check pins the mirror instruction present
exactly once INSIDE `bg_timer_c_entry`, label to label. `bubble_main.c` carries a `_Static_assert` on
each of the four operand widths the assembly now hard-codes.

**The wave's finding was a hole, not a win: the GEM door's MFDB translation had no surface here.**
Deleting the destination MFDB's restore, and deleting the source raster's translation outright, were
both GREEN through `smoke.py game` and `smoke.py title` — the game mode photographed the framebuffer
at the FIRST arrival at `game_frame_update`, before that frame had drawn anything, and the title mode
makes no `vro_cpyfm` at all. **CLOSED** by the second capture at the SECOND arrival described under
"The `game` mode" above: the source translation now reds by 414 bytes, deleting the DESTINATION
translation halts the CPU on a Bus Error, and the destination RESTORE stays green because it is an
equivalent mutant — every `vro_cpyfm` call site rewrites both MFDB `fd_addr` fields first, so what it
puts back is never read. `../STATUS.md` carries the table.

### Wave 5a (2026-09-08) — the GEM door as one hand-written routine

**483.8K -> 482.2K cycles a frame, 16.58 -> 16.63 fps, x1.036 -> x1.033.** The whole-window move is
inside the instrument's own spread and is NOT the evidence; **the door's row is: 8,493 cycles a frame
-> 6,702, 984 a call -> 775, over 2,396 calls.** Measured in a scratch worktree of `b8ad1b0` so that
waves 5b and 5c are not in the window; `atari/` only, and `make test`'s 1,895 cases are green either
side of it.

| | before (C) | after (asm) |
|---|---|---|
| the GEM door, exclusive | `bg_gem_dispatch` 3,055 + `raster_copy_call` 5,438 = **8,493** | one row, **6,702** — **-21%** |
| a non-raster VDI call / an AES call / a `vro_cpyfm`, hand-counted | 498 / 518 / 1,104, plus `bg_gem_trap`'s 100 | **406 / 412 / 878**, plus **68** — the profiled window was 8 cycles a call dearer on each, before the review's own cleanup |
| `bg_gem_trap`'s row (the ROM VDI, which is what it measures) | 268,918 | 269,543 — unchanged, as it must be |
| the shim's two objects, `.text` | 1,646 B | **1,424 B** |

**The hand count is the instrument at this size, and the profiler is the check on it**: the door's
hand-counted frame is 6,408 cycles against a measured 6,702, so Hatari charges **4.6%** over the
68000's own tables (the same sum for the C door was 7,936 against 8,493, **+7.0%**).

**Eleven constants moved out of the compiler's sight** when the door became assembly — the two
selectors, the THREE `contrl` word indices the door reads, `VDI_VRO_CPYFM`, `MFDB_ADDR`,
`MFDB_SCREEN_ADDR`, each block's LAST index (the lengths are derived from those) and `A_vdi_contrl`
— so `build.sh`'s two-language loop went from 3 entries to 14, its scrapes were ANCHORED on both
sides so an expression-valued macro reds instead of scraping its first token, and two more pins are
the assembler's own `.error`s (a `MFDB_SCREEN_ADDR` that is no longer 0, which the door's `beq`
could not test for; a block whose length is no longer 5 and 6). Every `.error` was shown to fire.
Two gates came with the review: `build.sh` pins the door's C PROTOTYPE (its three `%sp` offsets are
that prototype restated, and had no other surface) and counts the three `addq.l` counter bumps.

**Four mutations, all caught**: the source raster's translation dropped reds `smoke.py game` by 419
of 32,000 framebuffer bytes; the destination's halts the CPU on a Bus Error writing at `$ffff8800`;
`VDI_CONTRL_DST_MFDB` 9 -> 10 is refused by the two-language loop before a byte compiles; and the
DERIVED slot offset off by one word — which that loop cannot see — halts the CPU reading at
`$30ef7300`. `../STATUS.md` carries the table and the two narrowings this wave made on purpose.

### Wave 5b (2026-09-08) — the 200 Hz handler is the ORIGINAL'S OWN INSTRUCTIONS

The tick is no longer compiled. `../src/asm/sound_tick.S` is a hand-written m68k routine carrying
`timer_c_sound_isr`'s C signature, 792 of whose 856 bytes are the shipped binary's own
0x145be..0x148d6 **byte for byte**, and `bg_timer_c_entry` calls it. It is the first time this build
runs anything other than a verified core, and "The one core this build does NOT run" above is the
row that says so — with the four pins that make it safe.

| | before (wave 4) | after | the original |
|---|---|---|---|
| the 200 Hz tick | 2,297 cycles | **1,842** (-20%) | 1,697 in this window |
| ...per frame | 28.0K | **21.9K** | 19.8K |
| the frame, on a tree carrying wave 5a as well | 485.6K, 16.52 fps | 476.8K, 16.82 fps, x1.02 | 466.9K, 17.18 fps |

**The 1,750-cycle target this wave was set was missed by 92, and what is left is the shape of the
seam rather than unspent work**: the transcribed body IS the original's, so the whole difference is
the eleven instructions around it plus `bg_timer_c_entry` — which the shipped binary has no
counterpart for, because ITS handler is the `$114` vector where ours is a C-ABI routine called from
one. `../STATUS.md`'s wave 5b prices the three levers, says which one was taken (16 cycles, measured
twice), and says that the only one crossing 1,750 folds the vector entry into the `.S` itself, which
is a seam decision rather than a tuning one.

Two lines left `bg_timer_c_entry` with the substitution and both are recorded there: `bg_in_timer_c`
is no longer raised (nothing C runs inside the interrupt any more, so `psg_untrapped_write` is an
unreached branch this build keeps for the argument `shim_include/psg.h` makes), and the image base
is popped rather than re-read — which `test_sound_asm.py::test_the_twin_never_stores_through_its_own_frame`
is what makes safe, not the transcription pin, whose bracket the prologue is outside.

### Wave 5c (2026-09-08) — the fp division loop and the VDI binding's base register

**485.6K -> 482.2K cycles a frame, 16.52 -> 16.63 fps, x1.040 -> x1.033.** `src/` only, so this is
the one wave of the three whose evidence `make test` (1,908 cases) and `make guarded` are green for
either way — the objdump is the evidence, and the whole-window move is barely outside the
instrument's 0.3% spread (wave 5a's re-window of the same before-binary read 483.8K). Measured in a
scratch worktree of `b8ad1b0`, so 5a and 5b are not in it. `../STATUS.md`'s wave 5c carries the
objdump tables, the two mutations and the four levers priced and declined.

| row, cycles a frame | before | after | the original |
|---|---|---|---|
| the fp package, summed | 13,281 | **12,017** | 11,535 |
| ...of which `fp_dispatch` exclusive (dispatch + `fp_div`) | 8,881 | **7,643** | 8,273 — now ahead |
| `vq_key_s` / `vq_mouse` / `vsf_color` / `vr_recfl` exclusive | 449 / 565 / 145 / 156 | **369 / 468 / 112 / 119** | 164 / 233 / 54 / 71 |
| the three sprite rows, exclusive | 6,813 | **5,793** | 6,458 — now ahead |
| `core_frontend.o` `.text` / the size gate's spare | 31,076 B / 72,512 B | **24,848 B / 78,656 B** | — |

**The two levers are one sentence each.** `fp_div` compares its 64-bit remainder and divisor as the
original does — high halves first, low ones only on equality — which drops the 34-cycle 64-bit
difference GCC computed and threw away, and takes the step to 64/78 against the shipped binary's
64/76. And the VDI binding materialises ONE barriered base pointer per entry point instead of a
32-bit address constant per slot, so every `contrl` slot is the `move.w #$80,-6186(a4)` the original
writes; `vq_key_s` is 426 -> 346 cycles hand-counted and the raster copy inlined at a sprite site is
548 -> 376.

### Wave 6a (2026-09-08) — the 200 Hz VECTOR is the twin, and the door's block re-read

**1,844 cycles a tick -> 1,748, 1,755 and 1,755 over three windows**, against the original's 1,697:
x1.087 -> **x1.030/x1.034**, and 20.6-20.7K a frame where it was 21.8K — so the 1,750 target is met
in one window and missed by five cycles in the other two, which is inside the wobble the unseeded
ambience puts on this row. **The whole window did not move outside the instrument's spread** (473.6K
-> 473.7K, 282 frames both ways, 16.94 -> 16.93 fps) — 1.2K a frame is 0.25% against a 0.3% spread —
so the tick's row is this wave's evidence and the headline is not. `atari/` and `../src/asm/` only.

| the tick's glue, hand-counted off the 68000's tables | before | after |
|---|---|---|
| the register save + restore | two `movem` pairs (four registers each), 40+40 / 44+44 | ONE pair of eight, **72 / 76** |
| the image base | pushed 28, read back 20, popped 12 | one `movea.l bg_image_base,%a3`, **20** |
| the call into the handler | `jsr` 20 + `rts` 16 | **none** — the vector falls through into the body |
| **total** | **356** | **260** |
| `bubble_os.o` + `asm_sound_tick.o` `.text` | 2,118 B | **2,096 B** |

**The profiler read 96 fewer cycles a tick in the first window and 89 in the other two, against a
hand count of 96.**

`bg_timer_c_entry` is no longer in `bubble_os.s`. It is the target-side entry of
`../src/asm/sound_tick.S`, behind `RECREATE_HOST_DIFFERENTIAL`, and the two arms are mutually
exclusive: the host build assembles the C signature the differential runs (byte for byte what it
assembled before, so the cost bar and every case read what they read), the target build assembles
the vector. **The chain is pushed before the registers**, which is what lets one `rts` close both
arms — TOS's saved `$114` on target, the C caller off it.

**It also removes an accounting asymmetry.** Hatari charges cycles to subroutine ARRIVALS, so while
our tick was `jsr`ed its cycles came out of whatever it interrupted; the shipped side's autovectored
handler leaves them in. Ours is autovectored now too, and the rows moved to match — `bg_gem_trap`'s
exclusive 268.3K -> **279.0K** against `vdi_call`'s 280.2K, `copy_longs_ascending`'s 135.9K ->
141.7K against `present_room`'s 139.3K — with neither routine changed. Same-name comparisons taken
before this wave and after it are reading two different accountings.

**The target arm is reachable by no differential in this workspace** (`docs/on-target-execution.md`
class 3), so `build.sh` reads it out of the linked disassembly instead: the routine from its label to
its one `rts` must call nothing, must contain the transcribed body's own label, must push
`bg_timer_c_chain` first, must `movem` `%d0-%d3/%a0-%a3` both ways, and must carry the `$484` mirror
once at `../include/sound.h`'s own address — which is the two-language pin the shared-numbers loop
used to carry for `CONTERM`, now made against the instruction that ships. `../STATUS.md`'s wave 6a
carries the mutation sweep and the register-class argument.

**The GEM door's five-slot restatement was scoped and is NO-GO**, and `../STATUS.md` says why with
the arithmetic: the five pointers are NOT constant — `vro_cpyfm` and `vr_recfl` lend the VDI their
caller's own rectangle, and one of the two is a runtime frame address — so the build gate that lever
asked for would refuse its own first build; a compare-against-a-cache costs 2,283 cycles a frame
against the restatement's 1,730 at this window's call mix; and the version that IS available (cache
the four constant slots, restage `ptsin` alone) buys ~930 a frame for a semantic coupling between
the door and `../src/frontend.c`'s opcodes that `bubble_os.s`'s own header disclaims.

### Wave 6b (2026-09-08) — the GAME TIER, on the base register the original keeps in a4

**The rows this wave owns are now 1,770 cycles a frame UNDER the shipped binary's, where they were
829 over** — 31,369 -> **28,770** against 30,540, summed over every function either map names for the
room simulation (the sprite protocol, the fp package, the `frame_*` slices, the two input VDI bodies,
`get_pixel`, `bubble_collision_probe`, the HUD's bar). The whole window went 473.6K a frame ->
**471.9K**, 16.94 fps -> **17.00**, x1.0143 -> **x1.0107**; that is 1.7K against a ~1.5K spread, so
**the tier's row is this wave's evidence and the headline is not**. Measured in a scratch worktree of
`7a2d648` with `src/` and `include/` only, so wave 6a is NOT in the window and the two do not add up.
`../STATUS.md`'s wave 6b carries the per-row table, the objdump counts and the six mutations.

| lever | what moved |
|---|---|
| `GlobalsBase` moved from `../src/frontend.c` to `../include/common.h` | the header `../README.md`'s ownership table designates for "an idiom a SECOND core needs" — and it keeps `word_at_base` beside `word_at`. Codegen-neutral: all seven core objects byte-identical across the move |
| the sprite protocol on the base | 5,758 -> **4,052** a frame. Ten slots a copy, and — the half wave 5c could not price — eleven hoisted address registers down to six, which is 80 cycles of `movem` a call |
| the `frame_*` slices on the base | 5,333 -> **4,921** a frame |
| `trap_save_registers` unified onto the base form (a review finding, not the brief) | **-2,396 B** across five core objects; the size gate's spare 78,912 -> **81,472 B**, at an unchanged window |
| `fp_pack_double` inlined as the fall-through tail the original has, and its `>> 28` given the original's `swap` | the fp package 12,058 -> **11,727**; the `always_inline` half is ~84 of that for +738 B, measured three ways rather than projected |

**What is left in the tier is structural and priced in `../STATUS.md`**: +1,890 on the `frame_*`
slices is the C ABI (nine `jsr`s and stack arguments where the original falls through nine regions of
one routine with `a4` already loaded), and closing it means `bubble_main.c`'s frame composition plus
verified signatures — another wave's brief. **The whole window's remaining 5.0K is entirely OUTSIDE
this tier** (+6.8K summed the other way: `bg_gem_dispatch` 6,644 with no shipped counterpart,
`game_room_frame_tail` 2,657, `bg_timer_c_entry` 1,702, against ours being ahead on the VDI trap and
the copy run).

**Three sites deliberately keep the `image + <address>` form**, and the pre-commit review corrected
why. `globals_at` is `image + (int32_t)address` where the image form is `image + (uint32_t)address`:
the same byte for every address this program can build, and a different one only above 0x80000000,
which `muls_ext_w`/`addr_add` cannot reach. So `apply_fan`'s object fields, `draw_sprites`' sprite
table slots and `v_gtext`'s `intin` index keep the image form because that is where the arithmetic
that built them belongs — not because converting them would be wrong. The first draft claimed a
hazard that does not exist; `../include/common.h` now states the real rule.

**Unpinned, and registered for the second time.** Deleting either `REGISTER_BARRIER`, or
`always_inline` from `fp_pack_double_tail`, `globals_base` or `sprite_copy`, is green under
`make test` and `make guarded` and gives back a third to a half of its lever. `build.sh` already has
the right gate half-built — `MUST_STAY_INLINED` would take the three names as a one-line change —
plus two codegen scans beside it. `build.sh` was wave 6a's file in the same working tree, so this is
named rather than done.
