# Reconstruction status — Zynaps

Human-readable C reconstruction of Zynaps (Hewson, 1988), each function **verified byte-for-byte
against the original 68000 code** by the shared differential harness (`tools/recreate_kit`: a
Musashi oracle running the real code vs. the compiled reconstruction, on the same memory image).
`../names.txt` is the source of truth for every name; it names all 195 functions, of which these
are the ported ones.

**Verified: the sum of the per-section counts below**, out of 195. Each `## Verified — <subsystem>`
heading carries its own count, so the only number an agent touches is its own section's;
`test/test_status.py` fails if a count and its rows disagree, and if a section names a subsystem
with no `src/<name>.c`.

**Not every verified row is a function, and the difference is worth stating before the counts are
quoted.** Eleven rows are SLICES — named address RANGES rather than functions — and each one's
Verification column opens with the `[start, end)` the differential actually runs. Nine of them are
`## Verified — init`'s, because the boot chain never returns and so offers no `rts` to stop at; the
other two are `## Verified — highscore`'s, the pure halves of two routines whose other halves are the
keyboard-driven loops. Every other row is a whole function. So today's sum is
**196 rows = 185 functions + 11 slices**. Every one of the 185 has an
`fn` line in `../names.txt` (four handlers the name map first reached only by `cmt` —
`anim_enemy_type16` 0x146f6, `anim_enemy_type20` 0x1467e, `anim_enemy_type22` 0x146ba,
`actor_script_op_thrust_to_centre_y` 0x14e1c — were named there once this reconstruction pinned
them). The eleven slices sit inside three more `fn` lines: `_start` @ 0x10000,
`game_over_screen` @ 0x12e66 and `highscore_check_and_insert` @ 0x12eae.
**195 − 185 = 10 named functions are not ported whole.** `_start` is one of them and appears in
`## Not reconstructed, and why` as the RANGES its slices do not join up over rather than as a row;
the other 9 each have exactly one row there, and two of those rows — 0x12e66 and 0x12eae — now say
which HALF is verified above rather than claiming nothing is.

**The memory map is README's, not this file's.** Where the stubs, the scratch buffers and the staged
files sit relative to the program and to the game's two hard-coded framebuffers is decided in
[`README.md`](README.md), "Free image space is not simply 'above the program'", and pinned by
`test/test_constants.py`. Nothing here restates it.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table, and the conventions all live there rather than being restated here.

Where an argument is load-bearing it has ONE home, cited from the others:

| the argument | its home |
|---|---|
| which globals a subsystem BORROWS, and from whom | `STATUS.md`, "## Borrowed globals" — one table for the whole project; the definitions are in the borrowing subsystem's own header, under a "BORROWED" note |
| why `tos_malloc_unused` is safe (the byte scan) | [`project.toml`](project.toml), re-tested by `test/test_heap_guard.py` |
| where each shipped preshift width comes from | `src/sprite.c`, "SHIPPED WIDTHS" |
| why the fuzz caps the frame width | `test/test_sprite.py`, `FUZZ_MAX_FRAME_BYTES` |
| what the entity record's fields are, and which are held by a test | `include/entity.h` |
| why a shifter store cannot be seen by the byte diff, and which surface holds it | `include/video.h`, header comment |
| what the masked sprite format is (mask word, four planes, 16-pixel cells) | `include/sprite.h`, "THE MASKED SPRITE FORMAT" |
| how the scroller's pieces fit together | `include/scroll.h`, header comment |
| how the differential method works | [`../../buggyboy/recreate/README.md`](../../buggyboy/recreate/README.md) |
| why the sprite fuzz caps the height from BELOW | `test/test_sprite.py`, `BLIT_FUZZ_MIN_HEIGHT` |
| why the map battery passes no `max_insns` | `test/test_scroll.py`, above the ctypes block |
| why the animation dispatcher reads its target out of the image | `src/enemy.c`, `enemies_animate_all` |
| which routines clobber A0, so the flag stub must load it itself | `test/test_enemy.py`, `A0_CLOBBERING_ENTRIES` |
| which input sets are driven short of 256, and what bounds them | `STATUS.md`, "## Coverage limits" |
| what every mutation sweep measured, per slice | `STATUS.md`, "## Mutation ledger" |

## Verified — entity (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13c9e` | `entity_kill_if_offscreen` | 54 | ✅ verified | all 36 combinations of the four box bounds one step either side; the dead-record early return; extreme coordinates at both ends of the word; six flag words through both the clearing and the non-clearing arm, which pins `clr.b` against `clr.w`; 600-case sharded fuzz clustered on the boundaries; poison on the clearing arm. THREE RESIDUALS, all proved unobservable rather than untested — the `tst.w`-vs-`tst.b` guard, the early return, and the coordinates' signedness; see the ledger below |

## Verified — enemy (58)

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
| `0x141c0` | `entity_ptr_from_index` | 22 | ✅ verified | all 256 indices `and.l #$ff` admits, sharded four ways, through BOTH entry points — 0x141c0 with the index in D0.b and 0x141c2 with it already in D6 — and the stub dumps D6 as well as A1, because `mulu.w` leaves the BYTE OFFSET in D6 rather than the index, which is what separates the multiply from a shift-and-add. Hi garbage in whichever register the entry does not read; poison on four indices. Not `util`'s file although it is util's routine by subject: the enemy script ops are its first ported callers |
| `0x146f6` | `anim_enemy_type16` | 58 | ✅ verified | NO `fn` LINE IN `../names.txt` — the name is this reconstruction's, taken from that file's own `var 0x1929c anim_frames_type16` and proposed back in `../out/names_enemy2.txt`. Fifteen frame bytes including 0x10 and 0xff, against a table span seeded 0x400 wide — which is what makes the UNMASKED index a difference (0x10 reads 0x3c bytes in where the four-frame handlers' `andi.l #$f` would read 0, and 0xff reaches 0x3f8 past the base); five blocking gate values on A_anim_phase_b, the OTHER phase byte and the opposite polarity to type17's; poison on two frames |
| `0x1467e` | `anim_enemy_type20` | 60 | ✅ verified | the same coined name (`var 0x191b4 anim_frames_type20`) and the same battery, plus nine values of the per-section frame LIMIT it reads from a global — each driven from the frame that steps onto it exactly, so a candidate that hard-coded 5 differs everywhere but at 5 and one that read the other section's byte differs everywhere. The wrap is an EQUALITY test, which frame 6 against a limit of 5 pins against a `>=` bound |
| `0x146ba` | `anim_enemy_type22` | 60 | ✅ verified | the same coined name (`var 0x191cc anim_frames_type22`) and the same battery again, from the other limit byte and the other table; `test_limit_anim_frame_tables_are_distinguishable` asserts the shipped image really holds three different ones |
| `0x147f2` | `enemies_animate_all` | 76 | ✅ verified | one record of each of the nine animatable types in a single pass AND the same set rotated one slot on, which is what separates "dispatched by type" from "dispatched by position"; each type in all eleven slots; a twelfth live record that must stay untouched; five phase values through the unconditional `not.b` with every record dead; 60-case fuzz. THE HANDLER IS READ OUT OF THE IMAGE, and two cases poke a real handler's address into the slot a type of 0x31 / 0x80 / 0xff reaches to prove it — which also pins the guard's SIGNEDNESS — while three more poke one into 0x32's and 0x7f's and require the record to stay untouched. `test_anim_table_is_fully_reconstructed` asserts every one of the shipped table's 23 entries maps to a C handler |
| `0x1494a` | `enemy_move_type14_sine` | 84 | ✅ verified | twelve x values around the 4-pixel step's own despawn edge (a different edge from the two 2-pixel movers'), against the seeded squadron-counter band that proves the open-coded despawn credits its squadron; nineteen phases covering every quadrant boundary of the sine fold, the phase step's 360-degree wrap and both ends of the word — 0x7fff and 0x8000 pin the wrap's SIGNED compare; six base-y values through the word's wrap; 200-case fuzz; poison |
| `0x14d14` | `actor_script_op_bounce_fall` | 116 | ✅ verified | the terrain test driven at five entity indices with ONLY that record's pixel-hit flag set, so a wrong `(a2 - table) / 0x2c` quotient answers "no hit"; both collidable and inert types; a chain-walk that DENIES the hit through a lower-indexed overlap; four values of the bounce flag through both arms; a 9 x 6 y/dy grid across the floor at 0xa0 (which the accel has already stepped past by the time the clamp runs); six acceleration words; 120-case fuzz; poison on both arms. The vertical step lands TWICE per call — `entity_apply_accel` falls into `entity_apply_velocity` and the tail adds dy again — and the fixed-point shift mutation is what holds that |
| `0x14da2` | `actor_script_op_set_heading` | 30 | ✅ verified | all 256 opcode bytes sharded four ways, which is what separates its `lsr.b #1` from the `lsr.b #3` its five sibling operand classes use (the two agree only at operand 0); eight speed bytes through the `ext.w` that makes 0x80..0xff steer the other way; five opcodes with both position longwords noise, so the fall through 0x142d4 into 0x14306 is attributed |
| `0x14de2` | `actor_script_op_random_heading` | 30 | ✅ verified | six generator states including the one the binary ships, the LFSR's 0 fixed point and the tap mask itself — the state is this opcode's whole input AND an output, since rand16 writes it back; the same eight signed speeds; poison |
| `0x14e1c` | `actor_script_op_thrust_to_centre_y` | 28 | ✅ verified | seven y values either side of the 0x60 centre line including 0x8000 and 0xffff, which hold `blt` against `blo`; six acceleration words through the velocity's wrap, so the fall is the RECORD's field and not a literal. No `fn` line in `../names.txt` — the name here is this reconstruction's |
| `0x14e38` | `actor_script_op_aim_at_player` | 24 | ✅ verified | fourteen relative positions round angle_to_target's octant fold, including the origin and the one-pixel neighbourhood; eight signed speeds. It neither STORES the heading it computed nor integrates the velocity it set, and the noise-seeded record is what makes both absences a diff |
| `0x14e5c` | `actor_script_op_thrust_to_centre` | 48 | ✅ verified | a 7 x 2 grid of x edges against both y arms, so every case drives one axis's arm against the other's — a candidate that dropped the `or.w` accelerates on one axis only; six acceleration words on each x arm; poison |
| `0x14e8c` | `actor_script_op_random_speed_nudge` | 44 | ✅ verified | fourteen draw bytes at every boundary of the two SIGNED compares, each against eight speeds, with the generator state chosen so the draw is the one the case names. THE EARLY RETURN'S CARRY IS THE FIRST COMPARE'S OWN and `cmp.b` sets it UNSIGNED, so a draw below 0x55 answers "continue" and one of 0x80 or more answers "frame over" out of the same `rts`; both are compared through the flag byte. The "+1" arm is UNREACHABLE and `test_op_random_speed_nudge_never_draws_the_increment` is the assertion that says so |
| `0x14eb8` | `actor_script_continue` | 6 | ✅ verified | the flag byte under a canary that is neither answer, over a noise record the six bytes must not touch. It is also ext 11's tail, so the battery above drives it a second time |
| `0x14ebe` | `actor_script_op_end_frame` | 6 | ✅ verified | its mirror, the same case the other way round |
| `0x1544e` | `explosion_animate_all` | 194 | ✅ verified | twelve particle-frame values against three group masks — the retiring edge, and the two that make `add.b #1` wrap into an arm of its own (0xff steps to 0, 0x7f to 0x80, and each SKIPS the sprite while still storing the stepped counter); six toggle values through a `not.b` gate whose branch is the OPPOSITE way round from asteroids_animate's; seven active-bit patterns, including the ones that arm the routine without animating anything and so isolate the two CLEARS that sit before group 1's own `btst`; two disjoint member lists, which is what pins the six-byte cursor step; 40-case fuzz; poison |
| `0x15510` | `explosion_spawn` | 114 | ✅ verified | ten source x values including three odd ones, which hold `and.w #$fffc` against a shift, and six y values that show only x is aligned; a hand-built offsets table read as dx/dy/frame triples; six starting values of the active-bits byte, so the `bset`'s read-modify-write is held; 40-case fuzz over random offset tables. THE OFFSETS ARE CUMULATIVE — each particle adds to the running position rather than to the source's own — and the mutation that applies them to the source instead is killed on every case but the first particle |
| `0x141c2` | `entity_ptr_from_index_d6` | 20 | ✅ verified | the SECOND ENTRY of 0x141c0, and it has no core of its own: the two entries share one body and differ only in which register the index arrives in, so the C is `entity_ptr_from_index` and this is one more glue. All 256 indices sharded four ways through `g_entity_ptr_from_index_d6`, with junk in the D0 this entry does not read; four whole 32-bit registers whose low byte is the index, under poison. Its landing means `entity_record` (include/collision.h) and `entity_from_index` (src/weapon.c) are now the same arithmetic written twice more — see the note below |
| `0x13ad0` | `enemy_morph_to_type6` | 34 | ✅ verified | nine y values through `subi.w #$2` on a WORD — 0 and 1 wrap round the bottom rather than clamping and 0x8000 wraps the sign the other way; the record is noise everywhere else, so a sixth store differs; poison. The sprite immediate is a RELOCATED longword and `test_morph_to_type6_sprite_is_the_relocated_address` reads it back off the routine's own instruction rather than trusting the header |
| `0x14d88` | `actor_script_op_fire` | 26 | ✅ verified | all 256 opcode bytes sharded four ways, which separates `(opcode & 0x78) >> 3` from the `>> 1` its sibling class uses and from the whole byte; five turn countdowns, so the two stores are seen to happen whatever the steer then does with them — 1 expires and turns while 0 wraps to 0xff and only ticks; the record sits at a REAL entity slot so `entity_steer_toward_target`'s index arithmetic lands in the table it names; poison. `test_op_fire_target_is_the_player_slot` is what says the literal 0x11 is an entity INDEX and which record it reaches |
| `0x14cce` | `actor_script_op_ext` | 26 | ✅ verified | all sixteen opcode bytes of each of the twelve live operands (192 cases, sharded) — every one of the class bits and bit 7 driven, which is what `(opcode & 0x78) >> 3` is the only spelling of; a REAL handler poked into a NULL slot, which separates "reads the table" from "switches on the operand"; poison. **ENTRY 8's CARRY IS DRIVEN AT LAST** — `test_ext_entry_8_answers_carry_clear` is the surface the weapon section's first residual asked for. The four NULL operands are undrivable and `test_ext_table_nulls_are_the_operands_no_case_drives` states that rather than leaving them looking untested |
| `0x14c66` | `actor_script_run` | 104 | ✅ verified | the delay tick's three arms at eight values — 1 fetches, 2/3/0x7f/0xff only tick, 0 wraps to 0xff and is PUT BACK (so a stalled actor re-runs its opcode for ever rather than counting through the byte), and 0x80/0x81 are the other side of the `bpl`; a run of delay bytes before the opcode, where the LAST one survives; the bounce latch cleared on a fetch and left on a tick; a signed pc of 0xfff0, sixteen bytes BELOW the script base; the `bcs` loop driven one and two opcodes deep, which is what says it re-enters at the routine's HEAD and re-ticks; and all eighteen SHIPPED scripts run from their own first byte. Poison |
| `0x14c16` | `enemy_move_scripted` | 46 | ✅ verified | eleven x values through both bounds one step either side, each against both values of the boss flag — the compares are SIGNED, so 0x8000 and 0xffff despawn where an unsigned reading would keep them, and the flag SKIPS the band test rather than being one more term of it; the despawn arm at every one of the six squadrons over a seeded counter band; five y values that show the clamp ran after the script. Poison |
| `0x1487c` | `enemies_move_all` | 76 | ✅ verified | one record of each of the six moved types in a single pass AND the same set rotated one slot on, which separates "dispatched by type" from "dispatched by position"; each type in all eleven slots; dead records skipped; 60-case attribution. IT DISPATCHES THROUGH THE ANIMATION MAP TOO — the two tables share storage (`test_the_two_tables_share_storage`) and this pass's guard reaches into the second, so three types past its own table are driven and must run an ANIMATION handler on both sides. `test_move_table_is_fully_reconstructed` covers every one of the 23 in-range entries; the boundary that is left is 0x2e..0x31, and it has its own note below |
| `0x11a2c` | `spawn_enemy_shot` | 400 | ✅ verified | the three launch arms and every gate in front of them: eight enemy x values through a SIGNED `cmpi.w #$50`; four kind bytes, since `tst.b` picks the seeker arm on any non-zero one; the flag bit and the class map driven INDEPENDENTLY, so neither stands in for the other; the halved chance at 0x31/0x32/0x33 with the generator state SEARCHED for rather than sampled, and against the same case with the bit clear; the seeker's cooldown over four values, which shows the reload happens BEFORE the position test; six ship/enemy x pairs through a SIGNED inclusive `ble`; seven player y values through the aim lead, which is raised and put back so a candidate forgetting either half aims elsewhere AND leaves the ship's record moved; 160-case sharded fuzz; poison on all three arms |
| `0x11bde` | `enemy_shot_tick_type0a` | 34 | ✅ verified | seven time-to-live bytes: only 1 expires, 0 WRAPS to 0xff and flies on (which separates the expiry from a `<= 0` test) and 0x80 is the other side of the sign; both of the steer's own countdown arms; six target indices from 0 to 0xff, so a wrong record stride lands on a different record; poison |
| `0x11bbc` | `enemy_shot_tick_type0b` | 34 | ✅ verified | the same battery against the twin, and the ONE difference driven side by side: this one MORPHS on expiry where 0x11bde only clears the alive byte |
| `0x11906` | `enemy_fire_and_update_shots` | 294 | ✅ verified | the chance table's index driven with four different HIGH BYTES over a seeded band either side of the table — the section is loaded with `move.b` and indexed with `d1.w` on the next instruction, so a candidate spelling that as an `ext.w` reads a different chance and fires where the original does not; the boss flag against four flag bytes, which is what says the encounter bypasses BOTH the flags and the chance; the two class maps choosing the kind; five alive bytes through `tst.b` + `btst #7`; four shot-slot vectors, so the launch scan's "first free" and its "none free" arm are both driven; the tick pass with all three kinds present and rotated; 120-case sharded fuzz over random states, sections and registers; poison. `test_fire_chance_compare_is_inclusive` drives the compare's EQUALITY from a searched state — the sweep's one survivor, now dead |
| `0x13898` | `wavescript_spawn_trio_type0e` | 192 | ✅ verified | the free-slot gate at every count from 0 to 8, which pins it against `> 4` and `!= 0` and says it reads the byte the routine JUST PUBLISHED rather than a register; the squadron scan at each of the six positions and with every one taken; three shapes of "exactly four free", so the fourth free record must come back untouched and the count of three is held; five generator states through the random y spacing; poison |
| `0x13958` | `groundscript_spawn_type10` | 186 | ✅ verified | **THE FREE-SLOT GUARD IS NOT ONE, and this battery is what says so.** `bsr count_free_wave_slots` + `beq` reads as "return when nothing is free", but that routine ends `movea.l (a7)+,a0 / move.l (a7)+,d7 / rts` and it is the last MOVE that sets the flags — so the branch tests the RESTORED D7, whose low word this routine has just loaded with the scripted y plus 0x20. Three cases separate the two readings: the only y that makes the whole longword zero, the same y with a non-zero high word, and an ordinary y with no free slot at all. Plus seven scripted y values through the WORD add's wrap, three free-slot shapes showing exactly one actor is placed, the squadron scan, and four generator states through the redraw-until-non-zero tail; poison |
| `0x13a12` | `groundscript_spawn_type0f` | 190 | ✅ verified | the same battery against the twin, driven from the same parametrised cases — the two differ in the actor type and in the extra `clr.b` this one makes, which is ACTOR_DIVING, so a fresh type-0x0f is spawned with its dive unarmed |
| `0x13af2` | `squadron_spawn_tick` | 208 | ✅ verified | the enable byte over four values and the countdown over four, which is what says the decrement is STORED before it is tested and that 0 wraps to 0xff without firing; one free group at each of the six positions, pinning the 0x84 group stride; three partial groups, which pin the `or.b` over all three columns; the no-free-group path, which must still reload; five generator states through the two flags, whose senses are OPPOSITE (`< 4` for one, `>= 4` for the other); poison. The three addresses names.txt reaches at 0x13b56 / 0x13b72 / 0x13bae are `bra` targets inside this body, not helpers — nothing calls them |
| `0x14a7c` | `spawn_formation` | 356 | ✅ verified | every one of the eighteen SHIPPED formations; the allocator's stop at every free count from 0 to 8; both early returns; the squadron claimed at each of the six positions, whose counter is then stepped once per actor; a 5 x 5 grid of base x and base y across the word, both wrapping; and the three arms the game's own data cannot reach, each driven from a poked record and each stated as poked by an assertion over the shipped table — the kind in byte 3, the 0xff random-row marker, and a count of ZERO, which walks the whole word until the allocator refuses. `test_formation_x_offset_is_signed_and_y_is_not` is the one case that separates the two axes' readings; 120-case sharded fuzz; poison over two formations |
| `0x13868` | `wavescript_spawn_wave` | 48 | ✅ verified | all sixteen formations its opcode nibble can name; the four combinations of bits 4 and 5, which is what pins the NESTED test — bit 5 alone leaves the flags at zero where two independent tests would not; seven base-y values through `and.w #$ff`; the cursor republished with every slot taken, so nothing else happens at all; poison. The `rts` at 0x13896 sits past its `bra.w` and is unreachable |
| `0x159be` | `asteroids_draw` | 52 | ✅ verified | all eighteen records live at once, marching diagonally across the playfield through all eight x sub-cell phases so no two blits coincide; a mixed alive vector; a nineteenth live record that must stay undrawn, which pins 6 x 3 against the boss records that follow; poison. D2 is DERIVED as half a preshift frame and `test_asteroid_draw_phase_step_is_half_a_frame` reads the routine's own immediate back out of the image to confirm it |
| `0x15a6a` | `asteroids_animate` | 100 | ✅ verified | the half-rate gate at four toggle values — `not.b` flips AND tests, so the flip must happen on the blocked call too; eight frame bytes through the six-frame cycle and its signed wrap; the column offset advancing over a DEAD record, which is what pins it as positional rather than as a running total; 40-case fuzz; poison |

