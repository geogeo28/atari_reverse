# The asm twins — what they are, and how to add the next one

A **twin** is a hand-written m68k transcription of the **original binary's own instruction
sequence** for one routine, carrying the C signature of the verified core it stands in for. The
target build (`atari/build.sh`) links the twin instead of the C; the host differential build never
sees it.

This directory holds Zynaps' twins: the scroll path (wave A — `scroll_blit.S`, `scroll_emit.S`,
`scroll_tile.S`), the sprite and text paths (wave B — `sprite.S`, `text.S`), and the frame loop's
five slices (wave C — `frame.S`; wave D — `frame_head.S`, `frame_fire.S`, `frame_spawn.S`; wave E —
`frame_draw.S`). Wave B followed this recipe unchanged and taught it four things; wave C was the
first twin that CALLS, and taught it four more; **wave D followed it faithfully and bought
nothing**, which taught it the most useful thing in the file; **wave E found what wave D's
instrument had hidden**, which taught it the second most useful. All four are folded in below under
**What wave B added**, **What wave C added**, **What wave D added** and **What wave E added**. The
recipe is the point of this file.

**READ "What wave D added" AND "What wave E added" BEFORE SCOPING A NEW TWIN.** Between them they
say when NOT to write one and — the harder question — how to tell that a routine nobody has scoped
is worth one. Wave D is where both of this project's mis-scoped waves are reduced to a single rule;
wave E is where that rule turned out to have a blind spot, and it is also where the recipe's
governing assumption is finally stated as a PRECONDITION rather than a fact.

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

**A CLOBBERED CALLEE-SAVED REGISTER IS CAUGHT OFF TARGET NOW, AND THIS PARAGRAPH USED TO SAY THE
OPPOSITE.** It was true when it was written: a differential compares the IMAGE, and a twin that
returns with `%a2` corrupted leaves the image perfect and breaks its C CALLER instead, so every case
passed. `asm_twin.py` closed it — `AsmTwins.call` seeds all eleven of `%d2-%d7`/`%a2-%a6` with
`CALLEE_SAVED_SEEDS` and asserts each one back, naming the register and telling you to read both
`movem` lists. Wave D re-measured it rather than trusting either version of the sentence.

**WHAT STILL HAS NO OFF-TARGET SURFACE IS THE `#ifdef`-ED ARM**, and that is the reason a twin is
still not done until `bash atari/build.sh game && python3 atari/smoke.py game` is green. Wave C's
five target-only instructions and wave D's six (`frame_head.S`'s pause spins) are assembled ONLY in
the target build: the transcription-order pin reads the file's text and so sees them, but it pins
their PRESENCE AND ORDER, not their operands. A wrong polled byte, a wrong scancode, a wrong
`HW_MFP_IERB` or a wrong bit number passes every off-target check in the workspace and shows up on
iron as a hang or a dead keyboard, which names nothing. `STATUS.md` records both sets as rows.

**The STACK FRAME is covered off target.** An
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

## What wave C added

Wave C is one twin — `frame.S`, the frame loop's last slice (`[0x11d30, 0x1296e)`, 703
instructions) — and it broke four of this file's assumptions at once, because it is the first twin
that is not a leaf.

