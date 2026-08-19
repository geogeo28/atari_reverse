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
include/effects.h          the 29 effect/state leaves at $10200..$103e7 and the 14 PICKUP
                           effects at $105e4..$10799 — prototypes
include/hud.h              the status panel's 30 routines — prototypes, and their register interfaces
include/input.h            the two joystick-pipeline leaves
include/map.h              the collision map's three routines — prototypes, why $10a2's result
                           is two registers rather than one, and the two `static inline` step
                           helpers (one probe with the ground flags no caller reads dropped) that
                           moved here from src/behavior.c when src/player.c's walk became their
                           second module
include/player.h           THE PLAYER'S OWN FRAME — NINE routines: SIX of behaviour slot 1's own
                           nine calls, the jump machine the gate reaches below one of them, the
                           routine that leaves the ladder, and the spawn helper the second call
                           hands a template to. (Of slot 1's other three, `player_gate_on_1516` and
                           `actor_fall_and_settle` belong to the behaviour tier and
                           `player_pending_event_gate` is unportable.) EIGHT of the nine reach
                           nothing this port lacks; the COLLISION CELL ($151a, batch 41 phase A) is
                           the one that reports an EXIT rather than returning. Plus the
                           per-arm reading of the WEAPON's threaded `sbcd` extend bit, and (at the
                           foot of the header) what the frame still calls that is NOT there —
                           which since batch 41 phase A is `player_pending_event_gate` ($b1a)
                           alone, UNPORTABLE on three stack-unwinding exits. Batch 41 phase A added
                           `player_run_map_cell` ($151a) and with it this file's first EXIT REPORTS
                           — the busy-wait and the triple pop
include/actor.h            the followed actor's record, the two tests over it, the two passes
                           that project actor records into screen coordinates, the table's
                           lifecycle — reset, free, the two pool allocators and the spawn — and
                           the two EXIT CODES $6bb8 reports in place of the respawn continuation
                           it declines to follow
include/behavior.h         the per-actor BEHAVIOUR tier's foundation: the walk ($8d0), the
                           four-instruction dispatcher the whole tier hangs off ($928), the spawn
                           animation twenty-five handlers branch into, the thirteen shared leaves
                           and the two overlap tests forty-two and twenty-five of them run every
                           frame — plus the three DISPATCH CODES the port returns in place of a
                           `jmp` it declines to follow
include/text.h             the message box: the once-a-frame driver's three arms, the glyph
                           plotter's two entry points, and why the prelude calls the plotter (the
                           original has no `rts` in it — it falls through)
include/stage.h            the STAGE LOADER — prototypes, and why it is not scroll.h: the scroll
                           engine maintains the eight pre-shifted buffers a frame at a time, this
                           tier BUILDS them once when a stage is entered
include/rng.h              the game's PRNG and the per-stage draw over it — and the DECLARED entropy
                           the generator runs on: its one hardware term is a modeled byte the case
                           states and the ledger compares, which retired the false green it carried
                           while both cores were served 0
include/scroll.h           the whole background scroll subsystem — prototypes, the queue's shape,
                           why a step returns a FLAG (the original returns it through its own
                           return address, and vertically it consumes TWO calls that way), and why
                           the blit's sixteen jump-table variants are one function with a column
src/rad.c                  the resource depacker (rad_depack @ 0x5d62) — the reconstruction's cores
                           live here, one file per subsystem
src/effects.c              the effect handlers and the state stubs above them — and, since batch
                           38, the FOURTEEN pickup effects behind the sibling table at $105ac,
                           which are the same kind of leaf one dispatch over and which reuse this
                           file's own slot writer and record push
