# The asm twins — what they are, and how to add the next one

A **twin** is a hand-written m68k transcription of the **original binary's own instruction
sequence** for one routine, carrying the C signature of the verified core it stands in for. The
target build (`../../atari/build.sh`) links the twin instead of calling the C; the host differential
build never sees it.

This directory holds three:

* `sprite.S` — the four **unclipped** masked sprite blitters (0x153b2 / 0x15408 / 0x154a4 / 0x15586);
* `restore.S` — the five **restore** blitters (0x14d58 / 0x14d6a / 0x14d80 / 0x14d9a / 0x14db8) and
  the **ring-seam copy** (0x156ae);
* `clipped.S` — the four **gated** (clipped) blitter bodies (0x14e1e / 0x14f06 / 0x1505e / 0x15230),
  and the one file here that is **not byte-identical** to the .PRG. See "The gated twin's declared
  substitution" below, which is where the exception is stated and bounded.

The recipe is written out at length in
[`projects/zynaps/recreate/src/asm/README.md`](../../../../zynaps/recreate/src/asm/README.md),
which is where five waves of it were learned; this file records only what is Flying Shark's own.
**Read that one before scoping a new twin** — its "What wave D added" is where the rule for when NOT
to write one is stated.

## Why transcription and not optimisation

The C cores in `../` are already proven byte-for-byte equivalent to the original — that is what
`test/test_sprite.py` does, against the shipped 1988 binary executed under Musashi. So when a core
is three times the original's cost, the fast version is not something to invent. It is sitting in
`../../../out/prg_dis.txt`, and it has the one property no rewrite can promise:

> **An asm twin that faithfully transcribes the original's instruction sequence is 1.00x by
> construction.**

