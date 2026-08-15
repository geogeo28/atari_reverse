# Methodology — naming functions & variables

This is where the real work is. The mechanics (load, decompile, apply names) are cheap;
turning `FUN_0001110e` into `game_update` with named state is the craft. The tools are in
`ghidra-pipeline.md`; this doc is *how to think*.

## Golden rule: anchors → outward

You never read a 48 KB binary top-to-bottom. You anchor on **ground truth** and propagate
along the call graph. Sources of ground truth, strongest first:

1. **OS traps** (annotated already) — "this function `Fopen`s a file / sets the palette."
2. **Hardware register access** — `$ffff8240` = palette, `$ffff8800` = sound,
   `$ffff8200` = video base, `$fffffc00` = keyboard. Unambiguous. → `hardware-map.md`.
3. **Imported symbols** — any DRI symbols name whole subsystems for free.
4. **Strings** — filenames loaded, menu text, author credit, score labels. They pin down
   loaders, menus, HUD, and high-score code.
5. **Interrupt installs** — whoever writes `0x456` (VBL) / MFP vectors owns the tick.
6. **Call graph** — name leaf utilities first (a `dbf` copy loop = `memcpy`; a masked
   blit = `draw_sprite`), then the callers that compose them.

## Verify before you name (this bit me repeatedly)

Position and size are hints, **not** evidence. In BuggyBoy: a function I assumed was
`read_input` was actually `flip_screen` (it wrote the video base); one I called
`show_message` was actually `add_score` (BCD score with carries). **Read the decompiled
body and confirm what it touches** before committing a name. Wrong sticky names are worse
than `FUN_`.

### An operand scan that spells ONE encoding finds half the sites

`$535c` in `SWB.PRG` is one word read and written by two routines 134 bytes apart, and the four
instructions that touch it are two `lea $535c.l` / `move.w d0,$535c.l` pairs and two
`lea $535c.w` / `move.w d0,$535c.w` pairs — the **long** and the **short** absolute forms of the
same address. A whole-image scan for `$0000535c` finds two of the four; a scan for the bare word
`$535c` finds all four but also every coincidental data word. Neither answer alone is the operand
census, and "N operand sites" written from one of them is wrong in a way nothing flags. Sweep BOTH
encodings, and say which of the two each hit is — the same trap hides a *caller*, not just a
reader: Wonder Boy's `actor_behavior_type61` has exactly one caller in the image and it is a
`jsr <abs>.w`.

**Then make the census a CASE, not a sentence.** A scan written into a plate is true on the day it
is run and unchecked for ever after; the same scan inside the battery re-runs on every commit. The
cheap form is to take the long-encoding hits and require the word in front of each to be the
instruction the plate claims (`lea <abs>.l,An`, say) — that separates an operand from the
coincidental data a bare address scan also finds, and it turns "one operand site" from prose into a
failing test. Wonder Boy's batch 35 pins fifteen tables this way. Say in the case WHICH instruction
forms it sweeps: `_lea_sites` there covers the two absolute `lea`s and the PC-relative indexed one
and *nothing else*, so it is silent about `pea`, `movea.l #imm` and a pointer assembled at runtime.

**AND THE FORM LIST IS WHERE THE NEXT MISS WILL BE — it is not only `lea` that names a table.** A
census keyed on the instructions that LOAD AN ADDRESS misses every instruction that reads THROUGH one
in a single step. Wonder Boy's batch 39 found the first: `move.w d8(PC,Dn.w),d16(An)` publishes a
frame straight out of a table with no `lea` anywhere, so a `lea`-only scan reported TWO readers of a
table three routines read — and the two it did find were the SHORT absolute form, which is what an
earlier batch's longword-only scan had already missed once. The rule that survives both misses: when
a plate says "N readers", the scan behind it must cover every ADDRESSING MODE that can reach the
address, not every opcode you happened to think of, and the case must name the modes it swept so the
next reader can see the gap rather than trust the number.

**AND A DIRECT-READER CENSUS IS NOT A REACHABILITY PROOF — do not let the case pretend otherwise.**
"No instruction names this address" bounds the routines that name it DIRECTLY. It says nothing about
a block sitting beside an INDEXED table, which is reached through the neighbour's `lea` the moment
the index runs past the table's end — and whether it can is a fact about the index's range, which
lives somewhere else entirely. Batch 35 wrote exactly that mistake down and had it caught: two
sixteen-byte blocks above slot 11's frame tables have no `lea` naming them, and the plate concluded
"nothing can reach them" because the cursor is masked. **The mask ran AFTER the index** — it bounded
the value stored BACK into the record, not the one the `lea` had already used — so the blocks are
reachable padding that happens to repeat the table below, and a cursor one table further on
publishes a word of the *next handler's opcodes*. A negative therefore needs BOTH halves, stated
apart: the direct-reader census, and the index's provable range. If you cannot pin the range, say
the bytes have no direct reader and stop there — that is a smaller claim and a true one.