src/sound.c                the sound module: snd_trigger_effect ($1a48a) and the
                           register-preserving stub snd_call_trigger_effect ($17b14) — the module's
                           first ported bytes — plus the STOP CHAIN, $17f24 -> $1aaea -> $17f30,
                           three routines joined by `bra.w` that end in the first ported code in
                           this project to drive the YM2149. test/test_sound.py owns the write-set
                           model test/test_hud.py and test/test_actor.py import, and the PSG access
                           ledger the latter imports too. Then the TICK TIER — what the per-VBL tick
                           calls, in the order it calls them: snd_sfx_tick ($1a5da), which the tick
                           runs FIRST, before a single music byte; snd_prng_step ($1aaca), the
                           module's own PRNG, distinct from src/rng.c's and stepped every tick;
                           and snd_channel_period_and_volume ($18208), the six-armed pass that turns
                           one music channel's record into a period and a volume. And now the TICK
                           ITSELF: snd_channel_step ($18106) with the 24 pattern-opcode handlers
                           below it ($17fd4..$18105) — one flow graph, since the stepper's last
                           instruction is the `jmp` that enters a handler and every handler but one
                           branches back into its body — and snd_music_tick_body ($17ca0), which is
                           snd_music_tick under its 44-byte tempo head. And that HEAD, snd_music_tick
                           ($17c74) itself: the module's last unported bytes and the only code in
                           this project steered by hardware. It branches on $fffa01 bit 7 and
                           $ff820a bit 1, so a case DECLARES both with leaf.run(..., hw_seed=) — the
                           kit's seeded hardware read model (TRAP_MODEL.md, "Phase 7"), whose first
                           consumer anywhere this is — and one that declares nothing is refused
                           rather than served the fabricated 0 both cores used to agree on
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
                           that move a record between standing and falling ($2af2, $14d6). At the
                           bottom, what a DEFEAT costs ($6bb8): the score its template's type is
                           worth, the kill counted, the slot freed and the template re-armed — plus
                           the boss block above all of it, which stops the music and fires an effect
                           — and the RESPAWN CONTINUATION ($6cdc) it branches to, which draws the
                           slot's new kind through src/rng.c and rebuilds nine of the dead record's
                           fields out of it, or frees the slot when the template forces a negative
                           one