**1. A TWIN THAT CALLS. The kit grew a door for it.** Waves A and B twinned routines that call
nothing, or that call each other inside the same blob. This one calls **sixteen verified C cores**,
and the twin blob is linked ALONE (`kit.mk`'s `$(ASM_ELF)`), so `jsr collision_chain_walk` did not
link at all. Two more of its seams — the raster and vblank spins, and the MFP `bset` — are modelled
HOST-SIDE by the kit and can never be m68k code. So `tools/recreate_kit` gained a **callback door**:
off target, a stub `jsr`s into a reserved address band, `asm_twin.py` services the callback by
calling the host C and resumes the blob. `TRAP_MODEL.md` carries the contract. **On target the door
does not exist** — the same `jsr` names the real core — so a twin's body is identical either way.

**Two consequences worth knowing before the next non-leaf twin.** The door charges the emulated
machine NOTHING for the C body, so **an off-target cost reading over a span containing a call is not
comparable to the original's**; pin cost over call-free spans, or say "the twin's own instructions".
And the door deliberately DESTROYS the caller-saved file (`%d0-%d1/%a0-%a1`, N/Z/V/C set and X on
an alternating schedule — `TRAP_MODEL.md`, and wave D's section below for what that did and did not
buy)
after each callback, exactly as a real core does — a courtesy version of it hid a stub that had
forgotten to save them.

**2. THE BYTE PIN IS MOSTLY UNAVAILABLE HERE, and that is the price of position-independence.** The
original IS the image, so it reads its sixty-six globals absolutely (`tst.b $19aad.l`). The
reconstruction gets the image as a pointer, so every one of those becomes base-relative — two
reserved registers, `%a6 = image` and `%a5 = image + 0x18000`, the second putting all sixty-six
inside one signed 16-bit displacement window. Almost every instruction in the slice mentions a
global, so almost nothing in it can be byte-equal to the original.

**Say what stands in its place rather than quietly dropping a check.** For `frame.S` that is: the
differential over staged worlds per exit arm, the cost bars, and a **transcription-order pin** —
every one of the original's 703 instruction addresses appears in the file's `| 0xxxxx` comments
exactly once, in ascending order, with no gaps and no extras. That is weaker than bytes and it is
not pretending otherwise; it is what catches a band spliced out of order, an instruction dropped, or
a line duplicated.

**TWO SUBSTITUTIONS PULL IN OPPOSITE DIRECTIONS, and only the measurement settles it.** The
base-relative globals are CHEAPER than the original's absolute-long forms — `tst.b d16(An)` is 12
where `tst.b abs.l` is 14, `move.b #imm,d16(An)` 16 against 20, `lea d16(An),An` 8 against 12 — and
gas relaxes some `.w` branches to short. That was predicted here first, and it predicted bars below
1.00x. **It was wrong.** The stage makes nine or ten door calls a frame, and a trampoline — a
four-register `movem` pair, the `suba.l` pointer-to-offset conversions, the argument pushes and the
`lea` unwind — costs far more than the single `bsr` the original has in its place. The trampolines
win: measured, the twin is 240-360 cycles OVER the original on every band, so the bars sit at
**1.022x-1.037x**. `test/test_asm_frame.py`'s cost section carries the four-row table.

**The general form of that mistake is worth keeping: a cost prediction assembled from instruction
timings is an argument, not a reading.** Take the reading.

**3. A SEAM MAY SPLIT BY BUILD.** Three of `frame.S`'s instructions are not the original's: the two
busy-waits and the `bset #6,$fffa09`. ON TARGET they are the original's own instructions, because the
interrupt really does write the byte and the register really is at $fffa09 — which is what
`tools/recreate_kit/include/sched.h` says a real-machine build should do, and the target's own
`sched.h`/`hw.h` supply `static inline` versions with no linkable symbol at all. OFF TARGET they go
through the kit so the poll ledger and the hardware-write ledger still see them. The `#ifdef` is in
the body, not hidden in a stub, and the transcription-order pin reads BOTH arms.

**4. AND THE MEASUREMENT THAT SENT US HERE WAS WRONG — read this before trusting a profiler row.**
Wave C was commissioned on the profiler attributing **211,784 cycles/frame** of SELF to this slice,
against an estimated ~71,600 for the original's same span: a 140,000-cycle prize. Both numbers were
wrong, in the same way. **The slice contains the frame's two synchronisation spins**, and Hatari
charges spin cycles to the function they occur in, so that SELF was ~95% *waiting*.

Measured properly — on the oracle, with the waits released on their first poll, so what is counted is
work — the original's slice costs **9,788 to 12,378 cycles a frame**. The C was ~2.7x that, which is
about the ratio the brief guessed; the ABSOLUTE prize was **~19,500 cycles a frame, not 140,000**.
The twin collected it: `frame_loop_once` inclusive 477,268 -> 457,803, the game smoke 2.80 -> 2.68
vblanks a frame (17.9 -> 18.7 fps). Real, and seven times smaller than the row said.

**The lesson is general enough to belong in this file: a profiler row for a routine that contains a
busy-wait measures the wait.** Before sizing a twin from one, either put the wait outside the span
or measure the span on the oracle, where a schedule releases it.

## What wave D added — and the one it added is a NEGATIVE RESULT

Wave D twinned the frame loop's other three slices — `frame_head.S` `[0x10f4e, 0x113c0)` (240
instructions, 17 doors), `frame_fire.S` `[0x113c0, 0x1167c)` (148, 4) and `frame_spawn.S`
`[0x1167c, 0x11c00)` (311, 25 doors over 44 sites) — 699 instructions, 43 external doors, on this
file's recipe unchanged. Every twin is byte-identical to its C over the staged worlds, every cost bar
is measured-then-set, every mutation reddens. **And it bought nothing: +13 cycles a frame, measured
A/B on one tree.** That is the finding, and it is worth more than the twins are.

