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
├── bubble_os.s       _start, the Mshrink, 29 trap wrappers, the two exception entries
├── bubble_main.c     the image, the composition of the verified slices, the record
├── bubble_backend.c  the GEM door's pointer translation, and three libc functions
├── shim_include/     the seam: shadows of the kit's os.h / hw.h / psg.h / string.h, plus tos.h,
│                     bubble_target.h (what the three shim files hand each other) and
│                     bubble_mfdb.h (the one place blit.h's MFDB offsets are pinned to the kit's)
├── smoke.py          the gate: two Hatari runs, nine checks, three negative controls, and two
│                     modes of its own — the bootable floppy, and the G key's room loop
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
| `os_vdi` / `os_aes` | the kit's software VDI/AES over the image | a real `trap #2`, with the parameter block **translated** — see below |
| `os_setscreen` / `os_setpalette` / `os_setcolor` / `os_vsync` | an ordered entry in the OS event ledger, and no image effect | the real XBIOS traps, made where the core makes them. The two screen bases and the palette table are image OFFSETS and are translated |
| `psg_port_write` / `psg_port_read` | an ordered ledger and a register file | the real `$ff8800`/`$ff8802`, through the `trap #9` gate, at IPL 7 across the select-and-access pair |
| `hw_write8` | an ordered (address, width, value) ledger | a real byte store through the same gate. Two core call sites, both the MFP vector register — and `build.sh` counts them, because `HW_WRITES` is predicted exactly |
| `os_in_image` | the model's 1 MiB | the same arithmetic against the 664 KiB array that actually exists |
| `OS_SCREEN_BASE` | `0x8000`, XBIOS `Logbase`'s answer | **`0x9e100`** — the one constant this build changes, and the only change to what a verified core computes. See below |
| the Timer C ISR | never entered; the harness drives it explicitly | installed at `$114` behind an asm entry that CHAINS to TOS's own handler, exactly as the original's does |
| `image[$a4]`, `image[$114]`, `image[$484]` | ordinary diffable image bytes | **not vectors.** `$114` is seeded from the machine before the installer runs (so it saves something real) and taken by the shim's entry after. `$484` is seeded before `init_gem_and_screens`, mirrored OUT after it — which is the poke that really stops the key click — and mirrored out again by every tick of the ISR, from inside the interrupt |
| `sound_stop` at the hand-back | not run: the harness has no teardown | **run**, so the PSG is really silenced and the MFP's vector register really goes back to software EOI. `$114` and `$484` are then mirrored out the same way the install's were |

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

`bg_gem_dispatch` (`bubble_backend.c`) is the translation, and its shape is **patch-trap-restore**:
each block is patched in place to machine addresses, the trap is made, and the original offsets are
put straight back — so the VDI writes its answers into the game's own `intout`/`ptsout` arrays with
no copy back, and the image the cores read afterwards holds what it held before. A copy of each
block would have to know which fields the VDI writes; this has to know nothing. `fd_addr == 0` is
left at 0, because that is the VDI's "the screen" and TOS substitutes the logical base `Setscreen`
was given — which for this program is `screen_back`.

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

At the room's FIRST frame — a deterministic moment on both sides, with the room drawn,
`game_room_frame_tail` not yet run once and the mouse untouched because nothing headless can move
it — it compares the sixteen colour registers and the 32,000 displayed bytes against the original's.
**They are byte-identical**, which makes this the second place in this directory where the two
programs' memory is compared and the first inside the game.

**THE FRAMEBUFFER IS DUMPED AT THE BREAKPOINT AND THE PICTURE FOUR BLANKS LATER**, and the split is
what makes the comparison mean anything. Memory is exact at the instruction; the DISPLAY surface is
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
4. **The `play` build is otherwise unjudged.** It composes the whole program — the endings, the hall
   of fame, the practice and demo branches — and nothing headless can play it. `run.sh` is the
   discharge for those, and it is a person, not a check.
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