src/behavior.c             the per-actor BEHAVIOUR tier's foundation, and the bottom of the 18,068
                           bytes PORTABILITY.md §0k's coverage break-open exposed. The per-frame
                           walk over the published actor table ($8d0, with its own three-record arm
                           for state_flag_a34) and the dispatcher it feeds ($928), which fetches a
                           longword out of the 62-entry table at $938 and tail-jumps through it —
                           on the WRAPPED offset, so 248 of the 65,536 type values reach an entry.
                           SIXTY-ONE of the sixty-two rows are reconstructed as of batch 39 and
                           the ONE that is not is the player (slot 1), for which the dispatcher
                           hands the target BACK and the differential runs the oracle on to it.
                           Batch 40 opened that row's own frame in src/player.c and RETIRED this
                           file's last returning boundary with it: `player_gate_on_1516` calls the
                           jump machine now, so slots 53 and 9/12/22/26 run their frames whole.
                           (This line read "twenty-two" while
                           ../STATUS.md read twenty-three at batch 32 and neither was checked
                           against anything; test_behavior.py's PORTED_SLOT_COUNT now holds the
                           number and a case asserts it against the table, so the next drift fails
                           a test rather than a reviewer.) Then
                           the tier's own grammar: the animation every spawned record plays
                           ($698a), the thirteen shared leaves the handlers call — three map
                           steppers, four animation cursors, a homing step, a moving platform's
                           catch and release, a sprite select and a side-flag write at the OPPOSITE
                           polarity to $67c2 — and the two tests the tier runs every frame, the
                           three-bit overlap mask against the followed record ($5c6e) and the
                           player-shot scan that consumes what it finds ($23b6). At the foot of it,
                           the PAYOUT CLUSTER the collectable rows spend through ($517a..$5207):
                           the scene descriptor's packed-BCD gold award, the one-to-four `abcd`
                           that jitters it — the tier's only hardware read, and a DECLARED one —
                           and the two digits it patches into message 3's own shipped string. They
                           live here rather than in src/hud.c because their addresses are inside
                           the behaviour band and both callers are dispatch rows, which is
                           sound_request_9's argument. Batch 34 CLOSED the band $4e38..$5407 with
                           slots 32..37: a second hopping gold collectable whose three state bytes
                           are all GLOBALS, the clock pickup that winds the panel's own countdown
                           back, the SHOP'S ITEM CURSOR (a record whose x is a menu selection the
                           joystick's edges walk between three positions), and the three EVENT
                           ACTORS player_pending_event_gate spawns and waits on — two sharing one
                           animation over one global cursor and the third a bare riser. Batch 38
                           then added slot 38 and THE PICKUP TIER: a collectable whose payout is a
                           TABLE LOOKUP — its own 16-byte kind row gives a packed-BCD score and an
                           index into a second dispatch table, so this is the first row here whose
                           frame dispatches again — plus the five digits it patches into message
                           16's own shipped string. The fourteen handlers behind that table are in
                           src/effects.c, beside the twenty-nine they are the siblings of. Batch 39
                           then closed everything but the player with slots 39..46 and 57, which
                           turn out to be THE TIER'S OWN AMMUNITION: each of the nine is the record
                           an already-reconstructed handler spawns (16->39, 6->40, 18->41, 25->42,
                           19->43, 21->44, 14->45, 23->46, 7->57), so the fields each spawner writes
                           are the fields its child reads. Two SHATTERERS that break up when they
                           land and share one tail, three WALKERS that die where the map stops them,
                           three SHOTS (one on a byte pair its spawner aimed, one re-aimed at the
                           player every frame through actor_aim_velocity, one on a word pair slot
                           7's burst copied in as a longword) and the RISER that is slot 23's stolen
                           gold floating away
src/player.c               the player's frame, batch 40: the DEATH CHECK ($a76, which spends the
                           revival medicine or starts the death sequence), the JUMP MACHINE ($e06 —
                           the ascent, the launch on a rising UP edge, and the WING BOOTS, which
                           burn one charge a frame to hold the fall at one pixel), the LADDER ($d84,
                           whose x snap keeps bit 0), leaving the ladder ($107c) and the event
                           actor's spawn ($539e). Its one meeting point with src/behavior.c is
                           `player_gate_on_1516` ($d78), which stays in that file where the
                           behaviour battery pins it — and which CALLS the jump machine now, which
                           is what retired the last boundary the original returned from. Phase B
                           then added the two calls below those: the WALK ($ec8 — five sections in
                           a row, of which the last is an accelerator whose two turn rates are NOT
                           equal, and whose two `bsr $107c` sites are the only callers $107c has),
                           and the WEAPON ($1208 — DOWN plus a FIRE edge spends one packed-BCD unit
                           off the newest WB_EFFECT_RECORD_LIST record and spawns the lightning
                           flash, a wind spout, a fireball or a bomb; its `sbcd` is the first
                           THREADED extend site in this project that one arm also produces LOCALLY,
                           so `entry_extend` is a parameter here rather than a claim). Phase C then
                           took the frame's LAST call, the POSTURE SELECTOR ($1f54): four cutscene
                           animations over four flag words and, below them, what the player's own
                           flag bits LOOK like — standing, walking, jumping, falling, climbing a
                           ladder or swinging, out of one of three 88-byte posture records
                           WB_EFFECT_STATE_21E4 picks between. It holds the only readers of the two
                           bits the walk writes, and its swing has a defect worth knowing about: the
                           first frame of every swing is indexed by the SFX ID, because the sound
                           stub restores d0
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
src/rng.c                  the game's PRNG (rng_next, $68c6, ten callers) and BOTH draws over it —
                           stage_random_kind8 ($e1f0, eight candidates per stage) and
                           stage_random_kind32 ($e1c8, thirty-two), which are one routine with three
                           operands changed and are written here as one static body with three
                           parameters. One module because a draw's whole result is the generator's
                           low three (resp. five) bits, so a battery that pinned them apart would
                           pin neither
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
                           next call by rewriting its own return address. It also forwards the two
                           OFF-IMAGE declarations a case can make — psg_seed (the YM2149's register
                           contents) and hw_seed ($fffa01/$ff820a, whose addresses it names) — since
                           a capability the kit grows is unreachable from a leaf case until this
                           file threads it
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
                           the meter clamp, and the record list's write pointer — and batch 38's
                           FOURTEEN pickup effects, whose extra surface is the MESSAGE each posts
                           (three of them post id 0, which CANCELS the box slot 38's score arm has
                           already asked for) and one of which has a callee
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
test/test_rng.py           the PRNG's differential, and the one battery here whose module
                           docstring OPENS with a RETIREMENT and the history behind it: the
                           generator's only hardware term was merely off-image, both cores read a
                           fabricated 0, and every green run here was green about a generator with
                           no randomness in it — until the kit's Phase 7 table modeled the byte, so
                           a case DECLARES what the counter held and one case drives it off 0. What
                           it pins — each counter on both sides of its own wrap (cleared when it
                           REACHES its limit, not modulo it), the entropy XOR over a whole word, the
                           `clr.w` that leaves the caller's high half in the result — and the draw
                           TWO draws above it, as ONE set of cases over two descriptors because the
                           routines are one routine over two tables: a packed-BCD stage number
                           decoded by one tens carry, every candidate of a row reached by choosing
                           the seeds that land on it, and the entry d2 whose high half the `add.l`
                           folds into the table index — including the one that leaves the 68000's
                           24-bit address bus, and the one on the bus's own top bit that separates
                           24 bits from 23
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
test/test_behavior.py      the behaviour tier's differential. Its shape is set by two routines that
                           WRITE NOTHING: the walk and the dispatcher are pinned by the BOUNDARY
                           they report — one differential per table slot, the oracle stopped at the
                           handler's own address with a `cov_visited` witness on the `jmp (a1)` —
                           which pins the dispatch arithmetic and the image's 62 longwords against
                           ../names.txt at once. It also holds an enumeration over all 65,536 type
                           values (eight shardable chunks) stating the alias bands and the refusal
                           set, a two-pass LABEL ASSEMBLER for the entry pins (a body with fourteen
                           forward branches into six shared exits does not survive the
                           sum-the-spanned-bytes idiom), and an independent model of $5c6e's three
                           overlap tests compared against the ORACLE's d0 as well as the port's
                           return. It imports test_map.py's map seeding and test_rng.py's generator
                           model rather than restating either. Then the SIXTY-ONE LIVE TABLE ROWS
                           (this is the second of the four surfaces PORTED_SLOT_COUNT's own comment
                           names, and the third batch running to drift on it — the pinning case
                           reads the TABLE, not this prose, so nothing but a reader catches it):
                           the five-handler band at $2462..$2db1 (one shape with five bodies), the
                           whole $5a band ($5928..$5c6b, seven rows and three endings of one
                           grammar), the three moving platforms, slot 60's retype, slot 61's message
                           sequence, slot 7 with the SWOOP state machine below it that its two
                           prologue rows also run into, and the three COLLECTABLES at 28, 30 and 31
                           with the payout cluster under them, batch 34's six at 32..37, batch 38's
                           slot 38 with the SECOND DISPATCH behind it (fourteen entries reached by
                           56 of the 65,536 index values, an eight-shard enumeration over all of
                           them, and a refusal that is a CODE rather than an address because the
                           span the index reads holds zeros), batch 39's LAST NINE ROWS at
                           39..46 and 57 — the AMMUNITION, whose cases thread three of the nine
                           through their spawner's own write ledger (21 -> 44, 7 -> 57, 23 -> 46),
                           drive the ONE table in the tier with three readers (two of them the
                           SHORT-absolute `lea`, one a `move.w` no `lea` census could see) and seed
                           the aim table's own rows to pin WHICH row slot 45 reads — and batch
                           35's MONSTER-PROLOGUE FAMILY at 9..13 — the $2462 band's grammar with five
                           more middles, two of which report a boundary on their hurt arm because
                           they call the player gate — and batch 36's SIX MORE of that family at
                           14..19, which add a hurt tail in a SECOND order (the defeated bit tested
                           BEFORE bit 0 is lowered, so a transferring record keeps both marks), five
                           SPAWNERS, two handlers whose struck arm depends on WHICH test struck, and
                           slot 19's own defect: `bsr $1b8e` returns in the register its frame table
                           was `lea`d into, so the sprite published on the firing frame comes out of
                           the record just allocated —
                           each entered where the `jmp (a1)`
                           would land, and each with its dispatch row flipped from a boundary to a
                           run. What those cases share is a GROUND WINDOW — a solid
                           row under the record, a clear one where the probes read, and a wide
                           WB_BG_SCROLL_LIMIT_X — because a keyed map tangles "did it land", "was
                           the step blocked" and "is there a drop ahead" into one byte
