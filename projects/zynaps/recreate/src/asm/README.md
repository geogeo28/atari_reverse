# The asm twins — what they are, and how to add the next one

A **twin** is a hand-written m68k transcription of the **original binary's own instruction
sequence** for one routine, carrying the C signature of the verified core it stands in for. The
target build (`atari/build.sh`) links the twin instead of the C; the host differential build never
sees it.

This directory holds Zynaps' twins: the scroll path (wave A — `scroll_blit.S`, `scroll_emit.S`,
`scroll_tile.S`) and the sprite and text paths (wave B — `sprite.S`, `text.S`). Wave B followed this
recipe unchanged and taught it four things, which are folded in below under **What wave B added**.
The recipe is the point of this file.

## Why transcription and not optimisation

The C cores in `../` are already proven byte-for-byte equivalent to the original — that is what
`test/test_scroll.py` and its neighbours do, against the shipped 1988 binary executed under Musashi.
So when a core is three times the original's cost, the fast version is not something to invent. It
is sitting in `../../out/prg_dis.txt`, and it has the one property no rewrite can promise:

> **An asm twin that faithfully transcribes the original's instruction sequence is 1.00x by
> construction.**

Measured, on this wave: the twenty page blits come out at **1.0024x** of the original's per-call
cycles and the two column emitters at **1.0083x / 1.0136x** — the whole of the excess being the C-ABI
prologue and epilogue the original does not have. Nothing was designed to achieve that; it follows
from copying.

The corollary matters as much: **do not improve on the original.** A cleverer instruction is a
divergence you now have to justify, in a file whose whole warrant is that it does not diverge.

## The chain of evidence

    original  ==(test/test_scroll.py)==  C core  ==(test/test_asm_scroll.py)==  asm twin

Both links are byte-exact **over the whole 1 MiB image**, so a twin is pinned to the original
transitively and neither link has to be re-derived. The twin is never compared against a second
oracle run: the C is already known equal to the original on exactly those cases.

Four things judge a twin, and a new one needs all four:

| check | where | what it catches |
|---|---|---|
| the differential | `test/test_asm_{scroll,sprite,text}.py` | any byte the twin computes differently, anywhere in the image |
| the transcription pin | `test_the_twins_transcribe_the_original` | a body that stopped being the original's own machine code |
| the cost pin | `test_the_*_twin_costs_what_the_original_costs` | a translation that quietly costs cycles |
| the build gate | `atari/build.sh`, "THE ASM-TWIN GATE" | the twin not actually being what the game calls |