Measured here: every body is **byte-identical** to the .PRG's, so its per-row cost is the original's
exactly, and a twin's whole excess is a FIXED per-call frame — 302–344 cycles for the sprite twin,
198–256 for the restore one, 56 for the seam copy (`test/test_asm_sprite.py`'s `TWIN_FRAME_CYCLES`
and `test/test_asm_restore.py`'s `RESTORE_FRAME_CYCLES` / `SEAM_FRAME_CYCLES`). Those are the C-ABI
entry's numbers; what the GAME pays is smaller again — see "The two entries" below.

The corollary matters as much: **do not improve on the original.** A cleverer instruction is a
divergence you now have to justify, in a file whose whole warrant is that it does not diverge — and
this project has already met the case in its mildest form. gas spells `move.l #$ffffffff,dN` as
`moveq`: two bytes shorter and eight cycles *cheaper*, and not what the original does. It is laid
down as the encoding the original used (`sprite.S`'s `MOVEL_ALL_ONES`), because a cheaper divergence
is still a divergence and this one would have put every body two bytes out of step with the .PRG.

## The chain of evidence

    original  ==(test/test_sprite.py)==  C core  ==(test/test_asm_{sprite,restore}.py)==  asm twin

Both links are byte-exact **over the whole image**, so a twin is pinned to the original transitively
and neither link has to be re-derived. The twin is never compared against a second oracle run: the C
is already known equal to the original on exactly those cases.

Six things judge a twin, and a new one needs all six:

| check | where | what it catches | proved able to fail |
|---|---|---|---|
| the differential | `test/test_asm_{sprite,restore,clipped}.py` | any byte the twin computes differently, anywhere in the image | `lea 146` → `lea 144` in one sprite body: 21 cases red; `SCREEN_ROW_BYTES` 160 → 158 in `restore.S`: 34 cases red; the same `lea` in `clipped.S`: 5 cases red |
| the transcription pin | `test_the_twin_transcribes_the_original` | a body that stopped being the original's own machine code | the same three mutations, named by address (for `clipped.S`, by SEGMENT) |
| the cost pin | `test_the_twin_costs_what_the_original_costs[_less_the_substitution]` | a translation that quietly costs cycles | dropping `%d7` from the `movem` pair; the same `restore.S` mutation moves all five; every `clipped.S` mutation moves all four |
| the build gate | `../../atari/build.sh` | the twin not actually being what the game calls | dropping `-DFS_ASM_SPRITE`: exits 1. And per twin: unhooking only the restore seam names `restore_blit_rows_asm` |
| the SHIPPED bytes | `../../atari/assert_twin_bytes.py`, run from `build.sh` | the object that ships not being the one the suite pinned | `lea 138` → `lea 136` in one body, and `SCROLL_WRAP_COPY_LONGS` 80 → 79: each named by address. For `clipped.S`, a segment address off by two and a segment dropped from the build line: named, and named as unpinned |
| no conditional assembly | `build.sh`, one `grep` | the two assemblies of a `.S` being able to differ at all | an empty `#ifdef` in either file: exits 1 |

...and `clipped.S` needs **four more**, because it is the one twin whose bodies are not the .PRG's
bytes. They are the substitution's own pins and they are in "The gated twin's declared substitution"
below, with what each was proved able to fail on.

The build gates are the ones worth dwelling on, and there are three because this substitution fails
**silently** in three different ways.

*The twin might not be what the game calls.* Drop `-DFS_ASM_SPRITE` and `../sprite.c`'s
`BLIT_SPRITE_ROWS_UNCLIPPED` resolves to the C again, the twin still assembles, still links, still
exports its name, and the game still draws exactly the right pixels — three times slower, with
nothing but the frame rate to say so. `make test` would not notice, because the C is not wrong, only
slow. So the gate asks the objects directly: the twin must be **defined** by an asm object and
**referenced** by the core object. Neither list is a literal in `build.sh` — the names it requires
DEFINED come out of `../../include/sprite.h`'s prototypes, the names it requires CALLED out of
`../sprite.c`'s own seams — so a twin renamed in one place and not the other reddens instead of
leaving the gate vouching for a symbol nobody defines.

*The object that ships might not be the one the suite pinned.* `test/test_asm_sprite.py` compares
the KIT's blob — assembled by `kit.mk` with its own flags, `-DRECREATE_HOST_DIFFERENTIAL` among them
— and `build.sh` assembles the same `.S` with a disjoint set. So `build.sh` compares the SHIPPED
object's spans against the original's own bytes (`FLYSHARK.IMG`, staged minutes earlier by
`gen_image.py`), which needs no artefact of the suite's at all.

*And the two assemblies must not be ABLE to differ,* which the span pin cannot say because the C-ABI
prologue and the width ladder are outside every span. An `#ifdef` is the only way they could — the
kit's callback door selects its stubs on exactly that macro — so `build.sh` refuses conditional
assembly in a `.S` outright.

And the callee-saved check is the kit's, not this suite's: `AsmTwins.call` seeds every callee-saved
register and requires it back, which is what caught the `movem` mutation above. Nothing else can —
the image, the return value and the cost are all a correct twin's.

## The two entries: what the suite drives, and what the game calls

The kit's `AsmTwins.call` drives a twin through the **C stack ABI**, so the entry the SUITE pins has
to be a C function — and that frame is not free. For the sprite twin it is `movem.l %d2-%d7` each
way plus five argument loads and two `adda`s; **measured, 3,774 cycles a call against 3,544** through
an entry whose caller has the values in registers already — two builds of one tree with nothing else
changed (`atari/profile.py ours`, same window; the shipped build, which also moved the restore seam,
reads 3,447). The restore twin's is smaller and still real: **1,133 against 1,005**, and 965 in
the shipped build.

So each of the two hot twins has two entry points into ONE ladder and ONE set of bodies:

    blit_sprite_rows_unclipped_asm   C ABI      the suite drives this; it marshals, then `bsr`s ↓
    blit_sprite_rows_unclipped_regs  register   ...and the target build's seam enters HERE

    restore_blit_rows_asm  / restore_blit_rows_regs   the same pair, the same way

**Every case the differential runs walks the register entry**, because the C-ABI entry reaches the
ladder through it. What is shipped-only is the handful of register moves GCC emits at the seam —
`../sprite.c`'s two inline-`asm` seams, whose whole content is loading a0/a1/d0/d6/d7 and a `jsr`.
That glue has no differential surface and is not pretended to: **the surface for it is
`atari/smoke.py`'s 32,000-byte framebuffer identity**, on two builds including the floppy. It is a
sufficient one because every value the glue marshals is consumed by the blit — a cursor, a shift, a
row count, a width — so a marshalling defect moves pixels rather than hiding.

The seam copy keeps the plain C ABI: its whole frame is 56 cycles at ~1 call a frame, so a second
entry would buy about fifty cycles and cost a name.

**The cost pins still clock the C-ABI entry**, so their numbers are that entry's frame and not the
game's — 278–310 cycles a call for the sprite twin against the ~50 of ladder the register entry
costs. They are still the right pin: the ladder and the bodies they reach are the shipped ones, so a
translation that quietly cost cycles shows up in them.

## What these twins cover, and what they deliberately do not

`atari/profile.py ours` over a 1000-vblank window of the attract screen, before the twin:
`blit_sprite_row` was **53% of everything the machine did**, at 1,334 cycles a row against the
original's 413. Of the blitter's cycles, **92% go through the unclipped path** (the gated one, which
the clip ladders reach, was 53,398 cycles a frame against 582,591).

So the sprite twin took the unclipped path first, and `../sprite.c` kept the C for the gated one
until a measurement made the case for the exception the next section states.

`restore.S` came next because a later profile named it, not because it was symmetrical: on a matched
75-sprite frame the restore replay was **149,634 profiled cycles against the original's 73,647**, the
largest single item in the frame. Its C is `include/common.h`'s `copy_longs`, which INDEXES the image
because it takes its cursors as offsets, and which `-funroll-loops` peels with a `__mulsi3` call per
restore. The five bodies are 130 bytes with no absolute operand anywhere, so they pin exactly as the
sprite bodies do — and the twin came out 2,048 bytes SMALLER than the C it replaced, because GCC no
longer has five specialised `copy_longs` to unroll.

`../STATUS.md`'s "On-target performance" carries the rows.

## The gated twin's declared substitution

`clipped.S` is the first file here that is **not** byte-identical to the .PRG, and this section is
the whole of why, what it costs, and what stands in for the pin it cannot have.

**It is impossible by construction, not merely inconvenient.** Each gated body differs from its
unclipped twin by ONE instruction per screen group:

    btst    #n,$16426.l          | 0839 000n 0001 6426 — 8 bytes, 20 cycles

an **absolute** address. This reconstruction receives the image base as a run-time ARGUMENT — that
is what `recreate_kit/asm_twin.py`'s memory layout exists to enforce, and what the target build
actually does — so no operand in a `.S` can name `image + 0x16426`. There is no 8-byte form of the
instruction that does not, either: `(An)` is 4 bytes and `(d16,An)` is 6, so a padded transcription
would have to invent an instruction, which is worse than declaring the substitution.

**The substitution is one instruction and one register.** `btst #n,(%a2)`, 4 bytes and 12 cycles,
with `%a2` holding `image + A_blit_clip_mask`. `%a2` is free: no instruction in any of the four
bodies touches it — they use a0, a1 and d0-d7 — and the file's own transcription is the evidence.
The register is loaded ONCE per call, by `../sprite.c`'s seam for the game and by the C-ABI entry
for the suite, so no body computes an address and the substitution stays the only divergence.

**The semantics are the original's.** The gate byte is still read FROM MEMORY at every group of
every row rather than hoisted, so a blit whose own destination covers 0x16426 draws its later groups
under the gate its earlier ones wrote — which `test_sprite.py`'s poked-destination case pins on the
C side and this twin's differential carries over.

**What replaces "the body IS the original's bytes".** Four pins in `../../test/test_asm_clipped.py`,
which together say *every byte is the original's except these*:

| pin | what it says | what it catches |
|---|---|---|
| the SEGMENTS | each run between two substituted instructions is the .PRG's own bytes at its own address (22 spans over four bodies) | any instruction that is not the original's |
| the TILING | each segment's ASSEMBLED length is its declared one, and the spans plus the excluded bytes cover the body exactly | a segment that lost its last instruction — which still matches a PREFIX of the original and passes the span compare (proved: deleting one `swap %d5` reddens the tiling pin alone) |
| the SUBSTITUTION | the gap between two segments is exactly four bytes, and it is `btst #n,(%a2)` on the bit the ORIGINAL's own 8 bytes at that address name | a wrong bit number — the substitution's one free parameter — and anything smuggled in beside it |
| the `dbf` | the row loop's back-branch displacement is the original's plus four per substituted site | the substitution's one consequence, and the only other instruction outside a segment |

**Every other branch in these bodies is intra-group** — the `bne.s` over a skipped group and the
`bra.w` past its merge both stay between two gates — so the `dbf` is the only displacement the shrink
moves, and the segment compare is what proves that rather than the claim's being taken on trust.

**The cost pin cannot be equality**, because the substitution is 8 cycles CHEAPER per group per row.
What is pinned instead is `twin == original - 8 * groups * rows + FRAME`, and the saving itself is a
second measurement: `test_the_substitution_saves_what_the_arithmetic_says` runs one body at two row
counts and checks that the twin's advantage grows by `8 * groups` a row, so a wrong constant cannot
move both sides of the cost test together.

**And `atari/build.sh` asks the shipped object for all 22 spans**, the same way it asks for the other
two twins' — with the "bodies this gate was not asked about" check making a span added to the `.S`
and not to the build line red rather than invisible.

## The shape of a twin here

    header: what it transcribes, from which address, and the C signature it carries
    .text
    .macro MOVEL_ALL_ONES        | the one encoding gas will not spell the original's way
    .equ   *_SAVED / *_ARG_*     | the C frame, every argument measured past the prologue's push
    <name>_asm:                  | THE C-ABI ENTRY — what the suite drives
        prologue                 | bind the C arguments to the original's registers
        bsr.s <name>_regs
        epilogue
    <name>_regs:                 | THE REGISTER-ABI ENTRY — what the target build calls
        width ladder             | OURS: the original's caller picks a body out of a jump table
        bra.w <class>_body       | the body's own `rts` returns to whoever entered the ladder
    sprite_blit_w16_body: ... sprite_blit_w16_body_end:      | the transcribed spans

Syntax is GNU `as` with `%`-prefixed registers and `|` line comments. Everything between a `_body`
label and its `_body_end` is the original's instruction sequence in order, one instruction per line,
each carrying its original address and encoding in a comment; everything outside those brackets is
ours and has no counterpart in the original. `restore.S` is the exception that proves that rule: its
five bodies differ in ONE number and are emitted by one `RESTORE_BODY` macro rather than written out
thirty times, and the byte pin is what says the macro laid down the original's own encoding.

**EVERY `.equ` IS PREFIXED WITH ITS TWIN'S NAME** (`SPRITE_SAVED`, `RESTORE_ARG_IMAGE`,
`RESTORE_SCREEN_ROW_BYTES`), with no exception for a value that looks universal. `kit.mk` links every
`.S` here into one blob with one flat symbol table; a gas `.equ` is a file-local ABSOLUTE symbol, so
two files defining one name do NOT collide at link — both land in `twins.elf` and a pin resolving the
name gets whichever `nm` printed last. kit.mk's own header records that happening, with a pin
checking one file's value and vouching for the other's, so the rule is a prefix rather than a
judgement per name.

**The `_body` / `_body_end` brackets are markers, never call targets**, and `atari/profile.py` drops
them from the symbol file it hands Hatari for that reason: `_body_end` sits at the first byte *after*
a span, which for bodies laid down back to back is the next body's entry point, and a profiler that
resolves by address would file that body's cycles under the marker.