test/test_actor.py         the actor tier's differential, and the battery that imports the most —
                           the SFX trigger's write set and the stop chain's PSG ledger from
                           test_sound.py, the packed-BCD and meter models from test_hud.py, because
                           $6bb8 calls five reconstructed routines and each is compared through the
                           battery that owns it. A routine whose WHOLE output is a register
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
                           It was the FIRST battery here to import another (`model_lives_draw` and
                           `lives_pokes` from test_hud.py): $fe8c CALLS $e80c, so its write set
                           contains that routine's, and two copies of the geometry could disagree
                           while both batteries stayed green. FIVE batteries now do it for that
                           same reason — test_actor, test_behavior, test_hud, test_scene and
                           test_stage each import a model, a cap or a write set from the battery
                           that OWNS the routine reached — and this entry went on claiming it was
                           the only one for several batches after it stopped being true. What a battery must NOT import is an
                           ENCODER: those go to leaf.py on their third copy, which is where batch 38
                           sent `bit_op_d16`, the three immediate BIT opcodes and the register
                           ordinals rather than let test_effects.py become a third importer of
                           test_actor.py
test/test_player.py        the player frame's differential, and the first battery here whose
                           routines are neither dispatch rows nor map-walkers: EIGHT entry pins, a
                           per-routine CENSUS (six of the eight are named by exactly one instruction
                           in the whole image and the other two by two each, positive and
                           negative), the
                           ladder's odd-x row that separates its $fff1 mask from a $fff0 one, the
                           ascent's zero-speed wrap, the wing boots' level-vs-edge read and their
                           word-wide rearm, and the death arm's whole `snd_play_song` write set
                           imported from test_sound.py. It also states the one arm no case here can
                           DRIVE — the cheat word at $604 lies inside the kit's harness-poked input
                           block, so `make_image` refuses to seed it — with a tripwire case that
                           fails if the block or the load base ever moves. Phase B widened it to the
                           COLLISION MAP (the walk's four probe sites, seeded through test_map.py's
                           own `map_pokes` with the probed rows cleared, so a step's whole effect is
                           the x it commits) and to the actor table's high pool (the weapon's three
                           spawn arms), and added the two structural pins for the routines this
                           project has MEASURED but not ported: the register convention of
                           `player_pending_event_gate`'s spawn site, driven with the two `lea`
                           operands taken out of the image, and the census that says $1fa2 is an
                           ARM of `player_stage_transition` rather than a routine. Phase C then
                           widened it a third time, to the 466-byte DATA BLOCK above $1f54 — three
                           posture records and four cursor-plus-table animations, seeded as one
                           keyed band so that a frame published from the wrong table lands on a byte
                           that is wrong for where it came from — with rows for the chain's ORDER
                           (all four flags raised at once), for the field order that FLIPS between
                           the idle pair and the other three, and for the swing's first frame being
                           indexed by the SFX id. Batch 41 phase A added the NINTH pin, $151a's
                           1,170 bytes, and with it the first COLLISION MAP this battery seeds for
                           itself (the cell is computed from the record's x,y through a stride word
                           that is zero in the shipped image, so a case that seeded neither would
                           read cell 0 of a map of zero-length rows) and the 32-byte SCENE
                           DESCRIPTORS, which are loaded from disk and so have no shipped bytes to
                           run against at all. It is also the battery's first user of the exit-report
                           convention below
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