The first three are `test/asm_twins.py`'s, shared by every suite; what a suite holds of its own is
its CASES (borrowed from that subsystem's C battery), its byte-pinned spans and its cost ceilings.

The build gate is the one worth dwelling on. This substitution fails **silently**: drop
`-DZY_ASM_SCROLL` and every `ZY_SCROLL(fn)` resolves to the C again, the twins still assemble, still
link, still export their names, and the game still draws exactly the right pixels — three times
slower, with nothing but the frame rate to say so. `make test` would not notice, because the C is not
wrong, only slow. So the gate asks the objects directly: every twin `include/scroll.h` declares must
be *defined* by an asm object **and referenced by a core object**. Proven able to fail — dropping the
define reddens it and exits 1.

## The shape of a twin

    | header: what it transcribes, from which address, and the C signature it carries
    .text
    .equ  <constants, named exactly as include/*.h names them>
    .equ  SAVED, (<n> * 4)                | what the prologue pushes
    .equ  ARG_<name>, <offset> + SAVED    | every argument offset measured past it

    .macro  <NAME>_PROLOGUE               | bind the C arguments to the original's registers
    .macro  <NAME>_EPILOGUE               | restore and rts

        .globl  <core>_asm
    <core>_asm:
        <NAME>_PROLOGUE
        .globl  <core>_body               | optional: brackets the transcribed span for the pin
    <core>_body:
        ...the original's instructions, one per line, each with its original address in a `|` comment
    <core>_body_end:
        <NAME>_EPILOGUE

Syntax is GNU `as` with **`%`-prefixed registers** (`%d0`, `%a5`, `%sp`) and `|` line comments. Files
are `.S` (capital) so cpp runs first.

### The two translations, and only these two

**1. The image base.** The original *is* the image, so it receives its cursors as absolute addresses
and reads globals absolutely (`tst.b $19ac1.l`). The reconstruction passes offsets from `image`,
which on the target is a real pointer. The prologue is the whole of that translation — add the base
to each offset argument once — and the body then works on absolute addresses exactly as it always
did.

The differential stages the image at a **non-zero base** on purpose (`tools/recreate_kit/asm_twin.py`
says why): a twin that ignored its base argument and addressed globals absolutely would pass at base
0 and fault the moment the target handed it a real pointer.

**2. Absolutes the body needs but has no register for.** `scroll_emit_tile_column` reloads
`lea $4b3be.l,%a1` **per tile row** with all seven address registers already in use. The answer is a
small stack frame: compute `image + A_tile_set_base` once in the prologue, then `movea.l
TILE_SET(%sp),%a1` in the loop. **This is cycle-neutral** — `lea abs.l,An` is 12 cycles on the 68000
and `movea.l d16(An),An` is also 12 — and that is the bar any substitution has to clear. If you find
one that is not cycle-neutral, say so in the file header and in `STATUS.md`; do not hide it and do not
raise the cost bar.

The bodies of the twenty page blits needed **neither** translation — they mention no address at all —
which is why they are byte-identical to the original's machine code and why that is a test.

### Registers

Save what you clobber of the callee-saved file (`%d2-%d7`, `%a2-%a6`) with a `movem.l` and measure
every argument offset past it, as `.equ SAVED` above. `%d0`, `%d1`, `%a0`, `%a1` are scratch. If the
prologue needs a temporary for the image base, use one the body loads before it reads.

If you add a stack frame, `%sp` must not move after the prologue or every displacement goes wrong.

**KNOW WHICH SURFACE CATCHES A CLOBBERED CALLEE-SAVED REGISTER, because it is not the differential.**
`test_asm_scroll.py` compares the IMAGE, and a twin that returns with `%a2` corrupted leaves the
image perfect and breaks its C CALLER instead — every case would pass. What catches it is the
on-target run: `bash atari/build.sh game && python3 atari/smoke.py game`, whose frame differential
against the shipped binary is computed by C that holds live values in exactly those registers across
the call. **So a new twin is not done until the game smoke is green**, and a twin that passes
`make test` and reddens `smoke.py game` should have its prologue/epilogue register lists read first.
**The blind spot is the callee-saved registers only — the STACK FRAME is covered off target.** An
epilogue that unwinds by the wrong amount returns to the wrong address, and the differential fails on
that before it ever compares an image: `asm_twin.py` calls a twin through the kit's `run_bench`
(`tools/recreate_kit/oracle/emu.py`), which plants a sentinel return address on the stack and raises
unless the `rts` lands on it. Measured — changing `TILE_EPILOGUE`'s `lea FRAME(%sp),%sp` to
`lea 8(%sp),%sp` reddens `make test` at once with
`RuntimeError: recon fn @ 0x844 did not return to the sentinel`.

## Adding a twin — the checklist

1. **Read the original.** Pull its bytes out of `../../out/prg_dis.txt` from the function's entry.
   Establish its register contract from the disassembly, not from the C.
2. **Write `src/asm/<subsystem>.S`** to the shape above. Constants get `.equ` names identical to the
   headers' — `test_constants.py::test_asm_twin_equates_match_the_headers` pins each to its header
   and requires **every `.S` to contribute at least one pinned name**, so a file that named nothing
   after the headers fails rather than going unchecked.
3. **Declare it in the subsystem header**, inside that header's `#ifdef ZY_ASM_<SUBSYSTEM>` block
   beside a `ZY_<SUBSYSTEM>(fn)` macro (see `include/scroll.h`, `include/sprite.h`, `include/text.h`).
   `include/*.h` is the build gate's GLOBBED source of truth for which cores have twins, so a new
   subsystem is covered by it the moment its header declares one — and add the new `-DZY_ASM_*` to
   `atari/build.sh`'s `ASM_SEAM_DEFINES` or the gate will tell you nothing calls your twin.
4. **Wrap every call site** in `ZY_<SUBSYSTEM>(fn)`. The C core and its own glue are left alone —
   they are the reference — with ONE exception the gate forces: a reference core that calls a
   twinned core in ANOTHER translation unit leaves an undefined reference to the bare name, which the
   gate cannot tell from a live call site, so that call is wrapped too (`src/hud.c`'s
   `draw_score_panel` calling `draw_bcd_number`; the wrapper is the identity on the host build, and
   on target that body is never reached).
5. **Add its cases to `test/test_asm_<subsystem>.py`**, on `test/asm_twins.py`'s four checks and
   reusing the C battery's staging rather than restating it — make that battery's helper public and
   say in its docstring who else drives it. Every case asserts the C *wrote something*
   (`must_write`), or a pair that both did nothing would read as a pass; a case that legitimately
   writes nothing (a clip rejection) passes `must_write=False` **and asserts the image came back
   untouched**, which is the positive control for that arm.
6. **Add its cost case.** A twin with no cost pin is a twin nobody would notice regressing. Measure
   first, then set the bar a handful of CYCLES above what you measured — see "one bar that moved".
7. **`make test`** (which assembles the twins first) and **`bash atari/build.sh game`** — the gate
   prints how many twins came from asm. Then **`python3 atari/smoke.py game`**, which is the only
   surface for a clobbered callee-saved register.
8. **Mutation-check your own differential**: flip one instruction, rebuild, watch the suite go red,
   revert. A differential that cannot fail is the failure. Mutate the COST pin separately with a
   behaviour-preserving change (one more register in the `movem`, `SAVED` corrected to match) — the
   differential and the byte pin both pass that, so it is the only mutation that judges the bar.

## What wave B added

Four things, each learned by getting it wrong first.

**1. A routine with several `rts`s is CALLED, not branched into.** Both sprite blitters and the
character blitter return from four or five places — every clip rejection is its own `rts`. Rewriting
each into a branch to a shared epilogue would change the body's byte layout at nine places and put
every branch displacement after them out of step with the original's. So the wrapper does its
`movem`, binds the arguments and then `bsr`s the transcribed body: each of the original's own `rts`
instructions returns to the wrapper, which unwinds the C frame. **18 cycles, and the rejection paths
and row loops stay byte-identical.** `text.S` gets a second use out of it — the original's own
`bsr draw_char` inside `draw_bcd_number` survives as a `bsr`, so eight score digits cost eight plain
subroutine calls rather than eight C calls with a `movem` pair each.

**2. When a routine falls off its own end into the next, the twin must too — so lay ALL the wrappers
out first and the bodies contiguously after them.** `draw_score_panel` has no `rts`: it sets up
`draw_bcd_number`'s arguments and runs into it. Written in the obvious order (wrapper, body, wrapper,
body) the panel body fell into the SECOND WRAPPER, which pushed a `movem` and read arguments off a
stack that no longer held any. `AsmTwins.call` caught it as "stored into its own code"; nothing about
the symptom named the cause.

**3. A byte pin is not always achievable, and the reason is `gas`.** The original's assembler encoded
`and.w #imm,Dn`, `cmp.b #imm,Dn`, `add.w #imm,Dn` and `sub.w #imm,Dn` as the immediate-EA forms
(0xc07c, 0xb03c, 0xd07c, 0x907c); gas spells all four as ANDI/CMPI/ADDI/SUBI. Same length, same cycle
count, a different opcode word. A CLIP PROLOGUE is almost nothing but those, so it cannot be
byte-equal however faithfully it is copied — but a ROW LOOP usually carries no immediate-to-Dn
operation at all, and wave B's seven loops are byte-identical to the original's. **Pin the loops,
name the limitation, and let the cost bar stand in for the rest.** (`.short` for the original's
encoding would restore the pin at the price of a file nobody can read; that trade was rejected.)

**4. A `_body_end` label MUST NOT share an address with an entry point.** It sits at the first byte
after the span, which for a body that ends a routine is the next routine's first byte —
`atari/profile.py` resolves a profiled call by ADDRESS and reports it by NAME, so the bracket label
takes that entry point's row. Measured: the collide twin's 1,146 calls a window came back under
`draw_sprite_masked_rows_body_end` and `draw_score_panel_asm` had no row at all, with every cycle
correctly counted and every name wrong. Wave B's brackets therefore end AT their loop's `rts` rather
than past it; the two bytes left outside are covered by the differential and by `run_bench`'s
sentinel-return check. **Check for it with `m68k-elf-nm` over the linked game ELF** — two names at
one address, `__mulsi3`/`_bss_start` aside, are yours.

**And one bar that moved.** Wave A's ceilings were 1.005-1.0125 because a page blit is 110,000 cycles
a call and its C-ABI prologue is a quarter of one percent of that. Wave B's routines are 1,700-16,000
cycles a call, so the same fixed cost is 2-11%. **Set the bar from your own measurement and keep the
margin in CYCLES, not in percent**: wave B's margins are 3-9 cycles, which is what makes one extra
register in a `movem` (16 cycles round trip) redden them. A bar quoted as "about 1.05" would have
been forty times looser than the effect it exists to catch.

## Where the pieces live

| | |
|---|---|
| the twins | `src/asm/*.S` |
| assembled to one blob | `build/asm/twins.{elf,bin}` — `make asm`, and `make test` first |
| the assemble rule | `tools/recreate_kit/kit.mk`, `$(ASM_ELF)` — generic, driven by `src/asm/*.S` existing |
| the Musashi runner | `tools/recreate_kit/asm_twin.py` — `AsmTwins.call(image, symbol, *args)` |
| the four checks, shared | `test/asm_twins.py` — `matches_the_c`, `assert_transcribes_the_original`, `cost_case`, `assert_within_the_bar` |
| the differentials | `test/test_asm_scroll.py`, `test/test_asm_sprite.py`, `test/test_asm_text.py` |
| the constant pin | `test/test_constants.py::test_asm_twin_equates_match_the_headers` |
| the seams | `include/scroll.h`'s `ZY_SCROLL()`, `include/sprite.h`'s `ZY_SPRITE()`, `include/text.h`'s `ZY_TEXT()` |
| the call sites | `src/frame.c`, `src/init.c`, `src/enemy.c`, `src/mothership.c`, `src/highscore.c`, `src/hud.c` |
| the build gate | `atari/build.sh`, "THE ASM-TWIN GATE" and `ASM_SEAM_DEFINES` |

The kit halves (`kit.mk`, `asm_twin.py`) are **game-agnostic**: a project acquires the whole
machinery by creating a `src/asm/` and writing a `.S` in it. Nothing in either file names Zynaps.
