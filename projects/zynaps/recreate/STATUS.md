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
| why a shifter write cannot be seen, and what the sink recovers instead | `include/video.h`, header comment |
| what the masked sprite format is (mask word, four planes, 16-pixel cells) | `include/sprite.h`, "THE MASKED SPRITE FORMAT" |
| how the scroller's pieces fit together | `include/scroll.h`, header comment |
| how the differential method works | [`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) |
| why the sprite fuzz caps the height from BELOW | `test/test_sprite.py`, `BLIT_FUZZ_MIN_HEIGHT` |
| why the map battery passes no `max_insns` | `test/test_scroll.py`, above the ctypes block |

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

## Verified — sound (13)

**The whole driver, end to end.** `test_music_frames` arms the in-game tune and runs the VBL tick
for up to 32 frames as ONE oracle run: tune 0x0b spawns 0x0c and 0x0d on voices 2 and 3, so all
three voices, both modulation machines, the noise sweep and the mixer are live at once over the
game's own data — and the whole multi-frame chip-register stream lands in a single PSG ledger, where
the order ACROSS frames is compared and not only within one.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x16ac8` | `sound_start` | 106 | ✅ verified | all 256 sound numbers (past the 45 real tunes the stream pointer lands in the tune data, and for 52 of them below the tables entirely — armed either way); every channel code 0..5 and 0xff against a shipped tune with NO `0xfa` header, which is the arm where D0 alone decides; the alternate code 4 over a shipped `fa 04` tune with the toggle byte poked to each of 0/1/2/3/0xff — the SHIPPED value is 2, so the round robin runs voice 3, voice 2, ... and not the 1/3 names.txt's comment on 0x16e90 assumed; hi-garbage in both arguments; poison on three tunes, which is what holds all three stream pointers separately. `movem.l` saves and restores every register, so memory is the whole of its effect |
| `0x16b32` | `sound_lookup_tune` | 28 | ✅ verified | all 256 sound numbers, sharded four ways, which is what pins `adda.w`'s SIGN EXTENSION: 52 of the words a number can reach have bit 15 set (the first at 45, 0x80c8 → 0xf2b0, below the load base), so dropping `sign_ext16` fails at 45. Also hi-garbage and a set high byte in D1 (only `andi.w #$ff` matters, and D1's high word must come back untouched); poison on 4, including the boot tune 0x0b and the first negative offset. The routine writes NO memory, so its answers reach the diff through a `jsr`+store stub (`test/abi.py`) |
| `0x16b4e` | `sound_reset_psg` | 70 | ✅ verified | the three enable bytes, three volumes and the mixer are diffed in the image; the FLUSH is diffed by the kit's ordered PSG access ledger, which is the only surface that can see it — a candidate pushing ten registers instead of fourteen, or pushing them ASCENDING, fails there while leaving an identical shadow behind (both mutations measured killed). The case also asserts the oracle logged exactly 14 accesses, so the ledger comparison cannot be silently comparing nothing |
| `0x16b94` | `sound_tick` | 66 | ✅ verified | driven at 1/2/3/8/32 frames of the real in-game tune, chained through one stub so the driver's state carries frame to frame; each run asserts the ledger holds exactly `frames * 11` accesses, which pins BOTH the register count (10..0 — pushing 11..13 would retrigger the envelope) and the descending order. Flush-before-tick is held by the same ledger: the frame-1 stream is the SHIPPED shadow, not the one the tick computes |
| `0x16bd6` | `sound_voice_tick` | 26 | ✅ verified | disabled/enabled, countdown 1 (fetches) and 2 (does not), and countdown 0 — which `subq.b`+`bne` WRAPS to 0xff rather than fetching on. The second enable test is held by its own case: a stream whose first row is command 0xe1 stops the voice inside the fetch, and the modulation that follows must not run (mutation measured killed) |
| `0x16bf0` | `sound_voice_next_row` | 438 (span, including its command handlers) | ✅ verified | one synthetic stream per opcode the dispatcher forks on — note, rest, the note range's top, the first command opcode, and every one of 0xe1/0xe4/0xe5/0xe6/0xe8/0xe9/0xea/0xec/0xf0/0xfc/0xfd/0xfe plus two unknown-command values; the jump/loop/exhausted-loop trio over their three pointers; the pending-noise flag at 0/1/2/0xff (the original decrements and branches on zero, so ONLY 1 is a noise note); the transpose over both bytes' signs and a rest, which skips it. Then eight SHIPPED tunes run from their own first row, so every command the game itself uses is driven on its own operands. Synthetic streams are justified only for the two arms the shipped data cannot reach (the unknown-command skip and 0xfc), and they are still opcode bytes the interpreter is built to read |
| `0x16c82` | `sound_cmd_swap_tunes` | 46 | ✅ verified | THROUGH THE INTERPRETER, not as its own entry: the routine ends in `bra` back into `sound_voice_next_row`'s loop and has no `rts` of its own, so it is driven by an `0xec` row. Both swapped words are diffed, and the `subq.l #1,a0` — the command takes NO operand, so the byte after the opcode is read as the next opcode — is held by the note that follows it in the stream (mutation measured killed) |
| `0x16cec` | `sound_lookup_modtable` | 28 | ✅ verified | the same 256-number sweep as its tune twin, as a SEPARATE battery rather than a parametrized one because the two answer in different registers: this one's answer is A0, which is the store-through-A0 stub's own cursor, so it needs the `movem.l` stub instead — and the stub's order is what proves which register carries the answer |
| `0x16da6` | `sound_voice_modulate` | 94 | ✅ verified | the pitch-sweep arm over five periods including 0, which is the early return (nothing sounding, nothing to sweep) and the only input that reaches it; the arpeggio arm over three phase bytes and three offsets — only the frame the phase flips to ZERO adds the offset, so one of the two notes is the row's own. NO POISON PASS: measured, its outputs include both machines' counters and the phase byte, all of which it branches on |
| `0x16e04` | `sound_set_note_period` | 36 | ✅ verified | all 256 note numbers (the table holds 100, so 100..255 read the modulation index behind it — the byte mask is the routine's only bound), into each of the three voices' shadow pairs. The DOUBLING and the low-byte-first store are both pinned (dropping the `lsl.w #1` is measured killed) |
| `0x16e28` | `sound_noise_modulate` | 32 | ✅ verified | register 6 swept across the four-bit mask's edge (0/1/8/0xf/0x7f/0xff) over a real modulation record, which is what separates masking-before-adding from masking-after and holds the 0x80 bias |
| `0x16e48` | `sound_modtable_step_a4` | 2 | ✅ verified | the two-byte entry that sets the counters to the record's own base; driven by every case in the family below, and separated from the 0x16e4a entry by `test_modtable_step_separate_counter_pointer`, which runs the same record with the counters equal and unequal |
| `0x16e4a` | `sound_modtable_step` | 56 | ✅ verified | six SHIPPED modulation tables (the operands of the game's own 0xe8/0xe9/0xea rows), each walked over every first-counter value from 0 to past its own hold byte — which is what drives all three exits (neutral, delta-only, delta-plus-cursor-step); five second-counter values; and the 0xff terminator followed to a restart pointer aimed at a DIFFERENT table, so a candidate restarting in place differs. NO POISON PASS: measured, the counters are both its outputs and its control flow |

## Verified — sprite (6)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bde` | `ship_sprite_deinterleave` | 26 | ✅ verified | disjoint, in-place (`A0 == A1`, which the seventh call site at 0x10132 does) and seven overlap offsets at row and word granularity — the read/store ORDERING is held by the overlap cases and by nothing else (measured: reversing the two half-row copies passes the in-place case and fails at +2/+10/+200/-1600); poison on the disjoint and the in-place shapes. Every byte of both destination frames is seeded with noise, so a candidate writing too few rows differs |
| `0x153f6` | `sprite_preshift8_2px` | 42 | ✅ verified | all six shipped widths (0x1e/0x50/0x5a/0x6e/0xa0/0xc8 — 0x1e and 0x6e reach it only through the tail `bsr` at 0x153e6 inside `sprite_bank_build_preshift8`) in place, six widths disjoint down to the 2-byte minimum, `frame_bytes` 0 for the `dbf` wrap (65536 rows, in-image because the slot step is then 0), four source/destination overlaps that put the source inside a written slot — which is what holds the read/store ORDER, measured — hi-garbage in D2's high half, 240-case sharded fuzz shared with the 4-px twin; the end pointer compared against the oracle's A1 on every case; poison in place and disjoint. The whole 8-slot bank is seeded, so a candidate writing an extra slot differs |
| `0x15420` | `sprite_preshift4_4px` | 46 | ✅ verified | same battery as the 2-px entry above. Seeding the slots it does NOT write (1, 3, 5, 7) is what makes the case a test at all — left as zeroes, a candidate that wrote all seven would pass |
| `0x15758` | `asteroid_preshift_bank` | 114 | ✅ verified | all SIX shipped banks (0x1a8ae..0x23eae), each holding the bank the builder at 0x156ac would really have left there — rebuilt in the test from BIGAST.DAT's own bytes, two cells per row and a transparent third. Real data is what makes the MASK column's carry-in visible for what it is rather than as an arbitrary bit. Plus noise over a whole bank (there is no data-dependent branch, so noise separates the five word columns and the three cells better than a sprite does), a bank that is none of the six (so the base comes from A0), and poison. Mutations killed: the mask carry-in dropped, the 2-pixel pass step, the cell count |
| `0x157ca` | `mothership_sprite_expand` | 110 | ✅ verified | its two ADDRESSES come from `include/mothership.h`, which owns the boss's data — this row's geometry constants are spelt `BOSS_SPRITE_*` and not `MOTHERSHIP_*` on purpose, because that header reads the same store at a different granularity (its `MOTHERSHIP_FRAME_BYTES` is 0xa0, one frame of the rotate banks its own routines build; the expander's frame is the five-cell 2000-byte one). Two verified readings of one buffer, so two names. Verified over all five boss sprites the disk ships (MOTHER1..5.DAT), whose 1600-byte length is itself the pin on the geometry — 40 rows of four 10-byte masked cells; noise in their place, which is what separates the four source cells from one another (a real sprite is symmetric enough that a transposed cell could still match); poison, which is what holds the synthesised fifth cell, whose four zero planes are otherwise indistinguishable from nothing written. Mutations killed: the source cell count, the blank cell's mask word |
| `0x15ace` | `draw_sprite_masked` | 174 | ✅ verified | all eight even sub-cell phases at BOTH shipped D2 values (0x3e8 and 0x1e0 — half a mothership frame and half an asteroid frame, which is what makes `mulu.w d2,d0` land on the right slot); six x positions across the row; both x rejections and both y rejections one step either side of their edges, odd values included because `and.w #$fffe` runs before the tests; the top clip at one row visible, half and all but one; the bottom clip at four depths including the tallest sprite that needs none; the two clip arms' shared boundary; 200-case sharded fuzz over the whole coordinate box; poison. Twelve mutations, ALL KILLED (below) |

## Verified — scroll (24)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x15920` | `map_rle_decompress` | 92 | ✅ verified | **all twelve levels the disk ships** (LEV1..9, X, Y, Z.MAP), unpacked from their own bytes at `tile_set_base` — twelve independent token streams, so the alternation of run and literal tokens, the run lengths and the literal spans are the level designers' and not a test author's guess at what a stream looks like. The whole 14400-byte column-major map is diffed against a noise-seeded destination, with a guard band either side (the map buffer is bss, so an overrun would otherwise write over zeroes and differ nowhere). Poison on level 1. Mutations killed: the 36-byte column stride, the run flag's bit, the row count |
| `0x15d3e` | `blit_page0_to_playfield` | 24 | ✅ verified | one playfield from the fixed backdrop page onto whichever buffer `screen_back` names — both framebuffers and a third that is neither, which is what says it reads the pointer rather than an immediate; noise and guard bands both ends; poison. Mutation killed: source and destination reversed |
| `0x15d56` | `scroll_page_to_screen_p00` | 66 | ✅ verified | window [8, 160), no wrap; entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15d98` | `scroll_page_to_screen_p01` | 70 | ✅ verified | window [16, 160) then [0, 8); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15dde` | `scroll_page_to_screen_p02` | 70 | ✅ verified | window [24, 160) then [0, 16); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15e24` | `scroll_page_to_screen_p03` | 70 | ✅ verified | window [32, 160) then [0, 24); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15e6a` | `scroll_page_to_screen_p04` | 70 | ✅ verified | window [40, 160) then [0, 32); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15eb0` | `scroll_page_to_screen_p05` | 70 | ✅ verified | window [48, 160) then [0, 40); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15ef6` | `scroll_page_to_screen_p06` | 70 | ✅ verified | window [56, 160) then [0, 48); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15f3c` | `scroll_page_to_screen_p07` | 70 | ✅ verified | window [64, 160) then [0, 56); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15f82` | `scroll_page_to_screen_p08` | 70 | ✅ verified | window [72, 160) then [0, 64); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x15fc8` | `scroll_page_to_screen_p09` | 70 | ✅ verified | window [80, 160) then [0, 72); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x1600e` | `scroll_page_to_screen_p10` | 70 | ✅ verified | window [88, 160) then [0, 80); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x16054` | `scroll_page_to_screen_p11` | 70 | ✅ verified | window [96, 160) then [0, 88); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x1609a` | `scroll_page_to_screen_p12` | 70 | ✅ verified | window [104, 160) then [0, 96); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x160e0` | `scroll_page_to_screen_p13` | 70 | ✅ verified | window [112, 160) then [0, 104); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x16126` | `scroll_page_to_screen_p14` | 70 | ✅ verified | window [120, 160) then [0, 112); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x1616c` | `scroll_page_to_screen_p15` | 70 | ✅ verified | window [128, 160) then [0, 120); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x161b2` | `scroll_page_to_screen_p16` | 70 | ✅ verified | window [136, 160) then [0, 128); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x161f8` | `scroll_page_to_screen_p17` | 70 | ✅ verified | window [144, 160) then [0, 136); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x1623e` | `scroll_page_to_screen_p18` | 70 | ✅ verified | window [152, 160) then [0, 144); entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x16284` | `scroll_page_to_screen_p19` | 62 | ✅ verified | window [0, 152), no wrap; entered at its own address, both buffers seeded over a whole playfield, plus its share of the 120-case fuzz — see the shared note below |
| `0x169f2` | `scroll_emit_column_shift2` | 100 | ✅ verified | the workspace, the page column and the screen edge all seeded over a whole playfield — not over the 8 bytes a row receives — so a candidate writing a fifth plane or stepping by the wrong row stride differs. Both values of `scroll_prefill_hide_screen` (and a third, 0xff, since the guard is `tst.b`): set, the edge destination is redirected onto the page, so those cases are what say the redirect happens and the others are what say the edge is written when it does not. Also run at the game's own `scroll_col_workspace` with the edge at `screen_back + 152`. Poison. Mutations killed: the 2-pixel shift amount, the redirect inverted, the emitted half taken from the low word instead of the high |
| `0x16a56` | `scroll_emit_column_shift0` | 80 | ✅ verified | the same battery. Its entry is pinned to TWENTY-TWO bytes rather than ten: the two emitters are the same routine but for one step and their first twenty bytes are byte-identical, so a shorter pin would let either address stand for the other |

**The shared note the twenty blit rows cite.** They are one body twenty times over, differing only
in where their ring window starts and in how the hand-unrolled `movem.l` runs are cut to land the
wrap on a movem boundary. What that costs the reconstruction is one residual, and it is a residual
of the CHUNKING and not of the copy: a movem pair reads a whole chunk before storing any of it, so
the chunk boundaries would be observable if the page and the screen overlapped. They cannot — a page
is one of the eight 0x5a00 buffers at `map_page_table` (0x1798a) and the screen is a framebuffer at
0x70300/0x78000 — so `src/scroll.c` copies the window in order and the twenty chunk lists are
**unmodelled by construction**, not untested. (Contrast `blit_graphic_block` in the video section,
whose two strips CAN overlap and where the same question was a real defect.)

## Verified — video (6)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x1296e` | `screen_clear` | 12 | ✅ verified | a whole 32000-byte frame at both of the game's hard-coded framebuffers and at a buffer that is neither (the destination is A0 and the routine cares about nothing else); noise with a 16-byte guard band either side, which is what makes an overrun visible at all — the buffers are bss and a candidate clearing too far would write zeroes over zeroes; poison. Mutation killed: the cleared span 4 bytes short |
| `0x1297a` | `screen_flip_buffers` | 48 | ✅ verified | the pointer swap is diffed byte for byte over four buffer pairs, two of them arbitrary longwords (the routine never dereferences either pointer, so any word is a legal input and that is what pins the byte extraction over the whole range). The $ff8203/$ff8201 publish is OFF-IMAGE and is held instead against the ORACLE'S OWN registers — A0 keeps the buffer that was published and D0 keeps it shifted down 16 — so both bytes have an oracle-side witness. **RESIDUAL: that the bytes reach the shifter at all is unpinned**, and no image differential can pin it; the surface that would is an on-target one (`docs/on-target-execution.md` — a hardware-state vector or the rendered pixels). Mutation killed: the two base bytes swapped |
| `0x12fc2` | `clear_backdrop_page0` | 18 | ✅ verified | one playfield's worth at the fixed page, noise + guard bands, poison. The address is an immediate in the routine, so the only thing a case can vary is what was there before. Mutation killed: the page address moved 4 bytes |
| `0x134b8` | `blit_graphic_block` | 18 | ✅ verified | both shipped heights (D0 = 0x3f and 0x17), the one-row minimum — the count is a `dbf` register, so 0 must copy ONE row — hi-garbage above the word, six source/destination overlaps at row and word granularity, and poison. **The overlaps are what caught a real defect**: a `movem` pair reads a whole row before storing any of it, and an interleaved reconstruction read back its own stores from the third longword on at dst = src + 2. Mutation killed: the 32-byte row width |
| `0x1597c` | `playfield_clear` | 66 | ✅ verified | the top 144 rows of whichever buffer `screen_back` names — both framebuffers and a third — noise + guard bands, poison. Mutation killed: the start moved one longword |
| `0x153ae` | `set_palette_title` | 18 | ✅ verified | the routine writes NO image byte — its whole effect is sixteen colour registers at $ff8240 — so the oracle enters at a stub that stores the eight longwords it loaded (d0-d7) where the diff can see them, as `sound_lookup_tune` does for a register-only answer, and the candidate's glue publishes what its SINK recorded at the same address. Driven on the palette the binary ships with and on three noise rows, so each of the eight longwords must come from its own slot; poison, which is what stands between an unwritten sink and a green. **RESIDUAL: as with the flip above, that the row reaches $ff8240 is unpinned** and needs an on-target surface. Mutation killed: the upload one longword short |

### Mutation check — video, scroll, sprite (this batch)

Thirty-eight mutations across the three subsystems above, each rebuilt after `rm -f build/*.so`
first (make's ~1 s mtime granularity has re-run an unmutated oracle in this workspace before) and
every one run from a green baseline — **37 killed, 1 survivor**. The per-function rows above name
the killed ones; the survivor is here.

**A SECOND WAY A SWEEP LIES, met and defended against in this batch.** The stale-`.so` trap is
already recorded above; this one is its sibling. `make test` exiting non-zero is only evidence when
pytest actually RAN — and `.venv` here is a symlink into a shared tree, which a concurrent
`make venv` broke for about a minute. Every mutant run in that window reported "killed" because
`import pytest` failed, and the first sweep duly came back 38/38. The runner now refuses to score a
run that produced no pytest summary line, and re-checks the baseline before and after the sweep;
re-run under that guard, the true result is the 37/38 above. A sweep that kills EVERYTHING is the
tell — one of these mutations is a known redundancy and had to survive.

| mutation | result |
|---|---|
| `scroll_page_to_screen`'s ring wrap (`% SCREEN_ROW_BYTES`) deleted | **SURVIVED** |

**And it is a redundancy, not a coverage hole.** The modulo only ever fires for phase 19, whose
window start is `8 * 20` = 160; without it, `start` stays 160, the head span becomes
`SCREEN_ROW_BYTES - start` = 0, and the wrapped span then copies all 152 bytes from the row's base —
which is exactly what the modulo produces by making `start` 0. The two spellings agree on every
phase because the wrap is expressed twice over. It stays as written because `% SCREEN_ROW_BYTES` is
what says the page row is a RING; the other reading works by an accident of the head/tail
arithmetic.

**`draw_sprite_masked` carries one unpinned arm of the off-image class**, the same shape as the two
`src/sprite.c` already records. Its row count is `ENTITY_HEIGHT` read as a WORD and NOT masked — the
sibling blitter at 0x15b7c masks the same field with `and.w #$7fff` — so a height of 0, or any
height with bit 15 set, reaches the `dbf` as 0 or as a negative word and the loop runs ~65536 rows
at 160 bytes each. That leaves the image within a hundred rows: the oracle drops the accesses and a
reconstruction indexing `image + addr` does not, which is the class `make guarded` exists to find and
why `test_sprite.py`'s `BLIT_FUZZ_MIN_HEIGHT` is load-bearing rather than tidiness. Both arms are
faithful and neither is reachable from a record any spawner writes — the shipped sprites are 32 and
40 rows — so they stay as written and are recorded here rather than repaired.

Two notes on what the batch's cases lean on:

* **`draw_sprite_masked`'s entity records are CONSTRUCTED, and have to be.** `entity_table` and
  `entity_boss_parts` are bss, so the binary carries no record to seed from — the game writes them
  at run time. What the cases do not do is invent a shape the spawner cannot produce: every field is
  one it sets, D2 is one of the two values the two call sites load, and the coordinates walk the
  same playfield box the routine clips against.
* **One height in that battery is bigger than any the game has.** The two clip arms are exclusive
  arms of one `bge` and they agree at `y == PLAYFIELD_TOP_Y` for every height up to
  `PLAYFIELD_ROWS`; only a taller sprite tells `<` from `<=` there (measured — the mutation survives
  the rest of the battery). `BLIT_OVERSIZE_HEIGHT` is 152 rows and the tallest shipped sprite is the
  mothership's 40, so that case is CONTRACT coverage and not game coverage.

## Verified — weapon (20)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13d3e` | `entity_type_is_lockable` | 48 | ✅ verified | all 256 type bytes, sharded four ways — exhaustive because the bound is a SIGNED byte compare, so every type from 0x80 up takes the in-range arm and resolves through `ext.w` to a word offset of 0x1ff0..0x1ffe, 8 KB past the table; the eleven types the shipped 0x191ac table lists; both sides of the signed edge; poison on an in-class and an out-of-class type. The answer is the Z FLAG and the routine writes no memory, so the case enters at a `seq` stub (`test/abi.py`). ONE RESIDUAL: the bound's inclusiveness — see the survivor ledger |
| `0x13ede` | `powerup_slot1_activate` | 10 | ✅ verified | the one word store, driven over a timer already holding the value it is about to be given (so the poison pass is what makes it a test), over 0 and 0xffff, with a trailing guard word that catches a long store. UNREACHABLE IN THE GAME — `powerup_capsule_collected` @ 0x13d9e diverts cursor 1 to 0x13f0e before the 0x19348 table is consulted — so this is a read-verified routine that the differential nonetheless drives directly |
| `0x13f72` | `powerup_downgrade_on_death` | 44 | ✅ verified | all 256 speed bytes and all 256 power bytes, each sharded four ways, plus a 7x6 corner grid of the two together. The sweep is what pins the SIGNS: the speed floor is `subq.b` + `bpl` on the decremented byte, so 0x00 wraps to 0xff and clamps while 0x80 becomes 0x7f and survives; the power floor is a signed `cmpi.b #$2` + `bge`. The two levels are adjacent bytes, so the grid also rules out one being clamped from the other's value; poison on a clamping and a non-clamping case |
| `0x13f9e` | `fire_seeker` | 124 | ✅ verified | seven gunsight-lock bytes against three D6 bytes, driven INDEPENDENTLY — which is what separates "copies the lock" from "copies D6" on the case where the two agree, and what pins the sound to the locked arm alone (an unlocked launch is silent, so nothing in the voice records moves). Four whole D6 registers whose low bytes agree and whose upper three do not, pinning `move.b d6,26(a2)`; six D0 values against four toggle bytes, which is the pair that actually chooses the voice — D0 cannot, and `test_every_launch_sound_names_its_own_channel` asserts that off the image by reading the 0xfa header out of sfx 0x1a's own stream rather than assuming it. The slot is pre-loaded with a value for every one of the twelve arming stores, so a missing store diverges; the four-byte launch-counter poke carries `free_wave_slot_count` as an interior guard. NO ALIVE GUARD, stated by driving the same alive grid its two neighbours refuse; poison |
| `0x1401a` | `fire_homing_missile` | 120 | ✅ verified | the alive guard over four bytes, and WHICH lock slot the launch claims: a non-zero `A_missile_lock_a` sets ENTITY_HEIGHT's bit 15 over a row count the same routine stored two instructions earlier, so the height is checked as a whole word rather than as a flag. Shares `arm_steered_shot` with `fire_seeker` above and the four shadow-position pairs below; poison |
| `0x14092` | `entity_pos_from_ship` | 20 | ✅ verified | five x/y pairs across the word including both extremes, with the destination record seeded with noise, so a copy of the wrong field — or of a long where the original copies two words — diverges; poison |
| `0x140a6` | `seeker_update` | 80 | ✅ verified | the retarget's two conditions driven INDEPENDENTLY — slot 19 alive across three bytes against three type bytes — so "the drone is out" and "slot 19 holds a drone" cannot stand in for each other; five target indices including the drone's own slot and one past the table, whose zeroed record always reads dead and so always retargets; six TTL bytes, which pin the retire as an EQUALITY on zero (0 wraps to 0xff and flies on, and the retire runs through the already-verified `shot_retire_kind36`); the whole routine driven at each of the six shot slots, since it takes its record as a pointer and a case at one slot says nothing about the others. Poison on the retarget and on the retire |
| `0x140f6` | `entity_type_is_missile_target` | 48 | ✅ verified | the same battery as `entity_type_is_lockable` above, against the 0x1918e table. Its record register is A1 and it clobbers A0, which is why the stub reloads A0 after the call rather than taking it through the run's registers. Same one residual |
| `0x14126` | `homing_missile_update` | 176 | ✅ verified | the acquire scan, which is the routine. Nine starting target indices — 0, the enemy band's two ends, MISSILE_NO_TARGET, and four ABOVE the band, which walk the byte counter up through 0xff and round to MISSILE_SCAN_END rather than spinning (the case that says the loop terminates at all); the alive x listed-type grid on the target it already had, so a target is kept only while BOTH hold; four indices held by the other missile, which pin the claim test as a comparison of the two lock BYTES and pin the lock store as happening BEFORE it — a refused candidate still leaves its index in the slot on the way past; three shapes of "nothing lockable" (no enemies, all inert, all dead), each ending with MISSILE_NO_TARGET in the record AND in the lock; the lock-slot flag driven both ways with both lock bytes poked to distinct markers, so writing or freeing the wrong slot is a diff. Five TTL bytes against both lock slots, the retire running through the already-verified `shot_retire_kind32`. `test_the_missile_target_types_this_battery_uses` asserts the two type bytes the scan turns on against the shipped 0x1918e table every run. Poison on the acquire and on the retire |
| `0x141d6` | `entity_steer_toward_target` | 120 | ✅ verified | all 256 heading bytes sharded four ways against a fixed target — the game holds only 0..0x3f there, but every step of the turn is a BYTE operation (a signed difference, a `neg.b` magnitude, two `and.b #$3f` wraps) and only the full range separates that from a masked reading. Eight max-turn bytes x four headings, pinning `cmp.b d2,d0` + `bge` as SIGNED: 0x80 and 0xff are NEGATIVE limits that every difference clears, so the shot steps by that byte instead of snapping. Nine target positions, one per compass point, each from four headings — which is what pins WHICH WAY the turn goes, since `(-difference) & 0x3f >= 0x20` is the only thing choosing between +max and -max. Five countdowns including 0 (`subi.b` wraps it to 0xff rather than expiring) and five reload periods including 0; ten target indices from 0 to 0xff, pinning the record stride over the whole byte range; six speed bytes across the `ext.w` sign edge. A target the shot is ALREADY aimed at leaves the velocity pair holding the seeded noise, which is the case that says the original branches past its own re-derivation. Poison on all three arms |
| `0x14324` | `fire_bomb` | 82 | ✅ verified | the alive guard over four bytes against two D0 channels, and the eight fields a launch writes over a slot pre-loaded with something else for each. The four ship-shadow x/y pairs (shared with the other two launchers) are what pin the spawn copy as the routine's LAST act — a `bra` tail call made after the velocity pair is already written; poison |
| `0x14376` | `bomb_update` | 130 | ✅ verified | the terrain test's two halves driven TOGETHER — four pixel-hit bytes x four overlap-row values — so neither can stand in for the other: a pixel hit is the landscape only when the bomb's own row is empty, and any other entity under it explains the hit instead. The bomb resolves that row from its record ADDRESS (`divu.w #$2c` / `lsl.w #2`), so it is driven at every one of the six shot slots with only that slot's row marked and then with its neighbour's, which is what a wrong stride or shift lands on. Ten dy values including 0x8000, where `neg.w` overflows back onto itself and the two readings of the following `asr.w #1` part; a 4x6 latch/bounce-count grid pinning ENTITY_BOUNCE as a ONE-FRAME latch rather than a counter (a bomb on the terrain two frames running is retired) and the count as stepped BEFORE that test, so a retiring bomb still spends one; seven y values across the floor and both sides of the word's sign edge, read AFTER gravity has moved it. Poison on all three arms. `make guarded` covers the computed row address |
| `0x152a4` | `player_shot_update_all` | 70 | ✅ verified | one slot of each kind plus a dead slot and an unknown kind in a single pass; the same kind in all six slots at once (which is what a wrong stride lands beside); both phases of the half-rate gate the puff arm sits behind. All 20 records are seeded and slots 6..19 must come back untouched, so a loop that overran the six shot slots diverges; poison |
| `0x152ea` | `shot_set_sprite_a` | 36 | ✅ verified | all 256 heading bytes, sharded four ways. The game's own headings are 0..0x3f, exactly the variant table's length, but BOTH lookups sign-extend their index — heading 0x80 reads 128 bytes BELOW the variant table, and a variant byte found there is itself signed and reaches 512 bytes below the sprite table — so the full 256 is what pins the two `ext.w`s (dropping either turns it red above 0x7f) and every resolution stays inside the text segment. The shipped variant table's 8-way fan-out is asserted off the image; poison on four headings; `make guarded` covers the computed indexes |
| `0x15370` | `shot_anim_puff` | 62 | ✅ verified | all 256 incoming frame bytes on the live phase, sharded four ways — three arms meet there and only a sweep separates them: the death frame is compared for EQUALITY so 6 and 0xff keep animating, the pointer index is `(frame - 1) & 0xf` so frame 0x11 draws frame 1's picture, and the increment is a byte so 0xff wraps to 0. Plus the half-rate gate over three non-zero phases and five frames, which must touch nothing at all; poison |
| `0x15582` | `shot_retire_kind32` | 50 | ✅ verified | the full alive x type x height grid (4 x 5 x 4), which pins both halves of the guard and WHICH lock slot the sign of field 8 releases — both lock bytes are poked to distinct markers, so releasing the wrong one is a diff rather than a coincidence, and the heights step across bit 15 in both directions. Counts driven at 0x00 so the `subi.b` wrap is seen not to borrow into its neighbour; poison over record, count and lock |
| `0x155b4` | `shot_retire_kind36` | 14 | ✅ verified | the same alive x type grid as its two neighbours, which is how the ABSENCE of a guard is stated rather than assumed: even a dead, wrongly-typed slot is converted and counted down. Count wrap at 0x00; poison |
| `0x155c2` | `shot_retire_kind33` | 32 | ✅ verified | alive x type grid; count wrap at 0x00; poison |
| `0x155e2` | `shot_to_puff` | 34 | ✅ verified | every field the rewrite touches, over a y that borrows across both ends of the word (`subi.w #$3` takes 0 to 0xfffd and 0x8002 to 0x7fff). The rest of the 44-byte record is noise, so writing ENTITY_HEIGHT as a byte or the sprite pointer as a word diverges; poison. THE SPRITE ADDRESS IS THE RELOCATED ONE, 0x6791e. The earlier note here blamed `../out/prg_dis.txt` for printing immediate-longword `<RELOC ptr>` operands unrelocated; THAT IS NO LONGER TRUE of the regenerated listing, which prints `move.l #$6791e,10(a2)` over the bytes `257c 0005791e`. `../names.txt` is right too — its comments on 0x155e2, 0x13f9e, 0x1401a and 0x14324 each carry an explicit `CORRECTION` giving the relocated number — so the listing and the name map now agree, and 0x6421e (`A_shot_sprite_steered`) and 0x6a11e (`A_bomb_sprite`) were read off both |
| `0x15604` | `player_shots_clear` | 64 | ✅ verified | the gunsight's unconditional kill and the six-slot seeker sweep in one poked table (slot 19 IS the gunsight: `A_entity_gunsight` is `A_entity_table + 19 * ENTITY_STRIDE`, asserted by `test_the_record_field_layouts_this_battery_leans_on`), over a 4 x 2 kind/alive grid and a mixed table where only some slots are live seekers, so the count ends up decremented exactly as many times as there were; poison. ONE RESIDUAL: the re-type to 0x32 before the retire is overwritten two instructions later and no whole-image diff can see it — see the survivor ledger |

## Verified — collision (4)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x11cce` | `object_pair_overlap_mark` | 98 | ✅ verified | a 7x7 grid stepping the partner box across all four `blt` bounds one pixel either side of each, which is what pins both spans as EXCLUSIVE at both ends and each comparison's own asymmetric operand pair; seven heights across bit 15, pinning the 0x7fff mask against a plain read; four y values near the word's sign boundary, pinning the bottom edge as a 16-bit `add.w` compared signed; four index pairs from the builder's own loop shape, pinning the mark as RECIPROCAL; five cases that aim BOTH row pointers at one longword, which is the only input that separates the original's read/read/store/store from two read-modify-writes (the reconstruction was the latter until this case was added); 240-case sharded fuzz clustered on the edges. Both mask rows are seeded non-zero so an extra `bset` shows; poison on the overlapping shape |
| `0x12d44` | `collision_chain_walk` | 130 | ✅ verified | the entry's two guards (no pixel hit, and a type the terrain table does not list); an unexplained hit at EVERY index 0..19, because the record address and the two row addresses are computed with different arithmetic (`mulu.w #$2c` against `lsl.w #2`); a row of all-ones at index 0 and 0xfffffff8 at index 3, pinning the lower-index mask; a one-hop chain to a flagged partner whose own type is inert, which is the difference between the 0x12d44 entry and the 0x12d78 loop head; the same chain unflagged; a three-bit row that separates "lowest bit" from "highest"; a four-hop chain 19->12->6->1->0; 200-case sharded fuzz with random flags, types and rows; poison on both answers. The shipped `lower_index_masks` is asserted to be `(1 << i) - 1`, which is what makes the walk terminate. Answers in D7 and in Z; the stub records both. `make guarded` covers the computed record and row addresses |
| `0x12dc6` | `object_type_is_collidable` | 48 | ✅ verified | all 256 type bytes sharded four ways (see `entity_type_is_lockable` for why exhaustive); the ten types the shipped 0x19196 table lists — including 0x32/0x33/0x34/0x36, the player's own shots, which are ABOVE `TYPE_PLAYER_OWNED_BASE` and are exactly what this routine's wider `ble #$37` bound exists for; one step either side of that bound; poison. Bound and probe both pinned — no residual |
| `0x13d6e` | `entity_type_is_lethal` | 48 | ✅ verified | the same battery against the 0x191a4 table, plus its fifteen shipped members. ONE RESIDUAL: the bound's inclusiveness — see the survivor ledger |

## Verified — player (2)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x11318` | `ship_move_up` | 66 | ✅ verified | nine y values across the clamp and both ends of the word, against both speed levels — which pins `cmpi.w #$20` + `ble` as SIGNED and INCLUSIVE (at exactly the minimum the ship is re-set, not stepped) — five mirror-y values that have drifted away from the live record, which is what makes "both records step, only one is compared" observable; a 6x6 countdown/tilt grid pinning the roll as one frame in four with the countdown decremented on every call; five caller-supplied speed entries whose +4 and +6 words DIFFER, which is the only input that says which word each mover reads — both entries the game can select hold the same value at both offsets, so swapping them survives everything else (found by the review, now killed); 320-case sharded fuzz shared with its twin; poison on the stepping arm, the clamping arm and a call that does not roll. The shipped speed table's two entries are asserted as whole words, not low bytes |
| `0x1135a` | `ship_move_down` | 68 | ✅ verified | the mirror battery of the above. The tilt grid is what separates the two arms: `ship_move_up` guards with `tst.b` (stop at 0) while this one guards with `cmpi.b #$6` + `beq`, so a bank already PAST the maximum keeps climbing instead of being held there |

## Verified — input (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x1326e` | `onscreen_keyboard_hit_test` | 116 | ✅ verified | all thirty keys addressed by their own screen position; one step either side of all four row-band edges (the bands SHARE their boundaries — a biased y of exactly 0x70 belongs to the TOP row — and the neighbouring rows hold different scancodes there); both column bounds including 0x110, which after the shift indexes byte 28 of a 28-byte row and so reads the NEXT row's first key; one key's whole 24-pixel span, pinning `lsr.w #3`; five incoming D0 values, because D0 IS AN INPUT — a hit overwrites only its low byte, so the caller's high word comes back, while a miss clears the whole register; 400-case sharded fuzz with junk in D0's high half; poison on a hit and a miss. The three row tables are transcribed off the image (the bottom row's last four keys are TWO columns wide, which a description would have got wrong). The routine writes no memory, so D0 reaches the diff through the `jsr`+store stub. `make guarded` covers the computed column index |

## Mutation check — the weapon / collision / player / input slice

Thirty-seven mutations over these twenty routines, each rebuilt with `rm -f build/*.so` first, from
a green baseline — **35 killed, 2 survivors**.

THE SWEEP AND THE REVIEW EACH FOUND A REAL COVERAGE HOLE, which is the reason for running them
rather than quoting them:

* *The sweep.* Two `collision_chain_walk` mutations (the loop's pixel-hit test deleted, and
  `lowest_set_bit` starting at 1) survived the first pass. The cause was in the battery, not the
  code — `test_collision.py`'s `_chain_pokes` assigned into `rows[start:][:4]`, a slice of a COPY, so
  every chain case ran with an all-zero overlap table and the walk never hopped at all. With the
  poke fixed both die, and the fix is what the "one hop", "lowest bit" and long-chain cases were
  written for in the first place.
* *The review.* Swapping `SHIP_SPEED_DY_UP` and `SHIP_SPEED_DY_DOWN` survived everything, because
  both speed entries the game can select hold the SAME word at +4 and +6 (2/2 and 4/4). A6 is a
  pointer argument, so the fix was a case that supplies its own entry with the two words distinct —
  the same justification `test_sprite.py`'s aliased pointer pairs carry. Now killed.

A third finding was a fidelity slip the differential could not have caught as written:
`object_pair_overlap_mark` was two sequential read-modify-writes, where the original reads BOTH rows
before storing either. The two differ only when the row pointers alias, which the game's builder
never does — so the code was corrected and a case that aims both pointers at one row was added, and
the mutation is killed rather than left unobservable.

| mutation | result |
|---|---|
| `entity_type_in_class`: word mask 0xfffe -> 0xffff | killed |
| `entity_type_in_class`: bit index not inverted | killed |
| `entity_type_in_class`: bound `>` -> `>=` (tightened by one type) | **SURVIVED** |
| `object_type_is_collidable`: bound 0x37 -> 0x36 | killed |
| `entity_type_is_lethal`: reads the terrain table | killed |
| `entity_type_is_missile_target`: reads the lethal table | killed |
| `collision_chain_walk`: loop drops the pixel-hit test | killed |
| `collision_chain_walk`: `lowest_set_bit` starts at 1 | killed |
| `collision_chain_walk`: row stride 4 -> 8 | killed |
| `object_pair_overlap_mark`: box width 0x10 -> 0x11 | killed |
| `object_pair_overlap_mark`: height mask dropped | killed |
| `object_pair_overlap_mark`: marks row i twice | killed |
| `object_pair_overlap_mark`: two read-modify-writes, not read/read/store/store | killed |
| `entity_pos_from_ship`: y copied from the destination | killed |
| `powerup_slot1_activate`: 0x3e8 -> 0x3e7 ticks | killed |
| `powerup_downgrade_on_death`: power floor 2 -> 1 | killed |
| `shot_to_puff`: y lift 3 -> 2 | killed |
| `shot_retire_kind32`: lock flag bit 15 -> bit 14 | killed |
| `shot_retire_kind36`: decrements the bomb count | killed |
| `shot_retire_kind33`: alive guard dropped | killed |
| `shot_set_sprite_a`: heading index read unsigned | killed |
| `shot_anim_puff`: death frame 5 -> 4 | killed |
| `shot_anim_puff`: frame index mask 0xf -> 0x7 | killed |
| `player_shot_update_all`: seekers get no sprite | killed |
| `player_shots_clear`: drone flag left standing | killed |
| `player_shots_clear`: the seeker is not re-typed before it is retired | **SURVIVED** |
| `player_shots_clear` / `player_shot_update_all`: 6 slots -> 5 | killed |
| `ship_move_up`: clamp 0x20 -> 0x21 | killed |
| `ship_move_up`: tilt guard tests the maximum | killed |
| `ship_move_up`: reads the DOWN word of the speed entry | killed |
| `ship_move_down`: tilt held at the maximum | killed |
| `ship_move_down`: clamp 0x9c -> 0x9d | killed |
| ship movers: the mirror record is not stepped | killed |
| `ship_tilt_due`: countdown reloaded every call | killed |
| `onscreen_keyboard_hit_test`: top band 0x70 -> 0x6f | killed |
| `onscreen_keyboard_hit_test`: column shift 3 -> 4 | killed |
| `onscreen_keyboard_hit_test`: a hit clears D0's high word | killed |

**Both survivors are unobservable by construction, not untested**, and neither can be reached by
seeding real data.

**(a) the class bound at its own value.** `entity_type_in_class` refuses a type past `last_type`;
tightening `>` to `>=` changes the answer for exactly one input, `last_type` itself. All three
tables that bound is used with (0x1918e, 0x191a4, 0x191ac) have that type's bit CLEAR, so both
spellings answer "not in the class". No seeded record can separate them, because the answer comes
from the game's own table and not from the case. `test_the_class_bound_is_unobservable_at_its_own_
value` (weapon) and `test_the_lethal_bound_is_unobservable_at_its_own_value` (collision) assert that
table bit against the image every run, so the claim ages with the data rather than in a comment.
`object_type_is_collidable`'s own wider bound IS pinned — that mutation is killed above.

**(b) an intermediate store the whole-image diff cannot see.** `player_shots_clear` sets a seeker's
type to 0x32 and then calls `shot_retire_kind36`, whose `shot_to_puff` overwrites the same byte with
0x37 two instructions later. The differential compares the FINAL image, so no case can distinguish
the store from its absence — deleting the line is green by construction. It stays because it is what
the original does, and because it is load-bearing for a reader: it is the reason the count-only
`shot_retire_kind36` can be reused here without its missing kind check ever mattering. A write-ledger
or an on-target trace would see it; the byte diff cannot.

## Mutation check — the steering / launch / projectile-update batch

Thirty-six mutations over the seven routines above and the two helpers they now share with
`src/collision.c`, each rebuilt with `rm -f build/*.so` first, from a green baseline whose pytest
summary line was re-read every run — **34 killed, 2 survivors, both no-ops by construction**.

TWO SWEEPS AND THE REVIEW EACH FOUND A REAL COVERAGE HOLE, which is why all three are run:

* *The first sweep.* `test_weapon.py`'s `_collision_rows` assigned each mark with
  `rows[start:][:4] = ...`, **a slice of a COPY**, so every `bomb_update` case ran against an
  all-zero overlap table. "collision row stride 4 -> 8" and "the overlap row is not consulted" both
  survived on that alone — the bomb bounced in every case, and neither the row address nor the row's
  contents reached the answer. This is byte-for-byte the defect the previous slice's ledger records
  against `test_collision.py`'s `_chain_pokes`, re-introduced by a fresh author writing a fresh
  helper. Both batteries now build that table through **one** shared `abi.indexed_table`, which
  cannot make the mistake and refuses an out-of-range index (which would silently APPEND, growing
  the poke past the 21-row table) — the fix is the shared helper, not a second local guard.
* *The second sweep.* `BOMB_ACCEL_BITS`'s two X-axis bits were unkillable: `_bomb_slots` seeded
  ENTITY_AX = 0, so `entity_apply_accel` on the X axis stored ENTITY_DX back unchanged and widening
  the mask to bits 3+5 wrote a byte-identical image. Seeding a live AX closes it — legitimate,
  because `bomb_update` takes the record as given even though a *launched* bomb's AX really is 0.
* *The review.* `_steer_slots` wrote the target's fields with `slots[target] = {...}`, so a case
  aiming the shot at its OWN slot **replaced the whole steering block** with three position keys:
  the countdown reverted to `_record` noise, the turn never came due, and every such case was a
  silent duplicate of the countdown-only arm. `test_steer_leaves_the_velocity_alone_when_already_on_
  heading` was therefore vacuous, and the already-on-heading arm was reached only incidentally, by
  the one heading in 256 that happens to match in the exhaustive sweep. `_merge_slot` fixes it, and
  the arm now has cases that reach it on purpose (a self-target and a due-east target, both of which
  `angle_to_target` answers 0 for).

| mutation | result |
|---|---|
| `heading_step`: the two turn directions swapped | killed |
| `heading_step`: turn-limit compare read unsigned | killed |
| `heading_step`: short-way test uses the magnitude, not the re-negated difference | killed |
| `heading_step`: exact arm steps instead of snapping | **SURVIVED** (a no-op — see below) |
| `entity_steer_toward_target`: countdown reloaded on every call, not from SHOT_TURN_PERIOD | killed |
| `entity_steer_toward_target`: velocity re-derived even when already on heading | killed |
| `entity_record`: record stride 0x2c -> 0x2d | killed |
| `entity_from_index`: the byte mask widened to a word | **SURVIVED** (unreachable — see below) |
| `fire_seeker`: keeps D6 even when the gunsight holds a lock | killed |
| `fire_seeker`: the sound plays on the unlocked arm too | killed |
| `fire_seeker`: the target byte is stored as a word | killed |
| `arm_steered_shot`: seeker TTL 0x4b -> 0x4c | killed |
| `arm_steered_shot`: the launch heading is not cleared | killed |
| `fire_homing_missile`: the lock-slot flag is never set | killed |
| `fire_homing_missile`: the alive guard is dropped | killed |
| `fire_bomb`: gravity 0x40 -> 0x41 | killed |
| `fire_bomb`: launch dx written as a byte | killed |
| `seeker_fallback_target`: always retargets at the ship | killed |
| `seeker_fallback_target`: the drone's type is not checked | killed |
| `seeker_update`: TTL retires at `<= 0` rather than `== 0` | killed |
| `missile_acquire_target`: the lock is written only after the claim test | killed |
| `missile_acquire_target`: the scan restarts at MISSILE_SCAN_FIRST every time | killed |
| `missile_acquire_target`: giving up leaves the lock byte standing | killed |
| `homing_missile_update`: the lock slot is always A | killed |
| `missile_target_is_valid`: a dead target is kept | killed |
| `bounce_velocity`: the shift is logical, not arithmetic | killed |
| `collision_table_row`: row stride 4 -> 8 | killed (SURVIVED the first pass — see above) |
| `bomb_collision_row`: the record index is off by one | killed |
| `bomb_hit_terrain`: the overlap row is not consulted | killed (SURVIVED the first pass) |
| `bomb_update`: the accel mask also drives the X axis | killed (SURVIVED the second pass) |
| `bomb_update`: the accel mask is the Y-subtract bit | killed |
| `bomb_update`: the latch is not cleared on a frame with no terrain | killed |
| `bomb_update`: the bounce count is spent only when the bomb survives | killed |
| `bomb_update`: the latch is read from the bounce COUNT instead | killed |
| `bomb_update`: floor 0xac -> 0xad | killed |
| `bomb_update`: floor compared unsigned | killed |

**Neither survivor is a missing case; both are rewrites that cannot differ from the code they
replace**, which is a different thing from an untested branch and is recorded as such:

**(a) the exact arm's two spellings are one function.** `heading_step` returns `wanted` where the
mutant returns `heading + difference`, and `difference` IS `wanted - heading` taken as a byte — so
the two agree for all 2^24 argument triples (swept off-line against a compiled copy of both). The
code keeps `wanted` because that is the instruction (`move.b d1,d0` at 0x1420c) and a reader should
not have to redo a modular-arithmetic argument to see that the comment matches the code.

**(b) the index mask is exact at every reachable call site.** `entity_from_index` transcribes
0x141c0's `and.l #$ff,d6`, and both call sites hand it a record BYTE, so nothing can supply an index
the mask would change. No seeded record reaches it either — the value comes from the game's own
record, not from the case. It stays because it is what the instruction does; widening the parameter
would be green today and wrong the first time a caller passes a word.

### Two residuals this batch leaves, and the surface that would catch each

**1. `entity_steer_toward_target` RETURNS WITH THE CARRY CLEAR, and the reconstruction cannot say
so.** Both its exits run into `entity_apply_velocity` @ 0x14306, which ends `andi #$fe,ccr` + `rts`
(the bytes `023c 00fe 4e75`, which `../out/prg_dis.txt`'s linear sweep renders as one bogus
`andi.b #$fe,#$75` — not a strange instruction). That flag is an ANSWER, not housekeeping: the
script VM's ext table at 0x19458 holds this routine at entry 8 and 0x14306 at entry 7, and
`actor_script_op_ext` @ 0x14cce is `jsr (a0)` + `rts`, so a handler's carry is the opcode's "run the
next opcode this frame" flag (`ori.b #$1,ccr` at 0x14cfa is the SET idiom). The C is `void` and its
glue stores no flag, so **no differential case can see it** — whoever wires ext entry 8 must answer
CARRY CLEAR from `../out/subsystems.tsv`'s reading and this note, not from the C's signature. The
surface that would catch a wrong choice is the ext-dispatch battery in `test_enemy.py`, and it does
not exist yet. Recorded here rather than fixed because the script VM is the `enemy` subsystem's.

**2. `bomb_collision_row` costs an on-target `__udivsi3` call the original does not pay.** It spells
`(bomb - A_entity_table) / ENTITY_STRIDE` as a full 32-bit divide, which is faithful over the whole
argument domain but which `m68k-elf-gcc` turns into a libgcc shift/subtract loop (~500-900 cycles)
where the original has one `divu.w #$2c` (~140). Measured: it is the only libgcc call in
`src/weapon.c` at both `-Os` and `-O2`. The cheap spelling — narrowing the dividend to a word — is
only equivalent while the record sits within 64 KB of the table, which every reachable slot does but
which neither C nor the differential can prove, so it is left alone and the cost is named here. The
surface that would catch it is a per-frame profile of the on-target build, not `make test`.

### One thing this batch names rather than ports

`entity_from_index` in `src/weapon.c` is `entity_ptr_from_index` @ 0x141c0's own mask and nothing
else: the address arithmetic under it is `src/collision.c`'s `entity_record`, now exported from
`include/collision.h` and called rather than copied (with `collision_table_row`, which `bomb_update`
needs for the same reason). 0x141c0 is **util's** routine by `../out/subsystems.tsv` and util has not
ported it — its own row at the end of this file is now stale, and corrected there. When util lands
0x141c0 and 0x141c2, `entity_from_index` is the one site to swap.

## Not reconstructed in the weapon / collision / player / input / score slice, and why

| Addr | Name | Status |
|---|---|---|
| `0x12df6` | `score_add_bcd` | **UNBLOCKED — `sound_start` (0x16ac8) has landed and is verified.** The four `abcd -(a1),-(a0)` are a leaf and the extra-life arm's call with D1 = 0x10 is now an ordinary composed callee, exactly as the three `fire_*` routines above compose it. It is the `score` agent's row, not this one's: no `src/score.c` exists yet, and a `## Verified — score` section without one fails `test_status.py` |
| `0x13d9e` | `powerup_capsule_collected` | **The `sound_start` block is gone; a DIFFERENT one replaced it, and it is about file ownership.** The routine and five of its six jump-table arms write `power_gauge_display` (0x198c3), which `../out/globals.tsv` assigns to the **hud** subsystem — so its address belongs in `include/hud.h`, which this agent may not create, and spelling it in `include/weapon.h` would plant exactly the duplicate `test_constants.py` refuses the moment that header lands. (This is the test that separates it from the three launch counters, which ARE named in `include/weapon.h`: those have no owner in `globals.tsv` at all, and the house rule for an unowned address is that whoever reads it names it. `panel_redraw_mask` 0x19904 and `selected_weapon` 0x198b4 are likewise unowned and would come with the port.) Second, the arms at 0x13e8a / 0x13eb4 / 0x13ee8 / 0x13f0e / 0x13f3a are **unnamed in `../names.txt`** — porting them would mean inventing five names in a file this agent does not edit. The body is read and waiting: the cursor advance when `0x19902` is clear; otherwise a commit that plays sfx **0x0f** and dispatches through **two** tables — 0x19348 at 0x13e1e for a NEW selection (with cursor 1 diverted to 0x13f0e before the table is consulted, which is what makes `powerup_slot1_activate` unreachable) and 0x1935c at 0x13e4a when the selection is unchanged. Port it in the change that lands `include/hud.h`, alongside the naming pass for the five arms. `powerup_slot1_activate` (0x13ede), the one arm that is named and whose only store is a `player` global, is verified above |
| `0x13cd4` | `ship_resolve_entity_hits` | Blocked on BOTH its callees, and neither is this agent's to write: `powerup_capsule_collected` above, and `explosion_spawn` (0x15510, the enemy subsystem's) — which the routine reaches by a `bra.w` TAIL CALL out of the middle of its own twelve-slot loop, so there is no prefix worth verifying without it. The loop itself is read: a4 walks entity slots 6..17 from 0x17b96 while d0 counts the bit it tests in the ship's overlap row (a3), a type-0x11 capsule is collected and killed with sfx 0x16, and anything `entity_type_is_lethal` (verified) accepts sets bit 0 of `death_event_flags` and leaves through the explosion |
| `0x14d14`, `0x14d88` | `actor_script_op_bounce_fall`, `actor_script_op_fire` | The `enemy` agent's this session, per that subsystem's ownership of the script VM. Both are now unblocked — the first calls `entity_apply_accel` (`util`, verified), the second `entity_steer_toward_target` (verified above) |
| `0x113c0`, `0x11c00`, `0x11d30` | `frame_weapons_and_spawn_stage`, `frame_draw_objects_and_collide`, `frame_resolve_hits_and_game_state` | The three frame stages — orchestrators over most of the game. Deferred to world-staging once their callees exist, per the playbook's order of attack |
| `0x14444` | `ikbd_send_cmd` | Blocked at KIT level. NOT restated here: the one explanation is its row in "Not reconstructed, and why" at the end of this file, and nothing in this slice depends on it |

## Verified — text (3)

The font is BSS and so is not in the `.PRG`: `_start` loads extchars.dat over it, so every case here
stages the real 1920 bytes from `../bin/disk`. Drawing against the zeroed bss would make every mask
and every plane byte 0x00 — a cleared cell for EVERY character, which would hide any glyph-indexing
mistake at all.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x12e40` | `draw_text_record` | 38 | ✅ verified | every one of the twelve `{column, row, text, 0}` records the game ships, drawn from the image's own bytes at its own column and row — which is what holds the column's SIGN extension against the row's ZERO extension, since the shipped rows run to 168 and a signed reading would put the credit lines above the screen. Plus synthetic edges: an empty string, both ends of the column byte's sign, a row byte of 0xff, and a run through the table arm. The cursor comes back ONE PAST the terminator and is dumped by the `movem.l` stub, so a caller walking a list of records is covered; poison over one record |
| `0x136f6` | `draw_bcd_number` | 26 | ✅ verified | six longwords including 0 (which draws eight zeroes, not one), 0x99999999 and two with nibbles above 9 — the digit is turned into a character by adding 0x30 with no range check, so those draw ':' through '?'. A rightmost column of 7 walks the run off the left of the row into the previous one, which a forward-stepping candidate would not do (mutation measured killed); hi-garbage in the column; poison over all eight cells |
| `0x13710` | `draw_char` | 186 | ✅ verified | all 256 character codes, sharded four ways — exhaustive because the routine forks FIVE ways and two of the boundaries are single values (0x40 goes through the table, 0x41 does not); above 0x7f the arithmetic arm indexes past the 48-glyph font and below 0x20 the table arm indexes before the table, both in-image and both driven. Then columns 0..40 for each of the five arms, which is what holds the odd/even cell address — a `column * 4` reconstruction agrees on every even column and is wrong on every odd one. Every case draws over a NOISY frame, which is what makes the AND mask visible at all; the space's no-op is an empty diff over that noise; poison on four arms |

## Verified — util (8)

`rand16` is the ninth routine of this subsystem and has its own section above (it lives in
`src/rng.c`). `entity_ptr_from_index` and its second entry are the two left; see the table at the
bottom.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13858` | `copy_block_words` | 14 | ✅ verified | the five byte counts the game's own call sites pass, plus odd counts (the odd byte is DISCARDED), five source/destination overlaps at word and row granularity — which is what holds the copy's forward direction — and the two counts only the dumped registers can tell apart: 0 (which `dbf` wraps to 0x10000 words, run in place so the traffic stays inside the scratch band) and 0x20004, whose half exceeds a word so that `lsr.l`/`sub.l` differ from their word twins ONLY in the counter D2 comes back with. Destination seeded, so a short copy differs; poison |
| `0x1424c` | `angle_to_target` | 136 | ✅ verified | a ring of 81 source/target pairs covering all eight octants, both axes and both diagonals; single-bit sweeps over both coordinates of both records, which separate `btst #2` from its neighbours and prove only the TARGET is rounded up; coordinates with bit 15 set, held by `lsr.w`'s logical shift; the zero vector, the one input that runs the search's counter all the way to 0; 400-case sharded fuzz; poison on four quadrants |
| `0x142d4` | `entity_set_velocity_from_angle` | 50 | ✅ verified | every one of the 64 circle angles against six speed bytes straddling the sign bit (`ext.w` before `muls.w` — an unsigned reading agrees on 0..0x7f and differs above), plus four angles ABOVE 0x3f, where the x index's byte mask reads past the 64-word table while the y index's `& 0x3f` stays inside it; hi-garbage in D0, D1 and D3 |
| `0x14306` | `entity_apply_velocity` | 26 | ✅ verified | seven velocity words × seven × four positions, including both extremes whose `<< 8` fills the longword. NOTE FOR `include/entity.h`, WHICH IS FROZEN: its `ENTITY_X`/`ENTITY_Y` are tagged `.w signed`, but this routine adds a LONGWORD at both offsets — the fields are 32-bit fixed point with 8 fractional bits and the tagged word is their integer half, which is also why `ENTITY_Y` is four bytes past `ENTITY_X` rather than two. Nothing is wrong today (the box test reads only the integer half); the tag is narrower than the field |
| `0x143f8` | `entity_apply_accel` | 76 | ✅ verified | all 256 direction bytes, sharded four ways — exhaustive because the four bits are two EXCLUSIVE pairs tested in order and because, with neither bit of a pair set, the original branches PAST its own store, so that axis's word must come back untouched; wrap cases at both ends of the word; hi-garbage in D1. Its acceleration pair (0x16/0x18) is named in `include/util.h` because the frozen `entity.h` does not have it — see the note under "Not reconstructed" |
| `0x15644` | `cos_scaled` | 16 | ✅ verified | all 360 degrees plus the wrap boundary either side and two negative angles; names.txt reports NO caller for this entry, and it is reconstructed because it falls straight into `sin_scaled` — a port that stopped at the fall-through boundary would leave a live entry point out |
| `0x15654` | `sin_scaled` | 64 | ✅ verified | all 360 degrees at both ends of the amplitude range, the three fold boundaries either side, and the angles OUTSIDE 0..359 — which is what holds the compares' SIGNEDNESS: 0x8000 and 0xffff take the FIRST arm, where an unsigned reading would take the fourth. Poison on five angles |
| `0x15694` | `sin_quadrant_scaled` | 22 | ✅ verified | every angle in the 91-word first-quadrant table against six amplitudes; five angles that index BELOW the table (the `d0.w` index register sign-extends, and every reachable address is still in-image); hi-garbage in both arguments. The answer is a `swap`, not a shift — the product's low half comes back in D0's HIGH word, and `>> 16` agrees on the low word and differs on that one (mutation measured killed) |

## Verified — fileio (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x144e8` | `load_file` | 68 | ✅ verified | four of the game's own files (extchars.dat, power.dat, status.pi1, lev1.map) staged from `../bin/disk` under the names the IMAGE holds — read out of the table at 0x19686 rather than typed, so a staged name that did not match would fail to open and the model REFUSES rather than fabricating a handle; short counts, a count past the end of the file, and a count of 0; the destination seeded with noise so a short read leaves some of it standing; two loads chained through one stub, which is what holds the handle word being rewritten; poison. The failure path (an unstaged name → Fopen -1) is UNREACHABLE under the model: `os_fopen` tallies a refusal and `differential` throws the case away, which is the correct answer — a case that tested it would be testing `shim.c` |

## Verified — irq (7)

Every handler returns with `rte`, so each case enters through `abi.interrupt_frame_pokes` — a stub
that pushes the 68000 exception frame the handler pops and lands its `rte` on an ordinary `rts`. The
frame is inside the stack-guard band the differential already drops.

**WHAT THESE ROWS DO NOT CLAIM.** `$ff8240..` (the shifter's colour registers) and `$fffa0f` (the
MFP's in-service register B) are outside the 1 MiB image: the oracle DROPS an off-image write and
the candidate makes none, so **no case here can fail on a palette upload or an interrupt
acknowledge**. Six of the seven handlers make one or both. `src/irq.c` routes them through
`shifter_write_palette` / `shifter_clear_pen0` / `mfp_ack_timer_b`, and those three live in
`src/irq_hw_offtarget.c` — a translation unit a build for the real Atari does NOT compile, which is
the split `tools/recreate_kit/src/psg.c` uses for the one hardware surface the kit does model. So
the omission is one named file rather than a silence spread through six routines, and a target
build cannot inherit the no-ops by accident. **The surface that would catch it** is a kit-level
hardware-write ledger
mirroring `psg.h`'s — one write feeding an ordered ledger both sides compare — or, on target, a
Hatari register snapshot (`docs/on-target-execution.md`). Until one exists these are the same class
as `ikbd_send_cmd` below, and the rows say which half of each handler is held.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x106a2` | `vbl_isr_title` | 12 | ✅ verified | IN-IMAGE HALF ONLY — the sound tick, over an armed voice, compared in memory and through the PSG ledger. Its `clr.w $ff8240` is off-image and unpinned (see above) |
| `0x106ae` | `timer_b_raster_isr` | 200 | ✅ verified | IN-IMAGE HALF ONLY — both colour cycles at, and either side of, the frame they fire on, over a shadow seeded with DISTINCT random words — over equal words (or the zeroes the `.PRG` ships for most pens) both machines would be invisible. The countdown of 0 is the case that matters: `subq.b`+`bne` wraps it to 0xff and does NOT fire, which is what an `if (--n <= 0)` reconstruction gets wrong. The two periods differ (8 and 4), so a candidate reloading both from one constant differs on one; poison. Its eight-longword palette upload is off-image and unpinned |
| `0x10776` | `vbl_isr` | 12 | ✅ verified | THE ONE HANDLER WITH NO HARDWARE STORE AT ALL, and so the only one held end to end: the sync flag over three values, and the sound tick with a voice armed, compared in memory and through the PSG ledger |
| `0x10782` | `timer_b_isr` | 16 | ✅ verified | IN-IMAGE HALF ONLY — the sync flag over three values, which is the whole of its in-image effect. Its `bclr #0,$fffa0f` is off-image and, unlike the palette, has no shadow at all — nothing about it is visible in the image |
| `0x12c9e` | `attract_vbl_isr` | 34 | ✅ verified | IN-IMAGE HALF ONLY — the line word, the sync flag and the list cursor, each seeded with a value the handler cannot produce (0x1234, 0x01, 0xdeadbeef) so a missing write shows up on the plain pass, plus the sound tick. Its `clr.w $ff8240` is off-image and unpinned |
| `0x12cc0` | `attract_rasterbar_isr` | 130 | ✅ verified | IN-IMAGE HALF ONLY — both band edges either side of each — the line is incremented FIRST, so entering on 0x26 puts the handler on 0x27, the first line outside — and the signed arm (a line of 0xffff increments to 0 and is BELOW the band, not far above it); three cursor positions walking the list; and a count of 0, which `subi.w` wraps to 0xffff so the pair is NOT retired. The count word is decremented IN PLACE, so the list is consumed as the band is painted; poison. Its colour store and its acknowledge are off-image and unpinned. The two out-of-band arms differ only in a delay loop with no memory effect, which is not reconstructed |
| `0x13c26` | `vbl_menu` | 120 | ✅ verified | IN-IMAGE HALF ONLY — every phase byte the counter can hold, including the three that never occur in play (2, 3, 0xff): the original counts UP and compares against 2, so a phase starting above 1 runs all the way round rather than wrapping next frame — which is what separates the instruction pair from the `^ 1` toggle a paraphrase would write (mutation measured killed). Its own eight-longword palette upload is off-image and unpinned |

**NO POISON PASS ON THE FOUR HANDLERS THAT TICK THE SOUND DRIVER.** Measured, not assumed: with
`poison=True` both `vbl_isr` and `attract_vbl_isr` fail inside the driver at `psg_reg_shadow+1`,
because the tick's outputs include the modulation counters and the tune cursor, which are also its
control flow. What holds them instead is that every flag and pointer a case drives is seeded with a
value the handler cannot produce.

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

## Mutation check — sound / util / text / fileio / irq

A second sweep, kept separate from the one above so that the two agents' counts never have to be
merged into one number. **Thirty-six mutations, 33 killed, 3 survivors**, each rebuilt with
`rm -f build/*.so` first and every one run from a green baseline. The four that touch code the
pre-commit review reshaped (the shared little-endian pair, the modulation stepper's counter helper,
the `swap`) were RE-RUN after that reshaping rather than carried over.

| mutation | result |
|---|---|
| `loop_passes` dropped from `copy_block_words`' row count | killed |
| `sin_quadrant_scaled`'s `swap` replaced by `>> 16` | killed |
| `ANGLE_FLAG_SWAPPED` 0x0f -> 0x1f | killed |
| `VELOCITY_QUARTER_TURN` 0x10 -> 0x11 | killed |
| `entity_apply_velocity`'s `<< 8` -> `<< 7` | killed |
| `entity_apply_accel`'s subtract arm disabled | killed |
| `PLANE_STRIDE` 2 -> 1 | killed |
| `draw_bcd_number` steps the column FORWARD | killed |
| `draw_text_record`'s column read UNSIGNED | killed |
| `draw_char`'s space compared as a WORD not a byte | killed |
| `draw_char`'s letter threshold compared UNSIGNED | killed |
| `SOUND_STREAM_CHANNEL_TAG` 0xfa -> 0xfb | killed |
| the SFX voice toggle XORs 2 instead of 1 | killed |
| the shadow flush pushed ASCENDING (image identical; only the PSG ledger sees it) | killed |
| `PSG_TICK_FLUSH_REGS` 11 -> 10 | killed |
| the note period's doubling dropped | killed |
| `MOD_DELTA_NEUTRAL` 0x80 -> 0x81 | killed |
| `SOUND_ROW_NOTE_MAX` 0x65 -> 0x64 | killed |
| `VOICE_MOD_TEMPLATE_BYTES` 12 -> 11 | killed |
| the pitch sweep adds the step once instead of twice | killed |
| `sound_voice_tick`'s SECOND enable test deleted | killed |
| `sound_cmd_swap_tunes` stops backing the cursor up one byte | killed |
| `le16` read big-endian (the shared little-endian helper, so this is every table at once) | killed. Worth recording that it USED to be killed as a HANG: while the read was spelt out three times, mutating only the modulation index left the tune lookup right and sent the candidate's interpreter round for ever, and a candidate infinite loop is a hung pytest worker rather than a named assertion (the oracle has an instruction cap; the candidate has none). Collapsing the three copies into one helper is what turned it into an ordinary red |
| the modulation stepper's SECOND counter arm deleted (the repeat count never elapses, so the cursor never steps) | killed |
| `load_file`'s handle store deleted | killed |
| `PALETTE_ROTATE_PERIOD` 4 -> 8 | killed |
| the palette swap long left unswapped | killed |
| `countdown_elapsed` fires on `> 0x80` instead of `== 0` | killed |
| the cycle-word rotation one word short | killed |
| `vbl_isr`'s sync-flag clear deleted | killed |
| the attract bar's count test replaced by "always retire" | killed |
| the attract band's upper edge `>=` -> `>` | killed |
| `vbl_menu`'s phase wrap `==` -> `>=` | killed |
| `angle_to_target`'s octant-swap compare read UNSIGNED | **SURVIVED** |
| `sin_scaled`'s first fold boundary `<=` -> `<` | **SURVIVED** |
| `load_file` closes from the REGISTER instead of re-reading `A_file_handle` | **SURVIVED** |

All three survivors are **unobservable by construction**, not coverage holes, and none can be
reached by seeding real data:

* *`angle_to_target`'s swap compare.* Both legs have already been made non-negative by the two
  negations above it, and the only value where a signed and an unsigned compare disagree is 0x8000
  (whose negation is itself). The legs are cell deltas — coordinates are shifted right by 3 before
  subtraction — so they span at most −0x1fff..0x2000 for any 16-bit coordinate pair. 0x8000 is
  unreachable, and the two readings agree on every input the routine can be handed.
* *`sin_scaled`'s 90-degree boundary.* At exactly 90 the first arm computes `sin_q1(90)` and the
  second `sin_q1(180 − 90)`, which is the same call. The fold is continuous there, so `<=` and `<`
  are the same function. The 360-degree boundary in `cos_scaled` is the same argument one wrap
  further out (`sin_scaled(360)` folds back to `sin_q1(0)`, which is `sin_scaled(0)`), and it is
  recorded here rather than as a second row because it is one fact, not two.
* *`load_file`'s handle round trip.* The word it stores and the word it reads back are the same
  value with nothing between them that could change it, so closing from the register agrees on every
  input. The store itself IS pinned — deleting it is killed above — and it is the round trip, not
  the store, that no case can see.

## Not reconstructed, and why

| Addr | Name | Status |
|---|---|---|
| `0x153c0` | `sprite_bank_build_preshift8` | Not blocked either: it composes the now-verified 0x13858 (`copy_block_words`) with the already-verified `sprite_preshift8_2px`, and is the natural next sprite row |
| `0x141c0` | `entity_ptr_from_index` (and `0x141c2`, its D6 entry) | **THE BLOCKER THIS ROW USED TO NAME IS GONE:** it said "there is no `include/player.h` yet", and there is — it defines `A_entity_table`, and `src/weapon.c` and `src/collision.c` both include it to read that address. A four-instruction leaf, still unported, and now the only thing standing between the tree and one home for the entity-record address: `entity_record` in `include/collision.h` is its arithmetic and `entity_from_index` in `src/weapon.c` is its `and.l #$ff,d6` mask, both waiting to be replaced by a call. Port the two entries together |
| `0x12a28` | `title_screen_draw` | The last `text` routine. It composes `draw_text_record` (verified) with the ZYNAPS logo blit and a buffer flip, both of which belong to subsystems this agent does not own — the logo blit is `sprite`'s and the flip is `video`'s |
| `0x156ac` | `asteroids_load_and_build` | The second `fileio` routine. Its `load_file` half is verified now; the rest expands bigast.dat's six masked sprites into 8-frame 3-cell banks, which is sprite work and reads as the natural pair to `sprite_bank_build_preshift8` above |
| — | the whole `hud` and `highscore` subsystems | Untouched this session, and neither is blocked: the HUD's ten routines are blits into the status panel that compose `draw_char`/`draw_bcd_number` (verified) with the panel graphics from status.pi1 and power.dat, and the four high-score routines compose those with the table and — for `highscore_enter_name` — the input model. They are the next natural rows once the panel's own staging exists |
| `0x16e90`, `0x19932`, `0x19a0a` | three name-map corrections | Not code: `../out/names_sound.txt` carries them for the orchestrator. Two `var` lines point one byte early at the previous record's terminator (the code loads 0x19933 and 0x19a0b), and the comment on the SFX toggle assumes a 0/1 byte where the `.PRG` ships 2 |
| `0x14444` | `ikbd_send_cmd` | **Blocked at the KIT level, and the earlier row prescribed the wrong fix.** The routine spins on bit 1 of the IKBD ACIA status at `$fffc00` and then writes `$fffc02`. Adding `$fffc00` to `os.h`'s `OS_HW_*` set as a VOLATILE address does NOT work: VOLATILE means one declaration describes exactly one read and a SECOND read in the same run is refused — but a spin loop's whole nature is re-reading. Nor does a STATIC declaration, whose contract is that the machine's answer never changes; a status byte that must read "not ready" and then "ready" is precisely what the Phase 7 model excludes. And the write half has no ledger at all: `hw.h` exports `hw_read8` and no `hw_write8`, so a reconstruction's `$fffc02` store would be invisible on both sides. The correct fix is a shim-level ACIA model (a status byte that becomes ready after a declared number of polls, the way `sched.c` counts polls per wait site) plus an IKBD write ledger mirroring `psg.c` — playbook §5's "model the input hardware registers so busy-waits terminate". That is kit work, not this project's, and the surface that would catch it is on-target rather than the differential |
| `0x14456` | `ikbd_acia_isr` | Same `$fffc00`/`$fffc02` gap as above, and it is an interrupt handler entered around a frame rather than a called routine |
| `0x15838` | `mothership_sprite_preshift` | **Blocked only on file OWNERSHIP, not on anything technical.** The body is `asteroid_preshift_bank`'s exact shape one geometry wider — five cells 400 bytes apart, 40 rows, a 2000-byte frame stride — and would share the same `shift_masked_frame_right_1px` helper. Its tail then sets four completion flags (`boss_in_playfield` 0x19aad, `mothership_phase_active` 0x198b0, `mothership_phase_frames` 0x19efe, `mothership_prep_stage` 0x19911), and `../out/globals.tsv` puts all four in the **mothership** subsystem — so their addresses belong in `include/mothership.h`, which the agent owning that subsystem creates. Spelling them in `sprite.h` instead would trip `test_constants.py`'s duplicate-address check the moment that header lands. Port it in the change that can include it |
| `0x15b7c` | `draw_sprite_masked_collide` | 450 bytes, and the widest of the sprite routines: three separate blit bodies chosen by x band (left edge, middle, right edge), a keep-mask pair read from `shift_mask_table` (0x1821e), and a terrain-collision flag stored through A5. Nothing about it is blocked — it needs a battery of its own, on the same constructed-record footing as `draw_sprite_masked` above plus a real `shift_mask_table` index |
| `0x162c2` | `scroll_emit_tile_column` | ~1840 bytes, the largest routine in the scroll subsystem: eighteen hand-unrolled copies of one tile decode, three entry arms (`bmi` to 0x16642 and to 0x16482 on the two map words), and three destinations at once — the screen's right edge, the off-screen page and the 32-pixel workspace the two emitters drain. Not blocked; it is a body-read job rather than a mechanism problem, and it wants the map (`map_rle_decompress`, verified above) and the tile set staged from a real level so the tile indices it shifts by 64 are the game's own |

## Suite

`make test` — **1858 passed**. `make guarded` — same count, 14061
candidate runs guarded across 10 workers, no fault.