## Reporting an exit the port cannot take

Three kinds of instruction end a routine somewhere a C function cannot follow: a `jmp` into unported
code, a stack unwind, and a spin the oracle can never leave. The convention is the same for all
three and it is **not** a refusal — the reconstruction runs the whole arm and then RETURNS WHICH
ENDING IT REACHED, out of band, as an integer no image byte can collide with:

* the C function's result is an exit code `#define`d in the module's own header
  (`include/scene.h`'s three, `include/player.h`'s three), scraped by `test/layout.py` so the case
  names the same constants the C does;
* the case sets `stop_pc` to the address of the instruction the report stands for, which diffs the
  whole image at the INSTANT control arrives there;
* and it goes through `leaf.run_reaching`, whose extra argument is the transfer instruction that
  must have EXECUTED. Without that witness a checkpointed case passes whether or not the arm was
  taken, because `emu.run` stops at either the checkpoint or the `rts` and reports only that it
  stopped.

**THE WITNESS HAS TO BE AN INSTRUCTION ONLY THE TAKEN ARM RUNS, and getting that wrong reads as
evidence rather than as a gap.** Batch 41 phase A's first draft named the `beq.w` at `$161c` as the
unwind's witness — and that `beq` executes on every path that reaches the tile-$39 test, taken or
not, so it witnessed nothing. `emu.run` stops BEFORE marking the checkpoint's own PC, so the witness
must lie ABOVE the checkpoint; when the only distinguishing instruction IS the one the report stands
for, move the checkpoint one instruction down. The unwind stops at the `jmp` at `$1626` and
witnesses the `lea 12(a7),a7` at `$1622`, which no other path executes — and the `lea` writes no
memory, so the image compared is still the one at the transfer.

