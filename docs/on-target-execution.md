# Running the Reconstruction On Real Hardware

The differential harness proves your reconstructed C produces the **same memory image** as the
original, instruction-for-instruction, against the Musashi oracle. That is a strong guarantee — but
it is not the same as "the game runs." The last mile is compiling the verified cores back into a
standalone GEMDOS `.PRG` and running them on a real 68000 (Hatari, or hardware). This doc is about
that step and the class of bugs that **only** appears there.

The BuggyBoy reference build lives in `projects/buggyboy/recreate/render/atari/` (`game_main.c` +
`game_os.s` + `game_build.sh`); read its README for the concrete wiring. This doc generalises the
lessons.

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
on-target behaviour diverges from the harness-verified image, suspect one of these four before you
suspect the reconstructed logic — the logic is the one part that *is* verified.

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

## Bug taxonomy (each hit in the BuggyBoy build)

### 1. Endianness tax — byte-shuffle accessors on a big-endian target

The image is a flat byte array indexed by Ghidra address; multi-byte fields go through `be16`/`be32`/
`wr16`/`wr32` (`include/machine.h`) to preserve the 68000's big-endian order. On the **little-endian
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
