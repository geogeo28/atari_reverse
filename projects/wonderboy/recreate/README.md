# Wonder Boy in Monsterland — differential reconstruction

Readable C for *Wonder Boy in Monsterland* (Atari ST, Activision 1989), each function to be
**proven byte-for-byte equivalent to the original 68000 code**. This is the *recreate* track:
faithfulness beats correctness every time, so original bugs are reproduced rather than fixed.

The machinery is shared — [`tools/recreate_kit`](../../../tools/recreate_kit/README.md) loads the
`.PRG` into a flat image, runs the original under a Musashi 68000 oracle and this project's
compiled C on the same image, and diffs the result. Everything game-specific lives here. For *why*
the method is differential rather than byte-matching, read the worked reference project,
[`projects/buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md).

**[`STATUS.md`](STATUS.md)'s ledger is the count of what is reconstructed — 118 functions as of
batch 11; this paragraph names the GROUPS rather than counting them, and had drifted several batches
behind that table before batch 11 removed its stale figure.** `rad_depack` (`0x5d62`), the resource depacker every `.RAD` the
game loads goes through, verified over the game's own resource corpus — the 41 `.RAD` files the two
disks ship, plus the four protection-damaged overlays a second time in their authentic disk-2 bytes,
so 45 streams in all. The first gameplay batch: 31 leaves with no callee and no hardware between
them — the joystick edge pipeline (`0x682`, `0x88c`) and the 29 effect/state routines at
`0x10200..0x103e7` that the game reaches only through a dispatch table. And the status panel's own
eleven leaves (`0xb372..0xbd26`): four packed-BCD accumulators over the score and the counter below
it; five blits — the record bitmap, one meter cell, the panel's animation frame and the HUD-slot
cell pair (copy and OR), of which the first three take their destination from whichever buffer
`screen_back` points at and the pair are handed one by their caller; the meter's clamped add; and
the table-select that ends the frame's panel pass. Then the two tiers above those leaves: the digit
plotter and the field walks and fields it draws (`$b54c..$bd65`), and the pass's three table walks
(`$b39c`, `$b8f0` and the region restore `$d93a` with its six blits), which left
`panel_refresh_frame` with nine of its ten callees reconstructed — **the tenth ($bbca) and the
pass itself landed in batch 16b, once `src/sound.c` opened the sound module** (`snd_trigger_effect`
plus its register-preserving stub is what $bbca's one outward call needed on the candidate side). And the **whole background
scroll engine** (`$7522..$8228` plus `$d28`, sixteen routines and 3398 bytes): the game keeps EIGHT
pre-shifted copies of the level background over `$44000..$70000`, two pixels apart, so a horizontal
scroll is a change of buffer and the only work per step is the one tile column it uncovers — while a
VERTICAL scroll moves row pointers, copies one map row in unrotated, and pre-shifts it through the
other seven copies. A request queue drained once a frame sits above all of it. And the **actor
table's own lifecycle** plus the **collision map** the actors walk on (ten routines, 748 bytes): a
table is reset to free markers, a run of slots is freed again, and two allocators hand back the
first free record of one of two pools — 3..11 and 13..18, which meet EXACTLY either side of the
followed actor's slot 12, so the record the scroll steers on is the one gap no allocation can reach.
A spawn then fills a slot in from a 32-byte template. The map underneath them is a second one laid
out like the background map, one byte per 16x16 cell, with a probe that walks an actor left until a
cell blocks it, a scan that lands one on a platform tile, and a stamp that writes four tiles into it
as a 2x2 block. Batch 11 then closed that map (five more routines, 454 bytes): the RIGHTWARD probe,
which shares the leftward one's ground test by branching into it and clamps at the level's own width
instead of at the actor's half-width; the cell lookup both probes spell, which writes no memory at
all and became portable only when the kit's oracle began reporting the whole `movem` register set;
the second settle, whose body physically encloses `actor_accelerate_fall`; and the fall pass above
all of them. The rest is the
binding plus a foundation battery that runs the original code under the oracle and pins how the
program starts.
Progress, the kit change this project required, the oracle defect the panel batch surfaced, and the
one blocker still ahead: [`STATUS.md`](STATUS.md).

**Read [`PORTABILITY.md`](PORTABILITY.md) before choosing what to port.** It measures how much of
this game a memory-only differential can actually verify — 83.8 % of the *recovered* code runs
end-to-end under the oracle, "recovered" is 46.8 % of the program's believed code, and 13 % of what
is measured would come back *falsely* green — and gives the
reconstruction order and the harness capabilities that follow from that. It also explains why
every project's Ghidra DB needs re-bootstrapping.

```
PORTABILITY.md             HOW MUCH OF THE GAME THE DIFFERENTIAL CAN SEE — the measurement that
                           answers STATUS.md's blocker 2, with the reconstruction order it implies
subsystems.tsv             address ranges -> subsystem, for tools/hw_portability.py --subsystems
project.toml               binds this directory to the kit (paths, load base, image size, two waivers)
Makefile                   three lines: KIT + GAME + include $(KIT)/kit.mk
include/wonderboy.h        how SWB.PRG becomes a running image, as constants — the canonical copy
include/rad.h              the .RAD/.CRU container and its bitstream, as constants
include/effects.h          the 29 effect/state leaves at $10200..$103e7 — prototypes
include/hud.h              the status panel's 30 routines — prototypes, and their register interfaces
include/input.h            the two joystick-pipeline leaves
include/map.h              the collision map's three routines — prototypes, and why $10a2's result
                           is two registers rather than one
include/actor.h            the followed actor's record, the two tests over it, the two passes
                           that project actor records into screen coordinates, and the table's
                           lifecycle — reset, free, the two pool allocators and the spawn
include/text.h             the message box: the once-a-frame driver's three arms, the glyph
                           plotter's two entry points, and why the prelude calls the plotter (the
                           original has no `rts` in it — it falls through)
