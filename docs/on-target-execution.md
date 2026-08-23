# Running the Reconstruction On Real Hardware

The differential harness proves your reconstructed C produces the **same memory image** as the
original, instruction-for-instruction, against the Musashi oracle. That is a strong guarantee — but
it is not the same as "the game runs." The last mile is compiling the verified cores back into a
standalone GEMDOS `.PRG` and running them on a real 68000 (Hatari, or hardware). This doc is about
that step and the class of bugs that **only** appears there.

Two reference builds exist. `projects/buggyboy/recreate/render/atari/` (`game_main.c` + `game_os.s`
+ `game_build.sh`) is the older and larger; `projects/joust/recreate/atari/` is the second, and
differs in ways worth reading both for — its OS seam is the **include path** rather than the linker
(the kit's `os_*` helpers are `static inline`, so there is no symbol to override), it keeps the
kit's staged-file model on target instead of using real GEMDOS, and it stays in user mode. Read
either README for the concrete wiring. This doc generalises the lessons.

## The core insight: the harness is blind to everything the oracle models as a no-op

The oracle services hardware and OS the game touches with *fixed, image-only semantics* (see
`os.h` / `tos-os-calls.md`): a palette write, a `Vsync`, a `Dosound`, a non-blocking console poll —
all return a modelled value and touch **no image bytes**. That is exactly what makes the
differential test clean. It is also exactly what the test **cannot see**. Anything whose only
effect is off-image is invisible to verification:

| Dimension the harness ignores | Why it's invisible | Bites you on-target as… |
|-------------------------------|--------------------|--------------------------|
| **Hardware timing** (`Vsync`, interrupt cadence) | modelled as a no-op returning 0 | animations run at full CPU speed; interrupt-driven work (sound) starves |
| **Endianness / codegen** | the `.so` and the PRG produce identical *values*, just at different cost | 4–8× slowdown from byte-shuffle or call-heavy inner loops |
| **Trap/ABI glue** (`game_os.s` wrappers) | not exercised by the harness at all — the oracle models the trap directly | wrong register/stack slot → silent no-op or hang |
| **Real OS/hardware behaviour** the model simplifies | oracle returns a constant (e.g. console = "no key") | a path that "can't happen" in the model does happen live |

**Working rule:** every one of these is a real bug surface with **zero test coverage**. When
on-target behaviour diverges from the harness-verified image, suspect one of these four dimensions
before you suspect the reconstructed logic — the logic is the one part that *is* verified.

### Measure the blindness BEFORE you choose what to reconstruct

That blindness is not uniform across a program, and its distribution decides the reconstruction
order. Measure it first, with `tools/hw_scan.sh` + `tools/hw_portability.py`: they read every
hardware access out of the Ghidra DB, sort each function into a tier by what the oracle would do
with it, and close the tiers over the call graph. Both are game-agnostic; the worked example is
`projects/wonderboy/recreate/PORTABILITY.md`.

The tiers are the shim's own behaviour, restated per function:

| tier | the oracle's behaviour | what a green differential means |
|---|---|---|
| T0 CLEAN | no off-image access | it means what you think |
| T1 PSG_WRITE_ONLY | the modelled write ledger (PSG bytes, `Dosound`) captures it | verified, including the off-image effect |
| T2 SEEDED_READ | a byte read of an address either seeded model owns — the PSG read-back port, or one of the modeled hardware bytes (`os.h`'s `OS_HW_*` set: MFP GPIP, shifter sync, and the shifter's two video-counter bytes) — is **served** from a file the case declares (`psg_seed=` / `hw_seed=`) and recorded in an ordered ledger both sides keep | verified — the value is a declared input, and an undeclared one is refused, never guessed. What it costs is a **case obligation**: the case must say which machine it means, and a byte the machine changes on its own may be read only once per run |
| T3 HW_WRITE_ONLY | the write is silently dropped, seeded bytes included | the memory effect is verified; **the hardware effect is untested**. A later read of an address the run WROTE is refused as stale, which no declaration can fix |
| T4 HW_READ | the read returns 0, on BOTH sides — for every address **outside** the two modeled sets | **falsely green** if a branch depends on it; merely incomplete if not |
| T5 HARD_REJECT | the run is refused, and no mode lifts it | not verifiable at all |
| T6 UNMEASURABLE | the code cannot be read statically (self-decrypting protection) | there is no source text to port |

> The table above moved **twice on 2026-08-07**, and the two changes are different in kind — a
> report has to be read against the right one:
>
> 1. **Tier NUMBERS changed** when `T2 PSG_SEEDED_READ` was inserted (kit Phase 6 made the PSG
>    read-back servable; `projects/wonderboy/recreate/PORTABILITY.md` §0g has the old→new mapping).
>    **Any report generated before that uses the old six-tier numbering**, in which today's
>    T3/T4/T5/T6 were T2/T3/T4/T5.
> 2. **Then T2 was RENAMED, not renumbered** — `PSG_SEEDED_READ` → `SEEDED_READ` — when kit Phase 7
>    made `$fffa01` and `$ff820a` seeded bytes of the same kind (§0i). Numbering is unchanged, so
>    only the LABEL distinguishes a report from between the two changes; in one of those, those two
>    addresses read as T4. They are T2 today, and the eight functions that left the false-green
>    count with them are named in §0i.
>
> A 16/32-bit read taking a seeded byte in is **T5**, not T2: the model would have to fabricate the
> register beside it, so it is recorded and refused, and no seed lifts it.

**T4-with-a-branch is the tier to hunt.** T5 announces itself — the run fails, loudly, and so does a
T2 whose seed the case forgot to declare. T4 does not: the same wrong value reaches both sides and
the diff agrees on a fiction. That asymmetry is the whole point of the lattice — a tier that *stops*
you has already done its job, and the dangerous tier is the one that lets the run finish. Telling
"steers a branch" from "stored and ignored" needs dataflow from the read to the first conditional
branch that consumes it, not a count of operands. Two measured examples of what it costs:

* BuggyBoy's `$ffff820a` 50/60 Hz music-tempo branch was invisible to its **entire** differential and
  only surfaced on real hardware.
* Wonder Boy polls `btst #5,$fffa01 / bne` for FDC-done. That line is **active low**, so a permanent
  0 reads as *"already finished"*: under the oracle the poll returns success on its first status
  test, in 107 instructions, having moved not one byte. A reconstruction that does the same is
  "verified". **Then measure the layer above before you generalise it** — the same game's *command*
  entries reject that fabricated status and report hard failure (`$fffb` / `$fffd`) while mutating
  driver state, so "the driver reports success" was true of the polls and false of the driver.
  A T4 read makes the code believe a fiction; which fiction, and what each caller does with it, is
  a separate measurement per entry point.

> Both examples above are **T2 today**, and they are why: kit Phase 7 put exactly those two
> addresses in the seeded set, so a differential that declares neither is now refused instead of run
> (§0i). The measurements stand — what a `0` in those bytes DOES is unchanged, and a case is free to
> declare a `0` — but the fiction is now written down in the case rather than invented by the shim.
> Read them as the defects the tier was named from, not as live instances of it; the live ones are
> the FDC/DMA status registers, which Phase 7 deliberately leaves unmodeled because a per-run seed
> cannot express a register that must CHANGE between two reads.

Three rules the measurement itself has to follow:

1. **Use the disassembler's reference model, not an operand scan.** In Wonder Boy 15 % of hardware
   accesses are register-indirect (`lea $ff8240,a0` then `clr.l (a0)+`) and an operand scan sees
   none of them. Cross-check the total against a linear sweep of the *whole* image and explain
   every difference — a sweep sees code the disassembler never reached, and manufactures hits
   inside data and ciphertext.
2. **A tier is a property of the code, not of a run.** A T5 function comes back green on any run
   whose data never reaches the offending access. Verify the tier empirically on a chosen case, and
   say which case.
3. **State the coverage of the measurement as loudly as its result.** If the disassembler only
   reached 46 % of what you believe is code, every tier total is a statement about that 46 %.
4. **The CALL-GRAPH half is a claim about the calls Ghidra RESOLVED, not about the calls the code
   makes.** The scan closes each tier over its call graph, so a missing edge understates a
   function's closure exactly the way a missed operand understates its hardware use — and it
   understates it *silently*, as "clean, one callee, port it". Two things follow, and the second is
   the one that bites.
   * **Read the `I` ledger before you read the `E` edges.** A call the scan could not resolve is not
     dropped: it is emitted as an `I` record (function, instruction, text) and `hw_portability.py`
     lists every one of them under "unresolved indirect call/jump site(s)", with the standing warning
     that a transitive tier is a LOWER bound wherever one appears. An unresolved `jsr d16(An)` lands
     there — Wonder Boy's ledger opens with `I 0x716 0x726 jsr (0xe,A0)`. A one-callee function
     whose `I` ledger is non-empty is not a one-callee function, and that is visible without reading
     a byte of its body.
   * **The dangerous site is the one that appears in NEITHER ledger** — no `E` edge, no `I` row. Then
     nothing in the output says anything is missing. Wonder Boy had a measured instance — `$bbca`'s
     `lea $17adc.l,a1 / jsr 56(a1)` at `$bca2` — and the 2026-08-05 diagnosis found TEN such drops
     in one image, all the same mechanism: **Ghidra's 68000 sleigh models `jsr/jmp (d16,An)` one
     dereference too deep** (`68000.sinc` exports the operand as a MEMORY varnode and spells the
     instruction `call [operand]`), so constant propagation "resolves" the call to the four bytes
     STORED AT the effective address — an opcode, in no function — and a scan that walks the flow
     references drops the site silently, while `getFlows().length != 0` keeps it out of the `I`
     ledger too. The EA the propagator really computed survives as the instruction's READ data
     reference, which is how `HwPortabilityScan.java` now recovers the true target: when a computed
     transfer's pcode reaches its target through a `LOAD`, take the READ reference as the edge, and
     emit `I` whenever a computed transfer produced no row at all — **every call/jump in exactly one
     ledger** is the invariant a scan of this class must keep. (68000-specific by design: on x86 a
     `call [ebx+4]` dereference is genuine and this correction would be wrong.)
   `$bf4e` is the same silence from a different cause: it is reported as a 16-byte function with no
   callees, and its 16 bytes have no `rts` — they **fall through** into a 210-byte plotter with eight
   `bsr` callers of its own. Neither miss is exotic, and both are cheap to catch: before porting
   anything the scan calls a leaf or a one-callee non-leaf, read the body to its `rts` and resolve
   every `jsr`/`jmp` in it by hand.
   Where a count of call *sites* is recorded, say which encodings the scan covered — `bsr.s/w/l`,
   `jsr`/`jmp` through `abs.l`/`abs.w`, `jsr d16(pc)` — and that a call through a register or a jump
   table is outside all of them.

## The seam pattern

Cores that only make sense with real hardware are written as a **seam**: a no-op (or modelled)
definition compiled into the harness `.so`, and a *strong override* linked only into the PRG that
does the real hardware work. This keeps the differential test byte-identical while letting the
standalone build talk to the metal.

Two mechanisms, both in the BuggyBoy tree:

- **`BB_WEAK`** (see `include/buggyboy.h`): the core defines the function `__attribute__((weak))`;
  `game_main.c` supplies a strong override the PRG linker prefers. Used for `g_flip_screen`,
  `g_wait_vbl_set_offset`.
- **Excluded-from-PRG file**: `src/os.c` (the OS glue) is compiled into the `.so` but *omitted*
  from the PRG's core list; `game_main.c` provides the real versions. Used for `g_read_joystick`,
  `g_vsync`, `g_console_scancode`, `g_xbios_setpalette`.

Both give the same result: **one definition on each side, verified behaviour unchanged.** When you
add a seam, the core/no-op side must have **no image effect** (or the oracle-modelled effect) so the
differential test still holds; put the real trap/hardware poke only in the PRG override, and gate it
on `hw_ready` if it touches supervisor-only I/O space (`$ffff8xxx`, `$fffffcxx`) before `Super(0)`.

## Bug taxonomy (each one hit in a real build — 1-5 in BuggyBoy, 6-8 in Joust, 9 in Wonder Boy)

### 1. Endianness tax — byte-shuffle accessors on a big-endian target

The image is a flat byte array indexed by Ghidra address; multi-byte fields go through `be16`/`be32`/
`wr16`/`wr32` (`tools/recreate_kit/include/machine.h`) to preserve the 68000's big-endian order. On the **little-endian
host** (`.so`) those must assemble each word byte-by-byte. But the **68000 target is itself
big-endian**, so there the same helpers are just aligned `move.w`/`move.l` — yet a naive
byte-by-byte definition still compiles to an `lsl #8` shuffle on *every* field access in *every*
draw/blit routine.

- **Symptom:** uniform ~4× slowdown — menu *and* race, independent of any one function.
- **Diagnosis:** `m68k-elf-objdump -d game.elf | grep -c 'lsl.*#8'` — hundreds of shift chains =
  every access is shuffling bytes.
- **Fix:** `#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__` → native `*(uint32_t*)ptr`; keep the byte
  assembly on the little-endian host. Harness untouched, PRG ~40% smaller, shuffle gone. (These
  accesses are all even-aligned — the original ran on a 68000, which faults on misalignment.)

### 2. Missing hardware timing — unpaced Vsync loops

The original paces animation loops to the 50 Hz vblank with `Vsync` (XBIOS `$25`). The oracle models
`Vsync` as a no-op with no image effect, so the readable reconstruction often *omits it entirely* —
correct for the diff, wrong on-target.

- **Symptom (two faces of one cause):** the animation is a blur, **and** interrupt-driven work
  (e.g. the 50 Hz VBL sound driver) audibly stutters/"sticks" — the unpaced loop hammers the CPU and
  starves the interrupt.
- **Diagnosis:** find the loop's origin in the disassembly and look for `trap #14` with `#$25`
  pushed (`grep '#\$25' dis` near the `dbf`). If the C loop has no matching pacing call, that's it.
- **Fix:** add a `g_vsync` seam (no-op in harness, real `Vsync()` in the PRG) and call it the same
  number of times per iteration the original does.

### 3. Trap/ABI glue bugs — invisible to the harness

The `game_os.s` trap wrappers are pure PRG code; the oracle never runs them (it services traps
directly). So a wrapper that mishandles the calling convention has **no test coverage at all**.

- **Real example:** `Crawio(short w)` read its argument with `move.w 4(%sp)`. The SysV m68k ABI
  passes `short` in a 4-byte slot, so on the big-endian stack the value is the **low** word at
  `6(%sp)`; `4(%sp)` is the high word (`0x0000`). `Crawio(0)` *writes* a NUL and returns 0, so every
  console poll silently did nothing — killing F-key leg-select and in-race ESC.
- **Symptom:** a whole input/OS feature is inert (no crash, no hang — it just does nothing).
- **Diagnosis:** disassemble the call site (`pea ff` pushes a *longword*) next to the wrapper; check
  which half of the 4-byte slot the wrapper reads. Compare against a wrapper that works
  (`Fcreate`/`Fopen` read the full longword then use `move.w %d0`).
- **Fix:** read the longword and use its low word, matching the working wrappers.

### 4. Compiler-vs-asm codegen — call-heavy inner loops

The readable cores lean on `memcpy`/`memset` and small helpers. GCC does **not** always inline a
fixed-size copy: a per-cell `memcpy` in a fill/blit loop becomes a `jsr` with three stack pushes
*per cell*. The original did it as an inline `move.l` loop.

- **Real example:** `screen_fill_span` did `memcpy(dst, pattern, 8)` per 8-byte cell — a full-screen
  clear = ~1900 `jsr memcpy` calls, every frame. `draw_leg_results` clears the screen each
  leg-select frame, so the menu's frame rate tanked and arrow-key auto-repeat felt sluggish.
- **Symptom:** one screen/mode is disproportionately slow (here: the menu, not the race).
- **Diagnosis:** `objdump -d` the hot function; a `jsr <memcpy>` inside a tight loop is the tell.
- **Fix:** copy the fixed-size cell inline (e.g. two `wr32(dst, be32(pattern))` — native `move.l`
  on-target, byte-order-safe on the host). Keep it expressed through the `machine.h` accessors so
  the diff stays byte-identical.

### 5. Off-image OS services the game *relies on for output* — dropped as no-ops

The oracle models an OS call that has no image effect as a no-op, and the reconstruction faithfully
drops it. That is correct for calls whose effect really is irrelevant (a `Vsync`, a palette load the
test checks elsewhere) — but wrong when the call **is** the feature. The trap taxonomy above is about
*timing/codegen/ABI*; this one is about a whole **behaviour** that never gets reconstructed because
the harness can't see it. If it produces no image bytes, the differential test passes whether the
call is there or not — so it silently isn't.

- **Real example:** the leg-start **countdown beeps**. BuggyBoy plays "3-2-1-go" not through its own
  VBL music driver (`REFRESH`) but by handing `stop_music` (@`0x12ec4`) an XBIOS **`Dosound`** command
  list (`0x18bba`/`0x18bca`) each of the four race-start settle frames; TOS's per-VBL `Dosound`
  engine steps the list and drives the YM2149 **hardware envelope** (reg 8=`0x10`, reg 13 shape). All
  of it is off-image: `Dosound` writes the chip, not RAM. So the differential harness verified
  `stop_music` *without* its `Dosound`, `game_main` reconstructed the four `stop_music` calls with no
  list, and — separately — the VBL install replaced TOS's `_vblqueue` with just our handler, dropping
  the routine that *steps* `Dosound`. Three independent "no image effect" omissions, one silent
  feature. Engine/effects still worked (those go through the reconstructed `REFRESH`), so only the
  `Dosound`-based sounds vanished.
- **Symptom:** a specific sound (or other pure-hardware output) is missing on-target while everything
  routed through reconstructed code works. Nothing in the diff is wrong.
- **Diagnosis:** capture the *original* PRG's hardware trace and diff it against ours at the same
  moment (`hatari --trace psg_write --trace-file`). A register the original writes and we never do
  (here reg 13, the envelope shape) localises the missing service. Then find the data it consumes
  (the `Dosound` lists are const bytes in the image: `07 fe 08 10 … 0d 0e … ff`) and the trap that
  feeds it.
- **Fix (PRG-only, harness stays byte-identical):** add the real trap wrapper (`Dosound` = XBIOS 32),
  **preserve** the TOS `_vblqueue` entries the original keeps (so TOS's stepper runs), and issue the
  call where the original does. The reconstructed core keeps its no-op model; the PRG supplies the
  real call next to it — the seam pattern, applied to an *action* rather than a value.
- **Working rule:** when reading a reconstructed function, treat every dropped/no-op OS call as a
  question — *"is this call's only effect off-image, or is the off-image effect the point?"* A
  `Dosound`, a `Cconout`, an `Ikbdws`, a palette poke to an unchecked register: each may be carrying
  behaviour the test is blind to.

### 6. Codegen again — an addressing mode whose semantics the compiler and the 68000 disagree on

Class 4 is about code that is *slow*. This one is about code that is **wrong**, emitted from C that
reads correctly, in the one place the harness can never look: a loop over hardware registers.

- **Real example (Joust).** A VBL handler loaded the 16 shifter colour registers with
  `for (i = 0; i < 16; i++) pen[i] = be16(table + 2*i);`, `pen` being a `volatile uint16_t *` at
  `$ffff8240`. GCC folded it to one instruction — `move.w (%a0)+,(%a0,%d0.l)`, with `%d0` pre-biased
  by `$ffff8240 - table`. On the 68000 a `MOVE`'s **destination** effective address is computed
  *after* the source operand's postincrement, so every pen landed one register high and the
  sixteenth write went to `$ffff8260` — the **resolution** register — carrying pen 15's `0x0777`.
- **Symptom:** the machine hangs, and *which* machine matters — TOS 1.04 died on the spot, EmuTOS
  absorbed it. Nothing in the diff is wrong, and the C is not wrong either.
- **Diagnosis:** `objdump -d` the handler and look for one instruction using the **same address
  register** in a postincrement source and an indexed destination. It is the shape, not the target,
  that is suspect.
- **Fix:** don't write hardware registers through a walked pointer at all. Where TOS has a
  variable for the job, use it: one longword into `_colorptr` (`0x45a`) *is* a palette load, done by
  TOS's own VBL — which is all XBIOS `Setpalette` does, and it is legal from an interrupt where the
  trap is not.
- **Working rule:** **run the smoke tests on more than one TOS ROM.** It costs one environment
  variable and it is what turned this from "works here" into a located bug. EmuTOS is forgiving in
  ways real TOS is not; the two disagreeing is a finding, and the two agreeing byte-for-byte (as the
  Joust framebuffers now do) is a much stronger green than either alone.

### 7. The exits the reconstruction reports but its caller drops

The original leaves a routine by a `jmp` that abandons the stack, or by a `Pterm` that ends the
process. Neither has a post-state to diff, so the reconstruction returns a RESULT CODE instead —
and its caller ignores it, faithfully, because in the original the routine that took such a path
never came back and the next line was never reached. The differential is perfectly happy. On target
the game then cannot be quit or restarted at all, and the loop simply carries on.

- **Real example (Joust).** `poll_quit_key` returns `INPUT_QUIT` after running the verified
  `quit_to_desktop`, and `INPUT_RESTART` for the R key; `check_highscore` returns
  `CHECK_HIGHSCORE_RESTART`. `start()` drops all three — twenty-one `jsr`s, no result tested, which
  is exactly what the original's `_start` does. Ctrl-C therefore saved the high score and kept
  playing.
- **Symptom:** a whole control-flow feature is inert on target, and there is nothing wrong with any
  reconstructed function.
- **Diagnosis:** grep the reconstruction for result codes whose enum names say "never returns"
  (`INPUT_QUIT`, `*_RESTART`, `TITLE_QUIT`), then look at who calls them. A caller that discards
  one is a feature the PRG owes.
- **Fix:** the shim finishes the exit from the only place it gets control — the OS seams the cores
  call, since the entry point never returns. WATCH the key rather than intercept it, so the verified
  tail still runs: Joust's shim notes Ctrl-C at the console seam, waits for `quit_to_desktop`'s own
  first trap to confirm the tail is running, and acts at the NEXT seam of any kind. Cost: the exit
  lands one frame later than the original's jump. A restart needs an actual unwind (`longjmp`) back
  to a `setjmp` in the shim, which then re-enters the verified entry point.
- **Two traps inside that fix, both measured:**
  * **hand the machine back on EVERY exit path.** Anything installed into TOS — KBDVBASE vectors,
    the `_vblqueue`, `conterm`, the screen base, the palette — outlives the process, and an IKBD
    handler still chaining interrogates out of freed memory halts the machine about a second after
    `Pterm`. It is invisible while the program runs, so **let the emulator run on past the exit and
    assert on what it reports** (`--run-vbls` plus the exit status) instead of stopping at the dump.
  * **a freestanding build has no `setjmp`.** Writing one is ten instructions, and two details are
    not optional: save the RETURN ADDRESS into the buffer rather than trusting the stack slot it sat
    in (that slot is dead the instant `setjmp` returns and every later call reuses it), and declare
    it `__attribute__((returns_twice))` or GCC compiles away the second return.
- **Working rule:** the reconstruction's honesty about not returning becomes the PRG's bug list.
  Every result code a caller drops is a feature the shim owes, and the shim's version of it is
  necessarily *later* than the original's — say where, and by how much.

### 8. Memory-equal is not display-equal — the video base register's missing low byte

Every comparison a differential harness makes is against MEMORY. The user looks at a SCREEN, and on
this hardware one register sits between them. It is the most complete blind spot in the method: a
byte-identical framebuffer, a byte-identical palette, and a wrong picture.

- **The mechanism.** An STF's video base register has no low byte — `$ffff8201`/`$ffff8203` hold bits
  23-16 and 15-8, and there is no `$ffff820d` (that is the STE's). An address handed to `Setscreen`
  that is not 256-byte aligned is TRUNCATED, and the shifter displays from up to 255 bytes below
  where the program draws. ST low-res interleaves plane0..plane3 word by word, so the remainder
  mod 8 decides the symptom: a multiple of 8 slides the picture by whole 4-plane cells, anything
  else PERMUTES THE BITPLANES — shapes intact, colours systematically remapped.
- **Symptom:** a user says "the planes/colours are shifted" while every check you own is green.
- **Why section alignment does not fix it:** GEMDOS loads a `.PRG` at whatever the TPA gives, and
  that is not 256-aligned (measured for one game: `0x12596` under TOS 1.04, `0x1b018` under EmuTOS),
  so alignment *inside* the image says nothing about the absolute address. An
  `__attribute__((aligned(256)))` on the buffer is not ignored — it does align the buffer within its
  section, and it is simply **irrelevant**, because the section's own base is unaligned at run time.
  Do not go looking for a linker script to blame: if yours uses `SUBALIGN(1)` in `.bss` so that BSS
  abuts text+data (which GEMDOS requires), that is doing a different and necessary job, and removing
  it will break the load without fixing anything here.
- **Fix:** reserve slack and round the buffer's base up at RUN TIME, then hand that to `Setscreen`.
- **Assert it every boot, in two instructions:** `Setscreen`, a `Vsync` (TOS applies it from its own
  VBL), then `Physbase()` — and compare the read-back with what you passed. They are equal only if
  the address was aligned.
- **And witness the rendered picture at least once.** Hatari's debugger `screenshot <file>` drives
  the emulator's real video path, so a PNG of your run and one of the original at the same frame
  anchor is a display-level comparison. Control it by deliberately misaligning the screen: every
  memory check must still pass and the picture must not.
- **A PNG comparison is a comparison of the ENCODER'S CHOICES as well as the pixels, and three
  Hatari settings decide whether it can succeed at all.** An earlier revision of this section
  justified a byte comparison by an argument about the two runs sharing one encoder; Wonder Boy's M5
  refuted it and measured all three of the reasons:
  * **`--frameskips 0`.** Under `--fast-forward` Hatari still emulates every frame but does not
    RENDER every frame, and `screenshot` grabs the last *rendered* surface — so without this a
    capture returns whichever frame happened to be drawn, and no two runs agree.
  * **`--drive-led off`, not just `--statusbar off`.** With the statusbar hidden Hatari draws a small
    activity LED **in the top-right border**, i.e. inside the photographed area. If one side touches
    a disk and the other does not, the picture differs by a coloured rectangle that is emulator
    chrome — and worse, the extra colours push Hatari's PNG writer from a palette image (colour type
    3) to a truecolour one (type 2), so the two files can never match byte for byte whatever the
    pixels do. **A colour-type difference in the IHDR is the tell**: it means the comparison was
    never about the game.
  * **Stop-then-shoot.** The display surface is built scanline by scanline, so a capture taken where
    an anchor happens to fire mixes that frame with the one before. Break at the anchor, then arm
    `b VBL > VBL :once` (Hatari substitutes the expression's current value on the right, so this
    reads "the next vblank") and photograph from *that* breakpoint's action file.
  With all three, measure rather than assume: run each side twice and diff the pictures per anchor.
  Assert only on the anchors that come back byte-identical on both sides — the rest are noise, and a
  green over them means nothing.
- **A PALETTE-MODE PNG CARRIES THE PALETTE, so the rendered picture reads pens no pixel uses.** This
  is the other half of the colour-type tell above and it is worth knowing for its own sake: a
  colour-type-3 PNG's `PLTE` chunk is literally the shifter's sixteen colour registers — verified
  byte for byte ($000 → `(0,0,0)`, $777 → `(238,238,238)`). A truecolour (type 2) image encodes only
  the pixels that are drawn and carries no such table. So the same fault — one corrupted pen — is
  invisible to a truecolour capture and visible to a palette one, and **removing the LED makes the
  rendered surface strictly more sensitive rather than merely cleaner.** Measured in Joust: its
  palette negative control classified the rendered picture as a surface the fault must NOT move, on
  a measurement taken while the LED was inflating the picture to truecolour; with `--drive-led off`
  that classification is simply wrong and the control now (correctly) requires the picture to move.
  If your project has a control that says a palette fault leaves the picture alone, check the IHDR
  colour type before believing it.
- **DO NOT ASSUME THE THREE SETTINGS EXPLAIN EVERY IRREPRODUCIBLE ANCHOR — measure the residue.**
  Measured across the two projects, two boots of the shipped side each: Wonder Boy is byte-identical
  at all four of its anchors. Joust, with the settings applied, is byte-identical at three of six —
  the LED came out of frames 1 and 115 (IHDR colour type 2 → 3, 5697 → 3270 bytes), and the deeper
  anchors 150/180/210 still disagree between two boots, as at least one of them did before. So the
  recipe accounts for the CHROME and not for the deep-anchor variance, whose cause is unmeasured and
  is registered as a blocker at Joust's own surfaces rather than explained here. Two runs cannot rank
  two configurations against a quantity that is itself nondeterministic, and the temptation this
  paragraph replaced was to close the gap with a one-line causal claim — that the two projects'
  different anchor counts were a property of the games rather than of the settings — which nobody
  had measured and which the measurement above partly contradicts.

### 9. `Super(0)` / `Super(ssp)` is not a balanced pair — TOS returns on the USP it froze

**The bug.** The standard supervisor wrapper is `ssp = Super(0); …; Super(ssp);` and every project in
this workspace ships it, commented "balanced pairs only". It is not a pair. **TOS returns to user
mode on the USP as it stood when `Super(0)` ran, and does not reload USP from the supervisor stack.**
So the unwind is correct only while the compiler leaves `%sp` at the same depth at BOTH call sites —
and m68k GCC defers and combines argument pops, so it very often does not.

**How it presents, which is the worst part.** Wonder Boy hit this the moment a title-screen load was
added ahead of the `Super(0)`: the two depths diverged by twelve bytes (`USP $3f7f52` against
`ISP $3f7f5e`), the `rts` after the second `Super` popped stale stack, and the program died at
`$26520020`. **After a clean teardown, with every read-back green and every record written.** The
crash is in the epilogue, so all the evidence a mode collects says the run succeeded. An earlier
build had measured `USP == ISP` and read that as correctness; it was the compiler's stack schedule.

**The fix**, one instruction: plant the USP yourself immediately before the trap that leaves
supervisor mode — `move.l %a0,%usp` with the SSP-to-be in `%a0` — so the value TOS returns on is the
one you chose rather than the one it happened to freeze. Wonder Boy's is `wb_leave_supervisor` in
`projects/wonderboy/recreate/atari/wonderboy_os.s`.

**WHO ELSE IS EXPOSED.** Any project using the plain wrapper. `projects/joust/recreate/atari/joust_os.s`
ships the byte-identical `Super` and `joust_main.c` leaves supervisor mode at five sites; Joust is
recorded as closed and hardware-confirmed, which means it is *currently* lucky rather than *correct*
— one inserted statement between its `Super(0)` and its `Super(ssp)` reproduces this. Not fixed there
by the phase that found it, and registered as such.

**The general rule this is an instance of.** *A wrapper whose correctness depends on where the
compiler left the stack is not correct.* Anything that captures machine state at one point and
restores it at another — supervisor mode, an interrupt mask, a vector — should restore from a value
it OWNS, not from one the ABI happens to preserve. And a teardown defect is invisible to every
surface that samples state before teardown, so the surface that catches this class is the exit status
and the machine-health scan of the merged stream, not the record the program writes.

## The observable surfaces

An on-target run can be watched on exactly six surfaces, and no more. They are listed here because
the useful question about any on-target change is not "is it right?" but **"which of these six would
have shown me if it were wrong?"**

| surface | what it is | what it cannot see |
|---|---|---|
| **memory** | framebuffers and image bytes, dumped by the program or by `savebin` | anything that never lands in RAM: the shifter, the PSG, the IKBD, TOS's own variables |
| **the trap ledger** | which OS calls were made, with what arguments (Hatari `--trace xbios,gemdos`) | what the *device* did with them |
| **the hardware-state vector** | the registers themselves, read back at a frame anchor — shifter pens, resolution, YM file, video base | the ORDER things reached them, and anything between two anchors. **And any register whose value is a PHASE rather than a state**: if the game has music playing at the anchor, the PSG's sound registers depend on which vblank the boot finished on, and two boots of the *same binary* disagree about them. Measure that before comparing them (boot the original twice and diff the vectors); what moves is not evidence, and the surface that can compare it is the timeline below |
| **rendered pixels** | Hatari `screenshot`, i.e. the emulator's real video path | nothing about *why*; and it is only as reproducible as the emulator's frame rendering |
| **timelines** | the ordered stream of hardware writes (`--trace video_color,psg_write`), reduced to a per-phase shape | values it does not sample; it is a shape, not a state |
| **exit status and the log** | the emulator's own return code plus its bus/address-error and halt lines | anything the machine survives *and* does not log |

**The rule: every on-target change names the surface that would catch its failure. If it names none,
that is the finding** — not a reason to proceed carefully. Add the surface, or record in `STATUS.md`
that the change is unpinned and why.

Four escapes in this workspace are the evidence, and each one names a surface that did not exist yet:

- **The EA pen shift.** A palette loop compiled to `move.w (%a0)+,(%a0,%d0.l)`; on the 68000 the
  destination EA is computed *after* the source postincrement, so every pen landed one register high
  and the sixteenth write hit the *resolution* register. Every memory check was green. → the
  **hardware-state vector** (nothing was reading the shifter back).
- **773 palette stomps.** The VBL handler re-armed `_colorptr` every vblank, so the palette was
  loaded 773 times over a run where the original loads it four times. Every snapshot was green,
  because all 773 loads wrote the same correct words. → **timelines** (every other surface is a
  snapshot, and a wrong route to the right state is invisible to all of them).
- **Video-base truncation.** An unaligned screen address is truncated by the shifter, which has no
  low byte on an STF; the framebuffer, the pens and every dump stayed byte-identical while the
  picture came out with its bitplanes permuted. → **rendered pixels**, plus the one read-back
  (`Physbase`) that caught it in the end.
- **The half-blind exit detector.** Hatari writes its log to *stderr* and the parser read *stdout*,
  so the line scan for bus errors and halts had been reading an empty string for a year. The
  emulator's *return code* still worked, which is why the blindness went unnoticed. → **exit status
  and the log**, and the lesson that a surface can be present and vacuous.

The practical form of the rule for the writes a shim makes: **read every one of them back.** A write
to RAM (TOS variables, KBDVBASE, a VBL queue) reads back exactly; a write to a write-only device (the
IKBD) gets the strongest available proxy — the next reply arriving, the transmitter draining — and
the residual blindness gets written down next to it rather than assumed away. Record *which checks
ran* as well as *which failed*: a check that silently stops running looks identical to a passing one,
which is precisely how the exit detector survived a year.

## Diagnostic toolkit

You cannot single-step a `.PRG` the way you diff a function. These techniques turn "it's wrong on
hardware" into a localised answer. All are cheap and were decisive in the BuggyBoy session.

- **Run the original binary as the benchmark.** Stage the *original* `.PRG` + its data on a Hatari
  drive and run it exactly as you run yours (same TOS, `--memsize`, `--joy1 keys`). It is the ground
  truth for speed *and* behaviour: "original menu is snappy, ours is slow" turned an "is this
  inherent?" debate into "this is a regression, find it." "Original's screen isn't shifted" localised
  a rendering bug. TOS boot-time bus errors at `PC=$e000xx` are the ROM probing hardware — harmless,
  ignore them; a panic from *your* text segment is real.

- **Border/background-colour probe.** Write palette reg 0 (`$ffff8240`) to a distinct colour at
  points of interest; the screen colour tells you which branch ran with no debugger. Used to prove
  input delivery: red when `input_state` had joystick bits, green when `Crawio` returned a key,
  blue idle → "joystick works, console delivers nothing" isolated the bug to the console path.
  Write **one** register with a constant — `*(volatile uint16_t *)0xffff8240ul = 0x700;` — and never
  a loop over several of them: `$ffff8260`, four registers past the end of the palette, is the
  resolution register, and taxonomy class 6 is what a loop that runs one register long does to
  the machine. A probe is throwaway code, which is exactly why it gets written without thinking.

- **Byte-compare against the original by dumping its RAM.** The strongest side-by-side there is,
  and it costs one Hatari debugger script. Run the ORIGINAL binary to the screen you want, dump the
  whole machine (`b VBL > N :once :file act.ini` with `savebin dump.bin 0 0x400000` and `cont` in
  it — host paths, not GEMDOS ones, and give Hatari `/dev/null` on stdin or the debugger blocks),
  then **search the dump for your own framebuffer bytes**. A hit means the two bitmaps are equal,
  and you never had to find the original's screen address. Joust's on-target title screen is
  byte-identical to the shipped binary's this way, at the original's own Physbase. Compare
  BITPLANES, not colour: the palette is off-image on both sides, so it is a GUI check instead.

- **Run the original as a DIFFERENTIAL, not just as a benchmark.** The RAM-dump comparison above is
  a single screen; the same debugger turns it into a frame-by-frame equality test against the
  shipped binary, which is the strongest on-target statement a reconstruction can make. Four
  techniques make it work, and each was a dead end first:
  * **Discover the load base, never assume it.** Search a RAM dump for a signature taken from a
    *relocation-free* part of the `.PRG`; the hit's address minus its file offset is the base. It
    varies with the ROM and with what TOS put below the TPA (measured for one game: `0x12596` under
    TOS 1.04, `0x1b018` under EmuTOS, same test). Every anchor is then `base + (ghidra - load_base)`.
  * **Pin the randomness where the two programs AGREE.** A game whose "RNG" harvests its own text —
    a common trick — reads different bytes in the two loads, because relocated longwords hold
    *file value + load base*. Forcing the same `Random` result pins only the starting offset into two
    different streams. Park the cursor inside the largest **relocation-free** stretch instead, and
    report how far it travelled so the test can prove it never left.
  * **Inject a keystroke ON the trap, not after it.** Forcing `Bconstat` to say "a key is waiting"
    makes the game call `Bconin`, which BLOCKS on an empty buffer and never returns. Break on the
    `trap` instruction itself and set both `D0` and `PC` past it.
  * **Anchor frames on a per-frame routine's entry.** Hatari's `b pc=$x :<count> :once` fires on the
    count-th hit, so one breakpoint per sample frame reads that frame off exactly (a count of `1` is
    rejected — use a plain `:once`). And feed the emulator a stream of `c` on stdin: an action file
    ending in `cont` still drops the debugger at its prompt, and a prompt with nothing to read stops
    the emulation dead after the first breakpoint.
  * **Choose the sample depths by where the screen MOVES.** With neutral input a game can be static
    for most of a window — Joust's is, from about frame 2 to frame 110 — and a depth whose
    neighbouring frame is identical cannot detect a mis-anchor at all. Measure frame N against N+1
    first and sample only where it differs.
  Then **control the control, with a fault you INJECT**: re-run the pinned side deliberately
  mis-anchored by one frame and require the comparison to FAIL. A "sensitivity check" assembled from
  numbers you already hold is a theorem, not a control — ours compared `ours[early]` against
  `shipped[late]`, which is guaranteed to differ once the main compare has passed, and it stayed
  green in a run where the main compare correctly failed. Check the dump LENGTHS too: `zip`-style
  comparison stops at the shorter side, so an empty dump reads as a perfect match.
  * **Compare the PALETTE as well as the bitplanes, and read both off the HARDWARE.** A framebuffer
    compare sees plane indices; the colour they resolve to lives in shifter registers that are in
    neither program's image, so a byte-identical framebuffer says nothing about what the screen
    looked like — and "the colours are shifted" is a whole bug class it cannot see (class 6 above put
    every pen one register high). Dump the shipped side's pens with
    `savebin <file> $ffff8240 32` at the same frame anchor and your own the same way, and mask to the
    bits the machine implements — on the ST three per gun, because a CPU read returns the unused
    fourth bit as bus noise while the debugger's read of the emulator's model does not. Know its
    limit: it compares the pens AT the anchors, so a pen that is right there and wrong in between
    still passes, which is exactly the shape of a flashing colour.
  * **A shim that PUSHES a palette must push on CHANGE, not per vblank.** The game owns the hardware
    between its own `Setpalette` calls; re-arming `_colorptr` every vblank stamps all sixteen pens
    back over anything its `Setcolor` just did. Pushing on change also makes the two shifter traces
    the same shape — ours went from 773 full loads to 6 against the original's 4 on the same pinned
    run — at the cost of one vblank of latency worth stating.
  Finally, **say which pins turned out not to be load-bearing.** Ours was the RNG: parking both
  sides in a region where their bytes genuinely differ still matched at every sampled frame, so the
  stream is consulted but nothing it feeds is drawn that early. Reporting that is the difference
  between evidence and theatre.

- **Raster colour-bars for timing.** Set the border to a different colour before each per-frame
  stage; the on-screen *height* of each colour band is that stage's share of the frame. A single
  dominant band = the bottleneck. (Caveat: if everything "flashes with no dominant colour," the cost
  is spread — a real result meaning no single hot function, not a failed measurement.)

- **`--cpuclock` bisect (8/16/32 MHz).** Overclock the emulated CPU. If a higher clock makes it
  smooth → the problem is **CPU-bound** (compiled-C tax, chase codegen). If nothing changes → you're
  frame-capped or blocked elsewhere, not compute-bound. Also the shipped workaround for playing
  faster than a real ST.

- **Oracle instruction counter.** The Musashi shim exposes `osh_num_insns()` (Python:
  `emu.run(...)` returns `out_regs["ninsns"]`). Run a function through the oracle with a test's
  realistic staging to get its exact per-call instruction count on the *original* code — objective
  per-function cost, no emulator GUI. This is how the BuggyBoy per-frame budget was measured
  (render_road ≈ 24k insns/frame, draw_leg_results ≈ 35k) and how a suspected hot function is
  confirmed or cleared before you spend effort optimising it.

- **Isolate a subsystem with a build flag.** A `-DNOAUDIO`-style define that stubs one subsystem
  (sound, a render stage) tells you by A/B whether it's the culprit — but prefer the raster bars /
  instruction counter first; they answer "which one" in a single run instead of one rebuild each.

- **Coverage-gap report — find the unverified triggers before they ship.** `make coverage-gap`
  (`recreate/tools/coverage_gap.py`) runs the differential suite with the oracle's executed-PC
  tracking on (`osh_cov_*` in `shim.c`, dumped per xdist worker by `test/conftest.py`), then lists
  every call site to a sound/OS *sink* (`Dosound`/`INITTUNE`/`INITFX`/`play_event_tune`/
  `handle_marker`/`stop_music`) that **no test executed**. Those are exactly the §5-class triggers —
  off-image or fuzz-unreached, so the image diff is blind to them. Knowingly read-verified sites go in
  `tools/coverage_gap_allow.txt` with a reason; the tool exits non-zero on a *new* gap. This is the
  systematic answer to "the diff is green but a sound is wrong": it would have flagged the leg-start /
  checkpoint / collision jingles up front instead of via play-testing.

## Verifying an on-target fix without breaking verification

Every fix above touches PRG-only code or a host/target-conditional, so the invariant is: **the
differential suite must stay green and byte-identical.** The workflow:

1. Make the change behind a seam or a `__BYTE_ORDER__` guard so the little-endian `.so` path is
   unchanged.
2. `make` + run the full differential suite — 100% pass, same as before (the harness can't see your
   change, which is the point).
3. Confirm the on-target codegen actually changed (`objdump -d`: shuffle gone / call gone / pacing
   added).
4. Rebuild the PRG and confirm the *behaviour* on Hatari against the original binary.

If a change makes the differential suite diverge, it wasn't a pure on-target fix — it altered image
output, and you've changed verified behaviour. Back up and re-scope.

## Scaffolding hygiene

Diagnostic probes (border colours, raster bars, subsystem stubs, A/B build flags) are throwaway.
Keep them behind build flags while investigating, then **remove them before committing** — commit
only the real fixes plus any genuinely reusable tool (the oracle instruction counter earned its
place; the `PROF_BARS` border-flasher did not). A committed `-DPROF_BARS` is a smell: it says the
investigation leaked into the artifact.