### `enemies_animate_all`'s unreconstructed edge

THE DISPATCHER READS ITS JUMP TARGET OUT OF THE IMAGE and maps the address back to a C function
(`src/enemy.c`, `ACTOR_ANIM_HANDLERS`). For an address the map does not hold it returns without
calling anything, and that arm is REACHABLE rather than defensive: the routine's own guard is a
SIGNED `cmpi.b #$32` on the type byte, while the animation table at 0x193dc holds only 23 entries —
it ends where the script class table at 0x19438 begins. A type of 0x17..0x31, or any negative one,
passes the guard and reads a longword from past the table.

**WHAT LIES PAST THE TABLE IS NOT JUNK, and an earlier draft of this section said it was.** Types
23..46 land inside the two script-VM jump tables, which hold real in-image code addresses: 23 is
`entity_apply_accel`, 26 `actor_script_op_bounce_fall`, 39 `entity_steer_toward_target`, and so on
through 46 — nineteen live entry points, four NULL longwords, and only 47..49 are data words
(47..49 read 0x400040 / 0x880000 / 0xb00028, the last of which would enter the 68000 vector page).
So the original really would call a SCRIPT handler from the ANIMATION pass, with A2 on the record
and D1 holding the type's byte offset rather than an opcode, and the reconstruction would return
having done nothing. That is a genuine divergence, not an impossible one.

It is left unmodelled and stated rather than pinned, because pinning it means giving
`ACTOR_ANIM_HANDLERS` entries of a second shape (the script ops answer in the carry and two of them
read D1) for a path the game's own data does not take: the naming pass records actor types 0x02,
0x06, 0x0b..0x11, 0x14 and 0x16 in these slots, and 0x32 upward for the player's own entities, with
nothing in 0x17..0x31. That is an absence in the recovered names, not a proof, and it is written
here rather than asserted in code for exactly that reason.

`test_the_types_past_the_table_are_this_batchs_boundary` is the assertion that keeps the boundary
where this paragraph says it is: it fails if a slot past the table ever becomes one the map holds.
The lookup ITSELF is verified past the table's end —
`test_animate_all_reads_its_handler_out_of_the_table` pokes a real handler into the slot a type of
0x31, 0x80 or 0xff reaches and requires both sides to run it — and
`test_anim_table_is_fully_reconstructed` covers every one of the 23 in-range entries.

### `enemies_move_all`'s unreconstructed edge, and why it is NARROWER than its twin's

The move pass reads its handler out of A_actor_move_table exactly as the animation pass reads its
own, and its guard is the same SIGNED `cmpi.b #$32`. But the two tables SHARE STORAGE — the
animation table IS the move table's 24th longword (0x19380 + 0x17 * 4 == 0x193dc), which
`test_the_two_tables_share_storage` asserts every run — so a move type of 0x17..0x2d takes its
target from the ANIMATION table, and nine of those slots hold animation handlers.

**Those nine are MODELLED rather than stated**, unlike the animation pass's own edge, and the reason
is the shape of the callee: an animation handler takes exactly the arguments a move handler does
(the record in A2, no opcode, no flag), so running one from this pass costs a second entry in the
map and nothing else. `src/enemy.c`'s MOVE_PASS_MAPS is that second map, and
`test_move_all_runs_the_animation_handler_past_its_own_table` drives three of the nine.

What is left is types 0x2e..0x31, which reach past BOTH tables into the script class table at
0x19438. Those handlers answer in the CARRY and two of them read the opcode in D1, so they cannot be
called from a pass that has neither — the same argument the animation section above makes about its
own boundary. `test_the_types_past_both_tables_are_this_batchs_boundary` fails the day one of those
four slots becomes an address either map holds.

### Three pieces of the original this batch did NOT transcribe

| where | what | why |
|---|---|---|
| `enemy_fire_and_update_shots` @ 0x119ba..0x119d8 | eleven instructions writing a second shape of shot record (a word at +0x10, the position pair, the alive byte, and D2 masked with 0x7ff into +0x1a) | **DEAD CODE.** They sit past an unconditional `bra` at 0x119b6 and nothing anywhere branches to them — `grep` over the whole listing finds no reference to 0x119ba. Left out rather than transcribed, on the same terms as 0x148ca |
| `wavescript_spawn_wave` @ 0x13896 | one `rts` | unreachable: 0x13892 is `bra.w $14a7c`, a tail call |
| `spawn_enemy_shot` @ 0x11bb4 | `movea.l a0,a1` before the seeker's `bsr` to `entity_set_velocity_from_angle` | the callee reads no A1, so the copy is dead. There is nothing to write in C but the comment that says so |

### The one input `spawn_formation` cannot be driven over

A formation index outside the shipped eighteen resolves a POINTER out of the table, and past the
eighteenth entry those longwords are data (0x580054 and up) — addresses outside the 1 MiB image. The
oracle bounds such a read and the candidate faults, so no differential can compare the two sides
there, and `make guarded` is the surface that says so rather than a case. The bound is stated by
`test_the_formation_tables_shipped_extent`, which reads the pointer one past the end back off the
image and asserts it does NOT address the data block. Every caller passes an index the game's own
tables produce: the wave script masks its opcode with 0x0f, and the boss's byte is 0x0b..0x11.

### The entity index -> record multiply is now written THREE times

`0x141c2`'s row in "Not reconstructed" used to carry this debt, with "when 0x141c2 lands,
`entity_from_index` is the one site to swap" as its trigger. The trigger has fired and the swap is
NOT this batch's to make, so the row moves here rather than disappearing with it:

| where | what it is |
|---|---|
| `entity_ptr_from_index` (src/enemy.c) | `A_entity_table + (index & 0xff) * ENTITY_STRIDE` — 0x141c0's own body, and both entry points' |
| `entity_record` (include/collision.h) | the same multiply without the mask; **`mothership_segment_hit` now calls it**, which is the first site this batch could convert |
| `entity_from_index` (src/weapon.c) | the mask, over `entity_record` |

The merge is `entity_from_index` becoming `entity_ptr_from_index` and `entity_record` becoming its
unmasked half — two edits in files this batch does not own (`src/weapon.c`, `include/collision.h`),
which is why it is a row and not a diff. Three other surfaces still say 0x141c2 is unported and are
the same owners' to correct: this file's weapon section, `src/weapon.c`'s "One thing this batch
names rather than ports", and `include/collision.h`'s note on `entity_record`.

### Two duplications this batch left in place, and why