include/stage.h            the STAGE LOADER — prototypes, and why it is not scroll.h: the scroll
                           engine maintains the eight pre-shifted buffers a frame at a time, this
                           tier BUILDS them once when a stage is entered
include/scroll.h           the whole background scroll subsystem — prototypes, the queue's shape,
                           why a step returns a FLAG (the original returns it through its own
                           return address, and vertically it consumes TWO calls that way), and why
                           the blit's sixteen jump-table variants are one function with a column
src/rad.c                  the resource depacker (rad_depack @ 0x5d62) — the reconstruction's cores
                           live here, one file per subsystem
src/effects.c              the effect handlers and the state stubs above them
src/sound.c                the sound module's RAM-only routine: snd_trigger_effect ($1a48a) and the
                           register-preserving stub snd_call_trigger_effect ($17b14) — the module's
                           first ported bytes; everything that touches the PSG stays unported behind
                           the differential wall (test/test_sound.py owns the write-set model that
                           test/test_hud.py imports)
src/hud.c                  panel_refresh_frame ($b346) below its own entry: batch 2's eleven leaves
                           (the BCD score/counter accumulators, the panel blits, the meter's clamped
                           add), batch 3's second tier (the digit plotter — a leaf too — its three
                           field walks, the four fields the pass draws, the meter's own pass) and
                           batch 4's third (the pass's three table walks: the region restore and its
                           six blits, the newest record's display, the six HUD slots)
src/input.c                the joystick edge pipeline: latch a frame, then diff two frames
src/actor.c                the actor tier: $67e0, which names the record everything else is
                           measured against, the two tests above it (which side the followed actor
                           is on, and whether it is within reach horizontally), and the two passes
                           that project actor records into the screen array the sprite pass reads —
                           one record ($8dfe, the one the scroll steers on) and all nineteen ($8e66).
                           Then the table's LIFECYCLE: reset ($1f36), free a run ($df9e), the two
                           pool allocators ($1b68/$1b8e, one function here because the originals are
                           byte-identical bar two operands), the spawn ($ffe4) and the two routines
                           that move a record between standing and falling ($2af2, $14d6)
