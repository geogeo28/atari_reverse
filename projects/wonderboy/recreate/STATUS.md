# Reconstruction status — Wonder Boy in Monsterland

Human-readable C reconstruction of `SWB.PRG` (the original, uncracked 1989 Activision release,
extracted from the Pasti `.stx` of disk 1), each function to be **verified byte-for-byte against the
original 68000 code** by the shared differential harness (`tools/recreate_kit`: a Musashi oracle
running the real code vs. the compiled reconstruction, on the same memory image). See
[`README.md`](README.md) for how this project binds to the kit, and
[`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) for how the differential
method itself works.

**Verified: 290/? — the .RAD depacker (216 bytes), the first gameplay batch (434 bytes), the status
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
$6cdc boundary is GONE — the defeat path runs end to end to the original's own `rts`) — and the
sound module's TICK TIER under `$17c74` (`snd_sfx_tick` + `snd_prng_step` +
`snd_channel_period_and_volume`, 958 bytes, batch 23: everything the per-VBL tick calls, pinned
whole with no boundary) — and the TICK ITSELF (`snd_channel_step` + its 24 opcode handlers +
`snd_music_tick_body`, 1,208 bytes, batch 24: the sound module is now WHOLE except its 44-byte
tempo head) — and now that HEAD (`snd_music_tick`'s tempo selector, 44 bytes, batch 25: the sound
module's last unported bytes, and the first code in this workspace verified across a DECLARED
machine rather than a fabricated one) — and the STAGE-TRANSITION HINGE (`stage_load_window` +
`set_palette` + `snd_play_song`, 374 bytes, batch 26: $f95c runs WHOLE — every stage entry in the
game now passes through reconstructed code end to end, and the dropped-write tier is named) — and
the SCENE TIER'S CLOSE (`scene_exit_and_reload` + the exit-action table's two remaining entries,
172 bytes, batch 27: the four exit tails run from the spending arm through the dispatch and the
whole reload to the original's `rts`, and the dispatch is on the WRAPPED offset — 32 index values
reach the eight entries) — and the $5a BAND CLOSED (`actor_behavior_type47/48/49`, 236 bytes,
batch 32: the seven dispatch rows of $5928..$5c6b now all run, and three of them are three different
endings of one grammar — the cursor, the countdown and a second table's cursor) — and SLOT 7 WITH
ITS SWOOP MACHINE (`actor_behavior_type07` + the four states at $72c2..$73cd, 692 bytes, batch 32
phase 2: the tier's LAST always-transfer boundary retired — three table rows share one body, both
prologues run straight into it, and the two mark bits of 30(a0) are answered) — and the THREE
COLLECTABLES with the payout cluster they spend through (`actor_behavior_type28/30/31` plus
`hud_award_gold_from_descriptor`, `bcd_add_random_1_to_4` and `text_write_gold_digits_a2ac`, 506
bytes, batch 33 phase A: the first code here that reads the game's SECOND hardware entropy source,
and the batch that established what the gold counter is; phase B then CLOSED the batch by carrying
the packed-BCD extend bit through the two chains and the one shift that produce one, verifying no
new function but making THREE already-counted ones faithful — including `actor_defeat_and_score`,
where the independent gate found a live divergence a refusal in the battery had been hiding) — and
the $4e38..$5407 BAND CLOSED (`actor_behavior_type32`..`type37`, 694 bytes, batch 34: every dispatch
row from slot 28 to slot 37 now runs, the last two collectables are a hop machine and the game's
CLOCK, and the other four are not creatures at all — the shop's item cursor and the three event
actors `player_pending_event_gate` spawns and waits on) — and the MONSTER-PROLOGUE FAMILY OPENS
(`actor_behavior_type09`..`type13` plus the leaf `actor_random_facing_hop`, 1,310 bytes, batch 35:
the $2462 band's grammar with five more middles — a random hopper, a flier that never touches the
map, a decider that spends one `rng_next` word on a facing AND a hop, a chaser, and a bouncer whose
hurt arm is a throe that ALWAYS ends in the defeat — and the first two handlers in the tier BOUNDED
on an arm the game runs every time a monster is hit) — and that family's SECOND BLOCK
(`actor_behavior_type14`..`type19`, 1,940 bytes, batch 36: six more middles and none of them
bounded — a patroller that drops escorts, a walker that turns AND hops off a blocked step, a hopper
that lobs, a drifter whose two cursors are GLOBALS and which seeds five records at a time, a charger
that saves its whole flag byte across the charge, and a two-phase glider whose firing frame
publishes a word of the record it just allocated) — and THE MONSTER FAMILY CLOSES
(`actor_behavior_type20`..`type27` plus the leaf `actor_aim_velocity`, 2,698 bytes, batch 37: the
family's last eight middles, of which FIVE are code this port already had at another address —
slot 27 is slot 20's 378 bytes byte for byte, slot 23 is slot 4's body with a gold-theft contact
arm that BRANCHES INTO IT, slot 25 is slot 18's charge, slot 26 is slot 12's chase and slots 22 and
26 share slot 9's gated hurt arm — and the three that are new are a hopper whose turn test reads a
WORD, a sentry that AIMS its shot out of a sixteen-direction table, and a launcher whose `bclr` is
its own test) — and THE PICKUP TIER (`actor_behavior_type38_pickup`, the digit routine
`text_post_bonus_points_a4be` and the FOURTEEN handlers of `pickup_effect_table`, 756 bytes,
batch 38: the first dispatch row whose frame reaches a SECOND dispatch — a collectable that reads
its own 16-byte kind row for a packed-BCD score and an index into a table whose fourteen entries
name what the pickup actually IS, twelve of them by the message they post) — and THE TIER'S OWN
AMMUNITION (`actor_behavior_type39`..`type46` and `type57`, 1,142 bytes, batch 39: the LAST NINE
NON-PLAYER ROWS, and each of them is the record an already-reconstructed handler spawns — two
shatterers that break up when they land and share one tail, three walkers that die where the map
stops them, three shots and the riser that is slot 23's stolen gold floating away. **SIXTY-ONE of
the dispatch table's 62 rows are now live and the one that is not is the player**) — and THE
PLAYER'S FRAME OPENS (`player_meter_empty_check`, `player_jump_step`, `player_apply_joystick`,
`player_reset_ground_state` and `scene_copy_record_fields`, 538 bytes, batch 40: the five routines
behaviour slot 1 calls that reach nothing this port lacks, in a src/player.c of their own — the death
check and its revival medicine, the jump machine and its wing boots, and the ladder — and with them
the LAST BOUNDARY THE ORIGINAL RETURNED FROM: `$e06` is reconstructed, so `player_gate_on_1516` calls
it and the five handlers that stopped there (53, and 9/12/22/26 through `gated_hurt_frame`) run their
frames whole) — and THE WALK AND THE WEAPON (`player_step_and_arm` and `player_weapon_fire`, 736
bytes, batch 40 phase B: the frame's fourth and fifth calls, and the last two that reach nothing this
port lacks — a five-section walk whose accelerator turns at two different rates, and the SPECIAL
ATTACK, whose `sbcd` is the first THREADED extend site in this project that one of its own arms also
produces LOCALLY. With them `player_reset_ground_state` and `scene_copy_record_fields` finally have
callers, which retires both of phase A's honesty items, and SIX of the frame's nine calls run) —
36,326 bytes in all, 82.1 % of everything
[`PORTABILITY.md`](PORTABILITY.md) measures *(the denominator is §0k's 44,262 — batch 28's
coverage break-open finally put the per-monster tier INSIDE the measured program, so this figure
dropped from batch 27's 80.3 % not because anything was lost but because the denominator now
contains the game; 80.7 % of believed CODE is measured, and only 226 bytes remain genuinely
unknown. Batch 29 — the behaviour tier's foundation — was the first port batch priced against
the honest denominator, and crossed it back over 50 %)*.** *(The batch-16 commit's header said 147 — an
oversight; its own section records 151, and batch 17 corrected the header to 153. Batch 22's edit
left this leading count at 161 while its own section and parenthetical said 163 — the same
oversight, found by batch 23's port agent. And batch 27's header said 175 while its own table
expands to 176 — found by the 2026-08-11 re-scan's reconciliation, corrected here. The class
recurs; expand the table before trusting the headline.)*
`make test`: **5438 cases green in what this batch commits**, measured by a full run from a clean
`build/` rather than added up (5353 after batch 40 phase A, plus phase B's 85 — every one of them in
`test/test_player.py`, which goes 83 -> 168. Two of the 85 are the mutation sweep's — the row that
makes a ZERO-PIXEL map probe observable and the seeding repair behind it — and two more the
INDEPENDENT gate's, which parametrised the entry-X carrier row over all three arms that inherit the
bit).
`make test` at batch 40 phase A: **5353 cases** (5262 after batch 39, plus phase A's 91 — 83 in the new
`test/test_player.py` and 8 net in `test/test_behavior.py`, which goes 1,568 -> 1,576: five cases
were REWRITTEN rather than added, which is what retiring a boundary looks like in a battery, and the
two independent gates then added the rest — the four ascent-position rows, the wing-boot-through-a-
handler row, slot 53's position row and the two arm-exclusivity rows).
`make test` at batch 39: **5262 cases** (5140 after batch 38, plus batch 39's 122 — 120 in
`test/test_behavior.py`, which stands at 1,568, and the other two `test/test_actor.py`'s entry pin
for `actor_aim_velocity` and the body-size row beside it. Seven of the 120 are the mutation sweep's
— two facings on the shatterers' turn, two walker body arms, two settle-order rows and the aim
table's X-flag geometry — and six the independent gate's: the three THREADED producer/consumer
runs, the header scrape that replaced a false completeness claim with two honest ones, the
mode-shaped sweep's superset check, and the hoist queue's own length).
`make test` at batch 38: **5140 cases** (4992 after batch 37, plus batch 38's 148 — split across
the two batteries that batch touched, `test/test_effects.py` 160 -> 238 and `test/test_behavior.py`
1,378 -> 1,448).
`make test` at batch 37: **4992 cases** (4812 after batch 36, plus batch 37's 180 — all of them in
`test/test_behavior.py`, which stood at 1,378).
`make test` at batch 36: **4812 cases** (4670 after batch 35, plus batch 36's 142 — all of them in
`test/test_behavior.py`, which stood at 1,198: 135 written with the batch, six more the mutation
sweep demanded and one the review gate did).
`make test` at batch 35: **4670 cases** (4558 after batch 34, plus batch 35's 112 — all of them in
`test/test_behavior.py`, which stood at 1,056: three from the mutation sweep, eight from the review
gate and seven from the INDEPENDENT gate, less two the last of those replaced).
`make test` at batch 34: **4558 cases** (4466 after batch 33, plus batch 34's 92 — all of them in
`test/test_behavior.py`, which stood at 944).
`make test` at batch 33: **4466 cases** (4359 after batch 33's prerequisites, plus phase A's 92 and
phase B's 15). The
92 is NET: the review gate and the independent gate after it added rows for the left walk arm, the
signed drift cursor, the sub-mark countdown at both sites, the collect point, the meter's SIGNEDNESS
and the live-row count, and trimmed three that could not fail (see the two gate paragraphs below).
Phase B's 15 are the extend chain's, and split three ways: SIX in `test/test_behavior.py` (which
stands at 852) — two more rows on slot 28's payout, one more award row, three premise guards; SEVEN
in `test/test_hud.py` (555) — the six model-only `sbcd` rows and their guard; and TWO NET in
`test/test_actor.py` (990) — the gate's two bit-14 rows and their guard, less the refusal-era guard
whose premise the fix made false.
`make test` at batch 33's prerequisites: **4359 cases** (4344 after batch 32, plus batch 33's first
5 — all in `test/test_behavior.py`, which stood at 754 — plus 6 in `test/test_rng.py` from the kit
extension below, which stands at 109, plus 4 in `test/test_actor.py`, the declared counter's two
consumer cases and their parametrisation, which stands at 988).
`make test` at batch 32: **4344 cases** (4200 before it, plus 144 — 47 in phase 1, 86 in phase 2
and 11 from the review gate).
`make test` at batch 31: **4200 cases** (4130 before batch 31, plus its 70,
all in `test/test_behavior.py`, which stood at 605).
`make test` at batch 30: **4130 cases** (4019 before batch 30; the growth is
the tier's battery `test/test_behavior.py`, including the review round's 16 death/struck-arm cases
and the rebuilt a32 pin).
`make test` at batch 29: **4019 cases** (3594 before batch 29, plus its 425,
all in the new `test/test_behavior.py` — the tier's own battery).
`make test` at batch 27: **3594 cases** (3546 before batch 27, plus its 48,
all in `test/test_scene.py`, which stands at 231; `test/test_stage.py` holds at 112 across a
refactor).
`make test` at batch 26: **3546 cases** (3483 before batch 26, plus its 63:
+31 in `test/test_sound.py`, which stands at 557, and +32 in `test/test_stage.py`, which stood at
112 — two measured trims inside those figures, recorded in the batch-26 section at the end).
`make test` at batch 25: **3483 cases** (3466 before batch 25, plus its 17,
all in `test/test_sound.py`, which stood at 526).
`make test` at batch 24: **3466 cases** (3333 before batch 24, plus its 133
net, all in `test/test_sound.py`, which stood at 509 — five measured trims inside that figure,
recorded in the batch-24 section at the end).
`make test` at batch 23: **3333 cases** (3133 before batch 23, plus its 200
net, all in `test/test_sound.py`, which stood at 376 — three measured trims inside that figure,
recorded in the batch-23 section at the end).
`make test` at batch 22: **3133 cases** (3052 before batch 22, plus its 81
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
*(batch 26: RECONSTRUCTED WHOLE — it runs end to end with no boundary; see its section at the end)*
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
  *(This figure held from the original measurement through §0g/§0h and moved for the FIRST time in
  PORTABILITY.md §0i, 2026-08-07: kit Phase 7 made `$fffa01`/`$ff820a` seeded case inputs, so the
  count is now **20 functions / 2,224 bytes** — the leavers are the tempo tier and the two
  `$fffa01`-polling FDC waits, each named in §0i. The paragraph below stays as the record of WHY
  those addresses were the class's worked examples.)*
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
| `0x1a48a` | `snd_trigger_effect` | 334 | verified | 123 cases: all 26 shipped ids on channel A, 12 call-site ids x channels B/C, 6 out-of-range ids (both sides of the sign extension) x 3 channels, 3 ids whose descriptor sits INSIDE the mix block (order), 2 whose descriptor sits inside the STATE band (the copy DIRECTION — a memmove reddens exactly these, over a keyed-seeded band, with the model SIMULATING the byte-by-byte copy), 5 seeded descriptors x 3 channels through a poked pointer-table entry, a d1 sweep over the third arm bracketing the last channel's own number, d0/d1 high-byte pins, table self-bounding + noise-arm coverage guards + entry pin over all three arms and the `rts` past them *(batch 23: NOT an orphan — it is `snd_sfx_tick`'s shared `rts`, reached by that routine's own backward branches; see its row)* |
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
| `0x1aaca` | `snd_prng_step` (`src/sound.c`) | 28 | verified | Batch 23: the module's OWN PRNG, distinct from the game's ($68c6) — a 32-bit shift through the X flag (`lsl.b #2` sets X, two `roxl.w` on memory chain it), pinned across the carry in both directions; a3 is INHERITED, not derived (the differential found it — the first case ran against a base of zero and wrote $375b), so every case seeds it; the four state bytes abut the routine's own last instruction, a self-bounding check |
| `0x1a5da` | `snd_sfx_tick` | 600 | verified | Batch 23: the SFX engine the tick calls FIRST (at $17cb6, before any music — the old plate order was backwards), three 186-byte arms as ONE parametrized C body entered at each arm's own address; its shared `rts` at $1a5d8 is the "orphan" cmt 0x1a48a disproved; each arm reads a DIFFERENT PRNG byte ($1aae6/7/8 — a sixth base-plus-stride block, stride 1, previously unrecorded); the pitch delta moves the period by delta×257 (`add.b` + `addx.b`); the volume-stream $80 loop, negative hold, AND the reload's unconditional store of a negative first byte (the review's mutant-confirmed hole, closed); ids 12/20/21 drive the PRNG path with $1aae6 seeded — the state is never reset by song start |
| `0x18208` | `snd_channel_period_and_volume` | 330 | verified | Batch 23: six arms over one music channel's 48-byte record — envelope, transpose+detune, arpeggio, table lookup, portamento, vibrato — returning d0 = period, d1.b = volume (d1's second byte carries portamento scratch); writes two module globals; note-table read proved in-image for all 256 notes (`add.b d0,d0` bounds the byte index — notes ≥96 ALIAS onto snd_arpeggio_ptr_table, ≥128 wrap to its start, both cases); the trim to one record + two named mask-pinning cases rests on the measured mutant (mask hardcoded to $09 passes record 0, fails 1 and 2); GLOBAL_DEFAULTS pins all four globals it reads, with a guard that fails if the C grows a fifth |
| `0x18106` | `snd_channel_step` (`src/sound.c`) | 258 | verified | Batch 24: one channel's pattern step — countdown, pitch slide, the read loop and the range decoder (`addi.b`+`bcs` chain whose command range ends at $b8, NOT the $97 the notes said) — ending in the `jmp (a3,a2.w)` handler dispatch; the two handler return addresses ($18116/$18148) are DERIVED from the stepper's own runs so stepper and handlers cannot disagree; a3 inherited; the $18036 read-BEFORE-store on the sequence entry is the batch's found-and-fixed ordering divergence, pinned by a case that solves the aliasing offset so the table names the record's own index word |
| `0x17fd4` | the 23 pattern-opcode handlers *(the title said 24 until the 2026-08-11 re-scan — $80..$97 is 24 OPCODES but $8d shares a body, and the scan finds 23 F records, agreeing with this row's own prose)* | 306 | verified | Batch 24: 23 distinct bodies below the stepper, each entered by its `jmp` and all but $8e branching back INTO the stepper's body; the opcode census is DERIVED by a walk the battery runs (658/95/88/51/48/16/11/5/4/3/2 over all 106 patterns of all 17 songs, self-proving 95+11=106, $93 retargets closure-guarded) — eleven of twenty-four reached by shipped data, each grid row saying which; $97's latent bug (sets d0, never d1) REPRODUCED not fixed; $98..$b7 (a dispatch through the handlers' own instruction stream) has no C and REFUSES by construction via os_refused, proven unreachable from shipped data |
| `0x17c74` | `snd_music_tick` (`src/sound.c`) | 44 | verified | Batch 25: the TEMPO SELECTOR, the sound module's last unported bytes and the kit's Phase 7 seeded-hardware-read model's first consumer anywhere — `btst #7,$fffa01` (mono detect, ACTIVE LOW, so SET = colour) and `btst #1,$ff820a` (SET = 50 Hz) choose the drop byte at $17c6e, 0/$2b/$48, and the run falls into `snd_music_tick_body`; three machines declared with `hw_seed=` as the tested BIT and its complement, plus the capture profile's own $b0/$02; the mono arm's `bra.s` over the sync test means a mono machine never reads $ff820a, an ordering only the ordered read stream can witness; a case declaring no machine is REFUSED (AssertionError from `differential`, not `emu.run` — the one place Phase 7 differs from Phase 6); this is also the routine that ESTABLISHES a3, so no case here seeds it; head + body now tile $17c74..$17f23 |
| `0xf944` | `set_palette` (`src/stage.c`) | 24 | verified | Batch 26: sixteen words from `palette_table + (row << 5)` to the shifter — and THE DROPPED-WRITE TIER NAMED: the output is off-image, the oracle and the reconstruction both drop it, and no ledger exists, so the case pins the EMPTY write set on both sides, the returned cursor (source + 32) and the oracle's own a1 landing at $ff8260, and says on every surface that the hardware effect is UNTESTED. The sweep proves the hole is real: three survivors (row shift, colour count, unscaled row) are one hole seen three ways, while the un-advanced-cursor mutant IS caught. The kit-scope remedy (a dropped-hardware-write ledger) is registered below |
| `0x17b3a` | `snd_play_song` | 140 | verified | Batch 26: stub +0 — stops the module FIRST through the +28 stub (the `movem` pair is what carries the song id in d0 across a routine that silences the chip, so a start's PSG traffic is exactly a stop's), reads the 8-byte directory record, arms three channels in one real `dbf` loop, and writes six globals — including the `st` at $17bb8 the old plate omitted: the row accumulator starts SATURATED, so a song's first row steps at once. This is the routine that WRITES the mutable bands batches 23–25 seeded by hand. Cases are the game's own data: all 17 shipped songs, both tail arms, the $fa2e dedup latch both ways |
| `0xf95c` | `stage_load_window` | 210 | verified | Batch 26: THE HINGE RUNS WHOLE — entered at $f95c, out at its own `rts`, no stop_pc: the raw-tiles flag (`cmpa.l #$1d43e,a6`), the three latches, the followed defaults, the three batch-12 builders, `set_palette` via `9(a0)<<5`, the follow subtraction unless frozen, and the sound tail selected by `8(a0)`'s sign through the $fa2e dedup. Composition asserted through the callees' OWN models (batch-19 style, one `_model_publish` after the review pass): 180 KB of buffers, the published scroll state, the tune latch and the module's write set compared as one. The plate's operands were corrected ($fe1a re-read three times — 4(a0)/9(a0)/8(a0), not a1; $f9d6's dead read; the six real caller sites). The .PRG ships FIVE start records at $1d40c, so both tail arms and two palette rows run on shipped data |
| `0x101bc` | `scene_exit_action_none` (`src/scene.c`) | 2 | verified | Batch 27: entry 0 of scene_exit_action_table, a bare `rts` — and what BOUNDS the table: its own first four bytes ($4e7533fc, odd and past the image) are the longword an out-of-table dispatch would jsr through, which is why the C refuses on the WRAPPED offset and no C stands in for the escape |
| `0x101be` | `scene_exit_action_select_a30_table` | 66 | verified | Batch 27: entry 1 — publish actor_table_default, allocate out of THAT table, republish as actor_table_a30, and count into scene_exit_alloc_count ONLY when a slot was found; the record is DISCARDED (a1 never written through), so the counter — one operand site, NO reader — is the allocation's whole lasting effect. The ordering (publish→alloc→republish leaves one longword either way) is pinned by a three-table probe reading it off whether the counter moved; the body self-bounds at $10200 against the first effect stub |
| `0xdfbe` | `scene_exit_and_reload` | 104 | verified | Batch 27: the exit tail — dispatch through the 8-entry table (ALL ported code: entry 0 the rts, entry 1 above, entries 2..7 batch-1's effect stubs) ON THE WRAPPED OFFSET (`lsl.w #2` wraps in 16 bits, so 32 index values reach the eight entries — the review gate's own find: a raw-index guard refused 24 aliased indices the original dispatches, caught by three per-band alias differentials), clr.b text_box_active right after the dispatch, three pointer loads (a0 := $22090 = bg_map_row_stride — the level map ITSELF, so this caller's header width IS the global stride), clr.w scroll_follow_frozen as the LAST instruction before jsr stage_load_window (this path always hands the hinge an unfrozen scroll), five state clears; the start-table index is REPRODUCED not refused (a data read — driven to $ffff, four bytes below the table); the four exit tails are FULL RUNS with the transfer witnesses kept and the arm/tail disjointness now a CHECKED property |
| `0x17ca0` | `snd_music_tick_body` | 644 | verified | Batch 24: the tick below its 44-byte tempo head — engine/SFX gate, the drop accumulator over a POKED $17c6e (all three drop values 0/$2b/$48 differentiable without the head), the fade with its NON-LOCAL exit into the ported stop chain, 3× row step, 3× period/volume, the 54/52/52 mixdown arms (A alone carries the abandon `bmi`, B/C alone the `rol.b`), and the PSG output block over psg_seed — ordered ledger + register file compared, the reg-7 RMW's preserved direction bits pinned, outgoing d1 = $2700 stated as the oracle's SR fact; multi-tick sequences are N runs from one declared chip state, NOT a continuous chip timeline (the harness reseeds per run — stated in the driver) |

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
* **The disassembler printed `abcd`/`sbcd` wrong — FIXED at batch 33, and the LISTING is still
  stale.** `c308` and `8308` came out as `and.b d1,a0` and `or.b d1,a0`, which made the four
  accumulators read as nonsense; Ghidra always had them right (`bcdAdjust` and `in_XF` in
  `../decomp.c`), and so did the entry-byte pin, which is built from the opcodes. `tools/prg_dis.py`
  now decodes the whole two-register family — `abcd`/`sbcd`, `addx`/`subx` and `cmpm` — and
  `tools/recreate_kit/test/test_prg_dis.py` pins the forms AND their operand order by reference
  encoding. **But `../out/wonderboy_dis.txt` is a generated file and predates the fix**, so every
  `$8xxx`/`$cxxx` line in the checked-out listing is still the old wrong one: regenerate before
  reading a plate out of that band (queued in the batch-33 section). `../names.txt` records the trap
  on `$b562`.
* **The BCD routines' entry X flag is live input — CARRIED since batch 33 phase B, and what is left
  unpinned is now narrow and named.** `abcd` folds in the extend bit and nothing between the entry
  and the first one touches it. The four accumulators take that bit as an argument and return the
  one they leave, so: the two ported CHAINS drive a run-produced X = 1 end to end
  (`$4e5a`→`$4e64`, `$5184`→`$5188`); `$6c26` threads the bit `lsl.w #2,d2` leaves and both answers
  are ordinary differential rows; and the `sbcd` half is pinned against the decimal model in both
  directions, borrow in and borrow out. TWO things remain, both stated at their sites: a run
  ENTERED with X set, which `emu.run` cannot express — the game does it at `$e064`, where `$e058`'s
  `subq.w #1,hud_meter_value` sets X on a meter already at zero so it scores one extra unit, and
  that call site is not ported — and the SHOP's subtract, whose entry X is its caller's and whose
  caller sets it on the frame `frame_tick_b39a` wraps (the open row in the phase-B section). Still
  the first reconstruction in this workspace whose entry condition is a CONDITION CODE rather than a
  register. See "Batch 33 phase B" for the whole of it.
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
independent reasons, below. *(All three fell in order: stage_load_window in batch 26, $101be read
in 26 and ported in 27 — $dfbe is RECONSTRUCTED in batch 27 and the four exit tails run whole.)*

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
tails); and the batch-19 boundary convention is exactly what porting does about that gap. *(Batch
27: the row's shape inverted — 3 of 3 reconstructed and the tails run WHOLE; the row's re-measure
rides with the next partition pass.)* The
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
* **The extend bit `$6bb8` hands the score accumulator.** **SUPERSEDED by batch 33 phase B — the
  port threads the bit and both answers are driven; the refusal is gone and the "every shipped type
  has bit 14 clear" reading was uncheckable (the template table has no shipped bytes). Also note
  this entry conflated `$6bb8` with `$e064`: only the latter is a run ENTERED with X set, which is
  the limitation that survives.** As written at batch 22: `lsl.w #2,d2` leaves X holding the spawn
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
`stage_load_window` remain the PSG wall's two faces, unmoved by this batch. *(Both fell:
`$17c74` in batch 25 behind kit Phase 7, `stage_load_window` in batch 26. The wall is down.)*

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
(3) then the partition edit this entry always was *(steps 2–3: RUN after batch 23 — see "Batch
22b (steps 2–3)" at the end and PORTABILITY.md §0h; the score-table prediction below was WRONG,
and the correction is that section's finding)*. The rows, ready for that day, with citations:
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

### Batch 23: the sound module's TICK TIER — the SFX engine, the module PRNG and the period/volume pass

Three functions, 958 bytes, and every one of them is what `snd_music_tick` calls rather than the
tick itself: the SFX engine it runs **first**, the PRNG that engine steps, and the pass that turns a
music channel's record into a period and a volume. **Verified 166, 19,226 bytes, 74.6 %;
`make test` 3333** (3133 before the batch, plus its 200 net, all in `test/test_sound.py`, which
stands at 376 — three measured trims inside that figure, below. `test_actor.py`, `test_hud.py` and
`test_stage.py` are converted to two encoders hoisted into `leaf.py` and their counts do not move:
984, 548 and 80.)

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$1aaca` | `snd_prng_step` | 28 | the module's OWN PRNG — a 32-bit shift through the X flag |
| `$1a5da` | `snd_sfx_tick` | 600 | the SFX engine, one 186-byte arm per channel (+ its shared `rts`) |
| `$18208` | `snd_channel_period_and_volume` | 330 | six arms over one music channel's 48-byte record |

**Three plate corrections and two structural findings, all read off the bytes.**

* **`$1a5d8` IS NOT AN ORPHAN.** `cmt 0x1a48a` called the `rts` past the trigger's body "an orphan
  no arm reaches". It is **`snd_sfx_tick`'s shared `rts`** — the target of that routine's `bmi.s` at
  `$1a5e6` and its `bra.s` at `$1a600`, exactly as `$17c72` serves `snd_music_tick` — and a
  whole-image branch/jump scan finds nothing else referencing it. So the tick is 600 bytes
  (`$1a5d8..$1a82f`), the entry pin's two backward branches assert it from inside, and
  `test_the_tick_tiles_the_module_between_the_trigger_and_the_pointer_table` asserts it from both
  sides.
* **The tick calls the SFX engine FIRST.** `$17cb6` is `bsr.w $1a5da`, before the fade countdown,
  before `snd_channel_step` and before `$18208`. `cmt 0x17c74` had it the other way round and now
  carries the verified order, the callee list and the **non-local exit**: `$18016` clears "song
  loaded" and `bra.w`s to stub +28, so the stop's `rts` returns to the *tick's* caller and the rest
  of the tick never runs — and opcode `$8e` enters two bytes earlier at `$18014`, whose
  `addq.l #4,sp` unwinds `snd_channel_step`'s frame first. Units 4 and 5 will need both.
* **`$1aaca` and `$18208` have no `lea $1738c(pc),a3` of their own.** Every routine reached through
  the stub table opens with one; these two are internal `bsr` targets and inherit a3 from their
  caller. **The differential found it** — the first PRNG case ran the two `roxl.w`s against a base
  of zero and wrote `$375b` — and every case now seeds a3.
* **Each SFX channel reads a DIFFERENT byte of the PRNG state**: A takes `$1aae6`, B `$1aae7`, C
  `$1aae8`. That is the sixth base-plus-stride block of the three arms and the only one whose stride
  is 1 rather than the size of a block; nothing had recorded it.
* **The pitch delta moves the period by `delta * 257`.** `add.b d0,lo` then `addx.b d0,hi` puts the
  same byte into both halves, carry included. With descriptor `+7` clear the delta is 0 and the tone
  period is copied verbatim; ids 12, 20 and 21 are the three that set it.

**All 958 bytes are pinned WHOLE.** The three entry pins assemble every instruction of every body
from `include/wonderboy.h`'s constants and `../names.txt`'s addresses — 28 + 600 + 330 — and each
arm of the tick is built from `channel` alone, so an arm wired to a neighbour's offset fails on the
bytes at its own address. The differential still enters each arm at ITS address, through the entry's
own three `bsr`s. Three self-bounding checks fall out: the PRNG's four mutable bytes sit immediately
past its last instruction, the tick's last arm ends exactly on `snd_sfx_ptr_table`, and `$18208`
ends exactly on `snd_psg_shadow`.

**Nothing here trusts an image byte.** All four mutable bands the tier reads ship **dirty** — the
`.PRG` was saved after a run at a load base of about `$2d360` — so every case seeds them with
`leaf.keyed_block` or fills them through `expected_writes`, the trigger's own model. Two cases now
guard that claim per band, and they exist because **the review pass found it false**: the poke dicts
merged key by key, so the trigger's fourteen-byte state write replaced the seventy-eight-byte state
seed and its two-byte mix write replaced the eleven-byte mix seed. Most of both bands ran on residue
and every case stayed green, because both cores read the same residue. `_overlay` merges byte by
byte and `_assert_bands_are_seeded` is what says so.

**Where the bus mask is.** `module_byte` masks with `WB_BUS_ADDR_MASK` before its off-image guard —
batch 21b's lesson — and it is the only place these routines need it: three cursors come out of the
dirty image (the envelope's, the arpeggio's and the volume stream's) and nothing bounds them. The
period-table read carries neither, and that is computed rather than assumed: `add.b d0,d0` bounds
the index to `$00..$fe` and the base is a constant, so the read is inside the image for every one of
the 256 notes — which is also why a note from 96 up ALIASES onto `snd_arpeggio_ptr_table` instead of
faulting, and a note from 128 up wraps to the table's start. Both are cases.

**Not pinned, honestly.**

* **The tick body itself (`$17c74`), `snd_channel_step` (`$18106`) and the 24 opcode handlers** —
  units 4 and 5, and the reason the tier stops where it does. Nothing here strays into them: the
  three routines call only each other, verified by a whole-image scan for every branch and jump
  target, so this batch needs no `stop_pc` and has no boundary. *(Batch 24: BOTH UNITS PORTED —
  see its section below; only the 44-byte tempo head `$17c74..$17c9f` remains, behind Phase 7.)*
* **The PSG wall is unmoved.** `$17c74`'s two hardware reads (`$fffa01` bit 7, `$ff820a` bit 1) and
  its whole output block are still what a memory differential cannot see. A green suite here says
  the right bytes landed in the right module fields and says nothing about what is heard.
* **The music channel records have no shipped initial state.** The band is residue, so every case
  seeds it; the one exception is `+47`, the constant mixer mask, which nothing in the module ever
  writes — a case requires the three shipped bytes to be `$09`/`$12`/`$24` in order.
* **A negative SFX-active flag** is reachable only from a seeded state (the trigger `sf`s the byte
  to 0 and stores 1), and so is a **slide direction of zero** — all 26 shipped descriptors carry
  `$01` or `$ff` at `+8`, which a case asserts so the seeded arm cannot quietly become redundant.
* **What a descriptor field MEANS** past the role the tick gives it.

**Mutation sweep: 44 mutants across three passes, per README.md's recipe** (forced relink, unpiped
returncode, `__pycache__` purged before each run, green tree immediately before each). **43
non-equivalent, all 43 caught; one equivalent.** The first pass caught 36 of 40 and its four
survivors are the batch's most useful finding:

* the `$1a62c` early exit — a countdown spent with neither a sustain flag nor a slide step left —
  was reached by no case built from a freshly armed descriptor, so a port that fell through into the
  countdown survived the whole battery. Closed by `PITCH_GATE_CASES`, five seeded states over three
  channels;
* an envelope countdown of exactly **one**, the tick before the borrow, which is the only value that
  tells `subq.b #1 / bcc` from a `<= 1` test apart;
* a portamento landing **exactly** on its limit, which `bcs` clamps and a `>` does not;
* and the **equivalent** one: `bclr #7` on the arpeggio byte clears a bit the routine then throws
  away, because the stripped byte's only use is `add.b d1,d0` and d0 is doubled as a BYTE — so bit 7
  becomes bit 8 of the index and is masked off. Proved for all 256 notes as a case rather than left
  for a reader. The `bclr` earns its place through the Z it sets, not through the value.

Three more were added by the independent review round and each was RUN before its case was written.
**The volume stream's loop reload does not re-test the sign of the byte it takes** — a port that
re-applied the `bpl` after the reload survived the whole battery, because no seeded or shipped
stream begins with a negative byte (all ten shipped ones open in `$00..$7f`, which a guard now
states). **The mixer mask hardcoded to channel A's `$09`** is the mutant the period/volume grid's
trim rests on, and it was measured rather than argued: it passes every one of the 45 rows on record
0 and fails on records 1 and 2. And **`bus_read_byte` without its 24-bit mask**, which the promoted
helper now carries for both of its callers.

**Three measured trims, batch-17's bar** (each removed run named the mutant it does NOT uniquely
catch, checked at the mutant level before cutting). The 45-row period/volume grid fell from three
records to ONE plus two named mask-pinning cases on the other two — 86 runs — because `$18208` is
channel-agnostic: a0 is its argument and the body has no per-channel code, unlike the tick's three
arms, which are three copies. The PRNG-pitch grid dropped its effect-id axis (12 runs): the reload
reads descriptor `+7` as a FLAG and nothing in it distinguishes one non-zero value from another, and
the `{12, 20, 21}` set is pinned by its own completeness guard. And `PITCH_GATE_CASES` lost the
`(0, 1, 1)` row, whose own label conceded it was the same arm by the first test alone.

**The review gate found three defects the suite could not.** The seeding collision above; a global
transpose left to the keyed seed, so 39 of the 40 period/volume cases ran at a salt-derived
transpose and the two boundary cases *inverted* on one channel (the "last note the table holds" case
was reading past the table and the "first note past it" case inside it) — `GLOBAL_DEFAULTS` pins it
and `_effective_note` makes both coverage guards compute the note the routine actually looks up; and
a `_branch_s_to` that accepted a displacement of 0, which is not a short branch at all but the
opcode's `.w` form. Also applied: `_overlay`, `_Memory.decrement` (five spellings of one
read-modify-write), every placeholder instruction in the pins replaced by the run it stood for, a
`X ^ TOGGLE ^ TOGGLE` case row that was a duplicate replaced by the fourth state of the flag pair
the noise arm reads, `WB_SND_MUSIC_CHANNELS` dropped for the `WB_SND_CHANNELS` it duplicated,
`_shift_imm`'s word form dropped for `leaf.lsl_w_imm_dn`, and `$18208`'s a0 parameter renamed
`record` — it is an ADDRESS where the SFX half's `channel` is an index 0..2.

**Four hoists landed, complete rather than additive.** `overlay`, `seeded_bytes` and
`assert_bands_are_seeded` are now `leaf.py`'s — the layered-seed hazard has fired *twice*
(`test_scene.py`'s `_poke` docstring records the identical failure, and this battery had it twice
before its review), so the third battery to build one does not have to find it a third time. The
guarded 24-bit-bus byte read is `include/bus.h`'s, with `src/rng.c` and `src/sound.c` as its two
callers — a project header and not the kit's `machine.h`, because it pairs a 68000 fact with an
os.h one that only a game's own reconstruction has an opinion about. `tst_b_d16` went to `leaf.py`
on its third speller and **all three** were converted (`test_actor.py`'s local copy deleted,
`test_hud.py`'s byte literal replaced); `move_b_postinc_dn` went with it and `test_stage.py`'s copy
is gone. `subq_b_d16` and the shift base opcode stand at two spellers and are annotated on both
sides.

**QUEUED, registered rather than half-done.**

* **Four batteries still merge their seeds KEY BY KEY** and are the queued consolidation onto
  `leaf.overlay`: `test_actor.py`'s `_defeat_pokes` (~3366) and `_state_pokes` (~1139),
  `test_map.py`'s `_map_pokes` (~776), and `test_scene.py`'s `_poke` (~303), whose mechanism
  *diverges* — it REFUSES a colliding key rather than overlaying it, so it cannot express a byte
  poked inside a seeded band at all. Deliberately not converted here.
* **`src/blit.c`'s `state_word`/`state_word_write`** are the WORD variant of the guarded read, but
  they guard a FIXED address and never mask, because nothing computes them. Noted, not folded in.
* **Promoting `bus_read_byte` to the kit's `machine.h`** once a second game needs it.
* **`_branch_s_to` is the third speller of a short-branch encoder** (`test_actor.py`'s `_branch_s`,
  `test_stage.py`'s `bpl_s`), and the three disagree about their guard. leaf.py already hosts the
  `.w` twin and its own rule says hoist; `_bytes_of` is its natural companion.
* **The kit's attribution pass has no fast path.** Measured under cProfile: of this battery's ~37 s
  single-process, **35 s** is `harness._attribution_check`'s per-byte Python walk of a 1 MiB image,
  once per poisoned run. `differential` itself already carries the `bytes(...) == bytes(...)`
  prefix comparison the check is missing. Kit scope, and worth more than any in-diff change: the
  in-diff copies it would be tempting to optimise (`_poked_image`, `_Memory.__init__`) total 60 ms.
* **`$17c74` and `stage_load_window` remain the PSG wall's two faces**, unmoved by this batch —
  *(batch 25 took the first, batch 26 the second; the wall is down)* —
  but the tick's callee list and its non-local exit are now recorded against the day one of them
  moves.


### Batch 22b (steps 2–3): the re-scan, and the score table that was never counted

Batch 22b's chain closed. [`PORTABILITY.md`](PORTABILITY.md) **§0h is the full record**; the
headline is that the re-scan moved almost nothing and the one figure everyone expected to move
did not. **256 → 258 functions, 25,786 → 25,826 bytes, runnable 242 → 244 / 24,358 B (94.3 %),
false-green 28 / 3,348 B — the identical function set.** Exactly two F records appear
(`actor_respawn_as_new_kind` $6cdc, 126 B, previously folded into `$6bb8`; `stage_random_kind32`
$e1c8, 40 B, previously in no function body at all) and **not one pre-existing function moves
tier, steering or reachability** — checked function-by-function against the old scan. The whole
+40 bytes is `$e1c8`.

**The prediction this batch and 22c both carried was wrong, and the correction is the finding.**
`$6bb8`'s 290-byte body was said to "fold in the 128-byte score table at `$6c5c`". It never did:
Ghidra's F `size` is the cardinality of a function's ADDRESS SET, not `body_end − entry`, and the
old record already spanned 418 bytes while counting 290. 164 + 126 = 290, so the re-cut split one
body in two at unchanged total bytes. `$1a5da` is the mirror case — 42 bytes over a 40-byte span,
because its set includes `snd_sfx_tick`'s shared `rts` two bytes BELOW its entry.

**The partition edit then landed against that baseline** and differs in exactly three subsystem
rows with no whole-program figure moving: `0x6cdc..0x6d5a` → actor (16 → 17 fns / 954 → 1,080 B)
and `0xe1c8..0xe222` → stage (4 → 6 / 458 → 548 B), one range over both draws because `$e1c8`
`bra.w`s into `$e1f0`'s shared fourteen-byte tail. `$e1f0` was checked first and was in the
catch-all, so nothing had to be adjusted. The catch-all is down to **20 functions / 2,058 B**.
One cost, named: the actor row was `T0 CLEAN` transitively and now prices `T4 HW_READ`, because
`$6cdc` reaches `rng_next`'s `$ff8209`. Runnable stays 100 %. The three batch-23 sound bodies
needed no range — the `sound (YM2149)` span already covers them.

**Sanity, reconciled:** the verified column is **171 F records / 19,226 bytes** against this
scan, and the bytes agree with the 166 reconstructions above to the byte. The gap is two counting
rules and gains one entry — `snd_sfx_tick` is one reconstruction Ghidra splits into four (the
42-byte head plus three 186-byte channel arms). Those two are the only per-row disagreements out
of 142 verified rows.

**No game code changed and no test moved**; `make test` 3333 on a forced relink, and
`tools/test_hw_portability.py`'s two literal-figure pins moved WITH the baseline in this same
commit (the scan they read is the working file, which §0h re-baselined — 37 cases green after).
**One stale figure flagged, deliberately not edited:** PORTABILITY.md §1's answer box still
prints the 2026-08-02 scan; re-stating it needs its CODE-bytes column recomputed, a measurement
of its own. **Observed, registered:** `$6bb8`/`$69fe`/`$6b46` (544 B of verified defeat-path
code) stay in the catch-all while their continuation `$6cdc` is now actor's — a partition
question for a future pass, recorded in §0h.

### Batch 24: the tick, whole — the pattern stepper, its 24 opcodes and the body that drives them

Two routines and the handler block one of them is inseparable from, **1,208 bytes**, and what they
close is the SOUND MODULE'S per-VBL tick: everything `snd_music_tick` calls was batch 23's, and this
is the tick itself. **Verified 168, 20,434 bytes, 79.1 %; `make test` 3466** (3333 before the batch,
plus its 133, all in `test/test_sound.py`, which stands at 509 — five measured trims inside that
figure, recorded below). The verified COUNT moves by two —
the two C functions — while the byte total moves by 1,208, because the 306-byte handler block is not
a routine of its own: it is `snd_channel_step`'s tail, entered by that routine's `jmp` and branching
back into its body. It gets a table row of its own anyway, because it is 306 bytes at their own
address and the pin checks them there.

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$18106` | `snd_channel_step` | 258 | one channel's pattern step: the countdown, the pitch slide, the read loop and the range decoder |
| `$17fd4` | the 24 opcode handlers | 306 | 23 bodies below the stepper, reached by its own `jmp` and branching back INTO it |
| `$17ca0` | `snd_music_tick_body` | 644 | `snd_music_tick` below its tempo head: the gate, the dropper, the fade, the rows, the mixdown and the chip |

**Unit 4 and unit 5 are one flow graph and are pinned as three blocks.** `$18106`'s last instruction
is the `jmp (a3,a2.w)` that enters a handler, and every handler but one `bra`s back into `$18106`'s
own body — at `$18116` for another pattern byte or at `$18148` to close the row. So the C is a read
loop with a three-valued exit, and the pins are the stepper's 258 bytes, the handler block's 306 at
its own base, and the tick's 644. **The two addresses the handlers branch back to are DERIVED** from
the runs above them, so the block and the stepper cannot disagree about either.

**Eight corrections, all read off the bytes** (`../names.txt`'s plates and
`../notes/sound_module_recon.md`'s addendum 3 carry them, and the three superseded lines in §6 now
carry in-place markers pointing at it):

* **The command range ends at `$b8`, not at `$97`.** `$181a6` is `cmp.b #$b8,d0 / bcs`, so
  everything below `$b8` goes to a table with 24 entries: `$98..$b7` index PAST it, read a word of
  the handlers' own instruction stream as a table entry and `jmp` through it. `$b8..$bf` fall the
  other way into the ARPEGGIO arm with a decoded index of `$f8..$ff` — entry 248 to 255 of a table
  that holds SIXTEEN. Both halves were "out of range" in the notes; they behave differently, and only
  the second is portable.
* **The opcode census, re-derived and self-proving.** The notes' counts do not tile — `$87`×92 plus
  `$8e`×11 is 103 against 106 patterns, every one of which ends in one or the other. The walk this
  battery RUNS gives `$80`×658, `$87`×95, `$8f`×88, `$8a`×51, `$88`×48, `$92`×16, `$8e`×11, `$89`×5,
  `$81`×4, `$93`×3, `$82`×2, and 95 + 11 = 106 exactly. **Eleven of the 24 opcodes are reached and
  thirteen are not**, and every row of the opcode grid says which it is, from the walk rather than
  from a table.
* **Thirteen instruments, not fifteen**: `$d0`, `$d1` and `$d4..$de`. The notes stated the range.
* **`$18106` and `$17ca0` inherit a3**, joining `$1aaca` and `$18208`. The stepper opens
  `subq.b #1,27(a0)` and the tick body `tst.b 2250(a3)` — the `lea` is in the tempo head above it.
* **The mixdown's three arms are 54 / 52 / 52 bytes, not three of a kind.** Channel A's alone
  carries a `bmi.w $17c72`: a NEGATIVE SFX-active flag abandons the whole tick, the mixer mask and
  the chip write included — the same double test of the same byte that opens `snd_sfx_tick`. B's and
  C's alone carry the `rol.b #1`/`#2`. The three `ori.b` immediates `$09`/`$12`/`$24` are ONE
  constant rotated by the channel number, and are also the three records' constant `+47`, which a
  case asserts.
* **Two `tst.l`s read a fourth byte each.** The gate covers `$17c5a..$17c5d`, so the unnamed pad byte
  keeps the tick alive; the chip block's covers `$17c5e..$17c61`, so a set pad byte suppresses the
  NOISE register while all three channels are still written. Both are cases.
* **The 51 sequence tables are NOT one band.** §6's map row shows 28 bytes at `$18508`, which is
  song 0's three; all 51 span `$18508..$1a42a` in **seventeen disjoint runs**, interleaved with the
  pattern data. The independent gate found this stated as fact on three surfaces. The load-bearing
  conclusion survives and now rests on the true span — no shipped table names a byte of the music
  channel records at `$17bc6..$17c55`, and a case walks all 51 and says so.
* **Opcode `$88` takes two operand bytes and writes three fields** — `+42` from the first and the
  second into BOTH `+41` (read without advancing) and `+43` — and then falls into `$82`'s control
  store. Opcode `$87`'s restart takes entry **0 itself**, because the reset reloads the sequence
  offset without the index it had just added to it, and it **re-reads the entry at `$18036` BEFORE
  storing the new index at `$1803c`** — see the review-gate finding below.

**The census is CLOSED, not just self-proving.** The tiling (`$87`×95 + `$8e`×11 = 106) passes just
as happily on a walk that missed half the data, because both sides of it shrink together. Opcode
`$93` re-points a channel's sequence table from two pattern bytes, so a pattern can send the
replayer at a table the walk never visited — and the walk starts from the song directory alone. The
three shipped `$93`s (patterns `$1872c`/`$1877b`/`$187c6`) name `$1871c`/`$18722`/`$18728`, mid-table
tails of tables already walked, so the set really is closed; a case asserts that every retargeting
operand lands inside a walked span rather than assuming it. It was verified to BITE: restricted to
song 0's three tables, all three retargets escape.

**And the operand lengths the census walks on are DERIVED from the model**, not a third hand-written
table. The entry pin checks each handler's `move.b (a1)+` instructions against the image, the
differential checks the model against the original, and `_derived_operand_lengths` reads the count
back out of the model's own cursor — so the published reachability column rests on the run. The
construction that motivated it: transcribe `$89` as taking no operand and its operand byte decodes
as a note with the census set unchanged. The arpeggio and instrument tails are the walk's claims too
now (bytes at or above `$b8` are counted by range): **only `$cf`, twice**, **thirteen** instruments,
and **no shipped byte anywhere in `$b8..$bf`** — which is what makes that whole range's case a seeded
one.

**The three case-design facts the batch was handed, and what they became.** The drop byte `$17c6e`
is an image byte, so a case pokes it: all three of the values the unported head can write, each on
both sides of its wrap. The `$17f08` mixer read is Phase 6's case: every tick case declares register
7 with `psg_seed`, and the ordered ledger and the register file are compared alongside the image —
`MIXER_SEEDS` and its four-direction-state guard are the stop chain's own tuple, reused. And **the
non-local exit is pinned from the TICK and never standalone**: `snd_channel_step` returns a status,
the tick acts on it, and the `$8e` case runs the whole tail from `$17ca0` — where the stack holds
the frame `addq.l #4,sp` is written for — with the PSG ledger as the proof that the rest of the tick
never ran (four accesses, silence's, and not the output block's fifteen).

**Mutation sweep: 62 mutants across three passes, per README.md's recipe** (forced relink per
mutant, unpiped returncode, `__pycache__` purged before each run, green immediately before). **62
non-equivalent, all 62 caught, none uncompilable.** The first pass ran 60 and left THREE survivors,
and all three were holes in the CASE DESIGN rather than in the port:

* **the hand-over ladder read one mixer byte for all three rungs.** Every row of the grid gave the
  three SFX channels the SAME descriptor `+6`, so a ladder that read channel A's state block for
  every rung agreed with all five. The rows now carry three different bytes and name which channel's
  block can see the difference.
* **...and every noisy channel in that grid was also ARMED**, so a ladder that dropped the `tst.b`
  on the flag passed too. Two rows now arm nothing and leave the noise bits on.
* **the mixdown's sign test was only ever exercised on channel A.** A `bmi` on all three arms passed
  the whole grid, because no row gave B or C a negative flag — for which a negative flag is merely
  non-zero and the arm RUNS. That row is now there.

The last two mutants came from the reviews: the sequence walk's store order (below) and the
`$98..$b7` refusal. **The final sweep was re-run whole rather than over the changed lines** — the
independent gate's trims and the folded tick driver touch every tick and SFX case, so a subset would
have measured the wrong thing.

**Five measured trims, batch-17's bar** (each removed run named the mutant it does NOT uniquely
catch, checked at the mutant level before the cut). The tick-drop grid lost the `$48` pair either
side of its own wrap — two runs re-making the claim the `$2b` pair makes, since every mutant that
grid is for dies on `$2b` — and kept the `$48` row the three-value guard needs. The tick's mixer
sweep took ONE row per state of the preserved bits instead of the stop chain's seven, three runs
fewer, and it is thinned FROM that tuple rather than re-tupled, so there is still one source; its own
guard says all four states survive the thinning.

**The pre-commit review gate found a REAL DIVERGENCE the suite could not see.** `movea.w
0(a3,a2.w),a1` at `$18036` re-reads the sequence entry and `move.w d0,10(a0)` at `$1803c` stores the
new index — **in that order** — and the port had them the other way round. It is invisible to every
ordinary walk, because a sequence table only ever names a place outside the record; it becomes
visible the moment the table names the record's own index WORD, which opcode `$93` can arrange from
two pattern bytes. Fixed in both the reconstruction and the model, and pinned by a case that SOLVES
`(offset + index) & $ffff` for the aliasing offset rather than transcribing one — plus a guard that
the alias really is one and that the two notes a store-first port would tell apart differ. The
mutant is in the sweep and is caught.

Five more findings were fixed and none of them was a divergence: a parameter that shadowed the
file's own `trigger_channel` helper (renamed `sfx_channel`), the channel-to-tone-register arithmetic
spelt twice in one twenty-line span (the REGISTER NUMBER is now the primitive and the shadow address
is derived from it, which is also what the test model does), `_module_address` and `assert_psg_state`
each written twice in the battery (one speller now, and `_Memory.set_bits` joins `decrement` as the
second read-modify-write the models had said four times), the hand-over cases hand-rolling
`_run_channel_step`'s whole run protocol (they call it, with the poke layer it now takes), and a
comment that put the `$b8..$bf` arpeggio overrun at "16 to 31 entries past" when the decoded index is
248 to 255 of a table holding sixteen.

**Not pinned, honestly.**

* **The 44-byte tempo head `$17c74..$17c9f`.** It reads `$fffa01` bit 7 and `$ff820a` bit 1 and
  writes one byte from them. No memory differential can answer either, so it stays behind the kit's
  hardware-seed phase; everything it can hand the body is `$17c6e`, and the battery pokes all three
  of its values. No case enters at `$17c74`. The `rts` at `$17c72` belongs to neither the head's 44
  bytes nor the body's 644 and is reached by four of the body's exits.
  *(RESOLVED — batch 25. The hardware-seed phase landed as the kit's Phase 7 and this head is its
  first consumer: it is reconstructed, cases enter at `$17c74` with `hw_seed=`, and one declaring no
  machine is refused. The `rts` sentence still stands.)*
* **`$98..$b7`, the one branch of the ported code that is not reproduced — and it now REFUSES rather
  than being merely documented.** The dispatch reads a word of the handlers' own instruction stream
  as a jump target; there is no C for that, and the first draft returned "read the next byte" and
  said so in a comment, which is indistinguishable from an ordinary opcode to everything that is not
  a differential. It now goes through the kit's own refusal helper (`os_refused`, `os.h`), so
  `harness.differential()` throws away any run that reaches it, and two cases — `$98` and `$b7`, the
  first past the table and the last the `cmp.b` keeps — drive the candidate ALONE (there is no oracle
  run to pair them with) and require the tally, with a third requiring an in-range opcode to leave it
  at zero. It is still unreachable from the game's data; this is what happens if that is ever wrong.
* **What is HEARD.** The chip surface is now a real one — an ordered ledger of up to fifteen accesses
  per tick and a register file — but it is still register values, not sound. A green suite says the
  right bytes reached the right PSG registers in the right order and says nothing about the audio.
* **The thirteen unreachable opcodes' semantics.** `$83`/`$8d` set a flag bit nothing in the ported
  tier reads; `$84`/`$85`/`$86`/`$90`/`$91` write fields `$18208` and `$18106` do read, so their
  effect is pinned, but no shipped song ever asks for it. Their behaviour is reproduced; what they
  are FOR is not established.
* **d1 at the tick's three calls into `$18106`.** Only opcode `$97` reads it, and it occurs zero
  times in the shipped data, so the tick hands the stepper a value of its own
  (`SND_TRIGGER_CHANNEL_UNMODELLED`) and a case guards that no tick-entered stream contains a `$97`.
  The defect itself IS pinned, from the stepper's own entry, over all four of the trigger's
  selectors.
* **The supervisor window.** `move.w sr,d1 / move.w #$2700,sr … move.w d1,sr` has no C analogue and
  the oracle enters at `$2700` already. What IS observable is that the SR save destroys the channel
  volume d1 was carrying — the outgoing d1 is exactly `$2700`, its high half zero because `$18208`'s
  own `moveq #0,d1` cleared it — and a case asserts that on the ORACLE, the precedent being the stop
  chain's saved SR in d2.

**What a multi-tick sequence can and cannot claim.** Both tick drivers are now one
(`_run_tick_sequence`, shared by `$1a5da` and `$17ca0`), and folding them surfaced a real asymmetry:
the image carries between ticks because the pokes do, and the **chip does not**. That is the
harness's rule rather than a shortcut — `differential()` calls `g_psg_reset(seed, known)` at the head
of every run on both sides, so a model that carried its own register file forward would expect a
read-back the oracle is never served and the case would redden on the harness instead of on the
game. A multi-tick sequence here is therefore N runs from one declared chip state and **not a
continuous chip timeline**; the driver says so where a reader would otherwise assume otherwise.

**Two mechanisms went to `docs/m68k-disassembly.md`**, in the same commit and grounded in this
batch's addresses: *the table with no bound, and the range decode that is wider than it* (the port
stance — refuse, don't approximate — and the closure guard a "the data never gets there" claim owes),
and *the other frame rewrite: a callee that pops its caller's return address* (why the pin can only
be written from the caller's entry, and why the off-image surface is the witness). Both sit under the
existing jump-table and `addq.l #n,(a7)` sections they extend.

**The sound module is now ported from stub +14 down.** `snd_play_song` (+0), `snd_resume` (+42) and
`snd_start_fadeout` (+84) are the three stub entries left, and none of them is behind a wall: they
are ordinary image work above a tier that is now whole.

**QUEUED, registered rather than half-done.**

* **`test_actor.py`'s PSG assert is `leaf.assert_psg_surfaces`'s third caller.** The helper was
  hoisted out of `test_sound.py` this batch (it had two spellings, and its own docstring names the
  hazard); `test_actor.py` asserts one of the two surfaces piecemeal — `psg_events == []` for a path
  that must not touch the chip — and converting it is deliberately not folded in here.
* **`assert_psg_state` still computes the stop chain's expectation from the seed** while the tick's
  records it. Both go through the hoisted helper now, so they cannot drift apart on the COMPARISON;
  they can still drift on what they expect, which is the right place for two statements.
* **The `$98..$b7` refusal has no on-target story.** This project has no Atari build today; one would
  need `OS_NO_REFUSAL_TALLY` (os.h) and would then walk on silently. Noted where the branch is.

### Batch 25: the tempo head — the sound module's last bytes, and the first DECLARED machine

**44 bytes**, and what they close is the whole sound module: everything at `$17adc..$1abc8` that
Ghidra recovered is now reconstructed except the three stub entries above the tick. `snd_music_tick`
is WHOLE — its 44-byte head and batch 24's 644-byte body tile `$17c74..$17f23` with nothing between
them, and a case asserts both joints. **Verified 169, 20,478 bytes, 79.3 %; `make test` 3483** (3466
before the batch, plus its 17, all in `test/test_sound.py`, which stands at 526). The verified count
moves by ONE and the byte total by 44.

**The count needs a word, because `$17c74` was already an `F` record whose body batch 24 ported.**
Ghidra's function at `$17c74` is one record; this project counts C FUNCTIONS and their bytes, and
batch 24 split the record into two of them so the body could be entered below the wall. So batch 24
counted `snd_music_tick_body` (644 B) and batch 25 counts `snd_music_tick` (44 B); the two together
are the record, no byte is counted twice, and the denominator is unchanged at §0h's 25,826.

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$17c74` | `snd_music_tick` | 44 | the tempo selector: two hardware reads, one image byte, and the fall into the body |

**The bytes, read rather than taken from the plate — and the plate was right about the values and
silent about the polarity, which is the whole of what a port has to get right:**

```
$17c74  lea   $1738c(pc),a3        ; the module base — THIS routine establishes it
$17c78  move.b #$0,2274(a3)        ; the 50 Hz value goes in FIRST, unconditionally
$17c7e  btst  #7,$fffa01           ; GPIP bit 7: mono-monitor detect, ACTIVE LOW
$17c86  bne.s $17c90               ; SET = a COLOUR monitor -> skip the mono store
$17c88  move.b #$48,2274(a3)       ; mono: drop 72/256
$17c8e  bra.s $17ca0               ; ...and NEVER read the shifter
$17c90  btst  #1,$ff820a           ; sync bit 1: SET = 50 Hz
$17c98  bne.s $17ca0               ; 50 Hz -> keep the 0 already stored
$17c9a  move.b #$2b,2274(a3)       ; 60 Hz: drop 43/256
```

**Both branches are `bne`, so both immediate stores are the bit's CLEAR meaning** — which is why an
emulator answering 0 for both lands on MONO, and why a port written from the register NAMES rather
than from the bytes gets both arms backwards. The C is a selector returning the value and one store
by the caller: the original's unconditional `move.b #0` and the two overwrites leave exactly the byte
a single store of the chosen value leaves, and the shape says which of the three the machine chose.

**The read COUNT is program behaviour, not an implementation detail.** The mono arm `bra.s`es over
the sync test, so a mono machine never touches `$ff820a`. No image byte can show that — the drop
value, the write set and every register are a correct run's exactly — and the differential's ordered
read stream is the only witness. It is a case, and the mutant that reads both bytes every time is
caught by the mono rows and by nothing else in the suite.

**Three machines, declared as the BIT and its COMPLEMENT.** `$80`/`$7f` for the GPIP and `$02`/`$fd`
for the sync, so every other bit of the byte carries the opposite value and either `btst` off by one
reads the branch backwards on one of the two rows. A fourth case declares the machine's REAL bytes,
taken from `emu.hw_capture_profile()` rather than restated — and reconciles them: **`$b0` has bit 7
SET, which because the detect line is active low means a COLOUR monitor**, with bits 5 and 4 the FDC
and ACIA lines (also active low, so set because idle); `$02` is 50 Hz. The profile therefore selects
drop 0, no tick is dropped, and `out/audio`'s 17 songs were captured at the speed they were written
— which is what the extraction's correctness rested on, unstated until now.

**The false green this closes had SHIPPED, in this repository, documented.** `PORTABILITY.md` §4's
prediction table carried `snd_music_tick $17c74 — completed green in 12 insns` against a prediction
of "rejected", and §4's last subsection reproduced the nine instructions above and said in as many
words that nothing in a memory differential can tell. That row is now RETIRED in place with a marker
citing this batch, and the two prose paragraphs carry markers of their own: the general claims stand,
the example does not, because a differential of `$17c74` that declares no machine is refused. A case
here states the refusal from this project's side — and it names ONE address, not two, because the
fabricated 0 already steered away from the second read.

**The refusal is a different shape from the PSG model's, and the case says so.** An undeclared PSG
read sinks `emu.run` itself (`RuntimeError`, every caller); an undeclared hardware read is served and
merely recorded, and only `harness.differential` refuses (`AssertionError`). That asymmetry is
deliberate kit design — a bare `emu.run` drives this project's relocator, Copylock and bootstrap, and
verifies nothing, so it cannot be falsely green — and `test_audio_capture.py` still runs `$17c74`
under a bare `emu.run` on the very next line of the suite.

**`test/leaf.py` threads `hw_seed`**, which is the registered follow-up from batch 21b repeated one
model over: that batch found `leaf.run` had no `psg_seed` parameter, so the kit's newest capability
was unreachable from a leaf case. `hw_seed` is threaded the same way — through `run`, and so through
`run_reaching`, which forwards `**kwargs` — with the docstring naming the difference from `psg_seed`
(where the refusal fires, and why). `leaf.py` also gains `MFP_GPIP`/`SHIFTER_SYNC`, spelt as literals
because they are a fact about the GAME's `btst` operands, and pinned equal to `emu.HW_ADDRS` by a
case, exactly as `PSG_SELECT` is shared and pinned. `test_audio_capture.py` now takes the sync
address from there instead of restating it, and its two tick-drop constants from `wonderboy.h`
instead of duplicating the port's.

**Two stale comments in `test_audio_capture.py`, both retired.** One cited `shim.c`'s
`#define SHIFTER_SYNC`, deleted when Phase 7 folded the capture mode into the seeded model. The other
said a wide read of a tempo byte is "an ordinary off-image 0" off the mode — false since Phase 7,
which records the wide-read mask on EVERY run and refuses on it in EVERY differential; what is
capture-only is where `emu.run` *raises*, because an extractor has no diff to catch it.

**Mutation sweep: 14 mutants, per README.md's recipe** (forced relink per mutant, `__pycache__`
purged, unpiped returncode, green verified immediately before and after). **14 non-equivalent, all 14
caught, none uncompilable, no second pass needed.** The three worth naming, each caught by a
different row:

* **the sync register read unconditionally** — caught by the mono rows ALONE (five of them), on the
  read stream, with the image and the write set identical to a correct run's;
* **either `btst` off by one** — caught because the complement bytes carry every other bit set;
* **`leaf.run` dropping the `hw_seed` forward** — caught as the undeclared refusal, which is what
  says the threading is load-bearing rather than decorative.

**The observable surface this change is caught by**: the modeled hardware READ LEDGER (an ordered
`(address, byte)` stream both cores keep, compared by `harness.differential`), plus the image diff
and the PSG ledger the tick already had. The read ledger is new to this project and is the only
surface that can see any of the head's behaviour except the one byte it writes.

**Not pinned, honestly.**

* **That a real ST serves these bytes.** `hw_seed={$fffa01: $b0, $ff820a: $02}` is the case's CLAIM
  about the machine — "a 50 Hz colour ST with the FDC and ACIA lines idle" — and what the
  differential pins is "given those bytes, both cores agree". This is the kit's own stated limit
  (`TRAP_MODEL.md`, "Phase 7 — the honest limit"), not this batch's, and it is not closable by any
  differential: it is a documented hardware fact, re-checkable only on hardware. What HAS changed is
  that the claim is now written down and shared instead of fabricated as 0 on both sides.
* **The FDC/DMA registers**, which stay outside the modeled set by design: an FDC status byte answers
  a per-access SEQUENCE, not a per-run constant, so `fdc_wait_irq`'s poll on `$fffa01` bit 5 and
  `fdc_wait_irq_bounded`'s on `$ff8609`+ cannot be seeded. `$fffa01` being IN the set for bit 7 does
  not help them: a case declaring bit 5 set spins to `max_insns`, which is loud rather than silent.
* **What is HEARD**, unchanged from batch 24: an ordered ledger of PSG accesses and a register file
  are register values, not sound.

**QUEUED, registered rather than half-done.**

* **`src/sound.c` now has an OFF-TARGET-ONLY dependency, and this project has no on-target build to
  test it against.** `hw.h` states the rule — a real Atari build reads the address itself and does
  not compile `src/hw.c` — so an on-target `snd_music_tick` needs `hw_read8` replaced by a
  `*(volatile uint8_t *)0xfffffa01` read, exactly as BuggyBoy's remaster does. The hazard if that is
  missed is not a link error but a **silent one**: linking `src/hw.c` into a target build with no
  seed installed serves 0, takes the mono arm, and plays every song 28 % slow on hardware — the very
  defect this batch closes off-target. Registered beside the `$98..$b7` refusal's identical gap.
* **`tools/recreate_kit/TRAP_MODEL.md`'s Phase 7 section says "No project passes a `hw_seed` yet —
  Wonder Boy's `$17c74` head is the consumer this was built for, and porting it is the next step".**
  This batch is that step; the sentence is now stale. The kit is outside this commit's pathspec, so
  it is registered here rather than edited.
* **Nothing asserts a DECLARED hardware seed was actually read**, at the level `leaf.run` threads it:
  two empty streams compare equal, so a case whose entry point never reached a `btst` would pass.
  This batch closes it inside `_run_tick_sequence` (every whole-tick case states its expected
  stream), which is right for one consumer. The depth-correct home is the kit — `harness.py` already
  has `_vet_psg_seed_reaches_the_path` for exactly this on the PSG model and no hardware twin.
* **`PORTABILITY.md` §0g's classifier row for `$17c74` still ends "it stays in the false-green 28".**
  Marked in place; the FIGURE is a measurement and is not edited without re-running the scan, which
  is the `tools/hw_portability.py` re-pricing pass already queued below.
* **`$17c6f` has no `var` line in `../names.txt`.** The drop ACCUMULATOR is a module global the
  reconstruction names (`WB_SND_TICK_DROP_ACC`) and its neighbour `$17c6e` is named; it belongs to
  batch 24's body rather than to this head, so it is noted here rather than folded in.
* **`tools/hw_portability.py` still prices `$fffa01`/`$ff820a` as "served a real byte ONLY under
  audio capture".** That was already registered by the kit's Phase 7 as a follow-up and is now
  doubly stale: this batch's cases are served those bytes under an ordinary differential. Re-pricing
  the tier is a measurement pass, not a comment edit.
* **`../notes/portability_predictions.py`'s two `T4` cases** still match `emu.run`'s refusal by a
  regex that passes for the wrong reason (§7's registered item). A third is now available and would
  be the honest replacement for the `snd_music_tick` row this batch retired: the refusal WITHOUT a
  `hw_seed` and a green run WITH one.

### Batch 26: the stage-transition hinge — $f95c runs WHOLE, and the dropped-write tier is named

`stage_load_window` ($f95c, 210 bytes) has been the T-tier hinge since batch 12: every stage entry
in the game goes through it, and the scene tier's four exit tails dead-end at its boundary. Both of
its historic blockers are gone. Blocker 2 fell with batches 21b–25 (the sound module is whole), and
blocker 1 — `bsr set_palette`, sixteen words to the shifter — turned out not to be a blocker but a
MEASUREMENT: the routine touches no image byte at all, so it is portable, and what it is portable
*at* is nothing. Three routines, 374 bytes. **Verified 172, 20,852 bytes, 80.7 %; `make test` 3546**
(3483 before the batch, plus 63: +31 in `test/test_sound.py`, which stands at 557, and +32 in
`test/test_stage.py`, which stands at 112 — two measured trims inside those figures, below).

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$f944` | `set_palette` | 24 | the shifter palette — and the DROPPED-WRITE tier |
| `$17b3a` | `snd_play_song` | 140 | stub +0: the routine that writes the module's mutable bands |
| `$f95c` | `stage_load_window` | 210 | the hinge, entered at $f95c and left at its own `rts` |

**IT RUNS WHOLE.** Every callee is reconstructed — the three builders (batch 12), `set_palette`,
`snd_play_song`/`snd_stop` — so a case enters at $f95c and comes out of the original's own `rts`
with no `stop_pc`. The composition is asserted through the callees' OWN models (`_model_build`,
`_model_preshift`, the review pass's `_model_publish`, and test_sound.py's `model_play_song` /
`STOP_WRITES`, which test_stage.py now imports): 180 KB of buffers, the published scroll state, the
followed record, the two follow words, the tune latch and the sound module's write set, compared
for EQUALITY against one model. Nothing is restated — two copies could disagree while both
batteries stayed green, which is why the review pass turned the last inline copy into the shared
`_model_publish` before this section could claim it.

**THE DROPPED-WRITE TIER, and why it is a finding rather than a gap.** WB_SHIFTER_PALETTE is off the
loaded image, so shim.c drops all eight `move.l`s; the kit models hardware READS (Phase 7) and has
no ledger for a write. So a reconstruction that wrote the wrong sixteen colours — or none — is
separable from this one by NOTHING the harness compares. The batch does not pretend otherwise: the
case asserts an EMPTY write set on both sides, the returned source cursor, and the oracle's own a1
landing at $ff8260, and the claim is stated where a reader meets it (src/stage.c, include/stage.h,
the battery's docstring). THE SWEEP IS WHAT PROVES IT IS A HOLE: three of its four survivors
(row shift, colour count, unscaled row) are one hole seen three ways, while the mutant that returns
the un-advanced cursor IS caught. REGISTERED, not built: a dropped-hardware-write LEDGER in the kit,
which would make this pinnable the way psg.h made the chip writes pinnable.

**THE CASES ARE THE GAME'S OWN DATA.** The .PRG ships FIVE start records at $1d40c..$1d43d, found by
reading $f95c's callers: four carry song ids 1..4 and one ($1d42a) carries $ff, the negative byte
that stops the module — so both arms of the tail are shipped, and so are palette rows 0 and 1. The
ten-byte record length is settled three ways over that block: stage_start_table's eight pointers step
by ten, the five records sit ten apart, and the last ends EXACTLY where bg_tile_bitmaps begins. Two
cases seed a record of their own, for the one thing the shipped five cannot reach: their map cells
are all (0,0), so nothing in them leaves a non-zero WB_BG_SCROLL_POS_X for the follow subtraction.

**snd_play_song is what makes the tick tier's bands defined.** Batches 23–25 seeded $17bc6..$17c71 by
hand because the .PRG ships it dirty; this is the routine that writes it. It also stops the module
first, and through the +28 STUB rather than $17f24 — the `movem` pair is what carries the song id in
d0 across a routine that silences the chip, which is why a start's PSG traffic is exactly a stop's.

PLATE CORRECTIONS, all cited to bytes (../names.txt): $f95c re-reads its own latch three times, so
its operands are 4(a0)/9(a0)/8(a0) and not 4(a1)/9(a1); its caller list was decomp.c's numbering and
is now the six real sites; $f9d6's `move.w 8(a0),d0` is a DEAD read. $17b3a's plate omitted the
`st 2270(a3)` at $17bb8 — the row accumulator starts SATURATED, so a song's first row steps at once.

**THE REVIEW GATE'S FINDINGS, all landed.** The one that mattered most was an INVARIANT the batch
had silently dropped: switching the pattern census from `leaf.entry_of("snd_song_directory")` to
the header constant left names.txt's `var 0x18480` pinned by NOTHING — after a re-bootstrap the
name map could label a different address while all 3,546 cases stayed green. The cross-pin is
restored as its own case, and the batch's three new two-source addresses (`stage_start_table`,
`stage_start_records`, `palette_table`) got the same parametrized pin. Also landed: `_model_publish`
extracted (the battery's own no-restatement claim is now true); two dead band tuples deleted whose
comment miscounted their own entries; the +28 stub offset collapsed from FOUR spellings (the fix
found one more than the review) to one exported constant; `leaf.brief_extension_word` now owns the
68000 brief-extension-word format for both its callers; the published-band margin seeding shared
and its 0x40 named; and `PLAY_SONG_MIXER` derived per the file's own TICK_MIXER precedent, which
surfaced `SONG_LOADED_SET` defined twice under one name.

**Two measured trims** (each removed run named the claim it re-makes): the shipped-bank flag case
(a whole 180 KB composed run whose ternary mutant already fails all five shipped-record runs), and
the play-song mixer sweep thinned from seven rows to four per `_one_seed_per_direction_state`, with
its own four-state guard — what a row here uniquely buys is a start reaching the chip through the
+28 stub with the declared seed intact; the per-seed ori-preservation claims are the stop chain's
own sweep.

SWEEP: 21 mutants over five pre-hoc axes (constant / branch / index / dropped store / order),
17 caught — re-run WHOLE after the review fixes, byte-identical verdicts. Three survivors are the
palette hole above; the fourth (reading the record from the entry register instead of the
re-latched pointer) is an EQUIVALENT mutant — the routine writes a1 into $fe1a itself and nothing
between rewrites it.

NOT PINNED, and REGISTERED:

* **What reaches the shifter** (above), and with it the palette row a record names. The kit-scope
  remedy — a dropped-hardware-write ledger, the write-side twin of Phase 7 — is REGISTERED here:
  trigger = the next routine whose whole observable is hardware writes; home = tools/recreate_kit.
* **$101be (66 B) is READ, not ported** — entry 1 of scene_exit_action_table: four state writes, an
  allocation whose record is DISCARDED (a1 never written through), and a counter ($21c58) no reader
  reads. Its one callee is reconstructed. **$dfbe is down to ONE blocker — porting those 66 bytes —
  and is the next batch's opener.** test_scene.py's four exit-tail cases keep their
  stop_pc-plus-transfer-witness convention until then.
* **No 24-bit bus guard on stage_load_window's three pointer arguments** — bg_build_buffer's
  exposure since batch 12 over the same three registers, so guarding it is a change to that tier,
  REGISTERED as one item: no shipped caller can produce a pointer above the image (five `lea`
  literals, and stage_start_table's eight entries are all $217d8..$2181e).
* **decomp.c is one reapply behind names.txt** (the stage_start_table rename) — the reapply rides
  with the next re-scan, per the two-stage measurement discipline.

### Batch 27: the scene tier closes — $dfbe runs, and its dispatch is on the WRAPPED offset

`scene_exit_and_reload` ($dfbe) was the scene driver's boundary for eight batches: four of $dbc0's
exits transfer to it, and it ends in `jsr stage_load_window`. Batch 26 made that hinge run whole and
left exactly ONE blocker — the 66 bytes of entry 1 of its dispatch table. Those 66 bytes are ported
here, and with them the whole eight-entry table turns out to be reconstructed code, so the dispatch
needs no refusal beyond its own bound. Three routines, 172 bytes. **Verified 175, 21,024 bytes,
81.4 %; `make test` 3594** (3546 before the batch, plus 48, all in `test/test_scene.py`, which
stands at 231; `test/test_stage.py` holds at 112 across a refactor).

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$101bc` | `scene_exit_action_none` | 2 | entry 0: an `rts`, and what BOUNDS the table |
| `$101be` | `scene_exit_action_select_a30_table` | 66 | entry 1: publish, allocate, republish, count |
| `$dfbe` | `scene_exit_and_reload` | 104 | the exit tail, entered at $dfbe and left at its own `rts` |

**THE TABLE IS ALL PORTED CODE, which is why there is no boundary.** Entries 2..7 are effects.h's six
`set_state_*` stubs (batch 1), entry 0 is the bare `rts` and entry 1 is this batch's 66 bytes. The C
dispatches through a `static void (*const EXIT_ACTIONS[8])` array whose order test_scene.py compares
entry by entry against ../names.txt, the same rule EFFECT_HANDLERS follows.

**THE DISPATCH IS ON THE WRAPPED OFFSET, AND THE REVIEW GATE'S OWN FIND IS THE PIN.** `lsl.w #2`
wraps in 16 bits, so the OFFSET selects the entry, not the index: $4000..$4007, $8000..$8007 and
$c000..$c007 alias onto entries 0..7, and the original dispatches ported code for all thirty-two
in-table index values. The batch as first written guarded on the RAW index — refusing 24 indices
the original dispatches, a reproducible divergence driveable from the disk's own descriptor word —
and the gate caught it. The fix computes the wrapped offset with the same expression the
start-index read uses ten lines below, an enumeration case pins the aliasing set over all 65,536
index values, and three differentials drive one alias per band onto three DIFFERENT entries. The
re-sweep's most valuable mutant is the gate's own defect — the raw-index guard restored — CAUGHT by
those three rows.

**TWO INDICES ONE WORD APART, AND THE PORT TREATS THEM DIFFERENTLY ON PURPOSE.** The exit-action
offset is REFUSED outside the table — the original `jsr`s through a longword outside it
($101bc's own first four bytes, odd and past the image) and no C stands in for that. The
START-table index is REPRODUCED, because it is a data read: a case drives $ffff, which lands four
bytes BELOW the table, and seeds the record it names. docs/m68k-disassembly.md's "table with no
bound" section now carries BOTH halves — refuse the code dispatch, reproduce the data read — with
$dfbe's pair as the worked example, so the next porter neither fabricates an arm nor over-refuses
a load.

**THE ORDERING $101be GETS WRONG-LOOKING, and how a differential sees it at all.** It publishes
WB_ACTOR_TABLE_DEFAULT, allocates out of THAT table, and republishes the pointer as
WB_ACTOR_TABLE_A30 — so the table searched is not the one left selected, and the allocated record is
DISCARDED (a1 is never written through). Both stores leave one longword behind whichever way round
they run, so no image byte separates them. The battery seeds a free record in exactly ONE of the
three tables and reads the ordering off whether WB_SCENE_EXIT_ALLOC_COUNT moved. That counter has
one operand site in the image and NO reader; it is the allocation's only lasting effect.

**THE FOUR EXIT TAILS ARE NOW FULL RUNS**, and what that traded is stated AND ENFORCED. Batch 19's
convention was a `stop_pc` at $dfbe plus a coverage witness naming the transfer; the witness stays
and the checkpoint is gone, so each of the four runs the arm, the exit, the dispatched action and
the whole stage reload to the original's own `rts`. A checkpoint compared the image at the INSTANT
of the transfer; a full run compares it at the end. Nothing is lost to an overwrite because the
four arms' write sets are DISJOINT from $dfbe's — and after the review pass that argument is a
CHECKED PROPERTY: run_frame_to_reload refuses a prefix/tail key overlap by name, so a future arm
whose write lands in the tail's set fails loudly instead of being silently un-pinned. What IS gone
is ORDER — an arm that wrote its byte after the tail is now indistinguishable. Batch 22's lesson,
applied to its own successor and this time bolted down.

**THE COMPOSITION IS THE OWNING BATTERY'S MODEL, not a second one.** test_scene.py imports
`load_window_pokes` / `model_load_window` from test_stage.py (renamed public and parametrized by
`map_ptr`/`stride` for this caller), the six stubs' destinations from test_effects.py's
WORD_SETTERS, and the PSG expectation from test_sound.py. `leaf.assert_written_is` was hoisted out
of test_stage's `_run_load_window` when this became its second and third caller — and the review
pass made its `extra` contract coherent: a model∩extra overlap is REFUSED by name, since an address
belongs to one side or the other.

**AND THE MAP $dfbe PASSES IS WB_MAP_ROW_STRIDE'S OWN ADDRESS.** `lea $22090.l,a0` names the word the
collision map is addressed from and the word the publish multiplies the start cell by — so for THIS
caller the level map's header width and the global stride are ONE word, where test_stage.py's cases
keep them deliberately apart. The seeding layers genuinely overlap, which is why they go through
`leaf.overlay` with `assert_bands_are_seeded` per layer. THE ORDER OF THOSE LAYERS IS LOAD-BEARING
AND WAS WRONG ONCE: the scene arm's address-keyed descriptor band buried the two words the tail
reads, and the run walked into a garbage start record instead of failing. Both descriptor words and
the start pointer are now re-read OUT OF THE COMPOSED IMAGE and compared against what the case
declared.

PLATE CORRECTIONS, cited to bytes (../names.txt): $dfbe's two clears are NOT a pair — `clr.b $c031`
at $dfd8 is the instruction after the dispatch and `clr.w $d76` at $e002 is the LAST before the
call, so this path always hands the hinge an UNFROZEN scroll; `lea $22090.l,a0` is
bg_map_row_stride, i.e. the level map itself; record_ptr_10420 is read TWICE ($dfbe and $dfea);
neither index is bounded, and the dispatch's aliasing set is 32 indices; $1019c's operand site is
the abs.l longword at $dfcc (the first draft said $dfc8, which holds the `lsl.w` — caught by the
gate against the file's own convention); and the plate lists all eight targets by name, recording
that the shipped descriptor bytes are zeros — entry 0 and start entry 0 are the whole of what
shipped data reaches, a fact about the disk rather than the port.

SWEEP: 24 mutants over five pre-hoc axes (constant / branch / index / dropped store / order), 22
caught, none uncompilable — re-run in FULL after the review fixes because the C changed. Survivor 1
is the refusal's own boundary (`off by one on the 32`, which differs only at offsets no differential
can drive) — NAMED IN THE SUITE as a coverage hole. Survivor 2 is EQUIVALENT: dropping the
descriptor re-read, unobservable because $10420 has one writer in the whole image. The caps are now
DERIVED from the entry pins' own instruction tuples (`len()` of the pin IS the count), which closed
three cap defects the gate found in one move — a 21-vs-24 undercount clearing on a sibling's slack,
a sentinel double-count (the batch-24 class, recurred), and a comment contradicting its own formula.

**The observable surface this change is caught by**: the image diff (180 KB of buffers, the
published scroll state, the followed record, the five state words and the counter), the oracle's
executed-PC coverage (which transfer fired), and the PSG access ledger the reload's song tail
reaches.

NOT PINNED, and REGISTERED:

* **The refusal's boundary at offset 32** (survivor 1). Unpinnable by any differential; the case
  that states it says so.
* **`scene_run_effect` carries the SAME raw-index guard** over WB_EFFECT_HANDLER_TABLE — the latent
  twin of the defect this batch fixed, pre-existing, deliberately not changed here. REGISTERED as
  the next gate-class item: the same wrapped-offset fix, the same per-band alias cases.
* **What the shipped descriptors select.** The table is loaded from disk and the image's own bytes
  are zeros; entry 0 and start entry 0 are all that shipped data reaches. Every other row is a seed.
* **The palette every reload sets** — batch 26's dropped-write hole, inherited by eleven more
  composed runs; strengthens the registered kit-side dropped-hardware-write ledger.
* **The `start` pointer is unbounded and unguarded** — the same tier-wide bus-guard item batch 26
  registered for bg_build_buffer's three arguments.
* **$1ab4**, the one exit left. scene_spend_visit_budget's `jmp $1ab4.w` keeps its stop_pc and its
  coverage witness.

**QUEUED, registered rather than half-done:** test_scene.py's older `pokes()` still merges by KEY
(the leaf.overlay consolidation, now four batteries strong); `forward_branch` unused in
test_stage.py (pre-existing, third consecutive noticing); the scene subsystem row's re-measure
(3 of 3 reconstructed, runnable no longer 0 — rides with the next partition pass, alongside the
re-scan the batch-26 rename queued).

### Measurement, 2026-08-11 — the re-scan after batches 23–27, and the wall measured as REACHABILITY

The reapply + re-scan behind [`PORTABILITY.md`](PORTABILITY.md) **§0j**. No reconstruction changed
and `make test` is 3,594 before and after. Ghidra now has **284 functions / 26,194 bytes** (was
258 / 25,826): the 23 pattern-op handlers, `snd_music_tick`'s split into a 44-byte head plus
`snd_music_tick_body`, and batch 27's two scene exit actions, which had been in **no function body
and no tier** until `names.txt` named them. **Runnable 270 / 24,726 B = 94.4 %**; false-green
unchanged at the identical 20 functions / 2,224 B. Not one pre-existing function moved tier,
steering or reachability — checked as sets. The accounting closes exactly: +68 −6 +306 = +368,
with the −6 being the §0h address-set rule reaching `snd_music_tick` (8 B to the handlers, 2 B
back from the shared tail at `$17c72`). The batch-26 `entry_of()` cross-pins came back CLEAN over
all 253 fn addresses. One partition range added with its citation (`0x101bc..0x10200` → scene,
reached only from `$dfd6`), and the scene row's §0f shape has fully inverted: **5 of 5 runnable**.
Two of this file's own figures were one out and are corrected in place above: the headline said
175 where the table expands to 176, and the `$17fd4` row was titled "24" where its own prose and
the scan say 23. The verified column reconciles to **203 F records / 21,026 B** against 176
reconstructions / 21,024 B — the +2 is `$17ca0`'s shared tail, the address-set rule touching the
verified column for the first time. Reconciliation stands at four rows: rad 1→3, snd_sfx_tick
1→4, the handlers 1→23, `$17ca0` +2 B.

**THE COVERAGE WALL, MEASURED — it is a REACHABILITY problem, not an attribution one.** Of the
~54,854 believed CODE bytes, 26,194 are in F records (47.8 %) and **28,660 are in no function
body** — of which only 1,782 were ever even disassembled. **26,878 bytes (49.0 % of the program)
were never reached as code.** Ten gaps hold 79.9 % of the wall; excluding the Copylock ciphertext,
**nine ranges hold 21,090 bytes**, and the largest — `$2bc8..$501a`, 9,298 bytes, where the
per-monster state routines live — is a third of the wall by itself. The scout that walks these
ranges is the next phase; §0j carries the full table.

### Batch 28: the coverage wall OPENED — one extension word hid half the game

A scout pass and its yield measurement, no ports. [`PORTABILITY.md`](PORTABILITY.md) **§0k is the
full record**; `make test` is 3,594 before and after, and the verified column is untouched.

**THE MECHANISM: the per-actor behaviour tier hangs off FOUR INSTRUCTIONS.** `actor_dispatch_behavior`
($928) reads the actor TYPE out of the record, scales it, and goes `lea (0x938,PC,d1.w),a1 /
movea.l (a1),a1 / jmp (a1)` — a tail call through a 62-entry longword table whose base `$938`
exists NOWHERE in the image as an operand: it is the 8-bit displacement of a brief PC-relative
indexed extension word. That is why Ghidra never decoded the table or any of its 61 distinct
targets, and that single instruction accounted for EIGHT of §0j's nine gaps.
docs/m68k-disassembly.md's lea-extension-word entry now has its worked example at scale. Four more
indirect tables fell with it (pickup_effect_table $105ac, actor_swoop_state_table $7490,
sprite_cru_copy_table $e91c, spawn_script_gate_table $e42e), and the caller chain is
game_main_loop → $882 → actor_behavior_pass ($8d0, the per-record walker) → the dispatcher.

**THE YIELD, measured per the two-stage discipline** (§0j reproduced byte-for-byte first): 125 fn /
8 var / 134 cmt seeded — every fn disassembled at its address before naming — then reapply
(378/378 applied, 407/407 exported, zero failures, the largest application ever) and re-scan.
**284 → 407 F records, 26,194 → 44,262 bytes: coverage of believed CODE 47.8 % → 80.7 %. The wall
fell 28,660 → 10,592 bytes, and only 226 of the residue is genuinely unknown** — the rest is the
Copylock (1,754), confirmed DATA under named vars (4,734, including actor_behavior_table itself),
and the inter-handler animation word tables (3,868). NOTHING pre-existing moved on any axis, and
not one of the 123 new functions touches hardware directly. Four join the false-green set
($a38 the player handler, $b1a, $151a, $6f9e — all reach the Copylock loader and the FDC steer);
the transitive-T4 jump is rng_next's T3-DATA class, not false green.

**A SECOND MECHANISM FINDING: the island.** `$928` has ZERO callees in the scan — `jmp (a1)` is as
opaque to Ghidra's reference model as the `lea` was to its disassembler, so the whole new tier is
a call-graph ISLAND: `reachable from the roots` did not move. §0k models the 61+22 dispatch edges
by hand and prices the tier both ways; the partition was DECLINED with the numbers (no range set
is clean and stable, the tier has no principled edge — rule A pulls in three shared leaves, rule B
reaches scene_spawn_from_script not at all — and the player and monsters are two mechanisms
sharing one table).

**Scout corrections, cited to bytes**: cmt 0x1044c was wrong twice (TWO lea sites, and the pickup
path reads [4] as a longword score and [10] as a word index — the correction rides in names.txt);
architecture.md's region table over-claims CODE by ≥1,656 B read directly (registered — the 80.7 %
is a lower bound); $10714 is NOT effect_add4_clamped_b6fa (it SKIPS the store where $10296 clamps
— a meter within 3 of max stays put); $7366 carries a deliberate double-bchg no-op; the relocation
table is 3 entries and useless for pointer-table hunting (recorded so nobody retries it).

**The port campaign's order, scan-confirmed**: all 25 monster slots runnable with every callee
runnable (26 T0 + 7 T4, no walls); 30 of 61 handlers transitive T0 CLEAN — 2,860 bytes portable
with no seed at all. First: actor_behavior_pass + the dispatcher + the table (104 B, pure). Then
the vanish tail ($698a, 25 callers), the shared leaves, the slots in table order, the pickup tier,
the swoop machine, and the PLAYER LAST ($a38's subtree is where the joystick and the sound vector
bite). The cheapest naming wins left: FUN_00005c6e (42 handlers call it, 244 B), FUN_0000501a
(29), FUN_000023b6 (25).

**QUEUED**: the tier partition (revisit at the fixpoint, when porting gives the edge a principled
answer); the architecture.md CODE-column correction (its own measurement); $69de..$69fd's reader;
which monster is WHICH (needs sprite-id cross-reference or runtime observation — the handlers are
named actor_behavior_typeNN, the verified structural fact, not guesses).

### Batch 29: the behaviour tier's FOUNDATION — the dispatch runs, and the tier's grammar is named

Batch 28 opened the wall by naming one `lea`; this batch ports what is behind it, from the bottom.
Twenty routines, 1,266 bytes: the per-frame walk, the four-instruction dispatcher every monster in
the game goes through, the 62-entry table itself, the animation every spawned record plays, the
thirteen shared leaves the handlers call, and the three high-fan-in routines batch 28 left as
`FUN_*`. **Verified 196, 22,290 bytes, 50.4 %; `make test` 4019** (3594 before the batch, plus 425,
all in the new `test/test_behavior.py`).

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$8d0` | `actor_behavior_pass` | 88 | the per-frame walk over `actor_table_selected` |
| `$928` | `actor_dispatch_behavior` | 16 | the four instructions the whole tier hangs off |
| `$a36` | `actor_behavior_null` | 2 | table slots 0 AND 58: a bare `rts`, and the table's bound |
| `$698a` | `actor_spawn_anim_step` | 50 | the SPAWN animation — 25 handlers branch into it |
| `$2f22` | `actor_step_facing` | 36 | step the way the side bit points; flip it when blocked |
| `$2f86` | `actor_tick_timer30` | 72 | the countdown, and the relaunch `rng_next` vetoes |
| `$2fce` | `actor_face_and_step_toward` | 26 | face the followed record, walk TOWARD it |
| `$2fe8` | `actor_face_and_step_away4` | 30 | ...and the same shape with the arms SWAPPED |
| `$3006` | `actor_anim_step_facing_list` | 52 | a frame list per facing, terminated by a negative word |
| `$4fea` | `actor_select_sprite_by_flag` | 48 | one of three sprite ids by two flag bits |
| `$501a` | `actor_hop_ascend_step` | 44 | the decelerating rise of a hop — 36 callers |
| `$5a3c` | `actor_advance_anim16` | 18 | the 16-byte-wrap step, both registers the caller's |
| `$5c6e` | `actor_followed_overlap_mask` | 244 | three overlap tests into three bits — 42 callers |
| `$6840` | `actor_step_toward_followed` | 50 | a HOMING step on both axes |
| `$6872` | `actor_relaunch_and_anim_5160` | 84 | the $5160 stepper, with a relaunch in front of it |
| `$6d5a` | `actor_sprite_from_6ed8` | 22 | an 8-byte-stride sprite row, then a tail jump into $67e0 |
| `$6d70` | `actor_platform_carry_followed` | 104 | the MOVING PLATFORM catches the player |
| `$6dd8` | `actor_platform_release_check` | 68 | ...and lets go, four ways |
| `$701c` | `actor_face_followed_reset_22` | 40 | the side flag, at the OPPOSITE polarity to $67c2 |
| `$23b6` | `actor_hit_by_player_shot` | 172 | did anything the player threw land — 25 callers |

**THE DISPATCH BOUNDARY IS THE MECHANISM THE NEXT SIXTY BATCHES EXTEND, AND THE TARGET IS FETCHED.**
The original is `movea.l (a1),a1 / jmp (a1)` — it READS the longword — so the port reads it too,
through the bus guard. What the C carries is not a copy of the table but the list of targets it has a
RECONSTRUCTION for, keyed by ADDRESS: one row today, one more per batch. A ported target RUNS and
reports `WB_ACTOR_DISPATCH_RAN`; an unported one comes BACK as its address, and the differential runs
the oracle with `stop_pc` there plus a `cov_visited` witness on the `jmp (a1)` at $936 — batch 19's
shape and batch 22's. **One differential per slot, all 62**, plus a case that pins the image's own 62
longwords against `../names.txt`; keying on the address rather than the slot is what a POKED table
separates, and there is a case for that too. Two slots ARE ported (0 and 58, both `$a36`), which is
what makes the walk itself runnable end to end in both cores.

**THE DISPATCH IS ON THE WRAPPED OFFSET — batch 27's lesson at eight times the table.** `lsl.w #2`
wraps in sixteen bits and the brief extension word then sign-extends, so the OFFSET selects the
entry: `$4000..$403d`, `$8000..$803d` and `$c000..$c03d` alias onto slots 0..61 exactly as 0..61 do.
**248 of the 65,536 type values dispatch a table entry, and a guard on the raw type would have
refused 186 of them** — the defect batch 27's gate caught in the scene tier, avoided here by
construction. All 65,536 are enumerated against the C (eight shardable chunks) and three
differentials drive one alias per band onto three different handlers.

**FOUR PLATE CORRECTIONS, EVERY ONE CITED TO BYTES.**
* **`$698a` IS THE SPAWN ANIMATION, NOT A VANISH.** Bit 2 of `9(a0)` has exactly TWO operand sites
  in the whole image — `bset #2,9(a1)` at `$10044` inside `actor_spawn_from_template` and the
  `bclr #2,9(a0)` at `$69b0` in this body. The spawn raises it and this is the only thing that
  lowers it, so a record plays this and nothing else until it wraps. Renamed
  `actor_vanish_anim_step` → `actor_spawn_anim_step` (29 references in `../names.txt` moved with it)
  and `actor_vanish_frame_table` → `actor_spawn_anim_frames`.
* **`$2fe8` IS NOT `$2fce` WITH `d7 = 4`.** The two arms of its `btst` are the other way round, so
  one walks TOWARD the followed record and the other AWAY. Renamed to
  `actor_face_and_step_toward` / `actor_face_and_step_away4`, and the claim is a CHECKED property:
  the two shapes assembled at one address differ in exactly the two arm calls' displacement words.
* **The A34 arm's third record is SLOT 12, not 13, and it is NOT GUARDED.** `lea 352(a0),a0` from
  slot 1 lands on `WB_ACTOR_FOLLOWED_SLOT`, and `$920` is followed straight by the `bra.w $928` tail
  with no free-marker test — so a FREE followed slot is dispatched on whatever type word its 32
  bytes hold. Driven as a case. The arm never tests the `$ffffffff` end marker either.
* **`$701c` WRITES THE SIDE FLAG AT THE OPPOSITE POLARITY TO `$67c2`.** `$67c2` raises bit 3 while
  the followed record is to the actor's LEFT; `$701c` raises it while the followed record is to its
  RIGHT. Two routines eight hundred bytes apart write one bit with opposite meanings, and a port
  that called `actor_set_side_flag` here would clear the bit exactly where this sets it. It also
  takes no step at all, which its old name claimed.

**THE THREE `FUN_*` ARE NAMED FROM WHAT THE BYTES DO.**
* `FUN_00005c6e` → **`actor_followed_overlap_mask`** (244 B, 42 callers). It selects the followed
  record exactly as `$67e0` does, builds the actor's box, and answers THREE INDEPENDENT TESTS as
  three bits of d0 — two of them gated on the followed record's own SPRITE id, so what the player's
  animation is showing decides which run. Thirty callers read bit 1 and twelve read bit 0; nothing
  in the image reads bit 2 alone.
* `FUN_0000501a` → **`actor_hop_ascend_step`** (44 B). It lifts the record
  by its own `11(a0)` and then lowers that byte — a rise that decelerates by construction and ends
  when the byte reaches zero, leaving it at ONE. **36 `bsr` callers, not the 29 batch 28 counted.**
* `FUN_000023b6` → **`actor_hit_by_player_shot`** (172 B, 25 callers, every one of them
  `tst.w d7 / bne.w` into its own damage arm). Two ways in: the screen flash with the followed
  record within 140 pixels, or a record of type `$30..$32` in the HIGH allocation pool whose
  footprint overlaps — which it CONSUMES, freeing it outright unless it is type `$31`, which is
  marked and left alive.

**AND THE BATCH-28 OPEN QUESTION IS CLOSED BY SCAN, NOT LEFT REGISTERED.** `$69de..$69fd` — the half
of the frame table the `andi.w #$1f` cannot reach — has NO reader: `lea $69be.l` at `$6994` is the
only reference to any address in `$69be..$69fd` anywhere in the image and nothing computes one. 32
bytes of unreached data, stated rather than trimmed.

**THE ONE PLACE THIS PORT IS NOT THE ORIGINAL, and it is bounded.** The walk has no bound: a table
with no terminator spins forever, and past the image every read is zero — neither the terminator nor
the free marker — so it dispatches slot 0 for ever. The stride divides the 24-bit bus exactly, so
after `WB_ACTOR_WALK_BUS_CYCLE` steps the cursor has returned to an address it already read with the
image unchanged and non-termination is PROVEN. The reconstruction stops and reports rather than
hanging the suite; the oracle's instruction cap fires long before, so no differential can tell the
two apart. The derivation is pinned as a case.

**The observable surface this change is caught by**: the image diff (the actor tables, the frame
words, the two global words `$6ef0` and `$714`), the oracle's REGISTERS for the three routines whose
whole output is one (`$5c6e`'s d0, `$23b6`'s d7, `$6d5a`'s a1 — and the pass's walked-out a0), and
the oracle's executed-PC coverage, which is what says a boundary run transferred rather than
returned.

SWEEP: 43 mutants over six pre-hoc axes (constant 13 / branch 12 / index 7 / dropped store 6 /
order 3 / boundary 2), relinked per mutant with `__pycache__` purged and the compiler line checked.
**42 caught; ONE survivor, and it is EQUIVALENT** — reordering $6872's advance-then-reset into an
if/else leaves the same final byte, and the oracle's write ledger is address-keyed, so no
differential can separate them. Named in the suite. (A second survivor turned out to be a MALFORMED
mutant — it duplicated an assignment instead of moving it, so it was a no-op. Read a survivor before
believing it: the real move is caught.)

**THE REVIEW GATE MOVED THE CODE, not just the comments.** Five reviewers ran over the diff and
four findings were deep enough to change the shape: (1) the reads went through the bus guard and the
WRITES did not, so a record address that was not trusted for a read was trusted for a store — every
byte and word access now goes through `bus_read_*`/`bus_write_*`, and bus.h grew the write half with
`blit_write_word`'s own argument; (2) the walk's runaway shared the dispatcher's refusal code, so a
case could not tell "this type left the table" from "this table has no end" —
`WB_ACTOR_DISPATCH_UNBOUNDED` is its own value now; (3) `behavior.h` claimed no routine here reaches
`rng_next`, which `actor_tick_timer30` does, carrying rng.h's T3-DATA false green with it; and (4)
the compile-time copy of the 62 table entries is gone, per the fetch above. Four coverage holes came
with them, each mutation-verified: the RNG VETO arm was never driven (both cases drew the same bit,
so deleting the guard passed), `$6d5a`'s sign extension had no negative index, `$23b6`'s free-marker
skip had no row a free record could have hit, and `$6840`'s two compares had no equal case.

**AND THE SWEEP FOUND A LIVE DEFECT, by an accident worth recording.** A first sweep run was killed
mid-mutant; its restore never ran, so `constant/spawn-anim-mask` — `$1f` swapped for the sixteen-byte
stepper's `$f` — was left in the tree, and **`make test` came back 3,977 GREEN on it**. Every cursor
the battery drove answered the same under both masks (both wrap at 16 and at 32, both step at 34);
the one that separates them is 14, and it was not in the table. Three more holes came out of the
sweep proper: the strike box's near edge and the mirrored point's two offsets had no row sitting ON
an edge, the end-marker case used a PORTED type so the reconstruction answered
`WB_ACTOR_DISPATCH_RAN` either way, and the platform catch seeded a followed record whose
`LAUNCHED` bit was already clear so a dropped `bclr` wrote nothing. All four are closed by rows
that fail without the fix. **The gotcha for the next porter: a killed sweep leaves the mutant
behind — check the source before trusting the green that follows.**

NOT PINNED, and REGISTERED:

* **The refused dispatch.** A type whose scaled offset leaves the table makes the original `jmp`
  through arbitrary data; no differential can drive one. The 65,536-value enumeration states the
  refusal set exactly against the C instead.
* **`$5c6e`'s high half.** `clr.w d0` clears only the low word, so the caller's upper half comes
  back in the result register; the reconstruction returns the low word alone and nothing in the
  image reads the other.
* **The registers every other routine leaves behind** — the convention `actor.h` already sets.
* **A bus read that STRADDLES the image's top.** `bus_read_word`/`bus_read_long` answer zero as a
  whole where the shim answers the oracle per byte. Nothing in the image can drive it (the straddle
  needs a cursor within two bytes of `$ffffff` and the walk's stride is 32).
* **What each monster IS.** The handlers are `actor_behavior_typeNN` — the verified structural fact.
  Which creature each slot draws still needs a sprite-id cross-reference or runtime observation.

QUEUED, registered rather than half-done: the tier partition (PORTABILITY §0k item 7 — the dispatch
edge now has a principled answer in `BEHAVIOR_SLOTS`, so the row can be drawn); `bus.h`'s promotion
to the kit (fourth noticing); `test_actor.py`'s `pokes()` merge-by-key (fifth battery).

### Batch 30: the first MONSTER SLOTS — ten handlers, and the register the settle had to hand back

Ten dispatch-table rows flipped from boundary to call, plus the two routines the reading forced:
`actor_stun_followed` ($6796 — a `# ctx` name the batch's premise wrongly counted as ported; it is
a STUN, the first recovered reader of $bd68) and `actor_platform_release_blocked_rider` ($6e8c).
Twelve routines, ~2,294 bytes of code. **Verified 208, 24,584 bytes, 55.5 % of §0k's 44,262;
`make test` 4130** (4019 before the batch; the tier's battery `test/test_behavior.py` carries all
of the growth).

| address | name | bytes | what it is |
| --- | --- | --- | --- |
| `$2462` | `actor_behavior_type02` | 254 | faces the player and never steps while alive — only falls |
| `$25c0` | `actor_behavior_type03` | 374 | patrols, turning two ways: a $46-frame countdown and the ground |
| `$2796` | `actor_behavior_type04` | 342 | hovers on a 64-word signed delta table; chases only inside $c8 |
| `$29ec` | `actor_behavior_type05` | 262 | hops when the ground says to |
| `$2bc8` | `actor_behavior_type06` | 490 | charges, then THROWS a type-$28 shot from the high pool |
| `$7060` | `actor_behavior_type07` | 424 | THREE table rows share it; two mark bits of 30(a0) say which fired |
| `$72c2` | `actor_swoop_state0_acquire` | 102 | three gates, then one of five canned dive paths |
| `$7328` | `actor_swoop_state1_run_path` | 62 | one dx,dy pair a frame until the path's sentinel |
| `$7366` | `actor_swoop_state2_home_x` | 56 | 4 px/frame onto the followed x; the no-op `bchg` pair |
| `$739e` | `actor_swoop_state3_descend` | 48 | 2 px along and 2 up until the launch y comes back |
| `$5928` | `actor_behavior_type47` | 42 | pure animation: no callee at all; the CURSOR wrapping frees the slot |
| `$5972` | `actor_behavior_type48` | 86 | settle + ascent + `$2f22` inline, then slot 50's countdown tail |
| `$59d0` | `actor_behavior_type49` | 108 | the same walk, then TWO tables over ONE cursor keyed on 31(a0) |
| `$5a6e` | `actor_behavior_type50` | 64 | drifts 8 px/frame, frees its own slot on a countdown |
| `$5ab2` | `actor_behavior_type51` | 138 | walks until stopped; bit 0 of 9(a0) is a one-way switch |
| `$6e1c` | `actor_behavior_type54` | 112 | the VERTICAL moving platform |
| `$6ef4` | `actor_behavior_type55` | 74 | the HORIZONTAL one — no rts at all, three bra.w into 54's tail |
| `$6f3e` | `actor_behavior_type56` | 64 | the SINKING one — no direction bit, no limit |
| `$6796` | `actor_stun_followed` | 44 | SFX 8 + a stun count into the followed record |
| `$6e8c` | `actor_platform_release_blocked_rider` | 76 | backs a rider out of a solid cell, ends the ride |

**THE REGISTER THE SETTLE HAD TO HAND BACK.** Slots 3 and 6 write their step with `move.b #$2,d7`
— the LOW BYTE alone, over whatever `actor_fall_and_settle` left in d7. On the early exits that is
`$5c6e`'s followed-sprite id, so the left arm steps `(sprite & $ff00) | 2` — 258 px for a $1xx
sprite — while the right arm's `move.w` always steps 2. A byte write over a stale register TURNS
THAT REGISTER INTO AN INPUT: three C signatures moved so the settle chain hands d7 back, a
previously unpinned register is now pinned, and the class is in docs/m68k-disassembly.md as the
sixth silently-changing semantic (the second register-width lesson after the 24-bit bus).

**The five $2462-band slots are ONE GRAMMAR**: the spawn-anim gate, the contact test (an enum —
the `bsr $23b6` shot hit SHORT-CIRCUITS `$5c6e`), the hit animation, the frame cursor and the
defeat check are five shared helpers, not fifty copies. The prologue's plates were REPLACED, not
stacked — the review caught four deepenings added above their stale predecessors, which
ApplyNames' last-wins rule would have silently discarded on the next reapply, plus $6ed8 carrying
two var names at once. THE HABIT-CHECK IS NOW A RULE: one directive per address (three deliberate
later-wins corrections from earlier batches stand, marked as such).

**Plate corrections, cited to bytes**: $6796 is a stun, not "a facing update", extent 44 not to
$67c2; $6e8c writes three things and probes collision_map_default UNCONDITIONALLY with `lsr.w` not
`asr.w`; slot 54 is 112 bytes (the old figure folded $6e8c in); $6ed8's 8-byte rows are sprite +
THE BAND RECORD $6d70/$6dd8 read; slot 6's throw gate was described BACKWARDS on four surfaces
(the code was right: it launches — clearing bit 2 — holds a standing frame while AIRBORNE, and
throws the frame it LANDS); the $bd66 "only reader" claim is corrected in both carriers ($bd68's
reader is $6796); slot 50's `lea $5aae.l` is dead; slot 2 reads $9aec ABSOLUTE where slot 3 goes
through $a098 — three spellings of the followed record now stated side by side.

**SWEEP: 43 mutants over six pre-hoc axes, 41 caught, two EQUIVALENT** (named in the battery:
slot 6's clr-vs-subq and slot 56's release pair — neither reads what the other writes). The sweep
first found TEN real holes, all closed; the review then found the a32-map asymmetry pin was
seeding a cell the probe never reads — WORSE than vacuous, untestable — and it now fails under
the map-selecting mutant it is named for. The death-wrap, defeat-transfer and struck arms are
driven for all five band slots (16 cases; the defeat's writes composed from test_actor.py's own
models); of the review's four named mutants three are caught and **always-store-the-cursor is
UNPINNABLE** — the skipped store would write the wrap's own zero and actor_defeat_and_score
writes FIELD_18 = 0 itself — recorded as knowingly not pinned with that reason.

**TWO MORE WAYS A SWEEP LIES** (the README's list now counts FIVE, its frame sentence fixed): an
UNBUILDABLE mutant reads as caught unless make's returncode is checked; and a KILLED sweep keeps
writing — the wrapper's child survives a pkill and its next restore overwrites your edits. Both
measured here (one false 42/43 on an unbuildable tree; the batch also re-verified batch 29's
gotcha by hitting it — sources are now verified pristine after EVERY sweep, aborted or not).

**Not pinned, honestly**: which creature each slot draws (still typeNN); the skipped cursor store
at the defeat frame (equivalent, above); the registers handlers leave behind; slot 3/6's left
step for a NEGATIVE settle span and slot 3's tile-33 early exit (no game data reaches either);
the refused dispatch.

**QUEUED**: batch 31 = slots 60/61/59/8 ($6f7e/$6f9e/$7044/$705a — 226 bytes, the cheapest four
rows) + slots 52/53 ($5b3c/$5be4, slot 51's neighbours, reusing the now-green stun); the
third-copy encoders for leaf.py (two more found by the verified scan: adda_l_dn, mulu_w_dn);
bus.h (now with write guards + bus_write_long) → kit promotion; the three deliberate later-wins
cmt pairs would read better merged; 50 slots remain.

### Batch 31: six more rows — and the boundary moves INSIDE the handler

Six dispatch rows plus one 12-byte gate, ~476 bytes. Three rows flipped CLEAN, three BOUNDED —
and the boundaries are the finding: this is the first batch where a handler's port stops at an
edge INSIDE its own body rather than at a callee. **Verified 215, 25,060 bytes, 56.6 % of §0k's
44,262; `make test` 4200** (4130 before; `test/test_behavior.py` stands at 605).

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$5b3c` | `actor_behavior_type52` | 152 | CLEAN — slot 51's grammar, third ending: frees itself the frame it LANDS |
| `$5be4` | `actor_behavior_type53` | 136 | BOUNDED at $e06 (through `$d78`'s gate while tile_33_mode is clear) |
| `$6f7e` | `actor_behavior_type60` | 30 | CLEAN — watches $6f9c and RETYPES ITSELF into slot 54 (`move.w #$36,4(a0)`) |
| `$6f9e` | `actor_behavior_type61` | 118 | BOUNDED at $e494 — not a creature: the COPYLOCK FAILURE MESSENGER |
| `$7044` | `actor_behavior_type59` | 22 | BOUNDED at $7060 — a prologue: `bset #2,30(a0)` + a template write, then bra.w |
| `$705a` | `actor_behavior_type08` | 6 | BOUNDED at $7060 — ONE instruction, runs INTO the shared body |
| `$d78` | `player_gate_on_1516` | 12 | ported; `# ctx` dropped, TWO callers (the plate said one) |

**Slot 60 closes batch 29's open question**: the `$36` it writes into offset 4 is WB_ACTOR_TYPE —
the record comes back next frame AS the vertical moving platform, pinned against the image's own
table. **Slot 61 is not a creature at all**: it plays song $e, posts the game's four HIGHEST
message ids ($72..$75) one per FIRE edge, and on the terminator resets a7 to $80000 and jumps to
show_data_disk_prompt — a restart. Its plate said "reached ONLY through the dispatcher"; the
bytes say otherwise: `4eb8 6f9e` = `jsr $6f9e.w` at $f56e, the Copylock failure path, a SHORT
absolute form a longword scan misses (the seventh way an operand hides, noted in the plate).
**Slots 59 and 8 are two prologues into `$7060`** — bits 1 and 2 of 30(a0) are how one shared
body knows which of its three entries fired; porting slot 7 retires both boundaries at once.

**Slot 52's step is the d7 class AGAIN, one field over**: `moveq #0,d7 / move.b 30(a0),d7` — the
byte the damage arm stamps $ff into is what a live record WALKS BY. And slot 53's boundary is a
new shape, stated honestly: the original `bsr`s into $d78 and — while tile_33_mode is clear —
branches into $e06 and RESUMES at $5c32; the port stops where the original would have continued.

**Plate corrections, cited to bytes**: both $5a-band extents ran two bytes long (the "code" was
each slot's own frame table / live word — two new vars, actor_type53_alive with THREE operand
sites); the $6f9e only-dispatched claim above; $d78's caller count.

**SWEEP: 41 mutants over six pre-hoc axes, 40 caught, one EQUIVALENT** (slot 52's two free-writes
reordered — independent addresses under an address-keyed ledger, named in the battery). Two real
holes closed the pre-hoc way (a clr.b over an already-zero byte; the settle/ascent exclusivity
needing the hop's LAST frame). **A SIXTH way a sweep lies**, measured: a PYTHONPATH holding a
`dis.py` makes pytest itself unimportable — the step-0 green check is what catches it.

**THE REVIEW GATE (high, six angles) found a real divergence**: slot 61 RE-READS 31(a0) after its
`addq.b` where the C held a local — the two diverge exactly when the bus write is dropped, now
mutation-pinned (index/type61-cursor-reread). Ten more findings applied, including the write band
widened globally, _run_handler now checking the handler's answer, and slot 51's contact arms
folded into the shared helper.

**Not pinned, honestly**: which creature each slot draws; the registers left across boundaries
(slot 59's a1, slot 61's a7 := $80000); slot 53's resume-past-the-boundary (the port's limit,
above); an ODD slot-52 frame cursor is an address error on real hardware the oracle cannot see;
the equivalent reorder; the refused dispatch.

**QUEUED**: batch 32 = slots 47/48/49 ($5928/$5972/$59d0, the last of the $5a band, self-contained)
then SLOT 7 ($7060, 424 B) — which retires this batch's two prologue boundaries and answers what
bits 1/2 of 30(a0) select; the NINE third-copy encoders now due in leaf.py; bus.h → kit; the three
later-wins cmt pairs. 43 slots remain.

### Batch 32 phase 1: the $5a band closes — three endings of one grammar

Three dispatch rows, 236 bytes, all three CLEAN — every callee was already green, so nothing here
is bounded. **Verified 218, 25,296 bytes, 57.1 % of §0k's 44,262; `make test` 4247** (4200 before;
`test/test_behavior.py` stands at 652). With slots 50–53 already in, `$5928..$5c6b` — the whole
$5a band, SEVEN dispatch rows plus `actor_advance_anim16` inside it — now runs reconstructed end to
end. 21 of the table's 62 rows are live (41 remain; slots 0 and 58 share one address).

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$5928` | `actor_behavior_type47` | 42 | CLEAN — no callee AT ALL; the cursor wrapping is what frees the slot |
| `$5972` | `actor_behavior_type48` | 86 | CLEAN — the band's walk, then slot 50's countdown tail over four frames |
| `$59d0` | `actor_behavior_type49` | 108 | CLEAN — the same walk, then TWO tables over ONE cursor keyed on 31(a0) |

**THREE ENDINGS OF ONE GRAMMAR, and that is the batch's finding.** All seven $5a-band handlers free
their own slot with `move.w #$ffbe,(a0)`, and what differs is only which flag the `bne` above it
reads. Slot 47 reads the CURSOR STORE's — `move.b d0,18(a0) / bne` — so a type-47 record lives
exactly sixteen frames whatever its countdown byte holds, and never touches 30(a0). Slot 48 reads
`subq.b #1,30(a0)`'s, so its cursor wrap frees nothing. Slot 49 reads the cursor
`actor_advance_anim16` hands BACK in d0, and only on its second table. Each pair is pinned against
the other in the battery (`test_slot48_does_NOT_free_itself_when_its_cursor_wraps` is the control
for slot 47's ending; `test_slot49_phase_two_..._ignores_the_countdown` is the control for 48's).

**Slot 49 is the tier's first TWO-PHASE animation.** 31(a0) is the phase byte, `moveq #0,d0 /
move.b 18(a0),d0` is read ONCE *before* `tst.b 31(a0)` picks the table, so both phases index the
same cursor and a record carries its offset across the change. Phase one plays $5a4e and counts
30(a0) down to `st 31(a0)` — it can never free its slot however long it runs; phase two plays
$5a5e, ignores the countdown entirely, and ends on the wrap. So the record's life is "phase one
until the timer expires, then exactly one pass of phase two".

**`$2f22` INLINE, and a fourth reading of a blocked step.** Slots 48 and 49 open with the same
forty-two bytes — `actor_fall_and_settle`, `actor_hop_ascend_step`, then `actor_step_facing`'s own
body spelt out rather than called. Its `tst.b d0 / bne / bchg #3,8(a0)` is the band's fourth answer
to a blocked step: slot 51 `bset`s a one-way switch, slot 52 discards the answer, slot 3 reaches
`actor_toggle_side_flag`, and these two simply turn round. The `move.w #$3,d7` sits AFTER the
settle, so only d7's low word is replaced — which is the word the probes read (`map.h`), so unlike
slots 3 and 6 the step really is the constant it looks like.

**Plate corrections, cited to bytes.** $59d0's extent ran EIGHTEEN bytes long: it claimed the code
runs to $5a4e, which swallowed `actor_advance_anim16` whole — but `6100002a` at $5a10 and
`6100001a` at $5a20 are `bsr.w`, i.e. CALLS, and $5a3c has its own `rts` at $5a4c, so slot 49 is
bounded at $5a3c and is 108 bytes rather than 126. $5928's and $5972's extents each ran one byte
past the code into their own frame tables (the batch-31 class again). Four new `var` plates:
`actor_type47_frames`, `actor_type48_frames`, `actor_type49_frames_phase1/2`.

**Slot 47 is the smallest live handler in the table** after slot 8's six bytes: no spawn gate, no
contact test, no settle, no map probe, no step, no callee — two writes a frame and an EXACT write
set in the battery, which is what would catch a handler that had borrowed a neighbour's countdown.
It is also the only one in the band whose table is reached absolute-long and then indexed in a
SECOND instruction (`lea $5952.l,a1 / lea 0(a1,d0.w),a1`) rather than by one `lea d8(PC,Dn.w)`.

**SWEEP: 12 mutants over the batch's own axes, 12 caught, none equivalent** — each mask against its
neighbours' ($1f/$f/$7), each table against another's, the step constant, `actor_step_facing`
against `actor_face_and_step_toward` (turn vs. face-first), the settle/ascent ORDER on the hop's
last frame, the phase test, phase one freeing, the cursor read moved after the phase test, and the
countdown's off-by-one. Sources verified pristine against a backup after the sweep, per batch 31.

**Reuse rather than new code**: `actor_advance_anim16` ($5a3c) was already green from batch 29 and
is slot 49's tail unchanged; `actor_step_facing` is slot 48/49's inline ending; slot 50's tail
became the shared `animate_then_free_on_countdown`, so slot 48 adds no tail of its own. In the
battery, `_switched_pokes` is renamed `_band5a_pokes` — the seed is the band's, not the switch's,
and it now serves five slots.

**Not pinned, honestly**: which creature each slot draws (still typeNN); the registers these three
leave behind; the refused dispatch. Nothing in this batch is unreachable by the game's own data —
all three handlers are pure record arithmetic, and every arm is driven.

**QUEUED**: SLOT 7 ($7060, 424 B — retires batch 31's two prologue boundaries and answers what bits
1/2 of 30(a0) select), the pickup tier, the swoop, the player LAST; the nine third-copy encoders
due in leaf.py; bus.h → kit; the three later-wins cmt pairs. 41 slots remain (counted
against the table's 62 rows, which is where batch 31's "43" was one out).

### Batch 32 phase 2: slot 7, the swoop machine — and the tier's LAST boundary retired

Five routines, 692 bytes, all CLEAN — every callee was already green, so nothing here is bounded.
**Verified 223, 25,988 bytes, 58.7 % of §0k's 44,262; `make test` 4344** (4247 after phase 1;
`test/test_behavior.py` stands at 749). 22 of the table's 62 rows are live; 40 remain.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$7060` | `actor_behavior_type07` | 424 | CLEAN — the body THREE table rows share |
| `$72c2` | `actor_swoop_state0_acquire` | 102 | CLEAN — three gates, then one of five canned paths |
| `$7328` | `actor_swoop_state1_run_path` | 62 | CLEAN — one dx,dy pair a frame to the sentinel |
| `$7366` | `actor_swoop_state2_home_x` | 56 | CLEAN — 4 px/frame, and the no-op `bchg` pair |
| `$739e` | `actor_swoop_state3_descend` | 48 | CLEAN — 2 px along, 2 up, back to the launch y |

**THE LAST ALWAYS-TRANSFER HANDLERS ARE GONE.** Batch 31 left slots 59 and 8 holding no `rts` at
all — each raised a bit of WB_ACTOR_FIELD_30 and ran into `$7060`, so what each *reported* was an
address, and the battery carried a checkpoint table (`ALWAYS_TRANSFER`) to drive them. Slot 7 is
reconstructed now, both run straight on, and that machinery is deleted: every ported row answers
WB_ACTOR_DISPATCH_RAN. `UNPORTED_SLOT` moved from 7 to 9 for the same reason it exists.

**AND THE TWO MARK BITS ARE ANSWERED.** Bit 1 (slot 8's) arms a FIVE-SHOT BURST — velocities from
`$7208`/`$721c`, mirrored left/right, one shot every 128 frames — and *also* switches the frame list
to `$74ee`/`$7508`. Bit 2 (slot 59's) arms a single DROPPER every 32 frames, `$20` above the record,
*and* replaces the animation with one of two constant sprites (`$21`/`$24`). Slot 7's own row raises
neither, so it animates and swoops and spawns nothing.

**Corrections to the phase-2 brief, cited to bytes.** The frame-list polarity was inverted in the
task's reading: `btst #3,8(a0) / bne.w $7128` at `$7102` branches when the bit is SET, so `$74a0` is
the SIDE-BIT-SET list and `$74ba` the clear one — "neither/side" had them the other way round. And
the `bsr $1b8e` really is inside the `dbf` (`51c9 ffd0` at `$71a4` targets `$7176`, the `bsr`
itself), so five separate records are taken and a mid-loop failure's `beq.w $7206` leaves the WHOLE
routine, skipping the dropper. The dropper's allocation really does precede its cadence test, so a
full pool leaves 31(a0) unadvanced — pinned as its own case.

**Plate corrections.** `$7060`'s extent ran one byte long (it claimed `$7208`, which is
`actor_type07_burst_left`'s first byte). `$73de` carried TWO `var`+`cmt` pairs — an ApplyNames
last-wins hazard, the class the batch-31 notes registered — now merged into one. Eight new `var`
plates: the path blob, the four live frame lists, the unreferenced fifth, and the two velocity
tables.

**THE FIFTH FRAME LIST AT `$74d4` HAS NO REFERENCE ANYWHERE IN THE IMAGE.** Twelve words ($92/$93)
in exactly the shape of the four around it, bounded only by its neighbours; no `lea`, `movea` or
computed address reaches it, and the cursor's wrap at twelve means no live path could arrive from a
neighbour either. Named `actor_type07_frames_unreferenced` rather than trimmed. (Twenty-four more
words at `$7230`, in the shape of two more such lists for the `$21`/`$24` sprites slot 7 publishes
as *immediates*, are noted in `$721c`'s plate and left for a later batch.)

**Two unbounded dispatches, one refusal apiece.** `jsr` through `actor_swoop_state_table` on 22(a0)
has NO bound — a byte reaches `$7490 + 0..1020` and the longword there is called — so the port
reports the address exactly as `actor_dispatch_behavior` does, and a case enumerates all 256 state
bytes against the C alone. The game's own flow writes only 0..3 (and `$701c` forces a nonzero byte
to 3), so no differential can drive one.

**SWEEP: 39 mutants over pre-hoc axes, 36 caught, 2 EQUIVALENT, 1 real hole closed.** The hole was
`type07/cadence-masks-swapped`: `$1f` is a subset of `$7f`, so every seed the battery had agreed
under both masks — a row at cursor `$1f` now separates them. The two equivalents are named because
no differential can hold them: `swoop/bchg-pair-dropped` (the two `bchg #3,8(a0)` cancel in memory,
so only the entry-byte pin sees them) and `type07/burst-failure-continues` (a burst that failed
means the pool is full, so the dropper's own allocation fails too and the extra call writes
nothing — the `beq.w $7206` target is pinned by the bytes instead). Two patterns collided with slot
6's identical shot-fill lines; one was re-run with unique context and killed, the other
(`shot-flags-not-copied`) is covered by an explicit per-facing assertion. Sources verified pristine
against a backup after every round.

**THE REVIEW GATE (eight finder angles + a verify pass) found THREE real divergences**, all now
fixed and each pinned by a mutant proven red:

  * **The state dispatch's refusal collided with its success value.** `type07_run_state` reported
    the fetched longword, and the span it reaches is ordinary DATA: state byte 65 lands on `$7594`,
    whose longword is `$00000000` — WB_ACTOR_DISPATCH_RAN's own value. A record with that state
    byte therefore ran BOTH spawners and answered "clean" where the original `jsr`s to address 0.
    The RAN/boundary answer is now the return and the address an out-parameter, and the 256-state
    enumeration asserts a refused state writes NOTHING (the seed arms both spawners with their
    cadences met, so a port that ran on is caught by the tables' own bytes). A second case takes the
    premise from the image rather than from this paragraph: some state byte does reach a zero
    longword.
  * **Swoop states 2 and 3 compared a local where the original re-reads memory.** `$7378`/`$7382`
    is `subq/addq.w (a0)` then `cmp.w (a0),d0`, and `$73c0` is `subq.w #2,2(a0)` then
    `cmp.w 2(a0),d0` — batch 31's stale-value class, in the direction that batch did not see. Both
    now re-read through bus.h. The pin is a record at `$fffff0`, whose coordinate stores the shim
    and bus.h both DROP while 24-bit folding puts 22(a0) and 26(a0) at `$6` and `$a` inside the
    image: the original compares against the zero a refused read answers and a port holding a local
    does not, and the state byte that separates them is observable.

**Three more holes in the BATTERY, not the port**, each closed with a case whose mutant is proven:
slot 7's defeat exit was undriven (a dead record could have fired a burst); rows 8 and 59 were only
ever driven with the spawn gate UP, so the mark-bit-then-body ordering never crossed the join under
test; and swoop state 3's "the probe's answer is discarded" claim had no control. Nine more findings
applied: the instruction caps were raised **globally** by 1481 for slot-7-only work and are now
per-handler (and the swoop's are per-STATE — only state 3 takes a map probe, and one, not two); the
`ALWAYS_TRANSFER` tautology test and a stale docstring removed; a fourth copy of the blocked-row
seed extracted (`_block_the_walk`); one word-reading convention across the new block
(`_written_word`); `bump_field_b` and `tick_countdown30` for the four/three sites that spelt them;
the two spawn cadences collapsed into `cadence_reached_zero`; the encoder ledger annotated.

**A REFUTED finding worth recording**: the spawners' cadence re-read is NOT a divergence. bus.h
guards reads and writes with one predicate, so a refused field reads back 0, masks to 0 and stores
nowhere — and `0 & mask` is 0. The computed-local form was adopted anyway because it models the
`andi`'s ALU-flags branch and drops one modelled read; the argument lives in that helper's plate.

**Plate corrections the gate added.** The shared `$5a`-band tail was NOT "identical instruction for
instruction": slot 48 steps its cursor `addi.b`/`andi.b` at `$59ae` and slot 50 the word forms at
`$5a86`, 230 bytes apart, plus slot 50's dead `lea` — the real justification is `step_cursor`'s,
that the two spellings agree for every cursor a record can hold. `type07_fill_shot`'s plate claimed
both spawners write "in the order they make them"; the dropper interleaves `subi.w #$20,2(a1)` after
the copy (`$71d0`), an ordering no address-keyed ledger can separate. `$745e` had no directive at
all and now has one. Header names were drifting from ../names.txt and are renamed to match it
(`..._FRAMES_PHASE1/PHASE2`, `..._FRAMES_UNREFERENCED`).

**Not pinned, honestly**: which creature slot 7 draws; the registers it leaves behind (a1 across the
slot-59 join, which `$7060` does not read); the refused BEHAVIOUR dispatch, and the refused STATE
dispatch's *transfer* — the enumeration pins what the port answers and that it stops, but the
original would call arbitrary data and no differential can drive that; the unreferenced `$74d4` list
and the `$7230` words, which no data can reach; and the two equivalent mutants above.

**Deferred, out of scope for this batch** (found by the gate, deliberately not folded in):
`src/map.c` writes WB_ACTOR_X through a raw `addr_add` with no bus guard — a pre-existing exposure
the state-2/3 pins route around rather than trip; and a `make_image` double-build pattern at five
sites in `test/test_behavior.py` (~0.15 ms).

**QUEUED**: the pickup tier ($38) and the player row ($1, the largest subtree behind the table); the
`$7230` words; the encoders due in leaf.py — now TWELVE, batch 32's `move_w_d16_d16`,
`movea_l_indexed` and `subi_w_d16` having become third copies, with `movea_l_indexed` the first to
promote because the other two batteries that spell it hand-roll `index << 12` where this one calls
`brief_extension_word`; bus.h → kit; the three remaining later-wins cmt pairs
($1023a, $10394, $1044c). 40 slots remain.


### Batch 33 phase A: dispatch rows 28, 30 and 31, and the payout cluster at $517a..$5207

**SIX ROUTINES, 506 BYTES, ALL CLEAN.** **Verified 231, 26,512 bytes, 59.9 % of §0k's 44,262;
`make test` 4466** (4359 after this batch's two prerequisites, 4451 at the end of phase A, 4466
after phase B below closes the batch; `test/test_behavior.py` stands at 852). 26 of the table's 62
rows are live and 36 remain — a figure `PORTED_SLOT_COUNT` now holds and
a case asserts, because it had drifted twice as prose. Every callee these six reach was already
reconstructed, so not one of them needed a boundary — the first batch in this tier where that is
true of the whole set.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$6786` | `sound_request_9` | 16 | CLEAN — the band's collect sound (prerequisite) |
| `$4ec8` | `actor_behavior_type29` | 2 | CLEAN — a bare `rts`, mapped to the null body (prerequisite) |
| `$51d8` | `text_write_gold_digits_a2ac` | 48 | CLEAN — two characters, leading zero blanked |
| `$51ac` | `bcd_add_random_1_to_4` | 44 | CLEAN — the game's SECOND declared-hardware routine |
| `$517a` | `hud_award_gold_from_descriptor` | 50 | CLEAN — the payout, and what named the counter |
| `$4e38` | `actor_behavior_type28` | 144 | CLEAN — the walking collectable, and the WORD step test |
| `$4eca` | `actor_behavior_type30` | 142 | CLEAN — the hoverer, its global cursor and the meter bug |
| `$4f9c` | `actor_behavior_type31` | 78 | CLEAN — 78 bytes, not 146: two exits, one of them a branch |

**WHAT A COLLECTABLE IS.** These three rows are not creatures. None has a spawn gate, none calls
`actor_hit_by_player_shot`, and the only contact test is `bsr $5c6e / btst #1,d0` — the FOOTPRINT
bit alone — so the followed record takes one by standing on it and a shot cannot touch it at all.
Each fires `sound_request_9`, pays, and writes `actor_free_marker` over its own x; each runs
`WB_ACTOR_FIELD_12` down and raises `WB_ACTOR_FLAG_FLICKER_BIT` on the way, so an uncollected one
blinks out. Slot 28 falls, hops and walks; slot 30 hovers on a signed table; slot 31 only falls.

**THE COUNTER AT $bd6e IS THE GOLD, and this batch is what established it** — three witnesses that
do not depend on one another. Message id 3's shipped string is `"        gold get."`; the two
characters `$51d8` patches into it (`$a2ac..$a2ad`, five spaces in) are the amount `$517a` adds to
`bcd_counter_bd6e`; and `scene_run_frame`'s shop arm compares its price against that same counter
and calls `bcd_sub_counter_bd6e`. The message-table read is a CASE and not a claim —
`test_the_gold_digits_land_inside_message_3s_own_shipped_string` takes the record's address off the
image's own pointer table and asserts the two bytes ship as spaces.

**THE BIGGEST FIND: `$51ac` ENDS IN AN `abcd`, NOT AN `and`.** The `# ctx` plate called it
`rng_1_to_4_masked` and said it masked the caller's d0; `out/wonderboy_dis.txt` prints the `c101` at
`$51d4` as `and.b d0,d1`. It is `abcd d1,d0`. Opmode 100 over an ea mode of 000 cannot be an AND (a
byte AND with a register destination would have to write a data register through the `<ea>` half),
and Ghidra's own decompile calls it `bcdAdjust`. This is the SAME disassembler bug `names.txt`
already documents for `$b562`'s `c308`/`8308` — **the ABCD/SBCD/EXG encoding space at `$c1xx`/`$81xx`
is systematically mis-printed in `out/wonderboy_dis.txt`, and any plate written from that listing in
that space is suspect.** So the routine adds a packed-BCD one-to-four INTO d0 and answers in d0, and
`$517a`'s award is JITTERED rather than masked. `bcd_add_random_1_to_4` is the new name; the entry
pin (13 instructions, 44 bytes) passed first try, which is the independent confirmation.

**...AND THE ROOT CAUSE IS FIXED, not just the plate.** `tools/prg_dis.py` had `ABCD`/`SBCD` on a
"knowingly unhandled, mnemonic-only" list that `docs/m68k-disassembly.md` had carried since
2026-07-28, and `../names.txt` warned about the very same encoding at `$b562` — and a plate was
written from the listing anyway. **A documented gap is not a guard.** The decoder now carries the
two table rows beside its `EXG_FORMS` (opmode 100 with ea mode 000/001 in lines 8 and C); the kit's
own opcode-space sweep flagged the two `KNOWN_MNEMONIC_GAPS` rows as stale the moment it did, which
is that test working as designed; and four reference encodings pin the forms including the operand
order (`c101` is `abcd d1,d0`, NOT `abcd d0,d1`). Kit suite 351, unchanged. This is the one change
in the batch outside `projects/wonderboy/`, and it is what stops slots 32 and 33 — queued, and in
the same band — repeating the mistake.

**A SECOND SCAN ERROR, and this one contradicted the tree's own data.** The reconnaissance recorded
slot 31 as `$4f9c..$5019`, 146 bytes, "three sprite arms sharing the `$5018` exit". Forty-eight of
those bytes are `actor_select_sprite_by_flag` — named in `../names.txt` since batch 28, ported in
`src/behavior.c` and entry-pinned in `test/test_behavior.py` since batch 29, with a `bsr.w` caller of
its own at `$54d6` inside `actor_behavior_type38_pickup`. Slot 31 is **78 bytes**, `$4f9c..$4fe9`,
and its last instruction is a `bne.w $4fea` INTO that routine, whose `rts` returns to the dispatcher.
The lesson is a cheap one to apply: **before recording a routine's extent from a scan, look up every
address inside it in `../names.txt`** — the answer was already in the tree.

**A SHIPPED BUG REPRODUCED: slot 30's pickup is worth nothing unless the meter is nearly full.**
`move.w $b6fa,d0 / addq.w #4,d0 / cmp.w $b6f8,d0 / blt` computes the topped-up value and stores it
NOWHERE; the only arm that writes is the one where the sum REACHED `hud_meter_max`, and it writes
the maximum rather than the sum. `hud_meter_add_clamped` ($b6fe) is the routine that adds properly
and this handler does not call it. FIVE parametrised rows pin it: four either side of the boundary
(a fifth, an already-full meter, was trimmed as the same claim as the over-full one) and one the
independent gate asked for, seeded at `$7ffe` so `addq.w #4` wraps the value NEGATIVE — because the
compare is `blt`, and every other row is small and positive, so an unsigned port answered them all
correctly. Three mutants are caught: "store the sum", "always store", and dropping both `(int16_t)`
casts, which the gate had already shown left the whole suite green.

**THE WORD TEST AT $4e98 IS PINNED, and both of its arms are reachable.** Slot 28 is the one place
in the tier that reads the step probe's whole low WORD (`tst.w d0`) where every other blocked-step
test reads the outcome BYTE. The probes leave a map column — or a clamp limit, or a parked x — above
that byte (map.h), so the `bchg` turns the record round only when both bytes are zero. Two cases:
a step blocked in map column 0 reports `$0000` and DOES turn it round; a step past the level's right
edge reports the clamp (`$0100` for the limit those seeds use) and does NOT, even though its byte is
`WB_ACTOR_STEP_BLOCKED`. The mutant that swaps `step_word_was_blocked_at_column_0` for
`step_was_blocked` is caught
by the second. Both arms come off the game's own geometry, so nothing here is unpinned.

**Other findings worth carrying.** Slot 30's animation cursor is a GLOBAL (`$4f5a`), the only one in
the tier that is not a record field — two live type-30 records share one phase, and a case runs the
handler on two records in turn to show the second starts where the first left off. Its drift table
(`$4f5c`, 32 signed words) is a triangle that sums to ZERO, which is what makes the handler a hover
rather than a drift; the table is reached by the one `lea $4f5c(pc,d0.w)` in the image, the
operand form §0k is about. `tst.b $712.w` reads `frame_toggle`'s HIGH byte, and two rows with only
a low byte set are what say so. And `$10424` is `record_ptr_10420`'s copy, so field 12 of the SCENE
DESCRIPTOR at `$21828` is the gold award — a field that table's plate did not list.

**THE REVIEW GATE (six finder angles) FOUND THIRTEEN REAL ITEMS**, all applied. The three that
matter most, each a claim the tree itself contradicted: (a) **slot 31 DOES end in an `rts` of its
own**, at `$4fe8` — four surfaces said it did not, and that reading is self-contradicting, since a
body ending at the `bne.w $4fda` would be 66 bytes and not the 78 `BODY_SIZES` records. The truth is
two exits: the collect and free arms reach `$4fe8`, and the LIVE-countdown arm leaves by the
`bne.w $4fea`. (b) **`behavior.h` claimed all three collectables `bclr` the flicker bit when they
free themselves** — slot 28 `bset`s it and frees the slot with it UP, which the source comment said
and the header denied, in one commit. (c) **slot 28's LEFT walk arm was never driven**, so a port
reaching for `step_right` outright stayed green; the first attempt to fix it did not separate the
arms either (both probes land in column 0 on a fully blocked row), and the case that works is the
off-the-map park, where the arms leave DIFFERENT x. `arm/type28-always-steps-right` is the mutant
that now proves it. Also applied: two dead constants deleted, an unused parameter dropped, the
collectable seed made to DELEGATE to the band's rather than restate fourteen of its lines, three
encoders annotated `ALSO IN` under the file's own third-copy rule, a helper renamed off a bare `0`
onto `WB_ACTOR_STEP_BLOCKED`, the direction-select extracted so three routines share it, the
instruction cap derived (it was 116 over a 52-instruction run) and a `names.txt` plate un-spliced
where a new clause had captured the previous field's parenthetical.

**Mutation sweep: 34/34 caught** on the reviewed code, then **three more axes the independent gate
found by mutating the tree itself** — both `(int16_t)` casts dropped from `type30_top_up_the_meter`
(4447 green, item 2 above), the flicker `==` widened to `<=` (exactly ONE failure, and it was a
slot-30 row: slot 31's own `cmpi.w` was pinned only through its neighbour's copy), and slot 28's
`step_facing` hard-wired to one arm. All three now red, and the flicker mutant reds at BOTH sites.
The first pass ran 30 and its two survivors are the two battery holes below.
Over pre-hoc axes (masks against neighbours, the drift table
swapped for the cursor, the word-vs-byte step test, the global cursor made a record field, a dropped
hardware read, the two hardware reads swapped, the `abcd` made a binary add, the shipped meter bug
"fixed" two ways, the signed collect-min compare made unsigned, the frame-toggle byte, the flicker
equality made a threshold, `bset`-then-read reordered, the step field moved, the two award arms
swapped, slot 31's sprite published on both arms). **The first pass found TWO real holes in the
BATTERY**, each now closed and each proven under its own mutant: no drift case drove a cursor with
its SIGN bit set, so `sign_ext16` could be dropped unnoticed (the rows at `$fffe` — which reads the
cursor word itself, two bytes below the table — and `$8000`, which leaves the image, close it); and
no countdown case sat strictly BELOW the flicker mark on an arm that does not clear the bit again,
so `==` and `<=` were indistinguishable. Sources verified pristine against the snapshot before every
mutant and after the run.

**A FALSE GREEN THE REVIEW GATE CAUGHT IN THE BATTERY ITSELF.** The two negative controls asserted
the kit's undeclared-hardware refusal with `pytest.raises(AssertionError, match="(?i)declar|hw|refus")`
— and each passed its case name to `leaf.run` as the `what`, which the run's OTHER assertions put at
the head of their own message. `"...undeclared"` matches `declar`. So a change that removed the
refusal would have fallen through to the byte-for-byte diff, failed on the fabricated 0, and been
reported as the refusal firing. Both halves are fixed and both are load-bearing: the pattern is now
`"modeled hardware byte"`, a phrase only `harness.py` produces, and the `what` those two cases pass
carries no word that could stand in for it.

**...and what those two controls DO and DO NOT pin, measured rather than assumed.** The refusal is
raised by the ORACLE's read, not the candidate's, so NO mutation of `src/behavior.c` can redden
either control — a mutant that deleted `bcd_add_random_1_to_4`'s two `hw_read8` calls outright
leaves both green, which was run and recorded rather than reasoned about. They pin the KIT's model.
What pins the PORT's own reads is the ordered read-stream comparison, and two mutants prove it:
`hw/type51ac-drops-the-mid-counter` and `order/type51ac-hw-reads-swapped` are both caught by the
DECLARED cases.

**NOT PINNED, HONESTLY.** (The BCD extend chain was here too, as a KNOWN DIVERGENCE; phase B
below FIXED it and this bullet moved with it.)
  * **SLOT 31's `cmpi`/`bset` ORDERING.** It runs the flicker mark BEFORE its contact test where
    slot 30 runs it after the drift, and no case can separate the two: a collected frame ends at
    `bclr #6,8(a0)`, so the flag byte it writes has the bit down whether the `bset` ran first or
    not, and a waiting frame reaches both orders alike. They converge on every arm.
  * **SLOT 28's TWO WALK ARMS on a fully blocked row.** `_block_the_walk` fills the whole probe row
    and from the seed those cases use BOTH probes land in map column 0, so the two arms report the
    same `$0000` and commit the same zero move. What separates them is the off-the-map case, where
    the left arm parks at the half-width and the right would commit `x + d7` — a distinction the
    review gate had to add, and `arm/type28-always-steps-right` is the mutant that proves it.
  * The `#$14` at `$4eba` and the `#$14` at `$4f2e`/`$4fa4` are the same number in two different
    operands (a byte written, a word compared) and carry two `#define`s. Nothing says they are the
    same design constant.
  * Which creature each of the three slots draws, and what `WB_ACTOR_FIELD_12`'s two spellings mean
    beyond "a countdown".
  * `$515c`/`$515d`/`$515e`, slot 32's three globals, are NAMED in `../names.txt` (they were read
    while the frame table above them was) but not ported — batch 34's. *(DONE, and the `$515e`
    plate's look-ahead claim was WRONG: see the batch-34 section.)*

**QUEUED — and BATCH 34 owns slots 32..37**, which is what the `$515c`/`$515d`/`$515e` plates in
`../names.txt` already say; this line said "the rest of batch 33" and the two disagreed. **BATCH 33
IS CLOSED**: the one item left of it was the BCD extend chain, and phase B below carries it.
*(Batch 34 DID those six and CLOSED the band; its own section is at the end of this file, and it
corrected the `$515e` plate this section's reconnaissance rested on.)*

**QUEUED — REGENERATE THE GHIDRA ARTIFACTS BEFORE THE NEXT NAMING PASS.** `../out/names_dump.txt`,
`../out/hw_scan.tsv` and `../decomp.c` are gitignored generated files and all three still carry the
three OLD names at `$517a`/`$51ac`/`$51d8`. The documented GUI-sync workflow is "run `dump_names.sh`,
diff against `names.txt`, merge" — run that against the stale dump and the corrected names read as
apparent GUI edits and get merged BACK, and `ApplyNames` is last-wins per address, so the batch's
central correction would be silently undone. It would surface as ~90 collection-time failures inside
`leaf.entry_of`, pointing at a missing name rather than at the merge. Run `../reapply.sh` and
re-dump first. `../out/wonderboy_dis.txt` also predates the decoder fix above, so its `$8xxx`/`$cxxx`
lines are still the wrong ones — regenerate it before reading any plate out of that band.

**QUEUED — `abcd_byte` to the kit.** `src/hud.c` un-`static`'d it so `bcd_add_random_1_to_4` could
execute the same decimal correction rather than a second spelling of it. Its proper home is
`tools/recreate_kit/include/machine.h`, beside `sign_ext16` and the `set_low_byte` its one outside
caller composes it with — registered here rather than done, which is the rule `bus.h` already
follows. And note what the export did NOT do: it shares one INSTRUCTION, and phase B's extend chain
is untouched by it.

**What the reconnaissance established about the six rows STILL to do** (read from
`out/wonderboy_dis.txt`, none ported — and read against `../names.txt` before it is trusted, which
is the lesson above):

  * **Slot 32 `$5046..$515b`, 278 B**, with THREE globals of its own immediately after it —
    `actor_type32_state` and `actor_type32_done` bytes and `actor_type32_cursor` a word — and it
    indexes `actor_anim_5160_frames` at `$5160` with that cursor and its own `cmpi.w #$ffff,2(a1)`
    sentinel look-ahead, which is a SECOND reader of a table `actor_relaunch_and_anim_5160` already
    owns and reads the terminator one word EARLIER than that routine does. It reaches
    `hud_award_gold_from_descriptor` at `$5070`, so it inherits the declaration and the extend chain.
    *(TWO CLAIMS IN THIS BULLET ARE WRONG, corrected in the batch-34 section at the end: the two
    readers look ahead at the SAME word — `$6872`'s publish is a POST-INCREMENT — and the table has
    THREE readers, the third being the unported `actor_behavior_type46` at `$58f8`. The two latch
    globals are now named `actor_type32_walking` and `actor_type32_hops_spent`.)*
  * **Slot 33 `$5208..$5259`**: contact, `sound_request_9`, `$ffff` into `$bd30` and `$bd26`,
    `$b5a2` with `$20`, and the same flicker/countdown tail slots 30 and 31 share.
  * Slots 34..37 are unread. *(Batch 34 read them: 34 is the shop's item cursor and 35..37 are the
    event actors — and slot 35 is 38 bytes, not the $5336..$53bb the scan gave it.)*

### Batch 33 phase B: the BCD extend chain, and what CLOSES batch 33

**ONE INTERFACE CHANGE, EIGHT CALL SITES, THREE OF THEM THREADED.** No new function is verified —
the count stays **231 / 26,512 B / 59.9 %** — and the suite moves **4451 → 4466**. What changed is
the faithfulness of code already counted: the four packed-BCD accumulators at `$b562`/`$b582`/
`$b5a2`/`$b5c6` no longer fold in a hard-wired zero.

**THE INDEPENDENT GATE FOUND A REAL DIVERGENCE IN THE FIRST CUT OF THIS SECTION, and it is the one
worth reading first.** `$6c26` was written up as "CLEAR, because every shipped spawn type has bit 14
clear". Both halves were wrong. The bit is produced by `lsl.w #2,d2` INSIDE
`actor_defeat_and_score`, so it is not the harness's entry CCR at all and an ordinary row can drive
it; and the shipped-types reading was uncheckable, because the template table has NO shipped bytes
(`wonderboy.h`, WB_SPAWN_TYPE: it is loaded from disk). The battery was meanwhile REFUSING a bit-14
seed while happily seeding fabricated `$8000`/`$2000`/`$bfff` types — excluding exactly the value
that would have shown the bug. Seeded, it is red: `bcd_score_bd70+3 ($bd73): oracle=0x01
cand=0x00`. The refusal and the guard test built on it are gone, `$6c26` threads the bit, and
`SCORE_EXTEND_TYPES` drives both answers as normal differential rows.

**THE SHAPE, and why it is an entry PARAMETER and an exit RETURN rather than `abcd_byte`'s
`unsigned *extend`.** Three readings decided it. (1) The exit bit has to be *observable* by a case:
the glue factory `leaf.register_glue` hands back the C's return value as `info["ret"]`, and an
out-parameter cannot travel that way — a pointer shape would have made the exit X invisible to the
harness at every one of the four. (2) At the five sites that do NOT chain, an entry parameter stays
a single expression carrying its own justification, where a pointer would force a mutable local at
each and make "ignored the output" and "threaded the output" look alike in review. (3) `abcd_byte`'s
pointer is right for what it is — a per-byte primitive called in a loop that needs a running
variable — and these are whole routines whose X is an argument and a result. `bcd_add_random_1_to_4`
is the exception: it already returns d0, so its carry-out goes through `unsigned *exit_extend`, and
it takes no entry parameter because `addq.b #1,d1` on a byte masked to `0..3` always clears X.

**THE EXIT BIT IS THE CARRY OUT OF THE TOP BYTE**, read off the bytes: the walk is
`abcd -(a0),-(a1)` from `$bd7a`/`$bd70` downward, so the LAST pair writes `$bd6e` (or `$bd70`), the
most significant byte — and `movem.l (a7)+,#$0300` and `rts` leave the CCR alone, so that carry is
still in X at the call site.

**EIGHT CALL SITES, EACH WITH ITS OWN READING.** The audit is `grep WB_BCD_ENTRY_EXTEND` (BOTH
constants) and it returns **FOUR** — three PROVED-clear plus one ASSUMED-clear. The three THREADED
sites carry no marker by construction, and are listed here by name instead. (`$5184` is in the table
because it is part of a chain, but it is the DRAW and not an accumulator site, so it claims nothing.)

| site | routine | entry X | why |
| --- | --- | --- | --- |
| `$4e5a` slot 28 | counter | CLEAR (proved) | the sound trigger's; not readable off these bytes, PINNED by the differential — `$0100 + 5` is `$0105` with X clear and `$0106` with it set |
| `$4e64` slot 28 | score | **threaded** | the counter's carry-out; `move.l #$20,d0` does not touch X |
| `$5184` payout | *the draw, not an accumulator* | — | its own `addq.b #1` clears X; it is here as the SOURCE of the next row's bit |
| `$5188` payout | counter | **threaded** | the draw's `abcd d1,d0` is the instruction before the `bsr` |
| `$5196` payout | score | CLEAR (proved) | `text_write_gold_digits_a2ac` runs between, and its last X-writer on BOTH exits is `addi.b #$30` on a nibble masked to `$0..$f` |
| `$6c26` defeat | score | **threaded** | the bit `lsl.w #2,d2` pushed out of the spawn type at `$6c20`, produced INSIDE this routine — `SCORE_EXTEND_TYPES` drives it both ways |
| `$e130` bonus | score | CLEAR (proved) | the banner walk's last X-writer is `lsl.w #5,d0` over a register the `moveq #0 / move.b / subi.b` above hold to `$0000..$00ff`, so five shifts cannot carry a 1 out of the word |
| `$ddae`/`$de24` shop | counter (sub) | **ASSUMED clear** | see the OPEN ROW below — it is the one site claiming a bit it cannot read off its own bytes, and it spells its own constant so a grep tells the two apart |

**OPEN ROW — THE SHOP'S ASSUMED-CLEAR ENTRY X (`$ddae`/`$de24`, src/scene.c).** Nothing on the path
from `scene_run_frame`'s entry to either `jsr $b582.l` writes X: `tst`, `cmpi`, `clr`, `move`,
`movea` and the branches leave it alone, and the one call on that path — `jsr $682.w`,
`joy1_newly_pressed`, four instructions (`move.b $8b3.l,d0 / move.b $8cf.l,d1 / eor.b d1,d0 /
and.b d1,d0`) — does not touch it either. So the bit is the CALLER's, and the caller was READ rather
than left unknown: `$dbc0` has exactly one caller, `jsr $dbc0.l` at `$4be`, whose preceding
instruction is `jsr $b346.l`; `panel_refresh_frame`'s last act before its `rts` is `bsr $b372`, and
`select_table_21e8c_and_tick_b39a`'s last instruction before ITS `rts` is `addq.w #1,frame_tick_b39a`
at `$b392` (both single-caller, verified by an absolute-operand and `bsr` scan). An `addq.w` sets X
on the wrap — so the assumption is exactly quantified rather than open-ended: **it holds on 65,535
frames out of 65,536 and fails on the frame the tick rolls `$ffff` → `$0000`, on which a purchase
spends one extra unit of gold.** No case can drive that frame, because every run is entered with the
CCR forced clear. Closing it needs an entry-CCR parameter on `emu.run` (kit work), not a seed.

**RED THEN GREEN, which is better than a mutant because the divergence was proven live.** The two
chain cases were written first and both went red against the unfixed C, each off by exactly one in
exactly the byte the reading predicted: slot 28 with the counter at `$9996` gave
`bcd_score_bd70+3 ($bd73): oracle=0x21 cand=0x20`, and the payout with an award of `$0096` (draw 4,
so the award's own `abcd` carries) gave `bcd_counter_bd6e+1 ($bd6f): oracle=0x01 cand=0x00`. The fix
turned both green and moved nothing else.

**MUTATION SWEEP: 16 of 16 after the gate's items landed** (the first pass was 11 of 13; the two
`sbcd` survivors are closed above, and three mutants over the newly threaded `$6c26` were added —
drop the threading, and take the bit from bit 15 or bit 13 instead of bit 14). **The sweep also
found a real hole in the battery.**
`exit/add-returns-the-carry-out-of-the-LOWEST-byte` SURVIVED the first pass, because the `$9996`
seed carries out of BOTH bytes (`$96+5` and then `$99+0+1`) and so cannot tell "the accumulator's
carry" from "its first digit pair's". A third row closed it — a counter of `$0096`, where the low
byte carries and the four digits do not, so a port returning the wrong bit scores one unit too many.
Caught: all three drop-the-threading mutants (slot 28's score, the payout's counter, the defeat's
score), the carry threaded to the wrong routine (`chain/award-score-gets-the-draw-carry`), the
defeat's bit taken from bit 15 and from bit 13, the exit bit taken from the wrong byte and replaced
by the entry one on BOTH `abcd` and `sbcd`, the add and the sub each ignoring their entry bit, the
draw never reporting a carry, and all three "this site claims a SET X" mutants — including the
shop's at 59 failures, which is what proves the sub routines read the parameter at all. Sources
verified pristine against the snapshot after the run.

**THE TWO `sbcd` SURVIVORS WERE COVERAGE HOLES, NOT EQUIVALENT MUTANTS — and they are now closed.**
The first cut of this section called `entry/sub-ignores-the-entry-bit` and
`exit/sub-returns-the-carry-out-of-the-LOWEST-byte` equivalent, on the grounds that no ported call
site drives either. That confused "no site exercises it" with "no case can": `bcd_expected` is an
INDEPENDENT decimal statement of packed BCD, and it needs no oracle and no entry SR to say what a
borrow does. `test_hud.py` now runs the reconstruction ALONE (`leaf.run_candidate_only`) over six
rows — borrow IN, borrow OUT, and the low byte borrowing while the accumulator does not — across
both subtract routines, and both mutants are CAUGHT. It is a C-vs-model pin and not an oracle one,
which the cases say plainly: it cannot catch a defect the two statements share. What remains honestly
open is only that **no ported CALL SITE hands a subtract a 1 or reads its borrow-out** — a fact about
the call graph (`bcd_sub_score_bd70` has no reference anywhere in the image and is dead as shipped),
not about the battery.

**WHAT STAYS UNPINNABLE, and after the gate's items it is exactly TWO things: THE KIT CANNOT SET AN
ENTRY CCR.** `emu.run` has no entry-CCR parameter and the shim forces `SR = $2700` after its reset,
so no case can enter one of these four routines — or anything that calls one — with X already set.
Every DIFFERENTIAL case therefore enters with 0, and what pins a set X is a run that PRODUCED it:
the two chains, and `$6c26`'s shift. So what is pinned is "the first pair folds in a 1 correctly
*when the run produced that 1 itself*"; what is not is:
  1. **a run ENTERED with X set.** The shipped site is `$e064`, where `$e058`'s
     `subq.w #1,hud_meter_value` sets X on a meter already at zero and the score add two
     instructions later scores an extra unit. That call site is not ported.
  2. **the shop's ASSUMED-clear entry X**, the open row above — same cause, one frame in 65,536.
Note what is NO LONGER on this list: the `sbcd` half's two directions, which needed no oracle at all
(they are pinned against the decimal model), and `$6c26`, which was never an entry-CCR question.

**`meter_add_expected` was NOT given an extend, and that is a reading rather than an omission**:
`add.w d0,$b6fa` is an ADD and not an `addx`, so nothing folds in; and the X it leaves reaches no
ported BCD call, because the one routine where the meter add and a score add meet
(`actor_defeat_and_score`) puts `lsl.l #5,d0` at `$6c04` and `lsl.w #2,d2` at `$6c20` between them.
`leaf.py` says so at the function.

**QUEUED — `abcd_byte` to the kit — IS STILL QUEUED.** Phase B did not touch it, and the note under
phase A still stands: it shares one INSTRUCTION, and threading the chain neither needed nor helped
that promotion.

### The KIT EXTENSION batch 33 needed (its own changeset)

**THE PHASE 7 TABLE GREW FROM TWO MODELED BYTES TO FOUR** — `OS_HW_SHIFTER_VCOUNT_MID` ($ff8207)
and `OS_HW_SHIFTER_VCOUNT_LOW` ($ff8209), the shifter's video address counter. The model was
entirely table-driven off `include/os.h`, so the change is the table plus the two places that are
deliberately per-slot: `hw.h`'s prose and shim.c's audio-capture profile.

**`HW_CAPTURE_PROFILE_KNOWN` IS DELIBERATELY UNCHANGED**, and shim.c already said why before the
question was asked: the profile is a designated initializer, so a new slot gets a silent 0 in it,
and declaring that 0 would mark a fabrication as a real answer — the monochrome-profile failure the
mode exists to close. Capture semantics do not move: under the mode the two new slots read 0 exactly
as they did when they were unmodeled, and they now land in `g_hw_unseeded` where they are visible.

**A COUNTER IS ADMISSIBLE HERE and the FDC/DMA registers still are not**, which os.h now argues:
what a per-run constant cannot express is a value that must CHANGE BETWEEN TWO READS OF THE SAME
ADDRESS. A routine that reads $ff8207 once and $ff8209 once per call never observes the counter
advancing, so a declared constant describes that call exactly. What it does not describe is a caller
that polls one byte twice and depends on the difference — stated as a non-goal rather than left to
be inferred.

**THE BLAST RADIUS WAS THE POINT.** `rng_next` ($68c6) reads $ff8209, and `include/rng.h`,
`names.txt`'s `cmt 0x68c6` and this file all registered that as a T3-DATA FALSE GREEN: both cores
were served a fabricated 0, the entropy term vanished, and the generator degenerated to a pure
function of three counters. The moment the byte became modeled, 22 cases across four batteries
REFUSED — which is the model working. `src/rng.c` now reads it through `hw_read8`, every case that
reaches the generator declares it, and `test_a_declared_video_counter_reaches_the_result` drives
five different bytes against one seeded state, so the XOR is finally observable as an operator (the
old sweep note that `0 ^ tick` equals `0 + tick` is retired with it). The false green is gone.

**Kit-side cases added**: `vcount_pair_declared`, `vcount_pair_undeclared` and
`vcount_write_then_read` in `hw_model_probe.c` + its Python mirror — served, tallied and stale over
the new slots. Two existing kit cases moved for real reasons rather than to be made to pass: the
capture cases' `known` is the PROFILE PAIR and not "every slot" (a distinction the two-slot table
could not express), and `long_read_straddling_in` now reports TWO slots because a longword spanning
$ff8209..$ff820a really does take both in. `_file_all()` replaces slot-by-slot expectations where a
case declares the whole table, so the next slot lands there automatically.

**...and the DIFFERENTIAL-level pair the probe cases could not reach**, added in the review pass:
the smoke `.PRG` now plants a routine reading `$ff8209` twice and one reading `$fffa01` twice, and
`test_hw_differential.py` pins the first REFUSED and the second SERVED (19 cases, was 17). The
volatile one is measured rather than asserted — its candidate reads the byte twice too, so with
`harness`'s volatile branch disabled every surface agrees and the case reds with DID NOT RAISE,
which names the false green exactly. `make test` under audio capture is deliberately unaffected: the
capture profile still declares only `$fffa01`/`$ff820a`, so the new slots read a fabricated 0 there
and a capture run is not a differential.

**Tri-project verification, all from clean and run SERIALLY** (see the queued rule below — the three
projects share one `liboracle.so`): kit 351, `tools/test_hw_portability.py` 56, Wonder Boy 4359,
Joust 4369, BuggyBoy 292.

**ALL FOUR OF THIS SUBSECTION'S OWN QUEUE ARE DONE** in phase A above: slots 28, 30 and 31 and the
whole helper cluster are ported, every case that reaches `$51ac` declares the counter pair,
`step_word_was_blocked_at_column_0` is the WORD variant slot 28 needed, slot 30's global cursor has
a `var` and
a `cmt` of its own. Slots 32..37 remain, and phase A's own queue is beside them.

**QUEUED — the serialised-suites rule**: Joust and BuggyBoy rebuild the same shared `liboracle.so`
via `ORACLE_VIA`, so concurrent runs produce phantom failures — one suite links the `.so` out from
under the other. Run the projects' suites SERIALLY. That is the **seventh way a sweep lies**, and it
is now in `recreate/README.md`'s list beside the other six.

### Batch 34: dispatch rows 32..37, and what CLOSES the $4e38..$5407 band

**SIX ROUTINES, 694 BYTES, ALL CLEAN.** **Verified 237, 27,206 bytes, 61.5 % of §0k's 44,262;
`make test` 4558** (4466 before, and all 92 of the growth is `test/test_behavior.py`, which stands
at 944 — 87 written with the batch, one the mutation sweep asked for, and four the review gate did). **32 of the table's 62 rows are live and 30 remain** — `PORTED_SLOT_COUNT` holds the figure
and a case asserts it against the image's own table. Every callee these six reach was already
reconstructed, so not one of them needed a boundary; that is the second batch running in this tier
where that is true of the whole set.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$5046` | `actor_behavior_type32` | 278 | CLEAN — the HOPPING gold collectable, and THREE globals of its own |
| `$5208` | `actor_behavior_type33` | 82 | CLEAN — the CLOCK pickup, and the one collectable with no moving gate |
| `$525a` | `actor_behavior_type34` | 220 | CLEAN — not a creature: the SHOP'S ITEM CURSOR |
| `$5336` | `actor_behavior_type35` | 38 | CLEAN — 38 bytes, not the 134 a scan gives it |
| `$53bc` | `actor_behavior_type36` | 38 | CLEAN — slot 35's six instructions, and the row that RETYPES ITSELF |
| `$53e2` | `actor_behavior_type37` | 38 | CLEAN — the riser, and the band's last row |

**THE BAND $4e38..$5407 NOW RUNS WHOLE, with one honest exception.** Every DISPATCH ROW between
slot 28's entry and slot 38's is reconstructed, and so is every leaf they share — the payout cluster,
`actor_select_sprite_by_flag`, `actor_hop_ascend_step`. The exception is `scene_copy_record_fields`
(`$539e`, 30 bytes), which sits INSIDE the band and is not a dispatch row at all: it is
`player_pending_event_gate`'s spawn helper, reached by a `bsr` from `$c5e`, and it belongs to
whichever batch ports that gate. Nothing else in `$4e38..$5407` is code this port does not have.

**WHAT THESE SIX ARE.** Two of them are collectables and four are not.

  * **Slot 32 is slot 31's payout with a HOP MACHINE in front of it.** It falls, ascends, and on
    every frame it is SUPPORTED it spends one of `WB_ACTOR_FIELD_10` and relaunches at whatever the
    byte now holds — so the hops shorten by one each time and the LAST one is skipped, because the
    tick that reaches zero raises the second latch and launches nothing. From its first landing it
    also walks one pixel a frame, turning round on a blocked probe, and plays
    `WB_ACTOR_ANIM_5160_FRAMES`. Collected, it pays `hud_award_gold_from_descriptor`, so it inherits
    the declared video-counter pair and the packed-BCD extend chain whole.
  * **Slot 33 is the game's CLOCK.** It raises `WB_PANEL_FRAME_REWIND` and `WB_PANEL_FRAME_HOLD`
    together, one instruction apart — which winds `WB_PANEL_FRAME_DELAY` back up to `$500` in steps
    of `$14` a frame and freezes the countdown while it climbs — and adds `$20` to the score. No
    gold, no meter. It is also the ONE collectable in the band with no `btst #0,8(a0)` anywhere in
    it, so a clock picked up mid-hop is taken where slots 28, 31 and 32 all refuse.
  * **Slot 34 is the SHOP'S ITEM CURSOR**, and its own `WB_ACTOR_X` is the selection. The joystick's
    left and right EDGES walk it between `$33`, `$78` and `$be`, each planted with a y as one
    `move.l #imm,(a0)`; arriving on either END posts that item's message id out of
    `shop_record_ptr` and arriving on the MIDDLE posts the dismiss `$ff` with no lifetime beside it.
    Fire writes `shop_request`. **The fire mapping is not the positional order** — left is item 1,
    right is item 2 and the MIDDLE is `WB_SHOP_REQUEST_FAREWELL`, so the word runs 1, 3, 2 across
    the screen. It is deaf while `scene_message_pending` or `scene_ack_wait` is up: both `tst.w`s
    run BEFORE the joystick is read.
  * **Slots 35, 36 and 37 are the actors `player_pending_event_gate` ($b1a) spawns and waits on**,
    and that is the whole of what they are for. 35 and 36 play ONE sixteen-word animation over ONE
    GLOBAL cursor and each raises a different flag on the wrap — `$b12` and `$b16`, two of the five
    fields inside `stage_reset_block` that nothing had read before. 36 also `clr.w`s its own
    `WB_ACTOR_TYPE`, retyping itself into the bare `rts` at slot 0. 37 is 36's ALTERNATIVE (`$cd8`
    picks between the two on `6(record_ptr_10420)`): no animation and no table, just a one-pixel
    rise until its y EQUALS the descriptor's own `WB_SCENE_VARIANT` word less `$20`, and then the
    same `$b16`.

**A PLATE CORRECTED, CITED TO BYTES, AND IT WAS THE BATCH'S OWN PREMISE.** `../names.txt` said slot
32's cursor "zeroes the cursor one word EARLY where $6872 reads the terminator after the frame it
published". Both readers look ahead by exactly the same word. `$6872` publishes with
`move.w (a1)+,6(a0)` — a POST-INCREMENT, `$3159` — so its `cmpi.w #$ffff,(a1)` at `$68b8` and slot
32's `cmpi.w #$ffff,2(a1)` at `$5148` read the same address, and neither ever draws the terminator.
`test_ALL_THREE_readers_of_the_5160_table_wrap_on_the_SAME_cursor` (named
`test_two_of_the_three_...` until batch 39 ported the third) drives every reader
against the oracle at the last frame and at the one below it. What the two DO differ in is the
cursor: `$6872`'s is the zero-extended record byte `18(a0)` and it commits `addq.b #2` to memory
BEFORE the test, overwriting it with `clr.b` on the wrap (two writes to one byte); slot 32's is a
GLOBAL WORD, indexed SIGN-EXTENDED, stepped in the register and stored ONCE.

**AND THE CENSUS THAT CORRECTION RESTED ON WAS ITSELF WRONG — THE TABLE HAS THREE READERS.** The
independent gate found the third: `$58f8`, six bytes into the UNPORTED `actor_behavior_type46`
(`$58f2`), is `lea $5160.w,a1` and steps the table off `18(a0)` exactly as `$6872` does, down to the
post-increment publish and the look-ahead. The batch's "two readers" swept the LONG encoding plus one
SHORT site and missed the other short one — which is precisely the operand-scan trap this batch wrote
into `docs/methodology.md`, committed in the same changeset that fell for it. The census is now a
stated WHOLE-IMAGE SCAN OF BOTH ENCODINGS, and it is in the `var` plate rather than in prose: long
`00005160` once at `$5138`; short `5160` word-aligned at `$513a` (the low half of that longword, not
an operand), `$58fa` and `$6874`; and `$6f2f`, which is ODD and therefore cannot be an operand at
all. Every table address this batch touched was re-swept the same way — `$535c`/`$535e` (slots 35 and
36, the long and short forms of one cursor, four sites), `$4f5c` and `$5160` — and only `$5160` moved.

**AND A SECOND SCAN ERROR OF THE SAME SHAPE.** The reconnaissance gave slot 35 `$5336..$53bb`,
which is 134 bytes. It is **38**, `$5336..$535b`: `$535c` is its own cursor, `$535e..$537d` its
sixteen frame words, `$537e..$539d` the 32-byte record TEMPLATE `scene_copy_record_fields` is
handed, and `$539e` that routine's own entry. The lesson batch 33 wrote down — look every address
inside a scanned extent up in `../names.txt` first — caught it: `$539e` was already named there.

**SLOT 32's THREE GLOBALS ARE THE TIER'S SECOND `actor_type30_cursor`, and over three bytes rather
than one word.** `actor_type32_walking` ($515c), `actor_type32_hops_spent` ($515d) and
`actor_type32_cursor` ($515e) are all GLOBAL, so two live type-32 records share one hop machine, one
walk gate and one animation phase — a record spawned while another is walking is walking from its
own first frame. `test_slot32s_latches_are_GLOBALS_two_records_share` runs an AIRBORNE second record
after a first one lands and requires it to walk. The two names are renamed from
`actor_type32_state`/`actor_type32_done`, which were written before the body was read.

**AND THE FREE ARM CLEARS THE LATCHES BUT NOT THE CURSOR** — where slot 30's ending `clr.w`s its own
cursor between the `bclr` and the free marker. The two handlers are a hundred bytes apart in one
band and disagree about it, so the next type-32 record starts its hop machine over and its animation
where the last one left off. A case asserts the cursor's ABSENCE from the free frame's write set.

**WHAT THE GATE'S TWO FLAGS MEAN, read off `player_pending_event_gate` rather than guessed.** `$b12`
is tested at `$c2e`: while it is clear and the record at `$998c` is free, the gate plays SFX 5 and
spawns a type-35 actor from the template at `$537e`; while it is set it runs the byte-coded script
at `$19ac` and clears `$b0e` and `$b12`. `$b16` is tested at `$c76` and its arm spawns a PAIR — an
inert type-0 record showing sprite `$1a9`, and beside it either a type-37 riser (`$1a8`) or a
type-36 animator (`$1a4`), chosen at `$cd8`. `$1a4` is also the first word of
`actor_event_anim_frames`, so a type-36 record's animation starts on the frame it was spawned
showing. Both flags now carry a `var` and a `cmt`, and `stage_reset_block`'s plate no longer says
that none of its five fields is established.

**TWO OTHER PLATES CORRECTED.** `shop_request`'s said the three `cmpi.w #$33/$be/$78,(a0)` read "the
spawn type of the thing being stood on"; that word is `WB_ACTOR_X`, and the same handler WRITES it —
they are the cursor's three positions. `shop_record_ptr`'s said `$52c0` and `$52e0` post `66(a1)`
and `68(a1)` "as message ids" without saying which; they are the two ends' cursor messages, and the
fire mapping at the same x is what says 66 belongs to item 2 and 68 to item 1.

**MUTATION SWEEP: 45 OF 46 CAUGHT, and the one survivor is the equivalence below.** Pre-hoc axes
over all six bodies: both halves of slot 32's contact gate, its two hop-machine gates, the latch
raised on the wrong arm, the countdown branch inverted, the launch speed made a constant, the walk
gate dropped both ways, the turn dropped, the sentinel read AT the frame instead of one word ahead,
the cursor zero-extended, the wrap removed, the frame published from the LOOK-AHEAD word, the free
arm made to clear the cursor / keep the latches / clear only the first, the frame published before
the countdown; slot 33 given slot 31's moving gate, each panel word dropped in turn, its score entry
X forced SET, its flicker dropped; slot 34's two gates dropped, left and right swapped, the middle
made to post a lifetime, the two item messages swapped, the message stored as a WORD, the middle's y
made the ends', the middle's fire made item 2, the fire arm hoisted above the directions, the held
byte read instead of the edge; the event step's mask moved before the fetch, its cursor
zero-extended and its stride doubled, slot 35 made to raise slot 36's flag and to retype itself,
slot 36 made not to; slot 37's equality made a threshold, its rise added instead of subtracted, made
to move on the frame it arrives, pointed at the other record pointer and at the descriptor's KIND
word instead of its variant.

**THE SWEEP FOUND ONE REAL HOLE IN THE BATTERY, and it is the word-versus-byte class again.**
`walk/type32-word-step-test` — slot 32's `tst.b d0` replaced by slot 28's
`step_word_was_blocked_at_column_0` — SURVIVED the first pass. Every blocked step the cases drove
landed in map column 0, where the whole low word is zero and the two tests agree.
`test_slot32_TURNS_ROUND_on_a_clamped_step_where_slot_28_does_not` closes it on the game's own
geometry: a step the right-edge clamp refuses comes back `$0100`, whose BYTE says blocked and whose
WORD does not, so slot 32 turns its record round on the level's edge and slot 28 — on the identical
seed — does not. The mutant is now caught, and the two handlers' readings are pinned against each
other rather than each against itself. (`test_slot28_does_NOT_turn_round_when_the_probes_high_byte_is_set`
is the other half of the pair, and batch 33 wrote it for the same reason.)

**Two sweep-hygiene notes, both measured.** `type34-message-stored-as-a-word` first came back
`NO-ANCHOR` because a comment tidy had reflowed the very line it patches — an anchor is part of the
mutant and goes stale with the source, and "no anchor" must be reported as its own verdict rather
than folded into "caught". And the sweep was re-run with `pytest -x`: the verdict is the returncode
either way, but stopping at the first failure took a caught mutant from ~5 minutes to ~30 seconds on
a loaded machine, which is what made 46 axes affordable at all.

**THE REVIEW GATE (eight finder angles) FOUND FIFTEEN REAL ITEMS**, all applied, and the three that
matter most are each a claim this batch itself had made and could not support:

  * **A CASE THAT COULD NOT FAIL.** `test_the_two_event_rows_share_ONE_cursor` handed the cursor
    from 0 to 2 — and `actor_event_anim_frames` holds each sprite for FOUR frames, so the frame at 2
    IS the frame at 0. The gate proved it by reseeding the second run to 0 ("it never saw the first
    record's step") and watching the case stay green. It now hands over from 6 to 8, which crosses a
    four-frame group, and the same reseed reds it — run, not reasoned about.
  * **AND A SECOND ONE, in the case next to it.** `test_slot32s_latches_are_GLOBALS_two_records_share`
    let its second record LAND, and a landing raises the walk latch itself ($50be's `tst.b` is a
    re-read below $508c's `st`) — so the record would have walked whatever the first one did. Both
    of its runs now shut the hop machine with WB_ACTOR_TYPE32_HOPS_SPENT, so the only thing that can
    raise the latch is the previous run, and a NEGATIVE control (latch down, same record, must stand
    still) is what pins the read side at all: the tier seeds every record with keyed NONZERO bytes,
    so a port reading a per-RECORD latch would have found one and walked.
  * **`$b16` HAS A READER THE RECONNAISSANCE MISSED**, and it changes what these rows are: `$1fa2` is
    a THIRD animation stepper of slots 35 and 36's exact shape over its own cursor at `$2394`, gated
    on the flag they raise. The `var` plate's census said four operand sites and named the wrong
    fourth (the `clr.l $b14.w`, which does not name `$b16` at all). Registered, not followed.

Also applied: `type32_walk_and_turn` deleted in favour of calling `actor_step_facing` — it was that
routine's body re-spelt, and its own plate justified the duplication by citing slots 48/49, which
CALL it (four angles found this independently); the two shop-record offsets moved out of the slot-34
block into the shop record's own, where every other field of that record already lives; `hud.h`'s
entry-X audit corrected from FOUR call sites to FIVE (slot 33's is the fifth, and the second proved
by the differential rather than by bytes); `behavior.h`'s "its ending clears all three" corrected —
it clears the two latches and NOT the cursor, which is the batch's own headline finding contradicted
one file over; `WB_JOY1_FIRE_BIT` pinned EQUAL to `WB_ACTOR_TYPE61_FIRE_BIT` by a case, since
layout.py's literal-only scrape cannot derive one from the other; the two hand-rolled second-record
runs given the return-code assertion `_run_handler` exists to make; slot 37's descriptor rows driven
on BOTH arms instead of only the arrived one; two dead parameters dropped; and five stale comments
fixed that this batch's own changes had falsified ("its one reference" on the `$5160` table, "only
slot 31 reads the video counter", "THREE different sets", "all three arms", "slots 28, 30 and 31").
Two arithmetic slips in `docs/methodology.md` corrected (78 + 48 is 126, not the recorded 146; the
two event rows are 134 bytes apart, not 128), and the `#$14 at $5218/$5220` bullet below rewritten —
those operands are `$ffff`.

**NOT PINNED, HONESTLY.**
  * **SLOT 32's `move.b 10(a0),d0 / move.b d0,11(a0)` RE-READ — an EQUIVALENCE rather than a hole,
    and THE FIRST WRITE-UP OF IT WAS WRONG.** That version argued the `btst #2,8(a0)` gate could
    never be satisfied on a record whose counter store bus.h drops, "because every arrangement that
    puts the counter outside also puts the FLAG byte outside". The independent gate constructed the
    counter-example: `os_in_image` admits `$fffff` as the last in-image byte, so a record at
    **`$ffff7`** puts WB_ACTOR_FLAGS on `$fffff` — INSIDE — while the counter (`$100001`) and the
    speed (`$100002`) are both outside. The gate CAN be satisfied. The rule as written was reusable
    and false, which is worse than no rule.
    The true argument is one step further on, and it is about the CONSUMER rather than the gate:
    **the store that consumes the re-read is dropped whenever the re-read's source is.**
    WB_ACTOR_SPEED (11) is the byte immediately after WB_ACTOR_FIELD_10 (10), so any address that
    puts the counter outside the image puts the speed outside with it, and whichever value the port
    computed lands nowhere. The single address where the two part is the 24-bit fold at `$fffff5`,
    where the counter is `$ffffff` (outside) and the speed wraps to `$000000` (inside) — and there
    WB_ACTOR_FLAGS is `$fffffd`, outside, so THAT record cannot pass the gate either. Both halves
    are needed; neither alone closes it. The original's spelling is reproduced regardless.
    `reread/type32-speed-from-the-computed-local` is the mutant and the sweep's ONE survivor.
    (Contrast the swoop's `$7378`/`$73c0` pin, where the state byte folded back INTO the image and
    the coordinates did not — there the geometry made the difference observable.)
  * **SLOT 32's DEAD `clr.b $515d.l`.** `clr.w $515c.l` has already written that byte with the same
    zero, and the oracle's write ledger is address-keyed, so one zero and two are the same ledger.
    The instruction is reproduced because it is what the bytes do; no case can hold it.
  * **WHY SLOT 33'S TWO PANEL WORDS HAVE TWO CONSTANT NAMES.** `$5218` and `$5220` both write
    `$ffff` (`33fc ffff ...`), and `WB_PANEL_FRAME_REWIND_SET` and `_HOLD_SET` are two names for
    that one value because they are two ADDRESSES. Nothing says the pair must move together beyond
    the fact that they do — no case can separate "one flag with two writers" from "two flags".
    *(An earlier revision of this bullet said the two operands were `#$14`; they are not, and the
    only `#$14` in the handler is the `cmpi.w #$14,12(a0)` flicker mark at `$5236`.)*
  * **Which creature or object each of the six slots DRAWS.** Slot 32 and slot 33 publish frames out
    of tables this batch reads but does not identify; slot 34's cursor sprite is whatever spawned it.
  * **The gates that READ `$b12` and `$b16`** — `player_pending_event_gate` ($b1a) is unported, so
    what these three handlers raise is pinned as a write and not as a consequence. **AND `$b16` HAS
    A SECOND READER the reconnaissance missed**, found by this batch's own review gate: `$1fa2` is a
    THIRD animation stepper of slots 35 and 36's exact shape — `tst.w $b16.w / beq / lea $2394.l,a1 /
    move.w (a1)+,d0 / move.w 0(a1,d0.w),6(a0) / addq.w #2,d0 / andi.w #$1f,d0 / move.w d0,$2394.l` —
    over its OWN cursor and table at `$2394`, gated on the flag these rows raise. It is unnamed,
    unported and NOT a dispatch row; it is registered here rather than followed, and it is why the
    claim "35..37 are what the gate spawns and waits on" is about those rows and not about every
    consumer of the flag.

**QUEUED — WHAT IS LEFT OF THE TABLE.** Thirty rows: **slot 1** (the player, the largest subtree
behind the table), **slots 9..27** — the nineteen-row monster-prologue family, the biggest single
block left — **slot 38** (the pickup, whose three `bra.w`/`bne.w` into `actor_defeat_and_score` are
already named), **slots 39..46** and **slot 57**. The order the reconnaissance suggests is 9..27
first (one grammar, nineteen bodies), then 38..46 and 57, and the player LAST.

**QUEUED — THE THREE UNPORTED ROUTINES THIS BATCH'S OWN SCANS TURNED UP**, none of them a dispatch
row and none followed here:
  * **`$1fa2`, `actor_event_anim_step_2394`** — a THIRD animation stepper of slots 35 and 36's exact
    shape, gated on `event_anim_done_b16` and stepping its own cursor/table at `$2394`. It and the
    table now have `fn`/`var` directives so both work-discovery mechanisms can see them.
  * **`actor_behavior_type46` ($58f2)** — the THIRD reader of `actor_anim_5160_frames`, found by the
    both-encodings re-sweep. It is slot 46 and will come with its own band.
  * **A SECOND READER OF `actor_type30_drift`, and it uses a DIFFERENT cursor.** `lea $4f5c.l,a1` at
    `$b84` inside `player_pending_event_gate` steps the same 32-word table off `$4f58` — the word
    slot 30's plate calls a `$0000` pad. So batch 33's "reached by the one `lea $4f5c(pc,d0.w)` at
    `$4f1a`" is wrong and `$4f58` is a cursor rather than padding. Out of this batch's scope,
    registered rather than folded in.

**QUEUED, CARRIED FORWARD UNCHANGED from batch 33**: `abcd_byte` to the kit; regenerate
`../out/names_dump.txt`, `../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt` before
the next naming pass; `bus.h` to the kit; the `$1ab4` boundary; the tier partition; the
`scene_run_effect` latent guard. **NEW**: `../names.txt` carries THREE duplicate `cmt` directives
(`0x1023a`, `0x10394`, `0x1044c`), which `ApplyNames` resolves last-wins — they predate this batch
and are registered rather than folded into it.

**A PROCESS FAILURE WORTH RECORDING, because CLAUDE.md §8 exists for it.** A `git checkout --
src/behavior.c` typed to clean up after an aborted sweep DISCARDED the batch's whole
reconstruction — the file was untracked work, not a committed state — and the sweep's own snapshot
was then overwritten by the next run before the loss was noticed. It was reconstructed verbatim, and
the suite came back to the same 4553 — which is this batch's count BEFORE the mutation sweep's row
and the review gate's four, i.e. the figure that was current at the moment the loss happened, and
not the 4558 the headline above states for what the batch finally commits. **Back up before a destructive git command on a file whose
only copy is the working tree**, and never let a sweep re-snapshot without checking what it is
snapshotting.

### Batch 35: dispatch rows 9..13 — the MONSTER-PROLOGUE family opens

**SIX ROUTINES, 1,310 BYTES.** Five dispatch rows and the leaf one of them calls. **Verified 243,
28,516 bytes, 64.4 % of §0k's 44,262; `make test` 4670** (4558 before, and all 112 of the growth is
`test/test_behavior.py`, which stands at 1,056). **37 of the table's 62 rows are live and 25
remain** — `PORTED_SLOT_COUNT` holds the figure and a case asserts it against the image's own table.
Three of the five are CLEAN; two are BOUNDED, and the boundary is the same one slot 53 reports.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$2e12` | `actor_behavior_type09` | 152 | BOUNDED at `$e06` — the random hopper, and the shortest body in the family |
| `$303a` | `actor_behavior_type10` | 350 | CLEAN — the flier: a 32-word hover table and no map probe at all while alive |
| `$3218` | `actor_behavior_type11` | 324 | CLEAN — the decider: one `rng_next` word buys a facing AND a hop |
| `$33bc` | `actor_behavior_type12` | 174 | BOUNDED at `$e06` — the chaser, and the only user here of `$2fce` and `$2f86` |
| `$34d2` | `actor_behavior_type13` | 246 | CLEAN — the bouncer, whose hurt arm ALWAYS ends in the defeat |
| `$2f46` | `actor_random_facing_hop` | 64 | the family's own leaf, ONE caller — and NOT the "coin-flip turn" its plate called it |

**THE NOMINAL SPANS ARE ALL WRONG, AND ONE OF THEM BY A FACTOR OF THREE.** A scan from each slot's
dispatch entry to the next gives 552 / 478 / 420 / 278 / 262 bytes; the code is 152 / 350 / 324 /
174 / 246. What the difference holds is data — frame lists, list PAIRS and slot 10's hover table —
and, in slot 9's case, **SIX SHARED LEAVES that belong to no slot at all**: `$2f22`, `$2f46`,
`$2f86`, `$2fce`, `$2fe8` and `$3006` sit between slot 9's last `rts` and slot 10's entry, and FIVE
of the six were already named and ported — `$2f46` is the only one this batch adds. Slot 9's own body is 152 of the 552 a scan gives it. Batch
34's rule — look every address inside a scanned extent up in `../names.txt` first — is what caught
it again.

**WHAT THESE FIVE ARE.** All five run the $2462 band's grammar: the spawn gate, the contact enum
(`$23b6` short-circuiting `$5c6e`), `bset #0,9(a0) / clr.b 18(a0)` before the tail jump into
`actor_damage_template_hitpoints`, and a hurt animation on bit 0 of `9(a0)`. The middles share
nothing.

  * **Slot 9 is a chain of calls and nothing else.** Its live frame is `actor_fall_and_settle`,
    `actor_hop_ascend_step`, `actor_step_facing` at three pixels, `actor_random_facing_hop` and
    `actor_anim_step_facing_list`. **The order inside it is what makes the two halves separable**:
    the step walks on the facing the record ARRIVED with, the hop then rewrites that facing, and the
    animation — which runs last — reads the byte the hop left. So on a turning draw the step and the
    published frame disagree about which way the record is looking, and a case drives both.
  * **Slot 10 never touches the collision map while it is alive**, and it is the only caller of
    `actor_step_toward_followed` (`$6840`) in the image. A 32-word signed table moves its y every
    frame; **the vertical close on the followed record happens ONCE PER 32-FRAME CYCLE**, not once a
    frame, because the `bne.w` reads the MASKED hover cursor and skips the close on the other 31.
    Sideways it drifts one pixel toward its side flag with no probe at all — it can walk through a
    wall, and a case seeds a solid row and requires it to — and every `$64` frames it turns round,
    reloads and takes one homing step on both axes. **The frame published on a turn frame is the NEW
    side's**: the `btst #3,8(a0)` below the turn re-reads the byte the `bchg` wrote, where slot 3's
    walk chooses its list before its own turn.
  * **Slot 11 walks while a countdown runs and DECIDES when it expires.** The decision frame reloads
    `$19`, and then — only for a SUPPORTED record — draws one `rng_next` word: bit 2 picks the
    facing and bit 1 vetoes the hop. **Both of its arms return above the walk, so the decision frame
    publishes no animation at all.** The reload runs BEFORE the supported test, exactly as
    `actor_tick_timer30` orders the same two things, so a record caught in the air still gets a
    fresh countdown and does nothing with it. Its walk at `$32b2` is `actor_step_facing`'s body
    spelt inline with `move.w #$2,d7` in EACH arm.
  * **Slot 12 is the chaser**, and the only handler in the family that uses `$2fce` and `$2f86`:
    face the followed record, step two pixels toward it, and hop every `$32` frames on the
    generator's permission. **Its animation is picked by `btst #2,8(a0)` rather than by a cursor** —
    supported plays an eight-word walk pair, airborne plays a pair whose lists are ONE word and a
    terminator, so `$3006`'s look-ahead zeroes the cursor on the very frame it publishes and an
    airborne record holds one frame.
  * **Slot 13 hops on every frame it is supported** — no countdown, no draw, no facing change — so
    it is airborne almost always. **And its hurt arm is not a hurt arm.** It never lowers bit 0 of
    `9(a0)` and never tests the defeated mark: `tst.b 30(a0)` zero arms a `$19`-frame throe once
    (`st 30(a0)` is the latch), every frame after that steps two pixels away and publishes sprite
    `$37` straight, and the frame `subq.b #1,31(a0)` reaches zero does `clr.b 30(a0)` and
    `bra.w $6bb8`. **THE ONE UNCONDITIONAL TRANSFER INTO `actor_defeat_and_score` IN THE FAMILY**, so
    a struck type-13 record always dies whatever its template's hit-point pool said — driven with
    the mark up AND down, and both die.

**THE FAMILY'S HURT TAIL IS NOT THE BAND'S, and the difference is one mnemonic.** Slots 9, 10, 11
and 12 all end their last hurt frame `bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8` — the DEFEATED
bit is only TESTED — where slots 2, 3 and 4 `bclr` it. A case that merely checked "the defeat ran"
would pass against either spelling, so `test_the_family35_hurt_wrap_transfers_and_LEAVES_the_defeated_bit_standing`
asserts the bit is still set behind the transfer, and the mutant that clears it is caught.

**AND THE STRUCK ARM SPLITS THE FIVE THREE-TWO.** `$2e52`, `$307a` and `$33fc` are `bsr $67c2`
between the two writes and the tail jump; slots 11 and 13 have no such instruction and take the hit
facing wherever they already were. `FAMILY35_STRUCK_FACES` states it per slot and one parametrised
case drives all five, asserting the flag both ways.

**TWO HANDLERS ARE BOUNDED, AND THE ARM IS ONE THE GAME RUNS EVERY TIME A MONSTER IS HIT.** Slots 9
and 12 both `bsr $d78` on their hurt arm, and `player_gate_on_1516` BRANCHES into
`WB_PLAYER_STEP_BODY` (`$e06`) while `WB_TILE_33_MODE` is clear — so those frames report an address
rather than a result. That is the port's limit and not a fact about the game: with the mode SET the
gate returns at once and both arms run whole, which is how every other slot-9 and slot-12 case here
is driven. `test_the_two_bounded_hurt_arms_are_exactly_the_two_that_call_the_player_gate` checks
`FAMILY35_BOUNDED` against the pinned bodies rather than against this paragraph.

**A PLATE CORRECTED, AND IT IS THE LEAF'S NAME.** `$2f46` was `actor_random_turn # ctx`, "a
coin-flip turn". The bytes say it turns AND LAUNCHES: bit 2 of the generator's word chooses `bset
#3,8(a0)` or `bclr`, and then bits 0 and 1 of `8(a0)` go up, bit 2 goes down and `11(a0) := $a`
unconditionally. It is renamed `actor_random_facing_hop`, and the contrast with `$2f86` — where
`btst #2` of the same word VETOES the relaunch instead of choosing a side — is in both plates.
**Slot 11 reads bit 2 the OPPOSITE way round from `$2f46`** (SET faces left there, right here), which
is why the two constants are separate names rather than one.

**THE CENSUS, RUN BEFORE THE FACT AND THEN CHECKED BY A CASE.** Every table this batch names was
swept over the whole image in BOTH absolute encodings and in the `lea d8(PC,Dn.w)` displacement
form; `test_every_table_this_batch_names_has_exactly_one_lea_naming_it` re-runs the long-form half
against the loaded image for all fifteen. The word `$337c` occurs 31 times in the image and `$3494`,
`$34c0`, `$3472`, `$3198`, `$303a` and `$3218` several times each — **none of them preceded by an
abs.w-mode opcode**, so all are data. The five slot ENTRIES were swept the same way over every
branch and absolute-jump form and have NO reference but their own dispatch longword: the plates'
"reached ONLY through `jmp (a1)`" is now measured rather than assumed, which is what batch 31's
hidden `jsr $6f9e.w` made necessary.

**THIRTY-TWO BYTES OF SLOT 11's DATA THAT NO INSTRUCTION NAMES — and they are REACHABLE PADDING,
not dead bytes.** `$338c..$339b` and `$33ac..$33bb` are two sixteen-byte blocks, byte-identical
copies of the two hurt lists below them, and the census finds no `lea` anywhere in the image naming
either address. **The first draft of this paragraph drew the wrong conclusion from that** and the
independent gate caught it — see "the index is RAW" below. What the cases pin now is the true shape:
the bytes are equal, no `lea` names them, and a cursor of `WB_ACTOR_ANIM16_MASK + 1` reaches the
first block through the LIVE table's own `lea` and publishes a frame identical to the table's. The
duplicates are what MAKES that over-read harmless, which is what they are for. They are recorded in
the `var` plates rather than trimmed.

**MUTATION SWEEP: 47 MUTANTS OVER SEVEN AXES, 46 CAUGHT, and the one survivor is an equivalence
UNDER THIS HARNESS with the argument checked rather than asserted.** Pre-hoc axes over all six
bodies: the family's hurt tail made to CLEAR the defeated bit and to keep bit 0, its away-step made
a toward-step, its cursor step collapsed to one store, its inline launch made to keep the supported
bit; `$2f46`'s bit 2 made a veto, its facing inverted, its supported gate dropped, its speed changed;
slot 9's walk step, its hop hoisted above the step, its two list pairs swapped, its boundary
ignored, its wrap test inverted, its struck facing dropped; slot 10's hover mask, the close made
every-frame and its sign inverted, the hover cursor moved to the other byte, the drift inverted, the
turn reload changed and the turn itself dropped, the homing step dropped, the animation facing read
BEFORE the turn, the hurt suppression inverted and its lists swapped; slot 11's reload moved below
the supported test, both draw bits inverted, its hop speed, its hurt list taken off the side flag
and its bit moved one over, the decision made to fall through into the walk, its walk step, its
struck arm made to face; slot 12's list pairs swapped, its chase made a retreat, its list chosen
before the timer runs, its boundary ignored; slot 13's hop speed, its relaunch gate inverted, its
throe latch inverted, its defeat made CONDITIONAL, its throe step made a chase, its hurt sprite, its
cursor mask, and its first-frame facing call dropped.

**THE SWEEP FOUND THREE REAL HOLES AND ONE BADLY BUILT MUTANT, and the three holes are one shape:**
an arm every case reached with only one value of the state that steers it.
  * `step/family-away-becomes-toward` SURVIVED because every case reached
    `step_away_without_facing` with `WB_ACTOR_FLAG_SIDE_BIT` CLEAR, so its SET arm was never driven.
    Closed by a parametrised slot-10 retreat over both facings, and by parametrising slot 13's
    arming frame over which side the followed record is on.
  * `slot13/side-flag-not-set-on-the-first-throe-frame` SURVIVED for the neighbouring reason: the
    arming case seeded the record already facing the way `actor_set_side_flag` would leave it, so
    dropping the call changed nothing. Both rows now seed the OPPOSITE flag to what the call writes.
  * `slot12/list-chosen-before-the-timer-runs` SURVIVED because no case let `actor_tick_timer30`
    reach its relaunch, so `WB_ACTOR_FLAG_SUPPORTED_BIT` never changed INSIDE a frame and the order
    of the two could not matter. `test_slot12_publishes_the_AIRBORNE_list_when_its_own_timer_launches_it`
    drives a supported record whose countdown is zero and whose draw permits.
  * `slot10/anim-facing-read-before-the-turn` was the batch's own mistake rather than the battery's:
    the mutant ADDED a publish above the timer instead of MOVING the facing read, so the real
    publish below overwrote it and the mutant could not have changed anything. Rebuilt to hoist the
    read, it is caught.

**AND AN EIGHTH WAY A SWEEP LIES — WHICH IS MODE 4's GUARD EXTENDED TO THE BUILD ARTIFACT, not a
new mode.** A sweep killed mid-`pytest` leaves the MUTANT's `build/*.so` on disk and never runs its
`finally`; the sources can then be restored by hand and the NEXT run's step-0 green check still
loads the mutant library and reports the pristine tree as RED. It reads exactly like a broken batch,
and it cost this batch a diagnosis before the cause was found. The cure is one line — force the
relink BEFORE the green check, not only before each mutant — and it is in
[`README.md`](README.md)'s recipe. The frame sentence's count of SEVEN stands, on batch 34's
precedent for exactly this kind of extension.

**A CASE THIS BATCH WROTE AND THEN DELETED, because it could not fail.** The one surviving mutant is
`cursor/memory-step-becomes-one-store`, and the first attempt to pin it put a type-10 record at
`$fffe2` so that `WB_ACTOR_FIELD_31` fell one byte past `os_in_image`'s last (`$fffff`): with the
store dropped the original's mask reads back ZERO and takes the vertical close, where a port holding
the stepped value in a register does not. The two really do diverge there — a candidate-only run
shows `$3fb` against `$3fd` — **and the differential cannot see it**: it compares `[0, STACK_GUARD_LO)`
and `STACK_GUARD_LO` is `IMAGE_SIZE - 0x1000`, so a record in the top `$1000` bytes is inside the
oracle's own machine-stack band and excluded. The case passed under the mutant, which is the
"worse than vacuous" failure batch 30 recorded, and it is deleted rather than weakened.
**The equivalence is now argued from geometry and the argument covers the CONSUMING use**: two of
the three sites discard the answer entirely, the third (slot 10's hover cursor) branches on it, and
for `WB_ACTOR_FIELD_31` to be refused the record must start at `$fffe1` or above — which puts its y,
the only byte the difference reaches, at `$fffe3` or above and therefore inside the excluded band.
Folding past `$ffffff` refuses the y too. So no record address separates them here. *(Contrast the
swoop's `$7378`/`$73c0` pin at `$fffff0`, which works because the fields it OBSERVES fold back to
`$6` and `$a`, inside the compared prefix — nothing folds a byte 29 offsets away into that prefix
while leaving its neighbour refused.)*

**NOT PINNED, HONESTLY.**
  * **The two BOUNDED hurt arms.** Slots 9 and 12 stop at `WB_PLAYER_STEP_BODY` whenever
    `WB_TILE_33_MODE` is clear, which is the ordinary state — so the retreat, the frame and the wrap
    on those two arms are only ever driven with the mode SET. That is the port's limit, and it will
    retire when the player tier lands.
  * **`cursor/memory-step-becomes-one-store`**, above.
  * **Which creature each of the five slots DRAWS.** They publish sprite ids out of tables this
    batch reads and does not identify; the slots are still `typeNN`.
  * **The registers each handler leaves behind**, as everywhere else in this tier.
  * **Slot 11's hurt-list select is pinned as a READ, not as a meaning.** `btst #3,30(a0)` is bit 3
    of the countdown byte the live arm reloads with `$19`, and both values a case drives are states
    that countdown really passes through — but what the two lists are FOR is not established.
  * **The refused dispatch**, as in every batch since 29.

**QUEUED — WHAT IS LEFT OF THE TABLE.** Twenty-five rows: **slot 1** (the player), **slots 14..27**
— fourteen more of this family, and the reconnaissance's own suggestion is to keep taking them in
blocks of five — **slot 38**, **slots 39..46** and **slot 57**. The order stands: 14..27, then
38..46 and 57, and the player LAST.

**AND WHEN 14..27 ARE SCOPED, DO NOT QUOTE A NOMINAL SPAN AS AN EXTENT.** Every difference-of-entries
figure in this batch's own scope was wrong — 552/478/420/278/262 against a measured 152/350/324/174/246
— because a dispatch table gives entry points and the gaps between them hold frame tables, list pairs
and (for slot 9) six shared leaves. **The per-slot plates in `../names.txt` already carry a decoded
extent, `decoded code runs $x..$y`, and all five of this batch's matched the bytes exactly.** Slots
14..27 carry the same field. Read the plate, verify it from the bytes, and quote a span only as a
span; `docs/methodology.md` now says so too.

**QUEUED — `scene_copy_record_fields` ($539e, 30 bytes), which has never been in a queue block.**
Batch 34 registered it in prose as the one exception to "the band $4e38..$5407 runs whole" and then
listed neither it nor its caller anywhere a later batch would look. It is not a dispatch row: it is
`player_pending_event_gate`'s spawn helper, reached by the `bsr` at `$c5e`, and it is handed the
32-byte template at `$537e` that slot 35's own extent stops below. It belongs to whichever batch
ports that gate ($b1a), and it is the reason a band described as CLOSED still contains unported
bytes — which is worth saying plainly, because "CLOSED" is otherwise load-bearing.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`); `actor_behavior_type46` ($58f2); the second reader of
`actor_type30_drift` at `$b84`; the three duplicate `cmt` directives (`0x1023a`, `0x10394`,
`0x1044c`). **NEW**: the twelve third-copy encoders due in `leaf.py` now number thirteen —
`move_w_indirect_dn` is this batch's, and it is a FIRST copy, so the list is unchanged; what IS new
is that `andi_b_d16`, `st_d16` and `cmp_w_d16_dn` were each nearly re-added to
`test/test_behavior.py` a second time by this batch before the duplicate was spotted, which is an
argument for hoisting the file's encoder block rather than growing it.
**THE REVIEW GATE (high, eight finder angles) FOUND THREE MORE COVERAGE HOLES — each one proved by
mutating the reconstruction and watching the whole suite stay green — plus a correction to a plate
this batch had just written.**
  * **Slot 10's vertical close is a SIGNED compare and nothing said so.** Replacing `field_w`'s
    `int16_t` with an unsigned reading survived all 4,657 cases, because every seed in the file uses
    a y of `STAND_Y ± 0x40` and never sets the sign bit. A record whose y is above the screen origin
    (`$ff00`) with the followed record at `$0010` closes DOWNWARD signed and upward unsigned — the
    flier drifts the wrong way for a whole cycle. A second row on the wrap case drives it.
  * **The close RE-READS the y the hover step just wrote**, which the comment claimed and nothing
    checked: comparing the pre-hover y instead also survived. The wrap frame's hover word is `-2`, so
    a followed record placed ONE PIXEL between the two readings is the only seed that separates
    them, and `test_slot10s_close_compares_the_y_the_hover_JUST_WROTE` places it there.
  * **`bsr $1334` BEFORE `bsr $501a` was unpinned at all five new sites** (and at nine older ones):
    swapping the pair everywhere survived. The order is observable only on the frame an ascent ENDS,
    because `actor_hop_ascend_step` lowers the very bit `actor_fall_and_settle`'s head tests — with
    `WB_ACTOR_SPEED` at 1 the original leaves the record one pixel higher than the swap does, and
    four parametrised rows now drive it.
  * **AND THE PLATE ON `step_away_without_facing` TRANSCRIBED THE WRONG BRANCH.** It read
    `btst #3,8(a0) / bne`; the image at both sites ($313e, $35a0) is `beq`, with `bsr $1170` falling
    through. The code and the pins were right and the evidence was not — the exact inversion that
    would make a later reader "fix" a correct handler. Both polarities are now stated side by side,
    since `$2fe8` genuinely is the `bne` spelling of the same mapping.

**AND THE GATE'S OWN MUTATION PASS, 6 OF 6 CAUGHT**, run over the three new cases and the three
shapes the review's de-duplication created (the shared hurt frame ignoring its list-pair argument,
`actor_face_and_step_away4` losing its facing call, and its step size changed).

**WHAT THE GATE CHANGED IN THE CODE, all of it de-duplication the diff had left undone:**
`type09_hurt_frame` and `type12_hurt_frame` were the same nine statements bar one constant and are
now one `gated_hurt_frame(image, actor, hurt_lists)`; `step_away_without_facing` is hoisted beside
`step_facing` and `actor_face_and_step_away4` is defined in terms of it, which removes the second
copy of the non-obvious flag→probe inversion; `move_w_indirect_dn` was deleted (`leaf.move_w_ind_dn`
already emits that two-byte form at displacement 0, and the new encoder's docstring said otherwise);
`_launch_inline_pieces` now spells the fourth of the four sites its own docstring counts;
`_handler_cap`'s growing `if` chain became the name-keyed `HANDLER_EXTRA_INSNS` dict `_handler_band`
beside it already used; `_type10_pokes` stopped restating three seeds `_walk_pokes_for` already sets;
and `_ticks_for_slot11_draws` stops at the fourth hit instead of building 64 one-megabyte images.

**AND FOUR CLAIMS THE GATE MADE FALSE.** The census case checked only `lea <abs>.l` while fifteen
plates and a `docs/methodology.md` paragraph claimed all three encodings had been swept — it now
resolves `lea <abs>.w` and every `lea d8(PC,Dn.w)` displacement in the image, which is the form
batch 28's whole coverage wall was made of, and all fifteen tables still come back with exactly one
site. `behavior.h` said all five slots end the hurt animation with the `bclr`/`btst` tail when slot
13 has neither instruction. `docs/methodology.md` said four of slot 9's six neighbouring leaves were
already ported; five were. And one hover-cursor row was seeded ODD, so the oracle took a word read at
an odd address — legal only because the kit builds Musashi with address-error emulation off, and
unreachable from the game's own state. *(That last fix did not take: the replacement expression,
`TYPE10_HOVER_LAST - ANIM_FRAME_BYTES + 1`, is `$3d` and still odd. The independent gate found it
still live under the very comment claiming every cursor was even; it is `$3c` now.)*

**ONE CONSTANT PINNED EQUAL TO ANOTHER, batch 34's `WB_JOY1_FIRE_BIT` pattern again.**
`test_the_random_hop_turns_AND_launches_a_supported_record` steers `WB_ACTOR_RANDOM_HOP_RNG_BIT` with
`TICKS_BY_RNG_BIT`, a table stated for `WB_ACTOR_TIMER30_RNG_BIT`. The two ticks separate the bit's
values only because the two constants are equal, and nothing said so — if they are ever read apart
the parametrisation would silently collapse onto one arm. A case now asserts the equality.

**A PROCESS FAILURE, and it is CLAUDE.md §8 and sweep-lie mode 4 arriving together from a third
direction.** A review subagent ran its own mutation probe against `src/behavior.c`, snapshotting the
file when it started and restoring that snapshot when it finished — over the de-duplication the gate
had just applied. The loss was silent (the suite was green either way, on the older code) and was
caught only by grepping for the new function names. **A reviewer that mutates is a writer**: give it
a copy, or take a backup before letting one run, and re-verify the tree afterwards by NAME and not
by the suite. The scratchpad's shared sweep module was overwritten in the same way, which is why the
gate's own pass is a self-contained script.

**NOT PINNED, HONESTLY — one more, from the gate's probes.** `SETTLE_SPAN_UNREAD` versus the
followed record's sprite on slots 9's and 13's HURT arms: handing either value to
`actor_fall_and_settle` survives, which is exactly what the constant's own comment claims (only
slots 3 and 6 read a byte of it back, through their `move.b #$2,d7`). It is reproduced as the
handler's own entry d7 because that is what the original hands over, and it is recorded here as
unobservable rather than as pinned.
**THE INDEPENDENT GATE (two reviewers, transcription re-verified against a fresh `objdump`) FOUND
TWELVE ITEMS, and the first is the batch's real defect: THE FRAME INDEX IS THE RAW RECORD BYTE, AND
THE PLATES ASSERTED THE INVERSE.**

At all four of this batch's frame reads — `$332e` (slot 11's hurt), `$3110` (slot 10's walk),
`$3548` (slot 13) and `$3084` (the hover) — the sequence is `move.b <cursor>,d0 / lea 0(a1,d0.w),a1 /
move.w (a1),…`, and the `andi.b` runs AFTERWARDS on the value going back into the record. **The mask
bounds where the cursor GOES, never where it came from.** The reconstruction was already faithful —
the entry pins hold the order — but three surfaces said otherwise ("the cursor is masked, so nothing
can reach past the first sixteen bytes"), and the battery rested on it: the duplicate-block case
asserted `LAST_FRAME[mask] + WB_ACTOR_ANIM_FRAME_BYTES == mask + 1`, which compares two constants
and **cannot fail**, and three mask-BEFORE-index mutants survived all 1,050 cases.

What replaced it is four seeded cases, each driving the over-read where it is observable:
  * **slot 13 at cursor `$20` publishes `$35e8` — sixteen bytes inside `actor_behavior_type14`'s
    code** — so a word of the next handler's OPCODES becomes a sprite id. Nothing pads slot 13's
    table, which is what makes this the sharp one.
  * **slot 10's walk at cursor `$10` publishes the NEIGHBOURING list's first frame** (`$47` off the
    left list where the table's own first word is `$43`), the four eight-word lists being contiguous.
  * **the hover at cursor `$40` reads `$3218` — slot 11's own entry opcode, `$0828` — and ADDS IT TO
    THE Y**, a 2,088-pixel jump where the table's first word is `-2`.
  * **and slot 11 at cursor `$10` publishes the PADDING, which is byte-identical to the table.** That
    is what the two duplicate blocks are *for*, and it is the corrected claim: they are reachable
    padding that makes the over-read harmless, not bytes nothing can reach.

All three mask-order mutants are now caught (`index/publish-frame-masks-before-indexing`,
`index/advance-cursor-masks-before-indexing`, `index/hover-masks-before-indexing`), and the axis is
in the gate's battery: **9 of 9 caught** on the re-run.

**AND THE RECIPE THAT TAUGHT THE TRAP IS REWRITTEN.** `docs/methodology.md` had just been given
"make the census a CASE", with the two duplicate blocks as its worked example of proving a
*negative* — a paragraph written for reuse, teaching precisely the inference that had just been
wrong. It now says that a direct-reader census bounds the routines naming an address DIRECTLY and
nothing else; that a block beside an INDEXED table is reached through its neighbour's `lea` the
moment the index runs past the end; that a negative needs both halves stated apart, the census AND
the index's provable range; and that `_lea_sites` sweeps three `lea` forms and is silent about
`pea`, `movea.l #imm` and any pointer assembled at runtime. Batch 28's coverage wall was this shape
one addressing mode over.

**ELEVEN OF THE FIFTEEN `lea` CITATIONS IN THE NEW PLATES NAMED THE OPERAND, NOT THE INSTRUCTION.**
A `lea <abs>.l,An` is an opcode word and a longword, and the scan reports where the longword starts —
so `$31a8`'s plate said `$3102` where the instruction is at `$3100`, while four plates (transcribed
from the listing instead) said the instruction. All fifteen now name the instruction, which is what
the census case reports, so a plate and the case that checks it can be compared by eye.

**FOUR MORE CORRECTIONS, each verified by the reviewers.** The odd hover row the section above
claims was fixed **was still live** — the replacement expression evaluates to `$3d` — under the very
comment saying every cursor is even; it is `$3c`. The "five shared leaves" figure is six addresses
with five pre-ported (three surfaces). "Sixty-four bytes nothing can read" is thirty-two, in two
blocks (three surfaces), and after the finding above the verb changes too. And **the RNG-bit equality
pin this section claimed did not exist**: the edit adding it was in a script that died on a syntax
error and was never re-run, so `WB_ACTOR_RANDOM_HOP_RNG_BIT` and `WB_ACTOR_TIMER30_RNG_BIT` were
still unpinned while the prose said otherwise — and the hop case could not have caught a divergence,
since it computes its expectation FROM the drawn word. The one-line assert is in.

**THE RULE ABOUT REVIEWERS IS NOW IN THE DURABLE DOCS**, where the narrative above only recorded the
incident: `README.md`'s sweep section says to give a reviewer a COPY or take a named backup, and to
re-verify the tree BY NAME afterwards — `git diff` looks identical whether an edit is missing or was
never made. This batch's second reviewer did that by hand; it is written down now.


### Batch 36: dispatch rows 14..19 — the family's SECOND BLOCK, and the frame that publishes a record

**SIX ROUTINES, 1,940 BYTES, AND NONE OF THEM BOUNDED.** Every callee of all six is already
reconstructed, so each runs to its own `rts` — the first block of this family to report no boundary
at all. **Verified 249, 30,456 bytes, 68.8 % of §0k's 44,262; `make test` 4812** (4670 before, and
all 142 of the growth is `test/test_behavior.py`, which stands at 1,198). **43 of the table's 62
rows are live and 19 remain**; `PORTED_SLOT_COUNT` holds the figure and a case asserts it against
the image's own table.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$35d8` | `actor_behavior_type14` | 316 | CLEAN — the patroller that drops escorts, and the only handler here whose turn frame and drop frame BOTH end the frame |
| `$3764` | `actor_behavior_type15` | 234 | CLEAN — the walker that turns AND hops: the two `bsr $2b8e` sites in the image are its two arms |
| `$38ae` | `actor_behavior_type16` | 312 | CLEAN — the hopper that lobs, whose launch gate is a `bclr` |
| `$3a46` | `actor_behavior_type17` | 290 | CLEAN — the drifter: two GLOBAL cursors, no map at all, and five records seeded at a time |
| `$3c84` | `actor_behavior_type18` | 424 | CLEAN — the charger, and the family's largest body |
| `$3e8c` | `actor_behavior_type19` | 364 | CLEAN — the two-phase glider, and the one that publishes a record as a sprite |

**THE PLATES WERE RIGHT AND THE SCAN WAS WRONG, AGAIN — which is batch 35's own instruction paying
off.** A difference of dispatch entries gives 396 / 330 / 408 / 574 / 520 / 652 bytes; the code is
316 / 234 / 312 / 290 / 424 / 364. Every one of the six `decoded code runs $x..$y` fields in
[`../names.txt`](../names.txt) matched the bytes **exactly, on the first read**, and what the gaps
hold is this batch's own tables — 928 bytes of them, every byte accounted for below. `BODY_SIZES`
carries all six figures and a case checks each against the pin.

**WHAT THESE SIX ARE.** All six run the $2462 band's grammar: the spawn gate, the contact enum
(`$23b6` short-circuiting `$5c6e`), `bset #0,9(a0) / clr.b 18(a0)` before the tail jump into
`actor_damage_template_hitpoints`, and a hurt animation on bit 0 of `9(a0)`.

  * **Slot 14 patrols and DROPS.** One pixel a frame; `30(a0)` counts a leg down and the frame it
    reaches zero turns the record round and ENDS — no step, no animation. Below that, `31(a0)`
    counts walking frames and the frame IT reaches zero drops a type-`$2d` record on the patroller's
    own square and ends the frame too. **`move.b #$1e,31(a0)` sits BELOW the failed-allocation
    branch**, so a record that could not drop retries on the very next walking frame instead of
    waiting out the gap. Its list select re-reads `8(a0)` AFTER `bsr $2b82`, so a blocked step's
    turn shows in the SAME frame's list — slot 6's order, not slot 3's.
  * **Slot 15 turns AND HOPS.** Four pixels toward the followed record, and then `bsr $2b8e` —
    `actor_turn_and_launch`, whose whole caller census is these two arms. A blocked step or a
    one-cell drop under a supported record flips the facing, clears the supported bit, raises the
    other two and writes the speed. **Its frame list is chosen BEFORE that can happen** (the `lea`
    sits between the probe and the `bsr`), which is the opposite order to slot 14's — so the two
    orders are now driven side by side. **And its two arms step their cursor differently**: the walk
    is `addq.b`/`andi.b` on `18(a0)` in memory under a `$f` mask, the hurt arm computes in `d0` and
    stores once under `$1f`.
  * **Slot 16 lobs.** It faces the followed record and animates every frame, and when `30(a0)` runs
    out it launches itself and spawns a type-`$27` record carrying the flag byte **the launch just
    wrote**. `bclr #2,8(a0)` is the TEST and the write: an airborne record leaves having stored its
    flag byte (unchanged in value) and done nothing else, which is a write a port that read the bit
    first would be missing.
  * **Slot 17 never touches the map on either arm, and its cursors are GLOBALS.** `$3bc0` and
    `$3bc2` are two words in the image, not record fields, so **two live type-17 records drift in
    lockstep** and one spawned mid-cycle joins wherever the other left the pair —
    `WB_ACTOR_TYPE30_CURSOR` and `WB_ACTOR_TYPE32_CURSOR` are the tier's two others of that kind.
    The x table is 64 words and the y one 32, so the y cursor comes round TWICE per horizontal lap,
    and **on each frame it wraps** a
    one-in-eight `rng_next` draw seeds **FIVE type-`$34` records** on the drifter's own square,
    numbered 5 down to 1 in `30(a1)`. The `dbf` closes onto the `bsr $1b8e`, so the burst is five
    SEPARATE lookups and the first refusal ends it.
  * **Slot 18 CHARGES, and it is the only handler in the family that keeps a flag byte.** While
    `30(a0)` runs it walks two pixels; when it reaches zero and `31(a0)` is clear the whole of
    `8(a0)` is saved into `29(a0)`, the record faces the followed one, launches at speed 9 and
    spawns a type-`$29` record. `31(a0)` latched to `$ff` says a charge is running; the frame the
    record is supported again, `move.b 29(a0),8(a0)` puts the byte back, `bchg #3,8(a0)` turns it
    round, `30(a0)` reloads and the latch clears. **A record still in the air mid-charge reaches the
    ANIMATION ALONE** — no step, no turn, no restore.
  * **Slot 19 ALTERNATES between two phases, and neither latch is permanent.** While `31(a0)` is
    clear it glides: sprite `$a2` and `16(a0) := 8` rewritten every frame, and 64 signed words of x
    drift over `30(a0)`. The frame that cursor wraps, `st 31(a0)` switches it to the attack — and
    the frame the ATTACK cursor wraps, `clr.b 31(a0)` at `$3fb0` puts it back in the glide. In the attack phase
    `16(a0) := $10`, it faces the followed record, animates over a `$3f` mask, and on the ONE cursor
    value `$14` drops a type-`$2b` record ten pixels to its own side and six above.

**AND SLOT 19 PUBLISHES A RECORD AS A SPRITE. IT IS THE ORIGINAL'S DEFECT AND IT IS REPRODUCED.**
`bsr $1b8e` returns the new record **in a1 — the very register the frame table was `lea`d into two
instructions earlier** — and the `lea 0(a1,d7.w),a1 / move.w (a1),6(a0)` below is reached from BOTH
arms. So on the frame the shot fires, the sprite published is the word at offset `$14` of the record
just allocated, which the spawn never writes; and **on a FULL POOL `a1` is 0** and the word comes
from address `$14`, inside the 68000 vector page four hundred bytes below the program. Two cases
drive the two halves, and the first asserts the keyed word differs from the table's before it
compares, so a seed that happened to agree could not pass as a proof.

**THE HURT TAIL NOW COMES IN THREE ORDERS, and the second one is this batch's.** Slots 14, 17 and 18
spell batch 35's `bclr #0,9(a0) / btst #3,9(a0) / bne.w $6bb8`; **slots 15 and 16 read the two marks
the OTHER way round** — `btst #3,9(a0) / bne.w $6bb8 / bclr #0,9(a0)` — so a record that transfers
arrives at `actor_defeat_and_score` **still marked hurt**, where the other three arrive with bit 0
down. Slot 19 is neither: its wrap is `bclr #0,9(a0) / bra.w $6bb8`, unconditional, the family's
second certain death after slot 13's. `FAMILY36_HURT` states the order per slot and one parametrised
case asserts what each leaves BEHIND the transfer — a case that only checked "the defeat ran" would
pass against all three spellings.

**AND TWO HANDLERS SPLIT THE STRUCK ARM, which no earlier handler in the tier does.** Slots 18 and
19 put `bsr $67c2` on the overlap-POINT branch ALONE (`$3cc0`, `$3ec8`), above the join a shot hit
enters from below — so **a monster shot from a distance takes the hit facing wherever it was, and one
struck by the player's reach point turns to face first**. Slot 17 faces on both arms and slots 14, 15
and 16 on neither. `src/behavior.c`'s `monster_contact` therefore reports WHICH test struck as a
FOURTH ENUMERATOR, `MONSTER_STRUCK_BY_POINT`, and all seventeen switches over it name both struck
values — the fifteen that do not care put them on one arm, and the two that do spell a documented
fall-through. *(The first draft of this batch used an optional out-parameter with fifteen `NULL`
callers; the review gate replaced it, for the reasons the gate's own section below gives, and this
paragraph is written from the shipped code rather than from that draft.)* Both arms are driven for
all six slots:
`test_the_family36_struck_arm_faces_on_the_arm_the_bytes_say` is twelve rows, and the POINT arm is
reached by placing the followed record so its reach point lands inside the actor's box while its own
body box stops short of it. The same two slots also `bchg #3,8(a0)` before the tail jump into
`actor_damage_followed`, which slot 3 does and nobody else here — and driving THAT needed
`_foreign_band` to learn a third model, `test_actor.py`'s own `_model_damage_followed`.

**THE SIBLING-TABLE RESIDUE, MEASURED AND CLOSED.** The reviewers noticed that where a handler's
two facing tables are CONTIGUOUS, `table + mask + 1` **is** `sibling + 0` — so an over-read row
seeded exactly one table past cannot tell "raw index on the right table" from "masked index on the
SIBLING table", and its single-mutant coverage rests on the separate facing cases existing. The two
reviewers' row lists differed; reconciled against the image the true set is **five of thirteen**:
slot 15's walk and hurt, slot 16's walk, slot 19's attack, and slot 17's dx. (Slot 14's walk, slot
18's walk and slot 19's drift are NOT ambiguous — their neighbours hold different words — and the
three tables with no sibling cannot be.) Each of the five is now seeded at the smallest cursor that
gives three DIFFERENT words — `$20`, `$40`, `$50`, `$80` and `$100` — and the premise guard checks
all three readings rather than two, so a table that moves fails the row instead of quietly going
ambiguous again. Proved: the composite mutant (mask the index AND take the sibling table) is
**caught at all five**, and the plain mask-order mutants are still caught at the new cursors —
**8 of 8**.

**THE RAW-INDEX CONVENTION, DRIVEN AT ALL THIRTEEN OF THIS BATCH'S CURSOR READS — before the fact,
not after it.** Batch 35 had to retract three plates and three surviving mutants over this; here
every one of the thirteen sites has a case that seeds a cursor ONE WHOLE TABLE past the mask and
requires the answer to be the word at `table + RAW cursor`, with the stored cursor still masked. Ten
are publishes and three are deltas added to a coordinate. Each row asserts the over-read word
DIFFERS from the masked one first, so a site whose neighbour happened to repeat it fails as a case
that proves nothing rather than passing. The sharp ones: **slot 14's hurt arm at cursor `$10`
publishes `$0828`, the first opcode word of `actor_behavior_type15`**; slot 19's death arm at `$20`
publishes slot 20's; and **slot 17's y cursor at `$40` reads `actor_behavior_type18`'s own entry
opcode and ADDS 2,088 PIXELS TO THE Y.**

**THE CENSUS, RUN BEFORE THE FACT AND CHECKED BY FOUR CASES.** All 23 tables this batch names have
**exactly one `lea`** in the whole image, in both absolute encodings and the `lea d8(PC,Dn.w)`
displacement form (`CENSUSED_TABLES` now runs batch 35's fifteen and these twenty-three together).
Three kinds of address needed their own statement, because a direct-reader census bounds direct
readers and nothing else:
  * **slot 17's FOUR frame lists (`$3b78`, `$3b8a`, `$3b9c`, `$3bae`) are named by NO instruction at
    all** — they are reached by DEREFERENCE, `movea.l (a1),a1` inside `$3006`, and the case states
    both halves: no `lea` and no control-flow site names them, AND each is held by exactly one of
    the two pairs' four longwords;
  * **the two GLOBAL cursors have exactly TWO absolute sites each** — one `move.w <abs>.l,d0` and
    one `move.w d0,<abs>.l`, both inside slot 17's own extent, which is what says nothing else in
    the image steers the drift;
  * **the six ENTRIES are reached only through the dispatch longword.** A new whole-image scan
    resolves every control-flow form — `Bcc`/`BSR`/`BRA` long and short, absolute `jsr`/`jmp`/`pea`/
    `lea` in both widths, and both PC-relative `lea` forms — and no instruction anywhere aims at any
    of the six; the only longword holding one is its own table slot. That is `_lea_sites` widened
    rather than a second copy of it, and the reason is batch 31's hidden `jsr $6f9e.w`.

**AND THE SCAN FOUND TWO INSTRUCTIONS OUTSIDE THIS BAND THAT AIM INSIDE IT.** `bra.w $3ae6` at
`$48b2` **enters slot 17's SEEDING block**, and `bne.w $3e2a` at `$4aa8` borrows slot 18's final
`rts` — both in handlers this port does not have. So **slot 17's body is not slot 17's alone**, the
same shape batch 31 recorded when the boundary moved inside a handler.
`test_the_only_foreign_entrances_into_this_band_are_the_two_the_plates_name` pins the pair exactly,
so whichever batch ports those rows finds the code already reconstructed instead of writing a second
copy of it.

**WHAT THE DE-DUPLICATION MOVED, and it reaches back into slot 6.** Four shapes were spelt twice or
more and are now one each: `publish_and_store_cursor` (eleven sites, publish + step + store in one
register), `walk_and_toggle` (slots 6, 14 and 18 — the `move.b`-left / `move.w`-right asymmetry and
`bsr $2b82`, in one place), `restore_flags_and_turn` (slot 6's `type06_restore_flags_and_turn` with
the reload as a parameter, now slot 18's too), and `spawn_companion` (slots 16 and 18 spawn the same
record bar the type word). Slot 3's walk keeps its own copy deliberately: it reads the facing for its
frame list BEFORE the toggle can turn the record, which is the whole difference between it and
slot 6.

**NOT PINNED, HONESTLY.**
  * **The `move.b #n,d7` left arms.** Slots 14 and 18 write a step into the LOW BYTE of the register
    `actor_fall_and_settle` left something in, and the port threads that register (`settle_span`) —
    but no case makes the high byte nonzero, so the two arms are only ever driven walking the same
    number of pixels. It is slot 3's and slot 6's unpinned edge, unchanged, and it is the same
    argument: `$13be` rewrites the low word before anything reads it, and nothing guarantees the
    high one.
  * **Which creature each of the six DRAWS**, and which the five spawn. They publish sprite ids and
    write type words out of tables this batch reads and does not identify; the slots are still
    `typeNN` and the minions are still `$2d`, `$27`, `$34`, `$29` and `$2b`.
  * **The registers each handler leaves behind**, as everywhere else in this tier.
  * **`WB_ACTOR_TYPE17_SEED_FIRST`'s meaning.** The five records are numbered 5..1 in `30(a1)` and
    what a consumer does with the ordinal is slot `$34`'s business, not established here.
  * **The refused dispatch**, as in every batch since 29.

**MUTATION SWEEP: 59 MUTANTS OVER TEN AXES, 53 CAUGHT FIRST TIME; FOUR OF THE SIX SURVIVORS WERE
REAL HOLES AND ARE CLOSED, ONE WAS A BADLY BUILT MUTANT AND ONE IS AN ARGUED EQUIVALENCE.** Pre-hoc
axes over all six bodies and the four hoisted helpers: the shared publish masked BEFORE indexing,
the defeat-first tail made clear-first, the shot arm made to report a point hit, the walk's two
probes exchanged and its byte step widened, the restore's turn dropped and its latch left standing,
the companion's flag copy and speed; slot 14's turn frame made to fall through, its turn count, its
gap armed on a refusal, its escort timer, its gap stepped early, its list chosen before the turn,
its step and its hurt mask, and its two countdown tests exchanged; slot 15's `$2b8e` made a `$2b82`,
its list chosen after the turn, its step, its tail order, its walk mask and its arms exchanged;
slot 16's facing moved below the list, its launch gate inverted, its supported bit left up, its
reload, its minion type, and its expiring timer made to skip the publish; slot 17's axis masks
exchanged, its odds inverted, its ordinals counted up, its burst continued past a refusal and
shortened, its x drift landed on the y, its seeding fired on a nonzero cursor, its facing dropped
and its cursor made a record field; slot 18's flag byte saved after the facing, its body arm's flip
dropped, its struck arm made to always face, its charge speed, its landing arm run in the air, its
defeated retreat unsuppressed, its step and its turn count; slot 19's latch value, glide sprite and
box heights, its shot's `a1` not reused, its cursor and its offsets exchanged, its death transfer
made conditional, its undefeated arm made to animate, its attack wrap made to stay, and both of its
masks.

**THE FOUR REAL HOLES, and three of them are ONE SHAPE — a mask whose seeds all answered the same
under either value.**
  * `slot17/axis-masks-exchanged` and `slot19/drift-mask` SURVIVED because every cursor those cases
    drove (0, `$10`, and the table's last entry) steps to the same byte under a `$7f` mask as under
    a `$3f` one. `$40` is the smallest cursor the two disagree about — `$42` against `$02` — and one
    row of it in each case catches both.
  * `slot17/live-arm-does-not-face` SURVIVED because every slot-17 seed left the record already
    facing the way `actor_set_side_flag` would leave it, so dropping the call changed no byte. That
    is batch 35's `slot13/side-flag-not-set-on-the-first-throe-frame` exactly; the new case seeds the
    OPPOSITE flag on both rows and checks the published list as well as the bit.
  * `walk/left-arm-takes-a-whole-word` SURVIVED — **and it is the edge slots 3 and 6 have carried
    UNPINNED since batch 33.** `move.b #n,d7` writes the low byte of the register
    `actor_fall_and_settle` handed back, and no case had ever driven that arm with a high byte in
    it. It IS drivable, and the lever is the settle's own EARLY EXIT: a record already MOVING is
    returned from untouched, so what comes back is the handler's entry d7 — the followed record's
    SPRITE word, which `_walk_pokes_for` states. With that word at `$300` the left arm steps `$301`
    pixels instead of one, the probe goes negative and `$10a2` parks the record at its own
    half-width, where the mutant leaves it one pixel over. Two rows (slots 14 and 18) now drive it,
    and **the batch-33 gap is retired for this helper.**

**ONE MUTANT WAS THE BATCH'S OWN MISTAKE, rebuilt and caught.**
`slot19/death-transfer-made-conditional` replaced the unconditional pair with
`monster_hurt_wrap_clear_then_test` — but that arm is only ever reached with the mark UP, so the
two are the same instructions for every state the guard above admits. What the bytes really say that
a port could get wrong is that **bit 0 goes DOWN before the transfer**, so the rebuilt mutant drops
the `bclr`. Caught. (Batch 35 recorded the same category with `slot10/anim-facing-read-before-the-turn`.)

**AND ONE SURVIVOR IS AN EQUIVALENCE UNDER THE ALLOCATOR'S CONTRACT, argued rather than asserted.**
`slot17/burst-continues-past-a-refusal` turns the burst's `return` into a `continue`.
`actor_alloc_slot_high` is a SCAN that hands back the first record whose x holds
`WB_ACTOR_FREE_MARKER`; it writes nothing and marks nothing, so once it has refused, every later
call in the same frame refuses too — the pool cannot gain a slot mid-burst. The two spellings
therefore differ only in how many times a routine that writes NOTHING is called, and the ordinal
byte cannot drift either, because `subi.b #$1,d6` sits below the refusal branch in both. The
consuming use is covered: nothing reads the loop counter after the burst, and the five records'
fields are written before any refusal can happen. The re-run of the five rebuilt/closed mutants is
**5 of 5 caught**, so the sweep's honest figure is **58 of 59, with one argued equivalence.**

**THE REVIEW GATE (high, eight finder angles, all of them READ-ONLY against a named backup) FOUND
TWENTY-ONE ITEMS AND CHANGED THE DESIGN ONCE.** Two of the angles were independent transcriptions of
the six routines from a freshly generated listing, and **both came back with no byte-behaviour
divergence** — the port is what the bytes are. Everything below is coverage, naming or a plate that
said something the image does not.

**THE DESIGN CHANGE: the struck-arm split is a FOURTH ENUMERATOR, not an out-parameter.** The first
draft gave `monster_contact` an `int *struck_by_poin…` that fifteen of seventeen callers passed
`NULL` to. Two angles independently argued the same thing from the bytes: at `$3cb8` the
overlap-point branch *falls through* `bsr $67c2` into the join the shot arm at `$3c9e` jumps
straight to, so "which test struck" is not extra information about one outcome — **it is the entry
point**, which is exactly what the enum models. And the out-parameter is the less safe encoding: it
defaults to "no", so the next handler that spells `bsr $67c2` on the point arm would be missed in
silence, where `MONSTER_STRUCK_BY_POINT` makes `-Wswitch` force its author to decide. All seventeen
switches now name both enumerators; the two that split spell a documented fall-through. The build is
`-Wall -Wextra` clean.

**FOUR CASES THAT COULD NOT FAIL, and the sharpest is the one this batch was proudest of.**
  * `test_two_slot17_records_drift_in_LOCKSTEP_through_the_shared_cursors` seeded both cursors at
    zero and required the second record to move by entry 1 of each table — **and both drift tables
    run in blocks of four equal words, so entry 1 IS entry 0**. The case demanded exactly what a port
    holding the cursors in the RECORD would produce. It now starts each cursor on the last entry of
    a block (`$06` and `$04`) and asserts the two entries differ before it compares.
  * `test_slot16_that_is_airborne...` claimed to pin the `bclr`'s store. It cannot: `bsr $67c2` runs
    on every live frame and ends in a `bset`/`bclr` of the same byte, so `8(a0)` is in the ledger
    whatever the `bclr` does. The case is renamed for what it does pin and says where the store is
    carried instead (the entry pin).
  * `test_slot17_stops_seeding_at_the_first_refused_allocation` was named for an exit no case can
    see — the same equivalence the sweep's own survivor argues — and is renamed to what it holds.
  * `test_slot19_publishes_from_ADDRESS_14...` lacked the premise guard its sibling has, and the word
    at `$14` is **zero**, so any port publishing a zero for any reason passed. Guarded now against
    both frame tables' words at that offset.
  * One more, weaker: the four rows of the body-arm case that expect NO flip were satisfied by the
    handler never writing the flag byte at all (`written.get(..., side)` reads "no write" as "did not
    flip"). Each row now first requires `actor_damage_followed` to have marked the followed record.

**AND THE INSTRUCTION CENSUS UNDER-REPORTED — the exact failure the two cases built on it exist to
rule out.** `_control_flow_targets` claimed "both PC-relative `lea` forms" and swept only the
INDEXED one, missing `lea d16(PC)`, `jsr`/`jmp`/`pea d16(PC)` and their indexed siblings, and every
`DBcc` (always a 16-bit displacement, and a branch); it also failed to sign-extend `abs.w` operands
and stopped eight bytes early. The answers were right today — the only edge the missing forms add
inside this band is slot 17's own `dbf $3afa`, which is in-band and therefore already excluded — but
a negative proved with an under-reporting scan is not a negative. **The two censuses are now ONE
scan**: `_lea_sites` is a lookup into `INSTRUCTION_TARGETS` rather than a second sweep with its own
(different) tail bound, the scan is bounded to `loader.PROGRAM_END` instead of decoding 900 KB of
uninitialised image as instructions, and the whole suite got FASTER for it — forty-four per-case
whole-image sweeps replaced by one.

**A HELPER THAT WAS DEAD ON ARRIVAL.** `_image_long` was added at line 4754 of a file that already
defines it at 7701; the later binding wins, so the new one never ran and an edit to it would have
been a silent no-op. Deleted.

**SEVEN PLATES SAID SOMETHING THE IMAGE DOES NOT, and in this project the plates are the
deliverable.** `restore_flags_and_turn` quoted slot 6's write order as if slot 18 had it too — `$3d48`
puts the `bchg` second and the `clr.b` last, and the fields are disjoint so nothing can go red on it;
both orders are now spelt out, with the note that the restore being FIRST is the one ordering that
matters. `spawn_minion` said its two writes are what every spawner "opens with"; slot 19 writes its
type fifth. The deletion of `type06_restore_flags_and_turn` orphaned its `$2cd0` plate on top of the
NEXT function, which then read as documentation of `$2ce6`; the addresses are back, on the shared
helper. `monster_contact` said "ten handlers", `monster_hurt_wrap_clear_then_test` "four of the
five", `step_away_without_facing` "three routines" and `step_over_low_byte` "slots 3 and 6…" — all
counts this batch itself invalidated. And **"WB_ACTOR_TYPE30_CURSOR is the tier's only other global
cursor" is false**: `WB_ACTOR_TYPE32_CURSOR` is a third, and `src/behavior.c` said so two thousand
lines above. Two more: `include/behavior.h` and `include/wonderboy.h` disagreed about whether the
hurt tail comes in two orders or three (three), and `src/behavior.c` had the seeding cadence the other way up — the y table is HALF the x one, so
the y cursor comes round TWICE per horizontal lap.

**AND THIS PARAGRAPH'S OWN FIX PASS FAILED SILENTLY, WHICH THE INDEPENDENT GATE FOUND BY GREPPING
THE FILE INSTEAD OF THE FINDINGS LIST.** Of the four corrections certified above, **one landed
(`step_away_without_facing`), one landed with its two numbers TRANSPOSED, and two never landed at
all.** The cause is one line of tooling: the fixes went in as a single scripted search-and-replace
whose only check was `assert s != before`, so a pattern that missed — `step_over_low_byte`'s began
` * ` where the file has `/* ` — was a silent no-op, and the certification was then written from the
review's findings list rather than from the file. The corrections are applied now, each asserted
individually, and **each verified by grepping the OLD phrase to ZERO across the tree**:

| retired phrase | sites then | now |
| --- | --- | --- |
| `every second …ap` | behavior.c, names.txt (+ this section quoting it) | 0 |
| `only other curso…` | behavior.c, STATUS narrative | 0 |
| `other ten in the fami…` | wonderboy.h | 0 |
| `Slots 3 and 6 both spe…` | behavior.c | 0 |
| `SIX hurt animation…` (transposed) | behavior.c | 0 |
| `for goo…` (slot 19) | behavior.h, behavior.c, names.txt | 0 |
| `arm ENDS there exactly as it ends on succes…` | behavior.c, behavior.h | 0 |
| `no way bac…` | behavior.c | 0 |

The true figures, re-derived rather than re-copied: the hurt tail is **SEVEN slots** (9, 10, 11, 12,
14, 17, 18) over **SIX call sites** in six bodies, because slots 9 and 12 share `gated_hurt_frame`;
`monster_contact` has **fifteen** callers that name both struck values on one arm and two that
split; and the `move.b` left arm is **four** slots — 3 in its own body, 6, 14 and 18 through
`walk_and_toggle`. **The rule that would have caught all of it is one grep**, and it is now in
`docs/methodology.md`: *a plate correction is landed when the OLD phrase greps to zero* — not when
the new phrase is present, and never when a findings list says so. The same section says not to let
a retraction QUOTE the retracted phrase, which is why the notes above describe the old claims rather
than repeating them.

**TWO MORE PLATES CONTRADICTED THE BYTES, and both are this batch's own headline material.**
  * **Slot 19 is NOT irreversible.** `include/behavior.h`, `src/behavior.c` and `../names.txt` all
    called the attack latch permanent — and `$3fac`/`$3fb0` is `bne.w` over
    `clr.b 31(a0)`, so the ATTACK cursor's own wrap puts the record back in the glide. The
    handler's own inline comment said so, and so did the passing case
    `test_slot19s_attack_wrap_puts_the_record_back_into_its_GLIDE`; three surfaces disagreed with
    two. All five now say the record ALTERNATES and neither latch is permanent.
  * **`spawn_minion`'s claim that every caller's arm ends on a refusal exactly as it ends on
    success is false at every caller, and most sharply at slot 19** — whose refusal does not end the arm at all but
    runs ON into the shared publish with `a1` at zero, which is this batch's headline defect and
    the subject of a whole `docs/m68k-disassembly.md` section written from the same bytes. Slot
    14's success also writes `WB_ACTOR_TYPE14_SPAWN_GAP` below the join, so even there the two arms
    are not the same frame. The plate now states the refusal per caller.

**AND THE INBOUND-EDGE RULE WAS NOT APPLIED TO ITSELF.** This batch added a methodology rule saying
that when an edge points into your span you must name the OWNER's plate — and then wrote the edges
into slot 17's and slot 18's plates only. `$48b2` falls inside **slot 24**'s extent (`cmt 0x484c`)
and `$4aa8` inside **slot 25**'s (`cmt 0x4916`), and slots 20..27 are the next batch. Both plates
now carry the edge, the helper to REUSE (`type17_seed_burst`; slot 18's shared `rts`) and the name
of the exact-set case that pins them, so the next batch finds the instruction already reconstructed
instead of porting it twice.

**TWO NAMES AND TWO CONSTANTS RENAMED.** `monster_recover_or_defea‥t` and `monster_defeat_or_recove‥r`
were word-swaps of each other with opposite semantics, callable interchangeably at nine sites with no
compiler complaint and a one-bit divergence as the only symptom; they are
`monster_hurt_wrap_clear_then_test` and `monster_hurt_wrap_test_then_clear`, which say the
difference. `WB_ACTOR_MINION_SIZE_6_…` named the digits of its own literal and is
`WB_ACTOR_MINION_SIZE`; `WB_ACTOR_TYPE17_SEED_LAS…` read as an inclusive bound that the code then had
to undo with `+ 1` and is `WB_ACTOR_TYPE17_SEED_DBF_COUNT`, with the `dbf` runs-COUNT+1-times rule in
its comment. `_family36_pokes`'s body was a no-op — it restated a cursor pin `_walk_pokes_for`
already makes — and now says honestly that it adds nothing but the absence of `WB_TILE_33_MODE`.

**AND ONE FINDING RETIRED A BATCH-33 GAP THE SWEEP HAD ALREADY OPENED.** The reviewers pointed out
that slot 3 has had a left-arm high-byte case since batch 33, so the sweep's "no case had ever driven
it" was true of the HELPER and not of the shape; slot 6, which this batch routed through
`walk_and_toggle`, was the one genuinely uncovered. `WALK_ARM_SLOTS` now drives 6, 14 and 18.

**THE GATE'S OWN MUTATION PASS: 11 OF 11 CAUGHT**, over the three shapes the enum refactor created
(a point hit reported as a shot, slot 18's point arm not facing, slot 17 facing on neither), the
renamed tail's order, the four holes the first sweep found re-run against their closed cases, the
rebuilt slot-19 death mutant, and two mutants aimed at the review's own new assertions (a second
record reusing the first's cursor; a body arm that damages nothing).

**TWO THINGS WENT INTO THE DURABLE DOCS**, because both are reusable and neither is about this game.
`docs/m68k-disassembly.md` gains **"a callee that RETURNS in the register a pointer was already
in"** — slot 19's defect generalised, with the three habits that catch it (write which registers a
callee RETURNS into its plate; suspect any join reached from both sides of an allocation; reproduce
rather than repair, and assert the published word DIFFERS from the one the obvious reading gives).
`docs/methodology.md` gains **"the extent is right and the body is still not yours"** — the inbound-
edge scan, which is the who-names-this-entry census asked about a whole RANGE, and batch 31's
"boundary moves inside the handler" seen from the callee's side. Its "read the plate first" rule
also records that batch 36 ran it as written and it held six times out of six.

**QUEUED — WHAT IS LEFT OF THE TABLE.** Nineteen rows: **slot 1** (the player), **slots 20..27** —
eight more of this family, still in blocks — **slot 38**, **slots 39..46** and **slot 57**. The order
stands: 20..27, then 38..46 and 57, and the player LAST. **And two of those rows now have a
prerequisite**: whichever batch ports the handler holding `$48b2` must reuse `type17_seed_burst`
rather than re-port `$3ae6`, and the one holding `$4aa8` must know its `rts` is slot 18's.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`); `actor_behavior_type46` ($58f2); the second reader of
`actor_type30_drift` at `$b84`; the three duplicate `cmt` directives (`0x1023a`, `0x10394`,
`0x1044c`); `scene_copy_record_fields` ($539e); the thirteen third-copy encoders due in `leaf.py`.

### Batch 37: dispatch rows 20..27 — THE MONSTER FAMILY CLOSES

**EIGHT ROUTINES, 2,604 BYTES, AND A NINETY-FOUR-BYTE LEAF — but only about nine hundred bytes of
new shapes.** Five of the eight are code this port already had, at another address:

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$4118` | `actor_behavior_type20` | 378 | CLEAN — the hopper that patrols, and the WORD turn test |
| `$42f2` | `actor_behavior_type21` | 362 | CLEAN — the sentry that AIMS: the family's only user of $6528 |
| `$44bc` | `actor_behavior_type22` | 264 | BOUNDED at `$e06` — the launcher, whose `bclr` re-arms an airborne record |
| `$461c` | `actor_behavior_type23` | 432 | CLEAN — the GOLD THIEF, and slot 4's body: it BRANCHES INTO IT |
| `$484c` | `actor_behavior_type24` | 150 | CLEAN — the shortest body in the family, and its tail is slot 17's |
| `$4916` | `actor_behavior_type25` | 424 | CLEAN — slot 18's charge again, one minion type over |
| `$4b1e` | `actor_behavior_type26` | 216 | BOUNDED at `$e06` — slot 12's chase, with a shot on the MOVING arm |
| `$4c5e` | `actor_behavior_type27` | 378 | CLEAN — slot 20's body, byte for byte |
| `$6528` | `actor_aim_velocity` | 94 | the aim table, and the leaf slot 21 needed |

**Verified 258, 33,154 bytes, 74.9 % of §0k's 44,262; `make test` 4,992** (4,812 before, and all 180 of the growth is
`test/test_behavior.py`, which stands at 1,378).
**51 of the table's 62 rows are live and ELEVEN remain**; `PORTED_SLOT_COUNT` holds the figure and a
case asserts it against the image's own table.

**THE PLATES WERE RIGHT AGAIN, EIGHT FOR EIGHT.** A difference of dispatch entries gives
474/458/352/560/202/520/320/474 bytes; the code is 378/362/264/432/150/424/216/378, and every one of
the eight `decoded code runs $x..$y` fields in [`../names.txt`](../names.txt) matched the bytes on
the first read. What the gaps hold is this batch's own tables — 1,236 bytes of them, every byte
accounted for in `BODY_SIZES` and in the plates.

**AND THE ENTRY PINS AGREE WITH THE IMAGE ON ALL 2,604 BYTES.** Each of the eight is re-assembled in
`test/test_behavior.py` from encoder primitives and compared against the loaded image, which is what
makes the readings below transcription rather than interpretation.

**SLOT 20 AND SLOT 27 ARE ONE ROUTINE, DUPLICATED.** Assembling slot 20's operands at slot 27's
entry reproduces slot 27's image bytes everywhere but **ten bytes in six runs**: the low halves of
four `lea <abs>.l` longwords (both high halves are zero) and the low bytes of two `move.w #imm`
words. So
`src/behavior.c` has ONE `hopper_frame` and two constant sets, and
`test_slots_20_and_27_are_the_SAME_body_with_six_operands_changed` asserts the run structure rather
than a byte count (a count matches by accident; a run structure does not).

  * **Slot 20/27 is the hopper that patrols.** A SUPPORTED record faces the followed one and runs
    `30(a0)` down; the reload fires on the frame `subq.b #1,30(a0)` goes **NEGATIVE**, not the frame
    the byte reaches zero, and then `btst #2` of a `rng_next` word SET vetoes the hop. The hop
    itself is `bra.w $2af2` — a TAIL jump — so that frame neither steps nor animates. Its turn test
    is the **`tst.w d0`** only slot 28 spells anywhere else in the tier, so a step blocked at a
    nonzero map column does not turn it. An AIRBORNE record publishes ONE sprite id instead of
    animating, and its cursor is never touched. **And its hurt wrap does `st 30(a0)` BEFORE the two
    mark instructions** — the only hurt tail in the family with a write of its own, and what makes a
    recovered record's very next live frame go straight to the reload and the draw.
  * **Slot 21 is the sentry that aims, and the ONLY handler in the family that never calls
    `actor_fall_and_settle`** — it does not fall, hop or step on any arm. `30(a0)` is a FLAG here
    and not a countdown: nothing steps it. Clear, it animates and `st 30(a0)` on the wrap arms it;
    set, a followed record within `$96` and a draw zero under `andi.w #$1f` fire an **AIMED** shot,
    whose `30(a1)`/`31(a1)` are the signed byte pair `$6528` returns for the vector out of row 6.
    `clr.b 30(a0)` runs ABOVE the allocation, so a refused shot still disarms the record — the
    OPPOSITE of slot 14's refused drop. And `clr.w d1` overwrites the returned dy on a level shot,
    which is observable only for a followed record to the LEFT: the level-RIGHT direction's own
    table entry is already zero, and the first draft of that case asserted nothing because of it.
  * **Slot 22 is the launcher, and its `bclr` is the test AND the write.** `bclr #2,8(a0) / beq` on
    a zero countdown: a supported record reloads, raises two bits and writes its speed INLINE; an
    AIRBORNE one stores its flag byte unchanged and falls into `subq.b #1,30(a0)`, **wrapping the
    countdown to `$ff`** rather than merely skipping the launch. Below that it animates and, while
    `actor_type53_alive` is clear and one draw in eight, drops a type-`$35` record carrying the
    parent's flag **WORD** (`move.w 8(a0),8(a1)`, so `9(a0)` crosses too).
  * **Slot 23 is the GOLD THIEF — and slot 4's body.** Its live arm and its death arm are
    `actor_behavior_type04`'s instruction for instruction, so `hover_chase_frame` and
    `hover_death_frame` serve both. **It does not end in its own body**: `bra.w $2840` at `$46fe`
    leaves for slot 4's publish-and-hover tail. Only the footprint arm is its own: it charges `$10`
    out of `bcd_counter_bd6e` and drops a type-`$2e` record carrying it — unless the followed record
    is already flickering or its purse is empty, in which case the frame is an ordinary
    `actor_damage_followed`. `cmpi.w #$10 / bgt` is SIGNED and the two arms are not one clamped
    subtraction: above the maximum the counter is charged in BCD, at or below it the whole word is
    `clr.w`ed. **And `move.b #$64,21(a1)` sits BELOW the failed-allocation branch**, so a full pool
    writes it at address `$15` — slot 19's defect one handler on, reproduced rather than repaired.
  * **Slot 24's tail is slot 17's.** Five calls and then `bra.w $3ae6`, so `type17_seed_burst` is
    CALLED rather than re-ported — the obligation batch 36 pinned from the other side, honoured and
    driven (`test_slot24_runs_SLOT_17s_seeding_burst_as_its_own_tail` requires five seed records of
    slot 17's own type, numbered down from `WB_ACTOR_TYPE17_SEED_FIRST`). Both of its `$3006` PAIRS
    hold the same list twice, so the facing that routine reads decides nothing here.
  * **Slot 25 is slot 18's charge**, one minion type over, and **one of its exits is slot 18's
    `rts`** — `bne.w $3e2a` at `$4aa8`, the second obligation batch 36 pinned. The port simply
    returns there; `TYPE18_RTS` is derived from slot 18's own first frame table rather than
    transcribed, so a body that moved would carry it.
  * **Slot 26 is slot 12's chase with one instruction added**: the frame list is chosen by
    `btst #0,8(a0)` — the MOVING bit — where slot 12 reads the SUPPORTED one, and the shot hangs off
    the SAME branch, so a refused allocation still plays the moving list. The bit is read AFTER the
    tick that can raise it.

**THE STRUCK-ARM SPLIT IS NOW A THIRD OF THE FAMILY.** Through batch 36 only slots 18 and 19 put
`bsr $67c2` on the overlap-POINT branch alone; slots 20, 21, 25 and 27 do it too (`$414a`, `$432e`,
`$4952`, `$4c90`). Slots 22, 24 and 26 face on BOTH arms, with the call BELOW the two writes, and
slot 23 on neither. `FAMILY37_STRUCK_FACES` states the pair per slot and sixteen rows drive it.

**THE CENSUS, RUN BEFORE THE FACT — AND IT CORRECTED A PLATE.** All 27 tables this batch names have
exactly ONE `lea` in the whole image over both absolute encodings and both PC-relative forms, except
slot 23's two fly tables, which have TWO each for the same structural reason slot 4's do (one `lea`
on the LEVEL branch and one on the stepping branch) — stated as its own case rather than as an
exception to the rule. **And `actor_type04_hover_deltas`' plate counted ONE reference and there are
TWO**: `lea $296c.l` at `$2864` in slot 4 and **`lea $296c.w` at `$4746` in slot 23** — the SHORT
absolute encoding, from another handler. That is batch 34's `$5160` miss at a different address, and
`test_slot_4s_hover_table_has_TWO_operand_sites_and_the_second_is_SLOT_23s` re-runs it.

**THREE INSTRUCTIONS INSIDE THIS BAND AIM OUT OF IT, and each lands inside another handler's body.**
`$46fe -> $2840` (slot 23 into slot 4), `$48b2 -> $3ae6` (slot 24 into slot 17) and
`$4aa8 -> $3e2a` (slot 25 onto slot 18's `rts`).
`test_the_only_foreign_exits_from_band37_are_the_three_the_plates_name` pins the exact set — and
building it found a trap worth recording: **a linear sweep over a band that holds frame tables
decodes data words as instructions**, and three of this band's data words happen to encode
`lea <abs>.w`. Filtering by opcode to the transfer forms is what keeps a phantom out of an exact-set
assertion.

**A BCD ENTRY EXTEND THAT IS PROVABLY DATA DEPENDENT, and the fourth THREADED site.** Slot 23's
`bsr $b582` at `$4678` reads whatever X the run left. Nothing between it and
`actor_followed_overlap_mask`'s return writes X — `btst`, `tst.w`, `cmpi.w`, `move.w #imm`, and
`$67e0`'s whole body is `tst.w` / `lea` / `rts` — so the bit is the LAST arithmetic on the only path
to `$5c6e`'s single `rts` at `$5d60`: `subi.w #$9,d6` on the followed record's y for the two sprite
ids that have a reach point, and `addi.w #$16,d5` on its x for every other sprite. Both are data
dependent, so `overlap_mask_exit_extend` computes the bit from the same two words rather than
claiming a zero that is wrong for any followed record above `$ffe9` or below y 9.
[`include/hud.h`](include/hud.h)'s audit block carries it as a FOURTH threaded site and
`docs/m68k-disassembly.md` gains the general procedure.

**THE RAW-INDEX CONVENTION, DRIVEN AT ALL NINE OF THIS BATCH'S OWN FRAME READS.** Eight direct
publishes and slot 23's hover cursor, each seeded ONE WHOLE TABLE past the mask, each requiring the
word at `table + RAW cursor` with the stored cursor still masked. `_over_read_cursor` picks the
smallest even cursor at which the RAW word, the MASKED word and the SIBLING table's masked word are
three DIFFERENT values, so the sibling-table residue batch 36 measured cannot come back: a row that
went ambiguous would fail its own premise guard rather than pass quietly. The four `$3006`-driven
arms (slots 22, 24, 26 and slot 21's hurt) index through the shared helper, whose sites batch 36
pins.

**WHAT THE PARAMETRISATION MOVED.** `type04_death_frame` became `hover_death_frame` and slot 4's
live arm became `hover_chase_frame` (both now serve slot 23); `type18_hurt_frame`, `type18_charge`
and slot 18's whole body became `charger_hurt_frame`, `charger_charge` and `charger_frame` over a
`ChargerFrames` row (slot 25's too); slots 22 and 26 call slot 9's `gated_hurt_frame` unchanged; and
slot 24 calls `type17_seed_burst`. What is genuinely new in `src/behavior.c` is `hopper_frame`,
slot 21, slot 23's theft, slot 26's shot and `overlap_mask_exit_extend` — and, in `src/actor.c`,
`actor_aim_velocity`.

**`actor_aim_velocity` ($6528), and the flag trick inside it.** Sixteen directions per row, chosen
by folding both deltas into the first quadrant and measuring the ratio in three steps. The
`asr.w #1,d2` at `$655c` leaves the bit it shifted out in X and the `roxl.w #1,d2` at `$6564` puts
it back — an exact halve-and-restore — **except when the `addq.w #1,d4` between them runs**, which
overwrites X with its own (always zero) carry and drops the low bit. That asymmetry is behaviour,
not noise, and the port reproduces it; two mutants pin it from both sides.

**NOT PINNED, HONESTLY.**
  * **`actor_aim_velocity` has no ENTRY PIN**, where every behaviour body in this file does. Its
    shifts, `exg`s, `eori`s and `movem`s need eight encoders no other body here spells, and what
    pins it instead is a differential entered at the leaf's OWN address (five rows, including the
    three overflowing operand pairs slot 21's reach gate cannot produce) plus six geometries through
    slot 21 and nine mutants. It is the only routine this batch adds whose bytes are not
    re-assembled and compared, and the queue below carries the obligation.
  * **The two BOUNDED hurt arms.** Slots 22 and 26 stop at `WB_PLAYER_STEP_BODY` whenever
    `WB_TILE_33_MODE` is clear, which is the ordinary state — the same limit slots 9 and 12 carry,
    and it retires when the player tier lands.
  * **Which creature each of the eight DRAWS**, and which the four spawn. The slots are still
    `typeNN` and the minions are still `$2c`, `$35`, `$2e`, `$2a` and `$33`.
  * **What reads `WB_ACTOR_FIELD_21`.** Slot 23 is the only writer read so far; the byte's consumer
    is not established, so "stun frames" is the write's shape and not its meaning.
  * **The rows of `actor_aim_velocity_table` above row 6.** Only slot 21's row is read by ported
    code; what bounds the table is slot 45's business, and slot 45 is unported.
  * **The registers each handler leaves behind**, as everywhere else in this tier.
  * **The refused dispatch**, as in every batch since 29.

**THE INDEPENDENT GATE (two reviewers) FOUND ONE REAL MODELING DIVERGENCE, THREE MUTATION-PROVEN
COVERAGE HOLES AND A STALENESS SWEEP — and the first is a defect in the shipped C.**

**`$6528`'s TWO SIGN TESTS ARE NOT THE SAME TEST, and the first draft spelt them alike.**
`sub.w d0,d2 / bge.s $6548` at `$653e` reads **N^V** — the EXACT signed comparison of the two
operands — where `tst.w d3 / bge.s` at `$6548` clears V first and so reads the SIGN OF THE WRAPPED
DIFFERENCE. The two part exactly when the x subtraction overflows (`to_x` `$7fff`, `from_x` `$ffff`:
the difference is `$8000`, whose sign bit is set, and BGE is still taken), and the port folded the
delta the wrong way round there. `aim_direction_code` now takes the branch's own answer as a
parameter, and the battery's model — which had repeated the same shortcut, so it could not have
caught it — derives the branch from N and V rather than from a comparison.

**AND THE DIVERGENCE IS NOT DRIVABLE THROUGH SLOT 21, which is why the leaf is now entered
DIRECTLY.** `WB_ACTOR_TYPE21_REACH` bounds `|to_x - from_x|` to `$96`, and overflow needs a true
difference past `$7fff` — so no frame of the only ported caller can reach it. `actor_aim_velocity`
is exported, so `_run_aim` binds it with `leaf.bind` and enters it at its own address with d0..d4,
comparing the ORACLE's returned d0/d1 against the port's out-params; it writes no memory at all, so
those two registers are the whole surface. Four rows drive three overflowing operand pairs and a
control, and a fifth pins that the five registers' HIGH HALVES cannot reach the answer — which is
what lets the C take whole registers and truncate at each word operation, the kit's own rule.

**THREE ARMS THAT NO CASE HAD EVER REACHED**, each found by a mutant that survived the whole suite:
  * **Slot 23's in-reach LIVE arm.** `_walk_pokes_for` parks the followed record at `$0600` —
    outside `WB_ACTOR_CHASE_REACH` — and `_thief_pokes` overlaps it into the TOUCHED arm, so every
    slot-23 case ran either the hover alone or the theft, and exchanging the two fly tables and
    widening the step both survived. Two rows now close on a record inside the reach and clear of
    the actor's box (its y is far below, which the reach test does not look at), one per facing.
  * **The `bra.w $2840` path itself.** An EQUAL x is the only state that takes it — and an equal x
    also leaves the side bit clear, since `bsr $67c2` raises it only where the actor is STRICTLY to
    the right — so one seed is the whole path. This batch's headline reuse claim is now EXECUTED on
    both cores rather than only asserted about the bytes: the frame steps nothing, publishes out of
    slot 23's own table through slot 4's instructions, and hovers on slot 4's table below them.
  * **`overlap_mask_exit_extend`'s reach-point arm.** Every thief row hard-seeded the followed
    record's sprite to 0, so only the `addi.w #$16` arm ever ran and `return 1` outright survived.
    Two rows now put `WB_FOLLOWED_SPRITE_POINT_LO` on the record and drive `subi.w #$9,d6`'s borrow
    both ways, one unit of gold apart.
  * **And the `(+dx,+dy)` fold quadrant of the aim was uncovered** — the only `(+, >= 0)` row
    degenerated the ratio at `dy = 0`. `(+$40,+$18)` and its odd-delta variant are two more rows on
    the aimed-shot case.

**ITEMS 1..4 ARE PROVEN BY MUTANT: 9 of 9 red.** `aim/first-test-as-plain-sign` and
`aim/first-test-as-plain-comparison-of-deltas` (the two spellings the draft could have had),
`aim/dy-eor-dropped`, `aim/high-halves-reach-the-answer`, `slot23/fly-tables-swapped`,
`slot23/fly-step`, `slot23/level-arm-steps-anyway`, `extend/point-arm-never-taken` and
`extend/always-one`.

**THE STALENESS SWEEP, AND EVERY CORRECTION CERTIFIED BY ITS OWN GREP.** Batch 36's lesson was that
uncertified corrections are where the silent no-ops live, so the count is recorded per correction
rather than for the pass:

| retired phrase | sites now |
| --- | --- |
| the hover table's reference count | 0 |
| `monster_contact`'s split census | 0 |
| `step_away_without_facing`'s caller count | 0 |
| `gated_hurt_frame`'s caller list | 0 |
| the struck-split's "other fifteen" | 0 |
| `$5c6c`'s unread reader | 0 |
| `walk_and_toggle`'s slot list | 0 live (1 in batch 36's own dated section) |
| `$6528`'s name | 0 |
| `$6528`'s byte count | 0 |
| the `tst.w` census, in `../names.txt` | 0 |
| the `tst.w` census, on the helper's plate | 0 |
| the `tst.w` census, in the hopper's body | 0 |
| the hurt-wrap slot count | 0 |
| the hurt-wrap sibling's count | 0 |

The three the gate found on top of this batch's own seven: **`$6528` is 94 bytes and not 92**
(`$6586 - $6528 = $5e`, and four other surfaces already said so); **the `tst.w` turn test is no
longer the tier's ONE** — three dispatch rows spell it over two call sites, slot 28 in its own body
and slots 20 and 27 through the shared `hopper_frame`; and the **hurt-wrap tail is FOURTEEN slots
over NINE call sites**, not seven over six, the figure taken from a grep of the call sites rather
than from a running tally (four of the nine are shared: `gated_hurt_frame` carries 9, 12, 22 and 26,
`charger_hurt_frame` 18 and 25, `hopper_hurt_frame` 20 and 27). `PORTABILITY.md` §1565 carried the
retracted name and reading for `$6586` and now names `actor_aim_velocity_table` and says what the
routine does NOT do. And the hover retraction QUOTED the phrase it was retracting — both halves
greppable, which is exactly what the methodology rule forbids — and now describes it instead.

**QUEUED — WHAT IS LEFT OF THE TABLE. THE MONSTER FAMILY IS WHOLE.** Eleven rows, and not one of
them is another monster: **slot 1** (the player, the largest subtree behind the table), **slot 38**,
**slots 39..46** and **slot 57**. The order stands: 38, then 39..46 and 57, and the player LAST.
`scene_copy_record_fields` ($539e, 30 bytes) is still queued with `player_pending_event_gate`
($b1a), which is the row that reaches it.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`); `actor_behavior_type46` ($58f2); the second reader of
`actor_type30_drift` at `$b84`; the three duplicate `cmt` directives (`0x1023a`, `0x10394`,
`0x1044c`); `scene_copy_record_fields` ($539e); the thirteen third-copy encoders due in `leaf.py`.
**NEW, AND IT IS AN OBLIGATION RATHER THAN A NICETY**: `actor_aim_velocity` ($6528) has no ENTRY
PIN. Giving it one needs eight encoders no body in `test/test_behavior.py` spells — `movem.l` both
ways, `asl.w`/`asr.w`/`roxl.w` by an immediate, `exg`, `neg.w`, `eori.w`, `adda.w` and
`move.b (An)+,Dn` with `ext.w` — and it is due NEXT-BUT-ONE, because behaviour slot 45 is the
leaf's second caller and sits in the 39..46 block. It goes in this list because the queue is the
only mechanism that survives a batch boundary; the `$3ae6`/`$3e2a` edges are this batch's own proof
that it works.

**MUTATION SWEEP: 42 MUTANTS OVER ELEVEN AXES, 35 CAUGHT FIRST TIME; FIVE OF THE SEVEN SURVIVORS
WERE REAL HOLES AND ARE CLOSED (the re-run of the five, plus four rebuilt or added while closing
them, is **9 of 9**), AND TWO ARE EQUIVALENCES — one PROVED and one argued. The honest figure is
therefore **40 of 42, with two equivalences**.** Pre-hoc
axes over all eight bodies and the leaf: the hopper's reload boundary, its rng veto, its hop speed
and walk step, its WORD turn test, its airborne sprites and walk lists exchanged, its hurt latch
dropped, its retreat suppression inverted and made a toward-step, its two facing calls dropped and
slot 27 given slot 20's tables; slot 21's idle latch, reach, odds mask, the order of its flag clear
against its allocation, its level dy and its aim row; the aim leaf's low-bit restore both ways, its
two quadrant `eori`s exchanged, its second `exg` dropped and its two deltas reversed; slot 22's
supported gate, its airborne wrap, its type-53 veto, its minion flag WORD and its reload; slot 23's
purse compare made inclusive, its two refusals dropped, its stun write guarded, its entry extend
forced clear and its death tables exchanged; slot 24's burst dropped and its step changed; slot 25
given slot 18's minion type and its whole table set; slot 26's list select moved to the supported
bit, its shot moved to the other arm and its two calls exchanged.

**THE FIVE REAL HOLES.**
  * `hopper/word-turn-test-becomes-byte` SURVIVED because every hopper case walked a CLEAR row.
    Closed by the pair slot 28 already carries one handler over: a step blocked in map column 0
    reports `$0000` and turns the record, and a LEFT probe that runs off the map reports the probe's
    negative cell index — `$ff00`, whose outcome BYTE is still "blocked" — and does not.
  * `type21/odds-mask` SURVIVED because every draw the cases reached was zero under BOTH `$1f` and
    `$f` or nonzero under both. `_tick_that_draws` generalises the tick scan to any predicate, and
    the separating draw is one whose low five bits are exactly `$10`.
  * `aim/low-bit-never-restored` SURVIVED because none of the aimed geometries then in the file
    reached the second ratio test with an ODD delta. A sweep of the model over ±100 pixels found the family that
    does; `(-99, +98)` is the row, and it lands on a different direction entry.
  * `type23/bcd-entry-extend-forced-clear` SURVIVED because every thief seed sat at an x whose
    `addi.w #$16` does not carry. Two rows now drive the followed record at `$0100` and at
    `$10000 - WB_ACTOR_POINT_RIGHT`, and they differ by ONE unit of gold — which is what says the
    bit is threaded and not assumed.
  * `type23/dead-tables-swapped` SURVIVED because **slot 23's death arm had no case at all**. Two
    rows now drive the recoil AWAY out of the table the same branch picked.

**AND TWO SURVIVORS ARE EQUIVALENCES, with the argument covering the consuming store.**
  * `aim/low-bit-always-restored` is **provable**, not merely unobserved. The restored bit only
    changes `far_axis` on the arm where the `addq` clobbered X — and that arm is entered exactly
    when `near_axis < far_axis/2`, so `near_axis` is below both `2*(far/2)` and `2*(far/2)+1`, and
    below both again after the `asl`. Every later compare therefore answers the same, the direction
    code is the same, and a sweep of the model over ±300 pixels finds no geometry at all where the
    two spellings part. It is reproduced faithfully because the bytes say so, and recorded here as
    unobservable rather than as pinned.
  * `type26/step-order-tick-before-face` exchanges `actor_face_and_step_toward` with
    `actor_tick_timer30`. Their read/write sets are disjoint on everything the frame consumes: the
    map probes read only x, half-width, type and the map, and the tick writes none of those; the
    tick reads `30(a0)` and the SUPPORTED bit, and the step writes neither; and both touch `8(a0)`
    as BIT operations on disjoint bits, so the byte's final value is the same in either order. The
    consuming use is covered — the list select below reads the MOVING bit, which the tick raises in
    both spellings. Slot 12 has carried the same pair since batch 35 and is the same argument.

### Batch 38: dispatch row 38 — THE PICKUP TIER, and a second dispatch behind a handler

**SIXTEEN ROUTINES, 756 BYTES, AND THE FIRST TABLE ROW WHOSE FRAME DISPATCHES AGAIN.**

| address | name | bytes | where |
| --- | --- | --- | --- |
| `$5408` | `actor_behavior_type38_pickup` | 236 | CLEAN — the collectable whose payout is a table lookup |
| `$6938` | `text_post_bonus_points_a4be` | 82 | the five digits it patches into message 16's own string |
| `$105e4` | `pickup_effect_none` | 2 | a bare `rts`, and the byte that bounds the table |
| `$105e6` | `pickup_effect_grant_bbc4` | 26 | the ONE grant that posts no message |
| `$10600` | `pickup_effect_grant_wing_boots` | 26 | message 82 |
| `$1061a` | `pickup_effect_grant_helmet` | 26 | message 88 |
| `$10634` | `pickup_effect_grant_gauntlet` | 26 | message 92 |
| `$1064e` | `pickup_effect_grant_revival` | 26 | message 93 |
| `$10668` | `pickup_effect_grant_fire_balls` | 34 | message 94 |
| `$1068a` | `pickup_effect_grant_bombs` | 34 | message 95 |
| `$106ac` | `pickup_effect_grant_wind_spouts` | 34 | message 96 |
| `$106ce` | `pickup_effect_grant_lightning` | 34 | message 97 |
| `$106f0` | `pickup_effect_refill_meter` | 36 | no message — it CANCELS the bonus box |
| `$10714` | `pickup_effect_add4_meter` | 50 | ...and it is NOT the clamped add at `$10296` |
| `$10746` | `pickup_effect_bump_attack_level` | 44 | message 99 |
| `$10772` | `pickup_effect_vanish_followed` | 40 | message 100 |

**Verified 274, 33,910 bytes, 76.6 % of §0k's 44,262; `make test` 5,140** (4,992 before, and all
148 of the growth is in the two batteries this batch touched: `test_effects.py` goes 160 -> 238 and
`test_behavior.py` 1,378 -> 1,448).
**52 of the table's 62 rows are live and TEN remain**; `PORTED_SLOT_COUNT` holds the figure and a
case asserts it against the image's own table.

**THE PLATES WERE RIGHT ON THE EXTENT AND WRONG ON TWO READINGS.** A difference of dispatch entries
gives slot 38 236 bytes and the code is 236 — the first row in this tier whose extent holds NO data
at all, because this handler ships no frame table. But `$6938`'s plate named the WRONG address
register for its `lea` and the wrong DIGIT COUNT for the unpack below it, and the bytes give **a6**
(`4df9 0000a4be`) and **five** characters. Both are corrected, and both are now pinned: the entry pin re-assembles all 82 bytes and the differential
compares the five characters against an independent model.

**WHERE THE HANDLERS LANDED, AND WHY.** The fourteen went into `src/effects.c` and
`test/test_effects.py` rather than into the behaviour files, which is the OPPOSITE call from
`sound_request_9`'s and rests on the same rule read the other way. Their addresses sit in the effect
band, not the behaviour band; every one is a straight-line leaf whose whole surface is a word or two
of game state, which is exactly the seeding `test_effects.py` already owns (a destination to
overwrite, a write pointer, a meter either side of its maximum); and four of them are
`effect_push_record`'s own three instructions pushing the SAME four record words. Slot 38's own
frame — the arithmetic that reaches them and the refusal when it does not — is `test_behavior.py`'s.

**WHAT SLOT 38 IS.** A collectable, and its waiting arm is slot 31's: `actor_fall_and_settle`,
`actor_hop_ascend_step`, then `WB_ACTOR_FIELD_12` run down as a BYTE that expires TWICE — slot 28's
shape, where the `bne` after `bset #6,8(a0)` reads the bit the `bset` has just overwritten, so the
first expiry raises the flicker and reloads `$14` and the second leaves for `actor_defeat_and_score`.
Its idle arm splits on the KIND byte: a pickup kind is given `$ff` frames while `state_flag_a32` is
set and nothing at all while it is clear, and a gold kind either relaunches (kind byte zero) or
publishes through `actor_select_sprite_by_flag`.

Its COLLECT arm is what is new. The SFX request is spelt INLINE (`jsr 56(a1)` where
`sound_request_9` has a `jmp`), so this handler is **not** one of that routine's five callers and
the C spells `snd_call_trigger_effect` directly rather than calling it. Then `cmpi.b #$2,20(a0)`:

  * **below the threshold the record pays GOLD**, through the same five calls
    `hud_award_gold_from_descriptor` makes but with `stage_number` as the amount instead of the scene
    descriptor's award. The two are now ONE function, `pay_gold_award`, with the amount as its
    parameter — a difference of two instructions at the top and a `bra.w` at the bottom.
  * **at or above it the KIND ROW decides.** A nonzero `WB_ACTOR_KIND_SCORE` longword goes into
    `bcd_add_score_bd70` AND into `text_post_bonus_points_a4be`; `WB_ACTOR_KIND_PICKUP_EFFECT` then
    indexes `pickup_effect_table`.

**AND THE COMPARE IS SIGNED, WHICH IS WHAT BOUNDS THE ROW INDEX.** `cmpi.b #$2,20(a0) / bge` reads
N^V on a BYTE, so a kind of `$80..$ff` is NEGATIVE and takes the gold arm — the kind arm runs only
for 2..127 and its read lands within 2032 bytes of the table. That is the OPPOSITE of the tier's
other reader: `actor_respawn_as_new_kind` bounds its kind at neither end. `../names.txt`'s `$1044c`
plate now says both things, in one directive.

**THE SECOND DISPATCH IS THE STATE-65 CLASS, AND THE REFUSAL IS A CODE.** `move.w 10(a1),d0 /
add.w d0,d0 / add.w d0,d0 / movea.l 0(a1,d0.w),a1 / jsr (a1)` — the scale wraps in SIXTEEN BITS and
the extension word then sign-extends, so entry `s` is reached by `s`, `s+$4000`, `s+$8000` and
`s+$c000`: **56 of the 65,536 index values dispatch and 65,480 refuse**, and a guard on the raw
index would have refused 42 of the 56. An eight-shard enumeration drives every one of them against
the reconstruction alone, which is the only surface a refusal has (the original reads a longword
outside the table and `jsr`s through it).

The answer for a refused index is a FOURTH dispatch code, `WB_ACTOR_DISPATCH_PICKUP_REFUSED`, and
not the address slot 7's state `jsr` reports. The reason is measured rather than assumed: the span
this index reads is ordinary data and holds zeros, and `0` is `WB_ACTOR_DISPATCH_RAN`. A case checks
the image's own fourteen longwords against all four codes, and a second case checks that the
longword below the table really is zero — which is the fact that rules the address out. The
"writes nothing" half is driven too: two refused indices whose target longwords DIFFER leave images
that are identical everywhere but the index word the case seeded.

**WHAT THE FOURTEEN HANDLERS ARE, AND HOW THEY GOT THEIR NAMES.** Every one but the bare `rts` ends
`move.b #id,$c030.l / move.w #$32,$c034.l`, and that id is the evidence: batch 17 identified the
helmet and the gauntlet slots from the messages their own paths post, and this batch applies the
same method to twelve more. Two of them IDENTIFY a HUD slot that had no meaning at all —
`$bbc2` is the **Wing Boots** and `$bbc6` the **Revival Medicine** — and two more are a second
witness for batch 17's helmet and gauntlet (that batch read the BREAK message, this one the grant).
The four appends push the SAME four words `effect_push_record_0605/0508/0705/0803` push from the
other dispatch table, and the messages name them: **Fire Balls, Bombs, Wind Spouts, Lightning**. So
`effect_record_list` is an INVENTORY of those four items, the two tables grant the same four, and
`src/effects.c` now spells the four record words ONCE, as `wonderboy.h` constants both call sites
read.

**THREE OF THE FOURTEEN POST ID 0, AND THAT IS A CANCEL RATHER THAN A SILENCE.** `text_run_message_box`'s
first arm needs a nonzero request, so a zero posts nothing — but the score arm has already posted
`WB_TEXT_MESSAGE_BONUS_POINTS` a few instructions earlier, so a scored pickup whose effect is
`$105e6`, `$106f0` or `$10714` takes the bonus box back down before it is ever composed. Reproduced,
not repaired.

**`pickup_effect_add4_meter` IS NOT `effect_add4_clamped_b6fa` AT ANOTHER ADDRESS.** Both compute
`hud_meter_value + 4` and both branch on `bgt` against the maximum; that one then CLAMPS and this one
just SKIPS the store, so a meter within 3 of full is left exactly where it was. Same shipped-bug
class as slot 30's missing store. The case that separates them is an ABSENCE — a raise past the
maximum must write the word not at all — because a case comparing only the final value would pass
for either routine.

**`pickup_effect_vanish_followed` IS THE ONE HANDLER WITH A CALLEE**, and its `jsr $67e0.w` is the
SHORT absolute form, the encoding batch 31's hidden caller hid in. What it writes is `$69fe`'s own
damage-flicker state at its maximum: `WB_ACTOR_FLICKER_COUNTDOWN` full,
`WB_ACTOR_FLAG_FLICKER_BIT` (which makes the projection publish no sprite) and
`WB_ACTOR_FLAGS2_INVULNERABLE_BIT` (which makes `$69fe` return without writing anything at all). The
message is "Vanished !", and the three writes are why. **It also establishes a READER for offset 21**,
which batch 37 listed as not established: `$f14` ticks the byte down under `btst #6,8(a0)`, and this
is the one writer that raises that bit beside it. Behaviour slot 23's `$64` into the same offset does
NOT, so whether that one is ever ticked depends on the record's flicker bit having been raised
elsewhere — the honest half of the retirement.

**`pickup_effect_bump_attack_level` RESOLVES THE `$b444` TENSION rather than dissolving it.** The
compare is SIGNED, so the `$ff` the new-game reset leaves in that byte (the high half of
`effect_record_list`'s `$ffff` "empty" word) is negative and BUMPS — turning the word into `$00ff`,
which `$b39c`'s `tst.w / bpl` no longer reads as empty. The two fields really do overlap at one
address, and the port reproduces the overlap. The `move.w #$ffff,$1079a.l` below the join runs on the
REFUSED arm too, which the case drives from both sides.

**TWO NEW BCD ENTRY-X SITES, BOTH PROVED, AND ONE OF THEM BY AN ARITHMETIC INSTRUCTION'S OWN CARRY.**
`$545e` is `$5196`'s three instructions through the shared `pay_gold_award`, so its proof is that
one's. `$548a` is new in kind: `lsl.l #4,d0` leaves X the last bit shifted out, which for a count of
four is bit 28 of the operand — and the operand is `moveq #0,d0 / move.b 20(a0),d0`, a zero-extended
BYTE, so bit 28 is 0 for every kind a record can hold. `lea`, `move.l d16(An),Dn` and `beq` between
it and the `bsr` leave X alone. Every other proved site here rests on the ABSENCE of an X-writer;
this one rests on the value one produces. [`include/hud.h`](include/hud.h)'s audit block now reads
SIX C sites over EIGHT original `bsr`s, and names the FIFTH threaded site (`$544c`/`$5450`, slot 38's
own copy of the payout chain, which adds no C at all).

**TWO RUNAWAYS INSIDE `$6938`, AND NEITHER IS DRIVEN.** The blanking loop decrements without testing,
so an addend of ZERO never leaves it; the digit loop tests AFTER decrementing, so entering it with the
counter already at zero wraps to `$ffff` and writes 65,536 more characters — which needs an addend
whose low FIVE nibbles are all zero and something above them. Both are reproduced because the bytes
say so and neither has a case, because a case would not terminate. What is stated instead is that the
ONE caller cannot produce either: it `beq`s on zero, and a case walks all 22 shipped kind rows and
requires every nonzero score to have a nonzero low 20 bits. `$6938`'s single caller is itself a
checked property.

**THE CENSUS, RUN BEFORE THE FACT — AND IT CORRECTED THE CITATION STYLE OF AN EARLIER CORRECTION.**
`pickup_effect_table` has exactly ONE `lea` in the whole image over both absolute encodings and both
PC-relative forms; `text_bonus_digits` ONE; `actor_kind_table` TWO. None of the fourteen handler
addresses is named by any instruction anywhere, and each is held as a longword in exactly one place —
its own table entry — which is what makes the fourteen the pickup dispatch's alone. **And batch 28's
`$1044c` correction cited `$5478` and `$6d3e`, which are the longword OPERANDS; the instructions are
at `$5476` and `$6d3c`.** The rulebook's "instruction-address citations" was written for exactly this.

**THE DUPLICATE `cmt 0x1044c` IS GONE, which discharges one of the three the queue carries.**
`ApplyNames` is LAST-WINS, so the original plate at that address had been dead in Ghidra and alive
only to greps since batch 28 — and it still claimed one reference where there are two, claimed only
the first two words of a row are read, and undercounted the pointer block below the table by two.
The correction is folded into one directive, with the count fixed and the two readers' different
bounds stated. `include/wonderboy.h` and `test/test_actor.py` carried the same undercount and now
say fourteen.

**MUTATION SWEEP: 33 MUTANTS OVER SIX PRE-HOC AXES, 32 CAUGHT FIRST TIME, ONE REAL HOLE CLOSED —
33 of 33. The independent gate then found FOUR COVERAGE HOLES the sweep's own axes had never asked
about, and the RE-RUN after closing them is 35 of 35** — the two added mutants being the gate's own:
the handler's post moved ABOVE the score/bonus pair, and the two meter grants exchanged. The axes:
the dispatch refusal (the scale's width, the extension's sign, the refusal reported as a run); each
handler's grant and its message; the score longword's BCD threading; the kind-row field offsets and
stride; the table-bound enumeration; the digit routine's swap, rotate direction, blank character,
count and message; and now the ORDER of the frame's two posts, and the two grants whose witness is a
word rather than a slot.

**THE ONE SURVIVOR WAS THE SIGN EXTENSION, and closing it took a differential rather than an
argument.** `movea.l 0(a1,d0.w),a1` sign-extends the wrapped offset, and dropping that survived the
whole suite: every legal offset is positive, and a high index refuses either way — below the table
with the sign, above it without — because each of the fourteen addresses is held as a longword in
exactly ONE place. So no index at all separates the two spellings on the image as it ships. What
separates them is a TARGET only the signed read can reach: index `$ffff` scales to offset `$fffc`,
four bytes BELOW the table, which is `actor_kind_table` row 21's last longword and zero in the
shipped image. Seeding an entry address there makes the ORIGINAL `jsr` to it, so the case is a full
differential and not a C-only claim; the zero-extended spelling reads `$205a8` instead and refuses.

**WHAT THE INDEPENDENT GATE FOUND, and every one of the four was a case that did not execute what
its name claimed.**
  * **THE id-0 CANCEL CLAIM HAD NO EXECUTING CASE.** Every fourteen-way row seeded a ZERO score, so
    the bonus box was never posted, and the one nonzero-score row used entry 0, which posts nothing —
    no run had both posts live, and moving `run_pickup_effect` ABOVE the score/bonus pair survived
    the whole suite. Four rows now put them together (entries 1, 2, 10 and 11) and assert the id the
    frame LEAVES: the entry's own message for entry 2, and a ZERO for the three that post none. The
    reorder mutant is red on all four.
  * **THE THREE WAITING-ARM CASES HAD LOST THEIR OUT-OF-CONTACT PREMISE SILENTLY.** `_pickup_pokes`
    overlaid the followed record's x unconditionally — it is the gold draw's entropy — over the very
    x `_band5a_pokes` parks far away to shut the contact test, so only the Y was separating the two
    records and no case said so. The overlay is now conditional and all three run
    `_assert_contact(.., False)`; a probe that collapses the y as well turns all three red. The
    double-expiry case's second half also asserted only the free marker, which the COLLECT arm
    produces too, and now asserts that neither accumulator moved and no message was posted.
  * **THE RUNAWAY GUARD WALKED THE WRONG RANGE.** It swept the table's own 22 rows where the site's
    `bge` admits kinds 2..127 — two rows checked that cannot be reached and 106 that can left
    unchecked — and the failure mode it guards is a HANG, not an assertion. Widened to
    `range(2, 0x80)`. Nothing in the wider range reaches it either, so this is a correction of PROOF
    SCOPE and the case's docstring says so.
  * **ENTRIES 10 AND 11 EXECUTED NO ASSERTION OF THEIR OWN** in the fourteen-way case: they post no
    message and write no HUD slot, so they rested entirely on the hand-built band. The meter and the
    panel countdown are now seeded as INPUTS and both are asserted, and the docstring's "two that
    post none" is corrected to three (1, 10 and 11, of which 10 and 11 write the meter).

**AND FIVE CLAIM CORRECTIONS the gate found on top of this batch's own.** Row 0 of
`actor_kind_table` carries a nonzero score (`$00000020`), so "rows 2 and 16..20" was short by one —
and row 0 is unreachable from this site anyway, which the plate now says. Message 15's string opens
with SIX spaces and not seven, so the five-byte patch leaves ONE before "Bonus"; three surfaces said
otherwise. The retraction about `$bbc4` landed on the plate that CITED it and not on `cmt 0xbbc4` or
on `WB_HUD_SLOT_BBC4`, both of which went on crediting the address to code no batch had recovered
and denying that any effect handler wrote it; both now carry the correction, and the Wing Boots /
Revival identifications sit ON `WB_HUD_SLOT_BBC2` and `_BBC6` where a future renamer starts rather
than only in this section. `src/behavior.c` claimed slot 38's waiting arm was slot 31's frame byte
for byte — the tier's recurring over-claim — where the two share exactly four instructions. And
three surfaces named the lifetime's VALUE where they meant its ADDRESS, which is
`WB_TEXT_LIFETIME_REQUEST`.

**AND ONE STRUCTURAL FIX.** `test_effects.py` had become a third battery importing `bit_op_d16`, the
three immediate BIT opcodes and the register ordinals from `test_actor.py`. They are promoted to
`leaf.py` under the third-copy rule instead, `test_actor.py` re-exports them for the two batteries
that name it as their source, and `README.md`'s claim that only one battery here imports another —
false for several batches, since five now import a MODEL, a cap or a write set from the battery that
owns the routine reached — is corrected with the distinction stated: models may cross, encoders go
to `leaf.py`.

**NOT PINNED, HONESTLY.**
  * **The two `$6938` runaways**, above: reproduced, argued unreachable from the one caller, and
    never driven.
  * **What `hud_slot_bbc4` IS.** Its grant is the one handler here that posts no message, so nothing
    names it. What this batch does close is that slot's own plate and `wonderboy.h`'s slot block,
    which between them credited the address to code no batch had recovered and denied that any
    effect handler wrote it — both retired, and the correction now sits ON `cmt 0xbbc4` and ON
    `WB_HUD_SLOT_BBC4` rather than only on the plate that cited them.
  * **What the four record words MEAN.** Each word's HIGH byte is distinct across the four
    (`$06/$05/$07/$08`) and its LOW byte is not (`$05/$08/$05/$03`), which is as far as the evidence
    for "{item, count}" goes. Nothing here follows a reader of the list.
  * **Whether `WB_HUD_SLOT_BBC2` and `_BBC6` should be RENAMED** to the two items their grants
    identify. The identification is recorded on both plates and in the header's comments; the rename
    would touch `src/effects.c`, `test_effects.py` and every other reader, so it is queued rather
    than made.
  * **The registers each handler leaves behind**, as everywhere else in this tier.
  * **The refused dispatch**, as in every batch since 29 — and now at two tables rather than one.

**QUEUED — WHAT IS LEFT OF THE TABLE.** Ten rows: **slot 1** (the player, the largest subtree behind
the table), **slots 39..46** and **slot 57**. The order stands: 39..46 and 57, then the player LAST.
**THE TWO STANDING OBLIGATIONS FOR 45/46, RESTATED**: `actor_aim_velocity` (`$6528`) still has no
ENTRY PIN and behaviour slot 45 is its second caller, so the eight encoders that pin it
(`movem.l` both ways, `asl.w`/`asr.w`/`roxl.w` by an immediate, `exg`, `neg.w`, `eori.w`, `adda.w`
and `move.b (An)+,Dn` with `ext.w`) are due with that block; and `actor_behavior_type46` (`$58f2`)
is the THIRD reader of `WB_ACTOR_ANIM_5160_FRAMES`, whose other two this port already has, so it
lands with its own block rather than being re-ported.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`); the second reader of `actor_type30_drift` at `$b84`; the **two**
remaining duplicate `cmt` directives (`0x1023a`, `0x10394` — `0x1044c` is discharged);
`scene_copy_record_fields` (`$539e`) with `player_pending_event_gate` (`$b1a`); the third-copy
encoders due in `leaf.py` (now **fourteen**, this batch adding `lsl_l_imm_dn`); the `WB_HUD_SLOT_BBC2`
/ `_BBC6` renames above.

### Batch 39: dispatch rows 39..46 and 57 — THE TIER'S OWN AMMUNITION, and the table CLOSES but for the player

**NINE ROUTINES, 1,142 BYTES, AND NOT ONE BOUNDARY.** Every callee below these nine was already
reconstructed, so each runs to its own `rts` or into a tail this port has. **Verified 283, 35,052
bytes, 79.2 % of §0k's 44,262; `make test` 5,262** (5,140 before; 120 of the 122 are in
`test/test_behavior.py`, which goes 1,448 -> 1,568, and the other two are `test/test_actor.py`'s
entry pin for `actor_aim_velocity` and the body-size row beside it. Seven of the 120 are the
mutation sweep's and six the independent gate's).
**SIXTY-ONE of the table's 62 rows are live and ONE remains — slot 1, the player.**
`PORTED_SLOT_COUNT` holds the figure and a case asserts it against the image's own table.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$54f4` | `actor_behavior_type39` | 164 | CLEAN — the shatterer, and the tail slot 41 also runs |
| `$55a8` | `actor_behavior_type40` | 148 | CLEAN — the walker that dies where the map stops it |
| `$563c` | `actor_behavior_type41` | 64 | CLEAN — slot 39 with ONE immediate changed, and NO ending of its own |
| `$567c` | `actor_behavior_type42` | 158 | CLEAN — the walker that breaks up, and the strike arm that keeps walking |
| `$572a` | `actor_behavior_type43` | 148 | CLEAN — slot 40's body with one sprite id spelt twice |
| `$57be` | `actor_behavior_type44` | 148 | CLEAN — the aimed shot in flight, on a signed BYTE pair |
| `$5852` | `actor_behavior_type45` | 160 | CLEAN — the HOMING escort, and `actor_aim_velocity`'s second caller |
| `$58f2` | `actor_behavior_type46` | 54 | CLEAN — the stolen gold floating away |
| `$7260` | `actor_behavior_type57` | 98 | CLEAN — the burst shot, on a WORD pair, with a tail-jump damage arm |

**WHAT THESE NINE ARE.** Each one is the record an ALREADY-RECONSTRUCTED handler spawns, read off
the spawners' own type constants rather than guessed from sprite ids: slot 16 lobs slot 39
(`WB_ACTOR_TYPE16_MINION_TYPE` is `$27` = 39), slot 6 fires slot 40, slot 18 drops slot 41, slot 25
slot 42, slot 19 slot 43, slot 21 slot 44, slot 14 slot 45, slot 23 slot 46 and slot 7 slot 57. Nine
parents, nine children, no two parents sharing one. So the fields each spawner writes are exactly
the fields the matching handler reads — slot 21 stamps `actor_aim_velocity`'s byte pair into
`30(a0)`/`31(a0)` and slot 44 spends it; slot 7's burst copies a `(dx,dy)` LONGWORD into `24(a1)`
and slot 57 flies on it; slot 23 stamps a `$50` countdown and `clr.b 18(a0)` and slot 46 runs
exactly those two down.

**AND IT IS NOT A BIJECTION OVER THE TIER'S SPAWNS — the first draft of this section said it was,
and that half was false.** `WB_ACTOR_TYPE17_SEED_TYPE` (`$34`), `WB_ACTOR_TYPE22_MINION_TYPE`
(`$35`) and `WB_ACTOR_TYPE26_SHOT_TYPE` (`$33`) are spawned behaviour rows too — slots 52, 53 and
51, reconstructed in batches 31 and 32 — so the tier spawns TWELVE rows and nine of them are this
batch's. The claim that survives is checked by SCRAPING `wonderboy.h` for every
`WB_ACTOR_TYPEnn_*_TYPE` constant rather than by reading a hand-list, and it has two halves stated
apart: every spawn constant names a row this port HAS, and the three that fall outside these nine
are named in the case so a reader is not left to notice the gap. (`WB_ACTOR_SHOT_TYPE_LO/_HI/_KEPT`
are deliberately not of that shape — they are the range `actor_hit_by_player_shot` SEARCHES, not a
type any handler writes, and the scrape's regex is what keeps them out.)

**THREE OF THE NINE ARE DRIVEN END TO END, THREADED THROUGH THE SPAWNER'S OWN WRITE LEDGER.** The
identification above is a claim about constants; these are the runs behind it, and the first draft
claimed them without having written them. Each is TWO differentials: the parent's frame runs on both
cores, `program_writes` becomes the seed for a second run, and the child's frame runs on that — so
the child's velocity, countdown and cursor are the parent's OUTPUTS and nothing between them is
written by hand. The three chosen are the three whose child reads a field the parent COMPUTES:
21 -> 44 (the aim table's signed byte pair), 7 -> 57 (the burst's `(dx,dy)` longword) and
23 -> 46 (the loot countdown, which bounds that record's whole life). Each is proved by its own
mutant — the spawner stamping the right value into the WRONG OFFSET — and all three red on it while
both handlers' own cases stay green.

**AND THE THREADING FOUND A FIELD NO SPAWNER WRITES.** `spawn_minion` copies the parent's x/y
longword and the type word and nothing at offset 9, so a fresh record's `WB_ACTOR_FLAGS2` is
whatever the freed slot was left holding — and for six of these nine that byte's bit 0 is what
chooses the frame's arm. The first threaded case ran the child's BREAK-UP arm on a keyed byte before
this was noticed. The two threaded cases that need it now state the bit, and say why; the game's own
behaviour is reproduced rather than repaired.

**AND IT SETTLES THE TIER'S REMAINING SHOT BAND.** `actor_hit_by_player_shot` searches types
`$30..$32`, which are slots 48, 49 and 50 — the three handlers in the `$5a` band with no contact
test of their own. Those are the PLAYER's shots; these nine are the monsters'. Nothing in this batch
opens on the spawn gate and nothing runs the player-shot scan, so a monster's ammunition cannot be
shot down.

**FIVE PLATES CORRECTED, TWO OF THEM ON THE EXTENT AND ONE BY A FACTOR OF THREE.**
  * `$54f4` and `$567c` said "decoded code runs $x..$5598 / $x..$571a", naming the first byte of the
    frame TABLE as the last byte of code — slot 47's own correction one band down. The code is
    `$54f4..$5597` and `$567c..$5719`.
  * **`$7260` said the code runs to `$73ce`**, which swallows all four SWOOP states
    (`$72c2..$73cd`, reconstructed in batch 32) and is 268 bytes of another machine. Slot 57 is 98.
  * `$6796`'s plate counted "ELEVEN `bsr.w` sites". Eleven is right and the mnemonic is not: only
    THREE are calls (`$5514`, `$565c`, `$5698`, in slots 39, 41 and 42, each returning into more of
    its own frame) and EIGHT are `bra.w` TAIL JUMPS, for which the stun's `rts` is the handler's.
  * `$6528`'s plate said "the caller count is two but slot 45 is still unported, so only slot 21's
    use is read". Both are read now, and they read DIFFERENT ROWS — 6 and 1.

The other seven `decoded code runs $x..$y` fields matched the bytes exactly, and every one of the
nine entry pins re-assembles the whole body. A difference of dispatch entries gives
180/148/64/174/148/148/160/54 for slots 39..46; the code is 164/148/64/158/148/148/160/54, and the
32 bytes of difference are the two frame tables.

**THE TWO STANDING OBLIGATIONS ARE DISCHARGED.**
  * **`actor_aim_velocity` ($6528) HAS AN ENTRY PIN**, in `test/test_actor.py`, and its 94 bytes
    assemble exactly. Eight encodings moved to `leaf.py` to make it possible — `movem.l` in BOTH
    directions, `roxl.w`, `exg` in BOTH operand orders, `neg.w`, `eori.w`, `addq.w`, `adda.w` and
    `ext.w`. Three of the eleven the queue listed (`asl.w`, `asr.w`, `move.b (An)+,Dn`) were already
    there. **TWO OF THE EIGHT ARE ORDER-SENSITIVE IN A WAY THE PIN IS WHAT CATCHES**: a `movem.l`
    register mask is numbered from a7 DOWN for `-(An)` and from d0 UP for every other mode, so the
    same registers are `$3ffe` pushing and `$7ffc` popping; and `exg d2,d3` and `exg d3,d2` are
    DIFFERENT WORDS (`$c543`, `$c742`) for the same effect, and this routine spells one of each. The
    one byte the first draft got wrong was `adda.w`'s operand order — the ADDRESS register sits in
    the opcode's register field, not the data one — and the pin failed on it.
  * **`WB_ACTOR_ANIM_5160_FRAMES` HAS THREE READERS AND THE CASE NOW DRIVES ALL THREE.**
    `test_two_of_the_three_readers_..._wrap_on_the_SAME_cursor` is
    `test_ALL_THREE_readers_of_the_5160_table_wrap_on_the_SAME_cursor`, with slot 46 driven beside
    `$6872` and slot 32 at the terminator and at the row below it. The two-of-three caveat is
    grepped to zero: the only surviving hits are the two RETIREMENT NOTICES that name the old case
    so a reader lands on the correction.

**AND SLOT 45 READS A ROW NOTHING HAD READ.** `actor_aim_velocity_table`'s plate said only row 6 had
a ported reader. Slot 45 reads ROW 1, and the case that pins it does not derive the direction code
at all: it POKES every pair of row 1 to one distinctive velocity and every pair of slot 21's row to
another, so whichever code the geometry produces the movement names the ROW. Both cores read the
poked table, so it is a differential and not a C-only claim, and a second case asserts the two row
constants are not equal — without that the seeding would silently stop separating them.

**THE ONE TABLE IN THIS BATCH WITH MORE THAN ONE READER, and a census form that had been invisible.**
`actor_type39_frames` (`$5598`, eight words) is read by THREE instructions: slot 39's own
`move.w $5598(pc,d0.w),6(a0)` at `$557e`, and `lea $5598.w,a1` at `$5826` and `$58c6` inside slots
44 and 45. **The two `lea`s are the SHORT absolute form** — batch 34's `$5160` miss, one table over —
**and the third is not a `lea` at all**: a single-instruction PC-INDEXED READ that
`_instruction_targets` did not decode, so the census would have reported two readers of a table three
routines read. `actor_type42_frames` (`$571a`) has exactly one.

**AND THE REPAIR IS TWO INDEXES, NOT A LONGER OPCODE LIST.** Adding
`move.w d8(PC,Dn.w),d16(An)` to `_instruction_targets` fixes this miss and leaves the shape that
caused it — an opcode list — intact for the next one. So the file now also carries
`PC_RELATIVE_SOURCE_TARGETS`, a MODE-shaped sweep that decodes a PC-relative source EA (both
`(d16,PC)` and `(d8,PC,Xn)`) in **every** opcode class. It is deliberately a SUPERSET — it decodes
data as instructions and cannot tell — and the two are used for opposite claims: the opcode-shaped
index carries every EXACT set in the file (which instructions name an address, which foreign edges
enter a band, where a mode-shaped sweep's phantoms would be fiction), and the mode-shaped one
carries the NEGATIVES, where a superset is precisely what is wanted. A case asserts the second is a
strict superset of the first, and the nine entry addresses and slot 39's table are now proved
against BOTH. On this image the wide sweep finds 620 targets and hits none of the batch's addresses
but the two real readers.

**WHAT IS STILL OUTSIDE BOTH, enumerated because `docs/methodology.md` requires the silence to be
stated completely rather than gestured at**: an ABSOLUTE operand in an opcode neither list names
(nothing sweeps abs by mode); `pea` with a register-indirect operand and `movea.l #imm,An`; and any
pointer ASSEMBLED AT RUNTIME — a base plus a computed offset, which is how every frame table in this
tier is actually indexed and which no static scan reaches.

**SLOT 41 HAS NO ENDING OF ITS OWN.** Sixty-four bytes: a settle, an ascent, a sprite immediate and
the contact enum, and then both exits branch into slot 39's tail at `$5534`. The whole-image branch
census finds exactly FOUR sites aimed there, two in each handler and none anywhere else, and a
`cov_visited` witness on that address in a slot-41 run is what says the port really runs the shared
code rather than a copy. The two are written as one body with the sprite id as its parameter.

**FOUR SHAPES ACROSS THE NINE, and what separates them is one instruction at a time.**
  * **The SHATTERERS (39, 41)** fall, drift three pixels while airborne, turn at a wall, and play an
    eight-word break-up the moment `WB_ACTOR_FLAG_SUPPORTED_BIT` is up OR `WB_ACTOR_FIELD_30` is
    latched. Their strike arm turns the record, stuns, and **FALLS THROUGH into the tail** rather
    than ending the frame; their body arm `st`s the countdown and ends it, which is what makes every
    later frame a break-up. Their cursor is stepped IN MEMORY (`addq.b` then `andi.b`, two writes to
    one byte) where the other three step it in a register, and their wrap does NOT lower the mode
    bit because they do not use one.
  * **The WALKERS (40, 43)** raise `WB_ACTOR_FLAGS2_BIT_0` when a probe refuses, and what the bit
    buys is slot 51's own fall-and-free arm. `btst #3,8(a0)` picks the sprite AND the probe in one
    test and nothing turns the record, so the id published is always the side it already faced —
    slot 40 has one per side, slot 43 spells the same one TWICE, which is what says the select is a
    select and not a constant hoisted above the test.
  * **Slot 42** is the walker that breaks up instead of falling, and **the only handler here whose
    strike arm neither ends the frame nor is a tail jump**: it raises the bit and then `bra`s into
    the walk, so the striking frame still steps. Its body arm raises nothing at all, so a type-42
    record can damage the followed one on every frame it touches it.
  * **The SHOTS (44, 45, 57)** carry a velocity. Slot 44's is the signed BYTE pair its spawner
    aimed, with the y SUBTRACTED, and its life is `WB_ACTOR_FIELD_29` spent TWO at a time — the one
    countdown in this file that is not `WB_ACTOR_FIELD_30`, and an odd value would never land on
    zero (the `$32` its spawner stamps is even, and a case pins that). Slot 45 carries none at all
    and re-aims every frame. Slot 57's is a WORD pair with **both axes ADDED**, its life a `$28`
    frame count compared for EQUALITY on a word the compare RE-READS, its body arm a `bne.w` TAIL
    JUMP into `actor_damage_followed` that latches nothing, and its death arm two `clr.l`s over the
    EIGHT bytes `22(a0)..29(a0)`, written as longwords because the shim bounds the whole operand —
    and that span is NOT "the swoop's block", which the first draft of this section and three other
    surfaces said: the machine's state is 22, 24 and 26, ending at offset 27, so the second `clr.l`
    reaches two bytes past it into `WB_ACTOR_FIELD_28`, slot 57's own frame count.
  * **The RISER (46)** is fifty-four bytes and the shortest live handler after slot 8's six. Its two
    arms are EXCLUSIVE: the frame the countdown reaches zero frees the slot and does NOT rise.

**THE BATTERY'S FOUR-CONSTANT BOUNDARY SCHEME COLLAPSES TO ONE, and the walk cases gained a witness
for it.** Through batch 38 `test_behavior.py` carried `UNPORTED_TYPE`, `UNPORTED_SLOT`,
`UNPORTED_MID` and `UNPORTED_HIGH`, because a case wanting two or three DIFFERENT boundaries had
several to choose from — and every batch that ported one had to re-point it (slot 7, then 9, then
14, then 20, then 39/40/57). There is one row left, so there is one constant left. What the extra
three used to buy is now bought properly: `_walk_pokes` gives every FREE record the unported type, so
"stopped at the record I seeded" and "dispatched a free record instead of skipping it" report the
same address and write nothing — **the separating witness is the ORACLE's own a0**, which stops on
the record that was dispatched, and the boundary rows assert it. The axis of those rows is now WHERE
the boundary sits rather than which slot it is.

**MUTATION SWEEP: 51 MUTANTS OVER TWELVE PRE-HOC AXES, 39 CAUGHT FIRST TIME, and the twelve that
were not split FOUR WAYS — six real holes, two argued equivalences, one mutant this batch built
badly and three the runner REFUSED to apply. After closing the six, rebuilding the one and
re-spelling the three, the re-run is 10 OF 10 and the batch stands at 49 of 51 caught.** The axes: the shatterers' two break-up gates and their turn; the cursor stepped in
memory against a register, and the mask's ORDER against the index; each contact arm's own shape
(which of them ends the frame, which raises the mode bit, which latches `WB_ACTOR_FIELD_30`); the
walkers' sprite-per-side select and their fall-and-free arm; slot 42's fall-through strike; slot
44's signed byte pair, its subtracted y and its two-at-a-time life; slot 45's aim ROW and argument
order; slot 46's exclusive arms and the `$5160` step's look-ahead; slot 57's both-added axes, its
equality compare, its zeroed counter, its eight-byte death arm and its tail-jump damage; and — this
batch's own new surface — `actor_aim_velocity`'s three ratio steps, its X-flag restore, its swap bit
and its row stride.

**THE SIX REAL HOLES, and five of them are the same shape: an arm reached with only one value of
the state that steers it.**
  * **`tail/turn-becomes-set`.** Every shatterer case arrived with `WB_ACTOR_FLAG_SIDE_BIT` CLEAR,
    where `bchg` and `bset` leave the same byte. The turn case is parametrised over both facings now
    and asserts the bit FLIPS.
  * **`tail/wrap-also-lowers-the-mode-bit`.** Slots 39 and 41 are the only rows in the batch that do
    not use `WB_ACTOR_FLAGS2_BIT_0` at all, and the exact write set says so — but only against a
    NONZERO seed, because the ledger records CHANGED bytes and a `bclr` over a byte already zero is
    invisible. The landed case seeds the bit up.
  * **`walker/contact-latch-dropped`.** No walker case reached the BODY arm at all: slots 40 and 43
    end it `st 30(a0)` and the shots' own cases only assert that latch's ABSENCE. A body-overlap case
    per walker now asserts it is there.
  * **`shatterer/settle-and-ascent-swapped`.** Batch 35's finding at two more call sites: the ascent
    LOWERS the very bit the settle's head tests, so the order is observable only on the tick the
    ascent ends. Every seed here uses `AMMO_SPEED`, deliberately above 1 so that it does not — and a
    new pair of rows with `WB_ACTOR_SPEED` at 1 is what separates them.
  * **AND THE TWO IN `actor_aim_velocity`, closed by ONE case whose geometry is DERIVED rather than
    searched for.** `aim/addq-does-not-clobber-x` and `aim/second-sign-test-reads-the-branch` both
    need operands the routine's two sign folds normally cannot produce, because a fold makes each
    delta non-negative — `$8000` is the one value that survives one (`neg.w` on it is itself). With
    the followed record at `($4001, $8000)` and the shot at the origin the y delta supplies a
    NEGATIVE near axis, the far axis is odd, the first ratio test's `addq` clobbers the X flag the
    `roxl` would have restored, and the third compare then reads `$8000` against `$8000` (equal, no
    add) where the un-clobbered spelling reads `$8002` (one more add) — ONE direction code apart, and
    so one PAIR apart. Row 1 is seeded with a different velocity in every pair for that case, which
    also makes it the only case anywhere that pins the direction CODE rather than the row.

**TWO ARGUED EQUIVALENCES, neither assertable under this harness — and ONE MUTANT THAT WAS THIS
BATCH'S OWN MISTAKE.**
  * **`tail/cursor-step-in-a-register`** is batch 35's `cursor/memory-step-becomes-one-store` one
    body over, and the same geometry retires it: the two spellings differ only for a record whose
    `WB_ACTOR_FIELD_18` `bus.h` refuses, which requires the record to sit in `[IMAGE_SIZE - 18,
    $ffffff]` — and every such record's x is above `STACK_GUARD_LO` or refused itself, so it is
    inside the band the differential excludes. No record address separates them.
  * **`anim5160/advance-not-committed-before-the-reset`** is the double write batch 34 already
    registered, in the helper batch 39 extracted:
    `test_the_double_write_the_5160_stepper_makes_is_unobservable` states exactly this — the ledger
    records final values, and both spellings leave the same byte.
  * **`shatterer/sprite-published-after-the-tail` was BADLY BUILT** and is this batch's own mistake
    rather than the battery's: it moved the publish across `actor_followed_overlap_mask`, which
    writes no memory at all, so it could not have changed anything — batch 35's
    `slot10/anim-facing-read-before-the-turn` exactly. Rebuilt to move it BELOW the contact enum,
    where the body arm's `rts` makes it observable, it is caught.

**AND THREE MUTANTS THE SWEEP REFUSED TO APPLY RATHER THAN RUN, which is the guard working.** The
runner requires each mutant's text to match EXACTLY ONCE: `slot45/aim-source-and-target-swapped` and
`anim5160/look-ahead-becomes-a-look-at` matched twice (the same four lines live in `type21_fire` and
in slot 32's own publish) and `aim/row-stride` matched zero times. A runner that had applied the
first match would have measured a mutant of the wrong routine and called the result a survivor; one
that silently applied nothing would have reported "caught". All three are re-spelt and re-run.

**AND THE INDEPENDENT GATE'S OWN MUTANTS, 7 OF 7 CAUGHT**, run after its twelve items landed and
each against ONLY the case it is meant to prove: the three spawners stamping a right value into a
WRONG OFFSET (slot 21's aim pair, slot 7's burst longword, slot 23's loot timer), the two spawn
constants moved so that one names the unported player and one collides with the nine, and the two
that narrow the mode-shaped sweep back towards the opcode list it exists to escape.

**THE RE-RUN: 10 OF 10 CAUGHT** — the six holes' own mutants, the rebuilt sprite-ordering one, and
the three the runner had refused, each re-spelt so its text matches exactly once. `make test` from a
clean `build/` is green either side of it, and the sweep's own restored tree is green.

**NOT PINNED, HONESTLY.**
  * **`tail/cursor-step-in-a-register` and `anim5160/advance-not-committed-before-the-reset`**, the
    two surviving mutants above: both are argued equivalences under this harness rather than pins,
    and the arguments are geometry and the write ledger's own shape.
  * **The two `clr.w`s at `$57fe`/`$5800`** in slot 44 are DEAD — `ext.w` rewrites the whole low
    word from the byte — and the entry pin carries them, but no differential can separate a port
    that dropped them.
  * **Slot 57's lifetime RE-READ.** `cmpi.w #$28,28(a0)` reads the word `addq.w` just wrote, and the
    computed value and a re-read differ only for a record at an address `bus.h` refuses — which is
    inside the oracle's own excluded stack band, exactly as batch 35's `cursor/memory-step` case
    was. It is reproduced as a re-read because that is the instruction; it is not driven.
  * **The registers each handler leaves behind**, as everywhere else in this tier.
  * **The refused dispatch**, as in every batch since 29.
  * **`WB_ACTOR_FLAGS2` on a freshly spawned record**, which no spawner writes: the threaded cases
    STATE the bit rather than inherit it, so what a record's mode byte actually holds when the game
    allocates one is not established here — only that the field crosses uninitialised.
  * **What bounds `actor_aim_velocity_table` ABOVE row 6.** Two rows have ported readers now (1 and
    6) where the plate credited one; nothing in the image computes d4, so the table's top is still
    unmeasured.

**A PROCESS FAILURE, AND IT IS A RECURRENCE: `git checkout --` AS A SWEEP CLEANUP, EXACTLY AS IN
BATCH 34.** That batch's own section records losing `src/behavior.c` to the same command and having
to rebuild it, and the lesson it wrote down was a sentence ("back up before a destructive git
command on a file whose only copy is the working tree"). A sentence was not enough, so this time the
repair is a STEP: [`README.md`](README.md)'s recipe now opens with a named backup outside the repo,
before the green check and before the snapshot, and the loop restores from the snapshot and never
from git. A timed-out sweep left the tree possibly holding a mutant, and the cleanup line
was `rm -rf <snapshot> && git checkout -- src/behavior.c src/actor.c` — which deleted the ONLY copy
of the good sources and then reverted the file to HEAD, losing the whole batch's reconstruction in
one command. It was recoverable only because the edits were still in the session's own transcript.
The rule the recipe already carries ("take the mutant text from ONE snapshot captured at the start")
is about the sweep's own restore; this is the other half. **Never restore a working tree from git
during a sweep**: the snapshot is the restore, and if the snapshot is gone the tree is the only copy
there is. A named backup outside the repo, taken before the sweep starts, is what the guideline
actually asks for and what this batch now takes.

**QUEUED — AND WHAT IS LEFT OF THE TABLE IS THE PLAYER, ALONE.** One row: **slot 1**
(`actor_behavior_type01_player`, `$a36`), the largest subtree behind the table and the only one this
port does not have. Every boundary case in `test/test_behavior.py` now rests on it, and there is no
second boundary to fall back on — a batch that ports it must delete those cases rather than
re-point them, which `test_the_only_unported_row_left_is_the_player` says in its own docstring.

**THE PLAYER BATCH'S RIDERS, RESTATED.** Two pieces of unported code are not dispatch rows and will
land with that batch or not at all:
  * **`scene_copy_record_fields` ($539e, 30 bytes)** — `player_pending_event_gate`'s spawn helper,
    reached by the `bsr` at `$c5e` and handed the 32-byte template at `$537e` that slot 35's extent
    stops below. It is the reason the band `$4e38..$5407`, described as CLOSED in batch 34, still
    contains unported bytes.
  * **`player_pending_event_gate` ($b1a)** itself — the second call of the player's own frame, and
    the routine that decides whether the rest of it runs (three word flags, `$b08`/`$b0e`/`$b14`,
    each with its own arm; a negative d7 skips movement, collision, scene and stage work).
  * ...and `player_gate_on_1516`'s two BOUNDED arms (slots 9 and 12's hurt frames, and 22's and
    26's through the same `gated_hurt_frame`) retire with it: those stop at `WB_PLAYER_STEP_BODY`
    whenever `WB_TILE_33_MODE` is clear, which is the ordinary state.

**THE ENCODER HOIST, HALF DONE AND NOW COUNTED.** Batch 39 needed eight encodings in `leaf.py` for
`actor_aim_velocity`'s entry pin, and two of them — `addq_w_dn` and `neg_w_dn` — were already on
`test/test_behavior.py`'s "twelve third copies, queued for leaf.py" list. Adding them to `leaf.py`
while that file still defined its own is how the third one, `adda_w_dn_an`, turned into a NAME
COLLISION IN THE OPPOSITE OPERAND ORDER against `test_blit.py`'s: each battery's byte pins pass
either way, so nothing fails until the two files meet. **The canonical order is DESTINATION-FIRST**,
which is what `leaf.py`'s own `add_w_dn_dn`/`sub_w_dn_dn`/`cmp_w_dn_dn` use and what `test_blit.py`'s
three call sites already passed; `leaf.py`'s first spelling had it the other way round and is
corrected, and the docstring records that a site using a1 and d1 would assemble identically either
way, so the order is not self-pinning.
So this batch converted FIVE copies — `addq_w_dn` and `neg_w_dn` in `test_behavior.py`, and
`addq_w_dn`, `ext_w_dn` and `adda_w_dn_an` in `test_blit.py` — and the list in `test_behavior.py`'s
own comment is corrected — and the correction is bigger than two: it said TWELVE and ENUMERATED
NINE, so it was wrong in both directions. **The true figure is FIFTEEN, and it is now stated as
"what `grep -c 'queued for leaf.py' test/test_behavior.py` returns"** rather than as a tally, which
is the thing that drifted: `add_w_d16_dn`, `adda_l_dn`, `addq_b_dn`, `clr_l_dn`, `cmp_b_imm_dn`,
`cmp_w_abs_l_dn`, `jsr_abs_w`, `jsr_ind`, `lsl_l_imm_dn`, `move_w_d16_d16`, `move_w_dn_abs_l`,
`move_w_dn_d16`, `movea_l_ind`, `mulu_w_dn`, `subi_w_d16`. Beside them, `neg_w_dn`'s remaining
copies in `test_map.py` and `test_scroll.py` and `addq_w_dn`'s in `test_map.py` stay because this
batch has no other reason to touch those two files; all three carry an ALSO-IN note pointing at
`leaf.py` now, in both directions.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`); the second reader of `actor_type30_drift` at `$b84`; the two
remaining duplicate `cmt` directives (`0x1023a`, `0x10394`); the `WB_HUD_SLOT_BBC2` / `_BBC6`
renames. **DISCHARGED THIS BATCH**: the `actor_aim_velocity` entry pin and the eight encoders it
needed; the `$5160` three-reader wrap; `actor_behavior_type46`, which batch 35 registered by name.
**NEW**: `_instruction_targets` covers `move.w d8(PC,Dn.w),d16(An)` but no other PC-relative SOURCE
form — `move.b`, `move.l` and every arithmetic op with a PC-indexed source are still outside it, and
so are `pea`, `movea.l #imm` and any pointer assembled at runtime. Batch 39 found the first of those
forms by needing it; the next census that claims "no instruction names this address" should widen
the scan again rather than trust it.

### Batch 40: the player's frame opens — THE PARTITION, and the tier's five leaves

**THE PARTITION FIRST, because the player is not one routine and the previous batches' shape does not
fit it.** Behaviour slot 1 (`actor_behavior_type01_player`, `$a38`) is NINE `bsr`s in a row and
nothing else; every one of them is a routine of its own, and they are spread over `$a38..$21e4` with
already-ported code interleaved between them. The band is 6,698 bytes and it divides EXACTLY, which
is the point of stating it as arithmetic rather than as prose — the twenty-five spans below add up to
the band with nothing left over:

| span | bytes | what |
| --- | --- | --- |
| `$a38..$a75` | 62 | **the frame top** — the nine calls. Portable only when all nine are |
| `$a76..$b07` | 146 | `player_meter_empty_check` — **THIS BATCH** |
| `$b08..$b19` | 18 | data (`WB_STAGE_RESET_BLOCK`) |
| `$b1a..$d27` | 526 | `player_pending_event_gate` — the frame's second call |
| `$d28..$d77` | 80 | `bg_scroll_raise_requests` (ported, batch 5) |
| `$d78..$d83` | 12 | `player_gate_on_1516` (ported, batch 31) |
| `$d84..$e05` | 130 | `player_apply_joystick` — **THIS BATCH** |
| `$e06..$ec7` | 194 | `player_jump_step` — **THIS BATCH**, and the retired boundary |
| `$ec8..$107b` | 436 | `player_step_and_arm` — the WALK — **PHASE B** |
| `$107c..$10a1` | 38 | `player_reset_ground_state` — **THIS BATCH** |
| `$10a2..$1207` | 358 | the two map probes (ported, batches 10–11) |
| `$1208..$1333` | 300 | `player_weapon_fire` — the WEAPON — **PHASE B** (298 code + 2 data) |
| `$1334..$1513` | 480 | the fall pass, the cell lookup and both settles (ported) |
| `$1514..$1519` | 6 | data (the three `WB_TILE_33_*` words) |
| `$151a..$19ab` | 1,170 | `player_collide_and_scroll` — the largest single routine in the game |
| `$19ac..$1aef` | 324 | `scene_spawn_from_script` — the SCENE-SPAWN TREE's head |
| `$1af0..$1b45` | 86 | `map_stamp_block` (ported, batch 10) |
| `$1b46..$1b67` | 34 | `speech_script_step` — **NOT ported** (`# ctx`), and a SHARED leaf: called from the tree AND from the `$151a` one |
| `$1b68..$1bb3` | 76 | both pool allocators (ported, batch 10) |
| `$1bb4..$1cbf` | 268 | the tree's second arm, reached by a `beq.w` from `$19d4` — a continuation, not a routine, and the only span in the band with no name at all |
| `$1cc0..$1f35` | 630 | `resource_descriptor_fetch`, `glyph_stamp_8_rows` and what is between them |
| `$1f36..$1f53` | 30 | `actor_table_reset` (ported) |
| `$1f54..$21e3` | 656 | `player_stage_transition`, and `$1fa2` sits INSIDE that span (phase B MEASURED it: the arm is this routine's) |
| `$21e4..$23b5` | 466 | data (sprite ids and `WB_EFFECT_STATE_21E4`) |
| `$23b6..$2461` | 172 | `actor_hit_by_player_shot` (ported, batch 29) |

**1,294 bytes were already ported, 490 are data, this batch ports 508, and 4,406 remain.** Add
`scene_copy_record_fields` (`$539e`, 30 bytes, outside the band, reached by the one `bsr` at `$c5e`
inside **`player_pending_event_gate`** — `$b1a`, which is NOT "the gate": that name is `$d78`
everywhere else in these documents) and the batch is 538.

**WHAT MADE THESE FIVE PHASE A, and it is a mechanical criterion rather than a judgement: every
callee below them is already reconstructed.** The joystick edge, the SFX trigger and `snd_play_song`
are the whole callee set of `$a76`, `$d84`, `$e06`, `$107c` and `$539e`, so each runs to the
original's own `rts` and **not one boundary is reported from src/player.c**. Three of the four that
remain fail that test: `$b1a` calls `$1f54` on nearly every arm and `$19ac` on one, `$151a` and
`$19ac` reach a tree of their own, and `$1208` carries an entry X (below). **`$ec8` PASSES the test
and is deferred anyway** — at 436 bytes, five sections and a walk accelerator whose two turn arms are
asymmetric it is a batch's worth of cases on its own, and phase B opens with it. It was WRITTEN in
this batch's first draft and then REMOVED, because a reconstructed routine ships with its
differential or it does not ship: an entry pin and a case set are what make the other five real, and
`$ec8` had neither.

**Verified 288, 35,590 bytes, 80.4 % of §0k's 44,262; `make test` 5,353** (5,262 before; 83 of the
91 are in the new `test/test_player.py` and the other 8 are `test/test_behavior.py`'s net, which goes
1,568 -> 1,576: FIVE cases were rewritten rather than added, and the two independent gates added the
rest). **`PORTED_SLOT_COUNT` stays 61**:
the row does not flip until the whole frame runs, which is the last act of the player port and not
this phase's.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$a76` | `player_meter_empty_check` | 146 | CLEAN — the DEATH CHECK: revive, or start the death |
| `$d84` | `player_apply_joystick` | 130 | CLEAN — the LADDER, and it does not fall into `$e06` |
| `$e06` | `player_jump_step` | 194 | CLEAN — the JUMP MACHINE, and the wing boots |
| `$107c` | `player_reset_ground_state` | 38 | CLEAN — leaving the ladder |
| `$539e` | `scene_copy_record_fields` | 30 | CLEAN — EIGHT longwords, not the five the plate said |

**THE STANDING BOUNDARY IS RETIRED, and it was the only one of the four the ORIGINAL RETURNED FROM.**
`player_gate_on_1516` ($d78) branched into `WB_PLAYER_STEP_BODY` whenever `WB_TILE_33_MODE` was clear
— the ordinary state — and FIVE handlers reported it: slot 53 directly, and slots 9, 12, 22 and 26
through the shared `gated_hurt_frame`. `$e06` is that body. The gate CALLS it now, its own C returns
`void`, and all five frames run whole. What that exposes is worth stating rather than tidying: a hurt
MONSTER runs the PLAYER's jump machine over its own record — a0 is whatever the dispatcher handed the
handler — so the strength byte, the ascent and the wing-boot charge are all applied to the monster.
That is what the original does, and ALL THREE ARMS ARE DRIVEN THROUGH A HANDLER rather than asserted
here: the head by the four gated hurt cases, the ASCENT by
`test_the_gated_hurt_arm_runs_the_ASCENT_BEFORE_the_retreat` (which is also what pins where the call
sits), and the wing boots by `test_a_hurt_monster_can_burn_the_PLAYERS_wing_boots` — a global
belonging to the player, spent by a monster's frame. Three of the five rewritten cases assert BOTH halves (the jump
machine's own two bytes, and the fields below the call that used to be missing), which is what
separates "the call ran" from "the call was skipped".

**FIVE PLATE CORRECTIONS, every one of them an EXTENT or a COUNT, and two were load-bearing.**
  * **`$d78` said `$e06` is "the body `player_apply_joystick` also falls into".** It is not:
    `$d84` ends in its own `rts` at `$e04`. A whole-image census over every branch form, both
    absolute encodings, both PC-relative ones and the mode-shaped sweep finds **exactly one**
    instruction naming `$e06` — the gate's own `beq.w` at `$d7e`. `test_player.py` carries that as a
    case per routine, positive and negative.
  * **`$539e` said "20(record_ptr_10420) and four following longwords".** It is SEVEN following, i.e.
    eight in all — a whole 32-byte record — and the `lea 4(a1),a1` between them means the template's
    first longword is never read. That is why `WB_ACTOR_TYPE35_TEMPLATE` opens with four dead bytes.
  * **`$a38` said "decoded code runs $a38..$b18"**, which runs through `player_meter_empty_check` and
    the whole of `WB_STAGE_RESET_BLOCK`. The code is `$a38..$a75`.
  * **`$a76` said "Body $a76..$b08"** — `$b08` is the reset block's first byte. The code is
    `$a76..$b07`.
  * **`$107c` said "Body $107c..$10a2"** — `$10a2` is `actor_step_left_against_map`'s entry. The code
    is `$107c..$10a1`.

**AND A HEADER CORRECTION THAT IS A FINDING: `WB_EFFECT_STATE_BD6A` IS NOT UNREAD.** wonderboy.h
carried "`$bd6a` and `$21e4` have no reader at all" since batch 2. It has THREE, and all three are the
player's, which is why they were invisible while that tier was unported: `$e12` and `$109a` add
`WB_PLAYER_JUMP_STRENGTH_BIAS` to its LOW BYTE (the jump's height, re-derived every frame) and
`$fde`/`$1048` add 4 to the WHOLE WORD (the walk's top speed — `addq.w #4,d0`, which has no constant
of its own until `$ec8` lands in phase B). So the word the three `$bd68`-sibling effect handlers stamp
is HOW HIGH THE PLAYER JUMPS AND HOW FAST HE RUNS, and the two spellings differ in operand size — a
state word of `$00fc` clamps the walk to a standstill where it leaves the jump at 4. `$21e4` is still unread.

**ONE CONSTANT RENAMED OFF A ONE-SITE READING: `WB_ACTOR_FLAG_CARRIED_BIT` -> `WB_ACTOR_FLAG_MOVED_BIT`.**
The old name was read off `$6dcc`, the platform's `bset #5,8(a1)`, and its comment said "the only site
in the tier that writes bit 5" — true of the tier and false of the image. The player's walk has three
more (`bset` on each direction arm, `bclr` on the frame neither is held), so the bit is "something
moved this record along x this frame". Its one READER is `$2184`, inside code this port does not have,
so what the bit buys is still open.

**TWO GLOBALS NAMED, and one of them is the game's own CHEAT.** `$604`
(`key_sequence_matched_604`) is raised `$ffff` at `$5fa` when the byte cursor at `$606` has walked the
sequence at `$608` to its `$ff` terminator against `key_last_scancode`. FIVE readers, all bare
`tst.w`: three that gate further scancode actions, and TWO inside `player_meter_empty_check`, where a
raised word takes the revival arm with an EMPTY medicine slot AND then skips the rearm — so the
medicine is never spent and the meter refills on every death for ever. `WB_ACTOR_TYPE35_TEMPLATE`
(`$537e`) is the other; it had no constant at all.

**WHAT THE TWO HUD SLOTS ARE, closed by the messages their spenders post.** `WB_HUD_SLOT_BBC2` is the
WING BOOTS: `$e06`'s airborne arm burns one charge per frame while UP is HELD, forces the fall speed
back to 1, and on the last charge rearms the slot and posts message `$13`, "You lost wing boots."
`WB_HUD_SLOT_BBC6` is the REVIVAL MEDICINE: `$a76` spends it on an empty meter and posts message
`$16`, "Used the revival medicine." Both readings were already in wonderboy.h from the PICKUP side
(batch 38 read the handlers that GRANT them); this batch reads the handlers that SPEND them, and the
two halves agree.

**THE ARM NO CASE HERE CAN DRIVE, AND IT IS THE HARNESS RATHER THAN THE MODEL.** `$604` lies inside
the kit's harness-poked input block (`$600..$61f`), which for this project sits inside the game's own
program because it loads at `$3f8`. `harness.make_image` REFUSES any poke landing there — correctly:
nothing can tell a poke staging kit model state from one patching the program at the same address
(`test_poked_input_guard.py` owns that waiver and its three guards). So the CHEAT ARM of
`player_meter_empty_check` is reproduced and **unpinned**. Two cases state the limitation instead of
hiding it: one asserts the shipped word is zero (which is what makes every revival case above the
SLOT's arm and not the cheat's), and one asserts `make_image` raises — a tripwire that fails, and
tells the next reader to write the differential, if the block or the load base ever moves. It is the
same shape as the entry-X sites include/hud.h tabulates: a run the shim cannot enter.

**MACHINERY: THE LABEL ASSEMBLER MOVED TO `leaf.py`.** `test_behavior.py` wrote the two-pass
assembler (`_Ref`/`_lab`/`_bcc`/`_asm`/`_instructions`) for the dispatch rows' entry pins; the
player's frame needs the same thing, and a body with four forward branches into two shared exits does
not survive the sum-the-spanned-bytes idiom either. Two batteries is the rule for hoisting, so it is
`leaf.Ref`/`leaf.lab`/`leaf.bcc`/`leaf.asm`/`leaf.instruction_count` now and `test_behavior.py`'s
several hundred call sites keep their private names as one-line aliases.

**MUTATION SWEEP: 34 MUTANTS OVER SIX PRE-HOC AXES, 32 CAUGHT FIRST TIME, and the two that were not
are one KNOWN limitation and one badly-built mutant of this batch's own.** The axes: the death
check's two gates and its sign test; the jump machine's three arms, their ORDER, and the byte-vs-word
add at its head; the wing boots' level-vs-edge read, their spend rate and their word-wide rearm; the
ladder's x mask, its two mode words, its direction order and its y mask; the copy's first longword
and its count; and the retired boundary itself (the gate inverted, and the gate not calling at all).

  * **`meter/rearm-unconditional` SURVIVED, and it is the unpinnable cheat arm above** — the mutant
    deletes the `tst.w WB_KEY_SEQUENCE_MATCHED` that skips the rearm, and no seed this project can
    build separates the two, because the word cannot be poked. It is the one mutant here that is a
    hole rather than an equivalence, and it is the harness's.
  * **`jump/ascent-tests-before-the-spend` SURVIVED BECAUSE IT WAS BUILT WRONG** — batch 39's
    `shatterer/sprite-published-after-the-tail` one routine over. The mutant tested the byte for 1
    and then spent it, which is the same function on every input; the mutation that means anything is
    testing the byte BEFORE the decrement, which differs at speed 1 (the ascent would not end) and at
    speed 0 (it would). Re-spelt as `jump/ascent-reads-BEFORE-the-spend` it is **caught**, by the two
    cases that already existed.

**TWO COVERAGE HOLES WERE CLOSED BEFORE THE SWEEP, by reading the seeds rather than by running it**:
every hover case seeded a CLEAR previous joystick frame, where "the stick is held" and "the stick was
just pressed" answer the same, and no case put anything in a HUD slot's SECOND byte, where `tst.b`
and `tst.w` answer the same. A row for each is in the battery, and the sweep's
`jump/hover-reads-the-edge` and `meter/slot-tested-as-a-word` are both caught by them.

**THE RE-RUN, TWICE, because the tree moved under the sweep twice** — `$ec8` was removed after it
(below) and the independent gate then changed the C again. Five mutants, one from each axis plus the
re-spelt ascent one, re-run on each tree: **4 caught and the cheat-arm survivor unchanged** both
times, with `make test` green from a clean `build/` either side. The second re-run also exercised the
recipe's own hazard for real — a ten-minute tool timeout killed it mid-mutant and left
`src/player.c` holding `copy/one-longword-short`. The cure was the recipe's: restore from the
SNAPSHOT, never from git, then finish the two remaining mutants.

**NOT PINNED, HONESTLY.**
  * **The cheat arm of `player_meter_empty_check`**, for the harness reason above — and with it the
    `meter/rearm-unconditional` mutant, which no seed this project can build separates.
  * **TWO ROUTINES HAVE NO CALLER IN THIS PORT, so their COMPOSITION is unexercised.** Both are
    pinned and driven at their own entry like any leaf; what no run covers is the call.
    `player_reset_ground_state`'s two call sites are both inside `$ec8`, deferred to phase B.
    `scene_copy_record_fields`' single site is `$c5e` inside `player_pending_event_gate`, also
    phase B — and its REGISTER CONVENTION is the live failure mode there: a1 is the template and a2
    the destination, in that order, with a3 clobbered, and the gate loads them at `$c52`/`$c58` as
    `lea $998c.l,a2 / lea $537e.l,a1`. A porter who reads that pair the other way round gets a
    routine that copies the record over the template and stays green in this battery, because every
    case here supplies both registers itself.
  * **The two double writes in `player_climb`.** `andi.w #$fff1,(a0)` then `addq.w #8,(a0)` are two
    stores to the x and `subq.w #2,2(a0)` then `andi.w #$fffe,2(a0)` two to the y; the ledger records
    final values, so folding each pair into one expression is unobservable.
  * **The registers each routine leaves behind.** None of the five hands one back that a caller
    reads — `$a4e` overwrites `player_step_and_arm`'s d0 unread — so nothing compares one.
  * **What `WB_ACTOR_FLAG_MOVED_BIT` and `WB_ACTOR_FLAG_FIRED_BIT` BUY.** Both are written here and
    read only at `$2184` and `$20ca`, inside `player_stage_transition`'s tail.

**THE INDEPENDENT GATE, five reviewers, and what it changed.** Two CORRECTNESS findings, both the
same class and both invisible to any case this project can write — a READ HOISTED ABOVE A WRITE.
`player_climb` read the record's y at the top of the body where the original reads it LAST, below
both global stores; `player_reset_ground_state` read WB_EFFECT_STATE_BD6A above the three flag
writes where the original reads it below them. Each diverges only for a record whose address makes
one of its own fields alias the global being written — `actor` of $1514/$1516 for the ladder, $bd62
for the reset — and every case here seeds its record in an actor table, so nothing could drive
either. Both are now spelt in the original's order, with the aliasing address named at the site.

The rest were record-keeping and reuse, and they are worth listing because four of the five findings
were COUNTS this batch got wrong in its own documents:
  * **Four handler plates and four C comments still claimed the retired boundary** (slots 9, 12, 22,
    26 and slot 53's own), in exactly the surfaces the rule says a retirement must be written on.
    Corrected on each CITED plate.
  * **`$d84`'s new plate called it "the fourth call"; it is the seventh** of nine. Both plates now
    name the CALL SITE ($a60) instead — an ordinal is a number two documents can disagree about, and
    these two did inside one commit.
  * **wonderboy.h's new section header said EIGHT `bsr`s** where player.h, names.txt and this file
    say nine.
  * **player.h's callee list over-claimed by six routines** (it named the map probes, the fall pass
    and both allocators, which are callees of the DEFERRED routines). The five here call exactly
    three things.
  * **This section cited `WB_PLAYER_WALK_SPEED_BIAS`, a constant the `$ec8` deferral had removed.**
  * **Seven ENCODERS reached their third or fourth copy** and went to `leaf.py` — `addq_b_dn`,
    `addq_w_ind`, `addq_w_d16`, `subq_w_d16`, `subq_b_d16`, `move_b_dn_d16` and `jsr_ind` — with
    `quick_field`, which is the improvement the move carries: every earlier copy inlines a silent
    `(amount & 7) << 9`, so a distance of 0 or 9 assembled as 8 or 1 rather than failing. Two of the
    seven were on `test_behavior.py`'s own hoist queue, so that queue is 15 -> 13 and the case that
    counts it is what caught the edit.
  * **The eight record accessors were a second copy of src/behavior.c's** and are now `static inline`
    in `include/bus.h`, which both files already include. A second copy is the one divergence nothing
    catches: each battery pins only its own routines, so both stay green while one drifts.
  * **The write band was widened for five handlers where three CASES needed it.** `HANDLER_GLOBALS`
    is the stray-write bound every case of a handler stops checking, so the jump machine's globals
    moved out of it and into the three cases that drive the gate's clear arm — and narrowing it
    proved the point: exactly those three failed, so no other case reaches that arm.
  * **And the two rewritten hurt-arm cases were WEAKER than the boundary cases they replaced.**
    "The field is present" says nothing about the call. Each now runs the frame TWICE on seeds
    identical but for WB_TILE_33_MODE and requires the DIFFERENCE to be exactly the jump machine's
    head — which pins both halves at once — and the pair became one case over all FOUR gated
    handlers, where batch 39's shape had covered two of the four.

**THE SECOND INDEPENDENT GATE FOUND TWO SURVIVING MUTANTS ON THE HIGHEST-STAKES CHANGE, and both
were the same failure of seeding: a state the cases never varied.**
  * **`arms/hover-after-the-launch` survived 5,345.** No case seeded WB_ACTOR_FLAG_SUPPORTED_BIT
    together with a wing-boot charge — every hover case was airborne and every launch case had an
    empty slot — so a port that ran the hover BELOW the launch instead of INSTEAD OF it answered the
    same on all of them. The state it gets wrong is ordinary: the frame after landing with boots on,
    where the charge would burn away while the player stands still. Two rows now seed it (standing,
    and rising), and the mutant is **caught by both**.
  * **`position/gate-below-the-retreat` survived too**, and that is the more interesting one: the
    difference helper hardcoded the jump machine's HEAD as the only permitted difference, and the
    head is two bytes nothing below the call reads — so moving `bsr $d78` to the foot of
    `gated_hurt_frame` left the same write set. What separates the positions is the ASCENT: it moves
    the record's y and the retreat below the call probes the MAP at that y. The helper is generalised
    past the head, and a case now seeds WB_ACTOR_FLAG_MOVING_BIT (which is both the ascent's gate and
    `actor_fall_and_settle`'s own early exit at $1376, so the settle above the call writes nothing),
    a speed of one WHOLE CELL, and that cell's row BLOCKED — so the retreat is refused where the
    un-risen one is not and the frame's x says which side of the call the gate ran. It asserts the
    two x's DIFFER, so a seed that stopped separating them fails rather than passing vacuously.
    **Caught in all four gated handlers.**
  * **Slot 53's position is HALF pinnable and the case says which half.** Above the call is the
    settle, and a speed of 1 puts the ascent's `bclr` of the moving bit in the same frame as the
    settle's early exit, so `position/slot53-gate-above-the-settle` is **caught**. Below the call are
    the x step, the sprite and the countdown — three addresses the jump machine neither writes nor
    reads — so a gate moved to the FOOT of that handler writes the same bytes and no case here can
    separate it. An argued equivalence under this harness, with the geometry as the argument.
  * **THE CONTROLS STILL REDDEN.** Generalising a difference assertion can weaken it into vacuity,
    so both "the gate does not run at all" mutants were re-run against the new helper:
    `control/gated-hurt-frame-drops-the-call` is caught by 8 cases and `control/slot53-drops-the-call`
    by 2.

**AND SIX MORE RECORD-KEEPING FAULTS, five of them one address over from the batch's own classes.**
  * **The `$bd6a` retraction had missed `../names.txt`** — `cmt 0xbd66` still read "$bd6a and $21e4
    have no reader at all", verbatim, on the SOURCE-OF-TRUTH surface and directly in phase B's path.
    Corrected on the cited plate.
  * **The partition's `$1af0..$1bb3` row claimed a 196-byte span with a 162-byte count**: the 34
    bytes between them are `speech_script_step`, which is `# ctx`, NOT ported, and SHARED between the
    scene-spawn tree and the `$151a` one. The row is now five rows, and the table is checked by
    arithmetic rather than by eye: 25 rows, contiguous, each row's count equal to its span, summing
    to exactly 6,698.
  * **`PORTABILITY.md` carried two off-by-one extents** feeding live arithmetic (`$a76..$b08` and
    `$151a..$19ac`, both naming the NEXT thing's first byte). Fixed, and its residual-bytes table
    re-checked: both runs still lie wholly inside the corrected extents, so the 226/254 figures stand.
  * **The honesty list was one routine short** — `scene_copy_record_fields`' composition is exactly
    as unexercised as `player_reset_ground_state`'s, and its REGISTER CONVENTION is the live failure
    mode for phase B.
  * **"reached only from the gate" was false**: the caller is `player_pending_event_gate` ($b1a), and
    "the gate" names $d78 everywhere else in these documents.
  * **`post_message` was a FOURTH spelling of two stores** and `LONGWORD_BYTES` a second copy. The
    message pair is `text_post_message` in `include/text.h` now (four modules converted; src/scene.c
    keeps its own because it takes a LIFETIME, and `type61_post_message` because its `clr.b` writes
    only the word's high byte), and the width is `WB_LONGWORD_BYTES`. Slot 53's instruction cap also
    gained the term for the routine its frame now runs — it is in none of the four families that
    carry it, so it had been passing on unrelated slack.

**QUEUED — PHASE B, in the order the frame calls them and with the reason each is not phase A.**
  * **`$ec8` `player_step_and_arm` (436 B), CALLEE-CLEAN and first.** Five sections: the knock-back
    that spends `actor_stun_followed`'s step count, the fire edge, the flicker countdown (`$f14` is
    `WB_ACTOR_FLICKER_COUNTDOWN`'s one reader), the launched step, and the WALK ACCELERATOR —
    `WB_ACTOR_FIELD_22` a speed, `_23` its direction, `_24` a sub-frame counter mod 4, the ceiling
    `WB_EFFECT_STATE_BD6A + 4`, and a turn that is NOT symmetric (2 per frame turning right, 1
    turning left).
  * **`$1208` `player_weapon_fire` (300 B), callee-clean but carrying an ENTRY X.** `sbcd -(a2),-(a6)`
    at `$1260` subtracts the byte at `$1332` from the shot count in BCD **with the X flag as an
    input**, and on three of its four arms the last instruction to write X is inside
    `joy1_newly_pressed`. That is the `overlap_mask_exit_extend` class — the bit has to be COMPUTED
    from the same inputs, not claimed — and it is why this row is not phase A.
    *(CORRECTED BY PHASE B, and the correction is load-bearing rather than cosmetic:
    `joy1_newly_pressed` writes NO X at all — it is `move.b`/`move.b`/`eor.b`/`and.b`/`rts`, and the
    two logical ops leave the bit alone. So on those three arms the last X-writer is not in that
    routine, or anywhere else inside `$1208`: the bit is the CALLER's, i.e.
    `player_step_and_arm`'s exit, which is why the port takes it as a parameter instead of computing
    it. The fourth arm, the fireball, produces its own. See phase B's section below.)*
  * **`$b1a` `player_pending_event_gate` (526 B).** Three word flags in order and an arm each; `bsr
    $1f54` sits on nearly every arm and `bsr $19ac` on one, so porting it before those two would make
    most of it a boundary.
  * **`$19ac` the SCENE-SPAWN TREE (592 B of its own plus `$1cc0`'s 94 and `$1d1e`'s 536).** Its
    `$1bb4` arm is reached by a `beq.w` from `$19d4`, i.e. it is a continuation and not a routine —
    the 268 bytes that carry no name at all in ../names.txt are that arm. **And `speech_script_step`
    (`$1b46`, 34 B) is a THIRD thing again**: it sits inside the tree's address range, is `# ctx`
    and unported, and is SHARED — `$1aac` calls it from the tree and `$1ef2` from the `$151a` one.
    Whichever of the two lands first must port it, and the other inherits it.
  * **`$151a` `player_collide_and_scroll` (1,170 B)**, the largest single routine in the game.
  * **`$1f54` `player_stage_transition` (656 B), AND A PARTITION CONFLICT TO RESOLVE FIRST**:
    ../names.txt GAVE `$1fa2` (`actor_event_anim_step_2394`, 186 B) an entry INSIDE `$1f54`'s stated
    span. One of the two extents is wrong and the batch that ports either must measure it.
    *(RESOLVED IN PHASE B, in `$1f54`'s favour: the `fn` is deleted and the plate is the label. Past
    tense here because a reader who checked ../names.txt for the present-tense claim would not find
    it.)*
  * **`$a38` the frame top (62 B) LAST**, and the dispatch row flips with it.

**QUEUED, CARRIED FORWARD**: `abcd_byte` to the kit; regenerate `../out/names_dump.txt`,
`../out/hw_scan.tsv`, `../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4`
boundary; the tier partition; the `scene_run_effect` latent guard; `$1fa2`
(`actor_event_anim_step_2394`) — now with the extent conflict above attached to it; the second reader
of `actor_type30_drift` at `$b84`; the two remaining duplicate `cmt` directives (`0x1023a`,
`0x10394`); the `WB_HUD_SLOT_BBC2` / `_BBC6` renames — for which this batch supplies the EVIDENCE
(the messages their spenders post) without making the rename.

*(PHASE B DISCHARGED the `$1fa2` item of this list — the conflict is measured and the `fn` deleted —
and added its own. The live list is the one at the END of this file, under phase B's section; this
paragraph is left as phase A wrote it.)*

### Batch 40 phase B: the WALK and the WEAPON — and the extent conflict, measured

**TWO MORE OF THE FRAME'S NINE CALLS, and the criterion is phase A's unchanged: every callee below
them is already reconstructed.** `player_step_and_arm` ($ec8) reaches the two map step probes and
`player_reset_ground_state`; `player_weapon_fire` ($1208) reaches `joy1_newly_pressed` and
`actor_alloc_slot_high`. All four are ported, so **still not one boundary is reported from
src/player.c** — and the two routines together are 736 bytes, which takes the partition's remaining
4,406 down to 3,670.

| address | name | bytes | row |
| --- | --- | --- | --- |
| `$ec8` | `player_step_and_arm` | 436 | CLEAN — the WALK: five sections, and the accelerator's two turns are not symmetric |
| `$1208` | `player_weapon_fire` | 300 | CLEAN — the WEAPON: four items, and the first LIVE threaded `sbcd` |

**Verified 290, 36,326 bytes, 82.1 % of §0k's 44,262; `make test` 5,438** (5,353 before; all 85 are
in `test/test_player.py`, which goes 83 -> 168 — measured from a clean `build/`, and stated ONCE
here and once at the top of this file rather than twice from different runs, which is the drift the
header's own preamble records at 161/163 and 175/176). **`PORTED_SLOT_COUNT` stays 61** — the row
flips when the whole frame runs, and three calls are still missing.

**WHAT THE WALK IS.** Five sections in a row, each falling into the next and none of them returning:

  * **the KNOCK-BACK** — while `WB_ACTOR_FIELD_29` (the step count `actor_stun_followed` seeds) is
    nonzero the record takes one map step AWAY from `WB_ACTOR_FLAG_SIDE_BIT` and one is spent. The
    distance is the count as it was, because d7 is loaded above the `subq.b`.
  * **the FIRE EDGE** — `tst.b d0 / bpl` on `joy1_newly_pressed`'s byte, a SIGN test of bit 7 alone,
    which raises `WB_ACTOR_FLAG_FIRED_BIT`, lowers `WB_ACTOR_FLAGS2_BIT_0` and zeroes the walk speed.
  * **the FLICKER COUNTDOWN** — `$f14`'s `subq.b #1,21(a0)` is `WB_ACTOR_FLICKER_COUNTDOWN`'s ONE
    reader in the image, and the frame it reaches zero ends the invulnerability with the flicker.
  * **the HURT DRIFT** — gated on `WB_ACTOR_FLAGS2_BIT_0`, this is the other half of
    `actor_damage_followed`: `WB_ACTOR_FIELD_31` is how far the knock-back has left to run and
    `WB_ACTOR_FIELD_30` which way, two are spent a frame, and LANDING lowers the gate instead.
  * **the ACCELERATOR** — `WB_ACTOR_FIELD_22` is the speed, `WB_ACTOR_FIELD_23` the direction it is
    travelling (zero LEFT, `WB_ACTOR_ST_BYTE` right) and `WB_ACTOR_FIELD_24` a counter that lets the
    speed rise on ONE FRAME IN FOUR, up to `WB_EFFECT_STATE_BD6A + WB_PLAYER_WALK_SPEED_BIAS`.

**AND THE ACCELERATOR'S TWO ASYMMETRIES ARE BOTH REAL.** Holding the direction the record is NOT
travelling sheds speed instead of raising it, at `subq.b #2` turning to face RIGHT and `subq.b #1`
turning to face LEFT — one constant would have answered every other row in the battery, so
`test_THE_TURN_IS_NOT_SYMMETRIC` drives both. And the ceiling is `addq.w #4` on the state word with
`cmp.b 22(a0),d0` on its LOW BYTE, where the jump machine's `addi.b #$8` is a byte add on the same
word: a state word of `$00fc` therefore clamps the WALK to a standstill (`$0100`, low byte 0) and
leaves the JUMP at 4. That is phase A's `WB_EFFECT_STATE_BD6A` finding closed from the other end, and
the constant it wanted — `WB_PLAYER_WALK_SPEED_BIAS` — exists now.

**WHAT THE WEAPON IS, and it is the game's SPECIAL ATTACK.** Four gates in series (no ladder tile
under the player, the record list's write pointer off its base, `joy1_newly_pressed` **exactly**
`$80`, and DOWN held), then the newest record's HIGH byte — which is the high half of the
`WB_PICKUP_RECORD_*` word the grant pushed — picks one of four arms: the LIGHTNING (whose whole body
is `move.w #$2,$714.w`, so it is the only item that costs no actor slot), the WIND SPOUT (behaviour
slot 48), the FIREBALL (slot 50) and the BOMB (slot 49, the arm the `bra.w` falls to). Every arm that
allocates then spends one packed-BCD unit off `WB_RECORD_LOW_BYTE` and POPS the record when the count
reaches zero.

**THE `cmp.b #$80,d0` IS AN EQUALITY, AND THAT IS A FINDING ABOUT THE CONTROLS.** The byte it tests
is `current & ~prev`, so DOWN has to be held FROM THE PREVIOUS FRAME — pushing down and fire together
produces `$82` and fires nothing. And `player_step_and_arm`, one `bsr` EARLIER in the same frame,
reads the same byte with `tst.b d0 / bpl` and arms the record on bit 7 alone. So one joystick frame,
two readings, and a paired case on each side says so.

**THE `sbcd` AT $1260 IS THE FIRST THREADED SITE IN THIS PROJECT WHOSE OWN ARMS DISAGREE.** The
scoped truth about include/hud.h's table, because the first draft of this sentence flattened it:
of the five sites it tabulated, $6c26's bit is produced INSIDE `actor_defeat_and_score` and IS
driven by an ordinary row; two more ($4e5a, $522e) are differential-PINNED over the paths their
seeds take, which that header is careful to call weaker than a proof; and only the shop's pair is
genuinely unreachable, because `emu.run` forces the CCR clear and no case can enter with X set.
What is new here is a single site that is BOTH at once, arm by arm: the FIREBALL's
`subq.w #8,2(a1)` is the only arithmetic instruction between that arm's `bsr $1b8e` and the `sbcd`
(`btst`, `bset`/`bclr`, `clr.b`, `movea`, `lea`, `move`, `cmpi`/`cmpa`, `tst` and `addq.l` on an
ADDRESS register all leave X alone), so the bit is a BORROW out of the shot's own y and an ordinary
differential row drives it either way — a fireball launched from a y below 8 costs TWO units. The
other three arms carry the caller's X, which is `player_step_and_arm`'s exit ($a4a and $a4e are
adjacent `bsr`s) and is data dependent; those are pinned for X = 0 only, and one
`run_candidate_only` row against an independent model of the arithmetic says the parameter is live.
`sbcd_byte` left src/hud.c's private block for include/hud.h to serve it, which is exactly what that
header's own note said would happen when a second module executed one.

**THE $1f54 / $1fa2 EXTENT CONFLICT IS RESOLVED, AND IN $1f54's FAVOUR.** ../names.txt gave `$1fa2`
(`actor_event_anim_step_2394`, `# ctx`) a routine of its own with a 186-byte body lying INSIDE
`player_stage_transition`'s stated `$1f54..$21e3`; one of the two had to be wrong. Measured: a
whole-image census over every branch form, both absolute encodings, both PC-relative ones and the
mode-shaped sweep finds **EXACTLY ONE** instruction naming `$1fa2` — the `beq.w` at `$1f62`,
twenty-two bytes into `$1f54` itself — and **no longword or word operand anywhere holds the
address**. So it is a CONTINUATION, the arm the second flag test falls to, and its own `beq.w $1fd6`
carries the same chain on: `$1f54 / $1fa2 / $1fd6 / $1ffc` is one flow graph with `$205c` and `$205e`
as its shared tails. **THE `fn` DIRECTIVE IS DELETED, NOT RENAMED, and the difference is the whole point.** An earlier
draft of this section announced `actor_event_anim_step_2394` -> `player_stage_transition_anim_2394`;
NO SUCH NAME EXISTS anywhere in the tree, and a reader who believed it would re-add an `fn` at
`$1fa2` — which is precisely what re-creates the conflict, because `ApplyNames` DEFINES a function
at an `fn` and Ghidra then truncates `player_stage_transition` there. What happened is that
`fn 0x1fa2` was REMOVED and the `cmt` kept: the plate IS the label, which is the convention the
`$1bb4..$1cbf` continuation already follows (it "carries no name at all"). `grep -rn "^fn 0x1fa2"
../names.txt` returns **0** and `grep -rn actor_event_anim_step_2394 ../names.txt include/ src/`
returns **1**, the retraction sentence itself; this file's historical batch sections keep the old
name as they wrote it and this section is the retraction that describes them.

**$1208 AND $ec8 LOSE THEIR `# ctx` TAGS; $b1a KEEPS ITS NAME AND LOSES ITS TAG TOO.**
`player_pending_event_gate` was read this phase and not ported, which is a different result from
either: three word flags in order with an arm each is what the body does, so the name stands. What
the reading ADDS is why it is unportable, measured rather than assumed — `bsr.w $1f54` at `$bb0`,
`bsr.w $19ac` at `$c66`, `jsr $fe8c.l` at `$c00`, and **TWO exits that are `lea 4(a7),a7 / jmp`**
(`$bdc` into `$e494`, `$c20` into `$e5ba`), which pop a return address and so do not return to the
caller at all. The one piece of it this port has is the spawn at `$c52`: `lea $998c.l,a2 /
lea $537e.l,a1 / bsr.w $539e`.

**AND THAT COMPOSITION IS PINNED, which retires the second of phase A's two honesty items.**
`scene_copy_record_fields`' register convention was the recorded live failure mode — a2 the
DESTINATION, a1 the TEMPLATE, in that order — and every case in the battery supplies both registers
itself, so a port that swapped them stayed green. The case now DECODES the two `lea`s out of the
image at `$c52` and runs the differential with the operands the site really carries. The first
honesty item went the same way: `player_reset_ground_state`'s two call sites are `$fb2` and `$101e`
inside the walk, and two ladder rows now run them.

**FIVE PLATE CORRECTIONS AND ONE CONSTANT RENAME.**
  * **`$1fa2`** — above, with its grep count.
  * **`$1f54` said "covers $1f54..$21e4"**; `$21e4` is `WB_EFFECT_STATE_21E4`'s own first byte. The
    code is `$1f54..$21e3`, 656 bytes — the figure the partition already used, so the two agree now.
  * **`$1f54` claimed to be the frame's last call and nothing else.** It has TWO `bsr` callers,
    `$a70` and `$bb0`, which is what makes "sits on nearly every arm of the gate" a measurement.
  * **`$a38` said FOUR of the nine are reconstructed.** It is SIX.
  * **`$ec8`'s plate described only its first section** ("runs 29(a0) as a step COUNT ... then reads
    joy1_newly_pressed"), which is two of five. Rewritten whole.
  * **`WB_ACTOR_FLAG_FIRED_BIT` is a NEW name off a THREE-SITE census**, not a rename: the immediate
    bit-operand sites over `8(An)` for bit 7 in the whole image are the `bset` at `$efa`, a `bclr` at
    `$212a` and the `btst` at `$20ca` — and both of the latter are inside `player_stage_transition`,
    which is where `WB_ACTOR_FLAG_MOVED_BIT`'s one reader (`$2184`) also lives. So what BOTH of the
    walk's flag writes buy is decided in the one routine of the frame this port still lacks.

**MACHINERY: THE TWO STEP HELPERS MOVED TO include/map.h.** `step_left`/`step_right` — one probe with
the ground flags no caller reads dropped — were src/behavior.c's, and the walk's SIX probe sites —
three direction pairs, one per section that moves the record — made src/player.c their second
module. They are `static inline` in the header both files already
include, the same rule and the same shape as bus.h's record accessors, and behavior.c's
twenty-four call sites are untouched.

**AND SIX ENCODERS REACHED A THIRD, FOURTH OR FIFTH COPY** — `tst_b_dn`, `cmp_b_imm_dn`,
`cmpi_b_ind`, `cmpa_l_imm`, `move_w_imm_d16` and `move_l_imm_d16`. Each carries an ALSO IN note in
test_player.py naming its siblings, exactly as test_behavior.py's queue does; hoisting them edits six
batteries, so this file registers the move rather than the batch making it. `move_b_d16_d16` is the
one to be careful with: test_behavior.py's copy takes its four arguments in the OPPOSITE order, which
is the `adda_w_dn_an` collision one address over, so whichever hoist takes it has to pick a
spelling. **AND `cmpi_b_ind` ALMOST BECAME THE SECOND SUCH COLLISION IN THIS COMMIT** — the
first draft here spelt it `(value, base)` where all three siblings take `(base, value)`, which
the review gate caught. It is spelt their way now, which is the rule a DEFERRED hoist has to
follow: a copy that disagrees with the copies its own note names is worse than a copy.

**MUTATION SWEEP: 35 MUTANTS OVER FOURTEEN PRE-HOC AXES — 31 CAUGHT FIRST TIME, and 34 on the
final tree — and every one of the four that were not is a different lesson — one BADLY BUILT, one SEEDING BUG, one COVERAGE HOLE and
one argued equivalence.** The axes: the knock-back's direction and the count it steps by; the fire
edge's width; the flicker countdown's order and what its last frame lowers; the drift's spend order,
its gate and its zero-count probe; the sub-frame mask; the ceiling's operand size and its SIGNEDNESS;
the two turn rates, the turn's sign test and which way it steps; the direction test's order; the
ladder exit's guard; the coast arm's three decisions; the weapon's four gates; the spend's BCD, its
extend and its pop; the full-pool refusal; and six fields of the three spawn arms.

  * **`flicker/countdown-read-BEFORE-the-spend` was BADLY BUILT** — batch 40 phase A's
    `jump/ascent-tests-before-the-spend` in the same file, one section over. `spend(x) != 0` and
    `x != 1` are the same function on every input; the mutation that means anything tests the byte
    against ZERO before the decrement, which differs at a countdown of 1 (the original ends the
    flicker, the mutant returns) and at 0 (the reverse). Re-spelt as
    `flicker/countdown-tested-BEFORE-the-decrement` it is **caught**, by the two rows that already
    existed.
  * **`weapon/fireball-clears-the-sprite-WORD` SURVIVED BECAUSE THE SHOT RECORD WAS NOT SEEDED**, and
    the cause is `leaf.overlay`'s own documented hazard firing for the fourth time in this project.
    The high pool's first record starts AT `POOL_LO`, so `pokes[record + WB_ACTOR_X]` shared a dict
    KEY with `pokes[POOL_LO]`'s 192-byte keyed block and `dict` kept the last — 190 bytes of the
    pool ran on the .PRG's zeros, where a byte the port clears and the original does not reads the
    same either way. The pool is its own `overlay` layer now, and the mutant is **caught**.
  * **`drift/zero-count-takes-no-probe` WAS A REAL COVERAGE HOLE, and closing it needed the map's
    own edge arm.** A probe of zero pixels stores the x UNCHANGED, and no memory differential can
    see a store of the value already there — not even the poison pass, which inverts the destination
    on BOTH sides. What makes it observable is `actor_step_left_against_map`'s NEGATIVE-probe arm: an
    x below the record's own WB_ACTOR_HALF_WIDTH parks it AT that half width, so the zero step moves
    something after all. One row seeds exactly that and the mutant is **caught**.
  * **`walk/coast-clears-on-a-nonnegative-result` SURVIVED AS AN ARGUED EQUIVALENCE.** `< 0` and
    `<= 0` differ only on a result of exactly zero, i.e. a speed of 1 — and on that frame the
    original falls to the tail, which re-reads the now-zero byte and takes no probe, while the mutant
    stores a zero over a zero and returns. Both leave the same image. It is an equivalence under this
    harness rather than a hole, with the geometry as the argument.

**AND $205c IS THE SAME SHAPE ONE ADDRESS ON, REGISTERED RATHER THAN RESOLVED.** `stub_rts_205c` is
an `fn` inside `player_stage_transition`'s newly stated body, exactly what the `$1fa2` plate says an
`fn` must not be — but the census separates them: `$1fa2` is named by a `beq.w` alone while `$205c`
has FIVE namers, one `bsr.w` at `$2010` and four `bra.w` (`$1ff8`, `$2034`, `$203e`, `$2052`). The
`bsr` makes it a genuine call target, so the directive stands and the plate now carries the census.

**THE RE-RUN, TWICE.** The four above plus FOUR CONTROLS (`walk/turn-rates-equal`,
`weapon/spend-drops-the-entry-extend`, `knock/side-inverted`, `weapon/full-pool-spends-anyway`) were
re-run on the repaired tree: 7 caught and the equivalence unchanged. The controls are there because
two of the repairs were to the BATTERY, and generalising a seed can weaken it into vacuity.

Then the REVIEW GATE below moved src/player.c again — two re-reads into the accelerator, a return
value out of the fireball, one allocation lifted out of three arms — so the WHOLE THIRTY-FIVE were
re-spelt against the shipped tree and re-run end to end: **34 CAUGHT, and the same single
equivalence**, with `make test` green from a clean `build/` either side. That is the rule a sweep
has to obey rather than a courtesy: a sweep measures the tree it ran on, and this batch's tree moved
after the first one.

**NOT PINNED, HONESTLY.**
  * **The `sbcd`'s entry X on the WIND SPOUT, BOMB and LIGHTNING arms.** The bit is
    `player_step_and_arm`'s exit and no case can enter with the CCR set; the reconstruction threads
    it and one `run_candidate_only` row proves the parameter live, which is weaker than the oracle
    and stronger than nothing. Same standing as include/hud.h's other threaded sites, which that
    header's table now lists as SIX with this one named as the drivable exception.
  * **`player_step_and_arm`'s own exit X**, which is what that bit IS: a `subq.b`/`addq.b` on one of
    four record bytes, or the map probe's own arithmetic, depending on the path. Reading it per path
    is only worth doing once the frame top is ported and something can compose the two.
  * **The registers either routine leaves behind.** `$a4e` overwrites the walk's d0 unread and the
    weapon's caller reads nothing, so both are `void`.
  * **What `WB_ACTOR_FLAG_FIRED_BIT` and `WB_ACTOR_FLAG_MOVED_BIT` BUY**, unchanged from phase A and
    now with the address of every site.
  * **The double writes.** `addq.b #1,24(a0)` then `andi.b #$3,24(a0)` are two stores to one byte and
    `subq.b #1,22(a0)` then `clr.b 22(a0)` two more; the ledger records final values, so folding each
    pair is unobservable — the same silence `player_climb`'s x and y carry. What is NOT folded is the
    TEST after the first pair, which re-reads the field (see the gate below).
  * **Every arm's behaviour for a record the BUS REFUSES.** The re-reads below are spelt for it and
    the write guards are bus.h's, but the player's record always comes out of the actor table, so no
    case here addresses one — the same silence phase A's aliasing reads carry.

**THE REVIEW GATE, five reviewers, and what it changed.** ONE CORRECTNESS finding, and it is the
class this file defends everywhere else — A VALUE CARRIED IN A LOCAL WHERE THE ORIGINAL RE-READS
MEMORY. `player_accelerate_walk` tested its own computed sub-frame counter and its own computed
speed, where `andi.b #$3,24(a0)` and `cmp.b 22(a0),d0` both FETCH the field again. For a record at
an address bus.h refuses the store is dropped and the fetch answers ZERO, so the two take opposite
arms; nothing in this project can reach such a record (the player's comes out of the actor table),
which is why it is latent — but `spend_field_b`'s own plate states the rule and
`player_spend_one_shot` obeys it, so the walk does now too, with the asymmetry named at the site.

The rest were counts, claims and duplication, and four of them were claims that had gone FALSE
rather than claims that were merely thin:
  * **include/map.h GENERALISED A SCOPED CLAIM INTO A WRONG ONE during the helper move.**
    src/behavior.c's deleted comment said "six routines HERE take a step and none of them reads d1";
    the header said "no RECONSTRUCTED ROUTINE reads the d1". It has four — the sites that feed the
    ground word to `actor_toggle_side_flag` and `actor_turn_and_launch` keep their own `ground`
    local. A reader trusting the header would delete that plumbing. Scoped back to the wrappers'
    users, and the same plate's "four steps of its own" corrected to SIX probe sites.
  * **include/hud.h's threaded-extend table was not updated for the site this batch adds.**
    include/player.h points AT that table for the reading, and the table still said FIVE. It says
    SIX now and names $1260 as the one a case can drive.
  * **THREE MORE PLATES CARRIED THE RETRACTED $1fa2 READING** — `cmt 0xb16`, `cmt 0x2394` and
    `WB_EVENT_ANIM_DONE_B16`'s own comment, all still saying "a THIRD animation stepper ... unnamed
    and unported". The flag word is the natural way IN to that code, so the retraction was findable
    only from the plate that made it. `grep -r "a THIRD animation stepper" ../names.txt include/
    src/` returns **1** — the retraction sentence in wonderboy.h.
  * **AND THE `fn 0x1fa2` DIRECTIVE ITSELF SURVIVED THE RETRACTION.** `ApplyNames` DEFINES a
    function at an `fn`, so the next `reapply.sh` would have re-created the exact extent conflict
    this batch measured away — Ghidra truncating `player_stage_transition` at `$1fa2`. The directive
    is gone; the plate is the label. $205c is the same shape one address on and is registered above
    rather than removed, because its census finds a real `bsr`.
  * **test_player.py's own MODULE DOCSTRING was the pre-phase-B one** — "these five routines", "four
    of the five are named by ONE instruction", and "NO MAP PROBE IS REACHED ... no case here seeds a
    map" directly above the file's own `from test_map import map_pokes`.
  * **THE ALLOCATOR CAP WAS MEASURED WRONG AND RESTATED RATHER THAN IMPORTED.** The first draft
    counted `actor_alloc_slot_high`'s loop at three instructions where it is four, in a file whose
    `_cap` docstring promises "nothing here states a round number"; it stayed green only on the
    slack `_cap` adds. It takes `ALLOC_INSN_PER_SLOT` from test_actor.py now, which is the battery
    that owns the routine — the same rule the models and the write sets already follow.
  * **`_spend_bytes` WAS A FOURTH STATEMENT OF PACKED BCD**, where `leaf.bcd_expected` has stated it
    in decimal since batch 33 and takes the borrow-in this needed. It also answered confidently
    outside the digit range, where `bcd_expected` declines to predict.
  * **AND THREE SMALLER ONES**: `player_arm_fireball` wrote its borrow through `&entry_extend`, so
    the value `player_spend_one_shot` received no longer matched the name it was passed under (it
    RETURNS the borrow now, into a local the site names); the three spawn arms each spelt the same
    allocate-and-bail, which is one call in the `else` of the lightning test and provably the same
    three (the allocator writes no memory and the lightning arm never reaches it); and
    `_weapon_spawn_pieces` decided its instruction ORDER by comparing its own label string.

**THE INDEPENDENT GATE, two reviewers, and TWELVE items — of which the sharpest were not about the
code at all.** Both routines were re-read instruction for instruction and found clean, the `$1fa2`
census reproduced exactly, and the standstill and borrow claims confirmed on both cores. What it
changed:

  * **COVERAGE (two items, both provable).** The entry-X carrier row ran the LIGHTNING arm only,
    where the wind spout and the bomb reach the same `sbcd` through the allocator and
    `player_arm_thrown_shot` first; a port that dropped the bit on ONE of those paths answered the
    single row identically. Parametrised over all three, and proved: an arm-local mutant
    (`extend_at_sbcd = 0` on the bomb path alone) **reds the bomb row and only the bomb row**. And
    the five refusal rows asserted "wrote nothing" with no witness of WHICH gate refused — which is
    load-bearing for the FULL-POOL rows, because four gates and a four-way dispatch sit above the
    allocator and every one of them also refuses by writing nothing. Each row now witnesses its own
    refusing instruction through `leaf.pc_coverage`, and states what that witness IS: the bitset
    marks the ORACLE's PCs, so it is a PREMISE GUARD on the seed and no C mutant can red it. Proved
    with a SEED mutant instead — dropping DOWN from the full-pool seed leaves the write set
    identical and **reds all three rows**.
  * **AN X-PRESERVATION CENSUS THAT COULD NOT CLOSE ITS OWN CLAIM.** The enumeration behind "nothing
    on these three arms writes X" omitted `eor.b` and `and.b` — and those are `joy1_newly_pressed`'s
    last two instructions, which run on EVERY path to the `sbcd` including the lightning's, whose
    plate called `move.w #$2,$714.w` "the whole arm". It also described `actor_alloc_slot_high` as
    five instructions; it is NINE, with `beq` and `rts` unlisted. The conclusion survives — logical
    ops set N/Z, clear V/C and leave X alone; `dbf` writes no condition code at all — but a claim of
    this shape is only worth the completeness of its list, so player.h and `cmt 0x1208` now carry
    the whole enumeration and the corrected count.

**AND SIX PLATE CORRECTIONS, of which the first is the one that would have cost a batch.**
  * **A PHANTOM RENAME.** This section announced `actor_event_anim_step_2394` ->
    `player_stage_transition_anim_2394`. There is no such name: the directive was DELETED. A reader
    who believed the sentence would re-add an `fn` at `$1fa2` and re-create the Ghidra truncation
    this batch measured away — the single most expensive misreading available in this section, in
    the sentence most likely to be acted on. Rewritten to what happened.
  * **AN INHERITED ERROR IN THE NEW `$1fa2` PLATE**: "slots 35 and 36 are the rows that RAISE it".
    The raisers of `event_anim_done_b16` are slots 36 ($53d6) and 37 ($5400); slot 35's raise writes
    `$b12`. The correct census was three lines away in `cmt 0xb16` — a rewritten plate inheriting a
    clause from the plate it replaces is its own class.
  * **PHASE A'S CLAIM WAS LOAD-BEARING AND WRONG, AND PHASE B REVERSED IT SILENTLY.** That section
    says the last X-writer on three arms is inside `joy1_newly_pressed`; that routine writes NO X,
    which is exactly WHY the port takes the bit as a parameter. Annotated as corrected IN PLACE, in
    the marked-correction form this file uses, rather than left for a reader to hit first.
  * **AN OVER-GENERALISATION IN THE `sbcd` HEADLINE**: "hud.h tabulates five threaded sites and every
    one of them is unpinnable". One ($6c26) is driven by an ordinary row and two more are pinned over
    their exercised paths — that header says so two paragraphs below the sentence being cited.
    Scoped, here and in hud.h's own heading and test_player.py's.
  * **FOUR-VERSUS-SIX**, in three places: the walk has SIX probe sites, and up to THREE fire in one
    frame (the knock-back's, the drift's and the accelerator's tail — nothing makes those sections
    exclusive), where the cap comment said two.
  * **AND THE MARKERS AND THE FILING**: the partition's `$ec8` and `$1208` rows carried no landed
    marker while every other landed row does, and phase B's carried-forward queue had been filed
    INSIDE phase A's section, directly above phase A's own paragraph still listing `$1fa2` as open.
    The live list is at the END of this file now and phase A's is annotated in place, so a linear
    reader and a last-section reader get the same state.
  * **RUNNER-UP SWEEP**: a present-tense "../names.txt gives `$1fa2` an entry" for a directive that
    no longer exists; `cmt 0x205c`'s "the `fn` below" (it is above); `WB_ACTOR_FLAG_SIDE_BIT`'s "its
    only reader in the image is the `btst #3,8(a1)` at $51e" — true of the a1 FORM alone, where the
    census finds **139 operand sites**, 83 of the `btst`s on a0 and two of those added by this batch,
    so it now carries the census its `WB_ACTOR_FLAG_MOVED_BIT` sibling already had; and the `$1fa2`
    pin covered CONTROL FLOW only, where a dispatch row is reached by a DATA longword — the scan is
    extended over aligned word and longword operands and finds none, which is the half that would
    have mattered had the answer been different.

**QUEUED — PHASE C, in the order the frame calls them.**
  * **`$b1a` `player_pending_event_gate` (526 B)** — needs `$1f54` and `$19ac` first, and its two
    stack-popping `jmp`s will be boundaries of a kind this port has not had.
  * **`$19ac` the SCENE-SPAWN TREE (592 B plus `$1cc0`'s 94 and `$1d1e`'s 536)**, with
    `speech_script_step` (`$1b46`, 34 B, `# ctx`, SHARED between it and the `$151a` tree — whichever
    lands first ports it).
  * **`$151a` `player_collide_and_scroll` (1,170 B)**, the largest single routine in the game.
  * **`$1f54` `player_stage_transition` (656 B)**, now with no extent conflict attached and with its
    two callers known. It holds the only readers of the walk's two flag bits.
  * **`$a38` the frame top (62 B) LAST**, and the dispatch row flips with it.

**QUEUED, CARRIED FORWARD — THE LIVE LIST** (phase A's, less what phase B discharged): `abcd_byte` —
and now `sbcd_byte` beside it — to the kit; regenerate `../out/names_dump.txt`, `../out/hw_scan.tsv`,
`../decomp.c` and `../out/wonderboy_dis.txt`; `bus.h` to the kit; the `$1ab4` boundary; the tier
partition; the `scene_run_effect` latent guard; the second reader of `actor_type30_drift` at `$b84`;
the two remaining duplicate `cmt` directives (`0x1023a`, `0x10394`); the `WB_HUD_SLOT_BBC2` / `_BBC6`
renames. **NEW IN PHASE B:** SIX ENCODERS to `leaf.py` (`tst_b_dn`, `cmp_b_imm_dn`, `cmpi_b_ind`,
`cmpa_l_imm`, `move_w_imm_d16`, `move_l_imm_d16`), each carrying an ALSO IN note in test_player.py —
and `move_b_d16_d16`, whose two copies take their arguments in OPPOSITE orders; and `fn 0x205c`, an
`fn` inside `player_stage_transition`'s body which the census leaves standing because a real `bsr`
names it. **DISCHARGED IN PHASE B:** the `$1fa2` extent conflict AND its `fn` directive, and both of
phase A's honesty items about routines with no caller.
