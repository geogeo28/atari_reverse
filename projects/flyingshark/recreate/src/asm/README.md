# The asm twins — what they are, and how to add the next one

A **twin** is a hand-written m68k transcription of the **original binary's own instruction
sequence** for one routine, carrying the C signature of the verified core it stands in for. The
target build (`../../atari/build.sh`) links the twin instead of calling the C; the host differential
build never sees it.

This directory holds one: `sprite.S`, the four **unclipped** masked sprite blitters. The recipe is
written out at length in [`projects/zynaps/recreate/src/asm/README.md`](../../../../zynaps/recreate/src/asm/README.md),
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

Measured here: each body is **byte-identical** to the .PRG's, so its per-row cost is the original's
exactly, and the twin's whole excess is a fixed 264–306 cycles of C-ABI frame per call
(`test/test_asm_sprite.py`'s `TWIN_FRAME_CYCLES`).

The corollary matters as much: **do not improve on the original.** A cleverer instruction is a
divergence you now have to justify, in a file whose whole warrant is that it does not diverge — and
this project has already met the case in its mildest form. gas spells `move.l #$ffffffff,dN` as
`moveq`: two bytes shorter and eight cycles *cheaper*, and not what the original does. It is laid
down as the encoding the original used (`sprite.S`'s `MOVEL_ALL_ONES`), because a cheaper divergence
is still a divergence and this one would have put every body two bytes out of step with the .PRG.

## The chain of evidence

    original  ==(test/test_sprite.py)==  C core  ==(test/test_asm_sprite.py)==  asm twin

Both links are byte-exact **over the whole image**, so a twin is pinned to the original transitively
and neither link has to be re-derived. The twin is never compared against a second oracle run: the C
is already known equal to the original on exactly those cases.

Six things judge a twin, and a new one needs all six:

| check | where | what it catches | proved able to fail |
|---|---|---|---|
| the differential | `test/test_asm_sprite.py` | any byte the twin computes differently, anywhere in the image | `lea 146` → `lea 144` in one body: 21 cases red |
| the transcription pin | `test_the_twin_transcribes_the_original` | a body that stopped being the original's own machine code | the same mutation, named by address |
| the cost pin | `test_the_twin_costs_what_the_original_costs` | a translation that quietly costs cycles | dropping `%d7` from the `movem` pair |
| the build gate | `../../atari/build.sh` | the twin not actually being what the game calls | dropping `-DFS_ASM_SPRITE`: exits 1 |
| the SHIPPED bytes | `../../atari/assert_twin_bytes.py`, run from `build.sh` | the object that ships not being the one the suite pinned | `lea 138` → `lea 136` in one body: named by address |
| no conditional assembly | `build.sh`, one `grep` | the two assemblies of a `.S` being able to differ at all | an empty `#ifdef`: exits 1 |

The build gates are the ones worth dwelling on, and there are three because this substitution fails
**silently** in three different ways.

*The twin might not be what the game calls.* Drop `-DFS_ASM_SPRITE` and `../sprite.c`'s
`BLIT_SPRITE_ROWS_UNCLIPPED` resolves to the C again, the twin still assembles, still links, still
exports its name, and the game still draws exactly the right pixels — three times slower, with
nothing but the frame rate to say so. `make test` would not notice, because the C is not wrong, only
slow. So the gate asks the objects directly: the twin must be **defined** by the asm object and
**referenced** by the core object.

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

## What this twin covers, and what it deliberately does not

`atari/profile.py ours` over a 1000-vblank window of the attract screen, before the twin:
`blit_sprite_row` was **53% of everything the machine did**, at 1,334 cycles a row against the
original's 413. Of the blitter's cycles, **92% go through the unclipped path** (the gated one, which
the clip ladders reach, was 53,398 cycles a frame against 582,591).

So the twin is the unclipped path, and `../sprite.c` keeps the C for the gated one. Two reasons, and
the second is the interesting one:

* it is 8% of the blitter, so it buys about a twentieth of what the unclipped path did;
* the gated bodies `btst #n,$16426.l` once per group — an **absolute** address, which in a
  reconstruction is `image base + 0x16426` and cannot be transcribed byte for byte at all. It would
  be the first body in this directory whose transcription pin had to carve an exception, and the
  case for one should be made by a measurement rather than by symmetry.

`../STATUS.md`'s "On-target performance" carries the row.

## The shape of this twin

    header: what it transcribes, from which address, and the C signature it carries
    .text
    .macro MOVEL_ALL_ONES        | the one encoding gas will not spell the original's way
    .equ   SAVED / ARG_*         | the C frame, every argument measured past the prologue's push
    blit_sprite_rows_unclipped_asm:
        prologue                 | bind the C arguments to the original's registers
        width ladder             | OURS: the original's caller picks a body out of a jump table
        bsr.w <class>_body       | so each body keeps the original's own closing `rts`
        epilogue
    sprite_blit_w16_body: ... sprite_blit_w16_body_end:      | the transcribed spans, four of them

Syntax is GNU `as` with `%`-prefixed registers and `|` line comments. Everything between a `_body`
label and its `_body_end` is the original's instruction sequence in order, one instruction per line,
each carrying its original address and encoding in a comment; everything outside those brackets is
ours and has no counterpart in the original.

**The `_body` / `_body_end` brackets are markers, never call targets**, and `atari/profile.py` drops
them from the symbol file it hands Hatari for that reason: `_body_end` sits at the first byte *after*
a span, which for bodies laid down back to back is the next body's entry point, and a profiler that
resolves by address would file that body's cycles under the marker.