src/map.c                  the COLLISION MAP the actors walk on — a second map with the background
                           map's layout, one byte per 16x16 cell, and which of the two
                           state_flag_a32 names. The two step probes ($10a2/$1170, forty-one callers
                           each), the cell lookup below them ($13be/$13c8), the two settles ($1400
                           onto a platform tile and $1492 onto a block or ledge), the FALL PASS
                           above them ($1334, forty-six callers: the record's speed added to its y,
                           then both settles) and the 2x2 tile stamp ($1af0). Its header records the
                           one place the pair of maps is not symmetric, which $10a2 reproduces
                           rather than tidies — and why $1492, whose body physically encloses
                           actor_accelerate_fall's 32 bytes, is written as a routine that CALLS it
src/text.c                 the WHOLE text subsystem. The driver ($bd8a): compose a message into
                           the 88-byte-wide 4-plane buffer on the frame it is requested, then
                           re-blit that buffer to screen_back every frame until its countdown ends.
                           The plotter ($bf4e/$bf5e): 32 bytes into the buffer, and the
                           character-code prelude that falls into it
src/stage.c                the stage loader. bg_build_buffer ($fa30) draws the map's visible
                           window into pre-shifted copy 0 out of a tile bank;
                           bg_build_preshifted_copies ($fd46) derives the other seven from it two
                           pixels at a time, each 128-byte scanline closing as a ring;
                           stage_publish_scroll_state ($fb06) writes the limits, the map cursor and
                           the sixteen buffer row pointers src/scroll.c then steps.
                           stage_reset_state ($fed2) is the per-stage state reset (and an overwrite
                           of the last eight entries of WB_TILE_INDEX_TABLE, which the .PRG ships
                           no part of — it lies past the image and is loaded from disk),
                           resource_table_relocate ($fe1e) the one-time fixup of a loaded table,
                           and $e110's three routines the banners plotted into copy 0
src/scroll.c               the whole scroll subsystem, producer and consumer. The ENGINE ($7522..
                           $8228 + $d28): the frame queue and its dispatch pass, four request
                           handlers, four position steps, the two column fills that redraw the
                           uncovered edge into the pre-shifted buffer the phase names, the two row
                           fills that redraw an uncovered scanline pair, and the pre-shift that
                           walks a fresh row through the other seven copies. The CONSUMER
                           ($82f8..$8dfe): the per-frame blit and — as ONE parametrised function,
                           because they are one pattern with one number in it — the sixteen unrolled
                           copy routines its jump table names
test/harness.py            the kit-binding shim
test/leaf.py               shared driver for LEAF routines: entry points looked up in ../names.txt,
                           the write set a routine is entitled to (which the depacker's battery
                           calls too) and its complement, the write set minus the machine stack, the
                           glue for one whose ENTRY REGISTERS are its arguments, the entry-pin
                           scaffolding the batteries share (operand encoders, the opcodes more than
                           one of them spells, and the readers that take a value out of the write
                           set), the word read and the sign extension every Python model of a
                           routine does, the address-keyed seeding they all build their images
                           from, the game's own two screen buffers (two batteries draw into them),
                           and the second stop PC a routine needs when it returns PAST its caller's
                           next call by rewriting its own return address
test/layout.py             include/wonderboy.h's constants, scraped from that header (one source of truth)
test/test_layout.py        that scraper's own cases — it refuses a duplicate or an octal-ambiguous #define
test/test_bootstrap.py     the foundation battery: the loader, the self-relocation, the trap inventory
test/copylock.py           the Copylock stub — two mechanisms, and the memory-difference witness that
                           refuses any run whose memory shows the protection executed after all
test/test_copylock.py      that stub's battery: each mechanism over its own domain, the two guards on
                           the witness's inputs, and the negative controls for an unstubbed run