### An extent from a linear scan is a hypothesis; look every address inside it up first

A scan that runs on to the next `rts` gives the *next routine's* bytes to the one you are reading,
and both of Wonder Boy's recent batches were bitten by it in the same place. Slot 31 came back as
146 bytes and is 78; the 48 bytes above it at `$4fea` are `actor_select_sprite_by_flag`, which the
name map had carried for two batches. (Scanning to the next `rts` from slot 31's entry actually
yields 126 — the recorded 146 was not even that, which is the second half of the lesson: an extent
nobody re-derived can be wrong in a way no arithmetic checks.) Slot 35 came back as `$5336..$53bb`, 134 bytes, and is **38**: below it sit
its own cursor word, its sixteen-word frame table, a 32-byte record template *and*
`scene_copy_record_fields`, again already named. **Before recording an extent, look up every
address inside it in the name map.** It is a one-line grep and it is the cheapest correction
available; a plate written from the scan instead propagates into the port, the tests and the docs
together.

**AND WHEN A PLATE ALREADY CARRIES A DECODED EXTENT, THAT IS THE CHEAP AUTHORITY — not the table.**
Wonder Boy's per-slot plates have said `decoded code runs $x..$y` since the reconnaissance pass, and
batch 35's five measurements matched all five to the byte while the difference-of-entries figure was
wrong for every one of them (552 against 152, worst case). A dispatch table gives you entry points;
subtracting two of them gives you an entry-to-entry SPAN, which is data plus code plus whatever
shared routines happen to sit between. Read the plate first, then verify it from the bytes; quote
the span only as the span. Slots 14..27 carry the same decoded extents and any queue that quotes
their nominal spans should say which figure it is quoting. **Batch 36 then ran the rule as
written and it held six times out of six, and batch 37's eight for eight** —
396/330/408/574/520/652 nominal against 316/234/312/290/424/364 decoded, and then
474/458/352/560/202/520/320/474 against 378/362/264/432/150/424/216/378: every plate matching
the bytes on the first read — which is what
turns "read the plate first" from an anecdote into the cheaper method. Batch 35 hit the worst instance yet: slot 9's dispatch entry to slot 10's is **552** bytes
and the handler is **152**, because SIX SHARED LEAVES — `$2f22`, `$2f46`, `$2f86`, `$2fce`, `$2fe8`
and `$3006`, FIVE of them already ported and only `$2f46` new — sit inside that span between the slot's own `rts` and its
frame tables. A dispatch table gives you entry points, not extents.

### The extent is right and the body is still not yours: scan for edges pointing IN

