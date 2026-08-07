# Reconstruction status — Wonder Boy in Monsterland

Human-readable C reconstruction of `SWB.PRG` (the original, uncracked 1989 Activision release,
extracted from the Pasti `.stx` of disk 1), each function to be **verified byte-for-byte against the
original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi oracle
running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 161/? — the .RAD depacker (216 bytes), the first gameplay batch (434 bytes), the status
panel's leaves (430 bytes), the second tier above them (710 bytes), the third tier (1412 bytes), the
WHOLE background scroll engine (3398 bytes), the WHOLE consumer tier that reads it (2742 bytes), the
actor tier and its two projection passes (356 bytes), the WHOLE text subsystem (678 bytes), the
actor table's LIFECYCLE (310 bytes), the COLLISION MAP the actors walk on, both probes and both
settles and the tier above them (892 bytes), the STAGE LOADER that fills the scroll engine's
eight buffers in the first place (1026 bytes), the SPAWN PASS that drives the lifecycle plus the
two resets that start a game and a life (568 bytes), and the WHOLE SPRITE TIER — the twelve
blitters plus `sprite_draw_pass`, the pass that clips, addresses and dispatches them, 2,458 bytes
tiling `$8f02..$989c` exactly (batches 14–15), and now the PANEL'S THIRD-TIER DRIVER pair plus the
SOUND MODULE'S FIRST PORTED BYTES — `panel_frame_timers` + `panel_refresh_frame` and
`snd_trigger_effect` + its register-preserving stub, 660 bytes that close the status panel end to
end (batch 16b) — and the TWO DAMAGE PATHS, `actor_damage_followed` + `actor_damage_template_hitpoints`
(380 bytes, batch 17: the pair rejected twice for a call 16a made visible and 16b made portable),
and the SCENE TIER — `scene_run_frame` + `scene_spend_visit_budget`, the game's dialogue and shop
engine, 990 bytes ported to an honest stop_pc boundary (batch 19) — and the SOUND MODULE'S STOP CHAIN
plus the first game-logic routine that runs it, the game's PRNG and the draw over it
(`snd_psg_silence` + `snd_stop_all_sfx` + `snd_stop`, `actor_defeat_and_score`, `rng_next` +
`stage_random_kind8`, 442 bytes, batch 21b: the seeded PSG read model's first consumer, and the
first ported code here that drives the YM2149) — and the RESPAWN CONTINUATION plus the 32-candidate
draw it calls (`actor_respawn_as_new_kind` + `stage_random_kind32`, 166 bytes, batch 22: batch 21b's
$6cdc boundary is GONE — the defeat path runs end to end to the original's own `rts`) —
18,268 bytes in all, 70.8 % of everything
[`PORTABILITY.md`](PORTABILITY.md) measures.** *(The batch-16 commit's header said 147 — an
oversight; its own section records 151, and batch 17 corrected the header to 153. It now carries
batch 22's 163.)*
`make test`: **3133 cases green in what this batch commits** (3052 before batch 22, plus its 81
net: +49 in `test/test_rng.py`, which stands at 103, and +32 in `test/test_actor.py`, which stands
at 984 — three measured trims inside those figures, recorded in the batch-22 section at the end).
`make test` at batch 21b: **3052 cases green in what that batch committed** (2925 before batch 21b, plus its
127: +36 in `test/test_sound.py`, +37 in `test/test_actor.py` and the new `test/test_rng.py` at 54).
The figures below are batch 19's and are left as that batch wrote them.
`make test` at batch 19: **2912 cases green in what that batch committed** — 2146 before batch 14, plus batch
14's 155 (154 in the new `test/test_blit.py`, and 1 in `test/test_layout.py`: a name defined in
two headers is refused, the guard that batch's `layout.py` scrape extension needs), plus batch
15's 75 (all in `test/test_blit.py`, which stands at 229), plus batch 16b's 189 — 137 in the new
`test/test_sound.py` and 52 in `test/test_hud.py` — plus batch 17's 164 net: 204 damage-path cases
less the 44 a measured review trim removed (two grids re-making already-made claims), +3 in
`test/test_sound.py` (the id-19 completeness work) and +1 in `test/test_effects.py` (the
two-headers slot-byte pin) — plus batch 19's 183 net: the new `test/test_scene.py` at 183 after
its own review trim and coverage additions.
Of the 2912: 77 are the foundation battery below, 48 are the depacker's differential, 187 are the
first gameplay batch's, 548 are the status panel's — that last figure was 169 after batch 2, 339
after batch 3, 481 after batch 10, 485 after batch 12 and 496 after batch 13, and the whole of the
growth is `test/test_hud.py` — 140 the sound module's (batch 16b's `test/test_sound.py`, +3 in batch 17), 231 are the background scroll subsystem's (65 after batch 5, 148 after batch 6),
915 are the actor tier's (113 after batch 8, 222 after batch 10, 755 after batch 13), 105 the text subsystem's (56 after
batch 8), 167 the collision map's, which is batch 10's new `test/test_map.py` (58 when it landed),
80 the stage loader's (65 when batch 12 landed it), 229 the sprite tier's (batch 14's
`test/test_blit.py` at 154, grown by batch 15's pass cases), and the last is `test_layout.py`'s
two-header refusal.
**`test/test_audio_capture.py`'s 13 cases ARE inside the 3052 above, and were not inside the 2912.**
That battery — which pins a KIT mode from this game's suite for `test_poked_input_guard.py`'s reason
— belonged to a concurrent session while batch 19 was being written, so batch 19 counted its own
2912 without it and noted that a working tree would report more. That session has since CLOSED and
committed the battery at 13 cases, which is the whole of the difference between batch 19's 2912 and
the 2925 batch 21b counts from: 2912 + 13 = 2925, + batch 21b's 127 = 3052. Nothing in this batch
rests on it. A row appears in the table at the end when a function is
reconstructed and green; everything else in `../decomp.c` and `../names.txt` is still only *named*,
not ported.

**THAT QUEUE ENTRY IS CLOSED: the 2026-08-05 re-measure is at the end of this file** and
[`PORTABILITY.md`](PORTABILITY.md) §0b records it in full. The "reconstructed and pinned" column now
reads **133 F records / 13,082 bytes**, up from 105 / 10,376 — **twenty-eight functions / 2,706
bytes**, where the hand estimate this header used to carry said twenty-one / 2,048. That gap is the
argument for queueing it as a measurement rather than hand-editing the column: the counting rules
disagree in three places (see `PORTABILITY.md`'s reconciliation table) and an estimate cannot see
them. `subsystems.tsv` gained four subsystems' worth of ranges, so the collision map, the
actor lifecycle, the stage tier and the three buffer builders are out of the "game logic" catch-all.
The 51.3 % this header carried was unchanged by it — a subsystem partition does not move the
25,696-byte denominator, and no whole-program figure in `PORTABILITY.md` moved either. *(The
same-day reapply + re-scan DID move them — denominator 25,786, verified column 136 F records /
13,172 B, header now 51.1 % — see the re-scan section at the end of this file and
`PORTABILITY.md` §0c.)*

**`panel_refresh_frame` ($b346) now has NINE of its ten callees reconstructed.** The tenth, `$bbca`,
is the sound-module blocker batch 3 registered, and it is reached by an unconditional `bsr` — so
`$b346` itself stays unported and no seeding can change that. The reasoning is in "The status
panel's third tier" below. *(Batch 16b: ALL TEN — the blocker fell the only way it could, by
porting the callee: `src/sound.c` opened with `snd_trigger_effect`, and $bbca and $b346 landed
behind it. The panel subsystem is CLOSED; see the batch-16 section at the end.)*

**AND THE TIER THAT FILLS THOSE BUFFERS BEFORE THE ENGINE EVER RUNS IS BATCH 12'S** — see "The
stage loader (batch 12)" at the end. `bg_build_buffer` ($fa30) draws the map's window into copy 0,
`bg_build_preshifted_copies` ($fd46) derives the other seven, and `stage_publish_scroll_state`
($fb06) writes the very row pointers and position words the engine then steps.

**THE WHOLE BACKGROUND-SCROLL STORY IS CLOSED, PRODUCER AND CONSUMER.** All fifteen routines of the
`$7522..$8228` cluster plus the request raiser at `$d28` that drives it — sixteen in all — are the
ENGINE that fills the eight pre-shifted buffers, and `bg_scroll_blit` (`$82f8`) plus the sixteen
unrolled copy variants at `$83b6..$8dfe` are the CONSUMER that copies one of them to the screen.
All thirty-three are reconstructed and green, 6,140 bytes. Nothing between `$7522` and `$8dfe` is
left named-but-unported, and **`subsystems.tsv` draws the subsystem around both halves** —
`$7522..$8228`, `$d28..$d76` and `$82f8..$8dfe` are one `video (background scroll)` range set.
**The 2026-08-05 re-measure added the third half**: batch 12's three buffer BUILDERS
(`$fa30..$fc46`, `$fd46..$fe0c`) and its three banner plotters (`$e110..$e19a`) write the same eight
buffers, so the subsystem now measures **39 functions / 7,010 bytes inside a function body, 100 % of
them reconstructed and green** — the largest such row in the file. What is still NOT closed is the
routine that calls the builders: `stage_load_window` (`$f95c`) ends in a `jsr` into the sound
module, which is why it is filed under `stage (load + reset)` and is that row's only unrunnable
function. See "The background scroll engine", "Closing it", "The consumer tier" and "The stage
loader" below, and the two re-measure sections at the end for what re-drawing the boundaries moved.

## What the harness has established

These are the results of `test/test_bootstrap.py`, all of them read off the original binary or off
the original code running under the oracle:

- **The loader is correct for this .PRG.** text = `0x214d8`, no data, no bss, three relocation
  entries; the image at `load_base` is the file's text verbatim apart from those three longwords,
  each `raw + load_base`.
- **The program is not position-independent — it relocates ITSELF to the absolute address `0x400`.**
  The entry point is a trampoline (`move.w d0,d0` / `jmp $213e0.l`, the target relocated) into a
  relocator at the end of the text, which copies `0x84f6` longwords (`0x213d8` bytes) from
  `load_base + 8` to `0x400` and jumps there. Run under the oracle to its `jmp`, with the
  destination compared against the file's own bytes, the neighbours on both sides proved untouched,
  and the write set proved to be exactly the destination range. Constants in
  [`include/wonderboy.h`](include/wonderboy.h).
- **`load_base = 0x3f8` makes the loaded image the runtime image.** `load_base + 8 == 0x400`, so the
  relocator's source and destination coincide and its copy is an identity copy — the program's own
  absolute operands address the loaded image directly, no staging step is needed, and the base
  agrees with `../names.txt` (checked against two of its anchors, `startup_relocate_and_run` at
  `0x217d8` and `cold_start` at `0x400`).
- **The game issues exactly ONE TOS trap in its whole image**: the GEMDOS `Super` at file offset
  `0x213ea`, immediately preceded by its in-line `move.w #$20,-(a7)` selector, with its argument
  (a relocated operand) pinned to the first byte past the program. Every other even-aligned
  `trap #N` encoding in the file sits inside an ASCII message string — pinned by offset, so a fifth
  one appearing anywhere fails the case. **The same five hits survive relocation**: the scan reads
  the file, but what the 68000 executes is the relocated image, and each of the three fixups
  rewrites four bytes that could in principle create or destroy a `trap #N` encoding, so the scan is
  re-run over the loaded image rather than argued about. So the game drives the hardware directly,
  including the floppy: it loads its own overlays by name with no GEMDOS file call anywhere.
- **The Copylock is stubbed, and every stubbed run proves it.** `test/copylock.py` offers two
  mechanisms with different domains — poke `copylock_arm_flag := 0` (undone by the game's own
  `move.w #$ffff` at `$e51e`/`$e6dc`, so it is valid only below an arming site) and poke `rts` over
  `copylock_entry` (valid anywhere, because an arming site does not write code) — and applies both
  by default. `copylock.run()` then refuses any result whose memory shows the protection ran, using
  a **difference** witness rather than a write-set one: at this load base the relocator's identity
  copy writes all 2,220 of the protection's bytes without changing any, so a write-set witness
  reports a false "it executed" for a `move.l (a0)+,(a1)+` loop. The guarantee is exactly "any run
  that COMPLETES the `movem.l d0-a7,(a6)` at `$ed4c`" — the five instructions before it are a blind
  window, and a caller's own pokes could land on both sides of the comparison, so `run()` refuses a
  `stop_pc` inside the blob and `stubbed_image()` refuses a poke overlapping the watched span. 40
  cases in `test/test_copylock.py`, including the negative controls for what an unstubbed run does:
  entered at the guard it reaches the decryptor at `$ee02` and **never returns** (the kit's Musashi
  is built with `M68K_EMULATE_TRACE` off, so the blob cannot self-decrypt), while entered at an
  arming site it **does** come back — to `$e7c8` in 184,997 instructions with 2,053 bytes of the
  protection scrambled, which is the false green in its exact shape. What the stub is worth, and the
  seven things it knowingly does not verify, are in [`PORTABILITY.md`](PORTABILITY.md) §6.1.

## The kit changes this project required

`load_base` **must** be below the kit's `OS_POKE_BLOCK_END` floor (`0x620`): the game runs at the
fixed absolute address `0x400`, and everything below that is the 68000 vector page. So the kit
gained a second waiver, built exactly like the existing `tos_malloc_unused` one and off by default:

* `project.toml` may declare `tos_poked_input_unused = true` — the claim that the game reads none of
  the harness-poked state (no `Bconstat`/`Bconin`/`Crawio`, no `Random`, no `Giaccess`, no
  `Kbdvbase`), which is what lets its program cover that block;
* the claim then buys the layout and **never a green run**, because two guards re-test it instead of
  trusting it, both keyed on the *overlap* rather than on the flag:
  * `emu.run()` refuses any run in which a trap reached the block (`_vet_no_poked_input_read`, keyed
    on the oracle's new `osh_poked_input_calls` tally) — the direct sibling of the Malloc waiver's
    per-run re-check, and the half that watches the **game** rather than the test. One case per
    counted trap pins all six increments; the tally is oracle-side only, and `TRAP_MODEL.md` states
    what that does and does not cover;
  * `harness.make_image()` refuses any poke whose byte range lands in the block, at the layer pokes
    are applied — so a hand-written `{OS_RANDOM_VALUE: …}` dict, the only way to stage an XBIOS
    `Random`, is seen exactly like a `console_key()` one;
  * `console_key()` / `psg_regs()` still refuse as well, but only as a friendlier early error.

Pinned by [`test/test_poked_input_guard.py`](test/test_poked_input_guard.py) — including that the
unwaived check really does fire here, and a negative control that disarms the run guard and measures
the false green it prevents (a `Bconin` reading the program's own bytes, being told a key is
pending, and zeroing four bytes of code). Wonder Boy is the only project the overlap exists for, so
the wiring can only be pinned here; the geometry underneath is pinned kit-side in
`tools/recreate_kit/test/test_os_map.py`. BuggyBoy (292 cases) and Joust (4368 cases) were re-run
green after the change.

**The second: the oracle reports the whole `movem` register set (batch 11).** `emu.run`'s result
dict used to hold `d0`/`d1`/`a0`/`a1`; it is keyed by `emu.REPORTED_REGS` now — `d0..d7` and
`a0..a6`, `a7` deliberately absent — because three reconstructions here had stopped short of that
window rather than of any difficulty. Decided in `TRAP_MODEL.md`, "What a run reports back", pinned
kit-side by `tools/recreate_kit/test/test_reported_regs.py`, and written up in full (the `a7`
exclusion, the three limits the report leaves, and what the widened window closed) in the batch-11
section at the end of this file.

## The oracle defect the status-panel batch surfaced

**Every `emu.run` used to inherit the previous run's condition codes.** A 68000 reset does not clear
the CCR and Musashi is faithful about it — `m68k_pulse_reset()` touches T, the interrupt mask and S,
and leaves `FLAG_X`/`N`/`Z`/`V`/`C` exactly as the last run left them — while `osh_run` set every
data and address register but not `SR`. So a routine that reads a condition code ON ENTRY answered
differently depending on what had run before it, in the same process.

The panel batch's four packed-BCD accumulators are the first reconstructions to read one: `abcd` and
`sbcd` fold in the extend bit, and the two instructions ahead of the first one (`move.w d0,$bd78`
and a `lea`) leave X alone, so entry X is live input. It showed up as four cases that reddened under
`-n auto` and passed on their own, each off by exactly one unit in the lowest digit.

`tools/recreate_kit/oracle/shim.c` now forces `ENTRY_SR` (`$2700`: supervisor, IPL 7, condition
codes clear) after the reset, in **both** entry points: the reset and the force are one
`enter_from_reset()` helper that `osh_run` and `osh_run_bench` share, so they cannot drift (the bench
path was left un-forced when the fix first landed, and inherited the CCR just as `osh_run` had).
Four things about that:

* **it is a correctness fix, not a new capability** — two identical `emu.run` calls now give the
  same answer, which is what a differential rests on. `emu.run` still has no way to SET the entry
  CCR, so the X = 1 entry the game itself reaches stays unreachable from a case (registered below);
* **the entry SR is a stated modelling decision now**, registered in
  `tools/recreate_kit/TRAP_MODEL.md` ("The entry state every run begins from") beside the
  `M68K_EMULATE_TRACE` one, with the same reasoning: `$2700` is the kit's convention for
  determinism, not a claim about any game's own boot SR;
* **it is pinned behaviourally on both sides.** Kit-side by
  `tools/recreate_kit/test/test_entry_state.py`, whose `entry_state_probe.c` runs one `abcd` three
  times in one process (the middle run wraps and leaves X set) — it compiles `shim.c` itself rather
  than linking the shared `liboracle.so`, so a reverted force cannot hide behind a stale artifact.
  Game-side by `test_hud.py::test_the_oracle_enters_every_run_with_the_condition_codes_clear`, over
  the reconstructions that surfaced it. Reverting the shim line and rebuilding reddens 2 of the
  kit's 5 probe cases and the game-side case with `assert 1 == 0`, so neither is vacuous;
* **the other two projects were re-run against the rebuilt oracle at this tree state** — BuggyBoy
  **292 green**, Joust **4368 green**, each with its candidate `.so` deleted first so `make` could
  not re-run a stale library. Since the oracle is shared, that is what says neither depends on a
  leaked flag, which was the risk.

## Blockers, in the order they will be hit

**1. The game's one trap is refused by the kit's trap model.** It calls `Super(<end of program>)` —
real GEMDOS's "enter supervisor mode with THIS supervisor stack". The kit's `Super` is a token
model that accepts only `0`, `1` and its own cookie (`tools/recreate_kit/TRAP_MODEL.md`, Phase 2),
so `emu.run` raises rather than fabricate a result. Pinned by
`test_the_games_only_trap_is_a_super_the_kit_refuses`. It costs nothing today — the oracle already
runs in supervisor mode, so an oracle run simply enters one instruction later, at
`WB_RELOCATOR_COPY_OFF` — but any case that must cross that instruction is blocked until the model
takes a third `Super` form.

**2. The game's own I/O is all direct hardware, and the oracle models almost none of it — MEASURED,
see [`PORTABILITY.md`](PORTABILITY.md).** With one trap in the whole image, everything the game does
to the shifter, the PSG, the IKBD and the floppy controller is a raw register access: 126 accesses
over 120 instructions, 31 reads and 95 writes, of which 18 are register-indirect and invisible to
any operand scan.

The measurement's answer, in the terms that decide a reconstruction order. **Every figure below is
out of the 25,696 bytes Ghidra has put inside a function body, which is 46.8 % of the ~54,854 bytes
`../notes/architecture.md` calls CODE** — the denominator is part of the finding, not a caveat:

* **220 of 252 functions (21,534 of 25,696 bytes, 83.8 % of what is measured; 39.3 % of the
  program's believed code) can be run end-to-end under the oracle today.** The blocker on the rest
  is the kit's outright rejection of a direct PSG **read** (`TRAP_MODEL.md`, Phase 3) — the same
  wall that put Joust's raw-floppy routine off its list. Here it is exactly three instructions: the
  floppy drive-select's read-modify-write of port A, and two mixer read-modify-writes in the sound
  module.
* **28 functions (3,348 bytes, 13.0 %) are at FALSE-GREEN risk**, and that is a *lower* bound — a
  conditional branch below them depends on a hardware read the shim answers `0` on both sides.
  Proven, not argued: under the oracle this game's floppy *polls* report a flawless error-free
  transfer on their first status test while moving nothing (the MFP FDC line is active low), the
  *commands* above them then reject that fabricated status and report hard failure, and the music
  replay tempo is chosen unconditionally by a zeroed `$fffa01` bit 7 / `$ff820a` bit 1 — BuggyBoy's
  defect, present before a line is ported.
* **T1 is empty**: every PSG writer in this game also reads the PSG, so no byte of the sound
  subsystem is verifiable *through the modeled write ledger*. That is not the same as unverifiable
  — `snd_trigger_effect` (`$1a48a`) is T0 with an exact closure and is diffable today, and 62 % of
  the sound module is runnable now.
* **The gameplay logic is portable now, as far as it has been recovered**: 85 of its 87 recovered
  functions touch no hardware at all (the two exceptions are the game's PRNGs), and 78 (5,156
  bytes) are runnable end-to-end. **62 of them / 3,098 bytes are ported and green** — the
  effect/state leaves, the joystick edge pair, the whole status panel (its leaves, the second tier
  above them and the third tier, the table at the end) and now `hud_draw_lives`. **That figure was
  51 out of 138 before the 2026-08-02 re-measure and 61 out of 114 after it**; the 2026-08-05
  re-measure takes it to 62 out of 87, and the whole of the +112 bytes is `hud_draw_lives` ($e80c)
  arriving **from** the `boot` bucket, where it never belonged. Every one of the thirty other
  functions batches 10–13 added (27 green F records under PORTABILITY's counting) LEFT the
  catch-all rather than joining it — the collision map, the
  actor lifecycle, the stage tier and the buffer builders are all subsystems of their own now. Of
  the earlier movement, none is batches 5–9's doing either: all forty-one of their functions end up
  outside the catch-all (twenty-four moved by the 2026-08-02 boundary redraw, and the seventeen
  consumer-tier blits were in the video range under either file). The +10 that got it to 61 is batch
  4's status-panel third tier — ten functions / 1,412 bytes ($d93a, $daf8..$db72, $b39c, $b3da,
  $b8f0) that landed after the 2026-08-01 measurement; 2,986 − 1,412 = 1,574 = 434 + 430 + 710, the
  old 51's exact composition (see "The portability re-measure"). The
  measurement was right that every leaf's whole surface is memory, and right that they need no new
  harness capability in the sense it meant; the panel batch still cost `test/leaf.py` a
  register-argument glue and a per-routine instruction cap, and it surfaced a defect in the shared
  oracle (above) that a batch of one-instruction setters could never have reached. The second tier
  cost nothing further: a non-leaf differential is the same call with the callees running under the
  oracle. So is every sprite blitter, the background scroll blitter and the
  RAD depacker. **But game logic is also the worst-measured subsystem that can be read at
  all, and both re-measures made it worse rather than better** (only the Copylock, which cannot be
  read, is below it) — those 6,904 bytes are 21.8 % of the 31,714
  bytes of game-logic CODE believed to exist, against 53.5 % for boot and 69–100 % for sound, disk,
  input, text, map, stage, actor and video. Carving three characterised subsystems out in 2026-08-02
  took 4,432 measured bytes with them and only 14 unmeasured ones; carving four more out in
  2026-08-05 took 2,692 measured bytes and only 90 unmeasured ones — and those 90 are two routines
  that ARE reconstructed and green but sit in no Ghidra function at all.

`PORTABILITY.md` also prices each missing harness capability in functions and bytes, and
[`../notes/portability_predictions.py`](../notes/portability_predictions.py) re-runs thirteen of the
classifications against the real oracle — three of the first nine were wrong on the first pass, and
the corrections are recorded in both files — plus a fourteenth check pinning the 16
background-scroll names to the jump table the game dispatches through.

**A workspace-wide defect surfaced on the way**: `tools/ghidra_scripts/PrgLoader.java` mis-parsed
the DRI relocation table's 254-byte span marker as a fixup, so **every** project's Ghidra DB was
built over corrupted bytes (536 spurious fixups here, 93 in BuggyBoy, 44 in Joust). It is fixed and
pinned by `tools/recreate_kit/test/test_reloc_table.py`; the reconstructions are unaffected because
`oracle/loader.py` always used the correct parser, but the DBs and `decomp.c` need re-bootstrapping.

**3. The overlays are decoded; the memory ceiling still is not.** `OVALAY*.RAD`, `TILEDATA.RAD`,
`SPRITES.CRU`, `DATADISK.RAD` on disk 2 are packed data the game loads by name (the names are in
the image at `0x21226`). Their **format is now established and pinned**: the depack routine is the
game's own, at text `0x596a` / runtime `0x5d62`, transcribed in `notes/rad_depacker.asm`,
reimplemented as `tools/depack_rad.py`, and diffed against the original under Musashi by
`notes/rad_differential.py` — 41/41 intact streams byte-identical, plus the 4 protection-damaged
overlays which both implementations refuse (`docs/binary-formats.md` has the format). The routine
itself is now **reconstructed** as well (`src/rad.c`, the table at the end), on the same corpus but
as a whole-image differential, so the format is pinned from both sides: a host reimplementation that
refuses what it cannot safely decode, and a faithful port that reproduces what the 68000 does
instead — garbage decode and all.

The **destinations** are readable from the five call sites, all at runtime addresses: overlays
depack to `0x217d8` (`0x3ce8` each), `TILEDATA.RAD` loads at `0x44000` and depacks to `0x4f000`
(`0x14a80`), the three full-screen files load at `0x49800` and depack to `0x6ff80` / `0x77f80`
(`0x7d80` each), and `SPRITES.CRU` is loaded raw to `0x25298` and never depacked. The highest
address any of them reaches is `0x7fd00`. That is **not** yet a memory ceiling: these buffers are
reused across phases rather than live at once, and nothing here audits the rest of the program for
other buffers — see `project.toml`'s `image_size` comment, which this narrows but does not close.

## Unverified claims this project currently rests on

- **Both waivers rest on the same fact — one trap in the image — and that scan covers the shipped
  `.PRG` only.** The game demonstrably depacks data, and it could depack code; a trap encoding that
  exists only after depacking is invisible to a scan of the file. That is why neither waiver is
  trusted: the Malloc half is re-enforced per run by `emu._vet_no_malloc_over_program()` and the
  poked-input half by `emu._vet_no_poked_input_read()`, so a trap that only exists after a depack
  reddens the run it appears in rather than being diffed. What no check covers is `OS_SCREEN_BASE`
  (`0x8000`, what `Physbase`/`Logbase` return), which is also inside this program: those two traps
  are tallied by nothing, so a program that drew into the modeled screen base would scribble its own
  code identically on both sides. Inert today for the same reason as everything else here — there is
  one trap in the image, and it is a `Super` — and recorded in
  `tools/recreate_kit/TRAP_MODEL.md`.
- **`image_size = 0x100000`** fits every address read out of the code so far (highest: `0x7fd00`),
  but no audit has established a ceiling — see blocker 3.
- **The ASCII-run rule** that separates the one real trap from the four message-table false hits is
  a heuristic with a wide measured margin (runs of 12–16 bytes vs 4), not a proof. It no longer
  stands alone: the five even-aligned hits are also pinned by offset, and the Super site by its
  selector push and its relocated argument.
- **`../run.sh` passes `0x3f8`**, so a re-bootstrap agrees with this directory and with
  `../names.txt`. It still re-imports and wipes the DB, so iterate with `../reapply.sh`.
- **The status panel's fifteen `proto` lines have not been through `ApplyNames` yet** — the eight
  the leaves added and the seven the second tier did (`$b54c`, `$b5ea`, `$b74a`, `$b7c6`, `$b7ea`,
  `$bd32`, `$bd4a`). Their storage is read off the disassembly and each one is pinned from the other
  side by a differential case that feeds that register — but a `proto` commits CUSTOM_STORAGE in
  Ghidra, and wrong storage breaks a decompile rather than failing loudly, so they are unverified in
  the DB. That is blocked on the same thing as everything else in `../ghidra_proj`: the `PrgLoader`
  relocation defect below means the DB has to be re-bootstrapped before any re-apply is meaningful.
  `hud_plot_digit` ($b850) deliberately gets a `cmt` and no `proto`, for `hud_blit_meter_cell`'s
  reason and one more: it returns the advanced cursor in `a0` (which the directive forces to void)
  and its `d7` is IN AND OUT.
- **The kit's relocation arithmetic has no test of its own.** `test_the_loader_changed_exactly_the
  _three_relocated_longwords` covers `oracle/loader.py`'s fixup loop, which BuggyBoy and Joust also
  rest on, from inside one project's suite. The game-specific half (no fixup lands inside the copied
  body) belongs here; the arithmetic half belongs in `tools/recreate_kit/test/`.
- **A reconstruction verified under the Copylock stub is verified for the game's DISARMED steady
  state** — the second and subsequent resource loads — **and not for the first.** The protection's
  own effects (the 96-byte register save area, the three vector installs, the decrypt cursor, the
  key it returns in `d0`) never happen under the stub, and `disk_check_signature` (`$5e3e`), the
  `$ecba` pointer table and the readers of `$f89a`/`$f89c` stay reachable only from inside the
  ciphertext. `PORTABILITY.md` §6.1's "KNOWINGLY UNPINNED" list is the full register.
- **All three of the Copylock module's protections stop at `copylock.run()`'s door, and
  `recreate_kit.harness.differential()` is a second door**: it calls `emu.run` itself, so
  `differential(entry, regs={"_pokes": copylock.stub_pokes()}, stop_pc=...)` gets no witness, no
  poke vetting and no `stop_pc` vetting, and its author must call
  `copylock.assert_did_not_execute()` by hand. Four things about that gap, so the next author
  neither over- nor under-reacts to it:
  * **Nothing that calls `differential()` goes near the protection yet.** `test_rad_depack.py` is
    the first caller, and `rad_depack` neither reaches the Copylock nor is reached from it: it is
    entered directly, its whole run is inside its own two buffers, and its cases stub nothing. The
    gap opens the day a differential runs a function on the boot path. And under this build,
    forgetting the stub does not go green: it fails loudly with `did not reach checkpoint`.
  * **The identified fix is `differential()` returning its final image**, so a caller can run the
    witness over it. Not built — nothing uses it yet, and CLAUDE.md §2 rules out speculative
    features. It is the cheaper and safer of the two candidates, and the one to build the day a
    boot-path differential is written. It closes the WITNESS half only; the two input guards would
    still have to be reached through `copylock.stubbed_image`, i.e. `differential` would need to
    take an image rather than build one.
  * **A per-run forbidden-WRITE veto in the kit was REJECTED**, not deferred. It would fire on
    `test_bootstrap.py`'s relocator runs, which write all 2,220 of the protection's bytes without
    changing one of them — the exact false positive that forced the witness to be a memory
    *difference* rather than a write set in the first place.
  * **That rejection is about the write-set FORM, not about the kit hosting a veto at all.** A
    difference-based veto over project-registered immutable ranges has no false positive on those
    relocator runs — the identity copy changes nothing — and would be the general form of this
    module's witness. It is also unbuilt, and it is the same change as returning the final image,
    so do not read "rejected" as "the kit cannot host this".
- **The Copylock witness's soundness rests on a kit-wide CPU setting**, `M68K_EMULATE_TRACE=0`. A
  trace decryptor re-encrypts as it goes and restores the vectors it saved, so a blob that ran to
  COMPLETION would leave the witness almost nothing to see; what stops it completing is that flag.
  It is now pinned in `tools/recreate_kit/kit.mk`'s `OCFLAGS` (it used to be the vendored, gitignored
  `m68kconf.h`'s own default — untracked, and asserted by no test), documented in
  `TRAP_MODEL.md`, and asserted behaviourally by
  `test_copylock.py::test_the_oracles_cpu_takes_no_trace_exception`.
- **Three test helpers are now duplicated rather than shared, and the shared home is the kit.**
  `test_copylock.py`'s `_image_writes` is the fourth copy of the `< emu.STACK_GUARD_LO` stack-band
  filter in this workspace (`notes/portability_predictions.py`, two in `projects/joust`) and its
  `_run_reaching` the second; `LONGWORD = 4` and the `rts` opcode literal are each a second/third
  spelling inside this directory alone. All of them belong in `tools/recreate_kit/harness.py`
  alongside the diff's own use of that band; folding them together is a kit change touching three
  projects and was left out of this one as out of scope. Related: `_run_reaching` clears the
  oracle's process-global coverage bitset, which is harmless only because this project has no
  session-wide coverage `conftest.py` the way `projects/buggyboy` does. Two more found by the
  review of the Copylock work and left alone for the same reason, both inside `test/`:
  `test_copylock.py`'s even-aligned operand sweep re-implements `test_bootstrap.py`'s
  `_even_aligned()`, and its `RELOCATOR_INSN_BUDGET` is a hand-rounded copy of that file's derived
  `RELOCATOR_INSN_CAP` — the derived one tracks `WB_BODY_LONGS` and the copy does not. The depacker
  work added a scratch-band predicate deliberately TIGHTER than the registered
  `< emu.STACK_GUARD_LO` family (it bounds the band above as well as below, since A7 enters at
  `STACK_TOP` and grows down); the gameplay batch needed the same one for two more batteries, so it
  now lives once in `test/leaf.py` as `stray_writes(writes, allowed)` and `test_rad_depack.py`,
  `test_effects.py` and `test_input.py` all call it. The scroll batch then arrived with a fifth
  spelling of the band — `test_scroll.py`'s `_program_writes`, which subtracts the stack from a write
  set instead of checking one against permissions — and it had drifted: its bound was `<= STACK_TOP`,
  which excludes only the FIRST byte of the return slot and leaves the other three in. The band is
  now one predicate, `leaf.on_machine_stack(addr)`, that both `stray_writes` and `_program_writes`
  call, and its upper bound is `< STACK_TOP` for a stated reason: the longword AT the stack top is
  the return address the runner planted, and a step that rewrites it (`addq.l #4,(a7)`) is program
  output that a case reads, not a frame to excuse. **The in-directory copies are collapsed.** What
  is left of this particular family is `../notes/rad_differential.py`'s copy — a frozen research
  artifact that must run without this directory — and the kit consolidation above; `leaf.py` is the
  shape the kit's version should take (an allowed-ranges list, with the two-sided stack band
  implicit), so folding it in is the same change. The buffer placement and corpus walk in
  `test_rad_depack.py` are still restated from `rad_differential.py`.
- **The status-panel batch's own scaffolding is collapsed into `test/leaf.py`**, which
  `test_effects.py` and `test_hud.py` now share one definition of each: the operand encoders `word()`
  / `longword()` (both MASK to their width — the 68000's operand field holds exactly two or four
  bytes, and without the mask a negative `dbf` displacement raises `OverflowError` instead of failing
  readably); the five opcode encodings both batteries spell (`RTS` and the four `move.w` forms —
  each keeps its own single-use encodings next to the routines that need them); the write-set readers
  `read_bytes` / `read_int`, which replaced this directory's two spellings of "the value the original
  left at an address" and fixed the one real defect in them (both sorted their failure message's
  addresses as STRINGS, so `$b10` sorted before `$b9`); `assert_rows`, which collapsed the three
  row-comparison idioms `test_hud.py` had; and `assert_batch_is_complete`. **What is left in this
  family:** each battery keeps its own `_filler`/`_rows`/`_seeded_rows` seeding helpers, which are
  geometry-specific rather than shared. The meter-cell battery's hand-rolled plane loop, registered
  here when the leaves landed, is **collapsed**: the second tier needed the identical comparison for
  every digit, so `_plotted_column` / `_assert_column` / `_seeded_column` now live once in
  `test_hud.py` and the meter cell, the meter's own pass and all nine digit batteries call them. They
  stayed in that file rather than moving to `leaf.py` because nothing outside the panel plots an
  8-row column. **The same collapse then happened on the C side**: `src/hud.c` carried the plane loop
  twice — once in `hud_blit_meter_cell` over a host pointer, once in `plot_column` over `addr_add` —
  and `plot_column` now takes a row count and serves both, so the meter's cell walks its destination
  through the 68000's address ALU as well and a stride mutation reaches both routines. **The scroll
  batch added the branch assemblers to the same collapse**: `test_scroll.py` arrived with a third
  spelling of the branch-displacement arithmetic (`branch_w` / `dbf` / `_bsr_w` against
  `test_hud.py`'s `_forward_branch` / `_dbf` / `_bsr_to`), so `forward_branch(spanned)`,
  `backward_branch(body)` and `bsr_w(here, target)` — plus the `BRANCH_EXTENSION` of 2 all three turn
  on and the one `BSR_W` opcode — now live once in `leaf.py` and both batteries call them. Only the
  displacements moved: each battery still spells its own branch OPCODES, byte constants in one file
  and integers fed to `_op()` in the other, because that is where they differ. The whole-body entry
  pins are the proof the hoist changed nothing — 1590 bytes of scroll and every panel routine still
  match the shipped image byte for byte. **Batch 11 hoisted four more encoders on evidence rather
  than on the two-user rule**: `test_map.py` arrived spelling `move_b_d16_dn`, `cmpi_b_dn`,
  `addq_b_d16` and `lsl_w_imm_dn`, all four already in `test_actor.py`, and one of the pairs had
  ALREADY drifted textually — `addq.b`'s opcode written `0x5028 | ((amount & 7) << 9)` in one file
  and `0x5000 | ((amount & 7) << 9) | 0x28` in the other, the same value spelt two ways. So they
  went to `leaf.py` at two users instead of being registered for a third, and the batteries' entry
  pins are again the proof nothing moved.
- **`rol.l` on the PYTHON side is written twice.** `test_hud.py`'s `_rotate_left32(value, bits)` (the
  digit register's nibble and byte rotates) and `test_scroll.py`'s `_rol32(value, count)` (the
  preshift's) are the same four lines over the same 32-bit mask — the C side's own pair of these is
  the RESOLVED entry below, and this is its Python mirror, left alone because the two batteries model
  different routines with it. Usual terms: **trigger** = a third battery user; **home** =
  `test/leaf.py`, beside `u16`/`s16`, in the guarded form that takes a count of 0.
- **`tst.w Dn` now has a user in each battery.** Batch 7 collapsed `test_scroll.py`'s own two
  single-register spellings into the encoder `tst_w_dn(reg)` (four registers use it), and
  `test_hud.py` still carries the byte constants `TST_W_D5` / `TST_W_D6`. Registered on the terms
  the rotate above was: **trigger** = a third user; **home** = `test/leaf.py`, beside the branch
  assemblers, in `tst_w_dn`'s parametrised form rather than as more per-register constants.
- **RESOLVED (batch 6: the preshift was the third user; now `machine.h`'s `rotate_left32`).** `rol.l`
  used to be written twice on the C side — `src/hud.c`'s unguarded `rotate_left32(value, bits)` for
  its literal counts of 4 and 8, and `src/scroll.c`'s `rotate_left32_by_register(value, count)` for a
  RUNTIME one (a phase word, 0..14, or the 16 the right edge substitutes for phase 0), which had to
  survive a count of 0 where the 68000 rotates by nothing and C's `value >> 32` is undefined. Batch 5
  registered the trigger as the preshift batch, and that is what fired: `bg_scroll_preshift_rows`
  (`$8144`) rotates by `rol.l #2` and was the third caller. The guarded form now lives once in the
  kit's `tools/recreate_kit/include/machine.h` beside `addr_add`/`sign_ext16`, and both files call it.
  It masks the count to five bits, which is the 68000's REGISTER form exactly — `rol.l Dm,Dn` rotates
  by `Dm mod 64` and a 32-bit rotate is cyclic mod 32 — so it is total for every count a caller can
  hand it, and costs a literal-count caller nothing after inlining. Being a kit file touching three
  projects, it lands as its own commit ahead of the batch.
- **RESOLVED (batch 8: `actor_followed_x_within` was the third user; now `machine.h`'s
  `set_low_word`).** It used to be written twice, in two projects — `src/scroll.c` and joust's
  `recreate/src/object.c` — and the two bodies said the same thing: a `move.w`/`clr.w` on a longword
  register replaces the low word and leaves the high one alone. `$67f8` returns its answer in d0's
  low word with the caller's high half surviving, which is the registered trigger; the helper now
  lives once in `tools/recreate_kit/include/machine.h` next to `set_low_byte`, and both projects
  call it. Being a kit file touching three projects it lands as its own commit ahead of the batch,
  as `rotate_left32` did, and BuggyBoy (292) and Joust (4368) were re-run green against it.
- **`RAD_HDR_LEN` (`include/rad.h`) and `HDR_LEN` (`tools/depack_rad.py`) are the same 12 bytes in
  two languages, accepted as pinned BEHAVIOURALLY rather than textually.** CLAUDE.md §5 asks for one
  canonical definition with the other held equal by a test; here each side has its own differential
  over the game's own corpus, so a drifted copy reddens its own suite on the first file it decodes.
  `depack_rad.py` is a workspace tool that must run without this project, so it cannot scrape this
  directory's headers the way `test/layout.py` does — which is why the equality is bought with
  behaviour instead.
- **`test/layout.py`'s header scraper is the third copy** of the same idea (`joust`'s
  `test_constants.py`, `buggyboy`'s `test_course_ring.py`). It belongs in the kit; folding the three
  together was left out of this change as out of scope. It now has cases of its own
  (`test/test_layout.py`) and refuses the two readings it used to get wrong — a duplicate `#define`
  (it took the last silently) and a leading-zero decimal, which C reads as octal and Python refuses
  (it died with a bare `ValueError` naming neither the header nor the constant).

## Functions (by address)

| Addr | Name | Bytes | Status | Verification |
|------|------|-------|--------|--------------|
| `0x682` | `joy1_newly_pressed` | 18 | verified | 21 cases: 7 frame-pairs (idle / pressed / HELD / released / mixed / all bits) x 3 entry `d0`s. It writes no memory at all, so the returned `d0` is the whole surface — compared as a full longword, which is what pins the byte-op width |
| `0x88c` | `joy1_latch_edge` | 20 | verified | 5 cases seeding all three pipeline bytes distinctly, plus a write-set assertion that each stage took its predecessor's byte (so a port that shifted the wrong way cannot pass) |
| `0x5d62` | `rad_depack` (`src/rad.c`) | 216 | verified | 45 differential cases: the 41 intact `.RAD` streams of the game's own corpus decode byte-for-byte identically (whole-image diff + `d0`), and the 4 protection-damaged overlays reproduce the garbage decode *and* the failure status. Plus a synthetic corrupted checksum, an attribution (poison) pass folded into the two smallest intact cases, and a per-case guard that the only bytes written are the destination and the scratch long |
| `0x10200` | `set_state_bbc8_1ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1020a` | `set_state_bbc8_2ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10214` | `set_state_bbc8_3ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1021e` | `set_state_bbc8_4ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10228` | `set_state_bbc8_6ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10232` | `set_state_6f9c_ffff` | 8 | verified | 4 setter cases + entry pin (the entry pin is what covers its SHORT operand) |
| `0x10296` | `effect_add4_clamped_b6fa` | 38 | verified | 10 cases: a 5-point sweep of where `value + 4` lands relative to the maximum (-4, -1, 0, +1, +4 — which pins the comparison against a SHIFTED one, though not against a non-strict one: see the batch notes) and 5 more outside the meter's own range that make the compare's SIGNEDNESS and the 16-bit wrap observable. Each case also asserts the word the meter ended at |
| `0x102bc` | `effect_add2_clamped_b6fa` | 38 | verified | Same battery as `0x10296`, with `value + 2` |
| `0x102e2` | `effect_set_bd6a_1` | 10 | verified | 4 setter cases + entry pin |
| `0x102ec` | `effect_set_bd6a_2` | 10 | verified | 4 setter cases + entry pin |
| `0x102f6` | `effect_set_bd6a_3` | 10 | verified | 4 setter cases + entry pin |
| `0x10300` | `effect_set_bd6a_4` | 10 | verified | 4 setter cases + entry pin |
| `0x1030a` | `effect_set_bbc2_80ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10314` | `effect_set_bd66_1` | 10 | verified | 4 setter cases + entry pin |
| `0x1031e` | `effect_set_bd66_2` | 10 | verified | 4 setter cases + entry pin |
| `0x10328` | `effect_set_bd66_3` | 10 | verified | 4 setter cases + entry pin |
| `0x10332` | `effect_set_bd66_4` | 10 | verified | 4 setter cases + entry pin |
| `0x1033c` | `effect_set_bd66_5` | 10 | verified | 4 setter cases + entry pin |
| `0x10346` | `effect_set_bbbe_05ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10350` | `effect_set_bd68_1` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10360` | `effect_set_bd68_2` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10370` | `effect_set_bd68_3` | 16 | verified | 4 cases, both destinations seeded independently, + entry pin |
| `0x10380` | `effect_set_bbc0_05ff` | 10 | verified | 4 setter cases + entry pin |
| `0x1038a` | `effect_set_bbc6_01ff` | 10 | verified | 4 setter cases + entry pin |
| `0x10394` | `effect_push_record_0605` | 18 | verified | 4 write-pointer cases: the reset value, mid-list, one that makes the record land ON the pointer's own high word, and one far outside the list. Hand-seeded attribution instead of the poison pass — see below |
| `0x103a6` | `effect_push_record_0508` | 18 | verified | Same battery as `0x10394`, with the record `$0508` |
| `0x103b8` | `effect_push_record_0705` | 18 | verified | Same battery as `0x10394`, with the record `$0705` |
| `0x103ca` | `effect_push_record_0803` | 18 | verified | Same battery as `0x10394`, with the record `$0803` |
| `0x103dc` | `effect_restore_b6fa_to_max` | 12 | verified | 4 cases, including a maximum BELOW the counter (which this routine LOWERS it to, unlike the two clamped adds) + entry pin |
| `0xb372` | `select_table_21e8c_and_tick_b39a` (`src/hud.c`) | 40 | verified | 12 cases: 4 flag words (including two whose LOW byte is zero, so a port that read a byte fails on one of them) x 3 tick seeds including the wrap, each asserting the published pointer and the ticked word, with the pointer pre-seeded to the other table + entry pin |
| `0xb410` | `hud_blit_record_bitmap` | 52 | verified | 22 cases: 8 selectors (the four handlers' own 5..8, plus $00, the $20 whose product SIGN-EXTENDS below the table, the largest that still fits a word and the $40 that overflows it back to entry 0) x 2 screen buffers, each comparing all 32 rows against the game's own bitmap; plus 3 entry `d0`s x 2 record addresses, since `move.b` leaves d0's high byte alive and a0 is the only thing that says where the record is + entry pin |
| `0xb562` | `bcd_add_counter_bd6e` | 32 | verified | 10 cases: 6 valid-BCD (nibble carry, byte carry, the four-digit wrap, the $4e56 call site's own +5 with a high word the `.w` staging must drop), 3 non-digit nibbles pinned against the oracle alone, and the 0 + 0 that holds the entry extend bit + entry pin |
| `0xb582` | `bcd_sub_counter_bd6e` | 32 | verified | 9 cases: 6 valid-BCD (nibble borrow, byte borrow, the wrap through zero) and 3 non-digit nibbles + entry pin |
| `0xb5a2` | `bcd_add_score_bd70` | 36 | verified | 9 cases: 6 valid-BCD over eight digits (both live call sites' addends, a carry across three bytes, the full wrap, every digit pair carrying at once) and 3 non-digit nibbles. Also the routine the oracle's entry-CCR regression case runs + entry pin |
| `0xb5c6` | `bcd_sub_score_bd70` | 36 | verified | 7 cases: 4 valid-BCD and 3 non-digit nibbles. **Dead as shipped** — no reference anywhere in the image + entry pin |
| `0xb6c2` | `hud_blit_meter_cell` | 34 | verified | 40 cases: the 5 cell bitmaps `$b61e` passes x 4 entries of the offset table (including odd ones) x both of the game's screen buffers, since this one takes its destination out of `screen_back` too; each comparing all 32 plane bytes, bounding the write set to one byte per plane so the bytes between them are proved untouched, and comparing the ADVANCED cursor against both the oracle's `a1` and the reconstruction's return value + entry pin |
| `0xb6fe` | `hud_meter_add_clamped` | 36 | verified | 20 cases: a 5-point boundary sweep x 3 amounts carrying garbage above their low word, plus the 5 out-of-range cases that make the compare's SIGNEDNESS and the 16-bit wrap observable. Its `ble` clamps where the effect handlers' `bgt` stores; the strictness is unobservable either way (see below) + entry pin |
| `0xbb8a` | `hud_blit_cell_copy` | 22 | verified | 8 cases: `$b8f0`'s own blank tile and three of its icons x 2 of its own destinations, all 14 rows compared against the game's data over a seeded destination + entry pin |
| `0xbba0` | `hud_blit_cell_or` | 30 | verified | The same 8 cases, with the expected row stated as `seed OR source` — plus a guard that the seeds actually overlap an icon, without which every case would agree with a plain copy + entry pin |
| `0xbcd6` | `hud_blit_panel_frame` | 80 | verified | 8 cases: 4 of the indices `$bbca` produces (its reset, 1, the $a it stamps and the $c it wraps at) x 2 screen buffers, all 32 rows compared + entry pin |
| `0xb54c` | `hud_draw_counter_bd6e` | 22 | verified | 13 cases: 5 counter fields x 2 screen buffers (so nothing about the destination is hardcoded), plus 3 entry `d7`s over one field — `move.w`/`swap` bury the caller's high word BELOW the four digits, and all three must draw the same thing + entry pin |
| `0xb5ea` | `hud_draw_four_digits` | 52 | verified | 15 cases: 6 fields (all-zero, a lone significant digit, zeros on both sides of one, no suppression at all, all-nines, and nibbles above 9) x 2 cursors, plus 2 that enter with the caller's `d0` set either way (the `moveq` must make them agree) and 1 that enters with the latch already raised + entry pin |
| `0xb61e` | `hud_draw_meter` | 164 | verified | 20 cases: 10 (value, maximum) pairs x 2 screen buffers, each asserting the restore flag, every cell drawn and its position in `meter_cell_offsets`. The pairs reach all five cell bitmaps, every remainder 0..3, an empty meter, a full one and the 10-cell maximum; a case-level guard fails a sweep that stopped reaching one of the five + entry pin |
| `0xb74a` | `hud_draw_score_and_size_meter` | 124 | verified | 17 cases: a 13-point threshold sweep (both sides of all five steps, plus `$0`, `$7fffffff` and the `$99999999` that reads NEGATIVE and matches none), each also comparing the eight digits, plus 2 screen buffers x 2 fonts. A guard fails a sweep that stopped reaching a step or the no-match arm + entry pin |
| `0xb7c6` | `hud_draw_larger_score` | 36 | verified | 10 cases: 6 (score, high score) pairs — either ahead, equal, both signed-negative forms and the `$80000000`/`$7fffffff` boundary — plus 2 screen buffers x 2 fonts + entry pin |
| `0xb7ea` | `hud_draw_eight_digits` | 100 | verified | 14 cases: 6 fields x 2 fonts (only the FIRST digit takes the caller's `d0`, which is what the sweep separates) plus 2 cursors + entry pin |
| `0xb850` | `hud_plot_digit` | 160 | verified | 45 cases: all 16 nibbles x 2 fonts over a raised latch, 2 cursors (one even, one ODD) x 2 fonts, the two suppressed-zero forms, the two that raise the latch, and 5 entry `d0`s that pin the `cmpi.w` on d0's low word. Each compares all 32 plane bytes, bounds the write set to one byte per plane, and compares the advanced cursor against both the oracle's `a0` and the reconstruction's return value + entry pin |
| `0xbd32` | `hud_draw_stage_number` | 24 | verified | 13 cases: 5 stage words x 2 fonts (the `swap`/`rol.l #8` must select the LOW byte — `$ff99` draws 9 and 9, not f and f), plus 3 entry `d7`s + entry pin |
| `0xbd4a` | `hud_draw_two_digits` | 28 | verified | 8 cases: 4 fields x 2 fonts, including the all-zero field that draws TWO blanks — the case only this walk can produce, since it is the one that never forces the latch + entry pin |
| `0xb39c` | `hud_draw_newest_record` | 62 | verified | 10 cases: 8 (list word, fresh flag, record) combinations reaching all four arms — the reset `$ffff`, the `$8000` that shows the empty test is SIGNED, the `$0000` that is NOT empty, fresh-with-digits, fresh-with-the-`$ff`-sentinel and neither arm — plus 2 screen buffers. Each asserts all 32 bitmap rows against the game's own data, the restore flag raised only on the bitmap arm, and the latch word untouched when the sentinel screens the digits out + entry pin |
| `0xb3da` | `hud_draw_record_digits` | 54 | verified | 18 cases: 6 record low bytes (a blanked leading zero, a forced trailing one, nibbles above 9, and the `$ff` its caller screens out) x 2 screen buffers, plus 3 entry (`d0`, `d7`) pairs that must not reach the digits and 3 record addresses + entry pin |
| `0xb8f0` | `hud_refresh_dirty_slots` | 666 | verified | 52 cases: 5 slots x 3 value bytes x 2 screen buffers for the two-way arm, the sixth slot's 8 values (its six chain arms, the zero arm and the fall-through that leaves the cell blanked) x 2 buffers, 3 request bytes, all six dirty at once x 2 buffers, and a pass with none dirty that must write nothing. Each asserts `blank OR icon` over all 14 rows, the restore flag raised and the request byte cleared + entry pin |
| `0xd93a` | `panel_restore_dirty_regions` | 446 | verified | 18 cases: each of the 15 flags raised ALONE (so a walk that restored a neighbour's region fails on the stray write), all 15 raised x 2 screen orders, and none raised. Every case seeds both screen pointers and runs the pair both ways round + entry pin |
| `0x75fc` | `bg_scroll_serve_right` (`src/scroll.c`) | 16 | verified | 3 cases: the step moves and the fill runs, the step only arms the latch and the fill STILL runs, and the step at the scroll's limit consumes the `bsr` so the pass writes exactly one byte. Each compares the whole write set for EQUALITY against a model of the step followed by the fill ON ITS OUTPUT + whole-body entry pin built from the two callees' addresses in `../names.txt` |
| `0x760c` | `bg_scroll_serve_left` | 16 | verified | The same 3 cases mirrored |
| `0x79d2` | `bg_scroll_step_right` | 106 | verified | 8 cases: both sides of the limit test, three latch words (armed / disarmed / a small POSITIVE one, which the two directions treat differently), and three phase/cell carries — mid-cell, a carry into the next cell, and one that wraps `bg_scroll_x` and zeroes the row offset. Every case reads the skip decision off the ORACLE's own rewritten return address and requires the reconstruction's flag to match + whole-body entry pin |
| `0x795e` | `bg_scroll_step_left` | 116 | verified | 9 cases: the same shape mirrored, plus a fourth borrow case that pins the `andi.w #$7f` this direction applies to `bg_scroll_row_byte_offset` and the right step does not |
| `0x7c08` | `bg_scroll_fill_right_column` | 678 | verified | 13 cases over the three words that place the column: four phases (including 0, where the mask clears the whole cell and the rotation becomes a whole 16 with the map cursor pulled back), three `bg_scroll_x` (including 1, where the second cell leaves the 128-byte row), and four coarse rows (0 = no second half, 1 = a one-tile-row second half, 10, and mid). Each compares the write set for EQUALITY against a Python model of the fill and every written byte against that model's value; the destination is seeded address-keyed over the whole $5800 buffer plus a scanline either side + whole-body entry pin |
| `0x7eb2` | `bg_scroll_fill_left_column` | 658 | verified | The same 13 cases mirrored, which pin the four differences: no `bg_scroll_x` bias, the map column fifteen cells to the left, the mask INVERTED while the phase is nonzero, and the two halves of the rotated longword swapped over + whole-body entry pin |
| `0x761c` | `bg_scroll_step_up` | 414 | verified | 8 cases x both directions: mid-ring; each ring cursor parked on each direction's wrap ROW alone (four seeds, which under the two directions give all four one-cursor-at-a-time combinations AND pin that a step ignores the wrap row it is not walking towards); one cursor on EACH wrap row, which no direction wraps both of; a coarse-row republish; and the position boundary that consumes TWO calls. Each compares the write set for equality against a model of both cursors, reads the skip off the oracle's rewritten return address (and requires it to be sentinel + 8, not + 4), and a further case asserts all sixteen `bg_scroll_buffer_rows` pointers against `buffer + row * 128` after a wrap in each direction + whole-body entry pin |
| `0x77ba` | `bg_scroll_step_down` | 420 | verified | The same battery mirrored, which pins the two places the pair are not mirror images: the boundary is `bg_scroll_limit_y` rather than zero, and the wrap test is `cmpi.w #$ae` where the up step's is `tst.w` |
| `0x7a3e` | `bg_scroll_fill_top_row` | 220 | verified | 6 cases: three `bg_scroll_tile_row` (mid-tile, 0 — where the step-BACK wraps and pulls the map cursor a row up — and the last pair) x three `bg_scroll_x` (0, whose second count is -1 = no second half; 1, whose second count is exactly 0; and 15). Each compares the write set for equality against a Python model, asserts the returned `d0` against BOTH the reconstruction's and the oracle's, and a seventh case asserts the fill touched exactly one scanline PAIR of one buffer + whole-body entry pin |
| `0x7b1a` | `bg_scroll_fill_bottom_row` | 238 | verified | The same 6 cases mirrored, pinning the four differences: the other row pointer, the map row ten strides further down, the tile-row step AFTER the draw rather than before it, and the `$ffff` marker it returns where the top fill returns 0 |
| `0x8144` | `bg_scroll_preshift_rows` | 228 | verified | 6 entry `d0`s: the two markers, both of them again under a tile offset in the HIGH half (which `tst.w` must not see), and the two words either side of the sign boundary. Each compares the write set for equality against a model of 7 copies x 2 rows x 16 cells, and asserts the walk started at copy 1 and ended at copy 7. Two more cases pin the ring: the extent of what it wrote, and that cell 0's rotated-out bits are parked in `bg_scroll_preshift_carry` and ORed into cell 15 + whole-body entry pin |
| `0x75d4` | `bg_scroll_serve_up` | 20 | verified | 2 cases: the step moves and both the fill and the pre-shift run, and the step at the boundary consumes BOTH calls so the pass writes exactly one byte — the request it consumed. Write set compared for equality against the composed model + whole-body entry pin built from the three callees' addresses in `../names.txt` |
| `0x75e8` | `bg_scroll_serve_down` | 20 | verified | The same 2 cases mirrored |
| `0x759a` | `bg_scroll_serve_requests` | 58 | verified | 6 cases: each direction raised alone, all four at once (which is what pins the ORDER — up, down, right, left — since each handler runs on the state the previous one left), and a pass with nothing raised that must write nothing at all. Each compares the whole write set for equality against the four sub-models composed in that order + whole-body entry pin |
| `0xd28` | `bg_scroll_raise_requests` | 78 | verified | 7 positions: centred (raising nothing), off-centre both ways on both axes, one pixel either side of the vertical centre, the origin, and `$8000` — the one position where the `subi.w`/`bgt` pair's OVERFLOW flag makes the branch disagree with the sign of the difference. Each states the distance the case expects, and compares the oracle's whole `d0`/`d1` against it, high halves included (they are the caller's and must survive) + whole-body entry pin |
| `0x7522` | `bg_scroll_run_queue` | 112 | verified | 5 cases: the `scroll_follow_frozen` gate both with a request already raised and with none, a centred position that raises nothing, and one- and two-step drains on both axes at once. Each compares the whole write set for equality against a model that raises, halves, drains and clears — running the dispatch pass as many times as the queue owes + whole-body entry pin, whose two `bra.s` loop-closing displacements come out of the geometry |
| `0x82f8` | `bg_scroll_blit` (`src/scroll.c`) | 110 | verified | 12 cases: 8 over the three position words (both phases at the ends of the eight buffers, four columns including the two that need no source-row wrap and the two that do, and five ring rows — 0, just below the wrap boundary, exactly ON it, one past it, mid-ring and the last row a vertical step can produce) x both screen buffers x a case that states the write set as the 240x160 window rather than as whatever the model produced, x one out-of-range ring row that separates the `bpl`'s wrapped-sign reading from a boundary comparison. Each compares the whole write set for EQUALITY against a Python model of the dispatcher and the variant together, and a further 8 assert the copy never read outside the buffer the phase named + whole-body entry pin |
| `0x83b6` | `bg_scroll_copy_x0` … `0x8d58` `bg_scroll_copy_x15` | 16 x 154/166 | verified | ONE legend for sixteen regular variants. Each is entered AT its own address with the four registers the dispatcher hands over (a0/a1/d7/d6) and copies four scanlines to the source buffer's end plus two past the `lea -$5800(a0),a0` rewind, its whole write set compared for equality against the model; four more are run with the "no second half" marker so the rewind never happens, and one asserts the rewind lands on the buffer's own first scanline. Each variant's WHOLE body is pinned against the image, assembled from one pattern parametrised by the column — and three of them (`x0`, `x2`, `x15`) are pinned a second time against bytes transcribed straight out of `../out/wonderboy_dis.txt`, so the pattern itself cannot be what is wrong. The jump table, the sixteen lengths and the gaps between them are pinned as well: the family tiles `$83b6..$8dfe` exactly |
| `0xdaf8` | `panel_restore_44x8` | 26 | verified | 4 cases: its 2 regions x 2 screen orders, all 8 rows of 44 bytes compared against the source screen + entry pin |
| `0xdb12` | `panel_restore_32x20` | 34 | verified | 2 cases: its one region x 2 screen orders, all 20 rows + entry pin |
| `0xdb34` | `panel_restore_none` | 2 | verified | 1 case: a bare `rts`, run over a band seeded the width of the WIDEST restore on both screens, which must be left untouched + entry pin |
| `0xdb36` | `panel_restore_32x29` | 34 | verified | 2 cases: its one region (the record bitmap's own origin, 29 rows where the bitmap draws 32) x 2 screen orders + entry pin |
| `0xdb58` | `panel_restore_16x14` | 26 | verified | 12 cases: its 6 regions — one per HUD slot, in the HUD-slot cell's own geometry — x 2 screen orders + entry pin |
| `0xdb72` | `panel_restore_24x32` | 62 | verified | 2 cases: its one region (the panel frame's origin and geometry) x 2 screen orders, all 32 rows + entry pin |
| `0x67e0` | `followed_actor_record` (`src/actor.c`) | 24 | verified | 5 flag words: the `$0000` and `$ffff` the image writes, plus `$0001`, `$7fff` and `$8000`. It writes NO memory, so its a1 is the whole surface — compared against the record the case names AND against the reconstruction's return value, with a case-level guard that nothing was written. The two small positives are what separate its `bne` from `project_actor_list`'s `bpl` on the same word + whole-body entry pin |
| `0x67c2` | `actor_set_side_flag` | 30 | verified | 37 cases: 9 (followed x, actor x) pairs — both sides, equal, one apart either way, both negative, and both signed boundaries — x 4 flag-byte seeds (bit 3 already raised, already clear, and both with every neighbouring bit set, which a byte-wide `bset`/`bclr` must leave alone). Plus one against the a32 record, seeded so a port that hardcoded the other one answers the other way + whole-body entry pin |
| `0x67f8` | `actor_followed_x_within` | 42 | verified | 27 cases: 13 (followed x, actor x, reach) triples — both arms of the `bgt`, both sides of each arm's boundary and the boundary itself, a zero reach, both actors negative, one either side of zero, and the two where the 16-bit ADD WRAPS out of the positive half (which an unbounded model answers the other way round on) — x 2 entry `d0` high halves, since only the low word is written. Plus one against the a32 record + whole-body entry pin |
| `0x8dfe` | `project_followed_actor` | 104 | verified | 13 cases: 11 over the state the body reads — both records, the small-positive `$a32` its callee's `bne` picks and a `bpl` would not, the positive `$a30` its own `bpl` runs on and a `bne` would not, all four combinations of the flicker bit and the frame toggle, and positions that wrap both subtractions — plus 2 negative `$a30`s that must write NOTHING at all. Each states the write set exactly (the six bytes of screen record 12) and asserts the oracle's a0/a1 against the model + whole-body entry pin |
| `0x8e66` | `project_actor_list` | 156 | verified | 17 cases: 7 (`$a30`, `$a32`) pairs reaching all three tables — including the sign boundary of each flag and the small positive `$a32` that separates this pass's `bpl` from `$67e0`'s `bne` — x 2 frame toggles, plus a stale published pointer the pass must ignore, a write set stated as the GEOMETRY (nineteen six-byte records back to back plus the published longword), and a guard that the address-keyed seed still arms the flicker bit on some records and not others + whole-body entry pin |
| `0xbf5e` | `text_plot_glyph` (`src/text.c`) | 210 | verified | 31 cases: 5 glyph sources (both ends of the frame-glyph run, two of the font's own, and the all-zero space) x 6 cursors (the buffer's first cell and its odd twin, a mid-buffer pair, and the last full text row's pair), each stating the 32 written bytes exactly and comparing the returned cursor against both the oracle's a1 and the reconstruction's. Plus a four-step cell walk that shows the +1/+7 alternation lands two plane groups on + whole-body entry pin |
| `0xbf4e` | `text_plot_char` | 16 | verified | 14 cases: 7 character codes x 2 cursors. The codes are the space the table starts at, two ordinary glyphs, the largest byte, one BELOW the first char (where the byte subtraction wraps), and two carrying rubbish in d0's high half — one harmless, one whose shifted low word is negative and indexes below the font. Each compares the indexed source against the oracle's a0 as well as the plotted bytes + whole-body entry pin |
| `0xbd8a` | `text_run_message_box` | 452 | verified | 38 differential cases over the ten state bytes: an idle frame that must write NOTHING, 2 dismiss requests, 24 composes (6 shipped messages — the minimum height, the other top line, the maximum height and line count, the shortest string, the one whose line overruns the frame, and the table's last entry — x 4 lifetime phases, including the two the shipped data cannot produce), a compose that beats an already-active box, 8 blits (4 countdown phases x the table's two extreme geometries), a blit into the other screen buffer and one at a top line whose scanline offset SIGN-EXTENDS. Each states the write set exactly — the whole 6400-byte buffer plus the latched fields, or the blitted rectangle plus the countdown — against a model built from `_model_plot` and the game's own message records. Plus 4 structural pins on the $a09c table (self-bounding three ways), one that the seven state fields tile the band, one on the geometry constants' identities + whole-body entry pin |
| `0x1f36` | `actor_table_reset` (`src/actor.c`) | 30 | verified | 3 cases: one per actor table, each seeded address-keyed across all three back to back so a walk that overran one lands in the next. Every case states the write set EXACTLY — nineteen records of the marker word plus thirty zero bytes — and asserts the a0 the original walks out with |
| `0xdf9e` | `actor_slots_mark_free` | 14 | verified | 13 cases: 4 `dbf` counts (0, 1, 5 and the whole table) x 3 starting slots, each stating the write set as marker words ONLY — the whole difference between this routine and the reset above — plus one entering with rubbish in d7's high half, which a `dbf` must not see |
| `0x1b68` | `actor_alloc_slot_low` | 38 | verified | Shares a battery with `0x1b8e`: each free slot of the pool taken alone (9 + 6 cases), several free at once, a full pool, every slot OUTSIDE the pool free at once, the followed slot free alone, and 2 tables x each pool published through `actor_table_selected` while the other two hold no free record. It writes no memory, so a1 is the whole surface — compared against the case's own answer AND the reconstruction's return + entry pin |
| `0x1b8e` | `actor_alloc_slot_high` | 38 | verified | The same battery, and the pin is built from ONE `_alloc_entry(first, slots)` — the two bodies are byte-identical bar two operand words, which is what lets `src/actor.c` have one function behind both names |
| `0xffe4` | `actor_spawn_from_template` | 134 | verified | 22 cases: the 5 types that carry their own footprint (all five `cmp.w` arms) and 6 that take it from `actor_size_table` — including the two either side of the $36..$38 run, so a compare written as a RANGE fails — plus the type whose `lsl.w #2` index WRAPS at $4000, 3 template slots, a template BELOW the published pointer (the `asr.l` is signed and only its low byte is stored) and 3 destination records. Each states the write set exactly against a model built from the seeded template + entry pin |
| `0x2af2` | `actor_start_motion_at_speed` | 24 | verified | 20 cases: 4 flag seeds — the supported bit already raised, already clear, and both with every NEIGHBOURING bit set, which a byte-wide `bset`/`bclr` must leave alone — x 5 speeds including one carrying rubbish above its low byte + entry pin |
| `0x14d6` | `actor_accelerate_fall` | 32 | verified | 24 cases: the same 4 flag seeds x 6 speeds — both sides of the `cmpi.b #$8`, the value itself, one ABOVE it (which keeps climbing, since the test is an equality and not a ceiling) and the $ff that wraps to 0. Each also asserts the pre-increment byte the original leaves in d0 + entry pin |
| `0x10a2` | `actor_step_left_against_map` (`src/map.c`) | 206 | verified | 20 cases over a seeded collision map: 5 walks (clear, blocked then clear, blocked across two cells, a zero step, and a block the actor cannot back out of, which runs the step down to an EXACT zero and commits a move of nothing), the probe that goes off the map's left edge, the player-only byte clear on a retry and a record type that must not get it, all 7 arms of the ground test, the ASYMMETRY case (the cell looked up in one map and the ground stepped by the other's stride), 2 step high halves, a column above $ff and a row product above $ffff — the two cases that show d0 and d1 are each a partial write over something else + whole-body entry pin |
| `0x1400` | `actor_settle_on_platform` | 146 | verified | 17 cases: 4 footprint scans reaching the platform at 0, 1 and 2 cells along and through the sub-cell test, its refusal one pixel short, a 5-point sweep of the landing band (both ends and both sides of each, plus the band itself), a platform word whose `subi.w` WRAPS, 3 flag seeds over the unsupported arm, a span whose HIGH half must not reach either word operation that reads it, and both readings of a negative span — one that must not enter the scan and one that must still reach the sub-cell test + whole-body entry pin |
| `0x1af0` | `map_stamp_block` | 86 | verified | 11 cases: 4 map cells (including an odd one) x both tile sets, each asserting the four bytes are the consecutive run `src/map.c` writes; plus a variant word whose LOW byte alone matches (the test is a word), a cell offset that SIGN-EXTENDS below the map's base, and a row stride whose top bit is set, which puts the block's second row above its first + whole-body entry pin |
| `0x13be` | `actor_map_cell_from_actor_x` | 10 | verified | 5 cases: 4 left edges — inside the map, on a cell boundary, one that goes past the origin and one whose `sub.w` WRAPS the word — plus a case that seeds rubbish above every register and requires d0/d1 to come back CLEARED (the `move.l`) while d2 and d7 keep theirs. Its pin ends at the FALL-THROUGH rather than at an `rts`, and a case asserts that: $13be + 10 == $13c8, with no `rts` in the ten bytes + whole-body entry pin |
| `0x13c8` | `actor_map_cell_lookup` | 56 | verified | 18 cases, every one of them comparing SIX registers three ways — the oracle's, a Python model's and the reconstruction's `map_cell_probe` fields: both maps selected with their strides seeded apart, a negative column and a negative row (the arithmetic shifts), a row multiplied UNSIGNED as $ffff, a product past $ffff whose high half a wrapping column add must not carry into, an index of $8000 that addresses BELOW the map, entry high halves in d0/d1/d2/d7 that must survive against a d3 the `mulu.w` must wipe, 6 sub-cell values and 5 spans including one whose doubling wraps. Plus a whole-image `bsr` scan: exactly three callers, and which entry each takes + whole-body entry pin |
| `0x1170` | `actor_step_right_against_map` | 152 | verified | 32 cases: 5 walks mirroring `$10a2`'s (clear, blocked then clear, blocked across two cells, a zero step, and a block it cannot back out of), the player-only byte clear and a type that must not get it, 8 about the CLAMP alone (the park, the literal-`$0` byte over a `d6` that still says CLEAR, the A32/default limit pair, a `bge` boundary triple, the signed compare a wrapped probe reads, and a bias add that wraps the word), 3 that separate what d0's low word carries per exit (the limit, the column, the parked x), 4 of the shared tail entered from this body including the ASYMMETRY case, 2 step high halves, the entry high halves, and the probe row on a cell boundary — the mutation sweep's finding, and the one case that pins `subq.w #1,d1` for BOTH probes. Plus 3 whole-image scans (41 `bsr` callers and no `jsr`, the three `bra`s into `$10a2`'s tail with no `rts` in this body, and `$83b2`'s three operand sites with the `$fb18` bias the limit was built with). Every case states all seven registers the original leaves against a model, not just the two the reconstruction owes + whole-body entry pin |
| `0x1492` | `actor_settle_on_tile_1_or_2` | 98 | verified | 16 cases: 7 footprint scans reaching the ground at 0, 1 and 2 cells along and through the sub-cell test, each in BOTH accepted tile codes (which is the `cmpi.b #$2,(a6)` a port carrying $1400's single test would fail), `$23` under the whole footprint refused, the landing arm's `andi.w #$fff0` on a mid-cell y, a flag seed asserting `9(a0)` is absent from the write set entirely, BOTH ways into the enclosed `actor_accelerate_fall` (the `blt.w` at $14c0 and the fall-through at $14d2), the terminal speed that leaves the byte unwritten, a negative span that must still reach the sub-cell test, a span high half and the entry high halves. Every case states the write set exactly and all fifteen reported registers against the model + a whole-body entry pin of 130 bytes, of which the enclosed 32 are asserted as `actor_accelerate_fall`'s own address, length and bytes (130 = 98 + 32) |
| `0x1334` | `actor_fall_and_settle` | 138 | verified | 17 cases, against a model that COMPOSES its five callees' models over one shared memory: the head's cell taken from the record's own x at its pre-step y (a different column AND row from the settles'), the type test, the three `clr.w`s each with its word seeded nonzero, the `tst.w $1516.l` early exit whose write set is the flag word ALONE, the same mode word off the tile, the moving-bit return that happens after the head has run, the step over 4 speeds including `$ff`, a 3-point sweep of `cmp.w d1,d0 / ble` (one short, exactly on, one past) told apart by the speed byte's value, the landed bit bypassing that test, the accelerate arm still running the platform scan, the second `bsr $13be` starting that scan over (asserted on a6), and the settle cells keyed to the MOVED y in a different row from the seeded one. Plus scans: 46 `bsr` callers and no other entrance, the closing `bra.w $1400` and exactly two `rts` of its own, both absolute encodings of all three globals it touches with the data spellings classified, and the two sites in the image that compare a map byte against `$33` |
| `0xfa30` | `bg_build_buffer` (`src/stage.c`) | 214 | verified | 10 cases over a map seeded at every cursor the routine's OWN arithmetic lands on: the indexed walk and the RAW one (which skips the index table, so the same bytes name different tiles), 4 start cells, a start row whose WORD index SIGN-EXTENDS below the map, a tile whose `number * 128` does not fit a word (the `lsl.l`/long index), a stride BELOW the 16 columns just walked — where `subi.w`/`adda.l` advance the cursor ~64 KB instead of stepping it back — and a stride of exactly 16, where all eleven rows read the same cells. Each states the write set as copy 0 EXACTLY and compares all 22,528 bytes against a model + whole-body entry pin |
| `0xfb06` | `stage_publish_scroll_state` | 320 | verified | 9 cases: 4 map headers — one EXACTLY on `WB_BG_LIMIT_X_BIAS` / `_Y_BIAS` (both limits land on zero, which a clamping port also produces) and one a cell BELOW each, where the limits wrap to `$fff0` and a clamping port does not — then 4 start cells, then the `st`/`clr.w` pair that shows a Scc writes ONE byte. Every case seeds `WB_MAP_ROW_STRIDE` APART from the header's own width — the cursor reads the global and the limits read the header, and while the two shared an address a mutation swapping them survived. States the write set exactly and derives all sixteen row pointers from `WB_BG_BUFFER_ROWS`' invariant; a structural case requires the SHIPPED instruction bytes to spell those same sixteen + whole-body entry pin |
| `0xfd46` | `bg_build_preshifted_copies` | 198 | verified | 3 cases, each seeding all eight buffers address-keyed and comparing 157,696 derived bytes against a model that walks the same 7 x 176 scanlines: the chain (a0/a1 never reloaded, so pass n reads copy n and writes copy n+1), the RING each 128-byte row closes through `WB_BG_BUILD_CARRY`, and the carry band as the only write outside the buffers + whole-body entry pin |
| `0xfe1e` | `resource_table_relocate` | 44 | verified | 5 cases: the relocation itself (each record's leading offset plus the table's own base), a stamped signature that must write NOTHING at all, and 3 `dbf` counts including 0 — which relocates ONE record, since no value of the word can make the walk skip the first + whole-body entry pin |
| `0xfed2` | `stage_reset_state` | 112 | verified | 4 cases (2 salts plus 2 structural): the 18-byte block, the panel's four timer words with `WB_PANEL_FRAME_DELAY` seeded rather than cleared, `clr.l $1514.w` covering BOTH tile-33 words, the three mode flags and the scroll's follow gate, `actor_table_selected` back to the default table, and the eight `WB_TILE_INDEX_TAIL` entries — an OVERWRITE of the last eight of a table the .PRG ships no part of (`$21e90` is past the image and the whole 256 entries are loaded from disk), so what the disk holds there beforehand is unpinned. Every band seeded address-keyed WITH a margin either side + whole-body entry pin |
| `0xe16a` | `bg_plot_banner_glyph` | 48 | verified | 6 cases: 4 characters of the game's own second font x the two cursor parities, each stating the 32 written bytes exactly and comparing the advanced cursor THREE ways — model, the oracle's a1, and the reconstruction's return + whole-body entry pin |
| `0xe140` | `bg_plot_banner` | 42 | verified | 3 cases: both shipped records plotted glyph by glyph with the write set stated exactly, the a6 that comes back pointing AT the terminator (a `tst.b`/`bpl` does not consume it), and a registration case for the reading no shipped record can distinguish — see the batch-12 section + whole-body entry pin |
| `0xe110` | `bg_plot_round_banner` | 48 | verified | 5 cases: a meter exactly at its maximum (which scores `WB_BG_BANNER_BONUS` through `bcd_add_score_bd70` and plots the second banner) against 3 that are not, plus a structural read of the two `lea`s that name the records. Each separates the plotted bytes from the score's own band and requires the score to move if and only if the compare was an EQUALITY + whole-body entry pin |
| `0xff42` | `actor_spawn_pass` (`src/actor.c`) | 162 | verified | 20 cases against a model that REPLAYS the whole pass on a mutable copy (the record one spawn fills is no longer free when the next allocation looks): 4 gate values including the two that tell its `bne` from the `bpl` the projections read the same word with, the countdown walk running at capacity, a countdown byte that WRAPS rather than sticking, an EMPTY table (the terminator handled before it is tested — the sweep's mutation survivor), 3 cursor positions, the wrapped flag raised on the last record, a cursor past the sign boundary (`lsl.l #5` then a WORD-indexed `lea`, so it names a template 32 KB BELOW the table), 4 sweeps — none/three/all eight of the records ready, the last raising the live count to EXACTLY the maximum, plus one seeded to CROSS it mid-pass (the capacity test is read once, above both arms) against a pool of three free records that runs out partway, so the later spawns land on the vector page — the walk-before-sweep ordering, the published-table case, and 2 that pin the VECTOR-PAGE stamp + whole-body entry pin |
| `0x1006a` | `actor_template_set_hitpoints` | 48 | verified | 81 cases: 10 types x 8 kill counts, each keyed off `hitpoint_entry(type)` — the routine's own `add.w d1,d1 / adda.l` — rather than off the type, plus the table-adjacency pin that gives its 32 entries. The types cover the fixed-constant arm and both its neighbours, the last entry, one PAST it and two that wrap the word index; the kill counts cover both signs of the `asr.w #1`. Each asserts the stored word, the d0 the `moveq` leaves as a whole longword, and the d1 the table arm DOUBLES + whole-body entry pin |
| `0x2b5a` | `actor_hop_or_flip_side` | 40 | verified | Shares a 420-case grid with the two below: 4 flag seeds x 5 outcome bytes x 7 ground words x 3 routines. The outcome seeds include two whose LOW byte is zero under a nonzero register, which is the only thing that tells `tst.b` from `tst.w`. Each states the write set exactly, asserts a0/d1 unmoved, and asserts the d0 this routine alone clobbers — `move.w #$4,d0` writes the LOW WORD, so the caller's high half survives + whole-body entry pin, whose 40 bytes INCLUDE the tail at `$2b7a` |
| `0x2b82` | `actor_toggle_side_flag` | 12 | verified | The same grid. Its pin is 12 bytes where Ghidra records 20, and a case reads both short branch displacements out of the image and requires them to land on `$2b7a` — the tail Ghidra folded in + whole-body entry pin |
| `0x2b8e` | `actor_turn_and_launch` | 58 | verified | The same grid, plus a case stating that its inline three bits and speed byte ARE `actor_start_motion_at_speed`'s writes with a different literal — which is why `src/actor.c` spells them out rather than calling it. Ghidra has no function here at all + whole-body entry pin |
| `0xe80c` | `hud_draw_lives` (`src/hud.c`) | 112 | verified | 11 cases: 8 lives counts — 0 through 4, and $8000/$ffff/$7fff, where a `tst.w`/`bne` fills every slot and a sign test would blank them — each stating the write set exactly across BOTH screen buffers against a model that steps the two cursors as the routine does. Plus the geometry identities (4 + the row skip is one scanline; 16 rows less the rewind is one cell; the two destinations are the same offset into the two buffers) and a case that the shipped icon is not the blank pattern, without which the two arms would be indistinguishable + whole-body entry pin |
| `0xfe4a` | `game_restart_reset` (`src/stage.c`) | 66 | verified | 4 cases: the head's eleven words, and the fall-through — it sets `WB_LIVES` to 3 BEFORE the tail draws them, so however many lives a case seeds the display comes out at three. Its write set CONTAINS `hud_draw_lives`', modelled once in `test_hud.py` and imported + whole-body entry pin |
| `0xfe8c` | `game_life_restart_reset` | 70 | verified | 6 cases: 5 lives counts taken as they stand (its own caller at `$c00` has already decremented one), plus one that the record LIST's empty word is the head's alone while the write POINTER is reset by both. A structural case requires the two halves to be adjacent, to add back up to Ghidra's single 136, and the head to end in something other than an `rts` + whole-body entry pin |
| `0x9594` | `blit_sprite_w2` … `0x9774` `blit_sprite_w5` (`src/blit.c`) | 98/156/226/296 | verified | ONE battery for the whole family of twelve (`test/test_blit.py`, 154 cases): every case enters a blitter AT its jump-table address with the dispatcher's register file (a0 sprite cells, a1 screen, d6 shift, d7 rows, d4 x in a prelude) over seeded cell data, compares the WHOLE write set for equality against a Python model of the cell/seam walk, and asserts all fifteen reported registers plus the eleven the return struct carries — the register file is half the output here. A 192-combination sweep (4 widths x 3 clip cases x 16 shifts, each exactly once, rng only for x/y/rows), sharded in 6 chunks. The entry pins ASSEMBLE all 2,254 bytes from the battery's own statement of the geometry and require them to equal the shipped image; plus the tiling pin, the three jump tables, and a whole-image longword scan that each entry is named ONCE, in its own slot |
| `0x8fce` | `blit_clip_left_w2` … `0x936c` `blit_clip_left_w5` | 22/40/58/74 | verified | The same battery: every left-ladder arm at its threshold and beside it (thresholds −16k, masks `(1<<(columns−k))−1`), and the fully-off-screen arm's `subq.w #6,a5` — a 32-BIT subtract, pinned with a5 seeded four bytes into a high word so a word-wide subtract is caught. Only the LEFT ladders unwind |
| `0x8fe4` | `blit_clip_right_w2` … `0x93b6` `blit_clip_right_w5` | 168/266/372/478 | verified | The same battery: each right ladder's complete mask set (3,2 / 7,6,4 / $f,$e,$c,8 / $1f,$1e,$1c,$18,$10) and its off-screen arm returning having touched NOTHING; the shared clipped bodies both preludes branch into (one helper per width in `src/blit.c`); the w4 body's LATE `or.w d4,d3` merge reproduced and pinned from the skipping arms of BOTH ladders (pixels identical, d3 differs); and the two-column row-count guard from both exits ($ffff → beq, $fffe/$7fff → bmi) against the wider bodies' bare `dbf` |
| `0x8f02` | `sprite_draw_pass` (`src/blit.c`) | 204 | verified | Batch 15, ~75 cases in the same battery: differentials entering the pass over seeded records + descriptors + `screen_back`, write set = the UNION of the rectangles the walk drew against a model that walks a MUTABLE image (each record sees what the last one drew), all reported registers + the pass's own a6/a4/a2 through `sprite_pass_regs`, and the a5 unwind accumulated across a walk. Every clip class reached FROM the x/y arithmetic; the top clip's `muls`/`suba.l` source advance; the $9f band's both edges; the sign-extended `adda.w` descriptor-index wrap run BOTH directions from the LAST slot; a skipped record's cursor observed from slot 18 (the review's mutation-confirmed hole, closed); the negative-height handoff through the guarded width AND the 65,536-row runaway RUN, pointed one byte past the image (1.37 s, 4.65 M instructions, both sides dropping every write — what batch 14's `os_in_image` was for); the dead d5 write pinned through the off-screen arms; seeded-band disjointness asserted + 204-byte whole-body entry pin assembled from the battery's own statement of the walk |
| `0x17b14` | `snd_call_trigger_effect` (`src/sound.c`) | 14 | verified | Batch 16b, 14 cases: the register-preservation pin (all fifteen reported registers seeded distinctly and required back, WITH the effect's writes landing), 12 shipped ids through the stub, and a 7-entry pin on the stub TABLE's shape — six `movem` thunks and the 10-byte a3 push, each `bsr` displacement rebuilt from `../names.txt` |
| `0x1a48a` | `snd_trigger_effect` | 334 | verified | 123 cases: all 26 shipped ids on channel A, 12 call-site ids x channels B/C, 6 out-of-range ids (both sides of the sign extension) x 3 channels, 3 ids whose descriptor sits INSIDE the mix block (order), 2 whose descriptor sits inside the STATE band (the copy DIRECTION — a memmove reddens exactly these, over a keyed-seeded band, with the model SIMULATING the byte-by-byte copy), 5 seeded descriptors x 3 channels through a poked pointer-table entry, a d1 sweep over the third arm bracketing the last channel's own number, d0/d1 high-byte pins, table self-bounding + noise-arm coverage guards + entry pin over all three arms and the orphan `rts` |
| `0xbbca` | `panel_frame_timers` (`src/hud.c`) | 268 | verified | 41 cases: 19 timer seeds x 2 screen buffers reaching every arm and both sides of every test in the body (the rewind clamp signed and exact, the meter floor and its non-floored negative, the effect's SIGNED `bgt`, the index wrap at $c), each asserting the arm's exact write set, the frame it drew and the d0 it hands on; the effect-firing arm's writes asserted through `test_sound.py`'s own model (imported, not restated) + entry pin assembling the `jsr 56(a1)` from `entry_of("snd_stub_00")` — batch 16a's `$bca2` edge confirmed by construction |
| `0xb346` | `panel_refresh_frame` | 44 | verified | 11 cases: 3 animation arms x 2 screen-buffer pairs over the whole ten-callee tier (write set composed from the batteries that own each callee), the poked-frame case that reaches the alternate stage font through the LIVE d0 the blit's last `movem` leaves, the entry-register indifference case, and the call-list guard + entry pin. Attribution off for a stated reason: a composed pass's outputs are its later callees' inputs (the poisoned meter value would drive $b61e's 16k-blit runaway) |
| `0x69fe` | `actor_damage_followed` (`src/actor.c`) | 266 | verified | Batch 17, ~110 cases after the review trim: 7 mode-flag seeds pinning `tst.b` against the `tst.w` every other reader uses ($0001/$00ff answer the OTHER record), the invulnerable arm as a differential over an EMPTY write set with all entry registers required back, all four funnel arms by exact write set, the helmet-slot boundary both ways, a 10-point meter sweep incl. a negative carried back positive and STORED, one damage-table type per distinct shipped word (6) + 6 out-of-range types (the index is unsigned and LONGWORD: $4000 reads above the table, $8000 wraps to entry 0) + 7 seeded + the 4-case inline sign-bit arm, a 9x4 x-compare grid (inclusive where $67c2's is strict), per-arm register model via leaf.set_low_word. SFX writes asserted through `test_sound.py`'s model, imported |
| `0x6b46` | `actor_damage_template_hitpoints` | 114 | verified | Batch 17, ~90 cases: the three gauntlet arms (the doubling runs on BOTH that spend a charge — batch 13's read had it inverted), 12 list-byte seeds over the `addq.b` wrap, the pool/flags2 axes split per the measured trim (9 pool cases + the 4-seed axis on one killing and one surviving case), 6 template slots, both table pointers, and the registers incl. d1's entered high half over the CHANNEL-B selector — every case drives snd_trigger_effect's B arm from this caller's own registers, and a B-arm stride mutation reddens 39 of them plus test_sound's new id-19 case |
| `0xdbc0` | `scene_run_frame` (`src/scene.c`) | 932 | verified | Batch 19, the bulk of `test_scene.py`'s 183 cases: both mode gates (incl. the exclusivity row a fall-through port fails), the kind ladder pinned in bytes, the speech script (edge gating, cursor, terminator, lifetime-0 post), the whole shop (request ladder, signed price compare on packed BCD, first/repeat messages, dispatch through the 23-entry effect table — shipped AND seeded — the a1-clobber spend landing in effect_record_list for exactly the four push handlers), the boss-fragment arm, the two shipped vector-page slips reached by seeding the vector page, and the four exit tails each pinned by stop_pc + the kit's positive cov_visited witness (which transfer fired, one run) |
| `0x17f30` | `snd_psg_silence` (`src/sound.c`) | 82 | verified | Batch 21b, 22 cases: 7 mixer seeds (reaching all four states of the preserved direction bits) x 3 entrants of the stop chain, each comparing the ORDERED PSG access ledger — reads included — and the register file the run leaves, neither of which is in the image; plus the preserved-bits claim stated on its own, the d1 the read-back lands in as a BYTE and the d2 the saved SR lands in as a WORD, a seed declaring two registers the chain must NOT touch, and the case that declares NOTHING and requires the oracle to REFUSE the run — the guard every other one rests on + entry pin |
| `0x1aaea` | `snd_stop_all_sfx` | 26 | verified | The same sweep, plus the write set stated exactly: the three SFX-active flags AND the unnamed fourth byte (a `clr.l`), and the four snd_psg_shadow bytes that MIRROR the four chip accesses — which is what says the shadow is indexed by PSG register number and not the `$18360` mix block an earlier plate claimed |
| `0x17f24` | `snd_stop` | 12 | verified | The same sweep over the whole chain, plus the engine flag its own twelve bytes add. The three bodies are required to tile: `$17f24 + 12` is the tail's entry and the tail's 82 end where `snd_resume` begins |
| `0x6bb8` | `actor_defeat_and_score` (`src/actor.c`) | 164 | verified | Batch 21b, ~33 cases: 5 spawn types with distinct shipped scores, a 7-point kill-count sweep bracketing the limit on both sides AND across the sign (the compare is signed, and read back out of MEMORY), the unscored type `$26` and its two neighbours, 4 wrapped-flag values incl. the small positive one where its `tst.w` and `$ff42`'s `cmpi.w #$ffff` part company, 3 spawn types whose `lsl.w`-scaled score index WRAPS inside the word, the whole boss block (music stopped, flag raised, SFX fired, meter paid — each compared through the battery that owns the callee) and its gate's three failing halves, each requiring an EMPTY PSG ledger, plus the two flag words with a zero BYTE in them ($0100, $00ff) that separate its `tst.w` from a read of either half. The respawn exit is a `stop_pc` checkpoint at `$6cdc` with `leaf.run_reaching`'s witness that the `ble.w` fired; the `ble.w`'s own address is SEARCHED for in the assembled body rather than transcribed + 164-byte entry pin, which meets the score table's base *(batch 22: the checkpoint is GONE — the continuation is ported and every arm runs to the original's `rts`; the `run_reaching` witness stays)* |
| `0x68c6` | `rng_next` (`src/rng.c`) | 108 | verified | Batch 21b, 33 cases: 6 seeds per counter x 3 counters (rest, either side of the wrap, AT the limit — where a `% limit` reading diverges — past it, and the 16-bit wrap), all three stepping in one run, 6 frame ticks whose bits reach the whole word and make the three word adds wrap, 3 entry `d0` high halves the `clr.w` must leave alone, and the d1 the tick lands in. **The result is a DEGENERATE generator**: its `$ff8209` term is off-image and reads 0 on both sides, so a case states that explicitly and the whole battery is green about a PRNG with no randomness in it — a registered T3-DATA false green |
| `0xe1f0` | `stage_random_kind8` | 50 | verified | Batch 21b, 17 cases: 7 stage numbers spanning both sides of the packed-BCD ladder (incl. stage 0, which indexes row −1 and reads BELOW the table, and $8001, whose sign bit says the `cmp.w`/`ble` is SIGNED) and all 8 candidates of a row, reached by choosing the counters and tick whose sum lands on each; 3 entry `d2` high halves the `add.l` folds into the table INDEX, one that sends the read off the image entirely (served 0 on both sides, which is what pins `src/rng.c`'s guard), and two ACROSS THE 68000'S 24-BIT ADDRESS BUS — one past it, which wraps back round onto the very byte a `d2` of 0 reads, and one ON its top bit, which separates a 24-bit mask from a 23-bit one; the table's self-bounding extent and the mask every byte in it survives; and the sibling `$e1c8`'s `bra.w` INTO this routine's tail |
| `0xde80` | `scene_spend_visit_budget` | 58 | verified | The borrow (word subtract, sign = borrow), the marker cell's twin pair in order, the map stamp against a NONZERO keyed seed, and the stage-reset tail — through the DRIVER from all four spending arms (the review's four surviving mutants, killed) as well as directly |
| `0x6cdc` | `actor_respawn_as_new_kind` (`src/actor.c`) | 126 | verified | Batch 22, ~32 cases: the arm split at the kill limit pinned from kills {1, 2, 3} PLUS $0102 — the word-width case a `cmp.b` port passes and the `cmp.w` fails; both forced-kind fields, each run seeding the other field 0 so a field-swap mutant draws instead and fails; negative forced kinds through BOTH C entrances of the retire tail (the `bmi.w $6c38` at $6d0a is a THIRD entrance nothing had recorded); the index edges — row 21, row 22, a negative index, the word wrap at $1000 and $7fff — with the table read carrying NEITHER bus mask nor off-image guard because a case COMPUTES over all 32,768 kinds that the row window `[table-$8000, table+$7ff0]` never leaves the image; the nine field writes (ten offsets — the plate's "six" was a pre-port miscount) as an exact write set; entry-d2 forwarding pinned on BOTH draw arms — the review gate's one live-mutant hole, found empirically and closed; and the 126-byte entry pin, `bmi` target derived from the `ble.w` rather than transcribed |
| `0xe1c8` | `stage_random_kind32` (`src/rng.c`) | 40 | verified | Batch 22, inside `test_rng.py`'s parametrized draw section (the whole battery stands at 103): every draw claim re-made over this descriptor's own operands — the packed-BCD stage ladder, all 32 candidates of a row, the closing mask, and its ELEVEN-row table (half the sibling's 22) walking off its own end onto `stage_kind_table` on the game's shipped bytes; the shared fourteen-byte tail ($e214..$e221) now pinned from THIS side's `bra.w` as well; ONE static C body serves both draws (three parameters where the original changed three operands), which is why the d2/bus quartet stays on the DRAW8 side alone — the sibling's runs execute the identical instruction on the identical operand; entry pin started at $e1c8 exactly, where objdump misaligns |

### The .RAD depacker

The 216 bytes are the whole routine, `0x5d62..0x5e3a`, which `../names.txt` splits into three:
`rad_depack` plus the leaf helpers `rad_refill_bit_buffer` (`0x5e14`) and `rad_get_bits` (`0x5e20`).
The C folds the first into `rad_bit` — the original's inline `lsr.l #1,d0` and the refill it falls
into are paired at every call site — and keeps the second under its own name.

Four things about this row that a later reader should not have to re-derive — the register of every
way the port and the original are knowingly not the same:

* **The scratch long at `0x5e3a` is written by the test's glue, not by the port.** The original
  parks its CALLER's stack pointer there (`move.l a7,$5e3a.l`) to restore on the success path; a C
  port has no such register, so `g_rad_depack` takes the stack pointer the oracle entered with and
  writes it, and the byte-for-byte diff still covers the write. Nothing else in the image reads that
  long (`../names.txt`, `rad_saved_a7`), so the port owes it nothing else.
* **The failure path's 65536-iteration delay loop is not reproduced.** It is timing only, and this
  differential's surfaces are memory and `d0`; the oracle counts the instructions and nothing
  asserts on them. If a caller is ever found to depend on that stall, this is where it bites.
* **On the failure path the original does not restore `a7` either.** Only the success path reloads
  it (`movea.l $5e3a.l,a7`); the failure path falls through the delay loop straight to its `rts`.
  That is a REGISTER-level asymmetry, outside this differential's memory + `d0` surface, and the C
  port has no machine stack to reproduce it with. Already recorded in `../notes/rad_depacker.asm`'s
  header, `include/wonderboy.h`'s `WB_RAD_SAVED_SP` and `../names.txt`'s `rad_saved_a7` comment;
  noted here so the register of asymmetries is in one place.
* **Two deviations are latent rather than pinned**, both stated in `src/rad.c`'s file comment. The
  loop's end test is now the SIGNED compare the original's `cmpa.l a2,a1 / blt` is, but only a
  header with bit 31 set in a length can tell a signed test from an unsigned one, and no corpus
  stream has one — the form is faithful by reading, not by a case that went red then green, so that
  divergence class stays UNPINNED. And an access that leaves the mapped image diverges by
  construction: the kit's shim answers the read with zeros and drops the write, while the C indexes
  a host buffer and is undefined behaviour. Every corpus case keeps both buffers and every oracle
  write inside the image, so neither is reachable from this battery; bounding the C's accesses would
  be a kit change, not a port one, and was not made.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, since a same-second
rebuild otherwise re-runs the stale library): dropping the checksum branch reddens exactly the 5
cases that reach it (the 4 damaged files and the synthetic one), while an off-by-one in the match
source, a literal-run base of 8 instead of 9, a shortest-match length of 3 instead of 2, and
dropping the scratch-long write each redden all 46 cases that decode a stream.

### The first gameplay batch

31 leaves in two files: `src/input.c` (the two joystick routines, `0x682` and `0x88c`) and
`src/effects.c` (the 29 at `0x10200..0x103e7` — the six `set_state_*` stubs and the 23 handlers of
`effect_handler_table`). 434 bytes of code: 38 in the joystick pair and 396 in the 29 — whose
`$10200..$103e7` span is 488 bytes, the difference being `effect_handler_table`'s 23 longwords,
which sit inside the span between the stubs and the first handler. This is also the first *game
logic* the project has ported: no hardware, no OS, no callee, every one entered directly by its
case. `test/leaf.py` is the shared driver — it looks each entry point up in `../names.txt` rather
than restating an address, and requires the original's write set to stay inside the words the case
says it may touch.

**"4 setter cases" in the table above means**: the destination word is pre-set to `$0000`, `$ffff`,
`$1234` and `$a55a` in turn, the whole image is diffed, the kit's attribution (poison) pass runs on
top, and the write set is bounded to that one word. The `$ffff` seed matters because one routine
*writes* `$ffff`: on that case alone the plain diff proves nothing and the attribution pass is what
holds it. Every row also carries an **entry pin** — the bytes at the entry compared against the
instruction the battery reconstructs from the same address and immediate the C uses, so a wrong
constant fails at its own address instead of surfacing as a puzzling diff.

Six things a later reader should not have to re-derive:

* **The names are at the MECHANISM, and the batch did not change that.** `effect_set_bd66_3` says a
  3 goes into `$bd66`; what a 3 there means is still open. Reading the bodies *did* firm up the
  shapes, and `../names.txt` now carries them: `$bbbe..$bbc9` is six 2-byte HUD slots
  `{value, changed}` swept once a frame by `$b8f0`, so a handler's single `move.w #$Nff` means
  "value := N, redraw me"; `$b6fa`/`$b6f8` are the value and maximum of a meter drawn in four-unit
  cells by `$b61e`; `$b546` is a longword write pointer advanced *before* its store. The obvious
  readings (a vitality bar, an item inventory) are still **not** verified — no cell's graphics were
  followed to a meaning — and no name here asserts one.
* **One `# ctx` tag came off**, the cluster comment at `0x10200`. Reading the six bodies also
  corrected it: they are *not* "six 10-byte stubs". Five write `hud_slot_bbc8` through a long
  absolute operand at 10 bytes each, and `set_state_6f9c_ffff` uses a **short** one and is 8 — which
  is why `effect_handler_table` begins at `$1023a`. That was the only tagged line in the batch; the
  other six tagged lines in `../names.txt` are on names nothing here ports.
* **`$6f9c` has no reader among the recovered functions — but it does have one in the image.**
  `set_state_6f9c_ffff` is its only writer of the 252, and none of them reads it. Unrecovered code
  at `$6f84` does: `tst.w $6f9c.l / beq / clr.w $6f9c.l / move.w #$36,4(a0)`, i.e. it consumes the
  word as a ONE-SHOT flag — tests it, clears it (so `$6f8e` is a second writer, outside the
  recovered set) and stamps `$36` into an object field. That is more than the batch started with,
  and `../names.txt` now records it; what the `$36` selects is still unknown, so the name stays at
  the mechanism.
* **The record pushes run WITHOUT the poison pass, deliberately.** Their output includes the write
  pointer, and poisoning inverts an oracle-written byte — so the pass would hand the next store an
  odd (or off-image) address and take an address error instead of producing a case. The attribution
  it buys is done by hand: the destination word is seeded to the record's own complement, and the
  case asserts that before it runs, so a port that advanced the pointer without storing still
  diverges. `src/effects.c` also inherits the depacker's **off-image divergence class** through that
  same pointer (the oracle's shim drops a write past the image; the C indexes a host buffer, which
  is undefined behaviour) — every case seeds a pointer well inside the image, so the battery never
  enters it, and bounding it would be a kit change.
* **The clamp is signed and 16-bit, and only the tests reach the parts that show it.** The meter's
  own range is `$18..$28`, so nothing the game does distinguishes `bgt` from an unsigned compare or
  shows the `addq.w` wrapping — the five out-of-range cases per routine are synthetic on purpose,
  and they are the reason the port's `(int16_t)` casts are pinned rather than merely plausible. The
  batch's one genuinely unreachable-by-real-data note is that pair: `../names.txt` records it on
  `0x10296`.
* **The `bgt`'s STRICTNESS is faithful but unobservable, and that is an equivalence, not a coverage
  hole.** The original stores when the raise lands exactly on the maximum, and `src/effects.c`'s `>`
  reproduces it — but `>=` would store the same word on that very case, so the two implementations
  are indistinguishable through memory, `d0`, or anything else a differential can see. No seeding
  fixes this and none should be attempted: unlike the branches real data cannot reach (which better
  data *would* pin), there is nothing here to pin. What the boundary sweep does pin is the
  comparison's POSITION — a `> max+1` reddens at offset +1 and a `> max-2` at offset -1.

Two register-level asymmetries, outside the memory surface and so outside most of this battery:

* **`joy1_newly_pressed` returns in `d0`, and only its low byte is the answer** — every instruction
  is a `.b` op, so the caller's top 24 bits survive. `g_joy1_newly_pressed` takes the `d0` the
  oracle was entered with and reproduces the whole longword, which each case compares (the same
  shape as `g_rad_depack`'s entry stack pointer). No `proto` line was added for it: Ghidra already
  recovers `byte joy1_newly_pressed(void)`, which is correct, so the interface is recorded as a
  `cmt` instead. **`d1` is clobbered and nothing checks it.**
* **The two clamped adds leave their working value in `d0`**, and no case asserts on it. That is
  safe at both dispatch sites and checked, not assumed: `$ddec` and `$de62` each `jsr (a0)` into the
  handler and then execute `move.w #$3,d0` as their very next instruction, so a handler's `d0` is
  dead the moment it returns. It would only bite if a handler were ever called from somewhere else,
  and nothing in the image reaches these addresses except through `effect_handler_table`.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, since a same-second
rebuild otherwise re-runs the stale library — 312 green each time it was restored): a setter aimed at
the **wrong address** and a setter with the **wrong immediate** each redden exactly that routine's 4
cases; **dropping the clamp branch** reddens 8 (the clamping cases of both adds, and no others);
`and` → **`or`** in `joy1_newly_pressed` reddens 12 of its 21; writing a HUD slot's **value byte
only** reddens all 36 slot cases; and **storing before advancing** the record pointer reddens all 16
push cases. A seventh, comparing **unsigned** instead of signed, reddens 18 — the 8 out-of-range
cases as designed, and the whole boundary sweep as well, because the attribution pass inverts the
meter's own bytes and so drives every one of those runs negative too. 7 mutations, 0 survivors.

An eighth, `>` → **`>=`** in the clamp, **survives all 312** — and no seeding would change that. It
is the equivalence registered above, not a hole: at a raise landing exactly on the maximum both arms
store the same word, so the mutant IS the original as far as any observer goes. "0 survivors" above
therefore means *of the observable mutations*; a sweep that flips this comparison's strictness (or
any other semantically inert bit) will report a survivor that no case can or should kill.

### The status panel batch

Eleven leaves of `panel_refresh_frame` (`$b346`), the game loop's once-a-frame status pass, in one
file: `src/hud.c`, 430 bytes of code across `$b372..$bd26`. `$b346` itself is `jsr $d93a` plus nine
`bsr`s and an `rts`, and that call list — the record list's display, the four-digit counter, the
score, the high score, the meter, the six HUD slots, the panel animation, a text pass and the
table-select — is the evidence for treating this region as one subsystem rather than as eleven
unrelated addresses. `../names.txt` gained the whole region: the eleven names, `$b346` itself,
`$bf4e` (which is NOT ported — see below), and eleven globals.

**This batch is the first that is not "a `move` and an `rts`."** Three things follow, and they are
what the 169 cases are shaped by:

* **Nine of the eleven take REGISTERS**, which Ghidra recovered none of (`void FUN(void)` for all
  eleven). The interfaces are read off the disassembly and `../names.txt` now carries a `proto` line
  for each one the directive can express. `hud_blit_meter_cell` gets a `cmt` instead: it returns its
  result in `a1`, and `ApplyNames`' `proto` forces a void return, so a `proto` there would record
  something false. `test/leaf.py` gained `register_glue(name, argtypes, restype)` for this — the
  shape `image_glue` already had for the register-less ones — and a `max_insns` argument: the
  straight-line leaves run at most six instructions, so `leaf.LEAF_INSN_CAP` is 64, and a routine
  that blits 32 rows needs a cap stated from its own geometry instead (400 here).
* **Five of them DRAW**, and **three** take their destination from `screen_back` (`$750`), a
  longword in MEMORY — `hud_blit_record_bitmap`, `hud_blit_meter_cell` and `hud_blit_panel_frame`.
  So every one of their cases seeds it, and seeds it with BOTH of the game's own buffers, because a
  reconstruction that hardcoded `$70000` would otherwise pass. (The remaining two,
  `hud_blit_cell_copy` and `hud_blit_cell_or`, are handed an address their caller `$b8f0` already
  resolved, in `a1`; there is no `$750` read to pin.) The expected bytes come from the game's own
  bitmaps in the loaded image, so each case says WHICH bytes moved; the allowed write set is one
  entry per row, which is what pins the 160-byte scanline stride as a stray write rather than only
  as a diff. `src/hud.c` inherits `src/rad.c`'s **off-image divergence class** through that pointer,
  and one more besides: an address computed as `base + adda.w delta` wraps at 32 bits on a 68000 and
  does not on a host pointer, so every address in the file is built as a `uint32_t` first. That is
  not decoration — the `$20` selector case reddened until it was. It is now the kit's
  `addr_add(base, delta)` (`tools/recreate_kit/include/machine.h`), which `src/effects.c`'s record
  pointer uses too; it was a `static` in `src/hud.c` until the second caller appeared.
* **Four of them are packed-BCD accumulators** over the score (`$bd70`, eight digits) and the
  counter below it (`$bd6e`, four). Their expected value is stated in DECIMAL and converted back,
  which is a different statement from the nibble arithmetic in `src/hud.c` rather than a copy of it.
  Three cases per routine deliberately feed a nibble above 9, which is not BCD: the decimal model
  declines to predict those and the differential is their whole pin — worth stating, because the
  68000's manual leaves `abcd` on such an operand UNDEFINED, so those twelve cases hold the port to
  the ORACLE's model of it and not to hardware. The game cannot reach them (both fields start
  cleared and only ever see BCD constants).

Five things a later reader should not have to re-derive:

* **`$bf4e` was in the batch and was NOT ported then. It is not a leaf.** *(Batch 8 ported it, with
  `$bf5e`, as `text_plot_char` + `text_plot_glyph` — see "The actor tier and the text plotter"
  below. What follows is the reading that deferred it, and it was right about every part of the
  shape.)* The hardware scan calls it a
  16-byte T0 function with an empty callee set; its 16 bytes have no `rts`, and it FALLS THROUGH
  into `$bf5e`, a 210-byte unrolled glyph plotter with eight `bsr` callers of its own. A
  differential entered at `$bf4e` would execute 226 bytes and verify a routine outside this batch.
  It is named and its shape recorded in `../names.txt`; porting it means porting `$bf5e` with it.
  **Read this as a caveat on the scan, not on that one address**: "T0, no callees, N bytes" is a
  claim about the bytes Ghidra put in the function, and a fall-through target is invisible to it.
* **The disassembler in `../out/wonderboy_dis.txt` prints `abcd`/`sbcd` wrong.** `c308` and `8308`
  come out as `and.b d1,a0` and `or.b d1,a0`, which would make the four accumulators read as
  nonsense. Ghidra has them right (`bcdAdjust` and `in_XF` in `../decomp.c`), and so does the
  entry-byte pin, which is built from the opcodes. `tools/prg_dis.py` is unfixed; `../names.txt`
  records the trap on `$b562`.
* **The BCD routines' entry X flag is live input and is NOT pinned beyond X = 0.** `abcd` folds in
  the extend bit and nothing between the entry and the first one touches it. X = 0 is now the
  oracle's guaranteed entry condition (see "The oracle defect..." above) and one case holds the port
  to it — 0 + 0 comes out 1 if the port assumes otherwise — but the GAME reaches `$b5a2` with X = 1:
  `$e058` does `subq.w #1,hud_meter_value`, which sets X when the meter was already zero, and
  `$e064` calls it two instructions later. So a meter at zero scores one extra unit, and neither
  `emu.run` nor this battery can express that. Honestly unpinned, and the first reconstruction in
  this workspace whose entry condition is a CONDITION CODE rather than a register.
* **`hud_meter_add_clamped` is the general form of the two effect handlers and not the same
  comparison.** `$b6fe` does `add.w d0,$b6fa` — a read-modify-write on MEMORY, so the raised value
  is stored before anything is tested — and its `ble` clamps where `$10296`'s `bgt` still stores.
  The difference is unobservable for the same reason batch 1 registered: the two arms store the same
  word at the boundary. The boundary sweep pins the comparison's POSITION, never its strictness.
* **The registers the blits leave behind are dead, and that is checked rather than assumed.**
  `hud_blit_meter_cell`'s advanced cursor IS read back (`$b61e` halves the distance it travelled to
  count the cells it drew), so the C returns it and every case compares it against the oracle's `a1`.
  The rest are not: all 18 `$bb8a`/`$bba0` call sites reload `a0` and `a1` immediately before the
  `bsr`, and `$b6c2` has **five** call sites, all inside `$b61e` — `$b648` and `$b6b8` are `dbf`
  loop bodies (the full cells and the empty ones), `$b660`/`$b676`/`$b68c` are the three arms of the
  one-shot `cmpi.w`/`bne` chain that draws the single partial cell — every one of which `lea`s `a2`
  in the instruction immediately before, the two loop sites doing so inside the loop body. The kit's
  oracle reports `d0`/`d1`/`a0`/`a1` only, so `a2` could not have been compared in any case.

Reference counts in `../names.txt` for this region are **byte scans of the whole image** for each
address as an `abs.l` operand and, where it fits, as an `abs.w` one — not walks of the 252 recovered
functions, which is the qualifier batch 1's notes had to keep attaching. **That method has one blind
spot: a PC-RELATIVE operand.** `lea $b6e4(pc),a0` encodes as `41fa 0052`, a displacement with the
target address nowhere in the bytes, so no scan for `$0000b6e4` can see it. A `d16(pc)` sweep (every
even offset whose opcode carries EA mode 7 / reg 2, resolved to `pc + 2 + d16`) was run over all
eight addresses this batch counts and found exactly one such reference in the image — `$b690`, now
recorded under `meter_cell_offsets`, which therefore has two references and not one. Two results
that survive the sweep and are worth having: `frame_tick_b39a` has exactly two references (this
batch's `addq.w #1` and `rng_next`'s read), so the panel pass is the **only** writer of the PRNG's
only non-hardware entropy; and `bcd_addend_bd78` has exactly four, all of them the accumulators' own
staging writes, so that scratch longword is invisible to the rest of the program.

Mutation-checked rather than assumed, re-measured at this tree state (each rebuilt with the `.so`
deleted first, since a same-second rebuild otherwise re-runs the stale library — 481 green each time
it was restored): the BCD decimal correction `+6` → `+5` reddens 19; **dropping the meter's clamp
branch** reddens 11; **swapping the table-select's two arms** reddens 12; degrading the **OR blit to
a copy** reddens 8; returning the **unadvanced cursor** from the meter cell reddens 40; dropping the
**sign extension** in the indexed bitmap address reddens 6; and a **row stride of 158 instead of
160** reddens 38. 8 mutations, 1 survivor.

Two of those numbers moved since the batch first landed, both for stated reasons rather than for
drift: the meter cursor's went 20 → 40 because its battery now runs over both screen buffers, and
the stride's 22 → 38 because `src/hud.c`'s three identical row loops are now one `copy_rows`, so the
mutation reaches the record bitmap, the HUD-cell copy and the panel frame at once instead of the
record blit alone. The refactor made that mutation coarser; no per-blit stride survives it.

That survivor is `<=` → **`<`** in `hud_meter_add_clamped`, and it is the equivalence above rather
than a coverage hole: the two comparisons differ only where the raise lands exactly on the maximum,
and there both arms store the maximum. It is the same inert bit batch 1's clamp has, mirrored.

### The status panel's second tier

Nine routines, 710 bytes, in the same file: `src/hud.c`, `$b54c..$bd65`. Eight of them are **the
first reconstructions in this workspace that are not leaves** — the three field walks, the four
fields above them and the meter's own pass, each of which calls another, the tallest chain three deep
(`hud_draw_score_and_size_meter` → `hud_draw_eight_digits` → `hud_plot_digit`). The ninth,
`hud_plot_digit`, calls nothing: it is a leaf, and came in with this batch only because six of the
other eight cannot be ported without it. So the twenty routines in `src/hud.c` are **twelve leaves
and eight non-leaves**, which is not the batch-2 / batch-3 line.
The differential shape that makes that work is the one Joust established: on the original's side the
`bsr` runs its callee under the oracle, on the reconstruction's side the C calls the ported C, and
the two are required to agree byte for byte anyway. So a defect anywhere in a chain reddens every
case above it — the eight-digit walk's mutations redden the score and the high score too.

**The cluster is the digit plotter and everything that walks a field of digits.** `hud_plot_digit`
($b850) rotates a register left by a nibble and draws the nibble that was on top: 8 rows of one
8-pixel column, four plane bytes at +0/+2/+4/+6. Above it are three field walks (4, 8 and 2 digits),
and above those the four fields `panel_refresh_frame` draws — the counter, the score (which also
sizes the meter), the high score and the stage number. `hud_draw_meter` ($b61e) is in the batch for a
different reason: its callee `hud_blit_meter_cell` was already ported, so it was the one candidate
that needed no prerequisite at all.

**$b850 WAS THE PREREQUISITE, AND IT WAS NOT IN BATCH 2.** Six of the nine could not be ported
without it (their whole closure is `→ $b850`), so the leaf came in with the tier that needs it. It
has sixteen call sites, and the two the batch does NOT reach are inside `$b3da`, which stays unported
— so the leaf is verified over a superset of the fields ported here, but not over that caller's use
of it.

**Three candidates were STOPPED, and the reasons are findings.** The batch was scoped off
`../out/hw_scan.tsv`, which classified all three as clean-closure game logic:

* **`$bbca` ($bcd6's driver, 268 bytes) IS NOT IN THIS SUBSYSTEM.** The scan gives it one callee;
  besides its four `bsr $bcd6` it does `lea $17adc.l,a1 / jsr 56(a1)` at `$bc9c`/`$bca2` — a FIXED
  call to `$17b14`, the `movem`-wrapped thunk into `snd_trigger_effect` (`$1a48a`). A differential
  entered at `$bbca` runs the sound module on the oracle's side, so porting it means porting that
  closure too. **Read this as a caveat on the scan, not on that one address**: "N callees" is a claim
  about the calls Ghidra RESOLVED — the same class of blind spot as the fall-through that made
  `$bf4e` not-a-leaf. Recorded on `$bbca` in `../names.txt`.
  **DIAGNOSED AND CLOSED 2026-08-05 (batch 16a): Ghidra's 68000 sleigh models `jsr/jmp (d16,An)`
  one dereference too deep**, and that — not a filter — is what dropped `$bca2`. `68000.sinc`
  exports the `(d16,An)` operand as a *memory* varnode (`addrRegD16: … export *[ram]:4 tmp`) and
  spells the instruction `call [operand]`, so the pcode LOADs four bytes at the effective address
  and calls THOSE — while a 68000 transfers control TO the effective address and reads nothing.
  Constant propagation duly resolved `$bca2` to `0x48e7fffe`, the `movem.l #$fffe,-(a7)` opcode
  STORED AT the real target `$17b14`; that "address" is in no function, so the edge loop's
  no-target else-path dropped it, and `getFlows().length != 0` kept it out of the `I` ledger. The
  earlier elimination of that else-path had checked the wrong address (`$17b14` is an F record; the
  flow never pointed there). **`$bca2` was one of TEN**: every mode-5 indirect call Ghidra resolved
  was dropped the same way (`$594 $a9e $1732 $67a2 $6aea $6b54 $6bd0 $6be8 $bca2 $fa28`); the ten
  `I` rows were all mode-2 (`jsr (An)`) sites Ghidra resolved nothing for.
  `tools/ghidra_scripts/HwPortabilityScan.java` now takes the EA — which the propagator records as
  the instruction's READ reference — as the target whenever a computed transfer's pcode reaches it
  through a LOAD, and emits `I` whenever a computed transfer produced no row at all, so **every
  call/jump is in exactly one ledger**. The header's old claim that a fixed-base indirect "belongs
  in I, not E" was itself wrong (`lea $17adc,a1 / jsr (a1)` always produced E edges). Cost to the
  measurement: **ten new `E` rows, none removed, the ten `I` rows byte-identical**; `$bbca` is now
  honestly `→ $17b14 → snd_trigger_effect` and STAYS runnable (that subtree is T0 clean); the real
  casualty is `game_routine_6bb8`, T3 → **T4** via `$17af8 → snd_stop → snd_stop_all_sfx →
  snd_psg_silence`'s PSG read — runnable 223 / 21,624 B → **222 / 21,334 B (82.7 %)**, unreachable
  116 → 112 (`$17b14`/`$17b30`/`$17f92`/`$1a48a`, 376 B, all T0), edges 233 → 240.
  `portability_predictions.py` stays 14/14 green. [`PORTABILITY.md`](PORTABILITY.md) §0d is the
  full record; `docs/on-target-execution.md` rule 4 carries the mechanism. The fall-through blind
  spot (`$fe4a`/`$fe8c`, `$bf4e`) is a DIFFERENT mechanism — no transfer instruction exists there —
  and remains open.
  (`docs/on-target-execution.md` rule 4 and `tools/ghidra_scripts/HwPortabilityScan.java`'s `I`
  record carry the short form.)
* **`$b8f0` (the six HUD slots, 666 bytes) is in scope but oversized.** Its closure is clean and both
  callees (`hud_blit_cell_copy`/`hud_blit_cell_or`) are already ported, so it is portable today; at
  666 bytes and 18 blit call sites it is a batch of its own. Now named and scoped in `../names.txt`
  (`hud_refresh_dirty_slots`): six slot records, a request byte each, blank-then-OR per slot.
  *(Landed in batch 4.)*
* **`$b346` itself cannot be ported until four more are.** It is ten calls and an `rts`; SIX of the
  ten are now reconstructed (`$b54c`, `$b74a`, `$b7c6`, `$b61e`, `$bd32`, `$b372`) and four are not
  — `$d93a` (446 bytes, the screen-region restore), `$b39c` (whose own `$b3da` is `$b850`'s other
  caller), `$b8f0` and `$bbca`. *(Batch 4 landed three of the four; `$bbca` remains, and the section
  after this one records why it is a hard stop rather than a queue position.)*

Six things a later reader should not have to re-derive:

* **Every entry pin here is the routine's WHOLE BODY, not its first instruction.** All nine matched
  byte for byte on the first run, which is the strongest single result in the batch: it means the
  step immediates, the branch displacements, the shift counts, the glyph stride, the five score
  thresholds and every `bsr` target were read correctly before a differential was run. Two of them
  are built rather than transcribed and that is deliberate: a `bsr.w` displacement is computed from
  the two entry points `../names.txt` gives (so a reconstruction aimed at the wrong callee fails at
  its own address), and the shift/rotate opcodes are assembled from the geometry constants (so
  `asl.w #5` is spelled out of `WB_DIGIT_GLYPH_LEN` and `asr.w #2` out of `WB_METER_CELL_UNITS`,
  rather than restating the counts).
* **THE FONT IS AN UNSET REGISTER.** `panel_refresh_frame` sets neither `d0` nor `d7` before any of
  its nine `bsr`s, and `$b850` reads `d0` (`cmpi.w #1,d0` picks between two overlapping glyph tables,
  and also picks what a suppressed zero looks like). So the glyphs three of the four fields are drawn
  with are whatever the routine before them left behind. That is the game's behaviour, not a gap in
  the reading; the port takes `d0` as an argument and every battery sweeps both sides of the compare.
  The four-digit walk is the exception — its first instruction is `moveq #0,d0` — and a case that
  enters it with `d0 = 1` and gets the same bytes is what pins that.
* **The leading-zero latch is a WORD IN MEMORY, and the three walks disagree about it.**
  `digit_significant_seen_b84e` suppresses a zero until something significant has printed. The
  four-digit walk forces it before its LAST digit, the eight-digit walk before its last TWO, and the
  two-digit walk not at all — so a stage number below 10 really is drawn as one digit and a blank.
  All three clear it on the way out, which is why every case can read the final value back. The
  battery states that rule independently of `src/hud.c` (`_field_expected`) rather than copying it.
* **A "blank" is not nothing.** Under the default glyphs a suppressed zero is `clr.b` on three planes
  and `st` on the fourth — a solid $ff, i.e. a coloured bar — while under the alternate glyphs all
  four are cleared. That single plane byte is the *only* place `d0` is observable on a zero digit,
  which is why the `cmpi.w`-on-the-low-word case runs on a suppressed zero rather than on a glyph.
* **The two glyph tables OVERLAP.** `$145bc` is `$1447c + $140`, exactly ten glyphs in, so "the font"
  is a window into one twenty-glyph block and a case that fed the wrong table would still read real
  image data. Pinned by its own assert.
* **`$b74a`'s five thresholds are SIGNED longword compares.** A score whose top nibble is 8 or 9
  reads negative, matches none of the five and leaves `hud_meter_max` untouched — which the sweep
  reaches with `$99999999`, a value the game's own BCD accumulator can produce. `$b7c6` has the same
  signedness: a score with bit 31 set loses to any small high score.

**One** thing this battery knowingly does not pin. Two more were registered here and are **now
pinned** — both were blocked on the oracle's register set, both were re-run against it by batch 11
below, and the paragraph after the mutation register records what happened to each:

* **`hud_draw_meter`'s RUNAWAY LOOP.** Every step after the `divu` is 16-bit, so a maximum below the
  value makes the empty-cell count negative, the `bne` still takes the loop and the `dbf` runs it
  down through 65535 iterations, walking the cursor far past `meter_cell_offsets`' ten entries and
  blitting off the end of the screen. `src/hud.c` reproduces it by construction (the count is a
  `uint16_t` and the loop is its exact value), no case reaches it — the battery's own `_meter_plan`
  refuses to build one — and **whether the game's own writers can produce it was not established**:
  `$fe4a` resets both words to `$14` and `$b74a` only raises the maximum, but the value has writers
  outside the recovered set. Honestly unpinned.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and compared byte for byte against a pristine copy afterwards — 649 green each time; every
figure below was re-measured against the tree as the batch landed, not against the draft it was
written on. The review then added the two raised-entry-latch cases, taking the suite to **651**; the
per-mutation counts below were NOT re-measured against those two, only the staged-field survivor
was):
a **blank filling the wrong plane** reddens 61; the shared 32-bit rotate **reversed** reddens 110;
the font selected on **d0's whole longword** reddens 1; the eight-digit walk **forcing the latch one
digit late** reddens 7; the two-digit walk **forcing the latch** like the other two reddens 8; the
score's threshold compare made **strict** reddens 5; the score compared **unsigned** reddens 1; the
meter's partial cells for **remainders 3 and 1 swapped** reddens 4; the empty count dividing the
maximum by **2 instead of 4** reddens 18; and the stage number's **`rol.l #8` cut to a nibble**
reddens 11. **12 mutations, 10 killed, 2 survivors as measured — and only ONE of the two is still a
survivor.** The equivalence is the `>` → `>=` in `hud_draw_larger_score`: at equality the two fields
hold the same bytes, so both arms draw the same digits — the same inert bit batch 1's and batch 2's
clamps have. The other, the staged-field half, **was an ORACLE BLIND SPOT and is now dead**: `>> 16`
and `& 0xffff` put *different words in d7*, i.e. different machine state, and the two were
indistinguishable only through the `d0`/`d1`/`a0`/`a1` window the kit's oracle then reported — a
missing observer, not an inert bit, which is why this register said "re-run this mutation if the
oracle ever grows `d7` reporting". Batch 11 grew it and ran it: **it reddens 6**, and the entry is
discharged rather than left standing.

**BOTH OF THIS TIER'S REGISTERED BLIND SPOTS ARE CLOSED (batch 11), and the trigger fired exactly as
written.** The kit's oracle now reports the whole `movem` set (`emu.REPORTED_REGS`: `d0..d7`,
`a0..a6`; `a7` is the harness's own), and the two things this battery stopped short of for
OBSERVABILITY rather than difficulty were re-run against it.

* **`hud_plot_digit`'s outgoing `d7` is a per-case assert now.** `rol.l #4,d7` at `$b868` is the only
  instruction in the whole 160-byte body that touches the register, so all three `rts` — `$b8a6` and
  `$b8c4` (the two blank arms) and `$b8ee` (the glyph one) — leave the entry value rotated by one
  nibble, and they do NOT differ, which was checked rather than assumed. All 45 cases now compare
  three values instead of two: a rotate MODEL, the ORACLE's `d7`, and the value the reconstruction
  leaves in its `uint32_t *digits` out-parameter. Only the third can catch a wrong C, which is the
  whole reason the exposure was worth a signature change.
* **The staged-field mutation DIED, and the batch-3 reading of it was right about the pixels and
  wrong about the register.** Four `rol.l #4` come to a `swap`, so the half `move.w field,d7 /
  swap d7` buries is back in `d7`'s HIGH word by `$b560` / `$bd48`. It never reaches a drawn nibble —
  that part of the reading stands, and is why 651 cases could not see it — but it is sitting in the
  register at the `rts`. `$b54c` leaves `(entry d7 & $ffff0000) | bcd_counter_bd6e` and `$bd32`
  leaves `(entry d7 & $ffff0000) | stage_number`, which
  `test_a_word_field_buries_the_callers_high_word_and_hands_it_back_in_d7` states by NAMING the two
  halves rather than by rotating.
* **The cost was five signatures**, and it is the price of an observer rather than a tidy-up: the
  three field walks and the two fields loaded as a word now return the digit register the original
  leaves in `d7`, the way `hud_plot_digit` already took a pointer to it and `hud_blit_meter_cell`
  already returned its cursor. An assert of the oracle's `d7` against a Python model would have
  pinned the ORIGINAL twice and the port not at all. `$b74a`, `$b7c6` and `$b3da` stay `void`:
  nothing reads their `d7`, so their cases assert the oracle's only — and `$b74a`'s agreement with
  the model is a COINCIDENCE, since it re-reads the score into `d7` at `$b75c` and an eight-nibble
  rotation is the identity.

Re-measured on the widened oracle (each with the `.so` deleted before the rebuild and the source
byte-compared against a pristine copy afterwards): the **staged-field half** reddens **6** — exactly
the cases whose entry `d7` has two different halves; a **pixel-neutral corruption of the register
`hud_plot_digit` hands back** (clearing the nibble it just drew, which cannot rotate back to the
bottom within eight plots and so draws an identical image everywhere) reddens **90**, of which 36 are
`$b850`'s own — before the widening that mutation was invisible in every one of the 651; the counter
returning its staged value instead of the walk's reddens 15 and the stage number doing the same 15;
the four-digit walk's last plot not advancing the register it returns reddens 30; `hud_plot_digit`
rotating by a **byte** reddens 148; `staged_word_field` dropping the `<< 16` reddens 26; the stage
number rotating by a **word** reddens 15; the blank filling the wrong plane's font reddens 81; and
`plot_digit_then_step` **adding** its rewind reddens 120. **10 mutations, 10 killed, 0 survivors.**

Three of those numbers are worth reading rather than skimming. The **font-on-the-longword** mutation
reddens exactly ONE case — the `d0 = $dead0001` blank — because that is the only case whose `d0` has
rubbish above a low word of 1; that is a battery with one case per claim, not a thin pin. The
**unsigned score compare** likewise reddens exactly the `$99999999` case, the only seed with bit 31
set. And the rotate's 110 is lower than the 112 the same mutation gave before `rotate_left32` was
factored out of the two rotate sites: it now flips the stage number's `rol.l #8` as well, and a
handful of stage cases come out identical under two flips that the nibble flip alone reddened. A
shared helper makes that mutation COARSER, exactly as the leaves' `copy_rows` did to the stride one.
**Read 110 as a FLOOR, not the count, since batch 6.** It was measured while `rotate_left32` was
`src/hud.c`'s own; the helper now lives in the kit's `include/machine.h` and `src/scroll.c` calls it
twice, so flipping it today also reddens scroll cases — the same coarsening one step further out. The
panel's own 110 was not re-measured, because the mutation no longer isolates the panel.

### The status panel's third tier

Ten routines, 1412 bytes, in the same file: `src/hud.c`. They are `panel_refresh_frame`'s three
remaining table walks and the six blits under one of them — the region restore that opens the frame
(`$d93a` and `$daf8`/`$db12`/`$db34`/`$db36`/`$db58`/`$db72`), the newest record's display (`$b39c`
and `$b3da`) and the six HUD slots (`$b8f0`). With them the pass has **nine of its ten callees
reconstructed**.

**WHAT THE THREE WALKS HAVE IN COMMON is a REQUEST BYTE that is consumed rather than read.** Each
finds its work by testing a byte something else raised and clearing it in the same breath: the
fifteen restore flags at `$dbb0`, the fresh-record flag `$b54a` (which `$b39c` tests but never
clears — see below), and the six slot request bytes at `$bbbf`/`$bbc1`/… So these are the first
reconstructions here whose write set includes bytes they were *told about* as well as bytes they
drew, and every case asserts the clear as well as the pixels.

**`$d93a` IS THE OTHER HALF OF EVERY `st $dbbN` IN THIS SUBSYSTEM,** and its table is the strongest
single piece of evidence the batch produced. Fifteen entries, each naming a screen offset; **eleven
of those offsets are constants `include/wonderboy.h` already carried** for a draw in this file — the
score, the high score, the counter, the record bitmap, the six slot cells and the panel frame — and
two of the five blit geometries are geometries this file already had: `$db58` moves 16 bytes over 14
rows, which *is* `hud_blit_cell_copy`'s cell, and `$db72` moves 24 over 32, which is the panel
frame's. So an entry means "put the front buffer's pixels back over what that draw dirtied", and the
header reuses the constants rather than restating them (a test asserts the two geometries are the
same numbers, since nothing else would).

**THE PAIRING IS NOT EXACT, and the port reproduces the original rather than the intent.** Five
things a later reader should not have to re-derive:

* the `$2800` entry restores **29 rows where `hud_blit_record_bitmap` draws 32**;
* the `$aa0` entry (the meter's — `panel_restore_flag_dbb3` has exactly one writer in the image,
  `hud_draw_meter`'s `st`) covers rows 17..36, and `meter_cell_offsets` starts at `$a01`, **row 16**,
  so the restore misses the meter's top row;
* the counter's entry `bsr`s **`$db34`, which is a bare `rts`** — a routine, not an absent call,
  which is why it is reconstructed as one and has an entry pin of its own;
* the **first three entries have no `bsr` at all**: they compute both cursors and fall through to the
  next test. They clear their flag and draw nothing, exactly like the `$db34` entry, and the
  difference between the two shapes is visible in the disassembly and nowhere else.
* **three of the eleven blitting entries have no writer in the image at all.** A whole-image
  `abs.l` scan for each of the fifteen flag bytes finds a writer for only eight — `$dbb3`, `$dbb5`
  and `$dbb6..$dbbb` — so the other seven (`$dbb0`/`$dbb1`/`$dbb2`/`$dbb4`/`$dbbc`/`$dbbd`/`$dbbe`)
  are never raised by anything a scan can see; four of those seven are dead entries anyway, and the
  remaining three DO blit, **including the panel frame's own `$dbbc`**. Recorded on
  `panel_restore_flags` in `../names.txt`; the differential enters `$d93a` directly, so the cases
  reach every entry regardless.

**THE RECORD'S DIGITS ARE DRAWN INSIDE THE RECORD'S BITMAP.** `$b3da` plots at `screen_back + $3490`,
which is row 84 byte 16, and `hud_blit_record_bitmap` fills rows 64..95 of bytes 0..31 — so on a
frame that takes both of `$b39c`'s arms the bitmap goes down first and the two digits are stamped
into it. The battery pins that geometry as its own assert and compares the bitmap's rows with the
digit bytes left out; without it the bitmap assert would have been red for the wrong reason. `$b3da`
is also **a fourth digit-field walk**, beside `$b5ea`/`$b7ea`/`$bd4a`, and the only one that forces
the ALTERNATE font (`move.w #1,d0` before *each* of its two plots) — which is why `hud_plot_digit`'s
sixteen call sites are now all inside reconstructed code.

**`record_fresh_flag` ($b54a) IS NEVER CLEARED.** It has exactly two operand references in the whole
image — one `st` at `$1262`, inside the unrecovered list-walker at `$1208`, and `$b39c`'s `tst.b` —
and no `clr` among them. So once something raises it the record's bitmap is redrawn every frame from
then on. The claim is an `abs.l` scan and cannot see a writer that reaches the byte through an
address register; stated that way in `../names.txt` rather than as "nothing clears it".

**`$b346` IS STILL NOT PORTABLE, and the reason is now final rather than arithmetic.** Its one
remaining callee is `$bbca`, the sound-module blocker batch 3 registered — and the `bsr.w $bbca` at
`$b364` is one of ten UNCONDITIONAL calls, not a branch. So no seeding of the image can steer a run
entered at `$b346` around it: the oracle would execute the `jsr 56(a1)` thunk into
`snd_trigger_effect` whatever the timers hold. Porting `$b346` therefore means porting `$bbca`,
and porting `$bbca` means either porting the sound module or shipping a reconstruction with a whole
subsystem call silently missing on one side. Neither was done, and **`$bbca` remains the single
blocker**; the `$bd2c > $a` branch inside it that skips the thunk is a seedable escape *if* that
routine is ever ported on its own terms, which is a scoping decision for a sound batch and not for
this one. *(Batch 16b did exactly that scoping the other way: `snd_trigger_effect` itself proved
RAM-only — the one routine in the module the differential can see whole — so the sound batch was
this batch, and $bbca and $b346 are ported. See the batch-16 section.)*

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and compared byte for byte against a pristine copy afterwards — 793 green each time):
the restore's source **stepping a row instead of a scanline** reddens 35; the `32x29` restore moving
the record bitmap's **32 rows** reddens 5; the bare `rts` **quietly blitting a cell** reddens 4; the
walk restoring **front from back** reddens 13; the walk **leaving its flag raised** reddens 17; the
walk **ignoring its flag entirely** reddens 16; a **dead entry given a blit** reddens 3; **two
restore regions swapped** reddens 2; the record display's empty test made **unsigned** reddens 2; the
record digits taking the record's **high byte** reddens 22; those digits drawn in the **default
font** reddens 24; their **latch forced one digit early** reddens 9; the slot pass **ORing before the
blank is laid down** reddens 35; the slot pass reading the **request byte as the value** reddens 25;
the slot pass **leaving the request byte set** reddens 51; the sixth slot's **out-of-range variant
drawing the last icon** reddens 2; and its **variant chain off by one** reddens 10.
**18 mutations, 17 killed, 1 survivor.**

**THE SURVIVOR IS DEAD DATA IN THE PORT, and it is registered rather than fixed.** Replacing
`WB_SCORE_ORIGIN` with `0x1234` in `PANEL_RESTORE_REGIONS`' first row leaves all 793 green. The
first three entries have no `bsr`, so their origin is never used for anything a case can observe —
the ORIGINAL's `lea` operands for those entries ARE pinned, byte for byte, by `$d93a`'s whole-body
entry pin, but the port's own copy of them is not, and no seeding can make it so. That is the
CLAUDE.md rule for a branch the data cannot reach, applied to a constant: say so and leave it
honestly unpinned. `src/hud.c` marks the three rows DOCUMENTARY at the table.

**Four of the eighteen were survivors first, and the fixes are house patterns worth keeping.** The
`32x29` restore moving 32 rows and the bare `rts` blitting a cell both survived the first sweep: the
cases seeded exactly the region's own geometry, so an over-copy read ZEROS from the source screen
and wrote them over ZEROS on the destination, and both sides still agreed. **A screen-to-screen blit
is the shape that has this hole** — the bitmap blits do not, because their source is real image data
(a probe confirms it: one row too many on the record bitmap, the HUD cell and the panel frame each
redden, and `test_the_bitmap_sources_are_non_zero_past_their_last_row` now keeps that property from
being lost silently). So every region case seeds its region WIDENED by a margin
(`REGION_MARGIN_ROWS`/`_BYTES`) on both screens, with filler keyed on the ADDRESS rather than on a
row index — the widened bands of two side-by-side slot cells overlap, and an index-keyed filler
would have let the later poke silently rewrite the earlier one. The review then found the same hole
ONE LEVEL UP, and the last two mutations are its measure: the walk's cases seeded a band only for
the entries that WERE to be restored, so "flag down ⇒ region untouched" and "a dead entry stays
dead" were pinned nowhere. `_run_restore_walk` now seeds all fifteen bands whatever the case, the
four dead entries at the WIDEST of the five geometries. The general lesson is written up in
[`docs/methodology.md`](../../../docs/methodology.md), "The seeding hole a mutation sweep finds".

**One branch of the slot pass is unreachable from the game's own data, and is pinned only by
fabricated bytes.** The sixth slot's variant chain has six arms; the recovered setters
(`src/effects.c`) write 1, 2, 3, 4 and 6, so **arm 5 and the `> 6` fall-through are reached in this
battery only by a value byte a case invents**. Both are pinned against the ORIGINAL (the differential
runs the real chain on the same invented byte), which is a real pin — but read the STATUS row's
"the sixth slot's 8 values" as eight *addressable* values, not eight the game produces.

**Every one of the ten entry pins is the routine's WHOLE BODY and every one matched on the first
run** (`panel_restore_none` included, all two bytes of it) — 1412 bytes, including `$b8f0`'s 666 and `$d93a`'s 446. Both of those are built from the same
table the reconstruction is (the six slots and the fifteen restore entries), so a routine wired to
the wrong region, flag, cell or callee fails at its own address rather than as a diff. The `movem`
masks are now built from a register LIST rather than transcribed, which is what ties `$daf8`'s
44-byte row to the eleven registers it moves.

### The background scroll engine (batch 5), and what the cluster turned out to be

Six routines, 1590 bytes, in a new file: `src/scroll.c`. The cluster at `$7522..$8228` was
unexplored — the hw scan could say only that it was fifteen functions with no hardware access and
every callee inside itself. **It is the level's SCROLLING ENGINE**, and the shape is worth stating
before the batch notes because everything else follows from it.

**THE GAME KEEPS EIGHT PRE-SHIFTED COPIES OF THE BACKGROUND.** `$5800` bytes each, tiling
`$44000..$70000` — the map `project.toml` already recorded from a longword scan, now explained. Copy
N is the same tile map drawn two pixels further left than copy N-1, so a two-pixel horizontal scroll
is a change of BUFFER and not a redraw, and the only work per step is the ONE tile column the scroll
uncovers. `bg_scroll_blit` (`$82f8`, named in a previous pass but not ported) is the consumer: it
copies the chosen buffer to the screen. Three independent readings agree on the model:

* `bg_scroll_phase` (`$83ac`) is used THREE ways in one routine — `mulu.w #$2c00` to pick the
  buffer, as a byte index into `bg_scroll_edge_masks`, and as the `rol.l` count that shifts the
  tiles. That is only coherent if the buffer index and the pixel offset are the same number. It was
  named `bg_scroll_buffer # ctx` before this batch; the `# ctx` tag is now gone and the name is
  `bg_scroll_phase`.
* `bg_scroll_preshift_rows` (`$8144`, read here and ported in batch 6) does nothing but walk a freshly drawn row
  through the seven remaining copies, `rol.l #2` at a time — the other half of the same scheme.
* The eight buffer addresses `bg_scroll_step_up`/`_down` reload are exactly `$44000 + N * $5800`.

**THE STEPS RETURN THROUGH THE STACK, and that is the batch's transferable finding.** A step with
nothing to do does `addq.l #4,(a7)` (or `#8`, in the vertical pair) and `rts`, returning PAST its
caller's `bsr` to the fill. One act means both "no movement" and "skip the redraw". **Ghidra models
none of it** — `../decomp.c` shows a bare `return` for that arm and an unconditional pair of calls
in the caller, so a reconstruction written from the decompiler would read correct and behave wrong.
It is not a hw-scan blind spot (the routines have an `rts`, no hidden callee, no hardware), it is a
decompiler one, and it is now written up as general 68000 method in
[`docs/m68k-disassembly.md`](../../../docs/m68k-disassembly.md).

It also broke the harness, in the way that idiom always will: the kit stops a run when the PC
reaches the sentinel it pushed as the return address, and the skipping arm returns to *sentinel + 4*
instead. `test/leaf.py` gained a `stop_pc` passthrough for it, and — because a second stop PC on its
own would let both arms pass the same case — every step case **reads the decision off the oracle's
own stack**: `emu.run` writes the sentinel AT A7, so the skipping arm has rewritten that longword to
sentinel + 4 and the other arm never wrote there at all. The reconstruction's returned flag is then
required to agree with it. Neither side is trusted to report its own answer.

**THE FILL CASES COMPARE A WRITE SET FOR EQUALITY, not for containment.** A column fill is a
read-modify-write over a buffer — `and.l` a mask over the cell the scroll vacated, then `or.w` the
rotated tiles back into it — which is the shape batch 4's mutation sweep found the seeding hole in.
Two defences, from opposite directions: every case seeds the whole `$5800` buffer PLUS a scanline
either side with a byte keyed on the ADDRESS (so an over-run writes something wrong, rather than
zeros over zeros — with a per-case salt taken from the case NAME by `crc32`, not by `hash()`, whose
randomisation per process would make a failure unreplayable and the red counts below unstable), and
every case then requires the oracle's write set to be EXACTLY the address set
a Python model of the fill produces, and every byte in it to be that model's value. The model is
written from the disassembly rather than from `src/scroll.c`, so it is a third statement of the
geometry and not a copy of the second.

**THE TILE SOURCE IS THE GAME'S OWN PIXELS, and there are only sixteen of them in the .PRG.** The
region `bg_tile_bitmaps` covers holds 148 bitmaps of 128 bytes; tiles 0..119 and 136..147 are ZERO
in the shipped file and filled at runtime (as the map, the tile index and the row stride all are —
they live past the program's end at `$218d0`). Only tiles **120..135** ship. Every case draws from
those, so no rotation is a rotation of zeros, and
`test_the_shipped_tile_bitmaps_are_the_sixteen_the_header_names` is the reading that fixes the two
numbers in `include/wonderboy.h` rather than asserting them.

**FOUR PIECES OF EVIDENCE CAME OUT OF THE READING that the batch did not need but the next one
will.** All four are in `../names.txt`:

* **`bg_scroll_raise_requests` (`$d28`) is what drives the whole cluster**, and it settles the
  direction names independently. It compares two words at `$9934`/`$9936` against `$5a` and `$30`
  and raises the request byte for the side the value falls on, returning the distances. So "left"
  means the tracked object is left of centre, and the routine that request reaches is the one that
  DECREMENTS `bg_scroll_pos_x` and fills the column at the map cursor's own cell — while "right"
  decrements nothing and fills fifteen cells further on. The two namings were derived separately and
  agree.
* **Two of the four request bytes have no writer anywhere in the image.** An `abs.l` scan finds a
  writer only for `$8230` and `$8232`, both inside `bg_scroll_run_queue` — and both are WORD moves
  of a byte PAIR, so `$8231` and `$8233` are raised only as the low halves of them. Same family as
  batch 4's "three of the eleven blitting entries have no writer": stated as what the scan sees, not
  as "nothing raises them", because a write through an address register is invisible to it.
* **The two split tables are the ring geometry, and both are pinned as data.**
  `bg_scroll_col_split_table` entry k is `(10 - k, k - 1)` and `bg_scroll_row_split_table` entry k is
  `(15 - k, k - 1)`, so a fill's two `dbf` halves always sum to exactly one buffer's worth of tile
  rows and entry 0's second count is `-1` = no wrap needed. Neither table has an `abs.l` reference of
  its own: both are reached only by a `lea` on the word before them, which is why
  `bg_scroll_col_split_table`'s `var` line records that its justification is
  `bg_scroll_y_coarse`'s `move.w (a5)+,d0`.
* **`bg_scroll_edge_masks` is `$ffff << phase` for every entry but the first**, which is `$0000`
  rather than the `$ffff` the rule would give — so phase 0 clears the whole cell and redraws it, and
  the right-hand fill's `move.w #$10,d5` / `lea -1(a3),a3` special case exists to feed it a whole
  fresh tile. Both are asserted against the shipped image.

**Every one of the six entry pins is the routine's WHOLE BODY and every one matched on the first
run** — 1590 bytes including two 670-byte routines of sixteen-times-unrolled loops. They are built
from the same constants the reconstruction is (the buffer geometry, the masks, the map offsets, the
callees' addresses out of `../names.txt`), and the loops are assembled programmatically so the `dbf`
and `bcc.w` displacements come out of the pieces they jump over rather than being transcribed. A
seventh case asserts each pin's LENGTH against the size `../out/hw_scan.tsv` records, because a
whole-body pin that happened to be a prefix would otherwise pass.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 858 green each time, re-measured
against the tree as it landed rather than against the draft the sweep was first written on):
the mask **inverted at every phase** reddens 3; the coarse row scaled by a **scanline instead of a
tile block** reddens 26; the clear loop **one scanline short** reddens 30; the two halves of the
rotated longword **swapped** reddens 30; the phase-zero redraw **without the map step-back** reddens
3; the second half given the **first half's count** reddens 24; the latch test made **strict**
reddens 3; the left step's row offset left **unmasked** reddens 3; the request byte **left raised**
reddens 3; the rotate turned into a **rotate right** reddens 24; the tile index read as a **byte
table** reddens 30; the split table indexed by the **word instead of the pair** reddens 26; the right
edge given **no x bias** reddens 15; the no-second-half test made an **equality** reddens 6; the map
walked by **one cell instead of a row** reddens 30; and the second cell taken from the **wrong side**
reddens 15. **16 mutations, 16 killed, 0 survivors.**

**One of the sixteen was a coverage finding, and the case that closes it is in the batch.** On the
first sweep the no-second-half test (`(int16_t)second < 0`) made an equality reddened only 4 — the
coarse-row-0 cases, where the count is `-1`. The count is exactly `0` at coarse row **1**, and no
case used it, so the boundary between "one tile row in the second half" and "no second half" was
pinned on one side only. `FILL_CASES` now carries `coarse1`, and the figure above is the 6 it
reddens with that case present.

**The four mutations that redden only 3 are the step and request-handler ones, and that is the
battery's shape rather than a thin pin.** Those routines write six words between them, and the
battery has one case per claim: the latch's three words, the phase carry's three positions, the
borrow's four. A mutation to one of them reddens exactly the cases that address it — the same
reading batch 2's "one case per claim" note records.

**Two things this batch does NOT pin**, both by construction rather than by omission:

* **The registers the fills leave behind.** Both walk out with every address register far past where
  it started; the kit's oracle reports `d0`/`d1`/`a0`/`a1` only, and both call sites `rts`
  immediately, so there is nothing a case could compare against. Same family as the panel blits'.
* **The 65536-iteration `dbf`.** Both fills take their lengths from `bg_scroll_col_split_table`,
  whose first words are 10 down to 0 — a negative first count would run 65536 tile rows and walk out
  of the buffers, and no seeding through `bg_scroll_y_coarse` can produce one, because the table is
  the game's own data and a case that rewrote it would be pinning an invented record. Reproduced by
  construction in `src/scroll.c` (`uint16_t` counters and do/while loops) and honestly unreached.

### Closing the scroll engine (batch 6): the vertical half and the tier above it

Ten routines, 1808 bytes, into the same `src/scroll.c`. With batch 5's six that is the **whole**
`$7522..$8228` cluster plus `$d28`: 3398 bytes, sixteen routines, nothing left named-but-unported and
nothing STOPPED. The cluster's own shape — a request queue drained once a frame, dispatching to
handlers that each consume their byte — is now reconstructed end to end, so a case entered at
`bg_scroll_run_queue` runs the entire engine for one frame under the oracle.

**THE VERTICAL HALF SCROLLS BY MOVING POINTERS, and that is why the pre-shift exists.** There is
nothing to pre-shift vertically: a two-scanline scroll is a change of row within the same buffer. So
the position is a ROW INDEX (`bg_scroll_y`) and the eight buffers' cached row pointers move with it,
the fill copies one map row of tiles into copy 0 **unrotated**, and `bg_scroll_preshift_rows` then
walks that fresh row through the other seven copies, `rol.l #2` at a time. That routine is the other
half of batch 5's eight-copy scheme, and porting it is what makes the horizontal half's "a scroll is
a buffer switch" a closed loop rather than an assertion.

**THERE ARE TWO RING CURSORS, NOT ONE, and batch 5's reading of `$761c` was wrong about them.**
`bg_scroll_y` (`$83a8`) governs the window's top scanline pair and the EVEN half of
`bg_scroll_buffer_rows`; `bg_scroll_y_bottom` (`$83aa`, unnamed until this batch) governs its bottom
pair and the odd half. Each has its own wrap test inside the same step, and `$fb96` starts them 158
rows apart — the visible 160-line window's two ends. Batch 5's `cmt` claimed the two halves reload to
`$49700..` and `$49800..`; they reload to the SAME eight addresses, and the `$49800` figure was the
*down* step's. Both `cmt`s are rewritten, and the case `bottom-cursor-at-its-own-wrap` — one cursor at
its wrap and the other not — is what a port driving both from one row word fails on.

**ONLY PAIR 0 OF `bg_scroll_buffer_rows` IS EVER READ.** An `abs.l` scan gives `$82a6` and `$82aa`
seven references each (four in the steps, one in the matching row fill, one in the pre-shift, one in
the init) and `$82ae..$82e2` only the steps' and the init's. The pre-shift chains from one copy to the
next by adding `$5800` rather than by reading the next pointer, so pairs 1..7 are bookkeeping nothing
consumes. Recorded in `../names.txt` rather than acted on: the steps still write them, and the
reconstruction still writes them, because that is what the original does.

**THE OVERFLOW FLAG IS PART OF A `subi.w`/`bgt` PAIR, and this batch found it the hard way.**
`bg_scroll_raise_requests` decides which side of the screen the followed object is on with
`subi.w #$30,d0 / bgt / blt`. The obvious C — take the wrapped difference, test its sign — is wrong at
one position: `$8000 - $30` is `$7fd0`, which reads *positive* while the 68000's `blt` (which reads
`N xor V`) takes the *negative* arm. The first draft had exactly that bug and the
`wrapped-at-the-lowest-position` case caught it; the fix compares the POSITION against the centre as
signed words, while the distance returned stays the wrapped difference. The same case records the
second thing that breaks there: the routine's "both distances come back positive" property fails, because
`neg.w $7fd0` is `$8030`. Both are reproduced rather than tidied, and the general rule is now in
[`docs/m68k-disassembly.md`](../../../docs/m68k-disassembly.md).

**THE SKIP IS `#8` HERE, AND THE BATTERY HAD TO LEARN THE DIFFERENCE.** A vertical step with nothing
to do does `addq.l #8,(a7)` — two return addresses, because it has a fill AND a pre-shift to consume.
`test/test_scroll.py`'s `STEP_SKIP_BYTES` is now a per-step map rather than the single `4` batch 5's
reviewer flagged, `_oracle_skipped` takes the distance and asserts the oracle landed at
*sentinel + that*, and the run's second stop PC comes from the same map. A step that consumed the
wrong NUMBER of calls fails on the assert rather than reading as a plain skip.

**THE VERTICAL CASES SEED ALL EIGHT BUFFERS.** The pre-shift writes 1792 bytes across seven copies, so
batch 5's "one buffer plus a scanline either side" is not enough margin: a walk that chained by the
wrong stride, or ran one copy too far, would land on zeros. `_scroll_pokes(whole_region=True)` seeds
`$44000..$70000` plus a scanline either side, keyed on the ADDRESS with the same salt as the
horizontal seeding — so a case that uses both (every dispatch and queue case does) gets one consistent
image where the two overlap. The block is `lru_cache`d, because it is 180 KB of Python-level byte
generation that would otherwise be redone per case.

**A SERVE AND EVERYTHING ABOVE IT RUNS WITHOUT THE ATTRIBUTION PASS**, and the reason is structural
rather than a convenience: the vertical step writes the sixteen row POINTERS and the fill under it
then draws THROUGH them, so poisoning the step's outputs in the input image would aim the fill at an
address the run stores to — off the image, in C. The step, the two row fills and the pre-shift are all
run WITH poisoning (none of them stores through a value it also writes); only the four serve routines,
the dispatch pass and the queue turn it off. This is exactly the case `leaf.run`'s `poison=False` was
documented for in batch 5.

**Every one of the ten entry pins is the routine's WHOLE BODY and every one matched on the first run**
— 1808 bytes, including two 400-byte steps of eight-times-unrolled `move.l`/`subi.l` and the
pre-shift's three nested loops. The routines with callees needed something the straight-line ones did
not: a `bsr.w`'s displacement depends on where it is assembled, so `test/test_scroll.py` gained a small
`_Assembler` that tracks the cursor, and each call's target still comes out of `../names.txt`. The
queue's two drain loops close with a `bra.s`, whose byte displacement is asserted to fit rather than
transcribed.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 937 green each time, and the whole
sweep re-run against the tree as it LANDED rather than against the draft it was written on. The
review then added the two vertical-step wrap seeds the function table's `$761c` row describes, taking the
suite to **941**; the per-mutation counts below were NOT re-measured against those four cases, so
read each as a floor): the row
pointers stepped by **rows instead of scanlines** reddens 19; both cursors driven from the **top row
word** reddens 18; the down step wrapping at **zero instead of `$ae`** reddens 4; the coarse row
republished from the **bottom cursor** reddens 18; the top fill **masking the tile row before testing
its sign** reddens 6; the row fill's second half rewinding **one cell instead of one scanline**
reddens 18; a row fill copying **one scanline instead of the pair** reddens 20; its map walking **down
a column instead of across a row** reddens 20; the bottom fill drawing into the **top row pointer**
reddens 10; its map row **nine strides down instead of ten** reddens 10; the pre-shift **rotating
right** reddens 15; **carrying into the next cell** reddens 15; **dropping the row's wrap-around
carry** reddens 15; **chaining by the phase stride** reddens 15; picking its source on the
**longword's sign** reddens 7; a vertical serve **leaving its request raised** reddens 6; the dispatch
pass serving the **horizontal pair first** reddens 1; the raiser testing the **wrapped difference**
reddens 1; the queue draining the **vertical axis first** reddens 2; **not halving** the distances
reddens 2; and clearing the raised pair **as a word** reddens 2. **21 mutations, 21 killed, 0
survivors.**

**The three that redden 1 or 2 are one-case-per-claim, not thin pins.** Only `all-four` can see the
dispatch ORDER, only `wrapped-at-the-lowest-position` reaches the overflow branch, and only the
two-step queue cases can see which axis drains first — the same shape batch 2's note records. Each is
the case written for that claim, and each dies.

**One kit file moved, and it is the registered trigger firing.** `rotate_left32` was duplicated
between `src/hud.c` (constant counts, no zero guard) and `src/scroll.c` (a runtime count, guarded);
batch 5 recorded that a third user would collapse them. The pre-shift's `rol.l #2` is that third user,
so the guarded form now lives in `tools/recreate_kit/include/machine.h` and both files call it. It
masks the count to five bits before the zero guard, which is the 68000's register form exactly
(`rol.l Dm,Dn` rotates by `Dm mod 64`, and a 32-bit rotate is cyclic mod 32, so mod 64 and mod 32
give the same value) — total for every count instead of undefined above 31 — and costs a
constant-count caller nothing after inlining. Being a kit file, it lands as its own commit ahead of
this batch.

**What is NOT pinned, both by construction:**

* **The registers the routines leave behind**, except the two row fills' `d0` — which IS an output,
  read by `bg_scroll_preshift_rows`, and compared on both sides in every case.
* **The runaway counts, which are TWO different unreachability arguments.** Every `dbf` here takes its
  length from a split table whose first words count down to 0, so a negative one runs `count + 1`
  passes — 32,769 to 65,536 — rather than none; that is out of reach of the game's own data, because
  the tables are the shipped image's and a case that rewrote one would be pinning an invented record.
  `bg_scroll_run_queue`'s two drains are a `while` rather than a `dbf`, so a negative count runs its
  own VALUE in passes, 32,768 to 65,535 — and their count is a halved distance, not a table entry.
  `$d28` can return one: the `wrapped-at-the-lowest-position` case in this very battery makes it
  return $8030, which halves to $c018, i.e. 49,176 passes. What keeps the drains unreached is
  therefore the range of the game's own follow positions, which this batch did not establish — NOT
  the range of what `$d28` can return. Both shapes are reproduced by construction (`uint16_t`
  counters, do/while and `while` loops) and left unreached.

**Deferred, deliberately: `subsystems.tsv` still calls this cluster "game logic".** Its
`video (background scroll)` range is `$82f8..$8dfe` — the blit that CONSUMES these buffers — while
`$7522..$8228` and `$d28` fall into the catch-all. Both are now known to be the same subsystem, but
re-drawing the boundary moves every figure in [`PORTABILITY.md`](PORTABILITY.md), which is a
measurement to re-run rather than a line to edit. Left as it is, and recorded here.
**CLOSED 2026-08-02 by the re-measure at the end of this file** — both ranges are
`video (background scroll)` now.

### The consumer tier (batch 7): the blit, and sixteen routines that are one routine

Seventeen routines, 2,742 bytes, into the same `src/scroll.c`. With batches 5 and 6 that is the
**whole** background-scroll story — `$7522..$8228` and `$d28` produce the eight pre-shifted buffers,
`$82f8..$8dfe` consumes one of them — 33 routines and 6,140 bytes, with nothing between `$7522` and
`$8dfe` left named-but-unported and nothing STOPPED.

**THE SIXTEEN VARIANTS ARE ONE ROUTINE WITH ONE NUMBER IN IT, AND THAT IS THE BATCH'S FINDING.**
`$83b6..$8dfe` is sixteen unrolled copy routines a jump table names. They are byte-identical apart
from where each splits its thirty `move.l (a0)+,(a1)+` about the source row's 128-byte ring seam,
which is exactly what `bg_scroll_x` says: column 0 and 1 need no split at all (30 longwords from
`8 * x` still fit the 32 a row holds), and every other column copies `32 - 2x` longwords, rewinds a
whole row with `lea -128(a0),a0`, and copies the remaining `2x - 2`. That is why two bodies are 154
bytes and fourteen are 166 — the twelve being the two extra `lea`s each of a variant's two halves
costs. So `src/scroll.c` reconstructs all sixteen as ONE function taking the column as an argument,
and the table collapses into that argument.

**THE REGULARITY IS TESTED, NOT ASSUMED, AND IN THREE INDEPENDENT WAYS.** A parametrised pattern
that was wrong in the same way sixteen times would pass sixteen pins built from it, so:

* every variant's WHOLE body is assembled from the pattern and pinned against the image, and its
  length against the size `../out/hw_scan.tsv` records (154, 154, then fourteen 166s);
* **three of them are pinned a second time against bytes transcribed straight out of
  `../out/wonderboy_dis.txt`** — `x0` (no seam), `x2` (the first that needs one) and `x15` (whose
  seam is at the other end). These are what fix the pattern itself — and they are TRANSCRIBED rather
  than computed for a concrete reason: a hand-computed `dbf` displacement for `x2` and `x15` came out
  two short, and reading the bytes off the image is what settled it;
* the sixteen table entries, the sixteen lengths and the gaps between them are asserted to tile
  `$83b6..$8dfe` exactly, and a whole-image `abs.l` scan requires each variant address to occur
  **exactly once** — in its own table entry — and the table itself exactly once, inside
  `bg_scroll_blit`'s body. So the table is the only way in and `$832e`'s `lea` its only reader.

**`bpl` READS N ALONE, AND THAT IS THE OTHER HALF OF BATCH 6'S FINDING.** The dispatcher decides
whether the window runs off the buffer's end with `subi.w #$10,d6 / bpl`, which looks like the
`subi.w`/`bgt` pair batch 6 got wrong. It is not the same: `bgt`/`blt` read `N xor V` and `bpl`/`bmi`
read `N`, so here the wrapped difference's own sign really *is* the test, and the reconstruction says
so. The two readings — the wrapped sign, and a comparison of the row against the boundary — agree on
every ring row the game can produce and part company from `$8010` up. Most of that range is
unrunnable, because the same word feeds `move.w #$b0,d7 / sub.w`: a row of `$8010` asks for 32,928
scanlines and walks off the image. **A row of `$fffe` does not**, and the case that seeds it copies
160 scanlines where the boundary reading would copy 178 — which is what turned the sweep's one
survivor into a kill.

**THE DIFFERENTIAL ENTERS BOTH WAYS, because either alone leaves half the mechanism unpinned.** A
case entered at `$82f8` runs the dispatcher AND the variant its `jmp (a2)` reaches, so the table is
exercised as the game exercises it; a case entered at a VARIANT supplies the four registers the
dispatcher would have (a0 = source, a1 = destination, d7 and d6 the two `dbf` counts) and pins that
body on its own, four scanlines to the buffer's end plus two past the rewind. Both kinds seed all
eight source buffers AND both screen buffers, address-keyed with the same salt, so a copy that ran
one scanline long, chained by the wrong stride or read the wrong buffer lands on bytes that are
wrong *for where they were written* rather than on zeros.

**ONE CORRECTION TO `../names.txt`, from re-reading the dispatcher.** Its `cmt` (and the block
comment above it) said the blit "enters [the variant] twice, once per side of the source buffer's
vertical wrap, through the `jmp (a2)` at `$8350`/`$8364`". It does not. Those two jumps are the two
ARMS of the `bpl` — one loading `d6 = $ffff` outright (the window fits: no second half) and the other
computing both counts from the ring row — and exactly one of them executes per call. The vertical
split happens INSIDE the variant, at its own `tst.w d6 / bpl / rts`. Both texts are rewritten.

**Every one of the seventeen entry pins is the routine's WHOLE BODY.** The dispatcher's 110 bytes end
at `jmp (a2)`, which is its only exit and the reason it has no `rts`; the table begins in the very
next word, which the pin asserts. The three shifts in it are spelt as the constants they scale BY
rather than as the counts in the opcodes (`_shift_for`), so a header constant that moved fails the
pin instead of quietly disagreeing with it.

Mutation-checked rather than assumed (each rebuilt with the `.so` deleted first, and the source
restored and byte-compared against a pristine copy afterwards — 1023 green each time, and the whole
sweep re-run against the tree as it LANDED rather than against the draft it was written on; the
batch's review then added the 1024th case, a static image scan that runs no reconstructed code and
so moves no figure here): the
scanline **never split at the seam** reddens 25; the seam rewind **one cell instead of one row**
reddens 25; a wrapping scanline **not re-advanced past the row it rewound** reddens 25; the
destination stepped **a whole screen line instead of the gap** reddens 32; the seam placed **one cell
per column instead of one longword pair** reddens 25; a half running **its count instead of its count
plus one** reddens 32; the second half rewound **one row instead of one buffer** reddens 23; the
no-second-half marker read as **a zero test** reddens 9; the ring row scaled by **a cell instead of a
scanline** reddens 10; the phase scaled by **a whole buffer instead of half of one** reddens 10; the
two halves' counts **swapped** reddens 8; the first half **one scanline long** reddens 8; the window's
origin within the screen **dropped** reddens 12; the variant picked by **the phase instead of the
column** reddens 10; and the wrap test made **an unsigned comparison of the row against the boundary**
reddens 1. **15 mutations, 15 killed, 0 survivors.**

**That last one reddens 1 because it is one-case-per-claim, and it is the batch's coverage finding.**
On the first sweep it was the only SURVIVOR: nothing in the battery could tell the wrapped-sign
reading from the boundary one, because the two agree on every row the game produces. The `$fffe`
case above is what closes it, and it is recorded this way round because that is how the case came to
exist — the sweep found the hole and the case was written for it, rather than the other way about.

**What is NOT pinned, and why:**

* **A COLUMN OUTSIDE 0..15.** `movea.l (0,a2,d1.w),a2` bounds nothing, so the original would jump
  through the longword after the table — which is `bg_scroll_x` itself. C has no such behaviour to
  reproduce and `bg_scroll_copy_column` is undefined there. The domain is established instead rather
  than asserted, and by a case rather than by prose: a whole-image `abs.l` scan
  (`test_the_column_is_a_nibble_wherever_the_image_writes_it`) gives `bg_scroll_x` exactly three
  writing sites — a `subq.w #1` and an `addq.w #1`, each immediately followed by its OWN
  `andi.w #$f`, and the `clr.w` at `$fb7e`.
* **THE REGISTERS THE COPY LEAVES BEHIND.** It walks out with a0/a1 far past where they started and
  its one call site `rts`s immediately, so there is nothing to compare against — the same family as
  the column fills'.
* **THE 65536-ITERATION `dbf`.** Each half's count is a `dbf`, so a negative one would run 65,536
  scanlines. Reproduced by construction (`uint16_t`, do/while) and out of reach through
  `bg_scroll_blit`, whose two counts provably sum to the window's 160 scanlines for every ring row
  the vertical steps can produce — asserted over all 88 of them.

**`$8dfe` IS QUEUED, NOT SKIPPED.** `game_main_loop` calls it immediately before `bg_scroll_run_queue`
and it is 104 bytes with the same "read a position, subtract the scroll" shape as `$8e66` just after
it — but it opens `jsr $67e0.w`, a callee this reconstruction does not have, so its closure is not
satisfied and it is not in this batch. It is a `$67e0` batch, not a scroll one. **CLOSED by batch 8**,
which ported `$67e0`, `$8dfe` and `$8e66` together — and the reading was right about more than it
knew: `$8dfe` writes `scroll_follow_x`, i.e. the very word this batch's `bg_scroll_raise_requests`
steers on, because that word is screen record 12 of `$8e66`'s array.

**Still deferred, and now more visibly: `subsystems.tsv` calls the ENGINE "game logic".** Its
`video (background scroll)` range is `$82f8..$8dfe` — exactly this batch — while `$7522..$8228` and
`$d28` fall into the catch-all. Both are now reconstructed, so the boundary is measurably wrong in a
way that flatters neither side; re-drawing it moves every figure in [`PORTABILITY.md`](PORTABILITY.md),
which is a measurement to re-run rather than a line to edit. Left as it is, and recorded here.
**QUEUED, alongside the `$67e0` batch above: re-draw `subsystems.tsv`'s game-logic/video boundary and
re-run `tools/hw_portability.py` over it, then restate `PORTABILITY.md` from what it prints** —
trigger: now that `$7522..$8dfe` is closed, the game-logic/video split is measurably wrong.
**CLOSED 2026-08-02** — the re-measure is the last section of this file; background scroll went
17 functions / 2,742 B to **33 / 6,140 B**, and game logic 138 / 14,028 B to **114 / 9,596 B**.

### The actor tier and the text plotter (batch 8): the queued small tiers, cleared

Seven routines, 582 bytes, in two new files. `src/actor.c` takes the five-routine cluster batch 7
queued as "a `$67e0` batch, not a scroll one"; `src/text.c` takes the two-entry-point plotter batch
2 registered as "named and NOT ported, because porting it means porting `$bf5e` with it". Both
queue entries are closed.

**WHAT `$67e0` TURNED OUT TO BE, AND IT IS THE BATCH'S FINDING.** The scan calls it a 24-byte leaf
with fifteen callers and nothing else. Reading it, and then the four routines above it, gives a
whole subsystem: the game keeps its moving objects as **nineteen 32-byte records in one of three
parallel tables** (`$996c` / `$9bd0` / `$9e34`) that two mode flags pick between, and once a frame
it projects the chosen table into a parallel array of **nineteen SIX-byte screen records** at
`$98ec` — map position minus the scroll, plus the sprite to draw. `$67e0` returns **slot 12** of
that table (`$9aec` == `$996c + 12 * 32`, `$9fb4` == `$9e34 + 12 * 32`), and slot 12 of the screen
array **is `$9934`** — `scroll_follow_x`, which `bg_scroll_raise_requests` already steers the camera
by. So "the followed object", which batch 5 could only read off the scroll's own arithmetic, is
slot 12 of the actor table, and `$8dfe` exists to refresh exactly that one record in
`game_main_loop` immediately BEFORE `bg_scroll_run_queue` reads it. The arithmetic is a case
(`test_the_scrolls_follow_words_are_screen_record_twelve`), not a remark.

**THE SAME FLAG IS READ TWO DIFFERENT WAYS AND BOTH READINGS ARE KEPT.** `$67e0` tests
`state_flag_a32` with `bne`; `$8e66` tests the same word with `bpl`. `../names.txt` records that
the image only ever writes it `$0000` or `$ffff`, so **the game cannot tell the two apart** — a
small positive word is the only input that does, and there is one per routine
(`SELECTOR_CASES`' `one` / `largest-positive`, `FOLLOWED_CASES`' `a32-small-positive`,
`LIST_CASES`' `a32-small-positive`). Without them the mutation "read the sign instead of nonzero"
survives; with them it reddens 3.

**`$8dfe`'s GATE IS WHAT KEEPS THE TIER CONSISTENT.** `$67e0` has no `$a30` form: in that mode
`$8e66` projects `$9bd0`, whose slot 12 is an address `$67e0` never returns. `$8dfe`'s
`tst.w $a30.w / bpl / rts` is what stops it refreshing slot 12 from the wrong table — and `bpl`
reads N alone, so a positive `$a30` runs the body where a `bne` would return. That is the batch's
one-case-per-claim mutation: reading the gate as a zero test reddens exactly 1.

**THE TWO PROJECTION PASSES ARE ONE BLOCK.** `$8dfe`'s `$8e20..$8e64` and `$8e66`'s
`$8eb4..$8ef8` are the same SIXTY-EIGHT BYTES, so `src/actor.c` reconstructs them as one
`project_actor` helper and the two entry pins are built from one `_projection_block()`. That the
two really are byte-identical is a case of its own
(`test_the_projection_is_one_block_the_two_passes_share`), for batch 7's reason: a pattern that was
wrong in the same way twice would pass two pins built from it.

**THE TEXT TIER TURNED OUT TO BE ONE ROUTINE WITH TWO ENTRY POINTS, AND `$bd8a` EXPLAINS THE 88.**
`$bf4e` has no `rts`: four instructions turn a character code into a glyph pointer and it FALLS
THROUGH into `$bf5e`, whose `rts` returns to `$bf4e`'s caller. So the C is a prelude that CALLS the
plotter and returns its result — exactly what the fall-through is — and `$bf5e` keeps a name of its
own because eight `bsr` sites enter it directly with a pointer they already hold. `../names.txt`
recorded the plotter's 88-byte row advance as "NOT a 160-byte scanline — unexplained, do not assume
a screen buffer". It is now explained: the destination is the off-screen message buffer at `$c03a`,
**88 bytes wide and 6400 long, ending exactly at `panel_restore_dirty_regions` (`$d93a`)**, which
`$bd8a` clears, composes into, and then blits to `screen_back` 88 bytes plus a 72-byte skip per
scanline — 88 + 72 being the screen's own 160. Both halves are cases
(`test_the_row_advance_is_the_buffers_line_and_not_the_screens`), and the `cmt` on `$bf5e` is
rewritten. The returned cursor's `+1` / `+7` alternation is the other half of the same geometry:
two 8-pixel cells share each 8-byte plane group.

**THE EIGHT `$be2a..$be9a` CALLERS ARE NOT A TIER — THEY ARE ONE FUNCTION.** The batch was scoped
to consider them next; a whole-image scan says all eight `bsr` sites, and the ninth into `$bf4e`,
lie INSIDE `$bd8a`, a single 452-byte routine. It is named
(`text_compose_message_box`, from a read of its body) and **QUEUED, not skipped** — see below.

**ONE NAME CORRECTED.** `$bf4e` was `text_glyph_source_from_d0`, which describes the prelude alone;
now that the prelude and the plotter are reconstructed as what the fall-through makes them, it is
`text_plot_char`. Its `cmt` is rewritten and the "NOT reconstructed" caveat replaced by the three
semantics the port keeps: the `subi` is a BYTE op, the `lsl` a LONGWORD one, and the index is the
low WORD SIGN-EXTENDED. Only the last is unreachable from the game, whose one caller enters with
`moveq #0,d0 / move.b (a6)+,d0`; a case reaches it with a `d0` that indexes below the font and
stays inside the image.

**FOUR `proto` LINES WERE NOT WRITTEN, DELIBERATELY.** `ApplyNames`' `proto` forces a VOID return,
so a directive on `followed_actor_record` (whose whole result is a1), `actor_followed_x_within`
(d0 in and out), `text_plot_glyph` or `text_plot_char` (a1 in and out) would record something
false — `hud_blit_meter_cell`'s reason, one tier on. Each carries its register map in its `cmt`
instead. `actor_set_side_flag` is the one routine here that really returns nothing, and it has one.

**Two kit/test hoists this batch's third users triggered**, both of them registered above rather
than invented here:

* **`set_low_word` is now `tools/recreate_kit/include/machine.h`'s**, beside `set_low_byte`.
  `actor_followed_x_within` returns d0 with only its low word written, which was the registered
  third user (`src/scroll.c` and joust's `recreate/src/object.c` were the first two); both now call
  the kit's. Being a kit file touching three projects it lands as its own commit ahead of the
  batch, exactly as `rotate_left32` did — **BuggyBoy (292) and Joust (4368) were re-run green
  against it**.
* **Seven helpers are now `test/leaf.py`'s.** Two new batteries needing the same pieces made each
  of them a third user, and all three batteries import them rather than restating them:
  `opcode()` and `lea_abs_l()` (the encoders every pin spells), `lea_d16()` (likewise — the only
  other encoder all three batteries needed), `keyed_byte()` and `case_salt()` (address-keyed
  seeding and its reproducible per-case salt, with the two mixing multipliers named where they
  live), and `program_writes()` and `merge_bands()` (the oracle's write set minus the machine
  stack, and the bands `leaf.run` wants). `test_scroll.py`'s local copies are deleted and it
  imports them (its `branch_w(opcode, …)` parameter, which shadowed the new name, is now
  `condition`); the shared `merge_bands()` sorts internally, so the `sorted()` its callers used to
  wrap the argument in is gone.
  **What deliberately stays local, and why:** every battery's own OPCODES (`tst_w_abs_w`,
  `lea_indexed`, `subi_b_dn`, …), for batch 7's stated reason — that is where the batteries differ,
  and a shared 68000 assembler is not what this is. And `_keyed_block()`, the one-line
  `bytes(keyed_byte(…))` wrapper, which `test_scroll.py` and `test_actor.py` each still spell:
  **registered** on the same terms as the two hoists above — **trigger** = a third user; **home** =
  `test/leaf.py`, beside `keyed_byte()`. The two copies carry different docstrings (the scroll one
  records a measured no-caching decision), which is the only reason it was not folded in here.

Mutation-checked rather than assumed (each rebuilt with the `.so` DELETED first, since a
same-second rebuild otherwise re-runs the stale library, and each source restored and byte-compared
against a pristine copy afterwards, and the whole sweep re-run against the tree as it
LANDED rather than against the draft it was written on — 1193 green each time it was restored): the selector reading the
flag's **sign instead of nonzero** reddens 3; the side flag raised on **equal** as well reddens 4;
the side flag moved to **bit 4** reddens 37; the reach test's ADD **not wrapping to 16 bits**
reddens 4; the reach test returning **a whole longword instead of a low word** reddens 13; the
projection using the **Y bias horizontally** reddens 27; the flicker arm needing **either condition
instead of both** reddens 18; the followed projection's gate read as **a zero test** reddens 1; the
list pass testing **a32 before a30** reddens 2; the list pass stepping the screen cursor by **an
actor record** reddens 16; the plotter stepping **a SCREEN scanline** between rows reddens 45; the
plotter's four plane bytes made **contiguous** reddens 45; the two cell advances **swapped** reddens
45; the character subtraction made **a longword one** reddens 2; and the glyph index **not
sign-extended** reddens 2. **16 mutations, 15 killed, 1 survivor.**

**The survivor is an EQUIVALENCE, and it is now stated as one.** `$bf5e` reads the parity of the
cursor its eight rows ENDED on; reading the STARTING cursor's instead survives, because the body
spans 622 bytes and 622 is even. `src/text.c` keeps the original's reading and
`test_the_parity_the_tail_reads_is_the_starting_cursors_own` asserts the evenness that makes the two
the same bit — so the day a geometry constant turns the span odd, the equivalence fails loudly
instead of the port quietly diverging.

**What this batch does NOT pin:**

* **THE REGISTERS THE TWO PROJECTIONS LEAVE BEHIND.** Both walk out with a0 one record past the
  last one they read and a1 at the end of what they wrote; `game_main_loop` reloads everything
  before its next `jsr`, so the C returns neither and the cases assert the ORACLE's against the
  model. The same family as the column fills'.
* **d7, WHICH THE PLOTTER CLOBBERS.** It parks the ended cursor there for the `btst`. The kit's
  oracle reports d0/d1/a0/a1 only, so no case can compare it; no caller reads it either.
* **A GLYPH POINTER OUTSIDE THE IMAGE.** `text_plot_char`'s sign-extended index can name a source
  far below the font. The case that reaches that arithmetic keeps the source inside the image;
  off-image is `src/rad.c`'s registered divergence class (the shim answers zeros, the C indexes a
  host buffer) and bounding it would be a kit change.
* **WHAT THE TWO MODE FLAGS SELECT.** `../names.txt` names each for its mechanism and nothing more:
  `$a30` has ten operand sites — five writers of `$0000`/`$ffff` (three `move.w #$ffff` at `$1ae6`,
  `$1e96`, `$e0d0` and two `clr.w`) against five bare `tst.w` readers (`$4ec`, `$8dfe`, `$8e66`,
  `$dbc0`, `$ff42`) — and `$a32` has sixteen: three writers against thirteen bare `tst.w` readers.
  That one of the three actor tables is "this level's actors" is not established.

**QUEUED, and it is the tier directly above this one: `$bd8a` (`text_compose_message_box`, 452
bytes).** Its closure is satisfied now — both plotter entry points are reconstructed and it calls
nothing else — but it is not small, and it reads the TEN bytes at `$c030..$c039`: four BYTE fields
(`$c030`/`$c031`, the two flags it runs on, and `$c032`/`$c033`, its two cell counts) and three
WORDS (`$c034`/`$c036`/`$c038`, its timers). That band is `WB_TEXT_STATE_BYTES`, which this batch
pins only by its EXTENT — what the fields mean, and the message-pointer table at `$a09c` that
`$bd8a` indexes, are not read. Its one caller is `game_main_loop`'s `jsr $bd8a.l` at `$4fc`.
**CLOSED by batch 9**, which ported it, read all seven state fields and the `$a09c` table — and
renamed it, because "compose" is one of its three arms.

### The message box (batch 9): the text subsystem, CLOSED end to end

One routine, 452 bytes, into the file batch 8 opened. It is the queue entry above, and closing it
closes the whole `$bd8a..$c030` block: **every routine in the text subsystem is now reconstructed,
its one caller is `game_main_loop`, and it calls nothing outside itself.**

**WHAT THE "COMPOSER" TURNED OUT TO BE, AND IT IS THE BATCH'S FINDING: A LIFECYCLE, NOT A DRAW.**
`$bd8a` runs once a frame and has THREE arms, picked by the two flag bytes:

1. **`text_request` nonzero** — a message id was posted since the last frame. `$ff` dismisses (clear
   both flags, draw nothing); otherwise the 1-based id indexes `text_message_table`, whose record
   gives the box's height and top scanline and then the string. The box is composed into
   `text_buffer` and **deliberately NOT blitted** — the arm `rts`s at `$bed0`, so the frame a
   message is requested on shows nothing.
2. **`text_request` zero and `text_box_active` nonzero** — tick the countdown and blit the
   **already-composed** buffer to `screen_back`. This is the arm that runs on every frame of a
   message's life but the first.
3. **both zero** — `rts` having written not one byte (a case of its own).

So `text_buffer` is a **CACHE, not a scratchpad**, and `$c032`/`$c033` exist to carry the composed
box's geometry from the one compose frame to every blit frame after it. That is also why the 6400
bytes are cleared and redrawn only on a request: composing costs ~16,000 instructions, blitting
~1,800. `../names.txt` renames the routine `text_run_message_box` for it — the same correction batch
8 made to `text_glyph_source_from_d0`, and for the same reason: the old name described one arm.

**THE TABLE AT `$a09c` IS SELF-BOUNDING, AND NOTHING ELSE COULD HAVE BOUNDED IT.** A whole-image
scan finds **exactly one** reference to `$a09c` — the routine's own `lea` — so no count is declared
anywhere. The shipped data gives it three ways over, and all three are cases
(`test_the_message_table_is_bounded_by_its_own_data`): pointer 0 names `$a270`, the first byte PAST
the 117-pointer block; every record ends exactly where the next begins; and the last ends at
`$b346`, which is `panel_refresh_frame`. A count one too small would leave a gap before that
routine, one too large would read a "pointer" out of a record's text. A record is
`{byte height in cell rows, byte top scanline, string}`, `$0a` newline and `$ff` terminator — the
same shape as batch 5's split tables, established from the reader's own walk.

**`$c036` IS A ONE-WAY LATCH, AND THE SCAN IS WHAT SAYS SO.** `text_lifetime_armed` has **exactly
two** operand sites in the whole image, both inside `$bd8a`: the `move.w #$ffff` that sets it and
the `tst.w` that reads it. Nothing ever clears it. So after the first message that posted a
lifetime, every later box decrements `text_lifetime_left` each frame whether or not it asked for
one — and since only an EXACT zero takes the box down, a box composed with no lifetime under an
armed latch counts down from whatever the previous message left and usually wraps past zero rather
than landing on it. Both of those phases are seeded cases (`no-lifetime-already-armed`,
`armed-and-wrapping-past-zero`), and both are **live gameplay states, not dead branches** — the
paragraph above is the argument that the game reaches them. What no shipped **record** encodes is a
lifetime: it is posted by a caller alongside `text_request`, so the phases arise from the state
history rather than from any record's data. That is exactly why seeding them is legitimate — the
cases poke the ten bytes of plain RAM the arm reads, which is a reading of the instructions, and no
record is fabricated.
`$c032`, `$c033` and `$c038` have no site outside `$bd8a` either.

**THE FRAME IS 22 CELLS WIDE, ALWAYS, AND THAT IS WHAT EXPLAINS THE BUFFER'S 88.** A corner, twenty
`move.w #$13,d0 / dbf` edges and a corner is `WB_TEXT_BOX_CELLS` = the whole `WB_TEXT_BUFFER_LINE`;
the blit moves exactly `WB_TEXT_BLIT_LONGWORDS` = the same 88 bytes. Only the HEIGHT varies, from
`$c032`. Every one of the composer's step constants is that same geometry from another side — 616 is
a cell row less a buffer line, 80 is the interior in cells, 704 is eight buffer lines — so
`test_the_boxs_geometry_constants_are_one_set_of_numbers` asserts each against the others rather
than transcribing them.

**THE SHIPPED DATA OVERRUNS THE FRAME, AND THE CODE LETS IT.** Nothing clamps a text line to the
twenty interior cells. Over all 117 records, heights run 3..9, top scanlines are only 50 or 60, and
line counts never exceed height minus 2 — but **message 113 has a 21-character line** that plots
over the frame's right edge. It is a case
(`test_exactly_one_shipped_message_overruns_the_frames_right_edge`) and a compose case, and it also
bounds the missing clamp: the overrun is exactly one cell, so every plot still lands inside the
buffer's own row.

**THE RUNAWAY THE SHIPPED TABLE CANNOT CAUSE.** `move.b $c032,d0 / subq.w #3,d0 / dbf` counts the
interior rows in a WORD, so a height below 3 would draw 65,536 rows and walk far past the buffer.
Reproduced by construction (`uint16_t`, do/while) and asserted unreachable over all 117 records —
the same family as the scroll's `dbf` counts.

Mutation-checked rather than assumed (each rebuilt with the `.so` DELETED first, and the source
restored and byte-compared against a pristine copy afterwards — 1242 green each time it was
restored): the two arms **swapped**, so an active box beats a new request, reddens 2; the **dismiss
arm dropped**, so `$ff` is an ordinary id, reddens 2; the countdown expiring on **`<= 0`** instead
of an exact zero reddens 2; the countdown **armed unconditionally** reddens 13; the expiring frame
**not drawn** reddens 2; **one interior row too many** reddens 25; the interior skip made a **whole
row advance** reddens 25; the text lines started at the buffer's **cell 0** reddens 25; the blit's
top line **not sign-extended** reddens 1; the blit's rows made **contiguous** reddens 10; and the
frame's bottom row drawn with the **top row's glyph triple** reddens 25. **13 mutations, 11 killed,
2 survivors.**

**Both survivors are EQUIVALENCES, and both are now stated as ones.**

* **The blit arm's `clr.b $c030`.** It opens an arm reached only when `text_request` is ALREADY
  zero, so the write changes no byte and dropping it from the reconstruction survives. The C keeps
  it, because it is a write the ORIGINAL makes and the cases state the oracle's write set exactly —
  the oracle making it is pinned even though the candidate omitting it cannot be.
  `test_the_blit_arms_request_clear_is_a_write_of_a_byte_already_zero` says so.
* **The order of the newline and terminator tests.** `$0a` and `$ff` are distinct, so no byte can
  take both branches and swapping the two `cmp.b`s is an equivalence for every input.
  `test_the_newline_and_the_terminator_cannot_be_the_same_byte` asserts the distinctness that makes
  it one, so the day the two constants meet it fails loudly.

**ONE MUTATION WAS A REAL HOLE AND IS NOW PINNED.** "The blit's top line is not sign-extended"
survived the first sweep: `mulu.w #$a0,d0` is a 32-bit product but `lea 48(a1,d0.w),a1` takes its
LOW WORD, sign-extended, and the shipped records only ask for 50 or 60 — neither reaches it.
`$c033` is not re-read from the record on that arm, though: it is plain RAM the blit reads, so a
case seeds it at 205 (the smallest top line that overflows the word) and the box lands BELOW
`screen_back` instead of far past it. That is the same move batch 8 made with the small-positive
mode flags, and it turns the survivor into 1 red.

**TWO COLLAPSES THIS BATCH'S THIRD USERS TRIGGERED, one per language.**

* **Thirteen more helpers are now `test/leaf.py`'s**, and `test_scroll.py` / `test_actor.py` /
  `test_text.py` import them instead of restating them. The encoders `tst.b`/`tst.w`/`clr.b`/`clr.w`/
  `st`/`subq.w` on an `<abs>.l`, `mulu.w #imm,Dn`, `movea.l <abs>.w,An`, `move.w #imm,Dn` and
  `moveq #0,Dn` — every one of them spelt in two files, and `move.w #imm,Dn` in three. The two
  branch assemblers went with them: `branch(condition, *over)` / `branch_over(condition, span)` and
  `dbf(reg, *body)` / `dbf_over(reg, body_bytes)`, which is where the drift actually was —
  `test_scroll.py` and `test_text.py` each had a `dbf` of its own with a DIFFERENT signature (one
  taking the pieces, the other their length), and the same forward branch was `branch_w` in one file
  and `_branch` in two others. Each shape now has one name, the pieces form and the length form named
  apart, so a call site says which it is. **The registered `_keyed_block` entry is CLOSED** —
  `test_text.py` was the third user batch 8 said would trigger it, and `keyed_block()` now lives once
  in `leaf.py` beside `keyed_byte()`, carrying the scroll copy's measured no-caching note. `moveq`
  kept the systematic `moveq_0_dn` spelling over `test_text.py`'s `moveq_zero`, matching
  `move_w_imm_dn` / `clr_w_dn` / `tst_w_dn`. The whole-body entry pins are the proof the hoist
  changed nothing: every routine in all three batteries still matches the shipped image byte for
  byte.
* **`copy_longwords` is shared between `src/scroll.c` and `src/text.c`**, declared in
  `include/scroll.h` and defined where it already was. The message box's blit row is the same run of
  `move.l (a0)+,(a1)+` the sixteen scroll copy variants spend their length on, down to the in/out
  cursors, so `text.c`'s inner loop and its `TEXT_LONGWORD_BYTES` are gone. It stays project-local
  rather than moving to the kit's `machine.h` because both users are this game: **registered** on the
  usual terms — **trigger** = a third user, in this project or another; **home** =
  `tools/recreate_kit/include/machine.h`, beside `addr_add` and `rotate_left32`.

**What this batch does NOT pin:**

* **WHAT `$bd8a` LEAVES IN d0/d1/a0/a1/d6/a6.** Each arm walks out with different rubbish — the
  terminator byte and the last glyph's source, or the blit's two ended cursors — and
  `game_main_loop` reloads everything before its next `jsr`. The C returns nothing; the cases assert
  the ORACLE's against the model where the arm defines them. The same family as the projections'.
* **THE ATTRIBUTION (POISON) PASS, ON THIS ROUTINE.** Every non-trivial arm WRITES `text_request`,
  so poisoning the oracle's outputs turns a zero request into `$ff` and both cores then take the
  DISMISS arm — the pass would agree, having tested the wrong arm. The driver's cases run with
  `poison=False` and replace it with an address-keyed destination, an EXACT write set and a model
  built from the game's own data. Registered here because it is a deviation from every other
  battery in this project.
* **AN ID PAST `WB_TEXT_MESSAGE_COUNT`.** `subi.b #$1,d0 / lsl.w #2,d0` indexes with a word, so ids
  118..256 read a "pointer" out of the record bytes and walk wherever it names. Fifty-two writers
  raise `$c030` and only their immediates are bounded (they top out at `$64`); the rest are
  `move.b d0` / `move.b (a0)` and nothing read here bounds them. Reaching it from a case means
  fabricating a pointer into a table the game ships, which is what CLAUDE.md's coverage rule
  refuses. Left honestly unpinned.
* **WHAT ANY GIVEN MESSAGE ID MEANS.** The 117 records are read as geometry and text; which game
  event raises which id is a property of the 52 writers, none of which this batch read.

### The actor table's lifecycle and the collision map (batch 10)

Ten routines, 748 bytes, in the file batch 8 opened and one new one. Seven are the actor table's own
LIFECYCLE (`src/actor.c`); three are the **collision map** the actors walk on, which is a subsystem
nothing before this batch had touched and so gets `src/map.c` and `include/map.h` of its own.

**THE TWO ALLOCATORS EXPLAIN SLOT 12, AND IT IS THE BATCH'S FINDING.** Batch 8 established that the
followed actor is slot `WB_ACTOR_FOLLOWED_SLOT` of the actor table by reading `$67e0`'s two
constants. From the other side: `$1b68` searches slots **3..11** of the published table for the
free marker and `$1b8e` searches **13..18**, and the two runs meet EXACTLY either side of slot 12.
So no allocation can ever hand out the record the scroll steers on — the followed actor's slot is
the one gap in the free list, and slots 0..2 are below both pools and equally reserved. The
arithmetic is a case (`test_the_pools_tile_the_table_around_the_followed_slot`), and one case per
pool plants a free record in the followed slot ALONE and requires both allocators to come back
empty-handed. The two bodies are byte-identical bar two operand words, so `src/actor.c` has ONE
`actor_alloc_slot(first, slots)` behind both names and both entry pins come out of one
`_alloc_entry(first, slots)` — batch 7's reason.

**AN ALLOCATION FAILURE IS NOT CHECKED, AND THE SPAWN WRITES THROUGH IT.** `$1b68` returns `$0` for
a full pool. Of its three call sites only `$101dc` tests it (`cmpa.l #$0,a1`); the two inside
`$ff42` hand it straight to `actor_spawn_from_template`, which writes through a1
unconditionally — over absolute `$0..$1f`, the 68000 vector page. Recorded in `../names.txt` on
`$1b68` as behaviour, not reproduced as a case: `$ffe4`'s a1 is its caller's argument, so a case
handing it `$0` would be testing the spawn at address zero rather than the pair's interaction —
which is `$ff42`'s to pin when that routine is ported. **BATCH 13 PORTED IT AND PINNED THIS, and
correcting "32 bytes" to EIGHTEEN was the pin's own finding** — see "The spawn pass and the two
resets" at the end of this file.

**THE COLLISION MAP IS A SECOND MAP WITH THE BACKGROUND MAP'S LAYOUT.** A word of bytes per row,
then one byte per 16x16 cell from base + 4 — the same +4 `WB_MAP_DATA_ROW` sits at above
`WB_MAP_ROW_STRIDE`, and `map_stamp_block`'s own `addi.w #$4` is a third spelling of it
(`test_the_cell_lookups_bias_is_the_background_maps_own`). `WB_STATE_FLAG_A32` picks between two of
them, the same flag that picks the actor table: `WB_COLLISION_MAP_A32` lies inside the .PRG (zero
below its stride word, filled at run time) and `WB_COLLISION_MAP_DEFAULT` past the program's last
byte, loaded from disk. Neither carries shipped data, so every case seeds a window of each
address-keyed and pokes the cells it means to test — plain RAM the game fills, not a fabricated
record.

**THE ONE PLACE THE PAIR OF MAPS IS NOT SYMMETRIC, AND IT IS REPRODUCED.** `$10a2` selects its map
with `tst.w $a32.w` for the CELL LOOKUP and then reads the row stride its ground test walks by from
`move.w $23494.l,d7` — `WB_COLLISION_MAP_DEFAULT`'s word, unconditionally. In the A32 mode the
"one row down" and "two rows down" cells are therefore taken at the OTHER map's pitch. The two
strides are seeded to DIFFERENT numbers in every case for exactly this reason, and
`test_the_ground_test_walks_by_the_default_maps_stride` plants blocks one and two A32 rows below the
cell and requires the tail to report open ground both times — a tidied port fails it.

**$13c8 WAS NAMED AND DELIBERATELY NOT PORTED, AND THE REASON WAS THE HARNESS — batch 11 below
closed it, together with the whole queue at the end of this section.** What this batch wrote at the
time, kept as written because the registration is the point:

**The five instructions
that turn an actor's pixel position into a cell pointer are a routine of their own, entered by
`bsr` at `$1344` and fallen into from `$13be`. It writes NO memory, so everything a case could
compare is in registers — and the kit's oracle reports d0/d1/a0/a1 only. **Two of those it does
leave**: d0 comes back as the probe's own column and d1 as its row, so the window is not shut
completely. But both are BY-PRODUCTS of the lookup. The routine's LOAD-BEARING output — the map it
selected, the cell pointer, the sub-cell and the span, in **a6, d2, d3 and d7** — is exactly what
the oracle does not report, and no caller reads d0 or d1. A reconstruction pinned on those two alone
would be a green function whose whole job is unchecked, so the stop decision stands. `src/map.c`
inlines the same block inside `actor_step_left_against_map`, where the write set makes it
observable, and `actor_settle_on_platform` takes a6/d7/d2 as arguments.

**And it is REGISTERED rather than argued each time, because it is the third thing this project has
stopped short of for OBSERVABILITY rather than for difficulty** — both of the others are batch 3's
(the status panel's second tier): `hud_plot_digit`'s outgoing `d7`, and the staged-field mutation
that survives only because the same window hides it. The usual terms: **trigger** = the kit's
oracle reporting the full `movem` register set instead of `d0`/`d1`/`a0`/`a1`; **home** =
`tools/recreate_kit`, in the oracle's own result dict. When it fires, all three are re-run against
it — `$13c8` becomes a reconstruction, `hud_plot_digit`'s `d7` becomes a per-case assert, and the
staged-field mutation should die (if it does not, that reading was wrong). **`$1334` in the queue
below hits the same wall from the tier above**: it is what supplies `$13c8`'s and `$1400`'s
register arguments, so porting it means either porting `$13c8` with it or reproducing that
hand-over unobserved.

**The trigger fired on 2026-08-04 and all three were re-run against it** — the widening is in
`tools/recreate_kit` (`TRAP_MODEL.md`, "What a run reports back") and the results are in "The oracle
window, and the tier it unblocked (batch 11)" at the end of this file. `$13c8` and `$13be` are
reconstructions, `hud_plot_digit`'s `d7` is a per-case assert, and the staged-field mutation died.

**THE PLATFORM IS AN ACTOR RECORD.** `$1400` lands a record on `platform_y` (`$9a6e`), a word with
exactly two operand sites in the whole image — both its own — and NO writer anywhere. It is
`actor_table_default + 8 * 32 + 2`, i.e. slot 8's own y, which
`test_the_platform_word_is_actor_slot_eights_own_y` states as arithmetic over the header's
constants. What puts an actor in slot 8 is not established and the name says only what the routine
does with it.

Mutation-checked rather than assumed (each rebuilt with the `.so` DELETED first, and each source
restored and byte-compared against a pristine copy afterwards — 1409 green each time it was
restored): the allocator pool starting at slot 0 reddens 7; walking one slot too many reddens 2; the
reset stamping the marker in the record's SECOND word reddens 3; the free run stopping one record
short reddens 10; the spawn's size index not masked to a word reddens 1; the terminal fall speed
read as a ceiling instead of an equality reddens 20; the launch leaving the supported bit alone
reddens 20; the ground test stepping by the map it WALKED reddens 1; the off-the-edge test read as a
zero test instead of a sign test reddens 1; the footprint scan comparing the span unsigned reddens
1; the landing band's top end made non-strict reddens 7; the stamp's row step not sign-extended
reddens 1; the step's result returned as the outcome byte alone reddens 2; the ground word returned
as the flags alone reddens 1; the sub-cell test skipping the extra cell one pixel early reddens 1;
and the retry loop clearing the player's byte for every record type reddens 4. **17 mutations, 16
killed, 1 survivor.**

**THREE OF THOSE REDS WERE HOLES THE FIRST SWEEP FOUND, AND THE THIRD WAS A CASE-GEOMETRY BUG.**
"the ground test steps by the map it walked", "the footprint scan compares the span unsigned" and
"the ground word is the flags alone" all SURVIVED the first sweep:

* **The asymmetry case was planting its tiles in the wrong column.** The probe lands at
  `(x - half_width - STEP) asr.w #4` and the case keyed its map pokes off `x - half_width` alone, so
  every tile it planted sat one cell away from where the routine looks — and the case passed on the
  seeded bytes that happened to be there instead. `probe_cell()` now computes the cell the first
  probe lands in and every `tiles` key is an offset from it. This is the batch's methodology
  finding: a differential case whose model is computed from the same image it seeds stays
  self-consistent while testing nothing, and only a mutation says so. Written up transferably in
  [`docs/methodology.md`](../../../docs/methodology.md), "The second seeding hole: a case keyed to
  the wrong place" — beside batch 4's margin hole, which does NOT catch this one.
* **The span comparison** needed a negative span that still LANDS: one that leaves the scan where it
  started and reaches the platform through the sub-cell test, where an unsigned reading walks 2,049
  cells first.
* **The ground word's high half** needed a row times a stride that overflows sixteen bits; every
  earlier case had a product under $10000, where dropping `set_low_word` is invisible.

**The one survivor is an EQUIVALENCE and is now stated as one.** The spawn's `asr.l #5` on the
template's byte offset differs from a logical shift only in the result's top five bits, and only the
LOW BYTE is stored — bits 5..12 of the difference either way. No input can tell them apart, and
`test_the_slot_bytes_signed_shift_is_an_equivalence_at_the_byte` asserts that over the boundary
values rather than leaving a red mutation unexplained.

**SIX ENCODERS AND THE TWO WORD READERS ARE NOW `test/leaf.py`'s**, on the registered third-user
terms: `lea_indexed`,
`move_w_ind_dn`, `move_w_abs_l_dn`, `tst_w_abs_w`, `subi_w_dn` and `sub_w_dn_dn` were each spelt in
TWO batteries already and this batch's are the third. `lea_indexed` is the interesting one — the
scroll's copy took a `longword_index` flag and the text plotter's took a `displacement`, and the map
probes need both, so the merged signature is what makes the three one spelling. `test_scroll.py`,
`test_text.py` and `test_actor.py` delete their copies and import them; the whole-body entry pins
are the proof the hoist changed nothing, since every routine in five batteries still matches the
shipped image byte for byte. `u16()` and `s16()` — how a Python model reads a word out of the image
and sign-extends it — went the same way for the same reason: `test_scroll.py`, `test_actor.py` and
this battery were three spellings of one sign extension, which is three places to get it wrong.

**What stays local is REGISTERED rather than argued:** `_put_word()` and `_assert_writes()` are
spelt identically in `test_actor.py` and here, which is TWO users — the line `_keyed_block` and
`copy_longwords` were both held at. Usual terms: **trigger** = a third user; **home** =
`test/leaf.py`, beside `program_writes()`, which `_assert_writes` is a stricter reading of. Plus
each battery's single-use encodings, for batch 7's stated reason.

**What this batch does NOT pin:**

* **THE REGISTERS THE LIFECYCLE ROUTINES WALK OUT WITH.** `actor_table_reset` leaves a0 one record
  past the last (asserted against the model, not pinned on the reconstruction) and d0 at `$ffff`;
  `actor_slots_mark_free` leaves a6 and d7 the same way; the spawn clobbers d0/d1. The same family
  as the projections'. Only `actor_accelerate_fall`'s d0 — the pre-increment speed byte — is
  asserted per case, and no caller reads any of them.
* **WHAT THE FLAG BITS AND TILE CODES MEAN.** `WB_ACTOR_FLAG_SUPPORTED_BIT` and
  `WB_ACTOR_FLAG_FALLING_BIT` are named for the routines that raise and clear them, and
  `WB_MAP_TILE_BLOCK`/`_LEDGE`/`_PLATFORM` for the tests that read them. Bits 0 and 1 of the flag
  byte are named `MOVING`/`LAUNCHED` from the one reader above them (`btst #0,8(a0)` at `$1376`) and
  no further.
* **WHAT `WB_RECORD_PTR_10420` POINTS AT.** The stamp reads two of its fields; nothing here bounds
  the record or says whether its twenty readers — fourteen `movea.l` sites and six that copy the
  pointer to its neighbour `$10424` — agree about its shape. (21 operand sites in all: those twenty
  and the single writer at `$163a`.)
* **`subsystems.tsv` STILL PUTS ALL TEN IN THE CATCH-ALL.** The collision map is a characterised
  subsystem now and the lifecycle belongs with `actor (table + projection)`, but re-drawing the
  boundary means re-running `tools/hw_portability.py` over the scan — a measurement, like the
  2026-08-02 re-measure below, and queued as one rather than half-done here.
  *(CLOSED by the 2026-08-05 re-measure at the end of this file: the collision map is its own
  subsystem, `map (collision + settle)`, and the lifecycle joined the actor one — which is renamed
  `actor (table + lifecycle)` because it is no longer just the table and the projections.)*

**QUEUED, with the names and evidence already in `../names.txt` — ALL FOUR CLEARED BY BATCH 11:**

* **`$1170` (`actor_step_right_against_map`, 152 bytes)** — `$10a2`'s mirror, the same head with
  both signs flipped, but its own tail reads `bg_scroll_limit_x` under `WB_STATE_FLAG_A32` rather
  than clamping at the actor's half-width, so it is not a parametrisation of the left one.
* **`$1492` (`actor_settle_on_tile_1_or_2`, 98 bytes)** — `$1400`'s sibling, walking the same
  footprint for tiles $1/$2. Its body ENCLOSES `actor_accelerate_fall` (`blt.w $14d6` at `$14c0`
  jumps into it), so porting it means deciding how to represent that overlap.
* **`$13be` + `$13c8` (66 bytes)** — named, and blocked on the oracle's register set as above.
* **`$1334` (138 bytes)** — the tier directly above the map probes: it calls `$13c8`, `$14d6`,
  `$13be` twice and falls into `$1400` by `bra.w`, and it is what supplies their register
  arguments.

### The portability re-measure (2026-08-02): the boundary the campaign proved wrong

The queue entries batches 6 and 7 left open, closed together. No code changed and no test moved —
`make test` is 1242 green before and after — because this is a **measurement**, not a
reconstruction: `subsystems.tsv` was re-drawn and `tools/hw_portability.py` re-run over the same
`../out/hw_scan.tsv`. [`PORTABILITY.md`](PORTABILITY.md) §0 records it in full.

**What moved.** Five ranges left the "game logic" catch-all, each on evidence a batch established
and each cited in `subsystems.tsv` itself: `$7522..$8228` and `$d28..$d76` (the scroll ENGINE, to
join its consumer under `video (background scroll)`), `$67c2..$6822` and `$8dfe..$8f02` (a new
`actor (table + projection)`), and `$bd8a..$c030` (a new `text (message box)`). The exact `hi` of
each is the `body_end` the scan records for its last function, so the ranges tile and no entry is
claimed twice. The `$a09c` message table is deliberately NOT in the file: ranges match a function
ENTRY, and that is data.

| | before | after |
|---|---|---|
| game logic | 138 fns / 14,028 B measured, 36.0 % of 38,942 B CODE | **114 / 9,596 B, 27.8 % of 34,496 B** |
| video (background scroll) | 17 / 2,742 B, 97.2 % | **33 / 6,140 B, 98.5 %** |
| text (message box) | — | **3 / 678 B, 100.0 %** |
| actor (table + projection) | — | **5 / 356 B, 100.0 %** |
| game logic, runnable end-to-end | 128 / 12,070 B | **104 / 7,638 B** |
| game logic, ported and green | 51 fns | **61 / 2,986 B** |

**Every whole-program figure is unchanged** — 220/252 functions and 21,534/25,696 bytes runnable,
83.8 % of what is measured and 39.3 % of believed code, 28 functions / 3,348 B at false-green risk,
and both tier tables byte-identical. A subsystem partition relabels the same 252 functions; the two
reports differ in exactly four rows, which was checked by diffing them rather than argued.

**THE CATCH-ALL GOT WORSE, AND THAT IS THE FINDING.** Carving three characterised subsystems out of
"game logic" was expected to leave a smaller, better-understood remainder. It did the opposite: the
bucket lost 4,432 **measured** bytes and only 14 unmeasured ones, so its coverage fell from 36.0 %
to 27.8 % and the CODE it holds outside every function body is now 72.2 % of it. What the catch-all
was hiding was not confusion — it was the three best-measured subsystems in it.

**THE REPORT CAN NOW SAY "GREEN", NOT ONLY "RUNNABLE".** The campaign created a fact the original
measurement had no column for: **105 functions / 10,376 bytes are reconstructed and pinned by a
differential** — 40.4 % of what is measured, 18.9 % of believed code, and 48.2 % of everything the
harness can run at all. `PORTABILITY.md`'s coverage table carries it as a column now. It reads 105
where this file's header reads 103, and the difference is a counting rule, not a disagreement:
`src/rad.c` is one reconstruction of what Ghidra splits into three functions.

**The limitation to state with it: the Ghidra DB is stale.** Batches 5–9's names, `cmt`s and
`proto`s have not been through `../reapply.sh`, and the DB still wants the re-bootstrap the
`PrgLoader` defect forced. **It affects no figure here, and that was checked rather than assumed**:
all 171 `fn` addresses in `../names.txt` are already `F` records in the scan, so naming since the
scan created no function body the scan lacks, and every column is keyed on addresses and body
extents. A re-scan would change only the name strings (`FUN_00007522` where `../names.txt` now says
`bg_scroll_run_queue`). The 29,158 bytes in no function body are untouched by any of this — 24,900
of them are now charged to game logic.

### The oracle window, and the tier it unblocked (batch 11)

**A REGISTERED TRIGGER FIRED, AND IT WAS A KIT CHANGE RATHER THAN A READ.** Three times this project
had stopped short of a reconstruction for OBSERVABILITY rather than for difficulty — `hud_plot_digit`'s
outgoing `d7` and the staged-field mutation (batch 3, the status panel's second tier) and `$13c8`
(batch 10) — and all three were registered on the same terms: **trigger** = the kit's oracle
reporting the full `movem` register set instead of `d0`/`d1`/`a0`/`a1`; **home** = `tools/recreate_kit`,
in the oracle's own result dict. The window was never chosen: `d0`/`d1`/`a0`/`a1` are what a
Ghidra-style calling convention returns in, inherited from the first function ported. It is now
`d0..d7` and `a0..a6` (`emu.REPORTED_REGS`), with **`a7` deliberately excluded** — the harness forces
it to `STACK_TOP` on entry and the run's own `rts` pops the sentinel frame back off it, so its final
value states the kit's convention rather than anything the function computed, and `min_a7` already
reports the one fact about it a case can use. The dict GREW and nothing indexes it positionally, so
no existing case in any project changed; that was checked rather than assumed, by re-running all
three suites with each candidate `.so` deleted first (**BuggyBoy 292, Joust 4368**, and the kit's own
131). `TRAP_MODEL.md`, "What a run reports back", is the decision's home, and
`tools/recreate_kit/test/test_reported_regs.py` pins it from C the way `test_entry_state.py` pins the
entry SR — a `movem` planting a distinct mark in every reported register, a second run leaving them
all at their entry values, a canary one slot past the set, and a textual pin of `emu.py`'s mirror
against `shim.c`, because the C fills the buffer and the Python allocates it.

**ALL THREE BLIND SPOTS ARE CLOSED, AND ONE OF THE THREE READINGS WAS WRONG IN AN INSTRUCTIVE WAY.**
The two status-panel entries are written up where they were registered (see the second tier's
mutation register above): `hud_plot_digit`'s `d7` is now a three-way per-case assert — model, oracle,
and the reconstruction's own out-parameter — and the staged-field mutation, which had survived all
651 cases, **reddens 6**. What batch 3 got wrong was not the pixels but the register: four `rol.l #4`
come to a `swap`, so the caller's buried half is back in `d7`'s HIGH word at the `rts`. It genuinely
never reaches a drawn nibble, which is why the memory differential could not see it — and it was
sitting in a register the oracle simply was not reporting. **The lesson is the one the registration
was designed to produce**: an unobservable is a property of the HARNESS, not of the code, and saying
so in writing with a trigger is what let it be discharged three batches later instead of hardening
into folklore.

**THE COLLISION MAP IS NOW EIGHT ROUTINES, AND BATCH 10's WHOLE QUEUE IS CLEARED.** 454 more bytes:
`$13be` + `$13c8` (the cell lookup and its prelude), `$1170` (the rightward probe), `$1492` (the
second settle) and `$1334` (the tier above all of them). `test/test_map.py` goes 58 → 167 cases.

* **`$13c8` writes no memory at all, so it is the batch's clearest demonstration of what the window
  is worth.** Every case states all six of its outputs — `a6` (the cell), `d2` (the sub-cell), `d3`
  (the row × stride product over the cell index), `d7` (the span) and the `d0`/`d1` coordinates —
  three ways, with the write set required to be EMPTY rather than merely bounded. Four semantics the
  inline copy inside `actor_step_left_against_map` could only half-show, because that routine clears
  or overwrites the registers carrying them: `mulu.w` is UNSIGNED (a row of `$ffff` multiplies as
  65,535, not as −1) and writes all 32 bits, so `d3`'s ENTRY value never survives at all; the `add.w`
  after it never carries into the product's high half; `lea 2(a6,d3.w)` sign-extends after the
  `(a6)+` has already stepped past the stride word, so an index past `$7fff` addresses BELOW the map;
  and every other write here is a WORD write into a longword register, so the ENTRY high halves of
  `d0`/`d1`/`d2`/`d7` come back untouched — which is exactly what `$13be`'s `moveq`/`move.l` pair
  exists to clear. **No second spelling of the arithmetic**: both routines go through the one
  `collision_map`/`cell_pointer`/`pixel_to_cell` trio the step probe already inlined, and the block
  stays inline there because that routine's write set is what makes it observable.
* **`$1170` IS NOT `$10a2` WITH A SIGN IN IT, AND THE PROOF IS THAT IT SHARES ONLY THE TAIL.** It has
  no `rts`: both exits `bra.w $111a`, thirteen instructions inside `$10a2`, and a whole-image scan
  finds exactly three branches there (`$1112`, `$11fc`, `$1204`) and no `bsr`/`jsr` — so the ground
  test is not a copy, and `src/map.c` now has one `map_ground_under_cell()` that both probes call.
  The left routine's cases stayed green through the extraction and its whole-body pin is
  byte-identical, which is what says the refactor changed nothing. The collision-map stride asymmetry
  comes with it: `$1170` branches INTO `move.w $23494.l,d7`, so its ground test walks at
  `WB_COLLISION_MAP_DEFAULT`'s pitch too, with a case per body seeding the two strides apart. What is
  NOT shared is the clear arm, and deliberately: `$10a2` tests the probe's own SIGN and parks at the
  half-width, while `$1170` builds a limit — `bg_scroll_limit_x + $f0`, or `$f0` ALONE under
  `WB_STATE_FLAG_A32`, that mode having no limit word (`$11b6` is a SECOND read of the same flag) —
  compares it against the UNSHIFTED probe and parks the actor's right EDGE on it. **`$f0` is not this
  routine's own number**: `$83b2` has three operand sites, and its one WRITER at `$fb1c` is preceded
  by `move.w (a0)+,d0 / lsl.w #4,d0 / subi.w #$f0,d0`, so `limit + $f0` recovers the level's width in
  pixels and `WB_BG_SCROLL_LIMIT_BIAS` is named for that pair rather than for a guess. **`d0` means
  three different things at the `rts`** — the probe's map column when the step ran out (`$11e4`), the
  clamp LIMIT when the compare committed the move (`$11d0`), and the PARKED x when the clamp fired
  (`$11f8`), where the byte is a literal `$0` rather than `d6`, so a first probe that was clear still
  reports blocked. Three cases are about nothing else.
* **`$1492`'s BODY ENCLOSES `actor_accelerate_fall`, AND THE ENCLOSURE IS REPRESENTED AS WHAT IT IS.**
  Those 32 bytes sit inside `$1492..$1513`, reached both by the `blt.w $14d6` at `$14c0` and by the
  not-taken `beq.w $14f6` at `$14d2` falling straight in, and that routine's `rts` at `$14f4` is one
  of `$1492`'s two exits. It is not two routines sharing bytes — it is a routine whose not-found arm
  IS another routine, so both arms are written as a call, the same way `$13be` is a prelude calling
  `$13c8` and `text_plot_char` falls into `text_plot_glyph`. The pin spans all **130** bytes and the
  size table asserts the RELATIONSHIP rather than a number — **130 = 98 + 32** — with the enclosed
  block tied to `actor_accelerate_fall`'s own address, length and bytes, so the pin cannot silently
  become a prefix and neither number can move alone. Against `$1400` it differs in more than a
  constant: it accepts a PAIR of tile codes at each of its three sites, parks the actor by MASKING
  its own y rather than on `platform_y`, and never touches `9(a0)` — the two settles accept disjoint
  code sets, and a case seeds `$23` under the whole footprint to say so.
* **`$1334`'s CLOSURE IS CLEAN BECAUSE ITS FIVE CALLEES ARE ALL RECONSTRUCTED, AND THAT WAS SCANNED
  RATHER THAN ASSUMED.** 138 bytes, **forty-six `bsr` callers** by whole-image scan where Ghidra's
  function table recorded four, no `jsr`/`jmp`/`bra` in, and four exits: its own two `rts`, `$1400`'s
  (it ends `bra.w $1400`) and — through `$1492` — `actor_accelerate_fall`'s. Its battery's model
  **composes**: the models of `$13c8`, `$13be`, `$1492`, `$1400` and `$14d6` run in the body's own
  order over one shared memory, which is the only way the two cell lookups take their row from the y
  the pass has just moved. That composition is what exposed **why `$13be` is called twice** —
  `$1492`'s scan CONSUMES `a6` and `d7`, so a port handing `$1400` what `$1492` left would start it
  partway through the footprint; a case puts the ground two cells in and the platform back at cell 0
  and reads the oracle's `a6`.
* **THREE GLOBALS AND A TILE CODE GOT THEIR FIRST NAMES, FROM SCANS RATHER THAN FROM POSITION.**
  `$1514`/`$1516`/`$1518` sit between `$1492`'s last byte and the routine at `$151a` and had no `var`
  or `cmt` anywhere. The scan runs **both** absolute encodings — all three lie below `$8000`, so a
  long-form-only scan reports a fraction of the sites — and classifies each short-form hit by whether
  the word below it really carries the abs.w effective address, which separates the real references
  from five byte pairs in the graphics data that spell the same numbers. `tile_33_flag` is raised
  while the player's own cell holds tile `$33`; `tile_33_mode`, while set, returns `$1334` at `$1362`
  before it touches the record; `tile_33_step_flag` has one reader, `$20ae`. `WB_MAP_TILE_33` is
  named for the tests that read it, like `$1`/`$2`/`$23`: exactly two sites compare a map byte
  against it (`$1348` and `$1554`) and both raise the flag. The mechanism around them reads as a
  climbable tile — `$d84` gates on the flag, snaps x to `(x & $fff1) + 8`, moves y by ∓2 under two
  bits of `joy1_current`, and walking dismounts through `$107c` — but **the bit assignment of
  `joy1_current` is not established anywhere in this workspace**, so that stays a reading and the
  names carry the tile code, in `state_flag_a32`'s voice. Two limits recorded honestly: `$1516` is
  written two DIFFERENT nonzero values (`$ff` at `$db2`, `$ffff` at `$dea`) and all five of its
  readers are bare `tst.w`, so nothing in the image can tell them apart; and `$1514` is written as a
  word by `$1334` but as a BYTE by `$155c`/`$179e`.

**THE MUTATION SWEEPS FOUND A HOLE THAT WAS NOT THIS BATCH'S, AND IT IS THE METHODOLOGY FINDING.**
Dropping the `subq.w #1` that makes the probe row the pixel ABOVE the actor's y reddened NOTHING on
the first sweep — because every case in `test_map.py`, `$10a2`'s included since batch 10, put the
actor one pixel inside its row, where `y` and `y - 1` name the same cell. `probe_cell` /
`right_probe_cell` now derive the row from the y a case seeds, and
`test_the_probe_row_is_the_pixel_above_the_actors_own_y` stands an actor exactly on a cell boundary.
This is batch 10's own finding recurring one layer up — a case whose geometry is computed from the
same image it seeds stays self-consistent while testing nothing — and it is the second time a
mutation, not a review, is what said so.

Mutation-checked as usual, each with the `.so` DELETED before the rebuild and each source restored
and byte-compared against a pristine copy afterwards, green each time it was restored. **51
mutations across the batch, 51 killed, 0 survivors**: 13 on the cell lookup and its prelude (the
span left undoubled reddens 22, the cell index dropped from the pointer helper 19, the sub-cell taken
after the shift 10, the sub-cell written as a longword 8, the span doubled as a long 7, the column
shift read as logical 5, the column added to the product as a long 5 — one of them a `$10a2` case,
the shared helper answering for itself — the left edge added instead of subtracted 5, the row taken
from `y - 1` 4, the index zero-extended 4, the prelude keeping the left edge's high half 2, the map
selection ignored 1, the prelude leaving the caller's row alone 1); 14 on the rightward probe (the
probe subtracting the half-width 13, subtracting the step 8, a strict clamp compare 1, an unsigned
one 1, the A32 arm reading the limit word 2, the clamp reporting `d6` instead of its literal 5,
parking the wrong side 5, not writing x 5, committing the column where the limit belongs 23, an
off-by-one retry 4, stepping the wrong way 11, the shared tail walking by the map it looked up 2 —
one case per body, the extraction answering for itself — the bias dropped 8, the probe row's `subq`
1); 14 on the two settles and the tier above (the ground test losing the LEDGE code 4, the span test
made strict 4, the y mask losing a bit 1, the landing keeping LAUNCHED 1, the extra cell never tested
3, the not-found arm doing nothing 6, the SHARED sub-cell edge made strict 3 — which fires in BOTH
settles, and is the evidence that `footprint_reaches_next_cell` is one piece of code rather than a
forced abstraction — the crossing test made strict 1, the landed-bit test inverted 4, the first
lookup reused for the platform scan 2, the head reading the left edge instead of the record's x 2,
the mode test inverted 2, the step-flag clear dropped 1, the pass gated on SUPPORTED instead of
MOVING 1); and 10 re-measured on the status panel, listed with the second tier above.

**REGISTERED, rather than argued each time:** `test_actor.py::_accelerate_fall_entry` and
`test_map.py::_accelerate_fall_body` are independent assemblies of `actor_accelerate_fall`'s six
instructions, which is TWO users — the line `_keyed_block`, `copy_longwords`, `_put_word` and
`_assert_writes` were all held at. Usual terms: **trigger** = a third user; **home** = `test/leaf.py`.
The duplication is bounded meanwhile by `test_the_enclosed_routine_is_actor_accelerate_fall`, which
ties `test_map.py`'s copy to `../names.txt`'s address for the routine and to the length
`test_actor.py` records, so the two cannot drift apart silently.

**What this batch does NOT pin:**

* **THE CONDITION CODES.** The widened window reports registers, not the CCR, so a routine whose
  output is a flag is still only pinnable through something that reads the flag — and the report is
  taken at the `rts` (or a `stop_pc` checkpoint) alone, so a value computed and then overwritten
  remains invisible. Both limits are stated in `TRAP_MODEL.md` beside the decision itself.
* **THE HAND-OVER FROM `$13c8` TO `$1400`, END TO END THROUGH A CALLER.** `$1334`'s battery composes
  the five models over one memory, which is the strongest statement available from outside; that the
  ORIGINAL's `$13c8` leaves exactly the registers the ORIGINAL's `$1400` is entered with is stated by
  the two batteries separately, not by one run through both.
* **WHAT TILE `$33` IS.** Named for its two readers, as above; the `joy1_current` bits that would
  settle it are not established.
* **THE REGISTERS EVERY EARLIER BATCH LEFT BEHIND.** The status panel's five blits, the scroll's two
  column fills, the text plotter's `d7`, `$bd8a`'s six — each was registered as unobservable, and
  each is now merely UNMODELLED: the window is open, the reconstructions have nothing to compare, and
  every call site reloads what it needs. The claims in `src/scroll.c`, `test/test_scroll.py` and
  `test/test_text.py` that named the oracle as the reason were corrected in this batch (a stale
  statement about the HARNESS is worse than an open item); the items themselves are honestly
  openable, one reconstruction at a time, rather than closed here.
* **`subsystems.tsv` AND `PORTABILITY.md`.** Eight collision-map routines now sit in the "game logic"
  catch-all, and the "reconstructed and pinned" column is five functions / 454 bytes stale. Re-drawing
  the boundary and re-running `tools/hw_portability.py` is a MEASUREMENT, queued as one — batch 10
  made the same call for the same reason. *(CLOSED by the 2026-08-05 re-measure at the end of this
  file.)*

### The stage loader (batch 12): what fills the buffers the scroll engine maintains

**THE $fxxx CLUSTER IS THE OTHER HALF OF THE BACKGROUND-SCROLL STORY, AND THAT IS THE BATCH'S
FINDING.** Batches 5–7 closed the engine that MAINTAINS the eight pre-shifted buffers — one
uncovered tile column or one row pair per frame — and the consumer that blits one of them to the
screen. Nothing had read the tier that fills them in the first place. It is `$f95c`'s three callees,
back to back:

* **`$fa30` (`bg_build_buffer`, 214 bytes)** draws the map's visible window — eleven tile rows of
  sixteen cells — into copy 0 at `$44000`, one 128-byte tile bitmap per cell laid down a
  `WB_BG_BUFFER_LINE` at a time.
* **`$fd46` (`bg_build_preshifted_copies`, 198 bytes)** derives copies 1..7 from it, `rol.l #2` a
  plane word at a time. `a0` and `a1` are `lea`d ONCE and never reloaded, so pass n reads copy n and
  writes copy n+1 — which is what makes the eight copies tile `$44000..$70000` at all, and it is the
  whole-buffer form of `bg_scroll_preshift_rows`, which does the same thing to one fresh row pair.
* **`$fb06` (`stage_publish_scroll_state`, 320 bytes)** writes the two limits, the map cursor, the
  position words, the cleared ring cursors and the SIXTEEN `WB_BG_BUFFER_ROWS` longwords the engine
  then steps. **The seam is asserted from both sides**: `test_stage.py` derives all sixteen from
  `WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + row * WB_BG_BUFFER_LINE` — the invariant
  `src/scroll.c`'s vertical steps preserve — and requires the SHIPPED instruction bytes to spell
  exactly those. So this batch and the scroll batch cannot disagree about a buffer address without
  failing on the .PRG's own bytes.

**THE MAP HEADER IS TWO WORDS, WHICH IS WHAT THE `+4` WAS.** `WB_MAP_DATA_ROW` sat four bytes above
`WB_MAP_ROW_STRIDE` with only "indexed from its THIRD byte" to explain it, and batch 10 found the
same 4 on the collision map three more times (`WB_COLLISION_MAP_CELLS`, `map_stamp_block`'s
`addi.w #$4`). `$fb06` reads BOTH header words — `move.w (a0)+,d0` twice, each `<< 4` and biased
into `WB_BG_SCROLL_LIMIT_X` / `_LIMIT_Y` — so the header is {cells across, cells down} and the cell
data starts past it. `test_the_map_header_is_the_collision_maps_own_cell_bias` states the four
spellings as one number.

**THE OTHER FOUR ARE THE SAME TIER'S HOUSEKEEPING.** `$fed2` (`stage_reset_state`) clears the
per-stage state block and — the find — writes the LAST EIGHT entries of `WB_TILE_INDEX_TABLE`
itself. **The .PRG ships NONE of that table**: `$21e90` is past the program's last byte (`$218d0`),
so all 256 entries are loaded from disk at run time and this reset OVERWRITES the last eight of
them — what the disk holds there beforehand is pinned by nothing, here or anywhere (an earlier
reading of this, that the shipped table was "248 entries of truth", was wrong on both surfaces and
is corrected in `../names.txt` and `include/wonderboy.h` too). It also `clr.l $1514.w`,
the one site in the image that clears batch 11's `tile_33_flag` and `tile_33_mode` together.
`$fe1e` (`resource_table_relocate`) turns each 20-byte record's leading offset into an absolute
pointer, ONCE, behind an `'E'` signature byte — the conversion is in place and is not idempotent,
which is the whole reason the byte exists. And `$e110`'s three routines plot "ROUND BONUS" and, when
the meter is exactly at its maximum, "PERFECT!  10000 PTS" into copy 0 out of a **second font** at
`$1387c`, which a whole-image scan of both absolute encodings finds exactly ONE operand site for —
`$e156`, inside `bg_plot_banner`. The cell layout is `src/text.c`'s (32-byte glyphs, one byte per
plane, the +1/+7 alternation) over a 128-byte line rather than an 88-byte one, so the two plotters
are two routines over one layout: the constants are shared and the code is not.

**THREE SEMANTICS REPRODUCED RATHER THAN TIDIED, each with a case and a mutation:**

* **The per-row map skip is UNSIGNED.** `moveq #0,d7 / move.w d2,d7 / subi.w #$10,d7 / adda.l d7,a0`
  subtracts the sixteen columns just walked from the row stride in a WORD, in a register whose high
  half is zero, and then adds the whole LONGWORD — so a stride below 16 advances the cursor by
  nearly 64 KB where a signed reading steps it back.
* **The cell index is a WORD and the `lea` SIGN-EXTENDS it**, so a start row past `$7fff` names a
  cell BELOW the map; while **`lsl.l #7,d7 / lea 0(a1,d7.l),a1` is a LONG shift and a LONG index**,
  so a tile number past 511 names a bitmap more than 64 KB above the bank rather than a wrapped one.
* **Each pre-shifted scanline closes as a RING.** The first cell's shifted-out bits are held in
  `bg_build_carry` (`$fe0c`, four words of scratch between `$fd46`'s `rts` and `stage_map_ptr`)
  across the whole 128-byte row and ORed into the LAST cell, so a pixel leaving a row's left edge
  re-enters at its right. That is the same ring the horizontal scroll reads, and it is why the
  routine cannot be written as a plain left shift.

**THE MUTATION SWEEP FOUND THREE HOLES AND THEY WERE ALL THE SAME HOLE.** 22 mutations, each with
the `.so` DELETED before the rebuild and the source restored and byte-compared afterwards. The
restored run reads 1585 green for the early mutations and 1586 for the later ones: the suite GREW BY
ONE mid-sweep, when the sweep's own finding about the terminator became
`test_the_terminator_is_a_sign_test_and_the_records_cannot_say_so`. (Both figures are the
committed-scope count of the time; the batch closes at 1587 after the below-the-bias limits case.)
Three survived the first sweep, and every one of them was a case
seeded in the wrong PLACE — batch 10's finding for the third time:

* **The level map was `WB_MAP_ROW_STRIDE` itself.** `$fb06` reads the header off the level map and
  the cursor's stride off the GLOBAL, and while the two were one address no case could tell them
  apart: a mutation reading the header where the routine reads the global reddened NOTHING. The map
  moved to a band of its own and every case now seeds the two APART (`reddens 6`).
* **The tile numbers were all shipped ones**, so `number * 128` never left 16 bits and shifting it
  as a word was invisible. A case now seeds an index entry past 511 and the bitmaps beside it
  (`reddens 1`).
* **The map band was keyed off `MAP + 4` rather than off the cursor the routine computes.** So the
  negative-index case read UNSEEDED zeros at both the right address and the wrong one, and the two
  agreed — the "zeros over zeros" shape, arrived at from the geometry side. `build_cursors()` now
  transcribes the routine's own arithmetic and yields all ELEVEN cursors, and a band is seeded at
  each with a cell of margin (`reddens 1`). This is the third batch in a row where a mutation, not a
  review, is what said the geometry was wrong; the rule is already written up in
  [`docs/methodology.md`](../../../docs/methodology.md).

**Final sweep: 22 mutations, 21 killed, 1 survivor.** The row skip read as a signed step back
reddens 1; the start cell index zero-extended 1; the tile number shifted as a word 1; the tile's
last row stepping like the fifteen above it 10; the raw-tile test inverted 10; the map header read
as one word 10; the horizontal limit built with the vertical bias 8; the bottom row pointer
published at row 0 8; the `st` written as a word 8; the map cursor taking the level map's own stride
6; the pre-shift's ring carry dropped 3; rotating by one pixel 3; its cell loop one cell long 3; the
carry taken from the shifted word's LOW half 3; the relocation running the count rather than the
count plus one 3; its signature check dropped 1; the panel delay reset to zero 4; the tile-33 pair
cleared as a word 4; the glyph's two advances swapped 12; its planes written one byte apart 12; the
meter compare made an inequality 1.

**THE ONE SURVIVOR IS A COVERAGE LIMIT OF THE GAME'S OWN DATA, AND IT IS REGISTERED AS ONE.**
`$e164` is `tst.b (a6)` and `$e166` a `bpl`, so ANY byte from `$80` up ends a banner string — but
both records the image ships end with exactly `$ff`, and `$e140`'s only two callers are `$e110`'s,
which pass exactly those two. Reading the terminator as `== $ff` therefore cannot be told apart
from the sign test without fabricating a record, which is what CLAUDE.md's coverage rule refuses.
What IS pinned is the instruction: the whole-body entry pin spells the `tst.b`/`bpl`, and
`test_the_terminator_is_a_sign_test_and_the_records_cannot_say_so` states the data that makes the
difference unobservable and fails if a shipped record ever stops ending in `$ff`.

**FIVE ENCODERS WENT TO `test/leaf.py`, AND THE PARAGRAPH THAT SAID OTHERWISE WAS FALSE.** This
section first claimed `test_stage.py` spelt `move_w_postinc_dn`, `movea_l_abs_l`, `mulu_w_dn_dn`,
`add_w_dn_dn` and `move_l_dn_dn` "for the FIRST time in this directory". It did not: every one of
them already existed elsewhere, and the third-user trigger had already fired on four of them —
`movea_l_abs_l` was defined identically in **four** batteries (`test_actor.py`, `test_scroll.py`,
`test_map.py`, `test_stage.py`) and `add_w_dn_dn`, `move_w_postinc_dn`, `move_l_imm_abs_l` and
`move_w_dn_dn` in **three** each. All five now live once in `test/leaf.py` and all four batteries
import them. `move_w_postinc_dn` took the two-argument `(reg, base)` form on the way: `test_scroll.py`
alone spelt it `(reg)` with `a0` baked into the opcode, which is a constant hidden in an encoder, and
its one call site now names `A0`. **The whole-body entry pins are the proof the hoist changed
nothing** — all 684 cases of the four batteries still match the shipped image byte for byte.

**What is STILL at two users is registered, and it is a longer list than one battery's.** Spelt
identically in exactly two batteries: `mulu_w_dn_dn`, `move_l_dn_dn`, `cmpi_b_ind`, `move_b_imm_ind`
(`test_map.py` + `test_stage.py`); `swap_dn`, `move_w_dn_abs_l` (`test_scroll.py` + `test_stage.py`);
`clr_l_postinc`, `move_l_imm_postinc`, `movea_l_an_an`, `move_w_dn_postinc` (`test_actor.py` +
`test_stage.py`); `bit_op_d16`, `clr_b_d16`, `clr_w_dn`, `cmp_w_dn_dn`, `move_w_d16_ind`
(`test_actor.py` + `test_map.py`); `addi_w_dn`, `andi_w_dn`, `neg_w_dn`, `tst_w_dn`
(`test_scroll.py` + `test_map.py`); `btst_imm_dn` (`test_stage.py` + `test_text.py`);
`move_w_abs_l_abs_l` (`test_scroll.py` + `test_text.py`). Usual terms — **trigger** = a third user;
**home** = `test/leaf.py` — the same line `_put_word`, `_assert_writes` and `_accelerate_fall_entry`
are held at.

`WB_TEXT_CELL_ADVANCE_EVEN` / `_ODD` and `WB_TEXT_GLYPH_ROWS` are REUSED by `src/stage.c`
rather than respelt: they are properties of `WB_PLANES * WB_PLANE_STRIDE`, not of the message
buffer, and a second spelling is exactly what CLAUDE.md §5 forbids — but their names now say TEXT in
a file that is not text, which is a rename the day a third user appears.

**AND `copy_longwords`' OWN THIRD USER FIRED IN THIS BATCH.** `bg_build_buffer`'s `draw_tile` had
the run of `move.l (a0)+,(a1)+` inlined a third time; it now CALLS the function `src/scroll.c`
defines and `include/scroll.h` declares, joining `src/scroll.c` and `src/text.c`. **The batch-8
registration above named the trigger as "a third user, in this project or another" and the home as
the kit's `machine.h`, so the trigger has fired as written — and the function is NOT moving.** The
REASON that registration gave for keeping it project-local was that every user is this game, and
three users later that is still true; a helper in `machine.h` that only Wonder Boy calls buys the
kit nothing. The registration is therefore restated on its reason rather than its count: **trigger**
= a user in another project; **home** = `tools/recreate_kit/include/machine.h`, beside `addr_add`
and `rotate_left32`.

**What this batch does NOT pin, beyond the terminator above:**

* **`$f95c`, THE CALLER (210 bytes), IS NAMED AND REJECTED.** It latches `stage_map_ptr` /
  `stage_start_ptr`, calls the three builders, computes `scroll_follow_x/_y`, and then does two
  things the harness cannot follow, both on the unconditional path: `bsr set_palette` (a write to
  the shifter at `$ffff8240`) and `lea $17adc.l,a1` + `jsr (a1)` / `jsr 28(a1)` into the sound
  module, de-duplicated through the byte at `$fa2e`. So the hand-over from `$f95c` to the three is
  stated by their own entry conventions, not by a run through it.
* **WHAT THE BUILDERS LEAVE IN THEIR REGISTERS.** `$fa30` walks out with a0/a1/a2/a5/a6 and d0–d7
  well past where they started and `$fd46` the same; `$f95c` reloads everything it needs from
  `stage_start_ptr`. The oracle reports them all since batch 11 — what is missing is a
  reconstruction that models them, not an observer — so this is openable, one routine at a time,
  rather than blocked. The banner pair is the exception and its cursor is asserted three ways.
* **WHAT `$fe1e`'s RECORDS HOLD.** Only the first longword of each twenty bytes is touched; the
  other sixteen are neither read nor named. Its table, its count and its signature all lie past the
  program and are loaded from disk, so every case seeds them as plain RAM.
* **WHAT `$fb06`'s TWO COPYLOCK FLAGS ARE FOR.** `$f89a` and `$f89c` have EXACTLY ONE operand site
  each in the plaintext image — the `clr.w` and the `st` in this routine. Their readers are
  reachable only from inside the protection's ciphertext, which is the other side of
  `PORTABILITY.md` §6.1's "KNOWINGLY UNPINNED" list.
* **WHAT MOST OF `$fed2`'s BLOCK MEANS.** `$b08..$b19` and three of the four panel timer words have
  no reader among the recovered functions; `$a34` has eleven operand sites and none inside anything
  reconstructed. The names carry the addresses, in `state_flag_a32`'s voice.

**QUEUED, read but deliberately not ported — ALL FOUR OF THESE ARE BATCH 13'S, AND ARE CLOSED:**

* **`$fe4a` (`game_restart_reset`, 136 bytes)** — the new-game reset the panel batches' `cmt`s keep
  citing. Everything in it is plain memory except one `bsr $e80c`, which is unported: `$e80c` writes
  `$704d8`/`$784d8` (both screen buffers) under `$be2`, the lives count this routine sets to 3.
  Porting the pair is a two-function batch of its own. *(Batch 13: it is three routines, not two —
  see below.)*
* **`$ff42` (`actor_spawn_pass`, 162 bytes)** — the per-frame spawn driver gated on `state_flag_a30`,
  and the routine that would pin batch 10's registered finding that an allocation FAILURE is not
  checked (a full pool hands `actor_spawn_from_template` `a1 = $0` and stamps 32 bytes over the
  68000 vector page). Two of its three callees are reconstructed; the third, `$1006a`, is not.
  *(Batch 13: pinned — and the stamp is eighteen bytes, not 32.)*
* **`$2b82` (`actor_toggle_side_flag`, 12 bytes, plus the 8-byte tail at `$2b7a`)** — batch 10
  rejected it for branching backwards out of Ghidra's boundary, and the true extent is now read:
  `tst.b d0 / beq $2b7a / btst #2,d1 / bne $2b7a / rts` over `bchg #3,8(a0) / rts`, which flips the
  bit `actor_set_side_flag` sets and clears. It is verifiable today (the write set is one byte of the
  actor record and the inputs are a0/d0/d1), and it is left out only because it belongs with
  `src/actor.c`'s flag family rather than with this cluster. **`$2b70` is NOT a sibling routine**,
  which an earlier reading here had wrong: it is the second arm (`btst #1,d1 / bne.w $2b7a / rts`) of
  the 40-byte routine at `$2b5a`, reached only by that routine's own `bne.w` at `$2b5c` and by no
  call anywhere. `$2b8e` (`actor_turn_and_launch`, 58 bytes, two `bsr` callers) IS a routine of its
  own and repeats `$2b82`'s head over a longer tail — the side flip plus exactly the flag bits and
  speed byte `actor_start_motion_at_speed` writes, at a fixed speed of 7. All four addresses now
  carry `fn`/`cmt` entries in `../names.txt`.

**RE-CHECKED AND STILL REJECTED, with the reason sharpened:**

* **`$638` (`game_unpause_on_key_release`, 54 bytes)** — `tst.w $66e.l` and `cmpi.b #$19,$879.l`
  both return at once, and the routine's whole payload (`clr.b $879`, `clr.w $66e`,
  `move.b #$ff,$c030.l` — unpause, and dismiss the message box) sits behind
  `cmpi.b #$99,$879.l / bne.s` — a spin on `key_last_scancode` waiting for the RELEASE code
  (`$19 | $80`) that only `ikbd_acia_handler` ever stores, and which no instruction in this routine
  writes. The pause is SET by the mirror-image arm at `$60e` inside `$53e`, which spins the same way.
  A wider register window does not help and neither does a `stop_pc`: the oracle never REACHES the
  checkpoint, because nothing changes memory while a run is in flight. **Registered with terms**:
  **trigger** = a kit capability to schedule a memory poke at an instruction count or a PC;
  **home** = `tools/recreate_kit`, in `emu.run`. Until then the two returning arms are portable and
  the payload is not, which is not worth a partial reconstruction.
* *(Batch 17: BOTH PORTED — `actor_damage_followed` / `actor_damage_template_hitpoints`, see the
  batch-17 section. The rejection below was right when written and fell in two stages: 16a made the
  invisible call an honest edge, 16b ported its target.)*
  **`$69fe` (`damage_path_69fe`, 266 bytes) and `$6b46` (`damage_path_6b46`, 114 bytes)** — the
  damage paths. Batch 10 rejected both for a `jsr 56(a5)` into the sound module at `$17adc`, and
  re-reading confirms the call is unavoidable in each: `$69fe` funnels all four of its arms
  (`$6a44`, `$6a7a`, `$6a96`, `$6ab0`) through `$6aba` into `$6ade` and the `lea`/`jsr` pair at
  `$6ae4`, and `$6b46`'s first four instructions ARE that pair. **`$69fe` does have one arm that
  returns before the call** — the `btst #4,9(a1) / beq.w` at `$6a16` falling into the `rts` at
  `$6a20` — but it is the arm for a record that already carries that bit and therefore writes
  nothing at all, so seeding it buys a differential over an empty write set. There is still no
  branch worth registering. Both now carry `fn`/`cmt` entries in `../names.txt`, bodies and callers
  included, so the read is not lost when the sound module opens.

### The spawn pass and the two resets (batch 13): what makes the lifecycle run

**BATCH 10 REGISTERED A FINDING AND THIS BATCH PINS IT.** `actor_alloc_slot_low` returns
`WB_ACTOR_ALLOC_NONE` on a full pool, and neither of `$ff42`'s two `jsr $1b68.w` sites tests the
result — so a full pool spawns over absolute `$0`, the 68000 vector page. That was recorded as
behaviour on `$1b68`'s `cmt` and nothing ran it. `test_a_full_pool_stamps_the_spawn_over_the_vector_page`
now does, from BOTH arms, with both pools seeded full so that the claim does not rest on which
allocator was called — and it **states the write set exactly, which corrected the registration**:
the stamp is **EIGHTEEN bytes, not 32**. `actor_spawn_from_template` writes ten fields, not a whole
record, so `$0..$9`, `$e..$13` and `$1e..$1f` move (both reset vectors, the bus-error vector's high
word, the address-error vector's low word, the whole illegal-instruction vector and TRAPV's low
word) while `$a..$d` and `$14..$1d` are untouched. `../names.txt` carries the corrected sentence.
This is the reproduce-not-tidy rule at its sharpest: a port that checked the allocator's result
would be *better code* and would fail this case.

**THE TEMPLATE TABLE HAS A FOUR-WORD HEADER, AND ITS FIELDS ARE READABLE FROM THEIR OTHER USERS.**
`$ff42` reads `-8(a6)`..`-2(a6)` off the pointer `table_ptr_21e8c` holds. What each is comes from the
routine that moves it the other way: `$6c3e` does `subq.w #1,-6(a6)` on a death against this
routine's `addq.w #1` per spawn, so `-6` is the LIVE COUNT and the `move.w -8(a6),d0 / cmp.w -6(a6),d0
/ beq` above it is a capacity test; `-4` is the cursor, post-incremented; `-2` goes to `$ffff` once
the cursor reaches the last record, and `$6c4e` re-arms a dead template's `30`/`31` only while it is
set. The same two other routines make the TEMPLATE's own fields readable: `$6b46`'s
`sub.w d0,4(a1)` spends offset 4 (so `$1006a` seeds a HIT-POINT POOL) and `$6bfa`'s
`addq.w #1,6(a1)` with `cmpi.w #$2,6(a1) / ble` raises offset 6 (a KILL COUNT, and the template
retires past two). So `$1006a` is "half the times you have already killed this thing, plus a
per-type base" — a difficulty ramp — and neither field could have been named from `$ff42` alone.

**FOUR SEMANTICS REPRODUCED RATHER THAN TIDIED, each with a case and a mutation:**

* **THE CURSOR'S `lea` INDEXES WITH A WORD.** `lsl.l #5,d0` builds the byte offset as a longword and
  `lea 0(a0,d0.w),a0` then takes its SIGN-EXTENDED LOW WORD — the extension word is `$0000`, not the
  `$0800` that `actor_spawn_from_template`'s own size-table lookup carries. The two are not
  neighbours: the `lea` is at `$ff8c` in THIS routine and the `move.l` at `$1002e` in that one, with
  40 instructions between them in the listing and a `bsr` between them at run time. A cursor of
  1024 therefore names a template 32 KB BELOW the table. Both readings were written before the
  bytes were checked, which is why the extension word is now quoted in `src/actor.c` and in
  `../names.txt`: `41f0 0000` and `2372 0800` are two different instructions.
* **THE COUNTDOWN WALK RUNS BEFORE THE CAPACITY TEST CAN RETURN**, so a table at capacity still
  counts down; and its `subq.b` WRAPS rather than sticking at zero. The two interact: an armed
  record seeded at zero is stepped to `$ff` by the walk and the sweep below then skips it, so the
  ready state cannot be reached from below and a case that wants a spawn seeds 1.
* **BOTH WALKS ARE `do`/`while`.** `lea 32(a0),a0 / cmpi.w #$ffff,(a0) / bne` tests the terminator
  only AFTER a record has been handled, so a table whose FIRST word is the terminator still has that
  record's byte 31 stepped. See the sweep below — this is the one hole it found.
* **THE SWEEP CAN OVERSHOOT THE CAPACITY.** The `cmp.w -6(a6),d0` runs once, above both arms, while
  the sweep raises the live count per spawn — so one pass over an all-ready table carries it well
  past `-8(a6)`, and later spawns in the same pass hit the full pool.

**GHIDRA'S ONE FUNCTION AT `$fe4a` IS TWO ROUTINES, AND A WHOLE-IMAGE SCAN IS WHAT SAYS SO.**
`$fe4a` has a single entrant (`bsr` at `$e59e`); `$fe8c`, 66 bytes into it, has one of its own —
`jsr $fe8c.l` at `$c00`, the instruction immediately after the `subq.w #1,lives` at `$bfc`. So the
head is what only a NEW GAME does (the level cursor, the lives count, the effect record list's
`$ffff` "empty" word, the six HUD slots) and the tail is what a lost life shares with it (redraw the lives, reseed the meter, clear
the score and the small state words, re-arm the tune latch, point the record write pointer back at
the list's base). Two consequences a case each states: **the head sets `lives` to 3 BEFORE falling
through**, so a new game always draws three icons however many the caller had; and **the write
pointer is restored on both paths while the `$ffff` is written only by the head**, so a life
restarted this way keeps whatever record the list already held.

**`test_stage.py` IMPORTS `test_hud.py`'s LIVES MODEL RATHER THAN RESTATING IT.** `$fe8c` calls
`$e80c`, so its write set CONTAINS that routine's 768 bytes across both screen buffers. Two copies of
the geometry could disagree and both batteries would still pass, so `model_lives_draw` and
`lives_pokes` are defined once, in the battery that owns the routine, and imported by the caller's.
That is the first cross-battery import in this project and it is deliberate: the alternative is the
duplication CLAUDE.md §6 forbids.

**THE MUTATION SWEEP: 39 mutations, 38 killed, 1 survivor — and the survivor list moved twice.**
Each mutation deleted the `.so` before the rebuild and restored the source afterwards (the rebuild
trap the workspace memory records). The first sweep of 35 left TWO alive:

* **The `do`/`while` written as a `while`** survived, and that was a real coverage hole: every case
  seeded a table with records in front of the terminator, where the two loops agree. The fix is a
  case seeding an EMPTY table — a second terminator at slot 0, which is the format's own degenerate
  shape and not a fabricated record — whose only write is the terminating record's countdown byte.
  It now **reddens 1**.
* **`clr.w $bd6a` moved to AFTER the fall-through** survived and is an EQUIVALENCE, not a hole: the
  tail never touches `$bd6a`, the two writes are disjoint, and a byte-for-byte diff of final memory
  cannot see the order of disjoint writes. Where ordering IS observable it is pinned — moving the
  `move.w #$3,$be2.w` past the same call **reddens 4**, because the icons drawn change.

Final sweep, with what each reddens: the countdown counting up 7; the walk ignoring the armed byte
13; the capacity test made an inequality 8; the walk moved below that test 1; the cursor index taken
as the long the shift produced 8; zero-extended instead of sign-extended 8; the cursor not advanced
8; the wrapped flag read as the opposite arm 13; raised off this record rather than the next 1; the
terminator read one short of `$ffff` 14; the sweep's countdown test inverted 4; the sweep leaving the
armed byte raised 3; the live count not raised 11; **the allocator's result tested before the spawn
2** (the vector-page pin, from both arms); the hit-point seed taking the whole kill count 61; its
shift made unsigned 31; its table indexed by the type rather than twice it 75; the fixed-type arm
taken for its neighbour 16; the step-outcome test widened from a byte to a word 96; the side flag set
rather than flipped 117; the clear-step arm reading the one-cell drop 16; the hop speed off by one
36; the toggle's two conditions ANDed 72; the turn-and-launch's supported test dropped 54; its speed
taken from the hop 54; the lives count read as a sign test 3; the icon re-loaded once rather than per
slot 14; the row step made a whole scanline past the post-increment 18; the per-slot rewind dropped
18; the blank slot's two longwords swapped 6; the lives count decremented for every slot 4; both
screens drawn from the same cursor 18; the lives word set after the tail 4; the score cleared as a
word 10; the tune latch written as a word 10; the record list emptied by the tail as well 6; the
meter maximum left alone 10; the empty-table `while` 1.

**FOUR ENCODERS WENT TO `test/leaf.py`, AND ALL FOUR TRIGGERS FIRED AS REGISTERED.** Batch 12's
two-user list named `addi_w_dn`, `tst_w_dn`, `btst_imm_dn` and `move_l_imm_postinc` with
**trigger** = a third user and **home** = `test/leaf.py`. This batch is that third user for each, so
all four now live once and the five batteries that had them (`test_map.py`, `test_scroll.py`,
`test_stage.py`, `test_text.py`, `test_actor.py`) import them. `move_l_imm_postinc` had two
DIFFERENT spellings of the same four bytes (`0x20fc | reg << 9` against
`0x2000 | an << 9 | 3 << 6 | 0x3c`); the simpler one survived. **The whole-body entry pins are the
proof the hoist changed nothing** — every battery still matches the shipped image byte for byte.

**What is STILL at two users, restated with this batch's additions.** From batch 12, unchanged:
`mulu_w_dn_dn`, `move_l_dn_dn`, `cmpi_b_ind`, `move_b_imm_ind`, `swap_dn`, `move_w_dn_abs_l`,
`clr_l_postinc`, `movea_l_an_an`, `move_w_dn_postinc`, `bit_op_d16`, `clr_b_d16`, `clr_w_dn`,
`cmp_w_dn_dn`, `move_w_d16_ind`, `andi_w_dn`, `neg_w_dn`, `move_w_abs_l_abs_l`. New to the list, at
two users because batch 13 spelt a second copy: `asr_w_imm_dn`, `cmp_w_d16_dn`, `cmpi_w_d16`
(`test_map.py` + `test_actor.py`); `lsl_l_imm_dn` (`test_stage.py` + `test_actor.py`);
`move_w_imm_abs_l` (`test_text.py` + `test_stage.py`); `clr_l_abs_l` (`test_scroll.py` +
`test_stage.py`). Usual terms — **trigger** = a third user; **home** = `test/leaf.py`.

**What this batch does NOT pin:**

* **WHAT THE TEMPLATE'S OTHER FIELDS HOLD.** Offsets 0, 8, 10, 18–23 and 28–29 of a 32-byte template
  are neither read nor written by anything reconstructed. Offset 0 is only ever compared against the
  terminator, and every case seeds it away from `$ffff` so the address-keyed filler cannot end a walk
  by accident.
* **WHERE THE TABLE AND ITS HEADER COME FROM.** `table_ptr_21e8c` is one of two immediates
  `select_table_21e8c_and_tick_b39a` publishes, and both (`$21e6a`, `$21c60`) are past the program's
  last byte — so the header, the records and their terminator are all loaded from disk, and every
  case seeds them as plain RAM. Whether the SHIPPED data can reach the sign-extended cursor, the
  wrapping hit-point index or a full pool is therefore not established by anything here.
* **`WB_SPAWN_HITPOINT_TABLE`'s LENGTH.** The code bounds the index at neither end, and what pins
  the 32 entries the header states is the table BELOW: `actor_size_table`'s 32 longwords end exactly
  where this one starts. Above it there is room for 33 — the next table's 4-byte records begin at
  `$1015c` (`lea $1015c.l,a0` at `$1a82`), so the zero word at `$1015a` belongs to neither table and
  whether it is a 33rd entry or padding is not established.
  `test_the_hitpoint_table_sits_immediately_above_the_size_table` states the size table's half of
  that; the boundary above is a read of the bytes and is not asserted anywhere.
* **WHETHER `WB_SPAWN_ARMED`/`_COUNTDOWN` REALLY SHARE THE ACTOR RECORD'S LAYOUT.** They sit at the
  same two offsets as `WB_ACTOR_FIELD_30`/`_31` and both records are 32 bytes, but `$ffe4` clears the
  ACTOR's pair while `$ff42` walks the TEMPLATE's. That the two layouts agree here is a coincidence
  as far as anything reconstructed can tell, and `include/wonderboy.h` says so.
* **WHAT `$e80c`'s ICON DEPICTS**, and what the blank slot's colour-2 block is over. The bitmap at
  `$ec38` has exactly one reference in the image, this routine's own `lea`.
* **WHY THE LIFE RESTART CLEARS THE SCORE.** `clr.l $bd70` is on the shared tail, so the path at
  `$c00` — which has just lost a life — zeroes `bcd_score_bd70`. The reconstruction reproduces it;
  whether `$bd70` is the *displayed total* is `../names.txt`'s open question, not this batch's.

### The second portability re-measure (2026-08-05): four more subsystems out of the catch-all

The queue entries batches 10, 11, 12 and 13 left open, closed together — and closed the same way the
2026-08-02 one was, because it is the same kind of work. **No code changed and no test moved**:
`make test` is 2159 green before and after. `subsystems.tsv` was re-drawn and
`tools/hw_portability.py` re-run over the same `../out/hw_scan.tsv`.
[`PORTABILITY.md`](PORTABILITY.md) §0b records it in full.

**The tool was pinned before anything changed.** The first run reproduced every figure in
`PORTABILITY.md` byte for byte off the unmodified `subsystems.tsv` — 252 functions, 25,696 bytes,
both tier tables, the roots table, the 126-site census, 220/21,534 runnable, 28/3,348 at
false-green risk and all fifteen subsystem rows. The re-run then differed **only in subsystem rows**,
which is what a partition is allowed to move.

**What moved.** Seven groups of ranges — 28 `F` records, 2,804 measured bytes — left the catch-all,
and one function left `boot`, each cited in `subsystems.tsv` itself: the collision map (`$10a2..$1208`, `$1334..$1514`, `$1af0..$1b46`) became
`map (collision + settle)`; the lifecycle and spawn tiers (`$1b68`, `$1f36`, `$2af2`, `$2b5a`,
`$df9e`, `$ff42..$1009a`) joined the actor subsystem, which is renamed
**`actor (table + lifecycle)`**; the three buffer builders (`$fa30`, `$fb06`, `$fd46`) and the three
banner plotters (`$e110..$e19a`) joined `video (background scroll)`; `$f95c` and the two resets
(`$fe4a`, `$fed2`) became **`stage (load + reset)`**; `resource_table_relocate` (`$fe1e`) joined
`resource loader`; and `hud_draw_lives` (`$e80c`) left `boot`, which it was never part of.

| | before | after |
|---|---|---|
| game logic | 114 fns / 9,596 B measured, 27.8 % of 34,496 B CODE | **87 / 6,904 B, 21.8 % of 31,714 B** |
| video (background scroll) | 33 / 6,140 B, 98.5 % | **39 / 7,010 B, 98.7 %** |
| actor (table + projection → lifecycle) | 5 / 356 B, 100.0 % | **14 / 864 B, 90.6 %** |
| boot | 12 / 1,184 B, 56.0 % | **11 / 1,072 B, 53.5 %** |
| resource loader | 1 / 104 B, 91.2 % | **2 / 148 B, 93.7 %** |
| map (collision + settle) | — | **9 / 924 B, 100.0 %** |
| stage (load + reset) | — | **3 / 458 B, 100.0 %** |
| game logic, runnable end-to-end | 104 / 7,638 B | **78 / 5,156 B** |
| game logic, ported and green | 88 fns / 5,580 B ¹ | **62 / 3,098 B** |
| whole program, ported and green | 105 fns / 10,376 B ² | **133 / 13,082 B** |

¹ The old partition evaluated with today's reconstructions (never previously published — the old
doc predates batches 12–13). ² The previously PUBLISHED stale column; the world-state before this
re-measure was already 133 / 13,082, since no code changed here. The two "before" conventions
differ, which is why the per-subsystem deltas do not sum to the whole-program delta.

**Every whole-program figure is unchanged**, and that was checked by diffing the two reports rather
than argued. **THE CATCH-ALL GOT WORSE AGAIN**, and harder than last time: it lost 2,692 measured
bytes and only **90** unmeasured ones, so its coverage fell 27.8 % → 21.8 % and the CODE it holds
outside every function body is now 78.2 % of it. Two re-measures have taken the bucket from 36.0 %
to 21.8 % without reaching one unmeasured byte — every subsystem this project has characterised was
already inside the 46.8 % Ghidra recovered.

**THE 90 BYTES ARE THE FINDING.** They are `actor_hop_or_flip_side` (`$2b5a`) and
`actor_turn_and_launch` (`$2b8e`) — reconstructed, green, and in **no `F` record at all**, because
Ghidra has one 20-byte function for the three-routine cluster and it is the middle one. So this is
the first row in `PORTABILITY.md` whose coverage (90.6 %) is short because the MEASUREMENT
under-counts the reconstruction, not the other way round.

**AND THE STALENESS LIMITATION HAS TEETH NOW.** The 2026-08-02 re-measure could say the stale Ghidra
DB changed no figure, because all 171 `fn` addresses in `../names.txt` were already `F` records.
There are 212 today and **four are not** — `$2b5a`, `$2b8e`, `$fe8c` and `$17f30` — so `reapply.sh`
+ a re-scan **would** move the measurement, by roughly +4 functions and +90 bytes (actor +2 fns /
+90 B, stage +1 fn, sound +1 fn). Every one of those four addresses already falls inside a range
this re-measure drew, so the re-scan would change the rows' contents and not the partition. Until it
is run, the actor and stage rows are lower bounds by construction. *(RUN 2026-08-05 — see the
re-scan section at the end of this file; the prediction was exact and the limitation is
discharged.)*

**One surprise worth its own line: `stage (load + reset)` is T0 direct and T4 transitive** — the
only row in the file with that shape. Nothing in it touches hardware; `stage_load_window` (`$f95c`)
ends with `lea $17adc,a1` + `jsr (a1)` ($fa1e) / `jsr 28(a1)` ($fa28) into the sound module, so 210 of its 458 bytes are unrunnable
behind the PSG wall. It is what stops the background-scroll story being closed end to end: the three
builders are green, and the routine that calls them is not portable until the PSG read model exists.

**QUEUED, and registered rather than half-done:**

* **THE STATUS PANEL HAS NO SUBSYSTEM, and moving `$e80c` out of `boot` is what exposed it.** The
  HUD is ~30 reconstructed functions spread over `$b346..$bd8a`, the restores at `$d93a..$db9x`, the
  effect stubs at `$10200..$103ee` and now `$e80c` — and every one of them is in the catch-all. It
  is the largest known mis-partition in the file. It is not drawn yet because a range here has to be
  cited from a batch's own read that the cluster TILES, and `panel_refresh_frame` (`$b346`) is still
  unported and blocked on `$bbca`. Same terms as every re-measure: it is a MEASUREMENT, and it is
  queued as one.
* **`$fe1e` IS FILED ON ITS CALLERS, NOT ITS DATA.** `resource_table_relocate` went to
  `resource loader` because its one caller is `show_data_disk_prompt` and all nine operand sites of
  its two addresses are on the boot resource-install path. What the 20-byte records at `$248d8`
  actually hold is still not established, so if that table turns out not to be the resource table,
  one row moves by 44 bytes.

## The reapply + re-scan (2026-08-05): the staleness limitation, discharged

The queue entry the re-measure above registered — `../reapply.sh` + `tools/hw_scan.sh`, the first
since this file's figures were taken — is CLOSED. No code changed and no test moved (`make test`
still green); what moved is the measurement, and it moved by exactly the predicted amounts.
[`PORTABILITY.md`](PORTABILITY.md) §0c is the full record; what belongs here:

* **Pinned before touching anything:** the OLD `out/hw_scan.tsv` (snapshotted first), classified
  with today's `subsystems.tsv`, reproduces every committed figure bit-for-bit. Then the reapply
  (212 `fn`, 202 `var`, 325 `cmt`, 36 `proto` applied; `../decomp.c` re-exported at 256/256
  functions) and the re-scan.
* **THE FOUR-ADDRESS PREDICTION WAS EXACT: 252 → 256 functions, 25,696 → 25,786 bytes.**
  `$2b5a`/`$2b8e` (the 90 bytes in no F record) are measured at last — actor reads 16 fns / 954 B /
  100.0 % and is no longer a lower bound; `$fe8c` split out of `$fe4a` (stage +1 fn, same bytes);
  `$17f30` (`snd_psg_silence`) split out of `$17f24` and took all nine PSG accesses with it, so
  `snd_stop` is direct-T0 / transitive-T4 now. Runnable 220 / 21,534 B → 223 / 21,624 B; the
  PORTABILITY.md answer box counts **136 F records / 13,172 B verified — the byte figure now agrees
  with this file's 134 / 13,172**, and the only remaining reconciliation row is the rad split.
* **The `$fe4a` split surfaced a graph blind spot of the `$bca2` class: a fall-through between two
  functions is no `E` edge.** `game_restart_reset` falls straight into `game_life_restart_reset`
  (no `rts` between), and `$fe8c`'s other caller (`jsr $fe8c.l` at `$c00`) sits outside every F
  record — so `$fe8c` and `hud_draw_lives` (`$e80c`) now count as UNREACHABLE (112 → 116 fns)
  although the game reaches both. Tier- and runnable-neutral (the subtree is all T0); it
  under-counts only the reachability column.
* **`$bca2` REPRODUCES on the fully named DB** — in neither ledger, byte-identically. Newly
  eliminated: the target thunk `$17b14` is an F record in both scans, so the scan script's silent
  no-target else-path is not the mechanism. The register entry in batch 3 carries the narrowed
  state; the diagnosis stays queued. *(Batch 16a: DIAGNOSED AND CLOSED — the "eliminated" step
  above had checked the wrong address; the else-path WAS the drop site, fed garbage by Ghidra's
  one-dereference-too-deep `jsr (d16,An)` sleigh. Ten sites, one mechanism. The batch-3 register
  entry carries the full closure, `PORTABILITY.md` §0d the deltas.)*
* **The names round-trip is clean.** `dump_names.sh` returns all 212 `fn` / 202 `var` lines
  verbatim (ctx tags stripped); its one extra line is `fn 0x3f8 _start`, the loader's own symbol.
  `names.txt` remains the source of truth with nothing to merge.

Still stale after this: nothing in the scan pipeline. The unmeasured bulk (29,068 bytes in no
function body) is a coverage limit, not staleness; the HUD-subsystem partition remains queued
above, and the `$bca2` diagnosis was closed by batch 16a (the batch-3 register entry).

### The sprite blitters (batch 14): twelve routines that are one walk

**THE WHOLE DRAWING TIER OF THE SPRITE PASS, 2,254 bytes.** Four widths (2..5 columns of 16 pixels)
times three clip cases (none, left edge, right edge), behind the three four-longword jump tables the
pass at `$8f02` indexes by a width code. `test_the_twelve_tile_the_region_the_jump_tables_close` is
what makes "the family is exactly these twelve" a reading rather than a boundary someone chose: the
twelve tile `$8fce..$989c` with no gap and no overlap and end exactly where `blit_table_mid` begins,
and a whole-image longword scan finds each entry address named ONCE, in its own table slot — so
entering the twelve directly is the whole of their interface. `$8f02` itself — the dispatcher that
computes the register file and picks the table — is NOT in this batch, and it is the natural next
one: it closes the sprite story end to end and it is what decides whether the runaway row count
below stays unreachable. *(Batch 15: done — and it decided REACHABLE, by a negative height byte.
The count below is also off by one: 65,536, measured. See the batch-15 section.)*

**THEY ARE ONE ALGORITHM, AND `src/blit.c` IS THAT ALGORITHM ONCE.** N columns are drawn from N−1
source CELLS of `mask + 4 planes`; every word is rotated right as a longword by the sub-word shift,
the low half draws its own column and the half pushed past the 16-pixel boundary is `and`/`or`ed
into the next one. So the first column is a cell's low half alone, the last a cell's high half
alone, and every column between is a SEAM of two cells. What separates the twelve is a column
count, a clip ladder and one `lea`. The same choice the consumer tier's sixteen copy variants got
in batch 7, made safe the same way: **the battery ASSEMBLES all 2,254 bytes** out of its own
statement of that geometry and requires them to equal the shipped image, so a width, a threshold, a
clip-mask value, a `btst` bit or a rotate that is wrong in the C is wrong in those bytes too.

**THE REGISTERS ARE HALF THE OUTPUT HERE**, which is new. A blitter walks out with a0 past the
sprite, a1 a scanline past the last row, d7 at its width's own exit value and d0–d5 holding the
last row's window — and one of the twelve leaves a DIFFERENT d3 depending on which column it
skipped. So every case is three-way: the model against all fifteen registers the oracle reports,
and against the eleven the return struct carries. The batch-11 oracle window is what makes that
possible at all.

**FOUR SEMANTICS REPRODUCED RATHER THAN TIDIED, each with a case and a mutation:**

* **ONLY THE TWO-COLUMN BODIES COUNT THEIR ROWS UP FRONT.** `$9594` and the clipped `$900a` open
  with `addq.w #1,d7 / tst.w d7 / beq / bmi` and loop back to that test, so they refuse a count that
  is zero or negative once bumped and exit with d7 = 0. The wider three and their clipped bodies
  just `dbf`: they exit with d7 = `$ffff`, and an entry count of `$ffff` would draw 65,537 rows
  *(batch 15 measured it: 65,536 — one full 16-bit cycle, not one more)*.
  `$7fff` is the case that separates the signed test from an unsigned one.
* **THE CLIPPED FOUR-COLUMN BODY MERGES ONE PLANE LATE.** `or.w d4,d3` sits at `$9324`, inside the
  arm the `btst #1` at `$9312` branches to, where every other body merges before the test. Skipping
  column 2 therefore leaves that plane unmerged. It moves NO pixel — the low word it would have
  merged is only ever drawn by the arm that merges it — and the case proves exactly that, from the
  skipping arms of BOTH ladders: same bytes, different d3.
* **THE ROW'S LAST `or.w` DOES NOT POST-INCREMENT**, so a drawn row stops two bytes short of its own
  width and the `lea` that closes it is two larger than the arithmetic suggests — 146/138/130/122.
  A clipped-out column is stepped over by exactly what drawing it would have cost, so where a row
  ends does not depend on what was clipped out of it.
* **ONLY THE LEFT LADDER UNWINDS.** A sprite wholly off the left edge does `subq.w #6,a5` — a
  32-BIT subtract, pinned with a5 seeded four bytes into a high word so a word-wide one would be
  caught — and one wholly off the right edge returns having touched nothing at all. WHOSE pointer
  a5 is is NOT established: the sprite pass walks its records in a6 (see `../names.txt`).

**THE MUTATION SWEEP: 26 mutations, 26 killed, no survivors** — each deleting the `.so` before the
rebuild. The two sharpest: **the unwind made a word subtract reddens 1** (the seeded-high-word a5
case, and nothing else), and the late merge made punctual reddens 10, all register comparisons.
The full per-mutation table is in the batch log; the families: row loops (5), the rotate/seam walk
(6), clip ladders and masks (6), merge and post-increment shape (5), guards and thresholds (4).

**THE REVIEW GATE FOUND TEN, AND THE THREE THAT MATTERED WERE ALL IN THE BATTERY, NOT THE C.**
Eight finder angles + verification; the C-vs-asm read came back clean. What the fixes changed:

* **The runaway-rows guard was defeated by the exact value it refuses.** `_rows_drawn` computed
  `(rows + 1) & $ffff`, so `$ffff` wrapped to "0 rows drawn" and got a 64-instruction cap — the one
  input that runs the runaway (65,536 rows — batch 15's measured count), admitted. Now refused for the unguarded widths (and the model runs
  only after the refusal). `test_the_battery_refuses_to_ask_a_wider_body_for_those_counts[ffff]`
  is the case that reddens if the wrap comes back.
* **The late-merge pin was vacuous as first written** — its skip arm came from the right ladder
  (mask `$c`), which skips columns 2 AND 3, so d3 was never read and "the late merge changed a
  pixel, which it must not" could not fail. It now runs the skipping arms of both ladders,
  including the left's mask 1 where the claim is actually exercised.
* **The whole-image reference scan stopped one longword short** of the program's end — the bound
  every scan in `test_bootstrap.py` gets right.
* **The C's off-image addressing now mirrors the shim** (`os_in_image`: off-image word reads answer
  0, off-image writes are dropped, same `addr+1 < size` boundary), applied to the source read and
  both write sites. This is a stated DEPARTURE from `src/rad.c`/`src/effects.c`, which register the
  off-image divergence class instead of closing it: here the runaway `dbf` makes the class
  reachable by a single bad register from batch 15's dispatcher, and a ~10 MB host write past the
  ctypes buffer is a heap smash the differential cannot report. In-image behaviour is untouched
  (the suite pins it).
* The rest: `include/blit.h` now sources `WB_PLANES`/`WB_STATE_WORD_LEN` from `wonderboy.h` instead
  of shadowing them, and `layout.py` scrapes module headers too, with a `test_layout.py` case
  refusing a name defined twice — so every simple-literal constant is stated once and the battery
  reads it through `wb(...)`; the two same-name-different-quantity `MASK_FILL`s are renamed apart;
  `or_w_dn_postinc`'s two copies now agree on argument order (`(dn, an)`, the mnemonic's own);
  the 32-bit rotate and `set_low_word` models were hoisted to `test/leaf.py` on their registered
  third-user trigger (batteries: hud, scroll, map, blit); the screen seed is built once at module
  scope (measured: 26 % of the battery's runtime was rebuilding it per case); `blit_rows` was
  renamed `blit_sprite_rows` (hud.c owns a different-shaped `blit_rows`); and the sweep's docstring
  now states coverage the generator actually delivers.

**Encoder ledger.** `swap_dn` was hoisted to `test/leaf.py` on batch 12's registered trigger (third
user; test_scroll and test_stage import it). NEW at two users, parked on the usual terms (trigger =
a third user, home = `test/leaf.py`): `cmp_w_imm_dn` (`test_actor.py`), `move_l_imm_dn`
(`test_stage.py`), `or_w_dn_postinc` (`test_stage.py`, orders now reconciled), `addq_w_dn`
(`test_map.py`). New and single-user in `test_blit.py`: `clr_l_dn`, `ror_l_dn_dn`, `and_w_dn_dn`,
`or_w_dn_dn`, `and_w_dn_ind`, `or_w_dn_ind`, `btst_imm_abs_l`, `subq_w_an`, `short_branch`,
`short_branch_back`.

**What this batch does NOT pin:**

* **THE 65,537-ROW `dbf`.** Reproduced by construction and left unreached; the battery refuses a
  case that asks for it. The two-column guard IS reached, from both of its exits. *(Batch 15: the
  count is 65,536, it IS reachable — a negative descriptor height survives the pass's signed
  bottom clamp — and it is now RUN, pointed past the image.)*
* **WHOSE POINTER `subq.w #6,a5` UNWINDS.** Six bytes is one screen-record, but the sprite pass
  walks that array in a6 and never touches a5.
* **THE DISPATCHER AT `$8f02`**, and so a width code outside 0..3. The twelve are entered directly
  at the addresses the tables hold; the tables themselves are pinned. *(Batch 15: reconstructed;
  only the out-of-table width code remains unpinned.)*
* **WHAT THE SPRITES LOOK LIKE.** The bitmaps are in `SPRITES.CRU`, past the program and loaded
  from disk, so every case seeds its own cell data and nothing here establishes the shipped
  sprites' shifts, widths or heights — including whether the game ever reaches the narrowest clip
  arms.

**QUEUED, registered rather than half-done:**

* **The `video (sprite blitters)` subsystem row now measures 100 % ported** — at the next
  `tools/hw_portability.py` re-run. A measurement, queued as one, per the house rule.
* **`SCREEN_BYTES` stands at three users with TWO meanings** — `test_blit.py`/`test_scroll.py`
  derive both-buffers, `test_text.py` carries the same name at half the value. Reconciling it is a
  cross-battery rename with its own blast radius, left out of this batch deliberately.
* **Sub-second efficiency findings left as-is** (redundant boundary re-runs ~0.55 s, closed-form
  register re-runs ~0.4 s, a re-run baseline ~0.09 s): dropping pinned cases to save under a second
  was judged the wrong trade. Registered here so the next author doesn't re-derive them.
* **`test/test_stage.py` imports `forward_branch` and never uses it** — pre-existing, noticed by
  the fix pass, left alone per the surgical-changes rule.

### Batch 15 — the sprite pass at `$8f02`: the story closes end to end

**204 BYTES, AND THE SPRITE TIER IS NOW WHOLE.** `$8f02..$989c` is accounted for byte by byte: the
pass tiles up to `blit_clip_left_w2` and the twelve tile from there to `blit_table_mid`. The pass
is `game_main_loop`'s one `jsr $8f02.l`, and batch 14's whole-image scan already said the twelve
have no other caller — so this batch closes both ends of the same story, and `subsystems.tsv` now
draws `video (sprite blitters)` as `$8f02..$989c` (cited on the spot; the re-measure is queued as
usual). Verified count 146 → 147; scope suite 2301 → 2376.

**IT DECIDES WHAT AND WHERE; IT WRITES NOTHING.** Nineteen screen records, and for each one naming
a sprite: a descriptor out of `resource_table`, a clip against the top and bottom of the 160-row
band, a screen address, a sub-word shift, and a `jsr` through one of three tables picked by the
screen x. Every byte the pass is responsible for goes through a blitter, which is why its battery's
write set is the UNION of the rectangles its records drew — against a model that walks a MUTABLE
image, so each record sees what the last one drew.

**THE `$248d8` QUEUED QUESTION IS ANSWERED: THEY ARE SPRITE DESCRIPTORS.** The 2026-08-05
re-measure registered "if that table turns out not to be the resource table, one row moves"; its
records' layout is now read from their one reader: `0` = the cell data the relocator fixes up
(handed to a blitter in a0), `4` = width code, `5` = height, `8`/`10` = x/y offsets added to the
screen record's own. Ten bytes per record remain unread. `resource_table_relocate`'s job is
thereby explained — it makes descriptor source pointers absolute — and `../names.txt` carries the
superseding text on both `cmt`s.

**FOUR SEMANTICS REPRODUCED RATHER THAN TIDIED, each with cases and mutations:**

* **THE DESCRIPTOR CURSOR IS A WORD INDEX.** `mulu.w #$14,d0` builds a 32-bit product and
  `adda.w d0,a4` takes its SIGN-EXTENDED LOW WORD, so an index past 3276 wraps and one whose low
  word has bit 15 set moves the cursor BACKWARDS — the reachable band is `$248d8` ±32 KB. Same
  class as batch 13's word-indexed `lea`. Both directions run, each from the LAST record slot,
  because `lea $248d8.l,a4` is INSIDE the loop and rebuilds the cursor for every record — which a
  review case now observes from a SKIPPED record too (below).
* **`move.w d1,d5` IS DEAD**, and observable through exactly one kind of record: every blitter
  buries d5, so only the two wholly-off-screen prelude arms let the pass's own write survive.
  Both arms are run.
* **THE SCREEN OFFSET IS BUILT IN SIXTEEN BITS** — `(x & $fff0) >> 1` SIGNED, `y*160` as `y<<5`
  plus that `<<2` — and only then sign-extended by the `adda.w`.
* **A NEGATIVE ROW COUNT SURVIVES THE BOTTOM CLAMP** — this batch's headline, below.

**THE RUNAWAY IS REACHABLE BY DATA, AND BATCH 14'S COUNT WAS OFF BY ONE.** The height is a byte
the pass `ext.w`s. The top clip can never hand a negative count on — its own `bmi` skips first,
stated over every signed byte value. The BOTTOM CLAMP can: `cmp.w d7,d2 / bge` is signed against a
rows-left count that is never negative, so it KEEPS a negative `d7`. That count reaches a blitter,
where the two-column bodies refuse it (full differential, three heights, the next record still
drawing) and the three wider ones `dbf` away. Measured, not argued: **65,536 rows, not 65,537** —
`a0` advances 65,536 × 20 and `a1` 65,536 × 160; the `dbf` exits when the counter is back at
`$ffff`, exactly one full 16-bit cycle. Batch 14's three statements of 65,537 are corrected in
place above, and `../names.txt`'s `cmt 0x9594` carries the measured number.

**AND IT IS RUN, POINTED SOMEWHERE THE HARNESS SURVIVES.** 10 MB of screen cursor walks straight
through the band the oracle keeps its own machine stack in; the first measurement returned a
correct-looking run only because one row ended a single byte short of the pushed return address.
So the case points `screen_back` one byte past the image: all 65,536 rows are dropped by the same
guard on both sides (4,653,254 instructions, 1.37 s of oracle — the suite's tail-setter now, a
registered watch-item), and what it pins is the CONTROL FLOW — the two cursors to the row, `d7` at
`$ffff`, whole-image byte equality and every struct register. Batch 14's `os_in_image` addressing
is what makes it survivable, and this is the batch it was added for. Stated in the docstring: two
implementations agreeing, not three — 65,536 rows of Python cost tens of seconds against the
machines' 1.4. Whether `SPRITES.CRU`'s real descriptors carry a negative height is NOT
establishable from the image; reachable-by-data, unpinned in fact.

**THE MUTATION SWEEP: 36 mutations, 34 killed, both survivors argued or registered.** One is
equivalent by construction (a redundant table-base assignment ADDED before the loop; removing the
in-loop one IS killed, so "rebuilt every record" is pinned). The other is a real, registered
unpinnable: **`ext.w d2` on the width-code byte** — the only byte the sign extension changes has
bit 7 set, and every such byte is a width code outside the four-entry table, which always `jsr`s
through garbage. The C refuses it, the battery refuses it, and the claim lives in `src/blit.c`'s
dispatch comment and this list rather than in a test — the review found the test that claimed to
guard it was a tautology, and it was deleted rather than kept for its name.

**THE REVIEW GATE FOUND TEN; THE TWO THAT MATTERED MOST WERE COVERAGE, BOTH MUTATION-PROVEN.**
Eight finder angles + verification; the C-vs-asm read came back exact (all 204 bytes and every
branch displacement hand-checked). What the fixes changed:

* **A SKIPPED RECORD'S CURSOR WAS UNOBSERVED.** Every skipping case sat in slot 0, where a later
  record's in-loop `lea` rebuilds a4 — so resetting the descriptor cursor before the above-band
  early return survived all 2,387 cases. A new case puts the skipped record in the LAST slot and
  reads the cursor the skip left behind; the review's mutation now reddens exactly it. The
  wholly-above-band case's docstring also stated the reading BACKWARDS (the cursor IS moved before
  the `bmi`) and is corrected.
* **THE NEGATIVE-X STEP-BACK CASE ASSERTED NOTHING** — `min(writes)` is always the clip-mask byte,
  below every screen address. The ordered repair (`min` over the screen writes alone being below
  the window origin) turned out UNSATISFIABLE — the left clip skips exactly the columns the
  step-back covers, so a left-clipped blit never writes below the origin — and the shipped
  assertion is the equality that is true and sharp: the lowest drawn byte IS the origin plus one
  stepped-over column. Both halves reproven by executed mutations.
* **The rest:** the model read the descriptor's source pointer at a hardcoded offset 0 instead of
  `DESC_SOURCE`; two unobservable intermediate register stores (the clamp's d2, the cursor's first
  d1) are deleted with the policy now stated in the C — the register FILE is modelled at
  observation points, intermediates only where observable, the dead d5 being the observable one;
  the runaway refusal no longer fires for wholly-off-screen records (whose preludes return before
  any row loop); `WB_SPRITE_LAST_ROW` is pinned to `WB_BG_BLIT_SCANLINES - 1` in the geometry test
  (a compound `#define` would fall out of the `layout.py` scrape — the reason is written beside the
  literal); the wrap case's 20-byte poke — which lands inside `bg_tile_bitmaps` by luck — and the
  descriptor filler's "must not reach `SPRITE_SOURCE`" bound are both ASSERTED now
  (`test_the_bands_a_pass_case_seeds_do_not_overwrite_each_other`); the pass-call tuple became a
  namedtuple, the 22 single-sprite sites a `_run_one` helper, the model's register writes a
  `put()` helper; three C helpers narrowed to the blit half of the struct so `sprite_dispatch`
  alone says it can move the walk's own cursors.

**Encoder ledger — FOUR REGISTERED TRIGGERS HAD FIRED, AND THE FIX PASS HONOURED THEM.**
`clr_w_dn`, `cmp_w_dn_dn`, `andi_w_dn` and `asr_w_imm_dn` were each parked at two users and this
batch was the registered third — all four went to `test/leaf.py`, plus `asl_w_imm_dn`, which
shares `asr`'s base opcode over one direction bit and would otherwise have re-split `0xe040`
across files. test_actor's redundant `| (1 << 6)` spelling died in the hoist; every battery's
whole-body entry pins prove no assembled byte moved. `adda_w_imm_an`'s two copies had OPPOSITE
argument orders (the `or_w_dn_postinc` hazard again) — reconciled to `(reg, value)` in both
files, parked at two users. `cmpa_l_imm_an` was test_actor's `cmpa_l_imm` under a second name —
renamed to match, parked at two users, ALSO-IN docstrings both sides. Still single-user in
`test_blit.py`: `ext_w_dn`, `movea_l_ind`, `add_w_d16_dn`, `cmpi_w_dn`, `muls_w_dn_dn`,
`suba_l_dn_an`, `adda_w_dn_an`, `jsr_ind`, and `s8` (`ext.w` after a `move.b`; `leaf.s16` one size
down). Usual terms throughout.

**What this batch does NOT pin:**

* **A WIDTH CODE OUTSIDE 0..3**, and with it the `ext.w` above. The original `jsr`s through the
  longword past the table; the C returns, the battery refuses.
* **THE RUNAWAY'S PIXELS.** The only way to make it draw is to point it into the image and let it
  march over the harness's own stack.
* **WHETHER THE GAME'S OWN DATA REACHES THE RUNAWAY.** The descriptors come off disk.
* **THE OTHER TEN BYTES OF A DESCRIPTOR.**
* **WHOSE POINTER `subq.w #6,a5` UNWINDS** — unchanged, and for a better reason: reading the pass
  RULED THE OBVIOUS ANSWER OUT (it walks in a6) rather than leaving it open.

**QUEUED, registered rather than half-done:**

* **THE KIT HAS A STACK-BAND BLIND WINDOW.** Writes in the 1 KB call-frame scratch below
  `STACK_TOP` are excused by `on_machine_stack` and excluded from the byte diff, so a case whose
  DESTINATION walks through that band would compare the reconstruction against an oracle run that
  corrupted its own frame, silently. The runaway case dodges it by pointing past the image;
  **trigger** = a second case that runs with a destination outside a screen buffer, **home** =
  `tools/recreate_kit/harness.py` beside the existing stray-write refusal (a kit change, in its
  own commit, per convention).
* **THE STRUCT-REGISTER-FILE GLUE IS AT ITS THIRD USER** (test_map's probe, `_blit_glue`,
  `_pass_glue`) — the in-file machinery is single now (both glues share `_fill_blit_regs` /
  `_read_blit_regs` parametrised by field map), and the cross-battery home is registered:
  **trigger** = a fourth user (batch 16's caller being the likely one), **home** = `test/leaf.py`
  beside `register_glue`.
* **THE `video (sprite blitters)` SUBSYSTEM ROW re-measure** — now covering `$8f02..$989c`, 100 %
  ported; a measurement, queued as one, folded with batch 14's identical entry.
* **THE RUNAWAY CASE SETS THE SUITE'S TAIL** (1.71 s under `-n auto`). Fits today; a second long
  pass case on the same worker is where wall time starts to move.

### Batch 16: the sound module opens, and the status panel CLOSES end to end

Two commits, because half of it was a tool defect: **16a** (its own commit) diagnosed and fixed the
`$bca2` scan gap — the batch-3 register entry above carries the closure, `PORTABILITY.md` §0d the
deltas, and the headline is that Ghidra's 68000 sleigh models `jsr (d16,An)` one dereference too
deep and TEN resolved call edges were being dropped image-wide. **16b** is the port the diagnosis
unblocked: `snd_trigger_effect` ($1a48a, 334 B) + its stub `snd_call_trigger_effect` ($17b14,
14 B) into the new `src/sound.c`, then `panel_frame_timers` ($bbca, 268 B) and
`panel_refresh_frame` ($b346, 44 B) — **verified 151, 16,290 bytes, and the thirteen-batch panel
story is CLOSED: all ten of the pass's callees green, entered at the top, one composed
differential.**

**THE SOUND MODULE IS OPEN, AND NARROWLY — BY DESIGN.** $1a48a is the one routine in
`$17adc..$1abc8` that touches nothing but RAM, so it is the one the differential can see whole. A
green suite here says the right bytes landed in the right module fields and NOTHING about audio:
the sound is made by the per-VBL tick at `$17c74` (PSG ports, supervisor mode), which stays
unported behind the differential PSG wall. What the read established: THREE arms, not two (0 = A,
1 = B, anything else = C, only d1's low byte compared, the third arm with no test of its own), the
same fifteen instructions over four base-plus-stride blocks, the noise byte SHARED across channels,
the five field stores reading their sources BACK OUT OF THE COPY, and state+17 never written.
`../names.txt`'s sound block carries the corrections, six new `var` lines, and the five timer
words' true names — including `panel_frame_rewind` ($bd30), the one word `stage_reset_state` does
not touch.

**THE PASS CARRIES ONE LIVE REGISTER BETWEEN TWO CALLEES, AND IT IS DATA.** $b346 sets neither d0
nor d7 before any of its ten calls. d7 is buried by both readers; d0 is forced to zero by $b5ea's
`moveq` before the score draws — but $bd32's font select is whatever $bbca left, which is
`hud_blit_panel_frame`'s last `movem`: the panel frame's LAST ROW, FIRST LONGWORD.
`hud_blit_panel_frame` and `panel_frame_timers` therefore RETURN that value. All thirteen shipped
frames hold `$1000e000` there, so the alternate font is unreachable on the game's own data; a
poked frame reaches it, which is what makes the flow observable rather than argued.

**THE MUTATION SWEEP: 30 of 33 killed**, one real coverage hole found and closed during it (the
channel clamp — no case passed a d1 of 2 or 3 until the selector sweep), and three survivors
argued equivalent and commented where they live: a record copy one byte LONG (the next store
overwrites state+14 unconditionally), the `sf` that disarms the channel (the flag ends at 1 either
way — that store exists for the VBL tick, an interrupt the harness does not model), and the meter
floor's strictness (a charge landing exactly on zero stores zero on both arms).

**THE REVIEW GATE FOUND TEN; TWO WERE MUTATION-PROVEN COVERAGE HOLES, BOTH NOW CLOSED:**

* **THE FORWARD COPY'S DIRECTION WAS UNPINNED — `memmove` survived all 693 cases.** The
  self-overlap cases pinned the copy's ORDER against the mix stores, never its direction, and the
  20 ids whose descriptor sits inside the state band landed in bytes the pristine image zero-fills.
  The fix seeds the band and adds the propagating class (ids $8f/$9f on channel C, source 11 and 4
  bytes below their own destination), with the model SIMULATING the byte-by-byte copy — a
  `memmove` now reddens exactly those cases. The model also gained a self-check that no case's
  volume stream lands inside a band the arm writes.
* **THE BLIT'S NEW RETURN WAS UNPINNED BY ITS OWN BATTERY** — mutating the returned longword left
  all 8 of its cases green and reddened only the tiers above. Its battery now asserts the return
  (and its d0 equality) for every index it draws.
* The rest: the `poison=False` justification named a byte that cannot cause the hazard (the meter
  MAX is rewritten before it is read; the true driver is the poisoned meter VALUE running $b61e
  16,374 blits) — reworded to the general truth, a composed pass's outputs are its later callees'
  inputs; a provably no-op `sign_ext16` under a comment claiming all three extensions load-bearing
  — deleted, comment now names the two that are; the encoder ledger's second regression in two
  batches repaired (leaf.py gains `jsr_abs_l`, `subq_w_dn`, `move_b_imm_d16` — a third-user found
  by the audit itself — `moveq`, `s8`, `LONGWORD_BYTES`, `image_glue(restype=)`; `clr_w_dn`'s
  re-forked byte literals deleted ONE batch after its hoist; six pairs parked at two users with
  ALSO-IN docstrings both ways; both files' false single-user ledger comments corrected);
  `WB_SND_TABLE_ENTRY_LEN` pinned through the header scrape (it was the batch's one unpinned
  cross-language constant); `sign_ext8` to the kit's `machine.h` beside `sign_ext16` (its own
  commit; blit.c's three inline spellings converted); the composed case's 1,711 allowed bytes
  pre-merged to 303 bands (77 → 17 ms measured); the channel sweep's duplicated dozen dropped
  (−12 cases, the sweep's claim is about B and C).

**What this batch does NOT pin:**

* **EVERYTHING THE TRIGGER ARMS.** Sound is made by `$17c74`; nothing here hears it.
* **The rest of the module's mutable state** — the music channel states, `snd_psg_shadow`, the
  PRNG. Deliberately unmodelled: $1a48a touches none of them, so a port that reached one reddens
  as a stray write rather than being covered by a model that does not exist.
* **The `sf` store's ordering purpose and the meter floor's strictness** (two of the three
  survivors) — invisible to memory.
* **`$bbca`'s d7 at the `rts`** — nothing reads it; the C returns only d0.
* **What the 13 frames depict**, what the meter means, and what the game DOES with the alternate
  font a poked frame reaches.

**QUEUED, registered rather than half-done:**

* **THE HUD-SUBSYSTEM PARTITION IS UNBLOCKED** — the condition its queue entry named ($b346
  ported) is met; a `subsystems.tsv` redraw + re-measure, folded with the two already queued.
  *(Batch 18: RUN — see the batch-18 section and `PORTABILITY.md` §0e.)*
* **THE DAMAGE PATHS ARE HONESTLY PORTABLE NOW.** `$69fe`/`$6b46` were rejected in batches 10 and
  13 for their invisible `jsr 56(a5)`; 16a made the edge visible and 16b ported its target, so
  their whole closure is green — the natural batch 17, alongside `$6bb8` whose T4 re-pricing
  (16a's one casualty) honestly needs the PSG-read model instead.
* **`LONGWORD_LEN` still has three out-of-batch spellings** (test_actor/test_blit/test_map/
  test_scroll, ~40 sites) — parked in `leaf.py`'s note beside `LONGWORD_BYTES`.
* **The `$17c74` per-VBL tick is the module's next wall** — supervisor-mode PSG writes; blocked on
  the seeded-PSG-read model the audio-capture work opened the door to.

### Batch 17: the two damage paths, and the arm that was never dead

`$69fe` (266 B) + `$6b46` (114 B) into `src/actor.c` — the pair rejected in batches 10 and 13 for a
`jsr 56(a5)` that batch 16a made visible and 16b made portable. **Verified 153, 16,670 bytes,
64.6 %; `make test` 2729 in scope (clean tree 2742).**

**THE FIRST GAME RULE THIS PROJECT HAS READ, not just a mechanism.** Each path spends a HUD slot
one charge at a time and falls back on a second pool when the slot is empty — and the message each
posts as its slot empties NAMES it. Resolving the ids through the message table in the image:
id $18 (record $17) = `"   Helmet is Broken"`, id $19 (record $18) = `" Gauntlet is Broken"`. So
`$bbbe` is the HELMET, absorbing hits instead of `hud_meter_value`, and `$bbc0` the GAUNTLET,
doubling the damage `$6b46` takes off the enemy's template pool. Both were "meaning not
identified" in `../names.txt` for fifteen batches; the string resolutions are pinned by a case,
and the slot identification is the reading those pins support — stated at that strength
everywhere it appears.

**THE B ARM WAS NEVER DEAD.** Batch 16b recorded `snd_trigger_effect`'s B and C arms dead on
"every call site passes d1 = 0" — inherited from `notes/sound_module_recon.md`, whose call-site
table was missing exactly the `$6b46` row (the same indirect call the hardware scan dropped until
16a). `$6b46`'s second instruction is `move.w #$1,d1`, reached from 25 control-flow sites. Every
surface is corrected — `../names.txt`, `sound.h`, `test_sound.py`, `wonderboy.h`, the note itself —
and `SHIPPED_CALL_IDS` is now DERIVED from a stated 26-site call-site table that a whole-program
`lea $17adc.l,aN` scan must equal (the guard that would have caught the missing row), which also
surfaced that id 19 on channel B — the one shipped (id, channel≠A) pair — had no case in the
owning battery. It does now, and a one-stride mutation of the B arm reddens it plus 39 actor cases
while every channel-C case stays green.

**FOUR CORRECTIONS TO BATCH 13'S PRE-PORT READ, all from the bytes:** `$69fe` reads the mode flag
ONE SIZE DOWN (`tst.b $a32.w` — the word's HIGH byte, where all twelve other readers are `tst.w`;
$0001/$00ff pick the OPPOSITE record from `followed_actor_record`'s `bne`, and `cmt 0xa32`'s
"thirteen `tst.w` readers" was wrong); `$6b46`'s doubling was INVERTED (it runs on both arms that
spend a charge; only a slot already empty on entry skips it); the caller counts were `bsr`-only
(38 and 25 control-flow sites — the tail jumps are how the per-type actor routines end); and
`19(a0)`'s SIGN BIT is a discriminator (a byte >= $80 carries the damage in its own low seven
bits, no table read at all).

**THE DAMAGE TABLE FIXES BOTH EXTENTS.** `$6b08..$6b45` is 31 words of DATA between the two
bodies — one `lea` reference, 25 entry sites landing on its far end, six distinct shipped values,
unbounded from either end (the type index is a sixteen-bit-wrapped LONGWORD, so $4000 reads 64 KB
above the table). `../names.txt` carries its plate.

**THE MUTATION SWEEP: 36 of 37 killed** (+ the reviewer's independent 19, 17 killed 2 equivalent).
The one survivor is the meter floor's strictness — the same `subq/bpl/clr` equivalence
`panel_frame_timers` registered in batch 16. The sweep also caught its own seeding weakness
(one seeded template record; the $7f slot outside the band) and fixed it before the final run.

**THE REVIEW GATE FOUND TEN; the C-vs-asm read came back exact twice** (the batch's own sweep and
Angle A's independent 19-mutation pass). What the fixes changed: the id-19 coverage above; the
three stale dead-arm surfaces; the two encoder hoists COMPLETED across all four batteries (they
had landed additive-only — three live definitions per encoding with docstrings claiming
migration — the third ledger regression in three batches, now with the completeness-scan pattern
as the countermeasure); `WB_ACTOR_FLAGS2_STRUCK_BIT` renamed `WB_ACTOR_FLAGS2_BIT_0` per the
offset+role convention for unestablished semantics (its own $709a caller's raise-across-call /
clear-on-return shape reads as a guard, which is evidence AGAINST "struck"; the site count is 49
bset, the 49th being this batch's own a1 site); the slot-rearm twin pinned
(`layout.py` scrapes `effects.h` as a third header and
`test_the_two_headers_spell_one_slot_byte` holds `WB_HUD_SLOT_REARM & $ff == WB_HUD_SLOT_CHANGED`);
the gauntlet cases' expectation computed from the override alone (it agreed with default+override
only because the default is zero); two dead runner parameters removed; three inline high-half
masks routed through `leaf.set_low_word`; the record-vs-id numbering comment fixed (id $18 is the
helmet's ID and the gauntlet's RECORD — both bases now spelt out, each constant beside its own
string); and the two measured grid trims (−44 runs re-making already-made claims, all 44 image
classes verified distinct first).

**What this batch does NOT pin:** what a helmet/gauntlet charge or a meter unit DOES (the
consuming tier is unported); `WB_ACTOR_FLAGS2_BIT_0`'s purpose — the busiest bit in the image (49
bset / 36 bclr / 33 btst against 9(An)); `WB_ACTOR_FIELD_31`'s meaning; and whether the game's
own data can reach the out-of-range damage-table types (the template table is disk-loaded; every
type in those cases is seeded).

**Registered rather than folded in:** `$b444`'s first byte is a 0..4 attack level that ALSO serves
as `effect_record_list`'s emptiness sign (`../names.txt` addendum); `21(a1)` is the
flicker/invulnerability countdown `$f14` runs down; `test_stage.py`'s unused `forward_branch`
import (pre-existing, noted by two consecutive fix passes — next touch of that file should drop
it).


### Batch 18: the HUD partition — the largest mis-partition, drawn and measured

The measurement queued since batch 15 and unblocked by 16b, run per the house discipline: the
unmodified partition reproduces every committed §0d figure first, then `subsystems.tsv` gains four
`hud (status panel)` ranges cited on the spot, and the re-run differs in EXACTLY ONE hunk. **No
code changed, no test moved** (`make test` 2742 before and after); [`PORTABILITY.md`](PORTABILITY.md)
§0e is the full record.

**THE HUD ROW IS THE FILE'S CLEANEST: 62 functions / 3,372 bytes, T0 CLEAN direct AND transitive,
100 % runnable, 100 % reconstructed** — the pass and its ten callees with every tier under them
(`$b346..$bd66`), the region-restore family (`$d93a..$dbb0`), the effect/state stubs that write
the panel's slots and state words (`$10200..$103e8`), and `hud_draw_lives` (`$e80c`). Sixteen
batches of panel work, one row.

**THE CATCH-ALL IS DOWN TO 24 FUNCTIONS / 3,328 BYTES** (from 138 before the first re-measure),
runnable 14 / 1,290 B — and its largest single remainder is now `FUN_0000dbc0` (932 B, unported,
unnamed, the routine after the panel restores), which is thereby the natural next READ. All three
queued measurement entries are closed: this partition, batch 15's sprite-row re-measure
(discharged — §0d had already measured the redrawn range), and batch 14's folded copy.

**What a partition cannot move, it did not move**: every whole-program figure is byte-identical
across the two runs, diffed rather than argued.


### Batch 19: the SCENE tier — the dialogue engine, ported to its boundary

`$dbc0` (932 B) + `$de80` (58 B) into a new `src/scene.c` — the catch-all's largest remainder,
batch 18's nominated next read. **Verified 155, 17,660 bytes, 68.5 %; `make test` 2912 in scope
(clean tree 2925).** `$dfbe` (`scene_exit_and_reload`) is read, named and NOT ported — three
independent reasons, below.

**BOTH MODE FLAGS FINALLY SELECT SOMETHING.** `state_flag_a30` hands the routine the scene
descriptor `record_ptr_10420` names — kind 1 a speech script, kind 2 the SHOP — and
`state_flag_a32` hands it kind 4, the eight fragments a defeated boss leaves. Fifteen batches of
"it is a boolean and WHICH mode it selects is not established" close here. THE READING IS PINNED
BY THE MESSAGE TABLE, batch 17's method: the farewell arm's hardcoded ids resolve to
`" Please come again."` and `"  Never Come Back!!"`, and speech script 0 to the game's opening
four lines. What any shop SELLS is not pinned — descriptor and records are disk-loaded; every
case seeds them.

**PORTED TO A BOUNDARY, AND THE CONVENTION SURVIVED ITS REVIEW STRONGER.** Four exits transfer to
`$dfbe` and one to `$1ab4`; both end in `jsr stage_load_window`, whose palette write the oracle
silently drops — so the C returns WHICH tail it reached, a case runs the oracle with `stop_pc` at
that address, and the tail is witnessed POSITIVELY by the kit's coverage bitset on the transfer
instruction itself (`run_reaching` — one run, and it says which transfer fired). The review killed
the first witness (a raises-any inference satisfiable by any unrelated fault) and registered the
real home: the shim reporting `final_pc`, trigger = a third battery. Unblocking the tails needs
`$f95c` → `set_palette` + the module's song start — the PSG wall. `$101be` (exit-action entry 1)
is read by nothing and is a third independent reason `$dfbe` stays unported.

**THREE SHIPPED DEFECTS, reproduced:** the vector-page slips (`cmpi.w #$1,$2c.l`/`$28.l` where the
sibling reads a record field — the encodings differ by exactly a lost `(a1)`; dead on hardware,
and at `$dd42` it costs the shop its second greeting), the SIGNED `bgt` price compare on a packed
BCD purse (from 8000 gold every priced item is refused — reachable on the game's own data), and
the four push handlers' a1 clobber landing the visit spend 32 bytes into `effect_record_list`
(it broke the first reconstruction and the differential caught it).

**THE REVIEW GATE EARNED ITS KEEP FOUR WAYS, all executed:** (1) the stage-reset exit never left
the driver in any case — FOUR mutants survived (the ternary and all three arm-swallows); one
parametrized borrow-with-no-twin case through every spending arm kills them all. (2) The kind
ladder's exclusivity — the `rts` at `$dbec`, all that keeps the a30 arm out of the boss arm — was
outside the entry pin and untested; a fall-through port survived the suite and now fails one
case. (3) The collision-map seed band was silently DISCARDED by a dict-key collision, breaking
the poison-off argument's stated property exactly where the borrow path writes; re-keyed, with
the poke builder now refusing colliding bands. (4) The witness replacement above. Plus: the
descriptor word the map tier and scene tier had named twice with contradicting vocabulary is one
name now (`WB_SCENE_KIND`, `src/map.c` converted); `branch_w_to` hoisted (two users);
the ITEM tuples became NamedTuples (killing an identity-comparison trap); 23 redundant full-shop
runs folded; and **the mutation-runner recipe is finally IN THE REPO** (`README.md`, beside a
citation of this batch's own 0/37 piped-pytest defect — the sweep first scored `tail`'s exit
status, reported zero survivors having compared nothing, and was rebuilt unpiped; the fifth
scratchpad copy of the correct runner shape is the last).

**THE MUTATION SWEEP: 39 designed, 39 killed** (after the runner fix), plus the review's
independent mutants (4 exit-propagation + 1 ladder fall-through, all now killed; its control
mutant killed on the first run). The one genuine first-pass survivor (`a32 >= 0` vs `> 0`) was a
real hole and its case is in the battery.

**EFFICIENCY, measured and exonerated:** the battery is 1.15 ms/case — the CHEAPEST in the suite,
+0.38 s total — and the apparent wall-time doubling my clean rebuild saw was a concurrent Blender
render at 736 % CPU, proven by reproducing the slowdown on a HEAD worktree with none of this
batch in it. Two suite facts recorded: `-n auto` is non-monotonic under external load (check
`uptime` before diagnosing a timing anomaly), and the suite's real cost center is
`test_blit.py`'s 76.6 ms/case sweeps.

**What this batch does NOT pin:** anything past a boundary; `$101be`; an effect index outside
0..22 (refused, sprite-dispatch precedent); the three farewell record words the original loads
and discards; the register file at exit; what the three shop spots (`$33`/`$be`/`$78`) are; and
the shipped shops themselves.

**QUEUED, registered rather than half-done:** a `scene (dialogue + shop)` `subsystems.tsv` row —
a measurement, queued as one *(batch 20: RUN — §0f; the first row where reconstructed exceeds
runnable, which is the boundary convention priced honestly)*; the shim reporting `final_pc` (home registered, trigger = a third
checkpoint battery); `$17c74` (the per-VBL tick) and `stage_load_window` remain the PSG wall's
two faces, and they are now what stands between the scene tier's tails and a full close.


### Batch 20: the scene row — reconstructed exceeds runnable, and that is the finding

The measurement batch 19 queued, run per the house discipline (baseline pinned, two cited rows,
one diff hunk, whole-program figures byte-identical). [`PORTABILITY.md`](PORTABILITY.md) §0f is
the record. **`scene (dialogue + shop)`: 3 fns / 1,094 B, direct T0 CLEAN, transitive T4,
runnable 0 — with 2 of 3 reconstructed and green.** No scene function touches hardware; none can
run WHOLE under the oracle (every one reaches `stage_load_window`'s sound call through the exit
tails); and the batch-19 boundary convention is exactly what porting does about that gap. The
catch-all falls to **21 fns / 2,234 B**, its runnable column unmoved — the three departures were
already in its unrunnable residue. `make test` 2925 before and after; no code changed.

### Batch 21b: the stop chain, the PRNG, and the first defeat — the seeded PSG model's first consumer

Six functions, 442 bytes, and one of them is the first ported code in this project that **drives the
YM2149**. They landed together because they are one dependency chain: `$6bb8` cannot run without the
stop chain, and the stop chain could not run at all until the kit gained the seeded PSG read model
(`tools/recreate_kit/TRAP_MODEL.md`, "Phase 6").

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$17f30` | `snd_psg_silence` | 82 | the module's silence: read the mixer back, `ori #$3f`, zero the three volumes |
| `$1aaea` | `snd_stop_all_sfx` | 26 | stub +70 — clear the SFX flags, mirror the four registers into the shadow, tail-jump |
| `$17f24` | `snd_stop` | 12 | stub +28 — clear the engine flag, tail-jump |
| `$6bb8` | `actor_defeat_and_score` | 164 | what a defeated actor costs, and the boss block above it |
| `$68c6` | `rng_next` | 108 | the game's PRNG, ten callers |
| `$e1f0` | `stage_random_kind8` | 50 | one of eight candidates for the current stage |

**Why `snd_psg_silence` is the interesting one.** `ori.b #$3f,d1` sets the six tone/noise enable
bits (active low) over a byte it has just **read back from the chip**, and what that preserves is
bits 6–7 — the port A/B I/O **direction** lines the floppy drive-select depends on. Before Phase 6
the oracle had no correct answer for that read; a fabricated `0` would have made `0 | $3f` and
`read | $3f` agree, so a reconstruction that ignored the read-back would have been **green** while
writing `$3f`, flipping port A to input and floating the drive-select lines. A case now declares the
byte with `psg_seed={7: …}`, both cores are served it, and the ordered access ledger and the register
file are compared alongside the image — none of which is IN the image. One case declares **nothing**
and requires the oracle to refuse the run, which is the guard the other twenty-one rest on. That
mutant (`ignore the read-back`) is in the sweep and is caught by the ledger alone.

**Four plate corrections, all read off the bytes.**

* `cmt 0x1aaea` said the routine "zeroes the SFX mix volumes (`$18360` block)". **Wrong.** `$1738c +
  4045/4046/4048` is `$18359/$1835a/$1835c`, which is `snd_psg_shadow` **indexed by PSG register
  number** — so its four stores mirror `snd_psg_silence`'s four chip accesses exactly, and the SFX
  mix block is untouched. `WB_SND_PSG_SHADOW + WB_PSG_REG_MIXER` is how the header says it now.
* `cmt 0x17f24` said snd_stop "falls into" snd_stop_all_sfx. It is a `bra.w` — a **tail jump**, and
  so is `$1aaea`'s into `$17f30`. Three separately reachable entry points into one tail, which is why
  each is a function here and each case states the module state ITS entrant is entitled to write.
* `cmt 0x6bb8` called the routine "structure only, meaning unidentified" and gave it Ghidra's **290
  bytes**. The body is **164** (`$6bb8..$6c5b`); the 290 folds in the 128-byte score table at `$6c5c`
  and stops two bytes short of its end. The meaning is now read: pay the score, count the kill, free
  the slot, re-arm the template. `WB_SPAWN_KILL_COUNT`'s header comment cited `$6bfa` for its `addq`,
  which is the `movea.l` that loads the record; it is `$6c2a`. It also counted **five** control-flow
  sites (four `bra.w` and the Copylock's `jmp`). There are **twenty-nine**: those five plus
  **twenty-four `bne.w`** (`$2556`, `$272c`, `$70aa`, …), each of them a per-monster state routine
  ending `bclr`/`btst #3,9(a0)` and branching here when `WB_ACTOR_FLAGS2_DEFEATED_BIT` was set. So
  this is not an obscure tail off a protection failure — **it runs on every monster death**, which is
  also what makes the unported `$6cdc` continuation hot code rather than a corner.
* `cmt 0x68c6` said the three counters advance "modulo `$25`/`$17`/`$11`". They do not: each is
  `addq.w #1 / cmpi.w #N / bne / clr.w`, an **equality** test, so a counter seeded at or above its
  limit never meets it again and runs on to `$ffff` and round. The game's own state cannot tell the
  two readings apart (all three start at 0) — only a seeded case can, and one per counter does.

**`$6bb8` stops at a boundary, the shape batch 19 established.** `ble.w $6cdc` leaves the 164 bytes
for a respawn continuation that rebuilds the slot as a new creature; that continuation is not
reconstructed, so the C returns WHICH exit it reached (`WB_ACTOR_DEFEAT_RETIRED` /
`_RESPAWN`, in `include/actor.h` as `include/scene.h`'s three are) and a case runs the original with
`stop_pc = $6cdc` **plus the witness** that the `ble.w` executed — `leaf.run_reaching`, hoisted out
of test_scene.py this batch because a second battery needed it. *(Batch 22: the boundary is gone —
the continuation is ported, the exit codes now report which tail RAN, and the witness stays.)*

**It is also the battery that imports the most.** `$6bb8` calls five reconstructed routines, and each
is compared through the battery that owns it: the SFX trigger's write set and the stop chain's PSG
ledger from `test_sound.py`, the packed-BCD accumulator and the meter clamp from `test_hud.py`. Two
models were made public for it (`bcd_expected`, `meter_add_expected`), the way `test_stage.py`
imports `model_lives_draw`.

**The PRNG is DEGENERATE under this oracle, and `test_rng.py`'s docstring opens with it.** The
entropy term is `$ff8209 ^ $b39a` — the shifter's video-address counter XOR the frame tick — and
`$ff8209` is off the image, so both cores are served `0` and the generator collapses to a
deterministic function of three counters and one frame counter. Every case in that file is green
about a generator with no randomness in it: a **T3-DATA false green**, registered in `../names.txt`'s
`cmt 0x68c6` before this batch and now stated where a reader of the cases meets it. `src/rng.c` reads
the port's own address through `os_in_image` rather than writing a `0`, which is the honest form of
the same instruction — and **no case can tell the two apart**, which is the cost.

What the cases DO pin exactly: each counter on both sides of its own wrap, and the wrap is a **clear
at equality**, not a modulo — a counter seeded at or above its limit never meets it again and runs on
to `$ffff`. That is the difference `(n + 1) % limit` would get wrong, and a mutant for it is caught.

**`$e1f0` reads `stage_number` as PACKED BCD**, which is what `cmp.w #9 / ble / subq.w #6` is:
subtracting 6 turns `$10..$19` into 10..19. `hud_draw_stage_number` drawing that word's low byte as
two digits is the other half of the reading. Its table is self-bounding at both ends — the sibling
draw's 32-wide table ends on its base, and three longword handler pointers begin where it ends — and
its sibling `$e1c8` **branches into its tail**, so the last fourteen bytes belong to both and a case
pins them against the sibling's `bra.w`.

**Not pinned, honestly.**

* **The generator's randomness**, above. Irreducible under a memory differential.
* **The extend bit `$6bb8` hands the score accumulator.** `lsl.w #2,d2` leaves X holding the spawn
  type's **bit 14**, and `bcd_add_score_bd70`'s first `abcd` folds the caller's X into the lowest
  digit pair; `src/hud.c` reproduces the X = 0 entry only, because `emu.run` has no entry-CCR
  parameter (TRAP_MODEL.md, "The entry state every run begins from"). Every shipped spawn type has
  bit 14 clear, so the game never reaches it — and `test_actor.py` **refuses** a case that would,
  rather than letting one pass silently. This is the second site of the entry-X limitation already
  registered for `$e058`/`$e064`.
* **The supervisor window.** `snd_psg_silence` masks interrupts around its chip writes; there is no C
  analogue and no interrupt to keep out, and the oracle enters every run at `$2700` already. What IS
  observable is the saved SR arriving in d2, and one case asserts it.
* **The respawn continuation** at `$6cdc`, and with it `$e1c8`, `$e1f0`'s one real caller, and what a
  "kind" means past the record fields it fills. *(Batch 22: both are ported and green — see its
  section below; what a "kind" MEANS past the fields it fills is still open.)*
* **`snd_psg_silence`'s select latch.** The candidate selects and accesses in one call, so a driver
  whose only effect were leaving a register selected is not expressible — the kit's own limitation,
  restated because this is its first game-side consumer.
* **`snd_psg_silence` CANNOT LINK INTO A `.PRG` YET**, and it is the first reconstructed routine here
  of which that is true. `psg_port_write`/`psg_port_read` live in the kit's `src/psg.c`, which is
  **off-target only** (`psg.h`: "a build for the real Atari writes the ports itself and does not
  compile `src/psg.c`"), so this routine is verified against the original and still has no on-target
  body. Every other ported byte in this project is target-buildable today. Closing it is a KIT task —
  an on-target psg backend that writes `$ff8800`/`$ff8802` — not a reconstruction one, and until it
  lands the stop chain is differential-only.
* **The generator's XOR, as an operator.** With the video term at `0`, `^`, `+` and `|` all agree,
  and the sweep confirms it: that mutant is the batch's one survivor. Closing it needs the harness to
  serve a nonzero video counter, which would be `shim.c`'s invention rather than the game's data.

**Mutation sweep: 51 mutants, per README.md's recipe** (forced relink, unpiped returncode).
**50 caught, ONE irreducible survivor** — 48 over the batch as written, plus three over the
review pass's fixes below. Three of the 48 survived the first pass, and two of those were real
coverage holes, closed by cases rather than waved through:

* **`^` -> `+` on the entropy term SURVIVES, and cannot be closed.** The video byte is `0` on both
  sides, and `0 ^ tick` is `0 + tick` — so the *operator* is unobservable for exactly the reason the
  randomness is. This is the false green above, measured: not a missing case but a consequence.
* **`>` -> `>=` on the BCD ladder** survived because stage 9's two candidate rows (8 under the strict
  reading, 2 under the other) hold the SAME byte at six of their eight draws — the sweep's case
  happened to land on one of the six. Closed by a case that picks its tick so the draw is one of the
  two they disagree about, with a guard that computes that rather than assuming it.
* **the closing `andi.l #$1f`** survived because every byte of the table's own 176 is already at or
  below the mask (a case here asserts exactly that), so over the table the mask is a no-op. It is
  observable only where the UNBOUNDED index leaves the table — which the instruction does freely —
  so the closing case seeds a stage number whose row lands on the game's own code at `$e6a2`, whose
  eight bytes are all above the mask. Real shipped data, not a fabricated record.

**The review pass added five more pins, four of them re-verified by the mutants they kill** (five
mutant runs, same recipe: forced relink, unpiped returncode, green tree immediately before each):

* **the 24-bit ADDRESS BUS.** `add.l d2,d0` can carry `$e1f0`'s index above `$00ffffff`, where the
  68000 wraps it back into the machine and `src/rng.c` was falling through its off-image guard to 0
  instead. Fixed with `WB_BUS_ADDR_MASK` and pinned by a case at `d2 = $01000000`, which reads the
  very byte a `d2` of 0 does; dropping the mask reddens exactly that one case and no other.
* **the WIDTH of that mask.** "Present or absent" is not the whole claim — a bus one bit too narrow
  reproduces the case above, and `& (WB_BUS_ADDR_MASK >> 1)` survives it. A second case at
  `d2 = $00800000` sits on the bus's top bit: masked to 24 the read is off the image and served 0,
  masked to 23 it would come back round onto the table and read a real byte.
  **And the sweep then found a hole in the fix itself**: a mask one bit NARROWER (`>> 1`) survived
  everything, because "present or absent" does not pin a WIDTH. Closed by a third case at
  `d2 = $00800000`, whose read is off the image at 24 bits — served 0 — and back ON the table at 23,
  with a guard requiring the narrower reading to land on a nonzero byte so the two cannot agree.
  The transferable lesson: **an off-image guard on a 68000 address is only correct after the bus
  mask**, and `src/blit.c`'s off-image words are worth re-reading against it.
* **the BCD ladder's SIGNEDNESS**, distinct from the strictness above. Stage `$8001` — `$8000` was
  tried first and pins nothing, because both rows it chooses between lie in a run of zero bytes,
  which the case's guard now computes rather than assumes.
* **the boss gate's `tst.w`**, at `$0100` and `$00ff` — the two flag words with one zero byte, which
  between them separate the word read from a read of either half. `$0000`/`$ffff`, the only values
  the game itself writes, agree with all three readings; the low-byte and high-byte mutants redden
  one case each, and neither reddens the other's.
* ...and one pin with no mutant to kill: **the extend bit is refused where a case is SEEDED**, not
  tallied afterwards. `_defeat_pokes`
  asserts bit 14 is clear on every spawn type it is handed, so the unpinnable above cannot be reached
  by a future case that simply forgets the list.

The sweep also caught a lie of its own, worth recording beside the two the README already documents:
a run in which the SUITE does not collect reports every mutant as caught. An encoder hoisted out of
two batteries without adding it to their import lists broke collection, and the three survivors came
back "caught" until the tree was green again. **Check the suite is green immediately before the
sweep, not merely before the batch.**

**Kit friction, filed as signal** (this batch is Phase 6's first game-side consumer):

* `leaf.run` had no `psg_seed` parameter — every project's batteries go through it, so the kit's
  newest capability was unreachable from a leaf case until this batch threaded it.
* `emu.run` refuses an undeclared read with a `RuntimeError` naming `psg_seed={7: <byte>}`, which is
  exactly the right message; nothing needed changing there.
* **`osh_run` counts one instruction past the routine's own `rts`.** A cap of exactly the body's
  length reports "did not reach rts". Measured here and named (`RUNNER_SENTINEL_INSN`) rather than
  absorbed as slack, because three batteries now derive caps from instruction counts.

### Batch 22: the respawn continuation — the defeat path, end to end

Two functions, 166 bytes, and the point of them is that batch 21b's boundary is **gone**:
`actor_defeat_and_score` now runs to the original's own `rts` on every arm, and the two
`WB_ACTOR_DEFEAT_*` codes report WHICH tail ran rather than where the run stopped. **Verified 163,
18,268 bytes, 70.8 %; `make test` 3133** (3052 before the batch, plus its 81 net: +49 in
`test/test_rng.py`, which stands at 103, and +32 in `test/test_actor.py`, which stands at 984 —
three measured trims inside those figures, below).

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$6cdc` | `actor_respawn_as_new_kind` | 126 | draw a kind, rebuild the dead record out of it |
| `$e1c8` | `stage_random_kind32` | 40 | one of thirty-two candidates for the current stage |

**`$6c38` HAS THREE ENTRANCES, which nothing had recorded.** The unscored type's `beq`, the kill
count's `ble` falling through — and the continuation's own `bmi.w $6c38` at `$6d0a`, taken when the
template FORCES a negative kind. So a defeat under the kill limit can still free the slot, which is
exactly why the C keeps reporting an exit code instead of deriving one from the kill count. The tail
is a `retire_slot` helper in `src/actor.c` for the same reason it is one block there — and after the
review pass the helper RETURNS `WB_ACTOR_DEFEAT_RETIRED`, so tail-and-code is one fact spelled once.

**The two draws are ONE routine, and now one C body.** `$e1c8` is `$e1f0` with three operands
changed — the table, the row shift, the draw mask — and no tail of its own: it `bra.w`s into
`$e1f0`'s last fourteen bytes. `src/rng.c` spells that as one static body with three parameters, and
`test_rng.py`'s whole draw section became ONE set of cases over two descriptors: a claim proved for
only one of them would be a claim about an operand rather than about the routine. The seeds cannot
be shared — each table's own bytes decide which stage and which draw make a reading observable — so
every seed is keyed by descriptor and carries a guard that COMPUTES why it was chosen. `$e1c8`'s
table has ELEVEN rows where `$e1f0`'s has twenty-two, so a stage past 11 walks off its end onto its
neighbour, which is now a case on the game's own bytes.

**Four plate corrections, all read off the bytes.**

* `cmt 0x6bb8` said the continuation "rewrites six of the record's fields". It is **nine writes over
  ten offsets**: the kind byte, the three bit ops on `WB_ACTOR_FLAGS`, four literal bytes, the two
  words out of `actor_kind_table` and the size longword.
* `cmt 0x6bb8` recorded only two ways into the retire tail. There are **three** (above).
* `cmt 0xe1f0` said its one caller "reaches here behind a `moveq #0,d2`". The `moveq` is fourteen
  instructions earlier at `$6c14` and a `lsl.w #2,d2` runs after it, so the entry d2's LOW word is
  the scaled spawn type and only its HIGH half is zero. The conclusion survives; the reason did not.
  It is also the LAST of a template's respawns that reaches `$e1f0` — the earlier ones go to `$e1c8`.
* The body is **126 bytes, `$6cdc..$6d59`** — the first draft of this batch's own plates said 125
  ending `$6d58`, an odd length no 68000 body can have; the closing `rts` is `$6d58..$6d59`. Caught
  by the review gate against the binary; the entry pin had assembled the correct 126 all along, and
  a body-size row now pins the figure rather than leaving it prose.

**Two new data labels.** `actor_kind_table` (`$1044c`): 22 rows of 16 bytes, bounded above by twelve
longword CODE pointers at `$105ac`, of which only the first two words are read — the record's new
type and sprite. **Rows 0..20 all carry `actor_type_unscored`** and row 21 carries `$3d` — so a slot
that has come back once pays no score, counts no kill and never respawns again when it next dies —
and the case asserts that ORDERED shape, not membership (a review find: the set-membership form
passed on any table with one `$26` in it). And `stage_kind32_table` (`$e222`), self-bounding at both
ends: `$e1f0`'s body ends on its base and `stage_kind_table` begins where it ends.

**Where the bus mask is, and where it deliberately is not.** `src/rng.c` masks with
`WB_BUS_ADDR_MASK` before its off-image guard — batch 21b's transferable lesson — and the sibling's
`add.l d2,d0` is pinned the same way from ITS side, wrap AND width. The respawn's own table read
carries neither, and that is computed rather than assumed: the `bmi` bounds the kind to
`$0000..$7fff`, `lsl.w #4` bounds the scaled word to `$0000..$fff0` and the `lea`'s sign extension
bounds the row to `[table - $8000, table + $7ff0]`, inside the image at both ends. A case walks all
32,768 kinds and requires exactly that window.

**Nothing here stops at a boundary.** The continuation reaches only the two draws and `rng_next`;
no sound call, no hardware write, no trap. What it inherits is the generator's registered T3-DATA
false green, which now covers `$e1c8` as well — it is the same degenerate generator. **One surface
narrowed, stated rather than hidden**: the deleted `stop_pc` runs diffed whole memory at the instant
control reached `$6cdc`; end-to-end runs compare final state, so a pre-boundary stray write at one
of the ~15 bytes the continuation constant-overwrites identically on both sides would no longer be
seen. No modeled write overlaps those bytes today (the pre-boundary and continuation write sets are
address-disjoint, and `WB_ACTOR_FLAGS` is an RMW that would still diverge); closing it for real
needs a candidate-side write ledger, which is kit scope and registered as such.

**THE REVIEW GATE FOUND A LIVE MUTANT, and the empirical verify earned its keep.** Eight finder
angles, seven verifiers, three of them running code: `stage_random_kind8(image, 0)` at the kind8
call site SURVIVED all 3,139 pre-review cases — the only nonzero-high-half entry-d2 case took the
kind32 arm, and every kind8-arm case's default d2 was an effective 0. Closed by parametrizing the
forwarding test over BOTH arms, each with its own moved-vs-unmoved guard on that draw's table; the
mutant is re-run and caught. The rest of the review, all verified before applied: the 126-byte
correction above; the kind-table guard strengthened to the ordered shape; the retire arm's
instruction cap restored (`DEFEAT_RETIRE_INSN_CAP` — folding the respawn allowance into one cap had
loosened the retire arm's enforced bound by exactly 59 instructions); `retire_slot` returning its
code; the motion-flag triple's THIRD spelling collapsed into `actor_set_moving_unsupported()` (three
callers, per-site asm-order comments kept); `KIND32_INSN_CAP` imported whole instead of rebuilt from
parts; the respawn helpers' template/d2 derivations each spelled ONCE (`_defeat_template`,
`_scaled_spawn_type`) where three spellings and an uncoupled twin invited silent desync;
`_run_respawn` returning its image (three 1 MiB rebuilds gone) and dropping two never-overridden
parameters; a dead dict copy and a 1 MiB model-side `bytearray` copy removed; `BSR_W_BYTES` derived
from `BRANCH_W_BYTES`; one inline longword read routed through `_u32`. **Three candidates REFUTED
and not applied, for the record:** no encoder hoist into `leaf.py` (the house precedent hoists on
the second SPELLER of the same encoder, and these have one each); the 40-run per-offset candidate
sweep stays whole (the proposed boundary-offset trim loses the ONLY killers of the kind32
`andi.l #$1b` mask-bit mutant — offsets {5,6,7,14,22,23,28,30} — because the stage-5 row's bytes
coincide at every boundary fold pair); and the sweep-coverage guard keeps its `DRAW_PARAMS`
coupling, which is a deliberate tripwire against exactly that trim.

**Three measured trims, batch-17's bar** (each removed run named the mutant it does NOT uniquely
catch): `RESPAWN_ARM_CASES` dropped kills `$0000` (re-makes `$0001`'s discrimination) and `$ffff`
(equality is sign-blind) and GAINED `$0102`, the word-width case — a `cmp.b` port of the kill-limit
compare passed all five original cases and fails this one; the forced-kind grid fell 14 → 8 runs
(the six index-boundary kinds on one arm — the two arms share every instruction from the `tst.w`
on — plus one nonzero forced kind per arm, each seeding the other field 0); and the d2/bus quartet
runs on DRAW8 alone, the sibling's six runs and three guard builds being strict duplicates at the
mutant level in both directions (checked by a model-level kill matrix, not argued).

**Not pinned, honestly.**

* **The template's two forced-kind fields have no shipped bytes.** The template table is loaded from
  disk and only `$b372` publishes `$21e8c`, so every case seeds them; there is no "real data" arm.
* **The d2 `$6bb8` hands the continuation.** `index` and `0` are the same input at that call: the
  draw's `move.w $bd88.l,d2` destroys the low word and `$6bb8`'s score arm — the only arm that
  branches here — opens with `moveq #0,d2`. The sweep's mutant for it survives and is EQUIVALENT,
  which a case now states rather than leaving a reader to find
  (`test_the_defeat_reaches_this_routine_with_d2s_high_half_already_zeroed`).
* **What a "kind" MEANS** past the record fields it fills — which creature each of the 32 values is.

**Mutation sweep: 34 mutants across three passes, per README.md's recipe** (forced relink, unpiped
returncode, green tree immediately before each). **32 non-equivalent, all 32 caught; two
equivalent** — one discarded as literally the same code (`sign_ext16` already truncates, so
dropping a redundant cast changes nothing; replaced by a real wrap+sign mutant, caught) and the d2
above, provable and stated as a case. The review pass's own finding is in that tally: the 8-wide
arm's d2 mutant survived a battery that had a case for the 32-wide arm alone, which is why the
forwarding test is parametrized over both — and the review's two refactor mutants (`retire_slot`
returning RESPAWN, the motion helper dropping its `bclr`) were run and caught before landing.

**QUEUED, registered rather than half-done:** the `subsystems.tsv` rows this batch touches — the
respawn continuation belongs beside the actor lifecycle, `$e1c8` beside the stage tier — a
re-measure, queued as one per the house rule *(batch 22b: ATTEMPTED and BLOCKED at the baseline
gate — see the next section; the prerequisite is named there)*; the candidate-side write ledger
(kit scope, the narrowed-surface note above); and `$17c74` (the per-VBL tick) and
`stage_load_window` remain the PSG wall's two faces, unmoved by this batch.

### Batch 22b: the queued re-measure — BLOCKED at the baseline gate, and the tripwire is why

The `subsystems.tsv` re-measure batch 22 queued could not be run, and the reason is a finding
rather than an obstacle. `tools/hw_portability.py` **exits before classifying anything**: its
`check_shim_agreement()` pins `shim.c`'s `PSG_SELECT`/`PSG_DATA`, which the kit's Phase 6
(`bd86412`) deleted, moving the canonical pair to `include/os.h` as
`OS_PSG_PORT_SELECT`/`OS_PSG_PORT_DATA` (same values). The pin did exactly its job; nothing had
re-run the tool since, so §0f (batch 20) is the last measurement that predates the break.
**Verified with a throwaway copy, repo untouched**: drop the two dead pins and the classifier
reproduces every committed §0e/§0f figure byte-for-byte off the committed scan — 222/256 runnable,
21,334 / 25,786 B, 82.7 %, false-green 28 / 3,348 B, all nineteen rows. The logic and the
partition are intact; only the constants pin is broken.

**The rename is not the whole repair.** `hw_portability.py`'s tier rule says *any* PSG-block read
is a hard reject; Phase 6 made a byte read of `$ff8800` **served** from the seeded register file
and logged into the ordered event ledger — diffable, not a reject — which is precisely what batch
21b's `snd_psg_silence` does and why it is green. Renaming the constants alone would print numbers
that silently understate runnability: the T4 read rule must be re-derived against Phase 6 before
any figure is trusted. (Batch 21b had already queued this as "hw_portability re-pricing"; the
baseline gate has now turned that queue entry into a prerequisite.)

**A third floor moves.** `out/hw_scan.tsv` predates batches 21b/22, so `$6cdc` is still inside
`$6bb8`'s 290-byte Ghidra body and `$e1c8` is in no function body at all; ranges match on ENTRY,
so the two proposed rows change NOTHING against the committed scan (verified empirically, not
argued). They become entries only after `../reapply.sh` re-cuts the DB — and that re-scan moves
whole-program figures itself (256 → ~258 F records, `$6bb8` re-cut from a 290 that folds in the
`$6c5c` score table), so the one-diff-hunk property needs a TWO-STAGE pin: re-scan and re-baseline
in its own section first, then the partition edit. `$68c6` and `$e1f0` are confirmed in the
catch-all today (21 members).

**No code changed, no test moved, `subsystems.tsv` and `PORTABILITY.md` untouched**; `make test`
3133 green on a forced relink after the attempt. **QUEUED, unchanged and now with a named
prerequisite chain:** (1) repair `tools/hw_portability.py` against Phase 6 — the constants pin
AND the T4 read rule *(batch 22c: DISCHARGED — see the next section and PORTABILITY.md §0g)*;
(2) `../reapply.sh` + `tools/hw_scan.sh`, re-baselined in its own section;
(3) then the partition edit this entry always was. The rows, ready for that day, with citations:
`0x6cdc 0x6d5a` → the actor lifecycle's subsystem (126 B, reached only from `$6c34`'s `ble.w`, a
continuation not a subroutine), and `0xe1c8 0xe222` → the stage tier's, ONE range covering both
draws (they share the last fourteen bytes and one C body — splitting them at `$e1f0` would draw a
subsystem boundary through the middle of an instruction sequence both routines execute).

### Batch 22c: the classifier repaired against Phase 6 — the priced wall was a year of the tool's, not the game's

Prerequisite (1) of batch 22b's chain, discharged. [`PORTABILITY.md`](PORTABILITY.md) **§0g is the
full record**; what belongs here is the headline and what it changes about planning. **Runnable:
222 fns / 21,334 B / 82.7 % → 242 / 24,318 / 94.3 %. Direct hard-rejects: 3 → 0 — the row is gone
from every table. False-green: 28 fns / 3,348 B, unchanged function-for-function.** The re-pricing
is Phase 6 stated honestly: a byte read of `$ff8800` is a **seeded, ledgered, diffable** input (a
new `T2 PSG_SEEDED_READ` tier — it costs a case obligation, not fidelity), which is what batch
21b's `snd_psg_silence` had already proven function-by-function. `$17c74`'s price is now its OWN
steering reads (`$fffa01`/`$ff820a`, the false-green class) — exactly the batch-23 scout's
inventory, converged on independently. The cross-check pins the §6 prediction: the new default
equals the old rule's `--model psg:read` projection, 242 / 24,318 both ways.

**The tool now carries its own committed pins** — `tools/test_hw_portability.py`, 37 cases,
standalone pytest, not wired into any project's `make test`: the 16 lattice shapes (the T5
boundary: `$ff8802` reads, mirrors, wide and straddling transfers, odd-alias writes), 8 tripwire
mutations on throwaway kit copies (constants renamed/revalued, the behavioural pin's
comment-bypass, BOTH file-level deletions — a present kit with a missing pinned file now exits 1,
the hole the review found by test), and the committed-figure reproduction as a regression case.
The review gate's other finds, all landed: the behavioural pin matches a **definition shape**, not
a substring (a changelog comment mentioning `psg_read_back` no longer satisfies it); the
`PINNED_CONSTANTS[0][0]` positional coupling replaced by named path constants; each pinned file
read once; `docs/on-target-execution.md`'s tier table rewritten to the seven-tier lattice (it was
teaching the OLD numbers against the new reports — "T4-with-a-branch is the tier to hunt" is the
new phrasing); and §0g's bridge widened to say plainly that EVERYTHING above it (§0–§0f and §2–§8)
speaks the old numbering, with the mapping stated once. A sweep caveat worth its line: two
byte-length-preserving mutations first reported phantom SURVIVED off stale `__pycache__` bytecode —
purge it per run; §0g records the trap beside the README's relink trap, same family.

**No game code changed, no suite case moved** (`make test` untouched by construction; the 37 new
cases live tool-side). **Still queued:** 22b's steps (2) re-scan + re-baseline and (3) the
partition edit — now unblocked, sequenced after batch 23 lands so the re-scan captures its names
too.