test/test_poked_input_guard.py  the kit waiver this project is the only user of, and its three guards
test/test_audio_capture.py  the kit's opt-in audio-capture mode, pinned from this game's suite for
                           test_poked_input_guard.py's reason: the sound module's mixer read-back
                           serves as the 68000 code the kit itself cannot carry
test/test_rad_depack.py    the depacker's differential: the game's own .RAD corpus (41 files, 45
                           streams), decoded by both sides, plus the failure branch
test/test_effects.py       the effect/state leaves' differential: seeded destinations, both sides of
                           the meter clamp, and the record list's write pointer
test/test_hud.py           the status panel's differential: the game's own bitmaps blitted into both
                           of its screen buffers, the BCD accumulators against a decimal model, the
                           regression case for the oracle's entry condition codes, and — for the
                           non-leaf tiers — whole-body entry pins, a leading-zero model the drawn
                           digits are checked against, and (for the screen-to-screen restores) a
                           seeded MARGIN around every region, without which an over-copy of zeros
                           over zeros stays invisible. It also holds the LIVES display, the one
                           routine here that writes both screen buffers at ABSOLUTE addresses
                           rather than through `screen_back`, and exports its model to test_stage.py
test/test_input.py         the joystick pair's differential — memory for the latch, the whole
                           returned d0 for the edge
test/test_scroll.py        the scroll subsystem's differential: whole-body entry pins for all
                           thirty-three (6140 bytes, every unrolled loop assembled from its own
                           geometry and the call-carrying bodies from a cursor-tracking _Assembler),
                           Python models of every routine that COMPOSE — a serve runs its fill on its
                           step's output, the queue runs the dispatch pass as many times as it owes —
                           with each case's write set compared against them for EQUALITY, an
                           address-keyed seeding of all eight buffers and both screens plus a margin,
                           and the skip decision read off the ORACLE's rewritten return address
                           rather than inferred. The consumer tier adds two entry conventions: a case
                           entered at $82f8 goes THROUGH the jump table, and one entered at a variant
                           supplies the four registers the dispatcher would have — plus three
                           variants pinned against bytes transcribed from ../out/wonderboy_dis.txt,
                           so the pattern the other thirteen are built from cannot be what is wrong
