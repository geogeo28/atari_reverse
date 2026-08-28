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

## Verified — sound (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x16b32` | `sound_lookup_tune` | 28 | ✅ verified | all 256 sound numbers, sharded four ways, which is what pins `adda.w`'s SIGN EXTENSION: 52 of the words a number can reach have bit 15 set (the first at 45, 0x80c8 → 0xf2b0, below the load base), so dropping `sign_ext16` fails at 45. Also hi-garbage and a set high byte in D1 (only `andi.w #$ff` matters, and D1's high word must come back untouched); poison on 4, including the boot tune 0x0b and the first negative offset. The routine writes NO memory, so its answers reach the diff through a `jsr`+store stub (`test/abi.py`) |

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

## Verified — weapon (13)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13d3e` | `entity_type_is_lockable` | 48 | ✅ verified | all 256 type bytes, sharded four ways — exhaustive because the bound is a SIGNED byte compare, so every type from 0x80 up takes the in-range arm and resolves through `ext.w` to a word offset of 0x1ff0..0x1ffe, 8 KB past the table; the eleven types the shipped 0x191ac table lists; both sides of the signed edge; poison on an in-class and an out-of-class type. The answer is the Z FLAG and the routine writes no memory, so the case enters at a `seq` stub (`test/abi.py`). ONE RESIDUAL: the bound's inclusiveness — see the survivor ledger |
| `0x13ede` | `powerup_slot1_activate` | 10 | ✅ verified | the one word store, driven over a timer already holding the value it is about to be given (so the poison pass is what makes it a test), over 0 and 0xffff, with a trailing guard word that catches a long store. UNREACHABLE IN THE GAME — `powerup_capsule_collected` @ 0x13d9e diverts cursor 1 to 0x13f0e before the 0x19348 table is consulted — so this is a read-verified routine that the differential nonetheless drives directly |
| `0x13f72` | `powerup_downgrade_on_death` | 44 | ✅ verified | all 256 speed bytes and all 256 power bytes, each sharded four ways, plus a 7x6 corner grid of the two together. The sweep is what pins the SIGNS: the speed floor is `subq.b` + `bpl` on the decremented byte, so 0x00 wraps to 0xff and clamps while 0x80 becomes 0x7f and survives; the power floor is a signed `cmpi.b #$2` + `bge`. The two levels are adjacent bytes, so the grid also rules out one being clamped from the other's value; poison on a clamping and a non-clamping case |
| `0x14092` | `entity_pos_from_ship` | 20 | ✅ verified | five x/y pairs across the word including both extremes, with the destination record seeded with noise, so a copy of the wrong field — or of a long where the original copies two words — diverges; poison |
| `0x140f6` | `entity_type_is_missile_target` | 48 | ✅ verified | the same battery as `entity_type_is_lockable` above, against the 0x1918e table. Its record register is A1 and it clobbers A0, which is why the stub reloads A0 after the call rather than taking it through the run's registers. Same one residual |
| `0x152a4` | `player_shot_update_all` | 70 | ✅ verified | one slot of each kind plus a dead slot and an unknown kind in a single pass; the same kind in all six slots at once (which is what a wrong stride lands beside); both phases of the half-rate gate the puff arm sits behind. All 20 records are seeded and slots 6..19 must come back untouched, so a loop that overran the six shot slots diverges; poison |
| `0x152ea` | `shot_set_sprite_a` | 36 | ✅ verified | all 256 heading bytes, sharded four ways. The game's own headings are 0..0x3f, exactly the variant table's length, but BOTH lookups sign-extend their index — heading 0x80 reads 128 bytes BELOW the variant table, and a variant byte found there is itself signed and reaches 512 bytes below the sprite table — so the full 256 is what pins the two `ext.w`s (dropping either turns it red above 0x7f) and every resolution stays inside the text segment. The shipped variant table's 8-way fan-out is asserted off the image; poison on four headings; `make guarded` covers the computed indexes |
| `0x15370` | `shot_anim_puff` | 62 | ✅ verified | all 256 incoming frame bytes on the live phase, sharded four ways — three arms meet there and only a sweep separates them: the death frame is compared for EQUALITY so 6 and 0xff keep animating, the pointer index is `(frame - 1) & 0xf` so frame 0x11 draws frame 1's picture, and the increment is a byte so 0xff wraps to 0. Plus the half-rate gate over three non-zero phases and five frames, which must touch nothing at all; poison |
| `0x15582` | `shot_retire_kind32` | 50 | ✅ verified | the full alive x type x height grid (4 x 5 x 4), which pins both halves of the guard and WHICH lock slot the sign of field 8 releases — both lock bytes are poked to distinct markers, so releasing the wrong one is a diff rather than a coincidence, and the heights step across bit 15 in both directions. Counts driven at 0x00 so the `subi.b` wrap is seen not to borrow into its neighbour; poison over record, count and lock |
| `0x155b4` | `shot_retire_kind36` | 14 | ✅ verified | the same alive x type grid as its two neighbours, which is how the ABSENCE of a guard is stated rather than assumed: even a dead, wrongly-typed slot is converted and counted down. Count wrap at 0x00; poison |
| `0x155c2` | `shot_retire_kind33` | 32 | ✅ verified | alive x type grid; count wrap at 0x00; poison |
| `0x155e2` | `shot_to_puff` | 34 | ✅ verified | every field the rewrite touches, over a y that borrows across both ends of the word (`subi.w #$3` takes 0 to 0xfffd and 0x8002 to 0x7fff). The rest of the 44-byte record is noise, so writing ENTITY_HEIGHT as a byte or the sprite pointer as a word diverges; poison. THE SPRITE ADDRESS IS THE RELOCATED ONE, 0x6791e — `../out/prg_dis.txt` prints an immediate-longword `<RELOC ptr>` operand UNRELOCATED (0x5791e) even though it relocates `lea` operands, and ../names.txt's comment carries the unrelocated number |
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