**THE A/B IS THE EVIDENCE, and it is the measurement anyone scoping the next wave should copy.** Not
a before-and-after across two sessions, where the window and the mixture both move: the same tree,
built twice, the three `ZY_FRAME()` wrappers at `src/frame.c`'s call sites the only difference.
`atari/profile.py frames` gave **403,947** cycles a frame with the twins off and **403,960** with
them on. Thirteen cycles on four hundred thousand is not a win and not a regression; it is a
NO-OP, and no distribution moved (`2x196 4x366 5x1` against `2x188 4x350 5x1`, the counts differing
because the two runs stopped playing at different frames).

**WHY, IN ARITHMETIC.** `STATUS.md` scoped the wave at ~44,000 cycles a frame, from "the slices' own
C, about 70,300". Both twins and C were then measured directly:

| slice | the twin's OWN instructions, door-discounted | from |
|---|---|---|
| `frame_head.S` | ~1,400 | its boss/asteroid bands, where `playfield_clear` is a door |
| `frame_fire.S` | ~600 | its two call-free bands |
| `frame_spawn.S` | ~2,700 | its ordinary band |
| | **~4,700 a frame** | |

The C they replaced costs the same to within those 13 cycles. **The 70,300 was never there.** It came
from an inclusive Hatari row minus a partial list of its children, and the children left off the list
— the twenty `scroll_page_to_screen_p*` blits (~110,000 cycles a frame), `draw_score_panel` (17,217),
`scroll_emit_column_shift2` (20,941) — are essentially the whole row.
`frame_panel_scroll_and_ship_stage_asm`'s inclusive 166,715 is ~165,000 of already-twinned children
and ~1,400 of its own.

**THIS IS WAVE C'S MISTAKE IN ITS SECOND FORM, so the rule needs restating more strongly than "a
profiler row containing a busy-wait measures the wait".** The general rule is:

> **An INCLUSIVE profiler row is not a prize. Subtract the children — ALL of them, by measurement,
> not by the ones you happen to have rows for — before you scope a twin from it.** Wave C's row was
> 95% spin and was scoped at 7x its truth. Wave D's row was 97% already-twinned children and was
> scoped at 15x its truth. Both times the arithmetic was done on the row rather than on the
> remainder.

The cheap way to get the remainder, and what wave D should have done first: **twin one slice, measure
the A/B, and only then scope the other two.** `frame_fire.S` is 148 instructions and four doors — a
day's work that would have answered the whole wave.

**SO WAVE D'S THREE TWINS ARE VERIFICATION-ONLY: BUILT, VERIFIED, NOT SHIPPED.** The target build
calls the C for those three slices; `include/frame.h` marks them `ZY_TWIN_VERIFICATION_ONLY` and
`atari/build.sh`'s gate carries that as a DECLARED CATEGORY — a marked twin must be DEFINED by an
asm object and must NOT be referenced by a core object, which is the ordinary gate inverted, and its
object is kept off the link line so the `.PRG` is byte-for-byte its pre-wave size. The reasons are
+13 cycles, six unpinnable pause instructions, and 699 instructions of maintenance; wave C's
`frame.S` still ships because its ~19,500 cycles are real. **A twin you do not ship is still worth
writing when the measurement is the point** — these are what put the three slices' own cost at
~4,700 cycles a frame, and their suites keep that number re-takeable rather than re-arguable.

