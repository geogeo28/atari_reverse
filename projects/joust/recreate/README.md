# Joust — differential reconstruction

Readable C for Joust (Atari ST, Gamex release), each function **proven byte-for-byte equivalent to
the original 68000 code**. This is the *recreate* track: faithfulness beats correctness every time,
so original bugs are reproduced rather than fixed.

The machinery is shared — [`tools/recreate_kit`](../../../tools/recreate_kit/README.md) loads the
`.PRG` into a flat image, runs the original under a Musashi 68000 oracle and this project's
compiled C on the same image, and diffs the result. Everything game-specific lives here. For *why*
the method is differential rather than byte-matching, read the worked reference project,
[`projects/buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md).

Progress and per-function verification notes: [`STATUS.md`](STATUS.md).

```
project.toml      binds this directory to the kit (paths, load base, image size)
Makefile          three lines: KIT + GAME + include $(KIT)/kit.mk
include/addrs.h   the globals MORE THAN ONE subsystem touches, by Ghidra address (mirrors ../names.txt)
include/joust.h   public prototypes + what several subsystems share: screen geometry, the 68000
                  primitives (loop_passes, lsr32/ror32, divu_w) and the object record
include/<sys>.h   one per subsystem (draw.h, object.h, …): only what that layer alone touches —
                  a constant earns its way into addrs.h/joust.h when a SECOND layer needs it, and
                  is never spelled out in two headers (no translation unit includes both, so a
                  drifted copy would compile silently; the test_*.py mirror pins scrape by header)
src/*.c           one file per subsystem: the readable core plus its `g_<name>` glue
                  (the kit also links its own src/*.c into the candidate — the Dosound ledger)
test/harness.py   the kit-binding shim
test/abi.py       how each of Joust's calling conventions is driven under the oracle
test/test_*.py    the differential batteries
```

## Running

```bash
make venv      # once: .venv + pytest/pytest-xdist (see requirements.txt)
make test      # build the candidate + the shared oracle, run the suite across cores
make oracle    # rebuild only the shared Musashi oracle
make clean     # this project's build/ only — the oracle is shared, see the kit README
```

## Calling conventions, and why `test/abi.py` exists

BuggyBoy is hand-written assembly and passes everything in registers. Joust is compiled C: most of
its routines take arguments on the **caller's stack** (`4(a7)`, `8(a7)`, …) and write their results
back into that same block. The oracle starts a function with A7 at the top of the image, and the
differential deliberately stops comparing there — the C reconstruction has no machine stack to
match — so a frame built at A7 would be invisible to the diff.

`test/abi.py` fixes that by poking a two-instruction 68000 stub into free image space and entering
the oracle there:

```
movea.l #ARG_BLOCK-4, a7      ; the argument block now lives in ordinary, diffed memory
jmp     <routine>             ; its rts pops a sentinel pre-poked into the slot below
```

Pre-poking the return slot instead of using `jsr` means the oracle makes **no stack write at all**,
so every byte it writes is the routine's own output. A second variant handles register-argument
routines whose results land in D1/D2 (which an image diff cannot see): it `jsr`s the routine and
stores D1/D2 through A0 with the same `move.l d1,(a0)+ / move.l d2,(a0)+` pair the game itself
uses. The candidate glue mirrors that store, so both sides are compared on identical bytes.

### A glue may refuse a call the original makes

Glue is normally a bare forwarder, but the oracle's instruction cap has no candidate-side
counterpart: a reconstructed routine that spins for ever hangs a pytest worker with **no output at
all** under `-n auto`, which is the one failure the differential cannot report. So a glue in front
of an unbounded spin may add a guard the original has no trace of, and report the refusal through
its own return code rather than through the routine's result. `g_pause_until_key`
(`src/input.c`) is the worked instance, with `_pause_glue` in `test/test_input.py` putting a
wall-clock deadline on every candidate-side entry into the spin as the second layer. The
reconstructed function itself stays uncapped and faithful — the guard lives in the glue precisely
so that it does.

`g_check_highscore` is the second, and its reason is different: its loop is not merely uncapped, it
has **no exit no staged input can reach** — on either side. The oracle blocks in the joystick
reader's IKBD wait on the first pass, and the candidate's entry screen clears the "has typed
something" flag, so RETURN and fire are ignored on the pass that follows and the console has only
one key to give. The glue therefore runs everything up to the loop head and reports
`CHECK_HIGHSCORE_ENTERED`, which is exactly the state the oracle has at its checkpoint.

`g_title_screen` (`src/init.c`) is the third, and it is the same shape as the second with one thing
in its favour: **no run can go round `title_screen`'s attract loop twice**, so stopping after one
pass is not an approximation, it is every reachable run. Either the pass reads a key that decides
the game — `'1'`, `'2'` or Ctrl-C, all three diffed to their own end — or it falls through to the
IKBD wait at `0x10bb8`, which ends on neither side. So the glue runs the painting and exactly one
pass and reports `TITLE_IKBD_WAIT`, which is the state the oracle has at its checkpoint.

`g_read_joysticks` (`src/player.c`) is the fourth and the smallest: the refused part is six
instructions. `read_joysticks` clears `ikbd_packet` and then waits on it, so on **every** input both
cores block — the glue runs the clear (through the shared `request_ikbd_packet`, not a copy of it)
and reports `READ_JOYSTICKS_IKBD_WAIT`, which is the state the oracle has at its `0x11db0`
checkpoint.

`_start`'s two glues are the fifth and sixth, and they are the only ones that refuse a call they do
not *contain* the spin of. `_start` is nothing but twenty-one `jsr`s and a `bra`, so each of its
passes carries whole routines whose own exits do not come back, and the refusal is a question about
**the staging** rather than about the routine:

- `g_start` runs the four one-shot calls and the frame's first four, and refuses unless the staged
  console key would make `title_screen` **return** — which only `'1'` and `'2'` do. It asks
  `title_key_chooses_game`, the same pair of `cmp.w`s the attract pass decides with, so the bound has
  one definition rather than one per caller.
- `g_start_frame_pass` runs one whole lap and refuses a console key `poll_quit_key` would not come
  back from, and a finished game whose leader has taken the record — which would send
  `check_highscore` into its unleavable entry loop. Both questions go to the routine that owns them:
  `poll_quit_key_comes_back` and `check_highscore_comes_back` live next to their routines and decide
  through the very constants and helpers those routines decide with.

**A staging refusal should be the routine's own gate, not a blanket over it.** The second guard was
first written as "refuse any `game_over_flag`", which is true but coarse — and coarse cost a mutant:
with every finished game turned away, nothing ever ran `check_highscore` for real and deleting the
call from the frame was invisible. Asking the routine's exact question instead lets a finished game
whose record still stands through, and that case holds the call.

**And "it cannot be armed without fabricating a record" has to be checked against the routine's
FIRST observable effect, not its interesting one.** Three of `_start`'s per-frame calls are asleep on
every frame the walk reaches, and all three were disclosed as unreachable on that reasoning. Two of
them were not: `lava_troll` gates on `wave_num` and then ticks a step timer, `animate_ground_shrink`
gates on a latch and then decrements one — both SCALARS, both reached before any table is indexed, so
a one- or two-byte poke of the gate's own operand wakes them without inventing anything, and both now
have positive cases and dead mutants. Only `dissolve_platforms` really is forced: its first act is to
walk `effect_table`, so nothing is observable until a slot's kind has indexed a sprite pointer, and
arming it means writing the record another subsystem writes. The rule of thumb: before disclosing a
call as unarmable, read forward to its first store and ask what the cheapest input that reaches it
is.

### Entering a loop mid-body, so that a pass can be diffed at all

The cost of that refusal is that the loop body is verified separately, and by a glue with **no
counterpart C function**: `g_hiscore_entry_pass` runs one pass *rotated* to start where the oracle
can start. The oracle is entered at the loop's colour-cycle tail (`0x14494`), runs round the branch
back to the head and through the keyboard poll, and stops at the joystick call it never returns
from (`0x14490`); the glue makes the same two calls.

`g_title_ikbd_pass` is the same rotation for what lies *past* `title_screen`'s wait: the oracle
starts **at** `0x10bb8` with a reply already in `ikbd_packet`, so the wait falls straight through
and the fire test, the mode test and the `rts` are ordinary diffed work. Starting any earlier is
useless for the reason `hiscore_joystick_input` meets — the routine clears `ikbd_packet` on the way
in, so the poke does not survive. Unlike the entry-loop rotation this one drives a **real function**
(`title_ikbd_pass`) and so holds order as well as presence, its two steps being a wait and a test of
what the wait produced. It is still not a bare forwarder: it refuses a packet pointer that is zero
or outside the image, because the routine dereferences that pointer and the two cores disagree
about what lies outside — the oracle's callbacks answer `0`, while the candidate would index host
memory past the end of the buffer.

`g_start_frame_pass` is the fourth rotation and the largest — a whole frame of the game. `_start`'s
loop blocks on its ninth call, so the oracle is entered at the **tenth** (`0x10036`), runs calls
10..21, takes the `bra` at `0x1007e` back to `0x10018` and stops at the ninth again: one lap, cut
where the wait is. It is walked over a **chain** of successive frames rather than the opening one
alone — each lap's staging is the state the previous lap produced, stepped past the wait through
`read_joysticks`' own rotated entry — because the opening frame's head is nearly inert: the floor and
ground timers have not come round, there are no eggs yet, and the platforms are being repainted over
nothing. The stale `D0`/`D2` `update_objects` reads on entry are a different matter, and the walk
does **not** rescue them: over sixty frames neither register changes a byte of program memory (they
land in the oracle's saved-register slots and nowhere else), so they stay a disclosed limit rather
than something a deeper walk would fix.

`g_read_joysticks_pass` is the third rotation, for what lies past `read_joysticks`' wait at
`0x11db0`, and it refuses the same two packet pointers for the same two reasons — through the same
`ikbd_packet_readable` predicate, so the bound has one definition rather than one per glue. What
makes it worth its own paragraph is that its pass holds **order as well as presence**. Its two steps are
`control_player` on each player, and most frames they touch disjoint memory — one object record
each — so the order would be invisible. On the frame both riders take their last life they share
`players_alive` and the message table: the first to run posts its per-player banner into slot 0 and
the second the shared GAME OVER into slot 1. Swapping the calls swaps both records, so on that one
input the differential holds the sequence rather than the disassembly having to.

**A refusing glue needs a wall-clock deadline as well as a probe.** The probe is one layer, and a
gap in it costs the whole worker: every candidate-side entry into a glue whose pass contains a spin
goes through a `threading` deadline, exactly as `_pause_glue` does for the pause spin. There is one
`_within_deadline` for the project — `test_player.py` defines it and `test_init.py` imports it — and
it takes the glue as an argument, since between them they drive four (`g_title_ikbd_pass`, `_start`'s
two, and both of `read_joysticks`'). The rule outlives the thread, too: `_start`'s frame-loop driver
runs its candidate in a forked CHILD, and the parent reads that child's report through a `select`
deadline for exactly the same reason — a blocking read with no bound is the same silent hang.
That second layer is what makes non-termination *assertable* rather than silent — with it,
deleting the probe or narrowing the wait fails as an ordinary red instead of hanging, which is the
difference between a mutation sweep that scores those mutants and one that cannot.

### A limit inferred from the harness's shape is a hypothesis, not a finding

Splitting a routine at its wait leaves an obvious-looking hole: no case runs the halves *in
sequence*, so the composition is unheld and deleting the wait is unobservable. `read_joysticks`
disclosed both as surviving mutants on exactly that reasoning — and both were wrong.

The reasoning came from the **oracle**, which models no interrupts and so can never leave the spin.
The **candidate** is a shared library in this process, and the wait is `volatile` precisely because
something outside the routine writes that slot. A `threading.Thread` poking the ctypes image *is*
the interrupt. `test_read_joysticks_blocks_until_a_reply_lands` runs the whole reconstructed routine
on a thread, polls until its own `clr.l` lands, asserts it is **still blocked** a quarter-second
later, and only then stores the reply pointer — which pins clear → block → read in order, and kills
both mutants. It is deliberately **not** a differential: there is no oracle run to compare with,
which is the entire reason it can exist. It pins the reconstruction's control flow, not its
equivalence, and it is the only test in this project that does.

Two guards keep the dwell from being a race. A wait-less build that somehow survived it is then
handed the reply and *still* fails, because it read the packet it had just zeroed and both target
speeds come out of the riders' own `vx` instead of the sticks. Neither layer can go green on a build
that does not wait.

So: before writing "the harness cannot see this", ask whether that is a property of the *oracle* or
of the *reconstruction*. The two disclosed survivors here were the first kind wearing the second's
clothes, and the experiment that settled it was fifteen lines.

**The same experiment scales to the whole program.** `_start`'s per-frame loop looked like the
extreme case of the same hole: two rotations diff the calls either side of the ninth, and nothing
composes them or shows the loop lapping. It is the oracle's limit again, and the same thread answers
it — `test_start_laps_its_frame_loop_when_the_ikbd_replies` runs `start` itself, waits for
`read_joysticks`' clear, checks the frame's HEAD has run and its TAIL has not, dwells to prove the
block, then plays the interrupt and watches the next lap arrive. Each half is read off one marker
byte only that half writes, and *that* claim is checked against the oracle's own write sets for the
very frames the driver walks rather than left as a comment. It found a real mutant the differentials
missed: deleting `frame_pass_head` from the loop leaves both rotations green, because each glue calls
the head itself.

Two things make that test practical rather than reckless. It runs in a **forked child**, because
`start` never returns — a thread driving it would spin in the wait for the rest of the session and
cost a core under `-n auto` — and because a frame loop walking evolving state is the one place a wild
pointer could take the pytest worker down with it. And its staging is the state the **game itself**
produces from cold, not noise: `render_object_body` dereferences the destination it stored on the
frame before, so a constructed image is not merely a different case, it is a crash.

**What that rotation buys is presence, not order.** No ordering anywhere in the entry loop is held
by the differential on the C side — not in `check_highscore`'s own `for (;;)`, and not in the glue
either. The steps of a pass touch disjoint memory (the colour cycle writes `draw_x`/`draw_y`; the
keyboard poll writes the letter and the screen and reads neither), so a final-image compare cannot
distinguish one order from the other, and swapping the glue's two statements leaves the whole suite
green. The order in both is **transcribed from the disassembly and asserted there** — the four
`bsr` encodings pin what the ORIGINAL does — while presence is what the diff holds, and only in the
glue: nothing executes `check_highscore`'s loop at all, so deleting a call from it is invisible too.
`STATUS.md` lists each of those as a surviving mutant rather than leaving the gap implied.

The general lesson is worth stating once: **a rotated single pass verifies the steps; it verifies
their sequence only where the steps share state.** Where they touch disjoint memory — the entry
loop's colour cycle and its keyboard poll — only the original's encoding can say what order they run
in. Where they do share it the order comes free, so the work is finding the input that makes them
share: `g_read_joysticks_pass` gets one from the single frame on which both riders take their last
life, and `g_title_ikbd_pass` from a wait whose second step reads what the first produced.

## `project.toml` — the heap waiver

Joust's data segment runs to `0x2b7ae`, which covers the kit's modeled Malloc heap
(`OS_HEAP_BASE = 0x20000`). That is why `project.toml` sets `tos_malloc_unused = true`. The
evidence is an exhaustive **byte scan** of text+data (there is no bss) — deliberately not a grep of
a disassembly listing, whose linear sweep drops trap sites after desyncing on data:

- 22 `trap #1` (`4e41`) sites exist, and every one is immediately preceded by an in-line
  `3f3c <sel>` selector immediate. No selector is ever loaded through a register.
- Those selectors are `0x19 0x20 0x3c 0x3d 0x3e 0x3f 0x40 0x4c` — **no `Malloc` (0x48), no
  `Mshrink` (0x4a)**. The Gamex loader does the memory setup before the game runs.
- The byte pattern `3f 3c 00 48` / `3f 3c 00 4a` occurs nowhere in the image at any alignment.

So no modeled allocation can ever be handed out on top of the program. Two guards back the
declaration up rather than trusting it: `harness._vet_os_memory_map()` refuses the overlap at
import unless the flag is set, and `emu._vet_no_malloc_over_program()` fails **every run** in which
the oracle actually serves a `Malloc` — because there both sides would scribble the same bytes over
the same program area and the diff would come back clean while proving nothing. The second sits in
`emu.run()` (not in `differential()`) so oracle-only runs are covered too, and counts serviced
`Malloc` traps rather than watching the bump pointer — `Malloc(-1)`, the "largest free block?"
query, is served without moving it. `test/test_heap_guard.py` pins both.

For the general lesson — why a trap census must be a byte scan — see `docs/m68k-disassembly.md`.
Joust's own dropped site is the `Bconstat` at image `0x11c2c`, which the desynced listing renders
as `ori.b #$4e4d,d1`.

## Staged files — an honesty note

Joust reads two files at startup:

- `HIGH.SCO` (26 bytes) — present in `../bin/`, authentic.
- `JOUST.MUR` (0x7d00 bytes, read straight over the program's own data segment at `0x23aae`) —
  **not shipped**. Despite the extension it is the **title picture**, not music: 0x7d00 = 32000
  bytes = one whole low-res framebuffer, and `title_screen` copies exactly that buffer to
  `screen_base`. Better still, **its loader is patched out** — `init_system` has a `bra.s` at
  `0x10224` jumping over it (and another at `0x10204` over a raw-floppy loader), so the Gamex
  release loads no external file but `HIGH.SCO` and runs on the placeholder picture the PRG
  carries. Staging that placeholder is not a compromise — it is what the shipped game does.

`HIGH.SCO` is staged by `test_input.py`'s quit battery and by `test_init.py`'s `init_system` and
Ctrl-C ones; `JOUST.MUR` is staged by nobody, because nothing opens it. `title_screen`'s battery
pokes **noise** over the buffer it would have landed in instead — which is a stronger input than
either the real picture or the PRG's placeholder, since a copy from the wrong address then shows as
a diff. Those bytes are constructed and are not a stand-in for authentic picture data —
`test_title_screen_paints_the_placeholder_picture_the_prg_carries` is the one case that runs on the
buffer's shipped contents, and it is the only one that says anything about the real artwork.

## The TOS traps Joust needs

The kit's shim originally covered only what BuggyBoy needed. The seven Joust also traps — `Super`,
`Giaccess`, `Fcreate`, `Fwrite`, `Random`, `Bconstat`, `Bconin` — are now modelled kit-wide;
`tools/recreate_kit/TRAP_MODEL.md` records what each one does and, per trap, what it deliberately
does **not** capture. `test/test_os_traps.py` pins the semantics with hand-assembled 68000 stubs.
Read the "not captured" notes before reconstructing a trap-bound function: two of them bound what
can be verified at all — a run delivers at most one console keystroke, and the whole program
executes in supervisor mode, so Joust's floppy routine never takes its user-mode `Super` path.

**The raw-floppy routine at `0x152dc` is unverifiable, not merely pending — leave it off the
reconstruction list.** The `Super` limitation above is the weaker one. The routine also reads the
PSG select port directly (`move.b $ff8800,d1` at `0x15544`), and the kit rejects **any** direct PSG
read on its own: the ledger records writes only, so there is nothing correct to return. That
rejection does not depend on the mixed-path guard, so *no* `emu.run` reaching that instruction can
go green, whatever else the run does. It is blocked on the oracle gaining a real PSG read model, not
on someone writing the C. Do not "fix" a rejection by narrowing either guard — that restores the
fabricated `0` read they exist to prevent (`tools/recreate_kit/TRAP_MODEL.md`, Phase 3).

The XBIOS `Dosound` ledger the harness compares off-image sound against (Joust has four `Dosound`
sites) is kit-wide — `tools/recreate_kit/src/dosound_log.c`, linked into every candidate.
`Giaccess`, by contrast, needs no ledger: it reads and writes an in-image register file, so the
differential covers it directly.