## Not reconstructed in the weapon / collision / player / input / score slice, and why

| Addr | Name | Status |
|---|---|---|
| `0x12df6` | `score_add_bcd` | **Blocked on `sound_start` (0x16ac8), the sound subsystem's.** The four `abcd -(a1),-(a0)` are a leaf, but the extra-life arm calls 0x16ac8 with D1 = 0x10 and that routine writes in-image voice-slot state the diff would compare. Reconstructing it here would mean writing another subsystem's function; testing only the non-awarding arm would leave the award read-verified while the row claimed green. It is the natural next score row once `sound_start` lands. THIS IS WHY THERE IS NO `## Verified — score` SECTION: a section's name must match a `src/<name>.c` (`test_status.py`), and an empty `src/score.c` would be a file with no code in it |
| `0x13d9e` | `powerup_capsule_collected` | Same block: its second arm calls `sound_start` with D1 = 0x0f before dispatching through the 0x19348 / 0x1935c jump tables. Its arms at 0x13ee8 / 0x13f0e / 0x13f3a are unnamed in `../names.txt` and would be ported with it; `powerup_slot1_activate` (0x13ede), the one arm that is named, is verified above |
| `0x13cd4` | `ship_resolve_entity_hits` | Calls `powerup_capsule_collected` above and `explosion_spawn` (0x15510, the enemy subsystem's) |
| `0x141d6` | `entity_steer_toward_target` | Blocked on four `util` routines: `entity_ptr_from_index` (0x141c0), the angle-to-target helper at 0x1424c, `entity_set_velocity_from_angle` (0x142d4) and the position integrator at 0x14306. NOTE for whoever ports 0x14306 and this one's tail: `../out/prg_dis.txt` renders the bytes `023c 00fe` + `4e75` at 0x14246 and 0x1431e as one bogus `andi.b #$fe,#$75`. They are `andi #$fe,ccr` (clear C) followed by `rts` — a linear-sweep artefact, not a strange instruction |
| `0x13f9e`, `0x1401a`, `0x14324` | `fire_seeker`, `fire_homing_missile`, `fire_bomb` | All three end by calling `entity_set_velocity_from_angle` (0x142d4, `util`); the seeker and the bomb also call `sound_start` |
| `0x140a6`, `0x14126` | `seeker_update`, `homing_missile_update` | Both call `entity_ptr_from_index` (`util`) and `entity_steer_toward_target` above |
| `0x14376` | `bomb_update` | Calls `sound_start` and `entity_apply_accel` (0x143f8, `util`); its terrain test is the already-verified `collision_chain_walk` |
| `0x14d14`, `0x14d88` | `actor_script_op_bounce_fall`, `actor_script_op_fire` | The first calls `entity_apply_accel` (`util`), the second `entity_steer_toward_target` |
| `0x113c0`, `0x11c00`, `0x11d30` | `frame_weapons_and_spawn_stage`, `frame_draw_objects_and_collide`, `frame_resolve_hits_and_game_state` | The three frame stages — orchestrators over most of the game. Deferred to world-staging once their callees exist, per the playbook's order of attack |
| `0x14444` | `ikbd_send_cmd` | Blocked at KIT level. NOT restated here: the one explanation is its row in "Not reconstructed, and why" at the end of this file, and nothing in this slice depends on it |

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
| `0x15838` | `mothership_sprite_preshift` | **Blocked only on file OWNERSHIP, not on anything technical.** The body is `asteroid_preshift_bank`'s exact shape one geometry wider — five cells 400 bytes apart, 40 rows, a 2000-byte frame stride — and would share the same `shift_masked_frame_right_1px` helper. Its tail then sets four completion flags (`boss_in_playfield` 0x19aad, `mothership_phase_active` 0x198b0, `mothership_phase_frames` 0x19efe, `mothership_prep_stage` 0x19911), and `../out/globals.tsv` puts all four in the **mothership** subsystem — so their addresses belong in `include/mothership.h`, which the agent owning that subsystem creates. Spelling them in `sprite.h` instead would trip `test_constants.py`'s duplicate-address check the moment that header lands. Port it in the change that can include it |
| `0x15b7c` | `draw_sprite_masked_collide` | 450 bytes, and the widest of the sprite routines: three separate blit bodies chosen by x band (left edge, middle, right edge), a keep-mask pair read from `shift_mask_table` (0x1821e), and a terrain-collision flag stored through A5. Nothing about it is blocked — it needs a battery of its own, on the same constructed-record footing as `draw_sprite_masked` above plus a real `shift_mask_table` index |
| `0x162c2` | `scroll_emit_tile_column` | ~1840 bytes, the largest routine in the scroll subsystem: eighteen hand-unrolled copies of one tile decode, three entry arms (`bmi` to 0x16642 and to 0x16482 on the two map words), and three destinations at once — the screen's right edge, the off-screen page and the 32-pixel workspace the two emitters drain. Not blocked; it is a body-read job rather than a mechanism problem, and it wants the map (`map_rle_decompress`, verified above) and the tile set staged from a real level so the tile indices it shifts by 64 are the game's own |

## Suite

`make test` — **1268 passed**. `make guarded` — same count, 8623
candidate runs guarded across 10 workers, no fault.