**AND THE COST BARS OF A NON-LEAF TWIN READ BELOW 1.00x, which is not a win either.** Wave D's bands
sit at 0.019x-1.41x, and none of them is a fidelity claim: the door charges the emulated machine
NOTHING for a C body while the original executes every one of its `bsr` targets in full. The two
readings that mean something are (1) the CALL-FREE bands — `frame_fire.S`'s +170 and +146 cycles,
which is almost exactly the C-ABI frame a 7-register `movem` pair costs (132 cycles) — and (2) the
bands whose heavy children ARE doors, like `frame_head.S`'s boss/asteroid pair at 1,320/1,546 cycles,
which is essentially the twin's own instructions and where a 16-cycle change is 1.2% of the reading.
**Set the bar on the band whose children are doors; a band dominated by twinned children barely moves
when the twin does.**

**Three smaller things wave D learned:**

* **A twin whose slice writes the reserved registers must permute, and say so per site.** `frame.S`'s
  header says the stage it transcribes "uses only %a0-%a4"; `frame_spawn.S`'s writes A5 and A6 — the
  two reserved — so the original's A5 became `%a3` and its A6 `%a4`, each live range checked dead
  across the substitution and each renamed line carrying the original's own text in its comment.
  `frame_head.S` did the same for its own A5/A6.
* **`gas` folds a zero displacement**, on top of wave B's ANDI/CMPI re-spelling: `ENTITY_X(%a1)` with
  `ENTITY_X = 0` assembles to the 2-byte `(%a1)` where the original wrote the 6-byte `d16` form, 4-8
  cycles CHEAPER at each site (six in `frame_head.S`, eleven in `frame_spawn.S`). Being cheaper, it
  cannot hide a regression behind a cost bar — but it is a divergence and it is named in both headers.
* **One mutation class is not expressible, because the assembler enforces it.** `sub.l %a6,%a0` is
  not a defect gas can emit: SUB has no `An,An` form, so it silently assembles `suba.l`. The
  X-transparency rule for `PUSH_OFFSET` is still right and still documented; on that operand shape
  the toolchain holds it for you, and a mutation sweep should not go looking for a red there.