### The busy-wait, which is the third kind and the one with a trap in it

`player_run_map_cell`'s flute arm ends at `$1932`: `lea $17adc.l,a5 / tst.b 378(a5) / bne.s $1932`,
spinning until `WB_SND_ENGINE_ENABLED` goes zero. Only the sound module's own interrupt clears that
byte and no differential run has one, so the spin never ends under the oracle.

The obvious treatment — "read the byte once, report the wait when it is up, and let a case that
wants the rest of the arm seed it ZERO" — is wrong here, and checking WHY before writing the branch
is the recipe:

> **Find out who last WROTE the byte the spin polls.** Three instructions above the `tst.b` is
> `jsr (a5)` on stub +0, and the last instruction of `snd_play_song` is `st 378(a3)` on that very
> byte. So the predicate is FORCED: whatever a case seeds, the spin is entered, and the SIX
> instructions below it ($1938..$194d, 22 bytes, the arm's own `rts` included) are unreachable
> under either core.

So they are **not ported at all** — a branch no case can drive would ship unpinned, which is the
same bar batch 40 phase A applied when it deleted a written-but-undriven walk. The arm ends at the
report. What that costs is recorded in `STATUS.md` as unpinned bytes rather than hidden in a comment,
and the premise is a CASE rather than prose:
`test_the_busy_wait_can_NEVER_be_entered_with_its_byte_clear` runs `snd_play_song`'s OWN 68000 CODE
under the oracle, on an image seeded with the byte CLEAR, and requires it back set. **Ask the
original, not a model of it**: the first draft of that case asked test_sound.py's `model_play_song`,
which is a statement this project wrote — so a reconstruction and its own justification would have
drifted together. It fails the day the original stops raising the byte, which is the day those six
instructions become reachable and have to be ported.

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
off-by-one an index, rebuild, re-run — a mutation nothing catches is a hole. A sweep **lies** in
**seven** ways, all seven measured here, so run one this way:

```bash
mkdir -p "$BACKUP" && cp src/*.c "$BACKUP"     # 0a. A NAMED BACKUP OUTSIDE THE REPO, first and
test -s "$BACKUP"/behavior.c || exit 1         #     unconditionally: a sweep's snapshot can be lost
                                               #     (mode 4), and then the tree is the only copy
                                               #     there is. TWICE now that has been a whole
                                               #     batch. Never `git checkout --` to clean up.
rm -f build/*.so && make build/libwonderboy.so # 0b. ...and force the relink FIRST: a killed sweep
.venv/bin/python -m pytest -q -n auto test     #    leaves the MUTANT's .so beside a restored source
echo "pre-sweep: $?"                           # 0. GREEN FIRST: a red or uncollectable tree
                                               #    reports every mutant as caught (see 5)
test -d snapshot && { echo "a snapshot exists — rm -rf it to RE-ARM"; exit 1; }
mkdir snapshot && cp src/*.c snapshot/         # 4. ONE snapshot, taken only after the green check,
                                               #    and never silently retaken (see below)
for m in mutants/*.patch; do
  diff -q src/ snapshot/ || break              # 4. refuse to run on a tree something else moved
  git apply "$m"
  rm -f build/*.so                       # 1. FORCE the relink...
  make build/libwonderboy.so | tee cc.log
  grep -q clang cc.log || { echo "NO REBUILD — the sweep would be measuring the clean .so"; break; }
  test ${PIPESTATUS[0]:-0} -eq 0 || continue   # 3. a mutant that will not COMPILE is not a result
  .venv/bin/python -m pytest -q -n auto test   # 2. NO pipe: read the RETURNCODE
  echo "$m -> $?"                              #    (0 = SURVIVED, nonzero = caught)
  git apply -R "$m"                            # restore, and re-green before the next one
done
```

1. **`make` can skip the rebuild.** `.so` mtimes have ~1s granularity, so a mutation applied within
   the same second re-runs the *unmutated* library and reports phantom survivors (BuggyBoy's sweep
   reported 8; the real result was 17/17). `rm -f build/*.so` and check the compiler line actually
   ran.
2. **A piped `pytest` hides its exit status.** `pytest … | tail` reports the *pipe's* status, so
   every mutant "survives". Batch 19's first sweep came back 0/37 caught for exactly this reason.
   Take the returncode from the unpiped run.
3. **A mutant that does not COMPILE reports itself as caught.** `make` fails, the `.so` the step
   above deleted is not rebuilt, pytest cannot `dlopen` it, and the returncode is nonzero — which
   "nonzero = caught" reads as a result. Batch 30 hit this after a rename left one file referring to
   a constant another had dropped. **Check `make`'s RETURNCODE, not just that a compiler line ran.**
4. **A killed sweep keeps writing — and the SNAPSHOT STEP is the other half of it.** `pkill` on the
   wrapper leaves the python child alive, and its next restore writes the copy IT read — over
   whatever you have edited since. Batch 30 lost a rename that way twice and then measured 42/43
   "caught" on an unbuildable tree; the honest figure was 33/43. Take the mutant text from ONE
   snapshot captured at the start, refuse to run when the file on disk is not that snapshot, and
   never edit a source while a sweep is running.
   **And the RESTORE has a third half, measured in batch 35: the BUILD ARTIFACT.** A sweep killed
   mid-`pytest` leaves the mutant's `build/*.so` on disk, the `finally` that would have restored the
   sources never runs, and even after you put the sources back by hand the next run's step-0 green
   check loads the MUTANT library and reports the pristine tree as RED. It reads exactly like a
   broken batch. The cure is the first line of the recipe above — force the relink before the green
   check, not only before each mutant — and it is the same guard as the two below rather than an
   eighth way a sweep lies; the frame sentence's count of SEVEN stands.
   **Batch 34 lost a whole batch to the SNAPSHOT half of this mode**, which is why the recipe above
   now guards it: an unconditional `cp src/*.c snapshot/` at the top of a re-run silently overwrites
   the good snapshot with whatever the tree currently holds — and after a killed sweep the tree
   holds a MUTANT, or (as happened) a reverted file. The snapshot is then poisoned and the guard in
   the loop, which compares the tree against it, agrees with the poison. So: snapshot only AFTER the
   step-0 green check passes, and refuse to overwrite an existing one — re-arming is an explicit
   `rm -rf snapshot`. This is not an eighth way a sweep lies; it is mode 4's guard extended from the
   restore step to the capture step, and the frame sentence's count of SEVEN stands.
   **AND A FOURTH HALF, MEASURED TWICE — batch 34 and again batch 39: NEVER RESTORE THE TREE FROM
   GIT DURING A SWEEP.** A timed-out sweep leaves the tree possibly holding a mutant, and the
   obvious cleanup — `rm -rf snapshot && git checkout -- src/*.c` — is the worst thing that can be
   typed at that moment: it deletes the only copy of the good sources and then reverts the file to
   HEAD, which for an in-progress batch is the whole reconstruction. Batch 34 lost `src/behavior.c`
   that way and rebuilt it; batch 39 lost the same file the same way and recovered it only because
   the edits were still in the session's transcript. **A guideline that has been broken twice needs
   a step, not a paragraph** — which is why step 0 of the recipe above now takes a NAMED BACKUP
   OUTSIDE THE REPO before anything else, and why the loop restores from the SNAPSHOT and never from
   git. Like the two halves above this is mode 4's guard reaching one step further, not an eighth
   way a sweep lies.
   A third self-inflicted variant, from batch 35's post-mortem: **`pkill -f` matches its own
   shell's command line** when the pattern string appears in it, so the cleanup kills the shell
   mid-diagnosis and the next check runs against a state you did not establish (a healthy tree
   read as total loss, twice, before the cause was found). Patterns must exclude the invoking
   shell — `pgrep -f … | grep -v $$`, or match on the interpreter path, never on a string your
   own command line carries.
5. **A tree that does not COLLECT reports every mutant as caught.** The returncode is nonzero either
   way, and "nonzero = caught" cannot tell a failing case from a failing import. Batch 21b hit this:
   an encoder hoisted out of two batteries without being added to their import lists broke
   collection, and three real survivors came back "caught" until the tree was green again. **Verify
   green immediately before the sweep, not merely before the batch** — the run at step 0 — and again
   after each restore.
6. **A broken import path breaks PYTEST, not just the tree.** Batch 32 measured it: a `PYTHONPATH`
   holding a `dis.py` shadows the standard library's, pytest itself will not import, and every
   mutant comes back "caught" with nothing having run. Same signature as 5 and the same cure — the
   step-0 green check — but a different cause, so it is worth recognising on sight.
7. **Two projects' suites cannot run at once.** Joust and BuggyBoy rebuild the SAME shared
   `oracle/build/liboracle.so` through `ORACLE_VIA`, so a concurrent run links the `.so` out from
   under the other suite and produces phantom failures that no mutant caused. Run the projects
   **serially** — which also means a sweep here must not share a machine with someone else's
   `make test`.

**A REVIEWER THAT MUTATES IS A WRITER, and the gate has to be told so.** A review agent that probes
a finding by editing `src/`, rebuilding and running the suite is doing everything a sweep does,
including mode 4's restore — and it will snapshot the tree when IT starts and put that snapshot back
when it finishes, over anything the author changed in between. Batch 35 lost a whole de-duplication
that way, silently: both versions were green, so only a grep for the new function NAMES found it.
So, whenever a reviewer may run code: give it a COPY of the tree (or a worktree), or take a named
backup before you let one start; and after any reviewer has run, re-verify the tree BY NAME —
`grep` for the symbols you added — and not only with `git diff`, which looks identical whether your
edit is missing or was never made. The same rule protects the sweep scripts themselves: keep them
out of a shared scratchpad path a subagent might reuse.

**TWO LESSONS FROM BATCH 40 PHASE C, both about reading a sweep rather than running one.**

* **A SURVIVOR'S FIRST EXPLANATION CAN BE TRUE AND STILL NOT BE THE CAUSE.** One mutant survived,
  the diagnosis found a real seeding defect (a keyed band silently dropped), the defect was fixed —
  and the SAME mutant survived the second sweep, because the keyed data was necessary and not
  sufficient: no seed varied more than one of the flags the mutant reorders. Both repairs were
  needed and only the second one was the cause. So a repair earns a RE-RUN of the mutant that
  prompted it, not a tick: "I found something wrong" is not "I found what was wrong".
* **A MUTANT THAT NO LONGER APPLIES IS NOT A CAUGHT ONE.** A review cleanup between two sweeps
  collapsed two arms into one condition, and the mutant that had patched them came back
  NOT APPLICABLE — which a loop that only counts returncodes would never distinguish from a pass.
  Re-spell it against the tree that ships, and run a control beside it, because a collapsed
  condition is exactly the shape that can lose an arm.
* **AND `.pyc` HAS THE `.so`'s MTIME PROBLEM.** Way 1 above is about `make` skipping a rebuild;
  pytest's assertion-rewrite cache is keyed on (mtime, size) too, so restoring a source with a
  SAME-SIZE edit inside the same second re-runs the MUTANT's rewritten module against a restored
  file. It reads exactly like a reproducible failure in clean code. `rm -rf test/__pycache__`
  between mutants, or make the restore change the size.

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