test/test_map.py           the collision map's differential: an address-keyed window of each map
                           with the two ROW STRIDES seeded apart (which is what makes the asymmetry
                           observable at all), whole-body entry pins for all eight, Python models
                           the write set is compared against for EQUALITY, a probe whose two results
                           are both partial register writes over something else, and case tiles
                           keyed to the cell the probe ACTUALLY lands in rather than to the actor's
                           own edge — the mutation sweep's finding. The two tiers above add a pin
                           130 bytes long over a routine the scan records as 98 (the 32 in the
                           middle being another routine's, asserted as its own), a model that
                           COMPOSES its five callees' models over one shared memory, and the whole
                           operand scan behind the three globals $1334 raises and clears
test/test_actor.py         the actor tier's differential: a routine whose WHOLE output is a register
                           (every case compares the oracle's a1 against the reconstruction's return
                           value), the small-positive flag words that separate the tier's `bne`
                           reading of a mode flag from its `bpl` one, the 16-bit ADD whose wrap the
                           reach test's compare reads, and an address-keyed seeding of all three
                           actor tables and the screen array they project into. It also holds the
                           SPAWN PASS, whose model replays the whole routine on a mutable copy
                           because its arms are sequential, and the case that pins the vector-page
                           stamp a full pool produces
test/test_stage.py         the stage loader's differential: whole-body entry pins for all ten
                           routines, the sixteen published row pointers derived from the scroll
                           engine's own invariant and required to equal the shipped instruction
                           bytes, a map band seeded at every cursor $fa30's own arithmetic lands on
                           (never off a coordinate the case has to hand), the whole 22,528-byte
                           copy 0 compared against a model, the seven derived copies and the ring
                           their carry word closes, the banner cursor compared three ways, and the
                           two resets Ghidra reports as one function -- split at the second entrant
                           a whole-image scan found, and required to add back up to its 136 bytes.
                           It is the ONE battery here that imports another (`model_lives_draw` and
                           `lives_pokes` from test_hud.py): $fe8c CALLS $e80c, so its write set
                           contains that routine's, and two copies of the geometry could disagree
                           while both batteries stayed green
test/test_text.py          the text subsystem's differential. The plotter: 32 bytes into the
                           4-plane buffer with the write set stated exactly, the returned cursor
                           compared against both sides, a cell walk that shows the +1/+7 alternation
                           lands on the next plane group, a scan of the eight `bsr` sites for the
                           frame glyphs they pass, and the d0 whose shifted low word indexes BELOW
                           the font. The driver: every phase of the ten state bytes seeded one at a
                           time, six shipped messages composed with the whole 6400-byte buffer
                           stated exactly, the blit's rectangle and countdown, and four structural
                           pins that read the $a09c message table's extent off its own data
```

## Running

```bash
make venv      # once: .venv + pytest/pytest-xdist (see requirements.txt)
make test      # build the candidate + the shared oracle, run the suite across cores
make oracle    # rebuild only the shared Musashi oracle
make clean     # this project's build/ only — the oracle is shared, see the kit README
```

`make venv` is `python -m venv .venv` plus `pip install -r requirements.txt` (`kit.mk`), the same
two lines BuggyBoy and Joust use — run it with the `atari_reverse` conda Python. The `.venv` already
in this directory was instead made the way Joust's was,
`python -m venv --system-site-packages .venv`, which borrows pytest and pytest-xdist from that conda
environment rather than installing its own copies. Either form works; `requirements.txt` is the
canonical list of what has to be reachable.

### Running a mutation sweep

The gate's coverage claim is only worth what a sweep says: flip a constant, delete a branch,
off-by-one an index, rebuild, re-run — a mutation nothing catches is a hole. A sweep **lies** in two
ways, and both have been measured here, so run one this way:

```bash
for m in mutants/*.patch; do
  git apply "$m"
  rm -f build/*.so                       # 1. FORCE the relink...
  make build/libwonderboy.so | tee cc.log
  grep -q clang cc.log || { echo "NO REBUILD — the sweep would be measuring the clean .so"; break; }
  .venv/bin/python -m pytest -q -n auto test   # 2. NO pipe: read the RETURNCODE
  echo "$m -> $?"                              #    (0 = SURVIVED, nonzero = caught)
  git apply -R "$m"                            # 3. restore, and re-green before the next one
done
```

1. **`make` can skip the rebuild.** `.so` mtimes have ~1s granularity, so a mutation applied within
   the same second re-runs the *unmutated* library and reports phantom survivors (BuggyBoy's sweep
   reported 8; the real result was 17/17). `rm -f build/*.so` and check the compiler line actually
   ran.
2. **A piped `pytest` hides its exit status.** `pytest … | tail` reports the *pipe's* status, so
   every mutant "survives". Batch 19's first sweep came back 0/37 caught for exactly this reason.
   Take the returncode from the unpiped run.

Restore and re-green after each mutant — a sweep left half-applied is worse than none. Its sibling
recipe, [writing a fuzz test so it shards across
workers](../../buggyboy/recreate/README.md#writing-a-fuzz-test-so-it-parallelizes), is in BuggyBoy's
README.

## The binary, and the one thing that makes it unusual

`../bin/disk1/AUTO/SWB.PRG` is the ORIGINAL, uncracked release, extracted from the Pasti `.stx`
images with `tools/stx_extract.py`. 136,979 bytes: text `0x214d8`, no data, no bss, entropy 4.96
(plain code+data, not packed). `bin/` is gitignored — no game data is committed.

**The program is not position-independent.** 136 KiB of text carries **three** relocation entries,
and the body addresses itself with absolute long operands (`jsr $e032.l`, …) that nothing fixes up.
The entry point is a trampoline into a relocator at the very end of the text:

```
+0x00000  3000                 move.w  d0,d0
+0x00002  4ef9 000213e0        jmp     $213e0.l           <- RELOCATED
...
+0x213e0  2f3c 000214d8        move.l  #$214d8,-(a7)      <- RELOCATED
+0x213e6  3f3c 0020            move.w  #$20,-(a7)
+0x213ea  4e41                 trap    #1                 ; GEMDOS Super(end of program)
+0x213ec  46fc 2700            move.w  #$2700,sr
+0x213f0  43f9 00000400        lea     $400.l,a1          ; NOT relocated — an absolute address
+0x213f6  41f9 00000008        lea     $8.l,a0            <- RELOCATED
+0x213fc  203c 000084f6        move.l  #$84f6,d0          ; 0x84f6 longwords = 0x213d8 bytes
+0x21402  22d8 5380 66fa       move.l (a0)+,(a1)+ ; subq.l #1,d0 ; bne
+0x2140a  4ef9 00000400        jmp     $400.l
```

So the program **copies itself to the fixed absolute address `0x400` and runs there**. The only
address space in which a reconstruction can be verified is that runtime one.

### Why `load_base = 0x3f8`, and not the workspace default

`0x3f8 + 8 == 0x400`. At that base the loaded image **is** the runtime image: the relocator's source
and destination coincide, its copy is an identity copy, and the game's own absolute operands address
the loaded image directly with no staging step. It is also the base `../names.txt` is written at —
the kit reads that file for its diff labels and its exclude-band vetting, so a base that disagreed
with it would mislabel every future report — and the base at which Ghidra recovers 186+ functions
rather than 57. Every line of the listing above is verified: the relocator is run under the oracle
in `test_the_relocator_copies_the_body_to_its_runtime_base`, with the destination compared against
the file's own bytes (no relocation fixup lands inside the copied body, so the runtime bytes ARE the
raw file bytes).

Two consequences worth knowing before touching anything:

* **`../run.sh` passes `0x3f8`**, so re-bootstrapping Ghidra lands in the same address space as
  `../names.txt` and this directory. It still re-imports and wipes the DB — iterate with
  `../reapply.sh`.
* **`0x3f8` is below the kit's `load_base >= 0x620` floor**, which is why the kit gained a second
  waiver (`tos_poked_input_unused`) and two guards that enforce its claim per poke and per run.
  [`STATUS.md`](STATUS.md) describes them and `test/test_poked_input_guard.py` pins them.

## One trap in the whole image

The game issues **exactly one** TOS call — the GEMDOS `Super` above — and drives the hardware
directly for everything else, including the floppy: it loads `OVALAY*.RAD` / `TILEDATA.RAD` /
`SPRITES.CRU` / `DATADISK.RAD` by name (the strings are at file offset `0x21226`) with no GEMDOS
file call anywhere. Established by an exhaustive byte scan of all sixteen `trap #N` encodings at
every even offset: five exist, four of them inside the game's ASCII message tables
("MYCO**NI**D MASTER!", "RED K**NI**GHT!", "GIANT CO**NG**!"). The five are pinned by offset *and*
classified by a printable-run rule, so neither the list nor the rule stands alone.

That single fact carries both of `project.toml`'s waivers — a `Malloc` and a poked-input read alike
need a trap, and there is only this one, and it is a `Super`. It also means the kit's trap model
**refuses** this game's `Super`, whose argument is the program's own end address rather than `0`,
`1` or the model's cookie (`TRAP_MODEL.md`, Phase 2). That costs nothing today, because the oracle
already runs in supervisor mode and a run can simply enter one instruction later at
`WB_RELOCATOR_COPY_OFF`; it is pinned as a case so a change to the model shows up as a failing test
rather than as a silently different run.

Direct hardware access is also where the harder wall is. The kit rejects any direct PSG *read*
outright, which is what an ST floppy drive-select does — the wall that put Joust's raw-floppy
routine off its list. How much of this game sits behind it is measured in
[`PORTABILITY.md`](PORTABILITY.md).