* **gas does NOT silently truncate an out-of-window `d16(An)` — it refuses.** Three of this
  directory's headers and the shared window pin all said it would, and wave D measured it: moving
  `frame_fire.S`'s `.equ FGB` out of range gives `Error: displacement too large for this
  architecture; needs 68020 or higher`, once per offending line, and the build fails. **The
  assembler is the gate.** The `%a5`-window pin is still worth having — it names the WINDOW rather
  than the architecture, before the build, over every global at once — but it is a better error,
  not the only surface, and it now says so.
* **A PYTHON MUTATION SWEEP LIES THE SAME WAY A `make` ONE DOES.** The workspace already knows that
  a mutation sweep is worthless unless the relink is forced; the same trap has a `__pycache__` form.
  Restoring a mutated constant in a test module within the same mtime second left pytest running the
  CACHED bytecode, and two unrelated cases stayed red after the file on disk was already correct —
  which reads as "my fix broke something else". `find . -name __pycache__ -exec rm -rf {} +` before
  trusting the green, exactly as `rm build/*.so` comes before trusting a build's.

## What wave E added — the instrument, and the recipe's PRECONDITION

Wave E is one twin — `frame_draw.S`, the frame loop's fourth slice `[0x11c00, 0x11d30)`, 86
instructions — and it is the smallest of the five by an order of magnitude. It took the game's
judged cadence from **2.68 to 2.51 vblanks a frame** and cut the overrunning frames from 101 of 300
to 77. Wave D's 699 instructions bought 13 cycles; wave E's 86 bought ~36,000 on the frame that
matters. The difference is not the code. It is the instrument.

**1. AN AVERAGE CANNOT SEE A COST THAT SCALES WITH ENTITY COUNT, AND EVERY INSTRUMENT BEFORE THIS
WAVE WAS AN AVERAGE.** `profile.py` measures a window; `smoke.py` measures 300 frames; the campaign's
closing table measured a mean. `frame_draw_objects_and_collide` draws all twenty entity slots and
then walks every ORDERED PAIR of them, so its cost is a function of what is on screen:

| the same stage, two frames | ours (C) | the original | excess |
|---|---|---|---|
| a quiet frame (3 live entities) | 32,720 | 22,970 | +9,750 |
| a busy frame (14 live, all 11 actor slots) | 132,094 | 91,038 | **+41,056** |

A mean over those hides the second inside the first — and the second is the frame a player feels.
The user's report was not "the game is slow"; it was "**it slows down when there are a lot of
sprites**", which is a statement about the DISTRIBUTION's tail and which no mean could confirm or
refute. `atari/bench_tier.py` and `atari/census.py` are the instrument that separates them: the
census walks the oracle playing the real game and saves the busiest image it sees, and the bench
prices every stage and routine on THAT image, both sides, under Musashi.

> **A routine whose cost depends on how much is on screen must be priced on a busy frame that the
> game itself produced. Add the per-entity axis to the instrument before concluding a tier is
> small.** Wave D's rule was "subtract the children before you scope a twin from a row". Wave E's is
> its partner: "and ask which frame the row is an average of".

**2. THE ROW WAS SKIPPED BECAUSE ITS CHILDREN WERE ALREADY TWINNED, which is wave D's rule
misfiring.** This slice's biggest child is `draw_sprite_masked_collide` — wave B's twin, at 1.06x.
Subtract it, as wave D says to, and the remainder looks empty. It is not: measured part by part on
the busy frame, the sprite calls are +4,212 and the stage's OWN loops and call glue are **+31,966 at
5.05x**. The C spells the inner pair walk as a seven-argument call, fifty-one times a frame, where
the original has a six-instruction loop and a `bsr`. Subtracting the children is right; assuming the
remainder is small because the children were large is what wave D actually did, and it is not the
same thing.

**3. THE RECIPE HAS A PRECONDITION, AND UNTIL WAVE E NOTHING HAD FAILED IT.** "A faithful
transcription is 1.00x by construction" assumes the original's instruction sequence CAN be
transcribed. Wave E scoped the enemy/actor tier next — `enemies_move_all`, `enemy_move_scripted`,
`actor_script_run`, at 2.5x-3.1x and +13,214 cycles on the busy frame — and found it cannot be:

```
01489a: lea $19380.l,a0          | the per-type handler table, IN THE IMAGE
0148ac: movea.l 0(a0,d1.l),a0    | ...one of the ORIGINAL's own code addresses
0148b4: jsr (a0)                 | ...jumped to directly
```

`actor_script_run` @ 0x14c84 has the identical shape through `$19438`. **Those tables hold the
addresses of the ORIGINAL's handlers, and our handlers are not there.** The reconstruction is
position-independent code at its own link addresses; the image is data. Transcribing `jsr (a0)`
faithfully would jump into the loaded game image and execute the 1988 binary's machine code against
its own absolute addressing.

So every dispatcher in that tier needs a translation the original does not have — image code-address
to our handler — and the C already spells it (`run_actor_handler`, `run_script_arm`: a linear scan
over an address map). **A twin would have to spell the same lookup and would be measured against its
cost, not against the original's `jsr (a0)`.** The 1.00x warrant does not apply, and "do not improve
on the original" forbids a twin quietly substituting a cleverer dispatch.

> **A routine that dispatches through an address table held in the image cannot be twinned.** Check
> for an indirect `jsr`/`jmp` through image data BEFORE scoping — it is the one shape this recipe
> cannot express, and it is why the enemy tier reads 2.4x-4.2x while every twinned routine reads
> 1.0x. The tier's excess is a DISPATCH problem, not a transcription problem.

That leaves the tier's ~13,000 cycles a busy frame open, and honestly open: the legitimate move is
an O(1) dispatch **in the C** — which is a change to a translation that was always ours (the C's
scan is nobody's transcription; the original has no such loop), not a twin, and it needs its own
decision and its own differential. `STATUS.md` carries it as the named next lever.

**Two smaller things wave E added:**

* **A twin CAN have a byte pin even in the frame family, and it is worth laying the registers out to
  get one.** The four earlier frame twins say a byte pin is unavailable because every instruction
  names a global. True of the stage's own code — but `object_pair_overlap_mark` [0x11cfe, 0x11d30)
  names none, carries no immediate-to-Dn operation, and touches only `%a3`-`%a6`. The slice uses all
  seven address registers, so the reconstruction's extra base had to displace one; putting the
  window in **`%a0`** (whose one use, the mask-table clear, has a live-range gap) rather than the
  family's `%a5` leaves those four registers unpermuted and makes 50 bytes byte-identical to the
  original's machine code. **Choose the reserved register to preserve a pinnable span, not by
  convention.** The family's scrapers took a `register` parameter to allow it.
* **The bench must price WHAT THE GAME CALLS, not the `g_*` glue.** A twinned core is substituted at
  its CALL SITE, so the glue still names the C — and `bench_tier.py`'s first A/B after the twin
  landed reported no change at all, because it was still pricing the C. It now resolves `<core>_asm`
  out of the linked ELF and falls back to the glue, which is also correct for a verification-only
  twin (its object is dropped from the link, so the symbol is absent). The table marks each row
  `[twin]` or not, because a 1.04x twin row and a 2.47x C row mean opposite things.

## Where the pieces live

| | |
|---|---|
| the twins | `src/asm/*.S` |
| assembled to one blob | `build/asm/twins.{elf,bin}` — `make asm`, and `make test` first |
| the assemble rule | `tools/recreate_kit/kit.mk`, `$(ASM_ELF)` — generic, driven by `src/asm/*.S` existing |
| the Musashi runner | `tools/recreate_kit/asm_twin.py` — `AsmTwins.call(image, symbol, *args)` |
| the callback door | `tools/recreate_kit/asm_twin.py`'s `DoorCallback` + `TRAP_MODEL.md` — how a twin calls a C core, OFF TARGET ONLY |
| the four checks, shared | `test/asm_twins.py` — `matches_the_c`, `assert_transcribes_the_original`, `cost_case`, `assert_within_the_bar` |
| the FRAME family's shared half | `test/asm_frame_common.py` — the one door table, the candidate arming, the differential, and the `.equ`/window/transcription scrapers the five frame suites share |
| the frame family's slot namespace | `test/test_asm_frame_doors.py` — the cross-file pin no single suite can make: two twins claiming one slot for different cores |
| the differentials | `test/test_asm_scroll.py`, `test/test_asm_sprite.py`, `test/test_asm_text.py`, and the frame family's `test_asm_frame{,_head,_fire,_spawn,_draw}.py` |
| the constant pin | `test/test_constants.py::test_asm_twin_equates_match_the_headers` |
| the seams | `include/scroll.h`'s `ZY_SCROLL()`, `include/sprite.h`'s `ZY_SPRITE()`, `include/text.h`'s `ZY_TEXT()`, `include/frame.h`'s `ZY_FRAME()` |
| the call sites | `src/frame.c`, `src/init.c`, `src/enemy.c`, `src/mothership.c`, `src/highscore.c`, `src/hud.c` |
| the build gate | `atari/build.sh`, "THE ASM-TWIN GATE" and `ASM_SEAM_DEFINES` |

The kit halves (`kit.mk`, `asm_twin.py`) are **game-agnostic**: a project acquires the whole
machinery by creating a `src/asm/` and writing a `.S` in it. Nothing in either file names Zynaps.