An extent measured from the entry to the `rts` can be exact and still describe a routine that
another routine runs part of. Wonder Boy's slot 17 (`$3a46..$3b67`) is byte-correct, and `bra.w
$3ae6` at `$48b2` — inside a dispatch row nobody has ported — jumps into the middle of it, at the
five-record spawn burst. Slot 18's final `rts` at `$3e2a` has a second entrance the same way. Batch
31 met the shape from the other side (a handler that *leaves* its own body) and named it "the
boundary moves inside the handler"; this is the same fact seen from the callee.

So when you finish an extent, run one more scan: **every control-flow target in the image that lands
inside your span, from an instruction outside it.** It is the same pass as the "who names this
entry" census — resolve `Bcc`/`BSR`/`BRA` (long *and* short), the absolute `jsr`/`jmp`/`pea`/`lea` in
both widths, and both PC-relative `lea` forms — but asking about the whole range rather than the one
address. Two things come out of it: the port of the *other* routine must call your helper instead of
writing a second copy, and the plate has to say so, because the next reader's only clue is a
displacement 5 KB away. Make it a case: assert the exact set of inbound edges, so a later batch that
adds one fails rather than silently forks the code.

### The same routine at two addresses: check before you transcribe it twice

A dispatch table of near-identical rows is not always near-identical *code*. Wonder Boy's behaviour
table holds one 378-byte body **twice** — slots 20 (`$4118`) and 27 (`$4c5e`) are the same
instructions with four table addresses and two sprite ids changed — and three more rows are another
handler's body with a different contact arm or a different minion type. Five of the block's eight
rows were parametrisations of code the port already had, so what looked like 2,604 new bytes was
about 900.

The check is cheap and worth running before you write a line: **assemble the body you already have
at the new entry's address and diff it against the image.** Displacements move with the base, so a
duplicated routine comes out differing only in its operands — ten bytes in six runs, in this case,
which is a crisper claim than "they look alike" and fails loudly if a later reader is wrong about it.
Do it as a case, and assert the *shape* of the difference (how many runs, how long) rather than a
byte count alone: a count matches by accident, a run structure does not.

Two second-order gains. A parametrised port halves the surface a mutation sweep has to cover — and
raises the value of each mutant, because one flipped constant is now driven by two rows' cases. And
the differences you *do* find are exactly the facts worth naming: they are the six constants that
make the two creatures different creatures.

### A plate correction is landed when the OLD PHRASE GREPS TO ZERO

The cheapest lesson in this file, and Wonder Boy's batch 36 paid for it twice in one batch. A review
returned a list of plates that said something the image does not; the fixes were applied in one
scripted pass of search-and-replace; the batch then certified all four in `STATUS.md`. **One landed,
one landed with its two numbers transposed, and two never matched at all** — a `str.replace` whose
pattern is off by a leading `/*` is a silent no-op, and the script asserted only that *something* in
the file had changed. The certification was written from the findings list rather than from the
file, so it documented corrections that were not there — which is worse than not fixing them, since
the next reader now has a plate that is wrong and a status note that says it is right.

Three rules, in order of how much they buy:

* **Grep the OLD phrase and require zero.** Not "the new phrase is present" — the old one absent.
  That is the only check that catches a pattern that missed, an edit applied to the wrong one of two
  copies, and a second site nobody knew about. Do it per correction, and quote the count.
* **Assert each replacement individually.** One `assert count == 1` per (old, new) pair, before
  writing anything. A pass that edits six plates and asserts once has five unchecked edits in it.
* **Do not let the retraction quote the retracted phrase.** A note reading "an earlier revision
  said X" keeps X greppable for ever and makes rule 1 unusable at that site — and a *ledger* that
  tabulates the retired phrases verbatim does the same thing across the whole tree. Describe the old
  claim ("called the first latch permanent") rather than repeating it, and elide a character in the
  middle where a table really must show the string. This paragraph follows its own rule, which is
  why it names no example.

And the reason it matters more here than in ordinary code: in this workspace the plates ARE the
deliverable. A wrong comment beside right code is not cosmetic — it is the thing the next batch
reads instead of the bytes.

## Classifying a region: two inferences that look like evidence and are not

Before you can name anything you have to decide which bytes are code. Two habits
cost Wonder Boy a whole region each, in opposite directions.

**"High entropy ⇒ packed" is not an inference.** Shannon entropy answers exactly
one question — *is the byte histogram flat?* — and plenty of plaintext answers
"yes". `$ed2a..$f89e` in `SWB.PRG` measured **7.73 bits/byte** and was filed as
UNKNOWN, "near-random, i.e. packed or compressed". The 808 bytes doing most of the
work measure **7.65** on their own and are four **permutation tables**: 200
scanline indices, `0..199`, each value occurring exactly once. A permutation is
*maximally* entropic **by construction**. So are palette ramps, pixel-shift
tables, delta-coded coordinates and anything else that enumerates a range. Entropy
is a cheap *screen*, never a verdict: if it is high, go look at the bytes — the
histogram being flat and the bytes being `00 02 04 06 08 …` are perfectly
compatible. (What was actually in that region: a trace-decrypting Copylock. See
`projects/wonderboy/notes/architecture.md` §2.5.)

**Idiom density has a blind spot shaped exactly like a jump table.** The usual
test — "code runs ~15 `rts` per 1000 words with hundreds of `bsr`/`lea`; data runs
0" — classified `$8fce..$989c` as DATA on "0 `bsr`, 0 `movem`". It is twelve
sprite blitters. **Leaf code entered only through a pointer table calls nothing
and saves nothing**, so its `bsr`/`movem` counts are zero *by construction* — the
one region the method mis-reads is precisely the one it is blind to. Its `rts`
density (14.2/kW) said CODE all along. Meanwhile the same program's ASCII dialogue
block scores **78 false `bsr`** (`$61xx` is `'a'` + any byte) and its graphics
block scores 14 `rts`. Practical rules:

* Score on **density per 1000 words**, not raw counts, and weight `rts`/`dbf`
  (which leaf code still has) over `bsr`/`movem` (which it may not).
* Ask "could this be reached only through a pointer table?" before believing a
  DATA verdict. Decode any nearby longword table and check whether its entries
  land inside the region — 12 in-range targets settled this one in a minute.
* When you ask "did Ghidra create a function here?", filter by **function body**,
  not by entry address. The Wonder Boy region was reported as having no function
  in it; `FUN_0000ecca` starts 36 bytes below the boundary and its body reaches
  well inside.
* **A correct CODE verdict is not coverage.** The rule above fires on a *DATA*
  verdict, and that is not enough: the same trap caught Wonder Boy a second time
  3 KB away, inside a region the table had always called CODE. `$83b6..$8dfe` —
  16 unrolled scroll blitters behind the longword table at `$8366` — sat in no
  Ghidra function at all, because the only way in is
  `movea.l (0,a2,d1.w),a2 / jmp (a2)`, and nothing in the region table was wrong.
  So ask the *coverage* question separately from the classification one: **which
  parts of a CODE region does the disassembler actually reach?** Subtract every
  function body and every unattributed instruction run from the region and read
  the holes; that one screen found 2,632 bytes of live blit code and is written
  up in `projects/wonderboy/recreate/PORTABILITY.md` §8.1.

## Naming variables

Name a global by how it's *used*, across functions:
- incremented every VBL → `frame_ctr`; counts down to 0 then triggers → `timer`.
- ANDed with joystick bits / compared to key scancodes → `input_state`.
- written to `$ffff8240` region → a palette buffer; toggled 0/N and used to pick a screen
  base → `flip_idx`.
- BCD digits `0x30..0x39` assembled for display → a score/time string.

## Jump tables → many names at once

Decode an offset table to reveal a whole family of handlers (and, for course/level
scripts, the *data format* that indexes it):

```python
import struct
d = open("bin/GAME.PRG","rb").read(); HDR = 28
base_img = 0x<table_image_off>            # Ghidra addr - load_base
for i in range(N):
    off = struct.unpack(">h", d[HDR+base_img+2*i : HDR+base_img+2*i+2])[0]
    print(i, hex(0x10000 + base_img + off))   # handler address (Ghidra)
```
Then read each target and name it (`evt_collision`, `evt_flag_gate`, …). Where handlers
are jump-only stubs (never `call`ed), `ApplyNames` disassembles + creates them.

## The loop, and honesty

Read `decomp.c` → name what you can confirm → `reapply.sh` → re-read (now more of the
program is legible, unlocking the next layer). Repeat until coverage is high. When you
name a leaf helper from **call-context** rather than a full read, tag it with a trailing
`# ctx` in `names.txt` (category-true names like `draw_hud_*`/`snd_*` are fine, but mark
them refinable rather than presenting a guess as fact). Untagged = verified from the body.
If you explore/rename in the GUI, fold those edits back with `dump_names.sh` so `names.txt`
stays the source of truth.

## What "done" looks like

`main` and the frame loop read as pseudocode; every function has a meaningful name; the
key globals (state, buffers, tables) are labelled; jump tables and asset formats are
documented. See `projects/buggyboy/README.md` for a finished example (91/91 functions).

## "Verified" ≠ "complete": the checkpoint trap (this bit us on sound)

A green differential test proves *our code ≡ the original, up to where the oracle can run it*.
It says **nothing** about behaviour past that point. Interactive functions that never return under
the oracle (they wait on the IKBD / a `mzflag` spin / Vsync) are verified only to a **checkpoint**
PC — the deterministic prefix runs, the tail is read-verified. That is fine, *as long as you track
what the checkpoint hides*.

We didn't, once. `update_highscore` was checkpoint-verified at `0x12450`/`0x123e6` — one instruction
*before* its `play_event_tune` calls. The prefix stub returned there and `game_main.c` called it and
moved on, so the game-over jingle and the name-entry jingle were never reconstructed and never
reachable in the playable build. Three tune triggers sat on the far side of a "91/91 verified" line.
The suite stayed 100% green the whole time the game was silent; it took running on hardware and a
human ear to notice (see [`on-target-execution.md`](on-target-execution.md) — same blind spot, applied
to a *missing feature* rather than perf).

Lessons, now guardrails:

- **A checkpoint is a suspicious boundary — ask what's on the other side.** If the deferred tail
  contains sound / palette / trap / I/O pokes, the harness cannot see them *and* they may be silently
  absent from the PRG. Note it explicitly in `STATUS.md`, don't let "read-only tail" read as "done".
- **Audit call-graph coverage, not just per-function correctness.** Grep the disassembly for every
  `play_event_tune` / `INITTUNE` / `INITFX` (and each trap / palette poke) call site and confirm each
  is both reconstructed *and* reachable in the playable build — or logged as intentionally omitted.
  That one grep would have caught the silent tunes immediately.
- **Don't let the headline count flatten the distinction.** "N/N verified" should still say which are
  checkpoint/piecewise-verified; a deferred tail is a *known gap*, not a finished function.
- **The playable build is its own verification surface.** A cheap on-target smoke check ("does every
  subsystem produce output — sound triggers, palette, input?"), e.g. a PSG-write / border-colour probe,
  catches this class of gap that the differential suite is structurally blind to.
## The seeding hole a mutation sweep finds: zeros copied over zeros

A differential case seeds the bytes a routine is supposed to touch, and asserts on those. That is
enough for a blit whose SOURCE is data in the image — an over-copy then moves real bytes into a
destination the oracle left alone, and the whole-image diff catches it. It is **not** enough for a
blit whose source is another region of the same seeded medium: a **screen-to-screen** copy that runs
one row too far, or one longword too wide, reads ZEROS from the unseeded part of the source and
writes them over ZEROS in the unseeded part of the destination. Both sides agree, the write-set
check sees no stray write (the *oracle* did not make one either — the mutation is in the port), and
the case stays green.

Found on Wonder Boy's `$d93a` region restore (`projects/wonderboy/recreate/STATUS.md`, "The status
panel's third tier"), where two mutations survived the first sweep for exactly this reason: a
restore moving 32 rows instead of 29, and a routine that is a bare `rts` in the original quietly
blitting a whole cell. The same probe on the *bitmap* blits in the same file kills them outright, so
the shape — not the file — is what carries the hole.

The fix, and the two parts of it that are not obvious:

- **Seed a MARGIN.** Widen every region a case seeds by a few rows and bytes on BOTH media, and
  leave the margin out of the write set the run may touch. An over-copy then lands on filler.
- **Key the filler on the ADDRESS, not on a row index.** Widened regions overlap (two panel cells
  side by side share rows), and two overlapping bands must produce the same byte at the same address
  or the later poke silently rewrites the earlier one — turning the case's own expectation into
  whatever the seeding order happened to be.

More generally: **a mutation that survives is a question about the seeds before it is a question
about the code.** Ask what the mutated code would have had to write, and whether any byte of the
case could have told the difference.

## The second seeding hole: a case keyed to the wrong place

The margin above catches a routine that touches bytes PAST where a case seeded. It does not catch a
case that seeded the right bytes in the WRONG PLACE. A differential case whose expected values are
**computed from the same image bytes it seeds** is self-consistent wherever those seeds landed: the
model reads the byte the routine will read, the oracle reads it, the reconstruction agrees, and the
case is green — while testing nothing it claims to be about.

Found on Wonder Boy's `$10a2`, the collision-map step probe
(`projects/wonderboy/recreate/STATUS.md`, batch 10). The routine probes the cell at
`(x - half_width - STEP) asr.w #4`; the battery keyed its map pokes off `x - half_width` alone. So
every tile a case planted sat one cell from where the routine actually looks, and each case passed
on whatever the address-keyed filler happened to hold at the real probe. All cases green, all of
them named after a tile they were not testing — until a mutation (the ground test stepping by the
wrong map's stride) SURVIVED, which is the only thing that said so.

The rule is about the KEY, not about the extent:

- **Derive the probe geometry from the ROUTINE's own arithmetic**, transcribed from the
  disassembly, and put it in one named function (`probe_cell()`, here). Key every seeded byte off
  that function's answer as an OFFSET from it (`{(column, row): tile}`), never off a coordinate the
  case happens to have to hand.
- **A margin does not help here.** Widening a seeded band makes an over-run land on filler; it does
  nothing for a case whose whole expectation sits one cell left of the truth.
- **Only a mutation asks the question.** A wrongly keyed case still asserts, still names a tile and
  still reads correctly. Mutate the geometry the case is about — the shift, the stride, the sign —
  and see whether anything reddens. Nothing reddening is the finding.
- **A derived key is necessary and not sufficient: seed each TERM of the arithmetic at a boundary
  where it matters.** The same hole recurred one layer up in batch 11 (same file, the collision-map
  batch): `probe_cell()` was in place and every case keyed off it, yet dropping the `subq.w #1` that
  makes the probe row the pixel ABOVE the actor's y reddened NOTHING — every case had put the actor
  one pixel INSIDE its row, where `y` and `y - 1` name the same cell, so that term of the derived
  expression never changed the answer. What killed the mutation was a case standing the actor
  EXACTLY on a cell boundary. Read the arithmetic term by term and ask, for each, which seed value
  makes it observable at all.