Both were found by the review gate and both are real; neither is merged here because the merge
would edit a file this agent does not own (README.md's ownership table).

| what is duplicated | where | the merge, and whose it is |
|---|---|---|
| the one-axis fixed-point position step (`velocity` sign-extended, shifted 8, added to a longword field) | `src/enemy.c`'s `step_position_by_velocity`, and TWICE more inside `src/util.c`'s `entity_apply_velocity`, once per axis with the shift as a bare `8` | hoist the helper into `include/util.h` and let `entity_apply_velocity` call it twice. **util's owner.** This copy is the only one that names the fraction width |
| the flag stub's `jsr / movea.l #result,a0 / Scc / rts` skeleton | `test/abi.py`'s `register_call_eq_flag_pokes` and the appended `flag_call_self_addressed_pokes` | a `condition` parameter on the first, and the second deleted. **abi.py is append-only** while several agents hold it, so an edit to an existing body would conflict with every concurrent append |
| the masked-sprite draw staging: a 32 KB scratch sprite arena, a seeded back buffer, `A_screen_back` pointed at it, a record built over it, and a "D2 is half a preshift frame" pin | `test/test_enemy.py` (asteroids_draw), `test/test_mothership.py` (mothership_draw) and — first, and not this batch's — `test/test_sprite.py` (draw_sprite_masked) | one builder in `test/abi.py`, which already owns the scratch map and the framebuffer addresses. **Three batteries, three owners**; doing it from one of them would edit the other two |

## Verified — mothership (9)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x14f18` | `mothership_place_tail` | 76 | ✅ verified | eight anchor x values including two that make the WORD step wrap across the five segments, and six anchor y values; a sixth seeded record past the five, which pins the loop count against the shift-mask table that follows; poison, so every one of the five fields written per segment is attributed |
| `0x14eda` | `mothership_begin` | 62 | ✅ verified | the arming gate at every free-slot count from 0 to 8, not just at 7 and 8 — the count comes back in a register the gate compares for EQUALITY, so a candidate testing `>= 8` or `!= 0` agrees on some of these and not others; four non-zero alive bytes through `tst.b`; seven section bytes through an index that is SIGN-extended into a seeded band while the energy byte it reaches is read UNSIGNED into a word; 40-case fuzz. It has no `rts`: canaries on both anchor words and on the prep-stage byte are what say the FALL-THROUGH into mothership_place_tail ran |
| `0x14f64` | `mothership_spawn_head` | 100 | ✅ verified | all sixteen level sections, each naming its own formation, its own fire-flags byte and — through the formation — its own base y, so a candidate reading either table with the wrong index or skipping the base-y table's doubling spawns the boss somewhere else; a third live record behind the two, which a fixup loop one pass too long would overwrite; poison. The whole preshift bank is seeded and the encounter's three flags are seeded to values that are neither what the routine writes nor what the image holds, so the two CLEARS are visible |
| `0x14fc8` | `mothership_move_and_place` | 130 | ✅ verified | five explosion-bit patterns, which say only bit 0 stands the routine down and the ship's own blast does not; nine x values on the first record and again on the second, through a SIGNED `bmi` on the left and a SIGNED `cmpi.w #$1b8` on the right; three starting values of the offscreen flag, which is cleared at the top and set only by a record that is outside; three head layouts far apart, which say the tail's anchor is the FIRST record's position and not the second's; poison |
| `0x151ba` | `mothership_segments_update` | 104 | ✅ verified | one live segment at each of the four PAIR positions, which pins the 0x58 stride against the 0x2c one — a candidate striding by a record would run the shadows as segments; six type bytes through an EQUALITY guard, which is what keeps this pass off the head records the same array holds; four alive bytes; ten x values through both bounds one step either side, where the kill takes BOTH records and the shadow's position has already been written by then; poison |
| `0x1504a` | `mothership_segments_respawn` | 222 | ✅ verified | the gate at every free count from 0 to 8, which is an EQUALITY on eight and so separates it from `>= 8` and `!= 0`; all sixteen sections through the formation, fire-flags and energy tables; five energy bytes; poison. `test_segments_respawn_energy_bytes_are_the_pairs_own` derives the four bytes it writes from the entity index of the first wave slot and asserts they are exactly the ones `mothership_segment_hit` decrements — which is what makes the two routines one encounter rather than two |
| `0x15222` | `mothership_segment_hit` | 130 | ✅ verified | all eight boss slots against three energy values, over a counter array seeded UNIFORMLY so what tells the pairs apart is which byte moved — that is what pins the `((i - 1) & ~1) + 1` fold, with 9 and 10 both costing pair 9 its energy; the explosion driven from four of the eight slots under poison, so each of its eight stores is attributable and the 4-pixel x alignment is held on BOTH halves; two starting scores, one of which makes every digit of the `abcd` award carry, so a binary add would agree on neither |
| `0x158f4` | `mothership_draw` | 44 | ✅ verified | all five segments live through eight x phases and four y bands; each of the five dead in turn; a sixth live record that must stay undrawn — the segments are contiguous with the shift-mask table, so a pass too far reads a record made of table bytes; poison. D2 is derived as half the boss frame and the case reads the routine's own immediate back to confirm it |
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

The mutation ledger for these rows is in `## Mutation ledger` below, under "enemy and
mothership" — one sweep, one baseline, one
set of numbers, because both subsystems are rebuilt into the same `.so` and a split count would be
two ways of saying the same run.

### `mothership_segment_hit`'s divide carries TWO residuals, not one

The 32-bit `(segment - A_entity_table) / ENTITY_STRIDE` costs an on-target `__udivsi3` the
original's one `divu.w #$2c` does not — the same trade `bomb_collision_row` makes in `src/weapon.c`,
for the same reason, and the surface that would catch it is a per-frame profile rather than
`make test`.

THE SECOND IS A BEHAVIOURAL DIVERGENCE and it is stated rather than modelled. `divu.w` leaves its
destination UNCHANGED (and sets V) when the quotient will not fit in sixteen bits, so a record
BELOW the table — a difference of 0xffffffxx, a quotient of about 0x5d17_0000 — leaves the original
folding the raw difference's low word where this C folds the truncated quotient. Both callers hand
the routine one of entity slots 9..16, all of them above the table, so nothing the game can do
reaches it; `src/mothership.c` carries the same note at the routine.

### The boss borrows the WAVE slots, and three routines read them differently

`include/mothership.h`'s "THE BOSS'S OWN SLOTS" is the one home for the layout: the encounter has
no records of its own, and the eight wave records at `A_enemy_slots` are the head (the first two)
and four segment PAIRS (an even record the script moves, an odd one placed to its right). That is
why `mothership_segments_update` and `mothership_segments_respawn` stride 0x58 where
`mothership_move_and_place` strides 0x2c, and why the respawn marks the ODD slots alive before it
spawns — so `spawn_formation` fills only the even ones. The ninth record every battery seeds behind
the eight is the SHIP's own (`A_enemy_slots + 8 * 0x2c == A_player_record`), which is what makes
the guard mean something rather than merely being spare memory.

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

## Verified — sprite (9)

**One routine of this subsystem has no row and cannot have one.** `asteroid_sprite_expand`
(`src/sprite.c`) is the loop nest at 0x156e2..0x15718 INSIDE `asteroids_load_and_build` — a name this
reconstruction coined, with no `fn` line and no entry address of its own — so it is verified only
through its caller's row in `## Verified — fileio`, six times per run. It lives here rather than in
`src/fileio.c` because it is the same transform `mothership_sprite_expand` @ 0x157ca is, two cells
narrower; the two now share one body (`expand_masked_sprite_frames`), which is what keeps the boss
expander's own row honest about what it still covers.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13bde` | `ship_sprite_deinterleave` | 26 | ✅ verified | disjoint, in-place (`A0 == A1`, which the seventh call site at 0x10132 does) and seven overlap offsets at row and word granularity — the read/store ORDERING is held by the overlap cases and by nothing else (measured: reversing the two half-row copies passes the in-place case and fails at +2/+10/+200/-1600); poison on the disjoint and the in-place shapes. Every byte of both destination frames is seeded with noise, so a candidate writing too few rows differs |
| `0x153f6` | `sprite_preshift8_2px` | 42 | ✅ verified | all six shipped widths (0x1e/0x50/0x5a/0x6e/0xa0/0xc8 — 0x1e and 0x6e reach it only through the tail `bsr` at 0x153e6 inside `sprite_bank_build_preshift8`) in place, six widths disjoint down to the 2-byte minimum, `frame_bytes` 0 for the `dbf` wrap (65536 rows, in-image because the slot step is then 0), four source/destination overlaps that put the source inside a written slot — which is what holds the read/store ORDER, measured — hi-garbage in D2's high half, 240-case sharded fuzz shared with the 4-px twin; the end pointer compared against the oracle's A1 on every case; poison in place and disjoint. The whole 8-slot bank is seeded, so a candidate writing an extra slot differs |
| `0x153c0` | `sprite_bank_build_preshift8` | 52 | ✅ verified | **all eight call sites, each over its own graphic file at its own bank address**, in place as `_start` runs it — SPINNERS/SEEKER2/ALTEXPL/ALSEEK/NEWBULS2/GEMGRAF/ALIENA/ALIENB.DAT, whose lengths are themselves the pin on the pair of counts beside each `bsr` (frames x frame_bytes is exactly the file, asserted per case). Three of them again disjoint (`src != dst`), which no call site does and which is what says A0 and A1 are separate cursors; noise at 1, 2 and 8 frames; a 40-case sharded fuzz over widths the game does not ship, odd ones included (both passes discard the odd byte, `lsr.l` then `lsr.w`); poison, which separates the copy pass's slot 0 from the preshift pass's slots 1..7. The whole bank is seeded every case, so a candidate spreading the frames the wrong distance apart leaves a seeded byte standing. Mutations killed: the 8-slot bank stride, the preshift pass one bank short |
| `0x15420` | `sprite_preshift4_4px` | 46 | ✅ verified | same battery as the 2-px entry above. Seeding the slots it does NOT write (1, 3, 5, 7) is what makes the case a test at all — left as zeroes, a candidate that wrote all seven would pass |
| `0x15758` | `asteroid_preshift_bank` | 114 | ✅ verified | all SIX shipped banks (0x1a8ae..0x23eae), each holding the bank the builder at 0x156ac would really have left there — rebuilt in the test from BIGAST.DAT's own bytes, two cells per row and a transparent third. Real data is what makes the MASK column's carry-in visible for what it is rather than as an arbitrary bit. Plus noise over a whole bank (there is no data-dependent branch, so noise separates the five word columns and the three cells better than a sprite does), a bank that is none of the six (so the base comes from A0), and poison. Mutations killed: the mask carry-in dropped, the 2-pixel pass step, the cell count |
| `0x157ca` | `mothership_sprite_expand` | 110 | ✅ verified | its two ADDRESSES come from `include/mothership.h`, which owns the boss's data — this row's geometry constants are spelt `BOSS_SPRITE_*` and not `MOTHERSHIP_*` on purpose, because that header reads the same store at a different granularity (its `MOTHERSHIP_FRAME_BYTES` is 0xa0, one frame of the rotate banks its own routines build; the expander's frame is the five-cell 2000-byte one). Two verified readings of one buffer, so two names. Verified over all five boss sprites the disk ships (MOTHER1..5.DAT), whose 1600-byte length is itself the pin on the geometry — 40 rows of four 10-byte masked cells; noise in their place, which is what separates the four source cells from one another (a real sprite is symmetric enough that a transposed cell could still match); poison, which is what holds the synthesised fifth cell, whose four zero planes are otherwise indistinguishable from nothing written. Mutations killed: the source cell count, the blank cell's mask word |
| `0x15838` | `mothership_sprite_preshift` | 188 | ✅ verified | `asteroid_preshift_bank` one geometry wider — five cells 400 bytes apart, 40 rows, a 2000-byte frame stride — so the two share `shift_masked_frame_right_1px` and differ only in four numbers. Verified over all five boss sprites the disk ships, each in the bank `mothership_sprite_expand` would really have left (rebuilt in the test from MOTHER*.DAT's own bytes rather than by running the expander, so this case does not lean on that reconstruction); noise over a whole bank; poison, which holds frame 7's fourteenth pass. **The four ENCOUNTER FLAGS it arms on the way out are seeded non-zero in every case**, because two of them are `clr`s over bss and would otherwise write zeroes over zeroes and differ nowhere; a separate case reads all four back out of the oracle's own final image so a failure names the flag rather than an address inside a 16 KB bank. Mutations killed: one cell short of the five, the prep-stage clear dropped |
| `0x15ace` | `draw_sprite_masked` | 174 | ✅ verified | all eight even sub-cell phases at BOTH shipped D2 values (0x3e8 and 0x1e0 — half a mothership frame and half an asteroid frame, which is what makes `mulu.w d2,d0` land on the right slot); six x positions across the row; both x rejections and both y rejections one step either side of their edges, odd values included because `and.w #$fffe` runs before the tests; the top clip at one row visible, half and all but one; the bottom clip at four depths including the tallest sprite that needs none; the two clip arms' shared boundary; 200-case sharded fuzz over the whole coordinate box; poison. Twelve mutations, ALL KILLED (below) |
| `0x15b7c` | `draw_sprite_masked_collide` | 450 | ✅ verified | the sibling blitter, and three things separate it: it spans TWO cells (the preshift banks are rotated, so `shift_mask_table` at 0x1821e re-splits each word — the table is pinned against the binary's own bytes as `0xffff >> s` doubled, which is the claim the C makes about it), its coordinates are the WORLD's (x 0x40 is column 0, so the rejections are at 0x30 and 0x180), and it REPORTS a pixel hit into a byte the caller names in A5. Verified over: all eight even phases; six x across the row; the two partial bands either side, three x each — the left one drawing the complement half into column 0 with no offset at all, the right one a fixed `lea 152`; both x rejections at their exact edges plus four values past them; both y rejections and both clips at the same edges as 0x15ace's; the two clip arms' shared boundary at an oversize height; the height's bit 15 SET, which this routine masks off (`and.w #$7fff`) where its sibling does not; 200-case sharded fuzz; poison; and both A5 shapes, the record's own ENTITY_PIXEL_HIT byte (0x11c48) and a byte outside it (0x13096). **THE FLAG'S THREE OUTCOMES ARE EACH THEIR OWN CASE**, because a noise screen makes every case hit and nothing would then separate the readings: a transparent sprite sets nothing; an opaque one over a background with planes 0 and 1 set and 2 and 3 clear sets nothing (this is what says the test reads the terrain planes and not "any pixel"); the same sprite over plane 2 sets it. A fourth puts terrain in the SECOND cell only, at three phases, so the near test misses and the far one has to fire — the only shape that can tell the two apart, both storing the same 0xff. Mutations killed: the collision reading planes 0+1, the far-cell test removed, the right band one cell early, the height mask dropped, the left band keeping the near half |

## Verified — scroll (25)

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
| `0x162c2` | `scroll_emit_tile_column` | 1840 | ✅ verified | the step ahead of the two emitters: eighteen tile rows of eight pixel rows each, every row written three times over — the screen's right-edge column, the page's column, and the workspace, where each longword is `this column's tile word : the NEXT column's`. 1,840 bytes because the eight-row body is written out FOUR times, once per (near flipped, far flipped) pair; the arms differ only in each cursor's start and step, so the reconstruction reads the direction out of a two-field struct. Verified over **all twelve levels**, each unpacked by running the ORIGINAL'S OWN `map_rle_decompress` (not a second unpacker here) and decoded against the smallest ZYN*.DAT that covers its indexes — a pairing the test derives from the data and which comes out EXACT for three levels (LEV1 needs 39,488 bytes and ZYN1.DAT is 39,488; LEV3/ZYN3 35,648; LEVZ/ZYN8 32,128). Each level runs at a column whose own eighteen rows reach all four arms, and a separate case asserts such a column exists in every level, so "all four arms" is a property of the shipped maps rather than of a column the battery picked. Plus seven columns across LEV1; both destinations real (`screen_back + 152` and a `map_page_table` page at three phases) and a third framebuffer that is neither; all three values of `scroll_prefill_hide_screen`; the last column, whose peek reads the 720-byte bss gap past the map; a 48-case sharded fuzz over levels and columns; poison, which is what holds the workspace's low words. A6 is compared against the oracle's own on every case and asserted to be exactly one column on. Mutations killed: the 64-byte tile scale, the peek one row off, the vertical flip ignored, the workspace halves swapped, the flipped index unmasked, the redirect inverted, seven pixel rows, the returned cursor short |
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
| `0x1297a` | `screen_flip_buffers` | 48 | ✅ verified | the pointer swap is diffed byte for byte over four buffer pairs, two of them arbitrary longwords (the routine never dereferences either pointer, so any word is a legal input and that is what pins the byte extraction over the whole range). The $ff8203/$ff8201 publish is OFF-IMAGE and is held by the kit's hardware write ledger, which compares the two byte stores' addresses, widths, values and ORDER against the oracle's (`tools/recreate_kit/TRAP_MODEL.md`, "Phase 10"); the case also names the two stores the oracle made, so the test says which registers the routine reaches rather than only that both sides agreed. **NO RESIDUAL LEFT HERE** — the earlier row's "that the bytes reach the shifter at all is unpinned" is retracted. Mutation killed: the two base bytes stored in the wrong order |
| `0x12fc2` | `clear_backdrop_page0` | 18 | ✅ verified | one playfield's worth at the fixed page, noise + guard bands, poison. The address is an immediate in the routine, so the only thing a case can vary is what was there before. Mutation killed: the page address moved 4 bytes |
| `0x134b8` | `blit_graphic_block` | 18 | ✅ verified | both shipped heights (D0 = 0x3f and 0x17), the one-row minimum — the count is a `dbf` register, so 0 must copy ONE row — hi-garbage above the word, six source/destination overlaps at row and word granularity, and poison. **The overlaps are what caught a real defect**: a `movem` pair reads a whole row before storing any of it, and an interleaved reconstruction read back its own stores from the third longword on at dst = src + 2. Mutation killed: the 32-byte row width |
| `0x1597c` | `playfield_clear` | 66 | ✅ verified | the top 144 rows of whichever buffer `screen_back` names — both framebuffers and a third — noise + guard bands, poison. Mutation killed: the start moved one longword |
| `0x153ae` | `set_palette_title` | 18 | ✅ verified | the routine writes NO image byte — its whole effect is sixteen colour registers at $ff8240 — so the ENTIRE verification is the kit's hardware write ledger, which compares each store's address, width, value and position in the stream. The case needs no stub and no result slot: it enters at 0x153ae and runs to its `rts`. Driven on the palette the binary ships with, on three noise rows so each longword must come from its own slot, and on an ALL-BLACK row — the one input where "stored zeros" and "stored nothing" have the same values, so the ledger's length and addresses are what separate them. **NO RESIDUAL LEFT HERE**; the earlier row's on-target prescription is retracted. Mutations killed: the upload one longword short, and the stride long → word |

## Verified — weapon (22)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13d3e` | `entity_type_is_lockable` | 48 | ✅ verified | all 256 type bytes, sharded four ways — exhaustive because the bound is a SIGNED byte compare, so every type from 0x80 up takes the in-range arm and resolves through `ext.w` to a word offset of 0x1ff0..0x1ffe, 8 KB past the table; the eleven types the shipped 0x191ac table lists; both sides of the signed edge; poison on an in-class and an out-of-class type. The answer is the Z FLAG and the routine writes no memory, so the case enters at a `seq` stub (`test/abi.py`). ONE RESIDUAL: the bound's inclusiveness — see the survivor ledger |
| `0x13ede` | `powerup_slot1_activate` | 10 | ✅ verified | the one word store, driven over a timer already holding the value it is about to be given (so the poison pass is what makes it a test), over 0 and 0xffff, with a trailing guard word that catches a long store. UNREACHABLE IN THE GAME — `powerup_capsule_collected` @ 0x13d9e diverts cursor 1 to 0x13f0e before the 0x19348 table is consulted — so this is a read-verified routine that the differential nonetheless drives directly |
| `0x13d9e` | `powerup_capsule_collected` | 216 | ✅ verified | the whole power-up bar, INCLUDING ITS FIVE JUMP-TABLE ARMS, which have no entry of their own: eight cursor values through the uncharged advance (the wrap is an EQUALITY test on the incremented byte, so 4 wraps and 5 walks on); four charge bytes, which hold `tst.b` as a test against zero; eight speed levels through the cursor-0 arm, whose ceiling is an equality test where the other two are signed `ble`s — a level of 2 steps to 3 and STAYS; every (cursor, active slot) pair of the five slots, which separates "index by the cursor" from "index by the slot just stored"; nine levels through both upgrade arms, 0x80 among them so the `ble`s are held as SIGNED; the cursor-1 diversion at six active slots, which is the reason `powerup_slot1_activate` is unreachable; 240-case sharded fuzz; poison on the uncharged arm only. **THE TABLES ARE READ OUT OF THE IMAGE** and mapped back to the C arms (`src/weapon.c`, `POWERUP_ARMS`); `test_powerup_tables_are_fully_reconstructed` asserts both shipped tables hold nothing else. TWO RESIDUALS: the index's SIGN EXTENSION (see `## Coverage limits`) and the fact that a COMMIT case cannot take a poison pass — the canary over the cursor sends the re-run into an out-of-range table index and the oracle `jmp`s to data. Mutations killed: all three ceilings, the cursor wrap, the commit taking the wrong table, the diversion dropped, the seeker arm clearing the shots |
| `0x13cd4` | `ship_resolve_entity_hits` | 106 | ✅ verified | every one of the twelve scan positions with a capsule at it and everything else harmless, which is what pins the bit index and the record cursor stepping TOGETHER; six mask bits OUTSIDE 6..17, which must touch nothing; a lethal touch at three positions against four invulnerability bytes; two capsules in one frame (both taken) against a lethal-then-capsule pair (only the first resolved) — **the lethal arm is a `bra.w` TAIL CALL out of the middle of the loop**, and that pair is the case that holds it; 120-case sharded fuzz over random masks and random type rows including both sides of the class test's signed bound; poison on both arms. `A2 IS AN INPUT` the routine never writes — it is handed straight to `explosion_spawn` as the record to blow apart, and both call sites pass the ship's own — so a reconstruction that exploded the record it FOUND agrees everywhere but there. Mutations killed: the scan's length and first bit, the tail call returning to the loop, the explosion taking the wrong record |
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
needs for the same reason). 0x141c0 is **util's** routine by `../out/subsystems.tsv`; it is verified now,
but under `enemy`, whose script ops were its first ported callers. Its second entry `0x141c2` landed in
wave 3, so `entity_from_index` is now the one site to swap — the debt is tabled in the enemy section.

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

## Verified — input (2)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x14444` | `ikbd_send_cmd` | 16 | ✅ verified | THE PROJECT'S OLDEST KIT WALL, and it is gone. Four instructions, none of which touches an image byte: `btst #1,$fffc00` spins on the IKBD ACIA's TDRE bit and `move.b d0,$fffc02` sends the command. Both halves are now kit surfaces — the status byte is a SEEDED READ slot whose model default has TDRE set, so the loop leaves on its first poll on BOTH sides, and the send goes through the hardware WRITE ledger (`tools/recreate_kit/TRAP_MODEL.md`, Phases 7 and 10). Verified over the nine command bytes the game's own call sites pass plus both ends of the byte and both sides of the sign bit; all 256 bytes as sharded fuzz, each under its own random TDRE-set status and its own junk in D0's high half; four status declarations that share only bit 1, which is what holds `btst #1` against a whole-byte compare; three high halves of D0, which hold `move.b` against a word store. Each case also names the ORACLE's own read stream and write stream, so the row says WHICH registers the routine reaches. Mutations killed: the status bit 1 → 0, the send byte → word, the poll skipped and readiness hardcoded, the send aimed at the status port, the send deleted, the command masked to seven bits |
| `0x1326e` | `onscreen_keyboard_hit_test` | 116 | ✅ verified | all thirty keys addressed by their own screen position; one step either side of all four row-band edges (the bands SHARE their boundaries — a biased y of exactly 0x70 belongs to the TOP row — and the neighbouring rows hold different scancodes there); both column bounds including 0x110, which after the shift indexes byte 28 of a 28-byte row and so reads the NEXT row's first key; one key's whole 24-pixel span, pinning `lsr.w #3`; five incoming D0 values, because D0 IS AN INPUT — a hit overwrites only its low byte, so the caller's high word comes back, while a miss clears the whole register; 400-case sharded fuzz with junk in D0's high half; poison on a hit and a miss. The three row tables are transcribed off the image (the bottom row's last four keys are TWO columns wide, which a description would have got wrong). The routine writes no memory, so D0 reaches the diff through the `jsr`+store stub. `make guarded` covers the computed column index |

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

## Verified — hud (11)

**The graphics are all bss**, loaded from POWER.DAT / SMLOGOS.DAT / SWEAP.DAT / SSWEAP.DAT /
LIFEGRA.DAT / ZYNLOGO.DAT / HEWLOGO.DAT / EXTCHARS.DAT, so every case stages the real file bytes at
the address `_start` loads it to — the same argument the text battery makes about the font. The
three PANEL STRIPS are not a file at all: `_start` stamps STATUS.PI1 into the screen at row 147 and
carves three rectangles back out of it, so `test_hud.py` derives them from STATUS.PI1 at the very
offsets each strip is later stamped to, and `test_the_strips_are_cut_from_the_panel_image` pins
that. The DESTINATIONS are bss too, so each case seeds BOTH framebuffers whole with noise and guard
bands; over zeroes a blit of zeroes is invisible.

`title_screen_draw` is filed here rather than under `text`: `../out/subsystems.tsv` assigns it to
`text` (it is mostly `draw_text_record` calls), but it lives in `src/hud.c` beside the two other
front-end screen composers it is a near-copy of, and `test_status.py` requires a section to name a
`src/<name>.c`.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x1452c` | `hud_draw_logo_anim` | 112 | ✅ verified | eight frame bytes including 0/1 (the game's own), 0x7f/0x80 and 0xff — the byte is EOR'd with 1 and read back, so the frame drawn is the NEW one, and it is re-masked afterwards, which is the only thing bounding a byte nothing else clamps. The source is five 8-byte COLUMNS 0x100 apart, not one 40-byte run, so the poison pass leaves four fifths of each row canary for a candidate that read the row straight through. Mutation killed: the column stride 8 bytes wide |
| `0x1459c` | `hud_draw_powerup_icon` | 62 | ✅ verified | 204 of the 256 cursor bytes, sharded four ways — every one whose pointer lands in the loaded program. That is far more than the five icons the bar shows: past the fifth entry the table runs straight into the weapon table beside it and a negative cursor indexes back into the .PRG's text, both of which `ext.w` + `lsl.w #2` reach. `test_icon_tables_point_into_the_staged_banks` pins the SWEAP.DAT staging address against the game's own pointers, which no differential can do; poison on two icons. Mutation killed: 25 rows instead of 26 |
| `0x145da` | `hud_draw_weapon_icon` | 76 | ✅ verified | both cells over 209 reachable slot bytes each, plus hi-garbage above D0's low byte and a D0 of 0xffffff00 — the cell is a `tst.b`, so only the low byte may move the glyph. The two cells are 16 bytes apart and the glyph is 8 wide, so a wrong right-hand offset leaves the left cell intact and still differs; poison on both cells. Mutation killed: the right cell 8 bytes along instead of 16 |
| `0x137ca` | `draw_power_gauge` | 94 | ✅ verified | levels 0..0x7f sharded four ways — the whole half of the byte whose frame is in the image. The clamp is a SIGNED compare against 4 that WRITES THE LEVEL BACK, so every value from 4 up is both drawn as frame 3 and stored as 3, and that store is diffed. It is also the one panel routine that reads 0x1797e/0x17982 rather than carrying the buffers as literals, so a case swaps them and a third gets a buffer that is neither. Mutation killed: the clamp at `> 4` instead of `>= 4` |
| `0x134ca` | `draw_lives_icons` | 158 | ✅ verified | all 256 lives bytes, sharded four ways — exhaustive because the full/empty choice is a SIGNED BYTE compare of `lives - 1` against each slot's 1-based number and every fork is a single value: 0 underflows to -1 (all empty), 1 is still all empty, 7 fills all six, 0x80..0xff are negative and empty again. Five panel-mask values hold the `bclr #4` against a candidate storing zero; poison on four counts. Mutation killed: the slot test at `<=` instead of `<` |
| `0x13568` | `draw_player_digit_shifted` | 84 | ✅ verified | 128 of the 256 player indices — every one whose glyph stays in the image (see `## Coverage limits`) — into the panel's cell in each buffer and one that is neither. The mask word STARTS AT 0xffff and takes the glyph's AND byte in its low half, so the rotate carries four ones into the top nibble and the background under them survives; over a noisy cell a `clr.w` start differs. Poison on both shipped indices. Mutation killed: the mask word started from 0 instead of 0xff00 |
| `0x136c8` | `draw_score_panel` | 46 | ✅ verified | both framebuffers and one that is neither (A6 is the whole of the destination), over five scores including 0 (which draws eight zeroes), 0x99999999 and 0xffffffff. IT HAS NO `rts` OF ITS OWN — it runs off its end into `draw_bcd_number` at 0x136f6 — so the eight digits are part of this routine's diff rather than a callee's; poison over the strip and all eight cells. Mutation killed: the rightmost digit one column left |
| `0x129aa` | `status_panel_build_master` | 126 | ✅ verified | three strips stamped into the front buffer and then 53 rows of it copied to the 8480-byte master, over three noise seeds. THE SNAPSHOT MUST SEE THE STAMPS: all three land inside the band it copies, so a candidate that snapshotted first differs in the master as well as on screen. The master's own bytes are seeded with noise and a guard band, because it is bss and a short copy would leave zeroes over zeroes; poison over all 8480. Mutation killed: the copy one longword short |
| `0x135bc` | `status_panel_redraw_all` | 268 | ✅ verified | the whole panel from the shipped state and from four states that move every piece at once (gauge level including a clamping one, lives including 0 and a negative byte, player index, logo frame, power-up cursor), plus three score/hi-score pairs — the score comes from `player_score_bcd` and the hi-score from the FIRST ENTRY of the high-score table, at different columns and rows in both buffers. Four entry values for the weapon slot byte, which the routine OVERWRITES itself (0 before the right glyph, 1 before the left) so nothing it held on entry can reach either blit. The buffer pair is also swapped, which moves the half of the panel that reads the pointers and not the half that carries literals. NO POISON PASS — see "Three routines that cannot take a poison pass" below. Mutation killed: the right-hand weapon glyph drawn in the left cell |
| `0x13426` | `player_intro_screen` | 146 | ✅ verified | all 256 player indices sharded four ways — the digit's column is `draw_text_record`'s LEFTOVER D1 and nothing reloads it, and the character is `index + 0x31` added as a BYTE, so 0xcf and up wrap into the three control characters `draw_char` forks on. All three arms of the PREPARE FOR COMBAT flag (0, 1, 0xff), both buffer orders and a third buffer, the 32-byte front-end palette copied into `A_menu_palette` over poked noise (the destination is the first byte of bss and is otherwise zero on both sides), and `clr.w $18fc4` over a noisy shadow, which is what shows it clears ONE word and not sixteen. NO POISON PASS — see below. Mutation killed: the digit's character one higher |
| `0x12a28` | `title_screen_draw` | 154 | ✅ verified | the shipped screen over two seeds, both buffer orders and a third buffer, and — the case that matters — ONE SOURCE POINTER DRAWING BOTH LOGOS: `blit_graphic_block` advances A6, the routine loads it once, three 64-row strips exhaust ZYNLOGO.DAT exactly, and the two 24-row strips after them read HEWLOGO.DAT, which `_start` loads at the next address up. Poking the two files to distinguishable patterns is what separates that from a second `lea`. NO POISON PASS — see below. Mutation killed: the Hewson strips read from the ZYNAPS logo |

### Three routines that cannot take a poison pass, and why

Each refusal is MEASURED — the pass crashes the candidate or leaves it reading outside the image —
rather than assumed, and `make guarded` is what found the second and third:

* `player_intro_screen`, `title_screen_draw` and `role_of_honour_screen` all end in
  `screen_flip_buffers`, which WRITES the two buffer pointers. The pass poisons every oracle-written
  byte, so it poisons the very longword the routine reads its draw buffer from, and the re-run draws
  at a canary address (measured: a bus error in the candidate).
* `status_panel_redraw_all` does not flip, but `draw_power_gauge` inside it writes the clamped level
  back to `power_gauge_display` and then indexes the frame table with it. The canary is the final
  value inverted and that byte can only end on 0..3, so the canary is always 0xfc..0xff — negative,
  which puts the frame 0xff00xx bytes outside the image.
* `draw_power_gauge`'s OWN poison cases are therefore restricted to levels 0..3, which are not
  written back and so are not poisoned. **`make test` passed the clamping level green** before
  `make guarded` caught it: there was no image there to differ.

What the pass would have bought for the composers is bought instead by the routines they are made
of, every one of which has poison cases of its own (`draw_char`, `draw_bcd_number`,
`draw_text_record`, `screen_clear`, `blit_graphic_block`, `playfield_clear`, and all eight `hud`
leaves above), plus the ordering and source-walking cases named in the rows.

**THIS IS A KIT GAP, NOT A PROPERTY OF THESE FOUR ROUTINES, and it wants naming as one.**
`_attribution_check` (`tools/recreate_kit/harness.py`) poisons the oracle's ENTIRE write set, so any
routine that READS A BYTE IT ALSO WRITES gets a canary where its own input was — every
read-modify-write, every write-back clamp, every pointer swap. `differential`'s existing `exclude=`
does not help: it is applied when the images are compared, never to the poisoning loop. The fix is a
`poison_exclude=` (or, better, poisoning `writes − reads`), and the kit already has the half-measure
precedent — `_vet_poison_is_attributable` REFUSES one such combination rather than fixing it. Until
then, attribution for a composer rests entirely on each case hand-seeding noise over every
destination, which is a thing an author can forget: `A_menu_palette` is bss and zero on both sides,
and `test_intro_installs_the_frontend_palette` only works because it pokes noise into the SOURCE.

### Three findings the review raised and this change deliberately did NOT fold in

Recorded rather than fixed, because each one reaches outside this slice's files or its subject:

* **`blit_rows_from_stream` copies BYTES where the original copies longwords.** Every `row_bytes`
  it sees is a multiple of 4 and every offset is even, so a `uint32_t buffered[10]` staged through
  `be32`/`wr32` is byte-identical for every input — and MORE faithful on target, where `be32` is an
  aligned load that address-errors on exactly the odd addresses the original's `movem.l` does. It is
  also ~4x cheaper: one panel repaint moves ~5,400 loop passes where ~1,400 would do, which at 8 MHz
  is on the order of half a frame. Zynaps has no on-target build and no perf gate yet, so this is a
  perf change with nothing to measure it against; it belongs to whichever change lands the first.
* **`blit_rows_from_stream` (here) and `blit_graphic_block` (`src/video.c`) are the same row blit**,
  the second being the first with one destination and a fixed 32-byte row. Two transcriptions means
  the read-whole-row-before-storing invariant has to be re-argued per copy — and this slice proved
  that risk real: `hud_draw_logo_anim`'s first draft dropped it, and only the review caught that the
  comment claiming otherwise was false. Unifying them means editing `src/video.c`, which no routine
  here needs; the natural home is a kit-level blit beside `machine.h`'s primitives.
* **`copy_longwords` here is `src/scroll.c`'s `static copy_longs` and `src/video.c`'s `zero_longs`
  a third time.** Collapsed to ONE definition inside this file (it had been written twice), but the
  repo-wide count is now three `static`s of one loop. The shared home is `tools/recreate_kit/include/
  machine.h`, beside `loop_passes` — a kit change, which is not this slice's to make.

### `src/text.c` and `include/text.h` were edited from this slice

Three changes, all to files the ownership table (`README.md`) assigns to the `text` subsystem rather
than to this one, and all because a routine here needs what the original already shares. **This is
the one convention this slice knowingly steps outside**, and it is recorded here rather than left
for a merge to discover:

* `cell_address` became the exported `text_cell_address`. `draw_lives_icons` @ 0x13506 executes the
  IDENTICAL four instructions `draw_char` @ 0x1371a does (`and.w #$fffe,d1 / lsl.w #2,d1 / adda.w`,
  then `and.w #$1,d1 / adda.w`, both `adda.w` sign-extending), so this is one shared mechanism and
  not two that look alike. A private copy in `src/hud.c` would have been the duplication.
* `draw_text_record` gained a `uint16_t *end_column` out-parameter. That is D1, its SECOND output:
  the original leaves the column one past the last character drawn, nothing reloads it, and
  `player_intro_screen` prints the player's digit at exactly that column. `g_draw_text_record`'s
  glue signature is unchanged, so `test_text.py` needed no edit — which is also why the output has
  no pin in its OWN battery: the stub there dumps A6 alone.
  `test_hud.py::test_intro_digit_follows_the_records_leftover_column` is the pin instead, seven
  record shapes over the length (0, 1, 6, 18 characters), both ends of the start column's sign, and
  a row change that must NOT move the digit. Measured: a `*end_column = column + 1` mutation is
  killed there and survives the whole of `test_text.py`.
* The eight shipped text records the front-end screens print (`A_msg_prepare_for_combat`,
  `A_msg_player`, the four credits, the menu line and `A_msg_role_of_honour`) are DEFINED in
  `include/text.h`, which is where `../out/globals.tsv` puts them and what owns the record format.
  They were briefly in `include/hud.h` under a "borrowed" note; that would have detonated
  `test_constants.py`'s duplicate-NAME check suite-wide the day the text agent spelt any of them,
  and since this change already edits text.h the borrowing bought nothing. `test_text.py`'s own
  SHIPPED_RECORDS still carries all twelve as bare literals — the four the high-score screens use
  join this block when those land.

## Verified — highscore (3)

**Two of these three rows are SLICES**, and both hosts are KIT-blocked whole: `game_over_screen` and
`highscore_check_and_insert` each reach `ikbd_send_cmd` @ 0x14444 on one arm. The slice names are
this reconstruction's, proposed in `../out/names_wave3_misc.txt`, and each row opens with the
`[start, end)` the differential runs.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x13338` | `role_of_honour_screen` | 238 | ✅ verified | the shipped table over three seeds, both buffer orders and a buffer that is neither, five distinguishable scores (a candidate walking the table with the wrong stride differs on four rows of five), five record columns including both ends of the byte's SIGN, and the logo's three strips poked to three patterns — which is what shows they walk ONE advancing source. The load-bearing case is `test_the_score_rows_are_the_routines_own`: each SCORE is drawn at a `lea` displacement of the routine's own (17600 and four steps of 1920) while each NAME is drawn at the row byte inside its record, and the shipped table makes those the same five rows. A table where they differ is the only thing that separates them, and a reconstruction that read the row from the record passes every other case here. NO POISON PASS — see "Three routines that cannot take a poison pass" in the `hud` section above. Mutation killed: the score rows one screen row apart |
| `0x12e66` | `game_over_screen_prologue` | 46 | ✅ verified | `[0x12e66, 0x12e94)`, stopping at the `bsr` into `highscore_check_and_insert`. Four player indices — the digit is `player + 0x31` added as a BYTE before `ext.w`, so the sweep runs past the two the game produces — over a noise-seeded playfield, both buffer orders and a buffer that is neither. THE DIGIT'S COLUMN IS `draw_text_record`'s LEFTOVER (nothing reloads D1), the same idiom `player_intro_screen` uses at a different row; and unlike the two front-end screens this one does NOT flip, because the high-score screens after it compose into the same back buffer. Mutations killed: the digit's row taken from hud.h's, the column named instead of inherited |
| `0x12eb2` | `highscore_rank_and_shift` | 92 | ✅ verified | `[0x12eb2, 0x12f0e)` for the rated arm and `[0x12eb2, 0x12f5a)` for the other — TWO EXITS, so two checkpoints. A MID-ENTRY slice: 0x12eae opens with a `bsr` into a screen clear, so the ranking half has no entry of its own. All five table rows driven, which pins the BACKWARDS walk; the not-rated arm, which writes nothing at all; equality at two rows, holding `ble` against `blt` — an EQUAL score ranks BELOW the entry it matched; a negative table entry, which holds `cmp.l` as SIGNED; a table with a different column, row and terminator per row, which is what says the shift carries the score and the fifteen name characters and NOT the record's own coordinates; a guard entry past the five; 60-case sharded fuzz over UNSORTED tables (nothing here re-sorts). The rank is checked against the ORACLE'S OWN D6 as well as against the byte diff. Mutations killed: the compare's strictness and signedness, the shift's row count, the shift carrying the coordinates |

## Verified — score (1)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x12df6` | `score_add_bcd` | 74 | ✅ verified | all four shipped awards added to the shipped score with A1 one past the entry, as every call site passes it; eight carry cases that walk a carry from the low nibble to the top byte (a candidate adding the bytes in ADDRESS order agrees on 1234 + 5678 and fails at 99 + 01); the threshold's edges, where `bgt` means equality AWARDS and 9999 + 1 is the value that lands on it; the SIGNED longword compare, driven with a score of 0x89999999 that reads as negative; the awarding arm's four outputs at once — the jingle `sound_start` arms, the threshold stepped by its own BCD chain, the lives byte at 0xff where `addi.b` wraps, and `bset #4` over a mask with other bits set; and a 256-case sharded fuzz over random longwords in both operands, INCLUDING nibbles above 9. Poison on both arms. Mutation killed: the low-nibble correction at `> 10` instead of `> 9` |

## Verified — util (8)

`rand16` is the ninth routine of this subsystem and has its own section above (it lives in
`src/rng.c`). `entity_ptr_from_index` @ 0x141c0 is verified too, but is filed under `enemy` — the
script ops were its first ported callers. Its second entry, `0x141c2`, landed in wave 3; see
`## Not reconstructed, and why`.

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

## Verified — init (9)

Nine SLICES, not nine functions, and the distinction is the subsystem's whole shape: `_start`
never returns and neither does the level-section chain it ends in — there is no `rts` between
0x10000 and the frame loop at 0x10f4e. So each row below is a named address RANGE the differential
enters at and stops at (`docs/agent-playbook.md` §5's checkpoint PC and mid-entry slices), and the
"Bytes" column is the range's own length. `../names.txt` gives only the entry an `fn` line
(`_start`); the eight slice names are this reconstruction's, proposed in `../out/names_init.txt` and
`../out/names_wave3_misc.txt`. The chain is now UNBROKEN from 0x10814 to 0x10d96 — the two gaps
earlier waves left between the reload gate and the asset load, and between the asset load and the
pre-fill, are the two newest rows.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10000` | `boot_enter_supervisor` | 16 | ✅ verified | `[0x10000, 0x10010)`. GEMDOS Super(0) and then `movea.l d0,a7` — the program adopts the old supervisor stack. IT WRITES NO IMAGE BYTE, so the empty diff is not the assertion: the token in D0 is, compared against the ORACLE'S OWN D0 and against `harness.OS_SUPER_TOKEN`. **RESIDUAL: that A7 becomes that token is unpinned** — `emu.REPORTED_REGS` does not carry A7 and the reconstruction has no machine stack of its own |
| `0x10012` | `boot_save_vbl_vector` | 10 | ✅ verified | `[0x10012, 0x1001c)`. `move.l $70.l,$195d0.l`, over three vectors TOS might have left there (a plausible ROM address, 0 and all-ones), with the destination seeded to a value that is neither — both addresses are otherwise zero in the loaded image, so without the seed a candidate that copied nothing would differ nowhere. Poison. Mutation killed: the destination zeroed instead of copied |
| `0x1002c` | `boot_load_title_assets` | 398 | ✅ verified | `[0x1002c, 0x101ba)`, the longest stretch of `_start` the harness can run end to end. Eight files read off the disk to the addresses the game gives them, the two framebuffer pointers fixed at their hard-coded values, the game's own VBL and Timer B vectors installed over TOS's, the title tune started, the picture published, its palette uploaded, seven ship frames de-interleaved and one four-frame preshift bank built. Every one of those is a leaf another battery verified; what this row proves is the COMPOSITION — the order and the addresses — over the whole image. Its OFF-IMAGE half is the kit's now: every hardware store the slice makes — the `andi.b #$fc,$ff8260` resolution select, the screen base the flip publishes, the sixteen colour registers `set_palette_title` uploads — is compared by `harness.differential` itself, address, width, value and order (`tools/recreate_kit/TRAP_MODEL.md`, "Phase 10"). ONE RESIDUAL survives that and `src/init.c`'s one-byte sink holds it: `andi.b` is a read-modify-write whose READ half has no modelled answer, so `0 & mask` is 0 for every mask and the ledger cannot tell `$fc` from `$ff`. Mutations killed: the two framebuffer constants swapped, the two vectors swapped, the palette upload deleted, the resolution store deleted, the resolution mask `$fc` → `$ff` (which only the sink can see) |
| `0x10814` | `section_advance` | 38 | ✅ verified | `[0x10814, 0x1083a)`. All sixteen section numbers plus 0xff: the wrap is a `cmpi.b #$10` on the INCREMENTED byte, so 15 wraps to 0 and 0xff increments to 0 and stays there. The map cursor is reset to the level's first column either way and is seeded elsewhere, so a candidate that skipped the reset differs. Poison. Mutation killed: the wrap never firing |
| `0x1083a` | `section_reload_needed` | 32 | ✅ verified | `[0x1083a, 0x1085a)` for the reload arm and `[0x1083a, 0x10b6e)` for the other — **TWO ARMS WITH TWO DIFFERENT EXIT ADDRESSES**, so they are two cases with two checkpoints rather than one case with a branch. Six pairs of (loaded, current) section bytes across both arms; both destination bytes seeded to values neither arm produces, which is what makes the no-write arm a real assertion. The answer is also the slice's return value, so a case checks WHICH exit as well as the bytes. Mutation killed: the comparison inverted |
| `0x1085a` | `section_reload_intro_screens` | 8 | ✅ verified | `[0x1085a, 0x10862)`. Two `bsr`s and nothing else, between the reload gate and the asset load: `player_intro_screen` @ 0x13426 then `status_panel_redraw_all` @ 0x135bc, both verified in `hud`. Driven over `test_hud.py`'s own panel staging — the eight .DAT files at the addresses `_start` gives them plus the three strips CUT OUT OF STATUS.PI1 — which is imported rather than rebuilt so panel graphics keep one source of truth. NO POISON PASS, for `hud`'s own two reasons. **ONE SURVIVOR: the ORDER of the two calls.** Swapping them leaves the image identical, because `status_panel_redraw_all` writes every panel piece to BOTH buffers and `playfield_clear` touches only rows 0..143 — so the flip between them moves nothing. It is observable on a rendered-pixel or on-target surface (what the player sees mid-repaint) and not to any memory differential; see `## Mutation ledger` |
| `0x10862` | `section_load_assets` | 778 | ✅ verified | `[0x10862, 0x10b6e)` over **all sixteen sections — BOTH ARMS**. (The `[0x10862, 0x109e2)` prefix checkpoint earlier waves ran over the four asteroid sections is GONE with the arm's landing: it stopped the ORACLE before the branch, and the candidate now has no prefix to stop at. The longer range covers the same instructions.) Each section is driven with the files its OWN tables name — worked out in the test from the binary's nine sixteen-byte tables rather than from a typed list, so a wrong index stages a file the routine never opens and the open is refused instead of passing. THE FILENAMES ARE PATCHED IN THE TEXT SEGMENT and the diff covers them, which is what holds the table lookups themselves. Downstream it composes two bank builds, the map unpacker, five block copies, eight preshift builders and the per-section palette row. A separate case pins that both ground-target arms are reached by the shipped tables. **THE ASTEROID ARM IS NOW RECONSTRUCTED** and the four sections that take it are driven end to end: one BIGAST.DAT load, six sprite banks built and preshifted over `A_backdrop_page0` (46 KB), the flag the map arm CLEARS and this one SETS, and a FIXED palette row where the map arm takes a per-section one. The answer still names which arm ran, because `section_start_prefill` reads that flag. **The palette SOURCE is pinned only by a poke**: the shipped 0x19638 row is byte-identical to row 0 of the per-section table (measured), so a candidate reading the table instead would copy the same 32 bytes — `test_the_asteroid_palette_row_is_only_pinned_by_a_poke` records the coincidence and the case gives both sides a distinct row. Mutations killed: the alien variant patched one byte early, the missile copies' shared source cursor dropped, the palette row read at half stride, the asteroid flag inverted, the asteroid palette read from the table |
| `0x10b6e` | `section_restart_prologue` | 224 | ✅ verified | `[0x10b6e, 0x10c4e)`. The per-life reset every section start runs through, reached both by falling out of the asset load and by the reload gate's `beq`: the PREPARE FOR COMBAT banner, the two front-end screens above, and then 0xd0 bytes of clears reaching five subsystems — every address included from its owner's header rather than restated. Driven over four alive-byte values (0x00 included, because a table that is already dead is what would hide a missing clear) with a record seeded PAST each of the two eighteen-record arrays. **WHAT SURVIVES IS AS DELIBERATE AS WHAT DOES NOT**: the sweep kills slots 0..17 and the stray `clr.b $17de0` is the GUNSIGHT's alive byte at slot 19, so the ship's SHADOW record (slot 18) is the one entity left alive — and the type-byte sweep is six slots, not eighteen. The ship pair's sprites are ONE FRAME apart (0x640), which is what says they are not two unrelated literals. NO POISON PASS, for `hud`'s reasons. Mutations killed: the sweep length, the gunsight's own kill dropped, the type sweep run over the whole table, the shadow's x, the shadow's sprite |
| `0x10c4e` | `section_start_prefill` | 328 | ✅ verified | `[0x10c4e, 0x10d96)`. Two steps: the restart search (the word table at 0x19e84 scanned BACKWARDS from the section's eight-byte slot for the last offset at or below the map cursor, publishing `map_ptr` / `map_offset` / `scroll_pos`) and then 160 columns of backdrop pre-rendered into the eight off-screen pages with the display hidden. Four sections, five map cursors around the rewind edge, four (page, column) starting positions including both ring wraps, and the asteroid arm that renders nothing. **This is the composition test for the whole scroller**: every one of the eight pages is seeded over a full playfield, so a candidate that filled the wrong page or stopped a column short differs. NO POISON PASS — see `## Mutation ledger`, "init". Mutations killed: the page ring wrapping early, the restart scan walking forwards, the asteroid guard inverted |

**What the whole subsystem still cannot see.** The boot writes three things off the image, and two of
the three are pinned now. The shifter stores it makes through `screen_flip_buffers` and
`set_palette_title`, and the store half of the `$ff8260` resolution select, all go through the kit's
hardware write ledger. What is left is the READ half of that read-modify-write — the six bits of the
mode register the `andi.b` preserves, which neither side has an answer for, held only as a mask by
`src/init.c`'s sink — and the two `move.w #$27xx,sr` interrupt masks, which are a CPU register and
not a device at all. The surface that would pin either is an on-target one
(`docs/on-target-execution.md`).

## Verified — fileio (2)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x144e8` | `load_file` | 68 | ✅ verified | four of the game's own files (extchars.dat, power.dat, status.pi1, lev1.map) staged from `../bin/disk` under the names the IMAGE holds — read out of the table at 0x19686 rather than typed, so a staged name that did not match would fail to open and the model REFUSES rather than fabricating a handle; short counts, a count past the end of the file, and a count of 0; the destination seeded with noise so a short read leaves some of it standing; two loads chained through one stub, which is what holds the handle word being rewritten; poison. The failure path (an unstaged name → Fopen -1) is UNREACHABLE under the model: `os_fopen` tallies a refusal and `differential` throws the case away, which is the correct answer — a case that tested it would be testing `shim.c` |
| `0x156ac` | `asteroids_load_and_build` | 172 | ✅ verified | the whole load-expand-preshift chain over the real BIGAST.DAT, over a short file (Fread serves what is there and the build runs on into the staging buffer's own noise), and over eight pseudorandom 0xf00-byte payloads staged under the image's own filename — which drives mask and plane words the artwork never produces, and is what exercises the `roxr` carry chain inside `asteroid_preshift_bank` across its whole space. Both ends are seeded: the staging buffer, so a short read leaves some of it standing, and the six banks PLUS A SEVENTH, so a build one sprite too long lands on bytes that are not zero. Poison over the whole 46 KB. `make guarded` covers it — the splitter and the preshifter both index the image with cursors they compute. `test_the_read_count_is_exactly_the_six_sprites` pins `move.l #$f00,d1` as a LENGTH (six 32x32 masked sprites, and the shipped file is exactly that long), unlike the two LEVEL reads in `include/init.h`, which really are caps. Mutations killed: the sprite count, the real cells per frame, the preshift pass striding by a frame instead of a bank, the read count. **ONE RESIDUAL, unpinned by construction:** the original runs all six EXPANSIONS and then all six PRESHIFTS, and that separation is unobservable — each bank's expansion and its preshift touch only that bank, and the expansion's only other input is a staging buffer the preshift never writes, so interleaving them into one loop is byte-identical on every input. The two loops are transcribed apart because that is the instruction sequence, not because a case holds them |

## Verified — irq (7)

Every handler returns with `rte`, so each case enters through `abi.interrupt_frame_pokes` — a stub
that pushes the 68000 exception frame the handler pops and lands its `rte` on an ordinary `rts`. The
frame is inside the stack-guard band the differential already drops.

**THE OFF-IMAGE HALF IS PINNED NOW, and the rows below say what that leaves.** `$ff8240..` (the
shifter's colour registers) and `$fffa0f` (the MFP's in-service register B) are outside the 1 MiB
image, so no BYTE DIFF can hold them — but `harness.differential` compares both sides' ordered
`(address, width, value)` store stream on every case (`tools/recreate_kit/TRAP_MODEL.md`, "Phase
10"), and `src/irq.c` makes those stores through the kit's `hw_write8`/`hw_write16`/`hw_write32`.
Deleting a palette upload or an interrupt acknowledge, aiming one at the wrong register, or storing
a word where the original stores a longword is a red; all six were measured killed in the sweep
below. (The three sinks used to be EMPTY bodies in a `src/irq_hw_offtarget.c` of their own, so that a
target build could not inherit them by accident; with a ledger to write through there is nothing
empty left, they are ordinary functions in `src/irq.c`, and a target build supplies `hw_write*`
instead of compiling the kit's `src/hw.c`.)

**ONE RESIDUAL, and it is `mfp_ack_timer_b`'s VALUE.** `bclr #0,$fffa0f` is a read-modify-write, and
the oracle's read of a register the kit's seeded READ model does not name answers a fabricated 0 — so
both sides store 0 and the ledger holds the address, the width and the fact of the store while the
bit the instruction cleared stays unpinned. `docs/on-target-execution.md`'s hardware-state vector is
that byte's surface.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x106a2` | `vbl_isr_title` | 12 | ✅ verified | the sound tick, over an armed voice, compared in memory and through the PSG ledger; its `clr.w $ff8240` through the hardware write ledger, which holds the register AND the word width. Mutation killed: the clear deleted, and the clear narrowed to a byte |
| `0x106ae` | `timer_b_raster_isr` | 200 | ✅ verified | both colour cycles at, and either side of, the frame they fire on, over a shadow seeded with DISTINCT random words — over equal words (or the zeroes the `.PRG` ships for most pens) both machines would be invisible. The countdown of 0 is the case that matters: `subq.b`+`bne` wraps it to 0xff and does NOT fire, which is what an `if (--n <= 0)` reconstruction gets wrong. The two periods differ (8 and 4), so a candidate reloading both from one constant differs on one; poison. Its eight-longword palette upload is held by the hardware write ledger — mutation killed: the upload one longword short |
| `0x10776` | `vbl_isr` | 12 | ✅ verified | THE ONE HANDLER WITH NO HARDWARE STORE AT ALL, and so the only one held end to end: the sync flag over three values, and the sound tick with a voice armed, compared in memory and through the PSG ledger |
| `0x10782` | `timer_b_isr` | 16 | ✅ verified | the sync flag over three values, which is the whole of its in-image effect, and its `bclr #0,$fffa0f` through the hardware write ledger — the acknowledge has no image shadow at all, so before the ledger nothing about it was visible. Mutation killed: the acknowledge deleted. RESIDUAL: the ledger holds the register and the byte width, not the BIT (see the note above) |
| `0x12c9e` | `attract_vbl_isr` | 34 | ✅ verified | the line word, the sync flag and the list cursor, each seeded with a value the handler cannot produce (0x1234, 0x01, 0xdeadbeef) so a missing write shows up on the plain pass, plus the sound tick. Its `clr.w $ff8240` is held by the hardware write ledger |
| `0x12cc0` | `attract_rasterbar_isr` | 130 | ✅ verified | both band edges either side of each — the line is incremented FIRST, so entering on 0x26 puts the handler on 0x27, the first line outside — and the signed arm (a line of 0xffff increments to 0 and is BELOW the band, not far above it); three cursor positions walking the list; and a count of 0, which `subi.w` wraps to 0xffff so the pair is NOT retired. The count word is decremented IN PLACE, so the list is consumed as the band is painted; poison. Its colour store (one WORD, unlike the raster split's longwords) and its acknowledge are held by the hardware write ledger. The two out-of-band arms differ only in a delay loop with no memory effect, which is not reconstructed |
| `0x13c26` | `vbl_menu` | 120 | ✅ verified | every phase byte the counter can hold, including the three that never occur in play (2, 3, 0xff): the original counts UP and compares against 2, so a phase starting above 1 runs all the way round rather than wrapping next frame — which is what separates the instruction pair from the `^ 1` toggle a paraphrase would write (mutation measured killed). Its own eight-longword palette upload, from the OTHER shadow, is held by the hardware write ledger |

**NO POISON PASS ON THE FOUR HANDLERS THAT TICK THE SOUND DRIVER.** Measured, not assumed: with
`poison=True` both `vbl_isr` and `attract_vbl_isr` fail inside the driver at `psg_reg_shadow+1`,
because the tick's outputs include the modulation counters and the tune cursor, which are also its
control flow. What holds them instead is that every flag and pointer a case drives is seeded with a
value the handler cannot produce.

## Borrowed globals

One table for the whole project, merged from the per-slice ones each wave used to keep. A borrowing
header DEFINES an address that `../out/globals.tsv` assigns to somebody else, because no ported
routine of the owner needs it yet. `test_constants.py`'s one-address-one-name and duplicate-address
checks are what will fail — in the OWNER's diff or in the borrower's — the moment two spellings of
one address stand at once, so this is the list that makes the debt findable from the owner's side.
**Deleting a row here and the `#define` it names is the whole of the migration.**

| address | name as spelt | owner, per `../out/globals.tsv` | defined today in | why it is on loan |
|---|---|---|---|---|
| `0x198b1` | `A_scroll_frozen` | scroll-map | `include/enemy.h` | the freeze gate three enemy movers read; no scroll routine writes it yet |
| `0x198c5` | `A_explosion_phase_odd` | sprite | `include/enemy.h` | the half-rate animation gate; `include/sprite.h` does not spell it, and this wave left it where it is on purpose (see the tripwire note below) |
| `0x17d7a` | `A_player_record` | NOT IN `globals.tsv` — `../names.txt`'s `var` line is its only source; `player` by subject | `include/enemy.h` | `enemy_move_type15_dive` reads the ship's position out of it |
| `0x19670` | `A_explosion_group_active_bits` | player | `include/enemy.h` | `explosion_animate_all` / `explosion_spawn` own the bits; no player routine touches them |
| `0x19664` | `A_explosion_group_members` | sprite | `include/enemy.h` | the same pair's member lists |
| `0x195a8` | `A_explosion_particle_offsets` | sprite | `include/enemy.h` | `explosion_spawn`'s cumulative dx/dy/frame triples |
| `0x191fc` | `A_explosion_small_frame_ptrs` | sprite | `include/enemy.h` | the particle sprite table |
| `0x198ae` | `A_explosion_frame_toggle` | NOT IN `globals.tsv`; `../names.txt` names the address and nothing claims it | `include/enemy.h` | `explosion_animate_all`'s own `not.b` gate |
| `0x19902` | `A_fire_charged` | NOT IN `globals.tsv`; `../names.txt`'s `# ctx` name, read as the charge flag the ship-death pass clears | `include/enemy.h` | one of the two clears in explosion group 1 |
| `0x19aad` | `A_boss_sequence_active` | mothership | `include/sprite.h` | `mothership_sprite_preshift` arms the boss encounter with it; `include/mothership.h` belongs to another agent this wave, so it is named here under a BORROWED note, with a tripwire (below) |
| `0x19abf` | `A_enemy_seeker_cooldown` | player ("counts down after a section (re)start") | `include/enemy.h` | `spawn_enemy_shot` both READS and WRITES it as the seeker launcher's own reload gate, and `include/player.h` does not spell it |
| `0x1991a` | `A_lives` | player | `include/hud.h` | `draw_lives_icons` reads it and **`src/score.c` WRITES it** (`image[A_lives]++`, the extra-life award) from a third translation unit, while `globals.tsv` classifies it `read`. The move is four edits, not one: delete the two lines, repoint two MIRRORS rows, swap `src/score.c`'s include |
| `0x1991b` | `A_current_player_index` | player | `include/hud.h` | `draw_player_digit_shifted` and `player_intro_screen`; `include/player.h` spells neither this nor `A_lives` |
| `0x70300` | `A_screen_back_buffer` | video | `include/hud.h` | the framebuffers as ABSOLUTE addresses, which is NOT what `include/video.h`'s `A_screen_back` / `A_screen_front` are — those are the pointer WORDS at 0x1797e / 0x17982. `test/abi.py` already holds the same two numbers for the scratch map |
| `0x78000` | `A_screen_front_buffer` | video | `include/hud.h` | as above |
| `0x1990a` | `A_shield_level` | player | `include/weapon.h` | the gauge three power-up arms clear or step; `include/player.h` spells its two neighbours (0x19907, 0x19908) and not this one |
| `0x19dc8` | `A_speed_decay_timer` | player | `include/weapon.h` | the speed arm refills it; `include/player.h`'s comment on `A_weapon_decay_timer` says out loud that this one is unnamed because nothing read it yet, and now something does |
| `0x19dca` | `A_shield_decay_timer` | player | `include/weapon.h` | as above — four power-up arms refill it |
| `0x19912` | `A_ship_invulnerable` | player | `include/weapon.h` | `ship_resolve_entity_hits`'s gate on the whole lethal arm |
| `0x198c4` | `A_death_event_flags` | `dead` in `globals.tsv` — written and never read, which is not a subsystem and owns no header | `include/weapon.h` | `ship_resolve_entity_hits` sets bit 0; `section_restart_prologue` (src/init.c) clears it and includes weapon.h for it |
| `0x19685` | `A_key_scancode` | NOT IN `globals.tsv`; `../names.txt` names it and the ACIA ISR writes it, so `irq` by subject | `include/init.h` | one of `section_restart_prologue`'s clears, and the ISR that owns it is KIT-blocked |
| `0x198af` | `A_mothership_pending` | NOT IN `globals.tsv`; `mothership` by subject | `include/init.h` | the same clear. `include/mothership.h` belongs to another agent this wave, which is why it is not there |
| `0x199d9` | `A_msg_game_over_player` | text | `include/highscore.h` | `game_over_screen_prologue` prints it; `include/text.h` spells its eight siblings and not this one |

`A_palette_hw_shadow` (0x18fc4) is the one the explosion pass clears that is NOT borrowed: it
already has a home in `include/irq.h`, which `src/enemy.c` includes.

**One migration is DONE and its row is gone rather than annotated.** `A_level_section` (0x19895) was
borrowed by `include/mothership.h` while nothing owned it; `include/init.h` now defines it (beside
`A_level_section_loaded`) and `src/mothership.c` reads it from there. That is what a finished row
looks like.

**A BORROWED GLOBAL WITH A TRIPWIRE.** `mothership_sprite_preshift` arms the boss encounter with four
byte writes that all belong to the mothership subsystem (`../out/globals.tsv`). Three are named in
`include/mothership.h` and are included from there; the fourth, `boss_sequence_active` (0x19aad), is
not, and that header belongs to another agent this wave — so it is named `A_boss_sequence_active` in
`include/sprite.h` with a BORROWED note. The clash that risks is a `test_constants.py` failure whose
message names `sprite.h`, a file the mothership agent is told never to edit, so
`test_sprite.py::test_the_borrowed_boss_flag_has_not_been_claimed_by_its_owner` catches it HERE first
with a message that names the move instead. Related and left alone for the same reason:
`A_explosion_phase_odd` is sprite's per `globals.tsv` but lives in `include/enemy.h`, and stays there
this wave.

## Coverage limits

Five input sets are driven short of their whole byte range, and in every case the bound is the
HARNESS's rather than the game's — a source outside the loaded image is not a case, because the
oracle would read unmapped memory or a synthesised vector while the candidate reads host heap:

| routine | driven | bound |
|---|---|---|
| `hud_draw_powerup_icon` | 204 of 256 cursor bytes | the pointer must be at or above `loader.LOAD_BASE` and its 416-byte read inside the image. Cursor 0x5c fetches a pointer of **0**, and the oracle then serves the 68000 vector page it models while the candidate reads the image's own zeroes — a differential the routine has nothing to do with |
| `hud_draw_weapon_icon` | 209 of 256 slot bytes | the same bound over a 144-byte read |
| `draw_player_digit_shifted` | 128 of 256 player indices | `ext.w` then `mulu.w #$28` is an UNSIGNED multiply, so a glyph number with bit 7 set scales 0xff80..0xffff and lands ~2.6 MB past the font. The reachable set is `(player + 1) & 0xff <= 0x7f`: 0..0x7e plus 0xff. `make test` passed the other 128 (0x7f..0xfe) green, and `make guarded` is what said they were reading nothing |
| `powerup_capsule_collected` | 5 of 256 committed slots | the commit `jmp`s through a table entry the slot indexes, and the index is `ext.w` + `lsl.w #2` added as a WORD — so a slot of 0x80 or more resolves BELOW the table. Whatever longword lies there is jumped to, and for every out-of-range slot tried the ORACLE ran away into data and never reached an `rts` (measured on slot 5: 200,000 instructions, no return). The five the game writes are all a table entry can be, which `test_powerup_tables_are_fully_reconstructed` asserts; the sign extension itself is READ-VERIFIED |
| `spawn_formation` | 18 of 256 formation indexes | past the eighteenth entry the pointer table holds DATA (0x580054 and up), so the record pointer it resolves is outside the 1 MiB image entirely: the oracle bounds such a read and the candidate faults, and no differential can compare the two sides there. `test_the_formation_tables_shipped_extent` reads the entry one past the end back off the image and asserts it does not address the data block. Its two callers pass 0..0x0f (`and.w #$f` on the wave opcode) and 0x0b..0x11 (the boss's per-section byte) |
| `draw_power_gauge` | 128 of 256 level bytes | the same UNSIGNED-multiply bound one table over: `ext.w` + `mulu.w #$100` on a byte at or above 0x80 puts the frame 0xff00xx bytes past POWER.DAT. 0..0x7f is complete — 0..3 select a frame and 4..0x7f all clamp — and 0x80..0xff leave the image |

The game itself writes 0..4 to the power-up cursor, 0..5 to the weapon slot, 0..1 to the player
index, 0..4 to the gauge level and 0..0x11 to the formation index, so every value it can
produce is inside all six sets.

## Mutation ledger

Thirteen sweeps, one per slice that landed, kept as separate sub-tables so that no two agents' counts
ever have to be merged into one number. **Across all thirteen: 458 mutations run, 438 killed, 20
survivors** — every survivor argued below its own sub-table, and every one of them unobservable by
construction or unreachable from data the game can produce, rather than a missing case.

Three lies a sweep can tell are recorded here once, because each was met in this project and each
would otherwise be re-learned per slice:

* **A stale `.so`.** make's ~1 s mtime granularity has re-run an unmutated oracle in this workspace.
  Every sweep below deletes `build/*.so` before each rebuild.
* **A run that never reached pytest.** `.venv` here is a symlink into a shared tree, and a
  concurrent `make venv` broke it for about a minute; every mutant run in that window reported
  "killed" because `import pytest` failed. A run is scored only if it printed a pytest summary line,
  and the baseline is re-checked green before and after each sweep.
* **A red baseline.** One sweep reported all nineteen mutants killed while `test_status.py` was red
  for an unrelated reason. A sweep is evidence only from a green baseline.

A sweep that kills EVERYTHING is itself a tell, and so is one whose mutants all die with the same
failure count — that is one test running, not the suite.

### the first cross-subsystem sweep — rng, sprite, entity, sound and the kit helpers

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

### enemy and mothership, first batch

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

### enemy and mothership, second batch

**Sixty-four mutations over the twenty functions added in this batch, 64 killed, 0 survivors** —
every one rebuilt after `rm -f build/*.so` from a green baseline, and every run required to print a
pytest summary line, because a sweep that never reached pytest reports every mutant killed and looks
exactly like a perfect one. The failure counts ranged from 1 to 80, which is the other half of that
check: a sweep whose mutants all died with the same count is running one test, not the suite.

Every loop count, table stride, record offset, mask, threshold, sign extension, gate polarity, carry
answer and store width the batch introduced was flipped, plus the structural ones a constant cannot
express — the explosion offsets made absolute instead of cumulative, the two clears moved inside
group 1's `btst`, the fall-through into `mothership_place_tail` deleted, the second vertical step of
the bounce aimed at the wrong axis, and the animation dispatcher's `(x & 0xf)` index masked the way
its four-frame siblings mask theirs.

ONE FURTHER MUTANT IS EQUIVALENT, found by re-running the sweep's affected anchors after the
review gate's refactors: `EXPLOSION_GROUP_SHIP` 1 -> 0, which moves the two clears
(`A_fire_charged`, `A_palette_hw_shadow`) from group 1's pass to group 0's. Both groups are visited
on every ticking call, the clears are idempotent, and nothing between them writes either address —
`explosion_part_step` touches only the record's frame, alive byte and sprite pointer. So the two
programs leave identical memory and no case can separate them. Recorded rather than counted as a
kill; the fact the mutant tests (which group the clears belong to) is carried by the disassembly and
by the comment beside the constant.

TWO ARMS IN THIS BATCH ARE UNREACHABLE and are recorded rather than mutated, because a mutation of
either changes the arm that IS reached and so dies for the wrong reason:

| arm | why nothing can reach it |
|---|---|
| `actor_script_op_random_speed_nudge`'s "+1" nudge | `cmp.b #$55` + `bge` admits only 0x55..0x7f read as signed bytes, and every one of those is above 0xaa read the same way, so `blt #$aa` never branches. `test_op_random_speed_nudge_never_draws_the_increment` asserts exactly that over all 256 draws |
| `explosion_spawn`'s group index modulo 8 | `bset d2,<ea>` counts the bit mod 8, but a group above 1 walks `group * 6` bytes into the member list and reads entity indices out of whatever follows the two lists the game ships — an index of 0x80 or more addresses ~0x2bedc0 past the table, outside the image. Both call sites pass a literal 0 or 1. The `% 8` stays because it is what the instruction does, and because it is also what keeps `1u << group` out of C's undefined range |

### the tile decoder and the three sprite additions

Nineteen mutations over `scroll_emit_tile_column`, `sprite_bank_build_preshift8`,
`mothership_sprite_preshift` and `draw_sprite_masked_collide`, each rebuilt after `rm -f build/*.so`
(make's ~1 s mtime granularity has re-run an unmutated oracle in this workspace before), each scored
only on a run that produced a pytest summary line (the `.venv`-broken sweep this file already
records), and the baseline re-checked green before and after — **17 killed, 2 survivors**. The
per-function rows above name the killed ones; both survivors are here, and both are redundancies
rather than coverage holes.

| mutation | result |
|---|---|
| `draw_sprite_masked_collide`'s middle band re-reading the screen row before the composite | **SURVIVED** |
| `scroll_emit_tile_column`'s screen store and page store swapped | **SURVIVED** |

**The re-read is faithful and unobservable.** The original's middle band runs `movem.l (a0),#$003c`
twice — once for the collision test, once for the composite — because the test clobbers the
registers it loaded. Between the two lies the `st (a5)` that sets the hit flag, so the second read
sees a different row than the first ONLY if A5 pointed into the row being drawn. Neither call site
does: 0x11c48 passes the record's own `ENTITY_PIXEL_HIT` byte and 0x13096 a front-end byte at
0x19ce3. The two edge bands read once and keep their copy, which is a real difference between the
arms and is transcribed rather than tidied — the mutation says only that no case can see it.

**And the store order is unobservable by construction.** With `scroll_prefill_hide_screen` clear the
two destinations are disjoint (a page in `map_page_table`'s 0x1a8ae..0x478ae range, a framebuffer at
0x70300/0x78000); with it set they are the SAME address and the two stores write identical bytes. So
no reachable input separates them. The order is written the original's way anyway.

**Two fuzz caps, both measured and both load-bearing.** `test_bank_build_fuzz` keeps `frame_bytes`
at or above 2: both of that routine's passes count through a `dbf`, so a width of 0 halves to 0 and
each frame becomes 128 KB of traffic for a width no call site passes. `test_tile_column_fuzz` fuzzes
the COLUMN and never the map word: a map word is a tile index scaled by 64 into an absolute address,
so a random word reaches up to 2 MB past `A_tile_set_base` — off the 1 MB image, where the oracle
drops the read and a reconstruction indexing `image + addr` reads host memory instead. That is the
class `make guarded` exists to find, and what keeps it out of reach is that every case's indexes come
from the game's own maps against the tile set that level really loads. **The residual: no case drives
a tile index the loaded set does not cover**, and none can honestly be fabricated — the game's maps
are the only source of indexes there is.

**One reach the game's own data DOES make, and it is tested.** Column 399's peek at the next column
lands 36 bytes past the unpacked map, in the 720-byte bss gap before `A_tile_set_base`. Left as the
image's own zeroes it names tile 0 for all eighteen rows, which is what makes the case runnable;
`test_tile_column_last_column_peeks_past_the_map` drives it and asserts the gap is still wide enough.

### video, scroll, sprite

Thirty-eight mutations across `video`, `scroll` and `sprite`, each rebuilt after `rm -f build/*.so`
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

### the weapon / collision / player / input slice

Thirty-seven mutations over the twenty routines of the `weapon` / `collision` / `player` / `input`
sections, each rebuilt with `rm -f build/*.so` first, from
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

### the steering / launch / projectile-update batch

Thirty-six mutations over the seven routines that batch added and the two helpers they now share with
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

### hud / highscore / score

Thirteen mutations, one per verified function of the `hud` / `highscore` / `score` sections, each
with the .so deleted before the rebuild
(make's ~1 s mtime granularity has re-run an unmutated oracle in this workspace before) and each run
from the green 1733-test baseline with its own pytest summary line recorded — **13 killed, 0
survivors**. Every mutation edits a `src/*.c` BODY and never a header constant a battery mirrors: a
mutated mirror fails `test_constants.py` by itself and would report a kill nothing else made. The
per-function rows above name each one.

**THE CODE REVIEW FOUND A REAL DEFECT THIS SWEEP DID NOT**, and the gap is worth recording because
it was a missing CASE and not a missing mutation. `redraw_player_strip` was reading the buffer
POINTERS where the original carries literals — the two strip blits are `lea $7f238.l,a0` @ 0x135ca
and `lea $77538.l,a0` @ 0x135f2, and so are the two `lea`s into the digit that follow them, while
the hi-score strip four instructions later genuinely does read `movea.l $17982.l,a3` @ 0x13620. The
only case that moved the pointers SWAPPED them, which is symmetric across the two literals: the
wrong code wrote the same two addresses in the other order and the diff stayed empty.
`test_redraw_all_moves_only_the_half_that_reads_the_pointers` now points a pointer at a THIRD
buffer, which is what separates the two halves; measured, it fails on the old code and passes on the
new. Every other composer in this slice already had a third-buffer case — this was the one that did
not, and it was the one where the code conflated them.

**One survivor is known and was not counted, because it cannot be reached at all.** `score_add_bcd`
hands `sound_start` a channel taken from D0, which at that point still holds the threshold longword
the compare was made with — nothing sets it deliberately. It is DEAD in the shipped binary: tune
0x10 opens with its own `fa 04` header, so `sound_start` overwrites the channel before using it. A
mutation that passed 0 there would survive the whole suite, and no data the game holds could kill
it. The argument is passed on because that is what the instruction stream does.

### init

Fourteen mutations, each rebuilt after `rm -f build/*.so`, each scored only on a run that produced a
pytest summary line, and the baseline re-checked green before and after — **13 killed, 1 survivor**.
Two of the fourteen were added by the pre-commit review and are the ones worth naming here, because
each closes a hole the review found rather than confirming something the battery already held: the
TITLE PALETTE UPLOAD deleted (killed by the slice's own upload counter — `set_palette_title` writes
no image byte at all, so before that counter existed the deletion left the suite green), and THE
ASTEROID ARM falling into the map path instead of reporting the branch it cannot follow (killed by
the four asteroid sections' prefix cases).

| mutation | result |
|---|---|
| the rewind floor tested with `>` instead of `>=` | **SURVIVED** |

**And it is unreachable, not untested.** The two spellings differ at exactly one input: a map cursor
of 0x47b7e, where `>=` rewinds by 0x2d0 and `>` does not. The restart search that follows then runs
with an offset of 0 in one reading and 720 in the other — and the word table at 0x19e84 answers both
with the same entry, because every backward scan from a section's own slot meets one of the table's
zero words before it meets anything in (0, 720]. The three globals the slice publishes are derived
from the entry the search FOUND and not from the cursor it started with, so nothing downstream can
separate them either. The case at 0x47b7e is in the battery; it is the mutation that has no witness.

**NO ATTRIBUTION PASS ON `section_start_prefill`, and it is measured.** `map_ptr` is both an input to
the restart search and its output, and `map_page` / `map_column` are both the pre-fill's cursors and
its results, so poisoning the oracle's own writes diverts its control flow (`docs/agent-playbook.md`
§8's pitfall). `test_section_start_prefill_publishes_the_search_result` stands in its place: it reads
the three globals back out of the oracle's final image and checks the two derived longwords against
the cursor the search settled on, so a candidate that published the cursor and left the other two to
chance fails there.

### sound / util / text / fileio / irq

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
| `mfp_ack_timer_b` stores nothing | killed |
| `shifter_clear_pen0` stores nothing | killed |
| `shifter_clear_pen0`'s width word -> byte | killed |
| the raster split's palette upload one longword short | killed |
| `screen_flip_buffers` stores its two base bytes in the wrong ORDER (same addresses, same values) | killed |
| `set_palette_title`'s stride long -> word | killed |
| `_start`'s `$ff8260` resolution store deleted | killed |
| `SHIFTER_MODE_RESOLUTION_MASK` 0xfc -> 0xff (the ledger cannot see it; `init_shifter_mode_mask_written` is what does) | killed |
| `ikbd_send_cmd` tests status bit 0 instead of bit 1 | killed |
| `ikbd_send_cmd`'s send width byte -> word | killed |
| `ikbd_send_cmd` skips the poll and hardcodes readiness | killed |
| `ikbd_send_cmd` sends to the STATUS port instead of the data port | killed |
| `ikbd_send_cmd`'s send deleted | killed |
| `ikbd_send_cmd`'s command masked to seven bits in the glue | killed |
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

### wave 3 — the power-up bar, the ship's hit pass, the asteroid arm and the two front-end slices

Thirty-six mutations over the nine routines and slices this wave landed, each rebuilt after
`rm -f build/*.so`, from a green baseline re-checked before and after. **35 killed, 1
survivor** — and the survivor was reduced from two by adding a case, which is the outcome the
"pin it by seeding real data" rule asks for rather than an argument.

It ran in two passes. The first twenty-nine went before the code-review gate, from a 2,863-case
baseline; the last seven went AFTER it, from the 2,864-case baseline, over the constants and the
one helper the review's fixes moved — a refactor that collapses six copies of a store into a helper
has to re-earn its coverage rather than inherit it.

| mutation | result |
|---|---|
| all three power-up ceilings (speed, shield, weapon power) | killed |
| the cursor's wrap count | killed |
| the commit taking the ACTIVATE table where the original takes the UPGRADE one | killed |
| the cursor-1 diversion deleted | killed |
| the seeker arm clearing the shots in flight, as its two siblings do | killed |
| the hit scan's length, and its first bit index | killed |
| the lethal arm returning to the loop instead of tail-calling out of it | killed |
| the explosion taking the entity the ship touched instead of the ship | killed |
| the asteroid sprite count, and the real cells per frame | killed |
| the two asteroid passes interleaved into one loop | **not run — unobservable by construction**; see the fileio row |
| the preshift pass striding by a frame instead of a bank | killed |
| BIGAST.DAT's read count | killed |
| the asteroid-section flag inverted | killed |
| the asteroid palette row read from the per-section table | killed **after a case was added** |
| the two front-end calls swapped | **SURVIVED** |
| the restart sweep's length; the gunsight's own kill deleted; the type sweep run over the whole table | killed |
| the ship shadow's x, and its sprite | killed |
| the game-over digit's row taken from `hud.h`'s; its column named instead of inherited | killed |
| the ranking compare's strictness, and its signedness | killed |
| the shift's row count, and the shift carrying the record's coordinates too | killed |
| *(post-review)* each of the three new panel-repaint bits, and `panel_request_repaint` assigning instead of OR-ing | killed |
| *(post-review)* the restart type sweep's bound, now `PLAYER_SHOT_SLOTS`; the ship frame stride, now `SHIP_SPRITE_GAP`; the launch restock value | killed |

**The survivor, and why it is not a missing case.** Swapping `player_intro_screen` and
`status_panel_redraw_all` inside `section_reload_intro_screens` leaves the image byte-identical.
`status_panel_redraw_all` writes every panel piece to BOTH framebuffers — the score panel and the
hi-score strip through the pointer pair, the player strip and the icons through absolute addresses —
so the `screen_flip_buffers` that ends the intro exchanges two pointers whose buffers both end up
holding the same panel. And `playfield_clear` inside the intro touches rows 0..143 while the panel
begins at row 147, so neither call can erase the other's work. Driving the pointers swapped, or at a
third buffer, does not break the symmetry; it is a genuine property of the two routines, not of the
staging. The surface that WOULD catch it is a rendered-pixel or on-target one — which buffer is on
screen while the panel is half-drawn — and `docs/on-target-execution.md` is where that lives.

**The other survivor was pinned rather than argued.** Reading the asteroid palette from the
per-section table's row 0 instead of from 0x19638 survived the whole suite, because the shipped .PRG
holds the SAME 32 bytes at both addresses. The fix was to give both sides a distinct row at 0x19638
— real program data, not a fabricated record — and
`test_the_asteroid_palette_row_is_only_pinned_by_a_poke` records the coincidence so the poke does not
read as arbitrary.
### enemy and mothership, third batch — the AI tree

**Seventy-eight mutations over the twenty-two functions this batch added, 78 killed, 0 survivors.**
Every one rebuilt after `rm -f build/*.so` from a green baseline, every run required to print a
pytest summary line, and — because `-x` would make every mutant die with the same count and hide a
sweep that was running one test — the batteries were run WHOLE. The failure counts ranged from 1 to
169 across 29 distinct values, which is the other half of that check.

Flipped: every table address, table stride, loop count, record offset, mask, threshold, bound
inclusiveness, sign extension, gate polarity, carry answer and store width the batch introduced,
plus the structural mutations a constant cannot express —

* the script VM's fetch moved onto the wrong delay value, and its `addq.b #1` restore deleted;
* the bounce latch left uncleared on a fetch, and the script pc read UNSIGNED;
* the move pass dispatched through the animation table, walked one slot short, and stripped of its
  second handler map (the arm types 0x17..0x2d take);
* `enemy_fire_and_update_shots`' chance index spelt as an `ext.w` instead of carrying the caller's
  high byte — the mutation that says why that core takes a register at all;
* the ground spawners' guard narrowed to the WORD, which is the difference between what the `beq`
  reads and what it looks like it reads;
* `spawn_formation`'s pass count taken as the raw byte instead of through `loop_passes`, its x
  offset read unsigned and its y offset read signed, and its kind read from byte 1 whatever the
  header flag said;
* `wavescript_spawn_wave`'s two opcode bits tested independently instead of nested;
* `mothership_segments_respawn` stripped of the pre-spawn marking that reserves the odd slots;
* `mothership_segment_hit` reduced to exploding only the half it was handed.

THREE COVERAGE HOLES WERE FOUND AND FIXED, not recorded — which is the point of running the sweep
and the review rather than quoting the last one:

* `enemy_fire_and_update_shots`' chance compare made EXCLUSIVE **survived**, because no case reached
  that compare with the draw equal to the section's byte. Three generator draws stand between the
  routine's entry and the comparison, so the fix is `_state_whose_fire_draw_is` — a search for a
  state that passes the roll and then draws a KNOWN value — plus a chance byte poked over the seeded
  band. The searched state is what makes it a case rather than a coincidence.
* `mothership_segments_respawn`'s section→energy index was **untestable**: the battery filled all
  sixteen bytes of the energy table with one value, so every in-range section read the same byte and
  a candidate that hard-coded section 0 was green on all sixteen cases. The table is seeded with
  NOISE now and only the section under test is poked; both "hard-coded to 0" and "off by one" die.
* THREE OF THE EIGHT OPCODE CLASSES were dispatched through `actor_script_run` by no case at all —
  the shipped scripts' own first opcodes only reach classes 0, 5 and 7 — so a class arm paired with
  the wrong handler survived. `test_script_run_dispatches_every_class` drives all seven live classes
  with one operand, and the three MIS-PAIRING mutants now die.

TWO EQUIVALENT MUTANTS were met and are recorded rather than counted: permuting the ROWS of
`SCRIPT_CLASS_ARMS`, and swapping the order of `run_script_arm`'s two `if`s. The first is equivalent
because that array is a map KEYED BY ADDRESS with distinct keys, so its row order carries no meaning
— the mutation that does bite is mis-PAIRING an address with another arm's handler, which is what
the three above are. The second is equivalent because every shipped arm carries exactly one of the
two function pointers.

## Suite-wide checks (not functions, so not counted above)

| file | what it holds |
|---|---|
| `test/test_constants.py` | the CLAUDE.md §5 pin, as a COLLECTOR rather than a registry so concurrent agents never edit it: every constant a battery restates equals the `#define` that owns it, every entry address equals the original's own first ten bytes, every battery declares both, no constant is defined in two files, no address has two `A_*` names, and `test/abi.py`'s scratch map clears the program, the game's hard-coded framebuffers and the staged-file table |
| `test/test_status.py` | this ledger's per-section counts against its rows, and its section names against `src/*.c` |
| `test/test_heap_guard.py` | the run-time half of the `tos_malloc_unused` waiver — ported from Joust, the other project the kit's guard is armed for. Until it landed the waiver was declared but never exercised here, because every case in the suite runs a pure leaf that traps not at all |

## Not reconstructed, and why

ONE table for the whole project, sorted by address, one row per unported function or per gap
between the init slices. Every `fn` line in `../names.txt` that has no ✅ row above appears here
exactly once — 9 of them — plus the five ranges the nine init slices do not join up over and one
address the name map reaches only by `cmt`. Two of the 9 are PARTLY verified above: `game_over_screen`
and `highscore_check_and_insert` each contribute a slice to `## Verified — highscore`, and their rows
say what is left rather than claiming nothing is. Each blocker is re-derived against the verified set
above (call targets read out of `../out/prg_dis.txt`, dispatch tables out of `../names.txt`'s own
table accounting), not inherited from the wave that wrote the row. The categories:

* **UNBLOCKED** — every callee is verified. What is left is transcription, and the row names what it
  composes.
* **BLOCKED-ON `0xaddr`** — one or more named callees are themselves unported; the row gives their
  addresses so the chain can be walked.
* **KIT** — the harness cannot run it at all. **All three of the walls this table used to name are
  gone**, closed in the kit rather than worked around here: `ikbd_send_cmd`'s `$fffc00` ACIA spin is
  a seeded READ slot and its `$fffc02` write is ledgered (kit `TRAP_MODEL.md`, Phases 7 and 10); the
  staged-file table holds 32 files, not 8; and every off-image palette / shifter / MFP store is
  compared as an ordered `(address, width, value)` stream. What is left under this label is ONE
  address and it is named where it is used: a READ of the ACIA's data port `$fffc02`, which
  `ikbd_acia_isr` makes and no phase models.
* **DEAD CODE** — nothing references it, and that is a finding rather than a block.

| Addr | Name | Status |
|---|---|---|
| `0x10010` | `_start`'s Line-A opcode | **MODELLED, not verified.** `$a00a` (hide the mouse pointer) is an unimplemented instruction the oracle takes as an exception, so no case can run through it. It is modelled as a NO-OP — there is no mouse pointer on any surface this project compares — and that is a model, not a verification |
| `0x1001c`..`0x1002c` | `_start`'s two `ikbd_send_cmd` calls | **UNBLOCKED — the wall is gone.** Both reach `ikbd_send_cmd` @ 0x14444, which is **verified** above: `$fffc00` is a seeded READ slot whose model default has TDRE set, so the spin leaves on its first poll on both sides, and the `$fffc02` send is ledgered. What is left is sixteen bytes of composition — two `move.b`+`bsr` pairs — waiting for a checkpoint slice that joins them to `boot_save_vbl_vector` above and `boot_load_title_assets` below |
| `0x101ba`..`0x10814` | the rest of `_start` | **UNBLOCKED — the wall is gone.** The staged-file table held eight files and the boot opens about thirty; 0x101ba was where the ninth would have been. `OS_FS_SLOTS` is 32 now, sized on this boot's own count (22 `load_file` calls before 0x10814, and five more per level section), and the staging area is nowhere near full — 66,818 bytes of file against 258,048 between `OS_FS_STAGING` and the stack guard, measured off the `move.l #len,d1` before each call. What the range needs now is ordinary slice work: a checkpoint at 0x10814, the thirty filenames and destinations read off the listing, and the sprite/preshift leaves it composes (all verified). Its one non-file hazard is the Line-A opcode at 0x10010, which is behind this range's entry rather than inside it |
| `0x10d96`..`0x10f4e` | the section start's tail | **UNBLOCKED — the ACIA wall is gone.** It polls the joystick through an `ikbd_send_cmd` at 0x10f26, and that routine is verified above; the poll now terminates on both sides and both its hardware accesses are compared. What remains is a checkpoint slice over the range |
| `0x10f4e`.. | the frame loop | **BLOCKED-ON `0x113c0`, `0x11c00`, `0x11d30`** — the three frame stages below are the loop's whole body |
| `0x113c0` | `frame_weapons_and_spawn_stage` | **BLOCKED-ON `0x11c00`** alone now — the other eight callees this row used to name (`0x11906`, `0x13868`, `0x13898`, `0x13958`, `0x13a12`, `0x13af2`, `0x1487c`, `0x14fc8`) are all verified above. Frame stage one: trail drone, fire/charge, weapon dispatch, bullet motion, spawn scripts, ending in a `bra` into 0x11c00. It is an orchestrator, deferred to world-staging, per the playbook's order of attack |
| `0x11c00` | `frame_draw_objects_and_collide` | **BLOCKED-ON `0x11d30`** (its own `bra` tail) alone; `0x151ba` landed. Everything it does itself is verified — `draw_sprite_masked_collide` 0x15b7c over the 20-entry object table, `asteroids_draw` 0x159be, and `object_pair_overlap_mark` 0x11cce building the all-pairs mask at 0x18252 |
| `0x11d30` | `frame_resolve_hits_and_game_state` | **BLOCKED-ON `0x12e66`** (partly verified, below) alone — `0x13ad0`, `0x13cd4`, `0x15222` and its `ikbd_send_cmd` @ 0x14444 poll are all verified now, so the KIT half of this row is gone. Frame stage four: resolve the collision matrix, run the game-state machine, starfield, decay timers, scroll step, buffer flip — and it leaves through five different addresses (0x10f4e / 0x10b6e / 0x1083a / 0x10814 / 0x10500), so it is world-staging work whatever its callees do |
| `0x12ac2` | `title_attract_loop` | **UNBLOCKED.** It waits for key '1'/'2' or joystick fire through `ikbd_send_cmd` @ 0x14444, now verified — sending the interrogate command is no longer a wall. Everything else it needs is verified too: `title_screen_draw` 0x12a28, `role_of_honour_screen` 0x13338, `rand16` 0x13bf8, and its own two ISRs 0x12c9e / 0x12cc0. **What it will need instead is a case shape, not a kit surface**: the loop spins on a byte only `ikbd_acia_isr` writes, which is Phase 8's scheduled-write model (`schedule=` / `wait_sites=`) rather than anything about the ACIA |
| `0x12e66` | `game_over_screen` | **PARTLY VERIFIED, and blocked past that.** `[0x12e66, 0x12e94)` — the playfield clear, the GAME OVER PLAYER record and the player digit — is `game_over_screen_prologue` in `## Verified — highscore`. What is left is the `bsr` into `highscore_check_and_insert` (below) and the eight-longword palette restore on ITS not-rated arm, which is four instructions this reconstruction cannot reach without running the routine it follows |
| `0x12eae` | `highscore_check_and_insert` | **PARTLY VERIFIED, and BLOCKED-ON `0x12fd4`** for the rest — the KIT half is gone, `ikbd_send_cmd` @ 0x14444 (its NOT RATED arm) being verified. The ranking and shift-down half is `highscore_rank_and_shift` in `## Verified — highscore`, entered MID-ROUTINE at 0x12eb2 and stopped at whichever of 0x12f0e / 0x12f5a the ranking chose. (An earlier row here gave the range as 0x12eb2..0x12f0c; 0x12f0c is not an instruction boundary — the `dbf` at 0x12f0a runs to 0x12f0e, which is also where both arms of the shift converge.) What is left is the screen clear at 0x12fc2 that the entry `bsr`s into, the NEW HIGH SCORE screen, and the two keyboard loops |
| `0x12fd4` | `highscore_enter_name` | **UNBLOCKED at the kit level.** The name-entry loop drives the keyboard through `ikbd_send_cmd` @ 0x14444, now verified. Its two busy-waits — for a scancode only `ikbd_acia_isr` stores, and on the VBL flag at 0x198a7 — are Phase 8's scheduled-write model, which the kit already has and this project has not used yet. Its drawing half is clear now: `draw_sprite_masked_collide` (0x15b7c) is verified, as are `onscreen_keyboard_hit_test` (0x1326e), `draw_char`, `draw_text_record`, `screen_flip_buffers` and `blit_page0_to_playfield` |
| `0x14456` | `ikbd_acia_isr` | **KIT, and the row is re-derived: two of the three gaps it inherited are closed.** It is an interrupt handler entered around a frame rather than a called routine, which `abi.interrupt_frame_pokes` already handles for the seven `irq` handlers. Of its four hardware accesses: `btst #4,$fffffa01` is the MFP GPIP, ALREADY a seeded READ slot (`hw_seed={0xfffa01: …}`); `bclr #6,$fffffa11` is a store to the MFP's in-service register B, ALREADY held by the hardware WRITE ledger, at the same fidelity as `mfp_ack_timer_b`'s (address and width, not the bit — its read half is a fabricated 0). **What is still missing is exactly one thing: a READ of the ACIA's data port.** The handler does `lea $fffffc00.l,a0` and then reads `(a0)` for the status and `2(a0)` for the byte, so it reads `$fffc02` once per entry and again per packet byte — and that port answers whatever the keyboard controller last put there, which is neither a per-run constant (Phase 7's shape, and the reason `$fffc02` is deliberately not a slot) nor a store into the image (Phase 8's). It needs a THIRD kit shape: a declared SEQUENCE of bytes one address yields, one per read. Note for whoever builds it: the 68000's 24-bit bus folds the handler's `$fffffc00` onto `$fffc00`, which the oracle masks and `hw.h` does not — a reconstruction spells the 24-bit form |
| `0x148ca` | — (no `fn` line; `../names.txt` reaches it by `cmt` only) | **DEAD CODE, and that is a finding rather than a block:** nothing anywhere references it, and it is a near-copy of `enemy_move_type14_sine` using D6 as a slot index into 0x19673. Left unported deliberately |
| `0x16aa6` | `sound_install_timer_a_dead` | **DEAD CODE** — unreferenced, per `../names.txt`. It would reset the PSG and then `Xbtimer` (Timer A, ctrl 7, data 0xf4, vector 0x16b94) to run the sound tick off Timer A instead of the VBL. Its one callee, `sound_reset_psg`, is verified |

**The three name-map corrections `../out/names_sound.txt` once carried are IN `../names.txt` now** (the
`var` lines at 0x19933 / 0x19a0b and the SFX-toggle comment at 0x16e90 — commit d383ae0); nothing is outstanding there.

**The off-image class was a KIT gap and it is closed.** `$ff8240..` (the shifter's colour
registers), `$ff8201`/`$ff8203` (the screen base), `$ff8260` (the resolution byte) and `$fffa0f`
(the MFP's in-service register B) are outside the 1 MiB image, so an oracle store there is dropped —
but `harness.differential` now compares both sides' ordered `(address, width, value)` store stream
on every case (kit `TRAP_MODEL.md`, "Phase 10"), and `src/irq.c`, `src/video.c` and `src/init.c` make
those stores through `hw_write8`/`hw_write16`/`hw_write32`. Six of the seven `irq` handlers,
`screen_flip_buffers`, `set_palette_title` and the boot slices are all held now; the eight mutations
this project ran against them were all killed, and `src/irq_hw_offtarget.c` — the file of empty
bodies that stood in for the ledger — is deleted.

**Two residuals survive it, both stated where they arise.** A READ-MODIFY-WRITE at an address the
seeded READ model does not name (`bclr #0,$fffa0f`, `andi.b #$fc,$ff8260`) computes its value from a
fabricated 0 on both sides, so the ledger holds the address, the width and the fact of the store
while the MASK or the BIT stays unpinned — `src/init.c`'s one-byte sink holds the resolution mask,
and the MFP bit is unheld. And the two `move.w #$27xx,sr` interrupt masks are a CPU register rather
than a device, which no ledger reaches. Both want an on-target surface
(`docs/on-target-execution.md`, the hardware-state vector).

## Suite

`make test` — **3410 passed**, 4 skipped. `make guarded` — same count, 20614
candidate runs guarded across 10 workers, no fault.

THIS LINE IS SHARED, and several agents add batteries to this project at once — the count is
whatever the last one to run the suite measured, so treat a mismatch against your own run as a
concurrent landing rather than a regression until you have checked which sections moved.

## On target

**`atari/README.md` is canonical for everything below; this section is a pointer and a count.**

`atari/` cross-compiles the VERIFIED cores above into `ZYNAPS.PRG` and runs them on a 68000
(Hatari, TOS 1.04, `--machine st --memsize 4`). **Milestone M1, 2026-08-29: the title picture and
its music.** It composes `_start`'s verified slices in the original's order and stops at `0x101ba`,
where the "Not reconstructed" table above stops the boot — so nothing on target runs a slice this
file does not carry a ✅ row for.

`python3 atari/smoke.py title` judges it against the shipped binary on the six surfaces of
`docs/on-target-execution.md`, and all twelve checks are green: the 32000-byte framebuffer is
**byte-identical**, the rendered picture is **byte-identical**, the sixteen pens / `$ff8260` /
`Physbase` agree, the GEMDOS ledger is 24 parsed calls matching the original's first 24 (the same
eight lowercase names, in order, on the same handle, with the same byte counts), and the first 64 of
the sound driver's tick frames are the same register stream. `smoke.py titlefault` is the negative
control — one pen corrupted on its way to the shifter — and reddens exactly the two colour surfaces
while the other twelve stay green.

**Two things this section is here to say to a reader of the tables above:**

* **The off-image class is still unpinned OFF target, and is now pinned ON it for the slices M1
  runs.** The rows above record that `$ff8240`, `$ff8260` and `$fffa0f` are outside the 1 MiB image
  and that no case here can fail on a palette upload or an interrupt acknowledge. That is unchanged.
  What M1 adds is the other surface those rows name — a Hatari register snapshot — for
  `boot_load_title_assets`, `set_palette_title`, `screen_flip_buffers` and `vbl_isr`.
  Six of the seven `irq` handlers, and `timer_b_isr`'s acknowledge, are still unexercised: they
  belong to the front end and to an MFP timer M1 never starts. `atari/README.md`'s "Unpinned" list
  is the full ledger, with a reason each.
* **`ikbd_send_cmd` @ `0x14444` and the Line-A opcode at `0x10010` are executed for real on target**,
  from `atari/zynaps_os.s`, which is where the "KIT" rows above said the answer would have to come
  from. The ACIA send is BOUNDED there (the original's is not) and its verdict is a record field.
  What is still unpinned is the 6301's *response* — M1 reads no input at all.

The verified counts above are untouched by any of this: `atari/` compiles the cores unchanged, and
`atari/build.sh` measures that (no core includes a shim header, and no core reads a target-only
`-D`). `make test` is still **2700 passed** with `atari/` present.
