# Reconstruction status — Zynaps

Human-readable C reconstruction of Zynaps (Hewson, 1988), each function **verified byte-for-byte
against the original 68000 code** by the shared differential harness (`tools/recreate_kit`: a
Musashi oracle running the real code vs. the compiled reconstruction, on the same memory image).
`../names.txt` is the source of truth for every name; it names all 188 functions, of which these
are the ported ones.

**Verified: the sum of the per-section counts below**, out of 188. Each `## Verified — <subsystem>`
heading carries its own count, so the only number an agent touches is its own section's;
`test/test_status.py` fails if a count and its rows disagree, and if a section names a subsystem
with no `src/<name>.c`.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table, and the conventions all live there rather than being restated here.

Where an argument is load-bearing it has ONE home, cited from the others:

| the argument | its home |
|---|---|
| which globals the enemy subsystem BORROWS from another owner, and why | `include/enemy.h`, "BORROWED" |
| why `tos_malloc_unused` is safe (the byte scan) | [`project.toml`](project.toml), re-tested by `test/test_heap_guard.py` |
| where each shipped preshift width comes from | `src/sprite.c`, "SHIPPED WIDTHS" |
| why the fuzz caps the frame width | `test/test_sprite.py`, `FUZZ_MAX_FRAME_BYTES` |
| what the entity record's fields are, and which are held by a test | `include/entity.h` |
| how the differential method works | [`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) |

## Verified — entity (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13c9e` | `entity_kill_if_offscreen` | 54 | ✅ verified | all 36 combinations of the four box bounds one step either side; the dead-record early return; extreme coordinates at both ends of the word; six flag words through both the clearing and the non-clearing arm, which pins `clr.b` against `clr.w`; 600-case sharded fuzz clustered on the boundaries; poison on the clearing arm. THREE RESIDUALS, all proved unobservable rather than untested — the `tst.w`-vs-`tst.b` guard, the early return, and the coordinates' signedness; see the ledger below |

## Verified — enemy (23)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13828` | `count_free_wave_slots` | 48 | ✅ verified | all eight records free and all eight in use; a single free record at each of the eight positions (which pins the walk's direction and its stride); alive bytes 0x01/0x7f/0x80/0xff, so `tst.b` is held as a test against zero rather than against 1; 60 random alive vectors. The published byte sits under a canary, so a candidate that computed the count and forgot to store it differs; poison on the all-free case |
| `0x14be0` | `enemy_alloc_slot` | 54 | ✅ verified | one free record at each of the eight positions, compared against the ORACLE'S OWN A2 as well as the carry byte, so "a free slot" is not mistaken for "the first free slot"; several free at once; both failure shapes, with a recognisable A2 going in — the zero-count arm never loads A2 and must return the caller's; 60 random alive vectors. The carry reaches the diff through the `scs` stub (`test/abi.py`, `flag_call_pokes`); poison on the multi-free case |
| `0x13bc2` | `entity_type_in_mask` | 28 | ✅ verified | all 256 types the `andi.w #$ff` admits, sharded four ways, against a pseudorandom 0x20-byte map — 0x20 because the largest type resolves 0x1e past the base, which the game's own 8-byte class maps do not cover; sixteen single-bit maps with the one type that must see each, which is what pins the MSB-first bit order (`not.w`); junk above D0's low byte; poison on four types. The answer is the Z flag, through the `seq` stub |
| `0x14c44` | `actor_clamp_y` | 34 | ✅ verified | both bounds one step either side, the far ends of the word, and 200-case fuzz clustered on the band. The FLOOR's signedness is pinned (0x8000 clamps up when read signed and is left alone when read unsigned); the ceiling's cannot be — see the survivor below |
| `0x14a64` | `actor_despawn` | 24 | ✅ verified | squadron ids 0, 1, 5, 0x0f, 0x7f, 0x80 and 0xff over a 0x100-byte noise band centred on the counter array, which is what turns the SIGN EXTENSION into a diff rather than a coincidence; a counter of 0 wrapping to 0xff; all four combinations of "set" for the alive byte and its pixel-hit neighbour, which is what holds `clr.b` against `clr.w` — an earlier revision seeded the pair 0x00ff, so the alive byte was already 0 and deleting the store left that case green (measured, then fixed); poison on every id |
| `0x1499e` | `enemy_move_type16_left` | 52 | ✅ verified | fourteen x values around 0, the kill edge and both ends of the word, each against three freeze bytes; 150-case fuzz. The squadron counters are seeded noise, so the despawn's decrement is attributed; poison on the moving arm |
| `0x14ec4` | `enemy_move_type17_left` | 22 | ✅ verified | the same fourteen x values. It retires at ACTOR_KILL_X rather than at zero and does NOT touch the counters — the seeded counter band is what proves the second half; poison on the kill arm |
| `0x149d2` | `enemy_move_type15_dive` | 146 | ✅ verified | the arming cone at five offsets either side of `dx <= |dy|` (dropping the `neg.w` on dy fails at once); the climb through the retire edge; the despawn off the left; both freeze arms, armed and not; 200-case fuzz over the whole playfield with a random player position. The player record is seeded noise, so reading the wrong field of it differs; poison on the climb |
| `0x14ce8` | `actor_script_op_loop_begin` | 24 | ✅ verified | all 256 opcode bytes, sharded four ways — which pins `andi.b #$78` + `lsr.b #3` against the bits above and below it — with the pc and loop-start words distinct noise, so copying the wrong direction or the wrong width differs. Carry through the `scs` stub |
| `0x14d00` | `actor_script_op_set_fire_rate` | 20 | ✅ verified | all 256 opcode bytes, sharded; D1 dirtied in bits 8..15 and 16..31 with the SAME value given to both sides, so a glue folding the high half into the opcode is killed (measured; an earlier revision handed the candidate a clean byte and could not fail on it); both bytes written are compared, so a candidate writing the countdown and not the reload differs |
| `0x14dc0` | `actor_script_op_drift_left` | 24 | ✅ verified | fourteen x values against both freeze arms. BOTH arms answer carry clear — the freeze arm because `tst.b` clears C — and the stub compares that byte on every case |
| `0x14dd8` | `actor_script_op_halt` | 10 | ✅ verified | eight noise records: both velocity words are non-zero going in, so clearing one, or clearing a longword across the pair, differs; poison on every case |
| `0x14e00` | `actor_script_op_loop_end` | 28 | ✅ verified | counts 0, 1, 2, 0x7f, 0x80 and 0xff — 1 falls out of the loop and 0 wraps to 0xff and stays in it, which is what separates this from a `dbf`; eight records with distinct pc and loop-start words; poison |
| `0x14e50` | `actor_script_op_step_left` | 12 | ✅ verified | fourteen x values with the freeze byte SET, which is what separates it from the drift above: this step is unconditional |
| `0x14730` | `anim_enemy_type12` | 62 | ✅ verified | twelve frame bytes including the four the cycle produces, the wrap point, and the out-of-range 0x10/0x80/0xff that pin `andi.l #$f`; SIX gate values per handler, not two, which is what separates `tst.b` from an equality test; poison on two frames. The four handlers share one C body, so their tables are the only thing telling them apart — and `test_anim_frame_tables_are_distinguishable` asserts the shipped image really does hold four different ones, rather than leaving that to luck |
| `0x1476e` | `anim_enemy_type14` | 62 | ✅ verified | the same battery, from its own frame table |
| `0x147ac` | `anim_enemy_type15_diving` | 70 | ✅ verified | the same battery plus its SECOND gate: the dive flag clear blocks it where its three siblings would run |
| `0x1483e` | `anim_enemy_type17` | 62 | ✅ verified | the same battery against the OTHER phase byte and the OTHER polarity — this one runs while its gate is set; inverting the test is killed |
| `0x1530e` | `enemy_set_sprite_b` | 36 | ✅ verified | all 256 headings, sharded four ways, over noise-seeded spans either side of BOTH tables (0x100 bytes around the variant table, 0x400 around the pointer table) — which is what makes the two consecutive SIGN EXTENSIONS observable rather than assumed; poison on four headings |
| `0x15332` | `enemy_anim_puff_b` | 62 | ✅ verified | ten frame bytes through the one-shot's kill at frame 5, which is what separates it from the four cycling handlers; three blocking gate values; poison on two frames. Killing with a word clear instead of a byte clear is caught |
| `0x14626` | `anim_ground_objects` | 88 | ✅ verified | ten frame bytes including 0x7f/0x80, which pin the SIGNED wrap (`cmp.b #$4` / `blt`) — an unsigned reading fails there; both record guards and their interaction over a mixed array; three blocking gate values; a seventh live type-0x34 record past the six, which pins the loop count against the enemy-shot slots that follow; 50-case fuzz; poison |
| `0x159f2` | `asteroids_move` | 120 | ✅ verified | the y wrap at every edge in BOTH directions (the two ends restart at different values, so one range check would fail at 0 going up); both x step widths against the same nine x values including the kill; a nineteenth record past the eighteen, which pins 6 x 3 against the boss records that follow; 40-case fuzz; poison on a mixed alive vector |
| `0x15a6a` | `asteroids_animate` | 100 | ✅ verified | the half-rate gate at four toggle values — `not.b` flips AND tests, so the flip must happen on the blocked call too; eight frame bytes through the six-frame cycle and its signed wrap; the column offset advancing over a DEAD record, which is what pins it as positional rather than as a running total; 40-case fuzz; poison |

### Mutation check — enemy and mothership

**Sixty-eight mutations across both subsystems, 66 killed, 2 survivors** — every one rebuilt after
`rm -f build/*.so` (make's ~1 s mtime granularity has re-run an unmutated oracle in this workspace
before) from a green baseline. Every loop count, record offset, table stride, mask, threshold, sign
extension, gate polarity and store width in `src/enemy.c` and `src/mothership.c` was flipped, plus
one glue mutation per answer shape. The two survivors are below; both are UNREACHABLE rather than
untested, and neither can be reached by seeding real data.

| mutation | result |
|---|---|
| `actor_clamp_y`'s CEILING read unsigned | **SURVIVED — unreachable** |
| the mothership bank index read unsigned (`ext.w` dropped) | **SURVIVED — unreachable** |

* *The ceiling's signedness.* Whatever reaches the second test has already been through the floor,
  so it is 0x0010..0x7fff, where the signed and unsigned readings agree on every value. The FLOOR's
  signedness IS pinned — reading it unsigned is killed by the 0x8000 case — and the difference is a
  property of the order the two tests run in, not of the battery.
* *The bank index's.* `sign_ext8(stage - 2)` turns negative only below stage 2, and stage 1 takes
  the copy branch while stage 0 cannot be entered at all (the caller at 0x1117e guards on
  `tst.b / beq`, and the finish arm clears the byte). It stays as written because it is what the
  instructions do, in the same spirit as `src/sprite.c`'s slot step.

TWO EARLIER SURVIVORS WERE COVERAGE HOLES AND WERE FIXED, not recorded — the sweep is what found
them, which is the point of running it rather than quoting the last one. `actor_despawn`'s only
store could be DELETED and the case named after it stayed green (its record seeded the alive byte to
0, so the clear wrote 0 over 0); and the glue folding D1's high half into the opcode was invisible
because the case handed the oracle a dirty register and the candidate a clean one. Both cases were
repaired and both mutants now die. A third apparent survivor, `SCRIPT_OPERAND_MASK` 0x78 -> 0x7c,
was an equivalent mutant — bit 2 shifts out — and is replaced in the table by 0x78 -> 0x38, which
dies.

### Not reconstructed here, and why

| Addr | Name | Blocked on |
|---|---|---|
| `0x14c66` | `actor_script_run` | the eight class arms of 0x19438, entry by entry: 0 = `entity_apply_accel` 0x143f8 (**util**), 1 and 2 are the two ported above, 3 = `actor_script_op_bounce_fall` 0x14d14 (**collision**), 4 = `actor_script_op_fire` 0x14d88 (**weapon**), 5 = `actor_script_op_set_heading` 0x14da2 (util's 0x142d4 / 0x14306), 6 = **a NULL longword** — so no shipped opcode can have `op & 7 == 6` — and 7 = `actor_script_op_ext` below. TWO of the eight are ported, not four |
| `0x14cce` | `actor_script_op_ext` | the 16 entries of 0x19458, entry by entry: 0, 1, 3 and 6 are ported above; 2 (0x14de2) and 5 (0x14e38) reach **util**'s 0x142d4 / 0x14306 / 0x1424c; 7 IS util's 0x14306 and 8 is **weapon**'s 0x141d6; 4 (0x14e1c) and 9 (`actor_script_op_thrust_to_centre` 0x14e5c) both reach util's 0x143f8; 10, 12, 13 and 14 are **NULL longwords**. **11 (0x14e8c) and 15 (0x14ebe) are NOT blocked** — 15 is `andi #$fe,ccr / rts`, six bytes with no callee at all, and 11's only callee is `rand16`, verified in the rng section. Neither has an `fn` line in `../names.txt`, which is why they are not ported here rather than because anything stands in the way; 4 is unnamed for the same reason |
| `0x147f2`, `0x1487c` | `enemies_animate_all`, `enemies_move_all` | their dispatch tables reach handlers in `util` and `weapon`, and the default arm at 0x148c8 is a bare `rts` that `../names.txt` does not name |
| `0x1494a` | `enemy_move_type14_sine` | `util`'s `sin_scaled` @ 0x15654 |
| `0x14de2`, `0x14da2`, `0x14e38` | the three heading script ops | `util`'s 0x142d4 / 0x14306 / 0x1424c |
| `0x14e5c` | `actor_script_op_thrust_to_centre` | `util`'s `entity_apply_accel` @ 0x143f8, which it falls into |
| `0x14a7c`, `0x13868`, `0x13898`, `0x13958`, `0x13a12`, `0x13af2` | the spawners | `spawn_formation` and the formation tables at 0x19504 / 0x19b85, which the wave and ground scripts all tail-call |
| `0x159be`, `0x1544e`, `0x15510` | the draw and explosion group | `sprite`'s draw entry at 0x15ace |

## Verified — mothership (2)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x14f18` | `mothership_place_tail` | 76 | ✅ verified | eight anchor x values including two that make the WORD step wrap across the five segments, and six anchor y values; a sixth seeded record past the five, which pins the loop count against the shift-mask table that follows; poison, so every one of the five fields written per segment is attributed |
| `0x15128` | `mothership_sprite_build_step` | 146 | ✅ verified | every stage the machine can be entered in (1..3) plus 4 and 5, whose arithmetic stays in the image; the banks and the raw frames seeded across their whole extent, which pins the copy's TWO DIFFERENT STRIDES (0xa0 in, 0x500 out) against each other; the finish arm's three stores with a canary under each, and the two earlier stages proving they are left alone. NO POISON, and that is a finding rather than a gap — see below |

### Why `mothership_sprite_build_step` has NO attribution pass

`A_mothership_prep_stage` is this routine's input AND its output, and the attribution pass re-runs
both sides over an image whose oracle-written bytes are INVERTED (`harness.py`, `o_final ^ 0xff`) —
so a stage-1 case, whose oracle leaves 2 in that byte, re-runs at 0xfd, and
`sub.b #$2 / ext.w / mulu.w` then addresses about 0x5030000: outside the image, the same place a
stage of 0 lands. **`make guarded` found that as a worker crash** while `make test` alone was green
on all three cases — which is exactly the class the guarded run exists to find. The lesson
generalises past this routine: `poison=True` is unsafe wherever an output byte steers the routine's
own addressing. Attribution here is carried by seeding instead — noise across both banks and both
raw frames, and a canary under each of the three finish flags — so a candidate that skips any store
still differs.

The mutation ledger for these two rows is in the enemy section above — one sweep, one baseline, one
set of numbers, because both subsystems are rebuilt into the same `.so` and a split count would be
two ways of saying the same run.

### Not reconstructed here, and why

| Addr | Name | Blocked on |
|---|---|---|
| `0x14fc8`, `0x151ba` | `mothership_move_and_place`, `mothership_segments_update` | `actor_script_run` @ 0x14c66, itself blocked above |
| `0x14eda`, `0x14f64`, `0x1504a` | `mothership_begin`, `mothership_spawn_head`, `mothership_segments_respawn` | `spawn_formation` @ 0x14a7c, plus 0x157ca / 0x15838 |
| `0x15222` | `mothership_segment_hit` | 0x12df6, the BCD score award |
| `0x158f4` | `mothership_draw` | `sprite`'s draw entry at 0x15ace |

## Verified — rng (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bf8` | `rand16` | 46 | ✅ verified | the state the binary ships with (0x83e4f2b3, pinned against the image's own bytes, not against a second draw — 65,536 states share any 16-bit output), the LFSR's 0 fixed point, both all-ones/one-bit extremes, the tap mask itself, an 8-draw chain checked against an independently written Python Galois step (so oracle and candidate could not agree on a wrong step count), 400-case sharded fuzz; D0 compared against the oracle's own D0 on every case; poison on 4 seeds |

## Verified — sound (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x16b32` | `sound_lookup_tune` | 28 | ✅ verified | all 256 sound numbers, sharded four ways, which is what pins `adda.w`'s SIGN EXTENSION: 52 of the words a number can reach have bit 15 set (the first at 45, 0x80c8 → 0xf2b0, below the load base), so dropping `sign_ext16` fails at 45. Also hi-garbage and a set high byte in D1 (only `andi.w #$ff` matters, and D1's high word must come back untouched); poison on 4, including the boot tune 0x0b and the first negative offset. The routine writes NO memory, so its answers reach the diff through a `jsr`+store stub (`test/abi.py`) |

## Verified — sprite (3)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bde` | `ship_sprite_deinterleave` | 26 | ✅ verified | disjoint, in-place (`A0 == A1`, which the seventh call site at 0x10132 does) and seven overlap offsets at row and word granularity — the read/store ORDERING is held by the overlap cases and by nothing else (measured: reversing the two half-row copies passes the in-place case and fails at +2/+10/+200/-1600); poison on the disjoint and the in-place shapes. Every byte of both destination frames is seeded with noise, so a candidate writing too few rows differs |
| `0x153f6` | `sprite_preshift8_2px` | 42 | ✅ verified | all six shipped widths (0x1e/0x50/0x5a/0x6e/0xa0/0xc8 — 0x1e and 0x6e reach it only through the tail `bsr` at 0x153e6 inside `sprite_bank_build_preshift8`) in place, six widths disjoint down to the 2-byte minimum, `frame_bytes` 0 for the `dbf` wrap (65536 rows, in-image because the slot step is then 0), four source/destination overlaps that put the source inside a written slot — which is what holds the read/store ORDER, measured — hi-garbage in D2's high half, 240-case sharded fuzz shared with the 4-px twin; the end pointer compared against the oracle's A1 on every case; poison in place and disjoint. The whole 8-slot bank is seeded, so a candidate writing an extra slot differs |
| `0x15420` | `sprite_preshift4_4px` | 46 | ✅ verified | same battery as the 2-px entry above. Seeding the slots it does NOT write (1, 3, 5, 7) is what makes the case a test at all — left as zeroes, a candidate that wrote all seven would pass |

## Suite-wide checks (not functions, so not counted above)

| file | what it holds |
|---|---|
| `test/test_constants.py` | the CLAUDE.md §5 pin, as a COLLECTOR rather than a registry so concurrent agents never edit it: every constant a battery restates equals the `#define` that owns it, every entry address equals the original's own first ten bytes, every battery declares both, no constant is defined in two files, no address has two `A_*` names, and `test/abi.py`'s scratch map clears the program, the game's hard-coded framebuffers and the staged-file table |
| `test/test_status.py` | this ledger's per-section counts against its rows, and its section names against `src/*.c` |
| `test/test_heap_guard.py` | the run-time half of the `tos_malloc_unused` waiver — ported from Joust, the other project the kit's guard is armed for. Until it landed the waiver was declared but never exercised here, because every case in the suite runs a pure leaf that traps not at all |

## Mutation check

Nineteen mutations, each rebuilt with `rm -f build/*.so` first (make's ~1 s mtime granularity has
re-run an unmutated oracle in this workspace before) — **13 killed, 6 survivors**. Re-measured in
full after the per-subsystem restructure, not carried over: the first attempt reported all nineteen
"killed" because `test_status.py` was red for an unrelated reason, which is the same lie a stale
`.so` tells. A sweep is only evidence from a green baseline.

| mutation | result |
|---|---|
| `RNG_TAP_MASK` bit 0 cleared | killed |
| `RNG_STEP_BITS` 16 -> 15 | killed |
| `SHIP_SPRITE_GAP` 1600 -> 1608 | killed |
| `PRESHIFT_4PX_PHASE` 4 -> 2 | killed |
| `PRESHIFT_2PX_SPAN` 1 -> 2 | killed |
| `SPRITE_PRESHIFT_SLOTS` 8 -> 7 | killed |
| `ENTITY_KEEP_X_MIN` 0x30 -> 0x2f | killed |
| `x > ENTITY_KEEP_X_MIN` -> `>=` | killed |
| entity alive byte cleared as a WORD | killed |
| tune table read big-endian | killed |
| `sign_ext16` dropped from `sound_lookup_tune` | killed |
| `loop_passes` dropped from the preshift row count | killed |
| preshift source read taken out of step order | killed |
| entity coordinates read UNSIGNED | **SURVIVED** |
| entity guard TESTED as a byte not a word | **SURVIVED** |
| entity early return deleted | **SURVIVED** |
| `word_sub` drops the high half (kit `machine.h`) | **SURVIVED** |
| `sign_ext16` dropped from the preshift slot step | **SURVIVED** |
| `rotate_right16`'s mask + zero guard deleted (kit `machine.h`) | **SURVIVED** |

Two of these were survivors in the previous revision and are now killed, which is the point of
re-running rather than re-quoting. The preshift read-order mutant died because the battery gained
four overlap cases (below); the `sign_ext16` one died because a glue change had quietly made
`sound_lookup_tune` unreachable from any test — the sweep is what found that, not review.

The six survivors fall into three groups, and all six are **honestly unpinned** rather than
oversights. None can be reached by seeding real data, so per CLAUDE.md they are recorded here rather
than papered over with a fabricated case.

**(a) three arms of `entity_kill_if_offscreen` that are unobservable BY CONSTRUCTION.** The routine
has exactly one store, `clr.b 14(a2)`, and that is what limits what any memory differential can see.

* *The guard's width.* `tst.w 14(a2)` spans `ENTITY_ALIVE` and the blitter's `ENTITY_PIXEL_HIT`
  next to it, but the clear writes the first byte alone. `tst.b` and `tst.w` differ only when the
  alive byte is already 0, and on exactly those records the surviving path clears a byte that is
  already `0x00`.
* *The early return.* Same argument one step further: falling through it reaches the same no-op
  clear.
* *The coordinates' signedness.* The keep band (x 0x31..0x17f, y 0x11..0xaf) lies entirely in the
  positive half of the word, so signed and unsigned readings agree on every input — a value under
  0x8000 is its own unsigned reading, and one at or above 0x8000 reads as negative (under the
  minimum) or as huge (over the maximum), and both answers are "kill". `test_extreme_coordinates`
  used to claim it held this; it does not, and now says so.

The `clr.b`-versus-`clr.w` half of the width question IS pinned — that mutation is killed above.

**(b) two arms whose input walks off the image** — `word_sub`'s high half and `sign_ext16`'s
negative slot step. `word_sub` models `sub.w` on a longword register, which differs from a plain
multiply only once the low word borrows: for the step-back that needs `frame_bytes >= 0x2000`, and
at that width the loop runs 0x1000 rows while the cursor drifts 0xfffe bytes *backwards* per row, so
the run leaves the 1 MiB image within sixteen rows. `sign_ext16`'s slot step turns negative only at
`frame_bytes >= 0x8000` (0x4000 for the 4-px entry, whose step is `frame_bytes << 1`), which escapes
even faster. The oracle bounds such an access and drops it; a reconstruction indexing `image + addr`
does not — which is exactly the class `make guarded` exists to find, and why `test_sprite.py`'s
`FUZZ_MAX_FRAME_BYTES` cap is load-bearing rather than tidiness. Every width the game ships is
0x1e..0xc8. Both stay as written because they are what the instructions do.

**(c) `rotate_right16`'s totality** — its count mask and zero guard are reached by no input: both
call sites pass a literal (2 or 4). They are there so the helper is total, in the same spirit as the
kit's own `rotate_right32` beside it, and cost nothing.

**Why the two batteries' synthetic overlaps ARE justified**, while a fabricated entity record would
not be: both sprite routines take a bare pointer pair and the game itself aliases them — all seven
`ship_sprite_deinterleave` call sites and all sixteen preshift ones pass `A0 == A1` — so behaviour
under aliasing is something the game already relies on, and the cases explore that same dimension at
neighbouring offsets. The inputs are pointers, not invented game data. What the game's own aliasing
cannot do is observe the read/store ORDER (every preshift store lands in slots 1..7 while every read
comes from slot 0), which is why the order needed cases of its own and went unheld until it got
them.

## Not reconstructed, and why

| Addr | Name | Status |
|---|---|---|
| `0x16ac8` | `sound_start` | **NOT blocked — verifiable today, and the next sound row.** An earlier revision of this file claimed it "needs the direct-PSG surfaces"; that was wrong and is retracted. Its body (0x16ac8..0x16b30) reads: `movem.l`, `bsr` to the already-verified `sound_lookup_tune`, `cmpi.b #$fa,(a1)` with an optional channel byte, an `eori.b #1` toggle on the byte at 0x16e90, a three-way select between the voice-slot structures at 0x16eaa / 0x16edc / 0x16f0e, seven stores into the chosen one, `movem.l`, `rts`. No trap, no hardware address, and every store lands in the text segment where the image diff sees it. The YM2149 writes belong to the routines BELOW it — `lea $ffff8800.l,a1` appears at 0x16b82 and 0x16b9e, inside 0x16b4e and its neighbour, which are separate functions |
| `0x153c0` | `sprite_bank_build_preshift8` | Not blocked either: it composes 0x13858 (unported) with the already-verified `sprite_preshift8_2px`, and is the natural next sprite row |
| `0x144e8` | `load_file` | Trap-bound (GEMDOS `Fopen`/`Fread`/`Fclose`), and the model serves all three from staged files — so reconstructible, just deferred past the pure leaves per the playbook's order of attack |
| `0x13c26` | `vbl_menu` | Partly off-image and NOT a plain call. It uploads eight longs from `palette_current` (0x19f46) to `$ff8240..$ff825c`, which the diff cannot see; it also ticks `raster_phase_counter` (0x198a8) mod 2 and clears `vbl_wait_flag` (0x198a7), which it can. Two further obstacles the earlier row omitted: it ends in `bsr.w $16b94` — an unported callee that writes in-image state, so the row cannot be verified before that one is — and it returns with **`rte`**, not `rts`, because it is the VBL vector installed at `$70`. Entering it needs an interrupt frame on the stack rather than the harness's ordinary return address |
| `0x14444` | `ikbd_send_cmd` | **Blocked at the KIT level, and the earlier row prescribed the wrong fix.** The routine spins on bit 1 of the IKBD ACIA status at `$fffc00` and then writes `$fffc02`. Adding `$fffc00` to `os.h`'s `OS_HW_*` set as a VOLATILE address does NOT work: VOLATILE means one declaration describes exactly one read and a SECOND read in the same run is refused — but a spin loop's whole nature is re-reading. Nor does a STATIC declaration, whose contract is that the machine's answer never changes; a status byte that must read "not ready" and then "ready" is precisely what the Phase 7 model excludes. And the write half has no ledger at all: `hw.h` exports `hw_read8` and no `hw_write8`, so a reconstruction's `$fffc02` store would be invisible on both sides. The correct fix is a shim-level ACIA model (a status byte that becomes ready after a declared number of polls, the way `sched.c` counts polls per wait site) plus an IKBD write ledger mirroring `psg.c` — playbook §5's "model the input hardware registers so busy-waits terminate". That is kit work, not this project's, and the surface that would catch it is on-target rather than the differential |
| `0x14456` | `ikbd_acia_isr` | Same `$fffc00`/`$fffc02` gap as above, and it is an interrupt handler entered around a frame rather than a called routine |

## Suite

`make test` — **549 passed**. `make guarded` — same count, 4256
candidate runs guarded across 10 workers, no fault.
